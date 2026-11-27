# Parallel Scan, Gather, and Gather Merge in PostgreSQL Query Plans

A PostgreSQL query scanning tens of millions of rows can take a long time if a single process handles all the data. When the workload fits, PostgreSQL can build a **parallel query plan**: splitting part of the work across multiple **parallel workers** so multiple processes scan, filter, compute, or sort concurrently and ship results back to the **leader**. In an `EXPLAIN` tree, the most visible markers are **`Parallel Seq Scan`**, **`Parallel Index Scan`**, **`Parallel Index Only Scan`**, **`Parallel Bitmap Heap Scan`**, **`Gather`**, and **`Gather Merge`**.

The hard part is not just memorizing node names. When analyzing a query, you must understand:

- **Which nodes can run in parallel?** Sitting underneath `Gather` does not automatically mean a node splits data among workers.
- **How do workers split work?** A "parallel-aware scan" coordinates fetching disjoint slices of data; each worker does not scan the entire table and emit duplicates.
- **How do `Gather` and `Gather Merge` differ?** `Gather` collects rows to the leader **without preserving global order**; `Gather Merge` merges pre-sorted worker streams to **preserve sort-key ordering**.
- **Why does `Workers Planned: 4` sometimes show `Workers Launched: 2`?** Planned worker count differs from runtime worker availability.
- **Why can a parallel plan still run slower?** Worker startup cost, IPC, leader processing, memory across multiple sorts/hashes, and I/O contention can outweigh gains.

This lesson sits in the context of the **PostgreSQL query planner and executor**. SQL scripts creating tables, loading data, and tweaking GUCs are strictly for a **lab database**; concrete `EXPLAIN` outputs vary by PostgreSQL version, statistics, hardware, and server settings.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the **leader + parallel workers** model and how a parallel plan executes.
2. Read `EXPLAIN` trees from parallel scan nodes up through `Gather` / `Gather Merge`.
3. Distinguish **parallel-aware** scans from nodes that do not split work, and distinguish **partial plans** from leader-side finalization.
4. Know when `Parallel Seq Scan`, `Parallel Bitmap Heap Scan`, `Parallel Index Scan`, and `Parallel Index Only Scan` appear.
5. Explain the difference between **`Gather`** and **`Gather Merge`**, especially under `ORDER BY`, `LIMIT`, and `Sort` nodes.
6. Analyze `Partial Aggregate`, `Finalize Aggregate`, `Sort`, `Hash`, and the placement of `Gather` in a plan.
7. Interpret `Workers Planned`, `Workers Launched`, `actual rows`, `loops`, per-worker timing/buffers, and leader participation.
8. Measure parallelism safely using `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)`.
9. Understand settings such as `max_parallel_workers_per_gather`, `max_parallel_workers`, `max_worker_processes`, `parallel_setup_cost`, `parallel_tuple_cost`, and size thresholds.
10. Recognize **parallel safety** limits, `PARALLEL SAFE`/`RESTRICTED`/`UNSAFE` functions, and why some queries cannot or should not run in parallel.
11. Weigh benefits, CPU/I/O/RAM costs, concurrency impact, and tuning criteria.
12. Practice on a sample dataset and explain plan shifts without drawing false conclusions.

## 2. Sequential Queries vs Parallel Queries

### 2.1. Sequential Query

Suppose an `events` table has 1 million rows. A query:

~~~sql
SELECT COUNT(*)
FROM events
WHERE event_type = 'purchase';
~~~

Under a sequential plan, one backend performs all scanning and counting:

~~~text
Client
  |
  v
PostgreSQL Backend (leader)
  |
  +-- Aggregate
        |
        +-- Seq Scan on events
              Filter: event_type = 'purchase'
~~~

Only one process executes those nodes, so speed can hit a ceiling when CPU, data size, or computation is large enough.

### 2.2. Parallel Query

When the planner sees parallelism as beneficial and the query meets safety rules, a plan might be:

~~~text
Client
  |
  v
Leader backend
  |
  +-- Finalize Aggregate
        |
        +-- Gather (Workers Planned: 2)
              |
              +-- Partial Aggregate
                    |
                    +-- Parallel Seq Scan on events
                         Filter: event_type = 'purchase'
~~~

In this model, workers scan portions of the table and compute **local partial counts**; the leader collects those partial results and combines them into the final count.

~~~mermaid
flowchart TD
    Q["Client sends SELECT"] --> L["Leader backend"]
    L --> G["Gather"]
    G --> PA["Partial Aggregate / Parallel Scan subtree"]
    PA --> W1["Worker 1: scans data slice"]
    PA --> W2["Worker 2: scans data slice"]
    PA --> W3["Leader may participate in scan"]
    W1 --> R["Partial results"]
    W2 --> R
    W3 --> R
    R --> G
    G --> F["Finalize Aggregate"]
    F --> O["Results returned to client"]
~~~

This diagram is conceptual: **`Gather` is a node inside the leader's execution tree**, not three independent copies of the SQL statement. Workers share shared-memory coordination structures and send tuples/partial results back to the leader.

### 2.3. Parallel Does Not Mean Speedup Equals Worker Count

Having 4 workers does not mean a query runs 4x faster:

- There is **startup and teardown cost** for workers.
- The leader must receive and merge data, sometimes becoming a bottleneck.
- Storage throughput, caching, or memory bandwidth may saturate.
- Workers compete for CPU with other active backends.
- Nodes above `Gather` still run sequentially on the leader.
- Small workloads are not large enough to amortize parallel overhead.

Parallel query is a **cost-based optimization choice**, not an "always enable as many workers as possible" dial.

## 3. Leader, Workers, and Partial Plan Structure

### 3.1. What Is the Leader?

The **leader** is the PostgreSQL backend serving the client connection. When a query uses a parallel plan, the leader:

- Launches the requested parallel workers;
- Executes the portion of the plan **above `Gather`**;
- Receives tuples/partial results sent by workers;
- May **participate in executing** the parallel portion depending on configuration and tuple arrival from workers;
- Returns final results to the client.

### 3.2. What Is a Worker?

A parallel worker is a **separate PostgreSQL OS process** spawned/coordinated to help execute the **parallel portion of one query plan**. Workers are not threads inside a Java application thread pool.

Workers use their own CPU and private RAM for certain operations while sharing coordination state to partition scans. Other backends can also request workers; available workers are a **finite instance-wide resource**.

### 3.3. What Is a Partial Plan?

The subtree **below `Gather`** (or `Gather Merge`) is structured as a **partial plan** that participating processes execute concurrently to produce **partial results**. `Gather`/`Gather Merge` then consolidates them.

~~~text
                 [Leader-only upper portion]
                    Finalize Aggregate
                           |
                        Gather
                           |
                 [Partial plan underneath]
                    Partial Aggregate
                           |
                   Parallel Seq Scan
~~~

Nodes inside the partial plan like `Filter`, `Project`, and `Partial Aggregate` process whatever slice of rows the parallel-aware scan hands them.

**Important:** "sitting below Gather" does not mean every node knows how to **divide work**. Only **parallel-aware** nodes like `Parallel Seq Scan`/`Parallel Index Scan` coordinate to avoid duplicate work; other nodes simply process the rows received by their worker process.

### 3.4. Parallel-Aware vs Parallel-Safe Differ

Two terms:

| Term | Meaning |
| --- | --- |
| **Parallel-safe** | Operation/function can safely run inside a parallel worker without breaking correctness or safety |
| **Parallel-aware** | Node coordinates **work distribution** across workers so each worker does not rescan the entire source |

A `Filter` performing simple arithmetic is parallel-safe without needing to partition work itself. `Parallel Seq Scan` both sits inside the partial plan and actively **distributes heap blocks** across processes.

### 3.5. One Query Can Have Multiple Parallel Regions

A plan can contain multiple `Gather` nodes in separate branches, such as complex aggregations or joins. Do not assume seeing one `Gather` means the **entire SQL statement** executes in parallel from end to end.

## 4. Parallel Seq Scan: Sequential Scanning with Multiple Readers

### 4.1. Seq Scan vs Parallel Seq Scan

`Seq Scan` reads a heap relation's blocks sequentially. `Parallel Seq Scan` lets multiple workers and the leader coordinate to claim **disjoint block ranges** of the same table.

~~~text
Heap table events:
   Block 0 ... 9999

Worker 1: blocks 0..N, then claims next unclaimed block
Worker 2: blocks M..K, then claims next unclaimed block
Worker 3: ...

Each block is handed out so participants
do not scan duplicate blocks in Parallel Seq Scan.
~~~

Assignment is typically **dynamic**. Never assume worker 1 always scans `1/N` of rows by primary key or a fixed `event_id` range.

### 4.2. Parallel Seq Scan Produces No Key Order

A plain sequential scan guarantees no `ORDER BY` order if SQL omits one. Parallel Seq Scan even less so—never assume "worker 1 returns low IDs and worker 2 returns high IDs."

**If ordering is required**, specify `ORDER BY` in SQL so the planner provides an ordering plan via `Sort` or `Gather Merge`.

### 4.3. Illustrative Plan

~~~text
Gather  (cost=1000.00..21000.00 rows=400000 width=...)
  Workers Planned: 3
  ->  Parallel Seq Scan on events e
        Filter: (event_type = 'purchase')
~~~

This is a **sample plan**; exact `cost`, `rows`, and worker counts **are not guaranteed outputs** for the lab dataset.

If the query returns **huge row counts**, the leader can spend heavy time pulling millions of tuples from workers through `Gather`. For `COUNT(*)`, placing `Partial Aggregate` below `Gather` so workers send **one tiny partial count** instead of millions of rows is vastly more efficient.

## 5. Practice Dataset for Parallel Plans

For PostgreSQL to consider parallel scans, the sample table needs more than a few dozen rows. Below we create **1,000,000 events** and a customer segment table. Run strictly in a lab database with adequate disk/RAM, never in production.

> **Practice resource note:** One million rows with a text payload consumes noticeable disk space and WAL/index build time. If your laptop or container is tight on resources, reduce `generate_series` to 100,000–300,000 and keep in mind the planner might stay serial; never overload a machine just to force a keyword in EXPLAIN.

### 5.1. Create Schema and Tables

~~~sql
CREATE SCHEMA parallel_lab_273;

