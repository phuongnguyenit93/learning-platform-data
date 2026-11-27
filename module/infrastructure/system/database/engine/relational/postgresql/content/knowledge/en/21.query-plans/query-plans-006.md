# Index-Only Scans and Heap Fetches in PostgreSQL

## 1. Why Can the Name "Index Only Scan" Be Misleading?

Consider a query fetching the newest orders for a store:

```sql
SELECT sale_id, sold_at, amount_cents
FROM sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

If a B-tree index holds every column needed to search, filter, sort, and return results, we might expect PostgreSQL to read **only the index** without ever visiting rows in the table.

PostgreSQL has an execution node named **`Index Only Scan`** for this purpose. However, PostgreSQL uses **MVCC (Multi-Version Concurrency Control)**. An entry in a B-tree does not by itself prove whether the corresponding row version is visible under the reading transaction's snapshot.

Consequently, a plan node named `Index Only Scan` **can still read the heap**. In `EXPLAIN (ANALYZE, BUFFERS)`, how often the heap had to be checked is reported as:

```text
Heap Fetches: N
```

Two illustrative cases:

```text
Index Only Scan ...
  Heap Fetches: 0

Index Only Scan ...
  Heap Fetches: 187
```

Both are `Index Only Scan`. The difference is how many index entries could skip heap visibility checks at runtime thanks to the **visibility map**.

**Core takeaway:** Having all needed columns in an index is a necessary condition to avoid reading row data, yet **heap page visibility** decides whether the heap can actually be skipped during each check.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish `Index Scan`, `Index Only Scan`, `Bitmap Heap Scan`, and `Seq Scan`.
2. Know the conditions required for the planner to consider Index Only Scan.
3. Understand a **covering index** and the role of `INCLUDE`.
4. Explain why indexes do not directly store all required MVCC metadata.
5. Understand the **visibility map (VM)**, the *all-visible* bit, and the *all-frozen* bit.
6. Read `Heap Fetches`, `Buffers`, `Index Cond`, and `actual rows` accurately.
7. Observe changes hands-on after `INSERT`, `VACUUM`, and `UPDATE`.
8. Understand why an UPDATE changing a non-indexed column can still increase Heap Fetches.
9. Evaluate effectiveness via all-visible page ratio, row count, heap I/O, and index cost.
10. Know the limitations of expression indexes, partial indexes, `INCLUDE` indexes, MVCC, and the query planner.
11. Apply these insights when tuning Java/JDBC queries and production systems.

---

## 2. Four Familiar Data-Reading Paths

When querying an indexed table, PostgreSQL does not have a single execution path.

| Node | Execution idea | Can it read the heap? |
|---|---|---|
| `Seq Scan` | Sequentially read table pages | Yes; it is the primary data source |
| `Index Scan` | Traverse index keys, visit matching records in heap | Normally yes |
| `Index Only Scan` | Traverse index; fetch columns from index, read heap only when needed for visibility | Can be positive or 0 |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Gather candidate locations from index, then read heap pages via bitmap | Yes, in the Bitmap Heap Scan step |

### 2.1. Index Scan

Diagram:

```text
B-tree index
    |
    | find store_id = 42
    v
Index entries + heap TIDs
    |
    v
Visit corresponding heap tuples
    |
    v
Check visibility, read columns, return results
```

`Index Scan` fits when an index locates rows quickly, yet heap visits are needed because the query selects columns outside the index or the scan structure was not chosen to skip the heap.

### 2.2. Index Only Scan

Diagram:

```text
B-tree index
    |
    | scan key range and read payload
    v
Index entry -> heap TID
    |
    v
Visibility map of heap page holding TID
    |
    +-- all-visible = 1 --> no heap read needed to verify tuple
    |
    +-- all-visible = 0 --> must visit heap to check MVCC
    |
    v
Return columns read from index
```

The word *Only* describes the goal of **retrieving column values from the index**. It does not guarantee zero heap checks.

### 2.3. Bitmap Heap Scan

For conditions returning many scattered rows, the planner may pick:

```text
Bitmap Index Scan
      |
      v
Bitmap of heap TIDs/pages
      |
      v
Bitmap Heap Scan
      |
      v
Read heap pages per bitmap plan
```

A bitmap plan reduces random I/O, yet loses linear B-tree entry ordering. If the query has `ORDER BY`, a `Sort` may be required.

### 2.4. Seq Scan Is Not Always a Bad Plan

If a table is tiny or a query returns most of its rows, reading sequentially can beat going through an index and verifying many positions.

Never judge "good/bad" solely from node names. Inspect **cost, rows, buffers, timing, and real workload**.

## 3. Index Entry vs Heap Row

PostgreSQL stores table row versions in the **heap**. During `INSERT`/`UPDATE`/`DELETE`, MVCC creates or alters visibility of **tuple versions**.

A typical B-tree index stores:

- **Index key** values.
- Payload columns if the index has `INCLUDE`.
- A pointer to the row/row version, usually a **heap TID**.

Heap tuples also carry critical MVCC metadata, such as creating/deleting transaction info. An index entry **does not carry full visibility information** to determine on its own whether a tuple is visible in a given snapshot.

### 3.1. Why Not Simply Return Results Straight from the Index?

Imagine:

```text
T1: UPDATE sale 100 from status='NEW' to 'PAID'
T1: not yet COMMITTED

T2: SELECT using index
```

T2 must not treat T1's uncommitted version as committed and visible across all snapshots. Finding an index entry alone is not enough to decide that.

### 3.2. Index Only Scan Does Not Bypass MVCC

Even when every returned column lives in the index, PostgreSQL still must guarantee:

- Rows match the reading transaction's snapshot.
- Uncommitted or invalid versions are never returned erroneously.
- Transaction visibility rules are upheld.

The **visibility map** is the mechanism telling PostgreSQL when it can safely skip visiting the heap to inspect individual tuples.

## 4. Visibility Map: The Key to Avoiding Heap Fetches

Every heap relation has a **visibility map** (often abbreviated *VM*) tracking visibility status at the **heap page** level.

In PostgreSQL's standard mechanism, the VM tracks key bits:

- **All-visible:** every tuple on the heap page is considered visible to all eligible transactions; an index-only scan can skip checking individual tuples on that heap page.
- **All-frozen:** every relevant tuple on the page is frozen under VACUUM rules, aiding transaction ID/tuple freezing management and related optimizations.

**For Index Only Scan, the all-visible bit is the decisive signal.** Do not confuse `all-frozen` with the mandatory requirement for Index Only Scan.

### 4.1. Visibility Map Tracks Pages, Not Individual Rows

Suppose a heap page contains multiple rows:

```text
Heap page P
   tuple 1
   tuple 2
   tuple 3
   tuple 4
   ...

VM[P].all_visible = 1
    -> matching tuples on this page can be verified by
       index-only scan without re-reading page P

VM[P].all_visible = 0
    -> when checking an entry pointing to P,
       index-only scan must visit the heap for visibility
```

A single UPDATE to one row on a page clears the all-visible bit for the **entire page**. That affects index-only scans for **all other rows on that same page**, even if those rows were untouched.

### 4.2. Why Is Page-Level Design Advantageous?

The VM is vastly smaller than a structure storing per-tuple visibility metadata, so it can be read efficiently. PostgreSQL checks the VM first; if the page is all-visible, no heap tuple fetch is needed to confirm visibility.

### 4.3. When Is the VM Updated?

Conceptually:

- Fresh `INSERT`s introduce tuples that cannot immediately be assumed all-visible.
- `UPDATE`/`DELETE` can invalidate a previously all-visible page, clearing its bit.
- `VACUUM` verifies, cleans up, and marks eligible pages as all-visible.
- Unfinished transactions, versions still needed by old snapshots, and data state can prevent VACUUM from marking some pages yet.

**Do not assume "right after COMMIT, the VM instantly becomes all-visible."** COMMIT does not mean VACUUM has scanned and marked the pages.

### 4.4. VACUUM Is Not a Switch Guaranteeing Heap Fetches = 0

Right after VACUUM finishes, another transaction may modify the table and clear all-visible bits on affected pages. Furthermore, some pages may not yet qualify to be marked.

Hence observed Heap Fetches depend on **execution timing and live data state**, not just VACUUM schedules.

## 5. Condition 1: The Index Must Contain the Data the Query Needs

An `Index Only Scan` is only possible when PostgreSQL can obtain the needed columns for that access step from an eligible index instead of reading an unindexed column from the heap.

Example table:

```sql
CREATE TABLE sales (
    sale_id bigint PRIMARY KEY,
    store_id integer NOT NULL,
    sold_at timestamptz NOT NULL,
    amount_cents bigint NOT NULL,
    status text NOT NULL,
    note text NOT NULL
);
```

Index:

```sql
CREATE INDEX ON sales(store_id, sold_at);
```

Query:

```sql
SELECT store_id, sold_at
FROM sales
WHERE store_id = 42;
```

All queried columns belong to the index, so **Index Only Scan is possible** if other conditions hold.

However:

```sql
SELECT store_id, sold_at, note
FROM sales
WHERE store_id = 42;
```

`note` is not in the index. With **this index**, PostgreSQL must fetch `note` from the heap or choose a different plan. The `(store_id, sold_at)` index cannot serve a query returning `note` index-only.

### 5.1. Columns in WHERE Must Also Be Considered

If a query reads `note` only for filtering:

```sql
SELECT store_id, sold_at
FROM sales
WHERE store_id = 42
  AND note = 'urgent';
