# KEEP (DENSE_RANK FIRST/LAST) in Oracle Aggregations

In Oracle Database, you sometimes need to compute an aggregate value, but only over rows that hold the first or last rank according to a given criterion. For example:

- Find the **highest salary among the earliest-hired employees** in each department.
- Compute the **total amount of transactions on the latest date** in each account.
- Count the **number of employees tied** at the highest sales figure.
- Retrieve the lowest commission value among employees with the highest commission rate.

Oracle provides the **`KEEP (DENSE_RANK FIRST ...)`** and **`KEEP (DENSE_RANK LAST ...)`** syntax to address these requirements. The syntax is commonly used with aggregate functions such as `MIN`, `MAX`, `SUM`, `AVG`, or `COUNT`.

The core idea is that `KEEP` performs two consecutive steps:

1. Ranks rows by the expression in `ORDER BY` using `DENSE_RANK`, then selects all rows belonging to the first rank (`FIRST`) or last rank (`LAST`).
2. Applies the specified aggregate function to the target expression, but only over the selected subset of rows.

Therefore, `KEEP` **does not pick just a single row by default**. If multiple rows tie at the first or last rank, the aggregate function processes all of those rows. Understanding ties, `NULL`, `ASC`/`DESC` ordering, and the difference between aggregate and analytic usage is essential to avoid incorrect results.

## 1. General Syntax and Meaning

Common structure:

```sql
aggregate_function(expression)
    KEEP (
        DENSE_RANK FIRST
        ORDER BY sort_expression [ASC | DESC] [NULLS FIRST | NULLS LAST]
    )
```

Or using `LAST`:

```sql
aggregate_function(expression)
    KEEP (
        DENSE_RANK LAST
        ORDER BY sort_expression [ASC | DESC] [NULLS FIRST | NULLS LAST]
    )
```

You can add `OVER (PARTITION BY ...)` to use the analytic form:

```sql
aggregate_function(expression)
    KEEP (DENSE_RANK FIRST ORDER BY sort_expression)
    OVER (PARTITION BY group_expression)
```

Where:

- `aggregate_function`: the aggregate function applied to the retained rows, typically `MIN`, `MAX`, `SUM`, `AVG`, `COUNT`, `VARIANCE`, or `STDDEV`.
- `expression`: the value to aggregate; it does not have to be the column used for ranking.
- `DENSE_RANK FIRST`: selects the set of rows holding the first dense rank in the declared order.
- `DENSE_RANK LAST`: selects the set of rows holding the last dense rank in the declared order.
- `ORDER BY`: defines the ranking criteria and direction; multiple expressions are allowed.
- `OVER (PARTITION BY ...)`: turns the aggregation into an analytic computation, evaluated separately per partition and returned alongside each row.

### 1.1. How It Works

```text
Rows within a group
          |
          v
Rank by ORDER BY inside KEEP
          |
          v
DENSE_RANK FIRST or DENSE_RANK LAST
          |
          v
Keep all rows in first/last rank
          |
          v
Apply MIN / MAX / SUM / AVG / COUNT...
          |
          v
One aggregate value per group/partition
```

Example:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC
)
```

The expression above **does not mean** "get the highest salary across the entire table". It means:

1. Find the earliest hire date according to `HIRE_DATE ASC`.
2. Keep all employees whose hire date falls in the first rank.
3. Compute `MAX(SALARY)` over those retained employees.

If three people share the earliest hire date, all three participate in `MAX`.

## 2. FIRST and LAST Depend on ORDER BY Direction

`FIRST` and `LAST` refer to positions in the **declared ordering**, not always the intuitively smallest or largest value.

| Ranking expression | `DENSE_RANK FIRST` selects | `DENSE_RANK LAST` selects |
|---|---|---|
| `ORDER BY hire_date ASC` | Earliest date | Latest date |
| `ORDER BY hire_date DESC` | Latest date | Earliest date |
| `ORDER BY salary ASC` | Lowest salary | Highest salary |
| `ORDER BY salary DESC` | Highest salary | Lowest salary |

Accordingly, these two expressions can select the same group of rows when ignoring NULLs:

```sql
MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date DESC)
```

and:

```sql
MAX(salary) KEEP (DENSE_RANK LAST ORDER BY hire_date ASC)
```

Both select rows with the latest hire date and then retrieve the highest salary in that set. Still, choose the form that is easiest to read for business logic and state the sort direction clearly.

### 2.1. Multiple Columns in ORDER BY

You can rank by multiple criteria:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY hire_date ASC, employee_id ASC
)
```

Here, the retained row set consists of rows holding the leading sort-key combination from left to right. `EMPLOYEE_ID` can break ties among people hired on the same date. If `EMPLOYEE_ID` is unique, the result typically reduces to a single row in the first rank.

**Note:** adding a column to `ORDER BY` can alter the tie set. If business logic requires aggregating all employees hired on the same earliest date, do not add a unique key to the ordering inside `KEEP`. Only add a secondary criterion when you genuinely want to break ties among those rows.

