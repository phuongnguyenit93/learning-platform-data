# Standard Collections and Capped Collections in MongoDB

In MongoDB, a **collection** holds BSON documents. Even though both are collections, how they manage data can differ dramatically: a standard collection suits business data that must be stored, queried, and updated according to its own lifecycle; a **capped collection** has a fixed allocated storage limit, behaves like a circular buffer, and automatically overwrites/evicts the oldest documents when limits are reached.

Choosing the wrong collection type leads to real consequences: records can vanish silently in a capped collection, delete operations or document-growing updates may be rejected, and event-reading applications can miss data if they consume too slowly. Conversely, when you need a bounded short-lived log or event stream, capped behavior can be more practical than manually bulk-deleting records after every write.

This lesson focuses on **standard collections and capped collections**: storage mechanics, creation and management, CRUD constraints, document ordering, tailable cursors, use cases, and hands-on practice with the MongoDB Shell.

## 1. What Is a Collection?

MongoDB organizes data according to this hierarchy:

~~~text
MongoDB deployment
└── Database: shop
    ├── Collection: customers
    │   ├── Document {_id: ..., name: "An", ...}
    │   └── Document {_id: ..., name: "Binh", ...}
    ├── Collection: orders
    │   ├── Document {_id: ..., total: ..., ...}
    │   └── ...
    └── Collection: activityBuffer (capped)
        ├── Newer events
        └── Older events, evicted when limits are reached
~~~

In relational databases, we often liken a collection to a table and a document to a row. However, MongoDB documents are BSON and can contain nested objects or arrays; documents in the same collection do not necessarily share identical fields unless the application or database enforces schema validation.

Example of two documents in the same collection:

~~~javascript
{
  _id: ObjectId("66f1c2a4b1d2e3f405162738"),
  name: "An",
  contact: { email: "an@example.test" }
}

{
  _id: ObjectId("66f1c2a4b1d2e3f405162739"),
  name: "Binh",
  preferences: ["email", "sms"]
}
~~~

A collection can also have **indexes**, validation rules, collation settings, and other properties. The collection type dictates key constraints on how documents are written and evicted.

## 2. Two Collection Types Solving Two Different Needs

### 2.1. Standard Collection

This is the default choice in most MongoDB applications. Documents persist until an explicit update, delete, replace, collection drop, or a clearly configured automatic mechanism such as a TTL index removes them.

For example, the **orders** collection in an e-commerce application:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "C-001",
  total: 250000,
  status: "PENDING",
  items: [
    { sku: "BOOK-01", quantity: 2 }
  ]
}
~~~

With this collection type, the application can update order status, add a `trackingCode` field, delete orders under valid authorization, query with indexes, or retain long-term history. MongoDB **does not automatically delete old documents just because the collection grows large**.

### 2.2. Capped Collection

A capped collection is a collection with **a storage size limit specified at creation time**. It uses a circular-buffer storage pattern: new documents are appended, and once limits are reached, the oldest documents are automatically evicted to make space for incoming data.

For example, a buffer keeping the most recent few thousand status notifications:

~~~javascript
{
  _id: 9001,
  time: ISODate("2026-11-14T03:00:00Z"),
  service: "checkout",
  level: "INFO",
  message: "Request accepted"
}
~~~

Over time, the system retains recent notifications while older ones disappear according to the storage limit. This is **intended by-design behavior** of a capped collection, not a MongoDB data-loss bug.

Mental model:

~~~text
Capped collection: max 4 documents

Initially:     [A] [B] [C] [D]
Insert E:          [B] [C] [D] [E]    (A is evicted)
Insert F:              [C] [D] [E] [F]    (B is evicted)
~~~

The diagram illustrates logical ordering; MongoDB manages data files internally and does not necessarily lay out bytes as a simple array like the diagram.

## 3. High-Level Comparison Table

