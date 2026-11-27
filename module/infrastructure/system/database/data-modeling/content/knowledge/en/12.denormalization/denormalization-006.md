# Authoritative Data Sources, Derived Data, and Sync Ownership

## Learning Objectives

After this lesson, you will be able to:

- Identify the **authoritative source (source of truth)** for each business fact, even when the same entity appears across multiple tables or services.
- Distinguish **source data**, **historical snapshots**, and **derived data** by semantics, effective time, and update rules.
- Describe **data lineage**: where a derived value originates, via which transformations, and at which data version.
- Establish a **synchronization contract** covering ownership, triggering events, consistency level, lag bounds, duplicate/out-of-order handling, reconciliation, and rebuild procedures.
- Design a PostgreSQL flow using a **transactional outbox**, monotonically increasing versions, and **conditional upserts** to protect read-serving copies.
- Diagnose when a data mismatch is expected lag versus a contract violation, and identify who owns remediation.

This lesson belongs to the **Denormalization** chapter of **DATABASE_DATA_MODELING**. Translating business requirements into clear data models requires more than picking entities, relationships, keys, indexes, and physical schemas. Whenever data is copied across relational, document, graph, or analytical models, the design must state **where truth resides, who is responsible for keeping it accurate, and how the system verifies it**.

## 1. One Product, Multiple Records: Which Place Decides the True Value?

Suppose an e-commerce system stores data in the following places:

| Storage Location | Data | Purpose |
| --- | --- | --- |
| **catalog_products** | Current product name and list price | Catalog management |
| **product_cards** | Display name and price in search listings | Fast reads, avoiding cross-service calls |
| **order_items** | Name and price locked at order confirmation | Historical transaction proof |
| **daily_sales_summary** | Daily aggregated quantities/sales totals | Reporting and dashboards |

All four places may hold a product name string or a monetary amount. Yet they **do not answer the same question**:

- **catalog_products.current_price** answers: what is the current list price?
- **product_cards.current_price_display** answers: what version of the display price has been synced?
- **order_items.unit_price_at_confirmation** answers: what price was accepted when locking the order line?
- **daily_sales_summary.sales_amount** answers: what is the total value under the agreed **reporting definition** and **reporting period**?

When the list price changes from 150,000 to 180,000 VND, the **product_cards** copy must be refreshed; **order_items** on confirmed orders must retain the old price; **daily_sales_summary** must generally not be rewritten with the new list price. If all four were "synced to match," the system would corrupt business truth.

> **An authoritative source is always tied to a fact with specific semantics and time scope.** No single table is automatically the source of truth for every interpretation of "product price."

## 2. Authority Is Decision Ownership, Not Just Storage Location

An **authoritative source** is the component empowered to determine the true value of an attribute under a business contract. That component typically also owns the corresponding write rules and constraints.

Distinguish three concepts:

1. **Authoritative source:** the place authorized to change a business fact. For example, the catalog service owns list names; a pricing service may own customer-segment prices.
2. **Copy or projection:** data generated from the authoritative source to serve an access pattern, API, cache, or external system. It must refresh or rebuild according to contract.
3. **Independent historical fact:** a price or address recorded when confirming a transaction. Once committed, the transaction record itself becomes authoritative for what was confirmed, even though the initial value came from live tables.

Having a database primary and replica does not make the primary the **business source of truth for every attribute**. Primary/replica describes infrastructure storage and replication. Business authority defines **who is allowed to define and mutate truth**.

Likewise, "single source of truth" does not force an entire company into a single database. In a multi-service architecture, different services can own different attribute groups. What matters is that **no two components arbitrarily decide a value with the same semantics**.

### 2.1. Map Ownership by Business Fact

Example:

| Business Fact | Authoritative Source | Derived Locations | Rule When Source Changes |
| --- | --- | --- | --- |
| Current product name | Product catalog | Search index, product cards | Update name per source version |
| Current list price | Authorized pricing/catalog system | Cache, product listings | Refresh or expire within committed lag |
| Confirmed transaction price | Locked order line or transaction receipt | Invoices, order reports | Preserve history; adjust via separate workflow |
| Active user follow relationships | **follows** relationship set | **follower_count** | Increment/decrement accurately or refresh per contract |
| Recognized daily sales | Payment/accounting transactions per metric rules | Summary tables, dashboards | Compute by event, time boundary, and currency |
| Current default address | Customer address book | UI checkout suggestions | Refresh when customer edits/deletes |
| Confirmed delivery address for an order | Approved order/shipping instruction record | Receipts and tracking UI | Keep locked record; apply changes via revisions |

