# LIMIT, OFFSET, FETCH, and Deterministic Ordering Requirements in PostgreSQL

A PostgreSQL table may contain millions of orders, while an admin screen only wants to show 20 orders at a time. We commonly write `LIMIT` to cap the row count, `OFFSET` to skip leading rows, or standard SQL `FETCH FIRST/NEXT`. However, those clauses **only produce predictable pages when the query explicitly defines row order**.

Example:

```sql
SELECT order_id, created_at
FROM orders
LIMIT 10;
```

This may return 10 rows, yet **makes zero promise that they are the first 10 orders by time, ID, or insertion order**. Even if the same query repeatedly returns the same 10 rows in a lab, that is still not a SQL guarantee.

Adding `ORDER BY created_at DESC` puts newer orders first, yet if multiple orders share the same `created_at`, their relative order remains undefined. That is a common root cause of pagination **duplicating rows, skipping rows, or shifting order** even when the table seems fine.

This lesson belongs to the *Basic Queries* chapter in *Database Engine Relational PostgreSQL* and covers:

- Syntax and semantics of `LIMIT`, `OFFSET`, `FETCH FIRST/NEXT`, and `WITH TIES`.
- Why **without `ORDER BY`, result order is never guaranteed**.
- Adding a unique tie-breaker column to build a **deterministic order**.
- Using `NULLS FIRST/LAST`, multi-column sorting, and handling ties.
- Page-number pagination (*offset pagination*) vs. last-row cursor pagination (*keyset/cursor pagination*).
- Effects of concurrent inserts, deletes, and updates; cost of deep `OFFSET`; indexes supporting sorting.
- Safe API query design, result verification, and practice exercises.

> **Key takeaway:** `LIMIT`/`OFFSET`/`FETCH` do not create ordering. **`ORDER BY` is the baseline requirement**, and `ORDER BY` on non-unique keys is still insufficient for stable pagination. In this lesson, examples using `FETCH ... WITH TIES` assume a PostgreSQL version that supports it (PostgreSQL 13 or newer).

## 1. Understanding Query Results as Unordered Sets by Default

### 1.1. SELECT Does Not Promise Order

Consider:

```sql
SELECT order_id, customer_name
FROM orders;
```

Without `ORDER BY`, PostgreSQL is free to use different execution plans: sequential scan, index scan, parallel scan, joins, or other operators. Those plans can yield different observed row orders.

Points to remember:

- Insertion order is **not** the default `SELECT` order.
- Physical heap row order is **not** an application contract.
- Having an index on `order_id` **does not mean** every `SELECT` returns rows ordered by `order_id`.
- Even after `VACUUM`, `UPDATE`, statistics updates, or plan changes, you must still specify `ORDER BY` whenever order matters.
- **`LIMIT 10`** caps only the number of returned rows; it does not define **which 10 rows** are chosen without ordering.

PostgreSQL might return what looks like a stable order several times in a row; that stability is strictly an **accidental artifact of the current plan**, not a rule you can rely on.

### 1.2. ORDER BY Defines Order, but Tied Keys Still Need Resolution

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC;
```

This guarantees orders with a **larger** timestamp precede orders with a smaller timestamp. However, if three rows share the exact same `created_at`, SQL does not require PostgreSQL to order those three rows by ID, insertion time, or any secondary rule.

To define order within tied timestamps too:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC;
```

If `order_id` is the **PRIMARY KEY**, the pair `(created_at, order_id)` distinguishes every row, giving a **stable total order over the same dataset and comparison semantics**.

### 1.3. Deterministic Order Does Not Mean an Immutable Data Snapshot

Even when `ORDER BY created_at DESC, order_id DESC` is unique, paginated queries running at **two different times** can observe different rows if another transaction inserts, deletes, or updates records.

Distinguish two separate goals:

1. **Deterministic ordering**: given the same row set, key values, and sort specification, order is completely determined.
2. **Consistent pagination across time**: multiple page fetches read against a consistent dataset or follow clear cursor rules.

`ORDER BY` solves goal 1; by itself, it **does not solve goal 2**.

## 2. Creating a Practice Dataset with Duplicate Sort Values

To observe these common pitfalls, use a dedicated orders table:

```sql
CREATE SCHEMA IF NOT EXISTS page_lab;

CREATE TABLE page_lab.orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled'))
);
```

Insert 16 orders; **several orders intentionally share identical timestamps**:

```sql
INSERT INTO page_lab.orders
    (order_id, created_at, customer_name, amount, status)
VALUES
    (101, '2026-11-01 10:00:00+00', 'An',    120000, 'paid'),
    (102, '2026-11-01 10:00:00+00', 'Bình',   85000, 'paid'),
    (103, '2026-11-01 09:00:00+00', 'Chi',   200000, 'new'),
    (104, '2026-11-02 08:00:00+00', 'Dũng',   45000, 'paid'),
    (105, '2026-11-02 08:00:00+00', 'Hà',     99000, 'new'),
    (106, '2026-11-02 08:00:00+00', 'Khánh',  66000, 'paid'),
    (107, '2026-11-03 13:30:00+00', 'Lan',   300000, 'new'),
    (108, '2026-11-03 13:30:00+00', 'Minh',  125000, 'paid'),
    (109, '2026-11-03 13:30:00+00', 'Ngọc',   75000, 'paid'),
    (110, '2026-11-04 07:00:00+00', 'Phúc',   56000, 'new'),
    (111, '2026-11-04 07:00:00+00', 'Quỳnh',  84000, 'paid'),
    (112, '2026-11-05 11:00:00+00', 'Sơn',   150000, 'new'),
    (113, '2026-11-05 11:00:00+00', 'Trang',  70000, 'paid'),
    (114, '2026-11-05 11:00:00+00', 'Uyên',   90000, 'paid'),
    (115, '2026-11-06 12:00:00+00', 'Vy',   105000, 'cancelled'),
    (116, '2026-11-06 12:00:00+00', 'Yến',   40000, 'paid');
```

Timestamps use offset `+00` to represent UTC instants. PostgreSQL stores `TIMESTAMPTZ` as instants and formats them according to the session's `TimeZone`; sorting by `TIMESTAMPTZ` compares the actual instants, not display strings.

Baseline query used throughout:

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC;
```

Deterministic `order_id` sequence:

```text
116, 115, 114, 113, 112, 111, 110, 109,
108, 107, 106, 105, 104, 102, 101, 103
```

This order comes from **two `ORDER BY` keys**: descending timestamp first; when timestamps tie, descending `order_id`.

> These IDs and timestamps are explicit lab data to make verifying outputs easy. Never assume this ordering comes automatically from `INSERT` order or `PRIMARY KEY` when `SELECT` omits `ORDER BY`.

## 3. LIMIT: Returning at Most N Rows

`LIMIT` is the widely used PostgreSQL clause to cap returned row counts:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Result on the lab dataset:

| Position | order_id |
|---:|---:|
| 1 | 116 |
| 2 | 115 |
| 3 | 114 |
| 4 | 113 |
| 5 | 112 |

**`LIMIT 5` means return at most five rows** after PostgreSQL applies the relevant filters and ordering. If only three rows match, three rows are returned. It does not pad rows or raise an error when fewer than five rows exist.

### 3.1. LIMIT with WHERE

```sql
SELECT order_id, amount, status
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

