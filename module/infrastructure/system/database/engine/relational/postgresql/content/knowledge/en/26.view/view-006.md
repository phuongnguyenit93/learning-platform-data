# REFRESH MATERIALIZED VIEW and CONCURRENTLY Mode in PostgreSQL

A sales system processes millions of orders per day. A dashboard needs to show revenue by day and store; scanning the orders table and running `GROUP BY` every time someone opens the dashboard can be very expensive. PostgreSQL lets you persist the result of a query in a **materialized view**, and then read those stored results like a physical relation.

However, a materialized view **does not update automatically when source tables change**. Yesterday the system had 10,000 orders; today 1,000 more arrived. The report continues showing data from the prior calculation until you run:

```sql
REFRESH MATERIALIZED VIEW reporting.daily_revenue;
```

A new challenge arises: users are still reading the dashboard while the refresh runs. The standard command can block reads on the materialized view while replacing its data. PostgreSQL provides:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY reporting.daily_revenue;
```

to **allow normal SELECTs to continue reading the materialized view** while the refresh executes. Yet `CONCURRENTLY` is not an option you can slap onto any materialized view: it requires the view to already be populated and to have **a qualifying UNIQUE index covering all rows using column names only**. It also **does not turn refresh into free incremental maintenance**, does not allow multiple concurrent refreshes on the same view, and does not make newly committed data appear instantaneously.

This lesson explains the exact mechanics, syntax, prerequisites for `CONCURRENTLY`, differences in locking and read consistency, real resource costs, safe operational practices, and runnable SQL examples.

## 1. Learning Objectives

Upon completing this lesson, you will be able to:

1. Distinguish `VIEW`, `MATERIALIZED VIEW`, and self-maintained summary tables.
2. Explain why materialized view data becomes *stale* and when refreshes are required.
3. Read the syntax `REFRESH MATERIALIZED VIEW [CONCURRENTLY] ... [WITH [NO] DATA]`.
4. Describe the differences between standard refresh and `CONCURRENTLY` regarding SELECTs, locks, resources, and data visibility timing.
5. List the exact **populated** and **qualifying UNIQUE index** requirements to use `CONCURRENTLY`.
6. Explain why partial or expression-based UNIQUE indexes fail concurrent refresh requirements.
7. Initialize a materialized view `WITH NO DATA`, perform initial population, build indexes, and transition to concurrent refreshes.
8. Recognize risks of duplicate rows / non-unique logical keys, source changes between refreshes, and access permissions.
9. Use `pg_matviews`, `pg_indexes`, `pg_stat_activity`, and `pg_locks` to inspect state, indexes, and running refreshes.
10. Design refresh schedules, monitor freshness, handle failed refreshes, and choose alternatives when real-time data is required.

## 2. Regular VIEW, MATERIALIZED VIEW, and Regular Tables

### 2.1. Regular VIEWs Store Definitions, Not Results by Default

```sql
CREATE VIEW reporting.daily_revenue_live AS
SELECT tenant_id, sale_date, SUM(amount) AS revenue
FROM sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date;
```

When `SELECT`ing through a regular view, PostgreSQL incorporates the view definition into the query plan and reads source data under MVCC rules at query time. A regular view **has no independent stored result copy** to refresh.

### 2.2. MATERIALIZED VIEWs Store Results

```sql
CREATE MATERIALIZED VIEW reporting.daily_revenue AS
SELECT tenant_id, sale_date, SUM(amount) AS revenue
FROM sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date;
```

A materialized view stores the query's output in physical storage, supports indexes on output columns, tracks statistics, and is scanned like a table on SELECT. PostgreSQL retains the defining query to recompute data on refresh.

When `sales` changes, stored results **do not update automatically**. `REFRESH MATERIALIZED VIEW` re-runs the query to produce a fresh result set.

### 2.3. Self-Maintained Summary Tables Are a Different Choice

A `reporting.daily_revenue_cache` table maintained by the application inside the same transaction, a trigger, or an event consumer can update incrementally per change. That is **not** automatic incremental maintenance built into PostgreSQL materialized views.

Standard materialized views fit well when an update lag window is acceptable. If every transaction must appear immediately in reports with strict consistency, evaluate transactional summary tables or direct source queries.

### 2.4. Quick Comparison

| Characteristic | VIEW | MATERIALIZED VIEW | App-Maintained Summary Table |
| --- | --- | --- | --- |
| Pre-stores result set? | No, normally. | Yes. | Yes. |
| Automatically reflects source edits? | At query time, per SQL snapshot. | No; requires REFRESH. | Depends on sync logic. |
| Dedicated indexes on output? | No; indexes live on source tables. | Can create indexes. | Can create indexes. |
| Must manage refreshes? | No. | Yes. | Must manage update pipeline. |
| Can become stale? | Not like a materialized snapshot cache; still follows query MVCC. | Yes, since last refresh. | Depends on mechanism. |
| Best fit | SQL abstraction, live queries. | Reports/aggregates tolerating lag. | Metrics needing transaction/event-level updates or custom logic. |

## 3. REFRESH MATERIALIZED VIEW Syntax

```sql
REFRESH MATERIALIZED VIEW [ CONCURRENTLY ] view_name
    [ WITH [ NO ] DATA ];
```

Where:

- **`view_name`**: an existing materialized view; schema-qualify to avoid `search_path` ambiguity.
- **Without `CONCURRENTLY`**: standard refresh, which can block SELECTs reading the view while refreshing.
- **`CONCURRENTLY`**: refreshes without blocking normal SELECTs reading the view; requires a populated view and a qualifying UNIQUE index.
- **`WITH DATA`**: executes the defining query and updates stored data; this is the **default**.
- **`WITH NO DATA`**: discards stored data and leaves the view **unscannable** until populated again.

Examples:

```sql
-- Standard refresh; implies WITH DATA:
REFRESH MATERIALIZED VIEW reporting.daily_revenue;

-- Can write explicitly:
REFRESH MATERIALIZED VIEW reporting.daily_revenue WITH DATA;

-- Allows SELECTs to continue during update:
REFRESH MATERIALIZED VIEW CONCURRENTLY
    reporting.daily_revenue;

-- Discards stored data and makes view unscannable:
REFRESH MATERIALIZED VIEW reporting.daily_revenue
    WITH NO DATA;
```

**Invalid:**

```sql
-- These two options cannot be combined:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     reporting.daily_revenue WITH NO DATA;
```

`CONCURRENTLY` only makes sense when replacing an existing readable dataset while readers continue querying the old version. `WITH NO DATA` leaves the view unscannable, so it cannot be combined with concurrent refresh.

### 3.1. REFRESH Does Not Alter the SELECT Definition

If the materialized view was created with `SELECT ... FROM sales WHERE status='paid'`, REFRESH **does not modify** the WHERE clause, column layout, or GROUP BY. It reuses the stored definition.

Changing the query structure substantially requires a migration/recreation strategy, not passing a new SELECT to REFRESH.

### 3.2. REFRESH Is On-Demand

PostgreSQL **does not auto-schedule REFRESH** merely because a materialized view exists. Triggers, external job schedulers, `pg_cron` (if installed), or ETL orchestrators sit outside the default behavior of the command.

### 3.3. No WHERE Parameter in REFRESH Syntax

```sql
-- No such standard syntax exists:
-- REFRESH MATERIALIZED VIEW reporting.daily_revenue
-- WHERE tenant_id = 7;
```

REFRESH recomputes **the entire view's defining query**, without syntax to refresh just one tenant or one month. If key-scoped or incremental updates are required, choose a different architecture.

## 4. What Does a Stale Materialized View Mean?

Suppose source data changes across three timestamps:

```text
T0  (09:00)  orders has 100 paid rows
             REFRESH daily_revenue completes
             MV currently holds revenue from 100 rows

T1  (09:05)  20 new paid orders COMMIT to orders
             MV still reflects only the T0 REFRESH snapshot

T2  (09:10)  Second REFRESH completes
             MV reflects source data observed at the new refresh
```

Between T1 and T2:

```sql
SELECT SUM(amount)
FROM sales
WHERE status = 'paid';
```

differs from:

```sql
SELECT SUM(revenue)
FROM reporting.daily_revenue;
```

This is **not a database consistency bug**. It is the expected outcome of using a scheduled materialized cache.

### 4.1. Freshness SLA

Before adopting a materialized view, answer:

- Does the report tolerate 30 seconds, 5 minutes, 1 hour, or 1 day of lag?
- How long does REFRESH actually take?
- Can late-arriving source batches occur?
- If refresh fails, how long may the system serve stale data?
- Should the UI display "Last updated at ..."?

If account balances must be exact immediately after COMMIT, periodic refresh is normally unsuitable.

### 4.2. Never Equate Start Time with Finish Time

Suppose a refresh starts at 09:00, runs for 4 minutes, and finishes at 09:04. Source rows committed at 09:03 are **not guaranteed to appear in that refresh** if the query's snapshot was captured before that commit. Thus "refresh succeeded at 09:04" **does not mean** all source commits up to 09:04 are included.

Freshness designs should track **source cutoffs/watermarks** when needed. A `refresh_finished_at` timestamp only states when the job finished, not a business completeness boundary.

## 5. How Does Standard REFRESH Work?

```sql
REFRESH MATERIALIZED VIEW reporting.daily_revenue;
```

PostgreSQL runs the materialized view's stored query, builds the result set, and swaps/replaces the materialized data. During this operation, standard mode acquires an **ACCESS EXCLUSIVE** lock on the materialized view itself.

### 5.1. What Impact Does ACCESS EXCLUSIVE Have?

`ACCESS EXCLUSIVE` conflicts with the `ACCESS SHARE` lock normal SELECTs need on the relation, so a SELECT targeting that materialized view while the lock is held **blocks waiting**.

```text
Session A                             Session B
---------                             ---------
REFRESH MATERIALIZED VIEW ...
  holds ACCESS EXCLUSIVE lock
                                      SELECT * FROM materialized_view;
                                      -> may wait on A's lock
COMMIT / command finishes
                                      -> SELECT proceeds
```

Source tables retain their own read locks/snapshots during query execution. `ACCESS EXCLUSIVE` on the materialized view does not lock all source tables in exclusive mode.

### 5.2. Why Is Standard Mode Still Useful?

Standard refresh can:

- Consume fewer resources and finish faster when most rows change.
- Require simpler setup—no UNIQUE index needed.
- Fit reports refreshed during maintenance windows or off-hours with zero readers.
- Perform initial population when a materialized view is unpopulated.

**Never assume CONCURRENTLY is always faster.** Its main purpose is **avoiding blocking SELECTs on the view**, not guaranteeing shorter REFRESH runtime.

### 5.3. Transactions and Atomicity

REFRESH is transactional. Readers never observe a half-populated table as the committed outcome of a refresh. In standard mode, SELECTs wait for the lock; after commit, queries with new snapshots see the new dataset.

If a refresh fails and rolls back, no partial new rows are published.

### 5.4. Locks Are Held Until Transaction End

If REFRESH runs inside an explicit transaction:

```sql
BEGIN;
REFRESH MATERIALIZED VIEW reporting.daily_revenue;
-- Transaction not yet COMMITted...
```

locks acquired by REFRESH remain held until the transaction ends. Never leave a session running REFRESH **idle in transaction**; even after computation finishes, readers stay blocked until COMMIT.

## 6. How Does REFRESH ... CONCURRENTLY Differ?

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    reporting.daily_revenue;
```

This option lets normal `SELECT` queries keep reading the materialized view while REFRESH performs the update. Under PostgreSQL's locking model, concurrent refresh acquires an **EXCLUSIVE** lock on the materialized view—which is compatible with `ACCESS SHARE` from normal SELECTs—though it **does not** mean zero locks exist.

### 6.1. Reading During Refresh Diagram

```text
             Populated materialized view
                          |
             currently published data
                          |
            +-------------+--------------+
            |                            |
            v                            v
      Session A                      Session B
      REFRESH ...                    SELECT ...
      CONCURRENTLY                   reads MV per snapshot
            |                            |
            |  builds new results        |
            |  and reconciles            |
            |                            |
            +------ COMMIT --------------+
                          |
            new SELECTs, with appropriate
            snapshots, see updated results
```

### 6.2. Which Data Do Readers See?

While `REFRESH CONCURRENTLY` runs, SELECTs continue reading the **materialized data version visible to their MVCC snapshot**. Once the refresh commits, new queries with fresh snapshots see the updated version. Older snapshot transactions continue reading the old version per MVCC.

**There is no automatic "live update":** when source tables receive a new row, the materialized view remains stale until a refresh commits.

### 6.3. Why Is a UNIQUE Index Required?

For concurrent refresh, PostgreSQL needs a reliable key to diff the old and new result sets and apply inserts/updates/deletes while concurrent readers remain active. A **qualifying UNIQUE index on the output columns** is mandatory for this reconciliation.

Having a `PRIMARY KEY` on the source table is not enough: the materialized view itself must have **its own qualifying UNIQUE index**.

### 6.4. Concurrent Refresh Is Not "Fetch Only New Rows"

In standard PostgreSQL, `REFRESH CONCURRENTLY` **still runs the full defining query to generate the new result set**, then diffs and applies changes. It **does not read WAL to simply add 10 new orders** to revenue or maintain incremental aggregates automatically.

If the view aggregates 500 million source rows, recomputation cost remains high even if only a few output rows changed.

### 6.5. Only One REFRESH on the Same View at a Time

Even with `CONCURRENTLY`, PostgreSQL allows only **one REFRESH at a time on a given materialized view**. Schedulers must not fire overlapping refreshes thinking `CONCURRENTLY` runs multiple refreshes in parallel.

Different materialized views can refresh concurrently with one another, though they still share CPU, I/O, WAL, source table locks, and system capacity.

### 6.6. Comparison Table

