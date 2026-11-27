# Late-Arriving Facts, Adjustments, and Compensating Records

In an analytical data warehouse, an order may be created on Monday while the source system sends the sales event only on Wednesday. A week later, customer support adjusts the discount amount. At month-end, the customer partially cancels or returns items. If a pipeline simply **loads once and never revisits data**, reports miss transactions. If a pipeline **overwrites arbitrarily**, nobody knows why figures changed. If a pipeline **inserts every message as a new transaction**, revenue gets doubled.

These challenges are known as **late-arriving facts**, **adjustments/corrections**, and **compensating records**. They all revolve around one central question:

> When a business fact becomes known late, is amended, or is reversed, how does the fact table maintain the right grain, aggregate accurately, and trace what the system knew at every point in time?

This lesson belongs to the **Fact Tables** chapter of the **DATABASE_DATA_MODELING** module. It focuses on turning business rules around time and data changes into verifiable **fact models, keys, constraints, ETL/ELT flows, reconciliation checks, and SQL**. It compares relational, document, graph, and analytical data organizations where relevant; implementation examples use PostgreSQL for illustration rather than serving as a complete accounting or payment-processing system.

## 1. Three Situations You Must Distinguish

### 1.1. Late-Arriving Fact: True Event, Known Late

A sales line actually occurred on **2026-10-10**, yet the analytics warehouse only receives it on **2026-10-13** due to a network outage. The fact is not erroneous; only its **arrival time** differs from its **occurrence time**.

If reporting analyzes sales **by sale date**, the record belongs to 10/10. If operations analyzes **transactions ingested per day**, it belongs to 13/10. Both questions are valid, yet require two different time axes.

### 1.2. Adjustment: Recorded Value Needs Amending

A sales line initially recorded **200,000 VND** for two items. On 16/10, the source confirms a **20,000 VND** discount was omitted.

Depending on reporting policy, the system may:

- Update the sales record's amount from 200,000 down to 180,000.
- Keep the original record and add an **adjustment record of -20,000** referencing the sales line.
- Reverse the original record and rebook the corrected record.
- Keep closed reporting periods frozen and book the adjustment into the **current period** instead of altering prior-period numbers.

These are distinct strategies for **historical modeling and accounting recognition**, not four interchangeable SQL syntaxes.

### 1.3. Compensation / Reversal: An Effect Must Be Canceled with Traceability

On 20/10, the example transaction is canceled per business rules. Instead of deleting the old sales row, you can write a **negative movement** to offset the remaining active effect.

If the sales line had value 200,000 and an adjustment of -20,000, the current active effect is **+180,000**. A record reversing the entire **remaining state** needs -180,000—not -200,000 if the -20,000 adjustment remains, which would sum to **-20,000** and miss the target of 0.

Reversal records must have a **target reference, reason, unique event identifier, and recognition timing policy**. Some businesses use a "reverse entire prior record + book replacement record" pair instead of delta adjustments; never mix both styles without explicitly specifying which records are invalidated.

### Quick Comparison Table

| Situation | Business Reality | Data Added / Edited | Main Risk |
| --- | --- | --- | --- |
| Late-arriving | Event already happened earlier | Loaded late under original business date | Missing prior period, misattribution to load date |
| Adjustment | Initial value or attribute was wrong | Amend original or append delta | Double-counting, lost history, wrong period totals |
| Compensation / reversal | Prior effect must be negated | Write linked offsetting movement | Double reversal, reversing wrong remaining balance |
| Return | A **new event** after sale | `FactReturn` or movement per business rules | Treating returns as data errors, conflating with cancellations |
| Redelivered message | **No new event** | Must not add another fact | Duplicate loads from retries/CDC |
| Late-arriving dimension | Real event lacks dimension context | Backfill / version dimension | Assigning wrong current version |

**Key takeaway:** "Late-arriving," "adjustment," "reversal," and "duplicate redelivery" can occur together yet require distinct handling rules.

## 2. Write the Grain Before Writing the Table

A fact table that can be safely adjusted requires a **clear definition of one row**.

Consider three ways to organize it:

| Fact Model | One Row Represents | Required Natural Identity | Change Behavior |
| --- | --- | --- | --- |
| **Current-state `FactSalesLine`** | One known sales line at its latest state | `source_system + sale_line_id` | May `UPDATE` same row, storing history elsewhere |
| **`FactSalesMovement`** | One **immutable event/delta** affecting a sales line | `source_system + source_event_id` | `INSERT` new events; `SUM(delta)` gives cumulative impact |
| **`FactInventorySnapshot`** | One product–store at one snapshot point | `date + product + store` | Revise/version **state values**; never sum snapshots |
| **`FactOrderLifecycle`** | One order across workflow milestones | `source_system + order_id` | Update milestones on arriving events, handling out-of-order messages |

Choose **`FactSalesMovement`** only when quantities can be expressed as **additive deltas** with consistent semantics: quantity delta, amount delta. An event saying "current price is 85,000" is an **absolute value**, not automatically "add 85,000." You must compute the difference against prior state before putting it into a delta model.

Conversely, an inventory snapshot of **20 units at end of day** and a revised snapshot of **18 units at end of day** are two **versions of one measurement**, not two quantities to sum into 38 units.

### 2.1. Event Grain vs. Reporting Grain

A movement fact has grain "one accepted source event," yet reports may want:

- One row per **sale date × product × store**.
- One row per **order × sales line** at current state.
- One row per **posting date × transaction type**.
- A snapshot of **"what reports knew on 15/10."**

Thus, the fact table's grain need not match a summary table or dashboard's grain. Define how grains transform before running `SUM`.

### 2.2. Deduplication Keys Are Not Sales-Line Business Keys

One sales line can have:

~~~text
sale_line_id = ORDER-901:1
~~~

and multiple events:

~~~text
source_event_id = SALE-1
source_event_id = SALE-1-PRICE-ADJ
source_event_id = SALE-1-CANCEL
~~~

The movement fact's key must distinguish **all three events**. Putting `UNIQUE(sale_line_id)` on the movement fact blocks recording adjustments; omitting `UNIQUE(source_event_id)` lets a retried message create two identical rows.

**Rule:** separate **business entity identity**, **transaction-line identity**, **source event/version identity**, and **warehouse surrogate key**.

## 3. Time Axes: Event, Effective, Posting, and Ingestion

A system may need at least four timestamps:

| Timestamp | Meaning | Question Answered |
| --- | --- | --- |
| **`occurred_at` / `event_time`** | When the event actually happened at the source | When did the customer buy/cancel/adjust? |
| **`business_effective_date`** | Business date to which the impact is attributed analytically | Which sales period does this adjustment affect? |
| **`posting_date`** | Date the system books the entry into ledgers / published periods | In which accounting period was this booked? |
| **`loaded_at` / `ingested_at`** | When the warehouse actually received and accepted the message | Since when has reporting known about this event? |

Example:

| Movement | Occurred | Effective | Posting | Loaded | Amount Delta |
| --- | --- | --- | --- | --- | ---: |
| Sell two units | 10/10 | 10/10 | 13/10 | 13/10 | +200,000 |
| Discount correction | 16/10 | 10/10 | 16/10 | 16/10 | -20,000 |
| Full cancellation | 20/10 | 20/10 | 20/10 | 20/10 | -180,000 |

**This is an illustrative policy choice.** The discount adjustment is attributed effectively to sale date 10/10 yet posted on 16/10. The cancellation is a new event effective 20/10. A company may adopt a different policy, especially when accounting periods are closed.

### 3.1. "Data Correct as of When?" Has Two Meanings

There are at least two types of questions:

1. **As-of business time:** include events whose business effective date is no later than date **t**.
2. **As-known-at / system time:** include only events the analytics system **had already ingested before cutoff k**.

Combining both axes lets you ask:

> "At end of day 15/10, what did the system **know** sales effective on 10/10 were?"

This is an audit need explaining why historical reports shift after receiving new data.

An **append-only** movement table with immutable `loaded_at` supports such queries, provided data is never silently deleted or overwritten and required dimension versions also retain history. If old events can be `UPDATE`d in place without versioning, `loaded_at` alone is **no longer sufficient** to reproduce historical reports accurately.

### 3.2. Business Dates Require Clear Timezones and Conventions

An event at 23:30 UTC falls on the next day in Vietnam. If the business reports in `Asia/Ho_Chi_Minh`, `DimDate` keys must be derived from **instant + business timezone**, never defaulted to UTC or the ETL worker's machine timezone.

For multi-market organizations, each `Store` may have its own timezone; decide between "revenue date in store local timezone" and "corporate date in UTC." Both yield different daily totals yet both are valid when clearly labeled.

## 4. Choosing a Strategy: UPDATE, Append-Only Delta, or Reverse-and-Rebook

Not every fact must be append-only. The choice depends on immutability, history requirements, and read/write costs.

### 4.1. In-Place Update (In-Place Correction)

Example:

~~~sql
UPDATE fact_sales_line
SET net_amount_vnd = 180000
WHERE source_system = 'checkout'
  AND source_sale_line_id = 'ORDER-901:1';
~~~

*This is a conceptual example assuming a `fact_sales_line` table with those columns exists.*

Pros: querying current state is simple; no summing deltas. Cons: loses visibility that 200,000 was once recorded unless backed by an **audit/version table or CDC history**. `UPDATE` also mutates results of previously published reports.

Appropriate when the fact represents **latest known state** and change history lives in another responsible system or is not required.

### 4.2. Delta Adjustment

Instead of overwriting 200,000 with 180,000:

~~~text
SALE:       +200,000
ADJUSTMENT:  -20,000
--------------------
Current:    +180,000
~~~

Pros: retains adjustment trail and reproduces as-known-at figures by ingestion time. Cons: current-state queries must aggregate; movement row volume grows; trickier key design, reversals, and out-of-order adjustments.

Suitable for **additive** measures with reliable event identities, audit requirements, and retry safety.

### 4.3. Reverse and Rebook (Full Replacement)

Another pattern:

~~~text
Original:            +200,000
REVERSAL original:   -200,000
REBOOK corrected:    +180,000
----------------------------
Current:             +180,000
~~~

This differs from appending a -20,000 delta. If you already booked **ADJUSTMENT -20,000** and later also write **REVERSAL -200,000, REBOOK +180,000** without accounting for the prior adjustment, the net sum becomes 160,000—wrong.

You must enforce a clear **logic family**:

- **Delta changes:** record only incremental differences relative to current state.
- **Full replacement:** reverse all effects of the old version and write the new version, safeguarding against double-counting adjustments tied to the old version.

A message saying "correct price to 180,000" **cannot** be inserted straight into a delta column as +180,000 without knowing whether 180,000 is the **new absolute value** or the **delta**.

### 4.4. Compensating Records Are Not Always Returns

**Technical compensation** usually offsets an erroneous record or cancellation. A **business return** is a new event with return reason, return date, restocking warehouse, refund, and possibly fees. Do not lump everything into a negative delta generically labeled "return" if the business needs to analyze cancellation counts, return counts, product quality, or refund reasons separately.

A system can have both **`FactSalesMovement`** and **`FactReturnLine`**. They are distinct event types requiring unified KPI definitions so **revenue is never subtracted twice**.

## 5. PostgreSQL Schema for an Immutable Movement Fact

Assumptions for this learning example:

- All monetary values in the fact are stored in **whole-integer VND**, without mixing currencies.
- Each `source_sale_line_id` has exactly one **original `SALE`** in its source system; every adjustment/reversal references the original `SALE` in the same `source_system`.
- Movements record **quantity deltas** and **post-discount net amount deltas**.
- Facts are never `UPDATE`d or `DELETE`d after acceptance. This is a **pipeline write rule**, not something guaranteed solely by the DDL below.
- Effective dates can differ from posting dates and ingestion timestamps.
- Each movement references Product/Store dimension versions resolved under business policy.

### 5.1. Minimal Dimension Tables

~~~sql
-- PostgreSQL; run in an isolated test database.
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,           -- e.g., 20261010
    calendar_date DATE NOT NULL UNIQUE
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_code TEXT NOT NULL,
    product_name TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE dim_store (
    store_key BIGINT PRIMARY KEY,
    store_code TEXT NOT NULL UNIQUE,
    store_name TEXT NOT NULL
);
~~~

One Product can have multiple Type 2 versions sharing `product_code`, so do not put `UNIQUE(product_code)` across all of `dim_product`. **Preventing overlapping versions** requires additional constraints; `PRIMARY KEY(product_key)` protects only the identity of **one version**.

### 5.2. Movement Fact Table

~~~sql
CREATE TABLE fact_sales_movement (
    movement_key BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,

    -- Deduplicate by source event identity:
    source_system TEXT NOT NULL,
    source_event_id TEXT NOT NULL,
    source_sale_line_id TEXT NOT NULL,
    related_source_event_id TEXT,

    movement_kind TEXT NOT NULL
        CHECK (movement_kind IN ('SALE', 'ADJUSTMENT', 'REVERSAL')),

    -- Define the time axes:
    occurred_at TIMESTAMPTZ NOT NULL,
    effective_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    posting_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Analytical context:
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL REFERENCES dim_store(store_key),

    -- Deltas may be negative for adjustments/reversals:
    quantity_delta INTEGER NOT NULL,
    net_amount_delta_vnd BIGINT NOT NULL,

    CONSTRAINT uq_source_sales_event
        UNIQUE (source_system, source_event_id),

    CONSTRAINT fk_movement_related_event
        FOREIGN KEY (source_system, related_source_event_id)
        REFERENCES fact_sales_movement(source_system, source_event_id),

    CONSTRAINT movement_shape CHECK (
        (
            movement_kind = 'SALE'
            AND related_source_event_id IS NULL
            AND quantity_delta > 0
            AND net_amount_delta_vnd >= 0
        )
        OR
        (
            movement_kind = 'ADJUSTMENT'
            AND related_source_event_id IS NOT NULL
            AND (
                quantity_delta <> 0
                OR net_amount_delta_vnd <> 0
            )
        )
        OR
        (
            movement_kind = 'REVERSAL'
            AND related_source_event_id IS NOT NULL
            AND quantity_delta < 0
            AND net_amount_delta_vnd <= 0
        )
    )
);

-- Enforces assumption: each business line has at most one original SALE.
CREATE UNIQUE INDEX uq_one_original_sale_per_line
ON fact_sales_movement (source_system, source_sale_line_id)
WHERE movement_kind = 'SALE';

CREATE INDEX idx_sales_movement_effective
ON fact_sales_movement
    (effective_date_key, product_key, store_key);

CREATE INDEX idx_sales_movement_posting
ON fact_sales_movement
    (posting_date_key, product_key, store_key);

CREATE INDEX idx_sales_movement_line
ON fact_sales_movement
    (source_system, source_sale_line_id, loaded_at);
~~~

**What this schema enforces:**

- No two events share `source_system + source_event_id`.
- Movements match the assumed types and delta signs/shapes.
- Adjustments/reversals must point to an **existing identified event** within the same `source_system`.
- Dimension FKs use valid surrogate keys.
- Under the one-original-SALE-per-line assumption, a second original SALE cannot enter under a different `event_id`.

