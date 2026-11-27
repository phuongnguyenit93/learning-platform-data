# SELECT Structure and Logical Clause Processing Order

In Oracle Database, `SELECT` is the statement used to **query data**. A `SELECT` statement can simply read a few columns from a single table, or it can join multiple tables, filter rows, group data, compute totals, eliminate duplicate results, sort, and retrieve a portion of the results for pagination.

What often confuses beginners is that **the order in which SQL is written is not the logical processing order of its clauses**. For example, we write `SELECT` at the beginning of the statement, yet we must know where the data comes from (`FROM`) and which rows remain after `WHERE` before determining the final output of the `SELECT` list. This explains many common errors such as "why can't an alias just declared in `SELECT` be used in `WHERE`?", "why is `HAVING` different from `WHERE`?", or "why doesn't `ROWNUM` return the right top 3 after sorting?".

Lesson objectives:

- Read common `SELECT` structures in Oracle, including optional clauses.
- Interpret the **logical processing order** to predict the row set at each stage.
- Choose the right `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, and `FETCH FIRST` clauses for a given requirement.
- Distinguish between **logical order for understanding results** and the **actual execution plan** chosen by the Oracle Optimizer.
- Write readable queries with stable pagination order and avoid discrepancies caused by `NULL`, joins, or aliases.

## 1. Basic SELECT Structure Template

An Oracle query typically takes the form:

```sql
SELECT [DISTINCT] expression_1 [AS alias_1],
                  expression_2 [AS alias_2],
                  ...
FROM   table_or_view [alias]
       [JOIN another_table ON join_condition]
[WHERE row_condition]
[GROUP BY grouping_expression_1, grouping_expression_2, ...]
[HAVING group_condition]
[ORDER BY sort_expression_1 [ASC | DESC] [NULLS FIRST | NULLS LAST],
          sort_expression_2, ...]
[OFFSET n ROWS]
[FETCH FIRST | NEXT m ROWS ONLY | WITH TIES];
```

**The `[ ]` pairs in the template are documentation notation indicating optional components, not characters to type literally into SQL.** Oracle has many extended features (`WITH`, subqueries, analytic functions, set operators, hierarchical queries, `MODEL`, `MATCH_RECOGNIZE`, `FOR UPDATE`, etc.), but first you need to master the `SELECT ... FROM ... WHERE ... GROUP BY ... HAVING ... ORDER BY ... OFFSET/FETCH` framework.

| Component | Question it answers | Example |
| --- | --- | --- |
| `SELECT` | Which columns/expressions should be returned? | `SELECT full_name, salary * 12 AS annual_salary` |
| `FROM` | Which sources do rows come from? | `FROM lab_employees e` |
| `JOIN ... ON` | By what relationship are data sources combined? | `JOIN lab_departments d ON d.department_id = e.department_id` |
| `WHERE` | Which **rows** are kept before grouping? | `WHERE e.active_flag = 'Y'` |
| `GROUP BY` | By which key are rows grouped together? | `GROUP BY e.department_id` |
| `HAVING` | Which **groups** are kept after computing aggregates? | `HAVING COUNT(*) >= 2` |
| `DISTINCT` | Remove duplicate result rows? | `SELECT DISTINCT department_id` |
| `ORDER BY` | In what order should results be returned? | `ORDER BY total_salary DESC` |
| `OFFSET/FETCH` | How many initial rows to skip and maximum rows to fetch? | `FETCH FIRST 5 ROWS ONLY` |

Two points to remember from the start:

1. `WHERE` and `HAVING` can both eliminate data, but they operate at **two different levels**: rows and groups.
2. **Without `ORDER BY`, Oracle does not guarantee the order of returned rows**, even if you previously saw them appear by `ID` or insertion order.

## 2. Creating Sample Data to Trace Each Step

The following examples use two small tables:

```text
LAB_DEPARTMENTS                      LAB_EMPLOYEES
  DEPARTMENT_ID  (PK) <------------+  EMPLOYEE_ID (PK)
  DEPARTMENT_NAME                 +-- DEPARTMENT_ID (FK, nullable)
                                     FULL_NAME
                                     SALARY (nullable)
                                     ACTIVE_FLAG ('Y' / 'N')
                                     HIRE_DATE
```

Run the DDL and DML in a **dedicated practice schema** with `CREATE TABLE` privilege and tablespace quota. If tables with the same names already exist, use a different lab schema; do not drop application tables to run examples.

### 2.1. Creating the Tables

```sql
CREATE TABLE lab_departments (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(80 CHAR) NOT NULL
);

CREATE TABLE lab_employees (
    employee_id   NUMBER PRIMARY KEY,
    full_name     VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER,
    salary        NUMBER(12, 2),
    active_flag   CHAR(1) DEFAULT 'Y' NOT NULL,
    hire_date     DATE NOT NULL,
    CONSTRAINT fk_lab_emp_dept
        FOREIGN KEY (department_id)
        REFERENCES lab_departments (department_id),
    CONSTRAINT ck_lab_emp_active
        CHECK (active_flag IN ('Y', 'N'))
);
```

### 2.2. Inserting Data

```sql
INSERT INTO lab_departments VALUES (10, 'Engineering');
INSERT INTO lab_departments VALUES (20, 'Sales');
INSERT INTO lab_departments VALUES (30, 'Human Resources');
INSERT INTO lab_departments VALUES (40, 'Legal');

INSERT INTO lab_employees VALUES (1, 'An',   10, 2000, 'Y', DATE '2024-01-10');
INSERT INTO lab_employees VALUES (2, 'Bình', 10, 3000, 'Y', DATE '2024-02-15');
INSERT INTO lab_employees VALUES (3, 'Chi',  10, 2500, 'N', DATE '2023-09-01');
INSERT INTO lab_employees VALUES (4, 'Dũng', 20, 2800, 'Y', DATE '2024-03-04');
INSERT INTO lab_employees VALUES (5, 'Hà',   20, NULL, 'Y', DATE '2024-04-05');
INSERT INTO lab_employees VALUES (6, 'Lan',  NULL, 1800, 'Y', DATE '2024-05-10');
INSERT INTO lab_employees VALUES (7, 'Minh', 30, 3200, 'N', DATE '2023-08-11');
INSERT INTO lab_employees VALUES (8, 'Nga',  20, 2800, 'Y', DATE '2024-06-06');
INSERT INTO lab_employees VALUES (9, 'Phúc', 30, 2700, 'Y', DATE '2024-07-07');

