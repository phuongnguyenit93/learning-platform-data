# LEFT JOIN, RIGHT JOIN, and FULL JOIN in PostgreSQL

## 1. Why Do We Need OUTER JOIN?

In a relational database, data is typically split across multiple tables to avoid duplication and maintain integrity. For example, the `departments` table stores departments, while the `employees` table stores employees and the department ID they belong to.

When combining two tables, the business question can vary:

- "List **employees who have a department**" → `INNER JOIN` can be used.
- "List **all departments**, including departments with no employees" → `LEFT JOIN`.
- "List **all employees**, including those not yet assigned to a department" → `RIGHT JOIN` or rewrite as `LEFT JOIN` with the table order reversed.
- "List **all departments and all employees**, including unmatched records" → `FULL JOIN`.

The last three joins are **outer joins**. They preserve rows that do not find a matching partner on one or both sides, filling in `NULL` for the columns of the missing side.

PostgreSQL supports the following forms:

```sql
LEFT JOIN         -- equivalent to LEFT OUTER JOIN
RIGHT JOIN        -- equivalent to RIGHT OUTER JOIN
FULL JOIN         -- equivalent to FULL OUTER JOIN
```

The `OUTER` keyword can be omitted without changing the meaning.

### Lesson Objectives

After completing this lesson, you will:

1. Clearly distinguish `INNER`, `LEFT`, `RIGHT`, and `FULL JOIN` using a dataset with verifiable results.
2. Understand **which table is preserved** and why columns on the unmatched side become `NULL`.
3. Write `ON`, `USING`, and place `WHERE` filters in the right place.
4. Count related records using `COUNT` without miscounting rows introduced by an outer join.
5. Find records **without a partner** using an anti-join or `NOT EXISTS`.
6. Understand why a one-to-many join can **increase the number of rows** in the result.
7. Use `COALESCE`, `CASE`, `GROUP BY`, and `ORDER BY` with outer joins.
8. Identify situations where a condition accidentally turns an outer join into an inner join.
9. Know how to use `EXPLAIN` and indexes to inspect join performance.
10. Apply these joins to department–employee reports, customer–order reports, and data reconciliation.

## 2. Shared Practice Dataset

To observe the true behavior of the three joins, we need:

- Two departments **with employees**.
- Two departments **without employees**.
- One employee **not belonging to any department**.
- One department with **multiple employees**, to clearly observe row multiplication.

### 2.1. Relationship Diagram

```text
departments                              employees
+---------------+---------------+       +-------------+--------------+---------------+
| department_id | department_name|       | employee_id | employee_name| department_id |
+---------------+---------------+       +-------------+--------------+---------------+
|      10       | Sales         |<------+|     101     | An           |      10       |
|      20       | Engineering   |<--+    |     102     | Bình         |      10       |
|      30       | HR            |   +----|     103     | Chi          |      20       |
|      40       | Support       |        |     104     | Dũng         |      NULL     |
+---------------+---------------+       +-------------+--------------+---------------+

Department 10 has 2 employees.
Department 20 has 1 employee.
Departments 30 and 40 have no employees yet.
Employee 104 is not assigned to any department yet.
```

This is a **one-to-many** relationship: one department can have many employees, and each employee has at most one department in this simplified model.

### 2.2. Creating the Schema and Tables

In a PostgreSQL database **dedicated to learning**, using a role with privileges to create schemas/tables:

```sql
CREATE SCHEMA IF NOT EXISTS join140;

CREATE TABLE join140.departments (
    department_id bigint PRIMARY KEY,
    department_name text NOT NULL UNIQUE,
    office_city text
);

CREATE TABLE join140.employees (
    employee_id bigint PRIMARY KEY,
    employee_name text NOT NULL,
    department_id bigint
        REFERENCES join140.departments(department_id),
    is_active boolean NOT NULL,
    monthly_salary numeric(12,2) NOT NULL
        CHECK (monthly_salary >= 0)
);
```

Explanation:

- `department_id` in `departments` is the primary key, so it is non-NULL and unique.
- `employees.department_id` is a **nullable** foreign key, because some employees do not belong to a department yet.
- The foreign key prevents an employee from referencing a **non-existent** department ID, when that ID is non-NULL.
- The `is_active` column helps practice the difference between filters placed in `ON` vs. `WHERE`.
- `monthly_salary` helps demonstrate aggregations after an outer join.

The `CREATE TABLE` statements are written for a **fresh lab schema without existing tables of the same name**. If the tables already exist, do not blindly run `DROP TABLE CASCADE` to re-run them without confirming the data can be deleted.

### 2.3. Inserting Sample Data

```sql
INSERT INTO join140.departments
    (department_id, department_name, office_city)
VALUES
    (10, 'Sales', 'Ho Chi Minh City'),
    (20, 'Engineering', 'Hanoi'),
    (30, 'HR', 'Ho Chi Minh City'),
    (40, 'Support', 'Da Nang');

INSERT INTO join140.employees
    (employee_id, employee_name, department_id,
     is_active, monthly_salary)
VALUES
    (101, 'An',   10,   TRUE,  15000000.00),
    (102, 'Bình', 10,   FALSE, 12000000.00),
    (103, 'Chi',  20,   FALSE, 20000000.00),
    (104, 'Dũng', NULL, TRUE,  11000000.00);
```

### 2.4. Inspecting the Input Data

```sql
SELECT department_id, department_name, office_city
FROM join140.departments
ORDER BY department_id;

SELECT employee_id, employee_name, department_id, is_active
FROM join140.employees
ORDER BY employee_id;
```

Departments table:

| department_id | department_name | office_city |
|---:|---|---|
| 10 | Sales | Ho Chi Minh City |
| 20 | Engineering | Hanoi |
| 30 | HR | Ho Chi Minh City |
| 40 | Support | Da Nang |

Employees table:

| employee_id | employee_name | department_id | is_active |
|---:|---|---:|---|
| 101 | An | 10 | true |
| 102 | Bình | 10 | false |
| 103 | Chi | 20 | false |
| 104 | Dũng | NULL | true |

**Convention:** illustrative tables display `NULL` as text for readability. In some tools, a NULL value may appear as an empty cell or another symbol. The text `NULL` in result tables does not mean the string literal `'NULL'`.

## 3. Reviewing INNER JOIN as a Baseline for Comparison

`INNER JOIN` returns only row pairs that **match the join condition**.

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
INNER JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Result:

| department_id | department_name | employee_id | employee_name |
|---:|---|---:|---|
| 10 | Sales | 101 | An |
| 10 | Sales | 102 | Bình |
| 20 | Engineering | 103 | Chi |

There are **3 rows**:

- Department 10 pairs with An and Bình, producing two rows.
- Department 20 pairs with Chi, producing one row.
- Departments 30 and 40 have no employees, so they disappear from the result.
- Dũng has `department_id = NULL`, so he matches no department.

This is the key boundary: `INNER JOIN` keeps only the **intersection satisfying the join condition**, whereas outer joins also keep rows that fail to find a match.

### 3.1. Visual Diagram of the Join Types

```text
               Left table (L)          Right table (R)
                   _______             _______
                  /       \           /       \
                 / L-only  \_________/ R-only  \
                 \         /  MATCH  \         /
                  \_______/           \_______/

INNER JOIN : MATCH only
LEFT JOIN  : L-only + MATCH
RIGHT JOIN : MATCH + R-only
FULL JOIN  : L-only + MATCH + R-only
```

This diagram only illustrates **which row groups are kept**. SQL evaluates results using multiset (*bag*) semantics, so a row on the left can match **multiple rows** on the right and appear multiple times.

## 4. LEFT JOIN: Preserving All Rows of the Left Table

### 4.1. Syntax

```sql
SELECT ...
FROM left_table AS l
LEFT JOIN right_table AS r
    ON join_condition;
```

