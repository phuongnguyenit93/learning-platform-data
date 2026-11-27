# LEFT, RIGHT, and FULL OUTER JOIN

In Oracle Database, an **outer join** lets you combine data from two sources while preserving rows that do not find a matching partner on the other side. This is an important difference from **INNER JOIN**, which returns only pairs of rows satisfying the join condition.

The three basic types of outer join:

- **LEFT OUTER JOIN:** keeps all rows from the left source; if no matching row exists on the right, the right-side columns are padded with NULL.
- **RIGHT OUTER JOIN:** keeps all rows from the right source; if no matching row exists on the left, the left-side columns are padded with NULL.
- **FULL OUTER JOIN:** keeps all rows from both sources; unmatched rows are padded with NULL on the opposite side.

The `OUTER` keyword is optional: `LEFT JOIN`, `RIGHT JOIN`, and `FULL JOIN` have the same respective meanings. In application SQL, use ANSI JOIN syntax with `ON` or `USING` to express table relationships clearly.

This lesson focuses on reading outer join results accurately—especially **NULL-extended rows**, placement of `ON` vs `WHERE` conditions, finding unmatched rows, and avoiding miscounting or row duplication after joining.

## 1. How do INNER JOIN and OUTER JOIN differ?

Suppose there are two tables:

```text
DEPARTMENTS                         EMPLOYEES
  DEPARTMENT_ID (PK) <------------+   EMPLOYEE_ID (PK)
  DEPARTMENT_NAME                 +-- DEPARTMENT_ID (FK, nullable)
                                      FULL_NAME
```

With `INNER JOIN`, only pairs of rows with matching department keys appear. With `LEFT JOIN`, every department still appears even if it has no employees. With `FULL OUTER JOIN`, both departments without employees and employees without an assigned department are preserved.

| JOIN Type | Keep all left rows? | Keep all right rows? | Unmatched rows |
| --- | :---: | :---: | --- |
| `INNER JOIN` | No | No | Excluded |
| `LEFT OUTER JOIN` | Yes | No | Padded with NULL on the right |
| `RIGHT OUTER JOIN` | No | Yes | Padded with NULL on the left |
| `FULL OUTER JOIN` | Yes | Yes | Padded with NULL on the unmatched side |

Conceptual diagram:

```text
LEFT OUTER JOIN
  All of A + matching part of B

RIGHT OUTER JOIN
  Matching part of A + all of B

FULL OUTER JOIN
  All of A + all of B
  (paired when the ON condition evaluates to TRUE)
```

**An outer join does not create missing business data.** Oracle simply produces a result row whose unmatched-side columns contain NULL to represent that no partner row was found.

## 2. Creating Practice Data

The examples use a dedicated lab schema. Run DDL in a schema you own with `CREATE TABLE` privileges and tablespace quota. Do not run create/drop table statements on a live application schema.

### 2.1. Create the two tables

```sql
CREATE TABLE lab_departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER,
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    salary        NUMBER(12, 2),
    CONSTRAINT fk_lab_employees_department
        FOREIGN KEY (department_id)
        REFERENCES lab_departments (department_id),
    CONSTRAINT ck_lab_employees_active
        CHECK (active_flag IN ('Y', 'N'))
);
```

### 2.2. Insert data

```sql
INSERT INTO lab_departments VALUES (10, 'Engineering');
INSERT INTO lab_departments VALUES (20, 'Sales');
INSERT INTO lab_departments VALUES (30, 'HR');
INSERT INTO lab_departments VALUES (40, 'Legal');

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (1, 'An', 10, 'Y', 5000);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (2, 'Binh', 10, 'Y', 3000);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (3, 'Chi', 20, 'N', 2800);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (4, 'Dung', NULL, 'Y', 4200);

INSERT INTO lab_employees
    (employee_id, full_name, department_id, active_flag, salary)
VALUES (5, 'Ha', 30, 'Y', NULL);

COMMIT;
```

