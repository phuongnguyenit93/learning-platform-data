# Creating Collections with Size or Document Limits

> **Module:** `SPRING_DATA_MONGODB` — Use Spring Data MongoDB to connect, map documents, and operate on MongoDB via `MongoTemplate` or repositories; practice query design, aggregation, indexing, transactions, reactive access, testing, and data performance diagnostics.
>
> **Chapter:** Tailable cursor.
>
> **Focus:** design and create a **capped collection** in MongoDB using `mongosh`, `MongoTemplate`, or `ReactiveMongoTemplate`; understand the exact roles of `size` and `max` so data can be read with a tailable cursor.

## 1. Why Do We Need a Bounded Collection?

Suppose an IoT device system emits a status event every few seconds. A monitoring service only needs to observe a recent window of data to update a dashboard. If written to a regular collection, the record count grows indefinitely until a cleanup job runs. To read continuously as new events are inserted, a **tailable cursor** pairs with a collection organized in insertion order.

A **capped collection** is a collection with **bounded data capacity**. When there is no longer enough space to store a new document or when the configured document count threshold is reached, MongoDB automatically evicts the oldest documents in natural order to make room for new ones. The collection thus behaves like a **circular buffer**.

```text
Producer  ── insert ──> MongoDB capped collection ── tail ──> Consumer
                            │                         │
                            │                         └─ Wait for newly inserted records
                            │
                   [oldest] [older] [newer] [newest]
                          │
                          └── Evicted when limit is exceeded
```

A capped collection has two core configuration parameters:

- `size`: **required**, maximum target capacity for the collection's data storage, in **bytes**.
- `max`: **optional**, desired maximum number of documents; this limit works alongside `size`.

**Core note:** you cannot create a capped collection with only a `max` threshold while omitting `size`. Even if you only want to limit by document count, you must still allocate a `size` large enough to hold that number of documents.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish capped collections from regular collections, TTL indexes, time series collections, and Change Streams.
2. Explain the automatic retention/eviction rules based on `size` and `max`, and what happens when storage or document count hits its threshold.
3. Create a capped collection with valid `db.createCollection` syntax in `mongosh`.
4. Create collections using `MongoTemplate` and `ReactiveMongoTemplate` with `CollectionOptions`.
5. Size capacity appropriately based on insert rate, document size, and desired retention window.
6. Verify that a collection is genuinely capped before opening a tailable cursor, especially in multi-instance environments.
7. Build a continuous-reading example with `Flux` and test circular buffer behavior.
8. Recognize constraints around updates, deletes, sharding, operations, and slow consumers.

## 2. How Does a Capped Collection Work?

A regular collection does not automatically evict older documents simply because its size grows. A capped collection has a maximum data storage budget configured at creation time.

Suppose a collection has enough room for three small documents. When a fourth document is inserted, MongoDB evicts the oldest document to make space:

```text
After inserting A:   [ A ]
After inserting B:   [ A ][ B ]
After inserting C:   [ A ][ B ][ C ]
After inserting D:        [ B ][ C ][ D ]  (A is logically overwritten)
After inserting E:             [ C ][ D ][ E ]
```

The diagram illustrates element count only; in practice, eviction also depends on the BSON size of each document and the document-count limit (if configured). Do not assume all documents occupy the same number of bytes.

### 2.1. The Two Limits: `size` and `max`

| Property | Value Type | Required | Role |
| --- | --- | --- | --- |
| `capped` | `true` | Yes | Marks the collection as capped |
| `size` | Positive integer, in **bytes** | Yes | Data storage budget allocated for the collection |
| `max` | Positive integer | No | Document count limit; `size` is still required |
| `collation`, `validator`, ... | Depends on MongoDB version | No | Evaluate separately if used with a capped collection |

The practical rule is that **whichever limit is reached first triggers eviction of old documents**. Setting `max: 10000` does not guarantee the collection always holds 10,000 records. If documents carry large payloads that fill `size` first, fewer documents will be retained.

Conversely, if each document is very small, `max` may be reached before exhausting `size`.

> `size` is the limit for the collection's data storage area, **not RAM bytes** pre-reserved by MongoDB, nor a total size quota for the entire database. Actual disk usage also depends on the storage engine, indexes, and other metadata. MongoDB may round allocation units depending on the version.

### 2.2. Important Properties

