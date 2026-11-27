# Copying Display Attributes to Reduce Joins

## Learning Objectives

After this lesson, you will be able to:

- Recognize when to consider copying a **display-only** attribute—such as a category name, author name, status label, or avatar—into a read structure.
- Distinguish **current** display attributes from **point-in-time transaction** snapshots, as the two follow different update rules.
- Measure the real benefit of eliminating a JOIN against the cost of maintaining copies on the write path.
- Choose an appropriate synchronization strategy: same transaction, trigger, asynchronous events, or a dedicated read model.
- Design a source of truth, update mechanism, reconciliation, backfill, and monitoring so that copies remain verifiable.

In the **Denormalization** chapter of **DATABASE_DATA_MODELING**, the goal is not merely to make one query fast. The goal is to translate business requirements into a clear model of entities, relationships, constraints, and physical schemas; knowing when relational, document, graph, or analytical models can serve the access pattern well while remaining easy to evolve and verify.

## 1. Scenario: Product Page Needs the Category Name

Suppose an e-commerce page displays 40 product cards. Each card includes:

- Product ID and name.
- Current display price, thumbnail image.
- Category name such as "Stationery."
- Additional labels such as "New" or "Best Seller."

In a normalized relational model, products store **category_id** and the category name lives in **categories.display_name**. When building cards, the query joins **products** with **categories**:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.display_price,
    c.display_name AS category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.is_active = TRUE
ORDER BY p.created_at DESC, p.product_id DESC
LIMIT 40;
~~~

A common proposal is to add **products.category_name_display** to skip the JOIN:

~~~sql
SELECT
    product_id,
    product_name,
    display_price,
    category_name_display AS category_name
FROM products
WHERE is_active = TRUE
ORDER BY created_at DESC, product_id DESC
LIMIT 40;
~~~

The second query looks simpler. However, **dropping a JOIN does not automatically make the system noticeably faster**. If you only fetch 40 product rows and each joins a single category via an indexed primary key, the JOIN can be extremely cheap. Meanwhile, copying the category name forces every rename to update all related products, or else accept stale display results.

Therefore, the design question is:

> Is the read-cost reduction large and frequent enough to offset synchronization, storage, and stale-data risks?

## 2. From Display Needs to a Data Contract

A **duplicated display attribute** is a value belonging to one entity that is stored alongside another entity to serve reads. For example:

| Source Attribute | Display Copy | Purpose |
| --- | --- | --- |
| **categories.display_name** | **products.category_name_display** | Render product cards without joining categories |
| **authors.public_name** | **article_cards.author_name_display** | Render article listings |
| **brands.logo_url** | **product_cards.brand_logo_url** | Render product cards from a single read model |
| **stores.display_name** | **search_documents.store_name** | Search, filter, and sort by store details |
| **users.avatar_url** | **comment_cards.author_avatar_url** | Return author info alongside comment lists |

This list merely illustrates data shapes; it does not mean all of these attributes should be copied. **Logos, avatars, usernames, private fields, and attributes used for business decisions** carry different update, access-control, and revocation risks.

Before adding a column, establish four things:

1. **Source of truth:** which field defines the correct value? For the current category name, that might be **categories.display_name**.
2. **Semantics:** is the copy the current value, a periodically refreshed value, or a point-in-time event snapshot?
3. **Consistency window:** after a rename, must the copy be accurate immediately after the transaction or can it lag by a few seconds/minutes?
4. **Verifiability:** can you measure how many copies are stale, mismatched, or awaiting rebuild?

If the team has not agreed on these four points, adding the column introduces **uncontrolled redundancy**, even though the read SQL looks shorter.

### 2.1. Distinguish Current Display Data from Historical Data

Compare:

- **products.category_name_display**: if it means "current category name," when **categories.display_name** changes, the copy **must update** within the committed time bound.
- **order_items.product_name_at_purchase**: if it means "product name confirmed at purchase," when **products.product_name** changes, the name on past orders **must stay unchanged**.
- **article_cards.author_name_display**: could mean the author's current name or the name at publication time; pick one meaning before designing synchronization.