COMMIT;
```

Key rows to reason about:

| EMPLOYEE_ID | FULL_NAME | DEPARTMENT_ID | SALARY | ACTIVE_FLAG |
| ---: | --- | ---: | ---: | :---: |
| 1 | An | 10 | 2000 | Y |
| 2 | Bình | 10 | 3000 | Y |
| 3 | Chi | 10 | 2500 | N |
| 4 | Dũng | 20 | 2800 | Y |
| 5 | Hà | 20 | `NULL` | Y |
| 6 | Lan | `NULL` | 1800 | Y |
| 7 | Minh | 30 | 3200 | N |
| 8 | Nga | 20 | 2800 | Y |
| 9 | Phúc | 30 | 2700 | Y |

The `LAB_DEPARTMENTS` table has four departments, in which **Legal (40) has no employees**. Employee **Lan** has no assigned department; **Hà** has a `NULL` salary. These cases clearly illustrate the impact of `JOIN`, `COUNT`, and `NULL` in `SELECT`.

## 3. Written Order vs. Logical Processing Order

A SQL statement is usually **written** in the order:

```text
SELECT -> FROM/JOIN -> WHERE -> GROUP BY -> HAVING
       -> ORDER BY -> OFFSET/FETCH
```

To understand the **result semantics** of a query block, you can imagine the **logical processing** sequence as follows:

```text
   FROM and JOIN ... ON
           |
           v
        WHERE
           |
           v
        GROUP BY
           |
           v
         HAVING
           |
           v
     SELECT expressions
     (including analytic functions at the appropriate phase)
           |
           v
        DISTINCT
           |
           v
        ORDER BY
           |
           v
     OFFSET / FETCH
           |
           v
       Result set
```

This is a **mental model**, not an assertion that Oracle physically executes these operations strictly one after another in this order. The Oracle Optimizer can push filter predicates down to table access, reorder joins, choose hash/group aggregation, sort or index scan, merge views, and change the plan to preserve **SQL semantics** at a reasonable cost.

For advanced features, the model needs refinement:

- `WITH` defines referenced **query blocks/CTEs**; it **does not guarantee they are executed and materialized once before the main SELECT**.
- **Analytic functions** (`ROW_NUMBER`, `RANK`, `SUM(...) OVER (...)`, etc.) are evaluated after the `FROM`/`WHERE`/`GROUP BY`/`HAVING` phases in a query block, and before the final `ORDER BY`. They cannot be used directly in the `WHERE` clause of the same query block.
- `DISTINCT` removes duplicates after the returned expressions are determined, while `ORDER BY` sorts the results before `FETCH` retrieves a subset.
- If there are **subqueries** or **set operators** (`UNION ALL`, `UNION`, `INTERSECT`, `MINUS`, etc.), each query block has its own processing scope; do not use the simple diagram of a single block to describe all nested operations.

## 4. Tracing a Complete Query

Requirement: **find departments that have at least two active employees; return the number of employees, the number of employees with a recorded salary, and the total salary, sorted by total salary descending, taking the first two departments.**

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS active_employees,
    COUNT(e.salary) AS known_salaries,
    SUM(e.salary) AS total_salary
FROM lab_departments d
JOIN lab_employees e
    ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
GROUP BY d.department_id, d.department_name
HAVING COUNT(*) >= 2
ORDER BY total_salary DESC NULLS LAST, d.department_id
FETCH FIRST 2 ROWS ONLY;
```

### Phase 1 — `FROM` and `JOIN` Produce Source Rows

`LAB_DEPARTMENTS` has 4 rows; `LAB_EMPLOYEES` has 9 rows. An `INNER JOIN` with the condition `e.department_id = d.department_id` keeps only employees whose department exists and matches.

| Department | Joinable employees | Rows after join |
| --- | --- | ---: |
| 10 — Engineering | An, Bình, Chi | 3 |
| 20 — Sales | Dũng, Hà, Nga | 3 |
| 30 — Human Resources | Minh, Phúc | 2 |
| 40 — Legal | None | 0 |

In total, there are **8 rows** after the `INNER JOIN`. Lan has `DEPARTMENT_ID NULL`, so she does not match any department and is eliminated by the inner join. Department 40 has no employees, so it produces no rows either.

### Phase 2 — `WHERE` Filters Individual Rows

`WHERE e.active_flag = 'Y'` eliminates the two inactive employees: Chi and Minh. **6 rows** remain:

```text
10: An (2000), Bình (3000)
20: Dũng (2800), Hà (NULL), Nga (2800)
30: Phúc (2700)
```

Key point: at the point of reasoning about `WHERE`, `COUNT(*)` or `SUM(e.salary)` for each group does not exist yet. `WHERE` receives individual rows, not a grouped summary table.

### Phase 3 — `GROUP BY` Splits into Groups

`GROUP BY d.department_id, d.department_name` creates **3 groups** corresponding to departments 10, 20, and 30:

| DEPARTMENT_ID | Members in group | `COUNT(*)` | `COUNT(e.salary)` | `SUM(e.salary)` |
| ---: | --- | ---: | ---: | ---: |
| 10 | An, Bình | 2 | 2 | 5000 |
| 20 | Dũng, Hà, Nga | 3 | 2 | 5600 |
| 30 | Phúc | 1 | 1 | 2700 |

Because Hà's `SALARY` is `NULL`, `COUNT(*)` still counts that row, whereas `COUNT(e.salary)` does **not** count the NULL value. `SUM` ignores NULL; the total salary of department 20 is 2800 + 2800 = **5600**, not NULL.

### Phase 4 — `HAVING` Filters Groups

`HAVING COUNT(*) >= 2` keeps groups 10 and 20; group 30 has one active employee and is eliminated.

### Phase 5 — `SELECT` Produces Result Columns

After grouping and group filtering, the `SELECT` list determines the output columns and assigns the aliases `ACTIVE_EMPLOYEES`, `KNOWN_SALARIES`, `TOTAL_SALARY`.

