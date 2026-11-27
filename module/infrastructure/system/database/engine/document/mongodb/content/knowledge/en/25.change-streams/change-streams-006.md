# `resumeAfter`, `startAfter`, `startAtOperationTime`, and Recovery Scenarios in MongoDB Change Streams

## 1. The Core Problem: Where Should a Consumer Resume?

MongoDB **Change Streams** enable applications to monitor data change events without tailing the oplog directly. A consumer can use them to update a search index, publish events to a message broker, refresh caches, build read models, or trigger business reactions on insert/update/delete.

Suppose an `order-indexer` service listens to `commerce.orders`:

```text
MongoDB                         Change stream consumer                    Search index
   |                                     |                                    |
   | -- E1: insert O100 ----------------> | -- index O100 ------------------> |
   | -- E2: update O100 ----------------> | -- update O100 -----------------> |
   |                                     X  service crash                     |
   | -- E3: insert O101                 |                                    |
   | -- E4: delete O100                 |                                    |
   |                                     |  restart                           |
   |                                     ?  resume from which event?          |
```

If the consumer opens a fresh `watch()` without a checkpoint, E3 and E4 that occurred while the service was down are skipped. If it reopens too early, E2 may be processed again; if the handler is not idempotent, that causes duplicate side effects.

MongoDB provides three options for choosing the starting point when **opening** a stream:

- **`resumeAfter`**: resume after the **resume token** of a known position, commonly used after a restart or connection error.
- **`startAfter`**: start a **new stream** after a token, notably usable when the last token came from an **`invalidate`** event.
- **`startAtOperationTime`**: start at or after a **BSON Timestamp**, when no resume token exists yet but a reliable operation time is available, or when intentionally backfilling from a point in time.

These three options are **mutually exclusive**. They do not replace persisting checkpoints, preserving processing order, or designing idempotency in target systems.

> **Principle:** MongoDB manages the read position; the application is responsible for proving an event has been applied to the sink before the checkpoint advances past that event.

---

## 2. Prerequisites for Change Streams to Work

| Prerequisite | Explanation |
| --- | --- |
| Deployment is a **replica set** or **sharded cluster** | Standalone `mongod` does not support change streams because it lacks a replica set oplog. |
| Compatible storage engine and replication | MongoDB requires WiredTiger and replication protocol version 1 (`pv1`) for change streams. |
| Sharded cluster connects via **`mongos`** | Routers create/merge streams from shards rather than forcing applications to merge oplogs manually. |
| Scope-matched access privileges | The account needs appropriate privileges to watch the collection, database, or deployment. |
| Oplog retains history | Resuming from a past token/timestamp requires the corresponding oplog entries to still exist. |
| Capable driver | Java Sync Driver provides `watch()`, `ChangeStreamIterable`, resume options, and cursor tokens. |
| Supported namespace | System collections, `admin`, `config`, `local`, and time-series collections have respective restrictions. |

Change streams emit events for majority-committed changes under MongoDB semantics. Do not treat them as a mechanism to receive every transient operation applied on a primary that could still roll back.

### 2.1. Choosing Scope

In `mongosh`:

```javascript
// Collection-level:
db.getSiblingDB("commerce").orders.watch();

// Database-level:
db.getSiblingDB("commerce").watch();

// Deployment-level, receiving from supported databases:
db.getMongo().watch();
```

In Java:

```java
collection.watch();
database.watch();
mongoClient.watch();
```

Tokens are bound to the change stream context, so when resuming you must keep **the same scope, pipeline, and options**. Never take a token from a collection watch, arbitrarily switch to a deployment watch, and assume the position and semantics stay identical.

### 2.2. Sharded Architecture

```text
              Java Consumer
                    |
                    v
                 mongos
              /     |     \
             v      v      v
         Shard A Shard B Shard C
             \      |      /
              \     |     /
              merged change stream
```

`mongos` opens corresponding change streams on shards and sorts/filters/merges them. Shard removal can close the stream and is not guaranteed to be seamlessly resumable in every case. Maintain a dedicated runbook for major topology changes.

---

## 3. Change Events, `clusterTime`, and Resume Tokens

An illustrative event:

```javascript
{
  _id: { _data: "SERVER_GENERATED_OPAQUE_TOKEN" },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1794632400, i: 1 }),
  ns: { db: "commerce", coll: "orders" },
  documentKey: { _id: "O100" },
  fullDocument: {
    _id: "O100",
    status: "CREATED"
  }
}
```

This is a **structural example**, not a real token you can use.

- **`event._id`** is the entire **resume token BSON document**.
- `operationType`: `insert`, `update`, `replace`, `delete`, `drop`, `rename`, `invalidate`, and others depending on version/options.
- `clusterTime`: **BSON Timestamp**, representing the logical time of the operation; not an arbitrary `Date`.
- `ns`: database/collection of the event.
- `documentKey`: key identifying the source document.
- `fullDocument`: document contents per event/options; omitted by default on `update`.

**Never confuse `event._id` with `documentKey._id`.** The resume token identifies stream position, not the `orders` record key.

### 3.1. Tokens Are Opaque: Preserve Exact BSON

Do not do this:

```javascript
// Wrong: fabricating a token from business keys or a clock.
const token = {
  _data: orderId + ":" + Date.now()
};
```

Never slice `_data` hex strings, reorder fields, turn a token into a business ID, or substitute `clusterTime` for a token.

Instead, store:

```javascript
{
  _id: "orders-cdc-v1",
  token: event._id,
  lastOperationType: event.operationType,
  scope: "commerce.orders"
}
```

This preserves the server-issued BSON token intact.

### 3.2. Event Tokens vs. High-Watermark Tokens

Conceptually, MongoDB distinguishes two token roles:

1. **Event token**: corresponds to a specific change event.
2. **High-watermark token**: represents a point of progress in the stream without needing to attach to a returned event.

In addition to each event's `_id`, `aggregate`/`getMore` responses can carry `cursor.postBatchResumeToken` (PBRT), even when the batch is **empty**. The Java driver caches this position on the cursor.

An idle stream does not mean no token progress occurs. However, in a sharded cluster, the high-watermark can advance slowly if one shard sees little write activity.

---

## 4. Comparison of the Three Methods

| Criterion | `resumeAfter` | `startAfter` | `startAtOperationTime` |
| --- | --- | --- | --- |
| Parameter accepted | BSON resume token | BSON resume token | BSON Timestamp |
| Starting position | **After** the given token | **After** the given token, opening a new stream | **At or after** the logical timestamp |
| Common use case | Restarting when a token exists | Continuing after `invalidate` | Bootstrap/backfill without a token |
| After `invalidate` | **Not supported** | **Supported** | Does not pinpoint past an invalidate token cleanly |
| Distinguishes events with identical timestamp | Yes | Yes | Cannot pinpoint one individual event |
| Depends on oplog history | Yes | Yes | Yes, if the timestamp is in the past |
| Can combine with the other options? | No | No | No |

Valid syntax examples:

```javascript
orders.watch([], {
  resumeAfter: savedToken
});

orders.watch([], {
  startAfter: invalidateToken
});

orders.watch([], {
  startAtOperationTime: savedBsonTimestamp
});
```

