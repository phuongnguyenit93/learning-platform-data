# Scalar Subqueries and the At-Most-One-Row Requirement in Oracle Database

## 1. When Is a Subquery Used as a Value?

In a SQL statement, there are times when we need **a single value** from another table to display, calculate, or compare. For example:

- Displaying the department name next to each employee.
- Comparing an employee's salary with that department's average salary.
- Looking up the current tax rate for an item code.
- Assigning a value to a column during an UPDATE.
- Fetching the latest transaction date for each account.

A natural way to express this is placing a subquery in an expression position:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM   departments d
        WHERE  d.department_id = e.department_id) AS department_name
FROM   employees e;
~~~

The part inside parentheses is a **scalar subquery**: a subquery used as a scalar value in the outer SQL statement. Oracle requires a scalar subquery to return **one column and at most one row**:

- **One row, one column:** takes the value in that column.
- **Zero rows:** the scalar subquery evaluates to SQL NULL.
- **More than one row:** Oracle raises `ORA-01427: single-row subquery returns more than one row`.

This is the core takeaway of this lesson. A subquery does not automatically become a single value merely by placing it in parentheses. The database schema or query logic must guarantee appropriate cardinality.

> This lesson uses Oracle Database 19c syntax. Examples use the familiar `EMPLOYEES` and `DEPARTMENTS` tables from the HR model; some sections have standalone lab tables. Substitute table and column names to match your real schema. Run CREATE/INSERT statements only in a permitted lab schema.

## 2. What Is a Scalar Subquery?

According to the SQL Language Reference, a scalar subquery expression is a subquery that returns **exactly one column value from one row**. It must be enclosed in its own parentheses:

~~~sql
(SELECT select_expression
 FROM   source_table
 WHERE  condition)
~~~

Minimal example:

~~~sql
SELECT (SELECT 'Oracle' FROM dual) AS product_name
FROM   dual;
~~~

The subquery reads one row from `DUAL` and returns one column containing the string `Oracle`; the outer SQL query receives that value as an expression.

### 2.1. Four cases to distinguish

| Subquery Columns | Subquery Rows | Outcome When Used as Scalar Subquery |
| --- | --- | --- |
| 1 | 1 | Receives the value from the single column |
| 1 | 0 | Receives SQL NULL |
| 1 | 2 or more | Error `ORA-01427` |
| 2 or more | Any | Not a valid scalar subquery; must redesign to return one expression/column |

One-row example:

~~~sql
SELECT (SELECT 10 FROM dual) AS value
FROM dual;
~~~

Zero-row example:

~~~sql
SELECT (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = -999
) AS department_name
FROM dual;
~~~

The result for `DEPARTMENT_NAME` is NULL because the subquery found no rows.

Multi-row example:

~~~sql
SELECT (
    SELECT e.employee_name
    FROM   employees e
    WHERE  e.department_id = 50
) AS employee_name
FROM dual;
~~~

If department 50 has multiple employees, the scalar subquery cannot decide which name to pick and Oracle raises `ORA-01427`.

### 2.2. Scalar subqueries vs subqueries returning a set of rows

A subquery can return multiple rows if the surrounding context accepts a set of values. Example:

~~~sql
SELECT employee_id, employee_name
FROM   employees
WHERE  department_id IN (
    SELECT department_id
    FROM   departments
    WHERE  location_id = 1700
);
~~~

The subquery after `IN` represents a set of values; it is allowed to return multiple rows. Conversely:

~~~sql
SELECT employee_id, employee_name
FROM   employees
WHERE  department_id = (
    SELECT department_id
    FROM   departments
    WHERE  location_id = 1700
);
~~~

The subquery after `=` is used as **a single value**. If location 1700 has multiple departments, the query can raise `ORA-01427`.

## 3. Where Can Scalar Subqueries Appear?

A scalar subquery is valid in most SQL positions that accept an expression (`expr`), subject to Oracle restrictions. Common locations:

### 3.1. In the SELECT list

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM   departments d
        WHERE  d.department_id = e.department_id) AS department_name
FROM   employees e
ORDER BY e.employee_id;
~~~

Each employee row gets a department name value. This is an example of a **correlated scalar subquery**, because the subquery references `e.department_id` from the outer query.

### 3.2. In WHERE to compare against a single value

~~~sql
SELECT employee_id, employee_name, salary
FROM   employees
WHERE  salary > (
    SELECT AVG(salary)
    FROM   employees
);
~~~

`AVG(salary)` is a single company-wide average value. Employees earning more than that figure are selected.

### 3.3. In arithmetic expressions

~~~sql
SELECT e.employee_id,
       e.salary,
       e.salary - (
           SELECT AVG(e2.salary)
           FROM   employees e2
       ) AS difference_from_company_avg
FROM   employees e;
~~~

The scalar subquery returns a NUMBER and is used as an operand in subtraction.

### 3.4. Inside functions or CASE expressions

~~~sql
SELECT e.employee_id,
       NVL(
         (SELECT d.department_name
          FROM   departments d
          WHERE  d.department_id = e.department_id),
         'Unassigned department'
       ) AS department_label
FROM employees e;
~~~

The scalar subquery sits inside `NVL`. If there is no matching department, the subquery returns NULL and `NVL` returns the fallback string.

### 3.5. In ORDER BY

~~~sql
SELECT e.employee_id, e.employee_name
FROM   employees e
ORDER BY (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = e.department_id
), e.employee_id;
~~~

The subquery is used as a sort expression. However, if you also need to sort by department name and display department columns, a JOIN is usually easier to read.

### 3.6. In UPDATE to assign a value

~~~sql
UPDATE employees e
SET    e.salary = (
    SELECT r.new_salary
    FROM   salary_rules r
    WHERE  r.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM   salary_rules r
    WHERE  r.employee_id = e.employee_id
);
~~~