### Phase 6 — `ORDER BY` and `FETCH`

`ORDER BY total_salary DESC NULLS LAST, d.department_id` places department 20 (5600) ahead of department 10 (5000). `FETCH FIRST 2 ROWS ONLY` limits the result to at most two rows.

| DEPARTMENT_ID | DEPARTMENT_NAME | ACTIVE_EMPLOYEES | KNOWN_SALARIES | TOTAL_SALARY |
| ---: | --- | ---: | ---: | ---: |
| 20 | Sales | 3 | 2 | 5600 |
| 10 | Engineering | 2 | 2 | 5000 |

If changed to `FETCH FIRST 1 ROW ONLY`, only **Sales** remains in the result. The query does not alter the grouping logic itself; `FETCH` simply takes a subset **after the specified sort order**.

## 5. `SELECT`: Selecting Columns, Expressions, and Aliases

To retrieve simple columns:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees;
```

To create a computed column:

```sql
SELECT
    employee_id,
    full_name,
    salary,
    salary * 12 AS estimated_annual_salary
FROM lab_employees
WHERE salary IS NOT NULL;
```

`SALARY * 12` is only a **query expression**; it does not create a new column in the table. `AS ESTIMATED_ANNUAL_SALARY` names the output column. The `AS` keyword for a column alias is generally optional:

```sql
SELECT salary * 12 annual_salary
FROM lab_employees;
```

In Oracle, a **table alias** is typically written without the `AS` keyword:

```sql
SELECT e.full_name, d.department_name
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id;
```

### 5.1. Should `SELECT *` Be Used?

`SELECT *` is useful for quickly inspecting a small table:

```sql
SELECT * FROM lab_departments;
```

However, for APIs and long-lived SQL, you should explicitly list the columns you need. The `*` list can change when columns are added to the schema, pulling in sensitive data or large columns the application does not need. In join queries, `SELECT *` can also produce duplicate column names, making DTO mapping unpredictable.

### 5.2. Aliases Are Only Valid in Their Appropriate Scope

Incorrect example:

```sql
SELECT salary * 12 AS annual_salary
FROM lab_employees
WHERE annual_salary > 30000;
```

In Oracle 19c and basic syntax, `ANNUAL_SALARY` is an alias in the `SELECT` list; `WHERE` in the **same query block** cannot see that alias yet. Oracle typically raises an error such as `ORA-00904: invalid identifier`.

Approach 1, repeat the expression in `WHERE`:

```sql
SELECT salary * 12 AS annual_salary
FROM lab_employees
WHERE salary * 12 > 30000;
```

Approach 2, place the calculation in an inner query block:

```sql
SELECT employee_id, full_name, annual_salary
FROM (
    SELECT
        employee_id,
        full_name,
        salary * 12 AS annual_salary
    FROM lab_employees
)
WHERE annual_salary > 30000;
```

In the outer query, `ANNUAL_SALARY` has become a **column of the inline view**. You can also use a CTE (`WITH`) to name the query block; do not assume a CTE is always a physical temporary table.

**Notable exception:** `ORDER BY` in the same query block is **typically allowed** to use a `SELECT` column alias:

```sql
SELECT full_name, salary * 12 AS annual_salary
FROM lab_employees
ORDER BY annual_salary DESC NULLS LAST, full_name;
```

This is a difference in semantics and name resolution, not Oracle "running SELECT twice."

## 6. `FROM`, `JOIN`, and Source Combination Order

`FROM` identifies row sources: tables, views, inline views, subquery factoring (`WITH`), or other data source forms supported by Oracle.

```sql
SELECT
    e.employee_id,
    e.full_name,
    d.department_name
FROM lab_employees e
JOIN lab_departments d
    ON d.department_id = e.department_id
ORDER BY e.employee_id;
```

This is an **inner join**: only pairs of rows satisfying the `ON` condition are kept. Employee Lan, whose `DEPARTMENT_ID` is `NULL`, is not returned.

### 6.1. `ON` Condition vs. `WHERE` in Outer Joins

In an **inner join**, the optimizer can often transform many `ON` and `WHERE` conditions while preserving meaning. In an **outer join**, where a condition is placed can change the result.

Query A: retrieve all departments, joining active employees only when present:

```sql
SELECT d.department_id, d.department_name, e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

Department **Legal (40)** still appears with `E.FULL_NAME NULL`. Because `LEFT JOIN` preserves the left-side rows, departments without matching employees still produce a result row padded with NULLs on the right side.

Query B: join all employees first, then filter active employees in `WHERE`:

```sql
SELECT d.department_id, d.department_name, e.full_name
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
WHERE e.active_flag = 'Y'
ORDER BY d.department_id, e.employee_id;
```

The Legal row generated by the outer join has `E.ACTIVE_FLAG NULL`; the condition `NULL = 'Y'` does not evaluate to `TRUE`, so **the Legal row is eliminated in WHERE**. Query B therefore does not preserve all departments like Query A.

Where a filter on the right table should be placed depends on the business requirement. **Do not move conditions between `ON` and `WHERE` in an outer join just because the syntax looks equivalent.**

### 6.2. The Missing JOIN Condition Mistake

```sql
SELECT e.full_name, d.department_name
FROM lab_employees e
CROSS JOIN lab_departments d;
```

`CROSS JOIN` produces a **Cartesian product**: 9 employees × 4 departments = **36 pairs** before any filter. This can be intentional when combinations of data are needed, but it is usually a bug when the author forgot the relationship condition. With large datasets, cardinality can explode dramatically.

Do not confuse "having multiple tables in `FROM`" with "Oracle will automatically know which `DEPARTMENT_ID` column to join them on."

## 7. `WHERE`: Row-Level Conditions

`WHERE` removes rows that do not satisfy the condition before `GROUP BY` executes in the **same query block**.

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE active_flag = 'Y'
  AND salary >= 2500
ORDER BY employee_id;
```

Conditions can use comparisons, `BETWEEN`, `IN`, `LIKE`, `IS NULL`, `EXISTS`, subqueries, and logical expressions. When combining complex `AND` and `OR` clauses, use parentheses to make intent clear:

```sql
SELECT employee_id, full_name, department_id, active_flag
FROM lab_employees
WHERE active_flag = 'Y'
  AND (department_id = 10 OR department_id = 20);