CREATE TABLE parallel_lab_273.events (
    event_id BIGINT PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    event_type TEXT NOT NULL
        CHECK (event_type IN ('purchase', 'view')),
    amount NUMERIC(12, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE parallel_lab_273.customers (
    customer_id INTEGER PRIMARY KEY,
    segment TEXT NOT NULL
        CHECK (segment IN ('NEW', 'REGULAR', 'VIP'))
);
~~~

### 5.2. Load Events

~~~sql
INSERT INTO parallel_lab_273.events (
    event_id,
    customer_id,
    event_type,
    amount,
    occurred_at,
    payload
)
SELECT
    g::bigint,
    (g % 10000 + 1)::integer,
    CASE
        WHEN g % 10 IN (0, 1, 2) THEN 'purchase'
        ELSE 'view'
    END,
    ((g % 100000)::numeric / 100 + 1)::numeric(12, 2),
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g % 15552000) * INTERVAL '1 second',
    repeat('x', 120)
FROM generate_series(1, 1000000) AS gs(g);
~~~

In the generated data:

- `event_id` runs from 1 to 1,000,000 uniquely.
- `customer_id` cycles from 1 to 10,000.
- Out of every 10 events, 3 are `'purchase'` and 7 are `'view'`, giving **300,000 purchases**.
- `amount` and `occurred_at` are deterministic, convenient for sort and filter tests.
- `payload` widens rows enough for parallel scans to become realistic.

### 5.3. Load Customers for Join Experiments

~~~sql
INSERT INTO parallel_lab_273.customers (
    customer_id,
    segment
)
SELECT
    g::integer,
    CASE
        WHEN g % 10 = 0 THEN 'VIP'
        WHEN g % 3 = 0 THEN 'NEW'
        ELSE 'REGULAR'
    END
FROM generate_series(1, 10000) AS gs(g);
~~~

Both tables have primary keys, so PostgreSQL already has B-tree indexes from `PRIMARY KEY`.

### 5.4. Refresh Statistics Before EXPLAIN

~~~sql
ANALYZE parallel_lab_273.events;
ANALYZE parallel_lab_273.customers;

SELECT
    COUNT(*) AS all_events,
    COUNT(*) FILTER (WHERE event_type = 'purchase')
        AS purchases
FROM parallel_lab_273.events;
~~~

**Expected counts:** `all_events=1000000` and `purchases=300000`. That reflects the generated data, not a requirement that plans match across machines.

### 5.5. Do Not Run VACUUM Inside a Transaction

If you later run:

~~~sql
VACUUM (ANALYZE) parallel_lab_273.events;
~~~

run it in autocommit mode outside `BEGIN`, because PostgreSQL forbids regular `VACUUM` inside an explicit transaction block. On a large table, it uses notable I/O.

## 6. Basic EXPLAIN: Identifying a Parallel Plan

First run **EXPLAIN without ANALYZE**:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

If the planner picks parallel, you may see:

~~~text
Finalize Aggregate
  ->  Gather
        Workers Planned: 2
        ->  Partial Aggregate
              ->  Parallel Seq Scan on events
                    Filter: (event_type = 'purchase')
~~~

Otherwise, a sequential plan looks like:

~~~text
Aggregate
  -> Seq Scan on events
       Filter: (event_type = 'purchase')
~~~

Both are **semantically identical** and reasonable cost-based choices in different environments.

### 6.1. Reading Bottom-Up

- `Parallel Seq Scan`: scans the table collaboratively; each participant claims blocks/tuples.
- `Partial Aggregate`: each worker/leader computes local partial counts.
- `Gather`: ships partial count rows to the leader.
- `Finalize Aggregate`: combines partial counts into the exact total.

`COUNT(*)` needs no ordering, so `Gather` fits; **`Gather Merge` adds zero value when sorted streams are unneeded**.

### 6.2. How Does EXPLAIN ANALYZE Differ?

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

`ANALYZE` makes PostgreSQL **execute the query** and record actual metrics like `actual time`, `rows`, `loops`, and `Workers Launched`. `BUFFERS` reports buffer I/O; `VERBOSE` can include per-worker breakdowns.

Since this is a pure `SELECT COUNT(*)`, running it in the lab is safe. **Running `EXPLAIN ANALYZE` on DML like `UPDATE`/`DELETE` executes the real write**, not just a dry run. Only do so after evaluating side effects and transaction safety.

### 6.3. Illustrative Actual Plan Structure

~~~text
Finalize Aggregate (actual time=... rows=1 loops=1)
  -> Gather (actual time=... rows=3 loops=1)
       Workers Planned: 2
       Workers Launched: 2
       -> Partial Aggregate (actual time=... rows=1 loops=3)
            -> Parallel Seq Scan on events
                 (actual time=... rows=100000 loops=3)
                 Filter: (event_type = 'purchase')
~~~

Here two workers plus the leader participated below `Gather`, producing `loops=3`; however, **never assume `loops` always equals `Workers Launched + 1`**, because leader participation and timing vary. `actual rows` beneath parallel nodes follows EXPLAIN's averaging rules and must be read alongside `loops`/worker stats—**never treat it as a single global row total**.

### 6.4. Why No Gather Despite a Large Table?

Parallel query is a planner choice. Absence of `Gather` can happen because:

- An index scan is faster.
- `max_parallel_workers_per_gather=0` or no workers are left.
- Table/work volume is too small to amortize startup cost.
- The query contains a parallel-unsafe operation.
- Selective filters shrink row count early.
- `ORDER BY`/`LIMIT` favors a single index scan.
- Cost parameters, statistics, or settings disfavor parallel.
- Transaction mode or statement constraints forbid parallel execution.

There is nothing to "fix" solely because `Parallel` does not appear if latency and SLAs are already good.

## 7. Workers Planned vs Workers Launched

In `EXPLAIN`:

~~~text
Workers Planned: 4
~~~

means the **planner requested up to four parallel workers** for that `Gather`. At runtime, `EXPLAIN ANALYZE` may report:

~~~text
Workers Launched: 2
~~~

meaning PostgreSQL **could only launch two workers** for that run.

### 7.1. Why Were Fewer Workers Launched?

Worker availability is bounded by:

- `max_parallel_workers_per_gather` — cap per Gather/query;
- `max_parallel_workers` — instance-wide cap on active parallel query workers;
- `max_worker_processes` — broader instance cap across all background worker types;
- Workers currently occupied by other queries;
- OS resources and runtime conditions.

Hence, **`Workers Planned` is neither actual workers used** nor dedicated CPU cores.

### 7.2. When Zero or Fewer Workers Launch

A parallel plan can still run with fewer workers, or even leader-only when needed. Results remain exact, though **elapsed time** can diverge sharply from planner expectations.

Never interpret `Workers Launched < Workers Planned` as data corruption; it reflects runtime worker availability, concurrency, or resource limits.

### 7.3. Does the Leader Participate in Scanning?

`parallel_leader_participation` controls whether the leader helps execute the subtree below `Gather`. It defaults to **on** in modern PostgreSQL.

Still, **the leader must also drain tuples from workers**. On queries emitting millions of rows, the leader spends most of its time receiving tuples rather than scanning. With `Partial Aggregate` emitting tiny rows, the leader has far more room to scan.

### 7.4. Never Multiply "Workers" into "Independent Full Scans"

A `Parallel Seq Scan` is **one coordinated scan**. Three participants does not mean the table was scanned three times. Interpret buffer/page scans and tuple counts via the parallel-aware model, not naive multiplication.

## 8. Gather: Collecting Results Without Preserving Order

`Gather` sits at the boundary between the **partial plan** and **leader-side processing**. It pulls tuples from participants and passes them upward.

~~~text
                  [Leader]
                     |
                   Gather
                     ^
          +----------+---------+
          |          |         |
       Worker A   Worker B  Leader
          |          |         |
       Tuple A1   Tuple B1  Tuple L1
       Tuple A2   Tuple B2  Tuple L2
       Tuple A3   Tuple B3  Tuple L3
~~~

Arrival order at `Gather` depends on worker timing:

~~~text
Worker A:  1,  3,  5,  7
Worker B:  2,  4,  6,  8

Gather may emit:
    1, 3, 2, 4, 6, 5, 8, 7
~~~

**Gather does not merge streams by any sort key.** Even if each worker produces an individually sorted stream, `Gather` **makes zero global ordering guarantee**.

### 8.1. Gather Is Not UNION ALL

`Gather` merges outputs from **one shared partial plan**, unlike SQL's `UNION ALL` combining independent queries. Both combine streams, yet their execution roles differ completely.

### 8.2. Gather + Sort

If a query has `ORDER BY` and the planner picks `Gather`, the tree may look like:

~~~text
Sort
  Sort Key: amount DESC, event_id DESC
  -> Gather
       Workers Planned: 2
       -> Parallel Seq Scan on events
~~~

Here, **Sort above Gather** runs on the leader to establish global order. With huge outputs, sorting on the leader can become a CPU/RAM bottleneck or spill to temp disk.

### 8.3. Gather Never Lets You Omit ORDER BY

~~~sql
SELECT event_id
FROM parallel_lab_273.events
WHERE event_type = 'purchase'
LIMIT 20;
~~~

Without `ORDER BY`, **which 20 IDs return is undefined by SQL contract**, regardless of `Gather`, `Seq Scan`, or `Index Scan`. If you need "the 20 newest events," write:

~~~sql
SELECT event_id, occurred_at
FROM parallel_lab_273.events
WHERE event_type = 'purchase'
ORDER BY occurred_at DESC, event_id DESC
LIMIT 20;
~~~

The planner can choose a serial index scan, `Gather Merge`, `Gather + Sort`, or another valid plan; results must obey `ORDER BY`.

## 9. Gather Merge: Merging Pre-Sorted Streams

**`Gather Merge`** differs from `Gather` in that it expects **already compatibly sorted** output streams from participants and **merges** them into one globally ordered output stream.

~~~text
Worker A (sorted): 1, 3, 5, 7
Worker B (sorted): 2, 4, 6, 8
Leader   (sorted): 0, 9

Gather Merge:
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9
~~~

The diagram uses integers for clarity; in reality `Gather Merge` compares the plan's **sort keys** obeying `ASC`/`DESC` and `NULLS FIRST`/`LAST`.

### 9.1. Why Must Streams Be Sorted Before Gather Merge?

If worker A emits `1, 7, 3` and worker B emits `2, 8, 4`, comparing stream heads cannot yield sorted output. To merge properly, **every participant's stream must be compatibly pre-sorted**.

Hence plans commonly show:

~~~text
Gather Merge
  Workers Planned: 3
  -> Sort
       Sort Key: amount DESC, event_id DESC
       -> Parallel Seq Scan on events
~~~

Or a parallel index scan supplies compatible ordering directly without a per-stream Sort:

~~~text
Gather Merge
  Workers Planned: 2
  -> Parallel Index Scan using idx_events_amount_event_id on events
~~~

**Both diagrams are illustrative plans**, never guaranteed for any specific query.

### 9.2. Gather Merge Does Not Re-Sort the Whole Table on the Leader

When `Sort` sits **below Gather Merge**, each worker/participant sorts **only its own slice**. `Gather Merge` inspects the head of each stream and emits the next smallest/largest row continuously, rather than pulling everything to the leader and sorting from scratch at the end.

In exchange, the leader performs merge comparisons across streams and coordinates tuple queues. With many streams or huge outputs, merging still carries cost.

### 9.3. ORDER BY with Duplicate Keys

`Gather Merge` guarantees **ordering on the specified sort keys**, not a **unique deterministic order** among rows sharing identical key values.

Example:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC
LIMIT 20;
~~~

Many events share the same `amount`. PostgreSQL may emit tied rows in arbitrary order. For pagination or reproducible results, add a unique tiebreaker:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 20;
~~~

**Gather Merge enforces only the ordering you asked for**; it never invents `event_id` tiebreaking on its own.

### 9.4. Gather Merge vs Merge Join

Similar names, different roles:

| Node | Responsibility |
| --- | --- |
| **Gather Merge** | Merges pre-sorted streams from **one partial plan** across workers/leader |
| **Merge Join** | Joins two separate ordered relations on matching join keys |

One plan can contain both nodes; never mistake `Gather Merge` for a join.

## 10. Comparing Gather and Gather Merge

| Criterion | Gather | Gather Merge |
| --- | --- | --- |
| Role | Collect tuples from partial plan | Collect **and merge sorted streams** |
| Must inputs be sorted? | **No** | **Yes**, on compatible keys |
| Preserves global order? | No | Yes, on specified sort keys |
| Commonly paired with | Parallel Seq Scan, Partial Aggregate, unordered output | `ORDER BY`, sorted partial scans, worker-side `Sort` |
| Leader cost | Receive/pass tuples, upper processing | Receive/pass tuples **plus key-based merging** |
| Where can Sort appear? | `Sort` **above** Gather | `Sort` **below** Gather Merge |
| Deterministic order on key ties? | No | No if `ORDER BY` omits a tiebreaker |
| Which is faster? | Depends on workload | Depends on row count, sort, index, and merge cost |

**There is no rule that "Gather Merge always beats Gather + Sort."** If output is tiny, sorting on the leader can be cheaper. If each worker processes massive rows and benefits from parallel sorting, `Gather Merge` shines. The planner estimates costs and chooses accordingly.

## 11. Practicing Gather Merge with ORDER BY

Query sorting events by amount with `event_id` tiebreaker:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 1000;
~~~

PostgreSQL can choose among several valid plans:

### 11.1. Sequential Sort Plan

~~~text
Limit
  -> Sort
       Sort Key: amount DESC, event_id DESC
       -> Seq Scan on events
~~~

One backend scans and sorts needed rows, potentially using top-N heapsort due to `LIMIT`.

### 11.2. Gather + Sort Plan

~~~text
Limit
  -> Sort
       Sort Key: amount DESC, event_id DESC
       -> Gather
            Workers Planned: 3
            -> Parallel Seq Scan on events
~~~

Workers help scan/filter, then the leader sorts because `Gather` does not preserve order.

### 11.3. Gather Merge Plan

~~~text
Limit
  -> Gather Merge
       Workers Planned: 3
       -> Sort
            Sort Key: amount DESC, event_id DESC
            -> Parallel Seq Scan on events
~~~

Each participant sorts its own slice by the same keys. `Gather Merge` merges them and feeds sorted rows to `Limit`.

### 11.4. LIMIT and Top-N Sort

With `ORDER BY ... LIMIT 1000`, PostgreSQL can use **top-N heapsort** rather than buffering every row in memory. In a parallel plan, each worker keeps its local top-N candidates, and `Gather Merge`/leader combines them for the global top-N.

In `EXPLAIN (ANALYZE)`, seeing:

~~~text
Sort Method: top-N heapsort  Memory: ...
~~~

reports the **actual sort method** used by that node—not an "index type" nor proof the rest of the table was skipped.

### 11.5. Why Doesn't Every ORDER BY Query Choose Gather Merge?

- A B-tree index already supplies the order efficiently.
- With a tiny `LIMIT`, a single index scan stops early.
- Filtered rows are few enough that leader sorting is cheap.
- Workers are unavailable or startup cost is too high.
- Intermediate operations prevent sorted partial streams.
- The planner estimates `Gather + Sort` or a serial path costs less.

`ORDER BY` only requires PostgreSQL to **deliver the requested order**, never dictating a specific node.

## 12. Parallel Index Scan: Splitting B-Tree Index Traversal

`Parallel Index Scan` is an index scan inside a partial plan coordinating participants. In modern PostgreSQL, parallel index scans support **B-tree indexes**. Participants claim chunks of index work to traverse and emit matching tuples concurrently.

### 12.1. Regular Index Scan

~~~text
Index Scan using idx_events_created_at on events
  Index Cond: occurred_at >= ...
~~~

One process walks the index and fetches heap tuples when needed.

### 12.2. Parallel Index Scan

~~~text
Gather
  Workers Planned: 2
  -> Parallel Index Scan using idx_events_created_at on events
       Index Cond: occurred_at >= ...
~~~

Workers cooperate to traverse the B-tree index. Do not imagine each worker owns an independent table shard or runs its own independent full cursor from start to finish.

### 12.3. Create a Test Index

~~~sql
CREATE INDEX idx_events_created_at_273
ON parallel_lab_273.events (occurred_at);

ANALYZE parallel_lab_273.events;
~~~

Range query reading many rows:

~~~sql
EXPLAIN
SELECT event_id, occurred_at
FROM parallel_lab_273.events
WHERE occurred_at >= TIMESTAMPTZ '2026-03-01 00:00:00+00';
~~~

Depending on rows, selectivity, correlation, and cost, PostgreSQL may pick `Index Scan`, `Bitmap Heap Scan`, `Seq Scan`, or their parallel counterparts.

**Having an index does not guarantee Parallel Index Scan appears.** For a highly selective predicate, a serial index scan beats launching workers. For a broad predicate covering most of the table, `Parallel Seq Scan` can beat scattered heap reads via index.

### 12.4. Ordering in Parallel Index Scan

A B-tree index supplies key order, yet participants process **separate pieces**. To emit globally sorted results, the plan must use `Gather Merge` (when participants supply compatible streams) or sort upstream.

**Never assume a B-tree means `Gather` automatically emits globally sorted rows.**

### 12.5. Index Scan and Heap Access

`Parallel Index Scan` finds TIDs via the index and reads the heap for unindexed columns or visibility checks. Its cost is shaped by:

- Number of heap visits;
- Fraction of pages cached in shared buffers;
- Correlation between index key order and physical heap order;
- Selectivity and tuples discarded by filters;
- Random I/O and buffer contention.

Often `Parallel Seq Scan` wins by reading heap blocks sequentially.

## 13. Parallel Index Only Scan: Fewer Heap Reads When All-Visible

`Index Only Scan` tries to return results directly from index data without reading full heap tuples. With a qualifying B-tree and conditions, PostgreSQL can choose **`Parallel Index Only Scan`**.

### 13.1. Create a B-Tree Index for a Key-Only Query

~~~sql
CREATE INDEX idx_events_customer_273
ON parallel_lab_273.events (customer_id);
~~~

A query:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE customer_id BETWEEN 1000 AND 8000;
~~~

can use `Parallel Index Only Scan` on `customer_id` if the planner estimates it is cheaper.

Illustrative plan:

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 2
       -> Partial Aggregate
            -> Parallel Index Only Scan using idx_events_customer_273
                 Index Cond: (customer_id >= 1000 AND customer_id <= 8000)
~~~

### 13.2. "Only" Does Not Mean Zero Heap Reads

PostgreSQL must verify each tuple is visible to the current snapshot. Indexes lack complete MVCC metadata; the **visibility map** tracks which heap pages are all-visible so heap checks can be skipped.

If a page is not all-visible, `Index Only Scan` still **visits the heap to check visibility**.

~~~text
Parallel Index Only Scan ...
  Heap Fetches: 12345
~~~

`Heap Fetches` is a critical metric in `EXPLAIN (ANALYZE)`. Never see "Index Only" and assume heap I/O is zero.

### 13.3. Practicing VACUUM / Visibility Map

After loading data and indexes, run **outside any explicit transaction**:

~~~sql
VACUUM (ANALYZE) parallel_lab_273.events;
~~~

After VACUUM, eligible pages are marked all-visible, letting index-only scans skip heap fetches. Still, final `Heap Fetches` depends on open transactions, concurrent writes, VM state, and plan choice—**it is never guaranteed to hit 0**.

### 13.4. INCLUDE to Return Extra Columns

If the app also needs `event_id` by `customer_id`, consider:

~~~sql
CREATE INDEX idx_events_customer_cover_273
ON parallel_lab_273.events (customer_id)
INCLUDE (event_id);
~~~

`event_id` sits in the index payload, enabling index-only scans for:

~~~sql
SELECT customer_id, event_id
FROM parallel_lab_273.events
WHERE customer_id BETWEEN 1000 AND 1200;
~~~

**`INCLUDE` inflates index size** and write cost. Never stuff every column into an index solely chasing Index Only Scan.

## 14. Parallel Bitmap Heap Scan: Sharing Heap Blocks After Building a Bitmap

When selectivity falls between a narrow index scan and a full table scan, PostgreSQL may pick **Bitmap Index Scan + Bitmap Heap Scan**.

### 14.1. Sequential Bitmap Scan

~~~text
Bitmap Heap Scan on events
  Recheck Cond: customer_id BETWEEN 1000 AND 8000
  -> Bitmap Index Scan using idx_events_customer_273
       Index Cond: customer_id BETWEEN 1000 AND 8000
~~~

`Bitmap Index Scan` collects matching heap locations; `Bitmap Heap Scan` visits those heap pages to fetch/verify tuples.

### 14.2. Parallel Bitmap Heap Scan

Illustrative plan:

~~~text
Gather
  Workers Planned: 3
  -> Parallel Bitmap Heap Scan on events
       Recheck Cond: customer_id BETWEEN 1000 AND 8000
       -> Bitmap Index Scan using idx_events_customer_273
            Index Cond: customer_id BETWEEN 1000 AND 8000
~~~

**Key nuance:** constructing the bitmap via `Bitmap Index Scan` is normally done by **one process (the leader/bitmap builder)**, then `Parallel Bitmap Heap Scan` coordinates multiple workers to read heap blocks from the **shared bitmap**.

Do not assume every worker runs a full duplicate `Bitmap Index Scan` to build identical bitmaps; the main parallelized phase is **reading the heap from the shared bitmap**.

### 14.3. Bitmaps Do Not Preserve Result Sort Order

Bitmap Heap Scan visits heap pages in block order to optimize I/O, **making no guarantee of index key order**. If the query specifies `ORDER BY customer_id`, a `Sort` or another access path is still needed.

### 14.4. What Does Recheck Cond Mean?

`Recheck Cond` is the predicate re-evaluated against heap tuples when needed, especially on **lossy bitmap pages** or equivalent access paths. In `EXPLAIN ANALYZE`, look for:

~~~text
Rows Removed by Index Recheck: ...
Heap Blocks: exact=... lossy=...
~~~

When a bitmap turns **lossy** under memory limits, it tracks blocks rather than individual offsets, forcing the executor to inspect more tuples per block.

### 14.5. work_mem Affects Bitmaps

`work_mem` limits memory for bitmap/sort/hash operations, yet never raise it endlessly just to "eliminate lossy bitmaps." With parallel workers and multiple memory-heavy nodes, total RAM rises steeply.

## 15. Four Parallel Scan Types: Comparison Table

| Node | Access source | How work is divided | Direct sort order support? | What to watch |
| --- | --- | --- | --- | --- |
| **Parallel Seq Scan** | Heap table | Coordinates scanning heap blocks | No order guarantee | Blocks/rows scanned, filters, buffers |
| **Parallel Index Scan** | B-tree index and heap | Coordinates scanning index slices | Can emit sorted partial streams | `Index Cond`, heap I/O, Gather/Gather Merge |
| **Parallel Index Only Scan** | B-tree index, heap when needed | Coordinates scanning index; VM governs heap fetches | Can emit sorted partial streams | `Heap Fetches`, all-visible pages, predicates |
| **Parallel Bitmap Heap Scan** | Bitmap index result + heap | Bitmap built once; participants read heap blocks from shared bitmap | No order guarantee | `Recheck Cond`, exact/lossy blocks, bitmap cost |

No single node is "universally best." The planner balances selectivity, page counts, data layout, statistics, indexes, workers, and upper nodes.

### 15.1. Index vs Scan Is Not Decided by Row Count Alone

A query returning 100,000 rows may use an index if matching rows cluster tightly, or `Parallel Seq Scan` if rows scatter across the table and sequential reading is cheaper. `rows` matters, never exclusively.

### 15.2. Index Only Scan Still Requires Data Inside the Index

If a query requests a wide `payload` and the index holds only `customer_id`, **Index Only Scan cannot return `payload`**. Index-only requires every returned/checked column to live in the index alongside favorable visibility.

### 15.3. Bitmap Heap Scan Can Combine Multiple Bitmap Index Scans

Example query:

~~~sql
SELECT event_id
FROM parallel_lab_273.events
WHERE customer_id BETWEEN 1000 AND 2000
  AND occurred_at >= TIMESTAMPTZ '2026-04-01 00:00:00+00';
~~~

With both indexes present, PostgreSQL **may** combine bitmaps via `BitmapAnd`/`BitmapOr`. That differs from a `Parallel Index Scan` walking a single index, and is never guaranteed just because two indexes exist.

## 16. Partial Aggregate and Finalize Aggregate

In parallel queries, **aggregation** is where parallelism often shines brightest because it shrinks tuples crossing `Gather`.

### 16.1. COUNT(*) Splits Cleanly

For `COUNT(*)`:

~~~text
Worker 1 counts: 100,000
Worker 2 counts: 120,000
Leader counts:    80,000
                     |
                     v
        Finalize = 300,000
~~~

Plan:

~~~text
Finalize Aggregate
  -> Gather
       -> Partial Aggregate
            -> Parallel Seq Scan on events
~~~

`Partial Aggregate` computes **intermediate partial state**; `Finalize Aggregate` combines partial states and emits final output.

### 16.2. SUM/AVG/COUNT with GROUP BY

~~~sql
EXPLAIN
SELECT
    customer_id,
    COUNT(*) AS event_count,
    SUM(amount) AS total_amount
FROM parallel_lab_273.events
GROUP BY customer_id;
~~~

Depending on data and cost, PostgreSQL may pick:

~~~text
Finalize HashAggregate
  Group Key: customer_id
  -> Gather
       Workers Planned: 3
       -> Partial HashAggregate
            Group Key: customer_id
            -> Parallel Seq Scan on events
~~~

Each worker builds local groups. Above `Gather`, the leader merges states sharing the same `customer_id`.

### 16.3. Why Can't COUNT(DISTINCT) Simply Sum Partial Counts?

`COUNT(DISTINCT customer_id)` cannot be computed by summing each worker's local `COUNT(DISTINCT)`, because the same customer can appear across multiple workers. PostgreSQL restricts **parallel partial aggregation** for aggregates using `DISTINCT` or `ORDER BY`.

Example:

~~~sql
EXPLAIN
SELECT COUNT(DISTINCT customer_id)
FROM parallel_lab_273.events;
~~~

Do not assume a simple `Partial Aggregate` appears like `COUNT(*)`. **Table scanning may still run in parallel**, while distinct aggregation gathers rows/states differently.

### 16.4. GROUP BY and Gather Merge

Another plan for `GROUP BY customer_id` could be:

~~~text
Finalize GroupAggregate
  Group Key: customer_id
  -> Gather Merge
       Workers Planned: 2
       -> Sort
            Sort Key: customer_id
            -> Partial HashAggregate
                 Group Key: customer_id
                 -> Parallel Seq Scan on events
~~~

**Role of Gather Merge:** each stream arrives sorted by `customer_id` so the leader processes groups sequentially for `Finalize GroupAggregate`. The planner selects among `HashAggregate`, `Sort`, and `GroupAggregate` based on types, group counts, and costs.

### 16.5. Aggregates Do Not Always Support Partial Mode

An aggregate function running in **Partial/Finalize** mode must define combine/serialization functions for intermediate states. Some extension or user-defined aggregates lack partial-mode support. Even if scanning runs in parallel, **`Finalize Aggregate` or all aggregation may have to run on the leader**.

Check the plan and aggregate documentation rather than assuming every `SUM`-like UDF parallelizes automatically.

## 17. Gather Merge and Finalize GroupAggregate

When `Finalize GroupAggregate` needs inputs ordered by group keys, `Gather Merge` fits naturally:

~~~text
                     Finalize GroupAggregate
                            Group Key: region
                                   |
                               Gather Merge
                            Sort Key: region
                                   |
                        Partial GroupAggregate
                            Group Key: region
                                   |
                               Sort/Index path
                                   |
                        Parallel-aware scan
~~~

Meaning:

1. Participants perform local grouping;
2. Local group streams are delivered in group-key order;
3. `Gather Merge` merges streams by group key;
4. `Finalize GroupAggregate` combines partial states per group.

This structure is helpful to recognize when `EXPLAIN` places **`Finalize GroupAggregate`** right above **`Gather Merge`**, yet it is **not the only plan** for `GROUP BY`.

### 17.1. Final ORDER BY Does Not Guarantee Gather Merge

~~~sql
SELECT customer_id, COUNT(*)
FROM parallel_lab_273.events
GROUP BY customer_id
ORDER BY customer_id;
~~~

PostgreSQL may choose:

- `Partial HashAggregate -> Gather -> Finalize HashAggregate -> Sort`;
- `Partial GroupAggregate -> Gather Merge -> Finalize GroupAggregate`;
- A serial scan/aggregate with sort;
- Other variants.

Every variant satisfies `ORDER BY`. Never force one diagram onto all queries.

### 17.2. Gather Merge Does Not Shrink Group Count by Itself

With 10,000 customer IDs, each worker can emit up to 10,000 partial group rows that the leader still must finalize into 10,000 groups. Rows crossing `Gather Merge` depend on distinct groups seen per participant, neither equal to base table rows nor always equal to global group count.

### 17.3. Ordering Within Identical Groups

In `Finalize GroupAggregate`, partial rows sharing a group key meet together via `Gather Merge`. However, if `ORDER BY` sorts by an aggregate result such as `COUNT(*) DESC`, PostgreSQL still needs a **final Sort** on the aggregated output.

## 18. JOINs in Parallel Plans: Not Every Node Splits Work

A query:

~~~sql
EXPLAIN
SELECT
    c.segment,
    COUNT(*) AS event_count,
    SUM(e.amount) AS total_amount
FROM parallel_lab_273.events AS e
JOIN parallel_lab_273.customers AS c
    ON c.customer_id = e.customer_id
GROUP BY c.segment;
~~~

may execute scans, joins, and aggregates in a parallel plan. Depending on sizes and stats, the planner may pick Nested Loop, Hash Join, Parallel Hash Join, or another strategy.

### 18.1. Illustrative Plan with Hash Join Below Gather

~~~text
Finalize GroupAggregate/Finalize HashAggregate
  -> Gather / Gather Merge
       -> Partial Aggregate
            -> Hash Join
                 Hash Cond: (e.customer_id = c.customer_id)
                 -> Parallel Seq Scan on events e
                 -> Hash
                      -> Seq Scan on customers c
~~~

In some plans, **each worker** builds its own private hash table copy for a small inner side. Seeing `Hash Join` below `Gather` does not mean it is a `Parallel Hash Join` sharing one hash table.

### 18.2. Parallel Hash Join

When PostgreSQL picks `Parallel Hash` / `Parallel Hash Join`, participants collaborate to **build a shared hash table** instead of every worker duplicating the build side. That is a distinct parallel optimization, related to yet separate from `Parallel Seq Scan`.

### 18.3. Distinguishing Parallelism Across Branches

Locate the `Gather` boundary. If a join sits **above Gather**, the leader executes that join while scans below run in parallel. If a join sits **below Gather**, participants execute it, with work-splitting mechanics governed by node and join type.

**Plan-reading habit:** find the *Gather boundary* first, then check which nodes truly run in workers.

## 19. Parallel Configuration: Key Parameters

PostgreSQL exposes several parallel settings. Default values in the table are **typical reference defaults in modern PostgreSQL**, not guaranteed settings on your server.

| Parameter | Typical default | Primary meaning |
| --- | ---: | --- |
| `max_parallel_workers_per_gather` | 2 | Max workers requested per Gather/Gather Merge |
| `max_parallel_workers` | 8 | Instance-wide cap on active parallel query workers |
| `max_worker_processes` | 8 | Broader instance-wide cap on all background worker processes |
| `parallel_setup_cost` | 1000 | Planner cost estimate for setting up parallel workers |
| `parallel_tuple_cost` | 0.1 | Planner cost estimate per tuple shipped from worker to leader |
| `min_parallel_table_scan_size` | 8 MB | Size threshold for considering parallel table scans |
| `min_parallel_index_scan_size` | 512 kB | Size threshold for considering parallel index scans |
| `parallel_leader_participation` | on | Lets the leader help execute the parallel subtree |
| `enable_parallel_hash` | on | Lets the planner consider Parallel Hash |
| `enable_parallel_append` | on | Lets the planner consider Parallel Append |

### 19.1. Inspecting Current Settings

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
SHOW parallel_setup_cost;
SHOW parallel_tuple_cost;
SHOW min_parallel_table_scan_size;
SHOW min_parallel_index_scan_size;
SHOW parallel_leader_participation;
~~~

Check setting sources (default/config/session) in `pg_settings`:

~~~sql
SELECT
    name,
    setting,
    unit,
    source,
    context
FROM pg_catalog.pg_settings
WHERE name IN (
    'max_parallel_workers_per_gather',
    'max_parallel_workers',
    'max_worker_processes',
    'parallel_setup_cost',
    'parallel_tuple_cost',
    'min_parallel_table_scan_size',
    'min_parallel_index_scan_size',
    'parallel_leader_participation'
)
ORDER BY name;
~~~

### 19.2. max_parallel_workers_per_gather

~~~sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 4;

EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events;

ROLLBACK;
~~~

Setting `4` lets the planner consider up to 4 workers per `Gather`, **without forcing 4 workers**. Cost/size may select fewer, and runtime may launch fewer.

### 19.3. Instance-Wide Limits

`max_parallel_workers` and `max_worker_processes` are shared pools across all queries and worker types. A server running 50 heavy queries concurrently cannot give 4 workers to every query if the pool cap is 8.

**When queries contend for workers**, raising `max_parallel_workers_per_gather` on one query adds zero physical CPU cores.

### 19.4. min_parallel_table_scan_size

On small tables, parallel scanning rarely pays off. Lowering this threshold lets smaller tables be costed for parallel scans, yet it remains a **costing threshold**, not a mandate.

### 19.5. min_parallel_index_scan_size

This threshold tracks expected index data scanned, not simply "launch workers if the index file exceeds 512 kB." The planner evaluates scanned volume, selectivity, and full-plan cost.

### 19.6. parallel_setup_cost and parallel_tuple_cost

The planner estimates:

- Worker startup/coordination setup cost;
- Per-tuple IPC transfer cost across `Gather`/`Gather Merge`.

If a query emits millions of raw tuples, **tuple transfer cost** can push the planner back to a serial path. With `Partial Aggregate` below `Gather`, few tuples cross the boundary, making parallel plans far more attractive.

Lowering these costs biases toward parallel plans yet risks wasting workers on small queries, hurting overall server throughput.

## 20. Testing Setting Impact Safely Without Server-Wide Edits

To avoid impacting other connections, use `SET LOCAL` inside a transaction wrapping `EXPLAIN`.

### 20.1. Scenario A — Intentionally Disabling Parallel in a Transaction

~~~sql
BEGIN;

SET LOCAL max_parallel_workers_per_gather = 0;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    COUNT(*),
    SUM(amount)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';

ROLLBACK;
~~~

In this transaction, the planner requests zero parallel workers through `Gather`. This provides a clean serial baseline.

### 20.2. Scenario B — Allowing and Encouraging Parallel in the Lab

~~~sql
BEGIN;

SET LOCAL max_parallel_workers_per_gather = 4;
SET LOCAL min_parallel_table_scan_size = '1MB';
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
SELECT
    COUNT(*),
    SUM(amount)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';

ROLLBACK;
~~~

These settings **nudge** toward a parallel plan on lab data, yet cannot guarantee one:

- The query must be parallel-safe.
- Global worker limits must allow it.
- Another plan may still be cheaper.
- Runtime may still launch fewer workers than planned.

### 20.3. Do Not Conclude from "A Ran First, B Ran Second"

Run A may warm shared buffers and OS cache; run B then looks faster even under worse settings. Or background I/O contention may skew one run.

Proper comparisons should:

1. Run multiple iterations, alternating order;
2. Capture `Execution Time`, `Buffers`, temp I/O, and launched worker counts;
3. Verify **identical SQL results**;
4. Observe CPU/I/O load and concurrency;
5. Evaluate medians/distributions rather than one run;
6. Measure **system-wide throughput**, not just one isolated query.

`EXPLAIN ANALYZE` adds measurement overhead, especially per-node timing; consider `TIMING OFF` when trimming instrumentation overhead:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*) FROM parallel_lab_273.events;
~~~

