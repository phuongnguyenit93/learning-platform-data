# Multi-Column Indexes and Column Ordering in PostgreSQL

An application often searches orders by **customer**, **status**, and **creation timestamp**. If PostgreSQL only has single-column indexes, each query may have to read many irrelevant rows or combine multiple indexes before filtering. A multi-column index (*multicolumn index*, also called a *composite index*) lets PostgreSQL store multiple key values inside **a single index structure**, making filtering, condition matching, sorting, and small top-N retrieval more efficient.

However, writing:

```sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC);
```

does not mean PostgreSQL treats those three columns as an unordered set. In a **B-tree**, left-to-right column order determines how keys are sorted inside the index. Consequently, an index on `(tenant_id, status, created_at)` and an index on `(created_at, tenant_id, status)` serve **two different query groups** with completely different costs.

This lesson focuses on the central question: **which column goes first, which comes next, and why?** We cover B-tree mechanics, equality and range predicates, `ORDER BY ... LIMIT`, covering indexes with `INCLUDE`, index-only scans, composite uniqueness, partial and expression indexes, reading `EXPLAIN`, and workload-driven decisions.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain lexicographic key ordering inside a multi-column B-tree.
2. Understand why **equality predicates on a leading prefix** followed by a **range predicate on the next column** are typically effective.
3. Avoid the misconception that PostgreSQL can only use a composite index when the leading column appears in `WHERE`.
4. Understand the role and limits of **B-tree skip scan** in supported versions and scenarios.
5. Distinguish **index condition** from **filter**, and recognize that trailing-column predicates can be checked in the index without narrowing the scanned range.
6. Design composite indexes for `WHERE`, `ORDER BY`, `LIMIT`, pagination, and `JOIN`s.
7. Distinguish key columns from `INCLUDE` payload columns, and understand visibility-map requirements for index-only scans.
8. Design multi-column unique constraints, partial indexes, and expression indexes with accurate semantics.
9. Compare a single composite index against multiple single-column indexes combined via bitmaps.
10. Verify index choices with `EXPLAIN (ANALYZE, BUFFERS)`, statistics, and representative datasets.

## 2. What Is a Multi-Column Index?

Consider an orders table:

```text
orders
  order_id
  tenant_id
  customer_id
  status
  created_at
  total_amount
```

Single-column index:

```sql
CREATE INDEX idx_orders_tenant
ON orders (tenant_id);
```

Multi-column index:

```sql
CREATE INDEX idx_orders_tenant_status_date
ON orders (tenant_id, status, created_at);
```

A **multi-column B-tree** sorts keys strictly from left to right:

```text
(tenant_id, status, created_at)

(1, 'paid',    2026-10-01)
(1, 'paid',    2026-10-05)
(1, 'pending', 2026-10-02)
(1, 'shipped', 2026-10-03)
(2, 'paid',    2026-10-01)
(2, 'pending', 2026-10-07)
(3, 'paid',    2026-10-08)
...
```

This diagram is illustrative. Actual `text` ordering depends on collation, and declaring `created_at DESC` reverses the timestamp sort order. The essential point is: PostgreSQL compares the **first column first**, consulting subsequent columns only as tie-breakers when preceding columns are equal.

### 2.1. A Composite Key Is Not String Concatenation

An index `(tenant_id, status)` **does not** store `'1|paid'` and compare strings. PostgreSQL builds B-tree keys from typed attributes using their respective operator classes and collations. Manually concatenating text in SQL:

```sql
-- Not equivalent in semantics or optimizer capabilities:
-- CREATE INDEX idx_bad
-- ON orders ((tenant_id::text || '|' || status));
```

differs fundamentally from a composite B-tree. String concatenation suffers from delimiter ambiguities, `NULL` handling issues, type conversion overhead, and loss of per-column range/sort semantics; never treat it as a standard multi-column key.

### 2.2. PostgreSQL Supports Multiple Index Access Methods

Access methods differ in how they handle multiple columns:

| Method | Multi-Column Capability and Key Notes |
| --- | --- |
| **B-tree** | Most common for equality, ranges, sorting, and prefix lookups. **Column order is especially critical.** |
| **GiST** | Supports multi-column indexes with compatible opclasses; efficiency depends on types/operators and can be sensitive to the leading column. |
| **GIN** | Supports multiple columns; fits containment/array/JSONB/full-text per opclass, without B-tree-style left-to-right prefix sorting. |
| **BRIN** | Stores block-range summaries suited for physically correlated data; multi-column BRIN has no B-tree prefix mechanism. |
| **Hash** | Not PostgreSQL's standard multi-column composite index method. |

Most examples here use **B-tree**, as it is the standard relational index for `WHERE tenant_id = ... AND status = ... ORDER BY created_at`. Do not apply B-tree ordering rules mechanically to GIN, GiST, or BRIN.

## 3. Practice Dataset: Multi-Tenant Orders System

Examples below use an isolated schema runnable in a test PostgreSQL database. **Never run DDL on production tables just to try out lesson exercises.**

### 3.1. Creating the Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS multicol_index_lab;

CREATE TABLE multicol_index_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    customer_id bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'shipped', 'cancelled')),
    created_at timestamptz NOT NULL,
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    store_id integer NOT NULL,
    shipped_at timestamptz
);
```

`order_id` uses explicit primary keys in the lab so results are easy to match. Production systems typically use `IDENTITY`, sequences, or another ID generator.

### 3.2. Inserting 24 Orders

```sql
INSERT INTO multicol_index_lab.orders
    (order_id, tenant_id, customer_id, status,
     created_at, total_amount, store_id, shipped_at)
VALUES
    (101, 1, 10, 'pending',   '2026-10-01 08:00+00', 200, 1, NULL),
    (102, 1, 10, 'paid',      '2026-10-02 08:00+00', 300, 1, NULL),
    (103, 1, 11, 'paid',      '2026-10-03 08:00+00', 450, 1, NULL),
    (104, 1, 12, 'shipped',   '2026-10-04 08:00+00', 600, 2, '2026-10-05 09:00+00'),
    (105, 1, 11, 'paid',      '2026-10-05 08:00+00', 180, 1, NULL),
    (106, 1, 10, 'cancelled', '2026-10-06 08:00+00',  90, 1, NULL),
    (107, 1, 13, 'paid',      '2026-10-07 08:00+00', 320, 2, NULL),
    (108, 1, 14, 'pending',   '2026-10-08 08:00+00', 700, 2, NULL),

    (201, 2, 20, 'paid',      '2026-10-01 09:00+00', 100, 1, NULL),
    (202, 2, 21, 'pending',   '2026-10-02 09:00+00', 220, 1, NULL),
    (203, 2, 22, 'shipped',   '2026-10-03 09:00+00', 340, 2, '2026-10-04 10:00+00'),
    (204, 2, 20, 'paid',      '2026-10-04 09:00+00', 460, 2, NULL),
    (205, 2, 21, 'cancelled', '2026-10-05 09:00+00',  70, 1, NULL),
    (206, 2, 23, 'paid',      '2026-10-06 09:00+00', 520, 1, NULL),
    (207, 2, 23, 'shipped',   '2026-10-07 09:00+00', 650, 2, '2026-10-08 10:00+00'),
    (208, 2, 24, 'pending',   '2026-10-08 09:00+00', 770, 2, NULL),

    (301, 3, 30, 'pending',   '2026-10-01 10:00+00', 130, 1, NULL),
    (302, 3, 31, 'paid',      '2026-10-02 10:00+00', 260, 1, NULL),
    (303, 3, 32, 'shipped',   '2026-10-03 10:00+00', 390, 1, '2026-10-04 11:00+00'),
    (304, 3, 30, 'paid',      '2026-10-04 10:00+00', 420, 2, NULL),
    (305, 3, 33, 'pending',   '2026-10-05 10:00+00', 550, 2, NULL),
    (306, 3, 34, 'cancelled', '2026-10-06 10:00+00',  80, 1, NULL),
    (307, 3, 31, 'paid',      '2026-10-07 10:00+00', 680, 2, NULL),
    (308, 3, 35, 'shipped',   '2026-10-08 10:00+00', 810, 2, '2026-10-09 11:00+00');
```

### 3.3. Inspecting Input Data

```sql
SELECT
    tenant_id, order_id, customer_id, status,
    created_at, total_amount
FROM multicol_index_lab.orders
ORDER BY tenant_id, created_at, order_id;
```

Each tenant has eight orders. For tenant 1:

| order_id | status | created_at (UTC date) | total_amount |
| ---: | --- | --- | ---: |
| 101 | pending | 2026-10-01 | 200 |
| 102 | paid | 2026-10-02 | 300 |
| 103 | paid | 2026-10-03 | 450 |
| 104 | shipped | 2026-10-04 | 600 |
| 105 | paid | 2026-10-05 | 180 |
| 106 | cancelled | 2026-10-06 | 90 |
| 107 | paid | 2026-10-07 | 320 |
| 108 | pending | 2026-10-08 | 700 |

`created_at` is `timestamptz`: displayed values depend on the session timezone. Showing UTC dates here does not mean PostgreSQL stores a raw timezone string per row.

### 3.4. Small Data and EXPLAIN

With only **24 rows**, PostgreSQL will likely choose `Seq Scan` for most queries even after creating ideal indexes. That is cost-optimal: scanning one heap page beats traversing an index tree.

Accordingly, small-table SQL examples teach **semantics**, whereas **performance** conclusions should only be drawn after loading representative data, running `ANALYZE`, and inspecting `EXPLAIN (ANALYZE, BUFFERS)`. A later section shows an optional larger dataset generator.

## 4. Lexicographic Order: The Foundation of Composite B-trees

Suppose we create:

```sql
CREATE INDEX idx_lab_tenant_status_created
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

The index key has three components:

```text
1. tenant_id
2. status
3. created_at DESC
```

Lookup intuition:

```text
Index (tenant_id, status, created_at DESC)

tenant=1
    status='cancelled': created_at...
    status='paid':      newest -> oldest
    status='pending':   newest -> oldest
    status='shipped':   newest -> oldest

tenant=2
    status='cancelled': created_at...
    status='paid':      newest -> oldest
    ...

tenant=3
    ...
```

The index sorts by `tenant_id` first, then `status` within each tenant, then descending timestamp within each `(tenant, status)` group. **A tenant's overall timeline is split into separate `status` blocks.**

### 4.1. Column Order Strongly Affects ORDER BY

For the query:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 10;
```

index `(tenant_id, status, created_at DESC)` can:

1. Jump to `tenant_id = 1`.
2. Within that slice, narrow to `status = 'paid'`.
3. Walk entries already ordered by `created_at DESC`.
4. Stop early once `LIMIT` rows are collected, if an index scan is chosen.

However, for:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 10;
```

that same index does **not** supply `created_at DESC` across the entire tenant, because rows are grouped by `status` first. PostgreSQL may need a `Sort` or another index.

### 4.2. Swapping Columns Changes Which Query Pattern Is Favored

A different index:

```sql
CREATE INDEX idx_lab_tenant_created_status
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, status);
```