If you do not yet know which component owns the authority over a field, **you cannot design controlled synchronization**. For instance, if both the catalog system and sales system can independently mutate **current_price** without arbitration rules, adding an event queue only propagates conflicts faster.

### 2.2. Authoritative Source vs. Convenient Read Source

An API may read primarily from **product_cards** for performance. That does not make **product_cards** authoritative for list pricing; it remains a read-serving copy.

Conversely, when a customer clicks "Place Order" and the price commits a payment, the write path must validate pricing against the authorized source and quoting rules. You cannot assume a cache that just returned 180,000 VND is sufficient proof for locking a transaction.

## 3. Data Lineage: Every Derived Result Must Trace Back to Its Source

**Data lineage** describes the origin, transformations, and journey of data. A copy is operationally sound when engineers can answer:

- Which **table, event, document, or service** did it originate from?
- Which **attributes and business definitions** were used?
- Which **formula, filters, grain, timezone, and rule version** computed it?
- Which **source version or processing watermark** does it reflect?
- Can it be **recomputed from the source**?
- If data is wrong, **who owns fixing the source and who owns fixing the projection**?

Examples describing derived data:

| Derived Field | Source | Rule | Markers to Store / Observe |
| --- | --- | --- | --- |
| **product_cards.display_name** | **catalog_products.display_name** | Copy current name | **source_version**, projection ingestion time |
| **product_cards.current_price** | Authoritative current price | Copy price and currency; never infer from old orders | Price version, currency |
| **orders.items_subtotal** | Confirmed order lines | SUM(quantity × unit_price_at_confirmation) | Calculation rule, line status |
| **user_stats.follower_count** | Active **follows** relationships | COUNT valid relationships | Transaction watermark or sync checkpoint |
| **daily_sales_summary** | Valid payment events | SUM/COUNT by day and currency | Watermark, timezone, formula version |

A daily monetary total **cannot directly sum different currencies**. A "unique users" metric cannot be built by arbitrarily summing daily **COUNT(DISTINCT)** values. Therefore, lineage must document **semantics and formulas**, not just "from Table A to Table B."

### 3.1. Distinguish Three Kinds of Markers

- **Source version:** version number of a source entity, incremented whenever relevant data changes. Useful for rejecting stale events.
- **Event/checkpoint or watermark:** marker indicating how far a consumer has processed data, common in streaming and analytics. Not all events share one global total order.
- **Business effective time:** when a price, status, or term takes business effect. It may differ from when the system wrote or the consumer received the event.

These three concepts are not interchangeable. An event received at 00:05 may take business effect for a transaction at 23:58 yesterday. A projection having received version 12 of Product A does not mean it has received version 12 of all other products.

## 4. Synchronization Contracts Must Be Expressed as Verifiable Terms

If you choose to denormalize, treat the source and derived data as two sides of **one data contract**.

Example for **product_cards**:

| Contract Element | Illustrative Content |
| --- | --- |
| Data | Product current name, list price, currency, display status |
| Authoritative source | **catalog_products**, managed by the Catalog team |
| Copy | **product_cards**, managed by the Search/Storefront team |
| Identifier | **product_id** |
| Versioning | **source_version**, monotonically increasing per product_id |
| Emission mechanism | Source mutation + transactional outbox in same transaction |
| Ingestion mechanism | Consumer upserts only newer versions; handles duplicate events |
| Consistency level | Eventual consistency for listing pages |
| Lag bound | E.g., max 30 seconds under committed operating conditions |
| When user needs immediate price | Read/validate against price source at transaction confirmation |
| Product deletion | Emit deletion tombstone/version and hide from projection |
| Reconciliation | Compare ID, version, price/name/status fields; classify discrepancies |
| Recovery | Replay outbox/CDC or rebuild from snapshot + event watermark |
| Observability | Lag, backlog, retries, mismatches, missing/orphan record counts |
| Ownership | Catalog team owns source values and events; Search team owns projection/consumer |

Durations and teams in the table are **contract examples**—replace them with your organization's real commitments. Never promise "always accurate" if the consumer actually updates asynchronously seconds later. Nor can you call a pipeline "near real-time" without defining how lag is measured.

### 4.1. Sync Mechanism and Read Guarantees Are Separate Concerns

**Same-transaction sync** can deliver atomic updates when source and copy live in the same database and all write paths obey the protocol. However, it increases write load, locking, complexity, and hotspot risk.

**Asynchronous event sync** decouples write paths from read models, at the cost of potential staleness. You must handle duplicates, out-of-order delivery, lost events, outages, and backfills.

