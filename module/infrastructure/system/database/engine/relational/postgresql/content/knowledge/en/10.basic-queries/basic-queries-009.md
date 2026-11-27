# CASE, COALESCE, and NULLIF in PostgreSQL Queries

When writing real-world queries, data is not always complete, and a column's raw value is not always suitable for direct display. An order may not be paid yet, a customer may not have provided a phone number, or an average calculation may encounter a zero denominator. We also often need to turn status codes into readable labels, bucket customers into tiers, or sum amounts conditionally.

In PostgreSQL, three essential expressions handle these situations:

- **`CASE`:** picks a result based on one or more conditions, similar to branching in programming languages.
- **`COALESCE`:** returns the **first non-`NULL` value** from a list of expressions.
- **`NULLIF`:** returns `NULL` if two expressions are equal; otherwise returns the first expression.

All three are **SQL expressions**, not standalone statements restricted to `SELECT`. You can combine them inside `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING`, `UPDATE`, aggregates, and many other contexts.

This lesson progresses from syntax and `NULL` mechanics to runnable examples, sales reporting patterns, zero-division protection, data type resolution, differences between simple and searched `CASE`, performance, and common design mistakes.

## 1. Reviewing NULL and Three-Valued Logic in PostgreSQL

Before using `CASE`, `COALESCE`, or `NULLIF`, remember that **`NULL` is not zero, not an empty string, and not boolean `FALSE`**. `NULL` represents an absent or unknown value under the column's semantics.

Example:

~~~sql
SELECT
    NULL::integer AS unknown_number,
    0 AS known_zero,
    ''::text AS empty_text,
    FALSE AS known_false;
~~~

These values carry distinct meanings:

| Value | Typical Meaning | Is It `NULL`? |
| --- | --- | --- |
| `NULL` | Unknown, missing, or not applicable | Yes |
| `0` | Known number equal to zero | No |
| `''` | Zero-length string | No |
| `'   '` | String of spaces | No |
| `FALSE` | Boolean false value | No |

### 1.1. Why Not Use = NULL?

In SQL, standard comparisons with `NULL` do not return `TRUE` or `FALSE`—they return **`UNKNOWN`**:

~~~sql
SELECT
    (NULL::integer = NULL::integer) AS null_equals_null,
    (10 = NULL::integer) AS ten_equals_null,
    (10 <> NULL::integer) AS ten_differs_from_null;
~~~

All three expressions return `NULL` (representing the logical outcome UNKNOWN). Thus:

~~~sql
-- Wrong intent: fails to match NULL rows as expected.
SELECT *
FROM some_table
WHERE some_column = NULL;
~~~

In real queries, use:

~~~sql
WHERE some_column IS NULL
~~~

or:

~~~sql
WHERE some_column IS NOT NULL
~~~

`WHERE` keeps only rows where the predicate evaluates to **TRUE**; both `FALSE` and `UNKNOWN` are discarded.

### 1.2. AND, OR, NOT, and UNKNOWN

Under three-valued logic:

| Expression | Result |
| --- | --- |
| `TRUE AND NULL` | UNKNOWN (`NULL`) |
| `FALSE AND NULL` | FALSE |
| `TRUE OR NULL` | TRUE |
| `FALSE OR NULL` | UNKNOWN (`NULL`) |
| `NOT NULL::boolean` | UNKNOWN (`NULL`) |

This directly affects **`CASE WHEN`**: a `WHEN` branch is taken only when its condition evaluates to `TRUE`; an `UNKNOWN` condition is not treated as TRUE.

### 1.3. IS DISTINCT FROM: NULL-Aware Comparison

PostgreSQL supports:

~~~sql
SELECT
    NULL::integer IS NOT DISTINCT FROM NULL::integer AS same_nulls,
    10 IS DISTINCT FROM NULL::integer AS different_values,
    10 IS NOT DISTINCT FROM 10 AS same_numbers;
~~~

Unlike standard `=`, `IS [NOT] DISTINCT FROM` always returns a definite boolean when encountering `NULL`:

- `a IS NOT DISTINCT FROM b`: treats two `NULL`s as equivalent for this comparison.
- `a IS DISTINCT FROM b`: detects differing values, including when one side is `NULL`.

This is an essential companion tool when checking whether two nullable columns changed. It **does not replace** `NULLIF`, because `NULLIF` returns a value or `NULL`, not a boolean.

## 2. Preparing Practice Data

The examples use a small orders dataset so results are easy to verify visually. Run table creation on a **study database** you control. Never drop or recreate schemas containing real data.

### 2.1. Creating the Schema and Two Tables

~~~sql
CREATE SCHEMA expr_lab_135;

CREATE TABLE expr_lab_135.customers (
    customer_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NULL,
    loyalty_tier TEXT NULL
);

CREATE TABLE expr_lab_135.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NULL
        REFERENCES expr_lab_135.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL,
    subtotal NUMERIC(12, 2) NOT NULL CHECK (subtotal >= 0),
    discount_amount NUMERIC(12, 2) NULL
        CHECK (discount_amount >= 0),
    shipping_fee NUMERIC(12, 2) NULL
        CHECK (shipping_fee >= 0),
    item_count INTEGER NOT NULL CHECK (item_count >= 0),
    status TEXT NULL,
    paid_at TIMESTAMPTZ NULL,
    customer_note TEXT NULL
);
~~~

Design meaning:

- `orders.customer_id` allows `NULL` to represent orders not tied to a registered customer (guest orders).
- `discount_amount` and `shipping_fee` can be `NULL` to model unentered or missing information.
- `item_count = 0` is intentional to demonstrate division by zero; `0` is not turned into `NULL`.
- `status` can be `NULL` to observe `ELSE` branches in `CASE`.
- `paid_at` is populated only for orders with a recorded payment timestamp.

In production systems, every nullable column needs a **clear business rule**: does `NULL` mean unknown, not yet calculated, not applicable, or not entered? Never casually treat every `NULL` as 0 when the difference affects money or reporting.

### 2.2. Inserting Customers

~~~sql
INSERT INTO expr_lab_135.customers
    (customer_id, full_name, email, phone, loyalty_tier)
VALUES
    (1, 'Nguyễn An',   'an@example.test',   '0901111111', 'GOLD'),
    (2, 'Trần Bình',   'binh@example.test', NULL,         'SILVER'),
    (3, 'Lê Chi',      'chi@example.test',  '',           NULL),
    (4, 'Phạm Dũng',   'dung@example.test', '   ',        'GOLD');
~~~

Phone numbers are chosen to illustrate three distinct cases: a populated value, `NULL`, and empty/whitespace-only strings. These are **synthetic dummy values**, not real contact details.

### 2.3. Inserting Orders

~~~sql
INSERT INTO expr_lab_135.orders
    (
        order_id, customer_id, ordered_at,
        subtotal, discount_amount, shipping_fee,
        item_count, status, paid_at, customer_note
    )
VALUES
    (
        101, 1, '2026-11-10 09:00:00+07',
        100000, 10000, NULL,
        2, 'PAID', '2026-11-10 09:10:00+07', NULL
    ),
    (
        102, 1, '2026-11-11 14:00:00+07',
        250000, NULL, 15000,
        5, 'NEW', NULL, ''
    ),
    (
        103, 2, '2026-11-11 16:00:00+07',
        80000, 0, 10000,
        1, 'CANCELLED', NULL, 'Customer changed mind'
    ),
    (
        104, 3, '2026-11-12 10:30:00+07',
        120000, 20000, NULL,
        0, NULL, NULL, '   '
    ),
    (
        105, NULL, '2026-11-12 11:00:00+07',
        70000, NULL, NULL,
        1, 'PAID', '2026-11-12 11:20:00+07', NULL
    ),
    (
        106, 4, '2026-11-13 08:15:00+07',
        1000000, 100000, 25000,
        10, 'PAID', '2026-11-13 08:30:00+07', 'Deliver early'
    );
~~~

### 2.4. Viewing the Raw Data

~~~sql
SELECT
    order_id, customer_id, subtotal, discount_amount,
    shipping_fee, item_count, status, customer_note
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

| Order | Customer | Subtotal | Discount | Shipping | Items | Status |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 101 | 1 | 100,000 | 10,000 | `NULL` | 2 | `PAID` |
| 102 | 1 | 250,000 | `NULL` | 15,000 | 5 | `NEW` |
| 103 | 2 | 80,000 | 0 | 10,000 | 1 | `CANCELLED` |
| 104 | 3 | 120,000 | 20,000 | `NULL` | 0 | `NULL` |
| 105 | `NULL` | 70,000 | `NULL` | `NULL` | 1 | `PAID` |
| 106 | 4 | 1,000,000 | 100,000 | 25,000 | 10 | `PAID` |

