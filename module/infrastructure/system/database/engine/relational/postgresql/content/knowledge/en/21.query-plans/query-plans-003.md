# Actual Rows, Loops, and Interpreting Timing in PostgreSQL Query Plans

When tuning PostgreSQL, it is easy to see a line in `EXPLAIN ANALYZE` like:

~~~text
Index Scan using idx_orders_customer on orders o
  (cost=0.29..5.10 rows=4 width=32)
  (actual time=0.010..0.035 rows=3 loops=500)
~~~

And conclude: "Index Scan only fetched three rows and took 0.035 ms." That conclusion is **incomplete**, because that node was invoked **500 times**. In standard text output, a node's `actual rows` and `actual time` are reported **as averages per execution (loop)**.

In this hypothetical example:

- `actual rows=3` indicates an average of about **3 rows per loop**.
- `loops=500` indicates the node executed **500 times**.
- Total rows emitted by the node across all iterations is roughly **3 × 500 = 1,500 rows**.
- `actual time=0.010..0.035` indicates the time from iteration start to first row, and to iteration completion, **averaged per loop**, in milliseconds.
- Total time accounted for across this node's iterations can be estimated as **0.035 × 500 ≈ 17.5 ms** under a sequential model; that is **not** necessarily the wall-clock time of the entire query from start to finish.

If the node sits inside a `Nested Loop`, a high loop count can turn a very fast index lookup into a major share of the workload. Conversely, when multiple workers run in parallel, adding worker times together **does not equal** the query's wall-clock latency.

This lesson guides you to read accurately:

1. `cost=... rows=... width=...`: the planner's **estimates**.
2. `actual time=startup..total`: **measured** timing per node iteration.
3. `actual rows`: rows actually emitted by the node **on average per iteration**.
4. `loops`: number of times the node ran.
5. `Planning Time` and `Execution Time`: overall timings distinct from per-node fields.
6. Connections to `Nested Loop`, `Hash Join`, `Sort`, `Aggregate`, `LIMIT`, `Materialize`, `Memoize`, parallel queries, and `BUFFERS`.

The plan snippets use illustrative numbers; **they are not live run logs from your environment**. `EXPLAIN ANALYZE` output depends on PostgreSQL version, data, caching, statistics, hardware, and concurrent load.

## 1. Why Must You Read Execution Metrics?

PostgreSQL must decide how to execute a SQL statement before actually knowing the result:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

The planner might estimate a customer has 10 orders, pick `Index Scan`, and only at runtime discover that customer actually has 2,000 orders.

That is the gap between:

- **Estimated values**: predicted by the planner from statistics, constraints, and the cost model.
- **Actual values**: measured by the executor when the query actually runs.

Regular `EXPLAIN` only shows estimates; `EXPLAIN ANALYZE` executes the statement and adds measured metrics. That gap is often what reveals why PostgreSQL chose an unsuitable plan or why a node was invoked too many times.

### 1.1. EXPLAIN and EXPLAIN ANALYZE

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

Displays the **estimated** plan without executing the `SELECT` to measure time/rows.

~~~sql
EXPLAIN ANALYZE
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

Executes the query and collects measurements. Options can be written explicitly:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE customer_id = 42;
~~~

### 1.2. Warning for Data-Modifying Statements

`EXPLAIN ANALYZE` **executes** `INSERT`/`UPDATE`/`DELETE`/`MERGE` and other supported statements; it does not merely simulate them.

To analyze DML in a lab environment and roll back transactional changes:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE perf_lab.orders
SET amount = amount + 1
WHERE order_id = 1;

ROLLBACK;
~~~

Note that rollback does not necessarily undo **all external side effects or sequences**, and triggers/functions can cause other effects. Do not run `EXPLAIN ANALYZE` on production write commands without understanding the consequences.

## 2. Anatomy of an EXPLAIN ANALYZE Node

An illustrative excerpt:

~~~text
Index Scan using idx_orders_customer_id on orders o
  (cost=0.29..8.31 rows=15 width=48)
  (actual time=0.016..0.051 rows=12 loops=1)
  Index Cond: (customer_id = 42)
  Buffers: shared hit=5
Planning Time: 0.219 ms
Execution Time: 0.114 ms
~~~

| Field | Example value | Meaning |
| --- | --- | --- |
| `cost` | `0.29..8.31` | **Estimated** startup and total cost, in planner cost units |
| `rows` in `cost` | `15` | Number of rows the planner **estimates the node returns**, per execution |
| `width` | `48` | Estimated average row size, in bytes |
| `actual time` | `0.016..0.051` | Measured startup/total time, **ms averaged per loop** |
| `actual rows` | `12` | Actual rows returned by the node, averaged per loop |
| `loops` | `1` | Node executed once |
| `Index Cond` | `customer_id = 42` | Condition used by the index scan |
| `Buffers` | `shared hit=5` | Block accesses served from shared buffers (details later) |
| `Planning Time` | `0.219 ms` | Reported planning duration |
| `Execution Time` | `0.114 ms` | Total statement execution time as measured by PostgreSQL |

**Both `rows` fields appear, yet do not mean the same thing.** `rows=15` next to `cost` is a prediction; `rows=12` next to `actual time` is a measured value.

### 2.1. "Rows Returned by a Node" Differs from "Rows Scanned by a Node"

Suppose:

~~~text
Seq Scan on orders
  (actual time=0.100..4.100 rows=100 loops=1)
  Filter: (status = 'paid')
  Rows Removed by Filter: 4900
~~~

The node may **inspect 5,000 rows** yet only **return 100 rows up to its parent node**. Therefore `actual rows=100` does not mean the node only read 100 rows.

Fields like `Rows Removed by Filter`, `Index Cond`, `Heap Fetches`, and `BUFFERS` help separate internal work from output row count.

### 2.2. Values Differ Even for the Same Plan

Execution metrics vary depending on:

- Rows in the table, statistics, and data distribution.
- Whether pages are cached or read from storage.
- Concurrent transactions and lock waits.
- JIT/parallel execution choices.
- PostgreSQL version, planner parameters, CPU load, and timing overhead.

Do not treat a figure like `actual time=0.051` as a fixed constant of the `Index Scan` operator.

## 3. Reading actual rows Correctly

**`actual rows` is the average number of rows returned by the node per execution.**

Example:

~~~text
Index Scan ...
  (actual time=0.01..0.05 rows=4 loops=1)
~~~

The node returned about 4 rows in a single run.

~~~text
Index Scan ...
  (actual time=0.01..0.05 rows=4 loops=200)
~~~

The node returned an average of about 4 rows across **200 runs**.

Approximate total rows:

\[
\text{total output rows from node}
\;\approx\;
\text{actual rows per loop}
\times
\text{loops}
\]

For the second example:

\[
4\times200=800\text{ rows}
\]

### 3.1. Why "Approximate"?

Text output from `EXPLAIN ANALYZE` typically displays an integer for `rows` and rounds the average when multiple loops occur.

Suppose three iterations return:

~~~text
Loop 1 -> 0 rows
Loop 2 -> 1 row
Loop 3 -> 2 rows

Total: 3 rows
Average: 1 row/loop
~~~

`rows=1 loops=3` represents the average accurately.

However, if:

~~~text
Loop 1 -> 0 rows
Loop 2 -> 0 rows
Loop 3 -> 1 row

Total: 1 row
Average: 0.333 rows/loop
~~~

text output may print `rows=0 loops=3` after rounding. Concluding "no rows were ever returned" would be wrong.

Therefore, **do not claim the multiplication above gives an exact count** when per-loop figures have been rounded.

### 3.2. Actual Rows on Parent and Child Nodes

~~~text
Aggregate  (actual ... rows=1 loops=1)
  -> Seq Scan  (actual ... rows=5000 loops=1)
~~~

`Aggregate` can consume 5,000 rows and return **one aggregated row**. A child returning 5,000 does not force the parent to return 5,000.

Nodes perform different transformations:

- `Filter` reduces rows.
- `Aggregate` combines rows.
- `Join` can multiply or reduce row counts.
- `Sort` usually preserves row counts while changing order.
- `LIMIT` returns a subset of output.
- `Unique`/`Distinct` can eliminate duplicates.

When analyzing row counts, follow **each node's input/output boundary**.

## 4. Reading loops Correctly

`loops` is the number of times a node was started/executed by the executor in the measured plan. High values commonly appear when a node sits on the **inner side of a Nested Loop**, inside a correlated `SubPlan`, or when plan structures are re-invoked.

### 4.1. A Node That Runs Only Once

~~~text
Seq Scan on customers
  (actual time=0.015..0.400 rows=2000 loops=1)
~~~

In this example, the node was scanned once and returned 2,000 rows.

### 4.2. A Node That Runs Many Times

~~~text
Index Scan on orders
  (actual time=0.005..0.020 rows=5 loops=2000)
~~~

The index scan repeated **2,000 times**, averaging 5 rows each; total output from the node is roughly **10,000 rows**.

