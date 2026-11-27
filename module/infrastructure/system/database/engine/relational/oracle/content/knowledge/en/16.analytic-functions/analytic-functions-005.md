# FIRST_VALUE, LAST_VALUE, NTH_VALUE, and Window Scope in Oracle

In Oracle Database, the analytic functions **`FIRST_VALUE`**, **`LAST_VALUE`**, and **`NTH_VALUE`** retrieve a value at the first, last, or Nth position within a **window frame** of data. They are commonly used to compare a transaction against a customer's first or last transaction, find the highest/lowest salary per department, retrieve the value at the second transaction, or display first/last benchmarks alongside each row without losing row-level detail.

The hardest part of this group of functions is not the function names, but the **window frame scope**. In Oracle, if an analytic clause includes `ORDER BY` without a windowing clause, the default frame is usually:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

This is especially surprising with `LAST_VALUE`: many people expect the last value of the entire partition, yet receive the last value of the **current frame**. To retrieve the last value of the entire partition, you generally need to declare explicitly:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

This lesson covers syntax, the meaning of each function, the difference between `ROWS` and `RANGE`, how to handle `NULL`, ties, and deterministic ordering, along with hands-on SQL examples.

## 1. Review of Analytic Functions and Window Frames

Analytic functions compute over a set of rows related to the current row while preserving every row of the result. Common structure:

```sql
function_name(expression)
OVER (
    PARTITION BY group_column
    ORDER BY sort_column
    windowing_clause
)
```

- `PARTITION BY`: divides data into independent groups; the function restarts calculation within each group.
- `ORDER BY`: defines the logical ordering of rows within the partition.
- `windowing_clause`: restricts the set of rows the function can see for the current row.

```text
Dataset
    |
    v
PARTITION BY (if specified)
    |
    v
Sort each partition by analytic ORDER BY
    |
    v
For each current row:
    determine window frame
    |
    v
FIRST_VALUE / LAST_VALUE / NTH_VALUE
    |
    v
Return analytic value alongside current row
```

Unlike `GROUP BY`, analytic functions do not collapse multiple rows into a single result row. For example, `FIRST_VALUE(salary)` can return the department's first salary alongside **every employee** in that department.

### 1.1. What Is a Window Frame?

A window frame is the specific subset of rows selected within a partition to compute the result at a current row. Under ascending date order, a frame can be:

- From the beginning of the partition to the current row.
- From the current row to the end of the partition.
- Two rows before through two rows after the current row.
- The entire partition.

Common bounds:

| Bound | Meaning |
|---|---|
| `UNBOUNDED PRECEDING` | First row of the partition |
| `n PRECEDING` | Step back n rows or n sort-key units, depending on ROWS/RANGE |
| `CURRENT ROW` | Current row; with RANGE, may include peers sharing the sort key |
| `n FOLLOWING` | Step forward n rows or n sort-key units |
| `UNBOUNDED FOLLOWING` | Last row of the partition |

Example of a full-partition frame:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

Example of a frame from the start of the partition to current:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

### 1.2. Processing Order and Analytic Function Placement

Within a query block, analytic functions are evaluated after row filtering (`WHERE`), grouping (`GROUP BY`), and group filtering (`HAVING`). Therefore, an analytic alias cannot be referenced directly in the `WHERE` clause at the same level. To filter by analytic results, wrap the query in an inline view or CTE.

```sql
WITH ranked AS (
    SELECT employee_id,
           FIRST_VALUE(salary) OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
               ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
           ) AS highest_salary
    FROM employees
)
SELECT *
FROM ranked;
```

## 2. Preparing Practice Data

The examples use a sample table `LAB_EMP_PAY_HISTORY`, containing employees, departments, effective dates, and salaries. The data includes duplicate salary levels and several `NULL` values to illustrate first/last value selection and the effect of `IGNORE NULLS`.

Only create tables in a **DEV/TEST** schema granted `CREATE TABLE` privileges and quota. Before running DDL, confirm the service, PDB, and user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 2.1. Create the Table

```sql
CREATE TABLE lab_emp_pay_history (
    history_id    NUMBER PRIMARY KEY,
    employee_id   NUMBER NOT NULL,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    effective_on  DATE NOT NULL,
    salary        NUMBER(12, 2)
);
```

