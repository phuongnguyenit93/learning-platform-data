# WINDOW and Reusing Window Definitions in PostgreSQL

When analyzing orders, you often want to display **individual orders** while simultaneously showing: which sequential order this is for the customer, the previous order's amount, cumulative spend, the customer's lifetime total, and the three-order moving average. These calculations share the same **customer** scope and usually the same **order timestamp** sequence, yet differ in function and sometimes in **window frame**.

Repeating `OVER (PARTITION BY customer_id ORDER BY ordered_at, order_id)` across many columns makes SQL verbose, hard to read, and prone to inconsistent definitions. PostgreSQL lets you declare **named windows** via the **`WINDOW`** clause and reuse them across window functions.

Example:

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    amount,
    ROW_NUMBER() OVER w_chrono AS order_sequence,
    LAG(amount) OVER w_chrono AS previous_amount,
    SUM(amount) OVER w_running AS cumulative_amount
FROM sales_orders
WINDOW
    w_chrono AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    );
~~~

`w_chrono` defines **partitioning and ordering**. `w_running` reuses that definition and appends a cumulative frame. This creates no persistent table or view: window names exist strictly within the **scope of the `SELECT` statement**.

This lesson covers complete `WINDOW` syntax, `OVER` forms, inheritance mechanics, `PARTITION BY`, `ORDER BY`, `ROWS`/`RANGE`/`GROUPS`, peer row handling, ranking functions, `LAG`/`LEAD`, `FIRST_VALUE`/`LAST_VALUE`, conditional aggregates, combining with `GROUP BY`, syntax pitfalls, and reading `EXPLAIN`. Examples use modern PostgreSQL and a consistent dataset.

## 1. How do window functions differ from GROUP BY?

Standard aggregate functions collapse multiple rows into one result row per group:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM sales_orders
GROUP BY customer_id;
~~~

If customer 1 has four orders, `GROUP BY customer_id` returns just **one summary row** for customer 1.

Window functions still calculate across rows in the same group while **preserving source rows**:

~~~sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_total
FROM sales_orders;
~~~

On every order belonging to customer 1, `customer_total` displays customer 1's total.

~~~text
                 Order rows
                     |
           +---------+----------+
           |                    |
        GROUP BY               OVER
           |                    |
     One row per group    Keep each input row
           |                    |
   total_amount/customer  total_amount on each order
~~~

**`WINDOW` does not introduce a different analytical model.** It simply lets you **name and reuse window specifications** for functions invoked with `OVER`.

### 1.1. Structure of a window function

~~~sql
function_name(arguments) OVER (
    PARTITION BY group_columns
    ORDER BY sort_columns
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

Each of the three components plays its own role:

| Component | Question answered |
| --- | --- |
| `PARTITION BY` | Which rows belong to the **same analytical group**? |
| `ORDER BY` inside `OVER` | In **what order** are rows within a group arranged for calculation? |
| Frame `ROWS/RANGE/GROUPS` | At the **current row**, which rows inside the partition enter frame-dependent calculations? |

Not all functions depend on the frame identically. `ROW_NUMBER`, `RANK`, `LAG`, and `LEAD` use partition and ordering; aggregates like `SUM` and `AVG`, plus `FIRST_VALUE`, `LAST_VALUE`, and `NTH_VALUE`, require careful attention to the **frame**.

## 2. Why name a window?

Suppose you need:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS sequence_no,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_amount,
    LEAD(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS next_amount
FROM sales_orders;
~~~

`PARTITION BY` and `ORDER BY` are repeated three times. While valid, adding a tie-breaker `order_id` or changing date order requires updating multiple places.

Declaring `WINDOW`:

~~~sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER w_customer_time AS sequence_no,
    LAG(amount) OVER w_customer_time AS previous_amount,
    LEAD(amount) OVER w_customer_time AS next_amount
FROM sales_orders
WINDOW w_customer_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
);
~~~

Benefits:

1. **Readability:** readers see immediately that all three functions follow the same chronological per-customer sequence.
2. **Less repetition:** partition and sort specifications live in one place.
3. **Fewer discrepancies:** avoids accidentally sorting `ordered_at DESC` in one function and `ASC` in another.
4. **Inheritance support:** you can define a base window and derive windows with different frames.
5. **Clear intent:** names like `w_customer_time` or `w_running` communicate analytical purpose.

Note that `WINDOW` **does not guarantee a faster query** than writing inline `OVER (...)`. PostgreSQL optimizes according to window requirements and execution plans; the primary benefit of naming is **maintainability and consistency**.

## 3. WINDOW syntax and placement in SELECT

General form:

~~~sql
SELECT
    expression_1,
    aggregate_or_window_function(...) OVER window_name
FROM some_table
WHERE row_condition
GROUP BY grouping_columns
HAVING group_condition
WINDOW
    window_name AS (
        PARTITION BY ...
        ORDER BY ...
        frame_clause
    )
ORDER BY output_sort
LIMIT output_limit;
~~~

`WHERE`, `GROUP BY`, `HAVING`, and `LIMIT` are optional. In **syntactic order**, `WINDOW` appears **after `HAVING` (if present)** and **before the outermost `SELECT`'s `ORDER BY`**.

Concrete definition:

~~~sql
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
~~~

Usage:

~~~sql
ROW_NUMBER() OVER w
~~~

### 3.1. Declaring multiple windows

~~~sql
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_chrono AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_channel AS (PARTITION BY channel);
~~~

Definitions are comma-separated. Each function picks its matching window by name.

### 3.2. Names are scoped to the SELECT statement

`w_customer` **is not saved** as a schema or table object. To reuse the same rules in another `SELECT`, redeclare `WINDOW` in that `SELECT` or encapsulate the logic in an appropriate view/query.

For example, a window name inside an inner CTE **is not automatically visible** to the outer `SELECT`:

~~~sql
WITH src AS (
    SELECT
        order_id,
        ROW_NUMBER() OVER w AS rn
    FROM sales_orders
    WINDOW w AS (ORDER BY order_id)
)
SELECT order_id, rn
FROM src;
~~~

The `src` CTE outputs **result columns** `order_id` and `rn`; it does not export a window object `w` for the outer `SELECT` to reference.

## 4. Creating lab data used throughout the lesson

The statements below target a **PostgreSQL practice database**. Do not run `CREATE SCHEMA` or data-modifying statements on production databases.

### 4.1. Creating the schema and tables

~~~sql
CREATE SCHEMA window_lab;

CREATE TABLE window_lab.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL
);

CREATE TABLE window_lab.sales_orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES window_lab.customers(customer_id),
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    channel text NOT NULL
);
~~~

### 4.2. Inserting four customers

~~~sql
INSERT INTO window_lab.customers (customer_id, customer_name)
VALUES
    (1, 'Lan'),
    (2, 'Minh'),
    (3, 'Chi'),
    (4, 'Dung');
~~~

Customer `Dung` has no orders yet so we can discuss preserving empty groups with `LEFT JOIN`. Examples on `sales_orders` involve only customers 1, 2, and 3.

### 4.3. Inserting ten sales orders

~~~sql
INSERT INTO window_lab.sales_orders (
    order_id, customer_id, ordered_at,
    status, amount, channel
) VALUES
    (1001, 1, '2026-01-05 09:00:00+07', 'paid',      120.00, 'web'),
    (1002, 1, '2026-01-07 09:00:00+07', 'paid',       80.00, 'web'),
    (1003, 1, '2026-01-07 09:00:00+07', 'pending',    50.00, 'store'),
    (1004, 1, '2026-01-10 15:00:00+07', 'paid',      200.00, 'web'),
    (2001, 2, '2026-01-06 08:00:00+07', 'paid',       60.00, 'store'),
    (2002, 2, '2026-01-08 11:00:00+07', 'cancelled',  40.00, 'store'),
    (2003, 2, '2026-01-12 14:00:00+07', 'paid',      140.00, 'web'),
    (3001, 3, '2026-01-04 10:00:00+07', 'paid',      110.00, 'partner'),
    (3002, 3, '2026-01-09 10:00:00+07', 'pending',    90.00, 'partner'),
    (3003, 3, '2026-01-11 12:00:00+07', 'paid',      160.00, 'web');
