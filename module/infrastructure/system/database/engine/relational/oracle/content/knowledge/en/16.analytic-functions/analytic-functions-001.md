# Distinguishing Aggregate Functions and Analytic (Window) Functions in Oracle

When writing SQL reports, you often need to answer two different questions: **how much is the total for each group?** and **how does each row contribute compared to the other rows in the group?** An *aggregate function* solves the first question by collapsing multiple rows into one result per group. An *analytic function* (often called a window function) solves the second question by computing over a window of related rows while preserving the rows of the query at their current level of detail.

For example, in a transactions table with multiple orders per customer:

- `GROUP BY customer_id` with `SUM(amount)` returns one row per customer.
- `SUM(amount) OVER (PARTITION BY customer_id)` computes the customer total on each transaction row, so each individual order remains visible.

Both expressions can use `SUM`, but where they are placed and what they mean are different. In Oracle, the `OVER(...)` clause turns an aggregatable function into an analytic computation over a window. Understanding this boundary helps avoid losing row-level detail, avoid self-joining a table just to attach group totals, and write chronologically accurate reports.

This lesson belongs to the **Analytic Functions** topic of *Database Engine Relational Oracle*. The content focuses on:

- Row count differences between aggregate and analytic functions.
- Syntax for `OVER`, `PARTITION BY`, `ORDER BY`, and window frames.
- When Oracle evaluates aggregates, analytics, and filtering clauses.
- `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `LAG`, `LEAD`, running totals, and moving averages.
- Common pitfalls with ties, NULLs, default frames, and result ordering.
- Reading execution plans and hands-on SQL practice.

## 1. Aggregate Functions: Collapsing Multiple Rows into Group Results

An aggregate function takes multiple input values and returns a single value for a set of rows. Commonly used functions:

| Function | Purpose |
| --- | --- |
| `COUNT(*)` | Counts the number of rows. |
| `COUNT(expr)` | Counts the number of non-NULL values of the expression. |
| `SUM(expr)` | Sums the non-NULL numeric values. |
| `AVG(expr)` | Computes the average of non-NULL numeric values. |
| `MIN(expr)` | Finds the minimum value. |
| `MAX(expr)` | Finds the maximum value. |
| `STDDEV(expr)` / `VARIANCE(expr)` | Computes standard deviation / variance as defined by Oracle. |

Without `GROUP BY`, an aggregate function usually computes over the entire row set after `FROM` and `WHERE`, and returns one row:

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(amount) AS total_amount,
       AVG(amount) AS average_amount
FROM orders
WHERE order_status = 'PAID';
~~~

With `GROUP BY`, Oracle divides rows into groups by the grouping expression and returns one row per group:

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(amount) AS total_amount
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id;
~~~

The result no longer has one row per order. Each `CUSTOMER_ID` has only a single row containing the count and total amount of PAID orders for that customer.

### Sample Data

Suppose we have the `LAB_ORDERS` table:

| ORDER_ID | CUSTOMER_ID | ORDER_DATE | AMOUNT |
| ---: | ---: | --- | ---: |
| 101 | 10 | 2026-01-01 | 100 |
| 102 | 10 | 2026-01-03 | 50 |
| 103 | 20 | 2026-01-03 | 80 |
| 104 | 10 | 2026-01-05 | 25 |
| 105 | 20 | 2026-01-06 | 20 |

Aggregate:

~~~sql
SELECT customer_id,
       SUM(amount) AS customer_total
FROM lab_orders
GROUP BY customer_id;
~~~

The result has two rows:

| CUSTOMER_ID | CUSTOMER_TOTAL |
| ---: | ---: |
| 10 | 175 |
| 20 | 100 |

The order rows have been collapsed. If a report needs to display each order alongside the customer total, using `GROUP BY customer_id` alone will lose detail columns such as `ORDER_ID` and `ORDER_DATE`.

## 2. Analytic Functions: Computing Over a Window While Keeping Detail Rows

An analytic function performs a calculation over a set of rows related to the current row, called a **window**. The result is attached to each row of the query block; it does not collapse rows into one row per group like `GROUP BY`.

General syntax:

~~~sql
analytic_function([arguments])
    OVER (
        [PARTITION BY partition_expression, ...]
        [ORDER BY sort_expression [ASC|DESC], ...]
        [windowing_clause]
    )
~~~

- `OVER(...)` tells Oracle this is an analytic computation.
- `PARTITION BY` divides the row set into independent partitions. If omitted, the entire row set of the query block is a single partition.
- `ORDER BY` defines the logical order within each partition for order-dependent computations.
- The window frame (if specified) defines the subset of rows around the current row used for the calculation.

Example:

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS customer_total
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

The result still has five rows. All three rows for customer 10 show `CUSTOMER_TOTAL = 175`; both rows for customer 20 show `CUSTOMER_TOTAL = 100`.

| ORDER_ID | CUSTOMER_ID | AMOUNT | CUSTOMER_TOTAL |
| ---: | ---: | ---: | ---: |
| 101 | 10 | 100 | 175 |
| 102 | 10 | 50 | 175 |
| 104 | 10 | 25 | 175 |
| 103 | 20 | 80 | 100 |
| 105 | 20 | 20 | 100 |

Key differences:

| Characteristic | Aggregate with GROUP BY | Analytic with OVER |
| --- | --- | --- |
| Result grain | One row per group | Preserves each input row of the current query block |
| Calculation scope | Entire group | Entire partition or window frame of the current row |
| Grouping | `GROUP BY` | `PARTITION BY` inside OVER |
| Ordering in calculation | Usually not needed | Can use `ORDER BY` inside OVER |
| Used for | Summarization, group-level reports | Ranking, running totals, row-to-row comparison, share of total |

### Aggregate Without GROUP BY and Analytic Without PARTITION BY

These two cases look similar at first glance, yet remain different:

~~~sql
-- A single row for the entire result set.
SELECT SUM(amount) AS grand_total
FROM lab_orders;

-- The total of the entire set repeated on every row.
SELECT order_id,
       amount,
       SUM(amount) OVER () AS grand_total
FROM lab_orders;
~~~

`SUM(amount)` in the first SELECT returns one row. `SUM(amount) OVER()` in the second SELECT returns a single total, but repeats it across every detail row.

## 3. PARTITION BY: Dividing the Window into Groups

`PARTITION BY` divides data into independent partitions for analytic computation. It does not remove rows and does not necessarily sort the output.

~~~sql
SELECT order_id,
       customer_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS total_by_customer,
       SUM(amount) OVER (
           PARTITION BY TRUNC(order_date)
       ) AS total_by_order_day
FROM lab_orders;
~~~

Within the same query, you can have multiple analytic functions with different partitions. The customer total and the daily total are computed independently over the same rows.

### Multi-Column Partitions

~~~sql
SELECT department_id,
       job_id,
       employee_id,
       salary,
       AVG(salary) OVER (
           PARTITION BY department_id, job_id
       ) AS avg_salary_by_dept_job
FROM employees;
~~~

Each partition is a combination of `DEPARTMENT_ID` and `JOB_ID`. Employees in the same department but with different jobs belong to different partitions.

### Omitting PARTITION BY

~~~sql
SELECT employee_id,
       salary,
       SUM(salary) OVER () AS company_payroll
FROM employees;
~~~

When `PARTITION BY` is omitted, Oracle computes over the entire row set of the query block. This is how you repeat the company-wide total on each employee row.

### PARTITION BY Is Not the Same as GROUP BY

`GROUP BY department_id` collapses multiple employees into one row per department. `PARTITION BY department_id` specifies the group used for the analytic computation while keeping every employee row:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       SUM(salary) OVER (
           PARTITION BY department_id
       ) AS dept_payroll
FROM employees;
~~~

## 4. ORDER BY Inside OVER and the Query's ORDER BY

There are two ORDER BY clauses with different roles:

1. `ORDER BY` inside `OVER(...)` defines the **logical order for computing the analytic function**.
2. `ORDER BY` at the end of SELECT defines the **display order of results** returned to the client.

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS order_sequence
FROM lab_orders
ORDER BY amount DESC;
~~~

`ORDER_SEQUENCE` is numbered by date and ID within each customer, while the displayed output is sorted by `AMOUNT DESC`. Ordering inside OVER **does not guarantee the order of returned rows**; if you want a specific output order, you must write the outermost ORDER BY.

### Tie-Breakers Are Needed

If multiple rows share the same `ORDER_DATE`, writing only:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY order_date
)
~~~

can produce non-deterministic ordering among rows on the same date. If business requirements demand repeatable, stable results, add a unique key:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
)
~~~

This is an important rule for `ROW_NUMBER`, running totals using `ROWS`, and any logic that depends on row position.

## 5. Window Frame: A Specific Window Around the Current Row

`PARTITION BY` defines the group, while the window frame defines **which part of the partition** is used for computing on the current row. Frames are commonly written with `ROWS` or `RANGE`.

### ROWS: Counting by Row Position

`ROWS` defines the frame by the physical number of rows before/after the current row in the analytic ordering:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_total
~~~

The frame starts from the first row of the partition and ends at the current row. The result is a running total.

Moving sum of the three most recent transactions (current row and two preceding rows):

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
) AS moving_sum_3_rows
~~~

`ROWS` depends on the order of individual rows. If ORDER BY keys have duplicates without a tie-breaker, which row comes first can be unstable; add a unique key whenever order matters.

### RANGE: Defining the Frame by Sort Value

`RANGE` defines the window by the logical value of the ORDER BY expression, not by row count. Rows with the same sort value (peers) are treated as having the same logical position.

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date
    RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
) AS running_total_by_day
~~~

If a customer has two orders on the same date, both rows can receive the same cumulative result ending on that date, because a RANGE frame up to CURRENT ROW includes peers with the same `ORDER_DATE`.

For time intervals, Oracle allows RANGE frames on a suitable sort expression, for example:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date
    RANGE BETWEEN INTERVAL '6' DAY PRECEDING AND CURRENT ROW
) AS rolling_7_calendar_days
~~~

This example uses a single date expression in ORDER BY and a seven-calendar-day window (the current day plus the six preceding days). RANGE offset syntax rules impose restrictions on the number and data types of ORDER BY expressions; for interval offsets, use a compatible date/datetime expression.

### UNBOUNDED, PRECEDING, FOLLOWING, and CURRENT ROW

| Keyword | Meaning |
| --- | --- |
| `UNBOUNDED PRECEDING` | Starts from the beginning of the partition. |
| `n PRECEDING` | Steps back n rows (ROWS) or a value interval (RANGE). |
| `CURRENT ROW` | The current row; with RANGE, includes peers sharing the same sort value. |
| `n FOLLOWING` | Steps forward n rows or a value interval. |
| `UNBOUNDED FOLLOWING` | Ends at the end of the partition. |

Example of the full-partition total on every row:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
)
~~~

If neither ordering nor a frame is needed, you can simply write `SUM(amount) OVER (PARTITION BY customer_id)`.

### The Default Frame Can Be Surprising

For many analytic functions that support windowing, when `ORDER BY` is present inside OVER without an explicit frame, Oracle uses a default frame equivalent to:

`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`

Therefore, the expression:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY order_date
)
~~~

is not the total of the entire partition repeated on every row; it is a running total using `RANGE`, including peer rows with the same date. To get the full-partition total, omit ORDER BY inside OVER or explicitly specify a frame ending at `UNBOUNDED FOLLOWING`.

## 6. Same SUM Function, Two Different Meanings

This is the central example for distinguishing aggregate and analytic:

~~~sql
-- One row per customer.
SELECT customer_id,
       SUM(amount) AS total_amount
FROM lab_orders
GROUP BY customer_id;

-- One row per order, with the customer's total.
SELECT order_id,
       customer_id,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS total_amount
FROM lab_orders;
~~~

The expression `SUM(amount)` is an aggregate because it has no `OVER` clause and is used for grouping. The expression `SUM(amount) OVER(...)` is analytic because the result is computed over a window and attached back to each row.

### Aggregate First, Analytic After

~~~sql
SELECT department_id,
       SUM(salary) AS dept_payroll,
       SUM(SUM(salary)) OVER () AS company_payroll,
       ROUND(
           100 * SUM(salary) / SUM(SUM(salary)) OVER (),
           2
       ) AS pct_of_company
FROM employees
GROUP BY department_id
ORDER BY department_id;
~~~

Logical order:

1. FROM/WHERE selects employees.
2. GROUP BY groups employees by department.
3. `SUM(salary)` produces each department's total.
4. `SUM(SUM(salary)) OVER()` runs the analytic function over the aggregated department rows.
5. SELECT returns one row per department with department total, company total, and percentage.

`SUM(SUM(salary)) OVER()` is not meaningless repetition: the inner SUM is a group aggregate; the outer SUM with OVER is an analytic function over the grouped result set.

## 7. Common Analytic Functions

### ROW_NUMBER: Numbering Rows

`ROW_NUMBER()` assigns a unique sequential number to each row in a partition according to ORDER BY:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS row_no
FROM employees;
~~~

Each department starts at 1. If salaries are equal, `EMPLOYEE_ID` breaks ties to make the ordering deterministic.

Top 3 highest-paid employees per department:

~~~sql
WITH ranked_employees AS (
    SELECT employee_id,
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
WHERE rn <= 3
ORDER BY department_id, rn;
~~~

### RANK and DENSE_RANK: Ranking with Ties

Both functions assign the same rank to rows with equal sort values, but handle ranking gaps differently:

| SALARY | ROW_NUMBER | RANK | DENSE_RANK |
| ---: | ---: | ---: | ---: |
| 9000 | 1 | 1 | 1 |
| 8500 | 2 | 2 | 2 |
| 8500 | 3 | 2 | 2 |
| 7000 | 4 | 4 | 3 |

- `ROW_NUMBER`: always a unique sequence number; does not preserve ties.
- `RANK`: tied rows receive the same rank, and subsequent ranks are skipped.
- `DENSE_RANK`: tied rows receive the same rank, and subsequent ranks increment consecutively.

~~~sql
SELECT employee_id,
       department_id,
       salary,
       RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS salary_rank,
       DENSE_RANK() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS dense_salary_rank
FROM employees;
~~~

If the requirement is "get three people", `ROW_NUMBER <= 3` limits the row count. If the requirement is "get the top three salary tiers, keeping everyone who ties", `DENSE_RANK <= 3` is more appropriate and may return more than three rows.

### LAG and LEAD: Reading Preceding/Following Rows

`LAG(expr, offset, default)` retrieves a value from a preceding row in the analytic order; `LEAD` retrieves a value from a following row:

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       LAG(amount, 1, 0) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS previous_amount,
       LEAD(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS next_amount
FROM lab_orders;
~~~

On the first row of each customer, `LAG` returns the default 0; if default is omitted, the default value is NULL. On the last row, `LEAD` returns NULL if there is no following row. This is the value of the preceding/following row in order, not an aggregate calculation.

### FIRST_VALUE and LAST_VALUE

~~~sql
SELECT employee_id,
       department_id,
       salary,
       FIRST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS highest_salary,
       LAST_VALUE(salary) OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
       ) AS lowest_salary
FROM employees;
~~~

`FIRST_VALUE` retrieves the first value in the frame; `LAST_VALUE` retrieves the last value in the frame. Pay close attention to the default frame: if you do not specify a frame ending at the end of the partition, `LAST_VALUE` may return the value of the current row or the last peer in the current frame, rather than the last value of the entire partition. To get the last value of the partition, explicitly specify `UNBOUNDED FOLLOWING`.

### NTILE: Dividing into Nearly Equal Buckets

~~~sql
SELECT employee_id,
       salary,
       NTILE(4) OVER (
           ORDER BY salary DESC, employee_id
       ) AS salary_quartile
FROM employees;
~~~

`NTILE(4)` divides rows into four buckets of nearly equal size according to the ordering. It is not an exact statistical percentile like `PERCENTILE_CONT`; when the row count is not evenly divisible, bucket sizes can differ by one row.

## 8. Aggregate Functions and Analytic Functions Are Not Two Separate Lists

Many functions can operate in both roles:

| Function | Without OVER | With OVER |
| --- | --- | --- |
| `SUM` | Aggregates into one value or one value per group | Sum over partition/frame, preserving rows |
| `AVG` | Average of the set/group | Average over partition/frame |
| `COUNT` | Counts rows/values in the set/group | Count over partition/frame |
| `MIN` / `MAX` | Minimum/maximum value of the set/group | Min/max over partition/frame |
| `STDDEV` / `VARIANCE` | Statistics of the set/group | Statistics over partition/frame |

Some functions are primarily analytic:

- `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`.
- `LAG`, `LEAD`.
- `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE`.
- Distribution functions such as `CUME_DIST`, `PERCENT_RANK`, and `PERCENTILE_CONT` in analytic form.

The distinction is not just the function name, but **whether OVER is used to request a windowed calculation** and the query block context where the function appears.

### COUNT(*) and COUNT(expr) in Analytic Form

~~~sql
SELECT employee_id,
       department_id,
       commission_pct,
       COUNT(*) OVER (
           PARTITION BY department_id
       ) AS employee_count,
       COUNT(commission_pct) OVER (
           PARTITION BY department_id
       ) AS commission_count
FROM employees;
~~~

`COUNT(*)` counts every row in the partition. `COUNT(commission_pct)` only counts rows with a non-NULL commission. The result is repeated on every employee in that department.

## 9. Evaluation Order: WHERE, GROUP BY, HAVING, and Analytic Functions

Understanding the logical processing order helps avoid errors when filtering by analytic results. A conceptual model:

~~~text
FROM / JOIN
    |
WHERE  -- filter input rows
    |
GROUP BY  -- group rows
    |
HAVING  -- filter groups
    |
SELECT expressions, including analytic functions
    |
ORDER BY  -- sort final results
~~~

Analytic functions are evaluated after `FROM`, `WHERE`, `GROUP BY`, and `HAVING` of the current query block, and before the final ORDER BY. Consequently:

- WHERE removes rows before analytic functions compute their windows.
- GROUP BY creates the grouped row set before analytic functions run on that grouped set.
- HAVING removes groups before analytic functions run.
- You cannot use an analytic function directly in WHERE/GROUP BY/HAVING of the same query block in the standard way.

### Why Can't You Filter ROW_NUMBER Directly in WHERE?

Invalid example:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC
       ) AS rn
FROM employees
WHERE rn <= 3;
~~~

The alias `RN` does not exist yet at the time WHERE is evaluated; Oracle also does not allow placing an analytic function directly in the WHERE clause of the same query block. Use an inline view or a CTE:

~~~sql
WITH ranked AS (
    SELECT employee_id,
           department_id,
           salary,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY salary DESC, employee_id
           ) AS rn
    FROM employees
)
SELECT employee_id, department_id, salary, rn
FROM ranked
WHERE rn <= 3;
~~~

The inner query block computes `RN`; the outer query block filters the result that already has `RN`.

## 10. NULLs and Edge Cases in Analytic Functions

Aggregates normally ignore NULLs in input expressions, except `COUNT(*)` which counts rows. For example:

~~~sql
SELECT department_id,
       COUNT(*) AS all_employees,
       COUNT(commission_pct) AS employees_with_commission,
       AVG(commission_pct) AS avg_commission
FROM employees
GROUP BY department_id;
~~~

Analytic aggregates such as `COUNT(expr) OVER(...)` and `AVG(expr) OVER(...)` follow the corresponding NULL-ignoring rules.

### NULLs in ORDER BY

Oracle allows specifying `NULLS FIRST` or `NULLS LAST`:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY commission_pct DESC NULLS LAST, employee_id
)
~~~

If unspecified, Oracle's default is usually NULLS LAST for ASC and NULLS FIRST for DESC. To keep ranking logic clear and consistent across sort directions, write NULLS FIRST/LAST explicitly when NULL has business meaning.

### LAG/LEAD and NULL

`LAG`/`LEAD` can return NULL because:

- There is no preceding/following row in the partition.
- The referenced row has a NULL expression value.
- The supplied default is NULL.

If you need to skip rows where the expression is NULL, Oracle supports `IGNORE NULLS` in appropriate functions:

~~~sql
LAG(measurement) IGNORE NULLS OVER (
    PARTITION BY sensor_id
    ORDER BY measured_at
)
~~~

Distinguish `IGNORE NULLS` from a default value: one skips rows with NULL values when searching for the preceding/following position; the other only provides a fallback value when no corresponding row exists at that offset.

## 11. Running Totals, Moving Averages, and Share of Total

### Running Total per Customer

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_total
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

Each row receives the total amount from the customer's first transaction up to the current transaction. `ORDER_ID` serves as a tie-breaker so the order within the same date is deterministic.

### Three-Transaction Moving Average

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       AVG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
       ) AS moving_avg_3_orders
FROM lab_orders;
~~~

At the beginning of a partition, the frame may have fewer than three rows. AVG computes the average over the non-NULL values currently present in the frame rather than assuming three transactions exist.

### Each Row's Share of Group Total

~~~sql
SELECT order_id,
       customer_id,
       amount,
       ROUND(
           100 * amount
           / NULLIF(
               SUM(amount) OVER (PARTITION BY customer_id),
               0
           ),
           2
       ) AS pct_of_customer_total
FROM lab_orders;
~~~

`NULLIF(..., 0)` prevents division-by-zero errors when the group total is 0. If the total is NULL, the percentage result may also be NULL; display rules in the report should be defined accordingly.

### Period-over-Period Comparison

~~~sql
SELECT customer_id,
       order_id,
       order_date,
       amount,
       LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS previous_order_amount,
       amount - LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS change_from_previous
FROM lab_orders;
~~~

This compares against the immediately preceding order by sequence, not the previous calendar day. If you need to compare by day, month, or accounting period, aggregate to the proper time grain first, then apply LAG on the aggregated period set.

## 12. DISTINCT and Analytic Functions

You can combine DISTINCT with analytic functions, but keep in mind that DISTINCT applies at the outermost query block after SELECT expressions have been evaluated. If the analytic function returns different values per row, DISTINCT will not deduplicate those rows.

~~~sql
SELECT DISTINCT
       department_id,
       SUM(salary) OVER (PARTITION BY department_id) AS dept_total
FROM employees;
~~~

In this example, because only department and department total are selected (two expressions that are identical across rows in the same department), DISTINCT can produce one row per department. However, if you add `EMPLOYEE_ID` or `ROW_NUMBER`, the rows become distinct and DISTINCT can no longer collapse by department.

Usually, if the goal is one row per department, consider GROUP BY instead of using analytic plus DISTINCT. Choose the expression that matches the target grain of the result from the start.

Some analytic aggregates support `DISTINCT` within their own syntax scope, but have restrictions when combined with analytic ORDER BY/window frames. Check the documentation for the specific function and Oracle version before writing `COUNT(DISTINCT x) OVER(...)`; do not assume every aggregate DISTINCT syntax is valid in analytic mode.

## 13. Performance and Execution Plans

Analytic functions often require sorting data by partition/order keys or maintaining window state. Cost depends on:

- Number of input rows after WHERE/GROUP BY/HAVING.
- Number of partitions and size of each partition.
- PARTITION BY/ORDER BY expressions.
- Window frames, especially frames that look forward or across the entire partition.
- Number of analytic functions and whether they can share a sort order.
- PGA/workarea, TEMP spill, parallel execution, and row width.

### Sorting for Analytic Functions

Example of `ROW_NUMBER` by department and salary:

~~~sql
SELECT employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM employees;
~~~

Oracle needs to organize rows by partition and the corresponding order. The execution plan may include operations such as `WINDOW SORT`, `WINDOW BUFFER`, or other analytic operations depending on the version and optimizer implementation. Do not assume every analytic function always produces the exact same operation type.

If multiple analytic functions share the same partition/order specification, Oracle can reuse the existing order instead of performing multiple independent sorts. If the specifications differ, additional sort steps may be needed.

### Do Indexes Help?

Indexes on PARTITION/ORDER BY columns can be helpful in some queries, but they do not guarantee eliminating a sort. The optimizer weighs the cost of reading the index versus a full scan, the number of columns needed, clustering factor, selectivity, and data ordering. Always check the actual plan before adding an index solely to serve an analytic function.

### Gathering the Actual Plan

~~~sql
SELECT /*+ gather_plan_statistics */
       employee_id,
       department_id,
       salary,
       ROW_NUMBER() OVER (
           PARTITION BY department_id
           ORDER BY salary DESC, employee_id
       ) AS rn
FROM employees;

SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +COST +PREDICATE'
    )
);
~~~

Observe:

- Which operation performs the sort/window?
- Does `E-Rows` diverge significantly from `A-Rows`?
- How many rows enter the analytic operation?
- What are logical reads (`Buffers`), physical reads, and elapsed time?
- Is there any TEMP/workarea spill?
- Are there multiple sorts because analytic functions use different orderings?

`ALLSTATS LAST` requires execution statistics to be collected (for example via the `GATHER_PLAN_STATISTICS` hint or appropriate configuration). `EXPLAIN PLAN` only provides an estimated plan and does not measure actual row counts or TEMP usage.

### Reducing Work Before Analytic Evaluation

When business logic allows, filter out unnecessary rows early with WHERE before analytic functions run. If you need to aggregate to the month level before computing LAG, perform GROUP BY month in a CTE first. Do not filter out rows that are needed for the window just to make the query faster; the analytic result will change because the input set changed.

## 14. Common Pitfalls and How to Fix Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Result only has one row per group | Used GROUP BY when detail rows were needed | Use analytic `... OVER(PARTITION BY ...)` if individual rows must be kept. |
| Running total has the same value for orders on the same date | Used RANGE frame or default frame with peers | Use ROWS and a tie-breaker if you want a row-by-row running total. |
| `ROW_NUMBER` changes between runs | ORDER BY inside OVER does not uniquely determine order on ties | Add a unique key as a tie-breaker. |
| Cannot filter `rn` in WHERE | Analytic functions are evaluated after WHERE | Wrap the analytic query in a CTE/inline view and filter outside. |
| `LAST_VALUE` does not return the partition's last value | Default frame ends at current row | Explicitly specify `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. |
| ORDER BY inside OVER does not sort the output | That ORDER BY only serves the analytic computation | Add an ORDER BY in the outermost query. |
| Unexpectedly low/high AVG | NULLs are ignored or the frame has only partial rows at boundaries | Check COUNT, NULLs, and the actual frame. |
| Group total repeated on every row | Used SUM OVER | This is expected analytic behavior, not duplicate data. |
| TEMP usage spikes on large analytic queries | Sort/window workarea lacks memory | Check actual plan, row count, partitions, PGA/TEMP, and concurrent workload. |
| LAG/LEAD results are unexpected | Incorrect analytic ordering or partition grain | Define the right partition/order and handle NULLs/defaults. |

