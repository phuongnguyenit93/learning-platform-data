# Single-Row, Multi-Row, and Correlated Subqueries

In Oracle Database, a **subquery** is a query nested inside another SQL statement. A subquery can supply a single value for comparison, a list of values, check for the existence of rows, or produce an intermediate dataset for the outer query. Depending on the goal and how many rows the outer context allows, we commonly distinguish **single-row subqueries**, **multi-row subqueries**, and **correlated subqueries**.

These three concepts do not lie on a single classification axis:

- **Single-row subquery** describes a subquery used as a single value: it must return at most one row and one column in a scalar context.
- **Multi-row subquery** describes a subquery that can return multiple rows, typically used with IN, ANY, ALL, or EXISTS.
- **Correlated subquery** describes a subquery referencing columns from an outer query block. It can be scalar or multi-row; correlation is a scoping relationship, not a guarantee that Oracle will execute the subquery once per outer row.

Understanding the differences helps you choose the right operator, avoid ORA-01427 errors, handle NULLs accurately, and read execution plans better. This lesson also covers using subqueries in SELECT, WHERE, HAVING, FROM, and DML, along with runnable SQL examples for a practice schema.

## 1. Subqueries and Query Blocks

A subquery is a SELECT statement nested inside another SQL statement. The outer query block uses the subquery's result in one of several ways.

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

In this example:
- The inner SELECT is the **subquery**.
- The outer SELECT is the **outer query**.
- The subquery computes the average salary.
- The outer query compares each employee's salary against that average.

Subqueries do not always live in WHERE. They can appear in many places:

| Position | Role | Example |
| --- | --- | --- |
| WHERE | Compare a single value or check a row set | `salary > (SELECT AVG(...))` |
| HAVING | Compare group aggregates against another query result | `AVG(salary) > (SELECT AVG(...))` |
| SELECT list | Compute one value per outer row | `(SELECT COUNT(*) ...) AS employee_count` |
| FROM | Create an intermediate dataset, also called an inline view | `FROM (SELECT ...) d` |
| DML | Compute UPDATE values or filter rows for DELETE/UPDATE | `SET col = (SELECT ...)` |

### 1.1. Distinguishing column count from row count

When using a subquery as a scalar value, Oracle requires one column and at most one row. When used with IN, ANY, or ALL, a subquery normally provides one column but can return multiple rows. EXISTS only checks whether any row exists and therefore does not read specific values from the select list.

Two questions must be kept separate:

1. **How many columns does the subquery return?** A scalar expression holds only one value; IN/ANY/ALL in basic form likewise compare one expression against one column from the subquery.
2. **How many rows does the subquery return?** A scalar subquery accepts 0 or 1 row; multi-row operators allow multiple rows.

A subquery can return one column and many rows; that is the classic IN case. An inline view in FROM can return multiple columns and multiple rows because it serves as a table source.

## 2. Single-Row Subquery: A Subquery Returning One Value

A single-row subquery, in a scalar comparison context, returns **one column and no more than one row**. Its result can be compared using standard operators:

- = 
- <> or !=
- >
- >=
- <
- <=

Example:

~~~sql
SELECT employee_id,
       full_name,
       salary
FROM employees
WHERE salary > (
    SELECT AVG(salary)
    FROM employees
);
~~~

The subquery returns one average value; each outer row is compared against that single value.

### 2.1. Comparing against a single value

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary = (
    SELECT MAX(salary)
    FROM employees
);
~~~

The MAX subquery returns one row and one column because there is no GROUP BY. The outer query retrieves all employees whose salary equals that maximum. If multiple employees tie for the highest salary, the subquery still returns **one value**, while the outer query can return multiple rows.

This is a crucial point: **single-row describes the row count of the subquery, not the row count of the outer SELECT.**

### 2.2. Subquery returning 0 rows

A scalar subquery that finds no rows evaluates to **NULL**:

~~~sql
SELECT (
    SELECT department_name
    FROM departments
    WHERE department_id = 999
) AS department_name
FROM dual;
~~~

If department 999 does not exist, the scalar result is NULL. The outer query can still return one row from DUAL.

In a comparison expression:

~~~sql
SELECT employee_id, full_name
FROM employees
WHERE salary = (
    SELECT salary
    FROM employees
    WHERE employee_id = 999
);
~~~

if employee 999 does not exist, the scalar subquery is NULL; the comparison `SALARY = NULL` is UNKNOWN, so no rows are selected.

Do not confuse this case with a subquery returning multiple rows. **Zero rows** yields NULL in scalar context; **more than one row** raises an error.

### 2.3. Subquery returning more than one row: ORA-01427

~~~sql
-- Intentionally demonstrates an error if department 20 has multiple employees.
SELECT employee_id, full_name
FROM employees
WHERE salary = (
    SELECT salary
    FROM employees
    WHERE department_id = 20
);
~~~

If department 20 has two employees, the subquery returns two salaries. Oracle cannot use two values as a single scalar for `=`, and raises:

~~~text
ORA-01427: single-row subquery returns more than one row
~~~

How to fix it depends on your intent:

- If you want to match any value in the list, use IN.
- If you want to compare against the maximum/minimum/average value, use the appropriate aggregate function.
- If you genuinely need just one row, define a deterministic order and limit rows with a row-limiting clause.
- If the subquery was supposed to be unique, check keys/constraints and WHERE predicates.

Example using IN:

~~~sql
SELECT employee_id, full_name, salary
FROM employees
WHERE salary IN (
    SELECT salary
    FROM employees
    WHERE department_id = 20
);
~~~

### 2.4. Using aggregates to guarantee a single value

Aggregates without GROUP BY such as COUNT, MAX, MIN, AVG, and SUM return one result row even when the input set is empty:

~~~sql
SELECT COUNT(*) AS employee_count,
       MAX(salary) AS max_salary,
       AVG(salary) AS avg_salary
FROM employees
WHERE department_id = 999;
~~~

Result:
- COUNT(*) returns 0.
- MAX, MIN, AVG, and SUM return NULL if there are no qualifying values to aggregate.

Aggregates with GROUP BY can return multiple rows:

~~~sql
SELECT AVG(salary)
FROM employees
GROUP BY department_id;
~~~

With multiple departments, this subquery can return multiple values. Do not see AVG/MAX/COUNT and blindly assume the subquery is always scalar; inspect GROUP BY and how many groups can be formed.

### 2.5. Scalar subquery in the SELECT list

A scalar subquery can compute one column value for each outer row:

~~~sql
SELECT d.department_id,
       d.department_name,
       (
           SELECT COUNT(*)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS employee_count
FROM departments d
ORDER BY d.department_id;
~~~

The subquery here references `d.department_id`, making it simultaneously a **correlated subquery**. `COUNT(*)` guarantees one row; departments without employees receive 0.

If a scalar subquery returns 0 rows, the output column is NULL. If it returns more than one row, Oracle raises ORA-01427.

## 3. Multi-Row Subqueries: Working with a Set of Values

A multi-row subquery can return multiple rows. Therefore, the outer operator must explicitly specify how to compare against **a set of results**, rather than treating the set as a single value.

Common operators:

| Operator | Meaning |
| --- | --- |
| IN | Outer value matches at least one value in the set |
| NOT IN | Outer value matches no value in the set, with NULL caveats |
| ANY / SOME | Comparison is true for at least one row in the set |
| ALL | Comparison is true for every row in the set |
| EXISTS | Subquery has at least one row |
| NOT EXISTS | Subquery has zero rows |

### 3.1. IN: matching one of several values

~~~sql
SELECT employee_id, full_name, department_id
FROM employees
WHERE department_id IN (
    SELECT department_id
    FROM departments
    WHERE department_name IN ('Sales', 'Engineering')
);
~~~

The subquery can return multiple `department_id` values. The outer query retrieves employees belonging to any of those departments.

IN is suitable for expressing set membership. You can use a literal list:

~~~sql
WHERE department_id IN (10, 20, 30)
~~~

or a subquery.

When a subquery returns an empty set, the IN condition is never true for any row; there are no values to match.

### 3.2. NOT IN and the NULL trap

~~~sql
SELECT department_id, department_name
FROM departments
WHERE department_id NOT IN (
    SELECT department_id
    FROM employees
);
~~~

At first glance, this appears to find departments without employees. Yet if the subquery returns even one NULL, `NOT IN` can evaluate to UNKNOWN for non-matching values. In practice, whenever the list contains NULL and no value matches, the condition never evaluates to TRUE, so the query may return zero rows unexpectedly.

Reason: NOT IN is semantically equivalent to being unequal to every value in the set. For example:

~~~sql
department_id NOT IN (10, 20, NULL)
~~~

is interpreted roughly as:

~~~sql
department_id <> 10
AND department_id <> 20
AND department_id <> NULL
~~~

The `department_id <> NULL` part is UNKNOWN. `TRUE AND UNKNOWN` is UNKNOWN, so WHERE drops the row.

If you still want NOT IN, filter out NULLs in the subquery when appropriate:

~~~sql
SELECT department_id, department_name
FROM departments
WHERE department_id NOT IN (
    SELECT department_id
    FROM employees
    WHERE department_id IS NOT NULL
);
~~~

In many anti-match problems, NOT EXISTS is clearer and avoids the inner-set NULL trap:

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Do not claim NOT EXISTS and NOT IN are always equivalent in every scenario. If the outer value can be NULL or business logic has special NULL-matching rules, write explicit conditions.

### 3.3. ANY and SOME: true for at least one value

ANY (with synonym SOME) combines with a comparison operator:

~~~sql
salary > ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

Meaning: the outer employee's salary is greater than **at least one** salary in department 10.

Examples:

~~~sql
-- Greater than at least one salary in department 10.
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 10
);

-- Equal to at least one value: similar to IN for scalars.
SELECT employee_id, full_name
FROM employees
WHERE department_id = ANY (
    SELECT department_id
    FROM departments
    WHERE department_id IN (10, 20)
);
~~~

Helpful rules:
- `> ANY`: greater than the minimum, in the sense that at least one comparison is true.
- `< ANY`: less than at least one value, equivalent to less than the maximum when the set is non-empty and unaffected by NULL.
- `= ANY`: equivalent to IN.
- `<> ANY`: not equal to at least one value; NOT synonymous with NOT IN.

ANY returns FALSE when the subquery is empty. If no comparison is TRUE and at least one is UNKNOWN due to NULL, the result can be UNKNOWN.

### 3.4. ALL: true for every value

~~~sql
salary > ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 10
)
~~~

Meaning: the outer salary must be greater than **all** salaries in department 10.

Examples:

~~~sql
-- Salary higher than every employee in department 10.
SELECT employee_id, full_name, salary
FROM employees
WHERE salary > ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 10
);

-- Salary not higher than any salary in department 10.
SELECT employee_id, full_name, salary
FROM employees
WHERE salary <= ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 10
);
~~~

Helpful rules:
- `> ALL`: greater than the maximum when the set is non-empty and unaffected by NULL.
- `< ALL`: less than the minimum.
- `= ALL`: true only if equal to every value; usually false when the set has multiple distinct values.
- `<> ALL`: equivalent to NOT IN, including the same NULL pitfalls.

ALL returns TRUE on an empty set by universal quantification: no element violates "true for all elements." This sometimes surprises authors, so verify inner subquery filters to ensure the set contains the intended business rows.

### 3.5. ANY and ALL with NULLs

NULL can turn comparisons into UNKNOWN. Example:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE salary > ANY (
    SELECT salary
    FROM employees
    WHERE department_id = 30
);
~~~

If department 30's set contains a NULL salary:
- As soon as one comparison is TRUE, ANY evaluates to TRUE.
- If no comparison is TRUE and at least one is UNKNOWN, the result can be UNKNOWN.
- If all comparisons are FALSE, the result is FALSE.

For ALL:
- As soon as one comparison is FALSE, ALL evaluates to FALSE.
- If all comparisons are TRUE, the result is TRUE.
- If none are FALSE and at least one is UNKNOWN, the result is UNKNOWN.

When business logic compares only non-missing values, filter NULLs inside the subquery:

~~~sql
WHERE salary > ALL (
    SELECT salary
    FROM employees
    WHERE department_id = 30
      AND salary IS NOT NULL
)
~~~

Add `IS NOT NULL` only when business rules mean ignoring unknown salaries. Do not filter NULLs mechanically if the presence of NULL should render the result undetermined.

## 4. EXISTS and NOT EXISTS

EXISTS tests whether a subquery returns **at least one row**. It does not care about specific values in the select list.

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

The result is departments that have at least one employee.

Usually `SELECT 1` is written inside EXISTS to emphasize that only row existence matters. `SELECT *` also expresses existence; Oracle does not need to fetch all columns to decide whether EXISTS is TRUE.

### 4.1. EXISTS is not IN

Two ways to express similar problems:

~~~sql
-- Using IN.
SELECT d.department_id, d.department_name
FROM departments d
WHERE d.department_id IN (
    SELECT e.department_id
    FROM employees e
);

-- Using EXISTS.
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

However, EXISTS directly expresses the relationship between an outer row and the existence of a child row, whereas IN expresses membership in a set of values. Because of NULLs, duplicates, and data structures, do not swap them blindly without checking semantics.

### 4.2. NOT EXISTS: finding rows without a partner

~~~sql
SELECT d.department_id,
       d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

This finds departments without employees. It is the standard anti-existence pattern, generally safer than NOT IN when the inner column may contain NULLs.

### 4.3. EXISTS answers existence questions without counting

If you only need to know whether a department has employees, you do not need:

~~~sql
WHERE (
    SELECT COUNT(*)
    FROM employees e
    WHERE e.department_id = d.department_id
) > 0
~~~

You can write more clearly:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
)
~~~

`COUNT(*)` represents a quantity; `EXISTS` only needs to know whether a row exists. The optimizer may transform both queries differently, yet EXISTS states the exact intent without asking for an unneeded count.

### 4.4. NOT EXISTS and NULL in the outer row

~~~sql
SELECT e.employee_id, e.full_name
FROM employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM departments d
    WHERE d.department_id = e.department_id
);
~~~

If `EMPLOYEE.DEPARTMENT_ID` is NULL, `d.department_id = e.department_id` is never TRUE for any row, so NOT EXISTS evaluates to TRUE and that employee is returned.

That may be right if the goal is "no matching department found." However, if the business goal is only to find employees with a non-NULL department code pointing to a missing department, add:

~~~sql
WHERE e.department_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM departments d
      WHERE d.department_id = e.department_id
  )
~~~

When an ENABLE VALIDATE foreign key exists, invalid non-NULL references normally cannot exist, yet NULL is still permitted unless the column is NOT NULL.

## 5. Correlated Subqueries: Referencing an Outer Query Block

A correlated subquery uses columns from an outer query block. The outer alias establishes the scope referenced by the subquery.

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.salary
FROM employees e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees e2
    WHERE e2.department_id = e.department_id
);
~~~

The subquery references `e.department_id` from the outer row. For each employee, the comparison logically uses their own department's average salary.

### 5.1. Correlated does not always mean physical row-by-row execution

**Semantically**, the subquery's result depends on the outer row's values. You can reason mentally as if the subquery runs for each outer row to understand the logic.

Yet do not assume Oracle is forced to physically re-run the subquery once per row. The optimizer can transform a correlated subquery into:
- A semi-join or anti-join.
- A join against an aggregated inline view.
- Another suitable access path.
- An appropriate execution or caching mechanism for scalar subqueries.

Thus, correlation is a **data-scoping property**, not a literal description of physical access frequency. To see how Oracle actually executes it, check the execution plan and runtime statistics.

### 5.2. Correlated scalar subquery in SELECT

~~~sql
SELECT d.department_id,
       d.department_name,
       (
           SELECT COUNT(*)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS employee_count
FROM departments d
ORDER BY d.department_id;
~~~

Each department row gets its corresponding count. Departments with no employees return 0 because `COUNT(*)` over an empty set returns 0.

If you replace COUNT with MAX:

~~~sql
SELECT d.department_id,
       (
           SELECT MAX(e.salary)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS max_salary
FROM departments d;
~~~

a department with no employees returns NULL, because MAX over an empty set returns NULL.

### 5.3. Correlated subquery with EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
);
~~~

This query selects departments with at least one employee earning 20 million or more. `e.department_id = d.department_id` forms the correlation; the salary predicate restricts which rows qualify for existence.

### 5.4. Correlated subquery with NOT EXISTS

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
);
~~~

This query selects departments where no employee earns 20 million or more. It does not select only empty departments; departments whose employees all earn below the threshold or have NULL salary also satisfy this condition.

Write conditions matching the exact business question:
- "Has no employees" differs from
- "Has no employee reaching the salary threshold" and differs from
- "Every employee has a salary below the threshold."

### 5.5. Correlated subquery in HAVING

~~~sql
SELECT e.department_id,
       AVG(e.salary) AS department_avg
FROM employees e
GROUP BY e.department_id
HAVING AVG(e.salary) > (
    SELECT AVG(salary)
    FROM employees
);
~~~

The subquery here does not reference an outer grouping column so it is non-correlated, yet used inside HAVING. If a comparison depends on each group, the subquery can reference outer grouping keys using valid syntax.

## 6. Subqueries in FROM: Inline Views

A subquery placed in FROM is called an **inline view**. It creates an intermediate data source that the outer query block can filter, join, or sort.

~~~sql
SELECT d.department_id,
       d.avg_salary
FROM (
    SELECT department_id,
           AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) d
WHERE d.avg_salary > 20000000
ORDER BY d.department_id;
~~~

An inline view can return multiple rows and multiple columns; it is not constrained to be scalar. This example aggregates salaries by department first, then filters departments with an average above 20 million.

### 6.1. An inline view is not automatically correlated

~~~sql
SELECT d.department_id, x.avg_salary
FROM departments d
JOIN (
    SELECT department_id,
           AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) x
  ON x.department_id = d.department_id;
~~~

Inline view `X` does not reference `D`. It is an independent data source joined to `DEPARTMENTS`.

Oracle supports mechanisms like view merging and query transformations; do not assume an inline view is always materialized into a temporary table. Execution depends on the optimizer and query structure.