**What this schema cannot enforce on its own:**

1. Whether `related_source_event_id` actually points to the **original SALE of the exact same `source_sale_line_id`**. An FK checks existence, not event kind or matching line.
2. Whether a reversal matches the **exact remaining balance**, was reversed twice, or drives net quantity negative.
3. Whether `effective_date_key` matches the business-date policy for `occurred_at` and timezone.
4. Whether an adjustment's `product_key`/`store_key` matches the original line's version/scope.
5. Whether events remain **immutable**; DDL does not block privileged writers from running `UPDATE`/`DELETE`.
6. Whether late-arriving gaps leave dashboards temporarily incomplete before full source arrival.
7. Whether amounts satisfy tax, fee, refund, FX, and closed-period rules.

These invariants require **DB permissions, triggers/procedures, transactions, ingestion rules, and reconciliation checks**. Never interpret illustrative DDL as a full accounting ledger.

### 5.3. Watch Out for Self-Referencing FKs and Out-of-Order Loads

Our FK referencing the original event rejects an `ADJUSTMENT` if the original `SALE` is not yet in the fact table. In real systems, however, **an adjustment message can arrive before the sale message** when transport layers do not guarantee ordering.

Policy options:

- **Staging/pending:** hold adjustments in a queue and load once the original arrives.
- **Inferred original:** create an identified anchor record and backfill measures when the original arrives; design a separate table/row status rather than fabricating a dummy `SALE` with fake measures.
- **Controlled independent acceptance:** omit the self-FK on the append-only fact, flag unresolved rows, and exclude them from marts until references resolve.
- **Separate ledger and materialized state:** ingest source events in any order, publishing eligible deltas only once dependencies resolve.

Never delete the FK and pretend out-of-order arrival is solved. You must decide **what "incomplete" data scope is allowed to appear** in dashboards and how queues replay.

## 6. Three-Movement Example: Late Sale, Price Correction, Cancellation

Illustrative dataset:

- **2026-10-10:** 2 units sold for 200,000 VND.
- **13/10:** `SALE` fact arrives late, is posted, and ingested.
- **16/10:** missing 20,000 discount identified; adjustment is effective back on sale date 10/10 yet posted on 16/10.
- **20/10:** entire remaining sale canceled; reversal of quantity -2 and amount -180,000, effective and posted on 20/10.

### 6.1. Dimension Data

~~~sql
INSERT INTO dim_date (date_key, calendar_date) VALUES
    (20261010, DATE '2026-10-10'),
    (20261013, DATE '2026-10-13'),
    (20261016, DATE '2026-10-16'),
    (20261020, DATE '2026-10-20');

INSERT INTO dim_product
    (product_key, product_code, product_name, valid_from, valid_to)
VALUES
    (101, 'P-001', 'Bluetooth Headphones',
     TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL);

INSERT INTO dim_store (store_key, store_code, store_name)
VALUES (11, 'HCM-01', 'Central Store');
~~~

### 6.2. Immutable Events

~~~sql
-- 1. SALE: occurred 10/10 but received and posted 13/10.
INSERT INTO fact_sales_movement
    (movement_key, source_system, source_event_id,
     source_sale_line_id, related_source_event_id,
     movement_kind, occurred_at, effective_date_key,
     posting_date_key, loaded_at, product_key, store_key,
     quantity_delta, net_amount_delta_vnd)
VALUES
    (1001, 'checkout', 'SALE-1', 'ORDER-901:1', NULL,
     'SALE', TIMESTAMPTZ '2026-10-10 11:00:00+07',
     20261010, 20261013,
     TIMESTAMPTZ '2026-10-13 08:00:00+07',
     101, 11, 2, 200000);

-- 2. ADJUSTMENT: known 16/10, yet effective on 10/10.
INSERT INTO fact_sales_movement
    (movement_key, source_system, source_event_id,
     source_sale_line_id, related_source_event_id,
     movement_kind, occurred_at, effective_date_key,
     posting_date_key, loaded_at, product_key, store_key,
     quantity_delta, net_amount_delta_vnd)
VALUES
    (1002, 'checkout', 'SALE-1-PRICE-ADJ', 'ORDER-901:1',
     'SALE-1', 'ADJUSTMENT',
     TIMESTAMPTZ '2026-10-16 09:00:00+07',
     20261010, 20261016,
     TIMESTAMPTZ '2026-10-16 09:05:00+07',
     101, 11, 0, -20000);

-- 3. REVERSAL: cancels remaining effect on 20/10.
INSERT INTO fact_sales_movement
    (movement_key, source_system, source_event_id,
     source_sale_line_id, related_source_event_id,
     movement_kind, occurred_at, effective_date_key,
     posting_date_key, loaded_at, product_key, store_key,
     quantity_delta, net_amount_delta_vnd)
VALUES
    (1003, 'checkout', 'SALE-1-CANCEL', 'ORDER-901:1',
     'SALE-1', 'REVERSAL',
     TIMESTAMPTZ '2026-10-20 14:00:00+07',
     20261020, 20261020,
     TIMESTAMPTZ '2026-10-20 14:01:00+07',
     101, 11, -2, -180000);
~~~

In this learning example, `loaded_at` is populated with hypothetical timestamps to reproduce point-in-time reports. In production, it is normally a **timestamp written by the pipeline/warehouse upon acceptance** and must remain immutable thereafter; never let senders supply arbitrary "received" timestamps to mask lag.

### 6.3. Final State of the Sales Line

~~~sql
SELECT source_system, source_sale_line_id,
       SUM(quantity_delta) AS net_quantity,
       SUM(net_amount_delta_vnd) AS net_amount_vnd
FROM fact_sales_movement
GROUP BY source_system, source_sale_line_id;
-- checkout | ORDER-901:1 | 0 | 0
~~~

The result is **0 units, 0 VND** because:

~~~text
Quantity: +2  +0  -2 = 0
Amount:  +200000 -20000 -180000 = 0
~~~

A sum of 0 **does not imply** the transaction never existed. History still shows a sale, a discount correction, and a cancellation. Dashboards must distinguish **gross sales events**, **current net impact**, **cancellations**, and other published metrics—never use `SUM(delta)` alone for every question.

## 7. Reporting by Effective Date, Posting Date, and As-Known-At Time

### 7.1. By Business Effective Date

~~~sql
SELECT d.calendar_date AS business_date,
       SUM(f.quantity_delta) AS quantity_delta,
       SUM(f.net_amount_delta_vnd) AS net_amount_delta_vnd
FROM fact_sales_movement AS f
JOIN dim_date AS d ON d.date_key = f.effective_date_key
GROUP BY d.calendar_date
ORDER BY business_date;
~~~

Output from the example:

| Effective Date | Quantity Delta | Amount Delta (VND) |
| --- | ---: | ---: |
| 10/10/2026 | +2 | +180,000 |
| 20/10/2026 | -2 | -180,000 |

The -20,000 adjustment was **attributed back to sale date 10/10**, so 10/10's total changed from 200,000 to 180,000 once the adjustment event arrived. The 20/10 cancellation takes effect on the cancellation date, producing a negative movement on 20/10.

**This is a movement report by effective date**, not necessarily an accounting revenue definition. If the business requires original sale-date revenue to end up at 0 upon cancellation on the 20th, define a separate **sale-cohort restatement** or allocate cancellations back to the original date.

### 7.2. By Posting Date