- **Reads in natural order (`$natural`):** a capped collection preserves insertion order, making it well suited for streaming cursors.
- **Append-only writes via insert:** suitable for temporary event logs, telemetry, and near-real-time observability data.
- **Automatic eviction of old records:** no periodic `deleteMany` job is needed to bound document count.
- **No individual document deletion like regular collections:** capped collections do not fit workflows requiring per-document `deleteOne` or `deleteMany`; full cleanup requires administrative operations such as dropping or an equivalent mechanism.
- **Restrictions on updates that grow documents:** updates causing a document to grow beyond its allocated space may be rejected; prefer immutable (append-only) records.
- **Cannot shard a capped collection** the way regular collections are sharded.
- **No fixed time-based retention:** how long a document remains depends on the rate and size of new inserts, not a fixed 60-minute or 24-hour TTL.
- **No infinite retention guarantee:** when producers outpace consumers or an application stays down for too long, unread documents may already have been evicted.

Specific limitations per MongoDB version should be verified during server upgrades.

## 3. Relationship Between Capped Collections and Tailable Cursors

A **tailable cursor** is a cursor that does not close immediately upon reaching the end of a capped collection. It can continue receiving newly inserted documents as data arrives.

A tailable cursor:

- Reads documents in the **natural order** of the capped collection.
- Is typically opened in **awaitData** mode to wait for more records rather than polling unnecessarily.
- Only reads documents returned by the query; by itself it does not emit UPDATE/DELETE events like MongoDB Change Streams.
- Can become invalid if the cursor is interrupted or the document at the read position has been evicted; in that case a reopen policy and handling for potentially lost data gaps are needed.
- Has no durable **resume token** like Change Streams. Do not treat a tailable cursor as a durable queue with delivery guarantees.

### 3.1. Why Must the Collection Be Capped?

Capped collections organize data in a way that suits long-lived cursors following natural order. A regular `find()` on a regular collection ends once existing results are returned and does not remain open waiting for new inserts.

```text
Regular collection:
find() ──> end of data ──> cursor closes

Capped collection:
tail() ──> existing records ──> wait ──> new insert ──> emit next
```

A tailable cursor may terminate immediately if opened on an **empty** capped collection. Therefore, practice exercises should insert a bootstrap record before tailing, or implement lifecycle management and delayed reopening on completion. Calling `subscribe()` and inserting immediately afterward does not prove the cursor was ready.

### 3.2. Comparison with Change Streams

| Criterion | Tailable cursor | Change Streams |
| --- | --- | --- |
| Source | Documents in a **capped collection** | Stream of changes from a supported MongoDB deployment |
| Regular collections | Cannot be tailed | Can watch changes if topology/version supports it |
| Operations received | Readable documents on insert | Event types such as insert, update, delete, replace |
| Ordering | Capped collection natural order | Change stream ordering and metadata |
| Resume token | None | Available when supported by the event |
| History retention | Based on capped collection `size`/`max` | Depends on oplog history retention and resume handling |
| Best suited for | Append-only event streams with short retention | Data change synchronization and CRUD-reactive workflows |

**Selection:** if the requirement is "write events and have readers consume continuously over a short window," a capped collection can make sense. If you need to know when a business document was UPDATED or DELETED, Change Streams are a better fit.

## 4. Creating a Capped Collection with `mongosh`

### 4.1. Size Limit Only

Example creating `device_events` with a 64 MiB data budget:

```javascript
use telemetry_demo;

db.createCollection("device_events", {
  capped: true,
  size: 64 * 1024 * 1024
});
```

Calculation:

```text
64 MiB = 64 × 1024 × 1024 = 67,108,864 bytes
```

Here MongoDB determines how many documents remain retained based on each record's size.

### 4.2. Size Limit and Document Count Limit

To retain at most 100,000 documents within a 128 MiB limit:

```javascript
db.createCollection("app_events", {
  capped: true,
  size: 128 * 1024 * 1024,
  max: 100000
});
```

- `size`: 134,217,728 bytes.
- `max`: 100,000 documents.
- If 128 MiB fills up before 100,000 documents, MongoDB will already have evicted older documents.
- If 100,000 documents are written before reaching 128 MiB, the document count limit takes effect first.

### 4.3. Examples of Misconfiguration

**Wrong: omitting `size`**

```javascript
// Invalid: a capped collection requires size.
db.createCollection("invalid_events", {
  capped: true,
  max: 5000
});
```

**Wrong: misunderstanding units:**

```javascript
// size: 1024 means 1024 BYTES, not 1024 MiB.
db.createCollection("tiny_events", {
  capped: true,
  size: 1024,
  max: 10000
});
```

Depending on minimum size limits and allocation rules for your MongoDB version, the command above may be rejected or create a collection too small to be useful. In practice exercises, use an appropriate size such as 1 MiB or more and size according to your needs.

