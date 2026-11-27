# Large Documents, Unbounded Arrays, and Hotspot Data Models

## Learning objectives

In **Spring Data MongoDB**, the data model determines not only how documents map to Java entities, but also how much data is read, how often a document is updated, index sizes, and how write load is distributed. Even a well-indexed query slows down if every document is huge; adding CPU or switching to `ReactiveMongoTemplate` cannot fix thousands of requests mutating the exact same document simultaneously.

After this lesson, you will be able to:

- Recognize three structural causes of performance degradation: **document bloat**, **unbounded array growth**, and **hotspots where heavy operations converge on one document, index range, or shard**.
- Choose among embedded documents, separate collections, bounded arrays, bucket patterns, subset patterns, and sharded/striped counters based on access patterns.
- Write `MongoTemplate`/repository operations for paged reads, targeted updates, and avoiding unnecessary history loads.
- Interpret signals from `explain("executionStats")`, BSON size, application metrics, and load tests to verify improvements.
- Understand boundaries between data modeling, indexing, transactions, sharding, and reactive access.

The running scenario is an order management system: each `Order` holds current state, thousands of historical events, operator notes, and concurrent updates.

## 1. How do large MongoDB documents affect the system?

MongoDB stores data as **BSON documents**. **The maximum size of a single BSON document is 16 MiB**; this limit applies to the **entire document**, including fields, nested objects, and array elements. While 16 MiB is a hard ceiling, operational pain typically starts **long before** hitting 16 MiB.

As a document grows, an application can suffer:

1. **Over-fetching data:** a screen only needs `orderId`, `status`, and `total`, yet the repository loads the full document including megabytes of history; network, BSON decoding CPU, and entity mapping process unneeded data.
2. **Higher update cost:** documents and storage structures must handle mutations on an increasingly large object. Partial updates via `$set`/`$inc` outperform full document replacement via `save`, yet do not eliminate the overhead of oversized documents.
3. **Cache and memory pressure:** a few huge documents compete for cache against many small hot documents; large JSON API responses can also trigger heavy JVM GC.
4. **Multikey index bloat:** indexing a field inside an array can generate many index keys from a single document; longer arrays drive up index size and write maintenance cost.
5. **Harder maintenance and migrations:** aggregations, concurrent updates, backfills, or archiving historical data incur higher costs.

There is no single "ideal" document size threshold for all applications. Look at **document size distribution (p50/p95/p99), read/write frequency, returned fields, and contention**. A tens-of-KiB document read infrequently in full may be fine, whereas a tiny document updated thousands of times per second becomes a hotspot.

### Example: an `Order` embedding its entire history

```json
{
  "_id": "ORD-1042",
  "customerId": "C-15",
  "status": "SHIPPED",
  "total": 280000,
  "events": [
    { "at": "2026-01-15T08:00:00Z", "type": "CREATED", "note": "..." },
    { "at": "2026-01-15T08:12:00Z", "type": "PAID", "note": "..." }
  ],
  "operatorNotes": [
    { "at": "2026-01-15T08:20:00Z", "text": "..." }
  ]
}
```

If `events` and `operatorNotes` are append-only, a long-lived order can accumulate hundreds of thousands of elements. Order detail views, event appenders, and audit flows then contend over the exact same document.

## 2. Unbounded arrays: convenient early on, painful at scale

Embedding an array in a document offers real advantages: reading the whole object in one query, updating fields atomically within a single document, and avoiding multi-collection joins. Those benefits fit best when **array size has a tight bound and elements are routinely accessed alongside the parent**.

A common anti-pattern:

```java
@Document("orders")
public class Order {
    @Id
    private String id;

    private String status;

    // Risk of bloat if every event ever recorded lives here.
    private List<OrderEvent> events = new ArrayList<>();
}
```

And a service updating it:

```java
Order order = mongoTemplate.findById(orderId, Order.class);
order.getEvents().add(newEvent);
mongoTemplate.save(order);
```