## 3. Preparing Practice Data

The examples use a sample table `LAB_KEEP_EMPLOYEES`, storing employees, departments, hire dates, salaries, and commission percentages. The data intentionally includes multiple people sharing hire dates and salaries to observe `DENSE_RANK FIRST/LAST` with ties.

Only create tables in a **DEV/TEST** schema granted `CREATE TABLE` privileges and quota. Before running DDL, confirm the service, PDB, and user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 3.1. Create the Lab Table

```sql
CREATE TABLE lab_keep_employees (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    hire_date     DATE,
    salary        NUMBER(12, 2),
    commission_pct NUMBER(5, 2)
);
```

`HIRE_DATE`, `SALARY`, and `COMMISSION_PCT` allow `NULL` to illustrate how nulls participate in ordering and aggregation. In real systems, determine the business meaning of each null; do not automatically assume null means 0 or a far-future date.

### 3.2. Load Sample Data

```sql
INSERT ALL
    INTO lab_keep_employees VALUES (101, 'An',    10, DATE '2020-01-01', 5000, 0.10)
    INTO lab_keep_employees VALUES (102, 'Binh',  10, DATE '2020-01-01', 6000, 0.20)
    INTO lab_keep_employees VALUES (103, 'Chi',   10, DATE '2021-01-01', 7000, 0.15)
    INTO lab_keep_employees VALUES (104, 'Dung',  10, DATE '2022-01-01', 6500, NULL)
    INTO lab_keep_employees VALUES (105, 'Em',    10, DATE '2022-01-01', 6800, 0.05)
    INTO lab_keep_employees VALUES (201, 'Giang', 20, DATE '2019-06-01', 8000, 0.10)
    INTO lab_keep_employees VALUES (202, 'Ha',    20, DATE '2020-06-01', 7500, NULL)
    INTO lab_keep_employees VALUES (203, 'Khanh', 20, DATE '2020-06-01', 7800, 0.20)
    INTO lab_keep_employees VALUES (204, 'Lan',   20, DATE '2021-06-01', 7200, 0.15)
    INTO lab_keep_employees VALUES (301, 'Minh',  30, DATE '2023-01-01', 6000, NULL)
    INTO lab_keep_employees VALUES (302, 'Nhi',   30, DATE '2023-01-01', 6200, 0.10)
    INTO lab_keep_employees VALUES (303, 'Oanh',  30, DATE '2024-01-01', 6100, 0.20)
    INTO lab_keep_employees VALUES (401, 'Phuc',  40, NULL,              5500, 0.12)
    INTO lab_keep_employees VALUES (402, 'Quynh', 40, NULL,              5700, 0.18)
    INTO lab_keep_employees VALUES (403, 'Son',   40, DATE '2024-05-01', 5900, 0.15)
SELECT 1 FROM dual;

COMMIT;
```

The dataset has four departments:

- Department 10: two employees hired on the earliest date (2020-01-01) and two employees on the latest date (2022-01-01).
- Department 20: two employees on 2020-06-01.
- Department 30: two employees on 2023-01-01.
- Department 40: two employees with `HIRE_DATE = NULL` and one employee with a defined hire date.

### 3.3. View Source Data

```sql
SELECT employee_id, employee_name, department_id,
       hire_date, salary, commission_pct
FROM lab_keep_employees
ORDER BY department_id, hire_date NULLS LAST, employee_id;
```

The final `ORDER BY` only sorts the displayed output. It does not dictate how `KEEP` ranks rows; that is governed separately by the `ORDER BY` inside `KEEP`.

## 4. KEEP with GROUP BY: Aggregating the First/Last Rows in Each Group

Example requirement: "For each department, find the earliest hire date, the highest salary among employees hired earliest, and the number of employees sharing that earliest hire date."

```sql
SELECT department_id,
       MIN(hire_date) AS earliest_hire_date,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS highest_salary_at_earliest_hire,
       MIN(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS lowest_salary_at_earliest_hire,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS employees_at_earliest_hire
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Analysis:

1. `GROUP BY department_id` creates one group per department.
2. `MIN(hire_date)` gets the earliest hire date of the group.
3. `DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST` selects all rows with the earliest non-null hire date; if dates tie, all rows in the first rank are retained.
4. `MAX(salary)` retrieves the highest salary within the retained group.
5. `MIN(salary)` retrieves the lowest salary within that same retained group.
6. `COUNT(*)` counts rows in the retained group, even if another data column is null.

Result on lab data:

| Department | Earliest hire date | Highest salary in first group | Lowest salary in first group | Count in first group |
|---:|---|---:|---:|---:|
| 10 | 2020-01-01 | 6000 | 5000 | 2 |
| 20 | 2019-06-01 | 8000 | 8000 | 1 |
| 30 | 2023-01-01 | 6200 | 6000 | 2 |
| 40 | 2024-05-01 | 5900 | 5900 | 1 |

Department 40 has two `HIRE_DATE = NULL` rows. Because the expression uses `ASC NULLS LAST`, nulls are placed after non-null dates. `DENSE_RANK FIRST` picks the defined date 2024-05-01, not the null rows.

### 4.1. KEEP with LAST: Latest-Hired Employees Group

```sql
SELECT department_id,
       MAX(hire_date) AS latest_hire_date,
       MIN(salary) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS lowest_salary_at_last_rank,
       MAX(salary) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS highest_salary_at_last_rank,
       COUNT(*) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS employees_at_last_rank
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