The subquery in `SET` must return a single value for each updated row. `WHERE EXISTS` in this example ensures only employees with a matching rule are updated. Without that condition, a zero-row subquery would return NULL and overwrite `SALARY` with NULL if the column allows NULL.

## 4. Cardinality: The At-Most-One-Row Requirement

**Cardinality** in this context means the number of rows a subquery can return. A scalar subquery requires cardinality no greater than 1.

Not every SQL query that looks like it "finds an employee" guarantees only one row:

~~~sql
SELECT employee_name
FROM   employees
WHERE  department_id = 50;
~~~

The condition `department_id = 50` can find dozens of employees. Placing that query in a scalar context is invalid whenever more than one match exists.

### 4.1. Using a primary key or unique key

A predicate on a full unique key is the most natural way to guarantee at most one row:

~~~sql
SELECT (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = 50
) AS department_name
FROM dual;
~~~

If `DEPARTMENT_ID` is the primary key, the subquery can return at most one row. It can return zero rows if ID 50 does not exist, in which case the value is NULL.

With a rule table:

~~~sql
CREATE TABLE employee_salary_rule_lab (
    employee_id NUMBER PRIMARY KEY,
    new_salary  NUMBER(10,2) NOT NULL
);
~~~

The predicate `r.employee_id = e.employee_id` on the primary key guarantees at most one row in `EMPLOYEE_SALARY_RULE_LAB`.

**Note:** A unique constraint guarantees uniqueness only on the exact declared columns. With a composite unique key, filter on the complete business key. Nullable columns and Oracle's NULL handling must be understood; do not assume a predicate missing part of a key guarantees a single row.

### 4.2. Aggregates without GROUP BY

An aggregate function without `GROUP BY` produces one result row even when the input set has zero rows:

~~~sql
SELECT (
    SELECT MAX(e.salary)
    FROM   employees e
    WHERE  e.department_id = 999
) AS highest_salary
FROM dual;
~~~

When department 999 has no employees, `MAX` returns NULL in a single result row; the scalar subquery still produces one value.

Common aggregates:

| Function | When Input Is Empty, No GROUP BY | Cardinality |
| --- | --- | --- |
| `COUNT(*)` | Returns 0 | One row |
| `COUNT(expr)` | Returns 0 if no non-NULL values exist | One row |
| `MAX(expr)` | Returns NULL | One row |
| `MIN(expr)` | Returns NULL | One row |
| `SUM(expr)` | Returns NULL | One row |
| `AVG(expr)` | Returns NULL | One row |

Example counting employees per department:

~~~sql
SELECT d.department_id,
       d.department_name,
       (SELECT COUNT(*)
        FROM   employees e
        WHERE  e.department_id = d.department_id) AS employee_count
FROM   departments d
ORDER BY d.department_id;
~~~

Even for a department with no employees, the `COUNT(*)` subquery still returns one row with value 0.

### 4.3. Aggregates with GROUP BY do not guarantee one row

~~~sql
SELECT (
    SELECT e.department_id
    FROM   employees e
    GROUP BY e.department_id
) AS department_id
FROM dual;
~~~

`GROUP BY department_id` can produce multiple groups, one row per group. With multiple departments, the scalar subquery still raises `ORA-01427`.

Aggregates guarantee one row only when **there is no GROUP BY** and no other construct increases row count. With `GROUP BY`, check how many groups can be returned.

### 4.4. DISTINCT is not a default cardinality fix

~~~sql
SELECT (
    SELECT DISTINCT e.department_id
    FROM   employees e
) AS department_id
FROM dual;
~~~

If the table has multiple distinct departments, `DISTINCT` still returns multiple rows and the scalar subquery still fails. If all employees happen to belong to one department, the query may pass by coincidence, but that is not guaranteed by data design.

`DISTINCT` is valid only when business logic genuinely calls for a set of **distinct values**. Never use it to mask join bugs or duplicate rows without diagnosing the root cause.

## 5. Zero Rows Return NULL: Implications for SQL Logic

The zero-row rule is crucial:

~~~sql
SELECT (
    SELECT d.department_name
    FROM   departments d
    WHERE  d.department_id = -1
) AS department_name
FROM dual;
~~~

The subquery returns zero rows, so the scalar expression evaluates to NULL. However, that **does not mean the outer SELECT returns zero rows**. The outer query still reads `DUAL` and returns one row where `DEPARTMENT_NAME` is NULL.

### 5.1. Comparing against a scalar subquery that finds no rows

~~~sql
SELECT employee_id, employee_name
FROM   employees e
WHERE  e.department_id = (
    SELECT d.department_id
    FROM   departments d
    WHERE  d.department_name = 'Nonexistent department'
);
~~~

The subquery finds no department and therefore returns NULL. The condition `e.department_id = NULL` is not TRUE; it is UNKNOWN, so `WHERE` selects no rows.

This is an important distinction:

- Subquery finds zero rows → scalar value is NULL.
- Comparison `= NULL` → UNKNOWN.
- `WHERE` selects rows only when the predicate evaluates to TRUE.

### 5.2. IS NULL cannot tell "no row" apart from "row exists with NULL column"

Consider:

~~~sql
SELECT (
    SELECT d.manager_id
    FROM   departments d
    WHERE  d.department_id = 50
) AS manager_id
FROM dual;
~~~

A NULL result can have two causes:

1. Department 50 does not exist.
2. Department 50 exists, but its `MANAGER_ID` is NULL.

Testing the scalar expression with `IS NULL` alone cannot distinguish these two cases.

To distinguish them:

~~~sql
SELECT CASE
         WHEN EXISTS (
           SELECT 1
           FROM   departments d
           WHERE  d.department_id = 50
         )
         THEN 'DEPARTMENT_EXISTS'
         ELSE 'NO_DEPARTMENT'
       END AS department_state
