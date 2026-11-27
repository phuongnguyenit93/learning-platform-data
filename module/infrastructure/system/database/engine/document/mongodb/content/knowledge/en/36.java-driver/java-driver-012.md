# Integrating Change Streams, Resume Tokens, and Graceful Shutdown with MongoDB Java Driver

> **Module:** Database Engine Document MongoDB  
> **Chapter:** Java Driver  
> **Lesson:** Integrating change streams, resume tokens, and graceful shutdown

## 1. Opening Problem: When an Event Is Processed Twice or Missed

A Java service processes orders in the `orders` collection. Whenever an order transitions to `PAID`, the system needs to:

- update an `order_read_model` read table;
- dispatch a sync task to a reporting tool;
- persist reading progress so deployments and restarts can pick up seamlessly;
- shut down cleanly when Kubernetes signals pod termination.

The engineering team writes:

```java
collection.watch().forEach(change -> {
    publishToAnotherSystem(change);
});
```

That snippet captures changes while running, yet leaves four operational questions unanswered:

1. If processing finishes but the app **crashes before persisting progress**, will the event be reprocessed?
2. If progress is saved **before** calling the external system and the process crashes, could the event be skipped forever?
3. If the app receives `SIGTERM` while `next()` blocks waiting for events, how does it exit and close the MongoDB cursor without losing in-flight work?
4. If the pod stays down for days and the oplog rolls past the resume point, can it simply reopen the stream "from now" without creating a data gap?

Solving these requires **MongoDB Change Streams + Java Driver + durable checkpointing + idempotent processing + graceful shutdown**. A reliable service needs all five—not `watch()` alone.

### 1.1. Learning Objectives

After this lesson, you will be able to:

1. Explain how change streams rely on the oplog and scope across collections, databases, or deployments.
2. Open change streams via the Java Sync Driver and manage `MongoChangeStreamCursor`.
3. Distinguish `tryNext()`, `next()`, `hasNext()`, await timeouts, and cursor resources.
4. Read `insert`/`update`/`replace`/`delete`/`invalidate` events, `documentKey`, `updateDescription`, and `fullDocument`.
5. Understand resume token `_id` and `postBatchResumeToken`, without fabricating or mutating tokens.
6. Distinguish `resumeAfter()`, `startAfter()`, and `startAtOperationTime()`.
7. Design checkpoints persisted **after processing** for **at-least-once** guarantees paired with idempotency to tolerate replay.
8. Distinguish resumable failures from expired oplog history, collection invalidations, or incompatible pipeline changes.
9. Build a Java loop with a stop flag, bounded polling, `try-with-resources`, and a shutdown hook.
10. Coordinate single- or multi-instance consumers using leases, fencing, and partitioning.
11. Configure metrics, alerting, runbooks, and safe labs on a test replica set.

## 2. Change Streams in Application Architecture

Change streams let applications subscribe to database changes exposed through an aggregation-based API. Compared to tailing `local.oplog.rs` directly, change streams provide structured event documents, resume tokens, and automatic driver resumption across transient errors.

```text
            Application writes
                  |
                  v
            MongoDB replica set
                  |
       Majority-committed changes
                  |
                  v
              Oplog history
                  |
            $changeStream
                  |
                  v
        Java Driver / watch()
                  |
          +-------+---------+
          |                 |
          v                 v
    Business handler    Durable checkpoint
    / idempotent sink    / resume token
          |                 |
          +-------+---------+
                  |
                  v
      External/read-model consumers
```

A change stream is an **event feed over database changes**, not a message queue retaining every event indefinitely. Resumability depends on remaining oplog history, consistent pipeline/options, and intact namespaces.

### 2.1. Deployment Prerequisites

Per MongoDB documentation, change streams require:

- **A replica set or sharded cluster**—standalone `mongod` is not supported.
- Compatible storage engine and topology; typical deployments use WiredTiger.
- Appropriate database privileges to open change streams and read target data.
- A Java MongoDB Driver compatible with the server version.
- Connections routed via `mongos` for sharded clusters, or a proper replica set URI.
- Sufficient oplog history so a stopped/restarting consumer still finds its resume point.

On a development workstation running only standalone MongoDB, you can run a **single-node replica set** for testing per official docs. Never run `rs.initiate()` on shared deployments used by others.

### 2.2. Scopes of `watch()`

The Java Sync Driver exposes:

```java
// Single collection:
MongoCollection<Document> orders =
        database.getCollection("orders");
orders.watch();

// All eligible collections in a database:
database.watch();

// Permitted namespaces across a deployment:
mongoClient.watch();
```

| API | Scope | Notes |
| --- | --- | --- |
| `MongoCollection.watch()` | Single collection | Tightly scopes business domain and avoids irrelevant events |
| `MongoDatabase.watch()` | Multiple collections in one database | Can fan out heavily; must handle namespace and type variations |
| `MongoClient.watch()` | Entire deployment | Requires broad privileges and carries higher event volume and cost |
| Adding an aggregation pipeline | Filters or reshapes events | Must never strip or alter the resume token `_id` |

For a worker watching only orders, start with `collection.watch()` rather than `client.watch()` just to skip writing a filter.

### 2.3. Why Change Streams Do Not Completely Replace Message Brokers

| Criterion | MongoDB Change Stream | Dedicated Broker / Queue |
| --- | --- | --- |
| Event source | Database state changes | Explicitly published producer messages |
| Retention | Finite oplog history window | Configurable broker retention/partitions |
| Cursor/offset | Resume token | Broker offset, ack, or cursor |
| Long-term replay | Bounded by oplog; needs separate recovery | Governed by topic retention and queue policies |
| Business intent | Must be inferred from DB mutations | Can carry explicit domain event contracts |
| Multi-consumer fan-out | Each stream adds server cost | Built around broker consumer groups |
| Exactly-once external side effects | Not automatically guaranteed | Still requires transactions or idempotency |
| Infrastructure footprint | Built into MongoDB | Extra component offering specialized queueing |

Change streams excel at **projection synchronization, cache invalidation, audit pipelines, CDC, and outbox relays**, yet should never be treated as permanent durable queues for unlosable tasks without a recovery plan.

## 3. Java Driver: Essential APIs

### 3.1. Dependency

For the Java Sync Driver, main dependency:

```xml
<!-- pom.xml: replace VERIFIED_VERSION with a compatible release -->
<dependency>
  <groupId>org.mongodb</groupId>
  <artifactId>mongodb-driver-sync</artifactId>
  <version>VERIFIED_VERSION</version>
</dependency>
```

Or in Gradle:

```kotlin
dependencies {
    implementation("org.mongodb:mongodb-driver-sync:VERIFIED_VERSION")
}
```

Do not copy a random version blindly into production. Verify compatibility across your Java runtime, Spring Boot/BOM, MongoDB Server/FCV, and the Java Driver compatibility matrix.

Examples in this lesson use **Java 17** and standard APIs from the MongoDB Java Sync Driver 5.x line; for other versions, verify against the corresponding Javadocs.

### 3.2. Sample Imports

```java
import com.mongodb.MongoException;
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;

import org.bson.BsonDocument;
import org.bson.Document;

import java.util.List;
import java.util.concurrent.TimeUnit;
```

MongoDB offers Sync, Reactive Streams, and higher-level wrappers like Spring Data MongoDB. `MongoChangeStreamCursor` belongs strictly to the **Sync Driver**, not the Reactive `Publisher` API—never mix the two lifecycle models.

### 3.3. Opening a Simple Stream

```java
String uri = System.getenv("MONGODB_URI");

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase database =
            client.getDatabase("mongo_change_row395_lab");

    MongoCollection<Document> source =
            database.getCollection("events");

    try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                 cursor = source.watch()
                     .maxAwaitTime(1, TimeUnit.SECONDS)
                     .cursor()) {

        while (true) {
            ChangeStreamDocument<Document> event =
                    cursor.tryNext();

            if (event != null) {
                System.out.println(event.getOperationType());
            }
        }
    }
}
```

This merely demonstrates the API: an infinite `while (true)` loop **lacks stop conditions** and is unfit for production. A real worker requires a stop flag, checkpointing, and error handling as shown next.

## 4. `next()`, `hasNext()`, `tryNext()`, and Blocked Threads

### 4.1. Key Differences

| Method | Change Stream Behavior |
| --- | --- |
| `next()` | Waits for and returns the next event; can block indefinitely |
| `hasNext()` | Blocks until an event arrives or the stream ends; ill-suited for fast shutdown polling |
| `tryNext()` | Returns an available event, or `null` when no event is currently ready after fetching a batch |
| `cursor.close()` | Releases cursor and server-side cursor resources per API |
| `watch().maxAwaitTime(...)` | Bounds how long the server waits during a single `getMore` before returning an empty batch |

**`tryNext()` does not mean non-blocking at the socket level in all cases.** It may execute a network round-trip and wait on the server up to `maxAwaitTime`, plus network latency, server selection, and driver timeouts.

### 4.2. Why Not Run `forEach` Directly on the Main Thread?

```java
database.watch().forEach(event -> {
    // Runs indefinitely while the stream stays open.
    // The main thread will not reach shutdown logic on its own.
});
```

Inside HTTP services, execute consumers on a dedicated **worker thread** or managed lifecycle component. Never block startup threads or request threads with an infinite `forEach`.

### 4.3. Bounded Polling for Graceful Shutdown

```java
AtomicBoolean stopping = new AtomicBoolean(false);

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
         cursor = collection.watch()
                 .maxAwaitTime(1, TimeUnit.SECONDS)
                 .cursor()) {

    while (!stopping.get()) {
        ChangeStreamDocument<Document> event =
                cursor.tryNext();

        if (event == null) {
            continue;  // loop back to check stop flag
        }

        handleAndCheckpoint(event);
    }
}
```

`maxAwaitTime(1, SECONDS)` lets the loop check the stop flag periodically under normal conditions. However, it **does not guarantee** every Java call returns in 1 second during network or server faults. Configure driver timeouts and outer shutdown deadlines as well.

## 5. Reading a Change Event Correctly

### 5.1. Shape of a Change Event

A general change event looks like:

```javascript
{
  _id: { _data: "826..." },      // Resume token
  operationType: "update",
  clusterTime: Timestamp({t: 1794630000, i: 1}),
  ns: {
    db: "mongo_change_row395_lab",
    coll: "orders"
  },
  documentKey: { _id: ObjectId("...") },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Exact fields depend on server version and operation type:

- `_id` at the **change event** level is the resume token—**not the mutated document's `_id`**.
- `documentKey` identifies the affected document; on sharded collections it also contains shard key fields.
- `operationType` specifies the mutation kind.
- `clusterTime` reflects the logical oplog timestamp; never use it in place of the resume token.
- `fullDocument` may or may not be present depending on operation type and driver options.
- `updateDescription` records update deltas.
- `lsid`/`txnNumber` can aid transaction diagnostics, though they are not simple unique event IDs.

### 5.2. Reading an Event in Java

```java
ChangeStreamDocument<Document> change = cursor.tryNext();

if (change != null) {
    BsonDocument resumeToken = change.getResumeToken();
    BsonDocument documentKey = change.getDocumentKey();

    System.out.println("op=" + change.getOperationType());
    System.out.println("ns=" + change.getNamespace());

    // Do not write full tokens or sensitive fullDocument payloads
    // to production logs.
}
```

### 5.3. Insert, Replace, Update, and Delete

| Operation | Typical Payload | Important Caveats |
| --- | --- | --- |
| `insert` | `fullDocument` contains the inserted document | Usable for projections; still design for idempotency |
| `replace` | Replacement `fullDocument` | Can overwrite multiple fields at once |
| `update` | `updateDescription` delta; `fullDocument` optional | `updateLookup` is not an immutable snapshot at event time |
| `delete` | `documentKey`; no document left to look up | Do not expect `fullDocument` |
| `invalidate` | Invalidate event token | Terminates cursor; follows different resume rules |

Additional events like `drop`, `rename`, and expanded events can appear depending on version and scope. Consumers must never blindly assume every event includes `fullDocument`.

### 5.4. `FullDocument.UPDATE_LOOKUP`

```java
ChangeStreamIterable<Document> stream =
        collection.watch()
            .fullDocument(FullDocument.UPDATE_LOOKUP);
```

For updates, the driver tells the server to look up the **current document** when emitting the event. If subsequent updates or a delete occurred before lookup executes, `fullDocument` can differ from the state **at the exact moment of the update**, or be missing entirely.

Example:

```text
T1: update status -> PAID
T2: update status -> CANCELLED
T3: change stream processes T1 event with updateLookup
    -> fullDocument may already show CANCELLED
```

If business logic demands exact per-event state transitions, inspect `updateDescription` or emit an outbox/domain event carrying explicit versions inside a transaction.

### 5.5. Pre-Images and Post-Images

MongoDB 6.0+ supports pre- and post-images when configured on the collection and still within retention.

Java API usage:

```java
collection.watch()
    .fullDocumentBeforeChange(
        FullDocumentBeforeChange.WHEN_AVAILABLE
    );
```

Never enable `REQUIRED` assuming historical events are guaranteed to retain pre-images. Pre/post-images obey collection settings and retention windows; missing images fail lookups.

Availability depends on server version; on write-heavy collections, storing pre/post-images increases storage cost and demands security review.

## 6. Resume Token: The True Checkpoint Unit

### 6.1. Resume Tokens Are Neither Document IDs Nor Simple Timestamps

MongoDB populates `event._id` as a BSON document:

```javascript
{
  "_data": "826..."
}
```

Token encodings vary across server versions; **treat it strictly as an opaque BSON document**.

Never:

- split `_data` strings to infer ordering;
- convert tokens into timestamps;
- fabricate tokens from `documentKey._id`;
- mutate internal fields inside a token;
- replace event `_id` using `$project` or `$replaceRoot` in pipelines;
- compare tokens lexicographically to determine newer events.

Java:

```java
BsonDocument token = change.getResumeToken();
```

This token marks the **event position** so restarts can request events **strictly after** that event.

### 6.2. Why Preserve Raw BSON Intact?

Example checkpoint document in MongoDB:

```javascript
{
  _id: "orders-consumer-v1",
  token: {
    _data: "826..."
  },
  pipelineVersion: "orders-v1",
  updatedAt: ISODate("2026-11-14T04:25:00Z")
}
```

Prefer storing tokens natively as BSON in a MongoDB checkpoint collection. If serialized to JSON, files, or external stores, use **Extended JSON** and verify round-trip fidelity rather than converting to lossy strings.

Resume tokens contain protocol/deployment metadata and should not be dumped into public logs.

### 6.3. `postBatchResumeToken` and High-Water Marks

Alongside individual event tokens, MongoDB returns a `postBatchResumeToken` on `aggregate` and `getMore` replies. This serves as a **high-water mark token**, advancing stream position in time even across empty batches.

The Java Sync Driver exposes:

```java
BsonDocument lastKnownToken = cursor.getResumeToken();
```

Per Javadocs, `getResumeToken()` returns:

- the resume token of the most recently delivered event;
- or `postBatchResumeToken` once the client finishes iterating the current batch;
- or `null` before any token arrives or once closed.

**Critical warning:** the cursor's token marks **what MongoDB has delivered**, not necessarily **what side effects completed**. If events sit in an async internal queue not yet drained, never checkpoint `cursor.getResumeToken()` prematurely.

### 6.4. Checkpointing on Empty Batches

A synchronous single-event consumer with zero pending work can advance progress cleanly on idle streams using `getResumeToken()` after an empty batch—provided ALL of the following hold:

1. Zero delivered events remain unprocessed.
2. Zero side effects are in flight or queued.
3. Zero retries or replays are pending.
4. The token matches the active pipeline and options.
5. This consumer holds exclusive permission to write the checkpoint.

In this lesson's core example, we persist **`event.getResumeToken()` after successful processing** for clarity and safety. On long idle streams, checkpoints simply stay unchanged while waiting—this is normal, not data loss.

## 7. Three Ways to Start or Resume a Change Stream

### 7.1. `resumeAfter(token)`

Used when resuming from a prior event token to receive events **after that event**:

```java
ChangeStreamIterable<Document> stream =
        collection.watch();

if (savedToken != null) {
    stream.resumeAfter(savedToken);
}
```

Requirements:

- Sufficient oplog history covering the token position.
- Compatible pipeline and options matching token creation.
- Valid namespace and topology.
- Never pass an **`invalidate` event token** to `resumeAfter`.

When checkpoints save after side effects, restarting with `resumeAfter` avoids replaying already-checkpointed events while re-delivering any **uncheckpointed** ones.

### 7.2. `startAfter(token)`

Starts a new stream **after a given token**; critically unlike `resumeAfter`, it can open a fresh stream **after an `invalidate` event**:

```java
ChangeStreamIterable<Document> stream =
        collection.watch()
            .startAfter(invalidateToken);
```

For instance, if a collection was dropped and recreated and the app wants to resume tracking that namespace. Still, **never use `startAfter` blindly to hide data loss**:

- The recreated collection may differ in schema or ownership.
- Oplog retention limits still apply.
- Business rules around drops/renames may mandate re-bootstrapping.
- Require an explicit policy deciding whether to resume, migrate, or halt.

### 7.3. `startAtOperationTime(timestamp)`

Opens a stream starting from a MongoDB **BSON timestamp**:

```java
BsonTimestamp operationTime = new BsonTimestamp(
    secondsSinceEpoch,
    increment
);

ChangeStreamIterable<Document> stream =
        collection.watch()
            .startAtOperationTime(operationTime);
```

This is **not** a plain `java.util.Date` or epoch millisecond value. Pass a valid server operation timestamp still retained in oplog history.

`startAtOperationTime` helps bootstrap/backfill workflows prior to obtaining event tokens, but never synthesize timestamps from client clocks and assume gap-free coverage.

### 7.4. Mutually Exclusive Starting Options

| Option | Use Case | Caveat |
| --- | --- | --- |
| Omit start point | Follow new changes from stream creation onward | Does not backfill past data |
| `resumeAfter` | Continue after a normal event token | Invalid after `invalidate` events |
| `startAfter` | Start after a token, including `invalidate` | Must verify namespace lifecycle |
| `startAtOperationTime` | Start at a MongoDB cluster operation time | Timestamp must sit in oplog; cannot combine with tokens |

Never specify `resumeAfter`, `startAfter`, and `startAtOperationTime` together.

## 8. Correctness: Why Checkpoint Ordering Determines Data Loss

### 8.1. Wrong: Checkpointing Before Business Side Effects

```text
Receive event E42
       |
Persist token T42  <-- prematurely marks completed
       |
Call external API
       |
CRASH before external API succeeds
       |
Restart with resumeAfter(T42)
       |
E42 is never replayed
```

This causes **at-most-once / lost work**. If the side effect fails after persisting the token, the system silently drops the event.

### 8.2. Better: Side Effects Before Checkpointing

```text
Receive event E42
       |
Apply side effect successfully
       |
Persist token T42
       |
Continue reading
```

If a crash occurs after applying the side effect and before saving the checkpoint, E42 replays on restart. This delivers **at-least-once** semantics (preventing silent drops across the crash window while permitting duplicates).

Pair this with **idempotent processing** so replays remain safe.

### 8.3. Crash Window Matrix

| Crash Timing | Sink Applied? | Token Persisted? | On Restart |
| --- | --- | --- | --- |
| Before processing E42 | No | No | E42 replays cleanly |
| Mid-flight during sink call | Unknown | No | Must verify/retry idempotently |
| After sink succeeds, before checkpoint | Yes | No | E42 replays (sink dedupes) |
| After checkpoint succeeds | Yes | Yes | Resumes cleanly after E42 |
| Checkpoint saved before sink | No | Yes | **E42 can be permanently lost** |

An external HTTP `ACK` can drop after the side effect already executed; never infer "nothing happened" from a network timeout exception alone.

### 8.4. Never Promise Unconditional Exactly-Once

**Change streams + resume tokens do not yield exactly-once external side effects across MongoDB and separate systems.**

Events can replay across restarts and retries. To keep business state duplicate-free:

- Pass event idempotency keys to downstream sinks.
- Perform deterministic-key upserts.
- Enforce unique constraints on deduplication ledgers.
- Commit side effects and checkpoints **in the same MongoDB transaction** when both reside in one supported deployment.
- Use transactional outbox/inbox patterns when publishing to queues.
- Use provider idempotency keys or business reconciliation for external payments/emails.

Only claim "exactly-once" when end-to-end architecture explicitly closes every failure window.

## 9. Idempotent Processing Using Event Tokens

### 9.1. Using a Stable Event Identity

`event.getResumeToken()` uniquely identifies each change event. When sinks cannot store BSON natively as keys, compute a **deterministic hash** from a fixed token serialization paired with the consumer name.

Java 17 example:

```java
import org.bson.BsonDocument;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