`HISTORY_ID` uniquely identifies a history record. One employee can have multiple salary rows over time; hence `EMPLOYEE_ID` is not the primary key of this table.

### 2.2. Load Sample Data

```sql
INSERT ALL
    INTO lab_emp_pay_history VALUES (1, 101, 'An',    10, DATE '2026-01-01', 5000)
    INTO lab_emp_pay_history VALUES (2, 102, 'Binh',  10, DATE '2026-01-05', 6000)
    INTO lab_emp_pay_history VALUES (3, 103, 'Chi',   10, DATE '2026-01-10', 6000)
    INTO lab_emp_pay_history VALUES (4, 104, 'Dung',  10, DATE '2026-01-15', 4500)
    INTO lab_emp_pay_history VALUES (5, 105, 'Em',    10, DATE '2026-01-20', NULL)
    INTO lab_emp_pay_history VALUES (6, 201, 'Giang', 20, DATE '2026-01-02', 8000)
    INTO lab_emp_pay_history VALUES (7, 202, 'Ha',    20, DATE '2026-01-07', 7500)
    INTO lab_emp_pay_history VALUES (8, 203, 'Khanh', 20, DATE '2026-01-12', NULL)
    INTO lab_emp_pay_history VALUES (9, 204, 'Lan',   20, DATE '2026-01-17', 7000)
SELECT 1 FROM dual;

COMMIT;
```

### 2.3. View Source Data

```sql
SELECT history_id, employee_id, employee_name,
       department_id, effective_on, salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Two departments have separate salary histories. Department 10 has two 6000 salary entries occurring on different dates; department 20 has alternating `NULL` and non-null values. This dataset helps observe both ties and nulls.

## 3. FIRST_VALUE: Retrieving the First Value in the Window Frame

Basic syntax:

```sql
FIRST_VALUE(expression)
    [RESPECT NULLS | IGNORE NULLS]
OVER (
    [PARTITION BY ...]
    ORDER BY ...
    [windowing_clause]
)
```

`FIRST_VALUE` returns the value of `expression` at **the first row in the window frame** according to the order defined by the analytic `ORDER BY`.

### 3.1. Retrieving the Highest Salary in Each Department

```sql
SELECT employee_id,
       employee_name,
       department_id,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS department_highest_salary
FROM lab_emp_pay_history
ORDER BY department_id, salary DESC NULLS LAST, history_id;
```

Within each department:

- Sort salary descending.
- Place `NULL` last so missing values do not become the highest level.
- `HISTORY_ID` breaks ties when salaries are equal.
- `FIRST_VALUE` retrieves the salary of the first row in the entire partition.

Illustrative result: department 10 has `DEPARTMENT_HIGHEST_SALARY = 6000` on every row; department 20 has `8000` on every row.

In this example, the full-partition frame is written explicitly so that the meaning "highest value in the entire department" does not rely on the default frame. With `FIRST_VALUE` and descending order, the default frame from start to current still includes the first row and usually returns the same first value on every row; however, declaring the frame explicitly clarifies intent for readers and makes future logic changes safer.

### 3.2. Retrieving the First Value Chronologically

```sql
SELECT employee_id,
       employee_name,
       department_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY employee_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_recorded_salary
FROM employee_salary_history;
```

The query assumes an employee has multiple salary records. `FIRST_VALUE` returns the salary from the earliest recorded date. If dates can repeat, add a unique key such as `HISTORY_ID` to identify the first row unambiguously.

### 3.3. FIRST_VALUE and NULL

Oracle defaults to `RESPECT NULLS`: if the first row in the frame has an expression value of `NULL`, `FIRST_VALUE` returns `NULL`. You can use `IGNORE NULLS` to skip null values when locating the first value:

```sql
SELECT employee_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_known_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

`FIRST_VALUE(salary) IGNORE NULLS` returns the first non-null salary by date across the entire partition. If the entire partition contains only nulls, the result remains null.

## 4. LAST_VALUE: Retrieving the Last Value in the Window Frame

Syntax:

```sql
LAST_VALUE(expression)
    [RESPECT NULLS | IGNORE NULLS]
OVER (
    [PARTITION BY ...]
    ORDER BY ...
    [windowing_clause]
)
```

`LAST_VALUE` returns the value of expression at **the last row in the current window frame**. The phrase "in the window frame" is crucial: the frame may span only from the start of the partition to the current row, not the entire partition.

