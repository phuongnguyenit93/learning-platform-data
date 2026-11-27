# Consumption Rate Throttling, Latency, and Disruption Recovery with MongoDB Change Streams

## Lesson Objectives

MongoDB **change streams** allow applications to observe committed changes on a collection, database, or deployment. Yet running a change stream in production is far more than calling `watch()` and looping over a cursor. If the source emits events faster than your consumer can process them, the consumer can run out of memory or fall too far behind the oplog window. If the process crashes, the network drops, or MongoDB elects a new primary, the system must know **where to resume**, **which events were already processed**, and **when to resynchronize**.

This lesson belongs to **Database Engine Document MongoDB → Change stream → Consumption Rate Throttling, Latency, and Disruption Recovery**. Specific objectives:

1. Understand the path from the MongoDB oplog to the change stream cursor and consuming application.
2. Distinguish arrival rate, successful processing rate, backlog, queue depth, processing latency, and checkpoint lag.
3. Use `batchSize`, `maxAwaitTimeMS`, `next()`, and `tryNext()` appropriately.
4. Build backpressure using bounded queues, semaphores, rate limiting, and concurrency control.
5. Persist resume tokens **in intact BSON format** after side effects succeed.
6. Use `resumeAfter`, `startAfter`, and `startAtOperationTime` in the right scenarios.
7. Detect lost oplog history and recover via snapshot/reconciliation instead of silently dropping events.
8. Design idempotent handlers and checkpoints that never leap past unprocessed events under parallel workers.
9. Handle MongoDB primary elections, reconnects, invalidations, schema errors, downstream timeouts, and graceful shutdowns.
10. Understand the performance impact of `fullDocument: "updateLookup"`, filters, and sharded change streams.
11. Build `mongosh`/Java Sync Driver examples alongside metrics, runbooks, and fault-injection tests.

> **Key takeaway:** Reading an event does not mean **it was processed**. Resume tokens must represent **safely processed progress**, not merely the last position the driver fetched.

---

## 1. How Does a Change Stream Work?

### 1.1. The Change Flow

An application writes:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);
~~~

The change stream emits a corresponding change event:

~~~javascript
{
  _id: {
    _data: "opaque-resume-token"
  },
  operationType: "update",
  clusterTime: Timestamp(...),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-101"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
~~~

This is an **illustrative** shape; exact fields and values depend on MongoDB version, event type, and stream options.

### 1.2. Architecture Diagram

~~~text
Application writes
     |
     v
MongoDB replica set / sharded cluster
     |
     v
Oplog and change stream infrastructure
     |
     v
Change stream cursor
     |
     v
Driver receives batches via getMore
     |
     v
Consumer / bounded queue / workers
     |
     v
Downstream side effect acknowledged (ACK)
     |
     v
Persist durable resume token checkpoint
~~~

The MongoDB server knows an event was returned from the cursor, yet **does not know** whether search, cache, analytics, or external APIs succeeded. The application must manage that part.

### 1.3. Which Deployments Support Change Streams?

Change streams operate on replica sets and sharded clusters that support the feature, with compatible server/driver versions and access privileges. A standard standalone `mongod` does not provide change streams like a replica set. For single-machine learning, a **single-node replica set** works, though it provides no high availability against machine failure.

### 1.4. Observation Scopes

| Call | Scope |
|---|---|
| `db.orders.watch()` | `orders` collection |
| `db.watch()` | Current database |
| `MongoClient.watch()` in drivers | Deployment-wide per privileges/support |
| `collection.watch(pipeline)` | Collection with valid filter/transform pipeline |

Do not open a cluster-wide stream for a workload needing only one collection if it adds unnecessary overhead.

---

## 2. Change Streams Do Not Replace Message Brokers

Kafka or RabbitMQ provide consumer groups, message acknowledgements, routing, and retention with dedicated semantics. MongoDB change streams use a **cursor** and **resume tokens**; an event delivered by the cursor carries no built-in "business consumer ACK" state.

Example:

~~~text
MongoDB sends event E101 to consumer
       |
       v
Consumer calls cursor.next()
       |
       v
Application crashes
       |
       v
Search index not yet updated
~~~

If the consumer saved token E101 **immediately upon receipt**, restarting with `resumeAfter(E101)` skips E101. If it had not checkpointed yet, E101 is redelivered and requires idempotent handling.

### 2.1. Three Milestones to Separate

1. **Fetched:** the driver received the event.
2. **Processed:** the handler completed side effects and received acknowledgement.
3. **Checkpointed:** the token was durably persisted.

Never treat these three milestones as one.

### 2.2. Why Does Oplog Retention Matter?

Changes can be resumed only while needed history remains available. Unlike an event log sized to retain months or years, oplog retention depends on storage capacity, write rate, and configuration. A consumer that is too slow or offline too long loses the ability to resume from an old token.

---

## 3. Arrival Rate, Processing Rate, and Backlog

### 3.1. Definitions

- `λ`: rate at which change events arrive, in events/second.
- `μ`: rate of **successful processing**, in events/second.
- `B`: backlog of unprocessed events.
- `L`: latency, in seconds/milliseconds.

Under approximately steady rates:

\[
\frac{dB}{dt}\approx\lambda-\mu
\]

### 3.2. Example: Source Faster Than Consumer

Suppose:

~~~text
Arrival rate   : 250 events/s
Processing rate: 180 events/s
Backlog growth :  70 events/s
~~~

After two hours:

\[
B \approx 70 \times 7200 = 504\,000\ \text{events}
\]

This is a simplified model **estimate**. Events may sit in the oplog, driver buffers, application queues, or already be processed yet uncheckpointed. MongoDB does not maintain an exact application business backlog counter for you.

### 3.3. Catch-Up Speed

If processing capacity rises to 500 events/s while the source keeps producing 250 events/s:

~~~text
Catch-up net rate = 500 - 250 = 250 events/s
~~~

With a 504,000 backlog:

\[
504000/250=2016\text{ seconds}\approx33.6\text{ minutes}
\]

Do not turn raw arithmetic into an SLA promise: retries, network overhead, disk I/O, out-of-order effects, throttling, and incidents all factor in.

### 3.4. When `μ <= λ` Persists

Backlog grows or stagnates. If the consumer's checkpoint lags past the oplog window, the next crash restart will hit `ChangeStreamHistoryLost` or a similar error.

### 3.5. Do Not Confuse Read Speed with Processing Throughput

A fetch thread might pull 1,000 events/s while downstream finishes only 100/s. Reporting "1,000/s throughput" is misleading when the goal is business processing. Track **processed/s**, failed/s, retry/s, queue depth, and checkpoint progress separately.

---

## 4. Multi-Layered Latency

### 4.1. Timeline

~~~text
T0  MongoDB commits
T1  Change observed by stream
T2  Driver receives event
T3  Event enters handler
T4  Downstream acknowledges success
T5  Checkpoint persisted
~~~

### 4.2. Metrics

| Metric | Definition |
|---|---|
| Source-to-receive | T2 - T0 |
| Queue wait | T3 - T2 |
| Handler latency | T4 - T3 |
| End-to-end processing | T4 - T0 |
| Checkpoint latency | T5 - T0 |
| Oldest unprocessed age | How long the oldest unfinished event has waited |
| Checkpoint staleness | Distance between source progress and persisted token |

A system with tiny average latency can still have a single event stuck for hours. Track p95/p99 and **oldest unprocessed age**.

### 4.3. `clusterTime` Is Not a Wall-Clock Date

`clusterTime` is a logical BSON Timestamp; never treat it as a JavaScript `Date` for exact millisecond subtraction. Some MongoDB versions expose `wallTime` on change events with distinct semantics.

To measure latency rigorously, choose well-defined clocks (business event time, server `wallTime` where appropriate, consumer receipt time) and account for clock skew. Document the calculation method on your dashboards.

### 4.4. Causes of Rising Lag

- MongoDB write bursts.
- CPU-bound event handlers.
- Downstream HTTP 429 or 5xx responses.
- Slow cache/search index updates.
- Overly deep consumer queues.
- Frequent `fullDocument: "updateLookup"` queries adding read load.
- Repeated cursor reconnects.
- A poison event blocking ordered execution.
- Parallelism still serialized on one hot aggregate.
- Sharded streams coordinating across many shards and network links.

---

## 5. Backpressure: Protecting Memory and Downstream Systems

### 5.1. Anti-Pattern: Unbounded Queue

~~~text
MongoDB: 500 events/s
       |
       v
Fetch: 500 events/s
       |
       v
Unbounded queue
       |
       v
Handler: 100 events/s
~~~

The queue grows by 400 events/s and triggers Out-Of-Memory crashes. Fast reading does not equal healthy processing.

### 5.2. Bounded Queue

~~~text
Change stream
      |
      v
Bounded queue, e.g., 128 events
      |
      v
8 workers, max 16 concurrent calls
      |
      v
Downstream API + ACK
      |
      v
Checkpoint contiguous completed progress
~~~

When the queue fills, the fetch thread **pauses**. RAM stays bounded even while the source keeps generating changes.

### 5.3. A Bounded Queue Does Not Keep the Oplog Forever

When the consumer pauses fetching, MongoDB keeps writing. If the pause outlasts oplog retention, resume history expires. A bounded queue prevents OOM; preventing data gaps requires capacity, retention, durable intermediaries, and recovery plans.

### 5.4. Rate Limiting

- **Semaphore:** at most N concurrent requests.
- **Token bucket:** at most X requests/second.
- **Per-key serial lane:** sequential handling per aggregate.
- **Backoff/jitter:** space out retries when downstream errors occur.
- **Circuit breaker:** temporarily stop calling a continuously failing destination.

For instance, if a search service allows at most 200 updates/s, scaling to 200 workers only worsens 429 errors. Throttle according to actual destination capacity.

### 5.5. Never Drop Events Unless Permitted by SLA

For non-critical telemetry logs, sampling/dropping may be explicitly agreed upon in the data contract. For orders, payments, or financial projections, **never drop events and checkpoint past them**. If you cannot keep up, alert and use durable staging or horizontal scaling.

---

## 6. `batchSize`: Tuning Batch Retrieval

Change streams use aggregation cursors and `getMore`. `batchSize` sets the desired maximum number of documents per batch within server limits.

~~~javascript
const stream = db.orders.watch(
  [],
  {
    batchSize: 50
  }
);
~~~

### 6.1. Small Batches

Advantages:

- Lowers peak memory/payload per fetch.
- Fits slow handlers and small queues.

Disadvantages:

- More `getMore` network round trips.
- Higher overhead when handlers are very fast.

### 6.2. Large Batches

Advantages:

- Fewer round trips under high throughput.

Disadvantages:

- More in-flight memory usage.
- Can hold large batches of uncompleted events.
- Does not speed up downstream if the bottleneck is an external API.

### 6.3. Batch Size Is Not a Rate Limiter

`batchSize: 50` does **not** cap throughput at 50 events/second. If both source and consumer are fast, the driver fetches many batches every second. Real rate limiting must live in application logic.

### 6.4. How to Benchmark

Test `batchSize` values such as 10, 50, and 200 while measuring events processed/s, `getMore` latency, queue depth, heap/RSS memory, downstream errors, and p99 completion latency.

There is no single optimal number across all systems.

---

## 7. `maxAwaitTimeMS` Controls `getMore` Wait Time

When no new events are ready, the server can wait inside a `getMore` request.

~~~javascript
const stream = db.orders.watch(
  [],
  {
    batchSize: 50,
    maxAwaitTimeMS: 1000
  }
);
~~~

### 7.1. What This Parameter Does

It guides how long the server waits during an idle `getMore` call before returning an empty batch, shaping responsiveness and round trips.

### 7.2. What It Does Not Do

- Does not force the server to send at most one batch per second.
- Does not limit events processed per second.
- Does not guarantee end-to-end latency under 1,000 ms.
- Does not write resume checkpoints.
- Does not set a handler execution deadline.

### 7.3. Other Timeouts

| Timeout | Scope |
|---|---|
| `maxAwaitTimeMS` | Server wait time during `getMore` |
| Server selection timeout | Picking an eligible MongoDB server |
| Socket timeout | Network I/O |
| Handler timeout | Downstream processing duration |
| Backoff delay | Pause before retrying |
| Shutdown grace period | Waiting for in-flight events to finish |

Never collapse all timeouts into one mental bucket assuming identical semantics.

---

## 8. `next()`, `hasNext()`, and `tryNext()`

### 8.1. Blocking Loop in `mongosh`

~~~javascript
const stream = db.orders.watch();

while (stream.hasNext()) {
  const change = stream.next();
  printjson(change);
}
~~~

Great for learning. Production processing also needs shutdown handling, checkpointing, retries, and observability.

### 8.2. Java `tryNext()`

With the MongoDB Java Sync Driver, the cursor returns `null` when no event is currently available:

~~~java
ChangeStreamDocument<Document> event = cursor.tryNext();

if (event == null) {
    // No matching change arrived during this attempt.
    // Does NOT mean the stream ended permanently.
}
~~~

Never treat `null` as an error. Avoid tight busy-spin loops if the API returns quickly; pair with `maxAwaitTime` and clean scheduling.

### 8.3. Empty Batches

The driver/server can expose a **post-batch resume token** even when a batch returns zero matching events. That token reflects API stream position, yet **does not** prove events already handed to workers have finished processing.

Never checkpoint a token newer than events still in flight.

---

## 9. Resume Tokens Mark Read Position, Not Business ACK

Each change event contains an `_id` field holding its resume token:

~~~javascript
{
  _id: {
    _data: "opaque-bson-token"
  },
  operationType: "insert",
  documentKey: {
    _id: "ORD-101"
  }
}
~~~

### 9.1. Treat Tokens as Opaque

Never parse `_data` strings to extract timestamps, document IDs, or shards, or sort them yourself. Tokens are server-generated; pass them back intact to the change stream API preserving BSON types.

### 9.2. Persisting Checkpoints Durably

Example checkpoint document:

~~~javascript
{
  _id: "orders-indexer-v1",
  resumeToken: {
    _data: "token-issued-by-MongoDB"
  },
  updatedAt: ISODate("2026-11-14T04:00:00Z"),
  checkpointVersion: 1
}
~~~

The token above merely illustrates shape—never pass a fake token to `resumeAfter`.

### 9.3. Do Not Save Only Timestamps

`documentKey._id` and `clusterTime` cannot substitute cleanly for resume tokens. Multiple changes can share the same timestamp, and sharded topologies introduce subtler resume semantics.

### 9.4. Where Should Tokens Live?

In production, use a durable checkpoint store such as a MongoDB collection with appropriate write concern. On container restarts, memory and ephemeral local files vanish. Across multiple instances, the checkpoint store also needs ownership/fencing.

---

## 10. Checkpoint Before or After Processing?

### 10.1. Wrong: Save Token Before Handler

~~~text
Read E101
   |
Save token E101
   |
Crash
   |
Handler never produced side effect
   |
Restart resumeAfter(E101)
   |
E101 is lost from consumer state
~~~

### 10.2. Right: Process Successfully, Then Save Token

~~~text
Read E101
   |
Handle E101
   |
Downstream ACK / local commit
   |
Persist token E101
~~~

If a crash hits between handler completion and checkpointing, E101 replays. Handlers must be **idempotent**.

### 10.3. Crash Matrix

| Crash Point | Side Effect | Checkpoint | After Restart |
|---|---|---|---|
| Before fetch | No | E100 | Reads E101 |
| After fetch, before handler | No | E100 | Reads E101 again |
| Mid-processing | Uncertain | E100 | Replays E101 |
| After effect succeeds, before checkpoint | Yes | E100 | Replays E101; needs deduplication |
| After checkpoint succeeds | Yes | E101 | Continues after E101 |
| Checkpointed before effect (wrong) | No | E101 | Skips E101 |

### 10.4. Acknowledge Side Effects Only Upon True Completion

Firing an async call or submitting a job to an executor is not completion. For a broker, wait for broker ACK per policy. For a MongoDB read model, wait for transaction/write concern success. For HTTP, enforce timeouts and idempotency keys.

### 10.5. Checkpoint Write Timeouts

If saving a checkpoint times out, the write may or may not have succeeded. On restart, read back the persisted checkpoint rather than guessing. If the old token remains, the event replays—so handlers must be idempotent.

---

## 11. `resumeAfter`, `startAfter`, and `startAtOperationTime`

### 11.1. `resumeAfter`

Given the token of a processed event:

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    resumeAfter: savedToken
  }
);
~~~

