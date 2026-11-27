# Sequential Scan, Index Scan, and Bitmap Scan in PostgreSQL

## 1. An Index Exists—Why Does PostgreSQL Still Scan the Entire Table?

Suppose the `events` table has 200,000 records and we created an index on the `category` column:

```sql
CREATE INDEX events_category_idx
ON scan_lab.events (category);
```

We run two queries:

```sql
-- Query A: almost all of the data.
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'standard';

-- Query B: only a relatively small subset.
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Same column, same index, yet PostgreSQL may choose:

- **`Seq Scan`** for A: sequentially reading the table's pages and checking the condition on each row.
- **`Bitmap Index Scan` + `Bitmap Heap Scan`** for B: finding matching entries via the index, grouping locations by page, and reading the needed table pages.
- Or **`Index Scan`** when the condition finds very few rows, especially when a suitable index exists and random heap reads are minimal.

Why? Because an index **is not automatically faster** than reading the table. PostgreSQL chooses a plan based on **estimated matching rows, pages to read, physical data distribution, query type, I/O and CPU costs, caching, sort requirements, and LIMIT**.

This lesson explains the three most important data access methods:

1. **Sequential scan** — reading the table sequentially.
2. **Index scan** — going from the index to the rows to read.
3. **Bitmap scan** — using an index to identify pages/rows and then reading the heap in a less random order.

These are **plan nodes** in an `EXPLAIN` tree, not three different types of SQL statements.

> **Core rule:** PostgreSQL does not ask "does this table have an index?" and blindly use it. The planner asks "among all valid plans, which plan is estimated to have the lowest total cost for the entire query?"

## 2. Learning Objectives

After this lesson, you will be able to:

1. Identify `Seq Scan`, `Index Scan`, `Index Only Scan`, `Bitmap Index Scan`, and `Bitmap Heap Scan` in `EXPLAIN`.
2. Distinguish **sequential heap access**, **index-to-heap lookup**, and **bitmap-driven heap reading**.
3. Explain **selectivity** and why queries returning many rows often do not want an index scan.
4. Read `cost`, `rows`, `width`, `actual time`, `loops`, `Buffers`, `Index Cond`, `Filter`, and `Recheck Cond` accurately.
5. Understand exact/lossy bitmaps, `Heap Blocks: exact/lossy`, and `Rows Removed by Index Recheck`.
6. Explain `BitmapAnd` / `BitmapOr` when multiple indexes exist.
7. Understand the role of `ORDER BY` and `LIMIT` in deciding to use an index scan.
8. Know when `Index Only Scan` genuinely avoids heap access via the visibility map.
9. Build a reproducible dataset and compare multiple plans in practice.
10. Distinguish **planner estimates** from **actual query execution time**.
11. Understand the impact of `ANALYZE`, data distribution statistics, correlation, `work_mem`, and cost parameters.
12. Avoid anti-patterns like forcing sequential scans off in production or indexing every column.

## 3. First: What Does PostgreSQL Read When Querying a Table?

A regular PostgreSQL table is stored as **data pages (*heap pages*)**. Each page contains tuples along with internal management metadata.

A B-tree index has its own page structure, helping locate keys stored in the index. For a standard index scan, index entries point to tuple locations in the heap.

Simplified model:

```text
                         SQL query
                            |
                         Planner
                            |
                  Choose an access path
                            |
           +----------------+----------------+
           |                |                |
           v                v                v
       Seq Scan         Index Scan        Bitmap path
           |                |                |
           v                v                v
      Heap pages       Index pages       Index pages
     read in order          |                |
                            v                v
                       Heap tuple      Bitmap of locations
                        via TID              |
                                             v
                                        Heap pages
                                      for needed set
```

### 3.1. What Is a TID?

A **tuple identifier (TID)** identifies a tuple's physical location, conceptually consisting of **block number + offset** in the heap.

B-tree index entries help reach the corresponding tuple via this location. In a regular index scan, PostgreSQL may need to access the heap to fetch columns not stored in the index and check MVCC visibility.

**Do not use TID as a business primary key.** Physical locations can change on updates or table reorganization; applications should use logical primary keys.

### 3.2. "Index" Does Not Mean Table Data Lives Inside the Index

A standard index does not store every column of the table. If a query requests:

```sql
SELECT event_id, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

and the index only covers `account_id`, PostgreSQL must go from the index to the heap to fetch `payload`.

An important exception is **Index Only Scan** when **all data needed by the query** resides in the index and visibility requirements are met. Section 14 covers this in detail.

### 3.3. A "Scan" Is Just One Node in a Larger Plan

Example:

```text
Aggregate
  -> Bitmap Heap Scan on events
       -> Bitmap Index Scan on events_category_idx
```

The engine can choose a scan path to locate rows, and upper nodes consume those rows to aggregate, join, sort, or limit.

Do not evaluate a scan node in isolation while ignoring the requirements of **the entire query**.

## 4. Preparing a Reproducible Test Database

Run only in a practice database. Inserting 200,000 rows, creating indexes, and running VACUUM consume I/O/CPU; never run arbitrarily in production.

### 4.1. Create Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS scan_lab;

CREATE TABLE scan_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id integer NOT NULL,
    category text NOT NULL,
    status text NOT NULL,
    occurred_at timestamptz NOT NULL,
    amount numeric(12,2) NOT NULL,
    payload text NOT NULL
);
```

Table columns:

- `event_id`: primary key, automatically backed by a B-tree index.
- `account_id`: account ID; multiple events share the same account.
- `category`: grouping column with strongly skewed frequencies.
- `status`: status with uneven frequency.
- `occurred_at`: event timestamp.
- `amount`: test monetary amount.
- `payload`: text column simulating heavier heap fetches.

### 4.2. Load 200,000 Rows

```sql
INSERT INTO scan_lab.events
    (
        account_id,
        category,
        status,
        occurred_at,
        amount,
        payload
    )
SELECT
    (g % 20000) + 1,
    CASE
        WHEN g % 11 = 0 THEN 'premium'
        ELSE 'standard'
    END,
    CASE
        WHEN g % 23 = 0 THEN 'FAILED'
        WHEN g % 5  = 0 THEN 'PENDING'
        ELSE 'DONE'
    END,
    timestamptz '2025-01-01 00:00:00+00'
        + (g * interval '1 minute'),
    (g % 10000)::numeric / 100,
    repeat('event-payload-', 10)
        || lpad(g::text, 7, '0')
FROM generate_series(1, 200000) AS s(g);
```

Useful properties of this dataset:

| Condition | Approximate prevalence |
| --- | ---: |
| `category = 'standard'` | About 91% |
| `category = 'premium'` | About 9% |
| `status = 'FAILED'` | About 4.3% |
| `status = 'PENDING'` | About 19% |
| `status = 'DONE'` | About 76% |
| `account_id = 4321` | About 10 rows |
| `account_id BETWEEN 1000 AND 1499` | About 2.5% |

Percentages are rough descriptions of the generator; count queries give exact numbers.

### 4.3. Update Statistics

```sql
ANALYZE scan_lab.events;
```

`ANALYZE` samples statistics so the planner can estimate row counts for predicates. Without sufficiently fresh statistics, the planner may misjudge selectivity.

### 4.4. Verify Data

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE category = 'premium'
    ) AS premium_rows,
    COUNT(*) FILTER (
        WHERE category = 'standard'
    ) AS standard_rows,
    COUNT(*) FILTER (
        WHERE status = 'FAILED'
    ) AS failed_rows,
    MIN(occurred_at) AS first_event,
    MAX(occurred_at) AS last_event
FROM scan_lab.events;
```

Note: this query **executes and scans data itself**; it validates lab data, not a fixed optimal plan.

### 4.5. Why Not Print One Single "Canonical" EXPLAIN Output?

The same SQL can produce different plans depending on:

- PostgreSQL version.
- Table and index sizes.
- Actual row counts after edits.
- `ANALYZE` statistics.
- Storage hardware and cost settings.
- Cache state, parallel workers, and `work_mem`.
- Indexes existing at runtime.
- Projected columns and `ORDER BY`/`LIMIT`.
- Value selectivity, including prepared statement parameters.

Therefore, the plans below are **structural patterns to recognize**, not a promise your machine will pick the exact same node.

## 5. Reading EXPLAIN Before Optimizing

`EXPLAIN` shows the plan PostgreSQL intends to run **without executing the SELECT** unless `ANALYZE` is requested.

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

An illustrative output:

```text
Seq Scan on events
  (cost=0.00..xxxx.xx rows=yyyy width=zzz)
  Filter: (category = 'standard'::text)
```

`xxxx`/`yyyy`/`zzz` are illustrative placeholders, not actual measurements.

### 5.1. Meaning of Common Parts

| Attribute | Meaning |
| --- | --- |
| `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` | Access path type |
| `cost=A..B` | Estimated startup and total cost of the node |
| `rows=N` | Estimated output rows from the node |
| `width=W` | Estimated average byte width per output row |
| `Filter` | Condition checked on rows arriving at the node |
| `Index Cond` | Condition usable to bound traversal inside the index |
| `Recheck Cond` | Condition that may need rechecking when reading heap from a bitmap |
| `Rows Removed by Filter` | Rows discarded at the filter step in ANALYZE |
| `Rows Removed by Index Recheck` | Rows discarded when rechecking index conditions |
| `actual time` | Observed actual duration when using ANALYZE |
| `actual rows` / `loops` | Actual output rows and execution count |
| `Buffers` | Blocks accessed in the buffer/cache system per EXPLAIN metrics |

### 5.2. Cost Is Not Milliseconds

For example:

```text
cost=0.00..1340.00
```

