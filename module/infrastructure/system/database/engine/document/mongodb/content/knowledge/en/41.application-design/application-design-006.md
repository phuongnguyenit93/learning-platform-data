# Change Notifications: Change Streams, Duplicate Handling, and Consumer Recovery in MongoDB

## 1. Application Design Problem

An ordering system stores documents in an `orders` collection. When an order is created or updated, the application needs to:

- Update an `orderReadModels` collection for fast queries.
- Send status notifications to users.
- Synchronize data to a search engine.
- Update caches or analytics stores.
- Continue processing accurately from a business perspective when a consumer disconnects, the server elects a new primary, or the process restarts.

A naive and unsafe approach is writing to MongoDB and then directly calling another API:

```java
orders.insertOne(order);
notificationApi.send(order);
```

If `insertOne` succeeds but the process crashes before `send`, the event is never sent. If `send` succeeds and the response times out, the request may be retried and sent twice.

MongoDB **Change Streams** let applications subscribe to committed changes recorded in the database and process them with a long-running consumer.

```text
                       MongoDB Replica Set
                                |
              Primary writes --> oplog
                                |
                                v
                     Change Stream cursor
                                |
                                v
                     Consumer Java Worker
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
       Read model           Search index        Notification
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                    Durable checkpoint
                     (resume token)
```

**However:** Change Streams do not automatically provide exactly-once execution of business side effects. Consumers can observe the same event again after errors or restarts. You must intentionally design **idempotency, checkpoints, retries, recovery, and observability**.

> **Guiding principle:** finish processing the change before persisting the checkpoint; accept that changes may be re-read and design processing so re-reading causes no harmful side effects.

---

## 2. Learning Objectives

After this lesson, learners can:

1. Explain Change Streams and the role of the oplog in notification architectures.
2. Build consumers using the MongoDB Java Sync Driver.
3. Distinguish database change events from business domain events.
4. Handle insert, update, replace, delete, and invalidate scenarios.
5. Use `resumeAfter`, `startAfter`, and `startAtOperationTime` in the right contexts.
6. Persist resume tokens durably without losing BSON fidelity.
7. Identify at-least-once delivery, duplicate events, and ambiguous outcomes.
8. Design idempotent consumers targeting MongoDB or external services.
9. Couple checkpoints with side-effect acknowledgments, using transactions when appropriate.
10. Restart consumers after network/election incidents and detect oplog history loss.
11. Bootstrap read models from historical data without creating gaps between snapshots and streams.
12. Design queues, worker ownership, processing order, retries, and metrics.
13. Test failures before/after checkpoints and recovery paths.

---

## 3. What Are Change Streams?

A **Change Stream** is a MongoDB API that lets applications watch committed changes observable under deployment guarantees, instead of continuously polling queries to check for new documents.

Example:

```javascript
use sales;

const stream = db.orders.watch();

while (stream.hasNext()) {
  printjson(stream.next());
}
```

The application can receive change events such as:

- `insert` when a new document is created.
- `update` when fields are updated.
- `replace` when a document is replaced.
- `delete` when a document is deleted.
- Other event types, including drop/rename/invalidate depending on stream scope, server version, and configuration.

### 3.1. Deployment Prerequisites

Change Streams rely on replication history and require a MongoDB deployment supporting them, typically:

- **Replica set**.
- **Sharded cluster**.

A standard standalone `mongod` is not a suitable environment for opening Change Streams. For local testing, use a single-node replica set or Testcontainers configured as a replica set.

### 3.2. Change Streams Are Not an Infinite Durable Queue

Consumer resumption depends on history retained in the oplog or server-supported change history conditions. Once aged history is evicted, an old resume token may no longer be usable.

### 3.3. Change Streams Do Not Completely Replace Domain Events

An update:

```javascript
{ $set: { status: "PAID" } }
```

tells you **data changed**, not necessarily the full business context:

- Did the bank confirm payment?
- Was this an error-correction edit?
- Should an email be sent again?
- Who performed it, and is an audit trail needed?
- Was this a data backfill?

If you need immutable business events, strict ordering, and long-term replay, consider a **transactional outbox** or a dedicated event log.

---

## 4. Basic Consumer Architecture

```text
Client/API
    |
    v
MongoDB orders collection
    |
    v
Change Stream
    |
    v
Single reader / dispatcher
    |
    +--> Validate event schema
    |
    +--> Deduplicate / check processing state
    |
    +--> Apply side effect
    |
    +--> Persist durable checkpoint
    |
    v
Read next event
```

A consumer requires these components:

| Component | Responsibility |
| --- | --- |
| Stream definition | Specifies collection/database/deployment and pipeline |
| Reader | Reads events through the cursor |
| Event decoder | Distinguishes operation types, document keys, full documents |
| Handler | Processes changes per business logic |
| Idempotency store | Prevents harmful duplicate side effects |
| Checkpoint store | Persists processed resume tokens |
| Retry policy | Separates transient errors from unrecoverable failures |
| Owner/lease | Prevents two instances from unintentionally processing the same logical stream |
| Metrics/alerting | Tracks lag, errors, checkpoint age, backlogs |
| Recovery procedure | Recovers cursors, re-snapshots, or replays on history loss |

Never just write `while (cursor.hasNext())` and consider reliable notifications solved.

---

## 5. Watch Scope: Collection, Database, Deployment

MongoDB allows watching at different scopes.

### 5.1. Collection Scope

```javascript
db.orders.watch();
```

Best when you only need events from `orders`.

### 5.2. Database Scope

```javascript
db.watch();
```

Watches supported collections within the database, subject to permissions and options.

### 5.3. Deployment Scope

In `mongosh`, you can watch at deployment level via the appropriate `Mongo` API; the Java Driver provides `MongoClient.watch()`.

```java
MongoClient client = MongoClients.create(uri);

var deploymentStream = client.watch();
```

Broader scopes increase event volume, privilege requirements, resource usage, and filtering complexity.

### 5.4. Choose Scope Based on Consumer Ownership

If you only build `orderReadModels`, prefer watching `orders` rather than watching all databases and filtering in Java. Conversely, if a workflow must observe changes across multiple collections, database or deployment scope may fit better.

---

## 6. Event Structure

A Change Stream event looks like:

```javascript
{
  _id: {
    _data: "82691A..."
  },
  operationType: "update",
  clusterTime: Timestamp({ t: 1794662400, i: 1 }),
  ns: {
    db: "sales",
    coll: "orders"
  },
  documentKey: {
    _id: ObjectId("691800000000000000000001")
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

Key fields:

| Field | Meaning |
| --- | --- |
| Event-level `_id` | **Resume token**, not the document ID |
| `operationType` | Type of change |
| `clusterTime` | BSON Timestamp indicating change position, not a standard wall clock |
| `ns` | Database/collection |
| `documentKey` | Key identifying the modified document |
| `fullDocument` | Optional post-change document depending on options, not always present |
| `updateDescription` | Updated and removed fields for update operations |
| `lsid`, `txnNumber` | Session/transaction metadata where applicable |
| `wallTime` | Wall-clock time when provided by the server |

### 6.1. Distinguish the Two `_id` Fields

```javascript
event._id              // opaque resume token
event.documentKey._id  // business document key
```

Never use `documentKey._id` as the Change Stream resume position; it carries no ordering information across all changes.

### 6.2. Do Not Parse Tokens by Splitting `_data`

Tokens are opaque BSON. Their internal format can change across server versions and topologies. Applications should store the value intact and pass it back via resume APIs.

### 6.3. Do Not Rely Solely on `clusterTime`

Multiple events, especially within transactions, can share a timestamp. Checkpointing solely by `clusterTime` can skip other events sharing that timestamp. The resume token is the primary choice whenever available.

---

## 7. Events Are Emitted After Changes Gain Majority Visibility

MongoDB Change Streams track changes committed under replication semantics and visible in majority-committed history. This is superior to tailing a collection directly with an uncontrolled read preference.

However, do not infer that:

- Events are delivered to consumers **exactly once**.
- Downstream has received the event the instant the database write succeeds.
- There is zero network delay.
- External notifications will succeed.
- There is a fixed latency bound between write and callback.
- All secondaries have caught up simultaneously.

**Source majority persistence and end-to-end side-effect delivery are two separate guarantees.**

---

## 8. Java Sync Driver: Preparing the Connection

Assume the project includes an `org.mongodb:mongodb-driver-sync` dependency compatible with your Java runtime and server.

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

public final class AppBootstrap {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException(
                "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase db = client.getDatabase("sales");
            MongoCollection<Document> orders =
                db.getCollection("orders");

            // Open a Change Stream in a managed worker.
        }
    }
}
```

The connection string should list replica set seeds or use a properly configured SRV mechanism, with TLS/auth/replicaSet as required.

`MongoClient` typically lives for the process lifetime; **each consumer cursor has its own lifecycle**. Never open and close a `MongoClient` per event.

---

## 9. Minimal Consumer Using `MongoChangeStreamCursor`

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

public final class SimpleOrderConsumer {

    public static void consume(
            MongoCollection<Document> orders
    ) {
        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 orders.watch()
                     .fullDocument(FullDocument.UPDATE_LOOKUP)
                     .cursor()) {

            while (cursor.hasNext()) {
                ChangeStreamDocument<Document> event =
                    cursor.next();

                System.out.println(
                    event.getOperationType()
                );
                System.out.println(
                    event.getDocumentKey()
                );
            }
        }
    }
}
```

### 9.1. This Sample Is Only for Learning the API

It lacks durable checkpoints, idempotency, shutdown handling, retries, history-loss detection, and downstream error handling.

### 9.2. `hasNext()` Can Block

A Change Stream continuously awaits new events. When no changes exist, `hasNext()` can block waiting for data.

### 9.3. Close Cursors Proactively

`try-with-resources` guarantees `close()` when the worker finishes or throws. Long-lived services also need stop signals/cancellation so shutdown does not hang indefinitely.

---

## 10. `tryNext()` and `maxAwaitTime` for Stoppable Workers

A service loop usually needs to check a shutdown flag periodically:

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.Document;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class PollingConsumer {

    private final AtomicBoolean running =
        new AtomicBoolean(true);

    public void stop() {
        running.set(false);
    }

    public void run(MongoCollection<Document> orders) {
        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 orders.watch()
                     .maxAwaitTime(
                         2, TimeUnit.SECONDS
                     )
                     .cursor()) {

            while (running.get()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    // No event on this poll.
                    continue;
                }

                process(event);
            }
        }
    }

    private void process(
            ChangeStreamDocument<Document> event
    ) {
        // Business handler.
    }
}
```

### 10.1. `null` Does Not Mean “Stream Ended Permanently”

