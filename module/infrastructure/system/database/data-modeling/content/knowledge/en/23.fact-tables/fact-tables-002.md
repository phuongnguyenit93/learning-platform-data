# Transaction, Periodic Snapshot, and Accumulating Snapshot Fact Tables

## Learning Objectives

After this lesson, you will be able to:

- Explain the three common types of **fact tables** in analytical modeling: **transaction fact**, **periodic snapshot fact**, and **accumulating snapshot fact**.
- Write an accurate **grain**—what a single row represents—before choosing columns, keys, measures, and dimensions.
- Choose the appropriate table type for questions about **events that occurred**, **point-in-time states**, or **progress of a multi-step workflow**.
- Distinguish **additive**, **semi-additive**, and **non-additive** measures; avoid summing inventory across multiple days or double-counting workflow instances.
- Design business keys, timestamps, incomplete cases, update mechanisms, late-arriving data handling, and reconciliation rules for each fact type.
- Read and implement PostgreSQL examples for warehouse movements, end-of-day inventory, and delivery progress; write KPI queries without mixing grains.
- Evaluate implementations across relational/columnar warehouses, document stores, graph databases, and analytics pipelines while keeping the authoritative transactional source separate.

In the **DATABASE_DATA_MODELING** module, systems must turn business requirements into clear, verifiable data models. On the write path, warehouse receipt/dispatch transactions must preserve exact quantities. On the analytical path, a manager might ask **"how many dispatches happened yesterday?"**, **"how much stock remained at the end of each day?"**, or **"how long did each package take from intake to successful delivery?"** These three questions have different time axes, counting semantics, and update patterns. That is why this chapter distinguishes three types of **fact tables**, rather than cramming every metric into a single table with status and timestamp columns.

## 1. Start from the Grain and the Question Being Measured

A **fact table** stores measurements, milestones, or events that can be analyzed within a defined context. Foreign keys to **dimensions** enable grouping by date, product, warehouse, channel, employee, or status.

**Grain** is the exact statement of **one row** in the table. For example:

- "One row is **one recorded physical inventory movement** of a product at a warehouse."
- "One row is the **inventory state of a product at a warehouse at the end of a business day**."
- "One row is the **entire progress of one fulfillment attempt** from opening to completion."

Those are three different grains, even though all three share `productId`, `warehouseId`, and a timestamp. You must choose the grain **before** designing the table or writing a `SELECT`.

| Business Question | What Is an Appropriate Row? | Fact Type |
| --- | --- | --- |
| How many receipts, dispatches, and adjustments occurred today? | One inventory movement event | **Transaction** |
| Total units dispatched in the month? | One dispatch movement with signed quantity | **Transaction** |
| How much of product P remained in warehouse A at end of day 10/31? | One product–warehouse–date state | **Periodic snapshot** |
| How did end-of-week inventory change over time? | One snapshot at each week boundary, or daily snapshot selecting week-end dates | **Periodic snapshot** |
| How many packages are currently awaiting packing or handed over? | One fulfillment process at its current state | **Accumulating snapshot** |
| Average time from request intake to successful delivery? | One process with multiple timestamps | **Accumulating snapshot** |
| How many times did a package fail delivery and get retried? | One specific delivery attempt / status transaction | **Transaction** or separate event table |

There is no rule saying "each domain may use only one fact type." A warehouse typically has **multiple facts with complementary grains**, each serving a distinct class of questions.

## 2. Overview of the Three Ways to Record Facts

~~~mermaid
flowchart TB
    O["OLTP source: inventory and delivery"]
    O --> E["Committed events<br/>receipt / dispatch / adjustment"]
    O --> S["State at cutoff points<br/>end-of-day inventory"]
    O --> P["Lifecycle of one fulfillment<br/>requested → packed → handed over → delivered"]
    E --> F1["Transaction fact<br/>multiple rows per event"]
    S --> F2["Periodic snapshot fact<br/>one row per period"]
    P --> F3["Accumulating snapshot fact<br/>one row per process"]
~~~

| Aspect | Transaction Fact | Periodic Snapshot Fact | Accumulating Snapshot Fact |
| --- | --- | --- | --- |
| **Grain** | One event/transaction that occurred | One entity at a predetermined point/period | One execution of a milestone-based process |
| **Row Creation Cadence** | Whenever an event occurs | On a periodic cutoff schedule | When the process starts |
| **Post-Creation Updates** | Usually append; errors fixed via adjustment entries or ruled upserts | Period may be restated if late data arrives | **Typically updates the same row** as milestones are reached |
| **Timestamps** | Time the event occurred | Snapshot date/cutoff | Multiple timestamps for workflow steps |
| **Primary Measures** | Quantities/deltas, transaction amounts, event counts | Balances, on-hand stock, active entities at cutoff | Step latencies, cycle times, outcome status |
| **Row Count Means** | Count of events | Count of entity–periods | Count of process executions |
| **Row Present When No Activity?** | Usually no | May still have a row for an unchanged period | Yes, if the process is still open |
| **Common Pitfalls** | Retries creating duplicates, JOIN multiplication | Summing balances across days, missing periods | Inferring history from current state, collapsing multiple retries |

**The most important distinction is not physical append vs. update**, since technologies and ingestion policies can vary. The distinction lies in **grain semantics and the questions answered**.

## 3. Transaction Fact: Recording Each Event That Occurred

A **transaction fact** stores one row per business event or measurable transaction at the defined level of detail. In the warehouse example:

> One row = one change to the **on-hand quantity** of one product at one warehouse, after being successfully committed by the authoritative inventory source.

Each row may contain:

- **movementId**: unique, stable identifier for the movement event.
- **productKey, warehouseKey**: dimension foreign keys.
- **occurredAt, businessDate**: occurrence timestamp and business-calendar date.
- **movementType**: RECEIPT, DISPATCH, RETURN, ADJUSTMENT, etc.
- **quantityDelta**: signed quantity; positive for inflows, negative for outflows.
- **sourceVersion/sourceReference**: reconciliation metadata if provided by the source.

### Numerical Example

Product P in warehouse A starts the day with **10 units**:

| movementId | occurredAt | movementType | quantityDelta | Balance Immediately After Event |
| --- | --- | --- | ---: | ---: |
| M-201 | 09:00 | RECEIPT | +6 | 16 |
| M-202 | 11:30 | DISPATCH | −4 | 12 |

Net change for that day:

\[
\Delta Q_{\text{day}} = (+6) + (-4) = +2.
\]

If the opening balance is 10 and no movements are missing, the closing balance is \(10+2=12\). However, **two transaction fact rows do not by themselves tell you inventory at every point in time** if the opening balance is missing, a movement is missing, or a backdated adjustment is recorded late.

### Measure Additivity

- **SUM(quantityDelta)** is valid when computing net change over an interval or across a set of products with compatible units of measure.
- **SUM(CASE WHEN quantityDelta < 0 THEN -quantityDelta ELSE 0 END)** can compute total outbound quantity if the convention guarantees every negative value is a dispatch. In practice, filter by **movementType** because write-downs, shrinkage, and sales dispatches differ.
- **COUNT(*)** counts warehouse events, **not** products, orders, or packages.
- Receiving an event again due to a retry must not create a new movement. Reloads must preserve the **same movementId** or an equivalent source identifier.

### Append-Only and Error Correction

Transaction facts are usually designed close to **append-only**, though "usually" does not mean "never corrected." There are two ways to handle erroneous figures:

1. **Correction event:** write a signed adjustment record referencing the original event, preserving occurrence history. Suitable when the business source has the concept of adjusting entries.
2. **Restatement:** replace/rewrite an erroneous fact and rebuild dependent aggregates according to a published policy. Suitable when the source corrects previously ingested data.

Never both update the old row and append an adjustment record for the same error and **count both**. An official policy must specify which version is authoritative.

## 4. Periodic Snapshot Fact: State at a Recurring Cutoff

A **periodic snapshot fact** records one row for **one entity at one cutoff period**; the period can be a day, week, month, or shift.

> One row = the inventory state of product P at warehouse A **at the end of business day D**, under a uniform cutoff and timezone convention.

Common measures:

- **onHandQty**: physical quantity according to warehouse accounting rules.
- **reservedQty**: quantity committed to active reservations at the cutoff time.
- **availableQty = onHandQty - reservedQty**: quantity available to allocate under the example policy.
- Optionally `inventoryValueVnd` if valuation unit cost and valuation time are clearly defined.

In the example above, if end-of-day on-hand is 12 and reserved is 3, then available is 9:

| snapshotDate | product | warehouse | onHandQty | reservedQty | availableQty |
| --- | --- | --- | ---: | ---: | ---: |
| 2026-10-30 | P | A | 10 | 2 | 8 |
| 2026-10-31 | P | A | 12 | 3 | 9 |
| 2026-11-01 | P | A | 12 | 5 | 7 |

On a day with **no receipts or dispatches**, the transaction fact may have **0 rows**; the periodic snapshot still has a row showing end-of-day inventory. You must distinguish "no activity" from "missing data because the pipeline has not closed."

### Semi-Additive: Why Not SUM Inventory Across Days?

Suppose a report asks for **end-of-October inventory** of P at A. The answer is **12**, not \(10+12=22\). Adding 10 and 12 combines **two different points in time**, so it does not represent units coexisting simultaneously.

The measure `onHandQty` is typically **semi-additive**:

- Can be **summed across warehouses at the same point in time**, if all warehouses close under compatible cutoffs and share the same unit.
- Can be **summed across homogeneous products at the same point in time** when the business permits.
- **Cannot be summed across days** to get "monthly stock"; you must pick an end-of-period value, start-of-period value, or a clearly defined daily average.
- Summing quantities of items measured in different units (pieces, kg, boxes) can be **meaningless** even on the same day.

Monthly average daily inventory differs from end-of-month inventory:

\[
\text{AverageDailyOnHand}
= \frac{\sum_{d\in D}\text{OnHandAtEndOfDay}(d)}{|D|},
\]

where \(D\) is **the set of days with valid snapshots per policy**. If two days are missing due to a pipeline outage, do not blindly divide by 30 and implicitly treat missing days as 0. Choose a gap-filling rule, flag missingness, or wait for complete data.

### Dense or Sparse Snapshots?

- **Dense:** emit one row for every in-scope entity/period, even when values are unchanged or 0. Easier to report on, higher storage cost.
- **Sparse:** emit rows only while the entity is active or when values are non-zero. Saves space, but queries must account for the missing-row rule.

If a date has no snapshot, **NULL or a missing row does not automatically mean 0**. The product might not exist yet, the warehouse might be closed, the sparse scope might legitimately omit it, or data ingestion might have failed. Missing-data rules must be published before applying COALESCE.

## 5. Accumulating Snapshot Fact: One Row Moving Through Process Milestones

An **accumulating snapshot fact** fits workflows with a **relatively well-defined start, intermediate milestones, and completion**, such as:

- procurement request: submitted → approved → ordered → received;
- application review: applied → reviewed → accepted/rejected;
- delivery: requested → picked → packed → handed over → delivered;
- loan processing: application → underwriting → approval → disbursement.

In the delivery example:

> One row = **one fulfillment execution with a stable fulfillmentId**, from intake to completion. That row is updated as the process reaches new milestones.

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> PICKED
    PICKED --> PACKED
    PACKED --> HANDED_OVER
    HANDED_OVER --> DELIVERED
    REQUESTED --> CANCELLED
    PICKED --> CANCELLED
    PACKED --> CANCELLED
    DELIVERED --> [*]
    CANCELLED --> [*]
~~~

This is an illustrative workflow; real systems may involve multiple delivery attempts, partial deliveries, returns, or reopenings. When workflows branch and loop, the grain must be chosen carefully.

| fulfillmentId | requestedAt | pickedAt | packedAt | handedOverAt | deliveredAt | currentStatus |
| --- | --- | --- | --- | --- | --- | --- |
| F-101 | 10/10 08:00 | 10/10 08:12 | 10/10 08:30 | 11/10 09:00 | 11/10 16:00 | DELIVERED |
| F-102 | 10/10 09:00 | 10/10 09:20 | NULL | NULL | NULL | PICKED |
| F-103 | 10/10 10:00 | NULL | NULL | NULL | NULL | CANCELLED |