static String eventKey(String consumerName, BsonDocument token) {
    try {
        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(
                (consumerName + ":" + token.toJson())
                    .getBytes(StandardCharsets.UTF_8)
            );

        return HexFormat.of().formatHex(digest);
    } catch (NoSuchAlgorithmException e) {
        throw new IllegalStateException("SHA-256 unavailable", e);
    }
}
```

This builds a deduplication key—**not a token decoder**. In production, keep serialization stable across driver upgrades and verify round-trips, or store canonical BSON bytes; never derive timestamps or ordering from the hash.

### 9.2. Inbox / Processed Events Collection

A deduplication ledger document:

```javascript
{
  _id: "sha256-of-consumer-and-resume-token",
  consumer: "order-projection-v1",
  source: "commerce.orders",
  op: "update",
  processedAt: ISODate("2026-11-14T04:15:00Z")
}
```

MongoDB enforces uniqueness on `_id`. Re-inserting the same ID detects duplicates cleanly; use an upsert with `$setOnInsert` for idempotency:

```java
String id = eventKey(consumerName, event.getResumeToken());

processedEvents.updateOne(
    Filters.eq("_id", id),
    Updates.combine(
        Updates.setOnInsert("consumer", consumerName),
        Updates.setOnInsert(
            "processedAt",
            new java.util.Date()
        )
    ),
    new UpdateOptions().upsert(true)
);
```

**Important:** inserting an event ID into a MongoDB ledger does not automatically make **separate HTTP side effects** idempotent. Email and payment sinks must also accept or reconcile idempotency keys, or coordinate via transactions/outbox.

### 9.3. Updating Projections Using Deterministic Keys

Example order read-model sync:

```java
Document fullDocument = event.getFullDocument();

if (fullDocument != null) {
    Object businessId = fullDocument.get("_id");

    orderReadModel.replaceOne(
        Filters.eq("_id", businessId),
        fullDocument,
        new ReplaceOptions().upsert(true)
    );
}
```

This demonstrates **idempotent replacement** by `_id` under a **sequential single consumer**. With concurrent consumers or `updateLookup` returning newer state out of order, add monotonic `version` guards, compare-and-set filters, or targeted updates—and never use `replaceOne` if the target holds independent columns/fields.

### 9.4. Avoid Infinite Feedback Loops When Watching and Writing

If you watch an entire database or deployment and write checkpoints or projections **into that same scope**, consumer writes trigger new change events in an endless loop.

Prevent feedback loops by:

- Watching only the narrow source collection.
- Filtering namespaces and operation types strictly when watching broader scopes.
- Keeping checkpoint and projection collections out of watched scopes.
- Preserving event `_id`.
- Monitoring for self-triggering write amplification.

## 10. Storing MongoDB Checkpoints as Intact BSON

### 10.1. Separate Collection per Consumer Scope

Example layout:

```text
Database: mongo_change_row395_lab

events_row395_lab          -> source events
processed_events_row395   -> demo idempotent sink
change_stream_checkpoints -> durable resume state
```

Checkpoint keys should distinguish:

- Deployment/cluster identity.
- Source namespace and watch scope.
- Consumer group/worker name.
- Pipeline + options version.
- Side-effect handler/schema version.

Example:

```javascript
{
  _id: "lab:events_row395:report-worker:pipeline-v1",
  resumeToken: { _data: "826..." },
  pipelineVersion: "v1",
  updatedAt: ISODate("2026-11-14T04:30:00Z")
}
```

Never share one checkpoint `_id` across consumers with incompatible logic or pipelines.

### 10.2. Reading Checkpoints in Java

Typed `BsonDocument` collection keeps the token intact:

```java
MongoCollection<BsonDocument> checkpoints =
    database.getCollection(
        "change_stream_checkpoints",
        BsonDocument.class
    );

String streamKey = "lab:events:workerA:pipeline-v1";

BsonDocument record = checkpoints
    .find(Filters.eq("_id", streamKey))
    .first();

BsonDocument token = record == null
    ? null
    : record.getDocument("resumeToken");
```

If persisting checkpoints in JSON/Redis/files, test round-trip deserialization back into an exact **`BsonDocument`**, rather than raw `_data` strings or client-synthesized fields.

### 10.3. Writing Checkpoints in Java

```java
import com.mongodb.client.model.ReplaceOptions;
import org.bson.BsonDateTime;
import org.bson.BsonString;

static void saveCheckpoint(
        MongoCollection<BsonDocument> checkpoints,
        String streamKey,
        BsonDocument token) {

    BsonDocument checkpoint = new BsonDocument()
        .append("_id", new BsonString(streamKey))
        .append("resumeToken", token)
        .append(
            "updatedAt",
            new BsonDateTime(System.currentTimeMillis())
        );

    checkpoints.replaceOne(
        Filters.eq("_id", streamKey),
        checkpoint,
        new ReplaceOptions().upsert(true)
    );
}
```

In production, protect checkpoint durability with suitable write concerns (such as `majority` when strong durability is needed), least-privilege write roles, auditing, and fencing if multiple pods compete.

### 10.4. Checkpoints Are Not Business Sequence Numbers

Do not replace tokens with `clusterTime` or `documentKey`. Multiple events in transactions or across shards share timestamps; the full resume token carries exact cursor positioning.

`checkpoint.updatedAt` records **when the worker wrote progress**, not event origin time. Use it for relative freshness checks, never global ordering.

## 11. Java Sync Driver Example: Consumer Loop with Checkpointing and Shutdown

This is a **complete instructional reference implementation**. It:

- connects to a **lab** replica set;
- watches one source collection;
- resumes via `resumeAfter` from checkpoint;
- processes sequentially into an **idempotent inbox**;
- persists the token **after** sink writes succeed;
- polls stop state cleanly via `tryNext()`;
- closes the cursor via `try-with-resources`;
- catches `SIGTERM` via a shutdown hook and waits boundedly for completion;
- never auto-deletes or drops test data.

### 11.1. Environment Configuration

```text
MONGODB_URI=mongodb://localhost:27017/?replicaSet=rs0
ROW395_SOURCE=events_row395_lab
ROW395_CONSUMER=demo-consumer-v1
```

Use an isolated lab replica set URI (the string above is illustrative). **Never commit passwords or real URIs into source code or public READMEs.**

Keep `ROW395_SOURCE` stable across restarts so the consumer resumes the same stream; generating random collection names on every boot orphans old checkpoints.

### 11.2. Java Class

```java
import com.mongodb.MongoException;
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;