Opens a stream starting **after** the token per MongoDB semantics, provided the token is valid and history remains.

### 11.2. `startAfter`

When a stream receives **`invalidate`** due to supported namespace operations like collection drop or rename, `resumeAfter` cannot resume past `invalidate` in the usual way. `startAfter` starts after an invalidate token where permitted.

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    startAfter: invalidateToken
  }
);
~~~

However, dropping and recreating a collection can leave old downstream read models invalid; decide whether to rebuild/reconcile.

### 11.3. `startAtOperationTime`

Given an eligible **BSON Timestamp**:

~~~javascript
const stream = db.orders.watch(
  [],
  {
    startAtOperationTime: someTimestamp
  }
);
~~~

This is not `new Date()` or an arbitrary ISO string. It requires matching oplog history and server version support.

### 11.4. Without Any Token

~~~javascript
db.orders.watch();
~~~

starts from the current point when opened and **does not replay pre-existing historical documents**. When building a search index from scratch, pair bootstrap snapshots with catch-up streaming.

### 11.5. Decision Table

| Scenario | Approach |
|---|---|
| Normal restart with token | `resumeAfter` |
| Reopening after an `invalidate` token | `startAfter` |
| Valid operation Timestamp available | `startAtOperationTime` |
| Only future changes matter | Intentionally watch from current point |
| Token hit history lost | Rebuild/reconcile; never silently reset |
| No checkpoint yet, existing source data | Snapshot/bootstrap + catch-up |

Never pass multiple start-position options in the same `watch` call.

---

## 12. Oplog History Loss and Data Loss Risk

### 12.1. Oplogs Do Not Retain Forever

The oplog stores replication/change-stream history within deployment size and retention bounds. As write load spikes, retained history duration shrinks.

~~~text
Oplog retains:
  09:00 --------------------------- 10:00

Consumer checkpoint:
  08:30

Consumer restarts at 10:00:
  08:30 token can no longer resume
~~~

### 12.2. History Lost Errors

MongoDB throws a `ChangeStreamHistoryLost`-style error when required history is gone. Never retry the old token indefinitely: once the oplog evicted that history, sleeping 10 seconds will never bring it back.

### 12.3. Dangerous Anti-Pattern

~~~javascript
try {
  consume();
} catch (error) {
  db.orders.watch(); // Reopens from "now", silently skipping the gap.
}
~~~

If your application needs accurate search indexes or projections, restarting from "now" after history loss silently drops mutations.

### 12.4. Business-Aligned Recovery

When zero gaps are required:

1. Alert and halt normal consumer progression.
2. Classify error, token, and source scope.
3. Identify the source of truth: live collection, event log, outbox, or backup/PITR.
4. Rebuild the read model or reconcile by entity/version.
5. Protect **changes occurring while the rebuild runs**.
6. Establish a fresh checkpoint via a safe cutover workflow.
7. Run consistency verification before marking the service healthy.

For loss-tolerant telemetry, resetting from "now" is acceptable only **under an explicit policy with clear logging**, never silently.

### 12.5. Monitor the Oplog Window

Track:

- Oplog configured size.
- Time span between oldest and latest oplog entries.
- Peak write burst rate.
- Consumer checkpoint staleness.
- Replication lag.
- Time-to-history-loss as workload grows.

