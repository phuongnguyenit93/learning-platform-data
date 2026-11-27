# LAG, LEAD, and Comparing with Preceding or Following Rows in Oracle Database

In reporting and data analysis, many requirements need not only the value of the current row, but also a comparison against **the preceding or following row according to a defined order**. For example:

- Did this month's revenue increase or decrease compared to last month?
- How much did an account balance change compared to the previous transaction?
- Is a status different from the immediately preceding status of the same order?
- How much time elapsed between two consecutive events?
- What is the value for the next period?
- Is the current row the first or last record for each customer?

Oracle Database provides two analytic functions, **LAG** and **LEAD**, to perform these comparisons without self-joining a table to itself:

- **LAG** retrieves a value from a row that precedes the current row according to the order in the analytic window.
- **LEAD** retrieves a value from a row that follows the current row according to that order.

These two functions belong to the analytic functions group. They keep the input rows intact and attach reference values from adjacent rows. To use them accurately, you need to understand PARTITION BY, ORDER BY, offset, default, NULL handling, and row order determinism.

## 1. Concept: Looking at the Preceding or Following Row

Suppose we have a monthly revenue table:

| MONTH_START | REVENUE |
|---|---:|
| 2026-01-01 | 100 |
| 2026-02-01 | 120 |
| 2026-03-01 | 90 |
| 2026-04-01 | 150 |

We want to add columns for previous month revenue and next month revenue:

| MONTH_START | REVENUE | PREVIOUS_REVENUE | NEXT_REVENUE |
|---|---:|---:|---:|
| 2026-01-01 | 100 | NULL | 120 |
| 2026-02-01 | 120 | 100 | 90 |
| 2026-03-01 | 90 | 120 | 150 |
| 2026-04-01 | 150 | 90 | NULL |

LAG produces PREVIOUS_REVENUE; LEAD produces NEXT_REVENUE. The first row has no preceding row and the last row has no following row, so by default the result is NULL.

~~~sql
SELECT month_start,
       revenue,
       LAG(revenue) OVER (
           ORDER BY month_start
       ) AS previous_revenue,
       LEAD(revenue) OVER (
           ORDER BY month_start
       ) AS next_revenue
FROM monthly_revenue
ORDER BY month_start;
~~~

Key point to remember: LAG and LEAD do not compare by physical storage order in the table. Order is determined by ORDER BY inside OVER.

## 2. LAG and LEAD Syntax

### 2.1 Oracle Syntax

~~~sql
LAG(value_expr [, offset [, default]])
    [ { RESPECT | IGNORE } NULLS ]
    OVER (
        [PARTITION BY expr [, expr] ...]
        ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
    )
~~~

LEAD has the same structure:

~~~sql
LEAD(value_expr [, offset [, default]])
    [ { RESPECT | IGNORE } NULLS ]
    OVER (
        [PARTITION BY expr [, expr] ...]
        ORDER BY expr [ASC | DESC] [NULLS FIRST | NULLS LAST]
             [, expr ...]
    )
~~~

Argument meanings:

| Component | Meaning |
|---|---|
| value_expr | Expression to retrieve from another row, e.g., AMOUNT, STATUS, or EVENT_TIME |
| offset | Number of row positions to step back (LAG) or forward (LEAD); defaults to 1 |
| default | Value returned if there is no row at the offset position; defaults to NULL |
| RESPECT NULLS | Treat NULL as a row's value; this is the default |
| IGNORE NULLS | Skip NULL values of value_expr when locating the target row |
| PARTITION BY | Divides data into independent groups; the function resets within each group |
| ORDER BY | Defines the row ordering used to find preceding/following rows |

LAG/LEAD require ORDER BY in the analytic clause. There is no meaningful concept of a "preceding row" unless an ordering is defined.

### 2.2 LAG Defaults to the Immediately Preceding Row

~~~sql
LAG(revenue) OVER (ORDER BY month_start)
~~~

is equivalent to:

~~~sql
LAG(revenue, 1, NULL) OVER (ORDER BY month_start)
~~~

The default offset is 1 and the default fallback value is NULL.

### 2.3 LEAD Defaults to the Immediately Following Row

~~~sql
LEAD(revenue) OVER (ORDER BY month_start)
~~~

is equivalent to:

~~~sql
LEAD(revenue, 1, NULL) OVER (ORDER BY month_start)
~~~

### 2.4 Looking Two Rows Away

~~~sql
SELECT event_id,
       event_time,
       LAG(amount, 2) OVER (
           ORDER BY event_time, event_id
       ) AS amount_two_rows_before,
       LEAD(amount, 2) OVER (
           ORDER BY event_time, event_id
       ) AS amount_two_rows_after
FROM account_events;
~~~

An offset of 2 means two row positions in the ordering, not two days or two months. If a day is missing from the data, LAG(..., 1) still retrieves the immediately preceding existing row rather than searching for an adjacent calendar day.

### 2.5 Default Is Only Used When No Row Exists at the Target Position

~~~sql
SELECT month_start,
       revenue,
       LAG(revenue, 1, 0) OVER (
           ORDER BY month_start
       ) AS previous_revenue
FROM monthly_revenue;
~~~

On the first row, there is no preceding row, so the default 0 is returned. However, if a preceding row exists and its REVENUE is NULL, under the default RESPECT NULLS the result is still NULL. Default does not replace a NULL value that already exists in the referenced row.

