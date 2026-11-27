# Evaluating Designs Using Query Plans and Appropriately Scaled Data

A schema with primary keys, foreign keys, data types, and indexes still cannot be considered a **good physical design** just because every SQL statement runs on a few hundred records. In practice, the same query may take milliseconds on test data yet stall for seconds with millions of rows, an unusual subset of heavy customers, years of accumulated history, or high concurrent write traffic.

Evaluating a physical model requires connecting three layers of evidence:

1. **Business requirements and real workload:** which screens/APIs/reports matter; what are the latency, throughput, and storage budgets?
2. **Query execution plan:** how does the DBMS plan to—and actually—read, filter, JOIN, sort, and aggregate data?
3. **Appropriately scaled and distributed data:** do row counts, widths, value distributions, skew, NULL ratios, cross-column correlations, write/delete rates, and resource contention resemble operating conditions?

This lesson belongs to the **Physical Modeling** chapter of **DATABASE_DATA_MODELING**. The goal is not picking an index by intuition, but knowing how to **form a hypothesis, run repeatable experiments, read evidence, change one factor, remeasure, and document trade-offs**. Examples use PostgreSQL; principles of row volume, selectivity, query plans, and benchmarking apply equally when evaluating relational, document, graph, and analytical databases.

> **Principle:** You cannot conclude "index A is faster than B" from an index type name alone or an EXPLAIN lacking execution metrics. You must ground conclusions in **the right query, the right data, the right system state, and the right measurements**.

## 1. Distinguishing Logical Design from Physical Design

In logical design, a sales system might consist of Customer, Product, SalesOrder, and OrderLine with clear relationships and constraints:

~~~text
Customer (1) ── (N) SalesOrder (1) ── (N) OrderLine (N) ── (1) Product
~~~

The logical model answers: who is who, which customer owns an order, which product each line references, and which keys must be unique.

Physical design adds decisions such as:

- Exact data types, field lengths, and row widths.
- How primary keys and foreign keys are stored, plus indexes serving query patterns.
- Whether multi-column indexes, partial indexes, covering indexes, BRIN, or partitioning are needed.
- How many rows queries should return, and whether pagination uses keysets or OFFSET.
- Which aggregate queries are permitted to scan large data volumes.
- How optimizer statistics, vacuuming, aging data, history, and archiving are managed.
- Whether derived structures, summary tables, or caches are needed for specific read paths.
- Effects on **data writes**, transactions, locking, disk space, backups, and schema migration downtime.

Any physical choice is valid only in **a workload context**. An index on a low-cardinality status column may add little value for a query reading 70% of the table, whereas a partial index filtering a rare status combined with a date predicate may shine for a narrow report.

## 2. Inputs for a Rigorous Evaluation

Before opening EXPLAIN, write down verifiable assumptions.

| Factor | Questions to Answer | Example |
| --- | --- | --- |
| Current scale | How many rows in each table? | 250k Orders, 1.25M OrderLines |
| Projected scale | How many rows in 12–24 months? | Order count grows 5x |
| Data distribution | Are there dominant hot values? | 10% of customers generate most new orders |
| Historical depth | Is old data retained intact? | Paid orders kept for many years |
| Critical queries | Which APIs have high frequency and latency sensitivity? | Fetch a customer's 20 latest orders |
| SLO | What are the acceptance thresholds? | E.g., p95 target under 150 ms, **set by the product** |
| Write load | How many INSERT/UPDATE/DELETE ops per second? | Creating orders, status updates, stock intake |
| Concurrency | How many sessions compete for resources? | 50 concurrent sessions at peak |
| Environment | CPU, RAM, disk, cache, DBMS version? | PostgreSQL on production-comparable hardware |

An **SLO (service level objective)** is an operational target agreed upon by the team, **not a PostgreSQL default**. Clarify whether you are measuring server-side SQL execution time, full API request time, or end-user device latency. A 20 ms SQL query does not imply a 20 ms API response once network, app logic, connection pooling, and serialization enter the picture.

### 2.1. Three Sample Query Classes

In our sales example, we test three queries with distinct profiles:

1. **Short OLTP lookup:** fetch the 20 latest orders for a `customer_id`.
2. **Operational list:** fetch 50 recent `PAID` orders.
3. **Aggregation:** unit sales by product over the last 30 days.

Query (1) requires high selectivity and returns few rows; query (2) depends on time and status selectivity; query (3) may read and aggregate hundreds of thousands of OrderLines.

**Do not force identical latency targets on all three** when their roles and costs differ. Set performance budgets per query class according to frequency and user impact.

## 3. Build a Test Schema with Real Keys and Constraints

Experiments are far more trustworthy when PKs, FKs, UNIQUE, CHECK, and target data types match the intended design. Stripping constraints just to bulk-load faster and then benchmarking writes hides real referential check and index maintenance costs.

PostgreSQL example, run only in a **dedicated development/benchmark environment**:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    region_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    list_price_cents BIGINT NOT NULL CHECK (list_price_cents >= 0)
);

CREATE TABLE orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no SMALLINT NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Key design points:

- OrderLine's primary key is **(order_id, line_no)**, matching row identity within an order.
- OrderLine references Product, yet **unit_price_cents** captures the price locked at purchase time; it need not match Product's current price.
- Amounts use integers in the currency's minor unit in this example, avoiding floating-point drift during sums. Multi-currency systems also need currency codes and rounding policies.
- Child-table FKs do not auto-create indexes on **every FK column** in PostgreSQL; index choices are driven by the queries below.

### 3.1. Loading Data with Intentional Distribution and Skew

Use `generate_series` to populate 50,000 customers, 3,000 products, 250,000 orders, and 5 lines per order (1,250,000 lines). This dataset is large enough for plan differences to emerge, though **not yet a production-scale benchmark**.

