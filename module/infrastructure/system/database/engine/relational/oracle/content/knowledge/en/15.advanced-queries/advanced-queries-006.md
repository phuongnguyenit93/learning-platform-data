# Global Top-N and Top-N per Group in Oracle Database

In reporting systems and business applications, it is very common to retrieve the **top N records**: the 10 largest orders, the 20 best-selling products, the 5 highest-performing employees in each department, or the 3 most recent transactions for each account. This class of requirements is called a **Top-N query**.

In Oracle Database, there are several ways to implement Top-N:

- **Global Top-N:** ranks the entire result set and takes the top N rows.
- **Top-N per group:** partitions the data into groups, ranks within each group independently, and takes the top N rows per group.
- **Top-N with ties:** decides whether to include additional rows tied at the same score as the boundary row.
- **Top-N on aggregated data:** computes `SUM`, `COUNT`, or `AVG` per group first, then ranks the groups or products afterward.

The most important decisions are clarifying **exact N rows vs. N rank tiers**, **tie-handling rules**, **whether sort order is deterministic**, and **which syntax your Oracle version supports**. A SQL statement can be syntactically valid yet return business-incorrect results if `ROW_NUMBER` is used instead of `RANK`, or if `ROWNUM` is placed in the wrong position relative to `ORDER BY`.

## 1. What Is Top-N?

Suppose an orders table has columns `ORDER_ID`, `CUSTOMER_ID`, `AMOUNT`, and `CREATED_AT`. The requirement "get the 5 highest-value orders" is a global Top-N:

```sql
SELECT order_id, customer_id, amount
FROM orders
ORDER BY amount DESC, order_id
FETCH FIRST 5 ROWS ONLY;
```

The requirement "get the 5 highest-value orders **for each customer**" is Top-N per group:

```sql
SELECT order_id, customer_id, amount
FROM (
    SELECT o.*,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY amount DESC, order_id
           ) AS rn
    FROM orders o
)
WHERE rn <= 5
ORDER BY customer_id, rn;
```

The two queries differ in their ranking scope:

```text
GLOBAL TOP-N
All rows --------------------> Global sort -------> Take N rows

TOP-N PER GROUP
All rows --> Partition --> Rank per group --> Take N/group
```

If there are 10 departments, a global Top-3 returns at most 3 rows for the entire company; a per-department Top-3 can return up to 30 rows. Never confuse the two requirements simply because both use the phrase "Top 3".

## 2. Preparing Practice Data

The examples use a mock table `LAB_EMP_SALES` containing employees, departments, sales amounts, transaction dates, and statuses. The data intentionally includes **tied sales amounts**, multiple rows per department, and some `NULL` values to illustrate ties and missing-data handling.

Create the table only in a **DEV/TEST** schema granted `CREATE TABLE` and quota. Before running DDL, verify the service, PDB, and user:

```sql
SELECT
    SYS_CONTEXT('USERENV', 'CON_NAME')       AS container_name,
    SYS_CONTEXT('USERENV', 'SERVICE_NAME')   AS service_name,
    SYS_CONTEXT('USERENV', 'SESSION_USER')   AS session_user
FROM dual;
```

### 2.1. Creating the lab table

```sql
CREATE TABLE lab_emp_sales (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80 CHAR) NOT NULL,
    department_id NUMBER NOT NULL,
    sales_amount  NUMBER(12, 2),
    sold_at       DATE NOT NULL,
    status        VARCHAR2(20 CHAR) NOT NULL
);
```

`SALES_AMOUNT` allows `NULL` so we can discuss how rows without recorded sales are ranked. In a production system, clarify whether `NULL` means unmeasured, zero sales, or not applicable; do not replace it with 0 without a business rule.

### 2.2. Loading mock data

```sql
INSERT ALL
    INTO lab_emp_sales VALUES (1,  'An',     10, 9500, DATE '2026-11-01', 'ACTIVE')
    INTO lab_emp_sales VALUES (2,  'Binh',   10, 9000, DATE '2026-11-02', 'ACTIVE')
    INTO lab_emp_sales VALUES (3,  'Chi',    10, 9000, DATE '2026-11-03', 'ACTIVE')
    INTO lab_emp_sales VALUES (4,  'Dung',   10, 7000, DATE '2026-11-04', 'ACTIVE')
    INTO lab_emp_sales VALUES (5,  'Em',     10, NULL, DATE '2026-11-05', 'PENDING')
    INTO lab_emp_sales VALUES (6,  'Giang',  20, 12000,DATE '2026-11-01', 'ACTIVE')
    INTO lab_emp_sales VALUES (7,  'Ha',     20, 11000,DATE '2026-11-02', 'ACTIVE')
    INTO lab_emp_sales VALUES (8,  'Khanh',  20, 11000,DATE '2026-11-03', 'ACTIVE')
    INTO lab_emp_sales VALUES (9,  'Lan',    20, 8000, DATE '2026-11-04', 'ACTIVE')
    INTO lab_emp_sales VALUES (10, 'Minh',   30, 6000, DATE '2026-11-01', 'ACTIVE')
    INTO lab_emp_sales VALUES (11, 'Nhi',    30, 5000, DATE '2026-11-02', 'ACTIVE')
    INTO lab_emp_sales VALUES (12, 'Oanh',   30, 5000, DATE '2026-11-03', 'ACTIVE')
    INTO lab_emp_sales VALUES (13, 'Phuc',   30, 3000, DATE '2026-11-04', 'ACTIVE')
    INTO lab_emp_sales VALUES (14, 'Quynh',  30, NULL, DATE '2026-11-05', 'PENDING')
SELECT 1 FROM dual;

COMMIT;
```