**Wrong: assuming calling `createCollection` again updates configuration:**

```javascript
db.createCollection("app_events", {
  capped: true,
  size: 256 * 1024 * 1024,
  max: 100000
});
```

If `app_events` already exists, re-running creation does not automatically act as a migration to change `size`. You need a version-appropriate administrative/migration procedure or to create a new collection and switch consumers in a controlled way.

## 5. Verifying the Collection After Creation

Do not assume a collection is capped merely because it is named `events`, has a `@Document` annotation, or has a particular index.

### 5.1. Quick Check with `isCapped()`

```javascript
use telemetry_demo;

db.device_events.isCapped();
// Expected: true

db.app_events.isCapped();
// Expected: true
```

If the result is `false`, the application does not meet the prerequisite to open a tailable cursor on that collection.

### 5.2. Inspecting Collection Creation Metadata

```javascript
db.getCollectionInfos({
  name: "app_events"
});
```

A valid definition will show `capped`, `size`, and `max` under `options` as created (formatting may vary by server/shell version).

You can inspect statistics:

```javascript
db.app_events.stats();
```

Pay attention to document count, current data size, and capped collection statistics if supported by your version. Do not treat `storageSize` or `totalIndexSize` as the exact configured `size` value: they represent different aspects of storage.

### 5.3. Testing Old-Document Eviction

Create a collection large enough in bytes that a few test documents will not exceed `size`, while limiting document count via `max`:

```javascript
db.createCollection("ring_test", {
  capped: true,
  size: 1024 * 1024,
  max: 3
});

db.ring_test.insertMany([
  { _id: "A", sequence: 1 },
  { _id: "B", sequence: 2 },
  { _id: "C", sequence: 3 }
]);

db.ring_test.insertOne({ _id: "D", sequence: 4 });

db.ring_test.find({}, { _id: 1, sequence: 1 })
            .sort({ $natural: 1 })
            .toArray();
```

With small documents and no other producers, the expected result in natural order is `B`, `C`, `D`. Document `A` is evicted when `D` is inserted. This is a simple experiment to verify the document-count policy.

Do not treat this test as proof of a guarantee to "always keep three documents" when payloads grow or when `size` might be hit first.

## 6. Sizing Based on Write Rate

Choosing an arbitrary `size` yields unpredictable retention. Before creating the collection, determine:

1. Average and peak insert rate: `r` documents/second.
2. Average and high-percentile BSON document size: `b` bytes/document.
3. Duration data must be retained so slow consumers can read it: `t` seconds.
4. Safety margin for traffic spikes, document size variance, or temporary consumer pauses.

Initial estimate:

\[
\text{requiredBytes} \approx r \times b \times t \times \text{safetyFactor}
\]

A `safetyFactor` can start around 1.5–3 depending on data variability and operational requirements. This is a planning formula, not a guaranteed history retention duration.

### 6.1. One-Hour Budget Example

Suppose:

- `r = 50` documents/second.
- `b = 1,200` bytes/document, including measured payload and overhead.
- `t = 3,600` seconds, targeting roughly one hour of data.
- `safetyFactor = 2`.

Calculation:

```text
50 × 1,200 × 3,600 = 216,000,000 bytes
With factor of 2:    432,000,000 bytes
432,000,000 / 1,048,576 ≈ 412 MiB
```

A reasonable starting choice is `size: 512 * 1024 * 1024` (512 MiB). Then measure actual retention under production-like load.

Document count over one hour:

```text
50 × 3,600 = 180,000 documents
```

If you want to retain roughly one hour, setting `max: 100000` will cause the document limit to trigger first, shrinking retention to around 33 minutes at a steady rate. In that case, omit `max` or set `max` higher than the expected count accounting for peaks.

### 6.2. Illustrative Sizing Matrix

| Rate | Average Size | Target Retention | Expected Documents | Estimated Raw Data |
| --- | --- | --- | --- | --- |
| 2/s | 512 B | 1 hour | 7,200 | ~3.7 MB |
| 50/s | 1,200 B | 1 hour | 180,000 | ~216 MB |
| 100/s | 2 KB | 10 minutes | 60,000 | ~120 MB |
| 500/s | 1 KB | 15 minutes | 450,000 | ~450 MB |

This table excludes the safety factor, size skew, indexes, and physical storage engine differences. Distinguish **decimal KB/MB** (1,000) from **binary KiB/MiB** (1,024) when passing values to `size`.

### 6.3. Index Cost and Document Size

Capped collections can still have indexes for regular lookups, though tailable cursors are designed to read in natural order and do not replace arbitrary sorted queries on indexed fields.

