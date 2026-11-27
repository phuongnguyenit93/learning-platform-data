# Building a Sales Fact Table with Analytical Dimensions

## Goals and expected outputs

This is an **integrated exercise** in the **DATABASE_DATA_MODELING** module, **Integrated Exercises** chapter. You will go from sales reporting requirements to a **star schema** featuring a fact table, dimension tables, keys and constraints, a data-loading pipeline, KPI queries, and reconciliation tests. The goal is not merely creating tables that run, but **explaining why the data is accurate in grain, timestamps, currency, history, and access control**.

After this lesson, learners should be able to:

1. Translate reporting requirements into **business processes, events, grains, and measures**.
2. Design a fact at **one order line of a confirmed order**, avoiding accidentally counting lines as orders.
3. Design dimensions for **date, product variant, buyer/segment, sales channel, and store**, identifying which require **Slowly Changing Dimension Type 2 (SCD2)** history.
4. Distinguish **surrogate dimension keys** from **natural/business keys** and **degenerate dimensions**.
5. Write PostgreSQL DDL with tenant-scoped PK/FKs, `CHECK`s, `UNIQUE`s, and indexes.
6. Build a **stage → validate → resolve as-of dimension → upsert fact → reconcile → publish** flow resilient to retries and late-arriving events.
7. Answer KPIs by date/product/channel/store without multiplying totals after JOINs; handle **multiple currencies, guest buyers, cancellations, and refunds** properly.
8. Catch issues with **late-arriving dimensions, Type 1/Type 2 dimensions, access permissions, PII, data quality, and performance**.
9. Complete the exercise set and check solutions; prove the design with repeatable verification queries.

> **Technical scope:** examples use PostgreSQL to analyze confirmed sales transactions by confirmed item amount. This is **not automatically accounting revenue, captured cash, or net sales after refunds**. Those KPIs require separate sources, events, and rules. Currency names, timestamps, and definitions used here are exercise contracts, not universal standards.

## 1. Prompt: sales leadership wants trustworthy reports

A business operates physical stores and online sales. The OLTP system records:

- Confirmed **Orders** and **OrderLines**.
- Products with multiple **variants/SKUs**; variants can change name, category, and brand.
- Registered buyers have **segments** (`NEW`, `RETURNING`, `VIP`...) that change over time. Some orders are guest checkouts without login.
- Channels include `WEB`, `APP`, `STORE`; stores belong to operational regions.
- Payment systems emit separate capture/refund events; one order may have multiple payments.
- Systems have distinct timestamps: order confirmation, event receipt, and warehouse ingestion.

Users want:

1. **Merchandise value and units sold** by date, category, channel, and store region.
2. **Distinct order counts** and line counts along every dimension.
3. **Historical analysis**: if a product moves from category A to B, past monthly reports still show the category at purchase time.
4. View **buyer segment at confirmation time**, not retroactively labeling all past orders with today's VIP tag.
5. Re-run loads after incidents **without double-counting any line**.
6. Exclude emails, phone numbers, or recipient street addresses from general-purpose fact tables.
7. Never silently drop part of sales when dimension mapping fails.

### 1.1. Locking down KPI definitions before drawing tables

| KPI | Definition in this exercise | Grain when computing |
| --- | --- | --- |
| **confirmed_line_count** | Count of confirmed order lines in filter scope | One fact row/line |
| **confirmed_unit_quantity** | Sum of quantity across lines | Order line; sum only when units match |
| **confirmed_gross_amount** | Sum of `quantity × locked unit_price`, before allocated discounts | Line, grouped by currency |
| **allocated_discount_amount** | Sum of discounts allocated to lines | Line |
| **confirmed_net_items_amount** | Gross minus line discount; excludes tax/fees in this example | Line, grouped by currency |
| **distinct_confirmed_order_count** | Count of distinct `order_id`s confirmed, not `COUNT(*)` on fact | Order; requires distinct grouping |
| **distinct_registered_buyer_count** | Count of distinct source buyers where authorized and identity rules fit | Buyer; requires identity governance and history |

One **Order** with two lines creates **two rows** in the proposed fact table, yet contributes **one** to distinct order count. Never call `COUNT(*)` on a line-grain fact `order_count`.

### 1.2. Reference data for verification

Suppose order **O-1001** of tenant 17 confirmed on Nov 22, 2026 Vietnam time:

| Line | Variant | Quantity | Unit price | Line discount | Gross | Net |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | PHONE-BLACK-128 | 2 | 150,000 VND | 20,000 VND | 300,000 VND | 280,000 VND |
| 2 | CASE-BLACK | 1 | 50,000 VND | 5,000 VND | 50,000 VND | 45,000 VND |
| **Order total** | | **3** | | **25,000 VND** | **350,000 VND** | **325,000 VND** |

When reporting **all items of O-1001**:

- **`confirmed_line_count = 2`**.
- **`confirmed_unit_quantity = 3`**, since examples share unit count ("piece").
- **`distinct_confirmed_order_count = 1`**.
- **`confirmed_net_items_amount = 325,000 VND`**.

Joining the line fact with an order table carrying header **325,000 VND** and summing the header across both rows yields **650,000 VND**—a **grain** bug, not a PostgreSQL bug.

## 2. Selecting business process and grain before tables

Multiple business processes touch “sales”:

| Process | Matching event/snapshot | Candidate grain |
| --- | --- | --- |
| Order confirmation | `OrderConfirmed` | One confirmed order line |
| Cash capture | `PaymentCaptured` | One capture transaction |
| Refunds | `RefundSucceeded` | One refund line or refund allocation |
| Warehouse dispatch | `StockMovement` | One inventory movement |
| Parcel delivery | `ShipmentDelivered` | One shipment/attempt |
| End-of-day stock | `InventoryEOD` | One variant × warehouse × date |
| Current order status | `OrderStateProjection` | One order at read time |

Never lump all of them into one fact table with a generic `amount` column. Every fact needs an explicit **grain** and **measure definitions**.

### 2.1. Official grain for this exercise

> **One row of `fact_sales_line_confirmed` represents one order line (`line_no`) of one confirmed order (`source_order_id`) within a tenant. It preserves quantity, price, and discount at confirmation time—not the current mutable line status.**

Natural source identifier:

~~~text
(tenant_id, source_order_id, source_line_no)
~~~

In this example, a line is confirmed once per source contract. If the business allows **re-confirming an order and altering lines across revisions**, add `confirmation_id`, `event_version`, or pick a different event grain; never silently overwrite an already-confirmed line.

**Post-confirmation cancellations/returns** should use dedicated event/fact tables or audited adjustment rules. Never delete a confirmed transaction simply because the order later moved to `CANCELLED` if the KPI asks “what was confirmed?”.

### 2.2. Why pick order-line grain?

Because users analyze by **product/variant**. One Order spans multiple SKUs; an order-grain fact cannot break totals down by SKU without allocation rules.

Line grain enables:

- Analyzing money and quantities by product, time, and channel.
- Linking dimensions capturing product attributes at transaction time.
- Computing order totals **as the sum of lines** when allocation formulas are explicit.

With trade-offs:

- **Distinct order count** is **non-additive** across product groups: an order buying two categories counts in both categories.
- Never `SUM` a **header order amount** after joining multiple lines.
- If orders carry **shipping fees, order-level discounts, or taxes**, allocate them via agreed rules or store dedicated facts/measures. Never dump fees onto line 1 and call it standard product revenue.

## 3. Bus matrix: which dimensions does the fact need?

A **bus matrix** shows which dimensions each business process uses. In this exercise:

| Business process / fact | Date | Product | Buyer | Channel | Store | Currency |
| --- | --- | --- | --- | --- | --- | --- |
| Confirmed order line | `confirmed_date` | product SCD2 | buyer SCD2 or guest | sales channel | store nullable for online | `currency_code` |
| Cash capture (extension) | `captured_date` | May omit if order-level capture | payer if needed/authorized | payment channel | Not always applicable | capture currency |
| Refund (extension) | `refunded_date` | SKU if refund is allocable | buyer/refund actor | source channel | Per policy | refund currency |
| End-of-day stock (extension) | `snapshot_date` | product/variant | N/A | N/A | warehouse dimension | quantity unit |

In the core exercise, dimensions are:

- **`dim_date`**: confirmation date in the business timezone.
- **`dim_product_scd2`**: product attribute **version** effective at confirmation.
- **`dim_buyer_scd2`**: buyer segment **version** effective at confirmation, omitting name/email.
- **`dim_channel`**: sales channel source.
- **`dim_store`**: store with region, nullable for online orders.
- **`currency_code`**: degenerate code/unit on the fact; expand to `dim_currency` when FX rates and attributes are needed.

**`source_order_id`** and **`source_line_no`** sit on the fact as **degenerate dimensions**: used for drill-through and source reconciliation without creating a single-column `dim_order`. Source keys are **not surrogate fact keys**.

### 3.1. Target star schema

~~~text
                   dim_date
                (date_key, date)
                       |
                       v
dim_product_scd2 --> fact_sales_line_confirmed <-- dim_channel
(product_key)           |                   (channel_key)
                        |
dim_buyer_scd2 ---------+------------------- dim_store
(buyer_key)                                 (store_key)
                        |
              source_order_id, line_no
                   degenerate IDs
                        |
          quantity, unit_price, discount,
          gross_amount, net_sales_amount,
          currency_code, confirmed_at
~~~

Every dimension must resolve to **one row referenced by the fact** at confirmation time, preventing a single fact row from fanning out across multiple product or buyer versions.

## 4. Key principles for a multi-tenant warehouse

PostgreSQL examples use:

- **`tenant_id`**: organizational and authorization boundary.
- **`product_key`, `buyer_key`, `channel_key`, `store_key`**: warehouse-issued **surrogate dimension keys**.
- **`source_variant_id`, `source_buyer_ref`, `channel_code`, `store_code`**: **natural/business references** to source systems.
- **`source_order_id`, `source_line_no`**: IDs tracing facts back to source events.
- **`confirmed_date_key`**: integer `YYYYMMDD` key into `dim_date` for calendar grouping, never replacing full timestamps.

`BIGINT GENERATED ALWAYS AS IDENTITY` keys here are technical warehouse surrogates; never mistake them for business IDs or API-safe tokens. For historical dimensions, **one natural ID maps to multiple surrogate keys**, one per version.

**Never JOIN facts to SCD2 tables on natural product ID without a time-range predicate**, or you multiply revenue whenever a product has two versions.

For tenant-scoped tables, we use composite FKs **`(tenant_id, dimension_key)`** so Tenant A facts cannot point to Tenant B dimensions. This protects referential scope; apps and DB roles still need separate **tenant authorization**.

## 5. DDL Part 1 — Date dimension

### 5.1. Locking down reporting date convention

This lesson uses **Vietnam business date (`Asia/Ho_Chi_Minh`)** derived from Sales-confirmed `confirmed_at TIMESTAMPTZ`. A record ingested next day still belongs to its confirmation date, not `loaded_at`.

