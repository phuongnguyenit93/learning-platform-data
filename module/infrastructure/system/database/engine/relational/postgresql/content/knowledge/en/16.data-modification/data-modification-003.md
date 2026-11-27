# UPDATE, Assignment Expressions, and Row-Selection Conditions in PostgreSQL

`UPDATE` is the SQL statement used to **modify column values in existing rows**. Whereas `INSERT` creates new rows and `DELETE` removes rows, `UPDATE` modifies existing information without replacing the entire table.

In PostgreSQL applications, this statement appears across many business workflows:

- Changing a customer's name, address, status, or segment.
- Transitioning an order from `pending` to `paid` according to status rules.
- Incrementing or decrementing inventory based on current values.
- Recalculating amounts from multiple columns or related tables.
- Updating attributes inside a `jsonb` column.
- Synchronizing values from another table via `UPDATE ... FROM`.
- Capturing the rows actually modified via `RETURNING`.

The three most important parts of the statement are:

~~~sql
UPDATE table_name
SET column_name = expression
WHERE condition;
~~~

**`UPDATE`** identifies the target table; **`SET`** specifies the new values; **`WHERE`** selects which rows are eligible to be changed. Among data-modification operations, getting `WHERE` right is often more critical than knowing advanced syntax: a missing or flawed condition can turn a single-order edit into updating millions of rows.

This lesson progresses from basic assignments to expressions, handling `NULL`, `CASE`, `COALESCE`, updating from other tables, subqueries, `RETURNING`, concurrency, transaction control, and real-world pitfalls.

## 1. Distinguishing the Three Questions of UPDATE

Before writing an `UPDATE` command, answer:

1. **Which table is being modified?** A single `UPDATE` statement has one direct target table; cascading effects from triggers or foreign keys are separate side effects.
2. **Which columns are modified, and by what formula?** New values can be constants, prior column values, arithmetic expressions, `CASE`, `DEFAULT`, subqueries, or data from `FROM` tables.
3. **Which rows are modified?** `WHERE` selects rows matching the condition at the time the statement processes them under PostgreSQL's transaction rules.

Example:

~~~sql
UPDATE update_lab.products
SET stock_qty = stock_qty - 2
WHERE product_id = 101
  AND stock_qty >= 2;
~~~

Meaning of this statement:

- Target table: `update_lab.products`.
- Modified column: `stock_qty`.
- New value: current stock minus 2.
- Selected rows: product 101 **and** currently having at least 2 units in stock.

The expression `stock_qty = stock_qty - 2` does **not** mean "use the stale value from when the user opened the UI." PostgreSQL evaluates it against the row version processed by the statement, respecting appropriate row-locking and isolation rules.

## 2. Preparing a Safe Practice Dataset

All examples use the `update_lab` schema in a **dedicated PostgreSQL practice database**. The setup includes `DROP SCHEMA ... CASCADE` so results are reproducible. **Do not run this script in a production database or a schema containing data you need to keep.**

### 2.1. Create Tables

~~~sql
-- Run only after confirming you are in a lab database.
DROP SCHEMA IF EXISTS update_lab CASCADE;
CREATE SCHEMA update_lab;

