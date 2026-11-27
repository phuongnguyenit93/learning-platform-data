# Materialized Views and Data Freshness Trade-Offs in PostgreSQL

An e-commerce system can receive thousands of orders per minute while reporting screens still need to display daily revenue by region. If opening the dashboard runs `JOIN`, `GROUP BY`, and `SUM` across millions of orders every time, response times can climb sharply. One solution in PostgreSQL is a **materialized view**: persisting the result of a query as physical data so it can be read repeatedly.

For example, instead of recomputing revenue from scratch every time:

~~~sql
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    c.region,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS revenue
FROM orders AS o
JOIN customers AS c ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY
    (o.created_at AT TIME ZONE 'UTC')::date,
    c.region;
~~~

the application can query a precomputed materialized view:

~~~sql
SELECT report_date, region, paid_orders, revenue
FROM daily_paid_revenue_mv
WHERE report_date >= DATE '2026-01-01'
ORDER BY report_date, region;
~~~

**In exchange, a materialized view does not update automatically when source tables change.** If a new order is written at 10:01 while the last refresh finished at 10:00, the dashboard continues showing stale numbers until the next refresh completes.

~~~text
Source tables (orders, customers)
    |
    +--- Continuous INSERT / UPDATE / DELETE
    |
    +--- Expensive aggregation query
                |
                v
       REFRESH MATERIALIZED VIEW
                |
                v
     Materialized view stores results
                |
                +--- Faster dashboard SELECTs
                |
                +--- Data may lag behind source
~~~

The trade-off is not just **speed vs. freshness**. Each refresh also consumes CPU, I/O, memory, WAL, and can create lock contention. This lesson examines the full mechanism, syntax, consistency, standard vs. `CONCURRENTLY` refresh, indexing, freshness tracking, operations, alternatives, and decision criteria based on business requirements.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Distinguish regular `VIEW`s from `MATERIALIZED VIEW`s.
2. Explain that materialized views persist point-in-time results and why data becomes **stale**.
3. Create materialized views using `CREATE MATERIALIZED VIEW ... AS SELECT ... WITH DATA`.
4. Use `WITH NO DATA`, understand the unpopulated state, and initialize data.
5. Update stored data via `REFRESH MATERIALIZED VIEW`.
6. Identify requirements and trade-offs when using `REFRESH MATERIALIZED VIEW CONCURRENTLY`.
7. Create a qualifying **UNIQUE index** for concurrent refreshes.
8. Distinguish **freshness**, **snapshot consistency**, and **refresh execution duration**.
9. Build a lab dataset and observe results before and after `INSERT`, `UPDATE`, and `DELETE`.
10. Track successful refresh timestamps, data age, and job failure risks.
11. Design refresh schedules based on SLAs, source load capacity, and actual runtimes.
12. Recognize when to choose regular views, incrementally updated summary tables, caches, or other architectures.

## 2. How Do Regular Views and Materialized Views Differ?

A **regular view** in PostgreSQL stores a **query definition**, not a persisted result set:

~~~sql
CREATE VIEW reporting.v_daily_paid AS
SELECT ... FROM ...;
~~~

When an application queries the view, PostgreSQL executes an optimized plan over the source tables, applying optimizations/pushdowns where applicable.

In contrast, a **materialized view** stores the **result rows** of its defining query:

~~~sql
CREATE MATERIALIZED VIEW reporting.mv_daily_paid AS
SELECT ... FROM ...
WITH DATA;
~~~

Applications read the materialized result table; this data **only changes when a refresh completes successfully** or the materialized view is rebuilt through an appropriate workflow.

| Criterion | VIEW | MATERIALIZED VIEW |
| --- | --- | --- |
| What is stored? | Query definition | Definition + physical result data |
| On SELECT | Reads source via optimized plan | Reads stored results |
| Newly written source data | Visible per next SELECT's snapshot | Invisible until refresh |
| Complex SELECT cost | May re-run JOIN/aggregation | Often lower if results are small and indexed |
| Dedicated storage for results | Negligible | Yes, including data and indexes |
| Create indexes directly on view? | Not like a physical table | Yes |
| Manual refresh | Not applicable | Yes |
| Freshness | Per source reads / MVCC | As of last refresh |
| Best fit | Data must be fresh; query not overly expensive | Dashboards/reports tolerating lag |

### 2.1. "Regular Views Are Always Slow" Is False

A regular view with selective predicates, suitable source indexes, and modest data volume can be very fast. A materialized view is only worth considering when the cost of **frequent recomputation** exceeds the cost of storing, refreshing, and operating the materialized copy.

### 2.2. "Materialized Views Are Always Fast" Is Also False

If a materialized view still holds tens of millions of rows and queries lack suitable indexes or require additional sorting/aggregation, SELECTs can still be slow. PostgreSQL does not guarantee optimal workload speed merely because the keyword `MATERIALIZED` is present.

### 2.3. Materialized Views Are Not Transparent Caches

PostgreSQL does not automatically rewrite queries targeting source tables to read an equivalent materialized view just because you created one. Applications or query layers must **explicitly SELECT from the materialized view**.

## 3. Consistency Differs from Freshness

These are two independent properties to understand before adopting materialized views.

**Freshness:** How close are the results to the current state of the source tables?

**Consistency:** Do the rows reflect a valid point-in-time data state rather than a half-old, half-new mix from an incomplete refresh?

A materialized view can be **consistent yet stale**. For example:

~~~text
09:00:00  REFRESH takes snapshot of source data
09:00:12  REFRESH finishes
09:00:15  New order COMMITs
09:00:20  Dashboard SELECTs from materialized view
~~~

The dashboard reads a consistent result set computed from the refresh snapshot, yet **excludes the new order** committed after that snapshot.

### 3.1. Refresh Completion Does Not Mean Every Prior Commit Is Included

If an order commits **after the refresh's snapshot was established**, that order will be missing from the result even though it committed before the refresh finished. Therefore, a `last_refreshed_at` timestamp is not always the **exact boundary of all included source changes**.

### 3.2. Readers Never See Half-Refreshed Results

Under PostgreSQL's transaction/MVCC and locking rules, readers never observe a partially updated result set as committed state. However, with a standard refresh they **may block on locks**; with a concurrent refresh, concurrent SELECTs continue reading the old data until the new state is committed.

### 3.3. Snapshot Consistency Does Not Guarantee Business Freshness

Revenue figures from 10 minutes ago may be mathematically accurate for that snapshot. Yet if a report drives real-time settlement, a 10-minute lag may be **unacceptable**, no matter how fast and consistent the query is.

## 4. Preparing the PostgreSQL Lab

The following examples run in a **test database**. Never create schemas, acquire locks, or refresh shared production tables to practice. We build simple source tables to observe data changes clearly.

### 4.1. Create the Schema

~~~sql
CREATE SCHEMA mv_lab;
~~~

### 4.2. Create the Customers Table

~~~sql
CREATE TABLE mv_lab.customers (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    region text NOT NULL
);
~~~

### 4.3. Create the Orders Table