With this index, once `tenant_id` is pinned, rows are ordered newest-first regardless of status. It fits much better for:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 10;
```

In return, for `tenant_id = 1 AND status = 'paid'`, `status` sits **after `created_at`**, potentially scanning many tenant rows just to filter `status`, especially if no narrow time range is specified. The trade-off lies in **scan-range narrowing and output sort order**, not merely whether a column happens to appear in the index.

## 5. Practical Heuristic: Equality First, Range Next

For multi-column B-trees, a classic high-value pattern is:

```sql
-- Created in Section 4; IF NOT EXISTS allows re-running safely in the lab.
CREATE INDEX IF NOT EXISTS idx_lab_tenant_status_created
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

Query:

```sql
SELECT order_id, total_amount, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-10-03 00:00+00'
ORDER BY created_at DESC;
```

Breakdown:

| Column in Index Order | Predicate | Role |
| --- | --- | --- |
| `tenant_id` | `= 1` | Leading equality: jumps to the tenant's key slice. |
| `status` | `= 'paid'` | Second equality: narrows to the status slice inside that tenant. |
| `created_at` | `>= cutoff` | Range on trailing column: bounds the time interval scanned. |

Thanks to leading equality predicates, the B-tree jumps straight to `(tenant = 1, status = 'paid')` and scans only the matching timestamp range inside it.

### 5.1. Equality/Range Is Not a Rigid Absolute Law

Never turn that heuristic into the false rule:

> “A multi-column B-tree helps only when `WHERE` filters the first column, and every predicate after a range column is ignored.”

In reality, PostgreSQL:

- Can evaluate predicates on **trailing** index columns inside the index, even if they cannot bound a single contiguous scan range the way leading equality columns do.
- Can perform a **skip scan** in supported versions and favorable cost scenarios.
- Can use **bitmap index scans**, combine multiple indexes, or use an index strictly for sort order.
- Can skip the index altogether when statistics and costs favor a sequential scan.

“Equality before range” is a **design heuristic for B-tree key ordering**, not an exhaustive description of every possible plan.

### 5.2. When Multiple Columns Use Equality

For:

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

both `(tenant_id, status)` and `(status, tenant_id)` narrow directly to the exact key pair. **There is no universal rule that the higher-selectivity column must always come first** when both use equality.

Decide ordering by asking:

- Which queries filter on **only one** of the two columns?
- Is there an `ORDER BY` or range condition after those equality columns?
- Do all queries enforce tenant isolation?
- What are the actual distinct counts, skew, and correlations?
- Can one index serve multiple important queries?

If queries frequently filter by `tenant_id = ?` alone and rarely by `status` alone, leading with `tenant_id` serves the overall workload better. If global reports filter by `status` and time, a different order may make sense.

## 6. Why the “Leftmost Prefix Rule” Needs Nuance

Many introductory guides summarize the leftmost prefix rule as:

```text
Index (a, b, c) works best for:
  a
  a, b
  a, b, c
```

This is a helpful starting point, yet it easily leads to the overstatement that `WHERE b = ?` can **never** use `(a, b, c)`. PostgreSQL can choose several execution paths when the cost model favors them.

### 6.1. Example Including the Leading Column

```sql
SELECT order_id, status
FROM multicol_index_lab.orders
WHERE tenant_id = 2
ORDER BY status;
```

Index `(tenant_id, status, created_at DESC)` naturally groups `tenant_id = 2` ordered by `status`.

### 6.2. Example Omitting the Leading Column

```sql
SELECT order_id, tenant_id, created_at
FROM multicol_index_lab.orders
WHERE status = 'paid';
```

On `(tenant_id, status, created_at DESC)`, PostgreSQL does not have one contiguous range holding all `'paid'` rows across every tenant. Even so, the index **might** still be chosen in some plans—for example, if scanning the index is cheap or skip scan applies. That still does not make it ideal for status-only lookups.

If status-only queries run very frequently, you may want:

```sql
CREATE INDEX idx_lab_status_created
ON multicol_index_lab.orders
    (status, created_at DESC);
```

Every extra index consumes storage and write overhead; avoid creating every permutation just because `WHERE` clauses vary.

### 6.3. A Predicate on the Trailing Column Alone Does Not Form a Narrow Range

Example:

```sql
SELECT order_id, tenant_id, status
FROM multicol_index_lab.orders
WHERE created_at >= TIMESTAMPTZ '2026-10-07 00:00+00';
```

In `(tenant_id, status, created_at DESC)`, recent timestamps are scattered across every `(tenant, status)` bucket. For date-only queries, `(created_at)` or `(created_at DESC, tenant_id)` is usually far more suitable depending on selectivity and queries.

This does not mean PostgreSQL is blind to the trailing column. Rather, **being able to check a condition** is very different from **narrowing the index scan to one tight slice**.

## 7. B-tree Skip Scan: A Useful Exception to Prefix Rules

In PostgreSQL versions supporting B-tree skip scan, the planner can use a multi-column index even when a query **omits an equality condition on the leading column**, by stepping across distinct values of that leading column.

Suppose you have:

```sql
CREATE INDEX idx_lab_store_customer
ON multicol_index_lab.orders (store_id, customer_id);
```

Query:

```sql
SELECT order_id, store_id, customer_id
FROM multicol_index_lab.orders
WHERE customer_id = 10;
```

If `store_id` has very few distinct values, the planner may find it worthwhile to probe:

```text
(store_id = 1, customer_id = 10)
(store_id = 2, customer_id = 10)
...
```

rather than scanning every leaf entry. The idea is to supply missing leading bounds iteratively so the trailing predicate can be probed directly.

### 7.1. When Can Skip Scan Pay Off?

- The leading column has **very few distinct values**.
- The trailing predicate is selective.
- Multiple index probes cost less than a wide index scan or sequential scan.
- Your PostgreSQL version and access method/planner support it.

If the leading column has millions of distinct values, probing every one of them would be prohibitively expensive, so the planner picks another scan.

### 7.2. Do Not Build Your Indexing Strategy Around Skip Scan

Skip scan is a **version- and cost-dependent optimization**, not a contract that `(a, b)` replaces `(b)` for `WHERE b = ?`.

When working on a specific PostgreSQL release:

1. Check the official docs for your running major version.
2. Inspect actual plans with `EXPLAIN`.
3. Test with realistic column cardinalities.
4. If `b`-only queries are a hot path, consider a dedicated index rather than relying on skip scan by assumption.

## 8. Equality First, Range in the Middle, Equality at the End

Consider an index:

```sql
CREATE INDEX idx_lab_tenant_time_status
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, status);
```

Query:

```sql
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND status = 'paid';
```

With this index:

1. `tenant_id = 1` narrows to one tenant region.
2. `created_at >= ...` bounds a time slice inside that tenant.
3. `status = 'paid'` can still be tested within the index, yet normally cannot tighten the scanned time slice the way placing `status` before `created_at` would.

Hence if a tenant has 100 million orders spanning years while only a small fraction are `'paid'`, `(tenant_id, status, created_at)` can be dramatically faster for this query.

Conversely, if the query always asks for **the 20 newest orders for a tenant regardless of status**:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

then `(tenant_id, created_at DESC, order_id DESC)` is usually the stronger candidate.

**You cannot pick column order by looking at one `WHERE` clause in isolation.** Factor in range predicates, sort order, `LIMIT`, and query frequency.

## 9. Equality, IN, BETWEEN, and Expressions

### 9.1. Equality

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

Two equality conditions form an ideal leading prefix on `(tenant_id, status, created_at)`.

### 9.2. IN

```sql
WHERE tenant_id = 1
  AND status IN ('paid', 'shipped')
```

`IN` specifies multiple discrete values, not a single contiguous key slice. PostgreSQL may evaluate it via repeated index probes, scalar-array operators, or another plan. Matching rows come from **multiple status groups** and are not globally sorted by timestamp across all matched statuses.

Example:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status IN ('paid', 'shipped')
ORDER BY created_at DESC
LIMIT 10;
```

With `(tenant_id, status, created_at DESC)`, PostgreSQL may still need a `Sort` or merge step to satisfy global `ORDER BY created_at DESC` across both statuses. Never assume `IN` behaves identically to single-value equality for `ORDER BY`.

### 9.3. BETWEEN and Half-Open Intervals

```sql
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
```

For timestamps, `[start, end)` is cleaner than inclusive `BETWEEN` when filtering a day or month. `BETWEEN` is valid, yet developers frequently miscalculate `23:59:59` endpoints when microsecond precision is present.

`(tenant_id, created_at)` handles tenant + half-open time ranges cleanly.

### 9.4. Expressions on Indexed Columns

Suppose a query writes:

```sql
WHERE tenant_id = 1
  AND created_at::date = DATE '2026-10-07'
```

Casting `created_at` to `date` does not map directly to a range bound on a standard B-tree on `created_at`. Furthermore, `created_at::date` on `timestamptz` depends on session timezone.

For a UTC calendar day, use explicit bounds:

```sql
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-07 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-10-08 00:00+00'
```

Filtering on the raw column lets PostgreSQL leverage `(tenant_id, created_at)`. If a workload genuinely requires filtering on an expression, design a matching expression index when PostgreSQL immutability rules allow.

## 10. Column Ordering for ORDER BY and LIMIT

B-trees do more than filter: they store keys in sorted order. When an index supplies the exact output order, PostgreSQL can avoid or reduce a `Sort`.

### 10.1. Latest Orders for a Tenant

```sql
CREATE INDEX idx_lab_tenant_created_order
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);
```

Query:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 2
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Here:

- `tenant_id = 2` pins the leading column.
- `created_at DESC, order_id DESC` matches the remaining key order.
- `LIMIT 5` allows early termination after reading enough rows, provided an index scan is chosen and residual filters do not discard many rows.

`order_id` acts as a tie-breaker making output **deterministic** when two orders share `created_at`. With only `ORDER BY created_at DESC`, tie ordering is undefined.

### 10.2. Backward Index Scans on B-trees

A B-tree:

```sql
CREATE INDEX idx_lab_tenant_created_asc
ON multicol_index_lab.orders
    (tenant_id ASC, created_at ASC);
```

can be scanned forward or backward. When **`tenant_id` is pinned by equality**, `ORDER BY created_at DESC` can scan that tenant's slice backward. Thus you do not always need a duplicate `DESC` index just to reverse one column.

However, if a query requires a **mixed** multi-column sort without pinning the first column:

```sql
ORDER BY tenant_id ASC, created_at DESC
```

an index `(tenant_id ASC, created_at DESC)` supplies that exact order directly; scanning `(tenant_id ASC, created_at ASC)` backward reverses **both** columns, not just one.

### 10.3. Mixed ASC/DESC Ordering

```sql
CREATE INDEX idx_lab_mixed_sort
ON multicol_index_lab.orders
    (tenant_id ASC, created_at DESC, order_id DESC);