Keep in mind: row **103 has a discount equal to 0**; rows 102 and 105 **have no discount recorded yet** (`NULL`). Both may receive the same value in a provisional calculation, yet they **do not carry the same data meaning**.

## 3. CASE Is SQL's Conditional Branching Expression

`CASE` returns a value based on conditions. PostgreSQL supports two standard forms:

1. **Searched CASE**: each branch tests an arbitrary boolean condition.
2. **Simple CASE**: compares one input expression against multiple `WHEN` values.

Both can be used anywhere PostgreSQL accepts a compatible SQL expression.

### 3.1. Searched CASE: Testing Conditions One by One

~~~sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    ...
    ELSE default_result
END
~~~

PostgreSQL evaluates conditions in order; **the first branch whose condition is TRUE** determines the result. If no branch is TRUE:

- With `ELSE`: returns `default_result`.
- Without `ELSE`: returns `NULL`.

Table-free example:

~~~sql
SELECT
    CASE
        WHEN 85 >= 90 THEN 'Excellent'
        WHEN 85 >= 70 THEN 'Pass'
        ELSE 'Needs improvement'
    END AS assessment;
-- Pass
~~~

The second condition holds; PostgreSQL returns `Pass` and skips `ELSE`.

### 3.2. Using CASE to Label Orders by Status

~~~sql
SELECT
    order_id,
    status,
    CASE
        WHEN status = 'PAID' THEN 'Paid'
        WHEN status = 'NEW' THEN 'Newly created'
        WHEN status = 'CANCELLED' THEN 'Cancelled'
        WHEN status IS NULL THEN 'No status yet'
        ELSE 'Other status'
    END AS status_label
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

On the sample data:

| `status` | `status_label` |
| --- | --- |
| `PAID` | Paid |
| `NEW` | Newly created |
| `CANCELLED` | Cancelled |
| `NULL` | No status yet |

The `status IS NULL` branch is vital. Writing `WHEN status = NULL` would **fail to match** `NULL` rows.

### 3.3. CASE for Multi-Column Conditions and Value Ranges

~~~sql
SELECT
    order_id,
    subtotal,
    item_count,
    CASE
        WHEN subtotal >= 500000 AND item_count >= 5
            THEN 'Large multi-item order'
        WHEN subtotal >= 200000
            THEN 'High-value order'
        WHEN item_count = 0
            THEN 'Empty order'
        ELSE 'Standard order'
    END AS order_group
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Searched CASE works well for overlapping conditions or inequality comparisons. **Branch ordering is part of the business rule**: if `subtotal >= 200000` precedes `subtotal >= 500000`, large orders get captured by the broader branch first.

### 3.4. Simple CASE: Matching One Expression Against Values

~~~sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ...
    ELSE default_result
END
~~~

Equivalent status-mapping example:

~~~sql
SELECT
    order_id,
    CASE status
        WHEN 'PAID' THEN 'Paid'
        WHEN 'NEW' THEN 'Newly created'
        WHEN 'CANCELLED' THEN 'Cancelled'
        ELSE 'Unspecified'
    END AS status_label
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Simple CASE is concise when comparing a single expression for equality against fixed values. However, **simple CASE cannot match `status IS NULL` using `WHEN NULL`**:

~~~sql
SELECT
    CASE NULL::text
        WHEN NULL::text THEN 'Two NULLs equal?'
        ELSE 'No match under standard comparison'
    END AS result;
-- No match under standard comparison
~~~

To distinguish `NULL` from unknown codes, use **searched CASE with `IS NULL`**, or normalize inputs under clear rules.

### 3.5. Searched CASE vs. Simple CASE: Which Should You Pick?

| Goal | Recommended Form |
| --- | --- |
| Map codes `PAID`, `NEW`, `CANCELLED` | Simple CASE if `NULL` needs no special handling |
| Handle `NULL` / `IS NOT NULL` | Searched CASE |
| Bucket by `>=`, `BETWEEN`, or multiple columns | Searched CASE |
| Overlapping conditions needing priority order | Searched CASE |
| Map one expression to a few constants | Simple CASE |

### 3.6. CASE Without ELSE

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN 'Payment collected'
    END AS payment_note
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

For non-`PAID` orders, `payment_note` evaluates to `NULL`. That can be intentional so aggregates ignore non-matching rows, though in a UI a `NULL` label may not be helpful. Write `ELSE` explicitly whenever a default value is desired.

## 4. CASE and Precedence Ordering Rules

A frequent mistake is placing a broad condition ahead of a narrower one.

Tier-classification example:

~~~sql
SELECT
    order_id,
    subtotal,
    CASE
        WHEN subtotal >= 100000 THEN 'Order >= 100k'
        WHEN subtotal >= 500000 THEN 'Order >= 500k'
        ELSE 'Small order'
    END AS incorrect_tier
FROM expr_lab_135.orders
WHERE order_id = 106;
~~~

Order `106` has `subtotal = 1000000`, yet gets labeled `'Order >= 100k'` because **the first branch already evaluated to TRUE**.

Fix by ordering from highest threshold down:

~~~sql
SELECT
    order_id,
    subtotal,
    CASE
        WHEN subtotal >= 500000 THEN 'Very large'
        WHEN subtotal >= 100000 THEN 'Medium or large'
        ELSE 'Small'
    END AS correct_tier
FROM expr_lab_135.orders
WHERE order_id = 106;
-- Very large
~~~

Not all conditions order cleanly along a single threshold. When prioritizing across multiple attributes, document the business precedence and include test rows satisfying **multiple conditions simultaneously**.

## 5. CASE with NULL and UNKNOWN

A `WHEN` branch runs only when its predicate evaluates to **TRUE**. If the result is `NULL`/UNKNOWN, PostgreSQL moves to the next branch.

~~~sql
SELECT
    CASE
        WHEN NULL::integer > 0 THEN 'Positive'
        WHEN NULL::integer <= 0 THEN 'Non-positive'
        ELSE 'Insufficient data'
    END AS classify_null;
-- Insufficient data
~~~

This causes a seemingly exhaustive expression:

~~~sql
CASE
    WHEN score >= 50 THEN 'Pass'
    ELSE 'Fail'
END
~~~

to classify **`score IS NULL` as "Fail"**. If `NULL` means not yet graded, that is a business bug. Clearer version:

~~~sql
CASE
    WHEN score IS NULL THEN 'Not graded'
    WHEN score >= 50 THEN 'Pass'
    ELSE 'Fail'
END
~~~

**`ELSE` catches not only "false condition" cases, but also UNKNOWN outcomes.** Whenever working with nullable columns, verify what the default branch captures.

### 5.1. Boolean Expressions in CASE

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' AND paid_at IS NOT NULL
            THEN 'Payment confirmed'
        WHEN status = 'PAID' AND paid_at IS NULL
            THEN 'Needs reconciliation'
        WHEN status IS NULL
            THEN 'Status not entered'
        ELSE 'Unpaid'
    END AS payment_state
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

This shows `CASE` is not restricted to single-column comparisons; you can combine checks like `IS NULL`, `AND`, `OR`, or `EXISTS` as needed.

## 6. COALESCE: Picking the First Non-NULL Value

Syntax:

~~~sql
COALESCE(value_1, value_2, ..., value_n)
~~~

`COALESCE` evaluates arguments in order and returns the **first non-`NULL` value**. If all arguments are `NULL`, it returns `NULL`.

~~~sql
SELECT
    COALESCE(NULL::text, 'Fallback A', 'Fallback B')
        AS first_available,
    COALESCE(NULL::integer, NULL::integer, 42)
        AS first_number,
    COALESCE(NULL::text, NULL::text)
        AS all_missing;
~~~

Results respectively:

~~~text
first_available = Fallback A
first_number    = 42
all_missing     = NULL
~~~

### 6.1. Zero, FALSE, and Empty Strings Are Still Selected

~~~sql
SELECT
    COALESCE(0, 100) AS zero_is_present,
    COALESCE(FALSE, TRUE) AS false_is_present,
    COALESCE(''::text, 'Fallback') AS empty_is_present;
~~~

Results respectively: `0`, `FALSE`, and empty string `''`.

**`COALESCE` does not look for "a business-valid value"; it strictly looks for the first non-`NULL` value.** To treat empty strings as missing, combine it with `NULLIF` or another cleaning step.

### 6.2. Substituting NULL in Arithmetic