## 21. What Is ALTER TABLE ... SET (parallel_workers)?

PostgreSQL supports the table-level `parallel_workers` storage parameter to **hint worker count** for parallel scans:

~~~sql
-- Practice only in the lab schema; modifies table metadata.
ALTER TABLE parallel_lab_273.events
SET (parallel_workers = 4);
~~~

Then:

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events;
~~~

**Do not treat this reloption as "always grant 4 workers to every SELECT."** Actual worker count remains bound by:

- Whether the planner picks a parallel plan;
- `max_parallel_workers_per_gather` and instance-wide limits;
- Parallel safety;
- Runtime worker availability;
- Costs and constraints of the whole query.

### 21.1. Resetting the Reloption

~~~sql
ALTER TABLE parallel_lab_273.events
RESET (parallel_workers);
~~~

Never scatter `ALTER TABLE SET (parallel_workers)` in production without measuring concurrency, latency, worker starvation, and impact on other queries.

### 21.2. Worker Count Does Not Mean One Worker per Partition

On a monthly partitioned table, the planner may use `Parallel Append` and different distribution schemes. Never assume each worker "owns one partition" or `parallel_workers=4` scans exactly 4 partitions simultaneously.

## 22. Impact of LIMIT: Few Rows Rarely Need Many Workers

