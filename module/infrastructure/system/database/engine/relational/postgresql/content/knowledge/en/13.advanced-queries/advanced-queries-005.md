# LATERAL and Row-Dependent Subqueries in PostgreSQL

A sales system often needs answers to questions like: "For **each customer**, retrieve their **two newest orders**", "For **each order**, expand its JSON tag list into rows", or "For **each store**, find its top three best-selling products". What they have in common is that **a trailing subquery or function needs to use values from the preceding row being evaluated**.

In PostgreSQL, the **`LATERAL`** keyword lets you write this kind of query naturally. It allows a subquery or function call in the `FROM` clause to reference columns from `FROM` items that appear before it in the same scope.

Typical example:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.created_at
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE;
~~~

Unlike an independent subquery in `FROM`, the `LATERAL` subquery here can use `c.customer_id` to select **orders specific to each customer**. `LEFT JOIN` retains customers with no orders yet; if you use `CROSS JOIN LATERAL` or `JOIN LATERAL ... ON TRUE`, customers with no matching rows drop out.

This lesson covers the mental model, syntax, a complete hands-on lab, differences between join types, comparisons with correlated subqueries/`EXISTS`/window functions/`DISTINCT ON`, handling JSONB and set-returning functions, and performance tuning notes using `EXPLAIN` and indexes.

## 1. Independent Subqueries vs. Correlated Subqueries

Before learning `LATERAL`, distinguish two types of subqueries.

### 1.1. Independent subquery

Example retrieving the total order count across the whole system:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    totals.all_orders
FROM customers AS c
CROSS JOIN (
    SELECT COUNT(*) AS all_orders
    FROM orders
) AS totals;
~~~

The `totals` subquery **uses no columns** from `c`. Logically, it computes one system-wide total and shares it across all customer rows. There is no need for `LATERAL`.

### 1.2. Correlated subquery

Example:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT COUNT(*)
        FROM orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM customers AS c;
~~~

The subquery in the **`SELECT` list** reads `c.customer_id` from the outer query. It is a **correlated subquery**, even though **`LATERAL` is not written**.

Key point:

- "Correlated" describes the **data-dependency relationship** between the inner query and the outer query.
- `LATERAL` is special syntax allowing a **component inside `FROM`** to reference preceding `FROM` components.
- Not every correlated subquery requires `LATERAL`. For instance, a scalar subquery in `SELECT` or `EXISTS` in `WHERE` already supports referencing the outer query.

## 2. Why Is a Regular Subquery in FROM Not Enough?

Consider fetching the two newest orders for each customer:

~~~sql
SELECT
    c.customer_name,
    x.order_id
FROM customers AS c
JOIN (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC
    LIMIT 2
) AS x ON TRUE;
~~~

The snippet above is **invalid in PostgreSQL**, because a standalone subquery in `FROM` is not allowed to reference `c.customer_id` from the surrounding `FROM` scope.

Add `LATERAL`:

~~~sql
SELECT
    c.customer_name,
    x.order_id
FROM customers AS c
JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS x ON TRUE;
~~~

Now `c.customer_id` can be used inside subquery `x`. In **SQL semantics**, PostgreSQL evaluates `x` for each row `c`, then pairs up the resulting rows. The optimizer may choose an appropriate execution strategy; do not treat this logical model as a promise that PostgreSQL literally re-runs an entire physical subquery once per row.

### Visual model

~~~text
customers
  |
  +-- c = An    ---> subquery WHERE customer_id = 1
  |                   ORDER BY created_at DESC LIMIT 2
  |                   => An's two newest orders
  |
  +-- c = Binh  ---> subquery WHERE customer_id = 2
  |                   ORDER BY created_at DESC LIMIT 2
  |                   => Binh's two newest orders
  |
  +-- c = Chi   ---> subquery WHERE customer_id = 3
  |                   ORDER BY created_at DESC LIMIT 2
  |                   => Chi's two newest orders
  |
  +-- c = Dung  ---> subquery WHERE customer_id = 4
                      => empty set if Dung has no orders
~~~

Handling **empty sets** is why we need to distinguish `CROSS JOIN LATERAL` from `LEFT JOIN LATERAL`.

## 3. LATERAL Syntax and Reference Scope

Common forms:

~~~sql
SELECT ...
FROM left_relation AS l
CROSS JOIN LATERAL (
    SELECT ...
    WHERE some_column = l.some_column
) AS r;
~~~

Or:

~~~sql
SELECT ...
FROM left_relation AS l
LEFT JOIN LATERAL (
    SELECT ...
    WHERE some_column = l.some_column
) AS r ON TRUE;
~~~

For set-returning functions:

~~~sql
SELECT ...
FROM left_relation AS l
CROSS JOIN LATERAL
    some_set_returning_function(l.some_column) AS f;
~~~

### 3.1. What can LATERAL see?

A `LATERAL` item can reference `FROM` items appearing **before it** within valid scope. When `LATERAL` sits on the right side of a `JOIN`, it can read columns from items or join trees on the left according to SQL syntax rules.

Example:

~~~sql
FROM customers AS c
LEFT JOIN LATERAL (
    SELECT ...
    WHERE o.customer_id = c.customer_id
) AS latest ON TRUE
~~~

Valid because `c` appears before `latest`.

Do not attempt to reference an alias declared **after** the `LATERAL` item:

~~~sql
-- Illustrates a scope error; alias o2 does not exist yet when x is defined:
FROM customers AS c
CROSS JOIN LATERAL (
    SELECT o2.order_id
) AS x
JOIN orders AS o2 ON TRUE
~~~

### 3.2. Always assign clear aliases

A subquery in `FROM` should have a readable alias:

~~~sql
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
    LIMIT 1
) AS latest_order ON TRUE
~~~

The alias `latest_order` is used to reference its columns outside:

~~~sql
SELECT latest_order.order_id
~~~

When two tables share column names like `order_id` or `customer_id`, explicitly writing `c.customer_id` and `o.customer_id` prevents ambiguity, especially in multi-stage queries.

### 3.3. LATERAL is not a separate JOIN type

`LATERAL` **does not replace** `INNER`, `LEFT`, or `CROSS`. It enables **left-referencing capability** for the item; the JOIN type decides how rows are paired and how unmatched rows are handled.

| Syntax | Can use left-side columns? | When right side returns zero rows |
| --- | --- | --- |
| `CROSS JOIN LATERAL (...) x` | Yes | Left row is dropped |
| `JOIN LATERAL (...) x ON TRUE` | Yes | Left row is dropped |
| `LEFT JOIN LATERAL (...) x ON TRUE` | Yes | Keeps one left row; right columns are null |
| `CROSS JOIN (SELECT ...) x` | Cannot reference left like a LATERAL item | Left row is dropped if subquery is empty |

For complex queries, other join types exist and join-tree grouping affects name scope. In this lesson, we use `CROSS` and `LEFT` because they express real-world query patterns most clearly.

## 4. Creating a Practice PostgreSQL Dataset

The SQL statements below are for a **lab database**—do not run them in an environment containing data you need to keep. Assume you have permissions to create schemas and tables.

### 4.1. Creating the schema and customers table

~~~sql
CREATE SCHEMA lateral_lab;

CREATE TABLE lateral_lab.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    signup_date date NOT NULL
);

INSERT INTO lateral_lab.customers
    (customer_id, customer_name, signup_date)
VALUES
    (1, 'An',   DATE '2026-08-10'),
    (2, 'Binh', DATE '2026-08-12'),
    (3, 'Chi',  DATE '2026-08-15'),
    (4, 'Dung', DATE '2026-08-20');
~~~

Customer `Dung` intentionally **has no orders yet** so the difference between `CROSS JOIN LATERAL` and `LEFT JOIN LATERAL` is easy to observe.

### 4.2. Creating the orders table

~~~sql
CREATE TABLE lateral_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lateral_lab.customers(customer_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled')),
    amount numeric(12, 2) NOT NULL
        CHECK (amount >= 0),
    tags jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(tags) = 'array')
);