~~~

**Lan's two orders 1002 and 1003 share the exact same `ordered_at`**. This is deliberate to illustrate *peer rows* and the difference between the default frame and `ROWS` with tie-broken ordering.

### 4.4. Reference figures

~~~sql
SELECT
    customer_id,
    COUNT(*) AS n_orders,
    SUM(amount) AS all_amount,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM window_lab.sales_orders
GROUP BY customer_id
ORDER BY customer_id;
~~~

Result:

| customer_id | n_orders | all_amount | paid_amount |
| ---: | ---: | ---: | ---: |
| 1 | 4 | 450.00 | 400.00 |
| 2 | 3 | 240.00 | 200.00 |
| 3 | 3 | 360.00 | 270.00 |

The full table holds **10 orders**: **7 paid, 2 pending, 1 cancelled**. Total value of all orders is **1050.00**; total paid value is **870.00**.

Concrete numbers in subsequent sections assume no further edits to this dataset.

## 5. Window with PARTITION BY only

Count orders and sum amount **per customer** while preserving every row:

~~~sql
SELECT
    order_id,
    customer_id,
    amount,
    COUNT(*) OVER w_customer AS customer_order_count,
    SUM(amount) OVER w_customer AS customer_amount
FROM window_lab.sales_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
~~~

Every row for Lan shows `customer_order_count = 4` and `customer_amount = 450.00`. Minh's rows show 3 and 240.00; Chi's rows show 3 and 360.00.

Without `ORDER BY` in the window definition, the default frame for an eligible aggregate is the **entire partition**. Therefore `SUM(amount) OVER w_customer` is the customer-wide sum, not a running sum.

### PARTITION BY differs from table partitioning

`PARTITION BY customer_id` inside `OVER` **splits input rows into logical calculation groups**. It **does not create partitioned tables**, move physical rows between storage partitions, or replace `CREATE TABLE ... PARTITION BY`.

If `PARTITION BY` is omitted:

~~~sql
SELECT
    order_id,
    COUNT(*) OVER () AS total_orders
FROM window_lab.sales_orders;
~~~

then all rows in the query form a single partition; every row gets `total_orders = 10`.

## 6. Window with PARTITION BY and ORDER BY

Name each customer's chronological order `w_chrono`:

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    status,
    ROW_NUMBER() OVER w_chrono AS order_sequence,
    LAG(order_id) OVER w_chrono AS previous_order_id,
    LEAD(order_id) OVER w_chrono AS next_order_id
FROM window_lab.sales_orders
WINDOW w_chrono AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, order_sequence;
~~~

Result for Lan:

| order_id | order_sequence | previous_order_id | next_order_id |
| ---: | ---: | ---: | ---: |
| 1001 | 1 | `NULL` | 1002 |
| 1002 | 2 | 1001 | 1003 |
| 1003 | 3 | 1002 | 1004 |
| 1004 | 4 | 1003 | `NULL` |

`order_id` inside `ORDER BY` acts as a **tie-breaker**: orders 1002 and 1003 share the same timestamp yet still have a deterministic sequence.

### ORDER BY inside OVER does not sort the final output

The two `ORDER BY` placements do different jobs:

~~~sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
~~~

defines the ordering **for evaluating the window function**.

Meanwhile:

~~~sql
ORDER BY customer_id, order_sequence
~~~

at the end of the query defines the ordering of **the returned output rows**.

Never drop the outermost `ORDER BY` assuming display output will match `OVER`'s order. The query planner is free to choose another execution path if no outer output order is requested.

## 7. Named WINDOW reused multiple times

The same window can serve different functions:

~~~sql
SELECT
    order_id,
    customer_id,
    ordered_at,
    amount,
    ROW_NUMBER() OVER w_time AS rn,
    LAG(amount) OVER w_time AS previous_amount,
    LEAD(amount) OVER w_time AS next_amount,
    FIRST_VALUE(amount) OVER w_time AS first_amount
FROM window_lab.sales_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, rn;
~~~

For each customer:

- `ROW_NUMBER` assigns sequence 1, 2, ...
- `LAG` inspects the previous order's amount.
- `LEAD` inspects the next order's amount.
- `FIRST_VALUE` inspects the first order's amount **within the active frame**; with the default frame starting at partition start up to current row, the result is always the first order's amount.

**Not every function has the same frame needs**. When adding cumulative `SUM`, three-order `AVG`, or all-history `LAST_VALUE`, specify explicit frames instead of sharing one unadjusted window blindly.

## 8. Reusing via window inheritance

PostgreSQL allows a definition in `WINDOW` to **reference an earlier declared window** and add missing clauses.

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    COUNT(*) OVER w_customer AS n_customer_orders,
    ROW_NUMBER() OVER w_chrono AS order_sequence,
    SUM(amount) OVER w_running AS running_amount,
    SUM(amount) OVER w_full AS customer_total
FROM window_lab.sales_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_chrono AS (
        w_customer
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_full AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, order_sequence;
~~~

These names form a dependency chain:

~~~text
w_customer
  PARTITION BY customer_id
        |
        v
w_chrono
  add ORDER BY ordered_at, order_id
        |
        +-----------------------+
        |                       |
        v                       v
w_running                    w_full
  frame start -> current       frame start -> end
        |                       |
        v                       v
  running SUM                 full customer SUM
~~~

Declaration order matters: `w_chrono` must be defined **after** `w_customer`, and `w_running`/`w_full` must appear after `w_chrono` to copy from it.

### 8.1. Result for Lan

| order_id | amount | running_amount | customer_total |
| ---: | ---: | ---: | ---: |
| 1001 | 120.00 | 120.00 | 450.00 |
| 1002 | 80.00 | 200.00 | 450.00 |
| 1003 | 50.00 | 250.00 | 450.00 |
| 1004 | 200.00 | 450.00 | 450.00 |

**`w_running` and `w_full` share partition and sort order, yet differ in frame.** Consequently, the same output row displays both the running total and the customer's full total.

### 8.2. Inheritance does not mutate the base definition

`w_running` does not turn `w_chrono` into a running-frame window for all functions. It creates a **new definition** copying valid clauses and appending a frame.

`ROW_NUMBER() OVER w_chrono` still references the original `w_chrono`. `SUM(amount) OVER w_full` uses the full-partition frame of the derived window.

## 9. OVER w and OVER (w) are not identical

This is a PostgreSQL syntax detail well worth remembering.

~~~sql
ROW_NUMBER() OVER w
~~~

means **directly referencing the named window `w`**.

~~~sql
ROW_NUMBER() OVER (w)
~~~

means **copying `w`'s definition into a new window specification**, even without adding clauses. Both behave identically when `w` contains only `PARTITION BY`/`ORDER BY`, yet they are not equivalent in validity.

### 9.1. With a frame-free window

~~~sql
SELECT
    order_id,
    ROW_NUMBER() OVER w_time AS a,
    ROW_NUMBER() OVER (w_time) AS b
FROM window_lab.sales_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
);
~~~

Both forms are valid because `w_time` **has no explicit frame clause**.

### 9.2. With a window that already has a frame

~~~sql
SELECT
    order_id,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

This is the **correct** way to use a named window carrying a frame.

Conversely:

~~~sql
-- Intentionally illustrates invalid syntax in PostgreSQL:
SELECT
    order_id,
    SUM(amount) OVER (w_running) AS running_amount
FROM window_lab.sales_orders
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