~~~sql
SELECT d.calendar_date AS posting_date,
       SUM(f.quantity_delta) AS quantity_delta,
       SUM(f.net_amount_delta_vnd) AS posted_amount_delta_vnd
FROM fact_sales_movement AS f
JOIN dim_date AS d ON d.date_key = f.posting_date_key
GROUP BY d.calendar_date
ORDER BY posting_date;
~~~

Output:

| Posting Date | Quantity Delta | Amount Delta (VND) |
| --- | ---: | ---: |
| 13/10/2026 | +2 | +200,000 |
| 16/10/2026 | 0 | -20,000 |
| 20/10/2026 | -2 | -180,000 |

10/10 has no **posted** movements in this example, even though the transaction occurred on that day. Therefore, name metrics explicitly such as **`posted_sales_delta`** or **`business_effective_sales_delta`**, avoiding a vague "sales" metric whose date axis is ambiguous.

### 7.3. "What Did the Report Know Back Then?"

Considering only sales effective on 10/10, at end of 15/10 the system knew +200,000; by end of 17/10 it knew the adjusted +180,000.

~~~sql
-- Knowledge snapshot at end of 15/10 in +07:00.
SELECT COALESCE(SUM(net_amount_delta_vnd), 0) AS known_amount_vnd
FROM fact_sales_movement
WHERE effective_date_key = 20261010
  AND loaded_at < TIMESTAMPTZ '2026-10-16 00:00:00+07';
-- 200000

-- Knowledge snapshot at end of 17/10.
SELECT COALESCE(SUM(net_amount_delta_vnd), 0) AS known_amount_vnd
FROM fact_sales_movement
WHERE effective_date_key = 20261010
  AND loaded_at < TIMESTAMPTZ '2026-10-18 00:00:00+07';
-- 180000
~~~

Use **half-open** intervals to define date boundaries unambiguously. Filtering by `loaded_at` provides a simple **as-known-at** mechanism for append-only events; if source rows have late-arriving revisions, hard deletes, or dimensions that mutated without history, extend the design to reconstruct full state.

### 7.4. Closed Reporting Periods Must Not Be Silently Mutated

Some organizations forbid altering published figures for closed accounting periods. When adjustments arrive after period close:

- **Policy A — restatement:** recompute the closed period and **publish a revised report version**.
- **Policy B — current-period adjustment:** book the adjustment into the currently open period; prior reports stay unchanged.
- **Policy C — dual views:** maintain both **as originally reported** and **restated** figures with a variance reconciliation table.

No single choice fits every company. What matters is that **`business_effective_date`** and **`posting_date`** express the chosen policy explicitly alongside version/period-close history. Never overwrite a `date_key` column in old facts just to make today's dashboard tie out.

## 8. Distinguishing Error Corrections, Cancellations, Returns, and Refunds

Negative events may all reduce a metric yet **do not share the same business meaning**.

| Business Case | Emitted Event | Primary Measure | History Requirement |
| --- | --- | --- | --- |
| Fix omitted discount | Transaction amount adjustment | Negative or positive `amount_delta` | Retain old amount, new amount / reason if required |
| Pre-delivery/completion cancellation | Reverse commitment/sale per policy | Quantity/amount reversal | Who canceled, when, order status |
| Customer returns delivered goods | A new **return event** | `returned_quantity`, `refund_amount` | Link to original sale, reason, receiving warehouse |
| Partial monetary refund | Refund event | `refund_amount`, possibly `quantity = 0` | Payment status, currency |
| Retry redelivery | No new business event | **No change to totals** | Dedup by source ID |
| Stocktake inventory adjustment | Inventory delta or snapshot revision | `stock_delta` or new `units_on_hand` | Reason, warehouse, stocktake period |

A canceled order and a returned parcel can both reduce revenue by 100,000, yet operational dashboards must separate **`cancellation_rate`**, **`return_rate`**, and **`refund_amount`**.

If `FactSalesMovement` already includes a -100,000 reversal and `FactReturnLine` also records +100,000 refund, the formula `"net sales = SUM(sales movements) - SUM(refund)"` **can subtract twice**. Clearly define which movements already incorporate refunds, which fact serves each report, and align scopes when drilling across.

### 8.1. Same-Line Adjustments Across Different Units

An adjustment might modify only:

- Quantity: +1 or -1 unit.
- Money: -20,000 VND from a discount.
- Tax: +5,000 VND if tax is tracked separately.
- Product or store code: a **dimension change**, not simple numeric addition.

If correcting **`product_key` from P-A to P-B**, a single movement delta with `product_key = P-B` and amount 0 **does not transfer** quantity/revenue from P-A to P-B. An appropriate pattern writes a negative delta under **P-A** and a positive delta under **P-B**, or updates/versions the sales line's dimension mapping under restatement policy.

**Non-additive** measures such as conversion rates, average unit prices, or distinct order counts cannot be "adjusted" by adding a negative percentage into a fact table. Recompute them from numerators/denominators or underlying events.

## 9. Protecting Safe Re-Ingestion (Idempotency)

Messaging systems, CDC streams, and ETL jobs commonly provide **at-least-once delivery**: the same message can be delivered again. Blindly `INSERT`ing multiplies fact totals.

### 9.1. Identity and Conflict Rules

A key like **`(source_system, source_event_id)`** must:

- Stay unchanged across retries of the **same event**.
- Differ across **two distinct business events**.
- Include the right tenant, topic, or source scope; if `event_id` is unique only within a tenant, include `tenant_id` in the key.
- Never be generated from receipt timestamps or warehouse sequences, since each retry produces a new value.

Example blocking duplicate `INSERT`s by key:

~~~sql
INSERT INTO fact_sales_movement
    (source_system, source_event_id, source_sale_line_id,
     movement_kind, related_source_event_id,
     occurred_at, effective_date_key, posting_date_key,
     product_key, store_key, quantity_delta, net_amount_delta_vnd)
VALUES
    ('checkout', 'SALE-1', 'ORDER-901:1', 'SALE', NULL,
     TIMESTAMPTZ '2026-10-10 11:00:00+07',
     20261010, 20261013,
     101, 11, 2, 200000)
ON CONFLICT (source_system, source_event_id)
DO NOTHING;
~~~

**`DO NOTHING` is not enough to prove correctness.** If the source reuses `event_id` while sending a **different payload**, silently ignoring it leaves an unresolved data conflict.

Production pipelines must compare normalized payloads or business-field hashes:

- Same ID, same content → **valid retry**, do not add again.
- Same ID, different content → **quarantine/escalate**, or invoke the source's official versioning workflow.
- Different IDs yet **a business-level duplicate transaction** → apply custom business-dedup rules rather than relying solely on `event_id`.

Never merge two genuinely distinct events merely because they share the **same amount, timestamp, or `product_id`**.

### 9.2. Never Treat Arrival Order as Business Order

An `ADJUSTMENT` message may arrive before `SALE`; a status message with sequence 13 may arrive before sequence 12. Use **source version/sequence**, identities, and dependencies to establish valid order; never sort by `loaded_at` and assume later-arriving events are always newer in business time.

When the source provides monotonic sequences **per aggregate/order**, check for missing sequences and replay behavior. If the source guarantees ordering only **within a message broker partition**, never infer global ordering from it.

### 9.3. Exactly-Once Effect Differs from Exactly-Once Delivery

A warehouse can receive the same message multiple times and still achieve an **exactly-once effect** via unique event keys, transactions, and safe retry handling. That is what matters for revenue totals.

When a single transaction both `INSERT`s a fact and commits a processed offset, ensure both parts **commit atomically** or remain idempotent so replays never duplicate data. Never assume a message broker or database alone guarantees end-to-end exactly-once effects across systems.

