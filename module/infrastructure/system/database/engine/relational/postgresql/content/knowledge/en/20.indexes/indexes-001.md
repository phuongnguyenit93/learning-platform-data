# What Problems Indexes Solve and Their Write Costs in PostgreSQL

A PostgreSQL table with 100 rows usually poses little difficulty when searching for an order. But when the table has 100 million rows, the question “where is order `order_id = 12345`?” is completely different from “read all orders from this month.” If the database has to inspect every row sequentially to find a few needed rows, the query can end up reading a huge amount of irrelevant data.

An **index** is an auxiliary data structure that helps PostgreSQL **locate the exact subset of data to read**, or **read data in a useful order**, instead of always scanning the entire table. However, indexes are not free:

- When you `INSERT` a row, PostgreSQL may have to write additional entries into multiple indexes.
- When you `UPDATE` indexed columns, PostgreSQL may have to update the index structures in addition to creating a new row version under MVCC.
- When you `DELETE`, old index entries and tuple versions must be cleaned up according to the MVCC/VACUUM lifecycle.
- Indexes consume storage space, generate WAL, cause page writes, page splits, and increase cache demand and maintenance time.
- A poorly chosen index may **rarely be used by the planner**, yet still add extra work to every write operation.

This lesson focuses on two inseparable questions:

1. **What read problems does an index solve?** Key lookups, filtering a small subset, supporting JOIN, ORDER BY, LIMIT, unique constraints, or specialized predicates such as JSONB/geospatial.
2. **What write costs do we pay in return?** Index maintenance overhead, impact on HOT updates, WAL, bloat, VACUUM, locking, build/rebuild time, and system resources.

The goal is not to “create an index for every column that appears in WHERE,” but to **design a small set of indexes tailored to the workload**.

## 1. Intuitive Example: Looking Up a Term in a Book

Imagine a 1,000-page book.

- If you read the entire book from page 1 to find the word “MVCC,” you are doing the equivalent of a **sequential scan**.
- If the book has a back-of-the-book index pointing to “MVCC” on pages 230 and 415, you can jump to the locations much faster. That is a simple picture of an **index lookup**.
- If you want to read **the entire book**, consulting the index to jump to individual pages can take more effort than reading sequentially from start to finish.

This is why an index can speed up a query looking for **one row**, yet not necessarily help a query returning **80% of the table's rows**.

~~~mermaid
flowchart TD
    Q["PostgreSQL query"] --> P["Planner estimates row count and cost"]
    P --> S["Seq Scan: read many rows from the heap"]
    P --> I["Index Scan: look up keys, access matching rows"]
    P --> B["Bitmap Scan: collect row locations then read by block"]
    P --> O["Index Only Scan: can avoid many heap fetches"]
    S --> R["Return results"]
    I --> R
    B --> R
    O --> R
~~~

**An index is an option for the query planner**, not a guarantee that PostgreSQL will always use it whenever it exists.

## 2. How Do a Data Table and an Index Structure Differ?

In PostgreSQL, tables typically store row versions in a **heap**. A B-tree index, the most common type, stores entries organized by search keys along with pointers referencing tuple locations in the heap.

Example table:

~~~text
orders
------------------------------------------------------------------
order_id | customer_id | status  | created_at | total
------------------------------------------------------------------
1001     | 11          | pending | ...        | 120.00
1002     | 42          | paid    | ...        |  80.00
1003     | 42          | pending | ...        |  50.00
1004     | 17          | paid    | ...        | 200.00
~~~

If you create:

~~~sql
CREATE INDEX idx_orders_customer
ON orders(customer_id);
~~~

the B-tree structure can be illustrated conceptually as:

~~~text
Index on customer_id               Heap containing full rows

11 → [location of row 1001] ─────→ order 1001 ...
17 → [location of row 1004] ─────→ order 1004 ...
42 → [location of row 1002] ─────→ order 1002 ...
42 → [location of row 1003] ─────→ order 1003 ...
~~~

This is only a **conceptual diagram**; an actual B-tree has internal pages, leaf pages, duplicate key handling, and other storage optimizations.

### Does an Index Contain the Entire Row?

A typical index **does not replace the heap**. It stores the information needed for that index's access method. With a B-tree, a query may find an entry in the index and then have to read the heap to fetch other columns and check whether the tuple is visible to the current MVCC snapshot.

Sometimes PostgreSQL chooses an **Index Only Scan** if all required columns are already provided by the index and the visibility map allows skipping heap reads for many pages. However, index-only does not mean PostgreSQL skips visibility checks entirely.

### A Table Can Have Multiple Indexes

For example:

~~~sql
CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_created ON orders(created_at);
CREATE INDEX idx_orders_status ON orders(status);
~~~

These are three separate structures, each with its own storage footprint and maintenance cost. PostgreSQL does not automatically merge them into one all-purpose index; for each query, the planner considers using one index, combining bitmaps from multiple indexes, or skipping indexes altogether.

## 3. Read Problems That Indexes Can Solve

| Need | Example SQL | Typically Useful Index |
| --- | --- | --- |
| Find one row by key | `WHERE order_id = 12345` | B-tree on the primary key |
| Filter a specific customer | `WHERE customer_id = 42` | B-tree on `customer_id` |
| Narrow time-range query | `WHERE created_at >= ... AND created_at < ...` | B-tree on `created_at` |
| Get latest records | `WHERE customer_id = ? ORDER BY created_at DESC LIMIT 10` | Multi-column B-tree matching filter and sort order |
| Foreign key JOIN | `orders.customer_id = customers.customer_id` | Index on matching join column(s) |
| Enforce uniqueness | `UNIQUE(tenant_id, external_code)` | Unique B-tree automatically created by the constraint |
| Filter only a small subset | `WHERE status = 'failed'` when failed is rare | Appropriate partial index |
| Search inside JSONB | `details @> '{"tag":"urgent"}'::jsonb` | GIN with an appropriate operator class |
| Spatial queries | Distance/geometry via extension/type | GiST or another suitable index type |
| Very large data, physically correlated | Date range scan on an append-only table | BRIN can save significant space |

Not every `WHERE` clause can be served efficiently by an index. You must consider **operators**, data types, column order, selectivity, and actual data distribution.

## 4. Why Does PostgreSQL Sometimes Choose Seq Scan Even When an Index Exists?

Suppose a table has 1,000,000 rows.

- Query A needs **one** row by primary key.
- Query B needs **900,000** rows for aggregation.

Query A usually benefits from an index lookup because it avoids scanning most of the data. For Query B, using an index would require traversing many index entries and then accessing many heap pages, which can cost more than reading the table sequentially.

The planner weighs factors including:

1. **Selectivity:** the estimated fraction of rows matching the condition.
2. **Cardinality:** the number of rows returned and intermediate rows processed.
3. **I/O cost:** sequential reads versus heap accesses with random I/O patterns.
4. **Data correlation:** whether the physical order of rows on disk aligns with the index order.
5. **Index and heap page counts:** the index itself must also be read.
6. **Cache:** whether many pages are already in shared buffers or OS cache.
7. **ORDER BY, LIMIT, JOIN:** whether an index can simultaneously filter and supply a useful sort order.
8. **Statistics and cost parameters:** `ANALYZE`, `random_page_cost`, `effective_cache_size`, and other settings.
9. **Parallel scan capability:** whether scanning the table in parallel is advantageous.

A `Seq Scan` in a plan is not automatically a bug. On small tables or when retrieving a large fraction of rows, Seq Scan is often the right choice.

## 5. How B-tree Helps Find Values

B-trees are designed to support lookups based on key ordering. Common cases include:

~~~sql
WHERE customer_id = 42
WHERE total >= 100
WHERE created_at >= timestamp_value
WHERE status IN ('paid', 'pending')
ORDER BY created_at DESC
~~~

B-trees are particularly effective for equality comparisons, ordering comparisons, range scans, and matching sort orders.

However, a B-tree is not optimal for every operator:

- Searching for an array element or JSONB keys typically requires GIN with an appropriate operator class.
- Geospatial or geometric conditions often call for GiST or SP-GiST.
- Substring matching with `LIKE '%term%'` is not optimized by a plain B-tree the way simple prefix searches are; the `pg_trgm` extension with GIN/GiST can help.
- Scanning very wide time ranges on multi-billion-row append-only tables may warrant considering BRIN.

**Do not create an index first and hope every operator will use it.** Start from the actual SQL queries and the operators they require.

## 6. Building a Reproducible Practice Dataset

The dataset below creates a dedicated schema `index_lab`, with 1,000 customers and 100,000 deterministic orders. This scale is enough for queries to produce different plans after `ANALYZE` and index creation, though exact results still depend on hardware, configuration, statistics, and PostgreSQL version.

**Warning:** The first script runs `DROP SCHEMA ... CASCADE` and **deletes any existing `index_lab` schema**. Only run this in a personal lab database you own, never on production or a shared database.

