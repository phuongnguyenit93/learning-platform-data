# Expression Indexes and Function Requirements in PostgreSQL

In PostgreSQL applications, not every query filters on the raw value of a column. An authentication service searches emails **case-insensitively**; an order system filters line items by **line total = unit price × quantity**; an event pipeline queries a field nested inside `jsonb`. When predicates are written as `lower(email)`, `unit_price * quantity`, or `payload ->> 'customer_id'`, a plain B-tree on the raw column does not automatically let PostgreSQL search by that computed expression.

An **expression index** (or *functional index*) stores **values computed from columns** inside an index. Instead of indexing only `email`, you can index **`lower(email)`**; instead of indexing `unit_price` and `quantity` separately, you can index **`(unit_price * quantity)`**.

However, PostgreSQL enforces a fundamental requirement: **all functions and operators used to compute index keys must satisfy appropriate immutability (`IMMUTABLE`)**. An expression depending on the current clock, session timezone, data in another table, mutable configuration, or any `STABLE`/`VOLATILE` function cannot be stored as a standard index key.

This lesson explains how to **create**, **query**, and **maintain** expression indexes, with special focus on function correctness rather than query speed alone.

## 1. Objectives

After completing this lesson, you will be able to:

1. Distinguish plain column indexes from indexes on **expressions computed from one or more columns**.
2. Write `CREATE INDEX ... ON table (lower(column))` and `CREATE INDEX ... ON table ((a * b))` with valid syntax.
3. Use expression indexes to accelerate filtering, sorting, and uniqueness enforcement on normalized values.
4. Understand PostgreSQL's three volatility categories accurately: **`IMMUTABLE`, `STABLE`, and `VOLATILE`**.
5. Recognize why `now()`, `random()`, or certain `timestamptz`-to-date conversions cannot be used directly as index keys.
6. Inspect actual volatility in `pg_proc` by **function signature**, not just function name.
7. Write custom SQL functions marked `IMMUTABLE` responsibly, understanding the consequences of lying about volatility or changing function logic.
8. Use **partial expression indexes**, **unique expression indexes**, and choose between expression indexes and generated/regular columns.
9. Read `EXPLAIN` and system catalogs to verify whether an index is valid and used.
10. Understand `INSERT`/`UPDATE` overhead, HOT update impact, collations/timezones, `REINDEX`, and concurrent deployment.

## 2. Mental Model: The Index Stores the “Result” of the Expression

A standard B-tree index:

~~~sql
CREATE INDEX idx_users_email ON users (email);
~~~

conceptually stores keys derived from raw `email`:

~~~text
Index key                 Row reference
---------------------------------------
Anh@Example.com          → user 1
binh@example.com         → user 2
chi@example.org          → user 3
~~~

An expression index:

~~~sql
CREATE INDEX idx_users_lower_email
ON users (lower(email));
~~~

stores the computed result:

~~~text
Index key                 Row reference
---------------------------------------
anh@example.com          → user 1
binh@example.com         → user 2
chi@example.org          → user 3
~~~

When querying:

~~~sql
SELECT *
FROM users
WHERE lower(email) = 'anh@example.com';
~~~

PostgreSQL can look up `anh@example.com` directly in the expression index instead of computing `lower(email)` on every row in a sequential scan.

~~~mermaid
flowchart TD
    A["INSERT / UPDATE row"] --> B["Evaluate lower(email)"]
    B --> C["Write expression value into index"]
    D["SELECT ... WHERE lower(email) = ?"] --> E["Planner inspects expression and stats"]
    E --> F{"Is index beneficial?"}
    F -->|Yes| G["Index Scan / Bitmap Index Scan"]
    F -->|No| H["Sequential Scan"]
    G --> I["Return matching rows"]
    H --> I
~~~

**The trade-off:** the expression result is computed and maintained **at write time**, allowing reads to avoid recomputing it across every row. Indexes are not free: they consume disk, add write overhead, and must remain consistent with function logic.

### 2.1. When Do You Need an Expression Index?

Common scenarios:

| Business Condition | Candidate Index Expression |
| --- | --- |
| Case-insensitive email lookup | `lower(email)` |
| Trimmed and case-folded email | `lower(btrim(email))` |
| Case-insensitive name search | `lower(display_name)` |
| Order line total | `(unit_price * quantity)` |
| Customer ID extracted from JSONB | `(payload ->> 'customer_id')` |
| Absolute balance | `abs(balance)` when semantically right |
| Date from a **timezone-naive** timestamp | `created_local::date` or `date_trunc('day', created_local)` with matching overload |

Do not create an expression index simply because a function appears in `WHERE`. Weigh row counts, selectivity, query frequency, write overhead, and whether the query can be rewritten to use a raw column index.

## 3. Practice Dataset

Examples use schema `expr_idx_256` inside a **dedicated lab database**. If the schema already exists, choose another name instead of wiping prior data.

### 3.1. Customers Table

~~~sql
CREATE SCHEMA expr_idx_256;

CREATE TABLE expr_idx_256.customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO expr_idx_256.customers
    (customer_id, email, display_name, deleted_at)
VALUES
    (1, 'Anh@Example.com',     'Anh Nguyễn', NULL),
    (2, 'binh@example.com',    'Bình Lê',    NULL),
    (3, 'CHI@sample.org',      'Chi Phạm',   NULL),
    (4, 'duong@example.com',   'Dương Trần', NULL),
    (5, 'user@legacy.test',    'Legacy account',
        TIMESTAMPTZ '2026-01-01 00:00:00+07'),
    (6, 'old@EXAMPLE.com',     'Deleted',
        TIMESTAMPTZ '2026-02-01 00:00:00+07');
~~~

Here `deleted_at IS NULL` indicates an active account; non-NULL values mark soft-deleted rows.

### 3.2. Order Lines Table

~~~sql
CREATE TABLE expr_idx_256.order_lines (
    line_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    quantity INTEGER NOT NULL
        CHECK (quantity > 0),
    created_local TIMESTAMP WITHOUT TIME ZONE NOT NULL
);

INSERT INTO expr_idx_256.order_lines
    (line_id, order_id, sku, unit_price, quantity, created_local)
VALUES
    (1, 1001, 'BOOK-01', 100000, 1,
        TIMESTAMP '2026-11-12 09:10:00'),
    (2, 1001, 'PEN-01',   10000, 4,
        TIMESTAMP '2026-11-12 09:10:00'),
    (3, 1002, 'MOUSE-01', 250000, 2,
        TIMESTAMP '2026-11-13 16:20:00'),
    (4, 1003, 'BOOK-01', 100000, 3,
        TIMESTAMP '2026-11-14 08:00:00'),
    (5, 1004, 'BAG-01',  450000, 1,
        TIMESTAMP '2026-11-14 09:30:00'),
    (6, 1005, 'CABLE-01', 90000, 2,
        TIMESTAMP '2026-11-14 10:15:00');
~~~

`created_local` is named explicitly as a reminder that it is a **timestamp without time zone**. Avoid using that type for business timestamps representing global instants; in distributed systems, `timestamptz` is generally more appropriate for unambiguous points in time.

### 3.3. JSONB Events Table

