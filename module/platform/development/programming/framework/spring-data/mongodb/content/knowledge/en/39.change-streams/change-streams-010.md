# Duplicate Events, Invalidate, Retention, and Idempotent Processing

## 1. Problem: A Replayed Change Stream Can Deliver the Same Business Effect Again

Suppose an order system has an **orders** collection in MongoDB. When an order transitions to **PAID**, a service uses a Spring Data MongoDB change stream to update an **order_summaries** read model and send a confirmation notification.

~~~text
Orders (MongoDB)
      |
      | Change stream
      v
OrderEventConsumer
      |
      +-- update order_summaries
      |
      +-- create notification/outbox
      |
      +-- save resume token
~~~

The consumer receives a PAID status transition event and updates the read model. Immediately afterward, the app drops its connection or the process stops before saving the checkpoint. Upon restart, the consumer reads from the old resume token and may **receive the already-processed event again**. If the handler adds revenue or sends an email on each receipt, data can be double-counted or sent twice.

Another case: an administrator drops or renames the watched collection. MongoDB emits **invalidate** and closes the cursor. A retry loop calling **resumeAfter** with the old token will not make the stream valid again.

A third case: a worker stops for hours while the oplog wraps around. The saved resume token still sits in the checkpoint database, yet the **history that token pointed to has been evicted from the oplog**. Resuming fails; infinitely retrying with that token merely prolongs the outage.

The lesson **Duplicate Events, Invalidate, Retention, and Idempotent Processing** belongs to the **Change stream** chapter in the **SPRING_DATA_MONGODB** module. The module covers connecting, document mapping, operating on MongoDB via MongoTemplate or repositories, query design, aggregation, indexing, transactions, reactive access, testing, and performance diagnostics.

### 1.1. Objectives

After this lesson, you will be able to:

1. Distinguish **duplicate events** caused by replay/reconnect from two valid business changes on the same entity.
2. Understand resume tokens, **resumeAfter**, **startAfter**, and **startAtOperationTime**.
3. Identify invalidations from drop/rename/dropDatabase and handle them according to watch scope.
4. Understand **oplog retention**, recovery windows, and cases where tokens are no longer usable.
5. Design **post-processing checkpoints**, never pre-processing checkpoints.
6. Apply **idempotent inboxes**, unique keys, business versions, and MongoDB transactions.
7. Decouple **side effects outside MongoDB** into idempotent outbox/notification workers.
8. Use Spring Data **ReactiveMongoTemplate** and **ChangeStreamOptions** with durable tokens.
9. Handle errors, backoff retries, poison events, and preserve event ordering.
10. Write integration and failure-injection tests and monitor lag against oplog retention.

## 2. What Is a Change Stream and What Infrastructure Does It Require?

MongoDB change streams let you watch committed changes across a MongoDB deployment without tailing **oplog.rs** directly.

Watches can apply at multiple scopes:

| Scope | Stream open point | Example |
| --- | --- | --- |
| Collection | db.orders.watch | Watch a single collection only |
| Database | db.watch | Watch changes across collections in one database |
| Deployment | Mongo.watch | Watch across databases/collections in the deployment per granted privileges |

**Change streams require a replica set or sharded cluster**, not an ordinary standalone MongoDB server. Applications need appropriate privileges to open change streams and watch namespaces.

### 2.1. Change streams are not message queues with independent retention

A broker can retain messages under independent topic retention policies. MongoDB change streams rely on **oplog history** to replay events. Storing a token in another collection does not keep event history alive forever.

### 2.2. Cursors are not immutable jobs

A change stream is a long-lived cursor. It can close due to:

- Application explicitly stopping it.
- Connection drops, timeouts, or mongod/mongos state transitions.
- **invalidate** events.
- Insufficient history left to resume.
- Other pipeline/permission/server errors.

Cursor closure and namespace closure via invalidate are distinct incidents. Transient errors can be resumed; invalidations and history loss require different decisions.

### 2.3. Watch scope governs DDL handling

A collection watch can be invalidated by **drop**, **rename**, or **dropDatabase** affecting that collection. A database watch is invalidated when **dropDatabase** affects the watched database. Never assume every child collection drop invalidates a database-level watch.

## 3. What Does a Change Event Contain?

A simplified insert event from mongosh:

~~~javascript
{
  _id: { _data: "8265...opaque-resume-token..." },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1730462400, i: 1 }),
  ns: { db: "commerce", coll: "orders" },
  documentKey: {
    _id: ObjectId("507f1f77bcf86cd799439011")
  },
  fullDocument: {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    tenantId: "shop-a",
    orderNo: "ORD-101",
    status: "CREATED"
  }
}
~~~

This example illustrates structure, not a real resume token usable for resuming.

| Field | Meaning |
| --- | --- |
| _id at **event** level | **Resume token**, representing position in the change stream |
| operationType | insert, update, replace, delete, invalidate, and other types |
| clusterTime | BSON Timestamp associated with the cluster operation |
| ns | Event database/collection |
| documentKey | Key of the modified document, normally including _id |
| fullDocument | Associated document, depending on operation type and lookup configuration |
| updateDescription | Fields updated/removed/truncated in an update event |

### 3.1. Two different `_id` fields

~~~text
event._id                  -> event resume token
event.documentKey._id      -> business document ID
event.fullDocument._id     -> document ID inside snapshot (if present)
~~~

Never use documentKey._id instead of the resume token. One Order can generate **dozens of events** sharing the same documentKey._id.

### 3.2. Not every event carries `fullDocument`

For delete, the deleted document body is normally absent. For update, events default to **updateDescription**; to look up the current document you can request **fullDocument: updateLookup**, though lookup results may differ from an exact update-time snapshot or be null.

For invalidate, never expect fullDocument to contain an Order. Handlers must branch on **operationType** before accessing the body.

### 3.3. Never modify event `_id` in a pipeline

MongoDB treats event._id as the resume token. Change stream pipelines must not project away or alter event._id; starting in MongoDB 4.2, modifying _id in the pipeline errors. To reshape DTO fields, transform **after receiving** while keeping the token intact.

## 4. When Do "Duplicate Events" Happen?

Change streams do not guarantee business side effects run exactly once. In the consumer layer, **design for replay/at-least-once safety**.

Common causes:

1. Worker completes processing then crashes before persisting the checkpoint.
2. Connection drops and driver/app reopens cursor from the pre-event checkpoint token.
3. Supervisor restarts the container and the consumer rereads a window of events.
4. A checkpoint token rolls back due to non-durable storage.
5. Two consumers handle the same logical subscription without a lease/fencing.
6. Retrying a message from an outbox or notification queue after a timeout.

### 4.1. Event-level duplication vs. business-command duplication

If an Order transitions:

~~~text
CREATED -> PAID -> REFUNDED -> PAID
~~~

there can exist **two valid distinct PAID events** with different resume tokens. Never assume "already saw this Order ID, so ignore all future events".

A retried business command can also create a **new event** with a new resume token even though the client thinks it was one request. Hence two layers of idempotency are required:

- **Event idempotency:** apply a single change event token at most once for its intended effect.
- **Business idempotency:** the same paymentId/commandId must never record revenue or charge payment twice.

### 4.2. Duplicates do not come solely from MongoDB

If a consumer publishes an email request and the email service times out after sending successfully, a retry from the notification worker can send it again. Deduplicating change-stream events in the consumer does not guarantee an email is sent once if downstream lacks idempotency.

## 5. Practical Guarantee Levels

| Goal | Approach | What is NOT automatically guaranteed |
| --- | --- | --- |
| Miss no events within history window | Durable token checkpoints, clean resuming | Does not protect once oplog history is lost |
| Never apply the same event twice | Unique inbox key/event token | Does not block two distinct tokens carrying the same business op |
| Never double-update projections | Idempotent $set/upsert/version guard | Does not preserve order automatically under parallel processing |
| Atomic inbox + projection + checkpoint | MongoDB transaction sharing one session | Not atomic with email/HTTP/Kafka outside MongoDB |
| Avoid duplicate emails | Outbox + downstream idempotency key | Email providers lacking idempotency can still duplicate |
| Continue after drop/rename | Detect invalidate + policy-driven startAfter | Does not restore old documents automatically |
| Recover after history loss | Rebuild/reconcile from consistent cut point | Cannot restore deleted events without another source |

**Exactly-once** is meaningful only when specifying **which artifact is processed once**, within which systems and transactions.

## 6. Resume Tokens: The Logical Checkpoint of a Change Stream

Each change event holds a token at **event._id**. Tokens are typically BSON documents with opaque fields, not custom sequential integers.

~~~javascript
const stream = db.orders.watch();
const event = stream.next();
const token = event._id;
~~~

Persist the **entire token intact** to resume; never slice timestamps or subsets of _data.

### 6.1. Event tokens and high-water-mark tokens

MongoDB provides both:

- **Event tokens:** tied to a specific event.
- **High-water-mark tokens:** represent an advance in cluster time when no new events arrive; may be returned by the server as **postBatchResumeToken** in cursor responses.

Spring Data ChangeStreamEvent.getResumeToken() mainly handles tokens on emitted events. To checkpoint high-water marks during idle periods, use driver/cursor APIs exposing postBatchResumeToken and obey the rule to checkpoint only once all earlier events are processed.

### 6.2. Tokens are not clocks

Do not sort or compare resume tokens alphabetically as JSON strings. Tokens are opaque BSON and formats can shift across servers/versions. Checkpoints should store the token with metadata: stream identity, watch scope, pipeline version, and observation timestamp.

### 6.3. One stream identity needs one clear checkpoint