### 6.1. Creating the Schema

~~~sql
-- WARNING: run only in a dedicated personal practice database.
DROP SCHEMA IF EXISTS index_lab CASCADE;
CREATE SCHEMA index_lab;

CREATE TABLE index_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    tier text NOT NULL
        CHECK (tier IN ('standard', 'silver', 'gold'))
);

CREATE TABLE index_lab.orders (
    order_id bigint PRIMARY KEY,
    tenant_id integer NOT NULL CHECK (tenant_id > 0),
    customer_id integer NOT NULL
        REFERENCES index_lab.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    created_at timestamptz NOT NULL,
    total numeric(12, 2) NOT NULL CHECK (total >= 0),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    note text
);
~~~

At this point, indexes already exist for:

- `customers.customer_id`: created by `PRIMARY KEY`.
- `customers.email`: created by `UNIQUE`.
- `orders.order_id`: created by `PRIMARY KEY`.

There is not yet any separate index on `orders.customer_id`, `orders.tenant_id`, `orders.status`, or `orders.created_at`.

### 6.2. Loading Deterministic Seed Data

~~~sql
INSERT INTO index_lab.customers (
    customer_id, full_name, email, tier
)
SELECT
    g,
    'Customer ' || g,
    'customer' || g || '@example.test',
    CASE
        WHEN g % 10 = 0 THEN 'gold'
        WHEN g % 3 = 0 THEN 'silver'
        ELSE 'standard'
    END
FROM generate_series(1, 1000) AS gs(g);

INSERT INTO index_lab.orders (
    order_id,
    tenant_id,
    customer_id,
    status,
    created_at,
    total,
    details,
    note
)
SELECT
    g::bigint,
    ((g - 1) % 20) + 1,
    ((g - 1) % 1000) + 1,
    CASE
        WHEN g % 20 = 0 THEN 'cancelled'
        WHEN g % 5 = 0 THEN 'paid'
        ELSE 'pending'
    END,
    timestamptz '2026-01-01 00:00:00+00'
        + (g % 180) * interval '1 day'
        + (g % 86400) * interval '1 second',
    (10 + (g % 1000))::numeric(12,2),
    jsonb_build_object(
        'channel', CASE
            WHEN g % 4 = 0 THEN 'mobile'
            ELSE 'web'
        END,
        'priority', CASE
            WHEN g % 100 = 0 THEN 'high'
            ELSE 'normal'
        END
    ),
    CASE
        WHEN g % 50 = 0 THEN 'Manual review'
        ELSE NULL
    END
FROM generate_series(1, 100000) AS gs(g);

ANALYZE index_lab.customers;
ANALYZE index_lab.orders;
~~~

Intentional dataset characteristics:

| Attribute | Characteristic |
| --- | --- |
| `order_id` | Unique from 1 to 100,000 |
| `customer_id` | 1,000 customers, about 100 orders each |
| `tenant_id` | 20 tenants, about 5,000 orders each |
| `status` | 75% pending, 20% paid, 5% cancelled |
| `created_at` | Distributed across 180 days, with a second offset |
| `total` | Non-negative numeric value, derived deterministically from `g` |
| `details` | JSONB containing channel and priority |
| `note` | Mostly NULL, some rows `'Manual review'` |

This synthetic data is designed to illustrate differences in **selectivity**. It does not mirror the exact customer/order distribution of a real-world application.

### 6.3. Checking Row Counts

~~~sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'pending') AS pending_count,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_count,
    COUNT(*) FILTER (WHERE status = 'cancelled') AS cancelled_count
FROM index_lab.orders;
~~~

Expected result:

| total_orders | pending_count | paid_count | cancelled_count |
| ---: | ---: | ---: | ---: |
| 100000 | 75000 | 20000 | 5000 |

If you have run examples that modify data and committed them, these counts may differ. **Intentionally** reset the lab if you want to reproduce the exact seed state.

## 7. First Experiment: Lookup by PRIMARY KEY

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM index_lab.orders
WHERE order_id = 54321;
~~~

Because `order_id` is a `PRIMARY KEY`, PostgreSQL already has a unique B-tree index supporting key lookups.

A plan **might** contain:

~~~text
Index Scan using orders_pkey on orders ...
  Index Cond: (order_id = 54321)
~~~

Cost numbers, actual time, shared hit/read counts, and extra plan nodes vary by server. Do not treat the sample above as exact output required on every run.

### Interpreting the Output

- `Index Scan`: the planner uses the index to locate matching tuples.
- `Index Cond`: the condition evaluated during the index traversal.
- `actual rows`: actual number of rows produced by the node.
- `Buffers: shared hit/read`: buffer statistics used by PostgreSQL when accessing data.
- `Execution Time`: execution duration for that run, affected by caching and system load.

Selecting 1 row out of 100,000 is a **high-selectivity** query, typically well suited for an index.

## 8. Second Experiment: Common Status and Seq Scan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM index_lab.orders
WHERE status = 'pending';
~~~

`pending` accounts for about 75% of the table. Even if you create a single-column index:

~~~sql
CREATE INDEX idx_orders_status
ON index_lab.orders(status);

ANALYZE index_lab.orders;
~~~

the planner may still pick `Seq Scan` or `Parallel Seq Scan`, because most rows must be processed and a sequential table pass can be cheaper than scanning many index entries and checking the heap.

This is **conceptual proof that an index does not automatically guarantee a speedup**.

### What About a Rarer Status?

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status
FROM index_lab.orders
WHERE status = 'cancelled';
~~~

`cancelled` is only about 5%. The planner may consider an index scan, Bitmap Scan, or Seq Scan depending on costs and data layout.

**There is no fixed 5%, 10%, or 30% threshold** below which PostgreSQL is forced to use an index. The effective crossover point shifts with row width, page count, cache state, correlation, and plan costs.

## 9. How Index Scan, Bitmap Heap Scan, and Seq Scan Differ

### 9.1. Seq Scan

~~~text
Seq Scan on orders
  Filter: (...)
~~~

PostgreSQL reads heap pages sequentially and evaluates the filter condition on each row. Best suited when reading a large fraction of rows or on small tables.

### 9.2. Index Scan

~~~text
Index Scan using idx_orders_customer ...
  Index Cond: (customer_id = 42)
~~~

PostgreSQL looks up keys in the index and accesses the heap as needed. Well suited for small result sets or when the index also provides the sort order for `LIMIT`.

### 9.3. Bitmap Index Scan + Bitmap Heap Scan

~~~text
Bitmap Heap Scan on orders
  Recheck Cond: (...)
  -> Bitmap Index Scan using idx_orders_status ...
       Index Cond: (...)
~~~

PostgreSQL collects matching page/row locations from the index into a bitmap, then reads the heap in page order to reduce random I/O. Multiple indexes can also be combined via `BitmapAnd`/`BitmapOr` when the planner judges it beneficial.

### 9.4. Index Only Scan

~~~text
Index Only Scan using some_covering_index ...
  Index Cond: (...)
  Heap Fetches: ...
~~~

Can return columns directly from the index and **avoid most heap accesses** when the corresponding pages are marked all-visible in the visibility map. If many pages are not all-visible, heap fetches are still needed to verify MVCC visibility.

The phrase “Index Only” **does not promise `Heap Fetches = 0`** under all circumstances.

## 10. How Indexes Help ORDER BY and LIMIT

A common requirement:

> Give me the 10 most recent orders for customer 42.

~~~sql
SELECT
    order_id,
    created_at,
    total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

If there is only an index on `customer_id`, PostgreSQL can locate the roughly 100 orders for customer 42, then sort them to pick the newest 10. For a customer with millions of orders, that sort can become expensive.

An index aligned with both the filter and the sort order:

~~~sql
CREATE INDEX idx_orders_customer_newest
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

A B-tree stores entries ordered by its defined columns. For `customer_id = 42`, the planner can walk the matching slice already ordered by `created_at DESC, order_id DESC` and stop early as soon as 10 rows are retrieved.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

**The benefit is not just scanning fewer rows**, but potentially **avoiding a full sort of the matching set** before applying `LIMIT`.

### When Is This Index Not Enough?

If the query asks for the 10 most recent orders **across the entire system** without filtering by customer:

~~~sql
SELECT order_id, created_at
FROM index_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

an index leading with `customer_id` does not provide a global order purely by `created_at` as requested. Another index starting with `created_at` may be needed if that workload is important enough.

**Column order in a multi-column index must follow query patterns**, not the order columns appear in the table definition.

## 11. Composite Indexes and the Leading-Column Principle

A multi-column B-tree index:

~~~sql
CREATE INDEX idx_orders_tenant_status_created
ON index_lab.orders (
    tenant_id,
    status,
    created_at DESC
);
~~~

is useful for the query:

~~~sql
SELECT order_id, created_at
FROM index_lab.orders
WHERE tenant_id = 7
  AND status = 'paid'
