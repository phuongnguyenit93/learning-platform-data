# Summary Tables, Counters, and Precomputed Results

## Learning Objectives

After this lesson, you will be able to:

- Distinguish **summary tables (aggregate tables)**, **stored counters**, and **precomputed results** by purpose, data unit, and update mechanism.
- Design keys, data *grain*, formulas, measurement units, timestamps, and constraints for a verifiable summary table.
- Choose among query-time computation, materialized views, synchronous transactional updates, and asynchronous event-driven updates.
- Avoid common bugs such as double counting, lost updates, wrong-day attribution, summing mismatched currencies, duplicate event processing, and mishandled historical edits.
- Measure read benefits alongside write costs, locking, storage, sync lag, reconciliation, and rebuild capability before denormalizing.

This lesson belongs to the **Denormalization** chapter of **DATABASE_DATA_MODELING**. It puts into practice turning business requirements into entities, relationships, constraints, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical structures so that data stays accurate, evolvable, and verifiable.

## 1. Three Ways to Pre-Store Results: Similar Goals, Different Natures

A system has **orders** and **order_items** tables. The application may need to display an order's total, a customer's order count, or daily revenue. These values can be **computed from detail records**, yet are sometimes stored separately to shorten the read path.

| Form | Example | Data Grain | Read Pattern Improved |
| --- | --- | --- | --- |
| **Precomputed result** | **orders.items_subtotal** | One value per order | View order lists without summing multiple line items |
| **Counter** | **user_stats.follower_count** | One value per user | Display follower count without counting relationship rows |
| **Summary table** | **daily_capture_summary** | One row per day × currency | Dashboards avoid aggregating individual transactions |
| **Materialized view** | Refreshed daily payment totals | One row per group in the SELECT query | Query results precomputed as of the refresh timestamp |

All of these forms can be **intentional denormalization** when backed by a measured read need, unambiguous semantics, and correctness guarantees. They become uncontrolled redundancy when multiple copies update independently without a designated source of truth.

**Not every piece of data that looks "aggregated" is a copy.** For example, the confirmed unit price on an invoice line is a historical fact with its own semantics, distinct from a product's current price. Before deciding whether to store or recompute, clarify whether the data is a source fact, a historical snapshot, or a derived result.

## 2. Start with the Business Question and Data Grain

Suppose a dashboard needs to answer: "Each day, how many **successful payment captures** occurred, and what was the total captured amount, broken down by currency?"

Define the rules precisely:

- **Counted event:** a successful *capture*, not automatically an order. One order may have multiple captures if business rules permit.
- **Amount:** sum of capture **amount**s; **not** net revenue after refunds.
- **Time:** calendar day in the **Asia/Ho_Chi_Minh** timezone based on when the capture occurred. A late-arriving capture still belongs to the day the event occurred.
- **Currency:** totals in VND and USD must reside in **separate groups**; never add them together directly without explicit conversion rules and exchange rates.
- **Status:** a confirmed capture event is immutable. Refunds generate separate refund events rather than silently mutating an existing capture.
- **Uniqueness:** each event is identified by a stable **event_id**; duplicate deliveries must be ignored or verified against already-stored data.

Under these assumptions, the summary table's **grain** is **(capture_day, currency)**. Each day-and-currency pair has at most one row, so that pair must be enforced by a primary key or unique constraint.

~~~text
payment_events (detailed event source)
  event_id
  payment_id
  captured_at
  currency
  amount
          |
          | COUNT and SUM by (local day, currency)
          v
daily_capture_summary (derived table)
  capture_day
  currency
  capture_count
  captured_total
~~~

If the system serves multiple organizations, **tenant_id** may need to become part of the grain and every related key: **(tenant_id, capture_day, currency)**. If dashboards need breakdowns by channel, location, or product, do not assume a day-only summary table is granular enough for every analysis. **Choosing too coarse a grain loses the ability to query omitted dimensions.**

### 2.1. Grain Must Match the Allowed Questions

| Report | Suitable Grain | What Cannot Be Safely Inferred |
| --- | --- | --- |
| Captures by day, currency | Day × currency | Number of **unique customers** without storing distinct-counting state |
| Sales by store/day | Store × day × currency | Sales by product once products are collapsed |
| Article views per hour | Article × hour | Exact timestamp of each individual view |
| Current cart value | Cart | Change history if only the latest value is kept |
| Count of orders **currently in PAID status** | Customer or day × current status | How many times an order ever transitioned to PAID |

