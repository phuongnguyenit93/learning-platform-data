# Reducing Data Read with Necessary Columns and Selective Predicates in PostgreSQL

A query returning 20 rows is not necessarily a lightweight query. PostgreSQL may have to read hundreds of thousands of rows, check predicates on every row, sort the result, and only then return those 20 rows. Conversely, a query asking for 20 rows belonging to a specific customer can locate them via an index without scanning the entire table.

Two changes often deliver major gains in query optimization:

1. **Fetch only the columns you actually need** instead of defaulting to `SELECT *`.
2. **Narrow the set of rows examined and returned** using selective `WHERE` predicates written so PostgreSQL can exploit indexes, statistics, and data-reduction mechanisms.

For example, a list screen displays only order ID, creation date, status, and total amount:

~~~sql
-- May fetch many unused columns, including large text fields.
SELECT *
FROM orders
ORDER BY created_at DESC
LIMIT 20;
~~~

Compared to:

~~~sql
-- Expresses the exact requirements of the screen.
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

The second query has a lean **projection** (column list) and a specific **predicate** (filter condition). With an appropriate index, PostgreSQL can bound index entries, heap rows, and data sent to the client.

However, distinguish three things:

- **Logical data:** the rows and columns the SQL statement asks to process and return.
- **Physical data PostgreSQL must access:** index pages, heap pages, TOAST, buffer cache, or storage.
- **Data transferred over the network and processed in the application:** row counts, bytes, deserialized objects, generated JSON, etc.

Reducing columns in `SELECT` **does not automatically** reduce the number of heap pages read if PostgreSQL still executes a full-table `Seq Scan`. The value of selecting exact columns also lies in shrinking output tuple size, avoiding processing wide values, cutting bandwidth, enabling **index-only scans**, and eliminating unnecessary data in the application tier.

This lesson moves from fundamentals to PostgreSQL practice: `SELECT`-lists, selective `WHERE` clauses, **sargable predicates**, B-trees and covering indexes, partial indexes, JOINs, `ORDER BY ... LIMIT`, pagination, partition pruning, `EXPLAIN (ANALYZE, BUFFERS)`, statistics, and exercises.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain why `SELECT *` is often unsuitable for APIs and reports that use only a subset of columns.
2. Distinguish **projection**, **filtering**, and **actual pages/buffers read**.
3. Use `EXPLAIN (ANALYZE, BUFFERS)` to read `rows`, `width`, `Index Cond`, `Filter`, `Rows Removed by Filter`, and `Buffers`.
4. Estimate predicate *selectivity* and recognize predicates that can use B-tree indexes.
5. Rewrite time predicates, expressions, `LIKE`, and `OR` to align with existing indexes.
6. Choose composite indexes and `INCLUDE` columns to support filtering, sorting, and returning specific columns.
7. Reduce intermediate row counts in JOINs and avoid unnecessary row multiplication.
8. Design `LIMIT` queries and keyset pagination without mistakenly assuming `LIMIT` automatically reduces data read.
9. Know when PostgreSQL intentionally chooses `Seq Scan` even when an index exists.
10. Test changes and re-measure on representative data, statistics, and workloads.

## 2. Two Foundational Operations: Projection and Selection

In the relational model:

- **Projection:** choosing which attributes/columns to display or compute with.
- **Selection:** choosing which rows satisfy a predicate.

In SQL, the corresponding idea is:

~~~sql
SELECT order_id, created_at, total_amount   -- projection
FROM opt_lab.orders
WHERE customer_id = 42                      -- selection
  AND status = 'paid';
~~~

### 2.1. Data Across Layers

~~~text
PostgreSQL storage / buffer cache
          |
          v
    Scan / Index Scan
          |
       Filter
          |
    Join / Aggregate / Sort
          |
      Projection
          |
    Network / Driver
          |
       API / UI
~~~

This is only a conceptual diagram: PostgreSQL is not forced to process every SQL statement in that strict linear order. The planner can push predicates into scans, pick different join strategies, and evaluate sorts and expressions at appropriate nodes.

**The goal of optimization** is to avoid unnecessary work as early as possible while preserving exact result semantics.

### 2.2. Fast Queries Do Not Always Mean Using an Index

A `Seq Scan` on a table of a few dozen rows is usually much cheaper than traversing an index and fetching heap tuples one by one. An index helps when it **eliminates a substantial share of data** or provides query ordering, not as an end in itself.

## 3. Setting Up the Lab Dataset

The following examples target modern PostgreSQL in a test database. Create schemas and data only in an authorized environment; **never run data-generation scripts on production**.

### 3.1. Create Schema and Customers Table

~~~sql
CREATE SCHEMA opt_lab;

CREATE TABLE opt_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    region text NOT NULL,
    registered_at timestamptz NOT NULL
);
~~~

### 3.2. Create Products Table