PostgreSQL forbids **copying a named window that already contains a frame clause** in this manner. Use `OVER w_running` to reference it directly.

### Quick rule

| Syntax | Interpretation | Note |
| --- | --- | --- |
| `OVER w` | Reference named window | Works when `w` has a frame |
| `OVER (w)` | Copy `w`'s definition | Cannot copy a window that has a frame |
| `OVER (w ROWS ...)` | Copy `w` and append frame | Base `w` must not have a frame |
| `OVER (...)` | Inline definition | No named window needed |

For named windows, **prefer `OVER w`** when using as-is. Use parentheses only when deliberately copying and extending a valid base definition.

## 10. Appending a frame at each OVER call site

You do not have to name every frame variant. You can declare one frame-free base window:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_amount,
    AVG(amount) OVER (
        w_chrono
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS last_three_average
FROM window_lab.sales_orders
WINDOW w_chrono AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, ordered_at, order_id;
~~~

This is **copy-and-extend**. Because `w_chrono` has no frame, both `OVER (w_chrono ROWS ...)` expressions are valid.

### When should you extract w_running and w_last_three names?

If a frame is reused across several columns, name it:

~~~sql
SELECT
    order_id,
    SUM(amount) OVER w_running AS running_amount,
    COUNT(*) OVER w_running AS running_count,
    AVG(amount) OVER w_last_three AS moving_avg
FROM window_lab.sales_orders
WINDOW
    w_chrono AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_chrono
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_last_three AS (
        w_chrono
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    );
~~~

The key rule is **never copy from a window that already carries a frame**. Inheritance should flow from a **frame-free base window** to specialized windows.

## 11. What is prohibited during inheritance

In PostgreSQL, window inheritance enforces syntactic constraints:

1. You may reference only windows declared **earlier** in the `WINDOW` list.
2. You cannot copy a window that already has a **frame clause**.
3. You cannot override a `PARTITION BY` or `ORDER BY` already defined in the copied window with conflicting clauses.
4. Each definition must follow valid clause order: copied window name, then `PARTITION BY`/`ORDER BY`/frame within syntax limits.

### 11.1. Do not redefine PARTITION BY

~~~sql
-- Illustrates INVALID syntax:
SELECT
    SUM(amount) OVER w_bad
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_bad AS (
        w_customer
        PARTITION BY channel
    );
~~~

If another window partitions by `channel`, declare an independent window:

~~~sql
SELECT
    order_id,
    SUM(amount) OVER w_customer AS customer_total,
    SUM(amount) OVER w_channel AS channel_total
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_channel AS (PARTITION BY channel);
~~~

### 11.2. Do not add a second ORDER BY when one already exists

~~~sql
-- Illustrates INVALID syntax:
SELECT
    ROW_NUMBER() OVER w_bad
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at
    ),
    w_bad AS (
        w_time ORDER BY amount
    );
~~~

If you need ordering by amount instead of time, derive two windows from the **same `ORDER BY`-free partition base**:

~~~sql
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w_time AS order_by_time,
    ROW_NUMBER() OVER w_money AS order_by_amount
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer
        ORDER BY ordered_at, order_id
    ),
    w_money AS (
        w_customer
        ORDER BY amount DESC, order_id
    );
~~~

### 11.3. Do not order inheritance backward

~~~sql
-- Invalid: w_child references undeclared w_base.
WINDOW
    w_child AS (w_base ORDER BY ordered_at),
    w_base AS (PARTITION BY customer_id)
~~~

Correct:

~~~sql
WINDOW
    w_base AS (PARTITION BY customer_id),
    w_child AS (w_base ORDER BY ordered_at)
~~~

This is a **sequential reference within the same `WINDOW` list**, not arbitrary class inheritance with overrides as in object-oriented languages.

## 12. What is a frame and why does it affect results?

Within a partition, a **frame** is a subset of rows defined relative to the **current row**.

Consider Lan's orders:

~~~text
Row 1: 1001, amount 120
Row 2: 1002, amount  80
Row 3: 1003, amount  50
Row 4: 1004, amount 200
~~~

If the frame is:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

then at row 1003, the frame contains **1001 + 1002 + 1003** and sums to **250.00**.

If the frame is:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

then at row 1004, the frame contains **1002 + 1003 + 1004**, totaling **330.00**; row 1001 has dropped out of the trailing three rows.

If the frame is:

~~~sql
ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
~~~

then all four of Lan's rows use the **entire partition**, totaling **450.00**.

### 12.1. Common frame keywords

| Expression | Meaning in `ROWS` |
| --- | --- |
| `UNBOUNDED PRECEDING` | Start of partition |
| `N PRECEDING` | N rows before the current row |
| `CURRENT ROW` | Current row |
| `N FOLLOWING` | N rows after the current row |
| `UNBOUNDED FOLLOWING` | End of partition |
| `BETWEEN ... AND ...` | Defines start and end bounds |

Not every pair of bounds is valid. Pick bounds matching the exact business question.

### 12.2. Frames do not remove rows from SELECT

A frame determines only which rows **contribute to the function's calculation** at the current position. `SUM(amount) OVER w_last_three` still returns **one value per order row** in the query, without collapsing or filtering out rows.

## 13. Differences between ROWS, RANGE, and GROUPS

PostgreSQL supports three frame units:

- **`ROWS`:** counts **physical row positions in window order**.
- **`RANGE`:** uses value ranges of the `ORDER BY` key; `CURRENT ROW` includes **tied peer rows**.
- **`GROUPS`:** counts **peer groups** sharing identical `ORDER BY` values.

For per-transaction chronological analysis, `ROWS` with a tie-breaker is usually easiest to reason about.

### 13.1. Default RANGE when ORDER BY is present

In PostgreSQL, when `ORDER BY` is specified without an explicit frame, the semantic default is:

~~~sql
RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
~~~

In `RANGE` mode, `CURRENT ROW` includes the **current row and all rows sharing the same `ORDER BY` values (peers)**.

Therefore:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at
)
~~~

can differ from:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

whenever multiple orders share the same `ordered_at`.

### 13.2. Testing Lan's peer rows

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER w_time_only AS default_range_sum,
    SUM(amount) OVER w_rows AS explicit_rows_sum
FROM window_lab.sales_orders
WHERE customer_id = 1
WINDOW
    w_time_only AS (
        ORDER BY ordered_at
    ),
    w_rows AS (
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
ORDER BY ordered_at, order_id;
~~~

Result:

| order_id | amount | default_range_sum | explicit_rows_sum |
| ---: | ---: | ---: | ---: |
| 1001 | 120.00 | 120.00 | 120.00 |
| 1002 | 80.00 | 250.00 | 200.00 |
| 1003 | 50.00 | 250.00 | 250.00 |
| 1004 | 200.00 | 450.00 | 450.00 |

Orders **1002 and 1003 share the same timestamp**, so they sit in the same peer group under `ORDER BY ordered_at` and are summed together by `RANGE ... CURRENT ROW`. With `ROWS` and the `order_id` tie-breaker, the sum steps row by row.

### 13.3. GROUPS counts peer groups

~~~sql
SELECT
    order_id,
    amount,
    SUM(amount) OVER (
        ORDER BY ordered_at
        GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW
    ) AS previous_and_current_time_group
FROM window_lab.sales_orders
WHERE customer_id = 1
ORDER BY ordered_at, order_id;
~~~

Timestamp groups:

~~~text
09:00 Jan 05: [1001]         sum = 120
09:00 Jan 07: [1002, 1003]   sum = 130
15:00 Jan 10: [1004]         sum = 200
~~~

In the Jan 07 group, the frame spans the **previous group (120) and current group (130)**, totaling **250** on both 1002 and 1003. In the Jan 10 group, the frame spans Jan 07 (130) and Jan 10 (200), totaling **330**.

**Peer groups depend on all `ORDER BY` expressions in the window.** Adding unique `order_id` eliminates ties among same-timestamp rows.

### 13.4. RANGE with offsets differs from ROWS

`RANGE BETWEEN INTERVAL '7 days' PRECEDING AND CURRENT ROW` over a suitable time key expresses a **time value span**, not "seven preceding rows".

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at
        RANGE BETWEEN INTERVAL '7 days' PRECEDING
                  AND CURRENT ROW
    ) AS amount_last_seven_days