## 15. Comprehensive Hands-On Lab

Examples use a learning schema with `CREATE TABLE` privileges and appropriate quota. DDL causes an implicit commit in Oracle; do not run on real production tables.

### Step 1: Create Transaction Data

~~~sql
CREATE TABLE lab_orders (
    order_id    NUMBER(8) PRIMARY KEY,
    customer_id NUMBER(8) NOT NULL,
    order_date  DATE NOT NULL,
    amount      NUMBER(12,2),
    status      VARCHAR2(20 CHAR)
);

INSERT INTO lab_orders VALUES (101, 10, DATE '2026-01-01', 100, 'PAID');
INSERT INTO lab_orders VALUES (102, 10, DATE '2026-01-03',  50, 'PAID');
INSERT INTO lab_orders VALUES (103, 20, DATE '2026-01-03',  80, 'PAID');
INSERT INTO lab_orders VALUES (104, 10, DATE '2026-01-05',  25, 'PENDING');
INSERT INTO lab_orders VALUES (105, 20, DATE '2026-01-06',  20, 'PAID');
INSERT INTO lab_orders VALUES (106, 20, DATE '2026-01-06', NULL, 'PENDING');
COMMIT;
~~~

### Step 2: Aggregate by Customer

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       COUNT(amount) AS orders_with_amount,
       SUM(amount) AS total_amount,
       AVG(amount) AS avg_amount