### 4.3. loops Is Not the Number of SQL Calls from the Application

A SQL query sent by an application **only once** can contain a node with `loops=2000`. That is looping **inside the executor**, not 2,000 HTTP requests or 2,000 prepared statements from the client.

### 4.4. loops Does Not Necessarily Equal the Outer Node's Row Count

In a standard `Nested Loop`, the inner scan is typically re-invoked per outer row, so `loops` often matches outer rows closely. However, nodes like `Materialize`/`Memoize`, join conditions, short-circuiting, parallelism, caching, or plan shape make counting less straightforward.

Read the **actual plan tree** and see which node is re-invoked, instead of applying "every inner loop count equals outer rows" to all cases.

## 5. Reading actual time = startup..total Correctly

Example:

~~~text
Index Scan ...
  (actual time=0.012..0.080 rows=20 loops=1)
~~~

Both numbers are in **milliseconds (ms)**:

- **Startup time (0.012 ms):** time until the node produces its **first row** in an execution. Even for a node returning zero rows, work is needed to determine none exist.
- **Total time (0.080 ms):** time until the node's execution finishes / output has been processed.

When `loops > 1`, those numbers are **per-iteration averages**.

### 5.1. Low Startup, High Total

~~~text
Index Scan
  (actual time=0.010..20.000 rows=100000 loops=1)
~~~

The node yields its first row quite fast, then continues spending time returning subsequent rows. This is characteristic of nodes capable of **streaming** data.

### 5.2. Startup Near Total

~~~text
Sort
  (actual time=25.200..25.600 rows=100000 loops=1)
~~~

Sort must gather/sort a significant volume of data before emitting its first row, making startup high.

A `HashAggregate` or blocking `Aggregate` in certain forms can also show startup near total because it must process its input before returning results.

### 5.3. 0.000 Does Not Mean Literally Zero Time

For very fast operations, measurements rounded to three decimal places can appear as `0.000 ms`. That does not prove CPU/IO took zero effort.

### 5.4. Time Notation Is Not a Confidence Interval

`0.012..0.080` is **not** "duration varied between 0.012 and 0.080 ms." It represents the **startup and total milestones of the same node**, generally interpreted per loop.

## 6. Formula for Reading Total Time When Loops Are High

Illustrative example:

~~~text
Index Scan ...
  (actual time=0.005..0.030 rows=2 loops=600)
~~~

Approximate total output:

\[
2\times600=1200\text{ rows}
\]

Total time accumulated across iterations of this node, in sequential execution and based on per-loop figures:

\[
0{,}030\times600\approx18\text{ ms}
\]

Total startup time recorded across iterations:

\[
0{,}005\times600\approx3\text{ ms}
\]

### 6.1. This Is Not Execution Time

Even if one node accumulates about 18 ms, the full query still involves:

- Parent nodes and other nodes.
- Executor setup/teardown overhead.
- Work not captured completely by simple multiplication.
- Parallelism, scheduling, instrumentation, and JIT when enabled.

`Execution Time` reported at the bottom of the plan is statement execution time as measured by PostgreSQL; it does not equal the sum of `actual total time × loops` across every node.

### 6.2. Parallel Scenarios

When multiple workers cooperate, accumulated worker time can **exceed wall-clock elapsed time**, because workers consume CPU / wait on I/O **concurrently**. Do not use the formula above as an exact wall-clock stopwatch for parallel plans.

## 7. Node Time Includes Child Node Time

In a plan tree, a parent node's `actual time` is usually **inclusive**: completing the parent node requires pulling from / waiting on child nodes, so it includes child execution time.

Example:

~~~text
Aggregate
  (actual time=12.00..12.01 rows=1 loops=1)
  -> Seq Scan on orders
       (actual time=0.02..10.40 rows=50000 loops=1)
~~~

If you add `12.01 + 10.40 = 22.41 ms` and say "these two nodes spent 22.41 ms," you have **double-counted** most of the scan time already included in the aggregate.

### 7.1. Inclusive vs Exclusive

- **Inclusive time:** time to complete a node including necessary work in its child subtrees.
- **Exclusive/self time:** work belonging solely to the node after subtracting child impact, when such separation is meaningful.

Text-format `EXPLAIN ANALYZE` **does not by default display a reliable self-time column for every node**.

### 7.2. Do Not Subtract Times Mechanically

Sometimes subtracting child time from parent time gives a rough sense of non-child overhead in a simple sequential plan segment. However, subtraction easily breaks when:

- A child node is invoked many times.
- Parallel workers are active.
- Nodes are rescanned or materialized.
- Time overlaps, blocking, or instrumentation skew occur.
- Figures are rounded or special node management applies.

**Do not treat simple subtraction as an accurate profiler** without understanding the executor and plan shape.

## 8. Key Example: Nested Loop Multiplying Loops

Suppose a query fetches 500 customers and each customer's orders:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    o.amount
FROM perf_lab.customers AS c
JOIN perf_lab.orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id <= 500;
~~~

An illustrative plan:

~~~text
Nested Loop
  (cost=0.58..5500.00 rows=12500 width=20)
  (actual time=0.025..16.800 rows=12500 loops=1)
  -> Index Only Scan using customers_pkey on customers c
       (cost=0.28..25.00 rows=500 width=4)
       (actual time=0.008..0.410 rows=500 loops=1)
       Index Cond: (customer_id <= 500)
  -> Index Scan using idx_orders_customer on orders o
       (cost=0.29..9.20 rows=25 width=16)
       (actual time=0.004..0.024 rows=25 loops=500)
       Index Cond: (customer_id = c.customer_id)
~~~

**These are illustrative figures for learning to read, not guaranteed lab output.**

### 8.1. Outer Scan

`customers` is the **outer** branch:

~~~text
rows=500 loops=1
~~~

The executor fetches 500 customers as input to the join loop.

### 8.2. Inner Scan

`orders` is the **inner** branch:

~~~text
rows=25 loops=500
~~~

Each customer triggers an index scan for related orders. Thus:

\[
25 \text{ orders/customer}\times500 \text{ customers}
=12,500 \text{ rows}
\]

### 8.3. Inner Total Time

`actual time=0.004..0.024` on the inner node is a **per-loop average**. Total time across inner iterations is roughly:

\[
0{,}024\times500=12\text{ ms}
\]

Do not see `0.024 ms` and conclude scanning orders is "virtually free": it was called 500 times.

### 8.4. Parent Nested Loop

~~~text
Nested Loop ... (actual time=0.025..16.800 rows=12500 loops=1)
~~~

The parent node returns 12,500 total rows in one loop, with inclusive time near 16.8 ms in this example.

Do not add `16.8 + 12 + 0.41` as total query time: the parent already includes child work.

## 9. Nested Loop Is Not Automatically a Bad Plan

Many people see `loops=100000` and immediately assume the query is poorly tuned. Check further:

- Is each inner scan iteration cheap?
- Is the Index Cond selective and appropriate?
- What is the total number of rows read/emitted?
- Does the query have a small `LIMIT`?
- Would Hash Join/Merge Join actually be better?
- Is the data favorably cached?
- Were row counts severely misestimated?

### 9.1. A Good Nested Loop

Outer has 10 rows, inner uses an index to find 1 row per loop:

~~~text
outer rows=10 loops=1
inner rows=1 loops=10
~~~

This is usually quite reasonable when lookups are fast.

### 9.2. A Nested Loop Worth Investigating

Outer has 100,000 rows; inner repeatedly scans a large table without a selective index:

~~~text
outer rows=100000 loops=1
inner rows=5000 loops=100000
~~~

Even with some inner caching, repeated work can be huge. Inspect `Rows Removed by Filter`, `BUFFERS`, and total time.

### 9.3. Do Not Judge Join Methods by Name Alone

A `Hash Join` can also be very slow if the build/hash table is large, skewed, spills to disk, or suffers from bad estimates. Optimization requires measuring the **concrete plan**, not applying "Hash Join good, Nested Loop bad."

## 10. Row Estimates and Discrepancies Across Loops

Two row numbers on the same node:

~~~text
(cost=0.29..9.20 rows=4 width=16)
(actual time=0.005..0.060 rows=80 loops=500)
~~~

The planner predicted **4 rows per loop**, while actual averaged **80 rows per loop**.

Discrepancy factor:

\[
\frac{80}{4}=20
\]

Across 500 iterations:

- Estimated total inner rows: about `4 × 500 = 2,000`.
- Actual total inner rows: about `80 × 500 = 40,000`.

A **20x discrepancy on a node called 500 times** can make real cost far exceed planner expectations.

### 10.1. Estimate/Actual Ratio

When `estimated rows > 0` and `actual rows > 0`, you can compute:

\[
\text{actual-to-estimated ratio}
=
\frac{\text{actual rows per loop}}
{\text{estimated rows per loop}}
\]