```

then `(store_id, sold_at)` does not contain `note` to check that predicate. The planner must visit the heap or pick another execution strategy.

### 5.2. ORDER BY and Expressions Also Matter

Account for columns used in:

- `SELECT`.
- `WHERE`.
- `ORDER BY`.
- Other expressions/predicates the execution node must evaluate.

An index "containing the SELECT columns" yet missing a filter/sort column may still fail to enable a purely index-only plan for that query.

### 5.3. Not Every Index Access Method Supports Index-Only Scans

B-tree is the canonical example supporting index-only scans because it stores exact key values.

Other index access methods vary:

- Certain GiST/SP-GiST operator classes can support it.
- GIN generally cannot serve index-only scans the way B-tree does, because its entries do not reconstruct full original row values as needed.
- Actual capability depends on access method, operator class, and PostgreSQL version.

Do not assume "having any index" lets the planner pick Index Only Scan.

## 6. Condition 2: Plan Cost Must Be Competitive

Even when an index covers all columns and B-tree supports index-only scans, PostgreSQL is **not forced** to use it.

The planner estimates:

- How many rows will likely match the predicate?
- How are they distributed across index and heap?
- What fraction of heap pages are expected to be all-visible?
- How many index entries must be read?
- Index scan cost vs Seq Scan or Bitmap Scan?
- Is a Sort required?
- Does `LIMIT` enable early stop?
- Does another plan leverage an index better?

Example:

```sql
SELECT COUNT(*)
FROM sales;
```

Even if an index could enumerate entries, a Seq Scan or parallel scan can still be cheaper when counting most of the table.

### 6.1. All-Visible Ratio Is a Cost Factor

If most heap pages are all-visible, Index Only Scan can skip most heap fetches. If continuous UPDATEs strip VM bits, the planner may anticipate frequent heap checks and pick a different plan.

A plan chosen when a table is read-mostly can differ from the plan chosen under heavy write load.

## 7. Preparing an Independent Lab Environment

The following examples use a dedicated `ios270` schema in a test PostgreSQL database. They **create tables, indexes, and modify data**, so never run them in production.

### 7.1. Create the sales Table

```sql
CREATE SCHEMA IF NOT EXISTS ios270;

CREATE TABLE ios270.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id integer NOT NULL,
    sold_at timestamptz NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    note text NOT NULL DEFAULT ''
);
```

### 7.2. Generate Data Spanning Many Heap Pages

```sql
INSERT INTO ios270.sales (
    store_id, sold_at, amount_cents, status, note
)
SELECT
    (g.n % 1000) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 180) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    (g.n % 5000 + 1)::bigint * 100,
    CASE
        WHEN g.n % 10 IN (0, 1) THEN 'CANCELLED'
        WHEN g.n % 10 IN (2, 3, 4) THEN 'PAID'
        ELSE 'NEW'
    END,
    repeat('x', 120)
FROM generate_series(1, 200000) AS g(n);
```

The dataset contains 200,000 sales distributed across 1,000 store IDs. `note` is intentionally wide so the table spans plenty of pages, making heap read costs easier to observe.

Notes:

- Run the INSERT only once on an empty fixture; running again adds another 200,000 rows.
- Rows with `store_id=42` are targeted by predicates in subsequent examples.
- Timestamps, row counts, and distribution percentages are simulated data.
- In real environments, exact execution plans and fetch counts are not guaranteed to match fixed numbers.

### 7.3. Create a Composite Covering Index with Payload

```sql
CREATE INDEX idx_ios270_sales_store_time_cover
ON ios270.sales (
    store_id,
    sold_at DESC,
    sale_id DESC
)
INCLUDE (amount_cents, status);
```

The index stores:

- **Key columns:** `store_id`, `sold_at`, `sale_id`.
- **INCLUDE payload:** `amount_cents`, `status`.

The `note` column is intentionally **excluded from the index**.

### 7.4. Update Statistics

```sql
ANALYZE ios270.sales;
```

`ANALYZE` helps the planner estimate data. It **does not mean all heap pages are marked all-visible**. A later step runs `VACUUM` separately.

### 7.5. Study Query

```sql
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
  AND sold_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND sold_at <  TIMESTAMPTZ '2026-06-01 00:00:00+00'
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

Filter, sort, and returned columns are all present in the index. This index is a **candidate** for Index Only Scan; what the planner actually chooses depends on your environment.

### 7.6. Verify Data Counts

```sql
SELECT COUNT(*) AS total_sales
FROM ios270.sales;

SELECT COUNT(*) AS store_42_sales
FROM ios270.sales
WHERE store_id = 42;
```

If inserted once, `total_sales` is 200,000 and `store_42_sales` is expected to be around 200. Do not assume these simulated numbers apply to a pre-existing database.

## 8. Reading EXPLAIN (ANALYZE, BUFFERS)

Run the query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
  AND sold_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND sold_at <  TIMESTAMPTZ '2026-06-01 00:00:00+00'
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

An **illustrative** plan shape, not an actual run log:

```text
Limit  (cost=... rows=50 ...)
  (actual time=... rows=50 loops=1)
  -> Index Only Scan using idx_ios270_sales_store_time_cover
       on sales
       (cost=... rows=...)
       (actual time=... rows=50 loops=1)
       Index Cond: ((store_id = 42) AND (...))
       Heap Fetches: 0
       Buffers: shared hit=... read=...
Planning Time: ...
Execution Time: ...
```

In another environment, you might see `Index Scan`, `Bitmap Heap Scan`, or different Heap Fetches numbers. This lesson does not assume a specific PostgreSQL run produced those exact figures.

### 8.1. Index Only Scan

`Index Only Scan using idx_ios270_sales_store_time_cover` shows the executor uses that index to retrieve needed column values, checking the VM/heap when necessary.

### 8.2. Index Cond

`Index Cond` shows the predicates the index node uses during index lookup/traversal. Here, equality on `store_id` plus a range on `sold_at` aligns with index key order.

### 8.3. Heap Fetches

`Heap Fetches: 0` means that during execution of this Index Only Scan node, PostgreSQL **did not need to visit the heap to check visibility for the processed index entries**.

If `Heap Fetches: 50`, it had to check the heap for visibility 50 times during node execution.

This is **not**:

- Count of unique physical heap pages read.
- Count of disk I/O operations.
- Count of returned rows.
- Total index entries read under every count.
- An index "error count."

### 8.4. Buffers

`Buffers: shared hit=... read=...` shows buffer accesses across categories like shared hit/read. Hits mean blocks were already in buffer cache—**not zero CPU or visibility-check work**.

An Index Only Scan may still read:

- Index pages.
- Visibility map pages.
- Heap pages when the VM does not confirm all-visible.

Therefore, even when `Heap Fetches=0`, the query **still reads index and visibility map pages**; it is not a "zero-page-read" query.

### 8.5. Actual Rows and Loops

`actual rows` is the rows returned by the node to its parent per EXPLAIN's reporting rules; `loops` is the number of node invocations. When a node runs multiple times, EXPLAIN's per-loop averages and totals must be interpreted carefully for each metric.

