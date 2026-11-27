# Conditional Aggregation with CASE

When building reports, you often need multiple metrics for the same data group: total paid revenue, total pending revenue, cancelled order count, number of purchasing customers, and maximum order amount. If you run a separate SQL query for each metric, the application must send multiple queries and stitch the results together. Oracle can compute all of these metrics in **a single grouping pass** using **conditional aggregation** — placing a `CASE` expression inside an aggregate function such as `SUM`, `COUNT`, `AVG`, `MIN`, or `MAX`.

Core idea:

~~~sql
SUM(
    CASE
        WHEN condition THEN value
        ELSE 0
    END
)
~~~

`CASE` determines the value contributed by each row; the aggregate function then sums or counts those values within each group. This technique is especially useful in reports grouped by month, region, status, sales channel, and dashboards requiring multiple metric columns.

This lesson progresses from basic expressions to multiple conditions, `NULL` handling, safe ratios, `HAVING`, analytic functions, and common pitfalls when joining. The examples use Oracle SQL and a hypothetical `SALES_ORDERS` table.

## 1. What is conditional aggregation?

Suppose the `SALES_ORDERS` table has the following columns:

| Column | Meaning |
|---|---|
| `ORDER_ID` | Order ID |
| `CUSTOMER_ID` | Customer ID |
| `ORDER_DATE` | Order creation date |
| `REGION_ID` | Region ID |
| `CHANNEL` | Sales channel, e.g. `WEB` or `STORE` |
| `STATUS` | Status, e.g. `PAID`, `PENDING`, `CANCELLED` |
| `AMOUNT` | Order value |

Reporting requirement: for each region, calculate the total revenue of paid orders. You can write:

~~~sql
SELECT region_id,
       SUM(
           CASE
               WHEN status = 'PAID' THEN amount
               ELSE 0
           END
       ) AS paid_revenue
FROM sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

For each row:

- If `STATUS = 'PAID'`, `CASE` returns `AMOUNT`.
- Otherwise, `CASE` returns 0.
- `SUM` adds the values contributed by each row within the same `REGION_ID`.

~~~mermaid
flowchart TD
    A["SALES_ORDERS rows"] --> B["Group by REGION_ID"]
    B --> C["Evaluate each row in group"]
    C --> D{"STATUS = PAID?"}
    D -->|Yes| E["Contribute AMOUNT"]
    D -->|No| F["Contribute 0"]
    E --> G["SUM contributed values"]
    F --> G
    G --> H["One PAID_REVENUE result per region"]
~~~

This is a **conditional sum**. `GROUP BY` itself creates the groups; `CASE` decides which rows contribute what value to the metric.

## 2. CASE patterns inside aggregate functions

### 2.1 SUM(CASE ...): conditional summing

Common pattern:

~~~sql
SUM(
    CASE
        WHEN condition THEN numeric_expr
        ELSE 0
    END
)
~~~

Example summing paid orders:

~~~sql
SELECT SUM(
           CASE
               WHEN status = 'PAID' THEN amount
               ELSE 0
           END
       ) AS paid_total
FROM sales_orders;
~~~

If you only want to sum values of rows meeting the condition and leave remaining rows as `NULL`:

~~~sql
SELECT SUM(
           CASE
               WHEN status = 'PAID' THEN amount
           END
       ) AS paid_total
FROM sales_orders;
~~~

Both forms can return the same result when a group has at least one matching row with valid numeric data. However, when **no rows match the condition**, the results can differ:

- `SUM(CASE WHEN ... THEN amount ELSE 0 END)` returns 0 if the group has rows but none match.
- `SUM(CASE WHEN ... THEN amount END)` returns `NULL` if no row contributes a non-`NULL` value.

Choose the result based on reporting semantics. If "no revenue" should display as 0, the `ELSE 0` form is usually clearer. If you need to distinguish "no computable data" from "total genuinely equals 0," keep `NULL` or return a count metric alongside it.

### 2.2 COUNT(CASE ...): counting rows meeting a condition

Safe counting pattern:

~~~sql
COUNT(
    CASE
        WHEN status = 'PAID' THEN 1
    END
)
~~~

`COUNT(expression)` only counts **non-`NULL`** values. When the condition is true, `CASE` returns 1; when false, without an `ELSE` it returns `NULL` and is not counted.

Example:

~~~sql
SELECT region_id,
       COUNT(*) AS all_orders,
       COUNT(
           CASE
               WHEN status = 'PAID' THEN 1
           END
       ) AS paid_orders
FROM sales_orders
GROUP BY region_id;
~~~

**Common mistake:**

~~~sql
COUNT(
    CASE
        WHEN status = 'PAID' THEN 1
        ELSE 0
    END
)
~~~

The expression above counts **every row**, because both 1 and 0 are non-`NULL` values. When counting conditionally, omit `ELSE` or use `SUM(CASE WHEN ... THEN 1 ELSE 0 END)`.

Both of the following patterns count rows with PAID status:

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
~~~

~~~sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
~~~

The `COUNT` pattern expresses "count non-NULL expressions"; the `SUM` pattern expresses "add 1 for each qualifying row." For groups with rows, they usually yield the same count. If a query has zero rows and no `GROUP BY`, `COUNT` returns 0 while `SUM` can return `NULL`; keep this in mind for summary reports.