**COUNT(*) is not COUNT(DISTINCT user_id).** When counting unique users across multiple days, summing daily distinct counts can double-count the same user across days. A sound design must store mergeable structures or explicitly state that the metric is approximate.

## 3. Read Directly from the Source Table Before Storing Totals

Example PostgreSQL schema for captures:

~~~sql
CREATE TABLE payment_events (
    event_id TEXT PRIMARY KEY,
    payment_id BIGINT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL,
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0)
);

CREATE INDEX idx_payment_events_captured_at
    ON payment_events (captured_at);
~~~

**payment_events** is the source of truth in this example. The **amount** column is assumed to be normalized to the currency's proper decimal precision before storage; in practice different currencies use different decimal scales, so **NUMERIC(18, 2)** is illustrative only. Real payment systems require per-currency representation and rounding rules.

Direct aggregation query:

~~~sql
SELECT
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS capture_day,
    currency,
    COUNT(*)::BIGINT AS capture_count,
    SUM(amount) AS captured_total
FROM payment_events
WHERE captured_at >= $1
  AND captured_at < $2
GROUP BY
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
    currency
ORDER BY capture_day, currency;
~~~

Here **$1** and **$2** are timezone-aware timestamps passed by the application, typically to bound the date range. Filtering directly on **captured_at** gives the optimizer an opportunity to use the index on the raw column. If user input is a local calendar date, convert start-of-day and end-of-day boundaries to exact timestamps before querying; never assume every day in every timezone is 24 hours long.

If the source table is not yet huge or the dashboard runs infrequently, the query above may be **fast enough and simplest**. Do not build summary tables merely because SUM/COUNT syntax appears. Measure frequency, p95/p99, CPU/I/O, scan time, and write-workload impact first.

## 4. Option A: Scheduled Refresh Materialized View

If multiple dashboards read the same aggregate and tolerate slight lag, a PostgreSQL **materialized view** stores the SELECT output and refreshes on demand.

~~~sql
CREATE MATERIALIZED VIEW daily_capture_mv AS
SELECT
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS capture_day,
    currency,
    COUNT(*)::BIGINT AS capture_count,
    SUM(amount) AS captured_total
FROM payment_events
GROUP BY
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
    currency
WITH NO DATA;

-- Initial refresh to populate the view:
REFRESH MATERIALIZED VIEW daily_capture_mv;

-- Unique index on the grain (not a partial or expression index):
CREATE UNIQUE INDEX ux_daily_capture_mv_grain
    ON daily_capture_mv (capture_day, currency);

-- Subsequent refreshes can use concurrent mode:
REFRESH MATERIALIZED VIEW CONCURRENTLY daily_capture_mv;
~~~

Keep these points clear:

1. PostgreSQL **does not automatically update** the materialized view when a new capture is inserted. A scheduled job or workflow must run **REFRESH**.
2. **CONCURRENTLY** has prerequisites, including an already-populated view and a qualifying unique index. It reduces read blocking compared to a standard refresh, yet still consumes substantial resources and does not make refreshes free.
3. A **REFRESH** builds results from a source-table snapshot at execution time. By the time it finishes, it may already lag behind newly committed transactions.
4. If the source table grows very large, scanning and recomputing the entire history every few minutes may exceed time, I/O, or resource limits. At that point, evaluate incrementally updated summary tables.

**Freshness** must be measured from when an event is written at the source until the updated value becomes readable. For instance, "refresh every 5 minutes" does not guarantee a 5-minute max lag if each refresh takes several minutes, queues up, or fails.

## 5. Option B: Incrementally Updated Summary Table in the Same DB

To avoid rescanning every capture, a summary table can be incremented by the contribution of **each newly accepted event**.

~~~sql
CREATE TABLE daily_capture_summary (
    capture_day DATE NOT NULL,
    currency TEXT NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    capture_count BIGINT NOT NULL DEFAULT 0
        CHECK (capture_count >= 0),
    captured_total NUMERIC(24, 2) NOT NULL DEFAULT 0
        CHECK (captured_total >= 0),
    PRIMARY KEY (capture_day, currency)
);
~~~

The primary key enforces one row per grain and enables **INSERT ... ON CONFLICT**. Choose a **NUMERIC** precision suited for monetary totals and guard against overflow as volume scales.

### 5.1. Increment Only When the Source Event Is Successfully Recorded

