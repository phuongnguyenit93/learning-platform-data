# Combining Change Streams with CDC, Outbox, and Downstream Event Systems in MongoDB

## 1. The Problem: Data Is Persisted, Yet Other Systems Don't Know

An e-commerce application stores orders in MongoDB. When an order transitions from `NEW` to `PAID`, the system must:

- Send an event to the shipping service;
- Update the search index;
- Update a reporting read model;
- Notify the customer;
- Synchronize data to an analytics warehouse.

The naive initial design is usually:

```javascript
await orders.updateOne(
  { _id: orderId },
  { $set: { status: "PAID" } }
);

await eventBus.publish("OrderPaid", { orderId });
```

What happens if MongoDB commits the update, and the application crashes **before publishing**? The order is paid, yet downstream event consumers are never notified. Conversely, if you publish first and the database write fails, consumers act on an event that never committed.

This is the **dual-write problem**: a single business action writes to **two independent systems** without a shared atomic transaction.

MongoDB provides **change streams**, a mechanism for observing committed changes on a collection, database, or deployment. By combining them with **CDC (Change Data Capture)** and a **transactional outbox**, we can build a far more resilient event-publishing pipeline.

Lesson objectives:

1. Understand change streams as MongoDB's CDC source and how they differ from polling.
2. Distinguish **database changes** from **domain events**.
3. Know when to watch a business collection's change stream directly vs. when an **outbox** is needed.
4. Design transactions writing business data and outbox records together.
5. Build a relay forwarding events to Kafka, RabbitMQ, or equivalent receivers.
6. Persist **resume tokens/checkpoints** in proper order, handling disconnects and replays.
7. Design **idempotent** consumers and understand why *at-least-once* delivery is usually more realistic than claiming end-to-end *exactly-once*.
8. Address event ordering, schema evolution, sensitive data, backfills, retention, and oplog limits.
9. Practice with `mongosh` and Node.js in an authorized test environment.

## 2. The Big Picture: Change Streams, CDC, Outbox, and Consumers

### 2.1. CDC Is a Data Integration Goal

**Change Data Capture** means detecting and forwarding changes from a source datastore to downstream systems. A typical CDC pipeline:

```text
             MongoDB
        Collection / Database
                  |
              Change Stream
                  |
                 CDC
                  |
          Connector / Relay
                  |
         Kafka / Queue / Sink
                  |
        Search / Analytics / API
```

CDC serves use cases such as:

- Synchronizing data to Elasticsearch or another search engine;
- Streaming ETL into a data warehouse;
- Refreshing caches or read models;
- Integrating data between legacy and modern services;
- Detecting changes for near-real-time reactions.

**CDC does not automatically equal event sourcing.** In event sourcing, events are the durably stored source of truth for business history; in CDC, streams reflect **mutations that occurred in the database**, subject to source history and retention limits.

### 2.2. Change Streams Are MongoDB's Way of Exposing Changes

Change streams leverage MongoDB's replication/oplog infrastructure and wire protocol to expose change events. They differ from polling `updatedAt > lastSeen`:

- No periodic collection scans for documents with newer timestamps.
- Receives insert/update/replace/delete details plus certain administrative events depending on scope/features.
- Provides **resume tokens** to continue after interruptions while required history remains available.
- Uses server/driver mechanisms to track majority-committed changes under change stream semantics.

However, **change streams do not provide a permanent event store**, do not natively publish to Kafka, and do not guarantee every downstream consumer processes events exactly once.

### 2.3. Outbox Protects Against Dual-Writes

In the **transactional outbox pattern**, the business operation writes:

1. The primary document, e.g., the order.
2. An **outbox record** describing the domain event.

Both writes commit inside **the same MongoDB transaction** when spanning distinct documents or collections.

```text
              Order Service
                   |
          BEGIN MongoDB TRANSACTION
                   |
         +---------+----------+
         |                    |
         v                    v
    update orders        insert outbox
         |                    |
         +---------+----------+
                   |
                 COMMIT
                   |
                   v
          Change stream outbox
                   |
             Relay / Publisher
                   |
                   v
              Kafka / Queue
                   |
                   v
              Consumer(s)
```

If the transaction aborts, **neither the business update nor the outbox record commits**. If it commits, the outbox record persists durably at the requested write concern for the relay to forward afterward.

**Core insight:** the transaction guarantees consistency between business state and **the intent to emit an event** inside MongoDB; it **does not turn publishing to an external broker into part of the MongoDB transaction**.

### 2.4. Relays and Consumers Hold Two Different Responsibilities

A **relay** reads the outbox and forwards messages to receivers. It focuses on:

- Change streams, resume tokens, backoff, and acknowledgements;
- Mapping outbox records into messages;
- Monitoring lag and handling broker unavailability.

A **consumer** reads messages and applies business side effects. It focuses on:

- Idempotency and deduplication;
- Ordering and gap detection;
- System-specific validation and authorization;
- Retries, dead-letter queues, and checkpoints/offsets;
- Recoverability when messages are redelivered.

A healthy relay does not automatically mean consumers are behaving correctly.

## 3. Before Using Change Streams

### 3.1. Supported Deployments

Change streams are supported on compatible **replica sets** or **sharded clusters**, not standard standalone `mongod` instances. They run on self-managed deployments or compatible managed services within version and tier limits.

Before building:

- Verify MongoDB server version, Feature Compatibility Version, and driver version.
- Confirm watched collections/databases reside on a replica set or sharded cluster.
- Use valid connection strings and access privileges.
- Verify read/write concerns, failovers, and resumability.
- Size the oplog window to cover the longest expected relay outage.

If your local MongoDB runs standalone, do not try to fake it by creating a collection named `oplog` or adding `updatedAt` and calling it a change stream.

### 3.2. Scope of `watch()`

MongoDB drivers typically expose three watching levels:

```javascript
// Watch a single collection.
db.collection("orders").watch();

// Watch eligible collections in a single database.
db.watch();

// Watch multiple databases/collections across the deployment.
client.watch();
```

These examples illustrate the **MongoDB Node.js driver**, where `db` is a `Db` instance and `client` is a `MongoClient`; syntax may vary slightly in `mongosh` across versions.

Pick the narrowest scope meeting requirements:

- CDC for `orders`: collection-level stream.
- Syncing a few collections in one database: database-level stream with an explicit filter.
- Central collector across databases: deployment-level stream where privileges, topology, and cost permit.

Broader streams touch more namespaces and increase filtering overhead. Never open a dedicated stream per end user or per document without architectural justification and resource sizing.

### 3.3. Least-Privilege Access Control

Typically requires **`changeStream`** and **`find`** privileges on the watched scope. A relay reading the outbox does not need write access to every business collection.

Separate roles:

- Order service: write access to `orders`/`outbox`.
- Relay: watch change stream, read `outbox`, write its dedicated checkpoint collection.
- Consumer: access strictly to target resources it owns.

Never run a relay with cluster-wide admin credentials merely for setup convenience.

### 3.4. Change Streams and Majority Commit

Change streams emit notifications for **majority-committed** changes under MongoDB mechanics. Events must not be treated as notifications of transient uncommitted writes.

Consequences:

- A write acknowledged with `w:1` may not appear immediately on the change stream.
- Multi-document transactions emit changes once the transaction commits properly.
- "When the client issued the write" differs from "when the relay received the change event."
- Never use client wall clocks as exact positions in change stream history.

Exact details depend on topology and server capabilities; cross-check official documentation for your running version.

## 4. Structure of a Change Event

### 4.1. Example Insert Event

A document returned by `watch()` may resemble:

```javascript
{
  _id: { /* opaque resume token */ },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1794631200, i: 1 }),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: ObjectId("66a000000000000000000001")
  },
  fullDocument: {
    _id: ObjectId("66a000000000000000000001"),
    status: "NEW",
    totalCents: NumberLong("120000")
  }
}
```

This is a simplified example; exact fields vary by operation, server version, and stream options.