CREATE TABLE update_lab.customers (
    customer_id integer PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    city text,
    tier text NOT NULL DEFAULT 'standard'
        CHECK (tier IN ('standard', 'silver', 'gold')),
    loyalty_points integer NOT NULL DEFAULT 0
        CHECK (loyalty_points >= 0),
    phone text,
    is_active boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE update_lab.products (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    list_price numeric(12,2) NOT NULL CHECK (list_price >= 0),
    sale_price numeric(12,2)
        CHECK (sale_price IS NULL OR sale_price >= 0),
    stock_qty integer NOT NULL CHECK (stock_qty >= 0),
    is_active boolean NOT NULL DEFAULT true,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE update_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES update_lab.customers(customer_id),
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    total_amount numeric(12,2) NOT NULL DEFAULT 0
        CHECK (total_amount >= 0),
    note text,
    created_at timestamptz NOT NULL,
    paid_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE update_lab.order_items (
    order_id integer NOT NULL
        REFERENCES update_lab.orders(order_id),
    product_id integer NOT NULL
        REFERENCES update_lab.products(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);

CREATE TABLE update_lab.product_discounts (
    product_id integer PRIMARY KEY
        REFERENCES update_lab.products(product_id),
    discount_percent numeric(5,2) NOT NULL
        CHECK (discount_percent BETWEEN 0 AND 100)
);
~~~

Each table has a clear purpose:

| Table | Role |
| --- | --- |
| `customers` | Constants, `NULL`, `DEFAULT`, `CASE`, customer filtering conditions |
| `products` | Arithmetic operations, stock deduction, `jsonb` updates, sale prices |
| `orders` | Status conditions, updates from line-item data, `RETURNING` |
| `order_items` | 1:N source illustrating `UPDATE ... FROM` and aggregation |
| `product_discounts` | Single-row-per-product source for price updates |

`CHECK`, primary keys, and foreign keys enforce invariants. A syntactically valid `UPDATE` can still fail if its result violates these constraints.

### 2.2. Load Fixed Seed Data

~~~sql
INSERT INTO update_lab.customers
    (customer_id, email, full_name, city, tier,
     loyalty_points, phone, is_active)
VALUES
    (1, 'an@example.test',   'An',   'HCM', 'gold',     120, NULL, true),
    (2, 'binh@example.test', 'Binh', 'HAN', 'silver',    60, NULL, true),
    (3, 'chi@example.test',  'Chi',  'DNG', 'standard',   0, NULL, false),
    (4, 'dung@example.test', 'Dung', 'HCM', 'standard',  10, NULL, true);

INSERT INTO update_lab.products
    (product_id, product_name, list_price,
     sale_price, stock_qty, is_active, attributes)
VALUES
    (101, 'Coffee', 30.00, NULL, 10, true,
     '{"category":"beverage","color":"brown"}'::jsonb),
    (102, 'Tea',    20.00, NULL,  5, true,
     '{"category":"beverage","color":"green"}'::jsonb),
    (103, 'Cup',    12.00, NULL,  0, false,
     '{"category":"accessory","color":"white"}'::jsonb);

INSERT INTO update_lab.orders
    (order_id, customer_id, status, total_amount,
     note, created_at, paid_at)
VALUES
    (1001, 1, 'pending',   80.00, NULL,
     '2026-11-01 08:00:00+00', NULL),
    (1002, 1, 'paid',      35.00, 'Paid at counter',
     '2026-11-02 09:00:00+00', '2026-11-02 09:20:00+00'),
    (1003, 2, 'pending',   60.00, NULL,
     '2026-11-03 10:00:00+00', NULL),
    (1004, 3, 'cancelled', 20.00, NULL,
     '2026-11-04 11:00:00+00', NULL);

INSERT INTO update_lab.order_items
    (order_id, product_id, quantity, unit_price)
VALUES
    (1001, 101, 2, 30.00),
    (1001, 102, 1, 20.00),
    (1002, 101, 1, 35.00),
    (1003, 102, 3, 20.00),
    (1004, 103, 1, 20.00);

INSERT INTO update_lab.product_discounts
    (product_id, discount_percent)
VALUES
    (101, 10.00),
    (102,  5.00);
~~~

Initial data:

| Order | Customer | Status | Total | Line Item Count |
| ---: | ---: | --- | ---: | ---: |
| 1001 | 1 (An) | pending | 80.00 | 2 |
| 1002 | 1 (An) | paid | 35.00 | 1 |
| 1003 | 2 (Binh) | pending | 60.00 | 1 |
| 1004 | 3 (Chi) | cancelled | 20.00 | 1 |

Product 101 has stock 10, product 102 has stock 5, and product 103 has stock 0.

**Practice convention:** all data-modifying examples after seeding should be run **individually** inside `BEGIN; ... ROLLBACK;`, unless you intentionally want to keep the changes. That way subsequent examples always start from the initial seed data.

## 3. UPDATE Syntax in PostgreSQL

Simple form:

~~~sql
UPDATE update_lab.customers
SET city = 'Hue'
WHERE customer_id = 2;
~~~

Form with alias, multiple assignments, and returning results:

~~~sql
UPDATE update_lab.customers AS c
SET
    city = 'Hue',
    updated_at = now()
WHERE c.customer_id = 2
RETURNING
    c.customer_id,
    c.full_name,
    c.city,
    c.updated_at;
~~~

Common general structure:

~~~sql
WITH optional_cte AS (
    SELECT ...
)
UPDATE target_table AS t
SET
    column_a = expression_a,
    column_b = expression_b
FROM optional_source AS s
WHERE selection_condition
RETURNING t.column_a, t.column_b;
~~~

Not every `UPDATE` needs `WITH`, `FROM`, or `RETURNING`. However, **`SET` is mandatory**, and **`WHERE` must be consciously evaluated**.

### UPDATE Without WHERE

~~~sql
-- DANGEROUS unless you truly intend to edit every row.
UPDATE update_lab.customers
SET tier = 'standard';
~~~

This selects **every row** in the `customers` table. Omitting `WHERE` is not a syntax error; it is a completely valid bulk update.

If the task was only meant to modify customer 2, omitting `WHERE customer_id = 2` is a severe business bug.

## 4. SET with a Constant Value

Try changing Binh's city:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET city = 'Hue'
WHERE customer_id = 2;

SELECT customer_id, full_name, city
FROM update_lab.customers
WHERE customer_id = 2;

ROLLBACK;
~~~

Inside the transaction before `ROLLBACK`, Binh has `city = 'Hue'`. After rollback, the original city `HAN` is restored.

### UPDATE Leaves Columns Not Listed in SET Unchanged

If only `city` is assigned, columns such as `email`, `tier`, and `loyalty_points` remain untouched—except for changes applied by **triggers or rules** configured separately in the system.

You do not need to resend the entire row to edit one column. This is a major advantage of `UPDATE` over applications trying to reconstruct a full record from previously read values.

## 5. SET Multiple Columns at Once

Multiple columns can be assigned in a single statement:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET
    full_name = 'Binh Tran',
    city = 'Hue',
    tier = 'gold',
    loyalty_points = loyalty_points + 20,
    updated_at = now()
WHERE c.customer_id = 2
RETURNING
    c.customer_id,
    c.full_name,
    c.city,
    c.tier,
    c.loyalty_points;

ROLLBACK;
~~~

With the seed data, Binh starts with 60 points, so `loyalty_points` temporarily becomes **80**.

Each target column should appear only once in the `SET` list. Right-hand expressions can combine constants, application parameters, current column values, and PostgreSQL functions.

### Never Put an Alias on the Left Side of `=` in SET

Correct syntax:

~~~sql
UPDATE update_lab.customers AS c
SET city = 'Hue'
WHERE c.customer_id = 2;
~~~

Invalid in PostgreSQL:

~~~sql
-- Deliberately wrong: cannot use c.city as the target column name.
UPDATE update_lab.customers AS c
SET c.city = 'Hue'
WHERE c.customer_id = 2;
~~~

The left side of `=` in `SET` must be an **unqualified target column name without an alias prefix**. The alias is still used to reference rows/columns in `WHERE`, `FROM`, `RETURNING`, and right-hand expressions.

## 6. Assignment Expressions Are Evaluated from Pre-Update Row Values

Suppose a table has two numeric columns `a` and `b` and you want to swap their values:

~~~sql
CREATE TABLE update_lab.swap_demo (
    demo_id integer PRIMARY KEY,
    a integer NOT NULL,
    b integer NOT NULL
);

INSERT INTO update_lab.swap_demo (demo_id, a, b)
VALUES (1, 10, 20);
~~~

Run:

~~~sql
BEGIN;

UPDATE update_lab.swap_demo
SET
    a = b,
    b = a
WHERE demo_id = 1
RETURNING a, b;

ROLLBACK;
~~~

The result is **a = 20, b = 10**.

Within an `UPDATE` statement, assignment expressions read the values from **the row version before the `UPDATE` applies any assignments to that row**; it does not work sequentially like "assign `a`, then read the new `a` to assign `b`."

Therefore:

~~~sql
SET
    a = a + 1,
    b = a + 1
~~~

computes both columns from **the old `a`** (not `b` = new `a` + 1). Keep this property in mind whenever multiple assignments reference related columns.

### Column-List Assignment

PostgreSQL also supports row-style assignment syntax:

~~~sql
BEGIN;

UPDATE update_lab.swap_demo
SET (a, b) = (b, a)
WHERE demo_id = 1
RETURNING a, b;

ROLLBACK;
~~~

The result is still swapped: 20 and 10. This form is useful when columns belong together and can be derived from a single tuple or subquery.

## 7. Arithmetic Operations in SET

Assignment expressions can perform ordinary arithmetic:

~~~sql
BEGIN;

UPDATE update_lab.products
SET
    list_price = ROUND(list_price * 1.10, 2),
    updated_at = now()
WHERE product_id = 101
RETURNING product_id, list_price;

ROLLBACK;
~~~

Coffee's price increases from **30.00** to **33.00**.

Common examples:

~~~sql
SET stock_qty = stock_qty + 5
SET stock_qty = stock_qty - 2
SET loyalty_points = loyalty_points + 10
SET list_price = ROUND(list_price * 0.95, 2)
~~~

Use appropriate types: money should use `numeric` when controlled decimal precision is needed; avoid arbitrary floating-point arithmetic for financial logic.

### Constraint Checks on Results

The `products` table declares:

~~~sql
stock_qty integer NOT NULL CHECK (stock_qty >= 0)
~~~

Running `SET stock_qty = stock_qty - 100` on a row with 10 remaining will be rejected by PostgreSQL for violating `CHECK`. However, relying on constraint failures is poorer design than checking availability in the condition beforehand.

We will use `WHERE stock_qty >= requested_qty` to model stock deduction cleanly in the next section.

## 8. WHERE Selects Rows; Only Matching Rows Are Updated

Suppose we deduct 3 units of Coffee:

~~~sql
BEGIN;

UPDATE update_lab.products
SET stock_qty = stock_qty - 3
WHERE product_id = 101
  AND stock_qty >= 3
RETURNING product_id, stock_qty;

ROLLBACK;
~~~

In the lab, Coffee's stock drops from 10 to **7**.

If you change `product_id` to 103, Cup has `stock_qty = 0`, so `WHERE stock_qty >= 3` does not match; the `UPDATE` affects **0 rows**. That is not a SQL error.

### WHERE Filters Input Rows, Not Post-UPDATE Values

The statement:

~~~sql
UPDATE update_lab.products
SET stock_qty = stock_qty - 3
WHERE stock_qty >= 3;
~~~

selects rows **currently** having stock of 3 or more and subtracts 3. If a row currently has stock 3, it **is updated to 0** and is not excluded from the update just because its new value no longer satisfies `stock_qty >= 3`.

This contrasts with the misconception that PostgreSQL re-evaluates `WHERE` after assignment and "pulls" rows out of the `UPDATE`.

## 9. AND, OR, and Parentheses in WHERE

Distinguish logical operator precedence:

~~~sql
WHERE condition_a AND condition_b OR condition_c
~~~

In SQL, `AND` has higher precedence than `OR`. The expression above equals:

~~~sql
WHERE (condition_a AND condition_b) OR condition_c
~~~

not:

~~~sql
WHERE condition_a AND (condition_b OR condition_c)
~~~

### Dangerous Example

Requirement: only change the status of orders **belonging to customer 1** that are `pending` or `cancelled`.

Avoid writing:

~~~sql
-- Wrong meaning: can select every cancelled order,
-- including orders from other customers.
UPDATE update_lab.orders
SET status = 'paid'
WHERE customer_id = 1
  AND status = 'pending'
   OR status = 'cancelled';
~~~

With the seed data, this condition would also match **Chi's order 1004**, because `status = 'cancelled'` satisfies the standalone `OR` branch.

Write it properly:

~~~sql
BEGIN;

UPDATE update_lab.orders
SET status = 'paid'
WHERE customer_id = 1
  AND status IN ('pending', 'cancelled')
RETURNING order_id, customer_id, status;

ROLLBACK;
~~~

Or use parentheses:

~~~sql
WHERE customer_id = 1
  AND (status = 'pending' OR status = 'cancelled')
~~~

**Business note:** changing a `cancelled` order to `paid` may be invalid in a real system; this example only illustrates row-selection logic. In real workflows, restrict allowed state transitions.

## 10. WHERE with NULL: Use IS NULL and IS NOT NULL

In SQL, `NULL` represents an unknown or absent value, not an empty string. Standard equality comparison with `NULL` never returns `TRUE`:

~~~sql
-- Wrong: will not match rows where phone is NULL.
WHERE phone = NULL
~~~

Correct:

~~~sql
WHERE phone IS NULL
~~~

Practice filling in a phone number **only for customers who do not have one yet**:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET phone = '000-EXAMPLE'
WHERE customer_id = 1
  AND phone IS NULL
RETURNING customer_id, phone;

ROLLBACK;
~~~

If `phone` already has a value, the statement updates 0 rows.

### Three-Valued Logic

A SQL condition evaluates to **TRUE, FALSE, or UNKNOWN (NULL)**. `UPDATE ... WHERE` only selects rows where the condition evaluates to **TRUE**. Neither `FALSE` nor `UNKNOWN` is selected.

For example:

~~~sql
WHERE phone <> '000-EXAMPLE'
~~~

does not select customers with `phone IS NULL`, because `NULL <> '000-EXAMPLE'` evaluates to `UNKNOWN`, not `TRUE`.

When you want to include `NULL` in inequality comparisons, `IS DISTINCT FROM` is usually the right tool.

## 11. IS DISTINCT FROM: Null-Safe Comparison

Suppose you want to set `city = 'HCM'` for customer 4 only if the current value differs from `HCM`. Use:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET city = 'HCM'
WHERE customer_id = 4
  AND city IS DISTINCT FROM 'HCM'
RETURNING customer_id, city;

ROLLBACK;
~~~

With the seed data, customer 4 is already in `HCM`, so **0 rows** are updated.

`IS DISTINCT FROM` has clear semantics when either side is `NULL`:

| Current Value | New Value | `IS DISTINCT FROM` |
| --- | --- | --- |
| HCM | HCM | FALSE |
| HAN | HCM | TRUE |
| NULL | HCM | TRUE |
| NULL | NULL | FALSE |

By contrast, `city <> 'HCM'` returns `UNKNOWN` for rows where `city IS NULL`.

### Avoiding Unnecessary Writes When Data Has Not Changed

~~~sql
BEGIN;

UPDATE update_lab.customers
SET
    city = 'HCM',
    updated_at = now()
WHERE customer_id = 1
  AND city IS DISTINCT FROM 'HCM'
RETURNING customer_id, city, updated_at;

ROLLBACK;
~~~

Customer An already has `city = 'HCM'`, so the query performs no update and leaves `updated_at` untouched.

This pattern is useful to avoid rewriting unchanged rows, firing unnecessary `UPDATE` triggers, and generating extra overhead. However, do not blindly add `IS DISTINCT FROM` if business logic **intentionally wants** to record a "re-confirmed" timestamp even when the value did not change.

## 12. SET NULL and SET DEFAULT

### 12.1. Setting a Column to NULL

~~~sql
BEGIN;

UPDATE update_lab.customers
SET phone = NULL
WHERE customer_id = 2
RETURNING customer_id, phone;

ROLLBACK;
~~~

This succeeds because `phone` is nullable.

If you try:

~~~sql
-- Deliberate error: full_name is declared NOT NULL.
UPDATE update_lab.customers
SET full_name = NULL
WHERE customer_id = 2;
~~~

PostgreSQL raises a `NOT NULL` violation. `SET` cannot bypass table constraints.

### 12.2. Resetting a Column to DEFAULT

Suppose customer 1 is currently in the `gold` tier and you want to reset to the default `standard`:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET tier = DEFAULT
WHERE customer_id = 1
RETURNING customer_id, tier;

ROLLBACK;
~~~

The table defines `tier text NOT NULL DEFAULT 'standard'`, so the new value is `standard`.

**`DEFAULT` is not "the row's original value at insert time."** It is the **column's default expression in the current schema**. If the default was changed in a migration, `SET column = DEFAULT` uses the current definition.

If a column has no explicit default, `DEFAULT` evaluates to `NULL`, which fails if the column has `NOT NULL` or another incompatible constraint.

## 13. CASE: Assigning Different Values per Row

A single `UPDATE` can select multiple rows and apply different assignments per row using `CASE`.

Example assigning customer tiers based on loyalty points:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET
    tier = CASE
        WHEN c.loyalty_points >= 100 THEN 'gold'
        WHEN c.loyalty_points >= 50 THEN 'silver'
        ELSE 'standard'
    END,
    updated_at = now()
WHERE c.is_active = true
RETURNING
    c.customer_id,
    c.loyalty_points,
    c.tier;

ROLLBACK;
~~~

Results for active customers:

| customer_id | points | Updated Tier |
| ---: | ---: | --- |
| 1 | 120 | gold |
| 2 | 60 | silver |
| 4 | 10 | standard |

Customer Chi (3) is inactive and therefore not selected.

### Order of WHEN Branches Matters

If you write:

~~~sql
CASE
    WHEN loyalty_points >= 50 THEN 'silver'
    WHEN loyalty_points >= 100 THEN 'gold'
    ELSE 'standard'
END
~~~

then a customer with 120 points matches `>= 50` first and receives `silver` instead of `gold`. `CASE` evaluates branches in order and picks the first match.

### What Happens Without ELSE?

~~~sql
CASE
    WHEN loyalty_points >= 100 THEN 'gold'
END
~~~

For any row not matching a branch, the expression returns **`NULL`**. If `tier` is `NOT NULL`, the `UPDATE` fails. When using `CASE` on a required column, cover all cases or include an appropriate `ELSE`.

## 14. COALESCE: Preferring the First Non-NULL Value

`COALESCE` returns the **first non-NULL** expression in its argument list.

Example overwriting `phone` only if the application supplies a new value:

~~~sql
BEGIN;

UPDATE update_lab.customers
SET phone = COALESCE('0900000000'::text, phone)
WHERE customer_id = 1
RETURNING customer_id, phone;

ROLLBACK;
~~~

If the first argument is `NULL`, the expression preserves the existing `phone`:

~~~sql
SET phone = COALESCE(NULL::text, phone)
~~~

### COALESCE Cannot Represent Every Optional-Update Rule

An API often needs three distinct meanings:

1. Field omitted → keep unchanged.
2. Field sent with a new string → update.
3. Field sent with explicit `null` → **clear the old value**.

If you always write:

~~~sql
SET phone = COALESCE(:new_phone, phone)
~~~

then case (3) **cannot clear the phone number**, because `NULL` falls back to the old value. The application must distinguish an "absent field" from an "explicit `null`" if the `PATCH` contract requires clearing values.

Use `CASE` with a `field_present` flag, conditional SQL construction, or an appropriate DTO/SQL strategy—do not use `COALESCE` blindly.

## 15. An UPDATE Statement Can Return Modified Rows

`RETURNING` returns data from the rows actually processed by the statement.

~~~sql
BEGIN;

UPDATE update_lab.orders AS o
SET
    status = 'paid',
    paid_at = now(),
    updated_at = now()
WHERE o.order_id = 1001
  AND o.status = 'pending'
RETURNING
    o.order_id,
    o.customer_id,
    o.status,
    o.paid_at;

ROLLBACK;
~~~

With the seed data, this returns **one row** with `status = 'paid'`.

If you change the condition to:

~~~sql
WHERE o.order_id = 1002 AND o.status = 'pending'
~~~

no rows are updated because order 1002 is already `paid`, and `RETURNING` returns **0 rows**.

### RETURNING vs. Re-Querying the Table with SELECT

- `UPDATE ... RETURNING` directly reflects the exact rows processed by that `UPDATE`.
- A separate `SELECT` after `UPDATE` sees the new state in the same transaction, but does not automatically identify which rows were **modified by the preceding statement** without tracking keys.
- `RETURNING` lets applications verify row counts, retrieve new values, capture actual server timestamps, and emit audit/outbox records when needed.

In PostgreSQL, `RETURNING` can include expressions such as:

~~~sql
RETURNING order_id, total_amount * 0.10 AS reference_amount
~~~

**Note:** in standard `UPDATE ... RETURNING column`, column references return **post-update values**. To capture both old and new values, use version-supported syntax if available or a dedicated audit mechanism; do not assume aliasing something `old_value` returns the pre-UPDATE value.

## 16. RETURNING Does Not Prove Values Actually Changed

The statement:

~~~sql
UPDATE update_lab.orders
SET status = 'paid'
WHERE order_id = 1002
RETURNING order_id, status;
~~~

still returns a row even though order 1002 already had `status = 'paid'`. PostgreSQL processes rows matching `WHERE` and creates a new row version with the assigned values.

If business logic requires **emitting an event only on an actual state transition**, the condition must guard the valid source state:

~~~sql
BEGIN;

UPDATE update_lab.orders
SET
    status = 'paid',
    paid_at = now()
WHERE order_id = 1002
  AND status = 'pending'
RETURNING order_id, status;

ROLLBACK;
~~~

Returning **0 rows** is the desired outcome here. Do not treat "a row returned by `RETURNING`" as proof that values actually changed unless your `WHERE` condition checks for a difference.

## 17. UPDATE with IN and EXISTS

When rows must be selected based on data in another table, use `IN` or `EXISTS` in `WHERE`.

Example: mark customers active if they have placed a `pending` order:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET
    is_active = true,
    updated_at = now()
WHERE EXISTS (
    SELECT 1
    FROM update_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'pending'
)
RETURNING c.customer_id, c.is_active;

ROLLBACK;
~~~

With the seed data, customers 1 and 2 have `pending` orders and are selected.

`EXISTS` asks whether **at least one matching row exists**. Even if a customer has three `pending` orders, each target customer row is updated once, not "three times."

### IN Works Similarly When Only a Key Set Is Needed

~~~sql
BEGIN;

UPDATE update_lab.customers
SET is_active = true
WHERE customer_id IN (
    SELECT customer_id
    FROM update_lab.orders
    WHERE status = 'pending'
)
RETURNING customer_id;

ROLLBACK;
~~~

This phrasing fits well when a subquery yields a set of IDs. Be careful with `NULL` semantics for `IN`/`NOT IN` over nullable expressions; `EXISTS`/`NOT EXISTS` is often clearer for existence checks.

## 18. UPDATE ... FROM: Assigning from a Related Table

PostgreSQL provides `UPDATE ... FROM` to read a data source while updating the target table.

Example calculating `sale_price` from the discount table:

~~~sql
BEGIN;

UPDATE update_lab.products AS p
SET
    sale_price = ROUND(
        p.list_price * (1 - d.discount_percent / 100),
        2
    ),
    updated_at = now()
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id
RETURNING
    p.product_id,
    p.product_name,
    p.list_price,
    p.sale_price;

ROLLBACK;
~~~

Results with the seed data:

| product_id | list_price | sale_price |
| ---: | ---: | ---: |
| 101 | 30.00 | 27.00 |
| 102 | 20.00 | 19.00 |

Product 103 has no matching row in `product_discounts`, so it is **not updated**.

How to read the SQL:

1. `UPDATE ... AS p` specifies the **target table**.
2. `FROM ... AS d` provides the **source data**.
3. `WHERE d.product_id = p.product_id` joins target rows to source rows.
4. `SET sale_price = ...` computes the new value using columns from both `p` and `d`.
5. `RETURNING` returns the post-UPDATE results.

`FROM` does not mean PostgreSQL infers join keys automatically. Omitting the join predicate causes an unintended cross-join that can corrupt rows.

## 19. UPDATE ... FROM Does Not Update Two Tables Simultaneously

In:

~~~sql
UPDATE update_lab.products AS p
SET sale_price = p.list_price * 0.9
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id;
~~~

only `products` is the **target table of the `UPDATE`**. `product_discounts` is **read-only** here for evaluation and filtering.

If you want to update both `products.sale_price` and `product_discounts.discount_percent`, you cannot write:

~~~sql
-- Wrong: d.discount_percent is not a column of the target table.
UPDATE update_lab.products AS p
SET
    sale_price = 10,
    d.discount_percent = 5
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id;
~~~

Typically, use two `UPDATE` statements inside the same transaction, or another DML pattern matching your consistency needs. Triggers or foreign-key actions can cause secondary changes, but those are separate mechanisms.

## 20. Major Pitfall of UPDATE ... FROM: Multiple Source Rows for One Target Row

PostgreSQL allows joining the target table with a `FROM` source. However, if **one target row matches multiple source rows**, PostgreSQL **does not guarantee which source row will be used for `SET`**. Never rely on insertion order or physical scan order.

Suppose you try to update `orders.total_amount` directly from `order_items`:

~~~sql
-- DO NOT USE: order 1001 has two order_items!
UPDATE update_lab.orders AS o
SET total_amount = i.quantity * i.unit_price
FROM update_lab.order_items AS i
WHERE i.order_id = o.order_id;
~~~

For order 1001:

- Coffee line: 2 × 30.00 = 60.00.
- Tea line: 1 × 20.00 = 20.00.

Order 1001 matches **two** source rows. This `UPDATE` does not sum to 80.00; PostgreSQL picks one arbitrary source row to apply, with **no guarantee which one**. It does not update order 1001 twice to accumulate across items like an application loop.

### Safety Rule

**Before using `UPDATE ... FROM`, verify that the source yields at most one row per target-table key.**

Achieve this by:

- A `PRIMARY KEY`/`UNIQUE` constraint on the source table, such as `product_discounts(product_id)`.
- Using `GROUP BY` to aggregate into one row per key.
- Using `DISTINCT ON` or `ROW_NUMBER()` with `ORDER BY` and a deterministic tiebreaker to select one representative row.
- Using a scalar subquery with exact semantics, which errors if multiple rows are returned when a single value is expected.

Do not try to "fix" it by slapping an `ORDER BY` on a source query and hoping `UPDATE` picks the "first" row. Source scan order is not a deterministic contract for `UPDATE` when multiple matches exist.

## 21. UPDATE from a GROUP BY Source

To accurately calculate order totals from line items, aggregate first:

~~~sql
BEGIN;

WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price)::numeric(12,2)
            AS calculated_total
    FROM update_lab.order_items
    GROUP BY order_id
)
UPDATE update_lab.orders AS o
SET
    total_amount = t.calculated_total,
    updated_at = now()
FROM totals AS t
WHERE t.order_id = o.order_id
  AND o.total_amount IS DISTINCT FROM t.calculated_total
RETURNING
    o.order_id,
    o.total_amount;

ROLLBACK;
~~~

In the seed data, all order totals already match their line items, so `IS DISTINCT FROM` causes the `UPDATE` to return **0 rows**. That is the right outcome: no order needs correction.

To observe an actual synchronization in the lab, introduce a **temporary mismatch** and recalculate:

~~~sql
BEGIN;

UPDATE update_lab.orders
SET total_amount = 55.00
WHERE order_id = 1003;

WITH totals AS (
    SELECT
        order_id,
        SUM(quantity * unit_price)::numeric(12,2)
            AS calculated_total
    FROM update_lab.order_items
    GROUP BY order_id
)
UPDATE update_lab.orders AS o
SET
    total_amount = t.calculated_total,
    updated_at = now()
FROM totals AS t
WHERE t.order_id = o.order_id
  AND o.total_amount IS DISTINCT FROM t.calculated_total
RETURNING o.order_id, o.total_amount;

ROLLBACK;
~~~

Within the transaction, order 1003 is corrected from 55.00 back to **60.00** (3 Tea items × 20.00).

### Why Does GROUP BY Solve Duplicate Sources?

`GROUP BY order_id` produces **at most one aggregated row per `order_id`**. Thus, with `order_id` as the target's `PRIMARY KEY`, each target row matches at most one total row.

**Note:** only orders with at least one line item appear in the `totals` CTE. If business rules require setting empty orders' totals to 0, build the source via `LEFT JOIN` from `orders`, or use a scalar subquery with `COALESCE`. Do not assume the CTE above covers empty orders in all schemas.

## 22. UPDATE Using a Scalar Subquery

You do not always need `FROM`. You can assign a value using a subquery that returns **a single scalar value**.

~~~sql
BEGIN;

UPDATE update_lab.orders AS o
SET
    total_amount = COALESCE(
        (
            SELECT SUM(i.quantity * i.unit_price)
            FROM update_lab.order_items AS i
            WHERE i.order_id = o.order_id
        ),
        0
    ),
    updated_at = now()
WHERE o.order_id = 1001
RETURNING o.order_id, o.total_amount;

ROLLBACK;
~~~

The subquery in `SET` correlates with the target row `o` via `o.order_id`. `SUM` always returns a single aggregate row (yielding `NULL` for an empty set); `COALESCE(..., 0)` turns zero-item orders into 0.

If you use a non-aggregated scalar subquery:

~~~sql
-- Deliberately wrong when an order has multiple items:
UPDATE update_lab.orders AS o
SET total_amount = (
    SELECT quantity * unit_price
    FROM update_lab.order_items AS i
    WHERE i.order_id = o.order_id
)
WHERE o.order_id = 1001;
~~~

the subquery returns **multiple rows** and PostgreSQL raises an error: `"more than one row returned by a subquery used as an expression"`. This is a helpful safeguard when the query fails to specify a single source value.

### Subquery Returning 0 Rows

A scalar subquery returning 0 rows evaluates to `NULL` in an assignment. If the target column is `NOT NULL`, the `UPDATE` fails. When business rules allow, use `COALESCE` or explicitly handle missing source data.

## 23. Assigning Multiple Columns from a Subquery

PostgreSQL lets a subquery supply multiple values for a group of columns:

~~~sql
BEGIN;

UPDATE update_lab.customers AS c
SET (city, tier) = (
    SELECT 'Hue'::text, 'gold'::text
)
WHERE c.customer_id = 2
RETURNING c.customer_id, c.city, c.tier;

ROLLBACK;
~~~

This illustrates tuple assignment. In practice, the subquery can read from a configuration table or compute expressions, provided it returns the exact number of columns and at most one row.

Distinguish:

- `SET (a, b) = (expr_a, expr_b)`: two expressions evaluated from old row values or parameters.
- `SET (a, b) = (SELECT x, y FROM source ...)`: a single result row providing two values.
- If the subquery returns more than one row, the `UPDATE` fails rather than arbitrarily picking one.

For 1:N sources, aggregate first or define a deterministic row-selection rule.

## 24. Using DISTINCT ON to Pick One Representative Row from a Source

Sometimes a target row has multiple historical event records, and you want to update using only the **most recent** record.

Create a customer-event table to practice:

~~~sql
CREATE TABLE update_lab.customer_city_events (
    event_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES update_lab.customers(customer_id),
    new_city text NOT NULL,
    effective_at timestamptz NOT NULL
);

INSERT INTO update_lab.customer_city_events
    (event_id, customer_id, new_city, effective_at)
VALUES
    (1, 2, 'Hue', '2026-11-01 10:00:00+00'),
    (2, 2, 'HCM', '2026-11-05 10:00:00+00'),
    (3, 1, 'DNG', '2026-11-03 09:00:00+00');
~~~

Do not directly join `customer_city_events` to `customers`: customer 2 has two source records and it would be ambiguous which city to apply.

Pick one row per customer with `DISTINCT ON`:

~~~sql
BEGIN;

WITH latest_city AS (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        new_city
    FROM update_lab.customer_city_events
    ORDER BY
        customer_id,
        effective_at DESC,
        event_id DESC
)
UPDATE update_lab.customers AS c
SET
    city = l.new_city,
    updated_at = now()
FROM latest_city AS l
WHERE l.customer_id = c.customer_id
  AND c.city IS DISTINCT FROM l.new_city
RETURNING c.customer_id, c.city;

ROLLBACK;
~~~

With the sample data, customer 2 receives `HCM` (event 2 is newer than event 1), and customer 1 receives `DNG`.

`event_id DESC` serves as a **tiebreaker** if two events share the exact same `effective_at`. This rule makes representative selection deterministic and explainable. When updating by a unique key directly, `DISTINCT ON` is unnecessary.

## 25. UPDATE with CASE and a FROM Clause

You can combine `UPDATE ... FROM` with `CASE` to apply rule-based updates from a source table.

Example updating `tier` based on the total amount of `paid` orders:

~~~sql
BEGIN;

WITH paid_totals AS (
    SELECT
        c.customer_id,
        COALESCE(
            SUM(o.total_amount) FILTER (WHERE o.status = 'paid'),
            0
        ) AS lifetime_paid
    FROM update_lab.customers AS c
    LEFT JOIN update_lab.orders AS o
        ON o.customer_id = c.customer_id
    GROUP BY c.customer_id
)
UPDATE update_lab.customers AS c
SET
    tier = CASE
        WHEN p.lifetime_paid >= 200 THEN 'gold'
        WHEN p.lifetime_paid >= 50 THEN 'silver'
        ELSE 'standard'
    END,
    updated_at = now()
FROM paid_totals AS p
WHERE p.customer_id = c.customer_id
RETURNING c.customer_id, c.tier;

ROLLBACK;
~~~

Because the `paid_totals` CTE starts from **customers** with a `LEFT JOIN`, every customer gets one aggregated row, even those with no `paid` orders. `FILTER (WHERE ...)` includes only paid orders; `COALESCE` converts empty sums to 0.

This is only a tier-calculation example for learning `UPDATE`. In production systems, tier transitions often involve refunds, time windows, currencies, and write permissions.

### Only Update When Tier Actually Changes

You can compute `target_tier` in another CTE and filter with:

~~~sql
WHERE c.tier IS DISTINCT FROM target_tier
~~~

This avoids rewriting rows whose tier is already accurate. Remember that `updated_at` should only change according to the application's defined update policy.

## 26. Updating JSONB with jsonb_set

PostgreSQL's `jsonb` type stores parsed JSON objects and allows manipulating nested keys.

The `products` table has:

~~~sql
attributes jsonb NOT NULL DEFAULT '{}'::jsonb
~~~

For Coffee:

~~~json
{"category":"beverage","color":"brown"}
~~~

To change `color` to `black` while preserving all other attributes:

~~~sql
BEGIN;

UPDATE update_lab.products
SET
    attributes = jsonb_set(
        attributes,
        '{color}',
        to_jsonb('black'::text),
        true
    ),
    updated_at = now()
WHERE product_id = 101
RETURNING product_id, attributes;

ROLLBACK;
~~~

`jsonb_set(target, path, new_value, create_if_missing)` produces a new `jsonb` value from the existing one:

- `attributes` is the initial JSONB value.
- `'{color}'` is the path to the top-level `color` key.
- `to_jsonb('black'::text)` produces the JSON string `"black"`, rather than an untyped SQL text literal.
- `true` creates the final key if missing per function rules.

The result contains `category = beverage` and `color = black`.

### Removing a JSONB Key

~~~sql
BEGIN;

UPDATE update_lab.products
SET attributes = attributes - 'color'
WHERE product_id = 101
RETURNING attributes;

ROLLBACK;
~~~

The `- 'color'` operator removes the top-level `color` key from the JSONB object, not the entire product row.

### Replacing the Entire Object

~~~sql
UPDATE update_lab.products
SET attributes = '{"category":"beverage"}'::jsonb
WHERE product_id = 101;
~~~

Unlike `jsonb_set`, this **replaces the entire `attributes` column**, losing any other keys omitted from the new object. That may be intentional, or a bug if the application only meant to edit a single attribute.

## 27. UPDATE Can Modify a Primary Key, Though Usually It Should Not

In SQL, if constraints allow, you can write:

~~~sql
UPDATE update_lab.customers
SET customer_id = 10
WHERE customer_id = 1;
~~~

However, in the lab schema, `orders.customer_id` is a foreign key referencing `customers` without `ON UPDATE CASCADE`, so changing the key of customer 1 (who already has orders) is rejected.

If the parent key is mutable and FKs specify `ON UPDATE CASCADE`, PostgreSQL cascades the change to child foreign keys. Even so, for surrogate primary keys like UUIDs or identities, the standard design rule is to **keep IDs immutable** and place mutable business codes in separate columns.

Never update a primary key merely to "make IDs look tidy" without auditing all foreign keys, external APIs, caches, events, logs, and linked data.

## 28. UPDATE Does Not Support ORDER BY or LIMIT Directly

PostgreSQL does not directly support syntax like:

~~~sql
-- NOT VALID STANDARD POSTGRESQL UPDATE SYNTAX.
UPDATE update_lab.orders
SET status = 'cancelled'
WHERE status = 'pending'
ORDER BY order_id
LIMIT 1;
~~~

To update a subset chosen by ordering, **select the target keys first** in a CTE or subquery, then `UPDATE` matching those keys.

Example selecting **the single pending order with the smallest ID**:

~~~sql
BEGIN;

WITH chosen AS (
    SELECT order_id
    FROM update_lab.orders
    WHERE status = 'pending'
    ORDER BY order_id
    LIMIT 1
)
UPDATE update_lab.orders AS o
SET
    status = 'cancelled',
    updated_at = now()
FROM chosen AS c
WHERE o.order_id = c.order_id
  AND o.status = 'pending'
RETURNING o.order_id, o.status;

ROLLBACK;
~~~

With the seed data, order 1001 is chosen.

`SELECT ... ORDER BY ... LIMIT 1` selects a deterministic target key from the data read at that point. The final `UPDATE` still checks `o.status = 'pending'` to prevent invalid transitions if the status changed concurrently.

### Batching with Multiple Workers

For a shared processing queue, combine `FOR UPDATE SKIP LOCKED` during key selection so workers avoid contending on rows already locked by others:

~~~sql
BEGIN;

WITH picked AS (
    SELECT o.order_id
    FROM update_lab.orders AS o
    WHERE o.status = 'pending'
    ORDER BY o.order_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE update_lab.orders AS o
SET
    status = 'cancelled',
    updated_at = now()
FROM picked AS p
WHERE p.order_id = o.order_id
RETURNING o.order_id;

ROLLBACK;
~~~

`SKIP LOCKED` is specifically suited for queue/worker patterns; it intentionally skips locked rows, so **do not use it for ordinary queries that require a complete, consistent list**.

This example uses `cancelled` solely to illustrate `UPDATE`; do not use real order cancellation as a job-queue mechanism. Production queues need dedicated processing statuses, deadlines/retries, and worker recovery.

## 29. UPDATE with CTEs and Complex Expressions

`WITH` makes SQL more readable by separating source computation from the write step.

Example summing paid amounts per customer and updating loyalty points by a test rule:

~~~sql
BEGIN;

WITH paid_amounts AS (
    SELECT
        customer_id,
        COALESCE(
            SUM(total_amount) FILTER (WHERE status = 'paid'),
            0
        ) AS paid_total
    FROM update_lab.orders
    GROUP BY customer_id
),
calculated_points AS (
    SELECT
        customer_id,
        FLOOR(paid_total / 10)::integer AS target_points
    FROM paid_amounts
)
UPDATE update_lab.customers AS c
SET
    loyalty_points = p.target_points,
    updated_at = now()
FROM calculated_points AS p
WHERE p.customer_id = c.customer_id
  AND c.loyalty_points IS DISTINCT FROM p.target_points
RETURNING c.customer_id, c.loyalty_points;

ROLLBACK;
~~~

This demonstrates splitting calculations into two read CTEs, keeping the final `UPDATE` clean.

**Limitation:** the `paid_amounts` CTE groups only customers who have at least one order. Customers with no orders are not updated rather than having their points set to 0. If business rules require covering all customers, start from `customers` and `LEFT JOIN` orders before aggregating.

**Important business note:** `SET loyalty_points = target_points` overwrites all existing points. If the application tracks redeemed points, refunds, or manual adjustments, this formula would be wrong. Syntactically valid SQL still needs properly designed business rules.

## 30. Preventing Lost Updates Under Concurrent Sessions

A common concurrency bug:

1. Session A reads `stock_qty = 10`.
2. Session B also reads `stock_qty = 10`.
3. A computes 10 - 3 = 7 and writes 7.
4. B computes 10 - 2 = 8 and writes 8.
5. The final value is 8 instead of 5 because both sessions overwrote using stale reads without synchronization.

This is an application-level **lost update**.

### Never Subtract Outside the DB and Write Back Stale Computed Values

~~~text
SELECT stock_qty FROM products WHERE product_id = 101;
-- Application computes new_qty = old_qty - requested_qty.
UPDATE products SET stock_qty = :new_qty WHERE product_id = 101;
~~~

Without proper locking or version checks, `:new_qty` may already be stale by the time `UPDATE` runs.

### Perform the Calculation Inside UPDATE Itself

~~~sql
BEGIN;

UPDATE update_lab.products
SET stock_qty = stock_qty - 3
WHERE product_id = 101
  AND stock_qty >= 3
RETURNING product_id, stock_qty;

ROLLBACK;
~~~

When concurrent transactions update **the same row**, PostgreSQL manages row locks. Under `READ COMMITTED` isolation, if an `UPDATE` waits for another transaction modifying that row, PostgreSQL re-evaluates the condition against the committed row version once the lock clears. Having `stock_qty >= 3` inside the `UPDATE` prevents deducting below zero when stock has become insufficient.

This is dramatically safer than overwriting with a precomputed quantity. Still, workflows spanning multiple products, multiple warehouses, inventory reservations, or cross-table invariants may require richer transactions and locking.

## 31. Optimistic Locking with a Version Column

Another technique adds a `version` column to verify the record is still at the version the application read.

~~~sql
CREATE TABLE update_lab.version_demo (
    item_id integer PRIMARY KEY,
    item_name text NOT NULL,
    quantity integer NOT NULL CHECK (quantity >= 0),
    row_version integer NOT NULL DEFAULT 0
);

INSERT INTO update_lab.version_demo
    (item_id, item_name, quantity)
VALUES (1, 'Sample item', 10);
~~~

Suppose the application read `quantity = 10`, `row_version = 0`. On write:

~~~sql
BEGIN;

UPDATE update_lab.version_demo
SET
    quantity = 7,
    row_version = row_version + 1
WHERE item_id = 1
  AND row_version = 0
RETURNING item_id, quantity, row_version;

ROLLBACK;
~~~

If another transaction updated the row first and bumped `row_version` to 1, `row_version = 0` no longer matches; the statement returns 0 rows instead of silently overwriting the other user's changes.

### What Should You Do When 0 Rows Are Returned?

The application can:

- Re-read the latest version and ask the user to confirm.
- Recompute the operation against fresh data.
- Return a business conflict error.
- Perform a bounded retry when the operation is safely idempotent/re-computable.

Never retry blindly in an infinite loop overwriting regardless of version—that defeats optimistic locking.

## 32. Using Transactions to Test UPDATE Safely

A minimal workflow before modifying multiple rows:

~~~sql
BEGIN;

-- 1. Inspect rows matching the condition.
SELECT order_id, customer_id, status, total_amount
FROM update_lab.orders
WHERE status = 'pending'
ORDER BY order_id;

-- 2. Update using the exact same condition.
UPDATE update_lab.orders
SET
    status = 'cancelled',
    updated_at = now()
WHERE status = 'pending'
RETURNING order_id, status;

-- 3. Verify results within the same transaction.
SELECT order_id, status
FROM update_lab.orders
ORDER BY order_id;

-- 4. Learning only: revert to initial state.
ROLLBACK;
~~~

In production, **never assume that a preview `SELECT` followed immediately by an `UPDATE` selects the exact same set of rows** if concurrent transactions are writing. Account for isolation, locking, predicates, and concurrent updates. Pre-checking with `SELECT` helps verify expected scope, not lock data against change.

### SAVEPOINT When Testing Statements That Might Fail

~~~sql
BEGIN;

SAVEPOINT before_try;

-- In the lab, this deliberately violates CHECK(stock_qty >= 0).
UPDATE update_lab.products
SET stock_qty = -1
WHERE product_id = 101;

-- In interactive sessions when the command above errors:
ROLLBACK TO SAVEPOINT before_try;

-- Subsequent SQL commands can now continue in the transaction.
SELECT product_id, stock_qty
FROM update_lab.products
WHERE product_id = 101;

ROLLBACK;
~~~

When a SQL error occurs inside a transaction, PostgreSQL puts the transaction into an aborted state; subsequent commands cannot run until you `ROLLBACK` or roll back to a `SAVEPOINT`. In scripts with `ON_ERROR_STOP` enabled, the client stops immediately on error; keep deliberate error examples out of automated scripts.

## 33. Impact of UPDATE on MVCC and Indexes

PostgreSQL uses **MVCC** to manage row versions. An `UPDATE` normally writes a new row version and marks the old version obsolete per visibility rules.

Consequences:

- `UPDATE` is not a simple in-place overwrite of a few bytes in a file.
- It generates WAL and work for `VACUUM`.
- Indexes may need maintenance when indexed key columns change.
- If only non-indexed columns change and conditions allow, PostgreSQL can use **HOT (Heap-Only Tuple)** updates to avoid index updates.
- A large multi-row `UPDATE` can hold locks and consume substantial resources.

Example:

~~~sql
UPDATE update_lab.customers
SET updated_at = now()
WHERE customer_id = 1;
~~~

Even if name or city did not change, this `UPDATE` still modifies the matching row, creates a new row version, and fires associated triggers.

### Why Avoid Unnecessary Writes?

Under heavy workloads, skipping rows that already hold the target value reduces write amplification, trigger invocations, and WAL volume. Use:

~~~sql
UPDATE update_lab.customers
SET city = 'HCM'
WHERE customer_id = 1
  AND city IS DISTINCT FROM 'HCM';
~~~

However, avoiding writes is not the only goal. If business rules require recording user activity even when values are unchanged, writing an audit/event record by design may be appropriate.

## 34. Constraints, Triggers, Privileges, and RLS Still Apply

`UPDATE` never bypasses rules:

- `NOT NULL`: cannot assign `NULL` to a required column.
- `CHECK`: new values must satisfy constraints, e.g. `stock_qty >= 0`.
- `UNIQUE`: cannot change an email to match another customer's email.
- `FOREIGN KEY`: updating `customer_id` in `orders` must point to an existing customer.
- `ON UPDATE CASCADE/RESTRICT/NO ACTION`: governs behavior when referenced parent keys change.
- Triggers: execute on `UPDATE`, including audit or timestamp logic.
- Row-level security (RLS): restricts which rows can be updated and what new values are permitted by policy.
- SQL privileges: the role needs `UPDATE` privilege on the target table/columns and `SELECT` privilege on columns read in expressions, `WHERE`, or `RETURNING`.

This example fails because the email already exists:

~~~sql
-- DELIBERATE ERROR: collides with UNIQUE(email) for customer An.
UPDATE update_lab.customers
SET email = 'an@example.test'
WHERE customer_id = 2;
~~~

Do not drop constraints just to make an `UPDATE` pass when data integrity matters. Determine whether two customers legitimately share an email, whether invalid input was sent, or whether accounts must be merged via a proper workflow.

## 35. UPDATE and Partitioned Tables

In PostgreSQL, when the target is a **partitioned table**, an `UPDATE` that changes the partition key can cause the row to move to a different partition. This is a special case compared to ordinary tables.

The system handles cross-partition row movement internally, with implications for concurrency, triggers, and potential serialization errors under concurrent workloads. If your application updates partition keys or date-range partition columns, consult the documentation for your exact PostgreSQL version and test in a production-like environment.

Updating an ordinary non-partition-key column **does not** require manually moving rows across partitions, yet changing partition keys should never be assumed to be a lightweight `UPDATE`.

## 36. RETURNING and JDBC Operations

In Java with pgJDBC, `UPDATE ... RETURNING` can be read through a `ResultSet`:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class StockRepository {
    public static boolean deductStock(
        Connection connection,
        int productId,
        int quantity
    ) throws SQLException {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "quantity must be positive"
            );
        }

        String sql = """
            UPDATE update_lab.products
            SET
                stock_qty = stock_qty - ?,
                updated_at = now()
            WHERE product_id = ?
              AND stock_qty >= ?
            RETURNING product_id, stock_qty
            """;

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {
            statement.setInt(1, quantity);
            statement.setInt(2, productId);
            statement.setInt(3, quantity);

            try (ResultSet rs = statement.executeQuery()) {
                if (!rs.next()) {
                    return false;
                }

                int remaining = rs.getInt("stock_qty");
                System.out.println(
                    "Remaining stock: " + remaining
                );
                return true;
            }
        }
    }
}
~~~