## 10. Concurrent Transactions, Double Reversals, and Final State

An insert-only movement table can still carry **cross-row invariants**.

### 10.1. A Reversal Can Look Valid Row-by-Row Yet Fail When Summed

In the sample dataset, inserting two reversals of -180,000 under two distinct `source_event_id`s passes local row `CHECK`s yet drives the sum negative. `UNIQUE(source_event_id)` does not prevent **two business reversals of the same line** when the source emits distinct IDs.

Depending on policy, add:

- A unique business operation key such as **`cancellation_id`**.
- A one-full-cancellation-per-`sale_line_id` constraint.
- Checking whether state is **already canceled** before writing compensation.
- Checking total quantity/amount within scope, including accepted adjustments.
- Transactions/locks ensuring two writers cannot both see "not yet canceled" and insert two reversals.

### 10.2. Safer Compensation Workflow

A business procedure can operate as follows:

1. Receive a command with a stable **`operation_id`**.
2. Within a transaction, lock the sales-line/aggregate entity **using a convention shared by all writers**.
3. Check whether the command was already processed; if so, return the prior result without inserting a new movement.
4. Compute **remaining active balance** from valid movements under the proper policy version.
5. Verify cancellation eligibility: delivered/completed, existing refunds, closed periods.
6. Emit the reversal with offsetting `quantity_delta` and `amount_delta` per rules.
7. Write the event, command completion record, and audit log in the same transaction; commit.
8. On serialization/deadlock errors, retry the **entire transaction** with the same `operation_id`.

Running `SELECT SUM` followed by `INSERT` in two independent transactions **does not protect** against concurrent writers. Use row locks on the representative source entity (order line), transactional advisory locks on the business key, or `SERIALIZABLE` isolation with retries, depending on DBMS and architecture.

If the warehouse ingests from a **source ledger that already resolves compensation rules**, the warehouse need not re-run every transactional lock. Still, the pipeline must verify **duplicates, missing messages, and broken references to original events**.

## 11. Late-Arriving Dimensions and SCD Type 2 Mapping

A late-arriving fact frequently encounters a **late-arriving dimension** problem.

For example, Product P-001 has history:

| product_key | product_code | category | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 101 | P-001 | Headphones | 2026-01-01 | 2026-11-01 |
| 102 | P-001 | Personal Devices | 2026-11-01 | NULL |

A sale from **10/10** reaches the warehouse on **05/11**. If the pipeline blindly looks up the **current** `DimProduct` row on load day, it assigns `product_key` **102**, retroactively shifting "category at time of sale" reports to "Personal Devices."

Map using **business event time** and effective intervals:

~~~sql
-- Assumes dim_product has clean SCD2 effective intervals.
-- :product_code and :event_at are source parameters.
SELECT product_key
FROM dim_product
WHERE product_code = 'P-001'
  AND valid_from <= TIMESTAMPTZ '2026-10-10 11:00:00+07'
  AND (
      valid_to > TIMESTAMPTZ '2026-10-10 11:00:00+07'
      OR valid_to IS NULL
  );
-- Expected: 101 if intervals do not overlap.
~~~

Ensure each event matches **exactly one version**. Zero matches require a missing-dimension policy. Two matches indicate overlapping intervals; never pick one arbitrarily with `LIMIT 1` and hide the bug.

### 11.1. Handling Unarrived Dimensions

Three common approaches:

1. **Hold the fact** in staging and retry once the dimension arrives, backed by SLAs and freshness alerts.
2. **Unknown member:** load the fact with an identified "Unknown" `product_key` and reason, then update the mapping or publish a historical restatement.
3. **Inferred member:** create a provisional dimension row for the business key and enrich attributes when dimension data arrives.

Each option trades off **fact completeness**, **classification accuracy**, and **publication latency**. Updating `product_key` on an already-loaded fact changes historical context; store an audit trail or mapping version, especially when dashboards require reproducing as-known-at reports.

### 11.2. Retroactive Dimension Corrections

Sometimes the source announces "P-001 actually changed Category on 01/10 instead of 01/11." This is a **dimension history change**, distinct from a late-arriving sale.

You may need to:

- Repair SCD2 effective intervals and verify non-overlap.
- Decide whether facts in the affected window require **rekeying/restatement** or stay as-was.
- Reconcile reports previously published under the old version.
- Separate **current classification** metrics from **classification at event time** metrics.

Never just edit `DimProduct` and assume every query stays accurate if facts still point to `product_key` of a revised version.

## 12. Watermarks, Completeness, and Data Window Handling

In batch or streaming, pipelines often use **watermarks** or progress markers to handle late events.

### 12.1. A Watermark Does Not Prove "No More Late Events"

Suppose a system sets a 48-hour lateness allowance for daily aggregations. When a 10/10 event arrives on 13/10, it exceeds that threshold.

A streaming system may:

- Route it to a **late-event handling** path.
- Update the closed window if the engine and policy permit.
- Book a current-period adjustment.
- Quarantine and trigger a controlled backfill.

"Closing the window after 48 hours" is a **processing policy**, not a law of physics preventing later events. Real sources suffer multi-day outages, manual back-entries, or corrections months later.

### 12.2. Tracking Lag Distributions

A simple measurement:

~~~sql
SELECT movement_kind,
       COUNT(*) AS event_count,
       MIN(loaded_at - occurred_at) AS min_lag,
       MAX(loaded_at - occurred_at) AS max_lag,
       AVG(EXTRACT(EPOCH FROM (loaded_at - occurred_at))) / 3600
           AS avg_lag_hours
FROM fact_sales_movement
GROUP BY movement_kind;
~~~

**Interpret carefully:** for `ADJUSTMENT`, `occurred_at` is when the adjustment occurred, not the sale date being adjusted. Thus lag here measures **propagation delay of the adjustment event**, not days elapsed between sale and adjustment.

Negative lag can arise from clock skew, broken time sync, or future `occurred_at` values from the source; classify and investigate them. `AVG` hides long tails, so in operations track **p95/p99**, SLA breach counts, and late-event rates by source.

### 12.3. Completeness Signals

- Source event count per day/partition/sequence vs. accepted event count.
- Missing **source sequence** gaps, especially for events tied to an original record.
- Pending movements blocked on missing dimensions or missing original events.
- Duplicate IDs with identical payloads vs. duplicate IDs with differing payloads.
- Source control totals for quantities/amounts vs. post-adjustment fact totals.
- Closed reporting days/periods and events arriving after close.
- Lag spikes by source system, tenant, transaction type, or region.

**Note:** Warehouse `COUNT` equaling source `COUNT` does not guarantee correctness if source records can be canceled, revised, or filtered out by eligibility rules. Reconcile across **explicit transformation rules and scope**, not raw uncontextualized totals.

## 13. Aggregate Tables and Published Reporting Periods

A dashboard may query a daily aggregate table:

~~~text
daily_sales_mart(
    business_date,
    product_code,
    store_code,
    net_amount_vnd,
    net_units,
    refreshed_at,
    calculation_version
)
~~~

When an adjustment effective on 10/10 arrives on 16/10, the 10/10 mart needs handling per policy:

- **Recompute affected partition:** rebuild 10/10 from source movements.
- **Apply exactly-once delta:** add -20,000 to existing total once, keyed by a unique `operation_id`.
- **Frozen snapshot + correction layer:** keep published figures frozen and report adjustments in a separate layer.
- **Versioned mart:** retain before/after result versions for comparison.

### 13.1. Why "Rerunning a Job" Sometimes Multiplies Numbers

If every job run scans events and executes:

~~~text
mart.total = mart.total + SUM(source_events)
~~~