Example accepting a new capture:

~~~sql
WITH accepted AS (
    INSERT INTO payment_events (
        event_id, payment_id, captured_at, currency, amount
    )
    VALUES (
        'capture-2026-0001',
        9001,
        TIMESTAMPTZ '2026-11-22 08:00:00+07',
        'VND',
        150000.00
    )
    ON CONFLICT (event_id) DO NOTHING
    RETURNING captured_at, currency, amount
)
INSERT INTO daily_capture_summary (
    capture_day, currency, capture_count, captured_total
)
SELECT
    (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
    currency,
    COUNT(*)::BIGINT,
    SUM(amount)
FROM accepted
GROUP BY 1, 2
ON CONFLICT (capture_day, currency)
DO UPDATE
SET capture_count =
        daily_capture_summary.capture_count
        + EXCLUDED.capture_count,
    captured_total =
        daily_capture_summary.captured_total
        + EXCLUDED.captured_total;
~~~

This is **a single PostgreSQL statement**, so inserting the event and updating the summary occur within the same statement transaction. If the operation fails, both parts roll back together.

- If **event_id** does not exist yet, the **accepted** CTE returns one row: the summary increments by **1 capture** and **150,000 VND**.
- If the same **event_id** arrives again, **ON CONFLICT DO NOTHING** returns zero rows: the outer statement adds nothing. This ensures once-only effect **per event_id**.
- If two transactions concurrently increment the **(day, VND)** group, **DO UPDATE** adds to the existing stored value under PostgreSQL row locking, avoiding lost updates from reading stale values first.

Critical condition: every path creating source events must go through this protocol or an equivalent mechanism. If any writer runs a raw **INSERT** into **payment_events** without updating the summary, the invariant breaks.

**Idempotency is more than ignoring duplicate event_ids.** If two requests reuse the same ID with different amounts, timestamps, or currencies, the system must flag a data error instead of treating them as equivalent retries. Likewise, if one payment is emitted under **two different event_ids**, a unique constraint on event_id will not catch the business-level double count; enforce uniqueness on the authoritative transaction identifier if required.

### 5.2. Explicitly Stated Invariants

For every **(capture_day, currency)**:

> **daily_capture_summary.capture_count** = number of valid capture rows in **payment_events** belonging to that day and currency.

> **daily_capture_summary.captured_total** = sum of **payment_events.amount** across those exact rows.

These two invariants assume the **immutable** event source defined in Section 2. If the system allows editing or deleting recorded captures, you must design exact compensating adjustments. You cannot keep adding forever and still claim the table reflects current state.

## 6. Counters: Small in Storage, Easy to Break on Writes

Counters are typically a single column: **follower_count**, **unread_count**, **items_in_cart**, **open_ticket_count**. Reads are fast, but you must define **what is being counted**:

- **follower_count:** currently active follow relationships, or total times the follow button was ever clicked?
- **unread_count:** notifications currently unread, or notifications never opened even once?
- **open_ticket_count:** does it include snoozed or reopened tickets?
- **view_count:** counting every request, per session, or per unique user?

An ambiguous counter can increment and decrement cleanly in SQL while still being wrong for the business.

### 6.1. Example of an Accurate Follower Counter

In PostgreSQL, suppose each **(follower_id, followee_id)** pair represents at most one follow relationship:

~~~sql
CREATE TABLE user_stats (
    user_id BIGINT PRIMARY KEY,
    follower_count BIGINT NOT NULL DEFAULT 0
        CHECK (follower_count >= 0)
);

CREATE TABLE follows (
    follower_id BIGINT NOT NULL,
    followee_id BIGINT NOT NULL REFERENCES user_stats(user_id),
    PRIMARY KEY (follower_id, followee_id),
    CHECK (follower_id <> followee_id)
);
~~~

**user_stats** is initialized when the corresponding account is created. If **follower_id** validity must also be enforced, add a foreign key to the accounts table; the snippet above is kept minimal to demonstrate counter updates.

When following:

~~~sql
WITH new_follow AS (
    INSERT INTO follows (follower_id, followee_id)
    VALUES (101, 205)
    ON CONFLICT (follower_id, followee_id) DO NOTHING
    RETURNING followee_id
)
UPDATE user_stats AS us
SET follower_count = us.follower_count + 1
FROM new_follow
WHERE us.user_id = new_follow.followee_id;
~~~

The unique key prevents duplicate relationships; only an **INSERT** that actually succeeds increments the counter. **UPDATE ... SET follower_count = follower_count + 1** avoids the hazardous read-N-write-N+1 anti-pattern across concurrent requests. PostgreSQL serializes conflicting row updates via row locks and transaction control.

When unfollowing, use **DELETE ... RETURNING** and decrement only when a row was genuinely deleted, within the same transaction. Test concurrent follow/unfollow bursts, relationship changes, account deletions, and retries. If driven by asynchronous events, also account for event ordering and counter lag.

### 6.2. Counters Can Create "Hotspots"

A high-profile account may receive thousands of events per second. If every event executes **UPDATE user_stats** on the same row, that row becomes a lock-contention bottleneck. Options include:

- Accept the cost if actual frequency is modest and write p95 remains within SLO.
- Batch updates when business rules allow counter lag.
- Split the counter across multiple buckets (*sharded counters*) and sum shards on read or via periodic consolidation.
- Use stream processing or a read model for display counters while the relationship table remains the source of truth.

**Sharded counters** reduce single-row lock contention at the cost of reading more rows, complicating reconciliation, and handling duplicate events. They do not guarantee correctness automatically; you still need a consistency contract and rebuild mechanism.

## 7. Precomputed Results: Single-Row, Multi-Row, and Generated Columns

Not every precomputed value requires a dedicated summary table.

Suppose each order item has **quantity** and **unit_price_at_purchase**. Line total is a calculation **within a single row**:

~~~sql
CREATE TABLE example_order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_purchase NUMERIC(14, 2) NOT NULL
        CHECK (unit_price_at_purchase >= 0),
    line_total NUMERIC(18, 2)
        GENERATED ALWAYS AS
        (quantity * unit_price_at_purchase) STORED
);
~~~