ORDER BY created_at DESC
LIMIT 20;
~~~

The first two columns use equality predicates; the trailing column supports range/ordering.

### Can It Still Be Used If the Leading Column Is Omitted?

~~~sql
SELECT order_id
FROM index_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC;
~~~

You should not **assume** an index starting with `tenant_id` is a good choice when `tenant_id` is absent from the filter. In certain versions or situations PostgreSQL can scan a multi-column index or use optimizations like skip scan, but effective filtering still depends heavily on constraints on the leading columns.

Practical rule: in a composite B-tree, **put frequently equality-filtered columns first**, then consider range/sort columns. Even so, verify with actual queries because selectivity and index-only scans can change the best layout.

### Can One Composite Index Replace All Single-Column Indexes?

Not necessarily.

`(tenant_id, status, created_at)` can be great for per-tenant lookups, but it is not automatically an efficient index for every query filtering only on `created_at` or sorting globally by `created_at`.

Conversely, creating every composite permutation will cause write costs and storage to explode. Choose a small set with clear value.

## 12. Indexes Help JOINs on Foreign Key Columns

Example:

~~~sql
SELECT
    o.order_id,
    c.full_name,
    o.total
FROM index_lab.orders AS o
JOIN index_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE c.customer_id = 42;
~~~

The `customers` table has a primary key on `customer_id`, so looking up the parent row is efficient. But to find `orders` rows by `customer_id`, you should consider:

~~~sql
CREATE INDEX idx_orders_customer_id
ON index_lab.orders(customer_id);
~~~

PostgreSQL **automatically creates indexes for PRIMARY KEY and UNIQUE constraints**, but **does not automatically create indexes on referencing foreign key columns in the child table**.

This matters especially when parent rows are deleted (`DELETE`) or have their key updated: PostgreSQL must check/enforce the FK constraint in the child table. If the child table is large and lacks an index on the FK, operations on the parent table may have to scan large amounts of data.

### Does Every FK Need an Index?

There is no absolute rule. If the child table is tiny, or the workload never queries by that column or deletes/updates parent keys, a separate index might not be worth the cost. But for large child tables with frequent joins or parent deletes, indexing the referencing column is well worth considering.

**Check existing indexes first**: in the lab, `idx_orders_customer_newest(customer_id, created_at DESC, order_id DESC)` also leads with `customer_id`, so it can serve many FK lookups. Adding `idx_orders_customer_id` as well would duplicate part of the read benefit while adding unnecessary write overhead.

## 13. Indexes Enforce Uniqueness, Not Just Speed

When you declare:

~~~sql
CREATE TABLE index_lab.order_requests (
    request_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    external_code text NOT NULL,
    request_amount numeric(12,2) NOT NULL,
    CONSTRAINT uq_order_request
        UNIQUE (tenant_id, external_code)
);
~~~

PostgreSQL creates a unique index backing `uq_order_request`. It serves two roles:

1. Speeds up lookups by `tenant_id` + `external_code`.
2. **Prevents two transactions from committing two rows with the same key pair**, even if both checked beforehand and believed none existed yet.

~~~sql
INSERT INTO index_lab.order_requests
    (tenant_id, external_code, request_amount)
VALUES (1, 'REQ-001', 100.00)
ON CONFLICT (tenant_id, external_code)
DO NOTHING
RETURNING request_id;
~~~

**A unique index provides a data integrity guarantee**, not merely a read optimization. Never drop an important unique constraint just because statistics show few SELECT scans on it.

However, uniqueness carries costs:

- Inserting a new key requires checking for conflicts.
- Concurrent writers inserting the same key can experience waits/contention.
- The index must be maintained for relevant modifications.
- An `ON CONFLICT DO UPDATE` upsert also incurs UPDATE work and row locking.

An index helps protect correctness, but it does not automatically make every upsert idempotent. `SET count = count + 1` in the conflict branch can still repeat side effects if a request is retried.

## 14. Cost of an INSERT When a Table Has Many Indexes

Suppose the `orders` table has:

~~~text
1. PRIMARY KEY(order_id)
2. INDEX(customer_id, created_at DESC, order_id DESC)
3. INDEX(tenant_id, status, created_at DESC)
4. INDEX(status)
5. INDEX(created_at)
6. Other expression/partial indexes
~~~

When you `INSERT` a new row:

1. PostgreSQL writes the tuple into the heap along with the appropriate WAL records.
2. For every index whose scope includes the row, PostgreSQL must insert the required entry.
3. Unique indexes must perform uniqueness checks and coordinate with concurrent transactions.
4. Index pages may need to be read/modified in buffers, logged to WAL, and occasionally split (*page split*).
5. Constraints, triggers, and FKs can also add work to the statement.

~~~mermaid
flowchart TD
    I["INSERT orders"] --> H["Write tuple to heap"]
    I --> PK["Maintain PRIMARY KEY index"]
    I --> C["Maintain customer index"]
    I --> T["Maintain tenant/status index"]
    I --> D["Maintain date/status/JSON index if present"]
    H --> W["WAL / buffers / I/O"]
    PK --> W
    C --> W
    T --> W
    D --> W
~~~

This is a **diagram of the types of work involved**, not a guarantee of PostgreSQL's exact physical execution order.

### Does Adding One Index Make INSERT Exactly 10% Slower?

There is no fixed multiplier. Cost depends on index size, whether pages are cached, entry count, pages dirtied, key distribution (sequential vs. random), uniqueness, fillfactor, contention, and storage hardware.

But the qualitative rule is vital:

> **Every additional index can add work to writes.** Therefore, the read benefit must be large enough to justify the maintenance cost.

## 15. Cost of UPDATE in PostgreSQL Is Tied to MVCC

PostgreSQL uses MVCC, so a normal `UPDATE` creates **a new tuple version** in the heap. The old version may need to be retained for active snapshots.

~~~sql
UPDATE index_lab.orders
SET note = 'Checked'
WHERE order_id = 1001;
~~~

Even when `note` is not part of any index, the operation still needs to create a new heap tuple version, write WAL, and generate future vacuum work.

So how do indexes affect `UPDATE`?

### When an Indexed Column Changes

~~~sql
UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id = 1001;
~~~

If the table has an index containing `status`, index entries may have to be updated to reflect the new key. This adds write work compared to updating an unindexed attribute.

### When an Unindexed Column Changes

~~~sql
UPDATE index_lab.orders
SET note = 'Checked'
WHERE order_id = 1001;
~~~

PostgreSQL can optimize this via a **HOT update (Heap-Only Tuple)** if conditions allow, avoiding creating new index entries for the updated version.

**This does not mean updating an unindexed column is always HOT.** It also depends on free space on the same heap page and on all other indexes, including expression indexes, partial index predicates, or `INCLUDE` columns.

## 16. HOT Updates: Why Indexes Can Make UPDATE Much More Expensive

**HOT** is a PostgreSQL MVCC optimization. When an `UPDATE` does not modify any columns needed for index maintenance and the new tuple version fits on the same heap page under PostgreSQL's rules, existing index entries can continue pointing to the heap tuple chain instead of inserting new entries into every index.

~~~text
Non-HOT (illustrative):
   UPDATE
      ├─ new heap tuple version
      ├─ new index A entry
      ├─ new index B entry
      └─ new index C entry

HOT when eligible (illustrative):
   UPDATE
      ├─ new heap tuple version on same page
      └─ heap chain maintained;
         avoids creating new entries in indexes
~~~

### Why Do Unnecessary Indexes Reduce HOT Opportunities?

Suppose a table has an `updated_at` column. If you index `updated_at` thinking “it might be useful later,” yet almost every `UPDATE` modifies `updated_at`, those updates touch an indexed column and lose HOT eligibility.

Similarly, an expression index on `lower(email)` can cause updates to `email` to incur index maintenance. A partial index with a predicate on `status` can also prevent HOT updates when `status` changes, even if the index stores different key columns.

**You must examine not only whether an index helps SELECTs, but also how frequently its referenced columns change.**

### Are There Technical Exceptions?

In newer PostgreSQL versions, certain summarizing index types like BRIN have specific HOT interaction rules. For general design, apply a practical rule of thumb: **indexes must be maintained when indexed attributes or expressions change, and more involved indexes increase write overhead**. When tuning at a low level, check the documentation and metrics for your exact major version.

## 17. Observing HOT via Statistics

PostgreSQL exposes `UPDATE` and HOT update counts in `pg_stat_user_tables`:

~~~sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'index_lab'
ORDER BY relname;
~~~

Meaning:

- `n_tup_ins`: number of tuples inserted according to statistics.
- `n_tup_upd`: number of tuples updated.
- `n_tup_hot_upd`: number of updates that used the HOT mechanism.
- `n_tup_del`: number of tuples deleted.
- `n_dead_tup`: estimated number of dead tuples, not an exact physical count.