FROM window_lab.sales_orders
ORDER BY customer_id, ordered_at, order_id;
~~~

In PostgreSQL, `RANGE` with offsets requires an appropriate `ORDER BY` structure—usually a **single sort key** whose type supports the offset; you cannot casually swap in two keys like `ordered_at, order_id` for an offset frame. Distinguish clearly between "seven days" and "seven rows".

## 14. Running totals and moving averages with WINDOW

Declare three specialized windows:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER w_running AS cumulative_sum,
    COUNT(*) OVER w_running AS cumulative_count,
    ROUND(
        AVG(amount) OVER w_last_three,
        2
    ) AS avg_last_three
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_last_three AS (
        w_time
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

For Lan:

| order_id | amount | cumulative_sum | cumulative_count | avg_last_three |
| ---: | ---: | ---: | ---: | ---: |
| 1001 | 120.00 | 120.00 | 1 | 120.00 |
| 1002 | 80.00 | 200.00 | 2 | 100.00 |
| 1003 | 50.00 | 250.00 | 3 | 83.33 |
| 1004 | 200.00 | 450.00 | 4 | 110.00 |

The final `avg_last_three = (80 + 50 + 200) / 3 = 110.00`. This is a **row-based three-order moving average**, not a three-day average.

### 14.1. Changing frame from 3 rows to 5 rows

If business requirements change to a five-order moving average, simply replace:

~~~sql
ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
~~~

for:

~~~sql
ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
~~~

in the corresponding named window definition. When multiple expressions share that frame, naming reduces edits to a single place.

### 14.2. Frames shorter than N at partition start

On a customer's first order, `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` **does not require three rows**: the frame contains whatever rows exist up to the current row. Thus `AVG` on the first order equals that order's own amount, not `NULL`.

## 15. FIRST_VALUE, LAST_VALUE, and NTH_VALUE

Positional value functions are highly sensitive to frames.

### 15.1. FIRST_VALUE and LAST_VALUE over the entire partition

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    FIRST_VALUE(amount) OVER w_full AS first_order_amount,
    LAST_VALUE(amount) OVER w_full AS last_order_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

For Lan, every row gets `first_order_amount = 120.00` and `last_order_amount = 200.00`. Minh gets 60.00 and 140.00; Chi gets 110.00 and 160.00.

### 15.2. LAST_VALUE with the default frame can trip you up

~~~sql
SELECT
    order_id,
    amount,
    LAST_VALUE(amount) OVER w_time AS last_value_in_frame
FROM window_lab.sales_orders
WHERE customer_id = 1
WINDOW w_time AS (
    ORDER BY ordered_at, order_id
)
ORDER BY ordered_at, order_id;
~~~

When `ORDER BY ordered_at, order_id` creates a tie-free ordering, the default frame ends at the **current row**. Consequently, `LAST_VALUE(amount)` returns the **current row's amount**, not the final order's amount across history.

For "customer's final order", specify `... AND UNBOUNDED FOLLOWING` or use an appropriate alternative technique rather than calling `LAST_VALUE` on an ordered frame-free named window.

### 15.3. NTH_VALUE

~~~sql
SELECT
    customer_id,
    order_id,
    NTH_VALUE(amount, 2) OVER w_full AS second_order_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, order_id;
~~~

`NTH_VALUE(amount, 2)` extracts the **second row's value inside the frame** in window order. Lan gets 80.00, Minh 40.00, Chi 90.00.

If the frame lacks two rows or a partition has fewer than two rows, the result is `NULL`. Never assume `NTH_VALUE` always reads the Nth row of the **entire partition** unless the frame covers the entire partition.

## 16. RANK, DENSE_RANK, and ROW_NUMBER reusing WINDOW

Ranking functions depend on partition and `ORDER BY`:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_amount AS row_no,
    RANK() OVER w_amount AS amount_rank,
    DENSE_RANK() OVER w_amount AS amount_dense_rank
FROM window_lab.sales_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount DESC
)
ORDER BY customer_id, amount DESC, order_id;
~~~

When a customer has two orders with identical `amount`, `RANK` and `DENSE_RANK` give them the **same rank**, while `ROW_NUMBER` assigns distinct numbers per row.

### Creating a dataset with clear ties

~~~sql
WITH scores(player, score) AS (
    VALUES
        ('A', 100),
        ('B', 90),
        ('C', 90),
        ('D', 80)
)
SELECT
    player,
    score,
    ROW_NUMBER() OVER w_points AS row_no,
    RANK() OVER w_points AS rank_no,
    DENSE_RANK() OVER w_points AS dense_rank_no
FROM scores
WINDOW w_points AS (
    ORDER BY score DESC
)
ORDER BY score DESC, player;
~~~

`rank_no` values are 1, 2, 2, 4; `dense_rank_no` values are 1, 2, 2, 3. `row_no` order between the two 90-point players can be **unstable** when the window sorts only by `score DESC`. If deterministic numbering is needed, add a stable secondary key—bearing in mind that adding it to the **same ranking window** breaks ties in `RANK`.

Separating them:

~~~sql
WITH scores(player, score) AS (
    VALUES
        ('A', 100),
        ('B', 90),
        ('C', 90),
        ('D', 80)
)
SELECT
    player,
    score,
    ROW_NUMBER() OVER w_deterministic AS stable_row_no,
    RANK() OVER w_score AS score_rank
FROM scores
WINDOW
    w_score AS (ORDER BY score DESC),
    w_deterministic AS (ORDER BY score DESC, player)
ORDER BY score DESC, player;
~~~

**Never reuse a single window merely because two expressions look similar**, if one function needs to keep peers tied while another needs a unique tie-breaker.

## 17. PERCENT_RANK, CUME_DIST, and NTILE

Other distribution functions also work with named windows:

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROUND(
        (PERCENT_RANK() OVER w_amount)::numeric,
        3
    ) AS percent_rank,
    ROUND(
        (CUME_DIST() OVER w_amount)::numeric,
        3
    ) AS cumulative_distribution,
    NTILE(3) OVER w_amount AS amount_bucket
FROM window_lab.sales_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount
)
ORDER BY customer_id, amount, order_id;
~~~

- `PERCENT_RANK` reflects the row's relative rank position within the partition, ranging from 0 to 1.
- `CUME_DIST` is the fraction of rows whose sort key is **less than or equal to** the current row's value in window order, including peers.
- `NTILE(3)` divides ordered rows into three numbered buckets (1, 2, 3), balancing row counts as evenly as possible.

These functions do not compute an interpolated median. When a median is needed, `PERCENTILE_CONT` or `PERCENTILE_DISC` uses ordered-set aggregate syntax paired with `GROUP BY` where appropriate.

### Watch function return types and ROUND

`PERCENT_RANK` and `CUME_DIST` return floating-point numbers in PostgreSQL. PostgreSQL's two-argument `ROUND(value, scale)` overload expects `numeric`; therefore, rounding to decimal places typically requires casting to `numeric`:

~~~sql
ROUND((PERCENT_RANK() OVER w_amount)::numeric, 3)
~~~

This differs from single-argument `ROUND(value)`, which accepts other input types. Check types with `pg_typeof` if you encounter a missing overload error when combining statistical functions.

## 18. Aggregate FILTER combined with named WINDOW

