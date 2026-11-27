# Choosing an Approach Based on Access Patterns and Measurement Evidence

## Learning Objectives

After this lesson, you will be able to:

- Describe a feature's **access pattern** in terms of operations, filters, sorting, frequency, result set, freshness, and latency targets.
- Distinguish between issues caused by the data model and issues caused by queries, indexes, pagination, or how the application calls the database.
- Formulate testable hypotheses to choose among a normalized relational model, indexes, caching, materialized views, summary tables, and denormalization.
- Read key signals from query execution plans and design experiments using representative read/write workloads.
- Decide whether to keep, adopt, or remove a data copy based on system-wide benefits alongside consistency requirements and reconcilability.

In **DATABASE_DATA_MODELING**, schema design does not stop at listing entities, relationships, and constraints. Model quality is also reflected in whether that structure serves how the system actually reads and writes data, can be verified through measurement, and can evolve as business rules change.

## 1. Why Can the Same Model Perform Well in One Place and Poorly in Another?

Two e-commerce systems might share the exact same **Customer – Order – OrderItem – Product** entities, yet have completely different access patterns:

- **System A:** Customers frequently view their own 20–50 most recent orders; orders are created and edited continuously; totals must be accurate immediately after saving.
- **System B:** Analysts frequently inspect daily aggregated order counts and revenue spanning several years; 5-minute data lag is acceptable; source data is written continuously.
- **System C:** Product search pages are read millions of times, combining description, price, category, and ranking; search data may lag by a few seconds, while checkout prices must be re-verified against the authoritative business source.

No universal rule like "all JOINs are slow" or "pre-storing values is always faster overall" fits all three.

**Denormalization** can reduce read costs by storing copies, aggregations, or dedicated read models. In return, the system pays additional costs in writes, storage, synchronization, schema evolution, and recovery. The right decision must start from **specific access patterns** and **measurements under representative load**.

A normalized relational model remains a useful starting point when business dependencies and foreign keys are clear. Read-serving structures should only be added once you know which queries need support, what improvement is required, and what correctness properties must be preserved.

## 2. What Should an Access Pattern Describe?

An access pattern specifies how a user, API, job, or external system interacts with data. Instead of writing "frequently fetches order info," describe it in enough detail to construct queries and benchmarks.

| Descriptor | Question | Example |
| --- | --- | --- |
| Operation | Detail read, search, aggregation, insert/update/delete, or event processing? | List a customer's most recent orders |
| Filters | Filter by key, status, time, price range, location, etc.? | customer_id, created_at |
| Sorting / pagination | Is there ORDER BY, LIMIT, cursor, or OFFSET? | Newest first, 50 orders/page |
| Projected fields | Need the entire entity or just a few attributes? | order_id, created_at, line-item subtotal |
| Relationships / cardinality | How many related records link to one record? | Average 4 lines/order; some orders have hundreds |
| Frequency / load | How many requests/second, and what do peak spikes look like? | 400 requests/min; 5x peak |
| Related write paths | How often is source data created, modified, or canceled? | Add line items, edit quantities, cancel lines |
| Consistency | Can stale values be read? What is the maximum allowed lag? | Order total accurate immediately after edit |
| SLO | Target latency / throughput / error rate? | API p95 at most 180 ms |
| Scale and growth | How many rows, daily growth, any oversized accounts? | 8 million orders, 35 million line items |

**Cardinality** is the number of matching elements in a relationship: how many line items per order; how many products per category. **Selectivity** indicates how narrowly a filter predicate reduces the dataset. Both properties directly affect join strategies, rows scanned, and index usefulness.

For analytical data, also record the result **grain**: one row per order, per customer/day, or per product/month. For document databases, record document size and how many documents must be updated when a current value changes. For graphs, record traversal hop count, vertex degree distribution, and depth bounds.

### 2.1. The Critical Query Set, Not Just the "Slowest Query"

A query running 2 seconds once a month and an 80 ms query called thousands of times per minute have very different system impacts. Identify:

1. Queries whose latency exceeds the business flow's target.
2. Queries consuming high cumulative resources due to high call frequency.
3. Queries causing load spikes, lock waits, or I/O bottlenecks.
4. Write paths that could be impacted when adding copies or indexes.

A rough initial prioritization is to look at **call count × average execution time** for each query group over the same measurement window. This metric estimates total recorded query execution time; **it does not equal actual CPU usage**, and you must never multiply p95 by call count to infer average time. Always cross-check against CPU, I/O, and wait statistics.

### 2.2. Do Not Let Averages Hide Worst-Case Outliers

For example, most customers place 2–5 orders per month, while some enterprise accounts have hundreds of thousands of orders. A query that is fast for typical customers can be severely slow for these rare accounts.

When selecting test datasets, include:

- Accounts with sparse and dense data; orders with few and many line items.
- Recent time ranges and historical data, including skewed distributions.
- Warm-cache and cold-cache queries.
- Low concurrency, high concurrency, and simultaneous read/write scenarios.
- Data scaled to projected size, not merely a test database with a few thousand rows.

Measuring a single sample query on a local laptop makes it very easy to draw wrong conclusions about denormalization.

## 3. Diagnose the Problem Before Changing the Schema

The process should begin with the question: **Where is the time going?** Bottlenecks may sit in the application, network, SQL query, locks, indexes, over-fetching rows, or UI rendering logic.

### 3.1. Collect Request Path Telemetry

At the application layer, measure total API latency versus database wait time, and check query counts per request. The **N+1 query** pattern commonly appears when an app fetches 50 orders and then issues 50 extra queries for their line items. Try batching queries or set-based reads before adding redundant columns.

At the database layer, tooling depends on the DBMS: PostgreSQL provides query statistics (such as **pg_stat_statements** when configured), slow query logs, APM traces, and execution plans. Track execution time, call count, row counts, block reads, CPU/I/O pressure, and lock waits.

Align all metrics within the same time window. Peak throughput, hardware specs, schema version, and dataset state must be documented; otherwise, two measurements cannot be compared reliably.

### 3.2. Read Execution Plans Hypothesis-First

PostgreSQL example:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 501
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Key signals worth inspecting:

| Plan Signal | Investigation Hint |
| --- | --- |
| **actual rows** far from **estimated rows** | Stale statistics, skewed distribution, correlated predicates; check ANALYZE and parameter binding |
| **Seq Scan** on a large table with a selective filter | Consider an appropriate index; note that Seq Scan may still be optimal if reading most of the table |
| **Sort** processing many rows before LIMIT | Check composite filter + sort-order index; shrink candidate set early |
| **Nested Loop** iterating many times over a large set | Verify row estimates and inner-side indexes; do not assume Nested Loop is inherently bad |
| **HashAggregate/GroupAggregate** over large row counts | Consider filtering early, aggregating the exact subset, or using summary tables when justified |
| **Buffers: shared hit/read** | Distinguish PostgreSQL cache hits from physical/OS block reads; inspect I/O volume |
| **Actual time**, planning and execution time | Check which node actually consumes time to avoid optimizing the wrong step |

**EXPLAIN (ANALYZE)** actually executes the statement; it is appropriate for observing SELECT queries like the example, but running it on data-modifying statements causes real mutations. Benchmark in a safe environment and under controlled load, because collecting execution timing adds overhead. "Cost" in EXPLAIN is the optimizer's relative unitless estimate, not milliseconds.

## 4. Running Example: The Order List Page

Suppose the normalized schema contains:

- **orders(order_id, customer_id, created_at, status)**.
- **order_items(order_item_id, order_id, quantity, unit_price_at_purchase)**.

Requirement: when a customer opens their order history page, return the **50 most recent orders** along with each order's line-item total. In this example, the total is strictly **SUM(quantity × unit_price_at_purchase)**, excluding taxes, shipping, discounts, or refunds. Before applying this to real financial accounting, define the full formula explicitly.

