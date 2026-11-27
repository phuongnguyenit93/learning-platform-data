# Choosing a View, Materialized View, or Summary Table in PostgreSQL

Suppose an order management application needs to provide a report of **paid revenue by day and by tenant**. There are three common design approaches:

1. Create a **view** containing the aggregation SQL query. Each time the report is read, PostgreSQL executes the query against the source data according to its planning mechanism and current snapshot.
2. Create a **materialized view** that persists the result. Report queries read the precomputed data, but the result **does not change automatically** when source orders are inserted or updated; `REFRESH MATERIALIZED VIEW` is required.
3. Create a **summary table** (*summary/aggregate table*) keyed by day and tenant. A job, transaction, trigger, or event pipeline proactively updates each aggregate group; in return, the system itself must guarantee correctness, synchronization, and recoverability.

All three options can return the exact same columns:

```text
tenant_id | sales_day  | paid_orders | gross_amount
----------+------------+-------------+-------------
        1 | 2026-11-01 |           2 |       200.00
        1 | 2026-11-02 |           1 |        50.00
        2 | 2026-11-01 |           1 |        90.00
```

However, they **do not share the same operational contract**.

```text
                       orders (source table)
                               |
                +--------------+--------------+
                |              |              |
                v              v              v
           SQL VIEW      MATERIALIZED VIEW  SUMMARY TABLE
                |              |              |
         Computed at     Computed at        Computed via events/
            read           REFRESH          jobs/transactions
                |              |              |
                v              v              v
         Result per      Stored snapshot    Metrics maintained
         query snapshot   may become stale   by your pipeline
                |              |              |
                +--------------+--------------+
                               |
                        API / Dashboard
```

This lesson belongs to the **View** chapter in the *Database Engine Relational PostgreSQL* module. The goal is not merely memorizing `CREATE VIEW` and `CREATE MATERIALIZED VIEW` syntax, but **choosing the right architecture** for data volume, freshness requirements, operational cost, and business correctness.

After this lesson, you will be able to:

- Distinguish where execution happens and where data is stored for a view, materialized view, and summary table.
- Properly design the **grain** (*level of granularity*) of a per-tenant/per-day report.
- Use the same dataset to build all three forms and demonstrate their differences after INSERT/UPDATE.
- Understand `REFRESH MATERIALIZED VIEW`, `CONCURRENTLY`, unique index requirements, and the limits of full refreshes.
- Design a summary table with a `PRIMARY KEY`, `INSERT ... ON CONFLICT DO UPDATE`, and duplicate-addition prevention mechanisms.
- Handle late-arriving data, refunds, date/tenant edits, deletions, and backfills.
- Set measurable freshness targets and know when an architectural transition is needed.
- Evaluate query plans, indexes, storage, locks, write amplification, permissions/RLS, and maintenance overhead.

> **Safety:** All hands-on examples use a dedicated `view_choice_lab` schema in a test database. Do not recreate or drop a schema containing someone else's data. The `REFRESH` and `UPDATE` commands in this lesson genuinely modify data/relations; execute them in a lab environment. Running `EXPLAIN (ANALYZE)` on DML also **executes real DML**.

---

## 1. Understanding the Three Concepts Correctly

### 1.1. Regular View: A Query Definition, Not a Stored Copy of Data

```sql
CREATE VIEW reporting.v_daily_sales AS
SELECT ...
FROM orders
GROUP BY ...;
```

A regular view stores an **SQL definition**. When a user runs a SELECT from the view, PostgreSQL processes the query referencing the underlying source tables and produces the corresponding execution plan.

A view **does not cache results by default**:

```sql
SELECT *
FROM reporting.v_daily_sales;
```

If `orders` just had a committed transaction modifying its data, a new query with a newer snapshot can see that change.

**Key takeaway:** A view is a logical abstraction layer, **not a "pre-executed SELECT table"**.

### 1.2. Materialized View: Query Results Stored as Data

```sql
CREATE MATERIALIZED VIEW reporting.mv_daily_sales AS
SELECT ...
FROM orders
GROUP BY ...;
```

PostgreSQL creates a relation storing the result at creation/refresh time. When querying a materialized view, the system reads **already materialized** data instead of recomputing the full GROUP BY over the source table on every SELECT.

In return:

```text
INSERT INTO orders ... COMMIT
           |
           +--> VIEW: new query can see it immediately
           |
           +--> MATERIALIZED VIEW: still holds old results
                        |
                   REFRESH
                        |
                        v
                   new results
```

A materialized view **does not auto-refresh** when source tables change. Core PostgreSQL also does not provide a general **incremental materialized view maintenance** mechanism by default for arbitrary SELECT definitions.

### 1.3. Summary Table: A Real Table with Its Own Aggregation Pipeline

```sql
CREATE TABLE reporting.daily_sales_summary (
    tenant_id INTEGER NOT NULL,
    sales_day DATE NOT NULL,
    paid_orders BIGINT NOT NULL,
    gross_amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (tenant_id, sales_day)
);
```

This is a **regular table**. PostgreSQL has no idea that the columns inside it are supposed to always equal the GROUP BY result from `orders`; the application or pipeline must enforce that.

Benefits:

- Small deltas can be applied without recomputing full history every time.
- Additional watermarks, revisions, control states, and metadata can be stored.
- Certain aggregate groups can be updated within the exact same transaction as the source data.
- Low-latency reporting can be served with clear primary keys and indexes.

Costs:

- Logic for **creation, updates, reversals, and duplicate-addition prevention** must be engineered by you.
- A buggy pipeline can corrupt metrics without PostgreSQL noticing on its own.
- Periodic reconciliation against the source of truth is required.

### 1.4. A Quick Comparison Table

| Criterion | View | Materialized view | Summary table |
|---|---|---|---|
| Stores separate aggregated results? | No | Yes | Yes |
| Sees source changes automatically on new queries? | Per snapshot/MVCC | No, requires `REFRESH` | Only when the pipeline updates it |
| Report SELECT cost | Potentially high | Usually low after refresh | Usually low with proper grain/indexes |
| Cost to update report data | No result maintenance needed | Periodic refresh, usually full recomputation | Per delta/batch or rebuild |
| Ability to index aggregated results | Cannot index directly on a view | Can create indexes | Can create indexes |
| Synchronization logic to write yourself | No | Refresh schedule, failure monitoring | Yes, usually the most complex |
| Staleness control | Per snapshot, replica/cache | Per last refresh | Per pipeline/watermark |
| Direct UPDATE support | Some simple views | Not usable like a normal DML table | Yes |
| Best suited for | Moderate data, non-expensive queries, fresh reads | High repeat reads, staleness tolerated | Large reports, continuous writes, tight freshness SLAs |

There is no single "fastest" option for all cases. **Report grain, read frequency, write rate, and acceptable staleness** are what dictate the choice.

---

## 2. Sample Problem: Paid Revenue by UTC Day

Let us establish the business definition before writing SQL:

- Each source row is **one order**.
- `status='paid'` counts toward revenue; `cancelled` and `refunded` do not count.
- `amount` is monetary value **in a single unified currency** in the lab. In multi-currency production systems, **never sum mixed currencies together**; add `currency` to the grain or convert according to controlled rules.
- A reporting day is computed in **UTC**, independent of the session's `TimeZone`.
- Each result row represents **one tenant on one UTC day**.
- `paid_orders` is the number of paid orders; `gross_amount` is the sum of `amount` for paid orders.

If the business allows partial refunds, split payments, or order line items, this simplified model must be extended. Do not equate `status='paid'` with a complete financial revenue recognition model.

### 2.1. What Is Grain?

**Grain** answers: "What does one row in the report represent?"

```text
Source order grain:
    1 row = 1 order_id

Report grain:
    1 row = (tenant_id, sales_day UTC)
```

The grain determines the unique key of both the materialized view and the summary table:

```sql
(tenant_id, sales_day)
```

If you add `currency`, `region`, or `product_category` to the report, you must revisit the grain and corresponding key; do not add columns to GROUP BY while forgetting to update the unique index/PRIMARY KEY.

### 2.2. Why Use an Explicit UTC Range?

`ordered_at` will be `TIMESTAMPTZ`. We define the UTC day as:

```sql
(ordered_at AT TIME ZONE 'UTC')::date
```

`AT TIME ZONE 'UTC'` produces a UTC wall-clock timestamp before extracting the `date`. This differs from `ordered_at::date`, which can depend on the session's `TimeZone`.

If the requirement is **days in Vietnam time**, replace the rule with `Asia/Ho_Chi_Minh` across **all** views, materialized views, summary tables, and delta pipelines. Never have a view computing UTC days while the summary table uses session-local days.

---

## 3. Creating the Lab Environment

### 3.1. Check the Database

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Do not create sample data in a production schema. This example assumes the `view_choice_lab` schema does not yet exist.

### 3.2. Create the Source Table

```sql
CREATE SCHEMA view_choice_lab;

CREATE TABLE view_choice_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('paid', 'cancelled', 'refunded')),
    amount NUMERIC(12,2) NOT NULL
        CHECK (amount >= 0)
);
```

Example limitations:

- No separate payment/refund table.
- No currency column because the lab assumes a single unified currency.
- `order_id` is an identity column; IDs are assigned at INSERT time and should not be treated as a chronological key.
- Order transactions must obey all constraints.

### 3.3. Load Six Deterministic Orders

```sql
INSERT INTO view_choice_lab.orders
    (tenant_id, ordered_at, status, amount)
VALUES
    (1, '2026-11-01 02:00:00+00', 'paid',      120.00),
    (1, '2026-11-01 03:00:00+00', 'paid',       80.00),
    (1, '2026-11-02 08:00:00+00', 'paid',       50.00),
    (1, '2026-11-01 10:00:00+00', 'cancelled',  20.00),
    (2, '2026-11-01 12:00:00+00', 'paid',       90.00),
    (2, '2026-11-02 15:00:00+00', 'refunded',   40.00);
```

### 3.4. Verify the Data

```sql
SELECT
    order_id,
    tenant_id,
    ordered_at,
    status,
    amount
FROM view_choice_lab.orders
ORDER BY order_id;
```

With a fresh schema and a single INSERT in the order above, identity typically assigns `order_id` 1 through 6. Do not rely on hardcoded IDs if re-running the lab on existing data.

### 3.5. Expected Report Output

| tenant_id | sales_day | paid_orders | gross_amount |
|---:|---|---:|---:|
| 1 | 2026-11-01 | 2 | 200.00 |
| 1 | 2026-11-02 | 1 | 50.00 |
| 2 | 2026-11-01 | 1 | 90.00 |

The cancelled 20.00 order and refunded 40.00 order are excluded. Tenant 2 on 2026-11-02 has no paid orders, so it **produces no row** in this GROUP BY result. This is an important convention when comparing against a summary table that might retain zeroed rows.