```

If you omit the parentheses and write `active_flag = 'Y' AND department_id = 10 OR department_id = 20`, the `AND` operator has higher precedence than `OR`; you could accidentally include **inactive** employees from department 20 if such rows exist in the data.

### 7.1. `NULL` and Three-Valued Logic

In SQL, a condition can evaluate to **TRUE**, **FALSE**, or **UNKNOWN** (often due to `NULL`). `WHERE` only keeps rows whose condition evaluates to **TRUE**.

Incorrect example to find employees without an assigned department:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id = NULL;
```

`= NULL` is not a logically valid way to check for NULL. Use:

```sql
SELECT employee_id, full_name
FROM lab_employees
WHERE department_id IS NULL;
```

Result: employee **Lan**. When finding employees with a salary, use `SALARY IS NOT NULL`:

```sql
SELECT full_name, salary
FROM lab_employees
WHERE salary IS NOT NULL;
```

**Oracle note:** for standard character string types, Oracle currently treats an empty string `''` as `NULL`. Therefore, checking a `VARCHAR2` column may differ from expectations coming from programming languages that distinguish empty strings from null. This should not be taken as a rule that every data type handles empty strings the same way.

### 7.2. `WHERE` and Aggregate Functions

The following query is invalid:

```sql
SELECT department_id, COUNT(*) AS employee_count
FROM lab_employees
WHERE COUNT(*) >= 2
GROUP BY department_id;
```

`COUNT(*)` requires data **after grouping**, so it cannot be placed as a group condition in `WHERE`. Use `HAVING COUNT(*) >= 2`. If you only want to filter active employees, the `ACTIVE_FLAG = 'Y'` condition still belongs in `WHERE` before grouping.

## 8. `GROUP BY` and `HAVING`: From Rows to Groups

`GROUP BY` places rows with the same grouping key values into one group to compute aggregates.

```sql
SELECT
    department_id,
    COUNT(*) AS employee_count,
    COUNT(salary) AS salary_count,
    SUM(salary) AS salary_total,
    AVG(salary) AS average_salary
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
ORDER BY department_id NULLS LAST;
```

On the sample data, the result includes **a `DEPARTMENT_ID NULL` group** containing Lan. Oracle groups NULL values of the grouping key into the same group. For the `DEPARTMENT_ID=20` group, `COUNT(*)=3` but `COUNT(SALARY)=2` because Hà has no salary recorded.

### 8.1. Rules for Columns in SELECT

In a query block with `GROUP BY`, non-aggregate expressions in the `SELECT` list must normally be **valid grouping expressions** according to Oracle rules:

```sql
SELECT department_id, COUNT(*) AS total
FROM lab_employees
GROUP BY department_id;
```

Commonly invalid query:

```sql
SELECT department_id, full_name, COUNT(*) AS total
FROM lab_employees
GROUP BY department_id;
```

Because a department has multiple `FULL_NAME` values, Oracle does not know which row's name to pick to represent the group. Oracle typically returns `ORA-00979: not a GROUP BY expression` or the corresponding error for the release. If you need individual names, do not group by department like this; if you need a representative value, you must **explicitly define the rule**, such as `MIN(FULL_NAME)`, `MAX(FULL_NAME)`, or use an analytic/subquery approach.

### 8.2. `WHERE` Filters First; `HAVING` Filters After

```sql
SELECT
    department_id,
    COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING COUNT(*) >= 2
ORDER BY department_id;
```

Result on the sample data:

| DEPARTMENT_ID | ACTIVE_COUNT |
| ---: | ---: |
| 10 | 2 |
| 20 | 3 |

`WHERE` drops `ACTIVE_FLAG='N'` employees before counting. `HAVING` then eliminates groups with fewer than two active employees. Moving `active_flag='Y'` into `HAVING` without including it in GROUP BY/an aggregate changes both semantics and validity.

### 8.3. Aggregate Aliases and HAVING Scope

In Oracle 19c, this example is typically invalid:

```sql
SELECT department_id, COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING active_count >= 2;
```

Correct version, well-compatible with classic Oracle releases:

```sql
SELECT department_id, COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING COUNT(*) >= 2;
```

**Version note:** Newer Oracle releases such as 23ai/26ai add the ability to reference certain `SELECT` aliases and positions in `GROUP BY`/`HAVING` under supported syntax. Therefore, you should not state "Oracle *never* allows aliases in HAVING." For code that must run on 19c or across multiple versions, using the aggregate expression directly in `HAVING` or an outer query block is clear and reliable.

### 8.4. `COUNT(*)` vs. `COUNT(column)` and `COUNT(DISTINCT column)`

```sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(salary) AS rows_with_salary,
    COUNT(DISTINCT department_id) AS distinct_nonnull_departments
FROM lab_employees;
```

Across the 9 sample rows:

- `COUNT(*) = 9` because there are 9 rows.
- `COUNT(SALARY) = 8` because one row has `SALARY NULL`.
- `COUNT(DISTINCT DEPARTMENT_ID) = 3` because the values are 10, 20, 30; `NULL` is not counted as a department value.

This difference is especially important when using `LEFT JOIN`. If you want to count actual employees in each department, use `COUNT(e.employee_id)` instead of `COUNT(*)`:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(*) AS joined_rows,
    COUNT(e.employee_id) AS actual_employees
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

For Legal (40), `JOINED_ROWS = 1` because of the single NULL-padded row from the outer join, while `ACTUAL_EMPLOYEES = 0` because `E.EMPLOYEE_ID` is NULL. This is the difference between **counting rows after JOIN** and **counting actually matched right-side entities**.

### 8.5. Aggregates on an Empty Set

A `SUM` over values with no matching data can return `NULL`, whereas `COUNT` typically returns 0:

```sql
SELECT
    d.department_id,
    COUNT(e.employee_id) AS staff_count,
    SUM(e.salary) AS salary_sum,
    NVL(SUM(e.salary), 0) AS salary_sum_for_display
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
GROUP BY d.department_id
ORDER BY d.department_id;
```