A value of 1 is near-exact; 10 means actual is roughly 10x predicted. For nodes showing `rows=0` due to rounding or special minimum estimates, inspect context rather than dividing blindly.

### 10.2. Always Compare Matching Units

Wrong:

~~~text
estimated rows=4  (per loop)
actual rows=80 × loops=500 = 40000
-> concludes a 10,000x misestimate
~~~

You compared a **per-loop estimate** against an **actual total across loops**.

Correct:

~~~text
estimated rows per loop = 4
actual rows per loop = 80
-> roughly 20x misestimate
~~~

Or given the actual 500 loops:

~~~text
estimated total over 500 loops ≈ 4 × 500 = 2000
actual total ≈ 80 × 500 = 40000
-> roughly 20x misestimate
~~~

### 10.3. When Actual Loops Also Differs from Outer Estimate

Total work also diverges when **the inner loop count itself** differs from predictions. The planner might predict 10 outer customers when reality has 10,000. Inner cost then blows up by **two multiplying factors**:

1. Far more inner scans than predicted.
2. More rows per inner scan than predicted.

That is why you should usually find **the first node near the bottom of the plan tree with severe estimated/actual cardinality drift**.

## 11. Why Do Estimates Go Wrong?

Common causes:

| Cause | Symptom in plan | Remedy direction |
| --- | --- | --- |
| Stale statistics | estimated rows differs from actual on heavily changed table | `ANALYZE`, check autovacuum |
| Skewed data distribution | One value has unusually many rows | Check MCV/histograms, statistics target |
| Correlated columns | Multi-column filter assumes near-independence | Extended statistics when appropriate |
| Predicate uses expression | Planner lacks direct stats for expression | Expression statistics/index, appropriate stats |
| Join on uneven data | Join output heavily skewed | Evaluate join key distribution, uniqueness |
| Varying parameter values | One plan serves widely varying selectivities | Evaluate prepared statement generic/custom plans |
| LIMIT/early stop | Actual rows small because node stopped early | Understand partial-fetch behavior |
| Parallelism | Rows/time split across workers | Inspect Workers and loops |

### 11.1. ANALYZE

~~~sql
ANALYZE perf_lab.orders;
~~~

`ANALYZE` refreshes planner statistics; it **does not create indexes**, does not guarantee a specific plan, and cannot fix every statistical limitation.

### 11.2. Extended Statistics

When multiple columns are correlated:

~~~sql
CREATE STATISTICS st_orders_customer_status
    (dependencies, mcv)
ON customer_id, status
FROM perf_lab.orders;

ANALYZE perf_lab.orders;
~~~

Extended statistics can assist **certain multi-column estimates** in suitable scenarios. Do not assume they resolve all join misestimations; support depends on expressions, PostgreSQL version, and query shape.

### 11.3. Estimation Error Differs from Correctness

A plan with inaccurate estimated rows must still **return the correct SQL result** under query and isolation semantics, barring bugs/corruption. Bad estimates mainly push the planner toward inefficient execution strategies.

## 12. Reading actual time in Nested Loop

Consider:

~~~text
Nested Loop
  (actual time=0.020..150.000 rows=50000 loops=1)
  -> Seq Scan on customers
       (actual time=0.010..3.000 rows=2000 loops=1)
  -> Index Scan on orders
       (actual time=0.008..0.060 rows=25 loops=2000)
~~~

The inner scan has:

\[
0{,}060\text{ ms/loop}\times2000
=120\text{ ms}
\]

This is the approximate total across 2,000 inner calls in this sequential example. The parent node has `total=150 ms` and **includes** execution time of its child nodes.

### 12.1. Why Is Parent Time Greater Than a Child's Total?

The parent also:

- Pulls outer rows.
- Invokes the inner scan and coordinates iteration.
- Evaluates join conditions.
- Constructs result tuples.
- Calls other executor nodes as needed.

Do not attribute the entire difference to a single operation without measuring.

### 12.2. When Inner actual time Is Very Low Yet Loops Are Huge

Even `0.001 ms`/loop × `1,000,000 loops` is roughly **1,000 ms** of accumulated time. Tiny operations repeated millions of times add up substantially.

This is another reason to always read `loops` alongside `actual time`.

## 13. Startup Time and Blocking Nodes

Not every node produces its first row right away.

### 13.1. Streaming Scans

~~~text
Index Scan
  (actual time=0.010..8.000 rows=15000 loops=1)
~~~

The first row can arrive after roughly 0.010 ms; the node keeps streaming subsequent rows.

### 13.2. Sort Must Collect Input

~~~text
Sort
  (actual time=40.000..43.000 rows=15000 loops=1)
  Sort Key: amount DESC
  Sort Method: quicksort  Memory: 1200kB
  -> Seq Scan
       (actual time=0.020..13.000 rows=15000 loops=1)
~~~

`Sort` normally needs its input to establish order before emitting the first row. Sort's startup time is therefore high, and includes the time spent reading input.

### 13.3. Aggregate

~~~text
Aggregate
  (actual time=12.000..12.001 rows=1 loops=1)
  -> Seq Scan
       (actual time=0.010..9.000 rows=50000 loops=1)
~~~

A whole-table aggregate must read all input before knowing the final `SUM`, so startup sits right next to total.

Certain aggregate/grouping forms can stream output per group depending on the plan; do not apply "every Aggregate must read the entire dataset before its first row" to every variant.

### 13.4. LIMIT Often Stops Child Branches Early

~~~text
Limit
  (actual time=0.025..0.100 rows=10 loops=1)
  -> Index Scan
       (actual time=0.020..0.090 rows=10 loops=1)
~~~

If rows arrive already in index order, `LIMIT 10` may only request 10 rows.

If an unsuitable Sort sits before LIMIT, the executor may still need to read **very many rows** to determine the top 10 values.

## 14. LIMIT Does Not Mean the Table Only Had That Many Rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM perf_lab.orders
ORDER BY amount DESC
LIMIT 10;
~~~

An illustrative plan:

~~~text
Limit (actual time=12.500..12.510 rows=10 loops=1)
  -> Sort (actual time=12.495..12.500 rows=10 loops=1)
       Sort Key: amount DESC
       Sort Method: top-N heapsort  Memory: 26kB
       -> Seq Scan on orders
            (actual time=0.010..4.000 rows=50000 loops=1)
~~~

Do not see `Sort actual rows=10` and say "Sort only looked at 10 rows." Sort **received roughly 50,000 rows** from Seq Scan, processed enough to pick the top 10, and **emitted only 10 rows up to Limit** because the parent asked for no more.

### 14.1. rows Describes Output, Not Input

When a node sits under `LIMIT`, its `actual rows` can reflect rows **actually requested by the parent**, not the full row count it could have produced if drained completely.

### 14.2. Sort Method Adds Context

`quicksort`, `top-N heapsort`, `external merge`, and memory/disk figures (depending on the plan) clarify how the node sorted. A Sort spilling to disk is usually a key investigation point when timing is high.

## 15. Be Careful with "actual rows = 0"

Node:

~~~text
Index Scan ...
  (actual time=0.015..0.015 rows=0 loops=1)
~~~

ran, yet returned zero rows in that run.

However:

~~~text
Index Scan ...
  (actual time=0.002..0.002 rows=0 loops=1000)
~~~

does not necessarily mean **0 rows on every iteration**, because the per-loop average may have been rounded down from less than 0.5.

### 15.1. loops=0 / never executed

If a plan branch was never invoked because its condition did not trigger, PostgreSQL may show:

~~~text
(never executed)
~~~

or an equivalent representation depending on format/version. That differs from **running and finding no matching rows**.

### 15.2. Why Is a Node Never Executed?

Examples:

- Inner side of a `Nested Loop` when the outer input is empty.
- Short-circuited `CASE`, condition, or subplan where allowed.
- A plan branch stopped early by a parent `LIMIT`.
- A plan branch bypassed under special executor logic.

Do not assume "the index doesn't work" just because a node appears in the plan as `never executed`.

## 16. Rows Removed by Filter and Rows Removed by Join Filter

Besides `actual rows`, plans can report rows discarded by predicates.

~~~text
Seq Scan on orders
  (actual time=0.020..3.500 rows=3000 loops=1)
  Filter: (status = 'paid')
  Rows Removed by Filter: 47000
~~~

The node likely examined around 50,000 rows and passed 3,000 rows up to its parent.

### 16.1. Rows Removed by Filter Also Has Per-Loop Semantics

When a node executes multiple times, text-format `Rows Removed by Filter` is typically shown as an **average per loop**, subject to rounding. Read it with `loops` just like `actual rows`.

### 16.2. Join Filter vs Filter

In a `Nested Loop` or another join:

~~~text
Join Filter: (c.region = o.region)
Rows Removed by Join Filter: 5000
~~~

Rows may satisfy part of an access condition yet fail the join condition. They are discarded **before the node emits output**, so they do not appear in the join's `actual rows`.

### 16.3. Index Cond, Recheck Cond, Filter