| Aspect | Standard REFRESH | REFRESH CONCURRENTLY |
| --- | --- | --- |
| Command | `REFRESH MATERIALIZED VIEW v` | `REFRESH MATERIALIZED VIEW CONCURRENTLY v` |
| Concurrent SELECT reads | Blocked by lock | Normal SELECTs can continue reading |
| Lock on materialized view | ACCESS EXCLUSIVE | EXCLUSIVE |
| Requires populated view | No | **Yes** |
| Requires qualifying UNIQUE index | No | **Yes** |
| Combines with WITH NO DATA | Yes | **No** |
| Speed | Often faster when most rows change | Has diff/reconcile overhead; helps when few rows change |
| Automatic incremental maintenance? | No | No |
| Allows two simultaneous REFRESHes on same view? | No | No |
| Guarantees real-time source reads? | No | No |

## 7. Two Mandatory Prerequisites for CONCURRENTLY

This is the most critical operational requirement.

### 7.1. Prerequisite 1: The View Must Already Be Populated

A materialized view created with:

```sql
CREATE MATERIALIZED VIEW some_view AS
SELECT ...
WITH NO DATA;
```

is **unpopulated** and cannot be queried normally with `SELECT`. The initial REFRESH must be:

```sql
REFRESH MATERIALIZED VIEW some_view WITH DATA;
```

Only once populated can you use `REFRESH ... CONCURRENTLY` (provided index requirements are met).

**Note:** populated does not require **at least one row**. A materialized view whose query returns **0 rows** is still populated/scannable after `REFRESH ... WITH DATA`. The prerequisite checks **populated state**, not row count > 0.

### 7.2. Prerequisite 2: A Qualifying UNIQUE Index on the View

Suppose a materialized view returns one row per `(tenant_id, sale_date)` pair:

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_date
ON reporting.daily_revenue (tenant_id, sale_date);
```

This index qualifies if:

- It is created on the **materialized view itself**.
- It is **UNIQUE** and valid.
- Its index keys are **column names** of the materialized view, not expressions.
- It covers **all rows** of the materialized view, with no `WHERE` clause (not a partial index).

### 7.3. Expression-Only UNIQUE Indexes Are Rejected

Not eligible for `CONCURRENTLY`:

```sql
-- Expression index, does not satisfy the requirement on its own:
CREATE UNIQUE INDEX ux_summary_lower_region
ON reporting.some_summary ((lower(region)));
```

This index may help queries, but it is **not a plain-column UNIQUE index** required by `REFRESH CONCURRENTLY`.

### 7.4. Partial UNIQUE Indexes Are Also Insufficient

```sql
-- Covers only a subset of rows, does not qualify:
CREATE UNIQUE INDEX ux_summary_current
ON reporting.some_summary (tenant_id, sale_date)
WHERE is_current;
```

Rows failing the `WHERE` predicate are uncovered by this index, failing the **full-coverage** requirement.

### 7.5. Non-Unique Indexes Are Insufficient

```sql
-- Does not satisfy the requirement on its own:
CREATE INDEX idx_summary_tenant_date
ON reporting.some_summary (tenant_id, sale_date);
```

Helps SELECTs, but does not enforce row identity for refresh reconciliation. With only this index, `REFRESH ... CONCURRENTLY` is rejected.

### 7.6. A UNIQUE Index on the Source Table Is Insufficient

```sql
-- Table sales having PRIMARY KEY(order_id)
-- does not mean the materialized view has a UNIQUE index.
```

A materialized view is a separate relation whose GROUP BY/JOINs can change uniqueness. You must define and verify the UNIQUE index on the **view's own output columns**.

### 7.7. Multi-Column Keys Are Supported

A UNIQUE index can span multiple columns:

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_date
ON reporting.daily_revenue (tenant_id, sale_date);
```

This is the common pattern because summary rows are identified by a **composite grouping key**. A single column like `sale_date` is not unique across multiple tenants.

### 7.8. Creating an Index Does Not Fix a Broken View Query

If the defining query generates two rows with the same `(tenant_id,sale_date)`, `CREATE UNIQUE INDEX` fails. Never "fix" it by slapping `DISTINCT` onto the query blindly if that alters revenue totals.

Instead, identify the true grouping/business key, fix JOIN fan-out duplicating rows, or redesign the aggregation.

## 8. Complete Practice Dataset

All SQL in this section uses `mv_refresh_lab`; run only in a **practice database**. You do not need the hypothetical `sales` table or `reporting` schema from earlier conceptual snippets.

### 8.1. Create Schema and Source Table

```sql
CREATE SCHEMA IF NOT EXISTS mv_refresh_lab;

CREATE TABLE mv_refresh_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    tenant_id integer NOT NULL,
    sale_date date NOT NULL,
    amount numeric(12, 2) NOT NULL
        CHECK (amount >= 0),
    status text NOT NULL
        CHECK (status IN ('paid', 'pending', 'cancelled'))
);
```

This design is intentionally simple: `sale_date` is a `date` independent of session timezone, `amount` is numeric, and only `status='paid'` rows count toward revenue.

### 8.2. Insert Sample Data

```sql
INSERT INTO mv_refresh_lab.sales
    (tenant_id, sale_date, amount, status)
VALUES
    (1, DATE '2026-11-01', 100.00, 'paid'),
    (1, DATE '2026-11-01',  50.00, 'paid'),
    (1, DATE '2026-11-01', 300.00, 'cancelled'),
    (1, DATE '2026-11-02',  75.00, 'paid'),
    (2, DATE '2026-11-01', 200.00, 'paid'),
    (2, DATE '2026-11-02',  30.00, 'pending');
```

Run once on an empty table. Re-running inserts duplicate rows because `sale_id` is auto-generated rather than throwing duplicate key errors—which shifts exercise numbers. Reset the lab schema or database if starting over.

### 8.3. Inspect Source Data

```sql
SELECT
    tenant_id,
    sale_date,
    SUM(amount) AS revenue,
    COUNT(*) AS paid_orders
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
ORDER BY tenant_id, sale_date;
```

Result:

| tenant_id | sale_date | revenue | paid_orders |
| ---: | --- | ---: | ---: |
| 1 | 2026-11-01 | 150.00 | 2 |
| 1 | 2026-11-02 | 75.00 | 1 |
| 2 | 2026-11-01 | 200.00 | 1 |

`pending` and `cancelled` rows are **excluded** from these totals.

### 8.4. Create a Populated Materialized View

```sql
CREATE MATERIALIZED VIEW mv_refresh_lab.daily_revenue AS
SELECT
    tenant_id,
    sale_date,
    SUM(amount)::numeric(14, 2) AS revenue,
    COUNT(*)::bigint AS paid_orders
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
WITH DATA;
```

`WITH DATA` is optional since populating on creation is the default. We write it explicitly to contrast with `WITH NO DATA`.

### 8.5. SELECT Materialized Data

```sql
SELECT tenant_id, sale_date, revenue, paid_orders
FROM mv_refresh_lab.daily_revenue
ORDER BY tenant_id, sale_date;
```

Matches Section 8.3's aggregate table until source changes occur.

### 8.6. Create the Qualifying UNIQUE Index for CONCURRENTLY

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_day
ON mv_refresh_lab.daily_revenue
    (tenant_id, sale_date);
```

Each `(tenant_id,sale_date)` has one row because the query groups by those two columns, making it the right logical key in this lab.

This index serves **two purposes**:

1. Enforces uniqueness of the grouping key in the materialized view.
2. Enables `REFRESH MATERIALIZED VIEW CONCURRENTLY` because it uses column names only and covers all rows.

It may also assist SELECTs filtering by tenant/date, though PostgreSQL chooses index vs. sequential scans based on cost.

### 8.7. Verify Populated State

```sql
SELECT
    schemaname,
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
  AND matviewname = 'daily_revenue';
```

After creating `WITH DATA` and adding the index, expect `ispopulated=true` and `hasindexes=true`. **`hasindexes=true` alone does not prove a qualifying UNIQUE index exists**, only that at least one index exists; verify exact index definitions later.

### 8.8. Source Data Changes, View Stays Unchanged

Insert new transactions:

```sql
INSERT INTO mv_refresh_lab.sales
    (tenant_id, sale_date, amount, status)
VALUES
    (1, DATE '2026-11-01',  25.00, 'paid'),
    (2, DATE '2026-11-02', 110.00, 'paid');
```

Both new rows commit immediately under autocommit. Query the source table:

```sql
SELECT
    tenant_id,
    sale_date,
    SUM(amount) AS current_revenue
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
ORDER BY tenant_id, sale_date;
```

Two key changes appear:

- Tenant 1, Nov 1: revenue increases from 150 to **175**.
- Tenant 2, Nov 2: a new group appears with revenue **110**.

Yet:

```sql
SELECT tenant_id, sale_date, revenue
FROM mv_refresh_lab.daily_revenue
ORDER BY tenant_id, sale_date;
```

still displays the **old** numbers until refreshed.

### 8.9. Standard Refresh

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue;

SELECT tenant_id, sale_date, revenue, paid_orders
FROM mv_refresh_lab.daily_revenue
ORDER BY tenant_id, sale_date;
```

Expected:

| tenant_id | sale_date | revenue | paid_orders |
| ---: | --- | ---: | ---: |
| 1 | 2026-11-01 | 175.00 | 3 |
| 1 | 2026-11-02 | 75.00 | 1 |
| 2 | 2026-11-01 | 200.00 | 1 |
| 2 | 2026-11-02 | 110.00 | 1 |

This is a snapshot of source data as of the refresh, not a continuously synced view afterward.

### 8.10. Update Source Then Refresh CONCURRENTLY

Recall tenant 2 on Nov 2 initially had a `pending` order with `amount=30`. Mark it `paid`:

```sql
UPDATE mv_refresh_lab.sales
SET status = 'paid'
WHERE tenant_id = 2
  AND sale_date = DATE '2026-11-02'
  AND amount = 30.00
  AND status = 'pending';
```

Before REFRESH, the materialized view still reports 110 for tenant 2 on Nov 2. After:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;

SELECT tenant_id, sale_date, revenue, paid_orders
FROM mv_refresh_lab.daily_revenue
WHERE tenant_id = 2
  AND sale_date = DATE '2026-11-02';
```

Output updates to **revenue = 140.00** and **paid_orders = 2**.

### 8.11. When a Group Disappears

If every paid row for a tenant/date pair is marked `cancelled`, the defining query no longer emits that group. The next refresh deletes that row from the materialized view rather than leaving it at revenue 0 (unless the defining query was explicitly built to retain empty groups).

Test inside a rolled-back transaction so lab data stays intact:

```sql
BEGIN;

UPDATE mv_refresh_lab.sales
SET status = 'cancelled'
WHERE tenant_id = 1
  AND sale_date = DATE '2026-11-02'
  AND status = 'paid';

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;

SELECT *
FROM mv_refresh_lab.daily_revenue
WHERE tenant_id = 1
  AND sale_date = DATE '2026-11-02';

ROLLBACK;
```

Inside the transaction, SELECT after refresh returns 0 rows for that group. After `ROLLBACK`, both the source edit and the refresh in the same transaction undo cleanly. Never hold long transactions like this in production unnecessarily; this illustrates atomicity semantics.

## 9. WITH NO DATA and the Populated/Unscannable Lifecycle

Materialized views have two distinct states:

```text
               CREATE MATERIALIZED VIEW ...
                          |
               +----------+-----------+
               |                      |
            WITH DATA              WITH NO DATA
               |                      |
               v                      v
            populated              unscannable
               |                      |
               |               REFRESH ... WITH DATA
               |                      |
               +----------------------+
                          |
                          v
                       populated
                          |
             REFRESH ... WITH NO DATA
                          |
                          v
                      unscannable
```

### 9.1. Creating an Unpopulated View

In the lab, create a separate materialized view so `daily_revenue` stays untouched:

```sql
CREATE MATERIALIZED VIEW mv_refresh_lab.daily_revenue_later AS
SELECT
    tenant_id,
    sale_date,
    SUM(amount)::numeric(14, 2) AS revenue
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date
WITH NO DATA;
```

Check:

```sql
SELECT matviewname, ispopulated
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
  AND matviewname = 'daily_revenue_later';
```

`ispopulated=false`. **You cannot SELECT data from this view** while it is unscannable.

### 9.2. First CONCURRENTLY Command Is Rejected

```sql
-- Expected to fail because view is not populated:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     mv_refresh_lab.daily_revenue_later;
```

Even if you created a UNIQUE index on the view beforehand, the unscannable state rejects `CONCURRENTLY`.

### 9.3. Initial Population via Standard REFRESH

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH DATA;

SELECT *
FROM mv_refresh_lab.daily_revenue_later
ORDER BY tenant_id, sale_date;
```

Now the view is **scannable**. It can legitimately hold 0 rows if the source query returns none and still be marked populated.

### 9.4. Create the UNIQUE Index, Then Use CONCURRENTLY

```sql
CREATE UNIQUE INDEX ux_daily_revenue_later
ON mv_refresh_lab.daily_revenue_later
    (tenant_id, sale_date);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue_later;
```

Proper bootstrap sequence:

```text
CREATE MV WITH NO DATA
        |
        v
REFRESH MV WITH DATA     (not CONCURRENTLY)
        |
        v
CREATE UNIQUE INDEX     (on columns, all rows)
        |
        v
REFRESH MV CONCURRENTLY (subsequent runs)
```

You can also create the materialized view `WITH DATA` right away and then create the UNIQUE index. Choose based on initial population runtime and deployment plan.

### 9.5. WITH NO DATA on an Already Populated View

```sql
-- Separate test on auxiliary view to avoid losing main lab data:
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH NO DATA;
```

Afterward `ispopulated=false`, making the view unscannable; SELECTs raise errors instead of returning 0 rows. An existing UNIQUE index **does not keep the view scannable**.