With `ASC NULLS LAST`, `DENSE_RANK LAST` selects the latest date **including null in the last position if the partition contains nulls**. Thus, on the lab data:

- Department 10: last date 2022-01-01; Dung and Em are selected, lowest salary 6500, highest 6800, count 2.
- Department 20: last date 2021-06-01; Lan is selected.
- Department 30: last date 2024-01-01; Oanh is selected.
- Department 40: because the two null dates are sorted last by `NULLS LAST`, the last-rank group consists of Phuc and Quynh; `MAX(hire_date)` still returns 2024-05-01, yet `KEEP LAST` selects the rows with `HIRE_DATE = NULL`.

The department 40 example shows that `MAX(hire_date)` and `DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST` may not describe the same set of rows when nulls exist. If the goal is "the latest non-null hire date", sort `DESC NULLS LAST` and pick `FIRST`, or filter out nulls per business rules.

## 5. FIRST/LAST with ASC and DESC in Practice

When you need the latest hire date group while ignoring null dates, the clearest expression is:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
)
```

`DESC` puts the latest dates first; `NULLS LAST` ensures rows missing dates are not prioritized; `FIRST` selects the latest date that has a value. This is usually more intuitive than `DENSE_RANK LAST ORDER BY hire_date ASC` when the column allows nulls.

| Goal | Suggested KEEP expression |
|---|---|
| Aggregate at the earliest non-null date | `... KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST)` |
| Aggregate at the latest non-null date | `... KEEP (DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST)` |
| Aggregate at the largest date, accepting NULL as the last rank | `... KEEP (DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST)` |
| Aggregate at the smallest date, accepting NULL as the last rank under DESC | `... KEEP (DENSE_RANK LAST ORDER BY hire_date DESC NULLS LAST)` |

Write the business rule for nulls accurately instead of mechanically memorizing "FIRST is smallest, LAST is largest".

## 6. Which Aggregates Does KEEP Support?

`KEEP` is a modifier for aggregate functions. Commonly used functions include:

| Aggregate | Meaning over retained rows |
|---|---|
| `MIN(expr)` | Minimum value of expr in the tie set |
| `MAX(expr)` | Maximum value of expr in the tie set |
| `SUM(expr)` | Sum of expr across tied rows |
| `AVG(expr)` | Average of expr across tied rows |
| `COUNT(expr)` | Count of tied rows where expr is non-null |
| `COUNT(*)` | Count of all tied rows, regardless of whether expr is null |
| `VARIANCE(expr)` | Variance of expr in the tie set |
| `STDDEV(expr)` | Standard deviation of expr in the tie set |

Example with the latest-hired employee group (latest non-null date):

```sql
SELECT department_id,
       SUM(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS total_salary_of_latest_hires,
       AVG(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS average_salary_of_latest_hires,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS latest_hire_count
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

If multiple employees share the same latest date, `SUM` totals all of their salaries; `AVG` averages non-null salaries; `COUNT(*)` counts every row on that date.

### 6.1. COUNT(*) and COUNT(expression) Differ

Suppose the retained rows have `COMMISSION_PCT` values `0.10`, `NULL`, and `0.20`:

```sql
COUNT(*) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

returns `3`, while:

```sql
COUNT(commission_pct) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

returns `2`. `COUNT(*)` counts rows; `COUNT(expression)` counts only non-null expression values in the first/last rank set.

### 6.2. MIN/MAX After KEEP Do Not Necessarily Return a Single Underlying Row

Suppose two employees were hired on the same first date, one earning 5000 and one earning 6000. Then:

```sql
MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date)
```

returns `6000`, whereas:

```sql
MIN(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date)
```

returns `5000`. Both are valid because they aggregate over **the same tie set** using different aggregate functions.

### 6.3. When the Aggregated Expression Is Entirely NULL

If all retained rows have `SALARY = NULL`:

- `MIN(salary) KEEP (...)` returns NULL.
- `MAX(salary) KEEP (...)` returns NULL.
- `SUM(salary) KEEP (...)` returns NULL.
- `AVG(salary) KEEP (...)` returns NULL.
- `COUNT(salary) KEEP (...)` returns 0.
- `COUNT(*) KEEP (...)` still counts the number of retained rows.

Nulls in the **sort key** and nulls in the **aggregated expression** are two separate concerns. A row can be selected because its sort key ranks first, while the expression being aggregated is null.

## 7. Ties: DENSE_RANK FIRST/LAST Retains All Tied Rows

`DENSE_RANK` assigns the same rank to rows with identical combinations of values in the order expression. `KEEP` selects the set of rows holding the first or last rank. Thus, if multiple rows share the same sort key at the boundary, **all of them participate in the aggregate**.

Example:

| Employee | Hire date | Salary |
|---|---|---:|
| An | 2020-01-01 | 5000 |
| Binh | 2020-01-01 | 6000 |
| Chi | 2021-01-01 | 7000 |

Expression:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC
)
```

selects An and Binh because both have the earliest date, and then computes `MAX(5000, 6000) = 6000`.

### 7.1. Adding a Tie-Breaker Changes the Retained Set

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC, employee_id ASC
)
```

If `EMPLOYEE_ID` is unique, only one row is selected in the first rank. The result is then the salary of the person with the earliest hire date and smallest ID in that group. This is different logic from "aggregate across all employees hired on the same earliest date".

### 7.2. Multiple ORDER BY Columns Create Ties on the Entire Combination

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY hire_date ASC, commission_pct DESC
)
```

First rank is determined by earliest hire date; if multiple people share the date, higher commission takes priority. Only rows matching the leading combination of both `HIRE_DATE` and `COMMISSION_PCT` tie in the first rank. Rows on the same date with different commissions are not in the same first rank.

If `COMMISSION_PCT` can be null, specify `NULLS FIRST/LAST` as required. With multiple sort keys, null ordering applies per expression.

## 8. NULLs in KEEP's ORDER BY

Oracle has default ordering for nulls:

- `ASC`: defaults to `NULLS LAST`.
- `DESC`: defaults to `NULLS FIRST`.

Because `KEEP` picks FIRST/LAST according to this ordering, nulls can become the selected group if not specified explicitly.

### 8.1. Selecting the Earliest Non-Null Date

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

The smallest date comes first; null dates go last. If at least one defined date exists, FIRST selects that earliest date.

### 8.2. Selecting the Latest Non-Null Date

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
)
```