Multi-timezone businesses must define dates by **store/business unit** and model dimensions/reports accordingly; never force everything into Vietnam time without an explicit decision as assumed in this exercise.

### 5.2. Creating `dim_date`

~~~sql
CREATE SCHEMA mart;

CREATE TABLE mart.dim_date (
    date_key INTEGER NOT NULL,
    calendar_date DATE NOT NULL,
    calendar_year INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL,
    calendar_quarter INTEGER NOT NULL,
    iso_year INTEGER NOT NULL,
    iso_week INTEGER NOT NULL,
    iso_day_of_week INTEGER NOT NULL,
    month_start_date DATE NOT NULL,

    CONSTRAINT pk_dim_date PRIMARY KEY (date_key),
    CONSTRAINT uq_dim_date_calendar_date UNIQUE (calendar_date),
    CONSTRAINT ck_dim_date_month
        CHECK (calendar_month BETWEEN 1 AND 12),
    CONSTRAINT ck_dim_date_iso_day
        CHECK (iso_day_of_week BETWEEN 1 AND 7)
);
~~~

Seed 2024–2029 calendar in PostgreSQL:

~~~sql
INSERT INTO mart.dim_date (
    date_key, calendar_date, calendar_year,
    calendar_month, calendar_quarter,
    iso_year, iso_week, iso_day_of_week, month_start_date
)
SELECT
    to_char(g.d::DATE, 'YYYYMMDD')::INTEGER,
    g.d::DATE,
    EXTRACT(YEAR FROM g.d)::INTEGER,
    EXTRACT(MONTH FROM g.d)::INTEGER,
    EXTRACT(QUARTER FROM g.d)::INTEGER,
    EXTRACT(ISOYEAR FROM g.d)::INTEGER,
    EXTRACT(WEEK FROM g.d)::INTEGER,
    EXTRACT(ISODOW FROM g.d)::INTEGER,
    date_trunc('month', g.d)::DATE
FROM generate_series(
    '2024-01-01'::TIMESTAMP,
    '2029-12-31'::TIMESTAMP,
    INTERVAL '1 day'
) AS g(d)
ON CONFLICT (date_key) DO NOTHING;
~~~

In PostgreSQL, **`WEEK`** follows ISO week numbering and **`ISOYEAR`** can differ from `calendar_year` around New Year boundaries. Pair `iso_week` with `iso_year` rather than grouping by `calendar_year` alone.

If real data contains dates outside the seeded range, ETL must flag **missing date dimension** and extend `dim_date` before publishing—never coerce into an arbitrary date.

## 6. DDL Part 2 — SCD Type 2 product dimension

Core requirement: **`PHONE-BLACK-128`** belonged to **`ELECTRONICS`**, then moved to **`SMARTPHONES`**. Historical reports must keep the attribute **effective at transaction time**.

### 6.1. One surrogate key per version

~~~sql
CREATE TABLE mart.dim_product_scd2 (
    tenant_id BIGINT NOT NULL,
    product_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_variant_id UUID NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    category_code TEXT NOT NULL,
    brand_code TEXT,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,

    CONSTRAINT pk_dim_product_scd2
        PRIMARY KEY (tenant_id, product_key),
    CONSTRAINT uq_dim_product_natural_version
        UNIQUE (tenant_id, source_variant_id, valid_from),
    CONSTRAINT ck_dim_product_effective_range
        CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_dim_product_current_range
        CHECK (is_current = (valid_to IS NULL))
);

CREATE UNIQUE INDEX uq_dim_product_current_natural
ON mart.dim_product_scd2 (tenant_id, source_variant_id)
WHERE valid_to IS NULL;

CREATE INDEX ix_dim_product_resolve_asof
ON mart.dim_product_scd2 (
    tenant_id, source_variant_id, valid_from, valid_to
);
~~~

**Definitional invariants:**

- Two rows with the same `source_variant_id` are **two dimension versions**, not two SKUs.
- Effective intervals are **`[valid_from, valid_to)`**: inclusive start, exclusive end.
- Current row has `valid_to IS NULL` and `is_current = TRUE`.
- Partial unique index blocks **two current rows** for the same natural ID in a tenant.

**Limitation:** `CHECK` and current-only unique indexes **do not automatically stop overlapping historical intervals**, e.g., `[01/01, 01/06)` and `[01/04, 01/05)`. Add a range **exclusion constraint** (with `btree_gist`) or serialize/validate SCD2 writes to prevent overlaps. Never claim “SCD2 is guaranteed right” just because you added `is_current`.

### 6.2. Time-versioned example

| product_key | source_variant_id | category_code | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 9001 | V-101 | ELECTRONICS | 2026-01-01 | 2026-09-01 |
| 9120 | V-101 | SMARTPHONES | 2026-09-01 | NULL |

These are illustrative IDs; the DDL uses source UUIDs and `BIGINT` surrogates. A fact confirmed on **Aug 20, 2026** points to **9001**. A fact on **Nov 22, 2026** points to **9120**. When a variant switches categories, **never update August facts' `product_key` to 9120** when KPIs require historical attributes.

### 6.3. Type 2 update procedure

When the source reports a **Type-2-tracked** attribute change effective at **T**:

1. Validate source ID, tenant, ordering/version, and effective timestamp `T`.
2. Close the old current row with **`valid_to = T`**, **`is_current = FALSE`**, verifying `T > valid_from`.
3. Insert the new row **`valid_from = T`**, **`valid_to = NULL`**, **`is_current = TRUE`**.
4. Execute inside a transaction, locking or serializing writes on the same natural ID.
5. Verify zero overlaps and exactly one current row.
6. Emit a dimension-ready/checkpoint signal for fact ETL.

If a late-arriving edit carries an **effective time between two existing versions**, you cannot simply close current and append at the end. **Split/adjust historical intervals**, verify adjacent boundaries, and **re-evaluate affected facts** per restatement policy.

**Choose Type 1 vs Type 2 per attribute.** Fixing a typo in `product_name` may use Type 1 if the business wants history corrected; changing `category_code` for historical breakdowns needs Type 2. Never blindly put every attribute into SCD2 without reason and cost analysis.

## 7. DDL Part 3 — Versioned buyer dimension with identity bounds

To analyze **segment at purchase time**, use **`dim_buyer_scd2`** with `source_buyer_ref` as a scoped pseudonymous ID; the dimension **omits full names, emails, phone numbers, and street addresses**.

~~~sql
CREATE TABLE mart.dim_buyer_scd2 (
    tenant_id BIGINT NOT NULL,
    buyer_key BIGINT GENERATED ALWAYS AS IDENTITY,
    source_buyer_ref UUID NOT NULL,
    buyer_segment_code TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,

    CONSTRAINT pk_dim_buyer_scd2
        PRIMARY KEY (tenant_id, buyer_key),
    CONSTRAINT uq_dim_buyer_natural_version
        UNIQUE (tenant_id, source_buyer_ref, valid_from),
    CONSTRAINT ck_dim_buyer_effective_range
        CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_dim_buyer_current_range
        CHECK (is_current = (valid_to IS NULL))
);

CREATE UNIQUE INDEX uq_dim_buyer_current_natural
ON mart.dim_buyer_scd2 (tenant_id, source_buyer_ref)
WHERE valid_to IS NULL;

CREATE INDEX ix_dim_buyer_resolve_asof
ON mart.dim_buyer_scd2 (
    tenant_id, source_buyer_ref, valid_from, valid_to
);
~~~

**Privacy note:** a pseudonymous UUID can still link multiple orders to one individual. It **is not automatically anonymous**; govern permissions, purpose, retention, and mapping back to real identities at the source. Segment summary reports usually need only `buyer_segment_code` and measures, never exposing `source_buyer_ref`.

If a buyer upgrades **NEW → VIP** in September, August facts hold the **NEW** `buyer_key` while November facts hold the **VIP** `buyer_key`. Running **`COUNT(DISTINCT buyer_key)`** across months counts **buyer versions** rather than unique individuals.

To count distinct buyers consistently over time, use **governed pseudonymous natural references under appropriate permissions** or a governed identity bridge—never blindly expose raw identities in broad reports.

### 7.1. Guest orders vs unmatched registered buyers

Distinguish cleanly:

- **GUEST**: source explicitly states no identified account; `buyer_key` is **intentionally NULL**.
- **REGISTERED**: has `source_buyer_ref`; must resolve to a **`buyer_key` at confirmation time** before entering the main fact dataset.
- **PENDING/UNMATCHED**: source ID present yet dimension not loaded yet. This is **not GUEST**; quarantine and process as a late-arriving dimension.

You may use an **unknown dimension row** if organizational conventions prefer it, provided you distinguish **truly unknown**, **lagging**, and **not applicable**. In this exercise we use `NULL` intentionally for guests and **block REGISTERED rows missing mappings** before publishing.

## 8. DDL Part 4 — Sales channels and stores

Sales channels have natural ID **`channel_code`** (e.g., `WEB`, `APP`, `STORE`); stores have **`store_code`**. Both dimensions below use **Type 1** for exercise simplicity, meaning edits update how **historical** rows group. If a store switches regions and reports must preserve the region **at sale time**, make `dim_store` Type 2 or snapshot region on the fact per contract.

~~~sql
CREATE TABLE mart.dim_channel (
    tenant_id BIGINT NOT NULL,
    channel_key BIGINT GENERATED ALWAYS AS IDENTITY,
    channel_code TEXT NOT NULL,
    channel_name TEXT NOT NULL,

    CONSTRAINT pk_dim_channel
        PRIMARY KEY (tenant_id, channel_key),
    CONSTRAINT uq_dim_channel_code
        UNIQUE (tenant_id, channel_code)
);

CREATE TABLE mart.dim_store (
    tenant_id BIGINT NOT NULL,
    store_key BIGINT GENERATED ALWAYS AS IDENTITY,
    store_code TEXT NOT NULL,
    store_name TEXT NOT NULL,
    region_code TEXT NOT NULL,

    CONSTRAINT pk_dim_store
        PRIMARY KEY (tenant_id, store_key),
    CONSTRAINT uq_dim_store_code
        UNIQUE (tenant_id, store_code)
);
~~~

**Important distinctions:**

- **`channel_code = 'STORE'`** does not replace **`store_code`**. One channel spans many stores.
- **`WEB`/`APP`** orders may lack `store_key` if online orders are not assigned to physical stores.
- **`STORE`** orders must carry a valid `store_code` in staging per source rules; a nullable FK on the fact cannot enforce “store required when channel is STORE,” so the validator must check it.
- **`region_code`** is Type 1 here; moving a store from North to South restates regional history. Decide before using it in historical regional KPIs.

## 9. DDL Part 5 — Confirmed sales line fact

### 9.1. Defining the fact before writing SQL