`FILTER (WHERE ...)` applies to **aggregate functions**, including when used as window aggregates.

~~~sql
SELECT
    customer_id,
    order_id,
    status,
    amount,
    COUNT(*) OVER w_customer AS all_customer_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) OVER w_customer AS paid_customer_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) OVER w_running AS running_paid_amount
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

For Lan:

| order_id | status | all_customer_orders | paid_customer_orders | running_paid_amount |
| ---: | --- | ---: | ---: | ---: |
| 1001 | paid | 4 | 3 | 120.00 |
| 1002 | paid | 4 | 3 | 200.00 |
| 1003 | pending | 4 | 3 | 200.00 |
| 1004 | paid | 4 | 3 | 400.00 |

The pending row **remains visible**, while not increasing `running_paid_amount`.

### FILTER does not attach to ROW_NUMBER

~~~sql
-- Illustrates INVALID syntax:
ROW_NUMBER() FILTER (WHERE status = 'paid') OVER w_time
~~~

`ROW_NUMBER` is a dedicated window function, not an aggregate accepting `FILTER`. To number **only paid rows**, filter first inside a CTE or use appropriate logic.

~~~sql
WITH paid AS (
    SELECT *
    FROM window_lab.sales_orders
    WHERE status = 'paid'
)
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w_paid AS paid_sequence
FROM paid
WINDOW w_paid AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, paid_sequence;
~~~

This query returns **only paid orders**, unlike the previous query where all statuses remain displayed.

## 19. WINDOW combining multiple partitioning schemes

A single report may need:

- Order count for the **same customer**.
- Order count in the **same channel**.
- System-wide **global order count**.
- Sequence within **customer history**.

~~~sql
SELECT
    order_id,
    customer_id,
    channel,
    COUNT(*) OVER w_customer AS customer_count,
    COUNT(*) OVER w_channel AS channel_count,
    COUNT(*) OVER w_all AS global_count,
    ROW_NUMBER() OVER w_customer_time AS customer_sequence
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_channel AS (PARTITION BY channel),
    w_all AS (),
    w_customer_time AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY customer_id, customer_sequence;
~~~

`w_all AS ()` defines an unpartitioned, unordered window. `COUNT(*) OVER w_all` returns 10 on every order in the sample dataset.

Multiple distinct window definitions can coexist in a single `SELECT`. Not all window functions must share the same `PARTITION BY`.

### Row count does not change on its own

Running window functions alone over 10 orders without filtering or joining produces 10 output rows, even across four different windows. `WINDOW` is not `JOIN` or `GROUP BY`.

## 20. WINDOW in queries with WHERE

`WHERE` restricts the row set **before** window functions are evaluated within a standard query level.

~~~sql
SELECT
    order_id,
    customer_id,
    status,
    ROW_NUMBER() OVER w_time AS sequence_among_paid
FROM window_lab.sales_orders
WHERE status = 'paid'
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, sequence_among_paid;
~~~

For Lan, only three paid orders enter the window, so `sequence_among_paid` is 1, 2, 3 for 1001, 1002, 1004. Pending order 1003 **is excluded from ranking**.

To number the full history and **display only paid orders**, filter after the window via a CTE:

~~~sql
WITH ranked_all AS (
    SELECT
        order_id,
        customer_id,
        status,
        ROW_NUMBER() OVER w_time AS sequence_in_all_orders
    FROM window_lab.sales_orders
    WINDOW w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    )
)
SELECT *
FROM ranked_all
WHERE status = 'paid'
ORDER BY customer_id, sequence_in_all_orders;
~~~

For Lan, order 1004 gets `sequence_in_all_orders = 4` because pending order 1003 participated in the initial ranking. **Filtering order vs. window evaluation changes report semantics.**

## 21. Why cannot a window function go directly inside WHERE?

Invalid example:

~~~sql
-- Invalid:
SELECT
    order_id,
    customer_id
FROM window_lab.sales_orders
WHERE ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
) = 1;
~~~

PostgreSQL prohibits window functions directly inside `WHERE` of the same query block; likewise for `GROUP BY` and `HAVING`. Windows are evaluated logically after rows/groups have been formed.

**Solution:** compute first in a subquery/CTE and filter at the outer level.

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER w_latest AS rn
    FROM window_lab.sales_orders AS o
    WINDOW w_latest AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT
    customer_id,
    order_id,
    amount
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
~~~

Latest order for Lan, Minh, Chi: **1004, 2003, 3003**. Customer Dung has no orders so she does not appear from `sales_orders`.

### Preserving customers with no orders

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER w_latest AS rn
    FROM window_lab.sales_orders AS o
    WINDOW w_latest AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id AS latest_order_id,
    r.amount AS latest_amount
FROM window_lab.customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
~~~

Customer Dung stays in the result with `NULL`s for `r` columns. Placing `r.rn = 1` inside `ON` prevents the `LEFT JOIN` from dropping customers without orders.

## 22. Combining WINDOW and GROUP BY

Window functions can appear in aggregated queries. In that case, they evaluate over the **grouped output rows produced by `GROUP BY`** in that query block, no longer seeing individual source orders directly.

Example:

~~~sql
SELECT
    customer_id,
    channel,
    COUNT(*) AS orders_in_group,
    SUM(amount) AS amount_in_group,
    SUM(SUM(amount)) OVER w_customer AS customer_total
FROM window_lab.sales_orders
GROUP BY customer_id, channel
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, channel;
~~~

Explanation:

1. `GROUP BY customer_id, channel` forms each customer–channel group.
2. `SUM(amount)` computes each group's sum.
3. `SUM(SUM(amount)) OVER w_customer` sums **those group totals** per customer to yield the customer total.

This is a supported **aggregate nested inside a window aggregate**; it is not "nesting one window function inside another window function".

### Be careful with COUNT(*) OVER after GROUP BY

~~~sql
SELECT
    customer_id,
    channel,
    COUNT(*) AS raw_orders_in_group,
    COUNT(*) OVER w_customer AS channel_groups_for_customer
FROM window_lab.sales_orders
GROUP BY customer_id, channel
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, channel;
~~~

Here `COUNT(*) OVER w_customer` counts the **customer–channel group rows** produced by `GROUP BY`, **not the customer's original order count**.

If a customer uses two channels, every group row for that customer gets 2. Always verify the **input granularity seen by window functions** when combining with `GROUP BY`.

## 23. WINDOW with ORDER BY at the SELECT level

Window functions may appear in valid sort expressions, though keeping queries readable is best.

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_high_value AS value_rank
FROM window_lab.sales_orders
WINDOW w_high_value AS (
    PARTITION BY customer_id
    ORDER BY amount DESC, order_id
)
ORDER BY customer_id, value_rank;
~~~

The outermost `ORDER BY customer_id, value_rank` references the alias computed in `SELECT`. Without outer sorting, output order is never guaranteed by SQL.

### Aliases within the same SELECT list

A column alias defined in a `SELECT` list generally **cannot be referenced as an input column** in another expression at the exact same level:

~~~sql
-- Do not expect the value_rank alias to work in the next expression:
SELECT
    ROW_NUMBER() OVER w AS value_rank,
    value_rank + 1 AS next_rank
FROM window_lab.sales_orders
WINDOW w AS (ORDER BY order_id);
~~~

To process window results further, use a subquery or CTE:

~~~sql
WITH ranked AS (
    SELECT
        order_id,
        ROW_NUMBER() OVER w AS value_rank
    FROM window_lab.sales_orders
    WINDOW w AS (ORDER BY order_id)
)
SELECT
    order_id,
    value_rank,
    value_rank + 1 AS next_rank
FROM ranked;
~~~

## 24. Do not nest window functions directly inside window functions

Invalid example:

~~~sql
-- Invalid:
SELECT
    SUM(ROW_NUMBER() OVER w) OVER w
