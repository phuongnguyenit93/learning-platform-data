# COUNT, SUM, AVG, MIN, MAX, and NULL Values in PostgreSQL

A sales system may need to answer: **how many orders were placed**, **what is the total value of paid orders**, **what is the average value per order**, **what is the smallest/largest order**, and **how many rows do not yet have a known amount**. Those questions typically use the aggregate functions `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX`.

A common source of confusion is that PostgreSQL handles **`NULL`** according to different rules: `COUNT(*)` counts every row, while `COUNT(column)` ignores `NULL` values in that column; `SUM`, `AVG`, `MIN`, and `MAX` also ignore `NULL`, but **usually return `NULL` rather than 0 when there are no matching input values**. The results can directly affect revenue, conversion rates, data quality, and API logic.

This lesson walks through basic aggregate queries to `GROUP BY`, `WHERE`, `HAVING`, `DISTINCT`, `FILTER`, `LEFT JOIN`, `COALESCE`, ratio calculations, and result data types. A small practice schema helps you verify every example yourself. The focus is on **choosing the right denominator, understanding missing values, and interpreting results in business terms**, rather than just writing SQL that runs.

## 1. Quick Overview of the Five Aggregate Functions

Aggregate functions take **a set of rows or values** and produce a single summary result per group:

| Function | Question Answered | Does It Include NULL Values in the Calculation? | Result When No Matching Values Exist |
| --- | --- | --- | --- |
| `COUNT(*)` | How many **rows** are there? | Counts rows containing NULL | `0` |
| `COUNT(expression)` | How many **non-NULL** values of the expression are there? | No | `0` |
| `SUM(expression)` | What is the sum of the numeric/supported values? | Ignores NULL | `NULL` |
| `AVG(expression)` | What is the average of the present values? | Ignores NULL | `NULL` |
| `MIN(expression)` | What is the minimum value? | Ignores NULL | `NULL` |
| `MAX(expression)` | What is the maximum value? | Ignores NULL | `NULL` |

The rightmost column results are especially important when there are no rows after `WHERE`, or when **every value of the column being aggregated is `NULL`**.

A simple aggregate query:

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(net_amount) AS total_amount,
    AVG(net_amount) AS average_amount,
    MIN(net_amount) AS smallest_amount,
    MAX(net_amount) AS largest_amount
FROM some_orders;
~~~

`some_orders` here is an illustrative name; the hands-on examples below use the `agg_lab_151.orders` table that can be created with SQL.

### 1.1. Aggregates vs. Row-by-Row Expressions

~~~sql
-- Row-by-row expression:
SELECT 100 + 20 AS value_per_expression;

-- Aggregating across multiple rows:
SELECT SUM(amount)
FROM (
    VALUES (100), (20), (30)
) AS v(amount);
-- 150
~~~

With an aggregate, PostgreSQL takes the corresponding input values and computes one representative result for that set. If `GROUP BY` is used, each group is computed separately. Without `GROUP BY`, all rows passing `FROM`/`WHERE` are treated as **a single aggregate group**.

## 2. Preparing the Practice Data

Create a dedicated schema on a **learning database**; do not run table creation or seed commands in production. If the `agg_lab_151` schema already exists and holds data from another exercise, choose a different schema name; do not arbitrarily drop existing data.

### 2.1. Customers Table

~~~sql
CREATE SCHEMA agg_lab_151;

CREATE TABLE agg_lab_151.customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NULL
);

INSERT INTO agg_lab_151.customers
    (customer_id, customer_name, region)
VALUES
    (1, 'Nguyễn An',  'Hà Nội'),
    (2, 'Trần Bình',  'Đà Nẵng'),
    (3, 'Lê Chi',     'TP.HCM'),
    (4, 'Phạm Dũng',  NULL);
~~~

Customer `4` **has no orders yet**. This helps demonstrate the difference between `COUNT(*)` and `COUNT(o.order_id)` when using `LEFT JOIN`.

### 2.2. Orders Table

~~~sql
CREATE TABLE agg_lab_151.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NULL
        REFERENCES agg_lab_151.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'NEW', 'CANCELLED')),
    order_date DATE NOT NULL,
    net_amount NUMERIC(12, 2) NULL
        CHECK (net_amount >= 0),
    shipping_fee NUMERIC(12, 2) NULL
        CHECK (shipping_fee >= 0),
    rating INTEGER NULL
        CHECK (rating BETWEEN 1 AND 5)
);
~~~

The `NULL` values have illustrative meanings:

- `net_amount = NULL`: the amount has not been determined/recorded at the time the data is viewed.
- `net_amount = 0`: **the amount is known to be 0**, for example a free promotional order.
- `shipping_fee = NULL`: the shipping fee has not been recorded yet, **not necessarily free**.
- `rating = NULL`: the customer has not submitted a rating yet.
- `customer_id = NULL`: a guest order.

### 2.3. Loading Eight Orders

~~~sql
INSERT INTO agg_lab_151.orders
    (
        order_id, customer_id, status, order_date,
        net_amount, shipping_fee, rating
    )
VALUES
    (101, 1,    'PAID',      DATE '2026-11-01', 120000, 15000, 5),
    (102, 1,    'NEW',       DATE '2026-11-02', NULL,   NULL,  NULL),
    (103, 2,    'PAID',      DATE '2026-11-02',  80000,     0, 4),
    (104, 2,    'CANCELLED', DATE '2026-11-03', 200000, NULL,  NULL),
    (105, 3,    'PAID',      DATE '2026-11-03',      0, 10000, NULL),
    (106, 3,    'PAID',      DATE '2026-11-04', 300000, NULL,  3),
    (107, NULL, 'PAID',      DATE '2026-11-04', 120000,  5000, NULL),
    (108, 1,    'NEW',       DATE '2026-11-05', NULL,   NULL,  NULL);
~~~

Orders `101` and `107` **share the same amount of 120,000, but they are two distinct orders**. This is particularly important when analyzing `SUM(DISTINCT net_amount)`: duplicate values **do not** mean duplicate transactions.

### 2.4. Inspecting the Raw Data

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    net_amount,
    shipping_fee,
    rating
FROM agg_lab_151.orders
ORDER BY order_id;
~~~

| Order | Customer | Status | `net_amount` | `shipping_fee` | `rating` |
| --- | ---: | --- | ---: | ---: | ---: |
| 101 | 1 | PAID | 120,000 | 15,000 | 5 |
| 102 | 1 | NEW | `NULL` | `NULL` | `NULL` |
| 103 | 2 | PAID | 80,000 | 0 | 4 |
| 104 | 2 | CANCELLED | 200,000 | `NULL` | `NULL` |
| 105 | 3 | PAID | 0 | 10,000 | `NULL` |
| 106 | 3 | PAID | 300,000 | `NULL` | 3 |
| 107 | `NULL` | PAID | 120,000 | 5,000 | `NULL` |
| 108 | 1 | NEW | `NULL` | `NULL` | `NULL` |

The dataset has **8 orders**, including **5 PAID**, **2 NEW**, and **1 CANCELLED**. There are **6 known `net_amount` values**, **2 `NULL`s**, and **3 `rating` values**. Among the six monetary values, there is one valid value of 0.

## 3. COUNT(*): Counting Rows

`COUNT(*)` counts all rows processed by the query, regardless of whether columns inside contain `NULL`.

~~~sql
SELECT COUNT(*) AS total_orders
FROM agg_lab_151.orders;
-- 8
~~~

`COUNT(*)` **does not inspect a specific column to decide whether to count a row**. It counts rows, so orders `102` and `108` with `net_amount = NULL` are still included.

### 3.1. COUNT(*) Combined with WHERE

~~~sql
SELECT COUNT(*) AS paid_orders
FROM agg_lab_151.orders
WHERE status = 'PAID';
-- 5
~~~

`WHERE` filters rows **before** `COUNT(*)` counts them. Therefore, `COUNT(*)` does not necessarily return the total row count of the entire table; it returns the number of rows **after all relevant filter conditions**.

### 3.2. COUNT(*) When No Rows Match

~~~sql
SELECT COUNT(*) AS cancelled_before_2020
FROM agg_lab_151.orders
WHERE status = 'CANCELLED'
  AND order_date < DATE '2020-01-01';
-- 0
~~~

No rows satisfy the condition, yet an aggregate query **without GROUP BY** still returns **one row**, with `COUNT(*) = 0`.