does not mean "takes 1340 ms." It is a **planner cost unit** used to compare plans, derived from I/O/CPU parameters and statistics.

`startup cost` is estimated cost before the node can emit its first row; `total cost` is estimated cost for the full node run under the planner's model.

With `LIMIT`, the cost of producing the first few rows can outweigh full-scan cost.

### 5.3. EXPLAIN ANALYZE Actually Executes the Statement

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

`ANALYZE` tells PostgreSQL to **execute** the SQL and record actual rows/timings.

**Warning:** for `INSERT`/`UPDATE`/`DELETE`, `EXPLAIN ANALYZE` **performs the data changes**.

To inspect an UPDATE in a lab database without persisting changes:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE scan_lab.events
SET amount = amount + 1
WHERE event_id = 1001;

ROLLBACK;
```

Rollback cancels transactional changes, yet I/O, WAL, locks, sequences, or external side effects can still occur depending on the statement/functions executed. Never treat `BEGIN...ROLLBACK` as a license to test dangerous DML in production.

## 6. Sequential Scan: Reading the Heap Sequentially

`Seq Scan` means PostgreSQL reads the table's pages along the heap and checks conditions on visible rows.

Model:

```text
Heap pages:
[0] [1] [2] [3] [4] [5] ... [N]
 |   |   |   |   |   |
 v   v   v   v   v   v
       Check WHERE on rows
                |
                v
             Results
```

### 6.1. When Is Seq Scan Reasonable?

Common scenarios:

1. The query needs **most rows** in the table.
2. The table is very small, so reading a few pages beats traversing an index then heap.
3. The WHERE clause has no suitable index access path.
4. Many columns or wide rows are selected; fetching heap rows one-by-one via index is costly.
5. High match count makes random heap access costlier than sequential reading.
6. The planner chooses a parallel scan or full-table join/aggregate strategy.
7. An index exists, yet selectivity is too low for the condition.
8. Expression filters do not match existing indexes.

### 6.2. Query Returning Most Events

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, payload
FROM scan_lab.events
WHERE category = 'standard';
```

In our lab data, roughly 91% of rows match. Without a `category` index, `Seq Scan` is expected. Even **after creating an index**, the planner may still choose Seq Scan because too many tuples match.

Example plan snippet:

```text
Seq Scan on events
  Filter: (category = 'standard'::text)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

This **does not by itself prove PostgreSQL ignored an index wrongly**.

### 6.3. Filter Applied During Scanning

```sql
SELECT event_id, amount
FROM scan_lab.events
WHERE amount >= 95.00;
```

Without an index usable for `amount`, Seq Scan remains a sensible plan, since PostgreSQL must check the condition on read tuples.

In EXPLAIN, `Filter` denotes the predicate used to discard non-matching rows at that node.

### 6.4. Seq Scan Does Not Mean All Data Travels Over the Network

If a query runs:

```sql
SELECT COUNT(*)
FROM scan_lab.events;
```

a Seq Scan reads the table to count, yet **does not send 200,000 rows to the client**. It feeds tuples into an `Aggregate` node and returns a single count.

Distinguish:

- Rows processed internally by the scan.
- Rows emitted by the node.
- Final rows returned over the network.

### 6.5. PostgreSQL Does Not Store an Exact Cached Row Count by Default

A `COUNT(*)` query on a large table normally must scan data in accordance with MVCC visibility, rather than reading a single always-exact global counter.

Some COUNT queries can use `Index Only Scan` if an index and visibility map are favorable, not because a B-tree stores a snapshot-agnostic exact table count.

## 7. Sequential Scan on Small Tables Is Usually Optimal

Create a tiny lookup table:

```sql
CREATE TABLE scan_lab.event_types (
    event_type_id integer PRIMARY KEY,
    description text NOT NULL
);

INSERT INTO scan_lab.event_types
    (event_type_id, description)
VALUES
    (1, 'Payment'),
    (2, 'Refund'),
    (3, 'Adjustment');

ANALYZE scan_lab.event_types;
```

Try:

```sql
EXPLAIN
SELECT *
FROM scan_lab.event_types
WHERE event_type_id = 2;
```

Despite having a PRIMARY KEY and index, the planner **may still pick Seq Scan**. The table has only a few rows on one page; reading it outright can be cheaper than doing a B-tree lookup.

**Do not add extra indexes or force index scans simply because you see Seq Scan on a 3-row table.** Check actual cost before calling it a performance problem.

## 8. Index Scan: Find Keys in the Index, Then Fetch Rows from the Heap

A typical `Index Scan` has two parts:

1. Use the index to locate entries satisfying **Index Cond**.
2. Visit the heap to fetch tuples, remaining columns, and/or check visibility/filters.

Model:

```text
B-tree index on account_id
           |
           v
     account_id = 4321
           |
      TID 1, TID 2, ...
           |
           v
   Heap page A, page F, page R ...
           |
           v
   Return event_id, payload, ...
```

When only a few results match, heap accesses are few; index lookup can vastly beat scanning the entire table.

### 8.1. Try First with PRIMARY KEY

`event_id` is the primary key, so PostgreSQL already has an index. Query one row:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE event_id = 12345;
```

A structure you might see:

```text
Index Scan using events_pkey on events
  Index Cond: (event_id = 12345)
  Buffers: shared hit=... read=...
```

Here `event_id = 12345` is supported by the index. The query selects `payload`, which is not in the primary key index, so heap access is normally needed.

### 8.2. Create an Index on account_id

```sql
CREATE INDEX events_account_idx
ON scan_lab.events (account_id);

ANALYZE scan_lab.events;
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, occurred_at, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

The generated data has roughly 10 events per account. PostgreSQL can choose `Index Scan using events_account_idx`.

### 8.3. Why Do Few Matching Rows Suit Index Scan?

If only 10 out of 200,000 rows are needed:

- Read index pages to locate entries.
- Fetch roughly 10 tuples from the heap.
- Skip scanning all remaining heap pages.

Conversely, if 180,000 rows match:

- Very many heap fetches are needed.
- Heap locations may be scattered.
- One sequential scan can be cheaper than countless scattered lookups.

### 8.4. Index Cond vs Filter

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, status, payload
FROM scan_lab.events
WHERE account_id = 4321
  AND status = 'DONE';
```

If the planner uses `events_account_idx`, the plan may show:

```text
Index Scan using events_account_idx on events
  Index Cond: (account_id = 4321)
  Filter: (status = 'DONE'::text)
  Rows Removed by Filter: ...
```

Explanation:

- `Index Cond` uses the index to narrow down candidate entries.
- `Filter` checks the remaining condition, typically on retrieved rows.
- An index on `account_id` alone does not contain a search structure for `status` values.

Depending on schema/indexes and actual plans, conditions may be partitioned differently.

### 8.5. Index Scan Does Not Always Read the Heap in Physical Order

A B-tree orders index entries by key. If entries for a value point to TIDs scattered far apart, an index scan can cause heavy random heap I/O.

This is a primary reason PostgreSQL picks a **bitmap scan** when match counts are moderate.

## 9. Bitmap Scan: Build a Map from the Index, Then Read the Heap

For a predicate returning **neither very few nor overwhelmingly many** rows, a `Bitmap Heap Scan` can fit well.

It normally appears alongside one or more `Bitmap Index Scan` nodes:

```text
Bitmap Heap Scan on events
  Recheck Cond: (category = 'premium'::text)
  -> Bitmap Index Scan on events_category_idx
       Index Cond: (category = 'premium'::text)
```

### 9.1. Two Execution Phases

**Phase 1: gather locations from the index**

`Bitmap Index Scan` reads the index to find matching TIDs. Rather than immediately fetching each heap tuple and handing it up, it builds a **bitmap** recording relevant pages/rows.

**Phase 2: read the heap**

`Bitmap Heap Scan` reads the heap blocks flagged by the bitmap, typically in **block order** to avoid jumping randomly across the heap in index key order.

Model:

```text
B-tree index (category)
         |
  Find premium entries
         |
         v
 Bitmap of matching TIDs / heap blocks
         |
         v
 +-----------------------------------------+
 | heap block 4: offsets 2, 7               |
 | heap block 5: offsets 3                   |
 | heap block 9: offsets 1, 8, 11            |
 | ...                                      |
 +-----------------------------------------+
         |
         v
 Bitmap Heap Scan reads blocks 4, 5, 9...
         |
         v
 MVCC visibility + quals/recheck as required
         |
         v
 Output rows
```

### 9.2. When Can a Bitmap Beat Index Scan?

Suppose 18,000 `premium` rows are spread across many heap pages. A regular Index Scan might visit the heap in index-entry order, causing heavy random heap accesses.

The bitmap path collects all needed positions first, then processes the heap page-by-page. Its trade-offs include:

- Upfront cost to build the bitmap.
- Memory for storing the bitmap.
- Loss of index key ordering in output.
- Potential need to recheck conditions.
- No early row emission like a simple index scan in many cases.

Thus, bitmap is not "an always-faster index scan." It is a **different trade-off**.

## 10. Practicing Bitmap Index Scan and Bitmap Heap Scan

### 10.1. Create an Index on category

```sql
CREATE INDEX events_category_idx
ON scan_lab.events (category);

ANALYZE scan_lab.events;
```

### 10.2. Query Selecting ~9% of Rows

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE category = 'premium';
```

A **possible** plan is:

```text
Bitmap Heap Scan on events
  Recheck Cond: (category = 'premium'::text)
  Heap Blocks: exact=...
  Buffers: shared hit=... read=...
  -> Bitmap Index Scan on events_category_idx
       Index Cond: (category = 'premium'::text)