---

## 4. Option A — VIEW: Always Computed from Source on Query

### 4.1. Create the Reporting View

```sql
CREATE VIEW view_choice_lab.v_daily_sales AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status = 'paid'
GROUP BY
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date;
```

We do not create a result data table: we only create an SQL definition.

### 4.2. Query the View

```sql
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.v_daily_sales
ORDER BY tenant_id, sales_day;
```

The output matches the table in section 3.

### 4.3. What Does PostgreSQL Do on Read?

The view is expanded through PostgreSQL's query processing mechanism. The planner can:

- Scan the `orders` table.
- Use an appropriate index if predicates and statistics permit.
- Apply `WHERE status='paid'`.
- Compute the UTC day from `ordered_at`.
- Aggregate groups via `HashAggregate` or `GroupAggregate`.
- Apply outer-query predicates/ordering according to the resulting plan.

There is no separate physical table named `v_daily_sales` holding three rows that need maintenance.

### 4.4. Reading a View and "Latest" Data Under MVCC

A new SELECT under `READ COMMITTED` isolation typically uses the latest statement snapshot, seeing source transactions committed prior to that snapshot. However:

- A `REPEATABLE READ` transaction can continue seeing an older snapshot within the same transaction.
- Reads from a read replica may experience replication lag.
- The application may cache responses.
- Uncommitted writes do not appear.

Therefore, saying "a VIEW is always strictly real-time" is inaccurate. More accurately: **a view does not maintain a separate stale aggregate copy; data read obeys database snapshot rules**.

### 4.5. When Is a View Usually Appropriate?

- Source tables are not overly large yet, or the GROUP BY query is already fast enough.
- Reports have many flexible filter combinations that are impractical to materialize across all permutations.
- Results must reflect source state as of the latest snapshot.
- You want centralized SQL logic in the database.
- You do not want to operate a refresh scheduler or delta pipeline.
- Read frequency is low or moderate relative to data volume.

### 4.6. A View Does Not Make Queries Cheaper by Itself

If a report scans 300 million orders and runs GROUP BY every 2 seconds, creating a view **does not eliminate the GROUP BY work**. It only enables SQL reuse and simplifies permissions/interfaces.

Do not treat a view as a "free cache".

---

## 5. Option B — MATERIALIZED VIEW: Persisting a Snapshot of Results

### 5.1. Create the Materialized View

```sql
CREATE MATERIALIZED VIEW view_choice_lab.mv_daily_sales AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status = 'paid'
GROUP BY
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date
WITH DATA;
```

`WITH DATA` instructs PostgreSQL to execute the query and store the initial result. This is also the default behavior in standard materialized view creation syntax, but writing it explicitly helps learners see the contrast with `WITH NO DATA`.

### 5.2. Read the Persisted Results

```sql
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.mv_daily_sales
ORDER BY tenant_id, sales_day;
```

At this point, the materialized view has the exact same three rows as the regular view, but **those rows are physically stored**.

### 5.3. Materialized Views Can Have Indexes

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales (tenant_id, sales_day);
```

This unique index fits because the result is grouped by `(tenant_id, sales_day)`, with at most one row per pair.

Benefits:

- Queries filtering `WHERE tenant_id=... AND sales_day=...` can perform targeted lookups.
- The index covers **all rows** and uses **plain column names only**.
- It satisfies the key requirement for `REFRESH MATERIALIZED VIEW CONCURRENTLY` (once populated).

You do not rely on the same index on source `orders` to make matview queries fast; the source table and the matview are **two distinct relations** with separate storage and indexes.

### 5.4. A Materialized View Cannot Be Updated Like a Summary Table

Do not run:

```sql
-- Standard DML operations are not supported on a matview:
-- UPDATE view_choice_lab.mv_daily_sales
-- SET gross_amount = 100
-- WHERE tenant_id = 1;
```

To change the result, update the **source table** and then run `REFRESH MATERIALIZED VIEW`. A materialized view is not an arbitrary table where you UPSERT individual rows like a summary table.

### 5.5. Lifecycle of a Matview

```text
CREATE MATERIALIZED VIEW ... WITH DATA
       |
       v
Results stored as of creation time
       |
       v
Source changes; matview retains old values
       |
       v
REFRESH MATERIALIZED VIEW
       |
       v
Results recomputed as of refresh snapshot
       |
       v
Subsequent SELECTs see new data once refresh commits
```

---

## 6. Option C — Summary Table: Self-Maintained by Grain

### 6.1. Create the Summary Table

```sql
CREATE TABLE view_choice_lab.daily_sales_summary (
    tenant_id INTEGER NOT NULL,
    sales_day DATE NOT NULL,
    paid_orders BIGINT NOT NULL DEFAULT 0
        CHECK (paid_orders >= 0),
    gross_amount NUMERIC(18,2) NOT NULL DEFAULT 0
        CHECK (gross_amount >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, sales_day)
);
```

The `updated_at` column here indicates **the last time a group was updated**, not an automatic watermark proving the entire source has synchronized up to a given timestamp.

### 6.2. Bootstrap from the Canonical Query

```sql
INSERT INTO view_choice_lab.daily_sales_summary
    (tenant_id, sales_day, paid_orders, gross_amount)
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.v_daily_sales;
```

Now the view, materialized view, and summary table all hold the same three rows.

### 6.3. Read the Summary Table

```sql
SELECT
    tenant_id,
    sales_day,
    paid_orders,
    gross_amount
FROM view_choice_lab.daily_sales_summary
ORDER BY tenant_id, sales_day;
```

The query reads a table that already contains the metrics; no GROUP BY over `orders` is needed at SELECT time.

### 6.4. No Automatic Synchronization

Creating the table above does not tell PostgreSQL:

```text
orders INSERT/UPDATE/DELETE
   -> must UPDATE daily_sales_summary
```

Without a job, trigger, or pipeline, the summary table becomes **stale** the moment the source changes. Unlike a materialized view with a built-in `REFRESH` definition, a summary table requires **maintenance logic designed by you**.

### 6.5. Summary Tables Need Constraints

`PRIMARY KEY (tenant_id,sales_day)` prevents two rows for the same group. `CHECK` prevents negative `paid_orders` or `gross_amount` in this simplified revenue model.

However, constraints **do not guarantee** that accumulated values actually equal the `orders` table. Drift (for example, 220 instead of 230) can still satisfy every constraint.

---

## 7. Experimenting with Differences After Source Changes

At this point, all three options have been built from the same six-order dataset.

### 7.1. Add One Paid Order

```sql
INSERT INTO view_choice_lab.orders
    (tenant_id, ordered_at, status, amount)
VALUES
    (1, '2026-11-01 17:00:00+00', 'paid', 30.00);
```

This is the seventh order if loaded only once. It increases paid orders for tenant 1 on 2026-11-01 from **2 to 3**, and revenue from **200.00 to 230.00**.

### 7.2. Read the VIEW Immediately After the Committed INSERT

```sql
SELECT paid_orders, gross_amount
FROM view_choice_lab.v_daily_sales
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

In a new statement seeing the commit, the result is:

```text
paid_orders | gross_amount
------------+-------------
          3 |      230.00
```

### 7.3. Read the MATERIALIZED VIEW Before REFRESH

```sql
SELECT paid_orders, gross_amount
FROM view_choice_lab.mv_daily_sales
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

It is still:

```text
paid_orders | gross_amount
------------+-------------
          2 |      200.00
```

No trigger automatically refreshes the materialized view when `orders` receives a new row.

### 7.4. Read the Summary Table Before the Pipeline Runs

```sql
SELECT paid_orders, gross_amount
FROM view_choice_lab.daily_sales_summary
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

It is still **2 / 200.00** because no summary-update code has run yet. This is not a PostgreSQL bug; it is the nature of a regular table that is not automatically linked to the source.

### 7.5. State After One INSERT

| Read source | paid_orders | gross_amount | Reason |
|---|---:|---:|---|
| `v_daily_sales` | 3 | 230.00 | Computed against new source snapshot |
| `mv_daily_sales` | 2 | 200.00 | Not yet refreshed |
| `daily_sales_summary` | 2 | 200.00 | Delta not yet processed |

This is the most important experiment for understanding why **you cannot choose an architecture solely by looking at SELECT speed**.

---

## 8. REFRESH MATERIALIZED VIEW and Data Freshness

### 8.1. Standard REFRESH

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales;
```

PostgreSQL re-executes the materialized view's defining query and replaces the materialized contents. After the refresh finishes and commits, a new SELECT can see:

```text
tenant 1 / 2026-11-01 -> 3 orders, 230.00
```

### 8.2. REFRESH Is Usually Not Incremental

Even when only a single new order was added, standard core PostgreSQL **does not automatically figure out how to update just one tenant/day group** with a `+30` delta. It re-executes the matview's defining query to rebuild the new result.

For example:

```text
Source: 250 million orders
Change: 1 new order
REFRESH: may still have to read/aggregate a massive amount of source data
```

Cost depends on the SQL, indexes, scans, joins, aggregates, and dataset size; never assume refresh is a quick metadata-only update.

### 8.3. Standard REFRESH Affects Readers

`REFRESH MATERIALIZED VIEW` without `CONCURRENTLY` can acquire a strong lock on the matview, blocking other SELECTs for the duration of execution. On heavily read dashboards, measure refresh duration and lock contention before scheduling.

### 8.4. REFRESH CONCURRENTLY

Because we already created a unique index on `(tenant_id,sales_day)` and the materialized view is currently populated, we can test:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    view_choice_lab.mv_daily_sales;
```

`CONCURRENTLY` is designed to avoid blocking concurrent SELECTs on the matview during refresh, but **it does not mean refresh is free** or lockless.

### 8.5. Mandatory Requirements for CONCURRENTLY

According to PostgreSQL rules, the materialized view must:

- **Be populated**: not in an unpopulated state from `WITH NO DATA`.
- Have at least **one UNIQUE index** on the matview.
- That unique index must reference **column names only**, not an expression index.
- That unique index must **cover all rows**, without a `WHERE` predicate (not a partial unique index).

Valid example in the lab:

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales
    (tenant_id, sales_day);
```

This index was already created in section 5, so this is an **illustrative definition**, not a command to re-run with the same name.

Examples that do not meet the requirements:

```sql
-- Partial UNIQUE: does not qualify for REFRESH CONCURRENTLY.
-- CREATE UNIQUE INDEX bad_partial_uidx
-- ON view_choice_lab.mv_daily_sales (tenant_id, sales_day)
-- WHERE paid_orders > 0;