PostgreSQL finds rows satisfying `status = 'paid'`, then returns **at most the first five rows in the requested order**. Never think of `LIMIT 5` as "grab any five rows first, then filter by status."

Standard syntactic clause order is:

```sql
SELECT ...
FROM ...
WHERE ...
ORDER BY ...
LIMIT ...;
```

Do not place `LIMIT` before `ORDER BY` within the same `SELECT`.

### 3.2. LIMIT 0, LIMIT ALL, and Invalid Negative Values

```sql
-- Returns zero rows.
SELECT order_id FROM page_lab.orders ORDER BY order_id LIMIT 0;

-- Places no upper row limit via LIMIT.
SELECT order_id FROM page_lab.orders ORDER BY order_id LIMIT ALL;
```

`LIMIT 0` is handy for expressing an empty result set or inspecting query result metadata/columns. `LIMIT ALL` behaves like omitting `LIMIT` (while still honoring `OFFSET` if present).

Never use `LIMIT -5`: negative values are invalid. When an application accepts `page_size` from a client, validate and cap the page size before passing it into SQL.

### 3.3. LIMIT Without ORDER BY Does Not Produce "Top N"

```sql
SELECT order_id FROM page_lab.orders LIMIT 5;
```

This only asks for **some five rows** produced by the execution plan—not "the five newest orders" or "the five smallest IDs."

To get the top 5 by order amount:

```sql
SELECT order_id, amount
FROM page_lab.orders
ORDER BY amount DESC, order_id DESC
LIMIT 5;
```

If two orders tie on `amount`, `order_id DESC` breaks the tie; without that secondary column, the placement of tied rows would be undefined.

## 4. OFFSET: Skipping the First N Rows of the Sorted Set

`OFFSET N` skips the first N rows before returning the rest, following the query's defined order.

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

Second-page result on the lab dataset:

| Sorted Position | order_id |
|---:|---:|
| 6 | 111 |
| 7 | 110 |
| 8 | 109 |
| 9 | 108 |
| 10 | 107 |

`OFFSET 5` skips the first five rows; `LIMIT 5` takes the next five. A query cannot know what "page two" means unless you specify **page two of which order**.

### 4.1. Page-Number Pagination Formula

With 1-based page numbers:

\[
\text{offset}=(\text{page}-1)\times \text{pageSize}
\]

Example with `pageSize = 5`:

| Page | LIMIT | OFFSET | Expected `order_id`s |
|---:|---:|---:|---|
| 1 | 5 | 0 | 116, 115, 114, 113, 112 |
| 2 | 5 | 5 | 111, 110, 109, 108, 107 |
| 3 | 5 | 10 | 106, 105, 104, 102, 101 |
| 4 | 5 | 15 | 103 |
| 5 | 5 | 20 | No rows |

Page 1:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;
```

Page 3:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 10;
```

If `OFFSET` exceeds the number of matching rows, the result is empty—which is normally valid API behavior.

### 4.2. OFFSET 0 and OFFSET Without LIMIT

`OFFSET 0` skips zero rows:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY order_id
OFFSET 0;
```

PostgreSQL allows `OFFSET` without `LIMIT`:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY order_id
OFFSET 10;
```

The second query skips the first ten rows and returns **all remaining rows**, not ten rows by default. Do not forget `LIMIT` when an API is meant to return only one small page.

### 4.3. Negative OFFSET and Invalid Values

`OFFSET -1` is invalid. `NULL` or ad-hoc values should not be treated as standard API inputs; pass clear integers validated by application logic.

For client-supplied page numbers and page sizes, enforce:

- `page` must be a positive integer (for 1-based paging).
- `pageSize` must be a positive integer capped at a **maximum threshold**.
- Offset must be computed in a wide enough integer type to avoid overflow.
- Very deep pages may be restricted due to processing cost and product requirements.

## 5. FETCH FIRST and FETCH NEXT: Standard SQL Syntax

PostgreSQL supports the `FETCH` clause to request the first or next N rows:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 5 ROWS ONLY;
```

Equivalent in goal to:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Alternative form:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH NEXT 5 ROWS ONLY;
```

In `FETCH`, both `FIRST` and `NEXT` are accepted with the same row-limiting meaning. **`FETCH NEXT` does not remember the previous page**: to skip earlier rows, you still need `OFFSET` or a cursor predicate.

### 5.1. OFFSET ... FETCH NEXT ...

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
OFFSET 5 ROWS
FETCH NEXT 5 ROWS ONLY;
```

Equivalent statement:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

`OFFSET 5 ROWS` is standard SQL syntax; with `LIMIT`, PostgreSQL also accepts `OFFSET 5`. Several other DBMSs support `FETCH` without supporting PostgreSQL-style `LIMIT`.

### 5.2. FIRST ROW and FIRST 1 ROWS

PostgreSQL accepts:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST ROW ONLY;
```

When the count is omitted in `FETCH FIRST ROW ONLY`, it defaults to **one row**. You can also write it explicitly:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 1 ROW ONLY;
```

### 5.3. Do Not Mix LIMIT and FETCH in the Same SELECT

`LIMIT` and `FETCH FIRST/NEXT` are two ways to specify a **row limit** on a `SELECT`. Never combine both in the same `SELECT`:

```sql
-- Do not use mixed syntax like this:
-- SELECT * FROM page_lab.orders
-- ORDER BY order_id
-- LIMIT 5 FETCH FIRST 5 ROWS ONLY;
```

Pick one style: `LIMIT ... OFFSET ...` for familiar PostgreSQL style, or `OFFSET ... FETCH ...` when standard SQL/portability is desired.

## 6. FETCH ... WITH TIES: Including Tied Rows at the Boundary

An important variant is **`WITH TIES`**. Instead of cutting off at an exact row count, PostgreSQL returns additional rows that **tie on the entire `ORDER BY` expression list** with the final row inside the limit.

Example:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
FETCH FIRST 3 ROWS WITH TIES;
```

In the lab dataset:

- Two orders (`116` and `115`) have `created_at = '2026-11-06 12:00:00+00'`.
- Three orders (`114`, `113`, `112`) have `created_at = '2026-11-05 11:00:00+00'`.
- The third row under `created_at DESC` belongs to the Nov 5 group; **all tied rows in that group** are included.

Therefore, the query returns **five rows** (`116`, `115`, and `114`, `113`, `112`), even though it says `FETCH FIRST 3 ROWS WITH TIES`.

**Note:** Within each group sharing `created_at`, ID order is still undefined because `ORDER BY` only lists the timestamp. To display IDs deterministically while preserving "all rows tied on timestamp", wrap the result in a subquery/CTE and sort outside:

```sql
WITH top_timestamps AS (
    SELECT order_id, created_at
    FROM page_lab.orders
    ORDER BY created_at DESC
    FETCH FIRST 3 ROWS WITH TIES
)
SELECT order_id, created_at
FROM top_timestamps
ORDER BY created_at DESC, order_id DESC;
```

`WITH TIES` determines **which rows belong at the boundary** under the inner order; the outer `ORDER BY` presents those selected rows in deterministic order.

### 6.1. Why Adding order_id to ORDER BY Eliminates Ties

Consider:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Because `order_id` is the primary key, **no two rows share the full sort key** `(created_at, order_id)`. Only three rows are returned.

This marks a crucial distinction between two goals:

- **Pagination with exact page size and unique order:** add a tie-breaker so the order is deterministic.
- **Fetching all rows tied on a business metric:** include only the ranking expressions in the `ORDER BY` of `FETCH ... WITH TIES`, then sort further in an outer query if needed.

Do not ask for "all rows tied on score" while simultaneously putting a unique ID into the ranking key list and expecting `WITH TIES` to return tied rows.

### 6.2. WITH TIES Requires ORDER BY

In PostgreSQL, `FETCH FIRST N ROWS WITH TIES` requires an `ORDER BY` clause. Without an ordering, "tied with the last row" is undefined.

```sql
-- Missing ORDER BY: invalid syntax/semantics for WITH TIES.
-- SELECT * FROM page_lab.orders FETCH FIRST 3 ROWS WITH TIES;
```

### 6.3. WITH TIES Is Unsuitable for APIs Requiring Exactly N Rows

An endpoint advertising `pageSize = 20` usually expects **at most 20 items**. `WITH TIES` can return 21, 50, or more rows if many rows tie at the boundary. Never use `WITH TIES` as the default for page-number pagination.

It fits **top-N with ties** queries, such as "fetch every athlete tied with the third-place score." When business rank numbers are needed, also consider `RANK()`/`DENSE_RANK()` and specify tie rules clearly.

## 7. ORDER BY: How to Build a Deterministic Order

### 7.1. Sorting by One Column Is Often Insufficient

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
LIMIT 5;
```

This expresses "newest timestamps first", yet rows `116` and `115` share a timestamp, and `114`, `113`, `112` also share a timestamp. Order within each tied group **is unspecified**.

A learner might see ID 116 before 115 on one run and infer PostgreSQL defaults to descending ID. That inference has no guarantee.

### 7.2. Adding a Unique Tie-Breaker Column

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Because `order_id` is unique, every row has a fixed position for the same dataset:

```text
116, 115, 114, 113, 112
```

The tie-breaker does not have to be named `id`. You can use:

- An integer primary key.
- A unique UUID, if its sort order is stable and fits business needs.
- A unique combination of columns, provided it **truly distinguishes** every returned row and NULL/collation rules are handled.

If the tie-breaker itself allows duplicates, the order is still not completely deterministic.

### 7.3. Same-Direction and Mixed-Direction Keys

```sql
-- Highest amount first; on equal amounts, larger ID first.
SELECT order_id, amount
FROM page_lab.orders
ORDER BY amount DESC, order_id DESC
LIMIT 5;

-- Ascending status name, newest timestamp first,
-- smaller ID first when status and timestamp tie.
SELECT order_id, status, created_at
FROM page_lab.orders
ORDER BY status ASC, created_at DESC, order_id ASC
LIMIT 8;
```

Each `ORDER BY` expression chooses `ASC` or `DESC` independently. In keyset pagination, **mixed-direction ordering** requires more careful cursor predicates than same-direction tuple comparisons.

### 7.4. ORDER BY NULLS FIRST/LAST

PostgreSQL lets you control `NULL` placement:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC NULLS LAST, order_id DESC;
```

In the lab table `created_at` is `NOT NULL`, so `NULLS LAST` does not change output here, yet it is crucial when real data contains unknown timestamps.

PostgreSQL defaults:

| Sort Clause | Default NULL Placement |
|---|---|
| `ORDER BY col ASC` | `NULLS LAST` |
| `ORDER BY col DESC` | `NULLS FIRST` |

To put newest first while pushing unknown dates to the end:

```sql
SELECT *
FROM (
    VALUES
        (1, TIMESTAMPTZ '2026-11-02 08:00:00+00'),
        (2, NULL::TIMESTAMPTZ),
        (3, TIMESTAMPTZ '2026-11-04 08:00:00+00'),
        (4, NULL::TIMESTAMPTZ)
) AS x(order_id, created_at)
ORDER BY created_at DESC NULLS LAST, order_id DESC;
```

Expected ID order: `3, 1, 4, 2`. Both `NULL` rows tie on `created_at` and are ordered by `order_id DESC`.

### 7.5. Collations and Expressions Also Affect Sort Keys

With strings:

```sql
SELECT order_id, customer_name
FROM page_lab.orders
ORDER BY lower(customer_name), order_id;
```

`lower(customer_name)` can produce identical strings for names differing only in case. Hence `order_id` is still needed as a tie-breaker for deterministic output.

**Collation** governs how text is compared and sorted. Under certain collations, two byte-distinct strings can compare equal. For stable pagination, always include a unique tie-breaker and ensure sessions/clients use consistent sort rules. Never assume collation library upgrades or locale changes have zero impact.

### 7.6. Outer ORDER BY Determines Final Result Order

An `ORDER BY` inside a subquery/CTE does not mean the **outer query** always preserves that order after joins, aggregations, or other transformations:

```sql
SELECT order_id
FROM (
    SELECT order_id, created_at
    FROM page_lab.orders
    ORDER BY created_at DESC
) AS x
LIMIT 5;
```

Never rely on inner ordering as a pagination contract. Place `ORDER BY` at the `SELECT` level **where the final `LIMIT`/`OFFSET` is applied**, or design bounded inner subqueries with intentional outer ordering.

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Similarly, after `UNION`, `DISTINCT`, or `GROUP BY`, final ordering still requires an `ORDER BY` on the query returning rows to the client whenever order is promised.

## 8. Why LIMIT/OFFSET Without Unique Ordering Causes Duplicates or Missing Rows

Suppose a query runs:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
LIMIT 3 OFFSET 0;
```

When timestamps tie, the server only has to maintain order **between timestamp groups**, and is free to order rows **within a group** however it likes. A second query:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
LIMIT 3 OFFSET 3;
```

has no guarantee that rows inside tied groups appear in the same order as the first query—especially if the optimizer picks a different plan for a different `LIMIT`/`OFFSET`. Combining pages can duplicate or skip rows **even when zero data changed** if there is no total order.

Basic fix:

```sql
-- Page 1
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 0;

-- Page 2
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

Against the same snapshot, `order_id` resolves ties so pages never overlap due to sort-key ties.

### 8.1. Is ORDER BY on a Unique Column Enough?

If `order_id` is a non-`NULL` primary key:

```sql
ORDER BY order_id DESC
```

is enough to establish a unique total order. However, if the business requirement is **newest orders first**, sorting solely by ID does not necessarily match creation time; IDs may be imported, allocated out of order, or backfilled for historical data.

Choose the **primary sort key matching business semantics**, then append a **unique column as a tie-breaker**.

### 8.2. Sorting on High-Cardinality Tables with Low-Cardinality Columns

The `status` column has three values: `new`, `paid`, `cancelled`. This query:

```sql
SELECT order_id, status
FROM page_lab.orders
ORDER BY status
LIMIT 5;
```

orders status groups, yet rows within each status have no unique order. If you genuinely want to paginate by status:

```sql
SELECT order_id, status
FROM page_lab.orders
ORDER BY status ASC, order_id DESC
LIMIT 5;
```

## 9. Fetching Subsequent Pages with LIMIT/OFFSET: Simple, but Has Costs

An API might accept two parameters:

```text
GET /orders?page=3&pageSize=20
```

For 1-based `page`, offset is `(3-1)*20 = 40`:

```sql
SELECT order_id, created_at, customer_name, amount
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;
```

Advantages of this design:

- Easy to understand page numbers 1, 2, 3.
- Supports jumping directly to any page number.
- Practical for small tables, few pages, or low-churn data.

However, it has two limitations:

1. **Deep offsets are expensive:** the server must walk through and discard all rows preceding the offset.
2. **Data mutates between requests:** row positions shift, causing duplicates or skipped rows across pages.

### 9.1. Large OFFSET Is Not a "Free Jump" to Row N

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Logically, the query must locate **at least the first 100,020 positions** in sorted order to skip 100,000 and return 20, assuming enough rows exist. A matching index can provide sorted order and avoid an expensive full sort, yet **the engine still scans and skips many entries**.

Consequently, page 5000 with `pageSize = 20` can be noticeably slower than page 1. Never assume `LIMIT 20` means PostgreSQL only reads or touches 20 rows.

### 9.2. Indexes Supporting ORDER BY

For the query pattern:

```sql
SELECT order_id, created_at, amount
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

you can consider a B-tree index:

```sql
CREATE INDEX orders_created_id_desc_idx
ON page_lab.orders (created_at DESC, order_id DESC);
```

This index matches the `ORDER BY` ordering. PostgreSQL can use an index scan to retrieve the leading rows without sorting the whole table, depending on table size, statistics, and cost.

**The lab table has only 16 rows**, so the optimizer may still pick sequential scan + sort. That does not mean the index is useless on a large production table.

### 9.3. Filtering by Status and Sorting Together

Query:

```sql
SELECT order_id, created_at, amount
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

A better-fitting index could be:

```sql
CREATE INDEX orders_status_created_id_idx
ON page_lab.orders (status, created_at DESC, order_id DESC);
```

Because `status` uses an equality filter, the index can jump to the matching status group already sorted by timestamp and ID. However, indexes consume storage, add `INSERT`/`UPDATE` overhead, and may not help if `status` is heavily skewed or the query runs rarely.

Never create indexes blindly by copying examples. Measure real workloads, query frequency, selectivity, and write costs.

### 9.4. Reading Execution Plans

```sql
EXPLAIN
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

To measure actual runtime and I/O:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

`EXPLAIN ANALYZE` **actually executes the query** to gather metrics; for read-only `SELECT`s it is safe to test in controlled environments, while write commands require extreme caution. Comparing `OFFSET 0` vs. `OFFSET 100000` on a large table reveals the real difference; the 16-row demo is purely for learning syntax.

## 10. Keyset Pagination: Resuming After the Last Page Key

When scrolling long lists, users usually want "20 more items after what I already see" rather than jumping to an **absolute page number**. Keyset (or *seek*) pagination uses the **sort-key values of the previous page's last row** as a cursor.

Instead of:

```sql
SELECT ...
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

we ask:

> "Give me the five rows that come **after** the `(created_at, order_id)` key pair where the previous page ended."

### 10.1. First Page Without a Cursor

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

On the lab dataset, page 1 is:

```text
116, 115, 114, 113, 112
```

The last row has:

```text
created_at = 2026-11-05 11:00:00+00
order_id   = 112
```

Save **both values** as the cursor. Never save only the timestamp, since multiple rows can share that timestamp.

### 10.2. Next Page with Descending ORDER BY

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-05 11:00:00+00', 112)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Result:

```text
111, 110, 109, 108, 107
```

Because both columns are sorted **DESC**, rows coming after `(T, ID)` are those where:

- `created_at < T`, **or**
- `created_at = T` and `order_id < ID`.

The tuple comparison `(created_at, order_id) < (T, ID)` evaluates **left to right**, matching the descending sort order in this example.

### 10.3. Writing the Equivalent Condition with OR

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
WHERE created_at < TIMESTAMPTZ '2026-11-05 11:00:00+00'
   OR (
       created_at = TIMESTAMPTZ '2026-11-05 11:00:00+00'
       AND order_id < 112
   )
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Both forms are equivalent when compared columns are **non-NULL**, support comparison operators, and share the same `DESC` direction. The `OR` form makes it visually obvious why a tie-breaker is required.

### 10.4. Page Three Using the Next Cursor

Page two ends at `order_id = 107`, `created_at = '2026-11-03 13:30:00+00'`:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-03 13:30:00+00', 107)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Result:

```text
106, 105, 104, 102, 101
```

The following page returns `order_id = 103` and then ends. This mechanism avoids `OFFSET 10` or `OFFSET 15`; it seeks directly from the **actual landmark of the previous page**.

### 10.5. ASC Flips the Comparison Operator

If sorting ascending:

```sql
ORDER BY created_at ASC, order_id ASC
```

then rows **after** cursor `(T, ID)` satisfy:

```sql
WHERE (created_at, order_id) > (T, ID)
```

Never blindly copy `<` from a DESC query into an ASC query. Using the wrong sign sends pagination backward or returns the wrong slice.

### 10.6. Mixed Directions Require a Different Predicate

With:

```sql
ORDER BY created_at DESC, order_id ASC
```

the predicate for rows **after** cursor `(T, ID)` is:

```sql
WHERE created_at < T
   OR (created_at = T AND order_id > ID)
```

Here, writing `(created_at, order_id) < (T, ID)` directly is **wrong**, because standard tuple comparison applies the same direction to both components, whereas the query sorts **DESC on time but ASC on ID**.

Query example with a hypothetical cursor:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE created_at < TIMESTAMPTZ '2026-11-05 11:00:00+00'
   OR (
       created_at = TIMESTAMPTZ '2026-11-05 11:00:00+00'
       AND order_id > 113
   )
ORDER BY created_at DESC, order_id ASC
LIMIT 5;
```

In production, construct cursors from **all `ORDER BY` expressions**, their directions, NULL handling, and active collations, then build the corresponding seek predicate.

