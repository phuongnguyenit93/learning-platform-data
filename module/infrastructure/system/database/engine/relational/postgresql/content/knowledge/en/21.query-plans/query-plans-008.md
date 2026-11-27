# Sort, Incremental Sort, Aggregate, and Temporary Memory in PostgreSQL

A PostgreSQL query can read data very quickly yet still spend most of its time **sorting**, **grouping**, **computing aggregates**, or **spilling intermediate data to disk**.

For example, an application needs revenue per customer:

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY total_amount DESC
LIMIT 20;
```

In this short SQL query, PostgreSQL may have to:

1. Locate and filter rows where `status='PAID'`.
2. Group rows sharing the same `customer_id`.
3. Compute `COUNT` and `SUM`.
4. Sort aggregated results by `total_amount DESC`.
5. Return only the top 20 groups.

Depending on data, indexes, and settings, the execution plan may contain `HashAggregate`, `GroupAggregate`, `Sort`, `Incremental Sort`, `Gather Merge`, or other intermediate nodes. If intermediate data exceeds an operation's memory budget, PostgreSQL uses **temporary files** on disk. That frequently drives up I/O and latency significantly.

This lesson focuses on four interconnected topics:

- **Sort** — sorting data and how PostgreSQL chooses an algorithm.
- **Incremental Sort** — exploiting a pre-sorted prefix so only remaining keys are sorted.
- **Aggregate** — differences among `HashAggregate`, `GroupAggregate`, partial/final aggregates, and specialized aggregations.
- **Temporary memory** — how `work_mem`, `hash_mem_multiplier`, spilling, temporary files, and parallelism affect queries.

The goal is neither "eliminate every Sort" nor "just raise work_mem for speed," but **reading evidence from execution plans, understanding trade-offs, and choosing grounded optimizations**.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Identify `Sort`, `Incremental Sort`, `HashAggregate`, `GroupAggregate`, `Aggregate`, `Gather`, and `Gather Merge` nodes in plans.
2. Distinguish `Sort Key`, `Presorted Key`, input ordering, and SQL's `ORDER BY` requirement.
3. Explain common sort execution methods: **quicksort**, **top-N heapsort**, and **external merge**.
4. Understand why `ORDER BY ... LIMIT` can use top-N sort instead of sorting the full set.
5. Explain conditions and benefits of **Incremental Sort**, and spot cases where it does not pay off.
6. Distinguish **HashAggregate** from **GroupAggregate**, along with each strategy's memory/spill risks.
7. Understand `work_mem` as a budget **per eligible operation**, not a single RAM cap per query or session.
8. Distinguish `work_mem` from `shared_buffers`, `temp_buffers`, and `maintenance_work_mem`.
9. Analyze the effect of `hash_mem_multiplier` on eligible hash operations.
10. Read `Sort Method: ... Memory: ...`, `Disk: ...`, `Batches`, and `Buffers: temp read/written`.
11. Monitor temp I/O via `pg_stat_database`, `pg_stat_statements` (if enabled), logging, and appropriate tools.
12. Evaluate B-tree indexes, prefix order, collation, NULL placement, and parallel execution.
13. Design a lab testing two `work_mem` settings with `SET LOCAL` and comparing the same query.
14. Propose optimizations grounded in data, statistics, SQL semantics, and realistic memory limits.

**Scope:** Modern PostgreSQL; Incremental Sort was introduced in PostgreSQL 13. Execution plan details, memory accounting, and planner optimizations vary across versions. Lab commands are strictly for test databases; never copy illustrative tuning values straight to production.

---

## 2. Where Do Sorting and Aggregation Appear in a Query?

Look at this SQL:

```sql
SELECT
    customer_id,
    COUNT(*) AS orders,
    SUM(amount) AS revenue
FROM sales
WHERE status = 'PAID'
GROUP BY customer_id
HAVING SUM(amount) > 1000
ORDER BY revenue DESC
LIMIT 10;
```

In logical SQL evaluation order, you can picture:

```text
FROM sales
    |
    v
WHERE status='PAID'
    |
    v
GROUP BY customer_id
    |
    v
COUNT, SUM
    |
    v
HAVING SUM(amount)>1000
    |
    v
ORDER BY revenue DESC
    |
    v
LIMIT 10
```

This is **logical processing order**, not a fixed list of physical plan nodes.

The planner may turn grouping into `HashAggregate`, ordering into `Sort`, or feed an index-ordered stream into `GroupAggregate`. With parallel execution, it may also use `Partial Aggregate` and `Finalize Aggregate`.

### 2.1. SQL Does Not Dictate Sort/GroupAggregate Algorithms

The clause:

```sql
GROUP BY customer_id
```

only requires correct grouping. It does not force PostgreSQL to:

- Sort then aggregate.
- Hash then aggregate.
- Return groups ordered by `customer_id`.

Similarly, `ORDER BY` specifies **result ordering**, not necessarily a `Sort` node: if input already arrives in matching order from an index or prior step, the planner can skip sorting.

### 2.2. Overview of Execution Options

```text
                Input data
                    |
         +----------+----------+
         |                     |
         v                     v
     Unsorted          Sorted by group key
         |                     |
    +----+------+              |
    |           |              |
    v           v              v
HashAggregate  Sort      GroupAggregate
    |           |              |
    |           v              |
    |     GroupAggregate       |
    +-----------+--------------+
                |
                v
        ORDER BY total revenue
                |
              Sort
                |
              Limit
```

Depending on the query, branches may contain additional nodes, or the planner may eliminate unnecessary steps.

---

## 3. Self-Contained Practice Dataset

We use a simulated sales table with customer, region, status, timestamp, amount, and product columns.

> **Warning:** `DROP TABLE IF EXISTS` removes any lab table with that name. Run strictly in a dedicated practice database, never in production.

### 3.1. Create Schema and Table

```sql
CREATE SCHEMA IF NOT EXISTS plan_memory_lab;

DROP TABLE IF EXISTS plan_memory_lab.sales;

CREATE TABLE plan_memory_lab.sales (
    sale_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELED')),
    product_id INTEGER NOT NULL,
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL
);
```

### 3.2. Load 80,000 Reproducible Rows

```sql
INSERT INTO plan_memory_lab.sales (
    customer_id, region, status, product_id, amount, created_at
)
SELECT
    ((g.n * 37) % 1000) + 1 AS customer_id,
    (ARRAY['north','south','east','west'])
        [((g.n * 7) % 4) + 1] AS region,
    CASE
        WHEN g.n % 10 < 6 THEN 'PAID'
        WHEN g.n % 10 < 9 THEN 'NEW'
        ELSE 'CANCELED'
    END AS status,
    ((g.n * 13) % 120) + 1 AS product_id,
    (((g.n * 89) % 250000)::NUMERIC / 100)::NUMERIC(12,2)
        AS amount,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n * INTERVAL '1 minute') AS created_at
FROM generate_series(1, 80000) AS g(n);

ANALYZE plan_memory_lab.sales;
```

The goal is enough rows to observe Sort/HashAggregate behavior without overloading an ordinary lab machine. Actual load depends on hardware.

### 3.3. Initial Verification

```sql
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT customer_id) AS customer_count,
    MIN(created_at) AS first_time,
    MAX(created_at) AS last_time
FROM plan_memory_lab.sales;
```

`COUNT(*)` will be 80,000 if loaded once after resetting. Never extrapolate these simulated numbers to production cardinality.

### 3.4. Create Indexes Supporting Different Access Paths

```sql
-- Can supply customer_id order, though not sorted by amount.
CREATE INDEX idx_sales_customer
ON plan_memory_lab.sales (customer_id);

-- Order suitable for ORDER BY most recent time.
CREATE INDEX idx_sales_created_desc
ON plan_memory_lab.sales (created_at DESC, sale_id DESC);

-- Order by region then time.
CREATE INDEX idx_sales_region_created
ON plan_memory_lab.sales (region, created_at DESC);

ANALYZE plan_memory_lab.sales;
```

For any query, whether the planner picks an index depends on cost. Never assume all three indexes are always used.

---

## 4. The Sort Node in EXPLAIN

Start with a query lacking an index matching the full sort condition:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, customer_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;
```

An **illustrative** plan might look like:

```text
Sort
  Sort Key: amount DESC, sale_id DESC
  Sort Method: quicksort  Memory: ...kB
  Buffers: shared hit=...
  -> Seq Scan on sales
       Buffers: shared hit=...
Planning Time: ...
Execution Time: ...
```

This is **not measured output** from a live run. Exact node names, ordering, and figures depend on data, version, indexes, memory, and planner decisions.

### 4.1. Sort Key

`Sort Key: amount DESC, sale_id DESC` shows PostgreSQL must sort by two keys:

1. `amount` descending.
2. On ties in `amount`, `sale_id` descending.

The `sale_id` tiebreaker ensures deterministic order when amounts match. With only `ORDER BY amount DESC`, tied rows can return in arbitrary order.

### 4.2. What Feeds Input into Sort?

Beneath Sort you might see:

- `Seq Scan`.
- `Index Scan`.
- `Hash Join` or `Merge Join`.
- `Aggregate`.
- `Gather`.
- Other nodes.

Sort only processes **the row stream emitted by its child node**. Do not read a Sort node and assume every table row was sorted: rows may have been filtered earlier.

### 4.3. Sort Method

With `EXPLAIN ANALYZE`, you may see:

```text
Sort Method: quicksort  Memory: ...
Sort Method: top-N heapsort  Memory: ...
Sort Method: external merge  Disk: ...
```

These lines report the observed sort execution method:

- **quicksort**: common in-memory sort.
- **top-N heapsort**: retains only the best N candidates when only a small leading count is needed.
- **external merge**: sort spilling intermediate runs to disk.

Different PostgreSQL versions and queries may display other variants. What matters is checking **whether the sort spilled and where memory/disk was spent**.

---

## 5. In-Memory Sort vs External Sort

A Sort must hold enough row/key data to order its stream. When the dataset fits within the sort's memory limit, PostgreSQL completes it in RAM.

When data exceeds expected memory, the engine writes sorted runs to temporary disk files and merges them.

### 5.1. In-Memory Sort

```text
Input rows
    |
    v
Buffer data within sort memory budget
    |
    v
Sort in RAM
    |
    v
Emit ordered output
```

Typically reports `Sort Method: quicksort Memory: ...`.

### 5.2. External Merge Sort

```text
Input exceeds sort memory budget
    |
    v
Split into sorted runs
    |
    v
Write intermediate runs to temporary files
    |
    v
Merge runs
    |
    v
Emit ordered output
```

The plan may show:

```text
Sort Method: external merge  Disk: ...kB
Buffers: temp read=... written=...
```

An external sort is not automatically a bug; on huge datasets, spilling to disk can be far smarter than reserving gigabytes of RAM for one query. What matters is **cost relative to latency SLOs, throughput, and available memory**.

### 5.3. Never Convert Disk Directly into work_mem by Simple Addition

If EXPLAIN prints `Disk: 120MB`, do not conclude setting `work_mem = 121MB` guarantees an in-memory sort:

- In-memory structures differ in layout from temp files.
- Overhead exists for tuple descriptors, keys, pointers, and alignment.
- Algorithms and memory allocation strategies differ.
- Multiple sort nodes or parallel workers may exist.
- PostgreSQL version and sort expressions affect memory footprint.

The right way is a **controlled benchmark** in an equivalent environment, not a single universal conversion factor.

---

## 6. Top-N Heapsort: ORDER BY Combined with LIMIT

If only the top 20 highest-amount orders are needed:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC
LIMIT 20;
```

Without a matching ordered index, PostgreSQL can use **top-N heapsort** instead of fully sorting all 80,000 rows.

Concept:

```text
Read all candidate rows
     |
     v
Maintain best N rows in memory
     |
     v
Emit N rows in requested order
```

### 6.1. Top-N Does Not Mean Skipping Table Scans

Without an ordered access path or selective filter cutting input, the engine still inspects all candidate rows to be sure which 20 rank highest.

Savings come primarily from **avoiding buffering and sorting the entire result set**.

### 6.2. Large LIMIT or Large OFFSET

```sql
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC
LIMIT 20 OFFSET 50000;
```

To return positions 50,001 through 50,020, PostgreSQL must rank all preceding rows too. A bounded sort now has to retain far more candidates than `LIMIT 20 OFFSET 0`.

Do not assume a small `LIMIT` is always cheap when `OFFSET` is huge.

### 6.3. Finding Top-N via Index

If you need:

```sql
SELECT sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY created_at DESC, sale_id DESC
LIMIT 20;
```

an index:

```sql
CREATE INDEX idx_sales_created_desc
ON plan_memory_lab.sales(created_at DESC, sale_id DESC);
```

lets PostgreSQL read the first 20 rows directly in order without sorting everything. That is the strength of **B-tree order**.

Still, if a query selects most of the table or many unindexed columns, the planner may stick with sequential scan + sort because index access incurs heavy random I/O.

### 6.4. FETCH FIRST ... WITH TIES

If tied rows at the cutoff must all be returned:

```sql
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC
FETCH FIRST 20 ROWS WITH TIES;
```

Output may exceed 20 rows. Optimization mechanics reflect tie semantics; never treat `WITH TIES` and `LIMIT 20` as identical.

---

## 7. ORDER BY and B-Tree: Avoiding Sort When Order Exists

A B-tree index can supply rows already ordered by its keys.

Example:

```sql
SELECT sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY created_at DESC, sale_id DESC
LIMIT 30;
```

This can use `Index Scan` or `Index Only Scan` on `idx_sales_created_desc` when suitable.

### 7.1. Ordered Indexes Do Not Replace ORDER BY Semantically

If you omit `ORDER BY` from SQL, output order is **never guaranteed**, even if one run happens to use an index scan.

Output ordering is part of the **SELECT contract** only when `ORDER BY` is specified. Never rely on physical table order, current index scans, or accidental `GroupAggregate` order.

### 7.2. Composite B-Tree and Leading Prefixes

An index:

```sql
ON sales(region, created_at DESC)
```

orders rows by:

1. `region`.
2. Within each region, `created_at DESC`.

It aligns with:

```sql
ORDER BY region ASC, created_at DESC
```

or compatible reverse-scan directions matching sort order and NULL placement.

However, it **does not order the whole table by `created_at DESC`** because rows are grouped by `region` first.

### 7.3. Collation and NULL Ordering

PostgreSQL checks:

- `ASC` vs `DESC`.
- `NULLS FIRST` vs `NULLS LAST`.
- Text collation.
- Expressions and operator families.

By default in PostgreSQL, `ASC` pairs with `NULLS LAST` and `DESC` pairs with `NULLS FIRST`. An index with mismatched NULL ordering may fail to satisfy a query's order without sorting.

Example:

```sql
CREATE INDEX idx_sales_time_nullslast
ON plan_memory_lab.sales (created_at DESC NULLS LAST);
```

This index explicitly specifies `DESC NULLS LAST`. In our lab `created_at` is `NOT NULL` so NULL placement does not matter yet, yet it is crucial for nullable columns in production.

### 7.4. Expression ORDER BY

If a query sorts by:

```sql
ORDER BY lower(region)
```

a B-tree on raw `region` does not provide exact `lower(region)` ordering across all collations and case variations. You may need an expression index if that pattern is critical:

```sql
CREATE INDEX idx_sales_lower_region
ON plan_memory_lab.sales ((lower(region)));
```

Every index increases write maintenance and storage, so inspect plans and workloads before adding one.

### 7.5. Index Scan vs Seq Scan + Sort: A Cost Trade-Off

Index order avoids Sort, yet scanning many rows via Index Scan causes random heap fetches. When almost the whole table must be returned, Seq Scan + Sort is often cheaper.

Thus: **having an index matching ORDER BY does not force PostgreSQL to use it**.

---

## 8. What Is Incremental Sort?

**Incremental Sort** exploits an input stream already sorted by a **prefix of the requested ORDER BY**, then sorts only the remaining keys within each group sharing the same prefix.

Suppose you want:

```sql
ORDER BY customer_id ASC, amount DESC
```

and input already arrives ordered by:

```text
customer_id ASC
```

Each customer forms a group sharing that prefix key. PostgreSQL sorts `amount DESC` **inside each `customer_id` group**, rather than sorting the entire table on both columns at once.

### 8.1. Model

```text
Input already sorted by customer_id:

customer 1: [amount 20, amount 90, amount 15]
customer 2: [amount 40, amount 10]
customer 3: [amount 70, amount 30, amount 80]

Incremental Sort on customer_id, amount DESC:

customer 1: [90,20,15]
customer 2: [40,10]
customer 3: [80,70,30]

Concatenated groups by customer_id:
    (1,90),(1,20),(1,15),
    (2,40),(2,10),
    (3,80),(3,70),(3,30)
```

### 8.2. Which Part Is Already Sorted?

- `Presorted Key`: key prefix guaranteed sorted by the input stream.
- `Sort Key`: full ordering that the Incremental Sort node must emit.

Illustrative plan:

```text
Incremental Sort
  Sort Key: customer_id, amount DESC
  Presorted Key: customer_id
  Full-sort Groups: ...
  Pre-sorted Groups: ...
  -> Index Scan using idx_sales_customer on sales
```

Instrumentation field names vary by version and grouping strategy. Not every EXPLAIN displays identical lines.

### 8.3. Potential Benefits

- Avoids holding the entire input in memory when prefix groups are reasonably sized.
- Cuts total sorting work when input is partially ordered.
- Can emit early groups sooner than a full Sort in suitable plans.
- Paired with `LIMIT`, can stop early without sorting unneeded tail groups.

### 8.4. Limitation: Oversized Prefix Groups

If 99% of rows share one `customer_id`, Incremental Sort ends up sorting one giant group. Memory and cost savings vanish, potentially performing worse than alternatives.

Effectiveness depends on:

- Number of distinct prefix groups.
- Size and distribution of each group.
- How the input path supplies order.
- Extra columns needing sorting.
- `LIMIT` and filter predicates.
- `work_mem`, disk I/O, and index-scan cost.

Never assume Incremental Sort is always faster than full Sort.

---

## 9. Lab: Incremental Sort Using a Prefix Index

Our lab has:

```sql
CREATE INDEX idx_sales_customer
ON plan_memory_lab.sales(customer_id);
```

Try:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id, amount DESC;
```

PostgreSQL **may** choose:

```text
Incremental Sort
  Sort Key: customer_id, amount DESC
  Presorted Key: customer_id
  -> Index Scan using idx_sales_customer ...
```

Or it may choose:

```text
Sort
  Sort Key: customer_id, amount DESC
  -> Seq Scan ...
```

Both are valid; the planner decides by cost.

