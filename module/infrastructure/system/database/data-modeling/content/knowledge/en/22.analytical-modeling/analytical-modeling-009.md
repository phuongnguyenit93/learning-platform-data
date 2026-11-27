# When to Choose Dimensional Modeling, Data Vault, or a Hybrid Approach

## 1. The Selection Problem: Optimize for Query Consumers or Source History?

Suppose a retail enterprise has three upstream sources: an e-commerce platform managing orders, a CRM managing customers, and a payment gateway confirming captures/refunds. The business team wants to inspect **net revenue by day, product group, and sales channel**. The data governance team needs to know **which field came from which source, how values changed, and whether data can be reprocessed when customer-merge rules change**. Meanwhile, operations needs to ingest a new ERP source without breaking active reports.

Those objectives do not fully align:

- **Dimensional modeling** organizes data into **facts** and **dimensions**, commonly as a **star schema**, so analysts understand it easily and query efficiently. It is the natural fit for the BI serving layer.
- **Data Vault** structures integrated multi-source history into **Hubs** (business identities), **Links** (relationships), and **Satellites** (attributes/history) to preserve source lineage, isolate stable keys from volatile attributes, and support incremental loading.
- **A hybrid model** uses Data Vault or another historical integration layer to retain source history, then publishes **dimensional marts** so end users analyze quickly with consistent metrics.

**There is no universal answer saying "Data Vault beats star schema" or vice versa.** First specify the *read paths*, *history to retain*, *source count and volatility*, *data governance rigor*, and *operational capacity*. Modeling decisions must translate into concrete keys, constraints, units of measure, update mechanics, physical indexing, and verifiable tests.

## 2. Seeing Each Data Layer's Proper Role

An analytical architecture commonly spans multiple layers rather than a single database:

~~~mermaid
flowchart LR
    E["E-commerce"] --> I["Landing / staging / CDC"]
    C["CRM"] --> I
    P["Payment"] --> I
    I --> V["Raw Vault or source history layer"]
    V --> B["Business Vault / conformance rules"]
    B --> M["Dimensional marts: facts + dimensions"]
    M --> BI["Dashboard / SQL / semantic layer"]
~~~

This diagram illustrates **one hybrid option**, not a mandate that every system deploy all layers. With few sources, stable definitions, and straightforward BI needs, you can go directly from staging to dimensional marts without introducing Data Vault.

| Layer | Core Responsibility | What the Data Must Explain |
| --- | --- | --- |
| **Landing/staging** | Receive data, validate format, capture load metadata, CDC, or source snapshots. | Which row/file came from which source, in which batch, and which errors were quarantined. |
| **Raw Vault** (if chosen) | Store business keys, relationships, and attribute history with clear provenance; avoid embedding KPI logic. | Source, load timestamp, change sequence; which source records produced the data. |
| **Business Vault** (if chosen) | Apply governed conformance/merge rules, build point-in-time tables, bridges, or derived values. | Rule version, survivorship rationale, and recomputation steps. |
| **Dimensional mart** | Deliver facts/dimensions aligned with business semantics and query performance. | Grain, measures, analytical dimensions, KPI definitions, and time semantics. |
| **Semantic/BI** | Name measures, enforce access controls, standardize metrics, and display outputs. | Ensures consumers interpret "revenue" and "completed orders" identically. |

**One minimum requirement:** every layer must have a source contract and verification checks. Adding more layers does not magically improve data quality; without ownership, metadata, and reconciliation, extra layers only add latency and cost.

## 3. Dimensional Modeling: Start with the Grain

In dimensional modeling, the single most important decision is typically the **fact grain**: *what event or measured object does one fact row represent?* When grain is vague, `SUM`s and `JOIN`s easily double-count results.

For "sales by product and day", you might select:

> **Each row of `fact_order_line` represents one line item inside an order at the time the order is accepted**, identified by `(tenant_id, order_id, line_id)`.

From this grain, determine the dimensions and measures:

| Component | Example | Design Notes |
| --- | --- | --- |
| **Fact business key** | `tenant_id, order_id, line_id` | Prevents duplicate loads using the authoritative source identifier. |
| **Dimension keys** | `order_date_key`, `customer_sk`, `product_sk`, `channel_sk` | Foreign keys to dimension versions resolved at the business milestone. |
| **Measures** | `quantity`, `gross_minor`, `discount_minor`, `net_minor` | Specify units, sign conventions, additivity rules, and cancellations/refunds. |
| **Degenerate dimension** | `order_id` | Enables order-level drill-through without needing a separate `dim_order`. |
| **Source/technical** | `source_system`, `source_record_id`, `loaded_at` | Supports reconciliation; never turn technical metadata into KPIs. |

**Grain cannot be "a row depending on whatever data arrived".** If one fact mixes order headers, order lines, and refunds, a three-line order with two payment events can yield a Cartesian product on `JOIN`, multiplying revenue.

### Common Fact Types

| Fact Type | Typical Grain | When Suitable |
| --- | --- | --- |
| **Transaction fact** | One accepted order line, one capture/refund transaction. | Records additive occurrences for detailed analysis. |
| **Periodic snapshot fact** | One product at one warehouse **per day**, one account **per month**. | Tracks inventory/balances at regular cutoffs; never confuse balances with cashflow. |
| **Accumulating snapshot fact** | One case/order tracking milestones from open to close. | Measures cycle times across predictable workflow stages. |

The word "snapshot" in periodic/accumulating facts describes **analytical measurement structure**, not event-sourcing aggregate snapshots or database backups.

### Measure Additivity