Each row above is **one process**, not one milestone. Row F-101 gets additional timestamps as business events occur. F-102 is not finished yet: **NULL means the milestone has not been recorded**, and must not be interpreted as a duration of 0.

### Measuring Cycle Times

For F-101:

- Intake → picking time: 12 minutes.
- Picking → packing time: 18 minutes.
- Handover → successful delivery: 7 hours.
- Total intake → successful delivery: 32 hours.

Time subtractions must use a consistent timestamp standard and explicit timezone. A milestone recorded late that actually occurred earlier in business operations must still use the verified **event time**, not the time the pipeline received the message.

### Why Multiple Date Columns Are Needed

An accumulating fact usually has multiple **role-playing date/time dimensions**: `requestedDate`, `pickedDate`, `packedDate`, `handedOverDate`, `deliveredDate`. They reference different temporal semantics of the same process. A single `createdAt` column is not enough to measure wait times across stages.

Typical metrics:

- Count of currently open / completed processes.
- On-time delivery rate among processes that have reached their due date.
- Distribution of time from intake to packing or to delivery.
- Count of processes currently stuck at picking and their processing age.

### When the Accumulating Model Does Not Fit

If a parcel has **multiple delivery attempts**, a single `deliveredAt` column cannot express the number of failed attempts or the time between attempts. You can:

1. Keep **one accumulating snapshot at the fulfillment grain** holding initial/final endpoints, paired with a separate transaction fact recording each delivery attempt.
2. Choose a **one-delivery-attempt grain** for the accumulating snapshot if each attempt has an independent lifecycle and needs its own KPIs.
3. Model detailed events and build a progress projection for the current operational view.

Do not create unbounded columns like `attempt1At`, `attempt2At`, `attempt3At` when the attempt count has no clear ceiling. A "one row per Order" grain can also be wrong if an Order splits into multiple separate shipments. **Grain must stick to the workflow unit that has its own ID and endpoint.**

## 6. Comparing Analytical Capabilities Across the Three Facts

A transaction table provides detailed event history, but deriving a snapshot requires opening balances, complete movements, adjustment handling, and cutoff rules. A periodic snapshot quickly answers end-of-day counts, yet **does not reveal every transaction** behind that number. An accumulating snapshot measures workflow durations conveniently, yet **loses loop details** unless transaction events are also stored.

| KPI | Preferred Source Fact | Formula / Watchouts |
| --- | --- | --- |
| Number of dispatches in a day | Transaction stock movement | `COUNT(*)` where `movementType = 'DISPATCH'` |
| Units dispatched in a month | Transaction stock movement | `-SUM(quantityDelta)` for `DISPATCH` rows |
| End-of-month on-hand stock | Periodic inventory snapshot | Select complete end-of-period snapshot |
| Average daily inventory | Periodic inventory snapshot | `AVG(onHandQty)` over days with complete data |
| Period-over-period stock change | Start/end snapshots + transaction reconciliation | `End - Start`; compare with `SUM(delta)` |
| Fulfillments currently in PACKED | Accumulating fulfillment | `COUNT(*) WHERE currentStatus = 'PACKED'` |
| Average time for delivered orders | Accumulating fulfillment | `AVG(deliveredAt - requestedAt)` for delivered set |
| Number of failed delivery attempts | Transaction fact `delivery_attempt` | One row per attempt/failure event |
| Fulfillments in PACKED at 17:00 on a past date | Event history or periodic process snapshot | Accumulating **only stores current state**, usually insufficient |

A common pitfall: using the current accumulating snapshot to build a chart of **how many orders were waiting in each status in the past**. Once F-101 is delivered, `currentStatus` no longer shows that it was in `PACKED` at 10:00 the previous day. For "as-of" history, you need status-transition events, periodic backlog snapshots, or effective-dated historical state.

## 7. Joining to Dimensions: Same Events, Three Different Grains

In a star schema, facts can share dimensions standardized in **analytical meaning** (*conformed dimensions*) such as product, warehouse, and date, without **merging the grains** of the three facts.

~~~mermaid
flowchart LR
    DP["dim_product<br/>product, category"]
    DW["dim_warehouse<br/>warehouse, region"]
    DD["dim_date<br/>business date"]
    FC["fact_stock_movement<br/>one movement"]
    FP["fact_daily_inventory<br/>one product-warehouse-date"]
    FA["fact_fulfillment_progress<br/>one fulfillment"]

    DP --> FC
    DW --> FC
    DD --> FC
    DP --> FP
    DW --> FP
    DD --> FP
    DW --> FA
    DD --> FA
~~~

Even dimensions with the same name require defining **temporal context**:

- A product changes category today: should historical reports group by category **at the time of dispatch** or **current** category?
- A warehouse switches management region: report by region at transaction time or today's regional structure?
- Is the snapshot date in **Vietnam time**, local warehouse time, or UTC? A business date does not necessarily match the UTC date.

If attributes at transaction time are required, the fact holds a key to the effective dimension version (*SCD Type 2*) or captures the needed snapshot attributes. If only current attributes are wanted, a different mapping can be used. Avoid joining on a business ID without historical qualification, which matches one fact row to multiple dimension versions and multiplies rows.

**Drill-across:** separate facts can be aggregated to the same dimensions/dates and then joined on their **aggregated results**. Never join movement rows directly to daily snapshot rows on `productId` and `warehouseId` and then SUM a measure, because a snapshot row gets repeated per movement.

## 8. Illustrative PostgreSQL Schema Design

The following examples use PostgreSQL to illustrate keys, grains, and constraints. An analytical data warehouse may use columnar storage and different key/partitioning mechanisms; this DDL is not the only or mandatory configuration for every DBMS.

### 8.1. Shared Dimensions

~~~sql
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE mart.dim_product (
    tenant_id UUID NOT NULL,
    product_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_product_id UUID NOT NULL,
    product_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, product_key),
    UNIQUE (tenant_id, source_product_id, valid_from),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE mart.dim_warehouse (
    tenant_id UUID NOT NULL,
    warehouse_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_warehouse_id UUID NOT NULL,
    warehouse_name TEXT NOT NULL,
    timezone_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, warehouse_key),
    UNIQUE (tenant_id, source_warehouse_id)
);
~~~