Normal arithmetic with `NULL` yields `NULL`:

~~~sql
SELECT
    100000::numeric - NULL::numeric AS unknown_total,
    100000::numeric - COALESCE(NULL::numeric, 0)
        AS defaulted_total;
~~~

Results:

- `unknown_total` → `NULL`.
- `defaulted_total` → `100000`.

Applied to the orders table:

~~~sql
SELECT
    order_id,
    subtotal,
    discount_amount,
    shipping_fee,
    subtotal
        - COALESCE(discount_amount, 0)
        + COALESCE(shipping_fee, 0)
        AS estimated_payable_amount
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

| Order | Subtotal | Discount (NULL → 0) | Shipping (NULL → 0) | Computed Total |
| --- | ---: | ---: | ---: | ---: |
| 101 | 100,000 | 10,000 | 0 | 90,000 |
| 102 | 250,000 | 0 | 15,000 | 265,000 |
| 103 | 80,000 | 0 | 10,000 | 90,000 |
| 104 | 120,000 | 20,000 | 0 | 100,000 |
| 105 | 70,000 | 0 | 0 | 70,000 |
| 106 | 1,000,000 | 100,000 | 25,000 | 925,000 |

The column is named **`estimated_payable_amount`** to emphasize this is an **illustrative convention**: when discount/shipping are `NULL`, this lesson temporarily treats them as 0. If `NULL` means "fee not yet determined", the real payable total **cannot be confirmed yet**; never substitute 0 just to produce a number.

### 6.3. COALESCE Across Multiple Data Sources

Suppose an API wants to display the best available name:

~~~sql
SELECT
    customer_id,
    COALESCE(
        full_name,
        email,
        'Unknown customer'
    ) AS display_name
FROM expr_lab_135.customers;
~~~

In the sample table `full_name` is `NOT NULL`, so fallbacks aren't triggered. In schemas with nullable nicknames, company names, or full names, fallback chains become very useful.

Argument order matters: `COALESCE(preferred_name, legal_name, email)` prioritizes preferred name over legal name rather than picking arbitrarily.

### 6.4. COALESCE in LEFT JOIN

`LEFT JOIN` preserves orders without a matching customer row. For guest order `105`:

~~~sql
SELECT
    o.order_id,
    o.customer_id,
    COALESCE(c.full_name, 'Guest customer')
        AS customer_display_name
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

For row `105`, because `customer_id IS NULL`, `customers` has no matching row, so `c.full_name` is `NULL` and `COALESCE` returns `'Guest customer'`.

Note: an unmatched `LEFT JOIN` row and a matched row whose right-hand nullable column is `NULL` can yield the same fallback. If you need to distinguish them, inspect a `NOT NULL` key from the right table such as `c.customer_id IS NULL`, rather than relying solely on `COALESCE(c.full_name, ...)`.

### 6.5. COALESCE in ORDER BY

To push records without a priority score to the bottom:

~~~sql
-- Hypothetical example assuming table tasks(priority) exists:
-- ORDER BY COALESCE(priority, 999) ASC
~~~

PostgreSQL also has dedicated syntax:

~~~sql
-- ORDER BY priority ASC NULLS LAST
~~~

When the goal is simply placing `NULL`s first or last in sorting, **`NULLS FIRST`/`NULLS LAST` expresses intent more clearly** without inventing a sentinel like `999` that might collide with real data.

## 7. NULLIF: Turning Sentinel Values into NULL When Both Sides Match

Syntax:

~~~sql
NULLIF(expression_1, expression_2)
~~~

Rules:

- If both expressions **are equal** under the comparison operator PostgreSQL selects, return `NULL`.
- If they **are not equal**, return `expression_1` (subject to type resolution rules).

Example:

~~~sql
SELECT
    NULLIF(0, 0) AS zero_equals_zero,
    NULLIF(15, 0) AS fifteen_not_zero,
    NULLIF('N/A'::text, 'N/A'::text) AS missing_marker,
    NULLIF('In progress'::text, 'N/A'::text) AS valid_text;
~~~

| Expression | Result |
| --- | --- |
| `NULLIF(0, 0)` | `NULL` |
| `NULLIF(15, 0)` | 15 |
| `NULLIF('N/A', 'N/A')` | `NULL` |
| `NULLIF('In progress', 'N/A')` | `In progress` |

Conceptually similar to `CASE`:

~~~sql
CASE
    WHEN expression_1 = expression_2 THEN NULL
    ELSE expression_1
END
~~~

This is a **logical** explanation, not a promise that PostgreSQL executes `NULLIF` as a `CASE` evaluating expressions the exact same number of times; never assume volatile functions inside arguments execute only a guessed number of times.

### 7.1. NULLIF Is Not "IS DISTINCT FROM"

~~~sql
SELECT
    NULLIF(NULL::integer, NULL::integer) AS both_null,
    NULLIF(NULL::integer, 0) AS left_null,
    NULLIF(0, NULL::integer) AS right_null;
~~~

Results are `NULL`, `NULL`, and `0` respectively. When either side is `NULL`, `=` evaluates to UNKNOWN rather than TRUE, so `NULLIF` returns the left operand; if the left operand itself was `NULL`, the result is `NULL`.

Never use `NULLIF(a, b) IS NULL` as a general test that `a` and `b` are equal; it can also be `NULL` simply because **`a` was already `NULL`**.

### 7.2. Safe Division by Zero in Numeric Expressions

In PostgreSQL, dividing by 0 raises an error:

~~~sql
-- Intentionally invalid: raises division_by_zero (SQLSTATE 22012).
-- SELECT 100::numeric / 0;
~~~

To turn a zero denominator into `NULL`:

~~~sql
SELECT
    100::numeric / NULLIF(0, 0) AS safe_division;
-- NULL
~~~

Because `NULLIF(0, 0)` is `NULL`, dividing by `NULL` yields `NULL` instead of failing. With a non-zero denominator, calculation proceeds normally:

~~~sql
SELECT
    100::numeric / NULLIF(4, 0) AS valid_division;
-- 25
~~~

### 7.3. Computing Average Value per Item

~~~sql
SELECT
    order_id,
    subtotal,
    item_count,
    subtotal / NULLIF(item_count, 0) AS amount_per_item
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

For order `104`, `item_count = 0`, so `amount_per_item` returns `NULL`. This makes complete sense when "average per item" **is undefined** for zero items.

If the UI truly wants `0` instead of "undefined", you can wrap with `COALESCE`:

~~~sql
SELECT
    order_id,
    COALESCE(
        subtotal / NULLIF(item_count, 0),
        0
    ) AS amount_per_item_for_display
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

Still, weigh the **semantics**: showing `0` on a dashboard can mislead readers into thinking "average item price was 0", when the denominator was actually zero and division is meaningless. For analytics, keeping `NULL` or showing "N/A" is usually better.

### 7.4. Removing Empty Strings and Whitespace-Only Strings

`NULLIF(phone, '')` handles only exact empty strings:

~~~sql
SELECT
    NULLIF(''::text, ''::text) AS empty_is_missing,
    NULLIF('   '::text, ''::text) AS spaces_are_not_empty;
~~~

To treat spaces-only strings as missing too, combine with `btrim`:

~~~sql
SELECT
    customer_id,
    phone,
    NULLIF(btrim(phone), '') AS cleaned_phone,
    COALESCE(
        NULLIF(btrim(phone), ''),
        'Not provided'
    ) AS phone_for_display
FROM expr_lab_135.customers
ORDER BY customer_id;
~~~

For the four customers:

| Customer | Original `phone` | After `NULLIF(btrim(phone), '')` | Displayed |
| --- | --- | --- | --- |
| 1 | `0901111111` | `0901111111` | `0901111111` |
| 2 | `NULL` | `NULL` | Not provided |
| 3 | `''` | `NULL` | Not provided |
| 4 | `'   '` | `NULL` | Not provided |

By default, `btrim` trims standard spaces per its rules; if data includes tabs, Unicode whitespace, or control characters, apply appropriate cleaning rules instead of assuming all whitespace behaves identically.

### 7.5. Normalizing Missing-Data Sentinel Values

Import pipelines might use `'N/A'`, `'-'`, or `'unknown'` to indicate missing data:

~~~sql
SELECT
    COALESCE(
        NULLIF('N/A'::text, 'N/A'),
        'No information'
    ) AS readable_value;
~~~

When multiple sentinel values exist, a clear `CASE` is often easier to read than nested `NULLIF` calls:

~~~sql
SELECT
    CASE
        WHEN raw_value IS NULL THEN NULL
        WHEN lower(btrim(raw_value)) IN ('', 'n/a', 'unknown', '-')
            THEN NULL
        ELSE btrim(raw_value)
    END AS normalized_value
FROM (
    VALUES
        ('N/A'::text),
        (' UNKNOWN '::text),
        ('Valid'::text),
        (NULL::text)
) AS src(raw_value);
~~~

Never strip `'0'`, `'-'`, or `'unknown'` mechanically if they could be **legitimate domain values** in another context. Normalization must match source data and documented conventions.

## 8. Combining CASE, COALESCE, and NULLIF in One Query

The three expressions frequently chain together cleanly:

~~~text
Raw data
   |
   +--> NULLIF: convert sentinel values to NULL
   |
   +--> COALESCE: provide fallback value if needed
   |
   +--> CASE: classify or interpret conditionally
   |
   v
Output expression for reports or APIs
~~~

Example simultaneously labeling statuses, cleaning notes, and computing amounts:

~~~sql
SELECT
    o.order_id,
    CASE
        WHEN o.status IS NULL THEN 'Not entered'
        WHEN o.status = 'PAID' THEN 'Paid'
        WHEN o.status = 'NEW' THEN 'Pending'
        WHEN o.status = 'CANCELLED' THEN 'Cancelled'
        ELSE 'Other'
    END AS status_label,
    COALESCE(
        NULLIF(btrim(o.customer_note), ''),
        'No note'
    ) AS normalized_note,
    o.subtotal
        - COALESCE(o.discount_amount, 0)
        + COALESCE(o.shipping_fee, 0)
        AS estimated_payable,
    CASE
        WHEN o.item_count = 0 THEN 'No items'
        WHEN o.subtotal / NULLIF(o.item_count, 0) >= 100000
            THEN 'High average item value'
        ELSE 'Standard'
    END AS item_value_group
FROM expr_lab_135.orders AS o
ORDER BY o.order_id;
~~~

In this query:

- `CASE` surfaces `NULL` status explicitly instead of lumping it into "Other."
- `NULLIF(btrim(...), '')` converts blank/whitespace-only notes to `NULL`.
- `COALESCE(..., 'No note')` supplies a display label.
- `COALESCE(..., 0)` applies the illustrative fee/discount convention.
- `NULLIF(item_count, 0)` guards against invalid division.

Even though `WHEN o.item_count = 0` handles the zero-item case first, keeping `NULLIF` inside the division expression remains a useful safety net if logic is later refactored or reused.

## 9. CASE for Conditional Aggregation

One of the most valuable uses of `CASE` is **conditional aggregation**: placing `CASE` inside `SUM`, `COUNT`, or `AVG` to compute filtered metrics.

### 9.1. Counting Orders by Status

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS paid_orders,
    SUM(CASE WHEN status = 'NEW' THEN 1 ELSE 0 END)
        AS new_orders,
    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END)
        AS cancelled_orders,
    SUM(CASE WHEN status IS NULL THEN 1 ELSE 0 END)
        AS missing_status_orders
FROM expr_lab_135.orders;
~~~

From the sample data:

| Metric | Count |
| --- | ---: |
| All orders | 6 |
| `PAID` | 3 |
| `NEW` | 1 |
| `CANCELLED` | 1 |
| `NULL` | 1 |

Each row becomes `1` or `0` before summing. If you omit `ELSE 0`, non-matching rows emit `NULL` and `SUM` skips them; if zero rows match, `SUM` returns `NULL` instead of `0`.

### 9.2. How Does COUNT(CASE WHEN...) Work?

~~~sql
SELECT
    COUNT(
        CASE WHEN status = 'PAID' THEN 1 END
    ) AS paid_orders
FROM expr_lab_135.orders;
~~~

`COUNT(expression)` counts **non-`NULL` values**. Here, only `PAID` orders return `1`, while others return `NULL` (since `ELSE` is omitted), yielding `3`.

Compare these patterns:

~~~sql
SELECT
    COUNT(*) AS every_row,
    COUNT(status) AS rows_with_status,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END)
        AS paid_by_case,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_by_filter
FROM expr_lab_135.orders;
~~~

| Expression | Result |
| --- | ---: |
| `COUNT(*)` | 6 |
| `COUNT(status)` | 5 |
| `COUNT(CASE WHEN status = 'PAID' THEN 1 END)` | 3 |
| `COUNT(*) FILTER (WHERE status = 'PAID')` | 3 |

PostgreSQL supports the **`FILTER (WHERE ...)`** clause on aggregate functions. When simply counting or aggregating conditionally, `FILTER` is usually cleaner and more expressive than `SUM(CASE WHEN ...)`. Still, `CASE` remains ideal when different branches contribute different computed values.

### 9.3. Total Revenue by Status

~~~sql
SELECT
    SUM(
        CASE
            WHEN status = 'PAID'
                THEN subtotal - COALESCE(discount_amount, 0)
                     + COALESCE(shipping_fee, 0)
            ELSE 0
        END
    ) AS paid_order_value
FROM expr_lab_135.orders;
~~~

On the sample data, the result is **1,085,000** (order 101: 90,000; 105: 70,000; 106: 925,000).

This is an **exercise-convention total**, not accounting-recognized revenue, refunds, or tax. Financial reporting requires explicit handling of cancellations, refunds, recognition timing, and unconfirmed fees.

### 9.4. Avoiding the "COUNT(CASE ... ELSE 0 END)" Bug

A common logic error:

~~~sql
SELECT
    COUNT(
        CASE WHEN status = 'PAID' THEN 1 ELSE 0 END
    ) AS wrong_paid_count
FROM expr_lab_135.orders;
-- 6, not 3!
~~~

Because **`0` is not `NULL`**, `COUNT` counts the `ELSE 0` branch as well.

To count with `CASE`, choose one of these two patterns:

~~~sql
COUNT(CASE WHEN condition THEN 1 END)
~~~

or:

~~~sql
SUM(CASE WHEN condition THEN 1 ELSE 0 END)
~~~

In PostgreSQL, `COUNT(*) FILTER (WHERE condition)` is also a remarkably clear choice.

## 10. CASE in GROUP BY and HAVING

`CASE` can group records by a **computed classification** rather than solely by raw columns.

~~~sql
SELECT
    CASE
        WHEN subtotal >= 500000 THEN 'Large'
        WHEN subtotal >= 100000 THEN 'Medium'
        ELSE 'Small'
    END AS order_band,
    COUNT(*) AS order_count,
    SUM(subtotal) AS subtotal_sum
FROM expr_lab_135.orders
GROUP BY order_band
ORDER BY
    CASE order_band
        WHEN 'Large' THEN 1
        WHEN 'Medium' THEN 2
        ELSE 3
    END;
~~~

In PostgreSQL, `GROUP BY` can reference a select-list alias in unambiguous cases. If an alias collides with an input column name, resolution rules can surprise you; pick unambiguous aliases or use a **CTE** to separate computation from grouping.

### 10.1. Using a CTE for Cleaner Classification Logic

~~~sql
WITH classified AS (
    SELECT
        order_id,
        subtotal,
        CASE
            WHEN subtotal >= 500000 THEN 'Large'
            WHEN subtotal >= 100000 THEN 'Medium'
            ELSE 'Small'
        END AS order_band
    FROM expr_lab_135.orders
)
SELECT
    order_band,
    COUNT(*) AS order_count,
    SUM(subtotal) AS subtotal_sum
FROM classified
GROUP BY order_band
HAVING COUNT(*) >= 1
ORDER BY order_band;
~~~

`HAVING` filters **groups after aggregation**, whereas `WHERE` filters **rows before aggregation**. `CASE` works in both stages, though semantics and cost differ.

### 10.2. Grouping Customers with and Without a Loyalty Tier

~~~sql
SELECT
    COALESCE(loyalty_tier, 'UNASSIGNED')
        AS loyalty_group,
    COUNT(*) AS customer_count
FROM expr_lab_135.customers
GROUP BY COALESCE(loyalty_tier, 'UNASSIGNED')
ORDER BY loyalty_group;
~~~

Because `COALESCE` transforms the grouping value, readers see `UNASSIGNED` instead of `NULL`. However, if real rows could legitimately store `'UNASSIGNED'` in `loyalty_tier`, this merges **two different meanings**. When separation matters, group by the raw column or build non-colliding labels.

## 11. CASE in ORDER BY: Sorting by Business Rules

Suppose we want to prioritize:

1. `NEW` orders.
2. `PAID` orders.
3. `CANCELLED` orders.
4. Orders with missing or unknown status.