To restore:

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH DATA;
```

Once populated again with its valid UNIQUE index, `CONCURRENTLY` works on future runs.

### 9.6. Do Not Use WITH NO DATA to "Temporarily Show an Empty Report"

`WITH NO DATA` does not make a materialized view a valid **0-row queryable relation**. It makes it **unscannable**, causing API reads to error. If business workflows need an empty report state, use a different mechanism.

## 10. Inspecting UNIQUE Indexes via Catalogs

An index existing does not mean it qualifies for `CONCURRENTLY`. Inspect via:

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'mv_refresh_lab'
  AND tablename = 'daily_revenue'
ORDER BY indexname;
```

Expected output:

```text
CREATE UNIQUE INDEX ux_daily_revenue_tenant_day
ON mv_refresh_lab.daily_revenue
USING btree (tenant_id, sale_date)
```

Formatting of `pg_get_indexdef`/`indexdef` varies slightly by major version, but the key elements are **UNIQUE** over the two plain column names with no `WHERE`.

### 10.1. Inspecting Catalog Attributes

```sql
SELECT
    idx.relname AS index_name,
    i.indisunique AS is_unique,
    i.indisvalid AS is_valid,
    i.indpred IS NULL AS covers_all_rows,
    i.indexprs IS NULL AS only_column_keys,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx
    ON idx.oid = i.indexrelid
WHERE i.indrelid =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY idx.relname;
```

For `ux_daily_revenue_tenant_day`, `is_unique`, `is_valid`, `covers_all_rows`, and `only_column_keys` are all TRUE.

This inspection query **helps identify** candidate indexes; applications should not blindly conclude "CONCURRENTLY is guaranteed to succeed" from four booleans alone, since populated state, data uniqueness, privileges, and resource/lock constraints also apply.

### 10.2. Expression UNIQUE Indexes Can Still Serve Other Purposes

Illustrative example:

```sql
-- This index is not an eligible UNIQUE index for concurrent refresh:
-- CREATE UNIQUE INDEX ux_lower_name
-- ON some_materialized_view ((lower(name)));
```

It can enforce expression uniqueness and optimize case-insensitive SELECTs, yet cannot satisfy `REFRESH CONCURRENTLY`.

### 10.3. Partial UNIQUE Indexes Do Not Cover All Rows

```sql
-- Not eligible:
-- CREATE UNIQUE INDEX ux_active
-- ON some_materialized_view (tenant_id, sale_date)
-- WHERE active;
```

If the view query already filters to `active`, the index does not need `WHERE active` for concurrent refresh. Creating an **unfiltered UNIQUE index** over the actual materialized view columns is the right approach.

### 10.4. NULLs in UNIQUE Keys

By default in PostgreSQL, UNIQUE indexes treat multiple SQL `NULL` values as distinct. Starting in PostgreSQL 15, `NULLS NOT DISTINCT` changes how NULLs are handled for uniqueness.

For aggregated materialized views, if a logical key allows NULLs, verify **grouping and uniqueness semantics carefully**. PostgreSQL has strict internal rules for concurrent refresh row matching; keeping grouping keys **`NOT NULL` and deterministic** avoids edge cases.

In our lab, both `tenant_id` and `sale_date` are `NOT NULL`, avoiding this issue.

### 10.5. Never Use "Row Order" as a Key

Because materialized views do not guarantee stable row order across refreshes, never generate a synthetic key via `row_number() OVER (...)` and treat it as an **immutable ID** across runs. When source data shifts, row numbers shift too, causing unnecessary diff churn or breaking downstream joins.

Always choose keys based on stable business/grouping identity like `(tenant_id,sale_date)`.

## 11. Observing Locks Across Two Sessions

To see how standard REFRESH blocks SELECTs, open **two separate psql sessions to the same lab database**. Never hold sleep/lock transactions in production. This test illustrates lock behavior because a 4-row view otherwise refreshes too fast to observe directly.

### 11.1. Setup in Session A

```sql
BEGIN;

REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue;

-- Lab only: hold transaction open a few seconds after refresh.
SELECT pg_sleep(8);

COMMIT;
```

`REFRESH` acquires ACCESS EXCLUSIVE on the materialized view and keeps it until transaction end. While Session A sleeps before COMMIT, run in Session B:

### 11.2. Session B During Session A's Standard Refresh

```sql
SET lock_timeout = '2s';

SELECT COUNT(*)
FROM mv_refresh_lab.daily_revenue;

RESET lock_timeout;
```

When SELECT starts while Session A holds the lock, it fails after waiting 2 seconds for the lock. This is the expected contention behavior, not a corrupted materialized view.

**If you miss the 8-second window**, SELECT succeeds normally. Re-run in a controlled lab with both sessions ready; never use infinite `pg_sleep` or test in production.

### 11.3. Retrying with CONCURRENTLY in Session A

```sql
BEGIN;

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;

-- Lab only:
SELECT pg_sleep(8);

COMMIT;
```

While Session A holds its EXCLUSIVE lock, Session B runs:

```sql
SET lock_timeout = '2s';

SELECT COUNT(*)
FROM mv_refresh_lab.daily_revenue;

RESET lock_timeout;
```

Normal SELECT acquires ACCESS SHARE, which is compatible with EXCLUSIVE; it **completes immediately** even before Session A commits. This **does not** mean Session B sees uncommitted row-by-row edits; it reads per its MVCC snapshot.

### 11.4. Remember the Limits of This Demo

- Other locks, DDL statements, or saturated hardware can still stall SELECTs even with CONCURRENTLY.
- `CONCURRENTLY` protects SELECT availability on the **materialized view**, not eliminating all lock contention on source tables.
- Long-running transactions retain old tuple versions, adding VACUUM pressure.
- Forgetting to COMMIT/ROLLBACK Session A leaves locks held; always close practice transactions cleanly.

### 11.5. Observing Waiting Sessions via SQL

From an authorized monitoring connection:

```sql
SELECT
    a.pid,
    a.state,
    a.wait_event_type,
    a.wait_event,
    a.query_start,
    a.query
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.query_start NULLS LAST;
```

When Session B waits on a lock, `wait_event_type` shows `Lock`; specific `wait_event` and `state` depend on execution. Never expose raw `query` text on public dashboards if queries contain sensitive literals.

When diagnosing blocked queries, run:

```sql
SELECT
    a.pid AS waiting_pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

`pg_blocking_pids` identifies blockers, though not every slow query is caused by table locks.

## 12. Inspecting Materialized View Lock Modes

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted,
    a.state,
    a.wait_event_type,
    a.wait_event
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a
    ON a.pid = l.pid
WHERE l.relation =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY l.granted, l.mode, l.pid;
```

### 12.1. Lock Modes to Know

| Command | Lock on Materialized View | Typical Impact |
| --- | --- | --- |
| `SELECT ... FROM matview` | ACCESS SHARE | Compatible with EXCLUSIVE; blocked by ACCESS EXCLUSIVE. |
| `REFRESH MATERIALIZED VIEW` | ACCESS EXCLUSIVE | Blocks SELECTs on the view. |
| `REFRESH MATERIALIZED VIEW CONCURRENTLY` | EXCLUSIVE | Permits normal SELECTs; blocks conflicting operations. |

Locks remain held until transaction end. A `SELECT` in Session B may wait not only while REFRESH computes, but also if Session A finished computing **yet hasn't COMMITted**.

### 12.2. Locks on Source Tables

The materialized view's defining query reads `mv_refresh_lab.sales` and acquires read locks/snapshots on source relations. Consequently, DDL on source tables can still block behind a refresh even though `CONCURRENTLY` keeps view readers unblocked.

Never interpret "CONCURRENTLY" as lock-free or zero impact on source workloads.

### 12.3. Never Kill a Session Solely Because You See ExclusiveLock

`ExclusiveLock` is completely normal during concurrent refresh. Canceling a refresh rolls back large amounts of work and adds I/O strain. Always check elapsed time, blockers, load, and runbooks before canceling or terminating backends.

## 13. MVCC and Data Consistency During REFRESH

A materialized view can lag in **time**, yet a single refresh must still compute a transactionally coherent result set.

### 13.1. Consistent Snapshot When Reading Source Tables

When PostgreSQL runs the defining query for a refresh, it uses the statement/transaction's MVCC snapshot. It never reads half of an uncommitted source transaction and mixes it with other data.

Suppose a source transaction runs:

```sql
BEGIN;
INSERT INTO mv_refresh_lab.sales
    (tenant_id, sale_date, amount, status)
VALUES
    (9, DATE '2026-11-07', 300, 'paid');
-- Not yet COMMITted.
```

A refresh in another session cannot see this uncommitted row. If the source commits after the refresh's snapshot was established, the row waits until the next refresh.

### 13.2. Why "Completed" Does Not Mean "Fresh Through Completion Time"?

```text
09:00:00  Refresh query takes source snapshot S
09:00:01  Source receives COMMIT of new order
09:00:10  REFRESH completes and COMMITs view
```

The order committed after snapshot S **is absent** from the materialized view. Therefore, when reporting freshness, distinguish:

- Job start time.
- Source snapshot / cutoff time.
- Job completion time.
- Business watermark: confirmed processed event timestamp/LSN/sequence, if tracked.

### 13.3. During CONCURRENTLY, Do Readers See the Old or New Snapshot?

While `REFRESH CONCURRENTLY` is running and uncommitted, SELECTs in other sessions **never see uncommitted changes**. After commit, subsequent statements with fresh snapshots read the new results. Transactions under `REPEATABLE READ` with an earlier snapshot continue seeing the pre-refresh version per MVCC.

Never build applications assuming "every SELECT across every transaction flips to the new version at the exact same millisecond regardless of snapshot."

### 13.4. No Automatic Cross-View Real-Time Synchronization

If you have:

```text
reporting.revenue_by_day
reporting.refunds_by_day
reporting.net_revenue_by_day
```

and a scheduler refreshes the three views at different times, dashboards querying all three can read **three different points in time**. `CONCURRENTLY` only manages single-view concurrency with readers; it does not synchronize snapshots across independent refreshes.

When business reports require synchronized snapshots across multiple output tables, design explicit publish/version cutovers or transactional refreshes aligned with lock and SLA tolerances.

## 14. Do Not Rely on ORDER BY in the Defining Query

A materialized view's defining query may include `ORDER BY`:

```sql
CREATE MATERIALIZED VIEW mv_refresh_lab.top_sales_demo AS
SELECT sale_id, tenant_id, sale_date, amount
FROM mv_refresh_lab.sales
WHERE status = 'paid'
ORDER BY sale_date DESC, sale_id DESC
WITH DATA;
```

This may sort rows initially on creation, yet **`REFRESH MATERIALIZED VIEW` does not guarantee preserving that physical or output order** across refreshes.

### 14.1. SELECTs Need Their Own ORDER BY

```sql
SELECT sale_id, tenant_id, sale_date, amount
FROM mv_refresh_lab.top_sales_demo
ORDER BY sale_date DESC, sale_id DESC
LIMIT 20;
```

When applications need deterministic pagination, always specify a **complete, deterministic `ORDER BY`** (e.g., date plus `sale_id`), never relying on heap order or creation luck.

### 14.2. Indexes Supporting Sorting Are Separate

```sql
CREATE INDEX idx_top_sales_date
ON mv_refresh_lab.top_sales_demo
    (sale_date DESC, sale_id DESC);
```

An index can accelerate `ORDER BY`/`LIMIT` plans, yet SQL queries must still **include `ORDER BY`** to guarantee ordering. An index does not replace SQL ordering clauses.

### 14.3. LIMIT in Definitions Requires Deterministic Tie-Breakers

If a materialized view defines `SELECT ... ORDER BY amount DESC LIMIT 100`, the top 100 recomputes on REFRESH. Without tie-breakers when amounts tie, which 100 rows appear is non-deterministic.

Add deterministic tie-breaker columns to `ORDER BY`. And before building a UNIQUE index on a computed rank, verify identity stability across refreshes.

## 15. Resource Costs of REFRESH

Maintaining a materialized view consumes resources: executing the source SELECT, building/storing results, I/O, sort/hash memory, index maintenance, WAL, and sometimes substantial temporary disk space.

### 15.1. Standard Refresh

In standard mode, PostgreSQL replaces the materialized relation's contents directly. When nearly all rows change between refreshes, this is often faster and uses fewer total resources if brief read blocking is tolerable.

### 15.2. Concurrent Refresh

Concurrent refresh builds the full new result set and **reconciles** it against the old contents so SELECTs stay unblocked. Diff computation, row-level index updates, and intermediate data increase CPU, I/O, WAL, and disk usage.

When few output rows change, concurrent refresh works well and avoids read stalls. Still, it **re-runs the full source query**; never mistake it for true incremental refresh.

### 15.3. Views with Many Indexes

Materialized views often get indexes for fast dashboard SELECTs. Every refresh maintains or rebuilds those indexes. Too many indexes inflate refresh duration, write amplification, and storage.

Never blindly create 20 indexes on a materialized view for rare queries. Balance query frequency, read latency, and refresh runtime.

### 15.4. Sources with Heavy JOINs and Aggregations

If the view defines:

```sql
SELECT ...
FROM large_orders AS o
JOIN large_order_items AS i
    ON i.order_id = o.id
JOIN large_customers AS c
    ON c.id = o.customer_id
GROUP BY ...;
```

every full refresh pays the cost of that complex query. `CONCURRENTLY` does not speed up JOINs or improve index plans. Tune source queries, indexes, and stats just like any heavy SELECT.

### 15.5. Read Latency and Refresh Runtime Are Two Separate SLAs

Consider:

- SELECT from materialized view: 5 ms.
- REFRESH: 15 minutes.
- Scheduled interval: 5 minutes.

A 5-minute schedule is **impossible** when refreshes take longer than the interval. Schedulers pile up backlogs, locks, and worsening staleness. Measure p50/p95/p99 refresh durations, not just SELECT speed.