How to read it:

1. Examine each row in the **left table**.
2. Find rows on the right that satisfy the `ON` condition.
3. If one or more rows match, return one result row for **each matching pair**.
4. If no right-side row matches, still return **one row** containing the left-side data, with `NULL` in the right-side columns.

`LEFT OUTER JOIN` and `LEFT JOIN` have the exact same meaning.

### 4.2. Listing All Departments, Including Empty Ones

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Result:

| department_id | department_name | employee_id | employee_name |
|---:|---|---:|---|
| 10 | Sales | 101 | An |
| 10 | Sales | 102 | Bình |
| 20 | Engineering | 103 | Chi |
| 30 | HR | NULL | NULL |
| 40 | Support | NULL | NULL |

There are **5 result rows**, even though the `departments` table has only 4 rows:

- Department 10 produces **two rows** because it has two employees.
- Department 20 produces **one row** because it has one employee.
- Departments 30 and 40 each produce **one null-extended row** because no employees match.

These null-extended rows **are not new employee rows stored in the table**. They exist only in the join result.

### 4.3. Why "Keep All Left Rows" Does Not Mean "Row Count Equals the Left Table"

For each department with `m` matching employees:

- If `m > 0`, that department contributes `m` result rows.
- If `m = 0`, that department still contributes 1 null-extended row.

On the dataset above:

```text
Department 10: max(1, 2) = 2
Department 20: max(1, 1) = 1
Department 30: max(1, 0) = 1
Department 40: max(1, 0) = 1
                              ---
Total LEFT JOIN rows       =   5
```

Thus, for a standard `LEFT JOIN` with no final filtering that drops rows, the result row count is **at least** the left table's row count, but can be much larger in a one-to-many or many-to-many relationship.

### 4.4. Swapping Table Order Changes the Question

If you change the left table to `employees`:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_id,
    d.department_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Result:

| employee_id | employee_name | department_id | department_name |
|---:|---|---:|---|
| 101 | An | 10 | Sales |
| 102 | Bình | 10 | Sales |
| 103 | Chi | 20 | Engineering |
| 104 | Dũng | NULL | NULL |

This time **all employees** are kept. Dũng appears even without a department. HR and Support do not appear because they are in the **right table** and have no employees to match.

**Rule for choosing LEFT JOIN:** identify the entity that must appear **in full** in the report, and place the table containing that entity on the left.

## 5. RIGHT JOIN: Preserving All Rows of the Right Table

### 5.1. Syntax

```sql
SELECT ...
FROM left_table AS l
RIGHT JOIN right_table AS r
    ON join_condition;
```

`RIGHT JOIN` preserves rows of the **right table**, regardless of whether the left table has a corresponding record. Columns from the left table are filled with `NULL` when there is no match.

### 5.2. Listing All Employees, Including Those Without a Department

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Result:

| department_id | department_name | employee_id | employee_name |
|---:|---|---:|---|
| 10 | Sales | 101 | An |
| 10 | Sales | 102 | Bình |
| 20 | Engineering | 103 | Chi |
| NULL | NULL | 104 | Dũng |

All four employees appear, including Dũng with no department.

### 5.3. RIGHT JOIN Can Be Rewritten as LEFT JOIN

The following two queries have the same logic and the same result multiset when keeping the same join condition and selected columns.

Using `RIGHT JOIN`:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id;
```

Swapping table positions and using `LEFT JOIN`:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id;
```

The difference is **syntax and table order**, not expressive power.

Many engineering teams prefer `LEFT JOIN` so that long SQL queries read naturally from left to right. However, `RIGHT JOIN` remains valid and useful when preserving an existing FROM/JOIN layout or reading queries generated by tools.

### 5.4. RIGHT JOIN Does Not Imply a Performance Preference

Never conclude that RIGHT JOIN is "slower" or "faster" than LEFT JOIN solely because of the join direction. The PostgreSQL optimizer can transform the internal representation and choose an appropriate join strategy. Actual performance depends on cardinality, join predicates, indexes, statistics, and the execution plan.

Best practice: use the JOIN direction that expresses the **clearest intent**, then measure with `EXPLAIN` when performance issues arise.

## 6. FULL JOIN: Preserving Matched and Unmatched Rows from Both Sides

### 6.1. Syntax

```sql
SELECT ...
FROM left_table AS l
FULL JOIN right_table AS r
    ON join_condition;
```

`FULL OUTER JOIN` is equivalent to `FULL JOIN`.

This join returns:

1. All **matching row pairs** according to the `ON` condition.
2. Each **unmatched** left-side row, with right-side columns as NULL.
3. Each **unmatched** right-side row, with left-side columns as NULL.

### 6.2. Listing Both Empty Departments and Unassigned Employees

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

Result:

| dept_id | department_name | emp_id | employee_name |
|---:|---|---:|---|
| 10 | Sales | 101 | An |
| 10 | Sales | 102 | Bình |
| 20 | Engineering | 103 | Chi |
| 30 | HR | NULL | NULL |
| 40 | Support | NULL | NULL |
| NULL | NULL | 104 | Dũng |

There are **6 result rows**:

- **3 matched pairs** between departments and employees.
- **2 unmatched departments**: 30 and 40.
- **1 unmatched employee**: 104.

You can visualize it as:

```text
FULL JOIN = MATCHED + LEFT_ONLY + RIGHT_ONLY

MATCHED    : (10,101), (10,102), (20,103)
LEFT_ONLY  : (30,NULL), (40,NULL)
RIGHT_ONLY : (NULL,104)

Total = 3 + 2 + 1 = 6 rows
```

**FULL JOIN is not CROSS JOIN.** With 4 departments and 4 employees, `CROSS JOIN` produces 16 pairs before any further filtering. `FULL JOIN` does not pair every row with every other row; it matches rows by `ON` and appends those without a partner.

### 6.3. Classifying the Three Row Groups with CASE

Since `department_id` in departments and `employee_id` in employees are both `NOT NULL` primary keys, we can use these exact columns to determine which side is present.

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name,
    CASE
        WHEN d.department_id IS NULL THEN 'EMPLOYEE_ONLY'
        WHEN e.employee_id IS NULL THEN 'DEPARTMENT_ONLY'
        ELSE 'MATCHED'
    END AS match_status
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

Result in the `match_status` column:

| dept_id | emp_id | match_status |
|---:|---:|---|
| 10 | 101 | MATCHED |
| 10 | 102 | MATCHED |
| 20 | 103 | MATCHED |
| 30 | NULL | DEPARTMENT_ONLY |
| 40 | NULL | DEPARTMENT_ONLY |
| NULL | 104 | EMPLOYEE_ONLY |

**Why use primary keys for classification?** Because the primary key of a real row cannot be NULL. If you pick a nullable column such as `office_city`, then `office_city IS NULL` could mean "the department exists but has no city entered yet" rather than "there is no department."

## 7. Comparison Table of the Four JOIN Types on the Same Data

| Join Type | Preserved Rows | Example Row Count | Do Depts 30 & 40 Appear? | Does Dũng Appear? |
|---|---|---:|---|---|
| `INNER JOIN` | Matched pairs only | 3 | No | No |
| `departments LEFT JOIN employees` | All departments | 5 | Yes | No |
| `departments RIGHT JOIN employees` | All employees | 4 | No | Yes |
| `departments FULL JOIN employees` | All records from both sides | 6 | Yes | Yes |

This table holds for the **sample dataset in section 2** and the written JOIN conditions. Row counts will change when data or join conditions change.

### 7.1. Choosing SQL from Business Requirements