This pattern carries two distinct flaws:

- `findById`/`save` passes the **entire entity** back and forth, scaling transfer and processing with event count; if two requests read the same version concurrently, rewriting the whole entity risks **lost updates** without concurrency control.
- The array is unbounded: nothing stops the document from growing until it degrades performance or hits the BSON limit.

Using a targeted update like `$push` avoids reading and rewriting the whole entity and uses **single-document** atomicity:

```java
Query byId = Query.query(Criteria.where("_id").is(orderId));
Update appendEvent = new Update().push("events", newEvent);

mongoTemplate.updateFirst(byId, appendEvent, Order.class);
```

Still, **`$push` alone does not solve unbounded arrays**. It improves the write path compared to load-and-`save`, yet storage growth and parent document contention continue accumulating.

### Signs an array should be extracted

Consider moving an array to its own collection when one or more apply:

- Element count lacks a tight upper bound over the object's lifetime.
- History is rarely read alongside current state, or only paged subsets are needed.
- Elements are appended at high frequency by multiple requests or workers.
- Individual elements need independent indexing, searching, filtering, retention, or deletion.
- Array growth can push documents close to the 16 MiB limit.
- The application maps or transmits the whole array just to display a few small fields.

Conversely, an array holding a couple of phone numbers, fixed settings, or **at most** a few dozen items always read with the parent is usually a strong candidate for embedding.

## 3. Hotspots are not limited to large documents

A **hotspot** occurs when excessive operations converge on a single resource, bottlenecking throughput at that resource even while the MongoDB cluster has spare nodes and low overall CPU.

Distinguish at least three hotspot types:

| Hotspot type | Example | Typical symptom |
| --- | --- | --- |
| **Hot document** | Every worker runs `$inc` on a shared `campaign` counter document | Contention on one document, rising write latency or conflicts |
| **Hot index/range** | Continuous inserts with a monotonically increasing key | Writes cluster on one active key range or working region |
| **Hot shard** | Poor shard key sends all new writes to one shard | One shard saturates while others sit idle; scaling shards adds no write throughput |

A **tiny document can still be extremely hot** if many threads mutate it concurrently. For example:

```javascript
db.campaign_stats.updateOne(
  { _id: "CAMPAIGN-1" },
  { $inc: { totalViews: 1 } }
)
```

`$inc` is atomic on one document, avoiding lost updates from read-modify-write loops. Yet every view still contends for write access on that **single document**. Atomicity and write scalability are two separate properties.

Likewise, sharding does not distribute updates to a **single document**: that document resides on one shard, so all updates to it converge there. You must change the write model once a single document becomes a bottleneck.

## 4. Measure causes before redesigning schemas

MongoDB performance is shaped simultaneously by data, queries, indexes, hardware, network, and concurrency. Never conclude "slow because of large documents" solely from collection names or Java class length.

### 4.1. Sampling BSON size and array length

In `mongosh`, use `$bsonSize` to inspect document sizes:

```javascript
db.orders.aggregate([
  { $sample: { size: 500 } },
  {
    $project: {
      _id: 1,
      bsonBytes: { $bsonSize: "$$ROOT" },
      eventCount: { $size: { $ifNull: ["$events", []] } }
    }
  },
  { $sort: { bsonBytes: -1 } },
  { $limit: 20 }
])
```

Sampling aids investigation; it **does not guarantee capturing rare outlier giants**. On very large collections, `$sample` and BSON size computation still consume resources; run bounded checks in an appropriate environment alongside system metrics.

Track together: BSON size, array lengths, index/collection sizes, read/write ratios, and requests hitting the same `_id`. Base alert thresholds on percentiles and growth rate over time.

### 4.2. Explaining queries with `explain`

Example API fetching recent events for an order:

```javascript
db.order_events
  .find({ orderId: "ORD-1042" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(50)
  .explain("executionStats")
```

Inspect in your MongoDB version's plan output:

- `nReturned`: documents actually returned.
- `totalDocsExamined` and `totalKeysExamined`: examined work; high ratios relative to `nReturned` suggest query or index misalignment.
- `executionTimeMillis` and stage breakdown: scans, unindexed sorts, or expensive stages.
- Returned payload size, network latency, and Java mapping time—which **cannot** be inferred solely from `explain`.

Indexes supporting filters and sorts do not make a 10 MiB document cheap to read in full; combine execution plan inspection with **projections** and data modeling.

### 4.3. Measuring in the application and cluster

Use metrics/tracing at the API, `MongoTemplate`, or MongoDB driver layers to observe:

- P50/P95/P99 latency for reads, writes, history queries, and hot-document updates.
- Response payload size, BSON/JSON serialization/deserialization time, and JVM GC.
- Write counts, retries, optimistic-lock failures, timeouts, and write conflicts.
- MongoDB resources: CPU, I/O, cache, lock/queue pressure, disk latency, and shard load skew (if sharded).
- Load-driving query shapes: `find`, `aggregate`, `updateOne`/`updateMany`, `findAndModify`.

Measure against **real request patterns** and compare before/after under consistent datasets, load, indexes, and configuration.

## 5. Pattern 1 — Extracting history to a separate collection

If screens typically need only current order state plus the 20 latest events, storing full history in one document is wasteful. A standard design:

```text
orders
  _id, customerId, status, total, updatedAt, ...

order_events
  _id, orderId, createdAt, type, actorId, payload, ...
```

Each event becomes an independent document. `orders` keeps current state compact; `order_events` supports append writes, filtering, and pagination. Appending events no longer grows an `events` array inside `orders`.

### 5.1. Entity and compound index in Spring Data MongoDB

```java
@Document("order_events")
@CompoundIndex(
    name = "order_created_id_desc",
    def = "{ 'orderId': 1, 'createdAt': -1, '_id': -1 }")
public class OrderEvent {

    @Id
    private ObjectId id;

    private String orderId;
    private Instant createdAt;
    private String type;
    private String actorId;
    private String message;

    // Constructors, getters, and setters omitted.
}
```

Index `{ orderId: 1, createdAt: -1, _id: -1 }` filters by `orderId` and returns newest events in deterministic order. Adding `_id` at the end stabilizes pagination when multiple events share `createdAt`.

Ensure an explicit index management strategy is configured: never assume Spring Data MongoDB creates every annotated index automatically. In production, manage index creation via migrations or operational scripts and verify rollout results.

### 5.2. Paged reads using keyset/cursor pagination

Deep `skip` pagination must walk past skipped records. For long histories, **keyset pagination** on `(createdAt, _id)` generally fits better.

First page:

```java
Query firstPage = Query.query(
        Criteria.where("orderId").is(orderId))
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")))
    .limit(50);

List<OrderEvent> events =
        mongoTemplate.find(firstPage, OrderEvent.class);
```

Subsequent page anchored on the previous page's final element:

```java
Criteria olderThanCursor = new Criteria().orOperator(
    Criteria.where("createdAt").lt(lastCreatedAt),
    new Criteria().andOperator(
        Criteria.where("createdAt").is(lastCreatedAt),
        Criteria.where("_id").lt(lastId))
);

Criteria filter = new Criteria().andOperator(
    Criteria.where("orderId").is(orderId),
    olderThanCursor
);

Query nextPage = Query.query(filter)
    .with(Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.desc("_id")))
    .limit(50);

List<OrderEvent> next =
        mongoTemplate.find(nextPage, OrderEvent.class);
```

Here `lastCreatedAt` and `lastId` come from the previous page's last document; `lastId` is the `ObjectId` matching `_id`. Filter and sort order must align. If new events arrive while a user pages through history, cursor paging behaves more predictably than offsets, though it **does not automatically provide an immutable snapshot** of history.

### 5.3. Do event writes need a transaction?

Updating current state in `orders` and inserting into `order_events` touch **two documents**, so two sequential calls have no shared atomicity.