## 7. Comparing Single-Row and Multi-Row Operators

| Need | Common Syntax | Subquery Expectation |
| --- | --- | --- |
| Equal to one exact value | `= (subquery)` | One column, at most one row |
| Greater than a single value | `> (subquery)` | One column, at most one row |
| Matches one of several values | `IN (subquery)` | One column, may be many rows |
| Greater than at least one value | `> ANY (subquery)` | One column, may be many rows |
| Greater than all values | `> ALL (subquery)` | One column, may be many rows |
| At least one matching row exists | `EXISTS (subquery)` | May be many rows; select list does not determine value |
| No matching row exists | `NOT EXISTS (subquery)` | Empty-set check |

Do not blindly fix ORA-01427 by adding MAX. If the business rule is "belongs to one of several departments," use IN. If it is "higher than everyone in the department," use `> ALL`. If it is "at least one employee meets the criteria," use EXISTS.

## 8. NULLs in IN, NOT IN, ANY, ALL, and EXISTS

NULL is the root cause of many subtle logic bugs when working with multi-row subqueries.

### 8.1. IN with NULL in the set

Suppose the inner set is `(10, 20, NULL)`:

| Expression | Result |
| --- | --- |
| `10 IN (10,20,NULL)` | TRUE |
| `30 IN (10,20,NULL)` | UNKNOWN |
| `NULL IN (10,20,NULL)` | UNKNOWN |

If a value matches, IN is TRUE. If no value matches and NULL is in the set, the result can be UNKNOWN.

### 8.2. NOT IN with NULL in the set

| Expression | Result |
| --- | --- |
| `10 NOT IN (10,20,NULL)` | FALSE |
| `30 NOT IN (10,20,NULL)` | UNKNOWN |
| `NULL NOT IN (10,20)` | UNKNOWN |

Because WHERE keeps only TRUE, 30 is not returned even though it equals neither 10 nor 20. This is why NOT IN often surprises users.

### 8.3. EXISTS is unaffected by a NULL select list

