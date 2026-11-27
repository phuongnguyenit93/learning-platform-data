# Data Redundancy Without an Authoritative Source or Synchronization Rules

## Learning Objectives

A sales application commonly keeps multiple copies of the same information: product names live in the catalog, search results, sold order lines, and reports; customer names appear in profiles, invoices, and delivery addresses. **Data redundancy is not automatically a bug.** It becomes a bug when copies **are treated as current truth while nobody knows which copy is authoritative**, or when **there are no rules for value changes, late messages, failed updates, and conflicting data**.

For example, product P01 has a list price of 100,000 VND in Catalog, 120,000 VND in Search, and 90,000 VND on a historical order line. All three different numbers can be **valid** if they represent **current price pre-sync, a stale or newer copy, and the accepted price at purchase time**, respectively. Conversely, if both Catalog and Search claim to hold **the current list price** with no authoritative source, that divergence is a consistency bug.

This lesson belongs to the **Common Pitfalls** chapter of **DATABASE_DATA_MODELING**. Aligned with the module's goal, learners practice translating business requirements into data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—comparing relational, document, graph, and analytical data to pick evolvable, verifiable structures. This lesson focuses on **how to detect and fix ungoverned data redundancy**.

After this lesson, you will be able to:

1. Distinguish **intentional duplication** (snapshots, caches, projections, read replicas, materialized aggregates) from **copied data with ambiguous ownership**.
2. Identify **authoritative sources by attribute, scope, time, and state**, rather than declaring a single database "the source of truth for everything."
3. Define a **synchronization contract** covering triggers, identity keys, versions, conflict policies, lag, retries, idempotency, and reconciliation.
4. Explain when **strong consistency inside one transaction** is required vs. when **eventual consistency** is acceptable and how to specify copy staleness bounds.
5. Demonstrate in PostgreSQL **Catalog owning products**, **Search as a read projection**, and **Sales holding transaction snapshots**, paired with an outbox and a version-checking projection consumer.
6. Write queries detecting **stale copies, same-version divergence, missing mappings, and overwritten historical data**.
7. Evaluate common failures such as **non-atomic dual-writes, CDC lacking semantic contracts, duplicate deliveries, out-of-order updates, and arbitrary last-write-wins**.
8. Design a remediation roadmap, test suite, and operational checklist for systems that already have multiple live copies in production.

> **Scope:** SQL examples are educational tools on PostgreSQL, not a full event broker or ETL platform. Deliberately introducing divergence is strictly for test environments. This lesson does not assume every system needs microservices or a separate database per model.

## 1. Spotting the Pitfall From a Concrete Scenario

### 1.1. Three Places Holding Product Prices

Suppose a store maintains three data stores:

| Store | Data Row | Who Uses It? |
| --- | --- | --- |
| **Catalog DB** | P01, list_price = 100,000 VND | Catalog admin portal |
| **Search index** | P01, list_price = 120,000 VND | Product search page |
| **Sales DB** | Order O100, P01, accepted_price = 90,000 VND | Order history and invoices |

Before declaring any price wrong, ask: **do these three prices represent the same fact or three different facts?**

- `Catalog.list_price` may be **the current list price**.
- `Search.list_price` may be **a read copy of the current list price**. If so, it must declare Catalog as its source, have refresh rules, and stay within an allowed lag window.
- `Sales.accepted_price` is **the locked purchase price**. It is a historical fact with its own semantics; **it must never be overwritten with the current Catalog price**.

If the Search team lets admins edit prices straight inside the index while the Catalog team edits prices in the DB, both sides are **competing writers** with no conflict resolution rules. That is the core anti-pattern of this lesson.

### 1.2. Two Opposite Mistakes

**Mistake A — Treating every copy as a source of truth:**

~~~~text
Catalog.updatePrice(P01, 110000)
Search.adminEditPrice(P01, 120000)
Sales.repriceHistoricalOrders(P01, 110000)
~~~~

Consequence: Search and Catalog conflict; historical invoices lose locked prices; nobody knows which store to fix so the system converges.

**Mistake B — Forbidding all redundancy:**

~~~~text
Every search query must call Catalog DB.
Every historical order view must look up current name/price from Catalog.
Every report must JOIN directly across all operational databases.
~~~~

Consequence: tighter coupling, degraded read scalability, destroyed historical snapshots, and broken order semantics. **Normalization protects data dependencies—it is not a mandate to delete copies that serve distinct purposes.**

### 1.3. Warning Signs

A system faces uncontrolled redundancy when:

1. Two systems can **mutate the same current attribute** with no conflict resolution.
2. Multiple tables named customer, product, or order share fields **without a semantic contract**.
3. A "sync" job blindly copies every row on a schedule **without checking which record is newer**.
4. Consumers can reprocess the same event and **add money or inventory twice**.
5. Nobody can answer "how long may a copy lag behind?"
6. Bad data gets "fixed" in a read model, only for **the owner to emit the old value again**.
7. `updated_at` appears everywhere **without defining clocks, timezones, versions, or who may write it**.
8. Historical facts that must remain immutable get **overwritten with current values** by sync jobs.
9. After an outage, operators do not know whether to **backfill, replay, restore, or patch manually**.

**Quick diagnostic:** for every duplicated attribute, ask **what does it mean — who decides it — when is it effective — how do copies refresh — how are discrepancies handled?** If you cannot answer, write the contract first rather than adding another cron job.

## 2. Classifying Redundancy Patterns That Need Different Rules

| Duplication Form | Example | When It Can Be Valid | Primary Risk |
| --- | --- | --- | --- |
| **Business snapshot** | Item name/price at order placement | Preserves agreed transaction terms | Overwritten by current catalog updates |
| **Cache** | Product price in Redis | Read optimization with TTL/invalidation | Serving stale values, cache stampedes |
| **Read projection** | Product in Search index | Search queries tolerating bounded lag | Late events or transform bugs |
| **Read replica** | PostgreSQL replica | Scaling reads with lag monitoring | Reading replicas lagging behind primary |
| **Local denormalization** | `customer_display_name` on order summary | Specific access pattern with clear source/rules | Update anomalies if current name must stay fresh |
| **Materialized aggregate** | Monthly sales by category | Clear grain, refresh/rebuild rules | Double counting, bad watermarks, missed corrections |
| **Warehouse / analytics** | Sales facts, product dimensions | ETL, lineage, explicit history semantics | Late records, SCD errors, unit mismatches |
| **Master data / golden record** | Unified customer from CRM and ERP | Matching, survivorship, and steward rules | False merges, picking unauthoritative values |
| **Two independent writers** | Catalog and Search both edit `list_price` | Only with explicit verified merge protocols | Conflicts, lost updates, non-convergent state |

**Identical byte values do not mean identical facts:** a purchase-price snapshot and a current list price are two distinct business attributes. Conversely, identical column names do not guarantee identical meanings.

### 2.1. Snapshots and Caches Do Not Share Update Rules

When Catalog renames "A5 Notebook" to "Hardcover A5 Notebook":

- **Search projection:** should update per Catalog contract if displaying current catalog titles.
- **Current-price cache:** should invalidate or refresh per cache policy.
- **SalesOrderLine.product_name_at_purchase:** normally **keeps** the name locked at purchase time.
- **Historical reports:** use point-of-sale name or current name depending on the KPI definition.

A blanket job to "UPDATE every copy to match Catalog" refreshes caches while **destroying snapshots**. Before syncing, separate **copies that must converge** from **records that must stay immutable**.

### 2.2. Intentional Denormalization

Suppose an `ORDER_OVERVIEW` table stores:

~~~~text
order_id
buyer_id
buyer_display_name
total_amount
payment_summary_status
shipment_summary_status
last_refreshed_at
~~~~

If `buyer_display_name` is **the current profile name for fast display**, this table is a projection requiring refresh rules. If it is **the buyer's name at purchase time**, it is a snapshot and must not mutate when the profile changes.

The danger is not duplication itself, but **two interpretations of one column** inside the same app. Prevent that with explicit naming: **`buyer_name_at_purchase`** vs. **`current_buyer_display_name`** instead of two uncontracted `name` columns.

## 3. "Source of Truth" Is Scoped, Not a Slogan

### 3.1. System of Record, Authoritative Source, and Reconciliation

Distinguish closely related terms:

- **System of record (SoR):** the system recognized by the organization to maintain a class of business records.
- **Authoritative source / source of truth:** the authority deciding **which value is right within a specific scope and point in time**.
- **Golden record:** a merged view across sources built via identity matching, precedence, verification, and survivorship rules—not an open write target for everyone.
- **Read model / projection:** derived data shaped for queries; may lag behind the source.
- **Snapshot:** facts frozen at a historical event under specific rules; not merely a current copy.

Organizations use varying labels. What is mandatory is **documenting ownership and update rules**, not slapping a "single source of truth" sticker on a database.

### 3.2. Assign Authority Attribute by Attribute

Example ownership matrix:

| Fact | Authoritative Source | Read / Derived Copies | Who May Change It? |
| --- | --- | --- | --- |
| Current product title | Catalog | Search, listing pages, caches | Catalog via publishing workflow |
| Current list price | Catalog/Pricing per authorization contract | Search, caches | Pricing authority |
| Accepted order-line price | SalesOrderLine | Invoices, transaction reports per contract | Approved order adjustment workflows only |
| Available inventory | Inventory | Product pages, caches | Inventory inside reservation/deduction transactions |
| Settled payment amount | Payments/Billing | Order overview, dashboards | Payments/Billing per verified settlement |
| Shipment tracking state | Fulfillment | Tracking UI, customer alerts | Fulfillment per carrier/delivery events |
| Current login email | Identity | Authorized projections | Identity/user via verified flows |
| Confirmed order shipping address | Sales/Fulfillment per business rules | Shipping manifests | Specific address-change workflow |

Here, **Catalog owns current names, Sales owns historical locked prices, and Inventory owns stock**. Never cram all three into one `UNIVERSAL_PRODUCT` entity.

### 3.3. The Time Axis of Truth

For the same `product_id`:

~~~~text
Catalog:
  price_current = 120000 on 2026-11-22

Sales:
  price_at_purchase = 90000 on 2026-10-01

Analytics:
  price_as_of_sale = 100000 per point-of-sale pricing policy
~~~~

These three fields need not be equal. Check:

1. **At what point in time** is current price queried?
2. Is historical price **frozen as a snapshot**?
3. Do `event_time` and `processed_at` differ?
4. Does the report need state **as of sale** or **current**?
5. Are `valid_from/valid_to` or versions needed to reconstruct history?

**Never reconcile semantically different fields by simple equality.** Valid reconciliation matches **semantics, scope, and point in time** first.

### 3.4. Identity Keys and Scope

If SKU `NOTE-A5` is unique only within each tenant, syncing by SKU without tenant merges unrelated products:

~~~~text
tenant A / NOTE-A5 → Product P01
tenant B / NOTE-A5 → Product P99
~~~~

Identity contracts must specify exact business keys such as **`(tenant_id, product_id)`**, or verified globally unique UUIDs with explicit mappings. **Matching ID strings** do not guarantee identical entities; syncing on the wrong key is worse than slightly stale data.

### 3.5. Ownership Spec for Every Copy