| Business Question | Recommended Join Direction |
|---|---|
| List of departments and employees, including empty departments | `departments LEFT JOIN employees` |
| List of all employees and their departments if any | `employees LEFT JOIN departments` |
| Keep FROM order starting from departments while still listing all employees | `departments RIGHT JOIN employees` |
| Reconcile all records across both tables, including unmatched ones | `FULL JOIN` |
| Only employees assigned to a department | `INNER JOIN` |
| Only departments without employees | `LEFT JOIN ... WHERE e.employee_id IS NULL` or `NOT EXISTS` |
| Only employees without a department | `employees LEFT JOIN departments ... WHERE d.department_id IS NULL` |
| Count employees in every department, including 0 counts | `departments LEFT JOIN employees` and `COUNT(e.employee_id)` |

## 8. Mastering ON vs. WHERE: The Most Common Outer Join Bug

In a `LEFT JOIN`, the two places where you put a condition can produce **two different results**:

- `ON` determines **which rows are considered a match**.
- `WHERE` filters **the rows of the result after the join**.

This distinction is especially critical when the right table might not match.

### 8.1. Putting the Active-Employee Filter in ON

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.is_active
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND e.is_active = TRUE
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Result:

| department_id | department_name | employee_id | employee_name | is_active |
|---:|---|---:|---|---|
| 10 | Sales | 101 | An | true |
| 20 | Engineering | NULL | NULL | NULL |
| 30 | HR | NULL | NULL | NULL |
| 40 | Support | NULL | NULL | NULL |

Explanation:

- Department 10 matches active employee An; Bình is not treated as a matching pair because `is_active = FALSE`.
- Department 20 has Chi, but Chi is inactive, so **no right-side row satisfies the entire ON clause**; department 20 is still preserved with NULL employee columns.
- Departments 30/40 have no employees anyway and are still preserved.

`LEFT JOIN` preserves all department rows even when **there are no active employees**.

### 8.2. Moving the Same Condition to WHERE

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name,
    e.is_active
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.is_active = TRUE
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Result:

| department_id | department_name | employee_id | employee_name | is_active |
|---:|---|---:|---|---|
| 10 | Sales | 101 | An | true |

Why did departments 20, 30, and 40 disappear?

- Chi in department 20 has `is_active = FALSE`, so `WHERE` filters her out.
- For departments 30/40 without a partner, `e.is_active` is NULL; comparing `NULL = TRUE` yields **UNKNOWN**, which `WHERE` discards.
- Thus, this condition causes the `LEFT JOIN` to **behave like an INNER JOIN with respect to the filtered condition**.

### 8.3. Rule of Thumb

If the goal is:

> "Show **all departments**, and join only **active employees** if any."

place the employee condition inside `ON`:

```sql
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
  ON e.department_id = d.department_id
 AND e.is_active = TRUE
```

If the goal is:

> "Show only **department–employee pairs** where the employee is active."

then `WHERE e.is_active = TRUE` may be right, though the result no longer preserves all departments.

**Not every WHERE condition breaks an outer join.** For instance, `WHERE d.department_id >= 20` filters on the preserved table and can still retain remaining departments even if they have no employees. The real issue is **conditions that reject null-extended rows** on the non-preserved side.

### 8.4. Thinking in Terms of Logical Processing Order

A helpful mental model:

1. Read sources from `FROM`.
2. Determine matching pairs via `ON`.
3. For outer joins, add null-extended rows for the preserved side(s).
4. Apply the `WHERE` filter.
5. Perform grouping/aggregation, evaluate SELECT, sort, and apply LIMIT according to SQL rules.

This order is a **logical model for understanding results**, not a promise that PostgreSQL physically executes each step in that exact order. The optimizer may transform the plan as long as query semantics are preserved.

## 9. Three-Valued Logic: TRUE, FALSE, and UNKNOWN When Comparing NULL

SQL uses three-valued logic when comparing nullable values:

| Expression | Result |
|---|---|
| `10 = 10` | TRUE |
| `10 = 20` | FALSE |
| `NULL = 10` | NULL/UNKNOWN |
| `NULL = NULL` | NULL/UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

In the sample data:

```sql
SELECT employee_id, employee_name
FROM join140.employees
WHERE department_id = NULL;
```

**Does not return Dũng** because `department_id = NULL` is never TRUE for any row. You must use:

```sql
SELECT employee_id, employee_name
FROM join140.employees
WHERE department_id IS NULL;
```

### 9.1. NULL From Non-Matching Differs From NULL Already in the Data

For a `LEFT JOIN`, a NULL column from the right table could be either:

- A column that is genuinely NULL in a **matched right-side row**.
- A column that is NULL because **no right-side row matched**.

To detect whether a right-side record actually exists, always use a **NOT NULL primary key** such as `e.employee_id`.

Example:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.department_id AS employee_department_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

For departments 30/40, `e.employee_id IS NULL` proves there is no matching employee because a real employee row cannot have a NULL primary key.

### 9.2. Should You Use IS NOT DISTINCT FROM in ON?

In PostgreSQL:

```sql
SELECT
    NULL::integer IS NOT DISTINCT FROM NULL::integer AS both_null_equal,
    NULL::integer = NULL::integer AS normal_equality;
```

The first expression returns TRUE; the second returns NULL/UNKNOWN.

If both join keys are nullable **and the business genuinely wants NULL on both sides to match**, `IS NOT DISTINCT FROM` may be considered in certain joins. However, matching records that "have no code" with one another can produce many unwanted pairs. For identifier keys, the better design is usually to **make keys NOT NULL with explicit values**.

## 10. Finding Rows Without a Partner: Anti-Join

Applications frequently need answers to questions like:

- Which departments **have no employees yet**?
- Which employees **have not been assigned to a department**?
- Which customers **have never placed an order**?
- Which products **have no corresponding inventory record**?

Semantically, this pattern is called an **anti-join**: finding rows for which no related record exists.

### 10.1. Departments Without Employees Using LEFT JOIN

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

Result:

| department_id | department_name |
|---:|---|
| 30 | HR |
| 40 | Support |

Why is `WHERE e.employee_id IS NULL` valid here when the previous section warned that WHERE can break an outer join?

Because **this time the goal is specifically to keep only the null-extended rows**. The `IS NULL` condition selects departments *with no matching employees*, rather than filtering on an attribute of real employees.

### 10.2. Same Requirement Using NOT EXISTS

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM join140.employees AS e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
```

The result is also departments 30 and 40.

`NOT EXISTS` directly expresses "no row exists satisfying the correlated condition." It is often more readable and avoids needing to pick a guaranteed NOT NULL column on the right side to detect non-matches. The PostgreSQL optimizer can execute it using an appropriate anti-join plan.

### 10.3. Employees Without a Department

```sql
SELECT
    e.employee_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL
ORDER BY e.employee_id;
```

Result: employee `104 — Dũng`.

With a valid foreign key as in the lab schema, any **non-NULL** `department_id` must reference an existing department. Therefore, in this dataset, an unmatched employee is one with a `NULL` `department_id`. In a staging table without a foreign key, an invalid department ID can also produce an unmatched row.

### 10.4. Why Can NOT IN Produce Unexpected Results?

Consider:

```sql
SELECT department_id, department_name
FROM join140.departments
WHERE department_id NOT IN (
    SELECT department_id
    FROM join140.employees
)
ORDER BY department_id;
```

The subquery returns the values `10, 10, 20, NULL`.

Because `NULL` is present in the set, `NOT IN` evaluates to UNKNOWN for absent department IDs (30 and 40), preventing them from **being returned**. The query above is expected to **return zero rows** on this lab dataset.

Using `NOT EXISTS` or an anti-join is much clearer and safer:

```sql
SELECT d.department_id
FROM join140.departments AS d
WHERE NOT EXISTS (
    SELECT 1
    FROM join140.employees AS e
    WHERE e.department_id = d.department_id
);
```

Never equate `NOT IN (subquery)` with `NOT EXISTS` when the subquery might return NULL.

## 11. Counting Related Records: COUNT(*) vs. COUNT(column)

Suppose a report requires:

> "Every department must appear; any department with no employees should show a count of 0."

You can use `LEFT JOIN` and `GROUP BY`:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Result:

| department_id | department_name | employee_count |
|---:|---|---:|
| 10 | Sales | 2 |
| 20 | Engineering | 1 |
| 30 | HR | 0 |
| 40 | Support | 0 |

### 11.1. Why Not Use COUNT(*)?

```sql
SELECT
    d.department_id,
    COUNT(*) AS joined_row_count,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id
