# OVER, PARTITION BY, and ORDER BY Structure in Oracle SQL

Analytic functions allow you to perform calculations over a set of related rows while **preserving every individual row in the result**. You can rank employees within a department, calculate running salary totals by hire date, compare a salary against the department average, retrieve a value from the preceding row, or select the top two employees in each group.

In Oracle SQL, the `OVER(...)` clause defines the row set and ordering that an analytic function uses. Three components to master are:

- `OVER`: declares the window for the analytic function.
- `PARTITION BY`: divides the row set into independent groups for calculation.
- `ORDER BY`: specifies the row ordering within each partition; for certain aggregate functions, it also defines cumulative or sliding windows.

Understanding these three components properly helps avoid confusing analytic functions with `GROUP BY`, computing duplicated totals incorrectly, and assuming the query's display order just because `ORDER BY` was written inside `OVER`.

## 1. How Do Analytic Functions Differ from GROUP BY?

`GROUP BY` collapses multiple rows into one row per group. Analytic functions calculate a value across a group or window while still returning the detail rows.

For example, an employee table has multiple people per department. If you use:

~~~sql
SELECT department_id, AVG(salary) AS department_avg_salary
FROM lab_af_employee
GROUP BY department_id;
~~~

The result has only one row per department. You know the average salary, but individual employees are no longer in the result.

If you use:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_avg_salary
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Oracle still returns every employee. The `DEPARTMENT_AVG_SALARY` column repeats the department's average value on each row belonging to that department.

| Technique | Result | Example of what one row represents |
|---|---|---|
| `GROUP BY department_id` | One row per department | One department |
| `AVG(salary) OVER (PARTITION BY department_id)` | One row per employee, adding the department average | One employee along with department statistics |

This is a critical distinction: **GROUP BY changes the grain of the result; an analytic function enriches the existing grain with additional information**.

## 2. OVER Syntax

General form:

~~~sql
analytic_function ( [ arguments ] )
OVER (
    [ query_partition_clause ]
    [ order_by_clause ]
    [ windowing_clause ]
)
~~~

Example:

~~~sql
SUM(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Reading from the inside out:

1. `SUM(salary)`: the function to compute is the sum of salaries.
2. `PARTITION BY department_id`: compute separately for each department.
3. `ORDER BY hire_date, employee_id`: define the row order within each department.
4. `ROWS BETWEEN ...`: determine which rows belong to the window used to compute the sum for the current row.
5. `OVER(...)`: turns the calculation into an analytic computation over related rows, keeping every output row intact.

Not every analytic function requires all three components. For example:

~~~sql
COUNT(*) OVER ()
~~~

counts the total number of rows in the input result set and displays that same count on every row; with no `PARTITION BY`, the entire set is one partition, and with no `ORDER BY`, no window ordering is defined.

## 3. Preparing Practice Data

We use an employee table with department ID, salary, and hire date. The dataset intentionally includes multiple employees with equal salaries and two employees hired on the same date to observe tie handling and `RANGE` windows.

### 3.1. Create the Table

Run in a lab schema inside a practice PDB. If a table with the same name already exists, use another schema or table name; do not overwrite data currently in use.

~~~sql
CREATE TABLE lab_af_employee (
    employee_id   NUMBER(5) PRIMARY KEY,
    employee_name VARCHAR2(60 CHAR) NOT NULL,
    department_id NUMBER(4) NOT NULL,
    salary        NUMBER(10,2) NOT NULL,
    hire_date     DATE NOT NULL,
    CONSTRAINT ck_lab_af_salary CHECK (salary >= 0)
);
~~~

### 3.2. Insert Data

~~~sql
INSERT INTO lab_af_employee VALUES
  (101, 'An',   10, 9000, DATE '2022-01-10');
INSERT INTO lab_af_employee VALUES
  (102, 'Binh', 10, 7000, DATE '2022-03-15');
INSERT INTO lab_af_employee VALUES
  (103, 'Chi',  10, 7000, DATE '2022-03-15');
INSERT INTO lab_af_employee VALUES
  (104, 'Dung', 10, 5000, DATE '2023-01-20');

INSERT INTO lab_af_employee VALUES
  (201, 'Em',    20, 12000, DATE '2021-07-01');
INSERT INTO lab_af_employee VALUES
  (202, 'Giang', 20, 10000, DATE '2022-08-01');
INSERT INTO lab_af_employee VALUES
  (203, 'Hanh',  20, 10000, DATE '2022-08-01');
INSERT INTO lab_af_employee VALUES
  (204, 'Khoa',  20, 6000,  DATE '2024-02-10');

INSERT INTO lab_af_employee VALUES
  (301, 'Lan',  30, 8000, DATE '2023-05-01');
INSERT INTO lab_af_employee VALUES
  (302, 'Minh', 30, 8000, DATE '2023-06-01');
INSERT INTO lab_af_employee VALUES
  (303, 'Nam',  30, 6500, DATE '2024-04-01');

COMMIT;
~~~

### 3.3. View Source Data

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    hire_date
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Summary:

| EMPLOYEE_ID | EMPLOYEE_NAME | DEPARTMENT_ID | SALARY | HIRE_DATE |
|---:|---|---:|---:|---|
| 101 | An | 10 | 9000 | 2022-01-10 |
| 102 | Binh | 10 | 7000 | 2022-03-15 |
| 103 | Chi | 10 | 7000 | 2022-03-15 |
| 104 | Dung | 10 | 5000 | 2023-01-20 |
| 201 | Em | 20 | 12000 | 2021-07-01 |
| 202 | Giang | 20 | 10000 | 2022-08-01 |
| 203 | Hanh | 20 | 10000 | 2022-08-01 |
| 204 | Khoa | 20 | 6000 | 2024-02-10 |
| 301 | Lan | 30 | 8000 | 2023-05-01 |
| 302 | Minh | 30 | 8000 | 2023-06-01 |
| 303 | Nam | 30 | 6500 | 2024-04-01 |

Salary totals by department:

| DEPARTMENT_ID | Employee Count | Total Salary | Average |
|---:|---:|---:|---:|
| 10 | 4 | 28000 | 7000 |
| 20 | 4 | 38000 | 9500 |
| 30 | 3 | 22500 | 7500 |

Matching salaries in departments 10, 20, and 30 help illustrate `RANK`, `DENSE_RANK`, and peer rows in `RANGE` windows.

## 4. OVER Without PARTITION BY

If `PARTITION BY` is not specified, the entire row set of the query block is treated as a single partition.

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    SUM(salary) OVER () AS all_employee_salary,
    COUNT(*) OVER () AS all_employee_count
FROM lab_af_employee
ORDER BY employee_id;
~~~

With this dataset, every row has:

- `ALL_EMPLOYEE_SALARY = 88500`
- `ALL_EMPLOYEE_COUNT = 11`

Both values are repeated on every employee. Salaries are not summed separately per department because there is no `PARTITION BY`.

### 4.1. Comparison with Regular Aggregate

~~~sql
SELECT SUM(salary) AS all_employee_salary
FROM lab_af_employee;
~~~

The query above returns exactly one row with a total of 88500. Meanwhile, `SUM(salary) OVER ()` returns 11 rows, each accompanied by the total 88500.

## 5. PARTITION BY Splits the Row Set into Independent Regions

`PARTITION BY` divides data into partitions based on the values of one or more expressions. The analytic function is calculated independently within each partition.

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
    ) AS department_total,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_average,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_employee_count
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Expected result:

| DEPARTMENT_ID | EMPLOYEE_NAME | SALARY | DEPARTMENT_TOTAL | DEPARTMENT_AVERAGE | DEPARTMENT_EMPLOYEE_COUNT |
|---:|---|---:|---:|---:|---:|
| 10 | An | 9000 | 28000 | 7000 | 4 |
| 10 | Binh | 7000 | 28000 | 7000 | 4 |
| 10 | Chi | 7000 | 28000 | 7000 | 4 |
| 10 | Dung | 5000 | 28000 | 7000 | 4 |
| 20 | Em | 12000 | 38000 | 9500 | 4 |
| 20 | Giang | 10000 | 38000 | 9500 | 4 |
| 20 | Hanh | 10000 | 38000 | 9500 | 4 |
| 20 | Khoa | 6000 | 38000 | 9500 | 4 |
| 30 | Lan | 8000 | 22500 | 7500 | 3 |
| 30 | Minh | 8000 | 22500 | 7500 | 3 |
| 30 | Nam | 6500 | 22500 | 7500 | 3 |

### 5.1. Multiple Columns in PARTITION BY

You can partition at multiple levels:

~~~sql
AVG(salary) OVER (
    PARTITION BY department_id, job_id
)
~~~

Each combination of `DEPARTMENT_ID` and `JOB_ID` creates a partition. In the current example there is no `JOB_ID` column; the expression above only illustrates syntax. Only use columns that actually exist in the schema.

If a partition column contains NULLs, rows with a NULL value in that column belong to the same partition group by expression value. Standard SQL "NULL equals NULL" comparison semantics do not apply here; this is the partitioning rule of analytic functions.

### 5.2. PARTITION BY Does Not Filter Out Rows

`PARTITION BY department_id` does not drop employees from any department, nor does it collapse employees into a single row. It only defines the scope that the analytic function uses for its calculation.

If you need to exclude inactive departments or employees who do not meet a condition, use `WHERE` or an appropriate filter in an outer query block. `PARTITION BY` is not a filter condition.

## 6. ORDER BY Inside OVER

