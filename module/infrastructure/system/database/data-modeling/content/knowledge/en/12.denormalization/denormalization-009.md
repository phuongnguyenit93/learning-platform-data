# Bounding Redundancy to Keep Models Explainable and Maintainable

## Learning Objectives

After this lesson, you will be able to:

- Explain why denormalization **does not mean** copying as much data as possible.
- Separate **current business facts**, **historical snapshots**, and **derived values** so multiple places never accidentally share write authority over one attribute.
- Establish bounds on **replication scope, copy count, dependency depth, update cost, lag, and recoverability** for each denormalization decision.
- Design a read model serving a concrete access pattern with an authoritative source, clear field names, versions, ownership, and reconciliation queries.
- Spot models that read fast yet are hard to explain—such as chains of copies-of-copies, tables stuffed with undocumented metrics, or copied fields lacking refresh mechanisms.
- Decide whether to retain, narrow, or remove redundant data using performance benchmarks and maintenance cost evidence.

In the **Denormalization** chapter of **DATABASE_DATA_MODELING**, we learn how to turn business requirements into schemas with clear entities, relationships, keys, constraints, and indexes. Extending into document, graph, or analytical systems, the principle holds steady: **every extra stored piece of data must have a reason, clear semantics, an owner, and a verification method**.

## 1. Intentional Denormalization Needs a Boundary

Suppose an e-commerce system manages **products**, **categories**, **orders**, and **reviews**. Listing pages display product names, prices, category names, and average ratings. A team proposes:

- Copying **category_name** into the **products** table to skip a JOIN.
- Copying **category_name** again into **product_cards**.
- Copying **category_name** into every search document.
- Storing **review_count**, **rating_sum**, and **average_rating** simultaneously across multiple tables.
- Copying **current_price** into order history and auto-refreshing it whenever catalog prices change.

Some reads may speed up, yet hard questions pile up: when a category is renamed, how many places must change? Which review statuses feed **average_rating**? If two places show different prices, which one is right? Why did an old order's price change?

These are signs of **unbounded redundancy without a contract**. Optimizing a single SELECT does not justify spawning multiple versions of the same fact.

Practical rule:

> **Store derived values strictly at the read boundaries that need them, backed by one authoritative source and a proven rebuild path.**

Bounding redundancy does not mean "at most one copy" or "never embed data." Search engines need search documents, dashboards need summary tables, and distributed services need dedicated projections. The issue is that **each copy must have an independent contract and benefits outweighing its costs**.

### 1.1. Four Questions a Newcomer Must Be Able to Answer

When reading a schema without its original author beside them, someone else should be able to explain:

1. **What does this field mean?** E.g., **category_name_current** differs from **category_name_at_purchase**.
2. **Where does it come from?** The authoritative source table/service/event and the formula or transformation rule.
3. **When and by whom is it updated?** Same transaction, async event, scheduled refresh, or immutable historical snapshot.
4. **If wrong, how do we detect and fix it?** Reconciliation, refresh, rebuild, and fallback to safe reads.

If a table cannot answer all four questions, it is not a maintainable denormalized design—even if every API test currently passes.

## 2. Classify Data Before Counting Copies

You cannot bound redundancy merely by counting duplicate column names. Distinguish **semantics** first:

| Data Type | Example | Change Rule | How to Verify |
| --- | --- | --- | --- |
| **Current fact** | **categories.display_name** | Mutated via business decisions at the owning source | Constraints and source change history |
| **Current-state copy** | **product_cards.category_name_display** | Refreshed from source within committed lag | Compare name/version and check lag |
| **Historical snapshot** | **order_items.product_name_at_confirmation** | Retains locked value; edited only via audited workflows | Compare against confirmation receipts/events, not today's name |
| **Aggregated result** | **daily_sales.total_amount** | Computed from valid transactions per grain/formula | Recompute from source for matching period, currency, and status |
| **Intra-row computed value** | **line_total = quantity × unit_price** | Updates from attributes within the same row | Generated column or row-level arithmetic invariant |
| **Ephemeral cache** | Product card payload in cache | TTL/invalidation per contract | Cache timestamp, version, and source cross-check when needed |

An order snapshot is **not** a copy meant to sync with current products. A summary table is **not** a place for users to type arbitrary revenue figures. Misclassification leads to "fixing" discrepancies by syncing historical records until history is corrupted.