```

With around 9% matching, the bitmap path often competes well against Index Scan and Seq Scan. The planner may still pick another plan based on cost estimates.

### 10.3. Compare the Same Index on a Common Value

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE category = 'standard';
```

Roughly 91% of rows match. Under most configurations, Seq Scan beats bitmap because the bitmap would end up touching nearly all heap blocks anyway.

### 10.4. Selecting Even Fewer Rows

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

Row count is tiny, so Index Scan can be cheaper than bitmap: no need to pay bitmap-building overhead for 10 results.

### 10.5. A Single Data Point Cannot Define a Universal "Percentage Threshold"

There is no hard-and-fast rule such as:

```text
< 1%  -> Index Scan
1-20% -> Bitmap Scan
> 20% -> Seq Scan
```

Thresholds like those are **over-simplified rules of thumb**, not PostgreSQL rules. Small tables, warm caches, wide rows, high correlation, or `ORDER BY LIMIT` can shift the choice substantially.

## 11. Exact vs Lossy Bitmaps

A bitmap can track selected tuples at two levels of precision:

1. **Exact**: records specific tuple offsets within each heap block.
2. **Lossy**: retains only heap block numbers without enough space to list individual matching offsets.

Under bitmap memory pressure, PostgreSQL can degrade portions from exact to lossy to reduce memory footprint.

### 11.1. Exact Bitmap

Model:

```text
block 105:
  matching offset 2
  matching offset 8
  matching offset 11

Other offsets are excluded from the bitmap.
```

`Bitmap Heap Scan` primarily examines the indicated TIDs alongside MVCC checks and remaining predicates.

### 11.2. Lossy Bitmap

Model:

```text
block 105:
  "This block may contain matching rows"

Exact list of matching offsets is no longer retained.
```

When reading that block, PostgreSQL must inspect additional tuples and **recheck the index qual** to discard tuples that do not actually match.

### 11.3. Reading `Heap Blocks`

In `EXPLAIN (ANALYZE, BUFFERS)`, you may see:

```text
Bitmap Heap Scan on events
  Recheck Cond: (...)
  Rows Removed by Index Recheck: ...
  Heap Blocks: exact=... lossy=...
```

| Line | Meaning |
| --- | --- |
| `Heap Blocks: exact=N` | Heap blocks tracked at exact tuple granularity |
| `Heap Blocks: lossy=M` | Blocks that had to be processed via lossy bitmap |
| `Recheck Cond` | Predicate used to verify rows from the bitmap when needed |
| `Rows Removed by Index Recheck` | Tuples discarded for failing the predicate upon recheck |

### 11.4. Seeing `Recheck Cond` Does Not Mean the Bitmap Was Lossy

A plan showing:

```text
Recheck Cond: (category = 'premium')
Heap Blocks: exact=...
```

**is not enough to conclude the bitmap went lossy**. EXPLAIN prints `Recheck Cond` as the condition to apply if recheck is needed; when the bitmap stays exact, many conditions do not discard rows via recheck.

To tell whether lossiness occurred, look for `Heap Blocks: lossy` and `Rows Removed by Index Recheck` when those counters appear.

### 11.5. "Rows Removed by Index Recheck" Is Not Filter

- `Rows Removed by Index Recheck`: rows discarded while re-verifying the bitmap's index predicate.
- `Rows Removed by Filter`: rows discarded by an ordinary node filter not part of the index recheck.

Example query:

```sql
SELECT *
FROM scan_lab.events
WHERE category = 'premium'
  AND amount > 50.00;
```

If the bitmap is built on `category` and `amount` is not part of that index predicate, `amount > 50` will appear as a separate `Filter`.

### 11.6. Lossy Does Not Always Mean "Broken Index"

Lossy bitmaps are a valid memory-saving mechanism in PostgreSQL, not a sign of index corruption.

They can add CPU for rechecking more tuples, yet sometimes remain the best plan compared to scattered heap reads or full sequential scans.

## 12. How Does `work_mem` Affect Bitmaps?

`work_mem` sets a memory budget for certain query operations, including bitmaps and sorts/hashes, with details depending on node type and version.

When a bitmap grows past its memory budget, it can switch to lossy representation.

### 12.1. Testing a Low Limit in the Lab Database

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';

ROLLBACK;
```

You may observe a change in exact/lossy heap blocks, **if** the planner picks a bitmap path and the bitmap grows large enough to hit memory pressure.

There is no guarantee this query goes lossy on every machine.

### 12.2. Testing a Higher Value

```sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';

ROLLBACK;
```

Compare:

- Is Bitmap Heap Scan still chosen?
- Did exact/lossy block counts change?
- Did `Rows Removed by Index Recheck` change?
- How did Buffers and actual time change?

### 12.3. Do Not Raise `work_mem` System-Wide for One Plan

`work_mem` is not a global RAM cap for PostgreSQL. Many concurrent queries, each with multiple sort/hash/bitmap nodes, can consume large total memory.

Setting the global value too high can cause severe RAM pressure. Measure and tune in the appropriate scope, weighing overall workload and concurrency.

### 12.4. Lossy Bitmaps Can Also Come from the Index Access Method

Certain index types, especially those operating at block/coarse granularity, inherently require substantial rechecks. For example, **BRIN** summarizes ranges of pages and produces bitmap heap scans with recheck filtering.

Hence lossiness/recheck is not solely a `work_mem` effect; it also depends on index type and predicate.

## 13. BitmapAnd and BitmapOr: Combining Multiple Indexes

Bitmap scans have a major advantage: PostgreSQL can combine location sets from **multiple indexes**.

### 13.1. Create a Second Index on status

```sql
CREATE INDEX events_status_idx
ON scan_lab.events (status);

ANALYZE scan_lab.events;
```

### 13.2. AND Condition

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

A **possible** plan shape is:

```text
Bitmap Heap Scan on events
  Recheck Cond: (
      (category = 'premium'::text)
      AND (status = 'FAILED'::text)
  )
  -> BitmapAnd
       -> Bitmap Index Scan on events_category_idx
            Index Cond: (category = 'premium'::text)
       -> Bitmap Index Scan on events_status_idx
            Index Cond: (status = 'FAILED'::text)
```

`BitmapAnd` intersects the two sets of TID/block positions.

However, the planner may also use **one** index and `Filter` the other condition if cheaper. Not every `AND` yields a `BitmapAnd`.

### 13.3. OR Condition

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
   OR status = 'FAILED';
```

A possible plan shape is:

```text
Bitmap Heap Scan on events
  Recheck Cond: (
      (category = 'premium'::text)
      OR (status = 'FAILED'::text)
  )
  -> BitmapOr
       -> Bitmap Index Scan on events_category_idx
            Index Cond: (category = 'premium'::text)
       -> Bitmap Index Scan on events_status_idx
            Index Cond: (status = 'FAILED'::text)
```

`BitmapOr` unions positions from both bitmaps. If a row matches both conditions, it is still returned once per query semantics (no duplicates created just because a TID appeared in both bitmaps).

### 13.4. Why Are AND/OR Bitmaps Useful?

You might avoid building a composite index for every pair of predicates if the planner can combine two existing indexes effectively.

However, BitmapAnd/BitmapOr incur bitmap construction cost; a **composite index** with the right column order can be faster, especially for hot queries or `ORDER BY LIMIT`.

Do not conclude "two single-column indexes are always better than one multi-column index." Measure against your workload.

## 14. Index Only Scan: When the Index Holds Enough Data to Answer the Query

`Index Only Scan` is a related yet **distinct** access path from ordinary `Index Scan`.

For index-only reads to be effective, you need:

1. An access method supporting index-only scans for the query's operators.
2. Every column returned/checked present in the index (index keys or appropriate `INCLUDE` columns).
3. PostgreSQL knowing relevant heap pages satisfy visibility requirements, via the **visibility map**.

### 14.1. Create a Suitable Covering Index

```sql
CREATE INDEX events_account_time_cover_idx
ON scan_lab.events (account_id, occurred_at DESC)
INCLUDE (status, amount);
```

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, occurred_at, status, amount
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

The B-tree index contains:

- `account_id`: filter predicate.
- `occurred_at DESC`: ordering.
- `status` and `amount`: index payload to return results, via `INCLUDE`.

The planner may choose `Index Only Scan`, though it is not forced to.

### 14.2. Visibility Map and `Heap Fetches`

PostgreSQL must guarantee a tuple is visible under the current MVCC snapshot. Index entries **do not carry full visibility metadata equivalent to the heap**.

The visibility map tracks which heap pages are **all-visible**, allowing PostgreSQL to skip heap reads for tuples residing on those pages.

The plan may show:

```text
Index Only Scan using events_account_time_cover_idx
  Index Cond: (account_id = 4321)
  Heap Fetches: 0
```

Yet if some pages are not all-visible:

```text
Index Only Scan using events_account_time_cover_idx
  Heap Fetches: 5
```

It is still called `Index Only Scan`, even though it had to visit the heap **several times** to verify visibility.

### 14.3. VACUUM Helps Under the Right Conditions

In the lab database, after data is committed:

```sql
VACUUM (ANALYZE) scan_lab.events;
```

This can update the visibility map for eligible pages, making index-only scans more effective. `VACUUM` must run outside explicit transaction blocks—**do not place this regular VACUUM command inside an explicit transaction block**.

There is no guarantee every query chooses `Index Only Scan` after VACUUM: columns, statistics, indexes, and costs still govern the choice.

### 14.4. Why Do Continuous INSERT/UPDATEs Reduce Index-Only Efficiency?

Newly written or recently modified heap pages may lack the all-visible bit. Index Only Scan then has to revisit the heap repeatedly for visibility checks.

