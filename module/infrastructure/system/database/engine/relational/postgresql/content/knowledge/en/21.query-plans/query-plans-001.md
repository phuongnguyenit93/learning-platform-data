# EXPLAIN, EXPLAIN ANALYZE, and Considerations for Statements with Side Effects in PostgreSQL

A SQL query that returns the correct result can still run slowly because it scans too many rows, chooses an unsuitable join method, sorts large datasets, misestimates row counts, or reads many pages from storage. To see how PostgreSQL **intends** to run a query, we use `EXPLAIN`. To see how many milliseconds the nodes take and how many rows they process when **actually running**, we use `EXPLAIN ANALYZE`.

The two command names look similar, but they have a huge operational difference:

```sql
-- Only plans, does NOT execute the UPDATE statement in the normal case:
EXPLAIN
UPDATE orders
SET status = 'cancelled'
WHERE order_id = 100;

-- Actually runs the UPDATE to measure it:
EXPLAIN ANALYZE
UPDATE orders
SET status = 'cancelled'
WHERE order_id = 100;
```

When a command modifies data or calls a function with a **side effect**, adding `ANALYZE` is no longer a "harmless preview" operation. `EXPLAIN ANALYZE` **executes the statement**, including writes, triggers, and any accompanying effects. Even when tested inside a transaction followed by `ROLLBACK`, not **every effect** is undone by PostgreSQL: for example, values allocated through a sequence (`nextval()`), changes outside the database, or network service calls do not automatically revert on rollback.

This lesson belongs to the **Query Plans** chapter in the *Database Engine Relational PostgreSQL* module, focusing on two closely linked competencies:

1. **Reading and explaining execution plans**: `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, `Nested Loop`, `Hash Join`, `Merge Join`, `Sort`, `Aggregate`, estimated costs, row counts, execution times, loop counts, and buffer statistics.
2. **Using EXPLAIN safely**: distinguishing planning from execution; protecting data when measuring `INSERT`, `UPDATE`, `DELETE`, and `MERGE`; understanding `ROLLBACK`, sequences, triggers, functions with side effects, external I/O, and commit/transaction scenarios.

After this lesson, you will be able to set up a test environment, explain a plan bottom-up, recognize signs of misestimation or resource-intensive queries, and avoid turning a "performance measurement" into a data deletion/modification incident.

> **Safety principle:** Only run examples that write data on a dedicated `explain_lab` schema in a practice database. When you want to inspect a plan **without executing DML**, use `EXPLAIN` **without** `ANALYZE`. For functions that send emails, transfer money, make HTTP calls, advance sequences, or triggers with external side effects, do **not** treat `BEGIN; EXPLAIN ANALYZE ...; ROLLBACK;` as a complete sandbox.

---

## 1. First: What Stages Does PostgreSQL Process a Query Through?

A query goes through these high-level steps:

```text
SQL text
   |
   v
Parser / analyzer
   |
   v
Rewrite (e.g., rules, view expansion)
   |
   v
Planner / optimizer
   |   Chooses plan and estimates cost/rows
   v
Execution plan
   |
   v
Executor
   |   Reads/writes tuples, calls functions, processes JOIN, FILTER,
   |   SORT, AGGREGATE, triggers, and other operations
   v
Results / effects on the database
```

This is a conceptual diagram and does not describe every internal detail. What matters is that **the planner chooses how to run it**, while **the executor carries out that execution**.

### 1.1. EXPLAIN Is the Planner's View

```sql
EXPLAIN
SELECT *
FROM some_table
WHERE id = 42;
```

PostgreSQL generates a plan and typically displays:

- The nodes used to scan tables or indexes.
- How joins, sorts, and aggregations are performed.
- **Estimated** row counts and row widths.
- Estimated costs for each part.

You do **not** receive the data rows of the `SELECT`; you receive text/JSON describing the plan.

### 1.2. EXPLAIN ANALYZE Is the View When the Executor Actually Runs

```sql
EXPLAIN (ANALYZE)
SELECT *
FROM some_table
WHERE id = 42;
```

This time PostgreSQL **runs the query**, then adds:

- Actual row counts.
- Actual time per node.
- Number of times each node was executed.
- Total planning time and execution time.
- Other execution details based on options.

Therefore, `ANALYZE` in `EXPLAIN ANALYZE` is an **execution mode for measurement**, not a statistics update operation like the `ANALYZE some_table;` command.

### 1.3. Two Different Meanings of the Word ANALYZE

| Statement | Role |
|---|---|
| `ANALYZE explain_lab.orders;` | Collects/updates statistics so the planner can make estimates |
| `EXPLAIN SELECT ...;` | Views the estimated plan without running the user query in the normal way |
| `EXPLAIN (ANALYZE) SELECT ...;` | Runs the SELECT and measures the actual plan |
| `EXPLAIN (ANALYZE) DELETE ...;` | **Actually runs the DELETE** and measures it |

Do not confuse these two uses of `ANALYZE` when writing runbooks or guiding teammates.

### 1.4. EXPLAIN Is Not the Answer to Every Performance Issue

Execution plans help identify causes on the database side, but the total latency perceived by users may also include:

- Time waiting for a connection from the pool.
- Network data transfer time.
- Driver time to read or map rows into objects.
- Application processing cost, JSON serialization, UI rendering.
- Lock waits, transaction retries, and queueing outside the measurement window.

A fast `EXPLAIN ANALYZE` **does not by itself prove** the entire API is fast, and a single slow measurement does not prove the plan is always poor.

---

## 2. Basic EXPLAIN Syntax and Options

### 2.1. Simple Forms

```sql
EXPLAIN SELECT ...;

EXPLAIN ANALYZE SELECT ...;

EXPLAIN (ANALYZE, BUFFERS)
SELECT ...;
```

`EXPLAIN` supports several statement types besides `SELECT`, such as `INSERT`, `UPDATE`, `DELETE`, `MERGE`, and `EXECUTE`. When the statement has side effects, decide **whether to enable ANALYZE or not** before running it.

### 2.2. Commonly Used Practical Options

| Option | Example | Meaning |
|---|---|---|
| `ANALYZE` | `ANALYZE TRUE` | Executes the query and records actual statistics |
| `BUFFERS` | `BUFFERS TRUE` | Information about operations on buffers/cache, when applicable |
| `VERBOSE` | `VERBOSE TRUE` | Displays more detail on output columns, aliases, and some expressions |
| `COSTS` | `COSTS FALSE` | Shows/hides estimated cost figures |
| `SETTINGS` | `SETTINGS TRUE` | Displays non-default planner settings that have an effect |
| `TIMING` | `TIMING FALSE` | With ANALYZE, skips per-node timing to reduce measurement overhead |
| `SUMMARY` | `SUMMARY TRUE` | Displays summary information when available |
| `WAL` | `WAL TRUE` | WAL statistics when ANALYZE is enabled and supported |
| `FORMAT` | `FORMAT JSON` | Formats output as `TEXT`, `JSON`, `XML`, or `YAML` |

Options and detail levels may vary across PostgreSQL versions. Check the documentation for **the running server version** if an option is not recognized.

### 2.3. Common Pattern for Diagnosing SELECT

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE, SETTINGS)
SELECT ...
```

This pattern **executes the SELECT**. If the SELECT calls a state-changing function or contains a data-modifying CTE, it can still have side effects. This pattern is only appropriate when you have confirmed the logic is safe to execute.

### 2.4. Pattern to Reduce Per-Node Timing Overhead

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, SUMMARY ON)
SELECT ...
```

`TIMING OFF` helps reduce part of the cost of taking timestamps across very many node executions, while still collecting row counts and loop counts. It does not stop the statement from executing, and it does not eliminate all instrumentation overhead.

### 2.5. Viewing Plans in JSON Format

```sql
EXPLAIN (FORMAT JSON)
SELECT *
FROM explain_lab.orders
WHERE order_id = 100;
```

With `FORMAT JSON`, the output is machine-readable, convenient for plan comparison tools. Part of the structure looks like:

```json
[
  {
    "Plan": {
      "Node Type": "Index Scan",
      "Relation Name": "orders",
      "Alias": "orders",
      "Startup Cost": 0.0,
      "Total Cost": 0.0,
      "Plan Rows": 1,
      "Plan Width": 1
    }
  }
]
```

The numbers `0.0` and `1` in this JSON example are only **placeholders illustrating the structure**, not a real PostgreSQL plan. Do not copy them as performance validation thresholds.

---

## 3. Practice Lab: Generating Diverse Data to Inspect Plans

All examples below use the `explain_lab` schema. Create the schema in a **practice** database, not a production database.

### 3.1. Verify the Environment

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Do not proceed until you have verified the right environment, especially before examples measuring `DELETE` and sequences.

### 3.2. Create the Customers Table

```sql
CREATE SCHEMA IF NOT EXISTS explain_lab;

CREATE TABLE explain_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    segment TEXT NOT NULL
        CHECK (segment IN ('standard', 'premium', 'enterprise'))
);
```

### 3.3. Create the Orders Table

```sql
CREATE TABLE explain_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id BIGINT NOT NULL
        REFERENCES explain_lab.customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled', 'refunded')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    archived BOOLEAN NOT NULL DEFAULT FALSE
);
```

In this schema, `customers.customer_id` is a global key; `tenant_id` on the orders table serves filtering and workload patterns. A real multi-tenant application would need additional constraints ensuring the customer and order belong to the same tenant, such as a composite FK, if both columns can be written arbitrarily.

### 3.4. Generate 1,000 Customers

```sql
INSERT INTO explain_lab.customers
    (customer_id, tenant_id, customer_name, segment)