`tryNext()` returns `null` when a batch temporarily has no events. Never treat that as `COMPLETED`.

### 10.2. `maxAwaitTime` Is Not an Overall Job Timeout

It governs server wait time during eligible await/getMore calls. The application still needs:

- Configured connection/operation timeouts.
- Deadlines for downstream calls.
- Shutdown signals.
- Retries with backoff.
- Consumer health checks.

### 10.3. Avoid Busy-Spinning

If `tryNext()` returns `null` too quickly due to configuration or faults, the loop can burn CPU. Use short backoffs or tune `maxAwaitTime` appropriately, while never turning polling into infinite retries after critical errors.

---

## 11. `ChangeStreamIterable` and Event-Filtering Pipelines

Example receiving only order mutations:

```javascript
[
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]
```

Java Sync Driver:

```java
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import org.bson.conversions.Bson;

import java.util.List;

List<Bson> pipeline = List.of(
    Aggregates.match(
        Filters.in(
            "operationType",
            "insert",
            "update",
            "replace",
            "delete"
        )
    )
);

try (var cursor =
         orders.watch(pipeline).cursor()) {
    while (cursor.hasNext()) {
        handle(cursor.next());
    }
}
```

### 11.1. Server-Side Filtering Reduces Traffic

If you only care about `status`, you can filter supported event fields using a valid pipeline, while carefully checking the behavior of `updateDescription` and `fullDocument`.

### 11.2. Never Arbitrarily Project Out Event `_id`

The event-level `_id` carries the **resume token**. A pipeline that alters or strips the token makes the stream unresumable or rejected by the server. Never run `$project: {_id: 0}` in a Change Stream just to shrink payload size.

### 11.3. The Pipeline Is Part of the Checkpoint Contract

If you change a filter from “inserts only” to “inserts + updates”, resuming from an old token will **not replay updates that were previously filtered out**. Store `pipelineVersion`, `consumerName`, scope, and options alongside the token; changing filter logic may require a rebootstrap.

---

## 12. Distinguishing `operationType` Values

| Type | Meaning | Typical handling |
| --- | --- | --- |
| `insert` | Document created | Create projection or emit corresponding event |
| `update` | Part of document modified | Use `updateDescription` or lookup per requirements |
| `replace` | Document replaced completely | Replace projection with new data |
| `delete` | Document deleted | Delete or mark tombstone in target |
| `drop` | Collection dropped | Stop, inspect namespace ownership |
| `rename` | Collection renamed | Handle mapping/scope |
| `invalidate` | Stream no longer valid for scope | Stop/resubscribe per policy |
| New event types | Depends on MongoDB release | Classify explicitly, never ignore silently |

Not every event type appears in every scope or version. Production consumers need an explicit policy for unsupported event types rather than a bare `default: return;`.

---

## 13. Handling `insert`

For insert events, `fullDocument` normally holds the inserted document.

```java
if (event.getOperationType()
        == OperationType.INSERT) {

    Document document = event.getFullDocument();

    if (document == null) {
        throw new IllegalStateException(
            "Missing insert fullDocument"
        );
    }

    indexOrder(document);
}
```

### 13.1. An Insert Is Not Necessarily a Unique “Business Order Created”

Migrations or data-repair scripts can also insert documents. If business rules require notifying on new orders, the handler must verify domain state/intent and idempotency, or consume business events from a transactional outbox.

### 13.2. Never Send Emails Directly Without a Retry Policy

If the consumer sends an email and crashes before checkpointing, the insert event can be re-read. Use an email idempotency key, delivery ledger, or outbox before deploying.

---

## 14. Handling `update`: Patch or Full Document?

An update:

```javascript
db.orders.updateOne(
  { _id: "O100" },
  { $set: { status: "PAID" } }
);
```

can produce an event:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O100" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

### 14.1. When to Use `updateDescription`

Appropriate when you genuinely want patch processing and understand nested paths, array modifications, removed fields, truncated arrays, and the event schema of your MongoDB version.

### 14.2. Never Process Patches with Non-Idempotent Increments

If a patch corresponds to “increment counter by 1” and the event replays, incrementing again corrupts the count.

### 14.3. When to Use `fullDocument`

If the consumer builds a current-state read model of the order, you can fetch the full document with the right option and `replaceOne` by ID. Still guard against races and ordering issues discussed later.

---

## 15. `fullDocument: UPDATE_LOOKUP` Is Not an Exact Historical After-Image

Java:

```java
orders.watch()
    .fullDocument(FullDocument.UPDATE_LOOKUP)
    .cursor();
```

The server looks up the **current state** of the document when processing the update, rather than returning an immutable after-image captured at the exact moment the event occurred.

Example:

```text
T1: order.status = NEW
T2: update status = PAID
T3: update status = REFUNDED
T4: consumer processes event at T2
```

The `fullDocument` for the T2 event with `UPDATE_LOOKUP` can contain `REFUNDED` if the lookup runs after T3.

### 15.1. `fullDocument` Can Be Null

If the document was deleted before the lookup ran, the field may be absent. Never interpret `null` as a `delete` event; inspect `operationType` and business policies.

### 15.2. Distinguishing State Replication from Event Sourcing

- **State replication:** target only needs to converge to the latest state. Current lookup can help if ordering is protected.
- **Event sourcing/business audit:** needs exact transitions recorded per event. `UPDATE_LOOKUP` may not satisfy this; use domain events/outbox or pre/post-images as required.

---

## 16. Pre-Images and Post-Images

Supported MongoDB versions offer **Change Stream pre- and post-images** when enabled on the collection.

Concept:

- **Pre-image:** document before modification.
- **Post-image:** document after modification.
- Consumers can request images when they exist.
- Availability depends on MongoDB Server version, collection settings, and image retention.
- Never assume every event includes images.
- When configuration requires an image that is unavailable, the stream can error per API semantics.

### 16.1. Benefits

- Comparing old vs. new state.
- Detecting transitions from `PENDING` to `PAID`.
- Building projections with clearer semantics than `UPDATE_LOOKUP`.
- Auditing certain changes when retention suffices.

### 16.2. Costs and Limitations

- Additional storage and write amplification.
- Image retention and oplog dependencies.
- Configuration management overhead.
- Document size and event-size limits.
- Some event types may not provide images.

### 16.3. Not a Replacement for Permanent Audit Logs

Pre/post-images have bounded retention; never use them as a multi-year audit store without a separate export and retention architecture.

---

## 17. Handling `delete`

Delete events normally do not include the deleted document as `fullDocument`.

```java
if (event.getOperationType()
        == OperationType.DELETE) {

    BsonDocument key = event.getDocumentKey();

    if (key == null) {
        throw new IllegalStateException(
            "DELETE without documentKey"
        );
    }

    target.deleteOne(key);
}
```

This example only works if `documentKey` is a valid filter for the target with identical key mapping. In sharded collections, `documentKey` may include shard key fields; if the target schema differs, transform it.

### 17.1. Never Ignore Deletes

A consumer that only upserts inserts and updates leaves stale records behind after the source deletes them.

### 17.2. Tombstones Prevent Old Events from Resurrecting Documents

If handlers run concurrently and receive:

```text
E40: update order status=PAID
E41: delete order
```

and E41 is applied before E40, a stale update can recreate the order in the target.

You can store a tombstone:

```javascript
{
  _id: "O100",
  appliedVersion: NumberLong("41"),
  deleted: true
}
```

and only accept events with a newer version. Retain tombstones long enough to block late replays; versions must come from a reliable protocol, not ObjectIds or client timestamps as a total order.

---

## 18. `drop`, `rename`, and `invalidate`

A Change Stream can **invalidate** when a collection or database changes in a way that invalidates the open stream.

### 18.1. Never Treat `invalidate` as a Routine Data Change

If `orders` is dropped and recreated, an old consumer may be watching a namespace or collection identity that no longer applies. Continuing requires deciding:

- Is the recreated collection the same business entity?
- Does the read model need a rebuild?
- Could events have been lost during drop/recreate?
- Is a new namespace needed?
- Do the pipeline and permissions still apply?

### 18.2. `resumeAfter` vs. `startAfter`

After `invalidate`, `resumeAfter` cannot be used to resume in the usual way. `startAfter` has semantics designed to reopen a stream after an invalidate token when supported by the server.

`startAfter` does **not** automatically guarantee the new data matches the old collection or that the consumer needs no bootstrap.

### 18.3. DDL Needs a Runbook

A production consumer needs explicit policies for:

- Collection drop/rename.
- Resharding/configuration changes.
- Schema/index changes.
- Stream pipeline versions.
- Database/tenant scope shifts.
- Namespace drop and recreate.

Never silently catch unexpected events and keep advancing the checkpoint.

---

# PART II — DUPLICATE HANDLING AND IDEMPOTENCY

## 19. Why Can a Consumer Receive the Same Event Twice?

Consider event E100:

```text
Read E100 from Change Stream
           |
           v
Apply to target successfully
           |
           v
Process crashes BEFORE checkpoint E100
           |
           v
Restart from token E99
           |
           v
E100 is delivered again
```

This is expected behavior under **at-least-once processing**.

Other causes:

- Lost network responses.
- Primary elections forcing cursor reopens.
- Driver or application retries.
- Worker lease expiring while the old worker is still alive.
- Multiple consumer instances running concurrently.
- Checkpoint store write failures.
- Intentional event replays for rebuilds.
- Target write succeeds while acknowledgment times out.

**Never try to deduplicate using an in-memory `lastEventId` variable**, since restarts wipe RAM state and concurrency breaks it.

---

## 20. Three Easily Confused Concepts

| Concept | Meaning |
| --- | --- |
| At-most-once | May drop events; avoids some duplicates |
| At-least-once | Never skips events within retention replay bounds, yet may reprocess |
| Exactly-once business effect | Business side effect occurs once, requiring protocols, transactions, or idempotency |

Change Streams support resumption, yet **do not guarantee exactly-once external side effects**.

### 20.1. Exactly-Once Is Not a Checkbox

Guaranteeing “send only one email” requires idempotency at the email provider or a delivery ledger capable of handling ambiguity. Saving a resume token at the right moment still does not solve a lost response after the email was sent.

### 20.2. Choose Guarantees per Side Effect

- Building read models via idempotent replace: at-least-once is usually fine.
- Summing revenue via `$inc`: requires deduplication, versioning, or an increment event protocol.
- Disbursing money/payments: requires business idempotency keys and reconciliation.
- Sending notifications: depends on “may deliver duplicate” vs. “at-most-once per user” policy.

---

## 21. What Is an Idempotent Operation?

A function `f` is idempotent when:

```text
f(f(x)) = f(x)
```

Example replacing with the same document:

```java
target.replaceOne(
    Filters.eq("_id", orderId),
    transformedOrder,
    new ReplaceOptions().upsert(true)
);
```

Reapplying the same *state* preserves the result if the transformation is deterministic and older events cannot overwrite newer state.

Non-idempotent:

```java
target.updateOne(
    Filters.eq("_id", orderId),
    Updates.inc("notificationsSent", 1)
);
```

Applying the event twice increments the counter twice.

### 21.1. Idempotency Does Not Guarantee Correct Ordering

If a newer `REFUNDED` state is applied and then an older `PAID` event replays, `replaceOne` can still leave the wrong final state.

### 21.2. Transformations Must Be Deterministic

When replaying the same event, never:

- Generate a random `_id`.
- Set `updatedAt = now()` if it affects business logic.
- Compute amounts using floating-point doubles or changing rules.
- Call external APIs without an idempotency key.

`lastAttemptAt` metadata is acceptable as long as it is decoupled from the desired business state.

---

## 22. Choosing an Idempotency Key

Common options:

1. **Event identity:** the BSON resume token preserved intact, paired with stream/consumer identity.
2. **Business operation ID:** e.g., `paymentAttemptId`, `orderEventId`.
3. **Document ID + monotonic version:** suitable for per-aggregate state projections.
4. **Outbox event ID:** immutable ID generated by the app and committed with the business write.

### 22.1. Never Use Only `documentKey._id`

A single order can emit 100 events. Deduplicating by order ID processes the first event and treats all subsequent updates as duplicates.

### 22.2. Tokens and Scope

A token belongs to a specific change stream history and scope. When storing it in a processed-events collection, namespace the key by:

```text
consumerName
streamScope
streamGeneration / pipelineVersion
event resume token
```

Avoid accidentally sharing idempotency keys across two consumers with different side effects.

### 22.3. Business Keys Are Usually Better for External Side Effects

If the event database is replayed or a consumer rebootstraps and gets a new token for the same business event, a stable `notificationId`/`paymentId` is more reliable than a resume token.

---

## 23. Inbox/Receipt Collection for Once-Only Processing in MongoDB

A consumer updating a projection in **the same MongoDB deployment** can use a `processedChangeEvents` collection as an inbox.

Example document:

```javascript
{
  _id: {
    consumer: "orders-read-model-v1",
    eventKey: "stable-encoded-token-or-event-id"
  },
  processedAt: ISODate("2026-11-14T10:00:00Z"),
  operationType: "update",
  documentId: "O100"
}
```

Create a unique constraint:

```javascript
db.processedChangeEvents.createIndex(
  { "consumer": 1, "eventKey": 1 },
  { unique: true }
);
```

In this schema, pick **one consistent key structure** (e.g., composite `_id` or compound fields). If `_id` already uniquely embeds consumer+event identity, the extra index may be unnecessary.

### 23.1. Check-Then-Write Is Unsafe Under Concurrency

Wrong:

```text
if inbox record absent:
    send notification
    insert inbox record
```

Two workers can both observe absence and send together.

### 23.2. A Unique Receipt Only Works When Coupled Properly to the Effect

If you write the receipt before calling an external API, crashing between them **loses the effect** because replays skip the event.

If you call the external API before writing the receipt, crashing between them **duplicates the effect**.

This is a cross-system atomicity problem; solve it with provider idempotency keys, outbox/delivery workflows, or reconciliation—not merely a unique index.

---

## 24. Atomic Inbox and Projection in the Same MongoDB Deployment

If the processed receipt and read model reside in **the same MongoDB replica set/sharded deployment** supporting multi-document transactions, both writes can share one transaction.

Pseudocode:

```text
BEGIN TRANSACTION
    insert receipt(eventId) with unique constraint
    upsert projection(orderId, newState)
COMMIT

On duplicate receipt:
    event already processed; do not reapply

After commit:
    checkpoint resume token
```

### 24.1. Why Is This Useful?

If the transaction commits but checkpointing fails, the event replays. Upon replay, the duplicate receipt prevents reapplying the projection.

If the transaction aborts, both receipt and projection roll back together within the transaction boundary.

### 24.2. Not Cross-Cluster Atomicity

If a consumer reads from source MongoDB A and writes projections to MongoDB B, a transaction on B covers **receipts and projections on B**, not reading the Change Stream from A.

That is usually fine: checkpointing after target commit plus idempotent replay still yields a recoverable workflow.

### 24.3. Never Call External APIs Inside Transaction Callbacks

APIs like `withTransaction()` can retry callbacks. External side effects would be invoked repeatedly. Place only transaction-scoped, safely retriable DB operations inside the callback.

---

## 25. Java Illustration of Receipt + Projection Transaction

The snippet below demonstrates transaction boundaries. `eventId` must come from a stable event identity per consumer protocol; `order` is the transformed state.

```java
import com.mongodb.MongoException;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;

public final class ProjectionWriter {

    private final MongoClient targetClient;
    private final MongoCollection<Document> receipts;
    private final MongoCollection<Document> projections;

    public ProjectionWriter(
            MongoClient targetClient,
            MongoCollection<Document> receipts,
            MongoCollection<Document> projections
    ) {
        this.targetClient = targetClient;
        this.receipts = receipts;
        this.projections = projections;
    }

    public void applyOnce(
            String consumerId,
            String eventId,
            Document order
    ) {
        String receiptId = consumerId + ":" + eventId;

        try (ClientSession session =
                 targetClient.startSession()) {

            try {
                session.withTransaction(() -> {
                    receipts.insertOne(
                        session,
                        new Document("_id", receiptId)
                    );

                    projections.replaceOne(
                        session,
                        Filters.eq("_id", order.get("_id")),
                        order,
                        new ReplaceOptions().upsert(true)
                    );

                    return null;
                });
            } catch (MongoException error) {
                if (error.getCode() == 11000) {
                    // Treat as an already-processed duplicate only if
                    // receiptId matches the consumer/event contract.
                    return;
                }
                throw error;
            }
        }
    }
}
```

### 25.1. Additional Prerequisites for This Example

- Ensure `receipts` has unique `_id`.
- `eventId` must be stable, never a fresh UUID per retry.
- If replace could overwrite newer state, add version/ordering guards.
- Handle `withTransaction` retries and commit uncertainty per driver docs.
- Error 11000 could come from **another index**, not the receipt; production code must identify the actual violated index/key and never swallow projection unique conflicts as “already processed”.
- Verify `targetClient`, `receipts`, and `projections` live in **the same transaction-capable deployment**.
- Transactions do not cover external email/payment calls.

**Important:** this illustrates the mechanism, not a complete implementation for every driver version and topology.

---

## 26. Side Effects Outside MongoDB: Notifications, Emails, Payments

Example:

```text
Change event E100
    |
    v
Call email provider
    |
    v
Provider sends email
    |
    v
Response lost / consumer crash
    |
    v
Consumer reprocesses E100
    |
    v
Email may be sent again
```

No MongoDB checkpoint alone can turn an external API lacking idempotency into exactly-once execution.

### 26.1. Viable Strategies

- Pass an **idempotency key** to the downstream provider.
- Create a notification record with a unique business key.
- Write intent to an **outbox/delivery queue** and have workers dispatch per policy.
- Persist delivery states, attempts, and correlation IDs.
- Track unknown outcomes and run reconciliation.
- Accept duplicate delivery if business rules allow (e.g., low-severity alerts).

### 26.2. Payments Are a Special Case

Never use a raw Change Stream event ID as a payment idempotency key if one transaction can emit multiple DB events. Use a pre-generated and managed business `paymentAttemptId`.

### 26.3. “Deliver Exactly Once” Is Usually an End-to-End Protocol

Source, consumer, queue, provider, and business state must all cooperate. When a provider offers no queryable confirmation, unknown outcomes may require manual resolution.

---

## 27. Transactional Outbox When Stable Business Events Are Needed

Another pattern:

```text
Application transaction
      |
      +--> Write business order
      |
      +--> Insert outbox event
      |
      v
Commit
      |
      v
Change Stream watches OUTBOX
      |
      v
Delivery worker
      |
      v
Notification provider / Kafka
```

Outbox event:

```javascript
{
  _id: "evt-order-O100-paid-v4",
  aggregateId: "O100",
  type: "OrderPaid",
  version: NumberLong("4"),
  payload: {
    orderId: "O100",
    customerId: "C7",
    amountMinor: NumberLong("199000")
  },
  createdAt: ISODate("2026-11-14T10:00:00Z"),
  deliveryState: "PENDING"
}
```

### 27.1. Why Is This Better Than Watching Every Update?

- Events carry **business intent**, independent of document diffs.
- Has a stable ID and version.
- Lets you emit only changes worth notifying.
- When business write and outbox insert share a transaction, intent is never lost between them.
- Can retain/replay longer than the oplog if the outbox is retained long enough.

### 27.2. Duplicate Delivery Still Happens

A worker can send and crash before marking delivered. Provider idempotency and retry/reconciliation remain required.

### 27.3. Watching Outbox Instead of Polling?

Both can coexist:

- Change Stream to wake the worker promptly.
- Durable outbox polling to sweep pending events if Change Stream history is lost.

Some architectures treat the Change Stream as **notification of work**, while the outbox collection remains the durable work queue.

---

# PART III — RESUME TOKENS AND CHECKPOINTS

## 28. What Should a Resume Token Store?

A resume token is an opaque `BsonDocument`, not an application-defined sequence number.

Store alongside metadata:

```javascript
{
  _id: "orders-projection-v1",
  streamScope: "sales.orders",
  pipelineVersion: 1,
  checkpointType: "resumeAfter",
  resumeToken: {
    _data: "opaque-bson-value"
  },
  updatedAt: ISODate("2026-11-14T10:00:00Z"),
  workerGeneration: NumberLong("12")
}
```

This is an illustrative schema. Storing in `MongoCollection<BsonDocument>` preserves the BSON token naturally without string conversion risks.

### 28.1. Never Store a Bare Token Without Scope

A token belongs to a stream and pipeline. If a new version deploys with a different event filter, you must know whether the old token remains compatible.

### 28.2. Avoid Converting Tokens into Timestamps

Never replace:

```javascript
resumeToken: event._id
```

with:

```javascript
lastSeenAt: event.clusterTime
```

expecting equivalent behavior. `clusterTime` does not uniquely identify an event and can collide across multiple changes.

### 28.3. Tokens Can Come from Empty Batches

The Java cursor can expose the latest resume token/high-watermark even when no new user events arrived, depending on server/driver support. Handle carefully when events are still in-flight.

---

## 29. Checkpoint After Side Effects, Not After Reading

Right:

```text
Read event E101
    |
    v
Validate event
    |
    v
Apply side effect idempotently
    |
    v
Receive/verify acknowledgment
    |
    v
Persist resume token of E101
    |
    v
Read event E102
```