```

Directly supports:

```sql
SELECT tenant_id, created_at, order_id
FROM multicol_index_lab.orders
ORDER BY tenant_id ASC, created_at DESC, order_id DESC;
```

Scanning this entire index backward produces the exact opposite direction for every component (along with reversed `NULL` placement).

If a query asks for `tenant_id DESC, created_at DESC` across all tenants, this mixed index **cannot** satisfy that order in a single scan.

### 10.4. NULLS FIRST / NULLS LAST

PostgreSQL B-tree defaults:

- `ASC` defaults to `NULLS LAST`.
- `DESC` defaults to `NULLS FIRST`.
- Backward scans flip both sort direction and `NULL` placement.

For a nullable `shipped_at` column:

```sql
CREATE INDEX idx_lab_tenant_shipped_nulls_last
ON multicol_index_lab.orders
    (tenant_id ASC, shipped_at DESC NULLS LAST);
```

Query:

```sql
SELECT order_id, tenant_id, shipped_at
FROM multicol_index_lab.orders
WHERE tenant_id = 2
ORDER BY shipped_at DESC NULLS LAST
LIMIT 10;
```

Never assume a plain `DESC` index matches `DESC NULLS LAST`. On nullable sort columns, declare the exact `NULLS` option required by the workload.

## 11. Why Does a Column Get “Trapped” Between WHERE and ORDER BY?

Consider:

```sql
-- Index from Section 4; repeated here for reference.
CREATE INDEX IF NOT EXISTS idx_lab_tenant_status_created
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

Query 1:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC;
```

Within a pinned `(tenant_id, status)` pair, `created_at` is cleanly ordered `DESC`.

Query 2:

```sql
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC;
```

Here `status` is unconstrained. Rows within the tenant are partitioned into separate `status` groups, each independently sorted by `created_at DESC`. **Combining those separate groups does not yield a single tenant-wide `created_at DESC` sequence.**

### 11.1. Design Lesson

If the most common screen shows “a tenant's newest orders,” favor:

```sql
(tenant_id, created_at DESC, order_id DESC)
```

If the most common screen shows “a tenant's newest paid orders,” favor:

```sql
(tenant_id, status, created_at DESC, order_id DESC)
```

If **both** queries are high-volume and latency-critical, maintaining both indexes may be warranted alongside their write cost. That is a workload trade-off, not an absolute SQL rule.

## 12. Keyset Pagination and Composite Indexes

On large order volumes, growing `OFFSET` values force the database to step through many skipped rows:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 200000;
```

A far more scalable pattern for chronological feeds is **keyset pagination** (seek pagination).

### 12.1. First Page

```sql
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Save `(created_at, order_id)` from the last row as the cursor.

### 12.2. Subsequent Pages

Suppose the last row had that timestamp and ID:

```sql
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-04 08:00+00', 104)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Because both `created_at` and `order_id` sort descending, the tuple comparison `<` selects keys appearing **after the cursor in descending order**. Index `(tenant_id, created_at DESC, order_id DESC)` accelerates this pattern cleanly.

Requirements:

- The key pair must form a **unique total order** (since `order_id` is unique).
- Nullable cursor columns require explicit handling; the lab defines `created_at NOT NULL`.
- Next-page queries must keep the exact same filters and sort order.
- Rows can change between requests. Keyset pagination avoids large `OFFSET` overhead, yet does not provide a frozen snapshot across separate HTTP requests.

### 12.3. Why Should order_id Come Last?

If two orders share the exact same `created_at` and `ORDER BY` specifies only the date, pagination cannot break ties deterministically. Trailing `order_id` resolves ties.

Putting `order_id DESC` after `created_at DESC` lets the index serve both the tuple seek and two-column ordering. Putting `order_id` before `created_at` breaks the chronological sort needed by the query.

## 13. Composite Indexes and JOIN Queries

Suppose `orders` includes `tenant_id` and `customer_id`. An application often fetches orders for one customer within a tenant:

```sql
SELECT order_id, created_at, total_amount
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND customer_id = 10
ORDER BY created_at DESC, order_id DESC;
```

Candidate index:

```sql
CREATE INDEX idx_lab_tenant_customer_created
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

This aligns with the access pattern:

```text
tenant_id = ?
    customer_id = ?
        created_at DESC
            order_id DESC
```

### 13.1. Joining from a customers Table

Suppose a `customers` table has `(tenant_id, customer_id)`:

```sql
CREATE TABLE multicol_index_lab.customers (
    tenant_id integer NOT NULL,
    customer_id bigint NOT NULL,
    display_name text NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);

INSERT INTO multicol_index_lab.customers
    (tenant_id, customer_id, display_name)
VALUES
    (1, 10, 'Customer A'),
    (1, 11, 'Customer B'),
    (2, 20, 'Customer C');
```

JOIN query:

```sql
SELECT
    c.display_name,
    o.order_id,
    o.created_at
FROM multicol_index_lab.customers AS c
JOIN multicol_index_lab.orders AS o
    ON o.tenant_id = c.tenant_id
   AND o.customer_id = c.customer_id
WHERE c.tenant_id = 1
  AND c.customer_id = 10
ORDER BY o.created_at DESC, o.order_id DESC;
```

One possible plan is a Nested Loop probing `orders` via `(tenant_id, customer_id, created_at DESC, order_id DESC)`. However, PostgreSQL may also choose Hash Join, Merge Join, or `Seq Scan` when row counts are small or join selectivity differs.

### 13.2. Indexing the Referencing Side

The primary key `customers(tenant_id, customer_id)` automatically has a unique B-tree index. Meanwhile, if `orders` holds a foreign key referencing `customers`, PostgreSQL **does not automatically create child-table indexes for foreign keys**.

`(tenant_id, customer_id)` or an extended composite index helps both JOIN queries and parent key deletes/updates, depending on workload.

### 13.3. A Join Index Does Not Guarantee Index Usage for Every Join

A query joining all customers and all orders with no tenant/customer filter will likely choose Hash Join and `Seq Scan`. An index built for selective lookups is rarely optimal for full-table joins.

## 14. Composite UNIQUE: Index Order and Uniqueness

Multi-column indexes do more than speed up reads—they also enforce data integrity rules:

> An external order number must be unique **within each tenant**, not globally across the entire platform.

Standalone table example:

```sql
CREATE TABLE multicol_index_lab.external_orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    external_order_no text NOT NULL,
    amount numeric(12, 2) NOT NULL,
    CONSTRAINT uq_external_orders_tenant_no
        UNIQUE (tenant_id, external_order_no)
);
```

Two rows with the same `external_order_no` under different tenants are valid:

```sql
INSERT INTO multicol_index_lab.external_orders
    (tenant_id, external_order_no, amount)
VALUES
    (1, 'INV-001', 200.00),
    (2, 'INV-001', 400.00);
```

Inserting the same pair `(tenant_id = 1, external_order_no = 'INV-001')` again violates the unique constraint.

### 14.1. Uniqueness Semantics vs. Query Efficiency

In terms of **pair uniqueness**, `UNIQUE(tenant_id, external_order_no)` and `UNIQUE(external_order_no, tenant_id)` reject the exact same duplicate pairs (under the same `NULL` rules).

Yet their key ordering serves different queries:

- `(tenant_id, external_order_no)` accelerates per-tenant lookups and listings.
- `(external_order_no, tenant_id)` accelerates global lookups by external code.

Never pick composite `UNIQUE` column order merely by which column appears earlier in a form. Consider both constraint semantics **and dominant read access paths**.

### 14.2. NULLs in Multi-Column Unique Constraints

By default, PostgreSQL treats `NULL` as distinct from `NULL` in standard unique constraints; multiple rows with matching non-NULL components and `NULL` in another component are allowed.

Our lab sets `external_order_no NOT NULL`, avoiding this case. On nullable columns, PostgreSQL 15+ adds **`UNIQUE NULLS NOT DISTINCT`** when `NULL` values should count as equal for uniqueness:

```sql
-- PostgreSQL 15+; separate schema example:
CREATE TABLE multicol_index_lab.optional_codes (
    tenant_id integer NOT NULL,
    optional_code text,
    UNIQUE NULLS NOT DISTINCT (tenant_id, optional_code)
);
```

With this constraint, two rows with the same `tenant_id` and `optional_code IS NULL` conflict. **Do not use this syntax on older PostgreSQL major versions that lack support.**

## 15. INCLUDE: Returned Columns Don't Need to Be Search Keys

Consider a hot query:

```sql
SELECT
    order_id,
    created_at,
    total_amount
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

An index can be designed as:

```sql
CREATE INDEX idx_lab_paid_order_cover
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Columns inside `(...)` are **key columns**. Columns after `INCLUDE` are **payload/non-key columns**:

| Component | Role |
| --- | --- |
| `tenant_id` | Key: filters tenant. |
| `status` | Key: filters status. |
| `created_at DESC` | Key: filters/sorts by time. |
| `order_id DESC` | Key: tie-breaker and lookup/sort support. |
| `total_amount` | `INCLUDE`: supplies the returned column without necessarily touching the heap. |

### 15.1. INCLUDE Columns Cannot Narrow Search Ranges

If an index is:

```sql
CREATE INDEX idx_lab_tenant_time_includes
ON multicol_index_lab.orders
    (tenant_id, created_at DESC)
INCLUDE (status, total_amount);
```

then `WHERE status = 'paid'` **does not make `status` act like a third key column** bounding the index scan the way `(tenant_id, created_at, status)` would. `INCLUDE` columns do not participate in B-tree ordering or key bounds.

PostgreSQL can still evaluate predicates on included values during an eligible index-only scan, yet carrying a column in `INCLUDE` is fundamentally different from making it an ordered key.

### 15.2. Index-Only Scans Need Additional Conditions

An index containing all queried columns **does not guarantee** PostgreSQL will pick `Index Only Scan`:

- Required columns must be retrievable from the index per the access method.
- PostgreSQL still verifies MVCC visibility via the **visibility map** to see if heap pages are all-visible.
- If pages are not all-visible, PostgreSQL still fetches the heap to verify visibility.
- The planner may still find a regular `Index Scan` or `Seq Scan` cheaper.

Practice:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

When `Index Only Scan` appears, check `Heap Fetches`. On small or recently updated tables, heap fetches may still occur.

### 15.3. Costs of INCLUDE

Payload columns enlarge the index, raise I/O and write overhead, can reduce B-tree fanout (and disable deduplication), and can block HOT updates when included columns change. Never blindly `INCLUDE` every `SELECT` column, especially wide text/JSONB or frequently mutated columns.

PostgreSQL also enforces a maximum index tuple size; oversized payloads can cause `CREATE INDEX`, `INSERT`, or `UPDATE` errors. Include only columns with measured payoff.

## 16. Does a Composite Index Replace a Single-Column Index?

Suppose you have:

```sql
CREATE INDEX idx_lab_tenant_only
ON multicol_index_lab.orders (tenant_id);