- **Additive:** `quantity`, transaction amounts in the same currency; safely summed across compatible dimensions.
- **Semi-additive:** end-of-day balances, inventory stock; additive across warehouses at one cutoff, **never** summed across days as if they were flows.
- **Non-additive:** conversion rates, unit prices, averages; compute from summed numerators and denominators, never blindly `SUM` or `AVG` group-level ratios.

For example, `refund_rate = SUM(refunded_minor) / NULLIF(SUM(captured_minor), 0)` per an approved definition; never take `AVG(refund_rate)` across stores of differing sizes.

## 4. Star Schema Example: Orders and Payment Movements

A compact PostgreSQL design illustrating grain, surrogate keys, foreign keys, `CHECK` constraints, and indexes; production models may involve more dimensions and fact types.

~~~sql
CREATE TABLE dim_customer (
    customer_sk       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    customer_bk       VARCHAR(100) NOT NULL,
    customer_segment  VARCHAR(40) NOT NULL,
    valid_from        TIMESTAMPTZ NOT NULL,
    valid_to          TIMESTAMPTZ,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (tenant_id, customer_bk, valid_from)
);

-- Only one open dimension version per business key.
CREATE UNIQUE INDEX ux_dim_customer_current
    ON dim_customer (tenant_id, customer_bk)
    WHERE valid_to IS NULL;

CREATE TABLE dim_product (
    product_sk        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id         UUID NOT NULL,
    product_bk        VARCHAR(100) NOT NULL,
    category_name     VARCHAR(100) NOT NULL,
    UNIQUE (tenant_id, product_bk)
);

CREATE TABLE fact_order_line (
    tenant_id         UUID NOT NULL,
    order_id          VARCHAR(100) NOT NULL,
    line_id           VARCHAR(100) NOT NULL,
    order_date        DATE NOT NULL,
    customer_sk       BIGINT NOT NULL REFERENCES dim_customer(customer_sk),
    product_sk        BIGINT NOT NULL REFERENCES dim_product(product_sk),
    quantity          NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    gross_minor       BIGINT NOT NULL CHECK (gross_minor >= 0),
    discount_minor    BIGINT NOT NULL CHECK (discount_minor >= 0),
    net_minor         BIGINT NOT NULL CHECK (net_minor >= 0),
    currency          CHAR(3) NOT NULL,
    source_system     VARCHAR(60) NOT NULL,
    loaded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id, line_id),
    CHECK (discount_minor <= gross_minor),
    CHECK (net_minor = gross_minor - discount_minor)
);

CREATE INDEX ix_fact_order_line_date_product
    ON fact_order_line (order_date, product_sk);

CREATE TABLE fact_payment_movement (
    tenant_id          UUID NOT NULL,
    payment_movement_id VARCHAR(120) NOT NULL,
    order_id           VARCHAR(100) NOT NULL,
    movement_date      DATE NOT NULL,
    movement_type      VARCHAR(20) NOT NULL
                       CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor       BIGINT NOT NULL CHECK (amount_minor > 0),
    currency           CHAR(3) NOT NULL,
    provider_reference VARCHAR(120) NOT NULL,
    loaded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, payment_movement_id)
);
~~~

Limitations of this example:

1. `dim_customer` implements **Slowly Changing Dimension Type 2 (SCD2)**; `customer_sk` identifies a specific *version*. The partial unique index prevents two open rows, yet **does not block all overlapping historical intervals**: write pipelines or exclusion constraints must add protection where required.
2. `dim_product` here holds current attributes (Type 1 style); if product classifications change and reports must preserve category at sale time, add SCD2 or store historical classification per policy.
3. `fact_order_line` stores sales at order-line grain; exchanges/returns may require a separate adjustment fact or explicit signed event rules. Never silently overwrite historical facts if reports require movement reconciliation.
4. `fact_payment_movement` stores individual **authoritative captures or refunds**, separate from order-line grain. `amount_minor` is positive; `movement_type` determines sign when computing net cashflow.
5. In multi-tenant systems, surrogate keys here are table-wide unique, yet single-column foreign keys do not enforce that fact and dimension share the same `tenant_id`. Verify tenant alignment in ETL, or enforce composite `(tenant_id, *_sk)` FKs when strict isolation is required.
6. Indexes reflect the illustrative workload. On columnar warehouses, partitioning, clustering, or materialized aggregates matter more than OLTP-style B-tree indexes. Benchmark real queries.

### Sales Query by Date and Category

~~~sql
SELECT f.order_date, p.category_name, f.currency,
       SUM(f.quantity) AS units_sold,
       SUM(f.net_minor) AS booked_net_minor
FROM fact_order_line f
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE f.order_date >= DATE '2026-11-01'
  AND f.order_date <  DATE '2026-12-01'
GROUP BY f.order_date, p.category_name, f.currency;
~~~

`booked_net_minor` here is **order-line value net of discounts at booking time**, not recognized accounting revenue and before refunds. Calling it "revenue" requires confirming cancellation, delivery, tax, refund, and recognition policies.

### Cashflow Query: Never Join Two Facts of Different Grains Directly

~~~sql
SELECT movement_date, currency,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE 0 END) AS captured_minor,
       SUM(CASE WHEN movement_type = 'REFUND'
                THEN amount_minor ELSE 0 END) AS refunded_minor,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE -amount_minor END) AS net_cash_minor
FROM fact_payment_movement
GROUP BY movement_date, currency;
~~~

Totals sum strictly within the same currency. Never reuse the same label `net` for both "net cash collected" and "booked order value after discounts"; they measure **two different processes**.

## 5. SCD and Point-in-Time ("As-Of") Analysis

A classic star schema question: was the customer **VIP or STANDARD when placing the order**, or are we grouping by their **current** segment?

Example:

| customer_sk | customer_bk | segment | valid_from | valid_to |
| ---: | --- | --- | --- | --- |
| 101 | CUS-42 | STANDARD | 2026-01-01 | 2026-07-01 |
| 205 | CUS-42 | VIP | 2026-07-01 | Unbounded |

If an order was placed on `2026-05-10`, the fact must reference `customer_sk = 101` for "segment at time of sale". If consumers want all history reclassified under the **current** segment, expose a separate semantic view or explicitly named query rather than silently rewriting fact keys and altering history.

Version lookup:

~~~sql
SELECT customer_sk
FROM dim_customer
WHERE tenant_id = :tenant_id
  AND customer_bk = :customer_bk
  AND valid_from <= :business_time
  AND (valid_to IS NULL OR :business_time < valid_to);
~~~

The half-open interval convention `[valid_from, valid_to)` prevents matching two versions right on a boundary. For retroactive edits, however, distinguish **business effective time** from **when the system learned the value**. Plain SCD2 with a single valid-time axis does not automatically answer every bitemporal question.

### Early-Arriving Facts and Late-Arriving Facts

- **Early-arriving fact / late dimension:** a fact arrives before customer metadata. Use an "unknown" dimension member **scoped per tenant/business key policy**, or an inferred member backfilled later—never lump all unknown customers into one real customer.
- **Late-arriving fact:** an order arrives late carrying an older business date. Resolve `customer_sk` using the approved event timestamp, not the ETL ingestion date.
- **Retroactive correction:** revising a segment effective last month may require updating dimension assignments or restating marts per definition. Preserve lineage and restatement plans.

Apply SCD2 when users **need attribute history**, not blindly on every attribute change. For fixing display-name typos, Type 1 suffices; for segments affecting historical reports, Type 2 is essential.

## 6. Data Vault: Separating Identity, Relationships, and Attribute History

Data Vault structures integrated data around core concepts:

| Component | What Does It Hold? | Example |
| --- | --- | --- |
| **Hub** | Stable business key of a business concept; load/source metadata. | `HUB_CUSTOMER` with `customer_bk`. |
| **Link** | Relationship among Hubs, or an association/transaction identified by rules. | `LINK_ORDER_CUSTOMER` linking order and customer. |
| **Satellite** | Time-varying attributes, plus history and source metadata. | `SAT_CUSTOMER_CRM` storing segment/name per delivery. |
| **Raw Vault** | Hub/Link/Satellite layer mirroring source data, preserving lineage and load history. | Ingest CRM/ERP without coupling directly to all KPI logic. |
| **Business Vault** | Derived elements applying versioned business rules and history-query helpers. | Identity survivorship, PIT, bridges, canonical values. |

**A Hub is not a dimension, a Link is not a BI join table, and a Satellite is not a fact.** These structures support integration and source reconstruction; BI users should rarely have to join dozens of Satellites, compute "latest row", and resolve effective timestamps in every dashboard.

### Example: Identifying Customers Across Multiple Sources

CRM has `customer_id = CUS-42`; the order system has `buyer_id = U-908`. Two codes might refer to the same person, yet **must never be equated automatically** merely because field names look similar. Instead:

1. Keep both business keys in separate source namespaces.
2. Store evidence-backed mapping/cross-reference records in Business Vault or an MDM domain.
3. Once confirmed as one entity, publish `canonical_customer_id` under versioned survivorship rules.
4. Expose conformed dimensions to reporting with clear handling when mappings change or remain unresolved.

Only when a business key is genuinely governed uniformly across sources should they share a single Hub directly. **Business key boundaries and namespaces** must be defined by business rules, not merely by hashing strings.

## 7. Illustrative Physical Data Vault Design in PostgreSQL

This simplified example uses `CHAR(64)` hash keys holding SHA-256 hex strings of **intentionally canonicalized, namespaced** business keys. That is a common Data Vault 2.0 convention, **not a requirement that every Data Vault must use hash keys**; other key strategies work if they preserve stability and integration capability.

~~~sql
CREATE TABLE hub_customer (
    customer_hk    CHAR(64) PRIMARY KEY,
    tenant_id      UUID NOT NULL,
    customer_bk    VARCHAR(120) NOT NULL,
    load_dts       TIMESTAMPTZ NOT NULL,
    record_source  VARCHAR(80) NOT NULL,
    UNIQUE (tenant_id, customer_bk)
);

CREATE TABLE hub_order (
    order_hk       CHAR(64) PRIMARY KEY,
    tenant_id      UUID NOT NULL,
    order_bk       VARCHAR(120) NOT NULL,
    load_dts       TIMESTAMPTZ NOT NULL,
    record_source  VARCHAR(80) NOT NULL,
    UNIQUE (tenant_id, order_bk)
);

CREATE TABLE link_order_customer (
    order_customer_hk CHAR(64) PRIMARY KEY,
    order_hk          CHAR(64) NOT NULL REFERENCES hub_order(order_hk),
    customer_hk       CHAR(64) NOT NULL REFERENCES hub_customer(customer_hk),
    load_dts          TIMESTAMPTZ NOT NULL,
    record_source     VARCHAR(80) NOT NULL,
    UNIQUE (order_hk, customer_hk)
);

CREATE TABLE sat_customer_crm (
    customer_hk     CHAR(64) NOT NULL
                    REFERENCES hub_customer(customer_hk),
    load_dts        TIMESTAMPTZ NOT NULL,
    record_source   VARCHAR(80) NOT NULL,
    hashdiff        CHAR(64) NOT NULL,
    customer_name   TEXT,
    segment         VARCHAR(40),
    source_updated_at TIMESTAMPTZ,
    PRIMARY KEY (customer_hk, load_dts)
);