FROM dual;
~~~

Or use LEFT JOIN to keep the parent probe row and inspect the child table's key:

~~~sql
SELECT req.requested_id,
       d.department_id,
       CASE
         WHEN d.department_id IS NULL THEN 'NO_DEPARTMENT'
         WHEN d.manager_id IS NULL THEN 'NO_MANAGER'
         ELSE 'HAS_MANAGER'
       END AS manager_state
FROM   (SELECT 50 AS requested_id FROM dual) req
LEFT JOIN departments d
       ON d.department_id = req.requested_id;
~~~

In this example, `DEPARTMENT_ID` is the primary key, so if `d.department_id` is NULL, no department row matched.

### 5.3. NVL can merge two different states

~~~sql
NVL(
  (SELECT d.manager_id
   FROM departments d
   WHERE d.department_id = 50),
  -1
)
~~~

This expression replaces NULL with -1, but cannot distinguish:

- No department 50.
- Department 50 exists without an assigned manager.

If business logic needs to differentiate them, use `EXISTS`, `CASE`, or LEFT JOIN with a row-identifying column. Use `NVL` only when both states truly share the same handling.

## 6. Correlated Scalar Subqueries

A **correlated subquery** references a column from an outer query block. Its return value therefore depends on each row of the outer query.

Example: showing each department's average salary next to every employee:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       e.salary,
       (SELECT AVG(e2.salary)
        FROM   employees e2
        WHERE  e2.department_id = e.department_id) AS department_avg
FROM   employees e
ORDER BY e.department_id, e.employee_id;
~~~

`e.department_id` belongs to the outer query. `e2.department_id` belongs to the subquery. Using aliases distinguishes columns across query blocks.

### 6.1. Finding employees earning above their department average

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       e.salary
FROM   employees e
WHERE  e.salary > (
    SELECT AVG(e2.salary)
    FROM   employees e2
    WHERE  e2.department_id = e.department_id
)
ORDER BY e.department_id, e.salary DESC;
~~~

The subquery is correlated to the current employee's department. The `AVG` aggregate without `GROUP BY` always returns one row; if no matching employees exist, AVG is NULL.

### 6.2. Correlation does not force the optimizer to do a full scan per row

Conceptually, a correlated subquery is evaluated for each outer row. However, **the Oracle optimizer can rewrite the query into a JOIN or an equivalent technique** when conditions and semantics allow.

Therefore:

- Do not assume every correlated subquery is slow.
- Do not assume the optimizer always rewrites it into a JOIN.
- Inspect the execution plan and actual runtime metrics when tuning.
- Ensure the correlation predicate has a suitable index if workload and selectivity call for it.

For example, `e2.department_id = e.department_id` may be helped by an index on `EMPLOYEES(DEPARTMENT_ID)` in some workloads; yet creating an index solely because you see a correlated subquery is insufficient justification. Evaluate the plan alongside DML and storage overhead.

### 6.3. Correlation and column resolution bugs

When two tables share column names, always qualify with aliases:

~~~sql
SELECT e.employee_id,
       (SELECT COUNT(*)
        FROM   employees e2
        WHERE  e2.manager_id = e.employee_id) AS direct_reports
FROM   employees e;
~~~

Here:

- `e2.manager_id` is the manager of the employee inside the subquery.
- `e.employee_id` is the ID of the current employee in the outer query.

If you omit aliases, Oracle can resolve column names across query-block scopes in ways the author did not intend. Alias qualification prevents mix-ups and protects against future schema changes adding identically named columns.

## 7. Scalar Subquery vs JOIN: Which Should You Choose?

The two queries below express the same department-name lookup if employee → department is many-to-one and `DEPARTMENTS.DEPARTMENT_ID` is unique.

**Scalar subquery approach:**

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id) AS department_name
FROM employees e;
~~~

**LEFT JOIN approach:**

~~~sql
SELECT e.employee_id,
       e.employee_name,
       d.department_name
FROM   employees e
LEFT JOIN departments d
       ON d.department_id = e.department_id;
~~~

### 7.1. Difference when the lookup side has multiple rows

Suppose the lookup table has two rows satisfying the condition:

- Scalar subquery: raises `ORA-01427`.
- JOIN: can duplicate the outer query's row.

These two behaviors differ, yet both expose a cardinality issue. A scalar subquery forces the author to address why a value is no longer unique; a JOIN reflects a one-to-many relationship with multiple output rows.

### 7.2. Difference when zero rows are found

In the SELECT list:

- Scalar subquery finds no row → the expression evaluates to NULL.
- LEFT JOIN finds no row → the right-table columns are NULL.
- INNER JOIN finds no row → the outer-table row is dropped.

Hence, comparing a scalar subquery with an INNER JOIN is usually not equivalent when lookup rows may be missing. LEFT JOIN matches the parent-row-preserving semantics of a scalar subquery in the SELECT list more closely.

### 7.3. When should you choose JOIN?

Prefer JOIN when:

- You need multiple columns from the related table.
- You need to filter, group, or sort by columns from the related table.
- You want to express one-to-one, one-to-many, or many-to-many relationships clearly.
- You want to keep multiple child rows instead of collapsing them into a single value.

A scalar subquery fits well when:

- Only a single value is needed per outer row.
- The lookup condition uses a clear unique key.
- A child aggregate produces one scalar such as COUNT/AVG/MAX.
- The expression is concise and improves query readability.

There is no rule that "scalar subqueries are always slower than JOINs" or "JOINs are always faster." The optimizer can rewrite queries; measure performance on real data and execution plans.

## 8. Scalar Subqueries vs Other Subquery Types