### 2.3 AVG(CASE ...): average over a subset

~~~sql
SELECT AVG(
           CASE
               WHEN status = 'PAID' THEN amount
           END
       ) AS average_paid_amount
FROM sales_orders;
~~~

Non-`PAID` rows return `NULL`; `AVG` ignores `NULL`, so it computes the average only over paid rows that have a non-`NULL` `AMOUNT`.

Do not arbitrarily write `ELSE 0`:

~~~sql
AVG(
    CASE
        WHEN status = 'PAID' THEN amount
        ELSE 0
    END
)
~~~

Here, non-`PAID` rows contribute 0 and **remain in AVG's denominator**. The result is no longer the average of PAID orders; it is the average across all rows in the group where non-PAID rows are treated as having a value of 0.

| Expression | Which values are averaged by AVG? | Meaning |
|---|---|---|
| `AVG(CASE WHEN status='PAID' THEN amount END)` | Only non-NULL amounts of PAID rows | Average value of PAID orders |
| `AVG(CASE WHEN status='PAID' THEN amount ELSE 0 END)` | PAID amounts and 0 for other rows | Average over all rows in the group treating non-PAID rows as 0 |

### 2.4 Conditional MIN and MAX

~~~sql
SELECT region_id,
       MIN(CASE WHEN status = 'PAID' THEN order_date END)
           AS first_paid_order,
       MAX(CASE WHEN status = 'PAID' THEN order_date END)
           AS latest_paid_order,
       MAX(CASE WHEN status = 'PAID' THEN amount END)
           AS largest_paid_order
FROM sales_orders
GROUP BY region_id;
~~~

`MIN` and `MAX` ignore `NULL`, so only PAID rows contribute dates/values. If a region has no PAID rows, the corresponding columns return `NULL`. This lets you retrieve the earliest/latest date or maximum value **within a subset** without a separate query.

### 2.5 COUNT(DISTINCT CASE ...): conditional distinct counting

Example counting distinct customers who have at least one paid order:

~~~sql
SELECT region_id,
       COUNT(
           DISTINCT CASE
               WHEN status = 'PAID' THEN customer_id
           END
       ) AS paid_customers
FROM sales_orders
GROUP BY region_id;
~~~

Non-PAID rows return `NULL`; `COUNT(DISTINCT ...)` ignores `NULL` and counts each non-`NULL` `CUSTOMER_ID` only once per group. If a customer has five PAID orders in the same region, that customer is still counted once.

If `CUSTOMER_ID` can be `NULL`, rows without a customer ID are not counted as distinct customers. That is usually desirable; if the business requires tracking unidentified customers, add a separate metric.

## 3. Preparing practice data

If you have a practice schema, you can create the following small table. Run only once in an authorized schema:

~~~sql
CREATE TABLE lab_sales_orders (
    order_id    NUMBER(10) PRIMARY KEY,
    customer_id NUMBER(10),
    order_date  DATE NOT NULL,
    region_id   VARCHAR2(10 CHAR),
    channel     VARCHAR2(10 CHAR),
    status      VARCHAR2(12 CHAR),
    amount      NUMBER(12,2)
);
~~~

Load sample data:

~~~sql
INSERT ALL
    INTO lab_sales_orders VALUES
        (1, 101, DATE '2026-01-05', 'NORTH', 'WEB',   'PAID',      1000)
    INTO lab_sales_orders VALUES
        (2, 102, DATE '2026-01-08', 'NORTH', 'STORE', 'PENDING',    500)
    INTO lab_sales_orders VALUES
        (3, 101, DATE '2026-01-12', 'NORTH', 'WEB',   'PAID',       700)
    INTO lab_sales_orders VALUES
        (4, 103, DATE '2026-01-15', 'SOUTH', 'STORE', 'CANCELLED',  300)
    INTO lab_sales_orders VALUES
        (5, 104, DATE '2026-02-02', 'SOUTH', 'WEB',   'PAID',      1200)
    INTO lab_sales_orders VALUES
        (6, 102, DATE '2026-02-10', 'NORTH', 'WEB',   'CANCELLED',  200)
    INTO lab_sales_orders VALUES
        (7, 105, DATE '2026-02-14', 'SOUTH', 'STORE', 'PENDING',    800)
    INTO lab_sales_orders VALUES
        (8, 106, DATE '2026-02-18', 'SOUTH', 'WEB',   'PAID',       600)
    INTO lab_sales_orders VALUES
        (9, 107, DATE '2026-02-20', 'NORTH', 'STORE', NULL,         400)
SELECT 1 FROM dual;

COMMIT;
~~~

The dataset has two regions, two channels, three statuses, and one row with `STATUS IS NULL` to test how conditions behave.

View the data:

~~~sql
SELECT order_id, customer_id, order_date,
       region_id, channel, status, amount
FROM lab_sales_orders
ORDER BY order_id;
~~~

## 4. Multiple conditional metrics in a single GROUP BY