Clarify business requirements:

- If events must remain immediately consistent with current state, consider a **MongoDB transaction** via `MongoTransactionManager` on a transaction-capable MongoDB deployment; weigh transaction overhead and retry handling.
- If **eventual consistency** suffices, treat the event log as the source of truth or use a reliable event-publishing mechanism to update the current-state read model.
- Never claim two independent writes automatically "succeed or fail together."

**Trade-off:** fetching full history takes an extra query and may require transactions or sync pipelines, yet current-state reads stay independent of history length and event writes stop contending on the parent document.

## 6. Pattern 2 — Bounded array / subset pattern

Not every array needs a separate collection. If the main screen always renders only the **50 most recent events**, you can embed a **bounded summary** inside `orders` while optionally keeping full history in `order_events`.

```java
@Document("orders")
public class OrderSummary {

    @Id
    private String id;

    private String status;
    private List<EventPreview> recentEvents = new ArrayList<>();
}
```

Bounded update via `$push` + `$each` + `$slice`:

```java
Query byId = Query.query(Criteria.where("_id").is(orderId));

Update update = new Update()
    .push("recentEvents")
    .each(new EventPreview(eventTime, eventType))
    .slice(-50);

mongoTemplate.updateFirst(byId, update, OrderSummary.class);
```

`$slice: -50` keeps at most the **last 50 elements** of the array after pushing, capping array growth. Keep in mind:

- Capping element count **does not cap byte size**: keep `EventPreview` compact and avoid embedding bulky payloads.
- MongoDB retains only the sliced tail in the bounded array; if this is the **sole storage**, older entries are discarded. Archive to a separate collection or store if full history is required.
- Concurrent writers still mutate the **same `OrderSummary` document**, so bounded arrays cure document size, **not document hotspots**.
- Insertion order does not guarantee matching `eventTime` under concurrent requests; if business timestamp order is required, design and test sorting/writing accordingly.

The **subset pattern** also suits products showing a few featured reviews, chats holding recent messages, or accounts keeping a few frequent addresses. Choose a small, meaningful, measurable bound.

### Projection shrinks reads without fixing everything

When a schema cannot change immediately, fetch only needed fields:

```java
Query query = Query.query(Criteria.where("_id").is(orderId));
query.fields().include("status").include("total");

Document summary = mongoTemplate.findOne(
    query, Document.class, "orders");
```

The server returns only projected fields instead of the huge array, cutting wire bytes and client mapping work. However, projection **neither removes the array from disk, relieves write contention, nor lifts the 16 MiB cap**. For full entities, partial projections can leave fields unpopulated; prefer DTOs or read models rather than saving a partially loaded entity back.

## 7. Pattern 3 — Bucket pattern for time-series data

A system may ingest millions of tiny readings (sensors, telemetry logs, click metrics). Storing **one document per reading** inflates document and index counts; putting **every reading in one document** recreates unbounded arrays.

The **bucket pattern** groups a controlled batch into each document:

```json
{
  "_id": "device-18:2026-11-20T13:00:00Z:0",
  "deviceId": "device-18",
  "bucketStart": "2026-11-20T13:00:00Z",
  "count": 3,
  "measurements": [
    { "at": "2026-11-20T13:00:02Z", "value": 42 },
    { "at": "2026-11-20T13:00:14Z", "value": 43 },
    { "at": "2026-11-20T13:00:28Z", "value": 44 }
  ]
}
```

Bucket boundaries usually combine **element/byte caps**, time windows, and partition keys—e.g., at most 200 readings or a short interval per bucket depending on payload size. Once full, roll over to a new bucket.

Range reads touch fewer documents and reduce per-reading overhead. However, if many devices or workers append to **one open bucket**, that bucket stays hot. Under heavy concurrent ingestion, consider multiple parallel buckets (partition/bucket slots), batch ingestion, or rolling over buckets safely to prevent exceeding bounds under contention.