### 4.1. The LAST_VALUE Default Frame Trap

Example:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on
       ) AS last_salary_default_frame
FROM lab_emp_pay_history
ORDER BY department_id, effective_on;
```

When `ORDER BY` is present without a declared frame, Oracle defaults to a frame of the form:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Consequently, `LAST_VALUE` returns the value at the last row of **the frame ending at the current row (and its peers under RANGE)**. With unique ascending dates, the last row of the frame is usually the current row itself; the output can therefore match `SALARY` on each row, leading learners to think `LAST_VALUE` does nothing.

This is a very common bug: the SQL runs without error, yet fails to return the last value of the entire department as intended.

### 4.2. Retrieving the Last Value of the Entire Partition

To retrieve the salary on the chronologically last row of each department, declare a frame spanning the full partition:

```sql
SELECT employee_id,
       employee_name,
       department_id,
       effective_on,
       salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS department_last_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Here:

- `UNBOUNDED PRECEDING`: starts from the first row of the department.
- `UNBOUNDED FOLLOWING`: ends at the last row of the department.
- `LAST_VALUE` takes expression at the last row of the full-partition frame.

In the lab data, the last row of department 10 is history 5 with `SALARY = NULL`, so `DEPARTMENT_LAST_SALARY` is NULL on all rows of department 10 under the default `RESPECT NULLS`. The last row of department 20 is history 9 with salary 7000, so the result is 7000 on all rows of department 20.

### 4.3. Retrieving the Last Non-NULL Value

If business rules require the most recently recorded salary **that has a value**, use `IGNORE NULLS`:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       LAST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_known_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Result:

- Department 10: the last non-null row is history 4, salary 4500.
- Department 20: the last non-null row is history 9, salary 7000.

`IGNORE NULLS` changes how rows with null expressions are selected; it does not alter source data or turn nulls into 0.

### 4.4. LAST_VALUE with a Frame from Current Row to End of Partition

Another way to retrieve the last value of the partition is:

```sql
LAST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING
)
```

This frame starts at the current row and extends to the end of the partition. The last row of the frame is still the last row of the partition, so `LAST_VALUE` can produce the same value on every row. The difference is that the frame set excludes rows before the current row; this matters when combined with other functions or calculations. For `LAST_VALUE`, both the full-partition frame and the current-to-end frame identify the same last row.

## 5. NTH_VALUE: Retrieving the Value at the Nth Position

General syntax:

```sql
NTH_VALUE(expression, n)
    [FROM FIRST | FROM LAST]
    [RESPECT NULLS | IGNORE NULLS]
OVER (
    [PARTITION BY ...]
    ORDER BY ...
    [windowing_clause]
)
```

- `expression`: the value to retrieve.
- `n`: 1-based position within the ordering of the frame.
- `FROM FIRST`: count from the start of the frame; this is the default.
- `FROM LAST`: count from the end of the frame.
- `RESPECT NULLS`: count nulls toward position; this is the default.
- `IGNORE NULLS`: skip nulls when counting positions.

`NTH_VALUE` returns the value at the Nth position within **the current row's window frame**. If the frame does not yet contain N rows/values under the chosen null mode, the result can be NULL.

### 5.1. Retrieving the Second-Highest Salary in Each Department

```sql
SELECT employee_id,
       employee_name,
       department_id,
       salary,
       NTH_VALUE(salary, 2) FROM FIRST OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_salary
FROM lab_emp_pay_history
ORDER BY department_id, salary DESC NULLS LAST, history_id;
```

The full-partition frame lets every row see the entire group. On the lab data:

- Department 10: the top two values are 6000 and 6000; the second value is 6000.
- Department 20: the top two values are 8000 and 7500; the second value is 7500.

If you need the **second-highest distinct value**, `NTH_VALUE` does not automatically remove duplicates. Depending on requirements, use `DENSE_RANK` or build a distinct set first.

### 5.2. Retrieving the Second Value from the End

```sql
SELECT employee_id,
       department_id,
       salary,
       NTH_VALUE(salary, 2) FROM LAST OVER (
           PARTITION BY department_id
           ORDER BY salary ASC NULLS FIRST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_from_high_end
FROM lab_emp_pay_history;
```