| Type | Question It Answers | Cardinality | Common Syntax |
| --- | --- | --- | --- |
| Scalar subquery | What is a single value? | One column, at most one row | `col = (SELECT ...)` |
| Single-row comparison subquery | What single value satisfies the comparison? | At most one row | `salary > (SELECT AVG(...))` |
| Multi-row subquery with IN | Is the value in the result set? | 0 or more rows | `dept_id IN (SELECT ...)` |
| ANY/SOME | Does at least one set value make the comparison TRUE? | 0 or more rows | `salary > ANY (SELECT ...)` |
| ALL | Do all set values satisfy the comparison? | 0 or more rows | `salary > ALL (SELECT ...)` |
| EXISTS | Does at least one row satisfy the condition? | 0 or more rows | `EXISTS (SELECT 1 ...)` |
| NOT EXISTS | Does no row satisfy the condition? | 0 or more rows | `NOT EXISTS (SELECT 1 ...)` |

### 8.1. = and IN are not freely interchangeable

~~~sql
-- Subquery must return at most one value:
WHERE department_id = (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
)

-- Subquery can return multiple department_ids:
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE location_id = 1700
)
~~~

If location 1700 has multiple departments, the first statement can raise `ORA-01427`, while the second is the proper set-based approach.

### 8.2. ANY and ALL

~~~sql
-- Salary higher than at least one employee in department 50.
SELECT e.employee_id, e.salary
FROM employees e
WHERE e.salary > ANY (
    SELECT e2.salary
    FROM employees e2
    WHERE e2.department_id = 50
);

-- Salary higher than all employees in department 50.
SELECT e.employee_id, e.salary
FROM employees e
WHERE e.salary > ALL (
    SELECT e2.salary
    FROM employees e2
    WHERE e2.department_id = 50
);
~~~

`ANY`/`ALL` accept a set of values. They express comparisons against multiple values without forcing the subquery to be scalar.

### 8.3. EXISTS checks existence, not values

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

`EXISTS` cares only whether a matching row exists. No specific column needs to be selected from the subquery; `SELECT 1` is a common convention. Do not use a scalar subquery when the actual goal is an existence check.

### 8.4. Beware of NOT IN and NULL

~~~sql
SELECT d.department_id
FROM departments d
WHERE d.department_id NOT IN (
    SELECT e.department_id
    FROM employees e
);
~~~

If the subquery returns even one NULL value, `NOT IN` turns the condition into UNKNOWN for non-matching values, yielding unexpected empty results. When the goal is "no employee references this department," usually use:

~~~sql
SELECT d.department_id
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

`NOT EXISTS` directly expresses the absence of matching rows and avoids the NULL trap of `NOT IN`.

## 9. ORA-01427: When a Scalar Subquery Returns More Than One Row

This is the signature error of scalar subqueries:

~~~text
ORA-01427: single-row subquery returns more than one row
~~~

Cause: the outer query expects one value, but the subquery returned multiple rows. Example:

~~~sql
SELECT e.employee_id,
       (SELECT e2.employee_name
        FROM employees e2
        WHERE e2.department_id = e.department_id) AS another_employee
FROM employees e;
~~~

A department has multiple employees, so the subquery can return multiple names.

### 9.1. How to investigate before fixing

Do not immediately slap on `ROWNUM = 1` or `DISTINCT` when encountering the error. First run the subquery on its own with the offending value:

~~~sql
SELECT e2.employee_id, e2.employee_name
FROM   employees e2
WHERE  e2.department_id = 50
ORDER BY e2.employee_id;
~~~

Then ask:

1. According to the data model, is this condition **supposed to be unique**?
2. Is part of a key missing from the JOIN/WHERE predicate?
3. Are the duplicate rows an integrity bug, or are multiple matches legitimately valid?
4. Does the business need an aggregated value, one ordered row, or the full set of rows?

### 9.2. Fix with a unique key if logic expects one specific row

If the subquery should look up an employee's department name, link via `DEPARTMENT_ID`, which is the primary key of `DEPARTMENTS`:

~~~sql
SELECT d.department_name
FROM departments d
WHERE d.department_id = :department_id;
~~~

If the query still returns multiple rows, inspect the schema, synonyms, views, or actual predicates. Do not fix it by truncating results, as that hides data problems.

### 9.3. Fix with an aggregate if business logic needs a summary value

If you need the highest salary in the department:

~~~sql
SELECT e.employee_id,
       (SELECT MAX(e2.salary)
        FROM employees e2
        WHERE e2.department_id = e.department_id) AS max_department_salary
FROM employees e;
~~~

`MAX` returns one value. This is the right fix if the requirement is **the highest salary**. It is not the right fix if the requirement is to pick **one employee** with that salary and retrieve other attributes of that exact employee.

### 9.4. Fix with TOP-1 and ORDER BY when business logic selects one row by rule

On Oracle 12c and higher:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT e2.employee_name
        FROM employees e2
        WHERE e2.department_id = e.department_id
        ORDER BY e2.salary DESC NULLS LAST, e2.employee_id
        FETCH FIRST 1 ROW ONLY) AS highest_paid_colleague
FROM employees e;
~~~

`ORDER BY` defines which employee comes first; `FETCH FIRST 1 ROW ONLY` limits the subquery to at most one row. Putting `EMPLOYEE_ID` last breaks ties deterministically when two employees share the same salary.

**Use this approach only when business logic truly wants the first row under a chosen ordering.** If a table has abnormal duplicates when it should be one-to-one, `FETCH FIRST 1` hides the bug instead of fixing it.

On versions prior to 12c, you can sort inside an inline view and limit with `ROWNUM`:

~~~sql
SELECT e.employee_id,
       (SELECT x.employee_name
        FROM (
            SELECT e2.employee_name
            FROM employees e2
            WHERE e2.department_id = e.department_id
            ORDER BY e2.salary DESC NULLS LAST, e2.employee_id
        ) x
        WHERE ROWNUM = 1) AS highest_paid_colleague
FROM employees e;
~~~

This is a nested query-block pattern: sort in the inline view, limit in the outer query block. Always verify syntax and correlation rules for your exact Oracle version when applying this to complex queries.

### 9.5. Fix with JOIN if multiple rows are actually required

If the question is "list all colleagues in the same department," you do not want a scalar subquery:

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e2.employee_id AS colleague_id,
       e2.employee_name AS colleague_name
FROM   employees e
JOIN   employees e2
       ON e2.department_id = e.department_id
      AND e2.employee_id <> e.employee_id
ORDER BY e.employee_id, e2.employee_id;
~~~

JOIN returns multiple rows matching the many-to-many relationship among employees in the same department.

## 10. Why Shouldn't You Blindly Patch ORA-01427 with ROWNUM or DISTINCT?

### 10.1. ROWNUM = 1 can pick arbitrarily

~~~sql
SELECT (
    SELECT e.employee_name
    FROM employees e
    WHERE e.department_id = 50
      AND ROWNUM = 1
) AS employee_name
FROM dual;
~~~

The query may stop failing, yet without `ORDER BY` there is no contract specifying which employee is picked. The result can change whenever access paths or execution plans change.

If you need the first row by defined criteria:

~~~sql
SELECT (
    SELECT e.employee_name
    FROM employees e
    WHERE e.department_id = 50
    ORDER BY e.salary DESC NULLS LAST, e.employee_id
    FETCH FIRST 1 ROW ONLY
) AS employee_name
FROM dual;
~~~

### 10.2. DISTINCT can hide duplicate signals

~~~sql
SELECT (
    SELECT DISTINCT d.department_name
    FROM departments d
    WHERE d.location_id = 1700
) AS department_name
FROM dual;
~~~

If multiple departments share a location, `DISTINCT` still returns multiple names and keeps failing. If rows happen to share the same name, `DISTINCT` collapses identical values without proving the underlying data has only a single row.

If business logic expects uniqueness, fix the JOIN condition, data model, or constraints. Do not use `DISTINCT` to hide duplicate rows without understanding their source.

## 11. Scalar Subqueries in DML

Scalar subqueries are not limited to SELECT. They can also supply values for certain DML operations.

### 11.1. UPDATE with a lookup value

~~~sql
UPDATE employees e
SET    e.salary = (
    SELECT r.new_salary
    FROM   employee_salary_rule_lab r
    WHERE  r.employee_id = e.employee_id
)
WHERE EXISTS (
    SELECT 1
    FROM   employee_salary_rule_lab r
    WHERE  r.employee_id = e.employee_id
);
~~~

`EMPLOYEE_ID` is the primary key of the rule table, so the subquery returns at most one row. `EXISTS` prevents updating employees who have no rule. Without `WHERE EXISTS`, a scalar subquery returning zero rows can assign NULL to the target column.

### 11.2. UPDATE with an aggregate

~~~sql
UPDATE departments d
SET    d.department_name =
       d.department_name || ' (' ||
       (SELECT COUNT(*)
        FROM employees e
        WHERE e.department_id = d.department_id) ||
       ')';
~~~

This illustrates a scalar aggregate inside an update expression. Note that this is a real UPDATE: running it repeatedly keeps appending counts to the name string. Run only in a lab or within a controlled transaction.

### 11.3. INSERT a single value from a subquery

~~~sql
INSERT INTO audit_note_lab (note_id, note_text)
VALUES (
    1,
    (SELECT 'Created by Oracle SQL' FROM dual)
);
~~~

The subquery returns one column and one row, so it can supply a value for a column in `VALUES`.

### 11.4. Do not confuse scalar subquery expressions with INSERT ... SELECT

~~~sql
INSERT INTO employee_archive (employee_id, employee_name)
SELECT employee_id, employee_name
FROM   employees
WHERE  department_id = 50;
~~~

This is a **subquery serving as the source for INSERT**, which can return many rows. It is not a scalar subquery expression. Similarly, a subquery in FROM is an inline view, used as a table source.

## 12. Scalar Subqueries vs SELECT INTO in PL/SQL

A scalar subquery is a SQL expression. In PL/SQL, `SELECT ... INTO` is a different mechanism for putting a query result into variables:

~~~sql
DECLARE
  l_department_name departments.department_name%TYPE;
BEGIN
  SELECT d.department_name
  INTO   l_department_name
  FROM   departments d
  WHERE  d.department_id = 50;

  DBMS_OUTPUT.PUT_LINE(l_department_name);
END;
/
~~~

`SELECT INTO` has different semantics:

- Zero rows: `NO_DATA_FOUND`.
- More than one row: `TOO_MANY_ROWS`.
- Exactly one row: assigns values to variables.

Whereas a scalar subquery:

- Zero rows: the expression evaluates to NULL.
- More than one row: `ORA-01427`.
- One row: the expression evaluates to the value.

| Situation | Scalar Subquery Expression | PL/SQL SELECT INTO |
| --- | --- | --- |
| 0 rows | NULL | `NO_DATA_FOUND` |
| 1 row | Scalar value | Assigns variable |
| Multiple rows | `ORA-01427` | `TOO_MANY_ROWS` |
| Context | Inside a SQL expression | PL/SQL statement |

If code needs to catch the missing-row case explicitly via exceptions, `SELECT INTO` can fit well. If you need the value directly inside a larger SQL query, a scalar subquery is the natural SQL representation.

## 13. Where Scalar Subqueries Are Invalid in Oracle

Oracle allows scalar subqueries in most expression positions, with exceptions documented in the SQL Language Reference. In Oracle 19c, a scalar subquery is invalid:

- As a column `DEFAULT` value.
- As a hash expression for a cluster.
- In the `RETURNING` clause of DML.
- As the basis of a function-based index.
- Inside a `CHECK` constraint.
- Inside `GROUP BY`.
- In non-query statements, such as `CREATE PROFILE`.

Conceptually invalid example:

~~~sql
CREATE TABLE order_limit_demo (
    quantity NUMBER,
    CONSTRAINT order_limit_ck
      CHECK (quantity <= (SELECT max_quantity FROM product_rules))
);
~~~

A CHECK constraint cannot contain a scalar subquery referencing another table. If `quantity` must enforce a product limit, consider appropriate data modeling, foreign keys, transactions, or application/procedure logic.

Additional restrictions apply per expression/query-block type; consult the syntax of the specific statement rather than generalizing solely from scalar subquery rules.

## 14. Performance and Execution Plans

Scalar subqueries can be very readable, yet a query containing multiple correlated scalar subqueries should be evaluated on realistic data.

### 14.1. Cost depends on row count and optimizer handling

Example:

~~~sql
SELECT e.employee_id,
       (SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id) AS department_name,
       (SELECT COUNT(*)
        FROM employees e2
        WHERE e2.manager_id = e.employee_id) AS direct_reports
FROM employees e;
~~~

There are two correlated scalar subqueries. Logically, each subquery depends on the outer employee row. The optimizer may transform the query or choose an appropriate execution strategy; do not assume statically that each subquery will run a full table scan for every row.

### 14.2. Viewing the execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT e.employee_id,
       (SELECT d.department_name
        FROM departments d
        WHERE d.department_id = e.department_id) AS department_name
FROM employees e;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows an estimated plan, not necessarily the actual plan with bind values and runtime statistics. Where permitted, use `DBMS_XPLAN.DISPLAY_CURSOR` with runtime statistics to inspect executed cursors. Do not grant administrative privileges just to run this example; ask a DBA if plan access is needed.

### 14.3. What to inspect

- Are there repeated full scans on the child table?
- Does the correlation predicate have an appropriate index?
- Do estimated rows diverge heavily from actual rows?
- Did the optimizer unnest/rewrite it into a JOIN?
- Does the scalar aggregate read large volumes of data per parent row?
- Can the aggregate be computed once per group and then JOINed?

### 14.4. Rewriting with an aggregate inline view when appropriate

Correlated scalar aggregate:

~~~sql
SELECT e.employee_id,
       (SELECT AVG(e2.salary)
        FROM employees e2
        WHERE e2.department_id = e.department_id) AS dept_avg
FROM employees e;
~~~

Inline view formulation:

~~~sql
SELECT e.employee_id,
       a.dept_avg
FROM   employees e
LEFT JOIN (
    SELECT department_id,
           AVG(salary) AS dept_avg
    FROM   employees
    GROUP BY department_id
) a
       ON a.department_id = e.department_id;
~~~

Logically, the inline view aggregates each department once and then JOINs the result to employees. Both forms can be equivalent in this case; the optimizer may also perform rewrites itself. Compare plans and results, while preserving semantics when `department_id` is NULL.

## 15. NULLs, Aggregates, and Comparisons in Scalar Context

### 15.1. COUNT and MAX return different values on zero rows

~~~sql
SELECT
  (SELECT COUNT(*)
   FROM employees
   WHERE department_id = -999) AS employee_count,
  (SELECT MAX(salary)
   FROM employees
   WHERE department_id = -999) AS max_salary
FROM dual;
~~~

Result:

| EMPLOYEE_COUNT | MAX_SALARY |
| ---: | --- |
| 0 | NULL |

Both subqueries return one row because they are aggregates without GROUP BY. `COUNT(*)` returns 0; `MAX` returns NULL.

### 15.2. Scalar NULL in arithmetic

~~~sql
SELECT 100 + (
    SELECT MAX(salary)
    FROM employees
    WHERE department_id = -999
) AS calculated_value
FROM dual;
~~~

Because the subquery returns NULL, `100 + NULL` evaluates to NULL. If business logic treats a missing value as 0, you can use `NVL`:

~~~sql
SELECT 100 + NVL((
    SELECT MAX(salary)
    FROM employees
    WHERE department_id = -999
), 0) AS calculated_value
FROM dual;
~~~

Substitute NULL with 0 only when business rules explicitly define that equivalence. "No record" can mean something different from "value of 0."

### 15.3. A scalar subquery returning NULL is not an error

A zero-row scalar subquery is a valid result and does not raise `NO_DATA_FOUND`. If logic must treat missing rows as an error, check with `EXISTS`/`NOT EXISTS` or use `SELECT INTO` in PL/SQL and handle the exception appropriately.

## 16. Self-Contained Lab Dataset

This section creates two simple tables to run the examples without needing the HR schema. Run only in a lab schema. If the names already exist, pick other names or clean up objects you created.

### 16.1. Create the departments and employees tables

~~~sql
CREATE TABLE sq_dept_lab (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(50 CHAR) NOT NULL
);

CREATE TABLE sq_employee_lab (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    department_id NUMBER,
    salary        NUMBER(10,2)
);
~~~

### 16.2. Load data

~~~sql
INSERT INTO sq_dept_lab VALUES (10, 'Finance');
INSERT INTO sq_dept_lab VALUES (20, 'Engineering');
INSERT INTO sq_dept_lab VALUES (30, 'Operations');