Never assume "yesterday's oplog held 12 hours, so today's will too."

---

## 13. Gapless Bootstrap Snapshot + Change Stream

### 13.1. Error-Prone Approach

~~~text
1. Scan all orders to build the search index.
2. After the scan completes, open watch from current time.
~~~

An order modified between steps 1 and 2 can miss both the snapshot and the stream—creating a **gap**.

### 13.2. Sound Architectural Pattern

- Establish a change-stream starting point or open the stream and durably capture incoming events.
- Snapshot source data under appropriate consistency settings.
- Build the read model from the snapshot.
- Apply events emitted during the snapshot using event versions/IDs.
- Catch up to the source and transition to live processing.
- Persist durable checkpoints after effects complete.

### 13.3. Never Hold Unbounded Bootstrap Backlogs in RAM

Scanning millions of documents takes time. Buffering incoming changes in an unbounded in-memory list risks OOM. Use durable staging or recoverable partitioned/batched workflows.

### 13.4. When Only Final State Matters

A cache or search projection can be fully rebuilt and reconciled periodically if eventual convergence meets business needs. Yet if **every transition event is mandatory for auditing or finance**, the finite oplog should not be your sole historical record—pair with a transactional outbox, event log, or long-retention broker.

---

## 14. Resumable Errors, Reconnects, and Retries

### 14.1. Scenarios

- Network disconnect.
- MongoDB primary election.
- Server selection timeout.
- Cursor closed.
- Server restart.
- Invalid token.
- History lost.
- `invalidate` event.
- Business handler failure.
- Downstream HTTP 429/5xx.

### 14.2. Driver Auto-Resume Differs from Application Recovery

Official MongoDB drivers automatically resume change streams on eligible **resumable errors** per the change stream spec. However, drivers have no knowledge of downstream completion and do not persist application checkpoints across process restarts unless you implement it.

**Driver auto-resume does not replace application checkpoints.**

### 14.3. Retry Loop

~~~text
while service is running:
    token = readDurableCheckpoint()
    try:
        stream = openWatch(resumeAfter=token)
        while running:
            change = cursor.tryNext()
            if change exists:
                handleIdempotently(change)
                persistCheckpoint(change.resumeToken)
    catch temporary/resumable:
        close cursor
        bounded backoff + jitter
        reopen using durable checkpoint
    catch history-lost / invalid token:
        alert
        stop normal consumption
        reconcile/bootstrap
    catch poison business event:
        do not checkpoint past it
        retry/quarantine with policy
~~~

### 14.4. Prevent Retry Storms

A tight loop reopening `watch` hundreds of times per second during a MongoDB outage adds severe load and log noise. Apply exponential backoff, jitter, retry budgets, and health signals.

### 14.5. Never Reset Checkpoints When Reading the Checkpoint Store Fails

A timeout reading the checkpoint database is **not** the same as "no checkpoint exists." On checkpoint read errors, fail closed or retry per policy—never open a stream from "now."

---

## 15. Idempotent Processing

### 15.1. Why Replays Are Normal

Suppose E101 updated the search index, and the process crashed before saving the token. Restarting from E100 delivers E101 again. That is expected when prioritizing zero lost events.

### 15.2. Idempotent Upserts

If a change event carries order state version 2, the handler can conditionally update the projection by aggregate ID and version rather than applying blind increments on replay.

~~~javascript
db.orderProjections.updateOne(
  {
    _id: "ORD-101",
    version: 1
  },
  {
    $set: {
      status: "PAID",
      version: 2
    }
  }
);
~~~

This example updates only when the projection exists at `version: 1`. For initial inserts or concurrent writes, add explicit upsert and conflict handling.

### 15.3. Using Inbox Markers

~~~javascript
{
  _id: "search-indexer:EVT-ORD-101-PAID",
  eventId: "EVT-ORD-101-PAID",
  processedAt: ISODate("2026-11-14T12:00:00Z")
}
~~~

Enforce a unique key per `consumer + eventId`. When the marker and local business write reside in the same transaction-capable MongoDB deployment, commit them **inside one transaction**.

### 15.4. External APIs

Sending emails, HTTP payment calls, and broker publishes are not rolled back by a MongoDB transaction. Use destination idempotency keys, outboxes, or sagas/compensation. Checkpoints alone do not protect external side effects.

### 15.5. Watch Out for `$inc`

~~~javascript
db.metrics.updateOne(
  { _id: "orderPaidCount" },
  { $inc: { count: 1 } },
  { upsert: true }
);
~~~

If E101 replays, `$inc` increments twice unless protected by deduplication or a transaction. Re-apply using idempotent updates or business event markers.

---

## 16. Parallel Processing and Contiguous Checkpointing

### 16.1. Fetch Order Differs from Completion Order

~~~text
Fetch:      E101, E102, E103
Worker A:   E101 takes 10 seconds
Worker B:   E102 takes 1 second
Worker C:   E103 takes 1 second

Completion: E102, E103, E101
~~~

Persisting E103's token as soon as E103 finishes causes a crash to skip E101 while E101 is unfinished.

### 16.2. Contiguous Completion Frontier

Advance the checkpoint only to the last event in the **contiguous completed prefix starting from the old checkpoint**.

~~~text
Fetched     E101  E102  E103  E104
Completed    NO   YES   YES    NO
Checkpoint   E100
~~~

Once E101 finishes, E101–E103 form a contiguous completed range → checkpoint advances to E103. Since E104 is unfinished, never checkpoint past it.

### 16.3. Never Compare Opaque Tokens Like Integers

Never use lexicographical comparisons on `_data` to find a "max token." Assign a **local sequence index** in fetch order, track completion flags, and map index → BSON token to advance the frontier safely.

### 16.4. Bounded Concurrency

Example bounds:

~~~text
MAX_IN_FLIGHT = 64
QUEUE_CAPACITY = 128
WORKERS = 8
~~~

Once limits are reached, throttle fetching rather than spawning thousands of unbounded Futures.

### 16.5. Per-Aggregate Ordering

Events for the same order often require sequential execution:

~~~text
OrderPlaced  v1
OrderPaid    v2
OrderShipped v3
~~~

Use per-key lanes keyed by `aggregateId` or version gating/gap detection. Parallelism across distinct aggregates preserves per-aggregate order.

### 16.6. Checkpoints on Process Crash

In-memory completion flags vanish on a crash. Any event completed after the last persisted checkpoint replays on restart, so consumer idempotency remains mandatory.

---

## 17. Multi-Instance Consumers and Checkpoint Ownership

### 17.1. Two Identical Watchers Do Not Partition Work

If both Instance A and Instance B run:

~~~javascript
db.orders.watch();
~~~