rerunning the same window adds already-processed events again. Use one of these patterns:

- **Replace results** for the entire affected key group (recompute + atomic swap/upsert).
- Maintain **checkpoint/cursor + `event_id` dedup**, adding only newly accepted events.
- Upsert by **source version** with run tracking and idempotency checks.

When updating multiple marts from the same event, ensure consistent report-version cutovers; never let Mart A show adjusted revenue while Mart B still shows the old version if dashboards treat both as one coherent publication.

### 13.2. Backfilling Past Periods

A safe backfill workflow should:

1. Identify the true **effective-date** range affected, not merely load dates.
2. Identify dimension/SCD2 versions that could alter groupings.
3. Mark affected aggregates/partitions for recomputation.
4. Load data using stable event keys, checking duplicates and missing messages.
5. Recompute in staging / a new version, reconciling sums and row counts.
6. Publish **one consistent version** after passing checks.
7. Log the backfill run, scope, input snapshot, and calculation version.
8. Prepare a rollback or correction release plan if reports are already consumed.

Never blindly wipe an entire partition and leave dashboards reading empty data during reload if availability and consistency are required.

## 14. Late or Revised Snapshots Are Not Transaction Deltas

A **periodic snapshot fact** has a different grain from a **transaction movement fact**.

For example, end-of-day inventory on 10/10 for P-001 at Store HCM-01:

~~~text
Snapshot revision 1: 20 units
Snapshot revision 2: 18 units (recount adjustment)
~~~

This does not mean end-of-day inventory is **20 + 18 = 38 units**. If reporting wants the latest confirmed value, use revision 2; if asking "what was known prior to recount," take the revision whose `loaded_at` is no later than the query cutoff.

### 14.1. Revision Model for Snapshots

~~~sql
CREATE TABLE fact_inventory_snapshot_revision (
    snapshot_date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL REFERENCES dim_store(store_key),
    revision_no INTEGER NOT NULL CHECK (revision_no > 0),
    source_revision_id TEXT NOT NULL,
    units_on_hand INTEGER NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        snapshot_date_key, product_key, store_key, revision_no
    ),
    UNIQUE (source_revision_id)
);
~~~

**Assumption:** `revision_no` increases monotonically per source-confirmed version for the same `(date, product, store)` tuple. With multiple independent sources, `UNIQUE(source_revision_id)` must include `source_system` or `tenant_id`.

Retrieve the latest revision known at cutoff in PostgreSQL:

~~~sql
SELECT DISTINCT ON
    (snapshot_date_key, product_key, store_key)
    snapshot_date_key,
    product_key,
    store_key,
    revision_no,
    units_on_hand
FROM fact_inventory_snapshot_revision
WHERE loaded_at < TIMESTAMPTZ '2026-10-18 00:00:00+07'
ORDER BY snapshot_date_key, product_key, store_key,
         revision_no DESC;
~~~

The `loaded_at` filter selects versions received before cutoff; `ORDER BY revision_no DESC` picks the highest source revision among known versions. If revisions arrive out of order, **never** order solely by `loaded_at` and assume the latest-arriving record is newest: an older source revision can arrive after a newer revision.

### 14.2. Inventory Is a Semi-Additive Measure

`units_on_hand` sums across **products/stores at the same point in time**, never across multiple days to represent "period-end stock."

To get month-end inventory, pick the **latest snapshot not after month-end** per product–store while handling missing-snapshot days and version history. For average inventory, define day coverage and missing-snapshot rules.

### 14.3. Accumulating Snapshots and Out-of-Order Events

An Order accumulating snapshot row holds `ordered_at`, `shipped_at`, `delivered_at`. If `DELIVERED` arrives before `SHIPPED`, never "keep the later arrival timestamp as the earlier state" just because ETL processes in arrival order.

Track milestones by **event type + event time + source version** and compute current status via state-transition rules; you can store all source events in a historical event table and derive/update the accumulating snapshot table from it.

## 15. Physical Structure: Partitioning, Indexes, and Query Cost

A movement fact can accumulate many rows because every adjustment/reversal is retained. Physical design must support **filtering by effective date**, **filtering by posting date**, and **tracing original lines**.

### 15.1. Choosing Indexes by Query Pattern

| Query | Supporting Structure | Trade-off |
| --- | --- | --- |
| Aggregate by effective date, Product, Store | Index or sort/partition by `effective_date_key` | Late adjustments may write into old partitions |
| Postings by posting date | Index/partition by `posting_date_key` | Does not replace effective-date filtering |
| Reconstruct one sales line | Index on `source_system + source_sale_line_id` | Increases `INSERT` cost |
| As-known-at reports | Index on `loaded_at` or combined with analytical keys | May be less selective over long windows |
| Duplicate detection | `UNIQUE(source_system, source_event_id)` | Mandatory index maintenance on writes |
| Reference checks | Index on `related_source_event_id` within scope | Supports lineage tracing and missing-event handling |

Do not blindly index every column. With hundreds of millions of movements, every index adds storage, write, vacuum, rebuild, and replication overhead. On columnar analytical warehouses, clustering, partition pruning, or column scans can matter more than B-trees.

### 15.2. Partition by Which Date?

- **By `loaded_at`:** writes mostly land in the current partition, easing ingestion and receipt-based retention; business-date reports may scan many partitions if lateness is unbounded.
- **By `effective_date`:** business-date reporting prunes cleanly; late events must write back into old partitions, which may be archived or frozen.
- **By `posting_date`:** aligns with closed accounting periods; does not automatically optimize restatements back to older effective dates.

There is no fixed answer. Choose the partition key based on **query patterns, lateness distribution, backfill policy, cold-data governance, and regulatory needs**. When one axis is the partition key, other axes may need indexes, clustering, or dedicated marts.

### 15.3. Verifying with Query Plans

In PostgreSQL, a sample query:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT product_key, store_key,
       SUM(quantity_delta) AS net_units,
       SUM(net_amount_delta_vnd) AS net_vnd
FROM fact_sales_movement
WHERE effective_date_key BETWEEN 20261010 AND 20261020
GROUP BY product_key, store_key;
~~~

Inspect estimated vs. actual rows, Seq Scan vs. Index Scan, hash/sort nodes, buffer reads, and runtime. If an aggregate reads most of the fact table, a Seq Scan can be optimal; never label every scan a bug.

**Caution:** `EXPLAIN ANALYZE` actually executes the SQL statement. The `SELECT` above is read-only, whereas `EXPLAIN ANALYZE` on `INSERT`/`UPDATE`/`DELETE` mutates data. Run benchmarks only in authorized environments with representative data.

## 16. Multi-Level Reconciliation: Event, Line, Period, and Warehouse

A system handling late facts must be verified at multiple levels. An accurate grand total **can hide** two offsetting bugs (one extra transaction + one missing transaction).

### 16.1. Checking Movement Data by Sales Line

~~~sql
SELECT source_system, source_sale_line_id,
       COUNT(*) AS movement_count,
       SUM(quantity_delta) AS net_quantity,
       SUM(net_amount_delta_vnd) AS net_amount_vnd
FROM fact_sales_movement
GROUP BY source_system, source_sale_line_id
ORDER BY source_system, source_sale_line_id;
~~~

In a model assuming non-negative net sold quantities, detect anomalous groups:

~~~sql
SELECT source_system, source_sale_line_id,
       SUM(quantity_delta) AS net_quantity
FROM fact_sales_movement
GROUP BY source_system, source_sale_line_id
HAVING SUM(quantity_delta) < 0;
~~~