CREATE INDEX idx_lab_tenant_status
ON multicol_index_lab.orders (tenant_id, status);
```

In a B-tree, the second index can usually also serve queries filtering solely on `tenant_id`:

```sql
SELECT COUNT(*)
FROM multicol_index_lab.orders
WHERE tenant_id = 2;
```

In terms of access capability, this is why an index on a **leading prefix** is often flagged as potentially redundant with a wider composite index.

Still, **never drop `(tenant_id)` blindly** just because `(tenant_id, status)` exists:

- The single-column index is **narrower**, fitting more keys per page and potentially reading faster for tenant-only queries.
- A wider index can cause more cache misses or disk reads.
- Differences in uniqueness, partial predicates, expressions, collations, or sort order mean one index does not always cover every semantic need of another.
- Tenant-only queries might vastly outnumber tenant+status queries.
- The planner may choose different plans based on actual data.

### 16.1. Right Way to Evaluate Redundant Indexes

Compare:

1. Purpose of each index (`SELECT`, `JOIN`, FK checks, uniqueness, `ORDER BY`).
2. Keys and exact column order.
3. Partial index `WHERE` predicates, expressions, collations, and operator classes.
4. Physical size and write maintenance overhead.
5. Usage stats and which hot queries could regress.
6. Rollback plan if dropping an index increases latency.

Index tuning optimizes **combined read/write workload**, not a contest to minimize or maximize index count.

### 16.2. Index (a, b) Differs from Two Indexes (a) and (b)

For:

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

PostgreSQL may:

- Use `(tenant_id, status)` to jump straight to the matching key slice.
- Scan `(tenant_id)` and filter `status`.
- Scan `(status)` and filter `tenant_id`.
- Combine bitmaps from both single-column indexes.
- Perform a sequential scan.

Two separate single-column indexes **do not magically merge** into a lexicographically ordered composite index. In particular, combining bitmaps destroys B-tree key ordering needed for top-N `ORDER BY ... LIMIT`.

## 17. Bitmap Index Scan: Combining Indexes, Losing Sort Order

Suppose two indexes exist:

```sql
CREATE INDEX idx_lab_tenant_bitmap
ON multicol_index_lab.orders (tenant_id);

CREATE INDEX idx_lab_status_bitmap
ON multicol_index_lab.orders (status);
```

A plan might look like:

```text
Bitmap Heap Scan on orders
  Recheck Cond: ...
  -> BitmapAnd
       -> Bitmap Index Scan on idx_lab_tenant_bitmap
       -> Bitmap Index Scan on idx_lab_status_bitmap
```

This is an **illustrative plan**, not guaranteed output on our 24-row lab table. On tiny tables, PostgreSQL uses `Seq Scan`.

### 17.1. Why Bitmap Heap Scan?

Each index collects candidate heap tuple locations into a bitmap. PostgreSQL intersects or unions bitmaps via `BitmapAnd` / `BitmapOr`, then reads heap pages in physical block order to verify and return rows.

Its strength is reusing multiple existing single-column indexes. Its weakness involves ordering:

- `Bitmap Heap Scan` returns rows in physical page order, **not B-tree key order**.
- If the query asks for `ORDER BY created_at DESC LIMIT 20`, an explicit `Sort` / Top-N sort is still needed.
- A composite B-tree matching both filter and sort order usually has a strong advantage on top-N hot queries.

### 17.2. Can Bitmap Scans Beat a Composite Index?

Yes. When predicates vary dynamically across dozens of ad-hoc filter combinations, maintaining a composite index for **every permutation** is impractical. A few targeted indexes combined via bitmaps give the planner flexible options.

Never claim composite **always** beats bitmap scans: selectivity, row counts, heap page density, physical clustering, RAM, and cache all affect the outcome.

### 17.3. Comparing Scan Nodes

| Plan Node | Typical Characteristics |
| --- | --- |
| `Index Scan` | Fetches TIDs from index and reads heap rows; can preserve B-tree key order. |
| `Index Only Scan` | Required columns live in the index, though MVCC visibility checks may still cause heap fetches. |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Collects row locations and reads heap pages via bitmap; loses index sort order. |
| `Seq Scan` | Scans the whole table sequentially; often optimal on small tables or broad filters. |

Never assume seeing the word `Index` in a plan means it is optimal. Measure rows, buffers, timings, and workload cost.

## 18. Partial Composite Indexes: Indexing Only a Subset of Rows

If a hot-path screen only queries `status = 'pending'` orders, indexing all statuses may waste space and write overhead.

PostgreSQL supports partial indexes:

```sql
CREATE INDEX idx_lab_pending_tenant_created
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC)
WHERE status = 'pending';
```

Meaning:

- Only rows satisfying `status = 'pending'` enter this index.
- Within that subset, keys sort by `tenant_id, created_at DESC, order_id DESC`.
- `status` **does not need to be a key column** if the index covers only pending rows and the query provably implies that predicate.

Target query:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'pending'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

### 18.1. The Planner Must Prove the Predicate

A partial index is usable only when PostgreSQL can prove the **query predicate implies the index predicate** in that plan.

Query:

```sql
WHERE tenant_id = 1
  AND status = 'paid'
```

cannot use a pending-only partial index because `'paid'` rows are absent from it.

With a prepared statement:

```sql
PREPARE pending_lookup(integer, text) AS
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

a **generic plan** cannot assume `$2` is always `'pending'`. Thus the partial index may be skipped even if callers usually bind `'pending'`. PostgreSQL switches between custom and generic plans automatically, so benchmark with the actual statement preparation and parameter binding your app uses.

### 18.2. Never Put now() in a Partial Index Predicate

A common invalid attempt:

```sql
-- Invalid due to index predicate immutability rules:
-- CREATE INDEX idx_recent
-- ON multicol_index_lab.orders (created_at)
-- WHERE created_at >= now() - INTERVAL '7 days';
```

`now()` varies by transaction/time and is not `IMMUTABLE`. Even conceptually, a partial index cannot automatically shift its membership as the wall clock ticks.

For time-bounded retention, use fixed batch cutoffs, partitioning, or a regular index on the timestamp column with `now()` evaluated in the query:

```sql
SELECT order_id
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND created_at >= now() - INTERVAL '7 days';
```

### 18.3. Partial Indexes and Status Transitions

When an order moves from `'pending'` to `'paid'`, the partial index must delete its entry. If status transitions occur constantly, factor that membership maintenance into write cost.

That is why a smaller partial index speeds up `SELECT`s without making `UPDATE`s “free.”

## 19. Multi-Column Expression Indexes: Normalizing Search Keys

A multi-tenant application wants case-insensitive email uniqueness **within each tenant**:

```text
tenant 1: Alice@Example.com
tenant 1: alice@example.com   -> duplicate under business rules
tenant 2: alice@example.com   -> valid because different tenant
```

You can define a unique expression index:

```sql
CREATE TABLE multicol_index_lab.contacts (
    contact_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL,
    email text NOT NULL
);

CREATE UNIQUE INDEX idx_contacts_tenant_email_lower
ON multicol_index_lab.contacts
    (tenant_id, lower(email));
```

Test:

```sql
INSERT INTO multicol_index_lab.contacts
    (contact_id, tenant_id, email)
VALUES
    (1, 1, 'Alice@Example.com'),
    (2, 2, 'alice@example.com');

SELECT contact_id, tenant_id, email
FROM multicol_index_lab.contacts
WHERE tenant_id = 1
  AND lower(email) = lower('ALICE@example.com');
```

The index has two keys:

1. `tenant_id` — plain column.
2. `lower(email)` — computed expression value.

### 19.1. Queries Must Match the Indexed Expression

An index on `lower(email)` does not optimize `WHERE email = 'ALICE@example.com'` the same way because the comparison semantics differ.

Write queries against the exact normalized expression or store a normalized column. Also remember real-world email normalization can be subtler than plain `lower()`, depending on collation, Unicode normalization, and product rules.

### 19.2. When to Store a Normalized Column?

In large systems, consider:

- Storing raw email alongside a controlled normalized value.
- Using an appropriate collation or data type when supported.
- Placing a unique index on the explicitly defined normalized value.

Never assume plain `lower(text)` under an arbitrary locale handles all Unicode identifiers properly.

### 19.3. Expression Column Order Matters Too

`(tenant_id, lower(email))` fits per-tenant email lookups. `(lower(email), tenant_id)` fits global email lookups **across all tenants**, though cross-tenant lookups demand careful attention to privacy and multi-tenant authorization.

## 20. Composite Indexes with GROUP BY and DISTINCT ON

Ordered indexes can assist grouping and picking the top row per group, though the planner may still choose hash aggregation or explicit sorting.

### 20.1. GROUP BY Tenant and Status

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count
FROM multicol_index_lab.orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

A B-tree `(tenant_id, status)` groups matching pairs adjacently, helping if PostgreSQL picks an ordered `GroupAggregate`. Still, `HashAggregate` or `Seq Scan` can be cheaper, especially on small tables.

### 20.2. Latest Order per Customer

Suppose you want **the single newest order for each `(tenant, customer)` pair**:

```sql
SELECT DISTINCT ON (tenant_id, customer_id)
    tenant_id,
    customer_id,
    order_id,
    created_at,
    status
FROM multicol_index_lab.orders
ORDER BY
    tenant_id,
    customer_id,
    created_at DESC,
    order_id DESC;
```

PostgreSQL's `DISTINCT ON` keeps the first row of each group according to `ORDER BY`. Here `order_id DESC` breaks timestamp ties deterministically.

Matching index:

```sql
CREATE INDEX idx_lab_customer_latest
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

This index supplies the exact ordering needed by `DISTINCT ON`. However, if nearly every index entry must still be scanned to find one row per group, total cost may still be substantial; verify plans against actual data sizes.

### 20.3. DISTINCT ON Differs from GROUP BY MAX Joined Back Carelessly

A common pattern:

```sql
SELECT tenant_id, customer_id, MAX(created_at)
FROM multicol_index_lab.orders
GROUP BY tenant_id, customer_id;
```

returns the latest timestamp, yet **cannot pick a unique `order_id`** cleanly when two orders share `created_at`. `DISTINCT ON` with a deterministic tie-breaker selects one unambiguous row.

### 20.4. Per-Group Ordering Is Not Table-Wide Pagination

Index `(tenant_id, customer_id, created_at DESC, order_id DESC)` sorts within each customer inside a tenant. It does **not** supply `created_at DESC` across all customers of a tenant when `customer_id` is unconstrained.

This is the exact same “trapped middle column” principle seen earlier, applied to top-1-per-group and pagination.

## 21. Collations and Operator Classes Are Part of Design

For `text` columns, index ordering and comparisons depend on collation and operator class. Two indexes listing identical column names with different comparison rules serve different workloads.

Example index for exact tenant + status lookups:

```sql
CREATE INDEX idx_lab_tenant_status_text
ON multicol_index_lab.orders (tenant_id, status);
```

If a query sorts under a different collation from the index's collation, PostgreSQL cannot use that index directly to avoid a `Sort`.

### 21.1. Prefix LIKE and text_pattern_ops

Under non-`C` collations, optimizing `LIKE 'abc%'` with a B-tree often requires a pattern operator class such as `text_pattern_ops`:

```sql
CREATE INDEX idx_lab_tenant_status_prefix
ON multicol_index_lab.orders
    (tenant_id, status text_pattern_ops);