INSERT INTO lateral_lab.orders (
    order_id, customer_id, created_at,
    status, amount, tags
) VALUES
    (101, 1, '2026-09-01 09:00+07',
        'paid', 120.00, '["gift","priority"]'::jsonb),
    (102, 1, '2026-09-03 10:00+07',
        'pending', 80.00, '["review"]'::jsonb),
    (103, 1, '2026-09-05 09:00+07',
        'paid', 200.00, '["priority"]'::jsonb),
    (201, 2, '2026-09-02 08:00+07',
        'paid', 50.00, '["gift"]'::jsonb),
    (202, 2, '2026-09-06 11:00+07',
        'cancelled', 30.00, '[]'::jsonb),
    (301, 3, '2026-09-04 14:00+07',
        'pending', 90.00, '["review","fragile"]'::jsonb),
    (302, 3, '2026-09-07 15:00+07',
        'paid', 160.00, '["priority"]'::jsonb),
    (303, 3, '2026-09-07 16:00+07',
        'paid', 210.00, '["gift","priority"]'::jsonb);
~~~

### 4.3. Creating the order items table

~~~sql
CREATE TABLE lateral_lab.order_items (
    item_id integer PRIMARY KEY,
    order_id integer NOT NULL
        REFERENCES lateral_lab.orders(order_id),
    sku text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL
        CHECK (unit_price >= 0)
);

INSERT INTO lateral_lab.order_items (
    item_id, order_id, sku, quantity, unit_price
) VALUES
    (1, 101, 'PEN',   2, 10.00),
    (2, 101, 'NOTE',  1, 100.00),
    (3, 102, 'BOOK',  1, 80.00),
    (4, 103, 'BAG',   2, 100.00),
    (5, 201, 'BOOK',  1, 50.00),
    (6, 202, 'BOOK',  1, 30.00),
    (7, 301, 'GIFT',  3, 30.00),
    (8, 302, 'LAMP',  2, 80.00),
    (9, 303, 'CLOCK', 1, 100.00),
    (10, 303, 'PAD',  1, 110.00);
~~~

In this dataset:

| customer_id | Customer | Order count | Latest order | Two newest orders |
| ---: | --- | ---: | ---: | --- |
| 1 | An | 3 | 103 | 103, 102 |
| 2 | Binh | 2 | 202 | 202, 201 |
| 3 | Chi | 3 | 303 | 303, 302 |
| 4 | Dung | 0 | None | None |

The items table has two line items for orders 101 and 303, while other orders have one line item. This helps illustrate how **one row on the left can produce multiple rows on the right**.

### 4.4. Verifying the data

~~~sql
SELECT c.customer_id, c.customer_name, COUNT(o.order_id) AS n
FROM lateral_lab.customers AS c
LEFT JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

The order counts per customer are **3, 2, 3, 0**. Subsequent examples assume the sample data has not been modified.

## 5. Correlated Scalar Subquery: Fetching One Value per Row

Writing it without `LATERAL`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    (
        SELECT o.order_id
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 1
    ) AS latest_order_id
FROM lateral_lab.customers AS c
ORDER BY c.customer_id;
~~~

Result:

| customer_id | customer_name | latest_order_id |
| ---: | --- | ---: |
| 1 | An | 103 |
| 2 | Binh | 202 |
| 3 | Chi | 303 |
| 4 | Dung | `NULL` |

Because the subquery returns **one column** and uses `LIMIT 1`, it works as a **scalar expression** in `SELECT`. When there are no orders, the scalar subquery returns `NULL`.

### When does a scalar subquery become awkward?

If you need `order_id`, `created_at`, `status`, and `amount` from **the same latest order**, you could write four nearly identical correlated subqueries. However, that duplicates `WHERE`/`ORDER BY` logic and makes the query hard to maintain.

LATERAL lets you retrieve **multiple columns from the same subquery**:

~~~sql
SELECT
    c.customer_name,
    latest.order_id,
    latest.created_at,
    latest.status,
    latest.amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        o.order_id, o.created_at, o.status, o.amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
~~~

Semantically, this means "each customer along with their latest order, if any".

### Note that a scalar subquery errors when returning multiple rows

A scalar subquery used as an expression must return **at most one row**. If `LIMIT 1` is removed and a customer has multiple orders:

~~~sql
-- Can error because the subquery returns more than one row:
SELECT
    c.customer_id,
    (
        SELECT o.order_id
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS one_order_id
FROM lateral_lab.customers AS c;
~~~

PostgreSQL does not randomly pick a row when a scalar subquery returns multiple rows; that is a semantic error. When you actually need **a set of multiple rows per customer**, `LATERAL` in `FROM` is the right tool.

## 6. CROSS JOIN LATERAL: Keeping Only Rows with Matches

Fetch the **two newest orders for each customer**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.created_at,
    recent.status
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id, o.created_at, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent
ORDER BY
    c.customer_id,
    recent.created_at DESC,
    recent.order_id DESC;
~~~

The result has **6 rows**:

| customer_id | Customer | order_id | status |
| ---: | --- | ---: | --- |
| 1 | An | 103 | paid |
| 1 | An | 102 | pending |
| 2 | Binh | 202 | cancelled |
| 2 | Binh | 201 | paid |
| 3 | Chi | 303 | paid |
| 3 | Chi | 302 | paid |

**Dung does not appear**, because the subquery for `customer_id = 4` returns an empty set. `CROSS JOIN LATERAL` pairs rows with whatever rows exist on the right; if there are none, no result row is produced for that customer.

### One customer can appear multiple times

`LATERAL` does not guarantee a one-to-one output. If the subquery returns two rows for a customer, that customer appears twice in the result. If it returns 100 rows, the customer can appear 100 times.

This is especially important when the output after `LATERAL` feeds into a `SUM` or a subsequent JOIN.

### CROSS JOIN LATERAL vs. JOIN LATERAL ... ON TRUE

For returning matched rows, these two forms produce identical results:

~~~sql
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (...) AS recent
~~~

~~~sql
FROM lateral_lab.customers AS c
JOIN LATERAL (...) AS recent ON TRUE
~~~

Pick one consistent style and make the intent "only customers with results" clear. When you need to keep customers without orders, switch to `LEFT JOIN LATERAL`.

## 7. LEFT JOIN LATERAL: Keeping Customers Without Orders

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id,
    recent.created_at,
    recent.status
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.created_at, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
ORDER BY
    c.customer_id,
    recent.created_at DESC NULLS LAST,
    recent.order_id DESC NULLS LAST;
~~~

The result has **7 rows**: the same six rows as before, plus:

| customer_id | customer_name | order_id | created_at | status |
| ---: | --- | --- | --- | --- |
| 4 | Dung | `NULL` | `NULL` | `NULL` |

`LEFT JOIN` keeps **one left-side row** when the right-side subquery returns empty, filling the right-side columns with null.

### Why ON TRUE?

`ON TRUE` means no extra filter condition is added after pairing. The linking predicate is already **inside the LATERAL subquery**:

~~~sql
WHERE o.customer_id = c.customer_id
~~~

For this pattern, `LEFT JOIN LATERAL (...) AS recent ON TRUE` is the standard, readable idiom.

### Do not carelessly move the right-side filter into WHERE

Compare:

~~~sql
SELECT c.customer_id, recent.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS recent ON TRUE
WHERE recent.status = 'paid';
~~~

The condition `WHERE recent.status = 'paid'` runs **after the LEFT JOIN**:

- Customers with no orders have `recent.status = NULL` and are dropped.
- Customers whose latest order is not paid are also dropped.
- It does **not** mean "get the latest paid order".

To keep every customer and find their latest **paid** order, place the condition **inside** the `LATERAL` subquery.

## 8. Conditional Top 1: Latest Paid Order per Customer

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    paid_latest.order_id AS latest_paid_order_id,
    paid_latest.amount AS latest_paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.amount, o.created_at
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS paid_latest ON TRUE
ORDER BY c.customer_id;
~~~

Result:

| customer_id | Customer | latest_paid_order_id | latest_paid_amount |
| ---: | --- | ---: | ---: |
| 1 | An | 103 | 200.00 |
| 2 | Binh | 201 | 50.00 |
| 3 | Chi | 303 | 210.00 |
| 4 | Dung | `NULL` | `NULL` |

The `status = 'paid'` filter is applied **before `ORDER BY ... LIMIT 1` inside the subquery**. Thus, even though Binh's newest overall order is 202 (`cancelled`), the query picks the latest paid order, 201.

**Design rule:** if the requirement is "top N rows matching condition X per group", condition X must be applied to the **input set being ranked**, before limiting to N. Changing filter order can break business logic even while SQL syntax remains valid.

### Why does LIMIT need ORDER BY?

~~~sql
LIMIT 1
~~~

alone does not define "newest". Without an appropriate `ORDER BY`, PostgreSQL can return any arbitrary row depending on the plan and storage state.

If multiple orders share the same `created_at`, add `order_id DESC` as a tie-breaker. Choose a deterministic tie-breaking rule aligned with business logic rather than relying on implicit table order.

## 9. Inner LIMIT Inside LATERAL vs. Outer LIMIT

Consider two queries:

~~~sql
-- A: at most two orders FOR EACH customer.
SELECT c.customer_id, recent.order_id
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS recent;
~~~

~~~sql
-- B: limits the ENTIRE joined result to two rows.
SELECT c.customer_id, o.order_id
FROM lateral_lab.customers AS c
JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 2;
~~~

In A, `LIMIT 2` sits **inside the correlated subquery**, giving at most two orders **per customer**.

In B, `LIMIT 2` sits **at the outermost level**, returning only two rows for the **entire result**, without guaranteeing two orders per customer.

This is why `LATERAL` is especially convenient for **top-N-per-group** problems.

## 10. LATERAL with Aggregates: Per-Customer Statistics

A `LATERAL` subquery does not have to return multiple rows; it can return **one aggregate row per customer**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    stats.total_orders,
    stats.paid_orders,
    stats.paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS total_orders,
        COUNT(*) FILTER (
            WHERE o.status = 'paid'
        ) AS paid_orders,
        COALESCE(
            SUM(o.amount) FILTER (
                WHERE o.status = 'paid'
            ),
            0::numeric
        ) AS paid_amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS stats ON TRUE
ORDER BY c.customer_id;
~~~

Result:

| Customer | total_orders | paid_orders | paid_amount |
| --- | ---: | ---: | ---: |
| An | 3 | 2 | 320.00 |
| Binh | 2 | 1 | 50.00 |
| Chi | 3 | 2 | 370.00 |
| Dung | 0 | 0 | 0.00 |

In the subquery:

~~~sql
SELECT COUNT(*), SUM(...)
FROM lateral_lab.orders AS o
WHERE o.customer_id = c.customer_id
~~~

there is no `GROUP BY`. It aggregates over the entire set of orders for that customer.

### Why does a customer with no orders still receive a stats row?

An aggregate query **without `GROUP BY`** such as:

~~~sql
SELECT COUNT(*) AS n
FROM lateral_lab.orders
WHERE customer_id = -1;
~~~

still returns **one row** containing `n = 0`. `SUM(...)` over an empty set normally returns `NULL`, so the example above uses `COALESCE` to display 0 where business rules call for it.

Because the aggregate subquery automatically emits **one row** for a customer without orders, in this specific case `CROSS JOIN LATERAL` would also retain Dung. **Do not generalize** that `CROSS JOIN LATERAL` keeps left rows in general: non-aggregate subqueries can return zero rows and drop customers.

### When is LATERAL unnecessary for statistics?

The same result can be achieved with `LEFT JOIN` and `GROUP BY`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS total_orders,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
~~~

If computing statistics **for all customers**, the `GROUP BY` approach can be cleaner and have a more efficient execution plan depending on the data. `LATERAL` is particularly useful when the left-dependent subquery uses `ORDER BY ... LIMIT`, selects a specialized subset, or returns complex structures.

## 11. Correlated EXISTS and NOT EXISTS: When Only Existence Matters

If the requirement is **which customers have ever had a paid order**, `LATERAL` is not necessarily needed.

~~~sql
SELECT
    c.customer_id,
    c.customer_name
FROM lateral_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
)
ORDER BY c.customer_id;
~~~

Result: An, Binh, and Chi.

`EXISTS` only needs to know whether the subset has **at least one row**; PostgreSQL can optimize it as a semi-join without emitting all order rows.

Customers with no orders:

~~~sql
SELECT c.customer_id, c.customer_name
FROM lateral_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Result: Dung.

### EXISTS or LEFT JOIN LATERAL?

| Goal | Pattern usually suited |
| --- | --- |
| Only filter whether customer has paid orders | `EXISTS` |
| Only filter customers with no orders | `NOT EXISTS` |
| Retrieve details of the latest paid order | `LEFT JOIN LATERAL ... ORDER BY ... LIMIT 1` |
| Retrieve the two newest orders per customer | `JOIN LATERAL ... LIMIT 2` |
| Compute multiple aggregates over a customer's rows | `GROUP BY` or LATERAL aggregate depending on workload |

`LATERAL` is not the sole answer for every correlated query. Pick the simplest construct that expresses the exact output needed.

## 12. Multi-Stage LATERAL: Using One Stage's Output as the Next Stage's Input

A useful pattern is **chaining LATERALs**:

1. Find the customer's latest order.
2. Use that `order_id` to summarize the line items on that order.

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    latest.order_id AS latest_order_id,
    latest.status AS latest_status,
    item_stats.item_lines,
    item_stats.total_quantity
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status, o.created_at
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS item_lines,
        COALESCE(SUM(i.quantity), 0) AS total_quantity
    FROM lateral_lab.order_items AS i
    WHERE i.order_id = latest.order_id
) AS item_stats ON TRUE
ORDER BY c.customer_id;
~~~

The result reads as follows:

| Customer | latest_order_id | latest_status | item_lines | total_quantity |
| --- | ---: | --- | ---: | ---: |
| An | 103 | paid | 1 | 2 |
| Binh | 202 | cancelled | 1 | 1 |
| Chi | 303 | paid | 2 | 2 |
| Dung | `NULL` | `NULL` | 0 | 0 |

`item_stats` can see the `latest` alias because `latest` appears before it in the join tree. For Dung, `latest.order_id` is `NULL`; `i.order_id = NULL` matches zero rows, yet an aggregate without `GROUP BY` still returns `COUNT(*) = 0`.

### What happens if the first stage uses CROSS JOIN LATERAL?

If you change the first `LEFT JOIN LATERAL` to `CROSS JOIN LATERAL`, Dung is dropped **right at the first stage**, leaving no row to pass to the second stage. Decide whether to keep or drop empty groups **at each step**.

### Pay attention to column qualification

In multi-stage chains, `order_id` can exist in both `orders` and `order_items`. Writing `latest.order_id` and `i.order_id` explicitly prevents ambiguous-column errors and makes dependencies clear.

## 13. LATERAL with Set-Returning Functions

Some PostgreSQL functions return **multiple rows**, not a single scalar. When the function's arguments depend on a preceding row, `LATERAL` expresses this naturally.

Example:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    dates.day_ts::date AS calendar_day
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL generate_series(
    c.signup_date::timestamp,
    (c.signup_date + 2)::timestamp,
    interval '1 day'
) AS dates(day_ts)
ORDER BY c.customer_id, dates.day_ts;
~~~

Each customer generates **three days**: their signup date, the next day, and the second day after signup.