For department 40: `STAFF_COUNT=0`, `SALARY_SUM=NULL`, and `SALARY_SUM_FOR_DISPLAY=0`. `NVL` only replaces NULL in the output; the application must decide **whether NULL means "unknown" or "none"** before blindly replacing every NULL with 0.

## 9. `DISTINCT`: Deduplication After Projection

When writing:

```sql
SELECT department_id
FROM lab_employees
ORDER BY department_id NULLS LAST;
```

The result has many duplicate `DEPARTMENT_ID` rows because each employee produces one row. Adding `DISTINCT`:

```sql
SELECT DISTINCT department_id
FROM lab_employees
ORDER BY department_id NULLS LAST;
```

You will get the values **10, 20, 30, and NULL**, each appearing once in the example's result. `DISTINCT` applies to the **entire tuple of expressions** in the `SELECT` list:

```sql
SELECT DISTINCT department_id, active_flag
FROM lab_employees;
```

Here it removes **duplicate `(DEPARTMENT_ID, ACTIVE_FLAG)` pairs**, which does not mean "keep one row per DEPARTMENT_ID." If you want **the single highest-paid employee per department**, you need a row-selection rule, usually analytic `ROW_NUMBER()` or a grouping-and-join solution with tie-breaking constraints.

Do not use `DISTINCT` to mask a `JOIN` that duplicates rows due to an incorrect join condition. `DISTINCT` can consume sort/hash resources and hide information about record counts.

## 10. `ORDER BY`: Output Order Does Not Exist Automatically

In SQL, result order is not guaranteed if the query **does not specify `ORDER BY` in the query block returning the result**.

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
ORDER BY salary DESC NULLS LAST, employee_id;
```

The rules:

- `ASC`: ascending; this is the default direction if omitted.
- `DESC`: descending.
- `NULLS FIRST` / `NULLS LAST`: explicitly specifies NULL placement. In Oracle, by default **ASC puts NULLs last** and **DESC puts NULLs first**, but it is best to state it explicitly when business requirements matter.
- Multiple sort keys are evaluated from left to right. The second key resolves ties among rows with equal values for the first key.

In the sample data, Dũng and Nga both have a salary of 2800. With only `ORDER BY SALARY DESC`, Oracle does not guarantee who comes first. Adding `EMPLOYEE_ID` as a tie-breaker stabilizes the order.

### 10.1. `ORDER BY` Can Use Aliases

```sql
SELECT
    employee_id,
    full_name,
    salary * 12 AS annual_salary
FROM lab_employees
ORDER BY annual_salary DESC NULLS LAST, employee_id;
```

The alias `ANNUAL_SALARY` is allowed in the `ORDER BY` of the query block, even though it cannot be used directly in `WHERE` in the Oracle 19c example. You can write `ORDER BY 3 DESC` to refer to the third expression in the `SELECT` list, but that easily breaks when column order changes. Prefer explicit names or expressions in maintainable code.

### 10.2. Character Sorting and NLS

`ORDER BY FULL_NAME` in Oracle can be affected by collation/NLS settings depending on column/session configuration. Byte sorting (`BINARY`) and Vietnamese linguistic ordering are two different policies. For multilingual data, verify the appropriate collation rules.

If a query is used for pagination, in addition to choosing the collation, include a **unique secondary key** such as `EMPLOYEE_ID` so that rows considered equal under the collation do not swap order between pages.

### 10.3. `ORDER BY` in an Inline View

An `ORDER BY` placed inside a subquery can serve a top-N operation or a specific requirement of that query block, but **do not assume it guarantees the final display order if the outer query has no `ORDER BY`**. Oracle reserves the right to transform query execution while preserving SQL semantics. To guarantee final display order for the client, put `ORDER BY` on the `SELECT` returning data to the client.

## 11. `OFFSET` and `FETCH FIRST`: Paginating by the Chosen Order

Since Oracle Database 12c, the **row limiting clause** syntax lets you request:

```sql
SELECT
    employee_id,
    full_name,
    salary
FROM lab_employees
ORDER BY salary DESC NULLS LAST, employee_id
FETCH FIRST 3 ROWS ONLY;
```

With the sample data, the three highest salaries may include inactive employees because this query **does not filter `ACTIVE_FLAG`**. If you only want active employees, add `WHERE ACTIVE_FLAG='Y'`.

### 11.1. Skipping Leading Rows to Fetch the Next Page

```sql
SELECT
    employee_id,
    full_name,
    salary
FROM lab_employees
WHERE active_flag = 'Y'
ORDER BY salary DESC NULLS LAST, employee_id
OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;
```

Logic:

1. Filter active employees.
2. Sort by salary descending, NULLs last, then employee ID.
3. Skip the first two rows of the **sorted** result.
4. Fetch at most the next two rows.

`FETCH FIRST ... ROWS ONLY` and `FETCH NEXT ... ROWS ONLY` express row-count limiting; the number of rows returned may be fewer than requested if not enough data exists. Without `ORDER BY`, page one and page two have no stable order for the application to rely on.

### 11.2. `WITH TIES` vs. `ONLY`

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary IS NOT NULL
ORDER BY salary DESC
FETCH FIRST 4 ROWS WITH TIES;
```

`WITH TIES` can return **more** than four rows if the row at the cutoff boundary shares the same `ORDER BY` key value with subsequent rows. For the 2800 salary shared by Dũng and Nga, the result can retain both if the boundary falls on the tied group. Adding `EMPLOYEE_ID` to `ORDER BY` makes the sort key unique, so normally no extra rows tie at the boundary across the full key.

**`WITH TIES` requires `ORDER BY`** to determine ties. Do not use `WITH TIES` when an API promises an exact fixed page size.

### 11.3. OFFSET Pagination When Data Changes

If concurrent inserts or deletes happen between two clicks of "Next page," offset pagination can **skip or duplicate rows** even with a stable `ORDER BY`. With large datasets, skipping `OFFSET 100000 ROWS` can also spend effort scanning many rows before returning the page.

When stable multi-page reading is required, consider:

- Using a **unique and immutable** sort key.
- Using **keyset/seek pagination**: remember the key values of the last row on the previous page and query rows after that key.
- Considering a consistent snapshot/transaction when business requirements demand the same dataset, rather than expecting `OFFSET` to hold a snapshot across multiple HTTP requests.