The dataset has three departments: `10`, `20`, and `30`. Department 10 has two employees tied at 9000; department 20 has two employees tied at 11000; department 30 has two employees tied at 5000. Two pending employees have `NULL` sales.

### 2.3. Inspecting source data

```sql
SELECT employee_id, employee_name, department_id,
       sales_amount, sold_at, status
FROM lab_emp_sales
ORDER BY department_id, sales_amount DESC NULLS LAST, employee_id;
```

This is an intentional display order for inspecting the table. It does not alter stored data and does not establish a fixed order for other queries that lack their own `ORDER BY`.

## 3. Global Top-N Using ORDER BY and FETCH FIRST

In Oracle Database **12c Release 1 and later**, the row limiting clause lets you write Top-N directly with `FETCH FIRST` or `FETCH NEXT`.

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS ONLY;
```

The query:

1. Filters for `ACTIVE` employees.
2. Sorts by sales amount descending.
3. Uses `EMPLOYEE_ID` as a tie-breaker so the order stays deterministic when sales amounts are equal.
4. Takes the first 5 rows of the entire result set.

On the lab dataset, the result consists of employee IDs `6`, `7`, `8`, `1`, and `2` (with the 11000 tie broken by ID 7 before ID 8; the 9000 tie broken by ID 2 before ID 3). There are only **5 rows globally**, not 5 rows per department.

### 3.1. FETCH FIRST vs. FETCH NEXT

The two forms have the same purpose when `OFFSET` is absent:

```sql
SELECT employee_id, sales_amount
FROM lab_emp_sales
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS ONLY;
```

```sql
SELECT employee_id, sales_amount
FROM lab_emp_sales
ORDER BY sales_amount DESC, employee_id
FETCH NEXT 5 ROWS ONLY;
```

`FIRST` and `NEXT` are both valid keywords in the row limiting clause; when an offset is present, `NEXT` is often easier to read as "fetch the next N rows after skipping".

### 3.2. OFFSET for pagination

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
OFFSET 5 ROWS FETCH NEXT 5 ROWS ONLY;
```

The query skips the first 5 rows and fetches the next 5 rows. `OFFSET` and `FETCH` operate on **the sorted result**. Without `ORDER BY`, which rows are skipped and which are returned has no stable order.

### 3.3. Top-N by percentage

Oracle supports percentage-based row limiting in versions with the row limiting clause:

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 25 PERCENT ROWS ONLY;
```

`PERCENT` retrieves a percentage of qualifying rows in the result. The actual row count depends on the row limiting clause's rounding rules and the total number of rows after filtering; do not replace it with an application-side estimate if exact Oracle semantics are required.

## 4. Global Top-N with Ties: WITH TIES

The requirement "get the 5 highest-selling employees, **including everyone tied with 5th place**" differs from "get exactly 5 rows". Oracle supports:

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS WITH TIES;
```

`WITH TIES` requires `ORDER BY`. Oracle retrieves at least 5 rows and appends any subsequent rows that share the same sort key value as the last row. With the lab data, the top positions are:

| Sales rank | Employee | Sales amount |
|---:|---|---:|
| 1 | Giang | 12000 |
| 2 | Ha | 11000 |
| 2 | Khanh | 11000 |
| 4 | An | 9500 |
| 5 | Binh | 9000 |
| 5 | Chi | 9000 |

The `WITH TIES` result has **6 rows**, because both Binh and Chi are tied at the 5th row's sales level.

### 4.1. Do not add a secondary unique key if you want ties on sales amount

Compare:

```sql
-- Includes everyone tied in sales with the 5th row.
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS WITH TIES;
```

with:

```sql
-- Because employee_id is unique, no rows can tie across the entire sort key.
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS WITH TIES;
```

`WITH TIES` evaluates **every expression in `ORDER BY`**. Adding a unique `EMPLOYEE_ID` to the sort key means two people with the same sales but different IDs are no longer considered tied. Therefore:

- To get an exact, deterministic N rows: add a unique key as tie-breaker and use `ONLY`.
- To get all rows tied on sales amount: sort only by `SALES_AMOUNT` in the `WITH TIES` query.
- If you also need a deterministic display order among tied rows, wrap the `WITH TIES` Top-N query and sort the outer query by `SALES_AMOUNT DESC, EMPLOYEE_ID`.

Example:

```sql
SELECT employee_id, employee_name, sales_amount
FROM (
    SELECT employee_id, employee_name, sales_amount
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
    ORDER BY sales_amount DESC
    FETCH FIRST 5 ROWS WITH TIES
)
ORDER BY sales_amount DESC, employee_id;
```

### 4.2. WITH TIES vs. RANK and DENSE_RANK