### 9.1. Comparing with Incremental Sort Disabled in a Lab Transaction

```sql
BEGIN;

SET LOCAL enable_incremental_sort = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id, amount DESC;

ROLLBACK;
```

`SET LOCAL` scopes the change to the current transaction. After ROLLBACK, the setting reverts.

### 9.2. Observing an Index-Input Plan

If the planner prefers Seq Scan due to lower cost, you can discourage one plan class **strictly for learning**:

```sql
BEGIN;

SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id, amount DESC;

ROLLBACK;
```

This is not a production tuning recommendation. If index scan + incremental sort runs slower than seq scan + full sort, the planner chose wisely by avoiding it.

### 9.3. Why Can Full Sort Win?

Reading 80,000 rows in `customer_id` index order can incur heavy random heap page accesses. A sequential scan plus in-memory Sort can easily finish faster.

Always evaluate **total plan cost**, not just RAM inside the Sort node.

### 9.4. Incremental Sort and LIMIT

```sql
SELECT customer_id, sale_id, amount
FROM plan_memory_lab.sales
ORDER BY customer_id ASC, amount DESC
LIMIT 25;
```

With input pre-sorted by `customer_id` and Incremental Sort chosen, PostgreSQL may only need to finish enough leading groups to emit 25 rows. A full Sort without ordered input would have to inspect all rows to find the global top 25.

Actual gain depends on prefix groups, plan, and filters; there is no fixed multiplier.

---

## 10. Incremental Sort Does Not Only Come from Indexes

Ordered input can come from:

- An ordered Index Scan.
- A Merge Join or an already-sorted branch.
- Grouping/merge operations preserving order.
- `Gather Merge` combining ordered worker streams.
- Other paths carrying compatible pathkeys.

The requirement is not "must have an index," but **the plan can prove input is already sorted by a prefix of the required order**.

### 10.1. Presorted Key Must Match Semantics Exactly

Two expressions looking alike yet differing in:

- Collation.
- `ASC`/`DESC`.
- `NULLS` placement.
- Expression form.
- Operator class / order family.

may not supply matching ordering.

For instance, an index on `lower(region)` does not provide ordering for raw `region` under a case-sensitive collation.

### 10.2. Incremental Sort and Cardinality Misestimation

The planner must estimate prefix group counts and sizes. If it expects thousands of tiny groups when reality has a few massive groups, Incremental Sort can perform poorly.

Sources of drift:

- Stale statistics.
- Skewed distributions.
- Multi-column correlations.
- Shifting parameter values.
- Expressions lacking dedicated statistics.

Inspect `estimated rows` vs `actual rows`, `n_distinct`, MCVs, and extended statistics when needed.

### 10.3. Should You Disable enable_incremental_sort System-Wide?

Do not treat `enable_incremental_sort=off` as a universal trick. It helps as a **diagnostic test** or scoped temporary workaround for a verified regression, subject to testing and rollback plans.

The true root cause is usually statistics or index/order mismatch, not the Incremental Sort feature itself.

---

## 11. Aggregate: Collapsing Many Rows into Summary Results

Common aggregates include:

```sql
COUNT(*)
SUM(amount)
AVG(amount)
MIN(amount)
MAX(amount)
```

Without GROUP BY:

```sql
SELECT SUM(amount)
FROM plan_memory_lab.sales;
```

a plain `Aggregate` node typically appears.

With GROUP BY:

```sql
SELECT customer_id, COUNT(*), SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

the planner picks `HashAggregate` or `GroupAggregate` depending on cost, ordering, group count, memory, and other factors.

### 11.1. Two Common Strategies

```text
           Input rows
              |
        +-----+------+
        |            |
        v            v
   HashAggregate    Sort by group key
        |            |
  Hash table         v
  per group      GroupAggregate
        |            |
        v            v
      Aggregate results
```

Both must yield the **exact same logical results** for SUM/COUNT on well-defined types, aside from valid numeric order sensitivity such as floating-point summation order.

### 11.2. GROUP BY Without ORDER BY Does Not Guarantee Order

Even if one run uses `GroupAggregate` emitting groups in `customer_id` order, SQL does not guarantee output order without a top-level `ORDER BY`.

Write:

```sql
SELECT customer_id, COUNT(*)
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY customer_id;
```

if the client relies on `customer_id` ordering.

---

## 12. How Does HashAggregate Work?

`HashAggregate` builds an **in-memory hash table** mapping each group key to its aggregate state:

```text
Key customer_id=1    -> count=80, sum=...
Key customer_id=2    -> count=80, sum=...
Key customer_id=3    -> count=80, sum=...
...
```

Each input row probes its group key's bucket and updates the running SUM/COUNT state.

### 12.1. When Is HashAggregate Usually Favorable?

- Input is not sorted by the group key.
- Group count can be hashed efficiently.
- Downstream steps do not need group-key order, or hashing beats sorting.
- Aggregates support hashed execution.

### 12.2. What Can the Plan Look Like?

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, COUNT(*) AS order_count,
       SUM(amount) AS total_amount
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Example plan shape:

```text
HashAggregate
  Group Key: customer_id
  Batches: ...
  Memory Usage: ...kB
  Disk Usage: ...kB
  -> Seq Scan on sales
```

When group counts or aggregate states grow large, `HashAggregate` can split into **batches** and spill to disk in PostgreSQL versions supporting disk-based hash aggregation.

Do not assume every `HashAggregate` stays in RAM or every `HashAggregate` has `Disk Usage > 0`.

### 12.3. HashAggregate Has No Inherent Ordering

A hash table does not store groups sorted by `customer_id`. If the query asks for:

```sql
GROUP BY customer_id
ORDER BY customer_id;
```

the planner weighs adding a Sort after hashing versus choosing `GroupAggregate` to reuse ordering.

### 12.4. HashAggregate Can Spill Because of Group Count, Not Just Row Count

A 10-million-row table with only 5 regions holds just 5 group states. Conversely, 100,000 rows where nearly every row has a unique group key creates huge numbers of group states.

Distinguish:

- **Input row count**: rows read.
- **Group cardinality**: actual distinct groups.
- **Aggregate state size**: memory retained per group.

All three affect memory and time without a fixed ratio.

---

## 13. How Does GroupAggregate Work?

`GroupAggregate` processes rows already sorted or delivered in order matching the group keys.

Example input:

```text
customer_id amount
1           20
1           10
1           40
2           50
2           15
3            5
```

Because rows sharing `customer_id` arrive consecutively, the engine aggregates the current group and emits its result as soon as the key changes.

### 13.1. When Is GroupAggregate Worth Choosing?

- Input arrives sorted from a B-tree or upstream node.
- Input can be sorted cheaply.
- Output order benefits subsequent steps.
- `HashAggregate` is unfavorable on memory or cost.
- Aggregate/grouping clauses require ordered processing.

### 13.2. Plan May Use Sort + GroupAggregate

```text
GroupAggregate
  Group Key: customer_id
  -> Sort
       Sort Key: customer_id
       -> Seq Scan
```

Sort reads and orders rows by `customer_id`; then `GroupAggregate` streams consecutive groups.

### 13.3. Or Index Scan + GroupAggregate

With an index on `customer_id`, the planner can pick:

```text
GroupAggregate
  Group Key: customer_id
  -> Index Scan using idx_sales_customer
```

No extra Sort is needed because input already arrives ordered. Still, Index Scan has I/O cost; if it incurs heavy random page reads, `HashAggregate + Seq Scan` can still win.

### 13.4. Experimenting by Disabling hashagg Locally

```sql
BEGIN;

SET LOCAL enable_hashagg = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, COUNT(*), SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id;

ROLLBACK;
```

The goal is **inspecting alternative plans**, not claiming it is faster or safe to set system-wide.

---

## 14. HashAggregate vs GroupAggregate: Decision Comparison

| Criterion | HashAggregate | GroupAggregate |
| --- | --- | --- |
| Needs input sorted by group key? | No | Yes |
| Main intermediate structure | Hash table of group states | Sequential group stream and current state |
| Spill behavior | Can batch/spill when hash memory is tight | Input Sort can spill; aggregate state also uses memory |
| Output order SQL-guaranteed? | No, unless ORDER BY is present | No, unless ORDER BY is present |
| Advantage when input has index order | Not necessarily | Can eliminate Sort |
| Advantage with few groups | Usually strong | Also good if input is already sorted |
| Advantage with many large groups | Depends on memory and distribution | Depends on sort/scan cost |
| When ORDER BY aggregate result | Usually needs Sort afterward | Also usually needs Sort afterward |

### 14.1. GROUP BY and ORDER BY on Different Keys

```sql
SELECT customer_id, SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY revenue DESC;
```

Even if `GroupAggregate` reads input ordered by `customer_id`, output must be sorted by `revenue`. Ordering by an **aggregated value** still requires a sort step; a `customer_id` index cannot order by `SUM(amount)` directly.

### 14.2. Where Is HAVING Applied?

```sql
SELECT customer_id, SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id
HAVING SUM(amount) > 500
ORDER BY revenue DESC;
```

`HAVING` filters groups after logical aggregation. EXPLAIN may show `Filter` and `Rows Removed by Filter` on the aggregate node.

`HAVING` can shrink the number of groups entering a downstream Sort, yet does not reduce input rows read/aggregated beforehand.

### 14.3. WHERE Shrinks Input Before Aggregation

If the query filters early:

```sql
WHERE status = 'PAID'
```

fewer rows enter aggregation. Moving an eligible row-level condition into `WHERE` instead of filtering after aggregation saves work, though never alter semantics between **row filtering** and **group filtering**.

---

## 15. Aggregates Requiring Internal Ordering

Compare:

```sql
SELECT
    customer_id,
    array_agg(sale_id ORDER BY created_at DESC, sale_id DESC)
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