MongoDB also provides native **time series collections** optimized for storing and querying time-stamped measurements. Evaluate native time series collections before building custom buckets for pure telemetry. Time series collections carry different update/delete capabilities and indexing rules from standard collections; choose based on required APIs and your MongoDB version.

## 8. Pattern 4 — Distributing hot counter updates

For a campaign receiving tens of thousands of views per second, incrementing `viewCount` in a single document creates a hotspot despite tiny document size.

You can spread writes across **N counter stripes**:

```text
campaign_counters
  { campaignId: "C1", slot: 0, views: 12345 }
  { campaignId: "C1", slot: 1, views: 12981 }
  { campaignId: "C1", slot: 2, views: 12015 }
  ...
  { campaignId: "C1", slot: 15, views: 11888 }
```

Each request picks a `slot` via a hash or distribution source and increments that document. Enforce a **unique compound index** on `(campaignId, slot)` so each stripe maps to one document.

```java
int slot = ThreadLocalRandom.current().nextInt(16);

Query key = Query.query(
    Criteria.where("campaignId").is(campaignId)
            .and("slot").is(slot));

Update increment = new Update().inc("views", 1);

mongoTemplate.upsert(
    key, increment, "campaign_counters");
```

Total views equals the sum of `views` across stripes, computed via aggregation or a periodically refreshed materialized counter if read very frequently.

**Trade-offs:** more documents and higher total-read cost; summing across stripes does not automatically yield a point-in-time snapshot. If the use case requires strictly sequential numbering, exact per-event ordering, or atomic multi-field invariants, striped counters are not a drop-in substitute without transactional design.

Under moderate write rates, **a plain single-document `$inc`** is often best. Striping pays off only when measurements prove a single counter document is the bottleneck.

## 9. Other strategies: outlier pattern and cold data separation

Not every customer, thread, or order is the same size: most have a handful of events while a rare few have hundreds of thousands. The **outlier pattern** keeps the common case simple while offloading extremes to a side collection.

For instance, `orders` retains up to 50 recent notes plus `hasArchivedNotes`; beyond that threshold, older notes live in `order_notes`. The service layer can:

1. Load summary info from `orders`.
2. When a user clicks "View full history," query `order_notes` by `orderId` using a cursor.
3. Avoid pulling archived history back into `orders` on routine updates.

For binary files or huge blobs, do not embed them inside operational documents just to save a link. Store metadata and references pointing to **GridFS** or object storage as appropriate. GridFS handles large file storage and does not replace queryable event/history collections.

A **retention/archival** policy also keeps the working set bounded by moving or purging aged data per policy. TTL indexes automatically expire whole documents, though they cannot prune individual elements inside embedded arrays and do not replace business retention workflows.

## 10. Sharding and data models: distributing load or just moving the hotspot?

In sharded collections, the **shard key** directly governs document placement and write distribution. Common mistakes include:

- Choosing a **monotonically increasing** shard key on append-heavy workloads: new writes converge on a single shard owning the upper range.
- Choosing a shard key with **too few distinct values**: giant tenants or groups saturate individual shards.
- Picking `tenantId` or `orderId` by intuition without analyzing traffic skew, group sizes, and query patterns.
- Assuming adding shards spreads writes targeting **one single document**; that document still lives on a single shard.

A **hashed shard key** spreads inserts across shards for high-cardinality keys, while changing shard routing and range-query efficiency. Hashing still cannot spread concurrent writes hitting the **same shard key value**, nor does it split a single hot document.

When selecting a shard key, evaluate:

- Read/write distribution across keys and skew between large and small customers.
- Whether primary queries include the shard key for targeted routing.
- Query time ranges, sort/index alignment, and pagination needs.
- Future data and traffic growth, not just current document counts.

**Logical data models and shard keys must be designed together.** Splitting events into `order_events` breaks up huge documents, yet sharding on a poor key can still create shard-level hotspots.

## 11. Indexes, mapping, and updates in Spring Data MongoDB