CREATE INDEX ix_sat_customer_crm_latest
    ON sat_customer_crm (customer_hk, load_dts DESC);
~~~

**Assumptions to document right alongside this DDL:**

- `sat_customer_crm` holds **one CRM attribute version per customer per load timestamp**, using `load_dts` to distinguish versions within the same Hub. If two updates occur within the same microsecond or parallel loads collide on timestamp, add a batch sequence/ID or auxiliary key so history is not lost. `PRIMARY KEY(customer_hk, load_dts)` suffices only under the stated ingest contract.
- This Satellite feeds from **one logical CRM source**. If multiple sources supply `segment` with different semantics or cadences, separate Satellites by source/meaning; never overwrite one source's attributes with another's inside Raw Vault.
- `record_source` tracks where the record originated; `load_dts` is the **load timestamp** per convention. Never assume it equals business occurrence time.
- `source_updated_at`, when present, comes from the upstream system; it may predate `load_dts`, use another timezone, or be unreliable. Verify source contracts and retain ingest metadata.
- A Link states **a relationship was observed**; the Link alone does not state whether the relationship remains active or since when. Relationship state/lifecycle requires a Satellite or event feed with matching rules.
- DDL constraints here do not fully capture deletions/corrections, child-key dependencies, or "an order belongs to at most one customer". Enforce those invariants per business rules and source checks.

### Hash Keys: Not Magic That Solves Master Data

A deterministic hashing convention might look like:

~~~text
customer_hk = SHA256(
    encode_canonical(tenant_id, customer_bk_namespace, customer_bk)
)

order_customer_hk = SHA256(
    encode_canonical(order_hk, customer_hk)
)
~~~

`encode_canonical` must specify exact Unicode handling, whitespace/case normalization **only when business rules allow**, field order, length-prefixing or unambiguous delimiters, charset, and NULL encoding. Two pipelines must run the **exact same convention** to produce identical keys.

If `CUS-42` in two tenants denotes two people, `tenant_id` must belong in the identity space. If an upstream order ID is unique only *within that source*, include source namespace in the BK or use verified cross-reference mappings. Conversely, when a business entity shares a single true enterprise BK across sources, adding `record_source` into the Hub hash creates **two separate Hubs**, defeating integration. Distinguish `business_key_namespace` from `record_source` metadata per business rules.

Good hash algorithms make collisions astronomically rare, yet never replace BK uniqueness checks or source reconciliation. **`hashdiff`** on Satellite attributes is a **change-detection** optimization per canonicalization rules—not a cryptographic signature or legal proof of truth. Inspect raw payloads whenever collisions or canonicalization bugs are suspected.

## 8. Loading Raw Vault: How History and Provenance Are Preserved

A typical Raw Vault pipeline:

1. Ingest data via **batch/CDC/snapshot**, storing source ID, record ID, extraction timestamp, and load batch ID.
2. Validate basic schema, missing/invalid business keys, intra-batch duplicates, and error quarantine rules.
3. Standardize **integration keys** per approved contract without merging two customers prematurely without evidence.
4. Insert into Hubs if the business key is unseen; never update customer names inside a Hub.
5. Insert into Links if the relationship is unseen; verify referenced Hub completeness and namespaces.
6. For Satellites, compute `hashdiff` across contracted attributes; append a new version only when a **meaningful change per load policy** occurs.
7. Store `load_dts`, `record_source`, and audit metadata; never destroy prior history when new states arrive.
8. Reconcile source record counts, business keys, deltas, errors, and delete/adjustment events.

Example CRM feed:

~~~text
Batch 1, 2026-06-01: CUS-42, segment=STANDARD
Batch 2, 2026-07-10: CUS-42, segment=VIP
Batch 3, 2026-07-11: CUS-42, segment=VIP (unchanged)
~~~

With a Satellite inserting on `hashdiff` changes, two versions are recorded at Batch 1 and Batch 2; Batch 3 does not create a duplicate row under change-only rules. **Do not assume the segment took business effect on the exact load date**: those are merely two system observation timestamps unless the source provides an authoritative `effective_from` modeled explicitly.

### CDC Deletes, Late Arrivals, and Replays

- An **upstream DELETE** must not automatically erase Hubs/Links/Satellites in Raw Vault if the architecture commits to preserving history. Model record-tracking/deletion statuses per source contract and retention policy.
- **Late or out-of-order** events/CDC must be ordered by CDC log position/sequence when reconstructing source order, not solely by ingest clock.
- Batch reruns must be **idempotent**: retries must never spawn duplicate Satellite versions. Deduplicate using source + record ID/change position or equivalent, not solely payload `hashdiff`.
- When upstream data is a daily full snapshot, "missing today" can mean deleted, skipped during extraction, pagination drift, or a filter change. Never infer "deleted" without a snapshot-completeness policy.
- Test Hash Key/Hashdiff consistency across pipelines and code releases; inconsistent canonicalization fractures history.

Data Vault's append-only history aids source forensics, yet **does not automatically make data right**: if an upstream system emits a wrong monetary amount, you need an authoritative correction rather than relying solely on "a new version exists".

## 9. Business Vault: Turning Source History into Business Definitions

Raw Vault records **source-observed** facts and links under ingestion rules. Dashboards, however, ask harder questions:

- Do two customer IDs from CRM and e-commerce belong to the same real customer?
- At which milestone are sales recognized: order creation, shipment, capture, or invoicing?
- When CRM and ERP disagree on a name or address, which source takes precedence?
- Do we want what **the system knew on day X** or what **was effectively valid on day X**?

That is where **Business Vault**—governed transformation pipelines or versioned semantic transformations—comes in. Common constructs:

| Derived Construct | Purpose | Risk if Ungoverned |
| --- | --- | --- |
| **Master/canonical customer mapping** | Consolidate identities with evidence and effective dates. | Merging two distinct people or losing provenance. |
| **Business rule satellite** | Store derived attributes per policy/lifecycle rules. | Unclear which formula produced a figure. |
| **PIT (Point-In-Time) table** | Index matching Satellite versions at query cutoffs, avoiding repeated latest-row scans. | Wrong PIT results on late-arriving data or wrong time axis. |
| **Bridge table** | Precompute multi-Link/Hub paths or hierarchies queried frequently. | Relationship multiplication and double-counting if grain blurs. |
| **Reference/standardization** | Map status codes, categories, units, currencies. | Applying today's rules retroactively without versioning. |

Example daily PIT table:

~~~text
pit_customer_daily
(customer_hk, snapshot_date, sat_crm_load_dts, sat_erp_load_dts)
~~~

To answer "what did the warehouse **know** from CRM and ERP at end of day?", use agreed `load_dts`. To answer "which **business-effective** segment did the customer hold on that day?", you need `effective_at`/valid-time from sources or approved logic—possibly bitemporal. A PIT table does not turn ingestion time into business time.

**Business Vault does not have to be a separate physical database.** It is a separation of responsibilities, data layers, and transformation contracts. In smaller architectures, the same goal can be achieved cleanly with versioned SQL/dbt/ELT models without adopting full Data Vault terminology.

## 10. Comparison Table for Requirements-Driven Selection

| Criterion | Direct Dimensional Modeling | Data Vault Integration Layer | Hybrid Vault → Marts |
| --- | --- | --- | --- |
| **Design priority** | BI questions, grain, metrics, intuitive querying. | Business keys, links, source history, lineage. | Preserve source provenance while serving clean BI models. |
| **Data sources** | Few or stable enough to conform directly. | Many sources with independent schemas and churn. | Many sources serving multiple BI/metric teams. |
| **History** | SCD2, time-stamped facts, audit/landing as needed. | Satellite historization, explicit source and load times. | Source history in Vault; reporting history in marts. |
| **Changing report requirements** | Update marts and backfill from staging/history. | Historical foundation exists for reprocessing, still needs read models. | Rebuild new marts from complete history and versioned rules. |
| **Direct SQL/BI users** | Easier; straightforward fact/dimension JOINs. | Harder; many tables and temporal lookups. | Users query marts, not raw Vault. |
| **Storage/ELT cost** | Fewer layers, simpler within small scope. | More tables, metadata, pipelines, and tests. | Extra layer cost, offset by reuse across many marts. |
| **Onboarding source changes** | May require mapping updates and mart backfills. | Isolates attribute churn into Satellites/sources. | New sources load into Vault; published via canonical metrics. |
| **Source auditability** | Achievable with solid staging/audit/lineage. | Usually a primary design goal. | Preserves lineage down to reports when mappings are tracked. |
| **Primary risks** | Wrong grain, SCD mistakes, or losing raw history for restatements. | Overengineering, inconsistent hashing, confusing load time with business time. | Cost, latency, and drift between mart and Vault definitions. |

Data Vault does not automatically guarantee **dashboard query performance**; dimensional modeling does not imply **zero lineage or history**. The difference lies in what serves as the **primary design anchor** and which layer absorbs the cost of change.

## 11. Three Practical Selection Scenarios

### Scenario A — Single Source, Stable Reports: Choose Direct Dimensional Modeling

A retailer runs one sales application with normalized order and product tables and adequate retention. BI needs daily/product sales, inventory, and cancelled order counts. Source count is low, requiring no attribute history beyond SCD2 on customer segments and categories.

**Sound design:** landing/staging with checkpoints and minimal lineage, transforming into `fact_order_line`, `fact_payment_movement`, `dim_customer`, `dim_product`, and required dimensions. Define KPIs in a semantic layer. **You do not need Data Vault just to simplify a JOIN.**

Ensure tests verify grain uniqueness, late data, point-in-time dimension keys, and sufficient source history for rebuilds. If you only snapshot the mutable current orders table nightly, you cannot guarantee reconstructing overwritten intraday transactions.

### Scenario B — Multi-Source Enterprise with High Churn: Consider Data Vault

An enterprise operates multiple ERPs, regional CRMs, independent payment processors, and acquired systems. Business keys collide across sources with different meanings; source schemas evolve frequently; auditors demand "what did source A send on day X?" and the ability to replay entity-resolution rules.

**Sound design:** Raw Vault separating business keys, links, and source history; Business Vault for identity resolution and versioned precedence rules. Then build subject-area marts. Invest in source metadata, monitoring, orchestration, and hashing tests.

The core value is **traceability and re-integration agility**, not assuming Data Vault magically cuts query costs or ends debates over "unique customer".

### Scenario C — Growing Business: Choose a Scoped Hybrid Approach

An e-commerce company originally built star schemas directly from e-commerce data, then added ERP, CRM, and payment gateways; finance demands reconciled history and multiple reports share definitions.

**Sound design:** retain existing marts so BI stays uninterrupted; introduce an integrated historical layer for high-churn/high-audit domains (Order, Customer, Payment), gradually migrating mart inputs. You can apply Data Vault selectively to complex domains while keeping simple reference lookups directly conformed with proper lineage.

Avoid a "Big Bang migration" just so every table becomes a Hub/Link/Satellite. Scope by bounded context, weighing historical value against incremental cost.

## 12. Connecting Data Vault to Star Schemas Without Losing Semantics

In a hybrid model, one Vault entity may feed multiple dimensions and facts, governed by an explicit **transformation contract**.