both receive the exact same changes; MongoDB does not partition work like a Kafka consumer group.

### 17.2. Active-Passive

~~~text
Instance A: owner, opens stream, processes, and checkpoints
Instance B: standby, monitors owner lease
~~~

When A fails, B takes over from the durable checkpoint.

### 17.3. Active-Active

Use a single dispatcher reading the stream and publishing into a partitioned broker/durable queue, or partition independent consumers cleanly by business key/namespace.

### 17.4. Fencing and Leases

If owner A pauses until its lease expires, B takes over. When A wakes back up, A must never overwrite B's checkpoints.

Enforce owner tokens/fencing epochs with conditional checkpoint updates. Never allow "last writer wins" on a shared checkpoint document.

### 17.5. Never Build Synthetic Multi-Shard Offsets

When watching a sharded cluster, never stitch per-shard tokens into a single string offset and sort it. Use MongoDB's supported change stream API and a clean ownership model.

---

## 18. `fullDocument: "updateLookup"` and Its Overhead

### 18.1. Enabling Lookup

~~~javascript
const stream = db.orders.watch(
  [],
  {
    fullDocument: "updateLookup"
  }
);
~~~

For update events, MongoDB fetches the matching full document—handy when building current-state projections.

### 18.2. Important Limitation

The looked-up full document reflects state **at lookup time**, not necessarily an exact snapshot as of the update event's commit. If the document was subsequently updated or deleted before lookup, the result reflects the newer state or `null`.

### 18.3. Costs

- Extra database reads.
- Larger event payloads.
- Higher network bandwidth.
- Serialization cost.
- Memory pressure.
- Extra handler work.

If you only need a single modified field, `updateDescription.updatedFields` is lighter—though you must still handle inserts, replacements, deletes, and nested/array semantics accurately.

### 18.4. Pre-/Post-Images

MongoDB supports change stream pre-/post-images on compatible versions when configured. They carry their own storage, retention, and resource costs without offering infinite history. Check server version, collection options, and retention settings.

---

## 19. Filtering Change Streams Without Breaking Resume Tokens

### 19.1. Keep Only Relevant Operation Types

~~~javascript
const stream = db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

### 19.2. Never Strip Change Event `_id`

`_id` is the resume token. Pipelines that alter or remove it are rejected by the server or break resumability.

Never write:

~~~javascript
{
  $project: {
    _id: 0,
    operationType: 1
  }
}
~~~

in a change stream pipeline if it removes the event token.

### 19.3. Transform Payloads in the Handler Layer

If downstream only needs `documentKey` and `operationType`, extract them **after receiving the event**, keeping the full token for checkpointing.

### 19.4. Filter Changes May Require Migration

If v1 watched only inserts and v2 adds updates, never assume the old checkpoint already covers past updates. Plan backfill/reconciliation, change checkpoint IDs, or execute a deliberate cutover.

---

## 20. `invalidate` Events and `startAfter`

### 20.1. Scenarios

Dropping or renaming a collection can trigger `invalidate` depending on stream scope, closing the cursor.

### 20.2. Never Retry Blindly

An `invalidate` event is not a transient network timeout. If a collection was dropped, downstream projections may need clearing or rebuilding before watching further.

### 20.3. Tokens After `invalidate`

`startAfter` allows opening a stream past an `invalidate` token where supported. `resumeAfter` cannot resume past `invalidate` in the ordinary manner.

### 20.4. Downstream Accuracy

If a collection is dropped and recreated, simply calling `startAfter` does not repopulate the new collection or purge stale records from the old projection. Include explicit state reset/reconciliation logic.

---

## 21. `mongosh` Lab: Observing and Checkpointing

### 21.1. Seed Test Data

Run on a lab replica set:

~~~javascript
use change_stream_lab

db.orders.insertOne({
  _id: "ORD-101",
  status: "NEW",
  amount: 100000,
  updatedAt: new Date()
});
~~~

Never run destructive lab cleanup commands on production.

### 21.2. Open the Stream

~~~javascript
const stream = db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        }
      }
    }
  ],
  {
    batchSize: 10,
    maxAwaitTimeMS: 1000,
    fullDocument: "updateLookup"
  }
);

while (stream.hasNext()) {
  const event = stream.next();

  printjson({
    operationType: event.operationType,
    documentKey: event.documentKey,
    resumeToken: event._id
  });
}
~~~

The loop awaits events; close the cursor when finished. This is an observation demo only.

### 21.3. Generate Changes in a Second Session

~~~javascript
use change_stream_lab

db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      status: "PAID",
      updatedAt: new Date()
    }
  }
);

db.orders.updateOne(
  { _id: "ORD-101" },
  {
    $set: {
      status: "SHIPPED",
      updatedAt: new Date()
    }
  }
);
~~~

### 21.4. Save the Token After a Successful Handler

In a **separate** demo using a received event:

~~~javascript
const event = stream.next();

// Replace with durable business processing.
printjson(event);

db.getSiblingDB("change_stream_lab")
  .streamCheckpoints.updateOne(
    { _id: "orders-indexer-v1" },
    {
      $set: {
        resumeToken: event._id,
        updatedAt: new Date()
      }
    },
    { upsert: true }
  );
~~~

Here the handler only prints to stdout. In real consumers, await downstream acknowledgement before writing the checkpoint.

### 21.5. Restart

~~~javascript
const saved = db.getSiblingDB("change_stream_lab")
  .streamCheckpoints.findOne({
    _id: "orders-indexer-v1"
  });

if (saved && saved.resumeToken) {
  const resumed = db.getSiblingDB("change_stream_lab")
    .orders.watch(
      [],
      {
        resumeAfter: saved.resumeToken
      }
    );

  // Continue reading after the checkpoint.
}
~~~

Never fabricate fake tokens, and never confuse a missing checkpoint with a checkpoint-store connection failure.

---

## 22. Java Sync Driver: Sequential Consumer with Durable Checkpoints

### 22.1. Purpose

The Java example below demonstrates:

- Opening a stream on `orders`.
- Loading a BSON resume token from a checkpoint collection.
- Configuring `batchSize` and `maxAwaitTime`.
- Reading via `tryNext()`.
- Running a synchronous handler.
- Saving the token **after** handler success.

This is a lab skeleton; production services still need an external retry supervisor, idempotency, security, checkpoint durability, and a bootstrap strategy.

### 22.2. Java Code

~~~java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.changestream.ChangeStreamDocument;