Do not assume a fixed ratio between `Heap Fetches` and `Limit` rows.

## 9. Does Heap Fetches Equal Heap Pages Read?

**No.** That is a very common misconception.

Suppose 100 index entries point to tuples residing on **the exact same heap page**, and that page's VM bit is not all-visible.

The executor may have to verify visibility for many tuples on that single page. Thus:

```text
Heap Fetches: 100
```

does not mean 100 **distinct** heap pages were read from disk. One heap page can be brought into shared buffers and accessed repeatedly.

Conversely, a query reading many index/VM pages can still report:

```text
Heap Fetches: 0
Buffers: shared hit=... read=...
```

### 9.1. Interpretation Examples

| Scenario | Heap Fetches | Interpretation |
|---|---:|---|
| 50 tuples from all-visible pages | 0 | No heap visits needed for visibility |
| 50 tuples from non-all-visible pages | Up to 50 or more depending on path | Heap checks performed for visibility |
| 1,000 tuples on 20 non-all-visible heap pages | Could be hundreds/thousands | Does not mean that many distinct physical pages |
| 10 rows returned, node checked extra candidates | Can exceed 10 | Fetches is not output row count |
| Index Only Scan inside a Nested Loop | Accumulates across calls | Inspect loops and full plan structure |

These figures are **hypothetical scenarios**, not actual measurements.

### 9.2. Why Can Heap Fetches Exceed Returned Rows?

The node might inspect extra candidates before filtering, sit beneath a `LIMIT`, or execute repeatedly in a Nested Loop. Heap visibility checks can outnumber final query rows.

An index entry pointing to a tuple version invisible to the current snapshot still forces a heap check while **returning zero result rows**.

## 10. Experiment A: After INSERT, Before VACUUM

After loading data and creating the index, run:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

**What to observe:**

- Did the planner pick Index Only Scan?
- If yes, what is `Heap Fetches`?
- What are Buffers hit/read?
- What are actual runtime and actual rows?

Right after a large INSERT, many pages may not yet be marked all-visible. Hence Index Only Scan **may** show substantial Heap Fetches.

However, if autovacuum already ran, other transactions ran, or the planner chose another node, results can differ. This is an observational experiment, **not a test requiring positive Heap Fetches every time**.

### 10.1. Why Doesn't CREATE INDEX Automatically Mark the VM All-Visible?

`CREATE INDEX` builds the index structure, yet does not prove all heap pages are all-visible to active snapshots. All-visible tracking has its own lifecycle, managed mainly by VACUUM and MVCC visibility rules.

### 10.2. Does ANALYZE Replace VACUUM?

No. `ANALYZE` collects planner statistics. `VACUUM` handles tuple cleanup and visibility map maintenance.

An index with fresh statistics **can still incur heavy heap fetches** if pages are not all-visible.

## 11. Experiment B: VACUUM ANALYZE and Re-Measure

After the INSERT transaction commits and ensuring you are in the lab environment, run standalone:

```sql
VACUUM (ANALYZE) ios270.sales;
```

**Important:** ordinary `VACUUM` cannot run inside an explicit transaction block. Run directly in autocommit mode during practice; do not write:

```sql
BEGIN;
VACUUM ios270.sales;
COMMIT;
```

expecting VACUUM to run inside a transaction.

After VACUUM:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

### 11.1. What Can Change?

If VACUUM marks the heap pages holding matching tuples as **all-visible**, an Index Only Scan may report `Heap Fetches: 0` or a sharp drop.

Under the same plan, same data, and an updated VM, reducing heap fetches usually cuts tuple-verification work.

### 11.2. Do Not Treat Speed Changes as Sole Proof

The second run might be faster because:

- Data/index pages are now warm in buffer cache.
- The visibility map improved.
- Updated statistics altered the plan.
- Background system load dropped.
- Heap/index pages were touched by another task.

To analyze properly, inspect together:

- Node type.
- `Heap Fetches`.
- `Buffers`.
- `actual rows`.
- `Execution Time`.
- Data/transaction and cache state.

### 11.3. What If Heap Fetches Stays High?

Possible reasons:

- An old transaction holding an open snapshot prevents pages from becoming all-visible.
- New DML occurred after VACUUM.
- VACUUM could not mark every page.
- The planner or execution path differed from expectations.
- The query touches pages that are frequently modified.

Do not conclude VACUUM is broken from a single number. Check MVCC state, VM, and live write activity.

## 12. Experiment C: Updating a Column Outside the Index

This is a key insight: **you do not need to modify an indexed key to impact Index Only Scan**.

After VACUUM and baseline measurement, run:

```sql
UPDATE ios270.sales
SET note = note || ' reviewed'
WHERE store_id = 42;
```

`note` is **not** in `idx_ios270_sales_store_time_cover`. From the perspective of columns needed by our SELECT query, all key and payload values stayed identical.

However, the UPDATE modified tuple versions in the heap. Affected heap pages lose their **all-visible** bit in the VM.

Re-measure:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

If the planner still picks Index Only Scan, `Heap Fetches` **can rise** compared to right after VACUUM, because the VM no longer certifies those pages as all-visible.

### 12.1. Why Is This Such an Important Lesson?

Someone might argue:

> "We only updated `note`, while `sale_id`, `sold_at`, `status`, and `amount_cents` stayed unchanged. The index still holds every queried column, so no heap visit is needed."

That argument misses one step: **heap row-version visibility changed**. The index-only scan must check the heap to avoid returning an obsolete or invalid version.

### 12.2. Does a HOT Update Eliminate Heap Fetches?

PostgreSQL performs **HOT (Heap-Only Tuple)** updates when eligible, avoiding new index entries when no indexed columns change and free space exists on the same page.

However:

- HOT optimizes **write / index maintenance paths**.
- It **does not guarantee** the heap page keeps its all-visible bit after UPDATE.
- An index-only scan still has to visit the heap for visibility checks on modified pages.
- The planner may also switch away from Index Only Scan if statistics/costs shift.

Thus "UPDATE can be HOT" does **not** mean "Index Only Scan always keeps Heap Fetches = 0."

### 12.3. Run VACUUM Again Afterward

Once relevant transactions finish and no new writes touch those pages:

```sql
VACUUM (ANALYZE) ios270.sales;
```

Re-run EXPLAIN. If pages qualify as all-visible again, Heap Fetches can drop back down.

**Illustrative timeline:**

```text
INSERT 200,000 rows
    |
    v
Many pages not yet all-visible
    |
    v
VACUUM
    |
    v
Many pages marked all-visible
    |
    v
Index Only Scan can see low / 0 Heap Fetches
    |
    v
UPDATE note for store 42
    |
    v
Affected pages lose all-visible bit
    |
    v
Index Only Scan can see higher Heap Fetches
    |
    v
VACUUM when eligible
    |
    v
All-visible can be re-established
```

This is a design behavior to observe, not a promise that every PostgreSQL server outputs exact matching numbers at every step.

## 13. Experiment D: Updating a Column Inside the Index

Now consider:

```sql
UPDATE ios270.sales
SET status = 'PAID'
WHERE store_id = 42
  AND status = 'NEW';
```

Unlike updating `note`, `status` is **INCLUDE**d in the index. Changing `status` requires maintaining index entries carrying the new payload.

Potential consequences:

- Higher write/WAL volume and index maintenance cost.
- MVCC creates new row versions.
- Affected heap pages lose all-visible status.
- Subsequent Index Only Scans may incur heap fetches.
- HOT updates are generally blocked when a column referenced by an index changes, even an `INCLUDE` column.

### 13.1. INCLUDE Is Not Free on UPDATE

An `INCLUDE` column does not guide B-tree key ordering, yet it **still lives inside the index tuple**. When that payload value changes, the index must be updated accordingly.

A `status` column that mutates constantly can make a wide covering index costlier on writes than the heap reads it saves under write-heavy workloads.

### 13.2. Measuring Write Performance Properly

Beyond `EXPLAIN SELECT`, when evaluating `INCLUDE`, measure:

- UPDATE/INSERT latency.
- WAL generation.
- Index size.
- HOT update ratio.
- Autovacuum work.
- Read-query Heap Fetches.
- Overall throughput under concurrency.

Do not add `INCLUDE` columns merely to make one isolated SELECT's plan look cleaner.