Invalid:

```javascript
// These three options are mutually exclusive:
orders.watch([], {
  resumeAfter: savedToken,
  startAfter: invalidateToken
});
```

Passing two of the three options simultaneously causes the server to return an error, not an automatic fallback.

---

## 5. `resumeAfter` — Standard Recovery Path

`resumeAfter` takes the token of a stream position safely processed by the consumer. MongoDB returns events **after** that position.

```text
E1 ---- E2 ---- E3 ---- E4 ---- E5
         ^
         |
      checkpointed token T2

watch({ resumeAfter: T2 })
=> E3, E4, E5, ...
```

This is the preferred choice when the consumer holds a valid token from the same subscription and needs to continue from its checkpoint.

### 5.1. `mongosh` Example

```javascript
const orders = db.getSiblingDB("commerce").orders;
const cursor = orders.watch();

let savedToken;

// In another terminal, insert/update to generate an event.
if (cursor.hasNext()) {
  const event = cursor.next();

  // A real consumer must process the event successfully first.
  printjson(event);

  savedToken = event._id;
}

cursor.close();

if (savedToken) {
  const resumedCursor = orders.watch([], {
    resumeAfter: savedToken
  });

  // resumedCursor awaits events following savedToken.
}
```

Storing the token in a variable merely demonstrates the method. A process restart loses in-memory variables; persist checkpoints to durable storage.

### 5.2. Critical Prerequisites

- The token must be **server-provided**, never fabricated.
- The oplog must retain enough history.
- The reopened stream should use **the same pipeline, options, and scope** as when the token was issued.
- **Never use `resumeAfter` after `invalidate`**.

If the token has expired and history has been overwritten, retrying the same command repeatedly will not bring old events back.

### 5.3. "After Token" Does Not Prove the Sink Received the Event

MongoDB only tracks stream position. If an application persists T2 before sending E2 to the search index and then crashes, restarting begins at E3 and the sink **loses E2**. That is a bug in the checkpointing protocol, not a bug in `resumeAfter`.

---

## 6. `startAfter` — Recovering a Stream After `invalidate`

An **`invalidate` event** signals that the stream is no longer valid for the watched scope. On a collection-level stream, it can occur after a `drop`, `rename`, or `dropDatabase` affecting the collection, closing the cursor.

Timeline:

```text
Collection commerce.orders:
E1 insert
E2 update
E3 drop collection
E4 invalidate         <-- stream closes
      |
      +-- resumeAfter(T4) => invalid
      |
      +-- startAfter(T4)  => can open a new stream
```

Usage:

```javascript
const lastInvalidateToken = invalidateEvent._id;

const restarted = db.getSiblingDB("commerce")
  .orders.watch([], {
    startAfter: lastInvalidateToken
  });
```

`invalidateEvent` is the real event received from the stream. Never use a fabricated or placeholder token.

### 6.1. `startAfter` Does Not Restore the Collection

If a collection was dropped, `startAfter` merely positions a **new** stream after the invalidation. It does not:

- Recover deleted data.
- Recreate indexes or validation rules.
- Guarantee a recreated collection with the same name shares the same UUID/generation.
- Restore a wiped search index or read model.
- Replace backups or PITR.

Therefore, after an `invalidate`, you must decide:

1. **Planned, approved migration?** Reopen the stream, record a new generation, and rebuild if needed.
2. **Unexpected drop or rename?** Trigger incident response—never quietly continue.
3. **Database-level vs. collection-level watch?** Verify the exact invalidation scope.
4. **Does the oplog still hold history?** If the token expired, `startAfter` cannot rescue it either.

### 6.2. `drop` Token Differs from `invalidate` Token

A stream may emit a `drop` event followed by an `invalidate` event. Use the **`invalidate` event's token** when opening after invalidation, and persist `operationType` alongside the checkpoint to distinguish it from prior events.

```javascript
{
  _id: "orders-indexer",
  token: { _data: "..." },
  lastOperationType: "invalidate",
  generation: 2
}
```

### 6.3. Scope Determines Lifecycle

| Scope | Operations That Terminate the Stream |
| --- | --- |
| Collection | Drop/rename of the collection, or `dropDatabase` of its database. |
| Database | `dropDatabase` of the watched database. |
| Deployment | Has distinct behavior; do not extrapolate directly from collection-level streams. |

Dropping one collection does not necessarily close every database- or deployment-level change stream in the exact same way. Always account for your watch scope.

---

## 7. `startAtOperationTime` — Opening from a Logical Point in Time

Unlike the two token-based options, `startAtOperationTime` accepts a **BSON Timestamp**:

```javascript
Timestamp({ t: 1794632400, i: 1 })
```

Here `t` represents the seconds portion of the timestamp, and `i` is the logical ordinal increment within that second.

**A BSON Timestamp is not a BSON Date.**

```javascript
// BSON Date: commonly used in application documents:
ISODate("2026-11-14T09:00:00Z")

// BSON Timestamp: used as a change stream starting point:
Timestamp({ t: 1794632400, i: 1 })
```

Usage:

```javascript
// savedBsonTimestamp must be obtained/persisted from MongoDB,
// and still be within the oplog if it lies in the past.
const cursor = db.getSiblingDB("commerce")
  .orders.watch([], {
    startAtOperationTime: savedBsonTimestamp
  });
```

Invalid:

```javascript
orders.watch([], {
  startAtOperationTime: new Date()
});
```

A BSON Date from `new Date()` is not accepted by this option.

### 7.1. `startAtOperationTime` May Redeliver Events Sharing a Timestamp

Suppose one transaction produces:

```text
E1 update A      clusterTime=T, token=T1
E2 update B      clusterTime=T, token=T2
E3 insert audit  clusterTime=T, token=T3
```

If a consumer already applied E2 and restarts with `startAtOperationTime: T`, it may receive E1 and E2 again. When token T2 is available, `resumeAfter: T2` is superior because it positions **immediately after that exact event**.

Per the MongoDB Change Streams Driver Specification, `startAtOperationTime` begins returning changes **at or after** the specified Timestamp. Never treat a timestamp as a unique event identity.

### 7.2. When Should You Use It?

- Initial bootstrap when no resume token exists yet, but a valid operation time was captured.
- Intentional replay/backfill from a recorded logical timestamp.
- Migrating from a legacy CDC tool that persisted only Timestamps, paired with deduplication/reconciliation.
- Bridging a snapshot and a stream under a coordinated protocol.

### 7.3. When Should You Avoid It?

- You already have a valid event resume token: `resumeAfter` is exact.
- You lack a server timestamp and only have a client clock: provides no no-gap guarantee.
- The timestamp is too old and outside the oplog window: cannot reconstruct lost events.
- Trying to bypass an `invalidate` by guessing a newer timestamp: handle the collection lifecycle explicitly instead.

---

## 8. Decision Flow for Selecting a Recovery Method