Hence, a covering index that shines on mostly static tables becomes less effective on write-heavy tables, even with identical SQL.

### 14.5. INCLUDE Is Not Free

`INCLUDE` stores extra data in the index, which can:

- Increase index storage size.
- Increase I/O and index maintenance cost during writes.
- Reduce entries per index page.
- Affect B-tree storage/deduplication characteristics.
- Not help filter on an included column the way a search key column does.

Choose `INCLUDE` for **high-value queries** rather than stuffing every column to "cover" the whole table.

## 15. ORDER BY and LIMIT Can Let Index Scan Beat Bitmap Scan

A B-tree index maintains key order. Therefore, if a query needs that exact order, Index Scan or Index Only Scan can return **already-sorted** rows without a separate Sort.

### 15.1. Fetching the 5 Most Recent Events for an Account

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, occurred_at, status, amount
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

Index:

```sql
CREATE INDEX events_account_time_idx
ON scan_lab.events (account_id, occurred_at DESC);
```

If this index exists, the planner can walk `(account_id, occurred_at DESC)` directly to return the first 5 rows quickly without scanning all rows for that account.

If the covering index from section 14 also exists, the planner may pick either equivalent index depending on cost; that is normal in the lab.

### 15.2. Bitmaps Lose Index Key Order

When using a bitmap, PostgreSQL organizes heap reads by block order. Consequently, `Bitmap Heap Scan` output **does not preserve B-tree key order** merely because the bitmap came from a B-tree.

If the SQL requires:

```sql
ORDER BY occurred_at DESC
```

a bitmap plan may need an extra:

```text
Sort
  -> Bitmap Heap Scan
       -> Bitmap Index Scan
```

Whereas a matching index scan can avoid Sort entirely.

### 15.3. LIMIT Makes Startup Cost Crucial

With `LIMIT 5`, PostgreSQL can favor a plan returning **the first five rows** rapidly, even if another plan has lower total cost when returning the full result set.

For example:

```sql
EXPLAIN
SELECT event_id, occurred_at
FROM scan_lab.events
ORDER BY occurred_at DESC
LIMIT 5;
```

With a suitable B-tree index on `occurred_at`, the planner can scan the index forward/backward to grab a few rows without sorting the whole table.

### 15.4. LIMIT Without ORDER BY

```sql
SELECT event_id
FROM scan_lab.events
LIMIT 5;
```

This does not require any specific row order. The planner may pick Seq Scan to emit five rows right away.

Do not interpret that as "Seq Scan reads all 200,000 rows" when only five are needed: the executor can **stop early** once the `Limit` node receives enough rows, depending on plan structure.

### 15.5. Deep OFFSET Is Usually Expensive

```sql
SELECT event_id, occurred_at
FROM scan_lab.events
ORDER BY occurred_at DESC
LIMIT 20 OFFSET 100000;
```

Even with an index, the query must step through a huge number of entries before returning the requested page. For deep pagination, **keyset pagination** on a stable key is often better, provided conditions and ordering are designed properly.

## 16. Direct Comparison of the Three Access Paths

| Characteristic | Seq Scan | Index Scan | Bitmap Heap Scan |
| --- | --- | --- | --- |
| Starts from | Heap | Index | One or more indexes building a bitmap |
| Uses index? | Not required | Yes | Yes, during bitmap index phase |
| Reads heap how? | Sequentially by page | By tuple locations from index | Grouped by heap blocks |
| Emits rows very early? | Possibly | Usually good when selective | Must build bitmap first |
| Good for few matches? | Usually poor on large tables | **Usually good** | Overhead may not pay off |
| Good for moderate matches? | Depends on table/cache | Can incur heavy random I/O | **Often worth considering** |
| Good for most of table? | **Usually good** | Usually poor due to many heap fetches | Often loses advantage |
| Preserves B-tree key order? | Not guaranteed | Can do so | No |
| Combines multiple indexes via AND/OR? | Not this way | Usually needs another suitable index | Yes via BitmapAnd/BitmapOr |
| Can produce lossy bitmap? | No | No | Yes |
| Has `Index Cond`? | No | Usually yes | On Bitmap Index Scan |
| Has `Recheck Cond`? | Not bitmap-style | Not bitmap-heap-style | Usually yes |
| Can run in parallel? | Parallel Seq Scan variant | Supported under eligible conditions/AM | Parallel Bitmap Heap Scan variant |

This table is an architectural guide, **not an absolute planner rulebook**.

## 17. Selectivity Drives Many Decisions

**Selectivity** of a predicate expresses the estimated fraction of rows satisfying it.

Examples:

```sql
WHERE account_id = 4321
```

might match ~10 out of 200,000 rows, or ~0.005%.

```sql
WHERE category = 'standard'
```

might match ~91%.

### 17.1. Why High Match Ratios Disfavor Ordinary Index Scan

An Index Scan would have to:

1. Read index pages.
2. Visit very many heap pages to fetch rows.
3. Repeat numerous heap accesses.

If most heap pages are touched anyway, a single sequential heap pass via Seq Scan is often cheaper.

### 17.2. Why Low Match Ratios Might Still Use Seq Scan

If a table spans only a few pages, planning and traversing an index can cost more than reading the table directly.

Or if the predicate is not index-compatible due to expressions, collation, or operator class, the planner has no usable index path.

Or the index is huge and uncached, making actual cost unfavorable.

### 17.3. Selectivity Is Estimated—The Planner Does Not Count Rows First

PostgreSQL typically uses:

- Estimated table row count.
- Per-column statistics.
- Most common values (MCV).
- Histograms.
- Distinct value counts.
- Null fraction.
- Correlation.
- Extended statistics for certain multi-column queries.

The planner does not run an exact `COUNT(*)` for every value right before picking a plan.

## 18. `ANALYZE` and Planner Statistics

Inspect statistics:

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    correlation
FROM pg_stats
WHERE schemaname = 'scan_lab'
  AND tablename = 'events'
  AND attname IN (
      'account_id', 'category', 'status', 'occurred_at'
  )
ORDER BY attname;
```

### 18.1. Most Common Values

If `category = 'standard'` is ~91% and `premium` is ~9%, statistics help the planner know the two values have vastly different frequencies.

It will not naively assume two values mean 50% each.

### 18.2. `n_distinct`

Represents estimated distinct value count. For a column with many account IDs, this shapes row estimates for `=` comparisons.

### 18.3. Correlation

`pg_stats.correlation` reflects how closely column value order aligns with physical table order.

- Correlation near `+1` or `-1` suggests physical order aligns strongly with the key.
- Near `0` indicates little physical ordering correlation.

The planner uses this in index access cost models. If heap tuples with adjacent keys also sit physically close together, an index scan suffers far less random I/O than on shuffled data.

### 18.4. Refresh After Large Changes

```sql
ANALYZE scan_lab.events;
```

After bulk imports, deletes, or updates, stale stats can cause bad `rows` estimates. Autovacuum/autoanalyze maintains stats per system policy, yet sudden dataset shifts may call for manual ANALYZE.

**Do not treat ANALYZE as a "command forcing PostgreSQL to use an index."** It simply gives the planner better inputs for cost estimation.

## 19. Estimation Errors: Signals to Investigate

Examine:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

Compare:

- `rows=...` in the planner estimate.
- `actual rows=...` in ANALYZE output.

If the estimate is 10 rows while actual is 10,000 rows, the planner may have picked an unsuitable access path or join strategy.

### 19.1. Illustrative Numbers Example

```text
Index Scan on events
  (cost=0.40..18.20 rows=10 width=180)
  (actual time=0.080..40.000 rows=10000 loops=1)
```

**This is not real measured output from the lab dataset.** It illustrates a massive row-estimate mismatch.

### 19.2. Possible Causes

- Stale statistics.
- Skewed distribution.
- Unmodeled dependencies across multiple columns.
- Conditions with hard-to-estimate functions/expressions.
- Prepared statements using a generic plan unrepresentative of specific parameters.
- Sampling resolution too coarse.
- Multi-table joins compounding estimation errors.

### 19.3. Extended Statistics When Columns Are Correlated

Example:

```sql
CREATE STATISTICS events_category_status_stats
    (dependencies, mcv)
ON category, status
FROM scan_lab.events;

ANALYZE scan_lab.events;
```

PostgreSQL can use these multi-column statistics to improve selectivity estimates for applicable predicates.

Do not assume `CREATE STATISTICS` builds an index or forces BitmapAnd: it only supplies estimation data.

### 19.4. Look Beyond Just the Slow Node

An access path may be reasonable on its own yet invoked repeatedly due to a parent join strategy.

With `EXPLAIN ANALYZE`, watch `loops`. `actual rows` on a node is normally displayed as an average per execution; understanding total work requires accounting for `loops`.

## 20. Physical Locality and Correlation: Same Selectivity, Different Cost

Two tables both match 5% of rows for a predicate, yet:

- In table A, matching rows cluster tightly on few heap blocks.
- In table B, matching rows scatter across almost the entire table.

Optimal access paths can differ because **heap pages read** and randomness differ.

### 20.1. Visual Model

```text
Table A: clustered matches
[XXXX][XXXX][XXXX][....][....][....]
    ^ fewer pages needed

Table B: scattered matches
[X...][.X..][..X.][...X][X...][.X..]
    ^ many pages touched despite similar match count