### 15.6. Temporary Storage and WAL

For large refreshes, monitor:

- Free disk space, including space for intermediate/temporary sets.
- Temp files and Sort/Hash spills.
- WAL generation and replication lag.
- Autovacuum load and dead tuple bloat after concurrent refreshes.
- Read I/O on source tables.

Never assume `CONCURRENTLY` uses zero extra storage or generates minimal WAL. Actual overhead depends on plan, view size, and change ratio.

## 16. Measuring Source Query vs. Materialized View Query Costs

`EXPLAIN (ANALYZE, BUFFERS)` helps inspect the defining SELECT; note that `ANALYZE` **executes the SELECT**. For a simple reporting view:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    tenant_id,
    sale_date,
    SUM(amount)::numeric(14, 2) AS revenue,
    COUNT(*)::bigint AS paid_orders
FROM mv_refresh_lab.sales
WHERE status = 'paid'
GROUP BY tenant_id, sale_date;
```

Compare with querying the view:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, sale_date, revenue
FROM mv_refresh_lab.daily_revenue
WHERE tenant_id = 1
  AND sale_date = DATE '2026-11-01';
```

Direct queries scan many source rows and aggregate; materialized view queries read a stored summary row. On a tiny lab table, both may use Seq Scan with negligible timing differences.

### 16.1. Measuring REFRESH Duration Itself

In `psql`:

```text
\timing on
```

Then run:

```sql
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;
```

`\timing` is a **psql client metacommand**, not SQL for JDBC. Applications and monitoring should record elapsed runtime in the job runner alongside success/failure status.

### 16.2. Comparing Modes Fairly

To compare standard vs. concurrent refresh:

1. Use the same dataset and view definition.
2. Run multiple iterations, not a single sample.
3. Record the percentage of output rows modified.
4. Capture CPU, I/O, temp space, WAL, and concurrent reader counts.
5. Measure both reader wait time and refresh duration.
6. Never force-disable index/seq scans globally to manufacture prettier numbers.

**One mode winning in a tiny lab proves nothing about production.**

### 16.3. Why EXPLAIN Alone Is Not Enough

`EXPLAIN` on the defining query shows SELECT/aggregation cost. REFRESH also updates materialized storage and indexes (plus diffing in `CONCURRENTLY`), so measure actual `REFRESH` executions. Summing SELECT planner costs does not yield true refresh duration.

## 17. REFRESH Privileges: Version Differences

PostgreSQL changed its privilege model for maintenance commands in recent versions.

### 17.1. PostgreSQL 17 and Newer

In PostgreSQL 17+, the **`MAINTAIN`** privilege governs `REFRESH MATERIALIZED VIEW`. Relation owners hold it implicitly; other roles can be granted `MAINTAIN` as needed.

Privilege pattern:

```sql
-- Example only when role exists and owner grants privilege:
-- GRANT MAINTAIN
-- ON TABLE mv_refresh_lab.daily_revenue
-- TO report_refresh_worker;
```

You do not need superuser privileges to run periodic refreshes when proper maintenance grants are used.

### 17.2. PostgreSQL 16 and Older

On older majors like PostgreSQL 16, `REFRESH` documentation requires **ownership of the materialized view** (or inheriting that owner role). Do not copy `GRANT MAINTAIN` from PostgreSQL 17 onto an unsupported older server expecting it to work.

Check:

```sql
SHOW server_version;
```

and consult the documentation for your **exact major version**.

### 17.3. View Read Privileges Differ from Refresh Privileges

A role authorized to run:

```sql
SELECT * FROM mv_refresh_lab.daily_revenue;
```

does not automatically hold permission to refresh the view. Reading and refreshing are distinct responsibilities.

### 17.4. Schema Privileges and Security

In production, separate roles:

- Dashboard reader roles hold only required `SELECT`.
- Refresh worker roles hold only required maintenance privileges.
- DDL/index migration roles are separate.
- Base tables and user-defined functions in the defining query are audited under PostgreSQL's security model.

Avoid granting broad privileges to `PUBLIC` or running routine refreshes as superuser unnecessarily.

### 17.5. search_path During REFRESH

PostgreSQL documentation notes that while `REFRESH` runs, `search_path` is temporarily set to `pg_catalog, pg_temp`. Therefore, do not write user-defined functions or view dependencies that rely on arbitrary unqualified name resolution during refresh.

In view definitions, explicitly schema-qualify user-created relations and functions, and test behavior on your target major version. This protects both reliability and `search_path` security.

## 18. What Happens When REFRESH Fails?

REFRESH can fail due to:

- Insufficient maintenance/owner privileges.
- Missing qualifying UNIQUE index for `CONCURRENTLY`.
- Unpopulated view (`WITH NO DATA`).
- Runtime errors in operators/functions inside the source SELECT.
- Exhausted disk or temp space.
- Lock timeout, statement timeout, or cancellation.
- Incompatible DDL/schema edits on source objects.
- New output rows violating UNIQUE index constraints.

### 18.1. No "Half-Updated View" After a Clean Rollback

If a refresh fails inside a PostgreSQL transaction, partial changes are never committed to the materialized view. An already-populated view continues holding **stale but valid** data after rollback.

However, the service may still breach its freshness SLA. That is a freshness failure—never mask it by returning HTTP 200 claiming "real-time data" while jobs are failing.

### 18.2. Track Real Errors, Never Guess from Last Success

When a refresh fails, record:

- View and job name.
- Start time and failure timestamp.
- SQLSTATE or sanitized error message (free of sensitive data).
- Duration and retry state.
- Last successful refresh timestamp.
- Estimated source lag/watermark if available.

Never store just a `refresh_running` boolean and ignore failure details.

### 18.3. Retry with Backoff

For lock timeouts or transient load spikes, retry with exponential backoff and a retry cap. For missing unique indexes, broken source schemas, or duplicate rows, tight retries only overload the database. Classify **transient** vs. **structural** failures first.

### 18.4. Canceling a Job Takes Rollback Time

When a large refresh is canceled, rolling back intermediate work incurs I/O and takes time; cancellation is not always instantaneous. Configure timeouts and runbooks realistically for your workload.

## 19. Scheduling REFRESH: How to Prevent Overlaps

PostgreSQL does not auto-refresh materialized views on source `INSERT`/`UPDATE`/`DELETE`. You must pick an external **trigger scheduling** mechanism:

- Cron / Task Scheduler invoking `psql`.
- Application background schedulers (Spring Boot scheduler, Quartz).
- Airflow, Dagster, or ETL orchestrators.
- `pg_cron` extension if supported, installed, and permitted.
- Serverless jobs or dedicated workers with proper roles and timeouts.

### 19.1. Pick Cadence Based on SLA

Examples:

| Business Need | Reference Strategy |
| --- | --- |
| Yesterday's daily summary dashboard | Refresh daily after source ingestion completes. |
| Admin page tolerating 10–15 min lag | Refresh every 5–10 minutes if runtime and source load permit. |
| Multi-million-row aggregate taking 20 min | Run less frequently, optimize source query, or switch to incremental design. |
| Financial balances needing instant COMMIT visibility | Never rely solely on periodic refresh. |

Leave enough **headroom between runs** so refreshes do not overlap even when p95/p99 durations spike.

### 19.2. Example Shell Command Calling psql

An external job can execute:

```bash
psql -X -v ON_ERROR_STOP=1 \
  -d your_database \
  -c "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_refresh_lab.daily_revenue;"
```

This **shell** snippet assumes `psql` is installed with secure connection and auth config. Never hardcode database passwords in command lines or logs. Shell quoting varies across OSes and schedulers.

`ON_ERROR_STOP=1` ensures SQL errors exit non-zero so alerts fire instead of treating failed refreshes as job successes.

### 19.3. Optional pg_cron Example

If a DBA installed and permitted `pg_cron`, scheduling syntax looks like:

```sql
-- Only when pg_cron is installed and configured:
-- SELECT cron.schedule(
--     'daily-revenue-refresh-every-10-minutes',
--     '*/10 * * * *',
--     $$
--         REFRESH MATERIALIZED VIEW CONCURRENTLY
--             mv_refresh_lab.daily_revenue;
--     $$
-- );
```

Do not run `CREATE EXTENSION pg_cron` or assume it is available in managed PostgreSQL. `shared_preload_libraries`, privileges, and metadata database location depend on your environment.

### 19.4. Avoid Queuing Up Refreshes When Jobs Run Slow

If Job A takes 12 minutes on a 5-minute cron:

```text
10:00  Job A starts
10:05  Job B arrives, may wait
10:10  Job C arrives, may wait
10:12  Job A finishes, Job B may only start now
...
```

Because PostgreSQL allows only one refresh at a time per materialized view, schedulers must **skip, coalesce, or serialize** runs by policy. Overlapping refresh requests never make data fresher.

### 19.5. Job-Level Advisory Locks

With multiple workers, **advisory locks** help ensure only one worker runs the refresh. Pattern:

```sql
BEGIN;

SELECT pg_try_advisory_xact_lock(337001)
    AS acquired_job_lock;

-- Only when acquired_job_lock = TRUE does orchestrator call:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY
--     mv_refresh_lab.daily_revenue;

COMMIT;
```

This is a **two-step protocol pattern**. SQL does not skip REFRESH automatically when `acquired_job_lock=FALSE`; the worker must inspect the boolean and branch. Transaction-scoped advisory locks hold until COMMIT/ROLLBACK, so keep the transaction open across the refresh if using it for serialization.

Advisory locks do not replace PostgreSQL's internal locks on the materialized view; they help **applications avoid starting redundant work** and queuing up workers.

### 19.6. Never Refresh After Every Single INSERT

A trigger calling REFRESH on every inserted row is an anti-pattern on write-heavy tables: every transaction pays the full aggregation cost or stalls on locks, crushing write throughput.

For per-row updates, use **transactional/trigger delta summary tables or asynchronous events**, never full-view REFRESH per INSERT.

## 20. Tracking Successful Refresh Timestamps

PostgreSQL offers `pg_matviews` for populated status and metadata, yet **lacks a built-in `last_refresh_at` column in `pg_matviews`** for job monitoring.

### 20.1. Creating a Dedicated Operational Metadata Table

Lab example:

```sql
CREATE TABLE mv_refresh_lab.refresh_status (
    view_name text PRIMARY KEY,
    last_started_at timestamptz,
    last_succeeded_at timestamptz,
    last_duration_ms numeric,
    last_status text NOT NULL DEFAULT 'never_run',
    last_error text
);

INSERT INTO mv_refresh_lab.refresh_status (
    view_name, last_status
)
VALUES
    ('mv_refresh_lab.daily_revenue', 'never_run');
```

### 20.2. Recording Metadata from the Orchestrator

A worker can:

1. Record start time and `running` status.
2. Execute REFRESH.
3. Once REFRESH commits, record finish time, duration, and `success`.
4. On failure, record the error in a **separate active transaction**.

Illustrative update after success (timestamps and duration supplied by job runner):

```sql
UPDATE mv_refresh_lab.refresh_status
SET
    last_started_at = TIMESTAMPTZ '2026-11-14 08:00+00',
    last_succeeded_at = clock_timestamp(),
    last_duration_ms = 3200,
    last_status = 'success',
    last_error = NULL
WHERE view_name = 'mv_refresh_lab.daily_revenue';
```

`3200` is purely an illustrative duration, not a benchmark. In production, record real measured runtime from the worker.

### 20.3. Why Log Failures in a Separate Transaction?

If REFRESH fails and rolls back its transaction, any log entry **inside that failed transaction** rolls back too. The scheduler must catch the exception and open a fresh transaction to record the failure and alert.

### 20.4. Last Success Is Not a Data Watermark

`last_succeeded_at` tells when the job finished, not that all source events up to that exact timestamp were included. When ETL pipelines track watermarks like `max_ingested_at` or LSNs, store those verified values separately per contract.

### 20.5. Surfacing Freshness on Dashboards

```sql
SELECT
    view_name,
    last_succeeded_at,
    clock_timestamp() - last_succeeded_at
        AS elapsed_since_success,
    last_status
FROM mv_refresh_lab.refresh_status
WHERE view_name = 'mv_refresh_lab.daily_revenue';
```

If `last_succeeded_at IS NULL`, no success has been recorded in the metadata table yet (or metadata is out of sync)—not proof the materialized view was never populated.

## 21. Observing Active Materialized Views

### 21.1. pg_stat_activity

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS elapsed,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND state <> 'idle'
ORDER BY query_start NULLS LAST;
```

Filter by database and worker user on busy systems. Never rely solely on `query LIKE '%REFRESH%'` assuming it finds everything: query strings can be truncated or invoked via wrappers/functions.

### 21.2. pg_locks on the View

```sql
SELECT
    l.pid,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
WHERE l.relation =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY l.pid, l.mode;
```

You will see `ExclusiveLock` or `AccessExclusiveLock` while a refresh holds its lock. When queries block, inspect **blocking PIDs**, **transaction states**, and concurrent activity.

### 21.3. pg_matviews.ispopulated

```sql
SELECT
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
ORDER BY matviewname;
```

`ispopulated=true` means the view holds a scannable dataset, **not that its contents are fresh or in sync with sources**.

### 21.4. View and Index Sizes

```sql
SELECT
    pg_size_pretty(
        pg_relation_size(
            'mv_refresh_lab.daily_revenue'::regclass
        )
    ) AS heap_size,
    pg_size_pretty(
        pg_indexes_size(
            'mv_refresh_lab.daily_revenue'::regclass
        )
    ) AS index_size,
    pg_size_pretty(
        pg_total_relation_size(
            'mv_refresh_lab.daily_revenue'::regclass
        )
    ) AS total_size;
```

Sizes vary by refresh mode and history. Monitor storage growth and maintenance bloat alongside query durations.

### 21.5. Estimated Rows and Statistics

```sql
SELECT
    c.relname,
    c.reltuples,
    c.relpages