~~~mermaid
flowchart TD
    RAW["Raw Vault: HUB_ORDER, HUB_CUSTOMER, LINK_ORDER_CUSTOMER, SAT_*"] --> RULES["Business rules: canonical IDs, timestamps, statuses"]
    RULES --> DIM["dim_customer SCD2 + dim_product"]
    RULES --> FACT["fact_order_line"]
    RULES --> CASH["fact_payment_movement"]
    DIM --> KPI["Semantic layer: booked sales, cash flow"]
    FACT --> KPI
    CASH --> KPI
~~~

### Example Transformation Path

1. **Hub Order** establishes order identity, business key, and namespace; **Link Order–Customer** records the observed association.
2. **Satellite Order / Order Line** preserves upstream statuses and attributes; if lines undergo revisions, define which events represent bookings vs. versions/corrections.
3. **Business rules** determine when a line qualifies as a successfully booked order; capture quantity, currency, price, and discount per milestone and acceptance rules.
4. **Conformed Customer Dimension** assigns `customer_sk` using the resolved canonical business key and SCD2 version at the transaction timestamp.
5. **Fact Order Line** holds exactly one row per `(tenant_id, order_id, line_id)` per agreed business definition. If lines mutate repeatedly and reports require every revision, use an event fact or revision history.
6. **Payment Movement Fact** ingests **authoritatively confirmed** capture/refund transactions—never treating `RefundRequested` as settled cash refunded.
7. Every mart row carries minimal lineage metadata or a deterministic trace back to source records, Hubs/Links/Satellites, and rule versions.

### What If a Customer Exists in Two Sources?

Consolidating customers takes more than string-matching `customer_bk`. Maintain a mapping table containing:

~~~text
(source_system, source_customer_bk, canonical_customer_bk,
 valid_from, valid_to, mapping_rule_version, evidence_id)
~~~

A retroactively adjusted mapping can affect numerous historical fact rows. Pick an explicit policy: **preserve historical report attribution** or **restate reports** under the updated mapping with clear version/publish dates.

### Specify Which Timestamp "As-Of" Means

- `event_time` / `business_effective_time`: when the event took business effect.
- `source_updated_at`: when the source system reported modifying the record.
- `load_dts`: when data entered the Vault.
- `mart_loaded_at`: when the analytical mart updated.

When fetching the "latest" Satellite, never default to `MAX(load_dts)` as **business-effective truth** on the sale date. When corrections arrive late, ingest order and business order diverge. Models must distinguish valid time from record time—sometimes requiring bitemporal design.

## 13. Preventing Double-Counting in Both Models

In a star schema, joining two facts of different grains is a classic bug. In Data Vault, joining Hub → multiple Links → multiple Satellite versions likewise multiplies rows.

### Fan-Out Risk Example

An order has two order lines and three CRM segment changes. Fetching all versions of `SAT_CUSTOMER_CRM` and joining directly to two order lines produces **six rows**. `SUM(net_minor)` triples even though the order only has two lines.

Resolution steps:

1. Declare the target grain (one row per order line at sale time).
2. Select **one** matching customer Satellite version per the defined temporal policy.
3. Attach one resolved `customer_sk` to each fact row.
4. Check row counts before and after joins; assert uniqueness at grain.
5. If a relationship is genuinely many-to-many (e.g., multiple reps sharing credit on one sale), use a bridge/allocation rule rather than giving 100% credit to each rep and summing into a grand total.

In Data Vault, PIT and bridge tables eliminate repetitive "pick latest version and join" boilerplate, yet cannot fix **a broken grain or wrong business rule**.

### Simple Verification SQL

~~~sql
-- Each grain key appears at most once in the mart.
SELECT tenant_id, order_id, line_id, COUNT(*) AS n
FROM fact_order_line
GROUP BY tenant_id, order_id, line_id
HAVING COUNT(*) > 1;

-- Compare total value before and after a JOIN at the same grain.
SELECT currency, SUM(net_minor) AS booked_net_minor
FROM fact_order_line
GROUP BY currency;
~~~

The first query must return **0 rows** for a valid grain-compliant fact. The second establishes a baseline total to reconcile after joining dimensions—ensuring joins neither drop nor duplicate rows.

## 14. Source Changes, Backfills, and Reproducibility

Handling ongoing changes and reprocessing matters far more than a static diagram frozen at one point in time.

| Scenario | Direct Dimensional Model Needs | Data Vault / Hybrid Needs |
| --- | --- | --- |
| Source adds optional field | Update staging/transforms; add dimension/measure when meaningful. | Place new attributes in a Satellite or new version; marts change only if needed. |
| Source changes business key | Stable mapping, duplicate checks, backfill keys in dims/facts. | Define namespaces, Hub/Link mappings; never re-hash arbitrarily. |
| Retroactive correction | Re-evaluate affected SCD2/facts and publish restatement. | Retain load history, apply Business Vault precedence rules, rebuild marts. |
| Source stops sending | Missing/late-data policy; never silently treat NULL/0 as truth. | Keep last observed source state, flag freshness and coverage limits. |
| Batch replay | Idempotent upsert by grain and batch/source ID. | Deduplicate business keys, Links, and Satellite deltas per contract. |
| Data erasure request | Purge/mask across facts/dims, staging, exports, caches, backups per policy. | Include Hubs/Links/Satellites, PIT/Bridges, marts, and lineage in erasure scope. |

**Data Vault preserves history it received**, and cannot reconstruct events the upstream source never emitted. If CRM exports only end-of-day snapshots while changing state three times intraday, the warehouse cannot observe those three intermediate states without an event/CDC log. Conversely, a star schema backed by granular CDC/history tables can satisfy many replay needs without Data Vault.

### Safe Mart Rebuild