## 14. Why VACUUM Sometimes Cannot Mark Pages All-Visible

A heap page becomes all-visible when PostgreSQL can verify all relevant tuples on it are visible to all transactions; this depends on commit status and active snapshots.

Notable situations:

### 14.1. Uncommitted Write Transactions

If transaction A just INSERTed/UPDATEd without committing, PostgreSQL cannot treat uncommitted tuple versions as visible to everyone.

### 14.2. Long-Running Transactions Holding Old Snapshots

A long-running read transaction may still need older row versions. Version cleanup and visibility marking can be held back by that old transaction horizon.

### 14.3. Continuous DML

A page just marked all-visible by VACUUM can immediately lose its bit from a subsequent UPDATE. On hot write tables, the all-visible percentage fluctuates constantly.

### 14.4. VACUUM Has Not Scanned/Marked Every Page

VACUUM follows operational rules, page-skipping optimizations, and data-state constraints. Never assume a finished "VACUUM" guarantees 100% all-visible pages.

### 14.5. Replicas and Long-Running Snapshots

Replication feedback or long-lived snapshots can affect tuple cleanup lifecycles in certain configurations. When diagnosing production, examine active transactions and replication context rather than assuming "missing VACUUM."

## 15. Inspecting All-Visible Ratio from pg_class

You can view catalog/estimated metrics for a heap relation:

```sql
SELECT
    c.relname,
    c.relpages,
    c.relallvisible,
    ROUND(
        100.0 * c.relallvisible
        / NULLIF(c.relpages, 0),
        2
    ) AS pct_pages_all_visible_estimate
FROM pg_class AS c
WHERE c.oid = 'ios270.sales'::regclass;
```

Columns:

- `relpages`: recorded/estimated heap pages in relation statistics.
- `relallvisible`: pages recorded as all-visible for the planner.
- Percentage: an **estimate** helping explain why the planner expects index-only scans to help or not.

### 15.1. relallvisible Is Not Heap Fetches

`relallvisible` describes **pages across the entire relation**, whereas `Heap Fetches` measures runtime heap checks **in a specific execution node**.

Two different scopes:

```text
relallvisible:
    describes table-wide pages per catalog/estimates

Heap Fetches:
    describes runtime work inside one Index Only Scan
```

Never compute:

```text
Heap Fetches = relpages - relallvisible
```

That formula is **wrong**. One non-all-visible page might hold dozens of matching entries, or zero entries matching the query.

### 15.2. Catalog Numbers Can Lag

`relpages`/`relallvisible` are not microsecond-accurate live counters. They serve planner estimation and update via operations like VACUUM/ANALYZE.

To inspect exact VM bits directly, use a dedicated extension if permissions allow.

## 16. Inspecting the Visibility Map with pg_visibility

PostgreSQL provides the **`pg_visibility`** extension to inspect a relation's visibility map and page visibility.

In a lab with appropriate privileges:

```sql
CREATE EXTENSION IF NOT EXISTS pg_visibility;
```

Then query:

```sql
SELECT
    COUNT(*) AS heap_pages_in_map,
    COUNT(*) FILTER (WHERE all_visible)
        AS all_visible_pages,
    COUNT(*) FILTER (WHERE NOT all_visible)
        AS not_all_visible_pages,
    COUNT(*) FILTER (WHERE all_frozen)
        AS all_frozen_pages
FROM pg_visibility_map('ios270.sales'::regclass);
```

`pg_visibility_map(regclass)` returns per-block info including `blkno`, `all_visible`, and `all_frozen` where supported.

### 16.1. If You Lack CREATE EXTENSION Privileges

Never alter production permissions or request superuser privileges just to run an example. Rely on `pg_class.relallvisible`, `EXPLAIN`, statistics views, and DBA assistance when needed.

### 16.2. Do Not Use pg_visibility to "Fix" the VM

`pg_visibility` is primarily an **inspection/diagnostic tool**, not a VACUUM substitute.

When many pages lack all-visible, investigate root causes: write activity, long transactions, vacuum scheduling, or snapshot retention—do not blindly force maintenance commands.

### 16.3. Observing Before and After UPDATE

Practice sequence:

1. Run VACUUM.
2. Read `all_visible_pages`.
3. Run UPDATE on `store_id=42`.
4. Read again.
5. Run EXPLAIN and compare Heap Fetches.
6. Run VACUUM once all relevant transactions finish.
7. Read VM and EXPLAIN again.

Do not expect `all_visible_pages` to drop by **the exact count of updated rows**. The VM is per-page, and one page holds many rows.

## 17. Where Do Index Scan and Index Only Scan Differ in a Plan?

The same logical query can appear in two forms:

**Index Scan form:**

```text
Index Scan using idx_ios270_sales_store_time_cover on sales
  Index Cond: (store_id = 42)
```

**Index Only Scan form:**

```text
Index Only Scan using idx_ios270_sales_store_time_cover on sales
  Index Cond: (store_id = 42)
  Heap Fetches: 0
```

In Index Scan, PostgreSQL uses the index to find rows and fetches data/visibility from the heap per node mechanics. Index Only Scan aims to fetch column values from the index and consults the VM to decide whether heap checks can be skipped.

### 17.1. Never Compare Out of Context

Do not just look at:

```text
Index Scan 30 ms
Index Only Scan 40 ms
```

and declare Index Only Scan slower. Verify:

- Were the queries truly identical?
- Were row counts identical?
- Did data change?
- Were cache/buffers comparable?
- Did Sort/Nested Loop/parallel workers differ?
- Did all-visible ratios and Heap Fetches differ?
- Were plans chosen under identical statistics and settings?

### 17.2. When Can Index Scan Be Faster?

Index Scan is chosen when unindexed columns must be fetched, or when the planner estimates direct heap access costs less than the available Index Only Scan.

"Index Only" is an **execution strategy**, not a runtime speed guarantee.

## 18. Adding SELECT *: Accidentally Breaking a Covering Index

Suppose the query is:

```sql
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

The index covers every needed column.

Change it to:

```sql
SELECT *
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

Now `*` includes `note`, which is absent from the index. Thus **that index no longer covers the query**. PostgreSQL switches to Index Scan or another plan to fetch `note`.

### 18.1. SELECT * Also Hurts Beyond Indexing

Beyond losing index-only capability:

- Sends more bytes over the network.
- Couples code to schema changes when columns are added.
- Raises driver decode/serialization cost.
- Risks exposing sensitive columns via APIs.

Always project only the columns your application genuinely uses.

### 18.2. Yet Never Drop Needed Columns Just to Get Index Only Scan

If business logic needs `note`, the query must return accurate data. Options:

- `INCLUDE(note)` if `note` is small, rarely updated, and the query is critical.
- Restructure queries around actual workload needs.
- Accept Index Scan when heap access is already plenty fast.

Optimization must never compromise result correctness.

## 19. INCLUDE: What Benefit Do Payload Columns Bring?

A B-tree index can be declared as:

```sql
CREATE INDEX idx_example
ON some_table (key_a, key_b)
INCLUDE (payload_c);
```

Here:

- `key_a` and `key_b` govern **B-tree ordering and searching**.
- `payload_c` is stored in the index tuple so values can be returned without reading the heap when the VM allows.
- `payload_c` is not a key column for bounding range scans along B-tree order.
- On unique indexes, uniqueness applies strictly to **key columns**, not `INCLUDE` payloads.

### 19.1. Store and Time Query Example

```sql
CREATE INDEX idx_ios270_sales_store_time_cover
ON ios270.sales (
    store_id,
    sold_at DESC,
    sale_id DESC
)
INCLUDE (amount_cents, status);
```

For the store query:

```sql
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50
```

the index has matching keys and carries the needed payload.

### 19.2. What If WHERE Filters Only on amount_cents?

```sql
SELECT sale_id, amount_cents
FROM ios270.sales
WHERE amount_cents > 100000;
```

In the current index, `amount_cents` is an `INCLUDE` column, not a leading key. PostgreSQL cannot treat it as a B-tree-ordered key to jump directly to the `> 100000` range.

If that query pattern is frequent, you need a different index keyed on `amount_cents` or an appropriate key tuple.

### 19.3. Large Payloads Carry Risks

An index `INCLUDE`ing large columns can:

- Inflate index size dramatically.
- Pack fewer index entries per page.
- Increase WAL and INSERT/UPDATE overhead.
- Trigger index-tuple size limit errors on oversized values.
- Restrict B-tree deduplication when non-key columns are present.

Do not `INCLUDE` a long `note` column solely to chase `Heap Fetches=0` on a rarely used dashboard.

## 20. MVCC, HOT Updates, and the Visibility Map

Two concepts often confused:

**HOT (Heap-Only Tuple)** optimizes updates by skipping new index entries when eligible.

**All-visible** marks that tuples on a heap page need no separate visibility checks during index-only scans.

### 20.1. Example: Updating note

```sql
UPDATE ios270.sales
SET note = 'checked'
WHERE sale_id = 100;
```

If `note` is unindexed and free space exists on the heap page, a HOT update is possible. Even though index entries are untouched thanks to HOT:

- The heap tuple still changed.
- The page's VM all-visible bit is cleared.
- An Index Only Scan touching related rows must read the heap for visibility.

### 20.2. Updating status Inside INCLUDE

```sql
UPDATE ios270.sales
SET status = 'PAID'
WHERE sale_id = 100;
```

Because `status` is `INCLUDE`d, it is referenced by the index. Updating it requires index maintenance and generally prevents HOT when `status` actually changes.

### 20.3. Why Can Impact Spill Over to Many Queries?

One heap page stores many rows. Modifying one row clears the page's all-visible bit, forcing index-only scans for completely different rows on that same page to check the heap too.

Thus table UPDATE rate and physical row clustering affect index-only efficiency well beyond the specific rows being updated.

## 21. HOT Statistics and Write Activity

Check aggregate statistics in `pg_stat_user_tables`:

```sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'ios270'
  AND relname = 'sales';
```

Interpretation:

- `n_tup_upd`: recorded tuple updates.
- `n_tup_hot_upd`: updates recorded as HOT.
- `n_dead_tup`: estimated dead tuples.
- `last_vacuum`/`last_autovacuum`: timestamps of last VACUUM runs.
- `last_analyze`/`last_autoanalyze`: timestamps of last statistics collections.

### 21.1. HOT Ratio Does Not Directly Determine Heap Fetches

A table with a high HOT ratio can still have many non-all-visible pages under continuous updates.

Conversely, a near read-only table can achieve super-efficient Index Only Scans even if historical loads involved non-HOT updates.

Examine both metrics together to understand **writes/index maintenance** and **reads/visibility**, without expecting a simple formula converting `n_tup_hot_upd` into `Heap Fetches`.

### 21.2. Counters Have Reset Timestamps

Do not infer update rates from cumulative counters without checking when stats were last reset. Monitoring should compute deltas over time tied to workload.

## 22. VACUUM, Autovacuum, and Maintenance Work

### 22.1. Two Key Tasks VACUUM Performs for This Topic

- Reclaims/cleans dead tuples for space reuse under MVCC rules.
- Updates the visibility map, setting `all-visible` when safe.

Consequently, a quiet table after VACUUM maintains a high all-visible ratio, ideal for Index Only Scans.

### 22.2. Autovacuum

PostgreSQL runs autovacuum automatically based on thresholds and configuration. Thus in production, shifts in `Heap Fetches` often correlate with background autovacuum runs not initiated by the application.

Never disable autovacuum to "stabilize benchmarks"; disabling or misconfiguring it causes dead-tuple bloat, transaction ID wraparound risks, and severe operational hazards.

### 22.3. When a Table Has Heavy Writes

Autovacuum marks pages all-visible, yet subsequent UPDATEs clear the bits again. A hot table can stay low on all-visible pages even with healthy autovacuum.

In such workloads, huge covering indexes rarely pay off. Measure actual write costs and heap fetches.

### 22.4. Is VACUUM FULL the Way to "Achieve Index Only Scan"?

`VACUUM FULL` rewrites the table with heavy locking and is not a routine tool for lowering Heap Fetches. In production it blocks concurrent traffic and requires careful maintenance planning.

To maintain the VM normally, tune VACUUM/autovacuum first—never run VACUUM FULL solely for a prettier plan node.

## 23. Heap Fetches and Buffer Cache

Question:

> If `Heap Fetches: 1000` yet `Buffers: shared read=0`, is there a performance problem?

The heap pages were likely already cached in shared buffers, avoiding disk reads. Still, the executor performed 1,000 heap visibility checks, consuming CPU and buffer-pinning operations.

### 23.1. Hit Does Not Mean Free

`shared hit` means PostgreSQL found the block in shared buffer cache. It still consumes CPU work, though usually far cheaper than slow storage read I/O.

### 23.2. Heap Fetches Alone Does Not Measure Total I/O

A query with `Heap Fetches=0` still reads index pages and VM pages. If uncached, disk reads still occur.

A query with high Heap Fetches yet mostly shared hits can run fast when cache is warm.

Measure together:

- `Heap Fetches`.
- `Buffers`.
- `Execution Time`.
- Row counts and loops.
- Execution frequency in workload.
- Storage/cache characteristics.

### 23.3. Cold vs Warm Cache Testing

Never drop OS caches or restart production just to compare runs. Run queries repeatedly in the lab, observe buffer hit trends across runs, and explicitly document cache state and environment.

## 24. Heap Fetches Inside a Nested Loop

An `Index Only Scan` can sit inside a `Nested Loop`:

```text
Nested Loop
  -> Seq Scan on stores
  -> Index Only Scan on sales
       Index Cond: (store_id = stores.store_id)
       Heap Fetches: ...
```

In that structure, the index node runs once per outer `store_id`.

### 24.1. Why Do Loops Matter?

If the inner node runs 100 times, EXPLAIN's displayed rows and timings follow per-loop averaging/summary rules. Do not read every number as if the node executed once.

`Heap Fetches` reflects heap checks performed by that node across execution, accumulating over repeated probes.

### 24.2. Rows Queried Repeatedly

If inner probes repeatedly hit index entries pointing to the same non-all-visible heap pages, visibility checks repeat too. Having the page cached does not eliminate the heap check.

### 24.3. Tuning May Mean Reducing Probes

In some workloads, improving join cardinality, shrinking outer rows, picking a different join method, or tightening access predicates delivers far more benefit than chasing `Heap Fetches = 0`.

## 25. Can SELECT COUNT(*) Use Index Only Scan?

Yes, if an eligible index matches the condition and the planner estimates it is cheaper.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM ios270.sales
WHERE store_id = 42;
```

The SELECT returns **one COUNT row**, yet the executor must inspect all matching index entries. If the VM is not all-visible, `Heap Fetches` can far exceed 1.

### 25.1. COUNT(*) Is Not Instant Metadata Without Scanning

For an MVCC PostgreSQL table, an exact `COUNT(*)` must count rows visible to the current snapshot. The database cannot simply read one global row-count number and return it for every transaction.

An index-only scan reduces heap I/O, yet **still scans matching index entries and verifies visibility**.

### 25.2. Full-Table COUNT(*)

```sql
SELECT COUNT(*)
FROM ios270.sales;
```

The planner may choose Seq Scan, Parallel Seq Scan, Index Only Scan, or another plan based on cost. Never assume having a PRIMARY KEY index guarantees full-table `COUNT(*)` runs index-only.

## 26. Partial Indexes and Index Only Scan

Consider an index solely for PAID orders:

```sql
CREATE INDEX idx_ios270_sales_paid_time
ON ios270.sales(store_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents)
WHERE status = 'PAID';
```

Query:

```sql
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE status = 'PAID'
  AND store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Because the query specifies `status='PAID'`, the planner can consider the partial index once it proves the query only asks for rows inside the index. Returned columns are also present in the index.

### 26.1. Why Not Assume the Planner Always Picks the Partial Index?

- The query predicate must imply the index predicate.
- A prepared statement using a generic plan may not prove the predicate for parameterized status values.
- Data/query may lack selectivity.
- Another index may cost less.
- A low all-visible ratio reduces index-only benefit.

### 26.2. A Partial Index Does Not Hold All Table Data

This index only holds `status='PAID'` rows. Queries seeking NEW or CANCELLED rows cannot read this partial index to satisfy full results.

### 26.3. Partial Indexes and Status Updates

If a sale transitions from NEW to PAID or back, it enters/leaves the partial index, incurring index maintenance; affected heap pages also lose their all-visible bit.