FROM pg_class AS c
WHERE c.oid =
    'mv_refresh_lab.daily_revenue'::regclass;
```

`reltuples` is an **estimate**, not an exact row count. If planner estimates drift after large data swings, update statistics per policy, e.g.:

```sql
ANALYZE mv_refresh_lab.daily_revenue;
```

In production, ensure appropriate maintenance privileges and monitor impact. `ANALYZE` **does not REFRESH from source tables**; it only updates planner statistics.

## 22. Operational Runbook Specs for Refresh Jobs

A reliable refresh job documents:

| Component | Operational Question |
| --- | --- |
| Owner / job role | Which role has `MAINTAIN` or proper ownership? |
| Frequency | How often does it run, and why? |
| Deadline | When must dashboards show fresh data? |
| Dependencies | Which source ETLs/tables must finish first? |
| Overlap policy | Should new triggers skip, queue, or coalesce? |
| Timeout | When should a stalled/slow command be canceled? |
| Lock budget | Is blocking SELECTs permitted? |
| Resource budget | Are CPU, RAM, temp space, WAL, and I/O sufficient? |
| Observability | Who gets alerted on failures or duration spikes? |
| Recovery | On failure, keep serving stale MV or fall back? |
| Data contract | How are "Last refreshed at" and watermarks defined? |

### 22.1. Job Flow Pattern

```text
Scheduler triggers
    |
    v
Check if previous job is still running?
    | Yes
    +-----> SKIP / COALESCE / ALERT (per policy)
    |
    | No
    v
Record started_at + check dependency/watermark
    |
    v
REFRESH MATERIALIZED VIEW [CONCURRENTLY] ...
    |
    +-----> Error -> rollback -> log failed in new transaction -> alert
    |
    v
COMMIT succeeds
    |
    v
Record succeeded_at/duration/watermark + metric
    |
    v
Check freshness SLA
```

### 22.2. Never Log Success Before Commit

If a scheduler marks "success" right after issuing REFRESH without awaiting server commit, monitoring lies. Confirm success strictly after command and transaction completion.

### 22.3. Schedule Based on Worst-Case Runtime

Suppose a cron runs every 10 minutes and refreshes normally take 4 minutes, yet month-end runs take 30 minutes. Size schedules for p99 durations, not averages. If overloaded, lower frequency, optimize the defining query, or move to controlled incremental updates.

## 23. When Should You Choose Standard REFRESH?

Not every application needs `CONCURRENTLY`.

### 23.1. Initial Population

A view created `WITH NO DATA` is unpopulated, so the first refresh must be standard `WITH DATA`. Creating indexes beforehand does not allow running `CONCURRENTLY` on an unpopulated view.

### 23.2. Off-Hours Reporting

If a view is queried only during business hours, a 02:00 AM batch refresh can tolerate `ACCESS EXCLUSIVE` locking and benefit from lower resource usage or faster runtime in standard mode.

### 23.3. Nearly All Output Rows Change

When every refresh replaces almost the entire result set, concurrent diffing overhead offers little advantage over full replacement. Benchmark at production scale.

### 23.4. No Qualifying Unique Key

If output rows lack a unique business key for a qualifying UNIQUE index, `CONCURRENTLY` cannot run. Standard REFRESH still works, though you should inspect the **view definition**—duplicate rows often stem from bad JOINs or missing GROUP BYs.

### 23.5. Consciously Accepting Read Locks

Standard REFRESH fits best when:

- Concurrent readers during the refresh window are minimal.
- Clear maintenance windows exist.
- Batch completion speed matters most.
- Concurrent mode overhead outweighs reader-lock avoidance.

Never use standard mode on a materialized view backing latency-sensitive APIs without assessing blocking impact.

## 24. When Should You Choose CONCURRENTLY?

### 24.1. Dashboards with Continuous Readers

If dashboards receive queries every second all day, a multi-minute standard REFRESH causes timeouts. `CONCURRENTLY` keeps readers querying the prior version while the new one computes.

### 24.2. Stable Unique Business Keys

Summary views with `GROUP BY tenant_id, sale_date` have clear keys suitable for a UNIQUE index. When only a small fraction of rows change per cycle, diffing cost stays reasonable.

### 24.3. Stale Reads Tolerated During Refresh

Readers continue seeing **old results** until the concurrent refresh commits. Product requirements must accept:

- Metrics are not real-time.
- Last update timestamps are displayed or well understood.
- Failed refreshes leave data staler than SLA until resolved.

### 24.4. Sufficient Resource Headroom

Concurrent refresh demands CPU, temp space, WAL, and index maintenance. During peak write traffic, avoid unconstrained concurrent refreshes that starve primary transactions.

### 24.5. Overlap Coordination in Place

Only one REFRESH per view can run at a time. The job runner must manage overlap, timeouts, and success/failure state.

## 25. What If You Need Near-Real-Time or Real-Time Data?

If metrics must update every second or within the same transaction, cranking `REFRESH CONCURRENTLY` down to every 100 ms will not work. Each REFRESH still runs the source query and reconciles.

### 25.1. Query Source Tables Directly

Pros:

- Reads committed state per SQL snapshot.
- Zero materialized cache management.
- Ideal when tables are well-indexed and queries run fast enough.

Cons:

- Re-runs filters, JOINs, and aggregations on every read.
- Wide dashboards over massive tables can become too expensive.

### 25.2. Transactional Aggregate Tables

A summary table updated inside the same transaction as source writes:

```text
BEGIN
    INSERT order
    UPDATE daily_totals SET revenue = revenue + delta
COMMIT
```

Provides strong consistency if concurrency, edits/deletes/rollbacks, constraints, and idempotency are handled properly. However, it shifts compute onto the write path and requires handling status transitions carefully.

### 25.3. Event-Driven Projections

Consumers process `OrderPaid` and `OrderRefunded` events to update a read model table:

```text
Orders DB -> Outbox/CDC -> Worker -> Revenue projection
                                   |
                                   v
                            Dashboard SELECT
```

Updates incrementally, yet introduces lag, retries, duplicate delivery, out-of-order events, and reconciliation needs. Strong source consistency is not automatic without careful design.

### 25.4. Extensions and Analytics Engines

Specialized extensions or analytics databases offer native incremental/continuous aggregates. These are **capabilities outside PostgreSQL's standard `REFRESH MATERIALIZED VIEW` command**; never assume they exist on every managed PostgreSQL host.

### 25.5. Two-Tier Reporting

Example:

- A materialized view aggregates stable history through yesterday.
- Live queries hit hot tables only for today.
- The API merges both without double-counting.

This reduces full-refresh frequency while keeping today fresh, but requires **strict watermarks/cutoffs**, consistent timezones, and handling of late-arriving edits. Never add two sources together without proving zero overlap.

## 26. Common Errors When Using CONCURRENTLY

### 26.1. Error "cannot refresh ... concurrently"

Common causes: the view is unpopulated or lacks a qualifying unique index. Checklist:

1. Check `pg_matviews.ispopulated`.
2. If false, run `REFRESH MATERIALIZED VIEW ... WITH DATA`.
3. Inspect view indexes via `pg_indexes` and `pg_index`.
4. Ensure at least one valid UNIQUE index uses **column names only** and no `WHERE`.
5. Verify index validity and uniqueness of data.
6. Retry with proper privileges and resources.

Never try fixing this by adding a non-unique index and retrying in a loop.

### 26.2. Duplicate Key Error on CREATE UNIQUE INDEX

If the query produces multiple rows for the same key:

```sql
-- Hypothetical materialized view contains:
-- tenant_id | sale_date   | revenue
-- 1         | 2026-11-01  | 100
-- 1         | 2026-11-01  |  50
```

`CREATE UNIQUE INDEX ... (tenant_id,sale_date)` fails with a duplicate key violation. Investigate why two rows exist for one key if business rules expect one summary row.

Check on a populated view:

```sql
SELECT
    tenant_id,
    sale_date,
    COUNT(*) AS rows_per_key
FROM mv_refresh_lab.daily_revenue
GROUP BY tenant_id, sale_date
HAVING COUNT(*) > 1;
```

The clean lab dataset has zero duplicates; use this diagnostic query on any view with composite keys.

### 26.3. UNIQUE Index on a Non-Grouping Key

For instance, `UNIQUE(tenant_id)` on `daily_revenue` fails as soon as a tenant has sales on multiple days. The problem isn't "missing DISTINCT"—it's that **`tenant_id` alone does not uniquely identify a row**.

### 26.4. Still Failing After Creating Expression/Partial Indexes

If you only have:

```sql
-- Not eligible:
-- CREATE UNIQUE INDEX ux_expression
-- ON my_matview ((lower(name)));
-- CREATE UNIQUE INDEX ux_partial
-- ON my_matview (tenant_id, sale_date) WHERE active;
```

`REFRESH CONCURRENTLY` remains disallowed. Those indexes serve other queries, not the reader-friendly concurrent refresh prerequisite.

### 26.5. REFRESH Taking Too Long

Investigate:

- Is the defining SELECT/JOIN/GROUP BY expensive?
- How many rows/bytes are in the view output?
- Did a huge percentage of rows change since last refresh?
- Are temp disk, WAL, or I/O saturated?
- Are lock waits or queued workers stalling execution?
- Are too many indexes on the view adding maintenance overhead?
- Are long-running transactions pinning snapshots/dead tuples?

Never bump `work_mem` server-wide blindly without identifying the root cause.

### 26.6. Dashboards Timing Out Despite CONCURRENTLY

Check:

- Is the dashboard still querying **source tables directly** instead of only the materialized view?
- Are SELECTs blocked by unrelated DDL or `ACCESS EXCLUSIVE` locks?
- Is the server CPU/I/O saturated by the REFRESH itself?
- Do dashboard SELECTs lack proper indexes/statistics on the view?
- Are client/transaction timeouts set too aggressively?

`CONCURRENTLY` eliminates **lock conflicts between refresh and view SELECTs**, not every latency bottleneck under load.

### 26.7. REFRESH Succeeded Yet Dashboard Totals Look Wrong

Possible causes:

- Refresh snapshot was captured before a source batch committed.
- View filters status/dates differently from dashboard expectations.
- Source query has a JOIN duplicating rows.
- ETL introduced late-arriving data.
- Dashboard joins multiple views refreshed at different times.
- Dashboard SELECT lacks deterministic `ORDER BY` or `GROUP BY` keys.

Audit definitions, snapshots, and watermarks before blaming PostgreSQL for "incomplete refreshes."

## 27. Production Troubleshooting Runbook for REFRESH

Follow a non-destructive diagnostic sequence:

### Step 1. Identify the Symptom

Distinguish:

- REFRESH throws an SQL error.
- Refresh runs too long.
- Readers block on locks.
- Readers run slow without blocking.
- Data is stale.
- Aggregates are business-incorrect.

Each symptom points to different causes and fixes.

### Step 2. Check View State

```sql
SELECT
    schemaname,
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab';
```

If unscannable, run standard `REFRESH ... WITH DATA` after confirming source state.

### Step 3. Verify Qualifying UNIQUE Index

```sql
SELECT
    idx.relname,
    i.indisunique,
    i.indisvalid,
    i.indexprs IS NULL AS no_expressions,
    i.indpred IS NULL AS no_predicate,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid =
    'mv_refresh_lab.daily_revenue'::regclass;
```

The index must live on the **view itself**, be UNIQUE, valid, non-partial, and expression-free.

### Step 4. Inspect PIDs and Locks

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    query_start,
    clock_timestamp() - query_start AS elapsed
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY query_start NULLS LAST;
```

Combine with `pg_locks` or `pg_blocking_pids(pid)` to spot contention. Never terminate backends without understanding side effects.

### Step 5. Evaluate Source Query and Plan

Run `EXPLAIN (ANALYZE, BUFFERS)` on the defining SELECT in a safe environment. Inspect estimated vs. actual rows, sort/hash spills, buffers, and source indexes. On large datasets, `EXPLAIN ANALYZE` executes the full SELECT, so pick an appropriate window.

### Step 6. Reconcile Freshness Metadata

Inspect last successful refresh, duration, and watermarks recorded by the job runner. If metadata is missing or untrusted, state clearly that exact freshness timestamps are unknown rather than guessing from `pg_matviews.ispopulated`.

### Step 7. Apply the Right Remediation

| Root Cause | Action |
| --- | --- |
| View unpopulated | Standard `REFRESH ... WITH DATA`. |
| Missing UNIQUE index | Design proper key and `CREATE UNIQUE INDEX`. |
| Heavy source query | Optimize query/indexes/stats or switch aggregation pattern. |
| Readers blocked by standard REFRESH | Adopt `CONCURRENTLY` if eligible, or move run window. |
| Blocked by unrelated DDL | Coordinate locks/DDL; `CONCURRENTLY` won't fix unrelated DDL. |
| Overlapping scheduler runs | Skip/coalesce/serialize jobs. |
| Stale due to late ETL | Track ETL dependencies/watermarks; adjust refresh trigger timing. |
| Duplicate rows failing UNIQUE | Fix business key or JOIN/GROUP BY logic. |
| Missing privileges | Grant `MAINTAIN` (PG17+) or align ownership. |

### Step 8. Post-Fix Monitoring

Track subsequent refresh durations, error rates, WAL/temp usage, reader latency, and data freshness. Keep a rollback plan for index, schedule, or query changes.

## 28. Safely Creating UNIQUE Indexes on Large Views

When an existing materialized view holds hundreds of millions of rows, building a UNIQUE index can take significant time and locks. PostgreSQL supports:

```sql
-- Example when materialized view is already populated:
-- CREATE UNIQUE INDEX CONCURRENTLY ux_daily_revenue_tenant_day
-- ON mv_refresh_lab.daily_revenue (tenant_id, sale_date);
```