import org.bson.BsonDateTime;
import org.bson.BsonDocument;
import org.bson.BsonString;
import org.bson.Document;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Date;
import java.util.HexFormat;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ChangeStreamWorker395 {
    private final MongoCollection<Document> source;
    private final MongoCollection<Document> processedEvents;
    private final MongoCollection<BsonDocument> checkpoints;

    private final String streamKey;
    private final AtomicBoolean stopping = new AtomicBoolean(false);
    private final CountDownLatch finished = new CountDownLatch(1);

    public ChangeStreamWorker395(
            MongoDatabase db,
            String sourceName,
            String consumerName) {

        this.source = db.getCollection(sourceName);
        this.processedEvents =
                db.getCollection("row395_processed_events");
        this.checkpoints = db.getCollection(
                "row395_change_checkpoints",
                BsonDocument.class
        );

        this.streamKey = db.getName()
                + ":" + sourceName
                + ":" + consumerName
                + ":pipeline-v1";
    }

    public void requestStop() {
        stopping.set(true);
    }

    public boolean awaitStop(long seconds)
            throws InterruptedException {
        return finished.await(seconds, TimeUnit.SECONDS);
    }

    private BsonDocument loadToken() {
        BsonDocument row = checkpoints
                .find(Filters.eq("_id", streamKey))
                .first();

        return row == null
                ? null
                : row.getDocument("resumeToken");
    }

    private void storeToken(BsonDocument token) {
        BsonDocument row = new BsonDocument()
                .append("_id", new BsonString(streamKey))
                .append("resumeToken", token)
                .append("updatedAt",
                        new BsonDateTime(System.currentTimeMillis()));

        checkpoints.replaceOne(
                Filters.eq("_id", streamKey),
                row,
                new ReplaceOptions().upsert(true)
        );
    }

    private static String sha256(String data) {
        try {
            byte[] hash = MessageDigest.getInstance("SHA-256")
                    .digest(data.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
    }

    private void applyIdempotently(
            ChangeStreamDocument<Document> event) {

        BsonDocument token = event.getResumeToken();
        String eventId = sha256(streamKey + ":" + token.toJson());

        // Demo: write to idempotent inbox; DO NOT invoke HTTP side effects.
        processedEvents.updateOne(
                Filters.eq("_id", eventId),
                Updates.combine(
                        Updates.setOnInsert(
                                "streamKey", streamKey
                        ),
                        Updates.setOnInsert(
                                "operation",
                                String.valueOf(event.getOperationType())
                        ),
                        Updates.setOnInsert(
                                "processedAt", new Date()
                        )
                ),
                new UpdateOptions().upsert(true)
        );
    }

    public void consume() {
        try {
            while (!stopping.get()) {
                BsonDocument persisted = loadToken();

                ChangeStreamIterable<Document> iterable = source.watch()
                        .maxAwaitTime(1, TimeUnit.SECONDS);

                if (persisted != null) {
                    iterable = iterable.resumeAfter(persisted);
                }

                try (MongoChangeStreamCursor<
                        ChangeStreamDocument<Document>> cursor =
                             iterable.cursor()) {

                    System.out.println("Change stream active: " + streamKey);

                    while (!stopping.get()) {
                        ChangeStreamDocument<Document> event =
                                cursor.tryNext();

                        if (event == null) {
                            continue;
                        }

                        if (event.getOperationType()
                                == OperationType.INVALIDATE) {
                            // Drop/rename: do not resume normally.
                            throw new IllegalStateException(
                                    "Source invalidated; manual re-bootstrap required"
                            );
                        }

                        // 1) Complete idempotent side effect.
                        applyIdempotently(event);

                        // 2) Checkpoint ONLY AFTER side effect succeeds.
                        storeToken(event.getResumeToken());
                    }
                }
            }
        } finally {
            finished.countDown();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        String uri = System.getenv("MONGODB_URI");
        String sourceName = System.getenv("ROW395_SOURCE");
        String consumerName = System.getenv("ROW395_CONSUMER");

        if (uri == null || sourceName == null ||
                consumerName == null) {
            throw new IllegalArgumentException(
                    "Need MONGODB_URI, ROW395_SOURCE, ROW395_CONSUMER"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase(
                    "mongo_change_row395_lab"
            );

            ChangeStreamWorker395 worker = new ChangeStreamWorker395(
                    db, sourceName, consumerName
            );

            Runtime.getRuntime().addShutdownHook(
                    new Thread(() -> {
                        worker.requestStop();

                        try {
                            if (!worker.awaitStop(20)) {
                                System.err.println(
                                        "Shutdown deadline reached; " +
                                        "uncheckpointed events may replay."
                                );
                            }
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                        }
                    }, "row395-shutdown")
            );

            // This loop runs on the main thread. SIGTERM triggers the
            // shutdown hook on another thread, setting stopping=true.
            worker.consume();
        }
    }
}
```

### 11.3. Behavior and Limitations of This Sample

- The worker processes events **sequentially** with zero internal queue, so saving the checkpoint immediately after the sink succeeds is sound.
- `processedEvents` acts as an inbox via `$setOnInsert` and unique `_id`; replaying the same token writes no duplicate entries.
- Sink and checkpoint writes are **two separate MongoDB writes**. Crashing between them replays the event, and the inbox absorbs the duplicate cleanly.
- No external system is called here. Integrating emails, payments, or Kafka requires adding idempotency, outbox, or broker ack semantics.
- The code **does not catch all `MongoException`s to loop indefinitely**. On fatal stream errors, the process exits so a supervisor handles backoff and alerting—a deliberate **fail-closed** choice here. Classified retry policies are discussed later.
- Cursor `getResumeToken()` is deliberately avoided for checkpointing because it can advance to a high-water mark ahead of acknowledged sink work.
- The demo has no distributed leader election or lease; **run only one active instance per `streamKey`**. Multiple pods sharing a `streamKey` will race on checkpoints.
- During shutdown, `tryNext()` can exceed 1 second under network trouble. Never promise shutdown always completes in 20 seconds; coordinate socket timeouts and orchestrator grace windows.
- If a crash hits during inbox/checkpoint writes under weak write concerns, consider replica set rollbacks. In production, configure `WriteConcern.MAJORITY` on critical collections.

### 11.4. Enforcing Write Concern When Needed

```java
MongoCollection<Document> durableSink =
        db.getCollection("row395_processed_events")
          .withWriteConcern(WriteConcern.MAJORITY);

MongoCollection<BsonDocument> durableCheckpoints =
        db.getCollection(
            "row395_change_checkpoints",
            BsonDocument.class
        ).withWriteConcern(WriteConcern.MAJORITY);
```

Remember to import `com.mongodb.WriteConcern`. Match durability to business SLAs and replica set latency; `majority` adds latency when secondaries lag. **A write concern timeout does not mean the write never occurred**—reconcile state before replaying side effects.

## 12. Graceful Shutdown: From `SIGTERM` to Client Close

### 12.1. Desired Sequence

```text
Kubernetes / systemd / application stop
                  |
                 SIGTERM
                  |
                  v
             Stop flag = true
                  |
       Stop receiving new work
                  |
                  v
         Wait for current event
           side effect to finish
                  |
                  v
       Persist processed event token
                  |
                  v
           Close change cursor
                  |
                  v
        Close MongoClient/resources
                  |
                  v
             Process exit
```

If the shutdown deadline hits before the side effect finishes, **never save the checkpoint prematurely just to force exit**. Let the next run replay the event via idempotency.

### 12.2. Why Not Close `MongoClient` Immediately on `SIGTERM`?

If the shutdown hook calls:

```java
client.close();
```

while the worker is actively:

- polling the change stream;
- writing projections/inbox state;
- persisting the checkpoint;

the worker gets hit by closed connections mid-operation. Side effects may already have committed server-side without client confirmation, creating ambiguous outcomes.

Always follow: **signal stop → await in-flight drain/ack → close cursor → close client**.

### 12.3. Bounded Shutdown Deadlines

A shutdown hook waiting forever stalls pod replacement. Too tight a deadline forces unnecessary event replays.

Align these timers cleanly:

- Server `maxAwaitTime` / `getMore` limits.
- Driver socket and server selection timeouts.
- Per-event processing deadline.
- External sink timeout and reliability characteristics.
- Kubernetes `terminationGracePeriodSeconds`.
- Spring Boot graceful shutdown grace period.
- Time to flush final metrics and logs after consumer stops.

The **20 seconds** shown above is purely illustrative; no universal constant fits every workload.

### 12.4. `tryNext()` Does Not Guarantee Instant Termination

Even with `maxAwaitTime(1, SECONDS)`, network stalls or server selection delays can extend the call.

Do not fix this by calling `close()` arbitrarily from another thread while mixing unsynchronized calls on `MongoChangeStreamCursor`: Javadocs warn cursors are **not thread-safe**. Keep cursor ownership with the worker loop and close cleanly via `finally` / `try-with-resources`.

If a hard force-kill occurs after the grace deadline, operations must accept that **uncheckpointed events can replay**. Forcefully closing sockets never guarantees "side effects didn't run".

### 12.5. Graceful Shutdown vs. Hard Crashes

| Scenario | Hook / `finally` Runs? | Expectation |
| --- | --- | --- |
| Caught `SIGTERM` | Usually runs | Stop, drain, checkpoint, close |
| Normal Spring context close | Lifecycle callbacks run | Clean ordered consumer stop |
| `SIGKILL` / OOMKill | **Not guaranteed** | Uncheckpointed events replay |
| Power loss / node crash | No | Restart from durable checkpoint |
| Network partition | Process stays alive; calls fail | Retry with backoff or fail closed |
| DB election | Driver auto-resumes eligible errors | Possible event redelivery; checkpoint intact |
| Uncaught code bug | `finally` can execute | Never checkpoint the failed event |

Graceful shutdown shrinks duplicate replay windows, **yet never removes the need for idempotency**.

## 13. Integrating with Spring Boot and Container Lifecycles

### 13.1. Never Start Consumers Inside an HTTP Request Handler

Avoid:

```java
@GetMapping("/listen")
public void listen() {
    collection.watch().forEach(...);
}
```

It pins request threads, breaks lifecycle ownership, and risks opening thousands of streams whenever clients hit the endpoint.

Instead, build a dedicated component:

- `@Service` with a managed executor;
- `SmartLifecycle` for explicit start/stop ordering;
- or an independent worker deployment separated from web pods.

### 13.2. Conceptual Lifecycle Skeleton

```java
@Component
public class ChangeStreamLifecycle implements SmartLifecycle {
    private final ExecutorService executor =
            Executors.newSingleThreadExecutor();

    private final AtomicBoolean running =
            new AtomicBoolean(false);

    private Future<?> future;

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            future = executor.submit(() -> consumeLoop(running));
        }
    }

    @Override
    public void stop() {
        running.set(false);
        executor.shutdown();

        try {
            if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
                // Do not checkpoint unprocessed events.
                // Report deadline; supervisor/replay handles it.
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
```

This is a **skeleton** omitting imports, `consumeLoop`, and DI wiring. In real code:

1. Close the cursor cleanly inside the worker.
2. Prevent spawning duplicate threads on repeated `start()` calls.
3. Ensure Spring stop phases stop the consumer before destroying the `MongoClient` bean.
4. Monitor `Future` and worker health; `running=true` means nothing if the worker thread died silently.
5. Never expect `executor.shutdownNow()` to abort blocking I/O instantaneously; rely on safe replay.
6. Size Spring Boot and Kubernetes grace periods coherently.

### 13.3. Readiness and Liveness

A broken watcher that lost its token (`ChangeStreamHistoryLost`) should not keep reporting green across every health probe.

Separate:

- **Liveness:** the JVM is alive and recoverable.
- **Readiness:** the service handles work within SLOs.
- **Consumer health:** last checkpoint age, event lag, connected stream status, handler error rates, and lease ownership.

Avoid tying unrelated HTTP API readiness directly to a secondary background consumer unless business requirements mandate halting API traffic too.

## 14. Reactive Streams Driver vs. Java Sync Driver

### 14.1. Same Server Semantics, Different Lifecycle

With the MongoDB Java Reactive Streams Driver, consumers subscribe to a **`Publisher`/`Subscriber`** (often wrapped via Project Reactor) instead of managing `MongoChangeStreamCursor`.

Key differences:

- `Subscription.cancel()` halts downstream demand.
- Backpressure controls how many events are requested.
- Never fire-and-forget a subscription without storing lifecycle cancellation handles.
- Never save checkpoints inside `doOnNext` before async downstream operations finish.
- Use `concatMap` or ordered commit tracking when checkpoint sequence matters.
- Dispose subscriptions cleanly on Reactor context shutdown and await completion of in-flight side effects.

### 14.2. Parallel Processing Traps

Consider out-of-order execution:

```text
Event E10 -> slow processing
Event E11 -> fast processing
Event E12 -> fast processing
```

If E12 checkpoints before E10 finishes, a crash skips E10 permanently upon restarting after E12.

Parallel processing requires:

- an **ordered commit frontier**, advancing checkpoints only up to the highest token whose **preceding events all succeeded**;
- or key-based partitioning with independent per-partition checkpoints;
- never updating one shared global token from out-of-order workers without coordination.

Throughout this material, sequential Java Sync loops provide the clearest correctness baseline.

## 15. Errors: Transient, Resumable, and Fatal Differ Fundamentally

### 15.1. Automatic Driver Resumption on Eligible Errors

Following MongoDB change stream specifications, the Java Driver automatically attempts **one-step resumption** for qualifying **resumable errors** using cached tokens or operation times—helpful during brief elections and network glitches.

However:

- Not all failures are resumable.
- Driver retries do not run endlessly.
- Your application may still fail mid-processing before checkpointing.
- On full process restarts, you must load **your durable checkpoint**, not rely on driver in-memory state.

### 15.2. Error Classification Table

| Category | Examples | Handling Strategy |
| --- | --- | --- |
| Transient network / election | Timeouts, `NotPrimary`, interrupted replica state | Driver auto-resumes when eligible; app applies bounded backoff/reopen |
| Transient sink outage | HTTP 503, broker unavailable | Do not checkpoint; retry with idempotency and backoff |
| Permanent / poison message | Invalid payload, business invariant failure | Route to DLQ/quarantine for repair; never drop silently |
| Auth / KMS / RBAC | Missing watch/read permissions | Fail closed, alert, fix credentials or policies |
| `ChangeStreamHistoryLost` | Saved token older than oplog history | **Never** "resume from now"; re-bootstrap and reconcile |
| `invalidate` | Collection dropped or renamed | Evaluate lifecycle; optionally `startAfter` per policy |
| Pipeline / option mismatch | Old token incompatible with new options | Version checkpoints and plan migration |
| Resource saturation | Excessive cursors, pools, CPU, or disk | Reduce watcher fan-out, right-size, and alert |

### 15.3. Never Hammer Retries Unboundedly

Polling every 10 ms cannot fix missing permissions or expired resume tokens.

Enforce:

- retry budgets;
- exponential backoff with jitter;
- clear resumable vs. non-resumable classification;
- owner alerting;
- sink circuit breakers;
- reopen/resume attempt metrics;
- oplog window and lag monitoring.

### 15.4. `ChangeStreamHistoryLost`: When the Token Falls Out of the Oplog

Suppose:

```text
Oplog history window: ~12 hours
Consumer stopped:      36 hours
Latest checkpoint:     older than available history
Restart:               resumeAfter fails
```

Some server versions emit code `286` (`ChangeStreamHistoryLost`); inspect error labels and server-version behavior rather than relying exclusively on hardcoded strings.

Never do this:

```java
// Anti-pattern: if history is lost, discard token and watch from now.
if (resumeFailed) {
    collection.watch().forEach(this::process);
}
```

Doing so silently **loses 24 hours of mutations** without raising alarms. Instead, require:

- a source-of-truth reconciliation mechanism;
- snapshot + backfill procedures;
- longer-retention upstream event logs if available;
- or an explicit, audited business decision accepting and logging the gap.

## 16. Oplog Window and Resumability

### 16.1. The Oplog Is a Finite History Window, Not an Infinite Queue

Change streams read from the oplog. Oplog capacity and retention depend on disk sizing and write throughput. During write spikes, **actual retention time shrinks**.

Example:

```text
Normal write volume:
   oplog covers 40 hours

Sales campaign / bulk import:
   oplog covers only 6 hours

Worker paused 10 hours:
   restart token may be too old
```

Never calculate "30 GiB oplog means workers can stay down 2 days". Measure **live oplog retention hours and write velocity**.

### 16.2. Compare Consumer Downtime Against Oplog Window

Monitor:

- Earliest and latest oplog timestamps (live retention window).
- Last persisted checkpoint timestamp / `clusterTime`.
- Time elapsed since the last processed event.
- Event processing latency.
- Retry backlog size.
- Replication lag and primary election events.

Safe operating margins ensure **remaining oplog retention exceeds worst-case recovery time** with comfortable headroom rather than relying on static hour thresholds.

### 16.3. Reference Inspection in `mongosh`

On authorized lab or self-managed replica sets:

```javascript
rs.printReplicationInfo();
```

Output summarizes oplog window duration on the server. Managed tiers may restrict direct `local.oplog.rs` reads; use Atlas monitoring metrics instead.

Never execute `replSetResizeOplog` or alter oplog configs casually in production just from a guide—oplog changes impact replication, disk I/O, and retention and belong in DBA runbooks.

## 17. Change Stream Pipelines and Compatibility Contracts

### 17.1. Filtering Operation Types

```java
List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.in(
            "operationType",
            List.of("insert", "update", "replace", "delete")
        )
    )
);

ChangeStreamIterable<Document> stream =
        collection.watch(pipeline);
```

Benefits: drops irrelevant network traffic before reaching Java. Watch out for filtering away `invalidate` and DDL lifecycle events, which removes visibility into why streams close.

### 17.2. Never Strip or Alter Event `_id`

Do not write:

```javascript
// DO NOT do this on a change stream:
{ $project: { _id: 0, operationType: 1 } }
```

MongoDB 4.2+ rejects pipelines that strip or modify the change event `_id`, because that destroys the resume token.

To trim payloads, project non-`_id` fields while **leaving `_id` intact**, and validate stages against the official change stream pipeline matrix.

### 17.3. Keep Pipelines and Options Consistent Across Resumes

MongoDB warns that resuming with altered pipelines or options can break resumption or produce unexpected output.

Example:

```text
checkpoint generated under:
   source = orders
   filter = operationType in [insert, update]
   fullDocument = updateLookup
   collation = simple

restart under:
   source = orders
   filter = status = PAID
   fullDocument = default

=> never assume the old token stays compatible
```

Tag checkpoints with `pipelineVersion` and deployment config. When changing a pipeline:

1. Analyze how event coverage changes.
2. Stop the old consumer at a clean checkpoint.
3. Follow documented compatibility paths if applicable.
4. Otherwise deploy a versioned consumer/checkpoint key and re-bootstrap/reconcile.
5. Cut over routing after verifying lag and output accuracy.
6. Never silently reuse incompatible tokens.

### 17.4. Multiple Events Inside One Transaction

One transaction can emit multiple change events sharing the exact same `clusterTime`. Deduplicating by timestamp drops valid mutations.

Use the **full resume token** for positioning, pairing `lsid`/`txnNumber` only when analyzing transaction grouping—never assume "same `clusterTime` = duplicate event".

## 18. Gap-Free Full Snapshots and Change Stream Bootstrapping

### 18.1. Change Streams Do Not Emit Pre-Existing Documents

Opening a fresh stream:

```java
collection.watch();
```

receives changes **occurring after the stream start point**, not an initial dump of existing documents like `find()`.

Building a search index or read model from 10 million existing documents requires coherent **backfill + CDC**.

### 18.2. Classic Bootstrapping Gap Bug

```text
T0: scan all documents
T1: write projection from scan
T2: open watch()

Document updated between T0 and T2
  -> missed completely from the projection
```

That creates a **data gap** with no prior resume token to replay changes inside `[T0, T2]`.

### 18.3. Safer Bootstrapping Protocol

Depending on requirements:

1. Establish an explicit **CDC start marker** (stream token or operation time) per protocol.
2. Begin capturing/buffering changes **before or concurrently with** the snapshot scan.
3. Backfill existing records into a versioned/idempotent projection.
4. Replay buffered events over backfill output, resolving races using document versions.
5. Switch live only after projections catch up and counts/checksums reconcile.
6. Persist the resume token and continue normal streaming.
7. Ensure oplog retention comfortably spans the entire backfill duration.

Never assume "open stream first, then scan slowly" works safely without buffering capacity or sufficient oplog retention, since a slow backfill can expire the start point. For critical pipelines, prefer tested CDC connectors or snapshot-consistent tooling.

### 18.4. When History Is Lost, Re-Bootstrap

No trick can recover oplog events already overwritten and absent elsewhere. When tokens expire:

- Halt inconsistent downstream writes.
- Fire clear alerts.
- Identify the source of truth and affected time range.
- Run backfill and reconciliation.
- Establish a fresh checkpoint via a gap-free protocol.
- Record an audit entry—never jump silently to current time.

## 19. Correctness Across Multiple Pods

### 19.1. Two Instances Watching the Same Stream

```text
Pod A watches orders
Pod B watches orders
          |
Both receive E42
          |
Both write shared checkpoint
```

MongoDB Change Streams **do not provide Kafka-style consumer groups or partition rebalancing**. Two pods watching the same collection both receive every event; sharing one checkpoint creates races that can skip unprocessed work.

### 19.2. Single Active Owner per Checkpoint

Common coordination design:

- Leader election or distributed leases.
- One `streamKey` per logical consumer.
- Lease metadata tracking `ownerId` and `leaseUntil`.
- Only the active lease holder consumes and writes checkpoints.
- On leadership handoff, bump `fencingEpoch` to block stale writers.
- Make checkpoint updates conditional on matching `ownerId`/`fencingEpoch` and monotonic progression.

Example lease record:

```javascript
{
  _id: "orders-projection-v1",
  ownerId: "pod-3",
  leaseUntil: ISODate("2026-11-14T04:32:00Z"),
  fencingEpoch: NumberLong("12"),
  resumeToken: { _data: "..." }
}
```

This coordination lives in your application—**the MongoDB driver creates no automatic stream lease**.

### 19.3. Expired Leases Do Not Automatically Stop Stale Writers

Pod A can stall during a network partition or GC pause, let its lease expire, yet keep reading from an open cursor while Pod B acquires the new lease. Without fencing, both A and B write side effects.

Enforce fencing at **checkpoint and sink writes**, not merely in local JVM memory checks. If external sinks cannot verify fencing tokens, combine strong sink idempotency with careful handoff pauses.

### 19.4. Scaling Out via Partitioning

Options:

1. **Single watcher** fanning tasks onto partitioned internal queues by document key, advancing checkpoints via an ordered commit frontier.
2. **Multiple watchers with disjoint pipelines** sharded cleanly by tenant or shard key ranges, each maintaining an isolated checkpoint.
3. **Outbox + message broker** when large fan-out, per-key ordering, and long retention are required.

Never spin up 20 pods all executing identical `collection.watch()` expecting MongoDB to split events 1/20th each—that simply multiplies oplog scanning, `getMore` load, and connections twentyfold.

## 20. Transactional Checkpoints When Side Effects Live in MongoDB

### 20.1. Shrinking the Crash Window

When both the target projection and checkpoint collection reside in the same transaction-capable MongoDB deployment:

- read the change event **outside a transaction**;
- start a **short-lived transaction**;
- update the projection/inbox;
- persist the checkpoint;
- commit;
- read the next event only after commit succeeds.

```text
watch().tryNext() -> event E42
          |
          v
begin MongoDB transaction
          |
update projection / inbox
          |
save token T42
          |
commit transaction
          |
          v
next event
```

If the transaction aborts, both projection and checkpoint roll back together, allowing clean replay of E42. Still handle **unknown commit outcomes** on network drops using transaction retry semantics and idempotency.

### 20.2. Why Keep `watch()` Outside Transactions?

A change stream is a long-lived aggregation cursor; **never open an indefinitely long transaction around the watcher loop**. Scope short transactions strictly to individual projection + checkpoint updates.

### 20.3. Transactional Pseudocode

```java
// Pseudocode: retry labels and document versioning
// must be added per driver version and business semantics.
ChangeStreamDocument<Document> event = cursor.tryNext();

if (event != null) {
    try (ClientSession session = client.startSession()) {
        session.withTransaction(() -> {
            applyProjection(session, event);
            persistCheckpoint(session, event.getResumeToken());
            return null;
        });
    }
}
```

Pass `session` to **every** participating write, set appropriate read/write concerns, and handle `TransientTransactionError` and `UnknownTransactionCommitResult` per driver guidelines.

Never invoke external HTTP APIs, emails, or payments **inside the `withTransaction` callback**: retries re-run the callback and MongoDB cannot roll back external effects.

### 20.4. Transactions Do Not Solve External Consistency

Transactions ensure atomicity strictly across writes **within that transaction**. They never make:

- HTTP calls,
- Kafka publishes,
- emails,
- payment charges, or
- filesystem writes

atomic with MongoDB. Coordinate those via transactional outboxes and idempotent delivery.

## 21. Change Stream Resource Management

### 21.1. Cursors Pin Connections and Server Resources

Each open change stream holds a server-side cursor and associated resources. Scaling streams indiscriminately causes:

- Connection pool pressure.
- Oplog scanning and `getMore` CPU/IOPS overhead.
- Stream merging/coordination load on `mongos` in sharded clusters.
- Leaked cursors inflating server memory.
- Slow consumers risking `ChangeStreamHistoryLost`.

Never open a change stream per HTTP request or per browser tab.

### 21.2. `maxAwaitTime` and `batchSize`

```java
collection.watch()
    .maxAwaitTime(1, TimeUnit.SECONDS)
    .batchSize(100);
```

- `maxAwaitTime` bounds how long the server waits during an idle `getMore` before returning an empty batch.
- `batchSize` hints at maximum events per batch without guaranteeing fixed sizes.
- Larger batches trim round-trips at the cost of higher peak memory and larger replay batches on crash.
- Smaller batches improve shutdown responsiveness and metric freshness with slightly more round-trips.

Never treat `maxAwaitTime` as a **business handler timeout**; enforce independent timeouts on downstream sinks.

### 21.3. `FullDocument.UPDATE_LOOKUP` Adds Overhead

Performing live lookups adds disk/cache reads and latency, particularly on large documents under heavy writes. If deltas suffice, prefer `updateDescription`.

Pre/post-images add storage and retention costs—enable them selectively only where business rules truly require them.

### 21.4. Sharded Clusters

In sharded clusters:

- Connect change streams via `mongos`.
- Factor in cross-shard merging and coordination latency.
- Pipelines, `fullDocument` lookups, and shard topology changes affect latency.
- Events arrive across shards and transactions; never deduce global commit order solely from client wall clocks.
- Shard removals and oplog retention affect resumability in edge cases.

When strict ordering per business aggregate is needed, partition by aggregate key and carry explicit entity versions.

## 22. Observability: Metrics and Alerts for Java Consumers

### 22.1. Minimal Dashboard

```text
+------------------------------+--------------------------------+
| Consumer running / ownership | MongoDB change stream errors   |
+------------------------------+--------------------------------+
| Events received per second   | Events processed per second    |
+------------------------------+--------------------------------+
| Processing p95/p99 latency   | Checkpoint write latency      |
+------------------------------+--------------------------------+
| Checkpoint age / lag         | Oplog history window          |
+------------------------------+--------------------------------+
| Sink errors / DLQ backlog    | Reopened cursors / retries    |
+------------------------------+--------------------------------+
| Network/pool utilization     | CPU/RAM/disks of cluster       |
+------------------------------+--------------------------------+
| Source event volume          | Last successful shutdown      |
+------------------------------+--------------------------------+
```

### 22.2. Suggested Application Metric Names

```text
mongo_change_stream_open
mongo_change_stream_events_received_total
mongo_change_stream_events_processed_total
mongo_change_stream_event_processing_seconds
mongo_change_stream_checkpoint_success_total
mongo_change_stream_checkpoint_failure_total
mongo_change_stream_checkpoint_age_seconds
mongo_change_stream_resume_attempts_total
mongo_change_stream_errors_total
mongo_change_stream_history_lost_total
mongo_change_stream_sink_errors_total
mongo_change_stream_shutdown_graceful_total
mongo_change_stream_shutdown_deadline_total
mongo_change_stream_consumer_leader
```

These are suggested Micrometer/Prometheus application metric names—**not metrics exported automatically by MongoDB**.

### 22.3. Version-Specific Server Metrics

MongoDB 9.0 introduced additional `serverStatus.metrics.changeStreams` counters such as:

- currently open cursors;
- total cursors opened;
- resumable and non-resumable error counts;
- `ChangeStreamHistoryLost` counts.

Older server versions may omit these fields. Verify server version before querying, and never coerce `undefined` into `0`.

```javascript
const s = db.serverStatus();
printjson(s.metrics?.changeStreams);
```

Run with least-privilege monitoring permissions, and extract targeted fields rather than logging entire `serverStatus` documents every second.

### 22.4. Lag Is Not Simply Time Since Last Event

An idle stream receiving zero events for 5 hours can be perfectly healthy. A stale `lastEventAt` alone does not prove lag.

Distinguish clearly:

- **Stream liveness:** cursor remains active and polls successfully.
- **Checkpoint age:** time since the last event/token checkpoint.
- **Event processing lag:** `now - event.wallTime/clusterTime` (within bounded clock-skew limits).
- **Backlog:** queued events or gap behind the oplog tip.
- **Oplog retention headroom:** remaining safety buffer before tokens expire.

While idle, high-water mark advancements confirm stream liveness—never let them overwrite unacknowledged pending work.

### 22.5. Safe Logging

Recommended structured log shape:

```json
{
  "consumer": "orders-projection-v1",
  "streamScope": "commerce.orders",
  "pipelineVersion": "v1",
  "operationType": "update",
  "eventKeyPrefix": "e4f87b8c",
  "attempt": 1,
  "handlerDurationMs": 54,
  "checkpointPersisted": true
}
```

Never log full `fullDocument` objects containing PII, tokens, or payment fields, and omit raw resume tokens from unprivileged logs or public support tickets.

## 23. Runbook: Slow Consumer and Shrinking Oplog Window

### 23.1. Symptoms

```text
Source writes:        20,000 events/s
Consumer processed:     2,000 events/s
Checkpoint lag:          increasing
Oplog window:            4 hours -> 1 hour
```

Risk: the consumer falls too far behind and its saved resume token drops out of the oplog.

### 23.2. Investigation Steps

1. Identify `streamKey`, source namespace, and pipeline version.
2. Check last persisted token/checkpoint, event rate, and sink latency.
3. Inspect consumer JVM CPU, thread pools, connection pools, and network throughput.
4. Check MongoDB IOPS, replication lag, and live oplog retention window.
5. Measure filter selectivity and average payload size (including `updateLookup`).
6. If downstream sinks bottleneck, throttle/scale sinks and verify idempotency.
7. To scale consumers, design key partitioning or ordered commit frontiers first.
8. If catching up becomes impossible, trigger backfill and reconciliation procedures.
9. Never silently drop the token to "restart from current time".

### 23.3. Remediation by Root Cause

| Root Cause | Remediation |
| --- | --- |
| Slow Java handler CPU | Optimize parsing/logic; add bounded micro-batching |
| Slow HTTP sink | Switch to idempotent async/outbox, retry budgets, circuit breakers |
| Slow MongoDB writes | Fix queries/indexes, disk/replica health, or write concerns |
| Too many watcher scopes | Consolidate scopes or push `$match` filters upstream |
| Short oplog window | Review oplog sizing/disk with DBA while burning down lag |
| Concurrent out-of-order execution | Enforce ordered commit frontier or lease fencing |
| Invalidated/expired token | Fail closed; run snapshot backfill and reconciliation |

## 24. Runbook: Deployments Trigger Reprocessed Events

### 24.1. Typical Crash Window Example

```text
T0: Worker receives event A
T1: Sink writes successfully
T2: SIGTERM
T3: Worker killed by SIGKILL before persisting token A
T4: New pod starts from checkpoint before A
T5: Event A replays
```

This is normal **at-least-once** behavior. With idempotent upserts/dedup at the sink, zero duplicate business effects occur.

### 24.2. When Is Replay Actually a Bug?

- Duplicate emails or charges occur because the sink lacks idempotency.
- Checkpoints persisted **before** sink confirmation, losing events on crash.
- Old and new pods both write checkpoints without fencing.
- Health probes report ready even when the worker thread crashed.
- Shutdown hooks ignore in-flight handlers or call `client.close()` prematurely.

### 24.3. Resolution Steps

1. Trace the event key across checkpoints and sink logs.
2. Confirm whether the sink duplicated effects or cleanly absorbed redelivery.
3. Add missing idempotency or business compensation if side effects duplicated.
4. Increase graceful shutdown deadlines if normal handlers run longer.
5. Add leader leases and fencing before scaling pods.
6. Drill `SIGTERM`, primary elections, and network faults in staging.

## 25. Runbook: `invalidate` on Collection Drop or Rename

### 25.1. `invalidate` Is a Lifecycle Boundary

Collection streams receive an `invalidate` event when the collection is dropped or renamed; database streams receive `invalidate` if the database drops.

`invalidate` terminates the cursor. Never treat it as a harmless empty batch or ordinary mutation.

### 25.2. Application Decision Steps

Upon receiving `invalidate`:

- Log the namespace and event type clearly.
- Stop applying normal event logic.
- Verify whether planned maintenance/migration caused it or an unexpected incident.
- Check whether a recreated collection shares identical semantics and schema.
- Follow approved protocols if re-bootstrapping or pointing to a new source.
- If resuming via `startAfter(invalidateToken)`, retain the token, verify oplog history, and confirm scope safety.
- Never retry `resumeAfter(invalidateToken)` in a loop—MongoDB rejects it.

### 25.3. Collection Renames During Releases

Blue/green swaps or schema migrations may rename source collections. Even if the logical collection name still resolves afterward, existing streams may invalidate. Never stitch tokens blindly across old and new namespaces.

Version `streamKey` explicitly and coordinate cutover/backfill or watch at the database scope when appropriate.

## 26. Runbook: Unknown Outcome While Persisting Checkpoints

### 26.1. Scenario

A worker finishes handling E42, sends `replaceOne` to save the checkpoint, and hits a network timeout before receiving the server reply.

Possibilities:

- The server saved the checkpoint, and only the reply dropped.
- The checkpoint never persisted.
- The primary wrote it, yet write concern acknowledgment timed out.

### 26.2. Safe Handling

- Do not proceed to E43 until confirming E42's checkpoint durability per contract.
- Read back the checkpoint using an appropriately consistent read concern/preference.
- If it already matches E42 and side effects succeeded, continue safely.
- If it still holds an older token, retry persisting **that exact E42 token and `streamKey`** while holding the lease.
- If state remains ambiguous, fail closed so restart replays E42 idempotently.
- Never mask a failed E42 checkpoint write by saving E43 later.

In multi-pod deployments, guard checkpoint writes with `ownerId`/`fencingEpoch` checks so a stalled pod can never overwrite a newer pod's progress.

## 27. Controlled Lab: Creating a Collection, Running the Java Watcher, Restarting

### 27.1. Prerequisites

- Lab MongoDB replica set or sharded cluster (not standalone).
- Java 17 and verified MongoDB Java Sync Driver version.
- URI authorized to watch source collections and run CRUD in the lab namespace.
- Never run experimental watchers on production.
- Never drop shared databases or lab clusters.
- Never alter oplog sizes or cluster configs.
- Run strictly one active consumer instance per `streamKey`.

### 27.2. Creating Lab Fixtures in `mongosh`

Use a dedicated lab database:

```javascript
const lab = db.getSiblingDB("mongo_change_row395_lab");

const runId = "row395-" + new ObjectId().toHexString();
const sourceName =
  "events_" + runId.replace(/-/g, "_");

if (lab.getCollectionNames().includes(sourceName)) {
  throw new Error("Collection name already exists");
}

lab.createCollection(sourceName);

printjson({
  database: lab.getName(),
  sourceName,
  runId
});
```

Record `sourceName` and set:

```text
ROW395_SOURCE=<created sourceName>
ROW395_CONSUMER=demo-v1
```

**Do not change `ROW395_SOURCE` across restarts** if you want to observe resumption from the saved token. Keep only one consumer running per `streamKey`.

### 27.3. Start the Java Worker Before Inserting

Launch the Java worker in one terminal using your lab URI and env vars; wait for `Change stream active`.

In a second `mongosh` terminal:

```javascript
const lab = db.getSiblingDB("mongo_change_row395_lab");

// Fill in the exact sourceName/runId from this run:
const coll = lab.getCollection(sourceName);

const docId = new ObjectId();

coll.insertOne({
  _id: docId,
  runId,
  kind: "order",
  status: "CREATED",
  version: 1
});

coll.updateOne(
  { _id: docId, runId, version: 1 },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);

coll.deleteOne({ _id: docId, runId });
```

These writes emit `insert`, `update`, and `delete` events. The worker writes to the idempotent inbox and checkpoints after each event.

**Note:** the Java sample writes audit rows to `row395_processed_events` rather than building a full order projection; its goal is demonstrating proper checkpoint ordering.

### 27.4. Stopping with `SIGTERM` or `CTRL+C`

Trigger normal JVM/container shutdown and observe:

```text
shutdown signal
    -> stopping=true
    -> tryNext poll returns
    -> cursor close
    -> client close
```

With `CTRL+C`, the JVM usually runs shutdown hooks depending on OS/container settings. **Never use `SIGKILL` for routine stops.**

### 27.5. Restarting and Verifying the Checkpoint

Restart with identical configuration:

- `MONGODB_URI`;
- `ROW395_SOURCE`;
- `ROW395_CONSUMER`;
- unchanged `pipeline-v1`.

The worker reads the checkpoint and invokes `resumeAfter(token)`. Already-checkpointed events do not replay; any crash prior to checkpointing replays cleanly and gets deduplicated via the event key.

Inspect checkpoints (read-only):

```javascript
const ck = lab.getCollection("row395_change_checkpoints");

ck.find(
  {
    _id: {
      $regex: "^mongo_change_row395_lab:"
    }
  },
  {
    _id: 1,
    updatedAt: 1,
    resumeToken: 0
  }
).limit(20).toArray();
```

Never print raw tokens in logs or public tickets. Filter by exact `streamKey` in multi-consumer setups.

### 27.6. Testing Failure Windows Deliberately Without Breaking the Cluster

In staging:

1. Simulate a sink failure right before `storeToken` (for instance via an injected test exception).
2. Confirm the checkpoint token stayed at the previous value.
3. Restart the worker with the same key.
4. Confirm the uncheckpointed event replays.
5. Confirm `processedEvents` creates zero duplicates even if the inbox write finished before the simulated crash.
6. Test graceful stop while the stream sits idle.
7. Test graceful stop during a slow fake sink with timeouts.
8. Drill approved network fault tests with infrastructure owners—never kill a production primary.

Never wait for live oplog rollover on real data to trigger `ChangeStreamHistoryLost`; test with synthetic fixtures in an isolated lab.

### 27.7. Controlled Cleanup

Before cleaning up, **stop the Java worker first** so cleanup deletes don't stream back through it.

In `mongosh`:

```javascript
// Only on the sourceName/runId from this test run:
const owned = coll.find(
  { runId },
  { _id: 1, runId: 1 }
).toArray();

for (const item of owned) {
  coll.deleteOne({
    _id: item._id,
    runId
  });
}

print("remaining=" + coll.countDocuments({ runId }));
```

Keep checkpoint and processed-events ledger documents during restart verification. Lab maintainers may prune documents **belonging to that test `streamKey`** per retention rules—never drop whole databases or wipe other consumers' checkpoints.

Only drop temporary lab collections after verifying the namespace is **strictly isolated**, the worker is stopped, and no active consumers reference it; dropping triggers `invalidate` on active watchers, so never include blind drops in automated cleanup scripts.

## 28. Security and Operations

### 28.1. Least-Privilege Permissions

Grant a change stream worker strictly:

- watch/read privileges on the exact source scope;
- write privileges limited to its sink, deduplication ledger, and checkpoint collection;
- zero permissions to drop collections or modify roles;
- reviewed justification if pre-images or `fullDocument` access is enabled;
- dedicated credentials with rotation and auditing;
- TLS encryption in transit.

Never grant cluster-wide admin accounts to a service watching one collection.

### 28.2. Sensitive Data Inside Events

Change events carry field values in `fullDocument` and `updateDescription`. Pipelines, logs, metrics, and sinks must enforce PII masking and authorization checks.

Never tamper with resume tokens or expose them in public URLs. While not KMS keys, they encode operational metadata and deserve restricted access.

### 28.3. Backing Up Checkpoints

If checkpoints are lost while source data remains, you have **no reliable way to know** how far processing reached unless backed by a durable inbox, projection logs, or a recovery protocol.

Back up:

- checkpoint collections;
- sink/inbox ledgers;
- source data and backfill artifacts;
- pipeline versions and stream scope configs;
- audit logs and lease records.

During restores, never let restored checkpoints sit ahead of restored sink state: a checkpoint "newer" than the restored sink causes `resumeAfter` to skip side effects absent from the restored sink. Follow consistent backup/restore ordering and verify consistency.

### 28.4. Multi-Region and Failovers

After primary elections, clients may resume against a newly elected member. MongoDB 9.0 refined read-preference enforcement when node roles transition, raising resumable errors in specific cases handled by modern drivers per specification.

Never pin connections to "primary IP X" in deployments that can elect other members; use replica set seed lists or SRV URIs from environment configuration.

## 29. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| "`watch()` works on standalone MongoDB" | Requires a replica set or sharded cluster |
| "New streams send all existing documents first" | Streams emit changes from their start point onward; backfill separately |
| "`documentKey._id` is the resume token" | The resume token is `changeEvent._id` |
| "`clusterTime` is enough to checkpoint every event" | Store the full opaque resume token BSON document |
| "You can edit bytes inside `_data` tokens" | Tokens are opaque; keep BSON intact |
| "Pipelines can project out `_id` to save bandwidth" | Breaks resumability and triggers server errors |
| "`resumeAfter` works after `invalidate`" | Use `startAfter` under namespace policy when re-attaching |
| "`startAfter` always recovers expired tokens" | Still bounded by oplog history |
| "Saved tokens last forever" | Oplog history retention is finite |
| "`tryNext()` never blocks" | May wait for `getMore` up to `maxAwaitTime` and network timeouts |
| "`maxAwaitTime` bounds HTTP sink latency" | Only bounds server wait on `getMore` |
| "`cursor.getResumeToken()` always matches completed work" | Can advance via `postBatchResumeToken` ahead of pending work |
| "Checkpoint immediately when an event arrives" | Crashes lose side effects permanently |
| "Post-processing checkpoints give exact once-only execution" | Crashes between write and checkpoint replay; sinks need idempotency |
| "Driver auto-resume removes the need for checkpoints" | Driver RAM tokens vanish on process restarts |
| "The driver retries infinitely" | Retries apply only to eligible errors per spec limits |
| "If oplog history is lost, restart from now safely" | Leaves silent data gaps; must re-bootstrap and reconcile |
| "`updateLookup` captures exact event-time state" | Reflects current document state when lookup runs |
| "Delete events carry `fullDocument`" | Normally carry only `documentKey`; pre-images require config |
| "Multiple pods auto-balance a change stream like consumer groups" | Each watcher receives duplicate events |
| "Multiple pods writing one checkpoint concurrently is safe" | Races overwrite progress; needs leases, fencing, or ordered frontiers |
| "Finishing E12 lets you checkpoint past unfinished E10" | Skips E10 permanently on crash recovery |
| "Calling `client.close()` immediately on `SIGTERM` is graceful" | Interrupts in-flight handlers and checkpoint writes |
| "`SIGTERM` hooks always run on OOM / `SIGKILL`" | Hard kills skip hooks entirely |
| "Stop flag guarantees sockets unblock within 1 second" | Network and selection timeouts can exceed `maxAwaitTime` |
| "You can change pipelines freely and reuse old tokens" | Pipelines and options must remain compatible |
| "Writing sink state into the same DB doesn't affect `watch()`" | Database/client-scoped streams suffer feedback loops |
| "Checkpoint `updatedAt` equals source event timestamp" | Records when the consumer persisted the checkpoint |
| "Zero events for 5 hours proves consumer lag" | Idle collections emit zero events normally |
| "Lost checkpoints only need fetching the latest server token" | Skips unapplied changes since the true last write |
| "Change streams replace auth and retention governance" | Still require RBAC, backfill plans, and data governance |

## 30. Practice Exercises

### Exercise A — Identifying the Resume Token

Given event:

```javascript
{
  _id: { _data: "826..." },
  operationType: "update",
  documentKey: { _id: ObjectId("66a000000000000000000395") },
  clusterTime: Timestamp({ t: 1794630000, i: 1 })
}
```

1. Which field is the resume token?
2. Why shouldn't you use `documentKey._id`?
3. Why isn't `clusterTime` sufficient?
4. Should you return the raw token inside HTTP API responses?

### Exercise B — Checkpoint Ordering

```text
Event E7 -> send email -> persist token T7
```

If the process crashes after sending the email and before saving the token, what happens? Where do idempotency keys and deduplication belong?

### Exercise C — Event Loss Bug

```text
Event E8 -> persist token T8 -> call payment API -> crash
```

1. Why can E8 be skipped permanently?
2. Reorder the steps safely.
3. If the payment API times out after charging, how should retries behave safely?
4. Do change streams automatically roll back payment charges?

### Exercise D — `tryNext()` and Graceful Shutdown

Write Java pseudocode combining:

- `AtomicBoolean` stop flag.
- `cursor.tryNext()` loop.
- `maxAwaitTime(2, SECONDS)`.
- Synchronous per-event handling.
- Post-sink token persistence.
- `try-with-resources`.
- Shutdown hook with bounded timeout await.

Explain why `client.close()` must not be the first call inside the hook.

### Exercise E — Resuming After `invalidate`

A watched collection is renamed and the stream emits `invalidate`.

1. Can you call `resumeAfter(invalidateToken)`?
2. When is `startAfter` appropriate?
3. Do you need to verify the recreated collection's schema and ownership?
4. What if the token already fell out of the oplog?

### Exercise F — Oplog History Window

```text
Normal oplog window: 24 hours
Peak oplog window:    4 hours
Consumer downtime:    7 hours
```

1. What failure risk arises on restart?
2. May you silently drop the token and stream from current time?
3. What alerts and capacity headroom should exist?
4. How do you re-bootstrap without creating fresh gaps?

### Exercise G — Multi-Pod Races

Pods `A` and `B` share one `streamKey`. `B` finishes E10 and E11 quickly; `A` stalls on E10 and later overwrites the checkpoint with E10.

1. What goes wrong with the saved token?
2. Is `leaseUntil` alone sufficient to stop stale writers?
3. Where must fencing checks be enforced?
4. How would you redesign the architecture to scale throughput safely?

### Exercise H — Pipeline Evolution

Consumer v1 filters `insert`/`update`; v2 wants only `status: "PAID"`.

1. Why shouldn't you blindly reuse v1's resume token?
2. Can the pipeline project out `_id`?
3. What metadata should versioned checkpoints carry?
4. How would you execute backfill/shadow migration?

### Exercise I — Update Lookup Race

```text
T1: status = PAID
T2: status = REFUNDED
T3: handle T1 event with UPDATE_LOOKUP
```

1. What value might `fullDocument.status` hold?
2. How does `updateDescription` help?
3. When exact business transitions are required, how should an outbox be structured?

### Exercise J — At-Least-Once with a MongoDB Sink

Design `processed_events`:

- Unique `_id` derived from event token hash + consumer name.
- `$setOnInsert` upsert.
- Post-sink checkpointing.
- Crash recovery across every failure window.

Explain why write concern timeouts and token races still need handling.

### Exercise K — Snapshot Bootstrapping

Source holds 5 million documents; the new projection is empty.

1. Why does running `find()` followed by `watch()` leave gaps?
2. How does establishing a start point before the snapshot help?
3. What minimum duration must oplog retention cover?
4. How do you confirm the projection caught up?

### Exercise L — Spring Boot Lifecycle

A bean uses `@PostConstruct` to launch `watch().forEach()` directly on the main startup thread.

1. Why does application startup hang?
2. How should an executor + `SmartLifecycle` be structured instead?
3. How should consumer health inform readiness probes?
4. On Spring context close, in what order should the consumer and `MongoClient` shut down?

### Exercise M — Metrics Design

Design a dashboard with at least 6 metrics distinguishing clearly among:

- idle stream;
- handler backlog;
- failing sink;
- expired resume history;
- continuous cursor reopens;
- shutdown exceeding grace periods.

### Exercise N — Transactional Checkpointing

When both projection and checkpoints live in MongoDB:

1. Which writes belong inside the transaction?
2. Should `watch()` itself run inside the transaction?
3. If the transaction callback retries, may you send email inside it?
4. For external sinks, which outbox/idempotency architecture works?

## 31. Official Reference Documentation

In production, always verify against your exact **server version, topology, FCV, Java Driver version, JVM runtime, and framework**:

- [Open Change Streams — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — `watch()`, filters, `MongoChangeStreamCursor`, pre/post-images, and synchronous cursor behavior.
- [MongoDB Change Streams — Server Manual](https://www.mongodb.com/docs/manual/changestreams/) — availability, oplog history, resume tokens, resume/start semantics, and sharded clusters.
- [`$changeStream` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changestream/) — `resumeAfter`, `startAfter`, `startAtOperationTime`, `fullDocument`, and expanded events.
- [Java Sync Driver `ChangeStreamIterable` API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/driver-sync/com/mongodb/client/ChangeStreamIterable.html) — overloads, `maxAwaitTime`, `batchSize`, and resume options.
- [Java Sync Driver `MongoChangeStreamCursor` API](https://mongodb.github.io/mongo-java-driver/5.5/apidocs/driver-sync/com/mongodb/client/MongoChangeStreamCursor.html) — `tryNext()`, `getResumeToken()`, lifecycle, and thread safety.
- [Java Driver Change Stream Examples](https://github.com/mongodb/mongo-java-driver/blob/main/driver-sync/src/examples/documentation/ChangeStreamSamples.java) — official examples of resume tokens and `watch()` usage.
- [Change Streams Specification](https://github.com/mongodb/specifications/blob/master/source/change-streams/change-streams.md) — driver resumable error rules and cached/`postBatchResumeToken` updates.
- [`invalidate` event](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/) — drop/rename/dropDatabase semantics and `startAfter`.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — reasoning about oplog sizing and retention windows.
- [`rs.printReplicationInfo()`](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/) — inspecting server replication history.
- [Transactions in Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — transaction retry callbacks and atomic checkpoints where appropriate.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — selecting durability levels for checkpoints and sinks.
- [MongoDB `serverStatus`](https://www.mongodb.com/docs/manual/reference/command/serverStatus/) — server telemetry, including change stream metrics in newer releases.
- [MongoDB Drivers Compatibility](https://www.mongodb.com/docs/drivers/) — selecting compatible driver/server combinations.

**Version note:** Java examples use APIs from the Java Sync Driver 5.x series. Features such as `showExpandedEvents`, pre/post-images, specific change stream `serverStatus` metrics, and election resumption rules vary across MongoDB releases; never assume every cluster supports all features. Complete Spring/retry/outbox skeletons with deployment-specific configuration and error handling before production use.

## 32. Conclusion

A Java consumer backed by MongoDB change streams becomes dependable only when **event semantics, progress tracking, and lifecycle management** work together:

1. **`watch()`** tracks changes across compatible collections, databases, or deployments, without sending an initial historical snapshot.
2. **Resume tokens** are opaque BSON documents in `changeEvent._id`; store them intact and use `resumeAfter()` to pick up after checkpointed events. Reserve `startAfter()` for special cases like `invalidate`, and supply valid in-oplog timestamps to `startAtOperationTime()`.
3. **Apply side effects first, persist checkpoints second** to avoid marking incomplete work finished. Crashes between those steps replay events—handle replays cleanly with idempotency.
4. **`tryNext()` + stop flag + `try-with-resources`** build the foundation for graceful shutdown, calibrated alongside network timeouts, handler execution time, and orchestrator grace windows.
5. **Driver auto-resumption** handles only transient eligible errors—never replacing durable checkpoints or re-bootstrapping when tokens expire out of the oplog.
6. **Every `streamKey` needs clear ownership**, particularly across multiple pods. Never let out-of-order workers advance checkpoints past unfinished events.
7. **Monitor oplog retention windows, event lag, sink failures, checkpoint age, and shutdown metrics** so silent data-loss risks surface early.
8. **Lost oplog history or pipeline changes** require explicit re-bootstrapping and reconciliation—never silently watching "from now".

**Core principle:** treat the resume token as a **commitment of changes durably processed by your system**, not merely what MongoDB delivered over the socket. Graceful shutdown minimizes duplicates, while idempotency, disciplined checkpointing, and tested recovery protocols keep data processing trustworthy across crashes, deploys, failovers, and prolonged outages.