Wrong:

```text
Read event E101
    |
    v
Persist token E101
    |
    v
Apply side effect -> FAILURE
    |
    v
Restart from AFTER E101
    |
    v
E101 skipped
```

### 29.1. At-Least-Once and Checkpoints

Checkpointing after applying means a crash between them causes duplicate replay; that is why idempotency is mandatory. This is a deliberate trade-off to avoid losing events.

### 29.2. When to Batch Checkpoints?

If you process 100 events sequentially and only save the checkpoint at event 100, a crash replays all 100. Ensure:

- All effects are idempotent.
- Batch size is reasonable.
- Progress/lag is monitored.
- Checkpoints never advance past unacknowledged events.
- Replay volume fits your SLO.

### 29.3. With Parallel Processing

Never save the **highest completed token** if earlier events are still pending. Only checkpoint up to the **contiguous prefix** processed/acknowledged in stream order, or per an explicit per-partition protocol.

---

## 30. Persisting Raw BSON Resume Tokens in Java

Example using `MongoCollection<BsonDocument>`:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.BsonDocument;
import org.bson.BsonString;

public final class ResumeTokenStore {

    private final MongoCollection<BsonDocument> checkpoints;
    private final BsonString consumerId;

    public ResumeTokenStore(
            MongoCollection<BsonDocument> checkpoints,
            String consumerId
    ) {
        this.checkpoints = checkpoints;
        this.consumerId = new BsonString(consumerId);
    }

    public BsonDocument load() {
        BsonDocument record = checkpoints.find(
            Filters.eq("_id", consumerId)
        ).first();

        return record == null
            ? null
            : record.getDocument("resumeToken");
    }

    public void save(BsonDocument token) {
        if (token == null) {
            return;
        }

        BsonDocument record = new BsonDocument(
            "_id", consumerId
        ).append(
            "resumeToken", token
        );

        checkpoints.replaceOne(
            Filters.eq("_id", consumerId),
            record,
            new ReplaceOptions().upsert(true)
        );
    }
}
```

### 30.1. Durable Acknowledgment Required

The checkpoint store needs appropriate durability policies. If checkpoints are saved with weak write concern and rolled back after failover, the consumer may replay extra events. Idempotency covers this case.

### 30.2. One Consumer ID per Logical Stream

Never let two different pipelines overwrite the same checkpoint document. Include consumer name and stream version in the ID.

### 30.3. Never Use an In-Memory Cache as the Checkpoint Store

State must survive process restarts. A MongoDB collection works, alongside appropriate backup/retention and lease policies.

### 30.4. When Checkpoints Live in the Same Target as Effects

You can transactionally save the checkpoint and apply the projection in a single transaction, provided you design ordering, duplicate handling, and transaction error semantics. When external effects span another deployment, no native cross-system atomicity exists.

---

## 31. Restarting Consumers with `resumeAfter`

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.BsonDocument;
import org.bson.Document;

import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public final class ResumableConsumer {

    private final ResumeTokenStore checkpointStore;
    private final AtomicBoolean running =
        new AtomicBoolean(true);

    public ResumableConsumer(
            ResumeTokenStore checkpointStore
    ) {
        this.checkpointStore = checkpointStore;
    }

    public void stop() {
        running.set(false);
    }

    public void run(
            MongoCollection<Document> orders
    ) {
        BsonDocument saved = checkpointStore.load();

        ChangeStreamIterable<Document> stream =
            orders.watch()
                .fullDocument(FullDocument.UPDATE_LOOKUP)
                .maxAwaitTime(2, TimeUnit.SECONDS);

        if (saved != null) {
            stream = stream.resumeAfter(saved);
        }

        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 stream.cursor()) {

            while (running.get()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    continue;
                }

                // Must be idempotent!
                processEvent(event);

                // Save AFTER successful processing.
                checkpointStore.save(
                    event.getResumeToken()
                );
            }
        }
    }

    private void processEvent(
            ChangeStreamDocument<Document> event
    ) {
        // Business-specific idempotent handler.
    }
}
```

### 31.1. Limitations of This Example

- Does not handle error labels and retries.
- Lacks worker leases/fencing.
- Lacks missing event-type/invalidation handling.
- Lacks snapshot bootstrapping.
- `processEvent` is a placeholder.
- Lacks monitoring/checkpoint metadata.
- `checkpointStore.save(...)` is not atomic with external effects.

This is a **skeleton demonstrating the right operation order**, not a complete production consumer.

### 31.2. When No Token Exists

`watch()` by default starts from a current position per stream semantics; **it does not replay all pre-existing documents**. Bootstrap historical data as required before letting the consumer serve traffic.

---

## 32. `resumeAfter`, `startAfter`, and `startAtOperationTime`

| Option | When to use | Notes |
| --- | --- | --- |
| `resumeAfter(token)` | Normal consumer restart after a valid checkpoint | Cannot resume past `invalidate` in the usual way |
| `startAfter(token)` | Reopening a stream after an `invalidate` event when supported | Does not rebuild the collection/read model |
| `startAtOperationTime(timestamp)` | Starting at a BSON logical time with available history, usually when no token exists | Less specific than a resume token; requires clear scope/time understanding |

### 32.1. Pick Only One Starting Point

Never configure multiple starting options simultaneously on the same Change Stream.

### 32.2. `startAtOperationTime` Is a BSON Timestamp

It is not a Java `Date` or a client-guessed epoch millisecond value.

```java
import org.bson.BsonTimestamp;

BsonTimestamp time =
    new BsonTimestamp(secondsSinceEpoch, increment);

orders.watch()
    .startAtOperationTime(time);
```

Obtain the timestamp from an authoritative source/operation and verify history still exists; never fabricate `increment` and treat it as an exact event position.

### 32.3. Token from `invalidate`

If a consumer handles an `invalidate` event and holds its token, `startAfter` can open a new stream per MongoDB semantics. However, if the namespace was deleted, the business projection may still require a rebuild.

---

## 33. Post-Batch Resume Tokens and High-Watermarks

When the server returns an empty batch, the response can carry a `postBatchResumeToken`, indicating the stream position has advanced even without user events.

Java `MongoChangeStreamCursor` exposes:

```java
BsonDocument token = cursor.getResumeToken();
```

This token may reflect the latest event or a server-provided resume point managed by the driver.

### 33.1. Why Is This Useful?

If a collection receives few writes, the consumer should not leave its checkpoint stale solely due to quiet periods. High-watermarks allow resuming from a fresher position when no work is outstanding.

### 33.2. Never Checkpoint Past Unfinished Events

```text
E100 read, handler still running
E101 read, handler still running
postBatch token = T105
```

Saving T105 while E100/E101 remain unacknowledged can skip them upon restart.

### 33.3. Safety Rules

Only update a high-watermark token when:

- All events preceding the token have been processed/acknowledged per protocol.
- No older in-flight work remains.
- Consumer ownership/lease is valid.
- The token came from the exact stream and pipeline currently active.

In a **single-threaded synchronous** consumer that finishes processing every event before polling again, persisting high-watermarks on empty batches is viable once those conditions hold.

### 33.4. Persisting PBRT Is Not Mandatory for Correctness

You can choose to checkpoint only event tokens after processing completes. That is simpler, though tokens age during quiet periods. Choose based on history/idle SLOs.

---

## 34. Does the Driver Auto-Resume?

Modern Java Drivers include **automatic resume for certain resumable errors** in Change Streams, governed by server/driver error labels and API conditions.

However, never assume:

- Every error is resumable.
- The driver will retry forever.
- Expired history can still be recovered.
- Unacknowledged side-effect callbacks will execute once.
- `invalidate` events reopen the collection with identical business semantics.
- Application checkpoints are unnecessary.

### 34.1. Separation of Responsibilities

**Driver:**

- Manages connections and topology.
- Fetches batches.
- May auto-resume per contract and current token in eligible cases.

**Application:**

- Persists durable checkpoints.
- Enforces idempotency.
- Defines startup/restart policies.
- Handles business errors.
- Handles long outages.
- Orchestrates rebootstrap/reconciliation.
- Enforces worker ownership.

### 34.2. After a Process Crash

In-memory driver state is lost. The application must read the checkpoint store and open a new stream using the proper starting option.

---

## 35. Oplog History Window and Losing the Resume Point

Change Streams depend on sufficiently long history. If a consumer stops for hours or days while writes continue:

```text
00:00 consumer saves token T100
01:00 consumer crashes
...
20:00 oplog overwrites old history
21:00 consumer restarts from T100
       -> history no longer available
```

When a token can no longer be resumed, never silently start a fresh stream at “now” and mark the consumer `HEALTHY`. Doing so drops all changes from the outage window.

### 35.1. What to Monitor

- Current oplog window of the source/sync topology.
- Consumer lag and checkpoint age.
- Write rate spikes during peak hours.
- Maximum offline/restart duration.
- Downstream backlog.
- Per-event processing latency.
- Initial sync, resharding, or maintenance affecting history.

### 35.2. When a Token Is Too Old

You may need to:

1. Stop the consumer and report degraded status.
2. Protect the current target from receiving inconsistent updates.
3. Assess the source of truth and data-loss window.
4. Rebootstrap all or affected partitions.
5. Establish a valid new stream starting point.
6. Reconcile data and side effects.
7. Restore `HEALTHY` status only after verifying data and offsets.

### 35.3. Growing the Oplog After History Loss Does Not Recover Past Entries

Expanding retention helps future outages; it never recreates entries already truncated.

---

# PART IV — FAILURE RECOVERY

## 36. Classifying Consumer Errors

| Error class | Example | Response |
| --- | --- | --- |
| Transient network | Connection reset, temporary timeout | Backoff and reopen from checkpoint |
| Primary election | Stepdown, topology change | Wait for healthy cluster, resume per policy |
| Server selection | No suitable node found | Alert outage, bounded retry |
| History lost | Resume token missing from oplog | **Never skip**; rebootstrap/reconcile |
| Invalidate/DDL | Drop, rename | Scope-specific handling; usually needs business decision |
| Authentication/authorization | Permission revoked | Stop and fix permissions, do not retry infinitely |
| Payload/schema | Unknown event type/field | Quarantine/poison event policy |
| Downstream unavailable | Search/email/Kafka down | Durable retry, do not advance checkpoint |
| Duplicate event | Replay after crash | Idempotent no-op or read/confirm state |
| Checkpoint store failure | Event applied yet token unsaved | Controlled replay |
| Worker lease lost | Worker no longer owner | Stop applying and checkpointing |
| Process shutdown | SIGTERM/deploy | Stop fetching, drain, checkpoint, close |

### 36.1. Never Catch Every Exception and `continue`