The dataset includes key cases to observe:

| Department | Employees | Status |
| --- | --- | --- |
| Engineering (10) | An, Binh | Two employees |
| Sales (20) | Chi | Inactive employee |
| HR (30) | Ha | Has employee, salary NULL |
| Legal (40) | None | Empty department |
| No department | Dung | Employee with `DEPARTMENT_ID NULL` |

Department 40 lets you observe unmatched rows on the employee side. Dung lets you observe unmatched rows on the department side. These are the two opposite directions of an outer join.

## 3. LEFT OUTER JOIN: Keeping All Left-Side Rows

Syntax:

```sql
SELECT select_list
FROM left_table l
LEFT [OUTER] JOIN right_table r
  ON join_condition;
```

Example: retrieve all departments along with employee details if any:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name,
    e.active_flag
FROM lab_departments d
LEFT OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id, e.employee_id;
```

Logical result:

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_ID | FULL_NAME | ACTIVE_FLAG |
| ---: | --- | ---: | --- | :---: |
| 10 | Engineering | 1 | An | Y |
| 10 | Engineering | 2 | Binh | Y |
| 20 | Sales | 3 | Chi | N |
| 30 | HR | 5 | Ha | Y |
| 40 | Legal | NULL | NULL | NULL |

Department 40 still gets a result row. The `E.*` columns carry NULL because no matching employee was found. Dung does not appear because the left table is `LAB_DEPARTMENTS`; `LEFT JOIN` does not mean "keep all rows from both tables."

### 3.1. What is a NULL-extended row?

For department 40, Oracle generates a result row like:

```text
D.DEPARTMENT_ID   = 40
D.DEPARTMENT_NAME = 'Legal'
E.EMPLOYEE_ID     = NULL
E.FULL_NAME       = NULL
E.ACTIVE_FLAG     = NULL
E.SALARY          = NULL
```

This is not an employee row stored in `LAB_EMPLOYEES`. It is a row synthesized in the outer join result to preserve the department row.

Therefore, when counting employees, do not blindly use `COUNT(*)`:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS employee_count
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

For department 40:

- `COUNT(*) = 1`: the NULL-extended row is still a result row.
- `COUNT(e.employee_id) = 0`: the employee primary key is NULL on the padded row, so it is not counted.

When counting child rows, count a child-side column that is **non-NULL on every real row**, typically the primary key.

### 3.2. Keeping all departments while joining only active employees

Requirement: display every department, but join only employees with `ACTIVE_FLAG = 'Y'`.

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name,
    e.active_flag
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

The result still includes department 40. Sales (20) is also preserved, while Chi is excluded from matching because she is inactive; since no active employee matches, the `E.*` columns for department 20 are padded with NULL.

The condition `E.ACTIVE_FLAG = 'Y'` is placed in `ON` because it specifies **which right-side rows qualify to match** a department row.

## 4. RIGHT OUTER JOIN: Keeping All Right-Side Rows

Syntax:

```sql
SELECT select_list
FROM left_table l
RIGHT [OUTER] JOIN right_table r
  ON join_condition;
```

To keep all employees, including those without a department:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
RIGHT OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY e.employee_id;
```

The result includes An, Binh, Chi, Dung, and Ha. Dung appears with NULL department columns because Dung's `DEPARTMENT_ID` is unassigned.

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_ID | FULL_NAME |
| ---: | --- | ---: | --- |
| 10 | Engineering | 1 | An |
| 10 | Engineering | 2 | Binh |
| 20 | Sales | 3 | Chi |
| NULL | NULL | 4 | Dung |
| 30 | HR | 5 | Ha |

### 4.1. RIGHT JOIN can be rewritten as LEFT JOIN

The following two queries are equivalent in result set:

```sql
-- RIGHT JOIN
SELECT d.department_id, e.employee_id, e.full_name
FROM lab_departments d
RIGHT JOIN lab_employees e
  ON e.department_id = d.department_id;

-- Swap table order and use LEFT JOIN
SELECT d.department_id, e.employee_id, e.full_name
FROM lab_employees e
LEFT JOIN lab_departments d
  ON d.department_id = e.department_id;
```