~~~sql
CREATE TABLE expr_idx_256.events (
    event_id BIGINT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

INSERT INTO expr_idx_256.events
    (event_id, event_type, payload, occurred_at)
VALUES
    (1, 'purchase',
        '{"customer_id":"1","channel":"web"}'::jsonb,
        TIMESTAMPTZ '2026-11-12 09:00:00+07'),
    (2, 'login',
        '{"customer_id":"2","channel":"mobile"}'::jsonb,
        TIMESTAMPTZ '2026-11-13 09:00:00+07'),
    (3, 'purchase',
        '{"customer_id":"1","channel":"mobile"}'::jsonb,
        TIMESTAMPTZ '2026-11-14 08:00:00+07'),
    (4, 'logout',
        '{"customer_id":"3","channel":"web"}'::jsonb,
        TIMESTAMPTZ '2026-11-14 08:30:00+07');
~~~

### 3.4. Note on Sample Table Size

These lab tables have only a few rows so learners can verify outputs easily. PostgreSQL will likely prefer **`Seq Scan`** because reading one heap page is cheaper than an index plus heap fetch, even with a valid index. **Seeing `Seq Scan` in `EXPLAIN` on a tiny table does not mean the expression index is broken.**

## 4. Basic Example: Index on lower(email)

### 4.1. Querying Without an Expression Index

~~~sql
SELECT
    customer_id,
    email,
    display_name
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

Returns customer `customer_id = 1`.

If there is only a regular B-tree index on `email`, a query filtering on `lower(email)` **will not automatically** use that index to search by lowercased keys. The indexed column and the predicate expression differ.

### 4.2. Creating the Expression Index

~~~sql
CREATE INDEX idx_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

In PostgreSQL syntax, an expression that is a **function call** like `lower(email)` can sit directly inside the index key list without an extra set of parentheses. More complex expressions generally require outer parentheses around the expression.

### 4.3. Query Matching the Index Expression

~~~sql
SELECT
    customer_id,
    email
FROM expr_idx_256.customers
WHERE lower(email) = lower('ANH@EXAMPLE.COM');
~~~

PostgreSQL can use `idx_customers_lower_email_256`. The right-hand side folds from a constant; the left-hand expression matches the indexed key.

### 4.4. Using EXPLAIN

~~~sql
EXPLAIN
SELECT customer_id, email
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

On a tiny table, the plan will likely still be `Seq Scan`. To inspect the index plan shape in a **lab environment**, you can temporarily discourage sequential scans inside a transaction:

~~~sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN
SELECT customer_id, email
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';

ROLLBACK;
~~~

**This is strictly a planner demonstration.** `enable_seqscan = off` does not ban all sequential scans and **must never be used as “production tuning”**; it distorts normal cost selection.

### 4.5. The Query Must Express a Compatible Condition

An index:

~~~sql
ON expr_idx_256.customers (lower(email))
~~~

matches:

~~~sql
WHERE lower(email) = 'anh@example.com'
~~~

yet do not assume it identically accelerates:

~~~sql
WHERE email = 'anh@example.com'
~~~

or:

~~~sql
WHERE email ILIKE 'anh@example.com'
~~~

The planner is not obligated to prove **every seemingly equivalent logical rewrite** and map it onto `lower(email)`. In particular, `ILIKE` is a pattern-matching operator with distinct semantics, not `lower(email)` equality. If your API searches by normalized email, align **the query expression** with **the index expression**.

## 5. Arithmetic Expressions: Index on (unit_price * quantity)

### 5.1. Why Two Separate Indexes Don't Replace the Expression

Suppose queries frequently filter order lines with a large total:

~~~sql
SELECT
    line_id,
    order_id,
    sku,
    unit_price,
    quantity,
    unit_price * quantity AS line_total
FROM expr_idx_256.order_lines
WHERE unit_price * quantity >= 300000
ORDER BY line_id;
~~~

Expected output:

| line_id | SKU | Line total |
| ---: | --- | ---: |
| 3 | MOUSE-01 | 500.000 |
| 4 | BOOK-01 | 300.000 |
| 5 | BAG-01 | 450.000 |

Separate indexes on `unit_price` and `quantity` do not store **the product of the two columns** for threshold lookups like `>= 300000`.

### 5.2. Creating an Expression Index with Double Parentheses

~~~sql
CREATE INDEX idx_order_lines_total_256
ON expr_idx_256.order_lines ((unit_price * quantity));
~~~

**The double parentheses `((...))`** come from two layers:

- Outer parentheses belong to the key list syntax `ON table (...)`.
- Inner parentheses wrap the **arithmetic expression** `(unit_price * quantity)`.

~~~text
ON order_lines ( (unit_price * quantity) )
               ^ ^                   ^ ^
               | +--- expression ----+ |
               +----- index keys ------+
~~~

### 5.3. Range Conditions and ORDER BY

~~~sql
SELECT line_id, unit_price * quantity AS line_total
FROM expr_idx_256.order_lines
WHERE unit_price * quantity >= 300000
ORDER BY unit_price * quantity, line_id;
~~~

A B-tree expression index supports range predicates on the expression key and can supply sorted order for the expression itself in compatible plans. Appending `line_id` as a tie-breaker in `ORDER BY` may still trigger sorting if `line_id` is not part of the index key order.

**Never assume** this index helps queries filtering solely on `unit_price > 100000`. The indexed key is the **product**, not the raw unit price.

### 5.4. Limitations

- `unit_price` and `quantity` must use types whose multiplication operator is eligible for expression indexing.
- `numeric` preserves exact decimal multiplication rules; with `double precision`, watch out for floating-point rounding in financial logic.
- Arithmetic in an expression index may only reference columns of the **current row** via eligible functions and operators—never a subquery reading another table.

## 6. Expression Indexes Can Combine Multiple Keys and INCLUDE

Example filtering by event type and customer ID extracted from JSON:

~~~sql
CREATE INDEX idx_events_type_customer_256
ON expr_idx_256.events (
    event_type,
    (payload ->> 'customer_id')
);
~~~

`payload ->> 'customer_id'` returns `text`. The index has two ordered keys:

1. `event_type` (plain column);
2. `payload ->> 'customer_id'` (expression).

Matching query:

~~~sql
SELECT event_id, occurred_at
FROM expr_idx_256.events
WHERE event_type = 'purchase'
  AND payload ->> 'customer_id' = '1';
~~~

Returns event IDs **1** and **3**.

### 6.1. Composite Indexes Still Care About Column Order

A B-tree on `(event_type, expression)` shines when queries filter `event_type` first or filter both keys. It does not offer the same narrow range lookup as a standalone expression index when queries filter **only** on `payload ->> 'customer_id'`; PostgreSQL may use another plan or scan depending on stats and version.

### 6.2. INCLUDE vs. Key Columns

When many queries also select `event_id`:

~~~sql
CREATE INDEX idx_events_customer_cover_256
ON expr_idx_256.events (
    (payload ->> 'customer_id')
)
INCLUDE (event_id);
~~~

`event_id` is an **`INCLUDE` payload column**—it does not participate in B-tree ordering or uniqueness checks. An index with `INCLUDE` can enable index-only scans when the visibility map and planner agree.

Avoid adding wide columns to `INCLUDE` indiscriminately: it bloats the index, raises write cost, and risks hitting tuple size limits.

## 7. Core Requirement: Functions in Expressions Must Be IMMUTABLE

PostgreSQL classifies function volatility into three categories:

| Volatility | Meaning | Common Examples | Allowed Directly in Expression Index Keys? |
| --- | --- | --- | --- |
| **`IMMUTABLE`** | Same inputs always return the same result under system assumptions; depends on no mutable state | `lower(text)`, pure arithmetic operators | **Yes**, if the full expression is eligible |
| **`STABLE`** | Within one SQL statement, same inputs return the same result; can differ across statements as environment changes | `now()` / `transaction_timestamp()`, timezone-dependent overloads | **No** |
| **`VOLATILE`** | Can return different values even across repeated calls with identical arguments, or have side effects | `random()`, `clock_timestamp()` | **No** |

When an index stores a computed function result, PostgreSQL must assume **the result never changes unless the row's columns change**. Otherwise, the index would silently hold stale keys.

### 7.1. Example of Why STABLE Is Not Enough

Suppose someone tries to index “orders created today”:

~~~sql
-- INVALID example:
-- CREATE INDEX idx_today
-- ON orders ((created_at::date = current_date));
~~~

`current_date` changes after midnight (and depends on session timezone). A row created “today” becomes “yesterday” **without any `UPDATE` on the row**; PostgreSQL would have no way to update stored index keys at midnight.

Instead, index the timestamp column and compute boundaries **at query time**:

~~~sql
CREATE INDEX idx_events_occurred_at_256
ON expr_idx_256.events (occurred_at);

SELECT event_id
FROM expr_idx_256.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
~~~

For dynamic “today” filters, the application or query computes `[start, end)` bounds in the business timezone, allowing PostgreSQL to use the B-tree on `occurred_at`. **You never need an index on “today”**—a time-varying concept.

### 7.2. IMMUTABLE Is a Correctness Promise, Not a Speed Flag

Marking a function `IMMUTABLE` **does not make it truly immutable**. PostgreSQL trusts the author's declaration when optimizing and indexing. If you lie, index lookups and cached plans can return wrong results; PostgreSQL does not always catch hidden violations inside function bodies.

### 7.3. Operators Are Also Functions Under the Hood

The expression:

~~~sql
unit_price * quantity
~~~

uses the multiplication operator. In the system catalogs, operators resolve to underlying implementation functions. **Not only explicit `some_function(...)` calls must satisfy volatility rules**; operators in the expression must also be `IMMUTABLE`.

### 7.4. Partial Index Predicates Must Also Be Immutable

This applies not only to expression index **keys**: a **partial index predicate** (the `WHERE` clause in `CREATE INDEX`) must likewise contain only `IMMUTABLE` functions and operators.

Example:

~~~sql
-- INVALID because now() is not IMMUTABLE:
-- CREATE INDEX idx_recent_orders
-- ON orders (created_at)
-- WHERE created_at >= now() - INTERVAL '7 days';
~~~

Even though the index key `created_at` is a plain column, the **predicate** changes truth value as time passes without any row writes, so it cannot be stored in a partial index.

## 8. Inspecting Volatility in pg_proc

Never guess from a function name alone. PostgreSQL records volatility in the system catalog **`pg_proc.provolatile`**.

~~~sql
SELECT
    n.nspname AS function_schema,
    p.proname AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS argument_types,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility,
    CASE p.proparallel
        WHEN 's' THEN 'PARALLEL SAFE'
        WHEN 'r' THEN 'PARALLEL RESTRICTED'
        WHEN 'u' THEN 'PARALLEL UNSAFE'
    END AS parallel_safety
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'pg_catalog'
  AND p.proname IN (
      'lower',
      'date_trunc',
      'now',
      'random',
      'clock_timestamp',
      'to_char'
  )
ORDER BY p.proname, argument_types;
~~~

### 8.1. Why Display argument_types?

**PostgreSQL functions can be overloaded by parameter types.** A name like `date_trunc` has distinct implementations taking `timestamp without time zone`, `timestamp with time zone`, and other types. Those overloads **do not necessarily share the same volatility**.

Never declare “`date_trunc` is always immutable” or “`date_trunc` is always stable” from its name alone. Always check the **exact signature chosen by SQL**.

### 8.2. Checking One Function by Exact Signature

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.provolatile,
    p.proparallel
FROM pg_catalog.pg_proc AS p
WHERE p.oid = 'pg_catalog.lower(text)'::regprocedure;
~~~

`provolatile = 'i'` means declared `IMMUTABLE`. `proparallel` separately tracks parallel execution safety; **`PARALLEL SAFE` does not mean `IMMUTABLE` and vice versa**.

### 8.3. Using regprocedure to Avoid Overload Confusion

~~~sql
SELECT
    'pg_catalog.now()'::regprocedure AS now_signature,
    'pg_catalog.random()'::regprocedure AS random_signature;
~~~

For custom functions, always verify both **schema and argument types**, especially when names collide with `pg_catalog` or exist across schemas.

## 9. Two Overloads of date_trunc and the timestamptz Trap

A classic error is trying to index a calendar date extracted from a `TIMESTAMPTZ` column:

~~~sql
-- INVALID due to the volatility of the conversion overload:
-- CREATE INDEX idx_events_date_bad_256
-- ON expr_idx_256.events ((occurred_at::date));
~~~

Converting `timestamptz -> date` **depends on the session timezone**: the same UTC instant falls on November 14 in one timezone and November 15 in another. Hence that cast cannot be `IMMUTABLE` on `timestamptz`.

Example:

~~~text
2026-11-14 23:30:00+00
    = 2026-11-15 06:30:00+07

UTC day             : 2026-11-14
Asia/Ho_Chi_Minh day: 2026-11-15
~~~

### 9.1. date_trunc(text, timestamptz)

~~~sql
-- Also rejected:
-- CREATE INDEX idx_events_trunc_bad_256
-- ON expr_idx_256.events (
--     date_trunc('day', occurred_at)
-- );
~~~

The `date_trunc(text, timestamptz)` overload depends on the session `TimeZone` setting, so it is ineligible for `IMMUTABLE` index expressions.

### 9.2. date_trunc(text, timestamp without time zone)

By contrast, when the column is a **timestamp without time zone** and uses the matching overload:

~~~sql
CREATE INDEX idx_lines_created_day_256
ON expr_idx_256.order_lines (
    date_trunc('day', created_local)
);
~~~

The index key is the timestamp truncated to midnight of that timezone-naive timestamp.

Query:

~~~sql
SELECT line_id, created_local
FROM expr_idx_256.order_lines
WHERE date_trunc('day', created_local)
      = TIMESTAMP '2026-11-14 00:00:00'
ORDER BY line_id;
~~~

Returns `line_id = 4, 5, 6` in our dataset.

### 9.3. Do Not Cast Just to Bypass IMMUTABLE Checks

Never cast `timestamptz` to `timestamp` implicitly or carelessly without pinning a timezone:

~~~sql
-- Depends on session timezone; never assume immutable:
-- occurred_at::timestamp
~~~

If business logic truly needs grouping by local calendar day, **specify the target timezone explicitly** (for example via `AT TIME ZONE 'Asia/Ho_Chi_Minh'`) and verify the volatility of every function in the expression. In many systems, the cleanest, safest, and most maintainable design is a **B-tree index on `occurred_at`** paired with explicit timezone-aware range bounds.

### 9.4. Range Predicates Usually Beat Truncating Timestamps to Dates

~~~sql
SELECT
    event_id,
    occurred_at
FROM expr_idx_256.events
WHERE occurred_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND occurred_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07';
~~~

The **half-open `[start, end)`** range avoids tricks like `23:59:59.999999`, preserves full microsecond accuracy, and uses a plain index on `occurred_at`. For timezones observing DST, **never assume every local day is 24 hours**; compute both local midnights in that timezone and convert to instants.

## 10. Expressions Referencing Current Time Cannot Be Index Keys

The statements below are **intentionally invalid examples**—read to understand the error, do not apply them:

~~~sql
-- now() is STABLE, not IMMUTABLE:
-- CREATE INDEX idx_bad_1
-- ON expr_idx_256.events ((now() - occurred_at));

-- clock_timestamp() is VOLATILE:
-- CREATE INDEX idx_bad_2
-- ON expr_idx_256.events ((clock_timestamp()));

-- random() is VOLATILE:
-- CREATE INDEX idx_bad_3
-- ON expr_idx_256.events ((random()));
~~~

PostgreSQL rejects them with:

~~~text
ERROR: functions in index expression must be marked IMMUTABLE
~~~

And for partial index predicates:

~~~text
ERROR: functions in index predicate must be marked IMMUTABLE
~~~

### 10.1. “Last Seven Days” Is a Dynamic Query Condition

Requirement:

> Retrieve events from the last seven days.

Practical solution:

~~~sql
SELECT event_id, event_type
FROM expr_idx_256.events
WHERE occurred_at >= now() - INTERVAL '7 days'
ORDER BY occurred_at DESC;
~~~

The plain `(occurred_at)` index from Section 7 still supports a **range scan** even though the right-hand side calls `now()`. The `IMMUTABLE` rule governs **expressions stored in index keys or predicates**, not runtime bounds evaluated during query execution.

### 10.2. Why Is now() Allowed in the Query?

Inside a query, `now() - INTERVAL '7 days'` is evaluated at execution time as a `STABLE` transaction timestamp bound. It is not persisted in an index across future transactions.

### 10.3. “Currently Active” and Partial Indexes

Never write:

~~~sql
-- INVALID:
-- CREATE INDEX idx_active_promotions
-- ON promotions (promotion_id)
-- WHERE expires_at > now();
~~~

A promotion valid today expires tomorrow **without any `UPDATE`**. A partial index only updates when rows are modified, so it cannot evict rows automatically as time advances.

Valid solutions:

- Index `expires_at` and filter `expires_at > now()` at read time.
- Maintain a **materialized** status column via controlled jobs/transactions if business rules tolerate lag.
- Define partial indexes on **stable column states** such as `cancelled_at IS NULL`, never against the clock.

## 11. Custom Functions: Marking IMMUTABLE Properly

Suppose a system defines email matching as **trimming leading/trailing whitespace and lowercasing**. We can define an SQL function:

~~~sql
CREATE FUNCTION expr_idx_256.normalize_email(input_email TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT pg_catalog.lower(
        pg_catalog.btrim(input_email)
    );
$$;
~~~

Attributes:

| Attribute | Meaning |
| --- | --- |
| `LANGUAGE sql` | Function body is an SQL expression |
| `IMMUTABLE` | Declares identical inputs always return identical outputs |
| `STRICT` | Returns `NULL` when any argument is `NULL` without running the body |
| `PARALLEL SAFE` | Safe to execute inside parallel query workers |

For a function calling only `btrim(text)` and `lower(text)`, `IMMUTABLE` is reasonable as long as the underlying collation stays stable. Still, **case folding can depend on collation/locale**; collation library upgrades or normalization policy changes require index maintenance.

### 11.1. Using the Function in an Index

~~~sql
CREATE INDEX idx_customers_normalized_email_256
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
);
~~~

~~~sql
SELECT
    customer_id,
    email
FROM expr_idx_256.customers
WHERE expr_idx_256.normalize_email(email)
      = expr_idx_256.normalize_email('  ANH@EXAMPLE.COM  ');
~~~

Returns customer 1.

### 11.2. Queries Must Use the Same Normalization Expression

An index on:

~~~sql
expr_idx_256.normalize_email(email)
~~~

will not automatically be used by a query writing:

~~~sql
WHERE lower(email) = 'anh@example.com'
~~~

Even if the function happens to be equivalent to `lower(btrim(email))`, do not assume the planner expands arbitrary UDFs to match index expressions. Standardize the expression across queries or store a dedicated normalized column.

### 11.3. Why Qualify with pg_catalog?

SQL functions can be affected by object name resolution via `search_path`. Qualifying `pg_catalog.lower` and `pg_catalog.btrim` pins the built-in functions and prevents shadowing by identically named functions in other schemas.

This supports **stable function semantics**, though it does not remove the need to verify collations, data, and execution privileges.

## 12. Never “Lie” to PostgreSQL About Immutability

Suppose an author writes a function reading an exchange rate from another table:

~~~sql
-- PSEUDOCODE — NEVER PUT IN PRODUCTION:
-- CREATE FUNCTION calc_vnd_price(usd numeric)
-- RETURNS numeric
-- LANGUAGE sql
-- IMMUTABLE
-- AS $$
--     SELECT usd * rate
--     FROM exchange_rates
--     WHERE currency = 'USD';
-- $$;
~~~

The rate can change while **`usd` on the product row stays unchanged**. Even if marked `IMMUTABLE`, the function depends on `exchange_rates`. If indexed, stored index keys **are never recomputed** when `exchange_rates` updates.

Consequences:

- Index lookups see stale values.
- Sequential scans compute fresh values.
- Business query results can **change depending on the execution plan**.
- Unique expression indexes enforce uniqueness against outdated rules.
- Cached SQL plans can constant-fold `IMMUTABLE` calls incorrectly when state actually changes.

### 12.1. Factors That Make a Function Non-Immutable

- Reading another table or depending on mutable values.
- Calling clock functions (`now`, `current_timestamp`, `clock_timestamp`).
- Using randomness (`random`).
- Depending on session settings like `TimeZone`, `DateStyle`, `lc_time`, or `search_path`.
- Making external HTTP/API calls or reading mutable files/external state.
- Depending on mutable extension/dictionary data without an index rebuild workflow.
- Performing side effects, writing data, or mutating state.

Not every locale-sensitive function is marked `STABLE` in catalogs: built-ins like `lower` are marked `IMMUTABLE` assuming stable collation definitions. **Distinguish** PostgreSQL's declared volatility from rare external shifts like OS/ICU collation upgrades, which require `REINDEX`.

### 12.2. Can You Wrap a STABLE Function in an IMMUTABLE Wrapper?

You can write a wrapper and **falsely declare** it `IMMUTABLE`, because PostgreSQL trusts the wrapper's metadata rather than proving purity across all execution paths. Doing so **never makes session-dependent logic correct**.

Take `unaccent`: its dictionary/rules file can change. Some guides wrap it in an `IMMUTABLE` function for indexing. Only do that if you strictly **control and lock down the transformation rules**, know when to rebuild, and accept manual maintenance. Whenever rules may evolve, storing a **controlled normalized column** is far more transparent.

### 12.3. IMMUTABLE Does Not Mean “Source Code Can Never Change”

A function may be genuinely immutable **under its current definition**, yet if you later change its logic from:

~~~text
normalize_email = lower(trim(email))
~~~

to:

~~~text
normalize_email = lower(trim(email)) + a new rule
~~~

existing keys stored in the index become inconsistent with the new logic. Altering the body of an indexed function **does not automatically rebuild indexes**. You need a migration plan, uniqueness checks, backfill/`REINDEX`, and coordinated rollout.

## 13. STABLE and VOLATILE Have Valid Roles Outside Expression Indexes

Never assume `STABLE` or `VOLATILE` functions are “bad.” Each has legitimate roles:

### 13.1. STABLE

Example:

~~~sql
SELECT now();
~~~

`now()` returns transaction start time, remaining constant throughout a transaction under PostgreSQL semantics. It is ideal for:

~~~sql
SELECT event_id
FROM expr_idx_256.events
WHERE occurred_at >= now() - INTERVAL '24 hours';
~~~

yet unsuitable **inside an index key** because tomorrow's transaction gets a different timestamp for the exact same zero arguments.

### 13.2. VOLATILE

~~~sql
SELECT random(), clock_timestamp();
~~~

These can return different results on consecutive calls within a single statement. Useful for sampling or timing, unsuitable for stable index keys.

### 13.3. Difference from Parallel Safety

A function can be declared:

~~~sql
STABLE PARALLEL SAFE
~~~

yet **cannot** be used in an expression index because it is not `IMMUTABLE`. Conversely, an `IMMUTABLE` function marked `PARALLEL UNSAFE` restricts parallel query execution, which is an **orthogonal property**, not the index volatility requirement.

## 14. Unique Expression Indexes: Case-Insensitive Email Uniqueness

Expression indexes do more than accelerate reads: they can enforce **uniqueness on computed values**.

### 14.1. Uniqueness on Raw email Is Not Enough

~~~sql
CREATE UNIQUE INDEX idx_customers_email_raw_256
ON expr_idx_256.customers (email);
~~~

This treats `'Anh@Example.com'` and `'anh@example.com'` as **two distinct strings** under standard text comparison. If business rules require case-insensitive email uniqueness, a raw unique index is insufficient.

### 14.2. Unique Index on lower(email)

~~~sql
CREATE UNIQUE INDEX uq_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

Now inserting `'ANH@example.COM'` collides with `customer_id = 1`'s `lower(email)` and violates uniqueness.

~~~sql
-- Lab test only:
BEGIN;
SAVEPOINT before_duplicate;

INSERT INTO expr_idx_256.customers
    (customer_id, email, display_name)
VALUES
    (100, 'ANH@example.COM', 'Normalized duplicate email');
-- Expected: ERROR duplicate key value violates unique constraint.
-- SQLSTATE 23505.

ROLLBACK TO SAVEPOINT before_duplicate;
ROLLBACK;
~~~

After an error inside a transaction, roll back to a savepoint or abort the transaction before continuing.

### 14.3. A Unique Expression Index Does Not Imply NOT NULL

If `email` is nullable, `lower(NULL)` evaluates to `NULL`. Under PostgreSQL's default uniqueness rules, **multiple `NULL` keys** are permitted in a unique index. Our lab defines `email TEXT NOT NULL`, closing that loophole.

If `NULL`s should conflict, modern PostgreSQL offers `UNIQUE NULLS NOT DISTINCT` in supported contexts, though only use it when compatible with your data contract and server version.

### 14.4. Note on Unicode and Collations

`lower(text)` follows collation rules, which do not necessarily match full **Unicode case folding** or every email canonicalization rule (local-part conventions, domains, etc.). **Never claim unique `lower(email)` solves every Unicode/email identity edge case** if strict domain rules apply.

### 14.5. Differs from a Column UNIQUE Constraint

A unique expression index enforces uniqueness of an expression, yet behaves differently from a plain column `UNIQUE` constraint in schema references:

- A `FOREIGN KEY` cannot reference an arbitrary expression like `lower(email)` directly without a stored column.
- Schema tools cannot always treat an expression index identically to `UNIQUE(email)`.
- `ON CONFLICT` supports inference on matching expression/predicate indexes with exact syntax, yet you cannot name an expression index identically to a table-level column constraint everywhere.

When FK targets, ORM portability, or clean schema semantics matter, consider a **constrained `normalized_email` column**.

## 15. Partial Expression Indexes: Indexing Only Active Rows

In many systems, soft-deleted accounts stay in the table for history without blocking new active accounts from reusing the email.

Example:

~~~sql
CREATE UNIQUE INDEX uq_customers_active_email_256
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
)
WHERE deleted_at IS NULL;
~~~