| Customer | signup_date | Generated days |
| --- | --- | --- |
| An | 2026-08-10 | Aug 10, 11, 12 |
| Binh | 2026-08-12 | Aug 12, 13, 14 |
| Chi | 2026-08-15 | Aug 15, 16, 17 |
| Dung | 2026-08-20 | Aug 20, 21, 22 |

`generate_series` returns multiple rows; each row from `customers` produces its own date range based on `signup_date`.

### Functions in FROM can reference left items without writing LATERAL

PostgreSQL allows **function arguments** in `FROM` to reference preceding `FROM` items even without an explicit `LATERAL` keyword:

~~~sql
FROM lateral_lab.customers AS c
CROSS JOIN generate_series(
    c.signup_date::timestamp,
    (c.signup_date + 2)::timestamp,
    interval '1 day'
) AS d(day_ts)
~~~

This is special behavior for **function calls in FROM**. For a **SELECT subquery in FROM** that references left-side rows, write `LATERAL` explicitly.

In documentation or team codebases, many developers still write `LATERAL` on functions to make the "row-dependent function" intent explicit.

## 14. JSONB Arrays and LATERAL: Expanding Arrays into Rows

The `orders` table has a `tags jsonb` column where each value is a JSON array.

For example, order 101:

~~~json
["gift", "priority"]
~~~

To return each tag as its own row:

~~~sql
SELECT
    o.order_id,
    tag.value AS tag
FROM lateral_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.tags) AS tag(value)
ORDER BY o.order_id, tag.value;
~~~

`jsonb_array_elements_text` returns array elements as text.

For order 101:

| order_id | tag |
| ---: | --- |
| 101 | gift |
| 101 | priority |

Order 202 has `tags = []`, so the function returns **zero rows**. With `CROSS JOIN LATERAL`, **order 202 disappears from the result**.

### LEFT JOIN LATERAL keeps orders with empty arrays

~~~sql
SELECT
    o.order_id,
    tag.value AS tag
FROM lateral_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(o.tags) AS tag(value)
    ON TRUE
ORDER BY o.order_id, tag.value NULLS LAST;
~~~

Now order 202 appears with `tag = NULL`. Just like customers without orders, this is the **null-extending** behavior of `LEFT JOIN`.

### WITH ORDINALITY: preserving element position

~~~sql
SELECT
    o.order_id,
    tag.position,
    tag.value AS tag
FROM lateral_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.tags)
        WITH ORDINALITY AS tag(value, position)
ORDER BY o.order_id, tag.position;
~~~

`WITH ORDINALITY` adds a 1-based element index (**starting at 1**). For order 101:

| order_id | position | tag |
| ---: | ---: | --- |
| 101 | 1 | gift |
| 101 | 2 | priority |

This matters whenever array order is meaningful. Do not simply `ORDER BY tag.value` and treat it as the original JSON order.

### What if the JSON value is not an array?

`jsonb_array_elements_text` expects valid JSON array input (a SQL NULL produces zero rows). In the sample dataset, `CHECK (jsonb_typeof(tags) = 'array')` and `NOT NULL` guard the data shape.

If real-world JSONB data can be an object, scalar, or unexpected type, array-expansion functions can raise errors. Normalize data or check/handle shapes before expanding.

## 15. UNNEST and SQL Arrays

PostgreSQL has native SQL array types such as `text[]` or `integer[]`, distinct from JSONB arrays. The `unnest` function can also return multiple rows.

Example of a SKU list per store:

~~~sql
WITH stores(store_id, sku_codes) AS (
    VALUES
        (1, ARRAY['A','B','C']::text[]),
        (2, ARRAY['D']::text[]),
        (3, ARRAY[]::text[])
)
SELECT
    s.store_id,
    sku.sku_code
FROM stores AS s
LEFT JOIN LATERAL unnest(s.sku_codes)
    AS sku(sku_code) ON TRUE
ORDER BY s.store_id, sku.sku_code;
~~~

Result:

| store_id | sku_code |
| ---: | --- |
| 1 | A |
| 1 | B |
| 1 | C |
| 2 | D |
| 3 | `NULL` |

Switching `LEFT JOIN LATERAL` to `CROSS JOIN LATERAL` drops store 3 because its array is empty.

### Multiple parallel arrays require care

PostgreSQL supports certain multi-array `unnest` forms, but positional pairing, mismatched array lengths, and null handling must be understood before use. For important relational data with multiple attributes per item, a **normalized child table** is usually easier to protect with `FOREIGN KEY`, `CHECK`, and indexes than parallel arrays.

## 16. LATERAL Can Also Aggregate Multiple Rows into One Value

A `LATERAL` does not have to **increase the row count** of the output. We can pack the top 2 list into a JSONB array on **one row per customer**:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        recent.orders_json,
        '[]'::jsonb
    ) AS recent_orders
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
        jsonb_build_object(
            'order_id', x.order_id,
            'status', x.status,
            'amount', x.amount
        )
        ORDER BY x.created_at DESC, x.order_id DESC
    ) AS orders_json
    FROM (
        SELECT
            o.order_id, o.created_at, o.status, o.amount
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 2
    ) AS x
) AS recent ON TRUE
ORDER BY c.customer_id;
~~~

What each layer does:

1. Subquery `x` selects at most **two newest orders per customer**.
2. `jsonb_agg(...)` aggregates those selected rows into a JSONB array.
3. `LEFT JOIN LATERAL` attaches the array to the current customer.
4. `COALESCE(..., '[]'::jsonb)` returns an empty array for Dung.

This prepares data for an API returning:

~~~json
{
  "customer_id": 1,
  "customer_name": "An",
  "recent_orders": [
    {"order_id": 103, "status": "paid", "amount": 200.00},
    {"order_id": 102, "status": "pending", "amount": 80.00}
  ]
}
~~~

The JSON example illustrates **the output structure**, not a byte-for-byte guarantee of object key ordering or numeric formatting by a specific driver/JSON serializer. `jsonb` does not preserve **object key order**, whereas **array element order** is specified by `ORDER BY` inside `jsonb_agg`.

### Why not just write LIMIT 2 after jsonb_agg?

~~~sql
SELECT jsonb_agg(...)
FROM lateral_lab.orders
LIMIT 2;
~~~

`LIMIT 2` outside the aggregate **does not limit how many rows enter `jsonb_agg`**; the aggregate already collapses rows into one result before the outer limit applies. To get "two orders, then aggregate", place `ORDER BY ... LIMIT 2` in a subquery before `jsonb_agg`.

## 17. Be Careful When Chaining Multiple Multi-Row LATERALs

Suppose a customer has two recent orders, and you attach another three-row independent tag/result set afterward. Joined tables follow relational pairing; if two independent `LATERAL`s each return multiple rows without a relationship between them, row counts get **multiplied**.

Model:

~~~text
One customer
  |
  +-- recent_orders => 2 rows
  |
  +-- special_tags  => 3 rows
  |
  +-- independent pair => 2 x 3 = 6 rows
~~~

Example:

~~~sql
SELECT
    c.customer_id,
    r.order_id,
    t.tag
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS r
CROSS JOIN LATERAL (
    SELECT tag
    FROM unnest(ARRAY['a','b','c']::text[]) AS q(tag)
) AS t
WHERE c.customer_id = 1
ORDER BY r.order_id, t.tag;
~~~

The result has **6 rows** for customer An: 2 orders × 3 independent tags.

**This is not a PostgreSQL bug:** it is standard set-product semantics. If you only want each order's own actual tags, the trailing subquery/function must **correlate with `r.order_id` or columns of that order**:

~~~sql
SELECT
    c.customer_id,
    r.order_id,
    tag.value AS tag
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id, o.tags
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS r
LEFT JOIN LATERAL
    jsonb_array_elements_text(r.tags)
        AS tag(value) ON TRUE
WHERE c.customer_id = 1
ORDER BY r.order_id, tag.value;
~~~

Here, tags are expanded **from that specific order's `tags` array**, not from an unrelated shared set.

### Aggregation rule

Before writing `COUNT(*)` or `SUM(amount)` after multiple `LATERAL`s, ask:

- Does one row still represent **one order**, or has it become **one order–tag pair**?
- How many times can a single business entity appear?
- If summing order amounts, should amounts be summed **before expanding tags**?

`COUNT(DISTINCT order_id)` can help count unique orders after row multiplication, but `SUM(DISTINCT amount)` **is not a general fix** because two distinct orders can share the exact same amount.

## 18. LATERAL vs. ROW_NUMBER for Top-N-per-Group

Besides `LATERAL`, PostgreSQL can use the `ROW_NUMBER()` window function to rank each group.

~~~sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM lateral_lab.orders AS o
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id,
    r.created_at,
    r.status
FROM lateral_lab.customers AS c
LEFT JOIN ranked_orders AS r
    ON r.customer_id = c.customer_id
   AND r.rn <= 2
ORDER BY c.customer_id, r.rn NULLS LAST;
~~~

The result matches the `LEFT JOIN LATERAL ... LIMIT 2` example: An, Binh, and Chi each have up to two orders, and Dung has one null row.

### Two processing approaches

~~~text
LATERAL:
  Scan target customers
       -> for each customer, find top 2 matching orders

ROW_NUMBER:
  Rank orders per customer_id
       -> keep rn <= 2
       -> join back to customers
~~~

This is a **logical model**; PostgreSQL decides the physical execution plan.

| Scenario | LATERAL often worth considering | ROW_NUMBER often worth considering |
| --- | --- | --- |
| Fetching top 1–3 for a small filtered set of customers | Yes | May rank far more orders than needed |
| Index exists on `(customer_id, created_at DESC)` | Can leverage lookup + LIMIT | Can also leverage index order depending on plan |
| Need top N for very many customers | Measure lookup count | A single pass over orders may fit well |
| Need rank numbers for all orders | Not its primary purpose | Very suitable |
| Need to keep customers with no orders | `LEFT JOIN LATERAL` | `LEFT JOIN` against ranked result |

There is no "always faster" pattern. Run `EXPLAIN (ANALYZE, BUFFERS)` on representative data with the exact same customer filter and conditions.

## 19. LATERAL vs. DISTINCT ON for Top 1

PostgreSQL provides `DISTINCT ON` syntax to select **the first row** of each group under a given sort order:

~~~sql
SELECT DISTINCT ON (o.customer_id)
    o.customer_id,
    o.order_id,
    o.created_at,
    o.status
FROM lateral_lab.orders AS o
ORDER BY
    o.customer_id,
    o.created_at DESC,
    o.order_id DESC;
~~~

Returns the latest order for customers 1, 2, and 3; no row for Dung since Dung has no orders.

To keep all customers:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    latest.order_id,
    latest.status
FROM lateral_lab.customers AS c
LEFT JOIN (
    SELECT DISTINCT ON (o.customer_id)
        o.customer_id, o.order_id, o.status, o.created_at
    FROM lateral_lab.orders AS o
    ORDER BY
        o.customer_id,
        o.created_at DESC,
        o.order_id DESC
) AS latest
    ON latest.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

### Rules of DISTINCT ON

In PostgreSQL, `DISTINCT ON` expressions must match the leftmost expressions of `ORDER BY` per syntax rules. To get one latest order per customer:

~~~sql
DISTINCT ON (customer_id)
ORDER BY customer_id, created_at DESC, order_id DESC
~~~

`ORDER BY` decides **which row is kept** in each group. Without an explicit order, "the first row" has no stable business meaning.

### When to choose which?

- `DISTINCT ON` is concise when you need **one row** per group.
- `ROW_NUMBER()` is flexible when you need top N, rankings, or multiple window calculations.
- `LATERAL` excels when top N depends on a **filtered outer entity set**, has per-row limits, or needs correlated subqueries/functions.

Never switch syntax purely on a rumor about speed; verify both results and plans.

## 20. Creating Suitable Indexes for LATERAL Top-N

Query:

~~~sql
SELECT c.customer_id, recent.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE;
~~~

filters by equality on `customer_id` and sorts by `created_at DESC, order_id DESC`. A B-tree index worth evaluating:

~~~sql
CREATE INDEX idx_orders_customer_recent
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

On a large orders table, PostgreSQL can use this index to:

1. Jump directly to entries for the target `customer_id`.
2. Read in an order matching `ORDER BY`.
3. Stop right after fetching 2 rows if the plan and predicates allow.

This is where the `LATERAL ... ORDER BY ... LIMIT N` pattern frequently shines.

### If only looking for the latest paid order

Another option to evaluate:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
WHERE status = 'paid';
~~~

This is a **partial index** containing only rows with `status = 'paid'`. It can help if the application frequently runs:

~~~sql
WHERE o.customer_id = c.customer_id
  AND o.status = 'paid'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 1
~~~

However, do not blindly create both indexes: every index takes disk space and adds write overhead. If nearly all orders are paid or the workload rarely uses that query, a partial index may not pay for itself.

### Should INCLUDE be used?

If the query also needs `status` and `amount`, you can consider a covering index:

~~~sql
CREATE INDEX idx_orders_recent_include
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, amount);
~~~

This is an **alternative to test**, not a rule that you must add a third index. Index-only scans are only possible when all needed columns are in the index and **visibility map conditions** allow; `INCLUDE` increases index size. Evaluate using real plans and I/O counts.

## 21. Reading EXPLAIN for LATERAL Queries

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    r.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS r ON TRUE
ORDER BY c.customer_id;
~~~

In a typical plan, you might see:

~~~text
Nested Loop Left Join
  -> Scan customers
  -> Limit
       -> Index Scan using idx_orders_customer_recent
            Index Cond: (customer_id = c.customer_id)
~~~

The snippet above is an **illustrative sketch**, not guaranteed `EXPLAIN` output. On tiny sample tables, PostgreSQL may pick `Seq Scan` and `Sort` because that is cheaper than using an index.

### What to read

| EXPLAIN component | Interpretation |
| --- | --- |
| `Nested Loop` | Shows the inner side being evaluated with parameters from the outer side |
| `loops` | Number of times the node executed per instrumentation; read alongside rows/time |
| `Index Cond` | Predicates pushed into the index lookup |
| `Filter` | Remaining filter applied at the node |
| `Limit` | Caps rows in the corresponding inner subset |
| `Sort` | PostgreSQL must sort if the access path does not already yield the needed order |
| `actual rows` / `actual time` | Measured rows and timings from execution |
| `BUFFERS` | Buffer hits/reads as reported by PostgreSQL |

Read **`loops` together with `actual rows`**: displayed row counts for a node are averages per loop; never multiply or add carelessly when comparing costs.

### Does LATERAL always execute physically once per row?

Not necessarily for every query. `LATERAL` defines **referencing capability and result semantics**; the planner can rewrite expressions, decorrelate joins, or choose other valid execution steps. For `ORDER BY ... LIMIT` dependent on an outer row, a parameterized nested loop index scan is common, though never guaranteed.

## 22. Database-Side N+1 Risk

Applications suffer from the **N+1 query** pattern when they:

1. Send SQL to fetch 10,000 customers.
2. Loop in Java and send 10,000 additional SQL queries to fetch each customer's latest order.

`LATERAL` collapses that into **one SQL statement from the client**, eliminating thousands of network round trips.

However, it does not erase **lookup cost inside the database**. For 10,000 customers, a nested loop plan may still execute thousands of index lookups. If the query ends up scanning nearly the entire orders table, `ROW_NUMBER` or `DISTINCT ON` is worth benchmarking against it.

### When the left side is very large

For example, a report over 2 million customers:

~~~sql
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (...) AS recent ON TRUE
~~~

Each customer row may trigger dependent work per the plan. Therefore:

- Filter down to the customers actually needed before running top-N.
- Create proper indexes for correlation predicates.
- Avoid CPU-heavy functions or external calls repeated millions of times.
- Consider pre-aggregation, materialized views, or batch reporting if real-time data is unnecessary.

