# INCLUDE, Covering Indexes, and Index-Only Scans in PostgreSQL

Suppose an e-commerce system frequently displays the **20 most recent orders for a customer**, showing order ID, creation date, status, and total amount:

```sql
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

If PostgreSQL has a B-tree index on `customer_id`, the database can locate that customer's orders faster than scanning the entire table. Yet to fetch `ordered_at`, `status`, and `total_amount`, the executor may still have to visit the **heap table** for every row. When this query runs very frequently and the heap is large, those heap accesses can consume substantial I/O.

One design approach is:

```sql
CREATE INDEX idx_orders_customer_recent_cover
ON orders (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Here:

- `customer_id`, `ordered_at`, and `order_id` are the **key columns** of the index: used to structure B-tree ordering, search, or satisfy `ORDER BY` when conditions align.
- `status` and `total_amount` are **included columns** or **payload/non-key columns**: stored in the index entry so they can be read from the index, yet **they do not participate in B-tree ordering and are not search keys**.
- Because the index holds every column the query needs, it is a **covering index for this query**.
- When MVCC/visibility conditions allow, PostgreSQL can choose an **Index Only Scan** to return results without accessing the heap for most or all rows.

However, **`INCLUDE` does not automatically guarantee `Index Only Scan`**, and **`Index Only Scan` does not automatically guarantee `Heap Fetches = 0`**. This lesson focuses on both points to prevent guesswork-driven index tuning.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **index keys** from **included (non-key) columns**.
2. Understand that a covering index is a **query-dependent** concept, not a type of index that universally “covers” every query.
3. Write PostgreSQL `CREATE INDEX ... INCLUDE (...)` syntax accurately.
4. Explain **Index Scan**, **Bitmap Heap Scan**, **Index Only Scan**, and how the planner chooses among them.
5. Understand the role of the **visibility map**, the **all-visible** bit, MVCC, and `VACUUM` in reducing heap fetches.
6. Analyze `EXPLAIN (ANALYZE, BUFFERS)`, especially `Index Cond`, `Filter`, and `Heap Fetches`.
7. Know which columns belong in keys vs. `INCLUDE`, and when not to add `INCLUDE`.
8. Understand trade-offs in **index size, `INSERT`/`UPDATE` speed, HOT updates, bloat, WAL**, and maintenance.
9. Combine `INCLUDE` with unique indexes, partial indexes, multi-column indexes, and `LIMIT` queries.
10. Design safe experiments to **measure** benefits instead of assuming gains from syntax alone.

## 2. Mental Model: Heap Tables vs. B-tree Indexes

In a standard PostgreSQL table, row records live in the **heap**. A B-tree index stores index entries containing **keys** and pointers locating the corresponding tuples. When a query needs a row, PostgreSQL can use the index to narrow down where to look.

A simple illustration:

```text
B-TREE INDEX                              HEAP TABLE
customer_id / ordered_at / order_id       All columns of the order
            |
            +-- locate entry --------------> read tuple in heap
                                               |
                                               +-- status
                                               +-- total_amount
                                               +-- note
                                               +-- ...
```

Indexes typically help **avoid reading every row in the table**. Yet after locating positions, the executor may still have to read the heap to fetch columns missing from the index or verify tuple visibility.

### 2.1. Traditional Index Scan

When a query selects `total_amount` while the index holds only `customer_id`, the executor may:

1. Traverse the B-tree to find entries with `customer_id = 42`.
2. Retrieve the matching tuple locations.
3. Visit the heap to read tuples and extract `total_amount`.
4. Apply any residual filters not handled in the index.
5. Return results.

If few rows are returned and heap pages are already cached, this works very well. If many rows scatter across numerous heap pages, heap accesses can add substantial cost.

### 2.2. Index Only Scan

With an index storing **all data required by the query**, PostgreSQL can locate and return data straight from the index. However, an index entry itself **does not hold enough MVCC metadata to prove whether the tuple is visible to the query's snapshot**. PostgreSQL must consult the **visibility map** or fall back to checking the heap.

The meaning of `Index Only Scan` is: **capable of avoiding the heap because needed columns reside in the index**, not a promise of “never reads the heap.”

### 2.3. What Problem Does a Covering Index Solve?

If a query only needs `customer_id`, `ordered_at`, `order_id`, `status`, and `total_amount`, placing non-search display columns into `INCLUDE` ensures the executor **has the values available right in the index**.

This optimization **trades disk space and write overhead for the chance to skip heap reads**—it is never a free feature.

## 3. INCLUDE Syntax

B-tree example:

```sql
CREATE INDEX index_name
ON table_name (key_column_1, key_column_2)
INCLUDE (payload_column_1, payload_column_2);
```

Unique index example:

```sql
CREATE UNIQUE INDEX index_name
ON table_name (unique_key_1, unique_key_2)
INCLUDE (payload_column);
```

PostgreSQL also supports `INCLUDE` in compatible constraint/index definitions. Support depends on the **index access method**: **B-tree** is the primary example because it can return column values directly from index tuples. Other access methods support `INCLUDE` per their own capabilities; never assume every method—especially **GIN**—behaves like B-tree or supports `Index Only Scan`.

### 3.1. Three Column Roles to Distinguish

| Group | Where It Lives | Effect |
| --- | --- | --- |
| **Key column** | Inside the index key structure | Searching, range comparisons, sorting, uniqueness on unique indexes |
| **INCLUDE column** | Index entry payload where supported | Can return extra values to queries; creates no new ordering or key-search path |
| **Heap-only column** | Not stored in this index | Queries needing this column must visit the heap |

Example:

```sql
CREATE INDEX idx_demo_cover
ON some_table (tenant_id, created_at DESC)
INCLUDE (amount, status);
```

This is illustrative DDL assuming the table exists. `tenant_id` and `created_at` are keys, while `amount` and `status` are payload.

### 3.2. INCLUDE Does Not Create a “Third Key”

Do not equate:

```sql
CREATE INDEX idx_key_amount
ON some_table (tenant_id, created_at, amount);
```

with:

```sql
CREATE INDEX idx_include_amount
ON some_table (tenant_id, created_at)
INCLUDE (amount);
```

In the first index, `amount` is a **key**, shaping B-tree order and search opportunities. In the second index, `amount` is **payload**, stored purely for data retrieval.

Putting `amount` in `INCLUDE` does not turn:

```sql
WHERE amount > 100000
```

into an efficient B-tree **`Index Cond`** the way making `amount` a properly positioned key column can.

## 4. Covering Index Is a Query-Specific Concept

Consider the index:

```sql
CREATE INDEX idx_orders_cover
ON orders (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Query A:

```sql
SELECT order_id, ordered_at, status, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

All output and filter columns exist in the index. It **can cover Query A**.

Query B:

```sql
SELECT
    order_id,
    ordered_at,
    status,
    total_amount,
    customer_note
FROM orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Because `customer_note` is absent from the index, Query B **is not covered by this index**, even though it adds only one column over Query A.

Query C:

```sql
SELECT COUNT(*)
FROM orders
WHERE customer_id = 42;
```

The index has enough information to satisfy Query C, even though C uses none of the `INCLUDE` payload. In fact, a plain index on `customer_id` alone can also qualify for `Index Only Scan` on Query C when conditions hold.

**Conclusion:** `INCLUDE` is not required for `Index Only Scan`. It is a tool to **expand the set of columns readable from an index** without turning them into B-tree keys.

### 4.1. “Covering” Involves More Than the SELECT List

When checking whether an index covers a query, inspect:

- Columns in `SELECT`.
- Columns used in `WHERE`, join conditions, or evaluated expressions.
- Columns in `ORDER BY`, `GROUP BY`, and related expressions.
- Columns needed by any operator/function to compute output.
- Any table columns the executor must read at that stage.

Checking only the `SELECT` list before adding `INCLUDE` is not enough. For example, selecting only `total_amount` with `WHERE status = 'PAID'` still needs `status` to filter rows, unless a partial index predicate proves it by other means.

## 5. INCLUDE Does Not Participate in B-tree Ordering or Search Bounds

Suppose an index is:

```sql
CREATE INDEX idx_customer_time
ON orders (customer_id, ordered_at DESC)
INCLUDE (status, total_amount);
```

### 5.1. Favorable Search Case

```sql
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
```

With leading key `customer_id` followed by `ordered_at`, PostgreSQL can use both conditions to narrow the index scan range.

### 5.2. When status Is Only in INCLUDE

```sql
WHERE status = 'PAID'
```

When `status` is merely an `INCLUDE` column, it **builds no B-tree key structure by status**. PostgreSQL can read `status` from the payload to filter during an `Index Only Scan` if the plan allows, yet it cannot jump directly to a `'PAID'` B-tree slice as a leading key.

Never confuse:

- **Value is present in the index** ⇒ can avoid fetching that value from the heap.
- **Value is a positioned index key** ⇒ can narrow scan bounds or supply sort order.

Those are two distinct benefits.

### 5.3. ORDER BY on an INCLUDE Column

An index:

```sql
ON orders (customer_id, ordered_at)
INCLUDE (total_amount)
```

does not sort entries by `total_amount`. The query:

```sql
WHERE customer_id = 42
ORDER BY total_amount DESC
```

still requires a `Sort` or alternative plan. To get `total_amount` order directly from a B-tree, `total_amount` must be a **key column in the appropriate position**.

## 6. PostgreSQL Lab: Creating Tables and Sample Data

Examples below use an isolated `index_include_lab` schema meant strictly for a test database. Running `CREATE TABLE` and loading tens of thousands of rows uses real disk and time; never run casually in production.

### 6.1. Creating the Schema

```sql
CREATE SCHEMA IF NOT EXISTS index_include_lab;
```

### 6.2. Creating the Orders Table

```sql
CREATE TABLE index_include_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    region_code TEXT NOT NULL,
    customer_note TEXT
);
```

Here:

- `order_id` is the row identifier.
- `customer_id` filters orders per customer.
- `ordered_at` supports chronological display and sorting.
- `status` and `total_amount` are frequently displayed on screen without always driving searches.
- `region_code` is an additional filter dimension.
- `customer_note` simulates longer text—**do not put it in `INCLUDE` just because the column exists**.

### 6.3. Loading Synthetic Data

```sql
INSERT INTO index_include_lab.orders (
    customer_id,
    ordered_at,
    status,
    total_amount,
    region_code,
    customer_note
)
SELECT
    (g.n % 400) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + make_interval(mins => g.n),
    CASE
        WHEN (g.n / 13) % 10 < 7 THEN 'PAID'
        WHEN (g.n / 13) % 10 < 9 THEN 'PENDING'
        ELSE 'CANCELLED'
    END,
    (1000 + g.n % 9999)::numeric(12, 2),
    CASE WHEN g.n % 3 = 0 THEN 'S'
         WHEN g.n % 3 = 1 THEN 'N'
         ELSE 'C'
    END,
    repeat('Sample note. ', 10)