A major advantage of conditional aggregation is generating multiple metrics in one grouping pass. Example:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       SUM(CASE WHEN status = 'PENDING' THEN amount ELSE 0 END)
           AS pending_amount,
       SUM(CASE WHEN status = 'CANCELLED' THEN amount ELSE 0 END)
           AS cancelled_amount,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_order_count,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END)
           AS pending_order_count,
       COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END)
           AS cancelled_order_count
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

Expected result:

| REGION_ID | TOTAL_ORDERS | PAID_REVENUE | PENDING_AMOUNT | CANCELLED_AMOUNT | PAID_ORDER_COUNT | PENDING_ORDER_COUNT | CANCELLED_ORDER_COUNT |
|---|---:|---:|---:|---:|---:|---:|---:|
| NORTH | 5 | 1700 | 500 | 200 | 2 | 1 | 1 |
| SOUTH | 4 | 1800 | 800 | 300 | 2 | 1 | 1 |

Each aggregate expression is an independent metric. Oracle groups rows by `REGION_ID`, then evaluates all expressions in the `SELECT` list for each group. The row with `STATUS IS NULL` is included in `TOTAL_ORDERS` but is not counted in any of the three specific statuses.

### 4.1 Computing count and total amount per status

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
           AS paid_count,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_amount,
       SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END)
           AS pending_count,
       SUM(CASE WHEN status = 'PENDING' THEN amount ELSE 0 END)
           AS pending_amount
FROM lab_sales_orders
GROUP BY region_id;
~~~

A common pair of metrics consists of:

- **Count:** add 1 for each qualifying row.
- **Amount:** sum the amount of each qualifying row.

There is no need to run separate queries and JOIN results by region if all metrics come from the same row set and grouping.

### 4.2 Splitting metrics by channel

~~~sql
SELECT region_id,
       SUM(CASE WHEN channel = 'WEB' THEN amount ELSE 0 END)
           AS web_revenue,
       SUM(CASE WHEN channel = 'STORE' THEN amount ELSE 0 END)
           AS store_revenue,
       COUNT(CASE WHEN channel = 'WEB' THEN 1 END)
           AS web_orders,
       COUNT(CASE WHEN channel = 'STORE' THEN 1 END)
           AS store_orders
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

This is a form of "manual pivoting": each condition becomes a result column. This approach is very flexible when the groups to display are known in advance.

## 5. Conditional aggregation with compound conditions

Conditions inside `CASE` can combine multiple columns with `AND`, `OR`, `IN`, range comparisons, and `NULL` checks.

### 5.1 Combining status and channel

Revenue of PAID orders via WEB:

~~~sql
SELECT region_id,
       SUM(
           CASE
               WHEN status = 'PAID'
                AND channel = 'WEB'
               THEN amount
               ELSE 0
           END
       ) AS paid_web_revenue
FROM lab_sales_orders
GROUP BY region_id;
~~~

Count of PAID or PENDING orders:

~~~sql
SELECT region_id,
       COUNT(
           CASE
               WHEN status IN ('PAID', 'PENDING') THEN 1
           END
       ) AS active_orders
FROM lab_sales_orders
GROUP BY region_id;
~~~

Conditions can get long; when they do, use line breaks and clear parentheses:

~~~sql
SUM(
    CASE
        WHEN status = 'PAID'
         AND channel IN ('WEB', 'STORE')
         AND order_date >= DATE '2026-01-01'
         AND order_date <  DATE '2026-02-01'
        THEN amount
        ELSE 0
    END
) AS paid_january_amount
~~~

### 5.2 Grouping conditions by date range

Example reporting January and February revenue on the same row per region:

~~~sql
SELECT region_id,
       SUM(
           CASE
               WHEN order_date >= DATE '2026-01-01'
                AND order_date <  DATE '2026-02-01'
                AND status = 'PAID'
               THEN amount
               ELSE 0
           END
       ) AS jan_paid_revenue,
       SUM(
           CASE
               WHEN order_date >= DATE '2026-02-01'
                AND order_date <  DATE '2026-03-01'
                AND status = 'PAID'
               THEN amount
               ELSE 0
           END
       ) AS feb_paid_revenue
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

Use the half-open interval `[start of month, start of next month)` to include every timestamp within the month if `ORDER_DATE` has a time component. For example, `ORDER_DATE < DATE '2026-02-01'` cleanly excludes everything from the start of February onward; there is no need to guess end-of-day as `23:59:59`.

### 5.3 One row can satisfy multiple conditions

Conditional aggregation allows **overlapping** conditions. Example:

~~~sql
SELECT region_id,
       SUM(CASE WHEN amount >= 1000 THEN amount ELSE 0 END)
           AS large_order_amount,
       SUM(CASE WHEN channel = 'WEB' THEN amount ELSE 0 END)
           AS web_order_amount
FROM lab_sales_orders
GROUP BY region_id;
~~~

A WEB order worth 1,200 contributes to both `LARGE_ORDER_AMOUNT` and `WEB_ORDER_AMOUNT`. That is valid when the two metrics describe different dimensions; however, you must not sum the two columns and call it total revenue, because that would **double-count**.

If you want mutually exclusive buckets, design the conditions so every row falls into exactly one bucket and verify that the buckets cover the entire dataset being reported.

## 6. CASE and NULL: details that determine the result