`FROM LAST` counts from the end of the frame according to the declared order. You can express the same intent by reversing the `ORDER BY` direction and using `FROM FIRST`, but watch out for null ordering and ties. Never invert sort direction while forgetting to update `NULLS FIRST/LAST`.

### 5.3. NTH_VALUE with Default Frame Can Return NULL on Early Rows

Example:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       NTH_VALUE(salary, 2) OVER (
           PARTITION BY department_id
           ORDER BY effective_on
       ) AS second_salary_so_far
FROM lab_emp_pay_history
ORDER BY department_id, effective_on;
```

With the default frame `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, early rows in the partition do not yet have two rows in the frame, so `NTH_VALUE(..., 2)` returns NULL. Once the frame expands to at least two rows, the function can return the second value in order. The result is not "the second value of the entire partition" repeated on every row.

If you want the second value of **the entire partition**, declare the full frame:

```sql
NTH_VALUE(salary, 2) OVER (
    PARTITION BY department_id
    ORDER BY salary DESC NULLS LAST, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

### 5.4. NTH_VALUE with IGNORE NULLS

```sql
SELECT employee_id,
       department_id,
       effective_on,
       salary,
       NTH_VALUE(salary, 2) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_known_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

With `IGNORE NULLS`, Oracle skips rows where `SALARY IS NULL` when locating the second position. If the partition has fewer than two non-null values, the result is NULL.

## 6. ROWS and RANGE: Two Different Window Frame Types

This is the foundational concept for understanding why `FIRST_VALUE`, `LAST_VALUE`, and `NTH_VALUE` can return different results despite sharing the same `PARTITION BY` and `ORDER BY`.

### 6.1. ROWS: Frame by Physical Row Count

`ROWS` defines the frame by the number of rows before/after the current row in the analytic order. For example:

```sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
```

means the current row plus up to two rows preceding it. If sort keys repeat, ordering among tied rows must be established with a secondary column so the frame does not depend on nondeterministic order.

### 6.2. RANGE: Frame by Logical Value of the Sort Key

`RANGE` defines the frame based on the value of the `ORDER BY` expression, rather than simply counting rows. With:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

the frame spans from the beginning of the partition up to the current sort key value; **peer** rows sharing the same sort key value are included in the frame together. Thus, if two rows share the same effective date, `CURRENT ROW` under `RANGE` can include both rows.

### 6.3. Example of ROWS vs. RANGE with Ties

Suppose the data is:

| `ID` | `SCORE` |
|---:|---:|
| 1 | 10 |
| 2 | 20 |
| 3 | 20 |
| 4 | 30 |

Two frames:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

and:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

produce different scopes at the rows with `SCORE = 20`:

| ID | SCORE | ROWS Frame (conceptual) | RANGE Frame (conceptual) |
|---:|---:|---|---|
| 1 | 10 | Row 1 | Row 1 |
| 2 | 20 | Rows 1, 2 | Rows 1, 2, 3 |
| 3 | 20 | Rows 1, 2, 3 | Rows 1, 2, 3 |
| 4 | 30 | Rows 1, 2, 3, 4 | Rows 1, 2, 3, 4 |

At row 2, `ROWS` stops at the second physical row; `RANGE` includes peer row 3 because it shares `SCORE = 20`.

### 6.4. Default RANGE Is the Cause of the LAST_VALUE Trap

When `ORDER BY` is present without a specified frame, Oracle uses a default frame equivalent to:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Consequently, `LAST_VALUE(expr)` does not automatically look to the end of the partition. It retrieves the value at the last row of the active frame. To get the partition's last value, use `UNBOUNDED FOLLOWING` or an equivalent construct.

### 6.5. ROWS Typically Needs a Unique Tie-Breaker

If the analytic `ORDER BY` is only `ORDER BY salary DESC` and multiple rows have the same salary, Oracle lacks complete criteria to determine the physical order among tied rows. With `ROWS`, this can cause which row is seen as preceding or following to vary across execution plans.

For deterministic results, add a unique key:

```sql
ORDER BY salary DESC, history_id
```

However, if the goal is to preserve peers by salary value for `RANK`, `RANGE`, or tie semantics, do not add a unique column to the analytic `ORDER BY` if it alters the peer definition. Separate the deterministic output ordering from the sort key used to define ties.

## 7. Full-Partition Frame, Cumulative Frame, and Sliding Frame

Three common frame patterns:

### 7.1. Full Partition

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
```

Every row can see the entire partition. This form fits when you need to repeat the first, last, or partition-wide value on every row.

### 7.2. Cumulative from Start to Current

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

The frame grows progressively as it moves through each row. This form is commonly used for running totals, and also affects `FIRST_VALUE`/`LAST_VALUE`/`NTH_VALUE`:

- `FIRST_VALUE` usually keeps the first value in the partition.
- `LAST_VALUE` returns the value at the current row (or the last peer under a RANGE frame).
- `NTH_VALUE(..., 2)` can be NULL on the first row because the frame does not yet have two rows.

### 7.3. Sliding Frame

```sql
ROWS BETWEEN 2 PRECEDING AND 2 FOLLOWING
```

The frame has at most 5 rows: two preceding rows, the current row, and two following rows. With `FIRST_VALUE`/`LAST_VALUE`, the selected value is the start or end of the sliding window. With `NTH_VALUE`, the Nth value within that window is selected; if the window is shorter than N near partition boundaries, the result can be NULL.

Example:

```sql
SELECT history_id,
       department_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS first_salary_in_recent_3_rows,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS last_salary_in_recent_3_rows
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

At each row, `FIRST_VALUE` returns the salary of the oldest row among the three most recent rows up to the current row; `LAST_VALUE` returns the current row's salary because the frame ends at current row. If you want a symmetric sliding frame including two following rows, use `2 FOLLOWING`, keeping in mind that the query looks ahead to future rows in the analytic order.

## 8. NULL Rules: RESPECT NULLS and IGNORE NULLS

`FIRST_VALUE`, `LAST_VALUE`, and `NTH_VALUE` default to **`RESPECT NULLS`**. This means nulls participate when determining the first, last, or Nth position.

### 8.1. RESPECT NULLS

```sql
LAST_VALUE(salary) RESPECT NULLS OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

If the last row has `SALARY = NULL`, the result is NULL. Since `RESPECT NULLS` is the default, the keyword can be omitted, though writing it explicitly is helpful in lessons or logic where handling missing data should be clear.

### 8.2. IGNORE NULLS

```sql
LAST_VALUE(salary) IGNORE NULLS OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

Oracle skips rows with a null expression when finding the last non-null value in the frame. If no non-null value exists, the result remains NULL.

### 8.3. IGNORE NULLS Is Not the Same as NVL

`IGNORE NULLS` **skips null rows when locating a position**; `NVL`/`COALESCE` replaces a null value with another expression. For example:

```sql
FIRST_VALUE(salary) IGNORE NULLS OVER (...)
```

differs from:

```sql
FIRST_VALUE(NVL(salary, 0)) OVER (...)
```

In the second expression, null is converted to 0 before the function picks the first row; 0 becomes an actual value in the window function's logic. If a salary of 0 has a different business meaning from "salary unknown", the two queries are not interchangeable.

### 8.4. NULLS FIRST/LAST vs. IGNORE NULLS

Two frequently confused concepts:

- `ORDER BY salary DESC NULLS LAST`: determines the **sort position** of rows with null salary.
- `IGNORE NULLS`: skips null values of **the expression evaluated by the analytic function** when picking the first/last/nth value.

Example:

```sql
LAST_VALUE(salary) IGNORE NULLS OVER (
    PARTITION BY department_id
    ORDER BY effective_on DESC NULLS FIRST, history_id DESC
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

`NULLS FIRST` controls row ordering by `EFFECTIVE_ON`; `IGNORE NULLS` applies to the `SALARY` expression. A row with a non-null date but null salary is still skipped when choosing the salary value.

## 9. NTH_VALUE: The Nth Position and Counting Semantics

`NTH_VALUE(expr, n)` requires a valid N according to Oracle rules. N is a positive 1-based ordinal position; N is not a "distinct rank" but rather the position of the row/value within the ordered frame.

### 9.1. NTH_VALUE Does Not Deduplicate Ties

If two rows have the same salary, both still count as two separate rows in the ordering. For example, given the list:

| Row position | Salary |
|---:|---:|
| 1 | 9000 |
| 2 | 8000 |
| 3 | 8000 |
| 4 | 7000 |

`NTH_VALUE(salary, 2)` returns `8000`. `NTH_VALUE(salary, 3)` also returns `8000`. If you need the second-highest **distinct** salary, use `DENSE_RANK` or a distinct subquery instead of `NTH_VALUE`.

### 9.2. FROM FIRST and FROM LAST

```sql
NTH_VALUE(salary, 2) FROM FIRST OVER (...)
```

retrieves the second value counting from the beginning of the frame. Meanwhile:

```sql
NTH_VALUE(salary, 2) FROM LAST OVER (...)
```

retrieves the second value counting from the end of the frame. If you reverse the `ORDER BY` direction, the first and last order also reverses. State the intent clearly in business terms—such as "the second value from the earliest date" or "the second value from the latest date"—before choosing `ORDER BY` and `FROM`.

### 9.3. Frame Does Not Yet Have N Values

With a cumulative frame:

```sql
NTH_VALUE(salary, 3) OVER (
    PARTITION BY department_id
    ORDER BY effective_on
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

the first two rows do not yet have a third row in the frame, so the result is NULL. From the third row onward, the function can return the value at the third position. If `IGNORE NULLS` is used, positions are counted across non-null values of the expression; the frame may need more than N physical rows to contain N values.

## 10. ORDER BY, Ties, and Determinism

Value functions need an ordering to know which row is first, last, and Nth. If the sort key is not unique, multiple peer rows can exist. With `ROWS`, the physical position among peers can be nondeterministic without a tie-breaker.

### 10.1. Using a Unique Key to Identify a Specific Row

```sql
FIRST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY effective_on, history_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

`HISTORY_ID` distinguishes two records sharing the same effective date. When business rules require a single unambiguous "first record", include a stable secondary criterion.

### 10.2. Do Not Break Ties If Ties Are Part of Business Logic

If all employees with the same salary should be treated as tied, do not add `EMPLOYEE_ID` to the analytic `ORDER BY` of a ranking function. With `FIRST_VALUE`/`LAST_VALUE`/`NTH_VALUE`, if multiple rows share the sort key and have different expression values, there is no unique "first/last" unless additional ordering is defined. Decide explicitly:

- Need to pick **one specific row**: add a unique tie-breaker.
- Need to preserve **peer semantics**: use `RANGE` where appropriate and understand peers sharing the frame; or use a ranking function to express ties.
- Need to return **all tied rows**: do not expect `FIRST_VALUE`/`LAST_VALUE` to return multiple rows automatically; use `RANK`/`DENSE_RANK` and filter by rank.

### 10.3. ORDER BY Inside OVER Differs from Final Query ORDER BY

`ORDER BY` inside `OVER (...)` determines the order for computing the function; it **does not guarantee the final row order** of the SELECT statement. To display results ordered by department, date, and ID, add `ORDER BY` at the end:

```sql
SELECT employee_id,
       department_id,
       effective_on,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

## 11. Common Business Examples

### 11.1. Comparing Current Salary with an Employee's Initial Salary

```sql
SELECT employee_id,
       effective_on,
       salary,
       FIRST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY employee_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_known_salary,
       LAST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY employee_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_known_salary
FROM employee_salary_history;
```

The query assumes the table holds multiple history records per employee. The result can be used to compute the change from the first recorded salary to the latest recorded salary, provided `NULL`, effective dates, and ties are clearly defined.

### 11.2. Retrieving the Initial and Latest Status of a Sequence

```sql
SELECT account_id,
       event_time,
       status,
       FIRST_VALUE(status) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS initial_status,
       LAST_VALUE(status) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS latest_status
FROM account_status_events;
```

This is a conceptual example with a hypothetical event table. `EVENT_ID` acts as a tie-breaker if multiple events share the same `EVENT_TIME`. If null statuses should not be selected, add `IGNORE NULLS`.

### 11.3. Retrieving the Third Price Tier per Product Category

```sql
SELECT product_id,
       category_id,
       price,
       NTH_VALUE(price, 3) FROM FIRST OVER (
           PARTITION BY category_id
           ORDER BY price DESC NULLS LAST, product_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS third_price_in_category
FROM products;
```

Each row receives the value at the third position of the category's price list. If a category has fewer than three products, the result may be NULL. If you want the third distinct price, handle duplicates beforehand.

### 11.4. FIRST_VALUE and LAST_VALUE for Comparing Against Highest/Lowest

```sql
SELECT employee_id,
       department_id,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS highest_salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS lowest_salary
FROM employees;
```

Under descending order, the first row is the highest salary and the last row is the lowest salary (nulls are pushed to the end; if nulls exist, `RESPECT NULLS` can cause `LAST_VALUE` to be null). If you need the lowest non-null salary, use `IGNORE NULLS` or filter data per business requirements.

## 12. Common Errors

| Symptom / Misconception | Cause | Solution |
|---|---|---|
| `LAST_VALUE` returns the same value as the current row | Default frame ends at current row | Declare `ROWS/RANGE ... UNBOUNDED FOLLOWING` if partition end is needed |
| `NTH_VALUE(..., 2)` returns NULL on early rows | Cumulative frame does not yet have two positions | Use a full-partition frame if the second value of the entire group is needed |
| `FIRST_VALUE` returns NULL even though later rows have values | First row in frame has NULL expression under default RESPECT NULLS | Use IGNORE NULLS if business logic skips nulls |
| `LAST_VALUE` returns NULL across the whole partition | Last row in partition has NULL expression | Use IGNORE NULLS if the last known value is needed |
| Results change between runs on ties | Analytic ORDER BY is underspecified | Add a unique tie-breaker key if a specific row must be chosen |
| Adding ID removes ties | ID was placed inside the sort key used to define peers | Separate the tie key inside analytic ORDER BY from the outer display order |
| `ROWS` and `RANGE` return different results | ROWS counts rows; RANGE groups peers by sort key value | Choose the frame matching the intended meaning and test duplicate sort keys |
| Thinking ORDER BY inside OVER sorts the final output | Analytic ORDER BY only controls calculation | Add ORDER BY at the end of the SELECT statement |
| Filtering an analytic alias directly in WHERE fails | WHERE is processed before analytic functions in the query block | Wrap in a CTE or inline view |
| NTH_VALUE returns repeated values when distinct tiers were expected | NTH_VALUE counts row positions, not distinct values | Use DENSE_RANK or a distinct set |
| Used NULLS LAST yet NULL is still picked | NULLS LAST only sorts; the frame still includes null rows | Use IGNORE NULLS or filter out nulls as required |

## 13. Controlled Practice Lab

Exercises use `LAB_EMP_PAY_HISTORY` created in section 2. Run only on an authorized DEV/TEST schema and the right PDB/service. Do not run DDL or cleanup operations on production.

### Exercise 1 — FIRST_VALUE Across the Full Partition

```sql
SELECT history_id, department_id, effective_on, salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS first_salary
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Record the earliest value by date for each department and explain why that value repeats across rows in the same department.

### Exercise 2 — Default LAST_VALUE vs. Full-Partition Frame

Run both queries:

```sql
SELECT history_id, department_id, effective_on, salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
       ) AS last_default
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