```

### 20.2. `CLUSTER` and Physical Ordering

PostgreSQL offers `CLUSTER` to rewrite a heap in index order:

```sql
-- Illustrative in lab database only:
CLUSTER scan_lab.events USING events_account_idx;
ANALYZE scan_lab.events;
```

This operation **rewrites and reorganizes the table**, requiring strong locks and heavy resources—not a casual production tweak.

`CLUSTER` also **does not preserve physical order permanently** as subsequent INSERT/UPDATEs occur.

### 20.3. When Is CLUSTER Unnecessary?

If `WHERE account_id = ...` only returns a few rows, index scan is likely fast enough already. Rewriting an entire table just for one small lookup rarely justifies the lock and maintenance cost.

Measure `EXPLAIN ANALYZE BUFFERS` and real workloads before considering physical layout changes.

## 21. Composite Indexes Can Replace Single-Index Bitmaps

Create index:

```sql
CREATE INDEX events_category_status_idx
ON scan_lab.events (category, status);

ANALYZE scan_lab.events;
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

The planner now has additional options:

1. Seq Scan.
2. Index Scan/Bitmap Index Scan on `events_category_idx`, then filter `status`.
3. Index Scan/Bitmap Index Scan on `events_status_idx`, then filter `category`.
4. BitmapAnd of both single indexes.
5. Index Scan or Bitmap Index Scan on the **composite index**.

### 21.1. Column Order in B-Tree Matters

An index on:

```sql
(category, status)
```

is especially helpful when queries filter on the **leading column `category`** and subsequent columns.

A query with only:

```sql
WHERE status = 'FAILED'
```

is not automatically optimized the same way as filtering on both columns. PostgreSQL has specialized strategies depending on version and data, yet **never treat all composite index column orders as equivalent**.

### 21.2. Composite Indexes Do Not Always Beat BitmapAnd

If the workload runs mostly:

- Queries by `category` alone.
- Queries by `status` alone.
- Complex OR queries.
- Many varying condition combinations.

individual indexes can remain valuable. Composite indexes also add write and storage overhead.

Design indexes for **real high-frequency or latency-critical queries**, not every possible permutation.

### 21.3. When Are Partial Indexes Useful?

Suppose `FAILED` events are queried frequently:

```sql
CREATE INDEX events_failed_time_idx
ON scan_lab.events (occurred_at DESC)
WHERE status = 'FAILED';
```

Query:

```sql
SELECT event_id, occurred_at, payload
FROM scan_lab.events
WHERE status = 'FAILED'
ORDER BY occurred_at DESC
LIMIT 20;
```

A partial index stores only rows matching its predicate. It stays small and aligns tightly with this query.

However, the planner only uses a partial index when it can **prove the query's predicate implies the index predicate** at planning time. A generic prepared plan with `status = $1` cannot prove `status = 'FAILED'` for all values.

**A partial index is not a shortcut forcing PostgreSQL to use an index on every similar-looking SQL query.**

## 22. Not All Index Types Share the Same Scan Paths

Common examples:

| Index access method | Relevant characteristics |
| --- | --- |
| B-tree | Suited for `=`, ranges, sorting; supports multiple index access forms |
| Hash | Useful for equality with matching operator class; provides no B-tree ordering |
| GIN | Common for key/element sets, arrays, JSONB, full-text; bitmap access common |
| GiST | Spatial/similarity searches; may need rechecks per operator class |
| SP-GiST | Space-partitioned search structures |
| BRIN | Summarizes **ranges of heap pages**, tiny and effective for physically correlated data; usually needs recheck |

### 22.1. BRIN Illustrating Page-Level Bitmaps

Suppose `occurred_at` increases roughly in insertion order, as in our lab dataset. You can create:

```sql
CREATE INDEX events_time_brin_idx
ON scan_lab.events
USING brin (occurred_at);
```

Range query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM scan_lab.events
WHERE occurred_at >= timestamptz '2025-04-01 00:00:00+00'
  AND occurred_at <  timestamptz '2025-04-02 00:00:00+00';
```

BRIN summarizes page ranges, which can lead to:

```text
Bitmap Heap Scan
  Recheck Cond: ...
  Rows Removed by Index Recheck: ...
  Heap Blocks: lossy=...
  -> Bitmap Index Scan on events_time_brin_idx
```

This is **a possible plan**, not guaranteed. BRIN shines when data correlates strongly with physical storage order and the table is large.

### 22.2. Why Can BRIN Return Many Non-Matching Rows Before Recheck?

A BRIN index states "this page range may contain values in the range," rather than tracking individual exact TIDs like a B-tree. Reading those pages requires PostgreSQL to **recheck** and discard tuples outside the predicate.

### 22.3. Do Not Equate "Bitmap Scan" with B-Tree

A `Bitmap Index Scan` can use index methods other than B-tree. What matters is the **bitmap + heap scan access path**, while index type determines operator support, precision, and cost.

## 23. Parallel Seq Scan and Parallel Bitmap Heap Scan

For large tables and suitable configuration, the planner may pick a **parallel plan**.

### 23.1. Parallel Seq Scan

```text
Gather
  Workers Planned: ...
  -> Parallel Seq Scan on events
       Filter: ...
```

Workers divide heap reading and filtering work.

Related elements:

- `Gather` collects results from workers.
- `Workers Planned` is the worker count planned.
- `Workers Launched` in ANALYZE is the count actually started.
- Query/plan must satisfy parallel-safety rules.

### 23.2. Parallel Bitmap Heap Scan

Some plans take the form:

```text
Gather
  -> Parallel Bitmap Heap Scan on events
       Recheck Cond: ...
       -> Bitmap Index Scan on ...
```

Bitmap creation and parallel heap-reading coordination have specific implementation details, yet logically it still **identifies matching pages/rows and scans the heap**.

### 23.3. Why Isn't Parallel Always Faster?

Parallelism incurs overhead:

- Starting and managing workers.
- Partitioning/coordinating work.
- Collecting tuples via Gather.
- Contending on shared memory/I/O.

A small query returning very few rows can run faster on a single backend. Worker availability also depends on system load.

### 23.4. Can Index Scans Run in Parallel?

PostgreSQL supports parallel index/index-only scan paths on eligible index access methods (such as B-tree). Do not assume every index type and every predicate supports parallel scans equally.

When reading `EXPLAIN`, check **the actual node names** instead of assuming "all index scans are single-threaded."

## 24. Reading `EXPLAIN (ANALYZE, BUFFERS)` Properly

Example query:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE account_id BETWEEN 1000 AND 1499;
```

Watch for:

### 24.1. Estimated Rows vs Actual Rows

```text
(cost=... rows=5000 width=...)
(actual time=... rows=4980 loops=1)
```

If estimates track reality closely, statistics are likely sound. If off by orders of magnitude, investigate stats/predicates before blindly changing indexes.

### 24.2. Startup and Total Time

```text
actual time=0.050..12.300
```

The first value is observed time before emitting the first row; the second is time until the node completes (under instrumented execution).

Node times **do not simply add together** because parent nodes generally include child execution time.

### 24.3. Loops

```text
actual rows=10 loops=100
```

means the node executed 100 times; displayed `actual rows` is generally **averaged per loop**, not the sum across all loops. In nested-loop joins, this is crucial.

### 24.4. Shared Hit/Read

```text
Buffers: shared hit=300 read=50
```

General meaning:

- `shared hit`: blocks found in shared buffer cache.
- `shared read`: blocks brought into shared buffers; you cannot deduce every read hit physical disk because OS filesystem cache may satisfy it.
- Some plans also show `dirtied`, `written`, or local/temp buffers depending on operations.

A query with huge hits can still burn CPU or suffer contention. Never compare `read` across two runs after the cache warmed up.

### 24.5. Planning Time and Execution Time

`Planning Time` and `Execution Time` are distinct:

- Planning Time: time spent building the plan during measurement.
- Execution Time: instrumented query execution time in the executor.

Neither necessarily captures network transfer, client formatting, or end-to-end application processing time.

### 24.6. TIMING OFF Option

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT event_id
FROM scan_lab.events
WHERE account_id = 4321;
```

`TIMING OFF` reduces per-node clock-sampling overhead while retaining actual row counts and overall execution time.

Useful when measuring very short queries or plans with high loop counts.

### 24.7. I/O Timings

If `track_io_timing` is enabled, EXPLAIN BUFFERS can report I/O timing details. Enabling I/O timing adds platform-dependent overhead.

Do not assume `shared read=100` means 100 identically slow physical disk reads.

## 25. Cost Model: Why Does an Index Look Fast Yet the Planner Picks Seq Scan?

Parameters involved in the cost model:

```sql
SHOW seq_page_cost;
SHOW random_page_cost;
SHOW cpu_tuple_cost;
SHOW cpu_index_tuple_cost;
SHOW cpu_operator_cost;
SHOW effective_cache_size;
SHOW effective_io_concurrency;
```

### 25.1. `seq_page_cost` and `random_page_cost`

`seq_page_cost` is the reference cost unit for sequential page reads. `random_page_cost` reflects estimated relative cost of random page reads.

Traditional Index Scans can trigger many random heap accesses. Thus the ratio between these two parameters influences Seq Scan vs Index Scan/Bitmap selection.

On SSDs, the random/sequential gap may be smaller than on spinning disks, though proper tuning still depends on workload and caching.

### 25.2. `effective_cache_size` Does Not Allocate RAM

`effective_cache_size` estimates usable cache memory (combining shared buffers and OS cache in the planner's model); it **does not allocate extra RAM to PostgreSQL**.

It influences how many pages the planner assumes are likely cached when costing plans.

### 25.3. CPU Costs

`cpu_tuple_cost`, `cpu_index_tuple_cost`, and `cpu_operator_cost` model CPU effort for processing tuples, index entries, and predicates.

A query matching many rows still spends CPU decoding and filtering tuples, even when 100% cached.

### 25.4. Do Not Tweak Cost Parameters Before Verifying Row Estimates

If the planner estimates 1% when reality is 80%, the core problem is likely statistics rather than `random_page_cost`.

Good workflow:

1. Read the plan and actual rows.
2. Check statistics.
3. Inspect indexes and predicates.
4. Check I/O and wait events.
5. Only adjust cost model parameters under controlled, evidence-backed testing.

Tuning is not a contest to "set `random_page_cost` super low so plans use indexes as much as possible."

## 26. Using `enable_seqscan` and `enable_bitmapscan` to Learn, Not as Quick Fixes

PostgreSQL exposes planner method configuration flags:

```sql
SHOW enable_seqscan;
SHOW enable_indexscan;
SHOW enable_indexonlyscan;
SHOW enable_bitmapscan;
```

Inside a **test transaction**, you can toggle them temporarily:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'standard';

ROLLBACK;
```