The product dimension uses a surrogate `product_key` to track different descriptive versions. The `UNIQUE (tenant_id, source_product_id, valid_from)` constraint **does not prevent two SCD intervals from overlapping**; the pipeline must validate non-overlap or use an appropriate range constraint. Warehouse `timezone_name` must come from a valid timezone registry and have a policy for when a warehouse changes its cutoff schedule.

### 8.2. Transaction Fact: One Inventory Movement

~~~sql
CREATE TABLE mart.fact_stock_movement (
    tenant_id UUID NOT NULL,
    movement_id UUID NOT NULL,
    product_key BIGINT NOT NULL,
    warehouse_key BIGINT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    business_date DATE NOT NULL,
    movement_type VARCHAR(16) NOT NULL
        CHECK (movement_type IN (
            'RECEIPT', 'DISPATCH', 'RETURN', 'ADJUSTMENT'
        )),
    quantity_delta BIGINT NOT NULL CHECK (quantity_delta <> 0),
    source_reference TEXT,
    load_batch_id UUID NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, movement_id),
    FOREIGN KEY (tenant_id, product_key)
        REFERENCES mart.dim_product(tenant_id, product_key),
    FOREIGN KEY (tenant_id, warehouse_key)
        REFERENCES mart.dim_warehouse(tenant_id, warehouse_key),
    CONSTRAINT valid_stock_movement_sign CHECK (
        movement_type = 'ADJUSTMENT'
        OR (movement_type IN ('RECEIPT', 'RETURN') AND quantity_delta > 0)
        OR (movement_type = 'DISPATCH' AND quantity_delta < 0)
    )
);

CREATE INDEX stock_movement_by_date
    ON mart.fact_stock_movement
        (tenant_id, business_date, warehouse_key, product_key);
~~~

One `movementId` appears only once per tenant, so re-running a batch must not create another movement for the same event. If the source emits one transaction containing multiple products/lines, you must identify the **movement line** (`movementLineId`) as the grain key rather than taking the transaction header ID and accidentally collapsing multiple lines into one.

### 8.3. Periodic Snapshot Fact: End-of-Day Inventory

~~~sql
CREATE TABLE mart.fact_daily_inventory (
    tenant_id UUID NOT NULL,
    snapshot_date DATE NOT NULL,
    product_key BIGINT NOT NULL,
    warehouse_key BIGINT NOT NULL,
    on_hand_qty BIGINT NOT NULL CHECK (on_hand_qty >= 0),
    reserved_qty BIGINT NOT NULL CHECK (reserved_qty >= 0),
    available_qty BIGINT NOT NULL CHECK (available_qty >= 0),
    snapshot_batch_id UUID NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (
        tenant_id, snapshot_date, product_key, warehouse_key
    ),
    FOREIGN KEY (tenant_id, product_key)
        REFERENCES mart.dim_product(tenant_id, product_key),
    FOREIGN KEY (tenant_id, warehouse_key)
        REFERENCES mart.dim_warehouse(tenant_id, warehouse_key),
    CHECK (reserved_qty <= on_hand_qty),
    CHECK (available_qty = on_hand_qty - reserved_qty)
);

CREATE INDEX daily_inventory_latest_by_product
    ON mart.fact_daily_inventory
        (tenant_id, product_key, warehouse_key, snapshot_date DESC);
~~~

The last two CHECK constraints reflect an **example policy: disallow reserving more than physical stock, and enforce `available = onHand - reserved`**. Real systems may compute available stock with damaged goods, quarantined stock, incoming stock, or backorder limits; in those cases, change the measures and formulas rather than assuming these CHECK constraints always hold.

The primary key on `(tenant, date, product, warehouse)` defines the grain accurately. To compute **as-of** inventory when `product_key` changes across SCD2 versions, the pipeline must assign the version valid at snapshot time or provide a mapping to `source_product_id`. Never accidentally count the same stock multiple times under two dimension versions on the same day.

### 8.4. Accumulating Snapshot Fact: Delivery Progress

~~~sql
CREATE TABLE mart.fact_fulfillment_progress (
    tenant_id UUID NOT NULL,
    fulfillment_id UUID NOT NULL,
    order_id UUID NOT NULL,
    origin_warehouse_key BIGINT NOT NULL,
    current_status VARCHAR(16) NOT NULL
        CHECK (current_status IN (
            'REQUESTED', 'PICKED', 'PACKED',
            'HANDED_OVER', 'DELIVERED', 'CANCELLED'
        )),
    requested_at TIMESTAMPTZ NOT NULL,
    picked_at TIMESTAMPTZ,
    packed_at TIMESTAMPTZ,
    handed_over_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    source_version BIGINT NOT NULL CHECK (source_version >= 0),
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, fulfillment_id),
    FOREIGN KEY (tenant_id, origin_warehouse_key)
        REFERENCES mart.dim_warehouse(tenant_id, warehouse_key),
    CHECK (delivered_at IS NULL OR delivered_at >= requested_at),
    CHECK (current_status <> 'DELIVERED' OR delivered_at IS NOT NULL),
    CHECK (current_status <> 'CANCELLED' OR cancelled_at IS NOT NULL)
);

CREATE INDEX fulfillment_open_by_warehouse
    ON mart.fact_fulfillment_progress
        (tenant_id, origin_warehouse_key, current_status, requested_at)
    WHERE current_status NOT IN ('DELIVERED', 'CANCELLED');
~~~

One `order_id` can map to **multiple fulfillmentIds** if an order is split into packages or reprocessed; do not add `UNIQUE(order_id)` just for query convenience. `source_version` prevents stale updates from overwriting newer state, yet **a version number does not automatically recover intermediate milestones if messages were lost**.

The DDL enforces minimal invariants, without proving every timestamp is chronologically ordered or every transition is valid. When redelivery, rerouting, or corrections happen, you must choose a concrete state machine and data-quality policy; a rigid CHECK requiring "every milestone strictly increasing" could wrongly reject valid timestamp corrections.