### 2.1. Truth Boundaries Belong at the Attribute and Time Level

Saying "the products table is the source of truth" can still be too coarse. Current pricing may belong to a pricing service, display names to Catalog, and accepted transaction prices to Order Management. When multiple systems store **price**, establish precise names and contracts:

- **current_list_price**: currently effective catalog price.
- **product_cards.list_price_display**: versioned display copy of the list price.
- **order_items.unit_price_at_confirmation**: unit price locked at confirmation, immutable by business rule.
- **daily_revenue.net_amount**: metric computed under the published revenue definition, not a list-price copy.

Having multiple **NUMERIC** price fields is not inherently bad redundancy; **letting multiple services independently decide one value with identical semantics** is the major risk.

## 3. Set a "Redundancy Budget" Before Adding Structures

Teams can use a **redundancy budget** as an architectural review tool. It is not a rigid mathematical quota, but a set of concrete constraints preventing designs from sprawling without ownership.

### 3.1. Six Dimensions to Estimate

| Dimension | Control Question | Sign of Exceeding Maintainability |
| --- | --- | --- |
| **Scope** | How many fields does the access pattern actually need? | Copying entire records "just in case" |
| **Copy count** | How many places store the same current attribute? | Each API spawns its own copy without distinct needs |
| **Fan-out** | How many target rows/documents does one source edit touch? | One rename writes millions of documents while users wait |
| **Freshness / consistency** | How stale can the copy get? Who measures it? | "Near real-time" with no numeric bound or metric |
| **Operational cost** | Who handles failures, backfills, schema evolution, replays? | Pipeline exists with no owner or recovery playbook |
| **Measured value** | How much latency/load/round-trips are saved for which flow? | Skipping a JOIN barely moves p95 while write costs jump |

Also inspect **privacy and access scope**: duplicating sensitive fields multiplies leak surfaces, erasure duties, and governance overhead even when CPU cost looks tiny.

**There is no universal rule** like "at most three tables may repeat a column." A search index and a cache might both need the same field because they serve distinct lifecycles and goals. Conversely, **even one** single copy lacking a source of truth or update path is already a design flaw.

### 3.2. Use Fan-Out to Spot Hidden Risk

Suppose:

- A category contains **600,000** products.
- The listing page typically returns **40** products.
- Category names change on average **a few times per month**.
- If the name is embedded in every product document in a search store, one rename can trigger writing **600,000 documents**.

Under a normalized relational model, the listing page can JOIN the category by primary key after bounding to 40 products; read cost may be tiny. Under embedding, the system absorbs writing hundreds of thousands of documents, lag, retries, and reconciliation.

Before copying a field across a **1:N** relationship, measure at least **the distribution of N**: median, p95/p99, and max—not just the mean. A single "hotspot" parent with millions of children can dominate maintenance costs even when most parents have only dozens of children.

Fan-out is more than UPDATE rows; it includes **message counts, index churn, WAL volume, cache invalidations, and rebuild duration**. Counting the byte length of a name string grossly understates real cost.

### 3.3. Prefer Lifecycle-Aligned Copies Over Ad-Hoc Proliferation

A dedicated read model can consolidate fields needed for **one access shape**. If **product_cards** already serves listing pages, do not immediately copy **category_name** into **products**, **product_search_cache**, and **homepage_cards** just because each screen displays the category name.

This is not a ban on specialized optimizations. When a search index needs its own documents or screens have different freshness bounds, adding another projection can be justified—provided **each new copy proves its need via workload evidence, carries its own contract, and updates the lineage map**.

## 4. Find the Real Bottleneck Before Complicating the Model

Seeing a JOIN in SQL is not proof that the JOIN is the bottleneck. Reads can be slow due to:

- Returning too many columns, missing LIMIT/pagination, or failing to narrow rows before joining.
- Missing indexes matching filter predicates and ORDER BY.
- Application-layer **N+1 queries**: fetching 40 products then firing 40 individual category queries.
- Data skew causing poor plans on outlier inputs.
- Serialization, network latency, cache misses, or cross-service RPCs dominating request time.

PostgreSQL example assuming **products(category_id)** and **categories(category_id)**:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    p.product_id,
    p.product_name,
    p.current_price,
    c.display_name AS category_name
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
WHERE p.is_active = TRUE
ORDER BY p.created_at DESC, p.product_id DESC
LIMIT 40;
~~~