If documents are too large:

- Fewer documents fit inside the capped region.
- An unusually large document can sharply reduce the retention time of preceding documents.
- Serializing and transferring full documents increases network traffic and consumer RAM usage.
- If a document exceeds the valid BSON size limit, MongoDB rejects the insert.

For streams, choose a small, fixed, append-only event schema; store large payloads elsewhere and include only a reference in the event.

## 7. Creating a Capped Collection with `MongoTemplate`

In Spring Data MongoDB, the API for creating a collection with options is `MongoTemplate.createCollection(...)` combined with `CollectionOptions`.

### 7.1. Complete Java Example

```java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;

public final class CappedCollectionSetup {

    private static final String COLLECTION = "device_events";

    private final MongoTemplate template;

    public CappedCollectionSetup(MongoTemplate template) {
        this.template = template;
    }

    public void createIfAbsent() {
        if (template.collectionExists(COLLECTION)) {
            return;
        }

        CollectionOptions options = CollectionOptions.empty()
                .capped()
                .size(64L * 1024 * 1024)
                .maxDocuments(100_000L);

        template.createCollection(COLLECTION, options);
    }
}
```

**API explanation:**

- `CollectionOptions.empty()` creates a configuration object for the collection.
- `.capped()` marks the collection as capped.
- `.size(...)` declares the byte budget.
- `.maxDocuments(...)` maps to the MongoDB `max` option.
- `collectionExists(...)` only checks whether a collection with that name exists.
- `createCollection(...)` is a schema/collection creation operation and should run during controlled bootstrap or migration.

**Mandatory production check:** if the collection already exists as **non-capped**, `collectionExists` returns `true` and the code above returns without changing the collection type. Therefore, verify the state using metadata and refuse to start the consumer if the configuration does not match.

### 7.2. Why Not Auto-Create the Collection on Save?

A repository operation like `repository.save(...)` or `mongoTemplate.insert(...)` can cause MongoDB to auto-create a **regular collection** if none exists yet. If the first insert runs before bootstrap creates the capped collection, the collection will have the wrong format for tailable cursors.

Proper workflow:

```text
Migration / bootstrap (create capped collection)
                │
                ▼
Verify options: capped=true, expected size/max
                │
                ▼
Allow producers to insert
                │
                ▼
Start tailable consumer
```

Grant schema creation/modification privileges to a deployment account, keeping the application runtime account restricted to the read/write permissions it needs. If multiple pods start simultaneously, a "check then create" pattern has a race condition; use a single migration process or handle "namespace already exists" errors together with a metadata verification step.

## 8. Creating a Capped Collection with `ReactiveMongoTemplate`

In Spring WebFlux applications using `ReactiveMongoTemplate`, collection creation returns a publisher and **executes only upon subscription**.

```java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public final class ReactiveCappedCollectionSetup {

    private static final String COLLECTION = "device_events";

    private final ReactiveMongoTemplate template;

    public ReactiveCappedCollectionSetup(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Void> createIfAbsent() {
        CollectionOptions options = CollectionOptions.empty()
                .capped()
                .size(64L * 1024 * 1024)
                .maxDocuments(100_000L);

        return template.collectionExists(COLLECTION)
                .flatMap(exists -> {
                    if (exists) {
                        return Mono.empty();
                    }

                    return template.createCollection(COLLECTION, options)
                            .then();
                });
    }
}
```

**Do not write:**

```java
// Only declares the Publisher; does not trigger the create operation.
setup.createIfAbsent();
```

Instead, compose it into startup or dependent pipelines:

```java
Mono<Void> startup = setup.createIfAbsent()
        .then(checkCollectionConfiguration())
        .then(startProducerOrConsumer());
```

Here `checkCollectionConfiguration()` and `startProducerOrConsumer()` are application-implemented steps returning `Mono<Void>`. They illustrate the required sequence: **create → verify → start reading/writing**. Do not call `subscribe()` independently and assume the remaining steps have finished.

### 8.1. Caution When Multiple Instances Start Simultaneously

`collectionExists` followed by `createCollection` is a non-atomic two-step sequence. Two instances can simultaneously observe that the collection is absent and both attempt to create it.

In production, prefer:

- Managing collections via a separate migration/deployment step before scaling out application replicas.
- If auto-creating, catching "already exists" errors only after verifying that the existing schema actually matches.
- Never catching all exceptions and proceeding as if initialization succeeded.
- Never dropping and recreating a collection at runtime to "fix configuration," as doing so loses data and breaks tailable cursors for other consumers.