~~~sql
CREATE TABLE opt_lab.products (
    product_id integer PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    product_name text NOT NULL,
    category text NOT NULL,
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    description text,
    attributes jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

`description` and `attributes` represent data that a product list screen may not need, whereas a product detail page does.

### 3.3. Create Orders Table

~~~sql
CREATE TABLE opt_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES opt_lab.customers(customer_id),
    product_id integer NOT NULL
        REFERENCES opt_lab.products(product_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL CHECK (
        status IN ('paid', 'shipped', 'cancelled')
    ),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    note text
);
~~~

Primary key and `UNIQUE` indexes backing constraints are created automatically. **Foreign keys do not automatically create indexes on referencing columns in the child table**, so `orders.customer_id` and `orders.product_id` do not get dedicated indexes merely from FK declarations.

### 3.4. Create 5,000 Customers

~~~sql
INSERT INTO opt_lab.customers (
    customer_id, full_name, email, region, registered_at
)
SELECT
    g,
    'Customer ' || g::text,
    'customer' || g::text || '@example.test',
    CASE (g % 4)
        WHEN 0 THEN 'north'
        WHEN 1 THEN 'south'
        WHEN 2 THEN 'central'
        ELSE 'other'
    END,
    TIMESTAMPTZ '2025-01-01 00:00:00+00'
      + g * INTERVAL '1 hour'
FROM generate_series(1, 5000) AS s(g);
~~~

### 3.5. Create 20,000 Products

~~~sql
INSERT INTO opt_lab.products (
    product_id, sku, product_name, category,
    price, description, attributes
)
SELECT
    g,
    'SKU-' || lpad(g::text, 6, '0'),
    'Product ' || g::text,
    CASE g % 4
        WHEN 0 THEN 'book'
        WHEN 1 THEN 'office'
        WHEN 2 THEN 'drink'
        ELSE 'electronics'
    END,
    (10000 + (g % 3000) * 100)::numeric(12, 2),
    repeat(
        'Detailed product description text. ',
        20
    ),
    jsonb_build_object(
        'brand', 'brand-' || (g % 30)::text,
        'warehouse', g % 12,
        'features', jsonb_build_array('standard', 'online')
    )
FROM generate_series(1, 20000) AS s(g);
~~~

The description text is repeated to illustrate long values. PostgreSQL may compress or TOAST values depending on actual size, so **do not assume every description occupies its own heap page**.

### 3.6. Create 60,000 Orders

~~~sql
INSERT INTO opt_lab.orders (
    order_id, customer_id, product_id, created_at,
    status, total_amount, note
)
SELECT
    g::bigint,
    ((g - 1) % 5000) + 1,
    ((g - 1) % 20000) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
      + g * INTERVAL '1 minute',
    CASE
        WHEN g % 10 BETWEEN 0 AND 6 THEN 'paid'
        WHEN g % 10 IN (7, 8) THEN 'shipped'
        ELSE 'cancelled'
    END,
    (20000 + (g % 1000) * 125)::numeric(12, 2),
    repeat('Order communication notes. ', 12)
FROM generate_series(1, 60000) AS s(g);
~~~

The dataset intentionally has:

- 5,000 customers.
- 20,000 products.
- 60,000 orders, with exactly **12 orders** per customer.
- Exactly **3 orders** per product.
- Roughly **70%** `paid` orders, **20%** `shipped`, and **10%** `cancelled`.
- Order dates spanning from early January into February 2026.

This is **formulaically uniform synthetic data**, not a reflection of real commerce data with skew, seasonality, and complex correlations.

### 3.7. Gather Statistics

~~~sql
ANALYZE opt_lab.customers;
ANALYZE opt_lab.products;
ANALYZE opt_lab.orders;
~~~

### 3.8. Verify Data Volume

~~~sql
SELECT COUNT(*) AS customers FROM opt_lab.customers;
SELECT COUNT(*) AS products FROM opt_lab.products;
SELECT COUNT(*) AS orders FROM opt_lab.orders;

SELECT status, COUNT(*) AS n
FROM opt_lab.orders
GROUP BY status
ORDER BY status;
~~~

Expected: `customers=5000`, `products=20000`, and `orders=60000`. By the generation formula, `paid=42000`, `shipped=12000`, and `cancelled=6000`.

## 4. What Does `SELECT *` Bring Along?

~~~sql
SELECT *
FROM opt_lab.products
WHERE product_id = 42;
~~~

This query requests **every current column in the table**:

~~~text
product_id
sku
product_name
category
price
description
attributes
~~~

Meanwhile, a product listing screen might display only:

~~~sql
SELECT product_id, sku, product_name, price
FROM opt_lab.products
WHERE product_id = 42;
~~~

### 4.1. Why Avoid `SELECT *` When Unneeded?

- **Network payload:** fewer columns can reduce bytes sent from server to client.
- **Driver and application:** fewer values to decode, allocate as objects, and serialize to JSON.
- **TOAST / wide values:** omitting large text/JSON columns avoids fetching or detoasting out-of-line values unnecessarily.
- **JOINs:** avoids carrying duplicate column names or bulky payloads through intermediate nodes.
- **Covering / index-only scan eligibility:** queries needing only indexed columns can skip many heap fetches when MVCC visibility allows.
- **API contract:** explicit column lists are more resilient when new or sensitive columns are added to the table.

### 4.2. Do Not Claim Fewer Columns = Fewer Heap Blocks

Suppose PostgreSQL chooses:

~~~text
Seq Scan on products
~~~

for both queries:

~~~sql
SELECT * FROM opt_lab.products;

SELECT product_id FROM opt_lab.products;
~~~

When scanning the entire relation sequentially, PostgreSQL still must **read the table's heap pages**. Selecting only `product_id` does not significantly reduce `shared read/hit`.

It can, however, cut output tuple construction, unnecessary detoasting/decoding of wide values, client processing, and network bytes. With a suitable index, the planner may also pick an **index-only scan** for narrow projections.

### 4.3. `SELECT *` Also Has Valid Uses

- Inspecting a complete row while debugging in a lab database.
- A detail page that genuinely displays every attribute.
- Small diagnostic checks not on a high-frequency path.

The problem is **fetching excess data on hot paths**, not that `*` syntax is inherently wrong.

## 5. Measuring Output Width with `EXPLAIN`

~~~sql
EXPLAIN
SELECT *
FROM opt_lab.products
WHERE product_id <= 100;

EXPLAIN
SELECT product_id, product_name, price
FROM opt_lab.products
WHERE product_id <= 100;
~~~

In the plan you may see:

~~~text
... (cost=... rows=... width=...)
~~~

`width` is the **planner's estimated average row size** in bytes for that node's output, not exact measured network bytes.

### 5.1. `width` Differs from Pages Read

If `width` drops from 180 to 40 when selecting fewer columns, that indicates a slimmer projected output. **Do not infer** that heap blocks read also dropped by a factor of `180/40`.

### 5.2. `width` Varies Across Plan Nodes

A scan node may pass extra columns up for filtering or joining while a parent node projects fewer columns. PostgreSQL prunes unneeded columns at each node. Read the **entire plan tree** to see where columns are used rather than checking only the root node's `width`.

## 6. Wide Columns, TOAST, and Projection Limits

PostgreSQL uses **TOAST** to handle large values of types such as `text` and `jsonb`; values may be compressed or stored out-of-line depending on storage settings and actual size.

~~~sql
SELECT product_id, product_name
FROM opt_lab.products
WHERE product_id = 42;
~~~

does not need to return `description` or `attributes`.

~~~sql
SELECT
    product_id,
    product_name,
    description,
    attributes
FROM opt_lab.products
WHERE product_id = 42;
~~~

requires those values to construct the result.

### 6.1. Large Values Are Not Always Read from TOAST

If a value is stored inline or compresses small enough inside the heap, access patterns differ from out-of-line TOAST storage. Savings from omitting wide columns **must be measured** on actual data and plans.

### 6.2. Functions on Wide Columns Still Force Processing Them

~~~sql
SELECT product_id
FROM opt_lab.products
WHERE length(description) > 500;
~~~

Even though only `product_id` is returned, the filter **must read/evaluate `description`** for examined rows. Trimming the `SELECT`-list alone does not eliminate work on columns referenced elsewhere in the query.

### 6.3. `ORDER BY` Also Needs the Data

~~~sql
SELECT product_id
FROM opt_lab.products
ORDER BY description
LIMIT 20;
~~~

Only one column is returned, yet PostgreSQL must still evaluate ordering on `description` unless a matching index path exists. **A narrow projection does not offset an expensive sort expression**.

## 7. What Is a Selective `WHERE`?

**Selectivity** represents the fraction of rows matching a predicate out of the relevant population:

\[
\text{selectivity}\approx
\frac{\text{rows matching predicate}}
{\text{rows examined in relevant population}}
\]

Examples on 60,000 orders:

~~~sql
SELECT *
FROM opt_lab.orders
WHERE order_id = 100;
~~~

matches **1 row** via the primary key—very high selectivity.

~~~sql
SELECT *
FROM opt_lab.orders
WHERE status = 'paid';
~~~

matches roughly **42,000/60,000 = 70%** of rows—relatively low selectivity.

### 7.1. “Having a `WHERE` Clause” Is Not Enough

The two predicates:

~~~sql
WHERE order_id = 100
~~~

and:

~~~sql
WHERE status = 'paid'
~~~

both use `WHERE`, yet their ability to **eliminate data** differs dramatically.

### 7.2. Selectivity Depends on Dataset and Parameters

`customer_id=42` in the lab returns 12 orders. In production, a few customers may have millions of orders while typical customers have only a handful. An index suited for small customers may not behave identically for mega-customers across every workload.

### 7.3. Selectivity Is Not Just Final Row Count

A predicate can return 10 rows while still scanning 60,000 rows:

~~~sql
WHERE lower(status) = 'paid'
  AND order_id < 11
~~~

What matters is not only **how many rows are output**, but **how much work PostgreSQL must do to find them**.

## 8. Three Levels of Measuring Data Processed

When reading a plan, distinguish:

1. **Rows returned:** rows passed by a node to its parent.
2. **Rows examined/filtered:** rows inspected; often inferred from `Rows Removed by Filter` combined with node output.
3. **Pages/blocks touched:** `Buffers: shared hit/read` and related counters.

Illustrative plan example:

~~~text
Seq Scan on orders
  (cost=0.00..1700.00 rows=12 width=24)
  (actual time=0.050..7.800 rows=12 loops=1)
  Filter: (customer_id = 42)
  Rows Removed by Filter: 59988
  Buffers: shared hit=900
~~~

**This is a hypothetical example**, not fixed lab output.

Meaning:

- The node returned **12** rows.
- It discarded **59,988** rows via the filter.
- It examined roughly **60,000** rows.
- `shared hit=900` counts block accesses in shared buffers, **not 900 rows**.

With a good index, the plan can change to:

~~~text
Index Scan using idx_orders_customer_created on orders
  (actual ... rows=12 loops=1)
  Index Cond: (customer_id = 42)
  Buffers: shared hit=...
~~~

The key difference is that the predicate **locates keys directly** rather than checking nearly every row in the table.

## 9. `EXPLAIN`: `Index Cond` vs `Filter`

Consider:

~~~sql
SELECT order_id, created_at
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

With a suitable index, the plan may contain:

~~~text
Index Cond: (customer_id = 42)
~~~

`Index Cond` shows the condition used by the index scan during key lookup/traversal.

### 9.1. `Filter`

~~~text
Filter: (status = 'paid')
Rows Removed by Filter: 5
~~~

When a predicate appears under `Filter` on a scan, it is checked against tuples/outputs already retrieved by that scan; it does not necessarily narrow the **index key range scanned** the way `Index Cond` does.

### 9.2. `Index Cond` Does Not Guarantee All Conditions Are Filtered in the Index

A plan can include both:

~~~text
Index Cond: (customer_id = 42)
Filter: (status = 'paid')
~~~

The index finds customer 42's orders, and then `status` is filtered. This can still be an excellent plan if the customer has only a few orders.

### 9.3. `Filter` Can Also Appear on Other Nodes

`Filter` appears on Seq Scan, Index Scan, Join, Aggregate, or other nodes depending on the expression. Inspect **which node holds the Filter**, rather than seeing the word `Filter` and assuming a full table scan.

### 9.4. Confirm with `BUFFERS`

Moving a predicate from a full-table `Filter` into `Index Cond` can slash block accesses. Yet if the predicate matches 70% of rows, the planner may still reasonably pick a Seq Scan.

## 10. Creating Indexes for Selective Predicates

~~~sql
CREATE INDEX idx_orders_customer
ON opt_lab.orders (customer_id);

ANALYZE opt_lab.orders;
~~~

Then test:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

The index allows PostgreSQL to locate customer 42's ~12 orders without scanning all 60,000 orders.

### 10.1. Why Not Index Every Column?

Indexes add costs:

- `INSERT`, `UPDATE`, and `DELETE` must maintain affected indexes.
- Disk space and cache footprint.
- Maintenance/VACUUM overhead and impact on write throughput.
- Index build/rebuild time and potential locking during migrations.

Create indexes only when real queries, selectivity, and execution frequency justify the trade-off.

### 10.2. Low-Cardinality Columns

~~~sql
CREATE INDEX idx_orders_status
ON opt_lab.orders (status);
~~~

`status` has only three values and `paid` accounts for 70%. For `WHERE status='paid'`, PostgreSQL often **rightly chooses `Seq Scan`** instead of traversing an index only to touch most heap rows.

For `status='cancelled'` at ~10%, the index may look more attractive, though it still depends on table layout, clustering, cache, and selected columns.

**An index's existence does not mean every filter value benefits from it.**

## 11. SARGable Predicates: Writing Conditions That Can Use Indexes

*SARGable* is practical shorthand for predicates that an access method can turn into a lookup against an appropriate index structure.

Example on B-tree index `orders(created_at)`:

~~~sql
CREATE INDEX idx_orders_created
ON opt_lab.orders (created_at);
~~~

Index-friendly predicate:

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00'
~~~

Because the comparison sits directly on `created_at`, PostgreSQL can use a B-tree range scan.

### 11.1. Wrapping a Column in a Function Can Block Standard Indexes

~~~sql
WHERE created_at::date = DATE '2026-02-01'
~~~

The expression operates on the **date converted from the timestamp**, not directly on the raw `created_at` index keys. The planner will not automatically convert this into a timestamp range to use the index above.

### 11.2. Rewrite as a Half-Open Range

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00';
~~~

The **[start, end)** interval is advantageous because:

- It captures all sub-second fractions within the day.
- You never have to hand-craft `23:59:59.999999`.
- Consecutive day intervals never overlap.
- It aligns with a B-tree range scan on `created_at`.

### 11.3. Watch Out for Time Zones with `timestamptz`

`created_at::date` depends on the **session time zone** for `timestamptz`, whereas the `+00` literals above specify a UTC day. The two forms are equivalent only if the business requirement truly means a **UTC day** and boundaries are computed in the right time zone.

For a user's local calendar day, the application should compute the **two UTC instants corresponding to midnight at the start and next day in that time zone**, accounting for DST transitions in DST zones.

Never rewrite a predicate in a way that silently changes the business date meaning.

## 12. Functions on Columns: When to Use an Expression Index?

Example case-insensitive product lookup:

~~~sql
SELECT product_id, product_name
FROM opt_lab.products
WHERE lower(product_name) = 'product 42';
~~~

A standard index on `product_name` cannot automatically serve lookups on `lower(product_name)`.

One option:

~~~sql
CREATE INDEX idx_products_lower_name
ON opt_lab.products (lower(product_name));
~~~

Then:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_id, product_name
FROM opt_lab.products
WHERE lower(product_name) = 'product 42';
~~~

### 12.1. Look for Simpler Rewrites First

If a condition can be written as a direct comparison on the column, do not add an expression index just to preserve an unnecessarily complex expression.

### 12.2. Expression Indexes Have Maintenance Costs

PostgreSQL must evaluate the expression during index creation and on affected row updates. In addition, the expression must satisfy *immutability* requirements and match query semantics.

### 12.3. The Query Must Match the Expression

An index on `lower(product_name)` matches `WHERE lower(product_name) = ...`; there is no rule making it automatically handle arbitrary `ILIKE`, `LIKE`, or other string transformations.

## 13. `LIKE`, Prefixes, and Leading Wildcards

Two conditions:

~~~sql
WHERE sku LIKE 'SKU-0001%'
~~~

and:

~~~sql
WHERE sku LIKE '%0001%'
~~~

differ in B-tree indexability:

- `'SKU-0001%'` has a **fixed prefix**.
- `'%0001%'` begins with a wildcard, offering no simple B-tree prefix range.

### 13.1. Collation and `pattern_ops`

Under some non-`C` locales, a default text B-tree may not optimize prefix `LIKE` well. Consider:

~~~sql
CREATE INDEX idx_products_sku_prefix
ON opt_lab.products (sku text_pattern_ops);
~~~

If the default index already uses the `C` collation and a compatible operator class, prefix search may already work. **Do not create duplicate indexes before checking `EXPLAIN` and collation**.

### 13.2. Substring Search

For:

~~~sql
WHERE product_name ILIKE '%product%'
~~~

a trigram index from the `pg_trgm` extension may be an option:

~~~sql
-- Run only in the lab if installing the extension is permitted.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_products_name_trgm
ON opt_lab.products
USING gin (product_name gin_trgm_ops);
~~~

Trigrams are not guaranteed to be fast for every pattern (especially very short ones) and increase write cost and index size. If the workload needs linguistic full-text search, consider a dedicated full-text search mechanism.

### 13.3. Never Alter `LIKE` Semantics Just to Hit an Index

`LIKE 'ABC%'` differs from `LIKE '%ABC%'`. Never drop a leading wildcard just to make a query faster when the business requirement is substring matching.

## 14. Avoid Unnecessary Casts on Key Columns

Suppose `order_id` is `bigint`:

~~~sql
-- Avoid casting to text just to compare IDs.
SELECT order_id
FROM opt_lab.orders
WHERE order_id::text = '100';
~~~

Instead of:

~~~sql
SELECT order_id
FROM opt_lab.orders
WHERE order_id = 100::bigint;
~~~

In the second query, PostgreSQL can use the numeric B-tree primary-key index.

### 14.1. Non-Sargable Conditions Do Not Always Mean `Seq Scan`

PostgreSQL can sometimes use another index, bitmap scan, expression index, or expression optimization; never claim that every function or cast on a column forces a full scan.

Rule of thumb: **keep predicates as close to direct comparisons on index keys as possible**, and verify the plan.

### 14.2. Check Application Parameter Types

Prepared statements using parameters must bind the right types:

~~~sql
PREPARE get_order(bigint) AS
SELECT order_id, customer_id, total_amount
FROM opt_lab.orders
WHERE order_id = $1;
~~~

Numeric-to-numeric comparisons are far more predictable than declaring IDs as text and casting the column in `WHERE`.

## 15. `OR`, `IN`, and Filtering Multiple Values

A query:

~~~sql
SELECT order_id, status
FROM opt_lab.orders
WHERE status = 'paid'
   OR status = 'shipped';
~~~

is logically equivalent to:

~~~sql
SELECT order_id, status
FROM opt_lab.orders
WHERE status IN ('paid', 'shipped');
~~~

Yet `IN` is no magic wand to speed up every query. Those two values here cover roughly **90%** of the table, so a Seq Scan may be entirely reasonable.

### 15.1. `OR` Across Multiple Columns

~~~sql
SELECT order_id
FROM opt_lab.orders
WHERE customer_id = 42
   OR product_id = 17;
~~~

PostgreSQL may use a **BitmapOr** combining matching indexes, or pick another scan. This depends on selectivity and available indexes.

### 15.2. When Can Splitting with `UNION` Help?

Sometimes splitting two highly selective branches with `UNION`/`UNION ALL` gives the planner better options. However:

- `UNION` deduplicates rows, adding extra work.
- `UNION ALL` preserves duplicates, which can change results compared to `OR` if a row satisfies both branches.
- Not every `OR` should be rewritten.

Preserve semantics and measure against the workload.

## 16. `NULL` and Selective Predicates

~~~sql
WHERE note IS NULL
~~~

and:

~~~sql
WHERE note = NULL
~~~

are **different**. In SQL, comparing `= NULL` yields unknown and does not select NULL rows as intended.

### 16.1. `IS NULL` Can Use an Index

PostgreSQL B-trees can store and search for NULLs under appropriate conditions; `WHERE note IS NULL` does not always force a Seq Scan.

### 16.2. `COALESCE` on a Column Changes the Expression

~~~sql
WHERE COALESCE(note, '') = ''
~~~

is not identical to:

~~~sql
WHERE note IS NULL
~~~

because the first selects both empty strings and NULLs. If business logic wants only NULL, write `IS NULL`. If it wants both, write explicitly:

~~~sql
WHERE note IS NULL OR note = ''
~~~

and evaluate matching indexes/plans without changing meaning just to “make an index fit.”

## 17. Composite Indexes: Combining `WHERE` and `ORDER BY`

A customer's order history page:

~~~sql
SELECT
    order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

A properly ordered index:

~~~sql
CREATE INDEX idx_orders_customer_created
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

### 17.1. Why That Column Order?

1. `customer_id` is an **equality** predicate.
2. Once scoped to one customer, `created_at DESC` provides the desired order.
3. `order_id DESC` serves as a tie-breaker when two orders share the same timestamp.

With this index, PostgreSQL can read the customer's newest orders in index order and **stop early** once `LIMIT` is reached.

### 17.2. You Don't Always Have to Add `DESC`

B-trees can scan forward or backward. When multiple columns mix sort directions or NULL placements, declaring matching directions matters more. For `ORDER BY created_at DESC, order_id DESC`, an index with both descending is straightforward and clear.

### 17.3. If You Also Need to Filter by `status`

~~~sql
SELECT order_id, created_at, status
FROM opt_lab.orders
WHERE customer_id = 42
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Consider:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON opt_lab.orders (
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

When the query has equality on both `customer_id` and `status`, the index narrows to that slice and returns rows already ordered by time.

### 17.4. Design Indexes for the Workload, Not a Single Query

If most screens filter by customer **without filtering `status`**, `(customer_id,status,created_at)` does not directly supply a single `created_at` ordering across all statuses of a customer because `status` precedes `created_at`.

Two similar indexes can help two query patterns, at the cost of extra write amplification. Weigh frequency, data size, and real queries before keeping both.

## 18. `INCLUDE` and Index-Only Scans

The order history query needs `status` and `total_amount` even though it filters/sorts mainly on other keys:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

You can create a covering index:

~~~sql
CREATE INDEX idx_orders_customer_cover
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, total_amount);
~~~

### 18.1. Key Columns vs Included Columns

| Column | Role |
| --- | --- |
| `customer_id` | Equality search key |
| `created_at` | Ordering key |
| `order_id` | Tie-breaker / ordering key |
| `status` | Output payload; not a search key in this index |
| `total_amount` | Output payload |

`INCLUDE` stores values inside the index, yet **does not** make `status` an index search key the way a key column is.

### 18.2. When Is an Index-Only Scan Possible?

PostgreSQL can use `Index Only Scan` when:

- The access method supports it.
- All required columns/expressions can be retrieved from the index under a suitable plan.
- Visibility map and MVCC state allow skipping or minimizing heap reads.
- The planner judges it cost-effective.

### 18.3. `Heap Fetches`

A plan may show:

~~~text
Index Only Scan using idx_orders_customer_cover ...
  Heap Fetches: 0
~~~

This means **in that measurement**, no heap accesses were needed to verify visibility for the returned tuples. Another `Index Only Scan` can still report **Heap Fetches > 0**, especially when the table is frequently updated and pages lack all-visible bits in the visibility map.

### 18.4. Do Not `INCLUDE` Every Column

Adding payload columns bloats the index, consumes buffer cache, and increases write costs. Wide values can also hit index tuple size limits. Only `INCLUDE` essential columns frequently needed by hot queries.

## 19. Partial Indexes for the Subset Actually Needed

If most queries target recent `paid` orders rather than all statuses:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON opt_lab.orders (
    created_at DESC,
    order_id DESC
)
WHERE status = 'paid';
~~~

This index contains only rows satisfying `status='paid'`, not the entire table.

Matching query:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 19.1. Advantages

A partial index can be much smaller than a full index with the same keys when the predicate selects a small slice of the table, reducing maintenance cost for rows outside the predicate.

### 19.2. The Lab Predicate Is Not Very Selective

`paid` makes up **70%** of orders, so this partial index won't always yield dramatic savings here. A partial index on a rarer status or a real dataset where only a few percent of rows are “active” can behave very differently.

Do not take the lab example as proof that partial indexes are always tiny or fast.

### 19.3. The Query Must Prove the Predicate

PostgreSQL can use a partial index only when the planner proves the query condition **implies** the index predicate.

~~~sql
WHERE status = 'paid'
~~~

is straightforward.

However, a prepared statement:

~~~sql
WHERE status = $1
~~~

especially with a **generic plan** unaware of `$1`'s value, **cannot prove** `status='paid'` for every execution. Never design an index assuming every parameter is substituted as a literal at planning time.

### 19.4. Do Not Use a Partial Index to Filter Out Business Data

A partial index only changes access structures; **it does not delete rows outside its predicate**. Queries not matching the predicate will simply use another access path to return accurate results.

## 20. `WHERE` + `LIMIT` Does Not Guarantee Reading Few Rows

Compare two queries:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

and:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE status = 'paid'
ORDER BY total_amount DESC
LIMIT 10;
~~~

The first query can use `(customer_id,created_at,order_id)` to scan and stop early. The second, lacking an index ordered by price, may have to inspect **many paid orders** before selecting the top 10.

### 20.1. Reading a `Sort` Plan

Illustrative example:

~~~text
Limit
  (actual ... rows=10 loops=1)
  -> Sort
       (actual ... rows=10 loops=1)
       Sort Key: total_amount DESC
       Sort Method: top-N heapsort
       -> Seq Scan on orders
            (actual ... rows=42000 loops=1)
            Filter: (status = 'paid')
            Rows Removed by Filter: 18000
~~~

`Sort actual rows=10` **does not mean it only examined 10 rows**: its child fed ~42,000 rows, and `Sort` kept only the top-N requested by its parent.

### 20.2. Index Supporting Both Filter and Order

A candidate index if this query is very common:

~~~sql
CREATE INDEX idx_orders_status_amount
ON opt_lab.orders (
    status,
    total_amount DESC,
    order_id DESC
);
~~~

Then the query can pull the top-N within `status` already sorted by amount. However, if a query orders by `total_amount` without filtering `status`, the leading `status` column prevents the index from providing global price ordering.

## 21. Pagination: `OFFSET` Can Force Walking Past Many Rows

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 1000;
~~~

To return 20 rows at a deep offset, PostgreSQL generally still has to process/walk past **all preceding rows before `OFFSET`** as dictated by the plan. `LIMIT 20` does not skip the first 1,000 rows for free.

### 21.1. Keyset Pagination

For the next page, if the client retains the last `created_at` and `order_id` of the previous page:

~~~sql
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
  AND (created_at, order_id)
      < (
          TIMESTAMPTZ '2026-02-01 12:00:00+00',
          45000::bigint
        )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

With **two NOT NULL columns** both sorted descending, the tuple comparison `<` defines the next-page boundary cleanly and matches `(customer_id,created_at DESC,order_id DESC)`.

### 21.2. Cursors Must Come from Real Results

The two values above are only examples. In a real API, take them from the **last row of the previous page**, never guess them.

### 21.3. Keyset Trade-Offs

- Requires deterministic ordering and a tie-breaker key.
- Handling NULLs and mixed ASC/DESC directions requires more careful cursor predicates.
- Does not directly support jumping to “page 500” like `OFFSET`.
- Concurrent data changes can still affect pagination UX, though keyset avoids many deep-`OFFSET` issues.

### 21.4. Narrow Column Selection Still Matters

If the client displays 20 rows and four columns, do not fetch a wide `note` column or perform a heavy `JOIN` for data unused on the listing view.

## 22. JOINs: Filter on the Right Side and Avoid Excess Columns

An API returning a customer's orders may need the customer's name and order amount:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.full_name
FROM opt_lab.orders AS o
JOIN opt_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id = 42
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

No need for:

~~~sql
SELECT o.*, c.*
~~~

if the screen only uses four columns.

### 22.1. Which Table Gets Filtered?

`o.customer_id = 42` is highly selective. PostgreSQL can use the index on `orders`, then look up one customer via its primary key. The query does not have to scan and join all 60,000 orders with 5,000 customers.

### 22.2. Writing `WHERE` After `JOIN` Does Not Mean Filtering After Joining Everything

With an **INNER JOIN** and safe predicates, the planner can usually push filters down to the appropriate scans before joining. Never assume the engine always materializes the full join before evaluating `WHERE` simply because SQL puts `JOIN` before `WHERE`.

### 22.3. `OUTER JOIN` Must Preserve Semantics

Example:

~~~sql
SELECT c.customer_id, o.order_id
FROM opt_lab.customers AS c
LEFT JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
WHERE c.customer_id = 42;
~~~

preserves customer 42 even if there are no paid orders (unmatched case).

By contrast:

~~~sql
SELECT c.customer_id, o.order_id
FROM opt_lab.customers AS c
LEFT JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 42
  AND o.status = 'paid';
~~~

eliminates rows where `o.status IS NULL`, effectively turning the `LEFT JOIN` into an `INNER JOIN` with respect to that condition.

**Never casually move predicates between `WHERE` and `ON` across an outer join hoping to make it faster.**

## 23. Multi-Table JOINs and the Risk of Row Multiplication

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    p.product_name
FROM opt_lab.customers AS c
JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
JOIN opt_lab.products AS p
  ON p.product_id = o.product_id
WHERE c.customer_id = 42;
~~~

In the lab, customer 42 has 12 orders and each order points to one product, so the result is 12 rows.

### 23.1. When Child Tables Have Multiple Rows per Order

When adding `order_lines` and `order_events`, joining two one-to-many relations onto the same order produces a Cartesian product per order:

~~~text
1 order has:
  5 line items
  10 events

JOIN both tables -> potentially 5 × 10 = 50 rows
~~~

Consequences:

- Far more intermediate rows than needed.
- Duplicated data in the result.
- Expensive sorts and aggregations.
- Risk of miscalculating sums if cardinality is misunderstood.

### 23.2. `EXISTS` When You Only Need Existence of Related Records

Instead of joining and then deduplicating child rows:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM opt_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM opt_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
~~~

`EXISTS` expresses “at least one paid order exists,” letting the planner use a **semijoin** or existence probe without multiplying child rows into the output.

### 23.3. `DISTINCT` Is Not a Cure for Wrong Joins

~~~sql
SELECT DISTINCT c.customer_id
FROM opt_lab.customers AS c
JOIN opt_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'paid';
~~~

may return the right IDs, yet still has to process all joined rows before deduplicating. When the intent is existence, `EXISTS` states it more clearly—though never guarantee it is always faster in every workload without measuring.

## 24. Filtering Before Grouping

Suppose you want total paid order amount for a customer in February:

~~~sql
SELECT
    customer_id,
    SUM(total_amount) AS total_paid
FROM opt_lab.orders
WHERE customer_id = 42
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
GROUP BY customer_id;
~~~

`WHERE` reduces rows before entering `GROUP BY`, so the aggregate processes only the necessary subset.

### 24.1. `HAVING` Does Not Replace `WHERE`

~~~sql
SELECT customer_id, COUNT(*) AS n
FROM opt_lab.orders
GROUP BY customer_id
HAVING COUNT(*) >= 10;
~~~

`HAVING` filters **groups after aggregation**. To count only paid orders, put that condition in `WHERE`:

~~~sql
SELECT customer_id, COUNT(*) AS n_paid
FROM opt_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
HAVING COUNT(*) >= 10;
~~~

The two clauses solve different problems. Never move row-level conditions across `WHERE` and `HAVING` in a way that changes results.

### 24.2. PostgreSQL Supports `FILTER` in Aggregates

~~~sql
SELECT
    customer_id,
    COUNT(*) FILTER (WHERE status = 'paid') AS n_paid,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS n_cancelled
FROM opt_lab.orders
WHERE customer_id = 42
GROUP BY customer_id;
~~~

`FILTER` is handy for computing multiple conditional aggregates over the same input set; it does not narrow the scan the way `WHERE status='paid'` does if other statuses are still needed.

## 25. Predicate Pushdown and CTEs

The PostgreSQL planner can push safe predicates down near the scan to avoid building large intermediate sets.

### 25.1. CTEs Are Not Automatically Optimization Barriers

~~~sql
WITH recent AS (
    SELECT order_id, customer_id, created_at, status
    FROM opt_lab.orders
)
SELECT order_id, created_at
FROM recent
WHERE customer_id = 42;
~~~

In modern PostgreSQL, a non-recursive CTE without volatile side effects referenced once can usually be **inlined/folded** into the main query for joint optimization.

### 25.2. `MATERIALIZED` Changes Optimization Opportunities

~~~sql
WITH recent AS MATERIALIZED (
    SELECT order_id, customer_id, created_at, status
    FROM opt_lab.orders
)
SELECT order_id, created_at
FROM recent
WHERE customer_id = 42;
~~~

`MATERIALIZED` intentionally creates a materialization boundary; outer query predicates generally cannot be pushed down into the CTE scan. This can force processing huge numbers of rows just to pick 12 at the end.

### 25.3. Do Not Treat Every `MATERIALIZED` as Wrong

Materialization helps when a result is reused multiple times or an expensive computation must run once. Decide from real queries and plans; **do not blindly remove `MATERIALIZED`**.

### 25.4. Put Filters Early When Expressing Intent

When logic allows:

~~~sql
WITH recent AS MATERIALIZED (
    SELECT order_id, customer_id, created_at, status
    FROM opt_lab.orders
    WHERE customer_id = 42
)
SELECT order_id, created_at
FROM recent;
~~~

places the scope filter inside the CTE, avoiding materializing 60,000 orders when only one customer is needed.

## 26. Partition Pruning: Skipping Unrelated Partitions

On massive tables **partitioned by time**, PostgreSQL can prune partitions outside the query's range, shrinking the data scanned.

Concise lab definition example:

~~~sql
CREATE TABLE opt_lab.events_by_month (
    event_id bigint NOT NULL,
    created_at timestamptz NOT NULL,
    event_type text NOT NULL,
    payload jsonb
) PARTITION BY RANGE (created_at);

CREATE TABLE opt_lab.events_2026_01
PARTITION OF opt_lab.events_by_month
FOR VALUES FROM ('2026-01-01 00:00:00+00')
         TO ('2026-02-01 00:00:00+00');

CREATE TABLE opt_lab.events_2026_02
PARTITION OF opt_lab.events_by_month
FOR VALUES FROM ('2026-02-01 00:00:00+00')
         TO ('2026-03-01 00:00:00+00');
~~~

### 26.1. Query Using the Partition Key Directly

~~~sql
EXPLAIN
SELECT event_id, event_type
FROM opt_lab.events_by_month
WHERE created_at >= TIMESTAMPTZ '2026-02-10 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-11 00:00:00+00';
~~~

The planner can prune away unrelated partitions and inspect only February's partition.

### 26.2. Functions Wrapping the Partition Key

~~~sql
WHERE created_at::date = DATE '2026-02-10'
~~~

does not enable pruning as reliably as a direct range condition on the partition key—and with `timestamptz`, time zone also comes into play.

### 26.3. Partitioning Does Not Replace Indexes for Every Query

If February's partition still holds hundreds of millions of rows, a single-day query still needs indexes **inside the partition** or another strategy. Pruning reduces **which partitions** are touched, not necessarily all remaining scan work.

### 26.4. Lab Data Limitation

The example events table has no inserted rows. `EXPLAIN` demonstrates partition pruning from predicates; timing or `BUFFERS` on an empty table is not evidence of real-world speedup.

## 27. `COUNT(*)` Is Not a Free Row Count

~~~sql
SELECT COUNT(*)
FROM opt_lab.orders;
~~~

Under PostgreSQL MVCC, an exact count of all rows must verify snapshot visibility and typically scan an appropriate structure. It cannot simply return an instant exact count from metadata.

### 27.1. Counting a Small Subset

~~~sql
SELECT COUNT(*)
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

can benefit from an index on `customer_id`, since it only needs to locate matching entries and check visibility.

### 27.2. Fast Estimates Differ from Exact Counts

~~~sql
SELECT reltuples::bigint AS estimated_rows
FROM pg_class
WHERE oid = 'opt_lab.orders'::regclass;
~~~

`reltuples` is an **estimate** maintained by statistics/catalog updates, not guaranteed to equal `COUNT(*)` at the current snapshot.

### 27.3. Pagination APIs

Not every page request needs to execute:

~~~sql
SELECT COUNT(*) FROM huge_table;
~~~

if the UI only needs to know “is there a next page?” Fetching `page_size + 1` rows with the right filter and sort reveals whether another page exists while keeping desired UX semantics.

## 28. Selecting the Right Columns at the Application Layer

SQL is not the only place to trim columns. ORMs and APIs should also avoid **fetching an entire entity graph** when an endpoint needs only a few fields.

Example order listing API:

~~~text
GET /customers/42/orders

Response needs:
  orderId
  createdAt
  status
  totalAmount
~~~

SQL:

~~~sql
SELECT
    order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 28.1. DTOs/Projections in ORMs

A projection/DTO query reduces columns returned compared to loading full entities with wide `note` fields or unneeded lazy/eager relationships.

### 28.2. Avoiding N+1 Queries

If you fetch 20 orders and then issue 20 separate queries for product names:

~~~text
1 query fetching 20 orders
20 queries fetching each product
-> 21 database round trips
~~~

a single join query selecting exact columns is often better:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    p.product_name
FROM opt_lab.orders AS o
JOIN opt_lab.products AS p
  ON p.product_id = o.product_id
WHERE o.customer_id = 42
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

N+1 is a **database round-trip** problem—distinct from, yet complementary to, reducing rows and columns. Never blindly replace every N+1 with a giant join that multiplies rows; pick an approach matching cardinality.

### 28.3. Avoid Exposing Unnecessary Sensitive Data

`SELECT *` in an API can accidentally expose newly added columns (internal flags, tokens, operational notes) if mapping isn't tightly controlled. An explicit column list defines a clear data contract and limits data exposure.

## 29. When Does Selecting Fewer Columns Enable `Index Only Scan`?

Before creating a covering index:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, created_at
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC;
~~~

If index `(customer_id,created_at DESC,order_id DESC)` already exists, every column requested by the query lives in the index keys. The planner can consider `Index Only Scan`.

Compare with:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC;
~~~

`SELECT *` also requires `product_id`, `status`, `total_amount`, and `note`. Those columns are absent from the index keys, forcing PostgreSQL to read the heap or choose another plan.

### 29.1. MVCC Visibility Still Matters

Even when every column resides in the index, PostgreSQL may still perform heap fetches to verify tuple visibility if the visibility map has not marked pages all-visible. **Index-only does not automatically mean 0 heap reads.**

### 29.2. Index-Only Does Not Replace Measuring Buffers and Time

An oversized covering index can consume cache and slow down writes. Compare `Execution Time`, `Buffers`, `Heap Fetches`, index size, and write overhead before shipping to production.

## 30. Inspecting Planner Selectivity Statistics

`ANALYZE` collects per-column statistics so the planner can estimate selectivity.

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'opt_lab'
  AND tablename = 'orders'
  AND attname IN (
      'customer_id', 'status', 'created_at'
  )
ORDER BY attname;
~~~

### 30.1. `null_frac`

Estimated fraction of NULLs in the column. This influences `IS NULL`/`IS NOT NULL` predicates and index selection.

### 30.2. `n_distinct`

Estimated number of distinct values following PostgreSQL's convention. A negative number represents a fraction relative to total table rows, not “negative distinct values.”

### 30.3. `most_common_vals` and `most_common_freqs`

Help the planner identify frequent values and their estimated shares. For `status` in the lab, `paid` is very common, telling the planner that filtering for `paid` is far less selective than filtering for a specific `customer_id`.

### 30.4. Estimates Are Not Immutable

Stats are **samples/statistical summaries**; after major bulk loads or updates, run `ANALYZE` or wait for autovacuum/autoanalyze as configured. Never conclude a query returns wrong results just because estimated rows differ from actual rows; bad estimates primarily affect plan choice.

## 31. Extended Statistics and Multi-Column Predicates

Suppose in real data `status` and `region` or `customer_id` are strongly correlated. The planner can misestimate combined predicates when relying only on independent single-column stats.

On the same table, you can create extended statistics:

~~~sql
CREATE STATISTICS st_orders_customer_status
    (dependencies, mcv)
ON customer_id, status
FROM opt_lab.orders;

ANALYZE opt_lab.orders;
~~~

### 31.1. Not a Direct Speedup Mechanism

`CREATE STATISTICS` does not build an index or directly cut block reads. It **gives the planner better information** to choose superior access paths on certain queries.

### 31.2. Limitations

Effectiveness depends on predicate shape, correlation strength, and PostgreSQL version. Extended statistics **do not automatically solve all join cardinality misestimates**. On the lab's uniform 12-orders-per-customer data, the benefit may be negligible.

## 32. Prepared Statements: Parameter Values Affect Plans

A prepared statement:

~~~sql
PREPARE recent_orders(bigint) AS
SELECT
    order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = $1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Can be inspected via:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE recent_orders(42);
~~~

### 32.1. Generic Plan vs Custom Plan

PostgreSQL may use a parameter-specific plan (custom) or a shared plan (generic) depending on context and caching policy. Under heavy skew, a generic plan may be suboptimal for some values.

### 32.2. Partial Indexes and Parameters

A partial index `WHERE status='paid'` cannot be assumed to always apply to `WHERE status=$1`: a generic plan cannot prove every execution passes `'paid'`.

### 32.3. Do Not Hardcode All Parameters

Bind parameters remain vital for security and correctness. Plan tuning should rely on driver/tool support, data distribution, and measurement—never string concatenation that introduces SQL injection risk.

## 33. `EXPLAIN (ANALYZE, BUFFERS)`: Proper Measurement Workflow

First measure the baseline:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Then measure the trimmed projection:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Next, add the appropriate index:

~~~sql
CREATE INDEX IF NOT EXISTS idx_orders_customer_created
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);