If you want to replace both "no preceding row" and "referenced value is NULL" with 0, you can use:

~~~sql
NVL(
    LAG(revenue) OVER (ORDER BY month_start),
    0
) AS previous_revenue_or_zero
~~~

Only replace NULL with 0 if business rules treat those two cases as equivalent. If you need to distinguish "no preceding row" from "preceding row exists but measure is unrecorded", keep NULL and add metadata such as ROW_NUMBER or a separate flag.

## 3. ORDER BY Determines What Preceding/Following Means

### 3.1 The Order Must Reflect Business Logic

For example:

~~~sql
LAG(amount) OVER (ORDER BY event_time)
~~~

means taking the value of the row whose EVENT_TIME comes immediately before in ascending order. If you want to compare transactions chronologically, EVENT_TIME is a sensible sort key.

If you use:

~~~sql
LAG(amount) OVER (ORDER BY amount)
~~~

then the preceding row is the row with the next lower numeric AMOUNT, not necessarily the transaction that happened earlier. The SQL statement may be valid, but its business meaning is different.

### 3.2 Adding a Tie-Breaker for Deterministic Ordering

Suppose two transactions share the same EVENT_TIME:

| EVENT_ID | EVENT_TIME | AMOUNT |
|---:|---|---:|
| 101 | 2026-11-14 10:00:00 | 50 |
| 102 | 2026-11-14 10:00:00 | 70 |

If you write only:

~~~sql
LAG(amount) OVER (ORDER BY event_time)
~~~

Oracle has no basis to guarantee the order between the two rows at the same timestamp. Which row is treated as preceding can be unstable across executions or different plans.

Add a distinguishing key:

~~~sql
LAG(amount) OVER (
    ORDER BY event_time, event_id
)
~~~

If EVENT_ID is unique, the pair EVENT_TIME, EVENT_ID establishes a deterministic order. This rule is especially important for transaction reconciliation, change detection, and sequential event processing.

### 3.3 ORDER BY Inside OVER Differs from the Query's Final ORDER BY