FROM window_lab.sales_orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY ordered_at
);
~~~

PostgreSQL does not permit a window function call directly inside an argument of another window function in the same query block.

If you need to aggregate ranking values, compute them first:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ROW_NUMBER() OVER w_time AS rn
    FROM window_lab.sales_orders
    WINDOW w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    )
)
SELECT
    customer_id,
    SUM(rn) AS rank_number_sum
FROM ranked
GROUP BY customer_id
ORDER BY customer_id;
~~~

This illustrates splitting query blocks; summing sequence numbers only makes sense if business logic genuinely calls for that metric.

## 25. DISTINCT, LIMIT, and WINDOW output row counts

Outer clauses can **reduce the final output row count**, yet window functions still evaluate over the query block's row set in logical order.

~~~sql
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w AS rn
FROM window_lab.sales_orders
WINDOW w AS (
    PARTITION BY customer_id
    ORDER BY ordered_at DESC, order_id DESC
)
ORDER BY customer_id, rn
LIMIT 5;
~~~

`LIMIT 5` returns **five rows of the final output**, not five rows per customer. To get the two newest orders **per customer**, compute `rn` and filter `rn <= 2` in an outer query:

~~~sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER w AS rn
    FROM window_lab.sales_orders
    WINDOW w AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT *
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
~~~

Result has **6 rows**: the two latest orders for each customer who has orders. Do not confuse this with a global `LIMIT 2`.

## 26. WINDOW does not fabricate missing date/month groups

When analyzing daily revenue, windows do not generate dates **with no orders**:

~~~sql
WITH daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS order_day,
        SUM(amount) AS day_amount
    FROM window_lab.sales_orders
    GROUP BY 1
)
SELECT
    order_day,
    day_amount,
    SUM(day_amount) OVER w_running AS cumulative_amount
FROM daily
WINDOW w_running AS (
    ORDER BY order_day
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY order_day;
~~~

Only dates with orders appear in the `daily` CTE.

If zero-revenue dates must appear as 0-value rows, generate a **date axis** with `generate_series` and `LEFT JOIN` aggregated sales before applying the window:

~~~sql
WITH days AS (
    SELECT d::date AS order_day
    FROM generate_series(
        TIMESTAMP '2026-01-04',
        TIMESTAMP '2026-01-12',
        INTERVAL '1 day'
    ) AS g(d)
),
daily AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS order_day,
        SUM(amount) AS day_amount
    FROM window_lab.sales_orders
    GROUP BY 1
),
calendar AS (
    SELECT
        d.order_day,
        COALESCE(s.day_amount, 0::numeric) AS day_amount
    FROM days AS d
    LEFT JOIN daily AS s USING (order_day)
)
SELECT
    order_day,
    day_amount,
    SUM(day_amount) OVER w_running AS cumulative_amount
FROM calendar
WINDOW w_running AS (
    ORDER BY order_day
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY order_day;
~~~

**`WINDOW` operates strictly on actual input rows**, never synthesizing missing dates, customers, or products. That responsibility belongs to building the input dataset.

## 27. Avoiding confusion between NULLs and empty groups

Customer Dung has no orders in `sales_orders`, so window functions run directly on `sales_orders` **produce no rows for Dung**.

To return one row per customer with order count and total amount:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS n_orders,
    COALESCE(SUM(o.amount), 0::numeric) AS total_amount
FROM window_lab.customers AS c
LEFT JOIN window_lab.sales_orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

For Dung, `n_orders = 0` and `total_amount = 0.00`.

Watch out: writing `COUNT(*)` after a `LEFT JOIN` with no matching right-side row still counts **one null-extended row**. To count actual orders, use `COUNT(o.order_id)` on a non-null order key.

When putting a `LEFT JOIN` into a query with window functions over order columns, clarify whether null-extended rows count as partition rows. Often **isolating order stats in a CTE** before joining to customers avoids numbering a "non-existent order".

## 28. WINDOW and performance: not an automatic speedup

Changing:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

to:

~~~sql
SUM(amount) OVER w_running
~~~

using an equivalent named window **does not alter the logical nature** of the computation. PostgreSQL may recognize identical windows, share sort work, or schedule multiple `WindowAgg` nodes as needed. However, there is no guarantee that one `WINDOW` name yields strictly one scan or one sort.

### 28.1. What appears in execution plans?

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    order_id,
    ROW_NUMBER() OVER w_time AS rn,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    );
~~~

In the plan, you may see:

- `WindowAgg`: node executing window evaluations.
- `Sort`: sorts input if not already in the required order.
- `Incremental Sort` in suitable cases where a prefix order already exists.
- `Index Scan` or `Index Only Scan` when query and visibility state permit.
- `actual rows`, `actual time`, `loops`, and `BUFFERS` showing runtime metrics.

Never assume a `WindowAgg` node automatically makes SQL slow. Examine sort cost, row counts, groups, frame sizes, joins, and total data read.

### 28.2. Indexes serving PARTITION BY and ORDER BY

For frequent queries running with:

~~~sql
PARTITION BY customer_id
ORDER BY ordered_at, order_id
~~~

consider a B-tree index:

~~~sql
CREATE INDEX idx_orders_customer_time
ON window_lab.sales_orders (
    customer_id,
    ordered_at,
    order_id
);
~~~

If the planner can read rows in this order, it may reduce or skip sorting steps. Still, the lab table has only 10 orders, so `Seq Scan` + `Sort` can remain cheaper than an index scan.

Indexes also carry **storage and write maintenance costs**. Create indexes for real workload patterns and inspect `EXPLAIN` on representative data.

### 28.3. Different sort orders may require multiple sorts

~~~sql
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_amount AS (
        PARTITION BY customer_id
        ORDER BY amount DESC, order_id
    )
~~~

these two windows have **different sort orders**. Naming them does not let them share one physical sort order in general. Queries with multiple distinct sort definitions can incur higher computation cost.

### 28.4. Filter early when business semantics match

When analyzing orders for one customer or date range, `WHERE` shrinks the row count to process. Keep in mind `WHERE` also alters the **historical scope** seen by the window. When filtering must happen after full-history ranking, use subqueries in proper logical order instead of filtering early and silently changing results.

## 29. Common mistakes with WINDOW

### Mistake 1: Placing WINDOW in the wrong position

Wrong idea:

~~~sql
-- Incorrect syntax order:
SELECT ROW_NUMBER() OVER w
FROM window_lab.sales_orders
ORDER BY order_id
WINDOW w AS (ORDER BY order_id);
~~~

`WINDOW` must precede the outermost `ORDER BY`:

~~~sql
SELECT ROW_NUMBER() OVER w AS rn
FROM window_lab.sales_orders
WINDOW w AS (ORDER BY order_id)
ORDER BY rn;
~~~

### Mistake 2: Referencing an undeclared window name

~~~sql
-- Missing WINDOW w_time AS (...):
SELECT ROW_NUMBER() OVER w_time
FROM window_lab.sales_orders;
~~~

Window names are not global variables. Declare them within the corresponding `SELECT`.

### Mistake 3: Inheriting windows in reverse order

If `w_child` references `w_base`, `w_base` must appear earlier in `WINDOW`.

### Mistake 4: Copying a window that has a frame

If `w_running` already carries a frame, use `OVER w_running`, not `OVER (w_running)`. The parenthesized form attempts to copy a framed window and is rejected by PostgreSQL.

### Mistake 5: Overriding an existing PARTITION BY/ORDER BY

Do not add `PARTITION BY channel` when copying a window already partitioned by customer; do not add another `ORDER BY` when the base window already has `ORDER BY`. Split the base window appropriately.

### Mistake 6: Thinking ORDER BY inside OVER sorts final output

Add an outermost `ORDER BY` whenever stable output order is required.