ANALYZE opt_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 33.1. Metrics to Record

| Metric | What to Check |
| --- | --- |
| `Execution Time` | Total statement execution time reported by `EXPLAIN` |
| `Planning Time` | Time spent planning |
| `actual rows` | Rows emitted per node; read alongside `loops` |
| `loops` | How many times the node executed |
| `Rows Removed by Filter` | Rows discarded by a filter |
| `Index Cond` | Predicates pushed into the index access path |
| `Buffers: shared hit/read` | Logical block-access footprint |
| `Sort` / `Sort Method` | Whether sorting or disk spilling occurred |
| `Heap Fetches` | For Index-Only Scan, heap visits required for visibility checks |
| `width` | Estimated output row width |

### 33.2. Check `Buffers`, Not Just Duration

A query may run fast because all pages are warm in cache yet still touch huge numbers of blocks. Under real load, that large buffer footprint competes with other queries for cache and CPU.

### 33.3. `read` Does Not Equal a Disk Seek

`shared read` reports blocks brought into `shared_buffers` as needed; **it does not mean every block caused a physical disk read**, because of the OS page cache and I/O coalescing.

### 33.4. Parent Node Buffers Usually Include Children

Do not sum `Buffers` from root to leaves as independent numbers; you would **double count**.

### 33.5. `actual rows` and `loops`

