# Estimated vs. Actual Discrepancies and Finding Expensive Nodes in PostgreSQL Query Plans

## 1. A “Slow” Query Does Not Necessarily Come from a Long SQL Statement

Suppose an API that fetches orders for a group of customers runs in 100 ms in a test environment, but takes 15 seconds in production. The SQL statement has not changed. One possible reason is that PostgreSQL **misestimates intermediate row counts**, causing it to choose a join method, join order, index scan, or sorting strategy that no longer fits the actual data.

For example, the planner thinks a filter returns only **10 orders**, while in reality it returns **80,000 orders**. If the plan picks a **Nested Loop** and each order triggers another index lookup, a small discrepancy at a lower node can multiply into a massive amount of work.

Proper analysis does not stop at spotting “Seq Scan” and adding an index. You need to answer three questions:

1. **What did the planner predict?** — `cost`, `rows`, `width`, chosen nodes, join order.
2. **What actually happened during execution?** — `actual time`, `actual rows`, `loops`, filtered rows, memory, I/O, temp files, WAL.
3. **Which discrepancy actually increases total cost?** — wrong cardinality, too many loops, disk I/O, sort spilling to disk, multi-batch hash, or poor selectivity.

This lesson focuses on **reading and diagnosing** with `EXPLAIN` and `EXPLAIN ANALYZE`, rather than offering a “one parameter fixes every query” trick.

### Learning Objectives

After this lesson, you will be able to:

- Accurately read `cost=a..b rows=n width=w` and `actual time=c..d rows=m loops=k`.
- Compute row estimation discrepancies (*cardinality estimation error*) without forgetting `loops`.
- Distinguish **planner estimates** from **actual measured timings**, and distinguish total query time from inclusive subtree timing.
- Locate the node to investigate by walking down from the root to the node amplifying the work.
- Read `Rows Removed by Filter`, `Index Cond`, `Filter`, `Join Filter`, and `Recheck Cond`.
- Use `BUFFERS`, `I/O Timings`, `Sort Method`, `Disk`, `Hash Batches`, and parallel metrics to isolate root causes.
- Identify common issues: stale statistics, skew, column correlation, hard-to-estimate predicates, join fan-out, and insufficient `work_mem`.
- Test appropriate fixes: `ANALYZE`, extended statistics, selective indexes, SQL rewrites, data design, or pagination strategies.
- Run experiments in a reproducible lab dataset and explain your findings.

> **Safety Rule:** `EXPLAIN ANALYZE` executes the SQL statement. Do not run it casually on `UPDATE`, `DELETE`, `INSERT`, DDL, or functions with side effects in production. Only measure on authorized datasets with appropriate load limits.

---

## 2. What Is a Query Plan?

An **execution plan** is a tree of operations that PostgreSQL intends to use to retrieve, join, filter, group, and sort data.

Illustrative structure:

~~~text
Limit
└── Sort
    └── Hash Join
        ├── Seq Scan on orders
        └── Hash
            └── Seq Scan on customers
~~~

Reading along the data flow:

1. Read the `customers` table.
2. Build a hash table for one side of the join.
3. Read `orders`.
4. Hash Join the two data streams.
5. Sort the result.
6. Limit the number of returned rows.

In a text-formatted plan, a parent node sits **above** its child nodes. Most data originates at leaf nodes and flows upward; however, execution can be lazy, pipelined, looped, or stopped early due to LIMIT, so do not treat the tree as a strictly sequential step-by-step list.

### 2.1. Nodes Are Operations, Not SQL Clauses

A single SELECT statement can generate many nodes: Seq Scan, Index Scan, Bitmap Index Scan, Bitmap Heap Scan, Sort, Hash, Hash Join, Nested Loop, Merge Join, Aggregate, Gather, and many others.

Each node has its own **estimates**, and when ANALYZE is used, can have its own **actual measurements**.

### 2.2. Planner and Executor Have Different Roles

- **Planner/optimizer:** uses statistics, metadata, indexes, filter conditions, and a cost model to compare candidate plans.
- **Executor:** runs the chosen plan, interacts with cache/disk/CPU, processes actual rows, and records measurements when EXPLAIN ANALYZE instrumentation is enabled.

The planner does not measure in advance that “this query will take exactly 17.2 ms.” It makes **relative predictions in cost units**.

### 2.3. Specific Numbers Vary by Environment

Two machines with the same data may choose different plans because of:

- PostgreSQL version and extensions.
- Statistics and when ANALYZE ran.
- Differences in indexes, partitions, and constraints.
- `work_mem`, `random_page_cost`, `effective_cache_size`, and parallel settings.
- Warm/cold cache and active concurrent connections.
- New/updated data, bloat, and visibility map state.
- Bind parameter values and generic/custom plan behavior.

Therefore, execution-plan snippets in this lesson are **format illustrations**. In practice, you must read the real plan on your database.

---

## 3. EXPLAIN vs. EXPLAIN ANALYZE: Execution-Level Differences

### 3.1. EXPLAIN Shows Estimates Only

~~~sql
EXPLAIN
SELECT *
FROM plan_lab.orders
WHERE status = 'paid';
~~~

Plain `EXPLAIN` shows what the planner expects to do, **without running the SELECT to measure actual processing time**.

### 3.2. EXPLAIN (ANALYZE, BUFFERS) Executes the SELECT

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM plan_lab.orders
WHERE status = 'paid';
~~~

Typically, output includes both:

~~~text
Seq Scan on orders  (cost=0.00..3000.00 rows=102000 width=...)
                    (actual time=0.030..26.100 rows=102000 loops=1)
  Filter: (status = 'paid'::text)
  Rows Removed by Filter: 18000
  Buffers: shared hit=..., read=...
Planning Time: ... ms
Execution Time: ... ms
~~~

This is an **illustrative example of how to read output**, not fixed lab output. Exact floating-point numbers, type casts, widths, and buffer counts depend on your database.

### 3.3. Recommended Diagnostic Options

~~~sql
EXPLAIN (
    ANALYZE,
    BUFFERS,
    VERBOSE,
    SETTINGS,
    SUMMARY,
    FORMAT TEXT
)
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE customer_id BETWEEN 1 AND 100;
~~~

Explanation:

| Option | Role |
|---|---|
| `ANALYZE` | Actually executes the query; adds actual time/rows/loops |
| `BUFFERS` | Counts buffer/cache/disk/temp accesses on relevant nodes |
| `VERBOSE` | Shows additional target lists, schema names, and internal details |
| `SETTINGS` | Prints relevant planner parameters that differ from defaults |
| `SUMMARY` | Total planning/execution time and summary metadata |
| `FORMAT TEXT` | Easy to read manually |
| `FORMAT JSON` | Convenient to store/compare via tooling; avoids fragile regex parsing on text |
| `TIMING OFF` | Reduces per-node timing overhead when queries are tiny or have high loop counts |
| `WAL` | Shows WAL statistics for applicable statements when ANALYZE is used |

### 3.4. What Does TIMING OFF Still Measure?

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM plan_lab.orders;
~~~

`TIMING OFF` disables **per-node timing**, reducing instrumentation overhead in some situations, while still reporting `actual rows`, `loops`, and total **Execution Time**. Because there is no per-node actual time, you cannot use this output to attribute milliseconds to individual nodes; in return, the total measurement may incur lower overhead.

### 3.5. Do Not Run ANALYZE Carelessly on DML

~~~sql
-- Dangerous on real data if run without controls:
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM plan_lab.orders
WHERE status = 'canceled';
~~~

This command **executes the DELETE**. In a private lab, you can wrap a test DML statement in a transaction and roll it back, keeping in mind that sequence/identity allocations, side effects outside the database, or functions calling external services **are not necessarily rolled back**.

To inspect without **modifying data**, use `EXPLAIN` without ANALYZE. To measure DML, run it in staging or a controlled lab transaction, and terminate all error paths properly.

---

## 4. Reading cost, rows, and width Correctly

Sample node:

~~~text
Index Scan using ix_orders_customer on orders
    (cost=0.42..31.76 rows=12 width=48)
~~~

### 4.1. Startup Cost and Total Cost

- `cost=0.42`: estimated **startup cost**, the work required before the node can return its first row.
- `cost=31.76`: estimated **total cost** for the node to produce all its output under the planner's cost model.
- Cost uses **relative internal units**, **not milliseconds**.
- A parent node's cost already incorporates its child nodes' costs as calculated by the planner; **do not add up total costs across all nodes** to compute a "true total cost."

A Sort node usually has a substantial startup cost because it may need to collect its input before emitting the first row. An Index Scan can have a low startup cost to return a few rows early.

### 4.2. rows Is Estimated Rows Emitted by the Node

`rows=12` means the planner expects the node to produce roughly **12 rows per execution of the node**, matching how `loops` is interpreted in actual measurements. It is not 12 rows read from storage, not 12 pages, and not 12 transactions.

A Filter node might scan 100,000 rows from a table yet **emit only 12 rows** to its parent node.

### 4.3. width Is Estimated Average Output Row Size in Bytes

`width=48` is the **estimated average width, in bytes**, of each row passed upward by the node. The planner uses it to compute data volume, sort/hash costs, and other operator estimates.

If `width` is underestimated for wide text/jsonb columns or complex expressions, sort/hash memory and tuplestore sizes may diverge from expectations. Still, `width` is not the exact number of bytes stored on disk per tuple.

### 4.4. Do Not Compare Absolute Costs Across Different Systems

`cost=10000` on machine/setting A cannot be converted directly into "10 seconds" or compared against system B if statistics or cost constants differ. What is useful is **comparing candidate plans under the same conditions** and checking them against actual measurements.

---

## 5. Reading actual time, actual rows, and loops

Example node:

~~~text
Index Scan using idx_order_items_order_id on order_items
  (cost=0.42..9.60 rows=2 width=32)
  (actual time=0.018..0.045 rows=3 loops=5000)
~~~

### 5.1. What Is actual time=a..b?

- `actual time=0.018`: average time to the first row per execution of the node, when per-node timing is enabled.
- `actual time=0.045`: average time until the node completes per execution.
- The unit is **milliseconds**.
- When `loops>1`, the timing numbers are typically **averages per execution**, not the sum across all 5,000 iterations.

### 5.2. actual rows Must Also Be Read Together with loops

`actual rows=3 loops=5000` means the node returned an average of about **3 rows per execution** across 5,000 executions. Total rows emitted are approximately:

\[
3 \times 5000 = 15000 \text{ rows}
\]

`actual rows` can be rounded in text display; for automated analysis, use JSON output and understand measurement semantics.

### 5.3. Do Not Compare “actual rows = 3” with “estimated rows = 2” While Ignoring loops

Looking at a single iteration, 3 vs. 2 is a 1.5× difference, which looks small. However, **5,000 lookups** may be the primary source of cost.

For a repeated node:

~~~text
actual time=0.045 rows=3 loops=5000
~~~

a rough estimate of cumulative time spent in node invocations is:

\[
0.045\text{ ms} \times 5000 \approx 225\text{ ms}
\]

**Caution:** node timing is generally **inclusive of child work**; this multiplication is only a rough heuristic and does not mean all 225 ms are exclusive CPU time of that node, as parent/child timings overlap and include instrumentation overhead.

### 5.4. Total actual time Is Not Computed by Summing Nodes

Wrong:

~~~text
Seq Scan 100 ms
Hash     90 ms
Hash Join 120 ms
Sort     50 ms
-----------------
Total time = 360 ms  (invalid if summed this way)
~~~

Parent node timings **already include much of the time spent in child nodes** under the execution model. Pipelined plans, parallel workers, and instrumentation make summing them even less meaningful. **Execution Time at the bottom** is the executor's measured total time for the statement.

### 5.5. A Node with Zero actual rows Is Not Necessarily Useless

`actual rows=0` can happen because:

- A Filter discarded all rows.
- A Limit stopped early on another branch.
- The outer side of a join produced no input for the inner side.
- The branch was not executed (`never executed`).
- Partition pruning skipped the branch.
- The actual data contains no matching values.

You must read **loops**, parent nodes, and conditions together; do not drop an index or rewrite SQL just because a branch returned zero rows on one run.

---

## 6. Why Estimation Discrepancies Are a Key Diagnostic Signal

The planner needs to predict how many rows will flow through each node in order to decide:

- Nested Loop vs. Hash Join vs. Merge Join.
- Index scan vs. sequential scan.
- Join order.
- Resource planning for Sort, Aggregate, and Hash.
- Whether to use parallel workers.
- LIMIT, DISTINCT, and ORDER BY strategies.

A node estimated at **100 rows** that actually produces **1,000,000 rows** can turn a plan well-suited for 100 rows into a very expensive one.

### 6.1. Estimate/Actual Ratio

A practical metric when both numbers are positive:

\[
\text{misestimate factor}
=\max\left(
\frac{\text{actual rows}}{\text{estimated rows}},
\frac{\text{estimated rows}}{\text{actual rows}}
\right)
\]

Examples:

| Estimated rows | Actual rows | Discrepancy | Interpretation |
|---:|---:|---:|---|
| 100 | 120 | 1.2× | Close |
| 100 | 10,000 | 100× | Underestimate |
| 20,000 | 50 | 400× | Overestimate |
| 5 | 5 | 1× | Accurate at this node |
| 1 | 0 | No finite ratio | Zero actual output |

**There is no universal “10× means a bug” threshold.** A large discrepancy on a cheap node can matter far less than a 2× discrepancy on a node executed a million times.

### 6.2. Watch Out for Zero Cases

If actual rows is 0, actual/estimated is 0 and its reciprocal is infinite. Do not report “∞×” as an optimization conclusion. First check whether the input was empty, the condition was highly selective, or LIMIT/pruning prevented the node from running.

### 6.3. Actual Rows Averaged per Loop

A node with estimated rows=5 and actual rows=3 loops=1000 should usually be read as **5 predicted and 3 actual per execution**, not that the planner “predicted 5 total” while reality was “3000.” When analyzing *total work performed*, also inspect the loop count predicted/executed through the parent node.

### 6.4. A Small Leaf Discrepancy Can Grow Large After a Join

Example:

~~~text
Scan customers:         estimated 100, actual 200
Scan orders/customer:   estimated   2, actual  40
Nested Loop output:     estimated 200, actual 8000
~~~

The discrepancy amplifies through join fan-out. **A join node with a large estimated vs. actual gap** is a signal to trace down into each child to find where cardinality first diverged.

---

## 7. Building a Skewed Lab Dataset for Analysis Practice

This lesson uses the `plan_lab` schema. Create it on a dedicated practice database; the generated data is **logically reproducible**, while XIDs, runtimes, cache state, and chosen plans depend on the environment.

### 7.1. Create the customers Table

~~~sql
CREATE SCHEMA IF NOT EXISTS plan_lab;

CREATE TABLE plan_lab.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    region TEXT NOT NULL,
    is_vip BOOLEAN NOT NULL
);

INSERT INTO plan_lab.customers
    (customer_id, customer_name, region, is_vip)
SELECT
    g,
    'Customer ' || g::text,
    CASE
        WHEN g <= 1200 THEN 'north'
        WHEN g <= 1800 THEN 'south'
        ELSE 'west'
    END,
    (g % 20 = 0)
FROM generate_series(1, 2000) AS g;
~~~

There are 2,000 customers: north has 1,200, south 600, and west 200.

### 7.2. Create the orders Table with Skewed Data

~~~sql
CREATE TABLE plan_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES plan_lab.customers(customer_id),
    status TEXT NOT NULL,
    created_at DATE NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    payload TEXT NOT NULL
);

INSERT INTO plan_lab.orders
    (order_id, customer_id, status, created_at, amount, payload)
SELECT
    g::bigint,
    CASE
        WHEN g % 10 < 8 THEN (g % 100) + 1
        ELSE (g % 2000) + 1
    END,
    CASE
        WHEN g % 100 < 85 THEN 'paid'
        WHEN g % 100 < 95 THEN 'pending'
        ELSE 'canceled'
    END,
    DATE '2026-01-01' + (g % 365),
    ((g % 9000) + 100)::numeric / 100,
    repeat('x', 80)
FROM generate_series(1, 120000) AS g;
~~~

There are 120,000 orders. The `customer_id` assignment puts many orders onto a small group of customers, creating **skew**; `status` is unevenly distributed, with `paid` making up the majority. `created_at` spans multiple days.

This dataset **does not perfectly simulate production**, but it is enough to explore questions about selectivity, row counts, and join order. Modulo arithmetic introduces correlations between some columns; do not assume attributes are independent.

### 7.3. Create order_items to Observe Fan-Out

~~~sql
CREATE TABLE plan_lab.order_items (
    item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES plan_lab.orders(order_id),
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12,2) NOT NULL
);

INSERT INTO plan_lab.order_items
    (item_id, order_id, sku, quantity, unit_price)
SELECT
    g::bigint,
    ((g - 1) / 2 + 1)::bigint,
    'SKU-' || (g % 500)::text,
    (g % 5) + 1,
    ((g % 5000) + 100)::numeric / 100
FROM generate_series(1, 240000) AS g;
~~~

Each order has **two items** by the generation formula (no missing items). This gives us a known theoretical 2× fan-out for orders → items joins in the lab.

### 7.4. Update Statistics After Bulk Load

~~~sql
ANALYZE plan_lab.customers;
ANALYZE plan_lab.orders;
ANALYZE plan_lab.order_items;
~~~

`ANALYZE` samples/updates planner statistics; it **does not create indexes**. Autovacuum/autoanalyze can handle this later, but in a lab you should explicitly run it after loading bulk data so measurements have up-to-date statistics.

### 7.5. Row Counts

~~~sql
SELECT 'customers' AS entity, COUNT(*) AS n
FROM plan_lab.customers
UNION ALL
SELECT 'orders', COUNT(*) FROM plan_lab.orders
UNION ALL
SELECT 'order_items', COUNT(*) FROM plan_lab.order_items;
~~~

Expected output if the load script ran once on empty tables:

| entity | n |
|---|---:|
| customers | 2,000 |
| orders | 120,000 |
| order_items | 240,000 |

**Do not re-run INSERT on tables that already contain data** if you expect these counts; the primary key will fail with duplicates.

### 7.6. A Few Queries to Explore the Distribution

~~~sql
SELECT status, COUNT(*) AS n
FROM plan_lab.orders
GROUP BY status
ORDER BY n DESC;
~~~

~~~sql
SELECT customer_id, COUNT(*) AS n_orders
FROM plan_lab.orders
GROUP BY customer_id
ORDER BY n_orders DESC, customer_id
LIMIT 20;
~~~

~~~sql
SELECT c.region, o.status, COUNT(*) AS n
FROM plan_lab.orders AS o
JOIN plan_lab.customers AS c USING (customer_id)
GROUP BY c.region, o.status
ORDER BY c.region, n DESC;
~~~

These numbers help reveal **skew and dependencies between attributes** before inspecting plans. Accurate planner predictions require statistics matching the data distribution, not just total COUNT(*).

---

## 8. Learning to Read a Plan in Order

An effective reading process is not scanning all text left-to-right. Work in layers:

1. **Root node and total time:** final row count, Planning Time, Execution Time.
2. **Branches producing most data:** which scan/join/group/sort handles many rows?
3. **Measure row discrepancies:** which node first diverges from estimates?
4. **Check loops:** is a small node executed hundreds of thousands of times?
5. **Check resources:** buffers read/hit, temp, I/O timing, sort memory, hash batches.
6. **Find SQL/stats root causes:** predicates, join order, column correlation, indexes, data.
7. **Test one hypothesis-driven change** and compare plan and actuals afterward.

### 8.1. Do Not Just Look at the Top Node with the Largest Time

Parent nodes near the root usually have high `actual time` because they **include running their child nodes**. For example:

~~~text
Aggregate actual time=500 ms
  -> Hash Join actual time=490 ms
      -> Seq Scan on orders actual time=100 ms
      -> Hash ... actual time=390 ms
~~~

Seeing Aggregate at 500 ms **does not prove SUM/COUNT itself took 500 ms**. You must descend into the subtree to find where input is produced and resources are consumed.

### 8.2. Do Not Automatically Treat Seq Scan as the “Culprit”

If a query needs 90% of a table, a Seq Scan is often reasonable. An `Index Scan` with hundreds of thousands of random heap fetches can be slower.

**The right question:** is the node doing **necessary or unnecessary** work to satisfy the predicates and output?

### 8.3. The Truly Expensive Node Can Be Small but Looped

For instance, an Index Scan fetching one `order_items` row takes only 0.02 ms, but is invoked 100,000 times. Its cumulative cost will exceed a 20 ms Sort node, even though the Sort shows higher single-execution time on the surface.

### 8.4. Find the “First Point of Divergence”

If root rows are 100× higher than estimated, check the inputs immediately underneath. If the `orders` scan estimate is accurate but join output is wrong, suspect **join selectivity** or join key distribution. If the estimate is already off at a scan filter, inspect the corresponding statistics or predicate.

---

## 9. Diagnosing Underestimated Row Counts

A typical case:

~~~text
Nested Loop
  (cost=... rows=100 ...)
  (actual time=... rows=150000 loops=1)
  -> Index Scan on customers
       (cost=... rows=10 ...)
       (actual ... rows=200 loops=1)
  -> Index Scan on orders
       (cost=... rows=10 ...)
       (actual ... rows=750 loops=200)
~~~

This plan **illustrates the pattern only**, not actual lab output.

Key observations:

1. **Customers:** estimated 10, actual 200 → 20×.
2. **Inner orders:** estimated 10, actual 750 per loop → 75×.
3. **Loops:** inner runs 200 times.
4. **Nested Loop output:** 200 × 750 = 150,000 rows, while the planner predicted very few.

A single index lookup can be cheap, yet **200 loops × 750 rows** makes the overall query expensive. Fixing it may require better statistics, a different join strategy, or index/SQL redesign—not simply “adding an index on the inner side” if an index already exists.

### 9.1. In the Lab: Filtering High-Volume Customers

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, o.customer_id, o.amount
FROM plan_lab.orders AS o
WHERE o.customer_id BETWEEN 1 AND 100;
~~~

Compare `estimated rows` with `actual rows` at the scan/filter. With skewed data, values 1–100 can hold a much larger share of orders if the planner's distribution model does not capture it accurately.

### 9.2. Do Not Assume ANALYZE Solves Every Relationship Automatically

`ANALYZE` updates statistics. However, estimates involving correlated columns, complex expressions, or relationships **across multiple tables** can still be inaccurate even after a recent ANALYZE. Distinguish **stale** statistics from **insufficiently modeled** statistics.

### 9.3. Where Do actual rows Come From?

In `EXPLAIN (ANALYZE)`, `rows` in `actual ... rows=...` on a scan/filter is the number of rows **passed up to the parent node**, not the number of pages read. To see how many rows were discarded, read `Rows Removed by Filter` and index conditions.

---

## 10. Diagnosing Overestimated Row Counts

Another case:

~~~text
Hash Join
  (cost=... rows=300000 ...)
  (actual ... rows=400 loops=1)
~~~

The planner predicted 300,000 rows while reality was only 400. A large **overestimate** can cause it to:

- Choose Hash Join / Seq Scan instead of a selective Index Scan.
- Expect a large sort or hash table.
- Choose a suboptimal join order.
- Make different parallelism decisions.

### 10.1. Do Not Assume Hash Join Is Bad

Hash Join works very well for combining large row sets with suitable equality joins. It is only “bad” relative to an alternative on the real workload, never merely because of the node's name.

### 10.2. Finding Causes of Overestimation

- Is the predicate genuinely rare while statistics fail to reflect it?
- Is the filter value inside or outside the MCV list?
- Is there a dependency between two columns?
- Does the join condition include another highly selective condition?
- Do columns have a different NULL fraction than expected?
- Does the query use correlated subqueries or hard-to-estimate functions/parameters?
- Is the planner using a generic plan with limited parameter information?

### 10.3. Compare Actual Join Inputs and Output

If both join inputs are accurately estimated while join output is far off, the cause may be **join condition selectivity**, key distribution, or cross-table dependencies rather than base table row counts.

If one scan is already off by 100×, address the scan estimation issue before tuning database-wide cost constants.

---

## 11. Finding Expensive Nodes with BUFFERS: Cache Reads vs. Storage Reads

### 11.1. What Does BUFFERS Tell You?

With `EXPLAIN (ANALYZE, BUFFERS)`, you may see:

~~~text
Buffers: shared hit=16000 read=4200 dirtied=12 written=5
Buffers: temp read=1000 written=1030
~~~

Common counters:

| Field | Practical Meaning |
|---|---|
| `shared hit` | Pages found in PostgreSQL shared buffer cache |
| `shared read` | Pages that had to be read into shared buffers; **not necessarily physical disk I/O** since OS page cache may serve them |
| `shared dirtied` | Pages marked dirty by the measured operation |
| `shared written` | Pages written out by the backend during the measured operation |
| `local hit/read/...` | Buffers for temporary relations of the session |
| `temp read` / `temp written` | Temporary file I/O from nodes such as Sort/Hash spilling to disk |

`BUFFERS` reports **block accesses**, not row counts. The default block size in many PostgreSQL builds is 8 KiB, though it can be configured differently at build time. Do not take a raw block count and assert an exact number of bytes read from physical disk.

### 11.2. Parent Node Buffers Are Cumulative

In many plans, buffer statistics on a parent node include buffer accesses occurring inside its child nodes. Thus:

~~~text
Hash Join     Buffers: shared hit=1200
  Seq Scan A  Buffers: shared hit=700
  Hash
    Seq Scan B Buffers: shared hit=500
~~~

**Do not** sum them to 2400. The parent figure already reflects work from child nodes under executor instrumentation.