The largest date comes first in descending order; nulls go last. This is a clean pattern for retrieving data from the latest known date.

### 8.3. LAST with ASC NULLS LAST Can Select NULL

```sql
MAX(salary) KEEP (
    DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
)
```

If the partition has rows with `HIRE_DATE IS NULL`, the null group sits at the end and is picked by `DENSE_RANK LAST`. This may not be intended when the author wants the latest hire date. Switch to `DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST` or filter out nulls if that is the requirement.

### 8.4. NULLs in the Aggregated Expression

Suppose the first hire date is clearly determined, yet some people in that group have null salary. `KEEP` still retains those rows by sort key; afterward `MIN`/`MAX`/`AVG`/`SUM` handle nulls according to regular aggregate rules. `COUNT(*)` and `COUNT(salary)` can differ as shown earlier.

## 9. Combining KEEP with GROUP BY and HAVING

`KEEP` commonly appears in queries with `GROUP BY` to return one row per group.

```sql
SELECT department_id,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS max_salary_of_earliest_hires,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS earliest_hire_count
FROM lab_keep_employees
GROUP BY department_id
HAVING COUNT(*) >= 2
ORDER BY department_id;
```

`HAVING COUNT(*) >= 2` filters department groups that have at least two rows overall. It does not filter by the number of people selected by `KEEP`; if you need a condition based on the number of rows in the first rank, repeat the `COUNT(*) KEEP (...)` aggregate in `HAVING`:

```sql
HAVING COUNT(*) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
) >= 2
```

The second condition retains only departments with at least two employees tied on the earliest hire date. Distinguish group-wide `COUNT(*)` from `COUNT(*) KEEP (...)` over the first/last rank set.

## 10. KEEP in Analytic Form with OVER(PARTITION BY)

`KEEP` can be used as an analytic function. When adding `OVER (PARTITION BY ...)`, Oracle computes the result separately for each partition and repeats it across the rows of that partition, rather than collapsing into one row per group.

```sql
SELECT employee_id,
       employee_name,
       department_id,
       hire_date,
       salary,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) OVER (
           PARTITION BY department_id
       ) AS highest_salary_among_earliest_hires
FROM lab_keep_employees
ORDER BY department_id, hire_date NULLS LAST, employee_id;
```

Each employee still appears as one row. The column `HIGHEST_SALARY_AMONG_EARLIEST_HIRES` is computed within that employee's department and repeated on every row in the same department.

### 10.1. Comparing Aggregate and Analytic KEEP

| Syntax | Result |
|---|---|
| `MAX(salary) KEEP (...)` in a query with `GROUP BY department_id` | One row per department |
| `MAX(salary) KEEP (...) OVER (PARTITION BY department_id)` | Keeps each employee row, adding the department's aggregate value |
| `MAX(salary) KEEP (...)` without GROUP BY/OVER | One aggregate result over the entire input row set |