```text
Consumer starts / reopens stream
                 |
                 v
Checkpoint token available?
       |                     |
      Yes                    No
       |                     |
       v                     v
Is it an invalidate token?  Reliable BSON Timestamp available?
    |          |               |         |
   No         Yes             Yes        No
    |          |               |         |
    v          v               v         v
resumeAfter  startAfter  startAtOperationTime  Bootstrap with
    |          |               |             explicit policy
    +----------+---------------+
                  |
                  v
       Enough oplog history retained?
             |         |
            Yes        No
             |         |
             v         v
        Process     Rebuild/backfill/
        & checkpoint reconciliation
```

In production, add validation layers for `scope`, `pipelineVersion`, `optionsVersion`, worker ownership, and checkpoint integrity before entering any branch.

---

## 9. Hands-On with `mongosh`: Generating Events and Resuming

Test dataset on a replica set or sharded cluster:

```javascript
const lab = db.getSiblingDB("cdc_lab");

lab.orders.insertOne({
  _id: "O100",
  status: "CREATED",
  createdAt: new Date()
});
```

In Terminal A:

```javascript
const orders = db.getSiblingDB("cdc_lab").orders;

const cursor = orders.watch([], {
  maxAwaitTimeMS: 1000
});

print("Change stream ready");
```

In Terminal B:

```javascript
const orders = db.getSiblingDB("cdc_lab").orders;

orders.insertOne({
  _id: "O101",
  status: "CREATED"
});

orders.updateOne(
  { _id: "O101" },
  { $set: { status: "PAID" } }
);
```

Back in Terminal A:

```javascript
const firstEvent = cursor.next();
printjson(firstEvent);

const savedToken = firstEvent._id;
printjson(savedToken);

cursor.close();

const resumed = orders.watch([], {
  resumeAfter: savedToken
});

// The event immediately following firstEvent can now be returned.
// resumed.next() will block if no further events arrive.
```

**Note:** this example requires MongoDB supporting change streams, not standalone; the collection and IDs are strictly for lab use. `next()` blocks waiting for events, so avoid unbounded loops in automated test scripts without event generation.

---

## 10. Designing Durable Checkpoints

Checkpoints must be stored outside process memory:

```javascript
{
  _id: "commerce-orders-search-v3",
  resumeToken: { _data: "<opaque token from server>" },
  resumeMode: "resumeAfter",
  scope: {
    type: "collection",
    database: "commerce",
    collection: "orders"
  },
  pipelineVersion: 3,
  optionsVersion: 2,
  lastOperationType: "update",
  lastClusterTime: Timestamp({ t: 1794632400, i: 2 }),
  checkpointedAt: ISODate("2026-11-14T10:00:00Z")
}
```

This illustrates the checkpoint document schema only, without a real token.

### 10.1. Why Store Versions and Scope?

- Switching from `collection.watch()` to `database.watch()` does not guarantee the old token is compatible.
- Adding or removing `$match`, `fullDocument`, pre-/post-images, or `showExpandedEvents` changes stream semantics.
- If two workers on different code versions share one checkpoint `_id`, the older worker could overwrite with a token incompatible with the new pipeline.
- If a collection is dropped and recreated, track data generations so stale checkpoints are not misapplied.

### 10.2. Store Intact BSON Only

```javascript
const checkpoint = {
  _id: "orders-indexer",
  resumeToken: firstEvent._id,
  updatedAt: new Date()
};

db.getSiblingDB("cdc_state")
  .checkpoints.replaceOne(
    { _id: checkpoint._id },
    checkpoint,
    { upsert: true }
  );
```

If checkpoints live outside MongoDB, serialize/deserialize via **BSON Extended JSON or an official BSON codec**—never strip it down to a bare `_data` string lacking type metadata.

### 10.3. Protecting Checkpoints

- Persist with an appropriate write concern.
- Restrict write access so unrelated applications cannot mutate checkpoints.
- Monitor checkpoint deletion or reset events.
- Enforce ownership/leases/fencing when multiple consumers share a subscription.
- Never overwrite a valid checkpoint with `null` before the cursor yields a token.
- Never equate a fresh `updatedAt` timestamp with the consumer actually being caught up.

---

## 11. Checkpointing Before vs. After Processing and Correctness

### 11.1. Dangerous: Checkpointing Before Applying the Event

```text
Receive E2
   |
   v
Persist T2
   |
   X crash before applying E2
   |
   v
Restart resumeAfter(T2) => E3 onward
=> Sink loses E2
```

This design risks **dropping events**.

### 11.2. Safer: Process First, Then Checkpoint

```text
Receive E2
   |
   v
Apply E2 successfully
   |
   X crash before Persist T2
   |
   v
Restart resumeAfter(T1)
=> E2 may be applied a second time
```

This provides **at-least-once** delivery at the consumer layer, requiring an **idempotent sink**.

### 11.3. Exactly-Once Is Not Automatic

Change stream resume tokens **do not** automatically guarantee exactly-once delivery for:

- Emails.
- HTTP webhooks.
- Search indexes.
- Kafka or other message brokers.
- Statistical counters incremented via `$inc` without deduplication.

An event can be processed twice if the consumer crashes after committing to the sink but before persisting the checkpoint.

### 11.4. Idempotent Operations

Using `$set` to assign a field to the same value can be idempotent:

```javascript
db.orderReadModels.updateOne(
  { _id: "O100" },
  { $set: { status: "PAID" } },
  { upsert: true }
);
```

Even this is not always enough on its own. If an older event runs out of order after a newer event, it can **overwrite newer state**. You still need ordering, sequence numbers, or version fences.

Not idempotent:

```javascript
db.dashboard.updateOne(
  { _id: "paid-orders" },
  { $inc: { count: 1 } },
  { upsert: true }
);
```

If the `PAID` event replays, the counter increments twice.

### 11.5. Design Guidelines

- Use an explicit event identity or stable business key.
- Record a processed-event marker protected by a unique constraint.
- Apply state and marker **atomically** when both live inside the same MongoDB transaction.
- Otherwise, rely on sink-side idempotency, inbox/outbox patterns, and reconciliation.
- Never skip a failing event and advance the checkpoint past it unless an explicit policy records the discard.

---

## 12. `postBatchResumeToken` and Empty Batches

A change stream does not need continuous events. `getMore` responses can return an empty batch alongside a `postBatchResumeToken`.

```text
10:00: event E1; token T1
10:01: empty batch; PBRT T_10:01
10:02: empty batch; PBRT T_10:02
```

A high-watermark token represents a stream position passed safely, without needing an attached event.

### 12.1. The Java Driver Caches the Token

```java
MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
    collection.watch().cursor();

ChangeStreamDocument<Document> event = cursor.tryNext();
BsonDocument token = cursor.getResumeToken();
```

`token` **may be null initially**. After consuming events or empty batches carrying PBRT, the driver exposes the updated token. Do not track only the last event's token and assume an idle stream makes zero progress.

### 12.2. Never Checkpoint Past Unprocessed Events

```text
Batch: E1, E2, E3

E1 processed successfully.
E2 processing failed.
E3 not yet processed.

=> Must NOT checkpoint past E3.
```

If processing a batch concurrently, track the **contiguous completed offset** rather than checkpointing whichever event finishes fastest. A single sequential processing loop avoids this whole class of bugs.