When isolating which branch touches the most pages, **compare sibling/child nodes** while accounting for inclusivity rather than summing the whole tree indiscriminately.

### 11.3. High shared read: What Does It Signal?

High `shared read` indicates data pages had to be brought into PostgreSQL shared buffers. However, to know whether the query **actually waited long on I/O**, also inspect `I/O Timings` (if enabled), node timings, storage metrics, and cache state.

A sequential scan reading 100,000 blocks on an SSD can be faster than thousands of scattered random heap fetches.

### 11.4. High shared hit Can Still Cost CPU

If a node has `shared hit=1,000,000` from 100,000 index lookups, even when pages are cached, every lookup still costs CPU and buffer-pinning overhead. “100% cache hit” does not guarantee a fast query.

### 11.5. Temp read/written Is a Signal Worth Checking

Temp I/O occurs when certain operations need more space than available in memory, such as:

- Sort spilling to disk.
- Multi-batch Hash Join.
- HashAggregate or tuplestore/materialization in applicable cases.
- Other operations needing temporary files.

Do not immediately conclude that any temp I/O requires raising `work_mem` server-wide. You need to know **which node produces temp I/O**, the data volume, strategy choices, and query concurrency.

---

## 12. I/O Timings and Real Execution Time

### 12.1. Tracking I/O Read/Write Duration

When `track_io_timing` is enabled, `EXPLAIN (ANALYZE, BUFFERS)` can display:

~~~text
I/O Timings: shared read=76.552
I/O Timings: temp read=22.100 write=35.840
~~~

The unit is normally **milliseconds**.

Check setting:

~~~sql
SHOW track_io_timing;
~~~

Enabling I/O timing has its own overhead and requires configuration privileges. Do not enable it arbitrarily in production without operational procedures; use other metrics when it is unavailable.

### 12.2. Reading I/O Time Relative to Node Time

If Execution Time is 2,000 ms while shared read I/O time is 30 ms, concluding that **all 2 seconds are disk latency** is unjustified. CPU, high loop counts, sorting/hashing, expression evaluation, or other waits may dominate.

Conversely, large I/O timing points to read/write bottlenecks; you still need to check why the access path touches so many blocks.

### 12.3. Timing Has Overhead

Recording timing on every node invocation in EXPLAIN ANALYZE can add significant overhead when loop counts are huge and each operation is tiny. To analyze cardinality without heavy timing overhead, you can use:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT ...
~~~

Remember that `TIMING OFF` **removes per-node actual time**; do not use that output to compute standalone per-node timings.

### 12.4. Measurement Results Are Not Strictly Deterministic

Latency depends on cache state, CPU scheduling, concurrency, autovacuum, WAL flushes, OS cache, and storage conditions. Measure multiple times on representative data; do not conclude a change is faster from a single 11 ms vs. 12 ms run.

---

## 13. Reading Seq Scan, Index Scan, and Bitmap Scan

### 13.1. Seq Scan

~~~text
Seq Scan on orders
  (cost=... rows=102000 ...)
  (actual time=... rows=102000 loops=1)
  Filter: (status = 'paid'::text)
  Rows Removed by Filter: 18000
~~~

If `paid` accounts for 85% of the table, a sequential scan can make sense. If a query only needs 10 rows out of 120,000 and still reads the whole table, check whether the predicate and indexes are appropriate.

### 13.2. Index Scan

~~~text
Index Scan using idx_orders_customer on orders
  Index Cond: (customer_id = 50)
  Filter: (status = 'paid')
~~~

- `Index Cond`: condition used to narrow the access path via the index.
- `Filter`: additional condition evaluated on candidate rows, potentially after fetching heap rows.
- If `Rows Removed by Filter` is very large, the index may narrow down only part of the predicate, leaving the most selective filter unhandled by the index.

Do not confuse `Filter` with conditions fully pushed into the index. Depending on columns, index type, operator classes, and expressions, PostgreSQL cannot always apply an indexable strategy for every predicate.

### 13.3. Bitmap Index Scan → Bitmap Heap Scan

~~~text
Bitmap Heap Scan on orders
  Recheck Cond: (customer_id BETWEEN 1 AND 100)
  Heap Blocks: exact=..., lossy=...
  -> Bitmap Index Scan on idx_orders_customer
       Index Cond: (customer_id BETWEEN 1 AND 100)
~~~

Bitmap Index Scan builds a map of row/page locations; Bitmap Heap Scan visits the heap by page set and performs necessary checks.

`Heap Blocks: lossy` appears when the bitmap has to represent some blocks approximately (e.g., due to memory limits), increasing row rechecks on those pages. `Recheck Cond` by itself **does not prove** an index scan became lossy.

### 13.4. Index Only Scan

~~~text
Index Only Scan using ... on orders
  Heap Fetches: 12000
~~~

The name `Index Only Scan` does **not guarantee zero heap accesses**. PostgreSQL may still have to consult the visibility map and fetch heap pages if pages are not marked all-visible.

If `Heap Fetches` is high, check index coverage, the visibility map, and UPDATE/VACUUM activity. Do not simply add INCLUDE columns and assume heap fetches will disappear.

### 13.5. Rows Removed by Filter

The lines:

~~~text
Rows Removed by Filter: 9990
actual rows=10 loops=1
~~~

indicate the node inspected roughly 10,000 candidates, discarded 9,990, and returned 10.

If `loops>1`, “Rows Removed ...” counters are usually reported as **averages per node execution**, just like actual rows. Do not ignore loops when estimating total rows processed.

### 13.6. Scanning Many Rows Is Not Inherently a Bug

If a query needs to aggregate revenue across **all 120,000 orders**, reading most of the table is necessary work; indexing `status` will not remove the need to process the full dataset. Ask whether the query/filter can reduce inputs, use summary tables, apply partition pruning, or adjust the business calculation validly.

---

## 14. Nested Loop: A Small Child Node Called Too Many Times

### 14.1. General Mechanism

~~~text
Outer row 1 ──> Inner scan ──> matching rows
Outer row 2 ──> Inner scan ──> matching rows
...
Outer row N ──> Inner scan ──> matching rows
~~~

Nested Loop works well when the **outer side is small** and the inner lookup has an appropriate index. Trouble starts when the planner expects a small outer input while reality is large, causing far more inner lookups than intended.

### 14.2. Lab with order_items

To support lookups on the join key:

~~~sql
CREATE INDEX ix_plan_items_order_id
ON plan_lab.order_items (order_id);
~~~

Query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.customer_id,
    i.item_id,
    i.quantity
FROM plan_lab.orders AS o
JOIN plan_lab.order_items AS i
  ON i.order_id = o.order_id
WHERE o.customer_id BETWEEN 1 AND 100;
~~~

With skewed data, the outer `orders` input can be large. The planner **may choose** Hash Join, Nested Loop, or another plan depending on statistics, indexes, and costs; the exercise is to read the actual plan rather than assuming a specific join node.

### 14.3. Quantifying the Amplification Cost

Suppose a plan shows:

~~~text
Nested Loop actual rows=60000 loops=1
  -> Bitmap Heap Scan on orders actual rows=30000 loops=1
  -> Index Scan on order_items actual rows=2 loops=30000
~~~

The inner scan ran roughly 30,000 times—once per outer row. Even if each lookup averages 0.02 ms:

\[
30000 \times 0.02\text{ ms} \approx 600\text{ ms}
\]

This is only a **practical rough estimate**, not an exact exclusive node time sum. Compare it against the query's Execution Time.

### 14.4. Causes to Check

- Is actual outer row count larger than estimated?
- Are inner rows per outer row larger than estimated?
- Does each index lookup trigger many heap fetches / random page reads?
- Is there an inner filter not pushed into the index?
- Does the join condition match data semantics, or does it unintentionally fan out?
- Is there a `Memoize` node caching repeated lookups in supported PostgreSQL versions?
- Do identical join keys occur heavily (skew)?

### 14.5. Do Not Disable Nested Loop Server-Wide as a “Fix”

`SET enable_nestloop = off` is a session-level hypothesis-testing tool in the lab, not a universal remedy. Small point-lookup queries can become much slower if forced into Hash Joins. Root causes are usually **cardinality estimates, index design, or join logic**.

---

## 15. Hash Join: Reading Hash Build, Batches, and Memory

### 15.1. Mechanism

An equality Hash Join typically:

1. Reads one side of the join as the **build side**.
2. Builds a hash table on the join key.
3. Reads the other side as the **probe side** and looks up matches.

Conceptual plan:

~~~text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  -> Seq Scan on orders o
  -> Hash
       Buckets: 4096  Batches: 1  Memory Usage: 210kB
       -> Seq Scan on customers c
~~~

### 15.2. Batches Greater Than 1 May Indicate Memory Spill

When the hash table does not fit within the applicable memory budget, PostgreSQL can split it into multiple batches, reading and writing temporary files.

Example:

~~~text
Hash
  Buckets: 65536  Batches: 16  Memory Usage: 8192kB
Buffers: temp written=...
~~~

Inspect:

- Actual number of batches.
- Temp I/O at Hash / Hash Join.
- Row count and width of the build side.
- Was build-side cardinality or width underestimated?
- Can filters or join order shrink the build side?
- Are `work_mem`/`hash_mem_multiplier` and concurrency balanced?

### 15.3. Do Not Raise work_mem System-Wide Immediately

`work_mem` applies **per internal operation** such as sort or hash within each query—not as a “total memory limit per connection.” One query with multiple sorts/hashes, or many concurrent queries, can consume substantial memory.

Adjust it in a **bounded session/job** scope, measure before and after, and factor in total concurrency. Increasing it excessively trades temp I/O for RAM pressure, swap, or OOM.

### 15.4. Cardinality Errors Affect Hash Join

If the planner expects 100,000 rows on the build side when reality is 2,000,000, memory sizing and cost comparisons can be skewed. Hash Join is not a “wrong plan” merely for using hashing; investigate cardinality, data skew, and actual I/O.

### 15.5. Hash Join with Non-Equality Join Conditions

Hash Join usually uses equality conditions as the hash key. If the query includes additional inequality or computed conditions, the plan may show:

~~~text
Hash Cond: (...)
Join Filter: (...)
Rows Removed by Join Filter: ...
~~~

`Join Filter` discards candidate pairs already matched by the hash condition. If huge numbers of pairs are rejected, review the join condition and opportunities to filter inputs before joining, while preserving outer join semantics.

---

## 16. Merge Join: Requiring Ordered Inputs

Merge Join exploits two input streams sorted on the join key. They can come from ordered index scans or explicit Sort nodes.

~~~text
Merge Join
  Merge Cond: (o.customer_id = c.customer_id)
  -> Sort
       Sort Key: o.customer_id
       -> Seq Scan on orders o
  -> Sort
       Sort Key: c.customer_id
       -> Seq Scan on customers c
~~~

### 16.1. When Does Merge Join Fit?

- Both sides are large.
- Ordering on the join key can be provided or sorted at reasonable cost.
- Join conditions match merge semantics.
- Downstream operations also benefit from the sort order.

### 16.2. The Bottleneck May Be in Child Sorts

A root Merge Join may report high actual time, yet **the two Sort nodes underneath are where I/O is spent**, especially if `external merge Disk: ...` appears.

### 16.3. Do Not Create Indexes Blindly Just to Avoid Sort

An index providing order can eliminate a Sort, but scanning many rows through an index incurs random heap page reads. Test natural plans with and without the index on representative data.

### 16.4. Duplicate Join Keys Cause Fan-Out

With duplicate join keys, Merge Join can still emit many combinations. Cardinality errors can arise from key duplication or skew rather than the sorting mechanism itself.

---

## 17. Sort: Spotting Disk Spills

### 17.1. In-Memory Sort

A plan may display:

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: quicksort  Memory: 4200kB
~~~

`quicksort` and `Memory` indicate the sort ran in memory using the corresponding algorithm/representation.

### 17.2. External Merge: Sort Spilling to Disk

~~~text
Sort
  Sort Key: created_at DESC
  Sort Method: external merge  Disk: 64000kB
  Buffers: temp read=... written=...
~~~

Signals:

- Large volume of data to sort.
- Insufficient memory for an in-memory sort under current settings.
- Temp reads/writes present.
- Query runtime may be dominated by temp file I/O.

### 17.3. Lab: Sorting 120,000 Rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, amount, payload
FROM plan_lab.orders
ORDER BY amount DESC, order_id;
~~~

Whether it spills to disk depends on `work_mem`, width, statistics, cache, and the planner. Do not assume 120,000 rows automatically spill.

### 17.4. Top-N Heapsort with LIMIT

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM plan_lab.orders
ORDER BY amount DESC, order_id
LIMIT 10;
~~~

When the planner picks top-N heapsort, the sort only needs to retain the target number of candidates, using far less memory than a full sort. **However, the child source may still have to read every row** to find the top 10 if no suitable ordered index exists.

### 17.5. Indexes Supporting ORDER BY

~~~sql
CREATE INDEX ix_plan_orders_amount_desc
ON plan_lab.orders (amount DESC, order_id);
~~~