Many development teams prefer standardizing on `LEFT JOIN` because reading "keep the left table" is more consistent. `RIGHT JOIN` remains valid and sometimes reads naturally when the source to be preserved is already on the right in a fixed query structure.

**Do not swap the two tables' positions without also reversing the outer join direction.** `A LEFT JOIN B` and `B LEFT JOIN A` are not equivalent; the second must be `B RIGHT JOIN A` to preserve the same side of data.

## 5. FULL OUTER JOIN: Keeping All Rows from Both Sides

Syntax:

```sql
SELECT select_list
FROM left_table l
FULL [OUTER] JOIN right_table r
  ON join_condition;
```

Example:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
FULL OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY d.department_id NULLS LAST, e.employee_id;
```

The result contains:

- All departments, including Legal with no employees.
- All employees, including Dung with no department.
- Department/employee pairs matched on `DEPARTMENT_ID`.

Illustrative result:

| DEPARTMENT_ID | DEPARTMENT_NAME | EMPLOYEE_ID | FULL_NAME |
| ---: | --- | ---: | --- |
| 10 | Engineering | 1 | An |
| 10 | Engineering | 2 | Binh |
| 20 | Sales | 3 | Chi |
| 30 | HR | 5 | Ha |
| 40 | Legal | NULL | NULL |
| NULL | NULL | 4 | Dung |

An unmatched row on the **left** has NULL right-side columns; an unmatched row on the **right** has NULL left-side columns. FULL JOIN does not discard any row merely for lacking a match.

### 5.1. NULLs in the join key do not match NULLs

The condition:

```sql
ON e.department_id = d.department_id
```

does not treat two NULL values as equal. In SQL, `NULL = NULL` evaluates to UNKNOWN, not TRUE. Therefore, if both tables have a row with `DEPARTMENT_ID NULL`, those two rows **do not pair up**. FULL JOIN keeps each row separately as unmatched rows.

If business logic genuinely requires treating two NULLs as the same group, design an explicit matching condition. Do not add `OR (a.key IS NULL AND b.key IS NULL)` casually, because multiple NULL rows on both sides can create a many-to-many pairing and multiply rows. Normally, relational keys should be non-NULL identifiers; NULL indicates no linked key yet.

### 5.2. Choosing a display key for FULL JOIN

In a FULL JOIN, the left-side key column can be NULL for rows existing only on the right, and the right-side key column can be NULL for rows existing only on the left. To display a single unified key column:

```sql
SELECT
    COALESCE(d.department_id, e.department_id) AS department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
FULL OUTER JOIN lab_employees e
  ON e.department_id = d.department_id
ORDER BY department_id NULLS LAST, e.employee_id;
```

`COALESCE` returns the first non-NULL value. For matched rows, both keys are identical; for a department without employees, the left key is taken; for an unassigned employee, both keys are NULL in this example. Thus `DEPARTMENT_ID` remains NULL for Dung, accurately reflecting that Dung has no department.

If you use `USING (department_id)`, Oracle provides a single coalesced join column in the select list instead of two separate key columns. However, `USING` has its own column referencing rules; do not prefix the join column with a table alias in the select list. With FULL JOIN, understand clearly what common key value is returned and use explicit `COALESCE` if you want to state the intent clearly.

## 6. ON vs WHERE: The Most Important Distinction in OUTER JOIN

`ON` determines which row pairs match during the JOIN. `WHERE` filters the rows of the query block after the logical join is formed. With INNER JOIN, many conditions can move between ON and WHERE without changing the result; with OUTER JOIN, moving a condition can alter which rows are preserved.

### 6.1. Putting a right-table filter in WHERE can turn a LEFT JOIN into an INNER JOIN

Query:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Legal has no employees, so its NULL-extended row has `E.ACTIVE_FLAG = NULL`. The condition `NULL = 'Y'` is UNKNOWN; WHERE keeps only TRUE, so department 40 is eliminated.

Sales has only Chi, who is inactive; Chi's row is eliminated by WHERE. Because a row did match in ON, Oracle does not synthesize a replacement NULL-extended row for department 20. Neither of those two departments is preserved in the result.

If the requirement is **every department, along with active employees if any**, move the condition into ON:

```sql
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Now both department 20 and department 40 remain, with NULL employee columns. The difference is not a syntax trick; it reflects two distinct business requirements:

- `WHERE e.active_flag = 'Y'`: return only result rows that have an active employee.
- `ON ... AND e.active_flag = 'Y'`: keep every department, but match only active employees.

### 6.2. Adding OR e.employee_id IS NULL does not replace a condition in ON

A common workaround looks like:

```sql
WHERE e.active_flag = 'Y'
   OR e.employee_id IS NULL
```

This keeps departments that truly have zero employees, but **does not keep Sales (20)** in the lab dataset: Chi matches department 20 in ON, and is then filtered out by WHERE because she is inactive; no second NULL-extended row is generated. Therefore, an OR condition cannot substitute for filtering the right table in ON when you need to preserve parents whose only children fail the filter.

### 6.3. Conditions on the preserved table can go in WHERE

If you want to show only departments with ID 20 or higher, that is a filter on the left side:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE d.department_id >= 20
ORDER BY d.department_id, e.employee_id;
```

This properly excludes department 10 while still keeping department 40. There is no rule that "every condition in a LEFT JOIN must be in ON"; placement depends on **which rows** the condition applies to and which rows must be preserved.

## 7. ON Conditions in FULL OUTER JOIN

With FULL JOIN, both sides are preserved. The ON condition determines which rows pair up; unmatched rows still appear individually.

### 7.1. FULL JOIN across two datasets with differing keys

A practical example is reconciling budget plan vs actual figures by department. Create two independent lab tables:

```sql
CREATE TABLE lab_budget_plan (
    department_id NUMBER PRIMARY KEY,
    planned_amount NUMBER(12, 2)
);

CREATE TABLE lab_budget_actual (
    department_id NUMBER PRIMARY KEY,
    actual_amount NUMBER(12, 2)
);

INSERT INTO lab_budget_plan VALUES (10, 10000);
INSERT INTO lab_budget_plan VALUES (20, 15000);
INSERT INTO lab_budget_plan VALUES (30, 8000);

INSERT INTO lab_budget_actual VALUES (10, 9500);
INSERT INTO lab_budget_actual VALUES (30, 9000);
INSERT INTO lab_budget_actual VALUES (40, 7000);

COMMIT;
```

FULL JOIN reveals both plan-only codes and actual-only codes:

```sql
SELECT
    COALESCE(p.department_id, a.department_id) AS department_id,
    p.planned_amount,
    a.actual_amount,
    CASE
        WHEN p.department_id IS NULL THEN 'ACTUAL ONLY'
        WHEN a.department_id IS NULL THEN 'PLAN ONLY'
        ELSE 'BOTH'
    END AS match_state
FROM lab_budget_plan p
FULL OUTER JOIN lab_budget_actual a
  ON a.department_id = p.department_id
ORDER BY department_id;
```

Result:

| DEPARTMENT_ID | PLANNED_AMOUNT | ACTUAL_AMOUNT | MATCH_STATE |
| ---: | ---: | ---: | --- |
| 10 | 10000 | 9500 | BOTH |
| 20 | 15000 | NULL | PLAN ONLY |
| 30 | 8000 | 9000 | BOTH |
| 40 | NULL | 7000 | ACTUAL ONLY |

This is an ideal use case for FULL OUTER JOIN: **reconciling two independent sources** to detect keys present in only one source.

### 7.2. Filters can drop unmatched rows

If you write:

```sql
SELECT
    COALESCE(p.department_id, a.department_id) AS department_id,
    p.planned_amount,
    a.actual_amount