SELECT
    g,
    1 + (g % 10) AS tenant_id,
    'Customer-' || g::text,
    CASE
        WHEN g % 20 = 0 THEN 'enterprise'
        WHEN g % 5 = 0 THEN 'premium'
        ELSE 'standard'
    END
FROM generate_series(1, 1000) AS gs(g);
```

### 3.5. Generate 100,000 Orders

```sql
INSERT INTO explain_lab.orders
    (tenant_id, customer_id, status,
     amount, created_at, archived)
SELECT
    1 + ((1 + (g % 1000)) % 10) AS tenant_id,
    1 + (g % 1000) AS customer_id,
    CASE
        WHEN g % 100 < 8 THEN 'pending'
        WHEN g % 100 < 80 THEN 'paid'
        WHEN g % 100 < 95 THEN 'cancelled'
        ELSE 'refunded'
    END AS status,
    ((g % 500) + 1)::numeric(12, 2) AS amount,
    TIMESTAMPTZ '2026-09-01 00:00:00+00'
        + g * INTERVAL '1 minute' AS created_at,
    (g % 100 < 5) AS archived
FROM generate_series(1, 100000) AS gs(g);
```

The calculation of `tenant_id` for orders intentionally matches the `tenant_id` of the customer with `customer_id=1+(g%1000)`. This is deterministic simulated data and does not represent production data distributions.

**Note:** These data-generation `INSERT` blocks are **not idempotent** if run repeatedly. Run them only once on a fresh schema. Do not use `TRUNCATE ... CASCADE` carelessly to reset a shared database.

### 3.6. Check Row Counts and Statuses

```sql
SELECT COUNT(*) AS customers_count
FROM explain_lab.customers;

SELECT COUNT(*) AS orders_count
FROM explain_lab.orders;

SELECT status, COUNT(*) AS cnt
FROM explain_lab.orders
GROUP BY status
ORDER BY status;
```

With data generated once, expected counts are:

| status | Row count |
|---|---:|
| pending | 8,000 |
| paid | 72,000 |
| cancelled | 15,000 |
| refunded | 5,000 |
| **Total** | **100,000** |

### 3.7. Update Statistics

```sql
ANALYZE explain_lab.customers;
ANALYZE explain_lab.orders;
```

The planner needs estimates of row counts, value distributions, correlations, table page counts, etc. `ANALYZE` updates statistics using a sample taken from the data; it is not a guarantee that estimated row counts will always match actual row counts exactly.

---

## 4. A Query Plan Is a Tree of Nodes

Example query fetching orders for a tenant:

```sql
EXPLAIN
SELECT order_id, customer_id, amount
FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'pending';
```

The plan can be represented as a tree:

```text
An upper-level node
    |
    +-- data scan node
           |
           +-- filter condition
```

A hypothetical plan:

```text
Seq Scan on orders
  (cost=0.00..2500.00 rows=800 width=28)
  Filter: ((tenant_id = 3) AND (status = 'pending'))
```

The numbers `2500.00`, `800`, and `28` here **only illustrate how to read the output**. The real plan depends on statistics, table size, PostgreSQL version, and existing indexes.

### 4.1. Reading a Plan Tree Bottom-Up

For a complex query:

```text
Aggregate
  -> Sort
      -> Hash Join
          -> Seq Scan on orders
          -> Hash
              -> Seq Scan on customers
```

An easy-to-follow explanation order:

1. Fetch rows from `orders`.
2. Fetch rows from `customers`.
3. Build a hash table from the appropriate input.
4. Join rows via `Hash Join`.
5. Sort if required by the node.
6. Aggregate and return results.

This explains the **data flow** across nodes; it does not guarantee the executor always computes all inputs of one node before moving to the next. Many nodes use a pull/iterator model, streaming or batching rows.

### 4.2. Indentation Shows Parent-Child Relationships

In text-format `EXPLAIN`:

```text
Parent Node
  -> Child Node 1
  -> Child Node 2
```

The `->` arrows at matching indentation show **which node feeds data into which node**. To explain why a parent node is slow, you usually must inspect its child nodes and the volume of data they pass up.

---

## 5. Reading cost, rows, and width: Forecasts, Not Measurements

A hypothetical plan line:

```text
Index Scan using orders_pkey on orders
  (cost=0.42..8.44 rows=1 width=36)
```

There are three concepts:

| Property | Meaning |
|---|---|
| `cost=0.42..8.44` | Estimated **startup cost** and **total cost** |
| `rows=1` | Number of rows the planner **estimates the node returns** |
| `width=36` | Average row size estimated by the planner, in bytes |

### 5.1. Cost Is Not Milliseconds

`cost` is an **internal planner cost unit**, composed of relative parameters such as:

- `seq_page_cost`, `random_page_cost`.
- `cpu_tuple_cost`, `cpu_index_tuple_cost`, `cpu_operator_cost`.
- Other costs and estimates related to I/O, CPU, and parallelism.

`cost=8.44` **does not mean 8.44 ms**. It is a relative metric PostgreSQL uses to compare alternative plans.

### 5.2. Startup Cost and Total Cost

**Startup cost** is the estimated cost before the node can produce its first row. **Total cost** is the estimated cost to return all rows of the node according to the planner's model.

For example:

- `Seq Scan` typically has a low startup cost: it can start returning rows as it scans.
- `Sort` normally needs to collect its input before producing the first ordered row, so its startup cost can be substantial.
- `Limit` can cause a plan with a **low startup cost** to be preferred over a plan with a lower total cost but slow startup, because the query only fetches a few rows.

### 5.3. Costs Do Not Simply Add Line by Line

A parent node's cost **already includes the cost of its child nodes** in the planner's model. Do not add every `total cost` in the tree to report a "total cost," as that easily **double-counts**.

To compare alternatives, look at the root plan's cost and read individual nodes to see where cost originates.

### 5.4. Rows Is the Node's Output Row Count

If a plan states:

```text
Seq Scan on orders
  (cost=0.00..X rows=800 width=Y)
  Filter: (status = 'pending')
```

`rows=800` is the **estimated number of rows after filtering**, not by default the entire table's row count. The actual query may return many more or fewer rows due to statistics or data correlation.

### 5.5. Width Affects Calculations

When a query selects a large `payload JSONB` column as well, the planner may predict a larger width than a query selecting only ID and timestamp. Output width affects estimated processing, sorting, hashing, and memory costs.

Thus, `SELECT *` in an exploratory query is not equivalent to a production query selecting only a few columns; use the same projection when comparing performance.

---

## 6. Reading actual time, actual rows, and loops

When `ANALYZE` is enabled:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM explain_lab.orders
WHERE order_id = 100;
```

A node might display as:

```text
Index Scan using orders_pkey on orders
  (cost=0.42..8.44 rows=1 width=8)
  (actual time=0.025..0.027 rows=1 loops=1)
```

### 6.1. Actual Time: Measured Actual Time

`actual time=a..b` describes the observed time to the first row and to node completion in **milliseconds**, influenced by how the node is looped and instrumented.

Do not directly compare `cost=8.44` with `actual time=0.027`; they use two **different scales**.

### 6.2. Actual Rows Is Usually an Average Per Loop

A very important note: when a node executes multiple times, PostgreSQL displays `actual rows` and `actual time` in text plans as **averages per node execution**, while `loops` shows the execution count.

For example:

```text
Index Scan on customers
  (actual time=0.004..0.005 rows=1 loops=1000)
```

Approximate interpretation:

- The node was called **1,000 times**.
- Each call returned an average of about **1 row**.
- Total rows across all calls to the node is about **1,000**, not a single row.

Do not naively sum child node row counts without multiplying/interpreting `loops`.

### 6.3. Rows Removed by Filter

A Seq Scan may report:

```text
Rows Removed by Filter: 99000
```

This indicates many tuples were examined but failed the node's filter. For nodes executed multiple times, the displayed value also needs to be read according to the instrumentation/loops convention.

However, `Rows Removed by Filter` **is not synonymous** with disk pages read, table row count, or function call counts at every layer.

### 6.4. Comparing Estimated vs Actual Properly

If:

```text
rows=10
actual rows=10000 loops=1
```

the planner underestimated by roughly **1,000x** at that node.

This is a **signal worth investigating**, because a large discrepancy can cause the planner to pick the wrong join or sort. But you cannot immediately conclude "need to add an index"; the cause may be:

- Stale statistics.
- Skewed data distribution.
- Correlation across multiple columns.
- Expressions/functions that are hard to estimate.
- Parameter-sensitive plans.
- Results depending on time-varying data.

### 6.5. Why Total Execution Time Does Not Equal the Sum of Every Node's Actual Time

A parent node's time usually **includes the execution time of its child nodes**. Summing every `actual time` line can double-count multiple times. Nodes with high `loops` are even more prone to misreading.

Read along the **execution tree**, locate the time/volume-intensive paths, and compare against the plan's total time. Do not treat the numbers as an independent task list that adds linearly.

---

## 7. Common Data Scan Nodes

### 7.1. Seq Scan: Table Scan

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM explain_lab.orders
WHERE status = 'paid';
```

Because around **72%** of orders in the seed data have status `paid`, a sequential scan can be a reasonable choice: the query needs to inspect a huge proportion of rows. A Seq Scan **is not automatically a bug**.

When you see a Seq Scan:

1. How many rows / what percentage of rows need to be fetched?
2. Is there an index matching the predicate/key?
3. Does the query fetch just a few rows or almost the entire table?
4. Is there a function call in the condition making a regular index key hard to use?
5. Did the planner estimate the row count accurately?

### 7.2. Index Scan: Using an Index Then Visiting the Heap When Needed

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, status, amount
FROM explain_lab.orders
WHERE order_id = 100;
```

The primary key on `order_id` creates a B-tree index. Queries looking up a single key typically suit Index Scan, because there is no need to scan 100,000 rows to find one order.