Within **active rows**, normalized emails must be unique. Soft-deleted rows are excluded from this partial index.

**Important lab note:** Section 14.2 created `uq_customers_lower_email_256` **across all rows**. When testing “soft-deleted rows allow email reuse,” drop that **full-table unique index** or test on a separate table; otherwise the full-table index still blocks duplicate `lower(email)` values regardless of `deleted_at`.

### 15.1. Query Matching the Predicate

~~~sql
SELECT
    customer_id,
    email
FROM expr_idx_256.customers
WHERE deleted_at IS NULL
  AND expr_idx_256.normalize_email(email)
      = expr_idx_256.normalize_email('ANH@EXAMPLE.COM');
~~~

The `deleted_at IS NULL` condition lets the planner prove the query only needs rows covered by the partial index.

### 15.2. Why Can Omitting deleted_at Prevent Partial Index Usage?

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE expr_idx_256.normalize_email(email)
      = 'anh@example.com';
~~~

This query also requests **deleted rows**, whereas the partial index covers only **non-deleted rows**. PostgreSQL cannot use a partial index when it does not cover all eligible rows.

### 15.3. Predicate Implication and Prepared Statements

The planner must prove the query's `WHERE` clause **implies the partial index predicate** at planning time. Complex boolean rewrites or parameterized predicates in generic plans may **fail this proof**.