FROM lab_budget_plan p
FULL OUTER JOIN lab_budget_actual a
  ON a.department_id = p.department_id
WHERE p.planned_amount > 0;
```

The actual-only row (code 40) has `P.PLANNED_AMOUNT NULL`, so WHERE drops it. The query no longer keeps all rows from both sides even though it uses FULL JOIN.

If the goal is to keep all codes while matching only positive planned amounts, design the condition in ON or filter the source before the FULL JOIN:

```sql
SELECT
    COALESCE(p.department_id, a.department_id) AS department_id,
    p.planned_amount,
    a.actual_amount
FROM (
    SELECT department_id, planned_amount
    FROM lab_budget_plan
    WHERE planned_amount > 0
) p
FULL OUTER JOIN lab_budget_actual a
  ON a.department_id = p.department_id
ORDER BY department_id;
```

Here the plan source is filtered before joining; all actual rows remain preserved. If you want to keep plan rows with NULL amounts as well without letting them match, express the condition explicitly in ON and verify the expected result. Filter placement must always follow data semantics.

## 8. Finding Rows Without a Partner

Outer joins are often used to find rows that have no related record on the opposite side, also known as the **anti-join pattern**.

### 8.1. Departments without employees

```sql
SELECT
    d.department_id,
    d.department_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.employee_id IS NULL
ORDER BY d.department_id;
```

The result is Legal (40). The check `E.EMPLOYEE_ID IS NULL` tests the right-side primary key, which is never NULL on a real employee row. Thus NULL indicates no matching employee row exists.

### 8.2. Employees without a valid department

```sql
SELECT
    e.employee_id,
    e.full_name
FROM lab_employees e
LEFT JOIN lab_departments d
  ON d.department_id = e.department_id
WHERE d.department_id IS NULL
ORDER BY e.employee_id;
```

With the lab data, the result includes Dung. The check tests the primary key `D.DEPARTMENT_ID` of the departments table; if no department matches, this key is NULL in the outer join result.

### 8.3. NOT EXISTS often expresses the intent more clearly

The following two queries are generally equivalent for finding departments without employees:

```sql
-- LEFT JOIN + right-side key check.
SELECT d.department_id, d.department_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.employee_id IS NULL;

-- NOT EXISTS.
SELECT d.department_id, d.department_name
FROM lab_departments d
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_employees e
    WHERE e.department_id = d.department_id
);
```

`NOT EXISTS` directly expresses "no matching child row exists" and avoids introducing NULL-extended columns into the result set. The Oracle Optimizer can transform these patterns into an anti-join depending on the query and statistics. There is no universal rule that one form is always faster; measure on real data.

### 8.4. Do not check a right-side column that can be NULL in real data

If the child table has a nullable column such as `E.SALARY`, the condition:

```sql
WHERE e.salary IS NULL
```

cannot distinguish between:

- No matching employee (NULL-extended row).
- A real employee whose salary is not yet recorded.

Always test a right-side column **guaranteed to be NOT NULL**, usually the primary key:

```sql
WHERE e.employee_id IS NULL
```

This is a critical rule when using an outer join to find missing data.

## 9. Joining Multiple Tables and the Risk of Row Multiplication

Outer joins still follow relationship cardinality. If a department has three employees, `LEFT JOIN`ing departments to employees produces three rows for that department. That is not an error; each row represents one department/employee pair.

Problems arise when joining multiple independent child tables.

Suppose an employee has two phone numbers and three certificates. Joining both child tables on `EMPLOYEE_ID` yields:

```text
1 EMPLOYEE
   |
   +--- 2 PHONE rows
   |
   +--- 3 CERTIFICATE rows

JOIN both child tables:
   2 x 3 = 6 rows