### Mistake 7: Confusing default RANGE with ROWS

When multiple rows share `ORDER BY`, `RANGE ... CURRENT ROW` includes the **entire peer group** at each row. To step transaction by transaction, use `ROWS` with a tie-breaker key.

### Mistake 8: LAST_VALUE returning only the current value

With the default frame ending at the current row, `LAST_VALUE` is not necessarily the partition's last row. Use `... UNBOUNDED FOLLOWING` when partition end is required.

### Mistake 9: Filtering at the wrong stage

If `WHERE status='paid'` sits in the same query block, non-paid orders never enter ranking. To rank full history and display only paid orders, compute the window in a CTE first.

### Mistake 10: Putting ROW_NUMBER inside WHERE

Window functions cannot appear directly in same-block `WHERE`. Use a CTE and filter on the ranking alias outside.

### Mistake 11: Nesting two window functions

PostgreSQL forbids passing a window function directly as an argument to another window function. Chain sequential query blocks instead.

### Mistake 12: Assuming COUNT(*) OVER after GROUP BY counts original orders

Once `GROUP BY` forms group rows, windows process **group rows**. For original order counts, aggregate at the proper granularity.

### Mistake 13: Neglecting tie-aware rankings

Adding a unique key to the same named window used by `RANK` breaks ties among equal scores. Separate the score-ranking window from the tie-broken row-numbering window.

### Mistake 14: Treating WINDOW as an index or physical cache

Named windows store no data and do not guarantee a single sort. Use `EXPLAIN (ANALYZE, BUFFERS)` instead of inferring speed from shorter SQL text.

## 30. Practice exercises

The exercises below use the `window_lab` schema and 10 orders created earlier. Write the SQL, predict outputs, and verify against the solutions. Read-only queries leave lab data unchanged.

### Exercise 1. Defining a named window

Write a query returning `order_id`, `customer_id`, and `ROW_NUMBER` in ascending chronological order per customer using a window named `w_time`. Use `order_id` as tie-breaker.

### Exercise 2. Reusing the same window

In the same `SELECT`, use `w_time` for `ROW_NUMBER`, `LAG(amount)`, and `LEAD(amount)`. Why does naming prevent ordering mismatches across all three functions?

### Exercise 3. Window with PARTITION BY only

Return each order alongside the order count and total amount **for the whole customer**. Window `w_customer` needs no `ORDER BY`.

### Exercise 4. Window inheritance

Declare `w_customer` with only `PARTITION BY customer_id`, then `w_time` inheriting from it and adding `ORDER BY ordered_at, order_id`.

### Exercise 5. Running total