### 4.1. Initial Approach: Bounded Read First, Aggregate Second

~~~sql
WITH recent_orders AS (
    SELECT
        o.order_id,
        o.created_at
    FROM orders AS o
    WHERE o.customer_id = $1
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 50
)
SELECT
    ro.order_id,
    ro.created_at,
    COALESCE(
        SUM(oi.quantity * oi.unit_price_at_purchase),
        0
    ) AS items_subtotal
FROM recent_orders AS ro
LEFT JOIN order_items AS oi
    ON oi.order_id = ro.order_id
GROUP BY ro.order_id, ro.created_at
ORDER BY ro.created_at DESC, ro.order_id DESC;
~~~

Key detail: the query **selects the 50 orders first**, then sums only their matching line items. This avoids aggregating every historical order for a customer when only 50 are needed. The sort order includes **order_id** as a deterministic tie-breaker when two orders share the same **created_at**.

Candidate indexes:

~~~sql
CREATE INDEX idx_orders_customer_created_id
    ON orders (customer_id, created_at DESC, order_id DESC);

CREATE INDEX idx_order_items_order_id
    ON order_items (order_id);
~~~

These are candidates to **benchmark**; do not blindly create them if equivalent indexes already exist. Check selectivity, index size, write overhead, and actual execution plans. If the API supports deep pagination, consider **keyset pagination** on **(created_at, order_id)** instead of large OFFSETs.

### 4.2. Alternative Approach: Storing the Subtotal on Orders

If the optimized query remains too slow, the team might evaluate **orders.items_subtotal**:

~~~sql
ALTER TABLE orders
ADD COLUMN items_subtotal NUMERIC(14, 2);
~~~

This field is a **derived value**. It is only useful when designed with a contract:

> For each order, **items_subtotal** equals the sum of quantity times unit price of valid line items, computed at an agreed point in time; line-item changes must be reflected according to the chosen consistency mechanism.

If immediate accuracy after each edit is required and all data resides in the same PostgreSQL instance, updating within the same transaction may fit. However, you must also handle line updates/deletes, cancellations, request retries, concurrency, and backfills. Simply adding a column and copying totals once is insufficient.

With the pre-stored value, the read query only touches 50 **orders** rows, but every line-item change incurs extra work on **orders**; multiple transactions modifying the same order concurrently can cause lock contention.

### 4.3. Comparison with Hypothetical Metrics

**The following table uses purely illustrative numbers** to demonstrate decision-making; it is not a benchmark from a production system.

| Metric under identical workload | Original Query | Early Filter + Indexes | Store items_subtotal |
| --- | ---: | ---: | ---: |
| Order list API, p95 | 340 ms | 125 ms | 96 ms |
| List API SLO | ≤ 180 ms | ≤ 180 ms | ≤ 180 ms |
| Line-item insert/update, p95 | 105 ms | 112 ms | 158 ms |
| Extra data/index storage | 0 (baseline) | Increases due to indexes | Increases due to column + supporting logic |
| Consistency maintenance work | Recomputed at query time | Recomputed at query time | Sync updates, reconciliation, backfill |
| New risks | Aggregation load on reads | Index maintenance cost | Write locks, stale derived values if paths are missed |

In this hypothetical scenario, **"early filter + indexes" already meets the read SLO**. Storing the subtotal shaves an extra 29 ms off read p95, but slows writes noticeably and increases operational burden. Unless stricter read targets exist, **keep the optimized normalized model**, continue monitoring real traffic, and revisit storing the subtotal only if needed.

Note: p95 is a percentile; **you cannot add or subtract component p95s to derive end-to-end p95**. The table reports p95 measured separately per operation type under the same load test.

## 5. Another Case: Daily Summary Dashboard

Suppose the analytics team needs the daily count of orders in the **PAID** status and their corresponding collected amounts. The dashboard gets heavy traffic, queries long historical ranges, and users tolerate up to **10 minutes** of data lag.

From a business rules standpoint, assume:

- **orders.paid_at** is the payment timestamp, non-null for PAID orders.
- **orders.charged_amount** is the recorded payment amount for the order, governed by its own rules.
- The report counts **orders currently in status = 'PAID' at refresh time**.
- Reporting days are defined in **UTC**. If the business uses another timezone, update the definition and handle day boundaries accordingly.

Running a direct aggregation over a huge table can be expensive, especially when users repeatedly request the same metrics. After trying filter optimizations, a **materialized view** can be considered.

~~~sql
CREATE MATERIALIZED VIEW daily_paid_order_summary AS
SELECT
    (paid_at AT TIME ZONE 'UTC')::date AS day_utc,
    COUNT(*) AS order_count,
    SUM(charged_amount) AS charged_total
FROM orders
WHERE status = 'PAID'
  AND paid_at IS NOT NULL
GROUP BY (paid_at AT TIME ZONE 'UTC')::date
WITH NO DATA;

-- Initial data population:
REFRESH MATERIALIZED VIEW daily_paid_order_summary;

CREATE UNIQUE INDEX ux_daily_paid_order_summary_day
    ON daily_paid_order_summary (day_utc);

-- Subsequent refreshes, when PostgreSQL conditions are met:
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_paid_order_summary;
~~~

**Note:** the statements above illustrate creation and refresh ordering. **CONCURRENTLY** requires the materialized view to already be populated and have a suitable unique index; operationally, you must manage scheduling, overlapping jobs, completion duration, and resource usage. PostgreSQL materialized views update via full REFRESH, not automatically in increments whenever source rows change. For very large datasets, a full refresh may become too expensive; consider incrementally updated summary tables or a dedicated analytics platform.

Suppose a representative measurement shows the direct aggregation query has **p95 = 2.1 seconds**, while reading from the view has **p95 = 80 ms**; refreshes complete well within budget, and the maximum observed data lag during testing is **6 minutes**. When the dashboard target is **p95 ≤ 300 ms** and staleness must stay under **10 minutes**, a materialized view is a sensible candidate.

To confirm decisively, still verify peak-load behavior, late-arriving payment events, status transitions, recomputation capability, and lag during job failures. If the system requires instant payment totals to authorize transactions, the exact same materialized view **lacks sufficient freshness**.

## 6. Option Map by Access Pattern

Do not start with a technology name. Start with **query shape**, **freshness**, and **source mutation rate**.

| Dominant Access Pattern | What to Try First | When to Consider Additional Options |
| --- | --- | --- |
| Lookup by PK/FK returning few rows | Normalized model, PK/FK, indexed JOINs | When cross-service/cross-store joins prove expensive with evidence |
| Filter + sort + LIMIT on large datasets | Composite indexes, keyset pagination, narrower projections | When results are read repeatedly and fit specific freshness bounds |
| Application-layer N+1 queries | Query consolidation, batch fetching, set-based processing | If batching misses targets, evaluate a dedicated read model |
| SUM/COUNT aggregations over deep history | Early filtering, indexes, partitioning if appropriate | Materialized views, incremental summary tables, OLAP |
| Popular content: read-heavy, rarely changing | Keyed cache with TTL / invalidation | Snapshots/materialized views if stable aggregate queries are needed |
| Multi-criteria listing/search, full-text | Specialized indexes, search engine when warranted | Event-synchronized read model with a defined lag contract |
| Aggregate details routinely read/written together | Relational or document model aligned to transaction boundaries | Embed snapshots or derived data when semantics are explicit |
| Multi-hop relationship queries, variable paths | Proper relational indexes, test recursive queries | Graph model when traversal is the primary workload and proven |
| Multi-dimensional reporting, multi-year scans | Grain-based analytical schema, fact/dimension modeling | Pre-aggregation, materialized views, columnar engines |
| High-frequency counter updates on a single row | Re-examine consistency requirements and calculation rules | Sharded counters / async aggregation if business rules allow |

This table represents an **investigation order**, not absolute law. For instance, caching works well for product catalog pages, but price and inventory at checkout must be re-validated against the authoritative source per business constraints.