against:

```sql
SELECT
    customer_id,
    array_agg(sale_id)
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

In the first query, **element ordering inside the array** is part of the requirement. In the second, array element order is unguaranteed without an `ORDER BY` inside the aggregate.

### 15.1. Order-Sensitive Aggregates

Example:

```sql
SELECT
    customer_id,
    string_agg(product_id::TEXT, ',' ORDER BY product_id) AS products
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Ordered aggregates like `string_agg` and `array_agg` can require internal sorting inside the aggregate node or exploit plan ordering depending on PostgreSQL version.

Do not assume **seeing no outer Sort node** means zero sorting happened internally. Understand aggregate syntax, instrumentation, and your server version's optimizer behavior.

### 15.2. DISTINCT Inside Aggregates

```sql
SELECT
    customer_id,
    COUNT(DISTINCT product_id) AS distinct_products
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

`COUNT(DISTINCT ...)` deduplicates within each group, adding work and memory beyond `COUNT(*)`. Some `DISTINCT`/`ORDER BY` aggregates also restrict hash aggregation and parallel partial aggregation.

### 15.3. GROUP BY Does Not Order Elements Inside array_agg

Example:

```sql
SELECT customer_id, array_agg(product_id)
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY customer_id;
```

The outer `ORDER BY` sorts **result rows by `customer_id`**. It **does not guarantee** elements inside `array_agg` are ordered by `product_id`.

To order array elements, write:

```sql
array_agg(product_id ORDER BY product_id)
```

---

## 16. DISTINCT and DISTINCT ON Related to Sort/Aggregate

`DISTINCT` eliminates duplicate result rows:

```sql
SELECT DISTINCT customer_id
FROM plan_memory_lab.sales;
```

The planner picks hash-based deduplication or sort + unique depending on query and cost.

### 16.1. DISTINCT ON: Keeping One Row per Group

PostgreSQL supports:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id, sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY customer_id, created_at DESC, sale_id DESC;
```

Meaning: for each `customer_id`, keep the first row under that sort order—here the latest order (breaking timestamp ties by highest `sale_id`).

Important:

- `DISTINCT ON` is PostgreSQL-specific syntax.
- `DISTINCT ON` expressions must match the leading `ORDER BY` expressions per PostgreSQL rules.
- Without a deterministic `ORDER BY`, which row gets kept is unpredictable.
- The planner may use Sort + Unique or an already-ordered index path.

### 16.2. Index Supporting DISTINCT ON

An index:

```sql
CREATE INDEX idx_sales_customer_latest
ON plan_memory_lab.sales (
    customer_id, created_at DESC, sale_id DESC
);
```

can supply the needed order. Still, it consumes storage and adds INSERT/UPDATE cost, and is not mandatory for `DISTINCT ON` to work.

### 16.3. DISTINCT + ORDER BY

```sql
SELECT DISTINCT customer_id
FROM plan_memory_lab.sales
ORDER BY customer_id;
```

can use a single strategy satisfying both uniqueness and ordering. Exact choice depends on indexes, data, and planner; do not assume two Sort nodes always appear.

---

## 17. GROUPING SETS, ROLLUP, and CUBE

PostgreSQL supports multiple aggregation levels in one query:

```sql
SELECT
    region,
    status,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY ROLLUP (region, status)
ORDER BY region NULLS LAST, status NULLS LAST;
```

`ROLLUP (region, status)` produces levels:

1. `(region, status)`
2. `(region)`
3. Grand total

Subtotal/total rows insert NULLs for rolled-up dimensions; if base data also holds NULLs, disambiguate using `GROUPING(...)`.

### 17.1. MixedAggregate

Plans may display `MixedAggregate`, `GroupAggregate`, or other strategies for grouping sets depending on version and expressions.

Do not treat seeing a different Aggregate node as an error; grouping sets expand the execution strategy space.

### 17.2. Distinguishing Real NULLs from Rollup NULLs

```sql
SELECT
    region,
    status,
    GROUPING(region, status) AS grouping_mask,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY ROLLUP (region, status)
ORDER BY region NULLS LAST, status NULLS LAST;
```

`GROUPING` identifies which columns were rolled up at each row—far safer than guessing from NULLs in output.

---

## 18. Parallel Aggregate and Gather Merge

On sufficiently large tables with parallel-safe aggregates, PostgreSQL can split work across multiple workers.

A plan might include:

```text
Finalize GroupAggregate
  Group Key: ...
  -> Gather Merge
       Workers Planned: ...
       -> Sort
            Sort Key: ...
            -> Partial HashAggregate / Partial GroupAggregate
                 -> Parallel Seq Scan ...
```

This is an **illustrative** diagram, not a mandatory plan shape.

### 18.1. Partial Aggregate

Workers compute **intermediate partial aggregate states** on their slice of rows, such as local counts and sums.

### 18.2. Finalize Aggregate

The finalize node merges intermediate states into the final result.

Not every aggregate supports partial/finalize execution; eligibility depends on aggregate function definitions and query features like `DISTINCT`/`ORDER BY` inside aggregates.

### 18.3. Gather vs Gather Merge

- `Gather` collects worker results without preserving global key ordering.
- `Gather Merge` merges **pre-sorted worker streams** into one globally ordered stream.

When `ORDER BY` is present, `Gather Merge` can preserve order across workers; later steps may still add another Sort if a different key order is needed.

### 18.4. Memory Scales with Workers

Each worker can execute its own sort/hash operations. A parallel query does **not** split one single `work_mem` allowance across all workers.

Consequently, more parallelism can cut wall-clock time while raising peak CPU, temp I/O, and RAM usage on the server.

---

## 19. Window Functions Can Require Sort Too

Example:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    sale_id,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY amount DESC, sale_id DESC
    ) AS rank_in_customer
FROM plan_memory_lab.sales;
```

To compute `row_number` per customer ordered by `amount DESC`, the executor needs a stream ordered by the window's `PARTITION BY` and `ORDER BY`.

Plans may contain `Sort`/`Incremental Sort` feeding `WindowAgg`, depending on indexes and data.

### 19.1. ORDER BY Inside OVER Is Not Output ORDER BY

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY amount DESC
)
```

defines ordering for the window function, **not** the guaranteed return order of the outer SELECT.

If the client requires ordered rows:

```sql
ORDER BY customer_id, amount DESC, sale_id DESC
```

place `ORDER BY` on the outer query. The planner can reuse existing ordering, yet SQL semantics must be stated explicitly.

### 19.2. Multiple Window Definitions Can Require Multiple Sorts

If a query uses two window functions requiring incompatible orderings, PostgreSQL may insert separate Sort steps. One Sort cannot always satisfy every window clause.

---

## 20. work_mem: Not "Maximum RAM per Query"

`work_mem` is a critical setting for sorts and hashes, yet frequently misunderstood.

### 20.1. Practical Definition

`work_mem` sets the base memory limit **per memory-consuming query operation**—such as each Sort or eligible hash operation under current rules.

It is **not**:

- Total RAM PostgreSQL may use.
- Total RAM one connection may use.
- Total RAM one SQL statement may use.
- Buffer cache size.
- Total temp file limit across the database.

A query with **multiple sort/hash nodes** can allocate multiples of this budget. Some nodes execute in different phases, so peak usage must be measured rather than simply assuming every node peaks simultaneously.

### 20.2. Thought Experiment on Peak Memory

Suppose:

```text
work_mem = 32 MB

One query has:
  Sort A
  Sort B
  HashAggregate C

And uses parallel workers.
```

You cannot claim "this query uses at most 32 MB." Each operation can use its own allowance, and hash operations are further scaled by `hash_mem_multiplier`.

Under dozens of concurrent queries, total RAM risk is far higher than one isolated sort.

### 20.3. Inspecting Settings

```sql
SHOW work_mem;
SHOW hash_mem_multiplier;
SHOW temp_file_limit;
SHOW temp_tablespaces;
```

Privileges to modify settings depend on parameter class and DBA policy. `SHOW` inspects current session settings.

### 20.4. Transaction-Scoped Changes for Lab Testing

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;

ROLLBACK;
```

`SET LOCAL` confines the change to the current transaction. `64kB` is an artificially tiny value **intentionally forcing spill pressure in the lab**, never a system-wide setting.

### 20.5. Comparing with 32 MB

```sql
BEGIN;

SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;

ROLLBACK;
```

Observe:

- Sort Method.
- Memory or Disk.
- Temp read/written.
- Execution time.
- Buffers.

Treat this strictly as a **technical experiment**. Never assume that because 32MB helped one Sort, 32MB is safe for every query at all times.

---

## 21. hash_mem_multiplier: Separate Memory Budget for Hashes

Eligible hash operations in PostgreSQL can derive their memory budget from `work_mem × hash_mem_multiplier` per version and memory rules.

Conceptual example:

```text
work_mem = 16 MB
hash_mem_multiplier = 2.0

Expected threshold for eligible hash operations
  follows a ~32 MB baseline.