**Caches with TTL/invalidation** are also copies. TTL bounds how long certain stale states linger, yet does not guarantee freshness in all cases; caches can be warmed with stale data or suffer invalidation failures.

**Reading from read replicas** introduces replication lag. That reflects storage-layer replication consistency and affects user behavior, yet does not replace business-level authoritative ownership.

## 5. PostgreSQL Example: One Source of Truth, One Versioned Projection

Consider a minimal model. **catalog_products** is the authoritative source for names and list prices. **product_cards** is a derived table for fast listing API reads; a consumer updates it asynchronously.

### 5.1. Source and Outbox Schemas

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL
        CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    source_version BIGINT NOT NULL DEFAULT 1
        CHECK (source_version >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE product_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id BIGINT NOT NULL,
    aggregate_version BIGINT NOT NULL CHECK (aggregate_version >= 1),
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ,
    UNIQUE (aggregate_type, aggregate_id, aggregate_version)
);
~~~

Assume **each source version emits at most one full-state snapshot event for the projection**. If a system needs multiple events per version, redesign the UNIQUE constraint and versioning scheme accordingly.

**product_outbox** is an intermediate table linking business writes to event emission. It is **not** a message broker on its own. A publisher must poll unpublished rows, dispatch reliably, mark state, and retry failures. The **published_at** column only illustrates publish status; production systems also require worker concurrency control, retry/backoff, and error logging.

### 5.2. Writing Source and Event in the Same Transaction

When updating name and price, use one transaction so events never detach from source mutations:

~~~sql
BEGIN;

WITH changed AS (
    UPDATE catalog_products
    SET display_name = $2,
        current_price = $3,
        currency = $4,
        source_version = source_version + 1,
        updated_at = CURRENT_TIMESTAMP
    WHERE product_id = $1
      AND is_deleted = FALSE
    RETURNING
        product_id,
        display_name,
        current_price,
        currency,
        is_deleted,
        source_version
)
INSERT INTO product_outbox (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    payload
)
SELECT
    $5::UUID,
    'Product',
    product_id,
    source_version,
    'ProductSnapshotChanged',
    jsonb_build_object(
        'productId', product_id,
        'displayName', display_name,
        'currentPrice', current_price,
        'currency', currency,
        'isDeleted', is_deleted,
        'sourceVersion', source_version
    )
FROM changed;

COMMIT;
~~~

Parameters **$1 … $5** are supplied by the application: product ID, new name, new price, currency, and an event UUID. Before committing, verify a row was actually updated; if **changed** is empty because the product does not exist or is deleted, do not report success.

Key property: the **UPDATE** and **outbox INSERT** commit or roll back together. If a source write fails, it never leaves a stray event claiming the price changed. If the commit succeeds while the publisher is down, the event remains safely stored for later dispatch.

Be clear on limits: **an outbox does not automatically yield exactly-once delivery**. A publisher can send a message and crash before marking **published_at**, causing re-delivery. Consumers must still deduplicate.

**Source version** increments inside the UPDATE on the product row; concurrent transactions editing the same row serialize under PostgreSQL row locks. This establishes version ordering **within a single product_id**, not a global total order across all products.

If the same **user command** is retried, running the UPDATE again increments the version again. Use **command-level idempotency keys** when a price change must not execute twice; consumer idempotency only protects the copy from re-applying **the same event**.

### 5.3. Projection Schema