Example without `GROUP BY`:

```sql
SELECT MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
) AS max_salary_among_earliest_hires
FROM lab_keep_employees;
```

The query returns one row for the whole table, taking the maximum salary among the employees with the earliest hire date across the company.

### 10.2. KEEP's OVER Is Not the Window Frame of FIRST_VALUE/LAST_VALUE

In analytic `KEEP` syntax, `ORDER BY` sits inside `KEEP (DENSE_RANK ...)`; `OVER` is used for partitioning. Do not confuse it with:

```sql
LAST_VALUE(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
```

This is an analytic value function with a window frame. Meanwhile:

```sql
MAX(salary) KEEP (
    DENSE_RANK LAST ORDER BY hire_date
) OVER (PARTITION BY department_id)
```

is an aggregate applied over the set of rows holding the last dense rank of each partition. Both expressions can solve related questions, yet their semantics and tie handling differ.

## 11. How Does KEEP Differ from FIRST_VALUE, LAST_VALUE, and ROW_NUMBER?

The names are easy to confuse, but their purposes differ:

| Tool | What does it select? | Tie handling |
|---|---|---|
| `FIRST_VALUE(expr)` | Value of expr at the first row of the window frame | Returns one value from the first row; ties may require a tie-breaker |
| `LAST_VALUE(expr)` | Value of expr at the last row of the window frame | Returns one value from the last row; watch out for the default frame |
| `NTH_VALUE(expr, n)` | Value of expr at the Nth position in the frame | Counts row position, does not aggregate all ties |
| `ROW_NUMBER()` | Assigns a distinct number to each row | Ties are still split into different sequence numbers |
| `RANK()` | Assigns rank to rows by sort key | Tied rows get same rank, with gaps |
| `DENSE_RANK()` | Assigns dense rank to rows by sort key | Tied rows get same rank, no gaps |
| `MAX(expr) KEEP (DENSE_RANK FIRST/LAST ...)` | Aggregates expr over all rows in first/last rank | All tied rows participate in the aggregate |

### 11.1. When You Want All Columns of One Specific Row, Use ROW_NUMBER

If the requirement is "get one single earliest-hired employee; on date ties, pick the smallest ID", use:

```sql
WITH ranked AS (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY hire_date ASC NULLS LAST, employee_id
           ) AS rn
    FROM lab_keep_employees e
)
SELECT employee_id, employee_name, department_id,
       hire_date, salary, commission_pct
FROM ranked
WHERE rn = 1;
```

`ROW_NUMBER` selects one complete row according to the tie-breaker rule. If you use `KEEP` separately for each column, the aggregates may pull values from different tied rows.

### 11.2. Be Careful When Retrieving Multiple Columns with KEEP

Example:

```sql
SELECT department_id,
       MIN(employee_name) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS selected_name,
       MAX(salary) KEEP (
           DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST
       ) AS selected_salary
FROM lab_keep_employees
GROUP BY department_id;
```

If multiple employees share the last date:

- `MIN(employee_name)` may pick the smallest name by collation.
- `MAX(salary)` may pick the highest salary.

These two values **do not necessarily belong to the same employee**. Pairing `SELECTED_NAME` and `SELECTED_SALARY` can fabricate a combination that does not exist in any source row. If you need columns from the same record, use `ROW_NUMBER` with deterministic ordering or another method guaranteeing the same row is selected.

### 11.3. When You Need All Tied Rows, Use Analytic DENSE_RANK

If you want to return all employees on each department's earliest hire date:

```sql
WITH ranked AS (
    SELECT e.*,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY hire_date ASC NULLS LAST
           ) AS hire_rank
    FROM lab_keep_employees e
)
SELECT employee_id, employee_name, department_id, hire_date, salary
FROM ranked
WHERE hire_rank = 1
ORDER BY department_id, employee_id;
```

This is how to retrieve **the rows** holding the first rank; `KEEP` is appropriate when you want to aggregate one or more expressions over that set of rows.

## 12. Multiple Criteria in KEEP and How Peers Are Determined

`ORDER BY` inside `KEEP` can contain multiple columns or expressions:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY hire_date ASC NULLS LAST,
             commission_pct DESC NULLS LAST
)
```

Oracle ranks from the first expression to the next. Hire date takes precedence; commission is checked only when hire dates are equal. The row set at the first dense rank consists of rows sharing the leading sort-key combination.

If commission is null, `NULLS LAST` puts nulls after known commission values within the earliest-hire-date group. If all commissions in that group are null, those null rows tie in the first rank under the sort-key combination.

### 12.1. Ties Are Not Determined Only by the First Column

With:

```sql
ORDER BY hire_date, commission_pct
```

two rows with the same `HIRE_DATE` but different `COMMISSION_PCT` do not tie, because the full sort-key combination differs. If the intent is to tie strictly by hire date, put only `HIRE_DATE` inside `KEEP`'s `ORDER BY`.

### 12.2. Ranking by Expression

You can rank by an expression:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY TRUNC(hire_date, 'MM') ASC NULLS LAST
)
```