~~~javascript
{
  _id: "orders-projection-v1",
  watchScope: "commerce.orders",
  pipelineVersion: 1,
  resumeTokenJson: "{ \"_data\": \"8265...\" }",
  lastOperation: "update",
  updatedAt: ISODate("2025-06-01T12:00:00Z")
}
~~~

resumeTokenJson is an **illustrative serialization example**, not a mandatory contract. You can store BSON tokens natively as BSON/BsonDocument once codecs and storage schemas are verified. When using JSON, ensure **type-preserving Extended JSON round-tripping** and protect checkpoint data.

## 7. Proper Checkpointing Order: Process First, Save Token Afterward

Replay-safe timeline:

~~~mermaid
sequenceDiagram
    participant M as MongoDB Change Stream
    participant C as Consumer
    participant P as Projection/Inbox
    participant K as Checkpoint
    M->>C: Event E1 + token T1
    C->>P: Apply idempotent effect E1
    P-->>C: Durably processed
    C->>K: Persist token T1
    K-->>C: Checkpoint succeeded
    Note over C: Only now treat E1 as committed for consumption
~~~

### 7.1. Saving token before effect is dangerous

~~~text
T0: receive event E1
T1: checkpoint T1 succeeds
T2: crash before updating read model
T3: resumeAfter(T1) => skips E1
~~~

Outcome: the projection is missing data, and the new token prevents E1 from appearing in normal stream continuation.

### 7.2. Saving token after effect can repeat — which is why idempotency is required

~~~text
T0: receive E1
T1: projection update succeeds
T2: crash before checkpoint T1
T3: resumeAfter(T0) => receive E1 again
T4: idempotent handler sees E1 was already applied
T5: checkpoint T1
~~~

This design safely absorbs replays as long as markers/effects are durable.

### 7.3. Transactions eliminate the gap

When **inbox marker, projection update, and checkpoint reside in the same MongoDB deployment** and share one MongoDB transaction:

~~~text
BEGIN TRANSACTION
  insert inbox marker(event E1)
  update projection
  update checkpoint(T1)
COMMIT
~~~

After commit, all three changes persist together; on abort, none commit. This **excludes** external HTTP/email calls outside MongoDB and depends on topology and session/transaction options.

## 8. Crash Matrix: Predicting Duplicates vs. Data Loss

| Crash point | Effect saved? | Checkpoint saved? | On restart |
| --- | --- | --- | --- |
| Before processing E1 | No | No | E1 may replay |
| After effect, before token | Yes | No | E1 may replay; inbox must dedupe |
| After token, before effect | No | Yes | **Risk of losing E1** |
| After transaction committing effect+token | Yes | Yes | Resume after E1 |
| Transaction aborted | No | No | E1 retried if oplog remains |
| External effect ran, local transaction aborted | Possibly yes | No | Downstream needs its own idempotency |

### 8.1. Do not "fix" with infinite retries

Retries help against transient errors, yet **cannot bridge transaction gaps** or resurrect truncated oplogs. Pair retries with error classification, time limits, metrics, and recovery plans.

### 8.2. Why not checkpoint on receiving the event?

The onNext callback only proves the consumer **read bytes/event**. It does not prove the projection, outbox, or business operation committed. Checkpoints must represent **last durably processed position**, not merely last observed position.

## 9. Opening and Resuming Streams in `mongosh`

Practice on a **replica set test database**; never create/edit/delete data on production collections.

~~~javascript
use commerce;

const stream = db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);

const first = stream.next();
printjson(first);

const token = first._id;
stream.close();
~~~

Calling **next()** can wait until an event arrives. For a controlled example, open the watch first, then insert/update from another session. In automated scripts use tryNext/timeouts/cancellation instead of waiting forever.

### 9.1. Resuming after an event

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    resumeAfter: token,
    fullDocument: "updateLookup"
  }
);
~~~

**resumeAfter(T)** opens a cursor starting **after** the event identified by token T. Ensure the token remains within oplog recovery limits and watch pipeline/options match those used when creating the token.

### 9.2. Never fabricate tokens from `clusterTime`

~~~javascript
// Fundamentally wrong:
const token = { _id: first.clusterTime };
~~~

Tokens have a MongoDB-generated BSON shape, not an arbitrary application object. To start from a timestamp, use **startAtOperationTime** with a proper BSON Timestamp—never forge resume tokens.

### 9.3. Starting by timestamp

~~~javascript
const startTime = Timestamp({ t: 1730462400, i: 1 });

const byTime = db.orders.watch(
  [],
  { startAtOperationTime: startTime }
);
~~~

The starting point must still lie inside the oplog history window. Timestamps do not identify a distinct event like resume tokens and are not always granular enough when multiple events share a timestamp.

### 9.4. Never use all three options together

Options **resumeAfter**, **startAfter**, and **startAtOperationTime** are mutually exclusive ways to pick a starting position and must not be combined on a single watch.

### 9.5. Keep pipeline/options uniform

MongoDB recommends using the **same pipeline and options** when resuming from a token. Incompatible changes to aggregation filters, collation, or fullDocument options can prevent resuming or yield unexpected results. Store **pipelineVersion** in checkpoints for controlled deployments and migrations.

## 10. What Is `invalidate`?

**invalidate** is a change event signaling the watched stream is no longer valid for its current namespace scope, for instance because the collection was dropped or renamed.

~~~javascript
{
  _id: { _data: "opaque-invalidate-token" },
  operationType: "invalidate",
  clusterTime: Timestamp({ t: 1730462401, i: 1 })
}
~~~

The cursor usually **closes after invalidate**. Never process invalidate like an update carrying fullDocument.

### 10.1. When does `invalidate` appear?

| Watch scope | Related DDL operation | Typical outcome |
| --- | --- | --- |
| `orders` collection | Drop `orders` itself | Drop event and invalidate; cursor closes |
| `orders` collection | Rename `orders` | Invalidate; cursor closes |
| `orders` collection | Drop database containing `orders` | Invalidate; cursor closes |
| `commerce` database | Drop a child collection | Database watch may see drop event; does not invalidate entire DB by default |
| `commerce` database | Drop `commerce` database itself | Invalidates database watch; cursor closes |
| Deployment watch | DDL on a collection/database | Different scope; inspect event types and API, never assume collection-watch rules apply blindly |

MongoDB versions can support additional expanded DDL events when **showExpandedEvents** is configured. Never couple logic tightly to an exact sequence of DDL events without integration testing on your target server version.

### 10.2. Drop/rename vs. update/delete

A normal document **delete** does not invalidate a collection watch. **Dropping a collection** alters namespace/collection lifecycle and has broader effects.

### 10.3. Should `invalidate` emit a business event?

Typically consumers should:

1. Record that the stream became invalidated.
2. Stop applying old business updates.
3. Alert if the drop/rename was not part of a planned migration.
4. Decide whether to open a new stream, switch namespaces, or rebuild the read model.

Never translate invalidate into "delete an order" or notify customers as a normal business event.

## 11. How Do `resumeAfter` and `startAfter` Differ?

| Situation | resumeAfter(token) | startAfter(token) |
| --- | --- | --- |
| Normal event token, history intact | Standard choice | Works per contract to open a new stream |
| Token of an **invalidate event** | **Cannot be used** | **Can open a new stream after invalidate** |
| Token rolled off the oplog | Cannot resume | Cannot recover lost history |
| Pipeline/options differ from creation | Risky / unsupported | Also requires compatibility |
| Old namespace dropped | Does not restore collection | Only opens stream after invalidate; does not recreate lost data |

### 11.1. `mongosh`: `startAfter` invalidate

~~~javascript
// Assuming the real invalidate event token was received and stored intact:
const invalidateToken = {
  _data: "token-from-real-invalidate-event"
};

const freshCursor = db.orders.watch(
  [],
  { startAfter: invalidateToken }
);
~~~

This snippet illustrates **option syntax** only; fake tokens will not work. Persist the actual token from the invalidate event. On a dropped collection, you may need to wait for recreation, change watch scope, or apply another deployment policy.

### 11.2. Conditions for `startAfter` to succeed

**startAfter does not bypass retention limits.** The server must still hold enough history to locate the token. Renamed or dropped namespaces are not magically restored; if the app needs new state, inspect the recreated/new collection and migration path.

### 11.3. Do not swap `resumeAfter` for `startAfter` on every exception

Transient network drops, permission denials, bad pipelines, and invalidations mean completely different things. Overusing startAfter can mask unauthorized DDL changes or silently continue the consumer on a different dataset.

### 11.4. After invalidate, should the consumer automatically recreate the collection?

Not by default. Recreating a collection changes UUIDs, indexes, validators, sharding, privileges, and data meaning. Migrations/deployments should govern schema creation. A change-stream consumer **should not arbitrarily create schemas** upon seeing a drop.

## 12. State Machine for Consumers Encountering `invalidate`

A production handler has more states than just "running" and "retrying".

~~~mermaid
flowchart TD
    A["STREAMING"] -->|normal event| B["PROCESSING"]
    B -->|commit effect + checkpoint| A
    A -->|temporary error| C["RETRY_WAIT"]
    C -->|token still valid| A
    A -->|invalidate| D["INVALIDATED"]
    D -->|approved migration / new scope| E["START_AFTER"]
    E -->|new valid watch| A
    D -->|unapproved| F["PAUSED + ALERT"]
    C -->|history lost| G["RECOVERY_REQUIRED"]
    G -->|rebuild / reconcile| H["NEW_BASELINE"]
    H --> A
~~~

### 12.1. Handle `invalidate` before business event filtering

If a server-side pipeline matches only operationType=insert/update and strips all invalidate/DDL signals, the consumer can miss critical termination cues. A safer design receives **all lifecycle-relevant operation types**, handles invalidate/control events first, and forwards only business events to domain handlers.