~~~sql
SELECT d.department_id
FROM departments d
WHERE EXISTS (
    SELECT NULL
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

EXISTS only checks whether the subquery has any row. A row whose select list returns NULL is still a row, so EXISTS evaluates to TRUE. In practice, write `SELECT 1` so the statement expresses its intent cleanly.

### 8.4. NOT EXISTS and NULL in the outer row

NOT EXISTS checks that no row satisfies the entire WHERE condition inside the subquery. If comparing two columns hits NULL and evaluates to UNKNOWN, that row does not satisfy WHERE, which can cause NOT EXISTS to evaluate to TRUE.

To treat two NULLs as matching, write an explicit null-safe rule:

~~~sql
WHERE e.department_id = d.department_id
   OR (e.department_id IS NULL AND d.department_id IS NULL)
~~~

Add this branch only when business rules genuinely define NULL on both sides as the same group. For foreign keys, NULL usually means unassigned relationship rather than a shared join key.

## 9. Correlated Subqueries vs JOIN: Choosing the Right Representation

Many subqueries can be rewritten as JOINs, but the two forms do not always return the same row counts.

### 9.1. EXISTS and semi-join

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

A JOIN alternative:

~~~sql
SELECT DISTINCT d.department_id, d.department_name
FROM departments d
JOIN employees e
  ON e.department_id = d.department_id;
~~~

If a department has many employees, the JOIN creates multiple department rows and then DISTINCT deduplicates them. EXISTS directly expresses "keep the department if at least one employee exists," without multiplying outer rows due to multiple child rows.

The optimizer can transform EXISTS into a **semi-join**. Depending on the plan, you may see `HASH JOIN SEMI` or `NESTED LOOPS SEMI`.

### 9.2. NOT EXISTS and anti-join

~~~sql
SELECT d.department_id, d.department_name
FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Oracle can execute this logic as an **anti-join**, such as `HASH JOIN ANTI` or `NESTED LOOPS ANTI`, depending on data and plan.

### 9.3. Scalar aggregate vs JOIN with inline view

Subquery:

~~~sql
SELECT d.department_id,
       (
           SELECT AVG(e.salary)
           FROM employees e
           WHERE e.department_id = d.department_id
       ) AS avg_salary
FROM departments d;
~~~

Inline view representation:

~~~sql
SELECT d.department_id,
       x.avg_salary
FROM departments d
LEFT JOIN (
    SELECT department_id,
           AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
) x
  ON x.department_id = d.department_id;
~~~

LEFT JOIN preserves departments without employees; AVG with no matching group returns NULL on side X. Using INNER JOIN would drop departments without employees, changing the result.

### 9.4. Do not rewrite mechanically

Before converting a subquery to a JOIN or vice versa, verify:
- Can one outer row match multiple child rows?
- Must each outer row remain unique?
- Do NULLs change the result?
- Does the aggregate subquery return NULL or 0?
- Does the correlation condition include all key columns?
- Which filters belong in ON, WHERE, or HAVING?
- Does the query use DISTINCT or row limiting?

The goal is preserving exact semantics before comparing performance.

## 10. Subqueries in UPDATE and DELETE

Subqueries do not just serve SELECT. They can also compute updated values or identify rows to modify.

### 10.1. UPDATE with a scalar subquery

Suppose `DEPARTMENTS` has an `AVG_SALARY` column:

~~~sql
UPDATE departments d
SET avg_salary = (
    SELECT AVG(e.salary)
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

This is a correlated scalar subquery. For departments without employees, AVG returns NULL and `AVG_SALARY` is set to NULL. If business rules expect 0, wrap the subquery in NVL, while verifying what NULL truly means.

### 10.2. UPDATE with an EXISTS condition

~~~sql
UPDATE departments d
SET department_name = department_name || ' - ACTIVE'
WHERE EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

Updates only departments that have employees. In practice, guard against appending the suffix repeatedly on reruns; the example focuses on illustrating correlation.

### 10.3. DELETE with NOT EXISTS

~~~sql
DELETE FROM departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees e
    WHERE e.department_id = d.department_id
);
~~~

This deletes departments without employees. Run only on practice data and verify foreign keys, privileges, triggers, and business policies before using in a live system. This demonstrates that NOT EXISTS works in DML too, not only in SELECT.

## 11. Sample Dataset for Practice

The following examples use two sandbox tables. Run them in a dedicated schema with CREATE TABLE, INSERT, and SELECT privileges. The dataset includes:
- A department without employees.
- An employee with NULL `department_id`.
- An employee with NULL `salary`.
- Two employees sharing the highest salary to test scalar subqueries and outer query results.

### 11.1. Create the departments table

~~~sql
CREATE TABLE departments_subq (
    department_id   NUMBER(4)
        CONSTRAINT pk_departments_subq PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);
~~~

### 11.2. Create the employees table

~~~sql
CREATE TABLE employees_subq (
    employee_id   NUMBER(6)
        CONSTRAINT pk_employees_subq PRIMARY KEY,
    full_name     VARCHAR2(100 CHAR) NOT NULL,
    department_id NUMBER(4),
    salary        NUMBER(12,2),
    CONSTRAINT fk_emp_dept_subq
        FOREIGN KEY (department_id)
        REFERENCES departments_subq (department_id)
);
~~~

The foreign key allows NULL `DEPARTMENT_ID` because the column is not declared NOT NULL. An employee row with a NULL department ID does not violate the foreign key.

### 11.3. Insert departments

~~~sql
INSERT INTO departments_subq VALUES (10, 'Sales');
INSERT INTO departments_subq VALUES (20, 'Engineering');
INSERT INTO departments_subq VALUES (30, 'Human Resources');
INSERT INTO departments_subq VALUES (40, 'Research');

COMMIT;
~~~

Department 40 is intentionally left with no employees.

### 11.4. Insert employees

~~~sql
INSERT INTO employees_subq VALUES
    (101, 'An', 10, 20000000);

INSERT INTO employees_subq VALUES
    (102, 'Binh', 10, 15000000);

INSERT INTO employees_subq VALUES
    (103, 'Chi', 20, 30000000);

INSERT INTO employees_subq VALUES
    (104, 'Dung', 20, 30000000);

INSERT INTO employees_subq VALUES
    (105, 'Giang', 30, 12000000);

INSERT INTO employees_subq VALUES
    (106, 'Hanh', 30, NULL);

INSERT INTO employees_subq VALUES
    (107, 'Khanh', NULL, 18000000);

COMMIT;
~~~

7 employees total. Department 10 has two; department 20 has two; department 30 has two, one without a salary; department 40 has none. Employee 107 has not been assigned to a department.

## 12. Practicing Single-Row Subqueries

### 12.1. Find the highest-paid employees

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary = (
    SELECT MAX(salary)
    FROM employees_subq
)
ORDER BY employee_id;
~~~

The subquery returns a single value of 30,000,000. The outer query returns two rows: Chi and Dung. This illustrates how a single-row subquery can yield multiple outer result rows.

### 12.2. Find employees earning above the company-wide average

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary > (
    SELECT AVG(salary)
    FROM employees_subq
)
ORDER BY salary DESC, employee_id;
~~~

AVG ignores NULL `SALARY`. The average across the six non-NULL salaries is:

\[
\frac{20 + 15 + 30 + 30 + 12 + 18}{6}
= 20.833333\ldots \text{ million}
\]

Chi and Dung earn 30 million and are selected.

### 12.3. Scalar subquery returns NULL when nothing is found

~~~sql
SELECT (
    SELECT department_name
    FROM departments_subq
    WHERE department_id = 999
) AS missing_department
FROM dual;
~~~

Result: one row with `MISSING_DEPARTMENT = NULL`. This is not an ORA-01427 error.

### 12.4. Intentionally triggering ORA-01427

~~~sql
-- Subquery can return two rows for department 20.
SELECT employee_id, full_name
FROM employees_subq
WHERE salary = (
    SELECT salary
    FROM employees_subq
    WHERE department_id = 20
);
~~~

This query fails because the subquery returns salaries for both Chi and Dung. To find employees whose salary matches any salary in department 20, replace scalar `=` with `IN`.

### 12.5. Aggregates with and without GROUP BY

~~~sql
-- One row even with zero employees in department 40.
SELECT COUNT(*) AS employee_count,
       AVG(salary) AS avg_salary
FROM employees_subq
WHERE department_id = 40;
~~~

Result: `COUNT(*) = 0` and `AVG(SALARY) = NULL`.

~~~sql
-- May return many rows, one group per department.
SELECT department_id,
       AVG(salary) AS avg_salary
FROM employees_subq
GROUP BY department_id
ORDER BY department_id NULLS LAST;
~~~

The second query returns multiple groups, including one group for `DEPARTMENT_ID NULL`. Do not use it as a scalar subquery without a restricting condition or outer aggregation.

## 13. Practicing Multi-Row Subqueries

### 13.1. IN: employees in Sales or Engineering

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id
FROM employees_subq e
WHERE e.department_id IN (
    SELECT d.department_id
    FROM departments_subq d
    WHERE d.department_name IN ('Sales', 'Engineering')
)
ORDER BY e.department_id, e.employee_id;
~~~

Result includes employees 101, 102, 103, and 104.

### 13.2. ANY: salary higher than at least one Sales employee

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary > ANY (
    SELECT salary
    FROM employees_subq
    WHERE department_id = 10
)
ORDER BY salary DESC, employee_id;
~~~

Sales has salaries of 20 million and 15 million. An employee only needs a salary higher than at least one of those two; hence 18 million qualifies because it exceeds 15 million. The two Engineering employees earning 30 million also qualify.

### 13.3. ALL: salary higher than all Sales employees

~~~sql
SELECT employee_id, full_name, salary
FROM employees_subq
WHERE salary > ALL (
    SELECT salary
    FROM employees_subq
    WHERE department_id = 10
)
ORDER BY salary DESC, employee_id;
~~~

To exceed all Sales salaries, the value must exceed 20 million. Chi and Dung at 30 million qualify.

### 13.4. EXISTS: departments with employees

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
~~~

Result is departments 10, 20, and 30. Department 40 does not appear.

### 13.5. NOT EXISTS: departments without employees

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
)
ORDER BY d.department_id;
~~~