```

This supports prefix matching when predicates and operator classes align. Never expect it to accelerate:

```sql
WHERE status LIKE '%aid%'
```

because a leading wildcard cannot map to a B-tree prefix range. For arbitrary substrings or full-text search, evaluate `pg_trgm` GIN or FTS if extensions and workloads fit.

### 21.2. An Index Is More Than a List of Column Names

A B-tree definition specifies:

- `ASC` or `DESC` per column.
- `NULLS FIRST` / `NULLS LAST`.
- `COLLATE` on text columns.
- Operator class such as `text_pattern_ops`.
- Expression keys.
- `INCLUDE` payload columns.
- `WHERE` partial index predicates.

When comparing two “similar” indexes, inspect all of these properties; comparing column names alone leads to mistaken deletions.

## 22. Reading EXPLAIN: Index Cond vs. Filter

Inspect a query:

```sql
EXPLAIN
SELECT order_id, created_at, status
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND status = 'paid';
```

When PostgreSQL uses `(tenant_id, created_at, status)`, the plan may display `Index Cond`, `Filter`, or predicates applied across stages depending on the plan. These terms have distinct meanings:

| EXPLAIN Detail | How to Interpret It |
| --- | --- |
| `Index Cond` | Predicates passed to the index access method while scanning the index. |
| `Filter` | Predicates evaluated at that node after retrieving candidate entries/rows. |
| `Rows Removed by Filter` | Rows discarded by `Filter` at that node during `ANALYZE`. |
| `Rows Removed by Index Recheck` | Rows discarded during recheck steps, such as lossy bitmap heap scans. |
| `Heap Fetches` | Heap accesses during `Index Only Scan` when visibility is not proven from the visibility map alone. |

**A column appearing in `Index Cond` does not guarantee it narrows the leaf scan range the way a leading equality condition does.** In a multi-column B-tree, trailing predicates can be evaluated inside the index while still scanning wide ranges left open by earlier columns.

### 22.1. Illustrative Plan Example

```text
Index Scan using idx_lab_tenant_time_status on orders
  Index Cond: (
      tenant_id = 1
      AND created_at >= <cutoff>
  )
  Filter: (status = 'paid')
```

This is **not** a guaranteed output plan in PostgreSQL. In many situations PostgreSQL pushes `status` into `Index Cond` too, picks another index, or runs `Seq Scan`. The diagram illustrates the right question to ask: **how many index entries and heap pages were actually visited?**

### 22.2. Questions to Ask When Reading a Plan

1. Which index did PostgreSQL choose, and what is its key order?
2. Which predicates sit in `Index Cond`?
3. Is there a post-index `Filter`, and how many rows did it discard?
4. Is there a `Sort` or `Incremental Sort`, and why?
5. Is there a `LIMIT`, and can the scan stop early?
6. Is it using `Bitmap Heap Scan` / `BitmapAnd`?
7. If `Index Only Scan`, is `Heap Fetches` high?
8. Do estimated `rows` diverge sharply from `actual rows`?
9. Do buffer hits/reads and execution time match expectations?

## 23. EXPLAIN (ANALYZE, BUFFERS): Measuring on Meaningful Data

Test:

```sql
ANALYZE multicol_index_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

With 24 rows, `Seq Scan + Sort` is a completely sensible plan. The lesson is that **the planner estimates cost** from current statistics and row counts—never blindly guaranteeing a new index will be chosen.

### 23.1. Optional Larger Dataset

To observe clearer differences on a larger table—strictly in a **lab database**—insert 100,000 synthetic rows:

```sql
INSERT INTO multicol_index_lab.orders
    (order_id, tenant_id, customer_id, status,
     created_at, total_amount, store_id, shipped_at)
SELECT
    100000 + g AS order_id,
    1 + (g % 50) AS tenant_id,
    1000 + (g % 500) AS customer_id,
    CASE (g % 4)
        WHEN 0 THEN 'pending'
        WHEN 1 THEN 'paid'
        WHEN 2 THEN 'shipped'
        ELSE 'cancelled'
    END AS status,
    TIMESTAMPTZ '2025-01-01 00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    (50 + (g % 1000))::numeric AS total_amount,
    1 + (g % 4) AS store_id,
    NULL::timestamptz AS shipped_at
FROM generate_series(1, 100000) AS series(g);

ANALYZE multicol_index_lab.orders;
```

These `order_id`s do not collide with `101–308` from the initial seed. **Insert only once**; re-running causes primary-key errors. Generating indexes on 100k rows uses real disk, I/O, and WAL, so keep this strictly off important databases.

**Simulation caveat:** modulo-generated data introduces artificial correlation among tenant, status, customer, and store; it lets you watch the planner at larger scale, not replicate real e-commerce distributions.

### 23.2. Two Competing Queries

Query A — newest orders of any status for a tenant:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Query B — newest paid orders for a tenant:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Evaluate matching indexes:

```sql
CREATE INDEX idx_lab_tenant_latest
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);

CREATE INDEX idx_lab_tenant_status_latest
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);
```

Note that earlier lab steps already created similar indexes differing in trailing columns. Never pile up overlapping indexes like this in a real system; the purpose here is comparing **an index tailored for Query A** against **an index tailored for Query B**.

### 23.3. Modulo Data May Not Mirror Production

Because of how the modulo dataset was generated, certain `(tenant, status)` combinations are skewed or uniform. The planner may produce plans different from intuition—underscoring that **real data cardinality and correlation drive plan costs**. Never judge an index from syntax while ignoring statistics.

## 24. Extended Statistics for Correlated Columns

A classic multi-predicate problem arises when columns are **not independent**:

- In tenant A, 90% of orders are `'paid'`.
- In tenant B, only 5% of orders are `'paid'`.
- Certain customers order exclusively from one store.

If the planner assumes `tenant_id` and `status` are independent, row estimates for `tenant_id = ... AND status = ...` can be wildly wrong.

PostgreSQL provides **extended statistics**:

```sql
CREATE STATISTICS stats_lab_tenant_status
    (dependencies, ndistinct, mcv)
ON tenant_id, status
FROM multicol_index_lab.orders;

ANALYZE multicol_index_lab.orders;
```

Meaning:

- `dependencies`: functional dependency strength between columns where usable by the planner.
- `ndistinct`: estimated distinct count for multi-column combinations.
- `mcv`: multi-column most-common values, helpful under skewed correlations.

### 24.1. Statistics Are Not an Index

`CREATE STATISTICS` does not create a B-tree-style access structure. It improves planner row estimates so PostgreSQL **chooses** better plans and indexes where supported for that query shape.

Do not expect extended statistics to make every `JOIN` and `WHERE` estimate flawless. Applicability varies by query structure and PostgreSQL major version.

### 24.2. Viewing Extended Statistics

```sql
SELECT
    statistics_name,
    schemaname,
    tablename,
    attnames,
    kinds
FROM pg_stats_ext
WHERE schemaname = 'multicol_index_lab'
  AND tablename = 'orders';
```

`pg_stats_ext` shows extended statistics visible to your role. Reliability depends on when `ANALYZE` last ran and how data changed since.

### 24.3. Do Not Confuse Index Column Order with Statistics Column Order

In a B-tree, key order dictates search paths and sorting. In extended statistics, the column list specifies a **set of statistically related columns**; it has no B-tree ordering and does not replace an index.

## 25. Why Doesn't the Highest-Selectivity Column Always Go First?

A popular rule of thumb claims:

> “Always put the most selective column first in a composite index.”

This is **not an absolute rule**.

Suppose:

- `tenant_id` has 50 distinct values.
- `customer_id` has 100,000 distinct values.
- A query always filters `tenant_id = ? AND customer_id = ?`.

Both indexes:

```sql
(tenant_id, customer_id)
(customer_id, tenant_id)
```

pin down the exact pair efficiently. Never put `customer_id` first **solely because it has more distinct values**.

### 25.1. Consider Secondary Queries

| Frequent Query | Index Favoring It |
| --- | --- |
| `WHERE tenant_id = ?` | `(tenant_id, customer_id)`. |
| `WHERE customer_id = ?` across platform | `(customer_id, tenant_id)`. |
| `WHERE tenant_id = ? AND customer_id = ?` | Both handle pair equality lookups well. |
| `WHERE tenant_id = ? ORDER BY customer_id` | `(tenant_id, customer_id)`. |
| `WHERE customer_id = ? ORDER BY tenant_id` | `(customer_id, tenant_id)`. |

### 25.2. Equality Before Range Is a Better Rule of Thumb

For:

```sql
WHERE tenant_id = ?
  AND status = ?
  AND created_at >= ?
ORDER BY created_at DESC
```

`(tenant_id, status, created_at DESC)` fits well because **two equality keys form the prefix, followed immediately by the range/sort key**.

Swapping **the two equality keys** generally matters far less than pushing `created_at` ahead of `status`—because a leading range breaks `status`'s ability to bound a single contiguous slice and changes the sort order.

### 25.3. Skewed Data Distributions

If tenant A holds 90% of rows and tenant B holds 0.01%, the same index can yield different optimal plans per parameter value. Generic prepared plans may also pick a sub-optimal plan for skewed tenants.

Test with **large tenants, small tenants, rare statuses, and common statuses**, rather than just one set of bind values.

## 26. Workload-Driven Tuning: Pick a Few Indexes Instead of Every Permutation

Suppose a system runs four important queries:

| Workload | Sample SQL | Index Direction |
| --- | --- | --- |
| A. Latest orders per tenant | `tenant_id = ? ORDER BY created_at DESC, order_id DESC LIMIT 20` | `(tenant_id, created_at DESC, order_id DESC)` |
| B. Latest orders per status | `tenant_id = ? AND status = ? ORDER BY created_at DESC, order_id DESC LIMIT 20` | `(tenant_id, status, created_at DESC, order_id DESC)` |
| C. Customer order history | `tenant_id = ? AND customer_id = ? ORDER BY created_at DESC, order_id DESC` | `(tenant_id, customer_id, created_at DESC, order_id DESC)` |
| D. Global status feed | `status = ? ORDER BY created_at DESC LIMIT 20` | `(status, created_at DESC)` if high priority |

You do not necessarily need all four immediately. A sound workflow:

1. Collect execution frequencies and latencies for real queries.
2. Identify key SLAs (p95/p99 latency, throughput).
3. Measure each query under current indexes.
4. Prioritize indexes serving **hot paths with meaningful selectivity**.
5. Consider partial indexes if only one status dominates queries.
6. Measure added `INSERT`/`UPDATE`/`DELETE` cost and storage footprint.
7. Remove proven redundant indexes safely.

### 26.1. Why Not Create All 3! Permutations?

Three columns (`tenant_id`, `status`, `created_at`) have six permutations. Adding six indexes on a large table:

- Consumes significant disk space.
- Forces every write to maintain six structures.
- Inflates WAL volume.
- Reduces HOT update opportunities as more attributes are indexed.
- Slows index builds, backups/restores, and maintenance.
- Gives the planner more choices without making queries faster.

Choose indexes from **real queries** rather than enumerating permutations.

