# Reading Empty Results, NULL Values, and Multiplied Row Counts

When running a `SELECT` statement in Oracle, the result can be **no rows at all**, rows where some columns contain **`NULL`**, or **more rows than expected** because a data join created multiple combinations. These three phenomena are often lumped together as "the query returned wrong data," yet their causes and fixes are completely different.

For example:

- Searching for an employee with a nonexistent ID and getting **0 rows**: an empty result set.
- Finding an employee whose `MANAGER_ID` has not been assigned and getting **1 row with MANAGER_ID = NULL**: a row exists, with a missing value.
- Joining a customer with three phone numbers and two orders and getting six rows: **row multiplication from 1-to-many relationships**, which may be relationally valid or a query design bug.

Lesson objectives:

1. Distinguish **empty result set**, **NULL**, empty strings, and empty LOBs.
2. Understand how Oracle handles NULL in conditions, aggregates, joins, subqueries, and conversion functions.
3. Diagnose why a parent row appears multiple times after a `JOIN`.
4. Choose the right tool: `IS NULL`, `COUNT`, `EXISTS`, `NOT EXISTS`, pre-aggregation, `DISTINCT`, or analytic functions.
5. Know how to verify each stage so queries return the right row count and business meaning.

## 1. Three Distinct Phenomena

| Phenomenon | Observed result | Meaning |
| --- | --- | --- |
| **Empty result set** | Zero rows returned | No row matched the condition, or the source produced no rows |
| **Rows containing NULL** | Rows exist, but one or more columns show `(null)` | The row exists; the column's value is unknown/unprovided per NULL semantics |
| **Multiplied row counts** | One parent key appears in multiple output rows | A join produced multiple matching pairs, or projection dropped columns making distinct rows look identical |

Three simple examples:

```sql
-- 0 rows if no employee_id = 999 exists.
SELECT employee_id, full_name
FROM lab_employees
WHERE employee_id = 999;

-- May return 1 row; manager_id may be NULL.
SELECT employee_id, full_name, manager_id
FROM lab_employees
WHERE employee_id = 1;

-- May return multiple rows for one employee if they have multiple phone numbers.
SELECT e.employee_id, e.full_name, p.phone_number
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

**No rows** is not the same as **one row with all NULL columns**. If an application fails to distinguish these two cases, it can display wrong business states or overwrite existing data.

## 2. Lab Data to Reproduce Each Case

The examples use three tables: departments, employees, and employee phone numbers. An employee may lack a department, lack a salary, or have multiple phone numbers.

### 2.1. Creating the Tables in a Practice Schema

Run the DDL below only in a **lab schema you own** with table-creation privileges and tablespace quota. If tables with the same names already exist, use a different practice schema instead of dropping tables of unclear ownership.

```sql
CREATE TABLE lab_departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER,
    manager_id    NUMBER,
    salary        NUMBER(12, 2),
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    CONSTRAINT fk_lab_emp_dept
        FOREIGN KEY (department_id)
        REFERENCES lab_departments (department_id),
    CONSTRAINT fk_lab_emp_manager
        FOREIGN KEY (manager_id)
        REFERENCES lab_employees (employee_id),
    CONSTRAINT ck_lab_emp_active
        CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_employee_phones (
    phone_id      NUMBER PRIMARY KEY,
    employee_id   NUMBER NOT NULL,
    phone_number  VARCHAR2(30 CHAR) NOT NULL,
    phone_type    VARCHAR2(20 CHAR),
    CONSTRAINT fk_lab_phone_employee
        FOREIGN KEY (employee_id)
        REFERENCES lab_employees (employee_id)
);
```

### 2.2. Inserting Purposeful Data

```sql
INSERT INTO lab_departments VALUES (10, 'Engineering');
INSERT INTO lab_departments VALUES (20, 'Sales');
INSERT INTO lab_departments VALUES (30, 'Human Resources');
INSERT INTO lab_departments VALUES (40, 'Legal');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (1, 'An', 10, NULL, 5000, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (2, 'Bình', 10, 1, 3000, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (3, 'Chi', 10, 1, NULL, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (4, 'Dũng', 20, NULL, 2800, 'Y');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (5, 'Hà', 20, 4, 2800, 'N');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, manager_id, salary, active_flag)
VALUES (6, 'Lan', NULL, NULL, 1800, 'Y');

INSERT INTO lab_employee_phones VALUES (101, 1, '0900000001', 'MOBILE');
INSERT INTO lab_employee_phones VALUES (102, 1, '0280000001', 'OFFICE');
INSERT INTO lab_employee_phones VALUES (103, 2, '0900000002', 'MOBILE');
INSERT INTO lab_employee_phones VALUES (104, 4, '0900000004', 'MOBILE');
INSERT INTO lab_employee_phones VALUES (105, 4, '0280000004', 'OFFICE');

COMMIT;
```

The dataset has these characteristics:

| Employee | Department | Manager | Salary | Phones |
| --- | --- | --- | ---: | ---: |
| An (1) | Engineering (10) | `NULL` | 5000 | 2 |
| Bình (2) | Engineering (10) | An (1) | 3000 | 1 |
| Chi (3) | Engineering (10) | An (1) | `NULL` | 0 |
| Dũng (4) | Sales (20) | `NULL` | 2800 | 2 |
| Hà (5) | Sales (20) | Dũng (4) | 2800 | 0 |
| Lan (6) | Unassigned | `NULL` | 1800 | 0 |

Department **Legal (40)** has no employees. This dataset is enough to observe empty results, NULLs, outer joins, 1-to-many joins, and multiplication caused by joining multiple child tables.

## 3. Empty Results: A Query Returns Zero Rows

An empty result set means **no rows satisfied the query conditions**. For example:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE employee_id = 999;
```

Because the table has no ID 999, the client displays "no rows selected" or an empty result table. That is not a SQL error: the statement is valid and the condition simply found no matching records.

### 3.1. Distinguishing an Empty Table from an Unmatched Condition

```sql
-- Check total row count across the table.
SELECT COUNT(*) AS total_rows
FROM lab_employees;

-- Check whether any rows match the condition.
SELECT COUNT(*) AS matching_rows
FROM lab_employees
WHERE department_id = 999;
```

On the lab data, the results are 6 and 0, respectively. The second query **still returns one row** with `MATCHING_ROWS = 0` because `COUNT(*)` is an aggregate without `GROUP BY`. This is a vital distinction:

- `SELECT employee_id ... WHERE ...` can return **0 rows**.
- `SELECT COUNT(*) ... WHERE ...` without `GROUP BY` still returns **1 row with COUNT = 0**.

Next example:

```sql
SELECT SUM(salary) AS salary_total
FROM lab_employees
WHERE department_id = 999;
```

The result is **1 row with `SALARY_TOTAL = NULL`**, because `SUM` over a set with no matching values returns NULL. Therefore, never infer from "SUM returned NULL" that the query returned zero rows; inspect **returned row count** and **column value** separately.

### 3.2. Aggregate Without GROUP BY vs. With GROUP BY

```sql
-- Without GROUP BY: COUNT returns one row even when the source has zero rows.
SELECT COUNT(*) AS row_count
FROM lab_employees
WHERE department_id = 999;

-- With GROUP BY: no groups are formed, so zero result rows are returned.
SELECT department_id, COUNT(*) AS row_count
FROM lab_employees
WHERE department_id = 999
GROUP BY department_id;
```

The first query returns `0`. The second returns **0 rows**, because there is no input to form any `DEPARTMENT_ID` group. That is the difference between **whole-set aggregation** and **per-group aggregation**.

### 3.3. `HAVING` Can Eliminate Every Group

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM lab_employees
GROUP BY department_id
HAVING COUNT(*) > 100;
```

Groups are formed, yet none exceed 100 employees; the final result is **0 rows**. To investigate why, remove `HAVING` to inspect per-group metrics before filtering.

### 3.4. Distinguishing "Not Found" from "Not Visible"

A table may not appear in query results because:

- It does not exist in the current schema/PDB.
- It has a different name, including double-quoted identifiers.
- You are connected to the wrong PDB or schema.
- Your account lacks privileges, so `USER_*`/`ALL_*` dictionary views do not list it.
- Filter conditions or joins eliminated all rows.

When investigating, verify your context first:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'DB_NAME')        AS database_name,
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user,
    SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema
FROM dual;
```

Then check objects within your permitted scope. **0 rows from `ALL_TABLES` is not absolute proof that a table does not exist anywhere in the database**; it may simply lie outside your visibility privileges.

## 4. NULL: The Row Exists, but the Value Is Undetermined

`NULL` represents the state of **no known/provided value** for an attribute. It is not zero, not the string `'NULL'`, and does not necessarily mean "not applicable." Business meaning must be defined per column.

Example:

```sql
SELECT employee_id, full_name, manager_id, salary
FROM lab_employees
WHERE employee_id IN (1, 3);
```

An (1) has `MANAGER_ID NULL` because no manager is assigned. Chi (3) has `SALARY NULL` because her salary has not been recorded. Both rows exist; only certain attributes lack values.

### 4.1. NULL Is Not Equal to Any Value, Including NULL

In SQL, comparisons with NULL usually evaluate to **UNKNOWN**:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE manager_id = NULL;
```

No rows are selected because `manager_id = NULL` never returns `TRUE`. Even:

```sql
SELECT *
FROM dual
WHERE NULL = NULL;
```

returns no rows. To test for NULL, use:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE manager_id IS NULL;
```

And to find employees who have a manager:

```sql
SELECT employee_id, full_name, manager_id
FROM lab_employees
WHERE manager_id IS NOT NULL;
```

### 4.2. Three-Valued Logic: TRUE, FALSE, UNKNOWN

SQL uses three-valued logic when NULL is present:

| Expression | Result |
| --- | --- |
| `5 = 5` | TRUE |
| `5 = 3` | FALSE |
| `5 = NULL` | UNKNOWN |
| `NULL = NULL` | UNKNOWN |
| `NULL IS NULL` | TRUE |
| `NULL IS NOT NULL` | FALSE |

`WHERE` and `HAVING` keep rows/groups only when the condition is **TRUE**. Both `FALSE` and `UNKNOWN` are excluded.

Example:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > 2000;
```

Chi has `SALARY NULL`, so `NULL > 2000` is UNKNOWN; Chi is not returned. If business logic wants to include employees without a recorded salary for separate handling, write:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary > 2000
   OR salary IS NULL;
```

### 4.3. NOT, AND, and OR with UNKNOWN

| A | B | `A AND B` | `A OR B` | `NOT A` |
| --- | --- | --- | --- | --- |
| TRUE | UNKNOWN | UNKNOWN | TRUE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN | TRUE |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

For example, `NOT (salary > 2000)` **does not include** rows with `SALARY NULL`, because `NOT UNKNOWN` remains UNKNOWN:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE NOT (salary > 2000);
```

To include both employees earning at most 2000 and those without a recorded salary:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary <= 2000
   OR salary IS NULL;
```

### 4.4. Using NVL, COALESCE, and NULLIF Properly

**`NVL`** replaces a NULL value with a fallback value:

```sql
SELECT
    employee_id,
    full_name,
    salary,
    NVL(salary, 0) AS salary_for_display
FROM lab_employees;
```

**`COALESCE`** returns the first non-NULL expression:

```sql
SELECT
    employee_id,
    COALESCE(
        TO_CHAR(manager_id),
        'No manager assigned'
    ) AS manager_display
FROM lab_employees;
```

**`NULLIF(a,b)`** returns NULL if both expressions are equal, otherwise returns the first expression:

```sql
SELECT
    NULLIF(salary, 0) AS salary_or_null
FROM lab_employees;
```

Do not apply `NVL(salary, 0)` mindlessly in every calculation. If NULL means **salary unknown**, replacing it with 0 can skew total payroll or average salary reports. Substitute 0 for NULL only when business rules explicitly define "missing value" as zero.

### 4.5. NVL Inside vs. Outside an Aggregate Differs

```sql
SELECT
    SUM(salary) AS sum_ignore_null,
    SUM(NVL(salary, 0)) AS sum_null_as_zero,
    NVL(SUM(salary), 0) AS display_sum
FROM lab_employees
WHERE department_id = 999;
```

When zero rows match:

- `SUM(SALARY)` returns NULL.
- `SUM(NVL(SALARY, 0))` also returns NULL because **there are no input rows** on which to evaluate NVL.
- `NVL(SUM(SALARY), 0)` returns 0 because NVL is applied to the NULL aggregate result.

If rows exist but every salary value is NULL, `SUM(NVL(SALARY, 0))` returns 0 while `SUM(SALARY)` returns NULL. These are two different business situations: **no rows** vs. **rows exist without figures yet**.

### 4.6. Empty Strings in Oracle

For standard SQL character string types such as `VARCHAR2`, Oracle currently treats zero-length strings (`''`) as `NULL`:

```sql
SELECT
    CASE WHEN '' IS NULL THEN 'EMPTY_IS_NULL'
         ELSE 'NOT_NULL' END AS empty_string_test
FROM dual;
```

When inserting:

```sql
INSERT INTO lab_employees
    (employee_id, full_name, department_id, salary, active_flag)
VALUES
    (7, 'Quang', 10, NULL, 'Y');

COMMIT;
```

If an application sends an empty string to a nullable `VARCHAR2` column, the database stores NULL under Oracle semantics. Do not use `= ''` to search for empty strings; use `IS NULL` when that matches Oracle's interpretation. **Do not generalize this rule to every data type**: empty LOBs like `EMPTY_CLOB()` differ from NULL; check release documentation for other types and future behavior.

### 4.7. NULL vs. Empty LOBs

For LOBs, distinguish:

- `NULL`: no LOB locator/value exists.
- `EMPTY_CLOB()` or `EMPTY_BLOB()`: a LOB locator exists, but its content length is 0.

Example:

```sql
CREATE TABLE lab_lob_state (
    id      NUMBER PRIMARY KEY,
    content CLOB
);

INSERT INTO lab_lob_state VALUES (1, NULL);
INSERT INTO lab_lob_state VALUES (2, EMPTY_CLOB());

SELECT id,
       CASE WHEN content IS NULL THEN 'NULL'
            ELSE 'NOT NULL' END AS lob_state,
       DBMS_LOB.GETLENGTH(content) AS lob_length
FROM lab_lob_state
ORDER BY id;
```

Logical output:

| ID | LOB_STATE | LOB_LENGTH |
| ---: | --- | ---: |
| 1 | NULL | NULL |
| 2 | NOT NULL | 0 |

Certain APIs modifying internal LOBs require an initialized locator; a NULL locator cannot be treated like an empty LOB. Applications should clearly separate "not uploaded yet," "empty file uploaded," and "content uploaded."

## 5. NULL in JOINs

### 5.1. NULL Does Not Match NULL Under Ordinary Equality

Suppose an employee row has `DEPARTMENT_ID NULL`:

```sql
SELECT e.employee_id, e.full_name, d.department_name
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id;
```

Employee Lan does not appear because `NULL = department_id` is UNKNOWN. An inner join retains only row pairs where the ON condition is TRUE.

### 5.2. LEFT JOIN Produces Extra Rows with NULL Columns

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Legal (40) has no employees yet still appears with `E.EMPLOYEE_ID` and `E.FULL_NAME` set to NULL. Those NULLs are **generated by the outer join**, not a real employee row whose columns happen to be NULL.

### 5.3. Conditions in ON vs. WHERE Can Drop Outer Join Rows

To keep every department while joining only active employees:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

If you move the condition to WHERE:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

The outer-join padded rows have `E.ACTIVE_FLAG NULL`; `NULL = 'Y'` evaluates to UNKNOWN and is dropped by WHERE. The second query therefore stops preserving departments without active employees. This is the classic cause of "a LEFT JOIN that behaves like an INNER JOIN."

### 5.4. Counting Rows After a LEFT JOIN

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_row_count,
    COUNT(e.employee_id) AS employee_count
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

For department 40:

- `COUNT(*) = 1` because the outer join produced one row representing the department.
- `COUNT(e.employee_id) = 0` because the right-side key column is NULL in the padded row.

When counting **employees**, count a right-side column that is **non-NULL for every real row**, usually the primary key. Never use `COUNT(*)` in an outer join and label it as the employee count.

## 6. Multiplied Row Counts: Understanding 1-to-Many Relationships

A parent row appearing multiple times after a join is not automatically a bug. If an employee has two phone numbers, joining employees with phones produces **two rows** representing the two relationship pairs.

### 6.1. One Employee, Multiple Phones

```sql
SELECT
    e.employee_id,
    e.full_name,
    p.phone_id,
    p.phone_number,
    p.phone_type
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1
ORDER BY p.phone_id;
```

The result has two rows:

| EMPLOYEE_ID | FULL_NAME | PHONE_ID | PHONE_NUMBER | PHONE_TYPE |
| ---: | --- | ---: | --- | --- |
| 1 | An | 101 | 0900000001 | MOBILE |
| 1 | An | 102 | 0280000001 | OFFICE |

`EMPLOYEE_ID` repeats, yet the output is accurate: the query returns **one row per phone**. If the screen wants only one row per employee, decide how to represent the phone list (aggregation, subquery, JSON/XML, or picking one phone type by rule), rather than arbitrarily deleting rows.

### 6.2. Why Do Two 1-to-Many Child Tables Multiply Rows?

Suppose an employee has:

- 2 phone numbers in `LAB_EMPLOYEE_PHONES`.
- 3 skills in a `LAB_EMPLOYEE_SKILLS` table.

If you join both child tables directly to employee:

```sql
SELECT
    e.employee_id,
    p.phone_number,
    s.skill_name
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
JOIN lab_employee_skills s
  ON s.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

With 2 phones and 3 skills, the result has **2 × 3 = 6 rows**. Each phone number is paired with every skill. This is a Cartesian multiplication **within the relationships of the same employee**, not Oracle misbehaving.

Diagram:

```text
                 EMPLOYEE 1
                 /       \
                /         \
       2 PHONE ROWS      3 SKILL ROWS
                \         /
                 \       /
            JOIN ON EMPLOYEE_ID
                      |
                      v
          2 x 3 = 6 combination rows
```

If you then run `COUNT(p.phone_id)`, each phone is counted three times; running `SUM(p.some_amount)` multiplies the sum by the number of skills. This is a common reporting bug when joining multiple 1-to-many relationships without aggregating each child table first.

## 7. Distinguishing True Duplicates from Rows That Look Alike

There are at least three distinct concepts:

1. **Duplicate key:** the same business/technical key appears in multiple table rows. This violates uniqueness if constrained.
2. **Duplicate projected rows:** rows differ on unselected columns, but the displayed subset of columns looks identical.
3. **Repeated parent row after join:** one parent row joins to multiple child rows, so repeating the parent key is relationally accurate.

Example:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

The two output rows share the same `EMPLOYEE_ID` and `FULL_NAME` because the query omitted phone columns. Yet the join source had two distinct child rows.

Adding `DISTINCT`:

```sql
SELECT DISTINCT e.employee_id, e.full_name
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
WHERE e.employee_id = 1;
```

leaves one row. This is reasonable **if the goal is simply a list of employees who have at least one phone number**; however, it hides phone counts and can mask a broken join if the author does not understand the root cause.

## 8. Choosing the Right Query Pattern for Your Goal

### 8.1. Only Checking Whether at Least One Child Exists: Use EXISTS

If the requirement is "get employees who have at least one phone number," do not join and apply DISTINCT when phone data is unneeded:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE EXISTS (
    SELECT 1
    FROM lab_employee_phones p
    WHERE p.employee_id = e.employee_id
)
ORDER BY e.employee_id;
```

`EXISTS` tests for matching child rows without multiplying employee rows across multiple phones. Oracle can transform it into a semi-join in the execution plan.

### 8.2. Needing Child Counts: GROUP BY the Child Table First

```sql
WITH phone_counts AS (
    SELECT employee_id, COUNT(*) AS phone_count
    FROM lab_employee_phones
    GROUP BY employee_id
)
SELECT
    e.employee_id,
    e.full_name,
    NVL(pc.phone_count, 0) AS phone_count
FROM lab_employees e
LEFT JOIN phone_counts pc
  ON pc.employee_id = e.employee_id
ORDER BY e.employee_id;
```

The `PHONE_COUNTS` CTE has at most one row per `EMPLOYEE_ID`. Joining it to employees never multiplies parent rows. `NVL` converts missing CTE matches to 0 because the business intent here is **counting phones** and having no child rows means zero.

### 8.3. Joining Multiple Child Tables: Aggregate Each Table Separately

Suppose `LAB_EMPLOYEE_SKILLS` is added. Safe pattern for count reports:

```sql
WITH phone_counts AS (
    SELECT employee_id, COUNT(*) AS phone_count
    FROM lab_employee_phones
    GROUP BY employee_id
),
skill_counts AS (
    SELECT employee_id, COUNT(*) AS skill_count
    FROM lab_employee_skills
    GROUP BY employee_id
)
SELECT
    e.employee_id,
    e.full_name,
    NVL(p.phone_count, 0) AS phone_count,
    NVL(s.skill_count, 0) AS skill_count
FROM lab_employees e
LEFT JOIN phone_counts p
  ON p.employee_id = e.employee_id
LEFT JOIN skill_counts s
  ON s.employee_id = e.employee_id
ORDER BY e.employee_id;
```

Each CTE is already collapsed to one row per employee, so the join never produces a 2 × 3 cross product. **If you actually need every phone and every skill in one result set**, the combinations may be desired; pre-aggregate only when business logic needs employee-level metrics.

### 8.4. Needing One Preferred Child Row by Rule: ROW_NUMBER

If you want only **one preferred phone number** per employee, define an explicit priority order. For instance, prefer MOBILE first, then smaller phone ID:

```sql
WITH ranked_phones AS (
    SELECT
        p.employee_id,
        p.phone_id,
        p.phone_number,
        p.phone_type,
        ROW_NUMBER() OVER (
            PARTITION BY p.employee_id
            ORDER BY
                CASE p.phone_type
                    WHEN 'MOBILE' THEN 1
                    WHEN 'OFFICE' THEN 2
                    ELSE 3
                END,
                p.phone_id
        ) AS rn
    FROM lab_employee_phones p
)
SELECT
    e.employee_id,
    e.full_name,
    rp.phone_number,
    rp.phone_type
FROM lab_employees e
LEFT JOIN ranked_phones rp
  ON rp.employee_id = e.employee_id
 AND rp.rn = 1
ORDER BY e.employee_id;
```

`ROW_NUMBER` reduces multiple child rows into one chosen row via a **priority rule with a tie-breaker**. The `RN=1` condition sits inside `ON` so employees without phone numbers are still preserved. Never use `MIN(PHONE_NUMBER)` just to pick "some arbitrary number" when business rules define a real priority rule.

### 8.5. Only Deduplicating Displayed Rows: DISTINCT

`DISTINCT` fits when the true goal is the set of unique value combinations for the selected columns:

```sql
SELECT DISTINCT department_id
FROM lab_employees
ORDER BY department_id NULLS LAST;
```

However, `DISTINCT` cannot decide:

- Which child row out of many should be kept?
- Should monetary totals be counted once or multiple times?
- How should differing columns across child rows be combined?
- Is the data relationship missing a join condition?

**If you use DISTINCT to mask a wrong join, the screen may look fine while totals or detail rows remain wrong.**

## 9. NOT IN, NOT EXISTS, and NULL

Another major trap is finding rows **with no related child** using `NOT IN` when the subset can contain NULL.

### 9.1. NOT IN with NULL Can Eliminate All Results

Consider:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE e.employee_id NOT IN (
    SELECT manager_id
    FROM lab_employees
);
```

The subquery yields `MANAGER_ID NULL` values (An, Dũng, Lan). When `NOT IN` expands into a chain of inequality comparisons, part of the condition becomes UNKNOWN; the query can **return zero rows** because NULL appears in the list.

### 9.2. Use NOT EXISTS for Non-Existence Relationships

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_employees child
    WHERE child.manager_id = e.employee_id
)
ORDER BY e.employee_id;
```

Meaning: select employees for whom **no other employee row references them as manager**. `NULL` in `CHILD.MANAGER_ID` does not match `E.EMPLOYEE_ID`, so it never breaks the anti-join logic.

If using `NOT IN`, ensure the subquery excludes NULL or the column is constrained NOT NULL:

```sql
SELECT e.employee_id, e.full_name
FROM lab_employees e
WHERE e.employee_id NOT IN (
    SELECT manager_id
    FROM lab_employees
    WHERE manager_id IS NOT NULL
);
```

For "no related record exists" problems, `NOT EXISTS` usually expresses intent more clearly and avoids subquery NULL traps.

## 10. Subqueries Returning 0, 1, or Many Rows

Subquery row counts carry distinct semantics depending on how the subquery is used.

### 10.1. Scalar Subquery

A scalar subquery used as an expression must return **at most one value**:

```sql
SELECT
    e.employee_id,
    e.full_name,
    (
        SELECT d.department_name
        FROM lab_departments d
        WHERE d.department_id = e.department_id
    ) AS department_name
FROM lab_employees e
ORDER BY e.employee_id;
```

- Subquery returns **0 rows**: the scalar value is `NULL`.
- Subquery returns **1 row**: that row's value is returned.
- Subquery returns **more than 1 row**: Oracle raises `ORA-01427: single-row subquery returns more than one row`.

Because `DEPARTMENT_ID` is the primary key of the departments table, at most one row matches above. If a subquery queries a table without a unique key, define a row-selection rule or use an appropriate `EXISTS`/join; never assume a scalar subquery picks the first row automatically.

### 10.2. SELECT INTO in PL/SQL

PL/SQL `SELECT ... INTO` has a different contract from ordinary SELECT:

- 0 rows: raises the `NO_DATA_FOUND` exception.
- 1 row: assigns the value to the variable.
- More than 1 row: raises `TOO_MANY_ROWS`.

Example:

```sql
DECLARE
    l_name lab_employees.full_name%TYPE;
BEGIN
    SELECT full_name
      INTO l_name
      FROM lab_employees
     WHERE employee_id = 999;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Employee not found');
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Condition is not unique');
END;
/
```

In this example, `EMPLOYEE_ID` is the primary key, so multiple matching rows cannot occur when the constraint is enforced. `TOO_MANY_ROWS` remains an essential exception to handle whenever `SELECT INTO` filters on a non-unique column.

Do not confuse a direct SQL `SELECT` returning 0 rows in a client with PL/SQL `SELECT INTO`: the former is valid and returns an empty set, whereas the latter demands strictly one row and raises an exception if none is found.

## 11. Diagnosing Duplicates Layer by Layer

When a report returns 20 rows while you expected 10 employees, **do not immediately slap on DISTINCT**. Find out which join increased the row count.

### Step 1 — Define the Result Grain (One-Row Unit)

Before writing the query, state it in one sentence:

- "One row represents **one employee**."
- "One row represents **one phone number**."
- "One row represents **one order**."
- "One row represents **one employee × one skill**."

Without defining the grain, you cannot tell whether a repeated row is a bug. What is the expected unique key in the output—`EMPLOYEE_ID` or `(EMPLOYEE_ID, PHONE_ID)`?

### Step 2 — Count Source Rows Before Joining

```sql
SELECT COUNT(*) AS employee_rows
FROM lab_employees;

SELECT COUNT(*) AS phone_rows
FROM lab_employee_phones;

SELECT employee_id, COUNT(*) AS phone_count
FROM lab_employee_phones
GROUP BY employee_id
ORDER BY employee_id;
```

If a source already has duplicate keys prior to joining, investigate constraints and data quality in that source table.

### Step 3 — Add Joins One by One and Count Rows

```sql
-- A: employees table only.
SELECT COUNT(*) AS rows_a
FROM lab_employees e;

-- B: add phone numbers table.
SELECT COUNT(*) AS rows_b
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id;

-- C: inspect matched pair counts per employee.
SELECT e.employee_id, COUNT(*) AS joined_rows
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
GROUP BY e.employee_id
ORDER BY e.employee_id;
```

If row count changes from 6 to 5 in the inner join, that is because employees without phones were excluded while employees with multiple phones were multiplied by their phone counts. Total rows can be smaller than employee count with an inner join even when some employees have multiple child rows.

### Step 4 — Find Keys Appearing More Than Once

```sql
SELECT e.employee_id, COUNT(*) AS occurrences
FROM lab_employees e
JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
GROUP BY e.employee_id
HAVING COUNT(*) > 1
ORDER BY e.employee_id;
```

This checks **how many times an employee key appears after the join**, not whether `LAB_EMPLOYEES` has duplicate primary keys. An employee key can repeat simply because that employee has multiple phone numbers.

### Step 5 — Check Whether Source Data Actually Has Duplicate Keys

```sql
SELECT employee_id, COUNT(*) AS occurrences
FROM lab_employees
GROUP BY employee_id
HAVING COUNT(*) > 1;
```

On a lab table with a primary key, this query must return zero rows. On a table lacking an appropriate unique constraint, this is a key step to uncover business-key duplicates.

### Step 6 — Verify Join Keys and Cardinality

Questions to ask:

- Did we join on **all columns** of a composite key?
- Is a tenant/company/partition/business-unit join condition missing?
- Is the real relationship 1-1, 1-many, or many-many?
- Did we join two independent child tables on the same parent key, creating a cross-product multiplication?
- Did a right-table filter in `WHERE` neutralize an outer join?
- Did `DISTINCT` hide differences users actually needed to see?

If a relationship key is `(COMPANY_ID, CUSTOMER_ID)` and you join only on `CUSTOMER_ID`, customers sharing the same ID in different companies collide and multiply rows.

## 12. Useful Diagnostic Patterns

### 12.1. Finding Groups with Duplicate Keys

```sql
SELECT business_key, COUNT(*) AS duplicate_count
FROM source_table
GROUP BY business_key
HAVING COUNT(*) > 1;
```

For composite keys:

```sql
SELECT company_id, customer_id, COUNT(*) AS duplicate_count
FROM source_table
GROUP BY company_id, customer_id
HAVING COUNT(*) > 1;
```

### 12.2. Counting Real Right-Side Rows in an Outer Join

```sql
SELECT parent.parent_id,
       COUNT(child.child_id) AS child_count
FROM parent_table parent
LEFT JOIN child_table child
  ON child.parent_id = parent.parent_id
GROUP BY parent.parent_id;
```

Count using a right-side column guaranteed non-NULL on every real row, typically the primary key. Avoid `COUNT(*)` when counting child rows.

### 12.3. Getting Parents With or Without Children

```sql
-- Has at least one child.
SELECT p.parent_id
FROM parent_table p
WHERE EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.parent_id = p.parent_id
);

-- Has no children.
SELECT p.parent_id
FROM parent_table p
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.parent_id = p.parent_id
);
```

### 12.4. Picking One Child Row by Rule

```sql
SELECT parent_id, child_id, created_at
FROM (
    SELECT c.*,
           ROW_NUMBER() OVER (
               PARTITION BY parent_id
               ORDER BY created_at DESC NULLS LAST, child_id DESC
           ) AS rn
    FROM child_table c
)
WHERE rn = 1;
```

`CHILD_ID` acts as a tie-breaker for deterministic selection when two rows share the same `CREATED_AT`. Without a secondary key, Oracle can pick unpredictably among tied rows.

## 13. Common Mistakes and How to Read Them Properly

| Symptom | Common misinterpretation | Correct diagnosis |
| --- | --- | --- |
| SQL returns zero rows | "The table lost data" | Check source, PDB/schema, privileges, and filter conditions |
| COUNT returns 0 yet client gets one row | "The query returned a NULL record" | Aggregate without GROUP BY returns one result row with COUNT = 0 |
| SUM returns NULL | "Zero rows returned" | Check row count; an aggregate can return one row with SUM NULL |
| Column displays `(null)` | "The record does not exist" | The row exists, but that attribute has no recorded value |
| `WHERE col = NULL` matches nothing | "Oracle doesn't support NULL" | Use `IS NULL` / `IS NOT NULL` |
| `NOT IN` returns zero rows | "No matching records exist" | Check for NULLs in the subquery; consider `NOT EXISTS` |
| LEFT JOIN drops parents without children | "LEFT JOIN is broken" | A right-table condition in WHERE eliminated NULL-padded rows |
| COUNT(*) = 1 for a childless parent | "There is one child record" | The NULL-padded outer-join row is still counted by COUNT(*) |
| Parent ID repeats after join | "The parent table has duplicates" | Check child row counts and the result set's grain |
| SUM of amounts doubles after join | "Oracle's SUM is wrong" | Another child table multiplied amount rows; pre-aggregate each source before joining |
| DISTINCT makes row count look right | "Data is fixed" | DISTINCT may just be masking a join/cardinality bug |
| Scalar subquery raises ORA-01427 | "Oracle picked the wrong row" | The subquery returned more than one row where a single value was expected |
| PL/SQL SELECT INTO raises NO_DATA_FOUND | "SQL SELECT always errors on 0 rows" | Plain SELECT returns an empty set; SELECT INTO requires strictly one row |

## 14. Practice Exercises

Run each query on the lab data, predict the result first, and explain using row counts and values—never just "right" or "wrong."

### Exercise 1 — Distinguishing Empty Result Sets and Aggregates

Compare:

```sql
SELECT employee_id
FROM lab_employees
WHERE employee_id = 999;

SELECT COUNT(*) AS row_count
FROM lab_employees
WHERE employee_id = 999;

SELECT SUM(salary) AS salary_sum
FROM lab_employees
WHERE employee_id = 999;
```

Answer: which returns 0 rows, which returns one row with 0, and which returns one row with NULL? Why?

### Exercise 2 — NULL and Negated Conditions

Compare:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE NOT (salary > 2000);

SELECT employee_id, full_name
FROM lab_employees
WHERE salary <= 2000 OR salary IS NULL;
```

Explain why Chi appears in the second query but not in the first.

### Exercise 3 — LEFT JOIN and COUNT

Write a query showing every department, including department 40, with its employee count. Test `COUNT(*)` and `COUNT(e.employee_id)` in turn. Explain the difference.

### Exercise 4 — Counting Phones Without Multiplying Employees

Write two queries:

1. Join employees with phones and show employee An appearing in two rows.
2. Use `GROUP BY` on the phones table before joining to return strictly one row per employee along with their phone count.

Explain the **grain** of each result.

### Exercise 5 — NOT IN and NOT EXISTS

Run the `NOT IN (SELECT manager_id FROM lab_employees)` query and the `NOT EXISTS` query from section 9. Record the results. Then add `WHERE manager_id IS NOT NULL` to the NOT IN subquery and compare.

Explain the role of UNKNOWN in negated membership checks.

### Exercise 6 — Multiplication When Joining Two Child Tables

Create an additional lab table:

```sql
CREATE TABLE lab_employee_skills (
    skill_id    NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL
        REFERENCES lab_employees(employee_id),
    skill_name  VARCHAR2(60 CHAR) NOT NULL
);

INSERT INTO lab_employee_skills VALUES (201, 1, 'SQL');
INSERT INTO lab_employee_skills VALUES (202, 1, 'PLSQL');
INSERT INTO lab_employee_skills VALUES (203, 1, 'Java');
COMMIT;
```

Join `LAB_EMPLOYEES`, `LAB_EMPLOYEE_PHONES`, and `LAB_EMPLOYEE_SKILLS` for employee 1. Confirm the output has 6 combinations. Then write separate CTEs counting phones and skills, and join both count sets to get **one row per employee**.

### Exercise 7 — Analyzing a Buggy Report

A report needs the total phone count and skill count per employee, yet the query was written as:

```sql
SELECT
    e.employee_id,
    COUNT(p.phone_id) AS phone_count,
    COUNT(s.skill_id) AS skill_count
FROM lab_employees e
LEFT JOIN lab_employee_phones p
  ON p.employee_id = e.employee_id
LEFT JOIN lab_employee_skills s
  ON s.employee_id = e.employee_id
GROUP BY e.employee_id;
```

For employee 1, two phones and three skills multiply each side across the combinations. Fix it using two separate pre-aggregating CTEs before joining. Do not rely on `COUNT(DISTINCT ...)` as a default band-aid if you might also need sums or other detail columns.

## 15. Cleaning Up Lab Data

Run only in the practice schema you created:

```sql
DROP TABLE lab_employee_skills PURGE;
DROP TABLE lab_lob_state PURGE;
DROP TABLE lab_employee_phones PURGE;
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
```

If you did not create `LAB_EMPLOYEE_SKILLS` or `LAB_LOB_STATE`, skip the corresponding statements. Drop child tables before parent tables due to foreign key references; `PURGE` bypasses the recycle bin. Never run these commands on someone else's tables or data that must be kept.

## Summary

When reading an Oracle query result, ask three separate questions:

1. **How many rows?** Zero rows is an empty result set; one row with NULL values is still one row.
2. **What does NULL mean here?** It creates three-valued logic affecting conditions, aggregates, joins, subqueries, and UI display. NULL differs from 0, the literal string `"NULL"`, and empty LOBs.
3. **What does one result row represent?** A 1-to-many join can legitimately repeat a parent key; joining multiple independent child tables multiplies rows by their product; apply DISTINCT only after understanding the grain and goal.

For NULL filtering, use `IS NULL`/`IS NOT NULL`; for existence/non-existence checks, consider `EXISTS`/`NOT EXISTS`; for child counts, aggregate before joining; for picking one prioritized child row, use `ROW_NUMBER` with a deterministic order. These address root causes semantically rather than merely making output look less duplicated.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — Nulls (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — NULL semantics and comparisons.
- [Oracle Database SQL Language Reference — Aggregate Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html) — how COUNT, SUM, AVG, and aggregates handle NULL.
- [Oracle Database SQL Language Reference — Joins (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html) — inner/outer joins and join conditions.
- [Oracle Database SQL Language Reference — EXISTS Condition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html) — existence conditions.
- [Oracle Database SQL Language Reference — IN Condition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html) — IN/NOT IN semantics.
- [Oracle Database PL/SQL Language Reference — SELECT INTO Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/SELECT-INTO-statement.html) — NO_DATA_FOUND and TOO_MANY_ROWS.

When working with real data, verify your exact Oracle release, table constraints, relationship cardinality, and business rules. A query returning many rows can be completely right; what matters is that every row carries the exact meaning the application needs.