These are **statistical counters** that may update with a delay, not immediate results of a single transaction measurement. Do not interpret a 0 immediately after a statement as “PostgreSQL did nothing.”

### Reference Formula

When `n_tup_upd > 0`, you can inspect the ratio:

\[
\text{HOT ratio} = \frac{n\_tup\_hot\_upd}{n\_tup\_upd}
\]

This metric describes table activity since stats were last reset, not a universal target KPI for every workload.

A low HOT ratio can result from:

- Frequently updated columns being included in indexes.
- Insufficient free space on heap pages.
- Index expressions, predicates, or `INCLUDE` columns referencing changed columns.
- Update distribution, fillfactor, and table history.

Do not conclude “index X definitely caused all non-HOT updates” from a single ratio alone.

## 18. Cost of DELETE: Dead Tuples and Index Cleanup

When a row is `DELETE`d, PostgreSQL marks the tuple version according to MVCC rules; older snapshots may still need to read it. The row does not necessarily disappear immediately from all physical structures upon commit.

~~~sql
BEGIN;

DELETE FROM index_lab.orders
WHERE order_id = 99999
RETURNING order_id;

ROLLBACK;
~~~

This example rolls back to keep the lab state intact.

In real systems:

1. `DELETE` can use an index to **locate the rows to delete**.
2. PostgreSQL handles MVCC/transaction state and writes necessary WAL.
3. Index entries pointing to row versions cannot be arbitrarily reclaimed while active snapshots might still need them.
4. `VACUUM` and cleanup mechanisms reclaim eligible space and entries later.
5. With heavy `DELETE`/`UPDATE` activity, dead tuples and bloat can accumulate, hurting I/O and read/write performance.

**An index can speed up finding rows to DELETE, while also being an object that must be cleaned up after DELETE.** These are two sides of the same design choice.

### Indexes Are Not Deletion History

Do not rely on indexes or old tuple versions for long-term business auditing. If you need to know who deleted an order and when, implement proper audit logs, events, or temporal tables; `VACUUM` can reclaim old physical versions once MVCC no longer needs them.

## 19. WAL, Page Splits, and Cache: Costs Harder to See in a Single SQL Query

An index introduces costs beyond CPU time:

| Component | Potential Impact |
| --- | --- |
| **WAL** | Index modifications require recovery records |
| **Buffer cache** | Index pages compete for RAM with heap pages and other indexes |
| **Page split** | Inserting a key into a full B-tree page can trigger a page split |
| **Random I/O** | Accessing scattered index and heap pages |
| **Checkpoint/writeback** | Dirty pages must eventually be flushed to storage |
| **Replica** | WAL must be shipped and replayed; heavier write workloads can increase lag |
| **Vacuum/cleanup** | Indexes must be cleaned and maintained alongside old tuple lifecycles |
| **Backup/restore** | Indexes consume backup size and add rebuild/restore time |
| **DDL** | Building an index on a large table scans data and consumes system resources |

Write costs can surface as:

- Higher `INSERT`/`UPDATE` latency.
- Lower write throughput per second.
- Higher WAL generation volume.
- Increased disk usage and cache pressure.
- Extra work for replicas and autovacuum.
- Higher contention on hot rows or keys.

Do not blame indexes for every slowdown. Triggers, FKs, locks, storage hardware, long-running transactions, and concurrent workloads can also dominate.

## 20. Single-Column, Composite, Covering, and Partial Indexes: Differences in Write Cost

For the same query, multiple index designs may assist reads, yet store different amounts of data and require maintaining different numbers of rows.

| Design | Common Benefit | Trade-off |
| --- | --- | --- |
| `(customer_id)` | Small index, filters by customer | May still need a sort when fetching newest rows |
| `(customer_id, created_at DESC)` | Filtering + ordering per customer | Wider index, more data written |
| `(customer_id, created_at DESC) INCLUDE (total)` | Can enable index-only scans needing total | Wider entries; changing total affects the index |
| Partial index `WHERE status='cancelled'` | Index holds only a subset of rows | Changing status requires maintaining membership; doesn't help other queries |
| Expression index `lower(email)` | Lookup by normalized expression | Evaluates expression on writes, maintains entries |
| GIN on JSONB | Supports JSON/array operators | Can generate many entries per row with notable write cost |

**There is no universally best index type.** It depends on query frequency, matched row counts, mutated columns, tuple width, and storage budget.

## 21. Are Covering Indexes and INCLUDE Truly “Free of Heap Reads”?

Consider the query:

~~~sql
SELECT order_id, created_at, total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

You can create an index containing both search/sort keys and returned columns:

~~~sql
CREATE INDEX idx_orders_customer_covering
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
)
INCLUDE (total);
~~~

`total` is stored as an **included payload column** rather than a search key. With a matching index and favorable visibility map state, the planner may choose an `Index Only Scan`.

### Three Caveats to Remember

1. **Visibility:** an index-only scan may still have to read the heap if pages are not marked all-visible under MVCC. On frequently updated tables, `Heap Fetches` can be high.
2. **Size:** `INCLUDE` widens entries, increasing index page count, WAL volume, and cache/write overhead.
3. **UPDATE:** if `total` changes, the included value in the index must also be maintained, which can reduce HOT update opportunities.

Index-only is not an ultimate goal. Sometimes a narrower index combined with a few heap fetches is faster overall and cheaper in write amplification.

### Limitations of INCLUDE

`INCLUDE` columns do not act as search or sort keys like key columns do. Do not put a column in `INCLUDE` and expect PostgreSQL to use it like a leading key for range searches.

## 22. Partial Indexes: Shrinking Size When Only a Subset Matters

Suppose business logic processes cancelled orders, which make up only 5% of the seed dataset:

~~~sql
CREATE INDEX idx_orders_cancelled_created
ON index_lab.orders (created_at DESC, order_id)
WHERE status = 'cancelled';
~~~

Query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM index_lab.orders
WHERE status = 'cancelled'
ORDER BY created_at DESC
LIMIT 20;
~~~

A partial index includes only rows matching `status = 'cancelled'`. Because it covers fewer rows, it can be:

- Smaller than a full index on the same keys.
- Less demanding on buffer cache.
- More efficient for the targeted queries.

### Does Write Cost Disappear?

No. PostgreSQL still must evaluate whether a row belongs in the partial index, and maintain the index when:

- Inserting a row with `status = 'cancelled'`.
- Updating a row from pending/paid to cancelled.
- Updating a row from cancelled to another status.
- Updating indexed key columns of a row already in the subset.

A partial index usually reduces the number of entries maintained compared to a broad full index, but it **does not guarantee zero predicate-evaluation overhead for writes outside the subset**.

### Must the Query State the Predicate?

The planner only uses a partial index when it can prove the query condition implies the index predicate. For example, the query must express in a planner-recognizable way that target rows have `status = 'cancelled'`.

With a **parameterized prepared statement** such as `WHERE status = $1`, a generic plan cannot always prove `$1 = 'cancelled'` for every execution. Consequently, the partial index might not be chosen in some cases even if the runtime parameter happens to be `'cancelled'`.

That is the difference between “an index that is logically right for the business case” and “an index the planner can prove applicable in a specific plan.”

## 23. Why Can't You Create a Partial Index Using now() as a Dynamic Predicate?

Invalid example:

~~~sql
-- Intentionally invalid: now() is STABLE, not IMMUTABLE.
CREATE INDEX idx_bad_recent
ON index_lab.orders(order_id)
WHERE created_at > now() - interval '7 days';
~~~

Membership in such an index would change **merely because time passes**, whereas PostgreSQL does not automatically update index entries every second for aging rows.

PostgreSQL requires functions used in index expressions and predicates to be **IMMUTABLE**. For that reason, you must never wrap `now()` inside a falsely declared `IMMUTABLE` UDF to bypass the check.

### The Proper Design

Index the column value itself:

~~~sql
CREATE INDEX idx_orders_created_at
ON index_lab.orders(created_at);
~~~

and pass the dynamic timestamp boundary in the query:

~~~sql
SELECT order_id
FROM index_lab.orders
WHERE created_at >= now() - interval '7 days';
~~~

`now()` is stable within a statement, so it works cleanly as a runtime comparison bound for a B-tree index.

For very large append-only datasets, partitioning or BRIN can be considered alongside timestamp bounds, though that is a separate architectural decision.

## 24. Expression Indexes: Optimizing Queries at the Cost of Write-Time Computation

If the application frequently looks up emails case-insensitively:

~~~sql
CREATE INDEX idx_customer_lower_email
ON index_lab.customers (lower(email));
~~~

Matching query:

~~~sql
SELECT customer_id
FROM index_lab.customers
WHERE lower(email) = lower('CUSTOMER42@EXAMPLE.TEST');
~~~

An expression index stores the precomputed value of the expression for each row, avoiding scanning and computing `lower(email)` across every row at query time.