For example, a partial index on:

~~~sql
WHERE deleted_at IS NULL
~~~

aligns cleanly with queries stating that exact condition. Avoid assuming PostgreSQL has a universal theorem prover for arbitrary `CASE`, `COALESCE`, `OR`, or bound-parameter combinations.

### 15.4. Using Partial Unique Indexes for “Unique Only While Active”

This illustrates how an index enforces **business invariants**, not merely read optimization. Still, ensure domain clarity on:

- Can soft-deleted emails truly be reused by new accounts?
- If an old account is restored, what happens if another active account took the email?
- Have existing active duplicates been cleaned up before building the unique index?
- Do login/lookup queries consistently filter `deleted_at IS NULL`?

If business rules change later, plan migrations and duplicate reconciliation carefully.

## 16. The Entire Expression Must Be Valid, Not Just the Outermost Function

Example:

~~~sql
CREATE INDEX idx_customers_cleanup_256
ON expr_idx_256.customers (
    lower(btrim(email))
);
~~~

For this expression index to be valid, it is not enough for `lower` alone to be `IMMUTABLE`. Every nested function (`btrim`), implicit cast, collation operation, and operator must also qualify.

### 16.1. COALESCE and CASE

Constructs like `COALESCE` or `CASE` do not automatically invalidate an expression index:

~~~sql
CREATE INDEX idx_customer_deleted_marker_256
ON expr_idx_256.customers (
    (CASE WHEN deleted_at IS NULL THEN 1 ELSE 0 END)
);
~~~

Checking `deleted_at IS NULL` depends purely on row data; the `1`/`0` output does not vary by session. Still, a two-value expression index typically has **low selectivity** and helps far less than a targeted partial index.

Another example:

~~~sql
CREATE INDEX idx_customers_name_fallback_256
ON expr_idx_256.customers (
    lower(COALESCE(display_name, ''))
);
~~~

In our lab schema `display_name` is `NOT NULL`, making `COALESCE` redundant. On nullable columns it can work, provided treating `NULL` identically to `''` matches business semantics.

### 16.2. Never Put Aggregates, Window Functions, or Subqueries in Index Expressions

An expression index evaluates **columns of a single row in the indexed table**, not arbitrary cross-row or cross-table queries.

The ideas below are invalid / wrong designs for expression indexes:

~~~sql
-- Invalid / wrong design:
--
-- CREATE INDEX idx_sum
-- ON order_lines ((SUM(unit_price * quantity)));
--
-- CREATE INDEX idx_rank
-- ON orders ((ROW_NUMBER() OVER (ORDER BY created_at)));
--
-- CREATE INDEX idx_latest_rate
-- ON products ((price * (
--     SELECT rate FROM exchange_rates ORDER BY changed_at DESC LIMIT 1
-- )));
~~~

Values such as **multi-row sums**, **window rankings**, or **latest rates from another table** belong in different patterns:

- Aggregating over well-indexed base data;
- Materialized views with controlled `REFRESH` schedules;
- Summary tables maintained explicitly;
- Materialized snapshot columns captured at write time;
- Business logic kept separate from index expressions.

### 16.3. Never Depend on Values from Another Row

A truly `IMMUTABLE` function cannot change output when a row in a lookup table changes. If you want an indexed lookup result, materialize the source value onto the target row itself, manage synchronization explicitly, and index that stored column. **Indexes do not track data dependencies on rows of other tables.**

## 17. Changing a Function Referenced by an Index: Why REINDEX Is Needed

Suppose a system has:

~~~sql
CREATE INDEX idx_customers_normalized_email_256
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
);
~~~

and version 1 of the function computes:

~~~text
normalize_email(email) = lower(trim(email))
~~~

Later the team updates the function body to strip extra characters, normalize Unicode, or apply new rules. **PostgreSQL does not automatically recompute existing index keys just because the function body changed.**

### 17.1. Stale Index Scenario

~~~text
Day 1:
    email = "A.B@example.com"
    f_v1(email) = "a.b@example.com"
    → index key = "a.b@example.com"

Day 20:
    f_v2(email) = "ab@example.com"
    → SELECT using new function searches for "ab@example.com"
    → index may still hold stale key "a.b@example.com"
~~~

If the planner uses the expression index, queries can miss matching rows. Worse, on a **UNIQUE** expression index, changed normalization rules can cause **previously distinct rows to collide**, requiring data cleanup before rebuilding.

### 17.2. Safe Migration Plan

1. Agree on the new rule and application version.
2. Dry-run the new expression across existing rows.
3. Detect any collisions/duplicates under the new rule.
4. Resolve duplicates and prepare a business rollback plan.
5. Deploy the new function cleanly (often versioned, e.g. `normalize_email_v2`).
6. Build the new index alongside, or `REINDEX` the affected index after updating the function.
7. Verify query plans, uniqueness constraints, and cut over application queries.
8. Drop the old index/function only after confirming zero dependencies and safe rollback.

**Never edit an `IMMUTABLE` function's body in production as a “harmless code tweak” when indexes, generated columns, or plans depend on it.**

### 17.3. Example REINDEX in an Appropriate Environment

~~~sql
-- Recomputes index keys using the current function definition.
-- Run only when planned and authorized operationally.
REINDEX INDEX expr_idx_256.idx_customers_normalized_email_256;
~~~

Standard `REINDEX` blocks concurrent writes/reads depending on scope. On supported PostgreSQL versions and situations, consider:

~~~sql
REINDEX INDEX CONCURRENTLY
    expr_idx_256.idx_customers_normalized_email_256;
~~~

`REINDEX ... CONCURRENTLY` has specific restrictions (cannot run inside an explicit transaction block, higher I/O, not valid for every object/failure case). Consult docs for your exact version and assess I/O and lock impact.

### 17.4. Changing Volatility Labels Does Not Fix Stored Index Data

If an existing index already references a function and you alter the function from `IMMUTABLE` to `STABLE`, PostgreSQL does not automatically “heal” or convert the index. **Index keys require `IMMUTABLE`**, so the right fix is dropping the index and redesigning the schema or queries—not tweaking metadata alone.

## 18. Collations and ICU/libc: Silent Logic Changes