Declare `w_running` inheriting `w_time` with `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. For Lan, what is the sum at order 1003?

### Exercise 6. Full-partition total

From `w_time`, derive `w_full` so `SUM(amount)` returns the customer total on every order. For Lan, what value should appear on all rows?

### Exercise 7. Three most recent orders

Create named window `w_three` and compute `AVG(amount)` across up to three orders (current row and two preceding rows). What is the value at Lan's order 1004?

### Exercise 8. OVER w or OVER (w)?

Suppose `w_running` already includes a `ROWS ...` frame. Which is valid: `SUM(amount) OVER w_running` or `SUM(amount) OVER (w_running)`? Why?

### Exercise 9. Getting true LAST_VALUE

Write a query using `LAST_VALUE(amount)` so every row for Lan sees the amount of her final historical order, not the current order.

### Exercise 10. RANGE and peers

Why can `SUM(amount) OVER (ORDER BY ordered_at)` in Lan's partition return `250` for **both 1002 and 1003**? Write the query so totals increment row by row.

### Exercise 11. GROUPS frame

On Lan's orders, use `GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW` ordered by `ordered_at`. What is the sum at the Jan 10 group?

### Exercise 12. Pre-window vs. post-window filtering

Compare: (a) `WHERE status='paid'` inside the query computing `ROW_NUMBER`; (b) computing `ROW_NUMBER` over all orders and filtering paid outside. Which sequence number does Lan's order 1004 receive in each?

### Exercise 13. Latest order per customer

Use `ROW_NUMBER() OVER w_latest`, a CTE, and outer `WHERE rn=1`. Which order IDs are selected? How do you keep Dung?

### Exercise 14. FILTER on a window aggregate

Compute `running_paid_amount` chronologically per customer while keeping unpaid orders in the output. For Lan, what is the paid total after order 1004?

### Exercise 15. Ranking with ties

Scores `100,90,90,80`: explain `RANK`/`DENSE_RANK`. If you want stable `ROW_NUMBER` while keeping `RANK` ties, how many named windows are needed and why?

### Exercise 16. GROUP BY + WINDOW

Write a query summing amount per `customer_id, channel`, then use `SUM(SUM(amount)) OVER w_customer` for customer total. What does `COUNT(*) OVER w_customer` count here?

### Exercise 17. Output ordering

Does `ORDER BY ordered_at, order_id` inside `OVER` guarantee output rows are sorted by those two columns? If not, what is needed?

### Exercise 18. WINDOW syntax fixes

Fix these errors: (a) placing `WINDOW` after outermost `ORDER BY`; (b) declaring `w_child` before `w_base`; (c) adding `ORDER BY amount` when copying a window that already has `ORDER BY ordered_at`.

### Exercise 19. Performance optimization

A table has millions of orders, and reports use windows partitioned by customer and ordered by `ordered_at, order_id`. Propose an index worth testing and how to check if the planner uses it.

### Exercise 20. Daily aggregation with empty days

If a day has no orders, does `WINDOW` create that day automatically? Describe how to build a complete daily report over a range with running totals.

### Exercise 21. Statistical type of percent_rank

Why can `ROUND(PERCENT_RANK() OVER w, 3)` fail with an overload error in PostgreSQL? Write the proper cast before rounding.

### Exercise 22. Comparing WINDOW with CTE/view

State the boundaries of named windows: do they persist data across queries, replace CTEs/views, or guarantee speedups?

## 31. Reference solutions

### Exercises 1 and 2. Shared named WINDOW

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_time AS seq_no,
    LAG(amount) OVER w_time AS prev_amount,
    LEAD(amount) OVER w_time AS next_amount
FROM window_lab.sales_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, seq_no;
~~~

You only need to adjust ordering in the single `w_time` definition if all three functions must follow a revised rule.

### Exercise 3. Customer-wide window

~~~sql
SELECT
    order_id,
    customer_id,
    COUNT(*) OVER w_customer AS n_orders,
    SUM(amount) OVER w_customer AS total_amount
FROM window_lab.sales_orders
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, order_id;
~~~

Lan has 4 orders and total 450.00.

### Exercise 4. Inheritance

~~~sql
SELECT
    order_id,
    ROW_NUMBER() OVER w_time AS seq_no
FROM window_lab.sales_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    );
~~~

### Exercise 5. Running SUM

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Lan, order 1003: `120 + 80 + 50 = 250.00`.

### Exercise 6. Full partition

~~~sql
SELECT
    customer_id,
    order_id,
    SUM(amount) OVER w_full AS total_customer_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND UNBOUNDED FOLLOWING
    );
~~~

Lan: `450.00` on all four rows.

### Exercise 7. Average last three

~~~sql
SELECT
    customer_id,
    order_id,
    ROUND(AVG(amount) OVER w_three, 2) AS avg_last_three
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_three AS (
        w_time ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

At Lan's order 1004, `(80+50+200)/3 = 110.00`.

### Exercise 8. OVER w with frame

`SUM(amount) OVER w_running` is valid; `OVER (w_running)` tries to copy a definition that already contains a frame, which PostgreSQL rejects.

### Exercise 9. All-history LAST_VALUE

~~~sql
SELECT
    customer_id,
    order_id,
    LAST_VALUE(amount) OVER w_full AS last_amount
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_full AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, order_id;
~~~

Every row for Lan gets `last_amount = 200.00`.

### Exercise 10. Peer rows

1002 and 1003 share `ordered_at`, so default `RANGE` includes the whole peer group at that timestamp. To get 200 then 250:

~~~sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
~~~

### Exercise 11. GROUPS

At order 1004 on Jan 10, the frame includes the Jan 07 group (80+50) and Jan 10 group (200), totaling **330.00**.

### Exercise 12. Filtering and ranking

(a) Only paid orders are ranked, so 1004 gets `rn = 3`. (b) All orders are ranked first and then filtered, so 1004 gets `rn = 4`.

### Exercise 13. Top 1 per customer

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER w_latest AS rn
    FROM window_lab.sales_orders AS o
    WINDOW w_latest AS (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    )
)
SELECT c.customer_id, r.order_id
FROM window_lab.customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
~~~

Orders 1004, 2003, 3003; Dung gets `order_id = NULL`.

### Exercise 14. Running paid

~~~sql
SELECT
    customer_id,
    order_id,
    status,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid')
            OVER w_running,
        0::numeric
    ) AS running_paid
FROM window_lab.sales_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
~~~

Lan after 1004: `400.00`.

### Exercise 15. Ties

`RANK`: 1, 2, 2, 4; `DENSE_RANK`: 1, 2, 2, 3. You need at least two ordering definitions: `w_score AS (ORDER BY score DESC)` to keep peers tied for ranking; `w_stable AS (ORDER BY score DESC, unique_id)` for deterministic row numbering.

### Exercise 16. Grouped sums

~~~sql
SELECT
    customer_id,
    channel,
    SUM(amount) AS channel_amount,
    SUM(SUM(amount)) OVER w_customer AS customer_amount,
    COUNT(*) OVER w_customer AS n_channel_groups
FROM window_lab.sales_orders
GROUP BY customer_id, channel
WINDOW w_customer AS (PARTITION BY customer_id)
ORDER BY customer_id, channel;
~~~

`COUNT(*) OVER w_customer` counts the number of **channel groups after `GROUP BY`**, not original order rows.

### Exercise 17. Output ordering

No. You must add an `ORDER BY` at the end of `SELECT`, such as `ORDER BY customer_id, ordered_at, order_id`.

### Exercise 18. Fixing placement and inheritance

Place `WINDOW` before outermost `ORDER BY`, place `w_base` before `w_child`, and derive `w_amount` from a base **without an existing `ORDER BY`** instead of overriding a time-ordered window.

### Exercise 19. Index and EXPLAIN

~~~sql
CREATE INDEX idx_orders_customer_time
ON window_lab.sales_orders (
    customer_id, ordered_at, order_id
);

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    SUM(amount) OVER w_running AS running_amount
FROM window_lab.sales_orders
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
~~~

Inspect `WindowAgg`, `Sort`/`Index Scan`, runtime, and buffers on sufficiently large data. An index is not guaranteed to be chosen in every plan.

### Exercise 20. Dates with no orders

`WINDOW` does not create empty dates. Use `generate_series` as a date axis, `LEFT JOIN` daily aggregates, `COALESCE` to show 0, and run `SUM(day_amount) OVER w_running` on the calendar result.

### Exercise 21. ROUND and result type

~~~sql
SELECT
    order_id,
    ROUND(
        (PERCENT_RANK() OVER w_amount)::numeric,
        3
    ) AS percent_rank_rounded
FROM window_lab.sales_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount
);
~~~

`PERCENT_RANK` returns floating-point `double precision`; casting to `numeric` selects `ROUND(numeric, integer)`.

### Exercise 22. Named window scope

A `WINDOW` name applies within a **single query block**. It stores no data, does not replace views/CTEs for sharing query datasets across queries, and guarantees neither index usage nor faster runtime. Its primary benefit is **clear, consistent, reusable partition/order/frame definitions within the same `SELECT`**.

## 32. Quick syntax lookup table

| Requirement | SQL pattern |
| --- | --- |
| Define a named window | `WINDOW w AS (PARTITION BY key ORDER BY time_col)` |
| Direct reference | `ROW_NUMBER() OVER w` |
| Unpartitioned, unordered window | `WINDOW w_all AS ()` |
| Copy a frame-free window | `OVER (w ROWS BETWEEN ...)` |
| Inherit partition and add order | `WINDOW base AS (PARTITION BY key), ordered AS (base ORDER BY time_col)` |
| Inherit and add frame | `WINDOW running AS (ordered ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` |
| Whole partition with `ORDER BY` | `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` |
| Average of last three rows | `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` |
| Running total | `SUM(value) OVER running` |
| Read preceding/following value | `LAG(value) OVER ordered`, `LEAD(value) OVER ordered` |
| Sequence numbering | `ROW_NUMBER() OVER ordered` |
| Tie-preserving rank | `RANK() OVER w_score`, `DENSE_RANK() OVER w_score` |
| Last value across whole partition | `LAST_VALUE(value) OVER full_frame` |
| Cumulative paid total | `SUM(amount) FILTER (WHERE status='paid') OVER running` |
| Top N per customer | CTE computing `ROW_NUMBER` then outer `WHERE rn <= N` |
| Inspect execution plan | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` |

## 33. Checklist before using WINDOW in production

| Question | Purpose |
| --- | --- |
| Does one input row represent an order, customer, or day group? | Avoid statistical grain errors |
| Keep individual rows or collapse via `GROUP BY`? | Choose window vs. group aggregate |
| What is the partition? | Set accurate data boundaries |
| Which columns are in `ORDER BY`, and is there a tie-breaker? | Prevent non-deterministic ordering |
| Is the function frame-sensitive? | Especially `SUM`, `AVG`, `FIRST/LAST/NTH_VALUE` |
| Does default `RANGE` affect peers? | Avoid unexpected group jumps in running sums |
| Need `ROWS`, `RANGE`, or `GROUPS`? | Pick the right frame unit |
| Can partition/order be reused? | Define a base named `WINDOW` |
| Does an inherited base contain a frame? | Prevent copy errors |
| Do multiple windows use different sort orders? | Evaluate sort overhead |
| Filter before or after window evaluation? | Avoid altering ranking semantics |
| Are customers/dates without data missing? | Add source table/`LEFT JOIN`/date axis |
| What type does the statistical function return? | Avoid cast/`ROUND` errors |
| What do `Sort`, `WindowAgg`, and buffers look like in `EXPLAIN`? | Tune on representative data |

## 34. Summary

In PostgreSQL, the **`WINDOW` clause lets you name one or more window definitions within a `SELECT`** so functions can invoke them via `OVER window_name`. It is invaluable whenever a report computes multiple metrics sharing the same customer, channel, or time grouping, avoiding repeated `PARTITION BY` and `ORDER BY` clauses across every function.

Three principles to remember:

1. **`PARTITION BY` defines groups, `ORDER BY` defines order, and the frame defines which rows contribute to frame-dependent functions.** For per-transaction cumulative totals, specify `ROWS ... CURRENT ROW` and a tie-breaker key.
2. **`OVER w` directly references a named window; `OVER (w ...)` copies to extend it.** PostgreSQL forbids copying a named window that already has a frame, so build a frame-free base window and derive `w_running`, `w_full`, `w_last_three` variants from it.
3. **Reusing a window reuses logical definitions, not cached data or guaranteed speedups.** Choose specs by business semantics, verify peer groups, default frames, and filter order, and inspect `EXPLAIN` to assess performance.

When authoring a report with many window functions, ask: **"Which calculations genuinely share partition and order? Which ones need different frames?"**. Declare `WINDOW` along the hierarchy **partition → order → frame**, then attach each function to the matching window. This keeps SQL readable, makes analytical rules explicit, and prevents bugs as reports evolve.