A **STORED** generated column is computed by PostgreSQL from columns in the same row upon write; the application never assigns it directly. The expression must obey generated-column restrictions (such as using immutable expressions and permitted functions). This prevents **line_total** from being forgotten when **quantity** changes.

By contrast, an **order-level** total depends on **multiple rows**, so a single-row generated column cannot sum across rows the same way. Options include:

- Compute **SUM(line_total)** at read time if line counts are small or read traffic is moderate.
- Store **orders.items_subtotal** and update it transactionally on line inserts, edits, and deletes.
- Build a read model or summary table when data resides in another store or lag is allowed.
- Use a materialized view for batch analytical queries on an explicit refresh schedule.

If the total also includes discounts, taxes, shipping, refunds, or rounding, define the exact **formula and calculation order** before storing results. Never treat an ambiguously defined **total** column as authoritative for every payment decision.

### 7.1. Aggregates Behave Differently Under Updates

| Aggregate | On New Record | On Edit/Delete of Old Data |
| --- | --- | --- |
| **COUNT** | Can add increment if new event is verified unique | Must subtract once or recompute |
| **SUM** | Can add new value | Must apply delta between old and new values |
| **AVG** | Store **SUM** and **COUNT** and divide at read time | Must adjust both sum and count |
| **MIN/MAX** | New value may replace extreme | Deleting the extreme often requires scanning for the next extreme |
| **COUNT(DISTINCT)** | Must know if element already exists in group | Cannot blindly add/subtract subgroup distinct counts |
| **Median/percentile** | Usually needs distribution state or sketch structure | May require recomputation or approximate algorithms |

For example, averaging two daily averages yields the wrong answer if the days had different order counts. To compute an accurate monthly average, store **sum_amount** and **order_count**, then divide **sum of sum_amount / sum of order_count**. If storing approximate metrics like HyperLogLog or percentile sketches, document error bounds and forbid using them for exact financial decisions.

## 8. Late Events, Corrections, and Refunds

Time-based summary tables are especially error-prone when events arrive out of order.

**Late-arriving events:** a capture happens at 23:58 yesterday but reaches the system at 00:03 today. If the grain is based on **captured_at**, the event must be added to **yesterday's** bucket, not the day the worker processed it.

**Correcting timestamps or amounts:** if source records can be edited, you must subtract the old contribution from the old bucket and add the new contribution to the new bucket within an appropriate consistency boundary. Applying only a numeric delta to the new bucket misses movements across days or currencies.

**Refunds:** a refund does not necessarily reduce **captured_total**. If the metric means "gross captured total," preserve capture history, store refunds separately, and optionally define **net_amount = captured_total - refunded_total** per agreed semantics. Depending on business rules, refund reporting dates differ from capture dates; explicitly define whether reports follow **cash-flow event dates** or allocate back to the **original order date**.