For text, many comparisons and case conversions depend on **collations**. PostgreSQL uses `libc` or `ICU` collations depending on build and configuration.

Example:

~~~sql
CREATE INDEX idx_customers_lower_name_256
ON expr_idx_256.customers (lower(display_name));
~~~

This index assumes `lower` behavior and collation sort order remain constant. If the OS `libc` or `ICU` library updates collation rules, keys stored under the old version may **no longer match the sort order or value rules of the new version**.

### 18.1. Inspecting Collation Metadata

~~~sql
SELECT
    oid::regcollation AS collation_name,
    collprovider,
    collversion,
    pg_catalog.pg_collation_actual_version(oid) AS actual_version
FROM pg_catalog.pg_collation
WHERE collversion IS NOT NULL
ORDER BY 1
LIMIT 30;
~~~

### 18.2. Detecting Collation Version Mismatches

~~~sql
SELECT
    oid::regcollation AS collation_name,
    collversion,
    pg_catalog.pg_collation_actual_version(oid) AS actual_version
FROM pg_catalog.pg_collation
WHERE collversion IS NOT NULL
  AND collversion IS DISTINCT FROM
      pg_catalog.pg_collation_actual_version(oid)
ORDER BY 1;
~~~

Mismatches signal the need to consult docs and plan index maintenance. **Do not claim every index is instantly corrupted from one version mismatch row**, yet you must audit collation-dependent objects carefully.

### 18.3. During Collation Upgrades

A safe plan typically involves:

- Identifying affected indexes, constraints, and materialized objects.
- Rebuilding affected indexes/objects under the new rules.
- Checking for collisions or reordered keys in unique indexes.
- Refreshing collation version metadata only after dependent indexes are rebuilt.

**Running `ALTER COLLATION ... REFRESH VERSION` just to silence warnings without rebuilding affected indexes leaves stale index keys intact.**

### 18.4. COLLATE "C" for Strict Byte/ASCII Semantics

For ASCII-only technical codes needing predictable rules, specify `"C"` collation explicitly:

~~~sql
CREATE INDEX idx_customers_email_c_256
ON expr_idx_256.customers (
    lower(email COLLATE "C")
);
~~~

Queries targeting this index must use **the same collation** and expression form:

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email COLLATE "C") = 'anh@example.com';
~~~

However, `"C"` collation follows ASCII case rules rather than full Unicode linguistics. **Never switch collations solely for index convenience** when applications require locale-sensitive human name or address matching.

## 19. Do Query Expressions Match the Index?

Consider:

~~~sql
CREATE INDEX idx_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

Queries:

~~~sql
-- A: direct match
SELECT customer_id FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';

-- B: also usable when planner constant-folds the right side
SELECT customer_id FROM expr_idx_256.customers
WHERE lower(email) = lower('ANH@EXAMPLE.COM');

-- C: different left-hand expression
SELECT customer_id FROM expr_idx_256.customers
WHERE lower(btrim(email)) = 'anh@example.com';

-- D: different operator and search pattern
SELECT customer_id FROM expr_idx_256.customers
WHERE email ILIKE '%example.com';
~~~

**A/B** align with the index key. **C** evaluates a different expression (`lower(btrim(email))`), so do not expect `lower(email)` to serve it. **D** is a substring search on the raw column, requiring a different index method/operator class.

### 19.1. PostgreSQL Can Normalize Some Expressions

The planner performs constant folding and basic transformations, so **SQL text does not have to be byte-for-byte identical to the index definition**. Still, never assume the planner proves arbitrary algebraic identities or sees through custom UDFs.

**Practical rule:** write predicates consistently with your data definitions, inspect `EXPLAIN`, and measure on real workloads instead of guessing.

### 19.2. Data Types and Implicit Casts

An index on:

~~~sql
(payload ->> 'customer_id')
~~~

produces `text`. The query:

~~~sql
WHERE payload ->> 'customer_id' = '1'
~~~

matches the `text` key. By contrast, writing:

~~~sql
WHERE (payload ->> 'customer_id')::bigint = 1
~~~

produces a **`bigint` expression**. A `text` expression index will not serve `bigint` comparisons directly. If numeric comparisons dominate and every JSONB document guarantees valid integer text, build the index with the matching cast.

### 19.3. Watch Out for Invalid Data When Casting in Expression Indexes

Example:

~~~sql
-- Valid only if every indexed payload contains
-- a customer_id string castable to BIGINT.
--
-- CREATE INDEX idx_events_customer_numeric
-- ON expr_idx_256.events (
--     ((payload ->> 'customer_id')::bigint)
-- );
~~~

If even one payload holds `"customer_id":"ABC"`, **creating the index fails** on the invalid cast. Once created, any later `INSERT`/`UPDATE` inserting malformed data also fails when PostgreSQL computes the index key.

While this catches bad data indirectly, **it never replaces explicit schema validation** such as `CHECK` constraints or application JSON schema checks.

## 20. B-tree Expression Indexes vs. GIN / GiST / Trigram

An expression index is not a **separate index access method**. It defines **what key is indexed**; the access method can still be B-tree, GIN, GiST, or another supported method.

### 20.1. B-tree for Equality and Ranges on Expressions

~~~sql
CREATE INDEX idx_lines_amount_btree_256
ON expr_idx_256.order_lines
USING btree ((unit_price * quantity));
~~~

Fits `=`, `<`, `>=`, and `ORDER BY` on that same expression depending on planner costs and stats.

### 20.2. GIN on Raw JSONB

When querying JSONB structure:

~~~sql
CREATE INDEX idx_events_payload_gin_256
ON expr_idx_256.events
USING gin (payload);
~~~

Query:

~~~sql
SELECT event_id
FROM expr_idx_256.events
WHERE payload @> '{"customer_id":"1"}'::jsonb;
~~~

GIN on `payload` accelerates `@>` containment via JSONB opclasses—a completely different strategy from a B-tree on `payload ->> 'customer_id'`.

### 20.3. B-tree on an Extracted JSONB Field

~~~sql
CREATE INDEX idx_events_customer_text_256
ON expr_idx_256.events (
    (payload ->> 'customer_id')
);
~~~

This indexes the extracted text for `WHERE payload ->> 'customer_id' = '1'`. When filtering solely by equality on one fixed JSON path, this can be much smaller and faster than a full-document GIN index. When filtering flexibly across many paths, GIN fits better.

### 20.4. Trigrams for Substring Search

If `pg_trgm` is installed and authorized:

~~~sql
-- Run only when extension is available and authorized:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- CREATE INDEX idx_customer_name_trgm_256
-- ON expr_idx_256.customers
-- USING gin (lower(display_name) gin_trgm_ops);
~~~

Query:

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(display_name) LIKE '%anh%';
~~~

A plain B-tree expression index on `lower(display_name)` cannot optimize `LIKE '%substring%'`. Trigram GIN/GiST indexes handle substring and similarity searches, subject to pattern length and write overhead.

**Never route every “name search” blindly to a B-tree on `lower(name)`**—distinguish exact equality, prefix search, and substring/fuzzy search.

### 20.5. Prefix LIKE and text_pattern_ops

Under many non-`C` collations, a default B-tree will not serve prefix `LIKE 'abc%'`. A pattern operator class solves this:

~~~sql
CREATE INDEX idx_customers_name_prefix_256
ON expr_idx_256.customers (
    lower(display_name) text_pattern_ops
);
~~~

Query:

~~~sql
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(display_name) LIKE 'anh%';
~~~

Actual index usage depends on collation, pattern selectivity, and data volume. **`text_pattern_ops` does not accelerate mid-string wildcard searches.**

## 21. Expression Indexes vs. Generated Columns: A Design Choice

Modern PostgreSQL supports **generated columns**. As an alternative to indexing `lower(btrim(email))` directly, you can store a generated column:

~~~sql
ALTER TABLE expr_idx_256.customers
ADD COLUMN normalized_email TEXT
GENERATED ALWAYS AS (
    lower(btrim(email))
) STORED;

CREATE INDEX idx_customers_normalized_column_256
ON expr_idx_256.customers (normalized_email);
~~~

### 21.1. Comparison

| Aspect | Expression Index | Stored Generated Column + Index |
| --- | --- | --- |
| Where is normalized data stored? | Inside the index | In the table row and optionally in the index |
| Can `SELECT` reference a simple column name? | Not directly; queries write the expression | Yes: `normalized_email` |
| Easy for multiple queries/ORMs to share? | Requires consistent expression everywhere | Easy to reference by column name |
| Storage footprint? | Index only | Table column + index |
| Requires `IMMUTABLE` expression? | Yes, for the index | **Yes**, for generated expressions |
| Can serve as FK target with unique constraint? | Not directly via expression | Yes, as a real column with `UNIQUE` |
| Changing normalization rules | Requires rebuilding the index | Requires migration/backfill/recompute as supported by PostgreSQL |

**Generated columns are not a loophole around volatility.** PostgreSQL also requires generated expressions to use `IMMUTABLE` functions and forbids referencing other tables.

### 21.2. When to Choose an Expression Index?

Usually preferable when:

- Only a few queries need the expression and you don't need it as a standalone column;
- The transformation is simple and genuinely immutable;
- No foreign keys or ORMs need a named normalized column;
- The expression index has strong selectivity.

### 21.3. When to Choose a Generated Column?

Useful when:

- Many queries, reports, and APIs read the transformed value;
- You want constraints or clean column references in SQL/ORMs;
- You want schema clarity instead of duplicating complex expressions across queries;
- Extra row storage and migration effort are acceptable.

### 21.4. Application-Maintained Columns

If transformation rules depend on time-varying dictionaries, rates, or configuration, a **regular column maintained explicitly** by application code, triggers, or batch jobs fits better than generated columns or expression indexes. When rules evolve, migrations backfill stored values and rebuild indexes cleanly.

No single choice wins everywhere; correctness and long-term operability outweigh saving a few lines of SQL.

## 22. Expression Statistics and the Role of ANALYZE

The planner decides index usage from statistics:

- Estimated fraction of rows matching the predicate (selectivity);
- Distinctness of expression values;
- Cost of index scan plus heap fetches;
- Table/index size, page count, and physical correlation;
- Other filters, joins, sorts, and `LIMIT`.

After creating indexes or loading significant data, run:

~~~sql
ANALYZE expr_idx_256.customers;
ANALYZE expr_idx_256.order_lines;
ANALYZE expr_idx_256.events;
~~~

`ANALYZE` gathers planner statistics—including per-expression statistics for expression indexes. It **never modifies business row values** the way an `UPDATE` does.

### 22.1. EXPLAIN in the Lab

~~~sql
EXPLAIN
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

Inspect:

~~~text
Seq Scan / Index Scan / Bitmap Heap Scan
Index Cond / Filter
estimated rows
estimated cost
~~~

With six rows, `Seq Scan` will beat `Index Scan`.

### 22.2. EXPLAIN ANALYZE Executes the Query

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email) = 'anh@example.com';
~~~

On read-only lab `SELECT`s, this is safe for measurement. However, **`EXPLAIN ANALYZE` executes the real SQL statement**: running it on `UPDATE`/`DELETE` in production without safeguards is dangerous. Even `SELECT`s calling volatile functions with side effects must be handled carefully.

### 22.3. Checking Whether the Index Actually Serves the Workload

~~~sql
SELECT
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch
FROM pg_catalog.pg_stat_user_indexes AS s
WHERE s.schemaname = 'expr_idx_256'
ORDER BY s.idx_scan DESC, s.indexrelname;
~~~

`idx_scan = 0` after a handful of lab queries does not prove an index is useless: statistics may have been reset, plans may shift at scale, or the workload has not run yet. Nor should you drop a unique index merely for low scan counts—it also **enforces data integrity on writes**.

## 23. INSERT/UPDATE Overhead and HOT Updates

An expression index pays off when reads speed up enough to outweigh write costs.

### 23.1. INSERT Must Compute the Index Key

With:

~~~sql
CREATE INDEX idx_customers_lower_email_256
ON expr_idx_256.customers (lower(email));
~~~

every inserted row computes `lower(email)` and writes an index entry. Multiple complex expression indexes can noticeably increase CPU and write I/O.

### 23.2. UPDATE Complicates Index Maintenance

When `email` changes, `lower(email)` can change too, requiring index updates for the new tuple version.

Example:

~~~sql
BEGIN;

UPDATE expr_idx_256.customers
SET email = 'ANH.NEW@EXAMPLE.COM'
WHERE customer_id = 1;

SELECT customer_id
FROM expr_idx_256.customers
WHERE lower(email) = 'anh.new@example.com';
-- Customer 1 inside the transaction.

ROLLBACK;
~~~

### 23.3. HOT (Heap-Only Tuple) Updates

PostgreSQL's **HOT update** skips creating new index entries when an update leaves all indexed columns untouched and the new tuple version fits on the same heap page.

An expression index references its underlying column `email`. Whenever `email` is updated, HOT eligibility is typically blocked even if the normalized expression result happens to remain unchanged. Thus **the more columns and expressions indexed, the harder it becomes to achieve HOT updates** on write workloads touching those columns.

Never assume “an expression index only affects `SELECT`s.” On high-`UPDATE` tables, write amplification and HOT loss are critical design factors.

### 23.4. Observing HOT Activity on Tables

~~~sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'expr_idx_256'
ORDER BY relname;
~~~

These are cumulative counters since stats reset and update asynchronously. They help monitor workload health, though they do not isolate a single expression index as the sole cause of every HOT ratio shift.

### 23.5. Complex Expressions Consume Build and Maintenance CPU

Heavy Unicode normalization, parsing large JSON documents, or computing expensive hashes adds CPU overhead to `CREATE INDEX`, `INSERT`, and `UPDATE`. Build expression indexes only where queries genuinely benefit, avoiding rarely queried or constantly mutated expressions.

## 24. CREATE INDEX CONCURRENTLY and Production Operations

On large production tables, standard `CREATE INDEX` blocks concurrent writes during the build. PostgreSQL provides:

~~~sql
CREATE INDEX CONCURRENTLY idx_customers_lower_email_conc_256
ON expr_idx_256.customers (lower(email));
~~~

### 24.1. Key Differences

`CREATE INDEX CONCURRENTLY` avoids **long write locks** while building, at the cost of:

- Longer total build duration;
- Multiple table scans and waits on active transactions;
- Sustained CPU and I/O load while running;
- Leaving behind an **`INVALID` index** if canceled or failed;
- Specific restrictions around partitioned tables and transaction blocks.

**Never run inside an explicit transaction block:**

~~~sql
-- INVALID:
-- BEGIN;
-- CREATE INDEX CONCURRENTLY idx_x ON table_x (lower(col));
-- COMMIT;
~~~

### 24.2. Checking Index Validity

~~~sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisvalid AS is_valid,
    i.indisready AS is_ready,
    i.indisunique AS is_unique
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS t
    ON t.oid = i.indrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'expr_idx_256'
ORDER BY index_name;
~~~

- `indisvalid`: whether the index is valid for planner query and constraint usage.
- `indisready`: whether the index is already receiving `INSERT`/`UPDATE` maintenance.

Never drop an invalid index without verifying which build created it and whether it impacts uniqueness or locking.

### 24.3. If CONCURRENTLY Fails

A typical runbook:

1. Check logs and SQLSTATE for the failure cause (duplicate key in unique build, invalid cast, lock timeout, disk full).
2. Inspect `pg_index.indisvalid` / `indisready`.
3. Inspect malformed or duplicate data.
4. Safely **drop the invalid index** per your PostgreSQL version/procedure and rebuild, or use supported rebuild tooling.
5. Verify valid status, query plans, and constraints afterward.

**Never treat a failed `CREATE INDEX CONCURRENTLY` as “nothing happened.”** It leaves catalog metadata that can still affect write paths until cleaned up.

### 24.4. UNIQUE CONCURRENTLY Requires Duplicate Preflight First

If you build a unique index on `lower(email)` when the table already holds case-colliding emails, the build fails. During concurrent unique builds, PostgreSQL begins enforcing uniqueness in intermediate phases even if the build ultimately fails invalid. Always run a preflight check and resolve duplicates before deploying online unique indexes.

## 25. Inspecting Expression Index Definitions in Catalogs

### 25.1. pg_indexes: Quick Overview

~~~sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'expr_idx_256'
ORDER BY tablename, indexname;
~~~

`indexdef` displays the DDL definition, including expressions, index method, `UNIQUE`, and `WHERE` clauses.

### 25.2. pg_get_indexdef

~~~sql
SELECT
    c.oid::regclass AS index_name,
    pg_catalog.pg_get_indexdef(c.oid) AS create_index_sql
FROM pg_catalog.pg_class AS c
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relkind IN ('i', 'I')
  AND n.nspname = 'expr_idx_256'
ORDER BY index_name;
~~~

### 25.3. Separating Expressions and Partial Predicates

~~~sql
SELECT
    idx.indexrelid::regclass AS index_name,
    idx.indrelid::regclass AS table_name,
    pg_catalog.pg_get_expr(
        idx.indexprs,
        idx.indrelid
    ) AS indexed_expressions,
    pg_catalog.pg_get_expr(
        idx.indpred,
        idx.indrelid
    ) AS partial_index_predicate,
    idx.indisunique,
    idx.indisvalid
FROM pg_catalog.pg_index AS idx
JOIN pg_catalog.pg_class AS c
    ON c.oid = idx.indexrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'expr_idx_256'
ORDER BY index_name;
~~~

Meaning:

- `indexprs`: decompiled **index expressions**, `NULL` for plain column indexes.
- `indpred`: **partial index predicate**, `NULL` for full-table indexes.
- `indisunique`: whether the index enforces uniqueness.
- `indisvalid`: validity flag.

This is the cleanest way to **audit the exact definitions stored by PostgreSQL**, especially when migrations or ORMs generated them.

## 26. Preflight Check Before Creating a UNIQUE Expression Index

Before enforcing normalized uniqueness, detect duplicate groups first:

~~~sql
SELECT
    lower(btrim(email)) AS normalized_email,
    COUNT(*) AS row_count,
    ARRAY_AGG(customer_id ORDER BY customer_id)
        AS customer_ids
FROM expr_idx_256.customers
WHERE deleted_at IS NULL
GROUP BY lower(btrim(email))
HAVING COUNT(*) > 1
ORDER BY row_count DESC, normalized_email;
~~~

On our clean seed dataset, this returns zero rows. In real production tables, resolve any `COUNT(*) > 1` groups per business policy before creating the unique index.

### 26.1. Testing Duplicate Rejection in a Lab Transaction

~~~sql
BEGIN;

-- If the full-table unique index from Section 14 is still active,
-- the INSERT below would fail immediately. In the lab, inspect
-- preflight logic rather than intentionally breaking constraints.

-- Example simulation when checking a non-unique staging table:
-- INSERT INTO stage_customers(email)
-- VALUES ('Anh@Example.com'), ('ANH@example.COM');

ROLLBACK;
~~~

**A proper unique index must reject new duplicates**, while preflight prevents migrations from failing unexpectedly on legacy duplicates.

### 26.2. Expression Uniqueness Checks Only the Expression Result

With `UNIQUE (lower(btrim(email)))`, equality is governed strictly by **the expression output and collation**. Two distinct raw strings can collide, while two strings users consider “identical” might not collide if normalization misses that rule.

Therefore, **canonicalization policy is a business decision** to finalize before building the index, never left blindly to `lower()`.

## 27. When Should You Avoid Creating an Expression Index?

### 27.1. Table Is Too Small

With only dozens of rows, `Seq Scan` beats `Index Scan`. Extra indexes just add write and maintenance overhead.

### 27.2. Expression Has Very Low Selectivity

~~~sql
CREATE INDEX idx_customers_is_active_256
ON expr_idx_256.customers (
    (deleted_at IS NULL)
);
~~~

This index holds only two key values: `TRUE` and `FALSE`. If most customers are active, queries filtering active rows still read most of the table, gaining little. A **partial index** on a selective key among active rows is usually far better.

### 27.3. Business Logic Changes Frequently

If pricing rules, exchange rates, or name-cleaning logic mutate regularly, expression indexes require constant migrations and rebuilds. Prefer keeping raw inputs and **storing versioned computed values**, or using dedicated lookup/summary tables.

### 27.4. Queries Don't Actually Use That Expression