In text-format `EXPLAIN ANALYZE`, `actual rows` is generally the **average per loop**. For an inner index scan showing `rows=12 loops=1000`, total cumulative output is around 12,000 rows, not 12.

## 34. Measuring Network and Result Size

`EXPLAIN (ANALYZE, BUFFERS)` reports server work but **does not fully measure bytes transferred to the client for the actual result set** like a normal query execution.

Practical approaches:

1. In the application, log row counts and serialized response sizes (e.g., JSON bytes), stripping sensitive data.
2. Compare server latency against end-to-end latency across multiple runs on the same network and load.
3. In the lab database, fetch 20, 200, and 2,000 rows with the same projection and observe throughput and mapping cost.
4. Watch JSON encoding, text encoding, compression, object allocations, and driver overhead.

### 34.1. Do Not Use `pg_column_size` as Network Bytes

~~~sql
SELECT
    pg_column_size(description) AS storage_bytes
FROM opt_lab.products
WHERE product_id = 42;
~~~

`pg_column_size` reflects internal PostgreSQL storage representation, **not exact JSON/HTTP response length** or wire-protocol byte count.

### 34.2. Illustrative Calculation

Suppose an API returns **1,000 rows × 2 KB/row ≈ 2 MB** of payload. Trimming to four columns averaging **150 B/row** cuts raw data down to around **150 KB** before JSON field-name and framing overhead.