`ORDER BY` inside `OVER` determines the order of rows **within each partition**. It is especially important for ranking functions, functions accessing preceding/following rows, and windowed aggregates.

Example ranking employees by descending salary within each department:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS row_num
FROM lab_af_employee
ORDER BY department_id, row_num;
~~~

Within each department, the highest-paid employee receives 1. `EMPLOYEE_ID` serves as a secondary criterion to determine order when two people have the same salary.

### 6.1. ORDER BY Inside OVER Does Not Sort the Final Output

Two concepts must be kept distinct:

- `ORDER BY` **inside `OVER(...)`**: governs the calculation order of the analytic function.
- `ORDER BY` **at the end of the SELECT statement**: governs the order of rows returned to the client.

Example:

~~~sql
SELECT
    employee_id,
    employee_name,
    salary,
    ROW_NUMBER() OVER (
        ORDER BY salary DESC, employee_id
    ) AS salary_position
FROM lab_af_employee;
~~~

The analytic function numbers rows in descending salary order, but without an `ORDER BY` at the end of the query, Oracle **does not guarantee** that rows are displayed in `SALARY_POSITION` order. To display in the intended order:

~~~sql
SELECT
    employee_id,
    employee_name,
    salary,
    ROW_NUMBER() OVER (
        ORDER BY salary DESC, employee_id
    ) AS salary_position
FROM lab_af_employee
ORDER BY salary_position;
~~~

Do not rely on physical order, insertion order, or indexes to replace the final `ORDER BY`.

### 6.2. ORDER BY Can Use Multiple Expressions

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, hire_date ASC, employee_id ASC
)
~~~

Oracle compares by salary first; if tied, it checks hire date; if still tied, it checks employee ID. A sufficiently unique secondary order keeps `ROW_NUMBER` results deterministic.

### 6.3. ASC, DESC, and NULLS FIRST/LAST

You can explicitly specify how NULLs are positioned:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC NULLS LAST, employee_id
)
~~~

In Oracle, by default NULLs are usually placed last with `ASC` and first with `DESC`. When a sort column can be NULL, writing `NULLS FIRST` or `NULLS LAST` explicitly prevents intent from depending on the reader remembering defaults.

## 7. ROW_NUMBER, RANK, and DENSE_RANK

These three functions are commonly used for ranking, but they handle tied values differently.

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS row_number_value,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS rank_value,
    DENSE_RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS dense_rank_value
FROM lab_af_employee
ORDER BY department_id, salary DESC, employee_id;
~~~

Result:

| DEPARTMENT_ID | EMPLOYEE_NAME | SALARY | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---|---:|---:|---:|---:|
| 10 | An | 9000 | 1 | 1 | 1 |
| 10 | Binh | 7000 | 2 | 2 | 2 |
| 10 | Chi | 7000 | 3 | 2 | 2 |
| 10 | Dung | 5000 | 4 | 4 | 3 |
| 20 | Em | 12000 | 1 | 1 | 1 |
| 20 | Giang | 10000 | 2 | 2 | 2 |
| 20 | Hanh | 10000 | 3 | 2 | 2 |
| 20 | Khoa | 6000 | 4 | 4 | 3 |
| 30 | Lan | 8000 | 1 | 1 | 1 |
| 30 | Minh | 8000 | 2 | 1 | 1 |
| 30 | Nam | 6500 | 3 | 3 | 2 |

| Function | Tied values | Next rank | Meaning |
|---|---|---|---|
| `ROW_NUMBER` | Always assigned distinct numbers | Sequential 1, 2, 3... | Position of each row |
| `RANK` | Same rank | Leaves gaps | Ranking with ties |
| `DENSE_RANK` | Same rank | No gaps | Ranking by distinct value tiers |

In `ROW_NUMBER`, if `ORDER BY` does not establish a unique order, two tied rows can receive sequence numbers in a non-deterministic order. Add a tie-breaker key such as `EMPLOYEE_ID` when business logic requires choosing a specific row.

## 8. Top-N Within Each Partition

Requirement: retrieve the two highest-paid employees in each department.

You cannot directly use `WHERE row_number_value <= 2` in the same query block that defines the analytic alias. We use an inline view:

~~~sql
SELECT
    ranked.department_id,
    ranked.employee_id,
    ranked.employee_name,
    ranked.salary,
    ranked.rn
FROM (
    SELECT
        e.department_id,
        e.employee_id,
        e.employee_name,
        e.salary,
        ROW_NUMBER() OVER (
            PARTITION BY e.department_id
            ORDER BY e.salary DESC, e.employee_id
        ) AS rn
    FROM lab_af_employee e
) ranked
WHERE ranked.rn <= 2
ORDER BY ranked.department_id, ranked.rn;
~~~

The result contains at most two employees per department:

| DEPARTMENT_ID | EMPLOYEE_NAME | SALARY | RN |
|---:|---|---:|---:|
| 10 | An | 9000 | 1 |
| 10 | Binh | 7000 | 2 |
| 20 | Em | 12000 | 1 |
| 20 | Giang | 10000 | 2 |
| 30 | Lan | 8000 | 1 |
| 30 | Minh | 8000 | 2 |

Because `ROW_NUMBER` has the secondary criterion `EMPLOYEE_ID`, the query retrieves at most two exact rows per department. For department 30, Lan comes before Minh by employee ID.

### 8.1. Top-N Including Ties

If the requirement is "retrieve all employees whose salaries fall in the top two ranks, including ties", use `DENSE_RANK`:

~~~sql
SELECT
    ranked.department_id,
    ranked.employee_name,
    ranked.salary,
    ranked.salary_rank
FROM (
    SELECT
        department_id,
        employee_name,
        salary,
        DENSE_RANK() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC
        ) AS salary_rank
    FROM lab_af_employee
) ranked
WHERE ranked.salary_rank <= 2
ORDER BY ranked.department_id, ranked.salary DESC, ranked.employee_name;
~~~

Result:

- Department 10: An (9000), Binh and Chi (7000).
- Department 20: Em (12000), Giang and Hanh (10000).
- Department 30: Lan and Minh (8000), Nam (6500).

`DENSE_RANK <= 2` can return more than two rows for a department. Choose the function based on the definition "top two rows" versus "top two rank tiers", rather than relying on the generic phrase "top-N".

## 9. Analytic Aggregates: Summarizing While Keeping Detail Rows

You can use aggregate functions with `OVER`:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
    ) AS department_salary_total,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_salary_avg,
    MAX(salary) OVER (
        PARTITION BY department_id
    ) AS department_max_salary,
    COUNT(*) OVER (
        PARTITION BY department_id
    ) AS department_size
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

Each employee remains a single row, accompanied by the department's total, average, highest salary, and headcount. Unlike `GROUP BY`, there is no need to join an aggregated result back to the employee table.

### 9.1. Comparing Each Employee's Salary Against Department Average

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_avg,
    salary - AVG(salary) OVER (
        PARTITION BY department_id
    ) AS difference_from_avg
FROM lab_af_employee
ORDER BY department_id, employee_id;
~~~

For example:

- An has a salary of 9000, which is 2000 above department 10's average.
- Dung has a salary of 5000, which is 2000 below department 10's average.
- Em has a salary of 12000, which is 2500 above department 20's average.
- Nam has a salary of 6500, which is 1000 below department 30's average.

This is a type of report where `GROUP BY` alone cannot both keep each employee and place the department average on the same row.

## 10. ORDER BY Combined with Windowing Clause

For analytic aggregates, `ORDER BY` can define a **window** around the current row. Common use cases include:

- Running totals.
- Running averages.
- Moving sums/averages over a recent number of rows.
- Totals over a logical value interval.

A window frame has the form:

~~~sql
ROWS | RANGE
BETWEEN frame_start AND frame_end
~~~

Common bounds:

| Bound | Meaning |
|---|---|
| `UNBOUNDED PRECEDING` | From the beginning of the partition |
| `n PRECEDING` | Step back n rows (ROWS) or value interval (RANGE) per frame rules |
| `CURRENT ROW` | The current row; with RANGE, may include peers with the same sort value |
| `n FOLLOWING` | Step forward n rows or corresponding value interval |
| `UNBOUNDED FOLLOWING` | To the end of the partition |

## 11. Running Total with ROWS

Calculate cumulative salary by hire date within each department:

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

`ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` means from the first row of the partition to the current row in the analytic ordering. Because `EMPLOYEE_ID` is included as a tie-breaker, each row has a clear order.

Manually calculated result:

| DEPARTMENT_ID | EMPLOYEE_NAME | HIRE_DATE | SALARY | RUNNING_SALARY |
|---:|---|---|---:|---:|
| 10 | An | 2022-01-10 | 9000 | 9000 |
| 10 | Binh | 2022-03-15 | 7000 | 16000 |
| 10 | Chi | 2022-03-15 | 7000 | 23000 |
| 10 | Dung | 2023-01-20 | 5000 | 28000 |
| 20 | Em | 2021-07-01 | 12000 | 12000 |
| 20 | Giang | 2022-08-01 | 10000 | 22000 |
| 20 | Hanh | 2022-08-01 | 10000 | 32000 |
| 20 | Khoa | 2024-02-10 | 6000 | 38000 |
| 30 | Lan | 2023-05-01 | 8000 | 8000 |
| 30 | Minh | 2023-06-01 | 8000 | 16000 |
| 30 | Nam | 2024-04-01 | 6500 | 22500 |

For Binh and Chi who share the same hire date, `ROWS` still processes them sequentially by `EMPLOYEE_ID`; Binh's running total is 16000, and then Chi's is 23000.