This index can help `ORDER BY amount DESC, order_id LIMIT 10` return early. However:

- Returning wide rows still requires heap fetches.
- Indexes incur build and write-maintenance costs.
- If queries strongly filter by `status` or `customer_id` first, an index solely on `amount` may not be optimal.
- When returning most rows, Seq Scan + Sort can still win.

### 17.6. Incremental Sort

PostgreSQL supports **Incremental Sort** when the input is already partially sorted on a prefix of the sort key:

~~~text
Incremental Sort
  Sort Key: customer_id, created_at
  Presorted Key: customer_id
~~~

It can reduce sorting work compared to a full sort, though its effectiveness depends on group counts/prefix cardinality. If rows per group are misestimated, actual performance can diverge as well.

---

## 18. GROUP BY, DISTINCT, and Aggregate: One Output Row Does Not Mean Little Work

### 18.1. COUNT(*) Outputs Only One Row

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab.orders;
~~~

You may see:

~~~text
Aggregate actual rows=1 loops=1
  -> Seq Scan on orders actual rows=120000 loops=1
~~~

Aggregate emits **one row**, yet the child node still has to process all 120,000 rows. Looking only at root `actual rows=1` and concluding the query is cheap is a mistake.

### 18.2. HashAggregate

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(amount)
FROM plan_lab.orders
GROUP BY customer_id;
~~~

HashAggregate uses memory for group keys. If actual distinct groups exceed estimates or rows are wide, it may require more memory, partition into batches, or spill to temporary files.

Depending on PostgreSQL version, the plan may show:

~~~text
HashAggregate
  Group Key: customer_id
  Batches: 8
  Memory Usage: ...
  Disk Usage: ...
~~~

### 18.3. GroupAggregate Requires Order

An alternative strategy:

~~~text
GroupAggregate
  Group Key: customer_id
  -> Sort ...
~~~

Inspect the child Sort as well, not just the GroupAggregate node.

### 18.4. DISTINCT Can Trigger Large Sorts or Hashes

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT sku
FROM plan_lab.order_items;
~~~

Even if there are only 500 distinct SKUs across 240,000 input rows, reading and grouping the input can still be costly despite a small output. If `n_distinct` statistics are off, the planner may pick a poor aggregation strategy or miscalculate memory.

### 18.5. Pushdown Aggregation and Pre-Aggregation

When computing revenue per customer, aggregating `orders` before joining with a wide dimension table can reduce rows flowing through the join:

~~~sql
WITH totals AS (
    SELECT customer_id, SUM(amount) AS total_amount
    FROM plan_lab.orders
    GROUP BY customer_id
)
SELECT c.customer_id, c.customer_name, t.total_amount
FROM totals AS t
JOIN plan_lab.customers AS c
  ON c.customer_id = t.customer_id;
~~~

Never apply pre-aggregation blindly to arbitrary joins, because doing so can alter semantics when joins have fan-out, outer joins, row-dependent filters, or non-distributive aggregates.

---

## 19. LIMIT: Plans Can Stop Early

### 19.1. A Plan Chosen for Low Startup Cost

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM plan_lab.orders
WHERE status = 'paid'
LIMIT 10;
~~~

If qualifying rows appear early, a Seq Scan can stop very quickly once 10 rows are found, even on a large table. The planner favors low startup cost over lowest total cost when a query specifies LIMIT.

### 19.2. LIMIT Does Not Mean Every Node Processes Few Rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM plan_lab.orders
ORDER BY amount DESC
LIMIT 10;
~~~

Without an index matching the order, the node below Sort may still have to read every row before identifying the top 10.

### 19.3. Large OFFSET

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM plan_lab.orders
ORDER BY order_id
LIMIT 20 OFFSET 100000;
~~~

Even though only 20 rows are returned, the database may have to scan and discard at least 100,020 ordered positions before reaching those 20. For production pagination, consider **keyset pagination** when the application has a stable sort key.

### 19.4. Early Termination Affects Node Statistics

When LIMIT halts execution early, child node `actual rows` reflects only the work **requested up to the stopping point**, not all rows the node would have emitted if run to completion. Row differences caused by early exit are not necessarily planner cardinality errors.

---

## 20. Parallel Plans: Do Not Blindly Multiply or Add Rows

### 20.1. Gather and Gather Merge

Large queries may employ parallel workers:

~~~text
Gather
  Workers Planned: 2
  Workers Launched: 2
  -> Parallel Seq Scan on orders
       (actual ... rows=40000 loops=3)
~~~

In this illustrative example, Parallel Seq Scan is executed by the leader and two workers; `actual rows=40000 loops=3` indicates roughly 120,000 rows total across the three participants.

**Do not** read `actual rows=40000` as the query scanning only 40,000 rows total. At the same time, **do not** blindly multiply by `Workers Planned` because the actual worker count launched may differ and leader participation varies.

### 20.2. Planned vs. Launched

- `Workers Planned`: number of workers the planner budgeted.
- `Workers Launched`: number of workers actually spawned at runtime.

If `Workers Launched` is lower, resource limits or parallel worker availability may be constrained, making real runtime diverge from expectations.

### 20.3. Worker Instrumentation

When `VERBOSE` is enabled or on supported nodes, plans can include per-worker breakdown lines: actual rows, sort memory, buffers, JIT, or other activity. These details are critical when diagnosing **worker-level data skew**.

### 20.4. Parallel Hash

Parallel Hash Join has more complex memory, batching, and work-sharing rules than single-threaded Hash Join. If high batch counts or temp I/O appear, examine the **actual distribution** rather than only total row estimates.

### 20.5. Total Execution Time Is Not the Sum of Worker Elapsed Times

Workers perform portions of the work **concurrently**. Summing per-worker durations can easily exceed wall-clock execution time; distinguish total CPU effort from observed request latency.

---

## 21. JIT, Planning Time, and Execution Time

### 21.1. JIT Compilation

On PostgreSQL builds with JIT enabled and plans crossing the threshold, EXPLAIN ANALYZE output may include a section like:

~~~text
JIT:
  Functions: ...
  Options: Inlining ..., Optimization ..., Expressions ..., Deforming ...
  Timing: Generation ..., Inlining ..., Optimization ..., Emission ..., Total ...
~~~

JIT can speed up CPU-bound queries processing large data volumes, but compilation overhead can be significant relative to small queries. Evaluate JIT timings in context over multiple runs rather than toggling it globally for every workload.

### 21.2. Planning Time

`Planning Time` measures how long planning took for the statement under EXPLAIN instrumentation. Queries touching many tables, partitions, or complex expressions can incur noticeable planning overhead even when execution is fast.

### 21.3. Execution Time

`Execution Time` is the executor's measured runtime for running the statement under EXPLAIN ANALYZE (subject to trigger, instrumentation, and overhead semantics); it **does not equal total client-observed round-trip latency**.

For instance, EXPLAIN ANALYZE does not serialize and stream result rows to the client like a normal SELECT; it executes the plan and returns the plan output itself. Network serialization, transfer, and client processing in real requests can differ.

### 21.4. One Query Executed Many Times

An API calling the same prepared statement 10,000 times can consume huge total resources even at 0.5 ms per call. An EXPLAIN of one invocation does not replace checking **execution frequency** in query statistics tools.

---

## 22. Rows Removed by Filter, Join Filter, and Index Recheck

These counters reveal “how much work was done only to be discarded.”

| Metric | Diagnostic Clue |
|---|---|
| `Rows Removed by Filter` | Candidate rows rejected by a node's filter |
| `Rows Removed by Join Filter` | Candidate row pairs checked during a join that failed the filter |
| `Rows Removed by Index Recheck` | Candidates rejected when the executor rechecked the index condition |
| `Heap Blocks: lossy` | Bitmap heap scan had to track some pages approximately |
| `Heap Fetches` | Index Only Scan still had to visit the heap to check visibility |
| `Rows Removed by Conflict Filter` | Appears in certain execution contexts (such as upsert conflicts); inspect the enclosing node |

### 22.1. Post-Scan Filtering Can Be the Bottleneck

~~~text
Index Scan using idx_orders_customer ...
  Index Cond: (customer_id = 50)
  Filter: (status = 'canceled')
  Rows Removed by Filter: 10000
  actual rows=1
~~~

If the workload frequently filters on both `customer_id` and `status`, a composite or partial index can help:

~~~sql
CREATE INDEX ix_orders_customer_status
ON plan_lab.orders (customer_id, status);
~~~

However, effectiveness depends on selectivity, correlation, and write volume. Do not create it directly in production from a single illustrative plan.

### 22.2. High Recheck Counts May Stem from Lossy Bitmaps

If a plan reports many `Rows Removed by Index Recheck`, check `Heap Blocks: exact/lossy`, index operator class, and `work_mem`. Insufficient bitmap memory—not necessarily the “wrong index”—may be the reason.

### 22.3. Join Filter and Outer Join Semantics

Moving a predicate between `WHERE` and `ON` can **change LEFT JOIN results** due to NULL-extended rows. Never manually “push down a filter” solely for speed without verifying query semantics.

Example:

~~~sql
-- Keeps only customers with a paid order: WHERE filters out
-- unmatched NULL-extended rows from the LEFT JOIN.
SELECT c.customer_id, o.order_id
FROM plan_lab.customers AS c
LEFT JOIN plan_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'paid';
~~~

~~~sql
-- Preserves customers without paid orders, with o.* = NULL:
SELECT c.customer_id, o.order_id
FROM plan_lab.customers AS c
LEFT JOIN plan_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid';
~~~

These two queries have different business semantics and must not be swapped merely because one emits fewer rows.

---

## 23. Why Are Estimates Wrong? Planner Statistics

### 23.1. The Planner Does Not Read the Entire Table Before Every Query

PostgreSQL does not run COUNT(*) or scan all values before each SELECT. It relies on statistics, metadata, and cost-model assumptions:

- `pg_class.reltuples`: **estimated** row count of a relation.
- `pg_class.relpages`: associated page count.
- `pg_statistic`: internal catalog holding column-level statistics.
- `pg_stats`: readable view over column statistics when permitted.
- `pg_statistic_ext`, `pg_statistic_ext_data`, and `pg_stats_ext`: multi-column/expression extended statistics where supported by the version.
- Metadata on indexes, constraints, uniqueness, partitions, expressions, and planner settings.

These figures can become **unrepresentative of recent data** or lack enough detail to model correlations.

### 23.2. Inspecting pg_stats

~~~sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'plan_lab'
  AND tablename = 'orders'
  AND attname IN ('customer_id', 'status', 'created_at', 'amount')
ORDER BY attname;
~~~

| Field | Interpretation |
|---|---|
| `null_frac` | Estimated fraction of NULL values |
| `n_distinct` | Estimated distinct count; negative values express a fraction relative to total rows |
| `most_common_vals` | Values appearing most frequently in the sample |
| `most_common_freqs` | Frequencies corresponding to MCVs |
| `histogram_bounds` | Bucket boundaries used to estimate range predicates |
| `correlation` | Correlation between value order and physical row order, affecting index scan cost |

`correlation` here **is not correlation between two columns**. It measures how closely a single column's sort order matches physical storage order, helping the planner estimate heap access cost.

### 23.3. n_distinct Can Be Negative

In `pg_stats`, a negative `n_distinct` represents an expected distinct count that scales with table size as a negative fraction of row count. For instance, `-1` indicates nearly every row has a unique value. Do not misread it as "minus one distinct value."

### 23.4. MCVs Matter Greatly Under Skew

If `status='paid'` appears in 85% of rows, assuming three statuses are equally likely fails badly. `most_common_vals` and `most_common_freqs` capture skewed frequencies for frequent values.

Some customers place far more orders than others. MCVs on `customer_id` distinguish hot customers from rare ones, though sample size, distinct count, and generic plans also affect accuracy.

### 23.5. Histograms Do Not Solve Every Predicate

Single-column histograms help estimate `created_at BETWEEN ...`. They cannot by themselves know how customer tier, status, and amount relate to one another. Multi-predicate queries require joint selectivity modeling.

---

## 24. Stale Statistics: Identifying and Fixing with ANALYZE

### 24.1. When Do Statistics Become Unrepresentative?

- Bulk-loading many rows after the last ANALYZE.
- Deleting a large share of rows in a segment or partition.
- Backfills that substantially shift status/region distributions.
- Promotions causing a few customers to generate most orders.
- New data falling outside the existing histogram bounds.
- Newly attached/loaded partitions where query-level stats do not yet reflect the data.

### 24.2. Checking Last ANALYZE Time and Modification Counts

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze,
    analyze_count,
    autoanalyze_count
FROM pg_stat_user_tables
WHERE schemaname = 'plan_lab'
ORDER BY relname;
~~~

These are **statistical estimates/counters**, not exact COUNT(*) values. `n_mod_since_analyze` indicates roughly how many rows changed since the last ANALYZE.

### 24.3. Refreshing Stats

~~~sql
ANALYZE plan_lab.orders;
ANALYZE plan_lab.customers;
ANALYZE plan_lab.order_items;
~~~