| Criterion | Standard Collection | Capped Collection |
|---|---|---|
| Creation | Implicit on first write or explicit via `db.createCollection()` | Must specify `capped: true` and `size` at creation |
| Primary purpose | Store business data with an arbitrary lifecycle | Maintain a size-bounded data buffer |
| Storage size limit | No fixed size cap imposed by collection type | Configured `size` limit in bytes |
| Document count limit | No fixed count cap imposed by collection type | Optional `max`; still bound by `size` |
| When new writes exceed limits | Continues growing if system resources allow | Automatically evicts oldest documents to make room |
| Deleting individual documents | Supports `deleteOne()`, `deleteMany()` | Does not allow deleting individual documents in the normal way |
| Updating documents | Can grow or shrink documents if operation is valid | Cannot perform updates that change document size beyond capped limits |
| Natural order | Not a stable business order | Organized to preserve insertion order, useful for sequential scans |
| Tailable cursors | Not supported | Supported for reading newly appended data in natural order |
| Indexes | Supported | Supports indexes, though write cost and query needs must be weighed |
| Sharding | Can be sharded if configuration requirements are met | Sharding capped collections is not supported |
| Time-based TTL | Can use TTL indexes when appropriate | Not intended for time-based retention via TTL |
| Typical use cases | Customers, orders, products, accounts, long-term audits | Short-term logs, transient events, observation buffers |

**Neither type is universally better for every scenario.** A capped collection trades away flexible editing and permanent retention in exchange for automatic size/count-bounded lifecycle eviction.

## 4. Creating and Working with Standard Collections

The examples in this lesson run in **mongosh**. You need a MongoDB deployment where you have privileges to create collections and write data. Never use a production database; create a separate one:

~~~javascript
use collection_lab
~~~

The `use` command selects the working database in the shell. The database is only materialized once data or metadata is created.

### 4.1. Explicit Collection Creation

~~~javascript
db.createCollection("customers")

db.customers.insertMany([
  {
    _id: "CUS-001",
    name: "An",
    status: "ACTIVE",
    tags: ["new"]
  },
  {
    _id: "CUS-002",
    name: "Binh",
    status: "ACTIVE",
    tags: []
  }
])
~~~

When creating a standard collection, you do not specify `capped` or `size`. You can also let MongoDB **auto-create the collection on the first insert**:

~~~javascript
db.products.insertOne({
  sku: "PEN-01",
  name: "Pen",
  stock: 10
})
~~~

If `products` does not exist yet, the first write creates a **standard collection**, never automatically turning it into a capped collection.

### 4.2. CRUD Operations

~~~javascript
// Read data
db.customers.find({ status: "ACTIVE" })

// Update, which can add new fields and change document size
db.customers.updateOne(
  { _id: "CUS-001" },
  { $set: { phone: "0900000000", status: "VERIFIED" } }
)

// Append an element to an array
db.customers.updateOne(
  { _id: "CUS-001" },
  { $push: { tags: "vip" } }
)

// Delete one document matching a filter
db.customers.deleteOne({ _id: "CUS-002" })
~~~

These operations belong to an application-controlled data lifecycle. The collection does not evict documents on a ring-buffer schedule.

### 4.3. Indexes and Result Ordering

~~~javascript
db.customers.createIndex({ status: 1, name: 1 })

db.customers
  .find({ status: "VERIFIED" })
  .sort({ name: 1 })
~~~

**Do not rely on default document order from `find()`.** Whenever results are required by name, creation date, sequence number, or business key, specify an explicit sort and design appropriate indexes. Physical/natural order can shift as data or query execution plans change.

## 5. Creating a Capped Collection

A capped collection must be configured at creation time:

~~~javascript
db.createCollection("eventBuffer", {
  capped: true,
  size: 1024 * 1024,
  max: 1000
})
~~~

Meaning:

- **capped: true**: tells MongoDB to create a capped collection.
- **size: 1024 * 1024**: sets the size cap to 1 MiB, specified in bytes in this example.
- **max: 1000**: sets the configured maximum document count.

**`size` is required** when creating a capped collection, while **`max` is optional**. If only `size` is set, eviction is governed by byte capacity. If both `size` and `max` are set, the collection evicts documents whenever **either limit is reached**; `max` does not override the `size` ceiling.

Note that `size` is the limit for the collection's own storage mechanism, not an exact quota for the database's total disk usage. Indexes, metadata, the journal, and other collections still consume their own resources.

### 5.1. Verifying the Created Collection Type

~~~javascript
db.eventBuffer.isCapped()
~~~

The expected result is `true`. View metadata:

~~~javascript
db.getCollectionInfos({ name: "eventBuffer" })
~~~

The returned information includes an `options` section where you can observe the stored `capped`, `size`, and `max` settings. You can also inspect collection statistics:

~~~javascript
db.eventBuffer.stats()
~~~

Statistical fields and size reporting details can vary by MongoDB version or storage engine. To check whether a collection is capped, **`isCapped()`** is the most direct and readable check.