Result is department 40.

### 13.6. Demonstrating the NOT IN trap

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE d.department_id NOT IN (
    SELECT e.department_id
    FROM employees_subq e
);
~~~

The subquery returns 10, 20, 30, and NULL (from employee 107). Because of NULL, the query fails to return department 40 as expected.

Fix by filtering NULL:

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE d.department_id NOT IN (
    SELECT e.department_id
    FROM employees_subq e
    WHERE e.department_id IS NOT NULL
)
ORDER BY d.department_id;
~~~

Or use NOT EXISTS as shown earlier. For relationship-based anti-matches across two tables, NOT EXISTS usually states the intent more cleanly.

## 14. Practicing Correlated Subqueries

### 14.1. Employees earning above their own department's average

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary
FROM employees_subq e
WHERE e.salary > (
    SELECT AVG(e2.salary)
    FROM employees_subq e2
    WHERE e2.department_id = e.department_id
)
ORDER BY e.department_id, e.employee_id;
~~~

The subquery uses alias `E2` to read the same table while referencing `e.department_id` from the outer row. Result on the sample data:
- An: 20 million, higher than department 10's average of 17.5 million.
- Department 20 employees earn 30 million, equal to the average, so not strictly higher.
- Giang equals department 30's average of 12 million.
- Hanh has NULL salary, so the comparison is UNKNOWN.
- Khanh has NULL `department_id`; comparing against NULL is not TRUE so the aggregate subquery finds no rows, AVG returns NULL, and the row is not selected.

### 14.2. Counting employees for each department

~~~sql
SELECT d.department_id,
       d.department_name,
       (
           SELECT COUNT(*)
           FROM employees_subq e
           WHERE e.department_id = d.department_id
       ) AS employee_count
FROM departments_subq d
ORDER BY d.department_id;
~~~

Result:
- Sales: 2.
- Engineering: 2.
- Human Resources: 2.
- Research: 0.

This is a correlated scalar subquery in the SELECT list. `COUNT(*)` returns a value even when zero rows match.

### 14.3. Finding departments with at least one employee earning 20 million or more

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
)
ORDER BY d.department_id;
~~~

Result is Sales and Engineering. Human Resources has no employee meeting the threshold.

### 14.4. Finding departments with no employee meeting the threshold

~~~sql
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE NOT EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
      AND e.salary >= 20000000
)
ORDER BY d.department_id;
~~~

Result includes Human Resources and Research. Research has no employees; Human Resources has employees, none meeting the threshold. The EXISTS condition asks "does anyone meet the threshold?", not "are there any employees?".

### 14.5. Correlated subquery vs aggregate inline view

You can rewrite the department counting query using LEFT JOIN:

~~~sql
SELECT d.department_id,
       d.department_name,
       COUNT(e.employee_id) AS employee_count
FROM departments_subq d
LEFT JOIN employees_subq e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
~~~

Or join against an aggregated inline view:

~~~sql
SELECT d.department_id,
       d.department_name,
       NVL(x.employee_count, 0) AS employee_count
FROM departments_subq d
LEFT JOIN (
    SELECT department_id,
           COUNT(*) AS employee_count
    FROM employees_subq
    GROUP BY department_id
) x
  ON x.department_id = d.department_id
ORDER BY d.department_id;
~~~

Both approaches produce the same result on the sample dataset, with key cautions:
- `COUNT(e.employee_id)` in LEFT JOIN counts a non-NULL column; do not use `COUNT(*)` if childless departments should return 0.
- LEFT JOIN preserves departments without child rows; INNER JOIN would drop them.
- Correlated scalar subqueries may be transformed by the optimizer; do not assume they are always slower than JOINs.

## 15. Nested Subqueries

A subquery can contain another subquery. Example: finding employees in departments whose average salary exceeds the company-wide average:

~~~sql
SELECT e.employee_id,
       e.full_name,
       e.department_id,
       e.salary
FROM employees_subq e
WHERE e.department_id IN (
    SELECT x.department_id
    FROM employees_subq x
    GROUP BY x.department_id
    HAVING AVG(x.salary) > (
        SELECT AVG(salary)
        FROM employees_subq
    )
)
ORDER BY e.department_id, e.employee_id;
~~~

In this example:
- The innermost subquery computes the company-wide average and is non-correlated.
- The middle subquery groups employees by department and uses HAVING to compare against the company-wide average.
- The outer query selects employees belonging to departments exceeding the company-wide average.

When nesting multiple levels, use clear aliases and avoid reusing alias names that could confuse scope. Each query block should have a single clear purpose: group filtering, aggregation, or outer row selection.

### 15.1. Do not use outer aliases ambiguously

~~~sql
SELECT e.employee_id
FROM employees_subq e
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e2
    WHERE e2.department_id = e.department_id
      AND e2.salary > e.salary
);
~~~

Aliases `E` and `E2` clearly distinguish the outer table from the inner table despite reading the same physical table. Without clear distinction, SQL easily becomes buggy or hard to read.

## 16. Common Errors and Resolutions

| Error / Situation | Cause | Resolution |
| --- | --- | --- |
| ORA-01427 | Scalar subquery returns more than one row | Use IN/ANY/ALL/EXISTS, aggregate, or deterministically ordered row limiting |
| Subquery returns NULL and outer query returns zero rows | Scalar subquery found no data; comparing with NULL yields UNKNOWN | Check predicates, handle NULL per business logic |
| NOT IN unexpectedly returns 0 rows | Inner set contains NULL | Use NOT EXISTS or filter NULL inside the subquery |
| Correlated subquery returns incomplete results | Incomplete correlation predicate or wrong alias | Check join keys and alias scope |
| Department without employees returns NULL instead of 0 | Used MAX/other aggregate or unsuitable scalar subquery | `COUNT(*)` returns 0; use NVL if aggregate can be NULL |
| EXISTS written as `COUNT(*) > 0` | Counting rows when only existence is needed | Use EXISTS/NOT EXISTS |
| Replacing subquery with JOIN multiplies rows | One outer row matches multiple child rows | Use EXISTS, intentional DISTINCT, or pre-aggregate before JOIN |
| ANY/ALL produces UNKNOWN | Comparison operand or inner set contains NULL | Define NULL policy, filter or preserve UNKNOWN per business rules |
| Aggregate subquery with GROUP BY returns multiple rows | Multiple groups exist | Add group filter, use IN/ANY/ALL, or aggregate at outer level |
| Slow correlated query | Large outer set, missing index, or suboptimal plan | Inspect plan/runtime, check unnesting and access paths |