| Field | Meaning |
| --- | --- |
| `_id` | **Resume token** of the change event, not the business document's `_id` |
| `operationType` | Change type: `insert`, `update`, `replace`, `delete`, `invalidate`, etc. |
| `clusterTime` | Logical timestamp of the event in MongoDB |
| `ns` | Database and collection where the change occurred |
| `documentKey` | Source document identifier key, potentially including shard key fields |
| `fullDocument` | Document body where supported by event type and options |
| `updateDescription` | Field/array deltas for an update when provided |

A very common mistake:

```text
change._id                 = STREAM resume token
change.documentKey._id     = modified MongoDB DOCUMENT _id
change.fullDocument._id    = _id inside the document if returned
```

Only **`change._id`** is saved for resuming a change stream. Never substitute `documentKey._id` for the token.

### 4.2. Insert, Update, Replace, and Delete Differ

For `insert`, `fullDocument` is included in the change event. For `update`, the event normally carries `updateDescription` listing changed fields:

```javascript
{
  operationType: "update",
  documentKey: { _id: orderId },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

For `delete`, the document is gone, so no pre-delete `fullDocument` is included by default.

Hence consumers cannot assume every event contains a full document body. Blindly forwarding `change.fullDocument` without branching on operation types drops deletes or yields incomplete CDC messages.

### 4.3. `fullDocument: "updateLookup"` and Its Limits

When watching updates, you can request:

```javascript
const stream = orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
```

MongoDB looks up the current document at lookup time per supported semantics. **The result is not guaranteed to be the state right at the moment of the update event**, because another update may have committed before lookup ran—or the document may have been deleted.

Example:

```text
T0: status NEW  -> PAID      (change event X)
T1: status PAID -> SHIPPED   (change event Y)
T2: lookup fullDocument for X

fullDocument on X may show SHIPPED,
not the exact snapshot at T0.
```

For workflows needing the exact payload of **`OrderPaid`**, never treat `updateLookup` as a reliable domain-event snapshot. Storing an outbox payload frozen at transaction time is far cleaner.

### 4.4. Pre-Images and Post-Images

Supporting MongoDB versions provide **change stream pre-images and post-images** when configured on the collection and requested on the stream. They expose before/after states per server semantics—helpful for auditing, diffing, or CDC.

However:

- Setting the watch option alone is insufficient if capture is not enabled on the collection.
- Incurs storage/resource overhead and finite retention.
- Supported operations and retention depend on MongoDB version.
- Never use pre-images as a permanent audit archive.
- Deleted data or expired retention affects image availability.

Never assume every update event includes `fullDocumentBeforeChange`; verify both options and server version.

## 5. Direct CDC from a Business Collection

### 5.1. Simple Pattern

```text
MongoDB orders collection
             |
      orders.watch()
             |
         CDC relay
             |
      Search index / Cache
```

Node.js example:

```javascript
const changeStream = orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        }
      }
    }
  ],
  { fullDocument: "updateLookup" }
);

for await (const change of changeStream) {
  console.log(change.operationType, change.documentKey);
}
```

This snippet lacks checkpoints, retries, and cleanup; it only demonstrates receiving events. Production code requires stream lifecycle management, resume tokens, error handling, and clean shutdown hooks.

### 5.2. When Does Direct CDC Make Sense?

For **search index synchronization**:

- An order insert → add document to the read model.
- An update → fetch/apply the new state.
- A delete → delete the document from the target index.

Here the consumer wants **to mirror persisted storage state**. Raw database changes map closely to the target, making direct CDC simpler than an outbox.

### 5.3. Why Direct CDC Is Not a Domain Event

Suppose a service runs:

```javascript
await orders.updateOne(
  { _id: orderId },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);
```

A CDC consumer observes `updatedFields.status = "PAID"`. It might guess the business event is `OrderPaid`, yet:

- An admin may have manually patched `status` to fix a data bug.
- The same final state may stem from different workflows.
- Another update might write `status: "PAID"` when it was already `PAID`.
- A migration might touch thousands of records without intending to trigger shipping.
- Downstream may need metadata like `paymentId`, operator, or business effective time absent from `updateDescription`.

**A database change describes "how data mutated"; a domain event describes "what happened in the business."** Sometimes they coincide, but they are not synonymous.

### 5.4. Choosing a Model by Intent

| Goal | Usually Appropriate Approach |
|---|---|
| Mirror a collection to a search index | Direct CDC |
| Refresh cache/read model from storage edits | Direct CDC, or outbox if business semantics matter |
| Notify shipping service of `OrderPaid` | Domain event via transactional outbox |
| Emit exact `paymentId`, `invoiceId`, rule version at commit | Outbox with immutable payload |
| Long-term compliance audit that must outlive oplog rotation | Durable event/audit store with dedicated retention |
| Inform another API that a field changed | Direct CDC may suffice if the contract is clear |

## 6. Transactional Outbox: Designing the Data Structure

### 6.1. Recommended Outbox Record

```javascript
{
  _id: "evt-7c82d",
  eventType: "OrderPaid",
  schemaVersion: 1,
  aggregateType: "Order",
  aggregateId: "ORDER-1001",
  aggregateVersion: 5,
  tenantId: "TENANT-A",
  occurredAt: ISODate("2026-11-14T03:30:00Z"),
  requestId: "req-4e91",
  correlationId: "trace-27e8",
  payload: {
    orderNo: "ORDER-1001",
    paymentId: "PAY-812",
    amountCents: NumberLong("120000"),
    currency: "VND"
  }
}
```

Design each field deliberately:

| Field | Role |
| --- | --- |
| `_id` / `eventId` | Stable event identifier for deduplication |
| `eventType` | Business event name |
| `schemaVersion` | Payload contract version |
| `aggregateType` and `aggregateId` | Business entity emitting the event |
| `aggregateVersion` | Consistently managed **business** sequence/version |
| `tenantId` | Data partitioning and authorization in multi-tenant systems |
| `occurredAt` | Business timestamp for observability |
| `requestId` | Links back to originating request intent |
| `correlationId` | Cross-service distributed tracing |
| `payload` | Data delivered to consumers |

Never use `occurredAt` as a unique identifier or strict ordering key: clocks skew and multiple events share timestamps. For strict per-aggregate ordering, use an **atomically incremented sequence/version**.

### 6.2. Why `eventId` Is Not the Resume Token

Example:

```text
Outbox document:
    _id = "evt-7c82d"             -> business event ID

Change event on outbox:
    _id = <opaque resume token>   -> change stream position
    documentKey._id = "evt-7c82d"
    fullDocument._id = "evt-7c82d"
```

The **business event ID** travels with the message to Kafka/consumers for deduplication. The **resume token** stays in the relay's own state to reopen the MongoDB stream.

Mixing the two up breaks relay resumption and strips consumers of a stable deduplication key.

### 6.3. Minimal Yet Self-Contained Payload

Avoid publishing the entire MongoDB document if consumers only need `orderId`, `paymentId`, and amount:

- Cuts bandwidth and message size.
- Reduces coupling to internal DB schemas.
- Avoids leaking PII or internal fields.
- Standardizes money types, dates, enums, and optional fields.

Conversely, an overly sparse payload forces consumers to call back into the source service; if data changed meanwhile, consumers read stale or wrong state. Design the **event contract** around downstream needs and security policy.

### 6.4. Size Limits

MongoDB documents obey the BSON limit—normally **16 MiB**. Outbox records and change events also face memory/bandwidth limits in streaming tools and brokers.

Never embed huge files, multi-thousand-line carts, or raw binaries directly into `payload`. For large blobs, store an ID/reference to managed object storage along with version/hash and access controls.

### 6.5. Immutable Events and Publishing State

Treat the **event payload** as immutable after commit. If you track `publishedAt`, `attempts`, or relay status, consider placing that metadata in a separate collection:

```text
outbox_events: immutable event payload
relay_checkpoints: consumer/relay progress
delivery_attempts: optional diagnostics
```

Updating `published: true` directly on the outbox document is not universally wrong, yet:

- It generates extra change events if updates are watched.
- A single shared `published` flag cannot track multiple independent consumers.
- Setting the flag **before broker acknowledgement** risks dropping events.
- Multiple relays require ownership/leases/fencing and race protection.

Never mistake a `published` flag for end-to-end proof that all downstream systems processed the message.

## 7. Writing Business Data and Outbox in One Transaction

### 7.1. Why Share One Transaction?

If a service writes:

```javascript
await orders.insertOne(order);
await outbox.insertOne(event);
```

even though both touch MongoDB, they remain **two separate writes**. If the process dies in between, the order exists without an event.

For all-or-nothing atomicity across **two documents** or two collections, use a MongoDB multi-document transaction on a supporting deployment:

```text
BEGIN
   insert order
   insert outbox event