### 6.1 Without ELSE, CASE returns NULL

~~~sql
CASE
    WHEN status = 'PAID' THEN amount
END
~~~

If the condition is not true, Oracle returns `NULL` because there is no `ELSE`. This behavior is useful with aggregate functions:

- `SUM` ignores `NULL` values.
- `AVG` excludes `NULL` values from both the sum and the sample count.
- `COUNT(expression)` ignores `NULL`.
- `MIN` and `MAX` ignore `NULL`.

Example:

~~~sql
SELECT SUM(CASE WHEN status = 'PAID' THEN amount END)
           AS paid_sum,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_count,
       AVG(CASE WHEN status = 'PAID' THEN amount END)
           AS paid_average
FROM lab_sales_orders;
~~~

### 6.2 Distinguishing NULL status from other statuses

The condition:

~~~sql
CASE
    WHEN status <> 'PAID' THEN amount
    ELSE 0
END
~~~

does not treat `STATUS IS NULL` as a value "other than PAID" under two-valued logic. In SQL, comparing `NULL <> 'PAID'` evaluates to UNKNOWN; the `WHEN` branch is not taken, so `ELSE 0` is used.

If you want a bucket for "not PAID, including NULL":

~~~sql
CASE
    WHEN status = 'PAID' THEN 0
    ELSE amount
END
~~~

or write explicitly:

~~~sql
CASE
    WHEN status <> 'PAID' OR status IS NULL THEN amount
    ELSE 0
END
~~~

If you want to count only non-PAID statuses **excluding NULL**:

~~~sql
CASE
    WHEN status IS NOT NULL
     AND status <> 'PAID'
    THEN amount
    ELSE 0
END
~~~

Conditions should explicitly express how missing data is handled, especially when the report serves data quality control.

### 6.3 SUM with no matching rows can return NULL

Suppose there are no REFUNDED rows in the entire table:

~~~sql
SELECT SUM(CASE WHEN status = 'REFUNDED' THEN amount END)
           AS sum_without_match,
       SUM(CASE WHEN status = 'REFUNDED' THEN amount ELSE 0 END)
           AS sum_with_zero
FROM lab_sales_orders;
~~~

When the table has rows but none with status `REFUNDED`:

- `SUM_WITHOUT_MATCH` is `NULL` because every input expression evaluates to `NULL`.
- `SUM_WITH_ZERO` is 0 because every row contributes 0.

If you want to display 0 while preserving the original inner expression logic:

~~~sql
NVL(SUM(CASE WHEN status = 'REFUNDED' THEN amount END), 0)
~~~

`NVL` outside the aggregate function converts a `NULL` sum result into 0. This is useful when you need to separate **row selection rules** inside `CASE` from **total display rules** outside.

If the query has `GROUP BY`, a group with no source rows at all normally does not appear as a result row. `ELSE 0` does not synthesize a group that does not exist in the data.

### 6.4 COUNT(*) and COUNT(CASE...) differ

~~~sql
SELECT COUNT(*) AS all_rows,
       COUNT(status) AS rows_with_status,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_rows,
       COUNT(CASE WHEN status = 'PAID' THEN amount END)
           AS paid_rows_with_amount
FROM lab_sales_orders;
~~~

The counts differ when `STATUS IS NULL` or `AMOUNT IS NULL`:

- `COUNT(*)` counts every row.
- `COUNT(status)` counts rows with a non-`NULL` status.
- `COUNT(CASE WHEN ... THEN 1 END)` counts rows meeting the condition.
- `COUNT(CASE WHEN ... THEN amount END)` counts only rows meeting the condition **and** having a non-`NULL` amount.

This is why using `THEN 1` for counting rows is usually clearer than using a column that can be `NULL`.

## 7. Conditional distinct counting

When counting distinct paid customers by region:

~~~sql
SELECT region_id,
       COUNT(DISTINCT
           CASE
               WHEN status = 'PAID' THEN customer_id
           END
       ) AS distinct_paid_customers
FROM lab_sales_orders
GROUP BY region_id
ORDER BY region_id;
~~~

In the sample data:

- Region NORTH has customer 101 with two PAID orders, so the distinct customer count is 1.
- Region SOUTH has customers 104 and 106 with PAID orders, so the distinct customer count is 2.

If you need to count customers with WEB orders regardless of status:

~~~sql
COUNT(DISTINCT CASE WHEN channel = 'WEB' THEN customer_id END)
~~~

Do not use `COUNT(DISTINCT customer_id)` if the goal is to count only PAID customers; that expression counts customers across all statuses.

### 7.1 Conditional distinct counting across multiple dimensions

~~~sql
SELECT region_id,
       COUNT(DISTINCT CASE
           WHEN status = 'PAID' AND channel = 'WEB'
           THEN customer_id
       END) AS paid_web_customers,
       COUNT(DISTINCT CASE
           WHEN status = 'PAID' AND channel = 'STORE'
           THEN customer_id
       END) AS paid_store_customers
FROM lab_sales_orders
GROUP BY region_id;
~~~

A single customer can appear in both columns if they paid via both WEB and STORE. These two counts do not necessarily sum to the region's total distinct customers.

## 8. Combining conditional aggregation with GROUP BY and HAVING