**A single SQL statement can still be very expensive.** Reducing network round trips alone does not guarantee the query is fast.

## 23. Keep the Correlation Condition Inside the Subquery

A serious mistake is forgetting:

~~~sql
WHERE o.customer_id = c.customer_id
~~~

When omitted:

~~~sql
SELECT
    c.customer_id,
    latest.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE;
~~~

The subquery is no longer correlated and returns the **single newest order in the entire system** for every customer. Writing `LATERAL` does not automatically insert a `customer_id` filter for you.

### Do not confuse the correlation condition with top-N selection

In top-N queries, the correlation condition **must sit inside the subquery or dependent definition** so each subset is limited per customer.

Wrong semantics:

~~~sql
-- Takes the 2 newest orders across the whole system, then matches customers:
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, customer_id
    FROM lateral_lab.orders
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS x ON x.customer_id = c.customer_id;
~~~

This does not "fetch the 2 newest orders for each customer": `LIMIT 2` ran **globally** before `ON x.customer_id = c.customer_id` matched customers.

Intended form:

~~~sql
LEFT JOIN LATERAL (
    SELECT order_id, customer_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS x ON TRUE
~~~

## 24. JOIN Order and Name Scope

`FROM` items can be joined using commas or `JOIN` operators. **Join-tree grouping** affects which aliases a `LATERAL` item is allowed to see. Moreover, explicit `JOIN` syntax has different associativity/precedence rules than comma-separated tables.

To avoid hard-to-read bugs:

- Prefer explicit `JOIN ... ON ...` over mixing commas.
- Place data-providing items **to the left** of the `LATERAL` item using them.
- If correlating against two joined tables, place `LATERAL` after a well-structured join tree.
- Use clear aliases and avoid unqualified column names when multiple tables are present.

Example:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    item_stat.lines
FROM lateral_lab.customers AS c
JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS lines
    FROM lateral_lab.order_items AS i
    WHERE i.order_id = o.order_id
) AS item_stat ON TRUE
ORDER BY c.customer_id, o.order_id;
~~~

Here `item_stat` can read `o.order_id` because `o` is part of the left join tree. There is no need to reference `c.customer_id` if unused.

### Avoid SELECT *

Writing:

~~~sql
SELECT *
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (...) AS x ON TRUE;
~~~

in large systems can produce duplicate column names and easily break when schemas evolve. Explicitly select needed columns and give clear output aliases, especially when mapping into Java DTOs or APIs.

## 25. LATERAL with LEFT JOIN: NULL Considerations

Look at:

~~~sql
SELECT
    c.customer_id,
    r.order_id,
    r.status
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS r ON TRUE
ORDER BY c.customer_id;
~~~

For Dung, both `r.order_id` and `r.status` are `NULL`. Do not assume:

~~~sql
r.status IS NULL
~~~

always means "no orders", if a real schema allows `status` to be null. Check a guaranteed non-null key on the right-hand row such as `r.order_id IS NULL`, where `order_id` is a `PRIMARY KEY` and therefore non-null for real rows.

### COALESCE on display values

~~~sql
COALESCE(r.status, 'no_orders') AS display_status
~~~

can be handy for UI display, but keep **an order's business status** separate from **"customer has no orders"**. Never store `'no_orders'` in `orders.status` if it is not a valid order state.

## 26. LATERAL and Pre-Filtered Left-Side Data

Suppose a dashboard only needs customers who signed up on or after August 12:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    recent.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 2
) AS recent ON TRUE
WHERE c.signup_date >= DATE '2026-08-12'
ORDER BY c.customer_id, recent.order_id;
~~~

On the sample data, An (Aug 10) is excluded; Binh, Chi, and Dung remain. The optimizer can apply the `customers` filter before evaluating the `LATERAL` side.

When the left table is huge and only a small slice is needed, **narrowing down the left set early** is a major lever to reduce total work.

### Paginating on the customer side

If an API returns 20 customers per page with 2 newest orders each, determine:

1. A stable pagination order for customers (e.g., `customer_id`).
2. Which 20 customers belong to the page.
3. Only then fetch the top 2 orders **for each customer on that page**.

Example:

~~~sql
WITH page_customers AS (
    SELECT customer_id, customer_name
    FROM lateral_lab.customers
    ORDER BY customer_id
    LIMIT 20
)
SELECT
    c.customer_id,
    c.customer_name,
    r.order_id
FROM page_customers AS c
LEFT JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS r ON TRUE
ORDER BY c.customer_id, r.order_id DESC NULLS LAST;
~~~

Putting `LIMIT 20` **at the outermost level after the join** limits **customer–order rows**, not necessarily 20 customers. That is a very common pagination bug.

## 27. Common Mistakes

### Mistake 1: Using a correlated FROM subquery and forgetting LATERAL

A subquery in `FROM` cannot see preceding aliases without `LATERAL`. Correlated scalar subqueries in `SELECT` or `EXISTS` have different scoping rules and do not take this keyword.

### Mistake 2: Using CROSS JOIN LATERAL when empty groups should be kept

If the subquery returns zero rows, `CROSS JOIN LATERAL` drops the left row. Use `LEFT JOIN LATERAL ... ON TRUE` when keeping customers without orders or orders with empty arrays.

### Mistake 3: Moving the selection filter into WHERE outside LEFT JOIN

`WHERE r.status = 'paid'` drops rows where `r.status` is null and can eliminate empty groups. If the requirement is "latest paid order", filter paid **inside the subquery** before `LIMIT`.

### Mistake 4: Placing LIMIT at the outermost level

`LIMIT 2` on the final output keeps only 2 rows total, **not 2 rows per group**. For `LATERAL` top-N, the limit belongs inside the correlated subquery.

### Mistake 5: ORDER BY without deterministic tie-breaking

If two orders share the same timestamp, `ORDER BY created_at DESC` alone can choose differently depending on data layout or plans. Add a stable secondary key like `order_id DESC`.

### Mistake 6: Assuming LATERAL creates correlation automatically

`LATERAL` only grants reference visibility; it does not write `WHERE o.customer_id = c.customer_id` for you. Forgetting that condition gives every customer the system-wide newest order.

### Mistake 7: Stacking multiple LATERALs into a Cartesian product

Two independent 2-row and 3-row results produce 6 rows per left-hand entity. Verify granularity before summing or counting.

### Mistake 8: Summing after expanding JSONB tags

If an order has multiple tags, `SUM(o.amount)` after `jsonb_array_elements_text` adds the amount once **per tag**. Aggregate at the order grain before expanding or ensure each order contributes only once.

### Mistake 9: Assuming LATERAL is always faster than window functions

With few customers and good indexes, correlated `LIMIT` can be efficient. With very many customers, lookup volume can be large. Use `EXPLAIN` and representative data rather than guessing.

### Mistake 10: Ignoring NULLs from scalar subqueries and LEFT JOIN

A scalar subquery with zero rows yields `NULL`; a `LEFT JOIN LATERAL` with zero matches produces null right-hand columns. Check `order_id` or a reliable non-null key to distinguish missing rows.

### Mistake 11: Using ROW_NUMBER FILTER

`ROW_NUMBER() FILTER (...)` is invalid because `FILTER` applies to aggregates, not arbitrary window functions. To rank only paid orders, filter in a CTE first and then apply `ROW_NUMBER()`.

### Mistake 12: Mixing commas and JOINs without tracking scope

A `LATERAL` item can only reference valid preceding items in the `FROM` tree. Use explicit joins and clear aliases to avoid missing-column errors or wrong row counts.

### Mistake 13: Thinking one SQL query replacing N+1 is automatically cheap

`LATERAL` eliminates network round trips, yet it can still perform thousands of index lookups or invoke expensive functions repeatedly. Inspect the plan and bound the left-side input properly.

## 28. Practice Exercises

These exercises use the `lateral_lab` schema from Section 4. Predict row counts and empty-set behavior before running queries.