COMMIT
```

When only a single document changes, MongoDB provides single-document atomicity; embedding events into the business document can leverage that if designed carefully. However, appending unbounded outbox arrays inside business documents risks document bloat, write contention, and awkward cleanup. For most services, an **outbox collection + short transaction** is easier to operate.

### 7.2. Preparing the Hands-On Environment

Examples use a test database:

```text
mongo_change_stream_row279_lab
```

Prerequisites:

- Test replica set or sharded cluster supporting transactions and change streams.
- Node.js driver installed in a sample app or isolated learning environment.
- Write privileges in the test database.
- Namespace isolated from other users' data.

No need to kill secondaries or flood millions of writes to practice change streams. Never run examples on production order/payment collections.

### 7.3. Node.js Example: Atomic Order + Outbox Creation

Assume a `MongoClient` connected to a replica set with dedicated lab collection names:

```javascript
import { ObjectId } from "mongodb";

async function createOrderWithOutbox({
  client,
  db,
  tenantId,
  requestId,
  orderNo,
  amountCents
}) {
  // Stable IDs across potential transaction callback retries.
  const orderId = new ObjectId();
  const eventId = new ObjectId();
  const occurredAt = new Date();

  const orders = db.collection("orders_demo");
  const outbox = db.collection("outbox_demo");
  const session = client.startSession();

  try {
    await session.withTransaction(
      async () => {
        await orders.insertOne(
          {
            _id: orderId,
            tenantId,
            requestId,
            orderNo,
            status: "NEW",
            amountCents,
            version: 1,
            createdAt: occurredAt
          },
          { session }
        );

        await outbox.insertOne(
          {
            _id: eventId,
            tenantId,
            eventType: "OrderCreated",
            schemaVersion: 1,
            aggregateType: "Order",
            aggregateId: orderId.toHexString(),
            aggregateVersion: 1,
            requestId,
            occurredAt,
            payload: {
              orderNo,
              amountCents,
              status: "NEW"
            }
          },
          { session }
        );
      },
      {
        readPreference: "primary",
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" }
      }
    );

    return { orderId, eventId };
  } finally {
    await session.endSession();
  }
}
```

Explanation:

1. `orders_demo` and `outbox_demo` live in the **same transaction-capable MongoDB deployment**.
2. `withTransaction` manages transaction lifecycle and retries eligible transient errors per driver semantics.
3. Both inserts pass the **same `session`**.
4. `orderId`/`eventId` are generated **before the callback** so retries never mint duplicate IDs.
5. `writeConcern: { w: "majority" }` ensures durable commit confirmation.
6. Never publish to Kafka, send emails, or call payment APIs **inside the callback**.

This illustrates **MongoDB atomicity**, not a complete production API. Validate `tenantId`, `orderNo`, amounts, access permissions, schema bounds, and money types. For exact monetary amounts, prefer integer minor units (`Long`) or `Decimal128` rather than floating-point numbers.

### 7.4. API-Level Idempotency Is Still Required

If an HTTP request is retried after the transaction committed yet the response got lost, calling this function again creates **new `orderId` and `eventId` values**. Both transactions are valid in MongoDB, yet they create two orders for **one user intent**.

In production:

- Accept and validate a client `requestId` or `idempotencyKey`.
- Enforce a **unique constraint** on the appropriate business key, e.g., `(tenantId, requestId)` on `orders` where sharding allows.
- On duplicate key errors, **read the existing record for that `requestId` and verify payload/fingerprint match** before returning the prior result.
- Retain idempotency records long enough to cover retries and reconciliation.

In sharded collections, **unique indexes require the shard key as a prefix**, so design keys and unique constraints before deployment. Do not assume `_id` on a sharded collection whose shard key excludes `_id` is globally unique across shards automatically.

### 7.5. No Event Is Emitted When a Transaction Aborts

Suppose business validation fails after inserting the order:

```javascript
await session.withTransaction(async () => {
  await orders.insertOne(order, { session });

  if (!inventoryAvailable) {
    throw new Error("OUT_OF_STOCK");
  }

  await outbox.insertOne(event, { session });
});
```

When the callback throws and the transaction aborts, neither the uncommitted order nor the outbox record persists. If business logic demands strict inventory verification, enforce that condition **atomically inside the transaction**, not solely via an `inventoryAvailable` boolean read from a stale cache.

### 7.6. Keep Transactions Short

Keep transactions brief:

```text
Outside transaction:
   validate input, prepare event, auth, compute derived fields

Inside transaction:
   check/update state needing consistency
   insert outbox record
   commit

After commit:
   relay publishes to broker
   consumers process
```

Never wait for HTTP webhooks, Kafka acknowledgements, or user responses **inside a MongoDB transaction**—that stretches snapshot lifetimes, increases lock/write contention, and introduces un-rollbackable side effects.

## 8. Relay: Reading the Outbox via Change Streams

### 8.1. Overall Flow

```text
outbox_demo (MongoDB, persistent)
           |
           | change stream insert events
           v
         Relay
           |
           | validate/map
           v
      publisher.publish()
           |
           | broker acknowledgement
           v
       save checkpoint
```

The order **publish succeeds → save checkpoint** underpins *at-least-once* delivery. Saving checkpoints before broker acknowledgement risks **silently dropping unpublished events** on crashes.

### 8.2. Processing an Outbox Insert

Node.js driver:

```javascript
const stream = outbox.watch(
  [
    {
      $match: {
        operationType: "insert"
      }
    }
  ],
  {
    fullDocument: "default",
    maxAwaitTimeMS: 1000
  }
);