Wrong:

```java
try {
    handle(event);
} catch (Exception ignored) {
    // Continue and checkpoint next event.
}
```

A failing event gets skipped permanently if the checkpoint keeps advancing.

### 36.2. Error Policies Must Be Explicit

For poison events:

- Halt the stream until data or code is fixed.
- Quarantine the event into a durable DLQ and advance the checkpoint **only if business rules allow skipping** with replay and alerting in place.
- Route to a manual workflow.
- Split event streams by partition when needed to narrow blast radius.

Never claim “zero lost events” while unresolved records sit in a DLQ.

---

## 37. Retries with Backoff and Jitter

A consumer should not hammer stream reopen every millisecond during a source outage.

Example policy:

```text
retry 1: 200 ms + jitter
retry 2: 500 ms + jitter
retry 3: 1 s + jitter
retry 4: 2 s + jitter
...
cap: 30 s
```

### 37.1. Need Deadlines and Failure Budgets

Background services can retry for a long time, yet health checks must report `DEGRADED` when making no progress and `FAILED/REBOOTSTRAP_REQUIRED` on unrecoverable errors.

### 37.2. Never Tight-Loop Retry Poison Data

If event transformation always throws due to an unsupported schema version, network retries will not help. Alert and require handler fixes or policy-driven quarantine.

### 37.3. Jitter Prevents Thundering Herds

If 200 consumers restart together after an outage, deterministic retry delays cause all of them to reconnect and run `getMore` simultaneously.

---

## 38. Recovering from Brief Disconnects

Runbook:

1. Log the exception and the last durably saved token.
2. Close the current cursor.
3. Inspect network/topology or wait per backoff.
4. Reload the token from the checkpoint store.
5. Open a new Change Stream with `resumeAfter`.
6. Rely on idempotency for events possibly applied before the crash.
7. Monitor lag until it returns within threshold.

### 38.1. Never Resume from an In-Memory Latest Token

If event E200 was read yet not applied, `cursor.getResumeToken()` may have already moved past E200. Always resume from the **durable acknowledged checkpoint**, not the last in-RAM read position.

### 38.2. Crashing Mid-Processing

At-least-once replay can deliver that same event to a new consumer. This scenario must be tested.

---

## 39. Recovering from Checkpoint Failures

```text
Event E200
    |
    v
Projection update success
    |
    v
Checkpoint save fails
    |
    v
Process restart
    |
    v
Replay E200
```

If the projection is updated via deterministic replace with versioning/ordering guards, replay can be safe.

If processing uses `$inc`, `sendEmail()`, or `chargeCard()`, replay can trigger duplicate side effects.

### 39.1. Compensating Mechanisms

- Receipt/processed-events store.
- Stable business idempotency keys.
- Atomic projection+receipt transactions when in the same deployment.
- Provider-level idempotency.
- Reconciliation to resolve unknown outcomes.

### 39.2. Checkpoint Store `writeConcern`

If a token is saved with `w:1` and rolled back on failover, the consumer can re-read events. Data stays safe if handlers are idempotent; if SLAs require durable progress, consider majority write concern.

---

## 40. Recovering from `invalidate`

A stream on a dropped or renamed collection can terminate with `invalidate`.

Never apply:

```text
catch invalidate -> resumeAfter(invalidateToken) -> success
```

as a general rule.

### 40.1. Differences Across Scopes

- Collection-level streams are tightly bound to collection identity.
- Database/deployment-level streams behave differently on drops/renames.
- Certain event types/DDL do not invalidate identically across all scopes.

### 40.2. Choosing a Recovery Policy

1. Stop and report `NAMESPACE_CHANGED`.
2. Confirm whether the new collection serves the same business purpose.
3. If needed, use `startAfter` on the invalidate token per supported semantics.
4. Rebuild the projection when old data is no longer compatible.
5. Update stream generation/schema version.
6. Verify backlogs and reconciliation before serving traffic.

### 40.3. Do Not Assume Recreating a Collection Continues the Same History

Dropping and recreating can produce a new collection with the same name yet completely different lifecycle, indexes, and data. Consumers must distinguish intentional migrations from unexpected operations.

---

## 41. Recovering from Oplog History Loss

When a token is too old:

```text
Resume attempt with token T
        |
        v
History unavailable
        |
        v
STOP + mark REBOOTSTRAP_REQUIRED
        |
        v
Rebuild baseline from source of truth
        |
        v
Establish safe new change capture boundary
        |
        v
Apply catch-up events
        |
        v
Verify and resume service
```

### 41.1. Simply Deleting the Token Is Not a Fix

Deleting the token and starting from “now” can silently skip millions of updates made during the disconnect window.

### 41.2. Some Side Effects Cannot Be Replayed from Current State Alone

If an email must go out for **every** historical state transition, a current snapshot does not show all intermediate transitions. That is why a durable domain outbox/event log can be far more important than relying solely on Change Streams.

### 41.3. Recovery Plans by Purpose

- **Read models/search indexes:** can rebuild from current data, then catch up.
- **Cache invalidation:** can invalidate/rebuild caches.
- **Transactional notifications:** may need an outbox/delivery ledger to avoid missing business events.
- **Auditing:** requires immutable audit logs with appropriate retention, not just the oplog.

---

## 42. Bootstrapping Historical Data: Change Streams Do Not Auto-Backfill

If a collection already holds one million orders before a consumer deploys, calling `watch()` from now only receives changes after that point.

### 42.1. Objective

```text
Initial data:
  O1...O1,000,000

During bootstrap:
  O100 updated
  O500 deleted
  O1,000,001 inserted
```

The target must converge to the exact final state after copying and replaying.

### 42.2. Safer Conceptual Process

1. Establish a valid **CDC starting point**.
2. Capture and persist changes from that point into a durable stream/log while copying.
3. Backfill source documents by stable key.
4. Apply changes captured since the starting point in an order/method preventing stale overwrites.
5. Monitor catch-up lag.
6. Reconcile source and target at a consistent logical boundary.
7. Transition the consumer to normal operation.

### 42.3. Trap: Backfill Overwriting Newer Events

```text
T1 backfill reads O100 status=PENDING
T2 source updates O100 status=PAID
T3 CDC applies PAID to target
T4 backfill writes stale PENDING to target
```

That is why backfill and CDC application must never race without an ordering or versioning protocol.

### 42.4. Solutions

- Capture first, complete backfill, then replay all captured changes.
- Consistent snapshot + supported CDC starting point.
- Version-aware conditional writes.
- Purpose-built migration connectors ensuring bootstrap/catch-up ordering.
- Pausing writes if brief downtime is acceptable.

### 42.5. Oplog Window During Bootstrap

A multi-hour backfill paired with a short oplog window can drop events if changes are not read and persisted promptly. Expand retention, shrink batches, buffer durably, or use dedicated migration tooling.

---

## 43. Ensuring Ordering with Multiple Consumers

A Change Stream cursor preserves order per MongoDB semantics, yet fanning events into a worker pool introduces reordering:

```text
E1: O100 status=PAID
E2: O100 status=REFUNDED

Reader dispatches:
  E1 -> worker slow
  E2 -> worker fast

Target applies E2 then E1
```

Final state is wrong if E1 overwrites E2.

### 43.1. Simplest Approach

A single sequential consumer processes events and checkpoints after each event or batch ack. Fits moderate throughput well.

### 43.2. When Parallelism Is Needed

- Partition by stable aggregate ID.
- Guarantee per-key order.
- One worker per partition or ordered queues.
- Enforce monotonic versions/tombstones at the target.
- Track completed contiguous offsets; never checkpoint past pending work.
- Enforce backpressure and concurrency limits.

### 43.3. Never Share a `MongoCursor` Across Threads

`MongoCursor` is not thread-safe. One reader thread reads and dispatches payloads to workers; never have multiple threads call `next()` on the same cursor.

### 43.4. Sharded Clusters

Ordering, transaction events, and cluster-wide streams carry nuances. Never assume a single timestamp field provides a total order for arbitrary parallel processing.

---

## 44. Bounded Queues and Backpressure

A pipeline:

```text
Change Stream reader
        |
        v
Bounded queue capacity=1000
        |
    +---+---+---+
    |       |   |
   W1      W2  W3
    |       |   |
    +-------+---+
        |
        v
Downstream
```

### 44.1. When the Queue Fills

The reader must apply backpressure and stop pulling events. If the reader keeps reading into an unbounded queue, heap memory grows with event rate until OOM.

### 44.2. Backpressure Is Bounded by History

When a reader stalls too long without advancing its resume point, source writes continue and the oplog window keeps sliding. Mitigate by:

- Scaling downstream.
- Skipping unnecessary event processing.
- Partitioning/sharding properly.
- Using a durable message broker if long buffering is required.
- Alerting on consumer lag vs. oplog headroom.

### 44.3. In-Memory Queues Are Not Crash-Durable

Bounded queues provide memory safety, not **durability**. After a process crash, replaying from the durable checkpoint must recover unprocessed events.

---

## 45. Worker Ownership, Leases, and Fencing

If two instances deploy with the same consumer ID:

```text
Consumer A reads E100
Consumer B reads E100
Both send side effect
```

Sharing a checkpoint does not stop two workers from processing simultaneously.

### 45.1. Single Active Consumer

A simple design:

- Each logical stream has at most one active owner.
- Lease stored in a control collection.
- TTL or expiry policy on the lease.
- Active worker renews periodically.
- Upon losing the lease, the worker stops reading and checkpointing.

### 45.2. Fencing Generations

A **monotonic fencing token** rejects writes from a stale worker after the lease transfers to a new worker.

```text
A owns generation=11
A becomes paused
Lease expires
B owns generation=12
A wakes up and tries to write
Storage rejects generation=11
```

Relying solely on an in-RAM boolean still lets a paused old worker emit side effects.

### 45.3. Leases Do Not Replace Idempotency

Even with a single owner, crashing after applying an effect and before checkpointing causes replays. Both leases/fencing and idempotency are required.

---

## 46. Graceful Shutdown

Upon receiving SIGTERM/deploy/cancellation:

1. Stop accepting new work.
2. If the reader is blocked, close the cursor per contract to cancel it.
3. Wait for or cancel in-flight tasks within a deadline.
4. Checkpoint only the acknowledged prefix.
5. Save state/metrics and release the lease.
6. Close cursor/session/driver resources cleanly per ownership.
7. Exit process.

### 46.1. `close()` from a Cancellation Thread

The `MongoCursor` API permits `close()` concurrently with reading per contract, while all other methods are **not thread-safe**. Never call `next()` on the same cursor from two threads.

### 46.2. Never Mark Completed on Stop Signals

A long-lived Change Stream is not a finite batch job; `STOPPED`/`DRAINED` differs from `COMPLETED`.

