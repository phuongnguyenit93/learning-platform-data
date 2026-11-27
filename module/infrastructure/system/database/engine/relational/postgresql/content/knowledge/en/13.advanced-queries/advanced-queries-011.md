# Keyset Pagination and Comparison with OFFSET in PostgreSQL

When an application has millions of orders, event logs, or articles, returning all data in a single request is inefficient. The UI typically only needs 20, 50, or 100 rows at a time. PostgreSQL supports two common strategies: **position-based pagination using LIMIT/OFFSET** and **key-based pagination using keyset/seek pagination**.

Both strategies use `ORDER BY` and `LIMIT`, but they differ in how they determine the starting position of the next page. OFFSET counts and skips the rows preceding the page; keyset records the **sort key values of the last row on the current page**, and then queries onward from that marker.

This difference affects performance, stability across requests, and user experience while data is being inserted, updated, or deleted.

This lesson belongs to the **Advanced Queries** chapter, **Database Engine Relational PostgreSQL** module, and covers:

- How `LIMIT/OFFSET` works and its cost.
- How to design keyset pagination for ascending/descending `ORDER BY` and composite keys.
- The role of a **unique tie-breaker**, row-value comparison, and B-tree indexes.
- How to handle mixed sort directions, `NULL`, filters, previous pages, and last pages.
- The impact of MVCC, transaction isolation, and concurrent data modifications.
- How to integrate cursors into APIs/Java JDBC, protect tokens, and measure with `EXPLAIN`.
- Situations where OFFSET should still be used instead of forcing everything into keyset pagination.

## 1. Pagination Must Start with a Deterministic Order

The SQL query:

~~~sql
SELECT id, created_at
FROM orders
LIMIT 20;
~~~

does not guarantee "the 20 newest orders", because there is no `ORDER BY`. PostgreSQL may return rows according to index order, heap order, or another execution plan.

If the application wants the newest orders first:

~~~sql
SELECT id, created_at
FROM orders
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Here:

- `created_at DESC`: newer creation timestamps come first.
- `id DESC`: when multiple orders share the same timestamp, the larger ID comes first.
- `LIMIT 20`: returns at most 20 rows.

The `id` column acts as a **tie-breaker**. If `id` is the primary key and `created_at` is NOT NULL, the pair `(created_at,id)` defines a total ordering: two distinct rows will never share the entire key pair.

**The most important rule:** pagination does not only need to limit the number of rows; it must define the **order of the rows** and the **position of the page within that order**.

## 2. Creating Practice Data

The examples use a dedicated orders table in a learning database. Do not run these on production. The `CREATE SCHEMA` statement below is only appropriate if the schema does not already exist; if it does, use a new lab database instead of dropping an active schema.

~~~sql
CREATE SCHEMA pagination_lab;

CREATE TABLE pagination_lab.orders (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);

INSERT INTO pagination_lab.orders
    (id, created_at, status, total_amount)
VALUES
    (100, TIMESTAMPTZ '2026-02-10 10:02:00+00', 'paid',       100000.00),
    (101, TIMESTAMPTZ '2026-02-10 10:03:00+00', 'new',        120000.00),
    (102, TIMESTAMPTZ '2026-02-10 10:03:00+00', 'paid',       140000.00),
    (103, TIMESTAMPTZ '2026-02-10 10:04:00+00', 'cancelled',  160000.00),
    (104, TIMESTAMPTZ '2026-02-10 10:04:00+00', 'paid',       180000.00),
    (105, TIMESTAMPTZ '2026-02-10 10:04:00+00', 'new',        200000.00),
    (106, TIMESTAMPTZ '2026-02-10 10:05:00+00', 'paid',       220000.00);

CREATE INDEX idx_orders_created_id_desc
ON pagination_lab.orders (created_at DESC, id DESC);
~~~

Verification query:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC;
~~~

Expected ID order:

~~~text
106  10:05
105  10:04
104  10:04
103  10:04
102  10:03
101  10:03
100  10:02
~~~

All timestamps are on the same date 2026-02-10 and in the same UTC time zone. Duplicate timestamps are intentionally included to illustrate why a secondary key `id` is needed.

## 3. OFFSET Pagination: Skipping Rows

OFFSET uses the syntax:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 0;
~~~

This is the first page, containing IDs `106,105,104`.

Second page:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;
~~~

The result is `103,102,101`.

Third page:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 6;
~~~

Only ID `100` remains.

With page numbers starting at 1:

\[
\text{offset}=(\text{pageNumber}-1)\times\text{pageSize}
\]

For example, page 3 with pageSize 3 has an offset of 6.

### 3.1. Practical Advantages of OFFSET

- Simple SQL query, easy to integrate with numbered-page UIs.
- Can jump directly to page N by computing the offset.
- No need to remember the last key of the previous page.
- Suitable for small tables, bounded datasets, admin reports, or workloads that only access the first few pages.
- Works with many sort options without having to build separate seek predicates for each one.

We should not conclude that OFFSET is a wrong technique. It is a valid tool when its cost and semantics fit the requirements.

## 4. Why Is Deep OFFSET Usually Expensive?

Consider a table with millions of rows:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 100000;
~~~

Even though it only returns at most 20 rows, PostgreSQL still has to locate and discard the rows preceding the offset position in the ordered result. With a suitable index scan, the engine can avoid sorting the entire table, yet it still typically has to **traverse many skipped index entries/rows**.

Conceptual illustration:

~~~text
OFFSET 0       -> starts near the beginning of the list, returns 20 rows
OFFSET 1000    -> traverses about 1000 preceding rows, returns 20 rows
OFFSET 100000  -> traverses about 100000 preceding rows, returns 20 rows
~~~

This is an intuition about the amount of work, not an exact cost formula for every PostgreSQL plan. Actual runtime also depends on WHERE clauses, indexes, sorting, visibility, caching, and the number of filtered rows.

If a query lacks an index supporting `ORDER BY`, PostgreSQL may have to read and sort a large volume of data just to determine the target page.

**LIMIT does not eliminate the cost of finding the position after OFFSET.** It caps the number of rows returned, but it does not automatically jump the cursor to the 100,001st row of a dynamic result set.

