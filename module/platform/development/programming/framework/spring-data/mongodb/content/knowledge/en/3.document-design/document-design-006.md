# Denormalization, Duplicated Data, and Synchronization Policies

## 1. Why Denormalize in MongoDB?

In the **Document Design** chapter of **Spring Data MongoDB**, an essential decision is whether to place data in a single document, keep it in a separate collection and reference by ID, or **intentionally duplicate** part of the information across multiple documents to optimize reads.

**Denormalization** organizes data around access needs, accepting duplicate storage of certain values rather than keeping a single copy and joining on every read. For example, an order page must display product titles and unit prices at purchase time; a catalog page must quickly display *current* product titles and prices. These two needs look similar yet require **two completely different synchronization policies**.

Denormalization typically helps:

- Fetch everything needed for a screen or operation in one query or fewer round trips.
- Reduce the number of extra collection lookups needed to enrich data.
- Co-locate data frequently read and updated together in one document when size and cardinality fit.
- Build a *read model* optimized for search, pagination, reporting, or display.

In return, the system must handle **write amplification** (one source change fanning out to many copies), **stale data**, sync failures, and rules declaring which copy is authoritative.

> Foundational rule: before duplicating a field, determine whether the copy represents **a truth at a past point in time** or **live state that must be kept updated**. Those two cases must never share the same policy.

## 2. Three Data Storage Patterns to Distinguish

### 2.1. Embedding Data Within the Same Document (*Embedding*)

Example of an order containing line items and a shipping address:

~~~json
{
  "_id": "o-1001",
  "customerId": "c-12",
  "placedAt": "2026-11-20T08:00:00Z",
  "shippingAddressAtOrder": {
    "city": "Ha Noi",
    "street": "12 Example Street"
  },
  "items": [
    {
      "productId": "p-101",
      "titleAtOrder": "Water Bottle 500 ml",
      "unitPriceVnd": 129000,
      "quantity": 2
    }
  ],
  "totalVnd": 258000
}
~~~

A single read of the order provides everything needed to render a receipt. Because the item list is normally **bounded per order**, it is a sound candidate for embedding. However, never embed an unbounded array—such as *every* order of a customer inside the customer document: MongoDB documents have a **16 MiB** BSON size limit, and updating oversized arrays increases complexity, write load, and conflict risk.

Embedding does not mean every field needs synchronization. `titleAtOrder` and `unitPriceVnd` are **historical snapshots**; updating a product's current title or price must not rewrite past orders.

### 2.2. Referencing Between Documents (*Referencing*)

For large, independently growing one-to-many relationships, store IDs instead of embedding everything:

~~~json
{
  "_id": "review-900",
  "productId": "p-101",
  "authorId": "u-42",
  "rating": 5,
  "comment": "Keeps temperature well"
}
~~~

A product does not need to store every review. When summarizing ratings, the application can query the reviews collection by `productId`, use aggregation, or maintain a summary value on the product document.

Manual ID referencing is a common choice. MongoDB also offers `$lookup` in aggregations to join data from another collection. Thus, **you do not need to duplicate data simply assuming MongoDB cannot combine collections**; evaluate actual query cost and read frequency first.

### 2.3. Controlled Replication into a Read Model

Suppose the source collection stores products:

~~~json
{
  "_id": "p-101",
  "title": "Water Bottle 500 ml",
  "priceVnd": 129000,
  "categoryId": "bottles",
  "version": 8
}
~~~

To power a search screen, the application can maintain a `product_cards` collection:

~~~json
{
  "_id": "p-101",
  "title": "Water Bottle 500 ml",
  "priceVnd": 129000,
  "sourceVersion": 8
}
~~~

This second record is a **projection**: a copy that can be rebuilt from the source product. When a product's title or price changes, the projection must update under a stated policy—for example, an acceptable sync lag of at most 60 seconds. This is **live derived data**, distinct from historical snapshots inside orders.

## 3. When to Embed, Reference, or Replicate?

| Business characteristic | Typically suitable pattern | Question you must answer |
|---|---|---|
| Fields share a lifecycle, are read together, and stay small/bounded | Embed in document | Could document size grow out of control? |
| Very large one-to-many or independently updated entities | Reference by ID | Which indexes or extra queries are needed for efficient reads? |
| Values must remain fixed at the transaction timestamp | Copy as historical snapshot | What is the lock milestone and how are corrections handled? |
| Source changes frequently while a screen needs fast reads | Synced projection/copy | How much lag is tolerable, and how are out-of-order events handled? |
| Complex read criteria with low query volume and modest dataset size | Reference + aggregation/`$lookup` | Is maintaining an extra copy genuinely justified? |
| Fields governing payments, limits, or inventory counts | Read/write authoritative source at decision point | If a copy lags, would business decisions become wrong? |