INSERT INTO sq_employee_lab VALUES (101, 'An',   10, 1200);
INSERT INTO sq_employee_lab VALUES (102, 'Binh', 10, 1800);
INSERT INTO sq_employee_lab VALUES (103, 'Chi',  20, 3500);
INSERT INTO sq_employee_lab VALUES (104, 'Dung', 20, 4200);
INSERT INTO sq_employee_lab VALUES (105, 'Em',   20, 4200);
INSERT INTO sq_employee_lab VALUES (106, 'Giang', 30, 2200);
INSERT INTO sq_employee_lab VALUES (107, 'Ha',   30, 2500);
INSERT INTO sq_employee_lab VALUES (108, 'Khanh', 99, 1600);
INSERT INTO sq_employee_lab VALUES (109, 'Linh', NULL, 1400);

COMMIT;
~~~

The lab intentionally omits a foreign key on `SQ_EMPLOYEE_LAB.DEPARTMENT_ID` so you can observe:

- Departments 10, 20, 30 have employees.
- Employee 108 references nonexistent department 99.
- Employee 109 has NULL department.
- Department 20 has three employees, two sharing a salary of 4200.

## 17. Practicing Scalar Subqueries Case by Case

### Exercise A — Looking up department name

~~~sql
SELECT e.employee_id,
       e.employee_name,
       (SELECT d.department_name
        FROM sq_dept_lab d
        WHERE d.department_id = e.department_id) AS department_name
FROM sq_employee_lab e
ORDER BY e.employee_id;
~~~

Observations:

- Employees 101–107 receive their department names.
- Employee 108 receives NULL because department 99 does not exist.
- Employee 109 receives NULL because `department_id` is NULL.

The last two rows both get a scalar NULL, though for different reasons.

### Exercise B — Counting employees per department

~~~sql
SELECT d.department_id,
       d.department_name,
       (SELECT COUNT(*)
        FROM sq_employee_lab e
        WHERE e.department_id = d.department_id) AS employee_count
FROM sq_dept_lab d
ORDER BY d.department_id;
~~~

Result:

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_COUNT |
| ---: | --- | ---: |
| 10 | Finance | 2 |
| 20 | Engineering | 3 |
| 30 | Operations | 2 |

Try adding a department with no employees to observe `COUNT(*) = 0`.

### Exercise C — Salary above department average

~~~sql
SELECT e.employee_id,
       e.employee_name,
       e.department_id,
       e.salary,
       (SELECT AVG(e2.salary)
        FROM sq_employee_lab e2
        WHERE e2.department_id = e.department_id) AS dept_avg
FROM sq_employee_lab e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM sq_employee_lab e2
    WHERE e2.department_id = e.department_id
)
ORDER BY e.department_id, e.salary DESC, e.employee_id;
~~~

The subquery in the SELECT list displays the average; the subquery in WHERE filters employees. Both subqueries share the same business meaning but appear in two places. You can rewrite this with an aggregated inline view so it is defined only once.

### Exercise D — Intentionally triggering ORA-01427

~~~sql
SELECT (
    SELECT e.employee_name
    FROM sq_employee_lab e
    WHERE e.department_id = 20
) AS one_employee
FROM dual;
~~~

Department 20 has three employees, so the subquery returns three rows. Scalar context requires at most one row, and Oracle raises `ORA-01427`.

Run the subquery on its own:

~~~sql
SELECT employee_id, employee_name, salary
FROM sq_employee_lab
WHERE department_id = 20
ORDER BY employee_id;
~~~

### Exercise E — Picking one employee by an explicit rule

~~~sql
SELECT (
    SELECT e.employee_name
    FROM sq_employee_lab e
    WHERE e.department_id = 20
    ORDER BY e.salary DESC NULLS LAST, e.employee_id
    FETCH FIRST 1 ROW ONLY
) AS highest_paid_employee
FROM dual;
~~~

Two employees earn 4200; the smaller `employee_id` wins due to the tie-breaker. Change `ORDER BY` or drop the tie-breaker to see why a clear deterministic single-row rule is essential.

### Exercise F — Comparing scalar subquery with LEFT JOIN

~~~sql
-- Scalar subquery:
SELECT e.employee_id,
       (SELECT d.department_name
        FROM sq_dept_lab d
        WHERE d.department_id = e.department_id) AS department_name
FROM sq_employee_lab e
ORDER BY e.employee_id;

-- LEFT JOIN:
SELECT e.employee_id,
       d.department_name
FROM sq_employee_lab e
LEFT JOIN sq_dept_lab d
       ON d.department_id = e.department_id
ORDER BY e.employee_id;
~~~

Both preserve employees without a matching department. If you try inserting a duplicate department ID into the lookup table, the PK blocks it; if the table lacks a unique key, the scalar subquery errors while JOIN duplicates rows.

### Exercise G — Lab cleanup (optional)

~~~sql
-- Drop only the tables you created in your lab schema.
DROP TABLE sq_employee_lab PURGE;
DROP TABLE sq_dept_lab PURGE;
~~~

DDL performs an implicit commit, and DROP cannot be undone with `ROLLBACK`. Skip this step if you want to keep the tables for practice.

## 18. Common Errors and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `ORA-01427` | Scalar subquery returned more than one row | Check data and predicates; use a unique key, aggregate, ordered TOP-1, or JOIN per business rules |
| Subquery returns NULL despite expecting data | No row satisfies predicate; NULL outer reference; wrong alias/type comparison | Run the subquery standalone with concrete values; verify aliases and data |
| `IS NULL` fails to separate missing row from NULL column | Both cases produce scalar NULL | Use EXISTS or LEFT JOIN with key check to distinguish |
| UPDATE overwrites a column with NULL | Scalar subquery found zero rows for a target row | Use WHERE EXISTS, business-defined NVL, or explicit missing-row handling |
| Scalar subquery breaks after new data is added | Cardinality happened to be 1 before, now duplicates exist | Verify unique keys and predicates; do not hide with ROWNUM |
| TOP-1 result fluctuates | Missing ORDER BY or missing tie-breaker | Define deterministic ordering with a tie-breaking key |
| Slow query | Correlated subquery has suboptimal access path or expensive aggregate | Inspect execution plan, indexes, cardinality; compare with JOIN/aggregate inline view |
| Referenced column resolves unexpectedly | Column name collision between inner and outer queries | Qualify every column with an alias |
| `NOT IN` returns zero rows unexpectedly | Subquery set contains NULL | Consider NOT EXISTS and explicit correlation predicates |