## 5. OFFSET Can Duplicate or Skip Rows Across Pages

At time T1:

~~~text
[106, 105, 104, 103, 102, 101, 100]

Page 1, LIMIT 3 OFFSET 0 -> [106, 105, 104]
~~~

Then another transaction inserts a new order ID 107 with a larger `created_at`:

~~~text
T2:
[107, 106, 105, 104, 103, 102, 101, 100]
~~~

The client fetches the second page:

~~~text
LIMIT 3 OFFSET 3 -> [104, 103, 102]
~~~

**ID 104 is returned again** even though it already appeared on the first page. Reason: a new row inserted before the offset position shifted older rows downward.

If a row before the boundary is deleted, subsequent rows shift upward and OFFSET can cause the client to **skip** an unseen row.

This is not an offset calculation bug. OFFSET literally means skipping N rows **in the current result**; it does not remember which records the client saw in the previous request.

## 6. What Is Keyset/Seek Pagination?

Keyset pagination does not store "skipped 3 rows"; instead, it stores **"what (created_at,id) key did the last displayed row have?"**.

With the demo data:

~~~sql
-- First page:
SELECT id, created_at, status
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

The result is `106,105,104`. The cursor sits on the **last row**:

~~~text
created_at = 2026-02-10 10:04:00+00
id         = 104
~~~

Because the list is in descending order, a row comes **after the cursor** if its timestamp is smaller, or if it has the same timestamp with a smaller ID:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
WHERE
    created_at < TIMESTAMPTZ '2026-02-10 10:04:00+00'
    OR (
        created_at = TIMESTAMPTZ '2026-02-10 10:04:00+00'
        AND id < 104
    )
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

The result is `103,102,101`.

Diagram:

~~~text
106 (10:05)
105 (10:04)
104 (10:04)  <- page 1 cursor
------------------------------
103 (10:04)
102 (10:03)
101 (10:03)  <- page 2 cursor
------------------------------
100 (10:02)
~~~

With a supporting index, PostgreSQL can use the key predicate to seek to the next range instead of scanning through a very long prefix.

## 7. PostgreSQL Supports Row-Value Comparison

The verbose condition:

~~~sql
WHERE
    created_at < :last_created_at
    OR (
        created_at = :last_created_at
        AND id < :last_id
    )
~~~

can be shortened to:

~~~sql
WHERE (created_at, id) < (:last_created_at, :last_id)
~~~

This is a lexicographic tuple comparison: compare the first column; if equal, compare the next column.

