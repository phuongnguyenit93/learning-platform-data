# Documenting Grain, Data Sources, and Effective Time

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, a data model does not only need to be correct in entities, relationships, constraints, normalization, keys, and indexes. The model must also be **clear enough for others to understand, integrate, query, and verify** without guessing meaning from table names. For data serving reporting, events, and integrations, three questions are especially critical:

1. **Grain:** what exactly does a single row, document, or event represent?
2. **Data source (*source/provenance*):** which system does the information come from, what transformation rules apply, and who is accountable for its meaning?
3. **Effective time:** for which business time interval does this fact hold, and since when has the system known/stored it?

If any of the three is missing, the same model can produce reports that **double-count, pull wrong historical values, or misinterpret late-arriving data**.

After this lesson, you can:

- Write a verifiable **grain statement**, specifying unique keys and identity scope.
- Build a **data dictionary**, *source-to-target mapping*, ownership, and *lineage*.
- Distinguish **business effective time**, **event time**, **recorded/system time**, **ingestion time**, **snapshot time**, and **business date**.
- Document SCD Type 2 dimension history and know when a **bitemporal** model is needed.
- Write SQL tests for unique grain, reference sources, duplicate events, overlapping effective intervals, as-of joins, and reconciliation.
- Maintain documentation as part of model evolution, API/event contracts, and data quality.

## 1. Three Documentation Axes: A "Contract of Meaning"

Do not describe a table solely by listing columns:

~~~text
fact_order_lines:
    order_id VARCHAR
    line_no INTEGER
    customer_key BIGINT
    amount NUMERIC
    date_key INTEGER
~~~

The snippet above **fails to answer**:

- Is a row a **current** order line, a line at **order confirmation**, or an **adjustment version**?
- Is `order_id` unique system-wide or only within one tenant?
- Is `amount` booked order value, collected cash, refunded cash, or recognized revenue?
- Does `customer_key` link to **current customer info** or the **version at purchase time**?
- Is `date_key` creation date, confirmation date, payment date, or warehouse load date?
- Does the data come from transaction tables, events, manual imports, or transformation results?

A proper specification must bind **grain, source, and time** into the same contract.

~~~mermaid
flowchart TD
    Q["Business question"] --> G["Grain: what is one record?"]
    Q --> S["Source: who owns the truth?"]
    Q --> T["Time: when is the fact effective?"]
    G --> M["Model documentation and constraints"]
    S --> M
    T --> M
    M --> D["Schema / API / Event / Data mart"]
    D --> V["SQL tests, lineage, reconciliation"]
~~~

**Model documentation** does not replace the physical schema. It explains **why** keys, relationships, timestamps, and transformations were chosen so the schema and queries can be verified.

## 2. Grain: Must Be Written as One Exact Sentence

**Grain** is the statement:

> **One record in model X represents exactly one [business unit] within [key/source/tenant scope], at [event or point in time] according to [versioning rules].**

Examples:

| Model | Grain Statement | Illustrative Business Key |
|---|---|---|
| `fact_confirmed_order_lines` | One product line of an order **at valid confirmation** | `(source_system, tenant_id, order_id, line_no)` |
| `fact_payment_transactions` | One payment transaction recorded by a payment provider | `(provider, payment_transaction_id)` |
| `fact_inventory_daily` | One product in one warehouse at **end-of-business-day stock cutoff** | `(snapshot_business_date, warehouse_id, product_id)` |
| `fact_order_status_events` | One status change of an order | `(source_system, event_id)` or source-guaranteed sequence |
| `dim_customer_segment_history` | One **effective customer segment version** over a time interval | `customer_segment_key` and non-overlapping interval rules |
| Order document | One **current** order with embedded lines | Stable order ID within defined scope |

Note: the keys above are **assumptions to verify with the source system**. If an order may be confirmed multiple times, a grain "at confirmation" must include `confirmation_id` or an appropriate event version; never pick `order_id + line_no` alone and silently drop other confirmations.

### 2.1. Grain Differs from a Technical Primary Key

A table with `fact_row_id BIGSERIAL PRIMARY KEY` **does not prove** its grain is right. Two rows with different `fact_row_id` values can still represent the same event ingested twice.

Example:

~~~text
fact_row_id=1001, tenant=T01, order=O7, line=1
fact_row_id=1002, tenant=T01, order=O7, line=1
~~~

If defined as "exactly one record per order line at confirmation," these two rows **violate the grain** unless a published version or state transition distinguishes them. Documentation must record:

- **Business key** reflecting identity at the business level.
- **Surrogate key** used for referencing or physical version management.
- **Uniqueness invariant**—enforced by the DB or checked in the pipeline.
- **Duplicate/replay policy** when the same event arrives again.

### 2.2. Grain Differs from the Displayed Aggregation Level

If the fact table is at order-line grain and a report aggregates by month:

~~~sql
SELECT DATE_TRUNC('month', confirmed_at) AS month_start,
       SUM(booked_amount) AS total_booked
FROM fact_confirmed_order_lines
GROUP BY DATE_TRUNC('month', confirmed_at);
~~~

the **table grain** remains one order line; the **query output grain** is one month. Document both when building materialized views or analytical APIs:

~~~text
Base fact grain: one confirmed order line
Aggregate grain: one business month × currency
Measure: sum(booked_amount) over eligible lines
~~~

If multiple currencies coexist, omitting `currency` or conversion rules in the aggregate can make **total amounts meaningless** even when the SQL executes cleanly.

### 2.3. Grain Determines Which Questions Cannot Be Answered

With an **order-line grain** fact, you can compute `SUM(booked_amount)` by product. Yet `COUNT(*)` counts **lines**, not orders; order counts may require `COUNT(DISTINCT (tenant_id, order_id))`.

With only **end-of-day inventory snapshots**, you cannot deduce exact intra-day receipt/issue counts without transaction facts. Two snapshots showing zero net change can still conceal numerous offsetting receipts and shipments.

With only a customer's **current state**, you cannot reconstruct last month's customer segment if the system never retained history.

Good documentation states **unsupported scope** rather than letting users assume the model answers every question.

## 3. Specify Fact Types and Permitted Aggregations

Numeric columns need **aggregation semantics**:

| Measure | Source Grain | Additivity | Warning |
|---|---|---|---|
| `booked_amount` | Order line at confirmation | Additive within same currency and deduplicated lines | Not synonymous with `paid_amount` or accounting revenue |
| `on_hand_units` | Warehouse × product × cutoff date | Semi-additive: sum across warehouses/products at same snapshot; **do not sum across days** | Month-end must pick the right closing snapshot |
| `account_balance` | Account × cutoff point | Semi-additive across time | Averages/closing balances require explicit rules |
| `conversion_rate` | Eligible session set | Non-additive | Must recompute from numerator/denominator |
| `distinct_customers` | Customer set in period | Non-additive across overlapping groups | Never sum daily `COUNT(DISTINCT)` into monthly totals |

**A monetary column cannot be summed across dimensions** when groups overlap or one-to-many JOINs multiply rows. Document which dimensions may be grouped, units of measure, currency, and **how incompatible units are handled**.

## 4. Data Sources: Distinguishing "Where It Lives" from "Who Owns the Truth"

**Source of truth** is the system/domain responsible for establishing a business fact, not simply wherever the freshest copy happens to be read.

Example:

~~~text
Orders Service / OLTP
    ├── orders
    └── order_items
          |
          | Normalized transactional outbox / CDC
          v
Raw event storage
          |
          | Deduplicate, validate, resolve dimensions
          v
Staging / canonical confirmed lines
          |
          | Type conversion, effective-time lookup
          v
fact_confirmed_order_lines
          |
          v
Data mart / dashboard
~~~

A dashboard pulls numbers from `fact_confirmed_order_lines`, yet **the dashboard is not the source of truth** for order confirmation events. Likewise, object storage may hold raw events without owning the definition of "confirmed."

### 4.1. Mandatory Questions for Every Source

| Attribute | Question to Answer |
|---|---|
| **Business owner** | Which business domain defines the event/state? |
| **Technical owner** | Which team operates the table, topic, API, or pipeline? |
| **Source location** | What is the exact DB/schema/table, topic, endpoint, collection, or file? |
| **Source grain** | Does one source record represent an order, line, mutation, or snapshot? |
| **Keys and namespace** | Is ID unique per tenant, store, provider, or globally? |
| **Capture mechanism** | Batch, CDC, API pull, outbox, file import, or manual entry? |
| **Availability / lag** | How late can data arrive? Are there SLAs/SLOs? |
| **Change semantics** | How are inserts, updates, deletes, upserts, tombstones, and corrections represented? |
| **Data quality** | Does the source block NULLs, duplicates, bad FKs, or invalid statuses? |
| **Retention/replay** | How far back can history be reconstructed? |
| **Security** | Sensitive fields, read permissions, permitted purpose, retention limit? |

Docs saying only `"source: Kafka"` are insufficient: Kafka is a **transport/storage mechanism**, not a description of **semantic ownership**, event types, identity rules, or effective timestamps.

### 4.2. Tracing Target Back to Source (*Lineage*)

Record all stages:

~~~text
fact_confirmed_order_lines.booked_amount
    <- staging_confirmed_lines.booked_amount
    <- quantity * unit_price_at_confirmation - line_discount
    <- Orders order_item snapshot at confirmation
~~~

For each transformation, know:

- **Formula** and unit of measure.
- **Filters**: valid confirmed orders only; are subsequently cancelled orders included or excluded?
- **Deduplication**: by `event_id`, row version, or business key?
- **Null and exception rules**.
- **Timestamp** used when resolving historical dimensions.
- **Rule version** and approver.

A column sourced across multiple tables must state **JOIN keys, cardinality, and post-JOIN grain**. Joining payments and shipments simultaneously easily multiplies line values:

\[
3\text{ order lines}\times2\text{ payments}\times2\text{ shipments}
=12\text{ joined rows}.
\]

`SUM(DISTINCT amount)` does not magically fix this: two genuine lines can share the exact same amount. Lineage docs must show how two facts are aggregated to compatible grains **before joining**.

## 5. Time: Six Concepts That Must Not Be Equated

A design can contain many `_at` and `_date` columns, each representing a distinct type of time:

| Time Type | Question | Example |
|---|---|---|
| **Business effective time / valid time** | From when to when is the value or relationship **true in business**? | Customer belongs to VIP segment from 01/06 |
| **Event time** | When did the event actually **occur**? | Order confirmed at 09:15 |
| **Recorded/system time** | Since when has the system **known/stored** that fact? | Segment edit recorded on 03/07 |
| **Ingestion/processing time** | When did the pipeline receive/process the data? | Event arrived at warehouse at 09:20 |
| **Snapshot/as-of time** | Which point in time does a state snapshot reflect? | End-of-business-day inventory on 30/11 |
| **Business date / reporting period** | Under which calendar and timezone is the reporting period defined? | 22/11 in Asia/Ho_Chi_Minh |

**Not every system needs all six.** Yet documentation must classify existing columns; `created_at` is not always event time, `updated_at` is not always when a fact took effect, and `ingested_at` must never replace business milestones.

### 5.1. Event Time vs. Ingestion Time

Example confirmed order:

~~~text
confirmed_at (event time) = 2026-10-31T23:58:00Z
ingested_at  (pipeline)   = 2026-11-01T00:07:00Z
~~~

If the KPI is **confirmed orders by UTC month**, the order belongs to **October**, not November. If the KPI follows Vietnam business dates, both timestamps must convert to the business timezone before grouping.

Late-arriving events need **watermarks, period-close update windows, and backfill policies**, rather than swapping event time for ingestion time just to simplify queries.

### 5.2. Business Date and Timezone

One absolute UTC timestamp can map to different dates across regions:

~~~text
2026-11-21T18:30:00Z
  = 2026-11-22 01:30 in Asia/Ho_Chi_Minh
~~~

Therefore document:

- Store absolute instants in UTC or `TIMESTAMPTZ` with explicit offsets.
- **Reporting timezone**: per tenant/store, or one unified timezone?
- Day/period cutoff time: local midnight or a specific closing hour.
- How DST calendars are handled in applicable regions; **a local day is not always 24 hours long**.

PostgreSQL example:

~~~sql
SELECT
    (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS confirmed_business_date,
    COUNT(*) AS confirmed_lines
FROM fact_confirmed_order_lines
GROUP BY (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date;
~~~

**Note:** this query counts **order lines**, not orders, because the fact's grain is order lines. Counting orders requires distinct order keys or an order-grain fact. The SQL only illustrates timezone conversion, not that every tenant uses Vietnam time.

## 6. "Effective Time" Needs Intervals and Boundary Conventions

Suppose a customer segment changes:

| customer_id | segment | valid_from (UTC) | valid_to (UTC) |
|---|---|---|---|
| C17 | STANDARD | 2026-01-01T00:00Z | 2026-06-01T00:00Z |
| C17 | VIP | 2026-06-01T00:00Z | null (open-ended) |

Choose a **half-open** interval:

\[
[\text{valid\_from},\ \text{valid\_to})
\]

meaning **inclusive start, exclusive end**. Under this convention:

- An event at `2026-05-31T23:59:59Z` belongs to `STANDARD`.
- An event at exactly `2026-06-01T00:00:00Z` belongs to `VIP`.
- Adjacent intervals do not overlap at the boundary.
- `valid_to IS NULL` can be defined as **currently active with no known end date**, rather than a zero value or 1970 sentinel.

Documentation must specify **time precision** (day, second, microsecond), timezone, and open/closed boundaries. If the source only knows "effective 01/06 store local time," never convert it to `2026-06-01T00:00Z` without knowing the store's timezone.

### 6.1. Invariants of a Historical Attribute

For each `(tenant_id, customer_id)`, if the system allows only one segment at a time:

1. `valid_from < valid_to` for bounded intervals.
2. **No two effective intervals overlap** for the same customer.
3. Any business timestamp maps to **0 or 1 version**; 0 means missing history or out-of-scope, handled per policy.
4. **Effective gaps** may exist if the business allows them; do not stitch intervals together to hide missing data.
5. If history is **corrected retroactively**, specify whether historical facts and old reports are reclassified.

### 6.2. SCD Type 2: Preserving Versions Instead of Overwriting

In a Type 1 dimension, overwriting `segment=STANDARD` with `VIP` erases last month's context. If reports require "segment **at time of purchase**," use history such as **SCD Type 2** (*Slowly Changing Dimension Type 2*) or a reliable snapshot.

With SCD Type 2:

- `customer_id`: customer business key.
- `customer_segment_key`: surrogate key of **one version**.
- `valid_from/valid_to`: **clearly defined** business effective interval or version interval.
- A fact occurring at `confirmed_at` must join to the **matching version** for that timestamp.

Documentation must distinguish **"record created today"** from **"record effective last month"**; when those two differ, an `updated_at` column cannot replace `valid_from`.

## 7. PostgreSQL Example: Proving Point-in-Time Dimension Versions

The SQL below illustrates **tenant-scoped customer segment history**. This is a simplified model and does not cover all segmentation rules or retroactive edits.

### 7.1. History Schema

~~~sql
CREATE TABLE dim_customer_segment_history (
    customer_segment_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    customer_id TEXT NOT NULL,
    segment_code TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (valid_to IS NULL OR valid_from < valid_to)
);

-- Prevent more than one "open" interval for the same customer.
CREATE UNIQUE INDEX ux_customer_segment_open
    ON dim_customer_segment_history (tenant_id, customer_id)
    WHERE valid_to IS NULL;

CREATE INDEX ix_customer_segment_asof
    ON dim_customer_segment_history
       (tenant_id, customer_id, valid_from);
~~~

**Mandatory limitations to state in docs:**

- `ux_customer_segment_open` only blocks **two rows with `valid_to IS NULL`** for the same key; it **does not** prevent bounded intervals with explicit `valid_to` from overlapping. Dedicated checks or an exclusion constraint are needed if the DBMS and requirements permit.
- `recorded_at` here is **when the version row was written**, **insufficient** to reconstruct "what did the system know at an earlier time" if rows are edited/deleted. True bitemporal history requires the two-axis model in the next section.
- If `customer_id` is unique only within one source system, the key must include `source_system` or a guaranteed global identifier; never assume two sources using the same ID refer to the same customer.
- Whether an index helps depends on data volume, cardinality, and actual query plans.

### 7.2. As-Of Join: Linking Order Lines to the Right Version

Suppose `staging_confirmed_order_lines` is a normalized source containing:

~~~text
source_system, tenant_id, order_id, line_no,
customer_id, confirmed_at, quantity,
unit_price, line_discount_amount, currency_code
~~~

Its grain is **one confirmed order line** within the stated identity scope.

~~~sql
SELECT
    s.source_system,
    s.tenant_id,
    s.order_id,
    s.line_no,
    s.confirmed_at,
    d.customer_segment_key,
    d.segment_code AS segment_at_confirmation,
    s.quantity * s.unit_price - s.line_discount_amount
        AS booked_amount,
    s.currency_code
FROM staging_confirmed_order_lines AS s
LEFT JOIN dim_customer_segment_history AS d
  ON d.tenant_id = s.tenant_id
 AND d.customer_id = s.customer_id
 AND d.valid_from <= s.confirmed_at
 AND (d.valid_to IS NULL OR s.confirmed_at < d.valid_to);
~~~

A customer who is currently `VIP` yet was `STANDARD` at purchase must map according to **`confirmed_at`** when the KPI requires segment at purchase time.

**Critical risk:** a `LEFT JOIN` can return **0 or more than 1 version** for a single source row. If history is missing, `customer_segment_key` is NULL; if intervals overlap, a line gets multiplied and **inflates revenue**. Before loading facts, verify that matched version count equals **1** (or apply an approved unknown-member policy).

### 7.3. Checking Matched Dimension Version Counts per Fact

~~~sql
SELECT
    s.source_system,
    s.tenant_id,
    s.order_id,
    s.line_no,
    COUNT(d.customer_segment_key) AS matching_versions
FROM staging_confirmed_order_lines AS s
LEFT JOIN dim_customer_segment_history AS d
  ON d.tenant_id = s.tenant_id
 AND d.customer_id = s.customer_id
 AND d.valid_from <= s.confirmed_at
 AND (d.valid_to IS NULL OR s.confirmed_at < d.valid_to)
GROUP BY
    s.source_system, s.tenant_id, s.order_id, s.line_no
HAVING COUNT(d.customer_segment_key) <> 1;
~~~

Results:

- `matching_versions = 0`: missing dimension or no version covers the event timestamp.
- `matching_versions > 1`: overlapping history or duplicate dimension rows.

This check assumes **staging is already deduplicated to grain**. If staging itself holds two rows with the same business key, `GROUP BY` will collapse them and produce misleading counts; therefore **unique-grain tests must run first**.

### 7.4. Checking Overlapping Effective Intervals

~~~sql
SELECT
    a.tenant_id,
    a.customer_id,
    a.customer_segment_key AS version_a,
    b.customer_segment_key AS version_b,
    a.valid_from AS a_from,
    a.valid_to AS a_to,
    b.valid_from AS b_from,
    b.valid_to AS b_to
FROM dim_customer_segment_history AS a
JOIN dim_customer_segment_history AS b
  ON a.tenant_id = b.tenant_id
 AND a.customer_id = b.customer_id
 AND a.customer_segment_key < b.customer_segment_key
 AND a.valid_from < COALESCE(b.valid_to, 'infinity'::timestamptz)
 AND b.valid_from < COALESCE(a.valid_to, 'infinity'::timestamptz);
~~~

With half-open intervals, two intervals **intersect** when one's start is strictly less than the other's end in both directions. `NULL` represents infinity on the upper bound. The query returns only pairs that overlap under a linear effective-history rule.

**Do not rely solely on an overlap-detection query for concurrency.** Under concurrent writes, use appropriate transaction isolation/locking or database constraints to **prevent** two updates from creating overlapping intervals rather than only detecting them later.

### 7.5. Fact Schema and Time Contract

~~~sql
CREATE TABLE fact_confirmed_order_lines (
    source_system TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),

    confirmed_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL,
    customer_id TEXT NOT NULL,
    customer_segment_key BIGINT
        REFERENCES dim_customer_segment_history(customer_segment_key),

    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18,2) NOT NULL,
    line_discount_amount NUMERIC(18,2) NOT NULL,
    booked_amount NUMERIC(18,2) NOT NULL,
    currency_code CHAR(3) NOT NULL,

    PRIMARY KEY (source_system, tenant_id, order_id, line_no),
    CHECK (
        booked_amount = quantity * unit_price - line_discount_amount
    )
);
~~~