import org.bson.BsonDateTime;
import org.bson.BsonDocument;
import org.bson.BsonString;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class OrdersStreamWorker {

    private final MongoCollection<Document> orders;
    private final MongoCollection<BsonDocument> checkpoints;

    public OrdersStreamWorker(MongoClient client) {
        MongoDatabase db =
            client.getDatabase("change_stream_lab");

        orders = db.getCollection("orders");

        checkpoints = db.getCollection(
            "streamCheckpoints",
            BsonDocument.class
        );
    }

    private BsonDocument loadCheckpoint() {
        BsonDocument doc = checkpoints.find(
            Filters.eq("_id", "orders-worker-v1")
        ).first();

        return doc == null
            ? null
            : doc.getDocument("resumeToken");
    }

    private void saveCheckpoint(BsonDocument token) {
        BsonDocument checkpoint =
            new BsonDocument()
                .append(
                    "_id",
                    new BsonString("orders-worker-v1")
                )
                .append("resumeToken", token)
                .append(
                    "updatedAt",
                    new BsonDateTime(
                        System.currentTimeMillis()
                    )
                );

        checkpoints.replaceOne(
            Filters.eq("_id", "orders-worker-v1"),
            checkpoint,
            new ReplaceOptions().upsert(true)
        );
    }

    private void handleIdempotently(
            ChangeStreamDocument<Document> change) {

        // DEMO: replace with real handler.
        // Await durable acknowledgement before returning.
        System.out.println(
            change.getOperationType()
        );
    }

    public void run() {
        BsonDocument token = loadCheckpoint();

        ChangeStreamIterable<Document> changeStream =
            orders.watch()
                .batchSize(50)
                .maxAwaitTime(
                    1000,
                    TimeUnit.MILLISECONDS
                );

        if (token != null) {
            changeStream =
                changeStream.resumeAfter(token);
        } else {
            // First run: stream does not automatically backfill history.
            // Requires explicit bootstrap or starting from "now".
        }

        try (MongoChangeStreamCursor<
                ChangeStreamDocument<Document>> cursor =
                    changeStream.cursor()) {

            while (!Thread.currentThread().isInterrupted()) {
                ChangeStreamDocument<Document> event =
                    cursor.tryNext();

                if (event == null) {
                    continue;
                }

                handleIdempotently(event);

                // Only after side effects succeed.
                saveCheckpoint(event.getResumeToken());
            }
        }
    }
}
~~~

### 22.3. Explanation

- `getResumeToken()` returns the change event's resume token.
- `resumeAfter(token)` requires a valid token and retained history.
- `tryNext() == null` merely indicates no event arrived during this poll.
- `handleIdempotently` is a placeholder here; production code must ensure durable side effects.
- `saveCheckpoint` executes after the handler returns.
- Because handling and checkpointing are separate steps, a crash between them triggers replay.
- Without a prior checkpoint, this code does not backfill existing documents.

### 22.4. Production Additions Needed

- MongoDB authentication and TLS.
- Appropriate write concern for checkpoints.
- Handler idempotency/inbox.
- Bounded error retries.
- History-lost classification.
- Snapshot bootstrapping.
- Monitoring and metrics.
- Clean shutdown lifecycle.
- Checkpoint owner fencing when running multiple instances.
- Alerting if checkpoints stall while the source keeps writing.

---

## 23. Java: Error-Classifying Retry Supervisor

Pseudocode:

~~~java
int attempt = 0;

while (serviceIsRunning()) {
    try {
        worker.run();
        attempt = 0;

    } catch (RuntimeException error) {

        if (isHistoryLostOrInvalidToken(error)) {
            alertOperator(error);
            stopConsumption();
            break;
        }

        if (!isTemporarilyRecoverable(error)) {
            alertOperator(error);
            stopConsumption();
            break;
        }

        attempt++;
        long delayMillis =
            boundedBackoffWithJitter(attempt);

        sleepSafely(delayMillis);
    }
}
~~~

This is **not standalone compilable code**: helper methods represent integration points with your operational policies.

### 23.1. Never Catch Every Error and Reopen from "Now"

Network blips are resumable, whereas history loss demands reconciliation. Handler bugs caused by mismatched `schemaVersion` will not heal after 100 retries.

### 23.2. Drivers May Auto-Resume Certain Errors

MongoDB drivers support auto-resume on eligible errors. Your supervisor must avoid spawning dozens of cursors concurrently; close failed cursors cleanly and resume from durable checkpoints in a controlled loop.

### 23.3. When Saving Checkpoints Times Out

Pause, re-read the durable checkpoint, and replay safely. Never guess whether the token succeeded or failed.

---

## 24. Consumer Side Effects and Checkpoints in the Same Transaction

When the handler updates **a projection residing in the same MongoDB deployment**, use a transaction:

~~~text
Read change event
       |
       v
MongoDB transaction:
  insert processed event marker
  update read model
  save checkpoint
       |
       v
commit
~~~

This closes the crash window between local effects and checkpoints, though it does not cover external HTTP calls or brokers.

### 24.1. Inbox Marker

~~~javascript
{
  _id: "orders-worker:EVT-101",
  eventId: "EVT-101",
  processedAt: ISODate("2026-11-14T04:00:00Z")
}
~~~

A unique marker detects replays cleanly when committed in the same transaction as the side effect.

### 24.2. When Using Multiple Workers

Checkpoints must follow the contiguous frontier; never let a worker finishing E103 save its token while E101 is still pending. A local transaction does not solve parallel completion ordering by itself.

### 24.3. External Side Effects

When calling a payment API, use idempotency keys and reconciliation. Never assume a MongoDB transaction can roll back an external payment.

---

## 25. Post-Batch Resume Tokens and Empty Batches

Change stream responses can carry progress tokens even across empty batches depending on server/driver APIs. For a sequential consumer with zero in-flight work, persisting a valid post-batch resume token per API guidelines keeps checkpoints fresh during quiet periods.

**However, if queued events remain unprocessed**, never leap the checkpoint past them simply because the driver received a newer position.

General invariant:

~~~text
Durable checkpoint <= contiguous position with all effects completed.
~~~

Never interpret token bytes or lexical order to compare positions.

---

## 26. Sharded Change Streams and Overhead

When watching a sharded collection or deployment, MongoDB aggregates changes across shards and coordinates order, adding network, CPU, and latency overhead.

### 26.1. Never Concatenate Per-Shard Tokens

Use the change stream API directly—never join per-shard tokens into a manual offset string.

### 26.2. Pick the Right Stream Scope

A single-collection stream is far simpler than watching an entire cluster and discarding 99% of events. Broaden scope only when genuinely required.

### 26.3. Monitor Resources

Track open stream cursors, MongoDB load, `getMore` latency, memory, network traffic, and shard lag. Even idle streams consume resources.

### 26.4. Namespace Changes

Drop, rename, sharding changes, and DDL operations affect change stream behavior and require migration/rebuild testing. Never assume every exception is resumable.