```

This does not promise every `HashAggregate` consumes 32MB or pre-allocates that amount.

### 21.1. Why Have a Multiplier?

Hash joins and hash aggregates have different memory profiles than sorts. Allowing a higher threshold can prevent multi-batch disk spills.

However, when many hash nodes, parallel workers, or sessions run concurrently, raising the multiplier raises peak RAM pressure too.

### 21.2. Inspecting a HashAggregate Plan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    sale_id,
    COUNT(*) AS n,
    SUM(amount) AS total
FROM plan_memory_lab.sales
GROUP BY sale_id;
```

Because `sale_id` is unique, group count is high. The planner may pick `GroupAggregate` using primary-key order or `HashAggregate` based on cost.

To force-observe hashing in a lab, you can adjust planner flags inside a transaction, though there is no guarantee every query uses HashAggregate from changing a single parameter.

### 21.3. High Group-Cardinality Query to Observe Hash Pressure

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    product_id,
    COUNT(*) AS n,
    SUM(amount) AS total
FROM plan_memory_lab.sales
GROUP BY customer_id, product_id;

ROLLBACK;
```

Across 80,000 rows, many groups exist. If HashAggregate is chosen and spills, EXPLAIN displays `Batches`, `Memory Usage`, and `Disk Usage`.

If the planner chooses Sort + GroupAggregate instead, that is also reasonable; observe and explain the costs rather than claiming this SQL must spill a hash.

---

## 22. work_mem vs shared_buffers, temp_buffers, and maintenance_work_mem

| Parameter | Primary role | Common misconception to avoid |
| --- | --- | --- |
| `shared_buffers` | Shared cache for table/index pages | Not direct workspace for each Sort |
| `work_mem` | Base threshold per sort/hash operation | Not a per-query or per-session global cap |
| `hash_mem_multiplier` | Budget multiplier for eligible hash operations | Does not raise Sort limits |
| `temp_buffers` | Buffers for session temporary tables | Not the memory budget for external sort |
| `maintenance_work_mem` | Maintenance tasks like CREATE INDEX/VACUUM per rules | Does not speed up ordinary SELECT Sorts |
| `autovacuum_work_mem` | Memory budget for autovacuum workers when configured | Not used for tuning ORDER BY |
| `temp_file_limit` | Cap on temporary file size per backend/process | Not a RAM limit and not cluster-wide |

### 22.1. Why Does the Word "temp" Cause Confusion?

**Temporary tables** and **temporary spill files** are completely different concepts:

- `CREATE TEMP TABLE` creates a session/transaction-scoped relation with its own storage lifecycle.
- External sorts or hash spills create internal executor working files.
- `temp_buffers` caches temporary table pages.
- `work_mem` governs memory before sort/hash operations spill to working files.
- `temp_file_limit` caps temp file disk footprint per process; it is not a switch disabling temp tables.

Never adjust `temp_buffers` to fix an external Sort spill without separating the two layers.

---

## 23. Temporary Files and Temp I/O in EXPLAIN

To observe a Sort likely to spill:

```sql
BEGIN;

SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, customer_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;

ROLLBACK;
```

You may see fields like:

```text
Sort Method: external merge  Disk: ...kB
Buffers: shared hit=..., temp read=... written=...
```

### 23.1. Meaning of temp read/written

- `temp read`: blocks read from temporary storage within the instrumented node scope.
- `temp written`: blocks written to temporary storage.
- Units in `BUFFERS` are **blocks**, not bytes.
- Parent node numbers can include child activity per EXPLAIN reporting; **never sum every plan line blindly**.

Temp I/O can come from Sort, HashAggregate, Hash Join, Materialize, or other intermediate operations. Never assume `temp read` always means Sort spilled without checking the actual node.

### 23.2. Disk Usage Yet Still Fast?

With fast storage and moderate data, an external Sort can still meet latency requirements. Optimize based on **application SLAs, throughput, and total load**, not merely seeing the word "Disk."

### 23.3. A Non-Spilling Sort Still Consumes RAM

A Sort reporting `Memory: ...` can consume substantial RAM even with zero temporary files. Under high concurrency, memory risk remains real.

Zero temp files does not mean "the query uses zero memory."

---

## 24. Monitoring Database-Wide Temp Usage

PostgreSQL exposes cumulative statistics in `pg_stat_database`:

```sql
SELECT
    datname,
    temp_files,
    temp_bytes,
    stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

- `temp_files`: total temporary files recorded in stats for this database.
- `temp_bytes`: total temporary file bytes written across queries.
- `stats_reset`: timestamp when stats were last reset.

### 24.1. Not a Single-Statement Measurement

These values are **database-wide cumulative statistics**, aggregating activity from all sessions and queries. When measuring before/after a lab on a shared server, other writers also contribute to temp files.

### 24.2. Computing Temp Byte Rate

If monitoring samples:

```text
T0: temp_bytes = 10 GB
T1: temp_bytes = 11.5 GB
Interval: 5 minutes
```

the delta indicates roughly 1.5 GB written to temp files during that window. It **does not reveal which query** caused it, nor does it equal temp disk space currently occupied at T1.

These values are illustrative only, not real measurements.

### 24.3. Statistics Lag

Cumulative stats update asynchronously and are snapshot-cached within a transaction. A test just completed may not appear immediately in the view.

You can call:

```sql
SELECT pg_stat_clear_snapshot();
```

to drop the session's cached stats snapshot if needed; it still does not convert cumulative counters into exact per-query measurements.

---

## 25. Tracking Temp I/O per Query with pg_stat_statements

When `pg_stat_statements` is configured and enabled, it aggregates metrics by normalized query fingerprint.

Example:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    temp_blks_read,
    temp_blks_written
FROM pg_stat_statements
WHERE query ILIKE '%plan_memory_lab.sales%'
ORDER BY temp_blks_written DESC
LIMIT 20;
```

**Prerequisite:** the extension must be installed and its library loaded, typically via `shared_preload_libraries` before server startup. Column names and views vary by PostgreSQL version, privileges, and config.

### 25.1. Temp Blocks Are Not Currently Open Temp Files

`temp_blks_read/written` count temp I/O blocks per query over time. They do not list files currently sitting on disk, nor pinpoint root causes from a single figure.

To analyze, cross-check:

- `calls`.
- Execution time.
- Query shape.
- `EXPLAIN` on representative queries.
- Data volume and `work_mem` at the time.

### 25.2. Query Text and Privacy

SQL text in monitoring/logs can contain sensitive literals, especially if apps omit bind parameters. Access to these views must comply with security and authorization policies.

---

## 26. log_temp_files: Catching Large Temp Files

`log_temp_files` instructs PostgreSQL to log temporary files exceeding a threshold when closed/deleted.

Common settings:

- `-1`: disable temp file logging.
- `0`: log all temp files.
- Positive integer: size threshold in configured units (typically kB).

### 26.1. When to Enable?

In an authorized investigation, temp file logging helps correlate:

- Query and session.
- Timestamp.
- Temp file size.
- Disk activity.

However, logging every temp file on a busy server produces heavy log volume and overhead. Never set `log_temp_files=0` across production just for an exercise.

### 26.2. Do Not Confuse log_temp_files with temp_file_limit

- `log_temp_files`: **observes/logs**.
- `temp_file_limit`: **enforces a hard cap** on temp file size per backend/process.

Setting `temp_file_limit` too low causes queries that need to spill to fail with an error. It protects disk capacity, rather than speeding up sorts.

### 26.3. Temp Tablespaces

`temp_tablespaces` lets you direct temporary objects to specific tablespaces per PostgreSQL rules. Offloading temp I/O to separate storage can balance load, subject to server config, `CREATE` permissions, reliability, capacity, and operations.

Never route temp files onto unreliable or cramped disks just chasing "speed" without weighing failure risk.

---

## 27. When Raising work_mem Can Harm the System

Suppose a Sort uses external merge at `work_mem=4MB` and runs faster at `work_mem=64MB` on one quiet lab connection.

The wrong conclusion is "set `work_mem=64MB` globally."

In production:

- Hundreds of connections may run concurrently.
- Each query can have multiple Sort/Hash nodes.
- Queries can spawn multiple parallel workers.
- Hash operations multiply budgets via `hash_mem_multiplier`.
- Sessions also need RAM for backends, shared buffers, and OS cache.
- Changing settings can flip query plans unexpectedly.

### 27.1. Mental Model, Not an Exact RAM Forecast

```text
20 concurrent queries
each with 3 large operations
work_mem = 64 MB

20 × 3 × 64 MB = 3,840 MB
```

This illustrates how **memory adds up across operations and sessions**, not a precise memory cap since nodes may use less, run in distinct phases, or add overhead, hash multipliers, and workers.

### 27.2. Safe Approach

1. Identify the exact query to optimize.
2. Run `EXPLAIN (ANALYZE, BUFFERS)` on representative data.
3. Test `SET LOCAL work_mem` in an isolated transaction/session.
4. Compare runtime, sort method, temp I/O, and CPU.
5. Check realistic peak concurrency.
6. Apply the narrowest scope possible (transaction/session/role) per policy.
7. Monitor memory, latency, and OOM risk after rollout.

Never use a cluster-wide memory bump as the first fix for a query with poor `WHERE`/`ORDER BY`/index design.

---

## 28. Planner Statistics Affect Sort and Aggregate

The planner chooses among Sort, HashAggregate, GroupAggregate, and Incremental Sort via **cost estimates**.

Key statistics inputs:

- Estimated row count.
- Filter selectivity.
- Distinct value count.
- Most common values (MCV).
- Histograms and correlation.
- Extended statistics for multi-column relationships.
- Average row/expression width.

### 28.1. Inspecting Column Statistics

```sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    correlation
FROM pg_stats
WHERE schemaname = 'plan_memory_lab'
  AND tablename = 'sales'
  AND attname IN (
      'customer_id','region','status','product_id','amount'
  )