### 12.3. Sharded Clusters Can Slow High-Watermark Progress

An idle shard with few writes can hold back high-watermark advancement. Never declare a stream broken solely because the token stayed unchanged for a few seconds; also inspect source traffic, `getMore` calls, shard health, connection pools, and consumer lag.

---

## 13. Java Sync Driver: Opening a Stream from a Checkpoint

Key types to use:

```java
org.bson.BsonDocument;   // Resume token
org.bson.BsonTimestamp;  // Logical operation time
```

Factory example:

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoCollection;
import org.bson.BsonDocument;
import org.bson.BsonTimestamp;
import org.bson.Document;
import org.bson.conversions.Bson;
import java.util.List;

public final class ChangeStreamFactory {

    public static ChangeStreamIterable<Document> open(
            MongoCollection<Document> collection,
            List<Bson> pipeline,
            BsonDocument token,
            boolean tokenIsInvalidate,
            BsonTimestamp operationTime
    ) {
        if (token != null && operationTime != null) {
            throw new IllegalArgumentException(
                "Choose token or operationTime, not both"
            );
        }

        ChangeStreamIterable<Document> stream =
            collection.watch(pipeline);

        if (token != null) {
            return tokenIsInvalidate
                ? stream.startAfter(token)
                : stream.resumeAfter(token);
        }

        if (operationTime != null) {
            return stream.startAtOperationTime(operationTime);
        }

        // Allowed only if this is a brand-new subscription and
        // starting from "now" is acceptable to business rules.
        return stream;
    }
}
```

`tokenIsInvalidate` must come strictly from checkpoint metadata recorded with the event itself—never guessed from collection names or connection errors.

### 13.1. Java BSON Timestamp

```java
import org.bson.BsonTimestamp;

// savedSeconds and savedIncrement must be valid values
// obtained from a durably recorded MongoDB operation time.
BsonTimestamp at = new BsonTimestamp(
    savedSeconds,
    savedIncrement
);

ChangeStreamIterable<Document> stream =
    collection.watch().startAtOperationTime(at);
```

Do not cast `java.util.Date` into a `BsonTimestamp` while inventing a logical increment. When a token exists, prefer resuming by token.

---

## 14. Java Sync Driver: Read, Process, and Checkpoint Loop

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.BsonDocument;
import org.bson.Document;

public final class ChangeStreamWorker {

    public interface EventSink {
        // Ensure reprocessing does not duplicate side effects.
        void applyIdempotently(ChangeStreamDocument<Document> event);
    }

    public interface CheckpointStore {
        // Persist durably, not solely in RAM.
        void save(BsonDocument token);
    }

    public static void run(
            ChangeStreamIterable<Document> source,
            EventSink sink,
            CheckpointStore checkpoints
    ) {
        try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
                 source.cursor()) {

            while (!Thread.currentThread().isInterrupted()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event != null) {
                    // Do not checkpoint if the handler throws.
                    sink.applyIdempotently(event);

                    BsonDocument token = cursor.getResumeToken();
                    if (token == null) {
                        token = event.getResumeToken();
                    }

                    if (token != null) {
                        checkpoints.save(token);
                    }
                } else {
                    // May have received PBRT on an empty batch.
                    BsonDocument token = cursor.getResumeToken();

                    if (token != null) {
                        checkpoints.save(token);
                    }
                }
            }
        }
    }
}
```

This is a **single-threaded processing skeleton**, not a complete production consumer. You still need `EventSink`/`CheckpointStore` implementations, backoff retries, `invalidate` handling, shutdown signals, ownership fencing, and telemetry.

**Advantage:** if the sink throws an exception, the code does not advance the checkpoint past that event.

**Limitation:** if the sink and checkpoint live in different systems, they do not commit atomically together. A crash right between the two writes causes a replay, which is why the sink must be idempotent.

### 14.1. `tryNext()` vs. `next()`

| Method | Behavior |
| --- | --- |
| `cursor.next()` | Waits for a change event; may block indefinitely. |
| `cursor.hasNext()` | Also blocks while awaiting events. |
| `cursor.tryNext()` | Waits up to `getMore`/await timeout, then returns an event or `null`. |
| `cursor.getResumeToken()` | Driver-cached position from the latest event or PBRT if available. |
| `cursor.close()` | Releases the cursor and underlying connection resources. |

Never open a cursor per HTTP request if the application only needs one shared subscriber. Change stream cursors hold connections during `getMore` waits; having more streams than connection pool capacity introduces latency.

### 14.2. Saving a BSON Token from Java

When persisting the token into MongoDB:

```java
BsonDocument token = cursor.getResumeToken();

if (token != null) {
    Document checkpoint = new Document(
        "_id", "orders-indexer"
    ).append(
        "resumeToken", token
    ).append(
        "checkpointedAt", new java.util.Date()
    );

    checkpointsCollection.replaceOne(
        new Document("_id", "orders-indexer"),
        checkpoint,
        new com.mongodb.client.model.ReplaceOptions()
            .upsert(true)
    );
}
```

This save must happen after the handler finishes, or inside a transaction alongside the sink. When `token == null`, never write a null checkpoint that clobbers an older valid position.

---

## 15. Recovery Scenario A: Normal Service Restart

```text
10:00  E1 processed -> checkpoint T1
10:01  E2 processed -> checkpoint T2
10:02  service crashes
10:03  E3, E4 arrive
10:04  service restarts
```

Steps:

1. Load checkpoint `T2` from durable storage.
2. Validate scope, pipeline/options versions, and ownership.
3. Open the stream with `resumeAfter(T2)`.
4. Consumer processes E3, E4, and subsequent events.
5. Persist the new token after successful processing.

If it crashes after processing E2 but **before** checkpointing T2, E2 is replayed. This is normal under at-least-once semantics; handlers must tolerate duplicates.

**Never substitute restart wall-clock time for T2.** That would skip E3 and E4.

---

## 16. Recovery Scenario B: Network Error or Primary Election

Transient faults include:

- Network hiccups between consumer and MongoDB.
- `mongod`/`mongos` restarts.
- Primary elections or a cursor-hosting node changing role.
- Driver losing a connection and selecting another server per read preference.
- `getMore` errors marked as resumable.

Compliant MongoDB drivers **automatically attempt one resume after a resumable error** using their in-memory cached token. Per the specification, each resumable error triggers a resume attempt; once resumed, subsequent resumable errors follow the same rule.

**Not all errors are resumable.** Authentication/authorization failures, invalid tokens, lost oplog history, malformed pipelines, and sink handler failures require separate handling.

### 16.1. Driver Auto-Resume Does Not Replace Durable Checkpoints

```text
Same process:
  driver holds token in memory -> can auto-resume on transient errors.

Process dies:
  memory is lost -> application needs checkpoint on disk/DB.
```

### 16.2. Read Preference Changes Starting in MongoDB 9.0

MongoDB documentation notes that starting in **9.0**, if a change stream is opened with read preference `primary` or `secondary` and an election changes the serving node's role so it no longer satisfies the preference, `getMore` may return the resumable error `InterruptedDueToReplStateChange` (code `11602`). Compliant drivers automatically resume on an eligible node.