## 12. Oracle `ROWNUM` and the Top-N Trap

Before the `FETCH FIRST` syntax, Oracle commonly used the **`ROWNUM`** pseudocolumn to number rows **in the order Oracle produces them within a query block**. It is **not equivalent** to row numbering after `ORDER BY` in the same query block.

### 12.1. An Easily Misunderstood Example

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE ROWNUM <= 3
ORDER BY salary DESC;
```

Do not interpret this as "get the three employees with the highest salary." In a typical execution model, `ROWNUM <= 3` limits which rows Oracle picks first, and then `ORDER BY` sorts only **those three rows**. An index access path chosen by the planner might happen to yield the expected result by coincidence, but you cannot rely on that as a SQL contract.

### 12.2. Top-N Using an Inline View

```sql
SELECT employee_id, full_name, salary
FROM (
    SELECT employee_id, full_name, salary
    FROM lab_employees
    WHERE salary IS NOT NULL
    ORDER BY salary DESC, employee_id
)
WHERE ROWNUM <= 3;
```

Here `ORDER BY` is inside the **inner query block**, while `ROWNUM` limits the rows supplied by the sorted inline view to the **outer query block**. This pattern was used in Oracle versions before the modern row limiting clause. To guarantee final return order to the client in general queries, you can add `ORDER BY salary DESC, employee_id` to the outer query.

When the release supports it, the more readable form is:

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE salary IS NOT NULL
ORDER BY salary DESC, employee_id
FETCH FIRST 3 ROWS ONLY;
```

### 12.3. Why Doesn't `ROWNUM > 1` Work as Expected?

```sql
SELECT employee_id
FROM lab_employees
WHERE ROWNUM > 1;
```

You cannot treat `ROWNUM` in a query block's `WHERE` clause as pre-assigned sequential row numbers from which you take row 2 onward: the first row evaluated against `ROWNUM > 1` fails the condition, so no row is ever accepted as "row 1" for ROWNUM to advance to 2. This is the trap of how Oracle assigns `ROWNUM`.

To fetch rows starting at a given position in an order, use `OFFSET/FETCH` after `ORDER BY` or assign `ROW_NUMBER()` in a subquery and filter in the outer query.

## 13. `WITH` and Inline Views: Splitting Query Blocks for Easier Reasoning

A large `SELECT` statement can be structured into **Common Table Expressions (CTEs)** using `WITH`:

```sql
WITH active_employees AS (
    SELECT department_id, employee_id, salary
    FROM lab_employees
    WHERE active_flag = 'Y'
),
department_totals AS (
    SELECT
        department_id,
        COUNT(*) AS employee_count,
        SUM(salary) AS total_salary
    FROM active_employees
    WHERE department_id IS NOT NULL
    GROUP BY department_id
)
SELECT
    d.department_name,
    t.employee_count,
    t.total_salary
FROM department_totals t
JOIN lab_departments d
  ON d.department_id = t.department_id
WHERE t.employee_count >= 2
ORDER BY t.total_salary DESC, d.department_id;
```

In the `DEPARTMENT_TOTALS` query block, `EMPLOYEE_COUNT` becomes an **output column of the CTE**. The outer query can use `WHERE t.employee_count >= 2` because at that outer level it is an existing source column, no longer an alias being created within the same `SELECT`.

**Do not assume a CTE is a physical temporary table by default.** The optimizer may inline/merge or materialize a CTE depending on semantics and the plan. The core value of `WITH` for learners is **naming logical steps**, separating alias scopes, and making queries readable.

### A Step-by-Step Mental Checklist

For a complex query, try listing:

1. Which **query blocks** exist (main query, CTEs, inline views, subqueries)?
2. What is the row source of **each block**?
3. Which rows does `WHERE` eliminate before grouping?
4. How many groups does `GROUP BY` form, and which groups does `HAVING` eliminate?
5. Which columns/aliases does `SELECT` produce so an **outer query block** can reference them?
6. Which **block's** final result set do `DISTINCT`, `ORDER BY`, and `FETCH` act upon?

This process helps avoid confusing aliases from different scopes and distinguishes a predicate filtering **base rows** from one filtering **aggregated results**.

## 14. Analytic Functions: An Important Layer After GROUP/HAVING

In SQL, an **aggregate** such as `SUM(salary)` typically collapses multiple rows into one row per group. An **analytic function** such as `ROW_NUMBER() OVER (...)` computes a result over a window without **collapsing away the input rows**.

Example ranking active employees by salary within each department:

```sql
SELECT
    employee_id,
    full_name,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC NULLS LAST, employee_id
    ) AS rn
FROM lab_employees
WHERE active_flag = 'Y';
```

`WHERE` removes inactive employees before the analytic function assigns numbers; `ROW_NUMBER` with `PARTITION BY department_id` splits the remaining employees by department and numbers them within each partition.

Common mistake:

```sql
SELECT
    employee_id,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS rn
FROM lab_employees
WHERE rn = 1;
```

You cannot use `RN` or an analytic expression directly in `WHERE` of the **same query block** under basic Oracle syntax rules. Compute the analytic function in an inner query block and filter in the outer block:

```sql
SELECT employee_id, full_name, department_id, salary
FROM (
    SELECT
        employee_id,
        full_name,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC NULLS LAST, employee_id
        ) AS rn
    FROM lab_employees
    WHERE active_flag = 'Y'
)
WHERE rn = 1
ORDER BY department_id NULLS LAST, employee_id;
```

Now the outer query picks **the highest-paid active employee in each department** according to the defined tie-breaker. Because `DEPARTMENT_ID NULL` values are also grouped together by `PARTITION BY`, Lan could represent the unassigned group unless you add `DEPARTMENT_ID IS NOT NULL`.

**Release note:** Newer Oracle versions may offer more convenient syntax for filtering analytic results (such as window/qualify extensions). For SQL that must run on 19c, an inline view/CTE is the standard and compatible approach.

## 15. Logical Processing vs. Physical Execution Plan

If you interpret "Oracle finishes `FROM` before touching `WHERE` in all cases" as **strict physical execution timing**, you will misunderstand the optimizer.