FROM lab_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Record the number of output rows and explain why `COUNT(*)` differs from `COUNT(amount)` for customer 20.

### Step 3: Analytic Group Total While Keeping Detail

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
       ) AS customer_total
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

Compare the row count with step 2. Why does customer 10's total appear on three rows?

### Step 4: Running Total and Moving Average

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       SUM(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
       ) AS running_total,
       AVG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
           ROWS BETWEEN 1 PRECEDING AND CURRENT ROW
       ) AS moving_avg_two_rows
FROM lab_orders
ORDER BY customer_id, order_date, order_id;
~~~

Explain the frame at the start of the partition and the effect of a NULL amount.

### Step 5: LAG and LEAD

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       amount,
       LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS previous_amount,
       LEAD(amount) OVER (
           PARTITION BY customer_id
           ORDER BY order_date, order_id
       ) AS next_amount
FROM lab_orders;
~~~

Distinguish NULL due to no preceding/following row from NULL because the referenced row has a NULL `AMOUNT`.

### Step 6: Ranking per Customer

~~~sql
SELECT order_id,
       customer_id,
       amount,
       ROW_NUMBER() OVER (
           PARTITION BY customer_id
           ORDER BY amount DESC NULLS LAST, order_id
       ) AS row_no,
       RANK() OVER (
           PARTITION BY customer_id
           ORDER BY amount DESC NULLS LAST
       ) AS amount_rank,
       DENSE_RANK() OVER (
           PARTITION BY customer_id
           ORDER BY amount DESC NULLS LAST
       ) AS dense_amount_rank