Alphabetical sorting does not satisfy this order. Use `CASE`:

~~~sql
SELECT
    order_id,
    status,
    ordered_at
FROM expr_lab_135.orders
ORDER BY
    CASE
        WHEN status = 'NEW' THEN 1
        WHEN status = 'PAID' THEN 2
        WHEN status = 'CANCELLED' THEN 3
        ELSE 4
    END,
    ordered_at DESC;
~~~

`CASE` computes a **numeric sort key**, while `ordered_at DESC` orders records within the same priority tier.

### 11.1. COALESCE to Label Missing Customer Names

~~~sql
SELECT
    o.order_id,
    COALESCE(c.full_name, 'Guest customer')
        AS customer_name
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY customer_name, o.order_id;
~~~

If you instead want **guest rows last** rather than sorted alphabetically under `'Guest customer'`, use:

~~~sql
ORDER BY c.full_name ASC NULLS LAST, o.order_id
~~~

This explicitly expresses `NULL` sort placement without depending on the fallback label's spelling.

## 12. CASE in WHERE: When Is It Useful and When Is It Not?

Because `CASE` returns a value, you can place a boolean-returning `CASE` in `WHERE`:

~~~sql
SELECT order_id, status, subtotal
FROM expr_lab_135.orders
WHERE
    CASE
        WHEN status = 'PAID' THEN subtotal >= 100000
        WHEN status = 'NEW' THEN subtotal >= 200000
        ELSE FALSE
    END
ORDER BY order_id;
~~~

On the sample data, order `106` matches (`PAID` and high subtotal), `102` matches (`NEW` and 250,000), and `101` matches (`PAID` and 100,000). Result: **101, 102, 106**.

Yet the exact same logic is usually far clearer with plain boolean operators:

~~~sql
SELECT order_id, status, subtotal
FROM expr_lab_135.orders
WHERE
    (status = 'PAID' AND subtotal >= 100000)
    OR
    (status = 'NEW' AND subtotal >= 200000)
ORDER BY order_id;
~~~

**Do not wrap every condition in `CASE`.** Plain `AND`/`OR` in `WHERE` is easier to read and gives the query planner better opportunities for index usage and sargability. Use `CASE` when **computing a branched value**, not as a replacement for ordinary boolean logic.

### 12.1. COALESCE in WHERE Can Change Meaning

~~~sql
SELECT order_id, status
FROM expr_lab_135.orders
WHERE COALESCE(status, 'NEW') = 'NEW';
~~~

This selects **both `NEW` orders and `status IS NULL` orders** by intentionally treating missing status as NEW.

If the business only wants orders whose actual status is NEW:

~~~sql
WHERE status = 'NEW'
~~~

If both groups are genuinely desired while keeping the condition explicit:

~~~sql
WHERE status = 'NEW' OR status IS NULL
~~~

Never use `COALESCE` to paper over missing values without noticing it alters the matched row set.

## 13. Result Data Types of CASE and COALESCE

PostgreSQL must determine **a single output data type** for the expression. All `THEN`/`ELSE` branches of `CASE` and all arguments of `COALESCE` must have types that **resolve compatibly** under PostgreSQL's type-resolution rules.

### 13.1. CASE with Matching Branch Types

~~~sql
SELECT
    CASE
        WHEN TRUE THEN 100::numeric
        ELSE 0::numeric
    END AS numeric_result,
    pg_typeof(
        CASE WHEN TRUE THEN 100::numeric ELSE 0::numeric END
    ) AS result_type;
~~~

Here the output type is `numeric`.

### 13.2. Never Arbitrarily Mix Numbers and Text

~~~sql
-- Poor design:
-- SELECT CASE
--     WHEN status = 'PAID' THEN subtotal
--     ELSE 'Not paid yet'
-- END
-- FROM expr_lab_135.orders;
~~~

One branch is `NUMERIC` while the other is descriptive text. PostgreSQL may try to coerce the text to numeric and error out, or fail type resolution.

If you want a **text display label**, cast the number to text explicitly:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN subtotal::text
        ELSE 'Not paid yet'
    END AS display_value
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

If you want a **numeric value for calculations**, keep all branches numeric:

~~~sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN subtotal
        ELSE 0::numeric
    END AS paid_subtotal
FROM expr_lab_135.orders;
~~~

**Never mix monetary amounts and descriptive strings in the same column just for UI convenience** if anything downstream needs to aggregate or sort numerically.

### 13.3. COALESCE Also Requires Compatible Types

~~~sql
SELECT
    COALESCE(NULL::numeric, 0::numeric) AS amount_zero,
    COALESCE(NULL::text, 'Not available') AS text_default;
~~~

Watch out when mixing numeric columns with digit strings:

~~~sql
-- Avoid relying on unpredictable implicit casts:
-- COALESCE(total_amount, '0')

-- Express type intent clearly:
COALESCE(total_amount, 0::numeric)
~~~

The last snippet illustrates an expression used inside a query with a `numeric` column `total_amount`; do not run that line standalone without a matching column.

### 13.4. NULLIF Can Return a Promoted Type

`NULLIF` performs an equality comparison after resolving a compatible operator. Its result type is **not always identical to the first argument's original type** if PostgreSQL had to promote types for the comparison.

Example:

~~~sql
SELECT
    pg_typeof(NULLIF(1, 2)) AS integer_result_type,
    pg_typeof(NULLIF(1, 2.2)) AS promoted_result_type;
~~~

Typically `NULLIF(1, 2)` is `integer`, whereas comparing with `2.2` promotes the result to `numeric`. When passing results through JDBC, views, or API contracts, add **explicit casts** if exact output types are part of the interface.

### 13.5. Typed NULLs vs. Untyped Literal NULL

~~~sql
SELECT
    COALESCE(NULL::integer, 5) AS int_default,
    COALESCE(NULL::text, 'N/A') AS text_default,
    CASE WHEN FALSE THEN 1 ELSE NULL::integer END
        AS nullable_integer;
~~~

Writing `NULL::integer` or `NULL::text` makes the `NULL` branch's domain clear to both PostgreSQL and human readers. It also prevents type-resolution errors in `UNION`, views, functions, and prepared statements.

## 14. Limits of "Only Evaluating the Selected Branch"

`CASE` and `COALESCE` normally avoid evaluating unused branches. Still, **never treat this as an absolute guarantee that expressions in untaken branches are never touched by PostgreSQL at any stage**.

### 14.1. Conditional Division

~~~sql
SELECT
    order_id,
    CASE
        WHEN item_count = 0 THEN NULL::numeric
        ELSE subtotal / item_count
    END AS average_per_item
FROM expr_lab_135.orders;
~~~

In standard execution, PostgreSQL selects the matching branch; for order `104`, `item_count = 0`, returning `NULL` without evaluating the division branch.

A shorter, cleaner pattern for division:

~~~sql
SELECT
    order_id,
    subtotal / NULLIF(item_count, 0) AS average_per_item
FROM expr_lab_135.orders;
~~~

### 14.2. Why Not Rely on CASE to Suppress Arbitrary Expression Errors?

PostgreSQL can perform **constant folding during planning**. An invalid constant expression like `1 / 0` inside an apparently unreachable branch can still be evaluated early in certain plans.

The following **is not a safe general pattern for handling division by zero**:

~~~sql
-- Do not rely on this as a general error-suppression pattern:
-- SELECT CASE WHEN FALSE THEN 1 / 0 ELSE 0 END;
~~~

Additionally, aggregate expressions can be evaluated **before an outer `CASE` in the select list picks a branch**, so wrapping an unsafe aggregate inside `CASE` does not guarantee it won't execute.

Dangerous conceptual example:

~~~sql
-- Do not assume an outer CASE blocks a failing division
-- if aggregates evaluate before the CASE expression:
-- SELECT CASE
--          WHEN MIN(denominator) = 0 THEN 0
--          ELSE MAX(numerator / denominator)
--        END
-- FROM some_table;
~~~

The safer approach is guarding the denominator **directly inside the division expression**:

~~~sql
SELECT
    MAX(subtotal / NULLIF(item_count, 0))
        AS max_amount_per_item
FROM expr_lab_135.orders;
~~~

Division with zero denominator evaluates to `NULL`; `MAX` ignores `NULL`s. Even so, that only prevents **arithmetic errors**; business logic must still decide whether zero-item orders should be excluded from the maximum metric.

### 14.3. Do Not Rely on AND/OR Order to Guard Unsafe Arithmetic

A condition like:

~~~sql
-- Do not treat left-to-right order as a universal guarantee:
-- WHERE item_count <> 0 AND subtotal / item_count > 100000
~~~