## 9. Designing an Entity for Events Stored in a Capped Collection

Example of a small event model with a creation timestamp and display payload:

```java
import java.time.Instant;

import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "device_events")
public record DeviceEvent(
        @Id ObjectId id,
        String deviceId,
        String type,
        String payload,
        Instant createdAt
) {}
```

This uses a Java 17+ record; for older Java versions, use a POJO with constructor, getters, and setters compatible with Spring Data. `@Document` maps the entity to a collection name; it **does not automatically ensure the collection is created as capped**.

Inserting a document:

```java
import java.time.Instant;

import reactor.core.publisher.Mono;

public Mono<DeviceEvent> append(DeviceEvent newEvent) {
    return template.insert(newEvent, "device_events");
}

DeviceEvent event = new DeviceEvent(
        null,
        "sensor-42",
        "TEMPERATURE",
        "27.5",
        Instant.now()
);
```

`template` in this example is `ReactiveMongoTemplate`. MongoDB/Spring Data maps `id` upon insertion according to the active conventions; production code should explicitly define IDs, payload size limits, and validation.

### 9.1. Prefer Writing Immutable Events

With capped collections, prefer appending a new document for each event instead of mutating an existing document across a workflow:

```text
Intended usage:
insert { deviceId, eventType, payload, timestamp }
insert { deviceId, eventType, payload, timestamp }
insert { deviceId, eventType, payload, timestamp }

Poor fit:
insert one document
update repeatedly causing the document to grow
delete documents based on business conditions
```

If the application needs flexible edits/deletes, long-term history, or multi-dimensional analytical queries, store source data in a regular or time series collection and use an appropriate event-publishing mechanism.

## 10. Reading with a Tailable `Flux` Once the Collection Is Created

A capped collection is the **foundational requirement** for a tailable cursor. Reactive Spring Data MongoDB provides `ReactiveMongoTemplate.tail(...)` to turn the document stream into a `Flux<T>`.

### 10.1. Continuous Reading Example

```java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;

public final class DeviceEventTailer {

    private final ReactiveMongoTemplate template;

    public DeviceEventTailer(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<DeviceEvent> tail() {
        return template.tail(
                Query.empty(),
                DeviceEvent.class,
                "device_events"
        );
    }
}
```

- `Query.empty()` requests reading without additional filter criteria.
- `DeviceEvent.class` specifies the target entity type for BSON mapping.
- `"device_events"` must point to an **existing capped collection**.
- The `Flux` does not terminate after a fixed element count under normal streaming conditions.
- A subscription is required to run the stream; certain errors can terminate the publisher and require opening a new cursor.

### 10.2. Processing via Reactor

```java
Flux<Void> handled = tailer.tail()
        .concatMap(event ->
                eventHandler.process(event)
        );
```

This assumes `eventHandler.process` returns `Mono<Void>` and completes after its side effect. `concatMap` processes items sequentially in the order emitted upstream. Avoid writing:

```java
// Does not wait for async processing; errors can be detached from the main stream.
tailer.tail().doOnNext(event ->
        eventHandler.process(event).subscribe()
).subscribe();
```

When event processing is very fast and independent, `flatMap` with bounded concurrency can increase throughput, though you must manage completion ordering and processing state yourself.

### 10.3. Seed Events and Cursor Open Timing

An important caveat: a tailable cursor can close immediately if the capped collection is **empty when the cursor opens**. Therefore, practice setups should insert a bootstrap record beforehand or build a delayed-reopen mechanism.

```javascript
db.device_events.insertOne({
  deviceId: "system",
  type: "BOOTSTRAP",
  payload: "ready",
  createdAt: new Date()
});
```

Then open the tailable cursor. A new tailable cursor may return documents already present in the collection before waiting for new inserts. Consumers must decide via business logic whether to replay existing records or skip them.

> If you need a reliable resume point after restart, tailable cursors do not provide a resume token like Change Streams. Consumer design must either accept retention limits and potential duplicate/missed events or use a more durable mechanism.

## 11. Understanding `size` and `max` Limits in Real Streams

### 11.1. `max` Does Not Mean "Total Events Processed"

`max: 10000` means the **concurrently stored document count** does not exceed that threshold if `size` allows, not that the producer stops after 10,000 events. The producer continues inserting; MongoDB automatically evicts older documents.

### 11.2. Evicted Data May Not Have Been Read by Consumers

Suppose a capped collection retains the latest 1,000 events, the producer writes 100 events/second, and the consumer pauses for 20 seconds. During the outage, 2,000 new events are inserted. Older unread events may no longer exist when the consumer reconnects.