### 26.2. INCLUDE Does Not Replace Missing Keys

If workloads A and B compete, trying:

```sql
CREATE INDEX idx_lab_tenant_latest_with_status
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC)
INCLUDE (status);
```

helps Query A and returns `status` from the index, yet **cannot jump directly to `status = 'paid'` the way an index with `status` right after `tenant_id` can**. Query B may still scan many tenant orders and filter `status`.

Conversely, `(tenant_id, status, created_at DESC)` serves B well without providing A's tenant-wide timestamp order. This trade-off cannot be solved with `INCLUDE` alone.

## 27. Cost of Large Composite Indexes

Read acceleration is never free on write-heavy workloads.

### 27.1. INSERT

Every new row inserts entries into all relevant indexes. Wide composite indexes produce larger keys, increasing storage and maintenance I/O.

### 27.2. UPDATE

If an `UPDATE` modifies any column present in an index's keys or `INCLUDE` payload, PostgreSQL must update that index and may lose HOT update eligibility.

Example:

```sql
UPDATE multicol_index_lab.orders
SET status = 'shipped'
WHERE order_id = 102;
```

Every index referencing `status` in its keys or `INCLUDE` incurs update overhead. When `status` changes frequently, maintaining many composite variants containing `status` creates heavy write amplification.

Skip running this `UPDATE` if you want to keep the lab dataset unchanged for earlier exercises, or wrap it in a transaction with `ROLLBACK`.

### 27.3. DELETE and VACUUM

`DELETE`/`UPDATE` generate MVCC dead tuples; `VACUUM` cleans heap and index entries once safe. More indexes mean more `VACUUM` and maintenance work.

### 27.4. Indexing Wide Text Columns

Putting wide text columns into multi-column keys bloats indexes and risks hitting tuple size limits. Never blindly stuff every `WHERE` column into a composite B-tree key, especially long strings or JSONB where other index types belong.

## 28. Multi-Column B-tree vs. Multi-Column GIN, GiST, and BRIN

Despite sharing `CREATE INDEX ... (col1, col2)` syntax, different access methods behave very differently.

### 28.1. GIN

GIN indexes multi-component values such as arrays, `tsvector`, or `JSONB` with matching operator classes.

Example:

```sql
CREATE TABLE multicol_index_lab.documents (
    document_id bigint PRIMARY KEY,
    tags text[] NOT NULL,
    search_vector tsvector NOT NULL
);

CREATE INDEX idx_lab_documents_gin
ON multicol_index_lab.documents
USING GIN (tags, search_vector);
```

Query:

```sql
SELECT document_id
FROM multicol_index_lab.documents
WHERE tags @> ARRAY['postgres']::text[]
  AND search_vector @@ to_tsquery('simple', 'index');
```

GIN does **not** mean “sort keys lexicographically by `(tags, search_vector)` for `ORDER BY`” like a composite B-tree. Never apply B-tree equality-prefix/range rules to this index.

### 28.2. GiST

GiST uses operator classes and region/signature models suited to spatial or range types. Multi-column GiST effectiveness can still be sensitive to the leading column, yet its semantics differ completely from lexicographic B-tree ordering.

Using GiST effectively requires matching data types, operator classes, and target predicates. Never replace B-tree with GiST just because you want a multi-column index.

### 28.3. BRIN

BRIN stores summaries per **block range**, effective when values correlate with physical heap location, such as append-only timestamps:

```sql
CREATE INDEX idx_lab_brin_tenant_created
ON multicol_index_lab.orders
USING BRIN (tenant_id, created_at);
```

BRIN is tiny compared to B-tree, yet it is lossy and may recheck candidate pages. It cannot return the top 20 newest orders in key order like a matching B-tree.

Effectiveness depends on physical correlation and distribution; on small tables or tenant-interleaved loads, BRIN offers little advantage.

### 28.4. Comparison Table

| Criterion | B-tree | GIN | GiST | BRIN |
| --- | --- | --- | --- | --- |
| Equality on key columns | Excellent | Per opclass operators | Per opclass operators | Range-summary pruning where correlated |
| Scalar ranges and standard `ORDER BY` | Excellent in key order | No B-tree ordering | Not standard B-tree order | No B-tree ordering |
| Column order critically important | Yes, lexicographic rules | No B-tree prefix rule | Can matter depending on opclass | No B-tree prefix rule |
| Candidate lookup mechanism | Ordered B-tree keys | Inverted posting entries | Opclass search partitions/bounds | Block-range summaries |

## 29. PostgreSQL Partitioning and Composite Indexes

**Table partitioning** splits data into physical child tables; **composite indexes** sort multiple columns inside an index. They are distinct mechanisms.

Suppose `orders` is partitioned monthly by `created_at`. A query:

```sql
WHERE tenant_id = 1
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-01 00:00+00'
```

can benefit from both:

1. **Partition pruning:** accessing only partitions overlapping the `created_at` range.
2. **Local index scan inside each partition:** using a local index like `(tenant_id, status, created_at)`.

Never assume partitioning eliminates the need for indexes, nor that composite indexes replace partition pruning. Combined value and cost depend on partition count, partition size, and query patterns.

### 29.1. Indexes and Unique Constraints on Partitioned Tables

PostgreSQL enforces strict rules for unique/primary keys on partitioned tables: to guarantee uniqueness across all partitions, any unique key must include all partition key columns under supported rules.

Therefore, when migrating a plain table to a partitioned table, **never copy a composite `UNIQUE` constraint assuming PostgreSQL automatically enforces table-wide uniqueness identically**. Design partition keys and unique constraints together.

### 29.2. Local Index Order Still Matters

An index inside each partition such as `(tenant_id, created_at DESC)` follows the exact same B-tree prefix and sort rules as on an unpartitioned table. Scanning multiple partitions may also add merge/sort overhead at the parent level.

## 30. Workflow for Choosing Column Order in Real Projects

Start from **a catalog of real queries**, not the table's column list.

### Step 1. List Frequent Queries

Example:

```text
Q1: tenant_id=? ORDER BY created_at DESC, order_id DESC LIMIT 20
Q2: tenant_id=? AND status=? ORDER BY created_at DESC LIMIT 20
Q3: tenant_id=? AND customer_id=? ORDER BY created_at DESC LIMIT 50
Q4: status=? AND created_at >= ?  (global report)
```

### Step 2. Classify Predicates

For each query:

- **Equality**: `=`, exact-match filters.
- **Range**: `<`, `<=`, `>`, `>=`, time intervals.
- **Multi-value**: `IN`, `ANY`, `OR`.
- **ORDER BY**: column sequence, `ASC`/`DESC`, `NULLS` handling.
- **LIMIT**: is early termination desired?
- **SELECT list**: would `INCLUDE`/index-only scans pay off?

### Step 3. Design a Candidate Index

Place frequently co-occurring equality columns first, followed by range/sort columns matching the workload. Among equality columns, weigh prefix reuse and secondary queries.

Example:

```sql
CREATE INDEX idx_candidate
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);
```

### Step 4. Evaluate Against Competing Queries

This index helps Q2, yet fails to supply Q1's `created_at` order directly when `status` is omitted. Consider a dedicated index for Q1 if Q1 is critical enough.

### Step 5. Verify Statistics and Plans

```sql
ANALYZE multicol_index_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Inspect actual rows, `Sort` nodes, buffer reads/hits, `Heap Fetches`, startup/total time, and index selection. Repeat across parameters with varying selectivity.

### Step 6. Measure Write Costs

Measure `INSERT`/`UPDATE`/`DELETE` latency, WAL generation, index size, `VACUUM`, and storage. If `status` mutates constantly, indexing it incurs substantial write cost.

### Step 7. Keep Only Proven Useful Indexes

Consolidate or drop redundant indexes based on evidence, always with a rollback plan and hot-path monitoring in production.

## 31. Building Indexes on Live Systems

Typical lab command:

```sql
CREATE INDEX idx_lab_example
ON multicol_index_lab.orders (tenant_id, created_at);
```

In production, a standard build blocks concurrent writes for its duration. PostgreSQL provides `CREATE INDEX CONCURRENTLY` under supported rules to minimize write blocking:

```sql
-- Illustrative pattern; verify locks, disk space, and version before running:
CREATE INDEX CONCURRENTLY idx_lab_example_concurrent
ON multicol_index_lab.orders (tenant_id, created_at);
```

Remember:

- `CREATE INDEX CONCURRENTLY` **cannot run inside an explicit transaction block**.
- It generally takes more work and wall-clock time than a standard build.
- It must wait for active transactions/snapshots across multiple phases.
- Failures or cancellations can leave behind an **`INVALID` index** requiring cleanup.
- It still consumes CPU, I/O, WAL, and disk space.

Never treat `CONCURRENTLY` as “zero-impact magic” in production. Plan rollout, monitoring, and rollback carefully.

### 31.1. Monitoring Index Build Progress

```sql
SELECT
    pid,
    relid::regclass AS table_name,
    index_relid::regclass AS index_name,
    command,
    phase,
    blocks_total,
    blocks_done
FROM pg_stat_progress_create_index;
```

This view reports live index build progress in supported PostgreSQL versions. Zero rows simply means no index build is currently running at that instant.

### 31.2. Inspecting Existing Index Definitions

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'multicol_index_lab'
ORDER BY tablename, indexname;
```

`indexdef` shows column order, sort direction, `INCLUDE`, `WHERE`, and access method.

### 31.3. Inspecting Index Usage and Sizes