### 3.3. COUNT(1) vs. COUNT(*) in PostgreSQL

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(1) AS all_constant_ones
FROM agg_lab_151.orders;
-- 8, 8
~~~

Because the constant expression `1` is non-`NULL` for every row, `COUNT(1)` counts the same number of rows as `COUNT(*)` in this example. In PostgreSQL, **`COUNT(*)` is the clear and idiomatic way to count rows**. Do not choose `COUNT(1)` under the assumption that it is always faster; optimization depends on the planner, version, and actual context.

## 4. COUNT(column): Counting Non-NULL Values

`COUNT(expression)` increments the counter only when **the value of the expression is not `NULL`**.

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(customer_id) AS orders_with_registered_customer,
    COUNT(net_amount) AS orders_with_known_amount,
    COUNT(shipping_fee) AS orders_with_known_shipping,
    COUNT(rating) AS rated_orders
FROM agg_lab_151.orders;
~~~

| Expression | Result | Why? |
| --- | ---: | --- |
| `COUNT(*)` | 8 | All orders |
| `COUNT(customer_id)` | 7 | Order 107 has no registered customer |
| `COUNT(net_amount)` | 6 | Orders 102 and 108 have `NULL` amount |
| `COUNT(shipping_fee)` | 4 | Only orders 101, 103, 105, and 107 have a recorded fee |
| `COUNT(rating)` | 3 | Only orders 101, 103, and 106 have a rating |

**The value 0 is still counted.** `COUNT(net_amount)` includes order `105` because an amount of 0 is **not `NULL`**. `COUNT(shipping_fee)` also includes order `103` because a shipping fee of 0 is known.

### 4.1. COUNT on an Expression

The argument does not have to be a bare column name:

~~~sql
SELECT
    COUNT(net_amount + shipping_fee)
        AS orders_with_both_amount_and_shipping
FROM agg_lab_151.orders;
-- 4
~~~

For `net_amount + shipping_fee` to be non-`NULL`, **both values must be present**. The qualifying orders are `101`, `103`, `105`, and `107`. All four have non-NULL values for both fields, so the result is **4**. This is easy to miss if you only check the amount column and forget to check the shipping fee.

Writing the same logic with explicit conditions:

~~~sql
SELECT COUNT(*) AS both_known
FROM agg_lab_151.orders
WHERE net_amount IS NOT NULL
  AND shipping_fee IS NOT NULL;
-- 4
~~~

If you want **at least one** of the two fields to be present, `COUNT(net_amount + shipping_fee)` is unsuitable because adding `NULL` returns `NULL`. You need an `OR` condition or an intentional `COALESCE` rule.

### 4.2. COUNT(*) - COUNT(column): Counting NULL Values

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(net_amount) AS known_amounts,
    COUNT(*) - COUNT(net_amount) AS missing_amounts
FROM agg_lab_151.orders;
-- 8, 6, 2
~~~

This pattern is useful for measuring missing-data rates. Another approach, often easier to read:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS missing_amounts
FROM agg_lab_151.orders;
-- 2
~~~

When using `COUNT(column)` instead of `COUNT(*)`, always ask: **can that column be `NULL`?** If so, the two functions can return different numbers.

## 5. SUM: Summing Known Values

`SUM(expression)` adds the **non-`NULL`** values. It does not treat `NULL` as 0 in the data; it simply skips absent values from the sum.

~~~sql
SELECT SUM(net_amount) AS total_known_amount
FROM agg_lab_151.orders;
-- 820000.00
~~~

Values summed:

~~~text
120000 + 80000 + 200000 + 0 + 300000 + 120000
= 820000
~~~

The two `NEW` orders with `net_amount = NULL` contribute no value. Order `105` with `net_amount = 0` is still a known value, though it does not change the arithmetic total.

### 5.1. Total Amount Is Not Necessarily Revenue

The result `820000` above **includes the `CANCELLED` order of 200,000**. If the requirement is the total amount of paid orders, you must filter by status:

~~~sql
SELECT SUM(net_amount) AS paid_amount
FROM agg_lab_151.orders
WHERE status = 'PAID';
-- 620000.00
~~~

Actual accounting policies may also need to consider refunds, taxes, fees, payment timing, and transaction reconciliation. `SUM` only adds **the values passed into it by the query**; it does not automatically understand a company's definition of revenue.

### 5.2. Summing Integers

~~~sql
SELECT SUM(x) AS total_integer_values
FROM (
    VALUES (10::integer), (20::integer), (30::integer)
) AS v(x);
-- 60
~~~

PostgreSQL follows specific result-type rules: `SUM(integer)` typically returns `bigint`, while `SUM(bigint)` returns `numeric` to provide a larger range. Do not cast large sums back to `integer` unnecessarily.

### 5.3. SUM with Negative Numbers

`SUM` does not require all values to be positive:

~~~sql
SELECT SUM(adjustment) AS net_change
FROM (
    VALUES
        (1000::numeric),
        (-200::numeric),
        (NULL::numeric),
        (300::numeric)
) AS t(adjustment);
-- 1100
~~~

Arithmetic sum: `1000 - 200 + 300 = 1100`. The `NULL` value is not added. If negative numbers represent refunds or adjustments, using `SUM` is valid **as long as data recording is consistent and the scope is well defined**.

## 6. AVG: Average of Non-NULL Values

`AVG(expression)` takes the average of the **non-`NULL`** input values. Conceptually, this corresponds to:

\[
\operatorname{AVG}(x)
= \frac{\operatorname{SUM}(x)}{\operatorname{COUNT}(x)}
\]

when at least one non-NULL value exists and type/arithmetic rules are handled appropriately. **The denominator is not `COUNT(*)` if the column contains `NULL`s.**

~~~sql
SELECT
    SUM(net_amount) AS total_known_amount,
    COUNT(net_amount) AS known_amount_count,
    AVG(net_amount) AS average_known_amount
FROM agg_lab_151.orders;
~~~

Result:

~~~text
total_known_amount = 820000.00
known_amount_count = 6
average_known_amount ≈ 136666.67
~~~

### 6.1. AVG Ignores NULL but Includes 0

Order `105` with `net_amount = 0` is included in the **denominator of 6**. The two `NEW` orders with `NULL` amount are excluded.

If you replace `NULL` with 0 before computing AVG:

~~~sql
SELECT
    AVG(net_amount) AS average_known,
    AVG(COALESCE(net_amount, 0))
        AS average_when_missing_is_zero
FROM agg_lab_151.orders;
~~~

| Calculation | Sum | Count Divided By | Approximate Average |
| --- | ---: | ---: | ---: |
| `AVG(net_amount)` | 820,000 | 6 | 136,666.67 |
| `AVG(COALESCE(net_amount, 0))` | 820,000 | 8 | 102,500.00 |

The two answers differ because they reflect **two different statistical definitions**:

- Average across orders with a **known amount**.
- Average across **all orders**, by convention treating orders with an unknown amount as 0.

Neither can be assumed always right without knowing the business meaning of `NULL`.

### 6.2. AVG on Paid Orders Only

~~~sql
SELECT
    COUNT(*) AS paid_orders,
    COUNT(net_amount) AS paid_orders_with_amount,
    SUM(net_amount) AS paid_total,
    AVG(net_amount) AS paid_average
FROM agg_lab_151.orders
WHERE status = 'PAID';
~~~

Result: **5 PAID orders**, **5 known amounts**, total **620,000**, average **124,000**.

If real-world data contains a `PAID` order with `net_amount IS NULL`, `AVG(net_amount)` will skip that row. This can make the average look valid even when a data bug exists. You should report **`COUNT(*)` alongside `COUNT(net_amount)`** to reveal completeness.

### 6.3. Average Rating

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(rating) AS rated_orders,
    AVG(rating) AS average_rating,
    MIN(rating) AS lowest_rating,
    MAX(rating) AS highest_rating
FROM agg_lab_151.orders;
~~~

The three known ratings are `5`, `4`, and `3`:

- `COUNT(rating) = 3`.
- `AVG(rating) = 4`.
- `MIN(rating) = 3`.
- `MAX(rating) = 5`.

**Do not divide the sum of rating scores by 8 orders** if the goal is the average among customers who rated. Conversely, to measure the **percentage of rated orders**, the denominator is all orders: `COUNT(rating) / COUNT(*)`.

### 6.4. Weighted Average