### Exercise 1. Latest order per customer

Write `LEFT JOIN LATERAL` to return **at most one newest order** per customer, including `order_id`, `status`, and `amount`. Customer Dung must appear.

### Exercise 2. Two newest orders

Write `CROSS JOIN LATERAL` to fetch up to two newest orders per customer. How many rows are returned? Which customer is missing?

### Exercise 3. Keeping customers with no orders

Convert Exercise 2 to `LEFT JOIN LATERAL`. How many rows are returned? What values do the order columns have for Dung?

### Exercise 4. Latest paid order

Write `LEFT JOIN LATERAL` to find the latest **paid** order for each customer. For Binh, which order is selected and why not order 202?

### Exercise 5. Correlated scalar subquery

Without using `LATERAL`, write a scalar subquery in `SELECT` counting orders per customer. If there are no orders, what is the count?

### Exercise 6. EXISTS and NOT EXISTS

Write two queries: (a) customers with at least one paid order; (b) customers with no orders at all. Why is `EXISTS` suited when only a yes/no check is needed?

### Exercise 7. Per-customer statistics

Use `LEFT JOIN LATERAL` with aggregates to return `total_orders`, `paid_orders`, and `paid_amount` per customer. What are the paid totals for An and Chi?

### Exercise 8. Second LATERAL stage

For each customer, retrieve the newest order and then count the `order_items` rows for that order using a second `LEFT JOIN LATERAL`. What `item_lines` value does Dung receive when using `COUNT(*)`?

### Exercise 9. Expanding JSONB tags

Write a query expanding each order's `tags` into rows with `jsonb_array_elements_text`. Use `WITH ORDINALITY` to keep tag positions. Why does order 202 disappear with `CROSS JOIN`?

### Exercise 10. Keeping orders with no tags

Convert Exercise 9 to `LEFT JOIN LATERAL ... ON TRUE`. Is order 202 kept, and what value does `tag` have?

### Exercise 11. Inner vs. outer LIMIT

Do the following two queries have the same meaning?

~~~sql
-- A
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT ...
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    LIMIT 2
) AS x
~~~

~~~sql
-- B
FROM lateral_lab.customers AS c
JOIN lateral_lab.orders AS o
    ON o.customer_id = c.customer_id
LIMIT 2
~~~

If not, explain how to fix case B to achieve top 2 per customer.

### Exercise 12. Comparing ROW_NUMBER

Write a query using `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at DESC, order_id DESC)` to fetch the two newest orders per customer, then join back to `customers` so Dung is preserved.

### Exercise 13. DISTINCT ON

Use `DISTINCT ON (customer_id)` to fetch the newest order for each customer **who has orders**. Why does this query not automatically return Dung?

### Exercise 14. Order totals when expanding tags

Order 101 has `amount = 120` and two tags. If you expand JSONB with `CROSS JOIN LATERAL` and run `SUM(o.amount)`, how much does order 101 contribute? Describe how to avoid double counting when summing order amounts.

### Exercise 15. Index for top-N

An `orders` table has 20 million rows. The critical query is "fetch the three newest orders for customer X". Propose a B-tree index for the `customer_id` predicate and `created_at DESC, order_id DESC` order. Why choose that column ordering?

### Exercise 16. EXPLAIN

A `LEFT JOIN LATERAL ... LIMIT 2` query shows `Nested Loop Left Join` with an inner `Index Scan` and `loops = 10000`. What does that suggest? Can you conclude the query is slow solely from the loop count?

### Exercise 17. Expanding a SQL array

Given `sku_codes text[]`, write `LEFT JOIN LATERAL unnest(sku_codes)` to display SKUs while retaining rows with an empty array.

### Exercise 18. Building top-2 JSON for an API

Write `LATERAL` returning a JSONB array of each customer's newest orders (at most two), returning `[]` for customers with no orders. Why is a subquery limiting top 2 needed before `jsonb_agg`?

### Exercise 19. Filtering at the wrong stage

Explain the difference between:

~~~sql
LEFT JOIN LATERAL (
    SELECT *
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC
    LIMIT 1
) AS x ON TRUE
WHERE x.status = 'paid'
~~~

and:

~~~sql
LEFT JOIN LATERAL (
    SELECT *
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
    ORDER BY created_at DESC
    LIMIT 1
) AS x ON TRUE
~~~

### Exercise 20. Choosing a technique

For each requirement, choose `EXISTS`, scalar subquery, `LATERAL`, `ROW_NUMBER`, or `DISTINCT ON`, and explain: (a) whether a customer has any order; (b) a single newest order ID; (c) the three newest orders for 20 selected customers; (d) the rank of every order; (e) one newest order per customer who has orders.

## 29. Solution Hints

### Exercise 1. Latest order with LEFT JOIN

~~~sql
SELECT
    c.customer_id, c.customer_name,
    latest.order_id, latest.status, latest.amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id, o.status, o.amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
ORDER BY c.customer_id;
~~~

The result has 4 rows; Dung has null columns for `latest`.

### Exercises 2 and 3. Top 2

~~~sql
-- Exercise 2: six rows, excluding Dung.
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS x
ORDER BY c.customer_id, x.order_id DESC;
~~~

~~~sql
-- Exercise 3: seven rows, including Dung with null order_id.
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 2
) AS x ON TRUE
ORDER BY c.customer_id, x.order_id DESC NULLS LAST;
~~~

### Exercise 4. Latest paid

~~~sql
SELECT c.customer_id, x.order_id
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS x ON TRUE
ORDER BY c.customer_id;
~~~

Binh gets order 201; order 202 has status `cancelled`, so it is filtered out **before selecting latest**.

### Exercise 5. Correlated scalar count

~~~sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS order_count
FROM lateral_lab.customers AS c
ORDER BY c.customer_id;
~~~

Results: 3, 2, 3, 0. A `COUNT(*)` aggregate without GROUP BY returns 0 when the filtered set is empty.

### Exercise 6. EXISTS / NOT EXISTS

~~~sql
SELECT c.customer_name
FROM lateral_lab.customers AS c
WHERE EXISTS (
    SELECT 1 FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
~~~

~~~sql
SELECT c.customer_name
FROM lateral_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1 FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

Results are An/Binh/Chi and Dung respectively. There is no need to pull order rows into the result just to check existence.

### Exercise 7. Aggregate per customer

~~~sql
SELECT
    c.customer_name,
    x.n_all,
    x.n_paid,
    x.paid_amount
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT
        COUNT(*) AS n_all,
        COUNT(*) FILTER (WHERE status = 'paid') AS n_paid,
        COALESCE(
            SUM(amount) FILTER (WHERE status = 'paid'),
            0::numeric
        ) AS paid_amount
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
) AS x ON TRUE
ORDER BY c.customer_id;
~~~

Paid totals: An = `320` and Chi = `370`.

### Exercise 8. Chained LATERAL

~~~sql
SELECT c.customer_id, latest.order_id, stats.lines
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT o.order_id
    FROM lateral_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 1
) AS latest ON TRUE
LEFT JOIN LATERAL (
    SELECT COUNT(*) AS lines
    FROM lateral_lab.order_items AS i
    WHERE i.order_id = latest.order_id
) AS stats ON TRUE
ORDER BY c.customer_id;
~~~

Dung gets `lines = 0`.

### Exercises 9 and 10. JSONB array

~~~sql
-- Exercise 9: omits order 202 because tags is an empty array.
SELECT
    o.order_id, t.position, t.tag
FROM lateral_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(o.tags)
        WITH ORDINALITY AS t(tag, position)
ORDER BY o.order_id, t.position;
~~~

~~~sql
-- Exercise 10: retains order 202 with null tag/position.
SELECT
    o.order_id, t.position, t.tag
FROM lateral_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(o.tags)
        WITH ORDINALITY AS t(tag, position)
    ON TRUE
ORDER BY o.order_id, t.position NULLS LAST;
~~~