### Trade-offs

- Inserting new rows must compute the expression and maintain the index.
- Updating `email` may require recomputing the expression and updating the index entry.
- The index consumes storage space.
- Queries must use matching expressions/operators for the planner to leverage the index.
- Collations or extension changes may require `REINDEX` and consistency checks.

If `email` already has a unique text index and the workload does not need case-insensitive lookups, an extra expression index can become **write cost with negligible return**.

## 25. A JSONB Index Can Be More Expensive Than You Think

The `orders` table has:

~~~sql
details jsonb
~~~

Suppose queries often ask:

~~~sql
SELECT order_id
FROM index_lab.orders
WHERE details @> '{"priority":"high"}'::jsonb;
~~~

A GIN index can support containment depending on the operator class:

~~~sql
CREATE INDEX idx_orders_details_gin
ON index_lab.orders
USING gin (details);
~~~

GIN is effective for data containing **many keys/values or elements** because it indexes components inside JSON documents or arrays.

However, when writing a JSONB object, the index may need to process multiple entries. Storage size and write latency can be significantly higher than a simple B-tree index on a scalar column.

### Consider Promoting a Dedicated Column

If the system **only** filters on a `priority` attribute and that attribute is central to the business schema, consider storing a typed `priority` column or generated column instead of indexing the entire JSONB document unnecessarily.

Conversely, if queries dynamically filter on many flexible JSONB keys, GIN can be justified. Decide based on actual workload rather than equating “JSONB” with “must add GIN.”

## 26. BRIN: An Option for Very Large, Physically Correlated Tables

**BRIN (Block Range Index)** stores summary metadata for ranges of heap blocks, rather than storing a detailed per-row key entry the way a B-tree normally does.

It is especially helpful when:

- The table is very large.
- Data is inserted mostly in chronological or monotonically increasing order.
- Column values correlate strongly with physical heap position.
- Reading and rechecking a few candidate blocks is acceptable.

Example:

~~~sql
CREATE INDEX idx_orders_created_brin
ON index_lab.orders
USING brin (created_at);
~~~

With suitable order data and physical correlation, BRIN can be orders of magnitude smaller than a B-tree, though it is not aimed at single-row point lookups at a specific timestamp.

### Is BRIN Exact?

BRIN is typically a **lossy index**: it indicates which block ranges **might** contain matching rows. PostgreSQL then rechecks actual rows in those blocks to discard false positives.

Conceptual comparison:

| Property | B-tree | BRIN |
| --- | --- | --- |
| Exact single-key lookup | Usually very good | Not its primary purpose |
| Size on large tables | Can be large | Usually very small when well suited |
| Uncorrelated physical data | Still effective | May scan many irrelevant blocks |
| Append-only writes | Per-entry index cost | Block-range summary cost can be lower |
| Large time-range scans | Depends on selectivity | Can work well when data is clustered by time |

Note that the lab seed distributes `created_at` using `g % 180` rather than monotonically, so **do not assume BRIN will show a dramatic advantage** in this lab. Test on production-like distributions.

## 27. Major PostgreSQL Index Types

| Type | Common Use Cases | Cost Considerations |
| --- | --- | --- |
| **B-tree** | Equality, ranges, sorting, uniqueness | Per-key entries; write maintenance |
| **Hash** | Equality with supported operators | Less versatile than B-tree; no ORDER BY/range support |
| **GiST** | Specialized types/operators like spatial, ranges, nearest-neighbor when supported by opclass | Operator-dependent; can be lossy/require recheck |
| **SP-GiST** | Space-partitioned or non-balanced data structures | Depends on data structure and operator class |
| **GIN** | Arrays, JSONB, full-text/trigrams with appropriate opclass | Multiple entries per row and higher update cost |
| **BRIN** | Very large tables with heap-correlated columns | Compact and small, but lossy scan; may read many candidate blocks |

PostgreSQL defaults to B-tree when you run `CREATE INDEX ... ON table(column)` without specifying `USING`.

**Not every index type works with every data type or operator.** An index requires a compatible operator class; sometimes an extension is needed too, such as `pg_trgm` for substring matching.

## 28. Indexes Can Increase Contention in Write Workloads

Beyond CPU and I/O, indexes can also cause concurrent transactions to contend for shared resources.

For example, a requests table with a unique index on:

~~~sql
UNIQUE (tenant_id, external_code)
~~~

If 100 concurrent requests try to insert the same `external_code`, PostgreSQL must coordinate uniqueness checks. Some transactions may wait for another transaction to commit or roll back, or enter an `ON CONFLICT` path.

Other sources of contention:

- Heavy concurrent `INSERT`s hitting hot B-tree pages.
- Concurrent `UPDATE`s on the same keys or row ranges, which already involve row-level locks.
- Page splits and maintenance operations.
- DDL transactions creating or rebuilding indexes alongside live workloads.
- Foreign keys, triggers, and constraints backed by indexes.

**Do not blame every lock wait on indexes.** Row locks, table locks, FKs, and DDL can also be the cause. Measure actual wait events using `pg_stat_activity`, `pg_locks`, and appropriate observability tools.

## 29. Indexes Do Not Change SELECT Correctness

For the same statement and snapshot, PostgreSQL must return logically equivalent results whether it uses `Seq Scan` or `Index Scan`. An index is an access path, not a “more authoritative copy of the data.”

Example:

~~~sql
SELECT *
FROM index_lab.orders
WHERE customer_id = 42;
~~~

Whether the planner picks an index or a sequential scan, the returned rows must obey `WHERE` and MVCC rules. It cannot omit rows just because an index is being vacuumed or include uncommitted changes from another transaction.

Business-rule exception: unique indexes/constraints **can restrict whether a write is valid**; that is a constraint enforcement role, not a SELECT optimization.

### Only ORDER BY Guarantees Row Order

An Index Scan may happen to return rows in index order, but **without `ORDER BY`, SQL gives no guarantee on result ordering**. Never remove `ORDER BY` just because a query currently uses a B-tree plan.

## 30. EXPLAIN: Read the Plan Before Adding Indexes

Before adding a new index, inspect the slow query:

~~~sql
EXPLAIN
SELECT order_id, total
FROM index_lab.orders
WHERE customer_id = 42;
~~~

`EXPLAIN` without `ANALYZE` shows only the **estimated plan**.

To measure a `SELECT` query in the lab:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total
FROM index_lab.orders
WHERE customer_id = 42;
~~~

Pay attention to these details:

| Plan Information | Questions to Ask |
| --- | --- |
| `Seq Scan` | Are many rows needed? Is the table small? Is a matching index missing? |
| `Index Scan` | Which columns and operators are used in `Index Cond`? |
| `Bitmap Heap Scan` | How many blocks are accessed or rechecked? |
| `Index Only Scan` | How many `Heap Fetches` occurred? |
| `Filter` | Are many rows discarded after reading? |
| `Rows Removed by Filter` | Is the scan reading too broadly before filtering? |
| `Sort` | Could an index provide the query's sort order? |
| `actual rows` vs estimated `rows` | Are table statistics accurate? |
| `Buffers: shared hit/read` | Are pages served from cache or read into buffers? |
| `Planning/Execution Time` | Is time spent in planning or execution? |

Do not compare a single “before” run with a single “after” run and draw absolute conclusions: the second run may simply benefit from a warm cache. For serious measurements, run multiple trials, control the workload, and compare options under equivalent conditions.

## 31. EXPLAIN ANALYZE on UPDATE/DELETE Actually Executes the Write

Example:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id = 1001;
~~~

**This statement actually executes the UPDATE.** It is not a “simulation-only” mode. When studying in the lab:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id = 1001;

ROLLBACK;
~~~

`ROLLBACK` reverts transactional table changes inside the database, though it does not necessarily revert external side effects or allocated sequence values. Therefore, never run `EXPLAIN ANALYZE` on write statements in production just to inspect a plan without a safe procedure.

### What to Observe on Writes

- Whether the scan node finds target rows via an index or Seq Scan.
- Actual number of rows affected.
- Trigger/FK overhead if reported.
- Buffer and WAL metrics when supported by your options and version.
- Lock wait time (observed via separate monitoring tools).
- Commit latency and write throughput under realistic load.

A fast row-lookup subplan does not mean the overall write statement is fast, because maintaining multiple indexes can represent substantial overhead.

## 32. Measuring Index Size via System Catalogs

Inspect existing indexes on `orders`:

~~~sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
JOIN pg_index AS x
    ON x.indrelid = t.oid
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE n.nspname = 'index_lab'
  AND t.relname = 'orders'
ORDER BY pg_relation_size(i.oid) DESC;
~~~

An overview query:

~~~sql
SELECT
    pg_size_pretty(
        pg_table_size('index_lab.orders'::regclass)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('index_lab.orders'::regclass)
    ) AS all_indexes_size,
    pg_size_pretty(
        pg_total_relation_size('index_lab.orders'::regclass)
    ) AS total_relation_size;