FROM generate_series(1, 80000) AS g(n);
```

This generates **80,000 rows** across 400 synthetic customers. Synthetic data lets you verify plans without touching real personal data.

`ordered_at` spans early January through late February 2026 (incrementing one minute per row). The status distribution simulates read/write patterns only and does not reflect real business metrics.

### 6.4. Initial Statistics

```sql
ANALYZE index_include_lab.orders;

SELECT
    COUNT(*) AS row_count,
    COUNT(DISTINCT customer_id) AS customers,
    MIN(ordered_at) AS first_order,
    MAX(ordered_at) AS last_order
FROM index_include_lab.orders;
```

After running the insert once cleanly, row count is 80,000 across 400 customers. If the table already held data from an earlier run, counts will differ; the lesson assumes a clean schema.

## 7. Core Query: 20 Most Recent Orders

Primary query:

```sql
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

This query has two performance requirements:

1. **Fast filtering:** locate orders for customer 42 after a timestamp cutoff.
2. **Early return:** prioritize newest orders and stop at 20 rows.

A well-aligned index places keys in filter and sort order:

```sql
CREATE INDEX idx_lab_orders_customer_recent_cover
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

### 7.1. Why Does customer_id Come First?

`customer_id = 42` is an equality predicate defining the logical slice of results. In a multi-column B-tree, this leading key lets the planner narrow directly to that customer's index slice.

### 7.2. Why Does ordered_at DESC Come Next?

Rows for the same customer are sorted newest-first in the index. Queries filtering a time range and taking the newest entries exploit this ordering directly—ideal for `ORDER BY ordered_at DESC LIMIT 20`.

### 7.3. Why Is order_id DESC a Key Column?

Two orders can share the same `ordered_at`. Including `order_id DESC` makes output **deterministic** and matches `ORDER BY ordered_at DESC, order_id DESC`.

In the sample table, `order_id` is unique. Putting `order_id` in `INCLUDE` instead of keys would leave ties unsorted within identical timestamps, forcing extra sorting.

### 7.4. Why Are status and total_amount in INCLUDE?

Both columns appear in `SELECT` without driving search bounds or sort order in this query. Putting them in `INCLUDE` provides output data directly **without widening B-tree comparison keys unnecessarily**.

## 8. Index Scan vs. Index Only Scan in EXPLAIN

After creating the index, inspect the plan:

```sql
EXPLAIN
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

A plan you **might** see (illustrative only, not guaranteed output):

```text
Limit
  -> Index Only Scan using idx_lab_orders_customer_recent_cover
       on index_include_lab.orders
       Index Cond: (customer_id = 42 AND ordered_at >= ...)
```

Other valid plans include `Index Scan`, `Bitmap Heap Scan`, or `Seq Scan + Sort`. The planner weighs:

- Table and column statistics.
- Estimated returned rows and selectivity.
- Presence of `LIMIT`.
- Page access cost, caching, and random I/O.
- Fraction of heap pages marked all-visible.
- Index width and B-tree traversal cost.
- Planner configuration and PostgreSQL version.

**Never treat `CREATE INDEX` as proof the planner is forced to pick that index.**

### 8.1. Measuring Actual Execution

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND ordered_at >= TIMESTAMPTZ '2026-01-10 00:00:00+00'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`ANALYZE` here **actually executes the `SELECT` to measure**, unlike plain `EXPLAIN`. `BUFFERS` adds page hit/read/write counts for the query.

When you see:

```text
Index Only Scan ...
  Index Cond: (...)
  Heap Fetches: 0
```

during that run, the executor needed zero heap fetches for visibility checks on the read entries. That is an excellent sign, **yet not a permanent contract**: after `INSERT`/`UPDATE`/`DELETE` or under different snapshots/VM states, `Heap Fetches` can rise.

### 8.2. Index Only Scan with Non-Zero Heap Fetches

Another illustrative plan:

```text
Index Only Scan using idx_lab_orders_customer_recent_cover ...
  Index Cond: (customer_id = 42)
  Heap Fetches: 19
```

This **does not contradict the name `Index Only Scan`**. The index supplies the requested column values, yet PostgreSQL still visits the heap to verify tuple visibility on entries pointing to pages not yet marked all-visible.

### 8.3. Index Cond vs. Filter

In `EXPLAIN`, distinguish:

- **`Index Cond`:** predicates used by the index access method to bound or test entries during index traversal.
- **`Filter`:** predicates evaluated at the node after reading candidate entries/tuples; can scan many entries before discarding non-matches.

When a column sits only in `INCLUDE`, an `Index Only Scan` can read it from the payload to filter rows, yet **having it in the index never makes it a B-tree search key**.

## 9. Visibility Map: What Governs Heap Fetches

To truly understand `Index Only Scan`, you must understand the **visibility map (VM)**.

PostgreSQL uses MVCC. A single heap page can contain:

- Currently live, visible row versions.
- Old tuple versions from `UPDATE`/`DELETE`.
- Uncommitted tuples from in-flight transactions.
- Data visible to some snapshots and invisible to others.

An index entry alone lacks sufficient metadata to prove a tuple is visible to every transaction. PostgreSQL must verify visibility.

### 9.1. The all-visible Bit

The visibility map tracks state per **heap page**. When a page has its **all-visible** bit set, PostgreSQL knows every tuple on that page is **visible to all active and future transactions** under MVCC rules usable by `Index Only Scan`.

When an index entry points to an all-visible page:

```text
Index entry -> check visibility map -> all-visible
            -> return values from index
            -> skip reading heap page for visibility check
```

If the page is **not all-visible**:

```text
Index entry -> check visibility map -> not all-visible
            -> visit heap to check tuple visibility
            -> return or discard per snapshot
```

The visibility map is tiny compared to the heap and usually stays cached in memory, saving substantial I/O when the all-visible ratio is high.

### 9.2. VM all-visible Differs from all-frozen

PostgreSQL also tracks freezing state to manage transaction ID wraparound. For this lesson, the focus is **all-visible** because it governs whether `Index Only Scan` skips heap visibility checks on that page.

Do not conflate:

- **all-visible** bit: allows skipping heap visibility fetches.
- **all-frozen** state: relates to transaction ID freezing/wraparound.