### 10.7. Keyset Requires Non-NULL Keys or Explicit NULL Handling

Our example uses `created_at TIMESTAMPTZ NOT NULL` and `order_id PRIMARY KEY`, because row comparisons with `NULL` do not follow a simple `<`/`>` total order.

If a sort key is nullable:

- Define the `NULLS FIRST` or `NULLS LAST` policy.
- Define how cursors encode `NULL` rows.
- Write explicit predicates transitioning between non-NULL and NULL regions.
- Use a non-NULL unique tie-breaker.

Never apply a naive tuple comparison to nullable columns and expect `NULL` rows to come through. Depending on scale, you might maintain a normalized non-null sort key, after evaluating semantics and indexing.

### 10.8. When Does Keyset Fit Best?

| Requirement | LIMIT/OFFSET | Keyset |
|---|---|---|
| Fetching pages 1, 2, 3 on small tables | Simple | Requires cursor |
| Jumping directly to page 500 | Supported by syntax | Cannot jump directly to arbitrary page numbers |
| Infinite scroll feeds/logs/orders | Possible, yet offset grows | Usually a better fit |
| Very large tables, deep pagination | Can become slow | Can seek efficiently via index |
| New rows inserted at the top between fetches | Prone to offset drift | Less affected if sort keys are stable |
| Mixed sort directions or nullable keys | `ORDER BY` is easier to write | Cursor and seek conditions are more complex |
| Strict point-in-time snapshot required | Not guaranteed | Also not guaranteed |

**Keyset is not "OFFSET, only faster for every query."** It is a different API model that trades random page jumping for key-based forward/backward seeking.

## 11. Pagination Under Concurrent Inserts, Deletes, or Updates

Real applications rarely hold a table static between page 1 and page 2.

### 11.1. New INSERT at the Top Shifts OFFSET

Suppose IDs currently order as:

```text
Initial Page 1: [116, 115, 114, 113, 112]
Initial Page 2: [111, 110, 109, 108, 107]
```

After the client loads page 1, another transaction inserts order `117` with a newer timestamp than all others.

New order:

```text
[117, 116, 115, 114, 113, 112, 111, 110, ...]
```

When the client calls `LIMIT 5 OFFSET 5` against the updated state, position 6 is now **112**, which already appeared at the bottom of page 1. Row **112 gets duplicated** across pages.

**An `ORDER BY` with a unique ID does not prevent this**, because the cause is the **mutating dataset**, not ties between sort keys.

### 11.2. Earlier DELETE Causes OFFSET to Skip Rows

With the same page 1 loaded, if a row above the boundary is deleted before page 2 runs, later rows shift upward. Skipping five positions causes the client to **miss an unread row**.

For example, deleting ID 116 after page 1 leaves `115,114,113,112,111,110,...`. Page 2 with `OFFSET 5` starts at `110`, skipping ID `111` which never appeared on page 1.

### 11.3. Keyset Reduces Drift, but Does Not Freeze the Snapshot

With page 1's end cursor `(2026-11-05 11:00:00+00, 112)`:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-05 11:00:00+00', 112)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

A newly inserted order **ahead** of the cursor does not alter where the next page starts. However:

- An older row that was deleted will no longer be returned.
- A row whose `created_at` changes can cross the cursor boundary and be skipped or duplicated across fetches.
- A newly inserted row with a timestamp **older than the cursor** can still appear on a later page.
- Changes to filter columns (such as `status`) can cause rows to enter or leave the result set.

Thus keyset is **more resilient to top-of-list insertions**, not a magic mechanism providing a "permanent frozen snapshot of the list."

### 11.4. MVCC and Isolation Levels

PostgreSQL uses MVCC (*Multi-Version Concurrency Control*). Under standard `READ COMMITTED` isolation, **each statement** sees a fresh snapshot. Two separate HTTP pagination requests normally run in separate transactions and can therefore see changes committed in between.

Inside a `REPEATABLE READ` transaction, PostgreSQL maintains a consistent snapshot for queries within that transaction, shielding it from external commits for the transaction's duration:

```sql
-- Illustration of a controlled read transaction.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;

SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;

COMMIT;
```

However, **never hold a transaction open for minutes or hours just while a user scrolls pages**: long-lived transactions retain old snapshots, impeding vacuum, resources, and operations.

If the business requires a **frozen result set** for report exports, design explicit snapshots, materialized ID lists, export jobs, or dedicated consistent read workflows rather than expecting `OFFSET`/`keyset` to solve it.

### 11.5. Reading from Multiple Replicas

If paginated requests hit **different read replicas** or a replica experiences replication lag, clients can observe differing data states even with unique sort keys.

When consistency matters, pair routing/read-consistency policies with an understanding of replication lag. Choosing a solid `ORDER BY` is necessary, yet does not replace system-wide read consistency design.

## 12. COUNT(*) and Total Page Count

Numbered pagination UIs often display:

```text
Page 3 / 25 — 487 orders
```

To calculate page count, you first need the number of rows matching the **exact same filter**:

```sql
SELECT COUNT(*) AS total_rows
FROM page_lab.orders
WHERE status = 'paid';
```

If `pageSize = 20` and `total_rows = 487`, total pages is:

\[
\operatorname{totalPages}
=\left\lceil\frac{\operatorname{totalRows}}{\operatorname{pageSize}}\right\rceil
=\left\lceil\frac{487}{20}\right\rceil
=25
\]

### 12.1. Filters on COUNT and SELECT Must Match

If the list fetches only `paid` orders:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;
```

then `COUNT(*)` must also include `WHERE status = 'paid'`. Counting all orders while paginating only paid ones displays wrong page totals.

### 12.2. Counting and Fetching in Two Queries Can See Two Snapshots

Under `READ COMMITTED`, two statements can observe commits occurring between them. Thus `COUNT(*)` might report 487 at count time, while 488 or 486 matching orders exist when the page query executes.

If an API needs a total count **strictly bound to the exact same snapshot** as the page rows, use an appropriate transaction isolation level or combined query—never assume two standalone `SELECT`s always match perfectly.

### 12.3. COUNT(*) OVER() in a Paginated Query

You can use a window function:

```sql
SELECT
    order_id,
    created_at,
    COUNT(*) OVER () AS total_rows
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;
```

`COUNT(*) OVER ()` returns the total filtered row count before `LIMIT`. However:

- It may process more rows than a page-only query, increasing cost on large tables.
- If `OFFSET` goes past all rows, the query returns **zero rows**, meaning **no `total_rows` cell** is returned either.
- It does not protect `OFFSET` pagination against mutations between subsequent requests.

This is a trade-off to evaluate, not a rule that "replacing two queries with one is always faster."

### 12.4. Not Every API Needs Total Pages

For infinite scroll, clients typically only need:

- Items on the current page.
- A cursor to fetch the next page.
- Whether another page exists.

A common trick is requesting `pageSize + 1` rows to detect whether more rows remain, returning at most `pageSize` items to the client:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 6;
```