After ANALYZE, compare plans and check:

- Did estimated rows move closer to actuals?
- Did join order or scan strategy change?
- Did Sort/Hash temp I/O decrease?
- Did Execution Time improve consistently across multiple runs?

`ANALYZE` **does not fix bad SQL, does not create indexes, does not guarantee the optimal plan**, and sample-based statistics still retain sampling error.

### 24.4. ANALYZE Is Not VACUUM FULL

ANALYZE gathers statistics with corresponding CPU/I/O/lock cost. It does not rewrite the entire table to reclaim disk space to the OS. Avoid running it unnecessarily often on large tables without clear diagnostic or monitoring reasons.

### 24.5. When Data Changes Very Rapidly

If statistics keep going stale before autoanalyze triggers, evaluate autovacuum/autoanalyze thresholds per table and workload rather than raising statistics targets on every column, since the issue may be refresh cadence or shifting distributions.

---

## 25. Statistics Target and Sample Quality

### 25.1. Defaults Have Finite Granularity

`default_statistics_target` controls the target number of MCV/histogram entries and influences the sample size collected for column statistics.

~~~sql
SHOW default_statistics_target;
~~~

### 25.2. Increasing Target on Key Columns

~~~sql
ALTER TABLE plan_lab.orders
    ALTER COLUMN customer_id SET STATISTICS 500;

ANALYZE plan_lab.orders;
~~~

Raising the target can better represent complex distributions at the cost of extra collection time and catalog storage; it does not guarantee perfect estimates.

### 25.3. When Is It Worth Testing?

- A column has many distinct values with some very frequent outliers.
- Critical queries depend heavily on that column's selectivity.
- Current MCV/histogram buckets are too coarse for the distribution.
- Estimation divergence begins right at that column's scan/filter.
- You have before/after plans to evaluate the effect.

Do not crank targets to maximum on every column just to get longer histograms.

### 25.4. Re-Inspecting Statistics

~~~sql
SELECT
    attname,
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname = 'plan_lab'
  AND tablename = 'orders'
  AND attname = 'customer_id';
~~~

When re-testing, use the exact same SQL, parameters, and dataset. Whether the plan changes or stays the same is a valid observation—not an exercise where you must force a plan change.

---

## 26. Extended Statistics: Correlation Between Columns

### 26.1. The Independence Assumption Problem

Suppose you filter with:

~~~sql
WHERE status = 'paid'
  AND customer_id BETWEEN 1 AND 100
~~~

When attributes are correlated, multiplying individual predicate probabilities gives wrong answers.

Theoretical example:

~~~text
P(status='paid') = 0.8
P(customer in hot group) = 0.5

Independence assumption: P(both) ≈ 0.8 × 0.5 = 0.4
Actual data:             P(both) = 0.65
~~~

The planner can underestimate by 0.65 / 0.4 ≈ 1.625× at the scan. Across joins, that error can compound.

### 26.2. CREATE STATISTICS

~~~sql
CREATE STATISTICS st_plan_orders_status_customer
    (dependencies, ndistinct, mcv)
ON status, customer_id
FROM plan_lab.orders;

ANALYZE plan_lab.orders;
~~~

| Kind | Purpose |
|---|---|
| `dependencies` | Models functional dependencies between columns; useful for some equality predicates |
| `ndistinct` | Estimates distinct combinations, helpful for GROUP BY/DISTINCT |
| `mcv` | Tracks common multi-column value combinations |

### 26.3. Inspecting pg_stats_ext

~~~sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds,
    n_distinct,
    dependencies
FROM pg_stats_ext
WHERE schemaname = 'plan_lab'
  AND tablename = 'orders'
ORDER BY statistics_name;
~~~

Available columns and view privileges can vary across major PostgreSQL versions. Check your version's catalog/view if a column is unavailable.

### 26.4. Limitations of Extended Statistics

- Functional dependencies do not apply to all range or cross-column predicates.
- MCV lists cover only part of a distribution.
- `ndistinct` does not replace general join fan-out statistics.
- In current PostgreSQL versions, extended statistics generally do not model **cross-relation join selectivity**.
- Data updates still require ANALYZE.

Therefore, if misestimation starts **at a join**, adding extended stats across columns of a single table may not be enough.

### 26.5. Before/After Comparison Exercise

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM plan_lab.orders
WHERE status = 'paid'
  AND customer_id BETWEEN 1 AND 100;
~~~

After `CREATE STATISTICS` and ANALYZE, run it again. Whether estimates improve or stay unchanged is useful diagnostic evidence: the goal is **evidence-based reading**.

---

## 27. Join Misestimation: Key Distribution and Fan-Out

### 27.1. Join Cardinality Is Not Just Base Table Sizes

~~~sql
SELECT COUNT(*)
FROM plan_lab.orders AS o
JOIN plan_lab.order_items AS i
  ON i.order_id = o.order_id;
~~~

The lab has 120,000 orders and 240,000 items—two items per order—so the join produces **240,000 rows** when loaded properly.

### 27.2. Uniqueness Helps the Planner

`orders.order_id` is a PRIMARY KEY and `order_items.order_id` is a FOREIGN KEY. Having one side unique on `order_id` supplies structural information. In real applications, items per order may be skewed; this lab uses a fixed two items per order.

### 27.3. Join Key Skew

In production data, certain join keys can occur heavily. Check:

~~~sql
SELECT order_id, COUNT(*) AS item_count
FROM plan_lab.order_items
GROUP BY order_id
ORDER BY item_count DESC, order_id
LIMIT 20;
~~~

Seeing two rows per group in the lab must not be extrapolated to production.

### 27.4. Wrong Join Conditions Can Explode Output

~~~sql
-- Illustration only; do not execute without LIMIT on a large table:
SELECT *
FROM plan_lab.orders AS o
JOIN plan_lab.order_items AS i
  ON i.order_id >= o.order_id;
~~~

Using `>=` generates huge numbers of pairs instead of matching items to their own order. When join output explodes, inspect **SQL semantics**, not just statistics.

### 27.5. Questions Before Adding an Index

- Does the join key include all necessary composite key columns?
- Are you joining fact-to-fact and causing fan-out?
- Are there duplicates or an intermediate bridge table?
- Does one side have the business-appropriate PK/UNIQUE constraint?
- Did the misestimate originate at a scan or only at the join?
- Is there an unintentional CROSS JOIN?

### 27.6. Correct Estimate When Output Is Naturally Huge

If business requirements genuinely ask for 10 million rows, even a perfectly accurate planner estimate will yield a slow query due to result volume. Solutions include pagination, pre-aggregation, or revisiting requirements—not “tweaking stats to pretend rows are fewer.”

---

## 28. Prepared Statements: Generic Plans vs. Custom Plans

### 28.1. Parameter Sensitivity

~~~sql
SELECT order_id
FROM plan_lab.orders
WHERE status = $1;
~~~

`$1='paid'` returns ~85% of the table, whereas `$1='canceled'` returns ~5%. Optimal access paths can differ. A **generic plan** is not tailored to each specific value the way a custom plan is.

### 28.2. PREPARE/EXECUTE in the Lab

~~~sql
PREPARE find_orders_by_status(text) AS
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE status = $1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('paid');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('canceled');

DEALLOCATE find_orders_by_status;
~~~

PostgreSQL chooses between custom and generic plans based on cost heuristics and prepared-statement execution history. Two runs are not enough to guarantee a generic plan was selected.

### 28.3. Comparing Generic vs. Custom in the Lab

~~~sql
PREPARE find_orders_by_status(text) AS
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE status = $1;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('paid');
ROLLBACK;

BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE find_orders_by_status('paid');
ROLLBACK;

DEALLOCATE find_orders_by_status;
~~~

This is a **lab session experiment**, not a recommendation to force custom or generic plans globally in production.

### 28.4. ORMs and Connection Pools

Drivers and ORMs often use bind parameters and server-side prepared statements. A query that is slow only for certain “hot” parameter values can stem from parameter-sensitive plans. Collect **representative parameter samples** within security policy, not just SQL placeholders.

---

## 29. Expressions, Casts, and Indexability

### 29.1. Functions on Columns Can Prevent Index Use

With a B-tree index on `created_at`, the predicate:

~~~sql
WHERE created_at >= DATE '2026-03-01'
  AND created_at < DATE '2026-04-01'
~~~

maps cleanly to an index range scan, unlike:

~~~sql
WHERE created_at::text LIKE '2026-03%'
~~~

The second casts to text and pattern-matches, carries different semantics, and typically cannot use a plain B-tree index on a DATE column for a range scan.

### 29.2. Query Rewrites Must Preserve Semantics

For a DATE column, both forms describe March. For TIMESTAMPTZ, however, “March” depends on business timezone. Never convert `date_trunc('day', timestamptz)` into UTC bounds if the business expects local calendar days in another timezone.

### 29.3. Expression Indexes Are a Separate Option

~~~sql
CREATE INDEX ix_plan_orders_month_expr
ON plan_lab.orders (
    (date_trunc('month', created_at::timestamp))
);
~~~

Here a DATE column is cast to timestamp to extract the month; an expression index can accelerate queries matching that exact expression. It will not speed up arbitrary month predicates automatically, adds write overhead, and requires the indexed expression to be immutable.

### 29.4. OR and Selectivity

~~~sql
WHERE customer_id = 10 OR status = 'canceled'
~~~

PostgreSQL may combine indexes via BitmapOr, choose Seq Scan, or use another access path. Estimates for OR can be off when conditions are correlated. Do not rewrite OR into UNION ALL blindly if both branches could emit the same row (which creates duplicates unless deduplicated); preserve OR semantics.

---

## 30. Partial Indexes and Composite Indexes

### 30.1. Partial Index for Rare Status Values

~~~sql
CREATE INDEX ix_plan_orders_canceled_customer
ON plan_lab.orders (customer_id)
WHERE status = 'canceled';
~~~

When `canceled` is a small fraction of rows, a partial index stays compact and serves specialized queries well.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE status = 'canceled'
  AND customer_id = 50;
~~~

The planner can use a partial index when it can prove the query predicate **implies** the index's `WHERE` predicate. A generic plan with `status=$1` cannot prove that condition for all parameter values.

### 30.2. Composite Index

~~~sql
CREATE INDEX ix_plan_orders_customer_created
ON plan_lab.orders (customer_id, created_at DESC);
~~~

This can serve:

~~~sql
SELECT order_id, created_at, amount
FROM plan_lab.orders
WHERE customer_id = 50
ORDER BY created_at DESC
LIMIT 20;
~~~

The leading column supports equality, and the trailing column supports ordering. If dominant queries also filter by status or target a very hot customer, benchmark against the actual workload rather than assuming this index is always ideal.

### 30.3. INCLUDE

~~~sql
CREATE INDEX ix_plan_orders_customer_date_cover
ON plan_lab.orders (customer_id, created_at DESC)
INCLUDE (amount, status);
~~~

INCLUDE stores extra payload columns to enable some Index Only Scans, though included columns **do not act as search keys**, and visibility map state can still cause an Index Only Scan to perform heap fetches.

### 30.4. Do Not Create Every Candidate Index in Production

Creating three overlapping indexes increases insert/update/delete overhead, disk footprint, VACUUM time, reindex cost, and migration duration. Select indexes based on critical queries, data distribution, plans, and measured net gains.

---

## 31. Walkthrough: Investigating a Query and Testing a Fix

### 31.1. Business Requirement

An API returns the 20 most recent paid orders from March, along with customer names.

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    o.customer_id,
    o.created_at,
    o.amount,
    c.customer_name
FROM plan_lab.orders AS o
JOIN plan_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
  AND o.created_at >= DATE '2026-03-01'
  AND o.created_at < DATE '2026-04-01'
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 20;
~~~

### 31.2. Evidence Checklist Table

| Question | Where to Look |
|---|---|
| What is Execution Time? | Plan summary footer |
| How many rows does the root return? | Root `actual rows` |
| Which node touches the most shared/temp blocks? | `BUFFERS` and child nodes |
| Did Sort spill to external merge? | `Sort Method`/`Disk` |
| Where did estimates first diverge? | Compare `rows` vs. `actual rows` bottom-up |
| How many loops did Nested Loop inner run? | Inner node `loops` |
| Did Index Scan discard many rows after fetching? | `Rows Removed by Filter` |
| What indexes already exist? | `pg_indexes` |
| Are stats fresh or stale? | `pg_stats`/`pg_stat_user_tables` |

### 31.3. Formulate a Hypothesis

Hypothesis:

> The query spends excessive time scanning and sorting because there is no index aligned with the `status + created_at + order_id` filter/order pattern.

Candidate index:

~~~sql
CREATE INDEX ix_plan_orders_status_created
ON plan_lab.orders (status, created_at DESC, order_id DESC);
~~~

Do not assert ahead of time that this index will always beat an index on `customer_id` or a Seq Scan. If the query matches most of the table or filters differently, the trade-off can reverse.