```text
Producer:  E001 ... E1000 E1001 ... E3000
                       └──────────────┘
                       Only latest 1000 retained

Consumer stopped at E0900, reopens after 20 seconds:
E0901 ... many intermediate events have already been evicted
```

Thus, a capped collection is a bounded buffer. It **does not replace** a message broker with retention and delivery guarantees when zero event loss is required.

### 11.3. Large Documents Can Sharply Reduce Retention

A multi-kilobyte payload can consume as much space as many small documents. Even with `max` unchanged, the effective history window shrinks. Measure BSON size percentiles (P95/P99) and enforce payload size limits at the producer.

### 11.4. Observing Pressure and Backpressure

Reactor backpressure signals the rate at which the consumer wants to receive items, but **does not prevent producers from writing to MongoDB**. If a consumer stays slow for an extended period, the capped buffer still wraps around. Lag alerts and recovery paths aligned with business requirements are essential.

## 12. Comparing Capped Collections, TTL, and Time Series

| Criterion | Capped collection | Regular collection + TTL index | Time series collection |
| --- | --- | --- | --- |
| Primary limit | Data size and optional document count | Document expiration timestamp | Time-ordered storage optimized for time-based writes/storage/queries |
| Auto-eviction of old data | Yes, upon hitting threshold | TTL monitor deletes expired records, not strictly instantaneous | Based on supported expiration policy |
| Suitable for tailable cursor | **Yes** | No | Not used like a standard capped collection |
| Insert-only data | Best fit | Not required | Well suited for measurement series |
| Guaranteed exact 1-hour retention | No | Approximate, per TTL monitor and configuration | Per time series policy, not a tailable mechanism |
| Querying / long-term storage | Bounded by circular buffer | More flexible | Often suited for telemetry/time-based analytics |

If the goal is **byte-bounded storage and tailing**, a capped collection fits. If the goal is **deleting data after N days**, TTL or time series should be considered. If you need to sync CRUD operations on business collections, use Change Streams.

## 13. Creation, Conversion, and Migration Operations

### 13.1. Creating the Collection Before the Write Path

Standard production workflow:

```text
Infrastructure / migration:
  1. Choose appropriate namespace, size, and max
  2. Create capped collection
  3. Verify capped=true and expected size/max

Application:
  4. Allow producers to insert
  5. Ensure data exists or define empty-cursor handling
  6. Open tailable Flux and monitor
```

Avoid having multiple production application instances mutate collection structure during scale-out.

### 13.2. What If the Collection Already Exists as Regular?

You cannot convert an existing collection to capped merely by adding `@Document`, invoking a repository, or re-running `createCollection`.

MongoDB provides the administrative command `convertToCapped` in supported environments/versions, for example:

```javascript
// Syntax reference ONLY; account for downtime, data loss, and deployment limits.
db.runCommand({
  convertToCapped: "legacy_events",
  size: 128 * 1024 * 1024
});
```

Conversion can lock the collection, alter behavior, and discard older documents if capacity is insufficient. It is not suitable as a surprise automatic migration in an application handling critical data.

A safer procedure in many cases is to create a new capped collection with a different name, switch producers, update consumers, verify data, and only then retire the old collection under an approved plan. Explicitly specify how much historical data must be carried over.

### 13.3. Want to Change `size` or `max` After Creation?

Do not assume every MongoDB version allows modifying `size`/`max` with the same command or interface. Modifying capped collection options depends on server version, topology, and tooling. Check official documentation before changing production environments.

When significant retention changes are needed, prefer a controlled migration and measure actual storage usage. Never drop a collection being tailed to "reset" it without a data and reconnect plan.

## 14. Testing Capped Collection Behavior

### 14.1. Essential Tests

| Scenario | Expectation |
| --- | --- |
| Create collection with `capped: true` and `size` | `isCapped() == true` |
| Create with `size` and `max` | MongoDB accepts expected options |
| Insert more than `max` small documents | Oldest documents are evicted |
| Insert large documents filling `size` before `max` | Retention holds fewer than `max` documents |
| Open tail on seeded capped collection | Consumer receives documents and can wait for more |
| Open tail on regular collection | Tailable query does not operate as designed |
| Open tail on empty collection | Handle possibility of immediate cursor closure |
| Consumer disconnects and restarts | Do not assume a resume token; evaluate duplicates/gaps |
| Multiple instances create same collection | Do not ignore bootstrap race |
| Collection exists but is not capped | Startup fails or executes explicit migration |

### 14.2. Quick Practice in `mongosh`