~~~sql
SELECT event_id,
       event_time,
       LAG(amount) OVER (
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events
ORDER BY event_id DESC;
~~~

The two ORDER BY clauses serve two purposes:

- ORDER BY inside OVER determines which row LAG/LEAD references.
- ORDER BY at the end of the query sorts how rows are returned to the client.

Changing the outer display order does not change the `previous_amount` value computed by `event_time` and `event_id`.

### 3.4 ASC, DESC, and NULLS FIRST/LAST

With ascending ORDER BY, Oracle defaults to NULLS LAST; with descending, it defaults to NULLS FIRST. If the sort column can be NULL, explicitly decide where NULLs go:

~~~sql
LAG(status) OVER (
    PARTITION BY customer_id
    ORDER BY changed_at ASC NULLS LAST, history_id
)
~~~

In event data, it is best to have a non-NULL timestamp if timestamp is the primary timeline. If NULL means undetermined, putting NULL first or last affects which row is considered preceding or following.

## 4. PARTITION BY: Restarting Within Each Group

If a table holds multiple customers, we usually want the preceding transaction of the **same customer**, not the preceding transaction across the entire table.

~~~sql
SELECT customer_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events
ORDER BY customer_id, event_time, event_id;
~~~

PARTITION BY splits data into independent groups:

~~~text
CUSTOMER 10:  row 1 -> row 2 -> row 3
              LAG      LAG

CUSTOMER 20:  row 1 -> row 2
              LAG

CUSTOMER 30:  row 1
~~~

On the first row of each customer, LAG finds no preceding row in the partition and returns NULL (or default). It does not pull the last row of the previous customer.

### 4.1 Multiple Columns in PARTITION BY

~~~sql
LAG(balance) OVER (
    PARTITION BY account_id, currency_code
    ORDER BY transaction_time, transaction_id
)
~~~

This example compares balances within the same account and same currency. If CURRENCY_CODE is omitted, a USD row could be compared against an EUR row of the same account, producing a business-logic error.

### 4.2 Without PARTITION BY

~~~sql
LAG(amount) OVER (
    ORDER BY event_time, event_id
)
~~~

When PARTITION BY is omitted, the entire row set after FROM/WHERE/GROUP BY/HAVING belongs to one partition. The first row of the entire set has no preceding value.

### 4.3 PARTITION BY Does Not Sort the Final Output

PARTITION BY defines independent groups for the analytic function. It does not guarantee results are returned in partition order. If you need output ordered by customer then time, add an outer ORDER BY:

~~~sql
ORDER BY customer_id, event_time, event_id
~~~

## 5. Comparing LAG and LEAD

| Criterion | LAG | LEAD |
|---|---|---|
| Reference direction | Toward preceding rows | Toward following rows |
| Default offset | 1 | 1 |
| Default when no row exists | NULL | NULL |
| PARTITION BY | Supported | Supported |
| ORDER BY | Defines ordering | Defines ordering |
| NULL handling | RESPECT/IGNORE NULLS | RESPECT/IGNORE NULLS |
| Example | Prior period revenue | Next period revenue |

Both functions share the same declaration structure; they differ in the direction of lookup. With ascending ORDER BY on time:

- LAG retrieves the earlier-time event.
- LEAD retrieves the later-time event.

With ORDER BY DESC, the meaning of "preceding/following" in analytic order is reversed relative to ascending time. Check the sort direction before naming aliases like PREVIOUS_EVENT or NEXT_EVENT.

## 6. Comparing the Current Value with the Preceding Row

### 6.1 Calculating Absolute Difference

~~~sql
SELECT customer_id,
       event_time,
       amount,
       amount - LAG(amount) OVER (
           PARTITION BY customer_id
           ORDER BY event_time, event_id
       ) AS change_from_previous
FROM account_events
ORDER BY customer_id, event_time, event_id;
~~~

If the current amount is 150 and the previous row is 120, the difference is 30. On the first row of a partition or when the previous value is NULL, the subtraction result is NULL.

### 6.2 Calculating Percentage Change

~~~sql
WITH compared AS (
    SELECT customer_id,
           event_time,
           event_id,
           amount,
           LAG(amount) OVER (
               PARTITION BY customer_id
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM account_events
)
SELECT customer_id,
       event_time,
       amount,
       previous_amount,
       amount - previous_amount AS amount_change,
       CASE
         WHEN previous_amount IS NULL OR previous_amount = 0
           THEN NULL
         ELSE ROUND(
             (amount - previous_amount) / previous_amount * 100,
             2
         )
       END AS percent_change
FROM compared
ORDER BY customer_id, event_time, event_id;
~~~

Formula:

\[
\text{Percent change} =
\frac{\text{Current} - \text{Previous}}{\text{Previous}}\times 100
\]

If the previous value is 0, percentage change is undefined under this formula; the example returns NULL. If business rules require displaying "newly occurring", "no comparison baseline", or another convention, use CASE to express it explicitly.

This example assumes AMOUNT is NOT NULL. If AMOUNT can be NULL, distinguish among:

- No preceding row.
- Preceding row exists, but amount is NULL.
- Preceding row exists with amount equal to 0.

Do not collapse those cases into a single default percentage if their meanings differ.

### 6.3 Classifying Increase, Decrease, or Unchanged

~~~sql
WITH compared AS (
    SELECT product_id,
           sale_date,
           sale_id,
           quantity,
           LAG(quantity) OVER (
               PARTITION BY product_id
               ORDER BY sale_date, sale_id
           ) AS previous_quantity
    FROM product_sales
)
SELECT product_id,
       sale_date,
       quantity,
       previous_quantity,
       CASE
         WHEN previous_quantity IS NULL THEN 'NO PRIOR VALUE'
         WHEN quantity > previous_quantity THEN 'INCREASED'
         WHEN quantity < previous_quantity THEN 'DECREASED'
         ELSE 'UNCHANGED'
       END AS trend
FROM compared
ORDER BY product_id, sale_date, sale_id;
~~~

In this example, NULL is used as a marker for having no prior value. If quantity in the table can be NULL, the first condition is insufficient to identify the first row. You can add ROW_NUMBER to distinguish the first row from a preceding row whose quantity is NULL.

### 6.4 Using ROW_NUMBER to Identify the First Row Reliably

~~~sql
WITH compared AS (
    SELECT product_id,
           sale_date,
           sale_id,
           quantity,
           ROW_NUMBER() OVER (
               PARTITION BY product_id
               ORDER BY sale_date, sale_id
           ) AS row_num,
           LAG(quantity) OVER (
               PARTITION BY product_id
               ORDER BY sale_date, sale_id
           ) AS previous_quantity
    FROM product_sales
)
SELECT product_id,
       sale_date,
       quantity,
       previous_quantity,
       CASE
         WHEN row_num = 1 THEN 'FIRST ROW'
         WHEN previous_quantity IS NULL THEN 'PREVIOUS VALUE IS NULL'
         WHEN quantity = previous_quantity
              OR (quantity IS NULL AND previous_quantity IS NULL)
           THEN 'UNCHANGED'
         ELSE 'CHANGED'
       END AS change_status
FROM compared
ORDER BY product_id, sale_date, sale_id;
~~~

ROW_NUMBER identifies the row's position within the partition. It will not confuse "no preceding row" with "preceding row has NULL value".

## 7. Using LEAD to Look Ahead at the Next Row

### 7.1 Comparing with the Next Period

~~~sql
SELECT region,
       month_start,
       revenue,
       LEAD(revenue) OVER (
           PARTITION BY region
           ORDER BY month_start
       ) AS next_month_revenue
FROM monthly_revenue
ORDER BY region, month_start;
~~~

This example lets you view current revenue alongside the following month, supporting planning and trend analysis.

### 7.2 Calculating Time Until the Next Event

With a DATE column EVENT_TIME:

~~~sql
SELECT account_id,
       event_id,
       event_time,
       LEAD(event_time) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS next_event_time,
       LEAD(event_time) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) - event_time AS days_until_next_event
FROM account_events
ORDER BY account_id, event_time, event_id;
~~~

Subtracting DATE from DATE in Oracle returns a NUMBER representing the number of days, potentially with fractional parts. If the column is TIMESTAMP, subtraction returns INTERVAL DAY TO SECOND; the result type differs, so formatting and unit conversion differ as well.

### 7.3 Finding Large Gaps Between Two Events

~~~sql
WITH event_gaps AS (
    SELECT account_id,
           event_id,
           event_time,
           LEAD(event_time) OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS next_event_time
    FROM account_events
)
SELECT account_id,
       event_id,
       event_time,
       next_event_time,
       next_event_time - event_time AS gap_in_days
FROM event_gaps
WHERE next_event_time - event_time > 7
ORDER BY account_id, event_time, event_id;
~~~

This example finds events with a gap greater than 7 days until the next event. The last row of each partition has no next_event_time, so the WHERE comparison evaluates to UNKNOWN and is not returned.

If exact calculations by hour, minute, or time zone are required, choose an appropriate datetime data type and clearly define the gap unit.

## 8. Offset and Default in Practical Scenarios

### 8.1 Getting the Value Two Rows Back

~~~sql
SELECT product_id,
       sale_date,
       quantity,
       LAG(quantity, 2) OVER (
           PARTITION BY product_id
           ORDER BY sale_date, sale_id
       ) AS quantity_two_sales_ago
FROM product_sales;
~~~

This is the value from the second preceding transaction in the sorted sequence, not necessarily the value from exactly two days ago.

### 8.2 Getting the Value Three Rows Ahead

~~~sql
SELECT event_id,
       LEAD(status, 3, 'NO LATER STATUS') OVER (
           PARTITION BY order_id
           ORDER BY changed_at, history_id
       ) AS status_three_changes_later
FROM order_status_history;
~~~

Default is used when no third following row exists in the partition. The default value must be type-compatible with value_expr. In the example, STATUS is a string, so default is also a string.

### 8.3 Default Does Not Replace NULL in the Referenced Row

~~~sql
SELECT event_id,
       status,
       LAG(status, 1, 'NO PREVIOUS ROW') OVER (
           PARTITION BY order_id
           ORDER BY changed_at, history_id
       ) AS previous_status
FROM order_status_history;
~~~

If the preceding row exists but its STATUS is NULL, PREVIOUS_STATUS remains NULL under RESPECT NULLS. The string 'NO PREVIOUS ROW' only appears when there is no preceding row.

### 8.4 Default and NVL Solve Different Cases

| Expression | When no preceding row exists | When preceding row has NULL value |
|---|---|---|
| LAG(x) | NULL | NULL |
| LAG(x, 1, 0) | 0 | NULL |
| NVL(LAG(x), 0) | 0 | 0 |
| LAG(x) IGNORE NULLS | Finds an earlier row with non-NULL x; if none, NULL | Skips rows where x is NULL |

Choose the expression based on the required semantics, not merely to avoid NULLs on screen.

## 9. RESPECT NULLS and IGNORE NULLS

By default, Oracle uses RESPECT NULLS. In that mode, NULL is treated as a row value and counts toward the offset.

### 9.1 RESPECT NULLS

~~~sql
SELECT event_id,
       reading,
       LAG(reading) RESPECT NULLS OVER (
           ORDER BY event_id
       ) AS previous_reading
FROM sensor_readings;
~~~

If the immediately preceding row has READING NULL, `previous_reading` is NULL. That NULL row still occupies a position in the ordering.

You can omit the RESPECT NULLS keyword because it is the default:

~~~sql
LAG(reading) OVER (ORDER BY event_id)
~~~

### 9.2 IGNORE NULLS

~~~sql
SELECT event_id,
       reading,
       LAG(reading) IGNORE NULLS OVER (
           ORDER BY event_id
       ) AS previous_known_reading
FROM sensor_readings;
~~~

IGNORE NULLS skips NULL values of value_expr when looking up the offset value. If the immediately preceding row has READING NULL, Oracle keeps searching backward to retrieve the most recent non-NULL READING value.

Example:

| EVENT_ID | READING | LAG RESPECT NULLS | LAG IGNORE NULLS |
|---:|---:|---:|---:|
| 1 | 10 | NULL | NULL |
| 2 | NULL | 10 | 10 |
| 3 | 15 | NULL | 10 |
| 4 | NULL | 15 | 15 |
| 5 | 20 | NULL | 15 |

At EVENT_ID 3, the preceding row is EVENT_ID 2 with READING NULL. RESPECT returns NULL; IGNORE searches backward to EVENT_ID 1 and returns 10.

### 9.3 IGNORE NULLS Does Not Remove Rows from the Result

IGNORE NULLS only changes how LAG/LEAD locates value_expr. Rows with NULL readings still appear in the result set unless the outer query filters them out. It is not equivalent to WHERE reading IS NOT NULL.

### 9.4 LEAD IGNORE NULLS

~~~sql
SELECT event_id,
       reading,
       LEAD(reading) IGNORE NULLS OVER (
           ORDER BY event_id
       ) AS next_known_reading
FROM sensor_readings;
~~~

Oracle skips trailing NULL reading values to find the next non-NULL value.

### 9.5 When to Use IGNORE NULLS?

Use it when:

- A status stream only records a value when a change occurs, and intermediate NULL rows should be skipped.
- Measurement data has entries without values, yet you still want to compare against the last known measurement.
- A report needs the most recently observed non-NULL value.

Do not use it if NULL carries business meaning that must be preserved, such as "value cleared", "not applicable", or "undetermined", where the occurrence of NULL itself is an event to analyze.

## 10. LAG/LEAD After Aggregation

LAG and LEAD can be applied to results already grouped by GROUP BY. This is a common pattern for monthly/quarterly reports:

~~~sql
WITH monthly AS (
    SELECT region,
           TRUNC(sale_date, 'MM') AS month_start,
           SUM(amount) AS monthly_revenue
    FROM sales
    GROUP BY region, TRUNC(sale_date, 'MM')
)
SELECT region,
       month_start,
       monthly_revenue,
       LAG(monthly_revenue) OVER (
           PARTITION BY region
           ORDER BY month_start
       ) AS previous_month_revenue,
       monthly_revenue
         - LAG(monthly_revenue) OVER (
             PARTITION BY region
             ORDER BY month_start
           ) AS change_from_previous_month
FROM monthly
ORDER BY region, month_start;
~~~

Logical flow:

1. GROUP BY calculates revenue per REGION and month.
2. The `monthly` CTE produces one row for each region/month with data.
3. LAG compares each monthly total against the previous month's total within the same REGION.

If a region has no transactions in February, the CTE may have no row for February. LAG for March will retrieve the preceding row that has data, which may be January. It does not generate empty months and does not assume the previous row is the adjacent calendar month.

If a report needs every calendar month including months with zero revenue, build a calendar/month dimension and LEFT JOIN aggregated data onto it before applying LAG. Then you can use NVL to represent months with no activity as 0 if confirmed by business rules.

## 11. LAG/LEAD and Filtering Results

Oracle does not allow analytic functions directly in the WHERE clause of the same query block, because analytic functions are evaluated after WHERE, GROUP BY, and HAVING.

Invalid:

~~~sql
SELECT event_id,
       event_time,
       amount,
       LAG(amount) OVER (
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events
WHERE amount > LAG(amount) OVER (
    ORDER BY event_time, event_id
);
~~~

The correct approach is to compute the analytic value inside an inline view or CTE and filter in the outer query block:

~~~sql
WITH compared AS (
    SELECT event_id,
           event_time,
           amount,
           LAG(amount) OVER (
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM account_events
)
SELECT event_id,
       event_time,
       amount,
       previous_amount
FROM compared
WHERE amount > previous_amount
ORDER BY event_time, event_id;
~~~

This example retrieves rows where amount is greater than the previous row. The first row has no previous_amount, so the comparison evaluates to UNKNOWN and is excluded.

### 11.1 Filtering for the First Row

~~~sql
WITH numbered AS (
    SELECT customer_id,
           event_id,
           event_time,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY event_time, event_id
           ) AS rn
    FROM account_events
)
SELECT *
FROM numbered
WHERE rn = 1;
~~~

ROW_NUMBER selects the first row of each partition. It can be combined with LAG for analysis so you do not have to infer the first row from a potentially NULL value.

### 11.2 Filtering Rows Where Status Changed

~~~sql
WITH history AS (
    SELECT order_id,
           history_id,
           changed_at,
           status,
           LAG(status) OVER (
               PARTITION BY order_id
               ORDER BY changed_at, history_id
           ) AS previous_status,
           ROW_NUMBER() OVER (
               PARTITION BY order_id
               ORDER BY changed_at, history_id
           ) AS rn
    FROM order_status_history
)
SELECT order_id,
       history_id,
       changed_at,
       previous_status,
       status
FROM history
WHERE rn > 1
  AND (
       status <> previous_status
       OR (status IS NULL AND previous_status IS NOT NULL)
       OR (status IS NOT NULL AND previous_status IS NULL)
  )
ORDER BY order_id, changed_at, history_id;
~~~

This condition keeps rows whose status differs from the previous row, including when one side is NULL. If both are NULL, it is not treated as a change. ROW_NUMBER is needed to exclude the first row because it has no previous status.

## 12. LAG/LEAD vs. Self Join and Scalar Subquery

Before analytic functions, finding the previous row could be done with a self join, for instance using ROW_NUMBER:

~~~sql
WITH numbered AS (
    SELECT account_id,
           event_id,
           event_time,
           amount,
           ROW_NUMBER() OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS rn
    FROM account_events
)
SELECT current_row.account_id,
       current_row.event_id,
       current_row.amount,
       previous_row.amount AS previous_amount
FROM numbered current_row
LEFT JOIN numbered previous_row
  ON previous_row.account_id = current_row.account_id
 AND previous_row.rn = current_row.rn - 1;
~~~

This works, but is more verbose than LAG:

~~~sql
SELECT account_id,
       event_id,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events;
~~~

| Criterion | LAG/LEAD | Self join |
|---|---|---|
| Getting preceding/following row by order | Direct syntax | Requires creating an ordering key or relational condition |
| Keeping all current rows | Yes | Requires outer join to preserve unmatched rows |
| Multiple offsets | Can call LAG/LEAD with different offsets | May require additional joins |
| Comparing by non-sequential relationship | Not primary purpose | More flexible |
| Retrieving many columns from preceding row | Can call LAG for each column | A single join can be more convenient |

LAG/LEAD fits best when preceding/following is defined by an ordering. A self join fits better when the relationship between two rows is defined by keys or complex rules rather than simple adjacent position.

## 13. Practical Use Cases

### 13.1 Comparing Account Balances

~~~sql
SELECT account_id,
       transaction_id,
       transaction_time,
       balance_after,
       LAG(balance_after) OVER (
           PARTITION BY account_id
           ORDER BY transaction_time, transaction_id
       ) AS previous_balance,
       balance_after
         - LAG(balance_after) OVER (
             PARTITION BY account_id
             ORDER BY transaction_time, transaction_id
           ) AS balance_change
FROM account_transactions
ORDER BY account_id, transaction_time, transaction_id;
~~~

Ordering needs a tie-breaker key if multiple transactions share a timestamp. If BALANCE_AFTER is the balance after the transaction, the difference between consecutive rows helps audit changes; note that the first transaction has no prior balance in the queried set.

### 13.2 Detecting Abnormal Time Gaps

~~~sql
WITH gaps AS (
    SELECT device_id,
           reading_id,
           reading_time,
           LAG(reading_time) OVER (
               PARTITION BY device_id
               ORDER BY reading_time, reading_id
           ) AS previous_reading_time
    FROM device_readings
)
SELECT device_id,
       reading_id,
       previous_reading_time,
       reading_time,
       reading_time - previous_reading_time AS gap_days
FROM gaps
WHERE previous_reading_time IS NOT NULL
  AND reading_time - previous_reading_time > 1
ORDER BY device_id, reading_time, reading_id;
~~~

This example finds gaps exceeding one day between two DATE measurements. With TIMESTAMP, the difference is an INTERVAL; the comparison condition should use an interval literal or appropriate conversion.

### 13.3 Detecting Status Transitions

~~~sql
WITH status_changes AS (
    SELECT order_id,
           history_id,
           changed_at,
           status,
           LAG(status) OVER (
               PARTITION BY order_id
               ORDER BY changed_at, history_id
           ) AS previous_status
    FROM order_status_history
)
SELECT order_id,
       history_id,
       changed_at,
       previous_status,
       status
FROM status_changes
WHERE previous_status <> status
ORDER BY order_id, changed_at, history_id;
~~~

This is a short example assuming STATUS is NOT NULL. If STATUS is nullable, the `<>` comparison misses cases where one side is NULL; use the null-safe condition shown earlier.

### 13.4 Finding Previous and Next Price Levels

~~~sql
SELECT product_id,
       effective_from,
       price,
       LAG(price) OVER (
           PARTITION BY product_id
           ORDER BY effective_from, price_history_id
       ) AS previous_price,
       LEAD(price) OVER (
           PARTITION BY product_id
           ORDER BY effective_from, price_history_id
       ) AS next_price
FROM product_price_history
ORDER BY product_id, effective_from, price_history_id;
~~~

This example helps inspect price history. If two records share the same EFFECTIVE_FROM, a business rule is needed to decide order and which price takes effect.

### 13.5 Comparing with the Immediately Preceding Business Day

LAG retrieves the preceding existing row; it does not understand work calendars automatically. If you need to compare against the previous business day even when no transactions occurred on that day, join with a calendar dimension containing all business days, then apply LAG over the normalized calendar set.

## 14. Data Types, NULLs, and Technical Notes

### 14.1 value_expr Must Be a Valid Expression

value_expr can be a column or a compatible expression:

~~~sql
LAG(amount * exchange_rate) OVER (
    PARTITION BY account_id
    ORDER BY event_time, event_id
)
~~~

Do not nest another analytic function directly inside value_expr of LAG/LEAD. If you need to retrieve the result of another analytic function, compute it in an inline view/CTE and then apply LAG in the outer query block.

### 14.2 Default Should Be Type-Compatible

~~~sql
LAG(amount, 1, 0) OVER (ORDER BY event_time)
~~~

works properly when AMOUNT is numeric and default is numeric. If value_expr is DATE, use an appropriate DATE value; if VARCHAR2, use a compatible string literal. Oracle applies type conversion rules to arguments, but explicit typing prevents errors or unwanted implicit conversions.

### 14.3 LAG on DATE and TIMESTAMP

LAG can retrieve a DATE or TIMESTAMP value from the preceding row. LAG itself does not compute time intervals; the subsequent subtraction determines the result type:

- DATE - DATE: NUMBER, in days.
- TIMESTAMP - TIMESTAMP: INTERVAL DAY TO SECOND.

If you need to convert to hours/minutes, handle according to the specific data type rather than assuming both subtractions return NUMBER.

### 14.4 No Window Frame in LAG/LEAD Syntax

LAG and LEAD use row-position offsets within a partition and take OVER with PARTITION BY/ORDER BY. Do not add a `ROWS BETWEEN` clause as used with certain analytic aggregates; it is not part of LAG/LEAD syntax.

## 15. Performance and Execution Plans

### 15.1 Sorting Is Part of the Problem

To locate preceding/following rows, Oracle must process the analytic ordering. On large datasets, partitioning and sorting can consume CPU, PGA, or TEMP depending on the plan and row set size.

### 15.2 Indexes May Help, But Do Not Guarantee Avoiding a Sort

Example query:

~~~sql
SELECT account_id,
       event_time,
       event_id,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events;
~~~

An index in this order:

~~~sql
CREATE INDEX idx_account_events_order
ON account_events (account_id, event_time, event_id);
~~~

can help access by partition and ordering. However, Oracle may still choose a sort or another access path depending on filter predicates, cardinality, clustering factor, and other operations. Do not create an index based solely on an illustrative query.

### 15.3 Reducing Input Data When Semantics Permit

If analyzing only a single year, you can filter in the source query block before applying LAG:

~~~sql
WITH source_rows AS (
    SELECT account_id,
           event_id,
           event_time,
           amount
    FROM account_events
    WHERE event_time >= DATE '2026-01-01'
      AND event_time <  DATE '2027-01-01'
)
SELECT account_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM source_rows;
~~~

However, verify the requirement: does the first row of the year need to be compared against the last row of the previous year? If so, filtering by year before computing LAG removes the reference row. In that case, include the needed historical row in the analytic input and filter results after computing LAG.

This is a critical point: early filtering reduces data volume, but it can also alter what "preceding row" means.

### 15.4 Viewing the Execution Plan

~~~sql
EXPLAIN PLAN FOR
SELECT account_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount
FROM account_events;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN shows the estimated plan. When tuning, inspect the actual execution plan, cardinality, sort/window operations, I/O, CPU, and TEMP on representative data. Do not draw performance conclusions merely from how many times LAG appears in the SELECT list.

## 16. Lab: LAG and LEAD with Transaction History

Commands in this section are intended for a dedicated practice schema with table-creation privileges and appropriate quota. Do not run experimental DDL/DML on a production schema. Oracle DDL such as CREATE TABLE causes an implicit commit.

### 16.1 Create the Table

~~~sql
CREATE TABLE lab_account_events (
    event_id    NUMBER PRIMARY KEY,
    account_id  NUMBER NOT NULL,
    event_time  DATE NOT NULL,
    amount      NUMBER(12,2),
    status      VARCHAR2(20)
);
~~~

### 16.2 Load Data

~~~sql
INSERT INTO lab_account_events VALUES
    (1, 10, DATE '2026-11-01', 100, 'OPEN');
INSERT INTO lab_account_events VALUES
    (2, 10, DATE '2026-11-03', 120, 'OPEN');
INSERT INTO lab_account_events VALUES
    (3, 10, DATE '2026-11-03', 90, 'HOLD');
INSERT INTO lab_account_events VALUES
    (4, 10, DATE '2026-11-08', NULL, 'HOLD');
INSERT INTO lab_account_events VALUES
    (5, 10, DATE '2026-11-12', 150, 'CLOSED');
INSERT INTO lab_account_events VALUES
    (6, 20, DATE '2026-11-02', 50, 'OPEN');
INSERT INTO lab_account_events VALUES
    (7, 20, DATE '2026-11-05', 75, 'OPEN');
INSERT INTO lab_account_events VALUES
    (8, 20, DATE '2026-11-10', 60, 'HOLD');
COMMIT;
~~~

Account 10 has two events on the same date to demonstrate the role of EVENT_ID as a tie-breaker; it also has a NULL AMOUNT to test RESPECT/IGNORE NULLS. Account 20 forms an independent partition.

### 16.3 View Preceding and Following Rows

~~~sql
SELECT account_id,
       event_id,
       event_time,
       amount,
       LAG(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_amount,
       LEAD(amount) OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS next_amount
FROM lab_account_events
ORDER BY account_id, event_time, event_id;
~~~

Check:

- Event 1 of account 10 has no preceding row in the partition.
- Event 3 takes event 2 as its preceding row despite sharing EVENT_TIME, because EVENT_ID is the secondary key.
- Event 4 has AMOUNT NULL; event 5 with RESPECT NULLS receives a NULL previous_amount.
- Event 6 is the first row of account 20; it does not take event 5 of account 10.

### 16.4 Compare RESPECT and IGNORE NULLS

~~~sql
SELECT account_id,
       event_id,
       amount,
       LAG(amount) RESPECT NULLS OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_respecting_null,
       LAG(amount) IGNORE NULLS OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS previous_known_amount
FROM lab_account_events
ORDER BY account_id, event_time, event_id;
~~~

At event 5 of account 10:

- PREVIOUS_RESPECTING_NULL is NULL because the immediately preceding event 4 has amount NULL.
- PREVIOUS_KNOWN_AMOUNT is 90 because event 3 is the most recent prior non-NULL amount.

### 16.5 Calculate Difference

~~~sql
WITH compared AS (
    SELECT account_id,
           event_id,
           event_time,
           amount,
           LAG(amount) OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM lab_account_events
)
SELECT account_id,
       event_id,
       amount,
       previous_amount,
       amount - previous_amount AS amount_change
FROM compared
ORDER BY account_id, event_time, event_id;
~~~

The change for event 2 of account 10 is 20. Event 3 is -30 compared to event 2. Event 5 yields NULL because the preceding amount (event 4) is NULL under RESPECT NULLS.

### 16.6 Filter Rows That Increased Over the Preceding Row

~~~sql
WITH compared AS (
    SELECT account_id,
           event_id,
           event_time,
           amount,
           LAG(amount) OVER (
               PARTITION BY account_id
               ORDER BY event_time, event_id
           ) AS previous_amount
    FROM lab_account_events
)
SELECT account_id,
       event_id,
       event_time,
       amount,
       previous_amount
FROM compared
WHERE amount > previous_amount
ORDER BY account_id, event_time, event_id;
~~~

The result contains only rows whose amount is greater than the preceding row's amount where both compared values are non-NULL.

### 16.7 Identify the First Row of Each Account

~~~sql
SELECT account_id,
       event_id,
       event_time,
       ROW_NUMBER() OVER (
           PARTITION BY account_id
           ORDER BY event_time, event_id
       ) AS row_num
FROM lab_account_events
ORDER BY account_id, event_time, event_id;
~~~

Filter ROW_NUM=1 in an outer query block to get the first row for each account.

### 16.8 Clean Up the Lab Table

Only drop tables you created in the lab schema once you have confirmed the data is no longer needed. Do not put DROP TABLE in scripts that might accidentally run on production; DDL performs an implicit commit and you cannot rely on ROLLBACK to recover.

## 17. Common Errors and Misconceptions

| Error / Misconception | Reality | Solution |
|---|---|---|
| LAG always reads the preceding row in physical storage order | LAG uses ORDER BY inside OVER | Declare the business order explicitly |
| ORDER BY is unnecessary | A meaningful preceding/following row cannot be determined without it | Always use an analytic ORDER BY |
| Ordering only by timestamp is enough | Multiple rows can share the same timestamp | Add a unique tie-breaker key |
| PARTITION BY only sorts | It creates independent groups and resets offsets | Choose the right grouping key |
| The query's final ORDER BY controls LAG | The outer ORDER BY only sorts returned rows | Put ORDER BY inside OVER |
| Offset 2 means two days earlier | Offset counts row positions | Use calendar/date logic if calendar days are needed |
| Default replaces all NULLs | Default is only used when no row exists at the offset | Use NVL if you also want to replace NULL from the referenced row |
| IGNORE NULLS removes NULL rows from the result | It only skips NULL values when searching for the offset | Do not confuse with WHERE IS NOT NULL |
| LEAD is always a future date | It is the following row in OVER order | Check ASC/DESC |
| LAG can be used directly in WHERE in the same query block | Analytic functions are computed after WHERE | Use a CTE/inline view |
| LAG over months always gets the previous calendar month | It gets the previous existing row | Use a calendar dimension if all months are needed |
| Correlated/self join is always faster than analytic | Optimizer and data shape determine cost | Check plan and runtime |
| LAG returning NULL means it is the first row | The preceding row may exist with NULL value_expr | Use ROW_NUMBER to distinguish |
| LAG/LEAD accept a window frame like SUM | LAG/LEAD syntax has no windowing clause | Use only PARTITION BY/ORDER BY |

## 18. Checklist Before Deploying to Reports or Applications

- Define "preceding" and "following" accurately by time, sequence number, version, or business key.
- Use PARTITION BY to prevent cross-comparison across different customers, accounts, products, or groups.
- Add a tie-breaker so ORDER BY determines a unique order when duplicate values exist.
- Decide whether NULLs should be respected or ignored; RESPECT NULLS is the default.
- Distinguish having no referenced row from having a referenced row whose value_expr is NULL.
- Choose offset by row position count, without confusing it with days or months.
- If all calendar periods are required, generate a calendar dimension or complete period series before computing LAG/LEAD.
- If filtering by analytic results is needed, use an inline view or CTE.
- When filtering input data, check whether historical rows needed for comparison are being excluded.
- Verify data types of default, value_expr, and calculations after LAG/LEAD.
- Inspect the execution plan and real workload before adding indexes.

## 19. Self-Practice Exercises

**Question 1 — Preceding row.** A partition has values 10, 20, 15 in order. What are the results of LAG(x) respectively?

Hint: NULL, 10, 20.

**Question 2 — Following row.** With the same data, what are the results of LEAD(x) respectively?

Hint: 20, 15, NULL.

**Question 3 — Offset.** On the fourth row, which value does LAG(x, 2) retrieve?

Hint: The value at the second row in the same partition, because offset counts row positions.

**Question 4 — Partition.** If there are two accounts, why does the first row of the second account not retrieve the last value of the first account?

Hint: PARTITION BY separates sequences independently and resets offsets within each partition.

**Question 5 — Tie-breaker.** Two events share the same EVENT_TIME; what should be added to stabilize the ordering?

Hint: A unique secondary key such as EVENT_ID, if that matches the appropriate business ordering rule.

**Question 6 — Default.** Compare LAG(amount,1,0) and NVL(LAG(amount),0) when the preceding row exists but AMOUNT is NULL.

Hint: The first returns NULL; the second returns 0.

**Question 7 — NULL handling.** The current row has value 30, the preceding row has NULL, and the row before that has 20. What do LAG(value) RESPECT NULLS and IGNORE NULLS return?

Hint: RESPECT returns NULL; IGNORE returns 20.

**Question 8 — Filtering.** Why can't LAG be placed directly in the WHERE clause of the same query block?

Hint: Analytic functions are evaluated after WHERE; compute it in a CTE and filter outside.

**Question 9 — Missing month.** Data exists for January and March, but not February. Which month does LAG for March return?

Hint: January, because it is the preceding existing row. To compare against February, build a complete calendar first.

**Question 10 — Datetime types.** How do DATE minus DATE and TIMESTAMP minus TIMESTAMP differ in Oracle?

Hint: DATE yields NUMBER in days; TIMESTAMP yields INTERVAL DAY TO SECOND.

## 20. Summary

**LAG** and **LEAD** are analytic functions that retrieve values from preceding or following rows according to a defined ordering:

- LAG looks backward; LEAD looks forward.
- The default offset is 1; the default fallback value is NULL and is used only when no row exists at the requested position.
- PARTITION BY divides data into independent groups; ORDER BY inside OVER defines the reference order.
- RESPECT NULLS is the default; IGNORE NULLS skips NULL expression values when searching for the offset.
- ORDER BY requires a tie-breaker if sort keys can repeat, ensuring deterministic results.
- LAG/LEAD keep current rows; they do not aggregate or automatically generate missing dates/months.
- To filter analytic results, compute them in a CTE or inline view and filter in the outer query block.

When you need to compare prior-period revenue, detect status changes, measure gaps between events, or analyze history per account, LAG and LEAD generally keep SQL more concise and expressive than a self join. The most important step is defining the partition, ordering, NULL handling, and offset semantics accurately before using the results in reports or business logic.