```

If `COUNT(phone_id)` or `SUM(phone_fee)` is then computed over the six rows, each phone is repeated three times. The solution is to aggregate each child source to one row per employee before joining, or join only the child table whose details are actually needed.

Example pattern:

```sql
WITH phone_counts AS (
    SELECT employee_id, COUNT(*) AS phone_count
    FROM lab_employee_phones
    GROUP BY employee_id
),
certificate_counts AS (
    SELECT employee_id, COUNT(*) AS certificate_count
    FROM lab_employee_certificates
    GROUP BY employee_id
)
SELECT
    e.employee_id,
    e.full_name,
    NVL(p.phone_count, 0) AS phone_count,
    NVL(c.certificate_count, 0) AS certificate_count
FROM lab_employees e
LEFT JOIN phone_counts p
  ON p.employee_id = e.employee_id
LEFT JOIN certificate_counts c
  ON c.employee_id = e.employee_id
ORDER BY e.employee_id;
```

Each CTE has at most one row per employee, so the final joins do not multiply phone counts by certificate counts. `NVL(...,0)` is appropriate here because zero child rows means a count of 0; if aggregating a nullable business value that means "unknown," do not apply the same substitution rule.

## 10. USING, ON, and NATURAL JOIN

### 10.1. USING when both tables share the same join column name

If both tables have `DEPARTMENT_ID`, you can write:

```sql
SELECT
    department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
USING (department_id);
```

`USING` is concise when joining on one or more identically named columns. The join column is treated as a shared column in the select list; do not write `D.DEPARTMENT_ID` or `E.DEPARTMENT_ID` to reference it within the same `USING` context. With `ON`, you can reference each side individually.

For FULL OUTER JOIN, if you need to show key values clearly from both sides, `COALESCE(d.department_id, e.department_id)` with `ON` syntax is usually easier to read and control.

### 10.2. Be cautious with NATURAL JOIN

`NATURAL JOIN` automatically joins on all identically named columns between two tables:

```sql
SELECT *
FROM lab_departments
NATURAL LEFT JOIN lab_employees;
```

The lab example happens to share only `DEPARTMENT_ID`, but a real schema may add identically named columns in the future. When that happens, the meaning of NATURAL JOIN can change silently without the SQL changing. In applications requiring explicit control over relationships, prefer `JOIN ... ON ...`.

## 11. Oracle Legacy Outer Join Operator (+)

In older Oracle systems, you may see the syntax:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d, lab_employees e
WHERE d.department_id = e.department_id(+);
```

`(+)` is Oracle's legacy outer join operator; the symbol is placed on the table side that may lack rows in order to preserve rows from the opposite side. In the example above, it is equivalent to a LEFT OUTER JOIN from departments to employees.

For new code, use ANSI JOIN:

```sql
SELECT d.department_id, d.department_name, e.employee_id
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id;
```

The `(+)` syntax has many restrictions and special rules, especially with multiple join conditions, multiple tables, or complex outer joins. Do not mix `(+)` syntax with ANSI JOIN syntax in the same query block. When maintaining legacy SQL, read the `(+)` conditions carefully and verify equivalence before converting; never just strip the plus signs without reviewing the logic.

## 12. FULL OUTER JOIN and the UNION of Two LEFT JOINs

In modern Oracle versions, `FULL OUTER JOIN` is the direct way to preserve all rows from both sides. In some legacy situations or when separate control over each branch is needed, it can be emulated with two LEFT JOINs and `UNION ALL`, provided the overlap is excluded from the second branch.

Example emulating a full join of the two budget tables:

```sql
-- Matched pairs and rows present only in PLAN.
SELECT
    p.department_id,
    p.planned_amount,
    a.actual_amount
FROM lab_budget_plan p
LEFT JOIN lab_budget_actual a
  ON a.department_id = p.department_id

UNION ALL

-- Rows present only in ACTUAL.
SELECT
    a.department_id,
    p.planned_amount,
    a.actual_amount
FROM lab_budget_actual a
LEFT JOIN lab_budget_plan p
  ON p.department_id = a.department_id
WHERE p.department_id IS NULL;
```