If using raw `getMore` or custom protocol code, follow version-specific documentation rather than guessing error code lists.

### 16.3. Backoff and Error Classification

An outer retry loop must:

- Classify resumable/transient errors accurately.
- Apply exponential backoff with jitter and a retry budget.
- Never reset the token when a reconnect fails.
- Stop normal retries when `history lost` or `invalidate` requires a business recovery decision.
- Alert if the stream stops advancing or the oplog window nears exhaustion.

---

## 17. Recovery Scenario C: Collection Drop/Rename and `invalidate`

Example:

```javascript
// In a test environment:
db.getSiblingDB("commerce")
  .orders.renameCollection("orders_archive");
```

When a collection-level watch is invalidated:

1. Consumer receives/logs the `invalidate` event and its token.
2. The cursor closes.
3. `resumeAfter(tokenInvalidate)` **is not allowed**.
4. `startAfter(tokenInvalidate)` can open a new stream according to policy.
5. If the namespace changed, adjust subscriptions and reinitialize downstream state per contract.
6. If the drop was unexpected, treat it as a data recovery incident rather than a routine restart.

**Note:** `rename`/`drop` events and `invalidate` events can have different tokens. Checkpoint the right event and store `lastOperationType` metadata.

### 17.1. Recreating a Collection Does Not Restore Old Data

A recreated collection may share the same name yet have a different UUID. Calling `startAfter` does not bring back dropped documents. Downstream systems may need to clear and rebuild projections for the new generation.

---

## 18. Recovery Scenario D: Token Older Than the Oplog Window

Suppose:

```text
Oplog retains only 2 hours.
Consumer checkpointed at 08:00.
Service restarts at 13:00.
```

If the token and its underlying oplog entry have already rolled off the oplog, MongoDB cannot resume. The error may be **`ChangeStreamHistoryLost`** or a missing-resume-token error depending on server version.

**Never perform a silent fallback:**

```text
resumeAfter(oldToken) errors
        |
        v
watch() with no options at 13:00
        |
        v
All events during downtime are silently skipped.
```

### 18.1. Proper Recovery Depends on the Downstream System

| Downstream | Rebuildable? | Required Action |
| --- | --- | --- |
| Search index of current data | Usually yes | Snapshot/reindex and cut over by generation. |
| Cache | Usually yes | Invalidate and warm from source of truth. |
| Statistical read model | Depends on source data | Backfill, recompute, and reconcile. |
| Complete historical change audit | Not guaranteed | Needs an external event log or historical backup; current state alone cannot reconstruct every transition. |
| Dispatched webhooks | Depends on receiver | Reconcile/deduplicate; check replay from an outbox. |

### 18.2. Runbook on History Loss

1. **Preserve the old checkpoint for investigation.**
2. Record the incident, last applied event, token, timestamp, and scope/pipeline version.
3. Determine the oplog window and the potentially missed interval.
4. Execute a rebuild/snapshot/backfill or restore from another log source.
5. Cut over to a new checkpoint only after downstream data is reconciled.
6. Never mark the consumer healthy merely because a fresh stream opened without errors.

Switching from `resumeAfter` to `startAfter` with **the same expired token** does not recover lost history. Nor can `startAtOperationTime` read past the oplog window.

---

## 19. Recovery Scenario E: Only Operation Time Is Available

A legacy consumer stored a BSON Timestamp instead of an event token:

```javascript
{
  _id: "orders-consumer-old",
  lastOperationTime: Timestamp({ t: 1794632400, i: 1 })
}
```

While the timestamp remains in the oplog:

```javascript
const checkpoint = db.getSiblingDB("cdc_state")
  .checkpoints.findOne({ _id: "orders-consumer-old" });

const cursor = db.getSiblingDB("commerce")
  .orders.watch([], {
    startAtOperationTime: checkpoint.lastOperationTime
  });
```

Because multiple events can share a timestamp, the consumer must **tolerate replaying already-processed events**, enforce idempotency, and run reconciliation if needed.

If you only recorded a client-side `new Date()`, that **is not** a reliable logical operation time for gapless resumption. Persist server tokens or MongoDB operation times when designing checkpoints.

---

## 20. Recovery Scenario F: Changing Pipeline/Options After Deployment

Original stream:

```javascript
orders.watch([
  { $match: { operationType: "insert" } }
], {
  fullDocument: "default"
});
```

New code:

```javascript
orders.watch([
  {
    $match: {
      operationType: { $in: ["insert", "update"] }
    }
  }
], {
  fullDocument: "updateLookup",
  resumeAfter: oldToken
});
```

MongoDB warns that **resuming from a token must preserve the same pipeline and options**; otherwise resuming may fail or exhibit unpredictable behavior.

### 20.1. Versioning Subscriptions

```javascript
{
  _id: "orders-indexer",
  token: { _data: "..." },
  scope: "commerce.orders",
  pipelineVersion: 4,
  optionsVersion: 2
}
```

When deploying a new version, the consumer compares metadata and either:

- Resumes if the contract matches;
- Or runs migration/backfill and starts a new checkpoint generation;
- Never blindly reuses an old token while silently missing newly added operation types.

### 20.2. Never Alter or Drop Event `_id`

Wrong:

```javascript
orders.watch([
  {
    $project: {
      _id: 0,
      operationType: 1,
      documentKey: 1
    }
  }
]);
```

`_id` is the resume token. MongoDB 4.2+ throws an exception if a change stream pipeline modifies `_id`.

Correct:

```javascript
orders.watch([
  {
    $project: {
      _id: 1,
      operationType: 1,
      documentKey: 1,
      clusterTime: 1
    }
  }
]);
```

Never confuse the change event's `_id` with `documentKey._id` of the source record.

---

## 21. Recovery Scenario G: Sharded Clusters

When reading a change stream through `mongos`:

- The router coordinates streams across shards.
- Results are merged/sorted according to MongoDB semantics.
- Each event carries its own opaque token; never construct `(shardId, clusterTime)` pairs manually.
- PBRT advances according to the high-watermark across shards.
- Chunk migrations and shard removals can affect the stream.
- Shard removal can close the cursor and is **not guaranteed to be completely resumable**.

### 21.1. Never Read Individual Shards to Bypass the Router

```text
Do NOT implement cluster-wide CDC like this:
  Consumer -> shard A directly
  Consumer -> shard B directly
  Consumer -> shard C directly
  Consumer sorts by clusterTime manually
```

This is not equivalent to watching via `mongos`; metadata, ordering, and chunk migrations make manual merging error-prone.

### 21.2. Multiple Events Sharing `clusterTime`

In sharded clusters, multiple events can share the same logical timestamp. Persist the **intact resume token** rather than a timestamp for exact checkpointing. During major topology changes, validate resumability and prepare a backfill plan.

---

## 22. Recovery Scenario H: Events from Multi-Document Transactions

Suppose a transaction generates:

```text
Txn #42:
  E1 update account A
  E2 update account B
  E3 insert transfer log
```