If APIs consistently query `email = ?` and never `lower(email)`, indexing `lower(email)` adds zero read benefit. Audit query patterns before indexing.

### 27.5. Write Cost Exceeds Read Benefit

High-throughput ingest/log tables suffer noticeably if every insert computes heavy expression indexes. Consider query frequency and alternatives like BRIN on timestamps, partitioning, or offloading analytics instead of stacking complex B-tree expression indexes.

### 27.6. No Governance Over Functions and Collations

If multiple teams can edit an `IMMUTABLE` UDF without migration discipline, expression indexes depending on it become silent correctness hazards. Establish ownership, versioning, and `REINDEX` runbooks first.

## 28. Designing Tests for Expression Indexes

Thorough testing goes beyond checking a query on a handful of rows:

1. **Expression match:** queries use the exact normalizer/predicate semantics.
2. **NULL handling:** `NULL`, empty strings, whitespace, missing JSON keys.
3. **Collation accuracy:** Unicode/case folding matches data contracts.
4. **Uniqueness:** duplicates are rejected; valid distinct rows succeed.
5. **Post-UPDATE consistency:** updating source columns updates index keys accurately.
6. **Function migration:** rebuild/new index aligns with updated UDF versions.
7. **Timezone/collation upgrades:** detect `REINDEX` requirements.
8. **Scale behavior:** planner choice, latency, buffers, and I/O on realistic volume.
9. **Concurrency:** online index creation, concurrent unique violations, rollback.
10. **Operations:** monitoring invalid indexes, sizes, and usage counters.

### 28.1. Comparing Seq Scan and Index Scan in Lab Tests

To inspect plans in the lab, run normal queries first, then inspect `EXPLAIN` under `SET LOCAL enable_seqscan = off` inside a transaction to see the index plan shape.

**Never force plans in production or cite timings on a six-row table as performance proof.** Real performance analysis requires representative data and complete statistics.

### 28.2. Checking Function Volatility via Catalogs

Before indexing a UDF, verify:

~~~sql
SELECT
    p.oid::regprocedure AS signature,
    p.provolatile
FROM pg_catalog.pg_proc AS p
WHERE p.oid =
    'expr_idx_256.normalize_email(text)'::regprocedure;
~~~

Expect `provolatile = 'i'`. Remember that **checking metadata does not prove the function is genuinely immutable**; manual code review remains mandatory.

## 29. Common Mistakes

| Symptom / Misconception | Why It Is Wrong | How to Handle It |
| --- | --- | --- |
| Having an index on `email` ensures `lower(email) = ?` uses it | Raw key and expression differ | Index `lower(email)` or query raw `email` |
| `CREATE INDEX ON t (a + b)` | Non-function expressions need outer parens | `ON t ((a + b))` |
| Indexing `name` suffices for `ORDER BY lower(name)` | Expression sort order differs from raw column order | Index `lower(name)` and check `EXPLAIN` |
| `IMMUTABLE` is just a hint to help the planner | It is a semantic contract indexes depend on | Ensure true immutability |
| `STABLE` is “almost immutable,” so it's fine in indexes | Output can change across transactions/sessions | Never use in index keys or predicates |
| Any function marked `IMMUTABLE` is guaranteed safe | PostgreSQL trusts declarations without deep purity proofs | Review code and dependencies |
| `now()` works in indexes because it is stable in a transaction | Changes across transactions | Index the timestamp column; filter ranges in queries |
| `random()` can index random sampling | Output changes on every call | Never use volatile index expressions |
| `timestamptz::date` is immutable | Depends on session `TimeZone` | Use `timestamptz` ranges or explicit timezone logic |
| All `date_trunc` overloads behave identically | `timestamp` and `timestamptz` overloads differ in volatility | Check `pg_proc` by signature |
| `PARALLEL SAFE` means `IMMUTABLE` | Orthogonal properties | Inspect `provolatile` and `proparallel` separately |
| Using `WHERE expires_at > now()` as a partial predicate | Membership drifts over time | Index `expires_at` directly |
| `DISTINCT`/`LOWER` handles all Unicode/email identity | Canonicalization depends on rules and collations | Define canonicalization explicitly |
| Adding unique `lower(email)` without `NOT NULL` | Multiple `NULL` rows may be allowed | Add `NOT NULL` or `NULLS NOT DISTINCT` as needed |
| Full-table unique index allows soft-deleted email reuse | Full-table index still rejects duplicates | Use a partial unique index for active rows |
| A partial index serves queries omitting its predicate | Deleted rows are absent from the index | Queries must imply the index predicate |
| Planner always recognizes algebraically equivalent expressions | No general theorem prover for arbitrary expressions | Standardize expressions and check `EXPLAIN` |
| Indexing JSON text works identically for `bigint` casts | Expression result types differ | Index the cast matching the query type |
| GIN on JSONB optimizes every `->>` equality optimally | Different operators and access patterns | Pick B-tree expression or GIN as needed |
| B-tree `lower(name)` accelerates `LIKE '%abc%'` | Mid-string wildcards need another strategy | Evaluate `pg_trgm` GIN/GiST or FTS |
| Editing an `IMMUTABLE` UDF updates existing indexes automatically | Stored keys become stale | Plan migration + `REINDEX` or new index |
| `ALTER COLLATION ... REFRESH VERSION` fixes stale keys | Only updates metadata; keys stay old | Rebuild dependent indexes first per runbook |
| Expression indexes only affect reads | They add write overhead and block HOT updates | Measure read/write trade-offs |
| Failed `CREATE INDEX CONCURRENTLY` leaves nothing behind | Can leave an `INVALID` index | Check `pg_index` and clean up |
| `EXPLAIN ANALYZE` only “observes” | It executes DML statements | Measure safely only on approved workloads |
| `Seq Scan` on a tiny table means the index is broken | Planner cost favors `Seq Scan` on tiny tables | Test on realistic data sizes |
| `idx_scan = 0` means drop a unique index | It enforces data integrity on writes | Check both usage and constraints |
| Generated columns allow `STABLE` functions | Generated expressions also require immutability | Use another design when logic mutates |

## 30. Practice Exercises

Exercises use `expr_idx_256`. Some ask you to **predict the error rather than running intentionally invalid DDL**. When practicing uniqueness violations or UDF edits, run only in a lab database with rollback/migration plans.

### Exercise 1 — Definition of Expression Index

Explain the difference between:

~~~sql
CREATE INDEX i1 ON expr_idx_256.customers (email);
CREATE INDEX i2 ON expr_idx_256.customers (lower(email));
~~~

**Hint:** `i1` stores raw column values; `i2` stores `lower(email)`. Queries filtering `lower(email)` align with `i2`.

### Exercise 2 — Case-Insensitive Email Lookup

Write a query searching for `'ANH@EXAMPLE.COM'` using `lower` and the created index.

**Expected answer:** customer ID 1.

### Exercise 3 — Expression Parentheses

Fill in the syntax:

~~~sql
CREATE INDEX idx_example
ON expr_idx_256.order_lines (___);
~~~

to index `unit_price * quantity`.

**Answer:** `(unit_price * quantity)` inside the index key list, yielding `((unit_price * quantity))` in full.

### Exercise 4 — Query by Line Total

Write a query fetching order lines with total `>= 300000`.

**Answer:** `line_id = 3, 4, 5`.

### Exercise 5 — JSONB Extraction

Create an expression index on `(payload ->> 'customer_id')` and query events for customer `'1'`.

**Answer:** `event_id = 1, 3`.

### Exercise 6 — Multi-Column Expression Index

Design an index with first key `event_type` and second key `payload ->> 'customer_id'`. Which query aligns better?

1. `WHERE event_type = 'purchase' AND payload ->> 'customer_id' = '1'`.
2. `WHERE occurred_at > ...`.

**Hint:** the index keys `(event_type, extracted_customer_id)`, not `occurred_at`.

### Exercise 7 — EXPLAIN on a Small Table

Why might `EXPLAIN` choose `Seq Scan` even when `idx_customers_lower_email_256` exists?

**Answer:** the table is tiny, so scanning it directly costs less; the planner is never forced to use an index.

### Exercise 8 — Inspecting Volatility

Run the catalog query from Section 8 and compare:

- `lower(text)`;
- `now()`;
- `random()`;
- `date_trunc` overloads.

Note `provolatile = 'i'/'s'/'v'` and explain each.

### Exercise 9 — Why Is now() Rejected?

Explain why you cannot index:

~~~sql
-- CREATE INDEX i_bad ON events ((now() - occurred_at));
~~~

**Answer:** for the same row and `occurred_at`, the result changes as time advances. `now()` is not `IMMUTABLE`.

### Exercise 10 — Proper Last-Seven-Days Query

Write a query selecting events from the last 7 days using an index on `occurred_at`.

**Hint:** `WHERE occurred_at >= now() - INTERVAL '7 days'`; the index stores the column, not `now()`.

### Exercise 11 — “Unexpired” Partial Index

Why is:

~~~sql
-- CREATE INDEX ON promotions(id)
-- WHERE expires_at > now();
~~~

invalid? Propose indexing `expires_at` instead.

### Exercise 12 — Date from TIMESTAMPTZ

Given `occurred_at = TIMESTAMPTZ '2026-11-14 23:30:00+00'`:

**Question:** how do the UTC date and `Asia/Ho_Chi_Minh` date differ? Why does `occurred_at::date` depend on session timezone?

**Answer:** UTC is Nov 14; HCMC is Nov 15.

### Exercise 13 — date_trunc Overloads

Compare:

~~~sql
date_trunc('day', TIMESTAMP '2026-11-14 10:15:00')
date_trunc('day', TIMESTAMPTZ '2026-11-14 10:15:00+07')
~~~

Check `pg_proc` to see the volatility of each overload. Why is the `timestamptz` overload unsuitable directly in an expression index?

### Exercise 14 — Email Normalization UDF

Create `expr_idx_256.normalize_email(text)` using `lower(btrim(input_email))`, declared `IMMUTABLE STRICT PARALLEL SAFE`. Write a query locating customer ID 1 using uppercase/whitespace input.

### Exercise 15 — Misleading IMMUTABLE Declaration

A developer marks a UDF computing `price * exchange_rate` from `exchange_rates` as `IMMUTABLE`.