**`CREATE UNIQUE INDEX CONCURRENTLY` and `REFRESH MATERIALIZED VIEW CONCURRENTLY` are two distinct commands.**

### 28.1. Meaning of CONCURRENTLY in Each Command

| Command | Purpose |
| --- | --- |
| `CREATE UNIQUE INDEX CONCURRENTLY ...` | Builds an index while minimizing blocking of concurrent operations where allowed. |
| `REFRESH MATERIALIZED VIEW CONCURRENTLY ...` | Replaces stored results while letting normal SELECTs continue reading the view. |

### 28.2. Transaction Restrictions on Concurrent Index Builds

`CREATE INDEX CONCURRENTLY` cannot run inside an explicit transaction block and has special recovery rules if interrupted. Never place both commands inside a single `BEGIN ... COMMIT` block expecting valid execution.

### 28.3. Invalid Indexes After Interrupted Builds

If a concurrent index build fails or is canceled, an invalid index object can remain in the catalog needing cleanup by a DBA. Never assume an index listed in `pg_indexes` is valid for concurrent refresh without checking `indisvalid`.

### 28.4. Index Builds Still Enforce Real Uniqueness

`CONCURRENTLY` on `CREATE UNIQUE INDEX` does not skip duplicate keys. If the view contains duplicate rows on the chosen key, the build fails.

### 28.5. Coordinating Index Creation and Refreshes

On large views:

1. Identify the logical key from the defining query.
2. Check for duplicates and NULL semantics.
3. Plan index creation within acceptable lock/duration budgets.
4. Verify the index is valid, full-coverage, and column-only.
5. Test `REFRESH CONCURRENTLY` in a staging/maintenance window.
6. Measure reader latency, refresh duration, and verify rollback steps.

## 29. Case Study 1: Continuously Read Dashboard

**Context**

- API reads revenue metrics from a materialized view.
- 300 SELECT requests/sec during peak hours.
- REFRESH takes ~90 seconds.
- Business tolerates up to 10 minutes of lag.
- Output has one unique row per `(tenant_id, sale_date)`.

### 29.1. Choosing the Mode

`REFRESH MATERIALIZED VIEW CONCURRENTLY` is a strong fit so readers stay served during the 90-second refresh. Create the matching UNIQUE index:

```sql
CREATE UNIQUE INDEX ux_daily_revenue_tenant_day
ON mv_refresh_lab.daily_revenue
    (tenant_id, sale_date);
```

Our lab already created this index; this simply reiterates the design—do not run it a second time if the index name already exists.

### 29.2. Controls Needed

- How often must REFRESH run to stay within the 10-minute SLA even with 90-second runtimes?
- Is the view populated?
- Do reader SELECTs have supporting indexes?
- Does the scheduler prevent overlapping runs?
- Are temp space and WAL sufficient during peak traffic?
- Does the dashboard display `last_success`/watermark?

### 29.3. Takeaway

`CONCURRENTLY` avoids blocking normal SELECTs on the materialized view, though it does not guarantee low reader latency if the server saturates on CPU/I/O. Load-test concurrent SELECTs alongside REFRESH.

## 30. Case Study 2: Overnight Summary Report

**Context**

- ETL ingestion completes after 01:00.
- Users access the report only starting at 08:00.
- 80% of summary rows change every night.
- Standard refresh takes 8 minutes; concurrent refresh took 13 minutes in testing.

### 30.1. Choosing the Mode

Standard `REFRESH MATERIALIZED VIEW` is likely better because:

- Zero readers are active during the batch window.
- No reason to pay diff/reconcile overhead for reader availability.
- Measured runtime and resource usage are lower in this scenario.

### 30.2. Never Refresh Before ETL Finishes

If the scheduler fires at 01:10 while ETL commits at 01:20, the report misses data. Enforce explicit dependency ordering:

```text
ETL source completed
          |
          v
Source validation/watermark
          |
          v
REFRESH MATERIALIZED VIEW
          |
          v
Success + report publish
```

### 30.3. Takeaway

**Do not force `CONCURRENTLY` just because PostgreSQL supports it.** Aim to hit read/freshness SLAs at the lowest acceptable cost, backed by benchmarks.

## 31. Case Study 3: Unpopulated Materialized View

**Context**

- A schema migration creates a materialized view `WITH NO DATA`.
- A UNIQUE index is created or planned.
- The deployment job immediately calls `REFRESH ... CONCURRENTLY`.

### 31.1. Symptom

Concurrent refresh fails because the view is **not populated**. Having the index does not satisfy the first prerequisite.

### 31.2. Bootstrap Workflow

```text
1. CREATE MATERIALIZED VIEW ... WITH NO DATA
2. REFRESH MATERIALIZED VIEW ... WITH DATA
3. CREATE UNIQUE INDEX ... (key columns; no WHERE)
4. REFRESH MATERIALIZED VIEW CONCURRENTLY ... (subsequent runs)
```

If created `WITH DATA` initially, skip step 2, create the index, and use concurrent refresh thereafter.

### 31.3. Empty Result Sets Are Still Valid

If zero source rows exist at initial load, `WITH DATA` populates a **0-row** view with `ispopulated=true`. Never write a bootstrap check testing `SELECT COUNT(*) > 0` to decide whether `CONCURRENTLY` is ready.

## 32. Case Study 4: No Qualifying UNIQUE Key

**Context**

A view outputs individual transactions yet omits `transaction_id`:

```sql
-- Example of a result design problem:
-- SELECT tenant_id, sale_date, amount
-- FROM sales;
```

Two distinct orders for the same tenant, date, and amount produce **two identical rows** in the view. A UNIQUE index on those three columns cannot be created.

### 32.1. Do Not Add DISTINCT Reflexively

Writing `SELECT DISTINCT tenant_id,sale_date,amount` collapses two real identical transactions into one row—**silently corrupting business totals**.

### 32.2. Proper Fixes

- If per-transaction grain is needed: include unique `transaction_id` in output and build the UNIQUE index on it.
- If daily tenant summary is needed: `GROUP BY tenant_id,sale_date` with proper `COUNT`/`SUM`.
- If invalid duplicates exist in source: fix source data and constraints.
- If no stable unique key exists: use standard REFRESH in maintenance windows or redesign the representation.

### 32.3. Takeaway

The UNIQUE index requirement for `CONCURRENTLY` reflects a **meaningful data identity requirement**, not a DDL trick. Picking the wrong key prevents indexing or corrupts business data.

## 33. Case Study 5: System Needing Updated Balance Right After Payment

**Context**

Users must see updated balances immediately after paying. A balance materialized view refreshes every minute.

### 33.1. Problem

One minute is far too stale for spendable/withdrawable balance checks. Even `REFRESH CONCURRENTLY` every second cannot guarantee every just-committed transaction is included in the snapshot.

### 33.2. Better Architectures

Read transactional data directly, maintain a summary table within the same transaction, or use a ledger/read model with explicit consistency guarantees. Periodic materialized views belong in **analytical reporting**, never real-time transactional decision paths requiring strong read-your-writes.

### 33.3. Takeaway

`CONCURRENTLY` never turns eventual freshness into strong consistency. Distinguish **unblocked readers** from **readers seeing the latest commit**.

## 34. Case Study 6: Chained Materialized Views

**Context**

Three layers:

```text
sales table
    |
    v
mv_sales_by_day
    |
    v
mv_sales_by_month
    |
    v
dashboard
```

If `mv_sales_by_month` refreshes before `mv_sales_by_day`, the monthly view reads yesterday's daily view even though `sales` updated.

### 34.1. Scheduler Must Enforce Dependency Order

```text
Source ingestion complete
          |
          v
REFRESH mv_sales_by_day
          |
          v
Confirm success/watermark
          |
          v
REFRESH mv_sales_by_month
          |
          v
Publish dashboard freshness
```

### 34.2. CONCURRENTLY Does Not Resolve Dependencies

Each `CONCURRENTLY` command keeps SELECTs unblocked on its own view, but never forces downstream views to wait for upstream refreshes unless the scheduler executes a proper DAG.

### 34.3. Cross-View Consistency

Even when refreshed in order, dashboards querying two views separately mid-run can observe mismatched versions. If cross-view snapshot consistency is required, implement a publish boundary/version swap protocol or coordinated transactions aligned with lock budgets.

## 35. Case Study 7: Late-Arriving Source Data

**Context**

- `revenue_by_day` aggregates by payment date.
- A payment gateway delivers delayed transactions from last week today.
- The view refreshes nightly.

### 35.1. What Happens?

Once delayed transactions commit before the refresh snapshot, the next refresh **changes past days' revenue**, not just today's. Standard REFRESH recomputes the defining query, automatically restating historical periods covered by the query.

### 35.2. Why Inspect the Defining Query?

If the query filters `WHERE sale_date = CURRENT_DATE`, last week's late transactions will never appear regardless of refreshes. If the query covers a historical window permitting backfills, late arrivals are picked up.

### 35.3. Watermarks and Policies

Applications must:

- Define the late-arrival window.
- Clarify which periods are finalized/closed vs. still mutable.
- Track source ingestion status.
- Schedule historical refreshes after corrections.

`CONCURRENTLY` does not decide which historical periods may change.

## 36. Anti-Patterns in Materialized View Design

### 36.1. Using random() as a Unique Key

```sql
-- Flawed design if used as identity across refreshes:
-- SELECT random() AS synthetic_id, ... FROM sales;
```

Random values change on every run. It is neither a stable identity nor collision-proof, and carries zero business meaning.

### 36.2. Using row_number() Without Accounting for Shifting Data

`row_number() OVER (ORDER BY amount DESC)` shifts IDs across every row whenever a new high-amount order arrives. Downstream consumers treating row numbers as stable IDs suffer silent corruption.

### 36.3. Refreshing the Entire View on Every Row Write

This creates an expensive loop and lock contention. High-write tables need incremental maintenance patterns rather than full-view re-aggregation per INSERT.

### 36.4. Enabling CONCURRENTLY Without Proper Key Design

When a defining query emits duplicate rows, forcing arbitrary keys just to pass index creation corrupts semantics. Fix the true key or underlying schema.

### 36.5. Scheduling Refreshes Faster Than Runtime

Causes queued jobs, zero freshness improvement, and lock/resource contention. Enforce skip/coalesce and measure runtimes.

### 36.6. Assuming ORDER BY in CREATE MV Persists

REFRESH never guarantees physical or output order. Every client needing sorted output must include `ORDER BY`.

### 36.7. Treating ispopulated as a Freshness Indicator

`ispopulated=true` only means the view is scannable; it could be days stale.

### 36.8. Logging Success Before COMMIT

If REFRESH rolls back while job metadata records success, dashboards mislead users. Separate `started`, `finished`, committed `success`, and source watermarks.

### 36.9. Using REFRESH WITH NO DATA to "Temporarily Clear a Report"

`WITH NO DATA` leaves the view **unscannable**, causing SELECT errors. Use application flags or empty-state responses instead.

### 36.10. Confusing CREATE INDEX CONCURRENTLY with REFRESH CONCURRENTLY

The two commands have distinct purposes, locks, and transaction restrictions. Sharing the word `CONCURRENTLY` does not make them equivalent.

### 36.11. Overlooking Security

Materialized views store physical data copies. Broad SELECT grants on a materialized view can leak sensitive totals even when source tables are locked down. Audit grants, schema `USAGE`, ownership, RLS, and export policies.

### 36.12. Assuming Refreshes Never Cause WAL or Replica Lag

On large datasets, replacing materialized contents generates significant WAL and disk I/O that can lag replicas. Monitor I/O and replication lag under load.

## 37. Integrating REFRESH Jobs into Java/JDBC

In Java Spring Boot or plain JDBC services, let a **scheduler/job worker** invoke SQL REFRESH with an appropriately privileged account. Never run REFRESH inside individual users' web requests before rendering dashboards.

### 37.1. JDBC Example with DataSource

```java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class MaterializedViewRefresher {
    private final DataSource dataSource;

    public MaterializedViewRefresher(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void refreshDailyRevenue() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(true);

            try (Statement statement = connection.createStatement()) {
                // Execution limit enforced by JDBC driver;
                // does not replace DB-side monitoring/timeouts.
                statement.setQueryTimeout(300);

                statement.execute(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY " +
                    "mv_refresh_lab.daily_revenue"
                );
            }
        }
    }
}
```

Prerequisites before this code works:

1. Materialized view exists and is populated (`WITH DATA`).
2. View has a qualifying UNIQUE index.
3. JDBC account holds `MAINTAIN` on PostgreSQL 17+ or ownership on older majors.
4. Scheduler enforces overlap protection and error handling.
5. Query and job timeouts are sized appropriately.

### 37.2. Do Not Treat setQueryTimeout as an Absolute Kill Switch

`setQueryTimeout(300)` asks the JDBC driver to cancel the query after 300s if supported. Cancellation can lag under network/server load; pair it with DB-side `statement_timeout` and monitoring where appropriate.

### 37.3. Never Trigger REFRESH Inside GET Requests

Poor design:

```text
GET /dashboard
     |
     v
REFRESH MATERIALIZED VIEW CONCURRENTLY
     |
     v
SELECT report
```

With 100 concurrent requests, you trigger 100 refreshes of the same view—PostgreSQL serializes them to one at a time, queuing and timing out requests.

Better design:

```text
Scheduler/job worker -> REFRESH on appropriate schedule/trigger

GET /dashboard       -> SELECT from materialized view
                        + display last_success/watermark
```

### 37.4. Transaction Context in Frameworks

Never wrap REFRESH inside a long application transaction alongside bulk DB writes and external HTTP calls. Locks remain held until transaction end, increasing contention.

When logging metadata, separate **start/failure logging** from **post-commit success**, and never attempt to log errors inside an already-aborted transaction.

### 37.5. Securing Credentials