A query:

~~~sql
SELECT
    event_id,
    occurred_at
FROM parallel_lab_273.events
ORDER BY event_id
LIMIT 10;
~~~

can use a **primary-key Index Scan** and stop after 10 rows. Spawning 4 workers to scan 1 million rows and merge them makes no sense.

Conversely:

~~~sql
SELECT
    event_id,
    amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 100000;
~~~

must process/sort a major share of data. The planner considers different strategies, including parallel scan + `Gather Merge`.

### 22.1. Creating an Index Aligned with ORDER BY

~~~sql
CREATE INDEX idx_events_amount_desc_273
ON parallel_lab_273.events (
    amount DESC,
    event_id DESC
);
~~~

Then:

~~~sql
EXPLAIN
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 10;
~~~

A single sequential `Index Only Scan`/`Index Scan` along that index can be blazingly fast for small `LIMIT`. Here **a well-ordered index beats parallelism**.

### 22.2. Deep OFFSET Remains Expensive

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 20 OFFSET 500000;
~~~

To return page 25,001 via `OFFSET`, the executor must still skip half a million ordered rows. Parallel scan/`Gather Merge` never makes deep `OFFSET` free.

For deep pagination, consider **keyset pagination** on stable sort keys:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
WHERE (amount, event_id) < (500.00::numeric, 100000::bigint)
ORDER BY amount DESC, event_id DESC
LIMIT 20;
~~~