**Question:** if the rate changes while product rows stay untouched, why does an index on that UDF return wrong results? What design is needed instead?

### Exercise 16 — Unique Expression Index

Create a unique index on `lower(email)` in the lab, test inserting `'ANH@example.COM'` inside a savepoint, and observe SQLSTATE `23505`.

**Hint:** in real migrations, run a duplicate preflight check before building the unique index.

### Exercise 17 — NULL and Uniqueness

Suppose `email` is nullable. Can multiple `email = NULL` rows coexist under a default unique index on `lower(email)`? If missing emails are forbidden, what constraint is needed?

**Answer:** multiple `NULL`s can coexist; add `NOT NULL` when an email is mandatory.

### Exercise 18 — Partial Unique Index for Active Customers

Write:

~~~sql
CREATE UNIQUE INDEX ...
ON expr_idx_256.customers (
    expr_idx_256.normalize_email(email)
)
WHERE deleted_at IS NULL;
~~~

**Question:** why must you drop a full-table unique index if soft-deleted accounts should allow email reuse? Why might restoring an old deleted account be blocked?

### Exercise 19 — Predicate Implication

Two queries:

~~~sql
WHERE deleted_at IS NULL
  AND expr_idx_256.normalize_email(email) = 'abc@example.com'
~~~

and:

~~~sql
WHERE expr_idx_256.normalize_email(email) = 'abc@example.com'
~~~

Which query can use a partial index with `WHERE deleted_at IS NULL` as a complete source? Explain.

### Exercise 20 — Modifying a UDF

A team updates email normalization rules. Outline a migration plan covering duplicate preflight, v2 index/`REINDEX`, uniqueness verification, application rollout, and rollback.

**Never just run `CREATE OR REPLACE FUNCTION` and assume indexes updated.**

### Exercise 21 — Collation Upgrade

Query `pg_collation_actual_version` vs. `collversion` in the lab database.

**Question:** when versions diverge, why doesn't `REFRESH VERSION` fix old B-tree keys? How should you audit dependencies and `REINDEX`?

### Exercise 22 — Text Pattern Search

Distinguish three queries:

~~~sql
WHERE lower(display_name) = 'anh'
WHERE lower(display_name) LIKE 'anh%'
WHERE lower(display_name) LIKE '%anh%'
~~~

Match each with candidate B-tree, B-tree `text_pattern_ops`, or GIN trigram indexes. Why can't a standard B-tree accelerate mid-string substrings?

### Exercise 23 — Generated Column

Add `normalized_email GENERATED ALWAYS AS (lower(btrim(email))) STORED` in the lab database.

**Question:** what are its pros/cons compared to indexing `lower(btrim(email))` directly? Can a generated expression call a UDF depending on `now()`?

### Exercise 24 — HOT Updates

A table has an expression index on `lower(email)`. Two updates:

1. Change `display_name`, leaving `email` untouched.
2. Change `email`.

Which has better HOT update eligibility assuming no other index covers the changed column and free heap page space exists? Why do expression indexes still affect write workloads?

### Exercise 25 — CONCURRENTLY and Invalid Indexes

Explain why `CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block, when it is useful, and how to inspect `pg_index.indisvalid`/`indisready` after a failure.

### Exercise 26 — Catalog Index Expressions

From `pg_index`, use `pg_get_expr(indexprs, indrelid)` and `pg_get_expr(indpred, indrelid)` to separate expressions and partial predicates for indexes in the lab schema.

**Question:** do full-table indexes have `indpred` as `NULL`? Do plain column indexes have `indexprs` as `NULL`?

### Exercise 27 — Write Cost and Index-Only Scans

A 50-million-row table has 15 expression indexes and heavy `INSERT`/`UPDATE` traffic. Developers want 5 more expression indexes because “reads are sometimes faster.”

**Exercise:** propose the metrics to check: query frequency, selectivity, query latency, index size, TPS/commit latency, HOT ratio, `VACUUM`, WAL, `pg_stat_user_indexes`, and rollback plan.

### Exercise 28 — Distinguishing Volatility from Parallel Safety

In `pg_proc`, a function has `provolatile = 's'` and `proparallel = 's'`.

**Question:** can it be used in an expression index? Why doesn't “Parallel Safe” imply “Immutable”?

**Answer:** no; index keys require `IMMUTABLE`, not merely safety inside parallel workers.

### Exercise 29 — JSONB Casts and Malformed Data

Plan creating an index `((payload ->> 'customer_id')::bigint)`. What happens if one JSON row contains `"customer_id":"not-a-number"`? Why is validation needed before building the index and before inserting?

### Exercise 30 — Comprehensive Code Review

A developer proposes:

~~~sql
CREATE FUNCTION app.discounted_price(p numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p * (1 - current_setting('app.discount')::numeric)
$$;

CREATE INDEX idx_discounted
ON products (app.discounted_price(price));
~~~

Explain:

1. Is this function truly immutable if `app.discount` configuration changes?
2. Why does marking `IMMUTABLE` cause the index to hold stale keys?
3. When should discounted prices be calculated and how should they be stored?
4. Should discounts come from a versioned policy table?
5. If pricing rules change, what is the migration/`REINDEX` or schema plan?
6. Which queries truly need a discounted-price index vs. indexing `price` directly after transforming filter thresholds?

**Guided answer:** the function depends on session configuration and is not truly `IMMUTABLE`; switch to a design independent of hidden parameters, or store/version discounted prices explicitly and index a stable stored value.

## 31. Production Workflow for Choosing Expression Indexes

Checklist before adding a production expression index:

1. **Identify slow queries** and inspect exact expressions used.
2. **Verify data types** of inputs/outputs, implicit casts, and collations.
3. **Audit volatility** of every function and operator, including overloads and UDFs.
4. **Verify semantics** for `NULL`s, whitespace, Unicode, timezones, and malformed JSON.
5. **Check whether a plain column index suffices** by rewriting filters into range predicates.
6. **Pick the right index method/opclass**: B-tree for equality/range, GIN for containment/trigrams, BRIN for physically correlated ranges.
7. **Choose full vs. partial vs. unique** based on business rules and query predicates.
8. **Run preflight checks** for duplicates and cast errors before building unique/expression indexes.
9. **Estimate write overhead**, bloat, WAL, and HOT update impact.
10. **Measure `EXPLAIN`/`EXPLAIN ANALYZE` on representative data**, not tiny lab tables.
11. **Plan online rollout**: locking, `CONCURRENTLY`, invalid index handling, rollback.
12. **Document dependencies in migrations**: UDF versions, collations, extensions, timezone assumptions.
13. **Monitor usage and performance post-rollout**, not only at creation time.
14. **Prepare a `REINDEX`/migration runbook** if functions or collations ever change.

### 31.1. Quick Decision Matrix

| Goal | Starting Choice |
| --- | --- |
| Case-insensitive email login | Unique expression index on defined canonicalization, or normalized column |
| Filter orders within the last 7 days | B-tree on `timestamptz` column + range predicate |
| Query one text field from JSONB | B-tree expression on `payload ->> 'field'` |
| Query JSONB object containment | GIN on JSONB with matching opclass |
| Filter line total `unit_price * quantity` | B-tree expression index if workload is large/selective enough |
| Normalize via mutable rates or dynamic rules | Materialized/versioned stored value, never fake `IMMUTABLE` |
| Substring `%keyword%` search | Evaluate `pg_trgm` with GIN/GiST |
| Unique only among non-deleted rows | Unique partial expression index aligned with business rules |

## 32. Official PostgreSQL Documentation

Always verify against your exact PostgreSQL version:

- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): mechanics and examples (`lower(col)`, `(col1 + col2)`, unique expression indexes).
- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): `VOLATILE`, `STABLE`, and `IMMUTABLE` semantics and impact on planner/cached plans.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): expression syntax, index methods, `WHERE`, `INCLUDE`, `CONCURRENTLY`, and restrictions.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): predicate implication, subset uniqueness, and planner limitations.
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): role of B-tree key ordering.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): B-tree, Hash, GiST, SP-GiST, GIN, BRIN, and supported operators.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): generated expression rules and limits.
- [REINDEX](https://www.postgresql.org/docs/current/sql-reindex.html): rebuilding indexes and concurrent variants.
- [The System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): `provolatile`, `proparallel`, and function metadata.
- [The System Catalog pg_index](https://www.postgresql.org/docs/current/catalog-pg-index.html): `indexprs`, `indpred`, `indisvalid`, `indisready`.
- [Collation Support](https://www.postgresql.org/docs/current/collation.html): collation rules and version-upgrade risks.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): reading plans and understanding `EXPLAIN ANALYZE` execution effects.
- [pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html): trigram GIN/GiST operator classes when the extension is available.

`/docs/current/` points to the latest release. When operating PostgreSQL 14, 15, 16, 17, 18, or another fixed release, use **that exact version's URL** to verify features, syntax, and limits.

## 33. Summary

**Expression indexes** let PostgreSQL index values computed from one or more columns—such as `lower(email)`, `unit_price * quantity`, and `payload ->> 'customer_id'`. They accelerate filtering, range queries, sorting, and **uniqueness over normalized values**; combined with partial predicates, they can enforce uniqueness exclusively across active rows.

**The central requirement is immutability:** functions and operators inside index keys or predicates must have **`IMMUTABLE`** semantics. `STABLE` holds only within a single statement/transaction; `VOLATILE` can vary across calls. Never force clock functions, session timezones, lookup tables, mutable dictionaries, or runtime settings into `IMMUTABLE` wrappers merely to satisfy `CREATE INDEX`.

An expression index that is **valid today** also demands maintenance whenever UDF logic or collation versions evolve. Stored index keys are not recomputed automatically when a function body changes—requiring **`REINDEX`, migrations, duplicate preflight checks, and coordinated rollouts**. Expression indexes also add write overhead, restrict HOT updates, and may be skipped by the planner on small tables or mismatched predicates.

**Guiding rule:** start by defining a **genuinely stable business expression**, then select the right index method, unique/partial predicates, and data types; verify volatility in `pg_proc`, inspect definitions via `pg_index`/`pg_indexes`, measure with `EXPLAIN`, and manage the function/collation lifecycle. Understanding function requirements matters far more than simply creating an index that appears to work: **the index must always preserve the exact meaning of the data your queries look for**.