A common analytical mistake: computing the **average of group averages** instead of weighting by observation count.

Suppose three groups have:

~~~text
Group A: 1 PAID order, average 120000
Group B: 1 PAID order, average  80000
Group C: 2 PAID orders, average 150000
~~~

The unweighted average of the three group averages is:

\[
(120000 + 80000 + 150000)/3 \approx 116666.67
\]

However, the average across the **four orders** of the three registered customers is:

\[
(120000 + 80000 + 0 + 300000)/4 = 125000
\]

The two numbers differ because each group has a different number of orders. If the goal is "every **order** has equal weight," divide the total amount by the **total number of qualifying orders**; if the goal is "every **customer** has equal weight," averaging per-customer averages can make sense.

## 7. MIN and MAX: Smallest and Largest

`MIN` and `MAX` select the lowest/highest value from the set of non-`NULL` values.

~~~sql
SELECT
    MIN(net_amount) AS min_known_amount,
    MAX(net_amount) AS max_known_amount,
    MIN(order_date) AS first_order_date,
    MAX(order_date) AS last_order_date
FROM agg_lab_151.orders;
~~~

Result:

| Expression | Result |
| --- | --- |
| `MIN(net_amount)` | `0.00` |
| `MAX(net_amount)` | `300000.00` |
| `MIN(order_date)` | `2026-11-01` |
| `MAX(order_date)` | `2026-11-05` |

### 7.1. MIN/MAX Ignore NULL

~~~sql
SELECT
    MIN(shipping_fee) AS min_known_fee,
    MAX(shipping_fee) AS max_known_fee
FROM agg_lab_151.orders;
~~~

The known fees are `15000`, `0`, `10000`, and `5000`:

- `MIN(shipping_fee) = 0`.
- `MAX(shipping_fee) = 15000`.

You cannot conclude that "every order has a fee between 0 and 15,000," because **four orders have `NULL` fees** and their true fees cannot be asserted.

### 7.2. MIN/MAX with Non-Numeric Data Types

These functions also apply to any type with suitable comparison rules, such as dates, timestamps, and text:

~~~sql
SELECT
    MIN(order_date) AS earliest,
    MAX(order_date) AS latest
FROM agg_lab_151.orders;
~~~

For text, "smallest/largest" is determined by collation/comparison rules, **not necessarily by string length or natural word meaning**. To find the order with the smallest value along with its `order_id`, see Section 7.3.

### 7.3. MIN/MAX Do Not Automatically Return the Full Matching Row

~~~sql
SELECT MAX(net_amount)
FROM agg_lab_151.orders;
-- 300000
~~~

The query only returns the **maximum value**, not which order it belongs to. One way to fetch the entire row:

~~~sql
SELECT
    order_id, customer_id, status, net_amount
FROM agg_lab_151.orders
WHERE net_amount IS NOT NULL
ORDER BY net_amount DESC, order_id ASC
LIMIT 1;
~~~

The result is order `106` in the sample dataset. If multiple orders tie for the maximum value, `LIMIT 1` picks only one according to the specified tie-breaker order. To get **all** orders matching the maximum value:

~~~sql
SELECT
    order_id, net_amount
FROM agg_lab_151.orders
WHERE net_amount = (
    SELECT MAX(net_amount)
    FROM agg_lab_151.orders
);
~~~

Do not write `SELECT order_id, MAX(net_amount)` without `GROUP BY` expecting PostgreSQL to know "the `order_id` of the max row." Those represent two different levels of aggregation.

## 8. NULL Values: Distinguishing No Rows from All-NULL Values

Two situations can both cause `SUM`/`AVG`/`MIN`/`MAX` to return `NULL`:

1. **No rows remain** after filtering.
2. Rows exist, but **all values of the aggregated expression are `NULL`**.

### 8.1. Completely Empty Set

~~~sql
SELECT
    COUNT(*) AS rows_found,
    COUNT(net_amount) AS amounts_found,
    SUM(net_amount) AS sum_amount,
    AVG(net_amount) AS avg_amount,
    MIN(net_amount) AS min_amount,
    MAX(net_amount) AS max_amount
FROM agg_lab_151.orders
WHERE order_id < 0;
~~~

Conceptual result:

| `rows_found` | `amounts_found` | `sum_amount` | `avg_amount` | `min_amount` | `max_amount` |
| ---: | ---: | --- | --- | --- | --- |
| 0 | 0 | `NULL` | `NULL` | `NULL` | `NULL` |

**`SUM` does not default to 0 on an empty set.** This is an important standard behavior to account for when building reports.

### 8.2. Rows Exist, but Every Column Value Is NULL

The two `NEW` orders have `net_amount = NULL`:

~~~sql
SELECT
    COUNT(*) AS new_orders,
    COUNT(net_amount) AS known_amounts,
    SUM(net_amount) AS total_amount,
    AVG(net_amount) AS average_amount,
    MIN(net_amount) AS minimum_amount,
    MAX(net_amount) AS maximum_amount
FROM agg_lab_151.orders
WHERE status = 'NEW';
~~~

Result:

~~~text
new_orders     = 2
known_amounts  = 0
total_amount   = NULL
average_amount = NULL
minimum_amount = NULL
maximum_amount = NULL
~~~

Compared to Section 8.1, `COUNT(*)` helps distinguish between **no orders** and **orders exist but their amounts are not yet recorded**.

### 8.3. Aggregation Without GROUP BY vs. With GROUP BY

Without `GROUP BY`:

~~~sql
SELECT COUNT(*) AS cnt
FROM agg_lab_151.orders
WHERE status = 'REFUNDED';
-- One row with cnt = 0.
~~~

With `GROUP BY`:

~~~sql
SELECT status, COUNT(*) AS cnt
FROM agg_lab_151.orders
WHERE status = 'REFUNDED'
GROUP BY status;
-- Returns zero rows.
~~~

Difference:

- An **aggregate query without GROUP BY** on an empty set still forms one overall group and returns one row.
- A query **with GROUP BY on a column** over an empty set forms no groups, so it returns **0 rows**.

When designing APIs, you must distinguish "one row with a count of 0" from "no result rows," especially when displaying lists by month, day, or status.

## 9. COUNT(DISTINCT ...), SUM(DISTINCT ...), and AVG(DISTINCT ...)

The `DISTINCT` keyword inside an aggregate removes **duplicate input values** before aggregating. For standard aggregate functions, `NULL` does not contribute to `COUNT(expression)` or numeric operations.

### 9.1. Counting Registered Customers Who Placed Orders

~~~sql
SELECT
    COUNT(*) AS order_count,
    COUNT(customer_id) AS orders_linked_to_customer,
    COUNT(DISTINCT customer_id) AS unique_customers_with_orders
FROM agg_lab_151.orders;
~~~

Result:

- `COUNT(*) = 8`: eight orders.
- `COUNT(customer_id) = 7`: seven orders linked to registered customers, excluding the guest order.
- `COUNT(DISTINCT customer_id) = 3`: only three distinct customer IDs (`1`, `2`, `3`).

**`COUNT(DISTINCT customer_id)` does not count customers without orders** (customer 4) because the input table is `orders`. To count every customer in the system, query the `customers` table.

### 9.2. DISTINCT Is Not a Way to Deduplicate Business Records

In the dataset, orders `101` and `107` both have `net_amount = 120000`. Observe:

~~~sql
SELECT
    COUNT(net_amount) AS known_amount_rows,
    COUNT(DISTINCT net_amount) AS unique_amount_values,
    SUM(net_amount) AS normal_sum,
    SUM(DISTINCT net_amount) AS distinct_sum,
    AVG(net_amount) AS normal_avg,
    AVG(DISTINCT net_amount) AS distinct_avg
FROM agg_lab_151.orders;
~~~

| Metric | Result |
| --- | ---: |
| `COUNT(net_amount)` | 6 |
| `COUNT(DISTINCT net_amount)` | 5 |
| `SUM(net_amount)` | 820,000 |
| `SUM(DISTINCT net_amount)` | 700,000 |
| `AVG(net_amount)` | approx. 136,666.67 |
| `AVG(DISTINCT net_amount)` | 140,000 |

`SUM(DISTINCT net_amount)` adds the value 120,000 **only once**, even though two distinct orders have that same amount. This is **not the correct total revenue** if both orders are valid.