A page can qualify as all-visible without necessarily meeting freezing goals in all contexts.

## 10. VACUUM and Covering Indexes: Why Rarely Modified Data Benefits More

The visibility map is typically updated by **`VACUUM`** once PostgreSQL confirms a page meets all-visible conditions. After bulk `INSERT`s or `UPDATE`s, newly written or modified pages lack the all-visible bit.

That explains why a covering index on a **read-mostly table or settled append-only data after `VACUUM`** avoids far more heap fetches than a table whose rows are constantly `UPDATE`d.

### 10.1. Before/After VACUUM Experiment

After the bulk `INSERT` and `CREATE INDEX` above, run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Note `Heap Fetches` if the plan is `Index Only Scan`.

Next, execute **outside a transaction block**:

```sql
VACUUM (ANALYZE) index_include_lab.orders;
```

Then re-run `EXPLAIN (ANALYZE, BUFFERS)` on the exact same `SELECT`.

If the relevant heap pages are now marked all-visible and the planner picks `Index Only Scan`, `Heap Fetches` should drop sharply—often to `0`.

### 10.2. VACUUM Does Not Guarantee Heap Fetches = 0

Results depend on:

- Whether old open transactions/snapshots prevent pages from becoming all-visible.
- Whether concurrent `INSERT`/`UPDATE`/`DELETE` statements arrive.
- Tuple state and `VACUUM` timing.
- Table layout, workload, and chosen execution plan.

Never claim running `VACUUM` once guarantees every query becomes `Index Only Scan` or marks every page all-visible.

### 10.3. Never Run VACUUM Before Every Query

PostgreSQL runs **autovacuum** to clean dead tuples and maintain MVCC/visibility per server settings. Never run `VACUUM` before `SELECT`s to “force index-only scans”; maintenance overhead easily outweighs read savings.

In production, inspect autovacuum pacing, long transactions, write rates, and all-visible ratios before adjusting maintenance settings.

## 11. After an UPDATE, Index-Only Scans May Hit the Heap More

Let us update some orders:

```sql
UPDATE index_include_lab.orders
SET customer_note = 'Changed after initial load'
WHERE customer_id = 42;
```

Immediately after `UPDATE`, modified heap pages lose their all-visible status. A query using the covering index for customer 42 will see **`Heap Fetches` rise**, even though all `SELECT`ed columns still reside in the index.

### 11.1. Modifying Only an Unindexed Column

`customer_note` is not in the covering index. An `UPDATE` modifying only `customer_note` **can qualify for a HOT update** if other conditions hold—such as free space on the page and no index referencing the modified column.

**HOT (Heap-Only Tuple)** avoids creating new index entries when eligible. Yet HOT **does not keep the page all-visible**: tuple modification still clears the visibility-map all-visible bit under MVCC.

### 11.2. Modifying an INCLUDE Column Can Break HOT

Example:

```sql
UPDATE index_include_lab.orders
SET total_amount = total_amount + 1
WHERE order_id = 100;
```

Because `total_amount` is stored in the payload of `idx_lab_orders_customer_recent_cover`, changing it forces PostgreSQL to update that index; it **cannot take the HOT update path because an indexed attribute changed**.

This is a **major cost of `INCLUDE`**. Even a non-key column forces index maintenance whenever its value changes.

### 11.3. Practical Trade-Offs

| Workload Type | Potential Benefit of INCLUDE | Risk |
| --- | --- | --- |
| Read-heavy table, rare `UPDATE`s | High; pages stay all-visible easily | Extra index disk footprint |
| Append-only table once settled | Strong for historical queries | Brand-new tail pages may not be all-visible yet |
| Constantly updated status table | Limited gains | Visibility map resets frequently; index maintenance |
| Frequently modified `INCLUDE` column | Saves heap reads for some queries | Fewer HOT updates; higher WAL and bloat |
| Very wide payload column | Unlikely worthwhile | Huge index tuples or tuple-size limit errors |

Therefore, **`INCLUDE` fits narrow, frequently read, rarely updated output columns**—not blindly stuffing every `SELECT` column into indexes.

## 12. Comparing Three Index Designs

Consider a query:

```sql
SELECT ordered_at, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC
LIMIT 20;
```

Three options:

**A. Index only on customer_id:**

```sql
CREATE INDEX idx_choice_a
ON index_include_lab.orders (customer_id);
```

Filters the customer quickly, yet lacks `ordered_at` and `total_amount`. Queries must read the heap and sort.

**B. Full composite key:**

```sql
CREATE INDEX idx_choice_b
ON index_include_lab.orders
    (customer_id, ordered_at DESC, total_amount);
```

Every column is a key, so `total_amount` enters B-tree ordering even though the query never searches or sorts by it.

**C. Composite key + INCLUDE:**

```sql
CREATE INDEX idx_choice_c
ON index_include_lab.orders
    (customer_id, ordered_at DESC)
INCLUDE (total_amount);
```

`total_amount` is stored as payload, satisfying retrieval without acting as a search key.

### 12.1. Semantic Comparison Table

| Design | Filters `customer_id` | Ordered by `ordered_at` | `total_amount` stored in index | `total_amount` is a key |
| --- | --- | --- | --- | --- |
| A | Yes | No secondary key order | No | No |
| B | Yes | Yes | Yes | Yes |
| C | Yes | Yes | Yes | **No** |

**Operational note:** these three `CREATE INDEX` statements illustrate design alternatives. Never keep all three on a production table when they overlap without distinct value; every index adds storage and write overhead.

### 12.2. Wide Keys vs. B-tree Internal Structure

`INCLUDE` payloads are not part of B-tree ordering keys. PostgreSQL omits unnecessary non-key columns from upper internal B-tree pages, keeping upper tree levels leaner than making every column a key.

However, **leaf entries still store the `INCLUDE` payload**, so total index size still grows. Never treat `INCLUDE` as “virtually free.”

## 13. UNIQUE INDEX ... INCLUDE: Uniqueness Applies Only to Key Columns

This is a frequent point of confusion:

```sql
CREATE UNIQUE INDEX idx_unique_demo
ON some_table (tenant_id, external_order_id)
INCLUDE (total_amount);
```

This index means:

> Within the same `tenant_id`, each `external_order_id` can appear at most once under uniqueness rules.

It does **not** require `total_amount` to be distinct.

### 13.1. Runnable Example

```sql
CREATE TABLE index_include_lab.external_orders (
    tenant_id INTEGER NOT NULL,
    external_order_id TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    source TEXT NOT NULL
);

CREATE UNIQUE INDEX idx_lab_external_orders_unique_cover
ON index_include_lab.external_orders
    (tenant_id, external_order_id)
INCLUDE (total_amount);

INSERT INTO index_include_lab.external_orders
    (tenant_id, external_order_id, total_amount, source)
VALUES
    (1, 'A-001', 100000, 'web'),
    (1, 'A-002', 100000, 'app'),
    (2, 'A-001', 100000, 'web');
```

All three rows are valid:

- Tenant 1 has two different order IDs sharing the same `total_amount`.
- Tenant 2 can reuse `'A-001'` because `tenant_id` differs.

However, the statement below **violates the unique key**, regardless of differing included amounts:

```sql
-- Error illustration only; no need to execute:
-- INSERT INTO index_include_lab.external_orders
--     (tenant_id, external_order_id, total_amount, source)
-- VALUES (1, 'A-001', 999999, 'other');
```

### 13.2. Why Is INCLUDE Useful on Unique Indexes?

Applications often look up an order by `(tenant_id, external_order_id)` and immediately need `total_amount`:

```sql
SELECT total_amount
FROM index_include_lab.external_orders
WHERE tenant_id = 1
  AND external_order_id = 'A-001';
```

The unique key locates the exact row, while included `total_amount` lets the query read it straight from the index when visibility allows.

Yet if you also select `source` which is absent from the index, this index no longer covers the query.

### 13.3. INCLUDE Does Not Expand the Unique Constraint

These two declarations mean completely different things:

```sql
UNIQUE (tenant_id, external_order_id)
INCLUDE (total_amount)
```

versus:

```sql
UNIQUE (tenant_id, external_order_id, total_amount)
```

In the first, `total_amount` is merely payload. In the second, it belongs to the uniqueness key tuple. Never use `INCLUDE` if business rules genuinely require the **three-column combination** to be unique.

## 14. Partial Covering Index: Storing Only a Subset of the Table

Suppose a dashboard shows only **paid orders**. A partial index can limit the number of entries:

~~~sql
CREATE INDEX idx_lab_paid_orders_cover
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount)
WHERE status = 'PAID';
~~~