### 31.4. Measure Before and After

1. Save the baseline plan and execution metrics.
2. Create the candidate index in lab/staging.
3. Run ANALYZE if data or statistics changed.
4. Re-run the exact same query and parameters.
5. Compare rows, buffers, sort method, loops, and runtimes across multiple iterations.
6. Measure write throughput, index size, and impact on other queries.
7. Keep the change only if gains are reliable and trade-offs are acceptable.

### 31.5. Sometimes SQL Needs Fixing Instead of Adding Indexes

If SQL produces millions of intermediate rows due to an unintended join, unnecessary DISTINCT, or grouping at the wrong granularity, an index may not solve it. Confirm **result granularity** and semantics before tuning access paths.

---

## 32. Partition Pruning and Estimates on Partitioned Tables

### 32.1. Clues in the Plan

~~~text
Append
  -> Seq Scan on orders_2026_03
  -> Seq Scan on orders_2026_04
~~~

Plans can also use MergeAppend or Parallel Append. Depending on the situation, output may show `Subplans Removed` or `never executed` from execution-time partition pruning.

### 32.2. Not Seeing All Partitions Is Expected Behavior

When a query filters March and partition pruning works, non-matching partitions are skipped. Conversely, if a predicate wraps the partition key in a cast or function that prevents range inference, the optimizer may inspect more partitions than necessary.

### 32.3. Statistics on Partitions

Distributions can vary widely across partitions—for example, a promotional month may have high cancellation rates while normal months do not. Inspect parent/child stats as appropriate for your PostgreSQL version rather than assuming uniform distribution from parent totals.

### 32.4. Partitions and Parallel Workers

One oversized partition can skew parallel worker execution; slowdowns may stem from **data skew and parallel scheduling**, not missing indexes.

---

## 33. Other Sources of Divergence to Investigate

### 33.1. Customer-Level Data Skew

A handful of customers have 100,000 orders while most have 1–2. Estimating by “average orders per customer” fails badly on hot keys. Check MCV frequencies and generic vs. custom plans.

### 33.2. Correlation Between Filters

A product category may sell almost exclusively in one region. Multiplying probabilities under an independence assumption produces wrong row estimates. Test multi-column extended statistics if both attributes live on the same table and your PostgreSQL version supports that predicate pattern.

### 33.3. Hard-to-Estimate Expressions

Functions or casts mismatched with statistics/indexes degrade estimates. Never mark a VOLATILE function as IMMUTABLE just to force index usage if it depends on time, tables, or session state.

### 33.4. Values Outside Older Histograms

Append-heavy time-series tables receive timestamps newer than the sampled statistics. Queries targeting the last hour can get poor estimates if autoanalyze lags behind ingestion.

### 33.5. NULL Fraction

If 90% of rows are NULL while stats say 5%, `IS NULL` / `IS NOT NULL` estimates will be off. Inspect `null_frac`.

### 33.6. Duplicate Join Keys

Joining against tables lacking uniqueness or bridge tables with duplicates creates fan-out. Properly enforced PRIMARY KEY and UNIQUE constraints protect data integrity and supply valuable metadata to the optimizer.

### 33.7. Prepared Plans

A single generic plan might suit `status='paid'` yet perform poorly for `'canceled'` (or vice versa). Inspect actual runtime plans and parameters, not just one literal EXPLAIN run.

### 33.8. Wide Rows

`SELECT *` on tables with large TEXT `payload` columns inflates row width, sort/hash memory consumption, heap fetches, and network traffic. Selecting only `order_id` and `amount` when that is all the API needs can improve performance without touching indexes.

### 33.9. Concurrent Load

A plan taking 200 ms single-threaded may take seconds under 100 concurrent requests. Do not blame cardinality estimates automatically; contention could come from queueing, shared I/O, locks, CPU saturation, or connection pools.

### 33.10. JIT on Small Queries

If JIT compilation consumes most of a short statement's Execution Time, inspect JIT thresholds and workload profile instead of blindly raising statistics targets or adding indexes.

---

## 34. Finding Resource-Heavy Queries with pg_stat_statements

EXPLAIN analyzes **a single execution**. In production, you also need to know which queries run frequently or dominate aggregate latency.

Once `pg_stat_statements` is properly configured per operational standards:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
~~~

Note: running `CREATE EXTENSION` alone **does not guarantee statistics collection is active**; server preloading/configuration and appropriate privileges are usually required.

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    temp_blks_written,
    LEFT(query, 200) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
~~~

Run this only if the view is enabled and your role has permission to read it.

### 34.1. Total Time vs. Mean Time

| Query | Calls | Mean | Total |
|---|---:|---:|---:|
| A | 100,000 | 2 ms | 200,000 ms |
| B | 10 | 1,000 ms | 10,000 ms |

Query B is slow per call, while A consumes far more aggregate database resources via call frequency. Distinguish between reducing **single-request latency** and reducing **total system load**.

### 34.2. Mean Is Not p95

`mean_exec_time` is an arithmetic mean, not a percentile. For tail latency analysis, combine it with distribution metrics from APM, histograms, or logs.

### 34.3. Queryid and Parameters

Normalized queries group multiple parameter sets under one `queryid`. It hides specific parameter values, plan variants, and cache states. Pair query stats with EXPLAIN runs using representative parameter samples.

### 34.4. Protecting Query Logs

Plans and SQL text may contain literals, table names, or sensitive data. Never send production logs to unapproved external services.

---

## 35. Investigation Workflow: From Symptom to Root Cause

~~~mermaid
flowchart TD
    A["Slow query / p95 spike"] --> B["Collect SQL, params, plan, metrics"]
    B --> C["EXPLAIN ANALYZE BUFFERS in authorized env"]
    C --> D["Root: planning, execution, output rows"]
    D --> E{"Large cardinality mismatch?"}
    E -- "Yes" --> F["Walk down to first divergent node"]
    F --> G{"Filter or join?"}
    G -- "Filter" --> H["pg_stats, skew, ANALYZE, extended stats"]
    G -- "Join" --> I["Join keys, fan-out, uniqueness, skew"]
    E -- "No / small" --> J["Loops, buffers, Sort/Hash, parallel"]
    H --> K["Form evidence-based hypothesis"]
    I --> K
    J --> K
    K --> L["Benchmark before/after on same workload"]
    L --> M{"Stable win, acceptable trade-offs?"}
    M -- "Yes" --> N["Deploy with monitoring"]
    M -- "No" --> O["Revert, evaluate next hypothesis"]
~~~

### 35.1. Diagnostic Notes Template

~~~text
Query fingerprint:
Parameter profile:
PostgreSQL version:
Row counts / table sizes:
Indexes present:
Last ANALYZE:
Plan captured at:
Planning Time:
Execution Time:
Worst estimate ratio:
First divergent node:
Highest loops and inner node:
Highest shared read / temp I/O branch:
Sort Method / Hash Batches:
Workers planned / launched:
Hypothesis:
Change:
After-plan evidence:
Safety / rollback:
~~~

Do not write “bug in Hash Join” merely because Hash Join has high inclusive time; break down build, probe, row counts, and I/O.

### 35.2. Goals Depend on Workload

An end-of-day batch report prioritizes total runtime and resource efficiency, whereas a real-time API prioritizes p95/p99 latency and avoiding lock contention. Judge indexes and plans against the primary goal.

### 35.3. Change One Variable at a Time

Do not simultaneously create five indexes, raise `work_mem`, disable Nested Loop, and rewrite SQL, then declare “optimization succeeded” without knowing why. Each experiment needs one hypothesis, measurable evidence, and a rollback plan.

---

## 36. Plan Reading Checklist

### 36.1. SQL and Environment

- [ ] Are representative parameter/literal values captured?
- [ ] Are we measuring a safe SELECT or DML with side effects?
- [ ] Are there LIMIT/OFFSET, DISTINCT, ORDER BY, or outer joins?
- [ ] Do data, schema, and indexes match the target environment?
- [ ] Is a prepared generic or custom plan involved?
- [ ] Are transactions, locks, or concurrent load distorting results?

### 36.2. Estimated Values

- [ ] `rows` inspected per node, not only at the root.
- [ ] Does `width` look realistic for wide columns?
- [ ] Avoid reading `cost` as milliseconds.
- [ ] Did divergence begin at a scan or at a join?
- [ ] Are any planner settings/cost constants non-default?

### 36.3. Actual Values

- [ ] Read `actual rows` together with `loops`.
- [ ] Check for `never executed`, LIMIT early exit, and partition pruning.
- [ ] Remember `actual time` is inclusive/per-loop; do not sum across the tree.
- [ ] Inspect `Rows Removed by Filter/Join Filter/Recheck`.
- [ ] Compare `Index Cond` vs. `Filter`.
- [ ] Check `shared hit/read`, temp read/write, and I/O timings.
- [ ] Check Sort Method, Disk, Hash Batches, and Memory Usage.
- [ ] Check Workers Planned/Launched and per-worker distribution.

### 36.4. Root Cause and Verification

- [ ] Stale statistics vs. insufficiently modeled statistics?
- [ ] Skew, correlation, NULL fraction, or duplicate join keys?
- [ ] Index alignment with filter + ORDER BY + LIMIT?
- [ ] Inner node executed in excessive loops?
- [ ] Query generating unnecessary intermediate rows?
- [ ] Any concurrency, I/O, JIT, or parallelism bottlenecks?
- [ ] Multiple before/after measurements on representative data?
- [ ] Evaluated write impact, disk footprint, and regression risk?

---

## 37. Common Misconceptions

| Misconception | Why It Is Wrong | Proper Interpretation |
|---|---|---|
| “cost=1000 means 1000 ms” | Cost uses relative planner units | Check actual time and Execution Time |
| “rows=2 loops=5000 means two rows total” | Two rows on average **per loop** | Roughly 10,000 output rows |
| “Five nodes at 100 ms each ⇒ 500 ms” | Parent time includes child time | Use Execution Time and read top-down |
| “Highest time at root is the culprit” | Root wraps all subtrees | Walk down the branches |
| “Seq Scan is always bad” | Scanning most of a table can be optimal | Evaluate selectivity |
| “Index Scan is always good” | Heavy random fetches/loops can be slower | Check Buffers, Heap Fetches, loops |
| “Filter drops many rows ⇒ add an index” | Index may not help or query needs full table | Inspect predicate and workload |
| “Hash Join means bad plan” | Often optimal for large equi-joins | Check build side, batches, fan-out |
| “external merge ⇒ raise work_mem globally” | Applies per operator across concurrent queries | Test locally and size to load |
| “Recheck Cond ⇒ index gives wrong answers” | Recheck verifies exact predicates | Check exact/lossy pages and candidates |
| “shared read = physical disk I/O” | OS page cache may satisfy reads | Check I/O Timings alongside buffers |
| “shared hit costs zero CPU” | Buffer pins and loops still cost CPU | Inspect actual time |
| “ANALYZE makes every estimate accurate” | Correlations, joins, and params remain hard | Re-check cardinality |
| “Extended stats fix all join estimates” | Limited scope across relations | Inspect join keys and uniqueness |
| “Higher statistics target is always better” | Raises stats cost and misses non-histogram issues | Tune selectively |
| “Planner must use a newly created index” | Optimizer is cost-driven | Verify with EXPLAIN |
| “LIMIT 10 processes at most 10 rows” | Sort/Aggregate may consume full input first | Inspect subtree |
| “OFFSET 100000 only processes LIMIT 20” | Must skip 100,000 positions | Use keyset pagination |
| “Workers Planned equals Workers Launched” | Runtime may grant fewer workers | Read both lines |
| “EXPLAIN ANALYZE DELETE only estimates” | Actually executes the DELETE | Run in lab with proper rollback |
| “One 9 ms vs. 10 ms run proves improvement” | Noise from cache/concurrency | Run multiple trials |
| “Swapping LEFT JOIN WHERE/ON is just tuning” | Changes result semantics | Preserve exact query meaning |
| “Mean latency equals p95” | Mean is not a percentile | Measure tail distributions |

---

## 38. Practice Exercises

Exercises use `plan_lab.customers`, `orders`, and `order_items` from Section 7. Text plan snippets in the questions are **synthetic numbers for reading practice**, not fixed output from a live PostgreSQL instance.

### Exercise 1 — Cost Is Not Milliseconds

Given the node:

~~~text
Index Scan on orders
  (cost=0.42..350.00 rows=100 width=24)
  (actual time=0.040..2.800 rows=120 loops=1)
~~~

Explain the exact meaning of the four numbers 0.42, 350.00, 100, and 120. Can you conclude the node “predicted 350 ms and ran in 2.8 ms”?

### Exercise 2 — Startup Cost

A query has `LIMIT 1`. The planner chooses between plan A (low startup cost, high total cost) and plan B (low total cost, high startup cost). Why might A win?

### Exercise 3 — Computing Total Output from Loops

~~~text
Index Scan
  (cost=... rows=2 ...)
  (actual time=0.010..0.030 rows=3 loops=10000)
~~~