If `pageSize` is 5 and 6 rows come back, at least one more row existed **at query time**. Use the 5th row as the next cursor; the 6th row serves purely as a "has more" signal. Under concurrent writes, that signal can still change by the time the next request arrives.

## 13. Pagination with ROW_NUMBER(): When Position Numbering Is Needed

`ROW_NUMBER()` assigns sequential numbers according to a window `ORDER BY`:

```sql
WITH numbered AS (
    SELECT
        order_id,
        created_at,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM page_lab.orders
)
SELECT order_id, created_at, rn
FROM numbered
WHERE rn BETWEEN 6 AND 10
ORDER BY rn;
```

The output matches page two on the lab dataset for `pageSize = 5`.

**There are two `ORDER BY` clauses at two layers:**

1. `ORDER BY` inside `OVER` defines how `rn` is assigned.
2. `ORDER BY rn` in the outer query defines the **final returned row order**.

Do not drop the `order_id` tie-breaker in the window if you want deterministic row numbers across identical `created_at` values.

### 13.1. When Is ROW_NUMBER Useful?

It shines when you need:

- Explicit row numbers on each row in a result.
- Top-ranked items per group using `PARTITION BY`.
- Position columns displayed in reports.

On large tables, computing and filtering `rn` is not necessarily faster than `LIMIT/OFFSET` or keyset, since PostgreSQL may have to rank many rows before filtering a slice. Check with `EXPLAIN`.

### 13.2. ROW_NUMBER vs. RANK and DENSE_RANK

When two orders share the same `amount`:

```sql
SELECT
    order_id,
    amount,
    ROW_NUMBER() OVER (ORDER BY amount DESC, order_id DESC) AS rn,
    RANK() OVER (ORDER BY amount DESC) AS business_rank,
    DENSE_RANK() OVER (ORDER BY amount DESC) AS dense_business_rank
FROM page_lab.orders;
```

`ROW_NUMBER` with ID as tie-breaker gives each row a distinct number. `RANK` and `DENSE_RANK` over `amount` give tied amounts the same rank, differing in whether subsequent ranks skip numbers. When asked for **"top 3 score tiers, including ties"**, clarify whether you want boundary ties via `WITH TIES` or rank tiers via `RANK`/`DENSE_RANK`.

## 14. DISTINCT, GROUP BY, and UNION Do Not Replace ORDER BY

Some developers assume these clauses "automatically sort":

```sql
SELECT DISTINCT status
FROM page_lab.orders
LIMIT 2;
```

There is no guarantee of getting "the first two statuses alphabetically." Make it explicit:

```sql
SELECT DISTINCT status
FROM page_lab.orders
ORDER BY status ASC
LIMIT 2;
```

Similarly:

```sql
SELECT status, COUNT(*) AS so_don
FROM page_lab.orders
GROUP BY status
ORDER BY so_don DESC, status ASC
LIMIT 2;
```

`GROUP BY` does not guarantee output order. `ORDER BY so_don DESC, status ASC` includes a tie-breaker in case two statuses have identical counts; `status` is unique after grouping by `status`.

### 14.1. Sort the Combined Result After UNION

```sql
SELECT order_id FROM page_lab.orders WHERE status = 'new'
UNION
SELECT order_id FROM page_lab.orders WHERE status = 'paid'
ORDER BY order_id DESC
LIMIT 5;
```

The trailing `ORDER BY` sorts the combined `UNION` output. Putting `LIMIT` inside each individual branch via subqueries means something completely different: each branch is capped **before** combining.

### 14.2. DISTINCT ON Needs Ordering to Pick Representative Rows

PostgreSQL supports `DISTINCT ON`:

```sql
SELECT DISTINCT ON (status)
    status, order_id, created_at
FROM page_lab.orders
ORDER BY status, created_at DESC, order_id DESC;
```

This picks **one representative row per status**, favoring newest timestamp and then largest ID. Omitting the secondary keys leaves the representative row nondeterministic on timestamp ties—the exact same tie-breaker lesson, even without `LIMIT`.

## 15. Writing Safe Paginated Queries from Applications

Never splice `LIMIT`/`OFFSET` values directly from request strings into SQL without type and range checks. Bind parameters and validate inputs.

### 15.1. Prepared Statements in PostgreSQL

```sql
PREPARE page_orders(INTEGER, INTEGER) AS
SELECT order_id, created_at, customer_name, amount
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT $1 OFFSET $2;

EXECUTE page_orders(5, 0);
EXECUTE page_orders(5, 5);

DEALLOCATE page_orders;
```

`$1` is page size, `$2` is offset. They are **data values**, not SQL column names; if users can choose sort keys, bind parameters cannot substitute arbitrary identifiers into `ORDER BY`.