With query:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

the planner can leverage:

- **Predicate** `status = 'PAID'` determining that only PAID rows are stored in the partial index.
- **Keys** identifying the customer and ordering.
- **INCLUDE total_amount** returning the monetary amount.

Because `status` here is the defining condition of the partial index rather than an output column selected by the query, the index can cover the values that need to be returned without storing `status` in `INCLUDE` in this example.

### 14.1. Partial Index Is Used Only When the Planner Can Prove the Predicate

Query:

```sql
WHERE customer_id = 42
  AND status = 'PAID'
```

has a condition clearly matching the predicate.

However, if the query is:

```sql
WHERE customer_id = 42
  AND status = $1
```

inside a prepared statement or generic plan, PostgreSQL **cannot necessarily prove** that parameter `$1` will always equal `'PAID'`, so you cannot assume the partial index will definitely be chosen. Index usage depends on how the plan is generated and the conditions known at planning time.

That is why you must benchmark the exact query shape sent by the application, including parameter binding.

### 14.2. Not Every Status Needs a Partial Index

Creating a separate index for PAID, PENDING, and CANCELLED can multiply write and maintenance costs several times over. Only create one when the workload truly needs it and the selectivity/predicate fit well.

## 15. INCLUDE with Filter Conditions on Payload

Consider the primary index:

```sql
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount)
```

And query:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`status` is in the payload, so it can be used to **filter results during an Index Only Scan**, yet it is not part of the B-tree key structure to directly narrow the scan range by status.

If most of the customer's orders are not PAID, the executor may have to examine many index entries to find 20 PAID orders. In that situation, alternative designs should be considered:

**Option A – put status in the key:**

```sql
CREATE INDEX idx_lab_customer_status_time
ON index_include_lab.orders
    (customer_id, status, ordered_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Suitable if queries frequently filter `customer_id = ? AND status = ?` and then `ORDER BY` time.

**Option B – partial index for PAID:**

```sql
CREATE INDEX idx_lab_paid_customer_time
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount)
WHERE status = 'PAID';
```

Suitable if the workload primarily accesses the PAID status and the predicate is recognized by the planner.

**Option C – keep status as INCLUDE:**

Suitable when you need to retrieve `status` for display, yet most queries **do not filter by status**, or the status condition is not selective enough to justify changing key order or adding another index.

### 15.1. No Single Key Order Fits Every Query

An index on:

```sql
(customer_id, status, ordered_at)
```

does not necessarily satisfy `ORDER BY ordered_at` for **all statuses of a customer** without extra processing, because entries in the index are grouped by `status` before `ordered_at`.

Conversely, the index:

```sql
(customer_id, ordered_at)
INCLUDE (status)
```

favors fetching all orders of a customer sorted chronologically, yet does not narrow the search directly by `status`.

Design must start from **important queries and real data distribution**, not merely the list of columns appearing in SQL.

## 16. Index Only Scan Is Not Bitmap Heap Scan

PostgreSQL has multiple index access methods/paths:

| Plan node | Primary read path | When can it make sense? |
| --- | --- | --- |
| `Seq Scan` | Scans heap in physical order | Many matching rows, small table, index provides no benefit |
| `Index Scan` | Traverses index, reads heap for needed rows | Selective filter, `ORDER BY/LIMIT` |
| `Bitmap Index Scan + Bitmap Heap Scan` | Collects row locations from index into a bitmap, reads heap by block | Many rows needed, combining multiple conditions/indexes |
| `Index Only Scan` | Traverses index, can skip heap when VM allows | Needed values are all in the index; many all-visible pages |

`Bitmap Heap Scan` has “Heap” in its name because it reads the heap according to a bitmap of matching blocks/rows. It does not turn into an `Index Only Scan` simply because the index has `INCLUDE`.

A query with a covering index can still choose `Bitmap Heap Scan` if the planner estimates its cost as favorable, or when other access conditions apply.

### 16.1. Bitmaps Can Combine Indexes

PostgreSQL can use `BitmapAnd` or `BitmapOr` to combine conditions from multiple indexes. This is a **different** technique from storing payload columns for index-only reads.

If a query needs a large number of rows and several independent filter conditions, a design relying on bitmap scans may make more sense than trying to build an overly wide covering index.

### 16.2. Do Not Assume Index Only Scan Is Always Fastest

An index-only plan can be slower than an index scan in some cases because:

- An index with overly wide `INCLUDE` columns requires scanning more pages.
- The visibility map is not yet all-visible, forcing many heap fetches.
- Planner row-count estimates diverge from reality.
- Caching and storage subsystems produce different costs than expected.
- The query must scan a great many index entries to filter on payload columns.

What needs optimizing is **overall workload latency, throughput, and resource usage**, not forcing a specific node name to appear in `EXPLAIN`.

## 17. Reading EXPLAIN (ANALYZE, BUFFERS) Carefully

An illustrative output:

```text
Limit  (actual time=... rows=20 loops=1)
  Buffers: shared hit=...
  ->  Index Only Scan using idx_lab_orders_customer_recent_cover
        on orders
        Index Cond: (customer_id = 42)
        Heap Fetches: 0
        Buffers: shared hit=...
Planning Time: ...
Execution Time: ...
```

Reading line by line:

### 17.1. actual rows and loops

- `rows=20` on `Limit` indicates the query actually returned 20 rows.
- `loops=1` is the number of times the node executed in this illustrative plan.
- If an inner node inside a nested loop executes many times, total cost can be high even if each iteration returns few rows.

### 17.2. Index Cond

`Index Cond` shows the predicates used by the index scan. Do not infer that a condition on an included column is a search key merely because that column resides in the index.

### 17.3. Heap Fetches

This metric shows how many heap fetches the `Index Only Scan` still had to perform to check visibility. **0** is ideal for read workloads; **non-zero** calls for examining MVCC/VM state and update frequency.

### 17.4. Buffers

`Buffers: shared hit` indicates accesses to blocks already in shared buffers; `shared read` indicates blocks read from the storage layer into shared buffers in PostgreSQL's accounting.

Do not equate every `shared read` with a slow physical disk read, because the OS also maintains a page cache. Nevertheless, these metrics remain useful for comparing I/O trends across plans.

### 17.5. Planning Time and Execution Time

A complex index can alter both planning time and execution time. In benchmarks, measure multiple runs, test warm/cold caches, and compare parameter distributions.

Do not draw conclusions from a single run on an 80,000-row table with synthetic data.

## 18. Can You Force the Planner to Observe Index Only Scan?

In a **lab** environment, you can temporarily restrict certain scan strategies to observe an index's capabilities. For example:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;
SET LOCAL enable_bitmapscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    ordered_at,
    status,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;

ROLLBACK;
```

The purpose is **strictly experimental**: to see alternative plans when the planner is constrained. Never leave `enable_seqscan=off` on permanently as a “performance fix.”

**Two caveats:**

1. Even when sequential/bitmap scans are disabled, PostgreSQL still chooses among valid paths based on cost; `enable_*` flags do not turn a non-covering index into a covering index.
2. A forced plan may be slower than the default plan. Restore settings after measuring and rely on real measurements to decide index design.

## 19. Checking Index Size

An index with `INCLUDE` is usually larger than a key-only index for the same row count and payload width.

### 19.1. Viewing Total Table and Index Size

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('index_include_lab.orders')
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('index_include_lab.orders')
    ) AS indexes_size,
    pg_size_pretty(
        pg_total_relation_size('index_include_lab.orders')
    ) AS total_size;
```

`pg_relation_size` on a table name as above typically reflects the main fork of the heap; `pg_indexes_size` is the total size of the table's indexes; `pg_total_relation_size` includes the table and associated structures such as indexes and TOAST.

### 19.2. Viewing Each Index

```sql
SELECT
    indexname,
    pg_size_pretty(
        pg_relation_size(
            (format('%I.%I', schemaname, indexname))::regclass
        )
    ) AS index_size
FROM pg_indexes
WHERE schemaname = 'index_include_lab'
  AND tablename = 'orders'