However, **do not enforce `net_quantity >= 0` blindly on every model**: if facts include stock adjustments or quantity-less fees, rules differ. Tailor checks to the exact fact type and unit-of-measure policy.

### 16.2. Detecting Events Referencing the Wrong Original SALE

The example FK only checks that `related_source_event_id` exists. This query catches adjustments/reversals referencing the **wrong line or wrong `SALE` kind**:

~~~sql
SELECT m.source_system, m.source_event_id,
       m.source_sale_line_id, m.related_source_event_id
FROM fact_sales_movement AS m
JOIN fact_sales_movement AS origin
  ON origin.source_system = m.source_system
 AND origin.source_event_id = m.related_source_event_id
WHERE m.movement_kind IN ('ADJUSTMENT', 'REVERSAL')
  AND (
      origin.movement_kind <> 'SALE'
      OR origin.source_sale_line_id <> m.source_sale_line_id
  );
~~~

If rules require related events to point to the original `SALE`, the result must be empty. This query does not catch every wrong amount, double reversal, or missing event; add checks on `operation_id` and business state.

### 16.3. Post-Backfill Verification Checks

After a backfill, measure at minimum:

1. Count of distinct accepted source event IDs.
2. Count of identical-payload duplicates ignored without adding movements.
3. Count of differing-payload duplicates handled/quarantined.
4. Count of adjustments unmatched to an original event.
5. Lag distribution and count of events exceeding processing windows.
6. Quantity/amount sums by business date, posting date, and source.
7. Before/after aggregates across affected groups.
8. Report releases restated, with version and root cause.

Never compare only a **warehouse-wide `SUM`**: an erroneous +100,000 and -100,000 cancel out in the grand total while corrupting store/product reports.

## 17. Relational, Document, Graph, and Warehouse Models

Late arrivals and compensation are **data semantics problems** that do not vanish when switching databases.

| Architecture | Candidate Representation | Controls Needed |
| --- | --- | --- |
| **Transactional RDBMS** | Immutable event/ledger table, FK/`UNIQUE`, transactions | Idempotency, concurrency, state transitions, reference checks |
| **Document** | Current-state Order doc + revisions/events array, or separate events collection | Unbounded array growth, concurrent updates, cross-document dedup |
| **Graph** | Event nodes linked to Order/SaleLine via `ADJUSTS`/`REVERSES` edges | Reference chains, double reversals, cycles/wrong edge types, deduplicating by event ID |
| **Warehouse / OLAP** | Append-only facts, versioned snapshot facts, role-playing `DimDate`, SCD2 | Grain, date roles, backfills, partitioning, marts, and reconciliation |

### 17.1. Document: Current State and Event Log

An Order document might store:

~~~json
{
  "orderId": "ORDER-901",
  "version": 3,
  "currentNetAmountVnd": 0,
  "lastEventId": "SALE-1-CANCEL"
}
~~~

This suits APIs reading **latest state**, yet lacks full progression without an **event history**. Store the event log in a separate collection where each event carries `eventId`, `occurredAt`, `effectiveDate`, `delta`, and `reference`. When updating the state document from events, use **version compare-and-set**, transactions, or idempotent projections so the same event is never applied twice.

Never assume "embedding all events in an array" is always better: documents can grow unboundedly, cross-order effective-date queries become hard, and concurrent writes contend on the same object.

### 17.2. Graph: Tracing Adjustment Relationships

A graph might contain:

~~~text
(:SaleLine {id:"ORDER-901:1"})
  <-[:APPLIES_TO]- (:SaleEvent {id:"SALE-1"})
  <-[:CORRECTS]- (:Adjustment {id:"SALE-1-PRICE-ADJ"})

(:Reversal {id:"SALE-1-CANCEL"})
  -[:REVERSES]-> (:SaleEvent {id:"SALE-1"})
~~~

Graphs trace **which event amends which event**, yet do not automatically guarantee reversal amounts match the effect being reversed. If multiple paths lead to one event, path traversals can return that event multiple times; financial aggregations must deduplicate by **event ID** or apply business weights rather than summing per traversed path.

### 17.3. Warehouse: Which Fact Plays Which Role?

An architecture may retain simultaneously:

- **Raw source events:** raw payloads, source IDs, source timestamps, and receipt timestamps for traceability.
- **Validated movement fact:** one row per eligible event with deltas and dimension keys.
- **Current-state mart:** summed deltas or projections serving current-state queries.
- **As-reported snapshots:** published report figures by run/version and cutoff.
- **Reconciliation/audit tables:** source–warehouse comparisons and period adjustments.

These layers are **not independent sources of truth**. Specify which layer is authoritative for rebuilding which downstream layer, data-correction rules, versioning, and backfill paths.

## 18. Design and Operations Workflow from Business Requirements

A practical workflow for facts subject to late arrivals or edits:

1. **Define the grain:** one source line, one event, one revision, or one state snapshot?
2. **Classify events:** original, adjustment, reversal, return, refund, duplicate, retraction, and dimension correction.
3. **Choose timestamps:** event time, effective date, posting date, load time, timezone, and publication cutoff.
4. **Define invariants:** how many times a sale can be recorded, how many times reversed, valid balances, closed periods.
5. **Select change strategy:** `UPDATE` with history, append delta, reverse-and-rebook, versioned snapshot, or hybrid by fact type.
6. **Design keys:** source system, tenant, business key, event ID, operation ID, and surrogate key; prevent duplicate loads at the exact scope.
7. **Design dependencies:** adjustments/reversals must link to originals; handle out-of-order messages and late dimensions.
8. **Design history:** requirements for as-known-at, as-reported, restated reports, and data retention.
9. **Design pipeline:** staging, validation, quarantine, dedup, SCD2 lookup, atomic publication, retries/backfills.
10. **Design reconciliation:** source totals, event counts, movement counts, affected periods, exceptions, and lag SLAs.
11. **Design physical layout:** partition on the right time axis, indexes, aggregates/materialized views, ingestion cost.
12. **Test edge cases:** duplicates, correction before original, competing reversals, closed periods, retroactive dimensions, late snapshot revisions.
13. **Measure results:** query plans, latency, throughput, p95/p99 lag, exception counts, and pre/post variances.
14. **Publish semantics:** whether metrics are gross, net, posted, or restated, and which date axis a report displays.

### 18.1. Minimal Data Contract for a Movement

~~~text
Event name:
  SOURCE_SALE_ADJUSTMENT

Identifying key:
  (source_system, tenant_id, source_event_id)

Business references:
  source_sale_line_id, original_sale_event_id

Timestamps:
  occurred_at, effective_date, posting_date, loaded_at

Quantities:
  quantity_delta, net_amount_delta, currency

Rules:
  In what units are deltas expressed?
  Can adjustments be negative/positive?
  Can they arrive after period close?
  Which staging table holds orphans before original arrives?
  Must retries with same ID have identical payload?
  Which operation key blocks duplicate reversals?
  Which reports get restated?

Reconciliation:
  Source messages, accepted movements, period quantities/amounts,
  load lag, error buckets, and publication checkpoints.
~~~

This is a **semantic contract**; never send a JSON schema with just an `amount` field while leaving ambiguous whether `amount` is a new value or a delta.

## 19. Self-Check Exercises with Solutions

### Exercise 1. Distinguishing Occurrence Date and Load Date

**Prompt:** A customer purchases on 10/10, and the source system sends the event on 13/10. Which date do sales-by-purchase-date reports vs. ingested-events reports assign the transaction to?

**Solution:** Purchase-date reports assign it to **10/10**; ingested-event reports assign it to **13/10**. Keep event/business date separate from `loaded_at`; never replace purchase date with batch run date.