### 5.2. Accidentally Wrote Data Before Creating the Capped Collection?

This is a common mistake:

~~~javascript
db.events.insertOne({ message: "First event" })

db.createCollection("events", {
  capped: true,
  size: 1048576
})
~~~

The preceding insert already created **events** as a standard collection. Calling `createCollection` with the same name will not automatically upgrade the collection and typically raises a namespace-already-exists error. When you want a capped collection, create it with the proper options **before the first write**, or execute an intentional data conversion plan.

MongoDB provides the **`convertToCapped`** mechanism to convert a standard collection to a capped collection in supported situations. Conversion can drop older documents if the data exceeds the new size, so take backups, check server version/permissions, and assess impact beforehand. This is not an operation for quick fixes of mistakes in production.

## 6. Hands-On Eviction Lifecycle Practice

To observe the effect directly, create a capped collection **dedicated to this experiment** with a small `max`. The following commands do not use `eventBuffer` from earlier:

~~~javascript
db.createCollection("tinyEvents", {
  capped: true,
  size: 1024 * 1024,
  max: 4
})
~~~

Here 1 MiB is plenty for a few tiny example documents; **`max: 4`** is much easier to observe than a byte limit.

Insert four events:

~~~javascript
db.tinyEvents.insertMany([
  { _id: 1, seq: 1, message: "Event A" },
  { _id: 2, seq: 2, message: "Event B" },
  { _id: 3, seq: 3, message: "Event C" },
  { _id: 4, seq: 4, message: "Event D" }
])

db.tinyEvents
  .find({}, { _id: 1, seq: 1, message: 1 })
  .sort({ $natural: 1 })
~~~

With no other concurrent writers, the four documents are scanned in insertion order. Continue:

~~~javascript
db.tinyEvents.insertMany([
  { _id: 5, seq: 5, message: "Event E" },
  { _id: 6, seq: 6, message: "Event F" }
])

db.tinyEvents
  .find({}, { _id: 1, seq: 1, message: 1 })
  .sort({ $natural: 1 })

db.tinyEvents.countDocuments({})
~~~

In a single-writer lab environment, you will see the newest documents (typically `seq` 3, 4, 5, 6) and a total count of 4. Documents `seq` 1 and 2 have been automatically evicted.

This is the **rollover** behavior of a capped collection: new writes cause the oldest data to disappear once limits are reached. `insertMany` still reports success for all newly written documents even as older documents are evicted during the write.

### 6.1. How `size` and `max` Work Together

Consider a collection:

~~~javascript
db.createCollection("recentMessages", {
  capped: true,
  size: 2 * 1024 * 1024,
  max: 500
})
~~~

Two cases:

1. If each document is small, the collection may reach 500 documents before reaching 2 MiB. Old documents are evicted by the count threshold.
2. If each document is large, the collection may reach the byte limit before holding 500 documents. In that case, fewer than 500 documents are actually retained.

Therefore, **`max` does not guarantee that the collection always retains a full `max` recent documents**. The actual number retained depends on document size and storage limits.

If a single new document is too large relative to the limits or violates storage constraints, the write can fail. A capped collection does not make an oversized document valid.

### 6.2. Capped Collections Do Not Guarantee Retention by Number of Days

Suppose `size` is set to 100 MiB for logs:

- On a normal day, the application writes sparingly; 100 MiB may hold several days of data.
- During an incident, log volume spikes; 100 MiB may hold only a few hours.

This means a capped collection **does not provide a guarantee to retain data for exactly 7 days** or any fixed time window. If the system requires keeping records for a defined duration, design a time-based lifecycle, such as a TTL index on a standard collection or another appropriate storage mechanism.

Even a TTL index deletes asynchronously via the TTL monitor, so never use TTL to promise millisecond-exact expiration.

## 7. Insertion Order and `$natural`

A key trait of capped collections is that documents are stored in insertion order to support sequential scanning. MongoDB supports sorting by **`$natural`**:

~~~javascript
// Read in forward natural order
db.tinyEvents.find().sort({ $natural: 1 })

// Read in reverse natural order
db.tinyEvents.find().sort({ $natural: -1 })
~~~

In a capped collection, natural order generally corresponds to insertion order. This is handy when reading a short-term log from oldest to newest or newest to oldest without maintaining an extra sequence field solely for inspection.

However, distinguish carefully between:

- **Insertion order:** the order in which MongoDB writes documents into the collection.
- **Event timestamp:** a timestamp field attached by the application; clocks across clients can skew.
- **Business order:** such as `orderNumber` or `eventSequence` assigned by the domain.

These three orders **do not necessarily match** in systems with multiple writers, late-arriving data, or concurrent processing. If the business requires deterministic sorting, store a timestamp and tie-breaker/sequence key and sort explicitly:

~~~javascript
db.eventBuffer.find().sort({
  producedAt: 1,
  eventId: 1
})
~~~

In a standard collection, never treat `$natural` as a business ordering contract. Indexed queries, updates, storage layout, or deployment changes can alter the observed order.

## 8. CRUD Capabilities and Specific Limitations of Capped Collections

### 8.1. Insert

Capped collections accept inserts just like standard collections, provided documents are valid and fit within storage limits:

~~~javascript
db.eventBuffer.insertOne({
  level: "INFO",
  message: "Health check passed",
  producedAt: new Date()
})
~~~

The difference is that new inserts can cause the oldest documents to be automatically evicted. Thus, a successful write **does not guarantee the document will remain stored indefinitely**.

### 8.2. Updates Cannot Arbitrarily Change Document Size

In a standard collection, you can normally add new fields:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-001" },
  { $set: { notes: "Frequent customer" } }
)
~~~

In a capped collection, **MongoDB restricts updates that change document size**, because that conflicts with capped fixed-space storage mechanics. For instance, updating a short message to a much longer string or adding several new fields can fail.

Accordingly, treat a capped collection as an **append-mostly, read-mostly stream**, rather than a place where records constantly mutate in content or size.

If an event must be updated across multiple steps, keep the current state in a standard collection; a capped collection, if used, should hold only emitted event records.

### 8.3. Individual Deletes Are Not Supported

On a standard collection:

~~~javascript
db.customers.deleteOne({ _id: "CUS-001" })
~~~

On a capped collection, deleting individual documents or deleting by filter is not supported in the normal way:

~~~javascript
// Cannot be used to delete a single event from a capped collection
db.eventBuffer.deleteOne({ level: "INFO" })
~~~

Documents in a capped collection disappear via **automatic eviction when writes exceed limits**, or when the entire collection is dropped administratively. Disallowing selective deletion is an important design constraint.

### 8.4. Drop, Truncate, and Recreate

If you want to empty a capped collection in a practice environment, you can **drop and recreate it** with the corresponding options:

~~~javascript
// Use only on test collections whose data does not need to be kept.
db.tinyEvents.drop()

db.createCollection("tinyEvents", {
  capped: true,
  size: 1024 * 1024,
  max: 4
})
~~~

`drop()` deletes the entire collection and its indexes. It is a destructive operation, not a conditional delete.

When you need to change `size`, `max`, or convert collection types in a real system, prepare a migration plan, backups, client impact assessment, and downtime window. Do not assume all capped options can be updated in place via routine metadata commands.

### 8.5. Indexes Still Exist but Do Not Alter Rollover Mechanics

A capped collection can have indexes to support appropriate queries:

~~~javascript
db.eventBuffer.createIndex({
  level: 1,
  producedAt: -1
})
~~~

Indexes help field-based queries, though they also add storage and write-maintenance overhead. Indexes **do not prevent documents from being evicted** when the capped collection exceeds its limits and do not turn a capped collection into long-term historical storage.

If the workload only tails newly arrived events sequentially via a tailable cursor, complex indexes may be unnecessary. If you need multi-dimensional filtering and long-term data retention, a standard collection with well-designed indexes is usually a better choice.

## 9. Tailable Cursors: Reading Data Continuously from a Capped Collection

A **cursor** in MongoDB is the mechanism clients use to iterate through query results in batches. A normal cursor reaches the end of the result set and closes.

A **tailable cursor** is a special cursor type for capped collections: it can stay open, wait, and receive newly appended documents after reading all existing ones. The concept resembles `tail -f` on a log file:

~~~text
Application A writes events
       |
       v
  [capped collection]
       |
       v
Application B opens tailable cursor
       |
       +-- Reads existing events
       +-- Waits for new events
       +-- Reads new events
       +-- Continues while the cursor remains valid
~~~

A tailable cursor is tightly coupled to the **natural order** of a capped collection. It is not a cursor that can sort arbitrarily using any index; if the application requires a different business order, redesign the access pattern.

### 9.1. Example with the MongoDB Java Sync Driver