1. Define the mart v2 contract: grain, dimensions, measures, units, timestamps, and late-arrival rules.
2. Select historical inputs and a **safe high-watermark** based on guaranteed commit/cursor semantics—never treat pre-commit sequence IDs as safe watermarks.
3. Build mart v2 in parallel with production; backfill history and catch up on live increments.
4. Reconcile record counts by grain, monetary totals by currency, missing dimension checks, source totals, and correction/refund edge cases.
5. Cut over read paths/semantic layer cleanly to v2; keep rollback readiness until verified.
6. Document rule versions and cutover dates so users understand why figures restated.

## 15. Cost and Operational Capacity: Gateways Before Choosing

Data Vault shines with many sources and deep history, yet costs go well beyond raw storage:

- **Table and pipeline count:** Hubs/Links/Satellites, PIT/bridges, marts, key checks, monitoring.
- **Compute overhead:** hashing, deduplication, historization, PIT rebuilds, dimension/fact transforms, multi-hop JOINs.
- **Engineering rigor:** governing business keys, source identities, canonicalization, rule versioning, naming standards.
- **Data latency:** extra layers do not deliver real-time SLAs automatically; measure load cadence and per-layer lag.
- **Quality overhead:** reconciling grain, temporal alignment, customer mappings, and missing fields.
- **Security/privacy:** more derived copies expand access surfaces and erasure workflows.

Conversely, direct star schemas grow costly as sources multiply: integration and SCD logic duplicate across marts, and redefining revenue touches numerous pipelines. Compare **total cost of change over your planning horizon**, not week-one table counts.

### Metrics Worth Measuring

| Metric | How to Observe |
| --- | --- |
| Freshness | Elapsed time from source commit/confirmation to mart report readiness. |
| Grain quality | Duplicate fact keys; JOIN fan-out incidents; orphan/unknown dimension rates. |
| Lineage | Share of mart rows traceable back to source records and rule versions. |
| Ingestion & retries | Batch failures/retries, record count drift, unexpected `hashdiff` churn. |
| Backfill capability | Duration, compute cost, and accuracy of rebuilding a historical window. |
| Resource usage | CPU, scanned bytes, storage, index/partition maintenance, pipeline count. |
| User impact | Dashboard p95/p99 query latency and KPI restatement volatility. |

Benchmarks must run on **the same dataset, KPI definitions, and queries**, including late arrivals, retroactive edits, multiple currencies, and business key changes. Measuring `SELECT COUNT(*)` alone proves nothing about a model's value.

## 16. Quality, Privacy, and Data Accountability

A model with great lineage that leaks PII or mis-sums currencies still fails production standards.

### Quality Checks by Layer

**Staging:**
- Valid source/cursor/batch IDs; zero dropped or duplicated records on retry.
- Quarantine schema errors and standardize timestamps/currencies.
- Confirm snapshot completeness before inferring deletions.

**Raw Vault:**
- Hub business keys unique within proper scope; deterministic hashes with reconciliation paths.
- Links reference valid Hubs; never link across sources solely on colliding codes.
- Satellites track genuine changes with complete source metadata and load timestamps.
- CDC/corrections/record-tracking obey historization contracts.

**Marts:**
- Facts obey grain with zero duplicates; dimension keys match event timestamps.
- KPIs compute from authoritative transactions; never mix captures with refund requests.
- Never sum across currencies or sum point-in-time balances over time.
- Lineage from marts back to sources and mapping logic is auditable.

### Privacy and Retention

When a user requests erasure or laws limit retention, having an append-only Raw Vault **does not exempt you from compliance**. Audit every storage tier: landing, Hubs, Satellites, Links, PITs, bridges, dimensions, facts, semantic caches, exports, and backups.

- Minimize copying names, emails, or phone numbers across every layer; use surrogate tokens and controlled linkages where suitable.
- Separate access controls between detailed Raw Vault and published marts; enforce row/column security or physical isolation as required.
- Build verifiable retention/anonymization/erasure workflows covering derived tables and backups per policy.
- Never treat hashed business keys as fully anonymized data; hashes can still be linked or reversed in constrained domains.
- Keep sensitive data out of `record_source`/metadata; `hashdiff` is a technical diff token, not proof of authorization.
- When erasure/anonymization reduces historical rebuild capability, document the scope and remaining rebuild guarantees explicitly.

## 17. Decision Process and ADR Example

A disciplined approach is writing a domain-level **Architecture Decision Record (ADR)** instead of forcing one model across the entire company.

| Question | Required Evidence |
| --- | --- |
| What must dashboards answer, and at what grain? | KPI catalog, sample SQL, drill-down paths, and SLOs. |
| How many sources exist, and what does one business key mean? | Source inventory, sample IDs, identity rules, and mappings. |
| How much history and auditability are needed? | Audit rules, late-data/correction rates, retention windows. |
| How volatile are schemas and relationships? | 6–12 months of historical churn or justified roadmap changes. |
| Must marts rebuild under new definitions? | KPI restatement cases and backfill tests. |
| What is the team's operational capacity? | Tooling, metadata governance, support bandwidth, hashing/SCD skills. |
| Which risks are unacceptable? | PII/tenant leaks, financial reconciliation drift, wrong KPIs, lag, cost. |

**Short ADR example:** "For the first 6 months, one e-commerce platform and one payment provider are the primary sources; dashboards require daily booked sales, gross captures, refunds, and net cash; full transaction history is retained and CDC is available. Choose staging with raw/lineage retention and direct star schemas to minimize overhead. Defer full-domain Raw Vault at this stage. Re-evaluate upon reaching three independent operational systems, colliding business keys, or M&A history integration."