Document each copy with at least:

~~~~text
COPY: search_product_projection
Purpose: Search current product names and list prices.
Authority: Catalog product listing state.
Key: (tenant_id, product_id) or globally unique product_id.
Source version: monotonically increasing catalog.version per product.
Refresh: Full-state integration events or snapshot pulls.
Consistency: Eventual; bounded staleness threshold and fallback defined.
Writes: Projection worker only; admins never edit prices directly.
Conflict: Stale/duplicate versions never overwrite newer versions.
Missing/gap: Reconciliation and rebuild procedures exist.
Expiry/deletion: Unpublish/tombstone per retention policy.
Owner: Catalog team for facts, Search team for projection.
~~~~

A nightly "push all prices" cron job **is insufficient** without handling **product deletions, consecutive updates, overlapping job runs, partial failures, and queries running before the job**.

## 4. Synchronization Contracts: Write Them Before Choosing Tech

A **synchronization contract** defines how a copy **is created, updated, freshness-checked, deleted, recovered, and verified**. APIs, CDC, message brokers, and batch jobs only implement parts of that contract.

### 4.1. Ten Questions of a Synchronization Contract

1. **What is the target?** Cache, search projection, historical snapshot, or co-owned entity?
2. **Where is the authoritative source?** Per attribute, tenant/market, and write role?
3. **Which identifiers join source and copy?** Internal PKs, business IDs, tenant IDs, and versions?
4. **When does sync run?** Post-commit event, schedule, on-read, or policy change?
5. **What does the payload carry?** Full state or incremental delta? Schema versioned?
6. **How is ordering handled?** Monotonic aggregate versions, partition ordering, or gap detection?
7. **How are duplicates handled?** Event IDs, request IDs, local inboxes, and transactions?
8. **How are errors and conflicts resolved?** Retries, quarantine, replays, manual review, or explicit merge policies?
9. **How stale may the copy get?** Freshness SLOs, alerts, and stale-read fallbacks?
10. **How are verification and deletion handled?** Value/version reconciliation, tombstones, retention, privacy, and rebuilds?

Without answers to the relevant points, adding a message queue merely **trades** "two out-of-sync tables" for "two systems emitting events nobody trusts."

### 4.2. Comparing Synchronization Mechanisms

| Mechanism | Pros | Key Limitations |
| --- | --- | --- |
| **Read source on demand** | Fewer copies; always hits authority | Depends on source latency/availability; not fit for every query |
| **TTL cache** | Simple for read-heavy, lag-tolerant data | TTL does not guarantee freshness post-update; stale reads |
| **Cache invalidation** | Fast refresh when changed keys are known | Dropped invalidations leave stale prices indefinitely |
| **API polling** | No broker needed; easy snapshot checks | Query load; must manage pagination, watermarks, deletes |
| **Batch ETL/ELT** | Good for large volumes and periodic reporting | Scheduled lag; misses intermediate states between scans |
| **Database log CDC** | Captures committed table changes with minimal app edits | Payloads tied to physical schema; lacks domain intent |
| **Integration events** | Publishes meaningful domain events and states | Must manage schemas, delivery, idempotency, ordering |
| **Transactional outbox** | Commits source state and event intent in one local tx | Still needs relay; at-least-once delivery; not distributed ACID |
| **Read replica** | Scales DB reads cleanly | Does not change ownership; replica lag occurs |
| **Materialized view** | Declarative recomputation inside DB | Refresh policies, freshness, and lock/refresh costs |

No single mechanism wins everywhere. A **current-price cache** and a **historical order line** should never share an "update whenever Catalog reprices" rule, because their business purposes differ fundamentally.

### 4.3. Version Contracts: Full-State vs. Delta

Suppose Catalog changes:

~~~~text
v1: list_price = 100000
v2: list_price = 110000
v3: list_price = 120000
~~~~

If v3 emits **full state**:

~~~~json
{
  "productId": "P01",
  "version": 3,
  "listPrice": "120000.00",
  "currency": "VND"
}
~~~~

the consumer can update directly to 120,000 upon receiving v3 even if v2 was missed—**provided** v3 carries every field needed by the projection and schema/semantics pass validation. Full snapshots let copies converge even across skipped versions.

If v3 emits only a **delta**:

~~~~json
{
  "productId": "P01",
  "version": 3,
  "priceDelta": "10000.00",
  "currency": "VND"
}
~~~~

the consumer **must never add v3's delta onto v1** when v2 is missing, which would yield 110,000 instead of 120,000. It must enforce **contiguous version sequences**, detect gaps, wait/replay, or pull an authoritative snapshot.

**Never call every event "idempotent" merely because it carries a version**: full-state events support conditional versioned upserts; deltas require contiguous exactly-once application or dedicated accumulation/recovery logic.

### 4.4. Ordering and Timestamps

Distinguish clearly:

- **`occurred_at`:** when the event occurred in domain semantics.
- **`committed_at`:** when the source transaction committed (if reliably recorded).
- **`published_at`:** when the relay emitted the event.
- **`received_at`:** when the broker or consumer received it.
- **`applied_at`:** when the copy finished updating.
- **`effective_from`:** when a value takes effect in business rules, which may differ from write time.

A message **received later** is not necessarily a **newer version**. Never use `received_at` as last-writer-wins when messages arrive out of order and an authoritative `source_version` exists.

If the source publishes "new price effective tomorrow," projections may need an **effective schedule** rather than a single latest-price column. Picking the **highest version** does not answer **current effective price** once future-dated prices exist.

### 4.5. Defining Freshness and Exceeded-Threshold Fallbacks

A Search read model may tolerate a few seconds of lag, whereas **checkout price locking** must query Pricing or validate an active quote before creating an order. Never treat a potentially stale Search index as binding authority for settlement.

An explicit contract states:

~~~~text
Search projection freshness:
  Internal target: 99% of Catalog updates converge within 60 seconds
  under defined operating conditions.

When exceeded:
  Alert on consumer lag.
  Display staleness indicator if product is high-risk.
  Never use Search price as final transaction price.

Checkout path:
  Verify quote/price from authoritative source.
  Persist accepted_unit_price as a snapshot at confirmation time.
~~~~

**60 seconds / 99% is purely an illustrative SLO**, not a universal standard. Real SLOs follow business risk, load, and cost. Specify **start/end timestamps**, event scope, clocks, and handling for dropped events.

## 5. Change Lifecycle: Who Writes, Who Emits, Who Projects?

One-way ownership flow:

~~~~mermaid
flowchart LR
    A["Catalog Admin"] -->|"Rename/reprice"| B["Catalog write model"]
    B -->|"Commit state + outbox"| C["Catalog DB"]
    C -->|"Outbox relay"| D["Broker / Event channel"]
    D -->|"Versioned event"| E["Search projection worker"]
    E -->|"Versioned upsert"| F["Search read model"]
    F -->|"Search (may be stale)"| G["Search UI"]
    B -->|"Valid quote"| H["Sales"]
    H -->|"Locked snapshot"| I["Sales order line"]
    I -->|"Reporting events"| J["Analytics read model"]
~~~~

The **sole write path** for current list prices is Catalog. Search never edits prices on its own. Sales **does not** copy list prices as fields expected to stay in sync; Sales keeps **`accepted_unit_price`** per the checkout quote contract.

### 5.1. Who Owns Each Link in the Chain?

| Stage | Owner | Correctness Criteria |
| --- | --- | --- |
| `Catalog.updatePrice` | Catalog/Pricing | Valid price per business rules and authorization |
| Catalog state + outbox | Catalog DB | Commit or roll back atomically together |
| Outbox relay | Integration / Ops | Never loses emission intent; safe under retries |
| Event contract | Catalog + consumers | Keys, versions, currency, semantics published |
| Search consumer | Search | Stale events never overwrite newer state; idempotent |
| Search data | Search | Projection is rebuildable with clear source/version |
| Sales snapshot | Sales | Locked price matches quote; unchanged when Catalog updates |
| Reconciliation | Data owner + Ops | Classifies lag vs. conflict vs. mapping bug |

Using multiple databases **does not automatically reduce risk** if these responsibilities are missing. Conversely, a modular monolith on a single PostgreSQL instance can maintain crisp ownership via modules, APIs, and DB privileges.

### 5.2. When Can a Copy Be Edited Directly?

Normally **admins must never edit the Search projection directly**. If the business needs channel-specific search display overrides separate from Catalog, model a **separately owned attribute**, such as:

~~~~text
Catalog.product_title: canonical product title.
SearchMerchandising.search_display_alias: curated search override label.
SearchProjection.display_title: explicit merge and precedence rule.
~~~~

Then `SearchMerchandising` **does not compete** with `catalog.product_title`; it owns a distinct **alias** concept. Precedence between alias and canonical title is explicit and tested instead of mutating a copy and pretending it updated Catalog.

## 6. PostgreSQL Example: Catalog Source, Search Read Model, and Sales Snapshot

This section presents **an illustrative SQL walkthrough on a clean test database**. For visibility and easy reconciliation, all three contexts live in **one PostgreSQL instance across separate schemas**. In production, they may span separate databases or services; cross-schema SQL joins here are **not a recommendation for services to query each other's internal tables directly**.

### 6.1. Model and Invariants