## 9. Querying the Right Fact Type for the Right KPI

### 9.1. Total Dispatches in a Date Range: Query the Transaction Fact

~~~sql
SELECT m.business_date,
       m.warehouse_key,
       m.product_key,
       COUNT(*) AS dispatch_events,
       -SUM(m.quantity_delta) AS dispatched_units
FROM mart.fact_stock_movement AS m
WHERE m.tenant_id = :tenant_id
  AND m.business_date >= DATE '2026-10-01'
  AND m.business_date <  DATE '2026-11-01'
  AND m.movement_type = 'DISPATCH'
GROUP BY m.business_date, m.warehouse_key, m.product_key
ORDER BY m.business_date, m.warehouse_key, m.product_key;
~~~

Do not SUM all negative `quantity_delta` rows and call it "units sold": a negative `ADJUSTMENT` or damaged write-off is not a `DISPATCH`. This is a KPI for **outbound warehouse movements**, not automatically identical to orders sold or revenue.

### 9.2. Period-End Inventory: Select Exactly One Snapshot per Combination

~~~sql
SELECT s.warehouse_key,
       s.product_key,
       s.on_hand_qty,
       s.reserved_qty,
       s.available_qty
FROM mart.fact_daily_inventory AS s
WHERE s.tenant_id = :tenant_id
  AND s.snapshot_date = DATE '2026-10-31';
~~~

When you need the latest date **with valid data** before a cutoff and are unsure whether 10/31 has a snapshot, you can retrieve the latest record **while explicitly exposing the actual date used**:

~~~sql
SELECT DISTINCT ON (s.warehouse_key, s.product_key)
       s.warehouse_key,
       s.product_key,
       s.snapshot_date AS actual_snapshot_date,
       s.on_hand_qty
FROM mart.fact_daily_inventory AS s
WHERE s.tenant_id = :tenant_id
  AND s.snapshot_date <= DATE '2026-10-31'
ORDER BY
    s.warehouse_key, s.product_key, s.snapshot_date DESC;
~~~

The condition **"latest available date" is not synonymous with "true month-end"**. If the 10/31 snapshot is missing, you need an incomplete-data flag or an approved fallback-date policy; never silently report 10/29 figures as 10/31 figures.

### 9.3. Cycle Time of Delivered Fulfillments

~~~sql
SELECT
    COUNT(*) AS delivered_fulfillments,
    AVG(
        EXTRACT(EPOCH FROM (delivered_at - requested_at)) / 3600.0
    ) AS avg_lead_time_hours,
    PERCENTILE_CONT(0.5) WITHIN GROUP (
        ORDER BY EXTRACT(EPOCH FROM (delivered_at - requested_at)) / 3600.0
    ) AS p50_lead_time_hours
FROM mart.fact_fulfillment_progress
WHERE tenant_id = :tenant_id
  AND current_status = 'DELIVERED'
  AND delivered_at >= TIMESTAMPTZ '2026-10-01 00:00:00+07'
  AND delivered_at <  TIMESTAMPTZ '2026-11-01 00:00:00+07';
~~~

The result measures **intake-to-delivery duration of fulfillments completed in October**, not the expected lead time of all fulfillments created in October. Those are two different cohorts. Measuring only completed cases can introduce **survivorship/selection bias** because very slow cases are still open and excluded.

To analyze overdue open cases, apply a cutoff condition at the reporting timestamp using `requested_at` and `current_status`, or maintain periodic backlog snapshots. Never treat a NULL `delivered_at` as 0 hours.

### 9.4. Reconciling Two Fact Types

With **complete** movement data, matching warehouse/product scope, and matching cutoffs:

\[
\text{OnHand}_{D}
=\text{OnHand}_{D-1}
+\sum_{\text{movements on day }D}\text{quantityDelta}.
\]

A query can detect discrepancies:

~~~sql
WITH movements AS (
    SELECT tenant_id, product_key, warehouse_key,
           SUM(quantity_delta) AS delta_qty
    FROM mart.fact_stock_movement
    WHERE tenant_id = :tenant_id
      AND business_date = DATE '2026-10-31'
    GROUP BY tenant_id, product_key, warehouse_key
)
SELECT curr.product_key,
       curr.warehouse_key,
       prev.on_hand_qty AS previous_on_hand,
       COALESCE(m.delta_qty, 0) AS movement_delta,
       curr.on_hand_qty AS current_on_hand,
       curr.on_hand_qty
         - prev.on_hand_qty
         - COALESCE(m.delta_qty, 0) AS unexplained_difference
FROM mart.fact_daily_inventory AS curr
JOIN mart.fact_daily_inventory AS prev
  ON prev.tenant_id = curr.tenant_id
 AND prev.product_key = curr.product_key
 AND prev.warehouse_key = curr.warehouse_key
 AND prev.snapshot_date = DATE '2026-10-30'
LEFT JOIN movements AS m
  ON m.tenant_id = curr.tenant_id
 AND m.product_key = curr.product_key
 AND m.warehouse_key = curr.warehouse_key
WHERE curr.tenant_id = :tenant_id
  AND curr.snapshot_date = DATE '2026-10-31'
  AND curr.on_hand_qty
    <> prev.on_hand_qty + COALESCE(m.delta_qty, 0);
~~~

This query only compares combinations that have **both snapshots** and does not catch completely missing dates or entities; completeness checks must run alongside it. It also assumes both snapshots and the transaction fact map to the **same `product_key`/`warehouse_key` versions**, and that every on-hand change is captured in the fact table. If SCD2 changes `product_key` across the two days, you must reconcile using the canonical source ID or historical mapping before applying the formula.

When backdated adjustments or cutoff timing differences exist, a mismatch is not necessarily a transactional source bug: check the time policy and finalized data cutoffs.

## 10. Handling Late-Arriving Data and Updating Accumulating Snapshots

The three fact types follow different update policies.

### Transaction Fact: Idempotent Ingestion

Ingest a stock event by the source's **movementId**. If the same `eventId` is retried, do not duplicate the event; if a different payload arrives for the same ID, check the versioning/correction workflow instead of silently ignoring it:

~~~sql
-- Illustration for data already mapped to the right dimensions.
INSERT INTO mart.fact_stock_movement (
    tenant_id, movement_id, product_key, warehouse_key,
    occurred_at, business_date, movement_type,
    quantity_delta, load_batch_id
) VALUES (
    :tenant_id, :movement_id, :product_key, :warehouse_key,
    :occurred_at, :business_date, :movement_type,
    :quantity_delta, :load_batch_id
)
ON CONFLICT (tenant_id, movement_id) DO NOTHING;

-- On conflict, the pipeline must compare hashes/fields of the existing row
-- or apply a versioning/correction policy at the ingestion layer.
~~~

`ON CONFLICT DO NOTHING` only protects against **inserting duplicate keys**; it does not verify that two payloads carry the same meaning. The pipeline must alert when the source resends the same ID with different data, or apply an authoritative update rule if the source permits corrections.

### Periodic Snapshot: Period Close and Restatement

A snapshot for day D is generated after cutoff from eligible data for day D. When movements for D arrive late, there are two options depending on the reporting contract:

- **Restate** snapshot D and subsequent affected snapshots, and refresh corresponding aggregates/report caches. Tag `load_version` or `snapshot_batch_id` for traceability.
- **Freeze** published periods and book adjustments into the next open period per accounting/business standards, providing a variance report if needed.

Never apply both inconsistently, as that double-counts adjustments. For **as-of historical** inventory reporting, altering closed periods requires versioning and reconciliation policies.

### Accumulating Snapshot: Updating the Row for the Same fulfillmentId

Scenario: F-101 is REQUESTED version 1, then PICKED version 2, PACKED version 3, HANDED_OVER version 4, DELIVERED version 5. If version 5 arrives before version 3, a naive UPDATE saying "only apply higher versions" could **miss `packedAt`** when version 3 later arrives.

A safe approach is to **build a complete projection of the process** from the source or ordered event log, then UPSERT the **entire state** with a newer `source_version`:

~~~sql
-- Input is a FULL reconstructed state snapshot:
-- all known milestones, including earlier ones, must appear in the incoming snapshot.
INSERT INTO mart.fact_fulfillment_progress AS target (
    tenant_id, fulfillment_id, order_id, origin_warehouse_key,
    current_status, requested_at, picked_at, packed_at,
    handed_over_at, delivered_at, cancelled_at, source_version
) VALUES (
    :tenant_id, :fulfillment_id, :order_id, :origin_warehouse_key,
    :current_status, :requested_at, :picked_at, :packed_at,
    :handed_over_at, :delivered_at, :cancelled_at, :source_version
)
ON CONFLICT (tenant_id, fulfillment_id)
DO UPDATE SET
    current_status = EXCLUDED.current_status,
    requested_at = EXCLUDED.requested_at,
    picked_at = EXCLUDED.picked_at,
    packed_at = EXCLUDED.packed_at,
    handed_over_at = EXCLUDED.handed_over_at,
    delivered_at = EXCLUDED.delivered_at,
    cancelled_at = EXCLUDED.cancelled_at,
    source_version = EXCLUDED.source_version,
    refreshed_at = CURRENT_TIMESTAMP
WHERE target.source_version < EXCLUDED.source_version;
~~~

This is **not** safe for an event carrying **only the newly changed field**: if `EXCLUDED.packed_at` is NULL because the Delivered event does not carry `packedAt`, that SQL wipes out the earlier milestone. To consume partial events, you must merge semantically and handle corrections, or accumulate/rebuild from event history.

If a gap in version numbers is detected, the pipeline can wait for missing events, request a full snapshot from the authoritative source, or mark the projection incomplete. A higher version number alone does not prove all intermediate business steps were observed.

### Separating Business Time from Ingestion Time

| Field | Meaning | Impact |
| --- | --- | --- |
| occurredAt / deliveredAt | Verified business timestamp | Report grouping, cycle-time measurement |
| businessDate / snapshotDate | Business-calendar date | Date filtering, cutoff, period comparison |
| recordedAt | Time recorded by source | Late-event reconciliation |
| loadedAt / refreshedAt | Time warehouse loaded or recomputed | Pipeline freshness and latency tracking |
| sourceVersion | State ordering from source, scoped to ID | Prevents stale records from overwriting newer ones |

Never overwrite `deliveredAt` with the ETL processing time to mask late-arriving events; doing so corrupts delivery-time KPIs.

## 11. Java Example: Preserving Identity and Business Date During ETL

A Java application may emit events after an OLTP transaction commits, or a Java pipeline may map events into fact tables. The following pure Java 17 snippet shows how to derive the **warehouse business date** from the **occurrence timestamp**, rather than using the consumer's receipt time:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.Objects;
import java.util.UUID;

record StockMovementEvent(
        UUID eventId,
        UUID tenantId,
        UUID productId,
        UUID warehouseId,
        Instant occurredAt,
        long quantityDelta) {
    StockMovementEvent {
        Objects.requireNonNull(eventId);
        Objects.requireNonNull(tenantId);
        Objects.requireNonNull(productId);
        Objects.requireNonNull(warehouseId);
        Objects.requireNonNull(occurredAt);
        if (quantityDelta == 0) {
            throw new IllegalArgumentException("No physical movement");
        }
    }
}

record MovementFactKey(UUID tenantId, UUID movementId) {}

record MovementProjection(
        MovementFactKey key,
        LocalDate businessDate,
        Instant occurredAt,
        long quantityDelta) {}

final class StockMovementFactMapper {
    static MovementProjection map(
            StockMovementEvent event, ZoneId warehouseZone) {
        Objects.requireNonNull(event);
        Objects.requireNonNull(warehouseZone);
        return new MovementProjection(
            new MovementFactKey(event.tenantId(), event.eventId()),
            event.occurredAt().atZone(warehouseZone).toLocalDate(),
            event.occurredAt(),
            event.quantityDelta());
    }
}
~~~

Notes:

- **The source `eventId`** is reused as `movementId` in the fact table so retries never generate a new key.
- `ZoneId` must reflect the **authoritative business convention and historical validity**; never hard-code the server's current timezone.
- If the business day closes at 04:00 instead of 00:00, adjust the classification function to the warehouse cutoff; `toLocalDate()` above only holds for midnight cutoffs.
- The mapper does not authorize inventory modifications. Stock reservation/transfer transactions must be confirmed in the **authoritative OLTP source**; fact tables exist purely for analytics.

## 12. Data Quality: Each Grain Requires an Ingestion Contract

When designing each fact table, establish a **data contract** covering events, periods, or processes:

| Item | Transaction | Periodic Snapshot | Accumulating Snapshot |
| --- | --- | --- | --- |
| Source Key | `movementId` or `transactionLineId` | `tenant + date + product + warehouse` | `tenant + fulfillmentId` |
| Uniqueness | One event is never counted twice | One snapshot per combination/period | One current row per workflow |
| Row Emission Rule | Event successfully committed | Closed period within scope | Workflow has started |
| NULL Handling | Reject/quarantine if essential fields missing | Missing row differs from zero value | Unreached milestones are NULL |
| Updates | Ruled correction/restatement | Replace period per policy | UPSERT workflow state |
| Freshness | Offset/LSN or event watermark | Snapshot completeness/cutoff | `source_version`, `refreshedAt` |
| Reconciliation | Quantities/event counts vs. source | Balances, entity counts, cutoff rules | Process counts, milestones, transition logs |

### Watchouts for Common Discrepancies

1. **Missing events:** a transaction fact missing one `DISPATCH` makes `SUM(delta)` diverge from snapshots; check for CDC errors or event definition bugs.
2. **Duplicate data:** the same `movementId` ingested twice because the pipeline minted a new ID on every retry.
3. **Missing snapshot rows:** day D has no records because a batch failed; a dashboard applying `COALESCE` to 0 makes stock look depleted.
4. **Grain mismatch in JOINs:** joining each daily snapshot to every movement on the same day, then `SUM(onHandQty)` multiplies stock by the movement count.
5. **Accumulating snapshot losing milestones:** keeping only the latest event or overwriting older milestones with NULL during an UPSERT.
6. **Wrong time axis:** using `loadedAt` to group delivery dates; late events shift into the wrong period.
7. **Split workflows:** one `orderId` has two fulfillments; using `orderId` as the accumulating snapshot key lets one package overwrite the other.
8. **Incompatible units:** summing kg with pieces, or summing amounts across currencies without a normalization policy.

### Testing the Design with Edge Cases

| Test Case | Expected Behavior |
| --- | --- |
| Replay M-201 with identical payload | Transaction fact still has exactly one row |
| Ingest M-201 with same ID but different delta | Alert/conflict or correction workflow, never silent miscounting |
| No warehouse activity on day D | Snapshot D still exists if dense design applies |
| Missing snapshot D due to batch failure | Missing-data status published; never treated as 0 |
| Movement for day D arrives late after close | Restatement/adjustment per policy; reports and reconciliation stay consistent |
| DELIVERED event arrives before PACKED | Accumulating snapshot does not erase milestones; controlled rebuild/deferral |
| Unshipped fulfillment | `deliveredAt` is NULL; delivery KPIs do not count it as 0 hours |
| Order split into two packages | Two distinct `fulfillmentId` values; never merged into one process |
| Joining movements and daily snapshots | Never sum inventory directly after joining at the transaction grain |

## 13. Storage Optimization by Fact Type and Workload

The three fact types exhibit distinct access patterns:

**Transaction facts** usually grow very rapidly. Partition by event time / business date if the DBMS and volume warrant it; cluster/sort by tenant, date, and heavily filtered dimensions. Avoid creating too many tiny partitions, and remember that corrections can touch older periods.

**Periodic snapshots** can exceed event counts during quiet periods if dense rows are generated for every product–warehouse–date. Decide on dense vs. sparse, compression, period partitioning, and retention policy. Queries often target **period-end/start** or period-over-period comparisons, so optimize access by date and entity.

**Accumulating snapshots** are typically smaller than event facts if each process has one row, but open cases are updated fairly frequently. Some columnar engines optimize appends over in-place updates, so pipelines may append to an event log and periodically **MERGE** in batches to produce the current snapshot. Historical snapshot versions can also be retained if past-date state views are needed.

Not every warehouse enforces `FOREIGN KEY` constraints like PostgreSQL, nor does every engine update single rows at the same cost. Choose indexes, partitions, micro-batches, and MERGE mechanisms based on the specific engine and measured benchmarks rather than copying OLTP optimizations wholesale into OLAP.

### Multiple Sources and Heterogeneous Timestamps

To analyze the "order → pick → deliver" chain, milestones may come from Sales, WMS, and carriers. You must align on:

- which identifier defines **one fulfillment attempt**;
- whether a milestone is recorded at **request time**, **execution confirmation**, or **physical event time**;
- how clock skew across sources is handled;
- versioning and authority to revise published milestones;
- whether SLAs measure business calendars or wall-clock elapsed time;
- when the warehouse can declare data **complete through** for reporting.

Without these definitions, a table full of timestamp columns can still yield wrong lead times.

## 14. Comparing Implementations Across Data Models

| Technology / Model | Implementation Candidates | Invariants to Preserve |
| --- | --- | --- |
| **Relational** | Three fact tables, dimensions, grain PKs, time indexes | Uniqueness, cutoffs, source transaction integrity, KPI logic |
| **Document** | One event document; one daily snapshot document; one updated process document | Per-document grain and versioning / atomic updates |
| **Graph** | Event nodes, process nodes, item nodes, and step edges | Graph relationships are not automatically measures or complete snapshots |
| **Columnar Warehouse / Lakehouse** | Transaction files, partitioned snapshots, accumulating MERGEs, semantic layer | Late data, idempotency, grain, measures, dimension history |

For example, in a document database, embedding an array of all movements inside an inventory document can bloat the document and require rewriting it on every event. Storing **movements separately**, **periodic snapshots separately**, and **current fulfillments separately** generally simplifies grain management; still, there is no absolute rule—you must weigh atomicity limits and the specific DBMS workload.

In a graph database, traversing a parcel's path across events excels at relationship queries, yet computing monthly median delivery time still requires defining **what one delivery is**, which timestamp applies, and how duplicates are handled.