## 19. Mental Checklist Before Writing a Scalar Subquery

1. **Do I need a single value or a set of rows?** If a set of rows, use IN/EXISTS/JOIN/inline view as appropriate.
2. **Does the subquery select exactly one column?** A scalar expression accepts only one value.
3. **Do the conditions guarantee at most one row?** Prefer PK/UNIQUE or an appropriate aggregate.
4. **If zero rows match, is NULL acceptable for the business logic?** If not, handle it explicitly.
5. **If multiple rows exist, what is correct?** A cardinality error may signal bad data, call for an aggregate/top-one, or actually require a JOIN.
6. **If picking one row, is the ordering deterministic?** Use ORDER BY and a tie-breaker.
7. **Is the subquery correlated?** Qualify aliases and check the execution plan.
8. **Would a JOIN or aggregate inline view be clearer?** Pick the construct that is readable and semantically right.
9. **Can DML assign NULL when the subquery returns zero rows?** Check UPDATE SET and WHERE scope.
10. **Does logic depend on NULL semantics?** Handle type conversions and NULLs explicitly.

## 20. Self-Check Questions

**Question 1.** How many columns and at most how many rows must a scalar subquery return?

**Question 2.** If a scalar subquery returns zero rows, does Oracle raise `NO_DATA_FOUND` or return a value?

**Question 3.** If a scalar subquery returns three rows, what Oracle error typically occurs?

**Question 4.** Why can `SELECT MAX(salary) FROM employees WHERE department_id = -1` still be used as a scalar subquery even with zero matching employees?

**Question 5.** Does an aggregate with `GROUP BY department_id` guarantee one row?

**Question 6.** When should you use `IN` instead of `=` with a subquery?

**Question 7.** Why can `IS NULL` on a scalar subquery not distinguish "no row" from "column has NULL value"?

**Question 8.** Does a correlated subquery force Oracle to run a full scan of the child table for every outer row?

**Question 9.** Why can adding `ROWNUM = 1` to a scalar subquery mask a data issue?

**Question 10.** If you need the name of the highest-paid employee in a department and salaries can tie, what must be added to pick one person deterministically?

**Question 11.** Compare a scalar subquery finding zero rows with a LEFT JOIN finding zero rows.

**Question 12.** In an UPDATE, what can happen if a scalar subquery in SET returns zero rows?

<details>
<summary>Answer Hints</summary>

1. One column, at most one row.
2. The scalar value is SQL NULL; it does not raise `NO_DATA_FOUND` like SELECT INTO.
3. `ORA-01427: single-row subquery returns more than one row`.
4. An aggregate without GROUP BY returns exactly one row; `MAX` is NULL when the input set is empty.
5. No. Each group produces a row, and there can be multiple groups.
6. When the subquery can return multiple values and you need to check set membership.
7. Both situations yield scalar NULL; use EXISTS or LEFT JOIN with a key check to distinguish.
8. No. The subquery is logically correlated per row, yet the optimizer can rewrite it into a JOIN or equivalent plan.
9. Without ORDER BY, it picks an arbitrary row depending on the access path, hiding the fact that the predicate matched multiple rows.
10. ORDER BY salary descending plus a unique key as tie-breaker; `FETCH FIRST 1 ROW ONLY` on 12c+.
11. A scalar subquery yields NULL in the expression; LEFT JOIN keeps the outer row with NULL inner columns; INNER JOIN drops the outer row.
12. The target column can be set to NULL; use EXISTS or explicit missing-data handling if needed.

</details>

## 21. Official Oracle Documentation

1. [Oracle Database 19c SQL Language Reference — Scalar Subquery Expressions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Scalar-Subquery-Expressions.html): definition of scalar subqueries, zero-row/one-row/multi-row rules, and disallowed locations.
2. [Oracle Database 19c SQL Language Reference — Using Subqueries](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Using-Subqueries.html): correlated subqueries, inline views, aliasing, and subquery usage.
3. [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): SELECT expressions, subqueries, JOINs, and the row limiting clause.
4. [Oracle Database 19c Database Error Messages — ORA-01427](https://docs.oracle.com/en/error-help/db/ora-01427/): causes and resolutions when a single-row subquery returns multiple rows.
5. [Oracle Database 19c SQL Language Reference — UPDATE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/UPDATE.html): subqueries in UPDATE SET and behavior when zero rows are returned.
6. [Oracle Database 19c SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): existence testing conditions.
7. [Oracle Database 19c SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): set membership conditions.
8. [Oracle Database 19c SQL Language Reference — Comparison Conditions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Comparison-Conditions.html): comparisons with ANY/ALL and result sets.
9. [Oracle Database 19c SQL Language Reference — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): limiting rows per query block; requires pairing properly with ORDER BY for TOP-1 selection.
10. [Oracle Database 19c SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/): execution plans, optimizer transformations, and performance evaluation.

**Principle to remember:** A scalar subquery is a **single-value expression**, so it must select **one column and at most one row**. Unique keys and aggregates without GROUP BY naturally guarantee cardinality. When zero rows match, the value is NULL; when multiple rows match, Oracle raises `ORA-01427`. If you must pick one row by order, specify an explicit ORDER BY and tie-breaker; if multiple rows are actually needed, use a JOIN or set condition rather than forcing the query into a scalar expression.