-- UNIQUE expression index: does not satisfy the corresponding requirement.
-- CREATE UNIQUE INDEX bad_expression_uidx
-- ON view_choice_lab.mv_daily_sales
--     ((tenant_id::text), sales_day);
```

### 8.6. CONCURRENTLY Does Not Mean Computing Deltas from Source

This is a common misconception:

```text
REFRESH MATERIALIZED VIEW CONCURRENTLY
             ≠
Refresh only rows that just changed in orders
```

`CONCURRENTLY` primarily governs **how the materialized view's contents are swapped and how it interacts with readers**. The defining query still must be re-executed; core PostgreSQL does not provide incremental refresh for GROUP BY out of the box.

In some workloads, `CONCURRENTLY` actually **consumes more resources or runs longer** than a standard REFRESH because it must diff and apply row changes.

### 8.7. Only One Refresh per Matview at a Time

PostgreSQL does not allow arbitrary concurrent refreshes against the same materialized view simultaneously. The scheduler must **coordinate one refresh job per matview** and handle overdue runs.

Do not configure a cron job every minute when each refresh takes ten minutes, causing a pile-up of overlapping jobs without coordination.

### 8.8. Readers Can See the Prior Version Until Refresh Commits

While a concurrent refresh is running, readers can usually keep SELECTing from the matview and see the **previously committed snapshot**; once the refresh commits, statements using newer snapshots see the new result.

That helps availability, but it does not eliminate **freshness SLA** requirements.

---

## 9. WITH NO DATA and the First Refresh

### 9.1. Creating a Matview Unpopulated

```sql
-- Standalone example; do not re-run over the existing mv_daily_sales.
CREATE MATERIALIZED VIEW view_choice_lab.mv_daily_sales_empty AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status = 'paid'
GROUP BY tenant_id, (ordered_at AT TIME ZONE 'UTC')::date
WITH NO DATA;
```

`WITH NO DATA` creates the relation definition while **not yet materializing results**. Do not confuse this with a populated table whose valid query result happens to be empty.

### 9.2. Do Not SELECT It Like a Populated Matview

An unpopulated matview is marked **unscannable**; SELECTing from it raises an error asking to populate it first. Do not assume it returns `COUNT(*) = 0`.

### 9.3. First REFRESH

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales_empty;
```

After succeeding, the matview is populated and queryable.

`REFRESH ... CONCURRENTLY` **is not an option for the initial load when a matview is unpopulated**. To use concurrent refresh later, create a qualifying unique index first.

### 9.4. Do Not Combine CONCURRENTLY with WITH NO DATA

Do not write:

```sql
-- Invalid:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     view_choice_lab.mv_daily_sales_empty
-- WITH NO DATA;
```

The two options cannot be combined. `WITH NO DATA` also leaves the materialized view unavailable for normal reading until a refresh with data runs.

---

## 10. When Is a Materialized View Truly Advantageous?

### 10.1. Expensive Report, Heavily Read, Slowly Changing Source

For example:

```text
Source table: 40 million transactions
Report query: GROUP BY day/tenant, multi-table JOIN
Read rate: 300 reads/minute
Freshness SLA: max 15 minutes
Change rate: a few thousand transactions per minute
```

If a REFRESH completes within a reasonable duration without causing excessive load spikes, a matview can eliminate the repeated computation of hundreds of SELECTs.

### 10.2. Grouped Result Has a Small Row Count

The source has 40 million orders, yet the materialized view holds only a few thousand `(tenant,day)` groups. An index on the grouped result lets dashboards perform narrow lookups.

### 10.3. No Need for Event-by-Event Delta Computation

When staleness up to 15 minutes is acceptable, operating a refresh schedule can be far simpler than building an event pipeline with exactly-once effects and historical reversals.

### 10.4. What If Refresh Takes 45 Minutes?

A 15-minute refresh schedule **cannot meet the SLA** if every refresh takes 45 minutes and waits on locks/CPU. You need to:

- Reduce source query cost, adding indexes or partition pruning where appropriate.
- Adjust the materialized grain or volume of data materialized.
- Split out particularly heavy reports.
- Move to a batch/delta-updated aggregate table.
- Offload deep analytical reporting to an analytics system if appropriate.

### 10.5. A Materialized View Is a Snapshot, Not an Always-Current Constant

Defining **"accurate numbers"** requires attaching a timestamp label:

```text
Revenue for Nov 01
    accurate per source at the 09:00 refresh snapshot
```

If the source records a refund at 09:03, a matview refreshed at 09:00 cannot reflect that transaction yet. That is expected staleness, not data corruption, **provided the SLA and metadata are clear**.

---

## 11. Summary Table Updated by Delta

After the +30.00 INSERT experiment in section 7, the materialized view was refreshed in section 8, whereas `daily_sales_summary` still holds 200.00 for tenant 1 on 2026-11-01. Let us update only the delta instead of running GROUP BY over the entire source.

### 11.1. Additive UPSERT

```sql
INSERT INTO view_choice_lab.daily_sales_summary AS s
    (tenant_id, sales_day, paid_orders, gross_amount, updated_at)
VALUES
    (1, DATE '2026-11-01', 1, 30.00, clock_timestamp())
ON CONFLICT (tenant_id, sales_day)
DO UPDATE SET
    paid_orders = s.paid_orders + EXCLUDED.paid_orders,
    gross_amount = s.gross_amount + EXCLUDED.gross_amount,
    updated_at = clock_timestamp();
```

After a single execution, this group reaches **3 paid orders / 230.00**, matching the view.

### 11.2. Why Use ON CONFLICT?

When a tenant/day has no row yet:

- `INSERT` creates the new group.

When the group already exists:

- `ON CONFLICT (tenant_id,sales_day)` locates the exact key.
- `DO UPDATE` adds the delta to the current totals.

Conflict detection and row updates are executed atomically per statement by PostgreSQL; concurrent writers updating the same key must coordinate row locks.

### 11.3. Risk: Running UPSERT Twice Double-Counts

If you execute the UPSERT above again:

```text
Run 1: +1 order, +30.00
Run 2: +1 order, +30.00

Actual source: only one new order
Summary: inflated to +2 orders, +60.00
```

`ON CONFLICT DO UPDATE` **does not inherently guarantee an exactly-once business effect** when the same event is redelivered. It only guarantees atomicity of the operation on that key.

**Do not re-run the +30 UPSERT in the lab if you want it to match the source data.** The next section designs duplicate-prevention mechanisms.

### 11.4. Snapshot Upsert Differs from Delta Upsert

Two patterns:

```sql
-- Assign recomputed group result:
-- gross_amount = EXCLUDED.gross_amount

-- Add incremental change:
-- gross_amount = s.gross_amount + EXCLUDED.gross_amount
```

Never mix the two payload types:

- A snapshot payload `gross_amount=230` must not be added onto 200.
- A delta payload `+30` must not overwrite 200.

A pipeline contract must explicitly state **whether events carry absolute totals or incremental changes**.

---

## 12. Preventing Duplicate Processing: Ledgers and Idempotency

Queue/outbox systems typically deliver events with **at-least-once** semantics. When a worker crashes after committing to the database but before acknowledging the message, the same event can be reprocessed.

### 12.1. Create a Ledger of Applied Changes

```sql
CREATE TABLE view_choice_lab.applied_sales_changes (
    change_id BIGINT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    sales_day DATE NOT NULL,
    delta_paid_orders BIGINT NOT NULL,
    delta_gross_amount NUMERIC(18,2) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

`change_id` is the **unique ID of a business change event**, not necessarily equal to `order_id`. One order can emit multiple valid events (paid, refunded, corrected), so never use `order_id` as the event ID for every change if multiple versions must be tracked.

### 12.2. Apply the Delta Only If the Event Is Not Yet Recorded in the Ledger

In the lab, the +30 order delta was already added in section 11. Therefore **do not replay that delta** in the example below. The statement below illustrates an independent new event with ID 91001 and a source-backed delta; only execute it when an actual corresponding source event exists.

```sql
WITH accepted AS (
    INSERT INTO view_choice_lab.applied_sales_changes
        (change_id, tenant_id, sales_day,
         delta_paid_orders, delta_gross_amount)
    VALUES
        (91001, 1, DATE '2026-11-02', 1, 25.00)
    ON CONFLICT (change_id) DO NOTHING
    RETURNING
        tenant_id, sales_day,
        delta_paid_orders, delta_gross_amount
)
INSERT INTO view_choice_lab.daily_sales_summary AS s
    (tenant_id, sales_day, paid_orders, gross_amount, updated_at)
SELECT
    tenant_id,
    sales_day,
    delta_paid_orders,
    delta_gross_amount,
    clock_timestamp()
FROM accepted
ON CONFLICT (tenant_id, sales_day)
DO UPDATE SET
    paid_orders = s.paid_orders + EXCLUDED.paid_orders,
    gross_amount = s.gross_amount + EXCLUDED.gross_amount,
    updated_at = clock_timestamp();
```

**Scope warning:** This is a syntax template for a valid event; if you run it verbatim after the lab without inserting a corresponding business source event, the summary will **intentionally diverge** from `orders`. To practice this end to end, first create a matching source event or use a separate database for event ingestion simulation.

### 12.3. Why Combining Them in One Statement Prevents "Ledger Recorded Without Summary Applied"

Both operations are linked via `WITH ... RETURNING` inside **a single SQL statement**:

1. Only new events are inserted into `applied_sales_changes`.
2. `accepted` returns only the rows actually inserted.
3. The summary receives deltas only from those rows.

If the statement fails, the transaction does not partially commit the ledger without the summary or vice versa.

### 12.4. Retrying the Same change_id

When event 91001 arrives again:

- `ON CONFLICT (change_id) DO NOTHING` inserts no new ledger row.
- The `accepted` CTE returns zero rows.
- The statement adds no delta to the summary.

This yields an **exactly-once effect per event key** given a sound schema and contract—not a guarantee that the network only ever delivers one message.

### 12.5. Duplicate ID with Different Payload

`ON CONFLICT DO NOTHING` can silently discard a different payload reusing the same `change_id`. In production, you must:

- Ensure event IDs are never reused for different contents.
- Store payload hashes/versions or fields needed for verification.
- Detect payload conflicts instead of silently treating them as harmless retries.
- Provide handling paths for poison messages and dead-letter queues.

### 12.6. Source and Summary Across Separate Transactions Is Still Unsolved

Ledger + summary are updated atomically **on the consumer side**. If orders are written in a different database or published via a separate queue, reliable event delivery from source to consumer remains an issue. Common patterns include:

- Transactional outbox in the same database as the business write.
- CDC reading the transaction log with lag monitoring.
- Event streaming with sequence/versioning and deduplication.
- Watermark tracking and reconciliation.

Never label a pipeline "end-to-end exactly once" merely because the consumer uses `ON CONFLICT DO NOTHING`.

---

## 13. Refunds, Order Edits, and Negative Deltas

Counting only new INSERTs is insufficient. Metrics also change when:

- `paid → refunded`.
- `paid → cancelled` when business rules allow it.
- Editing `amount` after payment.
- Changing `tenant_id` or `ordered_at`, moving an order into a **different reporting group**.
- Deleting rows, fixing duplicate entries, or correcting historical data.

### 13.1. Reversal When paid → refunded

If a paid order of 80.00 for tenant 1 on Nov 01 changes to refunded, the corresponding group needs:

```text
delta_paid_orders = -1
delta_gross_amount = -80.00
```

This is a **reversal** of the prior contribution. Never subtract 80 while forgetting to decrement `paid_orders`.

### 13.2. Updating Source and Summary in the Same Transaction

For simple systems inside **the same database**, transactions can coordinate source and summary updates together:

```sql
-- Example simulating refund of order_id=2 in a fresh lab database;
-- do not repeat if the order is already refunded.
BEGIN;