This condition fetches the next page after a known `(amount, event_id)` cursor. It matches an ordered composite B-tree and avoids scanning deep offsets. Key point: **optimizing the access path beats forcing Gather Merge**.

## 23. Parallel Safety: Can Functions and Expressions Run in Workers?

For PostgreSQL to run a node inside a parallel worker, every operation within it must be **safe for parallel execution**.

PostgreSQL functions carry one of three **parallel safety** labels:

| Declaration | Value in `pg_proc.proparallel` | Meaning |
| --- | --- | --- |
| **`PARALLEL SAFE`** | `s` | Permitted to execute inside parallel workers |
| **`PARALLEL RESTRICTED`** | `r` | Must run only in the leader, never in workers |
| **`PARALLEL UNSAFE`** | `u` | Prevents queries using it from choosing parallel plans |

Distinguish this from **volatility**:

| Label | Question answered |
| --- | --- |
| `IMMUTABLE` / `STABLE` / `VOLATILE` | When can identical inputs return different outputs, and does the function have side effects? |
| `PARALLEL SAFE` / `RESTRICTED` / `UNSAFE` | Can the function run inside parallel workers, leader-only, or not in parallel queries at all? |

A function can be `IMMUTABLE` yet `PARALLEL UNSAFE`; value immutability **does not prove transaction/session/worker safety**.

### 23.1. Inspecting Metadata via pg_proc

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_catalog.pg_get_function_identity_arguments(p.oid)
        AS arguments,
    CASE p.proparallel
        WHEN 's' THEN 'PARALLEL SAFE'
        WHEN 'r' THEN 'PARALLEL RESTRICTED'
        WHEN 'u' THEN 'PARALLEL UNSAFE'
    END AS parallel_safety,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_catalog.pg_proc AS p
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.proname IN ('lower', 'random', 'clock_timestamp', 'now')
ORDER BY p.proname, arguments;
~~~

**Never guess `proparallel` from function names alone.** Overloaded functions can have different definitions and metadata; inspect exact signatures and schemas.

### 23.2. UDFs Are Not Automatically PARALLEL SAFE

User-defined functions **default to `PARALLEL UNSAFE`** unless declared otherwise, because PostgreSQL cannot automatically prove a function's internals are worker-safe.

Example simple numeric function:

~~~sql
CREATE FUNCTION parallel_lab_273.double_amount(value NUMERIC)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT value * 2
$$;
~~~

Query:

~~~sql
EXPLAIN
SELECT SUM(parallel_lab_273.double_amount(amount))
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

This function merely multiplies a number, so `PARALLEL SAFE` is justified. Still, whether a parallel plan appears depends on the whole query and planner; simple SQL functions are often inlined so the function name won't even show in the plan tree.

### 23.3. Operations Requiring Extreme Caution

Per PostgreSQL's parallel safety rules, mark functions **UNSAFE** if they:

- Modify database state inappropriately for parallel workers;
- Alter transaction state;
- Access sequences or session/worker state unsafely;
- Depend on operations forbidden inside workers;
- Produce side effects that break when invoked concurrently by multiple workers.

Functions touching temporary tables, backend-local state, settings, cursors, or leader-only behaviors may need **RESTRICTED**, depending on the exact operation and version docs. **Never slap `SAFE` on a function just to make `Gather` appear in EXPLAIN.**

### 23.4. PARALLEL RESTRICTED vs UNSAFE

A **`PARALLEL RESTRICTED`** function can run in a parallel query **only above Gather** in the leader, never inside workers. If it must be evaluated during a scan/filter below Gather, the planner must either move the expression or reject the parallel path.

**`PARALLEL UNSAFE`** blocks parallel plan generation for the query containing it. Function labeling is a frequent reason queries on huge tables stay strictly serial.

### 23.5. Functions Calling Other Functions Must Still Be Audited

A UDF labeled `PARALLEL SAFE` that calls an unsafe side-effect function is **mislabeled**. PostgreSQL does not guarantee deep call-graph analysis to reject bad declarations.

Especially with extensions, PL/pgSQL, dynamic SQL, or evolving functions, audit:

1. Does the function read/write database tables?
2. Does it touch sequences, temporary tables, backend-local state, or cursors?
3. Does it call any external function marked UNSAFE/RESTRICTED?
4. Does it call external APIs or cause side effects?
5. Do multiple concurrent worker processes reproduce identical results?

### 23.6. Ordinary Function Queries May Stay Serial

~~~sql
EXPLAIN
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE some_custom_function(amount);
~~~

If `some_custom_function` is `PARALLEL UNSAFE`, the plan will avoid parallel workers even on millions of rows. **That is not a missing PostgreSQL feature**, but safety enforcement.

## 24. Limitations and Cases Preventing Parallel Plans

PostgreSQL does not parallelize every SQL statement. Situations restricting or disabling parallel plans include:

- Statements with **data modifications** or locking incompatible with parallel workers;
- **`PARALLEL UNSAFE`** functions or expressions;
- Accessing leader-only backend/session structures unsafe for workers;
- Cursor/partial-execution modes unsupported in parallel;
- Specific transaction, DDL, temporary table, or query constructs;
- Cost estimates too low to justify parallel overhead;
- Worker limits, transaction state, or configuration caps.

### 24.1. Do Not Assume INSERT/UPDATE Parallelizes Like SELECT

~~~sql
UPDATE parallel_lab_273.events
SET amount = amount + 1
WHERE event_type = 'purchase';
~~~

**Do not run this in the lab unless you want to rewrite 300,000 rows.** It illustrates DML, not a query to test parallel scans.

PostgreSQL enforces strict limits on parallel queries modifying data. In many versions, top-level write statements do not parallelize like pure `SELECT`s. Certain table-creation or materialized-view selects have version-specific rules; consult your version's docs.

**Never assume "if SELECT runs parallel, UPDATE with the same WHERE runs parallel too."**

### 24.2. SELECT ... FOR UPDATE

~~~sql
-- Illustrative only; do not run on large datasets:
-- SELECT *
-- FROM parallel_lab_273.events
-- WHERE event_id = 1
-- FOR UPDATE;
~~~

`FOR UPDATE` acquires row locks under transaction/backend rules that restrict parallel execution. Separate **analytical read** queries from **locking write** queries.

### 24.3. Temporary Tables and Session State

Parallel workers are not threads sharing the leader's session-private temporary state. Temporary table access restricts parallel execution; scanning a temp table generally cannot parallelize like a permanent table.

Never mark a UDF reading temporary tables as `PARALLEL SAFE` just for speed; it risks errors or wrong results.

### 24.4. CTEs and Barriers

Certain Common Table Expressions (especially data-modifying CTEs or materialized boundaries) can prevent pushing work into parallel subtrees. Yet **do not generalize "any WITH disables parallelism"**: simple read-only CTEs can be inlined/optimized and still run parallel depending on PostgreSQL version.

~~~sql
EXPLAIN
WITH recent AS (
    SELECT customer_id, amount
    FROM parallel_lab_273.events
    WHERE event_type = 'purchase'
)
SELECT COUNT(*)
FROM recent;
~~~

Read the **actual plan tree** to see where the optimizer placed the `Gather` boundary.

### 24.5. Function Safety and Row-Level Security

Row-Level Security policies, security-barrier views, policy functions, and security rules affect where predicates can execute. Never weaken security policies just to unlock a parallel plan. **Access control and correctness always come first.**

### 24.6. Parallel Query Is Not Distributed Query

Parallel workers run inside **one PostgreSQL server/instance** serving one leader; they do not automatically fan queries out across multiple physical standby servers or database shards.

~~~text
PostgreSQL Parallel Query:
  1 instance
  1 leader backend
  N parallel worker processes

Does NOT mean:
  1 query automatically distributed
  across multiple PostgreSQL replicas/shards
~~~

Multi-node distributed execution requires a different architecture (FDW/sharding/distributed engine), never inferred from `Gather`.

## 25. Performance Formula: Scaling Workers Has Limits

For intuition, split query time:

\[
T_{\text{query}}
\approx
T_{\text{setup}}
+
T_{\text{parallel work}}
+
T_{\text{transfer/merge}}
+
T_{\text{serial part}}
\]

This is an **approximate mental model**, not the exact runtime formula computed by the PostgreSQL planner.

### 25.1. Speedup Bounded by the Serial Fraction

Suppose 70% of computation splits evenly across `N` workers while 30% must stay serial. Idealized:

\[
S(N) \leq \frac{1}{0.3 + 0.7/N}
\]

With 4 workers:

\[
S(4) \leq \frac{1}{0.3 + 0.7/4}
\approx 2.11
\]

That is the **idealized** upper bound before overhead; reality adds worker startup, IPC, contention, and leader work. Four workers will never deliver a 4x speedup automatically.

### 25.2. Queries Returning Huge Row Counts

~~~sql
SELECT event_id, customer_id, amount, payload
FROM parallel_lab_273.events;
~~~

If the client consumes all 1 million rows with wide payloads, **the leader and client connection** become the bottleneck. Faster worker scans barely shorten end-to-end time because every tuple still ships through the leader.

### 25.3. Aggregation Cuts Tuple Transfer Overhead

~~~sql
SELECT COUNT(*), SUM(amount)
FROM parallel_lab_273.events;
~~~

With `Partial Aggregate`, each worker sends one tiny partial state instead of millions of rows. Aggregation queries therefore benefit far more from parallelism than raw `SELECT *` dumps.