With `UPDATE ... RETURNING`, pgJDBC lets you call `executeQuery()` to read the returned result set. For an `UPDATE` without `RETURNING`, `executeUpdate()` returns the affected row count.

### Why Bind Parameters?

Using `?` and `PreparedStatement` passes typed values safely and avoids string-concatenated SQL from untrusted input:

~~~java
// Never concatenate SQL strings:
// "... WHERE product_id = " + userInput
~~~

However, parameter binding does not enforce role or tenant permissions. If an API allows deducting stock, the application must still verify authorization and business rules.

### Transaction Boundaries Belong to the Service Layer

The method above does not call `commit()` or `rollback()` itself. In a real application, the repository participates in a larger transaction covering order creation, stock deduction, and history logging. Never alter `autoCommit` on a connection managed by a transaction manager without a clear contract.

## 37. When to Use UPDATE ... FROM, Subqueries, CTEs, or CASE?

| Requirement | Appropriate SQL Pattern | Rationale |
| --- | --- | --- |
| Change one customer's city | `UPDATE ... SET city=... WHERE id=...` | Simple, clear key |
| Increment points from current value | `SET points = points + :delta` | Evaluated on row at update time |
| Choose value conditionally per row | `SET tier = CASE ... END` | Branching logic |
| Keep column if parameter is NULL | `SET col = COALESCE(:value,col)` | Valid only if NULL means "no change" |
| Clear a nullable value | `SET phone = NULL` | NULL carries explicit meaning |
| Reset to schema default | `SET tier = DEFAULT` | Avoids repeating default constants |
| Update only when truly different | `WHERE col IS DISTINCT FROM new_value` | Handles NULLs accurately |
| Update from a 1:1 mapping table | `UPDATE ... FROM source` | Uses source columns |
| Update from a 1:N source | `WITH totals AS (... GROUP BY ...) UPDATE ... FROM totals` | Guarantees one source row per target |
| Single aggregated value per row | Scalar subquery with `SUM`/`COALESCE` | Clear assignment expression |
| One latest representative row | `DISTINCT ON` with `ORDER BY` and tiebreaker | Deterministic source choice |
| Limit modified row subset | CTE picking keys, then UPDATE | PostgreSQL lacks direct UPDATE ORDER BY LIMIT |
| Retrieve actually modified rows | `RETURNING` | Obtain values straight from DML |
| Prevent overwrites by other sessions | Status guard, version column, or row locks | Concurrency control |