Physical models vary, but the definitions of transaction, periodic snapshot, and accumulating snapshot live in the **meaning of a single record**, not in `CREATE TABLE` syntax.

## 15. Decision Process for Choosing a Fact Type

When stakeholders ask to "create a fact table for reporting," follow this sequence:

1. **Write down the questions and desired actions:** counting events, knowing point-in-time stock, or measuring workflow progress?
2. **Choose the grain in one sentence:** is one row an event, an entity–period, or a process instance?
3. **Define the unique key and tenant scope:** `eventId`, `(date, product, warehouse)`, `fulfillmentId`, etc.
4. **Identify measures:** signed deltas, point-in-time balances, or step lead times.
5. **Classify additivity:** across time, warehouses, products, channels; sum only when semantics and units allow.
6. **Choose dimensions and effective time:** product/category/warehouse/date, SCD2 or snapshot per policy.
7. **Design the ingestion path:** batch/CDC/events, high-watermarks, idempotency, corrections, restatements, and lineage tracking.
8. **Define incomplete states:** missing snapshot days, unreached workflow milestones, late events; never default to 0.
9. **Write reconciliation checks:** sum of movements vs. snapshot change; process counts vs. source; accumulating milestones vs. status logs.
10. **Test edge cases and measure performance:** JOIN multiplication, retries, late events, split processes, multi-period and high-volume queries.

A strong deliverable is a **data contract** documenting grain, measures, source, business date, keys, update rules, access permissions, and data-publication rules.

## 16. Hands-On Exercise: Warranty Repair Ticket Management

**Scenario:** A warranty center handles devices from customer submission through return. Each `RepairCase` has `caseId`, `customerId`, `deviceId`, and may be reopened after closure. A case can undergo multiple inspections, parts replacements, and requests for customer info; leadership wants daily pending backlog counts, while technicians want to measure turnaround time from intake to completion.

**Task 1 — Choose three grains:** propose:

- Which events belong in the transaction fact?
- At what cutoff and for what entity does the periodic snapshot fact create one row?
- Should the accumulating snapshot fact key on `caseId` or a **`caseCycleId`** when a case can reopen?

**Task 2 — Design the tables:** choose business keys, time columns, measures, dimensions, and valid NULLable fields. State one UNIQUE/PK constraint for each fact.

**Task 3 — Compute KPIs:** write how to calculate monthly repair completions, end-of-day backlog, completed cases, p50 turnaround time, and SLA-breach rate. Pick the right fact type for each KPI.

**Task 4 — Edge cases:** the source sends `"RepairCompleted"` twice; an inspection occurred yesterday but synced only today; a case reopened and had two repair cycles; a customer changed address after submitting the ticket. State which table updates, which table appends events, and whether historical attribute snapshots are needed.

**Task 5 — Reconciliation:** design at least two checks to detect missing transaction events or inconsistent timestamps in the accumulating snapshot.

### Reference Solution Approach

**Transaction fact** at the grain of **one repair status/action event**, with `eventId`, `caseCycleId`, `eventType`, `occurredAt`, and `technicianId`. Count `RepairCompleted` based on unique events per policy; if one repair has multiple steps, do not use an unfiltered `COUNT(*)`.

**Periodic snapshot** at the grain of **one active or in-scope `caseCycle` at end of day**, with `snapshotDate`, `currentStatus`, `waitingHoursAsOfCutoff`, `slaBreachedFlag`. You can choose a dense snapshot for every open cycle and define a cutoff rule for when closed cycles drop out. Count historical backlog from the exact-date snapshot rather than the case's current status.

**Accumulating snapshot** at the grain of **one independent repair cycle (`caseCycleId`)**, containing `openedAt`, `firstInspectedAt`, `partsOrderedAt`, `repairCompletedAt`, `returnedAt`, `currentStatus`, updated as milestones pass. If a closed case reopens, create a new cycle rather than overwriting the prior one. If the business wants cumulative time across multiple cycles of the same case, reports can aggregate by `caseId` from cycles without destroying the base grain.

Because a case can have multiple inspections or parts requests, the transaction fact preserves loop details. To answer "waiting on customer at 17:00 on 10/15," a periodic snapshot or event history answers far more accurately than the current accumulating snapshot.

**Testing:** a repeated `eventId` must not inflate counts; end-of-day snapshots reconcile against transitions up to cutoff; a reopened `caseCycleId` never collides with old cycles; `repairCompletedAt` must never use ETL `loadedAt`; unclosed periods carry freshness flags and are never defaulted to 0.

## 17. Design Review Checklist and Conclusion

- Does every fact have a **verbally stated grain**, matching key, and uniqueness scope?
- Does the transaction fact record **actual events**, rather than accidentally storing current state and overwriting history?
- Does the periodic snapshot define **cutoff, timezone, row density, completeness**, and missing-period policies?
- Does the accumulating snapshot have an ID for **one process instance**, valid milestones, and handling for loops/reopenings?
- Are measures classified as additive, semi-additive, or non-additive accurately by analytical dimension and unit?
- Have you avoided summing inventory across days, mis-grained `COUNT(*)`, and direct cross-grain JOINs that multiply rows?
- Are SCD/historical attributes, price snapshots, and role-playing dates chosen to match the reporting questions?
- Are `eventId` and `sourceVersion` preserved across retries, late arrivals, and data corrections?
- When a period is reprocessed, are report caches, subsequent snapshots, and reconciliation checks updated consistently?
- Can the accumulating table lose milestones when partial events arrive out of order?
- Does OLTP continue enforcing business state while analytical facts refrain from acting as transactional authorities?
- Are tests in place for duplicates, missing days, corrections, split workflows, and data discrepancies?

**Conclusion:** **Transaction facts** record what happened at the event grain; **periodic snapshot facts** answer entity state at recurring cutoffs; **accumulating snapshot facts** describe a process moving through multiple milestones in an updated row. Picking the right fact type does more than speed up queries—it determines **how you count, sum, reconcile, and interpret KPIs**. With clear grains, keys, timestamps, update rules, and data quality checks, all three fact types coexist and complement each other without stripping business meaning from the transactional source.