`WHERE` filters **source rows before grouping**; `HAVING` filters **groups after aggregates are computed**. Conditions inside `CASE` only decide whether a row contributes to a particular metric; they do not exclude the row from all metrics.

### 8.1 Retaining only regions whose PAID revenue exceeds a threshold

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_orders
FROM lab_sales_orders
GROUP BY region_id
HAVING SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) > 1500;
~~~

`HAVING` uses an aggregate to decide which groups are returned. Do both regions in the sample data have a PAID total greater than 1,500? NORTH has 1,700 and SOUTH has 1,800, so both qualify.

### 8.2 Mistakenly putting the condition in WHERE

If you write:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM lab_sales_orders
WHERE status = 'PAID'
GROUP BY region_id;
~~~

then `COUNT(*)` counts only PAID orders because `WHERE` already eliminated PENDING, CANCELLED, and NULL rows before grouping. If the report wants total orders **across all statuses** alongside PAID revenue, remove the status filter from `WHERE` and keep it inside `CASE`.

An appropriate `WHERE` example:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders_in_period,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM lab_sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-03-01'
GROUP BY region_id;
~~~

Here `WHERE` filters the date range of interest for **all metrics**; `CASE` continues to isolate the PAID status.

### 8.3 Filtering groups by multiple aggregate conditions

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM lab_sales_orders
GROUP BY region_id
HAVING COUNT(*) >= 3
   AND COUNT(CASE WHEN status = 'PAID' THEN 1 END) >= 2;
~~~

A region must have at least 3 total orders and at least 2 PAID orders. You cannot reference aggregate aliases in `WHERE` because `WHERE` is processed before the grouping step; put group conditions in `HAVING`.

## 9. Conditional aggregation by month, quarter, and time periods

A report often needs multiple monthly columns:

~~~sql
SELECT region_id,
       SUM(CASE
           WHEN order_date >= DATE '2026-01-01'
            AND order_date <  DATE '2026-02-01'
            AND status = 'PAID'
           THEN amount ELSE 0 END) AS jan,
       SUM(CASE
           WHEN order_date >= DATE '2026-02-01'
            AND order_date <  DATE '2026-03-01'
            AND status = 'PAID'
           THEN amount ELSE 0 END) AS feb,
       SUM(CASE
           WHEN order_date >= DATE '2026-03-01'
            AND order_date <  DATE '2026-04-01'
            AND status = 'PAID'
           THEN amount ELSE 0 END) AS mar
FROM sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-04-01'
GROUP BY region_id;
~~~

This is a manual pivot for three known months. If you want one row per month instead of a column per month, use `GROUP BY TRUNC(order_date, 'MM')`:

~~~sql
SELECT region_id,
       TRUNC(order_date, 'MM') AS month_start,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END)
           AS paid_orders
FROM sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-04-01'
GROUP BY region_id, TRUNC(order_date, 'MM')
ORDER BY region_id, month_start;
~~~

Choosing the output shape:

- **Multiple month columns:** suited for dashboards with a fixed number of periods.
- **One row per month:** suited for charts, data exports, or reports with a variable number of periods.

Do not use date strings dependent on `NLS_DATE_FORMAT` in conditions; date literals or date-typed binds keep results consistent.

## 10. Conditional aggregation with analytic functions

Regular aggregates combined with `GROUP BY` collapse rows down to one row per group. Analytic functions using `OVER` can compute group-level metrics while retaining every detail row.

Example: display each order alongside its region's total PAID revenue:

~~~sql
SELECT order_id,
       region_id,
       status,
       amount,
       SUM(
           CASE WHEN status = 'PAID' THEN amount ELSE 0 END
       ) OVER (PARTITION BY region_id) AS region_paid_revenue
FROM sales_orders
ORDER BY region_id, order_id;
~~~

Each row still represents one order; `REGION_PAID_REVENUE` repeats the total PAID revenue for the corresponding region. This is not the same output shape as `GROUP BY region_id`.

You can compute each PAID order's share of its region's PAID total:

~~~sql
SELECT order_id,
       region_id,
       status,
       amount,
       CASE
           WHEN status = 'PAID' THEN
               amount / NULLIF(
                   SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
                       OVER (PARTITION BY region_id),
                   0
               )
       END AS paid_order_share
FROM sales_orders;
~~~

Non-PAID rows return `NULL` in the share column; a zero denominator is guarded with `NULLIF`. If you need a percentage, multiply the expression by 100 and round as required.

## 11. Conditional aggregation and JOINs: avoiding data multiplication

A serious bug often lies not in `CASE`, but in the row count after a JOIN. Suppose an order has multiple line items in `ORDER_ITEMS`. When joining `SALES_ORDERS` with `ORDER_ITEMS`, an order with three line items appears three times.