~~~~mermaid
erDiagram
    CATALOG_PRODUCT ||--o{ CATALOG_OUTBOX : publishes
    CATALOG_PRODUCT ||--o{ SEARCH_PRODUCT_PROJECTION : "logical identity"
    SALES_ORDER ||--|{ SALES_ORDER_LINE : contains

    CATALOG_PRODUCT {
        uuid product_id PK
        string sku UK
        string title
        decimal current_list_price
        bigint version
    }
    CATALOG_OUTBOX {
        uuid event_id PK
        uuid product_id FK
        bigint aggregate_version
        jsonb payload
    }
    SEARCH_PRODUCT_PROJECTION {
        uuid product_id PK
        decimal list_price
        bigint source_version
        uuid source_event_id
    }
    SALES_ORDER {
        uuid order_id PK
        timestamp ordered_at
    }
    SALES_ORDER_LINE {
        uuid line_id PK
        uuid order_id FK
        uuid catalog_product_ref
        decimal accepted_unit_price
    }
~~~~

In this diagram, the link between Catalog and Search is **logical identity**, not a cross-context FK; the link between `SalesOrder` and `SalesOrderLine` **is a local FK** within Sales.

Rules:

1. **Catalog is the authoritative writer** for `sku`, `title`, `current_list_price`, `currency`, and `version`.
2. **`Catalog.version` increments monotonically on every published product state change.** Version v2 is strictly newer than v1 for that product.
3. **Outbox events commit in the same Catalog transaction** as state mutations.
4. **Search accepts only verified full-state payloads**, updating projections only when `source_version` is newer.
5. **Each `eventId` is processed idempotently in Search DB**; stale events never overwrite newer versions.
6. **Sales retains `accepted_unit_price` and `product_title_at_purchase`** with historical semantics independent of current prices.
7. Search copies may lag within bounds; at **checkout**, Sales validates an active quote from the authoritative source.

### 6.2. Catalog Source and Transactional Outbox DDL

~~~~sql
CREATE SCHEMA cp_catalog;
CREATE SCHEMA cp_search;
CREATE SCHEMA cp_sales;

CREATE TABLE cp_catalog.product (
    product_id UUID PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE CHECK (BTRIM(sku) <> ''),
    title TEXT NOT NULL CHECK (BTRIM(title) <> ''),
    current_list_price NUMERIC(14, 2) NOT NULL
        CHECK (current_list_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    version BIGINT NOT NULL CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cp_catalog.outbox_event (
    event_id UUID PRIMARY KEY,
    product_id UUID NOT NULL
        REFERENCES cp_catalog.product(product_id),
    aggregate_version BIGINT NOT NULL
        CHECK (aggregate_version > 0),
    event_type TEXT NOT NULL
        CHECK (event_type = 'catalog.product-published'),
    schema_version INTEGER NOT NULL
        CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    CONSTRAINT uq_outbox_product_version
        UNIQUE (product_id, aggregate_version)
);

CREATE INDEX ix_cp_outbox_unpublished
    ON cp_catalog.outbox_event(occurred_at, event_id)
    WHERE published_at IS NULL;
~~~~

**Meaning of the two outbox keys:**

- `event_id` identifies one message so consumers can deduplicate retries.
- `(product_id, aggregate_version)` prevents two events for the same product version in this example of **one full-state event per state change**.

"One event per version" fits this specific stream. Another source might emit multiple domain events under one version, requiring a different outbox key. **Never copy illustrative constraints blindly to every system.**

### 6.3. Search Projection and Inbox DDL

~~~~sql
CREATE TABLE cp_search.product_projection (
    product_id UUID PRIMARY KEY,
    sku TEXT NOT NULL,
    title TEXT NOT NULL,
    list_price NUMERIC(14, 2) NOT NULL
        CHECK (list_price >= 0),
    currency_code CHAR(3) NOT NULL,
    source_version BIGINT NOT NULL
        CHECK (source_version > 0),
    source_event_id UUID NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE cp_search.inbox_event (
    event_id UUID PRIMARY KEY,
    product_id UUID NOT NULL,
    source_version BIGINT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~~

**Reading the columns:**

- `list_price` in Search is **a read copy of `Catalog.current_list_price`**, never independently editable.
- `source_version` is **the version issued by Catalog**, not a Search-generated counter.
- `source_event_id` traces which event produced the current projection.
- `synced_at` is when **Search applied the update**, not when the source mutated.
- `inbox_event` records processed **`eventId`s**, without proving payload validity or contiguous versions on its own.

This example assumes a single logical consumer for the inbox. If multiple independent handlers share an `eventId` yet run separate logic, include **`consumer_name` / `handler_id`** in the inbox key so one handler does not block another.

### 6.4. Sales Transaction History DDL

~~~~sql
CREATE TABLE cp_sales.sales_order (
    order_id UUID PRIMARY KEY,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED'))
);

CREATE TABLE cp_sales.order_line (
    line_id UUID PRIMARY KEY,
    order_id UUID NOT NULL
        REFERENCES cp_sales.sales_order(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    catalog_product_ref UUID NOT NULL,
    product_title_at_purchase TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    accepted_unit_price NUMERIC(14, 2) NOT NULL
        CHECK (accepted_unit_price >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    line_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (quantity * accepted_unit_price) STORED,
    CONSTRAINT uq_sales_order_line UNIQUE (order_id, line_no)
);
~~~~

**`catalog_product_ref` is not a SQL FK to `cp_catalog.product`.** It is a cross-context identifier; even in a shared database where a technical FK is possible, Sales should not tie historical order retention to whether a product stays in Catalog. Sales validates **quotes and sellability** at confirmation time via an explicit contract.

### 6.5. Inserting Product and v1 Outbox Event in One Transaction

~~~~sql
BEGIN;

INSERT INTO cp_catalog.product
    (product_id, sku, title, current_list_price,
     currency_code, version, updated_at)
VALUES
    ('00000000-0000-0000-0000-000000000101',
     'NOTE-A5', 'A5 Notebook', 100000.00,
     'VND', 1, TIMESTAMPTZ '2026-10-01 09:00:00+07');

INSERT INTO cp_catalog.outbox_event
    (event_id, product_id, aggregate_version,
     event_type, schema_version, occurred_at, payload)
SELECT
    '00000000-0000-0000-0000-000000000401',
    p.product_id,
    p.version,
    'catalog.product-published',
    1,
    p.updated_at,
    jsonb_build_object(
        'productId', p.product_id::TEXT,
        'sku', p.sku,
        'title', p.title,
        'listPrice', p.current_list_price::TEXT,
        'currency', p.currency_code,
        'version', p.version
    )
FROM cp_catalog.product AS p
WHERE p.product_id =
    '00000000-0000-0000-0000-000000000101';

COMMIT;
~~~~

When this transaction commits, **source state and the outbox record commit atomically**. If the outbox `INSERT` fails and rolls back, the product is not left partially created without its event.

A relay polls unpublished rows and pushes to a broker; **the SQL above does not include the relay itself**. Search does not update automatically merely because an outbox table exists.

### 6.6. Creating a Confirmed Order Snapshot

Suppose Sales confirms an order at an agreed price of **90,000 VND** for P01 (e.g., customer discount):

~~~~sql
INSERT INTO cp_sales.sales_order(order_id, ordered_at, status)
VALUES
    ('00000000-0000-0000-0000-000000000201',
     TIMESTAMPTZ '2026-10-01 10:00:00+07',
     'CONFIRMED');

INSERT INTO cp_sales.order_line
    (line_id, order_id, line_no, catalog_product_ref,
     product_title_at_purchase, quantity, accepted_unit_price)
VALUES
    ('00000000-0000-0000-0000-000000000202',
     '00000000-0000-0000-0000-000000000201',
     1,
     '00000000-0000-0000-0000-000000000101',
     'A5 Notebook', 2, 90000.00);
~~~~

Sales persists **`accepted_unit_price = 90,000`** and **`line_amount = 180,000`**. That differs legitimately from Catalog due to quotes, promotions, or negotiated terms. These direct `INSERT`s are a **test fixture**, not proof of full pricing, authorization, payment, and inventory workflows.

**Key invariant:** future Catalog price changes **must never overwrite this order's locked price**. Historical orders are not copies meant to converge toward `Catalog.current_list_price`.

## 7. Search Projection Consumer: Blocking Duplicates and Stale Events

### 7.1. Exact Consumer Goals

A sound consumer distinguishes:

- **New product event not yet in projection:** insert new projection row.
- **Event with version greater than stored version:** update projection row.
- **Duplicate `eventId` already processed:** apply zero side effects.
- **Older-version event:** never overwrite newer projection state.
- **Same version with different payload:** **contract/source conflict** requiring alerts and triage—never pick arbitrarily.
- **Event missing required fields, wrong tenant/unit, or invalid schema:** reject or quarantine cleanly.

Here events are **full-state**, so intermediate skipped versions are harmless once a newer state applies. For delta events, you must **detect gaps** and process in order or rebuild snapshots.

### 7.2. Applying v1 and Recording Inbox Atomically

Assume the relay published v1 from the outbox. This SQL simulates the **Search consumer logic**:

~~~~sql
BEGIN;

WITH accepted AS (
    INSERT INTO cp_search.inbox_event
        (event_id, product_id, source_version)
    VALUES
        ('00000000-0000-0000-0000-000000000401',
         '00000000-0000-0000-0000-000000000101', 1)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
),
applied AS (
    INSERT INTO cp_search.product_projection
        (product_id, sku, title, list_price, currency_code,
         source_version, source_event_id, synced_at)
    SELECT
        '00000000-0000-0000-0000-000000000101',
        'NOTE-A5',
        'A5 Notebook',
        100000.00,
        'VND',
        1,
        accepted.event_id,
        CURRENT_TIMESTAMP
    FROM accepted
    WHERE TRUE -- Separates ON CONFLICT from SELECT/JOIN's ON clause.
    ON CONFLICT (product_id)
    DO UPDATE SET
        sku = EXCLUDED.sku,
        title = EXCLUDED.title,
        list_price = EXCLUDED.list_price,
        currency_code = EXCLUDED.currency_code,
        source_version = EXCLUDED.source_version,
        source_event_id = EXCLUDED.source_event_id,
        synced_at = EXCLUDED.synced_at
    WHERE cp_search.product_projection.source_version
        < EXCLUDED.source_version
    RETURNING product_id
)
SELECT
    (SELECT COUNT(*) FROM accepted) AS accepted_events,
    (SELECT COUNT(*) FROM applied) AS updated_products;

COMMIT;
-- First run: accepted_events=1, updated_products=1.
~~~~

**Why must both steps share one transaction?** If you commit the inbox first and fail while updating the projection, retries get skipped because `eventId` is already marked processed. Here, **inbox and projection commit or roll back together** inside Search DB.

**Why check `source_version` in `WHERE`?** An older event can arrive after a newer one. The condition blocks version 1 from overwriting version 2. PostgreSQL serializes concurrent upserts on the same `product_id`, while the version guard enforces **strictly forward version progress**.

### 7.3. Catalog Updates Price: Mutating Source and Emitting v2

Suppose title and list price update:

~~~~sql
BEGIN;

WITH changed AS (
    UPDATE cp_catalog.product
    SET title = 'Hardcover A5 Notebook',
        current_list_price = 120000.00,
        version = version + 1,
        updated_at = TIMESTAMPTZ '2026-11-01 09:00:00+07'
    WHERE product_id =
        '00000000-0000-0000-0000-000000000101'
      AND version = 1
    RETURNING product_id, sku, title, current_list_price,
              currency_code, version, updated_at
),
logged AS (
    INSERT INTO cp_catalog.outbox_event
        (event_id, product_id, aggregate_version, event_type,
         schema_version, occurred_at, payload)
    SELECT
        '00000000-0000-0000-0000-000000000402',
        c.product_id, c.version,
        'catalog.product-published',
        1, c.updated_at,
        jsonb_build_object(
            'productId', c.product_id::TEXT,
            'sku', c.sku,
            'title', c.title,
            'listPrice', c.current_list_price::TEXT,
            'currency', c.currency_code,
            'version', c.version
        )
    FROM changed AS c
    RETURNING event_id
)
SELECT COUNT(*) AS emitted_events
FROM logged;

COMMIT;
-- emitted_events = 1 if product is at version 1.
~~~~

`AND version = 1` performs an optimistic concurrency check. If another transaction already bumped the product to version 2, `UPDATE` affects 0 rows, `changed` is empty, and **no bogus event enters the outbox**. The application checks `emitted_events` and surfaces a conflict rather than reporting success on 0 rows.

**Never use arrival timestamps for last-writer-wins**: `source_version` is Catalog's authoritative business sequence incremented atomically with state changes.

### 7.4. Search Receives v2

A real consumer parses event JSON, validates schemas, and casts types safely. To focus on version enforcement, this snippet uses **already-validated** v2 values:

~~~~sql
BEGIN;

WITH accepted AS (
    INSERT INTO cp_search.inbox_event
        (event_id, product_id, source_version)
    VALUES
        ('00000000-0000-0000-0000-000000000402',
         '00000000-0000-0000-0000-000000000101', 2)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
),
applied AS (
    INSERT INTO cp_search.product_projection
        (product_id, sku, title, list_price, currency_code,
         source_version, source_event_id, synced_at)
    SELECT
        '00000000-0000-0000-0000-000000000101',
        'NOTE-A5',
        'Hardcover A5 Notebook',
        120000.00,
        'VND',
        2,
        accepted.event_id,
        CURRENT_TIMESTAMP
    FROM accepted
    WHERE TRUE -- Separates ON CONFLICT from SELECT/JOIN's ON clause.
    ON CONFLICT (product_id)
    DO UPDATE SET
        sku = EXCLUDED.sku,
        title = EXCLUDED.title,
        list_price = EXCLUDED.list_price,
        currency_code = EXCLUDED.currency_code,
        source_version = EXCLUDED.source_version,
        source_event_id = EXCLUDED.source_event_id,
        synced_at = EXCLUDED.synced_at
    WHERE cp_search.product_projection.source_version
        < EXCLUDED.source_version
    RETURNING product_id
)
SELECT
    (SELECT COUNT(*) FROM accepted) AS accepted_events,
    (SELECT COUNT(*) FROM applied) AS updated_products;

COMMIT;
-- First time receiving v2: 1, 1.
~~~~

Expected state:

| Source / Copy | Product | Version | Price (VND) |
| --- | --- | ---: | ---: |
| Catalog | P01 | 2 | 120,000 |
| Search projection | P01 | 2 | 120,000 |
| Confirmed Sales order line | P01 | Different version axis | 90,000 |

Sales stays **90,000** and the 2-unit line stays **180,000**. This is **semantically accurate across all three models**, not a discrepancy to "sync into alignment."

### 7.5. Redelivering the Same Event

Re-running **the exact v2 application block** with the same `eventId` `000...402`: the inbox already holds that `eventId`:

~~~~text
accepted_events = 0
updated_products = 0
~~~~

No projection update fires, and `synced_at` does not bump due to a replay—preventing **stale messages from faking fresh sync timestamps**.

### 7.6. A Stale Event Arriving With a Fresh `eventId`

Suppose a misconfigured producer re-emits **v1 content** under a brand-new `eventId`. The inbox checks only `eventId` and accepts it, yet the **higher-version guard** blocks overwriting newer state:

~~~~sql
BEGIN;

WITH accepted AS (
    INSERT INTO cp_search.inbox_event
        (event_id, product_id, source_version)
    VALUES
        ('00000000-0000-0000-0000-000000000499',
         '00000000-0000-0000-0000-000000000101', 1)
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id
),
applied AS (
    INSERT INTO cp_search.product_projection
        (product_id, sku, title, list_price, currency_code,
         source_version, source_event_id, synced_at)
    SELECT
        '00000000-0000-0000-0000-000000000101',
        'NOTE-A5',
        'A5 Notebook',
        100000.00,
        'VND',
        1,
        accepted.event_id,
        CURRENT_TIMESTAMP
    FROM accepted
    WHERE TRUE -- Separates ON CONFLICT from SELECT/JOIN's ON clause.
    ON CONFLICT (product_id)
    DO UPDATE SET
        sku = EXCLUDED.sku,
        title = EXCLUDED.title,
        list_price = EXCLUDED.list_price,
        currency_code = EXCLUDED.currency_code,
        source_version = EXCLUDED.source_version,
        source_event_id = EXCLUDED.source_event_id,
        synced_at = EXCLUDED.synced_at
    WHERE cp_search.product_projection.source_version
        < EXCLUDED.source_version
    RETURNING product_id
)
SELECT
    (SELECT COUNT(*) FROM accepted) AS accepted_events,
    (SELECT COUNT(*) FROM applied) AS updated_products;

COMMIT;
-- accepted_events = 1, updated_products = 0:
-- new event ID yet stale source state.
~~~~

**Takeaway:** the inbox blocks **duplicate event IDs**, while `source_version` blocks **regressing state**. They protect against two different failures. Still, same-version events with differing content need **explicit conflict detection**—ignoring every non-increasing version alone does not prove data integrity.

### 7.7. Limitations of This Illustrative SQL

This is a **consumer logic pattern**, not a production-ready message handler:

- Omits source authentication, signatures, and tenant authorization.
- Omits JSON Schema parsing/validation, currency mapping, and ID scoping.
- Does not detect **reused `eventId`s carrying different payloads**; production inboxes store payload hashes/metadata and collision alerts.
- Does not quarantine **same product/version with conflicting content**. Detect and alert/quarantine instead of ignoring silently.
- Omits broker acks/retries/DLQs, real outbox relays, and reconnect handling.
- Omits unpublish/delete tombstones and future effective-dated versions.
- Shares one PostgreSQL instance between Catalog and Search purely for learning, without separate DB roles/privileges.

**Core principle holds:** never rely on **arrival order** when the source provides versions, never duplicate side effects on retries, and commit inbox + projection in one local transaction.

## 8. Reconciliation: When Is Divergence Between Two Copies a Bug?

### 8.1. Never Compare Semantically Different Values Blindly

To reconcile Search against Catalog, match **same `product_id`, same current-list-price definition, and same version**. To audit Sales, compare **locked order price against the authoritative quote at order time**, never against today's list price.

A flawed reconciliation query:

~~~~sql
-- ILLUSTRATING A SEMANTICALLY INVALID COMPARISON:
SELECT l.line_id, l.accepted_unit_price, c.current_list_price
FROM cp_sales.order_line AS l
JOIN cp_catalog.product AS c
    ON c.product_id = l.catalog_product_ref
WHERE l.accepted_unit_price <> c.current_list_price;
~~~~

This flags the 90,000 order line against the 120,000 list price. That difference **proves no bug**, because list price and locked transaction price are different concepts. Such queries are valid only for **contextual variance analysis**, never to drive a "sync orders to match catalog" job.

### 8.2. Reconciling Search Against Catalog

On the test database:

~~~~sql
SELECT
    c.product_id,
    c.sku,
    c.version AS catalog_version,
    s.source_version AS search_version,
    s.synced_at,
    CASE
        WHEN s.product_id IS NULL THEN 'MISSING_PROJECTION'
        WHEN s.source_version < c.version THEN 'LAGGING'
        WHEN s.source_version > c.version THEN 'AHEAD_OF_SOURCE'
        WHEN s.sku IS DISTINCT FROM c.sku
          OR s.title IS DISTINCT FROM c.title
          OR s.list_price IS DISTINCT FROM c.current_list_price
          OR s.currency_code IS DISTINCT FROM c.currency_code
          THEN 'DIVERGENT_SAME_VERSION'
        ELSE 'IN_SYNC'
    END AS sync_state
FROM cp_catalog.product AS c
LEFT JOIN cp_search.product_projection AS s
    ON s.product_id = c.product_id
ORDER BY c.sku;
~~~~

Each state means something distinct:

| State | Interpretation | Action |
| --- | --- | --- |
| **MISSING_PROJECTION** | Catalog has product, Search does not | Check publish filters, seed/replay progress, event source |
| **LAGGING** | Search holds a lower version | Within SLO: wait; past SLO: alert and replay/repair |
| **AHEAD_OF_SOURCE** | Search holds a higher version than compared source | Check mixed environments, DB restores, bad mappings, or incidents |
| **DIVERGENT_SAME_VERSION** | Equal version yet differing attributes | Contract/transform bug; never overwrite blindly |
| **IN_SYNC** | Compared fields match at current version | Passes this check; does not prove other invariants |

After applying v2, P01 should show **`IN_SYNC`**. If Search hasn't processed v2 yet, it shows **`LAGGING`**, not necessarily source corruption.

**Critical caveat:** this query assumes **1:1 mapped attributes** within the same tenant and scope. If Search intentionally displays a merchandising alias title, never compare that alias to `Catalog.title` and call it divergence. Compare `catalog_title_projection` against `Catalog.title`, keeping aliases governed separately.

### 8.3. Detecting Rows Present Only in Search

An unpublished or deleted Catalog item may linger in Search. When the contract requires removing unpublished items from Search, scan for orphans:

~~~~sql
SELECT s.product_id, s.sku, s.source_version
FROM cp_search.product_projection AS s
LEFT JOIN cp_catalog.product AS c
    ON c.product_id = s.product_id
WHERE c.product_id IS NULL;
~~~~

**Never immediately `DELETE` every returned row**: another source may publish to Search, partitions may differ, replicas may lag, or retention may keep records. Base deletion on the **delete/tombstone contract** and verified source state.

### 8.4. Matching Versions Still Require Value Checks

Suppose Search holds:

~~~~text
product_id=P01, source_version=2, list_price=110000
~~~~

while Catalog v2 is 120,000. Both share version 2, so a check assuming "equal version means synced" **misses the bug**.

Possible causes:

- Payload mapped the wrong unit or column.
- Consumer applied a different event carrying the same version.
- An admin manually edited the projection.
- Events were tampered with or reused an ID.
- Search DB restored from an incompatible snapshot.

**Version numbers govern ordering, not payload correctness.** Periodic reconciliation must compare source values and projected values at equal versions under documented transforms.

### 8.5. Clocks and Freshness: Do Not Just Subtract Two Timestamps

Seeing `Search.synced_at` 5 seconds newer than `Catalog.updated_at` does not prove Search is accurate: a consumer may have just replayed an old event. Conversely, `synced_at` older than `updated_at` may still fall comfortably inside SLO lag.

Reliable freshness tracking requires:

1. Knowing **which source event and version applied**.
2. Tracking **oldest unprocessed message age**, consumer offsets/watermarks, and queue backlog.
3. Accounting for **clock skew** and `occurred_at` vs. `committed_at`.
4. Separating **emission, broker, processing, and read-query lag**.
5. Counting changes **not yet converged**, not just successful event deliveries.

A simple indicator:

~~~~text
product_version_gap = catalog.version - search.source_version
~~~~

helps when versions increment uniformly per product, yet `gap = 1` **does not tell you whether lag is 1 second or 1 day**. Meanwhile, `gap = 0` with mismatched payloads is still broken. Combine **version reconciliation with freshness monitoring**.

### 8.6. When Source and Copy Live in Separate Databases

In production, direct cross-DB joins between Catalog and Search are rarely allowed. Instead:

- Export **snapshots tagged with timestamps, versions, or watermarks** from Catalog.
- Run scheduled batch reconciliation jobs with read access to both.
- Paginate verification APIs across samples or full datasets.
- Compute **canonicalized hashes** over shared semantic fields to isolate mismatches fast.
- Reconcile objects by **`(tenant_id, business_id, source_version)`**.

Never hash two JSON blobs with differing key orders or decimal formats and declare divergence. Always **canonicalize** or compare normalized typed fields per contract.

## 9. Update Conflicts: Never Default to "Last Writer Wins"

### 9.1. Bug: Two Competing Writers With No Precedence

Suppose:

~~~~text
10:00 Catalog sets P01.list_price = 110000.
10:01 Search admin edits P01.list_price = 120000.
10:02 Catalog → Search sync runs, writes 110000.
10:03 Search admin asks why their price edit vanished.
~~~~

This is not merely an ordering bug; two parties are mutating **the same attribute with no ownership rule**.

The cleanest fix when Search is a read model: **revoke Search admin's ability to edit `list_price`**. All list-price changes go through Catalog/Pricing; Search updates strictly via events. If Search needs channel-specific promo pricing, create **`search_promotional_price`** or explicit pricing rules with clear ownership and precedence.

### 9.2. Last-Write-Wins Can Silently Drop Business Intent

Some systems use timestamp-based **last-write-wins (LWW)** to settle conflicting records. Remember that LWW is **a tie-breaking policy, not a guarantee of business correctness**.

Risks:

- Node clocks skew.
- Events arrive out of mutation order.
- Two fields are edited by actors with different permissions.
- A stale offline update syncs late and overwrites critical newer state.
- Pricing or financial records cannot afford silent history loss.

If LWW is used, define **trusted timestamps, conflict scopes, and whether lost updates are acceptable**, backed by tests. Never adopt LWW for prices, money, inventory, or permissions merely because it is easy to code.

### 9.3. Authoritative Versions and Optimistic Concurrency

With Catalog as the single writer, use optimistic locking:

~~~~sql
UPDATE cp_catalog.product
SET current_list_price = 130000.00,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id =
    '00000000-0000-0000-0000-000000000101'
  AND version = 2
RETURNING product_id, version;
~~~~

This is only **a conflict-detecting `UPDATE` pattern**, not a complete Catalog write path: under an outbox architecture, never commit this change while **forgetting the matching outbox event in the same transaction**. Wrap the conditional `UPDATE` and outbox `INSERT` inside one transaction as in Section 7.3.

When two requests race on `version=2`, only one advances to `version=3`; the other sees 0 rows, raises a conflict, and retries or alerts the user.

**Versions must increment at the authoritative aggregate**, never via an independent counter inside Search. If two systems independently assign `version=3` to conflicting values, comparing `source_version` masks conflicts instead of solving them.

### 9.4. Are Multiple Writers Ever Valid?

Yes—for offline collaborative editing, multi-device wishlists, or domains with **formal merge rules**. Yet that requires **intentional multi-writer design**, not "anyone can overwrite anything."

Define explicitly:

- **Field ownership** or write scopes per source.
- Whether merges are commutative.
- How same-field conflicts are detected and resolved.
- Version vectors, causal metadata, or equivalent tracking if needed.
- When a **data steward** must intervene on conflicts.
- Convergence criteria and post-merge invariants.

**CRDTs** help specific data types converge, yet **do not automatically enforce invariants like non-negative inventory, single-settlement invoices, or locked checkout prices**. Never adopt merge machinery for financial data merely because it syncs counters cleanly.

### 9.5. Duplicate Data Differs From Duplicate Identity

CRM and ERP both hold "Nguyen Van A" with similar emails. Merging both into one golden record is never `SELECT DISTINCT` or `GROUP BY email`.

You need:

- Clear **business identity**: person, legal entity, account, or shipping contact?
- Deterministic/probabilistic matching rules guarding against false merges.
- Preserved **source IDs**, provenance, and verification outcomes.
- **Survivorship rules** specifying which source wins **for each field**.
- **Unmerge** procedures when records are falsely combined.
- Privacy and access controls across merged profiles.

**Golden records are governed models**, not a table holding "the latest value from every source."

## 10. Deletion, Unpublishing, and Privacy: Sync Is Not Only UPDATE

### 10.1. Deletion Differs From Unpublishing

A product can be:

- **Unpublished:** hidden from search results while still existing in Catalog.
- **Discontinued:** unavailable for new sales while historical orders retain references.
- **Merged:** identity P01 remapped to P99 under explicit rules rather than deleted.
- **Hard-deleted per policy:** copies must purge with no source left to rebuild from.

If Search only consumes **`ProductPublished`** without **`ProductUnpublished`**, discontinued items stay searchable forever. If a batch job only upserts active rows without diffing removals, old items linger indefinitely too.

### 10.2. Versioned Tombstones

Contracts can emit:

~~~~json
{
  "eventId": "e-p01-v4",
  "eventType": "catalog.product-unpublished",
  "schemaVersion": 1,
  "productId": "P01",
  "aggregateVersion": 4,
  "isPublished": false
}
~~~~

The consumer tracks the **unpublish version**:

~~~~text
P01 v3: published = true
P01 v4: published = false
P01 v2 arrives late: must never restore P01 into search results.
~~~~

If the consumer simply runs `DELETE` on Search and **forgets the last applied version**, a late v2 event **re-inserts** the product! Retain **tombstones / version metadata** per retention and resync policy even when items are hidden.

Some architectures use CDC delete markers or snapshot reconciliation. Either way, specify **delete timing, ordering, tombstone history, and rebuild rules**.

### 10.3. Deleting Personal Data Across Replicas

Personal data can live across:

~~~~text
Identity profile
Sales contact snapshot
Search/cache
Warehouse/reports
Exports or partner systems
Backups
~~~~

Upon an erasure or correction request, updating only the source table never suffices. Maintain:

1. **An inventory of every replicated location**, purpose, access controls, and retention limits.
2. **An authoritative source** governing changes per applicable policy.
3. Contracts propagating erasure or anonymization across in-scope copies.
4. Explicit rules for **transaction snapshots, statutory accounting retention, and backups**—neither erasing illegally nor retaining past limits.
5. Confirmation reconciliation and escalation for unresponsive external systems.
6. Guards against replaying old events that **resurrect erased personal data**.

**This does not mean "delete every historical record instantly"**: erasure rights, statutory retention, and processing purposes depend on legal and business context. The modeling lesson is maintaining **lineage, scope, and coordinated deletion** rather than assuming "deleted at source means gone everywhere."

## 11. Failure Scenarios a Pretty Sync Diagram Does Not Fix

### 11.1. Dual-Write Between Database and Broker

An error-prone pattern:

~~~~text
1. Catalog DB COMMITS new price.
2. App publishes ProductUpdated.

If process crashes between 1 and 2:
  Catalog holds the new price; Search never receives the event.
~~~~

Publishing before `COMMIT` risks alerting consumers to changes that later roll back. **Two sequential calls between a DB and a broker are never atomic.**

**Standard remedy:** commit Catalog state and outbox record in one local transaction, then let a relay publish with retries. Because the relay can crash after publishing and before marking sent, events may **deliver multiple times**—so consumers must be idempotent.

### 11.2. Redelivery Double-Counting Money or Stock

An event:

~~~~json
{
  "eventId": "payment-001",
  "type": "PaymentSettled",
  "amount": "100000.00",
  "currency": "VND"
}
~~~~

If a projection runs:

~~~~text
daily_total += amount
~~~~

on every delivery without deduplication, a single redelivery inflates `daily_total` to 200,000. This is the **non-idempotent accumulator** bug.

Fixes:

- Store **unique `payment_id`/`eventId`** at fact grain and aggregate from the deduplicated facts.
- Commit inbox and projection updates inside one consumer transaction.
- Use source-keyed upserts rather than blind increments.
- If using deltas, enforce strict deduplication and gap checks.

**`SUM(DISTINCT amount)` is never a valid fix**: two distinct legitimate payments can share the exact amount 100,000.

### 11.3. Out-of-Order Processing

~~~~text
Catalog v3: price = 120000
Search already applied v3.
Event v2: price = 110000 arrives late.
~~~~

An unconditional consumer `UPDATE` regresses Search back to 110,000. Design for:

- **Authoritative aggregate-level monotonic versions** from the source.
- Consumers applying **strictly newer versions** (or contiguous sequences for deltas).
- Detection of **same-version payload mismatches**.
- Honest documentation of what ordering guarantees the broker actually provides, without guessing.

### 11.4. Infinite Bidirectional Sync Loops

~~~~text
Catalog updates title.
Search receives event, updates title, emits SearchTitleUpdated.
Catalog receives it, updates title, emits CatalogTitleUpdated.
...
~~~~

If Search is purely a projection, **never emit a business event back for the same attribute just because the copy synced**. When intentional bidirectional sync is genuinely required, carry **origin, causality, field ownership, and loop-suppression rules** so loops cannot occur and conflicts surface clearly.

### 11.5. Two Authorities Over Payment Status

Billing sets `invoice_paid=true`; Sales also flips `paid=true` manually without a verified `PaymentSettled` event. Both disagree with no clear winner.

Better design:

- Billing/Payments owns **authoritative settlement state**.
- Sales keeps a **`payment_summary_projection`** tagged with `source_version`/`eventId`.
- Sales never edits its projection to "force paid"; it sends valid commands to Payments.
- Partial settlements and refunds likely require **richer state models than a boolean `paid` flag**.

Collapsing a multi-state workflow into a copied boolean **destroys information**—a semantic mapping error, not just a sync glitch.

### 11.6. Timestamp Polling With `updated_at` Drops Updates

A polling query:

~~~~sql
SELECT *
FROM cp_catalog.product
WHERE updated_at > :last_watermark
ORDER BY updated_at;
~~~~

suffers from:

- Two rows sharing **the exact boundary timestamp**, where advancing the watermark skips the second row.
- Long-running transactions committing after the watermark passed their earlier `updated_at`.
- Offset pagination drifting while rows mutate.
- Crashes after target write and before saving checkpoints.
- **Hard-deleted rows** vanishing silently without appearing in polls.
- Clock skew and timezone mismatches across nodes.

Reliable alternatives use **CDC / change logs with log offsets**, or **total-order cursors `(updated_at, product_id)` over bounded snapshot windows** alongside delete handling and idempotent retries. Even with tie-breakers and overlap windows, verify against in-flight commit behavior on the source engine.

### 11.7. Gaps Between Initial Snapshot and Change Stream

When building a new Search index:

~~~~text
10:00 Start full scan of Catalog.
10:05 Catalog updates P01 price and emits event.
10:10 Snapshot scan finishes.
10:11 New consumer starts reading events emitted after 10:10.
~~~~

The 10:05 update **may miss the snapshot** while also being skipped by the consumer starting after 10:10. That is the **snapshot–stream gap**.

A proper bootstrap:

- Captures a **consistent snapshot aligned to a log position/watermark**.
- Starts stream consumption from a position guaranteed **not to miss changes during the snapshot**.
- Allows duplicate deliveries while relying on idempotency to converge without loss.
- Reconciles row counts, versions, and checksums post-build.
- Supports full rebuilds whenever correctness cannot be proven.

Never say "build the index, then turn on the consumer" without accounting for writes occurring **mid-build**.

### 11.8. Replaying Events After Deletions

Search processed `ProductUnpublished` v4, yet a replay archive holds only `Published` v1–v3. Rebuilding blindly from available events **without the v4 tombstone** resurrects unpublished products.

Replay plans require:

- Enough retention for the full history or an authoritative current snapshot.
- Explicit delete/unpublish handling.
- Version and checkpoint metadata.
- Post-replay reconciliation against the authoritative source.

**Replay cannot magically heal missing history** if logs were truncated or legacy schema versions can no longer decode.

## 12. Remediation Workflow for an Already-Diverged System

Never start by running `UPDATE` across all copies to match an arbitrary table. First **establish semantics and authority**, or you risk propagating corrupt data everywhere.

### Step 1 — Inventory Copies and Write Paths

Map per attribute:

~~~~text
Attribute: product.list_price (current list price).

Existing copies:
  Catalog.product.current_list_price
  Search.product_projection.list_price
  Redis.product-price:P01
  BI.DIM_PRODUCT.list_price
  Sales.order_line.accepted_unit_price (different semantics!)

Writers:
  Catalog Admin API
  Search Admin Direct Edit (invalid write path to eliminate)
  Nightly ETL Job
  Cache refresh Worker

Readers:
  Search UI
  Checkout API
  BI Dashboard
  Support Tool
~~~~

**Goal of this step is classification:** `Sales.accepted_unit_price` has different semantics and is excluded from "sync to match `Catalog.current_list_price`," even though both look like P01 prices.

### Step 2 — Declare Authoritative Sources and Write Authority

Establish a **data ownership contract**:

- Catalog/Pricing owns the catalog and list prices within scope.
- Search is strictly a read projection.
- Redis is a TTL/invalidation cache.
- BI retains reporting metrics per published definitions and timestamps.
- Sales owns locked order snapshots.

**Fence competing writers** or reroute them into commands on the authoritative source. Leaving Search Admin able to edit the projection post-backfill guarantees **divergence returns immediately**.

### Step 3 — Specify Identifiers and Transformations

Example:

~~~~text
Key:
  product_id UUID globally unique.

Catalog state:
  title TEXT
  price NUMERIC(14,2)
  currency = VND
  version BIGINT

Search projection:
  title = Catalog.title
  list_price = Catalog.current_list_price
  currency_code = Catalog.currency_code
  source_version = Catalog.version

Transformation:
  Exact decimal, no float rounding.
  No timezone conversion needed for price amount.
  Source event contains full state.
~~~~

When the target applies accent stripping, stemming, or tokenization, those columns are **derived** and validated against **transform rules**, never raw byte equality with source text.

### Step 4 — Guard New Mutations Before Repairing Historical Data

Design the pipeline:

1. Commit Catalog state and outbox **in one local transaction**.
2. Relay emits versioned events with retries.
3. Search validates and upserts only on strictly newer versions; inbox deduplicates.
4. Emit unpublish/tombstone events where needed.
5. Monitor lag/conflicts and test rebuilds.

Running backfills before guarding live writes means one Catalog update mid-backfill reintroduces drift immediately.

### Step 5 — Bootstrap Consistently Without Snapshot–Stream Gaps

Pick a bootstrap strategy anchored to a **consistent log offset or version watermark**. During index build, overlapping snapshot and stream events are safe once the consumer is idempotent—**tolerate duplicates, never drops**.

Post-bootstrap checks:

- Published product counts.
- `source_version` per product.
- Title/price/currency alignment per transform rules.
- Records missing in source yet lingering in projection.
- Unmapped rows or out-of-domain values.

### Step 6 — Controlled Cutover

Switch readers to the new projection only when:

- Freshness and error rates meet SLOs.
- All out-of-band projection write paths are closed.
- Traffic can fail back or read from source when access patterns permit.
- Checkout never locks purchase prices from potentially stale Search data.
- High-consistency actions display warnings, fall back, or fail closed if the authoritative source is down.

**Never cut over 100% of traffic merely because a backfill job exited zero once.**

### Step 7 — Retire Legacy Syncs and Keep Reconciliation Running

Once stable:

- Remove legacy bidirectional sync jobs and obsolete staging tables/triggers.
- Revoke direct write privileges on read stores.
- Run scheduled **reconciliation** with alerts.
- Standardize **repair from authoritative source**, never manual edits that break lineage.
- Review cost, retention, access controls, and future schema/event evolution plans.

### Visual Remediation Roadmap

~~~~mermaid
flowchart TD
    A["Detect diverged copies"] --> B["Classify same vs. different semantics"]
    B --> C{"Same current fact?"}
    C -- "No" --> D["Define snapshot / separate field"]
    C -- "Yes" --> E["Assign source of truth + owner"]
    E --> F["Design version/event/repair contract"]
    F --> G["Fence competing writers"]
    G --> H["Bootstrap + capture changes"]
    H --> I["Reconcile versions, values, and deletes"]
    I --> J{"Ready for cutover?"}
    J -- "No" --> K["Quarantine, replay, or fix mapping"]
    K --> I
    J -- "Yes" --> L["Cut over + monitor + cleanup"]
~~~~

## 13. Testing and Monitoring Synchronized Data

### 13.1. Test Matrix for Catalog → Search

| Scenario | Input | Expected Outcome |
| --- | --- | --- |
| Create product | v1, complete payload | Search holds one product at v1 |
| Rename / reprice | v2, full-state | Search advances to v2 with new title/price |
| Replay same `eventId` | Resend v2 event | No second update applied |
| Late older event | Already at v2, receives v1 | Stays at v2 |
| Future event arrives early | Missing v2, receives v3 full-state | Advances to v3 if valid full-state |
| Delta missing version | Receives v3 delta without v2 | Detects gap; does not add blindly |
| Same version, differing payload | v2 event price differs from v2 source | Flags conflict/quarantines; never succeeds silently |
| Wrong currency | USD payload when contract requires VND | Rejects or converts via approved policy |
| Wrong tenant/key | Tenant B's product P01 | Never writes into Tenant A's projection |
| Lost event | v2 never reaches Search | Lag/reconciliation detects and repairs |
| Unpublish | `ProductUnpublished` v4 | Hidden; stale events never resurrect it |
| Writes during snapshot | Concurrent backfill + events | Zero dropped or duplicated rows |
| Search data loss | Rebuild projection | Converges from trusted snapshot/logs |
| Catalog reprices post-order | Catalog becomes 120,000 | Sales locked price stays 90,000 |
| Consumer crash mid-tx | Inbox written before projection | Both roll back; retry succeeds cleanly |
| Distinct IDs, same state | Two events for same product/version | No duplicate effect; flags collision if payloads differ |

**No single test proves every condition.** Sequential happy-path tests never replace concurrency and failure-recovery testing.

### 13.2. Minimum SQL Audit Suite

**Check Search lagging behind Catalog:**

~~~~sql
SELECT
    c.product_id, c.version, s.source_version
FROM cp_catalog.product AS c
LEFT JOIN cp_search.product_projection AS s
    ON s.product_id = c.product_id
WHERE s.product_id IS NULL
   OR s.source_version < c.version;
~~~~

**Check mismatched values at equal versions:**

~~~~sql
SELECT c.product_id, c.version,
       c.current_list_price AS catalog_price,
       s.list_price AS search_price
FROM cp_catalog.product AS c
JOIN cp_search.product_projection AS s
    ON s.product_id = c.product_id
WHERE c.version = s.source_version
  AND (
       c.current_list_price IS DISTINCT FROM s.list_price
    OR c.title IS DISTINCT FROM s.title
    OR c.sku IS DISTINCT FROM s.sku
    OR c.currency_code IS DISTINCT FROM s.currency_code
  );
-- Expect 0 rows if Search maps 1:1.
~~~~

**Check unpublished outbox rows:**

~~~~sql
SELECT event_id, product_id, aggregate_version, occurred_at
FROM cp_catalog.outbox_event
WHERE published_at IS NULL
ORDER BY occurred_at, event_id;
~~~~

An unpublished row **is not automatically a failure**: the relay may simply be catching up, or crashed right after publishing before marking sent. Trigger alerts using **row age, backlog depth, retry counts, and broker health**.

**Verify locked order prices remain independent:**

~~~~sql
SELECT
    l.line_id,
    l.product_title_at_purchase,
    l.accepted_unit_price,
    l.line_amount,
    c.title AS current_catalog_title,
    c.current_list_price AS current_catalog_price
FROM cp_sales.order_line AS l
LEFT JOIN cp_catalog.product AS c
    ON c.product_id = l.catalog_product_ref;
~~~~

This final `JOIN` is **an instructional cross-schema query in one test DB**. Differences between locked and current prices are not errors when their semantics differ.

### 13.3. Operational Metrics

| Metric | What It Catches |
| --- | --- |
| **Outbox pending count / oldest age** | Relay falling behind or stalled |
| **Consumer lag / last applied offset** | Message backlog, slow projection |
| **Source-version gap** | Product copies lagging behind source |
| **Divergence count by field & version** | Bad transforms or direct projection edits |
| **Duplicate-event count** | Normal retries vs. upstream duplicate storms |
| **Version-conflict count** | Same version with conflicting payloads |
| **Dead-letter / quarantine count** | Malformed or unprocessable payloads |
| **Rebuild / replay duration** | Index recovery time |
| **Missing or orphan projection count** | Incomplete bootstrap or unpropagated deletes |
| **Correction latency** | Time from divergence detection to convergence |
| **Checkout quote mismatch** | Risk of Search price expiring before confirmation |

Pair metrics with **baselines, thresholds, and named responders**. A green dashboard celebrating high event throughput does not mean **permanently dropped items** were detected.

### 13.4. Incident Triage to Avoid Wrong "Repairs"

| Category | Symptoms | Proper Action |
| --- | --- | --- |
| **Stale within SLO** | Search version slightly behind while backlog drains | Accept contractual lag and monitor |
| **Stale beyond SLO** | Version lag exceeds threshold | Investigate relay/consumer; replay or rebuild |
| **Divergent same version** | Equal version yet differing prices | Quarantine, audit transforms/write perms, repair from source |
| **Ambiguous identity** | Unclear SKU/tenant mapping | Pause sync on affected keys; verify business key |
| **Conflicting authorities** | Two systems edit the same field | Lock down ownership or merge rules before overwriting |
| **Legitimate snapshot diff** | Sales accepted price differs from Catalog | Do not sync into equality; preserve history |
| **Unpropagated delete** | Deleted item still searchable | Fix tombstones, retention, and event ordering |
| **Corrupted source** | Wrong price entered at source | Fix via source business workflow and emit new version |

### 13.5. Traceability and Sensitive Data

To debug a wrong price, trace:

~~~~text
product_id
tenant_id / source scope
catalog_version
source_event_id
event schema_version
source occurred_at
Search applied_at
transform_version
reconciliation status
correction/replay ticket
~~~~

Yet **never dump full emails, addresses, tokens, or payment secrets into logs just for easier debugging**. Log IDs, hashes, or redacted metadata per privacy policy—remember logs and dead-letter queues are also **data copies** subject to retention and access controls.

## 14. Choosing the Right Structure Instead of Blindly Copying

### 14.1. Decision Tree by Data Purpose

Before creating a new copy, walk through:

1. **Must it preserve immutable transaction history?** If yes, design a dedicated snapshot with update guards; never overwrite from current sources.
2. **Is it a read view of current state?** If yes, pick the authoritative source, allowed lag, refresh mechanism, and drift repair rules.
3. **Is strong consistency needed at critical decisions?** If yes, query the authority, validate active quotes, use local transactions, or add explicit confirmation steps.
4. **Is lag tolerable?** If yes, caches, projections, or replicas fit with an explicit freshness SLO.
5. **Is it a time-aggregated metric?** If yes, define grain, additivity, fact/dimension sources, history rules, and refresh cadence.
6. **Are multiple writers truly allowed to edit?** If yes, design conflict resolution, provenance, and field ownership—never default to "last record wins."
7. **Can the copy be rebuilt from the authoritative source?** If not, the copy may actually hold **primary facts or decisions**, requiring a reassessment of ownership.

### 14.2. Trade-Offs Between Normalization and Denormalization

| Criterion | Appropriate Relational Normalization | Governed Denormalization / Projection | Ungoverned Redundancy |
| --- | --- | --- | --- |
| Ownership | Usually clear in one write model | Source and target explicitly declared | Ambiguous or competing |
| Update cost | Writes normalized source tables | Requires sync, versions, reconciliation | Causes update anomalies |
| Queries | May require joins | Tailored fast reads per access pattern | Fast yet untrustworthy |
| History | Needs explicit snapshot/temporal design | Can model explicit snapshots | Easily overwritten or wrong point-in-time |
| Evolvability | Clear FK/transaction constraints | Versioned contracts decouple models | One change triggers cascading drift |
| Operations | Monitor DB constraints | Adds relays, consumers, freshness metrics | Hard to trace root cause and recover |
| When to choose | Local dependencies and invariants | Clear read scalability or historical durability gains | Never acceptable as a design target |

**The right decision is not always deleting duplicates.** A well-contracted projection often beats joining five live operational databases on every request. Conversely, when no clear latency, history, or boundary benefit exists, removing copies **cuts cost and bugs**.

### 14.3. Minimum Spec Before Creating a Copy

A concise spec covers:

~~~~text
Replica/Projection name:
Business purpose:
Authoritative fields/source:
Business key and scope:
Snapshot or current-state semantics:
Writer permissions:
Event/API/CDC/batch contract:
Schema/transform version:
Source ordering/version and conflict behavior:
Freshness SLO and fallback:
Duplicate/late/delete handling:
Bootstrap and replay procedure:
Reconciliation rules:
Sensitive-data policy:
Owner and on-call:
Decommissioning conditions:
~~~~

If a spec cannot answer **who is authoritative, who may write, how copies refresh, and how drift is detected**, hold off on creating another copy of the same concept. That design pause costs far less than repairing corrupted production data later.

## 15. Checklist for Verifying Controlled Redundancy

### 15.1. Semantics and Ownership

- [ ] Every copy has an explicit **purpose**: snapshot, cache, projection, replica, or analytics.
- [ ] Duplicated fields are verified as **same semantics vs. different semantics**.
- [ ] Authoritative sources are defined by **field, scope, and time**, not by assuming one DB owns everything.
- [ ] No two writers mutate the same current attribute without a **conflict protocol**.
- [ ] Business keys include tenant, source, and version where scope demands.
- [ ] Historical snapshots are shielded from current-state sync overwrites.
- [ ] Access permissions on copies never exceed their purpose or privacy policy.

### 15.2. Change and Sync Contracts

- [ ] Sync triggers are defined: API, event, CDC, batch, polling, or TTL.
- [ ] Payloads declare **schema version**, units, IDs, and semantics.
- [ ] **Full-state** and **delta** events are distinguished; deltas define gap/ordering rules.
- [ ] Sources emit versions/sequences in the proper scope.
- [ ] Consumers block duplicate deliveries and version regressions.
- [ ] Consumers detect **same-version conflicting payloads**.
- [ ] State and outbox records commit in the same local transaction when using outboxes.
- [ ] Inbox and projection updates commit or roll back together.
- [ ] Retries, DLQs/quarantine, replays, and business idempotency exist where needed.
- [ ] **Unpublish/delete/tombstone** contracts prevent replays from resurrecting deleted items.
- [ ] Snapshot bootstrap and change streams align with zero unverified gaps.

### 15.3. Freshness, Reconciliation, and Operations

- [ ] Freshness SLOs and stale-read fallbacks exist for latency-sensitive decisions.
- [ ] Backlog, oldest unprocessed message, consumer lag, and version gaps are monitored.
- [ ] Reconciliation checks **attribute values at equal versions**, not just row counts or timestamps.
- [ ] Drift triggers **repair from authoritative sources** or governed conflict workflows.
- [ ] Checks catch missing/orphan projections, deletes, and unmapped tenant IDs.
- [ ] Projections can rebuild cleanly from authoritative snapshots/logs.
- [ ] Tests cover post-COMMIT crashes, redeliveries, late/out-of-order events, and restarts.
- [ ] Traceability/lineage supports debugging without leaking raw PII into logs.
- [ ] Obsolete copies have decommissioning paths covering access and retention.

### 15.4. Acceptance Criteria per Copy

| Goal | Required Evidence |
| --- | --- |
| **Right source** | Ownership matrix and writer inventory |
| **Right semantics** | Field, timestamp, unit, and scope contracts |
| **Right records** | Validated keys/mappings and cross-tenant tests |
| **No lost updates** | Failure-tested outbox/CDC/sync paths |
| **No duplicate side effects** | Inbox/idempotency tests and business keys |
| **No version regression** | v3 before v2, v1 replay, and same-version conflict tests |
| **Sufficient freshness** | Measured SLOs and alerts |
| **Repairable** | Reconciliation, replay, rebuild, and delete handling |
| **Historical integrity** | Sales snapshots remain untouched on Catalog edits |
| **Least-privilege access** | Named owners, ACLs, and scoped retention |

**A copy is "verified" only within the specific attributes and failure modes actually tested.** Passing SQL or delivering one broker message does not prove all copies across all consumers converge.

## 16. Practice Exercises With Solutions

### Exercise 1 — Are Different Prices Necessarily Wrong?

P01 has `Catalog.current_list_price = 120,000 VND`, `Search.list_price = 110,000 VND`, and `Sales.accepted_unit_price` from last month's order `= 90,000 VND`.

**Question:** which price must converge, and which must never be synced automatically?

**Answer:** if Search projects **current list price** from Catalog, it must converge to **120,000** within allowed lag; 110,000 indicates staleness or a mapping bug. `Sales.accepted_unit_price = 90,000` is a **locked purchase snapshot** and need not match Catalog. Never `UPDATE` historical order prices to match current catalog prices.

### Exercise 2 — Is There Really One Single Source of Truth for Every Field?

Catalog owns names/list prices, Inventory owns allocatable stock, and Billing owns settled amounts. One team proposes moving everything into Catalog to create "one source of truth."

**Question:** is that proposal sound?

**Answer:** no. **Authoritative sources are defined per attribute, context, and point in time.** Catalog should not write inventory balances or settled payments, which carry independent invariants and owners. A unified screen belongs in a **read model**, not one monolithic write model.

### Exercise 3 — Snapshot or Projection?

Order O100 stores `product_title_at_purchase`. Catalog renames the product the next day.

**Question:** should `product_title_at_purchase` be updated?

**Answer:** normally **no**, when defined as the title displayed at purchase time. It is a historical fact with its own meaning. `Search.current_title` should update to the new name. Correcting an actual historical document error requires an audited business adjustment workflow, not a periodic sync overwrite.

### Exercise 4 — Two Systems Editing One Price

Catalog Admin sets P01 to 110,000; Search Admin sets P01 to 120,000. A nightly job copies Catalog → Search.

**Question:** what is the root issue and fix?

**Answer:** **two competing writers on one attribute** without ownership or conflict rules. Since Catalog owns list price, block Search Admin from editing that field directly. Route price edits to Catalog, or introduce a distinct **promotional price** with clear ownership and precedence.

### Exercise 5 — Does a TTL Guarantee Accurate Checkout Prices?

Redis caches prices for 5 minutes. Catalog updates a price, and a customer checks out 20 seconds later using the cached price.

**Question:** does a 5-minute cache TTL guarantee accurate transaction pricing?

**Answer:** no. For up to 5 minutes—or longer if refresh fails—the cache can be stale. When checkout requires strong consistency or valid quotes, **verify against the authoritative pricing/quote service** before writing the order snapshot. Caches aid browsing, not unverified financial authority.

### Exercise 6 — Out-of-Order Full-State Events

Source emits:

~~~~text
v1 = 100000
v2 = 110000
v3 = 120000
~~~~

Consumer receives v3 first, then v2; both carry full state and accurate versions.

**Question:** after processing both, what should Search's price be?

**Answer:** **120,000** at `source_version` **3**. The consumer applies newer versions and **ignores stale events**, never trusting arrival order as latest truth. Full-state events converge cleanly here.

### Exercise 7 — Delta Event Missing a Version

Price at v1 is 100,000. Events v2 and v3 each carry `priceDelta = +10,000`. The consumer receives only v3.

**Question:** can it add +10,000 onto v1 and call it v3?

**Answer:** **no**, because delta v2 is missing. Adding only v3 yields 110,000 instead of **120,000**. Detect the **version gap**, replay the missing sequence, or fetch an authoritative full-state snapshot. Full-state and delta streams demand different rules.

### Exercise 8 — Duplicate `eventId` Delivery

A consumer processed `e-100`, yet the relay resends `e-100` after crashing before marking it published.

**Question:** how does the inbox help? Is this immediately a critical relay bug?

**Answer:** the consumer sees `eventId` is already processed and **skips duplicate side effects**. Redelivery is normal under at-least-once delivery; monitor retry rates and root causes without ripping out the outbox. Always commit the inbox inside the same transaction as the projection update.

### Exercise 9 — Committing Inbox Before Projection

A consumer inserts `eventId` into the inbox, COMMITs, and then crashes before updating Search.

**Question:** what happens when the event is redelivered?

**Answer:** the consumer skips the event because it is already in the inbox, leaving Search permanently un-updated! Always **commit inbox and projection in one local transaction** so crashes roll both back for safe retries.

### Exercise 10 — Is `source_version` Alone Enough?

Catalog and Search both report `source_version=2`, yet Catalog shows 120,000 and Search shows 110,000.

**Question:** are both copies converged?

**Answer:** **no.** Equal version with differing prices is **`DIVERGENT_SAME_VERSION`** under a 1:1 contract. Investigate mappings, payloads, write permissions, event collisions, or mismatched restores. Versions govern ordering, not payload correctness.

### Exercise 11 — Is a Lower Version Always a Critical Incident?

Catalog is at v3 while Search sits at v2 for 3 seconds. The contract permits 60 seconds of lag under normal load.

**Question:** should ops manually UPDATE Search immediately?

**Answer:** not necessarily. That may simply be **staleness within SLO**; watch queue drain and convergence. Only investigate and repair if v2 persists past SLO bounds. Never judge lag purely from an instantaneous version gap without checking **elapsed time and contractual freshness**.

### Exercise 12 — Equal Version With Derived Field Differences

`Catalog.title = "A5 Notebook"`, while Search holds `search_tokens = "so tay a5"` after accent stripping and lowercasing.

**Question:** is `search_tokens <> Catalog.title` a bug?

**Answer:** **not automatically**, because `search_tokens` is a **derived transformed field**. Validate it against the **tokenization/normalization rules** and transform version rather than raw string equality. By contrast, a `Search.catalog_title_projection` defined as a 1:1 copy must match verbatim.

### Exercise 13 — Timestamp Polling Without a Tie-Breaker

A job queries `WHERE updated_at > last_timestamp`. P01 and P02 share the same `updated_at`; the job processes P01, stops, and saves that timestamp as its checkpoint.

**Question:** can P02 be skipped?

**Answer:** **yes.** The next run filters strictly `> timestamp` and misses P02. Use a total-order cursor **`(updated_at, product_id)`**, overlap windows with deduplication, or CDC log offsets—while still handling late-committing transactions and deletes. A tie-breaker alone does not cover every source edge case.

### Exercise 14 — Updating Price and Emitting Events in Two Transactions

Catalog COMMITs a new price and then crashes before publishing the event.

**Question:** what is the risk, and how much does an outbox solve?

**Answer:** Catalog holds the new price while Search may **never receive the update** without a replay mechanism. A transactional outbox commits **state + event intent** atomically so a relay can retry. Because outboxes deliver at least once rather than strictly exactly once, consumers still need idempotency.

### Exercise 15 — Rebuilding an Index Under Live Writes

A job scans Catalog from 10:00 to 10:10. The consumer starts reading events only after 10:10. P01 reprices at 10:05.

**Question:** can that update be lost? How do you fix it?

**Answer:** **yes**, if the scan missed the 10:05 edit and the stream starts too late. Bootstrap using a **consistent snapshot aligned with a change-log watermark**, accepting idempotent overlap replays with zero drops, then reconcile against the source.

### Exercise 16 — Deleting a Product Then Receiving a Stale Event

Catalog emits `ProductUnpublished` v4; Search removes the item. Later, a replay delivers `ProductPublished` v2.

**Question:** should Search re-insert the product from v2?

**Answer:** **no.** Event v2 predates the v4 unpublish decision. Consumers must keep **tombstone/version metadata** (or verify against the source) so stale events never resurrect deleted items. Deleting rows without retaining applied version fences invites stale resurrections.

### Exercise 17 — Two Systems Sharing One `paid` Flag

Sales lets staff check `paid=true` manually; Billing records `payment_status=PENDING` because the gateway has not settled.

**Question:** who should own settled-payment authority?

**Answer:** Billing/Payments per the published payment contract. Sales may hold a **projection** yet must never mutate it to declare funds collected. Also check whether the domain needs **`authorized`, `partially_paid`, `settled`, and `refunded`**—a single boolean `paid` drops critical semantics.

### Exercise 18 — Cross-Tenant SKU Collisions

Tenant A sells SKU `NOTE-A5` for 100,000. Tenant B sells SKU `NOTE-A5` for 150,000. A Search sync job keys strictly by `sku` and omits `tenant_id`.

**Question:** how does data corrupt?

**Answer:** both products **collide and overwrite each other** on the same Search record. Key by **`(tenant_id, sku)`** or a properly mapped global `product_id`, and test cross-tenant SKU collisions explicitly. Adding versions fixes nothing when the identity key is wrong.

### Exercise 19 — Two Legitimate Payments With the Same Amount

Payments P100 and P101 are both valid and both equal 100,000 VND. A report runs `SUM(DISTINCT amount)` to prevent double counting.

**Question:** what does the report return, and what should it return?

**Answer:** `SUM(DISTINCT amount)` returns **100,000** instead of the true **200,000 VND**. `DISTINCT` on values erases **two distinct valid events**. Deduplicate by `payment_id`/`eventId`/business key at ingestion instead.

### Exercise 20 — Building Golden Records by Email Alone

CRM and ERP both hold users with `shared@example.org` belonging to two different organizations. ETL merges them into one customer purely on email match.

**Question:** what failure is this?

**Answer:** **false identity merging**: email alone does not prove the same person or legal entity. Define identity rules, source, tenant/organization scope, matching evidence, steward workflows, **unmerge** capability, and **per-field survivorship rules** rather than `SELECT DISTINCT`.

### Exercise 21 — Why Search Need Not Hold a SQL FK to Catalog Everywhere

Catalog runs in a relational DB while Search runs in a dedicated search engine. An architect demands a physical FK from every Search document back to Catalog.

**Question:** is that mandatory or feasible like a single-DB PostgreSQL FK?

**Answer:** no. Cross-database/service boundaries cannot enforce **standard SQL FKs**. Search holds an **external product reference** kept consistent via events/APIs, versions, and reconciliation. Even inside one shared DB where an FK is technically possible, weigh coupling and lifecycle ownership—especially for historical records.

### Exercise 22 — Fresh Timestamp Masking a Lagging Version

`Search.source_version = 2` while `Catalog.version = 3`. A v2 replay updates `Search.synced_at` to "just now," leaving Search's price at v2.

**Question:** can ops report "Search synced cleanly" from `synced_at`?

**Answer:** **no.** A fresh `synced_at` may reflect only a no-op replay, not v3 convergence. Monitor **`source_version`**, consumer lag, and reconciliation—and avoid bumping `synced_at` when stale events make zero actual changes.

### Exercise 23 — Manually Patching a Diverged Copy

Ops spots a wrong price in Search and runs a manual `UPDATE` to 120,000, while Catalog remains at 110,000 and keeps emitting events for P01.

**Question:** is this fix durable?

**Answer:** **no.** The next sync overwrites it back to 110,000. First determine **which value is right per business rules**, fix the authoritative source and emit a valid new version—or if Search's transform broke, fix the consumer and rebuild. Manual target edits require governance and lineage, never creating another competing writer.

### Exercise 24 — Designing a New Copy Contract

A team wants to add a new Search projection and must specify **at least eight contract items** before building it.

**Reference answer:**

1. Purpose and **field semantics** being replicated.
2. **Authoritative source** and owner.
3. **Business key and tenant scope**.
4. Change trigger and **event schema/version**.
5. Full-state vs. delta, plus **ordering/gap policy**.
6. Duplicate and version-regression guards.
7. **Freshness SLO**, breach alerts, and fallbacks.
8. **Delete/tombstone** rules.
9. **Snapshot bootstrap + replay** procedures.
10. **Reconciliation and repair** queries/workflows.
11. Sensitive-data, authorization, and retention rules.
12. Operational owner, metrics, alerts, and decommissioning plan.

Without an authoritative source and clear write rules, adding versions, triggers, or sync jobs merely produces **regularly refreshed wrong copies**.

### Exercise 25 — Classifying When Equality Checks Apply

Customer holds `current_phone`, Order holds `recipient_phone_at_purchase`, and a Search document holds `customer_current_phone`. A tester proposes asserting all three always match.

**Question:** which assertion is valid, and which is semantically wrong?

**Answer:** if `Search.customer_current_phone` is an **authorized copy** of `Customer.current_phone`, reconciling them (accounting for version/freshness, permissions, and identity scope) is valid. By contrast, **`recipient_phone_at_purchase`** was captured for that order at purchase time and may differ from current profile phone or even belong to a different recipient. Never force all three equal—verify **entity, role, point in time, and privacy rules** first.

### Exercise 26 — Failure-Testing Outbox and Inbox

Catalog commits state + outbox. Relay sends the event successfully, then crashes before marking published. Search processes the event, and on restart the relay sends it again.

**Question:** which invariants ensure the system stays correct?

**Answer:** (1) State and outbox **commit atomically** in Catalog; (2) the relay **re-emits** safely without losing events; (3) Search uses inbox/`eventId` plus business versions to **block duplicate side effects**; (4) inbox and projection commit atomically together; (5) crashes mid-consumer roll back cleanly for retry; (6) monitoring alerts on stuck outbox rows or non-convergent projections.

### Exercise 27 — Should Last-Write-Wins Apply Everywhere?

A stale offline update from yesterday arrives late and overwrites a price just approved in Catalog.

**Question:** is arrival-time LWW valid here?

**Answer:** not by default. **Later arrival** does not mean **newer business intent**, and clocks can skew. When Catalog is authoritative, enforce Catalog's version/concurrency contract. With true multi-writer scenarios, use **business-approved conflict resolution**—LWW risks silent lost updates and is unfit for prices, money, or permissions.

### Exercise 28 — Full Remediation Plan for Diverged Data

Catalog holds 50,000 products; Search holds 49,500; 300 prices disagree. Search admins can still edit prices directly, and a nightly full-copy batch job frequently aborts mid-run.

**Question:** outline priority steps to bring the system into a verifiable state.

**Reference answer:**

1. Declare **Catalog authoritative** for current list prices and semantically shared fields.
2. Inventory all writers/readers and revoke direct Search admin price edits.
3. Lock down business keys, mappings, versions, currency, unpublish policies, and effective timing.
4. Build a reliable change stream (outbox/CDC or equivalent), idempotent consumers, and version guards.
5. Bootstrap Search from a snapshot anchored to a **log position/watermark** so zero live changes are dropped.
6. Reconcile the **500 missing**, same-version price diffs, orphans, and out-of-scope records.
7. Quarantine unmapped rows or same-version payload conflicts; **never pick a side blindly**.
8. Canary and cut over against SLOs while monitoring lag, outbox depth, errors, and Search state.
9. Retire the legacy batch job or repurpose it into governed reconciliation/repair.
10. Maintain ownership, replay, delete/tombstone, and access-control procedures.

Never begin by updating the 300 mismatched rows to match an arbitrary table while **competing write paths remain open**, or divergence will return immediately.

## 17. Summary

| Topic | Key Principle |
| --- | --- |
| **Data redundancy** | Valid when purpose and semantics are explicit |
| **Core anti-pattern** | Multiple copies of current truth with unclear authority or sync rules |
| **Source of truth** | Defined per field, context, ID, tenant, and point in time |
| **Snapshots** | Freeze locked names/prices; never converge to live catalog state |
| **Projections / caches** | Derived read copies of an authoritative source needing freshness contracts |
| **Denormalization** | Intentional trade-off requiring update-anomaly controls |
| **Full-state events** | Converge via latest version when payloads are complete |
| **Delta events** | Require strict ordering, gap checks, and deduplication |
| **Source versions** | Authoritative per-aggregate sequence, never arrival timestamps |
| **Outbox** | Commits state + event intent atomically in source transaction |
| **Inbox / idempotency** | Prevents duplicate side effects at consumers |
| **Version conflicts** | Same version with differing values must be investigated, never overwritten blindly |
| **Reconciliation** | Separates missing, lagging, divergent, deleted, and distinct-meaning snapshots |
| **Tombstones** | Preserve delete/unpublish markers so old replays never resurrect items |
| **CDC / batch** | Needs semantic contracts, watermarks, clean bootstraps, and delete handling |
| **Multiple writers** | Valid only with field ownership, merge rules, and conflict resolution |
| **Freshness SLOs** | Lag must be defined, measured, and paired with fallbacks |
| **Data lineage** | Traces source, version, event, timestamp, and transform |
| **Repair** | Fix at the authoritative source or via verified merge workflows |

**Conclusion:** the problem is not that the same value appears in multiple tables or systems; the problem is **copying a current fact when nobody owns its true value and no rules make copies converge**. Clearly separate **historical snapshots** from **refreshable projections**, assign **authoritative sources by field and time**, lock down **business keys, versions, events, idempotency, lag bounds, deletions, and reconciliation**, and then select the right sync mechanism. Good design answers not only "where is the data stored?" but also **"who may edit it, when is a copy fresh enough, and how do we detect and recover from drift?"**