The same requirement can be written in multiple ways. Favor patterns that clearly prove **the right row set**, **the right assignments**, and **deterministic behavior when data deviates from expectations**.

## 38. Common Mistakes

### 38.1. Omitting WHERE

~~~sql
UPDATE update_lab.orders
SET status = 'cancelled';
~~~

Every order is updated, not just one. Always verify scope before running.

### 38.2. Missing Parentheses with AND/OR in WHERE

`customer_id = 1 AND status = 'pending' OR status = 'cancelled'` matches cancelled orders for all customers. Use parentheses or `IN` to express intent accurately.

### 38.3. Comparing NULL with `=`

`phone = NULL` matches no rows. Use `phone IS NULL`.

### 38.4. Using Only `<>` to Skip Identical Values

`city <> 'HCM'` skips rows where `city` is `NULL`. Use `IS DISTINCT FROM` when `NULL` must be treated as distinct from a value.

### 38.5. Assuming SET Assignments Execute Sequentially

`SET a=b, b=a` swaps the values; it does not set both columns to old `b` or new `a`. Right-hand expressions read pre-update row values.

### 38.6. Putting an Alias on the Left Side of SET

`SET p.list_price = 10` is invalid syntax for target columns. Write `SET list_price = 10`.

### 38.7. Using COALESCE for All Three PATCH States