---

## 27. Runbook: When a Consumer Falls Behind

### Step 1: Identify the Bottleneck

Check event arrival rate, successful processing throughput, queue depth, handler latency, downstream 429/5xx errors, and MongoDB `getMore` latency.

### Step 2: Calculate Backlog Growth

If `λ > μ`, measure net backlog growth and estimate catch-up duration once capacity increases.

### Step 3: Tune Backpressure

Bound queues, cap in-flight requests, rate-limit downstream calls, and prevent OOM.

### Step 4: Optimize Payloads

Trim unnecessary `fullDocument` lookups, filter irrelevant events, and avoid heavy serialization on large fields.

### Step 5: Scale Appropriately

Add workers across independent aggregates while preserving per-aggregate order or version fencing. Never exceed downstream quotas.

### Step 6: Compare Against the Oplog Window

If checkpoint staleness approaches the retention window, alert on history-loss risk. Increase retention/capacity or introduce a durable intermediary matching workload needs.

### Step 7: Observe After Changes

Is queue depth shrinking? Is checkpoint lag narrowing? Did p99 handler latency rise? Is downstream overloaded?

---

## 28. Runbook: When a Consumer Disconnects

### Step 1: Classify

Transient network glitch, election, killed cursor, `invalidate`, invalid token, history lost, handler failure, or unavailable checkpoint store?

### Step 2: Read the Durable Checkpoint

If reading the checkpoint fails, never treat it as "no checkpoint exists."

### Step 3: Resume

For recoverable errors, close the cursor and reopen from the saved token using bounded backoff. Drivers may also auto-resume eligible errors.

### Step 4: Never Jump to "Now"

If the resume token hit history loss, **never** reopen from "now" if the system requires zero gaps.

### Step 5: Reconcile

Identify the source of truth; rebuild the projection, replay mutations occurring during the rebuild, verify consistency, and cut over.

### Step 6: Verify Idempotency

Events processed prior to the last checkpoint will replay. Confirm zero double-charges, double-counts, or duplicate notifications.

### Step 7: Record the Incident

Log disconnect time, before/after checkpoints, history window, recovered events, and follow-up improvements.

---

## 29. Monitoring and SLOs

| Metric | Purpose |
|---|---|
| `change_events_received_total` | Fetch rate |
| `change_events_processed_total` | Completion rate |
| `change_events_failed_total` | Handler failures |
| `change_events_replayed_total` | Replay frequency |
| `change_stream_reconnect_total` | Reconnect frequency |
| `change_stream_history_lost_total` | Unresumable history-loss errors |
| `queue_depth` | Queue saturation |
| `in_flight_events` | Active concurrent work |
| `oldest_unprocessed_age_seconds` | Age of oldest stuck event |
| `handler_latency_ms` | Handler p50/p95/p99 |
| `checkpoint_staleness_seconds` | Age of last persisted checkpoint |
| `checkpoint_write_errors_total` | Token persistence failures |
| `oplog_window_seconds` | Retained oplog history span |
| `downstream_rate_limit_errors_total` | 429/quota errors |

### 29.1. Do Not Look Only at Averages

If 99% of events finish fast while one event stalls for an hour, averages hide the outage. Monitor oldest unprocessed age and checkpoint progress.

### 29.2. Example SLO

~~~text
99% of event effects complete within 5 seconds
with zero events lost across restarts while history remains available.
~~~

An SLO must specify start/end measurement points and retention assumptions, rather than just saying "real-time."

### 29.3. Alerts

- Checkpoint stops advancing while the source keeps writing.
- Queue approaches full capacity.
- `processing rate < arrival rate` persists.
- Oldest unprocessed age exceeds threshold.
- Oplog window nears checkpoint lag.
- Resume errors climb steadily.
- Any history-loss event on a zero-gap consumer.
- Downstream 429/5xx spikes.
- Abnormal handler exception rates.

---

## 30. Fault and Recovery Testing

### Test 1 — Consumer Slower Than Producer

Generate 200 events/s while handlers complete 50/s. Observe backlog, queue depth, and checkpoint lag. The bounded queue must prevent OOM without pretending to prevent oplog history loss.

### Test 2 — Scaling Workers

Increase workers in a controlled test; measure successful throughput, downstream error rate, and per-aggregate ordering.

### Test 3 — Crash After Fetch

Receive E101 and crash before the handler runs. Restart from E100 and confirm E101 runs.

### Test 4 — Crash After Handler, Before Checkpoint

E101 succeeds, crash before saving the token. E101 replays; verify the handler is idempotent.

### Test 5 — Checkpoint Store Timeout

Drop connection during checkpoint save. Restart from durable state; verify events are not skipped if the token wasn't persisted.

### Test 6 — Primary Failover

In a lab replica set, trigger an election and observe driver auto-resume and application recovery.

### Test 7 — Oplog History Lost

Supply a token older than retained lab oplog history. Confirm the consumer alerts and enters reconciliation rather than silently starting from "now."

### Test 8 — Invalidate

Drop/rename a collection in an isolated lab, observe `invalidate`, and exercise `startAfter` alongside projection rebuilds.

### Test 9 — Out-of-Order Completion

Delay E101 behind E102 and E103. Verify checkpoints never advance past E101 until E101 finishes.

### Test 10 — Poison Event

Send an event schema unsupported by the handler. Confirm the consumer never checkpoints past the failure without an audited quarantine/replay decision.

### Test 11 — Downstream 429

Rate-limit the target API; verify the consumer backs off, limits concurrency, and drops zero events.

### Test 12 — `fullDocument: "updateLookup"`

Update the same document rapidly in succession and verify code never assumes `fullDocument` always equals the exact snapshot of each historical transition.

### Test 13 — Initial Run Without Token

Verify a brand-new consumer bootstraps existing source data when a full index is required rather than merely opening `watch()`.

### Test 14 — BSON Token Roundtrip

Persist and reload tokens from the checkpoint collection and pass them back into `resumeAfter`.

### Test 15 — Two Instances Sharing One Checkpoint

Simulate Owner A's lease expiring and B taking ownership. Verify A cannot overwrite newer checkpoints thanks to fencing.

### Test 16 — Empty Batch

Emit zero matching events while the driver receives post-batch resume info. Verify checkpoints never leap ahead of in-flight events.

---

## 31. Practice Exercises

### Exercise 1: Backlog Calculation

Arrival rate is 600 events/s and processing rate is 450 events/s for 30 minutes. Compute accumulated backlog assuming constant rates.

### Exercise 2: Catch-Up Time

240,000 events remain unprocessed; the source produces 200/s while the consumer scales to 500/s. Calculate catch-up duration and state assumptions of the estimate.