`DISTINCT` is only appropriate when you **truly want to aggregate unique values**. If your data source has duplicate order rows due to an incorrect JOIN, fix the JOIN or aggregate at the right key/grain—**do not use `SUM(DISTINCT money)` to mask the bug**.

### 9.3. NULL in COUNT(DISTINCT)

~~~sql
SELECT
    COUNT(DISTINCT customer_id) AS known_customers,
    COUNT(*) FILTER (WHERE customer_id IS NULL)
        AS guest_orders
FROM agg_lab_151.orders;
-- 3 and 1
~~~

`COUNT(DISTINCT customer_id)` does not treat `NULL` as another distinct customer ID. However, when using `GROUP BY customer_id`, PostgreSQL groups `NULL` values together into **one group** for aggregation. These two behaviors do not conflict: one is the aggregate rule for NULL inputs, and the other is the grouping rule.

## 10. GROUP BY: Aggregating per Group

Without `GROUP BY`, all orders remaining after filtering are aggregated together. With `GROUP BY status`, PostgreSQL creates one group per status.

~~~sql
SELECT
    status,
    COUNT(*) AS orders_count,
    COUNT(net_amount) AS known_amounts,
    SUM(net_amount) AS amount_sum,
    AVG(net_amount) AS amount_avg,
    MIN(net_amount) AS amount_min,
    MAX(net_amount) AS amount_max
FROM agg_lab_151.orders
GROUP BY status
ORDER BY status;
~~~

Main result:

| `status` | `orders_count` | `known_amounts` | `amount_sum` | `amount_avg` |
| --- | ---: | ---: | ---: | ---: |
| CANCELLED | 1 | 1 | 200,000 | 200,000 |
| NEW | 2 | 0 | `NULL` | `NULL` |
| PAID | 5 | 5 | 620,000 | 124,000 |

A query using `GROUP BY` normally requires columns in `SELECT` that are **not inside an aggregate** to be included in the grouping list or be functionally dependent according to PostgreSQL's supported rules. For example:

~~~sql
-- Invalid in a general aggregate query:
-- SELECT status, order_id, COUNT(*)
-- FROM agg_lab_151.orders
-- GROUP BY status;
~~~

`order_id` does not have a single unique value per `status` group. If you want a list of IDs, use a different construct such as `array_agg` or a detail query rather than picking an arbitrary ID.

### 10.1. GROUP BY on Multiple Columns

~~~sql
SELECT
    order_date,
    status,
    COUNT(*) AS count_orders,
    SUM(net_amount) AS sum_known_amount
FROM agg_lab_151.orders
GROUP BY order_date, status
ORDER BY order_date, status;
~~~

Each **`(order_date, status)`** pair forms a distinct group. Multiple orders on the same date with the same status are aggregated together; orders with different statuses form separate groups.

### 10.2. GROUP BY Can Create a NULL Group

Including guest orders:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS orders_count,
    SUM(net_amount) AS amount_sum
FROM agg_lab_151.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

Groups present:

| `customer_id` | Order Count | Known Amount Sum |
| --- | ---: | ---: |
| 1 | 3 | 120,000 |
| 2 | 2 | 280,000 |
| 3 | 2 | 300,000 |
| `NULL` | 1 | 120,000 |

Rows with `customer_id IS NULL` are combined into a single guest group. **There is no group for customer 4** because customer 4 has no rows in the `orders` table. To list customers with zero orders, query from the `customers` table using `LEFT JOIN` as shown in Section 13.

## 11. WHERE and HAVING: Filtering Before or After Aggregation?

The two clauses serve two different stages:

- `WHERE` filters **input rows**, before `GROUP BY` and aggregation.
- `HAVING` filters **groups**, after computing the corresponding aggregates.

### 11.1. WHERE: Considering Only PAID Orders

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_orders,
    SUM(net_amount) AS paid_amount
FROM agg_lab_151.orders
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

Here, groups are built only from the **five PAID orders**. Customer 2 has one PAID order, even though they have two orders total including one CANCELLED order.

### 11.2. HAVING: Keeping Only Groups with Two or More Orders

~~~sql
SELECT
    customer_id,
    COUNT(*) AS all_orders,
    SUM(net_amount) AS amount_sum
FROM agg_lab_151.orders
GROUP BY customer_id
HAVING COUNT(*) >= 2
ORDER BY customer_id;
~~~

The query keeps customers 1, 2, and 3; the guest group has only one order and is filtered out. `HAVING COUNT(*) >= 2` is a condition on the **group result** and cannot be directly replaced by `WHERE COUNT(*) >= 2`.

### 11.3. WHERE + HAVING

~~~sql
SELECT
    customer_id,
    COUNT(*) AS paid_order_count,
    SUM(net_amount) AS paid_amount
FROM agg_lab_151.orders
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(net_amount) >= 100000
ORDER BY customer_id NULLS LAST;
~~~

Only groups with a **PAID amount total of 100,000 or more** appear. Note clearly that `WHERE` removed non-PAID orders first, so `HAVING` does not include the `net_amount` of the CANCELLED order.

## 12. FILTER: Computing Multiple Conditional Metrics in One Query

PostgreSQL supports the syntax:

~~~sql
aggregate_function(...) FILTER (WHERE condition)
~~~

This allows an aggregate to see only rows matching a condition **without excluding those rows from other aggregates in the same query**.

### 12.1. Counting PAID, NEW, and CANCELLED Simultaneously

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'NEW')
        AS new_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELLED')
        AS cancelled_orders
FROM agg_lab_151.orders;
~~~

Result: `total_orders = 8`, `paid_orders = 5`, `new_orders = 2`, `cancelled_orders = 1`.

### 12.2. Aggregating Amounts and Missingness by Status

~~~sql
SELECT
    COUNT(*) AS all_orders,
    SUM(net_amount) FILTER (WHERE status = 'PAID')
        AS paid_amount,
    AVG(net_amount) FILTER (WHERE status = 'PAID')
        AS average_paid_amount,
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS missing_amount_orders,
    COUNT(*) FILTER (WHERE net_amount = 0)
        AS zero_amount_orders,
    COUNT(*) FILTER (
        WHERE status = 'PAID' AND net_amount IS NULL
    ) AS paid_but_amount_missing
FROM agg_lab_151.orders;
~~~

Result:

| Metric | Result |
| --- | ---: |
| All orders | 8 |
| Total PAID order amount | 620,000 |
| Average PAID order amount | 124,000 |
| Orders with `NULL` amount | 2 |
| Orders with amount equal to 0 | 1 |
| PAID orders with `NULL` amount | 0 |

`FILTER` is very well suited for dashboards needing multiple KPIs over the same dataset. **A `FILTER` condition affects only the aggregate it is attached to**, not the entire `SELECT` statement.

### 12.3. FILTER vs. WHERE

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders
FROM agg_lab_151.orders;
-- 8, 5
~~~

Compared to:

~~~sql
SELECT
    COUNT(*) AS orders_after_where,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_after_where
FROM agg_lab_151.orders
WHERE status = 'PAID';
-- 5, 5
~~~

In the second query, `WHERE` already filtered out all non-PAID orders before either aggregate ran. Therefore, that query cannot return the **total number of orders across the whole table**.

### 12.4. When No Rows Match FILTER

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'REFUNDED')
        AS refunded_count,
    SUM(net_amount) FILTER (WHERE status = 'REFUNDED')
        AS refunded_amount
FROM agg_lab_151.orders;
~~~

There are no `REFUNDED` rows in the dataset:

- `refunded_count = 0`.
- `refunded_amount = NULL`.

`FILTER` does not change `SUM`'s rule of returning `NULL` when there are no input values. If you want to display 0 in a report, you can wrap it in `COALESCE` when appropriate for the business rule.

## 13. LEFT JOIN and the COUNT(*) Trap

A common requirement: **list every customer, including customers who have not placed any orders**.

Starting from `customers` and `LEFT JOIN orders`, a customer without orders still appears as **one joined result row**, where the columns from `orders` are `NULL`.

### 13.1. COUNT(*) Is Wrong When Counting Each Customer's Orders

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

For customer 4, `COUNT(*) = 1` **even though the customer has no orders**. Reason: `LEFT JOIN` still produces a row to preserve the customer on the left side.