## 27. Expression Indexes and Covering Limits

Example:

```sql
CREATE TABLE ios270.contacts (
    contact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    display_name text NOT NULL
);

CREATE INDEX idx_ios270_contacts_lower_email
ON ios270.contacts(lower(email));
```

Query:

```sql
SELECT lower(email)
FROM ios270.contacts
WHERE lower(email) = 'an@example.test';
```

Conceptually, `lower(email)` values reside in the index. However, whether an **expression index** yields an index-only plan depends on how the planner matches expressions and underlying columns per version and expression form.

### 27.1. Do Not Assume an Expression Index Covers Original `email`

An index on `lower(email)` stores the normalized expression, not enough by itself to reconstruct **original casing of `email`**:

```sql
SELECT email, display_name
FROM ios270.contacts
WHERE lower(email) = 'an@example.test';
```

With an index holding only `lower(email)`, `email` and `display_name` require heap access or another covering strategy. If genuinely needed and worthwhile, adjust the index design without over-stuffing payloads.

### 27.2. Example Covering with INCLUDE

Where supported by version and types:

```sql
CREATE INDEX idx_ios270_contacts_lower_email_cover
ON ios270.contacts(lower(email))
INCLUDE (email, display_name);
```

This stores the original email and display name so queries needing them can be covered. It is larger, adds write cost, and still relies on the VM to avoid heap fetches.

Always verify with `EXPLAIN` on the target server whether expression indexes are used as expected.

## 28. ORDER BY, LIMIT, and Early Stop

Because B-trees are ordered, index-only scans pair naturally with top-N queries:

```sql
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 10;
```

With `(store_id, sold_at DESC, sale_id DESC) INCLUDE (amount_cents, ...)`, PostgreSQL can:

1. Locate the `store_id=42` slice.
2. Scan entries in `sold_at`/`sale_id` descending order.
3. Verify visibility via VM, visiting heap when needed.
4. Stop early once 10 rows are emitted.

### 28.1. Small LIMIT Does Not Guarantee Heap Fetches < 10

If some index entries point to tuples invisible to the snapshot or filtered by extra predicates, the executor must scan more candidates before yielding 10 rows. Heap fetches can exceed the final row count.

### 28.2. ORDER BY Can Change the Plan

If a query requests a sort order incompatible with the index, the planner may add a Sort. An index-only scan does not make arbitrary sort orders free.

### 28.3. Pagination and Keysets

Example:

```sql
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE store_id = 42
  AND (sold_at, sale_id) <
      (TIMESTAMPTZ '2026-05-01 12:00:00+00', 10000)
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Tuple comparison can walk the B-tree directly for keyset pagination. Cursor values must come from the previous page's last row; the literals above are just examples.

Index-only execution still depends on heap pages being all-visible.

## 29. Impact of RLS and Read Permissions

When PostgreSQL enables **Row-Level Security (RLS)**, visible/editable rows depend on policies per role. Index-only scans cannot bypass permission or policy checks.

Multi-tenant example:

```text
tenant_id, sale_id, sold_at, amount_cents
```

Query reading only the current tenant:

```sql
SELECT sale_id, sold_at, amount_cents
FROM tenant_sales
WHERE tenant_id = :authenticated_tenant_id
ORDER BY sold_at DESC
LIMIT 20;
```

The placeholder above is application syntax, not direct `psql` parameter syntax.

### 29.1. Indexing for the Tenant Scope

An index such as:

```sql
CREATE INDEX ...
ON tenant_sales(tenant_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents);
```

works well because `tenant_id` leads, matching equality filtering plus time ordering.

### 29.2. Never Substitute Indexes for Security

Indexes are access structures; they do not enforce which tenant may view which rows. RLS, SQL privileges, and trusted tenant context must still be designed properly.

If an RLS policy evaluates additional columns/expressions, the planner may choose a different plan or lose index-only coverage.

## 30. Index Only Scan in Java/JDBC

Java applications do not request a specific scan node type. They send SQL; the PostgreSQL planner chooses the plan.

JDBC example:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class RecentSaleRepository {
    public record Sale(
        long id,
        OffsetDateTime soldAt,
        long amountCents,
        String status
    ) {}

    public List<Sale> findRecentByStore(
            Connection connection,
            int storeId,
            int limit) throws SQLException {

        if (limit <= 0 || limit > 500) {
            throw new IllegalArgumentException("limit out of range");
        }

        String sql = """
            SELECT sale_id, sold_at, amount_cents, status
            FROM ios270.sales
            WHERE store_id = ?
            ORDER BY sold_at DESC, sale_id DESC
            LIMIT ?
            """;

        List<Sale> result = new ArrayList<>();

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setInt(1, storeId);
            ps.setInt(2, limit);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(new Sale(
                        rs.getLong("sale_id"),
                        rs.getObject(
                            "sold_at", OffsetDateTime.class),
                        rs.getLong("amount_cents"),
                        rs.getString("status")
                    ));
                }
            }
        }

        return result;
    }
}
```

Key points:

- Query **explicitly lists needed columns**, avoiding `SELECT *`.
- `WHERE store_id=?` and `ORDER BY` align with sample index keys.
- `LIMIT` prevents fetching excessive data.
- The driver does not force `Index Only Scan`; verify the plan on the database.
- Index Only Scan efficiency depends on the VM, not special JDBC settings.

### 30.1. Prepared Statements and Generic Plans

PostgreSQL can plan a prepared statement using a custom or generic plan depending on execution context. If data skews sharply across stores, the optimal plan for one store can differ from another.

Do not assume `store_id = ?` always uses the same plan node or identical Heap Fetches across all parameters.

### 30.2. Do Not Optimize by Adding Unneeded Payloads

If the real API only needs `sale_id`, `sold_at`, and `amount_cents`, do not throw `status` or `note` into `INCLUDE` "just in case." Every payload column adds index maintenance cost.

## 31. Design Trade-Off: Small Index vs Covering Index?

Consider two candidate indexes:

**Index A — compact:**

```sql
CREATE INDEX idx_a
ON sales(store_id, sold_at DESC);
```

**Index B — covering:**

```sql
CREATE INDEX idx_b
ON sales(store_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents, status);
```

Comparison:

| Criterion | Index A | Index B |
|---|---|---|
| Index size | Usually smaller | Usually larger |
| Keys for store/time lookup | Yes | Yes |
| Explicit `sale_id` tie-break order | Not stored as explicit key | Yes |
| Returns amount/status from index | No | Yes |
| Index Only Scan chance when returning amount/status | None with this index | Yes |
| Cost on updating amount/status | Minimal direct impact on this index | Must maintain payload |
| Benefit when VM all-visible is high | Still visits heap for payload | Can skip many heap fetches |
| Benefit when VM all-visible is low | Index Scan fits well | Covering index still hits visibility heap fetches |

### 31.1. Do Not Decide by Counting Heap Fetches Alone

A covering index with fewer Heap Fetches yet huge size—slowing down writes and other queries—may hurt overall system health.

Evaluate:

- P95/P99 read latency.
- Query throughput.
- P95/P99 write latency.
- Storage and WAL footprint.
- Autoanalyze/vacuum behavior.
- Actual index-only hit ratio under workload.
- All-visible percentage and Heap Fetches.
- Maintainability as schema evolves.

### 31.2. One Index Cannot Serve Every Query Pattern

Queries filtering `amount_cents > ?` need `amount_cents` as a key. Queries filtering store and sorting by time need store/time keys. Queries returning `note` may accept heap visits.

Avoid building one giant index containing every column for every endpoint.

## 32. Controlled Measurement Methodology

### 32.1. Recording a Baseline

Run:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

Record:

```text
Step A: After INSERT
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:

Step B: After VACUUM
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:

Step C: After UPDATE note
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:

Step D: After second VACUUM
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:
```

### 32.2. What If the Planner Does Not Choose Index Only Scan?

That is a meaningful observation. Check first:

- Does the index cover every queried column?
- Do predicates and ORDER BY match keys?
- Is the table too small or does the query return many rows?
- Are statistics fresh?
- Does the VM have sufficient all-visible pages?
- Is another index cheaper?

In a lab, you can use planner settings **temporarily** to compare, e.g.:

```sql
BEGIN;
SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;

ROLLBACK;
```