| Field | Role |
| --- | --- |
| `Index Cond` | Condition used to access rows via the index |
| `Filter` | Additional condition checked after the node's access step |
| `Recheck Cond` | Condition that must be re-verified on rows in plans such as bitmaps |
| `Rows Removed by Filter` | Reported count of rows discarded at the filter step |
| `Rows Removed by Index Recheck` | Rows discarded when rechecking the index condition where applicable |

These fields explain why a node **reads many rows yet returns few**.

## 17. Actual Time and BUFFERS: Two Different Perspectives

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

The plan may report:

~~~text
Buffers: shared hit=35 read=12
~~~

`hit` means relevant buffer accesses were satisfied from shared buffers; `read` means blocks had to be brought into shared buffers at that point. A `read` is not necessarily a **slow physical disk hit**: the OS maintains a page cache, and PostgreSQL reports block/access counts via instrumentation.

### 17.1. Buffer Counts Are Not Row Counts

One block holds multiple tuples; one tuple can trigger distinct index and heap accesses. Thus do not read:

~~~text
shared hit=50
~~~

and claim the node read exactly 50 rows.

### 17.2. Buffers Are Also Inclusive

Buffer usage reported at a node generally reflects activity of the node and its subtrees. Do not sum every `Buffers` line from parent to child into a grand total, as that **double-counts**.

### 17.3. Common BUFFERS Metrics

| Metric | Hint |
| --- | --- |
| `shared hit` | Page already present in shared buffers |
| `shared read` | Page had to be read into shared buffers |
| `shared dirtied` | Shared buffer page marked dirty |
| `shared written` | Shared buffer page written out during observation |
| `temp read / written` | Temp file block accesses, often indicating spills |
| `local hit/read` | Local buffer accesses, e.g., temporary tables |

Do not assume a write query will show equal `dirtied` and `written` counts: dirty buffers may be flushed later.

### 17.4. BUFFERS and actual time Complement Each Other

Two queries both returning 100 rows:

- Query A: `shared hit=5`, `actual total=0.2 ms`.
- Query B: `shared read=5000`, `actual total=150 ms`.

Combining timing with buffer footprint helps spot queries doing far more logical I/O. Still, measure multiple times and inspect cache/system state before attributing a single cause.

## 18. I/O Timing and How It Is Measured

When configured appropriately (for example `track_io_timing` enabled), plans with `BUFFERS` can also report:

~~~text
I/O Timings: shared read=12.345
~~~

This is measured I/O duration within scope, **distinct from** overall node `actual time` and block counts. I/O timing statistics carry measurement overhead and depend on platform/configuration.

### 18.1. Missing I/O Timings Does Not Prove Zero I/O

If `track_io_timing` is off, `I/O Timings` will not appear even when `shared read` is non-zero. Do not conclude "zero disk reads" simply because no timing line appears.

### 18.2. High Shared Hits Yet Still Slow

A query can be CPU-bound due to:

- Expensive filters/expressions.
- Joins multiplying too many rows.
- Heavy sorts or aggregates.
- High loop counts.
- Internal contention.

**A high buffer hit rate does not guarantee fast execution.**

## 19. Planning Time and Execution Time

Plans usually end with:

~~~text
Planning Time: 0.310 ms
Execution Time: 18.720 ms
~~~

### 19.1. Planning Time

Planning duration reported by PostgreSQL, within the instrumentation scope of the version and options. It does not necessarily capture all client-side time or overhead before/after the query crosses the application boundary.

### 19.2. Execution Time

Statement execution time reported by PostgreSQL under `EXPLAIN ANALYZE` instrumentation. This is usually the most useful overall figure for comparing runs on the server **under equivalent measurement conditions**.

### 19.3. Does It Match What the Client Sees?

Not necessarily:

~~~text
Application
  -> network request
  -> PostgreSQL planning
  -> PostgreSQL execution
  -> network response
  -> data decoding / deserialization in driver
  -> UI rendering
~~~

Application latency can be higher due to network, queueing, connection setup, result transfer, parsing, and rendering. `EXPLAIN ANALYZE` also adds instrumentation overhead and does not transmit result rows like a normal query.

### 19.4. Never Measure Once and Conclude Permanently

Run multiple times under controlled conditions, observing medians/distributions, caching, and workload. A single run 2 ms faster does not prove an index change is superior.

## 20. Overhead of EXPLAIN ANALYZE

Timing every node requires PostgreSQL to sample clocks and count events. For queries with very many small iterations, timing instrumentation can introduce noticeable overhead.

### 20.1. TIMING OFF

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM perf_lab.orders
WHERE status = 'paid';
~~~

`TIMING OFF` disables **per-node timing measurement** to reduce overhead while still collecting useful metrics such as:

- `actual rows`.
- `loops`.
- Enabled count/BUFFERS metrics.
- Overall `Execution Time` when `ANALYZE` is enabled, as supported.

Do not expect per-node `actual time=...` when timing is disabled.

### 20.2. Comparing Both Measurement Modes

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING ON)
SELECT COUNT(*)
FROM perf_lab.orders;

EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM perf_lab.orders;
~~~

The two runs can differ in reported duration due to instrumentation/caching overhead. Use `TIMING OFF` when the main goal is checking **cardinality and loops**, especially in plans with many fast-looping nodes.

### 20.3. ANALYZE Is Not the Table Statistics ANALYZE Command

Do not confuse:

~~~sql
ANALYZE perf_lab.orders;
~~~

with:

~~~sql
EXPLAIN (ANALYZE)
SELECT ...;
~~~

The first collects statistics for the planner; the second option **executes the query and measures it**.

## 21. Parallel Plans: Read Rows, Loops, and Timing Carefully

PostgreSQL can execute some plans in parallel using a **leader** and **parallel workers**.

An illustrative plan:

~~~text
Finalize Aggregate
  (actual time=20.0..22.0 rows=1 loops=1)
  -> Gather
       (actual time=19.0..21.9 rows=3 loops=1)
       Workers Planned: 2
       Workers Launched: 2
       -> Partial Aggregate
            (actual time=17.5..17.6 rows=1 loops=3)
            -> Parallel Seq Scan on orders
                 (actual time=0.010..14.5 rows=16667 loops=3)
~~~

### 21.1. Partial Aggregate loops=3

Two workers and the leader can all execute part of the work, so `Partial Aggregate` in this example shows `loops=3`. This is the number of node executions counted in the combined output; it is not "the query ran 3 times from the app."

### 21.2. Parallel Seq Scan rows=16667 loops=3

Total rows scanned/emitted is **approximately** `16,667 × 3 ≈ 50,001`, reflecting 50,000 total rows with rounding.

However, workers may process **unequal numbers of rows**; the combined summary line shows only the average.

### 21.3. Parallel Time Cannot Be Multiplied into Latency

`actual total time=14.5 ms loops=3` does not mean the node took **43.5 ms wall-clock**. Much of the work runs concurrently; cumulative participant time can exceed wall-clock time.

### 21.4. Workers Planned vs Workers Launched

If:

~~~text
Workers Planned: 4
Workers Launched: 2
~~~

the planner expected four workers, yet only two actually launched. This can alter performance and work distribution; check parallel worker limits and system load.

### 21.5. Inspecting Worker Details

In eligible plans and options:

~~~sql
EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT SUM(amount)
FROM perf_lab.orders;
~~~

Output may show per-worker breakdowns under certain nodes. Display format depends on PostgreSQL version and execution choices. **Do not assume Workers output always appears** for small queries or every SQL statement.

## 22. Gather and Gather Merge

`Gather` collects results from workers and passes them up the plan. `Gather Merge` additionally preserves/merges result streams that **already have compatible ordering**.

~~~text
Gather
  -> Parallel Seq Scan
~~~

does not guarantee a final ordering:

~~~sql
ORDER BY created_at
~~~

If the query requires ordering, the planner must arrange the plan to guarantee `ORDER BY`, via `Sort`/`Gather Merge` or another mechanism.

### 22.1. Time on Gather

`Gather` time includes receiving/merging output per node mechanics, depending on worker scheduling, tuple queues, and whether upper nodes keep pulling rows.

If `Gather` looks slow, do not assume Gather's own CPU caused all the latency; its inclusive time can reflect waiting on workers.

### 22.2. Parallel Plans and I/O

Workers can concurrently put pressure on memory bandwidth and I/O. Total `Buffers` and per-worker figures must be read as cumulative logical activity, not mapped directly to unique physical blocks or serial milliseconds.

## 23. Materialize and Memoize: Avoiding Re-Scans or Parameter Caching

In a plan, PostgreSQL can use a `Materialize` node:

~~~text
Nested Loop
  -> outer input
  -> Materialize (actual ... rows=1000 loops=50)
       -> Seq Scan on small_table
            (actual ... rows=1000 loops=1)
~~~

### 23.1. Reading It Properly