### 13.2. COUNT(o.order_id) Counts Actual Orders

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(*) AS joined_rows,
    COUNT(o.order_id) AS actual_orders,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID')
        AS paid_orders,
    COALESCE(
        SUM(o.net_amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS paid_amount_for_display
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Key results:

| Customer | `joined_rows` | `actual_orders` | `paid_orders` | `paid_amount_for_display` |
| --- | ---: | ---: | ---: | ---: |
| Nguyễn An | 3 | 3 | 1 | 120,000 |
| Trần Bình | 2 | 2 | 1 | 80,000 |
| Lê Chi | 2 | 2 | 2 | 300,000 |
| Phạm Dũng | 1 | **0** | **0** | 0 |

`order_id` is a `NOT NULL` primary key in the actual table. When there is no matching order, `o.order_id` in the **unmatched joined row** is `NULL`, so `COUNT(o.order_id) = 0`. In other `LEFT JOIN` scenarios, pick a column guaranteed to be **NOT NULL when a real record exists** as the presence indicator.

Here `COALESCE(SUM(...), 0)` is only for **display formatting**. To distinguish "no PAID orders" from "PAID orders whose sum is 0," also keep `paid_orders` and/or `COUNT(o.net_amount)`.

### 13.3. A WHERE Filter on the Right Table Can Drop Customers Without Orders

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name;
~~~

`WHERE o.status = 'PAID'` eliminates the joined row for any customer without orders because `o.status` is `NULL`, so the condition is not TRUE. As a result, the query **no longer lists every customer**.

To keep every customer and match only PAID orders, put the condition inside `ON`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM agg_lab_151.customers AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

Another option is to keep all orders in the `LEFT JOIN` and apply `FILTER (WHERE o.status = 'PAID')` to the corresponding aggregate.

### 13.4. One-to-Many JOINs Can Multiply Rows

If you later join `orders` with `order_items`, a single order with three line items will appear **three times** in the join output:

~~~text
orders 101 --- item A
           --- item B
           --- item C
~~~

In that case:

~~~sql
-- In such a JOIN result:
-- COUNT(*)                  may count 3 rows
-- COUNT(DISTINCT o.order_id) may count 1 order
-- SUM(o.net_amount)         may sum the order amount 3 times (WRONG)
~~~

Do not attempt to fix the inflated sum with `SUM(DISTINCT o.net_amount)`: two different orders can share the same amount. The right approach is usually to **aggregate to the proper grain before joining**, or compute order-level totals separately and then join the properly grouped metrics.

## 14. COALESCE: When Should NULL Be Replaced with 0?

`COALESCE(value, default)` returns the first non-`NULL` value. It is often wrapped around aggregates:

~~~sql
SELECT
    SUM(net_amount) AS nullable_sum,
    COALESCE(SUM(net_amount), 0::numeric)
        AS sum_for_display
FROM agg_lab_151.orders
WHERE order_id < 0;
~~~

On an empty row set:

- `nullable_sum = NULL`.
- `sum_for_display = 0`.

However, you must distinguish between two placements of `COALESCE`.

### 14.1. COALESCE Inside vs. Outside SUM

~~~sql
SELECT
    SUM(COALESCE(net_amount, 0))
        AS sum_after_replacing_each_missing_value,
    COALESCE(SUM(net_amount), 0::numeric)
        AS default_after_aggregate
FROM agg_lab_151.orders;
~~~

On a dataset containing valid rows, both may produce the same sum of **820,000**. Yet they are **not completely equivalent**:

- `SUM(COALESCE(x, 0))` turns each missing value into 0 before summing.
- `COALESCE(SUM(x), 0)` lets `SUM` ignore missing values and only replaces the aggregate result if it is `NULL`.

Specifically, on an **empty set with no rows**, `SUM(COALESCE(x,0))` still returns `NULL`: there are no rows to generate a 0. Only `COALESCE(SUM(x),0)` guarantees returning 0 at the aggregate result level.

### 14.2. COALESCE Inside AVG Changes the Denominator

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(net_amount) AS known_orders,
    AVG(net_amount) AS avg_known_amount,
    AVG(COALESCE(net_amount, 0))
        AS avg_missing_as_zero
FROM agg_lab_151.orders;
~~~

This is not merely cosmetic display formatting: it changes **the definition of the metric**. If `NULL` means "amount not yet recorded," an average treating missing values as 0 can hide data entry bugs or understate order values.

### 14.3. When to Keep NULL?

Keep `NULL` when:

- There are no observations to compute an average.
- A fee or amount is unknown and must not default to 0.
- There is no valid denominator for a ratio.
- You need to distinguish "no data" from "confirmed zero."

Replacing with 0 can be appropriate when:

- Business rules define **no transactions = zero total** for reporting purposes.
- An optional column genuinely means "no charge incurred" under a clear data contract.
- The UI requires showing 0 and users also see a `sample_count` metric to interpret the data.

Rule of thumb: **substitute at the right level with the right semantics—never treat every NULL as 0 by default**.

## 15. NULL, Arithmetic, and Aggregating Expressions

Not only the aggregate itself, **the input expression** to the aggregate also shapes the result.

### 15.1. SUM(net_amount + shipping_fee)

~~~sql
SELECT
    SUM(net_amount + shipping_fee)
        AS sum_when_both_fields_known,
    COUNT(net_amount + shipping_fee)
        AS rows_with_both_fields_known
FROM agg_lab_151.orders;
~~~

Because `a + NULL` yields `NULL`, the expression `net_amount + shipping_fee` is non-`NULL` only when both components are present. Those orders are 101, 103, 105, and 107:

~~~text
101: 120000 + 15000 = 135000
103:  80000 +     0 =  80000
105:      0 + 10000 =  10000
107: 120000 +  5000 = 125000
--------------------------------
Total                  = 350000
~~~

Thus `SUM(net_amount + shipping_fee) = 350000` and `COUNT(net_amount + shipping_fee) = 4`.

Do not treat `350000` as the grand total across **all orders**, because orders with `NULL` shipping fees were excluded from the addition.

### 15.2. SUM(COALESCE(net_amount,0) + COALESCE(shipping_fee,0))

~~~sql
SELECT
    SUM(
        COALESCE(net_amount, 0)
        + COALESCE(shipping_fee, 0)
    ) AS estimated_total_with_missing_as_zero
FROM agg_lab_151.orders;
~~~

The sum of known `net_amount` is **820,000**; the known shipping fees are **15,000 + 0 + 10,000 + 5,000 = 30,000**. If missing values are treated as 0 by convention, the estimated total is **850,000**.

Compared to Section 15.1, the difference comes from the **NULL-handling policy**, not a bug in `SUM`. If shipping fees are undetermined, this estimated total may not reflect the final payable amount.

### 15.3. Using CASE/FILTER to Select Rows to Sum

~~~sql
SELECT
    SUM(
        CASE
            WHEN status = 'PAID' THEN net_amount
            ELSE 0::numeric
        END
    ) AS paid_amount_by_case,
    SUM(net_amount) FILTER (WHERE status = 'PAID')
        AS paid_amount_by_filter
FROM agg_lab_151.orders;
~~~

On this dataset, both return **620000**. However, for a group with no PAID orders:

- `SUM(CASE WHEN ... THEN value ELSE 0 END)` can return 0 **if the group still contains rows that fail the condition**.
- `SUM(value) FILTER (WHERE ...)` returns `NULL` when no values are selected.

To consistently display 0 for a summed KPI after aggregation, write explicitly:

~~~sql
COALESCE(
    SUM(net_amount) FILTER (WHERE status = 'PAID'),
    0::numeric
)
~~~

Neither variant is universally "more correct"; what matters is stating the **policy for empty sets and missing data**.

## 16. COUNT, SUM, AVG, and Percentages

A percentage has the general form:

\[
\text{Percentage (\%)} =
\frac{\text{Qualifying items}}
{\text{Items in sample}} \times 100
\]

You must identify the exact **numerator** and **denominator**.

### 16.1. Percentage of PAID Orders Out of All Orders

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percentage
FROM agg_lab_151.orders;
~~~

Result: `5/8 × 100 = 62.50%`.

`NULLIF(COUNT(*), 0)` converts a zero denominator into `NULL`. On an empty table, the percentage becomes `NULL` instead of raising a division-by-zero error.

### 16.2. Percentage of Orders with a Known Amount

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(net_amount) AS orders_with_amount,
    ROUND(
        100.0 * COUNT(net_amount)
        / NULLIF(COUNT(*), 0),
        2
    ) AS amount_completeness_percentage
FROM agg_lab_151.orders;
~~~

With the sample data: `6/8 × 100 = 75.00%`.

This is a **data completeness** metric, not a payment rate. Using the same aggregate functions while picking the wrong expression to count produces a KPI with a completely different meaning.

### 16.3. Percentage of Rated Orders

~~~sql
SELECT
    COUNT(rating) AS rated_orders,
    COUNT(*) AS total_orders,
    ROUND(
        100.0 * COUNT(rating)
        / NULLIF(COUNT(*), 0),
        2
    ) AS rating_coverage_percentage,
    AVG(rating) AS average_rating
FROM agg_lab_151.orders;
~~~

Result:

- **3/8 orders** were rated → **37.50%**.
- Average score **4.0** among **rated** orders.

Both KPIs should be presented together. Stating only "average rating 4/5" without reporting the sample size of 3 and 37.5% coverage can mislead readers about how representative the score is.

### 16.4. COUNT(*) Returns bigint: Avoiding Integer Division

If you divide integers using integer division, the fractional part can be truncated. Cast explicitly to a decimal type:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'PAID')::numeric
    / NULLIF(COUNT(*), 0)
    AS paid_ratio
FROM agg_lab_151.orders;
-- 0.625
~~~

Or multiply by `100.0` as in Section 16.1 to compute percentages. To control decimal places:

~~~sql
ROUND(numeric_expression, 2)
~~~

In PostgreSQL, the two-argument `round(value, scale)` function generally applies to `numeric`; if the expression is a floating-point type, an appropriate cast may be required.

## 17. Data Types of Aggregate Results

Inputs and outputs of aggregate functions do not necessarily share the same type. This is a practical issue when creating views, APIs, and using JDBC.

| Function and Input | Common PostgreSQL Result Type |
| --- | --- |
| `COUNT(*)` or `COUNT(expression)` | `bigint` |
| `SUM(smallint)` / `SUM(integer)` | `bigint` |
| `SUM(bigint)` | `numeric` |
| `SUM(numeric)` | `numeric` |
| `AVG(smallint/integer/bigint/numeric)` | `numeric` |
| `SUM(real)` | `real` |
| `SUM(double precision)` | `double precision` |
| `AVG(real/double precision)` | `double precision` |
| `MIN(x)` / `MAX(x)` | Usually the same comparable type as `x` |

The exact type depends on the aggregate function and the input types supported by PostgreSQL. You can inspect it directly:

~~~sql
SELECT
    pg_typeof(COUNT(*)) AS count_type,
    pg_typeof(SUM(1::integer)) AS sum_integer_type,
    pg_typeof(SUM(1::bigint)) AS sum_bigint_type,
    pg_typeof(AVG(1::integer)) AS avg_integer_type,
    pg_typeof(SUM(net_amount)) AS amount_sum_type
FROM agg_lab_151.orders;
~~~

### 17.1. AVG(integer) Is Not Just an integer

~~~sql
SELECT
    AVG(x) AS average_value,
    pg_typeof(AVG(x)) AS result_type
FROM (
    VALUES (1::integer), (2::integer)
) AS v(x);
~~~

The average is **1.5**, not 1. PostgreSQL returns `numeric` for `AVG(integer)`, preserving the fractional part in this calculation.

### 17.2. NUMERIC and Floating Point

`NUMERIC` is typically chosen for monetary values requiring exact decimal precision. Types like `real`/`double precision` use binary floating point, which can introduce representation rounding errors and slight discrepancies in `SUM`/`AVG` results, especially when summation order varies.

~~~sql
SELECT
    SUM(x) AS decimal_sum
FROM (
    VALUES (0.1::numeric), (0.2::numeric)
) AS v(x);
-- 0.3
~~~

For currency, do not switch to `double precision` solely for speed if the business requires exactness down to the smallest monetary unit. Conversely, scientific measurements may suit floating point; understand your type choices.

### 17.3. Avoid Downcasting Results to Narrow Ranges

`COUNT(*)` returns `bigint` because row counts can grow very large. `SUM(integer)` returns `bigint` to reduce overflow risk compared to summing within `integer`. Every numeric type still has bounds; if you cast a large sum down to `integer`, the cast can fail or violate application requirements.

In Java/JDBC, the receiver type should match the schema and aggregate: e.g., `getLong` for counts and `BigDecimal` for `NUMERIC` values. When `NULL` must be distinguished in results, do not read a primitive and ignore `wasNull()`.

## 18. NULL in Conditions and Three-Valued Logic

`NULL` is neither 0 nor an empty string. Standard comparisons against `NULL` evaluate to **UNKNOWN**:

~~~sql
SELECT
    NULL::numeric = 0 AS null_equals_zero,
    NULL::numeric = NULL::numeric AS null_equals_null,
    NULL::numeric IS NULL AS is_null_result;
~~~

The first two columns evaluate to `NULL`/UNKNOWN, and the third evaluates to `TRUE`.

To select orders missing an amount:

~~~sql
SELECT order_id
FROM agg_lab_151.orders
WHERE net_amount IS NULL
ORDER BY order_id;
-- 102, 108
~~~

Do not use:

~~~sql
-- Wrong intent:
-- WHERE net_amount = NULL
~~~

### 18.1. Counting Zeros and Counting NULLs Are Two Separate Checks

~~~sql
SELECT
    COUNT(*) FILTER (WHERE net_amount = 0)
        AS known_zero_amounts,
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS unknown_amounts
FROM agg_lab_151.orders;
-- 1, 2
~~~

This is essential for data quality checks: **free orders** and **orders with an unknown amount** must not be collapsed into the same business state.

### 18.2. GROUP BY and NULL

In `GROUP BY`, rows sharing a `NULL` grouping key are gathered into **one group**. However, `COUNT(customer_id)` on that group is 0 because the values of the counted column itself are `NULL`:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS rows_in_group,
    COUNT(customer_id) AS non_null_customer_ids
FROM agg_lab_151.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

The guest group has `rows_in_group = 1` and `non_null_customer_ids = 0`. Those are two different questions, not a PostgreSQL bug.

## 19. Daily Aggregation and Generating Dates Without Orders

A report may need **every day in a period**, including days with zero orders. If you only run `GROUP BY order_date` on the orders table, days without orders **do not appear**.

### 19.1. Aggregating Days with Orders

~~~sql
SELECT
    order_date,
    COUNT(*) AS order_count,
    COALESCE(
        SUM(net_amount) FILTER (WHERE status = 'PAID'),
        0::numeric
    ) AS paid_amount
FROM agg_lab_151.orders
GROUP BY order_date
ORDER BY order_date;
~~~

The output only includes dates from `2026-11-01` through `2026-11-05` that have orders in the data.

### 19.2. Using generate_series for Every Day in the Period

~~~sql
WITH calendar AS (
    SELECT day_point::date AS report_date
    FROM generate_series(
        TIMESTAMP '2026-11-01 00:00:00',
        TIMESTAMP '2026-11-07 00:00:00',
        INTERVAL '1 day'
    ) AS g(day_point)
)
SELECT
    c.report_date,
    COUNT(o.order_id) AS order_count,
    COALESCE(
        SUM(o.net_amount) FILTER (WHERE o.status = 'PAID'),
        0::numeric
    ) AS paid_amount
FROM calendar AS c
LEFT JOIN agg_lab_151.orders AS o
    ON o.order_date = c.report_date
GROUP BY c.report_date
ORDER BY c.report_date;
~~~

Nov 06 and Nov 07 have no orders yet still appear with `order_count = 0`. Use `COUNT(o.order_id)` instead of `COUNT(*)` because each zero-order day still produces one row from the `LEFT JOIN` preserving the calendar date.

Note: `generate_series` here generates **calendar dates** from timezone-naive timestamps. If reporting by local date on `TIMESTAMPTZ` events across regions, establish the proper time zone and day boundaries before grouping.

## 20. Window Aggregates: Aggregating While Keeping Every Row

`GROUP BY` collapses multiple rows into one row per group. **Window functions** can compute aggregates per group while **preserving the detail rows**:

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    net_amount,
    COUNT(*) OVER (
        PARTITION BY customer_id
    ) AS orders_of_customer_group,
    SUM(net_amount) OVER (
        PARTITION BY customer_id
    ) AS known_amount_sum_of_group
FROM agg_lab_151.orders
ORDER BY customer_id NULLS LAST, order_id;
~~~

For example, orders 101, 102, and 108 all have `customer_id=1`, so all three display `orders_of_customer_group=3`, and the known amount sum in the group is 120,000.

This uses an aggregate with `OVER (...)`, unlike a regular `GROUP BY` query. For a group with no valid amount values, `SUM` inside a window can also return `NULL`.

### 20.1. AVG OVER and Denominator Meaning

~~~sql
SELECT
    order_id,
    status,
    net_amount,
    AVG(net_amount) OVER (
        PARTITION BY status
    ) AS average_amount_for_status
FROM agg_lab_151.orders
ORDER BY status, order_id;
~~~

The two `NEW` orders still appear, but `average_amount_for_status` is `NULL` because **both net_amount values are NULL**. All `PAID` orders display a group average of 124,000.

Window functions are a deeper topic; this lesson uses them to emphasize that **aggregate NULL rules do not change just because OVER is used**.

## 21. Performance Considerations in Aggregation

### 21.1. COUNT(*) Is Not Always Instantaneous

PostgreSQL uses MVCC (*multi-version concurrency control*). The number of **visible** rows can depend on the transaction snapshot, so PostgreSQL cannot always pull an immutable exact row count from metadata without checking visibility.

~~~sql
SELECT COUNT(*) FROM agg_lab_151.orders;
~~~

On very large tables, the query may need to scan a significant amount of data. PostgreSQL may choose a sequential scan, an index-only scan under suitable conditions, or a parallel plan depending on workload and configuration. **There is no guarantee that `COUNT(*)` is always O(1)** or always faster than other queries just because it returns no columns.

### 21.2. Estimated Row Counts vs. Exact COUNT(*)

~~~sql
SELECT
    relname,
    reltuples AS estimated_rows
FROM pg_catalog.pg_class
WHERE oid = 'agg_lab_151.orders'::regclass;
~~~

`reltuples` is a **statistical estimate** used internally by PostgreSQL and can be stale, especially on new tables or after heavy writes. It cannot replace `COUNT(*)` when business logic requires an exact count.

### 21.3. WHERE Can Reduce Data Volume

~~~sql
SELECT SUM(net_amount)
FROM agg_lab_151.orders
WHERE status = 'PAID';
~~~

On large tables, indexes aligned with filters/grouping conditions can reduce the amount of data examined. However, adding an index does not automatically make an aggregate query fast; it still depends on selectivity, pages read, data visibility, parallelism, and the execution plan.

Always measure with:

~~~sql
EXPLAIN
SELECT
    status,
    COUNT(*),
    SUM(net_amount)
FROM agg_lab_151.orders
GROUP BY status;
~~~

`EXPLAIN` without `ANALYZE` only generates the plan without running the query for actual timings; `EXPLAIN (ANALYZE, BUFFERS)` actually executes the query, so use it only when you understand the cost and target environment.

### 21.4. GROUP BY, DISTINCT, and Memory

Depending on the plan, PostgreSQL may use operations such as **HashAggregate**, **GroupAggregate**, and sort/hash steps. `COUNT(DISTINCT ...)` may have to process unique value sets separately, incurring significant cost when cardinality is high.

Do not add `DISTINCT` to `SUM` or `AVG` assuming it optimizes the query or generally deduplicates rows. `DISTINCT` **changes the semantics** and can make the query more resource-intensive.

### 21.5. Aggregate Before Joining Across Different Grains

If one table has one row per **order** and another has one row per **line item**, a JOIN can duplicate the order's amount column. Before computing:

~~~sql
SUM(order_amount)
~~~

verify whether one input row represents an **order, line item, payment transaction, or customer**. The data grain must match the grain of the metric being aggregated.

## 22. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `COUNT(net_amount)` to count all orders | Skips orders with NULL amount | Use `COUNT(*)` when counting rows |
| Using `COUNT(*)` after `LEFT JOIN` to count right-side records | Counts 1 even with no matching record | Use `COUNT(o.order_id)` on a non-NULL key |
| Treating `NULL` as 0 | Distorts financial/data-quality reports | Distinguish missing values from known 0s |
| Assuming `SUM` on an empty set returns 0 | API/dashboard receives unexpected NULL | Use `COALESCE(SUM(...),0)` when allowed by policy |
| Using `AVG(COALESCE(x,0))` without thought | Changes denominator, skews average | Use `AVG(x)` when averaging only observed values |
| Reporting `AVG(rating)` without `COUNT(rating)` | Sample size is unknown | Return sample count and coverage alongside it |
| Taking `SUM` across all statuses as revenue | Includes cancelled/unpaid orders | Filter by clear recognition rules |
| Using `SUM(DISTINCT amount)` to "deduplicate orders" | Drops distinct orders sharing the same amount | Deduplicate by order key, fix the JOIN |
| Writing `COUNT(CASE WHEN cond THEN 1 ELSE 0 END)` | Counts rows returning ELSE 0 too | Use `COUNT(*) FILTER` or `SUM(CASE... ELSE 0 END)` |
| Using `WHERE aggregate(...)` | Wrong evaluation stage | Use `HAVING` |
| Putting right-table filter in `WHERE` of a LEFT JOIN | Drops unmatched rows | Move condition into `ON` or `FILTER` |
| Using `= NULL` in WHERE | Condition never evaluates to TRUE | Use `IS NULL` |
| Using `COUNT(DISTINCT customer_id)` to count all customers | Misses customers without orders and NULLs | Count from the customers table if all are needed |
| Counting `NULL`s with `COUNT(column)` | Returns the non-NULL count instead | Use `COUNT(*) FILTER (WHERE column IS NULL)` |
| Fetching MIN/MAX then selecting an arbitrary column | Fails to identify the min/max record | Use a subquery / `ORDER BY` and handle ties |
| Integer division for percentages | May truncate fractional part | Use `100.0` or cast to `numeric` |
| Assuming `COUNT(*)` is always as fast as reading metadata | Slow on large tables | Check the plan and exact vs. estimated needs |
| Ignoring row multiplication from JOINs | `SUM` is multiplied multiple times | Aggregate at the proper grain before joining |
| Confusing single-row `COUNT=0` with 0-row `GROUP BY` | UI/logic misinterprets empty state | Design clear result contracts |

## 23. Practice Exercises

### Exercise 1 — COUNT(*) vs. COUNT(column)

Query simultaneously:

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(customer_id) AS known_customers_in_orders,
    COUNT(net_amount) AS known_amount_rows,
    COUNT(shipping_fee) AS known_shipping_rows,
    COUNT(rating) AS rated_rows
FROM agg_lab_151.orders;
~~~

**Answer:** `8, 7, 6, 4, 3`.

Explain why `COUNT(net_amount)` includes the order with a 0 amount while excluding orders with `NULL` amounts.

### Exercise 2 — SUM and AVG

Compute `SUM(net_amount)` and `AVG(net_amount)` across all orders. Then compute them specifically for `status='PAID'`.

**Suggested answer:**

- All orders: sum `820000`; average approx. `136666.67` across six values.
- PAID orders: sum `620000`; average `124000` across five orders.

Why shouldn't `820000` be called paid revenue?

### Exercise 3 — MIN/MAX and Extremum Rows

Find `MIN(net_amount)`, `MAX(net_amount)`, and then write a query displaying **all orders** matching `MAX(net_amount)`.

**Answer:** min `0`, max `300000`, the order matching max in the dataset is `106`.

### Exercise 4 — Empty Row Set

Run:

~~~sql
SELECT
    COUNT(*), SUM(net_amount), AVG(net_amount),
    MIN(net_amount), MAX(net_amount)
FROM agg_lab_151.orders
WHERE order_date < DATE '2000-01-01';
~~~

**Question:** How many result rows are returned? What does `COUNT(*)` return? What do the remaining aggregates return?

**Answer:** one row; COUNT = 0; SUM/AVG/MIN/MAX = `NULL`.

### Exercise 5 — Rows Exist, All Amounts Are NULL

Filter only `NEW` orders and compute `COUNT(*)`, `COUNT(net_amount)`, and `SUM(net_amount)`.

**Answer:** `2`, `0`, `NULL`. Explain why this differs from having no rows in Section 8.1.

### Exercise 6 — COUNT(DISTINCT)

Find:

~~~sql
SELECT
    COUNT(customer_id) AS with_customer,
    COUNT(DISTINCT customer_id) AS unique_customers,
    COUNT(DISTINCT net_amount) AS unique_amount_values
FROM agg_lab_151.orders;
~~~

**Answer:** `7, 3, 5`. Are customers without orders counted? Are two orders with the same amount treated as one order?

### Exercise 7 — Why Is SUM(DISTINCT amount) Wrong for Revenue?

Compare `SUM(net_amount)` and `SUM(DISTINCT net_amount)`. Explain that the amount **120000** appeared twice in two separate orders and must be added twice when computing the order total.

**Answer:** `820000` vs. `700000`; difference `120000`.

### Exercise 8 — GROUP BY Status

Write a report:

~~~text
status | total_orders | known_amounts | amount_sum | amount_avg
~~~

From the `orders` table. For `NEW`, `total_orders` must be 2, `known_amounts` equals 0, and both `amount_sum` and `amount_avg` are `NULL`.

### Exercise 9 — HAVING After GROUP BY

List `customer_id`s with at least two orders. The query must use `GROUP BY` and `HAVING COUNT(*) >= 2`.

**Answer:** customer groups `1`, `2`, and `3`.

### Exercise 10 — COUNT After LEFT JOIN

List **every customer**, including customer `4` who has no orders, alongside `COUNT(*)` and `COUNT(o.order_id)`. Explain why for customer 4 the two values are `1` and `0` respectively.

### Exercise 11 — FILTER and Data Quality Metrics

Write a single `SELECT` returning:

~~~text
all_orders
paid_orders
new_orders
cancelled_orders
amount_missing
zero_amount_orders
paid_amount
average_paid_amount
~~~

Use `FILTER (WHERE ...)` for the conditional metrics. **Answer:** `8`, `5`, `2`, `1`, `2`, `1`, `620000`, `124000`.

### Exercise 12 — Ratios and Denominators

Compute:

- Percentage of PAID orders out of all orders.
- Percentage of orders with a known `net_amount`.
- Percentage of orders with a `rating`.

**Answer:** `62.50%`, `75.00%`, `37.50%`.

Why do all three share a denominator of 8 while having different numerators? If the table is empty, should the ratios return `NULL` or 0?

### Exercise 13 — AVG with Missing Data

Compare:

~~~sql
SELECT
    AVG(net_amount) AS average_known,
    AVG(COALESCE(net_amount, 0)) AS missing_as_zero,
    COUNT(net_amount) AS known_count,
    COUNT(*) AS total_count
FROM agg_lab_151.orders;
~~~

**Answer:** approx. `136666.67`, `102500`, `6`, and `8`. State a business rule that makes each calculation appropriate.

### Exercise 14 — Incorrect COUNT(CASE ...)

Consider:

~~~sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS incorrect_paid_count,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END)
        AS correct_paid_count,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS filter_paid_count