The planner tries to avoid Seq Scan if a valid alternative exists. Turning it off does not guarantee the alternative will be **faster**.

### 26.1. Comparing Bitmap and Index Paths

```sql
BEGIN;

SET LOCAL enable_bitmapscan = off;

EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';

ROLLBACK;
```

When bitmaps are discouraged, the planner chooses Seq Scan or Index Scan depending on cost and available alternatives.

### 26.2. Why Doesn't `enable_seqscan = off` Strictly Forbid Seq Scan?

PostgreSQL cannot eliminate sequential scans from all queries because sometimes no valid alternative exists. This setting **discourages** Seq Scan, essentially by heavily penalizing its cost.

Do not treat it as a guarantee that "the database will never scan a table."

### 26.3. Never Force Scan Methods in Production as a Permanent "Fix"

Forcing the planner onto indexes can:

- Hurt queries returning large row fractions.
- Trigger millions of random heap fetches.
- Spike I/O and latency.
- Produce terrible plans for other parameter values.
- Mask root causes like stale statistics or missing indexes.

Use `SET LOCAL` in the lab to explore alternatives, then restore normal settings.

## 27. Why Does the Planner Choose Differently for Prepared Statements?

JDBC applications or backend services often use bind parameters:

```sql
SELECT event_id, payload
FROM scan_lab.events
WHERE category = $1;
```

Parameter `$1 = 'standard'` has ~91% selectivity, whereas `$1 = 'premium'` has ~9%.

### 27.1. Custom Plan

A custom plan considers the specific parameter value. Thus PostgreSQL can pick Seq Scan for common values and bitmap/index paths for rare values.

### 27.2. Generic Plan

A generic plan is reused across parameter values; it cannot assume `$1` is always `premium`. Therefore, a generic plan's access path may be a compromise.

### 27.3. Experimenting with PREPARE

```sql
PREPARE event_by_category(text) AS
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_by_category('standard');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE event_by_category('premium');

DEALLOCATE event_by_category;
```

Results can shift due to generic/custom plan selection and execution count.

### 27.4. Testing with plan_cache_mode in the Lab

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

PREPARE event_by_category_demo(text) AS
SELECT event_id, payload
FROM scan_lab.events
WHERE category = $1;

EXPLAIN EXECUTE event_by_category_demo('standard');
EXPLAIN EXECUTE event_by_category_demo('premium');

DEALLOCATE event_by_category_demo;

ROLLBACK;
```

On PostgreSQL versions supporting `plan_cache_mode`, this demonstrates planning when parameter values are known.

Similarly, you can test `force_generic_plan` in the lab. Never arbitrarily change this setting across all application connections just because one query got an unexpected plan.

## 28. Index Scans Inside JOINs: Watch the Loop Count

Not every Index Scan plan is a single-table query.

Create an accounts table example:

```sql
CREATE TABLE scan_lab.accounts (
    account_id integer PRIMARY KEY,
    account_name text NOT NULL
);

INSERT INTO scan_lab.accounts (account_id, account_name)
SELECT g, 'account-' || g::text
FROM generate_series(1, 20000) AS s(g);

ANALYZE scan_lab.accounts;
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    a.account_name,
    e.event_id,
    e.occurred_at
FROM scan_lab.accounts AS a
JOIN scan_lab.events AS e
  ON e.account_id = a.account_id
WHERE a.account_id BETWEEN 4000 AND 4010;
```

The planner may use a shape like:

```text
Nested Loop
  -> Index Scan on accounts
  -> Index Scan on events
       Index Cond: (account_id = a.account_id)
```

Here the index scan on `events` may execute **many times**, once per outer account row.

### 28.1. Loops Multiply Cost

Suppose the inner index scan takes a tiny amount of time per call, yet runs 10,000 times. Total cost can be huge.

Do not look at a single per-loop `actual time` and declare the inner scan harmless. Factor in `loops` and total buffer accesses.

### 28.2. When Joining Many Rows, Seq Scan Can Be Right Again

If joining almost **all events** with `accounts`, PostgreSQL may choose:

```text
Hash Join
  -> Seq Scan on events
  -> Hash
       -> Seq Scan on accounts
```

This is not automatically a bad plan just because two Seq Scans appear. Reading each large table sequentially once and hash-joining can beat 200,000 scattered index lookups.

### 28.3. Only Tune Scan Nodes After Understanding the Full Join Tree

An index might satisfy one filter yet trick the planner into a Nested Loop worse than Hash Join due to bad estimates. Evaluate the whole **plan tree**, not just the count of Index Scans.

## 29. When Does Adding an Index Actually Help?

An index typically pays off when several factors align:

- Predicate is sargable and the index supports the operator.
- Selectivity is high enough to filter out most rows.
- Table is large enough that avoiding a full scan matters.
- Returned width/columns and heap fetch count are reasonable.
- Query has compatible `ORDER BY` or `LIMIT`.
- Index can cover the query with a favorable visibility map.
- Workload runs often enough to justify maintenance cost.

### 29.1. Do Not Create an Index Just Because Filter Appears

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

If 91% match, an index won't help and will add write overhead. Know how many rows the query returns and which access path is cheaper.

### 29.2. Indexes on Low-Cardinality Columns Still Have Cases Where They Help

`category` has only two distinct values, yet `premium` is relatively rare. An index can help `premium` queries under the right conditions.

Value frequency **matters more** than a simplistic rule like "never index a two-value column."

### 29.3. Index on account_id When Queries Fetch a Few Rows

```sql
SELECT event_id, account_id, occurred_at
FROM scan_lab.events
WHERE account_id = 4321;
```

An index on `account_id` fits narrow lookups on large tables well—a classic case where the planner favors Index Scan.

### 29.4. Read Gains Must Be Weighed Against Write Costs

Every added index can cause:

- Extra index updates on `INSERT`.
- Index maintenance on `UPDATE` modifying indexed columns.
- Higher storage footprint.
- Higher WAL volume.
- Longer REINDEX/backup/maintenance times.
- Reduced HOT update eligibility and higher VACUUM overhead in affected cases.

Do not index every column without accounting for write workloads.

## 30. Find Which Queries Need Tuning Before Inspecting Plans

In real systems, the question is rarely "does Seq Scan appear?"—it is "which queries consume the most total resources or breach SLAs?"

Prioritization signals:

1. High total SQL execution time.
2. High call frequency.
3. Rising P95/P99 latency.
4. Heavy buffer reads.
5. High ratio of rows read and discarded by filters.
6. Multi-order-of-magnitude estimation errors.
7. Sudden plan flips after data growth.
8. Exploding join loops.
9. Unnecessary sorting/aggregating of excessive rows.
10. Running full-table scans per request when narrower access is possible.

### 30.1. A Tiny Seq Scan Matters Less Than an Index Scan Looped Millions of Times

If a 3-row lookup table uses Seq Scan in microseconds, tuning it is pointless.

Conversely, a clean-looking Index Scan called 1,000,000 times inside a nested loop can be the primary bottleneck.

### 30.2. Observing Query Statistics

If `pg_stat_statements` is installed/enabled, use it to identify top queries by total time/buffers. This extension **is not automatically available everywhere** and requires configuration/permissions.

At the lesson level, always measure **real workload** before optimizing access paths.

### 30.3. Enable Logging/Monitoring Responsibly

Use policy-compliant slow query logging, EXPLAIN on representative queries, and existing monitoring metrics.

Do not turn on full logging/ANALYZE for every production query indiscriminately; instrumentation overhead and SQL data exposure can be serious.

## 31. Practical Plan Comparison Workflow

A reliable hands-on process:

### Step 1. Describe the Query and Data

Document:

- SQL and parameters.
- Schema and existing indexes.
- Table size and row count.
- Key distribution.
- Expected returned rows.
- SLA and execution frequency.

### Step 2. Refresh Statistics When Appropriate

```sql
ANALYZE scan_lab.events;
```

Do not run `ANALYZE` on an overloaded production server without checking timing/resources, though in the lab it is standard practice.

### Step 3. Read the Estimated Plan

```sql
EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Record Seq / Index / Bitmap nodes, cost, rows, and width.

### Step 4. Measure Execution on Representative SELECTs

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Compare estimates vs actuals and buffers.

### Step 5. Pick One Justified Change

For example, adding a missing index:

```sql
CREATE INDEX IF NOT EXISTS events_account_lookup_idx
ON scan_lab.events (account_id);
```

Since the lab already created `events_account_idx`, this would be **a largely redundant duplicate index**, so in real practice **do not create it again**. The snippet merely shows syntax when **no index exists yet**.

A more justified change might be a composite index for order/limit queries or refreshing stale statistics.

### Step 6. Re-Measure the Same Query

Compare:

- Actual Execution Time across multiple runs.
- Buffer hits/reads.
- Estimated/actual rows.
- Plan path.
- Query frequency.
- INSERT/UPDATE write cost.
- Contention under concurrent load.