This expression selects the group of employees belonging to the earliest hire month, rather than the earliest specific day. When applying a function to a column, consider data type, nulls, time zone (if applicable), and index reusability; the expression inside `KEEP` dictates which group is selected.

## 13. Combining KEEP with Other Aggregates

### 13.1. Counting Tied Employees at the Highest Salary

```sql
SELECT department_id,
       MAX(salary) AS highest_salary,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY salary DESC NULLS LAST
       ) AS employees_at_highest_salary
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

`DENSE_RANK FIRST ORDER BY salary DESC NULLS LAST` selects rows with the highest non-null salary; `COUNT(*)` counts all rows in that set. In department 10, the highest-paid employee is Chi (7000), so the tied count is 1. If two people shared the highest salary, the count would be 2.

### 13.2. Total Commission of the Highest-Paid Group

```sql
SELECT department_id,
       SUM(commission_pct) KEEP (
           DENSE_RANK FIRST ORDER BY salary DESC NULLS LAST
       ) AS commission_sum_at_top_salary
FROM lab_keep_employees
GROUP BY department_id;
```

If multiple people share the highest salary, `SUM` adds all of their commission rates. If one person's commission is null, `SUM` ignores that null; if all are null, the result is null.

### 13.3. Average Salary in the Latest-Hired Group

```sql
SELECT department_id,
       AVG(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS avg_salary_of_latest_hire_date
FROM lab_keep_employees
GROUP BY department_id;
```

This is the average salary across all employees on the latest known hire date. If multiple people share that date, all are included in the calculation.

### 13.4. Grouping and Filtering Groups with HAVING

```sql
SELECT department_id,
       COUNT(*) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS first_hire_count
FROM lab_keep_employees
GROUP BY department_id
HAVING COUNT(*) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
) >= 2
ORDER BY department_id;
```

The query retains only departments that have at least two employees sharing the earliest hire date. In the lab data, departments 10 and 30 have two people on the earliest date; department 20 has one; department 40 has only one defined earliest date because nulls are sorted last.

## 14. Type Conversion and Expression Data Types

`KEEP` does not override Oracle's data type rules. The aggregated expression must be valid for the aggregate function called; the `ORDER BY` expression must be comparable according to its data type.

### 14.1. Do Not Compare Dates as Strings

Do not write:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date_text ASC
)
```

if `HIRE_DATE_TEXT` holds dates in inconsistent string formats. Character sort order may not match chronological order. Store dates as `DATE`/`TIMESTAMP`, or parse with an explicit format:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST
    ORDER BY TO_DATE(hire_date_text, 'YYYY-MM-DD') ASC NULLS LAST
)
```

Use this only when all values conform to the exact format; invalid data will cause the query to fail. Better yet, validate data on ingestion and use date data types in the schema.

### 14.2. Numeric Types and Precision

If the aggregated expression is `NUMBER`, the aggregate result follows Oracle numeric rules. Do not pass formatted currency strings with separators into `SUM`/`AVG` relying on implicit conversion; parse to `NUMBER` using an explicit format/NLS model or bind numeric values from the application.

### 14.3. Character Types and Collation

When `ORDER BY` inside KEEP uses a character expression such as `employee_name`, FIRST/LAST results depend on the active collation/character comparison rules. `MIN(employee_name)` also applies character comparison rules when picking the smallest value in a tie set. For multilingual data, confirm collation and test case sensitivity, diacritics, and Unicode behavior.

## 15. Performance and Indexes

`KEEP` expresses query semantics, not a guarantee that Oracle will use a specific index. The optimizer may choose a full table scan, index scan, sort/group operation, or another plan based on statistics and data structure.

### 15.1. Indexes Can Support Grouping and Ordering

For the query:

```sql
SELECT department_id,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS max_salary_at_first_hire
FROM lab_keep_employees
GROUP BY department_id;
```

you can evaluate an index on the grouping and sort key columns, for example:

```sql
CREATE INDEX ix_lab_keep_dept_hire
ON lab_keep_employees (department_id, hire_date);
```

This is merely a candidate for testing. Creating an index increases storage and `INSERT`/`UPDATE`/`DELETE` overhead; it does not guarantee the optimizer will use it or eliminate sorting altogether. Measure on data with realistic size and distribution.

### 15.2. GROUP BY and KEEP May Need to Process Tie Sets

Oracle must identify the first/last dense rank group in each group or partition and then compute the aggregate. When tables are large with many groups, cost depends on row count, sort keys, cardinality, and memory/TEMP. Do not replace `KEEP` with multiple correlated subqueries assuming they will be faster; compare execution plans and data access counts.

### 15.3. Avoid Unnecessary Repeated Calculations

If a query needs multiple aggregates over the same tie set, you can repeat `KEEP` with the same `ORDER BY`:

```sql
SELECT department_id,
       MIN(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST),
       MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST),
       AVG(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST),
       COUNT(*) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST)