~~~sql
CREATE TABLE product_cards (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    is_deleted BOOLEAN NOT NULL,
    source_version BIGINT NOT NULL CHECK (source_version >= 1),
    projected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

This is a read-serving schema; **product_cards** never independently decides current prices. Reading active cards filters:

~~~sql
SELECT
    product_id, display_name, current_price, currency
FROM product_cards
WHERE is_deleted = FALSE
ORDER BY product_id
LIMIT 50;
~~~

If real queries sort by creation time or ranking, the projection and indexes must carry fields matching the **actual access pattern**; the snippet above only illustrates the read shape.

### 5.4. Consumer Applies Only Newer Versions

Suppose the consumer validates a full-snapshot event and binds its fields as parameters. Upserting into PostgreSQL:

~~~sql
INSERT INTO product_cards (
    product_id,
    display_name,
    current_price,
    currency,
    is_deleted,
    source_version,
    projected_at
)
VALUES ($1, $2, $3, $4, $5, $6, CURRENT_TIMESTAMP)
ON CONFLICT (product_id)
DO UPDATE SET
    display_name = EXCLUDED.display_name,
    current_price = EXCLUDED.current_price,
    currency = EXCLUDED.currency,
    is_deleted = EXCLUDED.is_deleted,
    source_version = EXCLUDED.source_version,
    projected_at = CURRENT_TIMESTAMP
WHERE product_cards.source_version < EXCLUDED.source_version;
~~~

The **WHERE** clause achieves three outcomes:

1. When the consumer receives a **newer** version, the copy updates.
2. When the consumer receives the **same** version again, already-applied values remain untouched.
3. When an **older** event arrives late, it does not overwrite newer values.

This implements **last version wins**, not arbitrary "last arrival wins." It is safe only when **source_version increases monotonically per product_id**, events carry a consistent full snapshot of fields, and no two distinct states share the same version.

Example:

~~~text
Source Product #501:
  v7 = Name A, price 150000
  v8 = Name B, price 180000
  v9 = Name C, price 175000

Consumer arrival order: v8 -> v9 -> v7 -> v9
Final projection:       v9
Duplicate/stale v7/v9:  ignored, never regresses data
~~~

**Important note on deletes:** if a product is deleted at the source, emit **is_deleted = true** with a higher version and retain the **deletion tombstone/version** in the projection long enough. Physically deleting the projection row while older events are still in flight allows a late stale event to re-INSERT the deleted product. In the example schema, the source uses **soft delete** and the consumer retains **is_deleted = true** rows to prevent resurrection. When hard-deleting or pruning tombstones, coordinate around event TTLs and rebuild protocols.

### 5.5. Why Forbid Admin UIs from Editing product_cards Directly?

If an admin screen allows directly updating **product_cards.current_price** without updating the source:

- Listing pages show the new price while product detail pages from the source show the old price.
- The next catalog event overwrites the "manually fixed" price.
- Consumers lose track of who decides prices, and reconciliation turns into an argument over which side is right.

Therefore, business write paths must target **catalog_products** (or the authoritative pricing service). Projections should only be mutated by the designated sync pipeline and controlled recovery tools. Database roles and API permissions must enforce this ownership boundary.

## 6. Synchronization Mechanisms and Their Limits

No single mechanism suits every type of data. Choose based on **required business consistency**, **number of write paths**, and **data store boundaries**.

| Mechanism | When Suitable | Critical Responsibilities |
| --- | --- | --- |
| **Same SQL transaction** | Source and summary/copy share one DB and must match immediately | All INSERT/UPDATE/DELETE paths follow rules, lock control, retries |
| **Trigger / stored procedure** | Centralize updates when multiple writers share one DB | Manage trigger deployment, error handling, deadlocks, write latency, permissions |
| **Outbox + message consumer** | Projection lives in another store, lag is allowed | Atomic outbox writes, relay, dedup/versioning, backlog monitoring, rebuild |
| **CDC from change logs** | Stream DB changes to read/analytics systems | Preserve snapshot watermarks, ordering, schema evolution, deletes |
| **Materialized view / refresh** | Heavy aggregations on a refresh schedule | Freshness bounds, refresh duration, source load, recomputation plan |
| **Cache TTL / invalidation** | Repetitive reads of slowly changing data with staleness policy | Invalidation, authorization, distinguishing cache misses from source truth |
| **Compute on read** | Queries meet SLOs and need exact live source values | Indexes, query shape, pagination, source load |

For example, **available stock used to commit a sale** may require a consistent reservation/decrement workflow at the source. **Informational stock counts shown in listings** can be an event-updated projection. Using that cached listing count to commit orders hands authority to a non-authoritative store.

### 6.1. "Synchronous Write" Does Not Mean "Everyone Reads It Immediately" in Distributed Systems

Updating source and outbox in the same transaction still **has not updated product_cards** in a separate store at commit time. Atomicity covers only **source + outbox**.

If an admin UI must display the new name immediately after saving a rename, options include:

- Read directly from the **authoritative source** inside the admin flow.
- Return **source_version** and wait for the projection to reach that version with a defined timeout and fallback behavior.
- Show optimistic UI confirmation while explicitly indicating public listings are syncing.

Never claim strong consistency simply because the system uses an outbox. Define exactly which readers and when are guaranteed to observe new data.

## 7. Sync Ownership Must Be Assigned Explicitly

A copy typically spans at least four roles: **source team**, **change-emitter team**, **projection owner**, and **operations/verification owner**. In smaller teams one group may wear multiple hats, yet responsibilities must still be documented.

| Activity | Primary Owner | Deliverables |
| --- | --- | --- |
| Defining current name/price | Catalog domain and source owner | Semantics, validation, write permissions, effective fields |
| Incrementing version and writing outbox | Source write-path implementer | Events from every write path, atomic transactions |
| Event format and versioning | Joint agreement between producer and consumer teams | Schema, field meanings, versioning, compatibility policy |
| Applying events and building projection | Search/Storefront owner | Deduplication, ordering, upserts, deletes/tombstones |
| Freshness and read experience | Read API owner with source team | SLOs, lag fallbacks, "updated as of..." labels if needed |
| Data reconciliation | Shared between source and projection owners | Comparison queries, watermarks, classification, remediation workflow |
| Backfill / rebuild | Projection owner, with source providing consistent watermarks | Snapshots, offsets/watermarks, reconciliation before cutover |
| Incidents and alerts | Operations team with designated owners | Lag, backlog, mismatch alerts, runbooks, on-call routing |
| Deletion and access-control changes | Data owner + all consumers | Erase/hide/revoke across all copies per policy |

**Avoid "everyone uses it, nobody owns it."** If one team builds a summary table for reporting and nobody owns updating it when metric formulas change, numbers can drift silently for months while pipelines stay green.

A sync agreement should name **who investigates each failure class**. For example: a publisher omitting a required field is a source-contract bug; a consumer applying an older version is a projection bug; a changed definition of "revenue" requires business and data teams to update formulas, schemas, and backfills together.

## 8. Common Sync Failures and How to Spot Them

| Symptom | Likely Cause | Mitigation |
| --- | --- | --- |
| Source changed, no event emitted | Write path bypassed outbox, or post-commit publish failed | Same-transaction outbox, audit all write paths, reconcile outbox |
| One change applied twice | Publisher/consumer retry without idempotency | Event ID, version checks, deduplication or conditional upserts |
| Newer price overwritten by older price | Out-of-order event delivery | Compare per-entity source version; avoid unconditional updates |
| Deleted record reappears | Hard delete in projection followed by delayed stale event | Retain versioned tombstones or anti-resurrection store |
| Some products update, others do not | Worker crashed mid-batch, pagination bug, missed retries | Progress tracking, idempotency, replay, reconciliation |
| Same version in projection, different price | Mapping bug, transform defect, direct manual edit | Validate payloads, lock down write permissions, rebuild |
| Backfill overwrites new events with old price | Historical snapshot running concurrently with live pipeline | Upsert only on newer version, coordinate snapshot watermark + catch-up |
| Today's metric wrong due to late events | Grouped by ingestion time instead of business effective time | Define business time, watermarks, recompute affected buckets |
| API reads stale data right after write | Eventual consistency projection | Read from source, await version, or surface sync status |
| One field modified by two independent sources | Ambiguous authority, cross-service conflict | Partition field ownership and establish resolution contracts |

A classic mistake is treating **retries** as a complete correctness guarantee. Retries recover from transient faults, but if an operation is **non-idempotent**, retries actively cause double-counted counters or state corruption.

### 8.1. Never Blindly Use "Last Write Wins" by Arrival Time

Suppose two services emit updates for a current address and one arrives late. If the consumer keeps whichever message arrived last, stale state wins. Comparing wall-clock timestamps across two hosts also fails under clock skew and inconsistent timestamp meanings.

Clarify **who has write authority**, **business ordering** (source-issued versions/sequences), and **conflict resolution rules** if multiple writers truly exist. Multi-writer collaboration requires explicit reconciliation semantics; never let late-arriving messages win blindly without business justification.

## 9. Reconciliation: Compare Matching Semantics, Time, or Versions

For **catalog_products** and **product_cards** in our PostgreSQL example, a reconciliation query reading both source and projection looks like:

~~~sql
SELECT
    COALESCE(s.product_id, p.product_id) AS product_id,
    s.source_version AS source_version,
    p.source_version AS projection_version,
    CASE
        WHEN s.product_id IS NULL THEN 'ORPHAN_PROJECTION'
        WHEN p.product_id IS NULL THEN 'MISSING_PROJECTION'
        WHEN p.source_version > s.source_version THEN 'VERSION_AHEAD'
        WHEN p.source_version < s.source_version THEN 'LAGGING'
        WHEN p.display_name IS DISTINCT FROM s.display_name
          OR p.current_price IS DISTINCT FROM s.current_price
          OR p.currency IS DISTINCT FROM s.currency
          OR p.is_deleted IS DISTINCT FROM s.is_deleted
            THEN 'VALUE_MISMATCH'
        ELSE 'MATCH'
    END AS sync_state
FROM catalog_products AS s
FULL OUTER JOIN product_cards AS p
    ON p.product_id = s.product_id;
~~~

Interpreting the results:

- **MATCH:** identical version and checked fields within the query's snapshot.
- **LAGGING:** projection is behind the source version; may be normal within the sync window.
- **VALUE_MISMATCH:** identical version yet differing values; typically indicates mapping bugs, direct projection edits, or inconsistent event emission.
- **VERSION_AHEAD:** projection holds a higher version than the source; investigate source restores, ownership changes, or version resets.
- **MISSING/ORPHAN:** record exists on only one side; check creation/deletion timing, retention policies, and backfill progress.

The SQL above illustrates **two tables inside the same PostgreSQL database**. When source and projection live in separate systems, you cannot simply JOIN them directly; export aligned samples or compare at matching **watermarks/versions** via a controlled verification job.

**Do not count every LAGGING row as an immediate bug.** If the contract allows 30 seconds of lag, measure which records have waited longer than 30 seconds from the relevant commit timestamp; freshly committed events may still be in flight. Comparing versions alone tells you **how many versions behind** a record is, not **how many seconds it has lagged**. Time-lag monitoring requires commit/receive/apply timestamps or reliable checkpoint tracking.

**Likewise, never reconcile historical snapshots against current source tables.** An order's locked-in price does not equal today's list price. Order invariants must check confirmation evidence, pricing formulas, and historical data.

## 10. Freshness, Quality, and Recoverability Are Operational Metrics

A sync contract can define metrics such as:

| Metric | Meaning | Example Alert |
| --- | --- | --- |
| **End-to-end lag** | Time from source commit until copy serves reads | Exceeds declared SLO threshold |
| **Consumer backlog** | Count/age of queued events awaiting processing | Grows continuously or fails to drain post-incident |
| **Retry / dead-letter** | Events failing processing or quarantined | Exceeds normal baseline |
| **Mismatch count** | Records violating contract at checked watermark | Matching version with mismatched price/name |
| **Missing projection** | Source records lacking a valid projection | Exceeds allowed age since source creation |
| **Rebuild duration** | Time to recreate projection to caught-up state | Exceeds recovery time objective |
| **Read fallback rate** | Share of API calls hitting source because projection lagged | Spikes abnormally, threatening source capacity |

Metric definitions must specify **time window, percentile, scope, and sampling method**. "Maximum 30 seconds" is a far stronger commitment than "p95 under 30 seconds"; never conflate the two. If events can be dropped before delivery, tracking lag only on **received** events misses failures: an unpublished outbox row never shows up in consumer metrics. Monitor both the source outbox and delivery pipeline.

When thresholds are breached, owners need a **runbook**: identify where to pause, prevent bad data from being served if necessary, perform controlled replay/repair, re-reconcile, and decide when to reopen read traffic.

## 11. Backfills and Rebuilds Must Not Overwrite Newer Truth

Building a projection initially for millions of products usually requires a **backfill**. Naively copying the source table and then turning on the consumer risks missing events committed between those two steps.

A controlled approach:

1. **Choose a snapshot or checkpoint watermark** aligned with the change stream and record it.
2. **Start capturing changes** at or before that watermark so there is zero gap between snapshot and stream.
3. **Load the source snapshot** into the projection, including each product's **source_version**.
4. **Apply remaining stream deltas** using version-guarded upserts; replaying older events must never regress records.
5. **Reconcile at a consistent watermark**, checking missing records, version mismatches, and tombstones.
6. **Cut over reads gradually**, monitoring latency and correctness with rollback to source reads available.

Example: the backfill reads a product at version 7, while the live consumer has already applied version 9. An unconditional backfill UPDATE would regress the projection back to version 7. Using **ON CONFLICT ... DO UPDATE ... WHERE product_cards.source_version < EXCLUDED.source_version** prevents regression, yet **does not by itself prevent missed events** if the snapshot and stream capture lack a connected checkpoint.

For full rebuilds, build into a new projection, catch up to the same watermark, reconcile, and cut over reads. Truncating and rebuilding a live table in place risks downtime and destroys comparison baselines. Specific mechanics depend on architecture, size, and deployment constraints.

### 11.1. Schema and Transformation Evolution

When the source adds **currency**, changes pricing logic, or renames fields, older consumers may misparse new events. Prepare:

- **Event schema versions**, defining required/optional fields and compatibility rules.
- **Transformation/calculation versions** when a derived metric's formula changes and source versions alone cannot distinguish outputs.
- **Ordered rollouts** for producers and consumers so both old and new versions work during transition.
- **Backfill/recompute plans** for historical data if new formulas apply retroactively.
- **Compatibility and reconciliation checks** before retiring old paths.

Do not confuse a product's **source_version** with an event's **schema_version**. One tracks entity state; the other governs message structure. Analytical pipelines may additionally require **calculation_version** and reporting-period metadata.

## 12. Write/Read Permissions, Data Deletion, and Copy Responsibilities

Sync ownership also spans security and retention:

- **Only the authoritative owner** or authorized write paths may mutate live facts; consumers never write back to the source just because they spot a mismatch.
- **Projections may need narrower read permissions** than source tables. Do not copy phone numbers, addresses, emails, or sensitive fields into search indexes unless the UI requires them.
- **Deletions and visibility changes** must propagate to all copies, caches, exports, and analytical stores within policy bounds.
- **Tombstones** preventing entity resurrection must comply with erasure rules—retaining minimal ID/version metadata rather than full deleted payloads.
- **Event logs and dead-letter queues** also persist copies; retention, access control, and erasure policies apply to them too.
- **Historical snapshots** serving transaction proof follow separate retention and access rules; never mechanically purge or mutate them using live cache rules.

An easily missed bug: a user sets their avatar to private, the main profile hides it, yet the read model continues serving the old URL publicly. Here the projection is not merely "a bit slow"—it violates access control. **Acceptable lag depends on data type and business impact**; not every field shares the same 30-second budget.

## 13. Choosing the Right Strategy by Data Type and Storage Model

| Need | Suggested Source of Truth | Derived Form | What Must Be Verified |
| --- | --- | --- | --- |
| Read-heavy product cards | Authorized catalog/pricing | Card table, cache, search document | Version, price, name, status, lag |
| Order history | Confirmed transaction | May be snapshot fields inside the order | Immutable vs. live price/address edits; revision trail |
| Follower counter | Active follow relationships | Counter on profile or read model | INSERT/DELETE/retry, anti-double-counting |
| Sales dashboard | Payment/sales events per metric rules | Aggregate table, materialized view, warehouse | Grain, currency, business time, watermark, late events |
| Full-text search | Source-managed content | Search index/document | Schema, updates/deletes, access control, rebuilds |
| Graph relationship queries | Authoritative vertices/edges | Derived properties/counters on vertices | Edge add/remove fan-out, depth, metric accuracy |

In **relational models**, foreign keys and transactions maintain certain intra-DB invariants, yet do not automatically refresh copies in other tables without explicit update logic.

In **document databases**, embedding author info into every article speeds up reads while creating **update fan-out** on author renames. The account document may be the authoritative source; embedded fields are projections whenever they must reflect current names.

In **graph databases**, friend counts on user vertices derive from follow/friendship edges. Pre-storing counters requires an authoritative relationship set and accurate edge add/remove rules.

In **analytical systems**, fact/dimension or summary tables require **business effective time**, late-arrival handling, and retroactive-edit rules. Lineage must trace back to source events or documents, not merely to an upstream summary table.

## 14. An Evidence-Based Design Decision Example

Suppose a search page has **240 ms** p95 against a **150 ms** target. After tuning queries and indexes, p95 drops to **162 ms**. The team prototypes **product_cards** with normalized name/price fields for single-read access; p95 drops to **105 ms**.

**The numbers below are purely illustrative for analysis, not a real benchmark.**

| Metric under identical representative load | Source Read + JOIN | Asynchronous Projection |
| --- | ---: | ---: |
| API p95 | 162 ms | 105 ms |
| API SLO | ≤ 150 ms | ≤ 150 ms |
| Sync lag p95 | No separate pipeline | 4 seconds |
| Worst observed sync lag | N/A | 38 seconds |
| UI freshness bound | Price/name ≤ 30 seconds old | Price/name ≤ 30 seconds old |
| Additional cost | Source reads, indexes | Outbox, consumer, copy storage, monitoring |
| Correctness | Live source at read time | Must prove lag and version alignment |

The projection **meets the API latency target**, yet **fails the 30-second max freshness bound** because worst-case lag reached 38 seconds. You cannot approve launch solely on the 4-second p95 sync lag. Tune the pipeline, drain backlogs, split streams, or renegotiate the product freshness contract—then re-measure.

If some fields (like category labels) tolerate 60-second lag while **checkout price** must validate live source truth, serve the two access patterns differently: listings use the projection; checkout confirmation reads the pricing source. **Source of truth and sync contracts must follow per-field semantics and read intent.**

## 15. Pre-Production Checklist for Derived Data

A team can walk through these questions during schema review:

| Question | Required Evidence |
| --- | --- |
| Which business fact does this value answer? | Field definition, status scope, and effective timestamp |
| Who has authority over the true value? | Per-field/aggregate source of truth, write permissions |
| Why is a copy needed? | Access pattern, baseline metrics, SLO |
| How is the derived value computed? | Formula, filters, grain, units, locale/timezone |
| How stale may the copy become? | Consistency/freshness contract and measurement method |
| How are source changes emitted? | Transaction/outbox/CDC across every write path |
| What if events duplicate or arrive out of order? | Event IDs, source versions, idempotent consumer |
| How are deleted records handled? | Tombstones, access control, retention |
| Who operates the projection? | Consumer owner, alerts, runbook |
| How do we detect drift? | Reconciliation at matching versions/watermarks, metrics |
| How do we rebuild? | Snapshot/checkpoint, replay, regression guards |
| What happens on schema/formula changes? | Event schema version, calculation version, backfill |
| Which decisions may rely on this result? | Distinguish reference display from confirmation-critical workflows |

**Do not denormalize** if querying the source already meets targets at acceptable cost. Adding a copy that speeds up reads without clear sync ownership often costs far more in incident remediation than it saves.

## 16. Case Studies

### Scenario A — Two Places Editing Price

Catalog owns **current_price**, yet the sales admin UI also allows directly editing **price_display** on product_cards. This morning Catalog set 180,000 VND; in the afternoon sales staff edited the copy to 175,000 VND. Later, the consumer receives a 180,000 VND event and overwrites it.

**Question:** Which source contract rule was violated? How should write paths change?

### Scenario B — Duplicate and Out-of-Order Events

A product has name versions: v5 = "Blue Shirt", v6 = "Ocean Shirt". A consumer receives v6, v5, v6 due to retries. Using an unconditional UPDATE makes the final name depend on arrival order.

**Question:** What metadata must be stored and what condition must guard event application?

### Scenario C — Deleted Record Resurrected

The search projection hard-deletes a product upon receiving **ProductDeleted v9**. Later, **ProductUpdated v8** is redelivered and the consumer INSERTs the product back into the projection.

**Question:** Why did this happen, and what are two patterns to prevent data resurrection?

### Scenario D — "Wrong Data" or "Still Syncing"?

Source has product #501 at version 21; projection is at version 20. The team set a 30-second lag limit. Someone runs reconciliation and sees the version gap.

**Question:** Is that enough to declare a bug? What additional evidence determines whether the contract was violated?

### Scenario E — Historical Shipping Address

A customer confirmed delivery to Address A, then updated their address book to B. A "drift-repair" job spots **order.ship_to_address** differing from **customer_addresses.current_address** and updates the old order to B.

**Question:** Where is the job wrong? Should historical snapshots and current projections share the same reconciliation suite?

### Suggested Solutions

1. **A:** Catalog is authoritative for list prices, while **product_cards** is strictly a copy. Stop editing the projection directly; route UI edits through the authorized source. If separate promotional/sales pricing rules exist, model a distinct price source or explicit precedence rules before projecting.
2. **B:** Store per-product **source_version** and apply events only when the incoming version is **strictly greater than** the stored version. This drops stale and duplicate events. Alert on contract violations if two events share the same version with differing payloads.
3. **C:** Hard deletion erased the stored version needed to reject v8. Either **retain a versioned tombstone / is_deleted row at v9** or record deletion watermarks in a separate guard store; align tombstone retention with event lifetimes and rebuild procedures.
4. **D:** Not enough; a version gap can be normal sync lag. Check commit timestamp / unapplied event age, consumer checkpoints, retry counts, and whether the 30-second bound is a strict maximum or a percentile. Declare a breach only against exact contract terms.
5. **E:** The job applied the wrong semantics: the confirmed address is a **historical fact**, not a copy of the current default address. Never reconcile them to match. Verify snapshots against order confirmation evidence/approved revisions; reconcile current projections against live sources within lag bounds.

## 17. Takeaways

**An authoritative source is the authority over a business fact; derived data is a representation built for a read or aggregation need.** Historical snapshots may match current data at capture time yet follow an entirely different change contract afterward.

Every copy must answer: **"Where does it come from, who owns it, which version is applied, how much lag is allowed, and can it be reconciled and rebuilt?"** Without those answers, adding tables or columns for read speed increases model risk.

Sound design preserves **performance, semantics, and evolvability**: authoritative sources, traceable lineage, contract-bound consumers, clear freshness expectations for users, and operators equipped to detect and repair drift.