### 25.4. I/O Bottleneck

If the table is uncached and storage throughput is saturated, adding more readers **cannot increase total I/O bandwidth**. Workers may even contend with autovacuum, checkpointer, and other queries.

### 25.5. CPU Bottleneck

If an 8-core server runs 10 concurrent queries each wanting 4 workers + 1 leader, 50 active processes compete for 8 cores. Context switching and cache thrashing degrade both throughput and latency.

### 25.6. Worker Starvation

A query sees `Workers Launched: 4` when idle, yet launches 0–1 workers during peak hours. Always log **actual launched worker counts** during benchmarks rather than comparing Execution Times blindly across differing resource states.

## 26. Memory: work_mem Is Per-Operation, Not Per-Query

`work_mem` is not a total RAM cap for one SELECT. Sorts, hashes, and other operations allocate memory independently per participant.

Example:

~~~text
Query with Gather Merge:

  Worker 1: Sort -> uses per-operation work_mem
  Worker 2: Sort -> uses per-operation work_mem
  Worker 3: Sort -> uses per-operation work_mem
  Leader  : may also execute partial Sort
  Leader  : Gather Merge + upper nodes
~~~

Consequently, raising `max_parallel_workers_per_gather` alongside `work_mem` **multiplies peak RAM demand**. Hash operations also apply rules like `hash_mem_multiplier`.

### 26.1. Observing Sort Spills to Disk

In `EXPLAIN ANALYZE`:

~~~text
Sort Method: quicksort  Memory: ...
~~~

indicates an in-memory sort; whereas:

~~~text
Sort Method: external merge  Disk: ...
~~~

indicates temporary disk spills. Parallel plans may show **per-worker** sort stats because each worker sorts its own slice.

### 26.2. A Safe Test Configuration

~~~sql
BEGIN;

SET LOCAL work_mem = '32MB';
SET LOCAL max_parallel_workers_per_gather = 3;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 100000;

ROLLBACK;
~~~

In the lab, changing `work_mem` can change Sort Method and plan choice. **Never assume raising to gigabytes is always safe**: concurrent parallel queries can exhaust RAM and trigger OOM/swapping.

### 26.3. Temp Files and Query Logs

With proper monitoring, these signals:

- `Buffers: temp read=... written=...`;
- `Sort Method` and `Disk` size;
- `pg_stat_database.temp_files`/`temp_bytes`;
- `log_temp_files` if enabled by DBAs;

explain why a parallel Sort plan takes time. Cross-check against real queries and overall server load.

## 27. Reading actual rows, loops, and Per-Worker Statistics

`EXPLAIN (ANALYZE, VERBOSE)` on a parallel plan can look like:

~~~text
Gather (actual time=... rows=300000 loops=1)
  Workers Planned: 2
  Workers Launched: 2
  -> Parallel Seq Scan on events
       (actual time=... rows=100000 loops=3)
       Filter: (event_type = 'purchase')
       Rows Removed by Filter: ...
       Worker 0: actual time=... rows=...
       Worker 1: actual time=... rows=...
~~~

### 27.1. actual rows Beneath Gather

When a node executes multiple times, `rows` in EXPLAIN ANALYZE generally shows the **average rows per execution**, while `loops` is execution count. On parallel nodes, participant runs aggregate into these summary numbers.

Hypothetical example:

~~~text
Parallel Seq Scan: actual rows=100000 loops=3
Gather:            actual rows=300000 loops=1
~~~

This gives approximate scan totals, yet **never blindly multiply `rows × loops` across every node and call it unique query rows**, because:

- `Filter` discards rows;
- Nodes can be rescanned;
- Aggregation collapses many inputs into fewer outputs;
- Workers and leader may handle uneven shares;
- `loops` does not always equal `Workers Launched + 1`.

### 27.2. Workers Planned/Launched Appears Only on Gather

`Workers Planned` and `Workers Launched` appear on `Gather`/`Gather Merge`, not every scan node. Per-worker timings and row counts appear on nodes beneath `Gather` when `ANALYZE, VERBOSE` is enabled.

### 27.3. Why Might One Worker Process More Rows?

Possible reasons:

- Staggered worker startup times;
- Leader busy draining tuples;
- CPU/I/O contention;
- Uneven cache hits or storage response;
- Skewed data selectivity across blocks;
- Inherent unevenness in work-stealing or node mechanics.

Mild imbalance is not a bug. If worker 0 does nearly all the work while others sit near 0 and the query is slow, investigate before adding more workers.

### 27.4. Loops on Partial Aggregate

~~~text
Finalize Aggregate
  -> Gather (rows=3)
       -> Partial Aggregate (rows=1 loops=3)
            -> Parallel Seq Scan ...
~~~

`Partial Aggregate` emits **one aggregate state per participant** when no `GROUP BY` is present; hence rows crossing `Gather` match participant count rather than 300,000 purchase rows.

### 27.5. Cost and Time Use Different Units

~~~text
cost=1000.00..25000.00
actual time=1.234..120.567
~~~

`cost` is a **planner estimate unit**, not milliseconds. `actual time` is measured duration during EXPLAIN ANALYZE. Never subtract cost from actual time to claim a plan is broken.

## 28. Identifying Bottlenecks at the Leader

Because the leader sits above `Gather` and ships final rows up, worker scans can finish fast while total runtime stays high:

~~~text
Parallel Seq Scan: plenty of workers, rows read fast
             |
           Gather: must drain huge row stream
             |
        Sort / Join / Aggregate above
             |
           Client: consumes data slowly
~~~

### 28.1. Symptoms Worth Investigating

- Huge row volumes crossing `Gather`;
- `Gather` or nodes above it dominate elapsed time;
- Leader Sort after `Gather` spills to disk;
- Leader CPU runs far hotter than workers;
- Query uses `SELECT *` with wide payloads and slow client consumption;
- Workers finish early while the query lingers on upper steps;
- Overall throughput drops as per-gather workers increase.

### 28.2. Fixes Usually Better Than Adding Workers

- Push selective `WHERE` filters below `Gather` where planner/semantics permit;
- Use partial aggregation instead of shipping millions of rows to the leader;
- Add an index eliminating large sorts;
- Select only genuinely needed columns;
- Use `LIMIT`/keyset pagination aligned with business rules;
- Improve join predicates, indexes, or statistics;
- Optimize client/server networking and batch fetching;
- Throttle concurrent heavy queries if the instance is saturated.

**There is no magic setting to "force Aggregate below Gather."** Check whether the aggregate supports partial mode, predicates are parallel-safe, and group counts/costs align.

## 29. Monitoring Running Parallel Workers

### 29.1. pg_stat_activity

On modern PostgreSQL versions with `leader_pid` in `pg_stat_activity`, query:

~~~sql
SELECT
    pid,
    leader_pid,
    backend_type,
    state,
    application_name,
    wait_event_type,
    wait_event,
    query
FROM pg_catalog.pg_stat_activity
WHERE backend_type = 'parallel worker'
   OR leader_pid IS NOT NULL
ORDER BY leader_pid NULLS FIRST, pid;
~~~

If zero rows return, likely **no parallel query is running at that instant**. Workers live for the duration of a query execution, not as a permanent dedicated worker pool per connection.

### 29.2. Per-Worker Data in EXPLAIN

To analyze work distribution for **one specific query**, `EXPLAIN (ANALYZE, VERBOSE, BUFFERS)` is far more informative than a point-in-time process snapshot.

### 29.3. Privilege Limits

Not every role can view query texts and other sessions' details. Monitoring roles should use policy-appropriate grants (e.g., `pg_monitor` where suitable), never superuser just to inspect `pg_stat_activity`.

### 29.4. Distinct Backend Types

Distinguish:

- `client backend` — client-serving connection;
- `parallel worker` — parallel query worker;
- `autovacuum worker` — table maintenance;
- `background writer` / `checkpointer` / `walwriter` — system processes.

Do not count all worker processes as parallel query workers when auditing `max_worker_processes`.

## 30. Tuning Under Concurrent Requests

A SELECT can fly in dev with `max_parallel_workers_per_gather=8` yet slow down production under hundreds of concurrent requests.

### 30.1. Concurrency and CPU Budget

Suppose an instance has 8 CPU cores and 10 heavy concurrent queries each wanting 4 workers:

~~~text
10 leaders + 40 parallel workers = 50 runnable processes
on 8 CPU cores (hypothetical demand).
~~~

Global limits cap launched workers, yet **overly permissive settings** still risk CPU contention, cache thrashing, and context switching.

### 30.2. Single-Query Latency vs System Throughput

A change may:

- Cut one isolated query from 2 seconds to 1 second;
- Yet drop overall throughput from 100 req/s to 70 req/s when concurrent queries fight over workers and RAM.

Tune based on SLAs, throughput, and latency under realistic load—**never an isolated, uncontended EXPLAIN ANALYZE**.

### 30.3. Worker Starvation and Unstable Latency

If a query expects 4 workers yet gets 0 at peak hours, latency swings wildly. Practical mitigations:

- Set conservative per-gather limits;
- Cap concurrency of heavy analytical reports;
- Route heavy reads to read replicas or analytics engines when architecture allows;
- Shift recurring reports to pre-aggregated or materialized views;
- Optimize queries, indexes, and filters before raising worker counts;
- Measure actual `Workers Launched`.

### 30.4. Plans Can Change After ANALYZE

The planner uses statistics. After `ANALYZE` or data shifts, PostgreSQL may switch from `Parallel Seq Scan` to `Index Scan` or back. **A plan change after data changes is not automatically a regression**—compare latency, buffers, and result accuracy.

### 30.5. Do Not Treat Gather Merge as a "Tuning Flag"

There is no `SET enable_gather_merge=on` magic bullet for all `ORDER BY` queries. The planner picks `Gather Merge` when it finds **viable sorted partial paths**. Optimize indexes, sort keys, query shape, costs, and workload instead of hunting for a toggle.

## 31. Common Pitfalls When Reading Parallel Plans

| Misconception | Fact |
| --- | --- |
| "Parallel scan = every worker scans the whole table." | Parallel-aware scans coordinate disjoint block/index slices |
| "Gather preserves primary-key order." | `Gather` **makes no ordering guarantee** |
| "Gather Merge always needs a giant leader Sort." | It merges **already-sorted streams**; Sort sits below Gather Merge |
| "Gather Merge is Merge Join." | One merges sorted worker streams; one joins two relations |
| "ORDER BY always uses Gather Merge." | May use serial index scan, Sort above Gather, etc. |
| "LIMIT 10 needs 10 workers to be fast." | A single index scan stopping early is cheaper |
| "Workers Planned: 4 means 4 actually ran." | Check `Workers Launched` in `ANALYZE` |
| "Workers Launched < Planned means data corruption." | Usually runtime/global worker availability limits |
| "loops always equals worker count." | Leader may participate, and nodes can rescan |
| "rows on Parallel Seq Scan is total query rows." | Account for loops/worker stats and upper nodes |
| "Every node below Gather is parallel-aware." | Many nodes are parallel-safe without splitting work themselves |
| "Having an index means Parallel Index Scan is chosen." | Costs/selectivity may favor another scan |
| "Index Only Scan never reads the heap." | Visibility map governs; check `Heap Fetches` |
| "Every worker runs an identical full Bitmap Index Scan." | Bitmap is normally built once; heap scanning runs in parallel |
| "Bitmap Heap Scan keeps index order." | Provides no ordering guarantee |
| "COUNT DISTINCT simply sums worker partial counts." | Cross-worker duplicates require global deduplication, limiting partial mode |
| "All SUM/aggregates support Partial/Finalize." | Aggregates must implement partial mode |
| "Parallel query = distributed across replicas." | It runs across processes inside one PostgreSQL instance |
| "More workers is always faster." | Startup, memory, leader, and CPU/I/O contention exist |
| "work_mem is total RAM per query." | Multiple sort/hash ops across participants hold separate budgets |
| "SET parallel_setup_cost=0 forces parallel plans." | Only alters cost estimates, cannot bypass safety/limits |
| "An IMMUTABLE UDF is PARALLEL SAFE." | Volatility and parallel safety are independent properties |
| "UDFs default to running in workers." | UDFs default to `PARALLEL UNSAFE` unless declared otherwise |
| "EXPLAIN ANALYZE only previews without running." | `ANALYZE` **executes the SQL** |
| "Planner cost=10000 means 10,000 ms." | Cost is a model unit, not time |
| "Workers finished SELECT * fast, so network doesn't matter." | Leader still sends all tuples to the client |
| "Parallel tuning just means raising max_parallel_workers." | Indexes, filters, query shape, and concurrency matter equally |
| "ORDER BY guarantees stable pagination even on duplicate keys." | Add a unique tiebreaker key |
| "Seq Scan on a tiny table proves parallel index is broken." | Sequential scan on tiny tables is optimal |