There is no rule that "embedding is always faster" or "referencing is always better". Weigh **query shape**, data size, write counts, volatility, consistency, and failure recovery.

A rough quantitative checklist:

- **Read benefit:** how many reads and how many transferred bytes does a copy save?
- **Write cost:** when one product changes, how many copies must update? Does a product appear in 10 or 100,000 documents?
- **Staleness tolerance:** can the app tolerate stale copies for seconds, minutes, or not at all?
- **Recoverability:** can the entire projection be rebuilt from the source? Are there tools to detect missing or mismatched copies?

In MongoDB design, **single-document atomicity boundaries** also matter greatly: an update to one document is atomic on that document. If fields must change together under a business invariant, keeping them in one document is usually simpler than coordinating updates across multiple documents.

## 4. Defining the "Source of Truth" and Each Copy's Meaning

Before writing synchronization code, establish a data contract for each field group:

| Data field | Authoritative source | Meaning of copy | Policy |
|---|---|---|---|
`orders.items[].titleAtOrder` | Product at order lock time | Title shown on the placed order | Locked once; never updated with new titles |
`orders.items[].unitPriceVnd` | Price confirmed at purchase | Historical unit price for order totals | Locked once; never synced with new list prices |
`product_cards.title` | `products.title` | Current product title for catalog screens | Synced after changes, with monitored lag |
`product_cards.priceVnd` | `products.priceVnd` | Reference price on browse screens | Synced near real time; re-verified at checkout |
`products.availableStock` | Authoritative inventory state / reservation flow | Sellable quantity | Reservations must act safely on the source; displayed count may be approximate |

Two critical caveats:

1. **Copying price and stock for display never authorizes using the copy for final decisions.** Order placement must verify or reserve stock at the authoritative source under concurrency-safe rules and lock the proper business price.
2. **"Unsynchronized history" does not mean data lives forever or is immutable in every scenario.** Order amendments, personal data protection, retention deletions, or legal rules may require adjustments through a separate controlled workflow.

Without a clear source of truth, a change originating from a read model might get synced backward, creating update loops and nondeterministic state.

## 5. Synchronization Policies for Duplicated Data

### 5.1. No Re-Sync: Intentional Snapshot

At checkout, the system reads the accepted title and price at transaction lock time and saves them into the order. Afterward:

- Product is renamed: old orders retain the title from purchase time.
- List price changes: old orders retain the confirmed price.
- Product is hidden from catalog: receipts and orders still hold required historical details under the retention policy.

Snapshots keep history independent of whether the product collection still holds the record. Even so, capturing the snapshot must happen inside a sound checkout flow alongside necessary price, stock, and version checks; you **cannot** assume separate, uncoordinated reads and writes magically stay transactionally consistent.

### 5.2. Updating Within the Same Document

If both source fields and duplicated fields live inside **one document**, a single MongoDB operation—such as `$set` across multiple fields—updates them together. This is straightforward when all copies share a small boundary and lifecycle.

The downside is document bloat and forcing unrelated entity updates onto a single contention point. Never embed unbounded lists just to take advantage of single-document atomicity.

### 5.3. Updating Multiple Documents in a Transaction

When an invariant truly requires simultaneous updates across multiple documents, MongoDB supports multi-document transactions on supported topologies such as replica sets or sharded clusters. In imperative Spring Data MongoDB apps, you can configure `MongoTransactionManager` and use `@Transactional` as long as all required operations share the managed session.

Points to weigh:

- Transactions add resource overhead, latency, and conflict probability compared to single-document operations.
- Updating thousands of copies just because a product was renamed rarely belongs inside a synchronous transaction on a user request path.
- Handle retries for transient transaction errors and ensure external side effects (sending emails, publishing events) do not duplicate unintentionally.
- Calling the driver directly outside the managed session can leave an operation outside Spring Data's transaction.

Use transactions only when the consistency requirement truly justifies the cost; **unnecessary strict consistency for a read model can turn into a write bottleneck**.

### 5.4. Asynchronous Synchronization via Events

A common strategy is **write source first, update read models asynchronously**:

~~~mermaid
flowchart LR
    U["Product update request"] --> S["Write products: version 9"]
    S --> E["Change event durably recorded"]
    E --> W["Event worker"]
    W --> P["Update product_cards if version is newer"]
    P --> R["Screen reads projection"]
    W --> C["Checkpoints and lag monitoring"]
    F["Periodic reconciliation"] --> P
~~~

Ways to capture change events include:

- **Transactional outbox:** write the source mutation and an event record in the same transaction; a separate relay publishes/processes events after commit. If the outbox lives in a separate document, ensure multi-document transactions are truly active.
- **MongoDB change streams:** watch committed changes on a collection or database to trigger projection updates. Change streams require a supported MongoDB deployment (such as a replica set or sharded cluster), durable **resume token** management, disconnect monitoring, and persistent checkpoints. Do not assume an extra `fullDocument` lookup reconstructs every intermediate state during rapid consecutive source updates.
- **Durable event queue:** record/enqueue events using a mechanism that avoids "updated source but forgot to publish event". Calling a broker right after `save` without recovery can cause permanent drift.

Event consumers must tolerate **duplicate deliveries and out-of-order events**. Production pipelines need retries, dead-letter/quarantine queues for persistent errors, lag alerts, and replay capability. For deletions, emit explicit delete events or tombstones; never assume enough data remains on a deleted record to rebuild projections.

### 5.5. Refresh on Read and Periodic Reconciliation

**Lazy refresh** checks a version or TTL when reading a projection; if stale, it fetches from the source, updates the cache/projection, and returns the fresh result. This avoids continuous background writes, at the cost of higher latency on stale reads and potential stampedes if many requests refresh at once.

**Periodic reconciliation** compares source and copy to find missing items, version mismatches, or missed deletions. It can use batched scans, watermarks, or recent-update windows. Reconciliation serves as a vital safety net even when change streams or event queues are in place.

| Strategy | Data freshness | Primary cost | Suitable use cases |
|---|---|---|---|
Snapshot, no sync | Fixed at lock time | Historical storage | Order lines, unit prices, terms at signing/purchase |
Same document | Consistent after single update | Large documents and write contention | Small field groups sharing a lifecycle |
Multi-document transaction | Consistent on commit when configured properly | Transaction overhead, retries, resources | Business invariants requiring joint updates |
Async events | Eventual consistency | Sync lag, event pipeline, recovery | Search cards, read models, near-real-time stats |
Refresh on read | Depends on TTL/version and read demand | Read latency and source load at read time | Infrequently read or rarely updated data |
Periodic reconciliation | Depends on scan interval | Verification and repair load | Safety net for every critical projection |

## 6. Projection Implementation Pattern with Spring Data MongoDB

The example below illustrates an **asynchronously synced projection**. `products` is the authoritative source; `product_cards` is the read-optimized copy. A `ProductChanged` event carries the presentation state along with a **monotonically increasing source version**.

### 6.1. Versioning Writes at the Source

Spring Data MongoDB supports optimistic locking via `@Version` on entities, detecting concurrent overwrites when writes flow through version-aware paths:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class Product {
    @Id
    public String id;
    @Version
    public Long version;
    public String title;
    public long priceVnd;
}
~~~

This snippet uses public fields to keep the mapping mechanics concise; in real applications, encapsulate entities and control mutations. **Do not** use a low-resolution `updatedAt` or clocks across multiple machines as a strict ordering key to block stale events. The version must increment per entity upon accepted mutations. With `@Version`, audit saves, updates, and custom queries to ensure no write path silently bypasses versioning.

### 6.2. Copy and Event Models

~~~java
// ProductCard.java
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "product_cards")
public record ProductCard(
        @Id String id,
        String title,
        long priceVnd,
        long sourceVersion) {}
~~~

~~~java
// ProductChanged.java
public record ProductChanged(
        String productId,
        String title,
        long priceVnd,
        long sourceVersion) {}
~~~

Each card uses the product's ID as `_id` to guarantee uniqueness. Events must describe **committed source state**, never uncommitted changes. For multi-field mutations, carry enough state in the event to rebuild the projection or include a key/version to reload committed state safely.

### 6.3. Preventing Stale Events from Overwriting Newer State

A worker receiving an event updates the card only if `sourceVersion` is lower than the event's version. If the card does not exist yet, it inserts one; if two workers race to insert, `_id` uniqueness blocks the duplicate and the loser retries the conditional update.