### 11.1. Match indexes to queries without multiplying index entries unnecessarily

Embedded event arrays can be indexed on subfields such as `events.type`. MongoDB creates **multikey indexes** for arrays; while useful for queries, each array element/value can add index keys. As arrays grow, index footprints expand alongside them.

Once separated into `order_events`, create focused compound indexes matching query shapes:

- By order and time: `{ orderId: 1, createdAt: -1, _id: -1 }`.
- By event type within an order: consider `{ orderId: 1, type: 1, createdAt: -1 }` **only if** that query runs often enough to justify index/write overhead.

Do not create speculative indexes for hypothetical future queries. Every index adds write overhead, disk usage, and cache pressure.

### 11.2. Choose `updateFirst`/`findAndModify` over `save` when appropriate

When only changing status, update just the affected fields:

```java
Query q = Query.query(Criteria.where("_id").is(orderId));

Update u = new Update()
    .set("status", "SHIPPED")
    .currentDate("updatedAt");

mongoTemplate.updateFirst(q, u, "orders");
```

This avoids loading and rewriting the entire entity just to change one field. To enforce valid state transitions, include the expected prior status in the filter and check `matchedCount`:

```java
Query transition = Query.query(
    Criteria.where("_id").is(orderId)
            .and("status").is("PAID"));

Update ship = new Update().set("status", "SHIPPED");

UpdateResult result =
    mongoTemplate.updateFirst(transition, ship, "orders");

if (result.getMatchedCount() == 0) {
    // Missing document or status already changed:
    // handle conflict per business rules.
}
```

This pushes concurrency control into the single-document update predicate. If using `@Version` entities with `save`, Spring Data provides optimistic locking when configured properly, and conflicts must be handled explicitly. Still, frequent conflicts/retries can signal **too many concurrent writers targeting one document**.

### 11.3. Projections and dedicated read APIs

Avoid `findAll()` followed by Java-side history filtering, and avoid returning full persistence entities from list endpoints. Use projections and dedicated DTOs:

```java
Query listQuery = Query.query(
    Criteria.where("customerId").is(customerId))
    .with(Sort.by(Sort.Direction.DESC, "updatedAt"))
    .limit(20);

listQuery.fields()
    .include("_id")
    .include("status")
    .include("total")
    .include("updatedAt");

List<Document> summaries =
    mongoTemplate.find(listQuery, Document.class, "orders");
```

Indexes matching filter and sort still require validation with `explain`. If the collection is huge and customers have many orders, apply keyset pagination just as with `order_events`.

### 11.4. Reactive does not fix schemas

`ReactiveMongoTemplate` and reactive repositories excel at non-blocking I/O, backpressure, and serving high concurrency without blocking threads waiting on I/O. Even so, loading giant documents, unbounded arrays, or hammering a hot document generates the exact same server-side load on MongoDB. Tuning concurrency caps instantaneous pressure, whereas **fixing data structures and access patterns** solves the root cause.

## 12. Choosing a model by business requirements

| Data and access characteristics | Pattern to consider | Trade-offs to accept |
| --- | --- | --- |
| Few elements, tightly bounded, always read with parent | Embedded subdocuments | Parent updated together |
| Unbounded history, needs paging or independent filtering | References and separate event collection | Extra queries / potential transaction needs |
| Main view needs only the latest 20–50 items | Bounded array or subset | Payload bound; may still need separate full history |
| Many small time-stamped measurements | Bounded buckets or time series collection | Bucket management / update and index rules |
| Most documents small, rare extreme outliers | Outlier pattern, archival/cold storage | Extra read path for outlier data |
| Single counter under extreme write contention | Striped/distributed counter | Read aggregation cost and snapshot caveats |
| Uneven write load across shards | Revisit shard key and workload distribution | Query targeting and resharding/migration complexity |

No single pattern fits every system. Base choices on **growth bounds**, primary read patterns, write distribution, consistency needs, and measurements.