### 6.1. When Should Data Be Duplicated Inside a Document?

If a document contains an entire order along with its line items and price snapshots at placement time, the application can read it in a single operation. The benefit depends on document size, atomic update boundaries, and unbounded sub-list growth.

Conversely, copying the **current seller name** into millions of product documents causes massive write amplification on a single rename. Measure **update fan-out**: how many records must sync per source change, what is the worst-case propagation delay, and whether reading the old name temporarily is acceptable.

### 6.2. When Is a Graph Model Worth Considering?

Queries like "suggest connections within three hops" or dependency-path tracing can fit a graph database well. Measure traversed vertices/edges, depth limits, and supernodes (high-degree vertices). Pre-storing path counts or aggregated vertex properties speeds up reads, but edge mutations trigger recalculation across many derived values. Choose a graph model based on real traversal workloads, not merely because data "has many relationships."

### 6.3. When Should Data Move to an Analytical Model?

Reports broken down by month, product, channel, and region may scan hundreds of millions of rows. If they degrade online transactions, offloading analytical workloads to a dedicated data warehouse can be cleaner than adding redundant columns to the transactional database. Explicitly document reporting periods, grain, sync schedules, and late-arriving data strategies.

## 7. Designing Fair Comparison Benchmarks

A useful benchmark must be capable of **falsifying a hypothesis**, not merely confirming a favored option. For example:

> "Pre-storing the line-item total will bring order list API p95 below 180 ms while keeping line-item update p95 under 140 ms, without corrupting totals or increasing lock waits past threshold."

This hypothesis has clear acceptance criteria. Measuring only the read API while ignoring the write path is insufficient for a decision.

### 7.1. Fix Experimental Conditions

Record: DB version, resource allocation, row counts and skew, optimizer statistics, index set, connection pooling, concurrency level, read/write mix, query types, parameters, caching policy, hot/cold data ratio, and run duration. Whenever possible, run the exact same query suite and dataset across candidates.

Do not benchmark on an idle workstation and extrapolate straight to high-concurrency production. For solutions adding columns or indexes, also measure migration duration and live backfill impact.

### 7.2. Measure Reads, Writes, Resources, and Correctness

| Metric Group | What to Measure | Why |
| --- | --- | --- |
| User experience | API p50, p95, p99; error rate; throughput | Verify whether user SLOs are met |
| DB reads | Execution time, rows, buffer hits/reads, temp files | Locate where query cost actually sits |
| DB writes | INSERT/UPDATE/DELETE latency, WAL volume, write amplification | Expose overhead of redundant columns/indexes |
| Concurrency | Lock waits, deadlocks, concurrent transaction rate | Catch aggregated rows becoming contention hotspots |
| Resources | CPU, I/O, memory, disk/index footprint | Avoid shifting cost blindly from reads to writes/storage |
| Consistency | Divergent record count, drift magnitude, replica age | Validate the derived data contract |
| Operations | Backfill time, refresh duration, recovery time, replication lag | Assess deployability and scalability |
| Growth | Cost as row counts, large accounts, and call rates grow | Avoid solutions fast only on small datasets |

**Correctness** requires an independent oracle: recompute from the source of truth and compare according to business rules and declared lag. For example, if **orders.items_subtotal** represents the sum of active line items, a reconciliation query can be written as:

~~~sql
SELECT
    o.order_id,
    o.items_subtotal AS stored_subtotal,
    COALESCE(
        SUM(oi.quantity * oi.unit_price_at_purchase),
        0
    ) AS calculated_subtotal
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, o.items_subtotal
HAVING o.items_subtotal IS DISTINCT FROM COALESCE(
    SUM(oi.quantity * oi.unit_price_at_purchase),
    0
);
~~~

**IS DISTINCT FROM** also catches cases where the stored value is NULL, since standard SQL equality/inequality with NULL does not evaluate to TRUE/FALSE like comparing two numbers. When a column is added via migration and backfill is in progress, evaluate against transition-state rules rather than treating every NULL as a final operational failure.