| Component | Name | Meaning |
| --- | --- | --- |
| Surrogate row key | `sales_line_key` | Technical ID of fact row |
| Degenerate business ID | `source_order_id`, `source_line_no` | Source line identity |
| Time dimension | `confirmed_date_key` | Vietnam business date |
| Product dimension | `product_key` | SCD2 version at `confirmed_at` |
| Buyer dimension | `buyer_key` | SCD2 version or NULL for GUEST |
| Channel dimension | `channel_key` | Channel at confirmation |
| Store dimension | `store_key` | Store if applicable |
| Event time | `confirmed_at` | Source timestamp with full precision |
| Monetary unit | `currency_code` | Line currency; never sum mixed currencies |
| Additive measure | `quantity` | Unit count (all items in pieces here) |
| Transactional measures | `unit_price_amount`, `allocated_discount_amount` | Price and discount at confirmation |
| Derived measures | `gross_sales_amount`, `net_sales_amount` | Derived from quantity, price, discount |
| Lineage | `source_event_id`, `source_event_version`, `loaded_at` | Idempotency, reconciliation, replay |

### 9.2. Fact DDL with foreign keys and invariants

~~~sql
CREATE TABLE mart.fact_sales_line_confirmed (
    tenant_id BIGINT NOT NULL,
    sales_line_key BIGINT GENERATED ALWAYS AS IDENTITY,

    source_order_id UUID NOT NULL,
    source_line_no INTEGER NOT NULL,
    source_event_id UUID NOT NULL,
    source_event_version BIGINT NOT NULL,

    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmed_date_key INTEGER NOT NULL,
    product_key BIGINT NOT NULL,
    buyer_key BIGINT,
    buyer_kind_code TEXT NOT NULL,
    channel_key BIGINT NOT NULL,
    store_key BIGINT,

    currency_code CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_amount NUMERIC(18, 2) NOT NULL,
    allocated_discount_amount NUMERIC(18, 2) NOT NULL,

    gross_sales_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_amount
        ) STORED,
    net_sales_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (
            quantity * unit_price_amount
            - allocated_discount_amount
        ) STORED,

    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_fact_sales_line_confirmed
        PRIMARY KEY (tenant_id, sales_line_key),
    CONSTRAINT uq_fact_sales_source_line
        UNIQUE (tenant_id, source_order_id, source_line_no),

    CONSTRAINT fk_fact_sales_date
        FOREIGN KEY (confirmed_date_key)
        REFERENCES mart.dim_date(date_key),
    CONSTRAINT fk_fact_sales_product
        FOREIGN KEY (tenant_id, product_key)
        REFERENCES mart.dim_product_scd2(tenant_id, product_key),
    CONSTRAINT fk_fact_sales_buyer
        FOREIGN KEY (tenant_id, buyer_key)
        REFERENCES mart.dim_buyer_scd2(tenant_id, buyer_key),
    CONSTRAINT fk_fact_sales_channel
        FOREIGN KEY (tenant_id, channel_key)
        REFERENCES mart.dim_channel(tenant_id, channel_key),
    CONSTRAINT fk_fact_sales_store
        FOREIGN KEY (tenant_id, store_key)
        REFERENCES mart.dim_store(tenant_id, store_key),

    CONSTRAINT ck_fact_sales_line_no
        CHECK (source_line_no > 0),
    CONSTRAINT ck_fact_sales_version
        CHECK (source_event_version > 0),
    CONSTRAINT ck_fact_sales_quantity
        CHECK (quantity > 0),
    CONSTRAINT ck_fact_sales_price
        CHECK (unit_price_amount >= 0),
    CONSTRAINT ck_fact_sales_discount
        CHECK (
            allocated_discount_amount >= 0
            AND allocated_discount_amount
                <= quantity * unit_price_amount
        ),
    CONSTRAINT ck_fact_sales_buyer_kind
        CHECK (
            (buyer_kind_code = 'GUEST' AND buyer_key IS NULL)
            OR
            (buyer_kind_code = 'REGISTERED' AND buyer_key IS NOT NULL)
        )
);
~~~

**Key observations:**

- The fact has a **technical PK** and **`UNIQUE` business grain** so retries never create two rows for one source line.
- Product/buyer FKs point to **time-resolved version keys**, not current variants or buyers.
- Composite FKs enforce tenant boundaries. Nullable `buyer_key`/`store_key` use standard PostgreSQL nullable FK rules, with `CHECK` ensuring `buyer_key IS NULL` only for `GUEST`.
- Gross/net are **stored generated columns** so they never drift from quantity, price, and discount on the same row.
- **`source_event_version`** guards against stale overwrites. It requires an explicit per-line ordering contract from the source; `eventId` alone does not express version order.
- `currency_code` sits on the fact to prevent adding VND and USD. Production requires validating ISO codes, precision, and per-currency rounding.

This is a **confirmed transaction fact**, not a payment ledger. Never attach a mutable **`current_payment_status`** column onto it that mutates on every capture/refund event.

### 9.3. Workload-driven indexes

~~~sql
CREATE INDEX ix_fact_sales_tenant_date
ON mart.fact_sales_line_confirmed
   (tenant_id, confirmed_date_key);

CREATE INDEX ix_fact_sales_tenant_product_date
ON mart.fact_sales_line_confirmed
   (tenant_id, product_key, confirmed_date_key);

CREATE INDEX ix_fact_sales_tenant_channel_date
ON mart.fact_sales_line_confirmed
   (tenant_id, channel_key, confirmed_date_key);

CREATE INDEX ix_fact_sales_tenant_buyer
ON mart.fact_sales_line_confirmed
   (tenant_id, buyer_key);
~~~

Do not keep unused indexes. Every index increases load/update overhead, storage, and maintenance. Foreign keys on a fact table **do not automatically create optimal query indexes**; pick indexes from predicates, selectivity, and **`EXPLAIN (ANALYZE, BUFFERS)`**.

### 9.4. Should we partition by day or month?

At billions of rows, partitioning by `confirmed_date` or `confirmed_at` aids pruning and retention. Note a key PostgreSQL rule: **unique/primary keys on a partitioned table must include the partition key** to enforce uniqueness natively across partitions. Our PK/UNIQUE above omits date partition keys.

Never tack on `PARTITION BY RANGE` and assume `UNIQUE(tenant_id, source_order_id, line_no)` stays globally enforced. Redesign keys/partitions, maintain a dedup registry, or enforce an invariant pinning an order to one partition—and test late/date-change cases. The core exercise uses a **regular table** to focus on clean grain and constraints.

## 10. Input pipeline and ETL invariants

Proposed flow:

~~~text
Sales source / OrderConfirmed event
                |
                v
  durable inbox / raw landing (event id, version)
                |
                v
      parsed & validated staging
                |
        +-------+-------+
        |               |
        v               v
   dim product       dim buyer
      SCD2              SCD2
        |               |
        +-------+-------+
                |
          resolve as-of
                |
          +-----+-----+
          |           |
          v           v
     valid rows   quarantine + reason
          |
          v
       MERGE/UPSERT fact
          |
          v
 reconcile + publish + monitor
~~~

**Never treat generic CDC `OrderUpdated` events as `OrderConfirmed` without checking authoritative source semantics.** Replayed events can duplicate; one Order with multiple lines shares `eventId`; events can arrive late.

### 10.1. Minimal input contract

A normalized staging row contains:

~~~text
tenant_id
source_order_id, source_line_no
source_event_id, source_event_version
source_variant_id
source_buyer_ref (nullable for GUEST)
buyer_kind_code ('GUEST' or 'REGISTERED')
channel_code
store_code (nullable for online per rules)
confirmed_at
currency_code
quantity
unit_price_amount
allocated_discount_amount
~~~

**Pre-processing checks:**

- Each source line has **`quantity > 0`**.
- Non-negative price, and discount within `[0, quantity × price]`.
- Valid IDs and bounds for `source_order_id`, `source_line_no`, and version.
- Event type is genuinely **`OrderConfirmed`** or an approved revision contract.
- `buyer_kind_code` matches presence/absence of `source_buyer_ref`.
- No anomalous duplicates in the same batch; resolve latest valid version per source first.
- Lines of the same Order share `currency_code`, `confirmed_at`, and `channel` where those are order-level attributes.
- Test/internal orders and currencies follow KPI rules rather than being silently dropped.
- Confirmation timestamps are verified against source clocks/timezones and normalized to `TIMESTAMPTZ`.

### 10.2. Normalized staging table definition

~~~sql
CREATE TABLE mart.stage_confirmed_order_lines (
    tenant_id BIGINT NOT NULL,
    source_order_id UUID NOT NULL,
    source_line_no INTEGER NOT NULL,
    source_event_id UUID NOT NULL,
    source_event_version BIGINT NOT NULL,
    source_variant_id UUID NOT NULL,
    source_buyer_ref UUID,
    buyer_kind_code TEXT NOT NULL,
    channel_code TEXT NOT NULL,
    store_code TEXT,
    confirmed_at TIMESTAMPTZ NOT NULL,
    currency_code CHAR(3) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_amount NUMERIC(18, 2) NOT NULL,
    allocated_discount_amount NUMERIC(18, 2) NOT NULL,

    CONSTRAINT pk_stage_confirmed_line
        PRIMARY KEY (tenant_id, source_order_id, source_line_no),
    CONSTRAINT ck_stage_source_line CHECK (source_line_no > 0),
    CONSTRAINT ck_stage_version CHECK (source_event_version > 0),
    CONSTRAINT ck_stage_quantity CHECK (quantity > 0),
    CONSTRAINT ck_stage_price CHECK (unit_price_amount >= 0),
    CONSTRAINT ck_stage_discount
        CHECK (
            allocated_discount_amount >= 0
            AND allocated_discount_amount
                <= quantity * unit_price_amount
        ),
    CONSTRAINT ck_stage_buyer_presence
        CHECK (
            (buyer_kind_code = 'GUEST'
                AND source_buyer_ref IS NULL)
            OR
            (buyer_kind_code = 'REGISTERED'
                AND source_buyer_ref IS NOT NULL)
        )
);
~~~

**This staging table holds the latest accepted snapshot per line**, not a raw event log. Stale or duplicate events must be filtered at the ingestion inbox using **strictly newer version checks** before entering staging. A blind `INSERT`/`UPDATE` into staging by natural key cannot guard against late stale events without upstream version logic.

If the source lacks stable `source_order_id`s or renumbers lines post-confirmation, fix the grain contract of staging and fact—never “fix” it by calling `ROW_NUMBER()` on a batch and treating it as a permanent line ID.

## 11. Loading sample data for manual verification

Codes **`O-1001`** and **`PHONE-BLACK-128`** in Section 1 are readable scenario labels. In physical DDL, `source_order_id` and `source_variant_id` are `UUID`s. The fixture below uses structured synthetic UUIDs for clarity—**never use these hardcoded UUIDs in production**.

### 11.1. Seeding required dimensions