Estimate the total rows emitted by this node and a rough cumulative `actual time` sum. State the limitations of that timing calculation.

### Exercise 4 — Cardinality Misestimation

Compute the misestimate factor and direction for each pair:

1. Estimated 50, actual 5000.
2. Estimated 30000, actual 100.
3. Estimated 2000, actual 2400.
4. Estimated 1, actual 0.

### Exercise 5 — Finding the First Divergence Point

~~~text
Hash Join: estimated 10000, actual 500000
  Seq Scan orders: estimated 100000, actual 105000
  Hash:
    Seq Scan customers: estimated 2000, actual 2000
~~~

Are the scans accurate? Should you investigate scan filters or join selectivity/logic first? Why?

### Exercise 6 — Is the Largest Root Time a Bug?

~~~text
Aggregate actual time=...1000ms
  Hash Join actual time=...990ms
    Seq Scan A actual time=...600ms
    Hash actual time=...390ms
~~~

Can you say Aggregate alone took 1000 ms? Explain inclusive time.

### Exercise 7 — Rows Removed by Filter

~~~text
Seq Scan on orders
  actual rows=100 loops=1
  Rows Removed by Filter: 119900
~~~

Roughly how many candidate rows were inspected? Why examine the predicate before creating an index?

### Exercise 8 — Index Cond vs. Filter

~~~text
Index Scan on orders
  Index Cond: (customer_id = 50)
  Filter: (status = 'canceled')
  Rows Removed by Filter: 5000
~~~

Which condition drives the index lookup? Which filters candidates afterward? Propose a candidate index design if this query is extremely frequent.

### Exercise 9 — Buffer Counts

`shared hit=120000` and `shared read=0`. Can you conclude the query is inexpensive and runs very fast? Why or why not?

### Exercise 10 — Physical Disk

Does `shared read=5000` prove the OS read 5,000 pages from a physical SSD? Name additional metrics or measurements to inspect.

### Exercise 11 — Summing Buffers

A parent node shows `shared hit=1500`; its two child nodes show `shared hit=800` and `shared hit=700`. Can you conclude total buffer hits are 3,000?

### Exercise 12 — External Sort

~~~text
Sort
  Sort Method: external merge  Disk: 50000kB
  Buffers: temp read=6500 written=6600
~~~

What does this indicate? Name at least three investigation or experiment directions.

### Exercise 13 — Top-N Heapsort

Why can `ORDER BY amount DESC LIMIT 10` use far less memory than a full sort while still needing to scan many rows?

### Exercise 14 — Hash Batches

~~~text
Hash
  Buckets: 65536 Batches: 16 Memory Usage: 8192kB
~~~

What does `Batches=16` suggest? List four settings or conditions to inspect.

### Exercise 15 — work_mem

A query contains three sorts and two hashes, running at 20 concurrent queries. Why can increasing server-wide `work_mem` from 4 MB to 512 MB be dangerous?

### Exercise 16 — COUNT(*) Single-Row Output

~~~text
Aggregate actual rows=1
  Seq Scan orders actual rows=120000
~~~

Why can a query returning a single row still take considerable time?

### Exercise 17 — Nested Loop

The outer node emits 20,000 rows, and the inner index scan averages two rows per loop with `loops=20000`. Roughly how many rows does the join output? Why can an inner scan averaging 0.025 ms per loop still be significant?

### Exercise 18 — Parallel Execution

~~~text
Gather
  Workers Planned: 3
  Workers Launched: 2
  -> Parallel Seq Scan
       actual rows=30000 loops=3
~~~

Estimate how many rows flowed through the parallel node. Should you multiply `30000 × (Workers Planned + 1)`?

### Exercise 19 — ANALYZE After Bulk Load

Write SQL to inspect `n_mod_since_analyze`, `last_analyze`, and `last_autoanalyze` for `orders`, then run ANALYZE. Are those numbers exact `COUNT(*)` counts?

### Exercise 20 — pg_stats

Write SQL to view `most_common_vals`, `most_common_freqs`, and `n_distinct` for `orders.customer_id`. What does a negative `n_distinct` mean?

### Exercise 21 — Raising Statistics Target

Write SQL to raise the statistics target of `customer_id` to 500 and refresh statistics. Why shouldn't you apply that setting uniformly to every column?

### Exercise 22 — Extended Statistics

Write SQL to create `CREATE STATISTICS` with `mcv` and `dependencies` on `orders(status, customer_id)`. What is its limitation for cross-table joins?

### Exercise 23 — Skew and Selectivity

In the lab, `status='paid'` is ~85% while `'canceled'` is ~5%. Why does an index solely on `status` behave differently for these two predicates?

### Exercise 24 — Generic/Custom Plans

Write a `PREPARE` statement filtering `status = $1` and run `EXPLAIN EXECUTE` for `'paid'` and `'canceled'`. Why can't you look at a single execution and conclude one optimal plan covers every parameter?

### Exercise 25 — Expression vs. Range

Rewrite the predicate:

~~~sql
WHERE created_at::text LIKE '2026-03%'
~~~

as a range predicate on the DATE column matching March 2026 orders.

### Exercise 26 — Partial Index

Write a partial index supporting queries for a customer's canceled orders. Why might a generic prepared plan with `status=$1` skip using this index?

### Exercise 27 — Composite Index and ORDER BY

Write a candidate index for:

~~~sql
SELECT order_id, created_at
FROM plan_lab.orders
WHERE customer_id = 50
ORDER BY created_at DESC
LIMIT 20;
~~~

Explain the role of the first and second columns in the index.

### Exercise 28 — OFFSET

Why might `LIMIT 20 OFFSET 100000` process over 100,000 positions? Propose a keyset pagination approach using the unique `order_id` key.

### Exercise 29 — Outer Join Semantics

Compare:

~~~sql
LEFT JOIN plan_lab.orders o
  ON o.customer_id = c.customer_id
WHERE o.status = 'paid'
~~~

and:

~~~sql
LEFT JOIN plan_lab.orders o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
~~~

Do both queries return the same set of customers when a customer has no paid orders?

### Exercise 30 — EXPLAIN ANALYZE DML

An engineer intends to run `EXPLAIN (ANALYZE) DELETE FROM plan_lab.orders ...` in production “just to view the plan.” What is flawed about that reasoning, and what is the safer alternative?

### Exercise 31 — JSON Plan

Write an `EXPLAIN` command with `FORMAT JSON, ANALYZE, BUFFERS` for counting orders. Why is JSON preferable to parsing text output in automated tooling?

### Exercise 32 — pg_stat_statements

Assuming the extension is ready, write a query returning the top 10 normalized statements by `total_exec_time`. Explain why a query with low mean latency can still be a top optimization priority.

### Exercise 33 — Partition Pruning

A query filtering March on a monthly partitioned table ends up visiting 24 partitions in its plan. How should you inspect predicates, the partition key, and statistics?

### Exercise 34 — Slow Query Despite Accurate Estimates

All scan estimates are close to actuals, yet the plan shows a 2 GB external Sort, 64 Hash Batches, and heavy temp I/O. Is cardinality misestimation necessarily the cause? Propose an investigation plan.

### Exercise 35 — Analyzing a Query with Three Issues

Suppose a plan reports:

~~~text
Limit actual rows=20 loops=1
  -> Sort actual rows=100000 loops=1
       Sort Method: external merge Disk: 80000kB
       -> Nested Loop actual rows=100000 loops=1
            -> Seq Scan on customers
                 estimated rows=100 actual rows=10000 loops=1
            -> Index Scan on orders
                 estimated rows=1 actual rows=10 loops=10000
~~~

Determine:
1. Misestimate factor on `customers`.
2. Per-loop misestimate factor on the inner node.
3. Approximate total rows emitted by the inner node.
4. Symptoms likely causing slowness.
5. Why simply raising `work_mem` immediately is insufficient.

### Exercise 36 — Capstone: Writing an Investigation Plan

An API query is slow in production only for certain high-volume customers. Propose a safe investigation plan from collecting SQL/parameters to testing index/stats fixes and rolling out changes, explaining how to distinguish estimation error from I/O bottlenecks or concurrent load.

---

## 39. Solution Hints

### Exercise 1 — Cost Is Not Milliseconds

- `0.42` is estimated **startup cost** in relative planner cost units.
- `350.00` is estimated **total cost** to emit all output under the cost model.
- `rows=100` is the planner's predicted output row count.
- `actual rows=120` is the measured output row count for that run (since `loops=1`).
- `actual time=0.040..2.800` is measured milliseconds to the first row and to completion.

There is no direct conversion from 350 cost units to 350 ms; concluding that is incorrect.

### Exercise 2 — Startup Cost

When a query only needs one row, the planner can favor a plan that **returns the first row early**, even if scanning the entire table would cost more overall. If plan A can fetch a row immediately via an index while plan B must sort everything before emitting row one, A can win for `LIMIT 1`.

This still depends on filter selectivity and early-stop capability, not a blanket rule that “LIMIT always uses an index.”

### Exercise 3 — Loops

`actual rows=3 loops=10000` gives an approximate total output of:

\[
3 \times 10000 = 30000 \text{ rows}
\]

`actual time=0.030 ms` per loop gives a rough estimate of:

\[
0.030 \times 10000 = 300\text{ ms}
\]

Do not treat 300 ms as **exclusive CPU time** because node timing is inclusive, display values are rounded, and instrumentation adds overhead. Use the query's overall Execution Time as the baseline.

### Exercise 4 — Misestimate Factor

| Estimated | Actual | Factor | Direction |
|---:|---:|---:|---|
| 50 | 5,000 | 100× | Planner underestimate |
| 30,000 | 100 | 300× | Planner overestimate |
| 2,000 | 2,400 | 1.2× | Slight planner underestimate |
| 1 | 0 | No finite ratio | Zero actual output |

When actual=0, check whether the node actually ran, whether filters/parameters matched data, and whether LIMIT or partition pruning stopped execution early. Do not treat an infinite ratio as the “biggest bug.”

### Exercise 5 — Join Estimate

Both scans are close:

- Orders: 100,000 predicted vs. 105,000 actual (~1.05×).
- Customers: 2,000 predicted vs. 2,000 actual (1×).

Join: 10,000 predicted vs. 500,000 actual (**50×** error). Suspect **join selectivity, join keys, duplicate keys, or fan-out** first. Inspect `Hash Cond`, `Join Filter`, and key distribution rather than simply raising statistics targets on an already-accurate scan.

### Exercise 6 — Inclusive Time

No. Aggregate's `actual time` includes pulling input from Hash Join. If Aggregate finishes around ~1000 ms and Hash Join around ~990 ms, the aggregation itself **certainly did not take 1000 ms**. Nor should you naively subtract 1000 − 990 to get exact exclusive CPU time across arbitrary plans; instrumentation, pipelining, and timing semantics must be considered.

### Exercise 7 — Rows Removed by Filter

In a single loop, approximately:

\[
100+119900=120000
\]

candidates were examined. If `WHERE` keeps 100 rows out of 120,000, an index may help; however, check predicate indexability, selectivity, and query purpose. If scanning the full table is required to compute a global sum anyway, an index may not improve it.

### Exercise 8 — Index Cond vs. Filter

- `Index Cond: customer_id=50` drives candidate lookup through the index.
- `Filter: status='canceled'` is evaluated afterward and discarded 5,000 rows in the example.

Candidates:

~~~sql
CREATE INDEX ix_plan_orders_customer_status
ON plan_lab.orders(customer_id, status);
~~~

Or if `canceled` is rare and the workload specifically targets it:

~~~sql
CREATE INDEX ix_plan_orders_customer_canceled
ON plan_lab.orders(customer_id)
WHERE status='canceled';
~~~

Choose only after measuring plans, write overhead, query distribution, and prepared generic-plan behavior.

### Exercise 9 — Shared Hit

`shared hit=120000` still means 120,000 buffer accesses occurred in the measured nodes. CPU work, repeated index lookups, and lock/memory overhead can still be substantial. Cache hits in PostgreSQL shared buffers alone do not prove the query is fast.

### Exercise 10 — Shared Read

`shared read=5000` indicates PostgreSQL loaded 5,000 blocks into shared buffers; the OS page cache may have satisfied them without physical SSD reads. Check `I/O Timings` (if `track_io_timing` is enabled), storage metrics, node timings, and cache state.

### Exercise 11 — Summing Buffers

No. Parent node buffer counts typically **already include child nodes**. Given parent=1500 and children=800+700, you cannot add them to 3000 as independent groups. Use the tree structure to locate which branch generates the buffer accesses.

### Exercise 12 — External Sort

Sort used **external merge** and temp I/O, indicating the sort input exceeded available operator memory under current configuration.

Investigation directions:

1. Can you filter earlier or select fewer columns before Sort while preserving semantics?
2. Would an index support `WHERE` + `ORDER BY`, especially with LIMIT?
3. Can `work_mem` be increased **locally and within limits** to avoid spilling for this workload?
4. Check whether estimated vs. actual rows or width are inaccurate.
5. Inspect BUFFERS, temp I/O, I/O Timing, and concurrency.