Example:

```sql
SELECT
    d.department_name,
    COUNT(*) AS active_count
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id
WHERE e.active_flag = 'Y'
GROUP BY d.department_name
ORDER BY active_count DESC;
```

To produce the same result, Oracle may:

- Scan the employees table and **filter `ACTIVE_FLAG='Y'` right during table access**.
- Use an **index range scan** if a suitable index exists and the estimated cost beats a full scan.
- Choose **nested loops**, **hash join**, or another join method.
- Perform **hash group by** or **sort group by**.
- Perform final sorting via `SORT ORDER BY`, or avoid certain sorts when the access path already satisfies the required order.

This does not invert the meaning of `WHERE`/`GROUP BY`/`HAVING`. Optimizer transformations must preserve results according to SQL rules and proper transactional consistency.

### 15.1. Viewing the Estimated Plan

```sql
EXPLAIN PLAN FOR
SELECT d.department_name, COUNT(*) AS active_count
FROM lab_employees e
JOIN lab_departments d
  ON d.department_id = e.department_id
WHERE e.active_flag = 'Y'
GROUP BY d.department_name
ORDER BY active_count DESC;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
```

`EXPLAIN PLAN` shows an **estimated plan** based on the environment and statistics at parse time; it is not a guaranteed record of an actual execution. When analyzing production performance, DBAs may need `DBMS_XPLAN.DISPLAY_CURSOR`, actual row counts, logical/physical I/O, and timing details from the executed cursor.

### 15.2. SQL Is a Declarative Language

Instead of writing "read table A, then loop 1000 times looking up table B," SQL describes the **desired result set**. The optimizer is responsible for finding a concrete execution strategy. **Logical processing order** helps learners verify query meaning; the **execution plan** helps administrators and developers analyze runtime performance.

## 16. Common Errors and How to Identify Them

| Symptom | Typical cause | Appropriate fix/check |
| --- | --- | --- |
| `ORA-00904` when filtering by an alias in `WHERE` | `SELECT` alias is not in scope in `WHERE` of the same block | Repeat the expression or use an inline view/CTE |
| `ORA-00979` on a query with `GROUP BY` | Non-grouped/non-aggregated column placed in `SELECT` | Group the column appropriately or wrap in an aggregate |
| Cannot use `COUNT(*)` in `WHERE` | Aggregates belong to the grouping phase | Use `HAVING COUNT(*) ...` |
| Empty departments disappear from `LEFT JOIN` | Filter on the right table in `WHERE` removes NULL-padded rows | Place the condition in `ON` when preserving the left table |
| `COUNT(*)` for an empty department is 1 | The NULL-padded row generated by `LEFT JOIN` is still a row | `COUNT(e.employee_id)` |
| `SUM` returns NULL for a group with no salaries | Aggregates ignore NULL and have no matching values to sum | `NVL(SUM(...), 0)` when business semantics allow |
| `WHERE x = NULL` finds no rows | Comparing with NULL yields UNKNOWN | `WHERE x IS NULL` |
| `DISTINCT` hides record counts | Deduplicates entire output tuples | Check joins/cardinality; do not use as a band-aid for bad joins |
| `FETCH FIRST` returns unpredictable rows | Missing `ORDER BY` or missing tie-breaker | `ORDER BY` stable/unique keys |
| `ROWNUM <= 3 ORDER BY salary DESC` does not give true top 3 | `ROWNUM` limits rows before sorting in the same block | `FETCH FIRST` or inner sorted query + outer `ROWNUM` |
| `WHERE ROWNUM > 1` does not return the second page | Behavior of assigning ROWNUM as rows are accepted | `OFFSET` or subquery using `ROW_NUMBER` |
| Filtering by `ROW_NUMBER()` causes an error | Analytic functions are evaluated after `WHERE` in the same block | Compute analytic inside, filter `RN` outside |
| Results from an index scan appear sorted | Physical order is not a SQL contract | Always specify `ORDER BY` when order matters |
| Grouped results are right but query is slow | Logical order does not dictate physical plan | Inspect optimizer statistics and execution plan |
| `WHERE salary > 2500` drops `SALARY NULL` rows | NULL makes the condition UNKNOWN | Explicitly define the NULL handling policy |
| Alias in `HAVING` works on newer releases but fails on 19c | Alias support in grouping varies by release | Use the aggregate expression directly for multi-version code |

## 17. Practice Exercises

All exercises use the two tables `LAB_EMPLOYEES` and `LAB_DEPARTMENTS` from section 2. **Predict the row count and results first**, then run the SQL to verify.

### Exercise 1 — Filtering and Sorting

Write a query to retrieve `EMPLOYEE_ID`, `FULL_NAME`, and `SALARY` of employees who:

1. Are active (`ACTIVE_FLAG='Y'`).
2. Have a salary of 2500 or higher.
3. Are sorted by salary descending; if tied on salary, `EMPLOYEE_ID` ascending.

**Suggested solution:**

```sql
SELECT employee_id, full_name, salary
FROM lab_employees
WHERE active_flag = 'Y'
  AND salary >= 2500
ORDER BY salary DESC, employee_id;
```

### Exercise 2 — Grouping Employees by Department

Write SQL to count **active** employees per department (including those not yet assigned to a department), returning `DEPARTMENT_ID` and `ACTIVE_COUNT`; keep only groups with at least two people.

```sql
SELECT department_id, COUNT(*) AS active_count
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING COUNT(*) >= 2
ORDER BY department_id NULLS LAST;
```

Expected results include departments **10 and 20**. Lan forms a `DEPARTMENT_ID NULL` group with one person, so it does not pass `HAVING`.

### Exercise 3 — Preserving Empty Departments