for await (const change of stream) {
  const event = change.fullDocument;

  await publisher.publish({
    topic: "orders.events",
    key: String(event.aggregateId),
    value: JSON.stringify({
      eventId: String(event._id),
      eventType: event.eventType,
      schemaVersion: event.schemaVersion,
      aggregateId: event.aggregateId,
      aggregateVersion: event.aggregateVersion,
      tenantId: event.tenantId,
      payload: event.payload
    })
  });

  // Only here may stream progress be checkpointed.
  await checkpoints.updateOne(
    { _id: "relay-orders-events" },
    {
      $set: {
        resumeToken: change._id,
        updatedAt: new Date()
      }
    },
    { upsert: true }
  );
}
```

Here `publisher.publish()` is a **hypothetical interface** for a Kafka/queue adapter. It must resolve only after receiving **broker acknowledgement matching your durability guarantees**, not merely after enqueueing into an in-memory buffer.

This snippet also assumes a single ordered relay, one checkpoint, and one target. Production relays add startup, reconnect, error handling, and leader election when multiple instances exist.

### 8.3. Relay Pattern with Resume Tokens

Structured example:

```javascript
async function runOutboxRelay({
  outbox,
  checkpoints,
  publisher,
  relayName = "orders-to-broker"
}) {
  const saved = await checkpoints.findOne({
    _id: relayName
  });

  const options = {
    fullDocument: "default",
    maxAwaitTimeMS: 1000
  };

  if (saved?.resumeToken) {
    options.resumeAfter = saved.resumeToken;
  }

  const stream = outbox.watch(
    [{ $match: { operationType: "insert" } }],
    options
  );

  try {
    for await (const change of stream) {
      const event = change.fullDocument;
      if (!event) {
        throw new Error("OUTBOX_DOCUMENT_MISSING");
      }

      // This example path requires every event to carry valid metadata.
      if (!event.eventType || !event.aggregateId) {
        throw new Error("INVALID_OUTBOX_EVENT");
      }

      await publisher.publish({
        topic: "orders.events",
        key: String(event.aggregateId),
        value: JSON.stringify({
          eventId: String(event._id),
          type: event.eventType,
          schemaVersion: event.schemaVersion,
          aggregateId: event.aggregateId,
          aggregateVersion: event.aggregateVersion,
          tenantId: event.tenantId,
          payload: event.payload
        })
      });

      await checkpoints.updateOne(
        { _id: relayName },
        {
          $set: {
            resumeToken: change._id,
            updatedAt: new Date()
          }
        },
        { upsert: true }
      );
    }
  } finally {
    await stream.close();
  }
}
```

Here:

- `saved.resumeToken` must be persisted in driver-supported BSON/Extended JSON and **restored intact**; never slice or alter opaque token structures.
- `resumeAfter` resumes **after** the checkpointed position.
- `change._id` is the stream token; `event._id` is the outbox event ID.
- If publishing fails to acknowledge, **never advance the checkpoint**.
- If publishing succeeds and the process crashes before checkpointing, the event will replay; consumers must be idempotent.

### 8.4. Can a Relay Stop Without "Losing" Events?

While the oplog still holds required history and checkpoints are saved properly, a relay can resume seamlessly across restarts. Yet there is **no infinite guarantee**:

- The oplog has a finite **retention window**.
- The stream can receive `invalidate` if the collection is dropped/renamed under supported conditions.
- Checkpoints can be corrupted, overwritten, or stripped of BSON types.
- Namespaces may change.
- A broker publish might remain unacknowledged if the relay crashed mid-flight.

A transactional outbox ensures **event records persist in MongoDB** so they can be scanned/reconciled if oplog history expires; however, if outbox records were already purged by TTL or manual deletion prior to backfill, that collection alone cannot recover them.

### 8.5. Never Blindly Delete Resume Tokens

If `resumeAfter` fails due to lost history, the solution is **not** discarding the token, opening a fresh stream from "now," and moving on. Doing so **skips every event emitted during the outage**.

Enforce a **recovery policy**:

1. Halt the relay or flag it as needing reconciliation.
2. Identify the range of data/event IDs potentially unpublished.
3. Scan retained outbox records from the business checkpoint onward.
4. Use `eventId` to deduplicate at the broker/consumers.
5. Re-establish live streaming via a gap-free handoff protocol.
6. Verify counts and reconcile state before declaring recovery complete.

Never fabricate a `resumeAfter` token from a timestamp or `ObjectId` to replace a server-issued token.

## 9. Checkpointing and *At-Least-Once* Delivery Semantics

### 9.1. Crash Matrix

| When the Relay Crashes | Event in Broker? | Checkpoint Advanced? | Outcome |
|---|---|---|---|
| Before publish | No | No | Resume retries; no loss due to checkpoint |
| Publish in flight, no response | Unknown | No | Retry may duplicate; requires idempotency |
| After broker ack, before checkpoint | Yes | No | Restart publishes again |
| After durable checkpoint saved | Yes, per ack level | Yes | Resumes from next position |
| Checkpoint saved **before** publish | Possibly not | Yes | **Risk of dropped event** |

This illustrates a fundamental truth:

> Ordering `publish()` before `saveCheckpoint()` does not produce end-to-end exactly-once across two systems without a shared transaction—a crash window always remains between them.

### 9.2. Choosing Checkpoint Durability

Checkpoints must be persisted **durably** with an appropriate write concern. Keeping checkpoints only in relay RAM triggers massive unnecessary replays on restarts. Writing checkpoints to MongoDB with a weak write concern risks rollbacks during failover, regressing the relay to an older token and re-publishing events.

Replays are normally handleable via deduplication; silently dropping unpublished events is far worse. Therefore, prioritize **at-least-once + idempotent consumers** first, then optimize duplicate rates.

### 9.3. One Checkpoint per Logical Stream

If two relay instances read the same change stream while sharing a checkpoint:

```text
Relay A: publishes event #10, checkpoints #10
Relay B: publishes event #11, checkpoints #11
Relay A: writes checkpoint #10 late
```

Checkpoints **regress** without ownership and ordering enforcement. Production requires:

- **One active owner** per logical stream/checkpoint;
- Leader election/leases with **fencing tokens** blocking deposed owners from writing checkpoints;
- Or deliberate source partitioning with independent checkpoints per partition.

Never run two identical processes with the same `resumeAfter` hoping the broker magically deduplicates everything.

### 9.4. Checkpoints Differ from Broker Offsets

Keep at least three concepts distinct:

```text
MongoDB change stream -> relay -> Kafka -> consumer
           |                       |
           v                       v
      resume token             Kafka offset