ORDER BY attname;
```

`n_distinct` may be an estimated count or negative ratio per PostgreSQL conventions; it does not have to equal exact `COUNT(DISTINCT ...)`.

### 28.2. ANALYZE After Major Data Changes

```sql
ANALYZE plan_memory_lab.sales;
```

If `customer_id`/`product_id` distributions shift sharply while stats stay stale, the planner can misestimate group cardinality and pick poor HashAggregate or Incremental Sort plans.

### 28.3. Extended Statistics

When columns correlate, you can create extended statistics:

```sql
CREATE STATISTICS st_sales_region_status
    (dependencies, ndistinct, mcv)
ON region, status
FROM plan_memory_lab.sales;

ANALYZE plan_memory_lab.sales;
```

Which statistics help depends on predicate/group usage and planner capabilities. Extended stats **do not automatically cure every cardinality issue** in joins, aggregates, and ordering.

### 28.4. Cost Estimates Differing from Actuals

When EXPLAIN shows:

```text
estimated rows = 100
actual rows = 100000
```

large mismatches produce unexpected plans. Check selectivity, statistics, parameter values, and correlations before disabling planner nodes.

---

## 29. Sort and JOIN

Sorts can appear before or after JOINs:

```text
Seq Scan A ----\
                -> Hash Join -> Sort ORDER BY ...
Seq Scan B ----/
```

Or to feed a merge join:

```text
Sort A --\
          -> Merge Join -> ...
Sort B --/
```

### 29.1. Merge Join Requires Ordered Inputs

Merge Join needs two streams sorted by join keys, supplied either by indexes or Sort nodes.

Thus whenever you see a Sort in a plan, ask:

- Does Sort serve the final `ORDER BY`?
- Or feed a `Merge Join`?
- Or feed `GroupAggregate`, window functions, or `DISTINCT`?
- Could an index ordering replace it?

There is no rule saying "a Sort right before a JOIN is wasteful."

### 29.2. Hash Join Also Uses Memory and Can Spill

A `Hash Join` builds a hash table and splits into batches when memory runs tight. It uses `work_mem`/`hash_mem_multiplier`, separate from `HashAggregate`.

When temp I/O is high, do not look only for Sort. Plans with hash nodes can spill too.

### 29.3. ORDER BY on JOIN Output

A fast join plan need not emit rows in the user's `ORDER BY`. The planner inserts a final Sort when Hash Join or Gather loses ordering, or chooses a merge/index path when cheaper overall.

---

## 30. Optimize SQL Before Adding RAM

Practical questions:

### 30.1. Are All Sorted Rows Actually Needed?

If the UI shows only the 20 newest rows:

```sql
SELECT sale_id, created_at
FROM plan_memory_lab.sales
ORDER BY created_at DESC, sale_id DESC
LIMIT 20;
```

it can benefit from index order + `LIMIT`, instead of sorting/returning every row and slicing in the app.

### 30.2. Can Input Be Reduced with WHERE?

```sql
SELECT customer_id, SUM(amount)
FROM plan_memory_lab.sales
WHERE status = 'PAID'
GROUP BY customer_id;
```

If the status filter is selective, trimming rows before aggregation helps. Still, an index on `status` won't help if most rows are PAID; the planner may prefer Seq Scan.

### 30.3. Do You Need to Sort by So Many Columns?

```sql
ORDER BY region, customer_id, created_at DESC, sale_id DESC
```

many sort keys raise sort cost and make index alignment harder. Drop keys only if result contracts allow; never break deterministic pagination.

### 30.4. Can You Aggregate First and Sort Fewer Groups?

To find the top 20 customers by revenue, aggregating first and sorting 1,000 groups beats sorting 80,000 raw rows. The planner normally does this automatically from clean SQL, unless unnecessary subqueries/sorts block optimization.

### 30.5. Would a Materialized View Help?

If historical summary reports run constantly and do not require second-by-second freshness, consider:

- Materialized views with scheduled refreshes.
- Summary tables updated via events/ETL.
- Partitioning for very large datasets.
- Caching with explicit staleness policies.

These trade data freshness, refresh cost, and complexity—not automatic replacements for `HashAggregate`.

---

## 31. Step-by-Step Procedure to Inspect Sort Spills

Practical lab workflow:

### Step 1 — Capture Baseline Under Current Settings

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;
```

Record plan shape, `Sort Method`, `Memory`/`Disk`, `temp read`/`written`, and `Execution Time`.

### Step 2 — Test Low work_mem in a Transaction

```sql
BEGIN;
SET LOCAL work_mem = '64kB';

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;

ROLLBACK;
```

If `external merge` appears, record `Disk` and temp blocks.

### Step 3 — Test Higher work_mem Strictly in the Lab

```sql
BEGIN;
SET LOCAL work_mem = '32MB';

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC;

ROLLBACK;
```

Compare `Sort Method` and I/O. Never rely on a single run across differing cache and concurrency states.

### Step 4 — Check Whether an Ordered Index Helps

Sorting by `(amount, created_at, sale_id)` currently has no composite index in the lab. Consider **only if genuinely needed**:

```sql
CREATE INDEX idx_sales_amount_time
ON plan_memory_lab.sales (
    amount DESC, created_at DESC, sale_id DESC
);
```

Then:

```sql
ANALYZE plan_memory_lab.sales;

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, amount, created_at
FROM plan_memory_lab.sales
ORDER BY amount DESC, created_at DESC, sale_id DESC
LIMIT 20;
```

B-tree order can help, especially with `LIMIT 20`. Still, the new index adds INSERT/UPDATE overhead and storage; never create it in production solely because EXPLAIN showed one Sort.

### Step 5 — Conclude Based on Workload

Compare:

- Baseline.
- Higher `work_mem`.
- Query with `LIMIT`.
- Query using index order.
- Write speed and new index cost.
- Concurrent session count.

Never choose an option from a single execution time.

---

## 32. Step-by-Step Procedure to Inspect Aggregates

### Step 1 — Default Hash/Group Strategy

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    customer_id,
    COUNT(*) AS n,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id;
```

Observe whether the node is `HashAggregate` or `GroupAggregate`.

### Step 2 — Inspect Non-Hash Strategy

```sql
BEGIN;
SET LOCAL enable_hashagg = off;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT customer_id, COUNT(*), SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id;

ROLLBACK;
```

Distinguish:

- `Sort + GroupAggregate`.
- `Index Scan + GroupAggregate`.
- Other alternatives.

### Step 3 — Observe When Group Count Rises

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    product_id,
    COUNT(*),
    SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id, product_id;
```

Cardinality of `(customer_id, product_id)` exceeds `customer_id` alone; `HashAggregate` memory and cost shift accordingly.

### Step 4 — Inspect ORDER BY on Aggregate Results

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    customer_id,
    SUM(amount) AS revenue
FROM plan_memory_lab.sales
GROUP BY customer_id
ORDER BY revenue DESC
LIMIT 20;
```

Separate:

- Aggregating raw rows.
- Sorting 1,000 aggregated groups to find the top 20.
- Applying Limit.

A `Sort Method: top-N heapsort` over ~1,000 groups is completely different from sorting 80,000 raw rows.

---

## 33. Real-World Scenario: Slow Paginated API

An API query:

```sql
SELECT *
FROM orders
WHERE tenant_id = :tenant
ORDER BY created_at DESC
LIMIT 20 OFFSET 200000;
```

is slow.

Potential causes:

- Sorting a very large result set.
- Missing index aligned with `tenant_id` + `created_at`.
- Large `OFFSET` forcing reading/discarding huge row counts.
- Returning too many columns, causing heavy heap fetches.
- Low `work_mem` causing Sort spills.
- Unselective `WHERE` predicate.
- Stale statistics leading to poor plans.

### 33.1. Consider Keyset Pagination

Given a stable sort order:

```sql
-- Pattern on a hypothetical table with id and created_at.
SELECT *
FROM orders
WHERE tenant_id = :tenant
  AND (
      created_at < :last_created_at
      OR (
          created_at = :last_created_at
          AND id < :last_id
      )
  )
ORDER BY created_at DESC, id DESC
LIMIT 20;
```

With an index on `(tenant_id, created_at DESC, id DESC)`, keyset pagination avoids skipping hundreds of thousands of rows like deep `OFFSET`.

However, you must handle:

- Timestamp ties using a unique tiebreaker.
- Concurrent inserts/updates while users paginate.
- Snapshot stability if business rules require it.
- NULL ordering and cursor predicates.
- Index design and tenant authorization.

Do not replace every `OFFSET` with keyset pagination if the UI requires jumping directly to arbitrary page numbers without cursors.

---

## 34. Real-World Scenario: HashAggregate Spill on Multi-Key GROUP BY

A report query:

```sql
SELECT
    customer_id,
    product_id,
    DATE(created_at) AS day,
    SUM(amount)