~~~sql
-- Run once on an empty test database.
INSERT INTO customers (customer_id, region_code, created_at)
SELECT n,
       CASE
           WHEN n % 10 < 7 THEN 'HCM'
           WHEN n % 10 < 9 THEN 'HN'
           ELSE 'OTHER'
       END,
       CURRENT_TIMESTAMP - ((n % 365) * INTERVAL '1 day')
FROM generate_series(1, 50000) AS g(n);

INSERT INTO products (product_id, title, list_price_cents)
SELECT n,
       'Product ' || n,
       10000 + (n % 101) * 500
FROM generate_series(1, 3000) AS g(n);

INSERT INTO orders (order_id, customer_id, status, created_at)
SELECT n,
       CASE
           -- Small group of customers with far more orders than average.
           WHEN n % 11 = 0 THEN (n % 100) + 1
           ELSE ((n * 37) % 49900) + 101
       END,
       CASE
           WHEN n % 10 < 7 THEN 'PAID'
           WHEN n % 10 < 9 THEN 'PENDING'
           ELSE 'CANCELLED'
       END,
       CURRENT_TIMESTAMP
           - ((n % 365) * INTERVAL '1 day')
           - ((n % 86400) * INTERVAL '1 second')
FROM generate_series(1, 250000) AS g(n);

INSERT INTO order_lines
    (order_id, line_no, product_id, quantity, unit_price_cents)
SELECT o.order_id,
       s.line_no,
       p.product_id,
       1 + ((o.order_id + s.line_no) % 3)::INTEGER,
       p.list_price_cents
FROM orders AS o
CROSS JOIN generate_series(1, 5) AS s(line_no)
JOIN products AS p
  ON p.product_id = CASE
      -- Roughly 70% of lines concentrate on 80 popular products.
      WHEN (o.order_id + s.line_no) % 10 < 7
        THEN ((o.order_id * 37 + s.line_no) % 80) + 1
      ELSE ((o.order_id * 17 + s.line_no * 13) % 2920) + 81
  END;
~~~

These generator constants merely create an **intentional test distribution**, not a realistic probabilistic model of a live marketplace. We deliberately introduce **skew**: heavy-buying customers and popular products. This surfaces edge cases hidden by uniform synthetic data.

**Repeatability note:** `CURRENT_TIMESTAMP` shifts relative dates on every reload, and modulo arithmetic introduces periodic correlation. When comparing across test sessions, pin a **fixed reference timestamp** and **dataset version**, or log load timestamps alongside verification counts. Never assume formula-generated data matches real-world physical correlation.

After loading:

~~~sql
ANALYZE customers;
ANALYZE products;
ANALYZE orders;
ANALYZE order_lines;
~~~

PostgreSQL needs **up-to-date statistics** to estimate row counts, value distributions, and plan costs. Benchmarking right after loading millions of rows without `ANALYZE` can misjudge a solid schema simply because the optimizer lacks accurate stats.

### 3.2. Verify the Dataset Before Benchmarking

~~~sql
SELECT 'customers' AS object, COUNT(*) AS rows FROM customers
UNION ALL
SELECT 'products', COUNT(*) FROM products
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'order_lines', COUNT(*) FROM order_lines;

SELECT status, COUNT(*) AS order_count
FROM orders
GROUP BY status
ORDER BY status;

SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
ORDER BY order_count DESC
LIMIT 10;

SELECT product_id, COUNT(*) AS line_count
FROM order_lines
GROUP BY product_id
ORDER BY line_count DESC
LIMIT 10;
~~~

The generator's **target counts** are 50,000, 3,000, 250,000, and 1,250,000 rows if all inserts succeed once on empty tables. In real runs, inspect returned counts and record **actual row counts**—never treat target numbers as observed results.

If hardware resources are constrained, you can scale counts down, provided you explicitly document the scaling factor. Benchmarking 2,500 orders does not represent 250 million orders just because both share the same schema.

## 4. How Does EXPLAIN Differ from EXPLAIN ANALYZE?

PostgreSQL provides two primary tiers of plan visibility:

~~~sql
-- Shows estimated plan only, without executing the SELECT.
EXPLAIN
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

-- Executes the SELECT and collects actual runtime metrics.
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

| Aspect | EXPLAIN | EXPLAIN ANALYZE |
| --- | --- | --- |
| Runs the query? | Does not execute the underlying SELECT | **Yes**, executes the underlying query |
| Shows estimated costs? | Yes | Yes |
| Shows actual rows and loops? | No | Yes |
| Shows actual per-node timings? | No | Yes, unless timing is turned off |
| Shows buffer stats when requested? | Cost metadata only, not runtime buffers | Yes with `BUFFERS` |
| When to use? | Inspecting plans, especially for state-changing statements | Measuring queries in environments where execution is permitted |

**Mandatory warning:** `EXPLAIN ANALYZE` **actually executes** `INSERT`, `UPDATE`, and `DELETE` when wrapping a write statement. Never run `EXPLAIN ANALYZE` on write queries against production data just to inspect a plan.

In a test environment, you can wrap DML probes in a transaction and `ROLLBACK`:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = 12345;

ROLLBACK;
~~~

`ROLLBACK` reverts normal **in-transaction** row changes, yet does not undo sequence increments, external service calls inside triggers, or non-transactional side effects. Always **isolate test environments and control side effects**; never treat this pattern as guaranteed production safety.

### 4.1. Useful Options

~~~sql
-- Include relevant modified settings and structured output.
EXPLAIN (ANALYZE, BUFFERS, SETTINGS, FORMAT JSON)
SELECT order_id
FROM orders
WHERE customer_id = 42;

-- Reduce per-node timing measurement overhead when needed:
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
SELECT COUNT(*)
FROM order_lines;
~~~

`FORMAT JSON` is convenient for storing, parsing, or automating plan comparisons. Plans still depend on PostgreSQL version, data state, statistics, and settings, so never declare a regression solely from raw text diffs.

## 5. Reading a Query Plan from Bottom to Top

A query plan is an **execution operator tree**. Common nodes:

| Plan Node | Main Job | Signals to Check |
| --- | --- | --- |
| **Seq Scan** | Reads table rows sequentially | Fraction of table read; filters; buffers |
| **Index Scan** | Finds rows via index, then fetches heap as needed | `Index Cond`, heap pages visited, selectivity |
| **Index Only Scan** | Reads columns directly from index when visibility permits | `Heap Fetches`; index coverage and visibility map |
| **Bitmap Index/Heap Scan** | Collects row locations from index, then reads heap pages | `Recheck Cond`, lossy pages, and page count |
| **Nested Loop** | For each outer row, probes matching inner rows | `loops`, cardinality, inner index |
| **Hash Join** | Builds hash table from one input and probes from the other | Hash size, batches, and memory |
| **Merge Join** | Merges two inputs sorted by join key | Already sorted vs. explicit `Sort` |
| **Sort** | Sorts rows | Sort Method, Memory/Disk, row count |
| **HashAggregate/GroupAggregate** | Groups and aggregates rows | Group count, memory, disk spill |
| **Limit** | Stops returning rows after threshold | Avoids full scan, or still requires full sort/aggregate? |
| **Gather/Gather Merge** | Coordinates parallel workers | Workers Planned/Launched, work distribution |

**Never assume `Seq Scan` is always bad or `Index Scan` is always good.** Reading most of a small table sequentially is often cheaper than hopping randomly across pages through an index. Conversely, fetching 20 rows from a giant table benefits enormously from an index matching filter and sort order.

### 5.1. Cost Is Not Milliseconds

A plan line may look like:

~~~text
Index Scan using idx_orders_customer_recent on orders
  (cost=0.42..15.30 rows=20 width=24)
~~~

This is **an illustrative output shape only**, not a run against Section 3's dataset. Cost numbers are **relative planner cost units**, not 0.42 ms or 15.30 ms. The planner compares estimates to pick the lowest-cost plan among candidates evaluated.

With `EXPLAIN ANALYZE`, a node also includes:

~~~text
(actual time=0.050..0.180 rows=20 loops=1)
~~~

`actual time` values reflect a specific execution, environment, and instrumentation overhead. **Never cite these illustrative values as benchmark results**.

### 5.2. Estimated Rows, Actual Rows, and Loops

This is one of the most revealing comparisons:

- **Estimated `rows`:** rows the optimizer predicts the node emits **per execution**.
- **`actual rows`:** average/actual rows emitted per execution loop.
- **`loops`:** number of times the node executed, crucial inside Nested Loops.
- **Approximate total work** relates to `actual rows × loops`, alongside filtered rows, heap pages, and child nodes.

If the planner estimates 10 rows while actual execution produces 100,000 rows, the optimizer may pick the wrong JOIN algorithm or join order. Root causes often lie in **missing/stale statistics, column correlation, skew, filter expressions, or bind parameters**—not merely a "missing index".

### 5.3. `Filter` Differs from `Index Cond`

In a plan:

- **`Index Cond`** shows predicates used to narrow index traversal.
- **`Filter`** shows predicates evaluated after rows reach that node.
- **`Rows Removed by Filter`** reports how many rows were discarded at that node.

An index on `status` alone locates status entries, yet if the query also filters `customer_id` and `created_at` without index support, PostgreSQL may fetch huge row sets only to discard most via `Filter`. Watch **the ratio of rows read to rows returned**, not just the label "Index Scan".

### 5.4. Buffers and Limits of Reading Buffer Counters

With `BUFFERS`, you observe counters like:

- **`shared hit`:** buffer pages found in PostgreSQL's shared buffer cache.
- **`shared read`:** buffer pages read into shared buffers; not strictly equal to physical disk reads due to OS page cache.
- **`shared dirtied/written`:** pages dirtied or flushed during execution.
- **`temp read/written`:** temporary file I/O, typically from sorts or hashes spilling out of memory.

A high `shared hit` count is **not automatically a bug**, nor does `shared read` directly measure disk I/O latency. Read buffers alongside execution time, loops, cache warmth, and host specs.

## 6. Case Study A: Querying a Customer's 20 Most Recent Orders

Query powering the "Order History" screen:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

### 6.1. Evaluating the Design Before Adding an Index

The `orders` table initially has only a PK on `order_id`, which **provides no direct support** for filtering `customer_id` and sorting by time. The planner may choose `Seq Scan` plus `Sort`, or another plan depending on scale. Reading the primary key name alone never exposes this bottleneck.

Measure the baseline plan:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Record: runtime, accurate row count, plan shape, estimated/actual rows, buffers, and whether `Sort` appears.

### 6.2. Adding an Index Matching Predicates and Sort Order

~~~sql
CREATE INDEX idx_orders_customer_recent
ON orders (customer_id, created_at DESC, order_id DESC)
INCLUDE (status);

ANALYZE orders;
~~~

Rationale:

1. **`customer_id`** first supports the equality predicate.
2. **`created_at DESC, order_id DESC`** aligns with display sort order, especially when two orders share `created_at`.
3. **`LIMIT 20`** enables early stopping after 20 rows if the plan scans the index in order.
4. **`INCLUDE(status)`** puts `status` into the index to allow `Index Only Scan` for this query.

Still, **`Index Only Scan` is not guaranteed**, and even when chosen it can incur **`Heap Fetches`** if table pages are not marked all-visible. Under heavy updates, visibility map state, `VACUUM`, and index width matter heavily. `INCLUDE` never means "guaranteed zero heap access".

Rerun **the exact same SQL** with identical data and settings; compare before vs. after. The new index also increases disk space and `INSERT`/`UPDATE`/`DELETE` work on `orders`, so measure write impact too.

### 6.3. Testing Both Heavy and Typical Customers

Example benchmarking across a "hot" customer and an ordinary customer:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 7
ORDER BY created_at DESC, order_id DESC
LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 10007
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

These two IDs are **test examples only**, not guaranteed to hold identical counts. Inspect actual distribution before classifying hot/cold customers. A good index can help both while latency and page reads still differ due to row count, data locality, and cache state.