ORDER BY d.department_id;
```

Result:

| department_id | joined_row_count | employee_count |
|---:|---:|---:|
| 10 | 2 | 2 |
| 20 | 1 | 1 |
| 30 | 1 | 0 |
| 40 | 1 | 0 |

`COUNT(*)` counts **every result row after the join**, including the null-extended row representing an empty department. Since each empty department still contributes one row, `COUNT(*)` returns 1.

`COUNT(e.employee_id)` counts only rows where the employee's primary key is **not NULL**, so empty departments return 0.

**Principle:** when counting actual matched records on the non-preserved side, use `COUNT(right_pk)` or an appropriate counting expression rather than defaulting to `COUNT(*)`.

### 11.2. Counting Active Employees

PostgreSQL supports `FILTER` in aggregates:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS total_employees,
    COUNT(e.employee_id)
        FILTER (WHERE e.is_active IS TRUE) AS active_employees
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Result:

| department_id | total_employees | active_employees |
|---:|---:|---:|
| 10 | 2 | 1 |
| 20 | 1 | 0 |
| 30 | 0 | 0 |
| 40 | 0 | 0 |

Here we want to **count two groups** over the same row set, so `FILTER` is very clear.

An alternative is placing `e.is_active = TRUE` inside `ON` if you only care about active employees while still keeping every department.

### 11.3. Total Salary Including Empty Departments

```sql
SELECT
    d.department_id,
    d.department_name,
    COALESCE(SUM(e.monthly_salary), 0) AS total_monthly_salary
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Expected result:

| department_id | total_monthly_salary |
|---:|---:|
| 10 | 27000000.00 |
| 20 | 20000000.00 |
| 30 | 0 |
| 40 | 0 |

`SUM` over a group with no actual salary values returns NULL; `COALESCE(..., 0)` converts the displayed result to 0 as required by the report.

If the business needs to distinguish "no employees" from "salary data not yet determined," do not automatically equate NULL with 0 without careful consideration.

## 12. COALESCE: Displaying a Fallback Value When One Side Does Not Match

`COALESCE(expression1, expression2, ...)` returns the first non-NULL value.

Example:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    COALESCE(d.department_name, 'Unassigned') AS displayed_department
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

Result:

| employee_id | employee_name | displayed_department |
|---:|---|---|
| 101 | An | Sales |
| 102 | Bình | Sales |
| 103 | Chi | Engineering |
| 104 | Dũng | Unassigned |

This makes the UI easier to read. However:

- `COALESCE` only produces a **value in the query output**; it does not update the underlying table.
- The fallback value is a **presentation convention**, not proof that underlying data exists.
- When real data can contain NULL in a descriptive column, a fallback value cannot distinguish between "unmatched record" and "matched record missing a description." Use each side's primary key if you need to distinguish them.

### 12.1. Using COALESCE in FULL JOIN

In reconciliation problems involving two tables that both contain customer IDs, you can use:

```sql
SELECT
    COALESCE(a.customer_id, b.customer_id) AS customer_id,
    a.amount AS source_a_amount,
    b.amount AS source_b_amount
FROM source_a AS a
FULL JOIN source_b AS b
    ON a.customer_id = b.customer_id;
```

The SQL query above is a **template** and only runs if `source_a` and `source_b` exist. It shows how `COALESCE` picks the ID from whichever side is present when a FULL JOIN leaves one side NULL.

In the lab dataset, you can observe something similar:

```sql
SELECT
    COALESCE(d.department_id, e.department_id) AS department_id,
    d.department_name,
    e.employee_id
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY department_id NULLS LAST, e.employee_id NULLS LAST;
```

For Dũng, both `d.department_id` and `e.department_id` are NULL, so `COALESCE` remains NULL. That is accurate: Dũng truly **has not been assigned a department ID**.

## 13. USING and ON in Outer Joins

When two tables share a column name and need an equality join, PostgreSQL allows `USING(column_name)`.

### 13.1. Writing with ON

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON d.department_id = e.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

### 13.2. Writing with USING

```sql
SELECT
    department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    USING (department_id)
ORDER BY department_id, e.employee_id NULLS LAST;
```

For the chosen key relationship, both queries have the same matching semantics.

Key points to remember:

- `USING (department_id)` requires **both tables to have that column**.
- With `SELECT *`, the column used in `USING` normally appears **once** instead of two separate copies `d.department_id` and `e.department_id`.
- With `FULL JOIN ... USING (key)`, the shared output column reflects the value from whichever side is present; semantically, this is similar to coalescing/merging the key values from both sides.
- `ON` is more flexible for differently named columns, multiple predicates, or non-equality conditions.

### 13.3. FULL JOIN with USING

```sql
SELECT
    department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    USING (department_id)
ORDER BY department_id NULLS LAST, e.employee_id NULLS LAST;
```

For departments 30 and 40, the shared `department_id` column is 30 and 40 respectively even though `e.department_id` has no row to supply. For Dũng, the shared value is NULL because there is no department in the employee row.

If you want to **clearly distinguish the originating side of each value** during reconciliation, prefer `ON` and select `d.department_id AS left_id` and `e.department_id AS right_id` separately alongside both NOT NULL primary keys.

### 13.4. Why Not Overuse NATURAL JOIN?

`NATURAL JOIN` automatically picks every column with the same name as a join condition. When a schema evolves and two tables happen to share a newly added column name, **the join logic can silently change**.

For important business data, use explicit `ON` or `USING` so you know exactly which columns are being compared.

## 14. Using FULL JOIN to Reconcile Two Data Sources

Applications often have two lists that need reconciliation:

- User lists from System A and System B.
- Account balances at two points in time.
- Products in the sales system and warehouse system.
- Customer IDs in the CRM and payment system.

The goal is to identify:

1. Present in both sources.
2. Only in the left source.
3. Only in the right source.
4. Present in both sources, but with differing values.

### 14.1. Balance Reconciliation Example

Create two small tables in the lab:

```sql
CREATE TABLE join140.balance_source_a (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

CREATE TABLE join140.balance_source_b (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
);

INSERT INTO join140.balance_source_a(account_id, balance)
VALUES
    (1, 100.00),
    (2, 250.00),
    (3, 300.00);

INSERT INTO join140.balance_source_b(account_id, balance)
VALUES
    (2, 250.00),
    (3, 310.00),
    (4, 400.00);
```

### 14.2. FULL JOIN Classifying the Results

```sql
SELECT
    COALESCE(a.account_id, b.account_id) AS account_id,
    a.balance AS balance_a,
    b.balance AS balance_b,
    CASE
        WHEN a.account_id IS NULL THEN 'ONLY_B'
        WHEN b.account_id IS NULL THEN 'ONLY_A'
        WHEN a.balance IS DISTINCT FROM b.balance THEN 'VALUE_DIFF'
        ELSE 'MATCH'
    END AS reconciliation_status
FROM join140.balance_source_a AS a
FULL JOIN join140.balance_source_b AS b
    ON a.account_id = b.account_id
ORDER BY account_id;
```

Result:

| account_id | balance_a | balance_b | reconciliation_status |
|---:|---:|---:|---|
| 1 | 100.00 | NULL | ONLY_A |
| 2 | 250.00 | 250.00 | MATCH |
| 3 | 300.00 | 310.00 | VALUE_DIFF |
| 4 | NULL | 400.00 | ONLY_B |

Key takeaways:

- `COALESCE(a.account_id,b.account_id)` displays the account ID from whichever side has the record.
- Both NOT NULL primary keys distinguish records that are **only in A** vs. **only in B**.
- `IS DISTINCT FROM` is a **NULL-safe** comparison, useful when either source may contain NULL in the compared column.
- Do not rely solely on `a.balance <> b.balance` to detect all differences if one side can be NULL, because standard comparisons with NULL yield UNKNOWN.

In this example `balance` is declared NOT NULL, yet `IS DISTINCT FROM` remains a valuable pattern when reconciling data that may have missing values.

### 14.3. Filtering Only Discrepant Records

```sql
WITH reconciliation AS (
    SELECT
        COALESCE(a.account_id, b.account_id) AS account_id,
        a.balance AS balance_a,
        b.balance AS balance_b,
        CASE
            WHEN a.account_id IS NULL THEN 'ONLY_B'
            WHEN b.account_id IS NULL THEN 'ONLY_A'
            WHEN a.balance IS DISTINCT FROM b.balance
                THEN 'VALUE_DIFF'
            ELSE 'MATCH'
        END AS match_status
    FROM join140.balance_source_a AS a
    FULL JOIN join140.balance_source_b AS b
        ON a.account_id = b.account_id
)
SELECT *
FROM reconciliation
WHERE match_status <> 'MATCH'
ORDER BY account_id;
```

The result includes accounts 1, 3, and 4.

This is a case where `FULL JOIN` is very natural: we do not want either source A or source B to take priority; both lists must be preserved to surface missing or mismatched data.

## 15. Where to Place Conditions When Using RIGHT JOIN and FULL JOIN?

### 15.1. RIGHT JOIN Also Has the ON/WHERE Trap

Suppose the requirement is:

> "Show all employees, along with department info **if that department is located in Ho Chi Minh City**."

Place the department condition in `ON`:

```sql
SELECT
    e.employee_id,
    e.employee_name,
    d.department_name,
    d.office_city
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND d.office_city = 'Ho Chi Minh City'
ORDER BY e.employee_id;
```

Result: all four employees remain present.

- An and Bình belong to Sales in Ho Chi Minh City, so they match.
- Chi belongs to Engineering in Hanoi, which **fails the full ON condition**, so department columns in her output are NULL.
- Dũng has no department, so his department columns are NULL.

Notice that Chi's NULL department columns **do not mean the underlying data lacks a department**: they are a consequence of the **join condition**.

If you put the condition in `WHERE d.office_city = 'Ho Chi Minh City'`, Chi and Dũng would be dropped from the result. That `RIGHT JOIN` would no longer preserve all employees.

### 15.2. FULL JOIN with WHERE Can Drop One or Both Unmatched Sides

Example:

```sql
SELECT
    d.department_id,
    e.employee_id
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.office_city = 'Ho Chi Minh City'
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

This query keeps only rows whose department info satisfies the city condition. Rows where the department side is NULL, such as Dũng, are discarded despite using `FULL JOIN`.

Therefore, whenever the requirement is "keep both sources in full," every `WHERE` filter after a `FULL JOIN` must be scrutinized carefully.

### 15.3. Filtering Unmatched Rows on Either Side

A common reconciliation query:

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL
   OR e.employee_id IS NULL
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

The result includes:

| dept_id | department_name | emp_id | employee_name |
|---:|---|---:|---|
| 30 | HR | NULL | NULL |
| 40 | Support | NULL | NULL |
| NULL | NULL | 104 | Dũng |

This is the **symmetric difference** under the join condition: keeping rows that appear on only one side.

## 16. One-to-Many, Many-to-Many JOINs, and Row Multiplication

### 16.1. One-to-Many

In the lab data, one department can have many employees. When joining department 10, the department row appears twice because two employees match it.

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.department_id = 10
ORDER BY e.employee_id;
```

Result:

```text
department_id | department_name | employee_id
--------------+-----------------+------------
10            | Sales           | 101
10            | Sales           | 102
```

These two rows are not "erroneously duplicated" data. They are **two distinct matching pairs**.

### 16.2. Many-to-Many and the Risk of Severe Row Explosion

Suppose we join:

```text
departments -> employees -> employee_skills
```

A department with 10 employees, each having 5 skills, can produce around 50 rows for that department in the join result.

If a report runs `SUM(d.department_budget)` over every post-join row, the department budget gets **counted repeatedly**. This is a common reporting bug known as **fan-out multiplication**.

Solutions depending on the scenario:

- Aggregate one-to-many data in a subquery/CTE **before joining**.
- Use `COUNT(DISTINCT employee_id)` when you truly need to count unique employees.
- Use `EXISTS` for existence-only checks to avoid duplicating result rows.
- Identify the exact reporting grain required: one row per department, one row per employee, or one row per skill.

**Do not use `DISTINCT` as a bandage for every join bug.** It can hide incorrect join logic and make aggregated results hard to verify.

### 16.3. Risk of Missing Join Conditions

If you write:

```sql
SELECT *
FROM join140.departments AS d
JOIN join140.employees AS e
    ON TRUE;
```

every department pairs with every employee: 4 × 4 = 16 pairs in this dataset. The query is not filtered by the department relationship.

A `JOIN` with the right join keyword but a missing business predicate still produces wrong data. When keys have multiple columns, include every key column—for example, both `tenant_id` and `department_id` in a multi-tenant system.

## 17. Pre-Aggregating Before LEFT JOIN: One Row per Department

Suppose you need employee statistics without repeating department rows.

Approach 1: `GROUP BY` after `LEFT JOIN` as in section 11.

Approach 2: **Aggregate employees first**, then join:

```sql
WITH employee_stats AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        SUM(monthly_salary) AS total_salary
    FROM join140.employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
)
SELECT
    d.department_id,
    d.department_name,
    COALESCE(s.employee_count, 0) AS employee_count,
    COALESCE(s.total_salary, 0) AS total_salary
FROM join140.departments AS d
LEFT JOIN employee_stats AS s
    ON s.department_id = d.department_id
ORDER BY d.department_id;
```

Result:

| department_id | employee_count | total_salary |
|---:|---:|---:|
| 10 | 2 | 27000000.00 |
| 20 | 1 | 20000000.00 |
| 30 | 0 | 0 |
| 40 | 0 | 0 |

Here `employee_stats` has at most one row per `department_id`, so joining it with `departments` produces exactly **one row per department**.

This pattern is very effective when a report combines multiple detail tables: aggregate each source to the same grain first, then join to avoid cross-multiplying rows.

## 18. LEFT JOIN LATERAL: Fetching One Related Record per Left Row

PostgreSQL supports `LATERAL`, allowing a trailing subquery to reference columns from preceding items in `FROM`.

Example requirement:

> "List every department along with the **highest-paid employee** in that department; still show empty departments."

```sql
SELECT
    d.department_id,
    d.department_name,
    top_employee.employee_id,
    top_employee.employee_name,
    top_employee.monthly_salary
FROM join140.departments AS d
LEFT JOIN LATERAL (
    SELECT
        e.employee_id,
        e.employee_name,
        e.monthly_salary
    FROM join140.employees AS e
    WHERE e.department_id = d.department_id
    ORDER BY e.monthly_salary DESC, e.employee_id ASC
    LIMIT 1
) AS top_employee
    ON TRUE
ORDER BY d.department_id;
```

Result:

| department_id | department_name | employee_id | employee_name | monthly_salary |
|---:|---|---:|---|---:|
| 10 | Sales | 101 | An | 15000000.00 |
| 20 | Engineering | 103 | Chi | 20000000.00 |
| 30 | HR | NULL | NULL | NULL |
| 40 | Support | NULL | NULL | NULL |

Explanation:

- The right-side subquery is correlated with `d.department_id`.
- `ORDER BY ... LIMIT 1` selects at most one employee for the current department.
- `LEFT JOIN LATERAL ... ON TRUE` still preserves the department if the subquery returns zero rows.
- Departments 30 and 40 appear with NULL employee columns.

This is a very practical way to implement **top-1 per parent**, though it is not guaranteed to outperform window-function solutions in every case. On large datasets, indexes and data distribution determine performance.

## 19. FULL JOIN and UNION ALL: Understanding via Two Branches

You can decompose `FULL JOIN` into:

1. All rows of a `LEFT JOIN` from left to right.
2. Plus rows that exist **only in the right table** and were not produced in the first branch.

Illustrative equivalent to the dataset's FULL JOIN:

```sql
SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id

UNION ALL

SELECT
    d.department_id AS dept_id,
    d.department_name,
    e.employee_id AS emp_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL

ORDER BY dept_id NULLS LAST, emp_id NULLS LAST;
```

Explanation:

- Branch 1 contains matched pairs and departments without employees.
- Branch 2 contains only employees without a matching department (Dũng in the example).
- `UNION ALL` **keeps every row**, matching the bag semantics of JOIN.
- The `WHERE d.department_id IS NULL` filter in branch 2 prevents matched pairs already in branch 1 from being appended again.

**Do not write two LEFT JOINs and UNION ALL everything** while forgetting to filter the right-only group, as matched pairs would be counted twice.

### 19.1. Why Not Arbitrarily Replace UNION ALL with UNION?

`UNION` deduplicates identical rows across the selected columns. In cases where two distinct underlying records happen to share the same projected values, `UNION` merges them and loses multiplicity.

By contrast, `FULL JOIN` never deduplicates rows that happen to have identical projected values.

To compare results accurately under multiset semantics, `UNION ALL` combined with a proper anti-join is the faithful decomposition.

### 19.2. Should You Manually Replace FULL JOIN with UNION ALL in Production?

Not unless there is a specific reason involving compatibility, architecture, or query plans. PostgreSQL supports `FULL JOIN` natively; the `FULL JOIN` syntax is shorter and communicates reconciliation intent much more clearly.

The two-branch decomposition is primarily meant for **understanding how the join works**, not as a mandatory optimization rule.

## 20. Combining Multiple OUTER JOINs in One Query

Real-world reports might join:

```text
departments
   LEFT JOIN employees
   LEFT JOIN employee_profiles
   LEFT JOIN attendance_records
```

Crucially, each JOIN produces an intermediate result; each subsequent JOIN operates on the accumulated result so far. If the third table has multiple records per employee, row counts can continue to multiply.

### 20.1. A Trailing Inner Join Can Drop Rows Preserved by an Outer Join

Suppose there is an `employee_profiles` table. A query like:

```sql
SELECT ...
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
  ON e.department_id = d.department_id
INNER JOIN employee_profiles AS p
  ON p.employee_id = e.employee_id;
```

is an **illustrative pattern** and only runs if `employee_profiles` exists.

Because `INNER JOIN employee_profiles` requires a matching `e.employee_id`, empty departments can be dropped from the final result even though the first step used `LEFT JOIN`.

If the goal is to preserve all departments, review condition placement, join types on subsequent steps, or pre-aggregate child data before joining.

### 20.2. Using Parentheses to Clarify Join Grouping

With multiple outer joins, the placement of `ON` and **table pairing order** can change results. Not all outer joins can be freely reordered and reassociated like inner joins.

You can use parentheses:

```sql
FROM table_a AS a
LEFT JOIN (
    table_b AS b
    INNER JOIN table_c AS c
      ON c.b_id = b.id
) ON b.a_id = a.id
```

This is a syntax pattern; the concrete tables must exist. Parentheses tell the reader that B and C are inner-joined first before the entire group is outer-joined to preserve A according to query semantics.

## 21. WHERE, GROUP BY, HAVING, and ORDER BY with OUTER JOIN

### 21.1. Output Order Is Not Automatically Guaranteed

Even if a `LEFT JOIN` appears to return departments in physical table order, SQL **guarantees no ordering** without `ORDER BY`.

```sql
SELECT d.department_id, e.employee_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

Whenever you need pagination, reporting, or deterministic test output, always define an explicit sort order.

### 21.2. NULLS FIRST and NULLS LAST

PostgreSQL supports:

```sql
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

This is very handy for FULL JOIN where an unmatched side leaves the other side's key as NULL. Never assume NULLs always sort first or last across all sort directions.

### 21.3. Using HAVING to Find Empty Departments

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(e.employee_id) = 0
ORDER BY d.department_id;
```

Result: departments 30 and 40.

Unlike `WHERE`, `HAVING` filters **groups after aggregation**. When the task is "departments with an employee count of 0," `HAVING COUNT(...) = 0` is an appropriate way to express it.

### 21.4. Counting Only Departments with at Least Two Employees

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(e.employee_id) >= 2;
```

Result: only Sales, with 2 employees.

## 22. JOIN and Foreign Keys: Related, Not Interchangeable

In the lab schema:

```sql
employees.department_id
    REFERENCES departments.department_id
```

The foreign key ensures that any employee with a non-NULL `department_id` must reference an existing department.

However, the foreign key does not force **every employee to have a department**, because the column is nullable. That is why Dũng matches no department in a JOIN.

If a new requirement states "every employee must belong to a department," you can change the model so `department_id` is `NOT NULL` with a foreign key; valid data will then have no unassigned employees.

**Yet even when foreign keys are always valid, a LEFT JOIN from departments to employees is still needed** if departments are allowed to exist without employees.

### 22.1. Unmatched Rows Are Not Always Corrupt Data

- A department that hasn't hired anyone yet: can be **completely valid**.
- An employee not yet assigned to a department: can be a **valid transitional state**.
- An order record with no customer in a staging table: can be **data needing investigation**.
- Two reconciled sources missing an account: can be a **discrepancy requiring action**.

An outer join tells us **whether a partner exists**, without judging whether that state is right or wrong in business terms.

## 23. Outer Join Performance in PostgreSQL

An outer join is neither automatically slower nor automatically faster than an inner join. Performance depends on data volume, join predicates, selectivity, indexes, statistics, and output row count.

### 23.1. Inspecting Plans with EXPLAIN

```sql
EXPLAIN
SELECT
    d.department_id,
    d.department_name,
    e.employee_id
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

PostgreSQL can use strategies such as:

- **Nested Loop Join**: scans one source and looks up matching rows from the other.
- **Hash Join**: builds a hash table and matches rows on the appropriate condition.
- **Merge Join**: merges sources already ordered by the join keys.

In the plan output you may see labels like `Hash Left Join`, `Merge Left Join`, or plan forms transformed by the optimizer. On small tables, a sequential scan is often the cheapest option.

**Do not infer performance solely from the LEFT/RIGHT/FULL keyword in SQL.** Inspect the actual plan and node row counts when tuning.

### 23.2. Indexes on Foreign Keys

PostgreSQL creates indexes as needed to enforce primary key/unique constraints. However, it **does not automatically create indexes on child-table foreign key columns**.

For the `employees` table, you might consider:

```sql
CREATE INDEX idx_join140_employees_department
ON join140.employees(department_id);
```

This index can help with:

- Looking up employees by department.
- Certain join strategies from departments to employees.
- Checking or processing changes related to foreign keys on the parent table.

However, creating an index increases storage usage and write costs. On small tables, the planner may still prefer a sequential scan.

### 23.3. Does EXPLAIN ANALYZE Actually Execute the Query?

Yes. For lab read queries:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    d.department_id,
    COUNT(e.employee_id)
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id;
```