`enable_seqscan=off` merely penalizes Seq Scan; it **does not force** Index Only Scan nor guarantee a valid index plan appears. Never flip planner flags globally in production as a permanent fix.

### 32.3. Why Shouldn't You "Benchmark" Inside a Transaction Containing VACUUM?

Regular `VACUUM` cannot run inside an explicit transaction block. Separate experiment phases:

1. Complete/commit DML.
2. Standalone VACUUM.
3. EXPLAIN SELECT.
4. Standalone UPDATE/commit.
5. EXPLAIN SELECT.

This also ensures an open test transaction does not block VACUUM from marking pages all-visible.

### 32.4. Do Not Measure from a Single Run

Buffer caches and background load cause timing variance. When validating performance, run multiple times on representative data, document environment conditions, and preserve SQL/result semantics.

**This is an observation methodology guide**, not a QA checklist or pre-executed benchmark report.

## 33. Common Misinterpretations

### Mistake 1 — "Index Only Scan means Heap Fetches must be 0"

False. Non-all-visible VM pages force the executor to check the heap for visibility.

### Mistake 2 — "I added all columns via INCLUDE, so no heap access is needed"

Insufficient. You also need access-method support, planner selection of Index Only Scan, and VM certification.

### Mistake 3 — "Heap Fetches=100 means 100 disk reads"

False. Multiple tuple checks can hit the same cached heap page in shared buffers.

### Mistake 4 — "Heap Fetches equals returned row count"

False. Visibility checks can examine unreturned candidates and accumulate across loops.

### Mistake 5 — "VACUUM always drops Heap Fetches to 0"

Not guaranteed. Concurrent DML, long transactions, ineligible pages, or plan shifts can prevent it.

### Mistake 6 — "ANALYZE updates the VM just like VACUUM"

False. ANALYZE collects statistics; VACUUM maintains dead tuples and the visibility map.

### Mistake 7 — "Updating a non-indexed column does not affect index-only scans"

False. UPDATE alters heap/MVCC state and clears the page's all-visible bit.

### Mistake 8 — "HOT updates guarantee zero heap fetches"

False. HOT optimizes index write maintenance, not all-visible persistence on modified pages.

### Mistake 9 — "Heap Fetches=0 means the query read zero pages"

False. It still reads index and VM pages, plus any data read by other nodes.

### Mistake 10 — "Buffers shared hit has zero cost"

False. Shared hits are buffer-cache accesses that still consume CPU and memory operations.

### Mistake 11 — "Index Only Scan is always faster than Index Scan"

False. Plan cost depends on data, visibility, index size, and surrounding operations.

### Mistake 12 — "Creating (a,b) INCLUDE(c) lets c power range scans"

False. `INCLUDE` payload columns do not participate in B-tree key ordering.

### Mistake 13 — "SELECT * does not affect covering indexes"

False. Including any unindexed column breaks index coverage.

### Mistake 14 — "COUNT(*) returns one row, so Heap Fetches cannot exceed 1"

False. Aggregate emits one row, while the index node beneath it may check thousands of tuples.

### Mistake 15 — "relallvisible is the maximum Heap Fetches"

False. `relallvisible` counts/estimates table-wide pages; `Heap Fetches` counts runtime visibility checks in a node.

### Mistake 16 — "Index Only Scan on expression indexes optimizes identically to regular column indexes"

Not guaranteed. Planner ability to match expressions/columns from the index varies by version and query shape.

### Mistake 17 — "A PAID partial index always serves prepared queries with status=$1"

Unlikely. The planner must prove WHERE implies the index predicate, and generic plans cannot assume `$1` is always `'PAID'`.

### Mistake 18 — "More INCLUDE columns is always better"

False. Larger indexes cost more on writes and can hinder HOT/deduplication.

### Mistake 19 — "EXPLAIN ANALYZE only predicts without executing"

False. It **executes** the query to measure. Exercise extreme caution with DML that modifies data.

### Mistake 20 — "Disable autovacuum to stabilize Heap Fetches"

False. That degrades visibility maintenance and introduces serious operational risks.

## 34. Practice Exercises with Answers

Exercises assume schema `ios270` exists. UPDATE/VACUUM commands must run only in a lab database; counts may vary if you completed earlier sections.

### Exercise 1. Does Index Only Scan Mean Zero Heap Reads Ever?

**Answer:** No. It retrieves column values from the index, yet still checks the heap for MVCC visibility whenever a heap page is not all-visible.

### Exercise 2. Why Can't an Index Entry Alone Decide Visibility?

**Answer:** Index entries lack complete transaction/version visibility metadata for snapshots; MVCC visibility lives in the heap unless the VM certifies the entire page as all-visible.

### Exercise 3. Which VM Bit Is Decisive?

**Answer:** `all-visible`. `all-frozen` serves tuple freezing and XID wraparound protection, not the requirement to skip heap reads in index-only scans.

### Exercise 4. Is the VM Per-Row or Per-Page?

**Answer:** Per heap page. Updating one row can force subsequent index-only scans on unrelated rows in that same page to check the heap.

### Exercise 5. Given Index `(store_id,sold_at)`, Can a Query Returning `note` Run Index-Only?

**Answer:** Not via that index if `note` is absent from it. It needs the heap or another index/plan.

### Exercise 6. Write a Covering Index for a Store/Time/Amount Query

```sql
CREATE INDEX idx_ios270_exercise_cover
ON ios270.sales(store_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents);
```

**Explanation:** The index holds keys for WHERE/ORDER BY and `amount_cents` to return. If the query also returns `status`, this exercise index does not cover `status`.

### Exercise 7. Query to Inspect Heap Fetches

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 25;
```

**Answer:** If the planner chooses Index Only Scan, inspect the `Heap Fetches: ...` line on that node.

### Exercise 8. If the Plan Uses Index Scan, Why Is Heap Fetches Missing?

**Answer:** `Heap Fetches` is a metric specific to `Index Only Scan`; `Index Scan` reports and accesses the heap differently, so its absence never implies zero heap access.

### Exercise 9. Why Does Heap Fetches Drop After VACUUM?

**Answer:** VACUUM marks eligible heap pages as all-visible, allowing Index Only Scan to skip per-tuple heap visibility checks on those pages.

### Exercise 10. Why Does Heap Fetches Rise Again After Updating `note`?

**Answer:** UPDATE alters heap/MVCC state and clears the all-visible bit on pages holding modified rows, even though `note` is unindexed.

### Exercise 11. Does a HOT Update Guarantee Heap Fetches Drops to 0?

**Answer:** No. HOT and the VM solve different problems.

### Exercise 12. Does Heap Fetches=500 Equal 500 Disk Reads?

**Answer:** No. Multiple tuple checks can hit the same cached page; read `BUFFERS` to understand I/O.

### Exercise 13. Can Heap Fetches=0 Have shared read=5?

**Answer:** Yes. Index and VM pages may still need to be read into buffers even with zero heap visibility checks.

### Exercise 14. How Many Rows Does COUNT(*) WHERE store_id=42 Return?

**Answer:** One COUNT row; the underlying index scan node may still process many entries and incur multiple heap fetches.

### Exercise 15. What Happens with SELECT *?

**Answer:** `note` is not in the covering index, so the index no longer covers the output; the planner must read the heap or choose another plan.

### Exercise 16. How Does INCLUDE Differ from Key Columns?

**Answer:** `INCLUDE` stores non-key payload columns not used for key ordering/searching; key columns govern B-tree positioning and sorting.

### Exercise 17. Inspecting relallvisible

```sql
SELECT relpages, relallvisible
FROM pg_class
WHERE oid = 'ios270.sales'::regclass;
```

**Answer:** Both are relation-level page metrics, not returned row counts or per-query heap fetches.

### Exercise 18. Inspecting VM via Extension

```sql
SELECT
    COUNT(*) FILTER (WHERE all_visible) AS visible_pages,
    COUNT(*) FILTER (WHERE NOT all_visible) AS other_pages