Use connection pools and secret managers/environment policies; never hardcode passwords or connection strings in code or logs. API reader roles need only `SELECT`, separate from the job worker's `MAINTAIN` role.

## 38. Practice Exercises

Exercises below can use Section 8's `mv_refresh_lab` dataset. Run two-session lock tests only in a dedicated database; never hold sleeping lock transactions in production. Expected numbers assume the lab's exact sequence; extra demo statements will alter counts.

### Exercise 1. Comparing Three Object Types

How does a regular VIEW differ from a MATERIALIZED VIEW and a self-maintained summary table? Which objects persist SELECT results in PostgreSQL?

### Exercise 2. Why Data Goes Stale

A materialized view refreshes at 08:00. At 08:10, 2,000 new rows commit to the source table. By 08:12 no further REFRESH has run. Must querying the materialized view reflect those 2,000 rows?

### Exercise 3. Syntax

Write both the standard refresh command for `mv_refresh_lab.daily_revenue` and the `CONCURRENTLY` command.

### Exercise 4. WITH DATA

Does `REFRESH MATERIALIZED VIEW v` differ from `REFRESH MATERIALIZED VIEW v WITH DATA` in default population behavior?

### Exercise 5. WITH NO DATA

After `REFRESH MATERIALIZED VIEW v WITH NO DATA`, does SELECTing from `v` return a valid 0-row result? Why or why not?

### Exercise 6. CONCURRENTLY + NO DATA

Is `REFRESH MATERIALIZED VIEW CONCURRENTLY v WITH NO DATA` valid?

### Exercise 7. Populated vs. Row Count

A materialized view created `WITH NO DATA` runs `REFRESH ... WITH DATA`, yet the source query returns 0 rows. Does it qualify as populated for a subsequent concurrent refresh?

### Exercise 8. Index Prerequisites

List the four attributes of a qualifying UNIQUE index for `REFRESH ... CONCURRENTLY`.

### Exercise 9. Source Table Unique Indexes

Source `sales` has `PRIMARY KEY(sale_id)`. Why is this **insufficient** to run `REFRESH CONCURRENTLY` on `daily_revenue`?

### Exercise 10. Composite Unique Key

The summary view produces one row per tenant per day. Why is `UNIQUE(tenant_id)` wrong? Write the correct index.

### Exercise 11. Expression Index

Does `UNIQUE INDEX ON mv ((lower(email)))` qualify for `CONCURRENTLY`? Why or why not?

### Exercise 12. Partial Index

Does `UNIQUE INDEX ON mv (tenant_id, sale_date) WHERE active` qualify? Why or why not?

### Exercise 13. Non-Unique Index

Only `CREATE INDEX ON mv (tenant_id,sale_date)` exists. Can `CONCURRENTLY` rely on it?

### Exercise 14. Bootstrap Sequence

Write the exact sequence from `CREATE MATERIALIZED VIEW ... WITH NO DATA` through the first `REFRESH CONCURRENTLY`.

### Exercise 15. Revenue Before/After Refresh

The lab initially has tenant 1 on Nov 1 with paid amounts 100 and 50; then a paid 25 order is added. What does the view report before refresh? After refresh?

### Exercise 16. New Group Appearing

Initially tenant 2 on Nov 2 has only a pending 30 order. After inserting paid 110 and refreshing, what row appears in `daily_revenue`?

### Exercise 17. Pending Changing to Paid

With paid 110 and pending 30 for tenant 2 on Nov 2, after updating 30 to paid and running `REFRESH CONCURRENTLY`, what are `revenue` and `paid_orders`?

### Exercise 18. Removing All Rows of a Group

If all paid rows for tenant 1 on Nov 2 become `cancelled`, does the paid-only `GROUP BY` query still return that group? What happens to the view after refresh?

### Exercise 19. ACCESS EXCLUSIVE

Why does standard REFRESH block SELECTs on the materialized view? What is the lock mode name?

### Exercise 20. EXCLUSIVE

Which lock mode does `REFRESH CONCURRENTLY` acquire on the materialized view? Which lock does normal SELECT acquire, and are they compatible?

### Exercise 21. Long Transactions

Session A runs standard REFRESH inside `BEGIN` and sleeps 5 minutes before `COMMIT`. Why does Session B stall on SELECT even after REFRESH finishes computing?

### Exercise 22. What Readers See Mid-Refresh

Session A is running `REFRESH CONCURRENTLY` and has not committed yet. Session B runs SELECT. Can it read uncommitted new data? What happens if an older snapshot transaction stays open?

### Exercise 23. Freshness

Refresh starts at 10:00, source commits a transaction at 10:01, and refresh finishes at 10:03. Can you guarantee the 10:01 commit is inside the view?

### Exercise 24. ORDER BY

A materialized view has `ORDER BY amount DESC` in its defining query. After REFRESH, can an application SELECT without `ORDER BY` rely on descending order?

### Exercise 25. Single REFRESH Only

A scheduler fires at 09:00, 09:05, and 09:10 while REFRESH takes 20 minutes. Does `CONCURRENTLY` allow all three refreshes on the same view to run simultaneously? Propose a policy.

### Exercise 26. Scheduling Cadence

A dashboard requires max 10-minute lag while REFRESH has a p99 duration of 8 minutes. Should you schedule REFRESH every 1 minute? Which metrics must you evaluate?

### Exercise 27. pg_matviews

Write a query reading `ispopulated` and `hasindexes` for `mv_refresh_lab.daily_revenue`. Is there a built-in `last_refresh_at` column in `pg_matviews`?

### Exercise 28. Verifying Indexes

Write SQL querying `pg_indexes` or `pg_index` to confirm a UNIQUE index has no `WHERE` or expressions.

### Exercise 29. Locks and Blocking

Write queries inspecting `pg_locks` on the materialized view and identifying blocker PIDs in PostgreSQL.

### Exercise 30. Maintenance Privileges

Which privilege governs refresh in PostgreSQL 17+? What is the key difference in PostgreSQL 16?

### Exercise 31. Live Data vs. Cache

An API must show updated balances immediately after COMMIT. Why can't scheduled `REFRESH CONCURRENTLY` guarantee this? Name two alternative architectures.

### Exercise 32. EXPLAIN

What does `EXPLAIN (ANALYZE, BUFFERS)` on the defining query reveal? Why must you still measure actual REFRESH runtime separately?

### Exercise 33. Materialized View Chain

`mv_month` depends on `mv_day`, which depends on `sales`. In what order should the scheduler refresh them, and why?

### Exercise 34. Unique Identity

If a view selects individual transactions without `transaction_id`, two transactions on the same date/tenant/amount look identical. Should you add `DISTINCT` to enable a UNIQUE index on those three columns? Explain the risk.

### Exercise 35. Error Recovery

`REFRESH CONCURRENTLY` fails due to an invalid unique index. Should the job retry every second or classify the error and alert? Why?

### Exercise 36. REFRESH WITH NO DATA

An admin runs `REFRESH ... WITH NO DATA` on a view actively used by a dashboard. What happens to SELECTs, and how do you make the view scannable again?

### Exercise 37. CREATE INDEX CONCURRENTLY

Distinguish `CREATE UNIQUE INDEX CONCURRENTLY` from `REFRESH MATERIALIZED VIEW CONCURRENTLY`. Which one cannot run inside an explicit transaction block?

### Exercise 38. Refresh Logging

Design minimal table/log fields to track last success, duration, errors, and source watermark. Why does a refresh finish timestamp not prove all source commits up to that timestamp were included?

### Exercise 39. JDBC

Why should a background job worker call REFRESH instead of every HTTP GET dashboard request? List privileges and timeouts to control.

### Exercise 40. Design Proposal

A system has a continuously read dashboard tolerating 15-minute lag, 4-minute REFRESH runs, a materialized view with a stable grouping key, and 1% of output rows changing per run. Which mode should you test first, and what metrics must you measure?

## 39. Suggested Solutions

### Solution 1. VIEW, MATERIALIZED VIEW, Aggregate Table

A regular VIEW is a query definition evaluated at read time without its own result store. A MATERIALIZED VIEW stores physical results and needs REFRESH to update. An application/trigger/event-maintained aggregate table has custom sync logic and can apply deltas, unlike core REFRESH.

### Solution 2. Stale Data

No. The materialized view still reflects the snapshot materialized at 08:00. Rows committed at 08:10 do not appear automatically; a REFRESH must run and capture a snapshot containing them.

### Solution 3. Syntax

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue;

REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue;
```

The second command is valid only when the view is populated and has a qualifying UNIQUE index.

### Solution 4. WITH DATA

No difference in default behavior: `REFRESH MATERIALIZED VIEW v` implies `WITH DATA`. Both run the defining query to update stored data and leave the view scannable.

### Solution 5. WITH NO DATA

No. `WITH NO DATA` leaves the view **unscannable**. SELECTs raise an error rather than returning a valid 0-row result set.

### Solution 6. CONCURRENTLY with NO DATA

Invalid. PostgreSQL forbids combining both options. `CONCURRENTLY` refreshes an already-populated view without blocking SELECTs, rather than making it unscannable.

### Solution 7. Populated Can Have 0 Rows

Yes. `REFRESH ... WITH DATA` populated the query cleanly, setting `ispopulated=true` even with 0 rows. Concurrent refresh still needs a valid UNIQUE index; the rule is populated state, not `COUNT(*) > 0`.

### Solution 8. Qualifying UNIQUE Index

The index must:

1. Be on the **materialized view itself**.
2. Be **UNIQUE** and valid.
3. Key solely on **column names**, not expressions.
4. Cover **all rows**, with no partial `WHERE` predicate.

In addition, the view must already be populated.

### Solution 9. Source PK Is Insufficient

A materialized view is its own relation with its own output rows; GROUP BY and JOINs alter row identity. `REFRESH CONCURRENTLY` requires a UNIQUE index **on the view itself**, not just on source tables.

### Solution 10. Composite Key

A tenant can have reports across multiple days, so `UNIQUE(tenant_id)` is wrong and fails.

```sql
CREATE UNIQUE INDEX ux_example_daily_revenue
ON mv_refresh_lab.daily_revenue (tenant_id, sale_date);
```

If `ux_daily_revenue_tenant_day` already exists, a second identical index is redundant; this snippet simply demonstrates the right key.

### Solution 11. Expression Index

No. An index on `lower(email)` is an **expression index**, not the column-only UNIQUE index required by `CONCURRENTLY`. It helps other queries, not concurrent refresh.

### Solution 12. Partial Index

No. `WHERE active` covers only a subset of rows. `CONCURRENTLY` requires a UNIQUE index covering the entire materialized view.

### Solution 13. Non-Unique Index

No. `CREATE INDEX` does not guarantee uniqueness. At least one qualifying UNIQUE index is required regardless of how many non-unique read indexes exist.

### Solution 14. Bootstrap

```sql
-- 1. Create unpopulated view:
-- CREATE MATERIALIZED VIEW ... AS SELECT ... WITH NO DATA;

-- 2. Initial population, NOT CONCURRENTLY:
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue_later WITH DATA;

-- 3. Create index if not yet present:
-- CREATE UNIQUE INDEX ...
-- ON mv_refresh_lab.daily_revenue_later (tenant_id, sale_date);

-- 4. Subsequent runs:
REFRESH MATERIALIZED VIEW CONCURRENTLY
    mv_refresh_lab.daily_revenue_later;
```

Section 9 has the complete sequence. This assumes `daily_revenue_later` was created `WITH NO DATA`, indexed in step 3, and populated before step 4.

### Solution 15. Revenue Change

Before REFRESH: **150.00** because the materialized view is stale. After REFRESH capturing the new 25 order: **175.00** and `paid_orders=3`.

### Solution 16. New Group

Tenant 2, `2026-11-02` gets row:

```text
tenant_id=2
sale_date=2026-11-02
revenue=110.00
paid_orders=1
```

The pending 30 order is excluded by `WHERE status='paid'`.

### Solution 17. Updating Pending to Paid

After changing 30 to paid and refreshing with a new snapshot:

```text
revenue=140.00
paid_orders=2
```

Post-refresh results replace the prior materialized values (110, 1).

### Solution 18. Disappearing Group

No. With zero `status='paid'` rows remaining in that group, the paid-only `GROUP BY` produces no row for it. After refresh, that `(tenant_id, sale_date)` row disappears rather than remaining with revenue 0.

### Solution 19. ACCESS EXCLUSIVE

Standard REFRESH takes **ACCESS EXCLUSIVE** on the materialized view. Normal SELECT needs `ACCESS SHARE`; the two modes conflict, blocking SELECTs.

### Solution 20. EXCLUSIVE

`REFRESH CONCURRENTLY` takes **EXCLUSIVE** on the materialized view. Normal SELECT takes `ACCESS SHARE`; these two modes are compatible, allowing concurrent MVCC reads.

### Solution 21. Transaction Holding Locks

In PostgreSQL, locks remain held until **COMMIT/ROLLBACK**. Even after REFRESH finishes computing, open transaction A holds `ACCESS EXCLUSIVE`, blocking Session B. Never leave REFRESH sessions idle in transaction.

### Solution 22. Snapshots During Concurrent Refresh

Session B never sees uncommitted refresh data. It reads its MVCC snapshot of the materialized view; once refresh commits, new queries with fresh snapshots see the new dataset. A `REPEATABLE READ` transaction with an older snapshot keeps seeing pre-refresh data.

### Solution 23. Timestamp Is Not a Watermark

No. If the refresh's source snapshot was captured before the 10:01 commit, that transaction is absent even though the refresh finished at 10:03. Track a source cutoff/watermark to know exact completeness.

### Solution 24. ORDER BY

No. REFRESH does not guarantee preserving the defining query's `ORDER BY` order. SELECT needs:

```sql
SELECT *
FROM mv_refresh_lab.top_sales_demo
ORDER BY amount DESC, sale_id DESC;
```

Assuming `top_sales_demo` from Section 14 exists. Adding `sale_id` as a tie-breaker makes ordering deterministic.

### Solution 25. Scheduler Overlap

No. A materialized view supports only **one refresh at a time**, even with `CONCURRENTLY`. Schedulers should skip/coalesce overlapping runs, log last success/duration, enforce timeouts, and alert when durations exceed cadence.

### Solution 26. Refresh Frequency

Do not schedule every minute when p99 duration is 8 minutes without overlap protection. Evaluate:

- 10-minute freshness SLA.
- p50/p95/p99 durations.
- Source commit/ETL completion timing.
- Lock/queue wait times.
- CPU, I/O, temp, and WAL costs.
- Failure backoff.

If full refreshes cannot meet the SLA, optimize the source query or switch to incremental updates.

### Solution 27. pg_matviews

```sql
SELECT
    schemaname,
    matviewname,
    ispopulated,
    hasindexes