```javascript
use telemetry_demo;

db.createCollection("small_buffer", {
  capped: true,
  size: 1024 * 1024,
  max: 5
});

for (let i = 1; i <= 8; i++) {
  db.small_buffer.insertOne({
    _id: i,
    event: "tick",
    createdAt: new Date()
  });
}

print("isCapped:", db.small_buffer.isCapped());
print("count:", db.small_buffer.countDocuments({}));

db.small_buffer.find({})
               .sort({ $natural: 1 })
               .toArray();
```

With small documents, IDs 4 through 8 are expected to remain. If a different result appears, inspect actual data size, whether another producer wrote to the collection, and the collection's metadata.

### 14.3. Reactive Testing with `StepVerifier`

Example integration test skeleton **requiring a fixture with a pre-created capped collection and a real MongoDB**:

```java
import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class DeviceEventTailIntegrationTest {

    private final ReactiveMongoTemplate template;

    DeviceEventTailIntegrationTest(ReactiveMongoTemplate template) {
        this.template = template;
    }

    @Test
    void tailReadsNewDocumentsAfterSeed() {
        // Fixture must create "device_events" as a capped collection
        // and clean old data at the collection level before running the test.
        DeviceEvent seed = new DeviceEvent(
                null, "system", "BOOTSTRAP", "ready", Instant.now());

        template.insert(seed, "device_events").block();

        Flux<DeviceEvent> stream = template.tail(
                Query.empty(), DeviceEvent.class, "device_events"
        ).take(2);

        StepVerifier.create(stream)
                .expectNextMatches(e ->
                        "BOOTSTRAP".equals(e.type()))
                .then(() -> template.insert(
                        new DeviceEvent(
                                null, "sensor-01", "TEMPERATURE",
                                "29.1", Instant.now()),
                        "device_events"
                ).block())
                .expectNextMatches(e ->
                        "TEMPERATURE".equals(e.type()))
                .verifyComplete();
    }
}
```

This is an **integration test skeleton**: supply actual constructor/fixture injection (`@SpringBootTest`, Testcontainers, or equivalent), isolated test namespaces, and finite timeouts. The two `block()` calls demonstrate synchronization in **test code**; never copy them into reactive application event loops.

The seed event ensures the cursor sees at least one document before awaiting new inserts, reducing races. If tests run concurrently with other producers, event counts and order may differ. Use isolated test namespaces.

### 14.4. Scale and Lifecycle Testing

On an appropriate replica set environment, run a variable-rate producer and simulate consumer pauses:

1. Create the capped collection using the calculated `size`.
2. Insert test data matching the production size distribution.
3. Monitor retained document count and time span between oldest and newest documents.
4. Make the consumer slower than the producer, and observe lag and cursor death events.
5. Restart the consumer and verify the business policy for lost events.
6. Measure the impact of multiple subscribers tailing the same collection.
7. After testing, clean up only the test namespace you own.

Do not treat `StepVerifier.withVirtualTime` as a substitute for a real MongoDB when testing storage rotation, collection locks, or driver interactions.

## 15. Common Errors and Troubleshooting

| Symptom | Possible Cause | Diagnosis |
| --- | --- | --- |
| `cannot use tailable cursor on a non-capped collection` | Collection exists but is not capped | `db.collection.isCapped()`; check bootstrap ordering |
| Error creating collection | Missing `size`, invalid value, insufficient permissions, or name collision | Inspect `createCollection` and MongoDB error |
| `collectionExists` returns true yet tail fails | Regular collection was auto-created by an insert first | Inspect metadata and apply controlled migration |
| Collection retains fewer documents than `max` | `size` threshold was reached first | Measure BSON sizes and insert rate |
| Data not retained for expected duration | Traffic increased, large documents, or `max` too small | Recompute sizing and observe actual retention |
| Tail receives no new events | Flux not subscribed, cursor closed, or collection empty on open | Check subscription, seed event, and lifecycle |
| Tail emits old documents | New cursor reads remaining documents in natural order | Design filtering/dedup per requirements |
| Consumer misses events after restart | Documents rotated out; no resume token | Increase capacity or change architecture if lossless required |
| `update` / `delete` rejected | Capped collection restriction | Use append-only writes or a regular collection |
| Sorting by an application field instead of natural order | Mixing regular query use cases with tailable | Use natural order for tail; separate projection for custom sorts |
| Multiple pods create the same collection | Race between exists check and create | Singleton migration, verify metadata on namespace-exists error |
| CPU/memory spike | Slow consumer, unbounded buffer, or large payloads | Bound concurrency, batch size, and monitor lag |