### Step 7. Account for Caching and Measurement Methodology

The first run may read many pages; later runs hit warm caches. Measuring once can mislead.

Do not try to flush production caches with risky commands just to get "fair" benchmarks. Use a test environment with documented repeatable runs.

## 32. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| If an index exists, PostgreSQL must use it | The planner picks the plan estimated to be cheaper |
| Seq Scan is always slow | Can be optimal for small tables or large row fractions |
| Index Scan is always faster than Seq Scan | Random heap accesses can cost more than sequential scans |
| Bitmap Scan scans the table without an index | It normally pairs Bitmap Index Scan + Bitmap Heap Scan |
| Bitmap Scan is always faster than Index Scan | Pays bitmap creation cost and loses index order |
| Bitmaps always track 100% exact TIDs | Can be exact or lossy |
| Seeing Recheck Cond means the bitmap went lossy | Not necessarily; check Heap Blocks lossy and recheck removals |
| Recheck Cond and Filter are the same thing | Recheck verifies bitmap predicate; Filter checks other conditions |
| Multiple single indexes cannot be combined | BitmapAnd/BitmapOr can combine them |
| AND always produces BitmapAnd | Planner may use one index + Filter or Seq Scan |
| Bitmaps preserve B-tree ORDER BY | Heap reads follow block order; Sort may be needed |
| SELECT LIMIT 5 always reads only 5 rows | May scan/sort many rows first depending on plan |
| Seq Scan + LIMIT always scans the whole table | Executor can stop early once Limit is satisfied |
| Index Only Scan never touches the heap | Can incur Heap Fetches for visibility |
| INCLUDE turns any column into an Index Cond | Included columns are not search keys |
| Any column order in a composite index works the same | Leading keys and ORDER BY matter greatly |
| Indexes on low-cardinality columns are always useless | Rare values can still be selective enough |
| Indexing every column optimizes the whole database | Increases write cost, WAL, storage, and maintenance |
| EXPLAIN cost is milliseconds | Cost is a planner estimate unit |
| EXPLAIN ANALYZE does not execute SQL | It executes it; DML modifies data |
| Buffers shared read equals physical disk reads | OS page cache still plays a role |
| actual rows is always total node output | With loops, text output averages per loop |
| Two EXPLAINs with different timings mean a bad plan | Cache/load/measurement variance can change times |
| ANALYZE forces index usage | ANALYZE refreshes stats; it does not force plans |
| Correlation does not affect access paths | Physical locality affects random heap I/O cost |
| Lowest random_page_cost is always best | Must model actual storage and caching |
| effective_cache_size allocates RAM to the server | Only informs planner cache estimates |
| Raising work_mem speeds up every bitmap | Carries RAM risk under concurrency |
| enable_seqscan=off is a production fix | Only a lab tool to explore alternatives |
| Prepared statements always optimize per value | Generic/custom plans can behave differently |
| BRIN works like exact-TID B-tree | BRIN summarizes page ranges and usually rechecks |
| Parallel always cuts latency | Worker/Gather overhead can outweigh gains |
| A Seq Scan inside Hash Join is a bug | Scanning large tables sequentially once can be fastest |

## 33. Guided Practice Exercises

Exercises use `scan_lab.events`. Record the **actual plan on your machine** rather than forcing it to match an example; explaining why PostgreSQL picked a different path is part of the exercise.

### Exercise 1. No Index on `amount`, Predict the Scan

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE amount >= 95.00;
```

**Suggested answer:** without a matching index on `amount` and on a sizable table, Seq Scan is usually the natural choice. Not every selective predicate has an index path.

### Exercise 2. Single-Row Lookup by Primary Key

```sql
EXPLAIN
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE event_id = 12345;
```

**Hint:** a B-tree PRIMARY KEY index exists; Index Scan normally fits a single-row lookup, and `payload` must be fetched from the heap.

### Exercise 3. Narrow `account_id` Query

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

**Hint:** with `events_account_idx`, looking up ~10 rows usually favors Index Scan. Observe actual rows.

### Exercise 4. Same `category` Column, Two Very Different Frequencies

```sql
EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';

EXPLAIN
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

**Hint:** `standard` is ~91%, `premium` ~9%. The two queries can pick different access paths using the exact same index.

### Exercise 5. Reading `Index Cond` and `Filter`

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, status, payload
FROM scan_lab.events
WHERE account_id = 4321
  AND status = 'DONE';
```

**Hint:** using an index solely on `account_id`, `Index Cond` handles `account_id` while `status` appears in Filter. With additional indexes, the plan may change.

### Exercise 6. Does Bitmap Index Scan Read `payload`?

**Answer:** not as its primary function. It finds matching positions from the index to build a bitmap; `Bitmap Heap Scan` reads the corresponding heap blocks to fetch `payload` and apply required checks.

### Exercise 7. Why Can a Bitmap Beat Index Scan When Many Tuples Match?

**Answer:** it groups heap locations by page, reducing scattered heap visits compared to an index scan jumping TID-by-TID in index order.

### Exercise 8. Does a Bitmap Return Rows Ordered by B-Tree Key?

**Answer:** not guaranteed. It visits the heap in block order; queries with ORDER BY may need a Sort.

### Exercise 9. Does `Recheck Cond` Guarantee the Bitmap Is Lossy?

**Answer:** no. Inspect `Heap Blocks: lossy` and `Rows Removed by Index Recheck` in EXPLAIN ANALYZE.

### Exercise 10. How Do Exact and Lossy Bitmaps Differ?

**Answer:** exact tracks specific offsets/TIDs to check within a block; lossy tracks only block-level presence, requiring more tuple rechecks.

### Exercise 11. `Rows Removed by Filter` vs `Rows Removed by Index Recheck`?

**Answer:** Filter discards rows failing the node's filter predicate; Index Recheck discards tuples after re-verifying the bitmap/index access predicate.

### Exercise 12. Which Condition Can Use `BitmapAnd`?

```sql
SELECT *
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

**Hint:** bitmaps from both single indexes can be combined via BitmapAnd, though the planner can pick another path.

### Exercise 13. Which Condition Can Use `BitmapOr`?

```sql
SELECT *
FROM scan_lab.events
WHERE category = 'premium'
   OR status = 'FAILED';
```

**Hint:** both bitmaps can be combined via BitmapOr; matching both predicates does not produce duplicate output rows.

### Exercise 14. Why Doesn't AND Guarantee BitmapAnd?

**Answer:** the planner compares costs of one index + Filter, composite index, BitmapAnd, and Seq Scan. BitmapAnd has overhead and does not always win.

### Exercise 15. How Does Low `work_mem` Affect Bitmaps?

**Answer:** it can force a bitmap to lose per-offset precision on some pages, degrading to lossy and increasing rechecks. Not every query with low `work_mem` goes lossy.

### Exercise 16. Why Not Raise `work_mem` System-Wide Immediately?

**Answer:** concurrent queries and multiple memory-using nodes per query multiply RAM consumption. Measure workloads and tune within safe scope.

### Exercise 17. Does Index Only Scan Ever Need the Heap?

**Answer:** it may still read the heap to check MVCC visibility if pages are not all-visible. Watch `Heap Fetches`.

### Exercise 18. What Is the Visibility Map Used For in Index Only Scan?

**Answer:** it marks heap pages that are all-visible, letting PostgreSQL skip heap fetches when the index already covers all needed columns.

### Exercise 19. Why Can VACUUM Improve Index Only Scan?

**Answer:** it sets/updates all-visible bits on eligible pages. Still, plan choice depends on statistics, indexes, columns, and cost.

### Exercise 20. Which Index Suits ORDER BY LIMIT?

```sql
SELECT account_id, occurred_at
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

**Hint:** a B-tree on `(account_id, occurred_at DESC)` can deliver the right order and stop after just a few entries.

### Exercise 21. Why Might Bitmap Heap Scan Need a Sort?

**Answer:** bitmaps do not preserve index key order, so ORDER BY can require a Sort node.

### Exercise 22. Must a Query with LIMIT 5 and No ORDER BY Scan the Whole Table?

**Answer:** not necessarily. The executor can stop a Seq Scan early once Limit has received enough rows, depending on plan shape.

### Exercise 23. Does `cost=0.00..100.00` Mean 100 ms?

**Answer:** no. These are planner cost estimate units.

### Exercise 24. Off by 100x on Row Estimates—What Do You Check First?

**Answer:** `ANALYZE` statistics, value skew, query predicates, multi-column dependencies, and generic/custom plans before forcing scan methods.

### Exercise 25. Inspecting `category` Statistics

```sql
SELECT
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname = 'scan_lab'
  AND tablename = 'events'
  AND attname = 'category';