If copies update asynchronously, reconciliation must apply only to records **past the sync window** or compare against matching version/event watermarks. Flagging every instantaneous difference as a bug creates false alarms.

### 7.3. Run Enough Scenarios to Expose Trade-offs

Compare at least three scenarios:

1. **Read-heavy:** high read ratio and high read concurrency.
2. **Write-heavy / update spikes:** inserts, edits, cancellations, retries, and concurrent transactions touching the same aggregate.
3. **Mixed workload:** production-like traffic, including high-volume accounts and duplicate update events.

After warming caches appropriately, run long enough to capture p95/p99 and variance. Record both the baseline and the best simple-optimization candidate—avoid benchmarking against an unoptimized strawman just to make denormalization look good.

## 8. Decision Framework: Adopt, Iterate, or Reject?

Evaluating options can be structured around **mandatory requirements** and **trade-off costs**.

**Mandatory requirements** include:

- Critical read and write flows meet SLOs under projected load.
- Results reflect accurate business semantics; copies have an explicit source of truth and consistency contract.
- Storage overhead, sync lag, recoverability, and migration effort stay within acceptable operational bounds.
- The design remains maintainable as business rules evolve without relying on ad-hoc manual fixes.

When multiple candidates pass, prefer the **simplest option that satisfies the agreed criteria**; the complexity of replicas, pipelines, and backfills is a real engineering cost.

An evaluation decision matrix can look like this:

| Option | Read SLO | Write SLO | Accuracy / Freshness | Operational Cost | Experimental Conclusion |
| --- | --- | --- | --- | --- | --- |
| Unoptimized normalized JOIN | Fail | Pass | Pass | Low | Fix query / indexes first |
| Optimized JOIN | Pass | Pass | Pass | Low | **Select** for hypothetical order page |
| Pre-stored total column | Pass | Fails hypothetical write bound | Passes only with full sync/reconciliation | Higher | Not selected |
| Periodically refreshed materialized view | Passes for dashboard | Reduces read pressure on source | Passes if freshness stays within bound | Requires refresh job / monitoring | **Select** for hypothetical dashboard |

These conclusions apply solely to **this lesson's two illustrative examples and numbers**, not as blanket recommendations for every system.

### 8.1. When Benchmarks Are Inconclusive

If a change improves p95 by only a few percent with high variance, do not rush to conclude. Re-run under steadier load, take multiple samples, inspect latency distributions, and verify behavior as data scales.

If an option wins on reads but fails during write peaks, explore caching, asynchronous pre-aggregation, write sharding, or a separate read model—provided the business genuinely tolerates the resulting lag.

If you cannot yet specify the source of truth or reconciliation check, the duplication approach **is not design-ready**, regardless of how fast the benchmark reads look.

## 9. Today's Choice Needs Tomorrow's Exit Path

Denormalization is a reversible architectural decision, but reversing it is often costly. Prepare:

- **Data contract:** derived field semantics, source of truth, refresh rules, allowed lag, owner.
- **Single rule-enforcing write path:** every code path follows one update rule; handles duplicates, missing steps, and out-of-order events.
- **Backfill strategy:** populate historical data without overwriting concurrent updates; reconcile afterward.
- **Observability:** measure lag, divergent record counts, event queues, refresh failures, and lock bottlenecks.
- **Safe cutover:** shift read traffic gradually, shadow-compare against source queries, and keep a rollback path to source reads if errors appear.
- **Retirement criteria:** when source queries are improved, usage drops, or copy maintenance outweighs measured gains.

For example, adding **items_subtotal** requires a backfill and synchronization plan during rollout. You cannot assume a single summary UPDATE suffices if concurrent transactions are adding or deleting line items at the same time. Control deployment ordering, concurrency handling, and cross-checks before cutting over reads completely.

Conversely, if a materialized view no longer serves any dashboard, continuing periodic refreshes wastes resources. The sound move is to verify zero remaining consumers or dependencies and drop it.