`COALESCE(NULL, old_value)` cannot clear an existing value. Distinguish an omitted field from an explicit `NULL`.

### 38.8. Forgetting ELSE in CASE

When no branch matches, `CASE` returns `NULL`. On a `NOT NULL` column, the `UPDATE` fails.

### 38.9. Non-Deterministic UPDATE FROM on a 1:N Source

An order has multiple line items; picking an arbitrary `order_items` row for `total_amount` does not compute the sum. Aggregate with `GROUP BY` or enforce a unique selection rule.

### 38.10. Thinking UPDATE FROM Modifies Every Table in FROM

Only the target table in `UPDATE` is directly modified. Tables in `FROM` are read-only sources.

### 38.11. Scalar Subquery Returning Multiple Rows

PostgreSQL raises an error if an expression expects one value and the subquery returns multiple rows. Aggregate or pick a single row deterministically.

### 38.12. Thinking RETURNING Only Emits Columns Whose Values Changed

`RETURNING` emits rows processed by the `UPDATE`. Running `SET status='paid'` on an already-paid row still processes and returns that row unless filtered in `WHERE`.

### 38.13. Overwriting with Values Computed from Stale Application Reads

`SET stock_qty = :new_stock_from_old_read` risks lost updates. Put arithmetic inside `UPDATE` or use optimistic locking/proper transactions.