`WITH TIES` in the row limiting clause is convenient for global Top-N by sort key. For Top-N per group, analytic ranking is usually more appropriate because each partition needs its own limit. The following sections explain `ROW_NUMBER`, `RANK`, and `DENSE_RANK`.

## 5. Global Top-N Using ROWNUM on Older Oracle Versions

Prior to Oracle 12c, the standard way to get global Top-N was **sorting in an inline view and filtering `ROWNUM` in the outer query**.

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM (
    SELECT employee_id, employee_name, department_id, sales_amount
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
    ORDER BY sales_amount DESC, employee_id
)
WHERE ROWNUM <= 5;
```

This is the classic Top-N pattern. `ORDER BY` in the inner query establishes the ranking order; the outer query limits `ROWNUM`.

### 5.1. Why shouldn't ROWNUM and ORDER BY be at the same query level?

Avoid writing:

```sql
-- Incorrect Top-N semantics: ROWNUM is assigned before the query block's ORDER BY finishes.
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
  AND ROWNUM <= 5
ORDER BY sales_amount DESC;
```

Within the same query block, Oracle assigns `ROWNUM` as rows are selected; `ORDER BY` then sorts those already-selected rows. The statement above can grab 5 arbitrary rows along the access path and sort just those 5 rows, **failing to guarantee the 5 highest sales in the table**.

Placing the sorted query inside an inline view ensures Oracle executes the Top-N logic properly:

```text
Inline view:
    FROM -> WHERE -> ORDER BY
                |
                v
        Sorted set by sales
                |
                v
Outer query:
    WHERE ROWNUM <= 5
                |
                v
              Top 5