~~~java
// ProductCardProjector.java
import com.mongodb.client.result.UpdateResult;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Component;

@Component
public class ProductCardProjector {
    private final MongoTemplate mongo;

    public ProductCardProjector(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void apply(ProductChanged event) {
        Query onlyNewer = new Query(
                Criteria.where("_id").is(event.productId())
                        .and("sourceVersion").lt(event.sourceVersion()));

        Update changes = new Update()
                .set("title", event.title())
                .set("priceVnd", event.priceVnd())
                .set("sourceVersion", event.sourceVersion());

        UpdateResult updated = mongo.updateFirst(
                onlyNewer, changes, ProductCard.class);
        if (updated.getMatchedCount() == 1) {
            return;
        }

        // Card may not exist yet, or the event is stale / already processed.
        try {
            mongo.insert(new ProductCard(
                    event.productId(),
                    event.title(),
                    event.priceVnd(),
                    event.sourceVersion()));
        } catch (DuplicateKeyException duplicate) {
            // Card already exists (possibly just created by another worker).
            // The version condition guards against overwriting with a stale event.
            mongo.updateFirst(onlyNewer, changes, ProductCard.class);
        }
    }
}
~~~

Behavior when events arrive in the order **v9 → v8 → v9 (duplicate) → v10**:

1. v9 creates the card if absent or updates a card with version < 9.
2. v8 is ignored because source version 8 is not newer than 9.
3. Duplicate v9 leaves the card unchanged.
4. v10 updates the card to version 10.

This provides **state-based idempotency** for replacement-style projections. It is **not** suitable when events mean "add 1" and each event must apply exactly once. For delta events like counter increments, use idempotency/event ID tracking, ordered application, or periodic recomputation from the source.

This example omits broker/change-stream consumption, checkpointing, retries, product deletion, and event publishing. Those must be implemented according to your data contract:

- Advance checkpoints only after the projection write is durable or the event is confirmed obsolete.
- If a write fails due to connectivity errors, retry; do not treat every error as a benign duplicate key.
- On deletion, consider writing a **versioned tombstone** so stale update events cannot resurrect a deleted product; purge tombstones only after the event retention window safely expires.
- When changing categories, sync both adding the item to the new category and removing copies from the old category.

### 6.4. Reading the Projection

~~~java
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductCardRepository
        extends MongoRepository<ProductCard, String> {
}
~~~

~~~java
// Example inside a service with ProductCardRepository cards:
Optional<ProductCard> card = cards.findById("p-101");
~~~

When a user must **immediately** see a price they just updated, reading this async projection may not fit. You can read the source directly or apply a version-aware read consistency check for that action. Explicitly design **read-your-writes** expectations rather than assuming every user tolerates lag.

## 7. Tricky Edge Cases in Synchronization

### 7.1. Out-of-Order Events, Duplicates, and Concurrent Updates

An event pipeline may redeliver events after retries, process partitions in parallel, or deliver out of order. **Every copy needs a version marker** for the source governing it. If a document aggregates multiple sources (product, seller, inventory), a single `sourceVersion` is usually insufficient: track per-source versions or use a deterministic merge flow.

### 7.2. Deletion and Recreation

Deleting a copy upon receiving a stale delete event can accidentally wipe out newly recreated data. Distinguish **fresh IDs** from **reused IDs**, and establish version/tombstone rules. Some applications use `deletedAt` or `isDeleted` flags on the source and propagate them through the same versioned stream to govern lifecycle cleanly.

### 7.3. Lost Events and Recovery After Outages

Even with version checks on every handler, **a lost event** leaves the copy permanently stale unless another mechanism intervenes. Make sure to:

- Store durable checkpoints or resume tokens properly.
- Detect stalled consumers, consumers lagging behind the source, or expired resume tokens.
- Run reconciliation and rebuild projections from authoritative data.
- Throttle backfills to avoid overloading the source collection.

### 7.4. Sensitive Data and Schema Changes

Every additional copy expands the surface where access controls, encryption, retention periods, and erasure must be enforced. Avoid copying emails, addresses, or phone numbers merely to save one query unless there is a clear need. When changing schemas, define `schemaVersion` or migration/backfill strategies so old and new consumers never interpret events inconsistently.

### 7.5. Indexes and Write Amplification

A single source document can fan out into many copies, each carrying multiple indexes. Changing an indexed field amplifies write work. When evaluating denormalization, check:

- Number of copies per source mutation; document size and growth rate.
- Total index count, index maintenance cost, and storage footprint.
- Read/write distribution, index selectivity, and aggregation cost.
- Whether the system can maintain sync SLAs during peak traffic.

## 8. Measuring and Testing Synchronization Policies

A useful design has **testable criteria**. Example policy for `product_cards`:

| Property | Example contract |
|---|---|
Authoritative source | `products` |
Copy scope | `id`, `title`, `priceVnd`, and `sourceVersion` |
Target latency | 95% of events reflected within 30 seconds; all within 2 minutes under normal operation |
Correctness | Lower-version events never overwrite higher-version state |
Recovery | Retry transient errors; alert on persistent failures; support reconciliation and backfill |
Usage limit | Display only; price and stock re-verified at checkout |

Thresholds like 30 seconds and 2 minutes are **illustrative design examples**. Choose numbers based on real requirements and infrastructure capacity.

With Spring Data MongoDB, write integration tests against a real MongoDB instance in Testcontainers to verify BSON storage and write behavior; when testing change streams or transactions, configure MongoDB with a supported topology. Minimum test scenarios:

1. Receive event v5 twice → card holds version 5 with intact data.
2. Receive v7 then v6 → card stays at version 7.
3. Two workers concurrently receive v8 and v9 when card does not exist yet → final version must be 9.
4. Consumer stops while source updates repeatedly, then consumer restarts → catches up or recovers via backfill.
5. Product is deleted, hidden, or moved to another category → projection stops showing outdated entries.
6. Already-created orders preserve checkout title and price even when the source product changes.

Beyond functional tests, monitor **projection lag**, queued event depth, retry rate, dead-letter count, missing cards, version mismatches, and backfill duration. Periodically compare source records with projections in batches to catch silent drift that event pipelines miss.

## 9. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
Re-syncing prices into all historical orders | Corrupted receipts and finalized totals | Separate historical snapshots from live prices |
Embedding unbounded arrays just to read one document | Document bloat, hitting BSON limits, painful updates | Reference and query items in a separate collection |
Updating source then emitting events unreliably | Source changes while projections stay unaware | Reliable outbox/CDC plus reconciliation |
Processing events without ordering or version checks | Stale events overwrite newer data | Monotonic versions and conditional updates |
Using read models for stock/payment decisions | Stale reads cause overselling or mispricing | Validate against the authoritative source in the business command |
Having only an event consumer with no backfill | Corrupted state persists forever after a dropped event | Build checkpoints, reconciliation, and rebuild tools |
Copying every field "just in case" | Higher security risk, index cost, and sync work | Replicate only fields with clear read demand and contracts |
Reflexively using transactions for every projection | Higher write latency, contention, reduced scalability | Match consistency level to need; prefer eventual consistency where appropriate |

## 10. Practice Exercises

**Exercise 1 – Order design.** Given customer info, products, current price, purchase price, shipping address, inventory, and status history, classify which fields belong at the source, which should be snapshotted into orders, and which can be projections. Explain why old order prices stay unchanged when product prices update.

**Exercise 2 – Catalog sync.** Design `product_cards` for product listings with an allowed lag of 1 minute. Specify the events, versioning, indexes, checkpoints, duplicate-event handling, product deletion, and how to rebuild after a one-hour consumer outage.

**Exercise 3 – Cost analysis.** A store has 50,000 products and each product appears in 30 curated lists. Calculate the potential number of copies and write operations triggered when renaming 1,000 products. Propose when embedded copies should be replaced with references or a dedicated read model; do not draw conclusions from counts alone while ignoring update frequency and read latency.

**Exercise 4 – Empirical verification.** Implement two catalog retrieval approaches: querying the source with necessary joins and reading a projection. Measure read latency, query counts, payload size, extra write cost, and copy staleness during failures. Pick a solution based on measured data.

## 11. Key Takeaways

Denormalization in **Spring Data MongoDB** is a **data design decision driven by workload and consistency contracts**, not merely copying fields for convenience. Embed when data has controllable size and is handled together; reference when entities grow large or have independent lifecycles; use snapshots when history must be preserved; use read models when optimizing queries with managed synchronization.

Every live copy must have a **source of truth, update conditions, acceptable lag budget, stale-event protection, deletion handling, and reconciliation workflow**. `MongoRepository` and `MongoTemplate` handle data access and mapping, while business design, indexes, transactions, and event pipelines determine the correctness, performance, and resilience of duplicated data.