### Exercise 2. Delta Adjustment

**Prompt:** Initially recorded +500,000, later confirmed the true amount is 460,000. Using a delta fact, which movement is added?

**Solution:** One **ADJUSTMENT -40,000** if the policy is **delta-only**. Never add +460,000 on top of +500,000. If using reverse-and-rebook, write -500,000 and +460,000 without also booking a standalone -40,000 delta.

### Exercise 3. Reversing an Adjusted Transaction

**Prompt:** `SALE` +200,000, `ADJUSTMENT` -20,000. To bring the final balance to 0 upon full cancellation, what reversal amount is required?

**Solution:** **-180,000** under the **reverse remaining active balance** policy. If reversing the original and rebooking, handle/reverse adjustments consistently rather than blindly adding -200,000 on its own.

### Exercise 4. Why Does `source_event_id` Matter?

**Prompt:** A +100,000 sale event is redelivered three times by the broker due to retries. If the warehouse uses an auto-incrementing surrogate `movement_key` with no source key, what happens?

**Solution:** It can insert three rows and report **300,000**—wrong. Enforce uniqueness over the stable source ID scope and inspect payloads when an `event_id` is reused with different contents.

### Exercise 5. Adjustment Arriving Before Original

**Prompt:** A price correction arrives at the warehouse before the original `SALE`; the movement table has an FK from adjustment to `SALE`'s `source_event_id`. What should you do?

**Solution:** Hold it in **staging/pending** and retry after the original arrives, or use an explicitly designed inferred-event model. Never drop the FK and let orphan adjustments flow straight into final reports.

### Exercise 6. Returns and Reversals

**Prompt:** The pipeline subtracted 80,000 from sales movements on a return, while `FactReturns` also recorded +80,000 refund. A dashboard computes `SUM(sales movements) - SUM(refund)`. What is wrong?

**Solution:** It likely **subtracts twice**. Clarify whether movements already include returns/refunds and define KPI formulas that count each effect once.

### Exercise 7. Late-Arriving Type 2 Dimension Data

**Prompt:** A product changes Category on 01/11. A 10/10 `SALE` arrives on 05/11. Which dimension version should a report grouping by category at sale time assign?

**Solution:** Assign the version **effective on 10/10**, not the current version on load day. If zero matching versions exist, invoke the missing-dimension/unknown policy.

### Exercise 8. Closed Periods and Restatements

**Prompt:** October is already published; on 05/11 a 1 million VND revenue shortfall in October is discovered. Must you overwrite October's summary table directly?

**Solution:** No. Choose a policy: **restate October under a new version**, **book an adjustment in the current period**, or provide both modes. Every option must leave an audit trail and clear effective/posting dates.

### Exercise 9. Revising an Inventory Snapshot

**Prompt:** The 10/10 snapshot shows 20 units; a late recount corrects it to 18 units. Can you sum both revision rows into 38 to compute closing inventory?

**Solution:** No. Select the **latest valid version** by source revision or cutoff policy; never `SUM` absolute snapshot values.

### Exercise 10. As-Known-At

**Prompt:** `SALE` +200,000 is loaded on 13/10, and `ADJUSTMENT` -20,000 is loaded on 16/10 effective 10/10. Querying 10/10 revenue with cutoffs at end of 15/10 and end of 17/10 gives what results?

**Solution:** **200,000** and **180,000**, assuming an immutable fact filtered by `loaded_at` against cutoff. These are two distinct knowledge snapshots of the same business period.

### Exercise 11. Concurrent Updates

**Prompt:** Two workers both compute remaining balance +180,000 and each inserts a -180,000 reversal under different event IDs. Is `UNIQUE(source_event_id)` enough?

**Solution:** No. Those are **two business operations** with two distinct IDs. Use an `operation_id`/business uniqueness constraint and transactions/locks/serialization guaranteeing at most one valid cancellation.

### Exercise 12. Choosing a Partition Key

**Prompt:** A pipeline ingests hundreds of millions of events with many late arrivals from months earlier. Reports filter mostly by business date while loads arrive by current date. Which date should you partition on?

**Solution:** Measure **lateness, query patterns, and backfill costs**. Partitioning by business date enables report pruning yet forces late inserts into old partitions; partitioning by `loaded_at` eases ingestion yet hinders business-date pruning; partitioning by `posting_date` matches accounting periods. There is no universal default.

### Exercise 13. Which KPIs Are Additive?

**Prompt:** A fact has `quantity_delta` and `average_unit_price`. When receiving a -20,000 adjustment, can you take `SUM(average_unit_price)` across all movements to compute the new average price?

**Solution:** No. Average price is a **non-additive** measure; compute it from **total amount / total quantity** within the right business scope, non-zero quantity check, and cancellation/return policy.

### Exercise 14. Why a Zero Net Variance Is Not Enough

**Prompt:** Two bugs occur: a missing +100,000 sale at Store A and an extra +100,000 sale at Store B. Total warehouse revenue still matches the source. What else must reconciliation check?

**Solution:** Reconcile **by source event ID, business key, date, store, product, quantity, and status**. One global total can hide two offsetting discrepancies.

## 20. Acceptance Checklist

Before exposing a fact table with late arrivals/adjustments in reporting, verify:

- **Grain:** every fact row has an exact meaning; event deltas and absolute snapshots are never mixed.
- **Keys:** every event has a stable source ID scoped to tenant/system; retries create zero extra effect.
- **Time:** occurred, effective, posting, loaded, and timezones are cleanly separated.
- **Reversals:** valid references to original records, reasons, scope, `operation_id`, and double-reversal guards.
- **Closed periods:** explicit rules for late corrections, restatements, and report versioning.
- **SCD2:** late-arriving facts map to dimensions at the appropriate timestamp, never defaulting to load date.
- **Arrival order:** adjustments arriving before originals route to staging or equivalent mechanisms.
- **Idempotency:** retries with matching ID/payload add no rows; matching ID with differing payload raises an error/quarantine.
- **Aggregates:** deltas apply once; backfilled marts recompute/upsert consistently.
- **Snapshots:** state revisions never sum like transactions.
- **Reconciliation:** checks cover event counts, row counts, quantity/amount totals, group breakdowns, and exceptions.
- **History:** able to explain why the same period reported differently at two points in time.
- **Performance:** indexes, partitions, and query plans benchmarked under realistic late-event distributions.
- **KPI definitions:** gross sales, posted revenue, adjustments, cancellations, returns, and refunds are distinct.

## 21. Takeaways

- **Late-arriving facts** are valid events received after they occurred; preserve accurate business time, receipt time, and period rules.
- **Adjustments** amend a prior value; explicitly choose **delta entries**, **versioned edits**, or **reverse-and-rebook**.
- **Compensating records** are traceable events designed to offset prior effects; guard against double recording and match the value being offset.
- **Never mix deltas with absolute snapshots.** Summing movements makes sense; summing two inventory revisions for the same timestamp does not.
- **Idempotency and out-of-order handling** determine correctness when events replay or arrive out of sequence.
- **Late-arriving facts and late-arriving dimensions** interact closely: late facts must resolve the right SCD version per business policy.
- **As-known-at, as-effective, and as-posted** are three distinct perspectives; a report changing after a backfill is not necessarily a bug when properly versioned and explained.
- **Reconciliation and empirical checks** must accompany keys, FKs, `CHECK`s, indexes, and partitions; a matching grand total never proves every row is right.

A trustworthy fact model does more than store the latest figures. It answers **which event produced the number, when the system learned it, which period it affects, how it was adjusted or compensated, and whether it reconciles back to the source**.