### 16.1. ORA-01427 should not always be fixed with MAX

If a scalar subquery unexpectedly returns multiple rows, using MAX to silence the error can mask a data problem. Use MAX only when the business requirement is genuinely "the maximum value." If the requirement is "any matching value," use IN; if a unique key was expected, inspect constraints and query conditions.

### 16.2. Zero-row vs multi-row subquery behavior

| Context | 0 Rows | Multiple Rows |
| --- | --- | --- |
| Scalar subquery | NULL | ORA-01427 |
| IN | No values to match; usually FALSE on empty set | Checks membership |
| ANY | FALSE on empty set | TRUE if at least one comparison is TRUE |
| ALL | TRUE on empty set | TRUE if all comparisons are TRUE |
| EXISTS | FALSE | TRUE |
| NOT EXISTS | TRUE | FALSE |

This table summarizes basic logic when unaffected by NULL-induced UNKNOWNs. With IN/ANY/ALL, NULLs in the set or outer expression can produce UNKNOWN.

## 17. Performance and Execution Plans

There is no rule that subqueries are always slower than JOINs. The Oracle optimizer can apply transformations to choose a plan suited to statistics and data structures.

### 17.1. Subquery unnesting

Oracle can transform certain subqueries in WHERE into equivalent joins. This process is called **subquery unnesting**. For example, EXISTS can become a semi-join, and NOT EXISTS can become an anti-join.

Whether unnesting applies depends on:
- Subquery structure and inner functions/conditions.
- Aggregation, DISTINCT, GROUP BY, or row limiting.
- NULL semantics and data constraints.
- Oracle version, optimizer settings, and cost estimates.

Do not rewrite every subquery as a JOIN prematurely before measuring. Write semantically clear SQL first, then inspect the plan.

### 17.2. Correlated subqueries and indexes

For the predicate:

~~~sql
WHERE e.department_id = d.department_id
~~~

an index on `EMPLOYEES_SUBQ(DEPARTMENT_ID)` can help certain access paths, especially when the outer query returns few departments. If the subquery also filters by salary, a composite index like `(DEPARTMENT_ID, SALARY)` may be considered depending on workload, though no index is universally optimal.

Evaluate:
- Number of departments/outer rows.
- Number of employees per department.
- Predicate selectivity.
- Frequency of INSERT/UPDATE/DELETE.
- Other queries sharing the index.
- Cost of table access vs index access.

### 17.3. Viewing plans with DBMS_XPLAN

In a practice environment:

~~~sql
EXPLAIN PLAN FOR
SELECT d.department_id, d.department_name
FROM departments_subq d
WHERE EXISTS (
    SELECT 1
    FROM employees_subq e
    WHERE e.department_id = d.department_id
);

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

You may see operations like `TABLE ACCESS`, `INDEX RANGE SCAN`, `HASH JOIN SEMI`, or `NESTED LOOPS SEMI` depending on the plan. For correlated scalar subqueries, you may see `FILTER` or a transformed join. Exact operation names and plan shapes depend on version, data, and optimizer.

`EXPLAIN PLAN` shows an estimated plan; it does not prove actual runtime duration. On production systems, inspect the executed cursor plan and runtime statistics when authorized, such as `DBMS_XPLAN.DISPLAY_CURSOR` with appropriate options.

### 17.4. Do not judge solely from textual appearances in SQL

A subquery written in the SELECT list does not automatically execute separately for every row. The optimizer may apply scalar subquery caching or suitable transformations. Conversely, a JOIN can also be expensive if it inflates cardinality or requires large sorts/hashes.

Measure on representative data, checking logical reads, elapsed time, rows, buffer gets, and plans; never judge solely by SQL statement length.

## 18. Java JDBC: Using Subqueries with Bind Variables

Subqueries live inside the SQL text, while input parameters should be passed via bind variables to prevent SQL injection and avoid string concatenation.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class EmployeeSearchRepository {
    private final DataSource dataSource;

    public EmployeeSearchRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printEmployeesAboveDepartmentAverage(long departmentId)
            throws SQLException {

        String sql = """
            SELECT e.employee_id,
                   e.full_name,
                   e.salary
            FROM employees_subq e
            WHERE e.department_id = ?
              AND e.salary > (
                  SELECT AVG(e2.salary)
                  FROM employees_subq e2
                  WHERE e2.department_id = e.department_id
              )
            ORDER BY e.salary DESC NULLS LAST,
                     e.employee_id
            """;

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, departmentId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    long employeeId = rs.getLong("EMPLOYEE_ID");
                    String fullName = rs.getString("FULL_NAME");
                    java.math.BigDecimal salary =
                        rs.getBigDecimal("SALARY");

                    System.out.println(
                        employeeId + " " + fullName + " " + salary
                    );
                }
            }
        }
    }
}
~~~

The subquery correlates on `E.DEPARTMENT_ID`; the bind variable supplies only the department ID to the outer query. Aliases and correlation predicates remain fixed in the SQL text.

### 18.1. Bind lists without string concatenation in IN

You cannot pass an arbitrary list into a single `?` placeholder expecting JDBC to expand it into multiple bind variables inside IN. Instead, you can:
- Generate the exact number of placeholders for a controlled list and bind each value.
- Use a subquery fetching the set of values from a table.
- Use an appropriate Oracle collection/table parameter mechanism if the application needs large lists.

Never concatenate user-supplied values directly into SQL. Table and column names cannot be bound either; if a query needs dynamic selection, map through an allowlist.

### 18.2. NULL when reading scalar results