FROM lab_keep_employees
GROUP BY department_id;
```

These expressions share the same tie row set with different aggregate functions. The optimizer may combine shared work depending on the plan; do not assume each expression always performs a separate sort or is always merged. Evaluate the plan when performance matters.

## 16. Common Pitfalls

| Symptom / Misconception | Cause | Solution |
|---|---|---|
| `DENSE_RANK LAST ORDER BY date ASC` selects rows with NULL date | `ASC` defaults to placing NULL last | Specify `NULLS LAST`/`FIRST` deliberately; use `DESC NULLS LAST` + FIRST for latest non-null date |
| KEEP result is not from a single row | Multiple rows share the first/last dense rank | Decide whether to aggregate all ties or pick one row with ROW_NUMBER |
| Adding ID changes the result | ID breaks ties in the sort key | Only add a tie-breaker when a specific single row must be chosen |
| Columns fetched with KEEP do not belong to the same employee | Each aggregate runs independently over the tie set | Use ROW_NUMBER to pick one row if a tuple from the same record is needed |
| Confusing FIRST as always meaning smallest | FIRST depends on ASC/DESC | Check ORDER BY direction |
| Confusing LAST with LAST_VALUE | KEEP LAST picks the last dense rank set and aggregates | Distinguish aggregate KEEP from analytic value functions |
| Used COUNT(expr) when wanting to count all rows | COUNT(expr) ignores null expressions | Use COUNT(*) KEEP when counting rows |
| Wanted to ignore nulls using only NULLS LAST | NULLS LAST only sorts nulls | IGNORE NULLS does not apply to KEEP; filter/define sort key or aggregate logic separately |
| Thinking KEEP returns the top N rows | FIRST/LAST selects only one extreme dense rank tier | Use analytic ranking for multi-tier Top-N |
| Results differ across environments | Different implicit conversions, NLS, or collation | Use proper data types and explicit conversions |
| Used GROUP BY expecting to keep every employee row | Aggregate queries collapse groups into one row | Use analytic KEEP with OVER(PARTITION BY) or a ranking query |
| Used MIN/MAX aggregate instead of KEEP | Group-wide MIN/MAX is not restricted to first/last rank | Use KEEP when the condition is "within the first/last rank group" |

**Note on NULL:** `KEEP` syntax does not have an `IGNORE NULLS` option like `FIRST_VALUE`/`LAST_VALUE`/`NTH_VALUE`. To skip nulls in the sort key, control them via `NULLS FIRST/LAST` or filter the input set; to ignore nulls in the aggregated expression, aggregates like `MIN`, `MAX`, `SUM`, `AVG`, and `COUNT(expr)` already apply their standard null-ignoring rules. `COUNT(*)` still counts every retained row.

## 17. Controlled Practice Lab

Exercises use `LAB_KEEP_EMPLOYEES` created in section 3. Run only on an authorized DEV/TEST schema and the right PDB/service. Do not run DDL or cleanup operations on production.

### Exercise 1 — Highest Salary in the Earliest-Hired Group

```sql
SELECT department_id,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) AS max_salary_at_earliest_hire
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Record the result for each department and explain why department 10 has two people with the same earliest hire date yet yields a single aggregate value.

### Exercise 2 — Computing MIN, MAX, and COUNT on the Same Tie Set

```sql
SELECT department_id,
       MIN(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS min_salary,
       MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS max_salary,
       COUNT(*) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS row_count,
       COUNT(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST) AS salary_count
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Compare `ROW_COUNT` with `SALARY_COUNT` and explain the difference when the expression contains nulls.

### Exercise 3 — Latest Non-Null Hire Date

```sql
SELECT department_id,
       MAX(hire_date) AS latest_date,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST
       ) AS max_salary_at_latest_known_date
FROM lab_keep_employees
GROUP BY department_id
ORDER BY department_id;
```

Compare with `DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST` in department 40. Explain why the two expressions are not equivalent when nulls exist.

### Exercise 4 — Altering Ties with a Tie-Breaker

Run both expressions:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
)
```

and:

```sql
MAX(salary) KEEP (
    DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST, employee_id
)
```

Explain why department 10 can produce different results when `EMPLOYEE_ID` is added to the sort key.

### Exercise 5 — Analytic KEEP by Partition

```sql
SELECT employee_id, employee_name, department_id, hire_date, salary,
       MAX(salary) KEEP (
           DENSE_RANK FIRST ORDER BY hire_date ASC NULLS LAST
       ) OVER (PARTITION BY department_id) AS first_hire_group_max_salary
FROM lab_keep_employees
ORDER BY department_id, employee_id;
```

Verify that the output row count matches the source table row count and observe the value repeated per department.

### Exercise 6 — Comparing KEEP with a DENSE_RANK Query