This is an illustrative calculation, not a measurement of the lab table. Actual latency impact depends on connection speed, compression, throughput, and serialization.

## 35. When an Index Isn't Picked Despite a Selective `WHERE`

An index exists, yet the plan still shows:

~~~text
Seq Scan on orders
~~~

Causes to check:

- Table is small; `Seq Scan` is cheaper.
- The predicate actually matches a large fraction of rows.
- Statistics are stale or data distribution differs from assumptions.
- The query has expressions, casts, or collations incompatible with the index.
- The index does not cover `ORDER BY`, so the planner picks scan + sort.
- Bitmap/Seq Scan beats Index Scan due to excessive random heap fetches.
- Cache state, cost parameters, and parallelism shift the comparison.
- A partial index predicate cannot be proved from the query.

### 35.1. Do Not Treat `enable_seqscan=off` as a Production Fix

You can toggle planner parameters in a lab session to explore alternatives, yet disabling `enable_seqscan` does not fix underlying data or indexes and can ruin plans for other queries.

### 35.2. Do Not Tune from a Ten-Row Table

Tiny datasets make every query look fast. The 60,000-order lab merely illustrates differences; production benchmarks need realistic scale, skew, NULL ratios, write rates, and cache behavior.

## 36. The Cost of Over-Trimming Data