Index Scan may still need to access the **heap** to fetch columns not in the index or check visibility.

### 7.3. Index Only Scan: Index Has All Columns, Yet MVCC Still Matters

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM explain_lab.orders
WHERE order_id BETWEEN 100 AND 200;
```

If every column needed by the query is present in the index, the planner **may** choose Index Only Scan. However, PostgreSQL also checks the visibility map; if heap pages are not marked all-visible, **Heap Fetches** may still occur.

Do not conclude "Index Only Scan = never reads the heap."

### 7.4. Bitmap Index Scan and Bitmap Heap Scan

A plan may use:

```text
Bitmap Heap Scan on orders
  Recheck Cond: (...)
  -> Bitmap Index Scan on some_index
       Index Cond: (...)
```

Overview:

1. Bitmap Index Scan identifies relevant tuple/page locations.
2. Bitmap Heap Scan retrieves data from the heap using the collected locations.
3. Conditions may need to be rechecked, especially when the bitmap degrades to page-level precision (*lossy bitmap*).

Bitmap scans can be useful when a query fetches more rows than a small Index Scan, yet not enough to make scanning the whole table optimal.

### 7.5. Index Cond vs Filter

Example plan:

```text
Index Scan using idx_orders_tenant_status on orders
  Index Cond: ((tenant_id = 3) AND (status = 'pending'))
  Filter: (amount > 200)
```

**Index Cond** is the part of the condition used to guide index traversal. **Filter** is a post-fetch step discarding extra retrieved rows.

Not every condition in `WHERE` becomes an Index Cond just because an index exists on the table. Index key order, operators, data types, expression indexes, and predicate derivability all matter.

---

## 8. Creating an Index and Observing Plan Changes

### 8.1. Measure Before Creating the Index

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, amount
FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'pending'
ORDER BY created_at DESC
LIMIT 20;
```

Record the plan, timing, buffer activity, and row counts.

### 8.2. Create an Index Matching the Filter

```sql
CREATE INDEX orders_tenant_status_created_idx
ON explain_lab.orders
    (tenant_id, status, created_at DESC);

ANALYZE explain_lab.orders;
```

### 8.3. Measure the Same Query Again

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, amount
FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'pending'
ORDER BY created_at DESC
LIMIT 20;
```

A B-tree on `(tenant_id, status, created_at DESC)` can help:

- Locate rows by `tenant_id` and `status`.
- Traverse in `created_at DESC` order matching `ORDER BY`.
- Stop once `LIMIT 20` rows are retrieved without processing all matching rows.

Still, the actual plan depends on data, memory, planner cost settings, and PostgreSQL version.

### 8.4. Avoid Concluding from a Single Measurement

The first run may have to load pages into cache, while subsequent runs benefit from a warm cache. Therefore:

- Compare the same query, same parameters, and relatively stable data.
- Run multiple times in the lab and observe variance.
- Compare `Buffers`, not just a single `Execution Time` value.
- Check other workloads affected by the new index.
- Account for INSERT/UPDATE/DELETE overhead from the added index.

Do not take "after creating the index, run #2 is faster than run #1" as the sole proof that the new index delivered the entire improvement.

---

## 9. JOIN Nodes: Nested Loop, Hash Join, Merge Join

### 9.1. Sample Query

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.segment,
    COUNT(*) AS order_count,
    SUM(o.amount) AS total_amount
FROM explain_lab.orders AS o
JOIN explain_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY c.segment
ORDER BY total_amount DESC;
```

This query filters orders, joins customers, aggregates, and sorts.

### 9.2. Nested Loop

```text
Nested Loop
  -> Outer input
  -> Inner lookup (loops = number of calls for outer rows)
```

Well suited in many cases when the outer input has few rows and the inner input has a fast index lookup. However, if the outer input is large and the inner side is scanned very many times, cost can rise sharply.

Detection example:

```text
Index Scan on customers
  (actual ... rows=1 loops=50000)
```

Do not look at `rows=1` and think the node did only one lookup; `loops=50000` indicates it may have been called tens of thousands of times.

### 9.3. Hash Join

```text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  -> Scan on orders
  -> Hash
       -> Scan on customers
```

PostgreSQL builds a hash table from one side, then uses the hash key to find matching rows on the other side. Often suitable for equality joins on medium/large datasets, depending on distribution, memory, and statistics.

Details such as `Buckets`, `Batches`, and `Memory Usage` may appear with ANALYZE. Multiple batches may indicate the hash table exceeded its memory budget and had to process in batches/spill to temp storage.

### 9.4. Merge Join

```text
Merge Join
  Merge Cond: (a.key = b.key)
  -> Sort / ordered scan on a
  -> Sort / ordered scan on b
```

Merge Join operates on data sorted by the join key. If inputs already have suitable ordering from an index, some Sort operations can be avoided; otherwise, sorting cost must be accounted for.

### 9.5. Do Not Judge a JOIN by Node Name Alone

`Hash Join` is not always faster than `Nested Loop`, and `Merge Join` is not always best when an index exists. The planner chooses based on:

- Row counts on each side.
- Condition selectivity.
- Join type.
- Index fetch capability.
- Expected memory.
- Data ordering.
- I/O/CPU costs and parallelism.

Before attempting to tweak planner settings, verify **row count estimates** and **query/index design**.

---

## 10. Sort, Aggregate, HashAggregate, and GroupAggregate

### 10.1. Sort

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM explain_lab.orders
WHERE status = 'paid'
ORDER BY amount DESC
LIMIT 30;
```

If there is no access path already ordered by `amount DESC` matching the condition, the planner may need a `Sort` node. With a small `LIMIT`, it can use a **top-N heapsort**, avoiding storing the full sorted output as a full sort would.

Commonly seen details:

```text
Sort Key: amount DESC
Sort Method: top-N heapsort  Memory: ...
```

Do not guess the Sort method without inspecting `EXPLAIN ANALYZE`.

### 10.2. Sort Spilling to Temporary Disk

When sort volume exceeds the memory budget under the execution plan, PostgreSQL may use an external sort and read/write temporary files.

The plan may report:

```text
Sort Method: external merge  Disk: ...
Buffers: temp read=... written=...
```

This is a signal to examine:

- Can row count be reduced before sorting?
- Is there an index for the matching `ORDER BY`?
- Can the query be rewritten to group/filter earlier?
- Is `work_mem` appropriate, considering multiple sort/hash nodes and concurrent sessions?

Do not increase `work_mem` globally to a huge value just to speed up one query: one session may have multiple nodes needing memory, and many concurrent sessions multiply resource demand.

### 10.3. Aggregate

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*), AVG(amount)
FROM explain_lab.orders
WHERE status = 'paid';
```

An `Aggregate` node can summarize filtered rows into a single row. Its input may still have to read very many rows; do not see `rows=1` at the root and conclude the query is lightweight.

### 10.4. HashAggregate and GroupAggregate

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, status, SUM(amount)
FROM explain_lab.orders
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

PostgreSQL can:

- Use `HashAggregate` to group via a hash table.
- Use `GroupAggregate` on data already in suitable order.
- Combine `Sort`/`Gather`/partial aggregation depending on the plan.

Evaluate based on group count, input rows, memory, batches, temp I/O, ordering alignment, and degree of parallelism.

---