### 15.2. Java JDBC with LIMIT/OFFSET

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderQueries {
    public static void readPage(
            Connection connection, int page, int pageSize
    ) throws SQLException {
        if (page < 1 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException(
                "page >= 1 and pageSize must be between 1 and 100"
            );
        }

        long offset = ((long) page - 1L) * pageSize;

        String sql = """
            SELECT order_id, created_at, customer_name, amount
            FROM page_lab.orders
            ORDER BY created_at DESC, order_id DESC
            LIMIT ? OFFSET ?
            """;

        try (PreparedStatement stmt =
                 connection.prepareStatement(sql)) {
            stmt.setInt(1, pageSize);
            stmt.setLong(2, offset);

            try (ResultSet rs = stmt.executeQuery()) {
                while (rs.next()) {
                    System.out.println(rs.getLong("order_id"));
                }
            }
        }
    }
}
```

This uses Java text blocks (Java 15+). `offset` is calculated as `long` to avoid `int` multiplication overflow. Real apps should also cap maximum allowed offset and apply timeouts/resource budgets rather than letting clients request arbitrarily deep pages.

### 15.3. Letting Clients Choose ORDER BY Without SQL Injection

A request might pass:

```text
GET /orders?sort=created_at&direction=desc&page=1
```

Column names and directions must never be concatenated from unchecked strings. Use an **allowlist**:

| Allowed Sort Option | Server-Generated ORDER BY |
|---|---|
| `created_at_desc` | `created_at DESC, order_id DESC` |
| `amount_desc` | `amount DESC, order_id DESC` |
| `order_id_asc` | `order_id ASC` |

Every final sort key list must be deterministic. Reject unsupported sort options or restricted fields rather than interpolating raw input as column names, expressions, or SQL clauses.

### 15.4. What Should a Keyset Cursor Contain?

A cursor might encode:

```json
{
  "createdAt": "2026-11-05T11:00:00Z",
  "orderId": 112,
  "sort": "created_at_desc_order_id_desc"
}
```

In production APIs, however:

- Tie cursors to the **sort mode**, active filters, and format version.
- Do not allow clients to tamper with cursors if doing so affects security or access rules; sign or integrity-check cursors if needed.
- Never embed secrets or sensitive data in plain base64 cursors, since base64 is **not encryption**.
- All sort values governing resumption must be stored or reconstructed reliably.
- Changing collations, sort options, or filters can invalidate older cursors.

A cursor is a **logical position in a sort order**, not a physical row number or PostgreSQL file byte offset.

## 16. Summary Table: LIMIT, OFFSET, FETCH, and Keyset

| Use Case | SQL Pattern | Strengths | Limitations |
|---|---|---|---|
| Top N rows | `ORDER BY ... LIMIT N` | Concise, idiomatic | Non-unique sort makes boundary rows arbitrary |
| Page K | `ORDER BY ... LIMIT N OFFSET M` | Direct jump by page number | Deep offsets are costly; inserts cause drift |
| Standard SQL syntax | `ORDER BY ... OFFSET M ROWS FETCH NEXT N ROWS ONLY` | Readable, portable SQL | Same sorting/offset trade-offs as `LIMIT` |
| Top N with ties | `ORDER BY score DESC FETCH FIRST N ROWS WITH TIES` | Keeps all rows tied on boundary key | Can return > N rows; tie order undefined |
| Cursor scrolling | `WHERE (sort_key,id) < (:last_key,:last_id) ORDER BY ... LIMIT N` | Efficient and resilient to top inserts | No random page jumps; complex with nulls/mixed sort |
| Row numbering | `ROW_NUMBER() OVER (ORDER BY ...)` | Great for explicit rank/position numbers | May process many rows; still needs tie-breaker |

**Every** one of these patterns requires clearly defining **"first" according to which order**. `FETCH WITH TIES` additionally requires specifying "tied" according to which expressions.

## 17. Common Mistakes

**1. "`LIMIT 10` gives the 10 most recently inserted rows."** False. Without `ORDER BY`, nothing is guaranteed.

**2. "There is a primary key, so `SELECT` returns rows in primary-key order."** False. PostgreSQL can choose other access plans.

**3. "`ORDER BY created_at DESC` is always stable enough."** Not when multiple rows share timestamps; append a unique tie-breaker.

**4. "`LIMIT/OFFSET` keeps tied rows in the same order across pages."** Not guaranteed unless `ORDER BY` establishes a total order.

**5. "A unique `ORDER BY` prevents duplicates across pages when `INSERT`s happen."** False. Offsets shift when the dataset changes.

**6. "`OFFSET` jumps straight to row N for free."** False. PostgreSQL still must identify and skip preceding rows.

**7. "`FETCH NEXT 10` remembers the last fetched page."** False. You still need `OFFSET` or a cursor.

**8. "`FETCH FIRST 10 ROWS ONLY` and `WITH TIES` always return the same number of rows."** False. `WITH TIES` can return extra tied rows.

**9. "Adding a unique ID to `ORDER BY` still keeps all tied scores under `WITH TIES`."** False. Including ID breaks ties across the full `ORDER BY` list.

**10. "`ORDER BY DESC` puts NULLs last automatically."** In PostgreSQL, `DESC` defaults to `NULLS FIRST`; specify `NULLS LAST` explicitly.

**11. "A single tuple `<` comparison works for mixed ASC/DESC sorts."** False. Mixed directions require explicit seek predicates.

**12. "Row comparisons with NULL pass NULL rows through cleanly."** False. SQL uses three-valued logic; NULLs require explicit handling.

**13. "`ROW_NUMBER() OVER (ORDER BY ...)` guarantees output order without an outer `ORDER BY`."** Never rely on that for final output order.

**14. "`GROUP BY` or `DISTINCT` returns sorted results."** Neither makes any ordering guarantee.

**15. "`COUNT(*) OVER()` always returns the total even when `OFFSET` goes past all rows."** False. Zero returned rows means zero rows carrying `total_rows`.

**16. "Any index helps `ORDER BY + LIMIT`."** False. Column order, sort direction, filter predicates, selectivity, and planner cost all matter.

**17. "Keyset pagination solves every concurrent-write edge case."** False. Updates to sort keys, changing filters, or reading across lagging replicas can still alter results.

**18. "Concatenating sort strings from requests into SQL is fine."** Dangerous. Only map allowlisted sort options.

**19. "`LIMIT 20` means the DB only processes 20 rows."** False. It may have to sort, filter, join, aggregate, or skip many rows beforehand.

**20. "An `ORDER BY` inside a subquery is always enough for the outer `SELECT`."** False. Specify `ORDER BY` at the query level returning the final output.

**21. "Sorting by a non-unique column works fine right now, so it's fine."** That works only by coincidence. Production SQL needs guarantees, not one-off demo luck.

**22. "Holding a `REPEATABLE READ` transaction open for minutes is an easy way to paginate web UIs."** Keeping snapshots open harms vacuum and resource usage; reserve it for controlled workflows.

## 18. Practice Exercises with Solutions

### Exercise 1 — LIMIT Without ORDER BY

Given:

```sql
SELECT order_id
FROM page_lab.orders
LIMIT 3;
```

**Question:** Can we conclude the three IDs are `101, 102, 103` because they were inserted first?

**Answer:** No. PostgreSQL makes no order guarantee for `SELECT` without `ORDER BY`. To get the three smallest IDs:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY order_id ASC
LIMIT 3;
```

Result is guaranteed to be `101, 102, 103` on the lab dataset.

### Exercise 2 — Page-Number Pagination

**Requirement:** retrieve page three with `pageSize = 4`, newest orders first, breaking timestamp ties with larger ID first.

**Answer:**

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 4 OFFSET 8;
```

Result: `108, 107, 106, 105`. Offset is `(3 - 1) * 4 = 8`.

### Exercise 3 — Rewriting with FETCH NEXT

**Requirement:** convert `LIMIT 5 OFFSET 10` to `FETCH` syntax.

**Answer:**

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
OFFSET 10 ROWS
FETCH NEXT 5 ROWS ONLY;
```

Result: `106, 105, 104, 102, 101` on the lab dataset.

### Exercise 4 — Why created_at Alone Is Unstable

**Question:** Two orders are created in the exact same second with identical timestamps. Does `ORDER BY created_at DESC LIMIT 1` guarantee picking the higher ID?

**Answer:** No. Add a tie-breaker:

```sql
ORDER BY created_at DESC, order_id DESC
LIMIT 1
```

Now within equal timestamps, the higher ID is guaranteed to come first.

### Exercise 5 — How Many Rows Can WITH TIES Return?

In the lab table, two orders are on Nov 6 and three orders are on Nov 5. Predict:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC
FETCH FIRST 3 ROWS WITH TIES;
```

**Answer:** **5 rows** with IDs `116, 115, 114, 113, 112`, though order within each timestamp group is not fixed without an outer sort. The 3rd row falls in the Nov 5 group, so the entire Nov 5 group is kept.

### Exercise 6 — WITH TIES and Unique Keys

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 3 ROWS WITH TIES;
```