~~~

Where:

- `pg_table_size`: size of the table and associated components, **excluding indexes**.
- `pg_indexes_size`: total size of all indexes on the table.
- `pg_total_relation_size`: combined size of the table, all its indexes, and related components.

These numbers vary with data volume, storage settings, page fill, VACUUM state, and which indexes have been created before measuring.

### Don't Look Only at Query Latency

An index that shaves 5 ms off a once-a-day query while consuming gigabytes of space and slowing down millions of daily `INSERT`s can be a poor trade-off. Evaluate the total **read + write + storage + operational cost**.

## 33. Monitoring Whether Indexes Are Being Used

The `pg_stat_user_indexes` view reports index access statistics:

~~~sql
SELECT
    schemaname,
    relname,
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'index_lab'
ORDER BY relname, indexrelname;
~~~

Common meanings:

- `idx_scan`: number of index scans initiated on this index.
- `idx_tup_read`: number of index entries returned/processed by scans on this index.
- `idx_tup_fetch`: number of live heap rows fetched by simple index scans using this index, subject to access-method caveats.

**Never infer solely from `idx_scan = 0` that an index is useless and safe to drop immediately.**

An index might:

- Enforce a `UNIQUE` or `PRIMARY KEY` constraint without appearing in normal SELECT queries.
- Serve rare but critical queries (month-end jobs, reporting periods, incident recovery).
- Have been newly created or have recently reset statistics.
- Be used infrequently yet prevent an extremely expensive full table scan.
- Only be selected by plans under specific data distributions, parameters, or time windows.

### Counters Have History and Lag

Statistics can be reset and are not always updated instantaneously. When deciding whether an index can be dropped, examine a **sufficiently long observation window**, hourly/daily/monthly workload cycles, and real application queries.

Never use a single point-in-time stats snapshot to justify dropping an index in production.

## 34. Comparing Read and Write Costs in Lab Experiments

You can test two groups of operations in a **dedicated lab database**.

### 34.1. Reading with Only PRIMARY KEY and a Few Indexes

~~~sql
ANALYZE index_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total
FROM index_lab.orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
~~~

If `idx_orders_customer_newest` already exists, the plan will differ from before it existed. Record the plan and buffer counts in your own environment.

### 34.2. Adding a Matching Index

~~~sql
CREATE INDEX IF NOT EXISTS idx_orders_customer_newest
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);

ANALYZE index_lab.orders;
~~~

Re-measure the SELECT query from the previous step. Do not look only at execution time—check whether fewer rows/blocks are scanned and whether the Sort node disappeared.

### 34.3. Testing UPDATE on Unindexed vs. Indexed Columns

~~~sql
BEGIN;

UPDATE index_lab.orders
SET note = 'Reviewed'
WHERE order_id BETWEEN 20001 AND 20100;

ROLLBACK;
~~~

Compare against:

~~~sql
BEGIN;

UPDATE index_lab.orders
SET status = 'paid'
WHERE order_id BETWEEN 20001 AND 20100;

ROLLBACK;
~~~

On a schema with an index on `status`, the second statement can trigger index maintenance and reduce HOT update eligibility. However, a single run is **not an exact benchmark**: the two updates modify different columns, may actually change different numbers of rows, and differ in cache state, WAL, and HOT conditions.

For production evaluation, measure on representative data and workloads across multiple runs, over sufficient duration, tracking HOT ratio, WAL, and index size. Do not extrapolate exact speedup/slowdown factors from tiny examples.

## 35. Creating an Index Has Cost and Can Cause Locks

On a large table serving live application traffic, the command:

~~~sql
CREATE INDEX idx_orders_created_normal
ON index_lab.orders(created_at);
~~~

must read table data, sort/build the index structure, consume system resources, and acquire locks according to standard `CREATE INDEX` rules. It can block concurrent writes while the index is being built.

PostgreSQL supports:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_created_concurrently
ON index_lab.orders(created_at);
~~~

`CONCURRENTLY` is designed to avoid blocking normal writes during index creation, yet it is **not free**:

- It can require multiple table scans and wait for concurrent transactions/snapshots.
- It generally takes longer and consumes more total resources than a standard index build.
- It cannot run inside an explicit transaction block.
- If it fails, it can leave behind an **INVALID** index that must be inspected and cleaned up.
- There are concurrency restrictions against running multiple concurrent index builds on the same table simultaneously.

**Do not run both forms for the same index in production just to “be safer.”** Choose the name, deployment approach, timing, and rollback plan intentionally.

### Checking Index Validity

~~~sql
SELECT
    i.relname AS index_name,
    x.indisvalid,
    x.indisready
FROM pg_index AS x
JOIN pg_class AS i
    ON i.oid = x.indexrelid
WHERE x.indrelid = 'index_lab.orders'::regclass
ORDER BY i.relname;
~~~

`indisvalid = false` indicates the index is not valid for planner use according to the catalogs. An invalid index can still incur maintenance overhead in certain states; diagnose the failure and recover according to the documentation.

## 36. Dropping Indexes Also Requires a Plan

If an index is proven unnecessary, you can remove it with:

~~~sql
-- Example only on a lab index not backing a unique/PK constraint.
DROP INDEX index_lab.idx_orders_created_normal;
~~~

In write-heavy environments, `DROP INDEX CONCURRENTLY` avoids blocking concurrent operations, though it has its own restrictions—including **not running inside an explicit transaction block**, and not being arbitrarily applicable to constraint-backing indexes.

Never casually drop an index backing a critical `PRIMARY KEY`/`UNIQUE` constraint. Such indexes are owned by constraints, and dropping the constraint removes the data integrity guarantee.

### Checklist Before Dropping an Index

1. Does this index enforce a unique, primary key, or exclusion constraint?
2. Do month-end queries, batch jobs, or incident-recovery procedures rely on it?
3. Do tenant-specific queries or foreign key checks depend on it?
4. Does another index truly cover all of its functionality?
5. Will query plans degrade significantly after dropping it?
6. Is there a fast rollback plan, and how long would rebuilding it take?
7. Do we need `CONCURRENTLY` and transaction-block control?

The goal is not “the fewest indexes possible” at all costs, but **not keeping indexes whose benefit does not justify their cost**.

## 37. REINDEX, Bloat, and Index Maintenance

Under heavy `UPDATE`/`DELETE` workloads, index structures can accumulate unused space over time. PostgreSQL provides vacuum cleanup and B-tree maintenance mechanisms, yet occasionally **REINDEX** is worth considering when signs of bloat, collation changes, corruption, or special maintenance needs appear.

Syntax example:

~~~sql
-- Reference command only; do not run casually in production.
REINDEX INDEX index_lab.idx_orders_customer_newest;
~~~

Supported PostgreSQL versions also provide `REINDEX CONCURRENTLY` variants, with specific rules around transactions and object types.

**REINDEX is not a daily routine just because a table receives many UPDATEs.** It consumes I/O, CPU, WAL, disk space, and can cause contention. First understand the root causes of bloat: autovacuum settings, long-running transactions, and write patterns.

### How VACUUM and REINDEX Differ

- **VACUUM**: cleans up eligible dead tuple versions and index entries, and maintains visibility maps and transaction freeze state.
- **REINDEX**: rebuilds an index from scratch based on current live table data.

`VACUUM` does not necessarily shrink index files back to the OS, and `REINDEX` does not replace `VACUUM`'s heap cleanup and freezing responsibilities.

## 38. Fillfactor and Write Tuning: No One-Size-Fits-All Formula

PostgreSQL exposes storage parameters like `fillfactor` to control how tightly pages are packed.

- On **heap tables**, leaving free space on pages can increase HOT update opportunities.
- On **B-tree indexes**, fillfactor controls space reserved for new entries and affects page split behavior under your workload.

Example creating a new lab table with a custom setting:

~~~sql
CREATE TABLE index_lab.update_hot_demo (
    id bigint PRIMARY KEY,
    frequently_changed_note text
) WITH (fillfactor = 80);
~~~

This is only a syntax example. **Do not apply `fillfactor = 80` to every table**: lowering fillfactor increases the number of pages needed to store the same data, which can hurt scan and cache efficiency. The trade-off only pays off when update frequency and tuple growth patterns align.

The “best” setting depends on your read/write mix, page fill behavior, updated columns, bloat, and storage resources.

## 39. Does Table Partitioning Replace Indexes?

**Partitioning** splits a logical table into physical partitions, for instance by month or tenant. PostgreSQL can perform **partition pruning** to skip irrelevant partitions when query predicates allow.

However:

- Each partition may still need indexes to locate a small number of rows within that partition.
- Indexes speed up row-level access, whereas partitioning narrows **which tables/partitions** must be inspected.
- Too many partitions/indexes also increase metadata, planning, maintenance, and DDL overhead.
- Unique constraints on partitioned tables have strict rules tied to the partition key.