```sql
SELECT history_id, department_id, effective_on, salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_full_partition
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Compare the outputs and explain the default frame trap.

### Exercise 3 — RESPECT NULLS vs. IGNORE NULLS

```sql
SELECT history_id, department_id, effective_on, salary,
       LAST_VALUE(salary) RESPECT NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_respect,
       LAST_VALUE(salary) IGNORE NULLS OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS last_ignore
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Explain why department 10 produces different results between the two columns.

### Exercise 4 — Full-Partition NTH_VALUE

```sql
SELECT history_id, department_id, salary,
       NTH_VALUE(salary, 2) FROM FIRST OVER (
           PARTITION BY department_id
           ORDER BY salary DESC NULLS LAST, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS second_salary
FROM lab_emp_pay_history
ORDER BY department_id, salary DESC NULLS LAST, history_id;
```

Identify the second value by row position, then explain why tied values still occupy two positions.

### Exercise 5 — NTH_VALUE with a Cumulative Frame

```sql
SELECT history_id, department_id, effective_on, salary,
       NTH_VALUE(salary, 2) OVER (
           PARTITION BY department_id
           ORDER BY effective_on, history_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS second_so_far
FROM lab_emp_pay_history
ORDER BY department_id, effective_on, history_id;
```

Observe the first rows of each partition and explain why having fewer than two rows produces NULL.

### Exercise 6 — ROWS and RANGE with Peers

Create a small lab table with duplicate sort key values, then compare `LAST_VALUE` or an analytic aggregate using:

```sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

and:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

Observe the frame at the first row of the peer group and explain the difference between logical offset and physical row offset.

### Exercise 7 — Distinguishing NTH_VALUE and DENSE_RANK

Given a salary set with values `10000, 9000, 9000, 8000`, apply `NTH_VALUE(salary, 3)` and `DENSE_RANK()`. Explain why the third value by row position can be 9000 while the third distinct salary level is 8000.

### Lab Data Cleanup

Only after confirming the table was created by you in DEV/TEST and no one else is using it:

```sql
DROP TABLE lab_emp_pay_history PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data without sending it to the recycle bin; this is a DDL operation with an implicit commit. Do not run it on production or any table outside the lab scope.

## 14. Review Questions

**Question 1.** What value does `FIRST_VALUE(salary)` return?

**Answer:** The expression value at the first row in the window frame according to the analytic `ORDER BY`.

**Question 2.** Why does `LAST_VALUE` often fail to return the partition's last value if the windowing clause is omitted?

**Answer:** Because the default frame when ORDER BY is present is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`; the frame ends at the current row/peers rather than extending to the end of the partition.

**Question 3.** How do you write the frame so `LAST_VALUE` sees the entire partition?

**Answer:** `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` (or an equivalent appropriate frame).

**Question 4.** Does `NTH_VALUE(expr, 2)` mean the second-largest distinct value?

**Answer:** No. It is the value at the second position in the frame; ties still occupy separate positions. For the second distinct value, consider `DENSE_RANK`.

**Question 5.** What does `FROM LAST` in `NTH_VALUE` do?

**Answer:** Counts position N from the end of the window frame rather than from the beginning.

**Question 6.** What NULL handling mode do these three value functions use by default?

**Answer:** `RESPECT NULLS`; you can specify `IGNORE NULLS` to skip null expression values when picking a position.

**Question 7.** Is `NULLS LAST` the same as `IGNORE NULLS`?

**Answer:** No. `NULLS LAST` sorts null rows to the end; `IGNORE NULLS` skips null values when the function determines the first/last/nth expression.

**Question 8.** How do `ROWS` and `RANGE` differ?

**Answer:** `ROWS` defines the frame by physical row count in order; `RANGE` defines it by sort key value and includes peers with the same value at the boundary.

**Question 9.** Why does ROWS need a tie-breaker when the sort key is not unique?

**Answer:** To define a deterministic physical order among tied rows and make results repeatable/deterministic.

**Question 10.** Does `ORDER BY` inside `OVER(...)` sort the final SELECT output?

**Answer:** No. It only controls the evaluation order of the analytic function; to sort displayed output, an ORDER BY in the outermost query is required.

## Conclusion

**`FIRST_VALUE`**, **`LAST_VALUE`**, and **`NTH_VALUE`** pick the first, last, or Nth value within **the current window frame**, not automatically across the entire partition. When an analytic `ORDER BY` is present without a windowing clause, Oracle uses a default frame equivalent to `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. This is a common reason why `LAST_VALUE` returns only the current row/peer value instead of the group's final value. To retrieve the last value of the full partition, declare the frame through `UNBOUNDED FOLLOWING`.

`ROWS` defines frames by physical rows, while `RANGE` defines them by sort key value and handles peers sharing the same value inside the frame. `RESPECT NULLS` is the default; `IGNORE NULLS` skips nulls when picking values, unlike `NULLS FIRST/LAST` which only governs sort placement. `NTH_VALUE` counts row positions in the frame rather than deduplicating to find the Nth distinct value. When designing queries, specify the partition, sort key, tie-breaker, frame, and NULL policy explicitly, and add an outermost `ORDER BY` whenever a deterministic output order is needed.

## Oracle Reference Documentation

- [Oracle Database 19c — FIRST_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FIRST_VALUE.html): syntax, window frame, and RESPECT/IGNORE NULLS.
- [Oracle Database 19c — LAST_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/LAST_VALUE.html): LAST_VALUE behavior and default windowing clause notes.
- [Oracle Database 19c — NTH_VALUE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NTH_VALUE.html): FROM FIRST/FROM LAST and RESPECT/IGNORE NULLS.
- [Oracle Database 19c — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): analytic function evaluation order, partitioning, ordering, and windowing clause.
- [Oracle Database 19c — Windowing Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): ROWS/RANGE rules and default frames in the analytic clause.