## 10. A Ready-to-Use Engineering Review Sheet

Before choosing denormalization, complete these fields for **one specific access pattern**:

| Item | What to Document |
| --- | --- |
| Use case | API/report, consumers, and business goal |
| Query shape | Filters, JOINs, aggregates, ORDER BY, LIMIT, returned fields |
| Volume | Row counts, distribution, growth rate, outlier large accounts/records |
| Frequency | Reads/writes per second; peak load; concurrency |
| SLO | Max p95/p99; throughput; error rate |
| Freshness / consistency | Immediate accuracy or allowed lag, and how it is measured |
| Baseline | Pre-optimization metrics, environment, and test conditions |
| Simpler alternatives | Query rewrite, indexes, batching, pagination, caching |
| Duplication option | Which copy, source of truth, owner, write/refresh mechanism |
| Costs | Write overhead, locks, storage, migration, backfill, recovery |
| Validation | Data reconciliation, mixed-load test, duplicate-event verification |
| Decision | Chosen option, evidence, conditions triggering re-evaluation |

This sheet turns a casual "let's add a column to make it faster" discussion into a reviewable decision. When traffic or business rules shift, the team can re-evaluate against the exact same criteria.

## 11. Practice Exercises

**Exercise 1 — JOIN or Stored Total?** A page fetching the 50 most recent orders has p95 = 300 ms against a 180 ms target. After adding proper indexes and aggregating only those 50 orders, p95 drops to 130 ms. Pre-storing the total on orders reduces read p95 to 100 ms, but increases line-item update p95 from 120 ms to 190 ms against a 160 ms write limit. What should you choose, and why?

**Exercise 2 — Hourly Summary Table.** A dashboard displays order counts by region and hour, requiring p95 under 500 ms and tolerating 15 minutes of lag. Direct queries take 4 seconds; an async summary table achieves p95 = 110 ms, but during peak hours pipeline lag hits 24 minutes. Does the summary table meet requirements? What additional metrics should be measured?

**Exercise 3 — Embedding Author Info.** A document-based article store embeds the current author name into every article to avoid a lookup. Authors average 20 articles, yet a few authors have millions of articles. What data must be collected before deciding to keep this embedded field?

**Exercise 4 — High Reads, Immediate Accuracy.** An inventory checker has heavy read traffic; caching lowers p95 but occasionally returns stock counts from several minutes ago. Can the cached value be used to commit sales? If caching remains useful on product browsing pages, how should responsibilities be separated?

### Suggested Solutions

1. **Keep the optimized query**: both read (130 ms) and write (120 ms) meet targets; storing the total breaches the write SLO and adds sync complexity. Revisit only if load or SLOs change.
2. **Not yet compliant**: 24-minute lag exceeds the 15-minute allowance. Measure p95/p99 and max data age, queue backlog, recovery time, missing/duplicate counts, and recomputation capability; then optimize or redesign the pipeline.
3. Measure rename fan-out distribution, rename frequency, cost of updating millions of documents, required freshness, read volume, latency, consistency needs, and repair mechanisms for missed updates. If the requirement is the name *at publication time*, that is different semantics from the *current* name.
4. Do not use potentially stale cache values to commit inventory when immediate accuracy is required. Caching can serve informational display, while the checkout path must validate, reserve, or decrement inventory using transactionally sound guarantees.

## 12. Takeaways

**Access patterns determine the experiment; measurements determine the choice.** Document real queries, data scale, frequency, concurrency, latency limits, and freshness; optimize queries, locking, and indexes before duplicating data.

**A denormalization approach only "wins" when it improves the target flow while still meeting write, correctness, operational, and growth requirements.** When a simpler option already hits targets, choosing *not* to add a copy is equally an evidence-based modeling decision.

When defending a design to an engineering team, the convincing answer is not "denormalizing will be faster," but rather: **"For this access pattern and representative workload, which SLOs does the chosen option meet, what costs does it incur, and how is it verified with metrics and data invariants?"**