Events within the same transaction can share a `clusterTime`, and a large transaction can even span multiple oplog entries.

```text
E1 clusterTime=T, token=T1
E2 clusterTime=T, token=T2
E3 clusterTime=T, token=T3
```

If E2 has been processed:

- `resumeAfter(T2)` positions cleanly after E2.
- `startAtOperationTime(T)` may replay E1 and E2.

Never treat `clusterTime` alone as an **event identity**. To correlate transactions, inspect fields like `lsid` and `txnNumber` when present, though they do not replace individual event tokens.

**A change stream does not make external sinks transactional.** When applying those events to multiple external systems, design transactional sinks, ordering, or outbox/reconciliation patterns.

---

## 23. `fullDocument: "updateLookup"` and Historical State

A default stream may return only the update delta:

```javascript
{
  operationType: "update",
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

You can request a lookup:

```javascript
orders.watch([], {
  fullDocument: "updateLookup"
});
```

However, `updateLookup` fetches **the current majority-committed document at lookup time**; it is not necessarily the exact state right after the historical update being replayed.

Example:

```text
10:00 E1 status = PAID
10:01 E2 status = REFUNDED
13:00 Consumer resumes from before E1
```

When processing E1 at 13:00, `fullDocument` may show `REFUNDED`—or `null` if the document was later deleted. If you need the exact state as of E1, design with pre-/post-images or an appropriate event store.

### 23.1. Pre-/Post-Images

MongoDB 6.0+ supports pre-/post-images when configured properly on the collection.

- `whenAvailable`: image may be missing/null if unavailable.
- `required`: stream returns an error if a required image is missing.
- **Oplog retention and pre-/post-image retention are separate**; being able to resume an event does not guarantee its historical image still exists.

Do not change `fullDocument` or `fullDocumentBeforeChange` arbitrarily between capturing a token and resuming without checking compatibility.

---

## 24. Bootstrapping from a Snapshot: Avoiding CDC Gaps

A common flawed flow:

```text
10:00 start copying documents as a snapshot.
10:05 snapshot finishes.
10:06 open watch() with no token, starting from now.
```

An update at 10:03 can appear inconsistently in the snapshot while missing from the stream opened afterward—creating a **snapshot-to-stream gap**.

### 24.1. Workflow with an Explicit Seam

```text
A. Capture a stream starting point (token/operation time).
B. Begin snapshotting source data.
C. Watch/buffer changes starting from A while the snapshot runs.
D. Apply snapshot + buffered events using ordering/version fencing.
E. Reconcile results.
F. Cut over to continuous streaming.
```

Merely "opening the stream before the snapshot" **is not enough** if a newer event is applied and then overwritten by a slower snapshot write:

```text
E1 update status=PAID
Snapshot reads status=PAID
E2 update status=REFUNDED
Sink applies E2
Slow snapshot writes status=PAID over sink
=> sink state regresses
```

You need generations/versions, snapshot boundaries, buffering, or reconciliation. For long-running snapshots, oplog retention must cover the entire window from point A until the consumer catches up.

### 24.2. Never Use Java `Instant.now()` as an Offset

A client clock cannot replace a server-issued resume token or logical operation time when zero-gap guarantees are required. Clocks skew, and a timestamp cannot distinguish concurrent events.

---

## 25. Oplog Window — The Recovery Boundary

The oplog has finite retention, and its effective time window fluctuates with write rate.

```text
Timeline: 08:00 --- 09:00 --- 10:00 --- 11:00
Oplog:              [ oldest ........ newest ]
Checkpoint: 08:15
              |
              +--> token may already be outside retained history
```

### 25.1. Checking the Oplog

On a replica set with appropriate privileges:

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

In a sharded cluster, inspect each relevant shard replica set; never assume a single cluster-wide oplog window.

### 25.2. Retention Sizing

Let:

```text
R = smallest relevant oplog window
L = maximum consumer lag
O = outage/restart/recovery budget
M = safety margin
```

Operational target:

```text
R > L + O + M
```

This is a capacity-planning guideline, not an absolute mathematical guarantee. A write burst shrinks the oplog window. Size against **peak load**, not idle averages.

### 25.3. Early Warning Signals

- `clusterTime` of the last processed event.
- Last checkpoint persistence timestamp.
- High-watermark/token progress.
- Consumer backlog and sink latency.
- Oplog retention window per shard.
- Error counts, resume attempts, and history-lost incidents.
- Node availability and connection pool health.

Never treat a fresh `updatedAt` field on a checkpoint document as proof the stream is caught up; the application might just be rewriting the same old token.

---

## 26. Atomic Sink and Checkpoint Persistence Where Possible

If the downstream target is a MongoDB collection **in the same deployment**, you can wrap both in a transaction:

```text
Receive E2
    |
    v
Begin transaction
    |
    +--> Check/deduplicate event identity
    |
    +--> Update read model
    |
    +--> Persist resume token T2
    |
    v