### 46.3. Kubernetes `terminationGracePeriod`

When running under an orchestrator, the shutdown deadline must either suffice to finish/ack an in-flight event or stop cleanly and rely on idempotent replay after restart.

---

# PART V — DESIGNING NOTIFICATION FEATURES

## 47. Domain Events vs. Database Events

Suppose an order transitions:

```text
PENDING -> PAID -> FULFILLED -> REFUNDED
```

If you only watch `orders`, any update might come from:

- Business APIs.
- Migration scripts.
- Admin corrections.
- Background jobs.
- Transaction retries.
- Reconciliation.

A database change event reflects a storage mutation, not always business intent. If notifications should only fire when **payment is confirmed for the first time**, emit explicit domain events:

```javascript
{
  _id: "order-O100-paid-evt-4",
  type: "OrderPaid",
  orderId: "O100",
  version: 4,
  customerId: "C7",
  occurredAt: ISODate("2026-11-14T10:00:00Z")
}
```

### 47.1. When Watching `orders` Still Fits

- Syncing a search index to latest state.
- Cache invalidation.
- Updating read models.
- Eventually consistent analytics.
- Waking a pipeline to scan pending tasks.

### 47.2. When an Outbox Fits Better

- Payments and invoicing.
- Sending emails/SMS on business transitions.
- Integrations requiring immutable event payloads.
- Long-retention auditing.
- Full business history replay.

---

## 48. Notification Model with Idempotency Keys

Reference schema:

```javascript
{
  _id: "notification-O100-paid-C7",
  eventId: "order-O100-paid-evt-4",
  recipientId: "C7",
  channel: "EMAIL",
  template: "ORDER_PAID",
  status: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T10:00:00Z")
}
```

Enforce uniqueness on the notification ID or compound business fields.

### 48.1. Decouple Intent Creation from Delivery

The consumer processes the Change Stream or outbox event by **upserting a notification intent** under a stable key. A separate delivery worker dispatches emails and updates status.

```text
Change Stream event
       |
       v
Upsert notification intent
       |
       v
Checkpoint event token
       |
       v
Delivery worker sends with idempotency key
```

### 48.2. Benefits

- If the consumer replays the event, upserting with the same ID creates no second intent.
- If the email provider fails, the delivery worker retries from the database record.
- Per-notification metrics become available.
- Source CDC lag is decoupled from delivery backlogs.

### 48.3. Never Claim Zero Duplicate Sends Unconditionally

If a provider lacks idempotency and a response is lost, the delivery worker still faces an ambiguous outcome. Adopt a clear business policy (“do not resend on unknown” vs. “retry accepting duplicate risk”) alongside reconciliation.

---

## 49. Versioning and Deletes/Tombstones in Read Models

A projection:

```javascript
{
  _id: "O100",
  status: "PAID",
  appliedVersion: NumberLong("42"),
  deleted: false
}
```

When receiving version 43, the update should only apply if the target is not already at version 43 or newer.

### 49.1. Conditional Update

Logic example:

```javascript
db.orderReadModels.updateOne(
  {
    _id: "O100",
    appliedVersion: { $lt: NumberLong("43") }
  },
  {
    $set: {
      status: "REFUNDED",
      appliedVersion: NumberLong("43")
    }
  }
);
```

**Note:** if the record does not exist yet, handle safe insert/upsert separately. Running an upsert with a version filter on `_id` can trigger a duplicate key error when a newer version already exists on the target.

### 49.2. Never Use Client Clock Timestamps as a Total Order

`updatedAt` across two machines suffers clock skew. Versions must come from a source of truth enforcing monotonic rules.

### 49.3. Tombstones After Delete

If you physically delete immediately and a stale event arrives later, the projection can be resurrected. Retain a versioned tombstone or enforce strict per-key ordering before cleanup.

---

## 50. Read-After-Write and Eventual Consistency

When an API writes an order, the Change Stream consumer needs time to update the read model.

```text
T0: write order
T0+20 ms: API responds success
T0+100 ms: consumer processes event
T0+150 ms: projection becomes visible
```

### 50.1. Do Not Promise Synchronous Consistency

If a user opens a page immediately after POST and reads from the projection, the update may not be visible yet.

Options:

- API reads directly from the source for read-your-writes.
- Optimistic UI on the client.
- Wait for projection version within a bounded deadline.
- Session/causal consistency on the same deployment where semantics fit.
- Return `202 Accepted` for async workflows when business UX permits.

### 50.2. Consumer Lag Is Part of the SLA

A notification SLA of “within 5 seconds” demands monitoring and capacity planning. Change Streams alone do not guarantee a 5-second deadline.

---

# PART VI — MONITORING AND TESTING

## 51. Key Consumer Metrics

| Metric | Why it is needed |
| --- | --- |
| `consumer_up` / last successful poll | Detect dead workers |
| Last event processed time | Detect stuck streams |
| Last durable checkpoint time | Verify persisted progress |
| Resume attempts | Measure connection instability |
| Resume history lost count | Alert on mandatory rebootstrap |
| Event processing duration | Handler speed |
| Downstream ack latency | Bottleneck visibility |
| Events processed/sec | Throughput |
| Duplicate events skipped/sec | Understand replay behavior |
| Dead-letter count/age | Unresolved failures |
| In-flight events | Checkpoint/ordering safety |
| Queue depth | Backpressure |
| Source oplog window | Recovery headroom |
| Consumer lag | History-loss and notification-delay risk |
| Fencing/lease owner | Prevent duplicate active workers |
| Notifications delivered/unknown/failed | End-to-end business outcomes |

### 51.1. A Quiet Consumer Is Not Necessarily Hung

A collection may receive zero writes for hours. Distinguish:

- No new events.
- Cursor polling/heartbeats remain healthy.
- Consumer stalled due to network failure.

Use poll health, error states, and high-watermark tokens instead of `events/sec` alone.

### 51.2. ClusterTime-Based Lag Has Limits

`clusterTime` is not an absolute wall-clock SLA; idle workloads or clock skew affect it. Measure event-creation-to-processing latency and checkpoint age using appropriate timestamps.

---

## 52. SLO-Driven Alerting

Example policy:

```text
WARNING:
  consumer lag > 15s sustained for 5m
  or queue depth > 80% capacity

CRITICAL:
  no durable checkpoint progress during active source writes
  or resume history lost
  or DLQ contains unresolved high-severity events
  or consumer lease owner missing
```

These are examples; production payment/notification systems require thresholds grounded in business SLAs.

### 52.1. Oplog Window vs. Consumer Lag

If the oplog window is only 2 hours and consumer lag reaches 90 minutes, act early. Never wait until resumption fails.

### 52.2. Low Lag Does Not Prove Zero Data Loss

A worker could checkpoint and **skip poison events**. A dashboard showing ~0 lag can still have corrupted business state. Monitor DLQs, duplicates, and reconciliation.

---

## 53. Testing Requires a Real MongoDB Deployment

To test Change Streams, you need:

- A supported replica set or sharded cluster.
- Adequate permissions to open streams.
- The consumer started and ready before triggering test events.
- Isolated namespaces to avoid cross-test interference.
- Separate durable checkpoint stores/consumer IDs.
- Clean teardown of cursors and workers after tests.

An in-memory mocked `MongoCollection` cannot verify resumption, oplog history, `invalidate`, or real event delivery.

### 53.1. Using Testcontainers

The Testcontainers MongoDB module supports running MongoDB in tests; APIs/packages vary by release. Modern versions provide `MongoDBContainer` with `getReplicaSetUrl()`.

### 53.2. Readiness Barrier

Wrong:

```text
startConsumerAsync()
insertDocument()
assertReceived()
```

`startConsumerAsync()` can return before the stream cursor is actually initialized.

Better:

```text
start consumer
wait until cursor/subscription is READY
perform test insert with unique correlationId
await matching output event
close resources
```

### 53.3. Avoid `Thread.sleep(500)` Instead of Event Conditions

CI scheduling, networking, and server load vary. Use polling with deadlines, JUnit timeouts, and logs tagged with correlation IDs.

---

## 54. Testing Duplicates After a Crash Before Checkpointing

Fixture:

```text
Checkpoint = E99
Consumer reads E100
Apply target E100 successfully
Simulate crash BEFORE checkpoint save
Restart consumer at E99
Consumer receives E100 again
```

Assertions:

- Read model state stays accurate.
- No duplicate notification intent created.
- Business counters do not increment twice.
- Final checkpoint advances to E100.
- Duplicate/retry metrics increment if expected.

### 54.1. This Test Is Mandatory

If your architecture cannot survive this scenario, it lacks safe at-least-once recovery.

---

## 55. Testing Failures Right After Checkpointing

Fixture:

```text
Consumer processes E100
Save checkpoint E100
Process crashes
Restart from resumeAfter(E100)
```

Expectations:

- Reprocessing E100 is not required.
- E101 is still received while source history remains.
- E100's data/side effects completed before the checkpoint.
- No gap in source events.

### 55.1. Do Not Try Timing Sleeps Precisely

Use hooks/test doubles on the checkpoint store or inject faults right at the boundary instead of guessing when to kill the process.

---

## 56. Testing Expired History

In test environments, you can configure a tiny oplog window or simulate history-lost errors at an abstraction layer. Never shrink a production oplog just for testing.

Expectations:

- Consumer marks `REBOOTSTRAP_REQUIRED`.
- Never silently clears the token and resumes from “now”.
- Fires alerts.
- Follows a runbook to rebuild the read model or replay from a durable outbox.
- Never reports healthy before reconciliation completes.

### 56.1. Practical Lab Note

Oplog rollover depends on load, size, and server version; integration tests forcing oplog history loss via millions of writes can be slow and flaky. Combine unit fault injection on policies with controlled integration rehearsals.

---

## 57. Testing `invalidate` and Rename/Drop

Run on an isolated test collection:

1. Start the Change Stream.
2. Verify normal event delivery.
3. Drop/rename the namespace in the test environment.
4. Observe invalidate/DDL handling.
5. Verify the consumer transitions to the right state.
6. Test recovery with `startAfter` where server conditions support it.
7. Rebuild the read model from the new collection if required.

Never `drop()` a production collection to test a consumer.

---

## 58. Testing Event Ordering and Concurrency

Emit events:

```text
O100 version 1 -> NEW
O100 version 2 -> PAID
O100 version 3 -> REFUNDED
```

Intentionally delay the version 2 handler relative to version 3 inside a worker pool.

Expectations:

- Final projection holds version 3.
- Not overwritten by v2.
- Checkpoints never advance past v2 while v2 is unacknowledged.
- Shutdown/restart drops no events.
- Delete tombstones are not resurrected by stale updates.