ORDER BY indexname;
```

When experimenting with multiple lab indexes, record byte counts along with row counts/widths to see how `INCLUDE` affects storage.

### 19.3. Before/After Comparison Without Leaving Overlapping Indexes Long-Term

To benchmark:

1. Measure the query with only the basic key index.
2. Create or replace it with the `INCLUDE` index.
3. Run `VACUUM`/`ANALYZE`, and measure multiple times under a similar workload.
4. Record execution time, buffers, heap fetches, and index size.
5. Account for added `INSERT`/`UPDATE` write overhead and disk space.
6. Keep only indexes delivering real net benefit.

Never assume “adding `INCLUDE`” is free just because one `SELECT` sped up.

## 20. Overly Wide INCLUDE Payload: Risk of Index Tuple Size Errors

B-tree indexes enforce an entry-size limit tied to page size and storage layout. If you `INCLUDE` a very large `TEXT`/`JSONB` column:

```sql
-- DO NOT apply mechanically if customer_note can be very long.
-- CREATE INDEX idx_bad_cover
-- ON index_include_lab.orders (customer_id, ordered_at)
-- INCLUDE (customer_note);
```

then the following can happen:

- Index bloat increases significantly.
- More pages must be read for the same number of rows.
- `INSERT`/`UPDATE` consumes more WAL, I/O, and CPU.
- Index creation or inserting new rows **fails because an index tuple is too large**.

**TOAST does not make including large text free.** Index entries must still obey the access method's size limits. A very long value should not be stored as payload just to save an occasional heap fetch.

### 20.1. Choosing Payload Columns

Columns commonly worth considering:

- Short status codes.
- Moderately sized `NUMERIC` amounts.
- Foreign key IDs.
- Frequently returned timestamps or flags.

Columns requiring careful scrutiny:

- Long descriptive text.
- Large JSON payloads.
- Large binary/blob data.
- Columns updated very frequently.
- Columns appearing only in a rarely run report.

## 21. B-tree Deduplication and INCLUDE

PostgreSQL B-trees feature a **deduplication** optimization when many duplicate key values exist: tuples sharing the same key can be grouped into posting lists to shrink index size.

For **B-tree indexes with non-key `INCLUDE` columns**, PostgreSQL **does not apply B-tree deduplication** to that index. This is an often overlooked trade-off.

For example:

```sql
CREATE INDEX idx_status_only
ON index_include_lab.orders (status);
```

versus:

```sql
CREATE INDEX idx_status_with_payload
ON index_include_lab.orders (status)
INCLUDE (total_amount);
```

When many rows share the same `status`, the first index can benefit from duplicate-key optimizations (where conditions and version allow); an index with `INCLUDE` cannot use B-tree deduplication in that manner.

Do not assume an index with `INCLUDE` will always grow by a fixed ratio, yet **losing deduplication compression** is a solid reason to check carefully when keys have low selectivity.

## 22. INCLUDE and HOT UPDATE

HOT update is an important PostgreSQL optimization when updating a row **without needing to modify index entries** under applicable rules and when sufficient free space remains on the heap page.

### 22.1. Before Including a Frequently Updated Column

Suppose `status` changes frequently:

```sql
UPDATE index_include_lab.orders
SET status = 'PAID'
WHERE order_id = 100
  AND status = 'PENDING';
```

If `status` appears in an index as either a **key or `INCLUDE` column**, changing its value can make the `UPDATE` **ineligible for HOT**. PostgreSQL must update the index to store the new payload value.

Impacts can include:

- More index entries and index pages written.
- Increased WAL volume.
- Lower HOT update ratio.
- More dead tuples and `VACUUM` work.
- Higher page/index contention under heavy write load.

### 22.2. Measuring HOT Updates

You can inspect statistics:

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'index_include_lab'
  AND relname = 'orders';
```

These are cumulative counters with update lag; do not treat them as exact proof for a single just-executed statement without accounting for stats resets and concurrent workload.

### 22.3. HOT and Index Only Scan Involve Trade-Offs

A wide index helps some `SELECT`s read fewer heap pages, yet placing frequently updated columns into `INCLUDE` can make `UPDATE`s costlier. Furthermore, `UPDATE`s clear the all-visible bit on affected heap pages, forcing subsequent index-only queries to perform additional heap fetches.

**Measure both reads and writes**, not only the `SELECT` currently being tuned.

## 23. INCLUDE Across Multiple Indexes Increases Write Cost

Suppose a table has:

```text
PRIMARY KEY(order_id)
INDEX(customer_id, ordered_at) INCLUDE(status, total_amount)
INDEX(status, ordered_at) INCLUDE(total_amount)
INDEX(region_code, ordered_at) INCLUDE(total_amount)
```

A single `UPDATE` to `total_amount` may have to maintain **multiple indexes** carrying it. On a write-heavy table, the cumulative overhead becomes substantial.

Therefore, before adding a new covering index:

1. List existing indexes.
2. Identify which query is genuinely slow and its execution frequency.
3. Check whether an existing index nearly covers it already.
4. Add only necessary payload columns—never dump the whole `SELECT` list unconditionally.
5. Measure index size, `UPDATE` latency, WAL, and autovacuum impact.
6. Check whether a new design can replace an older index.

### 23.1. Inspecting Existing Indexes

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'index_include_lab'
  AND tablename = 'orders'
ORDER BY indexname;
```

In production, never drop an index solely because its name looks redundant: it may back a unique/constraint, foreign key workload, another `ORDER BY`, or a query appearing infrequently in logs.

## 24. INCLUDE Is No Substitute for Proper Projection

Even with a covering index, the application should still select only the columns it actually needs:

```sql
-- Better for order listings:
SELECT order_id, ordered_at, status, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

instead of:

```sql
-- May force reading extra wide data from the heap:
SELECT *
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

`SELECT *` pulls `customer_note` and `region_code`, which are absent from the main index, so that index no longer covers the full output.

Do not `INCLUDE` every table column just to “fix `SELECT *`”; doing so can produce an index nearly as wide as or wider than the core table data, at unjustifiable maintenance cost.

## 25. Multi-Tenant Indexing and Data Scoping

In multi-tenant systems, queries must filter by the proper tenant:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM tenant_orders
WHERE tenant_id = 8
  AND customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

An appropriate index might be:

```sql
CREATE INDEX idx_tenant_orders_recent_cover
ON tenant_orders
    (tenant_id, customer_id, ordered_at DESC, order_id DESC)
INCLUDE (total_amount);
```

This is **illustrative DDL**, assuming a `tenant_orders` table exists.

### 25.1. Why Is tenant_id a Key?

The predicate `tenant_id = 8` scopes the allowed slice of data. When queries always filter by tenant, placing `tenant_id` among the leading keys usually narrows the index region scanned.

**However:** an index is not an authorization mechanism. If an application omits the tenant predicate or a role has broad `SELECT` privileges, having `tenant_id` in the index does not prevent data leaks. Apply proper authorization and Row-Level Security where appropriate.

### 25.2. Do Not Use INCLUDE to Mask Poor Key Design

If a query searches by:

```sql
WHERE tenant_id = ?
  AND customer_id = ?
```

but the index is only:

```sql
ON tenant_orders (customer_id)
INCLUDE (tenant_id, total_amount)
```

then `tenant_id` is merely payload and does not help the index search directly by tenant. In multi-tenant systems where `customer_id` collides across tenants, this can be much worse than a composite index keyed on both columns.

## 26. INCLUDE and Stable Pagination

A recent-orders listing typically uses:

```sql
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20
```

Including `order_id` in the key not only helps the planner use index ordering, but also makes **result ordering deterministic when orders share identical timestamps**.

### 26.1. OFFSET Can Be Costly

```sql
SELECT order_id, ordered_at, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
OFFSET 10000
LIMIT 20;
```

Even with a covering index, PostgreSQL still has to step through the skipped matching entries before reaching deep pages. `INCLUDE` does not eliminate the cost of large offsets.

### 26.2. Keyset Pagination

When tracking a “last seen” cursor with both timestamp and ID:

```sql
SELECT
    order_id,
    ordered_at,
    total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
  AND (ordered_at, order_id)
        < (TIMESTAMPTZ '2026-02-20 10:00:00+00', 78000)
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

This illustrates seeking to rows following the last-seen marker in descending order (assuming non-NULL key values and a matching sort pair). Index keys `(customer_id, ordered_at DESC, order_id DESC)` can advance far more efficiently than deep `OFFSET`.

**`INCLUDE` still serves only payload**: `total_amount` can be retrieved from the index, whereas the two pagination columns belong in keys to support ordering and seek conditions.

### 26.3. Pagination Does Not Automatically Guarantee a Fixed Snapshot

If new orders are inserted between two fetches, subsequent pages can shift according to newly committed data. Keyset pagination stabilizes ordering relative to sort keys, yet does not by itself enforce an immutable snapshot across separate requests.

If business logic requires locking an exact point-in-time report, define snapshot/transaction boundaries or historical data structures explicitly.

## 27. Index-Only Scans on Fresh Data vs. Historical Data

Distinguish two regions:

```text
Settled historical orders
    few UPDATEs, already VACUUMed
    -> many all-visible heap pages
    -> Index Only Scan has a chance at low Heap Fetches

Newly created / rapidly changing orders
    continuous INSERT/UPDATE
    -> many heap pages not yet all-visible
    -> Index Only Scan may still fetch heap pages
```

### 27.1. What If the Dashboard Always Queries the 20 Newest Orders?

The newest orders often reside in recently inserted or updated data regions. Hence, even with a complete covering index, `Heap Fetches` can be nontrivial.

That does not render the index useless:

- Keys still locate and return the 20 newest orders rapidly.
- `INCLUDE` still delivers output columns directly from the index.
- Yet **heap visibility checks** may still be required.

`INCLUDE`'s net benefit depends on how many heap fetches are actually avoided and how wide the payload is.

### 27.2. What If Reports Scan Last Month's Data?

A rarely updated historical partition or table region that has undergone `VACUUM` can have many all-visible pages and benefit substantially more from `Index Only Scan` when queries project only covered columns.

Therefore, benchmark **both recent-data queries and historical-data queries**, not just a single `customer_id`.

## 28. Index-Only Does Not Mean Zero Disk Reads

A common misconception:

> “Index Only Scan means zero disk reads, because it only reads the index.”

False. Indexes are stored on disk and cached in memory just like other relations. `Index Only Scan` can read **index pages** from storage, and visibility map pages must also be consulted when needed.

The actual optimization is **avoiding or reducing heap tuple fetches** for values already present in the index.

If an index is too wide or falls out of cache, it can generate heavy I/O. So check:

- `BUFFERS shared hit/read`.
- Index size.
- `Heap Fetches`.
- Actual rows and loops.
- Latency under concurrent load.

Do not treat `Heap Fetches = 0` as the whole performance story.

## 29. Index-Only Scans and MVCC Isolation

PostgreSQL must return rows **consistent with the statement/transaction snapshot**. The visibility map is an optimization allowing heap reads to be skipped when proven safe; it never bypasses MVCC rules.

### 29.1. READ COMMITTED

Each statement typically acquires a snapshot reflecting committed state at statement start. If a page is not yet all-visible, `Index Only Scan` may read the heap to check whether tuples are visible to that snapshot.

### 29.2. REPEATABLE READ

A transaction holds a stable snapshot across multiple statements, yet that does not automatically make all heap pages all-visible. Tuple versions not visible to every snapshot cannot simply be skipped without verification.

### 29.3. Long-Running Transactions and VACUUM

Old long-running transactions/snapshots can prevent `VACUUM` from reclaiming dead tuple versions and marking eligible pages all-visible, diminishing `Index Only Scan` effectiveness.

Never “optimize for index-only” by disabling or circumventing MVCC checks: PostgreSQL must preserve correctness before speed.

## 30. Different Access Methods Do Not Share Identical Index-Only Capabilities

B-tree is the most common access method for `INCLUDE + Index Only Scan` examples because it stores keys and can return column values directly from the index.

Do not overgeneralize:

> “Any index in PostgreSQL uses Index Only Scan whenever SELECT requests the exact columns.”

An access method must support reconstructing meaningful data from index entries:

- **B-tree:** supports index-only scans for eligible types and columns.
- **GiST / SP-GiST:** index-only capability depends on access method and operator class support, because some index representations are *lossy* or cannot reconstruct original values.
- **GIN:** generally does not support B-tree-style index-only scans because index entries store decomposed keys/elements rather than whole returnable values.
- **BRIN:** indexes summarize block ranges and do not replace fetching full tuples from the heap in this manner.

Likewise, syntax support for `INCLUDE` does not mean every access method or operator class yields the same benefit. With non-B-tree indexes, verify **PostgreSQL version, operator class, stored representation, and actual `EXPLAIN` output**.

## 31. Expression Indexes and INCLUDE

A common query:

```sql
SELECT
    customer_id,
    lower(region_code) AS normalized_region
FROM index_include_lab.orders
WHERE lower(region_code) = 'n';
```

If queries routinely search by the **expression `lower(region_code)`**, an expression index may help:

```sql
CREATE INDEX idx_lab_region_lower
ON index_include_lab.orders
    ((lower(region_code)), customer_id);
```

This indexes a **computed expression value**. PostgreSQL has specific rules and capabilities for matching expression indexes in `Index Only Scan` depending on how the query and planner inspect projected columns.

A design adding `INCLUDE` on base columns can serve a different query:

```sql
CREATE INDEX idx_lab_region_lower_cover
ON index_include_lab.orders
    ((lower(region_code)), customer_id)
INCLUDE (region_code);
```

Do not assume both indexes perform identically or always lead to index-only plans. **Verify with `EXPLAIN` on real queries.**

### 31.1. Expressions Are Not Accepted Arbitrarily in INCLUDE

`INCLUDE` holds **columns** as payload, not arbitrary expressions like the key expression list:

```sql
-- NOT valid syntax for placing an expression in INCLUDE:
-- INCLUDE (lower(region_code))
```

If you need an expression as a search key, define an expression index using proper key syntax.

## 32. Designing Covering Indexes from Real Workloads

Do not start by asking “which columns exist in the table?”; start from **which queries need optimizing**.

Suppose you have three query groups:

**A. Customer's 20 most recent orders:**

```sql
SELECT order_id, ordered_at, status, total_amount
FROM index_include_lab.orders
WHERE customer_id = $1
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

**B. Paid order count per customer:**

```sql
SELECT COUNT(*)
FROM index_include_lab.orders
WHERE customer_id = $1
  AND status = 'PAID';
```

**C. Regional revenue total report:**

```sql
SELECT region_code, SUM(total_amount)
FROM index_include_lab.orders
WHERE ordered_at >= $1
  AND ordered_at < $2
GROUP BY region_code;
```

An index keyed on `(customer_id, ordered_at DESC, order_id DESC) INCLUDE(status, total_amount)` fits query A closely, yet is not necessarily optimal for B or C:

- B adds a `status` filter and computes `COUNT`; depending on frequency, it may benefit more from `(customer_id, status)` or a partial index.
- C scans a time range and aggregates by region; leading with `customer_id` may not serve that access pattern well.

**One index need not serve every query optimally.** Sometimes two focused indexes outperform one ultra-wide index overall, subject to write cost and storage constraints.

### 32.1. Workload Analysis Checklist

Record:

1. Query frequency.
2. P50/P95/P99 latency and SLO targets.
3. Rows returned vs. rows scanned.
4. Equality, range, and join predicates.
5. `ORDER BY` and `LIMIT`.
6. Columns genuinely needed in output.
7. Heap all-visible ratio.
8. `INSERT`/`UPDATE`/`DELETE` rate.
9. Whether candidate payload columns are updated frequently.
10. Existing indexes and storage/WAL budgets.

Only then decide **key order and `INCLUDE` columns**.

## 33. Measuring SELECT Before and After Creating a Covering Index

A lab procedure:

### Step 1: Prepare Table and Data

Create the table and load 80,000 rows as in Section 6, then run `ANALYZE`.

### Step 2: Create a Key-Only Index

```sql
CREATE INDEX idx_lab_customer_recent_key_only
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC);
```

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, ordered_at, status, total_amount
FROM index_include_lab.orders
WHERE customer_id = 42
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

Record plan nodes, buffers, and timing.

### Step 3: Compare Against an Index with INCLUDE

```sql
CREATE INDEX idx_lab_customer_recent_with_payload
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

Because the lab may already hold a covering index from Section 7, note that **the planner can pick any eligible existing index**. For trustworthy comparisons, run under controlled index states (for example, resetting the test database or keeping only one design at a time) rather than assuming the newly named index was chosen solely because you created it.

### Step 4: VACUUM and Re-Measure

```sql
VACUUM (ANALYZE) index_include_lab.orders;
```

Re-run the `SELECT` and compare:

- `Index Scan` vs. `Index Only Scan`?
- How many `Heap Fetches`?
- How many `shared hit/read` buffers?
- Did sort cost change?
- Did overall execution time drop meaningfully?

### Step 5: Test UPDATE and Re-Measure

```sql
UPDATE index_include_lab.orders
SET total_amount = total_amount + 1
WHERE customer_id = 42;
```

Re-measure the plan and `Heap Fetches`. Also note how updating an included column affects HOT eligibility and index maintenance.

### Step 6: Record Total Cost

Check index size and update statistics. Gains are operationally worthwhile only when improvement on critical queries **justifies added storage and write costs**.

Never run `VACUUM FULL` or alter global planner settings just to make a demo look better.