**Takeaway:** benchmarking a single `customer_id` fails to represent customers with tens of thousands of orders or customers with just one order.

## 7. Case Study B: Filtering by Status and Date

Operational query:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE status = 'PAID'
  AND created_at >= CURRENT_TIMESTAMP - INTERVAL '7 days'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

In our sample dataset, `PAID` accounts for most orders, so an index **on `status` alone** has poor selectivity. Rather than blindly adding a single-column index, evaluate a **partial index**:

~~~sql
CREATE INDEX idx_orders_paid_recent
ON orders (created_at DESC, order_id DESC)
WHERE status = 'PAID';
~~~

Potential advantages:

- Contains only `PAID` rows.
- Uses creation timestamp to bound the time window and satisfy `ORDER BY`.
- Can stop early once 50 most recent rows are found.

Yet if nearly the whole table is `PAID`, the partial index remains **very large**. Net benefit depends on time selectivity, index size, status churn, and heap fetches.

### 7.1. Partial Indexes Rely on Predicate Implication

The planner must prove the query's `WHERE` clause **implies** the partial index predicate. A literal `status = 'PAID'` is obvious. However, a prepared statement with `status = $1` may skip the partial index under a **generic plan** because the parameter value is unknown at plan time.

Never declare a partial index "broken" from a literal SQL test when the app uses parameterized queries—or vice versa. Benchmark **the exact query form emitted by the application**, including custom/generic plans and realistic parameter distributions.

### 7.2. Time-Series Data Must Mirror Operations

When historical orders comprise 95% of the table and recent orders only 5%, a `created_at` index shines for recent-window screens. Yet on a tiny test table holding only 7 days of data, the same query reads nearly the whole table.

Therefore generate:

- Both **recent and historical** data following realistic age distributions.
- Peak-season bursts if the business is seasonal.
- Realistic status shares correlated with order age where applicable.
- Frequent updates/deletes to test MVCC, `VACUUM`, and index bloat when relevant to production.

## 8. Case Study C: Aggregating Sales by Product

Reporting requirement: for `PAID` orders in the last 30 days, return the top 20 products by units sold.

~~~sql
SELECT l.product_id,
       SUM(l.quantity)::BIGINT AS units_sold
FROM orders AS o
JOIN order_lines AS l ON l.order_id = o.order_id
WHERE o.status = 'PAID'
  AND o.created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days'
GROUP BY l.product_id
ORDER BY units_sold DESC, l.product_id
LIMIT 20;
~~~

This SQL measures **units sold**, not **revenue**. For revenue, sum `quantity × transaction unit price`, accounting for refunds/adjustments, currencies, and recognition timestamps. Never substitute Product's current `list_price_cents` for historical transaction prices.

### 8.1. What to Inspect in the Plan?

- **Are `orders` filtered early?** How many `PAID` orders exist in 30 days relative to the entire table?
- **Which JOIN strategy is picked?** Hash Join, Nested Loop, or Merge Join, and why?
- **How are `order_lines` accessed?** Via `PK(order_id, line_no)` per Order, or scanning most of `order_lines`?
- **Pre-aggregation estimates:** how many input rows enter `GROUP BY`?
- **Do `GROUP BY`/`SORT` spill to disk?** Look for `temp read/written` or `Sort Method: external`.
- **Does `LIMIT 20` skip aggregation?** Usually **no**: finding the top 20 products still requires aggregating all qualifying rows before sorting and taking the top 20.

Do not expect simply indexing `product_id` to speed up every top-products query. This query **aggregates filtered Orders**, so runtime is governed by rows scanned, join method, and aggregation cost.

### 8.2. Checking Acceleration by Source Access Path

If the query filters Orders first and looks up each order's lines, `PK(order_id, line_no)` already serves `order_lines` lookups by `order_id`.

If the application also frequently runs:

~~~sql
SELECT order_id, line_no, quantity
FROM order_lines
WHERE product_id = 52
ORDER BY order_id DESC
LIMIT 100;
~~~

then consider a separate index:

~~~sql
CREATE INDEX idx_order_lines_product_order
ON order_lines (product_id, order_id DESC);
~~~

This index serves a **different query pattern** and must not be assumed to optimize full-range product `GROUP BY`s automatically. Weigh every added index against storage footprint and `order_lines` insert throughput.

### 8.3. When Is a Summary Table Needed?

If similar heavy aggregations run continuously over massive history, consider a daily summary table:

~~~text
product_daily_sales(
    sales_date,
    product_id,
    units_sold,
    gross_amount_cents,
    currency,
    ...
)
~~~

Derived tables reduce report scan volume while adding obligations:

- Define **grain**: one row per date–product–currency.
- Handle `CANCELLED` orders, returns, and late adjustments past initial recording.
- Decide synchronous vs. asynchronous updates and acceptable freshness lag.
- Ensure **idempotency** so job retries never double-count sales.
- Reconcile totals against **the raw transaction source** to catch drift.

Never denormalize into rollup tables prematurely before proving that well-tuned queries over source tables fall short.

## 9. Why Does the Planner Misestimate Row Counts?

Even well-chosen indexes get skipped when the planner misestimates row counts. PostgreSQL relies on sampled statistics and bounded assumptions; common causes of misestimation include:

| Cause | Symptom | Where to Investigate |
| --- | --- | --- |
| **Stale statistics** | Estimated rows diverge wildly after bulk loads/deletes | `ANALYZE`, `autovacuum`/`autoanalyze` |
| **Skew** | "Hot" values behave completely differently from averages | Inspect top values and `most_common_vals` |
| **Cross-column correlation** | Combined predicates misestimate despite per-column stats | Extended statistics where appropriate |
| **Growing time-series** | Recent data differs sharply from older data | Histograms, partitions, refreshed stats |
| **Expressions/functions in `WHERE`** | Poor row estimates or unusable indexes | Rewrite predicates into index-friendly ranges |
| **Bind parameters** | Same SQL behaves differently across parameter values | Custom vs. generic plans and parameter distribution |
| **Many-to-many JOINs** | Output explodes beyond expectations | Check multiplicities, keys, FKs, grain, and join predicates |