## 32. Diagnostic Scenarios: Which Node Do You Check First?

### Scenario A — Slow COUNT Query with Gather

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 4
       Workers Launched: 4
       -> Partial Aggregate
            -> Parallel Seq Scan
~~~

Questions to answer:

1. How many buffers does `Parallel Seq Scan` read? Is I/O heavy?
2. Is work balanced across participants?
3. Did `Partial Aggregate` shrink tuples sent to `Gather` as expected?
4. Did adding workers cut elapsed time or merely burn CPU?
5. If run frequently, would an index, filter, or materialized summary help more?

**How to read:** Because `Gather` receives only tiny partial aggregates, this parallel plan is usually efficient if the bottleneck is scanning/compute rather than leader transfer.

### Scenario B — Slow ORDER BY Query with External Merge Sort

~~~text
Limit
  -> Gather Merge
       Workers Planned: 4
       -> Sort
            Sort Key: amount DESC, event_id DESC
            Sort Method: external merge  Disk: ...
            -> Parallel Seq Scan
~~~

Factors to weigh:

- How many rows are workers sorting? Can `WHERE`/`LIMIT` reduce them?
- Can a composite B-tree index matching `ORDER BY`/filters skip sorting altogether?
- Is `work_mem` safe for **overall concurrency**, not just one worker?
- Does an index on `(amount DESC, event_id DESC)` exist yet?
- Is deep `OFFSET` forcing excessive row processing?

**Never blindly raise `work_mem` very high** when many similar queries run concurrently.

### Scenario C — Planned 4, Launched 0

~~~text
Gather
  Workers Planned: 4
  Workers Launched: 0
  -> Parallel Seq Scan ...
~~~

The planner intended parallel execution, yet runtime **launched zero workers**. Check worker pool limits, active concurrent queries/workers, and runtime state. Do not start by adding indexes or raising `work_mem` when the cause may be **worker starvation**.

### Scenario D — Query Has ORDER BY Yet Shows Gather (Not Gather Merge)

~~~text
Sort
  Sort Key: occurred_at DESC
  -> Gather
       -> Parallel Seq Scan ...
~~~

PostgreSQL did **not** ignore `ORDER BY`. The `Sort` above `Gather` guarantees global order. Check whether that leader Sort consumes heavy RAM/temp I/O, and whether `Gather Merge` or an index-ordered scan costs less.

### Scenario E — Query on a Large Table Still Uses Seq Scan

~~~text
Aggregate
  -> Seq Scan on events
~~~

Check:

- Is `max_parallel_workers_per_gather` set to 0?
- Is a UDF defaulting to `PARALLEL UNSAFE`?
- Does query shape or transaction mode block parallel execution?
- Are statistics stale or size estimates too low?
- Are `parallel_setup_cost`/`parallel_tuple_cost` high relative to workload?
- Are global worker limits low?
- **Most importantly:** does the serial query actually breach SLAs?

If the query finishes in 2 ms, **skipping `Gather`** is completely sensible.

### Scenario F — Parallel Index Only Scan with High Heap Fetches

~~~text
Parallel Index Only Scan using idx_events_customer_273
  Heap Fetches: 200000
~~~

Inspect visibility map/all-visible state, UPDATE frequency, long-running transactions holding snapshots, and VACUUM status. Adding 4 more workers will not eliminate heap fetches; **visibility state** is independent of worker parallelism.

## 33. Practice Exercises

Exercises run on schema `parallel_lab_273`. If an `EXPLAIN` differs from the predicted node, **that does not mean your exercise is wrong**. Separate **correct SQL results** from **environment-dependent plans**, and explain why the planner chose differently.

### Exercise 1 — Reading a Basic Plan Tree

Given:

~~~text
Finalize Aggregate
  -> Gather
       Workers Planned: 2
       -> Partial Aggregate
            -> Parallel Seq Scan on events
~~~

Describe each node's role **bottom-up**.

**Hint:** scan data → compute local aggregate states → Gather ships partial states → Finalize combines them.

### Exercise 2 — Explaining Block Distribution

A table has 10,000 heap blocks and uses `Parallel Seq Scan` with 3 workers plus the leader.

**Question:** Does PostgreSQL assign exactly 2,500 static blocks to each process? Why does dynamic coordination beat static partitioning?

### Exercise 3 — Counting Purchases

Run:

~~~sql
SELECT COUNT(*)
FROM parallel_lab_273.events
WHERE event_type = 'purchase';
~~~

**Expected on sample data:** 300,000.

Then run `EXPLAIN` and check whether `Partial Aggregate`/`Gather` appear.

### Exercise 4 — Checking Parallel Settings

Run:

~~~sql
SHOW max_parallel_workers_per_gather;
SHOW max_parallel_workers;
SHOW max_worker_processes;
~~~

**Question:** If `per_gather=4` yet `max_parallel_workers=2`, is a query guaranteed to launch 4 workers?

**Answer:** No, due to global limits and worker availability.

### Exercise 5 — Planned vs Launched

Read:

~~~text
Workers Planned: 4
Workers Launched: 2
~~~

**Question:** Which line reflects planner intent, and which reflects executor reality? List three reasons launched can be lower.

### Exercise 6 — Comparing EXPLAIN and EXPLAIN ANALYZE

Write both commands:

~~~sql
EXPLAIN SELECT COUNT(*) FROM parallel_lab_273.events;

EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT COUNT(*) FROM parallel_lab_273.events;
~~~

**Question:** Which actually executes the query? When must `ANALYZE` be avoided due to write side effects?

### Exercise 7 — Toggling Parallel with SET LOCAL

In two lab transactions, run the same `COUNT(*)` with `max_parallel_workers_per_gather=0` and `=4`. Compare plan, timing, and buffers.

**Takeaway to state:** allowing 4 workers does not guarantee the planner or runtime uses all 4.

### Exercise 8 — Gather Does Not Guarantee Order

Given two workers:

~~~text
A: 1,3,5
B: 2,4,6
~~~

Give one **row-set-valid** output from `Gather` that is **unsorted**. Explain why SQL requires `ORDER BY` when order is needed.

### Exercise 9 — Gather Merge

Using the same two sorted streams from Exercise 8, what does `Gather Merge` ASC emit?

**Answer:** `1,2,3,4,5,6`.

### Exercise 10 — Sort Above Gather vs Sort Below Gather Merge

Sketch two trees:

~~~text
Sort -> Gather -> Parallel Seq Scan
Gather Merge -> Sort -> Parallel Seq Scan
~~~

**Question:** In which does the leader perform one global Sort, and in which do participants sort before merging? Why can both be valid?

### Exercise 11 — ORDER BY with Ties

On sample data with many duplicate `amount` values, compare:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC
LIMIT 20;
~~~

against:

~~~sql
SELECT event_id, amount
FROM parallel_lab_273.events
ORDER BY amount DESC, event_id DESC
LIMIT 20;
~~~

**Question:** Which version has a deterministic tiebreaker? Does `Gather Merge` add a tiebreaker automatically?

### Exercise 12 — Adding an Order-Aligned Index

Create B-tree `(amount DESC, event_id DESC)` and run `EXPLAIN` on `ORDER BY amount DESC, event_id DESC LIMIT 10`.

**Question:** Why can a serial `Index Scan`/`Index Only Scan` beat parallel scan + sort for a tiny `LIMIT`?

### Exercise 13 — Parallel Index Scan

Create index `(occurred_at)` and run `EXPLAIN` on a time-range query.

**Question:** Where do `Index Scan`, `Parallel Index Scan`, and `Parallel Seq Scan` differ in access path and work splitting?

### Exercise 14 — Parallel Index Only Scan

On B-tree `(customer_id)`, run `EXPLAIN (ANALYZE, BUFFERS)` for a count over a customer ID range.

**Question:** If the plan shows `Parallel Index Only Scan` with high `Heap Fetches`, did PostgreSQL mislabel the node?

**Answer:** No; inspect the visibility map and heap visibility checks.

### Exercise 15 — Parallel Bitmap Heap Scan

Given:

~~~text
Gather
 -> Parallel Bitmap Heap Scan
      Recheck Cond: ...
      -> Bitmap Index Scan
~~~

**Question:** Which phase coordinates multiple workers, and who usually builds the bitmap? Why doesn't every worker build its own separate bitmap?

### Exercise 16 — Bitmaps and Ordering

A query filters via `Bitmap Heap Scan` yet requires `ORDER BY customer_id`. Is a `Sort` needed?

**Hint:** bitmap scans guarantee no order; PostgreSQL must satisfy ordering via Sort or another ordered scan.

### Exercise 17 — Lossy Bitmap

Read `EXPLAIN ANALYZE` showing:

~~~text
Heap Blocks: exact=... lossy=...
Rows Removed by Index Recheck: ...
~~~

**Question:** Why do lossy pages increase when bitmap memory runs low? How does `Recheck Cond` preserve correctness?

### Exercise 18 — Partial Aggregate

Suppose three participants count purchases as `95,000`, `110,000`, and `95,000`.

**Question:** What does `Finalize Aggregate` return? How many partial count rows cross `Gather` instead of how many purchase rows?

**Answer:** 300,000; conceptually three local count rows instead of 300,000 purchase rows.

### Exercise 19 — COUNT(DISTINCT)

Why can't you simply sum `COUNT(DISTINCT customer_id)` from two workers if a customer appears in both?

**Hint:** duplicates span partitions, requiring global deduplication or appropriate aggregation states.

### Exercise 20 — GROUP BY and Gather Merge

Run:

~~~sql
EXPLAIN
SELECT customer_id, COUNT(*)
FROM parallel_lab_273.events
GROUP BY customer_id
ORDER BY customer_id;
~~~

**Exercise:** If `Finalize GroupAggregate -> Gather Merge` appears, explain why inputs must be sorted by `customer_id`. If `HashAggregate + Sort` appears instead, why is that still valid?

### Exercise 21 — Partial HashAggregate

Given 1,000,000 events across only 10,000 customer IDs, why does local aggregation cut tuples shipped from workers to `Gather`? When group count approaches row count, how does that benefit change?

### Exercise 22 — Parallel Join

Run `EXPLAIN` joining `events` with `customers` and aggregating by `segment`.

**Question:** Distinguish `Hash Join` under `Gather` from `Parallel Hash Join`. Which node splits the scan source?

### Exercise 23 — Checking Function Safety

Query `pg_proc` to inspect `proparallel` on system functions. Can a UDF with `provolatile='i'` and `proparallel='u'` run in parallel workers?

**Answer:** No; immutability and parallel safety are separate attributes.

### Exercise 24 — Default UDF Behavior