### 38.14. Treating 0 Affected Rows as a SQL Error

When `WHERE` matches nothing, PostgreSQL succeeds with 0 rows affected. The application must distinguish non-existence, invalid state, and constraint errors.

### 38.15. Assuming ROLLBACK Reverts Every Side Effect

`ROLLBACK` undoes transactional table changes in PostgreSQL, but consumed sequence numbers, external service calls, and non-transactional side effects do not automatically revert.

### 38.16. Forgetting a Transaction Enters Aborted State After an Error

A constraint error inside a transaction blocks subsequent statements until you roll back or roll back to a savepoint.

### 38.17. Confusing an Outer CTE LIMIT with Limiting the UPDATE

If you put an `UPDATE` inside a data-modifying CTE and write `SELECT ... LIMIT 1` outside, the DML CTE still executes on all matching rows. Limit the key-selection source before `UPDATE`, not the output.

### 38.18. Adding Indexes Without Checking WHERE Patterns

Indexes on heavily filtered keys help locate rows faster, but indexes add maintenance overhead during `UPDATE`. Check workload and `EXPLAIN`.

### 38.19. Modifying Primary Keys Without Checking FKs

Changing `customer_id` can be blocked by FKs or cascade unexpectedly, breaking external references. Prefer immutable surrogate keys.