`EXPLAIN ANALYZE` executes the query to measure actual row counts and timings. For read-only `SELECT` queries like the one above, it is suitable in a lab; for `UPDATE`, `DELETE`, or statements with side effects, protect transactions and environments before running.

### 23.4. Statistics and Cardinality Estimates

The optimizer relies on statistics to choose a plan. If data distribution shifts dramatically after a bulk load, a DBA or maintenance routine may need to run `ANALYZE` per operational policy.

Lab example:

```sql
ANALYZE join140.departments;
ANALYZE join140.employees;
```

This refreshes statistics; it is not a data test or a guarantee that every JOIN gets an optimal plan. On production systems, evaluate timing and cost.

### 23.5. Optimizing Output Row Count

If a report only needs to know whether a department **has any employees or not**, there is no need to fetch every employee and apply `DISTINCT`.

You can use:

```sql
SELECT
    d.department_id,
    d.department_name,
    EXISTS (
        SELECT 1
        FROM join140.employees AS e
        WHERE e.department_id = d.department_id
    ) AS has_employees
FROM join140.departments AS d
ORDER BY d.department_id;
```

The result has **exactly one row per department**, avoiding row multiplication from a one-to-many relationship.

## 24. Contrasting OUTER JOIN with Set Operations

Beginners often hear:

- INNER is intersection.
- LEFT is the left side plus intersection.
- FULL is union.

That is a memorable intuition, yet **incomplete** because SQL joins operate on rows and row pairs, not merely set unions/intersections of ID lists.

### 24.1. JOIN Pairs Rows Horizontally; UNION Stacks Rows Vertically

`JOIN` widens the column set by combining columns from two sources based on a condition.

`UNION` or `UNION ALL` **stacks rows** from two `SELECT` statements with compatible column counts and types.

Example:

```sql
SELECT employee_id, employee_name
FROM join140.employees
WHERE is_active = TRUE

UNION ALL

SELECT employee_id, employee_name
FROM join140.employees
WHERE is_active = FALSE;
```

This combines two employee lists row-wise; it is **not** a join with departments.

### 24.2. LEFT/RIGHT/FULL Do Not Automatically Deduplicate

If two employees share the same name, selecting only `employee_name` can return duplicate values even though they are two distinct employees. Outer joins do not implicitly apply `DISTINCT`.

Whether to group or count uniquely by a key must be decided by business requirements, not merely because displayed rows look similar.

## 25. Common Mistakes When Using LEFT, RIGHT, and FULL JOIN

### Mistake 1. Writing LEFT JOIN but Filtering the Right Table in WHERE

```sql
SELECT ...
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.is_active = TRUE;
```

This drops departments that have no active employees.

**Fix when you want to keep all departments:**

```sql
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND e.is_active = TRUE
```

### Mistake 2. Counting Empty Departments with COUNT(*)

Because the null-extended row still exists, `COUNT(*)` counts 1 for an empty department.

**Fix:** use `COUNT(e.employee_id)` when `employee_id` is a NOT NULL primary key.

### Mistake 3. Detecting Non-Matches Using a Nullable Column

```sql
WHERE e.some_optional_value IS NULL
```

This can also pick up matched employee rows whose optional column happens to be NULL.

**Fix:** use `e.employee_id IS NULL` or `NOT EXISTS` to detect the absence of a partner.

### Mistake 4. Swapping Tables Without Re-evaluating JOIN Direction

`departments LEFT JOIN employees` keeps departments; `employees LEFT JOIN departments` keeps employees. The two queries answer different questions.

**Fix:** state "which entity must appear in full?" before choosing the left table.

### Mistake 5. Thinking RIGHT JOIN Is Always Required to Keep the Right Table

It can be rewritten as a `LEFT JOIN` by swapping the two tables.

**Fix:** choose the clearest expression; do not assume one direction has an inherent performance edge.

### Mistake 6. Confusing FULL JOIN with CROSS JOIN

`FULL JOIN` keeps matched pairs and unmatched rows; `CROSS JOIN` generates every pair between two tables.

**Fix:** always verify the `ON` condition and the entities being paired.

### Mistake 7. Forgetting NULL Behavior in Join Conditions

`NULL = NULL` returns UNKNOWN, not TRUE. An employee with a `NULL` `department_id` does not automatically match a "NULL department."

**Fix:** define keys cleanly; use `IS NULL` to find missing values, and use null-safe comparisons only when business semantics truly warrant them.

### Mistake 8. Using NOT IN with a Subquery That Can Return NULL

`NOT IN` may return no rows at all due to UNKNOWN logic.

**Fix:** prefer `NOT EXISTS` or a LEFT anti-join when finding unlinked records.

### Mistake 9. Ignoring One-to-Many Cardinality

A department with 10 employees produces 10 rows in a LEFT JOIN, not one row.

**Fix:** pre-aggregate, use `EXISTS`, or pick one employee via `LATERAL`/window functions depending on requirements.

### Mistake 10. Omitting ORDER BY

Display order can change whenever PostgreSQL picks a different execution plan.

**Fix:** add an explicit `ORDER BY`, considering `NULLS FIRST/LAST`.

### Mistake 11. Using DISTINCT to Hide Join Mistakes

`DISTINCT` can drop valid distinct records that happen to share projected values and does not fix an invalid join condition.

**Fix:** verify keys, `ON` conditions, and cardinality before deciding whether deduplication is warranted.

### Mistake 12. Chaining a Subsequent INNER JOIN That Drops Preserved Rows

An initial `LEFT JOIN` keeps empty departments, but a following `INNER JOIN` referencing employee columns removes them.

**Fix:** analyze the entire join chain and filter placement, not just the first JOIN clause.

### Mistake 13. Using FULL JOIN and Adding WHERE on Only One Side

A filter on the left table can drop rows that exist only on the right side; the report then no longer reflects both sources completely.

**Fix:** clarify the reconciliation goal, scope conditions properly, or filter each source inside its own subquery/CTE prior to the FULL JOIN.

### Mistake 14. Joining on Incomplete Same-Named Keys

A multi-tenant system can have the same `department_id` in two different tenants. Joining on `department_id` alone mixes records across tenants.

**Fix:** include the full business key, for example:

```sql
ON e.tenant_id = d.tenant_id
AND e.department_id = d.department_id
```

Combine proper join predicates with authorization/RLS when handling multi-tenant data.

## 26. Comprehensive Practice: From Business Requirements to SQL

Below are common requirements. Each query uses the lab dataset created earlier.

### Practice A. All Departments and Employee Names, If Any

```sql
SELECT
    d.department_name,
    e.employee_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id NULLS LAST;
```

**Answer:** 5 rows, including HR and Support with NULL employee names.

### Practice B. All Employees and Department Names, If Any

```sql
SELECT
    e.employee_name,
    d.department_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

**Answer:** 4 rows, including Dũng with a NULL department name.

### Practice C. Same Requirement as B Using RIGHT JOIN

```sql
SELECT
    e.employee_name,
    d.department_name
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

**Answer:** identical to B.

### Practice D. All Departments and All Employees

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.employee_name
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

**Answer:** 6 rows consisting of three matched pairs, two empty departments, and one unassigned employee.

### Practice E. Only Departments Without Employees

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

**Answer:** departments 30 and 40.

### Practice F. Departments Without Active Employees

```sql
SELECT
    d.department_id,
    d.department_name
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
   AND e.is_active = TRUE
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

**Answer:** departments 20, 30, and 40.

Department 20 has Chi, but Chi is inactive, so department 20 also meets the condition "has no **active** employees."

### Practice G. Only Unassigned Employees

```sql
SELECT
    e.employee_id,
    e.employee_name