## 34. Estimating Visibility Map Coverage via Catalog: Read with Care

PostgreSQL maintains statistics in `pg_class` to assist the planner. You can inspect those estimates:

```sql
SELECT
    relname,
    relpages,
    relallvisible,
    CASE
        WHEN relpages > 0
        THEN ROUND(relallvisible::numeric / relpages * 100, 2)
        ELSE NULL
    END AS estimated_all_visible_pct
FROM pg_class
WHERE oid = 'index_include_lab.orders'::regclass;
```

Meaning:

- `relpages`: planner statistic estimating total relation pages.
- `relallvisible`: planner statistic estimating heap pages marked all-visible.
- Their ratio can provide a **hint** regarding index-only potential.

**Do not mistake these figures for an exact, real-time bit-level snapshot of the visibility map at query instant.** They may lag behind recent mutations and must be interpreted as statistical estimates.

For deeper inspection, dedicated diagnostic tools/extensions exist if approved by administrators; this lesson assumes no such extensions are installed.

## 35. INCLUDE in PRIMARY KEY and UNIQUE Constraints

Modern PostgreSQL versions support included columns on indexes backing **`PRIMARY KEY`/`UNIQUE` constraints** with appropriate syntax:

```sql
CREATE TABLE index_include_lab.customer_preferences (
    customer_id INTEGER PRIMARY KEY,
    language_code TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

This supplementary table does not yet use `INCLUDE` in its primary key.

An illustrative constraint design:

```sql
CREATE TABLE index_include_lab.api_keys (
    tenant_id INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    last_used_at TIMESTAMPTZ,
    CONSTRAINT uq_api_key_name
        UNIQUE (tenant_id, key_name)
        INCLUDE (enabled, last_used_at)
);
```

The unique key is `(tenant_id, key_name)`. The two included columns **do not participate in uniqueness**, yet can serve a `SELECT` looking up a key and reading its state.

### 35.1. When Should You Avoid INCLUDE on a Constraint Index?

If `last_used_at` is updated on **every API request**, including it forces the backing unique index to update constantly. That can cause far heavier write amplification than the benefit of saving one heap fetch during key lookup.

This example is intentional: **valid syntax does not imply sound design**.

## 36. CREATE INDEX CONCURRENTLY and Deployment Impact

On active production tables with live traffic, building a large B-tree index normally can block writes. PostgreSQL supports:

```sql
CREATE INDEX CONCURRENTLY idx_orders_recent_online
ON index_include_lab.orders
    (customer_id, ordered_at DESC, order_id DESC)
INCLUDE (status, total_amount);
```

`CONCURRENTLY` reduces blocking of concurrent `INSERT`/`UPDATE`/`DELETE` statements compared to standard index creation. However:

- The build can run longer and consume substantial I/O, CPU, and WAL.
- It still waits for certain concurrent transactions across build phases.
- `CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block.
- If it fails, an `invalid` index may remain in catalogs requiring inspection and cleanup per runbook.
- Avoid deploying overlapping redundant indexes in the same migration without a rollout plan.

### 36.1. New Indexes Are Not Guaranteed Immediate Use

After creation, run `ANALYZE` if needed and measure real queries. Remember query plans depend on all-visible ratios and data statistics, not merely the index's presence in catalogs.

### 36.2. Dropping Indexes No Longer Needed

```sql
-- Lab example; run only after confirming the index is unnecessary:
-- DROP INDEX CONCURRENTLY index_include_lab.idx_orders_recent_online;
```

`DROP INDEX CONCURRENTLY` also carries transaction restrictions and execution prerequisites. In production, verify no constraints or other workloads depend on the index, and coordinate rollouts while applications may still rely on multiple plans.

## 37. When Should You NOT Use INCLUDE?

A decision checklist:

**Do not add `INCLUDE` merely because:**

- A query projects a column, yet runs very rarely.
- The table holds only a few hundred rows and `Seq Scan` is already fast.
- The query already has an efficient `Index Scan` with few cached heap fetches.
- Payload columns are wide enough to bloat the index or risk index tuple size limits.
- Columns change constantly, degrading HOT updates and raising write costs.
- Heavy write churn keeps many heap pages non-all-visible.
- The query still needs other non-indexed columns, forcing heap reads anyway.
- Search filters lack an appropriate key: `INCLUDE` cannot replace keys.
- `ORDER BY` targets an included column while expecting B-tree ordering.
- You merely want `EXPLAIN` to print “Index Only Scan” without real latency gains.

### 37.1. When Is INCLUDE Worth Testing?

`INCLUDE` is often worth evaluating when:

1. One or a few queries are **high-frequency and latency-sensitive**.
2. Appropriate key columns already satisfy filtering and sorting.
3. Heap reads occur **primarily to fetch a few small output columns**.
4. Candidate payload columns change infrequently.
5. Queried heap regions maintain a high all-visible ratio.
6. Added storage and write overhead stay within budget.
7. Benchmarks confirm real improvements in latency, buffers, and heap fetches.

Treat this as an **optimization hypothesis to measure**, not an unconditional rule.

## 38. Comparison Table of Easily Confused Properties

| Question | Accurate Answer |
| --- | --- |
| Is an index with `INCLUDE` a covering index for every query? | No; it covers a query only when it contains all needed data |
| Can a key-only index perform `Index Only Scan`? | Yes, if the query needs only indexed data and visibility allows |
| Are included columns used for B-tree ordering? | No |
| Do included columns participate in unique keys? | No |
| Can filtering on an included column avoid heap reads? | Possibly, when the plan and visibility allow |
| Is filtering on an included column a B-tree search key? | No |
| Does `Index Only Scan` always have `Heap Fetches = 0`? | No |
| Does non-zero `Heap Fetches` mean the index does not cover output? | Not necessarily; it may reflect VM/MVCC state |
| Can `VACUUM` help reduce heap fetches? | Yes, by marking eligible pages all-visible |
| Does `VACUUM` guarantee every page becomes all-visible? | No |
| Does updating an `INCLUDE` column affect HOT updates? | Yes, it can prevent HOT because indexed payload changes |
| Is `INCLUDE` on large columns free thanks to TOAST? | No |
| Does B-tree deduplication apply to indexes with `INCLUDE`? | No, for B-trees with non-key `INCLUDE` columns |
| Does adding `INCLUDE` force the planner to choose `Index Only Scan`? | No |
| Does `INCLUDE` eliminate heap access across all queries? | No |
| Should write overhead be monitored after adding `INCLUDE`? | Yes, especially on write-heavy tables |

## 39. Specific Design Pitfalls

### 39.1. Stuffing Every Column into INCLUDE

```sql
-- Bad idea if columns are wide and frequently updated:
-- CREATE INDEX idx_everything
-- ON orders(customer_id)
-- INCLUDE(status, total_amount, region_code, customer_note, ...);
```

Consequence: bloated indexes, wasted storage, index tuple size errors, higher WAL volume, and reduced HOT updates. Optimize **only actual required projections**.

### 39.2. Using INCLUDE Instead of Keys for ORDER BY

```sql
ON orders(customer_id)
INCLUDE(ordered_at)
```

does not support `ORDER BY ordered_at DESC` the way index keys do:

```sql
ON orders(customer_id, ordered_at DESC)
```

### 39.3. Using INCLUDE Instead of Keys for Selective WHERE Filters

```sql
ON orders(customer_id)
INCLUDE(status)
```

does not create the key-range lookup capability for `status='PAID'` provided by:

```sql
ON orders(customer_id, status)
```

### 39.4. Mistaking HEAP FETCHES for Table Row Count

`Heap Fetches` in an `Index Only Scan` node counts heap visibility checks executed for that node—it is **not the table's row count, not `COUNT(*)`**, and does not tell you how many physical disk bytes were read.

### 39.5. Running VACUUM FULL to “Enable Index-Only”

`VACUUM FULL` rewrites the table under a strong lock and is not the right tool to boost all-visible ratios. Start with proper autovacuum tuning, update workload hygiene, and targeted `VACUUM (ANALYZE)`; reserve `VACUUM FULL` for explicit storage reclamation cases.

## 40. PostgreSQL Hands-On Exercises

The exercises below build on the `index_include_lab` schema. For performance measurements, use a **test database** and repeat runs before drawing conclusions.