FROM agg_lab_151.orders;
~~~

**Answer:** `8`, `5`, `5`. Why does `COUNT` include the 0s?

### Exercise 15 — Report Including Days Without Orders

Use `generate_series` to build a date list from 2026-11-01 to 2026-11-07, `LEFT JOIN` the orders table, and count orders per day. The last two days must show `0`, **not disappear** from the report.

### Exercise 16 — Avoiding Revenue Multiplication After a JOIN

Suppose a 120,000 order has three line items; joining the orders table with order details produces three rows. What will `SUM(order_amount)` after the JOIN produce? Why is `SUM(DISTINCT order_amount)` not a general solution? Describe how to aggregate at the proper grain before joining.

### Exercise 17 — Returning Data to a Java Application

An API wants to return:

~~~text
total_orders: integer
total_paid_amount: decimal | null
avg_rating: decimal | null
rated_orders: integer
~~~

Decide the appropriate JDBC receiver types for `COUNT` and `NUMERIC`, how to represent `NULL`, and whether `avg_rating` should always be replaced with 0. Explain why "no rating yet" differs from "a rating score of 0."

## 24. Complete Aggregate Query Template for a Dashboard

A simple dashboard often needs **counts**, **sums**, **averages**, **data coverage**, and **extrema**. Multiple KPIs can be returned in a single query:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'NEW')
        AS new_orders,
    COUNT(*) FILTER (WHERE status = 'CANCELLED')
        AS cancelled_orders,
    COUNT(*) FILTER (WHERE net_amount IS NULL)
        AS missing_amount_orders,
    COUNT(*) FILTER (WHERE net_amount = 0)
        AS zero_amount_orders,
    COUNT(net_amount) AS known_amount_orders,
    SUM(net_amount) AS all_known_amount_sum,
    COALESCE(
        SUM(net_amount) FILTER (WHERE status = 'PAID'),
        0::numeric
    ) AS paid_amount_for_display,
    AVG(net_amount) FILTER (WHERE status = 'PAID')
        AS average_paid_amount,
    MIN(net_amount) AS minimum_known_amount,
    MAX(net_amount) AS maximum_known_amount,
    COUNT(rating) AS rated_orders,
    AVG(rating) AS average_rating,
    ROUND(
        100.0
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percentage
FROM agg_lab_151.orders;
~~~

The result from the seed data is:

| KPI | Value |
| --- | ---: |
| Total orders | 8 |
| PAID orders | 5 |
| NEW orders | 2 |
| CANCELLED orders | 1 |
| Orders missing amount | 2 |
| Orders with amount 0 | 1 |
| Orders with known amount | 6 |
| Sum of known amounts across all statuses | 820,000 |
| Total amount of PAID orders | 620,000 |
| Average PAID order amount | 124,000 |
| Minimum known amount | 0 |
| Maximum known amount | 300,000 |
| Rated orders | 3 |
| Average score from rated orders | 4 |
| PAID order percentage | 62.50% |

**Real-world reports should include KPI definitions.** Specifically, "total PAID amount" is the sum of `net_amount` for rows with `status = 'PAID'`, without accounting adjustments; "average PAID order amount" divides only across PAID rows with a non-NULL amount; "average rating" includes only rated orders.

### 24.1. Why Return COUNT and AVG Together?

A single average metric can be over-interpreted. For example:

~~~text
average_rating = 4.0
rated_orders   = 3
total_orders   = 8
~~~

Together, these three numbers show that the average score is fairly high, yet only three orders have been rated. Small coverage does not reliably reflect the experience of all buyers. Therefore, **value** KPIs and **completeness/denominator** KPIs should travel together.

## 25. PostgreSQL Reference Documentation

To verify behavior for your PostgreSQL major version:

- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html): `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, result types, and empty-set handling.
- [Aggregate Expressions](https://www.postgresql.org/docs/current/sql-expressions.html#SYNTAX-AGGREGATES): `DISTINCT`, `FILTER`, and aggregate expression usage.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `WHERE`, `GROUP BY`, `HAVING`, and conceptual processing order.
- [Conditional Expressions](https://www.postgresql.org/docs/current/functions-conditional.html): `CASE`, `COALESCE`, `NULLIF`.
- [Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): comparisons and `NULL` checks.
- [Window Functions](https://www.postgresql.org/docs/current/functions-window.html): aggregates used with `OVER` and `PARTITION BY`.

The `/docs/current/` path points to the documentation for the current stable release. If you are using PostgreSQL 14, 15, 16, or another specific version, consult the documentation for that version.

## 26. Summary

The five functions `COUNT`, `SUM`, `AVG`, `MIN`, and `MAX` form the foundation of aggregate queries in PostgreSQL. **`COUNT(*)` counts rows**, while **`COUNT(expression)` counts non-`NULL` values**. `SUM`, `AVG`, `MIN`, and `MAX` ignore `NULL` values; when no qualifying values exist, they typically return `NULL` rather than **automatically converting to 0**. For `AVG`, the denominator is the count of non-NULL values, so replacing `NULL` with 0 beforehand changes the statistical meaning.

`GROUP BY` produces results per group; `WHERE` filters rows before aggregation; `HAVING` filters groups after aggregation; `FILTER` lets you compute multiple conditional KPIs simultaneously. `DISTINCT` removes only **duplicate values**, not duplicate business transactions. With `LEFT JOIN`, use `COUNT(non_NULL_key_of_right_table)` when counting actual matched records on the right side to avoid counting the placeholder row generated by LEFT JOIN.

When applying these in reporting, always clarify **input data grain, row scope, `NULL` semantics, statistical denominators, and empty-result display policies**. Those decisions matter just as much as SQL syntax: they ensure the query returns **the right number for the business question**, rather than a plausible-looking number with the wrong meaning.