## 11. BUFFERS: How Is the Plan Touching Memory?

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM explain_lab.orders
WHERE status = 'cancelled';
```

You may see output such as:

```text
Buffers: shared hit=120 read=8
```

Numbers are illustrative only. Common labels:

| Label | General meaning |
|---|---|
| `shared hit` | Page already present in PostgreSQL shared buffers |
| `shared read` | Page brought into shared buffers via the read path; does not necessarily mean physical disk I/O occurred |
| `shared dirtied` | Shared buffer page modified to dirty during the observed operation |
| `shared written` | Shared buffer page written out within the tracked work |
| `local ...` | Operations on local buffers for applicable relation types |
| `temp read/written` | Temporary page reads/writes, e.g., when Sort/Hash spills past memory budget |

### 11.1. Shared Hit Does Not Mean "Completely Free"

Reading pages already in shared buffers still consumes CPU, tuple processing, condition checks, visibility checks, and other work. A query with millions of `shared hit`s can still be slow due to the sheer volume of work.

### 11.2. Shared Read Does Not Equal Physical Disk Reads

`shared read` reflects PostgreSQL's read path into its buffer cache. The operating system may already have cached the data, so a page reported as "read" **does not necessarily** hit the physical drive.

Do not calculate "shared read count × estimated disk latency" and treat that as real latency.

### 11.3. Parent May Include Child Buffers

Buffer statistics on nodes follow a tree accumulation convention. Do not sum every `Buffers` line across the plan if you want total accesses; that easily double-counts child node work.

### 11.4. I/O Timing

If the server is configured to collect I/O timing via the corresponding version's mechanism, `EXPLAIN ANALYZE` can add details such as `I/O Timings`. Measuring I/O also incurs instrumentation overhead and depends on settings like `track_io_timing`.

Do not assume every server displays I/O timing simply because `BUFFERS` was added.

### 11.5. Temp I/O Suggests Where to Investigate

If the plan shows:

```text
Buffers: temp read=... written=...
```

look for `Sort`, `Hash`, `HashAggregate`, or related memory-consuming nodes. Check whether input data is unusually large due to JOIN fanout or misestimation rather than just adding memory.

---

## 12. Planning Time and Execution Time

`EXPLAIN ANALYZE` output usually includes summary lines:

```text
Planning Time: 0.250 ms
Execution Time: 3.400 ms
```

These are **illustrative** numbers.

### 12.1. Planning Time

Includes planning work reported in the measurement context. Complex queries with many JOINs, many index alternatives, or partitioning can spend significant time in planning.

When a query executes very quickly but is run thousands of times with different parameters, repeated planning cost can be notable. Prepared statements/generic plans may be relevant, though one strategy does not fit every case.

### 12.2. Execution Time

This is the time the executor ran within instrumentation scope, including node-related work and some execution overhead. It is **not identical** to the full time an application takes to receive results over the network and process them.

### 12.3. Result Size and Serialization

A query returning 1 million rows can spend substantial time **transmitting, encoding, and processing on the client** even after the executor runs a relatively fast plan. Newer PostgreSQL versions provide conditional serialization timing modes; if your environment does not support them, still measure round-trip from the application for an end-to-end picture.

### 12.4. Timing OFF Does Not Mean the Query Runs in Zero Time

`TIMING OFF` only changes **how per-node timing is collected and displayed**. The statement is still executed, filters still run, data is still written if it is DML, and triggers can still fire.

---

## 13. Most Important: EXPLAIN and EXPLAIN ANALYZE with Write Statements

### 13.1. Safe Comparison of EXPLAIN on DML

```sql
EXPLAIN
UPDATE explain_lab.orders
SET status = 'cancelled'
WHERE order_id = 100;
```

In normal cases, PostgreSQL **only plans** and **does not modify the status of order 100**. It may show an `Update on orders` node and the access path to locate the row.

**Subtle distinction:** "does not execute DML" does not mean planning can absolutely never produce side effects under every custom configuration: planning can access metadata, take necessary locks, invoke certain planner logic, and evaluate constant expressions or functions declared with incorrect volatility. Do not treat `EXPLAIN` as a sandbox for untrusted custom extensions/functions. For normal PostgreSQL SQL, however, it is the appropriate way to **view a plan without executing UPDATE/DELETE**.

### 13.2. EXPLAIN ANALYZE on DML Actually Runs

```sql
EXPLAIN ANALYZE
UPDATE explain_lab.orders
SET status = 'cancelled'
WHERE order_id = 100;
```

This command **executes the UPDATE**. If run outside an explicit transaction in an autocommit client, the change can be committed immediately once the statement succeeds.

Do not run this on production "just to test and see" unless you genuinely intend and are authorized to modify data.

### 13.3. EXPLAIN ANALYZE DELETE Actually Deletes

```sql
EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM explain_lab.orders
WHERE status = 'cancelled';
```

In the seed data, many thousands of orders have `status='cancelled'`. The command will **delete matching rows** upon execution and can cause:

- MVCC dead tuples.
- WAL generation, I/O, and index maintenance.
- FK checks and triggers.
- Locking, blocking, or deadlocks under concurrent workloads.
- Replication lag and subsequent autovacuum load.

Therefore, **never** run this example outside a controlled environment; here it only illustrates the risk, not a mandatory exercise to execute.

### 13.4. EXPLAIN ANALYZE INSERT Also Inserts Rows

```sql
-- Only run inside a lab transaction as shown in the next section.
EXPLAIN ANALYZE
INSERT INTO explain_lab.customers
    (customer_id, tenant_id, customer_name, segment)
VALUES (2001, 1, 'Test EXPLAIN', 'standard');
```

If run directly and successfully, row `2001` has been inserted. `EXPLAIN ANALYZE` may display only the plan/timing and **not automatically return inserted rows the way a normal INSERT does**, yet the effect has occurred.

### 13.5. MERGE Can Also Modify Data

`MERGE` (PostgreSQL 15+) can choose `INSERT`, `UPDATE`, or `DELETE` conditionally. `EXPLAIN ANALYZE MERGE ...` **executes** the corresponding actions when supported by the server and valid.

Do not assume a command with multiple `WHEN MATCHED`/`WHEN NOT MATCHED` branches is merely a plan description: it can perform real writes.

---

## 14. Testing EXPLAIN ANALYZE UPDATE Inside a Transaction with ROLLBACK

In a lab, you can observe DML and then revert **transactional** changes.

### 14.1. Verify the Value Beforehand

```sql
SELECT order_id, status, amount
FROM explain_lab.orders
WHERE order_id = 100;
```

The concrete row may show status `paid`, `pending`, etc., depending on the seed data.

### 14.2. Execute Inside a Test Transaction

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE explain_lab.orders
SET status = 'cancelled'
WHERE order_id = 100;

-- The next statement in the same transaction
-- will see the change made by its own transaction:
SELECT order_id, status
FROM explain_lab.orders
WHERE order_id = 100;

ROLLBACK;
```

Mid-transaction, this connection's SELECT sees `cancelled`. After `ROLLBACK`, the change on `orders` is undone.

### 14.3. Check Again After Rollback

```sql
SELECT order_id, status
FROM explain_lab.orders
WHERE order_id = 100;
```

The value returns to its state prior to the test transaction, **provided no other transaction modified the row while you tested**.

### 14.4. What Does ROLLBACK Protect?

For normal operations managed by a PostgreSQL transaction:

- `INSERT`/`UPDATE`/`DELETE` on tables are rolled back.
- Index entries created/modified by transactional operations do not become valid committed state.
- Trigger changes that write to **PostgreSQL tables in the same transaction** are also rolled back.

However, there are still categories of effects not undone that way; see the sections on sequences, external side effects, and locks/WAL next.

### 14.5. Practical Limits of "Measure Then Rollback"

- The statement still had to do real work, potentially generating WAL, dead tuples, and resource load.
- It can hold row/table locks while the test transaction remains open.
- It can be rejected by triggers/constraints or trigger other processing paths.
- It can increase replication/WAL pressure even when rolled back.
- `ROLLBACK` cannot undo side effects **outside the database**.
- Certain operations such as sequence usage do not roll back allocated values.

**Therefore, for production, the preferred approach is EXPLAIN without ANALYZE or measuring on a safe clone.** A test transaction is only appropriate after all effects are evaluated and the load is acceptable.

---

## 15. EXPLAIN ANALYZE SELECT Can Still Have Side Effects

A dangerous assumption is "`SELECT` is definitely read-only."

PostgreSQL allows calling **VOLATILE functions**, sequence operations, and even data-modifying CTEs inside a statement that returns results in SELECT form.

### 15.1. Sequence nextval()

Create a demo sequence:

```sql
CREATE SEQUENCE explain_lab.test_seq
    START WITH 1
    INCREMENT BY 1;
```

Try:

```sql
BEGIN;

EXPLAIN (ANALYZE)
SELECT nextval('explain_lab.test_seq'::regclass);

ROLLBACK;
```

Although the transaction was rolled back, `nextval()` **was executed** during measurement, and the sequence increment **is not undone**.

### 15.2. Confirm Sequences Do Not Roll Back

```sql
SELECT last_value, is_called
FROM explain_lab.test_seq;

SELECT nextval('explain_lab.test_seq'::regclass)
    AS another_value;
```

Values depend on previous runs, caching, and other sessions; they do not have to be 1 or 2. The key observation is that **there is no rollback guarantee returning allocated sequence values**.

**Lesson:** If you only want to inspect the plan, do not enable `ANALYZE` on a SELECT that uses `nextval()` in an environment where the sequence has business significance.

### 15.3. Why Are Sequences Intentionally Non-Transactional?

Sequences are designed for high-throughput number allocation under concurrency. If rolling back a transaction "returned" an allocated number, other transactions might already have received/seen subsequent numbers, complicating ordering and concurrent correctness.

Gaps in sequences after rollback are normal behavior. Do not rely on sequences as a guarantee that **no numbers are ever skipped**.

### 15.4. Functions That Send Email, Write Files, Call HTTP, or External Services

A SELECT can invoke an extension/application-defined function:

```sql
-- Illustrative only. Not a built-in PostgreSQL function.
-- SELECT external_service_send_notification(100);
```

If executed via `EXPLAIN ANALYZE`, that function might:

- Send an email.
- Call an HTTP API.
- Write a file.
- Publish a message to an external queue outside the DB.
- Trigger a payment service.

PostgreSQL's `ROLLBACK` **does not automatically recall** an email already sent or a transaction executed on an external system.

### 15.5. SELECT Calling a Database-Writing Function

PostgreSQL permits VOLATILE functions to perform allowed side-effect operations in applicable contexts. For instance:

```sql
-- A custom function can write to an audit table inside the same transaction:
-- SELECT my_function_that_inserts_audit_row(...);
```

If the function writes to a PostgreSQL table **in the same transaction**, that change is normally rolled back when the transaction rolls back. But if the function interacts with another system or allocates a sequence, the exceptions noted earlier still apply.

Do not deduce "if it's SELECT, it's safe" solely from the SQL verb.

---

## 16. Data-Modifying CTEs: A SELECT Can Wrap a Real UPDATE

PostgreSQL supports data-modifying statements inside `WITH` using `RETURNING`.

Example:

```sql
WITH changed AS (
    UPDATE explain_lab.orders
    SET archived = TRUE
    WHERE order_id = 100
    RETURNING order_id
)
SELECT COUNT(*)
FROM changed;
```

The outermost query is a SELECT, yet **the inner CTE contains an UPDATE**. When actually run, the `UPDATE` truly executes.

### 16.1. EXPLAIN ANALYZE with a Data-Modifying CTE

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
WITH changed AS (
    UPDATE explain_lab.orders
    SET archived = TRUE
    WHERE order_id = 100
    RETURNING order_id
)
SELECT COUNT(*) AS affected
FROM changed;

SELECT order_id, archived
FROM explain_lab.orders
WHERE order_id = 100;