Create a SQL function multiplying a number **without `PARALLEL SAFE`**. Compare its metadata against `parallel_lab_273.double_amount` declared safe.

**Question:** Why do UDFs default to `UNSAFE`? What must you audit before changing one to `SAFE`?

### Exercise 25 — Temp Tables / Parallel Workers

A developer wants a UDF reading the leader's session temporary table and marks it `PARALLEL SAFE`.

**Exercise:** Explain why that is wrong, and why `PARALLEL RESTRICTED` or redesigning data flow fits better depending on the function.

### Exercise 26 — Per-Operation work_mem

A query uses 4 workers, each running its own Sort and Hash, plus leader nodes. Why can't total peak RAM equal **one** `work_mem` value? Which metric confirms a sort spilled to disk?

### Exercise 27 — Worker Starvation

In an idle lab, a query launches 4 workers and finishes in 0.8s. At peak hours, the same SQL and plan launch only 1 worker and take 2.4s.

**Question:** Which runtime factor explains the gap? Why can't you tune solely from `Workers Planned`?

### Exercise 28 — CPU Bottlenecks and Throughput

An 8-core instance runs 20 concurrent queries. The team wants to set `max_parallel_workers_per_gather=8` so every query runs faster.

**Exercise:** List at least five risks/factors to measure: instance-wide workers, CPU contention, memory, Gather overhead, I/O, throughput vs latency, and worker starvation.

### Exercise 29 — SET LOCAL and Transaction Scope

Run a transaction:

~~~sql
BEGIN;
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;
EXPLAIN SELECT COUNT(*) FROM parallel_lab_273.events;
ROLLBACK;
~~~

**Question:** After `ROLLBACK`, do those `SET LOCAL` values persist in the session?

**Answer:** No; they apply only within that transaction.

### Exercise 30 — Deep OFFSET

Explain why `ORDER BY amount DESC, event_id DESC LIMIT 20 OFFSET 500000` must process/skip huge row volumes, and why **keyset pagination** works better.

### Exercise 31 — Reading actual rows / loops

Given:

~~~text
Gather actual rows=300000 loops=1
Parallel Seq Scan actual rows=100000 loops=3
~~~

**Question:** Is `rows=100000` on the scan total query rows or average per node execution? Why shouldn't you blindly treat `rows × loops` everywhere as "unique rows of the SQL query"?

### Exercise 32 — Leader Bottleneck

A `Parallel Seq Scan` runs fast, yet `SELECT payload` returning 2 million rows through `Gather` crawls.

**Question:** Besides adding workers, what fixes exist? Hints: trim columns/rows, aggregate, paginate, index, improve client throughput.

### Exercise 33 — Cost vs Actual Time

Given:

~~~text
cost=1000.00..20000.00
actual time=0.500..600.000
~~~

**Question:** Can you say "PostgreSQL predicted 20 seconds"?

**Answer:** No; `cost` is a planner estimate unit, not milliseconds.

### Exercise 34 — Parallel Query vs Replication

A report uses `Gather Merge`. Does it automatically run across two standby replicas? Why does this differ from read replicas or distributed SQL?

### Exercise 35 — Comprehensive Code Review Scenario

A teammate proposes:

~~~sql
SET max_parallel_workers_per_gather = 16;
SET work_mem = '1GB';

SELECT *
FROM parallel_lab_273.events
ORDER BY amount DESC
LIMIT 50 OFFSET 200000;
~~~

Point out at least eight concerns to review:

1. How many CPU cores and instance-wide workers does the server have?
2. How many concurrent queries run?
3. Can `work_mem` multiply across nodes and participants?
4. Why does `SELECT *` ship heavy payloads?
5. Is there an index matching `ORDER BY`?
6. How does deep `OFFSET` inflate work?
7. Does `ORDER BY amount` without a tiebreaker break pagination consistency?
8. What are Planned vs Launched workers?
9. Have plan/buffers/temp I/O been benchmarked on realistic data?
10. Should it switch to keyset pagination and explicit column projection?

**Guided answer:** Optimize SQL and access paths first; never crank up workers and `work_mem` simply to "force parallel execution."

## 34. Practical Workflow for Analyzing a Parallel Plan

A repeatable workflow for performance investigations:

<escape>**Step 1 — Clarify the required SQL result.**</escape> Is there `ORDER BY`? Does `LIMIT` need a tiebreaker? Is the query returning excessive columns/rows?

<escape>**Step 2 — Read the plan bottom-up.**</escape> Is access `Parallel Seq Scan`, `Parallel Index Scan`, `Parallel Index Only Scan`, or `Parallel Bitmap Heap Scan`? Are `Filter` or `Recheck Cond` present?

<escape>**Step 3 — Find the Gather boundary.**</escape> Which nodes run below `Gather` in the parallel portion, and which run on the leader above?

<escape>**Step 4 — Distinguish Gather vs Gather Merge.**</escape> Is ordering needed? Are input streams sorted? Does `Sort` sit below `Gather Merge` or above `Gather`?

<escape>**Step 5 — Identify Partial / Finalize.**</escape> Is aggregation partially distributed? How many partial rows cross to the leader?

<escape>**Step 6 — Check Workers Planned / Launched.**</escape> Were workers starved at runtime? Did the leader participate? Is work balanced?

<escape>**Step 7 — Inspect actual stats.**</escape> `rows`, `loops`, filters, `Heap Fetches`, buffer hits/reads, temp I/O, worker sort methods, and `Execution Time`.

<escape>**Step 8 — Pinpoint the largest bottleneck.**</escape> Scan I/O, sorting, lossy bitmaps, worker startup, leader transfer/merge, hashing, client output, or concurrency?

<escape>**Step 9 — Pick the smallest evidence-backed change.**</escape> Query rewrite, index, `ANALYZE` statistics, trimmed output, partial aggregation, worker limits, or memory.

<escape>**Step 10 — Re-measure on representative workloads.**</escape> Compare serial vs parallel across multiple runs, monitoring both latency and throughput, with a rollback plan if regressions occur.

### 34.1. Sample Benchmark Recording Table

| Attribute to record | Run A | Run B |
| --- | --- | --- |
| Query/parameters | Identical SQL | Identical SQL |
| Config | Parallel off | Parallel allowed |
| Plan root | `Aggregate` | `Finalize Aggregate` |
| Gather type | None | `Gather` |
| Workers planned | 0 | Per EXPLAIN |
| Workers launched | 0 | Per ANALYZE |
| Execution Time | Measured actual | Measured actual |
| Buffers shared hit/read | Measured actual | Measured actual |
| Temp disk | Measured actual | Measured actual |
| CPU / concurrency | Observed | Observed |
| SQL result | Must match | Must match |

Never fill in "default baseline" times. Always record real measurements from your test environment.

### 34.2. Decisions by Workload Type

| Workload | Primary considerations |
| --- | --- |
| `COUNT(*)` on large table | Parallel Seq/Index Only Scan + Partial Aggregate |
| `GROUP BY` on heavy data | Partial/Finalize Aggregate, Hash vs Group, Gather vs Gather Merge |
| Small `ORDER BY ... LIMIT` | Ordered B-tree to skip unnecessary sorts and parallel startup |
| Large `ORDER BY` result | `Gather Merge` + local sorts vs `Gather` + global sort |
| Index range with moderate/many rows | Parallel Index Scan vs Bitmap Heap Scan by selectivity |
| Customer ID lookup with good B-tree | Check Index Scan / Index Only Scan and visibility map |
| Query returning millions of rows | Leader transfer / client network bottleneck; trim output |
| Many concurrent analytics queries | Instance-wide worker quota, RAM, and system throughput |
| UDF in WHERE | Inspect `pg_proc.proparallel` and audit parallel safety |
| Queries using temp tables / DML | Check parallel restrictions for that statement class |

## 35. Official PostgreSQL Documentation

Always consult documentation for your **exact major version**, since parallel planner capabilities, `EXPLAIN` metrics, and worker behaviors evolve:

- [How Parallel Query Works](https://www.postgresql.org/docs/current/how-parallel-query-works.html): leader/workers, Gather and Gather Merge, parallel execution overview.
- [Parallel Plans](https://www.postgresql.org/docs/current/parallel-plans.html): partial plans, Parallel Sequential Scan, Parallel Bitmap Heap Scan, Parallel Index/Index Only Scan, parallel joins and aggregates.
- [When Can Parallel Query Be Used?](https://www.postgresql.org/docs/current/when-can-parallel-query-be-used.html): conditions restricting parallel plans.
- [Parallel Safety](https://www.postgresql.org/docs/current/parallel-safety.html): `PARALLEL SAFE`, `RESTRICTED`, `UNSAFE`, and UDF labeling.
- [Parallel Query](https://www.postgresql.org/docs/current/parallel-query.html): Parallel Query chapter overview.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): inspecting plans, `ANALYZE`, `BUFFERS`, `VERBOSE`, and `SETTINGS`.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): costs, actual rows/loops, scan methods, sorting, and plan analysis.
- [Planner Cost Constants](https://www.postgresql.org/docs/current/runtime-config-query.html#RUNTIME-CONFIG-QUERY-CONSTANTS): `parallel_setup_cost`, `parallel_tuple_cost`, and cost parameters.
- [Resource Consumption](https://www.postgresql.org/docs/current/runtime-config-resource.html): `max_parallel_workers_per_gather`, `max_parallel_workers`, `max_worker_processes`, `work_mem`.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): declaring parallel safety and volatility on UDFs.
- [pg_stat_activity](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-PG-STAT-ACTIVITY-VIEW): backend types, `leader_pid`, and observing workers.
- [Indexes and ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html): index ordering, `ORDER BY`, and `LIMIT` effectiveness.
- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html): visibility map, heap fetches, `INCLUDE`, and index-only performance.
- [Bitmap Scan / EXPLAIN examples](https://www.postgresql.org/docs/current/using-explain.html): `Bitmap Index Scan`, `Bitmap Heap Scan`, and cost-based plan selection.

Links under `/docs/current/` point to the current stable release. If your system runs a specific PostgreSQL version, check the **matching version's documentation** before applying syntax or configuration limits.

## 36. Summary

**Parallel queries** let PostgreSQL assign multiple processes to **one query** when the workload is large enough and operations are safe to parallelize. The leader serves the client; parallel workers collaborate on a **partial plan** where **parallel-aware** nodes like `Parallel Seq Scan`, `Parallel Index Scan`, `Parallel Index Only Scan`, and `Parallel Bitmap Heap Scan` divide work instead of redundantly scanning full relations.

At the parallel boundary, **`Gather`** collects results to the leader **without guaranteeing global order**. **`Gather Merge`** merges streams pre-sorted by the same sort keys, preserving order for `ORDER BY` or `Finalize GroupAggregate`. Neither resolves duplicate-key ties automatically: when reproducible ordering is needed, specify a complete `ORDER BY`.

For `COUNT`/`SUM` and partial-mode aggregates, **`Partial Aggregate -> Gather -> Finalize Aggregate`** sharply cuts tuples crossing to the leader. Meanwhile, queries returning millions of rows or needing massive sorts can still bottleneck on **IPC, leader CPU, memory, I/O, and client output**; adding workers does not guarantee faster execution.

When reading `EXPLAIN`, check **`Workers Planned`** and **`Workers Launched`** separately alongside `actual rows`, `loops`, buffer/temp I/O, `Heap Fetches`, `Sort Method`, and the `Gather` boundary. Audit **`PARALLEL SAFE`** labels on UDFs and statement limits before trying to coax workers from the planner.

**Practical principle:** optimize **correctness and access paths** first, then tune workers, costs, and memory using real measurements. Parallel scans, `Gather`, and `Gather Merge` are not "more is always faster" switches—they are components of a cost-optimized plan designed to **partition work cleanly, coordinate results accurately, and keep system-wide overhead in check**.