`Materialize` can be invoked many times (`loops=50`), while its child `Seq Scan` only reads the source once and materializes the result for subsequent scans.

**Do not look at `Materialize loops=50` and multiply the Seq Scan cost by 50** when Seq Scan only has `loops=1`.

### 23.2. Materialization Has a Cost

Intermediate buffering consumes memory and sometimes temporary files. Check `Buffers`, memory/temp usage, and timing instead of assuming every Materialize is optimal.

### 23.3. Memoize

A parameterized inner scan plan can use `Memoize` to cache lookup results by parameter key:

~~~text
Memoize
  Cache Key: o.customer_id
  Cache Mode: logical
  Hits: 980
  Misses: 20
  Evictions: 0
  Overflows: 0
  Memory Usage: 16kB
  -> Index Scan ...
~~~

**Illustrative metrics.** Memoize may be called 1,000 times while its child Index Scan only executes for misses/cache refills as needed.

### 23.4. Do Not Equate Parent and Child Loops

In some plans:

~~~text
Memoize loops=1000
Index Scan child loops=20
~~~

There is no contradiction here. The cache satisfied **980 lookups** without invoking the child scan.

When analyzing total rows and timing, **multiply by that node's own loops**, rather than using the parent's loops for every child.

## 24. SubPlan and InitPlan

Queries with subqueries can produce `SubPlan` or `InitPlan`.

### 24.1. Correlated SubPlan

~~~sql
SELECT
    c.customer_id,
    (
        SELECT MAX(o.amount)
        FROM perf_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS max_amount
FROM perf_lab.customers AS c
WHERE c.customer_id <= 100;
~~~

Depending on how the planner transforms the query, the subquery may appear as a `SubPlan` executed repeatedly for outer rows.

~~~text
Seq Scan on customers c
  (actual ... rows=100 loops=1)
  SubPlan 1
    -> Aggregate (actual ... rows=1 loops=100)
         -> Index Scan (actual ... rows=25 loops=100)
~~~

When a plan like this appears, it is a cue to inspect **the subplan's loops** and cumulative execution time.

### 24.2. InitPlan

An uncorrelated subquery can be evaluated once as an `InitPlan` or optimized differently:

~~~sql
SELECT *
FROM perf_lab.orders
WHERE amount > (
    SELECT AVG(amount)
    FROM perf_lab.orders
);
~~~

Do not assume every subquery runs once per row. **The actual plan determines** whether a subplan loops.

### 24.3. Rewriting SQL Is Not Always Necessary

Sometimes the planner automatically transforms a subquery into an efficient join or aggregate. Refactor only when the plan and workload demonstrate a concrete issue, not by a blanket rule like "all correlated subqueries are slow."

## 25. Hash Join: Understanding Startup and Row Counts

An illustrative plan:

~~~text
Hash Join
  (actual time=6.00..25.00 rows=50000 loops=1)
  Hash Cond: (o.customer_id = c.customer_id)
  -> Seq Scan on orders o
       (actual time=0.02..7.00 rows=50000 loops=1)
  -> Hash
       (actual time=5.20..5.25 rows=2000 loops=1)
       Buckets: 4096  Batches: 1  Memory Usage: 200kB
       -> Seq Scan on customers c
            (actual time=0.02..2.50 rows=2000 loops=1)
~~~

`Hash` must build its structure from the build-side input. Hash Join's startup can include the time spent building the hash table before emitting join rows.

### 25.1. Batches and Spills

If the hash table exceeds available memory, PostgreSQL may process in multiple batches using temp files; `Batches` and `temp read/written` are key investigative clues.

### 25.2. Hash Join Rows Is Not Bucket Count

`rows=50000` on `Hash Join` is **output rows**, not hash entries, buckets, or probe attempts.

### 25.3. Do Not Add Hash and Hash Join Times

Hash Join's `actual time` includes hash construction work from its child. Summing all node times double-counts just as in other joins.

## 26. Sort and GroupAggregate: Row Counts Change by Level

A query:

~~~sql
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM perf_lab.orders
GROUP BY customer_id
ORDER BY total_amount DESC
LIMIT 10;
~~~

May produce a node chain:

~~~text
Limit (actual ... rows=10 loops=1)
  -> Sort (actual ... rows=10 loops=1)
       Sort Key: (sum(amount)) DESC
       Sort Method: top-N heapsort
       -> HashAggregate (actual ... rows=2000 loops=1)
            Group Key: customer_id
            -> Seq Scan on orders
                 (actual ... rows=50000 loops=1)
~~~

### 26.1. Each Row Count Answers One Question

- Scan: 50,000 order rows.
- Aggregate: 2,000 customer groups.
- Sort: with LIMIT above it, emits only the 10 requested rows up to parent, **which does not mean it only received 10 groups to sort**.
- Limit: returns the final 10 rows.

### 26.2. Why Read the Whole Tree?

Looking only at `Limit rows=10` hides the work of scanning 50,000 orders and grouping 2,000 customers. Execution time is driven by **work at every layer**.

## 27. Lab Scenario: Generating Data to Observe Loops

The commands below create a dedicated schema in a practice database. They do not touch production tables.

### 27.1. Create Two Tables

~~~sql
CREATE SCHEMA perf_lab;

CREATE TABLE perf_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    segment text NOT NULL
);

CREATE TABLE perf_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES perf_lab.customers(customer_id),
    amount numeric(12, 2) NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL
);
~~~

### 27.2. Generate 2,000 Customers

~~~sql
INSERT INTO perf_lab.customers (
    customer_id, full_name, segment
)
SELECT
    g,
    'Customer ' || g::text,
    CASE
        WHEN g % 5 = 0 THEN 'vip'
        ELSE 'regular'
    END
FROM generate_series(1, 2000) AS s(g);
~~~

### 27.3. Generate 50,000 Orders

~~~sql
INSERT INTO perf_lab.orders (
    order_id, customer_id, amount, status, created_at
)
SELECT
    g::bigint,
    ((g - 1) % 2000) + 1,
    (1000 + (g % 500) * 100)::numeric(12, 2),
    CASE
        WHEN g % 4 = 0 THEN 'cancelled'
        ELSE 'paid'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
      + (g * INTERVAL '1 minute')
FROM generate_series(1, 50000) AS s(g);
~~~

This distribution is intentional: **each customer has 25 orders**. `status` has 37,500 `paid` orders and 12,500 `cancelled` orders. Plan shapes may vary with cost settings and execution environment.

### 27.4. Create Suitable Indexes

~~~sql
CREATE INDEX idx_orders_customer
ON perf_lab.orders (customer_id);

CREATE INDEX idx_orders_customer_created
ON perf_lab.orders (
    customer_id,
    created_at DESC,
    order_id DESC
);

ANALYZE perf_lab.customers;
ANALYZE perf_lab.orders;
~~~

### 27.5. Verify Source Counts

~~~sql
SELECT COUNT(*) AS n_customers
FROM perf_lab.customers;

SELECT
    COUNT(*) AS n_orders,
    COUNT(DISTINCT customer_id) AS n_customers_with_orders
FROM perf_lab.orders;

SELECT
    MIN(n_orders) AS min_per_customer,
    MAX(n_orders) AS max_per_customer
FROM (
    SELECT customer_id, COUNT(*) AS n_orders
    FROM perf_lab.orders
    GROUP BY customer_id
) AS x;
~~~

Expected results are 2,000 customers, 50,000 orders, and exactly 25 orders per customer.

## 28. Lab 1: Comparing Estimate and Actual in Index Scan

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id, customer_id, amount
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

With the lab data, this query returns **25 orders** if data has not been altered. In the plan, locate the orders scan node:

~~~text
Index Scan / Bitmap Heap Scan / Seq Scan ...
  (cost=... rows=... width=...)
  (actual time=... rows=25 loops=1)
~~~

**The scan type is not hardcoded**: the planner is free to choose different strategies. When a single query fetches few rows, you may see Index Scan or Bitmap access depending on config/data.

### Questions

1. What is estimated rows?
2. What is actual rows?
3. What is loops?
4. Is there an `Index Cond`, or only a `Filter`?
5. What are `shared hit/read`?

Record the metrics **you actually measured**, without substituting illustrative numbers from the lesson.

## 29. Lab 2: Nested Loop and Total Inner Invocations

One way to observe an inner lookup per customer is `LATERAL` with `LIMIT`:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    recent.order_id,
    recent.amount
FROM perf_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT
        o.order_id,
        o.amount
    FROM perf_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent
WHERE c.customer_id <= 100
ORDER BY c.customer_id, recent.order_id DESC;
~~~

The query retrieves up to three newest orders for each of 100 customers. In the lab dataset, each customer has 25 orders, so the final result has **300 rows**.

The plan will likely show:

- Outer scan returning 100 customers.
- An inner `Limit` and `Index Scan`, invoked repeatedly per `customer_id`.
- Inner `rows≈3 loops≈100`.
- Join node returning roughly 300 rows.