Simple example: a table partitioned by month reduces scan scope for monthly queries, yet looking up an order by `order_id` within a month still typically requires a B-tree index on that key.

**Do not treat partitioning as a “giant index” that replaces all read indexing.**

## 40. Why Indexing Every Column Is an Anti-Pattern

Suppose a table has 30 columns and someone indexes every column “in case we filter on it later.” That leads to:

- Many indexes to maintain on every `INSERT`.
- Almost any `UPDATE` touching an indexed column, destroying HOT opportunities.
- Extra `DELETE`/`VACUUM` cleanup work.
- Large total storage overhead.
- Still missing the exact composite key/order needed by critical queries.
- More index candidates for the planner to evaluate, though planning time impact varies.
- Overlapping or near-duplicate indexes.

**A better strategy: measure and choose based on real query patterns.**

~~~text
Critical queries
    ↓
WHERE / JOIN / ORDER BY / LIMIT
    ↓
Cardinality + selectivity + data distribution
    ↓
Minimal suitable index
    ↓
EXPLAIN (ANALYZE, BUFFERS)
    ↓
Measure write cost + size + HOT/WAL
    ↓
Keep, adjust, or drop with evidence
~~~

## 41. Cases Where You Should Not Rush to Create an Index

### 41.1. Very Small Tables

A 20-row configuration table can often be sequentially scanned faster than traversing an index.

### 41.2. Queries Needing Most Rows

~~~sql
SELECT COUNT(*)
FROM index_lab.orders
WHERE status = 'pending';
~~~

With 75% of rows pending, a Seq Scan can be the right plan.

### 41.3. Rarely Executed Queries

A large index serving a once-a-year query may not justify daily write overhead.

### 41.4. Constantly Updated Columns

Indexing `updated_at` when every `UPDATE` modifies it can cause heavy write amplification. Only keep it if queries filtering on update time deliver substantial real value.

### 41.5. Queries Using Expressions That Don't Match the Index

For example, an index on `email` does not mean `WHERE lower(email) = ...` can perform an efficient lookup. You need an expression index or a normalized storage model.

### 41.6. Stale Statistics

If the planner misestimates row counts after a bulk load, run `ANALYZE` before concluding that an index is missing.

### 41.7. Existing Composite Index Already Covers the Main Need

If `(customer_id, created_at DESC)` already serves customer lookups, adding `(customer_id)` may offer less benefit than its new write cost. Verify with actual queries rather than dropping or adding on guesswork.

## 42. Common Mistakes When Evaluating Indexes

### 42.1. Assuming an Index Always Makes SELECT Faster

The planner may still choose `Seq Scan` when many rows match or the table is small.

### 42.2. Measuring Only Read Queries and Ignoring Write Throughput

An index that speeds up a report yet slows down millions of daily `INSERT`/`UPDATE` operations can hurt overall system health.

### 42.3. Forgetting PRIMARY KEY/UNIQUE Already Create Indexes

This leads to redundant duplicate indexes and extra write overhead.

### 42.4. Assuming PostgreSQL Automatically Indexes Child FK Columns

PostgreSQL automatically indexes referenced `PRIMARY KEY`/`UNIQUE` columns; it does not automatically index referencing foreign keys.

### 42.5. Indexing Low-Cardinality Status Columns and Expecting Guaranteed Gains

If 75% of rows share the same status, a plain single-column index may go unused.

### 42.6. Ignoring Column Order in Composite Indexes

`(customer_id, created_at)` and `(created_at, customer_id)` serve very different query patterns.

### 42.7. Putting Every Returned Column in INCLUDE

This bloats the index and forces index maintenance whenever included columns change, reducing HOT updates.

### 42.8. Using STABLE/VOLATILE Functions in Expression or Partial Indexes

`now()` is not `IMMUTABLE` and cannot be used as a sliding predicate such as “last 7 days from now.”

### 42.9. Assuming Index Only Scan Never Touches the Heap

Visibility maps and MVCC can force heap fetches, especially on write-heavy tables.

### 42.10. Thinking UPDATE Has Write Cost Only When Index Key Columns Change

Even updating unindexed columns creates new heap tuple versions, WAL, and vacuum work; HOT only avoids part of index maintenance when eligible.

### 42.11. Confusing VACUUM with REINDEX

`VACUUM` performs MVCC cleanup; `REINDEX` rebuilds an index structure when needed.

### 42.12. Running Standard CREATE INDEX on Large Production Tables Without Checking Locks

Standard builds can block writes. Consider `CONCURRENTLY`, deployment windows, and failure handling.

### 42.13. Thinking CREATE INDEX CONCURRENTLY Uses No Resources

It still scans the table, generates WAL/I/O, and waits on transactions; it often takes longer than a normal build.

### 42.14. Dropping an Index Simply Because idx_scan = 0

Counters may have been reset, might not cover full business cycles, or the index may enforce a constraint.

### 42.15. Running EXPLAIN ANALYZE on UPDATE and Forgetting It Modifies Data

`ANALYZE` actually executes DML. Only test in a lab or controlled transaction.

### 42.16. Assuming Index Order Guarantees Output Order Without ORDER BY

SQL never guarantees row order without `ORDER BY`, even if today's plan uses an index.

### 42.17. Overlooking Tenant/Ownership Filtering

An index on `order_id` alone locates rows quickly, but multi-tenant queries must still enforce authorization filters and may benefit from tenant-leading composite indexes. Indexes do not provide security.

### 42.18. Creating a BRIN Index on Randomly Scattered Data and Expecting Speedups

BRIN depends heavily on physical correlation; if every block range contains the full value spectrum, block skipping is ineffective.

### 42.19. Forgetting Partial Index Predicates Must Be Provable by the Planner

A generic prepared plan with bind parameters may fail to use a partial index where a literal constant would succeed.

### 42.20. Judging by a Single Run's Timing

Caching, background I/O, and concurrent load create noise. Run multiple measurements and inspect `BUFFERS`.

## 43. Exercises with Answers

The following exercises use the `index_lab` schema from Section 6. For DML statements, wrap them in `BEGIN ... ROLLBACK` when testing. For DDL creating extra indexes, run in an isolated lab database and avoid placing `CONCURRENTLY` commands inside transaction blocks.

### Exercise 1. What Problem Does the Primary Key Index Solve?

**Question:** Why is finding `order_id = 54321` among 100,000 orders usually faster with a primary key index?

**Answer:** PostgreSQL can traverse the B-tree by key and read far less data than scanning the entire heap, though the actual plan choice still rests with the planner.

### Exercise 2. Why Does the Pending Query Still Use Seq Scan Despite an Index on status?

**Answer:** `pending` makes up 75% of the table; scanning the whole table can be cheaper than traversing many index entries and accessing the heap. An index is a cost-based choice, not a mandate.

### Exercise 3. Create an Index for a Customer's 10 Most Recent Orders

~~~sql
CREATE INDEX idx_exercise_customer_latest
ON index_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);
~~~

**Answer:** Matches `WHERE customer_id = ? ORDER BY created_at DESC, order_id DESC LIMIT 10`. If you already created the equivalent `idx_orders_customer_newest` in Section 10, do not keep both indexes in production.

### Exercise 4. Does an FK Automatically Create an Index on the Child Table?

**Answer:** No. The referenced primary key/unique constraint on the parent table is indexed; PostgreSQL does not automatically index `orders.customer_id`. Evaluate adding one based on JOINs and parent deletes/updates.

### Exercise 5. What Queries Does This Composite Index Serve?

~~~sql
CREATE INDEX idx_exercise_tenant_status
ON index_lab.orders(tenant_id, status, created_at DESC);
~~~

**Answer:** Especially useful for queries filtering by `tenant_id` and `status`, then ordering/filtering by `created_at`. It does not guarantee optimal support for queries filtering globally by `created_at` alone.

### Exercise 6. Why Does INCLUDE(total) Have a Write Cost?

**Answer:** `total` is stored in the index leaf payload, making entries wider and requiring index maintenance whenever `total` changes, which can reduce HOT update eligibility. Index-only benefits also depend on the visibility map.

### Exercise 7. Partial Index for Cancelled Orders

~~~sql
CREATE INDEX idx_exercise_cancelled
ON index_lab.orders(created_at DESC)
WHERE status = 'cancelled';
~~~

**Answer:** The index contains only cancelled rows (~5% of the seed); it can be much smaller than an equivalent full index and helps queries that explicitly specify `status = 'cancelled'`.

### Exercise 8. Can now() Be Used in a Partial Index Predicate?

**Answer:** Invalid under PostgreSQL's immutability requirement for index predicates. Index `created_at` and use `created_at >= now() - interval '7 days'` in the query instead.

### Exercise 9. What Happens to INSERTs When 5 More Indexes Are Added?