1. **Concepts:** Explain the difference between index keys, `INCLUDE` columns, and heap-only columns.
2. **Covering index:** For queries fetching `order_id, ordered_at, status, total_amount` by `customer_id`, design appropriate B-tree keys and `INCLUDE`.
3. **ORDER BY:** Why should `order_id` be in the key when sorting by `ordered_at DESC, order_id DESC`?
4. **Payload:** If queries neither filter nor sort by `total_amount`, why can `INCLUDE` be preferable to placing it at the end of keys?
5. **Uncovered:** Add `customer_note` to `SELECT`; why does the primary index no longer fully cover the query?
6. **Index-only without INCLUDE:** Write `SELECT COUNT(*) WHERE customer_id=42` and explain why a key-only index can still use `Index Only Scan`.
7. **Index Cond:** Create the primary index, run `EXPLAIN` with `customer_id=42` and an `ordered_at` range, and record `Index Cond` when present.
8. **Filter:** Add `status='PAID'` when `status` is only in `INCLUDE`. Explain the difference between payload filtering and B-tree key search.
9. **Keyed status:** Create `(customer_id,status,ordered_at DESC) INCLUDE(total_amount)` and compare efficiency on status-filtered queries.
10. **Sort:** Query `ORDER BY total_amount DESC` when `total_amount` is only in `INCLUDE`. Why might a `Sort` node still appear?
11. **VACUUM:** Compare `EXPLAIN (ANALYZE, BUFFERS)` before and after `VACUUM (ANALYZE)` on the lab table. How does `Heap Fetches` change?
12. **Visibility map:** Explain the role of the all-visible bit and why `Index Only Scan` may still hit the heap.
13. **MVCC:** Why cannot an index entry alone prove every tuple is visible to the current snapshot?
14. **Freshly INSERTed data:** Why are newly inserted pages not necessarily all-visible even when all output columns reside in the index?
15. **UPDATE unindexed column:** Update `customer_note` for customer 42 and re-measure heap fetches; why can a page lose all-visible status?
16. **UPDATE payload:** Update `total_amount` and explain the impact on HOT updates and index maintenance.
17. **Monitoring HOT:** Query `pg_stat_user_tables` for `n_tup_upd` and `n_tup_hot_upd`; why are these cumulative counters?
18. **Size:** Use `pg_relation_size` and `pg_indexes_size` to measure index size before and after adding `INCLUDE` payloads.
19. **Unique key:** Create unique index `(tenant_id,external_order_id) INCLUDE(total_amount)`. Which columns enforce uniqueness?
20. **Duplicate amount:** Insert two orders with different external IDs and identical amounts. Why does that not violate the unique index with `INCLUDE`?
21. **Partial index:** Create an index covering only `PAID` orders, keyed by `customer_id/ordered_at` and including `total_amount`. Write a matching query.
22. **Prepared statement:** Explain why `status=$1` may fail to match a partial index predicate in a generic plan.
23. **Index key order:** Compare `(customer_id, status, ordered_at)` vs. `(customer_id, ordered_at) INCLUDE(status)` for queries not filtering on `status`.
24. **B-tree dedup:** Why can an index with `INCLUDE` not leverage B-tree deduplication the way a key-only index can in suitable cases?
25. **Large columns:** Propose how to measure and decide whether `customer_note` should go into `INCLUDE`.
26. **Index tuple limit:** What can happen during index creation or `INSERT` if a `JSONB` payload column grows very large?
27. **Select star:** Compare `SELECT *` against a narrow projection and explain its impact on covering indexes.
28. **Bitmap:** Contrast `Bitmap Heap Scan` with `Index Only Scan` in terms of heap reads.
29. **Planner:** Why might PostgreSQL still pick `Seq Scan` on a small table even when a covering index exists?
30. **Buffers:** Explain `shared hit` and `shared read` in `EXPLAIN`, and why they do not map 1:1 to physical disk reads.
31. **LIMIT:** Add `LIMIT 20` to a newest-orders query; why do aligned index keys reduce examined rows?
32. **Pagination:** Compare deep `OFFSET` with keyset pagination on `(ordered_at,order_id)`; what does `INCLUDE` help with and what does it not help with?
33. **Multi-tenant:** Write an index with `tenant_id, customer_id, ordered_at` as keys; why should `tenant_id` not sit only in `INCLUDE` when queries always filter by tenant?
34. **RLS:** Explain why indexing `tenant_id` is no substitute for authorization/RLS.
35. **Read workload:** If historical tables rarely update and undergo regular `VACUUM`, what advantage can `INCLUDE` offer?
36. **Write workload:** If `status` changes constantly, why can including `status` make `UPDATE`s more expensive?
37. **Benchmark:** Design a before/after index benchmark capturing actual rows, `Heap Fetches`, `Buffers`, index size, and `UPDATE` latency.
38. **Live EXPLAIN caution:** Why be careful with `EXPLAIN (ANALYZE, BUFFERS)` on write statements or very heavy queries?
39. **CONCURRENTLY:** When building production indexes, why understand `CREATE INDEX CONCURRENTLY` caveats and invalid index states on failure?
40. **No blind optimization:** A query already runs in 2 ms with low heap fetches, yet `INCLUDE` adds 4 GB to index size; what metrics determine whether to keep or drop it?
41. **Designing for 3 queries:** Analyze queries A/B/C from Section 32 and propose indexes tailored to top queries without redundant overlap.
42. **Definition of done:** Write a checklist verifying an acceptable `INCLUDE` design: right keys, complete coverage, low heap fetches where appropriate, acceptable storage/write cost, and reliable benchmarks.

## 41. Review Checklist for an INCLUDE Proposal

When a teammate proposes:

```sql
CREATE INDEX idx_fast
ON big_table (customer_id)
INCLUDE (col_a, col_b, col_c);
```

ask:

1. **Which queries** will use this index? Do we have the real SQL and bind parameters?
2. Does **key order** align with equality/range predicates and `ORDER BY`?
3. Are all **payload columns** genuinely needed to cover those queries?
4. If queries filter or sort on a payload column, should it become a key column?
5. Will `SELECT *` or another column break index coverage?
6. Does the planner actually choose `Index Only Scan`? If not, why?
7. Is `Heap Fetches` low, and does the workload keep enough pages all-visible?
8. Are `INCLUDE` columns updated often enough to disrupt HOT updates?
9. Do payloads include large text/JSONB risking index tuple size limits?
10. How much extra index size, WAL, and write overhead will this add?
11. Can this replace or consolidate an existing overlapping index?
12. If partial, can real queries prove the predicate at planning time?
13. If unique, does everyone understand uniqueness applies only to key columns?
14. Was it benchmarked repeatedly against representative data and query rates?
15. Does production rollout account for concurrent build, duration, permissions, and rollback?

Only conclude “the new index is worth deploying” when read gains clearly outweigh total costs.

## 42. Summary

`INCLUDE`, covering indexes, and `Index Only Scan` are related yet **not synonymous**:

```text
1. INDEX KEY
   (customer_id, ordered_at DESC, order_id DESC)
   -> Searches B-tree ranges and provides matching sort order

2. INCLUDE PAYLOAD
   (status, total_amount)
   -> Stores additional output values
   -> Does not participate in key ordering or UNIQUE keys

3. COVERING INDEX
   -> Index containing all data needed by a query
   -> Coverage depends on the specific SQL statement

4. INDEX ONLY SCAN
   -> Planner chooses a plan reading values from the index
   -> Checks visibility map
   -> All-visible heap pages: can skip heap fetch
   -> Non-all-visible pages: must still check heap
```

Key principles:

- **Choose keys from `WHERE` and `ORDER BY`; choose `INCLUDE` for small, frequently read output columns.** Never use `INCLUDE` in place of search keys or sort keys.
- **Covering a query does not force the executor to choose `Index Only Scan`.** The planner decides using statistics, selectivity, and cost.
- **`Index Only Scan` does not guarantee `Heap Fetches = 0`.** MVCC still governs visibility, and the visibility map determines whether heap checks are needed per page.
- **`VACUUM` and update patterns strongly influence results.** Stable tables tend toward higher all-visible ratios; write-heavy tables may still incur significant heap fetches.
- **`INCLUDE` columns are not free.** They enlarge indexes, add write overhead, can inhibit HOT updates, disable B-tree deduplication, and hit tuple-size limits if payloads are too large.
- **`UNIQUE INDEX ... INCLUDE` enforces uniqueness solely on key columns.** Payload columns support reads without expanding uniqueness rules.
- **Measure both reads and writes using `EXPLAIN`, `Buffers`, `Heap Fetches`, index size, and workload metrics** rather than chasing a pretty node name in query plans.

Once you understand **keys for searching, payload for coverage, and the visibility map for MVCC**, you can design PostgreSQL covering indexes that deliver genuine value: cutting heap access on critical queries without overpaying in storage and write throughput.