### 58.1. Testing `UPDATE_LOOKUP` Races

Issue consecutive updates and delay processing to observe `fullDocument` semantics. Never assert `UPDATE_LOOKUP` always equals the exact state at the moment the update occurred.

### 58.2. Testing Multiple Events for the Same Business ID

Never use `documentKey._id` as the deduplication event key, as it drops valid subsequent updates.

---

## 59. Failure Test Matrix

| Case | Fault | Expected |
| --- | --- | --- |
| Network reset | Cursor loses connection | Resume from durable token |
| Primary election | Stream interrupted | Driver/app recovers per policy |
| Crash after apply | Effect succeeded, token unsaved | Replay with no harmful duplicate effect |
| Crash after token | Token saved after ack | Continue with subsequent events |
| Token too old | Oplog history lost | Stop + rebootstrap |
| Invalid token | Wrong/corrupt token | Stop, never skip |
| Collection drop | Invalidate | DDL recovery policy |
| Unknown event type | Unsupported by handler | Quarantine/block per business rules |
| Downstream 503 | Target unavailable | Backoff, never advance checkpoint |
| Provider response lost | Unknown external outcome | Idempotency/reconciliation |
| Two workers | Duplicate active owners | Lease/fencing + idempotency |
| Out-of-order apply | Older update finishes last | Versioning/per-key ordering |
| Queue full | Reader faster than sink | Backpressure, no OOM |
| Shutdown mid-event | Stopped while processing | Replay unacknowledged event |
| No events for hours | Quiet collection | Consumer stays healthy |
| Bootstrap race | Backfill writes stale state | CDC replay/versioning corrects |
| Restart with new pipeline | Filter changed | Contract/version/rebootstrap |
| Missing pre-image | Image not retained | Explicit policy, never silently skip |

---

## 60. Security and Access Control

A Change Stream consumer needs appropriate permissions on watched namespaces; in self-managed MongoDB, roles/privileges involve `find` and `changeStream` depending on scope. Atlas deployments also require matching roles.

Principles:

- Least privilege for source readers.
- Separate credentials for target writers.
- TLS and a secrets manager.
- Avoid logging raw resume tokens if logs risk exposing internal operational metadata.
- Never log `fullDocument` containing PII by default.
- Encrypt checkpoint stores and backups appropriately.
- Isolate consumers per tenant/authorization boundary when needed.
- Log correlation IDs, not raw personal data.
- Control retention for DLQs, processed-events stores, and outboxes.
- Protect manual replay/rebootstrap APIs from unauthorized invocation.

### 60.1. Resume Tokens Are Not Auth Tokens

Never turn resume tokens into public API pagination tokens or secret auth credentials. They only mark stream positions; database access still requires authorization.

### 60.2. Pre/Post-Images Retain Old Data

Pre-images can hold PII even after a document is updated or deleted. Data governance and retention must cover image stores, DLQs, and logs too.

---

## 61. Performance Tuning and Capacity

Factors:

- Source write/event rate.
- Event payload size.
- Filter pipeline selectivity.
- Consumer network/decoding CPU.
- Downstream throughput.
- Checkpoint write frequency.
- Batch size/`maxAwaitTime`.
- Worker concurrency and ordering.
- Queue depth and oplog retention.
- Pre/post-image overhead.

### 61.1. Never Open One Stream per User

If an application has one million users, opening one million Change Streams just to update dashboards can overwhelm connections, cursors, and server resources.

A more practical topology:

```text
A few shared consumers
       |
       v
Filter/route by tenant/user
       |
       v
Message broker / WebSocket gateway
       |
       v
End users
```

### 61.2. Multi-Tenant Routing

If events contain `tenantId`, ensure consumers and projections never leak data across tenants. For `delete` events, `fullDocument` may be absent, requiring tenant lookup/mapping via `documentKey` or another schema design.

### 61.3. Avoid Unnecessary Source Polling

Change Streams reduce continuous source polling, yet consumer health, checkpoints, and business delivery still need active monitoring.

---

## 62. Sharded Clusters: What to Understand

In sharded MongoDB:

- Watch at collection, database, or deployment scope as appropriate.
- Servers/`mongos` coordinate events across shards.
- Resume tokens and `documentKey` reflect server/sharding semantics.
- Ordering and event metadata across a cluster-wide stream can differ from a single replica set.
- Cross-shard transactions emit change events per commit semantics.
- Configure consumers with the proper MongoDB URI/topology; never tail a single shard directly expecting full-cluster changes.
- Resharding/DDL can affect streams and requires tested recovery.

### 62.1. Do Not Partition Arbitrarily by `clusterTime`

`clusterTime` does not replace resume tokens or global per-key ordering protocols. With multiple workers, define explicit ownership and versioning.

### 62.2. Database/Deployment-Wide Streams Carry Noise

Filter events by supported namespaces and event types; monitor open stream counts and privilege scopes.

---

## 63. Change Streams vs. Collection Polling

| Criterion | Change Stream | Polling on `updatedAt` |
| --- | --- | --- |
| Change detection | Near real-time via oplog | Periodic query intervals |
| Deletes | Emits delete events | Hard deletes hard to detect without tombstones |
| Continuous query load | Fewer repeated scans | Frequent queries and index pressure |
| Resumption | Resume tokens, history-dependent | App-managed markers/time windows |
| Bootstrap | Needs separate snapshot/backfill | Also needs initial state |
| Data type | Database changes | Current document state |
| Reliability | Idempotency/checkpoints/recovery | Idempotency/checkpoints/recovery |
| Topology | Supported replica set/sharded | Works even on standalone |
| Long outages | History loss risk | Can rescan current state, yet misses transitions |
| Business intent | Not inherently included | Not inherently included |

### 63.1. When Polling Still Fits

- Small datasets where low latency is unimportant.
- Only final state matters, not every intermediate transition.
- Indexed immutable/versioned markers exist.
- Deletes are unneeded or tombstones exist.
- Production topology does not support Change Streams.
- Periodic reconciliation alongside a stream.

### 63.2. Never Skip Reconciliation When Using Streams

A periodic repair scan catches drift from bugs, poison events, or bad transforms that lag metrics miss.

---

## 64. Change Streams vs. Transactional Outbox

| Criterion | Watching business collection | Watching outbox collection |
| --- | --- | --- |
| Event source | All observed DB mutations | Intentionally recorded business events |
| Payload | Update diffs/`fullDocument` lookup | Versioned immutable payload |
| History window | Oplog retention | App-designed outbox retention |
| Domain semantics | Inferred from document diffs | Explicit by event type |
| Backfill | Must build separately | Can replay retained outbox |
| Exactly-once notifications | Not automatic | Still needs idempotency |
| Migration scripts | Can accidentally trigger events | Skips domain events if outbox untouched |
| Cost | Minimal source write changes | Extra outbox collection/transactions |
| Best fit | Caches, projections, search sync | External integrations, business notifications |

A mature system often **combines both**: write a transactional outbox, watch it with a Change Stream for low-latency wakeups, and poll the outbox to recover if Change Stream history is ever lost.

---

# PART VII — RUNBOOKS, CHECKLISTS, AND EXERCISES

## 65. Runbook for Launching a New Consumer

1. Define purpose, source collection, and target.
2. Verify replica set/sharded topology and `changeStream` privileges.
3. Choose pipeline, event types, and schema versions.
4. Define downstream idempotency keys and delivery policies.
5. Design processed-events/receipt stores where needed.
6. Set up a durable checkpoint store.
7. Decide whether historical backfill is required.
8. If needed, establish a safe capture boundary and bootstrap plan.
9. Deploy a single active consumer instance with ownership.
10. Monitor first events, checkpoints, lag, and DLQ.
11. Test restarts and cancellation.
12. Scale replicas/workers per ordering plan.
13. Reconcile source and target.
14. Enable business notifications only after SLOs and duplicate behavior are signed off.

---

## 66. Runbook When a Consumer Reports Persistent Errors

```text
Alert: consumer has no progress
                |
                v
       Is source accessible?
         /              \
       No                Yes
       |                  |
  Check topology       Check cursor error
  auth/network             |
       |           +-------+--------+
       |           |                |
       v        Resumable?       History lost?
   Backoff          |               |
  and retry         v               v
               Resume from       STOP, mark
               durable token     REBOOTSTRAP
                    |
                    v
               Check target
               idempotency
                    |
                    v
               Check lag/DLQ
                    |
                    v
                 HEALTHY
```

### 66.1. Never Delete Checkpoints During an Incident Without Impact Review

The checkpoint is proof of the last confirmed position. Deleting it can erase your ability to determine the exact replay window.

### 66.2. Never Declare Recovery While Important Events Sit in the DLQ

Reconcile and resolve failed records even when lag reads low.

---

## 67. Code Review Checklist

- [ ] Is the Change Stream opened on a supported deployment?
- [ ] Are scope and pipeline sufficiently narrow?
- [ ] Does `$project` avoid stripping event `_id`?
- [ ] Are all relevant event types handled explicitly?
- [ ] Are event `_id` and `documentKey._id` kept distinct?
- [ ] Are `UPDATE_LOOKUP` caveats and null `fullDocument` understood?
- [ ] Do delete/replace/invalidate events have policies?
- [ ] Are `try-with-resources` and shutdown/cancellation implemented?
- [ ] Is the cursor never shared across threads?
- [ ] Does a durable checkpoint store save raw BSON tokens intact?
- [ ] Does checkpointing happen only after side-effect acknowledgment?
- [ ] Do checkpoints never skip pending events?
- [ ] Are high-watermarks/empty batches handled safely?
- [ ] Is pipeline version/scope metadata stored?
- [ ] Are `resumeAfter`/`startAfter`/`startAtOperationTime` used properly?
- [ ] Is idempotency implemented for post-crash replays?
- [ ] Are business idempotency keys used for external side effects?
- [ ] Is there a provider/reconciliation strategy for unknown responses?
- [ ] Are worker leases/fencing enforced for multi-instance deployments?
- [ ] Are bounded queues and backpressure in place?
- [ ] Is per-key ordering or monotonic versioning enforced?
- [ ] Are tombstones kept if deletes can arrive out of order?
- [ ] Is there a recovery strategy for oplog history loss?
- [ ] Is historical data bootstrapping covered?
- [ ] Is backfill prevented from overwriting newer CDC state?
- [ ] Are DLQ/quarantine, retries/backoff, and alerts configured?
- [ ] Are lag, oplog window, and checkpoint progress monitored?
- [ ] Are Change Streams never mistaken for domain events?
- [ ] Are privacy/tenant authorization and safe logging enforced?
- [ ] Are crashes before and after checkpoints tested?
- [ ] Are failovers, invalidations, and rebootstraps rehearsed?