### 29.1. If Nested Loop Does Not Appear as Expected

Planners and PostgreSQL versions can optimize differently. The goal is reading the **actual plan**, not forcing your machine's output to match an illustrative plan. Correlated `LATERAL` with per-customer top-N limits often highlights repeated lookups, though not every system yields the exact same plan.

### 29.2. Calculating Cumulative Row Count

If the inner node shows:

~~~text
(actual time=0.004..0.020 rows=3 loops=100)
~~~

cumulative inner output is roughly:

\[
3\times100=300
\]

Cumulative inner time is roughly:

\[
0{,}020\times100=2\text{ ms}
\]

These are **estimates from illustrative numbers**, not guaranteed lab measurements.

### 29.3. A 300-Row Result Does Not Mean Only 300 Table Rows Were Read

An index can quickly pinpoint the first three orders per customer. Without a suitable index, the executor might have to read far more rows to sort/find top-N per customer. Check child scans, `Sort Method`, and `BUFFERS`.

## 30. Lab 3: LIMIT, Sort, and Actual Rows Processed

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM perf_lab.orders
ORDER BY amount DESC, order_id
LIMIT 10;
~~~

Since the lab does not yet have an index on `(amount DESC, order_id)`, the planner may choose a scan followed by sort/top-N; inspect the actual plan.

Record these metrics:

| Node | Fields to record |
| --- | --- |
| Orders scan | Actual rows, loops, Buffers |
| Sort | Actual rows, Sort Method, Memory/Disk |
| Limit | Actual rows |
| Entire statement | Execution Time |

**Lesson:** `Limit rows=10` does not mean only 10 orders had to be inspected. When finding top-N on an unindexed sort order, the executor may need to examine all 50,000 orders.

### 30.1. Creating a Comparison Index

In the lab, you can add:

~~~sql
CREATE INDEX idx_orders_amount_desc
ON perf_lab.orders (amount DESC, order_id ASC);

ANALYZE perf_lab.orders;
~~~

Re-run `EXPLAIN (ANALYZE, BUFFERS)`. There is no guarantee the planner picks the index; compare whether `Sort` disappears, block counts, timing, and index write-maintenance cost.

## 31. Lab 4: Aggregate and Row Reduction

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, SUM(amount) AS total_amount
FROM perf_lab.orders
GROUP BY customer_id
ORDER BY total_amount DESC
LIMIT 10;
~~~

The query sums orders across 2,000 customers and takes the top 10 customers by total amount. Initial data has 50,000 orders, yet output is only 10 rows.

The plan may contain:

~~~text
Limit ... rows=10
  -> Sort ... rows=10
       -> HashAggregate ... rows=2000
            -> Seq Scan ... rows=50000
~~~

**Do not confuse "query returns 10 rows" with "executor only touched 10 rows."**

### 31.1. GroupAggregate vs HashAggregate

Depending on the plan, PostgreSQL may use `HashAggregate`, `GroupAggregate` over pre-sorted input, or parallel partial/final aggregates. Each node has distinct startup/total/rows. Compare **cardinality across every layer**.