Query that runs directly in `psql`:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
WHERE
    (created_at, id)
        < (TIMESTAMPTZ '2026-02-10 10:04:00+00', 104::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

In examples containing `:last_created_at`, the colon notation indicates a **conceptual application-layer parameter**. It is not a standard SQL placeholder that the PostgreSQL server understands verbatim when copied directly. JDBC uses `?` and binds values; `psql` has its own variable syntax.

### 7.1. Why Is Tuple Comparison Correct in This Case?

With:

~~~text
A = (10:04, 103)
B = (10:04, 104)
~~~

`A < B` because the timestamps are equal while 103 is smaller than 104.

With:

~~~text
A = (10:03, 9999)
B = (10:04, 104)
~~~

`A < B` because the timestamp is smaller, regardless of A's larger ID.

Both columns are sorted **DESC**, and both are **NOT NULL**, so tuple `<` matches the meaning of "after the cursor".

### 7.2. Conditions for Using the Shorthand

- All sort keys in the tuple share the same direction (**ASC** or **DESC**).
- They have compatible comparison types and no unhandled `NULL` cases.
- The cursor contains **all keys** used in ORDER BY.
- There is a unique tie-breaker to avoid skipping rows with duplicate keys.

For mixed sort directions or `NULLS FIRST/LAST`, a custom condition must be constructed.

## 8. Why Must There Be a Unique Tie-Breaker?

A common mistake:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC
LIMIT 3;
~~~

The dataset has three rows sharing timestamp `10:04`. If you only store a timestamp cursor, say `10:04`, and query:

~~~sql
WHERE created_at < TIMESTAMPTZ '2026-02-10 10:04:00+00'
~~~

then the other unseen rows with timestamp `10:04` will **never be returned**.

If you change it to `<=`, already-seen rows may appear again.

Solution:

~~~sql
ORDER BY created_at DESC, id DESC
~~~

and have the cursor carry both:

~~~text
(last_created_at, last_id)
~~~

`id` is the primary key, so it is unique, non-NULL, and usually immutable. It is a convenient tie-breaker, though another unique key can be used if it better reflects the design requirements.

**Do not assume that adding only `user_id` or `status` is enough:** multiple rows can easily share the same values for both of those fields.

## 9. Single-Column ID Keyset

If the business order truly is descending by ID:

~~~sql
SELECT id, status
FROM pagination_lab.orders
ORDER BY id DESC
LIMIT 3;
~~~

After the first page ends at ID 104:

~~~sql
SELECT id, status
FROM pagination_lab.orders
WHERE id < 104
ORDER BY id DESC
LIMIT 3;
~~~

This is single-column keyset pagination and is very simple. A primary key B-tree index is usually already present.

However, **increasing IDs do not guarantee absolute creation order or commit order**. A PostgreSQL sequence may assign an ID to one transaction first while that transaction commits after another transaction. Some applications use UUIDs or IDs from external systems that have no clear relationship with time.

Only sort by ID when ID order itself is the desired display order or when architectural guarantees are sufficiently clear.

## 10. Keyset Pagination with ORDER BY ASC

To view orders **oldest first, newest last**:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at ASC, id ASC
LIMIT 3;
~~~

The first page is `100,101,102`. The last row's cursor is `(10:03,102)`.

Next page:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
WHERE
    (created_at, id)
        > (TIMESTAMPTZ '2026-02-10 10:03:00+00', 102::BIGINT)
ORDER BY created_at ASC, id ASC
LIMIT 3;
~~~

Result: `103,104,105`.

Rules:

| Order | **Next** page predicate |
|---|---|
| `a ASC, b ASC` | `(a,b) > (:a,:b)` |
| `a DESC, b DESC` | `(a,b) < (:a,:b)` |
| `a DESC, b ASC` | Must build a mixed predicate |
| `a ASC, b DESC` | Must build a mixed predicate |

## 11. Mixed Sorting: DESC and ASC

Suppose a task list needs high-priority items first, but within the same priority level, smaller IDs come first:

~~~sql
CREATE TABLE pagination_lab.tasks (
    task_id BIGINT PRIMARY KEY,
    priority INTEGER NOT NULL,
    task_name TEXT NOT NULL
);

INSERT INTO pagination_lab.tasks
    (task_id, priority, task_name)
VALUES
    (10, 3, 'A'),
    (11, 3, 'B'),
    (20, 2, 'C'),
    (21, 2, 'D'),
    (30, 1, 'E');

CREATE INDEX idx_tasks_priority_id
ON pagination_lab.tasks (priority DESC, task_id ASC);
~~~

Ordering:

~~~sql
SELECT task_id, priority
FROM pagination_lab.tasks
ORDER BY priority DESC, task_id ASC;
~~~

Result:

~~~text
(priority=3,id=10)
(priority=3,id=11)
(priority=2,id=20)
(priority=2,id=21)
(priority=1,id=30)
~~~

If the cursor is at `(priority=3,id=11)`, the next rows must satisfy:

~~~sql
SELECT task_id, priority, task_name
FROM pagination_lab.tasks
WHERE
    priority < 3
    OR (priority = 3 AND task_id > 11)
ORDER BY priority DESC, task_id ASC
LIMIT 2;
~~~

The exact condition is **smaller priority**, or **equal priority and larger ID**.

Do not write:

~~~sql
-- Wrong for priority DESC, task_id ASC order:
-- WHERE (priority, task_id) < (3, 11)
~~~

because that condition can select task ID 10 (which comes before the cursor), rather than only tasks after it.

The index `(priority DESC, task_id ASC)` mirrors the mixed sort order. An all-ASC index cannot automatically satisfy DESC/ASC ordering merely by scanning backward.

## 12. NULLS FIRST/LAST and Cursors

When a sort key allows `NULL`, a simple row comparison may not reflect how `NULL`s are ordered in `ORDER BY`.

Example:

~~~sql
CREATE TABLE pagination_lab.shipments (
    shipment_id BIGINT PRIMARY KEY,
    shipped_at TIMESTAMPTZ,
    tracking_code TEXT NOT NULL
);

INSERT INTO pagination_lab.shipments
    (shipment_id, shipped_at, tracking_code)
VALUES
    (1, TIMESTAMPTZ '2026-04-02 09:00:00+00', 'A'),
    (2, NULL, 'B'),
    (3, TIMESTAMPTZ '2026-04-01 09:00:00+00', 'C'),
    (4, NULL, 'D');
~~~

Required order:

~~~sql
ORDER BY shipped_at DESC NULLS LAST, shipment_id DESC
~~~

Expected order: IDs `1,3,4,2`.

### 12.1. Cursor in the Non-NULL Timestamp Region

If the cursor is `(2026-04-01 09:00, ID 3)`, the subsequent rows include rows with a lower timestamp, same timestamp with smaller ID, **and** all rows with `shipped_at IS NULL` at the end.

~~~sql
SELECT shipment_id, shipped_at
FROM pagination_lab.shipments
WHERE
    (
        shipped_at IS NOT NULL
        AND (shipped_at, shipment_id)
            < (TIMESTAMPTZ '2026-04-01 09:00:00+00', 3::BIGINT)
    )
    OR shipped_at IS NULL
ORDER BY shipped_at DESC NULLS LAST, shipment_id DESC
LIMIT 3;
~~~

### 12.2. Cursor Already in the NULL Region

If the cursor is at ID 4, which has `shipped_at IS NULL`:

~~~sql
SELECT shipment_id, shipped_at
FROM pagination_lab.shipments
WHERE
    shipped_at IS NULL
    AND shipment_id < 4
ORDER BY shipped_at DESC NULLS LAST, shipment_id DESC
LIMIT 3;
~~~

The result is ID 2.

Corresponding index:

~~~sql
CREATE INDEX idx_shipments_shipped_id
ON pagination_lab.shipments (
    shipped_at DESC NULLS LAST,
    shipment_id DESC
);
~~~

Do not assume the default NULL placement is always `NULLS LAST` for DESC. Specify it explicitly in both SQL and the index when semantics require it.

**The simplest solution**, if business logic permits, is to use a `NOT NULL` sort key. Otherwise, the cursor must track whether the key is in the NULL region and choose the corresponding predicate.

## 13. Backward Pagination: The Previous Button

With the standard list `ORDER BY created_at DESC, id DESC`, the current page is:

~~~text
[103,102,101]
~~~

To fetch the three rows immediately preceding it, use the cursor from the **first row** (ID 103), not the last row (ID 101).

Rows preceding the cursor have **larger** keys. However, to retrieve the three rows *closest* before the cursor, you must temporarily reverse the sort direction:

~~~sql
SELECT p.id, p.created_at
FROM (
    SELECT id, created_at
    FROM pagination_lab.orders
    WHERE
        (created_at, id)
            > (TIMESTAMPTZ '2026-02-10 10:04:00+00', 103::BIGINT)
    ORDER BY created_at ASC, id ASC
    LIMIT 3
) AS p
ORDER BY p.created_at DESC, p.id DESC;
~~~

The result is `106,105,104` in the original display order.

If you kept `ORDER BY DESC LIMIT 3` directly in the inner query with the `>` predicate, on a long list it would return the three rows at the **very top of the entire list**, not the three rows adjacent to the cursor.

Practical rule:

- **Next:** cursor from the last row, forward condition, forward sort.
- **Previous:** cursor from the first row, reverse condition, reverse sort to grab the closest N rows, then flip the result back to the standard order.

## 14. Filters Must Remain Consistent Across Pages

Suppose we only view paid orders:

~~~sql
SELECT id, created_at, total_amount
FROM pagination_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, id DESC
LIMIT 2;
~~~

If the next page omits `status = 'paid'`, the dataset has changed. The cursor was a position within the "paid" set, not a position with an equivalent meaning across any other set.

Correct next-page query:

~~~sql
SELECT id, created_at, total_amount
FROM pagination_lab.orders
WHERE status = 'paid'
  AND (created_at, id)
      < (TIMESTAMPTZ '2026-02-10 10:04:00+00', 104::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 2;
~~~

If the user changes the filter to `status='new'` or changes the sort order to highest price first, the application should **reset the cursor** or reject tokens that do not match the new configuration.

In addition to display filters, tenant scope, access permissions, and server-verified conditions must also be preserved.

## 15. B-tree Indexes for Keyset Pagination

The basic index already created:

~~~sql
CREATE INDEX idx_orders_created_id_desc
ON pagination_lab.orders (created_at DESC, id DESC);
~~~

Can support:

~~~sql
SELECT id, created_at
FROM pagination_lab.orders
WHERE (created_at, id) < (:created_at, :id)
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

An appropriate index lets PostgreSQL seek directly to the key boundary and scan only the needed slice in many cases, rather than traversing a huge number of rows as in deep OFFSET.

### 15.1. Equality Filters Should Be Considered in the Index

If queries primarily filter by status:

~~~sql
WHERE status = 'paid'
  AND (created_at, id) < (...)
ORDER BY created_at DESC, id DESC
~~~

you can consider:

~~~sql
CREATE INDEX idx_orders_status_seek
ON pagination_lab.orders (
    status,
    created_at DESC,
    id DESC
);
~~~

`status` is the leading column serving the equality filter, while the trailing columns serve the sort keys.

However, if a query views **all statuses** ordered by time, an index leading with status will not necessarily support global ordering by `created_at` without extra sorting or merging.

### 15.2. Partial Index for a Common Status

~~~sql
CREATE INDEX idx_orders_paid_seek
ON pagination_lab.orders (created_at DESC, id DESC)
WHERE status = 'paid';
~~~

A partial index can be smaller and more efficient when requests predominantly query `status='paid'`. However, the planner must prove that the query's WHERE clause satisfies the partial index predicate. A prepared statement using a generic plan or overly general parameterization may not use it as intended.

### 15.3. INCLUDE Columns Are Not Sort Keys

If you only need extra display columns:

~~~sql
CREATE INDEX idx_orders_cover_seek
ON pagination_lab.orders (created_at DESC, id DESC)
INCLUDE (status, total_amount);
~~~

`INCLUDE` stores additional column data in the index, but **does not make status/total_amount sort keys**. It can enable index-only scans in some cases, though the visibility map/MVCC still determines whether heap fetches are needed; wider indexes also increase storage and write overhead.

Do not create all of these example indexes in production. Choose based on workload and measure execution plans.

## 16. EXPLAIN: Comparing Execution Work

On small tables, both queries may be fast and PostgreSQL may choose a sequential scan. `EXPLAIN` lets you inspect the plan instead of guessing.

OFFSET:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3 OFFSET 3;
~~~

Keyset:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders
WHERE
    (created_at, id)
        < (TIMESTAMPTZ '2026-02-10 10:04:00+00', 104::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 3;
~~~

Observe:

- `Index Scan` or `Index Only Scan` versus `Seq Scan`.
- Whether `Index Cond` carries the tuple condition.
- Whether a `Sort` node appears.
- The number of `actual rows` produced/read by each node.
- `Rows Removed by Filter` when present.
- `Buffers: shared hit/read`.
- Total time, cache effects, and WHERE selectivity.

`EXPLAIN ANALYZE` **actually executes the statement**. Here it is used with `SELECT`. When using it with DML in real environments, understand that the statement modifies data; do not run `EXPLAIN ANALYZE DELETE/UPDATE` casually just to inspect a plan.

## 17. Generating Larger Data to Compare OFFSET 90000 and Keyset

In a learning database with sufficient space:

~~~sql
CREATE TABLE pagination_lab.orders_bench (
    id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO pagination_lab.orders_bench
    (id, created_at, status, total_amount)
SELECT
    g::BIGINT,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + ((g - 1) / 20) * INTERVAL '1 second',
    CASE
        WHEN g % 4 = 0 THEN 'paid'
        ELSE 'new'
    END,
    (10000 + (g % 50000))::NUMERIC(12, 2)
FROM generate_series(1, 100000) AS g;

CREATE INDEX idx_orders_bench_seek
ON pagination_lab.orders_bench (created_at DESC, id DESC);

ANALYZE pagination_lab.orders_bench;
~~~

The benchmark table has 100,000 rows, with groups of 20 rows sharing each timestamp and deterministic values derived from ID. This is synthetic data for observing query behavior, not representative of production distributions.

### 17.1. Deep OFFSET

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders_bench
ORDER BY created_at DESC, id DESC
LIMIT 20 OFFSET 90000;
~~~

### 17.2. Keyset at the Same Position

With the dataset above unmodified, the row immediately preceding that result window is ID 10001 with timestamp `2026-01-01 00:08:20+00`.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at
FROM pagination_lab.orders_bench
WHERE
    (created_at, id)
        < (TIMESTAMPTZ '2026-01-01 00:08:20+00', 10001::BIGINT)
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Expected results for both queries on the static dataset are IDs **10000 down to 9981**.

Compare the number of index entries/rows actually traversed and the execution time across multiple runs. Keyset can seek directly to the target key range via the index; deep OFFSET usually still has to walk through most of the 90,000 preceding rows.

**Only in this measurement example do we hardcode the cursor** to get two equivalent queries; a real application must obtain the cursor from the last row of the previous page, never guessing IDs by position.

## 18. Keyset Does Not Automatically Make Every Query Fast

Keyset is especially beneficial when:

- WHERE and ORDER BY match a suitable index.
- The dataset is large.
- Deep pages are accessed frequently.
- Queries follow a stable ordering and key.

However, if:

- The query computes `ORDER BY expensive_function(...)` with no way to index it properly.
- JOINs/aggregations are very complex.
- Filters are unindexed and must scan most of the table.
- The planner cannot push the seek predicate into an index condition.
- The table only has a few dozen rows.

then the benefit may be small or negligible.

**Indexes and predicates must be designed together**, rather than merely replacing `OFFSET n` with `WHERE id < x` and assuming it is optimal.

## 19. What Information Must a Cursor Contain?

A logical cursor might include:

~~~text
version          = 1
sort             = created_at_desc_id_desc
last_created_at  = 2026-02-10T10:04:00.000000Z
last_id          = 104
status_filter    = paid
direction        = next
~~~

Depending on the API, it may also include tenant, expiry, or filter configuration identifiers. These fields do not need to be exposed to clients as raw JSON.

Design requirements:

1. **Complete sort keys:** every column required for boundary comparison, including the tie-breaker.
2. **No precision loss:** timestamps and integers must be encoded/decoded accurately.
3. **Filter/sort binding:** tokens become invalid if the browsed list configuration changes.
4. **Versioning:** so the token format can evolve.
5. **Do not trust the client:** verify token integrity and access permissions on the server.
6. **Limited lifetime** if the application does not want cursors to remain valid indefinitely.

### 19.1. Base64URL Is Neither Encryption Nor a Signature

An API commonly returns:

~~~text
GET /api/orders?limit=20&after=<opaque-cursor>
~~~

Base64URL only turns the payload into a URL-safe string. A client can still decode or tamper with its contents if the token is unprotected.

One approach:

- Serialize a versioned cursor.
- Sign the payload using HMAC with a server-side secret key.
- Encode the payload and signature into an opaque string.
- Upon receipt, verify the signature and expiry, and match filter/sort against the request.
- Enforce authorization and tenant restrictions from the current user session.

**A signature does not hide contents.** Do not place secrets or sensitive personal data inside an unencrypted payload. If confidentiality is required, use an encrypted token design or store cursor state server-side.

### 19.2. A Cursor Does Not Replace Authorization

Even when a token is valid, the server must still restrict the query to the authorized user/tenant. Never accept a client-supplied or token-tampered `tenant_id` as proof of access rights.

For multi-tenant systems, the index may need:

~~~sql
-- Conceptual pattern when the table has a tenant_id column:
CREATE INDEX idx_orders_tenant_created_id
ON orders (tenant_id, created_at DESC, id DESC);
~~~

Actual queries must include `tenant_id = :authorized_tenant_id`, using a server-verified value. This pattern is for tables with `tenant_id`; **do not run it verbatim on the demo table, which lacks that column**.

## 20. Pagination APIs and the LIMIT N+1 Technique

Suppose a client requests `pageSize=20`. The server can fetch **21 rows**:

~~~sql
SELECT id, created_at, status
FROM pagination_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, id DESC
LIMIT 21;
~~~

The application:

1. Reads at most 21 rows.
2. If 21 rows are actually returned, sets `hasNextPage=true`.
3. Returns at most the **first 20 rows** to the client.
4. Uses the **20th returned row** as the cursor for fetching the next page.
5. If 20 or fewer rows are returned, sets `hasNextPage=false` within the query snapshot.
6. If the page is empty, returns a null/absent cursor per the API contract.

**Do not take the cursor from the held-back 21st row**: that row was not shown to the client, and using it as the boundary for the next page would skip it.

An illustrative response structure:

~~~json
{
  "data": [
    {"id": 106, "createdAt": "2026-02-10T10:05:00Z"}
  ],
  "pageInfo": {
    "hasNextPage": false,
    "endCursor": "<opaque-or-null-cursor>"
  }
}
~~~

This is an **example JSON shape**, not the literal output of `LIMIT 21` on the demo dataset; `hasNextPage` must be computed from the actual SQL result.

### 20.1. Never Trust pageSize Directly

The server needs:

- A default value.
- A maximum cap.
- Validation for negative numbers, 0, non-numeric text, and overflow.
- Rate limiting/timeouts where appropriate.

For example, an API may allow `1 <= pageSize <= 100`; those bounds are application policy, not a mandatory PostgreSQL limit.

## 21. Java/JDBC: PreparedStatement with a Cursor

In Java, use `PreparedStatement` to bind filters and cursor parameters rather than concatenating request values into SQL strings.

Example for a PostgreSQL JDBC driver supporting `OffsetDateTime`, Java 17+, and a configured `DataSource`:

~~~java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class OrderPager {
    public record SortCursor(OffsetDateTime createdAt, long id) {}
    public record OrderRow(long id, OffsetDateTime createdAt, String status) {}
    public record Page(List<OrderRow> rows, boolean hasNext, SortCursor endCursor) {}

    private final DataSource dataSource;

    public OrderPager(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public Page fetch(String status, SortCursor after, int pageSize)
        throws SQLException {

        if (pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException("Invalid page size");
        }

        String sql = after == null
            ? """
              SELECT id, created_at, status
              FROM pagination_lab.orders
              WHERE status = ?
              ORDER BY created_at DESC, id DESC
              LIMIT ?
              """
            : """
              SELECT id, created_at, status
              FROM pagination_lab.orders
              WHERE status = ?
                AND (created_at, id) < (?, ?)
              ORDER BY created_at DESC, id DESC
              LIMIT ?
              """;

        List<OrderRow> fetched = new ArrayList<>();

        try (Connection con = dataSource.getConnection();
             PreparedStatement ps = con.prepareStatement(sql)) {
            int param = 1;
            ps.setString(param++, status);
            if (after != null) {
                ps.setObject(param++, after.createdAt());
                ps.setLong(param++, after.id());
            }
            ps.setInt(param, pageSize + 1);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    fetched.add(new OrderRow(
                        rs.getLong("id"),
                        rs.getObject("created_at", OffsetDateTime.class),
                        rs.getString("status")
                    ));
                }
            }
        }

        boolean hasNext = fetched.size() > pageSize;
        List<OrderRow> rows = new ArrayList<>(
            fetched.subList(0, Math.min(pageSize, fetched.size()))
        );

        SortCursor endCursor = rows.isEmpty()
            ? null
            : new SortCursor(
                rows.get(rows.size() - 1).createdAt(),
                rows.get(rows.size() - 1).id()
            );

        return new Page(rows, hasNext, endCursor);
    }
}
~~~

Details:

- The first page and cursor-based pages use **two distinct SQL statements**, avoiding unnecessary `OR :cursor IS NULL` conditions.
- `status` is always included in the filter.
- `OffsetDateTime` preserves instant semantics; no manual timestamp string truncation is needed.
- `setLong` passes the ID.
- `pageSize+1` detects whether another page exists.
- The cursor is built from the **last returned row**.
- The outer API layer must verify the token/filter/authorization **before calling** this method.

This code only illustrates the query flow; production implementations also need TLS, connection pooling, timeout handling, safe logging, and token signing.

### 21.1. Do Not Bind ORDER BY with Value Placeholders

You cannot use `?` directly in place of column names or `ASC/DESC` keywords as value parameters. If multiple sort options are allowed, the server should **whitelist** fixed templates:

~~~text
newest    -> ORDER BY created_at DESC, id DESC
oldest    -> ORDER BY created_at ASC, id ASC
highValue -> ORDER BY total_amount DESC, id DESC
~~~

Each template must have its matching cursor and seek predicate. Never concatenate arbitrary column names from user strings.

## 22. Timestamp Precision Affects Cursor Correctness

PostgreSQL `TIMESTAMPTZ` typically has microsecond precision. A value like:

~~~text
2026-02-10T10:04:00.123456Z
~~~

if rounded or truncated by a serializer to:

~~~text
2026-02-10T10:04:00.123Z
~~~

no longer represents the same position in `ORDER BY`. When multiple rows differ by only a few microseconds, the next query after a precision-truncated cursor can skip or duplicate rows.

Requirements:

- Serialize the full precision of sort keys.
- Decode into a temporal type matching PostgreSQL.
- Do not rely on the client machine's default time zone.
- Preserve large integer IDs intact (do not convert through numeric types that lose precision).
- Test cursors with closely spaced timestamps.

Values displayed in the UI may only need seconds, but **values inside the cursor must preserve the full precision used by database comparisons**.

## 23. How Does Keyset Behave Under Concurrent INSERTs?

First page:

~~~text
[106,105,104]  cursor=(10:04,104)
~~~

Another transaction inserts ID 107 with timestamp `10:06`, which falls **before the cursor** in DESC order. The next keyset page:

~~~sql
WHERE (created_at, id) < (:last_created_at, :last_id)
~~~

continues at `103,102,101`. Inserting a row before the cursor does not alter the key boundary, so ID 104 is not duplicated as with OFFSET.

However, keyset **does not guarantee all reads share the same snapshot**:

- Newly inserted rows whose sort key falls **after the cursor** may appear on later pages.
- Unseen rows that get deleted will no longer appear.
- Rows whose `updated_at`, score, priority, or filter values change can cross the boundary, causing duplicates or skips.
- Permission or tenant visibility changes also alter the result set.

Keyset gives stability by sort key, not a frozen list.

## 24. MVCC and Transaction Isolation

PostgreSQL uses **MVCC**. Under the default `READ COMMITTED` isolation level, each SELECT statement sees a snapshot as of the start of that statement. Separate HTTP requests generally do not share a snapshot.

A `REPEATABLE READ` transaction allows multiple SELECTs within the **same transaction** to see a consistent snapshot under PostgreSQL rules:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT id, created_at
FROM pagination_lab.orders
ORDER BY created_at DESC, id DESC
LIMIT 3;

-- Other SELECTs in this transaction see a consistent snapshot.

COMMIT;
~~~

However, **you should not keep a PostgreSQL transaction open for several minutes** just while a user reads page 1 and later clicks Next:

- Ties up connections in the pool.
- Holds back snapshots for a long time and impedes VACUUM.
- Scales poorly with many concurrent users.
- Hard to manage when requests time out or users close their browsers.

If a business workflow requires **exporting an exact fixed dataset**, consider materializing IDs/results, a server-side export/cursor mechanism with a bounded lifetime, or a controlled snapshot/version design.

### 24.1. Is a High-Water Mark a Snapshot?

You can record the maximum key at the start and bound subsequent pages by that ceiling. This prevents rows **newer than the initial watermark** from entering the results.

However, late-arriving rows with older timestamps, updated sort keys, status changes, or deleted records still affect pages. Therefore, a high-water mark is only **a boundary**, not a full point-in-time snapshot of the data at time T.

## 25. Mutable Sort Keys Cause Duplicates/Skips Even with Keyset

Suppose page 1 displayed `A,B,C` ordered by `updated_at DESC`. An unseen row D is updated so its `updated_at` becomes newer than C. When fetching the next page with "older than C", D is no longer in that region and may be skipped.

Conversely, an already-seen row B could be edited so its `updated_at` becomes older than C; B may then appear again.

To mitigate this:

1. Prefer relatively **immutable** sort keys like `created_at` when appropriate for the domain.
2. Clearly define that the feed shows a **live** list subject to change.
3. If strict consistency is needed, use snapshots, materialization, or versioning.
4. If the client needs to avoid redisplaying duplicate IDs, it can deduplicate received IDs with bounded memory, understanding this is not a snapshot.
5. Test concurrency cases where rows move across the cursor boundary.

Do not claim "keyset never duplicates or skips rows" if sort keys or set membership can mutate.

## 26. Page Numbers, COUNT(*), and Direct Page Jumping

Keyset usually pairs with UI patterns such as:

~~~text
Load more
Next / Previous
Infinite scroll
~~~

It does not inherently know where "page 900" is without first having a cursor for that region.

OFFSET makes page 900 easy to express:

~~~text
offset = (900 - 1) * pageSize
~~~

The trade-off is that reading deep pages can be expensive.

If the UI needs a total row count:

~~~sql
SELECT COUNT(*)
FROM pagination_lab.orders
WHERE status = 'paid';
~~~

An exact `COUNT(*)` can require substantial work on large datasets. It also reflects the snapshot of the count query, which may differ from pages read later.

`pg_class.reltuples` is only a **statistical estimate** and does not replace an exact COUNT for an arbitrary filter.

### 26.1. Which Approach Fits Each UI?

| Scenario | Usually appropriate strategy |
|---|---|
| Event feed with continuous inserts | Keyset |
| Very long infinite scroll | Keyset |
| Sequential export API over a stable key | Keyset, or a dedicated export pipeline |
| List of newest orders | Keyset |
| Admin table of a few hundred rows with page jumping | OFFSET may be simpler |
| Dataset bounded to the first 5–10 pages | OFFSET may be good enough |
| Report requiring exact totals and arbitrary jumps | OFFSET / dedicated reporting design |
| Strict immutable snapshot while browsing | Snapshot/materialization mechanism, not just OFFSET or keyset |

No single strategy is best for every problem. Consider UX, scale, data churn, and consistency guarantees.

## 27. Keyset When JOINing Other Tables

An API may want to display orders alongside customer names. If you perform a one-to-many JOIN before LIMIT, one order with multiple child rows can occupy multiple slots, making "20 JOIN rows" unequal to "20 orders".

One design approach when the main filters belong to the orders table:

~~~sql
-- Conceptual pattern for a real orders/customers schema.
WITH page_orders AS (
    SELECT id, customer_id, created_at
    FROM orders
    WHERE
        (created_at, id)
            < (:last_created_at, :last_id)
    ORDER BY created_at DESC, id DESC
    LIMIT :page_size
)
SELECT
    p.id,
    p.created_at,
    c.name AS customer_name
FROM page_orders AS p
JOIN customers AS c
    ON c.id = p.customer_id
ORDER BY p.created_at DESC, p.id DESC;
~~~

This snippet **cannot run directly on pagination_lab.orders** because the demo table has no `customer_id`; it is an architectural illustration.

Keep in mind:

- If a JOIN drops orders due to missing related records, the final page may return fewer than N orders.
- If a filter depends on the JOINed table, that filter must be applied **before selecting the page**.
- If JOINing to multiple detail rows, rows multiply; define the unit of pagination clearly.
- The outer query still needs `ORDER BY` if output order must be guaranteed.
- CTEs/subqueries with LIMIT affect optimization choices, so measure the real execution plan.

Do not mechanically apply a "LIMIT before every JOIN" rule without checking semantics.

## 28. Common Pitfalls

### Mistake 1 — Missing ORDER BY

Row order is not guaranteed. **Fix:** define an ORDER BY that matches the business requirement.

### Mistake 2 — Sorting Only by created_at

Rows with identical timestamps can be skipped when seeking. **Fix:** add a unique tie-breaker `id` to ORDER BY and the cursor.

### Mistake 3 — Using > with DESC

Fetches rows before the cursor instead of after it. **Fix:** when all sort keys are DESC, use `<` for Next.

### Mistake 4 — Mixed ASC/DESC with Tuple <

The predicate can return the wrong ordering. **Fix:** write a lexicographic comparison matching each column's direction.

### Mistake 5 — Ignoring NULL Handling

Tuple comparisons with NULL yield UNKNOWN and drop part of the list. **Fix:** handle NULLS FIRST/LAST branches explicitly or use NOT NULL keys.

### Mistake 6 — Cursor Missing an ORDER BY Column

Cannot distinguish rows that match on the partial key. **Fix:** include all sort columns, including the unique tie-breaker.

### Mistake 7 — Building the Cursor from Row N+1

The unreturned (N+1)th row gets skipped. **Fix:** build the cursor from the Nth returned row.

### Mistake 8 — Truncating Timestamps to Milliseconds

Seek boundaries diverge from microsecond values in the DB. **Fix:** preserve full precision.

### Mistake 9 — Changing Filter/Sort While Keeping the Old Cursor

The cursor no longer belongs to the same dataset. **Fix:** reset or reject the cursor.

### Mistake 10 — Treating Base64 as Security

Clients can modify token contents. **Fix:** sign/verify tokens or store state server-side, and always enforce authorization on the server.

### Mistake 11 — Assuming Keyset Is a Snapshot

Backdated INSERTs, UPDATEs, and DELETEs still affect results. **Fix:** document live semantics or implement dedicated snapshots.

### Mistake 12 — Sorting by updated_at While Assuming Immutable Keys

Rows move across the cursor boundary. **Fix:** accept live semantics or design a versioned/snapshot mechanism.

### Mistake 13 — Missing a Matching Index

Keyset may still perform large scans or sorts. **Fix:** index according to filters and ORDER BY, then verify with EXPLAIN.

### Mistake 14 — Running COUNT on Every Scroll

Adds unnecessary load for feeds that only need to know if another page exists. **Fix:** use LIMIT N+1 when appropriate.

### Mistake 15 — Very Deep OFFSET on Large Tables

The engine must traverse many preceding rows. **Fix:** use keyset for sequential flows or cap maximum depth.

### Mistake 16 — No Limit on pageSize

A single request could ask for too many rows. **Fix:** enforce bounds at the API layer.

### Mistake 17 — Using ID as an Absolute Timestamp

Sequences and transactions do not guarantee larger IDs always commit later. **Fix:** sort by the actual business criterion.

### Mistake 18 — Let JOINs Multiply Rows Before LIMIT

A single entity consumes multiple page slots. **Fix:** define the pagination unit and apply LIMIT at the right stage.

## 29. Keyset Endpoint Implementation Checklist

**Step 1:** Identify the entity being paginated: orders, customers, events, or aggregated results.

**Step 2:** Identify mandatory server-enforced filters, permissions, and tenant scope.

**Step 3:** Choose the ordering matching the UI: newest, priority, value, etc.

**Step 4:** Add a unique tie-breaker, typically the primary key.

**Step 5:** Handle NULLs and the ASC/DESC direction of each sort key.

**Step 6:** Write the first-page query and the next-page query with the matching seek predicate.

**Step 7:** Create a B-tree index aligned with the filters and ORDER BY if required by the workload.

**Step 8:** Fetch N+1, return N, and build the cursor from the last returned row.

**Step 9:** Serialize with full precision; sign/verify tokens and bind them to filter/sort settings.

**Step 10:** Support Previous using a reversed query and re-ordering the final rows.

**Step 11:** Define expected behavior when INSERT/UPDATE/DELETE occur between requests.

**Step 12:** Measure `EXPLAIN (ANALYZE, BUFFERS)` on representative data, including deep pages and common filters.

## 30. Self-Study Exercises

### Exercise 1 — OFFSET Page 3

Write SQL to fetch page 3 with pageSize 2 ordered by `created_at DESC,id DESC`.

**Hint:** `LIMIT 2 OFFSET 4`.

### Exercise 2 — Tie-breaker

Why is `ORDER BY created_at DESC` insufficient when IDs 103,104,105 share the same timestamp?

**Hint:** the order among rows with identical timestamps is nondeterministic.

### Exercise 3 — Next Cursor

Page 1 returns `106,105,104`. Write a query to fetch three rows after ID 104.

**Hint:** `(created_at,id) < (TIMESTAMPTZ '2026-02-10 10:04:00+00',104)`.

### Exercise 4 — ASC

With `ORDER BY created_at ASC,id ASC`, should you use `<` or `>` after cursor ID 102?

**Hint:** `>`.

### Exercise 5 — ID-only

Write keyset pagination for `ORDER BY id DESC` with cursor ID 104.

**Hint:** `WHERE id < 104`.

### Exercise 6 — Mixed Sort

The tasks table is sorted `priority DESC,task_id ASC`. Write the predicate after `(3,11)`.

**Hint:** `priority < 3 OR (priority=3 AND task_id>11)`.

### Exercise 7 — NULLS LAST

Shipment cursor `(shipped_at=NULL,shipment_id=4)`. What should the next query filter on?

**Hint:** `shipped_at IS NULL AND shipment_id<4`.

### Exercise 8 — Previous

Given current page `103,102,101`, fetch the three rows immediately before ID 103 and return them in DESC order.

**Hint:** tuple `>`, sort ASC in subquery, sort DESC outside.

### Exercise 9 — Index

Propose an index for `WHERE status='paid' ORDER BY created_at DESC,id DESC`.

**Hint:** `(status,created_at DESC,id DESC)` or a partial index for paid rows.

### Exercise 10 — OFFSET Under Concurrent INSERT

ID 107 is inserted at the top after the client received `106,105,104`. Which IDs will OFFSET 3 return?

**Hint:** `104,103,102`; ID 104 is duplicated.

### Exercise 11 — Keyset Under Concurrent INSERT

In the same scenario, how does keyset continue after ID 104?

**Hint:** independent of position 3; continues with `103,102,101`.

### Exercise 12 — Changing Sort Key

A row receives a newer `updated_at` and moves from a later page ahead of the cursor. Does keyset guarantee no skipped rows?

**Hint:** no.

### Exercise 13 — N+1

An API with pageSize=20 fetches 21 rows. Should the next-page cursor come from the 20th or 21st row?

**Hint:** the 20th returned row.

### Exercise 14 — Precision

A cursor stores milliseconds instead of microseconds. Why can this break?

**Hint:** the comparison value no longer matches the DB value.

### Exercise 15 — Cursor Security

If a Base64 token contains a tenant ID, can the server trust it for authorization?

**Hint:** no; verify the token and enforce authorization from the current session.

### Exercise 16 — Benchmark

Use `generate_series` as in Section 17 and `EXPLAIN (ANALYZE, BUFFERS)` to compare OFFSET 90000 with keyset at the same position.

**Hint:** compare the number of rows/index entries actually traversed and execution time.

### Exercise 17 — COUNT(*)

Does `hasNextPage` from N+1 tell you the total page count?

**Hint:** no; total count requires a separate calculation.

### Exercise 18 — Snapshot

Does a high-water mark guarantee no new row with an older timestamp appears on a later page?

**Hint:** no; it is not a full snapshot.

### Exercise 19 — Numbered Page UI

An admin table of 200 rows supports jumping straight to page 5. Is OFFSET or keyset simpler?

**Hint:** OFFSET may be appropriate when cost is small and ORDER BY is stable.

### Exercise 20 — API Design

Design a `GET /orders` endpoint with a status filter, newest sort, maxPageSize 100, HMAC-signed cursor, and a Previous button.

**Hint:** define keys, first/next/previous queries, N+1, cursor versioning, precision, filter consistency, and authorization.

## 31. Summary

- **OFFSET** paginates by **row position** using `LIMIT ... OFFSET ...`, making numbered pages easy but potentially expensive when skipping very deep offsets.
- **Keyset** paginates by **key values**, avoiding dependence on how many rows precede the page and leveraging indexes to seek efficiently to the next range.
- Both require a deterministic `ORDER BY`. Keyset additionally requires a **unique tie-breaker** and all sort keys in the cursor.
- For `ORDER BY created_at DESC,id DESC`, the next page uses `WHERE (created_at,id) < (:created_at,:id)`; for two ASC columns, use `>`.
- **Mixed ASC/DESC**, **NULLS FIRST/LAST**, and **Previous** require corresponding predicates and query ordering.
- Filters, sort order, tenant, and permissions must stay consistent across pages; cursor tokens must preserve precision and pass integrity verification.
- Choose composite B-tree indexes based on actual queries; verify with `EXPLAIN (ANALYZE, BUFFERS)`.
- Fetch **N+1** rows to detect whether a next page exists, but derive the cursor from the **last row actually returned**.
- Keyset **does not create a snapshot**. Backdated inserts, sort-key updates, or deletes can still change subsequent pages.
- OFFSET remains useful for small tables, numbered pages, and random page jumps. Keyset is usually better suited for large feeds and infinite scroll.

The key is not applying one technique to every query, but **clearly defining the ordering, boundaries, cost, and consistency guarantees the application commits to**. When those factors are clear, PostgreSQL lets you build pagination that is understandable, scalable, and free of the duplication/skipping issues caused by misusing OFFSET.
