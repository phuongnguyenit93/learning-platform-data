# Event Ordering, Duplicate Processing, and Delivery Guarantee Limits of MongoDB Change Streams

## 1. Why Reading an Event Does Not Mean It Was Processed Correctly

MongoDB **Change Streams** allow applications to monitor confirmed changes on a collection, database, or supported deployment scope. A consumer can receive events when documents are inserted, updated, replaced, or deleted, and then update caches, build lookup tables, send notifications, or synchronize data to external systems.

For example, an order management application has a collection:

```javascript
{
  _id: "O-1001",
  customerId: "C01",
  status: "CREATED",
  total: 250000
}
```

An order can go through the following changes:

```text
insert O-1001, status=CREATED
          |
          v
update O-1001, status=PAID
          |
          v
update O-1001, status=SHIPPED
          |
          v
delete O-1001 (if policy permits)
```

A consumer must answer four independent questions:

1. **Ordering:** how do you prevent processing `SHIPPED` before `PAID` and then accidentally overwriting back to `PAID`?
2. **Duplicates:** if `PAID` was already processed, but the connection drops before saving the checkpoint, what happens when the next startup receives that event again?
3. **Dropped events:** if you save the checkpoint before updating the target system and the process crashes, who guarantees the event is not skipped?
4. **Guarantee limits:** do Change Streams provide exactly-once semantics across MongoDB, Kafka, email, and payment systems?

Here are the three pillars of this lesson:

> **Event ordering** is provided by MongoDB within the scope of a single change stream, yet the application must preserve ordering during processing.

> **Resume tokens** let you continue reading from a stream position, yet they do not track the side effects a consumer has already executed.

> **At-least-once, at-most-once, and exactly-once** are properties of the **entire processing pipeline**, not labels you can blindly attach to a `watch()` call.

### 1.1. Lesson Objectives

After this lesson, you will be able to:

- Open a change stream and read `operationType`, `documentKey`, `clusterTime`, and the `_id` resume token.
- Distinguish **cursor delivery order** from **side-effect completion order** across multiple workers.
- Explain why `clusterTime` and `ObjectId` cannot replace a resume token.
- Choose the right order between **processing an event** and **saving a checkpoint**.
- Design **deduplication/idempotency** using stable keys.
- Understand limits of `resumeAfter`, `startAfter`, `startAtOperationTime`, and the **oplog window**.
- Separate event-delivery guarantees from write guarantees to MongoDB or external systems.
- Write a basic consumer in **mongosh** and the **MongoDB Java Sync Driver**.

## 2. What Is a Change Stream and What Are Its Prerequisites?

### 2.1. Watching Changes Instead of Polling a Collection Repeatedly

Without change streams, applications often have to poll:

```javascript
db.orders.find({
  updatedAt: { $gt: lastCheckedAt }
});
```

This approach suffers from several issues:

- `updatedAt` can be forgotten on some updates.
- Multiple updates to the same document between polls collapse together.
- Accuracy depends on clocks and timestamp-update discipline.
- Detecting deletes requires tombstones or separate tracking logic.

A Change Stream is a **stream of change events** backed by MongoDB internals, enabling consumers to observe mutations in stream order without maintaining manual timestamps on every document.

### 2.2. Supported Deployments

Change Streams require a MongoDB deployment with replication capability, typically:

- **Replica set**.
- **Sharded cluster**.

A standalone `mongod` not running as a replica set is not a valid environment for `watch()`. In labs, a **single-node replica set** suffices to practice syntax, though it does not simulate failover or inter-member replication lag.

Change streams observe changes meeting commit/majority criteria per server semantics; they **do not emit uncommitted transaction changes** as finalized business events.

### 2.3. Three Watch Scopes

In `mongosh`:

```javascript
// Single collection.
db.orders.watch();

// Single database: changes across collections in this database.
db.watch();

// Entire deployment scope per supported API/conditions.
db.getMongo().watch();
```

Broader scopes imply higher event volume, filtering cost, and permission exposure. Never open a deployment-wide stream if you only need to refresh a cache for one collection.

### 2.4. A Change Stream Is Not an Infinite Retention Queue

Change Streams rely on change history retained by MongoDB, tied to the **oplog**. Resumability is **bounded by retained history**, not a permanent log like a dedicated event store configured for multi-year retention.

If a consumer stays offline longer than required history remains retained, old checkpoints can no longer resume. You can never assume "passing a token always brings back every missed event."

## 3. Shape of a Change Stream Event

For example, in the `orders` collection, after running:

```javascript
db.orders.updateOne(
  { _id: "O-1001" },
  { $set: { status: "PAID" } }
);
```

A consumer may receive an abridged event like:

```javascript
{
  _id: {
    _data: "8265...opaque-resume-token..."
  },
  operationType: "update",
  clusterTime: Timestamp(1720000000, 1),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: "O-1001"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

**This is an illustrative structural example**, not a valid token or timestamp to copy into an API call. Server version, operation, watch scope, and `watch()` options determine which fields appear.

### 3.1. Fields to Understand

| Field | Meaning | How to Use |
|---|---|---|
| `_id` | **Resume token**, identifying the event's position in the change stream | Persist intact for resuming/checkpointing |
| `operationType` | Change type: `insert`, `update`, `replace`, `delete`, etc. | Route processing branch |
| `ns` | Target database and collection | Identify event source |
| `documentKey` | Key of the modified document, potentially including shard key | Correlate to business entity |
| `clusterTime` | Logical timestamp of the event | Observe/correlate; **never substitute for token** |
| `fullDocument` | Document contents when supplied by operation/options | Build projections where appropriate |
| `updateDescription` | Modified/removed fields on update events | Selective patching or auditing |
| `lsid`, `txnNumber` | May appear for changes inside transactions | Group changes belonging to the same transaction |

An event may carry additional metadata. Never build consumers assuming every event always contains `fullDocument` or `updateDescription`.

### 3.2. Event `_id` Is Not the Order Document `_id`

Example:

```javascript
// _id of the EVENT: resume token, opaque BSON value.
change._id

// _id of the MODIFIED DOCUMENT:
change.documentKey._id
```

Two fields serve two distinct purposes:

- `change._id`: **position of one specific change** in the change stream.
- `change.documentKey._id`: **entity identifier** affected by potentially many changes.

A single order document can have hundreds of distinct events while keeping the exact same `documentKey._id`.

### 3.3. Different Events Can Share the Same `documentKey`

```text
Event E1: update O-1001 status=CREATED
Event E2: update O-1001 status=PAID
Event E3: update O-1001 status=SHIPPED
```

If you deduplicate events solely by `documentKey._id`, the consumer keeps E1 and **drops E2 and E3**. That is a critical bug.

To deduplicate **events**, use a true event identifier such as the **intact resume token** or a source-assigned business/sequence key. To identify **the order**, use `documentKey`.

## 4. Ordering Within a Single Change Stream

### 4.1. Stream Order Provided by MongoDB

When a consumer reads **sequentially** from a single change stream cursor, it receives events in the exact order MongoDB presents for that stream.

Example:

```text
watch(orders)
  |
  +-- E1: insert O-1001
  |
  +-- E2: update O-1001 status=PAID
  |
  +-- E3: update O-1001 status=SHIPPED
```

If the consumer executes:

```text
read E1 -> process E1 -> checkpoint E1
read E2 -> process E2 -> checkpoint E2
read E3 -> process E3 -> checkpoint E3
```

then **processing completion order** matches **cursor read order**.

### 4.2. Does Not Mean Every Consumer Sees and Processes Identically

Keep these distinctions clear:

- A collection stream sees changes only for that collection.
- A database stream can see events across multiple collections.
- A stream with a `$match` pipeline drops filtered-out events.
- Two consumers may start at different positions.
- Two consumers operate at different speeds and checkpoint states.

Therefore, never assume **a single global processing order across all services** merely because all use Change Streams.

### 4.3. Delivery Order Does Not Guarantee Completion Order

Suppose a consumer reads sequentially yet dispatches work to two threads:

```text
Cursor reads:
  E1: status=PAID
  E2: status=SHIPPED