```

### 5.2. ROWNUM > 1 does not work as many people expect

`ROWNUM` is assigned sequentially to rows selected in a query block. The condition:

```sql
WHERE ROWNUM > 1
```

in a simple query block typically returns zero rows: the first row evaluated gets `ROWNUM = 1` and is rejected; because it was never emitted, the next row is also evaluated as the first row with `ROWNUM = 1`, and rejected as well. This is why `ROWNUM > :offset` cannot be used directly for pagination.

### 5.3. ROWNUM-style pagination

On older Oracle versions without `OFFSET ... FETCH`, you can use two nested inline views:

```sql
SELECT employee_id, employee_name, sales_amount
FROM (
    SELECT ordered_rows.*,
           ROWNUM AS rn
    FROM (
        SELECT employee_id, employee_name, sales_amount
        FROM lab_emp_sales
        WHERE status = 'ACTIVE'
        ORDER BY sales_amount DESC, employee_id
    ) ordered_rows
    WHERE ROWNUM <= :offset_value + :page_size
)
WHERE rn > :offset_value
ORDER BY sales_amount DESC, employee_id;
```

The innermost query sorts the data; the middle layer caps up to the end of the page; the outer layer discards rows before the offset. Bind `:offset_value` and `:page_size` must be validated as non-negative numbers, and `page_size` should have a reasonable upper bound to prevent returning excessive data.

## 6. Top-N per Group Using ROW_NUMBER

This is the most common form of Top-N per group. Oracle analytic functions split the data into partitions and number rows independently inside each partition.

```sql
SELECT employee_id, employee_name, department_id, sales_amount, rn
FROM (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
WHERE rn <= 2
ORDER BY department_id, rn;
```

Explanation:

- `PARTITION BY department_id`: divides data into department groups. Numbering restarts at 1 for each department.
- `ORDER BY sales_amount DESC NULLS LAST, employee_id`: higher sales come first; nulls last; ID breaks ties.
- `ROW_NUMBER()`: assigns a unique sequential number to each row in the partition.
- Outer `WHERE rn <= 2`: retains the top two rows in each department.
- Outer `ORDER BY department_id, rn`: orders the final output cleanly.

Result on the lab dataset:

| Department | `RN` | Employee | Sales amount |
|---:|---:|---|---:|
| 10 | 1 | An | 9500 |
| 10 | 2 | Binh | 9000 |
| 20 | 1 | Giang | 12000 |
| 20 | 2 | Ha | 11000 |
| 30 | 1 | Minh | 6000 |
| 30 | 2 | Nhi | 5000 |

Each department has at most 2 rows, totaling 6 rows. Because `ROW_NUMBER` needs a deterministic ordering if repeatable output is desired, include a unique column such as `EMPLOYEE_ID` at the end of `ORDER BY` when ties must be broken.

### 6.1. Why is an outer query required to filter rn?

In Oracle, analytic functions are evaluated after `FROM`, `WHERE`, `GROUP BY`, and `HAVING` within the same query block. Therefore you cannot filter an analytic alias directly in the same-level `WHERE` clause:

```sql
-- Invalid in the same query block:
SELECT employee_id,
       ROW_NUMBER() OVER (ORDER BY sales_amount DESC) AS rn
FROM lab_emp_sales
WHERE rn <= 5;
```

The alias `RN` does not yet exist at the `WHERE` stage; this raises `ORA-00904` or an invalid identifier error. Wrap it in an inline view or CTE to filter in the outer query block:

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id, sales_amount, rn
FROM ranked_sales
WHERE rn <= 2
ORDER BY department_id, rn;
```

A CTE names the "ranking" step and makes long queries easier to read.

## 7. Top-N per Group with Ties: RANK and DENSE_RANK

`ROW_NUMBER` always assigns a distinct number to every row, even when two rows have identical sales. Business rules sometimes require **keeping all tied employees** instead of arbitrarily picking one at the Top-N cutoff. In that case, understand these two analytic functions:

- `RANK()`: tied rows receive the same rank; the next position leaves a gap.
- `DENSE_RANK()`: tied rows receive the same rank; the next position increments consecutively without gaps.

### 7.1. Table illustrating the three ranking functions

Suppose sales are sorted descending:

| Employee | Sales | `ROW_NUMBER` | `RANK` | `DENSE_RANK` |
|---|---:|---:|---:|---:|
| A | 100 | 1 | 1 | 1 |
| B | 95 | 2 | 2 | 2 |
| C | 95 | 3 | 2 | 2 |
| D | 90 | 4 | 4 | 3 |
| E | 80 | 5 | 5 | 4 |

For the tied value 95:

- `ROW_NUMBER` assigns 2 and 3 (order between B and C is non-deterministic without a tie-breaker).
- `RANK` assigns 2 to both, then the next rank is 4.
- `DENSE_RANK` assigns 2 to both, then the next rank is 3.

### 7.2. RANK <= N: Top-N positions including ties

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sales_rank
FROM ranked_sales
WHERE sales_rank <= 2
ORDER BY department_id, sales_rank, employee_id;
```

In each department, everyone tied at position 2 is kept. Department 10 keeps An, Binh, and Chi (ranks 1, 2, 2); department 20 keeps Giang, Ha, and Khanh (ranks 1, 2, 2); department 30 keeps Minh, Nhi, and Oanh (ranks 1, 2, 2). That totals 9 rows, more than `ROW_NUMBER <= 2`.

**Do not put `EMPLOYEE_ID` inside `ORDER BY` of `RANK` if you want ties on sales**, because distinct IDs will break the ties. You can put the ID in the outer `ORDER BY` to sort tied rows consistently without affecting computed ranks.

### 7.3. DENSE_RANK <= N: N distinct sales tiers

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_dense_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sales_dense_rank
FROM ranked_sales
WHERE sales_dense_rank <= 2
ORDER BY department_id, sales_dense_rank, employee_id;
```

On the lab dataset, the output matches `RANK <= 2` because the ties occur at the second tier. However, in the A=100, B/C=95, D=90 example:

- `RANK <= 3` keeps A, B, C; D has rank 4 and is excluded.
- `DENSE_RANK <= 3` keeps A, B, C, D because those are the top three distinct sales levels.

Thus, you must select the function based on how business logic defines "Top N".

### 7.4. Quick comparison of ROW_NUMBER, RANK, and DENSE_RANK

| Function | Tied values | Rank gaps | Row count when filtering `<= N` | Business question |
|---|---|---|---|---|
| `ROW_NUMBER` | Each row gets a distinct number | No gaps | At most N rows per group | Pick an exact N records |
| `RANK` | Same rank value | Gaps after ties | Can exceed N rows | Get rows within the top N positions, including ties |
| `DENSE_RANK` | Same rank value | No gaps | Can exceed N rows | Get the first N distinct value/rank tiers |

## 8. NULLs in Top-N and NULLS FIRST/LAST Ordering

If the ranking column can be `NULL`, define whether nulls are considered lowest, highest, or should be excluded from ranking.

Oracle's defaults are:

- `ORDER BY value ASC`: `NULLS LAST`.
- `ORDER BY value DESC`: `NULLS FIRST`.

Therefore, the statement:

```sql
SELECT employee_id, sales_amount
FROM lab_emp_sales
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS ONLY;
```

can put `NULL` sales rows at the very top due to Oracle's default for descending sorts. If `NULL` means "no figure yet" and should not appear in Top-N, specify explicitly:

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC NULLS LAST, employee_id
FETCH FIRST 5 ROWS ONLY;
```

Or filter nulls out first:

```sql
WHERE status = 'ACTIVE'
  AND sales_amount IS NOT NULL
```

These two options behave differently if Top-N should still include null rows at the end when N is large enough. Choose according to business rules.

### 8.1. NULLs in analytic ranking

For Top-N per group, also specify explicitly:

```sql
ROW_NUMBER() OVER (
    PARTITION BY department_id
    ORDER BY sales_amount DESC NULLS LAST, employee_id
)
```

If `NULLS LAST` is omitted, null sales rows can be sorted first under `DESC` and slip into Top-N. If nulls are removed with `WHERE sales_amount IS NOT NULL` in the inner query, those rows are not ranked at all; if only `NULLS LAST` is used, they are still ranked, at the bottom of the partition.

## 9. Top-N per Group After Aggregating Data

A more realistic requirement: "Get the 3 highest-revenue products in each region". The transactions table may have multiple rows for the same product. You must **aggregate first**, then rank products within each region.

```sql
WITH product_totals AS (
    SELECT region_id,
           product_id,
           SUM(quantity * unit_price) AS revenue
    FROM sales_transactions
    WHERE transaction_status = 'COMPLETED'
    GROUP BY region_id, product_id
), ranked_products AS (
    SELECT region_id,
           product_id,
           revenue,
           ROW_NUMBER() OVER (
               PARTITION BY region_id
               ORDER BY revenue DESC, product_id
           ) AS rn
    FROM product_totals
)
SELECT region_id, product_id, revenue, rn
FROM ranked_products
WHERE rn <= 3
ORDER BY region_id, rn;
```

Logical sequence:

1. `WHERE` excludes non-completed transactions.
2. `GROUP BY region_id, product_id` computes per-product revenue in each region.
3. `SUM` calculates total revenue.
4. `ROW_NUMBER` ranks products independently within each region.
5. The outer query keeps the top three products per region.

If you ranked individual transactions before `GROUP BY`, the output would no longer answer "products with the highest total revenue". Clarify whether the **ranked unit** is a transaction, product, employee, or aggregated group.

### 9.1. Global Top-N groups after GROUP BY

If you need the 10 highest-spending customers system-wide:

```sql
SELECT customer_id,
       SUM(order_amount) AS total_spend
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id
ORDER BY total_spend DESC, customer_id
FETCH FIRST 10 ROWS ONLY;
```

This is a global Top-N on **aggregated customer groups**, not the 10 highest-value orders. `FETCH FIRST` applies after groups are formed and sorted.

### 9.2. Top-N groups with ties on total revenue

```sql
SELECT customer_id,
       SUM(order_amount) AS total_spend
FROM orders
WHERE order_status = 'PAID'
GROUP BY customer_id
ORDER BY total_spend DESC
FETCH FIRST 10 ROWS WITH TIES;
```

The query keeps all customers tied with 10th place on `TOTAL_SPEND`. Adding a unique `CUSTOMER_ID` to `ORDER BY` eliminates ties across the full sort key; add a secondary key only if you want exactly 10 deterministically ordered groups.

## 10. Top-N per Group with Multiple Ranking Criteria

Top-N may require secondary criteria: highest sales first, if tied then most recent sale first, if still tied then lowest ID first.

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           sold_at,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST,
                        sold_at DESC,
                        employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sold_at, rn
FROM ranked_sales
WHERE rn <= 3
ORDER BY department_id, rn;
```

Ordering inside `OVER (...)` determines **how ranking is computed**; the final `ORDER BY` determines **how results are presented**. The two lists can differ and serve distinct purposes.

### 10.1. Ties based on a single metric only

If ties are defined purely on sales while display order must remain deterministic, separate ranking from sorting:

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id,
       sales_amount, sales_rank
FROM ranked_sales
WHERE sales_rank <= 3
ORDER BY department_id, sales_rank, employee_id;
```

`EMPLOYEE_ID` appears only in the outer `ORDER BY`, so it does not break ranking ties. This is an easily reusable pattern when reports require ties alongside stable display ordering.

## 11. ROW_NUMBER, RANK, and DENSE_RANK for Global Top-N

The three analytic functions are not restricted to Top-N per group; they can apply to the whole table by omitting `PARTITION BY`.

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, department_id, sales_amount
FROM ranked_sales
WHERE rn <= 5
ORDER BY rn;
```

This writes global Top-5 using an analytic function. Compared with `FETCH FIRST`, it is more verbose, yet useful when you also need to return the rank, join with other tables, or apply additional filters after ranking.

With ties:

```sql
WITH ranked_sales AS (
    SELECT employee_id,
           employee_name,
           sales_amount,
           RANK() OVER (
               ORDER BY sales_amount DESC NULLS LAST
           ) AS sales_rank
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT employee_id, employee_name, sales_amount, sales_rank
FROM ranked_sales
WHERE sales_rank <= 5
ORDER BY sales_rank, employee_id;
```

This pattern expresses global "Top 5 positions with ties". For queries needing only a simple row limit, `FETCH FIRST ... WITH TIES` is more concise.

## 12. Top-N per Group and Groups Without Data

One point to watch: if the ranking query starts from a fact table like `LAB_EMP_SALES`, departments **with no rows** will not appear in the output. If the report must display every department, including groups without employees or sales, start from the departments lookup table and `LEFT JOIN` the Top-N set.

Conceptual example:

```sql
WITH ranked_employees AS (
    SELECT employee_id,
           department_id,
           sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM employees
    WHERE status = 'ACTIVE'
)
SELECT d.department_id,
       d.department_name,
       r.employee_id,
       r.sales_amount,
       r.rn
FROM departments d
LEFT JOIN ranked_employees r
  ON r.department_id = d.department_id
 AND r.rn <= 3
ORDER BY d.department_id, r.rn;
```

Putting `r.rn <= 3` in the `ON` clause preserves departments that have no ranked employees; putting it in `WHERE` filters out right-side null rows and turns the `LEFT JOIN` into an inner join. `DEPARTMENTS`/`EMPLOYEES` are hypothetical business table names.

## 13. Top-N per Group with LATERAL/CROSS APPLY (When Appropriate)

In Oracle versions supporting `CROSS APPLY`/`OUTER APPLY` and the row limiting clause, you can fetch Top-N separately for each parent row using a correlated subquery:

```sql
SELECT d.department_id,
       d.department_name,
       e.employee_id,
       e.employee_name,
       e.sales_amount
FROM departments d
CROSS APPLY (
    SELECT employee_id, employee_name, sales_amount
    FROM employees e
    WHERE e.department_id = d.department_id
      AND e.status = 'ACTIVE'
    ORDER BY e.sales_amount DESC NULLS LAST, e.employee_id
    FETCH FIRST 3 ROWS ONLY
) e
ORDER BY d.department_id, e.sales_amount DESC, e.employee_id;
```

`CROSS APPLY` executes the right-side query per department row and retains only departments with at least one matching row. If you want to keep departments with no employees as well, use `OUTER APPLY` where supported by your version. This is an alternative syntax, though **analytic `ROW_NUMBER` is generally more versatile and convenient across many groups**. Choose based on Oracle version, optimizer plan, and query complexity.

## 14. Time-Based Top-N: Latest Records in Each Group

A very common Top-N pattern is retrieving the 1 or N most recent records per account, device, order, or customer.

```sql
WITH ranked_events AS (
    SELECT event_id,
           account_id,
           event_type,
           occurred_at,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY occurred_at DESC, event_id DESC
           ) AS rn
    FROM account_events
)
SELECT event_id, account_id, event_type, occurred_at
FROM ranked_events
WHERE rn <= 3
ORDER BY account_id, occurred_at DESC, event_id DESC;
```

Each account retrieves up to its three latest events. `EVENT_ID` acts as a tie-breaker so output remains stable when multiple events share the same timestamp. If business rules want **all events tied at the third timestamp**, use `RANK` on `OCCURRED_AT` and use `EVENT_ID` only in the outer sort.

### 14.1. Fetching the single latest record per group

The `ROW_NUMBER() = 1` pattern is commonly used to pick the latest record:

```sql
WITH latest_event AS (
    SELECT event_id,
           account_id,
           event_type,
           occurred_at,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY occurred_at DESC, event_id DESC
           ) AS rn
    FROM account_events
)
SELECT event_id, account_id, event_type, occurred_at
FROM latest_event
WHERE rn = 1;
```

If `OCCURRED_AT` can be `NULL`, decide whether nulls come first or last. For a typical "latest" requirement, `NULLS LAST` is the clear choice when null means missing timestamp:

```sql
ORDER BY occurred_at DESC NULLS LAST, event_id DESC
```

## 15. Top-N per Group with Filters: Filter Before or After Ranking?

Where `WHERE` is placed directly affects which rows are ranked. For instance, finding the top 3 `ACTIVE` employees by sales in each department:

```sql
WITH ranked AS (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales e
    WHERE status = 'ACTIVE'
)
SELECT employee_id, department_id, sales_amount
FROM ranked
WHERE rn <= 3;
```

The inner `WHERE status = 'ACTIVE'` runs before the analytic function; only active employees are ranked. If you move the status condition outside:

```sql
WITH ranked AS (
    SELECT e.*,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales e
)
SELECT employee_id, department_id, sales_amount
FROM ranked
WHERE rn <= 3
  AND status = 'ACTIVE';
```

then `PENDING` employees participate in ranking first and are filtered out afterward. A department might end up with only 2 active employees even though eligible active employees exist further down. The two queries answer **two different questions**:

- Top 3 within the set of active employees.
- Top 3 across all employees, then show only those who are active.

When writing Top-N, clearly distinguish which filters restrict **the candidate pool to be ranked** and which filters restrict only **the displayed output**.

## 16. Optimizing Top-N Performance

Top-N is not just syntax; on large tables, query structure and indexing strongly affect execution time.

### 16.1. Indexing on filter columns and ranking order

For the query:

```sql
SELECT employee_id, department_id, sales_amount
FROM lab_emp_sales
WHERE department_id = :department_id
  AND status = 'ACTIVE'
ORDER BY sales_amount DESC, employee_id
FETCH FIRST 5 ROWS ONLY;
```

you can evaluate an index starting with the filter columns followed by the ranking columns, for example:

```sql
CREATE INDEX ix_lab_sales_dept_status_top
ON lab_emp_sales (
    department_id,
    status,
    sales_amount DESC,
    employee_id
);
```

This is merely a **candidate index to benchmark**, not an automatic recommendation for every table. Effectiveness depends on selectivity of `DEPARTMENT_ID`/`STATUS`, table size, sales distribution, columns returned, DML overhead, and optimizer statistics. For a global Top-N query that does not filter by department, an index leading with department may be unsuitable.

### 16.2. Top-N per group is harder than global Top-N

Global Top-N can stop once it finds N rows via a suitable access path. Top-N per group must find enough top rows for **every partition**; if there are many groups or scattered data, Oracle may need to process and sort far more rows. Analytic functions are usually the clearest expression, though the execution plan may include sort/window operations and use TEMP for large datasets.

### 16.3. Avoid adding extra columns to ORDER BY unnecessarily

Adding a unique tie-breaker makes `ROW_NUMBER` deterministic, but changes how ties are defined in `RANK` or `WITH TIES`. Separate the two goals:

- **Tie semantics:** which columns define two rows as tied?
- **Display determinism:** which columns are needed for stable display sorting?

With `RANK`, put only the business metric in the analytic `ORDER BY`; put the tie-breaking key in the outer `ORDER BY`.

### 16.4. Select only the necessary columns

Avoid `SELECT *` in large Top-N queries when the application needs only a few columns. Fetching fewer columns reduces I/O, network bandwidth, and sort memory, and gives the optimizer more index choices. However, do not create excessively wide covering indexes solely to avoid table access if the DML/storage cost is unwarranted.

### 16.5. Inspect the execution plan

When a query is slow, check:

- Can any predicate filter rows earlier?
- Does `ORDER BY` have to sort all data, or can a suitable index help?
- Is the analytic window partitioning/sorting too large?
- Are cardinality estimates skewed due to stale statistics?
- Are TEMP/PGA usage, parallelism, and output row counts reasonable?

Do not force an `INDEX` hint or rewrite `ROW_NUMBER` to `ROWNUM` simply hoping for speed without measuring. Correct Top-N semantics and tie stability come first.

## 17. Common Pitfalls

| Symptom/assumption | Cause | Resolution |
|---|---|---|
| Top-5 does not return the 5 highest values | Filtering `ROWNUM <= 5` in the same query block as `ORDER BY` | Put `ORDER BY` in an inline view and filter ROWNUM outside, or use FETCH FIRST |
| `ROWNUM > 1` returns no rows | ROWNUM is assigned as rows are selected in the query block | Use analytic `ROW_NUMBER` or the two-level inline view pagination pattern |
| Top-3 per department returns only 3 rows company-wide | Using global FETCH FIRST/ROWNUM | Use `ROW_NUMBER() OVER (PARTITION BY ...)` and filter in the outer query |
| Cannot filter `rn` alias in Top-N per group | Analytic aliases do not exist in the same query block's WHERE | Wrap in a CTE or inline view |
| Employees with tied sales are missing from output | Using ROW_NUMBER and taking only N rows | Use RANK or DENSE_RANK depending on tie definition |
| Output has more than N rows | `RANK <= N`, `DENSE_RANK <= N`, or WITH TIES | Decide whether you need exactly N rows or to include ties |
| Two people with equal scores no longer tie | Unique ID included in ORDER BY of RANK/WITH TIES | Use only the tie metric in ranking; sort deterministically outside |
| NULL rows slip into DESC Top-N | Default DESC places NULLS FIRST | Specify `NULLS LAST` or filter `IS NOT NULL` |
| Top-N after GROUP BY ranks the wrong grain | Ranking transactions before aggregating | Aggregate first, apply analytic ranking afterward |
| Top-N per group drops groups with no rows | Starting from the fact table | LEFT JOIN from the group lookup table; place rank filter in ON |
| Next page duplicates or skips rows | Non-unique ORDER BY or underlying data changed | Add a unique tie-breaker; consider keyset pagination/snapshots |
| Query gives different results across runs | Unbroken ties or missing outer ORDER BY | Specify a complete, deterministic order |
| Using FETCH FIRST on an older release | Database version lacks the row limiting clause | Use version-appropriate ROWNUM/analytic patterns |

## 18. Controlled Practice

The exercises below use `LAB_EMP_SALES`. Run only on DEV/TEST in an authorized schema. Never run DDL or cleanup operations on production.

### Exercise 1 — Global Top-5

```sql
SELECT employee_id, employee_name, department_id, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC NULLS LAST, employee_id
FETCH FIRST 5 ROWS ONLY;
```

Verify there are 5 rows and explain the role of `EMPLOYEE_ID` in ties.

### Exercise 2 — Top-5 with ties

```sql
SELECT employee_id, employee_name, sales_amount
FROM lab_emp_sales
WHERE status = 'ACTIVE'
ORDER BY sales_amount DESC
FETCH FIRST 5 ROWS WITH TIES;
```

Count the rows. Add `EMPLOYEE_ID` to `ORDER BY` and observe why the row count drops back to exactly 5.

### Exercise 3 — Top-2 per department

```sql
WITH ranked AS (
    SELECT employee_id, employee_name, department_id, sales_amount,
           ROW_NUMBER() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST, employee_id
           ) AS rn
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT *
FROM ranked
WHERE rn <= 2
ORDER BY department_id, rn;
```

Expected output: 6 rows, two employees per department.

### Exercise 4 — Top-2 with ties per department

```sql
WITH ranked AS (
    SELECT employee_id, employee_name, department_id, sales_amount,
           RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS rnk
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT *
FROM ranked
WHERE rnk <= 2
ORDER BY department_id, rnk, employee_id;
```

Explain why the output has 9 rows even though the requirement asks for 2.

### Exercise 5 — Top-2 distinct sales levels

```sql
WITH ranked AS (
    SELECT employee_id, employee_name, department_id, sales_amount,
           DENSE_RANK() OVER (
               PARTITION BY department_id
               ORDER BY sales_amount DESC NULLS LAST
           ) AS drnk
    FROM lab_emp_sales
    WHERE status = 'ACTIVE'
)
SELECT *
FROM ranked
WHERE drnk <= 2
ORDER BY department_id, drnk, employee_id;
```

Compare with `RANK <= 2`. Create a dataset with a tie at position three to see the difference between gapped rank and dense rank.

### Exercise 6 — Top-3 after aggregation

From a hypothetical transactions table, write a CTE computing `SUM(quantity * unit_price)` by `region_id, product_id`, then use `ROW_NUMBER` with `PARTITION BY region_id` to retrieve the top three products per region. Clearly identify which transaction filters run before aggregation.

### Exercise 7 — Latest record in each group

From a hypothetical events table, use `ROW_NUMBER() OVER (PARTITION BY account_id ORDER BY occurred_at DESC NULLS LAST, event_id DESC)` and filter `rn = 1`. Explain why the secondary key `EVENT_ID` is needed.

### Exercise 8 — Comparing pre-ranking and post-ranking filters

Run the two queries from section 15, one filtering `ACTIVE` before the analytic function and one filtering after it. Count the remaining employees in each department and explain how the two outputs answer different questions.

### Cleaning up lab data

Only after confirming the mock table was created by you in DEV/TEST and no one else is using it:

```sql
DROP TABLE lab_emp_sales PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data without sending it to the recycle bin; this is DDL with an implicit commit. Never run on production or any table outside the practice scope.

## 19. Review Questions

**Question 1.** How does global Top-5 differ from Top-5 within each department?

**Answer:** Global Top-5 takes at most 5 rows across the entire dataset; Top-5 per group splits into partitions and takes at most 5 rows within each group.

**Question 2.** In Oracle 12c and later, what concise syntax can express global Top-N?

**Answer:** `ORDER BY ... FETCH FIRST N ROWS ONLY`.

**Question 3.** Why is `WHERE ROWNUM <= 5 ORDER BY sales_amount DESC` not a valid Top-5 pattern?

**Answer:** ROWNUM is assigned in the query block before the final ORDER BY sorts; you must sort in an inline view first and filter ROWNUM outside.

**Question 4.** To get exactly 3 rows per department, still returning only 3 rows even when ties occur, which function should you use?

**Answer:** `ROW_NUMBER()` with a deterministic tie-breaker in the analytic `ORDER BY`, then filter `rn <= 3`.

**Question 5.** To get every employee ranked within the top three positions, including ties, which function should you use?

**Answer:** `RANK()` and filter `rank <= 3`.

**Question 6.** To get the three highest distinct sales levels in each department, which function should you use?

**Answer:** `DENSE_RANK()` and filter `dense_rank <= 3`.

**Question 7.** Why shouldn't `EMPLOYEE_ID` be placed in `ORDER BY` inside `RANK()` when you want to preserve tied salespeople?

**Answer:** A unique ID makes the sort key distinct and breaks sales ties. Put the ID in the outer `ORDER BY` for stable sorting.

**Question 8.** In Oracle, where does `ORDER BY sales_amount DESC` place NULLs by default?

**Answer:** `NULLS FIRST`. If NULL means unrecorded data, you usually need `NULLS LAST` explicitly or to filter out nulls.

**Question 9.** When retrieving the Top-3 products by revenue per region from a transactions table, what must be done before ranking?

**Answer:** `GROUP BY` region and product and sum revenue first; then rank the aggregated products within each region.

**Question 10.** Why is an outer query required to filter `ROW_NUMBER`?

**Answer:** Analytic functions are evaluated after WHERE in the same query block; analytic aliases cannot be referenced in the same-level WHERE clause.

**Question 11.** Which columns does `FETCH FIRST 5 ROWS WITH TIES` check for ties?

**Answer:** The entire sort key in `ORDER BY`. Adding a unique column can break ties.

**Question 12.** Without `ORDER BY`, is Top-N guaranteed to return the same rows across executions?

**Answer:** No. Without a deterministic ordering, Oracle does not guarantee which rows are picked or a stable display order.

## Conclusion

**Global Top-N** retrieves the top N rows across the entire dataset; in Oracle 12c and later you can use `ORDER BY ... FETCH FIRST N ROWS ONLY`, or `WITH TIES` when tied boundary rows must be kept. On older versions, the correct `ROWNUM` pattern sorts inside an inline view first and filters in the outer query. Never combine `ROWNUM` at the same level as `ORDER BY` expecting the N largest values.

**Top-N per group** requires analytic functions with `PARTITION BY`: `ROW_NUMBER` for at most N rows per group, `RANK` to preserve positional ties with gaps, and `DENSE_RANK` for N distinct value tiers. When building reports, decide explicitly how to handle ties, NULLs, secondary sort criteria, and pre/post-ranking filter placement. If Top-N is based on total revenue or aggregated counts, aggregate first and rank afterward. Finally, always add an outer `ORDER BY` for deterministic presentation and check execution plans and indexes on realistic workloads.

## Oracle Reference Documentation

- [Oracle Database 19c — ROWNUM Pseudocolumn](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROWNUM-Pseudocolumn.html): how Oracle assigns ROWNUM and the Top-N inline view pattern.
- [Oracle Database 19c — SELECT: row_limiting_clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html): syntax for `OFFSET`, `FETCH FIRST/NEXT`, `ONLY`, `WITH TIES`, and `PERCENT`.
- [Oracle Database 19c — ROW_NUMBER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ROW_NUMBER.html): sequential numbering within a query partition.
- [Oracle Database 19c — RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/RANK.html): ranking with gaps on ties.
- [Oracle Database 19c — DENSE_RANK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DENSE_RANK.html): ranking without gaps on ties.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/SELECT.html): SELECT and row limiting syntax reference in current Oracle AI Database documentation.