**Status transitions:** "orders currently PAID" differs from "times an order transitioned to PAID." When an order moves from PAID to REFUNDED, the current-status count decreases while the historical transition count may stay unchanged. Model the state lifecycle and compensating updates instead of naming both **paid_count**.

**Source deletions:** if data deletion or anonymization policies apply, retaining aggregated summaries may or may not be permitted depending on data classification and policy. Determine whether summaries must be adjusted, whether rebuilds from source remain possible, and whether copies must also be purged.

## 9. Asynchronous Sync Between Source and Summary Table

When source data lives in a transactional system while summary tables reside in a data warehouse, search service, or document database, a single SQL transaction typically cannot atomically update both. An event pipeline can bridge them:

~~~text
Business write transaction + outbox (same database)
                 |
                 v
         Publisher / stream
                 |
                 v
    Consumer checks ID, version, and order
                 |
                 v
       Summary table / read model
                 |
                 v
     Reconciliation and replayability
~~~

A sound design must answer:

1. **How do we avoid losing events?** Write to an outbox in the same transaction as the source mutation, or use an event-publishing mechanism with equivalent guarantees.
2. **How do we avoid double counting?** Persist processed event IDs or use idempotent update logic tied to business identifiers.
3. **How do we handle out-of-order delivery?** Use source versions, per-aggregate ordering, or well-defined compensating/retroactive updates.
4. **How do we know how fresh metrics are?** Monitor watermarks, oldest unprocessed event age, queue backlog, and last projection update timestamp.
5. **How do we fix corrupted summaries?** Maintain a source of truth, support replay or backfill, run reconciliation, and halt read cutover if divergence exceeds threshold.

**At-least-once delivery** can deliver duplicate messages. "Exactly-once" at the transport layer does not automatically guarantee exactly-once business effects across multiple stores. For SUM and COUNT, reapplying a positive delta corrupts data, so idempotency must be enforced where totals are updated.

**Eventual consistency** is only viable when the business accepts a staleness window. Specify concrete thresholds and fallback behavior when breached: display "updated as of...", suspend critical metrics, or query the source directly when immediate numbers are needed.

## 10. Reconciliation Must Catch Both Missing and Extra Groups

Suppose we maintain **daily_capture_summary** in PostgreSQL. Recompute from source events and compare against stored values:

~~~sql
WITH expected AS (
    SELECT
        (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS capture_day,
        currency,
        COUNT(*)::BIGINT AS capture_count,
        SUM(amount) AS captured_total
    FROM payment_events
    GROUP BY
        (captured_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date,
        currency
)
SELECT
    COALESCE(a.capture_day, e.capture_day) AS capture_day,
    COALESCE(a.currency, e.currency) AS currency,
    a.capture_count AS stored_count,
    e.capture_count AS expected_count,
    a.captured_total AS stored_total,
    e.captured_total AS expected_total
FROM daily_capture_summary AS a
FULL OUTER JOIN expected AS e
    ON a.capture_day = e.capture_day
   AND a.currency = e.currency
WHERE a.capture_day IS NULL
   OR e.capture_day IS NULL
   OR a.capture_count IS DISTINCT FROM e.capture_count
   OR a.captured_total IS DISTINCT FROM e.captured_total
ORDER BY capture_day, currency;
~~~

**FULL OUTER JOIN** detects both grains present in the source yet missing from the summary table and orphaned grains sitting in the summary table. **IS DISTINCT FROM** safely compares NULLs as well. This query assumes a consistent source snapshot within the statement, identical day-boundary logic, identical event scope, and matching currency rules.

For asynchronous projections, do not immediately compare every newly committed event and declare copies broken: reconcile up to a **processed watermark/version**, or evaluate only buckets past the committed lag window. Periodic reconciliation should log divergent group count, total discrepancy, oldest divergence duration, and error rate, paired with a source-based recomputation workflow.

**A CHECK constraint on a summary row cannot verify SUM/COUNT against the source table.** It only enforces local predicates like non-negative counts; hence independent reconciliation and repair mechanisms remain essential.

### 10.1. Rebuilds and Backfills Must Not Clobber New Updates

If a live summary table requires full historical recalculation, never casually run **TRUNCATE** and reload while consumers are actively writing. Options depend on architecture:

- Compute into a shadow table up to a well-defined **snapshot/watermark**.
- Apply subsequent deltas occurring after that watermark, in order and without duplicates.
- Reconcile the new table against the source at the same watermark.
- Switch read traffic via a controlled cutover; monitor closely with rollback capability.
- Drop old data only after confirming zero remaining dependencies.

When backfilling per group, guard against an older job overwriting newly updated results. If historical source data changes, know which groups must be recomputed and under what rules.

## 11. Measuring Performance Before and After Denormalization

To choose an approach, document the **real access pattern**: key lookup vs. date-range scan, returned group count, dashboard frequency, event write rate/sec, concurrency, and latency bounds.

The table below contains **purely hypothetical numbers for decision practice**, not an actual benchmark:

| Metric | Aggregate on Read | Materialized View (5-min refresh) | Incremental Table per Event |
| --- | ---: | ---: | ---: |
| Dashboard p95 | 1,800 ms | 95 ms | 70 ms |
| Target p95 | ≤ 250 ms | ≤ 250 ms | ≤ 250 ms |
| Max observed data age | Near read time | 9 minutes | 18 seconds |
| Required freshness bound | ≤ 2 minutes | ≤ 2 minutes | ≤ 2 minutes |
| Extra write cost | None | Refresh load | Group UPDATE per event |
| Primary risk | Scanning deep history | Refresh overruns window | Hot row locks, duplicate events |
| Reconciliation / rebuild | Query source directly | REFRESH from source | Needs compensation, reconciliation, rebuild |

Under these assumptions, **the materialized view fails the 2-minute freshness requirement**, despite fast dashboard reads. The incremental summary table is a candidate if it maintains lag bounds, preserves correctness, and avoids overloading the write path—but you still must measure write p95/p99, lock queues, throughput, and growth. If the dashboard tolerated 10-minute staleness, the materialized view would be simpler and preferable.

Measure:

- **Reads:** p50/p95/p99, result size, CPU, block reads, queries per request.
- **Writes:** INSERT/UPDATE/DELETE p95/p99, WAL volume, rows updated, lock waits, deadlocks, retries.
- **Data quality:** divergent group count, duplicate events, late arrivals, summary age, recomputability.
- **Resources:** table/index footprint, refresh/rebuild cost, worker backlog, data growth.
- **Representative load:** normal vs. peak hours, skewed data, ultra-hot grains, historical edits/deletions.

An incremental summary table can turn scanning millions of events on read into **updating a single row thousands of times per second** on write. If all events update **(today, VND)**, row locking can become the bottleneck. You may need sharding, micro-batching, stream aggregation, or adjusting grain granularity—and re-verify correctness and freshness for each option.

## 12. Workload-Based Selection Map

| Business Need | What to Try First | When to Consider Derived Structures |
| --- | --- | --- |
| Sum a few lines per order | Indexed SUM query by order_id | Very hot read path after optimization, with transactional updates |
| Count follower relationships | Indexed COUNT on relationship table | Extremely frequent reads, huge counts; accurate follow/unfollow handling |
| Daily dashboard over millions of events | Bounded range filters, indexes, analytics store | High repetition and direct aggregation misses SLO |
| Dashboard tolerating several minutes of lag | Scheduled materialized view / refresh | When full refresh gets too costly or misses freshness |
| Near-instant dashboard under continuous writes | Incremental summary table or stream aggregation | Once idempotency, watermarks, compensation, and lag are proven |
| Informational view counts | Async counters, batching, or approximations | Must define clearly whether counting requests, sessions, or unique users |
| Monetary totals gating payments | Authoritative source and consistent transactions | Store totals only when sync and reconciliation meet strict guarantees |
| Multi-dimensional deep historical analysis | Grain-aligned fact/dimension model, OLAP | Pre-aggregation or materialized views for repeated query families |

In a **document** model, **comment_count** can live alongside an article document for fast list responses, provided every create/delete/hide comment action updates it accordingly. In a **graph** model, incoming edge counts can be stored on vertices for fast statistics, provided edge additions/removals adjust the counter. In **analytics** systems, daily aggregated fact tables pair with dimensions; manage grain, slowly changing dimensions, and late-arriving data.

No data model automatically eliminates the **source of truth – updates – consistency – reconciliation** problem. The right choice serves required queries with measurable cost and verified accuracy.

## 13. Design and Implementation Workflow

1. **State the use case and semantics:** phrase the question in business terms, distinguishing event counts, unique entities, current state, and historical facts.
2. **Define source of truth and grain:** choose unique keys per group, currency, timezone, status scope, tenant, and time window.
3. **Write the source-of-truth query:** define a re-runnable formula that computes the exact result; avoid relying on the summary table to verify itself.
4. **Measure baseline:** inspect EXPLAIN, indexes, API latency, frequency, and write load; try simple optimizations first.
5. **Select update mechanism:** same transaction, materialized view, batch job, or event/outbox; set maximum freshness lag.
6. **Enumerate all mutations:** inserts, edits, deletes, cancellations, refunds, status changes, retries, duplicates, late arrivals, and scale growth.
7. **Design idempotency and reconciliation:** business keys, versions/watermarks, observability metrics, rebuild procedures, and divergence handling.
8. **Controlled backfill:** populate history, catch up with live changes, and validate accuracy before switching reads.
9. **Compare under representative load:** reads, writes, lock contention, storage, lag, and recoverability.
10. **Review periodically:** if metrics see little use, source JOIN/SUM becomes fast enough, or pipelines cost too much, consider retiring the derived structure.

A contract for **daily_capture_summary** should state at minimum: **source = payment_events; grain = capture_day Asia/Ho_Chi_Minh × currency; count = unique capture count; amount = total captured per currency; sync mode = same DB and transaction; dedup key = event_id + appropriate business ID; reconciliation = recompute COUNT/SUM from source; recovery = recompute from a consistent watermark**.

## 14. Case Studies

### Case 1 — Is Averaging Averages Correct?

Day A has 2 orders worth 100 and 300. Day B has 8 orders worth 50 each. The dashboard stores Day A's average = 200 and Day B's average = 50. The team computes **(200 + 50) / 2 = 125** as the average across all 10 orders.

**Question:** Where is the math wrong? What should be stored in the summary table instead?

### Case 2 — Counter Incremented Twice

An app processes **FollowCreated** events with **UPDATE follower_count = follower_count + 1**. A consumer disconnects and receives the exact same event again after already committing the first time.

**Question:** Why is the counter wrong, and what is the minimal mechanism to fix it?

### Case 3 — Daily Dashboard with Two Currencies

A summary table only has key **capture_day** and one column **captured_total**. On Nov 22, captures total 200,000 VND and 30 USD. The dashboard sums them into **200,030** and labels it "daily revenue."

**Question:** Which dimension is missing from the model? If a single converted total is required, what rules must be added?

### Case 4 — Both Options Read Fast

A materialized view refreshed every 5 minutes achieves 90 ms read p95, but data ages up to 11 minutes when refreshes run long. An incremental summary table hits 65 ms read p95 and max 40 seconds of lag, yet when many transactions land on the same day, write p99 exceeds the SLO. The dashboard tolerates up to 15 minutes of staleness.

**Question:** Should you immediately pick the incremental table just for better freshness? What should you measure to decide?

### Suggested Solutions

1. Averaging averages **ignores order-count weights**. Day A totals 400, Day B totals 400; the true average across 10 orders is **800 / 10 = 80**. Store **sum_amount** and **order_count** (or sufficient state) to compute a weighted average.
2. The consumer applied the same delta twice. You need a stable event identifier, recording/checking processed status **within the same transaction boundary** as the summary update (or equivalent idempotent logic), plus handling cases where two distinct IDs represent the same business action.
3. **Currency** is missing from the grain. Group separately by currency; if currency conversion is needed, specify exchange rates, effective timestamp, rate source, target unit, and rounding rules.
4. **Do not select the incremental table yet** while it violates the write SLO. The materialized view may fit if 11-minute lag stays safely within the 15-minute bound and refreshes stay stable under representative load. Measure worst-case lag, write p95/p99, refresh overlap, lock contention, recoverability, and accuracy; then choose the simplest option meeting every constraint.

## 15. Takeaways

**Summary tables, counters, and precomputed results are contracts between source data and derived data.** Sound design begins with **grain**, units, count/sum definitions, effective timestamps, and unique keys—only then choosing storage and update mechanisms.

Before caching SUM/COUNT values for fast reads, answer three questions: **"What exactly is being calculated?", "When source data changes, by what rules does this value change?", and "How do we recompute it, detect drift, and recover?"** If you cannot answer all three, optimizing the query first is safer than introducing a summary table you cannot verify.