Commit
```

Committing sink state and checkpoint in one transaction eliminates the window where "sink succeeds but checkpoint fails" or vice versa.

### 26.1. Java Pseudocode

```java
try (ClientSession session = client.startSession()) {
    session.withTransaction(() -> {

        // Implement duplicate handling within transaction scope.
        applyEventToReadModel(session, event);

        checkpoints.updateOne(
            session,
            Filters.eq("_id", "orders-consumer"),
            Updates.set(
                "resumeToken",
                event.getResumeToken()
            ),
            new UpdateOptions().upsert(true)
        );

        return null;
    }, options);
}
```

Names like `applyEventToReadModel`, `client`, `event`, `checkpoints`, and `options` represent service components rather than a standalone compilable snippet. The code illustrates **atomic commit placement**; you still need unique constraints, idempotency, retries, leadership fencing, and validation.

### 26.2. Never Put External Side Effects Inside a Transaction Callback

A `withTransaction` callback can be retried automatically on transient errors. Never send emails or call external HTTP APIs inside the callback assuming it runs only once. Use a transactional outbox or sink-side idempotency.

### 26.3. Two Workers on One Subscription

Transaction atomicity does not stop an old worker from writing token T100 after a new worker already wrote T150. You still need leases/fencing epochs, version compare-and-set, or single-owner enforcement.

---

## 27. Driver Auto-Resume Is Not Infinite Retry

Division of responsibilities:

| Responsibility | Owner |
| --- | --- |
| Generating events and resume tokens | MongoDB server. |
| Caching tokens and retrying certain resumable errors | MongoDB driver per spec. |
| Persisting offsets across process restarts | Application. |
| Applying events and deduplicating | Handler/sink. |
| Handling poison events | Consumer/DLQ per policy. |
| Rebuilding when oplog history expires | Application and operations. |
| Restoring a dropped collection | Backups/migrations, not `startAfter`. |
| Validating pipeline/options changes | Deployment workflow. |

For non-resumable errors, infinite reconnection only makes things worse. For example:

- `Unauthorized`: fix privileges.
- `$project` dropping `_id`: fix pipeline.
- History lost: backfill/rebuild.
- `invalidate`: check lifecycle; consider `startAfter`.
- Sink error: do not advance checkpoint; retry event or route to a controlled DLQ.
- Token from a newer server version passed to an older server: verify compatibility.

**Never automatically reset the checkpoint to null** after N retries just to make a consumer "turn green again."

---

## 28. Tokens and Upgrade/Downgrade Compatibility

Resume token formats depend on MongoDB server version and sometimes FCV. Never write custom business parsers for tokens.

In an upgrade plan:

1. Persist durable checkpoints before upgrading.
2. Verify driver compatibility with the target MongoDB server/FCV.
3. Keep scope, pipeline, and options consistent when resuming.
4. Do not assume an older server understands a newer token format after a downgrade.
5. Test in staging with tokens generated by the source version and consumed by the new cursor.
6. Monitor restart duration, oplog window, and catch-up lag.
7. If changing event schemas or pipelines, run a migration with a new checkpoint generation.

Tokens can be inspected for diagnostics using specialized tools, but **never rely on fixed hex layouts** in application routing or deduplication logic.

---

## 29. Testing Recovery Scenarios

Run tests in staging or a test replica set—never induce drops or failovers in production.

| Scenario | How to Test | Expected Result |
| --- | --- | --- |
| Restart after E2 | Persist T2, stop consumer, create E3/E4, restart | E3/E4 are processed if oplog retains history. |
| Crash after sink, before checkpoint | Kill process right at that point | E2 replays; sink produces no duplicate effects. |
| Checkpoint before sink | Simulate buggy consumer code | Reveals lost event so protocol can be fixed. |
| Network disconnect | Sever connection in test environment | Driver handles resumable error when eligible. |
| Primary election | Trigger stepdown in staging | Consumer resumes seamlessly from token. |
| Drop/rename | Trigger valid invalidation on a test collection | Distinguishes `resumeAfter` vs. `startAfter`. |
| Oplog rollover | Keep consumer offline past retention in test | Raises error; never silently resets to "now." |
| Empty batch | Run with zero writes | PBRT/cached token advances safely. |
| Multi-document transaction | Commit multiple updates in one transaction | Identical `clusterTime` is not merged into one event. |
| Pipeline change | Modify filter or `fullDocument` | Version mismatch is detected. |
| Sharded cluster change stream | Write across multiple shards | Connects via `mongos`, no manual oplog merging. |
| Sink timeout | Simulate HTTP/indexing timeout | Does not checkpoint before confirming completion. |
| Poison event | Event fails downstream schema checks | Routed to DLQ/retry policy, never silently skipped. |
| Duplicate worker | Two instances attempt checkpoint writes | Lease/fencing prevents checkpoint regression. |
| Snapshot + CDC | Continuous writes during snapshot | No lost updates or state reversals after cutover. |
| Pre-image retention expired | Replay old event with `required` | Failure is detected and handled per policy. |

### 29.1. Invariants to Verify

- No events within retained history and subscription scope are lost.
- The sink converges to the right state despite replays/duplicates.
- Checkpoints never advance ahead of successful processing.
- Poison events are never silently ignored.
- `invalidate` is never conflated with transient network errors.
- Tokens are never auto-reset when history is lost.
- Competing consumers cannot regress checkpoints.

---

## 30. Practice Exercises

### Exercise 1 — Consumer Restart

A consumer processes E1 and E2; the last checkpoint is T2. During an outage, E3 and E4 occur.

**Question:** Which option should you choose?

**Answer:** `resumeAfter: T2`, provided scope, pipeline, and options remain unchanged and the oplog still retains history.

### Exercise 2 — Invalidate

A collection is dropped. The final event of the collection-level stream is `invalidate` with token `T_inv`.

**Question:** Can you use `resumeAfter`?

**Answer:** No. If business logic permits starting a new stream, use `startAfter: T_inv`. It does not restore dropped documents.

### Exercise 3 — Timestamp

You have a saved MongoDB BSON Timestamp, but no resume token.

**Question:** Which option applies and what is the risk?

**Answer:** `startAtOperationTime`; requires deduplication since multiple events can share the same timestamp. History must still reside in the oplog.

### Exercise 4 — Wrong Type

```javascript
orders.watch([], {
  startAtOperationTime: ISODate("2026-11-14T09:00:00Z")
});
```

**Answer:** Invalid; `startAtOperationTime` requires a BSON Timestamp, not a Date.

### Exercise 5 — Crash After Checkpoint

A handler persists token T2 before updating the search index, and the service crashes.

**Question:** What happens on restart?

**Answer:** `resumeAfter(T2)` skips E2, losing E2's update in the sink. Fix the processing order.

### Exercise 6 — Crash Before Checkpoint

The sink updated E2, then crashed before saving T2.

**Question:** What property is needed?

**Answer:** Idempotency when E2 replays from the older checkpoint.

### Exercise 7 — History Lost

Oplog retention is 2 hours; the consumer was down for 6 hours.

**Question:** Can `startAfter(oldToken)` rescue it?

**Answer:** No, if the history required for the token has expired. You must backfill, rebuild, and reconcile.

### Exercise 8 — Transaction Events

Three events share the same `clusterTime` but have different tokens.

**Question:** Is saving `clusterTime` equivalent to saving the second event's token?

**Answer:** No; a timestamp cannot pinpoint the exact position immediately after the second event.

### Exercise 9 — `$project` Removing `_id`

```javascript
orders.watch([
  { $project: { _id: 0, operationType: 1 } }
]);
```

**Answer:** Invalid; `_id` is the resume token, and the server rejects pipelines that alter or strip it.

### Exercise 10 — Changing Filters

The old consumer watched only `insert`; the new version adds `update`.

**Question:** Should you immediately reuse the old token?

**Answer:** Never assume so. Evaluate pipeline mismatch, version checkpoints, and run migration/backfill if required.

### Exercise 11 — Idle Stream

No events arrive, yet `getMore` returns a PBRT.

**Question:** What does PBRT mean?

**Answer:** It is a high-watermark token marking stream progress; drivers cache it to resume efficiently even without new matching events.

### Exercise 12 — `updateLookup`

Event E1 sets status to `PAID`, then E2 sets it to `REFUNDED`. A consumer replays E1 an hour later.

**Question:** Is E1's `fullDocument` guaranteed to be `PAID`?

**Answer:** No. `updateLookup` may read the newer `REFUNDED` state, or `null` if the document was deleted.

### Exercise 13 — Replacing Sharded Router with Manual Merging

A team opens three direct change streams against three shards and sorts by timestamp.

**Answer:** Not equivalent to watching via `mongos`; introduces routing, chunk-migration, and ordering risks.

### Exercise 14 — Sending Email

A consumer sends an email when an order turns `PAID` and crashes before checkpointing.

**Question:** How do you avoid sending the email twice?

**Hint:** Use an idempotency key, outbox/inbox, or durable delivery status record; `resumeAfter` does not prevent duplicate external side effects.

### Exercise 15 — Snapshot Bootstrap

You copy an entire collection, then open `watch()` from current time afterward.

**Question:** What is the risk?

**Answer:** A data gap during the snapshot window. Capture a CDC starting point before/during the snapshot and enforce ordering and reconciliation.

### Exercise 16 — Worker Conflict

Worker A checkpoints T100, B checkpoints T150, and A then writes T110.

**Question:** What is the fix?

**Answer:** Leases/fencing/compare-and-set or strict consumer partitioning to stop stale workers from regressing checkpoints.

### Exercise 17 — Pre-Image

The token is still resumable, but the pre-image exceeded retention.

**Question:** Does `required` still succeed?

**Answer:** No. Image retention is a separate limit; the stream throws an error if a required image is gone.

### Exercise 18 — Poison Event

A valid event has a payload rejected by the sink.

**Question:** Should you checkpoint past it and keep the stream moving?

**Hint:** Never silently skip it. Implement retry/DLQ policies with explicit checkpoint rules and error trails.

---

## 31. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Opening `watch()` after restart automatically replays missed events." | No; you need a resume token or operation time. |
| "`resumeAfter` works after `invalidate`." | No; use `startAfter` when permitted. |
| "`startAfter` restores a dropped collection." | No; it only positions a new stream after the event. |
| "`startAfter` rescues a token that fell out of the oplog." | No; oplog history is still required. |
| "`startAtOperationTime` accepts a `Date`." | It requires a BSON Timestamp. |
| "One `clusterTime` corresponds to one event." | Multiple events can share a timestamp. |
| "The token is the source document's `_id`." | It is the **change event's `_id`**. |
| "You can construct `_data` from document IDs." | No; tokens are server-generated. |
| "Tokens work forever." | Corresponding oplog history must remain available. |
| "Driver auto-resume eliminates checkpoints." | Driver memory does not survive process restarts. |
| "Drivers retry all errors forever." | Only eligible resumable errors, per spec. |
| "Checkpoint as early as possible." | Saving before sink completion risks losing events. |
| "Saving after sink gives exactly-once." | Replays can still happen; idempotency or atomicity is required. |
| "Without events, the token never advances." | PBRT advances during empty batches. |
| "Drop `_id` with `$project` to slim payloads." | No; `_id` is the resume token. |
| "Changing pipelines while reusing old tokens is always safe." | MongoDB warns it can yield wrong behavior or fail to resume. |
| "`updateLookup` returns an exact historical post-image." | It can return a newer state or null. |
| "If oplog still exists, pre-images surely exist too." | Pre-/post-image retention has separate limits. |
| "A sharded cluster has one shared oplog." | Each shard maintains its own history and state. |
| "Sorting by `clusterTime` merges shard CDC cleanly." | Use `mongos` and the official change stream contract. |
| "On history loss, restarting from now is fine." | Drops intermediate data; handle explicitly. |
| "MongoDB transactions cover email/HTTP calls." | No; external sinks need idempotency. |
| "Two workers sharing a checkpoint is fine." | Checkpoints can regress without fencing. |
| "Infinite cursors cost no resources." | Every stream/`getMore` holds connections and server resources. |
| "`invalidate` always means server failure." | Can be caused by legitimate drop/rename; check scope. |

---

## 32. Production Checklist

1. Deployment supports change streams (not standalone).
2. Sharded clusters connect through `mongos`.
3. Appropriate collection/database/deployment scope selected.
4. Change event `_id` preserved intact in the pipeline.
5. Subscription pipeline and options are versioned.
6. Resume tokens persisted as intact BSON in durable checkpoints.
7. Checkpoints advance only after sink processing succeeds.
8. Handlers are idempotent or sink + checkpoint are atomic.
9. Leases/fencing enforced if multiple consumers share a checkpoint.
10. Checkpoint tracks whether a token came from `invalidate`.
11. `resumeAfter` used for normal events/tokens.
12. `startAfter` used after invalidations per policy.
13. `startAtOperationTime` receives only BSON Timestamps with deduplication.
14. Oplog window exceeds lag + outage budget + safety margin.
15. Never silently reset checkpoints on history loss.
16. Rebuild/backfill and reconciliation workflows exist.
17. PBRT/high-watermark tracked on idle streams.
18. Retries/backoff configured with fatal vs. transient classification.
19. Sink failures, poison events, and DLQs monitored.
20. `fullDocument` `updateLookup` and pre-/post-image retention understood.
21. Bootstrap avoids snapshot/CDC gaps.
22. Tests cover restart, crash, election, `invalidate`, and oplog rollover.
23. Migration plan exists for server/driver/FCV/pipeline upgrades.
24. Connection pools and active stream counts monitored.
25. Recovery procedures comply with security, auditing, and SLA rules.

Diagram:

```text
MongoDB majority-committed changes
                 |
                 v
         Change stream cursor
          | event or PBRT
          v
       Consumer handler
          |
          v
  Apply idempotently to sink
          |
          v
  Persist durable resume token
          |
          +-- restart ---> load token ---> resumeAfter
          |
          +-- invalidate ---> decide lifecycle ---> startAfter
          |
          +-- no token, known timestamp ---> startAtOperationTime
          |
          +-- history lost ---> rebuild/reconcile, not silent reset