```

**Hint:** check the skewed `standard`/`premium` frequencies; the planner can pick different paths per value.

### Exercise 26. What Does `correlation` Affect?

**Answer:** it partially reflects alignment between column value order and physical row layout; physical clustering lowers random heap access cost.

### Exercise 27. Is Seq Scan on the 3-Row `event_types` Table a Problem?

**Answer:** usually no. Reading a tiny table outright is cheaper than a B-tree lookup, even with a primary key index.

### Exercise 28. Why Does BRIN Frequently Require Rechecks?

**Answer:** BRIN summarizes values per page range, identifying only regions that **might** match; Bitmap Heap Scan must recheck individual tuples.

### Exercise 29. Does `shared hit` Mean Everything Came from RAM with Zero External System I/O?

**Answer:** it only indicates the block was already in shared buffers. `shared read` means it had to be read into shared buffers, though the OS cache may still satisfy that read without touching physical disk.

### Exercise 30. Does `EXPLAIN ANALYZE UPDATE` Modify the Table?

**Answer:** yes. It executes the DML. In a lab, wrap in a transaction and roll back to undo transactional table changes, while keeping remaining costs/side effects in mind.

### Exercise 31. When an Index Scan Node Shows `loops=10000`, What Should You Check?

**Answer:** total inner scan iterations in the nested loop, total buffers, and actual rows per loop. A cheap lookup multiplied by 10,000 can still be expensive.

### Exercise 32. Should You Index Every Column Even Under Heavy Write Workloads?

**Answer:** no. Every index adds storage, WAL, and write/maintenance overhead. Target indexes at expensive queries with proven value.

### Exercise 33. Can Two Runs with `status = $1` Use Different Plans?

**Answer:** yes. Custom plans can account for specific parameter values, whereas generic plans share one plan across values and may pick different access paths.

### Exercise 34. Is `enable_seqscan=off` a Fix for Slow Queries?

**Answer:** not a production fix. It is useful for exploring alternatives in a lab, yet can slow down queries returning many rows.

### Exercise 35. Choosing by Query Profile

Given three queries on a 200,000-row table:

```sql
-- A: find one row.
SELECT event_id, payload
FROM scan_lab.events
WHERE event_id = 12345;

-- B: ~9% group.
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';

-- C: ~91% group.
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

**Hint:** A typically favors Index Scan; B can favor Bitmap Heap Scan; C typically favors Seq Scan. Actual plans still follow `EXPLAIN`, statistics, and system costs.

### Exercise 36. Why Do Those Three Queries Have No Fixed Cutoff Threshold?

**Answer:** table size, caching, cost parameters, physical locality, index design, LIMIT, row width, storage, and statistics all influence the planner. No single percentage threshold holds universally.

### Exercise 37. Comparing a Query Before and After Creating an Index

Run on the lab table in sequence:

```sql
-- 1. Before the category index exists:
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';

-- 2. Create index (once only):
CREATE INDEX events_category_idx
ON scan_lab.events (category);

ANALYZE scan_lab.events;

-- 3. Re-measure the same query:
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

**Hint:** if you already created `events_category_idx` in section 10, **do not create it a second time**; skip the CREATE INDEX step or test on a fresh lab database. Compare plans, rows, buffers, and timings across multiple runs to avoid single-run cache bias.

### Exercise 38. Why Doesn't Having a Composite Index Guarantee the Planner Stops Using BitmapAnd?

**Answer:** costs depend on predicates, statistics, and specific values. The planner remains free to combine single indexes or choose another scan if estimated cheaper.

### Exercise 39. In a Join, Why Can Full-Table Seq Scan Beat Many Index Scans?

**Answer:** joining large portions of data can be far more efficient by scanning each table sequentially once and hash-joining than issuing countless random index lookups.

### Exercise 40. Writing a Meaningful EXPLAIN Report

**Suggested answer:** do not just report "saw a Seq Scan." Document the query, parameters, schema/indexes, row counts, estimated/actual rows, node tree, loops, buffers, multi-run timings, caching state, and why a change makes the overall query faster or slower.

## 34. Combined Query Suite for Self-Comparison

After creating the lesson's indexes, run each query on the lab database and record the actual plan.

### Case 1: Rare Lookup by Primary Key

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE event_id = 54321;
```

Prediction: Index Scan is usually favored.

### Case 2: Few Events by Account

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE account_id = 4321;
```

Prediction: Index Scan is favored when `account_id` is indexed.

### Case 3: Moderate Row Count

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'premium';
```

Prediction: Bitmap Heap Scan is a strong contender when indexed.

### Case 4: Nearly the Whole Table

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, account_id, payload
FROM scan_lab.events
WHERE category = 'standard';
```

Prediction: Seq Scan is normally sensible.

### Case 5: AND Across Two Indexes

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
  AND status = 'FAILED';
```

Prediction: may see BitmapAnd, composite index, or one index with Filter.

### Case 6: OR Across Two Indexes

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, category, status, payload
FROM scan_lab.events
WHERE category = 'premium'
   OR status = 'FAILED';
```

Prediction: BitmapOr can compete strongly.

### Case 7: ORDER BY + LIMIT with Covering Index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id, occurred_at, status, amount
FROM scan_lab.events
WHERE account_id = 4321
ORDER BY occurred_at DESC
LIMIT 5;
```

Prediction: Index Scan or Index Only Scan on the matching composite B-tree, potentially avoiding Sort.

### Case 8: Full-Table COUNT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM scan_lab.events;
```

Prediction: may pick Seq Scan/Parallel Seq Scan or Index Only Scan on a narrow index if the planner estimates it cheaper, depending on visibility map and costs.

### Case 9: Time Range with BRIN

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT event_id, occurred_at, payload
FROM scan_lab.events
WHERE occurred_at >= timestamptz '2025-04-01 00:00:00+00'
  AND occurred_at <  timestamptz '2025-04-02 00:00:00+00';
```

Prediction: may use Bitmap Index Scan on BRIN paired with Bitmap Heap Scan with recheck; depends on table size and other indexes.

### Case 10: Tiny Table

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM scan_lab.event_types
WHERE event_type_id = 2;
```

Prediction: Seq Scan is completely reasonable.

## 35. Access Path Evaluation Checklist in Real Projects

| Question | Suggested action |
| --- | --- |
| Is the table small or large? | Check row/page count; don't force indexes on tiny tables |
| What percentage of rows does the query return? | Check selectivity, estimated vs actual rows |
| Does an index match the predicate? | Inspect `Index Cond` and index definition |
| Index exists yet Seq Scan used? | Compare cost, rows, width, cache, and `ORDER BY` |
| Many random heap fetches? | Evaluate bitmap, composite, or covering index |
| Is the bitmap lossy? | Check `Heap Blocks` exact/lossy and Recheck |
| Filter discarding many rows after index? | Consider composite or partial index |
| Is there ORDER BY LIMIT? | Use a key-ordered B-tree when worthwhile |
| Many returned columns? | Evaluate index-only/`INCLUDE` against write cost |
| Index Only Scan has high Heap Fetches? | Check visibility map, VACUUM, and write rate |
| Multiple AND/OR predicates? | Evaluate BitmapAnd/BitmapOr vs composite index |
| Are statistics fresh? | Run `ANALYZE` after major changes |
| Large gap between estimate and actual? | Check MCV, histograms, extended stats |
| Low correlation? | Random heap access cost may be high |
| Are table/index warm in cache? | Inspect buffers and repeat runs |
| Running on SSD or HDD? | Understand cost parameters per workload |
| Is `work_mem` causing lossy bitmaps? | Measure in local scope; avoid blind global raises |
| Parallel plan chosen? | Inspect workers planned/launched and overhead |
| Query inside a nested loop? | Check `loops` on inner access nodes |
| Prepared statement with skewed params? | Compare custom vs generic plans |
| Does the query modify data while measuring? | Remember EXPLAIN ANALYZE executes DML |
| Duplicate indexes present? | Review before adding another index |
| Partial index applicable? | Query predicate must imply index predicate |
| BRIN applicable? | Fits large range-correlated data |
| Using enable_* flags to override planner? | Keep strictly to lab exploration |
| Measured the full plan? | Do not stare at a single scan node |
| Measured across multiple runs? | Account for caching, concurrency, and variance |
| Does the change slow down writes? | Measure INSERT/UPDATE/WAL/storage |
| What are query frequency and SLA? | Prioritize bottlenecks with real impact |
| Need plan stability across upgrades/data growth? | Monitor and re-evaluate after changes |
| Do you understand why the planner picked this path? | Document evidence from cost, stats, and buffers |

## 36. Summary: Three Access Paths, Three Trade-Offs

### Sequential Scan

`Seq Scan` reads the heap sequentially, fitting when:

- The table is small.
- The query needs most of the rows.
- No suitable index applies.
- Sequential reading beats many scattered heap lookups.

**Do not treat Seq Scan as a bug in itself.**

### Index Scan

`Index Scan` uses an index to locate target tuples, fitting when:

- Few rows match.
- Predicates are selective.
- The index supports the WHERE clause.
- ORDER BY/LIMIT can exploit B-tree ordering.
- Heap fetches remain moderate.

**Do not assume Index Scan always wins when queries return large shares of rows.**

### Bitmap Scan

`Bitmap Index Scan` paired with `Bitmap Heap Scan` builds a bitmap of matching locations and reads the heap by page, fitting when:

- Match counts are moderate and spread across many heap pages.
- Random heap I/O needs reduction.
- Multiple indexes can be combined via BitmapAnd/BitmapOr.
- Preserving index key order is not required.

**Remember to check exact/lossy bitmaps and recheck costs.**

### Index Only Scan: An Additional Access Path

When an index covers all needed data and the visibility map is favorable, `Index Only Scan` reduces heap reads. However, it **can still incur `Heap Fetches`**, and wide indexes carry their own maintenance costs.

### Final Mental Model

```text
SQL + data + statistics + index definitions
                  |
                  v
               Planner
                  |
     Estimate selectivity + I/O/CPU cost
                  |
                  v
         Seq / Index / Bitmap / ...
                  |
                  v
          EXPLAIN ANALYZE BUFFERS
                  |
                  v
   Compare estimate vs actual, read full plan tree
                  |
                  v
    Make evidence-based change and re-measure
```

**Core rule:** whenever you see `Seq Scan`, `Index Scan`, or `Bitmap Heap Scan`, ask **"how many rows does the query need, which heap pages hold those rows, which accesses does an index eliminate, and what sort/join/aggregate work does the rest of the query perform?"**. Answering those questions matters far more than trying to make every query print `Index Scan`.