```

- MongoDB **resume token**: how far the relay has read in the change stream.
- Kafka **consumer offset**: how far the consumer has processed/acked in a topic partition.
- Business **eventId**: event identifier checked by consumers to prevent duplicate side effects.

None replaces the others. A broker can hold a message that consumers haven't processed yet; the relay's checkpoint validly advances once the broker confirms persistence.

## 10. Idempotent Consumers: Preventing Duplicate Processing Downstream

### 10.1. Why Must Consumers Tolerate Duplicates?

Suppose an `OrderPaid` outbox event has `eventId = evt-1001`. The relay publishes it successfully yet crashes before saving its checkpoint. On restart, the relay resumes and publishes it again.

The consumer receives:

```text
evt-1001  (first time)
evt-1001  (second time)
```

If the consumer fires an email every delivery without deduplication, the customer receives two emails. If it credits balances or deducts stock twice, the damage is far worse.

### 10.2. Inbox / Deduplication Table

A common pattern is an **inbox**:

```javascript
{
  _id: "shipping-service:evt-1001",
  consumerId: "shipping-service",
  eventId: "evt-1001",
  processedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Combine **`consumerId + eventId`** as a unique key. When the consumer updates a MongoDB collection, execute:

1. Insert the inbox record.
2. Update business/read-model state.
3. Commit.

inside **the same transaction** on the consumer's MongoDB instance so the deduplication marker and database side effect are atomic.

### 10.3. Node.js Example: Processing an Event Inside a Transaction

Assume `inbox` and `readModels` reside in the same transaction-capable MongoDB deployment:

```javascript
async function consumeOrderCreated({
  client,
  db,
  event
}) {
  const session = client.startSession();
  const inbox = db.collection("consumer_inbox");
  const readModels = db.collection("order_read_models");

  const consumerId = "search-projection-v1";
  const inboxId = consumerId + ":" + event.eventId;

  try {
    await session.withTransaction(
      async () => {
        // Insert first to enforce a unique lock per consumer/event.
        await inbox.insertOne(
          {
            _id: inboxId,
            consumerId,
            eventId: event.eventId,
            processedAt: new Date()
          },
          { session }
        );

        // Illustrates OrderCreated (version 1).
        await readModels.updateOne(
          {
            tenantId: event.tenantId,
            orderId: event.aggregateId
          },
          {
            $setOnInsert: {
              tenantId: event.tenantId,
              orderId: event.aggregateId,
              status: event.payload.status,
              version: event.aggregateVersion
            }
          },
          { upsert: true, session }
        );
      },
      {
        readPreference: "primary",
        readConcern: { level: "snapshot" },
        writeConcern: { w: "majority" }
      }
    );

    return { outcome: "PROCESSED" };
  } catch (error) {
    if (error.code !== 11000) {
      throw error;
    }

    // Verify whether the duplicate key actually belongs to the processed event.
    const seen = await inbox.findOne({ _id: inboxId });
    if (seen && seen.eventId === event.eventId) {
      return { outcome: "DUPLICATE_ALREADY_PROCESSED" };
    }
    throw error;
  } finally {
    await session.endSession();
  }
}
```

Design notes:

- `inbox._id` must be unique within the required scope. If sharded, account for shard-key uniqueness constraints.
- `readModels` also needs a unique key on `(tenantId, orderId)` so distinct events never spawn duplicate target documents for the same order.
- This snippet illustrates `OrderCreated` only. `OrderPaid` and `OrderCancelled` require sequence checks and explicit state transitions.
- If the consumer performs **external HTTP calls or sends email**, MongoDB transactions do not make those atomic; combine with a downstream outbox or provider idempotency keys.
- If `DuplicateKey` comes from **another unique index**, never blindly treat every `11000` error as "already processed." Verify the duplicate belongs to the expected inbox key and inspect the event fingerprint.

### 10.4. Broker Acknowledgements / Offsets After Side Effects

With Kafka or message queues:

```text
receive event
     |
validate/schema
     |
check dedup/sequence
     |
apply business update (commit)
     |
ack message / commit offset
```

Acking the broker **before** side effects risks skipping unprocessed events on a crash. Committing side effects then crashing before acking redelivers the message—where the inbox/idempotency check safely catches duplicates.

### 10.5. What Does End-to-End Exactly-Once Mean?

Certain brokers or stream processors support **exactly-once processing semantics** within bounded scopes, such as atomic read-process-write across topics in the same cluster. However, MongoDB transactions, broker transactions, and external APIs rarely share **one unified atomic transaction**.

Therefore:

- You can achieve **effectively-once business outcomes** when every stage enforces idempotency keys and durable state.
- Messages may still be **published or received more than once**.
- Exactly-once inside a broker **does not guarantee** an email or card charge fires only once.
- For webhooks, pass provider idempotency keys and reconcile timeouts.

Avoid claiming "MongoDB change streams guarantee exactly-once delivery to every consumer." That is not the default contract.

## 11. Event Ordering and Broker Partitioning

### 11.1. Database Order Is Not Automatically Multi-Source Business Order

Change streams order events within MongoDB per stream scope using resume tokens/`clusterTime`. Once forwarded to a multi-partition broker, parallel workers, or multiple services, end-to-end execution order can shift.

Example:

```text
OrderCreated   (version 1)
OrderPaid      (version 2)
OrderShipped   (version 3)

Broker/consumer with parallel workers:
   Worker B finishes v3 before Worker A finishes v2
```

If handlers naively run `$set: {status: event.status}`, the older event overwrites the newer state.

### 11.2. Partitioning by Aggregate ID

In Kafka, use:

```javascript
publisher.publish({
  topic: "orders.events",
  key: event.aggregateId,
  value: serialize(event)
});
```

Using **`aggregateId`** as the message key routes events for the same order to the same partition while partition counts stay stable, aiding ordering. Still account for:

- Producer retries and broker ordering configurations.
- Partition count changes.
- Multiple independent producers writing for the same aggregate.
- Consumer retries, rebalances, and parallel worker pools.
- Events coming from different services with no shared total order.

Kafka partition ordering is not a full substitute for **`aggregateVersion`** and state-guard rules.

### 11.3. Aggregate Version / Sequence

A domain event can carry:

```javascript
{
  aggregateId: "ORDER-1001",
  aggregateVersion: 3,
  eventType: "OrderShipped"
}
```

The consumer stores the last applied version. Policy:

- If event version equals **`currentVersion + 1`**: apply.
- If event version **≤ `currentVersion`**: already processed or stale; verify `eventId`.
- If event version **> `currentVersion + 1`**: **gap** detected; wait, retry, or reconcile.

This applies when every significant state change emits an event with a contiguous sequence. If only selected transitions emit events, never blindly treat MongoDB's document `version` as a contiguous event sequence without an explicit mapping.

### 11.4. Attaching Sequence Atomically with Business Updates

One approach:

```javascript
// Inside the same transaction:
const updated = await orders.findOneAndUpdate(
  {
    _id: orderId,
    status: "NEW"
  },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  },
  {
    session,
    returnDocument: "after",
    includeResultMetadata: false
  }
);

if (!updated) {
  throw new Error("INVALID_STATE_OR_NOT_FOUND");
}

await outbox.insertOne(
  {
    _id: eventId,
    eventType: "OrderPaid",
    aggregateId: String(orderId),
    aggregateVersion: updated.version,
    payload: { status: "PAID" }
  },
  { session }
);
```

MongoDB Node.js driver versions differ in `findOneAndUpdate()` return signatures; match `includeResultMetadata` to your driver contract. Never run two operations sharing one `session` concurrently via `Promise.all()`.

If only a subset of order updates emit events, manage the event sequence explicitly rather than assuming every document version maps 1:1 to an event.

## 12. Initial Startup, Backfilling, and Handling Gaps

### 12.1. The Problem with Starting `watch` at "Now"

Suppose `outbox` already holds 100,000 events before a new relay deploys. Simply calling:

```javascript
const stream = outbox.watch();
```

does not replay **historical outbox documents** from when the collection was created. Change streams observe changes from an oplog position forward, not "read all existing documents then stream new ones."

To process historical backlogs, pair a **backfill/snapshot scan** with streaming.

### 12.2. Race Between Scan and Watch

Naive approach:

```text
1. Scan outbox from start to end
2. Open change stream after scan finishes
```

Between steps 1 and 2, the service can insert new outbox records that miss the completed scan yet predate the stream start point—creating a **lost-event gap**.

Reverse approach:

```text
1. Open stream
2. Scan outbox
3. Start consuming stream
```

can deliver the same event via both scan and stream. **Duplicates are handled by `eventId`**, yet you must ensure the stream cursor actually initialized/anchored on the server before starting the scan—some driver APIs initialize cursors lazily.

### 12.3. Controlled Handoff Strategy

A common architecture:

1. Establish a **consistent watermark/cluster time** or valid stream start mechanism per server/driver rules.
2. Open the change stream at a point guaranteed to cover all writes occurring during the scan.
3. Scan unpublished outbox records ordered by a stable key/watermark.
4. Publish scanned and streamed events with identical **`eventId`** so consumers deduplicate.
5. Once backfill finishes, transition to the live stream and persist resume tokens.
6. Reconcile **counts, sequence ranges, and any remaining unpublished records**.

Algorithm details must account for snapshots, read concerns, tokens, oplog windows, startup semantics, and write races. **Never treat a naive "watch then find" as proof of a gap-free handoff** without verifying the server-side stream anchor.

### 12.4. Outbox Retention Must Exceed Recovery Time

Suppose:

```text
Oplog window:                12 hours
Relay outage:                18 hours
Outbox document retention:    7 days
```

The relay cannot resume its change stream because oplog history expired. Yet because outbox records remain intact, the system can scan and reconcile unpublished events.

Conversely, if the outbox TTL were only 6 hours, both the oplog and outbox would lose needed records, leaving no complete recovery source.

Base retention on **recovery SLOs, maximum outage duration, backfill speed, and audit obligations**—not storage minimalism alone.

### 12.5. Never Attach an Unconditional TTL to the Outbox

Example:

```javascript
// Caution: TTL deletes solely by age,
// regardless of whether any consumer processed the event.
outbox.createIndex(
  { occurredAt: 1 },
  { expireAfterSeconds: 86400 }
);
```

A TTL index can purge an event before brokers or consumers ever receive it. That pattern is **unsuitable** if outages longer than 24 hours must incur zero event loss.

In production, consider:

- Cleaning up only after verified delivery/checkpoint evidence;
- Retention exceeding recovery SLOs with margin;
- Archiving to durable storage if auditing is required;
- Policies covering multiple consumers/subscribers;
- Reconciling before purging old events.

## 13. Resume Tokens, `invalidate`, and Tough Failures

### 13.1. What Is `resumeAfter`?

MongoDB change events carry an opaque resume token in `_id`. On restart:

```javascript
const saved = await checkpoints.findOne({
  _id: "orders-to-broker"
});

const options = saved?.resumeToken
  ? { resumeAfter: saved.resumeToken }
  : {};

const stream = outbox.watch([], options);
```

`resumeAfter` resumes **after** the event represented by the token while retained history exists. Never replace the token with a document `_id` or timestamp.

### 13.2. `startAfter`, `startAtOperationTime`, and Limits

Distinguish clearly:

| Option | High-Level Meaning |
| --- | --- |
| `resumeAfter` | Resume after an accepted resume token |
| `startAfter` | Start after a resume token, including supported recovery past `invalidate` |
| `startAtOperationTime` | Start from an eligible operation time where history and version support it |

Never mix mutually exclusive options arbitrarily. Never fabricate `startAtOperationTime` from `Date.now()` and treat it as a valid cluster time; it requires a server BSON Timestamp with specific semantics.

### 13.3. `invalidate` Events

Namespace changes like `drop`, `rename`, or `dropDatabase` can **`invalidate`** a stream depending on scope and operation type. After `invalidate`:

- `resumeAfter` cannot resume across `invalidate` in restricted cases.
- `startAfter` can open a new stream past `invalidate` in supported cases per MongoDB docs.
- Applications must decide whether the vanished old namespace still matches the intended outbox source.

Never "skip `invalidate`" and jump onto a new collection sharing the same name without checking event IDs, schemas, published history, and ownership.

### 13.4. Oplog History Loss

A relay stops for 48 hours while the oplog window is 6 hours. The old resume token fails with a change stream history error.

Resolution:

1. Never delete the checkpoint and silently start from "now."
2. Trigger reconciliation/backfill over retained outbox records.
3. Verify all events are accounted for and re-establish live streaming with zero gaps.
4. Adjust retention or capacity to reduce recurrence risk.

Increasing oplog size **after history was already overwritten** does not bring back old oplog entries.

### 13.5. Never Mangle Resume Tokens in Aggregation Pipelines

Change streams require event `_id` to preserve the intact resume token. Never write a pipeline like:

```javascript
// Do not do this when watching: strips the _id resume token.
[
  { $project: { _id: 0, operationType: 1 } }
]
```

Stripping or altering the token breaks streaming/resumption under MongoDB rules.

Filter only by relevant fields while keeping event `_id` untouched. If you need to map payloads to a broker schema, transform inside the **application relay**, not by rewriting system `_id` inside the server-side change stream pipeline.

### 13.6. Never Reuse One Token Arbitrarily Across Different Streams

A token belongs to a server-defined stream position and scope. Never treat collection A's token as a generic checkpoint for collection B or swap tokens across different databases/deployments. Whenever changing topology, namespace, watch pipeline, or options, verify resume compatibility against the documentation.

## 14. Downstream Event Receivers: Kafka, Queues, and Webhooks

### 14.1. Kafka

Pipeline:

```text
MongoDB outbox
      |
      v
 Change Stream Relay
      |
      v
 Kafka topic "orders.events"
      |
      +----> Shipping consumer group
      |
      +----> Analytics consumer group
      |
      +----> Notification consumer group
```

Kafka fits well when:

- One event feeds multiple consumer groups;
- Messages need Kafka-managed retention;
- Consumers replay by offset;
- Per-key partition ordering is useful.

Caveats:

- Kafka offsets are separate from MongoDB resume tokens.
- Topic retention is still finite—size it to SLOs.
- Producer acks, idempotent producers, and Kafka transactions carry their own semantics.
- A MongoDB-to-Kafka relay still requires idempotency unless wrapped in a specialized transactional bridge.

### 14.2. RabbitMQ or Message Queues

An acknowledgment-based queue/broker suits task distribution and retries. Verify:

- Persistent messages and durability;
- Publisher confirmations;
- Consumer acknowledgements;
- Redelivery and dead-letter queues;
- Routing keys and exchanges;
- Ordering under multiple consumers.

Never treat `publish()` returning as success merely because the client call completed; the adapter must await **broker acknowledgement per your durability contract**.

### 14.3. Webhooks or HTTP Services

A relay can call HTTP directly:

```text
outbox -> relay -> POST /shipping/events
```

However:

- HTTP timeouts leave target processing status ambiguous.
- Retries can resend the same `eventId`.
- Authentication, HMAC signatures, or mTLS are needed.
- Receivers must be idempotent.
- Prolonged receiver outages require backoff retries, DLQs, or an intermediary durable queue.

For multiple receivers, a queue/broker decouples dependencies much better than direct HTTP calls along the critical path.

### 14.4. Why Not Publish Separately to Multiple Consumers Using One Flag?

Suppose an event has three subscribers. If the relay sets:

```javascript
{ published: true }
```

after delivering to subscriber A, it has no idea whether B and C received it.

You need either:

- A broker providing fan-out and consumer groups with independent offsets; or
- A per-destination/per-consumer status table; or
- Separate checkpoints and replay tracking per destination.

**Delivery to a broker** and **processing by each consumer** are distinct milestones.

## 15. Schema Evolution and Contract Compatibility

### 15.1. Why Do Events Need `schemaVersion`?

Today's event:

```javascript
{
  eventType: "OrderPaid",
  schemaVersion: 1,
  payload: {
    orderNo: "O-100",
    amountCents: 120000
  }
}
```

Next version adds fields:

```javascript
{
  eventType: "OrderPaid",
  schemaVersion: 2,
  payload: {
    orderNo: "O-100",
    amountCents: 120000,
    currency: "VND",
    paymentMethod: "BANK_TRANSFER"
  }
}
```

A consumer still on v1 can ignore new optional fields if the contract permits. Changing `amountCents` from an integer to a string or altering `status` semantics is a **breaking change** requiring a migration plan.

### 15.2. Evolution Rules

- Adding optional fields with sensible defaults preserves compatibility better than renaming required fields.
- Never reuse one `eventType` for two completely different business meanings.
- Track `schemaVersion` or manage contracts in a schema registry.
- Version schema contracts separately from business aggregate versions to avoid confusion.
- Run consumer contract tests at integration boundaries.
- Store complete payloads in the outbox so events replay cleanly under their original schema.

Treat published events as **immutable history**. Never rewrite historical outbox payloads just to match a new consumer if doing so destroys traceability.

### 15.3. Protecting Sensitive Data

Direct change streams can expose **entire documents** when `fullDocument` is enabled. Before publishing onto shared brokers:

- Whitelist explicitly allowed output fields.
- Minimize PII, access tokens, and payment secrets.
- Encrypt in transit and at rest where appropriate.
- Enforce ACLs on topics/queues and RBAC on MongoDB.
- Enforce tenant isolation in both producers and consumers.
- Define clear retention and deletion policies.

Never grant a consumer access to full database records merely because it needs `OrderPaid` notifications.

### 15.4. Tracing

Include `correlationId` and `eventId` in messages for end-to-end observability:

```text
HTTP request req-42
    |
    v
MongoDB transaction
    |
    +-- order update
    +-- outbox event evt-77
                 |
                 v
             Kafka publish
                 |
                 v
       shipping consumer evt-77
                 |
                 v
             shipment created
```

SREs can then verify from logs and metrics whether an event committed, published, and processed—without guessing from an ambiguous flag.

## 16. Error Management and Replay

### 16.1. Failures at Each Stage

| Stage | Possible Errors | Handling Strategy |
| --- | --- | --- |
| MongoDB business transaction | Validation, write conflict, timeout | Abort/retry per error label; request idempotency |
| Outbox insert | Duplicate event ID, invalid schema | Reconcile `operationId`; never retry blindly |
| Change stream | Network, failover, `invalidate`, history lost | Resume by token when valid; recover/backfill if needed |
| Relay mapping | Payload fails schema check | Quarantine and alert; never skip silently |
| Broker publish | Timeout, unavailable, missing ack | Retry with backoff; never advance checkpoint |
| Checkpoint write | DB error after broker ack | Event may replay; consumer deduplicates |
| Consumer update | DB conflict, validation, duplicate | Classify retry; inbox/idempotency |
| External side effect | HTTP timeout, uncertain email/charge | Idempotency keys and provider reconciliation |
| Broker offset ack | Consumer crashes after processing | Redelivery protected by inbox |

### 16.2. Retryable vs. Non-Retryable

**Retryable** errors include brief network glitches, temporary broker unavailability, transient MongoDB errors, and consumer write contention.

**Do not infinitely retry verbatim**:

- Events missing required fields.
- Unsupported schema versions.
- Business invariant violations.
- Invalid credentials/authorization.
- Duplicate already-processed events.
- Expired resume tokens with lost history.

Set retry budgets, backoff with jitter, dead-letter/quarantine queues, and alerts. For poison messages, maintain a runbook to fix and replay **after resolving the root cause**.

### 16.3. Never Skip Poison Events and Advance Checkpoints Carelessly

Suppose a relay hits an invalid outbox event:

```text
event #100: ok
event #101: invalid payload
event #102: ok
```

"Log #101 and checkpoint #102" risks permanently dropping #101. If policy permits routing invalid events to a **durable quarantine/DLQ**, confirm the quarantine write succeeded and log the replay plan before advancing the checkpoint.

Choose a strict policy by business criticality:

- Halt the pipeline so critical events are never lost.
- Or quarantine durably with explicit confirmation before continuing.
- Never silently discard.

### 16.4. Replaying State Is Not the Same as Re-Executing External Side Effects

Replaying `OrderPaid` makes sense when rebuilding a read model. Yet if a consumer triggers "send payment email" or "charge balance," replays **must not re-execute those side effects** without a new business intent.

Distinguish clearly:

- **Projection rebuild**: recompute read models from historical data.
- **Side-effect replay**: may require neutralizing real-world effects or strict idempotency.
- **Reconciliation**: compare final source and target state and repair drift.

There is no single safe "replay all" button for every consumer.

## 17. End-to-End Observability from Commit to Consumer

### 17.1. Core Metrics

| Metric | Meaning |
| --- | --- |
| `outbox_events_created_total` | Events committed to the outbox |
| `outbox_to_broker_publish_latency` | Delay from commit to broker ack |
| `relay_checkpoint_age_seconds` | Age of relay's persisted progress |
| `relay_publish_failures_total` | Publish failures |
| `relay_resume_attempts_total` | Stream resume/reconnect attempts |
| `resume_token_history_lost_total` | Unresumable history-loss errors |
| `outbox_unpublished_backlog` | Backlog per reconciliation policy |
| `broker_consumer_lag` | Messages awaiting consumers in broker |
| `consumer_duplicate_events_total` | Deduplicated duplicate deliveries |
| `consumer_processing_failures_total` | Business processing failures |
| `dlq_or_quarantine_size` | Events awaiting operator intervention |
| `mongodb_oplog_window_seconds` | Retained history window at source |

These metric names are **suggested application-defined names**, not built-in MongoDB/Prometheus defaults.

### 17.2. Measuring Latency Accurately

Multiple latency legs exist:

```text
T1: MongoDB commits
T2: relay observes change event
T3: broker acks
T4: consumer receives event
T5: consumer commits side effect

T2 - T1 = change stream / relay observation latency
T3 - T1 = end-to-end publish latency
T5 - T1 = business propagation latency
```

Do not lump everything together as "MongoDB replication lag." Change stream latency, broker lag, and consumer processing latency are distinct components.

When comparing timestamps across hosts, clock skew affects measurements; synchronize clocks or rely on single-source/trace timestamps and document metric definitions clearly.

### 17.3. Oplog Window Is a Vital Health Signal

Example:

```text
Oplog window:              12 hours
Relay lagging behind:      10 hours
Estimated headroom:         2 hours
```

If write traffic spikes and shrinks the window, the relay loses resumability. Alert **well before headroom hits zero**, while keeping outbox retention long enough for backfills.

Subtracting checkpoint age from the time window is only an **estimate**; verify exact resume token positions and source sync health.

### 17.4. Runbook During Extended Broker Outages

1. Confirm MongoDB and outbox writes continue normally.
2. Monitor broker producer errors and backpressure.
3. Keep the relay in bounded retry mode, **never advancing checkpoints** without publish acks.
4. Watch the oplog window, outage duration, and outbox retention.
5. Once the broker recovers, monitor backlog drain and duplicate rates.
6. If oplog history expired, switch to reconciliation/backfill.
7. Reconcile business events and consumer state—never rely solely on "relay connected."

## 18. Safe Hands-On Practice with `mongosh` and Node.js

### 18.1. Preparing Test Collections

In `mongosh` connected to a **test replica set**:

```bash
mongosh "mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/?replicaSet=rs0"
```

Address is illustrative. Substitute authorized hosts, TLS, and authentication settings.

```javascript
const lab = db.getSiblingDB("mongo_change_stream_row279_lab");
const orders = lab.getCollection("orders_demo");
const outbox = lab.getCollection("outbox_demo");

const runId = "row279-" + new ObjectId().toHexString();
const orderId = new ObjectId();
const eventId = new ObjectId();

print("database=" + lab.getName());
print("runId=" + runId);
print("orderId=" + orderId);
print("eventId=" + eventId);
```

Example running a small transaction; execute only after verifying the test database is isolated and authorized:

```javascript
const session = db.getMongo().startSession();
const txLab = session.getDatabase(lab.getName());

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  });

  txLab.getCollection("orders_demo").insertOne({
    _id: orderId,
    runId,
    orderNo: "ORDER-279",
    status: "NEW",
    version: 1
  });

  txLab.getCollection("outbox_demo").insertOne({
    _id: eventId,
    runId,
    eventType: "OrderCreated",
    schemaVersion: 1,
    aggregateId: orderId.toHexString(),
    aggregateVersion: 1,
    occurredAt: new Date(),
    payload: {
      orderNo: "ORDER-279",
      status: "NEW"
    }
  });

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (_ignored) {}
  throw error;
} finally {
  session.endSession();
}

printjson(orders.findOne({ _id: orderId, runId }));
printjson(outbox.findOne({ _id: eventId, runId }));
```

Note: on certain versions, creating new collections inside a transaction carries specific rules/restrictions. If `orders_demo` and `outbox_demo` do not exist yet, **create both collections before the transaction** via `createCollection()` in your lab database, then run the transaction on the prepared namespaces. Never create or drop system or production collections to bypass errors. In sharded clusters, transaction DDL and namespaces have additional version-specific rules.

### 18.2. Observing the Change Stream in a Separate Session

To observe **new events**, open a second `mongosh` session connected to the same replica set and test database. Because `watch` waits for events, run the producer **after the watcher starts listening**:

```javascript
const lab = db.getSiblingDB("mongo_change_stream_row279_lab");
const outbox = lab.getCollection("outbox_demo");

const stream = outbox.watch(
  [{ $match: { operationType: "insert" } }],
  { fullDocument: "default" }
);

// Loop awaits events; break intentionally after observing.
for (const change of stream) {
  print("Resume token:");
  printjson(change._id);
  print("Business event ID:");
  printjson(change.documentKey._id);
  printjson(change.fullDocument);
  break;
}

stream.close();
```

Execute a **new** outbox insert from the producer session while the watcher is waiting; if inserted prior to opening the watch, remember streams do not scan pre-existing history. Never deploy this demo loop as a production relay, since it lacks checkpointing, acks, and error handling.

If your environment permits only one shell session, run the Node.js relay and producer script as two separate processes or inspect via monitoring tools—no need to artificially break or delay replication.

### 18.3. Inspecting Resume Tokens Without Altering Them

In watcher output:

```javascript
printjson(change._id);
```

Never do:

```javascript
// Wrong: documentKey is not the token.
const wrongToken = change.documentKey._id;
```

In applications, persist `change._id` using a compatible BSON serializer or type-preserving Extended JSON format. Never convert to custom strings or slice/drop fields.

### 18.4. Cleaning Up Only Your Test Data

In the session holding `runId`, `orderId`, and `eventId` for your test run:

```javascript
print("database=" + lab.getName());
print("runId=" + runId);
printjson(orders.findOne({ _id: orderId, runId }));
printjson(outbox.findOne({ _id: eventId, runId }));
```

Only after confirming both owned documents:

```javascript
const removedOrder = orders.deleteOne({
  _id: orderId,
  runId
});

const removedOutbox = outbox.deleteOne({
  _id: eventId,
  runId
});

printjson({
  orderDeleted: removedOrder.deletedCount,
  outboxDeleted: removedOutbox.deletedCount
});
```

**Note:** deleting test outbox records also emits `delete` change events. In real systems, never delete unpublished outbox events or records still within retention. Never run `deleteMany({})`, `dropDatabase()`, touch `local.oplog.rs` directly, or delete checkpoints of an active relay.

## 19. Architecture Comparison and Trade-Offs

| Attribute | Direct CDC from Business Collection | Transactional Outbox + Change Stream |
| --- | --- | --- |
| Event semantics | Database change | Service-defined domain event |
| Extra outbox collection needed | No | Usually yes |
| Prevents business DB + broker dual-write | Does not solve external side effects alone | Writes business state + event intent atomically in MongoDB |
| Event payload at business commit time | May require reconstruction from updates or lookups | Payload frozen inside transaction |
| Schema coupling | Consumers couple to DB schema | Enables independent event contracts |
| Write overhead | Fewer extra documents | Adds outbox insert/transaction |
| Backfill after oplog loss | Needs external source/state snapshot; may not rebuild all events | Can scan retained outbox events |
| Retention and cleanup | Bound to oplog/snapshot | Must manage outbox lifecycle |
| Multi-consumer fan-out | Via broker/connector | Via broker/connector |
| Default end-to-end exactly-once | No | No |
| Typical use cases | Search index, cache sync, analytics CDC | `OrderPaid`, `PaymentCaptured`, cross-service workflows |

Design conclusion:

- **Use direct change streams** when consumers genuinely need to mirror database state and understand source schemas.
- **Use a transactional outbox** when services must emit **explicit business meaning** and cannot lose events between database writes and publishing.
- **Use an inbox/idempotency in consumers** because outbox relays can still deliver the same event more than once.

## 20. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Updating MongoDB then publishing to Kafka as two separate steps | Crash between steps drops domain events | Transactional outbox |
| Publishing to broker inside a transaction callback | Side effects don't roll back; callback retries duplicate publishes | Write only outbox in transaction; relay publishes post-commit |
| Inferring all domain events from `updateDescription` | Migrations/admin fixes trigger wrong business events | Explicit domain events |
| Treating `change._id` as the business document ID | Confuses resume token with record ID | Use `documentKey._id` / `fullDocument._id` for records |
| Treating `fullDocument: "updateLookup"` as an exact point-in-time snapshot | Payload may reflect later updates | Outbox payload or pre-/post-images per semantics |
| Checkpointing before broker acknowledgement | Can silently drop events | Ack broker first, then checkpoint |
| Assuming crash post-publish never causes duplicates | Resuming replays if checkpoint wasn't saved | Idempotent consumers |
| Deleting expired checkpoints and restarting from "now" | Drops events during outage | Reconciliation/backfill |
| Serializing resume tokens in ways that lose BSON types | Cannot resume | Persist and restore intact BSON |
| Modifying change event `_id` in `watch()` pipeline | Breaks resume semantics | Keep change event `_id` token intact |
| Using only timestamps to identify events | Collisions and wrong ordering | Stable event IDs and aggregate sequences |
| Running two relays on one shared checkpoint without a leader | Duplicate publishes and checkpoint regression | Single owner/lease/fencing or partitioning |
| Confusing Kafka offsets with MongoDB resume tokens | Impossible to reconcile two stages | Manage each checkpoint independently |
| Consumer acks before committing side effects | Crash drops business effects | Commit side effects first, then ack |
| Consumer updates state without checking event versions | Old events overwrite newer state | Per-aggregate ordering/versioning and gap detection |
| Overly short outbox TTL | Outage outlasts backfill data | Size retention to recovery SLO |
| One `published: true` flag for multiple subscribers | Cannot track per-subscriber progress | Broker consumer groups or per-destination state |
| Claiming "exactly-once" from a single successful publish call | Crashes/retries still duplicate | At-least-once + idempotency/reconciliation |
| Replaying payment events like ordinary projections | Risk of double charges or duplicate emails | Idempotency/compensation |
| Opening a change stream per end user | High cursor count and server cost | Shared relay/connector per source/partition |
| Running change streams on standalone `mongod` | Unsupported topology | Replica set or sharded cluster |

## 21. Review Questions and Design Exercises

### Exercise A. Dual-Write and Transactional Outbox

An API creates an order, then calls `publisher.publish()`. MongoDB commits, and the process dies before publishing.

1. Why can the shipping service remain unaware the order was created?
2. How does replacing two independent writes with a transaction writing `orders` + `outbox` help?
3. Why is a separate relay still required?
4. Why isn't single-delivery relay publishing guaranteed merely because the MongoDB transaction succeeded?

### Exercise B. Tokens and Event IDs

A watcher receives:

```javascript
{
  _id: { _data: "opaque-token" },
  documentKey: { _id: "evt-12" },
  fullDocument: {
    _id: "evt-12",
    eventType: "OrderPaid"
  }
}
```

Identify:

- Which field is saved for `resumeAfter`?
- Which field is sent to consumers as the idempotency key?
- If two separate publishes deliver the same `eventId`, what should the consumer do?

### Exercise C. Crash Matrix

A relay publishes `evt-12`, the broker acks, and power drops before saving the checkpoint.

1. Upon restart, can the event be published again?
2. Why shouldn't you checkpoint before publishing to avoid duplicates?
3. How does a consumer inbox help?
4. If the side effect calls a payment gateway, what extra safeguard is needed beyond the inbox?

### Exercise D. Out-of-Order Events

A consumer receives:

```text
OrderShipped v3
OrderPaid v2
```

while its read model sits at `v1`.

- Should it immediately set status `SHIPPED` and process `v2` afterward?
- If the consumer requires a contiguous sequence, how should it handle the gap?
- Which field should serve as the Kafka partition key to aid ordering?
- When is reconciliation needed instead of waiting forever?

### Exercise E. Lost Oplog History

A relay stops for 30 hours. The oplog window holds 8 hours, while outbox retention is 7 days.

1. Why does `resumeAfter` fail?
2. Does retaining outbox records enable recovery?
3. How do you scan the backlog and open the live stream without gaps?
4. Why is `eventId` deduplication essential during backfill?

### Exercise F. Full Document Is Not a Domain Snapshot

An order changes `NEW → PAID`, then rapidly `PAID → SHIPPED`. The relay receives the `NEW → PAID` update event with `fullDocument: "updateLookup"`.

1. Why might `fullDocument.status` be `SHIPPED`?
2. If you must emit `OrderPaid` with the exact `paymentId` at payment time, where should the payload come from?
3. In which cases is direct CDC still a good fit?

### Exercise G. Multiple Consumers

An `OrderCreated` event feeds Shipping, Search, and Analytics.

1. Why does a single `published` flag fail to reflect whether each consumer processed it?
2. How does a broker with consumer groups help?
3. What checkpoints/deduplication does each consumer need?
4. If Analytics needs a rebuild, should notification emails be resent?

### Exercise H. Handling Poison Events

A relay hits an event missing `aggregateId` with hundreds of valid events queued behind it.

1. Why shouldn't you log, skip it, and checkpoint past the broken event?
2. What role does a durable quarantine/DLQ play?
3. Which metrics and alerts are needed?
4. Under what conditions can it replay after fixing the schema?

## 22. References

When implementing, cross-check your **MongoDB server/driver versions** and target broker:

- [MongoDB Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — mechanics, prerequisites, and limits of change streams.
- [Change Events](https://www.mongodb.com/docs/manual/reference/change-events/) — change event fields.
- [Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream) — resume tokens and continuation.
- [Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — before/after images on supporting versions.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity and sessions.
- [Node.js Driver Change Streams](https://www.mongodb.com/docs/drivers/node/current/monitoring-and-logging/change-streams/) — `watch()` API and cursors.
- [Node.js Driver Transactions](https://www.mongodb.com/docs/drivers/node/current/crud/transactions/) — `withTransaction()` and transaction lifecycle.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — retention and history windows.
- [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — source/sink connector integration with Kafka.

These references serve as starting points to verify versions, privileges, read/write concerns, resume behavior, connector mappings, and limits. When using Kafka Connect/Debezium or third-party connectors, consult their specific documentation on snapshot, offset, retry, and deployment semantics.

## 23. Conclusion

**Change streams** provide a clean way to observe MongoDB mutations for near-real-time CDC, yet **a database change is not automatically a domain event**, and the oplog is not a permanent event store. When consumers simply mirror data state, direct CDC suffices; when services must emit explicit business meaning without gaps between persistence and publishing, **transactional outbox** is the right architecture.

The reliable pattern is: **business update + outbox insert in one MongoDB transaction → relay reads change stream → broker acknowledges publish → relay persists resume token → consumer processes idempotently before acking**. Crashes between publish ack and checkpointing trigger replays—manageable via `eventId`/inboxes and the reason not to lightly promise end-to-end exactly-once.

Production designs also require **sufficient outbox retention, gap-free backfills, per-aggregate ordering, schema versioning, least-privilege access, PII protection, lag observability, and oplog-loss runbooks**. The goal is never merely "receiving a change event," but **delivering committed business intent to downstream receivers in a verifiable, recoverable manner without duplicate side effects**.