FROM join140.employees AS e
LEFT JOIN join140.departments AS d
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL;
```

**Answer:** Dũng (104).

### Practice H. Employee Count in Each Department

```sql
SELECT
    d.department_name,
    COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

**Answer:** Sales 2; Engineering 1; HR 0; Support 0.

### Practice I. Total Payroll of All Departments

```sql
SELECT
    d.department_name,
    COALESCE(SUM(e.monthly_salary), 0) AS payroll
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

**Answer:** Sales 27 million, Engineering 20 million, HR 0, Support 0 (in the lab dataset's currency unit).

### Practice J. Only Unmatched Rows on Either Side

```sql
SELECT
    d.department_id AS dept_id,
    e.employee_id AS emp_id
FROM join140.departments AS d
FULL JOIN join140.employees AS e
    ON e.department_id = d.department_id
WHERE d.department_id IS NULL
   OR e.employee_id IS NULL
ORDER BY d.department_id NULLS LAST,
         e.employee_id NULLS LAST;
```

**Answer:** `(30,NULL)`, `(40,NULL)`, and `(NULL,104)`.

### Practice K. Departments with at Least Two Employees

```sql
SELECT d.department_id, d.department_name,
       COUNT(e.employee_id) AS employee_count
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
    ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
HAVING COUNT(e.employee_id) >= 2;
```

**Answer:** department 10 — Sales.

### Practice L. For Each Department, Select the Highest-Paid Employee

Use `LEFT JOIN LATERAL` as shown in section 18.

**Answer:** department 10 → An; department 20 → Chi; departments 30/40 → NULL.

## 27. Self-Assessment Questions with Answers

### Question 1. Does LEFT JOIN always return the same number of rows as the left table?

**No.** It retains at least one result row per left row when no filtering removes it; if a left row matches multiple right rows, it appears multiple times.

### Question 2. Do LEFT JOIN and RIGHT JOIN differ in expressive power?

**No.** `A RIGHT JOIN B` can be written as `B LEFT JOIN A` with the same condition and appropriate column selection.

### Question 3. What does FULL JOIN return when two tables have zero matching pairs?

It returns all left rows (with right columns NULL) **and** all right rows (with left columns NULL), unless a trailing filter drops rows.

### Question 4. Does FULL JOIN automatically deduplicate rows?

**No.** It retains matching pairs under multiset (bag) semantics. There is no implicit `DISTINCT`.

### Question 5. Why can `WHERE e.is_active = TRUE` cause LEFT JOIN to lose empty departments?

Because `e.is_active` on a null-extended row is NULL; the comparison evaluates to UNKNOWN and is discarded by `WHERE`.

### Question 6. To return all departments and only active employees, where should the filter go?

Usually put `AND e.is_active = TRUE` in `ON` so departments without active employees are preserved.

### Question 7. Should you count employees with COUNT(*) or COUNT(e.employee_id)?

Use `COUNT(e.employee_id)` to count genuinely matched employee rows. `COUNT(*)` also counts null-extended rows of empty departments.

### Question 8. Which syntax finds departments with no employees?

`LEFT JOIN ... WHERE e.employee_id IS NULL` or `NOT EXISTS (...)`.

### Question 9. Why can `NOT IN` be dangerous with nullable keys?

If the subquery returns NULL, `NOT IN` can evaluate to UNKNOWN and fail to return expected records.

### Question 10. Why can joining on a non-unique key increase row counts?

Because each left row can match multiple right rows and vice versa, generating multiple distinct pairs. Understand cardinality and key constraints.

### Question 11. When reconciling two sources, why is FULL JOIN usually suitable?

Because it preserves records present on both sides as well as records unique to either side, enabling MATCHED/ONLY_A/ONLY_B classification.

### Question 12. Does an outer join automatically guarantee output order?

**No.** Use `ORDER BY` and consider `NULLS FIRST/LAST` when stable output is needed.

## 28. Quick Reference Table

| Scenario | SQL Pattern | Key Note |
|---|---|---|
| Matched pairs only | `A INNER JOIN B ON ...` | Unmatched rows are dropped |
| Keep all of A | `A LEFT JOIN B ON ...` | B can be NULL |
| Keep all of B | `A RIGHT JOIN B ON ...` | A can be NULL |
| Keep both A and B | `A FULL JOIN B ON ...` | Both sides can be NULL |
| Rewrite RIGHT | `B LEFT JOIN A ON ...` | Preserve semantics and selected columns |
| Filter B while keeping all of A | `LEFT JOIN B ON ... AND B.flag = ...` | Do not carelessly place in WHERE |
| Only A not matching B | `A LEFT JOIN B ON ... WHERE B.pk IS NULL` | `B.pk` must be NOT NULL on real rows |
| Alternative anti-join | `WHERE NOT EXISTS (SELECT 1 FROM B WHERE ...)` | Avoids the NOT IN NULL trap |
| Count B per every A | `COUNT(B.pk)` after `LEFT JOIN` | Empty groups return 0 |
| Conditional count | `COUNT(B.pk) FILTER (WHERE ...)` | Keeps aggregate logic clear |
| Sum with empty groups | `COALESCE(SUM(B.value), 0)` | NULL and 0 carry different semantics |
| Classify FULL | `CASE WHEN A.pk IS NULL ...` | Use NOT NULL keys |
| Unify report key | `COALESCE(A.id, B.id)` | Picks whichever side is present |
| Same-named key column | `JOIN ... USING (key)` | USING column appears once in SELECT * |
| Top-1 on right per A | `LEFT JOIN LATERAL (...) ON TRUE` | Keeps A when subquery returns no rows |
| Inspect plan | `EXPLAIN SELECT ...` | Planner may transform joins |
| Measure SELECT execution | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` | ANALYZE executes the SQL |
| Sort order with NULLs | `ORDER BY key NULLS LAST` | JOIN does not guarantee order |
| Avoid row multiplication | Pre-aggregate before JOIN / EXISTS | Choose the right data grain |

## 29. Summary

PostgreSQL's three outer joins differ in **which side is preserved**:

```sql
-- Keep all departments:
FROM join140.departments AS d
LEFT JOIN join140.employees AS e
  ON e.department_id = d.department_id

-- Keep all employees:
FROM join140.departments AS d
RIGHT JOIN join140.employees AS e
  ON e.department_id = d.department_id

-- Keep both sides:
FROM join140.departments AS d
FULL JOIN join140.employees AS e
  ON e.department_id = d.department_id
```

When writing and reading queries, ask yourself in order:

1. **Which entity must appear in full?** Choose LEFT, RIGHT, or FULL based on the side(s) to preserve.
2. **When are two rows considered a match?** Define the full `ON` or `USING` condition.
3. **Is there a one-to-many relationship?** Do not confuse joined row count with left-table record count.
4. **Filter in ON or WHERE?** Conditions on a non-preserved side can drop null-extended rows.
5. **How is NULL interpreted?** Use NOT NULL primary keys to detect non-matches; never use `= NULL`.
6. **Are you counting, aggregating, or reconciling?** Use `COUNT(B.pk)`, `COALESCE`, `CASE`, `NOT EXISTS`, and `FULL JOIN` for the right goal.
7. **Must the result have a deterministic order?** Add `ORDER BY`.
8. **Is performance truly an issue?** Check row counts, indexes, and `EXPLAIN` plans rather than guessing from the JOIN keyword name.

**Core takeaway:** `LEFT JOIN` keeps all rows on the left; `RIGHT JOIN` keeps all rows on the right; `FULL JOIN` keeps matched and unmatched rows from both sides. A deep grasp of `ON`, `WHERE`, `NULL`, and cardinality lets you write accurate PostgreSQL reports even when relationships between tables are incomplete.