```sql
SELECT
    s.schemaname,
    s.relname AS table_name,
    s.indexrelname AS index_name,
    s.idx_scan,
    s.idx_tup_read,
    s.idx_tup_fetch,
    pg_size_pretty(pg_relation_size(s.indexrelid))
        AS index_size
FROM pg_stat_user_indexes AS s
WHERE s.schemaname = 'multicol_index_lab'
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

Usage counters can be reset; low counts do not prove an index is useless if it backs a constraint, serves rare batch jobs, or was recently created. Nor do `idx_tup_read` and `idx_tup_fetch` always match 1:1 due to index-only scans, bitmaps, and visibility checks.

## 32. Common Misconceptions

### Misconception 1. “The highest-selectivity column must always go first”

False. For co-occurring equality predicates, either order narrows to the exact pair; weigh prefix reuse, ranges, sorting, joins, and the full workload.

### Misconception 2. “Index (a, b, c) is equivalent to (c, b, a)”

False. They sort keys in completely different lexicographic orders and serve different partial filters and sorts.

### Misconception 3. “Without filtering on a, index (a, b) is completely useless”

Not strictly true. Skip scan or alternative paths can apply when supported and cost-effective, though `(a, b)` is not naturally optimal for `b`-only lookups.

### Misconception 4. “A trailing column in Index Cond means only matching rows are scanned”

False. Predicates after a range or missing prefix can be evaluated inside the index while still scanning wide key ranges left open by preceding columns.

### Misconception 5. “Having equality everywhere else is enough; ORDER BY doesn't matter”

False. On `(tenant, status, created_at)`, pinning `tenant` without pinning `status` does not provide tenant-wide `created_at` ordering.

### Misconception 6. “Two single-column indexes equal one two-column index”

False. Bitmap combinations lose B-tree sort order and have different execution costs from a single composite index.

### Misconception 7. “If an index contains all SELECT columns, Index Only Scan is guaranteed”

False. The planner weighs cost and MVCC visibility; `Heap Fetches` can still be high.

### Misconception 8. “INCLUDE status filters status just like a key column”

False. `INCLUDE` holds non-key payload data and does not participate in B-tree ordering or search bounds.

### Misconception 9. “DESC always requires a separate DESC index”

False. PostgreSQL can scan a B-tree backward when directions align cleanly. Mixed directions and `NULL` ordering still need careful design.

### Misconception 10. “ORDER BY just needs an index containing those columns in any order”

False. `(a, b)` differs from `(b, a)`, and an unconstrained column in the middle breaks the sort order of trailing columns.

### Misconception 11. “A composite index is always faster than Seq Scan”

False. On small tables or low-selectivity predicates, `Seq Scan` is cheaper.

### Misconception 12. “Partial indexes work with any bind parameter”

False. The planner must prove the query implies the index predicate. A generic prepared plan with `status = $1` cannot assume `'pending'`.

### Misconception 13. “Partial index WHERE created_at >= now() - 7 days creates a rolling index”

False. Time-dependent non-immutable functions are rejected in index predicates. Sliding cutoffs belong in queries or retention partitioning.

### Misconception 14. “Composite UNIQUE forces each column to be unique on its own”

False. `UNIQUE(a, b)` enforces uniqueness of the **tuple pair** (subject to `NULL` rules), not of `a` or `b` individually.

### Misconception 15. “UNIQUE(a, b) and UNIQUE(b, a) have different pair uniqueness”

Under identical `NULL` semantics, pair uniqueness is identical; only **index key order** and query usability differ.

### Misconception 16. “NULLS FIRST/LAST doesn't affect index order”

False. `NULL` placement is an integral part of B-tree ordering and `ORDER BY` matching.

### Misconception 17. “EXPLAIN on 24 rows proves a new index is fast”

False. On tiny tables `Seq Scan` wins; test with representative data volumes and parameters.

### Misconception 18. “Fewer indexes are always better”

False. Hot-path queries often need dedicated indexes. Balance read latency, write throughput, storage, and maintenance.

### Misconception 19. “More indexes are always better since the planner chooses”

False. Every index adds write overhead and resource usage; duplicate indexes hurt without helping.

### Misconception 20. “GROUP BY or DISTINCT ON always uses a composite index”

False. An index may supply order, yet the planner can still pick hashing, sorting, or scanning if cheaper.

### Misconception 21. “B-tree column-order rules apply identically to GIN/GiST/BRIN”

False. Each access method has its own mechanics and operator classes.

### Misconception 22. “Table partitioning replaces composite indexes”

False. Pruning narrows partitions; local indexes still accelerate queries **inside** each partition.

### Misconception 23. “A status-only query definitely needs composite (tenant, status)”

False. If status-only is a hot path, an index leading with `status` may fit better; measure on the workload.

### Misconception 24. “CREATE INDEX CONCURRENTLY can never wait or block”

False. It avoids blocking normal writes during scanning, yet runs in multiple phases, waits on transactions, and requires monitoring.

## 33. Practice Exercises

Exercises use `multicol_index_lab` from Sections 3, 13, 14, 19, and 28. When asked to create an index, test in a lab database rather than adding every variant to a single production table. For plan questions, focus on **capability and what to inspect**, without assuming the planner must pick one specific node on tiny data.

### Exercise 1. Explain Key Ordering

A B-tree index is defined as:

```sql
CREATE INDEX idx_exercise_1
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC);
```

Describe the key order across multiple tenants, statuses, and timestamps. Are rows within the same tenant sorted by `created_at DESC` **across the whole tenant**?

### Exercise 2. Prefix Lookup

With `(tenant_id, status, created_at DESC)`, how do these two queries differ in narrowing the scanned key range?

```sql
-- A
WHERE tenant_id = 1
  AND status = 'paid'

-- B
WHERE status = 'paid'
```

### Exercise 3. Multiple Equality Predicates

A query always filters `tenant_id = ? AND customer_id = ?`. Can you claim `(customer_id, tenant_id)` is always faster than `(tenant_id, customer_id)` simply because `customer_id` has higher cardinality?

### Exercise 4. Equality and Range

Design a composite B-tree index for:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 2
  AND status = 'paid'
  AND created_at >= TIMESTAMPTZ '2026-10-01 00:00+00'
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

Explain the column order.

### Exercise 5. ORDER BY When Status Is Omitted

Does `(tenant_id, status, created_at DESC)` directly satisfy:

```sql
WHERE tenant_id = 1
ORDER BY created_at DESC
```

across the whole tenant? Why or why not?

### Exercise 6. Top-N per Tenant

Design an index to fetch the 20 newest orders for a tenant with deterministic tie-breaking when timestamps collide.

### Exercise 7. IN Across Multiple Statuses

Why might `WHERE tenant_id = 1 AND status IN ('paid', 'shipped') ORDER BY created_at DESC` still require a sort despite having `(tenant_id, status, created_at DESC)`?

### Exercise 8. Backward Scan

Can `(tenant_id ASC, created_at ASC)` assist `WHERE tenant_id = 1 ORDER BY created_at DESC`? When is a separate mixed-direction index needed?

### Exercise 9. NULLS LAST

Write a suitable index for:

```sql
SELECT order_id, shipped_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY shipped_at DESC NULLS LAST
LIMIT 10;
```

### Exercise 10. Keyset Pagination

Given `ORDER BY created_at DESC, order_id DESC` and cursor `(2026-10-04 08:00+00, 104)` from the end of the previous page, write the `WHERE` clause to fetch the next page in tenant 1.

### Exercise 11. Composite UNIQUE

Design a constraint making `external_order_no` unique **within each tenant** while allowing the same code across two different tenants. Does this make `external_order_no` globally unique by itself?

### Exercise 12. Nullable Unique

Explain how PostgreSQL handles `NULL` by default in composite unique keys. Starting in PostgreSQL 15, what syntax treats `NULL`s as non-distinct for uniqueness?

### Exercise 13. INCLUDE

Design an index supporting paid-order lookup by tenant sorted newest-first and returning `total_amount` without making `total_amount` a key column. Why doesn't `INCLUDE` help filter on `total_amount` like a key column?

### Exercise 14. Index-Only Scan

If an index contains every column read by a query, can PostgreSQL skip all heap accesses automatically? What are the roles of the visibility map and `Heap Fetches`?

### Exercise 15. Partial Index

Design a compact index for a screen showing only the latest pending orders per tenant. Can a query searching for shipped orders rely on this index for complete results?

### Exercise 16. Prepared Statements with Partial Indexes

Why might `WHERE status = $1` skip a `status = 'pending'` partial index when PostgreSQL picks a generic plan?

### Exercise 17. Expression Index

Write a unique index ensuring no two emails within the same tenant collide under `lower(email)`. Which query form matches that expression?

### Exercise 18. Bitmap Index Combination

Suppose only `(tenant_id)` and `(status)` exist. How can PostgreSQL combine them for a query with both predicates? Why might `ORDER BY created_at DESC LIMIT 20` still require a `Sort`?

### Exercise 19. Index Cond vs. Filter

A plan shows `Index Cond: tenant_id = 1` and `Filter: status = 'paid'`. What does this tell you, and what does it **fail to prove** about cost?

### Exercise 20. Small Data and EXPLAIN

Why might PostgreSQL ignore a matching composite index on a 24-row table? Which command measures actual runtime metrics and buffer usage?

### Exercise 21. DISTINCT ON

Write an index for selecting the latest order **per customer within each tenant** using `DISTINCT ON (tenant_id, customer_id)` with tie-breaker `order_id`.

### Exercise 22. Extended Statistics

`tenant_id` and `status` are strongly correlated. Write `CREATE STATISTICS` for `mcv` and `dependencies`, then refresh statistics. Why is this not an index?

### Exercise 23. UPDATE Costs

A table has 10 composite indexes all including `status`, and `status` changes frequently. What happens to write throughput, WAL, storage, and HOT updates?

### Exercise 24. Skip Scan

Can `(store_id, customer_id)` serve `WHERE customer_id = 10` in certain PostgreSQL versions? When can skip scan pay off, and why shouldn't you rely on it blindly?

### Exercise 25. B-tree vs. BRIN

A massive log table is appended chronologically and queried mostly across broad time intervals. Briefly compare a timestamp BRIN against a `(tenant_id, created_at)` B-tree. Do both equally support `ORDER BY created_at DESC LIMIT 20`?

### Exercise 26. Workload-Based Index Design

You have three queries:

```text
Q1: WHERE tenant_id=? ORDER BY created_at DESC LIMIT 20
Q2: WHERE tenant_id=? AND status=? ORDER BY created_at DESC LIMIT 20
Q3: WHERE tenant_id=? AND customer_id=? ORDER BY created_at DESC LIMIT 20
```

Propose candidate indexes and explain why you may not need to build all three.

## 34. Suggested Solutions

### Answer 1. Key Ordering

The index sorts by `tenant_id` first, then `status` within each tenant, then `created_at DESC` within each `(tenant, status)` pair. It does **not** order rows by `created_at DESC` across an entire tenant when `status` is unconstrained.

### Answer 2. Prefix

Query A filters both leading columns by equality, allowing the B-tree to jump directly to `(tenant = 1, status = 'paid')`. Query B omits `tenant_id`: `'paid'` rows are scattered across all tenants; the index might still be scanned via alternative strategies, yet without the contiguous-slice benefit. If status-only is a hot path, consider an index leading with `status`.

### Answer 3. Ordering Equality Keys

No. Either order works well when both columns appear with equality. Choose based on single-column prefix queries, `ORDER BY`, and the wider workload rather than single-column cardinality alone.

### Answer 4. Equality Then Range/Sort

```sql
CREATE INDEX idx_exercise_4
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);
```

The first two columns handle equality, followed by timestamp for range filtering and sorting, with `order_id` breaking ties. This is a strong candidate index; PostgreSQL will still choose `Seq Scan` on tiny data.

### Answer 5. Status in the Middle

Not directly across the whole tenant. The index groups by `status` ahead of `created_at`, so timestamps are sorted only inside each status group. PostgreSQL needs a `Sort` or a dedicated `(tenant_id, created_at DESC)` index.

### Answer 6. Top-N

```sql
CREATE INDEX idx_exercise_6
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);
```

Query:

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

`order_id` breaks timestamp ties, keeping output ordering and pagination cursors deterministic.

### Answer 7. IN

`IN` on `status` matches multiple separate status blocks. Each block is ordered by `created_at` individually, not globally merged across statuses. PostgreSQL may require a `Sort` or another plan.

### Answer 8. Backward Scan

Yes. When `tenant_id` is fixed by equality, scanning that tenant's slice backward provides `created_at DESC`. If `tenant_id` is not fixed and you need `tenant_id ASC, created_at DESC`, a mixed-direction index is needed because scanning `(ASC, ASC)` backward reverses both columns.

### Answer 9. NULL Ordering

```sql
CREATE INDEX idx_exercise_9
ON multicol_index_lab.orders
    (tenant_id, shipped_at DESC NULLS LAST);