### Exercise 3: `batchSize` and Rate Limiting

Use `batchSize: 20` and explain why it does not cap throughput at 20 events/s. Design a 100 events/s token bucket.

### Exercise 4: `maxAwaitTimeMS`

Set `1000 ms` and measure `getMore` behavior on idle vs. busy streams. List the other latency layers.

### Exercise 5: Bounded Queue

Configure queue size 128, max 16 in-flight, and 8 workers. Describe behavior when the queue fills, when downstream returns 429, and during shutdown.

### Exercise 6: Correct Checkpoint Order

Extract a resume token from a real event, save after the handler, and restart with `resumeAfter`. Explain the consequence of saving before the handler.

### Exercise 7: Idempotency

Process E1 then crash before checkpointing. Design an inbox marker or version-gated projection so E1's replay produces zero duplicate effects.

### Exercise 8: Contiguous Frontier

E1, E2, E3, E4 complete in the order E2, E4, E3, E1. Write the valid checkpoint after each completion.

### Exercise 9: History Lost

A consumer stays offline longer than the oplog window. Write a zero-gap runbook covering alerts, snapshot rebuild, catch-up, and cutover.

### Exercise 10: Bootstrap Gap

Why can scanning documents first and opening `watch` afterward miss an update? Design a gapless workflow.

### Exercise 11: Java Sync Driver

Write a consumer using `ChangeStreamIterable`, `MongoChangeStreamCursor`, `tryNext`, `resumeAfter`, and durable checkpoints. Add bounded retries.

### Exercise 12: Full Document

Compare `updateDescription` and `fullDocument: "updateLookup"` under two rapid consecutive updates on one document.

### Exercise 13: Multi-Instance

Two workers both open `watch` sharing one checkpoint ID. Design leases/fencing or a dispatcher-broker split to avoid corrupting tokens.

### Exercise 14: Per-Key Ordering

Attach `aggregateId` and `version` to `OrderPlaced`, `OrderPaid`, and `OrderShipped`. Ensure version 2 never overwrites version 3.

### Exercise 15: Monitoring

Build a dashboard showing arrival/success rates, queue depth, checkpoint age, oldest unprocessed event, oplog window, reconnect/error rate, and p99 handler latency.

### Exercise 16: Recovery Testing

Plan fault-injection tests for network cuts, primary elections, handler exceptions, checkpoint failures, poison events, history loss, `invalidate`, and shutdown with in-flight events.

---

## 32. Review Questions

1. From which MongoDB history mechanism do change streams read?
2. Why doesn't MongoDB automatically know when a business consumer finished processing?
3. How does arrival rate differ from processing rate?
4. When does backlog grow?
5. What problem does a bounded queue solve?
6. Does a bounded queue by itself prevent oplog history loss?
7. Is `batchSize` an events/sec rate limit?
8. What does `maxAwaitTimeMS` control?
9. Does `tryNext() == null` mean permanent EOF?
10. Where is the resume token located inside a change event?
11. Why must tokens be treated as opaque BSON values?
12. Why should checkpoints advance only after handler acknowledgement?
13. What happens on a crash after the handler succeeds but before checkpointing?
14. Why is a crash after checkpointing but before the handler dangerous?
15. When is `resumeAfter` used?
16. How does `startAfter` relate to `invalidate`?
17. What value type does `startAtOperationTime` require?
18. Without a token, does `watch` replay pre-existing documents?
19. When does history loss occur?
20. Why shouldn't you silently reset from "now"?
21. What gap exists in naive snapshot bootstrapping?
22. Why is durable staging needed during long snapshots?
23. How does driver auto-resume differ from application recovery?
24. How does idempotency help during replays?
25. Why is `$inc` normally non-idempotent?
26. What is a contiguous checkpoint frontier?
27. Why must you not checkpoint E103 if E101 is still unfinished?
28. Do two identical watchers automatically split work like a consumer group?
29. Why is fencing required when sharing a checkpoint?
30. What risks come with `fullDocument: "updateLookup"`?
31. Why must you never drop event `_id` inside a pipeline?
32. What overhead do sharded streams carry?
33. Which metrics reveal a lagging consumer?
34. Why does oldest unprocessed age matter more than averages?
35. How should you throttle when downstream returns HTTP 429?
36. How do you recover once oplog history is lost?
37. How do collection drop/rename operations affect streams?
38. When is it safe to persist a post-batch resume token?
39. Why are change streams not an infinite long-term audit log?
40. Which milestones should a change stream SLO define?

---

## 33. Summary

MongoDB change streams deliver changes from the server's oplog/stream engine, yet a production consumer must proactively manage **throughput**, **latency**, and **recoverability**.

**Rate throttling:** measure source rates and real completion capacity; apply bounded queues, concurrency caps, rate limiters, and backoff. Treat `batchSize` as batch tuning and `maxAwaitTimeMS` as `getMore` awaiting—**never** as rate limits.

**Latency:** track commit-to-receive, queue wait, handler duration, checkpoint lag, and oldest unprocessed age. When processing lags behind arrival, backlog climbs; once checkpoints fall past oplog retention, resumability breaks.

**Recovery:** persist intact BSON resume tokens **after side effects succeed**. Use `resumeAfter` for normal restarts, `startAfter` after eligible `invalidate` events, and `startAtOperationTime` when holding a valid BSON Timestamp. Distinguish transient errors from history loss; never silently skip gaps. Under concurrency, checkpoint along the **contiguous completion frontier**, never the newest fetched token.

**Business correctness:** make handlers idempotent so replays never duplicate side effects. Change streams do not natively provide consumer groups, end-to-end exactly-once semantics, or infinite replay history. When long-term zero-gap guarantees are required, pair with outboxes, brokers, backups/reconciliation, and fault-injection testing.

A trustworthy consumer does more than keep a cursor open. It can prove **how far it has processed**, **how far behind it lags**, **whether history remains to catch up**, and **how to recover when a checkpoint can no longer resume**.

## References

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Change Events](https://www.mongodb.com/docs/manual/reference/change-events/)
- [MongoDB Manual — db.collection.watch()](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [MongoDB Manual — $changeStream](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/)
- [MongoDB Manual — Change Stream Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/)
- [MongoDB Manual — Replication Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images)
- [MongoDB Manual — Change Streams in Sharded Clusters](https://www.mongodb.com/docs/manual/changeStreams/#sharded-cluster-considerations)
- [MongoDB Manual — Aggregation Pipeline Limits](https://www.mongodb.com/docs/manual/core/aggregation-pipeline-limits/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [MongoDB Java Sync Driver — Cursors](https://www.mongodb.com/docs/drivers/java/sync/current/crud/query-documents/cursor/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