WITH changed AS (
    UPDATE view_choice_lab.orders
    SET status = 'refunded'
    WHERE order_id = 2
      AND status = 'paid'
    RETURNING
        tenant_id,
        (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
        amount
),
adjusted AS (
    UPDATE view_choice_lab.daily_sales_summary AS s
    SET
        paid_orders = s.paid_orders - 1,
        gross_amount = s.gross_amount - c.amount,
        updated_at = clock_timestamp()
    FROM changed AS c
    WHERE s.tenant_id = c.tenant_id
      AND s.sales_day = c.sales_day
      AND s.paid_orders >= 1
      AND s.gross_amount >= c.amount
    RETURNING s.tenant_id, s.sales_day
)
SELECT
    (SELECT COUNT(*) FROM changed) AS changed_orders,
    (SELECT COUNT(*) FROM adjusted) AS adjusted_groups;

-- In operational code, ONLY COMMIT when the verification check passes.
-- If changed_orders=1 while adjusted_groups<>1, ROLLBACK and investigate.
COMMIT;
```

**Note:** The `COMMIT` line here illustrates transaction flow for lab data in the expected state. Production application code must **check affected row counts and explicitly ROLLBACK on invariant violations**, or wrap logic in a function using `RAISE EXCEPTION` so skewed state cannot commit. Do not copy this snippet into cron assuming a `SELECT` check alone prevents bad commits.

### 13.3. Why the status='paid' Predicate Matters

If the same refund command is retried, `status='paid'` is no longer true on the second attempt, so `UPDATE orders` returns zero rows in the CTE and no contribution is subtracted twice.

However, systems with multiple status transitions require a proper **state machine** and event versioning, not just a single status filter.

### 13.4. How Does a Materialized View Handle Refunds?

For a matview:

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales;
```

The new result is recomputed from the source, automatically excluding the refunded order's contribution. You do not need to write a `-80` delta for a matview, though you pay the cost of refreshing.

### 13.5. How Does a View Handle Refunds?

The view runs GROUP BY over rows where `status='paid'` as of the query snapshot, so once the refunded status is committed at the source, new reports automatically exclude that order.

### 13.6. Changing Grain Requires Updating Both Sides

If an order is moved from tenant 1 / Nov 01 to tenant 2 / Nov 02:

```text
Old grain (tenant 1, Nov 01): subtract old contribution
New grain (tenant 2, Nov 02): add new contribution
```

A delta pipeline must know both the **old row** and the **new row**. Inspecting only NEW is insufficient to subtract from the old group. In PostgreSQL triggers, use `OLD`/`NEW`; in CDC, use before/after images or compensating events; in application code, lock/read the prior record within the transaction.

### 13.7. Empty Groups and Zero Values

If a group previously had one paid order that was later refunded:

- A view/matview built with `GROUP BY ... WHERE status='paid'` will **no longer contain a row** for that group.
- A delta-subtracting summary table may retain a row with `paid_orders=0, gross_amount=0`.

These are two different representations. When reconciling, choose a rule:

- Delete the summary group when both order count and revenue drop to 0, or
- Keep zero rows and use a calendar/COALESCE pattern to standardize output.

Do not conclude there is data corruption merely because one side omits a row while the other keeps a zero row, if the reporting contract permits it.

---

## 14. Backfill and Reconciliation: Non-Negotiable

With a self-maintained summary table, a pipeline can drop events, double-count, apply the wrong timezone, or undergo revenue-definition changes over time. You must be able to rebuild from the **source of truth**.

### 14.1. Canonical Query for Reconciliation

`v_daily_sales` in the lab acts as the centralized definition of revenue from the source. In production, the canonical query must be independently reviewed and versioned; do not assume a view is always bug-free either.

### 14.2. Reconcile the Entire Grain with FULL OUTER JOIN

```sql
SELECT
    COALESCE(v.tenant_id, s.tenant_id) AS tenant_id,
    COALESCE(v.sales_day, s.sales_day) AS sales_day,
    COALESCE(v.paid_orders, 0) AS actual_paid_orders,
    COALESCE(s.paid_orders, 0) AS summary_paid_orders,
    COALESCE(v.gross_amount, 0) AS actual_gross_amount,
    COALESCE(s.gross_amount, 0) AS summary_gross_amount
FROM view_choice_lab.v_daily_sales AS v
FULL OUTER JOIN view_choice_lab.daily_sales_summary AS s
    ON s.tenant_id = v.tenant_id
   AND s.sales_day = v.sales_day
WHERE
    COALESCE(v.paid_orders, 0)
        <> COALESCE(s.paid_orders, 0)
    OR
    COALESCE(v.gross_amount, 0)
        <> COALESCE(s.gross_amount, 0)
ORDER BY tenant_id, sales_day;
```

This query surfaces per-group discrepancies, including groups missing on either side. It incurs source-table read/aggregation cost; on large datasets, reconcile by date window, tenant, or sampling first.

### 14.3. Simple Rebuild During a Maintenance Window

For small demo tables where **blocking writers temporarily** is acceptable, an illustrative workflow is:

```sql
BEGIN;

-- SHARE lock on orders blocks transactions modifying orders
-- during the rebuild; evaluate lock contention carefully.
LOCK TABLE view_choice_lab.orders IN SHARE MODE;

DELETE FROM view_choice_lab.daily_sales_summary;

INSERT INTO view_choice_lab.daily_sales_summary
    (tenant_id, sales_day, paid_orders, gross_amount)
SELECT tenant_id, sales_day, paid_orders, gross_amount
FROM view_choice_lab.v_daily_sales;

COMMIT;
```

After rebuilding, the summary table accurately reflects the GROUP BY over source data within that transaction/locking context, assuming no separate pipeline is concurrently applying independent deltas to the summary.

**Do not treat this snippet as an online procedure for tables with hundreds of millions of rows**:

- `LOCK ... IN SHARE MODE` blocks writers on `orders`.
- A full-table `DELETE` generates WAL, creates dead tuples, and holds row locks.
- Readers on older snapshots may observe intermediate states under MVCC depending on isolation/cutover.
- Running delta consumers may block on locks or double-apply events already included in the rebuild snapshot.

### 14.4. Production Rebuilds Need Cutoffs and Coordination

A large-scale procedure typically requires:

1. Establishing a source snapshot/watermark.
2. Recomputing aggregates into a staging table or checkpointed batches.
3. Validating row counts, sums, and critical groups.
4. Pausing or coordinating delta consumers during cutover.
5. Applying post-watermark changes to the new version or swapping atomically via an appropriate mechanism.
6. Switching readers to the reconciled version.
7. Retaining a rollback path and monitoring post-cutover.

Never rebuild into a live table while letting an event consumer re-apply **the same orders already captured in the rebuild**.

### 14.5. Watermarks Must Be Meaningful

An `updated_at` timestamp on a summary row is not enough to prove the worker has processed **all** events prior to a given cutoff. Good watermarks rely on:

- Ordered, acknowledged offsets/sequences.
- Transaction log positions in CDC.
- Batch/job IDs with deterministic data boundaries.
- Durably stored snapshots/revisions.

The goal is being able to answer: "Exactly **up to what point** has this table applied all source changes?"

### 14.6. Reconciling Counts and Sums Is Not Everything

Two bugs can accidentally cancel out to the same dollar total, hiding wrong underlying rows. For sensitive data, supplement checks with:

- Breakdowns by status/currency/category.
- Detecting unprocessed events by ID.
- Transaction/amount totals per checkpoint.
- Audit logs and scoped hashes/checksums.
- Business tests covering refunds and date/tenant edits.

---

## 15. Freshness Requirements: Designing a Freshness SLA

### 15.1. Freshness Differs from Query Latency

- **Query latency:** time for one SELECT to return results (e.g., 40 ms).
- **Data freshness:** delay between a source change and its appearance in the report.

A materialized view might return in 5 ms while displaying metrics from 30 minutes ago. A direct view might take 1,500 ms while reading the latest source snapshot.

### 15.2. Define the SLA in Measurable Terms

For example:

```text
99% of paid events are reflected in the report
within 60 seconds after the source transaction commits.
```

That is a concrete target, unlike "near real-time report".

### 15.3. Selection Guidance by SLA

| Goal | Option to consider | Condition |
|---|---|---|
| Query current state at latest snapshot | View | Source GROUP BY/JOIN is fast enough |
| Minutes/hours of lag acceptable | Materialized view + refresh schedule | Refresh reliably finishes ahead of deadline |
| Sub-second/few-second updates, heavy load | Transactional/event-driven summary table | Has deltas, idempotency, watermarks, and reconciliation |
| Ad-hoc queries with low read volume | View or direct query | Avoid materializing endless permutations |
| Heavy report on infrequently changing data | Materialized view | Aggregated output is much smaller than source |
| Many complex real-time reports | Dedicated aggregation system or analytics architecture | Evaluate cost/engineering overhead of another system |

Never stop at the word "real-time" in a requirement. Ask about **source commit time**, percentage of events required to catch up, failure modes, and how stale data should be surfaced.

### 15.4. Scheduling REFRESH Does Not Guarantee an SLA If Jobs Are Slow

Suppose:

```text
Refresh starts at 09:00
Refresh finishes at 09:12
Next run starts at 09:15
```

A query at 09:14 sees a snapshot computed from source state around the start of the refresh, not 09:14 metrics. Merely "refreshing every 15 minutes" does not prove **15-minute max staleness** in every scenario.

Monitor:

- Refresh **start** and **completion** timestamps.
- Source snapshot timestamp read per transaction semantics.
- Lock wait duration.
- Recomputation query duration.
- Success/failure status.
- Age of the served snapshot/data offset.

### 15.5. What If a Refresh Fails?

The matview may continue serving an old snapshot. The dashboard should know:

- Time of the last successful refresh.
- Job failure count.
- Whether data age has breached the SLA.
- Whether to alert or display a "data as of ..." badge.

Do not treat a successful SELECT against a matview as proof that the refresh scheduler is healthy.

---

## 16. Views Are Not Materialized Storage and Have No Own Indexes

### 16.1. Indexes Belong on the Source Table

For the view backed by `orders`:

```sql
CREATE INDEX orders_paid_tenant_time_idx
ON view_choice_lab.orders (tenant_id, ordered_at)
WHERE status = 'paid';
```

This is a **partial B-tree index on the source table**. It can accelerate queries constrained by tenant and time range, because it indexes paid rows only.

Do not write:

```sql
-- You cannot create a physical B-tree index directly on a regular VIEW:
-- CREATE INDEX ... ON view_choice_lab.v_daily_sales (...);
```

### 16.2. Time Conversions Can Affect Index Usage

The view groups by:

```sql
(ordered_at AT TIME ZONE 'UTC')::date
```

An outer query:

```sql
SELECT *
FROM view_choice_lab.v_daily_sales
WHERE sales_day = DATE '2026-11-01';
```

may not always be transformed by the planner into a simple range scan on `orders.ordered_at`. If this becomes a hotspot, consider:

- Direct SQL using `ordered_at >= lower` and `ordered_at < upper`.
- Creating an appropriate expression index when valid and backed by actual workload needs.
- Materializing daily reports into an MV or summary table.
- Inspecting `EXPLAIN` to verify actual pushdown/pruning behavior.

**Never assume a view automatically turns every predicate on an aggregated column into an indexable predicate on the base table.**

### 16.3. Predicate Pushdown Has Limits

In many simple queries, PostgreSQL optimizes views by pushing predicates down. However:

- Aggregates, window functions, DISTINCT, and LIMIT can restrict certain transformations.
- `security_barrier` can alter evaluation order to protect sensitive data.
- Volatile functions and complex JOINs carry specific semantics.

Thus, a view is a useful abstraction layer, not a guarantee that every outer query produces the same plan as hand-written SQL at a different level.

### 16.4. ORDER BY Inside a View

Never rely on physical row order or incidental output order from a view, MV, or summary table. When an API requires deterministic pagination:

```sql
SELECT *
FROM view_choice_lab.v_daily_sales
ORDER BY tenant_id, sales_day;
```

Views are read through an outer SELECT; **ORDER BY in the consuming query** is the ordering contract that must be stated explicitly.

---

## 17. Indexing Materialized Views and Summary Tables

### 17.1. Indexes on a Materialized View

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales
    (tenant_id, sales_day);
```

This index was already created in section 5; the snippet above restates the definition—do not run it twice.

A query:

```sql
EXPLAIN
SELECT paid_orders, gross_amount
FROM view_choice_lab.mv_daily_sales
WHERE tenant_id = 1
  AND sales_day = DATE '2026-11-01';
```

may use the index depending on cost and cardinality. With only a handful of rows in the lab, a Seq Scan is usually optimal.

### 17.2. Primary Keys on Summary Tables

```sql
PRIMARY KEY (tenant_id, sales_day)
```

PostgreSQL creates a unique B-tree index to enforce the constraint. It can serve queries like:

```sql
WHERE tenant_id = 1
  AND sales_day >= DATE '2026-11-01'
  AND sales_day <  DATE '2026-12-01'
```

If the workload frequently queries **all tenants for a single day**, a secondary index leading with `sales_day` may be helpful, but create it only after measuring.

### 17.3. There Is No "Global Index" for Reports Just Because the Source Is Indexed

An index on `orders(tenant_id,ordered_at)` speeds up scanning the source. An index on `mv_daily_sales(tenant_id,sales_day)` speeds up reading **stored results**. The two indexes serve different stages and different relations.

### 17.4. Covering Indexes and INCLUDE

In certain workloads:

```sql
-- Pattern to consider; no need to add this in the lab:
-- CREATE INDEX ... ON daily_sales_summary
--   (tenant_id, sales_day)
--   INCLUDE (paid_orders, gross_amount);
```

`INCLUDE` can enable index-only scans when MVCC visibility conditions permit. However, if a summary table receives continuous UPDATEs, the visibility map may limit index-only scans more than expected, and wider indexes increase write overhead.

Do not add INCLUDE indexes out of habit when the primary key already suffices for a few hundred or thousand groups.

### 17.5. ANALYZE After Bulk Loads or REFRESH

```sql
ANALYZE view_choice_lab.mv_daily_sales;
ANALYZE view_choice_lab.daily_sales_summary;
```

Accurate statistics help the planner estimate row counts and selectivity. For large reporting relations that are refreshed or rebuilt, adopt a proper statistics management strategy; never rely on plans gathered prior to populating data.

---

## 18. Reading EXPLAIN: When Does Cost Shift from READ to WRITE?

### 18.1. Querying the VIEW

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_choice_lab.v_daily_sales
WHERE tenant_id = 1
ORDER BY sales_day;
```

Inspect the nodes beneath the aggregate: source scan, paid filter, hash/sort/group, and buffers touched. PostgreSQL still performs the aggregation work on read.

### 18.2. Querying the MATERIALIZED VIEW

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_choice_lab.mv_daily_sales
WHERE tenant_id = 1
ORDER BY sales_day;
```

The plan accesses only the stored matview relation; it does not redo GROUP BY over `orders` on every SELECT.

### 18.3. Querying the SUMMARY TABLE

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM view_choice_lab.daily_sales_summary
WHERE tenant_id = 1
ORDER BY sales_day;
```

Read cost for the small result relation is similar, but you must include the total cost of the pipeline, UPSERTs, ledger, and backfills for a fair architectural comparison.

### 18.4. Do Not Compare Single-SELECT Latency Alone

A complete comparison requires at least:

| Metric | View | Materialized view | Summary table |
|---|---|---|---|
| SELECT p50/p95/p99 | Yes | Yes | Yes |
| Source query CPU/I/O | Per SELECT | Per REFRESH | Per job/delta |
| Total source scans | Scales with read traffic | Scales with refresh schedule | Scales with backfills/reconciliation |
| WAL generation | Primarily source | Source + refresh storage/indexes | Source + summary/ledger |
| Lock contention | Per source query | Per refresh and SELECT | Per group/source update |
| Storage | View definition | Results + indexes | Results + indexes + ledger |
| Data lag | Query snapshot | Last refresh | Pipeline watermark |
| Recovery complexity | Typically low | Re-run refresh | Rebuild/replay/reconcile |

### 18.5. Be Cautious with Small Lab Datasets

On six or seven orders, a view can easily be faster than a matview because overhead is tiny. Never use a test on a handful of rows to justify a production architecture for hundreds of millions of orders.

### 18.6. Measure the True Cost of Refresh

Do not measure only matview SELECT time. Measure:

- Both standard REFRESH and CONCURRENTLY durations.
- CPU/I/O spent recomputing the source query.
- Lock hold and wait times.
- Replica lag and WAL volume.
- Matview and index footprint.
- Timestamp when new data becomes visible after refresh commit.

If a refresh triggers multi-minute resource spikes that degrade application performance, a matview may need replacement even if individual SELECTs are blazingly fast.

---

## 19. Designing Aggregations Correctly

### 19.1. SUM and COUNT Are Compensatable by Grain

In the simplified paid-order model, these two measures:

```text
paid_orders = SUM(1 per paid order)
gross_amount = SUM(amount per paid order)
```

are **additive** across disjoint groups, enabling delta additions and reversals when status changes.

### 19.2. AVG Is Not the Average of Daily AVGs

Consider two days:

```text
Day A: 1 order, amount 100
Day B: 9 orders, total amount 90

Period AVG = (100 + 90) / (1 + 9) = 19
AVG of daily AVGs = (100 + 10) / 2 = 55  <- wrong
```

If you need monthly average order value from a daily summary, store **SUM(amount)** and **COUNT(*)** and compute:

```sql
SELECT
    tenant_id,
    SUM(gross_amount)
        / NULLIF(SUM(paid_orders), 0) AS avg_paid_order_amount
FROM view_choice_lab.daily_sales_summary
GROUP BY tenant_id;
```

### 19.3. COUNT(DISTINCT ...) Is Not Simply Additive

If the same customer makes purchases on two different days, summing daily distinct customer counts double-counts that customer in the monthly total.

**Do not** store a daily distinct count and sum it across a year if the business requires annual distinct counts. Options include:

- A finer-grained summary by customer.
- Recomputing from raw data for the requested window.
- Sketches/approximate distinct structures with explicit error bounds.
- A membership table to track distinct customers.

### 19.4. Join Fanout Breaks All Three Options

If an order has three line items and a report runs:

```sql
SELECT SUM(o.amount)
FROM orders o
JOIN order_items i ON i.order_id = o.order_id;
```

`o.amount` gets counted three times. A view, matview, and summary table will all **store or return the exact same wrong calculation**.

Fix: identify table grain before and after JOINs; pre-aggregate items by order or separate measures at their proper grains. `SUM(DISTINCT o.amount)` is not a general fix because two distinct orders can have identical amounts.

### 19.5. Multiple Currencies

Never add:

```text
100 USD + 100 VND = 200 "money"
```

In production:

- Include `currency` in the grain and keys if reporting per currency.
- If reporting in a single converted currency, define which exchange rate timestamp applies.
- Store source currency, exchange rate/version, and target currency.
- Establish a policy for restating summaries when rates or transactions are adjusted.

### 19.6. Distinguish Gross, Net, Refunds, and Recognized Revenue

The `status='paid'` rule in the lab is a simplification. Real systems typically involve payment, invoice, refund, and ledger tables; accounting revenue may be recognized at a different point than order payment.

Never name a column `gross_amount` and pass it off as official financial reporting without business sign-off.

---

## 20. Choosing an Approach When Reports Have Many Filter Dimensions

A dashboard might filter by:

```text
tenant
date range
region
sales channel
product category
campaign
payment method
currency
```

### 20.1. Views Stay Flexible Under Diverse Filter Combinations

A view over source data can serve arbitrary WHERE predicates and JOINs. However, flexibility does not remove source scanning cost at large scale.

### 20.2. Materializing Too Many Dimensions Explodes Cardinality

Suppose:

```text
100 tenants × 365 days × 20 regions × 10 channels × 50 categories
      = 365 million theoretical combinations
```

In practice, only combinations with data emit GROUP BY rows, yet cardinality can still grow huge.

An overly granular materialized view will:

- Consume large amounts of disk.
- Take a long time to refresh.
- Require large indexes.
- Lose the "much smaller than source" benefit.

### 20.3. Choose a Grain Flexible Enough Without Being Too Fine

This grain:

```text
(tenant_id, sales_day)
```

fits per-day/per-tenant reporting, but **cannot** reconstruct per-product reports because product detail has been aggregated away.

If product-level detail is needed:

```text
(tenant_id, sales_day, product_id)
```

can still roll up to day/tenant via SUM, at higher storage and update cost. Verify whether all measures are additive across products.

### 20.4. Hybrid: Multi-Layer Data Architecture

A realistic architecture can combine approaches:

```text
orders source
  |
  +--> v_order_details          (logical SQL layer)
  |
  +--> daily_sales_summary      (real-time API)
  |
  +--> mv_monthly_kpis          (periodic dashboard)
  |
  +--> analytics warehouse      (deep historical reporting)
```

You do not need to force **a single mechanism** to serve every use case. Still, avoid having multiple slightly different revenue definitions silently powering the same metric.

---

## 21. Views and Data Access Permissions

### 21.1. A View Can Act as a Stable SQL API

A view:

```sql
CREATE VIEW view_choice_lab.v_paid_order_public AS
SELECT
    order_id,
    tenant_id,
    ordered_at,
    amount
FROM view_choice_lab.orders
WHERE status = 'paid';
```

can expose selected columns while hiding fields you do not want granted to a given read role.

However, **do not assume a view automatically provides a tenant security boundary** without properly designing permissions and RLS.

### 21.2. Permissions on Views and Base Tables

By default in PostgreSQL, views evaluate base-table permissions using rules tied to the **view owner** per PostgreSQL's standard behavior. Consequently, a role granted SELECT on a view can normally read through it even without direct SELECT privileges on the underlying base table.

This helps expose a restricted interface, provided you manage ownership, grants, function privileges, and related controls carefully.

### 21.3. security_invoker

PostgreSQL 15+ supports the `security_invoker` option on views:

```sql
-- Example on PostgreSQL versions supporting security_invoker:
-- CREATE VIEW view_choice_lab.v_order_invoker
-- WITH (security_invoker = true)
-- AS SELECT order_id, tenant_id
--    FROM view_choice_lab.orders;
```

With `security_invoker=true`, permissions of the calling user are checked on underlying relations according to that option's semantics; RLS behaves accordingly as well. Do not copy this syntax onto older PostgreSQL versions without checking support.

### 21.4. security_barrier

`security_barrier` on a view restricts certain plan transformations that could otherwise leak data through functions or predicates evaluated out of security order.

```sql
-- Depending on security goals:
-- CREATE VIEW some_view WITH (security_barrier = true) AS ...;
```

However, a security barrier can inhibit predicate pushdown and impact performance. It **does not replace a complete authorization model**.

### 21.5. RLS and Tenant Isolation

In multi-tenant systems:

- Enforce authorization rules where they can be verified.
- Explicitly verify view owner/invoker and RLS behavior.
- Never grant SELECT on a multi-tenant matview if cross-tenant reads must be blocked.
- Never assume a client-supplied `WHERE tenant_id=$1` condition is sufficient security if a caller can omit it.

### 21.6. A Materialized View Is Copied Data

Because a matview holds physical data, RLS or permissions configured on the source table **are not automatically re-evaluated against the source whenever someone SELECTs the matview**. Separately audit grants, ownership, and access controls on the materialized relation.

A cross-tenant aggregated matview can leak other tenants' numbers if read permissions are overly broad.

### 21.7. Summary Tables Must Also Be Protected

A summary table may hold PII, financial metrics, and per-tenant data. Permissions for writer workers/consumers and reader roles must be designed separately; writer workers should not receive blanket privileges across the entire schema unnecessarily.

---

## 22. Updatable or Not? Important Limitations

### 22.1. Some Simple Views Are Automatically Updatable

For instance, a single-table view without GROUP BY:

```sql
CREATE VIEW view_choice_lab.v_paid_order_public AS
SELECT order_id, tenant_id, ordered_at, amount
FROM view_choice_lab.orders
WHERE status = 'paid';
```

This definition was already created in section 21; this is a reminder—**do not re-run CREATE VIEW with the same name**.

PostgreSQL supports **automatically updatable views** when the definition meets the required rules. Still, updates through a view remain bound by updatable columns, constraints, and `CHECK OPTION` rules when configured.

### 22.2. GROUP BY Views Do Not Auto-Update Like Tables

```sql
CREATE VIEW view_choice_lab.v_daily_sales AS
SELECT tenant_id, ..., COUNT(*), SUM(amount)
FROM ...
GROUP BY ...;
```

This illustrates the definition created in section 4. An aggregated row does not map one-to-one to a single order, so there is no simple automatic UPDATE that changes `gross_amount=200` to 250 and knows which order to modify.

You can write `INSTEAD OF` triggers/rules for specific interfaces, but never assume PostgreSQL can back-propagate edits to source rows through an aggregate view.

### 22.3. A Materialized View Is Not an Arbitrary DML Table

A matview is refreshed from its defining query. Do not run direct `INSERT/UPDATE/DELETE` on it as you would on a regular summary table.

### 22.4. A Summary Table Supports Standard UPDATE/UPSERT

That is precisely why summary tables fit delta-update pipelines. In return, **correctness** does not come automatically from the table being updatable.

### 22.5. Do Not Confuse "Updatable View" with "Live Aggregate"

A view can reflect live source data while **not permitting writes through the view**. "Live" describes **reading**, whereas "updatable" describes **writing through the interface**.

---

## 23. Synchronization Under Concurrency and Transactions

### 23.1. Views Read a Statement-Consistent Snapshot

An aggregate SELECT uses a database snapshot determined by the transaction isolation level. It does not mix half-committed pre-commit and post-commit states from the same transaction in a way that violates commit atomicity.

### 23.2. Materialized Views Have a Refresh Snapshot

REFRESH executes its query using the snapshot of the refresh transaction/statement, then publishes the result upon commit. While refresh runs, writers can continue modifying source tables; changes committed after the snapshot used by refresh **will not necessarily be included** in that refresh run.

Never label a matview "accurate up to job completion time" if the job actually read an earlier snapshot.

### 23.3. Synchronous Summaries in the Same Transaction

If an API inserts an order and updates the daily summary **in the same transaction**—rolling back if either step fails—the system achieves strong consistency between the two relations for that workflow.

However, this can increase:

- Lock contention on hot summary groups.
- Transaction duration.
- Deadlock risk if different code paths update tables in different orders.
- Write amplification.

### 23.4. Hot-Row Contention

If every order for a busy tenant on the same day updates:

```sql
PRIMARY KEY (tenant_id, sales_day)
```

that summary row can become a **hot row** when thousands of concurrent writers try to apply deltas at once.

Mitigations to consider:

- Batch events instead of running an UPDATE per individual order.
- Shard counters into sub-buckets and roll them up.
- Partition an event stream/queue by tenant for intentional serialization.
- Decouple analytics workloads from online transactions.
- Use a matview if freshness tolerances allow.

Do not turn every order write into a transaction waiting on one hot row lock without benchmarking first.

### 23.5. Isolation Levels Do Not Cure Missing Events

`SERIALIZABLE` or stricter locking prevents certain anomalies, but it cannot redeliver lost messages between a source system and an async consumer. Delivery guarantees, idempotency, and reconciliation must be designed independently.

### 23.6. Eventual Consistency Must Be Made Explicit

If the summary is updated asynchronously, a gap exists:

```text
Paid order committed at source
            |
            v
Event waiting in queue
            |
            v
Summary not yet updated
            |
            v
Consumer processes and commits summary
```

This lag must stay within the freshness SLA or be surfaced in the UI. Never describe an asynchronous summary pipeline as "instantaneously consistent".

---

## 24. Partitioning and Data Lifecycle

A large `orders` table may be partitioned by month. That introduces additional reporting considerations:

### 24.1. Views Over Partitioned Tables

Views can benefit from **partition pruning** when predicates match the partition key and the planner proves irrelevant partitions can be skipped.

If a query aggregates all historical data every time, the view must still scan many partitions.

### 24.2. Materialized Views Do Not Auto-Update When Source Partitions Detach

If an old monthly partition is DETACHed or DROPped, a matview **does not automatically alter its stored contents**. Only after a refresh does the result reflect the current source state.

This can be:

- Useful if historical aggregates should be kept after raw data leaves online storage, **provided policy and controls are in place**.
- Risky if source data was deleted for privacy compliance while the matview still retains prohibited personal/aggregate data.

### 24.3. Summary Tables Can Outlive Raw Data

For example:

```text
Raw orders: retained 90 days
Non-PII daily summary: retained 3 years
```

This saves space, but is only valid if retention and compliance policies allow it. Once raw data is purged, **exact rebuilds** of historical periods from source are no longer possible; preserve required audit trails or backups per policy.

### 24.4. Do Not Assume Retention Automatically Purges Every Copy

Dropping a source partition does not automatically delete data from:

- Materialized views.
- Summary tables.
- Backups/archives.
- Data warehouses.
- Logs and caches.

Execute retention policies using an **inventory of all data copies**, not just the primary source table.

---

## 25. Choosing Based on Workload Metrics

Before deciding, gather at least:

| Question | Information needed |
|---|---|
| How large is the source table? | Rows, bytes, partitions, growth rate |
| How long does the query take now? | p50/p95/p99, buffers, CPU, temp spills |
| How often is the query called? | Requests/minute, concurrency |
| How heavily does the source change? | INSERT/UPDATE/DELETE rates |
| How many aggregate groups exist? | Cardinality at the chosen grain |
| What is the max tolerable lag? | SLA, measured via commit time/watermark |
| Are there late events/refunds? | Timing and frequency of corrections |
| Multi-tenant or multi-currency? | Authorization rules and group keys |
| Can source be locked for rebuilds? | Maintenance windows, write load |
| What operational complexity is acceptable? | Scheduler, queue/CDC, alerts, on-call |

### 25.1. Example Decision: Stick with a View

Suppose:

```text
orders: 2 million rows, growing 3,000/day
dashboard: 5 requests/minute
view query: 80 ms p95
SLA: fresh per latest snapshot
```

A view already meets requirements well. Adding a matview or event pipeline adds unnecessary complexity unless other constraints apply.

### 25.2. Case Worth Testing a Matview

```text
orders: 100 million rows
report query: 12 seconds
dashboard: 200 requests/minute
SLA: up to 30 minutes lag
Test REFRESH: 4 minutes, acceptable load
```

A matview can drastically reduce repeated SELECT overhead; validate the refresh job, concurrency/locks, and actual freshness.

### 25.3. Case Worth Testing a Summary Table

```text
orders: 400 million rows
report query: 20 seconds
dashboard: 1,000 requests/minute
SLA: most events under 15 seconds
Full REFRESH: 25 minutes
Event stream/outbox already in place, with reconciliation
```

A delta/batch-updated summary table fits better than full refreshes. Still, if concurrent updates hit the same hot key, the delta design must mitigate contention.

### 25.4. Do Not Treat Illustrative Numbers as Official Benchmarks

The timings and rates above are **hypothetical scenarios** to illustrate decision-making, not PostgreSQL performance guarantees. Real-world results depend on hardware, caching, query shape, indexes, data distribution, concurrency, and PostgreSQL version.

---

## 26. Operational Runbook for MATERIALIZED VIEW

### 26.1. Before Deployment

1. Define grain and business semantics.
2. Benchmark the defining query on representative data.
3. Estimate result row count and storage footprint.
4. Create the matview `WITH DATA` or run the initial load if using `WITH NO DATA`.
5. Create indexes needed by read queries.
6. If using `CONCURRENTLY`, create at least one **non-partial, non-expression UNIQUE index covering all rows**.
7. Audit access permissions and tenant isolation.

### 26.2. Running Refreshes

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    view_choice_lab.mv_daily_sales;
```

Use the concurrent form only when the matview is populated and has a qualifying unique index; otherwise, run standard refresh according to procedure.

### 26.3. Monitoring the Job

Track:

- Started/finished timestamps.
- Success/failure status.
- Lock wait duration.
- Refresh execution duration.
- Result row count and index sizes.
- Concurrent source write activity during refresh.
- Data freshness via snapshot/watermark.
- Replica lag and WAL generation.

### 26.4. Handling Refresh Failures

Do not immediately drop the matview when a job fails. Instead:

1. Inspect the error (unique index, permissions, defining SQL, disk space, statement timeout).
2. Verify whether the matview remains populated and readable.
3. Retain the stale snapshot if the contract permits; raise staleness alerts.
4. Fix the root cause and perform a coordinated retry.
5. If a full rebuild is required, plan it so dashboards do not abruptly lose data.

### 26.5. Changing the SQL Definition

Do not expect `REFRESH` to accept arbitrary changes to the defining query. When reporting logic changes (adding currency, changing timezone, adding a grouping dimension), perform a proper materialized view migration, update the unique index, and verify output.

For large systems, a safe approach is building a **new versioned matview**, populating/indexing/comparing it, and switching readers in a planned cutover rather than breaking the live relation in place.

---

## 27. Operational Runbook for Summary Tables

### 27.1. Source Data Contract

Define:

- Which source events generate positive contributions (`+`)?
- Which events generate negative contributions (`-`)?
- When is an order considered paid?
- Are partial refunds, taxes, discounts, and multiple currencies involved?
- When editing an order, which contributions must be reversed?

Never leave consumers guessing from undefined status transitions.

### 27.2. Grain Contract

```text
PRIMARY KEY:
  (tenant_id, sales_day)

METRICS:
  paid_orders
  gross_amount
```

If currency or product is added, update both the key and the delta logic.

### 27.3. Delivery Contract

- Every change event carries a unique ID/version.
- A ledger or offset mechanism enforces deduplication.
- No gap exists between source writes and event publication.
- Retries and out-of-order events are handled.
- Dead-letter handling and replay capabilities exist.

### 27.4. Freshness Contract

- Track source position/watermark.
- Measure consumer lag.
- Alert on SLA breaches.
- Surface "data as of" in UI/API where needed.

### 27.5. Reconciliation Contract

- Reconcile by tenant/day (and currency if present).
- Detect missing or extra groups.
- Verify COUNT/SUM and edge-case groups.
- Maintain a repair procedure from the source of truth.
- Retain correction audit trails, distinguishing corrective adjustments from routine replays.

### 27.6. Backup and Rebuild Contract

- Know up to what point raw data allows a full rebuild.
- If raw source data is archived/dropped, preserve lawful access paths for rebuilds.
- Ensure cutover avoids double-applying deltas.
- Factor rebuild duration into RTO.

### 27.7. Protecting Sensitive Data

Separate writer and reader privileges; never let arbitrary application roles run ad-hoc UPDATEs against audited aggregate metrics. Log changes, enforce tenant boundaries, and audit copies.

---

## 28. Common Pitfalls

**1. "A view is a SELECT cache."** False. A regular view stores a query definition, not a copy of results.

**2. "A view is always faster than the raw query."** No. It typically performs the same underlying source work while changing the SQL interface.

**3. "A view is always strictly real-time."** No. Reads follow snapshot/MVCC semantics and can still be affected by replica or application cache lag.

**4. "A materialized view auto-updates when the base table changes."** No. It requires `REFRESH`.

**5. "REFRESH CONCURRENTLY is an incremental refresh."** No. The defining source query still re-executes.

**6. "CONCURRENTLY is always faster than standard REFRESH."** No. It can use more resources and take longer.

**7. "REFRESH CONCURRENTLY does not need a unique index."** False. A qualifying unique index is mandatory.

**8. "A partial unique index works for REFRESH CONCURRENTLY."** False.

**9. "A unique expression index is sufficient too."** False. The unique index must reference column names (not expressions) and cover all rows.

**10. "You can REFRESH CONCURRENTLY on an unpopulated WITH NO DATA matview."** No.

**11. "WITH NO DATA means SELECT normally returns 0 rows."** False; an unpopulated matview is unscannable.

**12. "If refresh finishes at 09:10, the snapshot is guaranteed to be 09:10."** No. Data reflects the snapshot active when execution began/ran.

**13. "A matview's staleness always equals the cron interval."** No. Run duration, failures, and lock waits increase staleness.

**14. "A matview can be UPDATEd row-by-row like a summary table."** Not via normal DML operations.

**15. "A summary table automatically knows about its source table."** No. It is an ordinary table.

**16. "Additive ON CONFLICT guarantees exactly once."** No. Retrying the same event double-counts without deduplication.

**17. "Setting change_id=order_id works for all refunds and corrections."** Not if one order generates multiple business events.

**18. "No backfill is needed because the job will run properly going forward."** False. Historical data may be missing or skewed.

**19. "If a summary table has a PRIMARY KEY, its numbers are guaranteed accurate."** No. Constraints do not reconcile results against the source.

**20. "REFRESH matview updates only the groups that changed."** Not by default in core PostgreSQL.

**21. "When an order changes date, you only need to add it to the new group."** False. You must subtract from the old group.

**22. "A refund only needs to reduce amount, not order count."** Incorrect under this lab's `paid_orders` definition.

**23. "Updating status again should still apply a -1 delta."** No, if that transition was already processed; idempotence/state machines are required.

**24. "A summary row of 0 is always identical to an absent view row."** Not structurally; the API must standardize them.

**25. "The AVG of daily AVGs equals the overall period AVG."** False whenever daily order volumes differ.

**26. "Daily distinct counts can be summed across days."** No, whenever entities appear on multiple days.

**27. "SUM(DISTINCT amount) fixes JOIN fanout."** No, because distinct orders can share identical amounts.

**28. "Summing multiple currencies in a single SUM is fine."** No, not without explicit conversion rules.

**29. "SUM(gross_amount) on paid orders is always official accounting revenue."** No. Business definitions must be confirmed.

**30. "A GROUP BY view is automatically updatable just like a single-table SELECT view."** No.

**31. "Indexes on a regular view are created just like table indexes."** No. Index the source tables or materialize the view.

**32. "Indexes on orders also serve as indexes on the materialized view."** No. The two relations maintain separate indexes.

**33. "Views always push every predicate past GROUP BY, LIMIT, or security barriers."** Not guaranteed.

**34. "SELECTing a matview automatically enforces source RLS at read time."** Never assume this. Access controls on materialized data must be enforced explicitly.

**35. "Adding a summary table keeps write latency zero."** No. UPSERTs and ledgers generate WAL, locks, and contention.

**36. "Storing updated_at on each group proves every prior event has been processed."** No. You need a watermark with well-defined semantics.

**37. "Rebuilding with DELETE + INSERT is online and free."** No. It incurs WAL, locks, and conflicts with running consumers.

**38. "Reporting by UTC day matches every tenant's local day."** False. An explicit timezone policy is required.

**39. "Dropping raw partitions automatically removes data from matviews/summaries."** No.

**40. "Benchmarking fastest SELECT alone is enough to pick an architecture."** No. Account for refresh/write cost, storage, freshness, and recovery.

---

## 29. Hands-On Exercises with Answers

### Exercise 1 — Choosing the Simplest Option

**Scenario:** 200k orders, 10 users viewing reports per hour, GROUP BY takes 40 ms, post-commit freshness required.

**Answer:** Start with a **view** or direct query; there is no compelling reason to materialize or build an event pipeline.

### Exercise 2 — Choosing a Materialized View

**Scenario:** 70 million orders, report read 300 times/minute, 20-minute staleness acceptable, refresh takes 3 minutes.

**Answer:** A materialized view is worth evaluating. Measure end-to-end freshness, locking, and actual refresh load.

### Exercise 3 — Choosing a Summary Table

**Scenario:** 500 million orders, report must reflect changes within seconds, full REFRESH takes 20 minutes.

**Answer:** Consider a delta/batch summary table with idempotency, watermarks, and reconciliation; evaluate hot-row contention.

### Exercise 4 — Report Grain

**Requirement:** paid revenue by tenant, day, and currency.

**Answer:** Grain is `(tenant_id,sales_day,currency)`; the grouping key, unique index, or PK must include all three if each row represents one group.

### Exercise 5 — Does a VIEW Store the Three Result Rows?

**Answer:** No. `v_daily_sales` stores only the SELECT definition; GROUP BY executes against the source when queried.

### Exercise 6 — Create the VIEW

**Answer:**

```sql
CREATE VIEW view_choice_lab.v_daily_sales AS
SELECT
    tenant_id,
    (ordered_at AT TIME ZONE 'UTC')::date AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(amount) AS gross_amount
FROM view_choice_lab.orders
WHERE status='paid'
GROUP BY tenant_id,
         (ordered_at AT TIME ZONE 'UTC')::date;
```

The lab already contains a view with this name; this is illustrative syntax, do not re-run it.

### Exercise 7 — How Does a New INSERT Affect Each Option?

**Scenario:** Insert a 30.00 paid order for tenant 1 on Nov 01 after bootstrapping all three options.

**Answer:** The view reads the updated source and shows **3/230.00**. The MV remains **2/200.00** before REFRESH. The summary remains **2/200.00** before applying the delta.

### Exercise 8 — What Does the Materialized View Need?

**Answer:**

```sql
REFRESH MATERIALIZED VIEW
    view_choice_lab.mv_daily_sales;
```

After refresh, results reflect the source snapshot read during the refresh.

### Exercise 9 — What Does CONCURRENTLY Change?

**Question:** Does `REFRESH ... CONCURRENTLY` mean scanning only recently changed orders?

**Answer:** No. It changes how results are replaced to better support concurrent readers in valid cases; the defining query still re-executes.

### Exercise 10 — Unique Index for CONCURRENTLY

**Answer:**

```sql
CREATE UNIQUE INDEX mv_daily_sales_tenant_day_uidx
ON view_choice_lab.mv_daily_sales (tenant_id, sales_day);
```

This index already exists in the lab; do not create a duplicate. The unique index must cover all rows and reference plain column names, not expressions or partial predicates.

### Exercise 11 — WITH NO DATA

**Question:** Can an unrefreshed `WITH NO DATA` matview be SELECTed normally like an empty table?

**Answer:** No. It is unpopulated and marked unscannable. A standard REFRESH is required first to populate it.

### Exercise 12 — First REFRESH

**Question:** Can you use `REFRESH CONCURRENTLY` immediately on an unpopulated matview?

**Answer:** No. Run the initial population using REFRESH without CONCURRENTLY.

### Exercise 13 — Does a Summary Table Auto-Sync?

**Answer:** No. It is a regular table requiring a job, transaction, trigger, or event pipeline.

### Exercise 14 — Upsert Delta

**Answer:**

```sql
INSERT INTO view_choice_lab.daily_sales_summary AS s
    (tenant_id,sales_day,paid_orders,gross_amount)
VALUES (1,DATE '2026-11-01',1,30.00)
ON CONFLICT (tenant_id,sales_day)
DO UPDATE SET
    paid_orders=s.paid_orders+EXCLUDED.paid_orders,
    gross_amount=s.gross_amount+EXCLUDED.gross_amount;
```

**Illustrative syntax only**; do not replay the same delta if already applied in section 11.

### Exercise 15 — Retrying a Delta

**Question:** If the `+30` UPSERT runs twice for the same order, are the numbers right?

**Answer:** No. It adds 60. You need change event IDs plus a ledger/deduplication mechanism or equivalent to guarantee an exactly-once effect.

### Exercise 16 — Why Isn't order_id Sufficient as change_id?

**Answer:** One order can emit paid, refunded, and corrected events. Each **change event** needs an independent ID/version both to deduplicate retries and to permit legitimate subsequent changes.

### Exercise 17 — Refund Delta

**Requirement:** A paid order of 80 becomes refunded; metrics count paid only.

**Answer:** Apply delta `paid_orders=-1`, `gross_amount=-80` to the old grain within a controlled transaction/state machine.

### Exercise 18 — Changing Date or Tenant

**Answer:** Reverse the old grain's contribution and add to the new grain based on post-edit values; never update only one side.

### Exercise 19 — Group with No Remaining Paid Orders

**Question:** The view omits the row while the summary retains a zero row. Can they always be treated as identical?

**Answer:** Not structurally in SQL. Standardize display/reconciliation rules using COALESCE or delete zeroed groups.

### Exercise 20 — Reconciling Missing Groups

**Answer:** Use `FULL OUTER JOIN` on `(tenant_id,sales_day)` between the canonical view and the summary, comparing `COUNT/SUM` with `COALESCE` per the zero/missing convention.

### Exercise 21 — Monthly AVG

**Question:** Should you take the AVG of daily AVGs?

**Answer:** Not if daily order counts vary. Compute `SUM(gross_amount)/NULLIF(SUM(paid_orders),0)`.

### Exercise 22 — Distinct Customers

**Question:** Does the sum of daily unique customers equal monthly unique customers?

**Answer:** Not if customers appear on multiple days. COUNT DISTINCT is non-additive in that case.

### Exercise 23 — JOIN Fanout

**Question:** An order has 3 items; how wrong is `SUM(order.amount)` after joining raw items?

**Answer:** If the amount repeats three times, SUM triples that order's contribution. Aggregate at the proper grain before or after JOINs.

### Exercise 24 — Indexing a View

**Question:** Can you run `CREATE INDEX ON v_daily_sales` like a regular table?

**Answer:** No. Regular views store no rows. Index the underlying source table appropriately or use a matview/summary table.

### Exercise 25 — Matview Indexes

**Question:** Does an index on `orders(tenant_id,ordered_at)` automatically act as an index on the matview?

**Answer:** No. Create separate indexes on the materialized view to speed up queries on materialized results.

### Exercise 26 — MVCC

**Question:** Does a view always see every new COMMIT inside an open `REPEATABLE READ` transaction?

**Answer:** No. The transaction retains its snapshot per isolation semantics; the fact that a view does not cache does not bypass MVCC.

### Exercise 27 — Long Refresh

**Question:** A job triggers every 10 minutes, but each refresh takes 25 minutes.

**Answer:** A 10-minute schedule cannot guarantee 10-minute freshness. Measure durations/waits and redesign.

### Exercise 28 — Tenant Isolation

**Question:** Can you grant SELECT on a multi-tenant matview to a tenant role and rely solely on client-passed `WHERE tenant_id`?

**Answer:** No. Design permissions, RLS, or restricted access interfaces so cross-tenant data cannot leak.

### Exercise 29 — Currencies

**Question:** Can you sum 100 USD and 100 VND into 200 currency units for a daily summary?

**Answer:** No. Add currency to the grain or apply controlled conversion/exchange-rate rules.

### Exercise 30 — Dropped Source Partitions

**Question:** Does dropping a source partition automatically remove historical data from a materialized view or summary table?

**Answer:** No. Materialized or separately copied data must be managed under its own retention rules.

### Exercise 31 — Source Snapshot vs. updated_at

**Question:** Does `summary.updated_at=09:00` prove all changes prior to 09:00 were applied?

**Answer:** No. It only records when that summary row was written, not a source offset/watermark.

### Exercise 32 — Making the Decision More Rigorous

**Requirement:** List at least three measurements to gather before migrating from a view to a matview.

**Answer:** (1) view query latency and call frequency, (2) REFRESH duration and resource load on realistic data, (3) freshness SLA along with observed staleness metrics. Also measure locks, index/storage overhead, replica lag, and failure behavior.

---

## 30. Architectural Decision Checklist

### Business Definition

1. **What does one report row represent?** Is the grain locked down?
2. **Are the measures accurate?** Paid/refunded/gross/net, VAT, discounts, and currency?
3. **Which timezone defines a day?** UTC or per-tenant?
4. **How should empty groups (`count=0`) appear?** No row or zero row?
5. **Do you need rollups to month/year?** Are AVGs and distinct counts additive?

### Query Analysis

6. **What is the current source query cost?** Safe `EXPLAIN (ANALYZE, BUFFERS)` on SELECTs.
7. **What is the read rate?** API/QPS, concurrency, peak traffic.
8. **What is the write/correction rate?** INSERT/UPDATE/DELETE/source events.
9. **How large is the GROUP BY result?** Row counts and storage.
10. **Do queries filter arbitrarily across many dimensions?** Are combinations practical to materialize?
11. **Are source and result indexes suitable?** Key order, partial indexes, statistics.

### Freshness and Consistency

12. **What staleness is acceptable?** Define SLAs in terms of commit/watermark times.
13. **Is a view fast enough when reading the latest snapshot?**
14. **Is matview refresh fast and predictable enough?**
15. **Does the summary have a reliable event source?** Outbox/CDC/transaction.
16. **Is idempotency enforced?** Event ID/version + deduplication.
17. **Are refunds, date edits, deletes, and late events handled?**
18. **Are reconciliation and rebuilds in place?**
19. **Are reliable watermarks and SLA-breach alerts configured?**

### Operations and Security

20. **Is the matview populated?** If using concurrent refresh, does it have a compliant unique index?
21. **Does refresh cause lock contention?** Are backlog and failure policies defined?
22. **Does the summary hit hot-row contention?** Is batching needed?
23. **Are index footprint, WAL, disk, and replication lag acceptable?**
24. **Is tenant security enforced?** Owner/invoker/RLS, grants on copied data?
25. **Retention?** Are copies in MVs, summaries, caches, and backups governed?
26. **Migration rollback?** Are versioned reports and fallbacks prepared?
27. **Are business results validated before/after switching?**
28. **Is total operational cost accounted for?** Not just SELECT latency.

---

## 31. Conclusion: Choose by Operational Contract, Not Technology Name

A **view** is a sound choice when you need a clean SQL interface, want reads tied to recent source snapshots, and the underlying query is already fast enough. Views do not store aggregates and do not eliminate scan, join, or aggregation work.

A **materialized view** makes sense when aggregated results are read heavily, source computation is expensive, and bounded staleness is acceptable. It can be indexed for very fast SELECTs; in return, you must schedule `REFRESH`, measure locks and resource spikes, monitor staleness, and remember that `CONCURRENTLY` **is not an incremental refresh**.

A **summary table** makes sense when large reports must reflect events rapidly or need custom maintenance rules. It supports delta `UPSERT`s along with watermarks and ledgers, but requires engineering **idempotency, corrections, old/new grain transitions, failure recovery, and reconciliation**. Fast SELECTs never justify inaccurate numbers.

### A Pragmatic Decision Heuristic

```text
                  Need an aggregated report?
                             |
                             v
         Is a direct query on source fast enough?
                   /                  \
                 Yes                   No
                 |                     |
                 v                     v
             Use VIEW        Is periodic refresh acceptable
                                  with a lag SLA?
                                  /          \
                                Yes           No
                                 |             |
                                 v             v
                          MATERIALIZED     SUMMARY TABLE
                              VIEW          / pipeline
                                 |             |
                          Measure refresh  Design deltas,
                          and staleness    idempotency, reconcile
```

This diagram is a **starting point**, not a rigid algorithm. Under diverse workloads, you can combine views, matviews, summary tables, and dedicated analytics systems while keeping metric definitions consistent.

**The single most important question before deciding:** "Up to **what point in time** must this report be accurate, with **what level of business precision**, and where is the system willing to pay the compute cost—**at read time, at refresh time, or at source write time**?"

### Official PostgreSQL Documentation

- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html).
- [Rules and Views](https://www.postgresql.org/docs/current/rules-views.html).
- [Updatable Views](https://www.postgresql.org/docs/current/rules-views.html#RULES-VIEWS-UPDATE).
- [CREATE MATERIALIZED VIEW](https://www.postgresql.org/docs/current/sql-creatematerializedview.html).
- [REFRESH MATERIALIZED VIEW](https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html).
- [Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html).
- [CREATE UNIQUE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- [INSERT ... ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html).
- [CREATE TABLE / Constraints](https://www.postgresql.org/docs/current/sql-createtable.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html).
- [Aggregate Functions](https://www.postgresql.org/docs/current/functions-aggregate.html).