Assume MongoDB already has a capped collection `collection_lab.eventBuffer` containing at least one document. A Java application using the MongoDB Java Sync Driver can tail it:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.CursorType;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class TailableEventReader {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("collection_lab")
                    .getCollection("eventBuffer");

            try (MongoCursor<Document> cursor = events.find()
                    .cursorType(CursorType.TailableAwait)
                    .maxAwaitTime(1, TimeUnit.SECONDS)
                    .iterator()) {

                while (cursor.hasNext()) {
                    Document event = cursor.next();
                    System.out.println(event.toJson());
                }
            }
        }
    }
}
~~~

**How to read this example:**

1. The MongoDB driver opens a cursor in **`TailableAwait`** mode.
2. After reaching the end of current documents, the server waits briefly to return newly inserted documents instead of terminating immediately like a normal query.
3. The client iterates and processes documents as they are appended to the capped collection.
4. If the cursor becomes invalid or closes, this illustrative snippet exits. Production systems must implement reconnect/resume logic per application requirements.

A tailable cursor can become invalid if older data rolls over past the read position, if the collection is dropped, or if the connection fails. On an empty collection, some ways of opening a tailable cursor may also fail to wait as expected. Never treat this as a messaging mechanism guaranteeing every event is processed exactly once.

### 9.2. A Tailable Cursor Is Not a Durable Message Queue

If a consumer stops for an extended time, the capped collection can evict events it has not yet read. Upon restart, data already removed from the buffer **cannot be recovered** through the tailable cursor alone.

Nor do tailable cursors provide built-in:

- Per-message acknowledgements.
- Retries, dead-letter queues, and multi-consumer-group coordination.
- Guarantees that slow consumers will not lose data.
- Exactly-once processing semantics.

If business requirements involve payment processing, critical jobs, or durable message delivery, use a dedicated queue/stream system or an explicit persisted-checkpoint and recovery design.

### 9.3. Distinguishing from MongoDB Change Streams

**Change Streams** allow tracking MongoDB data changes through a dedicated API in supported environments, typically a replica set or sharded cluster. Change Streams do not require converting business collections into capped collections and offer resume tokens under the Change Streams contract.

| Aspect | Tailable Cursor on Capped | Change Streams |
|---|---|---|
Data source | Reads new documents from a capped collection | Watches change events on a supported collection/database/deployment |
| Infrastructure requirement | Capped collection | Supported replica set or sharded cluster |
| Observed payload | Documents in the collection | Change events with metadata and configurable details |
| Recovery | Must track read position yourself and accept that data may have rolled over | Provides resume tokens, subject to oplog/history limits and retention window |
| Suitable use case | Simple log/event buffer where dropping old items is acceptable | Observing inserts/updates/deletes in MongoDB data |

Change Streams also do not turn MongoDB into an infinite message queue or guarantee retaining all history forever; resumability still depends on available change history and client error handling.

## 10. When Should You Choose a Standard Collection?

A standard collection should be the default choice whenever data has **lasting business value** or requires document-level operations.

### 10.1. Customer Data and Profiles

Customer information must persist, be editable, and remain queryable regardless of how many new customers register:

~~~javascript
db.customers.updateOne(
  { _id: "CUS-100" },
  {
    $set: {
      name: "Minh",
      preferences: { language: "vi" },
      updatedAt: new Date()
    }
  },
  { upsert: true }
)
~~~

A capped collection is unsuitable because older profiles would be evicted as new profiles arrive, and changing document sizes would be restricted.

### 10.2. Orders, Payments, Inventory

These records may need long-term retention, status updates, audits, and explicit deletion policies. Having an older order disappear automatically because many new orders arrived is unacceptable.

### 10.3. Data with an Explicit Expiration Time

For example, storing login sessions until `expireAt`:

~~~javascript
db.createCollection("sessions")

db.sessions.createIndex(
  { expireAt: 1 },
  { expireAfterSeconds: 0 }
)

db.sessions.insertOne({
  tokenHash: "example-hash",
  userId: "U-001",
  expireAt: new Date(Date.now() + 60 * 60 * 1000)
})
~~~

A TTL index removes expired records according to a time-based policy. Deletion runs asynchronously, so it is not an instantaneous expiration timer. For security-sensitive operations, the application must still check `expireAt` itself when deciding whether a token remains valid.

Fundamental difference:

~~~text
Standard collection + TTL:
    Expires per document based on timestamp
    (asynchronous deletion)