Do not raise `work_mem` globally just because you see `Disk`.

### Exercise 13 — Top-N Heapsort

With `LIMIT 10`, top-N heapsort retains only a tiny candidate set in memory instead of materializing and sorting every row. Yet to find the top 10 values without a matching ordered index, it still has to **inspect many or all source rows**.

### Exercise 14 — Hash Batches

`Batches=16` indicates Hash Join partitioned the hash table into multiple batches, typically because the build side exceeded single-batch memory limits under current settings.

Inspect:

- Actual build-side rows/width vs. estimates.
- `work_mem` and `hash_mem_multiplier`.
- Temp read/write and I/O Timings.
- Join key distribution and skew.
- Filters capable of shrinking the build side before joining.
- Concurrency and total available RAM.

### Exercise 15 — work_mem

`work_mem` governs memory **per sort/hash operation**, not a single session cap. Three sorts plus two hashes × 20 concurrent queries create many simultaneous memory-consuming nodes. An illustrative multiplication of 5 × 20 × 512 MB ≈ **50 GiB** highlights the risk, even though actual allocation depends on the algorithm and not every node uses the maximum simultaneously. Raising it server-wide risks swapping or OOM; test locally and measure.

### Exercise 16 — COUNT(*) Single-Row Output

Aggregate emits only one row containing the total count, yet the child Seq Scan still processed 120,000 rows. Analyze **work inside the subtree**, not only the root node's output row count.

### Exercise 17 — Nested Loop

Approximate output:

\[
20000 \times 2=40000\text{ rows}
\]

An inner index scan called 20,000 times × 0.025 ms ≈ **500 ms** rough cumulative time. Repeated index probes incur heavy CPU and buffer-access overhead; read the entire plan, heap fetches, and Execution Time before deciding on a fix.

### Exercise 18 — Parallel Execution

`actual rows=30000 loops=3` totals roughly **90,000 rows** through that node. Do not take `Workers Planned=3` and multiply by 4 (120,000), because `Workers Launched=2` at runtime and leader participation varies. Inspect per-worker stats and the full plan.

### Exercise 19 — Last ANALYZE

~~~sql
SELECT
    relname,
    n_mod_since_analyze,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname='plan_lab'
  AND relname='orders';

ANALYZE plan_lab.orders;
~~~

Counters like `n_mod_since_analyze` are statistical estimates, not substitutes for COUNT(*). `last_analyze`/`last_autoanalyze` may be NULL if that type of analyze has never run.

### Exercise 20 — pg_stats

~~~sql
SELECT
    n_distinct,
    most_common_vals,
    most_common_freqs
FROM pg_stats
WHERE schemaname='plan_lab'
  AND tablename='orders'
  AND attname='customer_id';
~~~

A negative `n_distinct` expresses distinct values as a proportion of total rows, not a literal “negative distinct count.”

### Exercise 21 — Statistics Target

~~~sql
ALTER TABLE plan_lab.orders
  ALTER COLUMN customer_id SET STATISTICS 500;

ANALYZE plan_lab.orders;
~~~

Higher granularity helps with certain distributions but increases ANALYZE work and catalog size without solving cross-column correlation or join misestimates. Raise targets selectively where evidence warrants it.

### Exercise 22 — Extended Statistics

~~~sql
CREATE STATISTICS st_plan_orders_status_cust
    (mcv, dependencies)
ON status, customer_id
FROM plan_lab.orders;

ANALYZE plan_lab.orders;
~~~

Extended statistics improve certain multi-column estimates **within the same table**, without teaching PostgreSQL dependencies **across two different tables** for join selectivity. Always measure whether it actually helps.

### Exercise 23 — Skewed Status

`paid` accounts for most of the table, so an index scan would touch many heap pages, making Seq Scan cheaper. `canceled` is much rarer, so an index scan or partial index can pay off. Actual plan choice depends on existing indexes, selectivity, row width, cache, and cost constants.

### Exercise 24 — Prepared Statements

~~~sql
PREPARE orders_by_status(text) AS
SELECT order_id, customer_id
FROM plan_lab.orders
WHERE status=$1;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_status('paid');

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_status('canceled');

DEALLOCATE orders_by_status;
~~~

Because parameter values differ widely in selectivity and PostgreSQL switches between custom and generic plans, a single measurement is insufficient. Inspect plan variants, parameter frequency distribution, and real latencies.

### Exercise 25 — Range Predicate on DATE

~~~sql
WHERE created_at >= DATE '2026-03-01'
  AND created_at < DATE '2026-04-01'
~~~

This matches March 2026 on a DATE column and is B-tree range-friendly. With TIMESTAMPTZ, adjust bounds to the business timezone before making an equivalent transformation.

### Exercise 26 — Partial Index

~~~sql
CREATE INDEX ix_plan_orders_canceled_customer
ON plan_lab.orders(customer_id)
WHERE status = 'canceled';
~~~

The planner uses a partial index only when it can prove the query predicate implies the index predicate. A generic plan with `status=$1` cannot assume every `$1` value equals `'canceled'`, so it may skip the index.

### Exercise 27 — Composite Index

~~~sql
CREATE INDEX ix_plan_orders_customer_created
ON plan_lab.orders(customer_id, created_at DESC);
~~~

Equality `customer_id=50` leverages the leading column; `created_at DESC` ordering helps fetch the latest rows for that customer. Check heap fetches for remaining output columns and inspect the real plan.

### Exercise 28 — OFFSET

`OFFSET 100000` still has to walk past 100,000 positions before emitting 20 rows, even with an ordered index. With `order_id` as a unique ascending key, keyset pagination looks like:

~~~sql
SELECT order_id, customer_id, amount
FROM plan_lab.orders
WHERE order_id > 100000
ORDER BY order_id
LIMIT 20;
~~~

The idea is to pass the previous page's **last_seen_order_id**, not necessarily a hardcoded literal 100000; if sorting DESC, use `order_id < last_seen_order_id` with `ORDER BY order_id DESC`. The API should define pagination semantics when rows change between pages.

### Exercise 29 — LEFT JOIN Semantics

They are not identical:

- `WHERE o.status='paid'` filters out unmatched rows where `o.status IS NULL`, removing customers without paid orders from the result.
- `ON ... AND o.status='paid'` keeps every left-side row; customers without paid orders retain `o.*` as NULL.

Never rewrite between the two purely for speed without confirming business requirements.

### Exercise 30 — DML and EXPLAIN ANALYZE

`EXPLAIN ANALYZE DELETE` **executes the DELETE**. Never run it casually in production. If you only want estimates, run:

~~~sql
EXPLAIN
DELETE FROM plan_lab.orders
WHERE status='canceled';
~~~

If you genuinely must measure DML execution, use a lab/staging database; or when authorized, wrap in a controlled transaction:

~~~sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM plan_lab.orders
WHERE status='canceled';
ROLLBACK;
~~~

Even when database changes roll back, external side effects and mechanisms like sequence allocations may not revert. Do not treat this snippet as safe for casual production use.

### Exercise 31 — FORMAT JSON

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT COUNT(*)
FROM plan_lab.orders;
~~~

JSON provides structured objects and arrays for programs inspecting plan trees, rows/loops, and temp metrics, avoiding brittle whitespace/indentation regexes on text plans. Note that certain fields appear or vanish depending on PostgreSQL version and node type.

### Exercise 32 — pg_stat_statements

When the extension is configured:

~~~sql
SELECT
    queryid,
    calls,
    total_exec_time,
    mean_exec_time,
    LEFT(query, 160) AS query_sample
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
~~~

A query averaging 2 ms executed 100,000 times consumes 200,000 ms in aggregate, potentially outweighing a 1,000 ms query called 10 times. Prioritize optimization for both latency and total load.

### Exercise 33 — Partition Pruning

Check:

1. Is the partition key actually `created_at` or another expression?
2. Does the query use a range/cast that allows the optimizer to infer the month?
3. Does a function in `WHERE` hinder pruning?
4. Are partition bounds/constraints defined properly?
5. Is execution-time pruning occurring (`Subplans Removed` / `never executed`)?
6. Do parent/child stats represent each partition's data accurately?

Re-run EXPLAIN after tuning predicates/stats if appropriate rather than blindly indexing all 24 partitions first.

### Exercise 34 — Accurate Estimates Yet Still Slow

Cardinality errors are **not required** for slowness. A 2 GB external sort, 64 hash batches, and heavy temp I/O point to other questions:

- Are input rows/widths inherently large despite accurate estimates?
- Is `SELECT *` or genuine join fan-out making tuples huge?
- Can rows or columns be pruned before Sort/Hash without changing semantics?
- Can an index eliminate sorting for ORDER BY / LIMIT?
- Is memory insufficient for the active workload?
- Can `work_mem` / `hash_mem_multiplier` be adjusted locally within the concurrency budget?
- Is temp storage I/O itself bottlenecked?

Use `BUFFERS`, `I/O Timings`, `Sort Method/Disk`, `Hash Batches`, and before/after measurements.

### Exercise 35 — Three Compounding Problems

1. Customers: estimated 100, actual 10,000 → **100× underestimate**.
2. Inner orders: estimated 1, actual 10 per loop → **10× underestimate**.
3. Total inner output is roughly 10 × 10,000 = **100,000 rows**.
4. Symptoms:
   - Outer cardinality error triggers 10,000 inner lookups.
   - Inner fan-out underestimated by 10×.
   - Sort receives 100,000 rows and spills 80,000 kB to disk.
   - Even with root `Limit 20`, Sort may process all 100,000 input rows before returning the top 20.
5. Raising `work_mem` alone might remove the sort spill while leaving **10,000 lookups, broken cardinality estimates, and a poor join plan intact**. Investigate stats, filters, join keys, and ORDER BY index opportunities first; tune memory afterward with a clear hypothesis and budget.

### Exercise 36 — An Actionable Investigation Plan

1. Record the **SQL fingerprint**, parameters for “hot” vs. typical customers, call rates, and p95/p99 latency (respecting sensitive-data policies).
2. Gather PostgreSQL version, schema/indexes, row counts, `pg_stats`, `last_analyze`, and relevant configuration.
3. Capture `EXPLAIN (ANALYZE, BUFFERS)` in staging, a representative replica, or controlled production with a safe SELECT.
4. At the root, note Planning Time, Execution Time, and output rows.
5. Walk down branches: locate the first divergent estimate; compute `actual rows × loops` on inner scans; check fan-out.
6. Read `BUFFERS`, temp I/O, `I/O Timings`, Hash Batches, Sort Method, and parallel workers to see if I/O or CPU dominates instead of statistics.
7. If slowness affects specific customers, inspect MCV/skew, prepared custom/generic plans, and matching index filters rather than testing only an average customer.
8. Pick **one** change: ANALYZE/target, index, expression rewrite, or query restructuring. Re-measure under identical parameters, data, and load.
9. Check write throughput, index footprint, and regression impact on other queries—not just one SELECT's speed.
10. Roll out via safe migration, monitor latency and concurrency, and keep a rollback path ready.

---

## 40. Summary

**Misestimating row counts is a major reason PostgreSQL chooses expensive plans, yet not every slow query stems from cardinality error.** Reliable tuning pairs planner estimates with actual executor evidence.

Key takeaways:

- `cost` uses **relative planner units**, not milliseconds.
- `rows` is the node's estimated output row count; `actual rows` is the measured per-loop average and **must be read alongside `loops`**.
- Node `actual time` is **inclusive** of child work; never sum node times across the tree. `Execution Time` measures total statement execution under EXPLAIN ANALYZE.
- Trace estimation errors back **to the node where divergence begins**, not only at the root.
- Nested Loop can become expensive via tens of thousands of inner calls; Hash Join via batches/temp I/O; Sort via disk spills; and Aggregate can emit one row after scanning millions of input rows.
- `BUFFERS` reveals memory vs. storage accesses; `shared read` does not automatically equal physical disk I/O, and parent buffer counts include child activity.
- `Rows Removed by Filter`, `Index Cond`, `Filter`, `Heap Fetches`, `Recheck Cond`, and parallel counters show where excess work occurs.
- `pg_stats`, `ANALYZE`, and extended statistics can improve estimates, though they do not solve every correlation, join selectivity, or generic-plan issue.
- Suitable B-tree, partial, or composite indexes, query rewrites, pre-aggregation, keyset pagination, and memory tuning all have trade-offs—choose based on measurement rather than generic rules of thumb.
- `EXPLAIN ANALYZE` **executes the statement**; protect live data and respect DML side effects.
- Always measure **before and after** on representative workloads, checking latency, buffers, write overhead, disk usage, concurrency, and rollback safety.

Problem-solving loop: **capture exact SQL and parameters → run controlled EXPLAIN (ANALYZE, BUFFERS) → compare estimated vs. actual rows and loops → locate branches burning CPU/I/O/memory → form a hypothesis on stats, query, or indexes → apply one change → re-measure performance and operational impact**.