~~~sql
SELECT o.region_id,
       SUM(o.amount) AS order_revenue,
       SUM(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
           AS paid_revenue
FROM sales_orders o
JOIN order_items i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

If `O.AMOUNT` is the **order-level** total amount, every line item repeats it; `SUM(o.amount)` and `PAID_REVENUE` get multiplied by the number of item rows. Conditional aggregation does not automatically deduplicate rows multiplied by a JOIN.

### 11.1 Approach 1: aggregate the child table before joining

If you need the line-item count per order:

~~~sql
WITH item_counts AS (
    SELECT order_id,
           COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
)
SELECT o.region_id,
       SUM(o.amount) AS order_revenue,
       SUM(CASE WHEN o.status = 'PAID' THEN o.amount ELSE 0 END)
           AS paid_revenue,
       SUM(NVL(i.item_count, 0)) AS total_items
FROM sales_orders o
LEFT JOIN item_counts i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

The `ITEM_COUNTS` CTE produces one row per order before the JOIN, so order-level values are not repeated for each item.

### 11.2 Approach 2: aggregate item-level data at the right grain

If the goal is item revenue, sum `ITEM_AMOUNT` in the detail table and apply the order status from the header table:

~~~sql
SELECT o.region_id,
       SUM(CASE
               WHEN o.status = 'PAID' THEN i.item_amount
               ELSE 0
           END) AS paid_item_revenue
FROM sales_orders o
JOIN order_items i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

This calculation is at the **item grain**, not an order-level total. Confirm whether `ITEM_AMOUNT` includes or excludes taxes, discounts, and adjustments per requirements.

### 11.3 LEFT JOIN and COUNT(*)

With a parent table that may have no child rows:

~~~sql
SELECT o.region_id,
       COUNT(*) AS joined_rows,
       COUNT(i.item_id) AS actual_item_rows
FROM sales_orders o
LEFT JOIN order_items i
  ON i.order_id = o.order_id
GROUP BY o.region_id;
~~~

An order with no items still creates one NULL-extended row in the LEFT JOIN result. Therefore, `COUNT(*)` counts at least one row for that order; `COUNT(i.item_id)` counts only items with a non-NULL ID. When conditional aggregation needs to count orders, be explicit about whether you are counting **orders**, **items**, or **customers**, and avoid counting at the wrong grain.

## 12. Mutually exclusive conditions and completeness checks

A status report might define three buckets:

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid,
       SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
       SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END) AS cancelled,
       COUNT(*) AS total
FROM lab_sales_orders
GROUP BY region_id;
~~~

If there are only three valid statuses and no NULLs, you expect:

`PAID + PENDING + CANCELLED = TOTAL`.

However, the sample data contains one row with `STATUS IS NULL`, so in region NORTH:

`2 + 1 + 1 = 4`, whereas `TOTAL = 5`.

The discrepancy of 1 is the row missing a status. For transparent reporting, add a column:

~~~sql
SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END) AS missing_status
~~~

or track other statuses:

~~~sql
SUM(
    CASE
        WHEN status IS NULL THEN 1
        WHEN status NOT IN ('PAID', 'PENDING', 'CANCELLED') THEN 1
        ELSE 0
    END
) AS other_or_missing
~~~

When using `NOT IN` on a nullable column, remember that the condition can evaluate to UNKNOWN; to include NULL in the bucket, write `IS NULL` explicitly.

### 12.1 Conditions can overlap

If an order can belong to both "WEB orders" and "large orders," the sum of those metrics does not necessarily equal the total row count. Do not perform completeness checks by summing independent metrics unless the conditions are mutually exclusive.

To assign exactly one bucket per row, use a single `CASE` with branches ordered by priority:

~~~sql
CASE
    WHEN status = 'PAID' THEN 'PAID'
    WHEN status = 'PENDING' THEN 'PENDING'
    WHEN status = 'CANCELLED' THEN 'CANCELLED'
    ELSE 'OTHER_OR_MISSING'
END
~~~

You can then group by the bucket or write conditional aggregation using those same conditions. The order of `WHEN` branches matters when conditions overlap; Oracle picks the first matching branch.

## 13. Conditional aggregation vs. WHERE, subqueries, and PIVOT

### 13.1 When to use CASE inside aggregates?

Appropriate when:

- Multiple metrics are computed from the **same source dataset**.
- The metrics share the same grain and grouping dimensions.
- The conditions to project as columns are known ahead of time.
- Rows failing one condition must still be kept to compute other metrics.

Example:

~~~sql
SELECT region_id,
       COUNT(*) AS total_orders,
       COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_orders
FROM sales_orders
GROUP BY region_id;
~~~

### 13.2 When is WHERE more appropriate?

If the entire report cares only about PAID orders, filter beforehand:

~~~sql
SELECT region_id,
       COUNT(*) AS paid_orders,
       SUM(amount) AS paid_revenue
FROM sales_orders
WHERE status = 'PAID'
GROUP BY region_id;
~~~

This is more natural when metrics for other statuses are not needed. `WHERE` removes rows prior to grouping and can reduce the volume of rows to process. However, if you need `TOTAL_ORDERS` alongside `PAID_ORDERS` in the same result, putting status into `WHERE` would drop non-PAID rows.

### 13.3 When to use PIVOT?

Oracle provides the `PIVOT` operator for certain forms of turning values into columns. Conditional aggregation is often more flexible when:

- Different functions are needed per group.
- Each column has complex conditions.
- Counts, sums, averages, and distinct metrics must be combined.
- Explicit control over NULL/ELSE handling is desired.

Simple PIVOT example for total amounts by status:

~~~sql
SELECT *
FROM (
    SELECT region_id, status, amount
    FROM sales_orders
)
PIVOT (
    SUM(amount)
    FOR status IN (
        'PAID' AS paid,
        'PENDING' AS pending,
        'CANCELLED' AS cancelled
    )
);
~~~

`PIVOT` fits cleanly when pivoting naturally along a single category column. Conditional aggregation remains the direct choice when defining each metric individually. Neither technique is universally faster: inspect the execution plan and actual data.

## 14. Data types and CASE expressions in aggregates

The `THEN` and `ELSE` branches of `CASE` must have compatible data types so Oracle can determine the result type. Example:

~~~sql
SUM(
    CASE
        WHEN status = 'PAID' THEN amount
        ELSE 0
    END
)
~~~

`AMOUNT` is NUMBER and `0` is a numeric literal, so they are compatible.

Avoid mixing numbers with strings:

~~~sql
-- Unsuitable for numeric calculations:
CASE WHEN status = 'PAID' THEN amount ELSE '0' END
~~~

Oracle may be forced into implicit conversion or raise a data type error. For numeric aggregates, keep every branch numeric; for report formatting, convert to strings at the final step using `TO_CHAR`.

### 14.1 Comparison conditions and NULL

~~~sql
CASE
    WHEN amount >= 1000 THEN 'LARGE'
    WHEN amount >= 500 THEN 'MEDIUM'
    ELSE 'SMALL'
END
~~~

If `AMOUNT IS NULL`, none of the comparison conditions evaluate to TRUE, so the `ELSE` branch returns `SMALL`. If NULL needs to be identified separately:

~~~sql
CASE
    WHEN amount IS NULL THEN 'MISSING'
    WHEN amount >= 1000 THEN 'LARGE'
    WHEN amount >= 500 THEN 'MEDIUM'
    ELSE 'SMALL'
END
~~~

Branch order affects the result; place special cases before general fallback branches.

## 15. Performance and maintainability

Conditional aggregation lets you compute multiple metrics in a single grouping pass instead of sending multiple separate SQL statements. Still, **you cannot claim a conditional aggregation query is always faster than every alternative**. The optimizer also considers:

- Row counts and data distribution.
- Indexes, partition pruning, and `WHERE` predicates.
- Number of groups in `GROUP BY`.
- Number of `CASE` expressions and aggregate functions.
- Joins prior to grouping and row-multiplication risks.
- Statistics and execution plans.

### 15.1 Filter the source set with WHERE when all metrics share a condition

Example report covering only one quarter:

~~~sql
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue,
       COUNT(CASE WHEN status = 'PENDING' THEN 1 END)
           AS pending_orders
FROM sales_orders
WHERE order_date >= :period_start
  AND order_date <  :period_end
GROUP BY region_id;
~~~

Bind `:period_start` and `:period_end` using appropriate date/time types. Filtering the time window in `WHERE` removes out-of-period rows for all metrics; status remains inside `CASE` to split individual metrics.

### 15.2 Do not duplicate complex conditional logic arbitrarily

If multiple columns share the same complex condition, you can standardize it with a CTE:

~~~sql
WITH classified_orders AS (
    SELECT region_id,
           amount,
           status,
           CASE
               WHEN status = 'PAID' AND channel = 'WEB'
               THEN 1
               ELSE 0
           END AS is_paid_web
    FROM sales_orders
)
SELECT region_id,
       SUM(CASE WHEN is_paid_web = 1 THEN amount ELSE 0 END)
           AS paid_web_revenue,
       SUM(is_paid_web) AS paid_web_orders
FROM classified_orders
GROUP BY region_id;
~~~

A CTE centralizes classification logic for readability and reuse within the query. Do not assume a CTE is a physical temporary table or always materialized by Oracle; the optimizer may transform execution.

### 15.3 Inspect the plan instead of guessing

Once you have a real query, inspect the execution plan using authorized tools, for instance:

~~~sql
EXPLAIN PLAN FOR
SELECT region_id,
       SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
           AS paid_revenue
FROM sales_orders
WHERE order_date >= DATE '2026-01-01'
  AND order_date <  DATE '2026-02-01'