## 13. Verified performance improvement workflow

A practical workflow for a slow `orders` pipeline:

1. **Reproduce:** generate a dataset mirroring real size distributions (normal orders plus massive-event orders), concurrent write traffic, and core queries.
2. **Capture baseline:** endpoint p95/p99, response bytes, `$bsonSize`, array lengths, `explain("executionStats")`, conflict/retry counts, and server resources.
3. **Isolate causes:** separate missing indexes, oversized documents, client over-mapping, and hot-document contention on the same `_id`.
4. **Apply targeted changes:** projections for over-fetching; `$set`/`$push` instead of full entity `save`; bounded arrays where caps apply; separate history collections for unbounded growth; stripes for hot counters.
5. **Migrate safely:** backfill historical records, build required indexes, adjust read/write paths, and verify pre/post event counts. During dual-write transitions, define a single source of truth and sync rules.
6. **Verify correctness:** zero lost or duplicated events, stable pagination, accurate order state, idempotent retries, and unchanged authorization checks.
7. **Load test after changes:** under identical workload, compare latency, throughput, bytes/network, cache, index size, and execution plans. Check tail outliers, not just averages.
8. **Monitor post-deployment:** watch for renewed unbounded array growth, write conflict queues, and fresh shard skew.

Example team-defined acceptance criteria (not universal MongoDB limits): p99 `orders` document size stays under an agreed ceiling; `recentEvents` never exceeds 50 items; list endpoints omit history; recent-50-events query uses the expected index; p95 drops under identical load without anomalous error spikes.

### Questions to ask during schema reviews

- Does this array have a finite upper bound? **Where is it enforced**, including under concurrency?
- Does the application need the whole array with the parent, or just a recent subset?
- If a document grows from 10 to 100,000 items, which queries and updates degrade?
- How many concurrent writers target the **exact same `_id`**?
- Do indexes multiply keys across arrays or cluster writes on a narrow key range?
- Does the chosen transaction or eventual-consistency model meet business invariants?
- Was performance measured on realistic data distributions?

## 14. Hands-on exercise

**Scenario:** An order service stores `Order` documents holding 200,000 events in `events`. Every status update calls `findById`, appends to the list, and calls `save`. The list screen shows only `id`, `status`, and `total`; certain orders also receive hundreds of concurrent worker updates.

Work through each step:

1. Write a query projecting only list-screen fields; inspect `explain` and measure response size.
2. Extract history to `order_events` with a matching compound index; paginate newest events with a cursor.
3. Retain at most 20 `recentEvents` on `orders` for detail views if genuinely needed; design how full history stays intact.
4. Replace full-entity `save` with conditional `updateFirst` on status transitions; measure conflicts as concurrency rises.
5. Run load across varying order counts, especially **100 workers updating a single order**. Contrast overall system throughput against single-hot-document throughput.
6. Compile a before/after table: p95/p99, bytes/response, `docsExamined`, BSON document size, and update failure counts.

Closing question: **why can't a great index rescue a `save` loop rewriting documents containing 200,000 events?** Because indexes mainly speed up finding documents; they do not remove the cost of reading, mapping, transmitting, and rewriting a massive object.

## Key takeaways

- **16 MiB** is a hard cap per BSON document, yet performance trouble starts well before that ceiling.
- **Unbounded arrays** usually signal extracting history to a separate collection; embed only when growth is strictly bounded.
- **Bounded arrays** cap size but do not eliminate write contention if concurrent writers keep hitting the same document.
- **Hot documents, hot index ranges, and hot shards** are distinct bottlenecks; diagnose the exact type before picking a fix.
- In Spring Data MongoDB, favor **projections, field-level updates, cursor pagination, and workload-aligned indexes**; avoid `findById + save` for small mutations.
- Choose **references, subsets, buckets, outliers, striped counters, or time series collections** according to read/write patterns and consistency guarantees.
- Every schema change needs a migration plan, correctness verification, and load testing on meaningful data.