Worker 1 receives E1: takes 900 ms
Worker 2 receives E2: takes 100 ms

Completion order:
  E2 finishes first
  E1 finishes second
```

If both workers execute:

```javascript
db.orderCache.updateOne(
  { _id: "O-1001" },
  { $set: { status: nextStatus } },
  { upsert: true }
);
```

then the final cache value **regresses to `PAID`** even though a newer event already transitioned to `SHIPPED`.

This is a bug in **concurrent application processing**, not evidence that MongoDB emitted events out of order.

## 5. Logical Order vs. Wall-Clock Time

### 5.1. `clusterTime` Is Logical Time

`clusterTime` represents the logical timestamp of a change. It is useful for diagnostics and starting streams in certain cases, but must never be treated as a **unique event ID** or a millisecond-accurate wall-clock timer.

Two events can share the exact same `clusterTime`, especially within a single transaction.

```text
Event A: clusterTime = T, documentKey = O-01
Event B: clusterTime = T, documentKey = O-02

If saving only T as checkpoint:
  Cannot tell whether A, B, or both were processed.
```

### 5.2. Never Use `clusterTime` as the Sole Deduplication Key

Wrong design:

```javascript
// DO NOT use clusterTime as a unique eventId.
const eventId = String(change.clusterTime);
```

This drops distinct events that share the same logical timestamp.

Instead use:

```javascript
const resumeToken = change._id;
```

and persist **the token's BSON value**, without manually parsing or altering `_data`.

### 5.3. Never Sort Events by Business Document `_id`

If an event for order `O-9999` arrives before an event for `O-0001`, sorting by `documentKey._id` scrambles stream order.

Similarly, a document's **`ObjectId`** generated at insert time is not a sequence number for subsequent updates. Never use it to reconstruct mutation order.

### 5.4. `clusterTime` Does Not Guarantee External Side-Effect Ordering

Suppose you forward events to Kafka, email, or HTTP. Even though MongoDB emits events in stream order, target systems can:

- Route across multiple partitions.
- Run parallel consumers.
- Retry slow requests.
- Complete after timeouts in a different order.

To preserve per-entity ordering, enforce **partitioning, sequencing, idempotency, or version checks** at the point of application.

## 6. Ordering in Sharded Clusters

### 6.1. Multiple Shards Generate Multiple Change Sources

In a sharded cluster:

```text
Shard A: A1 -------- A2 -------- A3
Shard B: ----- B1 -------- B2 -----
Shard C: --- C1 ---------------- C2

                |
                v
              mongos
                |
                v
        Change stream cursor
        coordinated / merged
```

MongoDB coordinates event streams across shards to provide a unified order for **a single stream via `mongos`**, using cluster logical ordering and metadata. Applications should rely on **cursor delivery order**, rather than connecting to three shards separately and sorting by `Date.now()`.

### 6.2. Do Not Substitute Per-Shard Streams for One `mongos` Stream

If an application connects directly to each shard and merges events itself, it must solve:

- Synchronizing logical clocks across shards.
- Late-arriving events.
- Concurrent changes across shards.
- Chunk ownership shifts caused by the balancer.
- Per-shard checkpoints and recovery.

To watch a **sharded collection**, use a **Change Stream through `mongos`** via MongoDB's supported APIs.

### 6.3. Migrations Do Not Mean Business Documents Were Updated

When the balancer migrates chunks between shards, that is a data-distribution management operation, not an application `update status` business action on each document.

Never assume every document copied across shards emits a new `insert` event equivalent to an application insert. Consumers should rely on **`operationType` and the change stream contract**, not MongoDB's physical replica/chunk copies.

### 6.4. Adding Shards and Topology Changes

During cluster scaling or migrations, consumers still require:

- Connecting via an appropriate router (`mongos`).
- Version-compatible drivers.
- Reliable resume tokens and checkpoints.
- Monitoring lag and resumability errors.

Never hardcode fixed shard hostnames in business logic to decide which entity an event belongs to.

## 7. Transactions and Events Sharing the Same `clusterTime`

### 7.1. One Transaction Can Modify Multiple Documents

Example money-transfer transaction:

```text
Transaction TX-01:
  update accounts(A)
  update accounts(B)
  insert transferLedger(TR-01)
  commit
```

Upon commit, the change stream emits multiple events corresponding to those changes.

Key points:

- Events from the same transaction **can share one `clusterTime`**.
- Events may carry `lsid`/`txnNumber` metadata to correlate the transaction.
- Never deduplicate by `clusterTime`.
- Never assume "one transaction = one change event."

### 7.2. Events Appear Only After Commit

Uncommitted transaction changes are not exposed as finalized business events. If a transaction aborts, applications do not receive a stream of change events for rolled-back writes.

This is helpful for building projections: the stream emits only changes valid under commit semantics, sparing consumers from rolling back uncommitted operations.

### 7.3. Consumers Still Need Consistency at the Sink

Suppose three events from one transaction go to two workers. Worker A updates account A's cache; Worker B updates account B's cache more slowly.

Briefly, external cache readers observe **an intermediate inconsistent state**, even though the MongoDB transaction committed atomically.

Therefore:

> **Source transaction atomicity does not automatically yield projection atomicity in target systems.**

If projections require multi-entity consistency, process transaction groups together, use a target-side transaction where possible, or use versions/snapshots so readers never observe half-applied state.

## 8. `fullDocument` and the Read-Timing Trap

### 8.1. Update Events Do Not Always Contain the Full Document

An `operationType: "update"` event normally includes `updateDescription`:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O-1001" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

If a consumer needs the full order state, it can open the stream with:

```javascript
db.orders.watch([], {
  fullDocument: "updateLookup"
});
```

### 8.2. `updateLookup` Does Not Guarantee a Point-in-Time Snapshot of the Event

This is a major trap when building caches:

```text
T1: O-1001 becomes status=PAID      -> event E1
T2: O-1001 becomes status=SHIPPED   -> event E2
T3: Consumer processes E1, runs updateLookup
```

When the lookup runs at T3, the returned `fullDocument` can reflect a **newer** state than E1—such as `SHIPPED`—rather than the exact state immediately after update E1. In some cases the document may already be deleted, yielding no lookup result.

Therefore:

- If you only need fields changed in E1, inspect `updateDescription`.
- If near-current state suffices, `updateLookup` may fit.
- If you need **exact document snapshots at event time**, check **change stream pre-/post-images** support, enablement, and retention for your version.
- Never look at `fullDocument` from `updateLookup` and conclude event E1 itself set `SHIPPED`.

### 8.3. Pre-Images and Post-Images

Supporting MongoDB versions can supply:

- **Pre-image:** document before the change.
- **Post-image:** document after the change.

This feature has separate configuration and retention requirements; exact options like `fullDocumentBeforeChange`, `fullDocument`, and modes `whenAvailable`/`required` depend on API and server version.

Pre-/post-images **do not turn Change Streams into a permanent log**. Once images expire under retention policies, consumers can no longer retrieve that history.

## 9. Opening a Change Stream in `mongosh`

### 9.1. Preparing a Test Collection

The lab requires a **replica set** or **sharded cluster** capable of running Change Streams. Commands below use a dedicated database and never touch production collections.

In the first `mongosh` terminal:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");
const orders = labDb.orders277;

// Dedicated lab collection only. Create if missing.
if (!labDb.getCollectionNames().includes("orders277")) {
  labDb.createCollection("orders277");
}

print("Ready for change stream lab");
```

Do not call `drop()` to reset while a change stream is active, as dropping triggers `invalidate` and closes the active stream.

### 9.2. Open the Stream Before Emitting Events