Optimization does not mean splitting one query into many tiny queries. For instance:

~~~text
1 query fetching 20 orders with 4 columns
+ 20 queries fetching each order's status
= 21 round trips
~~~

can be worse than one query fetching all five needed columns.

### 36.1. Select “Enough Columns for the Use Case”

If the API must display the product name, do not avoid a clean JOIN just for a shorter `SELECT`-list if doing so triggers 20 extra database round trips.

### 36.2. Never Trade Away Correctness

Never drop permission or tenant predicates just because they complicate index use. Never replace `LEFT JOIN` with `INNER JOIN` when business logic requires keeping unmatched rows. Never add `LIMIT` to an export in a way that truncates data.

### 36.3. Data Minimization Must Align with Access Control

In multi-tenant systems, the predicate:

~~~sql
WHERE tenant_id = $1
~~~

is both a selective filter and part of access isolation. Optimization must preserve authorization/RLS policies and never assume an index alone enforces security.

## 37. Common Mistakes

### Mistake 1: `SELECT *` on Hot Paths

Returns wide unused data, bloats network/serialization, and can forfeit index-only scans. Select only needed columns.

### Mistake 2: Assuming Fewer Columns Always Reduces Heap Reads

Under a full-table `Seq Scan`, heap pages scanned remain roughly unchanged. Measure `Buffers` and scan type.

### Mistake 3: Thinking Every `WHERE` Is Selective

`WHERE status='paid'` covering 70% of rows is nowhere near `WHERE order_id=42`.