---

## 68. Exercise 1 — Duplicate Notification Delivery

A consumer receives E100, sends an email successfully, and crashes before saving the checkpoint.

**Question:** What can happen after restart?

**Answer:** E100 can replay and resend the email. You need a stable notification ID/idempotency at the provider or a delivery ledger, not just a resume token.

---

## 69. Exercise 2 — Checkpointing Too Early

A consumer saves token E200 first and then processes E200; the target write fails.

**Answer:** Restarting with `resumeAfter(E200)` skips E200. Always persist the token after successful processing.

---

## 70. Exercise 3 — Wrong Deduplication Key

A handler uses `documentKey._id` as the unique event identity.

**Answer:** Subsequent updates to the same document are falsely deduplicated. Use the resume token or a business event ID/version.

---

## 71. Exercise 4 — `UPDATE_LOOKUP`

The source updates to `PAID`, then immediately to `REFUNDED`; the consumer processes the `PAID` event slowly.

**Answer:** `fullDocument: UPDATE_LOOKUP` may return `REFUNDED`, not the exact `PAID` after-image. If exact transitions are needed, use a domain outbox or pre/post-images.

---

## 72. Exercise 5 — Ignored Deletes

A consumer only handles insert and update; the source deletes a document.

**Answer:** The target retains stale data. Implement a delete handler or tombstone semantics.

---

## 73. Exercise 6 — Two Workers

Two instances read the same stream from one checkpoint and both call the notification API.

**Answer:** Duplicate deliveries occur. Enforce single active owner/lease/fencing and idempotency.

---

## 74. Exercise 7 — Per-Key Ordering

Events version 5 and 6 for the same order are processed in parallel; version 6 writes first, version 5 writes second.

**Answer:** The final state is wrong. Use ordered partitioning or version-aware conditional writes.

---

## 75. Exercise 8 — Zero Events for 1 Hour

`tryNext()` repeatedly returns null.

**Answer:** This does not mean the consumer finished or the stream broke; check health metrics/heartbeats and whether source writes occurred.

---

## 76. Exercise 9 — `resumeAfter` After `invalidate`

A stream invalidates due to a collection drop, and the consumer calls `resumeAfter` with the invalidate token.

**Answer:** Invalid under standard semantics; use `startAfter` where supported and decide whether a new read model rebuild is required.

---

## 77. Exercise 10 — Stale Token

A consumer stays offline for 2 days while the oplog retains 6 hours.

**Answer:** Resumption fails due to history loss. Never start from “now” and declare healthy; rebootstrap/reconcile or replay from a durable event log.

---

## 78. Exercise 11 — Initial Data

A collection holds 10 million orders before the consumer deploys; a developer just calls `watch()`.

**Answer:** It will not automatically read the 10 million existing documents; bootstrap/backfill is required.

---

## 79. Exercise 12 — Backfill Race

CDC applies `PAID`, and backfill later writes `PENDING`.

**Answer:** Ordering/convergence bug. Capture changes first and replay after the baseline, or enforce version-aware writes.

---

## 80. Exercise 13 — `clusterTime` as Checkpoint

Two events share the same `clusterTime`, and the consumer saves the timestamp after the first event.

**Answer:** Timestamps do not uniquely identify events; use the opaque resume token.

---

## 81. Exercise 14 — Unbounded Queue

The reader pulls 10,000 events/sec, the sink handles 100 events/sec, and the queue is unbounded.

**Answer:** Heap memory grows unboundedly. Use a bounded queue with backpressure, scale the sink, and monitor oplog headroom.

---

## 82. Exercise 15 — External API Without Idempotency

A provider times out, leaving it unclear whether the notification was sent.

**Answer:** You cannot assume it was not sent. Use provider status queries, reconciliation, or an explicit duplicate-risk policy; token checkpoints do not resolve external ambiguity.

---

## 83. Exercise 16 — Pipeline Change

Consumer v1 only watched inserts; v2 starts watching updates while reusing v1's checkpoint.

**Answer:** Updates prior to v1's token were filtered out and will not reappear. Version the pipeline contract (`pipelineVersion`) and rebootstrap if needed.

---

## 84. Exercise 17 — Current Snapshot vs. Historical Notifications

A consumer loses 5 days of events, leaving only current order states.

**Answer:** You can rebuild the latest read model, yet cannot accurately reconstruct every historical transition/notification. Keep a durable domain event log/outbox.

---

## 85. Exercise 18 — Multi-Tenant

A delete event contains only `documentKey._id`, so the handler lacks `tenantId` to delete from the search index.

**Answer:** Design stable keys/mappings carrying tenant info, or maintain an identity lookup/tombstone. Never assume `fullDocument` is present on deletes.

---

## 86. Exercise 19 — Consumer Restarted While Old Worker Is Alive

The lease transfers to B, yet A wakes up and saves a checkpoint.

**Answer:** Enforce fencing generations on targets and checkpoints, and stop the stale worker; lease checks must not run only once at startup.

---

## 87. Exercise 20 — End-to-End Verification

Consumer lag=0, yet a failed payment event sits in the DLQ.

**Answer:** There is no proof the system is correct. Process/quarantine under control, reconcile business state, and report healthy only when all invariants hold.

---

## 88. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “Change Streams send notifications once automatically.” | Delivery can repeat after retries/restarts; external effects need idempotency. |
| “Reading an event means it is processed.” | Checkpoint only after downstream acknowledgment. |
| “Having a resume token means never losing events.” | Tokens depend on oplog history and stream validity. |
| “Document IDs can replace resume tokens.” | Document IDs do not identify individual changes. |
| “Timestamps suffice to resume every event.” | Multiple events can share a `clusterTime`. |
| “Change Streams read all existing documents.” | Bootstrapping/backfilling is still required. |
| “`UPDATE_LOOKUP` always returns the state right after the event.” | It can return a newer state or null. |
| “Deletes have `fullDocument` like inserts.” | Usually only `documentKey` is included; pre-images require config. |
| “No events means the cursor ended.” | `tryNext` returning null often just means an idle stream. |
| “The driver auto-resumes all errors forever.” | Only specific errors are resumable; does not replace app recovery. |
| “`resumeAfter` works after `invalidate`.” | `startAfter` has dedicated semantics for eligible cases. |
| “`startAfter` rebuilds data automatically.” | No. |
| “Saving tokens in RAM suffices for restarts.” | Durable checkpoints are mandatory. |
| “Checkpointing before apply avoids duplicates safely.” | It can drop events. |
| “Retrying target writes is always idempotent.” | `$inc`, appends, and external sends may not be idempotent. |
| “Idempotent `replaceOne` means ordering doesn't matter.” | Old events can overwrite newer state. |
| “MongoDB transactions cover external emails.” | No. |
| “A unique inbox before sending gives exactly-once.” | Crashing after receipt and before sending drops the send. |
| “Low consumer lag proves data correctness.” | Transform bugs, dropped events, or DLQ entries can still exist. |
| “Unbounded queues never block.” | They risk OOM crashes. |
| “Running duplicate consumers auto-balances work.” | They duplicate processing without partition ownership. |
| “The oplog window is unlimited.” | It has finite retention/sizing tied to write rate. |
| “Deleting the token and re-watching is recovery.” | It skips the entire missed history window. |
| “A fresh snapshot restores all historical notifications.” | Snapshots hold only current state. |
| “A dropped and recreated collection shares stream identity.” | Lifecycle and semantics can differ. |
| “Primary failover loses all events.” | Streams can resume via tokens/history and driver policies. |
| “One DB event always equals one API side effect.” | Business intent may require outbox mapping. |
| “Security does not affect CDC.” | Events, `fullDocument`, and pre-images can contain sensitive data. |

---

## 89. Official References

1. [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — concepts, scope, event schema, and resumption.
2. [MongoDB Manual — Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — event types, metadata, `documentKey`, `updateDescription`.
3. [MongoDB Manual — Change Stream Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — operations, oplog history, performance, and limitations.
4. [MongoDB Manual — Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream) — `resumeAfter`, `startAfter`, and `startAtOperationTime`.
5. [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — image availability and retention.
6. [MongoDB Manual — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — replication history and window.
7. [MongoDB Java Sync Driver — Monitor Data with Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — Java consumers, resume, and options.
8. [MongoDB Java Driver — ChangeStreamIterable Javadocs](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/ChangeStreamIterable.html) — watch configuration.
9. [MongoDB Java Driver — MongoChangeStreamCursor Javadocs](https://mongodb.github.io/mongo-java-driver/5.7/apidocs/driver-sync/com/mongodb/client/MongoChangeStreamCursor.html) — `tryNext`, `getResumeToken`, and `close`.
10. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transactions and atomic write boundaries.
11. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `ClientSession` and retry semantics.
12. [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability and acknowledgment.
13. [MongoDB Manual — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — retention and asynchronous cleanup.
14. [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — streaming integrations via connector.
15. [MongoDB Java Sync Driver — Compatibility](https://www.mongodb.com/docs/drivers/java/sync/current/compatibility/) — Java/server/driver version support.
16. [Testcontainers MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — replica set integration testing.
17. [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — when retries apply and what they mean.
18. [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/) — failover and availability.

**Version note:** event type names, pre/post-image options, cursor APIs, timeout behaviors, sharded cluster semantics, error labels, and Change Stream privileges vary across MongoDB Server, FCV, Java Driver, and topology versions. Always verify documentation for your exact stack before deploying to production.

---

## 90. Conclusion

**Change Streams** are a key tool for building change notifications and near-real-time synchronization on MongoDB. Yet a Change Stream is only **a source of change events**, not a complete reliable event-processing system.

For a reliable consumer:

1. Clearly define stream scope, event schema, and domain semantics.
2. Use Java `MongoChangeStreamCursor` and manage its lifecycle with `try-with-resources`.
3. Handle every event type, especially `update`, `delete`, and `invalidate`.
4. Understand the limits of `fullDocument: UPDATE_LOOKUP` and pre/post-images.
5. Persist **opaque BSON resume tokens** durably only after successful processing.
6. Design for at-least-once replay via idempotency, stable business keys, and receipts/outboxes where needed.
7. Enforce ordering, versioning, or tombstones so stale events never overwrite newer state.
8. On disconnects, resume from checkpoints; on history loss, stop and **rebootstrap/reconcile** instead of silently skipping.
9. Bootstrap historical data cleanly without gaps or backfill overwriting CDC.
10. Implement worker leases/fencing, bounded queues, retries with backoff, metrics, and failure-injection tests.

**Final rule:** never equate “observed the event” with “completed the business action”. Only when side effects are confirmed under a replay-safe protocol, checkpoints follow acknowledgment, and recovery paths are tested is a consumer ready for production.