Write a query returning all departments including department 40 and the count of active employees in each department, including 0. Use `LEFT JOIN`, place the active condition in `ON`, and count with `COUNT(e.employee_id)`:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS active_count
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
GROUP BY d.department_id, d.department_name
ORDER BY d.department_id;
```

Expected: 10 has 2, 20 has 3, 30 has 1, and 40 has 0. Move `e.active_flag = 'Y'` down to `WHERE` and compare the results; explain using logical processing order.

### Exercise 4 — One Highest-Paid Employee per Department

Use `ROW_NUMBER()` to retrieve one highest-paid active employee in each department, breaking salary ties with `EMPLOYEE_ID`. Exclude the `DEPARTMENT_ID NULL` group if the requirement only counts employees assigned to a department.

```sql
SELECT employee_id, full_name, department_id, salary
FROM (
    SELECT
        employee_id,
        full_name,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC NULLS LAST, employee_id
        ) AS rn
    FROM lab_employees
    WHERE active_flag = 'Y'
      AND department_id IS NOT NULL
)
WHERE rn = 1
ORDER BY department_id;
```

Explain why the query uses **two SELECT blocks** instead of placing `WHERE RN=1` inside the block containing the analytic function.

### Exercise 5 — Top-N and Pagination

Run three queries:

1. `FETCH FIRST 3 ROWS ONLY` after `ORDER BY SALARY DESC NULLS LAST, EMPLOYEE_ID`.
2. `OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY` with the same `ORDER BY`.
3. `WHERE ROWNUM <= 3 ORDER BY SALARY DESC` in the same block.

Record the results and explain why query 3 **must not be used as the definition of the top 3 highest salaries**.

### Exercise 6 — Distinguishing `WHERE` and `HAVING`

Given two requirements:

- **A:** compute the average salary of active employees in each department, but **keep only employees with a salary of 2500 or higher before computing**.
- **B:** compute the average salary of **all active employees** in each department, but **show only departments whose average is 2500 or higher**.

The two queries must differ:

```sql
-- A: row-level condition belongs in WHERE.
SELECT department_id, AVG(salary) AS avg_salary
FROM lab_employees
WHERE active_flag = 'Y'
  AND salary >= 2500
GROUP BY department_id
ORDER BY department_id NULLS LAST;

-- B: group-level condition belongs in HAVING.
SELECT department_id, AVG(salary) AS avg_salary
FROM lab_employees
WHERE active_flag = 'Y'
GROUP BY department_id
HAVING AVG(salary) >= 2500
ORDER BY department_id NULLS LAST;
```

Note that both can encounter groups containing NULL values; `AVG` ignores rows with `SALARY NULL`. Do not just look at coincidentally similar numbers on sample data and conclude that `WHERE` and `HAVING` are interchangeable.

### Exercise 7 — Fixing an Incorrect SQL Statement

Given the statement:

```sql
SELECT
    d.department_name,
    COUNT(*) AS staff_count,
    SUM(e.salary) AS total_salary
FROM lab_departments d
LEFT JOIN lab_employees e
    ON d.department_id = e.department_id
WHERE e.active_flag = 'Y'
  AND total_salary > 3000
GROUP BY d.department_name
ORDER BY total_salary DESC;
```

Actual requirement: display **all departments**, even departments with no active employees, while also supporting filtering for departments with active total salary greater than 3000 when the user enables that option. Do the following:

1. Explain why the `TOTAL_SALARY` alias cannot be used directly in `WHERE`.
2. Move the active employee condition to the right place so empty departments can be preserved.
3. Use `COUNT(e.employee_id)` instead of `COUNT(*)` to count actual employees.
4. When the total salary filter is **enabled**, use `HAVING NVL(SUM(e.salary),0) > 3000`; when **disabled**, omit `HAVING` to keep all departments.

A version **without total salary filtering**, preserving all departments:

```sql
SELECT
    d.department_id,
    d.department_name,
    COUNT(e.employee_id) AS staff_count,
    NVL(SUM(e.salary), 0) AS total_salary
FROM lab_departments d
LEFT JOIN lab_employees e
  ON e.department_id = d.department_id
 AND e.active_flag = 'Y'
GROUP BY d.department_id, d.department_name
ORDER BY total_salary DESC, d.department_id;
```

If `HAVING NVL(SUM(e.salary), 0) > 3000` is added, departments that do not meet the threshold are excluded — **that is a change per the filter requirement**, as you cannot simultaneously ask to show every department at every salary total while the filter is turned on.

## 18. Cleaning Up Practice Data

Run only in the **lab schema you own**, after completing the exercises:

```sql
DROP TABLE lab_employees PURGE;
DROP TABLE lab_departments PURGE;
```

Drop the child table `LAB_EMPLOYEES` first because it has a foreign key referencing `LAB_DEPARTMENTS`. `PURGE` bypasses the recycle bin; do not use this statement on tables that need recovery or that you do not own.

## Summary

To understand an Oracle `SELECT` statement, trace the **data flow**: `FROM/JOIN` builds the source row set, `WHERE` filters rows, `GROUP BY` forms groups, `HAVING` filters groups, `SELECT` produces output columns/aliases, `DISTINCT` removes duplicate rows, `ORDER BY` sorts the order, and `OFFSET/FETCH` takes a slice of the result. `WITH`, inline views, and analytic functions expand how query blocks are organized, without removing the rules of scope and logical order.

Clearly distinguishing **SQL logic** from the **execution plan** helps you write queries that are **semantically correct**, while knowing when to inspect the optimizer and I/O instead of guessing speed from the order of SQL lines. Whenever `NULL`, outer joins, aggregation, pagination, or aliases are involved, sketch out the stages and verify the row set at each phase before concluding the result.

## Oracle Reference Documentation

- [Oracle Database SQL Language Reference — SELECT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — syntax for `FROM`, `WHERE`, `GROUP BY`, `HAVING`, `ORDER BY`, row limiting, and related restrictions.
- [Oracle Database SQL Language Reference — Aggregate Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html) — semantics of `COUNT`, `SUM`, `AVG`, and NULL handling.
- [Oracle Database SQL Language Reference — Analytic Functions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — where analytic evaluation fits within a query block.
- [Oracle Database SQL Language Reference — ROWNUM Pseudocolumn (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html) — difference between `ROWNUM` and sorted top-N.
- [Oracle Database SQL Tuning Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — optimizer, join methods, execution plans, and performance analysis.

When working with Oracle 23ai/26ai or releases other than 19c, check the release-specific documentation for new syntax capabilities (especially aliases in `GROUP BY`/`HAVING` and analytic filtering). The logical processing order model remains the foundation for understanding queries.