~~~sql
CREATE TABLE mv_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES mv_lab.customers(customer_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL CHECK (
        status IN ('paid', 'pending', 'cancelled')
    ),
    total_amount numeric(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);
~~~

We keep `customer_id` and `created_at` strictly typed relational columns so filtering, JOINs, aggregations, and time handling stay transparent.

### 4.4. Insert Customers

~~~sql
INSERT INTO mv_lab.customers (
    customer_id, customer_name, region
) VALUES
    (1, 'An',   'north'),
    (2, 'Bình', 'south'),
    (3, 'Chi',  'north'),
    (4, 'Dung', 'central');
~~~

### 4.5. Insert Eight Orders

~~~sql
INSERT INTO mv_lab.orders (
    customer_id, created_at, status, total_amount
) VALUES
    (1, '2026-01-10 09:00:00+00', 'paid',      120.00),
    (2, '2026-01-10 10:00:00+00', 'paid',       80.00),
    (1, '2026-01-10 11:00:00+00', 'cancelled',  60.00),
    (3, '2026-01-10 12:00:00+00', 'paid',       50.00),
    (4, '2026-01-11 09:00:00+00', 'paid',      200.00),
    (2, '2026-01-11 10:00:00+00', 'pending',    30.00),
    (2, '2026-01-11 11:00:00+00', 'paid',       70.00),
    (1, '2026-01-12 08:00:00+00', 'paid',       40.00);
~~~

Sample `order_id` values will normally be 1 through 8 on a fresh table. If the schema had prior data or sequence advances, do not hardcode fixed IDs on a non-clean environment.

### 4.6. Why Use UTC Dates?

We use UTC reporting dates:

~~~sql
(created_at AT TIME ZONE 'UTC')::date
~~~

This keeps results independent of the session's application timezone. If business rules require reporting in Vietnam time or per store timezone, define day boundaries and grouping keys in that timezone explicitly; **never switch from UTC to another timezone without evaluating how aggregates shift**.

## 5. Building a Regular View as a Baseline

~~~sql
CREATE VIEW mv_lab.v_daily_paid AS
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    c.region,
    COUNT(*)::bigint AS paid_orders,
    SUM(o.total_amount)::numeric(14, 2) AS revenue,
    MAX(o.created_at) AS latest_paid_order_at
FROM mv_lab.orders AS o
JOIN mv_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY
    (o.created_at AT TIME ZONE 'UTC')::date,
    c.region;
~~~

### 5.1. Querying the View

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
ORDER BY report_date, region;
~~~

Initial data yields five groups:

| report_date (UTC) | region | paid_orders | revenue |
| --- | --- | ---: | ---: |
| 2026-01-10 | north | 2 | 170.00 |
| 2026-01-10 | south | 1 | 80.00 |
| 2026-01-11 | central | 1 | 200.00 |
| 2026-01-11 | south | 1 | 70.00 |
| 2026-01-12 | north | 1 | 40.00 |

`cancelled` and `pending` orders are excluded. The `latest_paid_order_at` column is the **creation timestamp of the latest paid order in each group**, not the time the view or materialized view was refreshed.

### 5.2. Always Verify JOIN Cardinality

Because each order references exactly one customer, this JOIN does not inflate order counts unexpectedly. If you JOIN a one-to-many child table such as `order_events` before `SUM`, revenue will be multiplied. **Materializing a flawed aggregation query only returns wrong numbers faster.**

## 6. Creating a Materialized View

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_daily_paid AS
SELECT
    report_date,
    region,
    paid_orders,
    revenue,
    latest_paid_order_at
FROM mv_lab.v_daily_paid
WITH DATA;
~~~

`WITH DATA` executes the defining query immediately upon creation so the materialized view is populated from the start.

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
ORDER BY report_date, region;
~~~

At this moment, results match the regular view because the same source query was just materialized.

### 6.1. Where Is Data Stored?

`mv_daily_paid` is a physical relation holding data. PostgreSQL manages storage, statistics, and indexes for it much like other data-bearing relations, though a materialized view cannot be directly `INSERT`ed into or `UPDATE`d by applications.

### 6.2. Materialized Views Can Have Indexes

Because it stores physical rows, you can create indexes:

~~~sql
CREATE INDEX idx_mv_daily_paid_date
ON mv_lab.mv_daily_paid (report_date);
~~~

This index speeds up date-filtered queries when the planner finds it beneficial. However, it **does not satisfy the UNIQUE requirement for concurrent refresh** because it is a non-unique index.

### 6.3. ORDER BY When Reading

Even if a materialized view's defining query contains `ORDER BY`, PostgreSQL **does not guarantee** reads after a refresh preserve that order. When ordering by date/region is needed, always write:

~~~sql
ORDER BY report_date, region
~~~

in the actual SELECT statement.

## 7. Observing Stale Data After Source Changes

Insert a new paid order for Jan 10 in region north:

~~~sql
INSERT INTO mv_lab.orders (
    customer_id, created_at, status, total_amount
) VALUES (
    1,
    '2026-01-10 17:30:00+00',
    'paid',
    30.00
);
~~~

### 7.1. Reading the Regular VIEW

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
WHERE report_date = DATE '2026-01-10'
  AND region = 'north';
~~~

In a fresh snapshot after the INSERT commits, the regular view sees **3 paid orders, revenue 200.00**.

### 7.2. Reading the MATERIALIZED VIEW

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-10'
  AND region = 'north';
~~~

The materialized view **still shows 2 orders, revenue 170.00** until refreshed.

### 7.3. This Is Not a Transaction Bug

Seeing the INSERT commit without updating the materialized view is **expected by design**. A materialized view is not a trigger pushing every source change automatically.

### 7.4. Staleness Can Cause Wrong Decisions

For example:

- Dashboards under-report current revenue.
- Inventory export APIs make decisions on stale snapshots.
- Pending-order queues fail to reflect newly arrived items.

Staleness is only acceptable when the product has a **clear freshness SLA** and users understand figures are point-in-time snapshots as of the last refresh.

## 8. Standard REFRESH MATERIALIZED VIEW

~~~sql
REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;
~~~

PostgreSQL re-executes the defining query to replace the **stored contents** of the materialized view.

Afterward:

~~~sql
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-10'
  AND region = 'north';
~~~

Expect **3 orders, 200.00** assuming no further source changes occurred during the refresh.

### 8.1. REFRESH Is Not Incremental by Default

Core PostgreSQL does not automatically "take just the one new 30.00 order" and add it to the aggregate via incremental materialized view maintenance. In principle, `REFRESH MATERIALIZED VIEW` **re-runs the defining query** to build the new result set, even though standard and concurrent refreshes apply the new contents differently.

### 8.2. Refresh Duration Depends on the Source Query

Even if `mv_daily_paid` holds only 30 rows, if it aggregates 500 million orders, refreshing that tiny materialized view still reads and aggregates **massive source data** every time.

### 8.3. Refreshes Are Not Scheduled Automatically

PostgreSQL has no built-in default schedule like "refresh every materialized view every minute." You need a scheduler/automation or external orchestration—such as an application job, OS scheduler, or an appropriate extension.

### 8.4. When Source Reads Are Still Required

An API requiring immediate visibility of data a user just wrote must query the source table or a synchronous read model; you cannot force such an API onto a stale materialized view merely because SELECTs are fast.

## 9. WITH NO DATA and the Unpopulated State

When creating a large materialized view, you may want to declare the object first without **immediately running the source query**:

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_daily_paid_unpopulated AS
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
WITH NO DATA;
~~~

### 9.1. Unpopulated Is Not Simply an Empty Table

A materialized view created `WITH NO DATA` starts in an **unpopulated / unscannable** state. Querying:

~~~sql
-- Error illustration: view is not yet populated.
SELECT * FROM mv_lab.mv_daily_paid_unpopulated;
~~~

does not return 0 rows like a valid empty table; PostgreSQL requires populating it before it can be scanned.

### 9.2. Initial Population

~~~sql
REFRESH MATERIALIZED VIEW
    mv_lab.mv_daily_paid_unpopulated;
~~~

Once this refresh succeeds, the materialized view transitions to populated and accepts SELECTs.

### 9.3. REFRESH ... WITH NO DATA

~~~sql
REFRESH MATERIALIZED VIEW
    mv_lab.mv_daily_paid_unpopulated
WITH NO DATA;
~~~

This discards stored data and marks the materialized view **unpopulated**, blocking SELECTs until refreshed with data again.

### 9.4. Creating the Object Does Not Make Dashboards Readable

Deployment pipelines must explicitly coordinate **when a materialized view is populated and ready** before switching application traffic to it. Never cut over traffic merely because `CREATE MATERIALIZED VIEW ... WITH NO DATA` succeeded.

## 10. Two Refresh Modes and Locking Behavior

PostgreSQL offers two primary options:

~~~sql
REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;
~~~

and:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

Both share the goal of updating materialized data, yet **their impact on readers and execution costs differ**.

| Criterion | Standard REFRESH | REFRESH CONCURRENTLY |
| --- | --- | --- |
| Can refresh when unpopulated? | Yes, for initial population | No |
| Requires a special UNIQUE index? | No | Yes |
| Concurrent SELECTs during refresh | Blocked by exclusive lock | Can continue reading old data |
| Impact on readers | Causes wait stalls | Minimizes read blocking, though resource contention/brief locks remain |
| Operational complexity | Simpler | Extra index requirements and diffing cost |
| Always faster? | Not guaranteed | No; sometimes slower |
| Incremental auto-update from WAL? | No | No |

### 10.1. Standard REFRESH and ACCESS EXCLUSIVE

Refreshing without `CONCURRENTLY` holds a lock that **blocks SELECTs** on the materialized view for the duration of the command. Thus, actively read dashboards can suffer latency spikes or timeouts during long refreshes.

### 10.2. REFRESH CONCURRENTLY and Availability

Concurrent refresh allows compatible SELECTs to continue querying the materialized view during refresh. Readers see the previous state until the new result set commits.

### 10.3. CONCURRENTLY Does Not Mean Zero Locking

Concurrent refresh still acquires locks, runs in a transaction, and consumes system resources; it can wait on other transactions, generate I/O and WAL, and affect overall load. "Less read blocking" does not mean "free and lockless."

### 10.4. Only One Refresh at a Time per Materialized View

PostgreSQL does not allow multiple concurrent refreshes on the **same materialized view** simultaneously. When a scheduler fires overlapping jobs, later jobs block or hit timeouts. Build overlap protection to avoid unbounded queuing.

## 11. UNIQUE Index Requirements for CONCURRENTLY

To use:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

the materialized view must:

1. **Already be populated**, not in `WITH NO DATA` state.
2. Have **at least one valid UNIQUE index** on the materialized view.
3. That UNIQUE index must reference **column names only**, not expressions.
4. That UNIQUE index must cover **all rows**, not be a partial index with `WHERE`.

### 11.1. Creating the Right UNIQUE Index for the Report

Each group is uniquely identified by `(report_date, region)`. In our lab, `region` is always `NOT NULL` and every pair is unique:

~~~sql
CREATE UNIQUE INDEX uq_mv_daily_paid_date_region
ON mv_lab.mv_daily_paid (report_date, region);
~~~

Then:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

satisfies both the UNIQUE index and populated requirements in the lab.

### 11.2. The UNIQUE Index Is Not Just for Speed

During concurrent refresh, PostgreSQL needs a way to match rows between the existing stored results and newly computed results. A full-coverage UNIQUE index is a technical prerequisite for the concurrent refresh diffing algorithm.

### 11.3. A UNIQUE Index Does Not Fix Broken GROUP BY Logic

If the source query can produce duplicate `(report_date, region)` pairs due to bad design, creating the unique index fails with a duplicate key error. The index **exposes the design bug** rather than merging duplicates into correct results.

## 12. UNIQUE Indexes That Do Not Qualify

### 12.1. Non-Unique Indexes

~~~sql
CREATE INDEX idx_mv_daily_paid_region
ON mv_lab.mv_daily_paid (region);
~~~

Helps region queries, but **does not enable `CONCURRENTLY`**.

### 12.2. Partial UNIQUE Indexes

~~~sql
-- Illustrative example of an index not meeting the requirement
-- covering all rows for concurrent refresh:
CREATE UNIQUE INDEX uq_mv_paid_north_only
ON mv_lab.mv_daily_paid (report_date, region)
WHERE region = 'north';
~~~

This index covers only a subset of rows and fails the full-coverage requirement for `REFRESH CONCURRENTLY`.

### 12.3. Expression-Based UNIQUE Indexes

~~~sql
-- Example that cannot replace a qualifying UNIQUE index:
CREATE UNIQUE INDEX uq_mv_daily_paid_expression
ON mv_lab.mv_daily_paid ((lower(region)), report_date);
~~~

This index uses an **expression `lower(region)`** rather than plain column names, so it does not qualify for concurrent refresh.

### 12.4. Do Not Create These Sample Invalid Indexes

In the lab, you only need `uq_mv_daily_paid_date_region` shown earlier. The partial/expression examples above exist solely to contrast requirements; **never create unnecessary indexes without a real query need**.

### 12.5. Watch Out for NULLs and Uniqueness

A standard PostgreSQL UNIQUE index treats multiple SQL `NULL` values as distinct by default. If your grouping key can contain NULLs, carefully verify uniqueness semantics and how concurrent refresh matches rows; a **NOT NULL, well-defined** grouping key is far simpler for concurrent refresh.

In the lab, `report_date` comes from `created_at NOT NULL` and `region` from a `NOT NULL` column, avoiding this pitfall.

## 13. Testing REFRESH CONCURRENTLY

With the materialized view populated and the UNIQUE index in place, insert another paid order:

~~~sql
INSERT INTO mv_lab.orders (
    customer_id, created_at, status, total_amount
) VALUES (
    2,
    '2026-01-11 15:00:00+00',
    'paid',
    25.00
);
~~~

### 13.1. Before Refresh

~~~sql
SELECT paid_orders, revenue
FROM mv_lab.v_daily_paid
WHERE report_date = DATE '2026-01-11'
  AND region = 'south';

SELECT paid_orders, revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-11'
  AND region = 'south';
~~~

The regular view sees the new value; the materialized view still holds results from the previous refresh.

### 13.2. Concurrent Refresh

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

### 13.3. After Refresh

~~~sql
SELECT paid_orders, revenue
FROM mv_lab.mv_daily_paid
WHERE report_date = DATE '2026-01-11'
  AND region = 'south';
~~~

Given the lab's sequential inserts with no other edits, this group now shows **2 paid orders, total 95.00**.

### 13.4. CONCURRENTLY Does Not Auto-Refresh on Every INSERT

Whenever source data changes, the materialized view remains stale **until a new refresh runs and commits**. `CONCURRENTLY` describes **how refresh interacts with concurrent readers**, not real-time updates.

## 14. UPDATE, DELETE, and Stale Data

Stale data isn't caused only by INSERTs. Test inside a rolled-back transaction to preserve lab data:

~~~sql
BEGIN;

-- A paid order changes amount.
UPDATE mv_lab.orders
SET total_amount = 150.00
WHERE order_id = 1;

-- Delete a paid order.
DELETE FROM mv_lab.orders
WHERE order_id = 8;

-- Regular view reflects changes within this transaction.
SELECT report_date, region, paid_orders, revenue
FROM mv_lab.v_daily_paid
ORDER BY report_date, region;

-- Materialized view does not update automatically.
SELECT report_date, region, paid_orders, revenue
FROM mv_lab.mv_daily_paid
ORDER BY report_date, region;

ROLLBACK;
~~~

### 14.1. Status UPDATEs Also Alter Result Sets

If an order moves from `pending` to `paid`, an aggregate group gains count and revenue. Conversely, changing `paid` to `cancelled` shrinks a group or **makes it disappear completely** if no paid orders remain.

### 14.2. DELETE Is Not Just Subtracting One Number

A deletion can shift multiple aggregates—`COUNT`, `SUM`, `MIN`, `MAX`, `AVG`, distinct counts, and JOIN logic. This makes hand-rolled incremental maintenance harder than it looks at first glance.

### 14.3. Changes in Joined Tables Matter Too

In the lab, `region` comes from `customers`. If a customer moves from `north` to `south`, **regional reports** change even with zero new orders. Refresh schedules must account for every table referenced in the query, not just the fact table.

## 15. Impact of Refresh Intervals

Suppose a job runs every 5 minutes and takes 40 seconds to complete.

~~~text
10:00:00  Start refresh A; source snapshot selected
10:00:40  A finishes
10:02:00  New order COMMITs
10:05:00  Start refresh B
10:05:40  B finishes
~~~

From 10:02 until B publishes its results, the dashboard lacks the new order.

### 15.1. Schedule Interval Does Not Equal Freshness SLA

"Refresh every 5 minutes" **does not guarantee max staleness of 5 minutes**, because:

- Jobs can start late.
- Jobs can run long.
- Jobs can fail and require retries.
- Jobs can stall on locks or resource contention.
- The refresh's source snapshot is taken **before** completion time.
- Long-running source transactions can commit after the snapshot.

### 15.2. Defining Freshness in Business Terms

Examples:

- "Dashboard tolerates up to 15 minutes of lag under normal operations."
- "After each successful refresh, a banner displays the last update timestamp."
- "If no refresh succeeds for 30 minutes, alert operators and disable sensitive actions relying on those metrics."

Tie SLAs to the **business impact of stale data**, not just scheduler cron frequency.

### 15.3. Do Not Pick a Schedule Merely Because It Is Easy to Configure

Refreshing every minute can overload the database if a full-history aggregation takes 50 seconds on a busy primary. Refreshing hourly may be too infrequent if operations dashboards track active fulfillment. Measure source query costs and gather real user requirements.

## 16. Cost of a Single REFRESH

A materialized view with few rows does not imply a cheap refresh.

### 16.1. Reading Source Data

PostgreSQL must execute the defining query. If it aggregates all paid orders from the beginning of history, each refresh may have to:

1. Scan a huge volume of source rows.
2. JOIN with customers or related tables.
3. Filter statuses.
4. GROUP BY and compute aggregates.
5. Rewrite or diff materialized data according to the refresh mode.
6. Maintain corresponding indexes.

### 16.2. CPU and Memory

Sorts, hash aggregates, hash joins, and expression evaluation all consume resources. Insufficient `work_mem` causes nodes to spill to temporary disk storage.

### 16.3. I/O and WAL

Rewriting materialized data and indexes generates substantial I/O and WAL. On replicated setups, WAL spikes can increase replica lag.

### 16.4. Contention with Write Workloads

Large refreshes drive heavy reads, cache eviction, and resource pressure, impacting production INSERT/UPDATE latency even when using `CONCURRENTLY`.

### 16.5. Storage Footprint

Materialized views store separate copies of rows and indexes; creating many overlapping materialized views multiplies storage and maintenance overhead.

## 17. Why Is CONCURRENTLY Sometimes Slower Than Standard REFRESH?

Concurrent refresh is designed to update without holding long read-blocking locks like standard refresh. It must diff the new query result against existing contents while maintaining indexes and constraints.

### 17.1. It Is Not Just Applying a Few WAL Changes

`CONCURRENTLY` in core PostgreSQL **does not mean incremental view maintenance** reading a delta of new orders. The defining query still recomputes the full candidate result set to diff against the current materialized view.

### 17.2. Trading Refresh Speed for Read Availability

For heavily read dashboards, avoiding SELECT stalls easily outweighs a few extra seconds of refresh time. Conversely, a materialized view used solely by an overnight batch job may be better served by a simpler standard refresh.

### 17.3. Change Ratio Also Matters

When nearly every aggregated row changes after a bulk write, diffing overhead yields low benefit. When few rows change, diffing still has baseline cost, and neither mode wins universally.

### 17.4. Measure Read Availability Too

Benchmarks should capture:

- Total refresh duration.
- Time SELECTs spend waiting on locks.
- Dashboard p95/p99 latency during refresh.
- CPU, I/O, WAL, and temp files.
- Storage and index overhead.

Measuring refresh duration in isolation misses the primary purpose of `CONCURRENTLY`: keeping readers unblocked.

## 18. Monitoring Materialized View Status

PostgreSQL provides the `pg_matviews` system view:

~~~sql
SELECT
    schemaname,
    matviewname,
    matviewowner,
    ispopulated,
    hasindexes,
    definition
FROM pg_matviews
WHERE schemaname = 'mv_lab'
ORDER BY matviewname;
~~~

### 18.1. ispopulated

`ispopulated` indicates whether the materialized view is scannable. It **does not tell you how fresh the data is**.

### 18.2. hasindexes

`hasindexes` indicates that indexes exist, **not whether a qualifying UNIQUE index exists for `CONCURRENTLY`**.

### 18.3. definition

`definition` shows the stored SQL. Verify filters, JOINs, and timezone logic before finalizing refresh schedules.

### 18.4. PostgreSQL Does Not Provide a Built-In Reliable last_refresh_at for Every MV

`pg_matviews` is not a refresh history log. To know when the last successful refresh occurred, **record logs/metrics in your operational pipeline** or monitoring system.

## 19. Creating a Dedicated Refresh Log Table

To track successful refresh history:

~~~sql
CREATE TABLE mv_lab.refresh_log (
    refresh_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matview_name text NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    refresh_mode text NOT NULL
        CHECK (refresh_mode IN ('blocking', 'concurrent')),
    note text
);
~~~

### 19.1. Logging Success in the Same Transaction

Lab example using standard refresh:

~~~sql
BEGIN;

REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;

INSERT INTO mv_lab.refresh_log (
    matview_name, finished_at, refresh_mode, note
) VALUES (
    'mv_lab.mv_daily_paid',
    clock_timestamp(),
    'blocking',
    'Refresh completed inside transaction'
);

COMMIT;
~~~

Because the refresh and log insert share one transaction, on `COMMIT` both become visible atomically. If the refresh fails, the transaction rolls back and no false success is logged.

### 19.2. finished_at Is Not Necessarily the Source Snapshot Cutoff

`finished_at` here records when the log row was written after refresh completion, **not necessarily** when the source snapshot was taken. It tracks operational cadence, not an exact source watermark.

### 19.3. If Logging Runs Outside the Transaction

If a scheduler logs **after** the refresh commits, a small gap or logging failure can occur between the two operations. Distinguish **actual refresh state** from **observed telemetry**, and support retries/reconciliation.

### 19.4. Where to Log Failures?

If a refresh fails, you cannot insert a failure row inside the same aborted transaction. The scheduler/worker must roll back and record the failure in a separate transaction or logging system so operators see the failure without advancing the success timestamp.

## 20. Computing Time Since Last Successful Refresh

~~~sql
SELECT
    matview_name,
    MAX(finished_at) AS last_successful_refresh,
    EXTRACT(
        EPOCH FROM (
            clock_timestamp() - MAX(finished_at)
        )
    ) AS seconds_since_success
FROM mv_lab.refresh_log
WHERE matview_name = 'mv_lab.mv_daily_paid'
GROUP BY matview_name;
~~~

### 20.1. Missing Logs Must Be Handled Explicitly

If no log rows exist yet, the query returns zero rows. Operational dashboards should display **"unknown / no successful refresh recorded"** clearly rather than defaulting lag to 0.

### 20.2. Refresh Age Is Not Unsynced Order Count

`seconds_since_success` measures elapsed seconds since logging, not how many source changes remain unrefreshed. If the source has been idle, data may still be exact even with an old refresh timestamp. If source traffic is intense, even a recently finished refresh may trail recent commits.

### 20.3. Labeling for End Users

Example dashboard banner:

~~~text
Daily revenue — metrics refreshed at 10:05:40 UTC
Order source data may have changed after processing time.
~~~

Display timestamps in a timezone appropriate for the audience; never let users mistake a UTC timestamp for local time.

## 21. Source Watermarks and True Freshness

An aggregated report may need to define **up to what point source data was processed** rather than relying solely on job finish time.

### 21.1. Never Use MAX(created_at) as a Refresh Timestamp

Our lab includes:

~~~sql
MAX(o.created_at) AS latest_paid_order_at
~~~

That is the **newest paid order timestamp within each group**. There is no reason it equals refresh time. A backdated entry with an old `created_at` can even alter last month's revenue.

### 21.2. Source Tables Need Change Tracking

Systems can rely on:

- Consistently maintained `updated_at` timestamps.
- Sequences or event offsets in a change stream.
- Suitable CDC/WAL-based processing.
- Batch ingestion completion markers.
- Verified job IDs or partition IDs.

Still account for **UPDATEs, DELETEs, and joined-table changes**. `MAX(created_at)` on orders misses customers changing regions or old orders getting refunded.

### 21.3. updated_at Alone Does Not Solve Everything Automatically

A `DELETE`d row is no longer present to return in `MAX(updated_at)`. If application-supplied timestamps are skewed or transactions commit out of timestamp order, watermarks can miss changes. Design audit/change logs or synchronization mechanisms aligned with your SLA.

### 21.4. "Fresh" Must Be Verifiable

If the SLO states "every change committed before T appears in the report," the architecture needs a **monotonic change ordering source** and proof of processing up to T. A simple refresh log timestamp alone cannot prove that guarantee.

## 22. Refresh Schedules and Periodic Operations

Suppose operations tolerates up to ~15 minutes of lag under normal conditions, and refreshes average 1–2 minutes.

A rough initial schedule might run every 5 minutes, while monitoring:

1. On-time job completion rate.
2. p95/p99 refresh duration, not just average.
3. Queue wait / lock wait duration.
4. Job failure rate and retry behavior.
5. Primary database CPU and I/O load.
6. Impact on transactional queries.

### 22.1. External Scheduler Example

A scheduled job executes:

~~~sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_lab.mv_daily_paid;
~~~

on schedule and logs outcome metadata. The scheduler can live in an application worker, orchestration tool, OS cron, or a separately installed and configured extension.

### 22.2. Do Not Assume pg_cron Is Available

`pg_cron` is an extension supporting in-database scheduling in some PostgreSQL environments, but **it is not always installed, enabled, or permitted**. Check your PostgreSQL version/provider docs and operational policy before designing around it.

### 22.3. Schedulers Must Handle Overlapping Runs

If a 5-minute schedule hits an 8-minute refresh, the next run overlaps the active one. Implement skip, single-queue, or lock-coordination logic with alerts instead of piling up blocked workers.

### 22.4. Retries Must Be Bounded

Aggressive retries during database overload worsen incidents. Configure backoff, max attempts, timeouts, and degraded/stale dashboard states.

### 22.5. Notify Consumers

When refreshes fall behind SLA, APIs and UIs should surface the refresh timestamp and a staleness warning rather than silently presenting old figures as live data.

## 23. Coordinating to Prevent Overlapping Refreshes

PostgreSQL already blocks concurrent refreshes on the same materialized view, but schedulers still need to avoid **queuing up backlogged jobs**.

### 23.1. One Worker per Materialized View

The simplest design uses a dedicated queue or single-threaded job:

~~~text
Scheduled trigger 10:00
      |
      v
Is job already running?
      +-- Yes -> skip this run / mark delayed
      +-- No  -> start REFRESH
                        |
                        v
                  record result
~~~

### 23.2. Advisory Locks Can Help

Some schedulers coordinate using PostgreSQL advisory locks. Remember advisory locks are **cooperative** across workers following the same lock convention; they do not replace `REFRESH`'s internal locks, access privileges, or transaction semantics.

### 23.3. Choosing Lock Keys and Scope

If using advisory locks, define distinct lock keys per materialized view, choose session-level vs. transaction-level locks intentionally, ensure cleanup when workers crash, and monitor locks. Never share one global lock key across unrelated materialized views without reason.

### 23.4. Never Allow Unbounded Refreshes from HTTP Requests

A "Refresh Now" button must never let thousands of users invoke `REFRESH` directly. Instead, enqueue a coalesced refresh request, rate-limit it, and return progress/cooldown status.

## 24. Measuring Source Read Cost vs. Materialized View Read Cost

Before creating a materialized view, measure the source query cost:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.v_daily_paid
WHERE report_date BETWEEN DATE '2026-01-10'
                      AND DATE '2026-01-12';
~~~

Then compare with:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    report_date,
    region,
    paid_orders,
    revenue
FROM mv_lab.mv_daily_paid
WHERE report_date BETWEEN DATE '2026-01-10'
                      AND DATE '2026-01-12';
~~~

### 24.1. Plans Can Differ Dramatically

- The regular view may scan `orders`, JOIN `customers`, and aggregate.
- The materialized view may simply scan a small relation or use an index on `report_date`.

### 24.2. Lab Tables Are Too Small for Real Benchmarks

Eight to ten orders cannot demonstrate speedup over millions of source rows. PostgreSQL will likely choose `Seq Scan` for both queries with similar timings. The lab's purpose is **observing semantics**, not proving production speedups.

### 24.3. Account for Total Refresh Workload

If 100 users query per minute, a materialized view saves repeated aggregations. Yet if you refresh all hundreds of millions of orders every minute, background load becomes massive. Evaluate total load:

\[
\text{Total load} \approx
(\text{reads}\times\text{cost per read})
+(\text{refreshes}\times\text{cost per refresh})
\]

This is a simplified mental model, not an exact CPU/I/O formula once concurrency, caching, and replication enter the picture.

## 25. Metrics to Measure with EXPLAIN

| Metric | Meaning in Evaluation |
| --- | --- |
| `Execution Time` | Server execution duration of SELECT |
| `Planning Time` | Plan construction cost |
| `Seq Scan`/`Index Scan` | Access path on source/materialized view |
| `HashAggregate`/`GroupAggregate` | Aggregation cost in regular view |
| `Hash Join`/`Nested Loop` | How source tables are joined |
| `actual rows`, `loops` | Data volume processed per node |
| `Buffers: shared hit/read` | Block access footprint |
| `Sort`, `Sort Method` | Whether sorting occurs and spills |
| `temp read/written` | Temporary disk I/O, if any |

### 25.1. Do Not Equate Buffers with Row Counts

`shared hit=1000` does not mean 1,000 rows were read; each block holds multiple rows and can be touched repeatedly.

### 25.2. Do Not Sum Buffers Across All Nodes

Parent nodes include buffer counts from child nodes in `BUFFERS` output. Summing them blindly double-counts blocks.

### 25.3. Query Latency Differs from Dashboard Latency

Dashboards also incur network, driver, serialization, authentication, and rendering time. Fast server SQL does not guarantee end-to-end SLA compliance under heavy load or oversized payloads.

### 25.4. Check Actual vs. Estimated Rows

Severe planner row misestimates lead to poor scan, join, or sort choices. Run `ANALYZE` on both sources and materialized views as needed rather than blindly adding indexes.

## 26. Indexing Materialized Views for Read Queries

Suppose dashboards filter by region and date range:

~~~sql
SELECT report_date, region, paid_orders, revenue
FROM mv_lab.mv_daily_paid
WHERE region = 'north'
  AND report_date >= DATE '2026-01-01'
ORDER BY report_date DESC;
~~~

A suitable index to consider:

~~~sql
CREATE INDEX idx_mv_daily_paid_region_date
ON mv_lab.mv_daily_paid (region, report_date DESC);
~~~

### 26.1. UNIQUE Index vs. Read Index Goals

`UNIQUE(report_date, region)` enables concurrent refresh and helps some date-range filters. However, queries filtering `region` first and sorting dates descending benefit from `(region, report_date DESC)`.

### 26.2. Skip Extra Indexes on Tiny Materialized Views

A materialized view with a few dozen rows is already fast via Seq Scan. Extra indexes add storage and refresh overhead; measure before adding them.

### 26.3. Indexing Aggregate Metrics

If dashboards often look up "top revenue days," an index on `revenue DESC` can help specific queries. Evaluate indexes supporting ORDER BY/LIMIT and filters against actual workload patterns.

### 26.4. Remember Permissions and Sensitive Data

Indexes do not enforce access control. A materialized view persists a copy of data; if it stores sensitive customer or revenue data, enforce `SELECT` privileges and appropriate retention/deletion cycles.

## 27. Source Table Indexes Affect REFRESH Cost

Materialized views read quickly, yet refreshes still run the source query. Thus source indexes still matter.

~~~sql
CREATE INDEX idx_orders_paid_created
ON mv_lab.orders (created_at)
WHERE status = 'paid';
~~~

### 27.1. When Source Indexes Help

A source query aggregating only paid orders from the last 7 days with a selective time predicate can benefit greatly from a matching index.

### 27.2. When Source Indexes May Not Help

If the materialized view aggregates **all paid orders ever placed** and paid orders make up most of the table, PostgreSQL will likely prefer `Seq Scan` on the source because sequential reads beat random heap fetches via an index.

### 27.3. Partition Pruning

On date-partitioned source tables where the refresh query targets a bounded window, predicates on the partition key prune irrelevant partitions. If the materialized view aggregates all history, window-based partition pruning does not apply automatically.

### 27.4. Never Add Time Filters That Corrupt Report Semantics

If users expect **all-time** revenue, never silently add `WHERE created_at >= now()-interval '30 days'` just to speed up refresh without updating the report's contract.

## 28. ANALYZE and Statistics After REFRESH

The PostgreSQL planner relies on statistics to estimate selectivity and pick indexes.

~~~sql
ANALYZE mv_lab.mv_daily_paid;
~~~

### 28.1. REFRESH and Statistics Are Separate Steps

Do not assume `REFRESH MATERIALIZED VIEW` immediately updates all planner statistics identically to `ANALYZE`. After significant size or distribution shifts, run `ANALYZE` per operational policy.

### 28.2. Inspecting Physical Size

~~~sql
SELECT
    pg_size_pretty(
        pg_relation_size('mv_lab.mv_daily_paid'::regclass)
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size('mv_lab.mv_daily_paid'::regclass)
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size('mv_lab.mv_daily_paid'::regclass)
    ) AS total_size;
~~~

### 28.3. Materialized Views Can Grow Larger Than Expected

If a materialized view retains raw JSON blobs or wide text fields instead of just required aggregates, storage and refresh costs balloon. Design projections carefully.

### 28.4. Source Statistics

~~~sql
ANALYZE mv_lab.orders;
ANALYZE mv_lab.customers;
~~~

helps the planner optimize the refresh query on sources, though it does not replace choosing an appropriate refresh schedule.

## 29. Activity Statistics and Monitoring

Catalog/statistics views assist observation:

~~~sql
SELECT
    schemaname,
    relname,
    seq_scan,
    idx_scan,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'mv_lab'
ORDER BY relname;
~~~

### 29.1. Do Not Mistake last_analyze for last_refresh

`last_analyze` records when statistics were updated, **not** when the materialized view was refreshed. Never use it as a freshness indicator.

### 29.2. Observing Active Locks and Queries

With appropriate privileges, `pg_stat_activity` and `pg_locks` help diagnose waiting refreshes or blocked SELECTs:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start,
    left(query, 180) AS query_prefix
FROM pg_stat_activity
WHERE query ILIKE '%REFRESH MATERIALIZED VIEW%'
ORDER BY query_start;
~~~

Results can include your own monitoring query itself; filter/interpret in context rather than treating a substring match as definitive proof a refresh job is running.

### 29.3. Avoid Excessive Polling

Monitor frequently enough to detect slow, failed, or overdue jobs without hammering the server with thousands of catalog queries per second. With many materialized views, track scheduler/observability metrics centrally.

## 30. Windowed Refresh Designs

A common optimization stores only the most recent 30 days:

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_paid_last_30_days AS
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS revenue
FROM mv_lab.orders AS o
WHERE o.status = 'paid'
  AND o.created_at >= clock_timestamp()
                      - INTERVAL '30 days'
GROUP BY (o.created_at AT TIME ZONE 'UTC')::date
WITH DATA;
~~~

### 30.1. Moving Windows Shift on Each Refresh

The "30 days before now" threshold evaluates when the refresh executes. Materialized rows can retain groups that have since aged out of the window **until the next refresh**.

### 30.2. Not an Index Over a Fixed Window

A sliding-window materialized view does not mean the source table is automatically partitioned/pruned for all queries. Refreshes still execute the defining query predicate, and index usage depends on predicate structure and data distribution.

### 30.3. 30 Rolling Days vs. "30 Calendar Days"

`clock_timestamp() - interval '30 days'` expresses a relative 30-day span from execution time, not necessarily 30 full UTC calendar days. For daily reports, clarify day/month boundaries and timezones explicitly.

### 30.4. Risks of Non-Deterministic Time Functions in Queries

`clock_timestamp()` can advance mid-query while running. When a refresh needs a consistent cutoff, use a statement-stable timestamp or pass a controlled cutoff from orchestration. This example illustrates **rolling windows vs. refresh timing**—do not use it carelessly in financial reporting.

### 30.5. Consider Partition/Batch Designs Over Sliding Windows

For large historical reports, split data by day or month, refresh recent open periods, and freeze closed periods per business policy. That is a dedicated summary architecture problem, not something core `REFRESH` solves automatically.

## 31. Querying Fresh and Historical Data Together

Sometimes dashboards need:

- Fast pre-aggregated history from a materialized view.
- The last few minutes of live data queried directly from source tables.

A **hybrid** architecture splits them:

~~~text
Closed / precomputed history -> materialized view
Recent data window          -> live aggregate
                               |
                               v
                           merge results
~~~

### 31.1. Prevent Double-Counting

If the materialized view already includes part of today and the live query also aggregates all of today, a naive `UNION ALL` **double-counts revenue**.

### 31.2. Establish a Deterministic Cutoff Boundary

One approach materializes data up to a verified **cutoff/batch watermark**, while live queries read strictly after that cutoff. Even then, handle updates/cancellations to older orders and late-arriving transactions.

### 31.3. Late-Arriving Changes Break "Immutable History" Assumptions

An order placed last month that gets cancelled or refunded today changes historical aggregates. When systems allow modifying past records, "only compute deltas from today" is incomplete.

### 31.4. Do Not Build Hybrid Architectures If Simple Refreshes Suffice

Merging two sources adds complexity, testing surface, and discrepancy risk. If reports tolerate 10 minutes of lag, a periodically refreshed materialized view is vastly simpler.

## 32. Incremental Summary Tables: An Alternative

Some systems maintain **summary tables** updated by events/transactions instead of recomputing the full query.

Example table:

~~~sql
CREATE TABLE mv_lab.daily_paid_summary (
    report_date date NOT NULL,
    region text NOT NULL,
    paid_orders bigint NOT NULL,
    revenue numeric(14, 2) NOT NULL,
    PRIMARY KEY (report_date, region)
);
~~~

### 32.1. Incremental Updates via UPSERT

A newly confirmed paid order event increments the matching group:

~~~sql
INSERT INTO mv_lab.daily_paid_summary (
    report_date, region, paid_orders, revenue
) VALUES (
    DATE '2026-01-10',
    'north',
    1,
    30.00
)
ON CONFLICT (report_date, region)
DO UPDATE SET
    paid_orders = mv_lab.daily_paid_summary.paid_orders
                  + EXCLUDED.paid_orders,
    revenue = mv_lab.daily_paid_summary.revenue
              + EXCLUDED.revenue;
~~~

### 32.2. Illustrative Only, Not Yet a Safe Pipeline

If an event is reprocessed—such as retrying the same order—totals get **counted twice**. If orders are cancelled or modified, you must apply positive/negative deltas and handle group transfers. Production pipelines need idempotency, source-of-truth guarantees, transaction boundaries, and reconciliation jobs.

### 32.3. MAX/MIN/COUNT DISTINCT Are Harder Than SUM

With simple `SUM`/`COUNT`, deltas are easy given old/new states. Deleting the current `MAX` requires rescanning for the next max; `COUNT(DISTINCT)` requires tracking value sets. Incremental maintenance is not always trivial.

### 32.4. Trade-Off Comparison

| Approach | Pros | Risks / Costs |
| --- | --- | --- |
| Materialized view (full refresh) | Simple logic, recomputes cleanly from source | Expensive refresh, stale data |
| Incremental summary table | Near real-time, avoids full recomputation | Sync complexity, double-counting, deltas, recovery |
| Regular VIEW | Fresh per query snapshot, minimal pipeline | Recomputes on every query |
| External cache | Offloads DB reads, flexible TTLs | Invalidation, consistency, deployment overhead |

### 32.5. Core PostgreSQL Materialized Views vs. Incremental Extensions

Third-party extensions or external tools can provide incremental view maintenance, yet **core `REFRESH` syntax does not automatically support arbitrary incremental strategies**. Never assume unverified extensions or privileges exist in your default architecture.

## 33. Read Replicas and Multi-Layer Freshness

An architecture may combine a primary database, a streaming replica, and a materialized view.

~~~text
Primary: new order COMMITs
            |
            v
Replication lag
            |
            v
Replica: source data may lag
            |
            v
Materialized view: snapshot from last refresh
            |
            v
Dashboard
~~~

### 33.1. Staleness Compounds Across Layers

If a report refreshes from a source already carrying replication lag, plus the refresh schedule interval, total lag stacks across layers. Production designs must track **where refreshes execute and where they read from**.

### 33.2. Do Not Assume Refresh Works on Standby

DDL/DML execution on PostgreSQL standbys is restricted by read-only mode. Never assume `REFRESH MATERIALIZED VIEW` can run on every read replica. Verify cluster topology and writable nodes.

### 33.3. Reading from Replicas Also Needs an SLA

Even right after a primary materialized view refreshes, an application querying a lagging replica can still see the previous version. Measure replication lag and read consistency against requirements.

## 34. Refresh Snapshots and Concurrent Transactions

A materialized view is built from a **consistent snapshot** of the source query under PostgreSQL transaction semantics.

### 34.1. Two Concurrent Source Transactions

Suppose:

~~~text
T1: INSERT order A, not yet COMMITted
T2: REFRESH materialized view, selects snapshot
T1: COMMIT order A
T2: finishes refresh
~~~

T2's refresh result **will not contain order A** because at the time T2's snapshot was taken, A was uncommitted and invisible.

### 34.2. No "Half-Committed Orders"

If a source transaction updates multiple tables atomically, the refresh snapshot sees consistent state under MVCC rules; it will never read half of a committed transaction under normal operation.

### 34.3. Long-Running Reader Transactions

A reader querying a materialized view inside a higher-isolation transaction may continue seeing an older snapshot per isolation rules even after another refresh commits. Never treat refresh commit time as a guarantee that **every open connection immediately observes new rows** across all isolation levels.

### 34.4. Freshness Is an Application-Wide Contract

If an API promises "read back immediately after writing," querying a materialized view without synchronization breaks *read-your-writes* expectations. Choose the right read source or communicate lag clearly.

## 35. When Should You Avoid Materialized Views?

### 35.1. Real-Time Financial or Inventory Decisions

Inventory checks accepting new orders or balance checks enforcing transactional invariants must never rely solely on a potentially stale aggregate. Query source tables with proper transactions and locking for correctness.

### 35.2. Fast-Changing Data with Near-Zero Lag SLA

If every committed write must appear immediately, periodic refresh cannot keep up without complex synchronization; an incremental read model or direct source query fits better.

### 35.3. Cheap, Infrequently Called Source Queries

If a report runs once a week over a few thousand rows taking tens of milliseconds, adding a materialized view, cron job, and monitoring creates unnecessary operational overhead.

### 35.4. Results Varying per User or Permission

A materialized view stores one shared result set for its defining SELECT. When applications require per-user or per-tenant security filtering, enforce proper privileges, predicates, and partitioning—never materialize a system-wide copy and grant broad SELECT just "for speed."

### 35.5. Oversized Outputs or Refresh Exceeding Its Window

If a materialized view keeps nearly every raw row and refreshes take longer than the schedule interval, costs outweigh benefits. Look at source indexing, partitioning, pre-aggregation, or incremental pipelines.

## 36. Managing Privileges on Materialized Views

A materialized view is a database object with its own ownership and access privileges.

### 36.1. Read Privileges Differ from Source Table Privileges

Roles granted `SELECT` on a materialized view can read its materialized contents according to the object's privileges, even without direct privileges on all underlying source tables. Hence a materialized view can become a **sensitive data copy** that must be governed.

### 36.2. REFRESH Privileges

`REFRESH MATERIALIZED VIEW` enforces ownership/privilege checks per PostgreSQL version. Never grant refresh or broad ownership rights to dashboard roles that only need `SELECT`.

### 36.3. When Source Rows Are Deleted

If a source row is deleted for privacy compliance, materialized view contents may still retain aggregated figures or copied details until the next refresh. Strict deletion SLAs must cover materialized views and any other caches/copies.

### 36.4. Evaluate Row-Level Security Separately

RLS on source tables never guarantees that every reader querying a materialized view is filtered per caller permissions. Explicitly audit the security context of the materializing query and SELECT grants on the materialized view.

## 37. Schema Migrations Affecting Materialized Views

When underlying tables or views change schema:

- Renaming or dropping referenced columns is blocked by PostgreSQL dependencies or requires coordinated migration.
- Changing revenue formulas can invalidate old materialized view definitions semantically.
- Changing column data types may require recreating the materialized view and its indexes.

### 37.1. No Direct CREATE OR REPLACE Like Regular Views

For materialized views, changing the query definition is not as simple as `CREATE OR REPLACE VIEW`. To change structure safely, create a new materialized view, populate and index it, verify results, and cut applications over to the new name/version.

### 37.2. Illustrative Rolling Cutover

~~~text
mv_daily_paid_v1  -> currently serving dashboard

1. Create mv_daily_paid_v2 with new query.
2. Populate v2 and build required indexes.
3. Verify results and access privileges.
4. Switch application reads to v2 via proper deployment.
5. Monitor and keep rollback capability for the required window.
6. Only then clean up v1.
~~~

### 37.3. Never Rename or Drop Impulsively

Renaming, dropping, and recreating materialized views involves permissions, dependencies, locks, and active connections. Plan rollouts to avoid outages or losing fresh data/refresh logs.

### 37.4. Rebuild the UNIQUE Index on the New Version

If v2 uses `REFRESH CONCURRENTLY`, build a qualifying full-coverage UNIQUE index matching v2's grouping key after initial population. Never assume v1's index carries over to v2.

## 38. Recovery, Refresh Failures, and Last Known Good Data

A refresh can fail due to:

- Insufficient disk/temp space.
- Statement timeouts, lock timeouts, or deadlocks.
- Source query errors after DDL/schema changes.
- Duplicate keys breaking the UNIQUE index on new results.
- Database restarts or scheduler connection drops.

### 38.1. Never Mark Failed Refreshes as Succeeded

Logs and schedulers must separate states:

~~~text
started -> running -> succeeded
                |
                +-> failed
~~~

If a refresh fails, **never update `last_successful_refresh`** with the start timestamp or retry timestamp.

### 38.2. Continuing to Serve Stale Data

In many cases, when a populated materialized view fails to refresh, applications can continue reading data from the last successful refresh. Still, verify object state and surface clear freshness notices—never assume all failures leave availability intact.

### 38.3. Unpopulated Views Have No Fallback

A materialized view created `WITH NO DATA` that has never completed a refresh cannot serve reports; cutting over early triggers runtime errors.

### 38.4. Retry Only After Fixing Root Causes

If a unique index is missing, create it first. If the source query is too heavy, optimize, provision resources, or adjust the schedule. Never hammer the database with rapid retries hoping a structural error vanishes.

## 39. Designing SLOs/SLAs Across Three Axes

Every materialized view decision should define at least three axes:

1. **Read latency:** How fast must the API/dashboard respond?
2. **Freshness:** How much lag relative to source writes is acceptable?
3. **Availability during refresh:** Can readers tolerate waiting/blocking?

| Example Use Case | Read Latency | Freshness | Design Option to Consider |
| --- | --- | --- | --- |
| Daily revenue report | Low | Minutes of lag okay | Periodically refreshed MV |
| Hourly executive dashboard | Low | Tens of minutes okay | MV or batch summary |
| Payment confirmation | Very low | Near commit-time | Source transaction / sync read model |
| Multi-year historical stats | Low | Infrequent updates | Scheduled MV or summary table |
| Ad-hoc exploration | Varies | Often needs fresh snapshot | Source query / analytics store |

### 39.1. No Single Answer Fits Every Use Case

Freshness and latency always depend on business context. Yesterday's summary can lag by hours; a screen verifying a newly submitted payment cannot.

### 39.2. Tie SLA Numbers to Real Measurements

If you commit to "p99 freshness within 15 minutes," measure the time from when source changes commit/arrive to when they appear in the materialized view, or a clearly defined proxy. Measuring `now() - last_refresh_finished_at` alone does not prove the full guarantee.

### 39.3. Define Degraded Behavior Up Front

When refreshes fall overdue:

- Return stale figures with a warning banner?
- Disable sensitive actions?
- Fall back to querying source tables directly?
- Rate-limit fallback concurrency to avoid crashing the primary DB?

These are product and SRE decisions, not mere SQL flags.

## 40. Safe Materialized View Deployment Workflow

A practical workflow includes:

1. **Define the source query** and validate correctness on representative data.
2. **Set business boundaries**, timezones, order statuses, and historical-edit handling.
3. **Measure baseline** source query cost with `EXPLAIN (ANALYZE, BUFFERS)`.
4. **Choose projections and grouping keys** without superfluous columns.
5. **Create the materialized view** in the proper schema/ownership; run initial population.
6. **Build a full-coverage UNIQUE index** if using concurrent refresh.
7. **Build workload-driven read indexes** without duplicates.
8. **Run `ANALYZE`** on the materialized view and sources where appropriate.
9. **Measure both REFRESH duration and SELECT latency** under load.
10. **Configure a scheduler** with overlap protection, timeouts, and bounded retries.
11. **Log successful refresh timestamps** and alert on overdue thresholds.
12. **Cut APIs over** only once the materialized view is populated and verified.
13. **Monitor lag and correctness** across source updates.
14. **Prepare rollback/fallback** if refreshes fail or freshness SLOs breach.
15. **Review periodically** for storage, WAL, schema changes, and sensitive data exposure.

Crucially, creating the materialized view is not the finish line. **Refresh scheduling, staleness tracking, and failure handling are integral parts of the design.**

## 41. Common Mistakes

### Mistake 1. Assuming Materialized Views Auto-Update with Source Tables

Source `INSERT`, `UPDATE`, and `DELETE` never refresh materialized results automatically. You need explicit refreshes or a dedicated incremental architecture.

### Mistake 2. Treating "Refresh Every 5 Minutes" as "Freshness <= 5 Minutes"

Jobs take time, start late, fail, and wait on locks; plus snapshots are captured before job completion.

### Mistake 3. Confusing Stale Data with Inconsistent Data

A materialized view can be stale while still faithfully reflecting a consistent past snapshot. Distinguish snapshot consistency from snapshot age.

### Mistake 4. Thinking CONCURRENTLY Updates Per Transaction

`CONCURRENTLY` avoids long SELECT locks during refresh; it does not perform automatic incremental maintenance.

### Mistake 5. Running CONCURRENTLY Without a Qualifying UNIQUE Index

Requires a full-coverage, non-partial, column-only UNIQUE index.

### Mistake 6. Running CONCURRENTLY on a WITH NO DATA Materialized View

The materialized view must already be populated; use standard refresh for initial population.

### Mistake 7. Assuming Expression UNIQUE Indexes Qualify

An index on `lower(region)` cannot satisfy concurrent refresh's column-only UNIQUE index requirement.

### Mistake 8. Assuming Partial UNIQUE Indexes Qualify

An index filtered by `WHERE region='north'` does not cover all rows in the materialized view.

### Mistake 9. Overlooking NULLs in Grouping Keys

UNIQUE indexes have specific NULL semantics; define NOT NULL grouping keys clearly to prevent surprises.

### Mistake 10. Assuming CONCURRENTLY Is Always Faster

Computing and applying diffs adds overhead; its primary benefit is keeping readers unblocked.

### Mistake 11. Thinking Refresh Only Reads New Source Rows

Core PostgreSQL typically re-runs the defining query rather than replaying WAL deltas.

### Mistake 12. Assuming Small MVs Always Have Cheap Refreshes

A 10-row summary can still require aggregating hundreds of millions of source rows.

### Mistake 13. Failing to Verify JOIN Cardinality Before Aggregation

One-to-many JOINs inflate revenue before materialization. The MV simply stores and serves wrong totals faster.

### Mistake 14. Treating latest_paid_order_at as last_refresh_at

`MAX(created_at)` is a business timestamp on rows, not refresh execution time or a complete source cutoff.

### Mistake 15. Using pg_matviews.ispopulated as a Freshness Metric

`ispopulated` only confirms the object is scannable, not how many minutes it lags behind sources.

### Mistake 16. Using last_analyze as last_refresh

`ANALYZE` updates planner statistics; it does not mean the MV was refreshed.

### Mistake 17. Logging Success Before Refresh Commits

If a refresh errors or rolls back while logs claim success, monitoring misleads everyone.

### Mistake 18. Ignoring Scheduler Failures

Missing alerts, retries, and fallbacks let days-old data appear normal on dashboards.

### Mistake 19. Overlapping Refreshes

Multiple queued jobs waiting on the same MV increase latency and contention. Coordinate runs.

### Mistake 20. Forgetting ANALYZE and Indexes on the MV

An MV stores physical data; heavy read queries need suitable indexes and statistics.

### Mistake 21. Over-Indexing

Every index adds storage and refresh overhead; index strictly for real query workloads.

### Mistake 22. Using MVs as Real-Time Authorization Sources

MVs hold separate copies with independent grants and stale state; enforce access controls independently.

### Mistake 23. Ignoring Historical UPDATEs and DELETEs

Adding only new orders fails whenever old transactions change status, amount, region, or get deleted.

### Mistake 24. Hybrid Live/MV Queries Without a Cutoff

Combining MV and live queries without strict boundaries causes double-counting or gaps.

### Mistake 25. Running REINDEX Instead of REFRESH

`REINDEX` rebuilds indexes over existing stored rows; it never re-runs the source query to update aggregates.

### Mistake 26. Expecting REFRESH to Migrate Schema Changes

Refresh recomputes data under the existing definition; it does not update outdated schemas or business formulas.

### Mistake 27. Routing Traffic to an Unpopulated MV

`WITH NO DATA` leaves the MV unscannable; populate before enabling reads.

### Mistake 28. Expecting Definition ORDER BY to Persist Forever

Not guaranteed after refreshes. Put `ORDER BY` on every consumer SELECT needing ordered output.

### Mistake 29. Ignoring Source Replica Lag

Reading/refreshing from lagging replicas makes real staleness exceed primary refresh intervals.

### Mistake 30. Treating Every Use Case as a Materialized View Fit

Real-time transactions, row-level sensitive data, and small tables often do not justify the trade-off.

## 42. Practice Exercises

Use the lesson's `mv_lab` schema. Run table/index creation only in a lab environment. Operational planning questions should never be applied directly to production.

### Exercise 1. Comparing VIEW and MV

State the two most important differences between regular views and materialized views regarding newly written source data and SELECT cost.

### Exercise 2. Freshness

A paid order commits after the last refresh. Does the materialized view update revenue automatically? Why or why not?

### Exercise 3. Consistency

A report excludes a newly created order yet matches an earlier snapshot accurately. Is the report "inconsistent" or "stale"?

### Exercise 4. Creating a Regular VIEW

Write a view aggregating by UTC date and region, counting only `paid` orders.

### Exercise 5. Creating a Materialized View

Write DDL creating a materialized view from `mv_lab.v_daily_paid`, populated immediately.

### Exercise 6. Querying After INSERT

If a `30.00` paid order is inserted into `north` on 2026-01-10, what revenue do the regular view and MV return before refresh?

### Exercise 7. Refreshing

Write the command to refresh `mv_lab.mv_daily_paid` after source changes.

### Exercise 8. WITH NO DATA

Can you SELECT from a materialized view created `WITH NO DATA`? Which command populates it initially?

### Exercise 9. ispopulated

Write SQL querying `pg_matviews` for the populated state of MVs in `mv_lab`.

### Exercise 10. Concurrent Refresh

List the three main requirements to run `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

### Exercise 11. UNIQUE Index

Write a valid UNIQUE index on `(report_date, region)`.

### Exercise 12. Partial UNIQUE

Why is a UNIQUE index restricted to `region='north'` insufficient for concurrent refresh?

### Exercise 13. Expression UNIQUE

Does a UNIQUE index on `lower(region)` satisfy concurrent refresh requirements?

### Exercise 14. Read Locks

How does `SELECT` availability differ between standard refresh and concurrent refresh?

### Exercise 15. Not Incremental

Why does `REFRESH ... CONCURRENTLY` not mean "process only new orders since last run"?

### Exercise 16. Schedule-Based Freshness

A refresh job runs every 5 minutes, takes 2 minutes, and occasionally fails. Can you guarantee at most 5 minutes of staleness?

### Exercise 17. Final State

A user sees "updated 10:05" yet a transaction committed at 10:04 is missing. Can this happen?

### Exercise 18. Refresh Log

Create a log table recording MV name, finish time, and refresh mode.

### Exercise 19. Measuring Log Age

Write a query returning the latest successful refresh and seconds elapsed since then.

### Exercise 20. Source Watermark

Why is `MAX(orders.created_at)` unreliable for proving all source changes are reflected in the MV?

### Exercise 21. EXPLAIN

Write two `EXPLAIN (ANALYZE, BUFFERS)` statements comparing SELECT on the regular view vs. the MV.

### Exercise 22. Indexes for Read Queries

Design an index for queries filtering `region='north'` and `ORDER BY report_date DESC`.

### Exercise 23. ANALYZE

Write SQL to update statistics on the materialized view; does it refresh revenue?

### Exercise 24. Size

Write a query measuring heap, index, and total size of the MV.

### Exercise 25. UPDATE/DELETE

Why does a strategy that only adds revenue from new INSERTs break after refunds or cancellations?

### Exercise 26. Full Recomputation

If an MV has 12 rows while the source has 200 million orders, why can a refresh still take a long time?

### Exercise 27. Read Replicas

If an app reads from a lagging read replica, why can the MV still look stale even right after the primary refreshes?

### Exercise 28. Choosing an Architecture

An executive dashboard tolerates 10-minute lag; an inventory reservation API tolerates zero lag. Choose the read mechanism for each and explain.

### Exercise 29. Multi-Table Sources

Can revenue by `customers.region` change due to updates on `customers`? Is watching only new orders sufficient?

### Exercise 30. Hybrid Pitfalls

What happens if an MV already includes today's orders and a dashboard adds a live aggregate also covering all of today?

### Exercise 31. Wrong Index Type

Is `CREATE INDEX ON mv_daily_paid(report_date)` sufficient for `CONCURRENTLY`? Why or why not?

### Exercise 32. Concurrency

A scheduler triggers jobs every 5 minutes while each run takes 9 minutes. Propose an overlap-prevention policy.

### Exercise 33. New Version Rollout

Describe the rollout sequence for MV v2 when changing the aggregate formula while dashboards still read MV v1.

### Exercise 34. Access Privileges

Why shouldn't you grant broad SELECT on an MV holding sensitive aggregates merely because source tables have RLS?

### Exercise 35. Refresh Failures

If a refresh fails, should the "last successful refresh" timestamp update? What should the dashboard show?

### Exercise 36. SLA Design

Propose the minimum metrics needed to claim a report meets a 15-minute freshness SLO.

## 43. Suggested Solutions

### Exercises 1–3. Core Differences

Regular views run the source query against a current snapshot; materialized views read persisted results that update only on refresh. A result matching an earlier snapshot is **stale**, not automatically inconsistent.

### Exercise 4. Source VIEW

~~~sql
CREATE VIEW mv_lab.v_daily_paid_answer AS
SELECT
    (o.created_at AT TIME ZONE 'UTC')::date AS report_date,
    c.region,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS revenue
FROM mv_lab.orders AS o
JOIN mv_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'paid'
GROUP BY
    (o.created_at AT TIME ZONE 'UTC')::date,
    c.region;
~~~

### Exercise 5. Creating MV WITH DATA

~~~sql
CREATE MATERIALIZED VIEW mv_lab.mv_daily_paid_answer AS
SELECT *
FROM mv_lab.v_daily_paid
WITH DATA;
~~~

`WITH DATA` runs the source query immediately upon creation.

### Exercises 6–7. Before/After Refresh

With initial data, north on Jan 10 totals 170.00. After inserting a 30.00 paid order before refresh: the regular view shows 200.00, while the MV still shows 170.00.

~~~sql
REFRESH MATERIALIZED VIEW mv_lab.mv_daily_paid;
~~~

After refresh completes with no further source changes, the MV reaches 200.00.

### Exercise 8. WITH NO DATA

`WITH NO DATA` leaves the MV unpopulated, blocking SELECTs unlike a normal empty table.

~~~sql
REFRESH MATERIALIZED VIEW
    mv_lab.mv_daily_paid_unpopulated;
~~~

Do not use `CONCURRENTLY` on initial population.

### Exercise 9. pg_matviews

~~~sql
SELECT
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_lab';
~~~

### Exercises 10–13. CONCURRENTLY and UNIQUE

The MV must be **populated**, have at least one **column-only**, **non-partial** UNIQUE index covering all rows.

~~~sql
CREATE UNIQUE INDEX uq_mv_daily_paid_answer
ON mv_lab.mv_daily_paid (report_date, region);
~~~

*Note:* The lab already created an equivalent index `uq_mv_daily_paid_date_region`, so do not add a duplicate second index. Partial UNIQUE or expression UNIQUE indexes do not qualify for concurrent refresh.

### Exercises 14–15. Locking and Full Recomputation

Standard refresh blocks SELECTs; concurrent refresh lets SELECTs continue during the update with added diffing cost. Both re-run the defining query; `CONCURRENTLY` is not automatic WAL-based incremental maintenance.

### Exercises 16–17. Timing

A 5-minute schedule cannot guarantee 5-minute max lag if runs take 2 minutes or fail. A 10:04 commit will miss a snapshot captured at 10:03 even if the refresh finishes and logs at 10:05.

### Exercise 18. Log Table

~~~sql
CREATE TABLE mv_lab.refresh_log_answer (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    matview_name text NOT NULL,
    finished_at timestamptz NOT NULL
        DEFAULT clock_timestamp(),
    refresh_mode text NOT NULL
);
~~~

### Exercise 19. Refresh Age

~~~sql
SELECT
    MAX(finished_at) AS last_success,
    EXTRACT(
        EPOCH FROM (
            clock_timestamp() - MAX(finished_at)
        )
    ) AS age_seconds
FROM mv_lab.refresh_log
WHERE matview_name = 'mv_lab.mv_daily_paid';
~~~

### Exercise 20. Watermark

`MAX(created_at)` misses status changes on older orders, DELETEs, customer region edits, and late-committed transactions with older business timestamps. It does not prove all changes were processed.

### Exercise 21. EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM mv_lab.v_daily_paid
WHERE report_date >= DATE '2026-01-01';

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM mv_lab.mv_daily_paid
WHERE report_date >= DATE '2026-01-01';
~~~

Inspect scan types, JOIN/Aggregate/Sort nodes, `actual rows`, `Buffers`, and `Execution Time`; never draw speedup conclusions from tiny lab tables.

### Exercises 22–23. Read Index and ANALYZE

~~~sql
CREATE INDEX idx_mv_region_date_answer
ON mv_lab.mv_daily_paid (region, report_date DESC);

ANALYZE mv_lab.mv_daily_paid;
~~~

`ANALYZE` updates statistics; **it does not refresh revenue**.

### Exercise 24. Storage

~~~sql
SELECT
    pg_relation_size(
        'mv_lab.mv_daily_paid'::regclass
    ) AS heap_bytes,
    pg_indexes_size(
        'mv_lab.mv_daily_paid'::regclass
    ) AS index_bytes,
    pg_total_relation_size(
        'mv_lab.mv_daily_paid'::regclass
    ) AS total_bytes;
~~~

### Exercises 25–26. Costs

Refunds and cancellations decrease `SUM`/`COUNT`, shift groups, or delete groups; adding only new orders yields wrong totals. Even a 12-row MV can incur heavy CPU/I/O if its source query aggregates 200 million orders.

### Exercise 27. Replica Lag

The replica may not yet have received/replayed WAL containing the primary's refresh commit, leaving apps reading stale MV data. Measure replication lag and confirm read routing.

### Exercise 28. Architecture

A dashboard tolerating 10-minute lag can read a periodically refreshed MV with a freshness label. An inventory reservation API needs transactional consistency, never relying solely on a potentially stale MV.

### Exercises 29–30. Multi-Table Edits and Hybrid

Updating a customer's region shifts historical order revenue between regions; tracking only new orders misses this. Adding live aggregates overlapping the MV's window double-counts; you need a verified cutoff watermark and late-change handling.

### Exercise 31. Non-Unique Index

A regular index on `report_date` does not enable concurrent refresh. You need a full-coverage, non-partial, column-only UNIQUE index.

### Exercise 32. Scheduler

Use a single worker/queue per MV that skips or coalesces triggers if a prior run is still active, plus lag alerts. Never let a 5-minute cron pile up infinite waiting refreshes.

### Exercise 33. Cutover

Create MV v2, populate it, build indexes (including UNIQUE for concurrent refresh), verify output and grants, then migrate dashboards/apps to v2. Keep v1 until rollback is no longer needed; drop only once zero dependencies remain.

### Exercise 34. Security

An MV stores a physical copy with its own SELECT grants. Source RLS does not guarantee MV readers see row-filtered output; design grants, scope, and materialized columns explicitly.

### Exercise 35. Failures

Never advance the success timestamp on failure. Display the last successful refresh timestamp, data age, and a "stale/degraded" banner; depending on SLA, fall back or disable sensitive actions.

### Exercise 36. Freshness SLO

Track at minimum: scheduled/start/end timestamps, p95/p99 duration, success rate, lock wait time, scheduler delay, source snapshot/watermark if applicable, commit-to-visibility lag of source edits, and displayed data age. "Last refresh time" alone is necessary but insufficient to prove all edits landed.

## 44. Quick Reference Table

| Need | Syntax or Principle |
| --- | --- |
| View always reading live source | `CREATE VIEW ... AS SELECT ...` |
| Persist query results | `CREATE MATERIALIZED VIEW ... AS SELECT ... WITH DATA` |
| Create unpopulated MV | `CREATE MATERIALIZED VIEW ... WITH NO DATA` |
| Initial population | `REFRESH MATERIALIZED VIEW mv_name` |
| Standard refresh | `REFRESH MATERIALIZED VIEW mv_name` |
| Refresh minimizing SELECT blocking | `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_name` |
| Concurrent prerequisites | Populated MV + qualifying UNIQUE index |
| Qualifying UNIQUE index | `CREATE UNIQUE INDEX ... ON mv(cols...)`, non-expression, non-partial |
| Discard data / unpopulate | `REFRESH MATERIALIZED VIEW mv_name WITH NO DATA` |
| Check populated state | `pg_matviews.ispopulated` |
| Check index presence | `pg_matviews.hasindexes` |
| Ordered MV reads | `SELECT ... FROM mv ORDER BY ...` |
| Measure SELECT plan | `EXPLAIN (ANALYZE, BUFFERS)` |
| Update statistics | `ANALYZE mv_name` |
| Measure physical size | `pg_relation_size`, `pg_indexes_size` |
| Record successful refreshes | Log table or scheduler/observability |
| Refresh age | `clock_timestamp() - MAX(finished_at)` |
| Source watermark | Change tracking/CDC design, not merely `MAX(created_at)` |
| Prevent job overlaps | Queue/lock coordination, bounded retries and timeouts |
| Reports needing immediate freshness | Query source or synchronous read model |
| Delta updates | Incremental summary table / custom pipeline |
| Change MV definition | Migration / versioned cutover; REFRESH does not alter query |

## 45. Pre-Deployment Checklist

1. **Is the source query business-accurate?** Verified JOIN cardinality and aggregations?
2. **How much staleness can the report tolerate?** Do consumers see clear refresh labels?
3. **Has p95/p99 refresh duration** been measured at production-like scale?
4. **Can standard refresh block SELECTs?** If unacceptable, are `CONCURRENTLY` prerequisites met?
5. **Is the UNIQUE index column-only, non-partial, non-expression, covering all rows?**
6. **Is the MV populated?** Avoid routing traffic before initial population finishes.
7. **Do read queries have needed indexes?** Avoid redundant indexes adding storage/refresh cost.
8. **Do source tables have indexes/partitioning supporting the refresh query?**
9. **Are CPU, I/O, WAL, temp files, and replica lag measured?**
10. **Does the scheduler enforce overlap protection**, timeouts, backoff, and bounded retries?
11. **Is `last_successful_refresh` logged reliably?** Are missing logs handled?
12. **Is a source watermark tracked if required by the SLO?**
13. **Are overdue-freshness alerts configured?**
14. **Is a fallback/degraded-mode policy defined if refreshes fail?**
15. **Can changes in joined dimension tables alter results?**
16. **Can historical records receive UPDATEs/DELETEs or late-arriving events?**
17. **If hybrid, does the cutoff prevent double-counting or gaps?**
18. **Are MV SELECT grants aligned with data security policies?**
19. **Do copies, caches, or read replicas have separate freshness SLAs?**
20. **Do schema migrations include an MV rebuild/cutover plan?**
21. **Are `ANALYZE` stats maintained after major refreshes?**
22. **Do consumer queries include explicit `ORDER BY`?**
23. **Are both read latency and refresh overhead measured, not just one side?**
24. **Is the MV periodically re-evaluated against regular views or summary tables?**

## 46. Summary

**A materialized view is an intentional trade-off between query speed and data freshness.** It stores the output of a SELECT query so repeated reads avoid recomputing expensive JOINs and aggregations over source tables. That makes it ideal for read-heavy, computationally expensive dashboards and reports that **tolerate stale data**.

Key principles:

1. **Regular VIEWs** read source tables under the query's current snapshot; **MATERIALIZED VIEWs** read stored results from the last refresh.
2. `REFRESH MATERIALIZED VIEW` must be invoked explicitly or scheduled; core PostgreSQL **does not incrementally update MVs on every INSERT/UPDATE/DELETE**.
3. `REFRESH MATERIALIZED VIEW CONCURRENTLY` avoids blocking concurrent SELECTs, but requires a **populated MV and a full-coverage column-only UNIQUE index**, and still incurs heavy work when source queries are expensive.
4. **Consistent yet stale data** can still drive wrong decisions. Refresh completion timestamps and source snapshot/watermark boundaries are not always identical.
5. Production reliability requires **refresh schedules, monitoring, alerting, bounded retries, overlap control, degraded-mode policies, and privilege governance**.
6. When near-real-time freshness or complex delta updates are needed, consider **incremental summary tables**, direct source queries, caches with invalidation, or specialized pipelines instead of endlessly refreshing full history.

Before choosing a materialized view, answer three questions: **"How expensive is one SELECT from source?", "How stale can displayed numbers be?", and "Will refreshes overload the system or block readers?"** Balancing all three turns materialized views into a reliable PostgreSQL building block rather than a fast copy whose age nobody knows.