In the `mongosh` terminal connected to your lab MongoDB:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");
const cursor = labDb.orders277.watch(
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

print("Watching orders277. Open another terminal to make changes.");

try {
  while (cursor.hasNext()) {
    const change = cursor.next();

    printjson({
      type: change.operationType,
      documentKey: change.documentKey,
      clusterTime: change.clusterTime,
      resumeToken: change._id,
      updatedFields: change.updateDescription
        ? change.updateDescription.updatedFields
        : undefined
    });
  }
} finally {
  cursor.close();
}
```

`hasNext()` blocks waiting for events; this is expected behavior for an open stream. To stop the lab, interrupt the loop/close the cursor cleanly in your terminal.

### 9.3. Generate Changes from Another Terminal

In a **second terminal**:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");

labDb.orders277.insertOne({
  _id: "O-277-001",
  status: "CREATED",
  total: 250000,
  customerId: "C01"
});

labDb.orders277.updateOne(
  { _id: "O-277-001" },
  { $set: { status: "PAID" } }
);

labDb.orders277.updateOne(
  { _id: "O-277-001" },
  { $set: { status: "SHIPPED" } }
);

labDb.orders277.insertOne({
  _id: "O-277-002",
  status: "CREATED",
  total: 100000
});
```

The consumer receives events in stream order. Do not rely on this example to predict exact BSON token contents or server delivery timing.

### 9.4. When Is a `$match` Pipeline Needed?

Filtering to `insert`/`update` reduces consumer workload:

```javascript
const c = labDb.orders277.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update"]
      }
    }
  }
]);
```

However, a pipeline filtering out `delete` prevents caches from removing deleted entities. When designing pipelines, decide **which change types matter to target state**.

## 10. Resume Tokens: More Reliable Progress Tracking Than Timestamps

### 10.1. Every Event Carries a Token

Each returned event carries `_id` as its **resume token**. Example:

```javascript
const change = cursor.next();
const token = change._id;
```

The token is an **opaque BSON value**. Never:

- Slice the `_data` string manually.
- Compare tokens lexicographically.
- Assume token layouts stay fixed across MongoDB versions.
- Substitute `new ObjectId()` for a token.
- Fabricate a token from `clusterTime`.

### 10.2. Tokens Resume After a Position

Once an application finishes processing event E10 and saves its token, a new stream can open with:

```javascript
const resumed = labDb.orders277.watch(
  [],
  {
    resumeAfter: storedToken,
    fullDocument: "updateLookup"
  }
);
```

`resumeAfter` instructs MongoDB to **continue after the token's position**, not redeliver the event matching that token by default.

**Critical condition:** the token must still be valid/resumable and the stream scope/configuration compatible. It is not an unlimited lifetime ticket.

### 10.3. Where Should Tokens Be Stored?

An application can persist a checkpoint document:

```javascript
{
  _id: "orders-projection-v1",
  namespace: "change_stream_lab277.orders277",
  resumeToken: {
    _data: "opaque BSON token, example only"
  },
  savedAt: ISODate("2026-11-14T04:00:00Z")
}
```

In production, `resumeToken` must store **the actual value returned by the driver**, not a sample string. Ensure your serializer **round-trips BSON types faithfully**; converting tokens into arbitrary JSON strings can drop type metadata or fields.

### 10.4. Checkpoints Are the Consumer's Commitment, Not MongoDB's

A Change Stream **does not know** whether your application finished updating its cache, sending email, or calling an external HTTP endpoint.

MongoDB delivers event E10, but whether the consumer:

- Wrote to the cache,
- Published a message,
- Updated a projection, or
- Persisted a checkpoint,

is **outside MongoDB's lifecycle guarantees**.

Checkpoints must reflect **the exact progress the consumer is ready to stand behind**.

## 11. "Process First — Checkpoint After" Order

This is the standard pattern when prioritizing **zero dropped events**, accepting potential duplicate processing:

```text
Receive event E10
      |
      v
Execute E10 side effect
      |
      v
Side effect confirmed successful
      |
      v
Save resume token of E10
      |
      v
Receive event E11
```

### 11.1. Crash Window Leading to Duplicates

Suppose:

```text
T1: Receive E10.
T2: Write projection for E10 successfully.
T3: Process crashes BEFORE saving E10's token.
T4: Restart with resumeAfter(E9's token).
T5: Receive E10 again.
```

E10 is **processed twice**. This is an **expected** replay under the process-first, checkpoint-after strategy.

If the side effect is:

```javascript
{ $set: { status: "PAID" } }
```

repeating it preserves the same field value.

If the side effect is:

```javascript
{ $inc: { totalPaidOrders: 1 } }
```

repeating it increments the counter twice, corrupting data.

**Conclusion:** post-processing checkpoints prevent intentionally dropping events, yet require idempotency/deduplication so replays never corrupt state.

### 11.2. Understanding At-Least-Once

With durable checkpoints, valid resumption, and retryable consumers, applications can build **at-least-once processing**:

> Uncheckpointed events have an opportunity to be redelivered and reprocessed, so duplicates must be tolerated.

This is a **conditional** property, not an unconditional guarantee that MongoDB holds all events forever. If oplog history expires or a non-resumable error occurs, recovery requires **rebuild/reconciliation**.

## 12. "Checkpoint First — Process After" Order

Some applications try to avoid replays by saving checkpoints first:

```text
Receive E10
      |
      v
Save token E10
      |
      v
Forward E10 downstream
```

### 12.1. Crash Window Leading to Lost Processing

```text
T1: Receive E10.
T2: Checkpoint E10 succeeds.
T3: Process crashes BEFORE writing projection.
T4: Restart with resumeAfter(E10).
T5: Stream continues from E11.
```

E10 is **skipped by the consumer**, even though MongoDB emitted it.

This represents **at-most-once risk by pipeline design**: avoiding duplicate processing at the cost of losing side effects whenever a crash lands between checkpoint and side effect.

### 12.2. "Zero Duplicates" Does Not Mean a Correct System

A projection corrupted by silently missing an update event is often far worse than a replay handled idempotently. Therefore, most applications favor:

```text
process -> durable acknowledge -> checkpoint
```

and design side effects to tolerate safe retries, instead of checkpointing early just to "eliminate duplicate errors."

## 13. Three Delivery Guarantee Levels

### 13.1. At-Most-Once

By consumer design, an event is processed **at most once**, yet may be **skipped** if a crash hits an unsafe window.

Simple pattern:

```text
checkpoint E10
  |
  X crash
  |
E10 side effect never executes
```

At-most-once is unacceptable when every balance update or permission change must reliably take effect.

### 13.2. At-Least-Once

The goal is ensuring every required event is processed **at least once**, given valid replay/recovery.

```text
process E10
  |
  X crash before checkpoint
  |
resume after E9
  |
process E10 one more time
```

Applications must accept duplicates and make operations **idempotent**.

### 13.3. Exactly-Once

"Exactly-once" can mean several different things:

1. **Event delivered once** to a callback.
2. **Side effect in a target database occurs once**.
3. **An entire workflow spanning MongoDB, brokers, HTTP, email, and payment gateways** takes business effect once.

Never conflate these three meanings.

Calling `watch()` and `resumeAfter` **does not provide end-to-end exactly-once**. Achieving any "exactly-once effect" requires defining an **atomicity boundary** and designing checkpoints, side effects, and deduplication around it.

### 13.4. Comparison Table

| Goal | Example Strategy | Remaining Risk |
|---|---|---|
| At-most-once | Save token before side effect | Side effect may be lost |
| At-least-once | Save token after side effect | Processing may be duplicated |
| Effectively-once for one projection | At-least-once + idempotent updates/dedup | Still needs ordering and checkpoint recovery |
| Atomic effect + checkpoint in one MongoDB txn | Commit both in a supported transaction | Covers only operations inside that transaction |
| End-to-end exactly-once across multiple systems | Per-system idempotency protocols, outbox/inbox, reconciliation | Never guaranteed by Change Streams alone |

## 14. Deduplication: Choosing the Right Key

### 14.1. Never Deduplicate by Document Key

Wrong:

```javascript
// DO NOT use orderId as the unique "processed event" key.
const dedupeId = change.documentKey._id;
```

Because one `orderId` receives many valid events over time, this drops all subsequent updates.

### 14.2. Resume Token as Event Identifier

A token identifies **a specific event within a stream**. You can persist the intact BSON token inside an inbox or checkpoint.

Illustrative schema idea:

```javascript
{
  _id: {
    source: "orders-projection-v1",
    token: { _data: "opaque-token-example" }
  },
  processedAt: ISODate("2026-11-14T04:05:00Z"),
  result: "APPLIED"
}
```

This is merely a **schema concept**, not a requirement to extract and concatenate `_data` strings manually.

If hashing to build a compact ID:

- Hash a **deterministic, type-preserving BSON representation**.
- Include namespace/scope/consumer identity if needed.
- Avoid turning an arbitrary library's `token.toString()` into a long-term storage contract.
- Check for and handle hash collisions.

In MongoDB, you can store the raw `BsonDocument` token in a field and enforce a unique constraint on the chosen identifier.

### 14.3. Business Event IDs from an Outbox Can Be Better

When the source application writes an **outbox event**:

```javascript
{
  _id: "EVT-2026-0001",
  aggregateId: "O-1001",
  eventType: "OrderPaid",
  aggregateVersion: 3,
  payload: {
    orderId: "O-1001",
    total: 250000
  }
}
```

consumers can deduplicate using the **business outbox event `_id`**, decoupled from MongoDB's resume token format.

Resume tokens still control **where the change stream resumes**, while `eventId` enforces **business-event uniqueness** downstream.

### 14.4. Deduplication Must Be Atomic

Never write:

```text
if (!processedEvents.contains(eventId)) {
    sendPayment();
    processedEvents.insert(eventId);
}
```

if two workers can check concurrently before either inserts. Both see "unprocessed" and both trigger payments.

You generally need a **unique constraint** or atomic conditional operation—and if side effects reside in MongoDB, a transaction protecting both the marker and target data writes together.

## 15. Idempotent Updates: Safe Under Repeated Application

### 15.1. `$set` to Fixed Values

A projection updating status:

```javascript
db.orderProjection277.updateOne(
  { _id: "O-1001" },
  {
    $set: {
      status: "PAID",
      total: 250000
    }
  },
  { upsert: true }
);
```

Re-running **the exact same operation** on the same document leaves those fields at the same values.

Yet keep two caveats in mind:

1. If an older event runs **after a newer event**, `$set` regresses state.
2. If each retry also calls an external API, sends email, or sets `updatedAt = new Date()`, **the overall workflow** no longer has identical effects.

Thus **idempotency against duplicates** and **ordering against stale writes** are two separate requirements.

### 15.2. `$inc` Is a Classic Non-Idempotent Operation

```javascript
db.dailyMetrics277.updateOne(
  { _id: "2026-11-14" },
  { $inc: { paidOrders: 1 } },
  { upsert: true }
);
```

If `OrderPaid` replays twice, `paidOrders` jumps from 10 to 12 instead of 11.

Options:

- Atomically deduplicate by `eventId`/token before incrementing.
- Recompute counts from the source of truth where feasible.
- Maintain a materialized view with checkpointing/versioning and recovery.
- Design an outbox/inbox with unique event IDs.

### 15.3. Dedupe Marker and Counter in One Transaction

If both collections live in the same transaction-capable MongoDB deployment:

```text
Target DB Transaction:
  1. Insert processedEvents[eventId] (unique)
  2. $inc dailyMetrics
  3. Update consumer checkpoint
  4. Commit
```

If `eventId` already exists, skip incrementing. If the transaction aborts, the marker, counter, and checkpoint all roll back together.

This achieves **exactly-once effect within the MongoDB transaction boundary** when designed properly, though it does not cover external emails or HTTP calls.

## 16. Checkpoints and Side Effects in the Same MongoDB Transaction

### 16.1. Goal

Instead of:

```text
Write projection -> Write checkpoint
```

which leaves a **crash window** in between, we want:

```text
Begin transaction
  +-- Apply event to projection
  +-- Save checkpoint
Commit
```

If the transaction commits, **both** take effect; if it aborts, **neither** does.

### 16.2. Prerequisites

Verify that:

- Projection and checkpoint reside in a MongoDB deployment supporting transactions.
- All related writes execute **within the same session/transaction**.
- Appropriate write concern is configured at commit.
- Replay/concurrency protections exist when parallel consumers run.
- External side effects are never placed inside the transaction assuming they will roll back.

The change stream cursor is **read outside the transaction**; the transaction wraps **writing results and checkpoint**, never opening `watch()` inside a transaction.

### 16.3. Processor Pseudocode

```text
cursor = watch(source, resumeAfter = durableCheckpoint)

for each event E, in order:
    begin transaction on target MongoDB

    if E.id not yet in inbox:
        apply E to projection
        insert inbox[E.id]

    update checkpoint = E.resumeToken
    commit transaction

    // Only after commit succeeds or is reconciled:
    // consider E's checkpoint durably advanced.
```

In practice, if commit returns **unknown commit result**, never blindly launch a new transaction containing non-idempotent side effects. Retry commit/reconcile per driver guidelines and event ID.

### 16.4. Shared Checkpoints Across Multiple Consumers

If two processes both read and write:

```text
Consumer A: processes E10 slowly
Consumer B: processes E11 quickly, checkpoints E11
Consumer A: writes checkpoint E10 afterward
```

The checkpoint **regresses** from E11 back to E10. On restart, unexpected replays occur; non-idempotent side effects corrupt data.

Options:

- Single consumer owner per stream/partition.
- Leases/leadership with fencing tokens blocking stale owners from writing.
- Sequential checkpointing in read order.
- Advancing checkpoints only after **all preceding events have completed**, even under parallel execution.

Never compare resume tokens as strings to decide which event is "greater."

## 17. Parallel Processing While Preserving Per-Entity Order

### 17.1. Global Order vs. Throughput

Sequential event processing keeps ordering trivial, yet bottlenecks if downstream writes are slow. Running 20 parallel workers boosts throughput while breaking **completion order**.

### 17.2. Partitioning by Business Key

Design:

```text
               Change Stream Cursor
                        |
               Dispatch by orderId
                        |
           +------------+------------+
           |            |            |
        Partition 0  Partition 1  Partition 2
          (FIFO)       (FIFO)       (FIFO)
           |            |            |
         Worker       Worker       Worker
```

Rules:

- Events for the **same `orderId`** go to the **same partition**.
- Each partition processes events sequentially in arrival order.
- Distinct `orderId`s run in parallel.

Example:

```text
E1 order=A -> partition 0
E2 order=B -> partition 1
E3 order=A -> partition 0

Partition 0: E1 -> E3 in order.
Partition 1: E2 runs independently.
```

### 17.3. Checkpoint Trap When Partitions Run at Different Speeds

Suppose the stream reads:

```text
E1(A), E2(B), E3(A), E4(C)
```

Partition for E4 finishes while E2 lags behind. **Never checkpoint E4 as though E1..E4 all finished**, because a crash would skip E2.

A **checkpoint coordinator** must track completed events and publish only the **contiguous completed prefix**:

```text
Done: E1=yes, E2=no, E3=yes, E4=yes
Safe checkpoint: E1

Once E2 finishes:
Done: E1=yes, E2=yes, E3=yes, E4=yes
Safe checkpoint: E4
```

This is why parallel event processing is far more involved than replacing a `while` loop with `parallelStream()`.

### 17.4. Transferring Partition Ownership

When scaling from three to four workers, an entity can migrate between partitions. If the old worker is still processing while the new worker applies the next event, ordering breaks.

Always **drain/stop the old owner**, enforce fencing, or execute an ordered offset handoff before reassigning a key to a new owner.

## 18. Using Entity Versions to Stop Stale Events from Overwriting Newer Ones

### 18.1. Add `version` to Business Documents

A document can carry:

```javascript
{
  _id: "O-1001",
  status: "PAID",
  version: 3
}
```

Each business change increments `version` atomically.

The projection also stores the applied version:

```javascript
{
  _id: "O-1001",
  status: "PAID",
  sourceVersion: 3
}
```

### 18.2. Apply Only Newer Versions

Pseudocode:

```text
if event.sourceVersion > projection.sourceVersion:
    write new state
else:
    skip stale/duplicate event
```

This condition must execute **atomically at write time** when multiple workers exist; never merely read and compare in RAM.

### 18.3. What Does Versioning Solve?

- Event version 4 finishes before version 3 → version 3 cannot regress state.
- Event version 4 replays → version 4 is already applied, ignored.
- Consumer restarts and receives older events → stale events are rejected.

However, versioning **does not tell you** whether version 2 was skipped if you observe version 1 followed by version 3. If business logic requires processing **every intermediate step** (e.g., invoicing each payment), check sequence gaps or process by individual event ID.

### 18.4. Change Streams Do Not Generate Business Versions

Resume tokens and `clusterTime` must never be turned into entity version numbers via string comparison.

If an application needs entity versions, the source writer must define and increment them alongside business mutations.

## 19. `resumeAfter`, `startAfter`, and `startAtOperationTime`

### 19.1. `resumeAfter`

Opens a stream **after the token** of a valid event/position:

```javascript
const stream = labDb.orders277.watch(
  [],
  { resumeAfter: checkpoint.resumeToken }
);
```

This is the natural option when a consumer has checkpointed a completed event and wants to continue.

### 19.2. `startAfter`

`startAfter` also starts after a token, with a special capability: **it can open a new stream after an `invalidate` event** under MongoDB's supported conditions.

```javascript
const stream = labDb.orders277.watch(
  [],
  { startAfter: invalidateResumeToken }
);
```

Never pass `resumeAfter` to continue **past an `invalidate` event** as if it were normal; after `invalidate`, evaluate `startAfter` and namespace/scope boundaries.

### 19.3. `startAtOperationTime`

Starts from an operation-time anchor where supported:

```javascript
const stream = labDb.orders277.watch(
  [],
  {
    startAtOperationTime: savedOperationTime
  }
);
```

Prerequisites:

- `savedOperationTime` must be a valid BSON Timestamp, not an arbitrary JavaScript Date.
- Required oplog history must still exist.
- It **does not replace per-event tokens** for exact checkpointing, since multiple events can share the same logical time.

### 19.4. Never Mix Positioning Options Arbitrarily

`resumeAfter`, `startAfter`, and `startAtOperationTime` are **distinct ways to specify a start point**. Never supply conflicting options together expecting MongoDB to pick "the best one."

### 19.5. Persisting Tokens When Events Are Filtered Out

Suppose a stream pipeline keeps only `operationType: "update"`. `insert` and `delete` events never reach the application. If the consumer saves only the token of the latest matching update, its checkpoint lags behind during long stretches without matching updates.

Drivers/cursors can provide a **post-batch resume token** indicating stream progress even across non-matching batches. When using this token:

- Understand your driver version and API semantics.
- Persist it only after **all prior delivered events needing work** have completed.
- Never "jump" the token ahead while earlier events remain running concurrently.

Never fabricate a post-batch token from `Date.now()`.

## 20. When Is Resuming No Longer Possible?

### 20.1. Oplog History Rolled Over

If a consumer saved token E100 and stayed offline too long, MongoDB may no longer retain the history needed to resume from E100. On resume, the server/driver reports a **change stream history lost** or non-resumable error.

```text
Oplog retains: E800 ... E999

Consumer checkpoint: E100

resumeAfter(E100)
    |
    X Required history is gone.
```

**Never attempt to fix this by retrying the same token forever.** Once history is lost, execute a state recovery plan: **rebuild projection, capture a new snapshot, or reconcile**.

### 20.2. Invalidation

Structural namespace changes such as dropping or renaming a collection can emit `invalidate` and close collection-scoped streams. Never assume the old cursor will keep receiving events forever.

Applications must decide:

- Should we watch the new/recreated collection?
- Must the projection be rebuilt?
- Should we open a fresh stream after `invalidate` using `startAfter`?
- Do schema or namespace changes require a consumer migration?

### 20.3. Changing Pipelines or Watch Scope

A token saved under a collection-level stream cannot simply be reused arbitrarily across a database/cluster watch or a completely rewritten pipeline.

When upgrading consumers:

- Record **stream scope and pipeline version**.
- Verify resume token compatibility.
- Decide whether newly added event types need historical backfill.
- Prepare a rebuild/backfill plan whenever semantics change.

### 20.4. Non-Resumable Errors

Drivers automatically resume **certain transient errors** per specification. However, not every exception is resumable, and drivers are not responsible for infinite application-level retries.

Structure explicit handling branches:

```text
RESUMABLE_ERROR   -> driver retry/resume + backoff
NON_RESUMABLE     -> halt pipeline, alert, investigate
HISTORY_LOST      -> trigger rebuild/reconciliation workflow
SCHEMA_ERROR      -> fix consumer or data; never skip silently
```

Never wrap everything in a `try/catch` that swallows failing events just to keep the process "alive."

## 21. Initial Snapshots and Change Streams: The "Read First, Watch Later" Problem

### 21.1. Change Streams Do Not Emit Pre-Existing State

If a collection already holds one million orders before enabling a consumer, calling:

```javascript
db.orders.watch();
```

does not emit one million `insert` events for historical documents.

Building a **new projection** typically requires:

1. Capturing an initial snapshot/state.
2. Tracking changes occurring while the snapshot runs.
3. Applying changes cleanly without drops or duplicates.

### 21.2. Anti-Pattern: Scan First, Then Start Watching

```text
T0: Scan entire orders collection to warm cache.
T1: Mid-scan, O-1001 updates to PAID.
T2: Scan finishes.
T3: Open watch() starting from current time.
```

If the T1 change missed the snapshot scan and occurred **before the watch start position**, the cache loses it permanently.

### 21.3. Bootstrapping with an Explicit Starting Boundary

General workflow:

```text
Choose reliable resumable start point / marker
                |
                v
Open or record Change Stream position
                |
                v
Capture source snapshot under proper consistency
                |
                v
Apply snapshot to projection
                |
                v
Replay changes from the recorded start point
                |
                v
Transition to live consumption + checkpointing
```

The start position and application order must guard against race conditions; merely "opening the stream first and blindly writing cache" is not automatically safe.

### 21.4. Preventing Stale Snapshots from Overwriting Newer Events

During bootstrap, if a live event updates an entity and a slower snapshot record for that same entity arrives afterward, the projection regresses.

Mitigations:

- Apply the snapshot completely before replaying buffered events within retained history.
- Attach source versions and perform conditional updates.
- Follow a rigorous snapshot-consistency and high-watermark protocol.

Snapshotting and event replay must be **coordinated as one consistent workflow**, not two uncoordinated concurrent writers.

## 22. Handling Delete, Replace, and Other Event Types

### 22.1. `insert`

Events include `fullDocument` for the new document. Consumers create the corresponding projection:

```javascript
{
  operationType: "insert",
  documentKey: { _id: "O-1001" },
  fullDocument: {
    _id: "O-1001",
    status: "CREATED"
  }
}
```

### 22.2. `update`

Normally carries `updateDescription`; depending on design, consumers:

- Patch the existing projection, provided rules and ordering are guaranteed.
- Or refresh state from the source after the event.
- Or use post-images when supported and enabled.

Never blindly patch a document that was deleted and recreated with the same ID without versioning or lifecycle handling.

### 22.3. `replace`

A `replace` event replaces the whole source document; consumers must not simply merge new fields onto old projections if removed fields must disappear.

```text
Before:  { status:"PAID", note:"old" }
Replace: { status:"SHIPPED" }

A faithful projection after replace must not accidentally
keep note:"old" once removed from the source document.
```

### 22.4. `delete`

Delete events include `documentKey` but omit the deleted document body by default.

If a consumer watches only `insert` and `update`, caches retain **deleted documents** forever. You can:

- Delete the projection by document key.
- Write a tombstone if history or stale-event resurrection protection is needed.
- Enable pre-images if business rules require pre-delete attributes.

### 22.5. DDL / `invalidate`

Operations like collection rename/drop or structural events impact the stream and require explicit handlers. Consumers must never skip unknown `operationType`s and blindly advance checkpoints when doing so corrupts projection schemas.

## 23. Java Sync Driver: Reading a Change Stream and Capturing Tokens

### 23.1. Simple Consumer Example

The Java code below illustrates a **sequential consumer** printing events and saving resume tokens **after processing** via an application-implemented helper. It does not automatically provide exactly-once.

```java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.BsonDocument;
import org.bson.Document;

public class OrdersChangeStreamConsumer {

    public static void main(String[] args) {
        // Replace with real seed list, replicaSet, TLS/auth for your deployment.
        String uri = "mongodb://localhost:27017/?replicaSet=rsLab";

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                .getDatabase("change_stream_lab277")
                .getCollection("orders277");

            BsonDocument checkpoint = loadCheckpoint();

            ChangeStreamIterable<Document> stream = orders.watch()
                .fullDocument(FullDocument.UPDATE_LOOKUP);

            if (checkpoint != null) {
                stream = stream.resumeAfter(checkpoint);
            }

            try (MongoCursor<ChangeStreamDocument<Document>> cursor =
                     stream.iterator()) {

                while (cursor.hasNext()) {
                    ChangeStreamDocument<Document> change = cursor.next();

                    // Processing may be invoked again on crash/replay.
                    // Handler must enforce idempotency and ordering.
                    processEvent(change);

                    BsonDocument token = change.getResumeToken();
                    saveCheckpoint(token);
                }
            }
        }
    }

    private static BsonDocument loadCheckpoint() {
        // Example: load BSON resumeToken field from checkpoint collection.
        // Return null if the consumer has no checkpoint yet.
        return null;
    }

    private static void saveCheckpoint(BsonDocument token) {
        // Implement durable persistence appropriately.
        // Illustrative stub does not persist checkpoints.
    }

    private static void processEvent(
            ChangeStreamDocument<Document> change) {
        System.out.println(
            change.getOperationType() + " " +
            change.getDocumentKey());
    }
}
```

### 23.2. Understanding the Code

- `orders.watch()` opens the collection stream.
- `fullDocument(FullDocument.UPDATE_LOOKUP)` requests current document lookup where appropriate; not guaranteed to be the exact post-image of an update event.
- `resumeAfter(checkpoint)` is called only when a prior token exists.
- `change.getResumeToken()` provides the token to checkpoint.
- `processEvent()` must finish before `saveCheckpoint()` under at-least-once semantics.

**Intentional limitation:** the two persistence helpers above are stubs to implement. Never copy this snippet and assume checkpoints are durably saved per production policy.

### 23.3. When Should You Use `tryNext()`?

Cursor APIs support non-infinite polling via `tryNext()`, letting consumers check shutdown flags or run periodic housekeeping.

However, tight-loop polling burns CPU and network bandwidth. Use `maxAwaitTime`, backoff, and proper driver APIs rather than spinning in a tight `while(true)` loop.

### 23.4. Exceptions and Driver Auto-Resume

Drivers automatically handle **certain resumable errors**. Applications must still:

- Persist durable checkpoints.
- Monitor non-resumable/history-lost errors.
- Configure backoff, deadlines, and restart policies.
- Never catch all exceptions and silently recreate a stream from "now," losing events.
- Never checkpoint a token if `processEvent()` threw an exception.

## 24. MongoDB Checkpoint Example

### 24.1. Dedicated Checkpoint Collection

In the lab database:

```javascript
const labDb = db.getSiblingDB("change_stream_lab277");
const checkpoints = labDb.consumerCheckpoints277;
```

Schema:

```javascript
{
  _id: "orders-projection-v1",
  namespace: "change_stream_lab277.orders277",
  resumeToken: /* BSON token returned by a real change event */,
  savedAt: ISODate("2026-11-14T04:00:00Z")
}
```

This is a **conceptual representation**; do not copy comment syntax verbatim into `insertOne` expecting a valid token.

### 24.2. Saving the Checkpoint After an Event

Inside the event handler:

```javascript
function saveTokenAfterSuccess(change) {
  checkpoints.updateOne(
    { _id: "orders-projection-v1" },
    {
      $set: {
        namespace: "change_stream_lab277.orders277",
        resumeToken: change._id,
        savedAt: new Date()
      }
    },
    { upsert: true }
  );
}
```

Invoke this **only after** the corresponding side effect succeeds and is acknowledged.

### 24.3. Reading the Checkpoint on Restart

```javascript
const stored = checkpoints.findOne({
  _id: "orders-projection-v1"
});

const options = {};
if (stored && stored.resumeToken) {
  options.resumeAfter = stored.resumeToken;
}

const cursor = labDb.orders277.watch([], options);
```

In production, add stream configuration versions, ownership/fencing, and history-loss handling. Never use this bare logic if competing consumers write to the same checkpoint.

### 24.4. A Checkpoint Collection Does Not Create Atomicity on Its Own

```text
processEvent()
saveCheckpoint()
```

remain **two separate operations** unless wrapped inside a supporting transaction boundary. Crashing between them still produces duplicates.

This is not a MongoDB bug—it is a fundamental property of two non-atomic steps.

## 25. Writing to Kafka, Email, or HTTP: Guarantees Stop at System Boundaries

### 25.1. Change Stream -> Kafka

A bridge:

```text
MongoDB Change Stream
          |
          v
       Producer
          |
          v
     Kafka topic
          |
          v
   Kafka consumer
          |
          v
  Target DB / email
```

Multiple acknowledgements and checkpoints exist:

1. Change Stream resume token.
2. Producer acknowledgement from Kafka.
3. Consumer's Kafka offset.
4. Side effects in the target database, email, or HTTP service.

Saving the token before Kafka producer acknowledgement risks **losing messages**. Saving after producer success risks **duplicate publishes** if the bridge crashes before checkpointing.

Kafka offers its own idempotent producer and transactional features, yet **it does not merge MongoDB and Kafka into one distributed atomic transaction**.

### 25.2. Change Stream -> Email

```text
E1: OrderPaid
  -> email sent successfully
  -> crash before checkpoint
  -> replay E1
  -> send email a second time?
```

Email services rarely participate in transactions with MongoDB. You need:

- A stable `notificationId`/`eventId`.
- A delivery-status table or outbox/inbox.
- Deduplication at the mail provider if supported.
- Reconciliation for ambiguous delivery states.

Never promise "emails are sent only once" merely because Change Stream events carry resume tokens.

### 25.3. Change Stream -> Payment Gateway

For money movement, never write directly:

```text
on event OrderPaid:
    chargeCard()
```

without an idempotency key. Replaying the event charges the customer twice. Payment APIs require a **unique business transaction key** and status verification before issuing new charge requests.

### 25.4. Transactional Outbox as a Design Pattern

If the application writes both the order and an outbox record inside **one MongoDB transaction**:

```text
MongoDB transaction:
  update order.status = PAID
  insert outbox { eventId: "PAY-1001", type:"OrderPaid" }
  commit

Change Stream watches outbox
  -> publisher dispatches event
  -> downstream consumer deduplicates by eventId
```

The outbox prevents lost messages by tying business state and event creation atomically. Still, the publisher can dispatch an outbox record more than once, so downstream consumers still need idempotency.

## 26. Backpressure: Consumer Slower Than Change Rate

### 26.1. The Lag Math

Source generates 5,000 changes/sec while the consumer processes 1,000 events/sec.

```text
MongoDB generates:   5,000 events/s
Consumer processes:  1,000 events/s
Deficit:             4,000 events/s
```

The consumer falls steadily further behind. Change Streams are not an infinitely buffered queue; once the backlog exceeds the **oplog history window**, crash recovery via resume breaks.

### 26.2. Metrics to Track

- **Lag** between source progress and consumer checkpoint, measured cleanly.
- **Event processing rate** and p95/p99 handler latency.
- **In-flight/queued event count**.
- **Checkpoint age** and last commit time.
- **Source oplog window**.
- **Resume errors**, non-resumable errors, and invalidations.
- Retry, deduplication, and dead-letter counts.
- Downstream errors, network latency, and connection pool saturation.

Never compute lag naively as `Date.now() - clusterTime` and treat it as an exact figure in all situations: `clusterTime` is a logical timestamp and traffic may be bursty.

### 26.3. Mitigations

- Optimize handlers and indexes on the target database.
- Use controlled batching where semantics allow.
- Partition by key and process concurrently **while keeping a safe checkpoint prefix**.
- Scale downstream sink capacity.
- Trim unnecessary fields in `fullDocument`/pipelines.
- Slim outbox/log payloads if events are overly heavy.
- Prepare rebuild procedures for history overruns.

Never increase concurrency to the point of breaking per-entity order or advancing checkpoints past in-flight events.

## 27. Changes You Must Not "Skip and Checkpoint"

### 27.1. Unrecognized Event Schemas

Suppose a consumer recognizes `PAID` and `SHIPPED`, and the source begins emitting:

```javascript
{ status: "PARTIALLY_REFUNDED" }
```

If code silently skips unknown statuses and checkpoints past them, projections become **permanently wrong**.

Instead:

- Log with event and correlation IDs.
- Classify schema errors explicitly.
- Halt or route to retry/review queues per policy.
- Never advance checkpoints past a **mandatory** event that failed processing.

### 27.2. Delete Events Without `fullDocument`

If a handler accesses `fullDocument._id` unconditionally, delete events without `fullDocument` crash it.

Use `documentKey` to identify deleted entities and branch cleanly on `operationType`.

### 27.3. Poison Events

One event repeatedly crashes the handler:

```text
E9 succeeds
E10 schema error, fails every attempt
E11, E12 unprocessed
```

Resuming after E9 and retrying E10 forever stalls the consumer. Yet skipping E10 and checkpointing E12 loses critical data.

Establish a **dead-letter, manual review, and reconciliation policy** scaled to event criticality, preserving full evidence and replay capability. There is no universal "always skip" rule.

## 28. When Multiple Services Share the Same Stream Source

### 28.1. Each Consumer Has Its Own Goal

Example:

```text
orders Change Stream
   |
   +--> SearchIndexer
   +--> AnalyticsProjection
   +--> NotificationService
```

Each service has:

- Different event filters.
- Different processing speeds.
- Different side effects.
- Its own checkpoint.
- Its own rebuild strategy.

Never let all three services share one `"orders-latest"` checkpoint document. If `AnalyticsProjection` runs faster than `SearchIndexer` and overwrites the shared token, `SearchIndexer` **drops events**.

### 28.2. Consumer Groups and Ownership

With multiple instances of **the same logical consumer**, decide:

- Either one leader reads the stream while others stay standby,
- Or a dispatcher distributes events to workers partitioned with per-key ordering.

Opening three identical streams on three instances **does not load-balance**: all three receive every event and execute side effects three times.

### 28.3. Fencing Stale Owners

An instance can lose its lease while an old handler thread is still running. If a new instance starts concurrently, both overwrite each other.

Safe leadership requires **fencing tokens/epochs** or conditional writes so a deposed owner cannot keep checkpointing or mutating projections after ownership transfers.

## 29. How to Recover When Events Are Truly Lost

### 29.1. Never Fabricate a Fresh Token to "Bypass Errors"

Wrong approach upon history loss:

```text
resumeAfter(oldToken) -> error
watch() from now -> continue silently without alerting
```

Between `oldToken` and "now", **huge numbers of changes may have been missed**. The projection silently drifts out of sync indefinitely.

### 29.2. Rebuilding Projections

If a projection can be recomputed completely from current MongoDB state:

1. Flag history loss and stop advertising stale state as authoritative.
2. Build a new staging projection.
3. Bootstrap a snapshot coordinated cleanly with a Change Stream starting anchor.
4. Replay changes occurring during the snapshot.
5. Reconcile counts, checksums, and critical fields.
6. Cut over to the new projection once validated.
7. Persist the new checkpoint with matching scope and pipeline version.

### 29.3. When Rebuilding from Current State Is Insufficient

Some event meanings **cannot be reconstructed from final state alone**, such as:

- Emitting an independent event for every successful payment.
- Auditing every single state transition on an order.
- Tracking every dispatched email.

If the source stores only current state and change stream history expired, **historical events cannot be rebuilt** from a live snapshot.

Such workloads require an **outbox, event log, or ledger with independent retention**, backups, or recoverable historical archives. Change Streams distribute mutations; they are not an all-purpose permanent event store.

## 30. Misconceptions to Avoid

| Misconception | Correct Understanding |
|---|---|
| Change Streams always deliver events once | Replays happen after restarts, network errors, or pre-checkpoint crashes |
| Sequential cursor reads guarantee sequential worker completion | Concurrent workers can reorder completions |
| `clusterTime` is a unique event ID | Multiple events, especially in transactions, share `clusterTime` |
| `documentKey._id` deduplicates all changes | One document undergoes many valid events |
| Resume tokens are sortable strings | Tokens are opaque BSON; never compare arbitrarily |
| MongoDB tracks whether emails were sent | External side effects are managed by the application |
| Checkpointing first avoids both duplicates and drops | Creates a crash window that drops processing |
| Checkpointing after guarantees zero duplicates | Creates a crash window that causes replays |
| Repeating `$inc` is harmless | Increments counters twice |
| Idempotent `$set` needs no ordering | Older events can overwrite newer state |
| `updateLookup` returns exact per-event post-images | May return newer state or null |
| Every MongoDB transaction emits one event | Transactions emit multiple change events |
| Atomic source txns make external caches atomic | Consumers apply individual events at different times |
| Drivers retry every error forever | Only eligible resumable errors, within limits |
| Oplogs retain history indefinitely | Resumability is bounded by retained history |
| `resumeAfter` works after any `invalidate` | `startAfter` handles resumption after `invalidate` |
| `Date.now()` works as a complete checkpoint | Drops or duplicates events; cannot replace tokens |
| On history loss, reopening from "now" suffices | Leaves unrecoverable data gaps |
| Multiple instances watching the same collection load-balance automatically | Every instance receives every event |
| Checkpointing the newest read token is always safe | Earlier in-flight events may not be finished |
| Balancer chunk moves emit business insert events per copy | Migration is metadata/distribution, not a business insert |
| Deduplicating an event guarantees all side effects ran | Requires atomicity and downstream verification |
| Change Streams replace long-term audit systems | Oplog retention is finite; build dedicated audit logs |
| MongoDB-level exactly-once extends to Kafka and payments | Each system has separate transactions, acks, and idempotency |

## 31. Practice Exercises

### Exercise 1 — Identifying Event Fields

Given:

```javascript
{
  _id: { _data: "opaque" },
  operationType: "update",
  clusterTime: Timestamp(1720000000, 2),
  documentKey: { _id: "O-001" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  }
}
```

Answer:

1. Which field is the **resume token**?
2. Which field identifies the **order**?
3. Which field describes the operation type?
4. Can `clusterTime` be used as a unique ID?
5. Why should you not parse the `_data` string manually?

### Exercise 2 — Read Order vs. Completion Order

The cursor delivers:

```text
E1: O-001 status=PAID
E2: O-001 status=SHIPPED
```

Worker A processes E1 in 900 ms; Worker B processes E2 in 100 ms.

- If both execute `$set` on `status` in the same projection, what can the final state be?
- Why is this not a MongoDB ordering bug?
- Propose two ways to preserve accurate state: per-key sequential processing or conditional versioning.

### Exercise 3 — Checkpoint First and Crash

Timeline:

```text
T1: receive E10
T2: save checkpoint E10
T3: crash
T4: restart resumeAfter E10
```

Was E10 applied to the projection? Can it be redelivered under this resume? What at-most-once risk does this expose?

### Exercise 4 — Checkpoint After and Crash

Timeline:

```text
T1: receive E10
T2: $inc dailyMetrics by 1
T3: crash before saving checkpoint E10
T4: restart resumeAfter E9
T5: receive E10 again
```

Explain:

- How many times can the counter increment?
- Why is this an expected replay under at-least-once?
- How do unique event IDs + transactions prevent double-counting?

### Exercise 5 — Broken Deduplication by `documentKey`

Order `O-001` has three events:

```text
E1: CREATED
E2: PAID
E3: SHIPPED
```

A consumer saves `processedOrders = { "O-001" }` after E1 and drops all subsequent events sharing that order ID.

What is the bug? Distinguish **entity identity** from **event identity** and propose a valid deduplication key.

### Exercise 6 — Two Events Sharing `clusterTime`

Transaction TX updates accounts A and B, then inserts a ledger record. All three change events share `clusterTime`.

Why is checkpointing only a logical timestamp insufficient per event? How do resume tokens help? Why doesn't source transaction atomicity guarantee caches on two workers update simultaneously?

### Exercise 7 — `updateLookup` and Newer State

```text
10:00 E1: O-001 status=PAID
10:01 E2: O-001 status=SHIPPED
10:02 Consumer calls updateLookup for E1
```

Which state can E1's `fullDocument` reflect? If you need the exact post-image immediately after E1, which MongoDB feature applies? Why shouldn't `updateLookup` be used for full auditing?

### Exercise 8 — `resumeAfter` and `startAfter`

1. When a consumer holds the token of the last processed update event, which option should it use?
2. After an `invalidate` caused by collection drop/rename, which option can start a new stream where supported?
3. Why can't a token whose oplog history expired be resumed directly?
4. How does `startAtOperationTime` differ from a per-event token?

### Exercise 9 — Parallel Workers and Checkpoint Prefix

The cursor reads:

```text
E1(A), E2(B), E3(A), E4(C), E5(D)
```

Status:

```text
E1 done
E2 in-flight
E3 done
E4 done
E5 done
```

Which event holds the safest checkpoint to avoid skipping in-flight work? Once E2 finishes, how far can the checkpoint advance? Explain the coordinator mechanism.

### Exercise 10 — Two Independent Consumers

`SearchIndexer` and `NotificationService` both watch `orders`:

- `SearchIndexer` processed through E100.
- `NotificationService` reached only E60.

Why shouldn't they share **one common checkpoint E100**? How should you name checkpoints per consumer and scope?

### Exercise 11 — Projection and Deletes

A consumer watches only `insert` and `update`; later, order `O-001` is deleted from the source collection.

What goes wrong in the projection? Add a `delete` branch using `documentKey` and explain when tombstones are preferable to physical deletes.

### Exercise 12 — History Loss After a Week Offline

A consumer checkpoints E100. The oplog now starts at E500. The application receives an error saying it cannot resume from E100.

- Why doesn't retrying `resumeAfter(E100)` help?
- If the projection is rebuildable from current state, outline the rebuild workflow.
- If you had to send **an email for every missed change**, does a current snapshot suffice?
- What historical source should have been designed upfront?

### Exercise 13 — Change Stream -> Kafka

A bridge sends E10 to Kafka successfully, then crashes before saving its resume token.

- Can E10 be sent again on restart?
- Does Kafka producer idempotency automatically protect side effects in downstream database consumers?
- What event IDs and checkpoints are needed at each boundary?
- Why should you never promise end-to-end exactly-once from a `watch()` call alone?

### Exercise 14 — Implementing an Exact Counter

For `OrderPaid` events, increment `paidOrders` exactly once per business event.

Design:

1. A stable event ID.
2. A unique index for the processed-events inbox.
3. Counter `$inc` update.
4. Resume token checkpoint.
5. A MongoDB transaction wrapping the related writes.

Analyze crashes before commit, after commit, and when commit returns an unknown result.

### Exercise 15 — Versioning and Reordering

Current projection:

```javascript
{ _id: "O-001", sourceVersion: 5, status: "SHIPPED" }
```

A delayed worker receives:

```javascript
{ orderId: "O-001", sourceVersion: 4, status: "PAID" }
```

Should this event be applied? Write the atomic conditional update based on `version`, and discuss what happens if `version` jumps from 3 to 5 when business rules require processing every intermediate event.

### Exercise 16 — Bootstrap Without Losing Updates

A system needs to build a search index from a one-million-document collection while writes continue during the scan.

- Why can "scan first, then watch from now" miss events?
- How should you anchor the stream start point and snapshot?
- What bug occurs if a slow snapshot write lands after a live event?
- How do versioning or coordinated replay prevent it?

### Exercise 17 — Observing Consumer Lag

The source produces 8,000 events/s while the consumer processes 2,000 events/s. Calculate backlog growth per second, and explain why that rate alone does not guarantee "events will be kept indefinitely." Which metrics must you monitor to spot oplog-window overrun risk?

### Exercise 18 — Designing a Production Runbook

A Change Stream cache consumer requires:

- Zero dropped events while required history exists.
- Duplicates must not corrupt projections.
- Events sharing the same `orderId` apply in order.
- Three parallel workers process events.
- Recovery plan after history loss.
- Logging and alerts when the consumer falls behind.

Design the dispatcher/partition/checkpoint coordinator flow, checkpoint/inbox schemas, retry rules, and rebuild procedure. Explicitly state **which guarantees are achieved** and **remaining limits**.

## 32. Practical Decision Checklist

When building a real Change Stream consumer, make decisions in this order:

1. **Source scope:** collection, database, or deployment? Which event types are needed?
2. **Event contract:** `operationType`, `documentKey`, `updateDescription`, `fullDocument`, or pre-/post-images?
3. **Ordering guarantees:** full stream or per-entity? How much parallelism is safe?
4. **Checkpointing:** where are BSON tokens stored, with what write concern, and who owns writes?
5. **Crash windows:** side effect first or checkpoint first? How are drops or duplicates handled?
6. **Idempotency:** are stable event/business IDs and unique constraints in place?
7. **Atomicity:** can effect + dedupe marker + checkpoint share a single MongoDB deployment transaction?
8. **Downstream:** do email/Kafka/payment sinks have their own acks, dedup, and reconciliation?
9. **Retention:** does the oplog window cover downtime, backlog, and backup/rebuild plans?
10. **Schema/version:** when pipelines, scopes, or event formats change, how do resume and backfill work?
11. **Observability:** are lag, throughput, retries, checkpoint age, history loss, and poison events monitored?
12. **Runbook:** on non-resumable errors, does the app halt for controlled recovery rather than silently jumping to "now"?

These decisions matter just as much as opening the `watch()` cursor successfully.

## 33. Summary

**MongoDB Change Streams provide an ordered change stream within stream scope and a resume token to continue reading**, yet **do not guarantee completion order** when applications fan events out to multiple workers or external systems. `clusterTime`, `documentKey`, and `ObjectId` cannot replace resume tokens for per-event checkpointing.

**Processing first and checkpointing second** avoids intentionally dropping events, while leaving a crash window that causes replays; **checkpointing first and processing second** leaves a crash window that drops side effects. Consequently, durable systems rely on **at-least-once + idempotency**, or atomic effect/checkpoint commits inside one transaction when all writes stay within supported boundaries.

**Exactly-once must be scoped explicitly.** A projection inside MongoDB can be protected with unique event IDs, conditional updates, and transactions. Calls to email, Kafka, or payment gateways cross separate acknowledgement boundaries; Change Streams do not provide distributed end-to-end transactions.

**Resuming has boundaries:** tokens remain valid only while MongoDB retains history; invalidations, namespace changes, oplog expiration, and non-resumable errors can force rebuilds or reconciliation. Once history is lost, reopening from "now" is never valid data recovery if skipped mutations carry business significance.

To build a dependable consumer, design **ordering, deduplication, checkpointing, retention, recovery, and monitoring** together. That is the foundation for using Change Streams as a near-real-time change source without confusing "received an event" with "accurately applied its business effect."