### 38.20. Updating Too Many Rows in One Transaction Without Considering Locks/WAL

Even a short statement can modify millions of rows, holding locks for a long time and generating massive WAL. Plan batching and maintenance for large datasets.

## 39. Practice Exercises with Answers

Run each exercise independently against the seed data from Section 2. For exercises that modify data, wrap them in `BEGIN` and `ROLLBACK` unless you want to persist changes.

### Exercise 1. Update a City

Change customer Binh's (2) `city` to `Hue`.

~~~sql
BEGIN;
UPDATE update_lab.customers
SET city = 'Hue'
WHERE customer_id = 2
RETURNING customer_id, city;
ROLLBACK;
~~~

**Answer:** One row with `customer_id = 2` and `city = Hue`.

### Exercise 2. Add 30 Loyalty Points to An

~~~sql
BEGIN;
UPDATE update_lab.customers
SET loyalty_points = loyalty_points + 30
WHERE customer_id = 1
RETURNING customer_id, loyalty_points;
ROLLBACK;
~~~

**Answer:** New points total is **150**.

### Exercise 3. Deduct 4 Units of Coffee When Stock Is Sufficient

~~~sql
BEGIN;
UPDATE update_lab.products
SET stock_qty = stock_qty - 4
WHERE product_id = 101
  AND stock_qty >= 4
RETURNING product_id, stock_qty;
ROLLBACK;
~~~

**Answer:** One row, new stock is **6**.

### Exercise 4. What Happens If We Try to Deduct 2 Units of Cup?

~~~sql
BEGIN;
UPDATE update_lab.products
SET stock_qty = stock_qty - 2
WHERE product_id = 103
  AND stock_qty >= 2
RETURNING product_id, stock_qty;
ROLLBACK;
~~~

**Answer:** **0 rows** updated because Cup's stock is 0.

### Exercise 5. Reset Tier to DEFAULT

~~~sql
BEGIN;
UPDATE update_lab.customers
SET tier = DEFAULT
WHERE customer_id = 1
RETURNING tier;
ROLLBACK;
~~~

**Answer:** `standard`, per the column default.

### Exercise 6. Update Phone Only If Currently NULL

~~~sql
BEGIN;
UPDATE update_lab.customers
SET phone = '0123456789'
WHERE customer_id = 2
  AND phone IS NULL
RETURNING customer_id, phone;
ROLLBACK;
~~~

**Answer:** One row. If `phone` is already non-NULL, no update occurs.

### Exercise 7. Exclude Cities Already Equal to HCM

~~~sql
BEGIN;
UPDATE update_lab.customers
SET city = 'HCM'
WHERE is_active = true
  AND city IS DISTINCT FROM 'HCM'
RETURNING customer_id, city;
ROLLBACK;
~~~

**Answer:** With the seed data, only Binh (2) changes from `HAN` to `HCM`; An (1) and Dung (4) are already in `HCM`; Chi (3) is inactive.

### Exercise 8. Classify Tier Based on Points

~~~sql
BEGIN;
UPDATE update_lab.customers
SET tier = CASE
    WHEN loyalty_points >= 100 THEN 'gold'
    WHEN loyalty_points >= 50 THEN 'silver'
    ELSE 'standard'