Capped collection:
    Evicts oldest documents when new writes hit
    size or max limits (not time-based)
~~~

If no new inserts arrive, a capped collection can hold old documents far longer than any predicted number of days.

## 11. When Can You Choose a Capped Collection?

A capped collection is a better fit when data is a **short-lived stream where dropping the oldest items is acceptable**, the byte budget for the buffer is fairly clear, and the workload is primarily insert/read.

### 11.1. Recent Log Buffer

For example, an application wants to show the N most recent events on an ops screen, while canonical logs are already stored elsewhere for auditing or long-term investigation:

~~~javascript
db.createCollection("diagnosticLog", {
  capped: true,
  size: 50 * 1024 * 1024,
  max: 20000
})
~~~

This design only makes sense when losing old events from the buffer **is acceptable**. If logs serve regulatory compliance, security monitoring, or long-term incident forensics, use durable storage with explicit retention.

### 11.2. Short-Term Event Watching for Developer Tools

A demo application can write an event stream to a capped collection so clients using tailable cursors can observe new messages:

~~~javascript
db.diagnosticLog.insertOne({
  at: new Date(),
  component: "payment-demo",
  level: "DEBUG",
  message: "Simulated request started"
})
~~~

As new data streams in, older events disappear while the demo app continues observing the recent stream. This is convenient for experimentation, not an event-sourcing store.

### 11.3. Cases Where You Should Consider Other Solutions

- **Time-series metrics and sensors:** look into MongoDB time series collections, time-based retention, and per-series query patterns.
- **Mandatory audits, financial history:** standard collections or archival storage with explicit retention and backups.
- **Job queues:** dedicated queue/stream systems or durable job-state tables that never silently drop pending work.
- **Recent-record lists with complex filtering:** standard collections with indexes, TTL, or maintenance jobs are often easier to satisfy business rules with.
- **Data requiring sharding:** capped collections do not support sharding.

The key rule is that the **data-eviction policy** must match business needs. If you cannot accept a record vanishing when new records arrive, do not choose a capped collection.

## 12. Sizing a Capped Collection

Setting `size` too small causes slow consumers to lose data quickly. Setting `size` too large wastes buffer capacity without adding any time-retention guarantees. Estimate based on actual write rates.

### 12.1. Rough Size Estimation

Suppose:

- The system writes an average of **100 events/second**.
- Each BSON document averages around **500 bytes**.
- You want the theoretical buffer to hold roughly **30 minutes** of data.

Expected document count:

\[
100\ \text{event/s} \times 30 \times 60\ \text{s}
= 180{,}000\ \text{event}
\]

Raw volume:

\[
180{,}000 \times 500\ \text{byte}
= 90{,}000{,}000\ \text{byte}
\approx 85.8\ \text{MiB}
\]

This is only an **estimate**. Actual BSON storage has overhead, individual document sizes vary, and traffic can spike. Add a safety margin and measure empirically using representative production-like data.

Example pilot configuration:

~~~javascript
db.createCollection("measuredEvents", {
  capped: true,
  size: 128 * 1024 * 1024
})
~~~

Do not call 128 MiB a promise to retain exactly 30 minutes; if the write rate jumps severalfold, record lifetime shrinks proportionally. To guarantee time-based retention, use a different retention mechanism.

### 12.2. Why Measure with Real Data?

Documents containing long messages, metadata, stack traces, or large payloads cause per-event size to vary wildly. Index count and storage engine resources also affect overall operational cost.

Observe with:

~~~javascript
db.measuredEvents.stats()
db.measuredEvents.countDocuments({})
~~~

In production, monitor insert rate, average document size, consumer lag/rate, age of the oldest retained record, cursor read errors, and disk utilization. Each metric answers a different question; knowing the configured `size` alone does not prove every consumer keeps up.

### 12.3. `size` Is Not a System-Wide Disk Quota

Even when a capped collection has `size` set to 128 MiB, disk also holds indexes, the journal, metadata, other databases, and internal files. Never treat a single capped collection's `size` as proof that the entire MongoDB container uses at most 128 MiB of disk.

## 13. Interacting with Java / Spring Data MongoDB Applications

A Java application using the MongoDB Java Driver can read and write both collection types through the `MongoCollection` API. **The difference lies in collection configuration and server-enforced constraints**, not in the Java class name.

### 13.1. Writing Documents from Java

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import java.util.Date;