~~~sql
INSERT INTO mart.dim_channel (
    tenant_id, channel_code, channel_name
)
VALUES
    (17, 'WEB', 'Website'),
    (17, 'STORE', 'Store');

INSERT INTO mart.dim_store (
    tenant_id, store_code, store_name, region_code
)
VALUES
    (17, 'HCM-01', 'HCM 01 Store', 'HCM');

INSERT INTO mart.dim_product_scd2 (
    tenant_id, source_variant_id, sku, product_name,
    category_code, brand_code, valid_from, valid_to, is_current
)
VALUES
    (
        17, '10000000-0000-4000-8000-000000000101'::UUID,
        'PHONE-BLACK-128', 'Smartphone 128 GB',
        'SMARTPHONES', 'BRAND-A',
        '2026-01-01T00:00:00Z'::TIMESTAMPTZ, NULL, TRUE
    ),
    (
        17, '10000000-0000-4000-8000-000000000102'::UUID,
        'CASE-BLACK', 'Black Phone Case',
        'ACCESSORIES', 'BRAND-B',
        '2026-01-01T00:00:00Z'::TIMESTAMPTZ, NULL, TRUE
    );

INSERT INTO mart.dim_buyer_scd2 (
    tenant_id, source_buyer_ref, buyer_segment_code,
    valid_from, valid_to, is_current
)
VALUES (
    17,
    '20000000-0000-4000-8000-000000000201'::UUID,
    'NEW',
    '2026-01-01T00:00:00Z'::TIMESTAMPTZ,
    NULL, TRUE
);
~~~

These `INSERT`s target an **empty study database**; re-running on populated databases requires idempotent dimension loaders and Type 2 management rather than inserting overlapping intervals.

### 11.2. Loading three staging rows

~~~sql
INSERT INTO mart.stage_confirmed_order_lines (
    tenant_id, source_order_id, source_line_no,
    source_event_id, source_event_version,
    source_variant_id, source_buyer_ref, buyer_kind_code,
    channel_code, store_code, confirmed_at,
    currency_code, quantity, unit_price_amount,
    allocated_discount_amount
)
VALUES
    (
        17,
        '00000000-0000-4000-8000-000000001001'::UUID, 1,
        '30000000-0000-4000-8000-000000000301'::UUID, 1,
        '10000000-0000-4000-8000-000000000101'::UUID,
        '20000000-0000-4000-8000-000000000201'::UUID,
        'REGISTERED', 'WEB', NULL,
        '2026-11-22T03:00:00Z'::TIMESTAMPTZ,
        'VND', 2, 150000.00, 20000.00
    ),
    (
        17,
        '00000000-0000-4000-8000-000000001001'::UUID, 2,
        '30000000-0000-4000-8000-000000000301'::UUID, 1,
        '10000000-0000-4000-8000-000000000102'::UUID,
        '20000000-0000-4000-8000-000000000201'::UUID,
        'REGISTERED', 'WEB', NULL,
        '2026-11-22T03:00:00Z'::TIMESTAMPTZ,
        'VND', 1, 50000.00, 5000.00
    ),
    (
        17,
        '00000000-0000-4000-8000-000000001002'::UUID, 1,
        '30000000-0000-4000-8000-000000000302'::UUID, 1,
        '10000000-0000-4000-8000-000000000101'::UUID,
        NULL, 'GUEST', 'STORE', 'HCM-01',
        '2026-11-23T02:00:00Z'::TIMESTAMPTZ,
        'VND', 1, 150000.00, 0.00
    );
~~~

Quick staging check:

~~~sql
SELECT
    tenant_id,
    COUNT(*) AS line_count,
    COUNT(DISTINCT source_order_id) AS order_count,
    SUM(quantity) AS unit_quantity,
    SUM(quantity * unit_price_amount
        - allocated_discount_amount) AS net_amount,
    currency_code
FROM mart.stage_confirmed_order_lines
GROUP BY tenant_id, currency_code;
~~~

Expected result on sample data:

| tenant_id | line_count | order_count | unit_quantity | net_amount | currency_code |
| ---: | ---: | ---: | ---: | ---: | --- |
| 17 | 3 | 2 | 4 | 475000.00 | VND |

**Never tweak the fact to “force a match” if staging or the source is wrong.** Investigate upstream bugs with proper fix decisions and audits.

## 12. Point-in-time dimension resolution: the critical fact-load predicate

To pick the right `product_key`, never JOIN on **`is_current = TRUE`**. Select the dimension version active at **`confirmed_at`**:

~~~sql
s.confirmed_at >= d.valid_from
AND (
    d.valid_to IS NULL
    OR s.confirmed_at < d.valid_to
)
~~~

This is the **as-of join** predicate. Apply the exact same logic to `dim_buyer_scd2`.

### 12.1. Gate: every row must match the exact required version count

Before loading the fact, check match counts:

~~~sql
WITH match_counts AS (
    SELECT
        s.tenant_id,
        s.source_order_id,
        s.source_line_no,
        s.buyer_kind_code,
        s.channel_code,
        s.store_code,

        (
            SELECT COUNT(*)
            FROM mart.dim_date AS d
            WHERE d.calendar_date =
              (s.confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        ) AS date_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_product_scd2 AS p
            WHERE p.tenant_id = s.tenant_id
              AND p.source_variant_id = s.source_variant_id
              AND s.confirmed_at >= p.valid_from
              AND (p.valid_to IS NULL
                   OR s.confirmed_at < p.valid_to)
        ) AS product_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_buyer_scd2 AS b
            WHERE b.tenant_id = s.tenant_id
              AND b.source_buyer_ref = s.source_buyer_ref
              AND s.confirmed_at >= b.valid_from
              AND (b.valid_to IS NULL
                   OR s.confirmed_at < b.valid_to)
        ) AS buyer_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_channel AS c
            WHERE c.tenant_id = s.tenant_id
              AND c.channel_code = s.channel_code
        ) AS channel_matches,

        (
            SELECT COUNT(*)
            FROM mart.dim_store AS st
            WHERE st.tenant_id = s.tenant_id
              AND st.store_code = s.store_code
        ) AS store_matches

    FROM mart.stage_confirmed_order_lines AS s
)
SELECT *
FROM match_counts
WHERE date_matches <> 1
   OR product_matches <> 1
   OR channel_matches <> 1
   OR (
       buyer_kind_code = 'REGISTERED' AND buyer_matches <> 1
   )
   OR (
       buyer_kind_code = 'GUEST' AND buyer_matches <> 0
   )
   OR (
       store_code IS NOT NULL AND store_matches <> 1
   )
   OR (
       channel_code = 'STORE' AND store_code IS NULL
   );
~~~

**Expected result: zero rows** when dimensions are loaded cleanly and sample rules hold.

Failure categories and actions:

| Gate failure | Meaning | Action required |
| --- | --- | --- |
| `date_matches = 0` | Date missing from `dim_date` | Extend calendar; never substitute another date |
| `product_matches = 0` | Late product or missing SCD gap | Load/fix dimension from source and retry |
| `product_matches > 1` | Overlapping Type 2 intervals | Fix dimension; never pick `MIN(product_key)` blindly |
| `buyer_matches = 0` for `REGISTERED` | Buyer dimension missing or bad ID | Quarantine, verify, load dimension |
| `buyer_matches > 1` | Buyer SCD2 overlap | Fix effective intervals |
| `channel_matches = 0` | Undefined channel | Obtain owner/metadata approval or block |
| `store_matches = 0` when `store_code` non-null | Unmapped store | Load `dim_store` or fix source |
| `STORE` channel with `store_code IS NULL` | Missing required store per rules | Hold bad row; never guess a region |
| `GUEST` has buyer mapping | Inconsistent guest flag | Investigate record or rule |

**Never add a `WHERE` filter merely to skip unmatched rows and report the job green.** Gates must block publishing or quarantine failing rows with reason, timestamp, and owner. Only gate-passing rows load into the fact. In production, execute gate and load inside a **consistent snapshot/transaction** so dimensions cannot mutate between both steps.

### 12.2. Late-arriving dimensions differ from true guests

If Sales confirmed an order whose buyer segment hasn't reached the warehouse yet, that is a **late-arriving dimension**. Never change `buyer_kind` from `REGISTERED` to `GUEST` to silence errors. Depending on SLA:

- **Quarantine the fact** until the dimension arrives (used in this exercise).
- Use an **inferred/unknown member** carrying the source reference, flagged unresolved, and repair later per policy.
- Temporarily report an **`UNKNOWN` segment** with alerts if the business accepts lag and guarantees accurate backfill.

The key is preserving **fact grain** and providing a **repair path**, never making sales vanish just because a dimension attribute lagged behind.

## 13. Idempotent fact loading with stale-version protection

Once **all Section 12 gates pass**, load from staging via as-of joins. The SQL below assumes ingestion already selected the latest valid staging row per natural line.

~~~sql
INSERT INTO mart.fact_sales_line_confirmed (
    tenant_id,
    source_order_id, source_line_no,
    source_event_id, source_event_version,
    confirmed_at, confirmed_date_key,
    product_key, buyer_key, buyer_kind_code,
    channel_key, store_key,
    currency_code, quantity,
    unit_price_amount, allocated_discount_amount
)
SELECT
    s.tenant_id,
    s.source_order_id, s.source_line_no,
    s.source_event_id, s.source_event_version,
    s.confirmed_at, d.date_key,
    p.product_key, b.buyer_key, s.buyer_kind_code,
    c.channel_key, st.store_key,
    s.currency_code, s.quantity,
    s.unit_price_amount, s.allocated_discount_amount