Inspect **actual rows**, **actual time**, buffer hits/reads, scan/sort/JOIN operators, and API call counts. Joining 40 rows to a primary-key-indexed category via **Nested Loop + Index Scan** can be completely optimal. Never label a plan bad solely by operator name.

**EXPLAIN (ANALYZE)** executes the query for real; run only in appropriate environments, and remember optimizer **cost** is a relative estimate, not milliseconds. To compare architectures, measure **end-to-end API p50/p95/p99** alongside CPU/I/O, throughput, and write load under representative scenarios.

### 4.1. Order of Investigation

A sound progression for product listings is:

1. Rewrite the query to select only required columns with tight filters and pagination.
2. Verify indexes supporting filters/sorting without creating redundant indexes.
3. Consolidate N+1 queries or batch lookups if the app fires per-item queries.
4. Evaluate caching for slowly changing data if freshness rules allow.
5. Only if targets still fail—or data crosses store boundaries—evaluate projections/denormalization.
6. Re-measure **reads, writes, correctness, freshness, and recovery costs**.

When the normalized option already hits SLOs, **adding no copy** is a valid conclusion and usually yields a far more maintainable model.

## 5. Designing a Bounded Projection: Products and Categories Example

Consider live sources in PostgreSQL:

~~~sql
CREATE TABLE categories (
    category_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    display_version BIGINT NOT NULL DEFAULT 1
        CHECK (display_version >= 1)
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    category_id BIGINT NOT NULL
        REFERENCES categories(category_id),
    product_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL
        CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    product_version BIGINT NOT NULL DEFAULT 1
        CHECK (product_version >= 1)
);
~~~

**categories.display_name** is the authoritative source for current category names. **products.category_id** holds the product–category link. **products.current_price** is the current list price **in this example**; real systems may use a separate pricing engine.

Suppose benchmarks prove a dedicated read model is needed for listings. Add **one bounded projection** carrying only the fields reads require:

~~~sql
CREATE TABLE product_cards (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    current_price NUMERIC(14, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    is_active BOOLEAN NOT NULL,
    category_id BIGINT NOT NULL,
    category_name_display TEXT NOT NULL,
    product_version BIGINT NOT NULL
        CHECK (product_version >= 1),
    category_display_version BIGINT NOT NULL
        CHECK (category_display_version >= 1),
    projected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Do not also add **products.category_name** merely so the projection can read it: the projection can pull the name via JOIN during initialization and stay synced on source mutations. **products** keeps a clean normalized schema; **product_cards** serves as a purpose-built read optimization.

Within the same PostgreSQL instance, initial state derives from a source query:

~~~sql
SELECT
    p.product_id,
    p.product_name,
    p.current_price,
    p.currency,
    p.is_active,
    p.category_id,
    c.display_name AS category_name_display,
    p.product_version,
    c.display_version AS category_display_version
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id;
~~~

This query represents the **projection transformation definition**, not a standalone safe backfill under concurrent writes. Production rollouts require anchored watermarks, non-regressing upserts, catching concurrent deltas, and reconciliation before shifting reads.

### 5.1. Only One Place Modifies Each Current Fact

In this design:

- Renaming a category: writes **categories** and increments **display_version**.
- Updating product name, price, status, or category: writes **products** and increments **product_version**.
- Updating **product_cards**: exclusively via the sync/read-model pipeline, never directly via admin UIs.
- Editing prices on old orders: **never** synced from live catalog prices; transaction prices are distinct historical records.

Write permissions and naming conventions should reinforce this boundary. Letting an admin UI edit **product_cards.category_name_display** directly—only for a worker to overwrite it later—creates two competing authorities with no clean resolution.

### 5.2. Bounding a Category Rename

Suppose a consumer receives a category rename event with **category_id**, **display_name**, and **display_version**; the projection SQL in PostgreSQL runs:

~~~sql
UPDATE product_cards
SET category_name_display = $2,
    category_display_version = $3,
    projected_at = CURRENT_TIMESTAMP
WHERE category_id = $1
  AND category_display_version < $3;
~~~

The version guard stops older events from overwriting newer names, while the **category_id** predicate stops renames from touching products moved to another category. Still, this **does not solve all concurrency**: if a product's category-move event arrives late relative to a rename event, the system needs **product_version** rules and coordinated two-entity snapshots.

A safer pattern in some architectures receives versioned product events, updates **product fields** conditionally on a higher product version, and refreshes category fields from **current source state or a consistent snapshot**. Never claim a single category-version check alone guarantees all product cards stay accurate.

For categories with massive fan-out, updating hundreds of thousands of cards may breach operational limits. Alternatives include:

- Keeping the category JOIN in the relational DB on read.
- Using a small application-tier category cache.
- Maintaining a separate **category display map** keyed by ID in the search stack if engine and query shape permit.
- Accepting an async projection with batched refreshes and measured lag, **if business rules allow**.

No option is free. Each requires measuring read latency, write fan-out, freshness, and recovery.

## 6. Bounding via Data Contracts: Write So Others Can Understand

Every read model deserves a **short, stable, verifiable contract**. Example for **product_cards**:

| Contract Field | Example Value |
| --- | --- |
| Name and purpose | **product_cards** serving product cards on listing pages |
| Grain | One row per **product_id** |
| Authoritative sources | **products** for product fields; **categories** for current category name |
| Transformation rule | Project product attributes and referenced category display name |
| Data scope | Strictly card-rendering fields; exclude full descriptions, customer addresses, private fields |
| Write authority | Projection pipeline only; business apps write strictly to sources |
| Version boundaries | **product_version** and **category_display_version** scoped per entity |
| Consistency | Eventual consistency on listing pages, if accepted |
| Freshness | E.g., stale category name max **30 seconds**; measured end-to-end |
| Deletes / relation moves | Properly hide/remove deleted products; handle **category_id** moves and category hides/deletes |
| Reconciliation | Compare against source at matching watermarks/versions; track missing, extra, and mismatched rows |
| Recovery | Rebuild from source + replay changes from consistent checkpoint |
| Owners | Explicitly assigned source and projection teams |
| Justification | Normalized query missed SLOs under observed workload |
| Retirement conditions | Zero remaining consumers, or simpler solution meets all SLOs |

You do not need a hundred-page spec to have a contract. What matters is capturing **field names, source queries, invariants, freshness bounds, owners, and repair workflows** clearly enough for another engineer to implement, test, and operate.

### 6.1. Naming Conventions That Prevent Semantic Confusion

Prefer role-revealing names:

- **category_id**: foreign reference to a category, not a name copy.
- **category_name_display** or **category_name_cached**: derived display attribute.
- **category_display_version**: source version applied to the copied name.
- **product_name_at_purchase**: point-in-time snapshot at purchase confirmation.
- **review_count_visible**: count of publicly visible reviews; distinct from total submitted reviews.
- **average_rating_visible**: average across valid visible reviews matching the count definition.

Never reuse contextless names like **name**, **count**, or **total** for different meanings. For instance, an order has pre-discount, post-discount, and collected amounts; calling all three **total** across three tables invites reporting bugs even when every SQL query runs cleanly.

### 6.2. Keep Transformation Chains as Shallow as Possible

Hard-to-maintain chain:

~~~text
categories.display_name (source)
       |
       v
products.category_name (copy 1)
       |
       v
product_cards.category_name (copy 2)
       |
       v
search_documents.category_name (copy 3)
       |
       v
cache.category_name (copy 4)
~~~

The problem is not merely having four copies. A bug in **copy 1** cascades downstream; rebuilding the search index may pull from an already-corrupted copy. Operators must trace backward across multiple hops to find the truth.

Whenever possible, derive read models **directly from the authoritative source** or from a contract-governed, verified event/snapshot stream. When scale or architecture demands multi-stage pipelines, enforce clear lineage, checkpoints, telemetry, and source-anchored rebuilds. **Reducing independent transformation hops** usually pays greater maintenance dividends than eliminating one JOIN.

## 7. Bounding Precomputed Metrics: Store Enough to Be Right, Not Every Variant

Redundancy extends beyond copying names. Fields like **review_count**, **rating_sum**, **average_rating**, **one_star_count**, and **positive_rating_percent** also need discipline.

Suppose a product receives **ratings** from 1 to 5 with visibility states. The UI needs **valid review count** and **average score**.

A minimal summary design stores:

~~~text
product_rating_stats
  product_id                 -- grain: one product
  visible_review_count       -- COUNT of visible reviews
  visible_rating_sum         -- SUM of scores across visible reviews
  source_checkpoint          -- how far source events were processed
  calculated_at              -- last update timestamp
~~~

On read, if **visible_review_count > 0**, compute **visible_rating_sum / visible_review_count**; if zero reviews exist, return "unrated" (NULL) rather than forcing 0 when business rules distinguish the two.

PostgreSQL query example:

~~~sql
SELECT
    product_id,
    visible_review_count,
    CASE
        WHEN visible_review_count > 0
            THEN visible_rating_sum::NUMERIC
                 / visible_review_count
        ELSE NULL
    END AS average_rating
FROM product_rating_stats
WHERE product_id = $1;
~~~

Because the average derives directly from **SUM and COUNT**, storing an extra **average_rating** column merely for convenience adds another invariant to maintain. If large-scale sorting/indexing by average rating requires storing it, keep its calculation and refresh tightly synchronized with both source components.

### 7.1. Never "Patch Roughly" When Review Statuses Change

If a visible review is hidden, decrement the valid count by 1 and subtract that exact review's score from the sum. If a review's score changes from 4 to 2, **COUNT stays unchanged** while **SUM decreases by 2**. Handle deletions and restorations symmetrically.

Never increment counts only on **ReviewCreated** while ignoring **ReviewHidden**, **ReviewRestored**, or **ReviewRatingChanged**. Numbers will drift steadily while UI reads stay misleadingly fast.

If updated via async events, enforce **event IDs, ordering/versioning, idempotency, and reconciliation**. If immediate accuracy is required in a single DB, update transactionally while measuring row-lock contention on heavily reviewed products.

### 7.2. Every Added Aggregation Dimension Is a New Commitment

Example daily sales dashboard by day and currency:

~~~text
daily_sales_summary
  business_day
  currency
  order_count
  captured_amount
~~~

The grain is **(business_day, currency)**. Adding **store_id**, **channel**, or **promotion_id** multiplies group counts and alters semantics—define whether a transaction belongs to one or multiple buckets. Duplicating every dimension explodes combinations and inflates write/backfill costs.

**Never add VND and USD directly.** Never sum daily **COUNT(DISTINCT customer_id)** values to estimate monthly unique customers. When deep multi-dimensional history is required, an analytics warehouse, fact/dimension schema, or properly grained pre-aggregation beats piling endless summary columns onto transactional tables.

## 8. Controlling Copies Across Relational, Document, Graph, and Analytical Models

### 8.1. Relational: Fewer JOINs Is Not the Only Yardstick

In relational models, authoritative truth is modeled cleanly with **PK, FK, UNIQUE, CHECK** constraints and dependency-aligned tables. Denormalization introduces extra derived columns/tables for proven workloads.

Bounds to check: are filters well indexed; what local constraints guard the copy; who updates on source INSERT/UPDATE/DELETE; do reconciliation queries exist; and can the copy be retired back to a JOIN if warranted?

A **CHECK** constraint on a derived row cannot verify equality against another table. Foreign keys enforce referential integrity yet **never auto-sync copied names or totals**. Lots of SQL constraints do not automatically equal sound data governance.

### 8.2. Document: Embed Within Aggregate Boundaries, Watch Document Bloat

Embedding order lines inside an order document works well when read and locked together at one event. Embedding **current author names** into millions of article documents creates rename fan-out and leaks stale names after privacy changes.

Evaluate document size limits, unbounded array growth, engine atomic-update boundaries, fan-out distributions, and rebuild paths. When **comments** grow without bound, embedding every comment inside an article document degrades both reads and writes despite eliminating a JOIN early on.

### 8.3. Graph: Copying Properties or Edge Counts Has a Price

In graph databases, **Product – BELONGS_TO – Category** captures the relationship; traversals can read the name off the Category vertex. Copying names onto every Product vertex pays off only when workloads prove substantial gains and rename fan-out is managed. Likewise, **friend_count** on user vertices derives from edges and must handle edge adds/removals and high-degree supernodes.

### 8.4. Analytics: Separate Read Schemas Still Need Lineage to Source

In analytical systems, fact and dimension tables organize data differently from OLTP for scanning and aggregation. Materialized views and summary tables are standard tools, provided you specify **grain, reporting period, timezone, currency, valid time, slowly changing dimensions, and late-arriving data handling**.

A dashboard overloading the word **revenue** for both "cash collected" and "gross ordered value" is impossible to trust regardless of query speed. In analytics, **formula clarity** matters just as much as raw query speed.

## 9. Reconciliation: Catching Drift, Gaps, Orphans, and Regressions

For **product_cards** in the same PostgreSQL DB (for illustration), classify category-field discrepancies:

~~~sql
SELECT
    p.product_id,
    p.category_id AS source_category_id,
    pc.category_id AS copied_category_id,
    c.display_version AS source_version,
    pc.category_display_version AS copied_version,
    CASE
        WHEN pc.product_id IS NULL
            THEN 'MISSING_PROJECTION'
        WHEN pc.category_id IS DISTINCT FROM p.category_id
            THEN 'RELATION_MISMATCH'
        WHEN pc.category_display_version > c.display_version
            THEN 'VERSION_AHEAD'
        WHEN pc.category_display_version < c.display_version
            THEN 'LAGGING'
        WHEN pc.category_name_display IS DISTINCT FROM c.display_name
            THEN 'VALUE_MISMATCH'
        ELSE 'MATCH'
    END AS sync_state
FROM products AS p
JOIN categories AS c
    ON c.category_id = p.category_id
LEFT JOIN product_cards AS pc
    ON pc.product_id = p.product_id;
~~~

**MISSING_PROJECTION**: product exists in source without a card. **RELATION_MISMATCH**: card still points to another category. **LAGGING**: card's category version trails source; may be valid inside the async window. **VALUE_MISMATCH**: versions match yet names differ; investigate mapping bugs, manual edits, or bad events.

This example checks **only category fields**; it does not yet inspect **product_name, price, currency, is_active**, or **orphan** cards whose source products disappeared. Full reconciliation must cover all contracted fields, deletes, and projection-only orphans. Across separate databases, direct JOINs will not work—use a shared-watermark comparison pipeline instead.

**Important:** under 30-second eventual consistency, a trailing version alone is **not enough** to declare a breach. Determining SLA breaches requires source commit timestamps, event/checkpoint watermarks, replica age, and measuring up to actual reader endpoints. Comparing two unaligned snapshots creates false alarms even when the system works fine.

### 9.1. Rebuild From the Source, Not From Another Suspect Copy

When a category name in a search document is wrong, do not blindly copy from **product_cards** into the search index if **product_cards** might also be stale. Trace back to **categories** or verified snapshot events and rebuild through a lineage-tracked pipeline.

A safe backfill workflow must:

1. Pick a reliable snapshot/checkpoint watermark.
2. Load source records alongside each entity's version.
3. Catch up concurrent changes emitted during loading.
4. Guard against older snapshots overwriting newer projection state.
5. Reconcile record counts, payloads, versions, and deletions.
6. Cut over reads progressively with rollback to source reads available.

Merely bumping a version column in one table without tracking where events sit in flight **never proves zero lost updates**. When multiple source entities feed one card, also resolve interleaved ordering between product and category streams.

## 10. Bounding Redundancy with Deployment and Ownership Discipline

One engineer might build a projection in a day; maintenance outlives that engineer. Assign clear roles:

| Role | Responsibility |
| --- | --- |
| **Business owner** | Defines semantics for names, prices, statuses, reporting formulas, and historical snapshots |
| **Source owner** | Guards write permissions, emits changes from every write path, manages versions and event contracts |
| **Projection owner** | Minimizes field scope, handles retries/reordering, controls updates, and maintains rebuildability |
| **Read API owner** | Uses projections within contract bounds, implements fallbacks and freshness indicators |
| **Operations / data reliability** | Monitors lag, mismatches, backlogs; owns runbooks, rebuilds, and incident response |
| **Security / privacy** | Enforces access controls, retention limits, and copy erasure across projections, logs, and events |

A common pitfall occurs when **the source owner changes a field's meaning** (such as what counts as a "valid review") without notifying projection owners. If the schema stays unchanged, consumers keep running and dashboards look healthy while numbers silently break. Contracts therefore need **transformation/formula versioning**, change notifications, and historical recomputation plans.

### 10.1. Pre-Addition Review for Any Derived Column

Short review template:

- **Why?** Which use case and SLO fail today, and when was the baseline measured?
- **What?** Which field, semantics, grain, and authoritative source?
- **Where?** How many copies exist, and can an existing read model serve this?
- **Who?** Who owns the source, the projection, and incident triage?
- **When?** Synchronous post-commit or eventual; what is the exact allowed lag?
- **On change?** How are creates, edits, deletes, relation moves, imports, and retroactive fixes handled?
- **On failure?** How do reconciliation, recovery, rollback, and rebuild work?
- **On retirement?** What signals, metrics, and plan govern removing it?

Missing answers on authoritative source or discrepancy handling are **reasons to pause and clarify the design**, not details to postpone until after deployment.

## 11. Comparing Options by Total Cost

Suppose a product listing screen targets **p95 ≤ 150 ms**. Numbers below are **purely hypothetical** to illustrate decision trade-offs, not real production benchmarks.

| Metric | Optimized Source JOIN | Copy category_name in products | product_cards Read Model |
| --- | ---: | ---: | ---: |
| Listing API p95 | 118 ms | 111 ms | 96 ms |
| Speedup vs. JOIN | Baseline | 7 ms | 22 ms |
| SLO p95 ≤ 150 ms | Pass | Pass | Pass |
| On category rename | Update 1 source row | Update many products | Update cards or rebuild |
| Fan-out risk | Low with PK lookup | High for large categories | High in pipeline if embedded on every card |
| Consistency cost | JOIN query | All write paths + tx/trigger | Consumer/queue/version/lag/reconciliation |
| Accuracy | Source at read time | Accurate only if all writers sync strongly | Depends on contracted freshness |
| Recommended in example | **Keep** | Unnecessary | Insufficient justification for this API alone |

Under these assumptions, **the JOIN already meets the SLO**, so adding a copy is unjustified for this screen alone. A few milliseconds' difference must also be weighed against measurement variance, write load, and operational overhead.

However, if a **separate search engine** must serve card data without direct JOIN access to the source database, a read model can be architecturally necessary even when PostgreSQL JOINs are fast. In that case, draft a **distinct contract** for search documents covering access pattern, freshness, field scope, versioning, access control, and reconciliation—rather than misapplying the comparison table above to reject every read model.

### 11.1. Measure Both Write Paths and Recoverability

Evaluate across all dimensions:

- **Reads:** API p50/p95/p99, throughput, queries/request, CPU, and I/O.
- **Writes:** INSERT/UPDATE/DELETE p95/p99, lock waits, WAL, rows or documents modified per source change.
- **Correctness:** records breaching lag bounds, same-version mismatches, missing/orphan rows, rule violations.
- **Operations:** oldest unpublished event age, backlog, refresh/rebuild times, schema rollout effort.
- **Growth:** behavior as products, reviews, tenants, locales, and fan-out scale up.
- **Sensitive data:** copy footprint, read permissions, and cost of erasing/hiding revoked source data.

Without measuring writes, a copy that speeds up reads can silently become a write bottleneck during bulk renames, price updates, or viral traffic spikes.

## 12. How to Narrow or Retire Existing Redundancy

In long-lived systems, copies accumulate across multiple optimization waves. Retire them systematically rather than deleting columns at random:

1. **Map data lineage:** inventory sources, projections, caches, search indexes, summary tables, and every consumer.
2. **Classify each copy:** current fact, historical snapshot, or derived value. Never delete required historical records merely because they resemble today's live data.
3. **Locate every read/write dependency:** APIs, batch jobs, reports, ad-hoc queries, and external integrations.
4. **Re-benchmark under real load:** can tuned JOINs, indexes, or shared caches meet SLOs without bespoke copies?
5. **Migrate readers by cohort:** cut over to normalized paths or consolidated projections and shadow-compare outputs.
6. **Shut down redundant writers before dropping structures:** verify zero refresh jobs or dashboards still touch the copy.
7. **Drop after verification:** execute a reversible migration while monitoring error rates and source load.

Consolidating summary tables demands special care around **grain**. Two tables with similar names—one grouped by payment date and another by order placement date—cannot be merged just because both contain **total_amount**.

### 12.1. Watch Schema Evolution and Localization

If category names are localized by **locale**, a single **category_name_display** column without locale breaks once cards serve multiple languages. Model **(category_id, locale)** or bounded per-locale projections. **Each added language** multiplies copy counts and fan-out, so factor it into your redundancy budget upfront.

When metric formulas change (e.g., hidden reviews no longer count toward ratings), version the transformation, plan backfills, and reconcile. A consumer succeeding cleanly on valid payloads **does not prove** numbers comply with the new business rule.

### 12.2. Never Duplicate Personal Data Unless the Screen Needs It

User attributes like addresses, emails, or avatars can change visibility or face erasure requests under privacy policies. When copied across multiple read models, every copy, cache, log, and analytical store must honor access controls and retention bounds.

Often, storing just **user_id** and fetching permission-checked profile fields at read time is safer and easier to govern than embedding full profiles into every document.

## 13. Case Studies

### Case 1 — Category Name Stored in Three Places

The **products** table holds both **category_id** and **category_name**; **product_cards** also holds **category_name**; the search index stores it too. The PostgreSQL listing page with a JOIN already achieves p95 = 105 ms against a 180 ms SLO. Renaming one category forces updating 450,000 products.

**Question:** What is the core problem? Propose a minimal redundancy boundary.

### Case 2 — Average Rating Always Drifts Slightly

A **product_rating_stats** table stores **visible_review_count**, **visible_rating_sum**, and **average_rating**. When hiding a review, code decrements count and sum yet forgets to recompute the average.

**Question:** If the UI does not filter or sort by average, which fields should be stored? What must happen when a review's rating changes?

### Case 3 — Newcomer Doesn't Know Which Column to Fix

The **orders** table has **total_amount**, **customer_orders** also has **total_amount**, and the dashboard shows **order_total**. No documentation states whether totals include taxes and discounts or at which lifecycle point they were computed.

**Question:** Before touching the schema, which definitions must be verified and documented?

### Case 4 — Snapshot Mistaken for a Cache

Records in **order_items.product_name_at_confirmation** preserve names locked into orders a year ago. A new script spots differences from **products.product_name** and "fixes" them to today's name.

**Question:** Is this a redundancy that should be cleaned up?

### Case 5 — Category Move Collides with Rename

Product P sits in category A, then moves to B. A rename event for A arrives late. The consumer checks only A's **event_version** before updating **product_cards.category_name_display**.

**Question:** Which check is missing to avoid stamping A's name onto a product now in B? What else is needed when product and category events arrive out of order?

### Case 6 — A Copy That May No Longer Be Needed

A projection was built years ago because a dashboard took 3 seconds. After migrating reporting to an analytics warehouse, no API reads the projection anymore, yet its refresh worker still runs every minute consuming CPU and writes.

**Question:** What checks and steps should the team take before deleting the projection?

### Suggested Answers

1. The model maintains multiple copies without commensurate measured benefit; the JOIN already beats the SLO while renames cause massive fan-out. Keep **categories.display_name** as the source of truth and **products.category_id** as the relationship; retain only read models/search documents genuinely required by distinct access patterns, each with a contract and reconciliation.
2. Store only **visible_review_count** and **visible_rating_sum**, computing the average at read time with a zero-count guard. When a visible review updates its rating from x to y, adjust sum by **y − x** and keep count unchanged; when hiding a review, subtract 1 from count and its old score from sum once, handling retries idempotently.
3. Lock down **monetary semantics**, grain, currency, effective timestamp, taxes, discounts, shipping, refunds, source of truth, formulas, status scope, snapshot vs. copy role, and ownership. Only then decide which columns can be removed or merged.
4. **No.** This is a historical snapshot from order confirmation; it must not match today's catalog name. The script enforces the wrong invariant and rewrites history. Edit only through audited transaction-correction policies if permitted.
5. Verify **the card's current category_id** matches the event's category ID alongside the increasing category version. Also track **product_version**, handle relation-move ordering, and support refreshing from a consistent source snapshot when entity streams interleave.
6. Verify **all consumers and dependencies**, replacement reporting contracts, new read-path SLOs, stored data, and retention rules. Drain/stop readers, monitor, disable the refresh worker, confirm rollback safety, and then retire the projection/schema cleanly.

## 14. Takeaways

**Bounding redundancy means bounding how many facts must be kept consistent concurrently, not merely counting columns.** A sound copy has a clear read purpose, authoritative source, lineage, versioning/freshness bounds, strict write permissions, and paths for reconciliation and recovery.

**An explainable model** tells anyone why each field exists, which point in time it represents, and who owns it. **A maintainable model** lets teams ship features, evolve formulas, migrate schemas, or retire projections without guessing what might break.

Before adding any copy, ask: **"If the source attribute changes tomorrow, which places must update, who guarantees they stay right, what does it cost, and would the system still meet requirements without this copy?"** Only when answered with contracts and measurements is denormalization a controlled engineering choice.