Another ADR might choose: "Multiple independent CRMs/ERPs, shifting customer mappings, and multi-year financial restatement needs. Adopt Raw Vault + Business Vault for Customer/Order/Payment; publish dimensional marts for BI. Accept added operational cost conditional on verified lineage, rule versioning, and load SLOs."

What matters are **re-evaluation triggers** and **verifiable metrics**, not vague promises of "flexibility".

## 18. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Choosing Data Vault just because sources have many tables | Bloats tables/pipelines without serving historical integration needs. | Prove multi-source integration, lineage, and churn value first. |
| Letting BI users query Raw Vault directly | Massive SQL, wrong "latest row", fan-out, and inconsistent KPIs. | Serve contracted marts and a semantic layer. |
| Choosing star schema without defining fact grain | `SUM` multiplies or mixes incompatible transaction units. | Declare grain before drawing FKs; assert uniqueness. |
| Treating `order_status = PAID` as actual cashflow | Misses partial captures/refunds and gateway statuses. | Build a movement fact from settled gateway transactions. |
| Using `load_dts` as business date | Reports break whenever data arrives late. | Separate valid/event time from ingestion time. |
| Inconsistent BK hashing across sources | Falsely merges entities or splits one entity in two. | Standardize namespaces and canonical encoding with tests. |
| Treating `hashdiff` as full quality validation | Garbage data gets dutifully historized. | Enforce validation, lineage, quarantine, and reconciliation. |
| Failing to historize relationships when needed | Old Links misread as currently active relationships. | Use effectivity/record-tracking Satellites with clear policies. |
| Joining facts to multiple Satellite versions | Multiplies rows and inflates revenue. | Use PIT/as-of lookups and grain assertions. |
| Using `current customer segment` across all history | Silently restates past KPIs without notice. | Use SCD2 or explicitly label "current segment" metrics. |
| Failing to keep enough raw history for backfills | New KPIs cannot be reconstructed historically. | Align retention and raw capture with rebuild commitments. |
| Multiple layers with zero clear ownership | Drift among Raw Vault, Business Vault, and marts. | Establish contracts, data owners, monitoring, and tests. |
| Assuming append-only exempts data from deletion | Privacy and regulatory non-compliance. | Implement retention, minimization, erasure, and copy tracking. |

## 19. Practice Exercise: Choosing an Architecture for an Omnichannel Platform

**Context:** An enterprise sells products via website, online marketplaces, and physical stores. Data arrives from e-commerce, POS, CRM, and two payment providers. Customer IDs differ across channels; orders contain multiple lines, some have split payments and partial refunds. CRM may retroactively revise customer segments. Finance needs cashflow reconciliation; marketing wants sales both by segment at time of sale and by current segment.

### Tasks

1. **List sources and business keys:** distinguish `order_id` by channel, CRM/POS `customer_id`, and provider `payment_reference`. Which keys require namespaces, and which can merge with evidence?
2. **Write the grains:** define `fact_order_line`, `fact_payment_movement`, and a periodic inventory snapshot if needed. Identify which measures are additive across days and which are not.
3. **Design dimensional marts:** specify SCD2 `dim_customer`, `dim_product`, `dim_channel`, `dim_date`, surrogate keys, and unique constraints; describe dimension lookups at sale time.
4. **Design a minimal Raw Vault:** select Order/Customer/Product/Payment Hubs, corresponding Links, and per-source Satellites; specify `load_dts`, `record_source`, BK hashing, and `hashdiff`.
5. **Business Vault:** define cross-source customer identity mapping, PIT tables for historical version lookups where needed, and versioned KPI rules.
6. **Compare approaches:** direct star schema, Raw/Business Vault → star, or domain-scoped hybrid. State conditions and costs favoring each option.
7. **Fan-out bug:** an order has 3 lines and a customer has 4 Satellite versions. Prove why joining all versions multiplies data; fix via as-of selection and row-count checks.
8. **Late-arriving data:** a Nov 05 refund loads on Nov 09. Specify reporting date grouping and how published metrics are updated.
9. **Retroactive correction:** August customer segments are corrected in November. Distinguish "what was known in August" vs. restated reporting using new information.
10. **Rebuilds and security:** list affected tables/paths when rebuilding a mart or fulfilling a PII erasure request.
11. **Verification SQL:** write queries to detect duplicate grains, reconcile `CAPTURE - REFUND` by currency, and verify as-of dimension lookups never match two versions.
12. **ADR:** select an architecture backed by evidence, SLOs, owners, re-evaluation triggers, rollback readiness, and committed historical boundaries.

### Self-Evaluation Rubric

| Criterion | Indicator of Success |
| --- | --- |
| **Source of truth** | Clear source→landing→integration→mart map; lineage traces to source. |
| **Grain** | Each fact row has clear meaning and grain uniqueness; JOINs never multiply money. |
| **Keys** | Business keys and surrogate/hash keys serve proper roles; namespaces never collide. |
| **History** | SCD2 and Satellites track changes against explicit time axes. |
| **KPIs** | Booked sales stay distinct from gross captured/net cash; currencies never mix. |
| **Integration** | CDC/late data, deduplication, and corrections have clear policies. |
| **Performance** | SLOs and ELT/BI costs benchmarked against realistic workloads. |
| **Operations** | Rebuilds, verification, privacy, and rollbacks are intentionally engineered. |

**Conclusion:** Dimensional modeling should lead when the primary goal is **analyzing and understanding data at clear grains**; Data Vault deserves serious consideration when the main challenge is **integrating multiple changing sources, preserving history, and tracing lineage**; a hybrid model fits when an organization **needs both** and has the operational maturity to govern the layers. Do not follow trends. Start from business questions, define keys, relationships, time axes, and measures, reconcile with real tests—and select the physical structures and query paths that deliver at reasonable cost.