### Mistake 4: Wrapping Timestamp Columns in `::date`

Can block direct use of a timestamp index; prefer half-open ranges in the right time zone.

### Mistake 5: Defining End-of-Day as `23:59:59`

Can miss fractional seconds. Use `>= start AND < next_day_start`.

### Mistake 6: Casting `order_id` to `text`

`order_id::text` does not match a `bigint` index; bind parameters with proper types.

### Mistake 7: Using `LIKE '%text%'` and Expecting B-Tree Prefix Tuning

A leading wildcard removes any fixed prefix. Consider trigram or full-text indexes depending on workload.

### Mistake 8: Using `lower(column)` When Only `column` Is Indexed

You likely need an expression index matching `lower(column)`.

### Mistake 9: Indexing Every Column Appearing in `WHERE`

Excess indexes hurt writes and storage; choose based on frequency, selectivity, and `EXPLAIN`.

### Mistake 10: Treating `Seq Scan` as Always Wrong

Sequential scans are often the right, cheapest plan on small tables or broad filters.

### Mistake 11: Ignoring `ORDER BY` When Designing Indexes

An index serving only `WHERE` may still force sorting tens of thousands of rows. Design for `WHERE + ORDER BY + LIMIT`.

### Mistake 12: Putting `status` Before `created_at` for Every Query

`(customer_id,status,created_at)` does not provide global `created_at` order across multiple statuses for a single customer.

### Mistake 13: Confusing `INCLUDE` Columns with Key Columns

`INCLUDE(status)` helps covering/output, not key searching or ordering like a key column.

### Mistake 14: Assuming `Index Only Scan` Never Touches the Heap

Visibility map and MVCC state can still trigger `Heap Fetches > 0`.

### Mistake 15: Expecting Partial Indexes to Always Apply with Bind Parameters

A generic plan may be unable to prove the parameter satisfies the partial index predicate.

### Mistake 16: Assuming `LIMIT 20` Means Only 20 Rows Are Read

Underlying sorts, aggregates, or scans may still process the entire table.

### Mistake 17: Treating Deep `OFFSET` as Nearly Free

The executor still walks past preceding rows before reaching the page. Consider keyset pagination.

### Mistake 18: Using `DISTINCT` to Mask Row-Multiplying Joins

Cardinality blow-up still makes the join expensive. Use `EXISTS` when checking existence.

### Mistake 19: Pushing Predicates Across `LEFT JOIN` and Changing Semantics

Predicates in `ON` vs `WHERE` behave differently. Always preserve correctness.

### Mistake 20: Putting Row-Level Filters in `HAVING`

When aggregating only paid orders, filter in `WHERE` before grouping when semantically valid.

### Mistake 21: Assuming CTEs Always Materialize

Modern PostgreSQL often inlines eligible CTEs. `MATERIALIZED` is explicit and can block predicate pushdown.

### Mistake 22: Using Metadata as Exact `COUNT(*)`

`reltuples` is an estimate; exact MVCC-consistent counts are not free.

### Mistake 23: Looking at `Execution Time` from a Single Run

Cache, concurrency, instrumentation, and variance skew single runs. Compare buffers and multiple runs.

### Mistake 24: Forcing the Planner to Use an Index Just Because You Built It

Benefits must be proven with metrics. Never disable `Seq Scan` globally to “save” one query.

### Mistake 25: Trimming SQL Columns While Ignoring the API/ORM

If the ORM still loads huge relations or the API serializes the full entity, end-to-end gains shrink.

## 38. Practice Exercises

Work in `opt_lab`. Exercises creating indexes or running `ANALYZE` are strictly for the lab database; never run ad-hoc DDL on shared systems.

### Exercise 1. Projection

Write a query returning only `order_id`, `created_at`, `status`, and `total_amount` for customer 42 instead of `SELECT *`.

### Exercise 2. Selectivity

Out of 60,000 orders, `customer_id=42` returns 12 rows and `status='paid'` returns 42,000 rows. Which predicate is more selective? Compute both ratios.

### Exercise 3. Width

Two plans report `width=250` and `width=40`, yet both perform a full-table `Seq Scan`. Can you conclude the second reads 6.25× fewer heap blocks?

### Exercise 4. Wide Columns

Why can removing `description` from `SELECT` improve performance without guaranteeing fewer heap pages read during a full scan?

### Exercise 5. `EXPLAIN`

Write an `EXPLAIN (ANALYZE, BUFFERS)` query to measure filtering by `customer_id=42`. Which fields should you inspect?

### Exercise 6. `Index Cond`

Explain the difference between `Index Cond: (customer_id=42)` and `Filter: (customer_id=42)` in a plan.

### Exercise 7. Timestamp Range

Write a query finding orders within **UTC day 2026-02-01** using a half-open `created_at` range.

### Exercise 8. Time Zone

Why can `created_at::date = DATE '2026-02-01'` differ from a fixed UTC range?

### Exercise 9. Expression Index

Write an index suited for `WHERE lower(product_name) = 'product 42'`.

### Exercise 10. Prefix `LIKE`

How do `sku LIKE 'SKU-0001%'` and `sku LIKE '%0001%'` differ in B-tree indexability?

### Exercise 11. Status Index

Why might the planner skip an index on `status` when filtering `paid` (70% of the table)?

### Exercise 12. Composite Index

Design an index for a query filtering `customer_id`, sorting by `created_at DESC, order_id DESC`, and applying `LIMIT`.

### Exercise 13. Two Query Patterns

If one API always filters `status` while another does not, is `(customer_id,status,created_at)` enough for all queries sorting by `created_at`?

### Exercise 14. `INCLUDE`

Write a covering index for an order-history page needing `order_id, created_at, status, total_amount` filtered by `customer_id`.

### Exercise 15. `Heap Fetches`

Why can an `Index Only Scan` still report `Heap Fetches=100`?

### Exercise 16. Partial Index

Create a partial index for the newest `paid` orders. Why might a prepared query `status=$1` not always use it?

### Exercise 17. `LIMIT`

A plan shows `Limit rows=10`, `Sort rows=10`, and child `Seq Scan rows=42000`. Did `Sort` really inspect only 10 rows?

### Exercise 18. `OFFSET`

Why can `LIMIT 20 OFFSET 100000` be expensive even though it returns only 20 rows?

### Exercise 19. Keyset Pagination

Write the cursor condition for `created_at DESC, order_id DESC` when both columns are `NOT NULL`.

### Exercise 20. JOIN Projection

Write a query returning order ID, creation date, amount, and customer name for customer 42 without using `o.*, c.*`.

### Exercise 21. `EXISTS`

Write a query listing customers with at least one `paid` order without multiplying order rows into the output.

### Exercise 22. `LEFT JOIN`

What is the difference between placing `o.status='paid'` in `ON` vs `WHERE` of a `LEFT JOIN`?

### Exercise 23. `HAVING`

Write a query counting `paid` orders per customer and returning only customers with at least 10 `paid` orders.

### Exercise 24. CTE

Why might `WITH x AS MATERIALIZED (SELECT ... FROM orders) SELECT ... FROM x WHERE customer_id=42` process more data than an inlined CTE?

### Exercise 25. Partition Pruning

How should predicates on a `created_at`-partitioned table be written so PostgreSQL can prune unrelated partitions?

### Exercise 26. `COUNT`

Can `pg_class.reltuples` completely replace `SELECT COUNT(*)` when an exact snapshot row count is required?

### Exercise 27. `pg_stats`

Write a query to inspect `null_frac`, `n_distinct`, and `most_common_freqs` for `status`.

### Exercise 28. Extended Statistics

How can extended statistics help the planner without directly creating an index or reducing pages read?

### Exercise 29. Prepared Statements

How can a custom plan and a generic plan differ when `customer_id` is heavily skewed?

### Exercise 30. N+1

Why can trimming columns while issuing 20 extra queries for product names make the API slower?

## 39. Reference Solutions

### Exercise 1. Selecting Exact Columns

~~~sql
SELECT order_id, created_at, status, total_amount
FROM opt_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC;
~~~

### Exercise 2. Computing Selectivity

`customer_id=42`: `12/60000 = 0.0002 = 0.02%`. `status='paid'`: `42000/60000 = 70%`. `customer_id` is far more selective.

### Exercises 3–4. Projection vs Physical Scan

No. `width` is estimated output bytes per row; when both plans still scan the whole table, heap blocks accessed remain roughly similar. Omitting `description` reduces processing/serialization, can skip TOAST access, and opens the door to index-only scans.

### Exercise 5. Baseline Measurement

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM opt_lab.orders
WHERE customer_id = 42;
~~~

Inspect `Execution Time`, scan type, estimated/actual rows, `loops`, `Index Cond`, `Filter`, `Rows Removed by Filter`, and `Buffers`.

### Exercise 6. `Index Cond` vs `Filter`