In this example:

- Fact grain: one `(source_system,tenant_id,order_id,line_no)` row at valid confirmation.
- `confirmed_at`: **event time** used for daily/monthly confirmation reporting.
- `ingested_at`: **pipeline arrival time** for lag measurement, never a substitute for `confirmed_at`.
- `customer_segment_key`: key of the dimension version **at confirmation time**; nullable here to illustrate late-arriving dimension workflows, though production reporting needs clear block/quarantine/unknown policies.
- `booked_amount`: merchandise value after line discount, excluding taxes/shipping fees in this example.
- `currency_code`: **must group by currency** or apply proper conversion before `SUM`ming across currencies.

If the source amends a confirmed line, the model must define whether to **append an adjustment event** or **restate versions**. Never delete historical event records and still call the result "data as of confirmation" if the business requires auditability.

## 8. Bitemporal: "Effective Since When?" vs. "Known Since When?"

**Valid time** describes when a fact holds in the business world. **System/recorded time** describes when the system stored/knew **that version of knowledge**.

### 8.1. Retroactive Correction Scenario

Suppose the system initially knows:

~~~text
From 01/01: customer C17 is STANDARD.
On 03/07, business operations confirms:
    customer C17 was actually VIP starting 15/05.
~~~

If we directly update the `STANDARD` row to end on 15/05 and insert a `VIP` row starting 15/05, a report run on **04/07** will reclassify June transactions as VIP. However, if an auditor asks:

> "On **30/06**, which segment did the system know C17 belonged to?"

a **valid-time-only history after an in-place update** cannot answer that. You must retain the history of **knowledge versions**.

### 8.2. Two Time Intervals

A bitemporal record can be modeled as:

~~~text
tenant_id
customer_id
segment_code

valid_from, valid_to       -- When the fact is valid in business
system_from, system_to     -- When the system knew/recorded this version
~~~

On both axes, use half-open intervals `[from,to)`. Upon retroactive correction:

- Superseded knowledge rows have **`system_to` closed**, remaining intact for audit.
- New knowledge rows open **`system_from`** with `valid_from/valid_to` reflecting the newly confirmed effective period.
- Queries can specify both the **business point in time** and the **system-knowledge point in time**.

Conceptual query pattern:

~~~sql
SELECT segment_code
FROM customer_segment_bitemporal
WHERE tenant_id = :tenant_id
  AND customer_id = :customer_id
  AND valid_from <= :business_as_of
  AND (valid_to IS NULL OR :business_as_of < valid_to)
  AND system_from <= :known_as_of
  AND (system_to IS NULL OR :known_as_of < system_to);
~~~

The `customer_segment_bitemporal` table and parameters are an **illustrative model**, not a table created in earlier DDL. Implementing bitemporal data accurately requires **non-overlapping invariants across `(valid_time, system_time)`**, correction rules, transactions, audit checks, and controlled system-time writes.

**Never claim that adding `recorded_at` alone gives you bitemporal support.** A single write timestamp cannot capture full intervals showing **from when to when prior versions stood superseded**.

### 8.3. Both Historical Reporting Modes Can Be Valid

Two distinct questions:

1. **Restated view:** "Given the corrected facts, what were June sales by segment?"
2. **As-known-at view:** "At the 30/06 report close, how did the system classify June sales by segment?"

Documentation must specify the **report publishing policy**: whether prior periods are restated, who approves retroactive fixes, and whether published snapshots are preserved.

## 9. Source-to-Target Mapping: Field-Level Transformation Docs

A mapping table should include at least:

| Target Field | Source | Rule | Time Semantics | Verification |
|---|---|---|---|---|
| `source_system` | Authenticated connector metadata | Canonical namespace ID | At ingest | Non-empty, in source registry |
| `tenant_id` | Orders `tenant_id` | Preserve namespace, never guess from order ID | At event | Authorization and tenant existence |
| `order_id` | Orders `id` | Stable source identifier | At confirmation | Unique within stated scope |
| `line_no` | `order_items.line_no` | Line sequence/ID at confirmation | At confirmation | Non-NULL, unique within order |
| `confirmed_at` | `OrderConfirmed.confirmedAt` event | Parse ISO 8601 → `TIMESTAMPTZ` | **Event time** | Never overwrite with load time |
| `ingested_at` | Pipeline metadata | Timestamp when target received record | **Processing time** | Never use for sales date |
| `customer_id` | Orders `customer_id` | Map within right tenant | At confirmation | Never mix IDs across sources |
| `customer_segment_key` | History dimension | As-of lookup at `confirmed_at` | **Valid time** | Exactly 1 version or exception handling |
| `quantity` | Source order line | Locked quantity units | At confirmation | Valid range and unit |
| `unit_price` | Line price at confirmation | Decimal, never read current product price | At confirmation | Correct currency unit |
| `line_discount_amount` | Locked line discount | Decimal, per policy | At confirmation | Within policy bounds |
| `booked_amount` | Derived from order line | `quantity * unit_price - discount` | Per event | Line-by-line check |
| `currency_code` | Orders `currency_code` | Confirmed currency code | At confirmation | Never sum mixed currencies |