Because `DEPARTMENT_ID` is a primary key and non-NULL in both tables, `P.DEPARTMENT_ID IS NULL` in the second branch identifies actual rows without a plan. `UNION ALL` preserves rows as-is without the deduplication overhead of `UNION`.

This is only an emulation technique. If the join key is nullable or non-unique, unmatched detection must be designed on a non-NULL key and cardinality handled carefully. Never replace FULL JOIN with a UNION of two LEFT JOINs without proving that the two branches cover the exact set of matched pairs and unmatched rows.

## 13. Logical Order and Execution Plan

To reason about outer join results, use this logical model:

1. Read rows from the sources in FROM.
2. Identify matching row pairs according to the ON condition.
3. For LEFT/RIGHT/FULL JOIN, synthesize NULL-extended rows for preserved rows that have no partner.
4. Apply WHERE to the resulting query block rows.
5. Execute GROUP BY/HAVING, SELECT, ORDER BY, and row limiting according to their SQL semantics.

This is a **reasoning model**, not a mandatory physical execution order. The Oracle Optimizer may reorder table access, choose nested loops/hash join/merge join, and push predicates whenever transformations preserve semantics.

You can inspect the estimated plan in the lab:

```sql
EXPLAIN PLAN FOR
SELECT
    d.department_id,
    d.department_name,
    e.employee_id,
    e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y';

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows an estimated plan. When analyzing production SQL, examine the actual cursor plan and runtime statistics according to your privileges rather than judging performance solely from SQL line count or an estimated plan.

## 14. Common Pitfalls

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| LEFT JOIN but empty departments disappear | Right-side condition placed in WHERE | Place matching filter condition in ON |
| LEFT JOIN still drops departments with only inactive employees | ON matches inactive employees, then WHERE drops them | Filter active status in ON so NULL-extended rows are generated when no active employee exists |
| COUNT(*) equals 1 for departments with no employees | Counting the NULL-extended row | Count the employee primary key with COUNT(e.employee_id) |
| Using WHERE e.salary IS NULL to find departments with no employees | Real employees can also have NULL salary | Check a right-side NOT NULL key column |
| RIGHT JOIN drops rows from the table meant to be kept | Table placed on wrong side or join swapped without flipping LEFT/RIGHT | Identify the preserved side before writing |
| FULL JOIN does not pair two NULL keys | NULL = NULL evaluates to UNKNOWN | Use meaningful linking keys; handle NULL matching only when explicitly required by business rules |
| FULL JOIN returns two rows with NULL keys | One NULL row in each source does not match automatically | Check each source; do not assume two NULLs represent the same entity |
| FULL JOIN followed by WHERE on one side drops unmatched rows | WHERE eliminates rows where that side's column is NULL | Pre-filter the source or place match condition in ON as required |
| Parent key repeats after join | 1-to-many relationship | Determine grain; aggregate or use EXISTS if child details are not needed |
| SUM increases after joining two child tables | Join produces the Cartesian product of independent child rows | Aggregate each child source before joining |
| DISTINCT "removes duplicates" but totals remain wrong | DISTINCT masks the symptom without fixing cardinality | Investigate join keys and grain first |
| NOT EXISTS/anti-join returns unexpected results | Incorrect correlation condition or wrong nullable key | Check correlation predicates and key columns |
| NATURAL JOIN changes results after adding a column | Automatically joins on all shared column names | Use explicit ON conditions |
| Converting (+) to ANSI JOIN yields different results | Misplaced conditions or missed legacy outer join rules | Convert one query block at a time and compare results |

## 15. Practice Exercises

Use `LAB_DEPARTMENTS` and `LAB_EMPLOYEES` from section 2. Predict the output before running the SQL.

### Exercise 1 — LEFT JOIN

Write a query returning all departments and their corresponding employees, including departments without employees. Identify which department has NULL values for `EMPLOYEE_ID` and `FULL_NAME`.

### Exercise 2 — RIGHT JOIN

Write a query preserving all employees, including those not assigned to a department. Then rewrite the query by swapping the table order and using LEFT JOIN. Compare the result sets.

### Exercise 3 — FULL OUTER JOIN

Write a query preserving all departments and all employees. Explain why department 40 and employee Dung each appear in separate rows.

### Exercise 4 — ON vs WHERE

Write two LEFT JOIN queries:

1. `ACTIVE_FLAG = 'Y'` in ON.
2. `ACTIVE_FLAG = 'Y'` in WHERE.

Compare department 20 and department 40. Explain why an OR `EMPLOYEE_ID IS NULL` condition fails to preserve department 20 when it only has an inactive employee.

### Exercise 5 — Counting employees

Add `COUNT(*)` and `COUNT(e.employee_id)` to the department report. Determine the values for department 40 and explain why.

### Exercise 6 — Finding departments without employees

Write two versions: LEFT JOIN + `WHERE e.employee_id IS NULL`, and `NOT EXISTS`. Confirm both find the Legal department.

### Exercise 7 — Reconciling plan vs actual

Create the two budget tables from section 7.1, run FULL OUTER JOIN, and classify rows into:

- Both plan and actual present.
- Plan only.
- Actual only.

Then add a WHERE condition on `PLANNED_AMOUNT` and observe the actual-only row disappear.

### Exercise 8 — Cardinality

Suppose an employee has two phone numbers and three certificates. Write a join with both child tables, predict the row count, and then aggregate each child table before joining to return one row per employee.

### Exercise 9 — Designing a reconciliation query

A system has two customer data sources, each with `CUSTOMER_CODE`, `FULL_NAME`, and `EMAIL`. Write a FULL OUTER JOIN on CUSTOMER_CODE to find:

- Codes present in both sources.
- Codes present only in source A.
- Codes present only in source B.
- Codes present in both but with differing emails.

Explain how to handle cases where CUSTOMER_CODE is NULL or non-unique; do not assume a FULL JOIN automatically fixes missing key data.

## 16. Cleaning Up Practice Data

Run the following statements only in the lab schema you created and once you have completed the exercises:

```sql
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
DROP TABLE lab_budget_plan PURGE;
DROP TABLE lab_budget_actual PURGE;
```

If you did not create the budget tables, skip the corresponding two DROP statements. Drop child tables before parent tables due to foreign keys. `PURGE` bypasses the recycle bin; do not use it on recoverable data or tables you do not own.

## Summary

`LEFT OUTER JOIN` preserves all left-side rows, `RIGHT OUTER JOIN` preserves all right-side rows, and `FULL OUTER JOIN` preserves both sides. When no matching partner exists, Oracle pads the unmatched side's columns with NULL. NULL-extended rows belong to the **JOIN result**, not as real records inserted into the table.

The `ON` clause determines which rows match; `WHERE` filters the result after the logical join. With outer joins, moving conditions between these two clauses can drop rows that should be preserved. When counting child rows, count the child primary key instead of `COUNT(*)`. When results multiply, check the grain and cardinality of each relationship; aggregate each child source before joining if the target is one row per parent entity.

Outer joins are especially useful for reports that must retain unlinked entities, reconciling two sources, locating missing data, and checking data quality. Choosing the right join direction and writing explicit conditions ensures results accurately reflect business requirements.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — Joins (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Joins.html) — inner/outer join syntax, ON, USING, and related rules.
- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — query block structure, FROM, WHERE, and SELECT clauses.
- [Oracle Database SQL Language Reference — EXISTS Condition (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html) — existence conditions and correlated query patterns.
- [Oracle Database SQL Language Reference — Nulls (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — NULL logic in join and filter conditions.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — join methods, optimizer, and execution plans.

For Oracle releases other than 19c, consult the version-specific documentation regarding JOIN syntax and restrictions of the legacy `(+)` outer join operator before migrating production SQL.