GROUP BY region_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` shows the estimated plan under the current environment and statistics; it does not always reflect actual runtime behavior for a given execution with bind values. For critical workloads, use approved monitoring tools and actual runtime execution plans per DBA policies.

## 16. Common errors when using conditional aggregation

| Symptom | Cause | Resolution |
|---|---|---|
| `COUNT(CASE WHEN cond THEN 1 ELSE 0 END)` counts every row | 0 is non-NULL, so COUNT still counts it | Omit ELSE or use SUM with 1/0 |
| Unexpectedly low AVG | Using `ELSE 0` keeps non-matching rows in the denominator | Omit ELSE when averaging only the subset |
| Conditional sum returns NULL | No rows contribute a non-NULL value | Choose `ELSE 0` or `NVL(SUM(...),0)` based on meaning |
| Missing group in output | No source rows exist to form the group | Use a dimension/calendar table if empty groups must appear |
| Rows with NULL status missing from "other" group | Comparing `<>` against NULL gives UNKNOWN | Add `OR status IS NULL` or a dedicated branch |
| Revenue sum is multiplied after JOIN | One header row repeats across multiple detail lines | Pre-aggregate details or compute at the proper grain |
| Sum of buckets does not equal total rows | Overlapping conditions or unhandled NULL/other statuses | Review bucket definitions and add a missing/other bucket |
| Ratio raises division-by-zero error | Aggregate denominator equals 0 | Protect with `NULLIF` |
| Average of ratios differs from ratio of sums | Different definitions and weighting | Choose AVG of ratios or SUM/SUM per goal |
| Monthly report misses end-of-day rows | Using `<=` last day at midnight | Use half-open range from month start to next month start |
| CASE raises data type error | Branches return incompatible types | Keep numeric branches as NUMBER, text branches as text |
| Conditional aggregation is slow | Too many rows, JOIN fan-out, large groups, or missing filters | Check plan, grain, indexes/partitions, and statistics |

## 17. Self-check practice exercises

The exercises below use the `LAB_SALES_ORDERS` table from section 3. If you have not created it, substitute an actual reporting table with equivalent columns.

### Exercise 1 — Totals by status

Write a single SQL query by `REGION_ID` returning:

- Total number of orders.
- Total PAID amount.
- Total PENDING amount.
- Total CANCELLED amount.

Do not filter status in `WHERE`. Verify why NORTH's total order count includes the `STATUS IS NULL` row.

### Exercise 2 — Conditional counting

Write three expressions:

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
~~~

~~~sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
~~~

~~~sql
COUNT(CASE WHEN status = 'PAID' THEN amount END)
~~~

Explain how the third expression can differ from the first two when `AMOUNT` contains NULL.

### Exercise 3 — AVG and ELSE 0

Compare:

~~~sql
AVG(CASE WHEN status = 'PAID' THEN amount END)
~~~

with:

~~~sql
AVG(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
~~~

Calculate both by hand for the NORTH region and explain the denominator of each AVG.

### Exercise 4 — Counting distinct customers

By region, count customers with PAID orders:

~~~sql
COUNT(DISTINCT CASE WHEN status = 'PAID' THEN customer_id END)
~~~

Then write another column counting customers with WEB orders regardless of status. Can one customer be counted in both columns? Why?

### Exercise 5 — Monthly report

Produce one row per region with two columns `JAN_PAID` and `FEB_PAID`. Use half-open ranges with date literals. Explain why an `ORDER_DATE` with a time component is still filtered accurately.

### Exercise 6 — Missing status bucket

Add a column counting `STATUS IS NULL` and verify:

`PAID + PENDING + CANCELLED + MISSING_STATUS = TOTAL`

for the sample data. If a new status `REFUNDED` appears, what addition is needed to preserve completeness checks?

### Exercise 7 — HAVING

Display only regions with at least two PAID orders and PAID revenue over 1,500. Write the conditions in `HAVING`. Why aren't aggregates placed in `WHERE`?

### Exercise 8 — Safe ratios

Compute the ratio of PAID amount to total amount for each region. Use:

~~~sql
SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
/
NULLIF(SUM(amount), 0)
~~~

Explain when the result is NULL and why you should not blindly replace a 0 denominator with 1.

### Exercise 9 — Detecting JOIN fan-out

Suppose each order has multiple items. Write a query joining header/detail and explain why `SUM(header.amount)` can be multiplied. Rewrite it using a CTE that aggregates items before joining.

### Exercise 10 — Retaining detail rows with analytics

Write a query that still displays each `ORDER_ID` while adding total PAID revenue by `REGION_ID` using:

~~~sql
SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
OVER (PARTITION BY region_id)
~~~

Explain the difference between the analytic result and a `GROUP BY` result.

## 18. Summary checklist for conditional aggregation

| Need | SQL pattern to remember |
|---|---|
| Conditional sum of values | `SUM(CASE WHEN cond THEN amount ELSE 0 END)` |
| Subset sum preserving NULL semantics | `SUM(CASE WHEN cond THEN amount END)` |
| Conditional row count | `COUNT(CASE WHEN cond THEN 1 END)` |
| Counting via sum of 1/0 | `SUM(CASE WHEN cond THEN 1 ELSE 0 END)` |
| Subset average | `AVG(CASE WHEN cond THEN amount END)` |
| Subset maximum/minimum | `MAX/MIN(CASE WHEN cond THEN value END)` |
| Conditional distinct customer count | `COUNT(DISTINCT CASE WHEN cond THEN customer_id END)` |
| Safe ratio | `numerator / NULLIF(denominator, 0)` |
| Filtering groups after aggregation | `HAVING SUM(CASE WHEN ... END) ...` |
| Keeping detail rows alongside group totals | Aggregate with `OVER (PARTITION BY ...)` |

When writing conditional aggregation, clarify the **grain of the data**, the definition of each condition, NULL handling, and the meaning of 0 before choosing `ELSE`. Use `COUNT(CASE ... THEN 1 END)` to count rows, `AVG(CASE ... END)` to average subsets, and `NULLIF` to guard denominators. Finally, verify row counts after JOINs to avoid multiplying totals. Clarifying these points enables a single SQL query to produce multiple consistent, explainable metrics.