Two fields holding the exact same string do not necessarily represent the same business fact. Model quality must be judged by **semantics and data lifecycle**, not merely by how many times a value appears.

## 3. Normalized Model as a Starting Point

A simple PostgreSQL schema:

~~~sql
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    display_version BIGINT NOT NULL DEFAULT 1
        CHECK (display_version >= 1)
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL REFERENCES categories(category_id),
    product_name TEXT NOT NULL,
    display_price NUMERIC(14, 2) NOT NULL
        CHECK (display_price >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_active_created
    ON products (is_active, created_at DESC, product_id DESC);
~~~

**categories** stores the current category name. **products.category_id** models many products belonging to one category. **display_version** increments whenever a category's display attributes change; it becomes useful if an event-driven read model is needed later.

In PostgreSQL, the primary key automatically provides an index for looking up **categories.category_id**. A foreign key on **products.category_id** does not automatically create an index on the referencing side; if workloads frequently filter, bulk-update, or JOIN on that column, benchmark and consider adding a dedicated index. Do not blindly create indexes just because a column appears in a JOIN.

Example candidate query that selects products first and then joins categories:

~~~sql
WITH recent_products AS (
    SELECT
        product_id,
        product_name,
        display_price,
        category_id,
        created_at
    FROM products
    WHERE is_active = TRUE
    ORDER BY created_at DESC, product_id DESC
    LIMIT 40
)
SELECT
    p.product_id,
    p.product_name,
    p.display_price,
    c.display_name AS category_name
FROM recent_products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
ORDER BY p.created_at DESC, p.product_id DESC;
~~~

This query limits to 40 products before the JOIN. The optimizer can choose an appropriate execution strategy; evaluate with **EXPLAIN (ANALYZE, BUFFERS)** on real data rather than guessing from SQL syntax.

Note: the query uses **INNER JOIN** because the **category_id** foreign key enforces a valid category within this model's scope. If the application allows uncategorized products, NULL handling and the JOIN type must be redesigned.

## 4. When Is Copying a Category Name Likely Useful?

Copying a small attribute yields clear benefits only when it aligns with how data is served. Typical contexts include:

- **Extremely high-frequency listings:** an API returning hundreds of cards under heavy traffic where, even after index and query optimization, join/lookup cost remains a measured bottleneck.
- **Read models in a separate store:** a search index or projection table that must return full display payloads without joining directly against the transactional database.
- **Data already grouped as an aggregate/document:** the application routinely reads the same bundle of attributes, and update rules allow maintaining them within that boundary.
- **Cross-service API aggregation:** when rendering a screen requires calls across multiple services, a consolidated read model can reduce network latency and call count.
- **Analytical queries:** names or labels stored in reporting context with clear data watermarks and effective-date history.

Conversely, with a category table of dozens or hundreds of rows and a screen fetching 40 products, a primary-key JOIN is often far too cheap for duplication to deliver meaningful gains.

**Never use a copied display value as the source for business decisions** that require strictly current values. For example, a category name may lag by a few seconds on a search page, whereas checkout pricing, permissions, account status, or inventory at order confirmation must follow authoritative source and consistency rules.

## 5. Option A: Copying Directly in the Relational Table

Suppose measurements prove join overhead must be reduced, and operations chooses synchronous updates. You can extend the schema:

~~~sql
ALTER TABLE products
ADD COLUMN category_name_display TEXT;
~~~

Be explicit: this is a **derived read-serving column** and must never be edited by administrators independently of **categories.display_name**.

### 5.1. Renaming a Category in the Same Transaction

At an illustrative level, a rename operation updates both places:

~~~sql
BEGIN;

UPDATE categories
SET display_name = 'School Supplies',
    display_version = display_version + 1
WHERE category_id = 10;

UPDATE products
SET category_name_display = 'School Supplies'
WHERE category_id = 10;

COMMIT;
~~~

Because both run inside one PostgreSQL transaction, if either statement fails and the transaction rolls back, both source and copy roll back together. After commit, readers under appropriate MVCC rules observe the updated state.

However, this snippet alone **does not guarantee all copies stay accurate**: the system also creates products, moves products between categories, runs bulk imports, applies admin edits, and executes concurrent requests. All paths must obey one protocol.

### 5.2. Controlling Concurrency When Creating Products

An easy-to-miss race condition:

1. Transaction A renames a category.
2. Transaction B concurrently creates a product and reads the old category name.
3. Transaction A updates existing products and commits.
4. Product B appears with the stale category name.

Row locking on the category row can coordinate this gap. For instance, the **product creation** path reads and holds a **FOR SHARE** lock on the category within the same transaction, while the **rename** path updates the category row and thus waits per PostgreSQL row-locking rules:

~~~sql
BEGIN;

WITH selected_category AS MATERIALIZED (
    SELECT category_id, display_name
    FROM categories
    WHERE category_id = 10
    FOR SHARE
)
INSERT INTO products (
    product_id,
    category_id,
    product_name,
    display_price,
    category_name_display
)
SELECT
    501,
    category_id,
    'HB Pencil',
    12000.00,
    display_name
FROM selected_category;

COMMIT;
~~~

This illustrates an **INSERT** pattern in PostgreSQL under **READ COMMITTED** isolation. Changing a product's **category_id** must likewise read and lock the target category under matching rules. Standardize lock acquisition ordering, handle deadlocks/retries, and ensure no write path bypasses the protocol.

In practice, a tested stored procedure/trigger or a single service owning all write paths can be easier to govern than expecting every API endpoint to remember every step. **Foreign keys only guarantee the category exists; they do not automatically sync duplicated names.** Nor is a single transaction sufficient if other writers bypass the protocol.

### 5.3. The Cost of Renaming

If a category contains a huge number of products, **UPDATE products** can touch vast numbers of rows, generate heavy WAL, acquire locks, spike I/O, and slow down writes. Even a rarely changing category name can trigger a massive write burst whenever it does change.

Think of it as:

> **Update fan-out = number of target records affected by a single source change.**

Fan-out is critical in the trade-off: a JOIN reading 40 rows by primary key may be cheap, whereas one rename triggering updates across millions of products is very expensive. If immediate consistency is required and fan-out is huge, consider keeping the JOIN or changing the read architecture.

## 6. Option B: Separate Read Model, Asynchronous Sync

Suppose the search page uses a separate read store (**product_cards**, search index, or document store). Each record holds everything needed to render a product card:

~~~text
product_cards
├── product_id
├── product_name
├── display_price
├── category_id
├── category_name_display
├── category_display_version
└── projection_updated_at
~~~

**products** and **categories** remain the business source of truth in the transactional database. **product_cards** is a rebuildable projection.

When products are created or edited, the projection is populated from source data. When a category is renamed, the system emits an event such as:

~~~json
{
  "eventType": "CategoryDisplayNameChanged",
  "categoryId": 10,
  "displayName": "School Supplies",
  "displayVersion": 14
}
~~~

The event processor can enforce these rules:

1. Update only records that still belong to the event's **categoryId**.
2. Accept updates only if the version is newer than the stored **category_display_version**.
3. Handle duplicate events idempotently without altering already-correct state.
4. Track progress, errors, retries, and replica age.
5. Support event replay or full projection rebuild from the source of truth.

Example of applying an event to a PostgreSQL projection:

~~~sql
UPDATE product_cards
SET category_name_display = 'School Supplies',
    category_display_version = 14,
    projection_updated_at = CURRENT_TIMESTAMP
WHERE category_id = 10
  AND category_display_version < 14;
~~~

In this example, the category's **display_version** must increase monotonically on every display-name change. When a product moves to a different category, the projection must also update **category_id**, name, and version together; the **WHERE category_id = 10** guard prevents an old category's event from overwriting a product that has already moved. To handle overlapping changes to the same product, add product-level event versioning or per-product event ordering.

**Guaranteed event emission:** if the DB commit succeeds but event publishing fails, the projection can stay stale indefinitely. Use a transactional outbox in the source database with a worker forwarding events to the processor. Even with an outbox, the system must handle duplicate, delayed, and out-of-order events, as well as recovery after outages.

**Freshness:** if the UI permits stale category names for at most 30 seconds, measure end-to-end latency from source commit to projection update—not just the execution time of the UPDATE statement. During multi-product updates, some cards may reflect changes before others; never promise simultaneous instant updates across all records if the architecture cannot guarantee it.

### 6.1. Why Are Versions Better Than Timestamps Alone?

Events can arrive out of order. If "Name A" was emitted before "Name B" yet "Name A" arrives later, an unconditional update will overwrite the newer name with the older one.

A monotonically increasing **per-category** version number lets you discard stale events:

~~~text
Category #10 source:
  v12: Stationery
  v13: Office Supplies
  v14: School Supplies

Worker receives in order v14, v13:
  receives v14 => updates projection to v14
  receives v13 => ignores because 13 < 14
~~~

A standalone timestamp is vulnerable to clock skew across hosts, formatting differences, and how change instants are captured. Sequence versions generated at the source make comparison rules unambiguous. You still must prevent two writers from emitting the same version number with different payloads.

## 7. Option C: No Duplication, Optimize Query and Returned Data Instead

Before duplicating data, verify whether read cost actually lies in the JOIN.

### 7.1. Optimizations That Are Often Sufficient

- **Select only displayed columns:** avoid SELECT * and returning large descriptions, blobs, or rarely used attributes.
- **Bound the product set before joining:** use selective filters, ORDER BY, and a tight LIMIT.
- **Indexes supporting filters/sorting:** tailor indexes to the real access pattern; confirm with execution plans.
- **Eliminate N+1 queries:** load products and categories in set-based queries rather than fetching each category individually from application code.
- **Stable pagination:** keyset pagination reduces cost on deep pages, depending on UI needs.
- **Small category cache:** cache by **category_id** with expiration or change-driven invalidation if the freshness trade-off is acceptable.

An application can also fetch 40 products and then load categories via a single **WHERE category_id IN (...)** query, assembling results in application memory. This avoids long-lived duplication in the products table. However, it adds a network round-trip, so benchmark it against a direct JOIN rather than assuming it is faster.

### 7.2. Measure the Execution Plan

PostgreSQL example:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.product_id,
    p.product_name,
    c.display_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.is_active = TRUE
ORDER BY p.created_at DESC, p.product_id DESC
LIMIT 40;
~~~

When reading output, focus on:

| Observation | What to Verify |
| --- | --- |
| **Nested Loop + Index Scan** for categories | Can be completely optimal when fetching just 40 products with PK lookups |
| **Seq Scan** on products scanning many rows | May indicate a missing index, low filter selectivity, or planner estimating a table scan is cheaper |
| **Sort** over large row counts | May need a composite filter + sort-order index or earlier filtering |
| **actual rows** far from estimate | Check statistics, data skew, and plans under representative parameters |
| High **shared hit/read** | Analyze block reads and cache utilization rather than inferring network time directly |
| JOIN node time is tiny relative to total API | Look elsewhere: other queries, serialization, network, N+1, or rendering |

**EXPLAIN (ANALYZE)** executes the query for real. A SELECT example works safely in test environments, though instrumentation adds overhead. Optimizer **cost** is not milliseconds; compare real measured times, resource usage, and overall API latency.

## 8. Comparing Options with Access Patterns and Metrics

Suppose the normalized model serves 40 products/page. The team sets **API p95 ≤ 160 ms**, allows category names on listing pages to lag up to **30 seconds**, while admin screens require immediate accuracy after a rename.

**The table below uses hypothetical numbers to illustrate decision-making, not an executed benchmark.**

| Metric | Optimized JOIN | Copy in products, Same-Transaction Sync | Asynchronous Projection |
| --- | ---: | ---: | ---: |
| Product list API p95 | 118 ms | 109 ms | 83 ms |
| Read SLO ≤ 160 ms | Pass | Pass | Pass |
| Category name after commit | Reads source at query time | Accurate post-commit if all writers comply | May lag within sync window |
| Renaming a category with many products | Updates source row | Can trigger massive row writes and locks | Offloads work to pipeline and read store |
| Extra operational cost | Minimal | Sync logic + reconciliation | Outbox/events, projection, lag monitor, rebuild |
| What must be verified | Actual cost of the JOIN itself | Write p95/p99 during renames, concurrency | End-to-end lag, backlog, replay |
| Suitable for admin UI needing immediate name | Yes | Yes if consistency rules hold | Only if admin reads source or waits for sync confirmation |

Conclusions under these assumptions:

- **Optimized JOIN** meets the target, keeps the model simple, and stays consistent with the source. It is likely the best choice for standard listing screens.
- **Direct copy in products** saves an extra 9 ms at read p95 while adding heavy write overhead on renames. You need strong evidence that this trade-off is worthwhile.
- **Asynchronous projection** cuts read latency further in this example and fits well when a dedicated search/read model already exists and users tolerate lag. You still must measure real end-to-end lag against the 30-second budget.

You cannot infer from a single p95 number that an option wins across all workloads. Test under realistic concurrency, hot/cold data mixes, bulk renames, and categories with huge product counts.

## 9. Costs to Count Beyond SELECT Time

Display values are usually short, yet the number of copies can be massive. Measure:

| Cost Category | How It Arises | How to Verify |
| --- | --- | --- |
| Reads | JOINs, lookups, serialization, network round-trips | API p50/p95/p99, EXPLAIN, queries/request |
| Writes | One source change triggers many UPDATEs or events | Rows modified, write latency, throughput |
| Concurrency | Transactions updating many products hold locks longer | Lock waits, deadlocks, retried transactions |
| Storage | Copy columns, indexes, WAL, search index documents | Table/index size, growth rate |
| Synchronization | Queues, outbox, workers, invalidation | Commit-to-copy lag, backlog, error rate |
| Correctness | Wrong names, stale-event overwrites, category moves | Reconciliation queries, divergent record count |
| Operations | Backfills, bulk renames, projection recovery | Load duration, repair time, rollback capability |

Also consider **localization (multi-language)**. If categories have both Vietnamese and English names, copying a single **category_name_display** column fails to specify which locale it holds. Designs may require **(category_id, locale)** pairs, translation tables, locale-suffixed fields, or per-locale read models. Copy volume and update effort multiply with each supported language; model this before optimizing.

**Privacy and security:** copying author info, avatars, or visibility-controlled attributes multiplies the places that must delete or hide data when users change privacy settings. Display data is not automatically public forever. If using external search indexes or caches, authorization and revocation policies apply to copies too.

## 10. Reconciliation: How Do You Know Copies Are Still Right?

For **products.category_name_display** stored in the same PostgreSQL database with immediate-consistency guarantees, the reconciliation query is:

~~~sql
SELECT
    p.product_id,
    p.category_id,
    p.category_name_display AS copied_name,
    c.display_name AS source_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.category_name_display IS DISTINCT FROM c.display_name;
~~~

**IS DISTINCT FROM** catches cases where the copy is NULL, whereas **<>** fails to flag them because comparisons with NULL evaluate to UNKNOWN. Any returned row means copy and source currently diverge under the definition of current value.

For an asynchronous projection with **category_display_version**, split checks into two categories:

1. **Version lag:** records whose version trails the source. These may be temporary differences within the allowed lag bound.
2. **Same version, different name:** indicates a sync bug or data corruption, because equal versions must imply identical values.

Classification query example:

~~~sql
SELECT
    pc.product_id,
    pc.category_id,
    pc.category_display_version AS copy_version,
    c.display_version AS source_version,
    CASE
        WHEN pc.category_display_version < c.display_version
            THEN 'LAGGING'
        WHEN pc.category_display_version = c.display_version
             AND pc.category_name_display IS DISTINCT FROM c.display_name
            THEN 'VALUE_MISMATCH'
        WHEN pc.category_display_version > c.display_version
            THEN 'VERSION_AHEAD'
        ELSE 'MATCH'
    END AS sync_state
FROM product_cards AS pc
JOIN categories AS c
    ON c.category_id = pc.category_id;
~~~

This query assumes **product_cards** projects current category data and every rename increments the source version. If run while the source is changing, results reflect snapshot timing. When evaluating SLAs, record commit timestamps or event watermarks to determine whether lagging copies have exceeded the threshold.

Distinguish **allowed lag** from **permanent errors**. Alerting rules can track copies lagging past 30 seconds, worker processing failures, non-draining backlogs, and any **VALUE_MISMATCH** at matching versions. Test a recomputation job from the source of truth before an incident occurs.

## 11. Safe Rollout and Rollback Capability

Copying a display attribute modifies both the data model and read/write paths. For systems under continuous traffic, a reference rollout sequence is:

1. **Specify the contract:** name the column clearly as a read copy; document source of truth, semantics, versioning, lag bound, and owner.
2. **Expand schema:** add a nullable column or separate projection table; do not switch reads before populating data.
3. **Enable sync mechanism:** update copies on source mutations, including inserts/updates/deletes, relationship moves, imports, and retries.
4. **Controlled backfill:** populate historical records while preventing stale snapshots from overwriting newer updates.
5. **Reconcile:** verify against the source of truth, testing NULLs, category moves, bulk updates, and concurrent access.
6. **Shadow read comparison:** compare source-query results against the copy on representative datasets; monitor latency and discrepancies.
7. **Gradual read cutover:** roll out progressively; monitor API latency and correctness, keeping a fallback path to the JOIN if needed.
8. **Post-rollout review:** weigh measured read gains against write overhead, sync pipelines, storage, and incidents.

A common pitfall is simply running:

~~~sql
UPDATE products AS p
SET category_name_display = c.display_name
FROM categories AS c
WHERE p.category_id = c.category_id;
~~~

That statement is useful as an **illustrative backfill**, but it does not handle concurrent source changes happening while the backfill runs. With versioned async sync, prevent older records from overwriting newer versions; with strong sync, coordinate locking/transactions and rollout ordering. Batched backfills must also throttle I/O, limit lock duration, and support resuming if interrupted.

## 12. The Same Problem in Document, Graph, and Analytical Models

**Document databases:** a **product_card** document can embed **category.displayName** to serve reads in one fetch. Key questions are rename fan-out, document size limits, whether multi-document updates are atomic, and how long stale names are tolerable. Do not jump from "embedding is possible" to "duplicate every attribute."

**Graph databases:** a **Product** vertex links to a **Category** vertex that holds the name property. If queries already traverse the relationship and return the category name, normalized data may perform fine. Copying the name onto Product vertices enables local access for some queries at the cost of rename fan-out; measure traversal workloads and vertex update costs.

**Analytical systems:** sales reports typically use **fact** and **dimension** tables. If reports need the current category name, join the current dimension at query time. If reports need the category name **at the time of sale**, use a historical model (such as a slowly changing dimension with effective dates) or an explicitly timestamped snapshot. Copying names without timestamps produces incorrect historical reports.

Whether using relational, document, graph, or analytical systems, the core questions remain identical: **is this a current or historical name; where is the source of truth; on a rename, how many records are affected; how long does sync take; and how do we prove sync correctness?**

## 13. Decision Checklist Before Copying Attributes

| Question | Minimum Evidence |
| --- | --- |
| Which screen/read flow does the attribute serve? | API, query, returned fields, traffic volume |
| How much does the JOIN currently cost? | EXPLAIN (ANALYZE, BUFFERS), queries/request, API latency |
| Is there a simpler optimization? | Measurements with indexes, early filtering, batching, caching |
| Is the attribute current state or a snapshot? | Business definition when the source value changes |
| Where will the copy live? | Column in same DB or projection/search/document store |
| Source of truth and owner? | Source table/field, responsible team |
| Allowed lag? | Observable commitment and how lag is measured |
| How many copies are written per source change? | Min/percentile/max fan-out, write cost |
| How are updates synchronized? | Transaction/trigger or outbox/event/version |
| Deletes, relationship changes, retries, late events? | Consistency rules and edge-case tests |
| Detection and remediation? | Reconciliation checks, alert thresholds, rebuild plan |
| Do benefits exceed costs? | Read/write p95/p99, correctness, storage, operations |

A good decision can very well be **not copying** when a JOIN already meets targets. Conversely, a copy is sound design when real workload measurements prove the benefit, semantics are unambiguous, and synchronization is reliable.

## 14. Case Studies

### Scenario A — Small Categories and Short Listing Pages

The **categories** table has 80 rows, and the product page returns 40 cards per request. API p95 with an indexed JOIN is 95 ms against a 180 ms SLO. A prototype adding **category_name_display** reduces it to 92 ms, while categories are occasionally renamed in bulk.

**Question:** Should you maintain a copy in the products table just for a 3 ms p95 reduction?

### Scenario B — Search in a Separate Store

A system has a search index storing millions of product cards. It must display category names and tolerate stale names for at most 60 seconds. Rename events carry **categoryId**, **displayName**, and **displayVersion**, and the same event may be delivered multiple times.

**Question:** What minimum conditions must the handler enforce? From which moment should freshness be measured?

### Scenario C — Author Name at Publication Time

A newsroom requires articles published last year to retain the pen name recorded at publication time, even if the author updates their account display name later.

**Question:** Should you update the author name in old article records whenever profile names change? Why or why not?

### Scenario D — Wrong Copy After Moving Categories

Product P is moved from category A to category B. Later, a worker receives a delayed rename event for A and accidentally writes A's name onto P's record in the search index.

**Question:** Which condition prevents this bug? What else is needed if update events for P itself also arrive out of order?

### Suggested Solutions

- **A:** There is no strong case for copying: the JOIN already meets the SLO, the gain is negligible, and bulk renames create write fan-out. Keep the simpler model unless new measurements demand otherwise.
- **B:** Update only records whose current **category_id** matches the event and whose stored version is less than the new **displayVersion**; handle retries idempotently, monitor backlog, reconcile, and support rebuilds. Measure freshness from **source transaction commit time until the projection is readable**, including event queueing and store indexing.
- **C:** Do not overwrite historical names when publication-time names must be preserved. This is a snapshot with distinct semantics; define the exact capture point and an editorial correction policy if allowed.
- **D:** The handler must check **the product's current category_id** alongside the category version. You also need per-product change versions or per-product event ordering to avoid applying outdated category moves.

## 15. Takeaways

**Copying a display attribute trades JOIN cost on the read path for synchronization cost on the write path.** Decisions must rest on data: query shape, read frequency, joined row counts, update fan-out, p95/p99, write amplification, and required freshness.

If the copy represents **current state**, define the source of truth, cover every write path, handle concurrency, and reconcile. If it is a **historical snapshot**, anchor its timestamp explicitly and never blindly overwrite it with newer values.

The final question before adding any copied name, logo, or label column is: **"How much read cost does it save, how many copies must be updated on every source change, and can we prove every copy matches within our committed freshness bound?"**