`Index Cond` is used by the index access path to locate/bound index entries; `Filter` is evaluated on tuples already retrieved by the node. A query can have both.

### Exercise 7. UTC Day

~~~sql
SELECT order_id, created_at
FROM opt_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00';
~~~

### Exercise 8. Time Zone

`timestamptz::date` is evaluated in the session's time zone, while `+00` bounds are UTC. Compute boundaries matching the business time zone before rewriting.

### Exercise 9. Expression Index

~~~sql
CREATE INDEX idx_products_lower_name_answer
ON opt_lab.products (lower(product_name));
~~~

### Exercises 10–11. Prefixes and Selectivity

`'SKU-0001%'` has a fixed prefix and can use an appropriate B-tree, whereas `'%0001%'` has no fixed prefix. Filtering `paid` (70% of rows) can make a Seq Scan cheaper than an index.

### Exercise 12. Composite Index

~~~sql
CREATE INDEX idx_orders_history_answer
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

### Exercise 13. Status in the Middle

No. Without fixing `status`, entries are grouped by `status` ahead of `created_at`, so they do not provide a single `created_at` ordering across all statuses for a customer.

### Exercise 14. Covering Index

~~~sql
CREATE INDEX idx_orders_cover_answer
ON opt_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (status, total_amount);
~~~

### Exercise 15. MVCC

The visibility map has not marked those tuple pages as all-visible, so PostgreSQL must visit the heap to check visibility even though the data columns reside in the index.

### Exercise 16. Partial Index

~~~sql
CREATE INDEX idx_orders_paid_answer
ON opt_lab.orders (created_at DESC, order_id DESC)
WHERE status = 'paid';
~~~

A generic plan for `status=$1` cannot assume the parameter is always `'paid'` and therefore cannot prove the partial index predicate.

### Exercises 17–18. `LIMIT`/`OFFSET`

`Sort` received 42,000 rows to pick the top 10. `OFFSET 100000` typically still walks through all preceding rows before the target page rather than skipping them for free.

### Exercise 19. Cursor

~~~sql
SELECT order_id, created_at
FROM opt_lab.orders
WHERE customer_id = 42
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-02-01 12:00:00+00', 45000::bigint)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

In an API, the cursor comes from the last row of the previous page; the example uses illustrative literals.

### Exercise 20. JOIN Projection

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount,
    c.full_name
FROM opt_lab.orders AS o
JOIN opt_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.customer_id = 42;
~~~

### Exercise 21. `EXISTS`

~~~sql
SELECT c.customer_id, c.full_name
FROM opt_lab.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM opt_lab.orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'paid'
);
~~~

### Exercise 22. Outer Join

Putting the condition in `ON` restricts which `orders` rows match while keeping unmatched left-hand customers. Putting `o.status='paid'` in `WHERE` discards NULL-extended rows, effectively turning it into an `INNER JOIN` behavior.

### Exercise 23. `WHERE` Before `GROUP BY`

~~~sql
SELECT customer_id, COUNT(*) AS paid_orders
FROM opt_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
HAVING COUNT(*) >= 10;
~~~

### Exercise 24. `MATERIALIZED` CTE

Materialization can build the full large `orders` set before the outer filter applies; an inlined CTE allows the planner to push `customer_id=42` down to the scan. Still, not every CTE should be inlined if its result is reused multiple times.

### Exercise 25. Partition Key Range

~~~sql
WHERE created_at >= TIMESTAMPTZ '2026-02-10 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-02-11 00:00:00+00'
~~~

### Exercise 26. Exact `COUNT`

No. `reltuples` is an estimate; `COUNT(*)` counts rows visible under the active snapshot using the chosen execution plan.

### Exercise 27. Statistics

~~~sql
SELECT
    attname,
    null_frac,
    n_distinct,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'opt_lab'
  AND tablename = 'orders'
  AND attname = 'status';
~~~

### Exercise 28. Extended Statistics

They improve planner cardinality estimates across correlated columns, indirectly enabling better plan/index/join choices. They are not a new access path.

### Exercise 29. Custom vs Generic Plans

A custom plan inspects the concrete `customer_id` value and estimates row count from the skewed distribution; a generic plan picks one strategy for all values, which can be suboptimal for very hot or very rare values.

### Exercise 30. N+1 Round Trips

Network round trips, parse/execute overhead, and pool waits all multiply. A single JOIN query fetching exact columns cuts round trips—just watch out for row multiplication or overly wide payloads.

## 40. Quick Reference Table

| Goal | Approach |
| --- | --- |
| Avoid fetching unused columns | `SELECT col1, col2, ...` instead of defaulting to `SELECT *` |
| Reduce rows scanned | Selective predicates, suited indexes / partition pruning |
| Reduce network payload | Necessary columns, necessary rows, proper serialization |
| Primary-key lookup | `WHERE id = ...`, B-tree PK |
| Filter by customer | Index on `(customer_id)` or composite index |
| Filter dates/timestamps | Half-open range `>= start AND < end` |
| Function on column | Rewrite predicate or add matching expression index |
| Prefix `LIKE` | B-tree with matching opclass/collation |
| Substring `ILIKE` | `pg_trgm` GIN/GiST when workload warrants |
| Filter and sort | Composite B-tree matching `WHERE + ORDER BY` |
| Small output from index | `INCLUDE` and Index-Only Scan when MVCC permits |
| Index only one status | Partial index with predicate matching query |
| Latest-page list | `ORDER BY ... LIMIT` with matching index order |
| Deep pagination | Keyset/cursor pagination |
| Check child existence | `EXISTS` / semijoin when semantically appropriate |
| Reduce aggregate input | `WHERE` before `GROUP BY` when valid |
| Filter groups | `HAVING` for post-aggregation conditions |
| CTE blocking pushdown | Check `MATERIALIZED` vs inlining |
| Time-partitioned table | Direct range predicate on partition key |
| Exact count | `COUNT(*)` under snapshot; don't mistake metadata for exactness |
| Row estimates | `pg_stats`, `ANALYZE`, extended statistics where needed |
| Inspect plan | `EXPLAIN (ANALYZE, BUFFERS)` |
| Measure work | `actual rows`, `loops`, `Rows Removed by Filter`, `Buffers` |
| Inspect filter mechanism | `Index Cond` vs `Filter` |

## 41. Checklist Before Optimizing a SQL Query

1. Which columns does the API or report **actually need**?
2. Are wide `text`/`jsonb` columns being fetched without being used?
3. How many rows must the query return, and is `LIMIT` used properly?
4. Is `WHERE` selective, or does it match nearly the whole table?
5. Does the predicate compare directly against an index key?
6. Do functions or casts around a column block index use or partition pruning?
7. Do time predicates use `[start, end)` and the right time zone?
8. Does `LIKE` have a fixed prefix or a leading wildcard?
9. Could an index support **both filtering and ordering**?
10. Does `INCLUDE` genuinely enable an index-only scan worth its write cost?
11. Can the query prove a partial index's predicate?
12. Do `LEFT JOIN` / `INNER JOIN` / `EXISTS` preserve exact semantics?
13. Is there row multiplication or an N+1 query pattern?
14. Is `GROUP BY` processing excess rows due to a missing `WHERE` filter?
15. Does `LIMIT` actually stop the scan early, or does `Sort` still read large inputs?
16. Is `OFFSET` too deep for the pagination workload?
17. Is there a suitable partition-key predicate for pruning?
18. Are planner statistics up to date and capturing data skew?
19. What do `Index Cond`, `Filter`, and `BUFFERS` show in `EXPLAIN`?
20. Does the optimized SQL return **the exact same, complete results** as before?

## 42. Summary

Reducing data read in PostgreSQL is not just about adding a `WHERE` clause or replacing `SELECT *` with a shorter list. Separate three goals:

1. **Fetch only the needed columns:** shrink output width, wide-value processing, network transfer, and serialization; enable covering/index-only scans. On its own, this **does not reduce heap blocks** if a full table scan still runs.
2. **Read only the needed rows:** write selective, sargable predicates with proper types and time zones; provide access paths via B-trees, expression/partial/composite indexes, or partition pruning where justified. `Index Cond` and `Rows Removed by Filter` reveal whether PostgreSQL is seeking or post-filtering.
3. **Avoid generating unnecessary intermediate data:** combine `WHERE + ORDER BY + LIMIT`, use `EXISTS` for existence checks, prevent row multiplication, filter before aggregating when valid, review CTE materialization, and use cursor pagination where suitable.

The final arbiter is **measuring on real plans**. With `EXPLAIN (ANALYZE, BUFFERS)`, inspect which nodes read many rows, which discard rows via `Filter`, which indexes are chosen, how many buffers are touched, and how execution behaves across comparable runs.

When investigating a slow API, start with two concrete questions: **“Which columns and rows does the user actually need?”** and **“How much data does PostgreSQL have to read and check to return them?”** From there, rewrite SQL, design indexes, and tune statistics to cut real work without altering business results.