**Why record time semantics in the mapping table?** Because pulling `product.category` from the **current table** versus pulling the **version at purchase time** can share the exact same source column name while yielding completely different historical KPIs.

### 9.1. When Multiple Sources Supply the Same Field

For example, `customer_segment` may exist in CRM, Billing, and Orders. Never arbitrarily pick whichever source has the newest timestamp. Documentation must specify:

- Which system **owns the definition** of "segment" for this KPI.
- Source precedence order if valid fallbacks exist.
- When a source is considered **stale or faulty**.
- Conflict resolution, retroactive adjustments, and cross-system customer identity mapping.
- Reconciliation and escalation to the owner.

**A newer timestamp does not prove greater business accuracy.** Two systems may measure distinct concepts (marketing segment vs. credit segment).

### 9.2. A Copy Never Creates a New Source of Truth

If `orders` owns the confirmation event, `fact_confirmed_order_lines` is derived data. Changing storage engines to document, graph, or columnar warehouse **does not change truth ownership**. Consumers must never edit the fact table expecting Orders to update state.

## 10. Reusable Model Documentation Template

Below is an **illustrative YAML template inside lesson materials showing a data contract**, **not** the three-field structure of lesson metadata files.

~~~yaml
model: mart.fact_confirmed_order_lines
document_version: 1
owner:
  business: Orders Domain
  technical: Data Platform
purpose: Booked merchandise value after discount by date and product

grain:
  statement: >
    One order line of an order within a tenant and source_system,
    at a valid confirmation per source rules.
  business_key:
    - source_system
    - tenant_id
    - order_id
    - line_no
  duplicate_policy: Reject_or_quarantine_conflicting_duplicates

source:
  authority: Orders Service
  interface: order.confirmed event and line snapshot
  capture: transactional_outbox_or_approved_CDC
  raw_retention: According_to_data_policy
  reprocessability: From_approved_replay_or_snapshot

time:
  event_time: confirmed_at
  ingest_time: ingested_at
  report_timezone: Asia/Ho_Chi_Minh
  effective_dimension_lookup: customer_segment.valid_from_valid_to
  interval_convention: "start_inclusive_end_exclusive"
  late_event_policy: Reconcile_and_restate_within_approved_window
  finalization: Business_owner_approves_period_close

measure:
  booked_amount:
    formula: quantity * unit_price - line_discount_amount
    meaning: booked_merchandise_after_line_discount
    aggregation: sum_when_no_fanout_and_same_currency
    exclusions: [shipping_fee, tax, refunds]
  currency_code:
    meaning: source_transaction_currency

tests:
  - unique_business_key
  - valid_source_namespace
  - exactly_one_effective_customer_version_or_exception
  - amount_formula
  - no_unexplained_source_target_reconciliation_gap

change_control:
  contract_review: Orders_and_Data_Platform
  consumers: [Finance_Reporting, Commercial_Dashboard]
~~~

Values like `Orders Domain`, consumer names, late-event policies, and exclusions are **learning assumptions**, not data from any specific enterprise. Production documentation must be **confirmed by owners**, especially monetary formulas and period-close rules.

### 10.1. Information Belonging in a Model Card

| Category | What to Document |
|---|---|
| Identity | Model ID, name, description, version, owner, environment |
| Purpose | Supported questions, KPIs, and **unsupported questions** |
| Grain | What one row is, business key, tenant/source scope, duplicate policy |
| Schema | Columns, types, nullability, defaults, units, enums, PK/FK |
| Source | Source of truth, topic/API/table, ingestion mechanism, SLA |
| Mapping | Field-level lineage, formulas, filters, JOINs, quality checks |
| Time | Event, valid, system, ingest, snapshot, timezone, period close |
| History | Type 1/Type 2/bitemporal, correction and late-event handling |
| Permissions | Data classification, authorized consumers, retention, and derived erasure |
| Correctness | Uniqueness, completeness, referential checks, source reconciliation |
| Operations | Latency, load, recovery, replayability, incident owner |
| Evolution | Changelog, consumer impact, versioning/deprecation rules |

**Never leave critical specs solely inside a SQL comment that can vanish upon schema recreation.** Maintain version-controlled/registry documentation linked to migrations, contract tests, and running pipelines.

## 11. Turning Documentation into Executable Tests

Documentation is credible only with evidence that data obeys the published **grain, source, and time** rules.

### 11.1. Unique Grain Test

~~~sql
SELECT
    source_system, tenant_id, order_id, line_no,
    COUNT(*) AS occurrences
FROM staging_confirmed_order_lines
GROUP BY source_system, tenant_id, order_id, line_no
HAVING COUNT(*) > 1;
~~~

For the example grain, this query must return zero rows **after staging applies approved deduplication rules**. If rows appear, never blindly slap `SELECT DISTINCT *` on top to hide differing data: two events with the same business key may hold **conflicting amounts or timestamps**, requiring source and version reconciliation.

If the source allows multiple confirmations per order, the grain differs and the test must include **confirmation identity**. Documentation is responsible for keeping tests and models **aligned**.

### 11.2. Event Time vs. Ingestion Time Lag Test

~~~sql
SELECT
    source_system,
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (
        WHERE ingested_at < confirmed_at
    ) AS apparent_negative_lag,
    COUNT(*) FILTER (
        WHERE ingested_at - confirmed_at > INTERVAL '1 hour'
    ) AS rows_later_than_one_hour
FROM fact_confirmed_order_lines
GROUP BY source_system;
~~~

Negative lag **does not automatically prove a bug**: the source clock might be skewed, events may be backdated per policy, or load timestamps may follow a different definition. Investigate definition/capture and clock sync. The one-hour threshold is **merely an example**, not a universal SLO.

### 11.3. Source-to-Target Reconciliation by Key and Period

Assuming the source is normalized to matching grain, currency, and formula, reconcile:

~~~sql
WITH source_daily AS (
    SELECT
        (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS business_date,
        currency_code,
        COUNT(*) AS source_lines,
        SUM(quantity * unit_price - line_discount_amount)
            AS source_booked
    FROM staging_confirmed_order_lines
    GROUP BY 1, 2
),
mart_daily AS (
    SELECT
        (confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS business_date,
        currency_code,
        COUNT(*) AS mart_lines,
        SUM(booked_amount) AS mart_booked
    FROM fact_confirmed_order_lines
    GROUP BY 1, 2
)
SELECT
    COALESCE(s.business_date, m.business_date) AS business_date,
    COALESCE(s.currency_code, m.currency_code) AS currency_code,
    s.source_lines, m.mart_lines,
    s.source_booked, m.mart_booked
FROM source_daily AS s
FULL OUTER JOIN mart_daily AS m
  ON s.business_date = m.business_date
 AND s.currency_code = m.currency_code
WHERE s.source_lines IS DISTINCT FROM m.mart_lines
   OR s.source_booked IS DISTINCT FROM m.mart_booked;
~~~

**Conditions for meaningful results:**

1. Both sides share identical tenant/source scope and valid event lists.
2. Both sides handle duplicates, updates, cancellations, and refunds **by identical rules**.
3. Identical timezone, currency, and precision/rounding.
4. Identical **watermark/cutoff**, or an explicit policy for late arrivals and restatement.

Without aligning these conditions, the query may flag **expected discrepancies** rather than actual bugs. Matching totals alone also do not prove individual rows are right; opposite errors can cancel out. Add reconciliation **by business key** and inspect exception samples.

### 11.4. Dimension Mismatch Checks

Minimum checks:

- Every event matches **exactly one effective dimension version** or enters a published exception queue.
- Historical effective intervals never overlap; open/close follows convention.
- No `customer_segment_key` cross-links the wrong customer/tenant.
- Current segment is never substituted when the KPI requires "at purchase time."
- When dimensions arrive late, facts are **backfilled with dimension keys** under control; affected reports are identified.

If a dimension uses an "Unknown" row to avoid dropping facts, document **why it is unknown, how long it may stay unknown, and when it must be backfilled**. Never silently treat Unknown as a real business segment.

### 11.5. Null, Completeness, and Measure Tests

~~~sql
SELECT
    source_system, tenant_id, order_id, line_no,
    quantity, unit_price, line_discount_amount, booked_amount
FROM fact_confirmed_order_lines
WHERE confirmed_at IS NULL
   OR currency_code IS NULL
   OR quantity <= 0
   OR booked_amount IS DISTINCT FROM
      quantity * unit_price - line_discount_amount;
~~~

In the illustrative DDL, some conditions are already enforced by PK/NOT NULL/CHECK. In analytical engines that do not enforce constraints, or on **staging before loading**, these checks remain essential.

**Never equate `NULL=0`.** Unknown values, not-applicable fields, load errors, and numeric zero are four distinct situations. Document them explicitly so checks never "fix data" using unapproved assumptions.

## 12. Documenting Late-Arriving Data and Retroactive Changes

Two situations must stay separate:

### 12.1. Late-Arriving Facts

~~~text
OrderConfirmed.occurredAt = 31/10
Warehouse receives event = 02/11
~~~

If the KPI counts orders by **confirmation date**, the transaction belongs to 31/10 under the defined timezone. Documentation needs:

- Threshold within which data is considered normally late.
- Watermark/offset tracking and idempotent event replay without duplicate loads.
- When prior-period numbers remain open to updates; who closes reports.
- How dashboards/consumers are notified when prior periods are restated.
- Reconciling late-arriving data against source event logs without altering `confirmed_at`.

### 12.2. Late-Arriving Dimensions

An order confirms at 09:15, while the customer's segment at purchase time syncs from CRM at 10:30.

**Conditional** handling patterns:

1. Hold the fact in staging before publishing if reports require complete dimensions.
2. Use a surrogate key for "Unknown/Not yet resolved" with a backfill queue and clear quality metrics.
3. Retain business key and event time to **re-resolve the version** when the dimension arrives; update facts/read models or reprocess depending on architecture.

Never casually substitute the current segment when `segment_at_confirmation` is missing, as that silently corrupts history.

### 12.3. Retroactive Corrections

Suppose on 03/07 CRM confirms a segment actually changed on 15/05. If June reports already used STANDARD, decide between:

- **Restatement:** recompute history using newly effective truth.
- **As-published:** keep published numbers and log separate adjustments.
- **Bitemporal:** support both the true-effective view and the "known at publication date" view.

No single choice fits every domain; financial reporting, regulatory filings, and marketing KPIs often follow different close policies.

### 12.4. Deletes/Tombstones Also Need Effective Timing

A "delete customer" event can mean:

- Customer became inactive **as of a business timestamp**.
- Record was deleted from the source system **at processing time**.
- Personal data must be erased/anonymized across copies per policy.

These meanings are not equivalent. Documentation must specify event type, copy scope, deadlines, and how historical figures are adjusted, while avoiding storing sensitive data forever in event replay logs merely to "keep history."

## 13. When Documentation Changes: Versioning, Consumers, and Migrations

Model documentation should never be written once and forgotten.

### 13.1. Changes Requiring Documentation Updates

| Change | Documentation Sections to Review |
|---|---|
| Changing key from `order_id` to `(tenant_id,order_id)` | Grain, namespace, unique/FK, JOINs, quality tests |
| Switching order-grain fact to line-grain fact | Grain, aggregation, COUNT DISTINCT, fanout, source mapping |
| Switching report time from `created_at` to `confirmed_at` | KPI, event time, timezone, restatement, dashboards |
| Adding SCD Type 2 | As-of lookup, interval convention, overlap tests, late dimensions |
| Switching source from CRM to customer master | Authority, lineage, mapping, diff tests |
| Adding a new currency | Currency, conversion policy, aggregation semantics, edge cases |
| Replacing batch with CDC | Watermark/offset, ordering, duplicates, lag, replay, retention |
| Dropping a column or API/event field | Consumer impact, compatibility, deprecation, and migration |
| Changing report cutoff window | Business date, update policy, published numbers |

### 13.2. Review Workflow Tied to Code/Schema Changes

~~~text
Change request
    ↓
Identify affected fields / grain / source / time
    ↓
Assess consumers and historical data
    ↓
Update model card + mapping + tests
    ↓
Business + technical + security review if relevant
    ↓
Execute expand / migrate / contract as needed
    ↓
Reconcile and measure impact
    ↓
Record changelog and effective date
~~~

Store documentation in a **traceably versioned** manner alongside schema migrations, SQL models, and API/event contracts, or in a catalog linked to commits/releases.

Example changelog:

~~~text
Version 1:
    line-level amount; business_date derived from confirmed_at (UTC)

Version 2:
    Same grain and formula,
    reports use tenant timezone from approved effective date
    Backfill/restatement rules recorded in migration record
~~~

Changing timezones can **alter daily numbers** without modifying any columns. That is a KPI semantic change requiring consumer notice, not just a query tweak.

### 13.3. Expand–Migrate–Contract for Schema and Documentation Changes

When evolving a model:

- **Expand:** add new structures/fields or versions; docs describe both old and new.
- **Migrate:** move data and consumers with mappings, backfills, and reconciliations.
- **Contract:** remove old fields/tables/contracts only once zero dependencies remain and history is handled.

Documentation identifies **the point of no easy rollback**: for example, once raw addresses, classification history, or non-replayable source events are dropped, legacy data may become unrecoverable.

## 14. Connecting Model Documentation to APIs, Events, and Analytics

### API: Returning Current State or Point-in-Time State?

`GET /customers/{id}` may return the **current** segment. `GET /orders/{id}` may return the **current** order. If consumers need "order as known on 30/06," the API must **publish as-of capabilities** backed by sufficient history; never slap an `asOf` query parameter onto a current-state-only DB.

JSON responses typically need documentation on read timestamp, freshness, and consistency level (cache, replica).

### Event: Occurrence Time Differs from Receipt Time

`OrderConfirmed` contains:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "O7",
  "tenantId": "T01",
  "occurredAt": "2026-10-31T23:58:00Z",
  "schemaVersion": 1
}
~~~

`occurredAt` is the business milestone published by the event owner; consumers must not replace it with `receivedAt`. `eventId` handles **logical deduplication**, whereas `orderId` identifies the order. If one order emits multiple distinct events, **never use `orderId` as the unique event ID**.

### Analytics: Choosing Dimension Grain and Effective Time

In a star schema:

~~~mermaid
flowchart LR
    D["dim_date"] --> F["fact_confirmed_order_lines"]
    P["dim_product (versioned)"] --> F
    C["dim_customer_segment_history"] --> F
    F --> R["booked_amount + event time"]
~~~

If the fact uses `customer_segment_key` resolved at `confirmed_at`, reports reflect segment **at purchase time**. If a dashboard joins directly to the **current** customer table, it reports by **current** segment. Both can be valid, yet **cannot share the same KPI name without clarification**.

## 15. Comparing Documentation Across Data Model Paradigms

| Model Type | Grain to Document | Source and Time to Document | Specific Risks |
|---|---|---|---|
| **Relational OLTP** | Does a row represent an entity/state or history? PK/FK in which namespace? | Who writes, transactions, effective columns, audit | `updated_at` mistaken for effective date |
| **Document** | Is one document an order or an update? What is the grain of `items[]`? | Document version, snapshots, source events | Flattening arrays multiplies order-level measures |
| **Graph** | Is node/edge or path the counted unit? Are relationships time-bounded? | Edge owner, `valid_from/to`, update source | Finding one relationship via multiple paths causes double counting |
| **Time series** | A series is metric + labelset; a sample is series + timestamp | Measurement time, ingest time, frequency, missing samples | Label cardinality/churn; timestamps used as labels |
| **Data warehouse/star** | Transaction, periodic snapshot, or accumulating snapshot | Event/snapshot time, SCD, late data | JOIN fanout and summing semi-additive measures across time |
| **Event stream** | One logical event or one delivery attempt? | `eventId`, `occurredAt`, `publishedAt`, offset | Duplicates, out-of-order, replay/versioning |

**Common thread:** every engine requires explaining **data units**, **truth ownership**, and **time semantics**. Switching from PostgreSQL to a document store, graph DB, or columnar warehouse does not make these questions vanish.

## 16. Common Misconceptions

| Misconception | Why Wrong | Prevention |
|---|---|---|
| "Grain = technical primary key" | Surrogate keys do not stop an event from loading twice | Write business grain and unique tests |
| "`COUNT(*)` is always order count" | Line-grain facts have multiple lines per order | Distinguish line, order, and event |
| "Source = last table read" | Fails to identify owner and fact-creation rules | Record business owner, source of truth, capture, and lineage |
| "Newest data from any system wins" | Two systems may use different definitions | Approved authority rules and mappings |
| "`created_at` is event time" | Records can be created before confirmation | Specify `event_time` per KPI |
| "`ingested_at` works as sales date" | Late events distort periods | Separate event time from processing time |
| "`updated_at` is already bitemporal" | Lacks history of what the system knew | Separate valid-time and system-time; retain versions |
| "Only `valid_from` is needed" | Unclear when old versions expire | Use `valid_to` and explicit interval bounds |
| "Overlapping effective intervals are harmless" | One fact joins to multiple versions, multiplying money | Unique match and overlap tests |
| "Drop facts missing dimensions" | Sales vanish silently without alerts | Quarantine/unknown handling and monitored backfill |
| "Current segment equals segment at purchase" | Historical shifts get erased | SCD Type 2/snapshots and as-of lookups |
| "Amounts are NUMERIC so they can be summed" | Mixed currencies/definitions or fanout | Document units, KPIs, and grain |
| "Matching totals prove data is correct" | Row-level errors can cancel out | Reconcile keys, rows, and totals |
| "SQL schema explains everything" | Lacks source, timing, and exceptions | Model card/data dictionary/source mapping |
| "Report tweaks don't need doc updates" | Consumers miss KPI semantic shifts | Reviews/changelogs and contract tests |
| "Source deletion erases all copies" | Raw events, marts, caches, backups may retain data | Lineage, retention, and derived erasure |

## 17. Practice Exercises with Solutions

### Exercise 1 — Writing a Grain Statement

A table contains `order_id`, `line_no`, `product_id`, `amount`. An order can have multiple lines, and `order_id` is reused across tenants. Write the grain.

**Solution:** Example: "One fact row represents **one order line `(tenant_id,order_id,line_no)` of a confirmed order at its valid confirmation**." If sources allow multiple confirmations, add `confirmation_id`/version. `order_id` alone is insufficient.

### Exercise 2 — PK Does Not Guarantee Grain

A fact table has auto-incrementing `fact_row_id` and holds two rows with different `fact_row_id`s but identical `(tenant_id,order_id,line_no)`. Are both rows guaranteed valid?

**Solution:** No. `fact_row_id` is merely a technical key. If the grain is one line per confirmation, two rows could be **duplicates** or conflicting data. Check business keys and version/event rules.

### Exercise 3 — Counting Orders vs. Lines

D01 has three lines; D02 has two lines. What does `COUNT(*)` on the line-grain fact return? How do you count orders?

**Solution:** **5 order lines**, yet **2 orders**. Count distinct on the **full order key** (including tenant/source if needed) or query an order-grain fact; never sum distinct order counts across overlapping groups.

### Exercise 4 — Event Time vs. Ingestion Time

An order confirms at `2026-10-31T23:58:00Z`, and the pipeline receives it at `2026-11-01T00:07:00Z`. In a report by UTC confirmation month, which month does it belong to?

**Solution:** **October**, because `confirmed_at` is used. `ingested_at` measures lag and operations, never replacing business timestamps.

### Exercise 5 — Grouping by Timezone

`confirmed_at=2026-11-21T18:30:00Z`. In a report by Vietnam business date, which date is it?

**Solution:** **22/11/2026** in `Asia/Ho_Chi_Minh` (UTC+7 at that time). In a UTC report it is 21/11. **Timezone is part of the KPI definition**.

### Exercise 6 — SCD2 Interval Boundaries

Customer C17 is STANDARD until `2026-06-01T00:00Z` (exclusive), then VIP from that exact instant. Which segment should an order confirmed at `2026-06-01T00:00Z` belong to?

**Solution:** **VIP**. Under half-open intervals `[valid_from,valid_to)`, VIP's start boundary is inclusive whereas STANDARD's end boundary is exclusive.

### Exercise 7 — Overlapping Dimension History

Customer C17 has two effective records `[01/01,01/09)` and `[01/06,01/12)`. How many versions does an order confirmed in July join to?

**Solution:** **2 versions**, violating the single-segment-at-a-time invariant if only one is allowed. The JOIN can **multiply fact rows**, so history must be validated/resolved before aggregating.

### Exercise 8 — Is `recorded_at` Bitemporal?

A history table only has `valid_from`, `valid_to`, and `recorded_at`. After a correction, old rows are updated in place and prior state is lost. Can you reliably answer "what did the system know on 30/06"?

**Solution:** **No**, unless prior knowledge versions are preserved. One `recorded_at` column is insufficient; system-time history or reconstructible audits are needed.

### Exercise 9 — Source of Truth

BI reads revenue from a data mart; the data mart reads events emitted by Orders. When a dispute arises over the definition of "confirmed order," which system is the owner?

**Solution:** **Orders domain**, if Orders owns the confirmation transition. The data mart is an analytical projection. KPI owners may define additional reporting formulas, but the mart must not unilaterally alter source event definitions.

### Exercise 10 — Late-Arriving Dimensions

An order confirms at 09:00, but CRM sends the point-in-time segment version at 11:00. Can you immediately use the current segment and call it "at purchase time"?

**Solution:** Not by default. You can wait for the dimension, use a monitored unknown key, or backfill as-of once the historical version arrives; document the policy and its impact on published reports.

### Exercise 11 — Reconciling Monetary Totals

Source has two rows `100` and `200`; mart has `150` and `150`, same currency and scope. Both totals equal 300. Has correctness been proven?

**Solution:** **Not yet**. Totals match while individual rows are wrong. Compare by business key and row-level measures, not only period totals.

### Exercise 12 — Changing Reporting Time

A dashboard groups by `created_at`; business changes it to `confirmed_at` while keeping the metric name. Is editing SQL enough?

**Solution:** No. This is a **semantic change** to the KPI that can shift transactions across days/months. Update the model card, lineage, tests, changelog, restatement policy, and notify consumers.

### Exercise 13 — Flattening a Document Order

A source document has `orderTotal=300` and three `items[]` elements. A pipeline flattens `items[]` into three rows, copies `orderTotal=300` onto each row, and runs `SUM`. What are the result and bug?

**Solution:** The sum becomes **900** instead of 300. Document grain is **one order**, whereas post-flatten grain is **one item**. Use line-level measures or keep `orderTotal` in an order-grain fact without repeating order-level totals.

## 18. Model Documentation Review Checklist

- [ ] Clear **business purpose, supported questions, and owner**.
- [ ] Exact **grain statement** for every table/fact/event/document.
- [ ] Complete **business key** with namespace, versioning rules, and uniqueness tests.
- [ ] Never conflates **surrogate keys** with business identity.
- [ ] Every measure has **units, currency, formula, aggregation rules, and exclusions**.
- [ ] **Source of truth**, source location, capture mechanism, and technical owner identified.
- [ ] Field-level **source-to-target mapping** and lineage back to original sources.
- [ ] JOINs specify **cardinality**, preventing measure multiplication.
- [ ] Distinguishes **event time, valid time, system/recorded time, ingestion time, snapshot time**.
- [ ] Includes timezone, business calendar, and day/period cutoff rules when using reporting time.
- [ ] For effective intervals, documents `[from,to)`, `NULL` semantics, and time precision.
- [ ] For historical dimensions, selects Type 1/Type 2/bitemporal per real needs.
- [ ] Tests for **non-overlapping intervals** and exactly one matched version in as-of joins.
- [ ] Policies for **late facts, late dimensions, corrections, restatement, and replay**.
- [ ] Handling for **missing, NULL, conflicting, duplicate, or unavailable source** data.
- [ ] Tests for referential integrity, completeness, measure formulas, and source-to-target reconciliation.
- [ ] Documents access permissions, data classification, retention, and derived copies.
- [ ] Docs tied to **schema/API/event versions**, with changelogs, reviews, and consumer impact.
- [ ] Tested on edge cases: tenant switches, late events, overlapping versions, boundary dates, replay jobs.

**Takeaway:** Data model documentation earns its value when readers can accurately answer **"what is one row, who owns this fact, and when is it true?"** Grain dictates keys and aggregations; source dictates accountability and reconciliation; effective time dictates how history is interpreted. Encoding all three into a **testable, versioned contract** lets relational, document, graph, and analytical models evolve without sacrificing data correctness.