FROM plan_memory_lab.sales
GROUP BY customer_id, product_id, DATE(created_at);
```

can generate huge group counts across three dimensions.

If `HashAggregate` is chosen and the hash table grows huge:

- High `Memory Usage`.
- `Batches > 1` when batching triggers.
- `Disk Usage`/temp blocks appear.
- Execution time rises due to temp I/O.

### 34.1. Re-Evaluate Grouping Granularity

Do we truly need breakdowns down to every customer, product, and day? If a dashboard only displays region/day totals, overly fine grouping inflates cardinality with zero business value.

Never alter `GROUP BY` if doing so breaks report accuracy; simplify only when business requirements allow.

### 34.2. Evaluate GroupAggregate

Test `enable_hashagg=off` in the lab; if `GroupAggregate` needs a huge external Sort, it may perform no better than a spilling `HashAggregate`. Neither always wins when spilling occurs.

### 34.3. Avoid Immediately Raising work_mem Server-Wide

Check first:

- Actual vs estimated group cardinality.
- Hash `Batches`/`Disk Usage`.
- Concurrency.
- Whether `WHERE`/range filters can run before grouping.
- Whether pre-aggregation or scheduled materialization fits.
- Whether an index order aligns with the workload.

Tuning memory is one option among several, never the only lever.

---

## 35. Real-World Scenario: Incremental Sort Regression

A PostgreSQL upgrade or new plan picks `Incremental Sort` after an index scan instead of `Seq Scan + full Sort`, yet latency spikes.

Hypotheses:

1. Overestimated number of prefix groups.
2. A few massive prefix groups in reality.
3. Index scan incurring heavy random heap I/O.
4. `LIMIT` unable to stop early as expected.
5. Filters skewing prefix group distribution.
6. Missing or stale statistics.
7. Changes in `work_mem`, parallelism, or schema.

### 35.1. How to Investigate

- Capture `EXPLAIN (ANALYZE, BUFFERS)` and PostgreSQL version.
- Inspect `Presorted Key` and statistics on that key.
- Compare estimated vs actual rows.
- Check group count and group sizes.
- Test in a transaction with `SET LOCAL enable_incremental_sort=off`.
- Compare total cost of index scan, I/O, and Sort.
- Run `ANALYZE` or add extended stats if evidence supports it.
- Roll out scoped changes and verify.

Never judge a feature by node name alone; Incremental Sort can be a huge win on another query.

---

## 36. Real-World Scenario: Heavy Temp Files and Slow Disk

Monitoring shows `pg_stat_database.temp_bytes` climbing fast and report latency spiking.

An investigative workflow:

1. Identify when `temp_bytes`/`temp_files` spike.
2. Check `pg_stat_statements.temp_blks_written` if enabled.
3. Use `log_temp_files` per policy to catch offending queries.
4. Run `EXPLAIN` on representative queries.
5. Pinpoint whether spills come from Sort, HashAggregate, Hash Join, Materialize, or another node.
6. Inspect `work_mem`, `hash_mem_multiplier`, parallel workers, and active sessions.
7. Check temp tablespace disk, throughput, and filesystem space.
8. Optimize `WHERE`/indexes/ordering/grouping before adding memory.
9. Benchmark against SLOs and monitor rollout.

### 36.1. Do Not Look Only at Cumulative temp_bytes

Many tiny queries can accumulate large `temp_bytes` over hours without any single query misbehaving. Conversely, one runaway query can fill disk in seconds.

Measure **rate, per-query breakdown, and peak temp disk usage**, not just a cumulative counter.

### 36.2. Is Temp I/O Always Just "Not Enough RAM"?

No. Some queries process datasets larger than any safe RAM budget, making external sort normal. The real flaw may be unnecessary full-table sorting or missing ordered indexes, not "RAM configured too low."

---

## 37. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "ORDER BY guarantees a Sort node." | Indexes or prior nodes can supply ordering |
| "Without ORDER BY, GroupAggregate always emits sorted output." | SQL guarantees order only with an outer ORDER BY |
| "Sort is always slow." | In-memory sorting of small sets is very cheap |
| "External Sort is a PostgreSQL bug." | It is a valid strategy when data exceeds memory budget |
| "Disk: 100MB means set work_mem=101MB." | In-memory layout and overhead differ from temp files |
| "LIMIT 20 means only 20 rows are read." | Without an ordered index, all inputs may be read |
| "Top-N heapsort and Index Scan LIMIT are identical." | They are two distinct strategies |
| "OFFSET 100000 is free because LIMIT is 20." | Preceding rows still must be processed/skipped |
| "Incremental Sort re-sorts the whole input." | It exploits a pre-sorted prefix and sorts within groups |
| "Any index enables Incremental Sort." | Input must match a compatible ordering prefix |
| "Incremental Sort is always faster than Sort." | Depends on prefix groups, scan cost, and memory |
| "Presorted Key is the full Sort Key." | Presorted Key is only the already-ordered prefix |
| "Nearly all rows sharing one prefix still works well." | One giant group loses the advantage |
| "GROUP BY always requires Sort." | HashAggregate groups without sorting input |
| "HashAggregate always stays completely in RAM." | It can batch and spill to disk |
| "GroupAggregate is always cheaper than HashAggregate." | Sorting large inputs can cost more |
| "GROUP BY guarantees customer_id order." | Only ORDER BY guarantees output order |
| "Outer ORDER BY sorts elements inside array_agg." | Only ORDER BY inside the aggregate controls element order |
| "COUNT(DISTINCT) costs the same as COUNT(*)." | Adds per-group deduplication overhead |
| "B-tree on created_at is always used for ORDER BY." | Planner may pick Seq Scan + Sort |
| "Any composite index orders by its second column." | Global order depends on leading keys |
| "ASC/DESC and NULLS FIRST/LAST don't matter." | They are part of ordering semantics |
| "Gather preserves worker ordering." | Gather Merge merges ordered streams |
| "Parallel queries share one work_mem equally." | Operations and workers have separate budgets |
| "work_mem is the max RAM per query." | It applies per eligible operation |
| "work_mem=64MB means 100 connections total 64MB." | Concurrent operations multiply memory usage |
| "hash_mem_multiplier increases Sort memory too." | Applies primarily to eligible hash operations |
| "temp_buffers fixes external Sort spills." | `temp_buffers` serves temporary tables |
| "temp_file_limit configures work_mem." | It caps temp disk usage per process |
| "pg_stat_database.temp_bytes measures only this query." | It is a cumulative database-wide counter |
| "temp_bytes is current disk space used by temp files." | It is cumulative bytes written over time |
| "log_temp_files speeds up queries." | It only logs for diagnosis |
| "Parent Temp read adds on top of every child." | BUFFERS aggregate inclusively; avoid double-counting |
| "EXPLAIN cost is milliseconds." | Cost is a relative planner unit |
| "Forcing enable_seqscan=off proves an index is faster." | Only reveals alternative plans |
| "Raising work_mem across all production is always good." | Concurrency brings OOM risks |
| "ANALYZE has nothing to do with sorting." | Stats drive Sort/Aggregate plan selection |
| "Hash Join spills are Sort bugs." | Hash Join is its own source of temp I/O |
| "High temp I/O always means insufficient RAM." | Often stems from query design and data volume |

---

## 38. Practice Exercises

### Exercise 1 — Reading Sort Key

Run EXPLAIN on:

```sql
SELECT sale_id, amount
FROM plan_memory_lab.sales
ORDER BY amount DESC, sale_id DESC;
```

Identify `Sort Key` and the input-producing node. Why is `sale_id DESC` a tiebreaker?

### Exercise 2 — Comparing Two work_mem Values

Use `SET LOCAL work_mem='64kB'` and `'32MB'` in two lab transactions running the same Sort query. Record `Sort Method`, `Memory`/`Disk`, and `temp read`/`written`.

### Exercise 3 — External Sort

Explain how an external merge sort splits into runs and merges them. Why doesn't `Disk` usage translate directly into minimum `work_mem`?

### Exercise 4 — Top-N Heapsort

Run `ORDER BY amount DESC LIMIT 20` and compare with no LIMIT. Why might `LIMIT 20` still read 80,000 rows?

### Exercise 5 — Index Order

Run `ORDER BY created_at DESC, sale_id DESC LIMIT 20`. Which lab index can supply that order? Why might Sort disappear?

### Exercise 6 — OFFSET

Compare `LIMIT 20 OFFSET 0` with `LIMIT 20 OFFSET 50000`. Why are returned row counts identical while actual work differs sharply?

### Exercise 7 — NULL Ordering

Explain the difference between `ORDER BY x DESC` and `ORDER BY x DESC NULLS LAST` when `x` is nullable. Why do index direction and NULL placement affect plans?

### Exercise 8 — Composite B-Tree

Given index `(region, created_at DESC)`, which query uses index order better: `ORDER BY region, created_at DESC` or `ORDER BY created_at DESC` across the whole table? Explain.

### Exercise 9 — Incremental Sort

Given input pre-sorted by `customer_id`, what Sort can `ORDER BY customer_id, amount DESC` use? Sketch three customers' rows and sort within each group.

### Exercise 10 — Presorted Key

In a plan showing `Sort Key: customer_id, amount DESC` and `Presorted Key: customer_id`, which part still needs sorting?

### Exercise 11 — Disabling Incremental Sort in the Lab

Use `SET LOCAL enable_incremental_sort=off` and compare plans. Why doesn't disabling a node prove the alternative plan is always better?

### Exercise 12 — Prefix Skew

90% of rows share the same `customer_id`. Predict how Incremental Sort performs when sorting by `customer_id, amount`. What should you measure?

### Exercise 13 — Aggregate Without GROUP BY

Run `SELECT SUM(amount)`. What kind of Aggregate node can appear? Why are no group-key structures needed?

### Exercise 14 — HashAggregate

Run `GROUP BY customer_id`. What does the hash table store for COUNT/SUM? When can `Batches` or `Disk Usage` appear?

### Exercise 15 — GroupAggregate

Disable `hashagg` locally. If `Sort + GroupAggregate` appears, what Sort Key does it need? What if `Index Scan` on `customer_id` is used instead?

### Exercise 16 — ORDER BY Aggregate Value

Run `GROUP BY customer_id ORDER BY SUM(amount) DESC LIMIT 20`. Why doesn't an index on `customer_id` automatically sort by revenue?

### Exercise 17 — HAVING and WHERE

Write a query filtering `status = 'PAID'` in WHERE and `SUM(amount) > 500` in HAVING. Distinguish input rows entering aggregation from groups remaining afterward.

### Exercise 18 — COUNT DISTINCT

Compare `COUNT(*)` with `COUNT(DISTINCT product_id)` per `customer_id`. Why can `DISTINCT` require extra memory, sorting, or hashing?

### Exercise 19 — array_agg Order

Write `array_agg(sale_id ORDER BY created_at DESC)`. Why doesn't an outer `ORDER BY` replace `ORDER BY` inside the aggregate?

### Exercise 20 — DISTINCT ON

Fetch the newest sale per customer using `DISTINCT ON` and a matching `ORDER BY`. Design a B-tree index supporting that order.

### Exercise 21 — ROLLUP

Total revenue by `(region, status)`, by `region`, and overall. Use `GROUPING` to separate rollup NULLs from real data NULLs.

### Exercise 22 — Parallel Aggregate

Distinguish `Partial Aggregate` from `Finalize Aggregate`. When is `Gather Merge` useful? Why do parallel workers complicate memory planning?

### Exercise 23 — WindowAgg Sort

Use `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY amount DESC)`. What ordering does PostgreSQL need? Is the outermost result guaranteed to stay in that order?

### Exercise 24 — work_mem

A query has three Sort/Hash operations and runs concurrently across 20 sessions. Why can't you multiply `work_mem` once and treat it as a total memory cap?

### Exercise 25 — hash_mem_multiplier

Given `work_mem=16MB` and `hash_mem_multiplier=2.0`, explain the base hash memory budget and why not every `HashAggregate` allocates exactly 32MB.

### Exercise 26 — temp_buffers

Distinguish temporary table buffers from temporary files created by external sorts. Does changing `temp_buffers` directly fix Sort spills?

### Exercise 27 — pg_stat_database

Query `temp_files`, `temp_bytes`, and `stats_reset`. Why doesn't this show how many temp bytes a single query used under concurrency?

### Exercise 28 — pg_stat_statements

If enabled, query statements with high `temp_blks_written`. Which extra metrics distinguish a query called millions of times from a query spilling gigabytes per call?

### Exercise 29 — log_temp_files

Explain `-1`, `0`, and positive values. Why shouldn't you log every temp file across production long-term without checking log volume?

### Exercise 30 — temp_file_limit

Explain which resource it protects, how it differs from `work_mem`, and why setting it too low breaks queries.

### Exercise 31 — Sort vs Hash Join Spill

A plan has Sort, Hash Join, and HashAggregate. How do you identify which node caused temp I/O? Why isn't total `temp_bytes` enough?

### Exercise 32 — Planner Statistics

Inspect `pg_stats.n_distinct` and `most_common_vals` on `customer_id` and `region`. How can misestimating group counts skew HashAggregate and Incremental Sort choices?

### Exercise 33 — Extended Statistics

Create statistics on `region, status` and run `ANALYZE`. Propose a measurement to check if planner estimates improved, and note limitations.

### Exercise 34 — Materialized Summary

A dashboard runs the same `GROUP BY` hundreds of times per minute on data that does not need real-time accuracy. Compare querying raw tables vs a materialized view/summary table on latency and freshness.

### Exercise 35 — Optimizing an API

An API `ORDER BY created_at DESC LIMIT 20 OFFSET 200000` is slow. Propose indexes, keyset pagination, and checks needed to preserve pagination semantics.

### Exercise 36 — High-Cardinality Report

A `GROUP BY customer_id, product_id, DATE(created_at)` report spills in HashAggregate. List at least five investigative steps before raising cluster-wide `work_mem`.

### Exercise 37 — Incremental Sort Regression

A new plan with Incremental Sort runs slower than full Sort. List possible causes: prefix skew, index heap I/O, cardinality, LIMIT, `work_mem`, planner stats. Design an experiment to isolate them.

### Exercise 38 — Production Memory Checklist

Design an evaluation table covering concurrent queries, sorts/hashes per query, parallel workers, `work_mem`, hash multiplier, temp disk capacity, SLAs, monitoring, and rollback plans.

---

## 39. Operations and Optimization Checklist

| Question | How to verify / meaning |
| --- | --- |
| Does the query genuinely need ORDER BY? | Product semantics |
| Does ORDER BY have a deterministic tiebreaker? | Pagination/consistency |
| Is there a Sort node? | EXPLAIN |
| What is Sort Key? | Check ordering requirements |
| What order does input already have? | Indexes/pathkeys, `Presorted Key` |
| Is Incremental Sort used? | EXPLAIN, prefix groups |
| Are prefix groups skewed? | Distribution, stats |
| What is Sort Method? | quicksort / top-N / external merge |
| Does it spill to disk? | `Disk`, `temp read/written` |
| Does LIMIT reduce work? | Top-N / index-ordered scan |
| Is OFFSET too deep? | Keyset pagination |
| Does the index match ASC/DESC/NULLS/collation? | B-tree definition vs ORDER BY |
| Does index order incur heavy random I/O? | BUFFERS/latency |
| Is there GROUP BY? | Aggregate strategy |
| HashAggregate or GroupAggregate? | Plan node |
| Is group cardinality estimated accurately? | estimated vs actual, `n_distinct` |
| Does HashAggregate show Batches > 1? | Memory/Disk, temp I/O |
| Does GroupAggregate have a prior Sort? | Sort Method / spill |
| Which key orders aggregate output? | Is a post-aggregate Sort needed? |
| Is DISTINCT used inside aggregates? | Deduplication cost |
| Is ORDER BY inside `array_agg`/`string_agg`? | Semantics and memory |
| Are GROUPING SETS/ROLLUP used? | MixedAggregate and grouping levels |
| Is WindowAgg present? | Sort by partition/order keys |
| Are parallel workers used? | Memory/concurrency, Gather Merge |
| Current `work_mem`? | `SHOW work_mem` |
| `hash_mem_multiplier`? | `SHOW hash_mem_multiplier` |
| Multiple memory-heavy operations in one query? | Each node has its own budget |
| Many concurrent sessions running? | Peak memory, OOM risk |
| Are temp tables used? | Distinguish `temp_buffers` |
| Is there temp disk pressure? | `pg_stat_database`, OS metrics |
| Which queries write heavy temp blocks? | `pg_stat_statements` if enabled |
| Are temp files logged? | `log_temp_files` per policy |
| Is `temp_file_limit` set safely? | Prevents disk exhaustion, realistic cap |
| Appropriate temp tablespace? | `temp_tablespaces`, permissions/disk |
| Are planner stats fresh? | `ANALYZE` |
| Are multiple columns correlated? | Extended statistics where helpful |
| Can filters run earlier? | WHERE / partition pruning |
| Can groups or sort keys be reduced? | Only if business rules permit |
| Should a new index be created? | Read, write, storage, concurrency |
| Should `work_mem` be increased? | Test per-session, check total load |
| Tested repeatedly on representative data? | Cache/I/O/concurrent load |
| Is there a tuning rollback plan? | Reset settings, controlled drop |

## Conclusion

In PostgreSQL, **Sort**, **Incremental Sort**, **Aggregate**, and **temporary memory** are critical building blocks of execution plans:

- **Sort** establishes requested ordering when input lacks compatible order. It runs in memory or uses external merge and temporary files when needed.
- **Top-N heapsort** helps when only the leading N rows are needed, yet does not reduce input row reads without an ordered access path.
- **Incremental Sort** exploits a pre-sorted prefix to sort only within each prefix group. It can save substantial work depending on group distribution and input path cost.
- **HashAggregate** groups via a hash table; **GroupAggregate** consumes a pre-sorted stream. Either can win or lose depending on cardinality, ordering, memory, and I/O.
- **Outer result ORDER BY** and **ORDER BY inside aggregates/windows** have distinct semantics. Without an outer `ORDER BY`, SQL never guarantees output row order.
- **`work_mem`** is the base budget per eligible operation, not a per-query RAM cap. Hash operations scale with `hash_mem_multiplier`, while parallel workers and concurrent sessions multiply total demand.
- **Temp I/O** must be read via plans, `Buffers: temp`, `pg_stat_database`, `pg_stat_statements`, and scoped logging. A cumulative `temp_bytes` counter alone never identifies a single offending query.
- **B-tree indexes, statistics, and SQL design** are often just as powerful levers as adding memory. Indexes speed reads while costing disk space and writes.
- **Safe optimization** measures a baseline, tests one variable in a restricted scope, verifies identical results and latency, and checks concurrency before touching production.

Once you can read input ordering, aggregate strategy, Sort method, memory usage, and temp I/O together on a single execution plan, slow reporting queries become solvable, measurable engineering problems rather than guesswork with `work_mem`.