A scalar subquery can return NULL when no matching row exists. In JDBC:
- `getString`/`getBigDecimal`/`getObject` can return Java `null` depending on type.
- Primitive getters like `getInt` return `0`; call `wasNull()` immediately after the getter to detect SQL NULL.
- If `NVL` is used in SQL, the NULL state is replaced before JDBC reads it.

Do not use NVL just to avoid handling Java null if NULL carries business meaning that must be preserved.

## 19. Workflow for Choosing a Subquery Type

Before writing the query, determine:

1. Must the subquery return **one value** or a **set of values**?
2. Is uniqueness guaranteed by a primary key or unique constraint?
3. If zero rows match, should the result be NULL, 0, FALSE, or no outer row?
4. If multiple rows exist, do you need IN, ANY, ALL, or EXISTS?
5. Does the subquery need to reference an outer query alias?
6. If NULL exists in the inner set, what will IN/NOT IN/ANY/ALL return?
7. Must outer rows be preserved when no child rows exist?
8. Would a JOIN rewrite duplicate or drop rows?
9. Can the optimizer unnest the subquery, and which operations appear in the actual plan?
10. Does the JDBC application preserve types and NULL states accurately?

Quick reference:

| Business Question | Commonly Suitable Expression |
| --- | --- |
| Equal to highest salary | Scalar subquery with MAX |
| Belongs to one of several departments | IN |
| Greater than at least one value | ANY |
| Greater than every value | ALL |
| At least one employee meets criteria | EXISTS |
| No employee meets criteria | NOT EXISTS |
| Each department needs employee count | Correlated COUNT or aggregate + LEFT JOIN |
| Each employee vs own department's average | Correlated scalar AVG |
| Need pre-aggregated intermediate table | Inline view in FROM |

## 20. Common Misconceptions

**Single-row subquery means the outer query returns one row.** False. The subquery returns one value; the outer query can return multiple rows matching that value.

**A subquery returning zero rows always causes an error.** False. A zero-row scalar subquery returns NULL; EXISTS returns FALSE; IN with an empty set matches nothing.

**A multi-row subquery can be used with regular equality `=`.** False in scalar context; it usually raises ORA-01427. Use IN/ANY/ALL/EXISTS as needed.

**Having MAX/AVG/COUNT guarantees the subquery returns only one row.** False if GROUP BY creates multiple groups.

**NOT IN and NOT EXISTS are always equivalent.** False when NULLs exist or when the outer key can be NULL.

**EXISTS requires SELECTing a specific column.** False. EXISTS tests row existence; `SELECT 1` is simply a readable convention.

**A correlated subquery always physically runs once per outer row.** False. That is the logical model; the optimizer may unnest, use joins, or apply other transformations.

**JOIN is always faster than a subquery.** False. The optimizer can transform subqueries into joins; JOINs can also multiply rows and require DISTINCT.

**`COUNT(*)` in a correlated subquery and EXISTS are always interchangeable.** False. COUNT computes a quantity; EXISTS checks existence and expresses a different intent.

**ANY and ALL differ only in name.** False. ANY requires at least one comparison to hold; ALL requires every comparison to hold.

**ALL on an empty set returns FALSE.** False under universal quantification; ALL over an empty set is TRUE, whereas ANY over an empty set is FALSE.

**A scalar subquery in the SELECT list cannot be correlated.** False. Counting employees per department is a correlated scalar subquery.

**A subquery in FROM must be scalar.** False. Inline views commonly return multiple rows and columns.

**EXPLAIN PLAN reports exact runtime duration.** False. It shows an estimated plan; runtime analysis requires inspecting appropriate cursor statistics.

## 21. Self-Practice Exercises

1. Write a single-row subquery finding all employees earning the company-wide maximum salary. Why can the outer result have multiple rows?
2. Write a subquery finding employees earning above the company-wide average salary.
3. If a scalar subquery returns 0 rows, what value does the outer query receive? What error occurs if it returns 2 rows?
4. Why does `SELECT AVG(salary)` without GROUP BY return one row, while `SELECT department_id, AVG(salary) GROUP BY department_id` can return multiple rows?
5. Use IN to find employees in Sales or Engineering.
6. Use ANY to find employees earning more than at least one Sales employee.
7. Use ALL to find employees earning more than every Sales employee.
8. Explain the difference between `> ANY` and `> ALL` using the set `10, 20, 30`.
9. Why might NOT IN fail to return department 40 when the subquery contains a NULL `department_id`?
10. Rewrite the query for departments without employees using NOT EXISTS.
11. If `employee.department_id` is NULL, why might an equality-based NOT EXISTS still return that employee?
12. Write a correlated scalar subquery counting employees for each department, including departments without employees.
13. Write a correlated subquery finding employees earning above their own department's average salary.
14. Explain why correlation does not prove the subquery physically runs once per row.
15. Write EXISTS to find departments with at least one employee earning 20 million or more.
16. Write NOT EXISTS to find departments where no employee earns 20 million; does its result differ from "departments with no employees"?
17. Rewrite correlated COUNT using LEFT JOIN and explain why `COUNT(e.employee_id)` is used instead of `COUNT(*)`.
18. A scalar subquery uses MAX but has GROUP BY. Why can it still return multiple rows?
19. Use UPDATE with a correlated subquery to store average salaries in the departments table. What happens for a department with no employees?
20. Inspect execution plans for EXISTS and correlated AVG. Look for semi-join, filter, or access path operations if present.
21. Write a nested query finding employees in departments whose average salary exceeds the company-wide average.
22. In Java JDBC, why should you use `PreparedStatement` for input values and check `wasNull()` after primitive getters?
23. A JOIN makes each department appear multiple times due to multiple employees. When does EXISTS express the intent better?
24. Design an anti-match query when the outer key can be NULL. Explicitly specify whether NULLs should be treated as a matching group.

**Single-row subqueries supply one value, multi-row subqueries operate on a set of values, and correlated subqueries reference data from an outer query block.** Choosing the right IN, ANY, ALL, EXISTS, or NOT EXISTS operator lets SQL express the question accurately; understanding NULLs and row counts prevents logic bugs and ORA-01427. Ultimately, the execution plan reveals how Oracle runs the query: correlated does not mean forced physical looping, and subqueries are not inherently slower than JOINs.