Write a CTE using `DENSE_RANK() OVER (PARTITION BY department_id ORDER BY hire_date ASC NULLS LAST)`, filter rank equals 1, then group by department to compute `MAX(salary)`. Compare the result with `MAX(salary) KEEP (...)` and explain the two ways of expressing the same goal.

### Exercise 7 — Demonstrating KEEP Columns Can Come from Different Rows

In a single query, fetch `MIN(employee_name) KEEP (...)` and `MAX(salary) KEEP (...)` over the latest-hire-date group of department 10. Compare the two values against Dung's and Em's rows; explain why the resulting pair does not necessarily correspond to a single original record.

### Lab Data Cleanup

Only after confirming the table was created by you in DEV/TEST and no one else is using it:

```sql
DROP TABLE lab_keep_employees PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data without sending it to the recycle bin; this is a DDL operation with an implicit commit. Do not run it on production or any table outside the lab scope.

## 18. Review Questions

**Question 1.** What does `MAX(salary) KEEP (DENSE_RANK FIRST ORDER BY hire_date ASC)` mean?

**Answer:** Find the earliest hire date, retain all employees with that date, and then take the maximum salary among those retained employees.

**Question 2.** Does `DENSE_RANK FIRST` always select the smallest value?

**Answer:** No. It selects the first rank according to `ORDER BY`; ASC typically puts smaller values first, while DESC puts larger values first.

**Question 3.** If three employees share the earliest hire date, how many rows does `KEEP FIRST` retain?

**Answer:** All three rows tied for first rank. The aggregate function before KEEP computes over all three.

**Question 4.** What effect can adding a unique `EMPLOYEE_ID` to `ORDER BY` inside KEEP have?

**Answer:** It can break ties and reduce the first/last rank set to a single row.

**Question 5.** Can `DENSE_RANK LAST ORDER BY hire_date ASC NULLS LAST` select rows where hire_date is NULL?

**Answer:** Yes. If nulls are sorted last and null rows exist, the null group can become the last dense rank.

**Question 6.** To aggregate at the latest known date, which expression is clear?

**Answer:** `... KEEP (DENSE_RANK FIRST ORDER BY hire_date DESC NULLS LAST)`.

**Question 7.** How does `COUNT(*) KEEP (...)` differ from `COUNT(salary) KEEP (...)`?

**Answer:** COUNT(*) counts every retained row; COUNT(salary) counts only rows with non-null salary.

**Question 8.** Does KEEP automatically select one unique row?

**Answer:** No. It retains all tied rows in the first/last rank and aggregates them. To pick a single row, use ROW_NUMBER with a tie-breaker.

**Question 9.** Can you fetch employee_name and salary using two KEEP expressions and be certain they belong to the same employee?

**Answer:** Not if ties exist. Each aggregate can pick its own value from within the tie set. Use ROW_NUMBER to pull columns from the same row.

**Question 10.** How does analytic KEEP with `OVER (PARTITION BY department_id)` differ from KEEP with GROUP BY?

**Answer:** GROUP BY returns one row per department; analytic KEEP preserves each employee row and repeats the department's aggregate result alongside each row.

**Question 11.** Is KEEP the same as LAST_VALUE?

**Answer:** No. KEEP is an aggregate over the rows holding the first/last dense rank; LAST_VALUE retrieves an expression at the last row of a window frame and depends on the frame.

**Question 12.** To retrieve all earliest-hired employees without aggregating salaries, what should you use?

**Answer:** Analytic DENSE_RANK by department and then filter rank = 1.

## Conclusion

**`KEEP (DENSE_RANK FIRST/LAST ORDER BY ...)` selects the set of rows holding the first or last rank in a defined order, then applies an aggregate over the target expression.** `FIRST` and `LAST` depend on `ASC`/`DESC` direction; if multiple rows tie, all of them participate in `MIN`, `MAX`, `SUM`, `AVG`, `COUNT`, or the chosen aggregate. This is a concise way to compute values tied to an extreme-rank group without writing multiple subqueries.

When using `KEEP`, define the tie set clearly via the full sort key, specify `NULLS FIRST/LAST` intentionally, and distinguish nulls in the sort expression from nulls in the aggregate expression. `KEEP` with `GROUP BY` returns one row per group; the analytic form with `OVER (PARTITION BY ...)` preserves every row and repeats the value per partition. If you need multiple columns from the exact same row, use `ROW_NUMBER` with a tie-breaker instead of combining multiple KEEP aggregates that may draw from different rows.

## Oracle Reference Documentation

- [Oracle Database 19c — FIRST and LAST](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/FIRST.html): `KEEP (DENSE_RANK FIRST/LAST ...)` syntax, aggregate and analytic usage.
- [Oracle Database 19c — DENSE_RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DENSE_RANK.html): ranking rows with matching sort keys.
- [Oracle Database 19c — Aggregate Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Aggregate-Functions.html): aggregation rules and NULL handling.
- [Oracle Database 19c — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html): partitioning, analytic processing, and OVER usage.