must not be relied upon as an absolute short-circuit guard, because the optimizer may reorder boolean predicates while preserving SQL semantics. When division can encounter 0, write:

~~~sql
WHERE subtotal / NULLIF(item_count, 0) > 100000
~~~

When `item_count = 0`, dividing by `NULL` yields `NULL`, `WHERE` evaluates to UNKNOWN, and the row is cleanly excluded.

## 15. NULLIF and COALESCE in Ratio and Percentage Reports

Percentage metrics typically have the form:

\[
\text{Percentage (\%)} = \frac{\text{Matching events}}{\text{Total events}} \times 100
\]

If total events is 0, ordinary division fails.

### 15.1. Paid Order Percentage

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    100.0
        * COUNT(*) FILTER (WHERE status = 'PAID')
        / NULLIF(COUNT(*), 0)
        AS paid_percentage
FROM expr_lab_135.orders;
~~~

The sample data has 3/6 `PAID` orders, so the rate is **50%**.

Here:

- `COUNT(*)` returns 0 if the table is empty.
- `NULLIF(COUNT(*), 0)` returns `NULL` when the denominator is 0.
- `100.0` promotes the arithmetic to decimal precision, avoiding integer division truncation.

If the table is empty, `paid_percentage` returns `NULL`, signaling **no sample data to compute a rate**. If a dashboard demands `0` for empty periods, wrap with `COALESCE` and document that convention.

### 15.2. Group Percentages and Empty Groups

~~~sql
SELECT
    customer_id,
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS paid_orders,
    ROUND(
        100.0
            * COUNT(*) FILTER (WHERE status = 'PAID')
            / NULLIF(COUNT(*), 0),
        2
    ) AS paid_percent
FROM expr_lab_135.orders
GROUP BY customer_id
ORDER BY customer_id NULLS LAST;
~~~

When `GROUP BY` reads directly from the orders table, each returned group has at least one row so `COUNT(*)` is non-zero. Yet in summary queries where groups come from `LEFT JOIN` or a calendar spine with zero events, `NULLIF` keeps the general formula safe.

### 15.3. Never Average Group Percentages with Unequal Weights

Suppose Group A has 1 paid out of 1 order (100%), and Group B has 1 paid out of 9 orders (11.11%). Averaging **100%** and **11.11%** does not equal the overall rate **2/10 = 20%**. `CASE`/`NULLIF` handle conditional calculation, not choosing the right **statistical denominator**. Always define aggregation level and weights per business requirements.

## 16. COALESCE and Aggregate Functions: Order of Application Matters

PostgreSQL aggregate functions have specific `NULL`-handling rules:

- `COUNT(*)` counts rows.
- `COUNT(expression)` counts non-`NULL` values.
- `SUM(expression)` skips `NULL`s, returning `NULL` if there are zero non-`NULL` inputs.
- `AVG(expression)` skips `NULL`s.

### 16.1. SUM(COALESCE(x,0)) vs. COALESCE(SUM(x),0)

Compare:

~~~sql
SELECT
    SUM(COALESCE(discount_amount, 0))
        AS sum_with_row_defaults,
    COALESCE(SUM(discount_amount), 0)
        AS sum_with_aggregate_default
FROM expr_lab_135.orders;
~~~

On a table with at least one non-NULL value, both return **130,000** on the sample data (10,000 + 0 + 20,000 + 100,000).

Semantically, however:

- `SUM(COALESCE(x, 0))` **replaces every row's missing value with 0 before summing**.
- `COALESCE(SUM(x), 0)` **lets `SUM` ignore NULLs**, only replacing a `NULL` aggregate result with 0 if zero values were summed.

They diverge when paired with `AVG`, `COUNT`, other calculations, or when distinguishing "unknown" from "zero."

### 16.2. AVG(COALESCE(x,0)) Differs from AVG(x)

~~~sql
SELECT
    AVG(discount_amount) AS average_known_discounts,
    AVG(COALESCE(discount_amount, 0))
        AS average_with_missing_as_zero,
    COUNT(discount_amount) AS known_discount_rows,
    COUNT(*) AS all_orders
FROM expr_lab_135.orders;
~~~

The sample data has known discounts: `10000`, `0`, `20000`, `100000`. The remaining two rows have NULL discounts; there are **6 orders and 4 known discount values**.

- `AVG(discount_amount)` averages over **4 known values**: **32,500**.
- `AVG(COALESCE(discount_amount, 0))` averages over **6 orders** treating missing as 0: roughly **21,666.67**.

Either formula can be valid depending on the question, yet **never silently replace missing values with 0 and present the result as the average of observed values**.

### 16.3. "No Data" Metrics vs. "Actually Zero" Metrics

Example of a reporting period with zero orders:

~~~sql
SELECT
    SUM(subtotal) AS no_rows_sum,
    COALESCE(SUM(subtotal), 0) AS zero_for_display,
    COUNT(*) AS no_rows_count
FROM expr_lab_135.orders
WHERE order_id < 0;
~~~

`SUM(subtotal)` returns `NULL` for zero rows, `COALESCE(SUM(...), 0)` returns 0, and `COUNT(*)` returns 0. Decide carefully whether displaying "0 revenue" is appropriate when there was simply "no data in the period."

## 17. CASE in UPDATE Statements

These three expressions are not limited to read queries. `CASE` can compute updated values in `UPDATE`:

~~~sql
-- Practice example inside a transaction; ROLLBACK preserves initial seed data.
BEGIN;

UPDATE expr_lab_135.orders
SET status = CASE
    WHEN status IS NULL THEN 'NEW'
    ELSE status
END
WHERE status IS NULL;

SELECT order_id, status
FROM expr_lab_135.orders
WHERE order_id = 104;
-- NEW inside this transaction.

ROLLBACK;
~~~

When simply backfilling `NULL` with a default, `COALESCE` is shorter:

~~~sql
BEGIN;

UPDATE expr_lab_135.orders
SET status = COALESCE(status, 'NEW')
WHERE status IS NULL;

ROLLBACK;
~~~

Still, **bulk data-cleaning updates should never run automatically** just because the SQL is short. `status IS NULL` might reflect a sync bug, pending review, or unconfirmed state rather than `NEW`.

### 17.1. Normalizing Strings on Write

~~~sql
BEGIN;

UPDATE expr_lab_135.customers
SET phone = NULLIF(btrim(phone), '')
WHERE phone IS NOT NULL;

ROLLBACK;
~~~

Once business rules confirm blank strings mean missing data, enforce that rule at the ingestion/application layer or via controlled migrations. Never run lossy data cleanups without backups and testing.

### 17.2. CASE/COALESCE in UPSERT

PostgreSQL supports `INSERT ... ON CONFLICT DO UPDATE`. During a sync, you might use `COALESCE` to preserve the existing value if the incoming field is `NULL`:

~~~sql
-- Illustrative idea, assuming customer_id=1 exists:
BEGIN;

INSERT INTO expr_lab_135.customers
    (customer_id, full_name, email, phone, loyalty_tier)
VALUES
    (1, 'Nguyễn An', 'an@example.test', NULL, NULL)
ON CONFLICT (customer_id) DO UPDATE
SET
    phone = COALESCE(
        EXCLUDED.phone,
        expr_lab_135.customers.phone
    );

ROLLBACK;
~~~

Here `EXCLUDED.phone` is the incoming value from the attempted insert. When it is `NULL`, the statement keeps the existing `phone`. **This is a specific update convention**: you cannot use it if an incoming `NULL` means **the user wants to clear their phone number**. APIs should distinguish "field omitted" from "field explicitly set to null to clear" when business rules require it.

## 18. CASE, COALESCE, and NULLIF in Views

A view can encapsulate common display expressions so applications do not duplicate logic:

~~~sql
CREATE VIEW expr_lab_135.v_order_display AS
SELECT
    o.order_id,
    o.ordered_at,
    COALESCE(c.full_name, 'Guest customer')
        AS customer_display_name,
    CASE
        WHEN o.status IS NULL THEN 'Not entered'
        WHEN o.status = 'PAID' THEN 'Paid'
        WHEN o.status = 'NEW' THEN 'In progress'
        WHEN o.status = 'CANCELLED' THEN 'Cancelled'
        ELSE 'Other'
    END AS status_label,
    COALESCE(
        NULLIF(btrim(o.customer_note), ''),
        'No note'
    ) AS customer_note_display,
    o.subtotal
        - COALESCE(o.discount_amount, 0)
        + COALESCE(o.shipping_fee, 0)
        AS estimated_payable
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Querying the view:

~~~sql
SELECT *
FROM expr_lab_135.v_order_display
ORDER BY order_id;
~~~

**A view does not turn an assumption into ground truth.** If shipping fees are still pending calculation, the view above still assumes 0. Before sharing a view in production, align on field names, `NULL` conventions, currency rules, and migration ownership.

### 18.1. When Reporting Rules Change

Suppose later you need to separate `UNKNOWN` from `NEW`. Because `CASE` inside the view is shared logic, altering the view can impact multiple clients. Manage changes through versioned migrations and compatibility checks rather than editing production views ad hoc.

## 19. CASE in SELECT and Conditional Monetary Calculations

Example computing a fee tier from order value:

~~~sql
SELECT
    order_id,
    subtotal,
    CASE
        WHEN subtotal >= 500000 THEN 0::numeric
        WHEN subtotal >= 200000 THEN 15000::numeric
        ELSE 30000::numeric
    END AS proposed_shipping_fee
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

All branches share type `numeric`, making downstream monetary addition clean. This is an **illustrative rate schedule**; it does not replace negotiated shipping fees, address-based quotes, or accounting records.

### 19.1. CASE for Isolating Data Quality Anomalies

~~~sql
SELECT
    order_id,
    status,
    paid_at,
    CASE
        WHEN status = 'PAID' AND paid_at IS NULL
            THEN 'Anomaly: paid without timestamp'
        WHEN status <> 'PAID' AND paid_at IS NOT NULL
            THEN 'Check status and timestamp'
        WHEN status IS NULL
            THEN 'Missing status'
        ELSE 'No issue detected by sample rules'
    END AS data_quality_note
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

When `status IS NULL` and `paid_at IS NOT NULL`, `status <> 'PAID'` is UNKNOWN rather than TRUE, so the subsequent `status IS NULL` branch catches it. To flag every unexpected combination accurately, add explicit branches for each anomalous state.

## 20. Performance and Index Usability

`CASE`, `COALESCE`, and `NULLIF` are convenient, yet wrapping a **filtered column** in an expression can alter the query plan compared to comparing the raw column.

### 20.1. Filtering Raw Columns vs. Expressions

Suppose an index exists:

~~~sql
CREATE INDEX idx_orders_status_135
ON expr_lab_135.orders(status);
~~~

Two queries with different semantics:

~~~sql
-- Selects only status PAID:
SELECT *
FROM expr_lab_135.orders
WHERE status = 'PAID';
~~~

~~~sql
-- Selects status PAID or NULL when convention equates NULL with PAID:
SELECT *
FROM expr_lab_135.orders
WHERE COALESCE(status, 'PAID') = 'PAID';
~~~

The second query wraps `status` in a function/expression. A plain B-tree index on `status` **is not guaranteed** to be used the same way as in the first query. When you want to include NULLs, write:

~~~sql
WHERE status = 'PAID' OR status IS NULL
~~~

or consider an **expression index** when the expression and workload genuinely warrant it—always weighing statistics, row count, and write overhead.

### 20.2. Expression Indexes Can Be Useful

For example, a system looking up normalized phone numbers:

~~~sql
-- Study example; also consider storing normalized values directly.
CREATE INDEX idx_customers_clean_phone_135
ON expr_lab_135.customers (
    NULLIF(btrim(phone), '')
);
~~~

An expression index can support queries using that matching expression:

~~~sql
SELECT customer_id, full_name
FROM expr_lab_135.customers
WHERE NULLIF(btrim(phone), '') = '0901111111';
~~~

On a four-row table, PostgreSQL will likely choose a sequential scan because it is cheaper even with an index. **An index existing does not force the planner to use it.** On large datasets, measure actual impact with `EXPLAIN (ANALYZE, BUFFERS)` in a safe environment.

### 20.3. Consider Write-Time Normalization Before Creating Expression Indexes

If every query has to apply `btrim`/`NULLIF`/`lower` on a column to search it, it is often cleaner to **clean the data on write** or maintain a dedicated normalized column. Expression indexes help certain workloads, yet add index-update overhead and cannot fix underlying source-data inconsistencies.

### 20.4. CASE Does Not Automatically Speed Up JOINs

~~~sql
SELECT
    o.order_id,
    COALESCE(c.full_name, 'Guest')
FROM expr_lab_135.orders AS o
LEFT JOIN expr_lab_135.customers AS c
    ON c.customer_id = o.customer_id;
~~~

`COALESCE` only sets the displayed value. Join strategy, key indexes, and row counts remain the primary performance drivers. Never put `CASE` inside a `JOIN` condition to "patch" broken foreign keys when the real fix is repairing link data.

## 21. Common Mistakes

| Mistake / Misconception | Problem | Better Approach |
| --- | --- | --- |
| `CASE WHEN col = NULL` | `= NULL` is never TRUE | `WHEN col IS NULL` |
| `CASE col WHEN NULL` | Simple CASE does not match NULL as expected | Searched CASE with `IS NULL` |
| Omitting `ELSE` while expecting `0` | Unmatched rows return `NULL` | Add `ELSE 0` intentionally |
| Putting `WHEN amount >= 100` before `>= 500` | Broad branch shadows narrower branch | Order branches by precedence |
| Thinking `COALESCE(0, 100)` returns 100 | `0` is not `NULL` | Actual result is `0` |
| Thinking `COALESCE('', 'N/A')` returns `'N/A'` | Empty string is not `NULL` in PostgreSQL | `COALESCE(NULLIF(value,''), 'N/A')` |
| Using `COALESCE(amount, 0)` everywhere | Hides unknown monetary values | Align on NULL semantics |
| Treating `NULLIF(a,b)` as a boolean check | Returns `a` or `NULL` | Use `=` or `IS [NOT] DISTINCT FROM` |
| Writing `100 / 0` guarded only by arbitrary `CASE` | Division by zero can still occur in some plans | Guard denominator with `NULLIF(denominator,0)` |
| `COUNT(CASE WHEN cond THEN 1 ELSE 0 END)` | `COUNT` counts `0` too | `SUM(CASE... ELSE 0 END)` or `COUNT(*) FILTER` |
| `AVG(COALESCE(value,0))` when wanting average of known values | Skews the statistical denominator | Use `AVG(value)` to skip NULLs |
| Mixing `numeric` and `text` in `CASE` | Cast failure or ambiguous contract | Pick one consistent output type |
| Thinking `NULLIF(phone,'')` handles spaces | `'   '` does not equal `''` | `NULLIF(btrim(phone), '')` with clear policy |
| Using `CASE` for every `WHERE` condition | Verbose and harder to optimize | Use direct boolean operators when appropriate |
| Assuming `CASE` guarantees unselected branches are never evaluated | Constant folding / aggregates have exceptions | Make the calculation itself safe |
| Folding `NULL` into a real status silently | Distorts reports and classifications | Use clear labels/rules and verify |
| Putting text labels inside a monetary `CASE` column | Breaks numeric aggregation and sorting | Keep `numeric`; put labels in a separate column |

## 22. Practice Exercises

### Exercise 1 — Mapping Statuses with CASE

Write a query returning `order_id`, `status`, and a label:

- `PAID` → "Paid".
- `NEW` → "Pending".
- `CANCELLED` → "Cancelled".
- `NULL` → "Not entered".
- Other values → "Unknown".

**Hint:** use searched CASE with an explicit `WHEN status IS NULL`.

~~~sql
SELECT
    order_id,
    CASE
        WHEN status IS NULL THEN 'Not entered'
        WHEN status = 'PAID' THEN 'Paid'
        WHEN status = 'NEW' THEN 'Pending'
        WHEN status = 'CANCELLED' THEN 'Cancelled'
        ELSE 'Unknown'
    END AS label
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

### Exercise 2 — Bucketing by Amount

Use `CASE` to classify `subtotal`:

- 500,000 or more: `HIGH`.
- 100,000 to below 500,000: `MEDIUM`.
- Below 100,000: `LOW`.

**Question:** if `>= 100000` is placed before `>= 500000`, which bucket does order `106` fall into, and why?

### Exercise 3 — Calculating Totals with COALESCE

Compute `subtotal - discount_amount + shipping_fee`, substituting 0 for `NULL` in both secondary amounts. For order `101`, the result must be **90,000**. For order `102`, the result is **265,000**.

**Follow-up question:** in a real payment system, why must you confirm whether a `NULL` `shipping_fee` can truly be treated as 0?

### Exercise 4 — Cleaning Phone Numbers

Write a query performing:

~~~text
raw phone -> btrim -> NULLIF(...,'') -> COALESCE(...,'Not provided')
~~~

For customers `3` and `4`, the final label must be **Not provided**. Explain why `COALESCE(phone, ...)` alone is insufficient.

### Exercise 5 — Division by Zero

Return the average `subtotal / item_count` per order. When `item_count = 0`, return `NULL` instead of raising an error. Use:

~~~sql
SELECT
    order_id,
    subtotal / NULLIF(item_count, 0) AS per_item
FROM expr_lab_135.orders
ORDER BY order_id;
~~~

**Question:** why can replacing `NULL` with `0` in `per_item` distort statistical meaning?

### Exercise 6 — Counting Statuses Properly

Compare three expressions:

~~~sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END)
        AS count_by_case,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS sum_by_case,
    COUNT(*) FILTER (WHERE status = 'PAID')
        AS count_by_filter
FROM expr_lab_135.orders;
~~~

All three must return **3**. Then analyze why `COUNT(CASE ... ELSE 0 END)` returns **6**.

### Exercise 7 — Average Discount With and Without COALESCE

Compute `AVG(discount_amount)` and `AVG(COALESCE(discount_amount, 0))`. Explain the difference in denominators, missing-data row counts, and why you should not pick a formula merely because the output looks "cleaner."

### Exercise 8 — Custom Priority Ordering

Write `ORDER BY CASE` to sort `NEW` before `PAID`, then `CANCELLED`, and finally `NULL`. Break ties within the same group by `ordered_at DESC`.

### Exercise 9 — Classifying payment_state

Return:

- `PAID` with `paid_at` → "Valid".
- `PAID` with `paid_at IS NULL` → "Missing payment timestamp".
- `status IS NULL` → "Missing status".
- All others → "Needs payment/reconciliation".

**Hint:** combine `IS NULL` and `AND` in a searched CASE. If using `status <> 'PAID'`, remember that `NULL` yields UNKNOWN.

### Exercise 10 — CASE in Grouped Reports

Bucket orders into `HIGH`/`MEDIUM`/`LOW` as in Exercise 2, returning:

~~~text
order_band | number_of_orders | subtotal_sum | paid_order_count
~~~

Use a CTE to compute `order_band` and then `GROUP BY`; use `COUNT(*) FILTER (WHERE status='PAID')` or `SUM(CASE...)` for paid order counts.

### Exercise 11 — NULL and Comparisons

Run:

~~~sql
SELECT
    NULL::integer = NULL::integer AS eq_null,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS null_safe_equal,
    NULLIF(0, 0) AS nullified_zero,
    COALESCE(NULLIF(0, 0), 99) AS fallback_after_nullif;
~~~

Explain why `eq_null` is `NULL`, `null_safe_equal` is `TRUE`, `nullified_zero` is `NULL`, and the final expression is `99`.

### Exercise 12 — Spot the Bugs in a Report Query

The following snippet contains multiple issues:

~~~sql
-- Buggy sample for analysis; do not use in production reports:
SELECT
    COUNT(
        CASE WHEN status = 'PAID' THEN 1 ELSE 0 END
    ) AS paid_orders,
    AVG(COALESCE(discount_amount, 0)) AS avg_discount,
    COALESCE(customer_note, 'No note')
        AS note_display
FROM expr_lab_135.orders
GROUP BY customer_note;
~~~

Identify:

1. Why `paid_orders` miscounts PAID orders.
2. When `AVG(COALESCE(discount_amount, 0))` is valid versus misleading.
3. Why `customer_note = ''` or `'   '` is not replaced by the label.
4. Why grouping by the raw `customer_note` can create multiple groups that look identical in the UI.

### Exercise 13 — Designing NULL Conventions in an API

An API returns:

~~~text
discount_amount
shipping_fee
payment_ratio
customer_phone
~~~

Create a table specifying whether `NULL` for each field means "none", "unknown", or "not applicable." Then decide when to:

- Keep `NULL` as-is.
- Use `COALESCE` for display.
- Use `NULLIF` to normalize input.
- Use `CASE` to build detailed user-facing labels.

Crucially, **do not apply one uniform rule to every column**, especially across monetary fields and ratios.

## 23. From Simple Queries to Application Code

When building a conditional query, follow this sequence:

1. **Inspect raw data** with `SELECT` to spot `NULL`s, empty strings, and sentinels.
2. **Write short expressions and test piece by piece**: `NULLIF(btrim(...),'')`, `COALESCE(...,...)`, `CASE...END`.
3. **Choose explicit output types**: `numeric` for money and ratios, `text` for labels.
4. **Test edge cases**: zero rows, all `NULL`s, zero denominators, negative values, and new statuses.
5. **Place expressions appropriately**: `SELECT` for presentation, `GROUP BY` for bucketing, `FILTER`/`CASE` for conditional aggregation, `WHERE` for filtering.
6. **Evaluate performance impact** if expressions wrap columns used in filters or joins on large tables.
7. **Document conventions in migrations/specs** when queries back shared views or official business logic.

Final integrated query example:

~~~sql
WITH normalized AS (
    SELECT
        o.order_id,
        o.status,
        o.subtotal,
        o.item_count,
        COALESCE(c.full_name, 'Guest customer')
            AS customer_label,
        COALESCE(
            NULLIF(btrim(o.customer_note), ''),
            'No note'
        ) AS note_label,
        o.subtotal
            - COALESCE(o.discount_amount, 0)
            + COALESCE(o.shipping_fee, 0)
            AS estimated_payable
    FROM expr_lab_135.orders AS o
    LEFT JOIN expr_lab_135.customers AS c
        ON c.customer_id = o.customer_id
)
SELECT
    order_id,
    customer_label,
    CASE
        WHEN status = 'PAID' THEN 'Paid'
        WHEN status = 'NEW' THEN 'New'
        WHEN status = 'CANCELLED' THEN 'Cancelled'
        WHEN status IS NULL THEN 'No status yet'
        ELSE 'Other'
    END AS status_label,
    note_label,
    estimated_payable,
    CASE
        WHEN item_count = 0 THEN NULL::numeric
        ELSE estimated_payable / NULLIF(item_count, 0)
    END AS payable_per_item
FROM normalized
ORDER BY order_id;
~~~

This query uses all three expressions while separating layers with a CTE for readability. `payable_per_item` for order 104 is `NULL` since it has zero items; other orders compute using the lesson's monetary convention. Layering queries aids testing and maintenance, though it **does not guarantee PostgreSQL always materializes the CTE or runs faster**; the planner can inline or optimize CTEs depending on version and query shape.

## 24. PostgreSQL Documentation References

To check syntax and expression-resolution rules for your PostgreSQL version:

- [Conditional Expressions — CASE, COALESCE, NULLIF](https://www.postgresql.org/docs/current/functions-conditional.html): syntax, branch evaluation, and evaluation caveats.
- [Comparison Functions and Operators](https://www.postgresql.org/docs/current/functions-comparison.html): comparisons with `NULL`, `IS NULL`, and `IS DISTINCT FROM`.
- [Type Conversion — UNION, CASE, and Related Constructs](https://www.postgresql.org/docs/current/typeconv-union-case.html): how PostgreSQL resolves common output types for `CASE` and related constructs.
- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html): `COUNT`, `SUM`, `AVG`, and their `NULL` behavior.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): using expressions in `WHERE`, `GROUP BY`, `HAVING`, and `ORDER BY`.

`/docs/current/` links point to the latest stable documentation. When targeting a specific major version, consult the documentation matching your deployed server.

## 25. Summary

**`CASE` produces values via conditional branching**: searched CASE handles arbitrary boolean predicates, while simple CASE maps one expression against equality values. `WHEN` order dictates which branch wins, and `UNKNOWN` from `NULL` never counts as TRUE. When no branch matches, the result is `ELSE`, or `NULL` if `ELSE` is omitted.

**`COALESCE` returns the first non-`NULL` value.** It is useful for fallback display labels or calculation defaults, yet does not treat **`0`**, **`FALSE`**, or **empty strings** as missing. **`NULLIF` returns `NULL` when two expressions are equal**, making it ideal for converting sentinel strings to `NULL` and guarding division denominators with `NULLIF(denominator, 0)`.

Combining these three expressions lets you write clearer queries, compute conditional metrics, and present missing data intentionally. What matters most is **understanding `NULL` semantics, picking consistent output types, testing edge cases, and never masking unknown data behind arbitrary defaults**. With these habits, `CASE`, `COALESCE`, and `NULLIF` become foundational tools for readable, reliable PostgreSQL queries.