## 32. Lab 5: TIMING ON and TIMING OFF

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING ON)
SELECT
    c.customer_id,
    (
        SELECT SUM(o.amount)
        FROM perf_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS total
FROM perf_lab.customers AS c
WHERE c.customer_id <= 100;
~~~

Compare with:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT
    c.customer_id,
    (
        SELECT SUM(o.amount)
        FROM perf_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS total
FROM perf_lab.customers AS c
WHERE c.customer_id <= 100;
~~~

Observe:

- Do `actual rows` and `loops` on the subplan still appear?
- Does per-node `actual time` still appear when timing is off?
- How does `Execution Time` vary across multiple runs?
- Could that difference be influenced by caching/instrumentation?

### 32.1. Do Not Use TIMING OFF to Prove a Query Is Faster

Turning off instrumentation does not optimize application SQL. It only **changes measurement behavior and timing collection overhead** during `EXPLAIN ANALYZE`.

## 33. Lab 6: Observing Parallel Seq Scan

On 50,000 rows, the planner may not consider a parallel scan worthwhile. You can increase lab dataset size or adjust settings **strictly inside a lab session** to explore:

~~~sql
BEGIN;

SET LOCAL max_parallel_workers_per_gather = 2;
SET LOCAL min_parallel_table_scan_size = '0';
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;

EXPLAIN (ANALYZE, VERBOSE, BUFFERS)
SELECT SUM(amount)
FROM perf_lab.orders;

ROLLBACK;
~~~

These `SET LOCAL` commands are strictly for lab observation. **Do not force the planner like this in production just to see workers.** Parallel plans also depend on parallel-safety of expressions, worker availability, and PostgreSQL limits.

### 33.1. Questions

1. Is there a `Gather` or `Gather Merge`?
2. What are `Workers Planned` and `Workers Launched`?
3. What is `loops` on `Parallel Seq Scan`?
4. Does cumulative row output across worker nodes approximate 50,000?
5. Why shouldn't you use total `actual total time × loops` as wall-clock query time?

## 34. Lab 7: Estimate Mismatch and Skew

To see the impact of an unusually frequent value, you can insert extra orders for one customer in the **lab database**:

~~~sql
INSERT INTO perf_lab.orders (
    order_id, customer_id, amount, status, created_at
)
SELECT
    (1000000 + g)::bigint,
    42,
    (5000 + g % 200)::numeric(12,2),
    'paid',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
      + g * INTERVAL '1 second'
FROM generate_series(1, 5000) AS s(g);
~~~

Now customer 42 has about **5,025 orders**, while other customers still have 25 orders.

### 34.1. Before and After ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;

ANALYZE perf_lab.orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

Compare estimated rows with actual rows. After `ANALYZE`, the planner can recognize the frequent value via MCV statistics, though perfect accuracy is never guaranteed.

### 34.2. Querying an Ordinary Customer

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 43;
~~~

Customer 43 still has only 25 orders. Compare plans for the high-volume customer and the ordinary customer, avoiding the assumption that one plan is optimal for all parameter values.

### 34.3. Do Not Run This Step Before Finishing the 50,000-Order Labs

After adding 5,000 orders, the total becomes **55,000** and the earlier baseline counts no longer hold. To repeat earlier exercises from scratch, use a fresh lab database or recreate the schema per standard procedure.

## 35. Inspecting Plan Structure in JSON Format

Text format is readable for humans, while automated tools parsing individual nodes can use:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT order_id
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

The output is a JSON structure containing the `Plan` tree and fields such as `Actual Rows`, `Actual Loops`, `Actual Startup Time`, `Actual Total Time`, along with estimates.

### 35.1. Using JSON to Avoid Fragile String Parsing

A JSON-reading tool can walk the node tree and:

1. Read `Node Type`.
2. Read `Plan Rows`.
3. Read `Actual Rows` and `Actual Loops`.
4. Read startup/total timings.
5. Compute estimated/actual ratios when needed.

**Do not split a JSON plan by lines and guess structure from spaces** when you can use a JSON parser.

### 35.2. JSON Does Not Fix Per-Loop Semantics Automatically

Changing format **does not change the semantics** of `Actual Rows` and `Actual Total Time`: they must still be read alongside `Actual Loops`, and parallel plans still require accounting for worker/leader distribution.

### 35.3. Avoid Exposing Sensitive Data

`EXPLAIN` with `VERBOSE` or output from real queries can include table/column/expression names and sometimes literal values from SQL. Review plans for sensitive data before sharing them outside your organization.

## 36. Step-by-Step Workflow to Read EXPLAIN ANALYZE Bottom-Up

Follow this order:

### Step 1. Read the Overview

Check `Planning Time`, `Execution Time`, occurrences of `Sort`, `Hash`, `Nested Loop`, `Gather`, `Buffers`, and signs of disk spills.

### Step 2. Read Leaf Nodes

Inspect `Seq Scan`/`Index Scan`/`Bitmap Heap Scan`:

- Estimated rows vs actual rows **per loop**.
- `Index Cond`/`Filter`.
- `Rows Removed by Filter`.
- `Buffers` and `actual time`.

### Step 3. Find Loop Multipliers

For nodes with `loops≫1`:

- Which parent invokes the node repeatedly?
- How many rows on average per loop?
- Roughly how many cumulative rows and how much cumulative time?
- Is `Materialize`/`Memoize` avoiding re-reading the child?

### Step 4. Trace Joins and Cardinality Across Layers

Compare:

- Outer input.
- Inner input (per-loop).
- Join output.
- Group aggregate output.
- Limit output.

### Step 5. Respect Inclusive Timing

Do not add total times across parent and child nodes. Use `Execution Time` as the overall anchor, and node timings to pinpoint which **branch** drives the work.

### Step 6. If Parallel Plan

Inspect workers planned/launched, loops on parallel children, worker breakdowns, and concurrent timing semantics.

### Step 7. Formulate Improvement Hypotheses

Examples:

- Update statistics/extended statistics when estimates drift.
- Add an index for repeated lookup/search conditions.
- Rewrite queries to avoid thousands of inner scans.
- Reduce rows entering sort/aggregate when business logic allows.
- Tune memory for appropriate workloads when spills occur.

### Step 8. Re-Measure Under Equivalent Conditions

Compare rows, loops, buffers, spills, and execution time across multiple runs. Never trade **result correctness** for a prettier plan.

## 37. Common Misinterpretations

### Mistake 1: actual rows Is the Total Row Count

Wrong when a node has multiple loops. In standard text output, `actual rows` is **averaged per loop**.

### Mistake 2: loops Is How Many Times the App Sent the Query

Wrong. Loops belong to **internal executor** node invocations.

### Mistake 3: actual time=0.050 Means the Whole Node Only Spent 0.050 ms

If `loops=1000`, cumulative sequential work on that node may be around `50 ms`, aside from parent/child structure and parallelism.

### Mistake 4: Summing Every Node's Time

Wrong because parent node timings are typically **inclusive** and already include child work.

### Mistake 5: Comparing estimated rows Against actual rows × loops

Wrong units. Compare **per-loop estimate with per-loop actual**; evaluate loop-count mismatch separately.

### Mistake 6: actual rows=0 loops=1000 Means Zero Rows Ever

May be wrong due to **average rounding**.

### Mistake 7: Limit rows=10 Proves the Executor Only Read 10 Rows

Wrong if Sort/Aggregate beneath it had to read huge inputs first.

### Mistake 8: Sort actual rows=10 Proves Only 10 Rows Were Sorted

Wrong; Sort may have received 50,000 rows and only emitted 10 as requested by its parent.

### Mistake 9: Nested Loop Is Always Slow

Wrong; with a small outer set and cheap inner index lookup, Nested Loop is often ideal.

### Mistake 10: Hash Join Is Always Fast

Wrong; large hash builds, spills, skew, and bad estimates can still make it slow.

### Mistake 11: Parallel Node Time × Workers Equals Execution Time

Wrong; workers execute concurrently, incur overhead, and can split work unevenly.

### Mistake 12: Buffers hit=100 Means Exactly 100 Rows Read

Wrong; buffer counts measure **block** accesses, not tuple counts.

### Mistake 13: Buffers read Always Means 100 Physical Disk Seeks

Wrong; OS caching and measurement mechanics apply. Separate logical block reads from physical storage I/O.

### Mistake 14: Planning Time + Execution Time Equals API Latency

Incomplete. Client/network/driver/UI add their own overhead.

### Mistake 15: EXPLAIN ANALYZE Never Modifies the DB

False for write statements. DML genuinely executes; watch out for rollback limits, triggers, and side effects.

### Mistake 16: TIMING OFF Makes Real SQL Faster

False; it mainly trims instrumentation overhead during that EXPLAIN run.

### Mistake 17: ANALYZE Statistics and EXPLAIN ANALYZE Are the Same

False: one collects statistics; the other runs a query to measure it.

### Mistake 18: Reading Only the Root Node Is Enough

False; a root returning 10 rows can still scan millions of rows in child nodes.

### Mistake 19: Seq Scan Is Always a Missing-Index Bug

False; sequential scans can be cheapest for small tables or queries returning a large fraction of rows.

### Mistake 20: Index Cond and Filter Are Fully Equivalent

False; conditions used to traverse the index differ from conditions applied after fetching rows.

### Mistake 21: Materialize loops=100 Means Its Child Seq Scan Also Has 100 Loops

False; the child has its own loop count, which may be just 1.

### Mistake 22: Optimizing Always Means Raising work_mem

Not every slow query is caused by Sort/Hash spills. If the issue is 100,000 inner lookups or bad estimates, adding memory misses the root cause.

## 38. Practice Exercises

Read the following simulated `EXPLAIN` snippets; compute approximate numbers when rounding applies. SQL exercises use the `perf_lab` schema created above. These are plan-reading and reasoning exercises, not QA test scripts.

### Exercise 1. Actual Rows and Loops

~~~text
Index Scan (actual time=0.010..0.040 rows=5 loops=200)
~~~

Roughly how many total rows does the node return? Roughly how many ms of cumulative time under a sequential model?

### Exercise 2. Startup and Total

~~~text
Sort (actual time=35.000..36.000 rows=10000 loops=1)
~~~

What do the numbers `35` and `36` mean? Are they a measurement error range?

### Exercise 3. Estimated vs Actual

~~~text
(cost=0.20..8.00 rows=2 width=16)
(actual time=0.01..0.10 rows=40 loops=500)
~~~

Roughly how many times off is the cardinality estimate per loop?

### Exercise 4. Do Not Compare Wrong Units

In Exercise 3, someone computes `40×500/2=10000` and claims the estimate is off by 10,000x. Explain the flaw in reasoning.

### Exercise 5. Inclusive Time

~~~text
Aggregate (actual time=12.00..12.01 rows=1 loops=1)
  -> Seq Scan (actual time=0.02..10.00 rows=50000 loops=1)
~~~

Can you add `12.01 + 10.00` to get Execution Time? Why or why not?

### Exercise 6. Nested Loop

~~~text
Nested Loop (actual ... rows=3000 loops=1)
  -> Seq Scan on customers (actual ... rows=100 loops=1)
  -> Index Scan on orders (actual ... rows=30 loops=100)
~~~

Why is inner `loops=100`? Roughly how many total inner rows?

### Exercise 7. Row Count Equals 0

~~~text
Index Scan (actual ... rows=0 loops=1000)
~~~

Can you assert the index returned zero rows across all 1,000 runs?

### Exercise 8. never executed

What is the difference between `never executed` and `rows=0 loops=1`?

### Exercise 9. LIMIT

~~~text
Limit (actual ... rows=10)
  -> Sort (actual ... rows=10)
       -> Seq Scan (actual ... rows=50000)
~~~

Why might Sort have processed 50,000 rows even though it only emitted 10?

### Exercise 10. Filter

~~~text
Seq Scan (actual ... rows=100 loops=1)
  Rows Removed by Filter: 9900
~~~

Roughly how many rows did the node inspect?

### Exercise 11. Buffers

Does `shared hit=500 read=20` mean exactly 520 rows were read? Does `read=20` mean exactly 20 physical disk seeks?

### Exercise 12. Parallel

~~~text
Parallel Seq Scan (actual ... rows=20000 loops=4)
~~~

Roughly what is total output? Can you multiply node time by 4 and call it wall time?

### Exercise 13. Workers

What do `Workers Planned: 4` and `Workers Launched: 2` indicate?

### Exercise 14. Materialize

~~~text
Materialize (actual ... rows=1000 loops=50)
  -> Seq Scan (actual ... rows=1000 loops=1)
~~~

Did the child Seq Scan execute 50 times?

### Exercise 15. Memoize

If `Memoize Hits=980, Misses=20` over 1,000 lookups, why might the underlying index scan only have around 20 loops?

### Exercise 16. Hash

Is `HashAggregate rows=2000` above `Seq Scan rows=50000` unusual? Why or why not?

### Exercise 17. Overall Timing

`Planning Time=0.5 ms`, `Execution Time=25 ms`, yet the API returns after 70 ms. List at least three components that could explain the difference.

### Exercise 18. TIMING OFF

Write an `EXPLAIN` command that still measures `actual rows` and `loops` while avoiding per-node timing overhead.

### Exercise 19. DML

Why must you be careful with `EXPLAIN ANALYZE UPDATE`? Write a safe block on the lab table to roll back transactional changes.

### Exercise 20. Statistics

If estimated rows diverge widely after loading data, what command do you run first to refresh statistics?

### Exercise 21. Index Lookup

Write a query finding all orders of customer 42 and run `EXPLAIN (ANALYZE, BUFFERS)`. Which fields should you record to evaluate whether an index helped?

### Exercise 22. LATERAL

Write a query fetching the three newest orders for each of the first 100 customers. Why might the inner lookup show `loops≈100`?

### Exercise 23. Generic Plan

When the same prepared statement runs for a customer with 25 orders and a customer with 5,025 orders, why might one generic plan be suboptimal for both?

### Exercise 24. Sort vs Ordered Scan

To fetch the top 10 orders by `amount DESC, order_id`, which index is worth testing? Which plan nodes might change?

### Exercise 25. SubPlan

A correlated SubPlan reports `Aggregate loops=2000`. Why must you weigh the execution count even though the aggregate returns only one row per loop?

### Exercise 26. JSON Plan

Write a command returning EXPLAIN in JSON format along with actual rows/loops and buffers.

### Exercise 27. Reading Time

~~~text
Index Scan
  (actual time=0.007..0.035 rows=2 loops=1000)
~~~

What is the approximate cumulative time of this node under sequential execution? Why not treat that as the entire query's Execution Time?

### Exercise 28. Finding the Root Cause

A plan has outer estimated 10 rows vs actual 10,000, and inner estimated 1 row/loop vs actual 20. Name the two multiplying sources of work amplification.

## 39. Reference Answers

### Exercise 1

Total rows roughly `5×200=1000`; cumulative iteration time roughly `0.040×200=8 ms`. Do not treat 8 ms as total statement latency.

### Exercise 2

`35 ms` is time until Sort outputs its first row; `36 ms` is time until the node completes its run. This is not a confidence interval/standard deviation.

### Exercises 3–4

Per-loop discrepancy is `40/2=20x`. Computing 10,000x is wrong because it compares **actual across all 500 runs** against **estimate per single run**.

### Exercise 5

No. Aggregate's total is typically inclusive, containing Seq Scan work. Adding them double-counts. Check `Execution Time` and individual branches.

### Exercise 6

The inner node is called for each of the 100 outer customer rows in the illustrative Nested Loop structure. Total inner rows is roughly `30×100=3000`.

### Exercises 7–8

`rows=0 loops=1000` can result from rounding the average, while some runs still returned rows. `never executed` means the node was never invoked; `rows=0 loops=1` ran once and returned zero rows.

### Exercise 9

Sort must read input to find the top 10; child Seq Scan sent 50,000 rows to Sort, while parent Limit only pulled 10 output rows.

### Exercise 10

Roughly `100+9900=10000` rows were examined in this single-loop example; real runs may carry additional instrumentation details.

### Exercise 11

No. Buffers measure **block** accesses, not row counts. `read=20` does not equate to exactly 20 physical disk seeks due to filesystem caching and I/O behavior.

### Exercises 12–13

Total output is roughly `20000×4=80000`. Workers/leader can run concurrently, so do not multiply timing and call it wall time. `Planned=4` is expected workers; `Launched=2` is actual workers started.

### Exercises 14–15

Materialize serves 50 iterations from buffered data while child Seq Scan runs only once. Memoize with 980 hits avoids calling the child for those lookups, leaving roughly 20 misses needing child work (subject to actual eviction/caching).

### Exercise 16

Not unusual: 50,000 orders are grouped into 2,000 customer groups, so the aggregate outputs 2,000 rows.

### Exercise 17

The difference can come from networking, connection acquisition/pooling, driver decoding/serialization, application logic, queueing, data transfer, and UI rendering; EXPLAIN measurements also carry instrumentation overhead unlike regular queries.

### Exercise 18

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM perf_lab.orders;
~~~

### Exercise 19

`EXPLAIN ANALYZE` genuinely executes the UPDATE:

~~~sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
UPDATE perf_lab.orders
SET amount = amount + 1
WHERE order_id = 1;
ROLLBACK;
~~~

Rollback protects transactional changes, though it does not guarantee undoing external side effects or sequences.

### Exercise 20

~~~sql
ANALYZE perf_lab.orders;
~~~

Then re-run the plan and compare estimates vs actuals; if still skewed, inspect skew, correlation, expression statistics, and join method.

### Exercise 21

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

Record `Index Cond`/`Filter`, estimated rows, actual rows, loops, Buffers, actual time, and Execution Time; never claim an index was used without reading the plan.

### Exercise 22

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT c.customer_id, recent.order_id
FROM perf_lab.customers AS c
CROSS JOIN LATERAL (
    SELECT o.order_id
    FROM perf_lab.orders AS o
    WHERE o.customer_id = c.customer_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 3
) AS recent
WHERE c.customer_id <= 100;
~~~

The correlated inner lookup finds three orders for **each customer**, so it is invoked around 100 times in a typical Nested Loop plan.

### Exercise 23

The two customers have vastly different selectivities. One generic plan/general estimate might select a scan/join strategy suited for ordinary customers but poor for extreme-volume customers (or vice versa). Measure across real parameter distributions and understand custom/generic plan behavior.

### Exercise 24

~~~sql
CREATE INDEX idx_orders_top_amount
ON perf_lab.orders (amount DESC, order_id ASC);
~~~

Then re-measure `ORDER BY amount DESC, order_id LIMIT 10`. An ordered index scan can eliminate a Sort, depending on selectivity and heap access cost.

### Exercise 25

An aggregate returning only 1 row per loop yet running 2,000 times can accumulate heavy input scans/CPU/IO. Read loops alongside actual time of both the aggregate **and** its child.

### Exercise 26

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT *
FROM perf_lab.orders
WHERE customer_id = 42;
~~~

### Exercise 27

Roughly `0.035×1000=35 ms` across iterations of this node in sequential execution. Node time can be inclusive and is only one piece of executor work; check `Execution Time` for total query time.

### Exercise 28

(1) Actual outer rows are 1,000x larger than predicted (10 → 10,000), multiplying inner invocations. (2) Inner returns 20x more rows per loop (1 → 20). Both errors multiply together, pushing actual work far past estimates.

## 40. Quick Reference Table

| Line in plan | Correct reading |
| --- | --- |
| `cost=a..b` | Startup/total estimate in planner cost units, **not ms** |
| `rows=E` in `cost` | Estimated node output per execution |
| `width=W` | Estimated average output row size (bytes) |
| `actual time=x..y` | Measured startup/total, ms **averaged per loop** |
| `actual rows=A` | Average output rows per loop; may be rounded |
| `loops=L` | Number of times the node executed |
| `A × L` | Approximate total output rows of the node |
| `y × L` | Approximate cumulative time of node iterations where applicable; **not query wall time** |
| `Rows Removed by Filter` | Rows discarded by Filter, usually reported per-loop |
| `Index Cond` | Condition used to access the index |
| `Filter` | Additional condition applied to rows |
| `Sort Method` | Sorting algorithm and memory/disk used |
| `Buckets/Batches` | Hash table structure and batching status |
| `Buffers: shared hit/read` | Block/buffer accesses, not row counts |
| `temp read/written` | Sign of temp file usage, potentially from spills |
| `Workers Planned/Launched` | Planned vs actual parallel workers |
| `Planning Time` | Reported planning duration |
| `Execution Time` | Total statement execution time under EXPLAIN instrumentation |
| `TIMING OFF` | Skips per-node timing while still measuring cardinality/loops with ANALYZE |
| `FORMAT JSON` | Structured plan output for automated analysis |

## 41. Checklist for Analyzing Any Execution Plan

1. Is the query actually slow **on the server** or only in the client/network?
2. Are you reading `EXPLAIN` or `EXPLAIN ANALYZE`?
3. Does the statement modify data? Have side effects been controlled if using `ANALYZE`?
4. What are `Execution Time` and `Planning Time`?
5. Which leaf node reads the most rows/blocks?
6. Do `Index Cond` and `Filter` match intent?
7. How much do estimated rows and actual rows **per loop** differ?
8. Which node has high `loops` and what causes it to be re-invoked?
9. What is the node's total output `rows × loops`?
10. Is the cumulative time of looped nodes significant?
11. Did you accidentally double-count parent/child times when explaining?
12. Is `LIMIT` hiding a full-table Sort/Scan underneath?
13. Are `Rows Removed by Filter` or Join Filter high?
14. Are `Sort`/`Hash` spilling to memory/disk?
15. Are `Materialize`/`Memoize` preventing repeated child calls?
16. Is it a parallel plan? Did Workers launched match planned?
17. Have you separated CPU, I/O, locking, and client overhead?
18. Do statistics need refreshing or skew/correlation investigation?
19. Have you measured multiple times with representative data and workloads?
20. After any change, did you verify **SQL result correctness** and the new plan?

## 42. Summary

In PostgreSQL's `EXPLAIN ANALYZE`, **`actual rows` and `actual time` cannot be interpreted properly without `loops`**. When a node executes multiple times, text output reports **per-iteration averages** for rows and timing. To approximate total rows emitted across all iterations, multiply `actual rows × loops`, keeping rounding error in mind. For time, `actual total time × loops` helps gauge cumulative work in a sequential plan, yet is **not** wall-clock time for the entire query, especially under parallelism.

Three essential rules:

1. **Compare estimated rows and actual rows in the same per-loop unit.** If there is a large gap, check statistics, skew, correlation, or cardinality drift in lower nodes.
2. **Read the execution tree rather than adding parent and child times.** Parent nodes generally carry inclusive time; `Nested Loop` multiplies inner iterations, while `Materialize`/`Memoize` can reduce child calls.
3. **Put timing in context.** `actual time=startup..total` describes a node's row-production timeline; `Planning Time`/`Execution Time` are summary totals; `BUFFERS`, `Sort Method`, worker details, and `TIMING OFF` help evaluate CPU/I/O/instrumentation carefully.

When you see `actual time=0.03 rows=3 loops=10000`, the question to ask is not "is 0.03 ms small?", but: **"Why was this node called 10,000 times, how many total rows did it return, how much cumulative work did it perform, and did the planner predict the loops/rows accurately?"**. That is how you turn `EXPLAIN ANALYZE` numbers into grounded optimization decisions.