FROM pg_matviews
WHERE schemaname = 'mv_refresh_lab'
  AND matviewname = 'daily_revenue';
```

`pg_matviews` has no built-in `last_refresh_at` column for monitoring. Maintain separate job metadata/logs.

### Solution 28. pg_index

```sql
SELECT
    idx.relname AS index_name,
    i.indisunique,
    i.indisvalid,
    i.indexprs IS NULL AS no_expressions,
    i.indpred IS NULL AS full_index,
    pg_get_indexdef(i.indexrelid) AS definition
FROM pg_index AS i
JOIN pg_class AS idx ON idx.oid = i.indexrelid
WHERE i.indrelid =
    'mv_refresh_lab.daily_revenue'::regclass;
```

A qualifying candidate has `indisunique=true`, `indisvalid=true`, no expressions, and no partial predicate, on a populated view.

### Solution 29. pg_locks and Blockers

```sql
SELECT
    l.pid,
    l.relation::regclass AS relation_name,
    l.mode,
    l.granted
FROM pg_locks AS l
WHERE l.relation =
    'mv_refresh_lab.daily_revenue'::regclass
ORDER BY l.pid, l.mode;

SELECT
    a.pid,
    pg_blocking_pids(a.pid) AS blocking_pids,
    a.wait_event_type,
    a.wait_event
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

In the lab, `ACCESS EXCLUSIVE` blocks SELECTs; `CONCURRENTLY`'s `EXCLUSIVE` permits `ACCESS SHARE` while still conflicting with certain other operations.

### Solution 30. REFRESH Privileges

PostgreSQL **17+** uses the **`MAINTAIN`** privilege for `REFRESH MATERIALIZED VIEW`, while owners also hold maintenance rights. PostgreSQL **16 and older majors** require ownership (or role inheritance to the owner), so `GRANT MAINTAIN` syntax is invalid there.

### Solution 31. Not Real-Time

`CONCURRENTLY` keeps view SELECTs unblocked during refresh, **not** updating immediately on every source commit. Alternatives:

- Direct SELECT on transactional tables or source ledger.
- Summary table maintained in the same transaction.
- Event-driven read model with explicit consistency contracts and versions/watermarks.

Financial requirements must specify consistency guarantees, not just average latency.

### Solution 32. EXPLAIN and Duration

`EXPLAIN (ANALYZE, BUFFERS)` on the defining SELECT measures filters, JOINs, GROUP BYs, row counts, I/O, and plan nodes. REFRESH also writes/diffs materialized storage and maintains indexes, so measure **actual REFRESH execution duration** and resource/lock metrics for total cost.

### Solution 33. Refresh Chain

Order:

```text
1. Source sales ingestion completed
2. REFRESH mv_day, confirm success
3. REFRESH mv_month, confirm success
4. Publish report/dashboard state
```

Because `mv_month` reads `mv_day`, refreshing monthly before daily leaves monthly stale; `CONCURRENTLY` does not enforce dependency order automatically.

### Solution 34. Do Not Use DISTINCT Carelessly

No. Two real transactions can share `(tenant_id,sale_date,amount)`. `DISTINCT` collapses them into one, losing rows and revenue. Include `transaction_id` for transaction-level views, or `GROUP BY` the grouping key with `SUM`/`COUNT` for summary views.

### Solution 35. Invalid Unique Index

This is a **structural failure**, not transient. Retrying every second wastes resources without fixing the index. Log the error, alert operators, check `pg_index.indisvalid`, and repair the index or key data before retrying.

### Solution 36. WITH NO DATA

The view becomes **unscannable**, causing SELECTs to error rather than returning 0 rows. Recover with:

```sql
REFRESH MATERIALIZED VIEW
    mv_refresh_lab.daily_revenue WITH DATA;
```

Once populated again with a qualifying UNIQUE index, `CONCURRENTLY` works on later refreshes.

### Solution 37. Two CONCURRENTLY Commands

- `CREATE UNIQUE INDEX CONCURRENTLY`: builds an index minimizing blocking, **cannot run inside an explicit transaction block**.
- `REFRESH MATERIALIZED VIEW CONCURRENTLY`: refreshes a populated materialized view with a qualifying UNIQUE index while keeping SELECTs unblocked.

Check transaction rules separately for each command.

### Solution 38. Refresh Log

A metadata table can track:

```text
view_name
last_started_at
last_succeeded_at
last_duration_ms
last_status
last_error
source_watermark
```

The finish timestamp records when the job completed. It does not indicate when the source query's snapshot was taken, so it cannot prove every source commit before finish time was included.

### Solution 39. JDBC Jobs

If every dashboard GET triggers REFRESH, concurrent requests duplicate work, queue behind locks, and time out because only one refresh runs per view at a time. Use an independent job worker with version-appropriate maintenance grants, a separate SELECT role for the API, timeouts/monitoring, overlap skipping, and `last_success` reporting.

### Solution 40. Choosing a Mode

`REFRESH MATERIALIZED VIEW CONCURRENTLY` is the right candidate to test first because:

- The dashboard serves continuous readers.
- A stable grouping key qualifies for a UNIQUE index.
- 15-minute lag is acceptable.
- Only a small percentage of output rows change.
- A 4-minute refresh fits the cadence cleanly when coordinated.

Measure reader latency during refresh, p95/p99 refresh duration, WAL/temp/I/O/CPU, changed row counts, overlap rates, `last_successful_refresh`, and true watermarks. Never promise `CONCURRENTLY` is faster or meets SLAs without benchmarking.

## 40. Deployment Checklist for REFRESH MATERIALIZED VIEW

Verify every category before promoting jobs to production.

### 40.1. Data Definition

1. Does the defining query match report business semantics?
2. Do JOINs duplicate rows before GROUP BY?
3. Is there a business or grouping key uniquely identifying every output row?
4. Can late arrivals, corrections, or state transitions alter historical data?
5. Are snapshot timing and watermarks clearly understood and surfaced?

### 40.2. CONCURRENTLY Eligibility

6. Is `ispopulated=true`?
7. Does a UNIQUE index exist **on the view itself**?
8. Is the UNIQUE index valid and column-only?
9. Does it cover all rows with no `WHERE` clause?
10. Do key columns have safe NULL semantics?
11. Are you starting from `WITH NO DATA` or an unpopulated view?
12. Does the scheduler prevent overlapping refreshes on the same view?

### 40.3. Performance

13. Measured the source query with `EXPLAIN` on realistic data?
14. Benchmarked standard vs. `CONCURRENTLY` refresh durations on representative workloads?
15. Measured SELECT latency while refresh runs?
16. Provisioned enough disk, temp space, and WAL bandwidth for peak refreshes?
17. Do read indexes on the view justify their maintenance cost?
18. Measured planning and execution times of key dashboard queries?
19. Checked whether long-running transactions hold locks or old versions?

### 40.4. Freshness and Operations

20. How is the freshness SLA defined and measured?
21. Does the job wait for ETL/source ingestion completion?
22. Are `started`, `succeeded`, `failed`, and `duration` logged?
23. Is a source watermark tracked if completeness proof is required?
24. Do alerts fire when successful refreshes go overdue?
25. Are backoff, skip/coalesce, and bounded retries configured for transient errors?
26. Are runbooks ready for invalid unique indexes, unpopulated states, or source schema changes?
27. Is degraded stale serving vs. fallback behavior defined if refreshes fail?

### 40.5. Privileges and Security

28. Does the worker hold `MAINTAIN` (PG17+) or proper ownership for older majors?
29. Do dashboard roles hold only required `SELECT`?
30. If the view stores sensitive data, are access controls and export policies enforced?
31. Do index/view DDLs have maintenance windows and rollback plans?
32. Are synchronous refreshes avoided inside HTTP GETs and long transactions?
33. Do logs avoid leaking SQL literals, secrets, or sensitive row values?

## 41. Quick Reference Table

| Issue | Solution / Warning |
| --- | --- |
| Refresh a materialized view | `REFRESH MATERIALIZED VIEW schema.view;` |
| Keep SELECTs running during refresh | `REFRESH MATERIALIZED VIEW CONCURRENTLY schema.view;` |
| View created `WITH NO DATA` | Initial refresh must be standard `WITH DATA`. |
| `CONCURRENTLY` rejected | Check populated status and qualifying UNIQUE index. |
| Only non-unique `CREATE INDEX` exists | Insufficient; requires a valid UNIQUE index. |
| Only expression UNIQUE index exists | Insufficient for `CONCURRENTLY`. |
| Only partial UNIQUE index exists | Insufficient for `CONCURRENTLY`. |
| Refresh only one tenant | Standard REFRESH has no `WHERE tenant_id` parameter. |
| Find last refresh time | Use job metadata/logs, not `pg_matviews` alone. |
| View has `ORDER BY` in definition | Client SELECTs still require explicit `ORDER BY`. |
| Standard refresh blocks SELECTs | Acquires `ACCESS EXCLUSIVE` on the view. |
| Concurrent refresh still locks | Acquires `EXCLUSIVE`, compatible with SELECT `ACCESS SHARE`. |
| Run parallel refreshes on same view | Forbidden; coordinate via scheduler. |
| Need real-time results | Query live tables or use transactional/incremental summary tables. |
| Missing new data despite refresh success | Check snapshot/watermark/ETL timing and query definition. |
| Permission denied | `MAINTAIN` on PG17+; ownership on older majors. |

## 42. Summary

**Materialized views speed up repeated read queries by persisting precomputed results.** In return, data never auto-updates when source tables change; PostgreSQL requires **`REFRESH MATERIALIZED VIEW`** to recompute and publish fresh output.

Key takeaways:

- **Standard REFRESH** can use fewer resources and fits initial population or off-hours batches, yet holds **`ACCESS EXCLUSIVE`** on the materialized view and blocks SELECTs.
- **`REFRESH CONCURRENTLY`** lets normal SELECTs keep reading during refresh via an **`EXCLUSIVE`** lock compatible with `ACCESS SHARE`, though it still incurs recomputation/diffing overhead and other locks.
- **`CONCURRENTLY` requires both prerequisites**: the view must already be populated, **and** it must have at least one **column-only, full-coverage UNIQUE index on the view itself**.
- **`CONCURRENTLY` cannot combine with `WITH NO DATA`**, cannot bootstrap an unpopulated view, and does not permit two simultaneous refreshes on the same view.
- **REFRESH is not incremental maintenance by default**: the defining query recomputes and results are replaced or diffed. Avoid full refreshes after every INSERT on write-heavy tables.
- **Freshness is a business decision.** Readers during concurrent refresh still see old data; finishing at 10:00 does not prove all commits through 10:00 are included.
- **`ORDER BY` inside the view definition does not guarantee SELECT order** after refresh; clients must write `ORDER BY` when ordering matters.
- **Build your own monitoring:** `pg_matviews` shows populated/index flags and `pg_stat_activity`/`pg_locks` diagnose waits, while successful refresh timestamps and watermarks belong in job runner logs.
- **REFRESH privileges depend on major version:** PostgreSQL 17+ introduces `MAINTAIN`, while older majors require appropriate ownership.
- **Pick modes by workload:** benchmark reader wait time, refresh runtime, CPU/I/O/WAL/temp space, change rate, and schedule feasibility; never assume `CONCURRENTLY` is always faster.

Practical rule of thumb:

> **Use materialized views when batch-refreshed lag is acceptable; use `CONCURRENTLY` when SELECT availability during refresh matters and a valid UNIQUE key exists.**

If the requirement is *every read sees the transaction that just committed*, the problem is **transactional consistency/aggregation**, not adding the `CONCURRENTLY` keyword.

## 43. References

Official PostgreSQL documentation (match links to your running major version):

- [REFRESH MATERIALIZED VIEW — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-refreshmaterializedview.html): syntax, `CONCURRENTLY` prerequisites, `WITH NO DATA`, and ordering limits.
- [CREATE MATERIALIZED VIEW — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-creatematerializedview.html): creating views and `WITH DATA/NO DATA`.
- [Materialized Views — PostgreSQL Documentation](https://www.postgresql.org/docs/current/rules-materializedviews.html): persistence behavior and aggregation examples.
- [CREATE INDEX — PostgreSQL Documentation](https://www.postgresql.org/docs/current/sql-createindex.html): UNIQUE indexes, expressions, partial indexes, and `CONCURRENTLY` builds.
- [Explicit Locking — PostgreSQL Documentation](https://www.postgresql.org/docs/current/explicit-locking.html): `ACCESS SHARE`, `EXCLUSIVE`, and `ACCESS EXCLUSIVE`.
- [REFRESH MATERIALIZED VIEW — PostgreSQL 16](https://www.postgresql.org/docs/16/sql-refreshmaterializedview.html): owner privilege model on older majors.
- [REFRESH MATERIALIZED VIEW — PostgreSQL 17](https://www.postgresql.org/docs/17/sql-refreshmaterializedview.html): `MAINTAIN` privilege on newer majors.