```

---

## 33. Official MongoDB Documentation

- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changestreams/): availability, scopes, resume tokens, high-watermark, sharded considerations.
- [`$changeStream` aggregation stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/): structure and starting-point options.
- [`db.collection.watch()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/): collection watch and token resumption.
- [`db.watch()`](https://www.mongodb.com/docs/manual/reference/method/db.watch/): database-level change stream.
- [`Mongo.watch()`](https://www.mongodb.com/docs/manual/reference/method/mongo.watch/): deployment-level change stream.
- [Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/): change event format.
- [`invalidate` change event](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/): drop/rename/dropDatabase and stream termination.
- [Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/): `watch`, `ChangeStreamIterable`, cursors, and `fullDocument`.
- [Change Streams Driver Specification](https://specifications.readthedocs.io/en/latest/change-streams/change-streams/): BSON Timestamp semantics, driver retries, PBRT.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): retention and oplog window.
- [Remove Shards from a Sharded Cluster](https://www.mongodb.com/docs/manual/tutorial/remove-shards-from-cluster/): resumability limits during topology changes.

When deploying, cross-check **MongoDB server version, FCV, Java Driver version, and deployment topology**. Specific error codes, read preference behavior, token formats, and expanded events can vary across versions.

## 34. Conclusion

- **`resumeAfter`** is the primary option for restarting a consumer after processed events: use a **durable BSON token** with matching scope, pipeline, and options.
- **`startAfter`** has one decisive distinction: it can open **a new stream after `invalidate`**, though it does not restore dropped collections or lost history.
- **`startAtOperationTime`** accepts a **BSON Timestamp** to start from a logical time when no token exists or during backfills; it does not pinpoint a single event like a resume token.

All three are bounded by **available oplog history**. On history loss, you must backfill/rebuild/reconcile—never silently start from the current time.

End-to-end recoverability depends on **post-processing checkpoints, idempotency, ownership fencing, `invalidate` handling, oplog monitoring, and a tested recovery procedure**, not merely calling `watch()`.

**The resume token answers "where to continue reading"; consumer design determines "whether every change is applied completely and accurately."**