## 12. Differences Between ROWS and RANGE

This is a subtle but important distinction.

- `ROWS` defines the frame by **physical row count in the analytic order**.
- `RANGE` defines the frame by **logical value of the ORDER BY expression**; rows with the same sort value (peer rows) can be included together in the frame at `CURRENT ROW`.

With data containing duplicate hire dates, run:

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date
        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS range_running_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Result in department 10:

| EMPLOYEE_NAME | HIRE_DATE | SALARY | RANGE_RUNNING_SALARY |
|---|---|---:|---:|
| An | 2022-01-10 | 9000 | 9000 |
| Binh | 2022-03-15 | 7000 | 23000 |
| Chi | 2022-03-15 | 7000 | 23000 |
| Dung | 2023-01-20 | 5000 | 28000 |

Binh and Chi share the same `HIRE_DATE`; `RANGE ... CURRENT ROW` includes the entire peer group with the same sort value, so both receive 23000. With `ROWS` and the secondary order `EMPLOYEE_ID`, the values for each row are 16000 and 23000 respectively.

Department 20 also has two people on 2022-08-01: both Giang and Hanh receive `RANGE_RUNNING_SALARY = 32000`, whereas ROWS produces 22000 then 32000.

### 12.1. When to Use ROWS?

Use `ROWS` when the intent is "calculate from N rows back to the current row", for example:

~~~sql
AVG(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
~~~

This is the average of at most three employees in hire order: two preceding rows and the current row. If the partition does not yet have two preceding rows, the frame contains only the available rows.

### 12.2. When to Use RANGE?

Use `RANGE` when the intent is a window by sort value, such as a cumulative total by point in time where rows with the same timestamp should receive the same result. `RANGE` with `UNBOUNDED PRECEDING ... CURRENT ROW` is often useful when duplicate sort values need to be processed as a peer group.

For frames with offsets such as `RANGE BETWEEN INTERVAL '7' DAY PRECEDING AND CURRENT ROW`, the data type and sort expression must conform to Oracle rules for logical ranges. `RANGE` offset syntax has specific restrictions on the number of sort expressions; check the syntax for your Oracle version when using advanced frames.

### 12.3. Non-Unique Ordering and Determinism

If you use `ROWS` when `ORDER BY` cannot distinguish tied rows, the physical order among peers is not guaranteed. Consequently, running total values among tied rows can vary across different execution plans.

For stable results, add a unique key:

~~~sql
ORDER BY hire_date, employee_id
~~~

If business logic requires rows on the same date to receive the same running total, consider `RANGE` and specify the appropriate sort criteria. Do not mechanically add a tie-breaker column to RANGE if doing so splits the peer group you want to preserve.

## 13. Default Window Frame When ORDER BY Is Present

For analytic aggregate functions that support windowing, when `ORDER BY` is present **without a windowing clause**, Oracle defaults to a frame equivalent to:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

Therefore:

~~~sql
SUM(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date
)
~~~

can produce a cumulative result using RANGE, in which employees with the same hire date receive the same total. If you want a row-by-row cumulative total with a deterministic order, write an explicit `ROWS` frame:

~~~sql
SUM(salary) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Do not omit the windowing clause and assume Oracle is computing one physical row at a time. On data with duplicate sort values, the difference between RANGE and ROWS can yield different results.

## 14. Sliding Window

Example calculating the average salary of up to the three most recently hired employees in each department:

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS moving_avg_3_rows
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

At each row:

- The first row of the partition has only one salary to average.
- The second row has two rows.
- From the third row onward, the frame has at most three rows.
- As it advances, the window slides forward; older rows drop out of the frame once they are more than two rows away.

This is a **three-row** average, not necessarily a three-day or seven-day average. If the business requirement is "average over the last 30 days", design `RANGE` with a date expression and appropriate interval.

## 15. LAG and LEAD: Accessing Preceding/Following Rows

`LAG` reads a value from a preceding row in the analytic order; `LEAD` reads a value from a following row. They are commonly used to compare salary, revenue, or status across points in time.

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    LAG(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
    ) AS previous_salary,
    LEAD(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
    ) AS next_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

On the first row of each department, `PREVIOUS_SALARY` is NULL because there is no preceding row in the partition. On the last row, `NEXT_SALARY` is NULL. NULL here means there is no row at that position, not necessarily that the source salary column is NULL.

You can specify an offset and a default value:

~~~sql
LAG(salary, 1, 0) OVER (
    PARTITION BY department_id
    ORDER BY hire_date, employee_id
)
~~~

If there is no preceding row, the expression returns 0 per the default argument. Only use a default value when it makes business sense; replacing "no preceding row" with 0 can skew downstream calculations if 0 is not a suitable representation.

## 16. FIRST_VALUE and LAST_VALUE

`FIRST_VALUE` retrieves the first value in the window; `LAST_VALUE` retrieves the last value in the window. Pay careful attention to the window frame, especially with `LAST_VALUE`.

~~~sql
SELECT
    department_id,
    employee_id,
    employee_name,
    hire_date,
    salary,
    FIRST_VALUE(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_hire_salary,
    LAST_VALUE(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_hire_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Here the frame spans the entire partition, so all rows in the same department share the same first and last hire salaries.

If you write `LAST_VALUE(salary) OVER (PARTITION BY department_id ORDER BY hire_date, employee_id)` without specifying a frame, the default frame ends at the current row (under the default RANGE), so the "last" value may only be the last value of the frame up to the current row rather than the last row of the entire partition. When you need the last value across the entire partition, write explicitly:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
~~~

This is an example of why you must understand `ORDER BY` and the windowing clause rather than just memorizing function names.

## 17. NTILE and Order-Based Bucketing

`NTILE(n)` divides rows within each partition into up to n buckets with nearly equal row counts, based on the analytic ordering:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    NTILE(4) OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS salary_quartile
FROM lab_af_employee
ORDER BY department_id, salary DESC, employee_id;
~~~

With `NTILE(4)`, each department is divided into up to four buckets. A department with four employees typically has one person per bucket; a department with three employees only has three buckets containing rows. `NTILE` splits by **row count**, does not guarantee buckets have equal salary spans, and can split employees with equal salaries into different buckets. If you want to keep ties together by value, consider `RANK`/`DENSE_RANK` instead of NTILE.

## 18. Combining GROUP BY and Analytic Functions

Analytic functions can run over a result set already aggregated by `GROUP BY`. Example: sum salaries by department, then rank departments by total salary.

~~~sql
SELECT
    department_id,
    department_total,
    RANK() OVER (
        ORDER BY department_total DESC
    ) AS department_rank
FROM (
    SELECT
        department_id,
        SUM(salary) AS department_total
    FROM lab_af_employee
    GROUP BY department_id
) department_totals
ORDER BY department_rank;
~~~

Result:

| DEPARTMENT_ID | DEPARTMENT_TOTAL | DEPARTMENT_RANK |
|---:|---:|---:|
| 20 | 38000 | 1 |
| 10 | 28000 | 2 |
| 30 | 22500 | 3 |

The same logic can be written with a CTE:

~~~sql
WITH department_totals AS (
    SELECT
        department_id,
        SUM(salary) AS department_total
    FROM lab_af_employee
    GROUP BY department_id
)
SELECT
    department_id,
    department_total,
    RANK() OVER (
        ORDER BY department_total DESC
    ) AS department_rank
FROM department_totals
ORDER BY department_rank;
~~~

These are two layers of computation:

1. `GROUP BY` changes the grain from employee to department.
2. `RANK() OVER(...)` ranks the aggregated department rows.

Do not nest an analytic function inside another analytic function in the same query block. If you need to use one analytic result as input to another analytic function, split them using an inline view or CTE to create a new query block.

## 19. Filtering Analytic Function Results

Analytic functions are evaluated after the `FROM`, `WHERE`, `GROUP BY`, and `HAVING` phases in the same query block. Therefore, you cannot use a newly created analytic alias in the `WHERE` clause at the same level:

~~~sql
-- Invalid due to query block processing scope:
SELECT
    employee_id,
    department_id,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS rn
FROM lab_af_employee
WHERE rn <= 2;
~~~

Place the analytic function inside an inline view and filter in the outer query:

~~~sql
SELECT employee_id, department_id, salary, rn
FROM (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM lab_af_employee
)
WHERE rn <= 2
ORDER BY department_id, rn;
~~~

Or use a CTE:

~~~sql
WITH ranked_employees AS (
    SELECT
        employee_id,
        department_id,
        salary,
        ROW_NUMBER() OVER (
            PARTITION BY department_id
            ORDER BY salary DESC, employee_id
        ) AS rn
    FROM lab_af_employee
)
SELECT employee_id, department_id, salary, rn
FROM ranked_employees
WHERE rn <= 2
ORDER BY department_id, rn;
~~~

In Oracle 23c and later, `QUALIFY` syntax is available for filtering analytic results in certain cases; in common Oracle 19c/21c environments, inline views or CTEs are the standard compatible approach. Confirm the database version before using newer syntax.

## 20. Multiple Analytic Functions in a Single SELECT

One query block can compute multiple analytic functions over the same or different windows:

~~~sql
SELECT
    employee_id,
    employee_name,
    department_id,
    salary,
    AVG(salary) OVER (
        PARTITION BY department_id
    ) AS department_avg,
    RANK() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC
    ) AS salary_rank,
    SUM(salary) OVER (
        PARTITION BY department_id
        ORDER BY hire_date, employee_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_salary
FROM lab_af_employee
ORDER BY department_id, hire_date, employee_id;
~~~

Three functions serve three purposes:

- Department average does not require row ordering.
- Salary ranking requires descending salary order.
- Running total requires hire date ordering and a ROWS frame.

There is no need to write three separate queries if the results can be computed in the same query block without changing the grain.

## 21. ORDER BY and Tie-Breaking

A common mistake is writing:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

When multiple people share the same salary, Oracle still must assign distinct numbers, so the order among equal-salary rows is not uniquely determined. If the result is used to pick one person, such as `rn = 1`, it may pick one of the tied individuals in a non-deterministic manner.

If business rules specify prioritizing employees with an earlier hire date, write:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC, hire_date ASC, employee_id ASC
)
~~~

If business rules want **everyone tied for the highest salary**:

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY salary DESC
)
~~~

and filter `RANK_VALUE = 1` in the outer query. Do not add `EMPLOYEE_ID` to the ORDER BY of RANK if you want to preserve salary ties, because adding a tie-breaker column stops the rows from being peers.

## 22. NULLs in Analytic ORDER BY and Aggregates

Analytic aggregate functions such as `SUM`, `AVG`, `MIN`, and `MAX` normally ignore NULL values in the input expression, just like regular aggregates. `COUNT(expr)` counts only non-NULL expressions; `COUNT(*)` counts rows in the window.

If the sort expression contains NULLs, specify the desired placement:

~~~sql
RANK() OVER (
    PARTITION BY department_id
    ORDER BY commission_pct DESC NULLS LAST
)
~~~

The example above assumes a `COMMISSION_PCT` column in an actual table; the current lab table does not have that column. `NULLS LAST` puts unknown values at the end when sorting descending.

If a partition key is NULL, rows with NULL partition values fall into the same partition. If `ORDER BY` has NULL values, they can become peers under sort rules and affect `RANK`, `RANGE`, or row-fetching functions.

## 23. Understanding Logical Order and Where Analytic Functions Run

A common mental model of SELECT logical processing order:

~~~text
FROM / JOIN
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
      |
      v
ANALYTIC FUNCTIONS
      |
      v
ORDER BY (final output)
~~~

This diagram explains why:

- Analytic functions can operate on results already grouped by GROUP BY.
- WHERE in the same query block cannot directly filter a newly created analytic alias.
- An outer query can filter an analytic column produced by an inline view.
- `ORDER BY` inside `OVER` and the final `ORDER BY` have different scopes.

This is a logical model for understanding semantics, not a claim that the optimizer physically executes steps in literal text order. Oracle can transform query blocks while preserving SQL semantic results.

## 24. Performance and Execution Plans

Analytic functions often require sorting or processing partitions. On large tables, cost depends on:

- Input row count after WHERE/JOIN.
- Number of partitions and size of each partition.
- ORDER BY expressions and ability to leverage existing order or suitable indexes.
- Number of analytic functions and distinct windows.
- Whether sorts fit in memory or spill to temporary space.
- Statistics and data distribution.

Some principles:

1. Filter out unnecessary rows with WHERE before computing analytic functions, if business logic permits.
2. Choose the right partition key; do not over-split or wrongly merge scopes.
3. Write an ORDER BY sufficient to define ordering when using ROW_NUMBER or ROWS.
4. Use only the window frame you need; do not treat every problem as a running total by default.
5. Check the execution plan and runtime statistics before adding hints or indexes.

### 24.1. Viewing the Execution Plan

~~~sql
EXPLAIN PLAN FOR
SELECT
    employee_id,
    department_id,
    salary,
    ROW_NUMBER() OVER (
        PARTITION BY department_id
        ORDER BY salary DESC, employee_id
    ) AS rn
FROM lab_af_employee;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` provides an estimated plan in parse context; it does not prove correctness by itself and does not replace runtime metrics. When you have privileges and have executed the statement, `DBMS_XPLAN.DISPLAY_CURSOR` can provide cursor details and actual statistics if gathered appropriately.

For a lab table with only 11 rows, a full table scan and a small sort are normal. Do not create an index just to force index usage on a tiny example. On real workloads, measure before and after changes using representative data.

## 25. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `ORA-30483: window functions are not allowed here` | Placed an analytic function in an unsupported position, usually WHERE/HAVING in the same query block | Move the analytic function into an inline view/CTE and filter in the outer query |
| `ORA-00904: invalid identifier` | Referenced an analytic alias/column out of scope or a non-existent column | Check the select list of the inner query block |
| Top-N selects non-deterministic rows | ROW_NUMBER's ORDER BY does not produce a unique order | Add a tie-breaker key such as employee_id |
| Running totals for people on the same date are equal | Used RANGE or default frame with peer semantics | Use ROWS with a tie-breaker if row-by-row calculation is needed |
| LAST_VALUE does not return the last row of the partition | Frame ends at CURRENT ROW | Explicitly specify UNBOUNDED FOLLOWING when the full partition is needed |
| Displayed output is not in analytic order | Only ORDER BY inside OVER was specified | Add ORDER BY to the outermost query |
| Salary totals get inflated when joining detail tables | JOIN multiplies rows before analytic aggregate runs | Aggregate to the proper grain before joining or control cardinality |
| RANK does not preserve ties as expected | Included a tie-breaker column in the analytic ORDER BY | Sort only by the criteria that actually define ties |
| Sliding window produces unexpected results | Confused ROWS with RANGE or overlooked default frame | Write the windowing clause explicitly |

## 26. Practice Exercises

### Exercise 1 — Department Average

Display each employee, salary, and the department average salary on the same row.

**Hint:** `AVG(salary) OVER (PARTITION BY department_id)`.

### Exercise 2 — Salary Ranking

Within each department, rank employees by descending salary. Compare `ROW_NUMBER`, `RANK`, and `DENSE_RANK`.

**Hint:** department 10 has two people with salary 7000; observe that the next rank is 4 with RANK but 3 with DENSE_RANK.

### Exercise 3 — Top Two Rows

Retrieve at most the two highest-paid employees per department.

**Hint:** use ROW_NUMBER with PARTITION BY department_id and ORDER BY salary DESC, employee_id; filter RN <= 2 in the outer query.

### Exercise 4 — Top Two Salary Tiers

Retrieve all employees in the top two highest salary tiers in each department.

**Hint:** DENSE_RANK by salary DESC; filter rank <= 2. Row count may exceed two.

### Exercise 5 — Running Total

Compute cumulative salary by hire date within each department.

**Hint:** SUM(salary) OVER (PARTITION BY department_id ORDER BY hire_date, employee_id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW).

### Exercise 6 — Comparing ROWS and RANGE

Run two running total queries by hire_date, one using ROWS and one using RANGE. Observe Binh/Chi and Giang/Hanh.

**Hint:** ROWS with a tie-breaker gives sequential values; RANGE groups peer rows on the same date so values in the peer group are equal.

### Exercise 7 — Preceding and Following Employee Salaries

Display the salary of the preceding and following employee in the same department by hire date.

**Hint:** LAG and LEAD with PARTITION BY department_id, ORDER BY hire_date, employee_id.

### Exercise 8 — Filtering Analytic Results

Write a query to get the top employee in each department. Compare the single top employee via ROW_NUMBER against all tied top employees via RANK.

**Hint:** compute the analytic function in an inline view, and filter RN = 1 or RANK_VALUE = 1 in the outer query.

### Exercise 9 — Ranking Departments by Total Salary

Aggregate salaries by department and then rank departments in descending order of total salary.

**Hint:** GROUP BY in an inline view/CTE; RANK() OVER (ORDER BY department_total DESC) in the outer query.

## 27. Workflow for Choosing OVER, PARTITION BY, and ORDER BY

When writing an analytic function, answer these questions:

1. **Which function is needed?** SUM, AVG, COUNT, ROW_NUMBER, RANK, LAG, or LEAD?
2. **What is the scope?** The entire result set or per group? If per group, which PARTITION BY?
3. **Is ordering needed?** If yes, which ORDER BY reflects the business order?
4. **Is a sub-window frame needed?** Running total, rolling average, or the full partition?
5. **ROWS or RANGE?** Count by row count or by sort value/peer group?
6. **Are there tied values?** Do you need a tie-breaker or must ties be preserved?
7. **Do you need to filter the analytic result?** Use an inline view/CTE or QUALIFY syntax if supported by your version.
8. **What is the final display order?** Write ORDER BY in the outermost query.

Diagram:

~~~text
Choose analytic function
          |
          v
Choose PARTITION BY scope
          |
          v
Need calculation order?
       /       \
     No        Yes
      |         |
      |         v
      |    Choose ORDER BY
      |         |
      |         v
      |    Need window frame?
      |      /       \
      |    No        Yes
      |     |         |
      |     |         v
      |     |    Choose ROWS or RANGE
      |     |         |
      +-----+---------+
            |
            v
      Compute analytic
            |
            v
      Need to filter analytic?
         /       \
       No        Yes
        |         |
        |         v
        |    Inline view / CTE
        |         |
        +----+----+
             |
             v
      Final result ORDER BY
~~~

`OVER` defines the window that the analytic function operates on; `PARTITION BY` divides the window into independent regions; `ORDER BY` defines the ordering within each region and, when combined with a windowing clause, determines which rows are included for each result. Always distinguish analytic ordering from display ordering, distinguish `ROWS` from `RANGE`, and define clearly how ties are handled. When these choices accurately reflect business requirements, Oracle analytic functions can add aggregations, rankings, running totals, and row-to-row comparisons while preserving every detail row.