FROM lab_orders;
~~~

Explain the differences when two orders have the same amount and when amount is NULL.

### Step 7: Top-N Filtering via CTE

~~~sql
WITH ranked_orders AS (
    SELECT order_id,
           customer_id,
           amount,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY amount DESC NULLS LAST, order_id
           ) AS rn
    FROM lab_orders
)
SELECT order_id, customer_id, amount, rn
FROM ranked_orders
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

Explain why the `RN <= 2` condition is placed in the outer query.

### Step 8: Aggregate Then Analyze

~~~sql
SELECT customer_id,
       SUM(amount) AS customer_total,
       SUM(SUM(amount)) OVER () AS grand_total,
       ROUND(
           100 * SUM(amount) / NULLIF(SUM(SUM(amount)) OVER (), 0),
           2
       ) AS pct_of_total
FROM lab_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Describe the order of aggregating by customer first and then applying analytic evaluation over the customer rows.

### Step 9: Clean Up Data

~~~sql
DROP TABLE lab_orders PURGE;
~~~

Run this only if you have completed the lab and no longer need the data. `PURGE` bypasses the Recycle Bin; DROP TABLE is DDL and cannot be rolled back like uncommitted DML.

## 16. Self-Check Questions

1. **What grain does an aggregate with GROUP BY return?** One row per group defined by GROUP BY.
2. **Does an analytic function with PARTITION BY lose detail rows?** No; it computes over the partition and attaches the result to each row of the query block.
3. **How do SUM(amount) and SUM(amount) OVER() differ?** The first aggregates into one value per group; the second repeats the total of the entire set on every row.
4. **How does PARTITION BY differ from GROUP BY?** PARTITION BY divides the window while keeping rows; GROUP BY collapses rows into result groups.
5. **Does ORDER BY inside OVER sort the output?** No; an outermost ORDER BY is needed.
6. **How does ROWS differ from RANGE?** ROWS counts by row position; RANGE operates by the logical value of the sort expression and includes peers according to the frame.
7. **Why does ROW_NUMBER need a tie-breaker?** To determine a unique order when primary sort values are tied.
8. **How do RANK and DENSE_RANK differ?** RANK leaves gaps after ties; DENSE_RANK does not leave gaps.
9. **What are LAG and LEAD used for?** Retrieving values from a preceding or following row in the partition according to the analytic order.
10. **Why might LAST_VALUE not return the last value of the partition?** The default frame may end at the current row; you need to specify UNBOUNDED FOLLOWING explicitly.
11. **Can analytic functions be used directly in WHERE of the same query block?** Not in standard syntax; use an inline view/CTE and filter outside.
12. **Does WHERE affect the analytic window?** Yes; WHERE filters out input rows before analytic functions are evaluated.
13. **Can an aggregate be used inside an analytic function?** Yes; for example, `SUM(SUM(amount)) OVER()` after GROUP BY.
14. **How does COUNT(*) OVER differ from COUNT(expr) OVER?** COUNT(*) counts all rows; COUNT(expr) ignores NULL expr values.
15. **Why can analytic functions use TEMP?** The sort/window workarea may not fit in PGA and may need to spill intermediate data.
16. **How do you get one row per department along with the company total?** GROUP BY department, then apply an analytic function over the grouped results, e.g., `SUM(SUM(salary)) OVER()`.

When choosing between an aggregate function and an analytic function, determine **the grain of the result you need to return**. If you need one row per group, use an aggregate with GROUP BY. If you need to keep individual rows while adding totals, ranks, running totals, or preceding/following values, use an analytic function with OVER. Then define the partition, ordering, and frame clearly; these three components determine the exact window Oracle uses to compute on each row.