### Exercise 11. LIMIT scope

A applies `LIMIT 2` **per customer**; B applies `LIMIT 2` globally. To fix it, use `JOIN LATERAL (SELECT ... WHERE o.customer_id = c.customer_id ORDER BY ... LIMIT 2)` or an appropriate per-customer ranking solution.

### Exercise 12. ROW_NUMBER

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM lateral_lab.orders AS o
)
SELECT c.customer_id, r.order_id
FROM lateral_lab.customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
   AND r.rn <= 2
ORDER BY c.customer_id, r.rn NULLS LAST;
~~~

### Exercise 13. DISTINCT ON

~~~sql
SELECT DISTINCT ON (customer_id)
    customer_id, order_id, created_at
FROM lateral_lab.orders
ORDER BY customer_id, created_at DESC, order_id DESC;
~~~

Dung has no rows in `orders` and thus does not appear. You need a `LEFT JOIN` back to `customers` to include all four customers.

### Exercise 14. Row multiplication when expanding tags

Order 101 has two tags, so it contributes `120 + 120 = 240` if `SUM(o.amount)` is computed **after expansion**. To get the right total, aggregate at the order level first, or expand tags only for display/filtering without multiplying order amounts.

### Exercise 15. Index

~~~sql
CREATE INDEX idx_orders_customer_top3
ON lateral_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

`customer_id` narrows down to the customer's group, `created_at DESC` serves newest-first ordering, and `order_id DESC` breaks ties. Measure actual plans to verify workload fit.

### Exercise 16. EXPLAIN

`loops = 10000` indicates the inner node ran many times, such as once per outer row across 10,000 customers. However, you cannot conclude "slow" from `loops` alone; inspect `actual time`, row counts, buffers, selectivity, and total duration.

### Exercise 17. UNNEST

~~~sql
WITH stores(store_id, sku_codes) AS (
    VALUES
        (1, ARRAY['A','B']::text[]),
        (2, ARRAY[]::text[])
)
SELECT s.store_id, x.sku
FROM stores AS s
LEFT JOIN LATERAL unnest(s.sku_codes)
    AS x(sku) ON TRUE
ORDER BY s.store_id, x.sku;
~~~

Store 2 has `sku = NULL`.

### Exercise 18. JSONB top 2

~~~sql
SELECT
    c.customer_id,
    COALESCE(x.orders_json, '[]'::jsonb) AS recent_orders
FROM lateral_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT jsonb_agg(
        jsonb_build_object('order_id', r.order_id)
        ORDER BY r.created_at DESC, r.order_id DESC
    ) AS orders_json
    FROM (
        SELECT o.order_id, o.created_at
        FROM lateral_lab.orders AS o
        WHERE o.customer_id = c.customer_id
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 2
    ) AS r
) AS x ON TRUE
ORDER BY c.customer_id;
~~~

`LIMIT 2` picks two orders **before aggregating** into the array; `LIMIT` outside an aggregate only limits the aggregate's output rows.

### Exercise 19. Filtering paid before vs. after LIMIT

The first query picks the **newest order regardless of status**, then drops the customer if that newest order is not paid. The second query picks the **newest paid order**; customers without any paid order are still kept with null right-side columns thanks to `LEFT JOIN`.

### Exercise 20. Choosing a solution

| Requirement | Recommendation |
| --- | --- |
| (a) Whether orders exist | `EXISTS` or `NOT EXISTS` |
| (b) Single newest order ID | Correlated scalar subquery with `ORDER BY ... LIMIT 1` |
| (c) Three newest orders for 20 selected customers | `LEFT JOIN LATERAL ... LIMIT 3` after selecting the 20 customers |
| (d) Rank of every order | `ROW_NUMBER() OVER (PARTITION BY ...)` |
| (e) One newest order per customer with orders | `DISTINCT ON (customer_id)` or `LATERAL ... LIMIT 1` |

## 30. Checklist When Using LATERAL in Real Applications

| Question | Why does it matter? |
| --- | --- |
| Does the LATERAL item reference the right left-side alias? | Avoids pulling system-wide data for every customer |
| Did you choose `CROSS` vs. `LEFT` intentionally? | Decides whether empty groups are retained |
| Are top-N filters placed before `LIMIT`? | Avoids getting "latest paid order" wrong |
| Does `ORDER BY` include a tie-breaker? | Guarantees stable, verifiable results |
| Which scope is `LIMIT` in? | Distinguishes top N per group from N rows overall |
| Does the subquery return 0, 1, or multiple rows? | Predicts cardinality and NULLs |
| Do multiple LATERALs multiply rows? | Prevents wrong counts and sums |
| Does JSON/array order need to be preserved? | Use `WITH ORDINALITY` or `ORDER BY` inside aggregates |
| Is there an index matching correlation + sort order? | Reduces cost of top-N lookups |
| Are there too many left-side rows? | Bounds lookups, CPU, and memory |
| What do `EXPLAIN` loops and buffers show? | Measures real execution plans |
| Is a simpler technique better? | `EXISTS`, `GROUP BY`, scalar subquery, `ROW_NUMBER`, `DISTINCT ON` |

## 31. Quick Syntax Reference Table

| Purpose | SQL pattern |
| --- | --- |
| Correlated item in FROM | `FROM t CROSS JOIN LATERAL (SELECT ... WHERE x = t.x) AS s` |
| Optional top 1 | `LEFT JOIN LATERAL (SELECT ... ORDER BY ... LIMIT 1) AS x ON TRUE` |
| Top N dropping empty groups | `CROSS JOIN LATERAL (SELECT ... LIMIT N) AS x` |
| Keeping empty groups | `LEFT JOIN LATERAL (...) AS x ON TRUE` |
| Per-row aggregate | `LEFT JOIN LATERAL (SELECT COUNT(*) ... WHERE key = t.key) AS x ON TRUE` |
| Row-dependent set-returning function | `CROSS JOIN LATERAL unnest(t.arr) AS x(value)` |
| JSONB array to rows | `CROSS JOIN LATERAL jsonb_array_elements_text(t.tags) AS x(tag)` |
| Preserve element position | `... WITH ORDINALITY AS x(value, position)` |
| Existence check | `WHERE EXISTS (SELECT 1 ... WHERE key = t.key)` |
| Top N with window function | `ROW_NUMBER() OVER (PARTITION BY key ORDER BY ...)` |
| Top 1 with PostgreSQL DISTINCT ON | `SELECT DISTINCT ON (key) ... ORDER BY key, ...` |
| Index for top-N lookup | `CREATE INDEX ... ON orders(key, created_at DESC, id DESC)` |
| Inspect plan | `EXPLAIN (ANALYZE, BUFFERS) SELECT ...` |

## 32. Summary

`LATERAL` allows an item in `FROM` to **use values from preceding rows** to produce a corresponding result set. It is particularly useful when a subquery or set-returning function depends on each row—such as **the two newest orders per customer**, **statistics for a just-selected order**, or **expanding a JSONB array into multiple rows**.

Three core principles:

1. **`CROSS JOIN LATERAL` drops left rows when the right set is empty; `LEFT JOIN LATERAL ... ON TRUE` retains left rows with null right columns.** Choosing the right join type means choosing the right business behavior for empty groups.
2. **Place correlation predicates, `ORDER BY`, and `LIMIT` in the right scope.** For top-N-per-group, `LIMIT` must cap rows **per group**, not after all results are joined.
3. **`LATERAL` does not automatically make queries faster or guard against row multiplication.** Check cardinality, indexes, `EXPLAIN`, and compare against `EXISTS`, `GROUP BY`, `ROW_NUMBER`, or `DISTINCT ON` where appropriate.

When writing advanced PostgreSQL queries, start by asking: **"For each row on the left, how many rows or what values do I need on the right?"**. Whenever the right side must reference the left row directly and produce a per-row result set, `LATERAL` is often a clear, powerful, and extensible SQL expression.