public class WriteDiagnosticEvent {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> events = client
                    .getDatabase("collection_lab")
                    .getCollection("eventBuffer");

            events.insertOne(new Document("level", "INFO")
                    .append("message", "Java client started")
                    .append("producedAt", new Date()));
        }
    }
}
~~~

This code only performs an insert; for **`eventBuffer` to actually be capped**, the collection must have been created beforehand with the right options. Merely calling `getCollection()` or `insertOne()` **does not create a capped collection**.

If the collection does not yet exist and the insert has sufficient permissions, MongoDB will create a standard collection. Therefore, in projects requiring capped collections, manage database/collection initialization deliberately and verify metadata during deployment.

### 13.2. Creating a Capped Collection with `MongoTemplate`

In a project configured with Spring Data MongoDB, you can use `MongoTemplate` to create it:

~~~java
import org.springframework.data.mongodb.core.CollectionOptions;
import org.springframework.data.mongodb.core.MongoTemplate;

public class MongoCollectionSetup {
    private final MongoTemplate mongoTemplate;

    public MongoCollectionSetup(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public void createEventBufferIfMissing() {
        if (!mongoTemplate.collectionExists("eventBuffer")) {
            mongoTemplate.createCollection(
                    "eventBuffer",
                    CollectionOptions.empty()
                            .capped()
                            .size(1024L * 1024L)
                            .maxDocuments(1000L)
            );
        }
    }
}
~~~

This is an API snippet showing collection setup, not a complete migration workflow. Checking `collectionExists` followed by `createCollection` are two separate operations, so multiple instances starting simultaneously can race. In real deployments, use a one-time schema/migration step, handle already-exists errors, and verify that the existing collection is actually capped with the expected options.

Never see `collectionExists("eventBuffer")` return `true` and blindly assume its type and size are right.

### 13.3. Designing a Dedicated Model for the Buffer

An event suited for a capped collection typically has a fairly stable structure:

~~~javascript
{
  eventId: "evt-2026-001",
  occurredAt: ISODate("2026-11-14T03:15:00Z"),
  source: "checkout",
  level: "INFO",
  message: "Completed",
  code: 200
}
~~~

Fields to pay attention to:

- **eventId** helps applications correlate messages; define a unique generation scheme if the business requires it.
- **occurredAt** records the business timestamp; it does not control when the document is evicted.
- **level/source** aid filtering during inspection; index choices depend on the workload.
- **message** can grow unexpectedly long, reducing how many events the capped collection holds; enforce sensible payload limits.

Applications should handle insert errors and never depend on a record still being present after a fixed time interval.

## 14. Common Limitations and Misconceptions

| Symptom | Cause or Correct Understanding | How to Handle |
|---|---|---|
| `db.createCollection` reports collection already exists | An earlier insert may have created a standard collection | Check `isCapped()` and metadata; create collections via controlled initialization |
| Old documents vanish on their own | Capped rollover evicted records when `size`/`max` limits were hit | Confirm this is intended; increase capacity to hold more, or switch storage model |
| Capped has `max: 1000` yet holds only 200 documents | The byte limit was reached before the count limit | Measure document size and adjust `size` to match requirements |
| Capped keeps records much longer than expected | Insufficient new writes to trigger rollover | Use time-based retention in an appropriate model if a fixed lifespan is required |
| `deleteOne`/`deleteMany` on capped raises an error | Capped collections do not support selective deletes | Use a standard collection if document-level deletion is needed |
| Updates adding fields are rejected | Capped collections restrict document size changes | Use immutable event schemas or switch to a standard collection |
| Tailable cursor cannot read when opened on a standard collection | Tailable cursors are only for capped collections | Verify the collection type or pick the appropriate API |
| Tailable cursor stops working | Connection drop, invalidated cursor, rollover past read point, or empty-collection behavior | Design reconnect/recovery logic and accept data-loss boundaries |
| `find()` results are not in timestamp order | Insertion order differs from business event timestamps | Add sequence/timestamp fields and sort explicitly |
| Created capped with small `size` yet disk usage keeps growing | `size` does not govern indexes, journal, or other databases | Monitor full-deployment storage and design separate quotas/monitoring |
| Using capped to guarantee 7-day retention | Capped retains by space/count, not wall-clock time | Use TTL, time series, or another archival workflow |
| Cannot shard a capped collection | Collection-type limitation | Move data design to a collection type supporting sharding when needed |

### 14.1. A Note on Performance

Capped collections are designed to operate within bounded space and support convenient sequential reads. However, there is no basis to conclude that every insert or query on a capped collection is **always faster** than on a standard collection.

Performance depends on workload, indexes, document size, concurrency, storage engine, hardware, and rollover pressure. Benchmark against a realistic workload before choosing one purely on speed assumptions.

### 14.2. A Note on Data Safety

A capped collection is **not a backup**, not a historical archive, and provides no guarantee of preserving older records. If an application uses a capped collection as the sole store for critical data, record eviction on limit rollover is a design flaw.

Standard collections also require backup policies, access controls, capacity monitoring, and recovery plans. The difference is that standard documents **are not automatically evicted by a circular-buffer cap**.

## 15. Hands-On Exercises

### Exercise 1. Classifying Requirements

Select the most appropriate collection type and explain why:

1. Active user accounts, where email and address can be edited.
2. A display buffer showing the latest 2,000 log lines for a debug dashboard.
3. Orders requiring historical retention per business policy.
4. Sessions expiring after the `expireAt` timestamp stored in each document.
5. An experimental status board where viewers can afford to miss older notices.

**Guidance:** (1) and (3) require standard collections; (2) and (5) can consider capped collections if automatic eviction of old data is acceptable; (4) uses a standard collection with a TTL index plus application-side validity checks.

### Exercise 2. Observing Rollover

Create a capped collection **`practiceBuffer`** with `size` equal to 1 MiB and `max` equal to 3. Insert 5 documents with `seq` from 1 to 5. Then run:

~~~javascript
db.practiceBuffer.isCapped()

db.practiceBuffer
  .find({}, { seq: 1 })
  .sort({ $natural: 1 })

db.practiceBuffer.countDocuments({})
~~~

**Expected result:** `isCapped()` is `true`, and at most 3 documents remain. If documents are small and there are no other writers, the remaining `seq` values are typically 3, 4, and 5. Explain why documents `seq` 1 and 2 disappeared without calling `deleteOne()`.

### Exercise 3. Explaining `size` and `max`

A capped collection has:

~~~javascript
{
  capped: true,
  size: 1048576,
  max: 1000
}
~~~

Meanwhile, each document averages about 10 KiB. Is it guaranteed to retain 1,000 documents? Why or why not?

**Guidance:** No. The 1 MiB limit will be reached after roughly a hundred ~10 KiB documents (approximately), so fewer documents than `max` will be retained.

### Exercise 4. Evaluating Tailable Cursors

A client reads events using a tailable cursor. Later the client goes offline for several hours while the producer writes millions of new events and the capped collection rolls over old events.

Answer:

1. Can the client use the same old cursor to read back all evicted events?
2. Can a tailable cursor be called a queue that guarantees delivery of every message?
3. If the business requires zero event loss, how would you redesign it?

**Guidance:** Evicted events are gone and cannot be re-read; a tailable cursor does not guarantee durable delivery. Retain data long enough, persist consumer offsets, or adopt a stream/queue system with proper recovery mechanisms.

### Exercise 5. Choosing Query Patterns

You have a standard collection `orders` and a capped collection `eventBuffer`. Write queries for:

~~~javascript
// Orders by newest creation time, with a tie-breaker key
db.orders.find().sort({ createdAt: -1, _id: -1 })

// Event buffer in natural order from oldest to newest
db.eventBuffer.find().sort({ $natural: 1 })
~~~

Explain why the first query sorts by a **business rule**, while the second relies on the **storage order** of a capped collection. Also state why `$natural` on a standard collection should not be treated as a stable chronological order.

## 16. Selection Principles in Real Projects

Before creating a collection, answer three questions:

1. **Can data disappear automatically when the buffer fills up?** If not, choose a standard collection or a long-term storage design.
2. **Do documents need to be updated, selectively deleted, or grown in size?** If yes, a standard collection is a better fit.
3. **Does the application need to stream newly appended items or run flexible business queries?** Capped collections support tailable cursors in natural order; standard collections combined with indexes, Change Streams, or a dedicated streaming architecture serve other needs.

A **standard collection** holds data whose lifecycle is controlled by the application. A **capped collection** is a bounded storage buffer that automatically evicts older documents to make room for new ones and supports tailable cursors. Understanding this difference helps you design MongoDB schemas fit for purpose, avoid unintended data loss, and pick the right event-consumption mechanism.