ROLLBACK;
```

Inside the test transaction, `archived` was switched to TRUE. `ROLLBACK` reverts the transactional table change.

### 16.2. A Data-Modifying CTE Does Not "Do Nothing If SELECT Reads Partially"

Data-modifying statements in `WITH` have their own execution semantics. Do not rely on `LIMIT 0` or the outer SELECT not consuming all rows to assume the UPDATE/DELETE portion will definitely not occur.

To avoid changes when measuring, **do not use `EXPLAIN ANALYZE` on statements containing DML**.

### 16.3. RETURNING Is Not a Dry-Run Mechanism

`RETURNING` displays values of written rows, yet the write action still occurs:

```sql
UPDATE explain_lab.orders
SET archived = TRUE
WHERE order_id = 100
RETURNING order_id, archived;
```

The `RETURNING` output helps verify operation scope; it does not turn the SQL statement into a read-only query.

---

## 17. Triggers and Foreign-Key Cascades: Side Effects Beyond the Target Table

A `DELETE` statement can delete child rows due to `ON DELETE CASCADE`, even though only one target table is named.

### 17.1. Create Isolated Test Tables

```sql
CREATE TABLE explain_lab.demo_parent (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE explain_lab.demo_child (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL
        REFERENCES explain_lab.demo_parent(id)
        ON DELETE CASCADE,
    note TEXT NOT NULL
);

INSERT INTO explain_lab.demo_parent(id, label)
VALUES (1, 'Parent for EXPLAIN lab');

INSERT INTO explain_lab.demo_child(id, parent_id, note)
VALUES
    (10, 1, 'Child A'),
    (11, 1, 'Child B');
```

### 17.2. EXPLAIN Without ANALYZE for DELETE

```sql
EXPLAIN
DELETE FROM explain_lab.demo_parent
WHERE id = 1;
```

This command does not execute the deletion in the normal case. Both `demo_child` rows remain.

### 17.3. EXPLAIN ANALYZE Runs the Cascade Too

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
DELETE FROM explain_lab.demo_parent
WHERE id = 1;

SELECT COUNT(*) AS remaining_parent
FROM explain_lab.demo_parent;

SELECT COUNT(*) AS remaining_child
FROM explain_lab.demo_child;

ROLLBACK;
```

Inside the transaction, `remaining_parent=0` and `remaining_child=0`. Those two child rows were deleted via cascade, not merely "planned on paper."

After `ROLLBACK`, both the parent and transactional children are restored.

### 17.4. Trigger Info in EXPLAIN ANALYZE

Some plans may display timing lines like `Trigger for constraint ...` or other trigger details. This signals that execution cost does not lie solely in the scan/update nodes of the target table.

However, do not assume `EXPLAIN` without ANALYZE estimates all trigger/cascade costs completely. For complex DML, measure in a safe environment and inspect dependencies as well.

### 17.5. Triggers with External Side Effects Are Riskier

If a table has a trigger that makes HTTP calls or sends notifications through infrastructure outside the database, `ROLLBACK` does not guarantee revoking those effects. Before trying `EXPLAIN ANALYZE DELETE` or `UPDATE` on a real table:

1. Check FKs and `ON DELETE` rules.
2. Check triggers and the functions they call.
3. Determine whether extensions, external queues, email, or payment systems are invoked.
4. Use an isolated clone if side effects cannot be safely disabled.

Do not disable triggers/constraints in production just for a quick measurement: that can skew the measurement and violate data integrity.

---

## 18. ROLLBACK Does Not Undo Everything: Classification Table

| Effect when running EXPLAIN ANALYZE | Usually rolled back in the same transaction? | Notes |
|---|---|---|
| `UPDATE` rows in a PostgreSQL table | **Yes** | Uncommitted, assuming no external mechanism |
| PostgreSQL `INSERT`/`DELETE` | **Yes** | Including transactional changes from triggers/FK cascades |
| Writing to a PostgreSQL audit table via a trigger in the same transaction | **Yes** | Provided it truly runs in the same transaction |
| `nextval()` on a sequence | **No** | Allocated numbers are not returned after rollback |
| Sending email via an external system | **No** | Emails are not automatically recalled |
| HTTP POST to another service | **Not automatically** | Requires idempotency/compensation on the external system |
| Writing files outside the database | **Not automatically** | Not managed by database transactions |
| Generating WAL/I/O pressure for the transaction | **Does not "reclaim time/resources"** | Rollback does not erase resources already consumed |
| Changes in another DB system | **Not by default** | Requires a separate distributed protocol if any |
| Sending async notifications in an external system | **Not by default** | May already have been dispatched before rollback |

### 18.1. Distinguish "No Longer Effective" from "Never Ran"

After rollback, a transactional `UPDATE` is no longer visible as committed. Yet the UPDATE statement **was executed by the executor**, and may have:

- Caused lock waits.
- Generated WAL and tuple versions that will need cleanup.
- Fired triggers.
- Incremented activity counters/statistics.
- Consumed CPU, I/O, and time.

Thus, `ROLLBACK` restores **transactional data semantics**, rather than turning back time or reversing all external actions.

### 18.2. Database Clones Are a Safer Boundary for Benchmarking

If you need to measure a `DELETE` removing millions of records with complex triggers, a safer approach is usually:

- Create a clone/staging database from data anonymized per policy.
- Intentionally disable external email/billing integrations by design.
- Verify permissions and service endpoints.
- Measure `EXPLAIN ANALYZE` there.
- Cross-check the plan with production using `EXPLAIN` without ANALYZE and available statistics.

The clone needs to resemble production in schema, indexes, statistics, data distribution, config, and hardware for the measurement to be meaningful; do not assume a tiny staging box mirrors production.

---

## 19. WAL, Execution Time, and the Cost of Write Statements

### 19.1. What Is WAL Used For?

PostgreSQL writes **Write-Ahead Log** records for many changes related to data and recovery. An `UPDATE` or `DELETE` can generate WAL, affecting replication and checkpoint frequency.

When you want to observe this:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE explain_lab.orders
SET archived = TRUE
WHERE order_id BETWEEN 100 AND 200;

ROLLBACK;
```

The `WAL` section in the plan can show WAL records, full-page images, and bytes depending on version and circumstances.

### 19.2. Why Doesn't Rollback "Erase Generated WAL"?

A transaction must write enough log records to protect consistency, and rollback itself can generate cleanup/status work. Consumed resources and written log records do not vanish simply because table results revert to pre-transaction state.

Therefore, **benchmarking DML with rollback still generates real load**. If a workload is sensitive to replica lag, autovacuum, disk I/O, or locks, use a separate environment.

### 19.3. EXPLAIN Does Not Provide a Complete Snapshot of System Impact

An `UPDATE` plan does not replace:

- Monitoring WAL generation and replication lag.
- Autovacuum statistics.
- Lock wait/deadlock metrics.
- Heap and index bloat size.
- Cache impact on other queries.
- Commit/checkpoint/replication timing in the specific operational context.

EXPLAIN is a **query plan diagnostic tool**, not an entire observability platform.

---

## 20. Prepared Statements: Generic Plans and Custom Plans

An application may send a parameterized query:

```sql
PREPARE lookup_orders(INTEGER, TEXT) AS
SELECT order_id, amount, created_at
FROM explain_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC
LIMIT 20;
```

### 20.1. Explaining the Problem

The optimal plan for:

```text
tenant_id = 3
status = 'pending'
```

may differ from the optimal plan for:

```text
tenant_id = 3
status = 'paid'
```

because `pending` and `paid` have very different frequencies in the seed data.

### 20.2. Custom Plan

When PostgreSQL builds a **custom plan**, the execution's parameter values can be considered during planning.

```sql
SET plan_cache_mode = force_custom_plan;

EXPLAIN EXECUTE lookup_orders(3, 'pending');
EXPLAIN EXECUTE lookup_orders(3, 'paid');
```

### 20.3. Generic Plan

A generic plan must remain valid across different parameter values:

```sql
SET plan_cache_mode = force_generic_plan;

EXPLAIN EXECUTE lookup_orders(3, 'pending');
EXPLAIN EXECUTE lookup_orders(3, 'paid');
```

Clean up:

```sql
RESET plan_cache_mode;
DEALLOCATE lookup_orders;
```

`plan_cache_mode` supports three common choices—`auto`, `force_custom_plan`, and `force_generic_plan`—on modern PostgreSQL versions. `force_*` should be used for **diagnosis**, not applied arbitrarily across an entire application.

### 20.4. EXPLAIN EXECUTE and ANALYZE EXECUTE

`EXPLAIN EXECUTE lookup_orders(...)` inspects the chosen plan without running the SELECT to return data. `EXPLAIN (ANALYZE) EXECUTE lookup_orders(...)` **executes the prepared statement**.

If the prepared statement performs DML or invokes a function with side effects, adding `ANALYZE` still causes all the effects discussed earlier. Being a prepared query **does not make it read-only**.

### 20.5. Do Not Force Indexes Before Understanding Plan Caching

If a query sometimes uses an index and sometimes uses Seq Scan, determine:

- Is it truly the same SQL / parameter values?
- Is it a generic or custom plan?
- Did statistics change?
- Did data change substantially?
- Does the query have a different `LIMIT`/`ORDER BY`?
- Are session settings or roles different?

A different plan does not by itself prove the planner is malfunctioning.

---

## 21. Queries with JOINs and Correlation Statistics

Suppose `tenant` and `status` are strongly correlated: tenant 1 is mostly `paid`, tenant 2 is mostly `pending`. If the planner only has single-column statistics, multiplying independent probabilities can misestimate.

### 21.1. Symptom in EXPLAIN ANALYZE

```text
Index Scan ...
  (cost=... rows=20 ...)
  (actual ... rows=4000 ...)
```

A large mismatch can affect whether Nested Loop or Hash Join is chosen.

### 21.2. Updating Basic Statistics

```sql
ANALYZE explain_lab.orders;
```

If stale statistics are the cause, updating statistics can improve estimates.

### 21.3. Extended Statistics

For cases where multiple columns are dependent/correlated:

```sql
CREATE STATISTICS orders_tenant_status_stats
    (dependencies, mcv)
ON tenant_id, status
FROM explain_lab.orders;

ANALYZE explain_lab.orders;
```

PostgreSQL can use extended statistics such as functional dependencies or multivariate most-common values for certain estimates. There is **no** guarantee that every JOIN, every expression, and every query will improve via a statistics object.

### 21.4. Why Not Use Actual Rows as a Fixed Row Count?

`actual rows` is the result at the moment the statement ran with that snapshot/parameters. In a system with concurrent writes, data volume and distribution can change. The planner must estimate for future executions and cannot "hardcode" actual rows from a single measurement.

---

## 22. Parallel Query, Gather, and Gather Merge

PostgreSQL can split some SELECT work across multiple workers.

```text
Gather
  -> Parallel Seq Scan on orders
```

or:

```text
Gather Merge
  -> Sort
      -> Parallel Seq Scan ...
```

### 22.1. Gather vs Gather Merge

- `Gather` collects tuples from workers; it does not preserve a global order of results by itself.
- `Gather Merge` merges streams that **already have compatible ordering**, preserving the required output order.

### 22.2. Actual Worker Count

A plan may display:

```text
Workers Planned: 2
Workers Launched: 1
```

The planner intended two workers, but runtime only launched one in this example. Causes may relate to configuration and available resources; do not assume planned equals launched.

### 22.3. Loops and Rows Under Parallelism

In parallel plans, row counts and node execution counts must be interpreted alongside worker information. Do not directly take one worker's `actual rows` as the system-wide total when the plan distributes work across workers.

### 22.4. Parallelism Is Not Always Better

For small queries, the overhead of launching workers, exchanging tuples, and gathering results can outweigh the benefit. PostgreSQL chooses based on cost; understanding the plan requires reading both the leader node and worker instrumentation.

---

## 23. CTEs, Materialize, and Intermediate Nodes

### 23.1. CTEs Are Not Always Materialized by Default

`WITH` helps structure queries, but PostgreSQL can inline/fold certain non-volatile read-only CTEs when appropriate. The `MATERIALIZED` and `NOT MATERIALIZED` options (PostgreSQL 12+) influence that decision where permitted.

```sql
EXPLAIN
WITH recent_paid AS (
    SELECT order_id, customer_id, amount
    FROM explain_lab.orders
    WHERE status = 'paid'
)
SELECT COUNT(*)
FROM recent_paid;
```

Do not assume a `CTE Scan` node must appear simply because SQL uses `WITH`.

### 23.2. Materialize Node

A `Materialize` node can cache intermediate results for reuse when a parent node needs to re-read them. It is not the same thing as a **materialized view** storing persistent data in the database.

Do not remove a CTE or force `NOT MATERIALIZED` merely because you see a Materialize node; understand why the plan needs to repeat/buffer data and measure the workload.

### 23.3. CTEs with Side Effects Must Be Viewed Differently

As in section 16: a CTE containing `INSERT`/`UPDATE`/`DELETE` is not merely a SELECT organization construct. When `EXPLAIN ANALYZE` is enabled, the data-modifying statement in the CTE **is executed** per PostgreSQL semantics.

---

## 24. How Can EXPLAIN Be Used for Queries in Production?

There is no single "all EXPLAINs are safe" or "all EXPLAINs are dangerous" rule that applies in every situation.

### 24.1. Group A — Planning Without Executing DML

Example:

```sql
EXPLAIN
DELETE FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'cancelled';
```

This is an appropriate way to **view the estimated plan** without executing the DELETE under normal mechanisms. Even so, query parsing/planning still uses resources and appropriate locks for metadata access; do not treat planning as "zero-cost."

### 24.2. Group B — Ordinary Read-Only SELECT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM explain_lab.orders
WHERE order_id BETWEEN 100 AND 200;
```

This executes the SELECT, with no obvious side effects. It can be used in a controlled way to measure, keeping in mind:

- SELECT can still cause CPU/I/O load.
- It can wait on locks or resources.
- Heavy queries still impact other workloads.
- Verify it calls no side-effect functions and has no data-modifying CTEs.

### 24.3. Group C — DML or SELECT with Side Effects

```sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE explain_lab.orders
SET archived = TRUE
WHERE tenant_id = 3;
```

This is **write execution**. For production:

- Prefer `EXPLAIN` without `ANALYZE` if you only need the plan.
- To measure real execution, use a controlled staging/clone environment.
- If testing inside a transaction on an environment with real data is unavoidable, obtain approval, understand every trigger/side effect, and have a rollback/recovery plan.
- Do not overlook risks from sequences, external systems, and consumed resources.

### 24.4. Group D — Dynamic SQL and Unknown Functions/Extensions

If a query calls a custom function or extension with external effects:

```sql
SELECT my_unknown_function(...);
```

that has not been audited, do not casually enable `ANALYZE`. With misdeclared volatility functions or special code, even planning can have non-obvious consequences. Inspect the function definition and permissions first.

---

## 25. Responsible Benchmarking Techniques

### 25.1. Choose Representative Queries

A plan for:

```sql
WHERE tenant_id = 1 AND status = 'paid'
```

may not represent:

```sql
WHERE tenant_id = 9 AND status = 'pending'
```

Different selectivity, distributions, and data types can lead to different plans. Sample both typical parameter values and worst-case scenarios.

### 25.2. Control Snapshots, Transactions, and Concurrency

Measuring while a table is undergoing bulk insert/delete jobs can produce wide variance compared to a quiet window. If the goal is peak-hour real performance, measure under representative conditions while ensuring no harm is done.

Do not leave a benchmark transaction open long after measuring; it can hold snapshots/locks and affect VACUUM or other writers.

### 25.3. Do Not Arbitrarily Toggle Planner Settings in Production

```sql
-- Illustrates checking a plan in an isolated session only:
SET enable_seqscan = off;
```

Forcing off Seq Scan can help ask "what would the plan look like if an index were chosen?", but:

- It does not conjure a missing index into existence.
- It only adds a cost penalty to one option; it does not strictly guarantee zero Seq Scans.
- A forced plan does not prove an index should be used in the real workload.
- You must `RESET enable_seqscan;` and never apply experimental settings application-wide.

### 25.4. SET LOCAL to Scope Test Settings to a Transaction

```sql
BEGIN;

SET LOCAL work_mem = '16MB';

EXPLAIN (ANALYZE, BUFFERS)
SELECT status, COUNT(*)
FROM explain_lab.orders
GROUP BY status;

ROLLBACK;
```

`SET LOCAL` is useful for scoping a setting change to the current transaction in appropriate contexts. However, **ROLLBACK does not undo external side effects of a statement**. Only use this pattern with ordinary SELECTs that have no side effects.

### 25.5. Use LIMIT Semantically

`LIMIT 10` can produce a vastly different plan and runtime than a query without LIMIT. If the real application needs all 100,000 rows, benchmarking with `LIMIT 10` is not representative.

Conversely, for a paginated API fetching 20 sorted rows, an index supporting ORDER BY + LIMIT is a key optimization direction.

### 25.6. Do Not Substitute a Tiny Toy Table for Real Data

On a 10-row table, PostgreSQL very reasonably chooses Seq Scan; that does not mean it will choose Seq Scan on a 10-million-row table.

Our lab uses 100,000 orders to provide enough variety to inspect plans, but production performance also depends on hardware, real data, concurrency, caching, and statistics.

---

## 26. Observing Slow Queries Outside EXPLAIN

### 26.1. pg_stat_activity

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Helps spot active sessions, sessions idle in transaction, or sessions waiting on something. Visibility into other sessions depends on role and monitoring configuration.

### 26.2. pg_stat_statements

The `pg_stat_statements` extension (if installed and configured appropriately) provides cumulative statistics by query fingerprint, such as execution time, call count, row counts, and buffer activity.

Do not assume this view is always present; the system must enable the extension and required parameters. It helps **choose which queries to EXPLAIN**, though it does not replace an actual plan for specific parameters.

### 26.3. auto_explain

The `auto_explain` module can log plans for slow queries to the server log per configuration, optionally with runtime measurements.

Considerations:

- Must be configured and permitted under operational procedures.
- Heavy plan logging creates overhead and may contain sensitive information.
- Do not enable `log_analyze` and `log_buffers` indiscriminately without weighing the cost.
- Use it to observe real queries that are hard to reproduce, rather than treating automatic logs as complete QA results.

### 26.4. pg_stat_user_tables and Autovacuum Statistics

```sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    n_live_tup,
    n_dead_tup,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'explain_lab'
ORDER BY relname;
```

Values are cumulative/estimated statistics and should not be treated as an exact point-in-time snapshot of every query or every tuple.

---

## 27. Workflow for Investigating a Slow Query

A practical workflow:

### Step 1 — Identify the SQL Statement and Context

Record:

- The actual SQL (or template) and parameter values with sensitive data protected.
- PostgreSQL version and database.
- Time of slowdown, repetition rate, concurrency.
- Isolation level, role/RLS if relevant.
- Target latency and expected row count.

### Step 2 — Determine Whether the Statement Has Side Effects

- Pure read-only `SELECT`?
- Calls `nextval()`?
- Has volatile functions, HTTP/email calls, or data-modifying CTEs?
- Is `UPDATE`/`DELETE`/`INSERT`/`MERGE`?
- Has triggers/FK cascades?

If it has side effects, **do not enable `ANALYZE` on production** just to measure.

### Step 3 — EXPLAIN First

```sql
EXPLAIN (VERBOSE, SETTINGS)
SELECT ...;
```

Understand the expected plan before deciding whether actual runtime measurement is possible/worthwhile.

### Step 4 — Only ANALYZE If Safe

On a pure SELECT or an isolated clone:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT ...;
```

Record row counts, loops, buffers, total execution time, and signs of temp I/O.

### Step 5 — Find Mismatched or Resource-Intensive Nodes

Examples:

- Estimated rows 10, actual rows 100,000.
- Nested Loop inner index probe running hundreds of thousands of loops.
- External Sort with high temp I/O.
- Seq Scan reading almost the entire table when the query only needs 0.01%.
- Index Scan fetching many heap tuples due to projection or selectivity.
- Hash Join splitting into many batches due to memory.

Do not optimize from node names alone; read the full tree.

### Step 6 — Formulate Testable Hypotheses

Directions:

- Index better aligned with filters + ORDER BY.
- Rewrite query to filter earlier / limit fanout.
- Collect fresh statistics or extended statistics.
- Reduce returned columns.
- Examine prepared statement generic/custom plans.
- Optimize locking/transactions when the real issue is waiting.
- Consider partitioning when data volume and lifecycle fit.

### Step 7 — Re-Measure and Check Optimization Side Effects

After each change:

- Compare under the same workload.
- Measure multiple times.
- Check write/index maintenance overhead.
- Verify correctness of results.
- Monitor impact on other queries.
- Have a rollback plan for migrations/indexes/config.

---

## 28. Common Mistakes When Reading and Using EXPLAIN

**1. "EXPLAIN and EXPLAIN ANALYZE are both just previews."** False. `EXPLAIN ANALYZE` executes the statement.

**2. "EXPLAIN ANALYZE UPDATE does not modify data because it only returns a plan."** False. The UPDATE genuinely executes.

**3. "EXPLAIN ANALYZE DELETE is safe on production if run outside a transaction."** False. Under autocommit, the operation can commit immediately.

**4. "BEGIN ... ROLLBACK undoes every effect in the world."** False. Sequences, emails, HTTP calls, and I/O outside PostgreSQL do not automatically roll back.

**5. "nextval() rollback returns the number."** False. Sequences can have gaps.

**6. "SELECT definitely has no side effects."** False if it calls volatile functions, sequences, or data-modifying CTEs.

**7. "RETURNING or WITH makes DML just a read query."** False. DML still executes under ANALYZE.

**8. "EXPLAIN without ANALYZE means the system spends zero resources."** No. Planning still has cost, needs metadata, and can interact with custom code.

**9. "Cost 100 means 100 milliseconds."** False. Cost is a relative planner unit.

**10. "Rows 1000 in EXPLAIN is the actual row count."** False. It is an estimate.

**11. "Actual rows 1 loops 10000 means only one row total."** False. Must multiply/interpret by node loop count.

**12. "Summing actual time of every node yields Execution Time."** False. Parent node cost can include children and loops.

**13. "Seq Scan is always bad."** No. When reading most of a table, Seq Scan can be optimal.

**14. "Index Scan is always faster than Seq Scan."** No. Random I/O, selectivity, and heap fetches can make index access expensive.

**15. "Index Only Scan absolutely never needs the heap."** False. Visibility checks are required and Heap Fetches can still occur.

**16. "Shared read definitely reads straight from physical disk."** No. The OS cache may satisfy it.

**17. "Shared hit costs zero CPU."** False. Accessing tuples still has cost.

**18. "Buffers per node can be summed directly for a total."** False, because they can accumulate across nodes.

**19. "External sort just needs unlimited work_mem."** False. RAM is shared across many nodes/queries/sessions; evaluate system-wide.

**20. "Nested Loop is wrong in all cases."** No. It works well when the outer side is small and inner lookup is efficient.

**21. "A query benchmarked fast on a 10-row table will be fast on 10 million rows."** Unfounded.

**22. "Adding an index is always good for every workload."** False. Indexes cost disk/WAL/writes and can affect HOT updates.

**23. "ANALYZE table and EXPLAIN ANALYZE are the same thing."** False. One updates statistics; the other executes to measure a plan.

**24. "EXPLAIN ANALYZE only measures pure database CPU with zero overhead."** False. Instrumentation has overhead; there is also I/O and other factors.

**25. "TIMING OFF stops the query from running."** False. It only reduces per-node timing measurement.

**26. "Not seeing Index Cond on WHERE means the query doesn't filter."** No. Filter and Index Cond play different roles.

**27. "The planner always estimates multi-column correlations accurately."** False. Extended statistics or query rewrites may be needed.

**28. "A prepared statement always uses one identical plan for all parameters."** No. There are generic/custom plans and cost-based selection.

**29. "With LIMIT, the query never processes much data."** Not always. ORDER BY/aggregates before LIMIT may still read/sort large amounts.

**30. "Creating a new index and seeing one faster run is sufficient proof."** No. Caching, data, workload, and other factors must be controlled.

**31. "EXPLAIN ANALYZE on a clone is identical to production."** Not guaranteed. Statistics, data, config, and resources may differ.

**32. "EXPLAIN without ANALYZE always calls every function in SQL to compute results."** No. It builds a plan; however, do not blindly trust unknown functions/extensions during planning.

**33. "Rolled-back DML creates no WAL or dead tuples."** False. The operation ran, and rollback does not erase all generated costs.

**34. "With triggers, EXPLAIN without ANALYZE already measures full trigger cost."** No. Triggers execute when the statement actually runs.

**35. "One EXPLAIN ANALYZE SELECT proves the end-to-end API is fast."** No. Networking, serialization, driver, and application costs remain.

**36. "pg_stat_statements replaces EXPLAIN."** No. It measures cumulative workload, not the plan tree like EXPLAIN under specific conditions.

**37. "Parallel workers planned always equals launched."** No. Actual runtime resources may limit them.

**38. "EXPLAIN under one role is identical to under another role with RLS."** Not guaranteed. Roles, policies, and settings can affect access paths.

**39. "With many temp reads, just adding server RAM is enough."** No. You may need to fix the query, reduce JOIN fanout, or add an index.

**40. "No Index Scan means the query is definitely wrong."** No. SQL correctness is separate from execution plan choice.

---

## 29. Practice Exercises with Answers

### Exercise 1 — Distinguish Two Commands

**Question:** What is the difference between `EXPLAIN DELETE FROM orders WHERE id=1` and `EXPLAIN ANALYZE DELETE ...`?

**Answer:** `EXPLAIN` without ANALYZE builds the plan and normally does not execute the DELETE. `EXPLAIN ANALYZE` **runs the DELETE** and then displays actual runtime metrics.

### Exercise 2 — Reading Cost

Plan:

```text
Index Scan (cost=0.43..8.45 rows=1 width=32)
```

**Answer:** Startup cost 0.43, total cost 8.45 in planner estimate units; expects one row, 32 bytes wide. **Do not** infer a duration of 8.45 ms.

### Exercise 3 — Reading Loops

Plan:

```text
Index Scan (actual time=0.003..0.004 rows=1 loops=5000)
```

**Answer:** The node was invoked 5,000 times, averaging one row per call; total rows returned through the node is about 5,000. Not just one row in total.

### Exercise 4 — Explaining Seq Scan

A query reads 90% of a table's rows. The planner chooses Seq Scan.

**Answer:** Likely reasonable. A sequential table scan can be cheaper than traversing an index and fetching most of the heap. Measure in practice rather than labeling it a bug.

### Exercise 5 — Index Cond and Filter

Plan shows:

```text
Index Cond: (tenant_id = 2)
Filter: (amount > 100)
```

**Answer:** The index uses the tenant condition to locate entries; after fetching rows, the filter discards rows not meeting amount. Consider an index if the workload shows post-filtering is too costly.

### Exercise 6 — Measuring a Small Order Lookup

**Task:** View the actual plan and buffers for order ID 100.

**Answer:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, amount
FROM explain_lab.orders
WHERE order_id = 100;
```

This is a pure read-only SELECT on the lab table.

### Exercise 7 — Before/After Index Comparison

**Task:** Propose an index for a query filtering by tenant/status and sorting by created_at DESC.

**Answer:**

```sql
CREATE INDEX orders_tenant_status_created_idx_ex
ON explain_lab.orders (tenant_id, status, created_at DESC);
```

The lab table already has a similar `orders_tenant_status_created_idx` index in the lesson; the new index only illustrates syntax. In production, do not keep two duplicate indexes unless each provides distinct value.

### Exercise 8 — Why Is BUFFERS Useful?

**Answer:** It shows activity on shared/local/temp buffers, helping distinguish whether a query hits cache, reads many pages, or spills Sort/Hash to temp storage. Do not directly equate shared read with physical disk I/O.

### Exercise 9 — Reading Sort Spill

Plan reports:

```text
Sort Method: external merge Disk: 20480kB
Buffers: temp read=... written=...
```

**Answer:** Sort had to use temporary disk space. Investigate row counts to sort, index/ORDER BY alignment, fanout, and work_mem; do not blindly raise work_mem server-wide.

### Exercise 10 — Hash Join vs Nested Loop

**Question:** A Nested Loop inner index lookup shows `loops=100000`. What is worth investigating?

**Answer:** The number of inner lookups is very large, potentially consuming high I/O/CPU. Check cardinality, selectivity, join order, indexes, and possible planner misestimation. Do not conclude from node name alone.

### Exercise 11 — WAL of an UPDATE

**Task:** Test measuring WAL from updating 101 orders in the lab and rolling back.

**Answer:**

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE explain_lab.orders
SET archived = TRUE
WHERE order_id BETWEEN 100 AND 200;

ROLLBACK;
```

Run only in the lab. The UPDATE actually executes; rollback reverts table state but **does not reclaim WAL/I/O cost**.

### Exercise 12 — Sequences and ROLLBACK

**Question:** Why is `EXPLAIN ANALYZE SELECT nextval('explain_lab.test_seq')` dangerous if you only intended to "view the plan"?

**Answer:** The SELECT executes, `nextval()` allocates a real value, and the allocated number **does not roll back**. The sequence advances even if the test transaction is rolled back.

### Exercise 13 — SELECT Calling a Side Effect

**Question:** Is a SELECT calling a function that sends email safe when wrapped in BEGIN/ROLLBACK?

**Answer:** No. Sending an email is an effect outside PostgreSQL and is not rolled back automatically. Only measure in a mocked/test environment or after confirming no external side effects.

### Exercise 14 — Data-Modifying CTE

**Question:** Does `EXPLAIN ANALYZE WITH changed AS (UPDATE ... RETURNING ...) SELECT ...` modify the table?

**Answer:** Yes. The UPDATE inside the CTE is executed according to statement semantics, even though the outer query is a SELECT.

### Exercise 15 — Cascade

**Question:** Deleting a parent with 2 children under an `ON DELETE CASCADE` FK. Does `EXPLAIN ANALYZE DELETE parent` affect the children?

**Answer:** Yes. If the DELETE succeeds, both children are cascaded. `ROLLBACK` in the same transaction reverts the transactional changes to parent/children.

### Exercise 16 — Safely Viewing a DELETE Plan

**Task:** Only view the plan for deleting cancelled orders of tenant 3 without deleting data.

**Answer:**

```sql
EXPLAIN
DELETE FROM explain_lab.orders
WHERE tenant_id = 3
  AND status = 'cancelled';
```

Do not add `ANALYZE` if execution is not authorized.

### Exercise 17 — JSON Format

**Task:** Get the plan in JSON format for a SELECT by order_id.

**Answer:**

```sql
EXPLAIN (FORMAT JSON)
SELECT order_id
FROM explain_lab.orders
WHERE order_id = 100;
```

The output is the JSON structure of the plan, not JSON data rows of orders.

### Exercise 18 — Timing OFF

**Question:** Does `EXPLAIN (ANALYZE, TIMING OFF)` stop the query from executing?

**Answer:** No. It only disables detailed per-node timing measurement; the query still runs.

### Exercise 19 — Large Row Estimate Mismatch

Plan estimates 20 rows, actual is 20,000.

**Answer:** Investigate statistics, data skew, correlation, parameter/plan caching, and query structure. Large mismatches can cause the planner to pick unsuitable joins/sorts.

### Exercise 20 — Generic and Custom Plans

**Task:** Describe how to observe plan differences for a prepared statement.

**Answer:** Use `SET plan_cache_mode=force_custom_plan` and `EXPLAIN EXECUTE ...`, then `force_generic_plan` and EXPLAIN with the same parameters. `RESET` afterward. Do not force settings long-term without evidence.

### Exercise 21 — Plan vs API Latency

**Question:** EXPLAIN ANALYZE reports 5 ms, yet the API returns in 600 ms. Is the database definitely unrelated?

**Answer:** Not enough to conclude that. There may be network transfer, connection pool waits, different transactions/locks, serialization/deserialization time, and different parameters/plans between the app and the measurement.

### Exercise 22 — EXPLAIN ANALYZE on Production?

**Question:** Can you run `EXPLAIN (ANALYZE) DELETE ...` on production if you roll it back afterward?

**Answer:** Not safe by default. The delete still runs and can cause locks/WAL/triggers/sequences/external side effects. Prefer EXPLAIN without ANALYZE or a safe clone; only use a test transaction when all consequences are controlled and approved.

### Exercise 23 — Measuring COUNT(*)

**Question:** The root Aggregate returns actual rows=1; does that mean the whole query only read one row?

**Answer:** No. The Aggregate node may consume millions of rows from child nodes to compute COUNT(*), then return one result row. Inspect the entire tree.

### Exercise 24 — Reading Parallel Plans

```text
Workers Planned: 4
Workers Launched: 2
```

**Answer:** The planner expected four workers, but runtime only launched two. Analyze resource/settings constraints and rows processed by workers; do not assume planned = launched.

### Exercise 25 — Creating a Runbook Checklist for Measuring DML

**Suggested answer:** Confirm environment, target objects, FKs/triggers/functions, external side effects, sequences, transaction scope, replica/WAL impact, permissions/approval, rollback plan, and post-check; if not controllable, only use `EXPLAIN` or a database clone.

### Exercise 26 — Mistake Using EXPLAIN ANALYZE SELECT on a Custom Function

**Question:** If you do not know whether `do_work()` makes HTTP calls or writes files, can you treat it as a pure SELECT?

**Answer:** No. Read its contract/implementation and verify side effects first. Running `EXPLAIN ANALYZE SELECT do_work()` will execute the function if it lies on the execution path; `ROLLBACK` does not undo external side effects.

---

## 30. Checklist Before Using EXPLAIN in a Project

1. **Right database/role:** verify server, schema, and privileges before testing.
2. **Right statement:** does the SQL truly match what the application sends?
3. **Right parameters:** test representative parameter values, especially tenant/status and time ranges.
4. **Right goal:** do you only need the estimated plan or actual runtime metrics?
5. **Any side effects:** DML, write CTEs, volatile functions, `nextval()`, triggers, HTTP, email?
6. **If only viewing a DML plan:** use `EXPLAIN`, do not add `ANALYZE`.
7. **If measuring actual DML:** prefer an isolated clone/staging environment with side effects controlled.
8. **If using a test transaction:** do not mistakenly assume `ROLLBACK` undoes sequences and external systems.
9. **Checked FKs/triggers:** does the impact extend beyond the named table?
10. **Could it cause load:** CPU/I/O/WAL/locks/replication lag during real execution?
11. **Are statistics updated:** run `ANALYZE table` when appropriate, without confusing it with EXPLAIN ANALYZE.
12. **Read from root and children:** do not look at a single node and jump to conclusions.
13. **Distinguish cost from milliseconds:** cost is a relative estimate; actual time is measured.
14. **Read rows alongside loops:** actual rows of a looped node must be scaled by loops.
15. **Read Index Cond/Filter:** is the query leveraging the index or post-filtering too much?
16. **Read temp buffers:** did Sort/Hash spill?
17. **Read shared hit/read accurately:** do not equate read with physical disk reads.
18. **Read Join/SORT/Aggregate:** which node is driving resource consumption?
19. **Check generic/custom plans:** is a prepared statement's plan parameter-sensitive?
20. **Control measurement variance:** caching, concurrency, and dataset stability.
21. **Do not force planner settings system-wide:** experimental settings must be reset.
22. **Do not create an index from a single EXPLAIN:** check write overhead and overall workload.
23. **Measure end-to-end when needed:** network, connection pool, ORM, response encoding.
24. **Record results and changes:** SQL, parameters, plan, version, timestamp, and rollback plan.
25. **Do not treat EXPLAIN as business protection:** permissions, RLS, constraints, and concurrency control are still required.

---

## 31. Summary

**`EXPLAIN` helps you understand how PostgreSQL intends to run a statement; `EXPLAIN ANALYZE` actually runs the statement and reports real metrics.** This distinction is both the key to performance tuning and a critical data-safety boundary.

To read plans accurately:

- Start from the **node tree**, not just the top line.
- Distinguish **estimated `cost`/`rows`** from **actual `actual time`/`actual rows`**.
- Always inspect **`loops`**, `Index Cond`, `Filter`, `Rows Removed by Filter`, `BUFFERS`, and signs of temp I/O.
- Understand that **Seq Scan is not automatically bad**; Nested Loop, Hash Join, Merge Join, Sort, and Aggregate are all context-dependent choices.
- Use statistics, data distribution, indexes, join order, prepared-plan behavior, and repeated measurements to explain differences.

To use safely:

- **`EXPLAIN` without `ANALYZE`** is the proper way when you only need to inspect the plan of a write command.
- **`EXPLAIN ANALYZE INSERT/UPDATE/DELETE/MERGE` executes real changes**.
- **`EXPLAIN ANALYZE SELECT` can also have side effects** if the query calls sequences, volatile functions, or contains a data-modifying CTE.
- **`BEGIN ... ROLLBACK` does not undo everything**: sequences, emails, HTTP calls, external queues/files, and consumed resource costs can still leave consequences.
- When needing to measure large DML or external dependencies, prefer an **isolated practice/clone environment**, understand triggers/FKs, and control transactions beforehand.

**Final rule:** before typing `ANALYZE` into an `EXPLAIN` command, ask **"if this entire statement actually runs right now, what will it read, write, lock, invoke, and affect?"**. If you cannot answer that yet, do not run `EXPLAIN ANALYZE` on important data.

### Official PostgreSQL Documentation

- [EXPLAIN — syntax and options](https://www.postgresql.org/docs/current/sql-explain.html).
- [Using EXPLAIN — how to read execution plans](https://www.postgresql.org/docs/current/using-explain.html).
- [Planner Statistics](https://www.postgresql.org/docs/current/planner-stats.html).
- [ANALYZE — updating table statistics](https://www.postgresql.org/docs/current/sql-analyze.html).
- [Sequences — nextval() function and semantics](https://www.postgresql.org/docs/current/functions-sequence.html).
- [WITH Queries — Data-Modifying Statements](https://www.postgresql.org/docs/current/queries-with.html).
- [CREATE TRIGGER and foreign keys](https://www.postgresql.org/docs/current/sql-createtrigger.html).
- [Resource Consumption — work_mem](https://www.postgresql.org/docs/current/runtime-config-resource.html).
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