## 16. Implementation Checklist

- [ ] Verify the use case fits an **append-only buffer with finite retention**.
- [ ] Determine insert rate, BSON size, retention duration, and safety factor.
- [ ] Declare `capped: true` and `size` in bytes; add `max` only if genuinely needed.
- [ ] Ensure `size` is large enough to hold the target document count when `max` is set.
- [ ] Create the collection in migration/bootstrap **before** producers write the first record.
- [ ] Verify `isCapped() == true` and actual `size/max` metadata.
- [ ] Use `MongoTemplate`/`ReactiveMongoTemplate` with `CollectionOptions` if managed in Java.
- [ ] Ensure reactive create operations are properly subscribed/chained, never leaving an unsubscribed publisher.
- [ ] Ensure tailable cursors open on capped collections and handle the empty-collection case.
- [ ] Do not rely on a single tailable cursor to guarantee replaying all events after extended downtime.
- [ ] Monitor write rate, document size, actual retention, lag, and subscription lifecycle.
- [ ] Have a migration plan when resizing or changing collection type.

## 17. Practice Exercises

**Exercise 1 — Comparing limits.** Create three collections: (A) `size` 1 MiB; (B) `size` 1 MiB and `max` 50; (C) `size` 4 MiB and `max` 50. Insert 200 identically sized documents and predict which collection retains the most data. Then vary payload sizes to test your prediction.

**Exercise 2 — Sizing.** A service writes 75 events/second averaging 1,600 bytes/event, targeting 30 minutes retention with a safety factor of 2. Calculate the recommended `size` and minimum document count so `max` does not shorten retention. Clearly show the conversion between MB and MiB.

**Exercise 3 — Bootstrap.** Write a migration creating `audit_tail` with `MongoTemplate`. If the collection already exists as non-capped, the migration must fail with an actionable error instead of silently returning success.

**Exercise 4 — Reactive setup.** Write `Mono<Void> initialize()` that creates the capped collection if absent, verifies metadata, and only then allows `tail` to run. Explain why calling `initialize()` without subscribing has no effect.

**Exercise 5 — Behavior.** Create `ring_test` with `max: 3` and small documents. Insert A, B, C, D; describe exactly which documents remain. Try increasing payload sizes to observe how the `size` threshold changes the outcome.

**Exercise 6 — Stream.** Create `DeviceEventTailer`, insert a seed, open `tail()`, and insert 10 records. Use `StepVerifier` or a test subscriber with a timeout to prove new events arrive in natural order.

**Exercise 7 — System limits.** Assume a collection holds roughly 20,000 events max, the producer emits 500 events/second, and the consumer stops for two minutes. Calculate how many events are produced during the outage and explain why a capped collection cannot guarantee processing every event.

**Exercise 8 — Architecture.** Compare capped collections + tailable cursors against Change Streams and an offset-storing message broker. Recommend mechanisms for a near-real-time monitoring dashboard and for a payment stream that must never drop events.

## 18. Official Documentation and References

1. [MongoDB Manual — Capped Collections](https://www.mongodb.com/docs/manual/core/capped-collections/): storage characteristics, update/delete restrictions, tailable cursors, and related requirements.
2. [MongoDB Manual — db.createCollection](https://www.mongodb.com/docs/manual/reference/method/db.createCollection/): `capped`, `size`, and `max` format during collection creation.
3. [MongoDB Manual — Tailable Cursors](https://www.mongodb.com/docs/manual/core/tailable-cursors/): cursor lifecycle, natural order, and empty collection behavior.
4. [Spring Data MongoDB — Tailable Cursors](https://docs.spring.io/spring-data/mongodb/reference/mongodb/tailable-cursors.html): `ReactiveMongoTemplate.tail` and usage with capped collections.
5. [Spring Data MongoDB — CollectionOptions API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/CollectionOptions.html): configuring capped/size/maxDocuments by version.
6. [Spring Data MongoDB — MongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/MongoTemplate.html): `createCollection` and `collectionExists`.
7. [Spring Data MongoDB — ReactiveMongoTemplate API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): creating collections and reactive tailing with Reactor.

Collection operation limits, drivers, and migration syntax may vary across MongoDB and Spring Data versions. When implementing, verify against the exact versions in operation and validate behavior in a production-like environment.

**Expected outcome:** you should be able to create a capped collection with the required `size`, know when `max` is appropriate, prove the collection evicts older documents automatically, use `MongoTemplate` or `ReactiveMongoTemplate` to create/verify configuration, and open a `Flux` via `tail(...)` on that collection.