**Answer:** PostgreSQL may have to insert entries into multiple indexes, increasing CPU, I/O, WAL, buffer pressure, and any uniqueness checks. You cannot derive a fixed latency multiplier purely from the index count.

### Exercise 10. Is Updating note Always a HOT Update?

**Answer:** No. It requires no affected indexed columns, enough free space on the same heap page, and other internal conditions. Updating `note` still creates a new MVCC tuple version.

### Exercise 11. How Does Updating status Affect Writes When index(status) Exists?

**Answer:** Changing `status` can modify index entries or partial index membership, incurring maintenance overhead and typically preventing HOT updates for standard indexes.

### Exercise 12. Why Doesn't DELETE Immediately Shrink the Index File?

**Answer:** MVCC must retain versions needed by older snapshots; cleanup/vacuum reclaims eligible entries later. File size on disk does not necessarily shrink immediately.

### Exercise 13. Compare Index Scan vs. Bitmap Heap Scan

**Answer:** `Index Scan` looks up the index and fetches matching heap rows directly; `Bitmap Heap Scan` collects matching locations/blocks from the index first and reads heap pages in block order to reduce scattered I/O, rechecking when lossy.

### Exercise 14. Does Index Only Scan Always Have Heap Fetches = 0?

**Answer:** No. If heap pages are not marked all-visible in the visibility map, PostgreSQL still needs heap fetches to check MVCC visibility.

### Exercise 15. Why Can GIN Be More Expensive When Writing JSONB?

**Answer:** GIN may need to write multiple index entries for keys/values inside a single JSONB object; its size and maintenance profile differ substantially from a single-column scalar B-tree.

### Exercise 16. When Is BRIN Appropriate?

**Answer:** Very large tables where a column correlates strongly with physical heap location, typically time-ordered append-only data; it is tiny, though lossy and may read/recheck multiple blocks.

### Exercise 17. How to Check Total Disk Space Used by a Table's Indexes?

~~~sql
SELECT
    pg_size_pretty(
        pg_indexes_size('index_lab.orders'::regclass)
    ) AS indexes_size;
~~~

**Answer:** Returns the total size of all indexes attached to `orders` via PostgreSQL's built-in admin function.

### Exercise 18. Should an Index with idx_scan = 0 Be Dropped Immediately?

**Answer:** Not without further checks. Review observation duration, stats resets, rare batch queries, `UNIQUE`/`PK`/`FK` roles, periodic workloads, and replacement plans.

### Exercise 19. Can CREATE INDEX CONCURRENTLY Run Inside BEGIN?

**Answer:** No. PostgreSQL forbids running `CREATE INDEX CONCURRENTLY` inside an explicit transaction block. It reduces write blocking but still takes time/resources and can leave an `INVALID` index if it fails.

### Exercise 20. Why Must EXPLAIN ANALYZE UPDATE Be Used Carefully?

**Answer:** Because it actually executes the `UPDATE`. Use plain `EXPLAIN` for estimates or wrap lab tests in `BEGIN ... ROLLBACK` to measure safely.

### Exercise 21. Why Doesn't a Regular Index Replace a Unique Constraint?

**Answer:** A non-unique index only speeds up access; it does not forbid duplicates. A unique constraint/unique index enforces uniqueness invariants under concurrent writes.

### Exercise 22. Is an Index Necessary for COUNT(*) Over an Entire Table?

~~~sql
SELECT COUNT(*) FROM index_lab.orders;
~~~

**Answer:** No ordinary index automatically lets PostgreSQL know an exact count valid for the current MVCC snapshot without checking data/visibility appropriately. The planner may use Seq Scan or other paths depending on circumstances, but adding an index does not make `COUNT(*)` instantaneous.

### Exercise 23. Why Can an Index on updated_at Be Harmful?

**Answer:** If nearly every `UPDATE` modifies `updated_at`, that index must be maintained constantly and can block HOT updates. Keep it only if queries filtering on `updated_at` deliver clear value.

### Exercise 24. Propose an Index for the Following Query

~~~sql
SELECT order_id, created_at
FROM index_lab.orders
WHERE tenant_id = 7
  AND status = 'cancelled'
ORDER BY created_at DESC
LIMIT 25;
~~~

**Suggested answer:** A B-tree on `(tenant_id, status, created_at DESC)` or a partial index for `status = 'cancelled'` with keys `(tenant_id, created_at DESC)`. Choose based on cancelled ratio, tenant distribution, and write workload, then verify with `EXPLAIN`.

## 44. Workload-Driven Index Design Workflow

A practical workflow:

1. **Collect critical queries** from the application, logs, and `pg_stat_statements` if enabled and accessible.
2. **Identify the problem:** latency, excessive block reads, large sorts, slow JOINs, locks during parent deletes, or uniqueness guarantees.
3. **Inspect current plans** safely with `EXPLAIN (ANALYZE, BUFFERS)`.
4. **Audit existing indexes:** primary/unique, composite, partial, expression, `INCLUDE`.
5. **Estimate selectivity and cardinality**, verifying that table/column statistics are up to date.
6. **Choose indexes around WHERE + JOIN + ORDER BY + LIMIT**, not bare column names.
7. **Ask whether the query needs most rows:** if so, Seq Scan may be right.
8. **Ask how often indexed columns change**, including predicates, expressions, and included columns.
9. **Assess impact on INSERT/UPDATE/DELETE, HOT, WAL, VACUUM, and storage.**
10. **Measure read gains in lab/staging** with realistic data and workload.
11. **Measure write costs**, not just a single SELECT run.
12. **Check contention and long transactions**, since indexes do not eliminate lock waits by themselves.
13. **Plan deployment**: standard `CREATE INDEX` vs. `CONCURRENTLY`, maintenance window, and free disk space.
14. **Monitor post-deployment:** index size, `idx_scan`, latency, write throughput, HOT ratio, WAL/replica lag.
15. **Clean up verified redundant or low-value indexes**, without removing critical constraint indexes.
16. **Re-evaluate periodically as workloads evolve**, because an optimal index today may not fit once the table grows 100x or queries change.

## 45. Official PostgreSQL Documentation

To verify syntax, internals, and limits for your **exact PostgreSQL major version**, refer to:

- [Indexes](https://www.postgresql.org/docs/current/indexes.html) — general purpose and costs of indexes.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html) — B-tree, Hash, GiST, SP-GiST, GIN, BRIN.
- [Multicolumn Indexes](https://www.postgresql.org/docs/current/indexes-multicolumn.html) — column ordering and usage conditions.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html) — expression indexes and write costs.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html) — predicates and applicability rules.
- [Index-Only Scans](https://www.postgresql.org/docs/current/indexes-index-only-scans.html) — `INCLUDE` and the visibility map.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html) — syntax, `CONCURRENTLY`, storage parameters.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html) — dead tuples, index cleanup, MVCC, and vacuum.
- [HOT](https://www.postgresql.org/docs/current/storage-hot.html) — Heap-Only Tuple updates.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html) — query plans and `BUFFERS`.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html) — `pg_stat_user_tables`, `pg_stat_user_indexes`.
- [System Information Functions](https://www.postgresql.org/docs/current/functions-admin.html) — size functions such as `pg_relation_size` and `pg_indexes_size`.

`/current/` points to the latest release on the website. When deploying to a specific version, consult the documentation for that exact major version and verify version-dependent features such as specific index build options or index scan optimizations.

## 46. Summary

**Indexes help PostgreSQL avoid reading all table data when only a small subset is needed, while also supporting JOINs, ORDER BY, LIMIT, and uniqueness enforcement.** Yet an index is an **extra storage and write structure**, never a completely free speedup switch.

Key takeaways:

1. **Read benefit:** an index works well when it reduces the amount of data read or supplies the needed sort order; however, `Seq Scan` can win when most rows must be processed.
2. **INSERT cost:** every index may require new entries and increase WAL, I/O, and cache pressure.
3. **UPDATE cost:** MVCC creates new tuple versions; modifying indexed columns triggers index maintenance and reduces HOT opportunities.
4. **DELETE cost:** old versions and index entries are cleaned up via `VACUUM`, rather than disappearing instantly.
5. **Workload-driven design:** composite, partial, expression, covering, GIN, and BRIN indexes solve different query patterns at different write costs.
6. **Measure instead of guessing:** inspect `EXPLAIN`, `BUFFERS`, catalog sizes, `pg_stat_user_indexes`, and `n_tup_hot_upd`, alongside write latency and replica lag under load.
7. **Do not drop constraint indexes just because few SELECTs scan them:** `PRIMARY KEY`/`UNIQUE` indexes protect data integrity, not merely read speed.

A good index is one that **solves a real, high-value read or data-integrity requirement at a write-maintenance cost the system can afford**. An indexing decision is only complete when you can answer both questions: *which queries benefit* and *which writes pay the price*.