```

Once `tenant_id` is fixed, the index directly supplies `shipped_at DESC NULLS LAST`.

### Answer 10. Keyset

```sql
SELECT order_id, created_at
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-04 08:00+00', 104)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

The tuple comparison with two `DESC` keys selects rows following the cursor. Real systems must also account for `NULL`s, matching filters, and concurrent mutations between pages.

### Answer 11. Composite Uniqueness

```sql
CREATE TABLE multicol_index_lab.partner_refs (
    tenant_id integer NOT NULL,
    external_order_no text NOT NULL,
    UNIQUE (tenant_id, external_order_no)
);
```

`external_order_no` is not unique on its own. `'INV-001'` in tenant 1 and `'INV-001'` in tenant 2 are both permitted.

### Answer 12. NULLs

By default, standard unique constraints allow multiple combinations containing `NULL`s because `NULL`s are treated as distinct. PostgreSQL 15+ adds:

```sql
UNIQUE NULLS NOT DISTINCT (tenant_id, optional_code)
```

Verify business rules before choosing `NULL` semantics.

### Answer 13. INCLUDE

```sql
CREATE INDEX idx_exercise_13
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

`total_amount` is non-key payload data, excluded from key sorting and searching. It enables index-only scans when the visibility map allows, yet does not make `total_amount` predicates narrow index key ranges.

### Answer 14. Index-Only

Not guaranteed. PostgreSQL must still confirm MVCC visibility; if heap pages are not all-visible, `Index Only Scan` performs heap reads. `Heap Fetches` tracks those checks, and the planner can also pick a different plan altogether.

### Answer 15. Partial Index

```sql
CREATE INDEX idx_exercise_15
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC)
WHERE status = 'pending';
```

Because it indexes only `'pending'` rows, it cannot serve a query looking for `'shipped'` rows.

### Answer 16. Generic Prepared Plan

In a generic plan, `status = $1` could bind any value, failing to prove the query always satisfies `status = 'pending'`. A custom plan for a specific execution might differ, so test plans with real driver execution patterns.

### Answer 17. Expression Index

```sql
CREATE UNIQUE INDEX idx_exercise_17
ON multicol_index_lab.contacts
    (tenant_id, lower(email));
```

Lookup:

```sql
SELECT contact_id
FROM multicol_index_lab.contacts
WHERE tenant_id = 1
  AND lower(email) = lower('Alice@Example.com');
```

Full email normalization depends on business rules and collations.

### Answer 18. Bitmap

The planner can combine two `Bitmap Index Scan`s via `BitmapAnd`, followed by `Bitmap Heap Scan`. Because bitmaps do not preserve B-tree order, `ORDER BY` on time still requires sorting and loses early-stop top-N efficiency.

### Answer 19. EXPLAIN

The plan uses the index on `tenant_id` and filters `status` at the scan node. That alone does not prove efficiency—check rows, buffers, timing, cache state, and selectivity. A different index might push `status` into `Index Cond` too.

### Answer 20. EXPLAIN ANALYZE

On tiny tables, `Seq Scan` beats traversing an index and heap. Measure with:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM multicol_index_lab.orders
WHERE tenant_id = 1
  AND status = 'paid';
```

Actual plans depend on row counts, cache, and existing indexes.

### Answer 21. DISTINCT ON

```sql
CREATE INDEX idx_exercise_21
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

```sql
SELECT DISTINCT ON (tenant_id, customer_id)
    tenant_id, customer_id, order_id, created_at
FROM multicol_index_lab.orders
ORDER BY
    tenant_id, customer_id,
    created_at DESC, order_id DESC;
```

The index supplies the matching group and tie-breaker order, though the planner decides by cost.

### Answer 22. Extended Statistics

```sql
CREATE STATISTICS stats_exercise_22
    (dependencies, mcv)
ON tenant_id, status
FROM multicol_index_lab.orders;

ANALYZE multicol_index_lab.orders;
```

Extended statistics improve planner cardinality/correlation estimates; they do not store ordered TID pointers like a B-tree index.

### Answer 23. Write Cost

Every `UPDATE` changing `status` must update multiple indexes, increasing WAL, I/O, and storage. Modifying columns present in index keys or `INCLUDE` blocks HOT updates as well. Prune indexes that fail to earn their maintenance cost.

### Answer 24. Skip Scan

Possible on PostgreSQL versions supporting skip scan when costs favor it—especially when leading `store_id` has very few distinct values and `customer_id` is selective. It is not guaranteed; if `customer_id`-only queries are critical, benchmark or add an index leading with `customer_id`.

### Answer 25. BRIN

BRIN is compact and suited for block-range filtering on physically correlated logs, yet **lacks B-tree ordering** for exact top-N queries. B-tree `(tenant_id, created_at)` serves tenant + time lookups and ordered sorts at higher storage and write cost.

### Answer 26. Candidate Index Set

Potential candidates:

```sql
-- Q1: tenant-wide chronological feed
CREATE INDEX idx_workload_q1
ON multicol_index_lab.orders
    (tenant_id, created_at DESC, order_id DESC);

-- Q2: tenant + status chronological feed
CREATE INDEX idx_workload_q2
ON multicol_index_lab.orders
    (tenant_id, status, created_at DESC, order_id DESC);

-- Q3: tenant + customer chronological feed
CREATE INDEX idx_workload_q3
ON multicol_index_lab.orders
    (tenant_id, customer_id, created_at DESC, order_id DESC);
```

In the lab, **there is no need to create all three** if equivalent indexes already exist from earlier sections. In production, weigh query frequency, selectivity, latency SLAs, and write cost; often only one or two hot queries justify dedicated indexes while remaining queries still meet SLAs via alternative plans.

## 35. Checklist for Designing and Operating Composite Indexes

Before adding a new index, answer:

1. **Which queries need optimization?** Do we have real SQL and frequency/latency numbers?
2. **What is the table's grain?** One row per order, line items, or multi-tenant records?
3. **Which equality predicates always appear?** Can they form a useful leading prefix?
4. **Which column uses a range?** Where should it sit after the equality keys?
5. **What does `ORDER BY` need?** Do column order, `ASC`/`DESC`, `NULLS`, and collation match?
6. **Is there a `LIMIT`?** Can the index avoid sorting and stop early?
7. **Is there a tie-breaker?** Does pagination have deterministic ordering via a unique key?
8. **Do hot queries omit the leading column?** Do we need another index, or do skip scan/bitmaps suffice?
9. **Does `IN` match one or multiple values?** Do multiple groups break global sorting?
10. **Does `INCLUDE` truly pay off?** Are included columns worth the extra size to avoid heap fetches?
11. **Does a partial index fit?** Can queries provably imply the predicate, especially prepared statements?
12. **Do expressions and collations match the SQL?** Are columns cast or wrapped in `lower()`?
13. **What business rule does a composite `UNIQUE` enforce?** Are `NULL` semantics right?
14. **Have existing composite indexes been audited?** Can a prefix-matching index be reused?
15. **Are statistics fresh?** Do we need `ANALYZE` or extended statistics for correlated columns?
16. **Is test data representative?** Does it include large/small tenants and rare/common statuses?
17. **Did you measure real `EXPLAIN` output?** Check `Sort`, `Bitmap`, `Index Only`, `Heap Fetches`, and buffers.
18. **How much does write cost increase?** Are indexed or `INCLUDE` columns updated frequently?
19. **Are disk space and WAL capacity sufficient?** Large builds consume major resources.
20. **Is the production rollout safe?** Plan concurrent builds, monitoring, and invalid-index recovery.
21. **Are there partitioning constraints?** How do index and unique keys interact with partition keys?
22. **Are child-table JOIN/FK columns indexed?** Never assume foreign keys create child indexes automatically.

## 36. Quick Decision Flowchart

```text
                       Query to optimize
                              |
                              v
                    Identify equality keys
                              |
                              v
                    Has range or ORDER BY?
                       /              \
                     Yes              No
                      |                |
                      v                v
            Place range/order    Consider prefix reuse
            after equality keys  and partial-filter queries
                      |                |
                      +--------+-------+
                               |
                               v
                         Has LIMIT?
                        /          \
                      Yes          No
                       |            |
                       v            v
               Check early stop  Measure selectivity,
               and Sort removal  scans, and bitmaps
                       |            |
                       +------+-----+
                              |
                              v
                    Need returned columns?
                              |
                              v
                      Consider INCLUDE
                              |
                              v
                   Need partial/expression?
                              |
                              v
                    ANALYZE + real EXPLAIN
                              |
                              v
                  Weigh read gain vs write cost
                              |
                              v
                  Keep minimal high-value indexes
```

This flowchart is a **guiding heuristic**, not a mechanical algorithm guaranteed to produce the optimal index for every workload. Mixed query patterns or partitioned tables require holistic evaluation.

## 37. Summary

Multi-column indexes in PostgreSQL—especially **B-trees**—are powerful tools that must be designed around **real queries**:

- **Column order dictates key order.** `(tenant_id, status, created_at)` differs fundamentally from `(tenant_id, created_at, status)`, especially when the middle column is unconstrained.
- **Leading equality prefix + trailing range/sort column** is a strong pattern to narrow scan spans and avoid sorts—yet it is a heuristic, not a rigid rule for every plan.
- **Multiple equality keys** can often be swapped while preserving pair lookup efficiency; prefix reuse, sorting, and secondary queries decide the better order.
- **Omitting the leading column does not automatically make an index unusable.** PostgreSQL has alternative paths, including skip scan in supported scenarios, though you should measure rather than assume it.
- **`ORDER BY ... LIMIT`** is a prime reason to order timestamps and tie-breakers carefully; keyset pagination avoids costly large `OFFSET`s.
- **`INCLUDE`** carries non-key payload columns for covering reads/index-only scans without turning them into search keys; index-only scans still depend on the visibility map and planner costs.
- **Composite `UNIQUE`, partial, and expression indexes** address correctness and specialized queries; mind `NULL`s, collations, predicates, and prepared statements.
- **Multiple single-column indexes** can combine via bitmaps, yet bitmaps lose B-tree sort order; a well-ordered composite index avoids sorts on top-N hot paths.
- **Impact goes beyond `SELECT`.** Every index adds storage, `INSERT`/`UPDATE`/`DELETE` overhead, WAL, and maintenance cost.
- **`EXPLAIN (ANALYZE, BUFFERS)` on representative data** provides the only trustworthy evidence for key ordering—never guess from SQL syntax or a 24-row toy table.

Principle to remember:

> Don't ask “which columns are on the table so we can put them all in an index?”. Ask **“what values will PostgreSQL filter on, in what order must keys be traversed, where can the scan stop early, and which other queries can reuse that index?”**

Answering those four questions lets you design composite index column order deliberately rather than guessing permutations.