### 9.1. Inspecting Baseline Statistics

~~~sql
SELECT schemaname, tablename, attname,
       null_frac, n_distinct,
       most_common_vals, most_common_freqs
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename IN ('orders', 'order_lines')
  AND attname IN ('customer_id', 'status', 'product_id')
ORDER BY tablename, attname;
~~~

The **`pg_stats`** view reveals sampled distributions including common values and frequencies. These are **estimates**, not an exact inventory of every row. Pair them with `COUNT`/`GROUP BY` queries when verifying hot subsets.

When column stats lack resolution, you can raise the **`statistics target`** and rerun `ANALYZE`, at the cost of slower `ANALYZE` runs and larger stats storage.

~~~sql
-- Example: use only after observing significant estimation error.
ALTER TABLE orders
ALTER COLUMN customer_id SET STATISTICS 500;

ANALYZE orders;
~~~

Do not raise statistics targets on every column by habit. Measure plan impact afterward and account for maintenance overhead.

### 9.2. Extended Statistics: Correlated Columns

If `PAID` occurs mostly on older orders or specific customer segments, assuming column independence misestimates combined predicates.

PostgreSQL supports extended statistics across columns within **the same table**, for example:

~~~sql
CREATE STATISTICS st_orders_status_customer
    (mcv, dependencies)
ON status, customer_id
FROM orders;

ANALYZE orders;
~~~

This helps the planner recognize **common value combinations** or functional dependencies. However, extended statistics are **no silver bullet for every misestimate**, especially cross-table estimates or complex range filters; applicability depends on stats type, query shape, and PostgreSQL version.

### 9.3. Queries Written in Index-Blocking Ways

Suppose you want orders for a specific day:

~~~sql
-- Can prevent clean use of a plain index on created_at:
SELECT order_id
FROM orders
WHERE created_at::date = DATE '2026-11-20';
~~~

With `TIMESTAMPTZ`, casting to `DATE` also depends on session timezone. If the requirement is **a calendar day in a business timezone**, compute explicit timestamp boundaries and use a half-open range:

~~~sql
-- Example: 2026-11-20 in UTC.
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-11-20 00:00:00+00'
  AND created_at <  TIMESTAMPTZ '2026-11-21 00:00:00+00';
~~~

Half-open ranges cleanly use B-tree indexes on `created_at`. For Vietnam local dates, convert **both local midnight boundaries** to corresponding instants; never silently substitute UTC, which shifts business results.

## 10. Pagination, `ORDER BY`, and `LIMIT`

A seemingly API-level choice can completely reshape the query plan.

### 10.1. Deep `OFFSET`

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 10000;
~~~

Even with a matching ordered index, the DBMS still must **walk past 10,000+ rows** and discard them before returning 20 rows. `OFFSET` is fine for shallow UI pagination, yet grows expensive on deep pages.

### 10.2. Keyset Pagination

When the screen knows **`created_at` and `order_id` from the prior page's last row**, use a keyset cursor:

~~~sql
SELECT order_id, created_at, status
FROM orders
WHERE customer_id = 42
  AND (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-20 10:15:00+00', 123456)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

When both columns sort descending and `order_id` breaks ties, tuple comparison resumes straight from that cursor without skipping thousands of rows. The query must match **the exact sort-key pair**, use a deterministic tie-breaker, and account for concurrent inserts/updates between page fetches.

**Never hardcode example cursor values as real data.** Applications extract the cursor from the last fetched row. For mixed `ASC`/`DESC` sort orders, rewrite the comparison predicate accordingly.

### 10.3. Verifying Sort Determinism

`ORDER BY created_at DESC` alone leaves tied timestamps in arbitrary order. Adding **`order_id DESC`** as a tie-breaker stabilizes pagination and keeps benchmark plan comparisons consistent. Under concurrent writes, items can still shift between page reads; strict page stability requires snapshots or feed-specific semantics.

## 11. Indexes Are Trade-Offs, Not Report-Card Points

An index helps when it saves substantial reading or sorting, yet it also:

- Consumes disk space and affects backup/replication footprints.
- Adds maintenance work to `INSERT`, `UPDATE`, and `DELETE`.
- Can increase WAL volume and index bloat.
- Can alter plans for unrelated queries, sometimes unexpectedly.
- Depends on selectivity and data distribution, not just column names.

### 11.1. Column Order in Composite Indexes

The index:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

serves queries fetching **one customer's** orders sorted by `created_at`. Yet queries filtering only `created_at` across **all customers** do not get the same optimal access as an index leading with `created_at`.

Before adding an index, check existing indexes, shared prefixes, `ORDER BY`, equality/range predicates, and column churn. Near-duplicate indexes slow writes without commensurate read benefits.

### 11.2. BRIN for Very Large, Physically Ordered Data

BRIN stores block-range summaries and can fit timestamp columns on huge tables when **`created_at` correlates strongly with physical row placement**. It is far smaller than a B-tree in suitable workloads, yet reads and rechecks wider page ranges.

~~~sql
-- Illustrates a candidate to benchmark on very large order tables:
CREATE INDEX idx_orders_created_brin
ON orders USING brin (created_at);
~~~

Never assume BRIN beats B-tree. In our modulo-generated test dataset, `created_at` wraps cyclically with `n`, so physical order **correlates poorly** with creation time—making BRIN ineffective there. Evaluate BRIN only on datasets loaded in **production-realistic physical order**.

### 11.3. Partitioning Does Not Automatically Speed Up Queries

Time-based partitioning is often proposed once `orders` reaches hundreds of millions of rows. It can help:

- Limit scanned partitions when `WHERE` enables **partition pruning**.
- Manage aging data periodically, e.g., archiving or dropping whole partitions per policy.
- Isolate maintenance tasks across large datasets.

Yet partitioning adds operational overhead and changes key/uniqueness rules, indexes, FKs, query plans, and writes. If queries omit the partition key or join across dozens of partitions, gains shrink or turn negative.

**Never partition a 250k-row table just because it has a `created_at` column.** Identify the concrete problem—query latency, historical retention, oversized indexes, or maintenance—then benchmark a realistic partition count and dataset size.

## 12. Proper Benchmarking: Never Run One Query Once

A single `EXPLAIN ANALYZE` is **diagnostic evidence**, not a reliable benchmark.

### 12.1. Recording the Environment

Document at minimum:

- PostgreSQL version, relevant extensions, CPU/RAM/storage.
- Relevant settings: `shared_buffers`, `work_mem`, `effective_cache_size`, `random_page_cost`, `max_parallel_workers_per_gather`, and actual tuned values.
- Table row counts, data/index sizes, distributions, and fragmentation.
- `ANALYZE`/`VACUUM` state and estimated cache residency.
- Concurrent users/jobs generating background load.
- Exact SQL matching the app: JOINs, parameters, `LIMIT`, sorting, `SELECT` list, and isolation level.

You need not dump the entire server config, yet record every variable that could flip conclusions. Never compare laptop millisecond timings directly to production as predicted production latency.

### 12.2. Distinguishing Warm Cache from Cold Cache

- **Warm cache:** hot tables/indexes sit in memory caches, minimizing storage reads.
- **Cold cache:** pages are not cached yet and must be read through OS/DB buffers.

A slow first query followed by fast repeats is normal. Conversely, benchmarking only on warm caches masks disk bottlenecks when working sets exceed RAM.

Never carelessly wipe caches on shared hosts to simulate cold caches. Use isolated environments, consistent measurement protocols, and explicit cache conditions. Repeat runs and discard or isolate warmup passes appropriately.

### 12.3. Sample Counts and Aggregation

A practical procedure:

1. Load test data and run `ANALYZE`.
2. Record baseline plans and latencies before changes.
3. Run multiple iterations across parameter classes: hot customers, low-volume customers, wide/narrow date ranges.
4. Record median, p95, max, returned rows, buffers, and variance.
5. Change **one variable** (e.g., add `idx_orders_customer_recent` alone).
6. Repeat the exact parameter set and equivalent load.
7. Remeasure **write throughput**, index footprint, and other critical queries.
8. Decide against pre-agreed acceptance criteria, not a single best millisecond run.

Example results template **to populate after running**, not measured data:

| Query | Parameter Set | Plan | p50 (ms) | p95 (ms) | Buffers/Read | Rows Returned |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| Order history | Hot customer | Before index | — | — | — | — |
| Order history | Hot customer | After index | — | — | — | — |
| Order history | Low-volume customer | Before index | — | — | — | — |
| Order history | Low-volume customer | After index | — | — | — | — |
| Top products | 30 days | Before change | — | — | — | — |
| Top products | 30 days | After change | — | — | — | — |

A p95 computed from 5 runs is highly unstable. Tail percentiles need enough samples, randomized or cache-controlled ordering, and explicit parameter selection rules. For **API** p95, measure at the HTTP request layer under representative load—never pass off internal `EXPLAIN` times as full-system p95.

### 12.4. Single-Session vs. Multi-Session Measurements

A single-session **`EXPLAIN ANALYZE`** shows how one query executes in isolation. It **cannot** measure throughput, connection-pool waits, lock contention, transaction throughput, or concurrent I/O across dozens of active sessions.

Concurrency benchmarks need proper load drivers in isolated environments with defined read/write mixes, arrival rates, and test durations. Never crank up concurrency blindly and blame one index for saturation without diagnosing CPU, I/O, locking, and pool bottlenecks.

## 13. Fast Reads Mean Little If Writes Break or Slow Down

Adding an index to accelerate order history can slow order creation, status updates, or historical purges. Physical evaluation must look both ways.

### 13.1. Measuring Core Write Paths

Benchmark dedicated tests for:

- `INSERT` Order and 5 OrderLines in one transaction.
- `UPDATE` Order from `PENDING` to `PAID`.
- `UPDATE` status or shipping address.
- Cancellations/refunds (if modeled).
- Archiving aging data or detaching partitions.

Even when `status` is an `INCLUDE` column, changing `status` still requires index maintenance. Read-optimizing index changes are rarely write-free.

### 13.2. Never Strip FKs or Atomicity

In benchmarks with orders and order lines, keep **OrderLine referencing existing Orders**. Dropping FKs to load fast without restoring them measures a **different** design from the business requirement.

Likewise, if creating a 5-line order must be atomic, benchmark a single transaction inserting both Order and OrderLines. Comparing against autocommit line-by-line inserts or `COPY` batches is valid only when testing real write paths or clearly labeled separate baselines.

### 13.3. Fast Metrics with Broken Semantics

A query returning 20 rows blazingly fast that:

- sorts inconsistently on tied timestamps;
- omits the `tenant_id` filter;
- joins `Product`'s current price instead of historical line prices;
- multiplies `OrderLine` rows via an ungrouped many-to-many join;
- or drops rows due to unstable pagination;

fails acceptance. **Correctness is a prerequisite**, never a trade-off for lower latency.

## 14. Testing at the Right Scale: Multiple Sizes and Edge Cases

A representative test suite covers **multiple scales and dimensions**, not a single `N`:

| Scenario | What to Test | Issues Exposed |
| --- | --- | --- |
| Small (1k–10k rows) | Correctness, SQL/constraint checks | Indexes may be skipped on tiny tables |
| Medium (hundreds of thousands) | Lookups, JOINs, sorts | Early plan bottlenecks |
| Large (millions–tens of millions) | Cardinality, I/O, index footprint | Sort/hash disk spills, overly broad scans |
| Very large (per realistic forecast) | Partitioning/retention, maintenance | Vacuum cost, index bloat, backup time |
| Hot/cold data | Common vs. rare values | Parameter-sensitive plans |
| Skewed data | 70% in one bucket, heavy NULLs | Estimated vs. actual row divergence |
| Historical depth | Mostly old rows, few new rows | Time indexes, BRIN/partition pruning |
| Concurrent writes | Contention on shared keys | Locks, retries, deadlocks |
| Near business limits | Power buyers, giant child tables | Deep pagination, huge Nested Loops |

**Not every table needs tens of millions of rows to benchmark.** Scale tables proportionally to real usage. A currency-code table has a couple hundred rows; inflating it to millions tests an unrealistic scenario.

At the same time, if orders are projected to grow from 250k to 50 million over a few years, test at least one tier large enough to expose **storage, index, JOIN, and maintenance** costs—never extrapolate linearly from 250k timings assuming plans stay unchanged.

## 15. Document, Graph, and Analytical Models

The same "propose → measure → read plan → verify" loop applies across storage technologies, though tooling and metrics change.

| Storage Model | What to Inspect | Key Representative Data Traits |
| --- | --- | --- |
| **Relational (PostgreSQL)** | `EXPLAIN`/`ANALYZE`, scans, JOINs, sorts/hashes, buffers, indexes | Row count, selectivity, skew, correlation, NULLs, row width |
| **Document** | Query/aggregation explain, indexes, documents examined, sorts/lookups | Document size, array length, nesting depth, missing-field rates |
| **Graph** | Traversal depth, branching factor, edges traversed, paths returned | Node degree, super-node hubs, path counts, cycles, edge types |
| **Warehouse / OLAP** | Partition pruning, bytes scanned, shuffles, spills, joins/aggregations | Fact volume, grain, width, dimension cardinality, partition skew |

### 15.1. Document: Do Not Just Count Documents

100k Customer documents each embedding a huge Orders array behave completely differently from 100k Customers with 2 Orders each. Measure:

- Average and **p95/p99** document sizes.
- Average/max array lengths.
- Queries filtering nested elements, multikey indexes, and rewrite cost of large documents.
- Whether embedding vs. referencing causes data duplication or multi-document update fan-out.

"Fewer JOINs" does not prove document stores are faster; measure real read/write costs on realistic shapes.

### 15.2. Graph: Node Count Alone Is Insufficient

A million-node graph with degree 2 behaves nothing like a graph with **hubs connected to hundreds of thousands of edges**. Even 2–4-hop traversals can explode at hub nodes.

Graph evaluations must track edges traversed, depth, degree distribution, path duplication, traversal caps, and cycle handling. Uniform random test graphs miss the hub bottlenecks dominating real-world graphs.

### 15.3. Warehouse: Do Not Confuse Query Latency with Processing Cost

Analytical warehouses optimize columnar scans, partitioning, and massive aggregations. Evaluate **bytes scanned**, rows shuffled, disk spills, join key skew, and many-to-many dimension bridges.

If joining a fact table to a bridge multiplies rows per event, monetary sums silently double-count. Verify **grain** and allocation rules before declaring a plan "fast and accurate".

## 16. Experiment Log and Acceptance Criteria

Every index or physical layout change should carry a concise, reproducible record:

~~~text
Proposal:
  Add index (customer_id, created_at DESC, order_id DESC)
  INCLUDE(status) on orders.

Hypothesis:
  Reduce rows read/sorted to retrieve a customer's 20 most recent orders.
  Accept measured index storage growth and write overhead.

Environment:
  PostgreSQL version, relevant settings, CPU/RAM/storage.
  Dataset version, creation date, row counts, hot/cold customer distribution.
  ANALYZE/VACUUM state, cache, and background load.

Query:
  Verbatim SQL, parameter types, time window, LIMIT.
  Parameter groups: hot, typical, zero orders.

Before/After Results:
  Saved EXPLAIN (ANALYZE, BUFFERS).
  Estimated/actual rows, scan/join/sort nodes.
  p50/p95 across repeated runs under identical conditions.
  Index size, INSERT/UPDATE latency, and other impacts.

Decision:
  ACCEPT / REJECT / NEEDS MORE DATA.
  Rationale grounded in agreed criteria, not a single millisecond figure.
~~~

Whenever test data differs substantially from production, state explicit **validity boundaries for your conclusions**. For example: "Results hold for single-customer lookups at 250k Orders, without proving performance at 50M Orders or 200 concurrent sessions."

## 17. Common Pitfalls

| Pitfall | Consequence | Remedy |
| --- | --- | --- |
| Testing on a few dozen rows | Tiny-table plans misrepresent real scale | Test multiple tiers and realistic distributions |
| Using only uniform random data | Misses hot keys, skew, and correlations | Generate or anonymize skewed representative datasets |
| Reading planner `cost` as milliseconds | Misinterprets planner units | Separate `cost` from `actual time` |
| Reading only the Scan name | Ignores filtered rows, loops, buffers | Read the entire operator tree |
| Assuming `Seq Scan` is always bad | Adds useless indexes, slows writes | Compare bytes/pages read and overall cost |
| Testing only one `customer_id` | Works for typical rows, stalls on hot buyers | Test across varied parameter profiles |
| Skipping `ANALYZE` after bulk loads | Planner acts on missing/stale stats | Refresh stats deliberately |
| Indexing every column in `WHERE` | Duplicate indexes, bloated writes | Design around predicates, sort orders, selectivity |
| Expecting `LIMIT` to make `GROUP BY` cheap | Still scans/aggregates qualifying input rows | Inspect plan; consider summaries if warranted |
| Running `EXPLAIN ANALYZE DELETE` on prod | Executes real deletions | Test only in isolated safe environments |
| Treating one run as p95 | Statistically meaningless | Repeat sufficiently under representative load |
| Read-only benchmarks | Blind to index write slowdown | Measure realistic read/write mixes and transactions |
| Changing multiple variables at once | Cannot isolate cause of change | Change one factor or run clean A/B comparisons |
| Focusing solely on latency | Misses wrong totals, duplicates, orphans | Verify correctness and invariants first |
| Judging partitioning by table count | Adds complexity without solving bottlenecks | Isolate the bottleneck and verify partition pruning |

## 18. Self-Check Exercises with Guided Solutions

### Exercise 1. Why Wasn't an Index Chosen?

**Prompt:** A table has 10k rows. A query selects 80% of the table and an index exists on the filter column, yet `EXPLAIN` chooses `Seq Scan`. Is this definitely a bug?

**Hint:** No. When reading most of a table, a sequential scan is often cheaper than hopping across index and heap pages. Inspect estimated/actual rows, buffers, row width, and runtime rather than just node names.

### Exercise 2. Index for Order History

**Prompt:** Query `WHERE customer_id = ? ORDER BY created_at DESC, order_id DESC LIMIT 20` on a multi-million-row `orders` table. Which index do you propose, and what must you measure?

**Hint:** Consider **`(customer_id, created_at DESC, order_id DESC)`**; if only `status` is additionally selected, test `INCLUDE(status)`. Measure plan shape, `Sort`, row counts, buffers, p50/p95 across hot/cold customers, plus index footprint and `INSERT`/`UPDATE` latency.

### Exercise 3. Severe Row Misestimation

**Prompt:** A Nested Loop estimates 20 outer rows yet receives 80,000 actual rows, running the inner probe tens of thousands of times. Should you immediately force a Hash Join?

**Hint:** Not yet. Diagnose why estimated vs. actual diverged: stale stats, skew, correlation, bind parameters, or join conditions. Run `ANALYZE`, adjust stats/extended stats, or refine indexes/queries, then remeasure. Forcing a join hint masks root causes rather than solving them.

### Exercise 4. `LIMIT` Over Aggregation

**Prompt:** `SELECT product_id, SUM(quantity) FROM order_lines GROUP BY product_id ORDER BY SUM(quantity) DESC LIMIT 10`. Why doesn't `LIMIT 10` guarantee reading only 10 rows?

**Hint:** Finding the top 10 products requires aggregating all qualifying input rows—often most or all of `order_lines`. `LIMIT` caps final output, not grouping work. Evaluate indexes or summary tables for the specific query pattern.

### Exercise 5. Does Benchmark Data Match Real Distribution?

**Prompt:** Production has a few customers with hundreds of thousands of orders, yet the generator spreads orders uniformly across all customers. Can you trust hot-customer conclusions?

**Hint:** Unreliable. Simulate realistic skew and test multiple parameter groups. Document distributions, historical depth, status/NULL shares, and table sizes so conclusion boundaries are explicit.

### Exercise 6. Is `EXPLAIN ANALYZE` Harmless?

**Prompt:** Someone runs `EXPLAIN ANALYZE DELETE FROM orders WHERE created_at < ...` on production just to time the delete.

**Hint:** Dangerous—`EXPLAIN ANALYZE` **executes the `DELETE`**. Use plain `EXPLAIN` (without `ANALYZE`) for estimated plans, or run controlled tests in an isolated environment. Even `ROLLBACK` in a test transaction cannot revert all non-transactional side effects.

### Exercise 7. BRIN or B-Tree?

**Prompt:** A massive event table has `created_at` rising roughly with insertion order, and most queries filter one week. What should you evaluate?

**Hint:** Compare B-tree and BRIN against data and physical ordering. BRIN stays tiny and helps when physical correlation is strong, though it reads and rechecks wider page ranges; B-trees prune more selectively at higher size and maintenance cost. Measure plans and I/O at realistic scale.

### Exercise 8. Many Indexes, Yet the API Remains Slow

**Prompt:** Server-side SQL p50 is low, yet API p95 is high. Can you conclude an index is missing?

**Hint:** No. Measure end-to-end to separate connection pool waits, locks, network, serialization, application logic, queues, and concurrency. Missing indexes are one hypothesis, never the default answer.

### Exercise 9. A JOIN Inflates Total Revenue

**Prompt:** A revenue report joins `OrderLine` to two independent multi-valued tables and runs `SUM(amount)`, duplicating each invoice line multiple times. If `EXPLAIN` runs fast, is it acceptable?

**Hint:** No. The output is **wrong** due to join grain mismatch. Pre-aggregate, fix relationship grain, or allocate proportionally by rule. Business correctness always precedes speed.

### Exercise 10. Does Partitioning Solve Every Query?

**Prompt:** `orders` is partitioned by `created_at`. A query filters only `customer_id` without `created_at`. Can you be sure it reads only one partition?

**Hint:** No. Without a partition-key predicate, the planner may examine many or all partitions. Inspect partition pruning and actual plans; partitioning adds management overhead rather than being a universal optimization.

## 19. Takeaways

- **Query plans are evidence of how the DBMS executes or plans to execute**, not an end in themselves. Read operator trees, estimated/actual rows, loops, filters, sorts/hashes, buffers, and timings in context.
- **`EXPLAIN`** does not run `SELECT`; **`EXPLAIN ANALYZE`** executes the statement. Never run state-changing DML probes on live production data.
- **Scale alone is not enough; distribution must also be realistic.** Hot keys, skew, NULL ratios, historical depth, and cross-column correlation shape query plans.
- **A good index depends on queries and load.** Measure read gains alongside write costs, footprint, maintenance, and side effects on other queries.
- **Preserve business correctness before optimizing.** Duplicating rows via joins, unstable pagination, or mutating historical prices fails regardless of latency.
- **Benchmarks must be repeatable, controlled, and explicitly scoped.** One fast laptop run never proves production p95 compliance.
- **Relational, document, graph, and warehouse models all require measurements aligned with real data structures.** No technology replaces checking plans, data, and business rules.

A trustworthy physical modeling decision must answer: **For which data and load, which queries improve, by how much in measured numbers, at what trade-off, and is correctness preserved?** That is how data design moves from guesswork to verifiable, evolvable engineering.