FROM mart.stage_confirmed_order_lines AS s
JOIN mart.dim_date AS d
  ON d.calendar_date =
     (s.confirmed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
JOIN mart.dim_product_scd2 AS p
  ON p.tenant_id = s.tenant_id
 AND p.source_variant_id = s.source_variant_id
 AND s.confirmed_at >= p.valid_from
 AND (p.valid_to IS NULL
      OR s.confirmed_at < p.valid_to)
LEFT JOIN mart.dim_buyer_scd2 AS b
  ON b.tenant_id = s.tenant_id
 AND b.source_buyer_ref = s.source_buyer_ref
 AND s.confirmed_at >= b.valid_from
 AND (b.valid_to IS NULL
      OR s.confirmed_at < b.valid_to)
JOIN mart.dim_channel AS c
  ON c.tenant_id = s.tenant_id
 AND c.channel_code = s.channel_code
LEFT JOIN mart.dim_store AS st
  ON st.tenant_id = s.tenant_id
 AND st.store_code = s.store_code
ON CONFLICT (tenant_id, source_order_id, source_line_no)
DO UPDATE SET
    source_event_id = EXCLUDED.source_event_id,
    source_event_version = EXCLUDED.source_event_version,
    confirmed_at = EXCLUDED.confirmed_at,
    confirmed_date_key = EXCLUDED.confirmed_date_key,
    product_key = EXCLUDED.product_key,
    buyer_key = EXCLUDED.buyer_key,
    buyer_kind_code = EXCLUDED.buyer_kind_code,
    channel_key = EXCLUDED.channel_key,
    store_key = EXCLUDED.store_key,
    currency_code = EXCLUDED.currency_code,
    quantity = EXCLUDED.quantity,
    unit_price_amount = EXCLUDED.unit_price_amount,
    allocated_discount_amount = EXCLUDED.allocated_discount_amount,
    loaded_at = CURRENT_TIMESTAMP
WHERE
    mart.fact_sales_line_confirmed.source_event_version
        < EXCLUDED.source_event_version;
~~~

**How this load works:**

- **`INSERT`** writes new rows at the source line grain.
- **`UNIQUE (tenant_id, source_order_id, source_line_no)`** plus `ON CONFLICT` stops retries from creating duplicate rows.
- **`WHERE` strictly newer version** blocks stale events from overwriting newer state.
- If the same version arrives with a different payload, this statement **leaves the row intact**. Data-quality checks must detect **same-version payload collisions** and treat them as source errors, not success.
- **Gross/net compute automatically** via generated columns—never accept raw totals from callers that could drift from quantity/discount.
- If valid post-confirmation edits must adjust facts, define an explicit **correction/version and restatement audit contract** instead of letting arbitrary `OrderUpdated` events rewrite history.
- Unmatched dimension `JOIN`s silently drop rows; **that is why pre-load gates and post-load reconciliation are mandatory**—this SQL does not catch missing dimensions on its own.

In production, wrap **resolve/gate/load/commit** inside a consistent isolation/locking/versioning boundary. If dimensions can mutate mid-load, pin a shared snapshot or retry on changes rather than trusting a gate run far ahead of the insert.

### 13.1. Why not make `eventId` alone the fact's `UNIQUE` key?

One `OrderConfirmed` event can carry **multiple order lines** sharing the same `eventId`. Putting `UNIQUE(source_event_id)` on the line fact rejects the second line of the same order as a duplicate.

**`eventId`** deduplicates messages at the ingestion inbox; **`source_order_id + source_line_no`** identifies the fact grain. Each layer serves a distinct purpose.

### 13.2. Late source events and retroactive SCD Type 2 updates

An `OrderConfirmed` occurred Aug 10 yet arrives in the warehouse in November. **`confirmed_date_key` remains Aug 10**, and product/buyer dimensions must resolve as of **Aug 10**, not November `loaded_at`.

If a Type 2 dimension is retroactively adjusted, affected facts may need their **`product_key`/`buyer_key` re-resolved** for the impacted interval once the dimension version is fixed. Manage that inside an audited restatement workflow; a fact pointing to an existing FK whose interval **no longer covers `confirmed_at`** still corrupts historical reporting.

## 14. Data quality and reconciliation: proving zero drops and zero inflation

### 14.1. Finding staging lines missing from fact or at older versions

~~~sql
SELECT
    s.tenant_id,
    s.source_order_id,
    s.source_line_no,
    s.source_event_version,
    f.source_event_version AS fact_version
FROM mart.stage_confirmed_order_lines AS s
LEFT JOIN mart.fact_sales_line_confirmed AS f
  ON f.tenant_id = s.tenant_id
 AND f.source_order_id = s.source_order_id
 AND f.source_line_no = s.source_line_no
WHERE f.sales_line_key IS NULL
   OR f.source_event_version < s.source_event_version;
~~~

Empty output means **every staged line** sits in the fact at an equal or newer version. It does **not yet prove payloads match**, amounts match, or as-of keys are right.

### 14.2. Finding same-version payload mismatches

~~~sql
SELECT
    s.tenant_id,
    s.source_order_id,
    s.source_line_no,
    s.source_event_version
FROM mart.stage_confirmed_order_lines AS s
JOIN mart.fact_sales_line_confirmed AS f
  ON f.tenant_id = s.tenant_id
 AND f.source_order_id = s.source_order_id
 AND f.source_line_no = s.source_line_no
WHERE f.source_event_version = s.source_event_version
  AND ROW(
      f.confirmed_at, f.currency_code,
      f.quantity, f.unit_price_amount,
      f.allocated_discount_amount
  ) IS DISTINCT FROM ROW(
      s.confirmed_at, s.currency_code,
      s.quantity, s.unit_price_amount,
      s.allocated_discount_amount
  );
~~~

Non-empty output reveals **same version with differing measure payloads**—investigate before publishing. Beyond these fields, production pipelines should also verify **product/buyer/channel/store mappings and `source_event_id`** per contract; matching amounts alone do not prove dimensions matched.

### 14.3. Reconciling staging vs fact totals by currency

~~~sql
WITH expected AS (
    SELECT
        tenant_id,
        currency_code,
        COUNT(*) AS expected_lines,
        SUM(quantity * unit_price_amount
            - allocated_discount_amount) AS expected_net
    FROM mart.stage_confirmed_order_lines
    GROUP BY tenant_id, currency_code
),
actual AS (
    SELECT
        f.tenant_id,
        f.currency_code,
        COUNT(*) AS actual_lines,
        SUM(f.net_sales_amount) AS actual_net
    FROM mart.fact_sales_line_confirmed AS f
    JOIN mart.stage_confirmed_order_lines AS s
      ON s.tenant_id = f.tenant_id
     AND s.source_order_id = f.source_order_id
     AND s.source_line_no = f.source_line_no
    GROUP BY f.tenant_id, f.currency_code
)
SELECT
    COALESCE(e.tenant_id, a.tenant_id) AS tenant_id,
    COALESCE(e.currency_code, a.currency_code) AS currency_code,
    e.expected_lines, a.actual_lines,
    e.expected_net, a.actual_net
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.tenant_id = e.tenant_id
 AND a.currency_code = e.currency_code
WHERE e.expected_lines IS DISTINCT FROM a.actual_lines
   OR e.expected_net IS DISTINCT FROM a.actual_net;
~~~

Expected result on sample data: **zero rows**. If unmapped rows were **silently dropped by `INNER JOIN`** during load, this check catches the missing line counts or sums.

**Limitation:** comparing totals can hide offsetting errors. Combine with **per-line key and payload comparisons**. Also, when the fact table holds historical batches beyond current staging, joining back to staging scopes the check to **the current stage batch**—never compare whole-fact `COUNT(*)` against one batch.

### 14.4. Checking that facts still point to matching dimension intervals

When `dim_product_scd2` is edited retroactively, FKs stay valid while `product_key` may fall outside the interval:

~~~sql
SELECT
    f.tenant_id,
    f.source_order_id,
    f.source_line_no,
    f.confirmed_at,
    f.product_key,
    p.valid_from,
    p.valid_to
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_product_scd2 AS p
  ON p.tenant_id = f.tenant_id
 AND p.product_key = f.product_key
WHERE NOT (
    f.confirmed_at >= p.valid_from
    AND (p.valid_to IS NULL OR f.confirmed_at < p.valid_to)
);
~~~

Expect zero rows. Run the same check on **`buyer_key`** when buyer is `REGISTERED`. Passing a foreign-key check **does not prove the right point-in-time dimension version was chosen**.

### 14.5. Checking order-level consistency across lines

Per this exercise's staging contract, all lines of one order share:

- Same **`confirmed_at`**.
- Same **`currency_code`**.
- Same **`channel_code`**.
- Same **`buyer_kind_code`/`source_buyer_ref`**.
- Same **`source_event_id`** when emitted from one confirmation event.

Example check:

~~~sql
SELECT
    tenant_id,
    source_order_id,
    COUNT(DISTINCT confirmed_at) AS confirmed_at_variants,
    COUNT(DISTINCT currency_code) AS currency_variants,
    COUNT(DISTINCT channel_code) AS channel_variants,
    COUNT(DISTINCT source_event_id) AS event_variants
FROM mart.stage_confirmed_order_lines
GROUP BY tenant_id, source_order_id
HAVING COUNT(DISTINCT confirmed_at) <> 1
    OR COUNT(DISTINCT currency_code) <> 1
    OR COUNT(DISTINCT channel_code) <> 1
    OR COUNT(DISTINCT source_event_id) <> 1;
~~~

If the source allows an Order to receive **line-level update events** across multiple versions, the `source_event_id` check above no longer fits; validate per **confirmation transaction/event group** rather than forcing one rule onto every model.

### 14.6. Minimal acceptance gate suite

| Gate | Meaning | Target |
| --- | --- | --- |
| **`missing_date/product/channel`** | Missing mandatory dimension | 0 |
| **`overlapping SCD versions`** | One event matches multiple versions | 0 |
| **`registered_buyer_unmatched`** | Identified buyer lacks dimension | 0 or handled per controlled policy |
| **`duplicate_source_line`** | Duplicate business grain | 0 |
| **`stale_event_overwrite`** | Fact overwritten by older version | 0 |
| **`same_version_mismatch`** | Same version, differing payload | 0 |
| **`source_vs_fact_line_diff`** | Line count mismatch in batch scope | 0 |
| **`source_vs_fact_net_diff`** | Monetary mismatch per currency | 0 within approved precision |
| **`fact_wrong_scd_interval`** | Valid FK row, wrong effective interval | 0 |
| **`unauthorized_dimension_read`** | Cross-tenant or unauthorized read | 0 |
| **`freshness_lag`** | Fact update latency | Within business SLO |

A **green job status** is not enough. Record **gate evidence** pre-publish and monitor post-publish, especially around late events and dimension edits.

## 15. Writing reports: querying at the right grain and units

### 15.1. KPIs by date, category, and channel

~~~sql
SELECT
    d.calendar_date AS confirmed_business_date,
    p.category_code,
    c.channel_code,
    f.currency_code,

    COUNT(*) AS confirmed_line_count,
    SUM(f.quantity) AS confirmed_unit_quantity,
    SUM(f.gross_sales_amount) AS confirmed_gross_amount,
    SUM(f.allocated_discount_amount) AS discount_amount,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount,

    COUNT(DISTINCT (f.tenant_id, f.source_order_id))
        AS distinct_confirmed_order_count
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_date AS d
  ON d.date_key = f.confirmed_date_key
JOIN mart.dim_product_scd2 AS p
  ON p.tenant_id = f.tenant_id
 AND p.product_key = f.product_key
JOIN mart.dim_channel AS c
  ON c.tenant_id = f.tenant_id
 AND c.channel_key = f.channel_key
WHERE f.tenant_id = $1
  AND d.calendar_date >= $2::DATE
  AND d.calendar_date <  $3::DATE
GROUP BY
    d.calendar_date,
    p.category_code,
    c.channel_code,
    f.currency_code
ORDER BY confirmed_business_date, p.category_code, c.channel_code;
~~~

**How to read this:**

- Fact has **one row per line**, so `COUNT(*)` counts lines.
- `SUM(quantity)` is valid because all lines use piece units per exercise contract; never add kg and pieces if supporting mixed units.
- Monetary sums group by **`currency_code`**; never add VND and USD.
- **`COUNT(DISTINCT (tenant_id, source_order_id))`** counts distinct orders **within each group**.
- An Order buying both a phone and a case appears in **two categories**, so **summing `distinct_order_count` across categories counts that order twice**. To get platform-wide distinct orders, re-compute `DISTINCT` over the fact at global scope.
- `p.category_code` comes from **the dimension version attached at confirmation time**, not the variant's current category.

### 15.2. Daily summary report without product dimension

If users ask **“total orders on Nov 22”**, avoid summing rows from the category breakdown:

~~~sql
SELECT
    d.calendar_date,
    f.currency_code,
    COUNT(*) AS confirmed_line_count,
    COUNT(DISTINCT (f.tenant_id, f.source_order_id))
        AS distinct_confirmed_order_count,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_date AS d
  ON d.date_key = f.confirmed_date_key
WHERE f.tenant_id = $1
GROUP BY d.calendar_date, f.currency_code
ORDER BY d.calendar_date;
~~~

Expected output on sample data:

| Date | Currency | Lines | Distinct orders | Net items |
| --- | --- | ---: | ---: | ---: |
| 2026-11-22 | VND | 2 | 1 | 325,000 |
| 2026-11-23 | VND | 1 | 1 | 150,000 |

Combined total across both days: **3 lines, 2 orders, and 475,000 VND**. If one order could have lines confirmed on different dates—outside this exercise's contract—clarify which event defines confirmation and fact grain before running this query.

### 15.3. KPIs by historical buyer segment

~~~sql
SELECT
    COALESCE(b.buyer_segment_code, 'GUEST')
        AS segment_at_confirmation,
    f.currency_code,
    COUNT(DISTINCT (f.tenant_id, f.source_order_id))
        AS distinct_order_count,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount
FROM mart.fact_sales_line_confirmed AS f
LEFT JOIN mart.dim_buyer_scd2 AS b
  ON b.tenant_id = f.tenant_id
 AND b.buyer_key = f.buyer_key
WHERE f.tenant_id = $1
GROUP BY COALESCE(b.buyer_segment_code, 'GUEST'), f.currency_code;
~~~

**Never JOIN on `source_buyer_ref` to `is_current = TRUE`** when the metric means segment at confirmation. That relabels past orders with today's VIP/NEW status and distorts historical cohorts.

Here, **`GUEST`** is guaranteed by `buyer_kind_code`; the `COALESCE` works because `CHECK` blocks `REGISTERED` with `buyer_key IS NULL`. If `UNKNOWN` or `PENDING` states are added later, give them **their own label** rather than lumping them into `GUEST`.

### 15.4. KPIs by store and region

~~~sql
SELECT
    COALESCE(st.region_code, 'ONLINE_NO_STORE') AS store_region,
    c.channel_code,
    f.currency_code,
    SUM(f.net_sales_amount) AS confirmed_net_items_amount
FROM mart.fact_sales_line_confirmed AS f
JOIN mart.dim_channel AS c
  ON c.tenant_id = f.tenant_id
 AND c.channel_key = f.channel_key
LEFT JOIN mart.dim_store AS st
  ON st.tenant_id = f.tenant_id
 AND st.store_key = f.store_key
WHERE f.tenant_id = $1
GROUP BY
    COALESCE(st.region_code, 'ONLINE_NO_STORE'),
    c.channel_code,
    f.currency_code;
~~~

This exercise uses **Type 1 `dim_store`**. When a store switches regions, historical regional reports **restate under the new region**. If the real requirement is region at sale time, convert `dim_store` to Type 2 and resolve as-of like products.

### 15.5. Averages and non-additive measures

- **Average line net amount** = `SUM(net_sales_amount) / COUNT(line rows)`.
- **Average order value (items)** = `SUM(net_sales_amount) / COUNT(DISTINCT order)` **computed over the full target scope**.
- **Average unit price** = `SUM(gross_sales_amount) / SUM(quantity)`, never an unweighted `AVG(unit_price)` when quantities vary.
- **Distinct order count** is non-additive across categories/channels when one Order spans multiple groups.
- **Distinct buyer count** is non-additive across dates. Surrogate `buyer_key` in SCD2 is also not “distinct natural buyers”; use controlled `source_buyer_ref` where authorized and needed.

When grouping by currency, never divide `VND + USD` by a shared order count and call it monetary average order value. Use explicit FX sources, timestamps, and conversion rules, or report each currency separately.

## 16. Classic mistakes when building a sales star schema

| Mistake | Wrong outcome | Fix |
| --- | --- | --- |
| Order-grain fact grouped by SKU | Cannot allocate totals cleanly | Use line grain, or an allocation bridge |
| Calling `COUNT(*)` `order_count` | Counts lines as orders | `COUNT DISTINCT` order ID in target scope |
| Joining fact to SCD2 on natural ID | One fact matches multiple versions, inflating totals | Join on surrogate `product_key` |
| Filtering `is_current` on historical reports | Past category/segment replaced by today's | Resolve as-of during fact load |
| Choosing dim version from `loaded_at` | Late events land in wrong month/cohort | Use authoritative `confirmed_at` |
| `INNER JOIN` drops missing dimensions silently | Sales quietly disappear | Data-quality gates, quarantine, reconciliation |
| `GUEST` and unmatched `REGISTERED` both NULL | Blurs business guest with sync lag | Explicit `buyer_kind` or status-tagged unknown member |
| Summing mixed currencies | Meaningless monetary sum | Group by currency or convert with FX contract |
| Summing header order total after joining lines | Multiplies order total by line count | Sum line measures or pre-aggregate to order |
| Summing distinct order counts across categories | Multi-category orders counted repeatedly | Recompute distinct at overall scope |
| Joining payment captures directly to sales lines | 1:N captures multiply lines | Separate payment fact; pre-aggregate before joining |
| `DELETE`ing confirmed facts on cancellation | Erases what actually happened | Dedicated cancellation/adjustment event fact |
| Copying names/emails into broad dimensions | Leaks PII to analytics consumers | Pseudonymize, minimize, and enforce ACLs |
| Overlapping SCD2 intervals | One event matches multiple `product_key`s | Enforce interval bounds and overlap audits |
| `UNIQUE` on `eventId` alone | Drops line 2 of the same `OrderConfirmed` | `UNIQUE` on natural line grain |
| Upserting without checking version | Old event overwrites newer state | Monotonic version guard + audit |

## 17. Extending the model: refunds, cancellations, promotions, and FX

A durable star schema explicitly documents **what the current fact cannot answer**. Our confirmed-line fact is a **transaction fact for locked merchandise value**. It does not answer **actual cash captured, refunds, accounting revenue, per-promotion discounts, or stock balances**.

### 17.1. Payment capture facts have a different grain

An order may:

- Capture 50% at placement.
- Capture the remaining 50% at delivery.
- Have a failed capture attempt followed by a retry.
- Have a partial refund after capture.

**`fact_payment_capture`** should take the grain **one confirmed capture transaction** from Payments, e.g.:

~~~text
fact_payment_capture:
  tenant_id
  source_capture_id           -- unique within provider/source scope
  source_order_id             -- degenerate reference
  captured_date_key
  payment_method_key          -- if needed and authorized
  captured_at
  captured_amount
  currency_code
  source_event_id, source_event_version
~~~

**Never JOIN raw captures directly to `OrderLine`s** and sum both `captured_amount` and `line_net_amount`: an Order with two lines and two captures produces four rows and doubles both sides. To compare “confirmed” vs “captured,” **aggregate each fact to one row per Order/currency first**, then JOIN:

~~~text
confirmed_by_order:
  (tenant_id, source_order_id, currency_code)
  SUM(net_sales_amount)

captured_by_order:
  (tenant_id, source_order_id, currency_code)
  SUM(captured_amount)

JOIN at grain (tenant_id, source_order_id, currency_code)
after each side aggregates cleanly.
~~~

Order and capture currencies may differ in cross-border payments; if so, you cannot simply join on matching currency and call the gap unpaid. Define FX/settlement contracts and adjustment rules.

### 17.2. Line-allocated refund facts

To report **refunded merchandise by product**, an order-level Refund must be validly allocated down to lines or sourced from return line workflows. Never evenly split refunds across SKUs without an approved rule.

An extension fact could look like:

~~~sql
CREATE TABLE mart.fact_refund_line (
    tenant_id BIGINT NOT NULL,
    source_refund_line_id UUID NOT NULL,
    source_refund_id UUID NOT NULL,
    source_order_id UUID NOT NULL,
    source_line_no INTEGER NOT NULL,
    refund_date_key INTEGER NOT NULL,
    refunded_at TIMESTAMPTZ NOT NULL,
    currency_code CHAR(3) NOT NULL,
    refunded_quantity INTEGER,
    refunded_amount NUMERIC(18, 2) NOT NULL,

    CONSTRAINT pk_fact_refund_line
        PRIMARY KEY (tenant_id, source_refund_line_id),
    CONSTRAINT fk_fact_refund_date
        FOREIGN KEY (refund_date_key)
        REFERENCES mart.dim_date(date_key),
    CONSTRAINT ck_refund_amount_nonnegative
        CHECK (refunded_amount >= 0),
    CONSTRAINT ck_refund_quantity_positive
        CHECK (refunded_quantity IS NULL OR refunded_quantity > 0)
);
~~~

This illustrates **one refund line grain** with tenant-unique `source_refund_line_id`. It omits an FK to the sales fact because our sales fact uses a technical PK alongside a `UNIQUE` natural grain; you can reference **`(tenant_id, source_order_id, source_line_no)`** if refunds always map to a warehouse-retained order line.

**Refunds can use a different currency or include fees unrelated to merchandise**, so “confirmed sales − refunds” holds only when sources, conversions, and deduction rules are aligned. If a refund cannot be attributed to an `OrderLine`, never pick a `product_key` arbitrarily just to plug a gap.

### 17.3. Cancellations are events, not deleting history

When a confirmed order is later cancelled:

- **`fact_sales_line_confirmed`** preserves the fact **it was confirmed**.
- Add **`fact_order_cancellation`** at cancellation-event grain, or line-level adjustment rows if KPIs require net adjustments.
- **`net confirmed after cancellations`** requires explicit rules: full vs partial cancellation, deduction by confirmation date vs cancellation date, and product allocation.
- Never `DELETE` confirmed rows while keeping the same KPI name with shifting historical meaning.

If the business opts for a mutable **accumulating snapshot** fact instead of immutable event facts, publish distinct definitions and restatement rules—never mix both patterns in one table silently.

### 17.4. Promotions create many-to-many fanout risk

One order line can qualify for two promotions. Bridge table:

~~~text
bridge_order_line_promotion:
  tenant_id
  source_order_id
  source_line_no
  promotion_key
  allocated_promotion_discount_amount
~~~

To report discounts by promotion, **`allocated_promotion_discount_amount`** must have an allocation contract reconciling to `line_discount`. Never JOIN `fact_sales_line_confirmed` to the bridge and sum full **`net_sales_amount`** per promotion, then sum across promotions as if lines weren't duplicated.

If users merely ask “which orders used promotion X?”, use **`EXISTS`** or a flag. If attributing revenue across promotions, define weighted allocation rules explicitly rather than summing an M:N join.

### 17.5. Multi-currency and conversion

Facts store **`currency_code`** and **original transaction-currency amounts at confirmation**. To report in a unified reporting currency:

- Specify **`fx_rate_source`**, effective timestamp, and rate type.
- Distinguish confirmation, capture, settlement, and refund dates.
- Record the **applied rate** per contract rather than retroactively applying today's rate to past orders.
- Store/reconcile **original amount, original currency, rate, converted amount, and rounding rules** if auditable.
- Never add VND, USD, and EUR before converting into one well-defined unit.

In the core exercise, **report per native currency** to avoid unconfirmed accounting FX rules.

## 18. Incremental pipelines: handling changes and late arrivals

Real pipelines can never assume **all sources and dimensions arrive in order**.

| Scenario | Controlled handling |
| --- | --- |
| Duplicate `OrderConfirmed` event | Inbox dedup by `eventId`; fact `UNIQUE` on natural line grain |
| Older version arrives late | Compare source version; block stale overwrites |
| Event arrives days late | Use **`confirmed_at`** as event time and for as-of dimension lookup |
| Product/buyer dimension arrives late | Quarantine or status-tagged inferred member; reconcile |
| Retroactive SCD2 fix | Repair intervals, identify facts needing restatement, log audit |
| Unknown dimension code | Block publish or route to owner mapping; never guess nearest value |
| Anonymous guest | `buyer_kind = GUEST` and `buyer_key IS NULL` per contract |
| Store missing from dim | Reconcile source `store_code`; never coerce to `ONLINE` |
| Source emits correction | Accept authorized event type, version, scope, and log edit |
| Mid-load disconnect | Idempotent transactional retries, checkpoints, observability |
| Buyer erasure/restriction | Propagate privacy workflow across mappings, projections, caches, backups |
| Rebuild a historical month | Replay from sources + versioned metadata; reconcile before/after |

### 18.1. Distinguishing watermarks

- **`event_time` watermark**: up to which business timestamp events are processed.
- **`ingestion` watermark**: position read in source/stream.
- **`dimension freshness` watermark**: up to which source version dimensions have converged.
- **`publication` watermark**: up to which period data passed all gates and published.

Checking only **`MAX(confirmed_at)`** in the fact can mislead if a very recent event arrives ahead of older delayed ones. Monitor **gaps, lag, checkpoints, and late arrivals**, not just maximum timestamps.

### 18.2. Rebuilds must respect permissions and historical timestamps

When rebuilding August facts in November:

1. Read August **`OrderConfirmed`** events and valid corrections by source version.
2. Resolve product/buyer dimensions as of **August effective time**, not November current labels.
3. Enforce PII, erasure/restriction, and consent policies active at rebuild time.
4. Never resurrect revoked identifiers or permissions merely because raw historical events still sit in storage.
5. Reconcile line-by-line and measure totals across currency, store, channel, and category.
6. Republish dashboards with an explicit **restatement** decision and audit record.

**Idempotency is necessary but not sufficient**: a pipeline can rerun without duplicates yet still link historical sales to current categories, silently corrupting past reports.

## 19. Operations, performance, and data protection

### 19.1. Separating source, analytical, and published tables

- **Order OLTP:** authoritative source for confirmations, IDs, lines, and price snapshots.
- **Product/Buyer services:** authoritative sources for dimension attributes and history.
- **Warehouse staging:** normalization and validation; not an independent business source.
- **SCD2 dimensions:** versioned attributes for as-of analytics.
- **Sales line fact:** fixed-grain derived facts with lineage.
- **BI semantic layer:** exposes approved metric definitions, safe groupings, and access rules.
- **Search/report caches:** read copies with freshness SLAs and reconciliation.

Never rename **`confirmed_net_items_amount`** to **`revenue`** merely because executives casually say “revenue.” Every metric needs an **owner, formula, status filter, unit, timestamp, and exclusions**.

### 19.2. Access control and personal data

The fact table needs no names, emails, phones, or delivery addresses. **`source_buyer_ref`** in the dimension still links an individual's purchases, so:

- Grant consumer access strictly by purpose and tenant.
- Serve **aggregated/segment views** for general reporting when individual tracking is unnecessary.
- Restrict exporting **natural IDs, source IDs, and pseudonymous buyer refs** unless justified.
- Guard tiny cohorts where rare SKUs, dates, and small stores could re-identify individuals.
- Propagate deletion/restriction requests across dimensions, projections, and caches after source changes.
- Enforce **object/tenant authorization**, not security-by-obscure-ID.
- Ensure logs, traces, CDC, and exports never accidentally serialize extra PII.

Tenant-scoped composite FKs **do not replace API or database-role authorization**. A user with broad `SELECT` across a multi-tenant fact table can still read unauthorized tenants without proper access boundaries.

### 19.3. Benchmarking by query shape, not index count

Minimal benchmark suite:

1. Net amount by **date × currency** over 30/90/365 days.
2. Queries by **category × channel** with varying selectivity.
3. **`COUNT(DISTINCT order)`** tenant-wide, per group, and across periods.
4. Buyer segment queries using SCD2 history.
5. Batch load of one million rows measuring write amplification and index footprint.
6. As-of resolution across products/buyers with deep version histories.
7. Late-event replay and restatement after retroactive product category edits.
8. Concurrent BI dashboards running during ETL loads.
9. Restricted-role read tests verifying zero cross-tenant leakage.
10. Backup/rebuild timing and post-restore accuracy checks.

Track **`EXPLAIN (ANALYZE, BUFFERS)`**, p95/p99, CPU/I/O, table/index bytes, rejected rows, and freshness lag. If adding partitions, materialized aggregates, or columnar OLAP engines, document **update costs and post-rebuild consistency**.

### 19.4. When to build an aggregate mart?

If dashboards repeatedly query **date × category × channel × currency** over billions of lines, add an aggregate:

~~~text
agg_confirmed_sales_daily:
  tenant_id, confirmed_date_key
  category_code_at_confirmation
  channel_key, currency_code
  confirmed_line_count
  confirmed_unit_quantity
  confirmed_gross_amount
  allocated_discount_amount
  confirmed_net_items_amount
  source_watermark
~~~

**Never `SUM(distinct_order_count)` from the aggregate** when an Order spans multiple categories. If dashboards require arbitrary distinct order counts across rollups, query the base fact, maintain dedicated structures, or use approved conditional distinct sketches with documented error bounds.

Aggregates are **derived data** requiring grain specs, lineage, idempotent recomputation, permissions, and SLOs. Never mistake a fast summary table for the source of truth.

## 20. Technology selection: why does a star schema fit here?

| Model | Best suited for | Risks if queried directly for BI |
| --- | --- | --- |
| **Relational OLTP** | Writing orders/lines, transactions, FKs | Multi-domain JOINs; write-tuned layout; current state masks history |
| **Document Order** | Reading whole orders with `items[]` and snapshots | Flattening must guard line grain; mixed arrays risk fanout |
| **Graph** | Customer–product–order–fraud path traversals | Lacks native additive fact measures; must preserve event IDs |
| **Time-series** | Quantities/stock over time buckets and events | Point-in-time stock snapshots are non-additive across time |
| **Star schema / columnar mart** | Multi-dimensional rollups, Type 2 history, grain-safe KPIs | ETL, dim alignment, late arrivals, maintenance |
| **Search index** | Faceted SKU filtering, product attributes, UX | Stale projections; not authoritative for captures/refunds/locked prices |

A star schema **does not replace OLTP**. It is an **analytical model** built from transaction facts and governed dimensions—runnable on PostgreSQL at moderate scale or columnar warehouses when data volume and concurrency demand it.

Good choices hinge on **access patterns, freshness, aggregation needs, security, and operational cost**, not technology preference.

## 21. Independent exercises

Use Sections 5–13's DDL and fixture as your starting point. For each problem, specify **grain, SQL/DDL, edge cases, expected outputs, and reconciliation checks**. Do not run against production.

### Exercise 1 — Identifying grain and picking measures

An Order has three product lines; one line has quantity 4. Sales asks for “order count, line count, unit count.”

**Task:** write the three exact expressions over `fact_sales_line_confirmed` and explain why `COUNT(*)` cannot answer all three KPIs.

### Exercise 2 — Proving sample dataset totals

Sample data has three fact lines: `2 × 150,000 − 20,000`, `1 × 50,000 − 5,000`, and `1 × 150,000 − 0`.

**Task:** compute gross, discount, net, `line_count`, and `order_count` by currency and state expected values.

### Exercise 3 — SCD2 product switching categories

`V-101` belonged to `ELECTRONICS` before 2026-09-01 and `SMARTPHONES` from 2026-09-01 onward. Order A confirmed Aug 20; Order B confirmed Nov 22.

**Task:** which `product_key` does each fact point to? Why is joining on natural ID to current dimensions wrong?

### Exercise 4 — SCD2 buyer upgrading segments

A buyer upgrades from `NEW` to `VIP` on Oct 1, with one order in August and one in November.

**Task:** design a query counting orders by segment at sale time. Why might `COUNT(DISTINCT buyer_key)` across both months count the same person twice?

### Exercise 5 — Missing buyer dimension

`source_buyer_ref` is present with `buyer_kind = REGISTERED`, yet no `dim_buyer_scd2` row covers `confirmed_at`.

**Task:** may the pipeline switch `buyer_kind` to `GUEST` to proceed? Propose a quarantine or inferred-member flow.

### Exercise 6 — One order spanning two categories

`O-1001` buys a phone and a case in different categories. The category report shows `distinct_order_count = 1` for each category.

**Task:** what is the total order count for the day? Can you sum the two category counts?

### Exercise 7 — Multiple currencies

One tenant has `confirmed_net_items_amount` of 325,000 VND and 50 USD on the same day.

**Task:** design the correct report; if management wants a single combined total in VND, what fields and FX policies are needed?

### Exercise 8 — Duplicate events and stale versions

`(source_order_id, line_no)` already loaded version 3. The broker replays version 2, then redelivers version 3 with the old `eventId`.

**Task:** how many rows exist in the fact and what is the final version? Contrast the roles of `eventId` and natural line keys.

### Exercise 9 — Unallocated order-level refund

Payments reports a 100,000 refund for a two-line order without specifying which product was refunded.

**Task:** should we subtract 50,000 from each line or all 100,000 from line 1? Can a product-level refund report be published?

### Exercise 10 — Store changing regions

Store `HCM-01` moves to a new operational `region_code` in December. November reports must keep the old region.

**Task:** is Type 1 `dim_store` sufficient? Redesign grain/versioning and resolution.

### Exercise 11 — Catching silently dropped rows on load

A staging row's product UUID is absent from `dim_product_scd2`. The `INSERT ... SELECT` uses an `INNER JOIN`.

**Task:** why does the SQL succeed while sales vanish? Name two checks that block publishing.

### Exercise 12 — Detecting a fact linked to the wrong product version

An Aug 20 fact points to a `product_key` whose version starts Sep 1. The FK constraint is satisfied.

**Task:** why did the FK allow this? Write the SQL predicate detecting wrong as-of intervals.

### Exercise 13 — Aggregating daily sales too early

ETL builds `agg_confirmed_sales_daily` on Nov 22, yet several `confirmed_at = Nov 21` events arrive late on Nov 24.

**Task:** which aggregate rows must be updated? Can we rely solely on `MAX(confirmed_at)`?

### Exercise 14 — Dashboard permissions

A summary report only needs sales by date, channel, and category. `dim_buyer` holds `source_buyer_ref` capable of linking purchase history.

**Task:** should the report/API expose `buyer_ref`? How do you verify sensitive info never leaks?

### Exercise 15 — Designing a new fact for parcel deliveries

Users want “on-time delivery rate by carrier,” where one Order can have multiple shipments and each shipment multiple delivery attempts.

**Task:** pick the new fact grain, two relevant dimensions, and distinguish shipment KPIs from order KPIs.

## 22. Solution hints and grading criteria

### Solution 1 — Three KPIs with different grains

- **Line count:** `COUNT(*)` on the fact in scope.
- **Unit count:** `SUM(quantity)` when units are compatible.
- **Order count:** `COUNT(DISTINCT (tenant_id, source_order_id))` in scope.

A line with quantity 4 is still **one line**. Multiple lines of one Order are still **one Order**. Never sum per-category distinct order counts when orders span multiple categories.

### Solution 2 — Sample arithmetic

- Gross = **300,000 + 50,000 + 150,000 = 500,000 VND**.
- Discount = **20,000 + 5,000 + 0 = 25,000 VND**.
- Net = **475,000 VND**.
- Quantity = **2 + 1 + 1 = 4 units**.
- Line count = **3**; distinct order count = **2**.

Exactly three rows post-load; re-running at the same version yields identical results.

### Solution 3 — Product SCD2

The Aug 20 fact selects the **`ELECTRONICS` `product_key`** valid then; the Nov 22 fact selects **`SMARTPHONES` `product_key`**. Joining on natural ID across all versions produces two rows per fact, and filtering `is_current` falsifies historical reports.

### Solution 4 — Buyer SCD2

Join the fact on **`buyer_key`** resolved at `confirmed_at` and group by **`buyer_segment_code`** on that version. Because one person can receive different `buyer_key`s before and after an SCD2 transition, `COUNT(DISTINCT buyer_key)` across time counts **dimension versions**, not necessarily unique people. For true distinct buyers across time, use governed pseudonymous mappings under authorized access.

### Solution 5 — Unmatched registered buyers

Never flip to `GUEST`. Quarantine with reason `buyer_dimension_missing`, wait for `dim_buyer_scd2`, and retry idempotently. An inferred-member flow must mark the row unresolved and repair it later, guarded by rules, quality gates, and privacy controls.

### Solution 6 — Distinct across categories

`O-1001` counts **1** in `SMARTPHONES` and **1** in `ACCESSORIES`, yet the daily total remains **1 Order** for `O-1001`. Never add `1 + 1 = 2` orders. Recompute `DISTINCT` over the fact after dropping the category grouping.

### Solution 7 — Currencies

Keep **`currency_code`** in `GROUP BY`, producing separate VND and USD rows. For a unified VND figure, specify FX source, timestamp, rate type, currency pair, precision, and rounding, plus whether confirmation or payment date governs conversion. Never add `325,000 + 50` directly.

### Solution 8 — Idempotency

The fact retains **one row** per `(tenant, order, line)` at version **3**. The inbox uses `eventId` to deduplicate message deliveries; the fact uses the natural line key so multi-line `OrderConfirmed` events do not collide. Stale versions never overwrite newer ones.

### Solution 9 — Refunds

Never split evenly or assign arbitrarily to line 1. Without reliable line allocation, report **refunds at Order/currency grain** rather than faking product refunds. Build line-level refund facts only from return-line workflows or owner-approved, reconciled allocation rules.

### Solution 10 — Store history

Type 1 `dim_store` fails when sale-time regions must remain intact. Upgrade `dim_store` to **SCD2** with versioned surrogate `store_key`, `valid_from`/`valid_to`, and non-overlapping intervals; resolve **as-of `confirmed_at`** during fact load. Retroactive effective-time edits require audited restatements.

### Solution 11 — Missing dimensions

`INNER JOIN` drops unmatched lines silently while `INSERT` succeeds. Run a pre-load **`product_matches = 1`** gate, post-load staging→fact anti-joins, and per-currency line-count/net reconciliations to catch dropped measures.

### Solution 12 — FKs do not verify as-of intervals

An FK only proves **`product_key` exists**, not that its interval covers `confirmed_at`. Check:

~~~sql
NOT (
    f.confirmed_at >= p.valid_from
    AND (p.valid_to IS NULL OR f.confirmed_at < p.valid_to)
)
~~~

Join on `product_key` and filter by that predicate to detect mismatched versions, then check source timestamps and restatement policy.

### Solution 13 — Late events

Recompute **Nov 21** aggregates when late events arrive on Nov 24. `MAX(confirmed_at)` can be high even while earlier dates miss data. Maintain ingestion checkpoints, late-arrival-aware watermarks, lookback recomputation windows, and per-day reconciliation.

### Solution 14 — Dashboard permissions

Summary dashboards need no `source_buyer_ref`. Expose a view/semantic layer projecting only date, channel, category, currency, and measures; enforce tenant authorization, attribute allowlists, table/source permissions, audits, and small-cell checks. Pseudonymous IDs still pose linkage risks—never treat them as anonymous by default.

### Solution 15 — Delivery fact

Choose **`fact_shipment_delivery`** at one delivered shipment grain (or `fact_delivery_attempt` at one attempt grain if tracking attempt counts). Include **delivery date** and **carrier** dimensions, plus store/region if applicable. Define **numerator, denominator, SLA deadline, terminal statuses, and timezone** for on-time rate. Because one Order can have multiple shipments, **`on_time_shipment_count`** differs from **`on_time_order_count`**; full order on-time usually requires every shipment on time.

## 23. Submission checklist and grading rubric

A complete submission includes:

| Item | Evidence |
| --- | --- |
| **Business definitions** | KPIs, status filters, currencies, timezones, exclusions |
| **Grain** | What one fact row means; accurate natural key |
| **Bus matrix** | Dimensions per fact/process |
| **Star schema** | Fact ↔ date/product/buyer/channel/store diagram |
| **Dimension design** | Natural/surrogate keys, Type 1/Type 2, history, permissions |
| **Fact DDL** | PK, `UNIQUE` source grain, tenant FKs, measure `CHECK`s |
| **ETL** | Stage contract, as-of resolution, version/idempotent load |
| **Data quality** | Missing/duplicate/overlap/mismatch checks, net reconciliation |
| **Reporting** | At least 3 SQL queries using `COUNT DISTINCT` and currency |
| **Late arrivals** | Quarantine/replay/restatement workflow documented |
| **Data protection** | No excess PII, tenant and consumer ACLs |
| **Performance** | Workload-based indexes, `EXPLAIN`, partition trade-offs |
| **Extensibility** | Separates capture/refund/cancellation from confirmed fact |
| **Explainability** | Every KPI traces back to source order lines and versions |

### 23.1. Reference rubric (100 points)

| Area | Points |
| --- | ---: |
| Grain, business processes, and accurate KPIs | 20 |
| Star schema, dimensions, and time-accurate SCD2 | 20 |
| DDL with tenant-scoped PK/FK/UNIQUE/CHECK | 15 |
| ETL, as-of lookups, idempotency, and late arrivals | 15 |
| KPI queries, anti-fanout, and currency handling | 15 |
| Reconciliation, permissions, and operations plan | 15 |
| **Total** | **100** |

**Failing critical errors:** even a seemingly complete model fails if facts multiply on JOINs, source lines silently drop on missing dimensions, historical reports read current dimensions, mixed currencies are summed without contracts, or PII access expands unnecessarily.

### 23.2. Sample data acceptance criteria

Starting from an empty DB and Section 11's three staging rows:

- **Staging rows:** 3.
- **Fact rows post-load:** 3.
- **Distinct orders:** 2.
- **Total quantity:** 4 units.
- **Gross:** 500,000 VND.
- **Discount:** 25,000 VND.
- **Net:** 475,000 VND.
- **2026-11-22:** 2 lines, 1 order, net 325,000 VND.
- **2026-11-23:** 1 line, 1 order, net 150,000 VND.
- **Registered buyer of O-1001:** maps to `NEW` segment version effective then.
- **Guest of O-1002:** `buyer_key IS NULL` intentionally, not a lookup error.
- **Re-running load at same version:** still 3 fact rows with unchanged measures.
- **Gates in Sections 12 & 14:** zero failures on valid sample data.

Note: **these DDL/INSERT snippets target a clean practice environment**, assuming dimensions load ahead of facts for one sample tenant. Never run them raw against production without migrations, role management, lock testing, quotas, and pipeline orchestration.

## 24. Summary

Designing a sales fact table begins with **the questions users need answered**, followed by selecting **business process and grain**. Once a fact sits at **one confirmed order line**, every measure, key, index, metric, and reconciliation check must respect that grain. Reversing the order—picking tables first and naming KPIs afterward—produces bugs even when SQL executes cleanly.

**Dimensions provide the fact's context at event time**, not a current lookup list to join arbitrarily. Product and buyer SCD Type 2 need **versioned surrogate keys** resolved **as-of `confirmed_at`**; historical segments and categories must never drift with current edits.

**Fact loading requires verification:** normalize staging, match exactly one dimension version in time, quarantine or track invalid rows, guard duplicates with natural keys, block stale overwrites via versions, and reconcile measures by currency and grain. A fact missing rows because `INNER JOIN` silently dropped them fails acceptance.

**Every metric carries distinct semantics.** Confirmed order value is not automatically cash collected or accounting revenue; `COUNT(*)` on line facts is not order count, distinct order counts do not add across categories, end-of-day stock snapshots do not sum across days, and mixed currencies must stay separate or convert under explicit contracts.

The final question before publishing any dashboard is: **“For every number on the report, can we point to the source event, grain, dimension version, currency, timestamp, and reconciliation check that produced it?”** When you can prove that with data and repeatable tests, your star schema becomes a **well-defined, evolvable, and trustworthy** analytical model.