FROM pg_visibility_map('ios270.sales'::regclass);
```

**Answer:** Requires the `pg_visibility` extension installed and proper privileges; counts represent pages, not tuples.

### Exercise 19. A Page Holds 80 Tuples and One Tuple Is UPDATED—What Happens?

**Answer:** The page's all-visible bit can be cleared; index-only scans touching any of the other 79 tuples on that page may also have to check the heap.

### Exercise 20. Why Do Read-Mostly Tables Suit Index Only Scan Better?

**Answer:** Rarely modified pages stay marked all-visible by VACUUM for much longer periods.

### Exercise 21. Should You INCLUDE a Long `note` Column to Avoid All Heap Reads?

**Answer:** Not by default. The index can bloat and slow writes, while VM updates might still trigger heap reads. Measure your workload first.

### Exercise 22. Can Parallel Index Only Scan Still Have Heap Fetches?

**Answer:** Yes. Parallelism does not bypass MVCC; workers still verify visibility when pages are not all-visible.

### Exercise 23. Can a PAID-Only Partial Index Serve status='NEW' Queries?

**Answer:** No. The index only contains PAID rows and cannot supply NEW rows.

### Exercise 24. Will a Generic Prepared Plan Always Use a status='PAID' Partial Index for status=$1?

**Answer:** No. A generic plan must work for all parameter values and cannot prove `$1` is always `'PAID'`.

### Exercise 25. What If Heap Fetches Drops Yet Execution Time Increases?

**Answer:** Check buffers, cache state, plan changes, loops, rows, concurrent load, and index size; never blame Index Only Scan from two numbers alone.

### Exercise 26. Why Should VACUUM Run After COMMIT in the Lab?

**Answer:** Ordinary VACUUM cannot run inside an explicit transaction block; uncommitted work and open transactions also block VM marking.

### Exercise 27. Index Only Scan with Filter Removing Many Rows

**Answer:** The node may still read many index entries and verify visibility for discarded candidates. Inspect `Index Cond` vs `Filter`, index structure, and data rather than final row counts alone.

### Exercise 28. How Do You Prove a Covering Index Actually Benefits the System?

**Answer:** Measure `EXPLAIN (ANALYZE, BUFFERS)` and read latency on representative data while also measuring storage, WAL, update throughput, autovacuum, and impact on other queries.

### Exercise 29. Why Not Rely Solely on relallvisible?

**Answer:** It is a relation-wide estimate, whereas a query accesses a specific subset of pages; table-wide all-visible ratio may not reflect a specific `store_id` slice.

### Exercise 30. Options When Continuous UPDATEs Keep Heap Fetches High?

**Answer:** Re-evaluate whether a covering index pays off, trim payload/update costs, tune maintenance for live data patterns, or separate read-mostly from hot data where business rules permit—never force Index Only Scan at all costs.

## 35. Quick Diagnostic Flowchart

```text
Query slow or still reading heap heavily
                |
                v
        EXPLAIN (ANALYZE, BUFFERS)
                |
         +------+-------+
         |              |
      Index Only     Not using
         Scan        Index Only
         |              |
         v              v
    Heap Fetches?    Are query columns/expressions
         |           all present in the index?
    +----+----+         |
    |         |         +-- No --> consider index/keys/INCLUDE
    0        High       |
    |         |         +-- Yes --> check planner costs,
    |         v                     selectivity, statistics,
    |    VM all-visible?            ORDER BY, index method
    |         |
    |    +----+----+
    |    |         |
    |   Low       High table-wide
    |    |         |
    |    v         v
    |  Check DML activity,    Does query hit specific
    |  long transactions,     skewed pages? Do stats
    |  VACUUM/autovacuum      reflect reality?
    |         |
    +---------+
              |
              v
    Compare rows, loops, BUFFERS,
    latency, caching, and write cost
              |
              v
    Optimize for the overall workload,
    not a single EXPLAIN line
```

## 36. Practical Checklist for Tuning Index Only Scan

| Question | Why check it? |
|---|---|
| Does the query actually need every SELECTed column? | `SELECT *` breaks covering indexes |
| Does the B-tree index hold all keys/payloads? | Missing columns force heap reads |
| Do key columns align with WHERE/ORDER BY? | Enables seeking and early stop |
| Is INCLUDE too large or updated too often? | Write cost and index bloat |
| Did the planner choose Index Only Scan? | Technical eligibility does not guarantee selection |
| What is Heap Fetches? | Measures actual heap visibility checks |
| How does Heap Fetches shift after VACUUM/UPDATE? | Evaluates visibility map impact |
| What do `relallvisible` and VM show? | Gauges all-visible page ratio |
| Are long-running transactions active? | Can block cleanup and VM marking |
| Did HOT update rate change after INCLUDE? | Index maintenance trade-off |
| What are shared hit/read Buffers? | Never equate fetches directly with disk reads |
| Does the query have many loops? | Avoid confusing per-loop vs total fetches/rows |
| Is the cache warm or cold? | Avoid skewed timing conclusions |
| Are statistics fresh and representative? | Drives planner cost/row estimates |
| Are partial predicates or expressions involved? | Query must match index logic |
| Are RLS/tenant filters active? | Affects correctness and index coverage |
| Are you forcing planner flags (`enable_*`)? | Never use as a production fix |
| Is read latency gain worth write overhead? | Evaluate net system benefit |
| Is VACUUM/autovacuum properly tuned? | Keeps visibility and table health strong |
| Tested on realistic workloads, not tiny fixtures? | Avoid optimizing for the wrong scale |

## 37. Recommended PostgreSQL Documentation

Official references matching your server version:

- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html): Index Only Scan requirements, visibility map, INCLUDE, MVCC, and limitations.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): `EXPLAIN ANALYZE` nodes and statistics.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): VACUUM lifecycle, stats updates, dead tuples, and maintenance.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html): why multiple row versions coexist.
- [Visibility Map](https://www.postgresql.org/docs/current/storage-vm.html): visibility map storage structure.
- [pg_visibility](https://www.postgresql.org/docs/current/pgvisibility.html): inspecting the visibility map when extension/privileges allow.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): capabilities of different index access methods.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): syntax for key columns, INCLUDE, partial/expression indexes.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_user_tables` and counters.
- [HOT Updates](https://www.postgresql.org/docs/current/storage-hot.html): how HOT reduces part of index maintenance cost.

Exact capabilities and plan output vary by version. Check:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

before applying behaviors to a live system.

## 38. Summary

A good `Index Only Scan` is never simply "we put every column into the index."

It depends on a chain of conditions:

```text
Query requests only columns the index can supply
                     |
                     v
Index method/opclass supports reading values from index
                     |
                     v
Planner estimates index-only scan is cheap enough to choose
                     |
                     v
Executor reads index entry and checks VM
                     |
          +----------+-----------+
          |                      |
    all-visible = 1        all-visible = 0
          |                      |
          v                      v
   Skip heap check        Visit heap to check
    for visibility            visibility
          |                      |
          +----------+-----------+
                     |
                     v
             Return matching rows
```

Key principles to remember:

1. **Index Only Scan can still read the heap.** The node name does not guarantee `Heap Fetches: 0`.
2. **Covering indexes are a column-data requirement.** Key columns and `INCLUDE` payloads serve distinct roles.
3. **The visibility map governs skipping the heap for MVCC.** The page-level `all-visible` bit is the key.
4. **VACUUM can lower Heap Fetches**, yet active DML and open transactions can clear or block `all-visible` bits.
5. **Updating a column outside the index still impacts index-only scans** because heap visibility changes.
6. **HOT updates do not mean all-visible.** HOT optimizes index write paths, not avoiding heap visibility checks.
7. **Heap Fetches is neither heap page count nor disk read count.** Always inspect `BUFFERS`, rows, loops, and execution time.
8. **COUNT(*) returning one row does not mean only one tuple was examined.** The executor still scans matching snapshot-visible entries.
9. **Wide indexes carry maintenance costs.** Do not `INCLUDE` every column just to lower one counter.
10. **The planner remains free to choose Seq Scan/Index Scan/Bitmap Scan** when total cost favors them.
11. **Benchmarks require clear controls**: before/after VACUUM/UPDATE, identical queries, representative data, buffers/cache tracking, and write overhead.
12. **The ultimate goal is workload performance and correctness**, not a pretty-looking `EXPLAIN` plan.

**One sentence to remember:** *Index Only Scan* can retrieve column values from the index, yet only when the visibility map confirms a heap page is **all-visible** can PostgreSQL skip visiting the heap to verify row-version visibility; every time it cannot skip, **`Heap Fetches`** is the signal to read.