If server-side filtering is needed to reduce traffic, verify filtering does not break invalidate detection or resuming by testing on a real MongoDB Server.

### 12.2. Never checkpoint past an unhandled control event

If you receive an invalidate token without yet deciding the new scope, saving it as a normal checkpoint and auto-retrying can restart the system with the wrong option. Persist **lastInvalidateToken + INVALIDATED state**, along with DDL info, so recovery logic decides between startAfter and rebuild.

### 12.3. State persistence

~~~javascript
{
  _id: "orders-projection-v1",
  state: "INVALIDATED",
  watchScope: "commerce.orders",
  lastInvalidateTokenJson: "{ \"_data\": \"...\" }",
  reason: "collection_drop",
  detectedAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

In multi-instance systems, enforce an **owner lease/fencing token** restricting which worker may mutate state, preventing two consumers from concurrently choosing conflicting resume points.

## 13. Oplog Retention: Resume Tokens Do Not Preserve History

MongoDB uses the oplog to record replica set operation history. The oplog acts as a bounded history region; under heavy writes, old entries get evicted.

~~~text
Oplog window:
|---------- retained history ----------|
T_old                               T_new

Consumer checkpoint at T_old - 2h
If T_old advances past the checkpoint, resuming fails.
~~~

### 13.1. Retention does not equal checkpoint record age

A checkpoint document can sit in an application collection for 1 year. **That does not force MongoDB to keep 1 year of oplog**. The server can resume only while sufficient history remains to locate the token/timestamp.

### 13.2. Never promise "guaranteed 24-hour retention" from oplog size alone

Actual history duration depends on:

- Oplog size.
- Deployment write rate.
- Transaction/bulk behavior.
- MongoDB retention settings.
- Disk capacity and operational policies.
- Traffic spikes (peak writes differ from daily averages).

Supported MongoDB versions offer a minimum oplog retention setting; it trades off disk space and must never be treated as infinite resumability. Always measure **actual earliest oplog entry** and consumer lag.

### 13.3. Formula for observing the safety margin

Suppose:

- Remaining actual history is **H minutes**.
- Consumer lags latest events by **L minutes**.
- Expected incident repair and catch-up duration is **R minutes**.

A rough warning indicator:

\[
M=H-(L+R)
\]

If M <= 0, the consumer risks falling past the history window during recovery. **This formula is for capacity planning only**, not a MongoDB guarantee; event timestamps, oplog age, and sharded idle shards can complicate real measurements.

### 13.4. Oplog window on sharded clusters

A sharded cluster change stream spans multiple shards. History/resume windows depend on all involved shards, chunk/shard migrations, and mongos activity. Never inspect one shard's oplog window and conclude the entire stream is safe.

## 14. History Lost: When Retries No Longer Help

If a resume token points to an operation already evicted from the oplog, MongoDB lacks the history needed to continue from that checkpoint. Errors may appear as **ChangeStreamHistoryLost** (error code 286 in some cases) or driver/server-specific messages.

### 14.1. Never delete the checkpoint and start from now

~~~text
T0: checkpoint processed up to E100
T1: app offline too long
T2: oplog evicted E101..E900
T3: resume from E100 fails
T4: consumer drops token, watches from now
=> E101..E900 are never applied
~~~

If read models, search indexes, metrics, or notifications depend on all events, this creates a severe **data gap**. Starting from now is valid only when business stakeholders **explicitly accept the loss** and log the gap.

### 14.2. Classify errors before retrying

| Error | Handling |
| --- | --- |
| Temporary disconnect | Retry with backoff/jitter, resume from checkpoint |
| Resumable election/repl state change | Let driver handle per contract; app prepares cursor restart |
| Poison event from code/validation | Do not checkpoint past it; DLQ/quarantine per policy and recover |
| Invalidate | PAUSED/INVALIDATED; evaluate startAfter/new scope |
| Change stream history lost | **REBUILD/RECONCILIATION** or explicit data-loss acceptance |
| Authentication/authorization failure | Fix credentials/policy, do not retry forever |
| Pipeline compatibility error | Fix pipeline/deployment, do not swap tokens arbitrarily |

### 14.3. Recovery must not open a new gap

Rebuilding a projection must pair **current snapshots** with **events preserved from a clear anchor**. Simply taking 20 minutes to read a snapshot and then watching from now risks dropping or misapplying updates occurring during those 20 minutes.

A sound pattern:

1. Stop the old worker and hold ownership/lease.
2. Select a recovery baseline tied to a valid **stream position**.
3. Open/anchor the stream from that position before scanning the snapshot, or use a snapshot/read timestamp with an appropriate consistency contract.
4. Rebuild the read model from source data.
5. Replay changes occurring during the rebuild **in order** and idempotently.
6. Switch traffic to the rebuilt read model once caught up.
7. Persist checkpoint and recovery state via a verified workflow.

**Algorithmic details** depend on topology, read concern, and data volume. If the history window is completely gone and no other event store exists, intermediate historical transitions cannot be reconstructed from current state alone.

## 15. Retention of Pre-Images and Post-Images Is a Separate Issue

MongoDB 6.0 and later support **change stream pre- and post-images** with proper collection configuration.

~~~javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

Images capture data "before/after" an operation, distinct from **resume tokens** and oplog event entries.

### 15.1. Two retention concepts not to conflate

| Component | Role | Limit |
| --- | --- | --- |
| Oplog entries | Basis of change stream history and resumability | Governed by oplog retention window |
| Pre-images | Document before update/delete | Governed by feature config and pre/post-image retention |
| Post-images | Document after insert/update/replace | Governed by config/version/retention |
| Checkpoint collection | App's processed token/progress | Does not extend oplog history |
| Read model | Aggregated query state | Must rebuild/reconcile on gaps |

### 15.2. `expireAfterSeconds`

MongoDB offers the cluster parameter **changeStreamOptions.preAndPostImages.expireAfterSeconds** on supported deployments. When set to **off** (documented default), images are kept until the corresponding events roll off the oplog—never meaning "kept forever".

Once the corresponding oplog entry is evicted, images are deleted **even if** expireAfterSeconds is longer. Never infer from pre-image retention settings that an old resume token remains valid.

### 15.3. `fullDocument: updateLookup` is not a historical snapshot

~~~javascript
db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
~~~

When looking up a document for an update event, MongoDB returns the **current majority-committed version** at lookup time. A newer update may have run before lookup; fullDocument can differ from the state right after the event or be null in some cases.

If business rules require exact before/after states of a mutation, evaluate pre/post-images under their version/retention contracts using **required/whenAvailable** rather than treating updateLookup as an exact before/after snapshot.

## 16. Without a Long-Enough Oplog: Multi-Layered Resilience Strategy

A resilient system should include:

- **An oplog window larger than** worst-case consumer outage + catch-up time, plus a safety margin.
- **Monitoring of lag** and earliest available oplog history, not just service uptime.
- **Durable checkpoints** with backups.
- **Replay-safe effects** so reprocessing never corrupts data.
- **Rehearsed rebuild/reconcile procedures.**
- **DLQ/quarantine** for poison events without losing visibility.
- **Owner lease/fencing** when multiple replicas could contend for stream ownership.
- **Separate runbooks** for invalidate vs. network outages.

### 16.1. Do not raise retention blindly without measuring disk

Larger oplogs keep history longer yet consume disk and can affect infrastructure. MongoDB minimum retention settings trade off disk space; monitor disk usage, write throughput, and cluster capacity.

### 16.2. Do not let retries burn recovery time

If errors indicate history is lost, retrying the same token every hour lets the read model fall further behind. Transition to **RECOVERY_REQUIRED**, alert, and run a controlled rebuild.

## 17. Inbox: Recording Already-Applied Events

A common pattern is an **idempotent consumer/inbox**. Each event gets a unique key in a marker collection:

~~~javascript
{
  _id: "orders-projection-v1:sha256(eventResumeToken)",
  streamId: "orders-projection-v1",
  eventTokenJson: "{ \"_data\": \"...\" }",
  operationType: "update",
  appliedAt: ISODate("2025-06-01T12:00:01Z")
}
~~~

MongoDB enforces a unique index on **_id** in collections. Two attempts trying to insert the same marker cannot both commit independently.

### 17.1. Inbox key design

~~~text
inboxId = streamId + ":" + SHA256(serializeResumeToken(token))
~~~

**streamId** separates two projections sharing a source yet applying different effects. **Resume token** separates multiple events on the same Order. Never use documentKey._id as the sole inbox key, because one Order receives many valid updates.

### 17.2. `ClusterTime` is not event identity

Multiple events can share a clusterTime, especially inside transactions or sharded clusters. Never build inbox keys from clusterTime alone. For transaction correlation, lsid/txnNumber have MongoDB-version-specific semantics and do not replace event resume tokens.

### 17.3. Markers must commit durably with effects

If the marker is written yet the projection update fails, a retry seeing the marker skips the event and leaves the read model incomplete. Therefore marker and effect should be **atomic in a MongoDB transaction**, or use a recoverable state protocol.

### 17.4. In-memory deduplication is insufficient

An in-memory set of seen tokens disappears on restart and grows unboundedly. Use durable storage with unique constraints and retention longer than the maximum replay horizon.

## 18. Event Idempotency vs. Business Idempotency

| Effect | Safe to repeat? | Strategy |
| --- | --- | --- |
| Set status=PAID | Yes for the same state, though susceptible to reordering | Upsert + business version |
| Increment revenue | **No** | Unique Payment ID + atomic inbox/transaction |
| Push item into array | **No** | Unique item ID or set semantics |
| Send email | Not guaranteed | Outbox + downstream idempotency |
| Mark event processed | Yes with unique marker | Unique inbox key per stream/token |
| Delete projection | Possible if version-matched | Version/order guard |

### 18.1. Two events with distinct tokens can represent the same business command

~~~text
E1: token=T1, orderId=O1, paymentId=P100
E2: token=T2, orderId=O1, paymentId=P100
~~~

If a payment request is recorded twice, E1 and E2 have distinct stream identities, yet business payment **P100** must be processed once per domain rules. A unique index could be:

~~~javascript
db.payments.createIndex(
  { tenantId: 1, paymentId: 1 },
  { unique: true, name: "uniq_payment_per_tenant" }
);
~~~

**Inbox tokens** guard against replaying the same event; **business paymentId** guards against duplicate commands at a higher layer.

### 18.2. Set operations do not protect ordering

~~~text
E1: status=PAID, version=5
E2: status=REFUNDED, version=6
~~~

If a consumer applies E2 first and E1 second, `set(status=PAID)` overwrites newer data even though both events ran once. Serialize per key or compare aggregate **versions**; never compare resume token strings as versions.

## 19. Atomic Apply + Checkpoint via MongoDB Transactions

Architecture pattern:

~~~text
orders (source)
processed_change_events (inbox)
order_summaries (projection)
change_checkpoints (checkpoint)
~~~

Inbox, projection, and checkpoint can be written inside one MongoDB transaction when in the **same deployment**, sharing the proper session/transaction manager. Keep transactions short; never wait on cursors or make HTTP calls inside a transaction.

### 19.1. Configuring the manager

~~~java
package com.example.changestream;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class ChangeStreamTxConfiguration {

    @Bean("mongoTransactionManager")
    MongoTransactionManager transactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

MongoDB must support transactions (replica set or compatible sharded cluster). Invoke `@Transactional` methods through Spring proxies, avoiding self-invocation.

### 19.2. A transactional handler specifically for INSERT

~~~java
package com.example.changestream;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Objects;
import org.bson.BsonValue;
import org.bson.Document;
import com.mongodb.client.model.changestream.OperationType;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderChangeApplier {

    private static final String STREAM = "orders-projection-v1";
    private final MongoTemplate template;

    public OrderChangeApplier(MongoTemplate template) {
        this.template = template;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void applyInsert(ChangeStreamEvent<Document> event) {
        if (event.getOperationType() != OperationType.INSERT) {
            throw new IllegalArgumentException(
                "INSERT events only");
        }

        BsonValue token = Objects.requireNonNull(
            event.getResumeToken(), "Missing resume token");
        String tokenJson = token.asDocument().toJson();
        String eventId = STREAM + ":" + sha256(tokenJson);
        Query eventKey = Query.query(
            Criteria.where("_id").is(eventId));

        boolean alreadyApplied = template.exists(
            eventKey, "processed_change_events");

        if (!alreadyApplied) {
            template.insert(
                new Document("_id", eventId)
                    .append("streamId", STREAM)
                    .append("tokenJson", tokenJson)
                    .append("appliedAt", java.util.Date.from(
                        Instant.now())),
                "processed_change_events");

            Document body = Objects.requireNonNull(
                event.getBody(), "Insert body required");
            Object orderId = Objects.requireNonNull(
                body.get("_id"), "Order ID required");

            template.upsert(
                Query.query(Criteria.where("_id").is(orderId)),
                new Update()
                    .set("tenantId", body.getString("tenantId"))
                    .set("status", body.getString("status"))
                    .set("orderNo", body.getString("orderNo")),
                "order_summaries");
        }

        template.upsert(
            Query.query(Criteria.where("_id").is(STREAM)),
            new Update()
                .set("resumeTokenJson", tokenJson)
                .set("streamState", "STREAMING")
                .set("checkpointAt", java.util.Date.from(
                    Instant.now())),
            "change_checkpoints");
    }

    private static String sha256(String raw) {
        try {
            MessageDigest md =
                MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(
                md.digest(raw.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                "SHA-256 unavailable", ex);
        }
    }
}
~~~

### 19.3. Limits to understand before copying this code

- **Only for INSERT events**. UPDATE, REPLACE, DELETE, and INVALIDATE require distinct handling; you cannot unconditionally read getBody().
- **template.exists does not lock concurrency**. Two workers may both see false; the unique _id and MongoDB transaction resolve conflicts. Retry **the whole transaction** where appropriate.
- **Same-transaction checkpointing** is safe only when a single active owner preserves token order; multiple writers updating tokens out of order can regress checkpoints. Use leases/fencing.
- Uses SHA-256 for a compact inbox key; token serialization must stay deterministic across reads/writes. Never truncate opaque tokens.
- Never keep a transaction open while the change stream awaits events.
- This is an integration pattern lacking retry configs, transaction options, leases, logging, and migrations.

### 19.4. When an old token replays

When the marker already exists, the handler skips reapplying the projection yet still advances the checkpoint inside the transaction. Under **single-owner sequential processing**, this serves as a clean recovery path. With multiple owners, fencing/checkpoint compare-and-set is mandatory rather than unconditional upserts.

## 20. Side Effects Outside MongoDB: Outbox and Downstream Idempotency

Suppose a PAID event must send an email or publish a message:

~~~text
Change event E1
     |
     v
MongoDB transaction:
  - insert inbox marker E1
  - update order_summaries
  - insert outbox record (fixed business key)
  - update checkpoint E1
     |
     v
Outbox worker -> Email provider / Broker
~~~

### 20.1. Why not send email inside the transaction?

~~~java
// Anti-pattern: email will not roll back if MongoDB aborts.
emailClient.sendConfirmation(order);
mongoTemplate.upsert(
    checkpointQuery, checkpointUpdate, "change_checkpoints");
~~~

If email succeeds yet MongoDB rolls back, retrying the event sends the email again. MongoDB transactions do not control external email providers.

### 20.2. Outbox idempotency key

~~~javascript
{
  _id: "order-paid:shop-a:P100",
  type: "ORDER_PAID_EMAIL",
  tenantId: "shop-a",
  orderId: ObjectId("507f1f77bcf86cd799439011"),
  paymentId: "P100",
  state: "PENDING",
  attempts: 0
}
~~~

The unique _id ensures one outbox command per business payment. The outbox sender can retry on timeouts; if downstream accepts idempotency keys, forward the exact same key on every attempt.

### 20.3. What if the email provider lacks idempotency?

You cannot guarantee "exactly-once email" with a local outbox alone. You can minimize duplicates using provider message IDs, suppression windows, receiver-side inboxes, or business state checks, though a timeout window still leaves uncertain outcomes. Document the contract and configure retries accordingly.

### 20.4. Dedupe retention

Never TTL-delete inbox markers after 1 day if the application might replay/rebuild across 7 days. Marker retention must exceed the longest expected replay/reconciliation window, or rely on longer-lived business idempotency. Marker TTL is **separate from** oplog retention.

## 21. Processing Order, Parallelism, and Checkpointing

A change stream delivers events ordered per stream contract, yet consumers can break order by running handlers concurrently.

~~~java
// Can let E2 complete before E1:
return eventFlux.flatMap(this::processAsync, 32);
~~~

For instance, E1(status=PAID,version=5) takes 2 seconds while E2(status=REFUNDED,version=6) takes 10 ms. E2 can write before E1, leaving the final projection inverted.

### 21.1. `concatMap`: straightforward choice for one checkpoint

~~~java
return eventFlux.concatMap(this::processAndCheckpoint);
~~~

concatMap waits for the prior inner Publisher to complete before starting the next event. With one subscription and one checkpoint, **processing completion order** matches event order.

### 21.2. When throughput demands parallelism

You can partition by aggregateId and run sequentially within each key while running across keys in parallel. However, the **stream-wide checkpoint** must advance only to the **highest contiguous processed position**: never checkpoint E500 while E499 has not committed.

This coordination is much harder than concatMap, especially on sharded streams. Never run high-concurrency flatMap where every handler blindly upserts the checkpoint.

### 21.3. Owner leases and fencing

With two instances:

~~~text
Worker A: processing E101..E200
Worker B: still processing E101..E150
~~~

Worker B might accidentally save token T150 after A saved T200. Because resume tokens are opaque, string comparison cannot tell whether "T200 is greater than T150".

Solution: **one active owner per stream**, bounded leases, a fencing generation bumped on every ownership transfer, and conditional checkpoint updates restricted to the authorized generation. Across leader failover, retries must rely on durable state rather than the old worker's RAM.

### 21.4. Multiple events can share `clusterTime`

A single transaction can produce multiple change events, so you cannot dedupe or checkpoint per event by clusterTime alone. Event resume tokens and stream order supply the required precision for consumption.

## 22. Spring Data MongoDB: Basic Reactive Change Stream

Spring Data provides **ReactiveMongoTemplate** to consume change streams as a Flux:

~~~java
package com.example.changestream;

import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;

public class RawOrderWatcher {

    private final ReactiveMongoTemplate template;

    public RawOrderWatcher(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Flux<ChangeStreamEvent<Document>> events() {
        return template.changeStream(Document.class)
            .watchCollection("orders")
            .listen();
    }
}
~~~

**Document.class** reads bodies as BSON-mapped Documents rather than forcing a domain type unsuitable for delete/invalidate/DDL events.

### 22.1. Not every event has a body

~~~java
Flux<ChangeStreamEvent<Document>> events = watcher.events();

return events.doOnNext(event -> {
    System.out.println(event.getOperationType());
    System.out.println(event.getResumeToken());
});
~~~

Never call event.getBody().getString("status") before checking operationType and null. **DELETE** and **INVALIDATE** lack fullDocument unlike INSERT.

### 22.2. Subscriptions and cursors

A change stream Flux is a long-lived Publisher. Without a subscriber, no actual watch command runs. On application shutdown, dispose subscriptions/close cursors via application lifecycle; never accidentally open duplicate streams sharing one checkpoint.

### 22.3. Filter deliberately

If you only care about status=PAID, filter business logic **after handling control events**, or use a carefully tested server-side pipeline. A server-side filter that drops all invalidate/DDL signals can blind the consumer to critical state transitions.

### 22.4. Reactive does not mean exactly-once

Flux, backpressure, retryWhen, and concatMap are composition tools. No operator atomically checkpoints alongside external effects, extends the oplog, or supplies business idempotency.

## 23. Resuming a Reactive Stream from a Checkpoint

Spring Data MongoDB provides **ChangeStreamOptions** with resumeAfter/startAfter builders. Given a token persisted as Extended JSON:

~~~java
import org.bson.BsonDocument;
import org.bson.BsonValue;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Flux;

public Flux<ChangeStreamEvent<Document>> openResumedStream(
        ReactiveMongoTemplate template,
        String tokenJson) {

    BsonValue token = BsonDocument.parse(tokenJson);
    ChangeStreamOptions options = ChangeStreamOptions
        .builder()
        .resumeAfter(token)
        .build();

    return template.changeStream(
        "orders", options, Document.class);
}
~~~

This snippet uses the ChangeStreamOptions overload on **ReactiveMongoOperations**. Current Spring Data versions also provide fluent changeStream(...).watchCollection(...).resumeAfter(token).listen().

### 23.1. What if no checkpoint exists yet?

If a service starts for the first time with no token:

~~~java
ChangeStreamOptions options = ChangeStreamOptions.empty();
~~~

This opens the stream for changes **from watch startup**, without replaying historical documents. If read models need existing data, combine an **initial snapshot/build + stream anchor** with a gap-free handoff plan.

### 23.2. Never use `resumeAfter` after `invalidate`

If the checkpoint store records **state=INVALIDATED** with an invalidate event token, take an approved recovery branch with:

~~~java
ChangeStreamOptions options = ChangeStreamOptions
    .builder()
    .startAfter(invalidateToken)
    .build();
~~~

Never apply that branch blindly to every token; remember the token must still fall within oplog history.

### 23.3. Serialization must preserve BSON types

BsonDocument.parse illustrates handling an Extended JSON token stored intact. Never serialize tokens by stripping _data strings or hashing and attempting to reconstruct tokens from hashes; **hashes are only for inbox keys**, never for resuming streams.

### 23.4. Persist pipeline version

Checkpoints should store watch scope, pipeline version, and option sets used when creating the token. Changing pipelines/filters while resuming from an old token can behave unpredictably per MongoDB warnings.

## 24. Reloading Checkpoints on Every Reactive Retry

A common mistake:

~~~java
// Anti-pattern: options built once from an old token.
Flux<ChangeStreamEvent<Document>> stream =
    openResumedStream(template, startupTokenJson);

return stream.retryWhen(retryPolicy);
~~~

On retry, the publisher resubscribes using **startupTokenJson**, even if the consumer already processed and checkpointed thousands of events while running.

### 24.1. Use `Flux.defer` and reload durable checkpoints

~~~java
import java.util.Optional;
import org.bson.BsonDocument;
import org.bson.BsonValue;
import org.bson.Document;
import org.springframework.data.mongodb.core.ChangeStreamEvent;
import org.springframework.data.mongodb.core.ChangeStreamOptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public Flux<ChangeStreamEvent<Document>> freshOnSubscribe() {
    return Flux.defer(() ->
        reactiveCheckpointStore.loadTokenJson("orders-projection-v1")
            .map(json -> Optional.of(
                (BsonValue) BsonDocument.parse(json)))
            .defaultIfEmpty(Optional.empty())
            .flatMapMany(optional -> {
                ChangeStreamOptions options = optional
                    .map(token -> ChangeStreamOptions.builder()
                        .resumeAfter(token)
                        .build())
                    .orElseGet(ChangeStreamOptions::empty);

                return reactiveTemplate.changeStream(
                    "orders", options, Document.class);
            })
    );
}
~~~

This snippet belongs in a class with injected **reactiveTemplate** and **reactiveCheckpointStore**, where the store exposes **Mono<String> loadTokenJson(String streamId)**. It is a skeleton showing how options are built **per subscription**.

### 24.2. Handling `INVALIDATED`/`RECOVERY_REQUIRED`

The snippet above only handles checkpoints in normal STREAMING state. Production code must inspect **state as well**, not just the token:

- STREAMING: valid token → resumeAfter.
- NEW: no token yet → apply initial-sync policy.
- INVALIDATED: do not auto-resumeAfter; pause or approved startAfter.
- RECOVERY_REQUIRED: do not retry; rebuild/reconcile.

### 24.3. Apply retry after the processing chain

~~~java
return freshOnSubscribe()
    .concatMap(this::processAndCheckpoint)
    .retryWhen(retryPolicy);
~~~

When the processing chain errors, retryWhen resubscribes from the top of **Flux.defer**, reloading the latest checkpoint. Ensure the policy **separates retryable and non-retryable errors**; never retry invalidate or history-lost infinitely.

### 24.4. Never ignore errors and still checkpoint

~~~java
// Anti-pattern if silently skipping unprocessed events:
return process(event)
    .onErrorResume(ex -> Mono.empty())
    .then(saveCheckpoint(event.getResumeToken()));
~~~

This marks the event processed even when the handler failed. If using a DLQ/quarantine, clearly define when an event is **durably handed off** so advancing the checkpoint is safe.

## 25. Reactive Transactions and Synchronous `MongoTemplate` Do Not Share Context

The transactional service in Section 19 used synchronous **MongoTemplate** and **MongoTransactionManager**. Never invoke it inside a reactive stream expecting it to join a ReactiveMongoTransactionManager transaction.

~~~java
// Misleading pattern:
return eventFlux.flatMap(event ->
    Mono.fromRunnable(() -> syncApplier.applyInsert(event))
);
~~~

This runs blocking code inside the reactive subscription, risking thread starvation. If you must wrap a legacy blocking API, isolating on a scheduler like boundedElastic is **only a temporary bridge**, and sync transactions keep their own context.

### 25.1. `ReactiveMongoTransactionManager`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
class ReactiveChangeTxConfiguration {

    @Bean("reactiveMongoTransactionManager")
    ReactiveMongoTransactionManager tx(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

A reactive transactional processing chain:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

TransactionalOperator operator =
    TransactionalOperator.create(
        reactiveMongoTransactionManager);

Mono<Void> effect = insertInbox(event)
    .then(updateProjection(event))
    .then(saveCheckpoint(event))
    .then();

return effect.as(operator::transactional);
~~~

**insertInbox, updateProjection, and saveCheckpoint** in this skeleton must return Publishers from the **same reactive MongoDB infrastructure** and share the active session context. This pattern only illustrates the atomic chain for unapplied events; production needs the **already-applied marker** branch and duplicate-key retry handling.

### 25.2. Combining `concatMap` with transactions

~~~java
return sourceEvents
    .concatMap(event ->
        applyIdempotentlyInReactiveTransaction(event))
    .then();
~~~

Never wrap the entire **sourceEvents** stream in one transaction because change streams run indefinitely. Scope transactions to **one event or a small batch**, committing and releasing resources promptly.

### 25.3. Callbacks/transactions vs. exactly-once

Reactor Context guarantees transaction propagation along the reactive chain. However, it does not create business idempotency, guarantee outbox uniqueness, or make external HTTP side effects atomic.

## 26. Synchronous: `MessageListenerContainer` and `ChangeStreamRequest`

Spring Data MongoDB also supports change streams through the **blocking driver** and messaging infrastructure:

~~~java
import org.bson.Document;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequest;
import org.springframework.data.mongodb.core.messaging.ChangeStreamRequest.ChangeStreamRequestOptions;
import org.springframework.data.mongodb.core.messaging.DefaultMessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.MessageListener;
import org.springframework.data.mongodb.core.messaging.MessageListenerContainer;
import org.springframework.data.mongodb.core.messaging.Subscription;
import org.springframework.data.mongodb.core.ChangeStreamOptions;

MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);

MessageListener<ChangeStreamDocument<Document>, Document> listener =
    message -> {
        // Placeholder receiver only. Production handlers must
        // classify operationType, transactions, checkpoints, and errors.
        System.out.println(message.getRaw());
    };

ChangeStreamRequestOptions options =
    new ChangeStreamRequestOptions(
        "commerce", "orders", ChangeStreamOptions.empty());

container.start();
Subscription subscription = container.register(
    new ChangeStreamRequest<>(listener, options),
    Document.class
);

// On application shutdown: cancel subscription and stop container.
subscription.cancel();
container.stop();
~~~

This snippet illustrates the API rather than a long-running service, since it cancels right after registering. In production, manage the container via **Spring lifecycle** and stop it on application shutdown.

### 26.1. Why not run blocking listeners in WebFlux?

MessageListenerContainer runs long-lived tasks on top of the sync driver. It fits managed workers, not callbacks running directly inside an HTTP event loop. For heavy stream workloads or reactive apps, Spring Data recommends preferring **Reactive Change Streams** to reduce thread overhead.

### 26.2. Error handlers must be explicit

Spring Data's messaging layer provides **ErrorHandler** hooks. Default error logging is insufficient for workflows that cannot drop events. Add metrics, checkpoint state, retry/restart policies, and alerts when listeners stop.

### 26.3. Listeners must commit before reporting progress

Never treat the start of a listener callback as last processed. If a callback hands work off asynchronously to another thread queue and returns immediately, checkpointing must follow actual **completion/commit** of that work.

### 26.4. Never let two listeners share a stream without coordination

Two instances registering the same collection watch normally observe **the same changes**; change streams do not turn into competing-consumers work queues distributing each event to one instance. Use explicit leader/leases or deliberate fan-out and idempotency.

## 27. Error Handling, Backoff, and Poison Events

A consumer should classify errors:

| Error category | Examples | Recommended action |
| --- | --- | --- |
| Resumable/transient | Connection reset, some election errors | Backoff + reconnect from durable checkpoint |
| Processing transient | MongoDB projection write timeout | Retry transaction/processing; never pre-checkpoint |
| Processing permanent | Invalid event schema, missing required field | Quarantine/DLQ or pause; never silently skip |
| Authorization | Watch read privilege revoked | Alert + fix privileges; avoid tight retry loops |
| Invalidate | Drop/rename/dropDatabase affecting scope | State INVALIDATED, apply startAfter/new scope policy |
| Retention exhausted | Resume token outside oplog | RECOVERY_REQUIRED, rebuild/reconcile |
| Incompatible pipeline | Changed filter/options on resume | Fix/deploy migration, never swap tokens arbitrarily |
| Duplicate marker conflict | Event already applied or concurrent race | Check marker/transaction, retry handler if needed |

### 27.1. Bounded `retryWhen`

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Retry retryPolicy = Retry.backoff(
        8, Duration.ofSeconds(1))
    .maxBackoff(Duration.ofMinutes(1))
    .jitter(0.25)
    .filter(this::isRetryableTransientFailure);
~~~

isRetryableTransientFailure is an **application error classifier** built from MongoDB exceptions/error labels, Spring translated exceptions, and business errors.

Never pass a predicate that always returns true. Invalidation, history loss, and validation errors must transition state/alert rather than retrying the same token forever.

### 27.2. After retries are exhausted?

Some systems allow a supervisor to restart the worker, provided it:

- Preserves the last committed checkpoint intact.
- Distinguishes STOPPED/PAUSED/RECOVERY_REQUIRED states.
- Records error codes and last attempt timestamps.
- Alerts according to SLOs.
- **Reloads the checkpoint from storage** on restart rather than using stale local variables.

### 27.3. Poison events

For example, an event carries an unknown status enum that fails converter parsing. Retrying it forever blocks all subsequent events, yet checkpointing past it drops a business change.

Choose an auditable policy:

1. **Pause + alert** to update schema/handler and replay.
2. **Durable quarantine/DLQ** storing the token and raw event (redacted if sensitive), logging an intentional skip decision.
3. **Rebuild projection** after fixing the bug.

When checkpointing after DLQ insertion, verify the DLQ write/ACK is durable and replay permissions exist.

### 27.4. Failures from `fullDocument` lookup

fullDocument=updateLookup can return null or a newer document state; handlers must not treat this as a network error to retry endlessly. Inspect operationType, updateDescription, source schema/version, and consistency requirements.

## 28. Observability: Measuring Lag and Retention Exhaustion Risk

A worker that "stays running" yet lags hours behind is a silent incident even with zero exceptions.

| Metric | Meaning |
| --- | --- |
| lastEventReceivedAt | Last time consumer received an event |
| lastDurableCheckpointAt | Last time checkpoint committed |
| lastProcessedClusterTime | Cluster time of last processed event |
| eventProcessingLatency | Apply + checkpoint duration |
| consumerLag | Delay relative to cluster/source progress |
| oplogHistoryWindow | Remaining resumable history on the deployment |
| retentionSafetyMargin | Oplog window minus lag and recovery buffer |
| duplicateDetectedCount | Replays intercepted by inbox |
| checkpointWriteErrors | Risk of tokens failing to advance |
| invalidationCount | Namespace/scope invalidations |
| historyLostCount | Loss of resumability incidents |
| deadLetterCount | Quarantined events |
| transactionAbortCount | Conflicts, retries, MongoDB errors |
| activeStreamOwners | Detect multiple workers sharing one checkpoint |
| streamReconnects | Network drops, elections, unstable cursors |

### 28.1. `ClusterTime` differs from wall clock

MongoDB event.clusterTime is a **BSON Timestamp**, not a unique instant with nanosecond wall-time semantics. Use cluster time for correlation/progress, never as a unique event ID.

### 28.2. Idle streams emit no new events

When collections have low write traffic, an old lastEventReceivedAt does not prove the consumer died. Combine cursor health, high-watermark tokens, worker heartbeats, and oplog metrics. In sharded deployments, idle shards can slow high-watermark progression.

### 28.3. Alerting on retention margin

Example alert rule:

~~~text
WARN:  estimated history window - consumer lag < 2h
CRIT:  estimated history window - consumer lag < 30m
~~~

Thresholds are illustrative; size them for worst-case incident repair + catch-up throughput and observation uncertainty.

### 28.4. Protecting tokens and event payloads

Tokens/metadata and raw change events can expose operational state or personal data. Restrict checkpoint read privileges, enforce encryption/secrets policies, and avoid dumping fullDocument in debug logs.

## 29. Unit Testing: Serializing Tokens Without Losing BSON Shape

Resume tokens must be saved and restored intact. A unit test can verify **Extended JSON round-tripping** with a synthetic token:

~~~java
package com.example.changestream;

import static org.assertj.core.api.Assertions.assertThat;

import org.bson.BsonDocument;
import org.bson.BsonString;
import org.junit.jupiter.api.Test;

class ResumeTokenCodecTest {

    @Test
    void tokenCanRoundTripThroughExtendedJson() {
        BsonDocument token = new BsonDocument(
            "_data", new BsonString("opaque-example"));

        String serialized = token.toJson();
        BsonDocument restored =
            BsonDocument.parse(serialized);

        assertThat(restored).isEqualTo(token);
    }
}
~~~

**Attention:** synthetic tokens only test encoding/decoding, not real tokens valid for MongoDB resumeAfter. Integration tests must capture real tokens from MongoDB.

### 29.1. Hashes do not replace tokens

SHA-256 of a token makes a fine inbox key, yet **you cannot reconstruct a resume token** from a hash to open a change stream. Store the full BSON-type-preserving serialized token separately.

### 29.2. Testing marker deduplication

A MongoDB integration test can:

1. Insert inbox marker with _id = streamId + ":" + sha256(token).
2. Attempt inserting the same marker a second time.
3. Assert duplicate-key exception and that only one marker exists.
4. Invoke the transactional handler twice with the same event; assert read model, payment counter, and outbox are not duplicated.
5. Check the committed checkpoint after processing or replay.

Steps 4–5 prove **full handler** idempotency, not just unique indexing.

### 29.3. Failure injection

In a MongoDB test database, inject exceptions after marker insert but before projection update, and after projection but before checkpoint. Assert the transaction aborts with none of marker/projection/checkpoint committed, then retry the event and verify the final result applied exactly once.

## 30. Integration Test: Capturing a Real Token and Calling `resumeAfter`

Example using MongoDB Testcontainers replica set and Java Sync Driver via MongoTemplate:

~~~java
package com.example.changestream;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.OperationType;
import org.bson.BsonDocument;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class ChangeStreamResumeIntegrationTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0"));

    @DynamicPropertySource
    static void mongoProperties(
            DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri",
            mongo::getReplicaSetUrl);
    }

    @Autowired MongoTemplate template;

    @Test
    void resumesAfterLastObservedEvent() {
        String collection = "watch_test_"
            + UUID.randomUUID().toString().replace("-", "");
        template.createCollection(collection);

        try {
            BsonDocument token;

            try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                    cursor = template.getCollection(collection)
                        .watch()
                        .maxAwaitTime(500, TimeUnit.MILLISECONDS)
                        .cursor()) {

                template.insert(
                    new Document("_id", new ObjectId())
                        .append("status", "CREATED"),
                    collection);

                ChangeStreamDocument<Document> first =
                    awaitNext(cursor, Duration.ofSeconds(10));

                assertThat(first.getOperationType())
                    .isEqualTo(OperationType.INSERT);
                token = first.getResumeToken();
                assertThat(token).isNotNull();
            }

            try (MongoChangeStreamCursor<ChangeStreamDocument<Document>>
                    resumed = template.getCollection(collection)
                        .watch()
                        .resumeAfter(token)
                        .maxAwaitTime(500, TimeUnit.MILLISECONDS)
                        .cursor()) {

                template.insert(
                    new Document("_id", new ObjectId())
                        .append("status", "PAID"),
                    collection);

                ChangeStreamDocument<Document> second =
                    awaitNext(resumed, Duration.ofSeconds(10));

                assertThat(second.getOperationType())
                    .isEqualTo(OperationType.INSERT);
                assertThat(second.getFullDocument()
                    .getString("status")).isEqualTo("PAID");
                assertThat(second.getResumeToken())
                    .isNotEqualTo(token);
            }
        } finally {
            template.dropCollection(collection);
        }
    }

    private static ChangeStreamDocument<Document> awaitNext(
            MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor,
            Duration timeout) {

        long deadline = System.nanoTime() + timeout.toNanos();
        while (System.nanoTime() < deadline) {
            ChangeStreamDocument<Document> event =
                cursor.tryNext();
            if (event != null) {
                return event;
            }
        }
        throw new AssertionError(
            "Timed out waiting for a change event");
    }
}
~~~

### 30.1. Cursor opens before insert

Change streams emit events starting from when watching begins. If an insert occurs **before the watch is genuinely open**, the event can be missed. Here calling cursor() on the sync driver opens the watch before inserting.

### 30.2. Requires a MongoDB replica set

MongoDBContainer with getReplicaSetUrl provisions the right test topology on supported Testcontainers versions. The test requires Docker, Spring Boot test, and the MongoDB driver. Never run against standalone mongod or production DBs.

### 30.3. This does not test idempotency yet

This test verifies server token generation and resuming past a prior event via resumeAfter. The transactional inbox/replay test in Section 29 is still required to prove business effects do not repeat.

### 30.4. Driver auto-resume does not replace checkpoints

MongoDB drivers can auto-resume certain resumable errors, yet cannot replace durable application checkpoints for restarting after process crashes.

## 31. Testing `invalidate` in a Controlled Environment

Never drop a production collection to test this. Use a disposable collection and **two mongosh sessions** connected to the same replica set.

### 31.1. Terminal A: open watch

~~~javascript
use test_change_streams;

db.watch_orders_test.insertOne({
  _id: "seed",
  status: "CREATED"
});

const stream = db.watch_orders_test.watch();

while (!stream.isClosed()) {
  const event = stream.tryNext();
  if (event !== null) {
    printjson(event);
    if (event.operationType === "invalidate") {
      print("Save the REAL event._id token");
      break;
    }
  }
}
~~~

### 31.2. Terminal B: drop the test collection

~~~javascript
use test_change_streams;

// ONLY run on the test collection:
db.watch_orders_test.drop();
~~~

Terminal A observes relevant control events and an **invalidate** event; the collection watch cursor closes.

### 31.3. Comparing `resumeAfter` and `startAfter`

Save the real invalidate token into invalidateToken. If you attempt:

~~~javascript
db.watch_orders_test.watch(
  [],
  { resumeAfter: invalidateToken }
);
~~~

MongoDB forbids resumeAfter past invalidate. To open a new stream after invalidate:

~~~javascript
db.watch_orders_test.watch(
  [],
  { startAfter: invalidateToken }
);
~~~

startAfter still depends on the history window, namespace/watch scope, and collection lifecycle; it does not restore dropped data. Real systems must stop/reconcile or wait for collection recreation per migration.

### 31.4. State machine test

Upon invalidate, assert the consumer:

1. Transitions to **INVALIDATED**.
2. Saves the invalidate token and reason.
3. Stops applying business events for the old namespace.
4. Does not retry resumeAfter infinitely.
5. Alerts if drop/rename was unauthorized.
6. Calls startAfter/rebuilds only under an approved recovery policy.

### 31.5. Database watch scope

A separate test uses db.watch and drops a child collection to verify it **does not invalidate the database watch by default**. On database-level watches, dropDatabase is one operation that invalidates the stream. Never run this test on a database shared by other tests.

## 32. Testing History Loss and Crash Windows

Never intentionally overflow a production oplog to reproduce history loss. Test across layers instead:

| Test | How to run | Expected outcome |
| --- | --- | --- |
| Error classifier | Simulate ChangeStreamHistoryLost | RECOVERY_REQUIRED |
| No retry on non-resumable | Inject history-lost error | RetryWhen rejects |
| Replay same event | Deliver same token twice to handler | Projection/outbox not duplicated |
| Crash before effect | Inject exception before transaction | Checkpoint does not advance |
| Crash between effect and checkpoint | Inject exception inside transaction | Marker/effect/token all roll back |
| Crash after commit | Replay after commit | Inbox blocks duplicate effect |
| Two owners | Two competing workers | Unique marker/fencing protects state |
| Consumer lag | Slow down worker controllably | Alert fires before exceeding oplog window |
| Poison event | Body missing mandatory field | Pause/quarantine, no silent skip |
| Invalidate | Drop/rename in test namespace | PAUSED/INVALIDATED |
| Pipeline drift | Change pipelineVersion | Refuses blind resume from old token |

### 32.1. Real history loss in a dedicated environment

If an end-to-end server test is needed, use a **disposable** replica set, configure a small oplog/history window per supported MongoDB version, and generate enough writes to evict old entries. Never run on shared or production clusters. Write volume needed depends on sizing/throughput; never hardcode a magic count assuming it always suffices.

### 32.2. Verifying retries

Tests should assert attempt counts, backoff classification, unchanged checkpoints on failure, and accurate state transitions. Asserting merely that an exception was caught does not prove the worker prevented event loss.

### 32.3. Recovery drill

1. Stop the consumer in a test environment receiving continuous writes.
2. Observe lag and retention safety margin.
3. Simulate or trigger history loss on the test cluster.
4. Transition state to RECOVERY_REQUIRED.
5. Rebuild projection and reconcile snapshot.
6. Verify zero gaps between snapshot and new stream.
7. Restart the worker and monitor lag, duplicate count, and data parity.

### 32.4. Re-runs must be safe

A crucial test is **rebuilding the same snapshot multiple times**. If repeated rebuilds inflate revenue or resend notifications, your recovery workflow is not yet idempotent even if normal change stream handling has an inbox.

## 33. Practice Exercises

### Exercise 1: Event ID vs. Document ID

An event contains:

~~~javascript
{
  _id: { _data: "opaque-token-T1" },
  documentKey: {
    _id: ObjectId("507f1f77bcf86cd799439011")
  }
}
~~~

**Question:** Which token is used to resume?

**Answer:** Use **event._id** intact, not documentKey._id.

### Exercise 2: Two updates to the same Order

E1 moves Order O1 to PAID; E2 moves O1 to REFUNDED. Should we dedupe using only orderId=O1?

**Answer:** No. Those are two valid events, each needing its own marker; business-level deduplication must rely on a specific command, payment ID, or version.

### Exercise 3: Duplicate event

A consumer updated the projection then crashed before checkpointing. What might it see after restarting?

**Answer:** It may see the same event again. Handlers must be idempotent via unique markers/transactions or an equivalent mechanism.

### Exercise 4: Checkpoint before effect

Token T200 saved successfully, then the app crashed before processing E200. Result of resumeAfter(T200)?

**Answer:** Starts after E200, risking **losing E200's effect**. Never checkpoint before durable processing.

### Exercise 5: Checkpoint after effect

Effect committed yet checkpoint remained stale. Why is this trade-off normally acceptable?

**Answer:** Replay can occur, yet idempotent processing detects and discards duplicate effects; whereas checkpointing first can permanently lose events under normal stream continuation.

### Exercise 6: Atomic inbox

Which three write operations should share one MongoDB transaction when in the same database deployment?

**Answer:** **Insert inbox marker, apply projection/outbox, and update checkpoint**. That closes the transaction gap inside MongoDB.

### Exercise 7: Unique index

Two workers both see the marker absent and insert simultaneously. Does checking `exists` first prevent a race?

**Answer:** No. Only unique constraints on marker IDs, transaction conflict handling, and owner coordination properly guard against races.

### Exercise 8: Business duplicate

E1 has token T1, E2 has token T2, yet both carry paymentId=P100. Does a token-based inbox stop a double charge?

**Answer:** No. You need a **unique business paymentId + idempotency policy** at the payment layer.

### Exercise 9: Avoid blind `$inc`

A handler receives PAYMENT_CAPTURED and calls $inc(revenue,amount). What happens if the event replays?

**Answer:** Revenue doubles. Use an idempotent marker in the same transaction, or unique ledger/payment entries keyed by business key and aggregate from the ledger.

### Exercise 10: Collection invalidation

A collection watch is open and the collection is dropped. What event signals the stream is invalid?

**Answer:** **invalidate**. The cursor closes; the consumer must transition state and execute its recovery policy.

### Exercise 11: `resumeAfter` after `invalidate`

Can we call resumeAfter(invalidateToken) to continue like a normal network error?

**Answer:** No. MongoDB forbids resumeAfter crossing invalidate.

### Exercise 12: `startAfter`

Does startAfter(invalidateToken) automatically restore dropped documents?

**Answer:** No. It only opens a new stream after invalidate if history remains; schema and data state must be handled separately.

### Exercise 13: Watch scope

Does dropping a child collection necessarily invalidate a database-level watch?

**Answer:** No. Database-level watch scope differs from collection-level; dropDatabase is a case that invalidates a database watch.

### Exercise 14: Retention

Checkpoints stay for 365 days. Oplog retains only 6 hours of actual history. Consumer stops for 48 hours—will resuming succeed?

**Answer:** No. Checkpoint durability does not extend the oplog window; recovery is needed once token history is gone.

### Exercise 15: Expired history token

What is the most dangerous reaction to receiving ChangeStreamHistoryLost?

**Answer:** Deleting the token, starting from now, and silently skipping missed events. Report the gap and rebuild/reconcile, or explicitly record accepted data loss.

### Exercise 16: Pre-image retention

Does setting a huge expireAfterSeconds for pre/post-images make the oplog retain events forever?

**Answer:** No. Once an oplog entry is evicted, its associated images are also removed regardless of longer image retention settings.

### Exercise 17: `fullDocument` `updateLookup`

E1 sets Order status=PAID; E2 immediately sets REFUNDED. Is E1's fullDocument guaranteed to say PAID?

**Answer:** No. Update lookup can observe the current majority-committed version already updated by E2. Use updateDescription/business versions or pre/post images under proper contracts when exact history is needed.

### Exercise 18: Transactions outside MongoDB

A handler sends an email before MongoDB commits. The transaction then aborts. Is the email rolled back?

**Answer:** No. Use an outbox and downstream idempotency.

### Exercise 19: `flatMap`

E1(version 5) runs slowly, E2(version 6) runs fast, both under flatMap concurrency=32. What is the risk?

**Answer:** E2 may commit before E1; then E1 overwrites newer state. Use concatMap or per-key partitioned ordering with checkpoint barriers.

### Exercise 20: Reactive retry

A worker builds options from a token at startup and calls retryWhen on that same Flux. Why can it replay far too much?

**Answer:** Retries may reopen from the stale startup token. Use **Flux.defer + load durable checkpoint** on every resubscription.

### Exercise 21: Reactive transaction

A change stream Flux runs continuously for days. Should the entire Flux be wrapped inside one MongoDB transaction?

**Answer:** No. Keep transactions short per event or small batch; never hold sessions/snapshots open across an infinite stream.

### Exercise 22: Poison event

An incompatible schema makes a handler throw IllegalArgumentException on every try. Should we use onErrorResume and checkpoint past it?

**Answer:** Not automatically. Define a pause/quarantine/recovery policy. If writing to a DLQ and skipping, verify DLQ persistence succeeded and a replay workflow exists.

### Exercise 23: High watermark

A consumer sees no new change events for hours. Should we assume the stream died?

**Answer:** No. Streams can simply be idle. Monitor cursor health, worker heartbeats, and postBatchResumeToken/high-water marks where supported by APIs.

### Exercise 24: Retention margin

Oplog window H=8 hours, consumer lag L=5 hours, estimated repair + catch-up R=4 hours. Margin M?

**Answer:** M=8-(5+4)=-1 hour. Risk of failing to resume in time; expand history window/throughput and intervene immediately instead of just restarting.

### Exercise 25: Multiple owners

Worker A checkpoints T200, slow worker B checkpoints T150. Can JSON tokens be compared as strings to tell which is newer?

**Answer:** No. Tokens are opaque; enforce leases/fencing, exclusive ownership, and controlled commit order.

### Exercise 26: Integration tests

Unit tests encoding/decoding a fake token pass. Does that prove resumeAfter works on real MongoDB?

**Answer:** Not yet. Run replica set integration tests: open a stream, write real changes, extract real tokens, close, reopen with resumeAfter, and verify the next event arrives.

### Exercise 27: Outbox

A notification sends successfully yet the worker times out. Does an outbox strictly stop resending?

**Answer:** Not if downstream lacks an idempotency contract. An outbox guarantees durable commands, while external exactly-once effects require downstream dedupe or accepting trade-offs.

### Exercise 28: Rebuilding

A read model takes 30 minutes to rebuild from a snapshot, then opens a watch from now. What is wrong?

**Answer:** Updates during those 30 minutes can be missed. Recovery needs a stream position/snapshot cut plus replay buffer or proper synchronization strategy.

## 34. Pre-Production Checklist

- **Topology:** Is the MongoDB deployment a change-stream-capable replica set or sharded cluster?
- **Privileges:** Does the watcher account have adequate permissions for the exact watch scope?
- **Namespace:** Are collection/database/deployment scopes chosen and documented clearly?
- **Pipeline version:** Are options, filters, and pipeline versions persisted with checkpoints?
- **Control events:** Does the handler handle invalidate/DDL deliberately rather than dropping them?
- **Resume tokens:** Are raw BSON tokens stored intact rather than only documentKey or clusterTime?
- **Serialization:** Does JSON/BSON serialization round-trip all types intact?
- **Checkpoint semantics:** Does the token mark **last durably processed**, not last received?
- **Ordering:** Is sequential processing guaranteed, or version guards + contiguous checkpoint barriers?
- **Single owner:** Are leases/fencing enforced if multiple instances share one checkpoint?
- **Crash windows:** Have faults been injected before/after effects and checkpoints to verify zero lost data?
- **Inbox:** Is event identity unique per stream + token?
- **Business keys:** Do paymentId/operationId have unique indexes and clear policies?
- **Atomic effects:** Do markers, projections, outbox, and checkpoints share MongoDB transactions where needed?
- **Outbox:** Are side effects outside MongoDB kept out of pre-commit paths?
- **Downstream dedupe:** Are idempotency keys used or duplicate risks documented?
- **Marker retention:** Is dedupe state retained longer than the replay/rebuild horizon?
- **Reprocessing:** Does applying the same event repeatedly preserve correct read models/revenue?
- **Versions:** Do stale events avoid overwriting newer state under concurrency shifts?
- **Invalidate:** Are INVALIDATED state and invalidate tokens tracked separately?
- **startAfter:** Is it used only after deliberate recovery decisions when history still fits?
- **resumeAfter:** Is it prevented from attempting to cross invalidate?
- **History loss:** Is there a RECOVERY_REQUIRED state and rebuild runbook instead of silent skips?
- **Initial sync:** Do snapshot + change stream handoffs avoid gaps?
- **Oplog:** Is actual history window measured with downtime/catch-up margins?
- **Pre/post-images:** Are image retention and oplog retention kept conceptually separate?
- **FullDocument:** Is updateLookup never mistaken for an exact event-time snapshot?
- **Retries:** Are resumable/non-resumable errors classified with bounded backoff/jitter?
- **Poison events:** Is there lossless quarantine/DLQ or halting?
- **Reactive:** Does the app use concatMap without blocking or unmanaged lifecycle subscriptions?
- **Reactive retries:** Are checkpoints reloaded on every resubscription/retry?
- **Reactive transactions:** Are ReactiveMongoTransactionManager and one Reactor chain used consistently?
- **Sync listeners:** Do MessageListenerContainers have proper error handlers and shutdowns?
- **Monitoring:** Are lag, oplog window, checkpoint age, duplicates, invalidations, and history loss tracked?
- **Security:** Are fullDocument/PII excluded from logs and checkpoints/outboxes protected?
- **Testing:** Are MongoDB replica set integration tests and Testcontainers in place?
- **Operations:** Are shutdown, failover, invalidate, and history-loss drills rehearsed?

## 35. Summary

1. **Change streams do not automatically guarantee exactly-once business effects**. Applications must tolerate replay/duplicate deliveries in their processing logic.
2. **Event._id is the resume token**, distinct from documentKey._id; never replace tokens with document IDs or clusterTime.
3. **Checkpointing after durable effects** prevents skipping unhandled events; post-crash replays must be absorbed by idempotent handlers.
4. **Inbox markers with unique keys** per streamId + event token block event replays, yet do not replace business idempotency on paymentId/operationId.
5. **MongoDB transactions** can atomically commit inbox + read model + outbox + checkpoint within the same deployment/session; they exclude side effects outside MongoDB.
6. **Outboxes** decouple email/broker delivery from transactions; downstream idempotency is still needed against timeout/retry duplicates.
7. **`$inc`, appends, and external calls are not idempotent** if reprocessed without unique guards.
8. **Once does not mean in-order**; use concatMap, partitioned ordering, or version guards with contiguous checkpoints.
9. **Invalidate** appears on certain DDL operations depending on watch scope and closes the cursor. It differs from transient network errors.
10. **resumeAfter cannot be used after invalidate**; **startAfter** can open a new stream after invalidate while history remains and recovery policy permits.
11. **startAfter does not restore dropped data**, fix pipeline drift automatically, or bypass oplog retention.
12. **Long-lived checkpoints do not mean long-lived oplogs**. Once history is lost, rebuild/reconcile or explicitly record an accepted data gap.
13. **Pre/post-image retention differs from oplog retention**; once the oplog entry is evicted, its images vanish too.
14. **fullDocument updateLookup** can return current state newer than the update event; choose data sources matching required semantics.
15. **Spring Data ReactiveMongoTemplate** offers Flux<ChangeStreamEvent<T>> and ChangeStreamOptions resumeAfter/startAfter; durable checkpoints must be reloaded on retries.
16. **Reactive transaction contexts** differ from imperative thread-bound transactions, so never mix blocking MongoTemplate inside reactive chains expecting atomicity.
17. **MessageListenerContainer** fits sync apps yet still demands clear lifecycle, error handlers, ownership, and processing semantics.
18. **Observability must track consumer lag and oplog safety margins**, not just process health status.
19. **Integration tests must run on replica sets** with real tokens and fault injection to verify resume, invalidate, duplicate handling, and recovery.
20. **Recovery must avoid opening new gaps between snapshots and streams**; that is a data-design responsibility no single resume option solves alone.

On the topic of **Duplicate Events, Invalidate, Retention, and Idempotent Processing**, **SPRING_DATA_MONGODB** services are reliable only when combining proper MongoDB change stream semantics, durable checkpoints, event- and business-level idempotency, scoped transactions, and a recovery runbook for when history runs out.

### Official References

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — scope, resume tokens, resumeAfter, startAfter, highwatermark, oplog history.
- [MongoDB Manual — Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/) — event._id, documentKey, operationType, and event metadata.
- [MongoDB Manual — Invalidate Event](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/) — when streams invalidate and cursor effects.
- [MongoDB Manual — db.collection.watch](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/) — resume options, fullDocument lookup, and cursor lifecycle.
- [MongoDB Manual — Change Streams Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — operations, stream sizing, and history considerations.
- [MongoDB Manual — changeStreamOptions](https://www.mongodb.com/docs/manual/reference/cluster-parameters/changestreamoptions/) — pre/post-image retention.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog history and retention.
- [Spring Data MongoDB — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html) — ReactiveMongoTemplate, MessageListenerContainer, resume support.
- [Spring Data MongoDB — ChangeStreamOptions Builder API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamOptions.ChangeStreamOptionsBuilder.html) — resumeAfter/startAfter and fullDocument.
- [Spring Data MongoDB — ChangeStreamEvent API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ChangeStreamEvent.html) — getResumeToken, getBody, getRaw, getOperationType.
- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager, ReactiveMongoTransactionManager, and context.
- [MongoDB Java Sync Driver — Open Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — ChangeStreamIterable, MongoChangeStreamCursor, and resuming.