END
WHERE is_active
RETURNING customer_id, tier;
ROLLBACK;
~~~

**Answer:** An gets `gold`, Binh `silver`, Dung `standard`; Chi is excluded.

### Exercise 9. Calculate sale_price from the Discounts Table

~~~sql
BEGIN;
UPDATE update_lab.products AS p
SET sale_price =
    ROUND(p.list_price * (1 - d.discount_percent / 100), 2)
FROM update_lab.product_discounts AS d
WHERE d.product_id = p.product_id
RETURNING p.product_id, p.sale_price;
ROLLBACK;
~~~

**Answer:** Coffee becomes 27.00, Tea 19.00; Cup has no discount row and remains unchanged.

### Exercise 10. Why Is Directly Using UPDATE FROM order_items Wrong?

~~~sql
UPDATE update_lab.orders AS o
SET total_amount = i.quantity * i.unit_price
FROM update_lab.order_items AS i
WHERE i.order_id = o.order_id;
~~~

**Answer:** An order can have multiple line items. For order 1001 with two lines, PostgreSQL does not guarantee which line is used, and does not sum them. You must `GROUP BY order_id` first.

### Exercise 11. Recalculate Total for Order 1001

~~~sql
BEGIN;
UPDATE update_lab.orders AS o
SET total_amount = COALESCE(
    (
        SELECT SUM(i.quantity * i.unit_price)
        FROM update_lab.order_items AS i
        WHERE i.order_id = o.order_id
    ),
    0
)
WHERE o.order_id = 1001
RETURNING o.order_id, o.total_amount;
ROLLBACK;
~~~

**Answer:** 2 × 30 + 1 × 20 = **80.00**.

### Exercise 12. Conditionally Transition a Pending Order to Paid

~~~sql
BEGIN;
UPDATE update_lab.orders
SET
    status = 'paid',
    paid_at = now(),
    updated_at = now()
WHERE order_id = 1003
  AND status = 'pending'
RETURNING order_id, status, paid_at;
ROLLBACK;
~~~

**Answer:** One row; order 1003 transitions from `pending` to `paid`.

### Exercise 13. If the Order Is Already Paid, What Does Conditional UPDATE Return?

Replace `order_id = 1003` with `order_id = 1002` in Exercise 12.

**Answer:** **0 rows** because order 1002 is already `paid`, failing `status = 'pending'`.

### Exercise 14. Update a JSONB Attribute

~~~sql
BEGIN;
UPDATE update_lab.products
SET attributes = jsonb_set(
    attributes,
    '{color}',
    to_jsonb('black'::text),
    true
)
WHERE product_id = 101
RETURNING attributes;
ROLLBACK;
~~~

**Answer:** `color = black`, while `category = beverage` remains intact.

### Exercise 15. Swap Two Columns

~~~sql
BEGIN;
UPDATE update_lab.swap_demo
SET (a, b) = (b, a)
WHERE demo_id = 1
RETURNING a, b;
ROLLBACK;
~~~

**Answer:** `a = 20`, `b = 10`.

### Exercise 16. Why Is the Following Condition Dangerous?

~~~sql
WHERE customer_id = 1 AND status = 'pending'
   OR status = 'cancelled'
~~~

**Answer:** Because `AND` binds tighter than `OR`, the condition matches cancelled orders across all customers. Use `customer_id = 1 AND status IN ('pending','cancelled')` if that is the intent.

### Exercise 17. Use a CTE to Update One Pending Order

~~~sql
BEGIN;
WITH chosen AS (
    SELECT order_id
    FROM update_lab.orders
    WHERE status = 'pending'
    ORDER BY order_id
    LIMIT 1
)
UPDATE update_lab.orders AS o
SET status = 'cancelled'
FROM chosen AS c
WHERE c.order_id = o.order_id
  AND o.status = 'pending'
RETURNING o.order_id, o.status;
ROLLBACK;
~~~

**Answer:** From the seed data, order 1001 is selected.

### Exercise 18. Optimistic Locking to Prevent Overwrites

~~~sql
BEGIN;
UPDATE update_lab.version_demo
SET
    quantity = 7,
    row_version = row_version + 1
WHERE item_id = 1
  AND row_version = 0
RETURNING quantity, row_version;
ROLLBACK;
~~~

**Answer:** While the record is at version 0, one row returns with `quantity = 7`, `row_version = 1`. If the version changed, `UPDATE` returns 0 rows to signal a conflict.

## 40. Safe Workflow for Preparing an UPDATE in Real Projects

Before running a significant `UPDATE`, walk through these steps:

1. **Identify the target table and columns to modify.** Do not touch unrelated columns.
2. **Write the `WHERE` condition first.** Prefer primary keys, business/tenant keys, and valid starting states.
3. **Run an exploratory `SELECT` with the same condition** to inspect expected scope; remember data can change concurrently.
4. **Verify `NULL` handling and `AND`/`OR` logic.** Use parentheses and `IS DISTINCT FROM` where needed.
5. **Define assignment expressions:** constants, arithmetic, `CASE`, `COALESCE`, `DEFAULT`, subqueries, or `FROM`.
6. **If using `UPDATE ... FROM`, guarantee one source row per target row.** Use constraints, `GROUP BY`, `DISTINCT ON`, or proper scalar subqueries.
7. **Evaluate constraints, FKs, triggers, and RLS.** New values must satisfy all applicable rules.
8. **Design for concurrency:** state guards, in-statement increments/decrements, optimistic locking, row locks, or appropriate isolation.
9. **Use `RETURNING`** to verify which rows were actually modified and inspect their new values.
10. **Set explicit transaction boundaries.** Handle errors and rollbacks; never leave half a business workflow committed unintentionally.
11. **For large datasets, check execution plan and scale:** filtering indexes, locks, WAL, triggers, vacuum, and batching.
12. **Test edge cases:** 0 rows, 1 row, multiple rows, `NULL`, unchanged values, duplicate source rows, constraint violations.
13. **Never assume `UPDATE=0` means business success.** Translate that result into the right API response.
14. **Never test destructive SQL directly on production.** Use a lab database, backups, and migration pipelines.

Sample template for a conditional, verifiable update:

~~~sql
BEGIN;

UPDATE update_lab.orders AS o
SET
    status = 'paid',
    paid_at = now(),
    updated_at = now()
WHERE o.order_id = 1001
  AND o.status = 'pending'
RETURNING
    o.order_id,
    o.customer_id,
    o.status,
    o.paid_at;

-- In the lab, use ROLLBACK. In production code,
-- the service decides COMMIT according to transaction boundaries.
ROLLBACK;
~~~

## 41. Official PostgreSQL Documentation

When implementing in production systems, consult the documentation for your server version:

- [PostgreSQL — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE`, `FROM`, `WHERE`, `RETURNING` syntax and multiple-source-row notes.
- [PostgreSQL — Conditional Expressions](https://www.postgresql.org/docs/current/functions-conditional.html): `CASE`, `COALESCE`, `NULLIF`.
- [PostgreSQL — Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): `IS DISTINCT FROM`, `IS NULL`, and comparisons.
- [PostgreSQL — JSON Functions and Operators](https://www.postgresql.org/docs/current/functions-json.html): `jsonb_set` and JSONB operators.
- [PostgreSQL — WITH Queries](https://www.postgresql.org/docs/current/queries-with.html): CTEs and data-modifying statements.
- [PostgreSQL — Concurrency Control](https://www.postgresql.org/docs/current/mvcc.html): MVCC, transactions, and concurrency behavior.
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locking and lock modes.
- [PostgreSQL — Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): inspecting query plans and costs.

`/current/` links point to the latest PostgreSQL documentation on the website. If your server runs another major version, open the corresponding version's docs to verify exact syntax and behavior.

## 42. Summary

`UPDATE` **selects the rows to modify and assigns new values to their columns**:

~~~sql
UPDATE target_table
SET
    column_a = expression_a,
    column_b = expression_b
WHERE selection_condition
RETURNING column_a, column_b;
~~~

Most important rules:

- **`WHERE` defines scope:** omitting `WHERE` updates the entire table.
- **`SET` accepts expressions:** prior column values, arithmetic, `CASE`, `COALESCE`, `DEFAULT`, subqueries, source tables, or PostgreSQL functions.
- **Assignments read pre-update row values**, rather than computing one column and immediately feeding its new value into the next assignment in the same `SET`.
- **Handle `NULL` explicitly:** `IS NULL`, `IS NOT NULL`, and `IS DISTINCT FROM`.
- **`UPDATE ... FROM` requires a deterministic source:** one target row matching multiple source rows yields unpredictable results.
- **`RETURNING` returns processed rows**, letting applications verify outcomes rather than guessing.
- **Transactions, constraints, and concurrency still matter:** syntactically valid SQL alone does not guarantee business integrity.

Before modifying data, always know **which rows are selected, what values are assigned, what source data is used, and how the outcome will be verified**. When all four are clear, `UPDATE` becomes a powerful yet controllable tool in PostgreSQL.