**Answer:** Exactly **3 rows**, because `(created_at, order_id)` is unique; no other row shares the full sort key with the 3rd row.

### Exercise 7 — NULLS LAST

**Requirement:** sort descending by timestamp, push NULL timestamps to the bottom, and put larger IDs first within the NULL group.

**Answer:**

```sql
SELECT order_id, created_at
FROM some_orders
ORDER BY created_at DESC NULLS LAST, order_id DESC;
```

`some_orders` is an illustrative table allowing nullable `created_at`. On `page_lab.orders`, where `created_at` is `NOT NULL`, `NULLS LAST` is explicit without altering results.

### Exercise 8 — Next Page via Keyset

Page 1 has five rows and ends at `(created_at, order_id) = ('2026-11-05 11:00:00+00', 112)`. Retrieve the next five rows.

**Answer:**

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-05 11:00:00+00', 112)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Result: `111, 110, 109, 108, 107`. Filtering only `created_at < ...` would **skip** orders sharing the cursor's timestamp with a lower ID.

### Exercise 9 — Keyset with ASC

**Question:** For `ORDER BY created_at ASC, order_id ASC`, what condition finds rows after the cursor?

**Answer:** With two non-NULL comparable columns:

```sql
WHERE (created_at, order_id) > (:last_created_at, :last_order_id)
```

In direct PostgreSQL queries, replace placeholders with real bound parameters or typed literals rather than `:name` syntax if your client does not support named parameters.

### Exercise 10 — Keyset with Mixed Directions

**Requirement:** sort by `created_at DESC, order_id ASC`.

**Answer:** After cursor `(T, ID)`:

```sql
WHERE created_at < T
   OR (created_at = T AND order_id > ID)
```

Do not use `(created_at, order_id) < (T, ID)` because `order_id` is sorted `ASC`.

### Exercise 11 — How Do New INSERTs Affect OFFSET?

A client fetches page 1 (`116..112`). A new order `117` is inserted at the top before the client calls `LIMIT 5 OFFSET 5`.

**Answer:** ID `112` can reappear on page 2 because positions shifted down by one row. Adding a tie-breaker resolves order among equal timestamps, **not** dataset changes between requests. Keyset pagination is generally a better fit for infinite scroll.

### Exercise 12 — Counting Total Filtered Rows

**Requirement:** list only `paid` orders, returning the five newest plus the total count of paid orders.

**Answer:**

```sql
SELECT COUNT(*) AS total_paid
FROM page_lab.orders
WHERE status = 'paid';

SELECT order_id, created_at, amount
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Note that under `READ COMMITTED`, two separate queries can observe different data if another transaction commits in between. If exact point-in-time agreement is required, use appropriate isolation/snapshot design.

### Exercise 13 — Does COUNT(*) OVER() Always Return Total?

```sql
SELECT order_id, COUNT(*) OVER () AS total_rows
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 1000;
```

**Answer:** No. Because the offset exceeds the lab row count, the query returns **zero rows**, so the client receives no `total_rows` field either.

### Exercise 14 — Choosing an Index for Filtering and Sorting

A frequently executed endpoint runs:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

**Suggested answer:** Consider:

```sql
CREATE INDEX orders_paid_paging_candidate
ON page_lab.orders (status, created_at DESC, order_id DESC);
```

Then measure with `EXPLAIN (ANALYZE, BUFFERS)` on representative data and weigh write/index costs. Indexes are not mandatory for every table.

### Exercise 15 — Safely Cleaning Up the Lab

Once you are certain the schema belongs solely to this lesson:

```sql
-- Execute only if no other data relies on this schema.
-- DROP SCHEMA page_lab CASCADE;
```

`DROP SCHEMA ... CASCADE` deletes every table and dependent object in the schema; never run it on a shared database without verifying scope first.

## 19. Practical Workflow for Designing PostgreSQL Pagination

Before picking syntax, answer in order:

1. **What is the target row set?** Define `FROM`, `JOIN`, `WHERE`, and authorization/tenant predicates.
2. **Which business order do users expect?** Newest, highest value, alphabetical, or status?
3. **Can the sort key have duplicates?** If so, append a unique tie-breaker—usually the primary key.
4. **Can sort keys contain NULL?** Pick `NULLS FIRST/LAST` and avoid naive cursor predicates that ignore NULLs.
5. **Does the API use page numbers or cursor scrolling?** For small/random-jump pages, `LIMIT/OFFSET` is simple; for large feeds, consider keyset.
6. **Must boundary ties be included?** If yes, use `FETCH ... WITH TIES` on the **ranking keys**, not mixed with a strict fixed `pageSize`.
7. **Can data mutate between requests?** Decide whether live drift is acceptable or if consistent snapshots/report exports are needed.
8. **Is a total row count needed?** Weigh `COUNT(*)` cost, snapshot consistency, and empty-page behavior.
9. **Do indexes support the filter and sort?** Check column order, ASC/DESC direction, selectivity, and execution plan.
10. **Are API inputs validated and bounded?** Validate `page`/`pageSize`, bind parameters, allowlist sorts, and protect cursors.
11. **Have edge cases been tested?** Duplicate timestamps, short last page, empty pages, concurrent inserts/deletes/updates, NULLs, and varying filters.
12. **Are replicas or partitioning involved?** Account for replication lag, read consistency, and query plans in your real topology.

## 20. Summary

In PostgreSQL:

- **`LIMIT N`** returns at most N rows; **`OFFSET M`** skips the first M rows.
- **`FETCH FIRST/NEXT N ROWS ONLY`** expresses row limits in standard SQL syntax and pairs with `OFFSET ... ROWS`.
- **`FETCH ... WITH TIES`** retains extra rows whose **entire `ORDER BY` key tuple matches the boundary row**; returned count can exceed N.
- **Without `ORDER BY`, result order is never guaranteed.** Sorting on a non-unique column is also insufficient for stable pages.
- **Append a unique tie-breaker** such as `order_id` at the end of `ORDER BY` for deterministic ordering over a fixed dataset.
- **`LIMIT/OFFSET` is easy to use yet degrades at deep offsets and shifts under concurrent writes.** Keyset pagination using the previous page's final keys generally fits long scrolling lists better.
- **MVCC, snapshots, indexes, and API design** govern real-world consistency and performance; no single pagination clause solves everything alone.

**Final principle:** before asking "how many rows to take" or "how many rows to skip", ask **"what is the right order, is it unique, and can the dataset change between reads?"** Once you answer those three questions, you can choose `LIMIT`, `OFFSET`, `FETCH`, or keyset with confidence.

### PostgreSQL References

- [SELECT: ORDER BY, LIMIT, OFFSET, and FETCH](https://www.postgresql.org/docs/current/sql-select.html).
- [Sorting Rows](https://www.postgresql.org/docs/current/queries-order.html).
- [LIMIT and OFFSET](https://www.postgresql.org/docs/current/queries-limit.html).
- [B-tree Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
