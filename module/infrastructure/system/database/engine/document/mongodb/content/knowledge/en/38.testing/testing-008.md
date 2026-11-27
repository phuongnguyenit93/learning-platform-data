# Testing Disconnects, Primary Stepdowns, and Change Stream Resumption in MongoDB

## 1. Context: Does an Interrupted Change Stream Drop Events?

Suppose an order-sync service uses MongoDB Change Streams to keep a search index updated:

~~~text
Orders API -> MongoDB orders
                     |
                     | Change Stream
                     v
              Search Indexer
                     |
                     v
                 Search Index
~~~

At 10:00:00, the indexer processes event `E100` and saves its resume token. At 10:00:02, the MongoDB primary drops offline; a secondary is elected as the new primary. Meanwhile, the API continues writing `E101`, `E102`, and `E103` once the election finishes.

The questions to test go far beyond **“does the app automatically reconnect?”**:

1. Does the consumer detect the closed cursor or `getMore` error?
2. After the primary change, does it open the stream on the new topology?
3. Does it resume from **the exact last acknowledged position**, or skip events?
4. If `E101` was processed yet its token was not saved before the process crashed, does the system handle replaying `E101` idempotently after restart?
5. If an outage exceeds oplog history, does it clearly report **unable to resume** and recover via snapshot/reconciliation?
6. Does the sink preserve accurate state across transient errors?

This lesson belongs to the **MongoDB Document Database Engine** module, **Testing** chapter, titled **Testing Disconnects, Primary Stepdowns, and Change Stream Resumption in MongoDB**.

**Key message:** Reconnecting does not automatically mean the output data is correct. Tests must verify **stream continuity, checkpointing, idempotency, and post-incident recovery**.

## 2. Learning Objectives

After this lesson, you will be able to:

- Understand Change Streams and their dependence on the replica set oplog.
- Distinguish temporary cursors, sessions/drivers, event resume tokens, and durable checkpoints.
- Know when to use `resumeAfter`, `startAfter`, or `startAtOperationTime`.
- Understand resumable errors vs unrecoverable oplog history loss.
- Distinguish primary switches from consumer crashes, network partitions, and DNS/TLS failures.
- Build a replica set test environment supporting real primary failover.
- Use `mongosh` to generate events, save tokens, close streams, resume, and verify outputs.
- Build a checkpointed consumer using the MongoDB Java Sync Driver.
- Handle Spring Data MongoDB synchronous and reactive change stream nuances.
- Design checkpoints without event-loss gaps.
- Prove idempotent processing when events are replayed.
- Verify exact post-failover state with automated assertions.
- Monitor lag, resume attempts, errors, duplicate rates, and oplog headroom.
- Build a runbook and production checklist for change stream consumers.

## 3. Change Streams Architecture

MongoDB Change Streams observe changes at three scopes:

- **Collection:** `db.orders.watch()` or `collection.watch()`.
- **Database:** `db.watch()`.
- **Deployment:** `MongoClient.watch()` or `Mongo.watch()`, depending on driver and privileges.

They run on **replica sets or sharded clusters**, backed by the oplog—never on pure standalone MongoDB.

~~~text
Application writes
       |
       v
Replica set PRIMARY
       |
       +----> Replicated oplog
       |             |
       v             v
 SECONDARIES    $changeStream aggregation
                      |
                      v
               Change Stream Cursor
                      |
                      v
                 Java Consumer
                      |
                 process event
                      |
                 persist token
~~~

### 3.1. A Change Stream Is Not an Infinite Queue

MongoDB Change Streams read change notifications from oplog history; they are not an unconditional drop-in replacement for message queues with independent retention.

A consumer paused too long loses the ability to resume once the oplog overwrites the resume position.

### 3.2. Events Are Published Once Majority-Committed

Change Streams emit majority-committed changes. A `w:1` write rolled back before majority commit may never appear as a committed change event.

Never use Change Streams to prove every command a client sent was durably persisted.

### 3.3. Consumers Hold Long-Lived Connections

A change stream cursor typically keeps a `getMore` waiting for events. When no changes occur, the call waits and returns an empty batch. **An empty batch is not a connection error.**

### 3.4. Reading on Secondaries

The MongoDB driver can open a change stream with an appropriate read preference. However, an election may cause the cursor-hosting node to stop matching that read preference; rely on driver topology discovery and resumable semantics rather than assuming an open cursor lives forever.

## 4. Prerequisites for Meaningful Tests

| Item | Requirement |
|---|---|
| Topology | Replica set or sharded cluster, never standalone |
| Write workload | Operations emitting events with easily matched IDs |
| Consumer | Event-processing and checkpointing logic |
| Checkpoint store | Survives consumer process restarts |
| Failure control | Permission to simulate network/primary faults in the lab |
| Recovery checks | Assertions on zero missing events, deduplication, and final state |
| Observability | UTC logs/metrics for timestamps, elections, and resume attempts |
| Isolation | Never run destructive fault injection on production |

### 4.1. Why Is a Single-Node MongoDBContainer Insufficient?

Testcontainers can run a **single-node replica set**, sufficient for basic change stream and resume token tests. However, it **cannot** simulate electing a new primary from another data-bearing node when only one member exists.

To test real failover, you need at least one eligible secondary—typically **three voting data-bearing members** to retain majority when one node drops.

### 4.2. Never Confuse a Docker Restart with an Election

Restarting the consumer container tests consumer lifecycle, not MongoDB elections. Restarting a `mongod` container in an unhealthy replica set can break quorum, and its behavior differs from a planned stepdown.

### 4.3. Atlas vs Self-Managed

On Atlas, never attempt self-managed OS or network manipulation on managed nodes. Use authorized staging/test environments, supported maintenance/test workflows, or coordinate with Support. The lab here uses an isolated self-managed replica set.

## 5. Change Event Structure

Illustrative event:

~~~javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "update",
  clusterTime: Timestamp({ t: 1794650400, i: 1 }),
  ns: { db: "change_stream_lab", coll: "orders" },
  documentKey: { _id: "order-101" },
  updateDescription: {
    updatedFields: { status: "CONFIRMED" },
    removedFields: []
  }
}
~~~

The token payload above is a placeholder. Never fabricate `_data` values as resume tokens.

| Field | Role |
|---|---|
| `_id` | Event resume token, a BSON document |
| `operationType` | `insert`, `update`, `replace`, `delete`, `invalidate`, etc. |
| `clusterTime` | Logical cluster/event timestamp |
| `ns` | Database/collection namespace |
| `documentKey` | Document identifier, potentially including shard key |
| `fullDocument` | Full document per configuration/event type |
| `updateDescription` | Update field delta |
| `lsid`/`txnNumber` | Transaction metadata when applicable |

### 5.1. Change Event `_id` Is Not the Business Document `_id`

- `event._id`: token used to resume the stream.
- `event.documentKey._id`: business document key.
- `event.fullDocument._id`: key inside the full document when returned.

Never use `documentKey._id` as a resume token. One document can emit many events over time.

### 5.2. Tokens Are Opaque BSON

Never treat resume tokens as simple sequence numbers, timestamp strings, or custom UUIDs. Store the **raw BSON document** returned by the driver/server alongside stream scope and pipeline config.

### 5.3. `clusterTime` Is Not a Unique Event ID

Multiple change events can share the same `clusterTime`, especially with transactions and sharding; certain scenarios from MongoDB 8.0 onward behave similarly on other deployments as well. Deduplicating purely by timestamp can drop events.

## 6. Resume Tokens: The Anchor of Recovery

Token sources:

1. `event._id` for each received event.
2. `postBatchResumeToken` from `aggregate`/`getMore`, when the server emits a high-watermark token.
3. Driver cursors track resume tokens internally for automatic resumption.

### 6.1. Event Tokens vs High-Watermark Tokens

An **event token** identifies a specific event.

A **high-watermark token** tracks cursor progress even across empty batches. That helps watermark/lag tracking, provided checkpointing guarantees all events prior to the watermark were processed.

### 6.2. Checkpoints Must Reflect Completed Processing

If the consumer receives `E100`, saves `E100`'s token *before* updating the search index, and crashes, resuming skips `E100`.

~~~text
Wrong:
  receive E100
     |
  save token E100
     |
  process E100 -> crash
     |
  restart resumeAfter(E100) -> E100 is skipped
~~~

### 6.3. Saving Tokens After Side Effects Can Still Produce Duplicates

~~~text
receive E100
   |
process E100 -> success
   |
crash BEFORE save token
   |
restart from token E99
   |
E100 may be processed again
~~~

Therefore consumers need **idempotency** or atomic persistence of output + checkpoint whenever possible.

### 6.4. Never Equate Auto-Resume with Durable Checkpoints

The driver can auto-resume after **resumable errors** while the process stays alive. Once the process is killed or redeployed, in-memory checkpoints vanish. Applications must load durable tokens from persistent storage on startup.

## 7. `resumeAfter`, `startAfter`, `startAtOperationTime`

| Option | Input | When to use |
|---|---|---|
| `resumeAfter` | Resume token | Continue after a processed event/watermark |
| `startAfter` | Resume token | Open a fresh stream after a token, including `invalidate` |
| `startAtOperationTime` | BSON timestamp | Start at a point in time when no suitable token exists |

These three options are **mutually exclusive** on a single watch call. MongoDB forbids setting multiple together.

### 7.1. `resumeAfter` Is the Common Choice

Once `E100` finishes processing and its token is durably saved, restart using `resumeAfter(tokenE100)` to continue cleanly.

### 7.2. `startAfter` for Invalidation

After an `invalidate` caused by dropping/renaming a collection or dropping a database, `resumeAfter` cannot use the invalidate token. `startAfter` opens a new change stream after that token under supported conditions.

**However**, “`startAfter` succeeded” does not guarantee the dropped/renamed namespace exists again or that data was restored. Business recovery must handle namespace lifecycle explicitly.

### 7.3. `startAtOperationTime` Is No Perfect Substitute for Tokens

`BsonTimestamp` encodes seconds plus an increment, offering finer ordering than `Instant` in several cases. The chosen time must still exist in the oplog, and an imprecise timestamp can replay duplicates or skip events.

Never pass the restarted app's current wall-clock time to “resume” if events occurred while the consumer was down.

### 7.4. Keep Pipeline and Options Identical

MongoDB recommends resuming with the **exact same pipeline and options** used when the token was created. Changing filters, `fullDocument`, or options during recovery can trigger unexpected behavior or fail resumption.

Version your stream definition alongside checkpoints.

## 8. Invalidation Differs from Connection Errors

A change stream cursor can terminate due to:

- Network drop or server election.
- Client stop, cancel, or close.
- Collection rename or drop.
- Database drop.
- Stream invalidation.
- Auth, access, or TLS errors.
- Oplog history loss.
- Special topology events such as shard removal.

### 8.1. Never Treat Every Closed Cursor as Resumable

A network timeout is typically resumable. An `invalidate` is a semantic event indicating the stream source changed. History loss signals **insufficient oplog history**. Each needs a distinct handler.

### 8.2. Rules by Scope

| Scope | Example invalidation |
|---|---|
| Collection-level watch | Rename/drop watched collection, drop database |
| Database-level watch | Drop watched database |
| Deployment-level watch | Do not extrapolate from collection-level; check docs/event semantics |

### 8.3. Collection Renames

If `orders` is renamed to `orders_archive`, an old collection-level watcher receives `invalidate` and closes. Monitoring the new collection requires changing watch scope/namespace and executing a business-appropriate re-bootstrap plan.

### 8.4. Sharded Clusters Have Extra Edge Cases

MongoDB docs warn that shard removal can close a change stream cursor and is not always seamlessly resumable. Sharded lifecycle tests differ from replica set failover tests.

## 9. Oplog Retention: A Prerequisite for Resumption

Change stream resumption relies on the oplog still retaining history back to the token. You cannot guarantee resumption from an old token merely because it is stored in your checkpoint table.

~~~text
Oplog:
 [E100 E101 E102 ... E400 E401] -> time
   ^                ^
   |                |
 token E100      oldest available
   |
   +--> old token fell out of oplog => history lost
~~~

### 9.1. Oplog Windows Shrink Under High Write Volume

With fixed oplog capacity, a spike in write throughput compresses the actual retention window.

Example:

~~~text
Before batch:
  Oplog window ~36 hours

After batch:
  Oplog window ~4 hours

Consumer outage:
  6 hours

=> Resumption risks failing.
~~~

### 9.2. Inspecting the Oplog Window in `mongosh`

On an appropriate replica set member:

~~~javascript
rs.printReplicationInfo();
~~~

Some scripts use:

~~~javascript
db.getReplicationInfo();
~~~

Never treat a point-in-time oplog window measurement as a guarantee that events survive until tomorrow; it fluctuates with write rates and configuration.

### 9.3. PIT Backups Do Not Replace Change Stream History

Point-in-time backups restore database state, yet do not make an expired token resumable. When history is lost, run a **projection/snapshot re-bootstrap + new start point + reconciliation**, designed with zero gap between snapshot and stream.

### 9.4. Recovering from History Loss

Never catch the exception, open a fresh `watch()` with no token, and pretend recovery succeeded. A fresh stream observes only future events, leaving downtime changes unapplied.

Transition the consumer to `RECONCILIATION_REQUIRED`, alert operators, stop reporting “caught up,” and rebuild or reconcile the projection cleanly.

## 10. Test Oracle: What Criteria Decide PASS?

Never assert solely “no exceptions thrown.” Establish a source of truth:

~~~text
Writer emits: E001 E002 E003 ... E100
               |                    |
               v                    v
          Durable order log    Consumer output
               |                    |
               +--------- compare --+
                         |
              Zero missing business events
              Zero duplicate side effects
              Projection state accurate
~~~

A **test oracle** can be a separate log collection recording each `eventId` of acknowledged writes under an appropriate write concern, or a known identifier set persisted and verified post-test.

### 10.1. Compare Event IDs, Not Just Counts

Consumer output containing 100 records does not prove 100 distinct events were processed; it could hold 99 valid + 1 duplicate + 1 missing.

Verify:

- Expected event ID set.
- Actually processed IDs.
- Duplicates.
- Missing IDs.
- Final projection/index state.
- Recovery latency.
- Checkpoint position and healthy consumer state.

### 10.2. Event Ordering and Sharding

Do not assume events across multiple shards carry a simple global application sequence number. When per-aggregate ordering is needed, embed domain versions/sequences and assert those invariants.

### 10.3. Do Not Rely Purely on Wall-Clock Time

Clock skew across containers or VMs invalidates strict cross-host timestamp comparisons. Favor business IDs, DB events, and monotonic counters to prove continuity. `clusterTime` is a logical timestamp, not a substitute for unique IDs.

## 11. Essential Fault-Injection Matrix

| Scenario | Injected failure | Expected behavior |
|---|---|---|
| Consumer process restart | Stop/redeploy worker | Resumes from checkpoint with zero gaps |
| Crash after processing before checkpoint | Kill between the two steps | Event may replay; output stays idempotent |
| Short network drop | Block TCP briefly | Bounded reconnect with zero data loss |
| DNS/SRV unavailable | Controlled DNS block | Keeps checkpoint; recovers when DNS returns |
| Primary stepdown | `rs.stepDown` in lab | Driver discovers new primary and resumes |
| Primary hard stop | Stop lab primary `mongod` | Election completes; stream eventually continues |
| Secondary outage | Stop one secondary | Primary stays up; consumer does not fail needlessly |
| Loss of majority | Isolate enough voting members | Writes stall; incident reported clearly |
| Lag exceeds oplog window | Wait or push writes in lab | History lost; triggers rebootstrap requirement |
| Collection drop/rename | Controlled DDL | Invalidation; `startAfter`/recreate per policy |
| Permission revoked | Alter lab role | Clear auth error without infinite retry |
| Broken TLS/CA rotation | Swap trust path in lab | New connections fail; recovers once fixed |
| Multiple consumers | Two workers share checkpoint | Fencing/lease or idempotency protects state |
| High event throughput | Large write batches | Lag and resources remain within bounds |
| Slow downstream | Throttle projector | Backpressure works; checkpoint never skips ahead |
| Shard event | Lab shard migration/removal | No unconditional resume assumed |

### 11.1. Separate Error Categories

- **Transient:** network drops, elections, server selection.
- **Semantic:** invalidation, schema changes, collection renames.
- **Permanent/configuration:** bad credentials, missing privileges, broken TLS trust.
- **Data history gap:** token expired from oplog.

A single blanket retry loop across all four causes false “healthy” reports or log storms.

## 12. Preparing the Lab Environment

Practice topology:

~~~text
                    MongoDB replica set rsLab
                 +------------------------------+
                 |                              |
                 |  m1 PRIMARY                  |
                 |  m2 SECONDARY                |
                 |  m3 SECONDARY                |
                 +------------------------------+
                     |                   |
                    Writer             Consumer
                                         |
                                    Checkpoint store
                                         |
                                   Projection output
~~~

### 12.1. Network Requirements

- All nodes use hostnames resolvable by **both nodes and clients**.
- Internal ports are open properly and never exposed outside the lab scope.
- Replica set member addresses match advertised hosts in `rs.conf()`.
- Java Driver URI includes sufficient seed hosts, `replicaSet=rsLab`, plus TLS/auth if configured in the lab.

### 12.2. Isolated Test Data

Use a dedicated `change_stream_lab` database with collections:

~~~text
orders
consumer_checkpoints
order_projection
test_writer_log
~~~

Never inject faults against production or accounts holding real customer data.

### 12.3. Least-Privilege Roles

The change stream consumer needs `read`/`changeStream` privileges for its scope (collection/database/deployment) plus write privileges on checkpoints/projections if using the same principal. Never run production workers as root. If source and projection live in separate DBs, scope permissions on both.

### 12.4. Verify Healthy Replica Set Before Faults

Before triggering primary elections:

~~~javascript
rs.status();
rs.conf();
db.hello();
rs.printSecondaryReplicationInfo();
rs.printReplicationInfo();
~~~

Never trigger a stepdown if members/quorum are missing or secondaries have not caught up.

## 13. Initializing Lab Data

**Run the commands below strictly in the test database.**

~~~javascript
use change_stream_lab

db.createCollection("orders");
db.createCollection("consumer_checkpoints");
db.createCollection("order_projection");
db.createCollection("test_writer_log");

db.orders.createIndex(
  { testRunId: 1, seq: 1 },
  { unique: true, name: "unique_test_seq" }
);

db.order_projection.createIndex(
  { eventId: 1 },
  { unique: true, name: "unique_event" }
);
~~~

### 13.1. Why Create Indexes Before the Test?

Creating collections/indexes mid-stream introduces DDL events, metadata overhead, and noise into test outputs. Pre-creating them keeps the ground truth clean.

### 13.2. Choose a Fixed `testRunId` per Run

Example:

~~~javascript
const runId = "failover-lab-2026-11-14-A";
~~~

Never reuse the same ID across runs without cleanup/reinitialization, or unique constraints will fail with duplicate keys.

### 13.3. Keep Test Data Free of PII

~~~javascript
db.orders.insertOne({
  _id: "order-001",
  testRunId: "failover-lab-2026-11-14-A",
  seq: 1,
  status: "CREATED",
  updatedAt: new Date()
});
~~~

Keep payloads small, deterministic, and tagged with business IDs for assertions.

## 14. Lab Step A: Opening a Change Stream in `mongosh`

Open **Shell A** connected to the replica set:

~~~javascript
use change_stream_lab

const cursor = db.orders.watch(
  [],
  { fullDocument: "updateLookup", maxAwaitTimeMS: 1000 }
);

print("Waiting for events...");
~~~

Open **Shell B** (also connected to `rsLab`) and write:

~~~javascript
use change_stream_lab

db.orders.insertOne({
  _id: "order-002",
  testRunId: "failover-lab-2026-11-14-A",
  seq: 2,
  status: "CREATED",
  updatedAt: new Date()
});
~~~

Back in Shell A:

~~~javascript
const firstEvent = cursor.next();

printjson({
  op: firstEvent.operationType,
  documentKey: firstEvent.documentKey,
  token: firstEvent._id
});
~~~

`cursor.next()` blocks until an event arrives; never run it on an HTTP request thread.

### 14.1. Why Open the Watcher Before Writing?

If you open the stream **after** the insert without a historical starting point, the event already occurred beforehand and will not appear. For deterministic tests, open the watcher/checkpoint before the writer starts, or use an explicit start point.

### 14.2. Full Document and `updateLookup`

`fullDocument: "updateLookup"` fetches the current document on updates. That returns the **latest majority-committed version at lookup time**, which may differ from the document right after that specific operation if newer updates arrived. Never use `fullDocument` instead of event deltas when per-update snapshots are required.

## 15. Lab Step B: Saving a Token and Resuming Manually

In Shell A, after successfully processing `firstEvent`:

~~~javascript
const token = firstEvent._id;

db.consumer_checkpoints.updateOne(
  { _id: "consumer-lab" },
  {
    $set: {
      token: token,
      savedAt: new Date()
    }
  },
  { upsert: true }
);

cursor.close();
~~~

Next, Shell B emits another event:

~~~javascript
db.orders.updateOne(
  { _id: "order-002" },
  { $set: { status: "CONFIRMED", updatedAt: new Date() } }
);
~~~

Reopen the cursor in Shell A:

~~~javascript
const saved = db.consumer_checkpoints.findOne({
  _id: "consumer-lab"
});

const resumed = db.orders.watch(
  [],
  { resumeAfter: saved.token, fullDocument: "updateLookup" }
);

const eventAfterRestart = resumed.next();

printjson({
  operationType: eventAfterRestart.operationType,
  documentKey: eventAfterRestart.documentKey,
  token: eventAfterRestart._id
});
~~~

### 15.1. Basic Assertions

- The event received after restart occurred after the checkpointed token.
- The checkpointed event is not re-read when no crash occurred between processing and saving.
- The token is stored as a BSON document, not turned into an ad-hoc string.
- Pipeline, namespace, and options stay identical across resume.

### 15.2. Data Logging Caveat

Printing tokens with `printjson` is fine in a lab. In production, protect the checkpoint store and never log full payloads or events containing PII or secrets.

## 16. Lab Step C: Consumer Crash Between Processing and Checkpointing

Create the scenario:

~~~text
Checkpoint = token E002

Receive E003
Process E003 successfully
*** KILL consumer BEFORE save token E003 ***

Restart consumer
resumeAfter(token E002)
Read E003 again
~~~

### 16.1. Expected Outcome

Expect **re-reading E003**, yet the projection, search index, or downstream side effects must not duplicate.

A simple pattern processes via an idempotent business event key:

~~~javascript
db.order_projection.updateOne(
  { eventId: "E003" },
  {
    $set: {
      orderId: "order-003",
      status: "CONFIRMED",
      lastAppliedAt: new Date()
    }
  },
  { upsert: true }
);
~~~

Use a stable, domain-unique `eventId` to avoid creating two projection entries. If sequential ordering across updates matters, add version/ordering controls—a bare `$set` is not enough for every workflow.

### 16.2. Why Not Checkpoint First?

Checkpointing before side effects succeed produces **at-most-once delivery** with silent event loss. Critical data syncs normally require at-least-once + idempotency or atomic checkpoints.

## 17. Lab Step D: Planned Primary Stepdown

**Solely on a self-managed lab replica set**, with admin privileges and healthy secondaries.

Connect **directly** to the current primary in `mongosh` for admin commands and verify:

~~~javascript
db.hello().isWritablePrimary;
rs.status();
~~~

Trigger a controlled stepdown:

~~~javascript
rs.stepDown(60, 15);
~~~

Meaning:

- The old primary volunteers to step down for 60 seconds.
- Gives up to 15 seconds for an electable secondary to catch up per parameters.
- The admin shell itself may drop its connection or return an error as the node changes role.

Never force `force: true` to break majority. If no eligible secondary exists, MongoDB rejects the stepdown.

### 17.1. Parallel Observation

During stepdown:

1. Writer emits events with sequential IDs using bounded retries.
2. Consumer continues reading the change stream.
3. Capture driver logs for server selection and resumable errors.
4. Record the timestamp of primary transition.
5. Track which event IDs the writer **confirmed succeeded**.
6. Compare projection and checkpoint once the cluster stabilizes.

### 17.2. Brief Errors Are Expected

During an election there is briefly no primary, so writes can fail, time out, or retry. Tests should not demand “zero network errors,” but rather **recovery within SLO and zero lost committed events**.

### 17.3. Read Preference and Role Changes

From MongoDB 9.0 onward, on cursors opened with `primary` or `secondary` read preferences, an election can leave the hosting node no longer matching that preference; `getMore` returns resumable `InterruptedDueToReplStateChange` (code 11602). Compatible drivers auto-resume; custom `getMore` callers must handle it.

Do not assume this exact behavior applies to older MongoDB releases.

### 17.4. What Must Be Proven

Not merely “a new primary was elected”; the consumer must resume delivering post-election events and advance its checkpoint through all expected IDs.

## 18. Lab Step E: Hard-Stopping the Primary

This differs from `rs.stepDown`:

~~~text
Primary m1
   |
   +--> OS process killed/stopped
   |
Secondaries m2 + m3 elect a new primary
   |
   +--> Driver rediscovers topology
   |
   +--> Change stream resumes from checkpoint/driver token
~~~

### 18.1. Affect Only One Node in the Lab

Never kill multiple members; majority is needed for failover. Confirm the current primary's identity right before stopping it, as leadership may have shifted since setup.

### 18.2. Differences from Planned Stepdown

- In-flight writes and transactions can abort mid-flight.
- Driver sockets to the dead node drop immediately.
- Election timing varies.
- Writes not yet majority-committed may roll back and **will not** appear as committed change stream events.

### 18.3. Oracle Must Include Only Committed Writes

When checking for missing events, include only writes with confirmed outcomes under your write concern and reconciliation strategy—never include timed-out/unknown writes blindly.

## 19. Lab Step F: Network Partitions and Consumer Disconnects

At least three distinct failure modes exist:

1. **Consumer ↔ MongoDB blocked**, while members still talk to each other.
2. **Primary ↔ secondaries blocked**, potentially triggering elections or quorum loss.
3. **One member ↔ several clients blocked**, altering topology discovery and cursor routing.

### 19.1. Test Model

~~~text
Time A: Consumer reading E020
Time B: Block network consumer -> MongoDB
Time C: Another writer persists E021..E030 on healthy cluster
Time D: Restore network
Time E: Consumer resumes
Time F: Compare expected IDs E021..E030
~~~

### 19.2. Nature of Timeouts

Distinguish:

- TCP connect timeout.
- Socket/read timeout.
- Server selection timeout.
- Cursor `maxAwaitTime` elapsing with zero events.
- Application deadline/batch processing timeout.

`tryNext()` returning `null` on an empty batch must never be classified as a network failure.

### 19.3. Do Not Demand Instant Network Recovery

Verify bounded retries and backoff without causing connection storms while the DB is unreachable. The consumer must preserve its prior checkpoint safely while waiting.

### 19.4. Reconnection Must Preserve Identity and TLS

On MongoDB Atlas, SRV URIs, private endpoints, TLS, and SCRAM introduce distinct failure surfaces. Never disable TLS verification or widen IP allowlists just to “make tests pass.”

## 20. Java Sync Driver Consumer: Reading a Change Stream

Minimal example using the MongoDB Java Sync Driver managed by Spring Boot BOM or a compatible driver release.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.ChangeStreamIterable;
import org.bson.Document;

import java.util.concurrent.TimeUnit;

public class SimpleChangeStreamWatcher {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders =
                client.getDatabase("change_stream_lab")
                      .getCollection("orders");

            ChangeStreamIterable<Document> stream =
                orders.watch().maxAwaitTime(1, TimeUnit.SECONDS);

            try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
                     stream.cursor()) {
                while (!Thread.currentThread().isInterrupted()) {
                    ChangeStreamDocument<Document> event = cursor.tryNext();

                    if (event == null) {
                        // No event right now; NOT an error.
                        continue;
                    }

                    System.out.println("type=" + event.getOperationType());
                    System.out.println("token=" + event.getResumeToken());
                }
            }
        }
    }
}
~~~

### 20.1. Key Takeaways

- `watch()` opens a change stream on the collection.
- `cursor.tryNext()` returns an event or `null` if none is available yet.
- `cursor.next()` blocks waiting for an event.
- `maxAwaitTime` configures how long the server waits on one `getMore`; it is not an overall transaction deadline.
- `try-with-resources` closes cursors and clients cleanly.

### 20.2. Never Run Blocking Cursors on Request Threads

In Spring MVC, synchronous consumers typically run on dedicated workers or managed executors. In WebFlux, use reactive change streams to avoid blocking event-loop threads.

### 20.3. Output and Data Sensitivity

Never log full `event.getFullDocument()` or tokens if payloads contain sensitive fields; printing tokens here is for lab learning, not production logging design.

## 21. Java: Persisting Durable BSON Checkpoints

A minimal checkpoint can live in `consumer_checkpoints`.

Raw driver repository example using `MongoCollection<BsonDocument>`:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.Filters;
import org.bson.BsonDocument;
import org.bson.BsonString;

public final class TokenCheckpointStore {
    private final MongoCollection<BsonDocument> checkpoints;
    private final String consumerId;

    public TokenCheckpointStore(MongoCollection<BsonDocument> checkpoints,
                                String consumerId) {
        this.checkpoints = checkpoints;
        this.consumerId = consumerId;
    }

    public BsonDocument load() {
        BsonDocument state = checkpoints
            .find(Filters.eq("_id", consumerId))
            .first();

        return state == null ? null : state.getDocument("token");
    }

    public void save(BsonDocument token) {
        if (token == null) {
            throw new IllegalArgumentException("missing resume token");
        }

        BsonDocument state = new BsonDocument("_id",
            new BsonString(consumerId))
            .append("token", token);

        checkpoints.replaceOne(
            Filters.eq("_id", consumerId),
            state,
            new ReplaceOptions().upsert(true)
        );
    }
}
~~~

### 21.1. Usage in the Watcher

~~~java
MongoCollection<BsonDocument> checkpointCollection =
    client.getDatabase("change_stream_lab")
          .getCollection("consumer_checkpoints", BsonDocument.class);

TokenCheckpointStore store =
    new TokenCheckpointStore(checkpointCollection, "orders-indexer-v1");

BsonDocument last = store.load();

ChangeStreamIterable<Document> stream = orders.watch();
if (last != null) {
    stream = stream.resumeAfter(last);
}

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         stream.maxAwaitTime(1, TimeUnit.SECONDS).cursor()) {
    // Read, process, then save token.
}
~~~

Import `org.bson.BsonDocument` and matching MongoDB driver types.

### 21.2. Save the Exact Token, Never Convert to Custom UUIDs or Strings

`BsonDocument` preserves exact BSON types. If transferring via JSON across systems, parse Extended JSON back into exact BSON types; losing type fidelity can render the token unusable.

### 21.3. Important Checkpoint Metadata

In production, checkpoints should include:

~~~json
{
  "_id": "orders-indexer-v1",
  "token": { "_data": "OPAQUE_BSON_FROM_MONGODB" },
  "streamScope": "change_stream_lab.orders",
  "pipelineVersion": "v3",
  "processorVersion": "search-indexer-2.1",
  "lastProcessedEventId": "E101",
  "updatedAt": "2026-11-14T10:25:00Z"
}
~~~

This JSON is conceptual only; the real `token` must retain its native BSON structure. Metadata guards against accidentally resuming a token created under a different stream definition.

## 22. Java: Reopening the Stream from Checkpoint After Restart

A read loop with clear recovery boundaries:

~~~java
BsonDocument savedToken = store.load();

ChangeStreamIterable<Document> stream = orders.watch();

if (savedToken != null) {
    stream = stream.resumeAfter(savedToken);
}

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         stream.maxAwaitTime(2, TimeUnit.SECONDS).cursor()) {

    while (running) {
        ChangeStreamDocument<Document> event = cursor.tryNext();

        if (event == null) {
            continue;
        }

        // This business handler MUST be idempotent in case of replay.
        processIdempotently(event);

        // Mark done only after processing completes.
        store.save(event.getResumeToken());
    }
}
~~~

`running` and `processIdempotently` are application hooks you must implement; the snippet illustrates **ordering**, not a standalone compilable class.

### 22.1. Exception Between Process and Save

If `processIdempotently` succeeds yet `store.save` fails, the event replays after restart. This is why business idempotency is mandatory even when driver auto-resume works well.

### 22.2. Never Catch-All and Reopen `watch()` from Now

If `cursor.tryNext()` throws, never discard the token and open `orders.watch()` without `resumeAfter`. Doing so silently drops events during downtime.

### 22.3. Driver Auto-Resume vs Application Reconnect Loop

The MongoDB driver automatically resumes certain resumable errors. Applications still need to:

- Reload the durable checkpoint after process restarts.
- Perform bounded retries if the cursor dies after driver retries exhaust.
- Distinguish non-resumable errors.
- Apply backoff and curb log spam.
- Transition the consumer to degraded status when downtime exceeds limits.

## 23. Checkpoints and Downstream Side Effects: Three Options

### 23.1. Checkpoint Before Processing — Risk of Loss

~~~text
save token -> process -> crash
                |
          event may be lost
~~~

Unsuitable whenever dropping events is unacceptable.

### 23.2. Process Before Checkpoint — At-Least-Once

~~~text
process -> save token
    |
    +--> crash => may reprocess
~~~

The standard strategy when side effects are designed idempotently.

### 23.3. Process + Checkpoint Inside One MongoDB Transaction

When **both projection and checkpoint live on the same MongoDB deployment**, commit them atomically in one transaction/session:

~~~text
Change Stream Event E101
       |
       v
Start MongoDB transaction
       |
       +--> Update projection
       +--> Save checkpoint token E101
       |
       v
Commit transaction
~~~

Great for **MongoDB-local materialization**, though it cannot make Kafka, HTTP, or external search engines transactional.

## 24. Java Example: Atomic Checkpoint with Projection

Using the MongoDB Java Sync Driver in a replica set lab:

~~~java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import org.bson.BsonDocument;
import org.bson.BsonString;

public final class MongoAtomicProjector {

    private final MongoClient client;
    private final MongoCollection<BsonDocument> projections;
    private final MongoCollection<BsonDocument> checkpoints;

    public MongoAtomicProjector(
            MongoClient client,
            MongoCollection<BsonDocument> projections,
            MongoCollection<BsonDocument> checkpoints) {
        this.client = client;
        this.projections = projections;
        this.checkpoints = checkpoints;
    }

    public void apply(String consumerId, String businessKey,
                      ChangeStreamDocument<?> event) {

        BsonDocument token = event.getResumeToken();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(() -> {
                BsonDocument projection = new BsonDocument(
                    "_id", new BsonString(businessKey))
                    .append("lastEventToken", token);

                projections.replaceOne(
                    session,
                    Filters.eq("_id", businessKey),
                    projection,
                    new ReplaceOptions().upsert(true)
                );

                BsonDocument checkpoint = new BsonDocument(
                    "_id", new BsonString(consumerId))
                    .append("token", token);

                checkpoints.replaceOne(
                    session,
                    Filters.eq("_id", consumerId),
                    checkpoint,
                    new ReplaceOptions().upsert(true)
                );

                return null;
            });
        }
    }
}
~~~

### 24.1. Guarantee Scope

This is a **transaction-mechanics example**; the projection stores only the token for brevity. Production code must map payloads, enforce versioning/ordering, and guarantee idempotency. Because `withTransaction` retries its callback, **never** perform external side effects inside it.

### 24.2. Do Not Read the Change Stream Inside This Transaction

The consumer reads events from an independent cursor, then uses a separate transaction to persist projection + checkpoint. Never try to run `watch()` as a transactional write operation.

### 24.3. Same Cluster Is Not Enough Without the Same Session

Every MongoDB write in the transaction must call the overload accepting `ClientSession`. Omitting `session` on `projections.replaceOne(...)` executes it outside the transaction.

### 24.4. Still Not System-Wide Exactly Once

External HTTP calls or Kafka publishes do not roll back with a MongoDB transaction. “Exactly-once projection” holds strictly within the narrow boundary of atomic checkpoints and idempotent writes—never claim exactly-once external delivery.

## 25. Idempotency Model Using Business Event IDs

Resume tokens work well for checkpoints, whereas downstream duplicate suppression should use meaningful business IDs:

~~~text
eventId = order-123:status-confirmed:v7
~~~

Example materialized event table:

~~~javascript
db.processed_events.createIndex(
  { eventId: 1 },
  { unique: true, name: "unique_business_event" }
);
~~~

### 25.1. Do Not Rely Only on Document `_id`

An order changes multiple times: created, paid, refunded. Using only `documentKey._id` as the deduplication key drops legitimate subsequent events.

### 25.2. Unique Insert and Idempotent Upsert

- First sight of `eventId`: insert/update projection.
- Replay of same `eventId`: recognize already processed and emit zero duplicate side effects.
- Newer event version: apply according to ordering/causal rules.

### 25.3. Account for Commit Ambiguity

If a MongoDB transaction commit times out with an unknown outcome, never blindly resend an HTTP payment call. Use the same business ID to reconcile state and retry safely.

## 26. Spring Data MongoDB: Synchronous Change Streams

Spring Data provides `MessageListenerContainer` atop the sync driver, managing blocking listener tasks on worker threads.

Skeleton per Spring Data documentation:

~~~java
MessageListenerContainer container =
    new DefaultMessageListenerContainer(mongoTemplate);

container.start();

MessageListener<ChangeStreamDocument<Document>, Document> listener =
    message -> {
        // Read metadata/event and invoke idempotent processor.
        // Save token after durable processing.
    };

ChangeStreamRequestOptions options =
    new ChangeStreamRequestOptions(
        "change_stream_lab",
        "orders",
        ChangeStreamOptions.empty()
    );

Subscription subscription = container.register(
    new ChangeStreamRequest<>(listener, options),
    Document.class
);
~~~

This is a **skeleton** requiring version-appropriate Spring Data imports, error handlers, lifecycle bean management, and checkpoint integration.

### 26.1. `ChangeStreamRequest` Needs an Error Handler

Per Spring Data documentation, listener errors route to an `ErrorHandler`; the default merely logs errors. **Logging alone is not enough** to ensure consumers recover cleanly from checkpoints. Implement an error handler that monitors, restarts subscriptions, and escalates non-resumable errors.

### 26.2. Stop Streams Cleanly on Shutdown

During application shutdown, stop the container/subscription gracefully and await in-flight processing/checkpointing within a deadline. Never abort mid-flight while marking an event processed if side effects did not commit.

### 26.3. Use `Document` for Database-Level Watches with Mixed Schemas

Database-wide watches emit events from collections with different schemas; mapping everything to one typed entity fails. Read raw `Document` or dispatch by namespace.

## 27. Spring Data Reactive Change Streams

Spring Data supports reactive streams:

~~~java
Flux<ChangeStreamEvent<Document>> changes =
    reactiveTemplate.changeStream(Document.class)
        .watchCollection("orders")
        .listen();
~~~

In a reactive service, compose processing and checkpointing sequentially:

~~~java
changes
    .concatMap(event ->
        processEvent(event)
            .then(saveCheckpoint(event.getResumeToken()))
    );
~~~

`processEvent` and `saveCheckpoint` are illustrative `Mono<Void>` methods. Ensure proper lifecycle subscription and error/retry strategies.

### 27.1. Why `concatMap`?

`concatMap` preserves sequential event processing order inside a subscription far better than concurrent `flatMap` when checkpoints must advance strictly in order. High concurrency could checkpoint a newer event before an older event finishes, causing event loss on restart.

### 27.2. Reactor Retry Alone Does Not Solve Everything

`retryWhen` can resubscribe to the stream, yet:

- It must reload the latest committed token, not reuse the startup token.
- It must separate resumable errors from history loss and auth failures.
- It needs bounded backoff with jitter.
- It must avoid spawning duplicate parallel subscriptions sharing one consumer checkpoint.

### 27.3. Timestamp Resume Is a Conditional Fallback

Spring Data supports `resumeAt(Instant)`; however, never pass `Instant.now()` on restart and claim zero events were lost. Prefer exact resume tokens whenever available; timestamp starts require oplog history coverage and deduplication.

### 27.4. Watch Out for Unawaited Async Subscriptions

A stray `subscribe()` inside `doOnNext` finishes asynchronously without blocking checkpoint advancement. Compose publishers properly inside `concatMap`/`flatMapSequential`, and test crashes between processing and checkpointing.

## 28. Java Failover Tests: Orchestration Instead of Fixed Sleeps

Reliable tests wait on **conditions** rather than calling `Thread.sleep(5000)` and hoping the election finished.

~~~text
1. Bootstrap three-node replica set
2. Wait until exactly one PRIMARY and secondaries caught up
3. Start consumer with checkpoint store
4. Generate first N committed events
5. Wait until consumer checkpoint at N
6. Initiate stepdown through dedicated admin connection
7. Wait until new PRIMARY elected
8. Generate next M committed events
9. Wait until consumer projection contains expected IDs
10. Assert missing=0, duplicate side effects=0, lag<SLO
11. Close resources, save timeline/metrics
~~~

### 28.1. Test Timeouts

Never let tests hang indefinitely when no primary emerges. Wait up to a configurable deadline; on expiry, dump status diagnostics and fail.

### 28.2. Separate Infrastructure Setup from Feature Assertions

A test failing because the replica set failed to bootstrap is an **infrastructure/setup failure**, not proof that change stream recovery failed. Classify failures explicitly.

### 28.3. Never Treat a Fixed Election Delay as a Guarantee

Election timeouts, heartbeats, and network timings vary by config and load. Poll actual observed primary identity (`hello`) and driver topology state.

## 29. JUnit Integration Test: Structural Sketch

JUnit 5 pseudocode:

~~~java
@Test
void resumesAfterPrimaryFailover() {
    String runId = uniqueRunId();

    ensureHealthyThreeNodeReplicaSet();
    startConsumer(runId);

    writeCommittedEvents(runId, 1, 20);
    awaitProcessed(runId, 20);

    String oldPrimary = currentPrimaryId();
    stepDownCurrentPrimaryInLab();
    awaitPrimaryDifferentFrom(oldPrimary);

    writeCommittedEvents(runId, 21, 40);
    awaitProcessed(runId, 40);

    assertExpectedEventIds(runId, 1, 40);
    assertNoDuplicateSideEffects(runId);
    assertCheckpointAdvanced(runId);

    stopConsumer();
}
~~~

Helpers above are **test harness methods**, not standalone runnable Java code. Real suites also need bounded retries/backoff for writes during elections plus an overall timeout.

### 29.1. How Can Testcontainers Help?

- Single-node replica set: tests `watch`, cursors, resume, and process crashes.
- Multi-node replica set: requires configuring container networking and advertised hosts to test real elections.
- Toxiproxy or a network fault harness: tests one-way and two-way connection drops.
- JUnit: assertions, deadlines, cleanup, and reporting.

Testcontainers APIs and MongoDB module packages differ across versions; verify javadocs before copying imports.

### 29.2. Keep Heavy Failover Tests Out of Rapid Unit Loops

Unit tests can mock handlers and checkpoint stores. True failover tests belong in an integration/chaos suite with dedicated infrastructure, scheduled appropriately in CI/staging.

## 30. Assertion Table by Fault Type

| Fault | Primary assertion | Additional assertions |
|---|---|---|
| Consumer restart | Resumes from exact token after restart | Zero missing IDs |
| Crash after side effect | Event replays | Zero duplicate side effects |
| Network disconnect | Reconnects within deadline | Checkpoint never advances ahead |
| Primary stepdown | New primary elected; consumer continues | Zero missing majority-committed events |
| Primary kill | Majority failover completes | Driver recovers; zero data corruption |
| Majority loss | Rejects/stalls unacknowledgeable writes | Recovers once quorum returns |
| Oplog expired | Enters explicit history-lost state | Never claims caught-up |
| Invalidate | Cursor closes semantically | `startAfter`/rebootstrap per policy |
| Shard removal | Error detected cleanly | Never assumes automatic resumption |
| TLS failure | New connections rejected | Never disables verification |
| Auth revoked | Clear authorization failure | Zero retry storms |
| Slow sink | Controlled lag growth | Backpressure; checkpoint lags behind processing |
| Duplicate workers | Lease/fencing or idempotency holds | Zero backward/corrupted checkpoints |

### 30.1. Include Negative Tests

A solid suite also confirms the system **refuses to report success** when unable to resume due to history loss, and never jumps ahead to wall-clock time when a token is lost.

### 30.2. Zero Duplicate Reads Are Not Required

Under at-least-once delivery, duplicate **deliveries** can happen. What matters is zero duplicate **business side effects** and accurate final state.

## 31. Verifying Consistency When Writers Time Out

If a writer calls `insertOne` and the network drops before ACK, the outcome is uncertain. Never count an uncertain failed write attempt as a mandatory expected event.

Oracle design:

1. Every event carries a unique `testRunId` and `seq`.
2. Writers use appropriate write concern/durability.
3. On unknown ACK, the writer reads back by unique key to reconcile.
4. Only documents confirmed persisted at target consistency enter the expected set.
5. Post-test, compare the expected set against consumer-processed IDs.

### 31.1. Never Use `w:1` to Represent Majority-Committed Writes

A `w:1` write can roll back after failover. Requiring every `w:1` write to produce a permanent change event is semantically wrong.

### 31.2. Unique Business IDs Protect Retries

When a writer retries `insertOne` after an unknown outcome, a duplicate key indicates the initial attempt succeeded. Use idempotent writes or reconciliation to avoid duplicating data.

## 32. Drop/Rename and Invalidation Tests

In an **isolated lab**, after opening a cursor on `orders`, run DDL:

~~~javascript
use change_stream_lab

db.orders.renameCollection("orders_archive");
~~~

Or:

~~~javascript
db.orders.drop();
~~~

These are destructive test operations; never run them on production.

### 32.1. Expectations

- Collection-level cursor receives an `invalidate` event per supported behavior.
- Cursor closes.
- `resumeAfter` with an invalidate token **is invalid** for continuing past invalidation.
- `startAfter` can open a new stream after invalidation, yet schema/namespace validity must be re-evaluated.

### 32.2. Define Application Policy Explicitly

If a production collection is unexpectedly renamed, the consumer should enter incident mode and wait for data owners rather than silently switching sources.

### 32.3. Database-Level Watch Differs from Collection-Level

Dropping one collection does not invalidate a database-level watcher the same way as a collection watcher. Test the exact scope your app uses.

## 33. Pipeline Filters, `_id`, and Versioning

You can filter solely for inserts and updates:

~~~javascript
const pipeline = [
  {
    $match: {
      operationType: { $in: ["insert", "update"] }
    }
  }
];

const cursor = db.orders.watch(pipeline);
~~~

### 33.1. Never Drop or Alter Event `_id`

MongoDB docs require preserving the `_id` resume token; since MongoDB 4.2, change stream pipelines modifying `_id` throw errors.

### 33.2. Filters Can Hide `invalidate` Events

If a pipeline filters out lifecycle events needed to handle namespace changes, the consumer misses semantic signals. Design filters and recovery together by scope, and never mutate filters across a checkpoint resume without a migration plan.

### 33.3. Version Pipelines

Checkpoint metadata:

~~~text
consumerId=orders-indexer
streamScope=change_stream_lab.orders
pipelineVersion=v2
fullDocumentMode=updateLookup
token=BSON...
~~~

Upgrading from v2 to v3 may require pausing, rebootstrapping, and reconciling rather than feeding a v2 token into a v3 pipeline.

## 34. `fullDocument: updateLookup` Is Not an Immutable Snapshot

Given sequential updates:

~~~javascript
db.orders.updateOne(
  { _id: "order-002" },
  { $set: { status: "PAID" } }
);

db.orders.updateOne(
  { _id: "order-002" },
  { $set: { status: "SHIPPED" } }
);
~~~

If a lagging consumer reads the first update with `fullDocument: "updateLookup"`, `fullDocument.status` may already read `SHIPPED` instead of `PAID`. Only `updateDescription` describes the field delta of that specific update event.

### 34.1. Pre/Post Images

MongoDB 6.0+ supports pre/post images under specific configuration and conditions. If you need exact before/after document snapshots per change, evaluate that feature and its retention explicitly rather than assuming it is enabled by default.

### 34.2. Event Size

Adding `fullDocument` or pre/post images can push change events past the BSON document size limit, failing the cursor. Test large documents, event-splitting support on your server version, and payload caps.

### 34.3. Data Mapping Changes

If Spring Data entity mapping breaks on an event from another collection, read raw `Document` so schema drift in unrelated collections does not crash the subscriber.

## 35. Watch Scope: Collection, Database, or Deployment?

| Scope | Advantage | Risk |
|---|---|---|
| Collection | Easy filtering, clear business context | Drop/rename invalidates easily |
| Database | One watcher covers multiple collections | Must route by namespace/schema |
| Deployment | Covers all databases | Broad privileges, high volume, complex routing |

### 35.1. Avoid Deployment-Wide Watches When One Collection Suffices

`changeStream` and `find` privileges across all databases can expose sensitive multi-tenant data. Minimize scope to shrink blast radius and throughput overhead.

### 35.2. Hot Namespaces

A database-level watcher can lag behind heavy write bursts in an unrelated collection, starving critical collections. Partition consumers by workload where needed.

## 36. Contention Between Multiple Consumers

Two worker pods sharing one checkpoint ID:

~~~text
Worker A reads E100, processes slowly
Worker B reads E101, processes fast and saves token E101
Worker A then saves token E100
=> checkpoint moves backward
~~~

Or conversely, the checkpoint leaps ahead of an unprocessed event.

### 36.1. One Logical Consumer = One Owner

In active/standby deployments:

- Only one worker holds the lease/fencing token.
- Use leader election or managed coordination.
- Guard checkpoint writes with compare-and-set/monotonic protections.
- Workers losing the lease stop emitting side effects and checkpoints.

### 36.2. Scaling Worker Groups Horizontally?

Change Streams are not Kafka consumer groups with automatic partition assignment. Horizontal scaling requires partitioning by business key/namespace, splitting streams, or ordered dispatching with careful checkpoint coordination.

### 36.3. Never Compare Resume Tokens as Numeric Order

Resume tokens are opaque BSON. Never sort or compare `_data` strings to decide which token is newer. For checkpoint ordering, use application sequences/versions or a proper fencing protocol.

## 37. Backpressure and Slow Downstreams

A slow consumer causes:

- Open cursor with growing lag.
- Oplog history window shrinking relative to consumer lag.
- Growing in-memory application queues.
- Overloaded external sinks.
- Stalled checkpoint progress.

### 37.1. Use Bounded Queues

Never buffer millions of events in an unbounded Java queue. If the process crashes, uncheckpointed in-memory events replay; huge queues risk OOM.

### 37.2. Design Processing Concurrency Deliberately

If per-order ordering is required, shard work by `orderId` and process sequentially per partition. Global stream checkpoints must still never advance past unfinished events in any partition.

### 37.3. Alert Before Lag Exceeds History

Example:

~~~text
Oplog window: 8 hours
Consumer lag: 6 hours
Headroom: 2 hours
~~~

Alerting only after the consumer disconnects is too late; track backlog, lag, and oplog headroom continuously with verified metrics.

## 38. Metrics and Logs to Instrument

Names below are **illustrative custom application metrics**, not built-in MongoDB metrics:

~~~text
change_stream_events_received_total
change_stream_events_processed_total
change_stream_events_failed_total
change_stream_event_duplicate_total
change_stream_resume_attempts_total
change_stream_resume_failures_total
change_stream_history_lost_total
change_stream_checkpoint_age_seconds
change_stream_processing_duration_seconds
change_stream_reconnect_duration_seconds
change_stream_consumer_lag_seconds
change_stream_active_subscriptions
change_stream_read_idle_seconds
change_stream_current_primary_changes_total
~~~

### 38.1. Separate Healthy Idle from Stalled

A consumer may receive zero events simply because the database is quiet. **Zero new events** alone does not mean stalled. Compare:

- Source write traffic.
- Cursor/driver health.
- Last successful `getMore`.
- Checkpoint watermark / processed event.
- Oplog window.
- Canary event injection in tests.

### 38.2. Core Alerts

| Alert | Purpose |
|---|---|
| Consumer not running | No active watcher |
| Sustained resume failures | Repeated reconnect failures |
| Checkpoint age breaches SLO | Downstream data falling stale |
| Low oplog headroom | Risk of losing resumability |
| History lost | Immediate reconciliation required |
| Duplicate side effects | Idempotency broken |
| Primary election + resume errors | Failover correlation |
| Logging-only error handler | Consumer may fail silently |

### 38.3. Tracing

Record logical event ID / trace ID, consumer ID, attempt count, `operationType`, namespace, error category, timestamps, and checkpoint version. Avoid logging raw payloads, credentials, PII, or unbounded tokens.

## 39. Runbook: Consumer Halts After Election

1. **Triage:** Is there user impact? How many events are backlogged? How stale is the projection?
2. **Topology:** Check current primary and replica health.
3. **Driver:** Inspect server selection, sockets, resumable error labels, and reconnect attempts.
4. **Checkpoint:** Retrieve the last committed token, stream scope, and pipeline version.
5. **History:** Check oplog window; is the token still inside retention?
6. **Recovery:** If resumable, reopen `watch` with identical pipeline/options and `resumeAfter`.
7. **Integrity:** Compare expected vs processed IDs and projection invariants.
8. **Observe:** Watch lag return to baseline.
9. **Escalate:** On history loss or corrupt checkpoints, refuse to report recovered until reconciled.
10. **Postmortem:** Improve retry logic, monitoring, retention, and fencing.

### 39.1. Avoid Destructive Actions That Erase Evidence

Never wipe the checkpoint collection or swap pipeline versions mid-incident before taking snapshots and diagnostics. Blindly “resetting the stream to now” loses track of unprocessed events.

### 39.2. Runbook for Unknown Errors

Network faults are often resumable; missing privileges, invalid pipelines, and history loss require different remediation. Classify via MongoDB error codes/labels and version docs instead of blanket catch-alls.

## 40. Common Failures and Diagnostic Guide

| Symptom | Likely cause | Remediation |
|---|---|---|
| Standalone watch fails | No replica set oplog | Use a replica set |
| Watcher silent | No events yet or cursor not open | Insert test event, inspect cursor |
| Missed events before watch opened | No starting point | Open watch early or use token/time |
| Missing events after restart | Checkpointed before processing | Reorder / add idempotency |
| Duplicate events after restart | Crashed before checkpointing | Deduplicate by business ID |
| Stream dies after election | Driver exhausted auto-resume; app lacks loop | Durable checkpoint + reconnect loop |
| Cannot find new primary | Wrong URI / `directConnection` / seed list | Multi-host URI / SDAM |
| Stepdown fails | No up-to-date electable secondary | Check health / quorum / catch-up |
| Brief write failures | Election in progress | Bounded retries and SLO |
| Token cannot resume | Oplog history lost | Rebootstrap / reconcile |
| Resume after invalidate fails | Wrong option used | Use `startAfter` per policy |
| Filter breaks token | Altered `_id` | Preserve event `_id` |
| Pipeline version upgrade fails | Incompatible token and options | Version / migration plan |
| Unexpected `fullDocument` | `updateLookup` reads latest majority | Use deltas or pre/post images |
| Consumer lag grows | Slow downstream | Backpressure / capacity |
| Projection wrong despite all events | Ordering or logic bug | Versioning / ordering tests |
| Two consumers overwrite checkpoint | Missing lease/fencing | Single owner / conditional writes |
| Single `mongod` test cannot elect | No secondary | Use a 3-member replica set |
| DNS/TLS error | Bad runtime network/truststore | Fix DNS/CA; never disable TLS |
| Auth fails after rotation | Stale vs new credentials out of sync | Synchronize rotation rollout |
| Read preference fails after election | Node role changed (version-specific) | Resumable handling |
| Shard removal closes cursor | Sharded topology change | Reconcile per docs |

## 41. Security and Compliance During Testing

### 41.1. Never Use Real Data for Chaos Tests

Use isolated lab databases/collections with synthetic IDs. Test data appears in logs, profilers, artifacts, and downstream test sinks; keep real PII out.

### 41.2. Least Privilege

Consumers need watch privileges in scope plus minimal write rights for projections/checkpoints; chaos harnesses use separate admin rights. Never grant `clusterAdmin` to a consumer just so it can run `rs.stepDown` in tests.

### 41.3. Audit Every Fault Injection

Record:

~~~yaml
testRunId: failover-lab-2026-11-14-A
scenario: planned-primary-stepdown
environment: isolated-test
faultInjectedAtUtc: 2026-11-14T10:25:00Z
faultOwner: test-runner
expected: resume-without-missing-committed-events
observed: pending
~~~

This is an illustrative test report schema, not a MongoDB config.

### 41.4. Avoid Leaking Resume Tokens and Metadata

While resume tokens are not passwords, they expose stream/cluster state and metadata. Restrict access to checkpoint stores, enforce log retention, and omit raw tokens from public alert channels unless needed.

## 42. CI/CD and Chaos Testing Strategy

Tiered testing:

| Tier | When to run | Goal |
|---|---|---|
| Unit | Every PR | Handlers, deduplication, checkpoint ordering |
| Single-node RS integration | Every PR/merge | Basic watch/resume/rollback |
| 3-node failover integration | Scheduled / key PRs | Elections, network drops, driver SDAM |
| Stress/soak | Scheduled | Throughput, lag, memory, catch-up recovery |
| Staging chaos | Before major releases | End-to-end pipeline and runbooks |
| Disaster recovery drill | Per policy | History loss, rebootstrap, backup correctness |

### 42.1. CI Needs Deterministic Failure Injection

Use test harness latches to control crash timing:

~~~text
afterProcessBeforeCheckpointLatch
afterCheckpointBeforeNextPollLatch
whileGetMoreBlockedLatch
afterPrimaryStepdownLatch
~~~

Internal test hooks/latches belong strictly in test harnesses—never leave debug kill switches in production APIs.

### 42.2. Guarantee Cleanup

Every test must close cursors/`MongoClient`, restore network rules, recover members, clean up synthetic data per policy, and never leave a broken replica set affecting subsequent tests.

### 42.3. Test Artifacts

Save:

- Test run ID, server/driver versions.
- UTC fault timeline.
- Node states and election markers.
- Expected/processed/duplicated event IDs.
- Resume attempts and checkpoint transitions.
- Latency, lag, and duration.
- Exit status and assertion failures.
- Redacted diagnostic evidence.

## 43. Pre-Failover Test Checklist

### Infrastructure

- [ ] Lab/staging environment authorized for fault injection.
- [ ] Replica set has electable secondaries and healthy majority.
- [ ] Java Driver and Spring Data versions recorded.
- [ ] Writer uses appropriate write concern to confirm committed events.
- [ ] Oplog window covers test duration.
- [ ] Network/TLS/auth verified prior to test.
- [ ] Separate admin session ready for stepdown.
- [ ] Rollback/restore/cleanup plan ready.

### Consumer

- [ ] Checkpoint store persists outside process memory.
- [ ] Tokens saved as native BSON without type-losing stringification.
- [ ] Stream scope, pipeline, and options versioned.
- [ ] Checkpoints saved after processing or atomically with projection.
- [ ] Idempotent handling of duplicate deliveries.
- [ ] Bounded retries and backoff configured.
- [ ] Resumable, invalidate, and history-lost errors handled separately.
- [ ] No uncontrolled concurrent workers sharing a consumer ID.
- [ ] No blocking raw cursors running on request or event-loop threads.

### Acceptance

- [ ] Expected event set derived from majority-committed writes.
- [ ] Normal reconnect tested.
- [ ] Crash before/after checkpoint tested.
- [ ] Stepdown and hard-stop primary tested.
- [ ] Network partition tested.
- [ ] History-lost negative test covered.
- [ ] Invalidation/`startAfter` tested per scope.
- [ ] Final projection state verified.
- [ ] Zero missing events or duplicate side effects.
- [ ] RTO / consumer catch-up SLO met.
- [ ] Alerts and runbooks verified.
- [ ] Logs and artifacts free of sensitive data.

## 44. Self-Practice Exercises

Use only a **lab** MongoDB replica set; never run `rs.stepDown`, drop collections, block networks, or kill processes in production.

### Exercise 1 — Why Do Change Streams Need a Replica Set?

Explain the oplog's role. Can a standalone `mongod` with authentication enabled run `watch()` without a replica set?

### Exercise 2 — Event vs Token

An event contains both `_id` and `documentKey._id`. Which field is the resume token?

### Exercise 3 — Majority Commit

A `w:1` write rolls back after an election. Should the consumer be required to permanently preserve that write?

### Exercise 4 — Cursors and Consumers

If the client app crashes, does MongoDB automatically store a durable checkpoint for the application?

### Exercise 5 — `resumeAfter`

A consumer processes `E20` and saves the token. Which option resumes after `E20` on restart?

### Exercise 6 — `startAfter`

A collection is dropped and `invalidate` arrives. Why can't `resumeAfter` take that invalidate token?

### Exercise 7 — `startAtOperationTime`

Why does passing `Instant.now()` after a 30-minute outage risk losing events?

### Exercise 8 — Identical Pipeline

You change a `$match` filter between stream runs. Should you reuse the old token, and why?

### Exercise 9 — Event IDs

One document receives three updates. Why can't `documentKey._id` serve as the unique ID for each change event?

### Exercise 10 — Checkpoint Before Processing

Write a timeline showing how `E101` gets lost when the token is saved before side effects finish.

### Exercise 11 — Checkpoint After Processing

Write a timeline where `E101` replays yet avoids sending two order notifications.

### Exercise 12 — Atomic Checkpoints

If projection and checkpoint share the same MongoDB cluster, how can a transaction combine them? Can it roll back a Kafka event?

### Exercise 13 — Basic `mongosh` Lab

Create an `orders` collection, open `watch`, insert a document, and inspect the resume token.

### Exercise 14 — `mongosh` Resume

Save the first event's token, close the cursor, update the document, reopen `watch` with `resumeAfter`, and verify the new event arrives.

### Exercise 15 — Planned Stepdown

Why is at least one up-to-date electable secondary needed before calling `rs.stepDown(60, 15)`?

### Exercise 16 — Primary Kill

What differs between a stepdown and hard-stopping the primary? Can in-flight writes become ambiguous?

### Exercise 17 — Quorum

With three voting members and two nodes lost, what happens to writes and change streams?

### Exercise 18 — Oplog Window

Oplog window is 4 hours; the consumer was offline 6 hours. Which recovery strategy must be ready?

### Exercise 19 — Event Sets

The writer emits IDs `E001..E100`. Consumer output has 100 records, yet one ID is duplicated and one is missing. Does the test PASS?

### Exercise 20 — Java Cursors

Distinguish `next()`, `tryNext()`, `maxAwaitTime()`, and returning `null` when no events exist.

### Exercise 21 — `BsonDocument`

Why is storing the raw `BsonDocument` resume token superior to storing an application-formatted string?

### Exercise 22 — Auto-Resume

Does the driver's single auto-resume after a resumable error replace durable checkpoints across process restarts?

### Exercise 23 — Read Preferences

What did MongoDB 9.0 introduce regarding `InterruptedDueToReplStateChange` after elections?

### Exercise 24 — Spring Data Sync

Why does `MessageListenerContainer` need dedicated worker threads and an error handler? Is logging errors by default enough?

### Exercise 25 — Spring Data Reactive

Why is `concatMap` preferred over concurrent `flatMap` when checkpointing a single stream?

### Exercise 26 — Reactor Retries

A `retryWhen` block opens a fresh stream from current time after errors. Can it drop events?

### Exercise 27 — `updateLookup`

If a document updates quickly to `PAID` and then `SHIPPED`, can `fullDocument` on the first event read `SHIPPED`?

### Exercise 28 — Pre/Post Images

When do you need exact pre-images instead of `updateLookup`? What server prerequisites apply?

### Exercise 29 — Multiple Consumers

Two workers write to the same checkpoint. Describe lease/fencing or deduplication techniques preventing backward or skipped checkpoints.

### Exercise 30 — Sharded Clusters

Why test per-shard/hot-shard behavior and handle cursor closure on shard removal?

### Exercise 31 — Network Recovery

Simulate a 20-second consumer-to-cluster disconnect. Which assertions prove recoverability?

### Exercise 32 — DNS/TLS

After a CA rotation, new connections fail. Why should you never enable `tlsInsecure` instead of fixing the truststore?

### Exercise 33 — Alerting

Design metrics for checkpoint age, history headroom, resume attempts, and consumer catch-up time.

### Exercise 34 — Runbook

Write consumer recovery steps after an election, distinguishing history-lost and invalidate cases.

### Exercise 35 — Testcontainers

A single-node replica set suffices for testing resume tokens—why is it insufficient for secondary elections?

### Exercise 36 — CI Strategy

Distinguish unit, integration, 3-node failover, and staging chaos suites; what does each verify?

### Exercise 37 — Incident Data Privacy

An event contains a customer address. Should failed-resume alerts log the entire `fullDocument`?

### Exercise 38 — Capstone Scenario

Design a Spring Boot + MongoDB Java Driver index-sync service featuring:

- A three-node replica set.
- Writers using unique IDs and majority commits.
- Change Streams cursor consumer.
- Durable BSON resume tokens.
- Scoped pipeline versioning.
- Idempotent downstream processing.
- Crash injection between processing and checkpointing.
- Planned stepdowns and primary kills.
- History-lost and invalidate tests.
- Bounded retries and backpressure.
- Metrics, alert routing, runbooks, and acceptance assertions.

## 45. Summary

Testing **disconnects, primary stepdowns, and change stream resumption** reliably requires combining three layers:

**Layer 1 — MongoDB topology and history:** Healthy replica set or sharded cluster, majority-committed writes, sufficient oplog history, driver topology discovery, and lab-tested elections.

**Layer 2 — Consumers and checkpoints:** Opaque BSON resume tokens, fixed pipelines/options, semantic selection of `resumeAfter`/`startAfter`, and checkpoints persisted strictly after processing or atomically with projections. Driver auto-resume never replaces durable restart recovery.

**Layer 3 — Business correctness:** At-least-once delivery can replay events; enforce idempotency, fencing, and reconciliation. Tests must verify more than reconnecting: **zero missing committed events, zero duplicate business side effects, accurate final state, and recovery within SLO**.

Final rule: **You can never resume from an oplog-expired token by retrying forever. Report the history gap explicitly and run a verified re-bootstrap/reconciliation workflow rather than silently starting from now.**

## Official References

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changestreams/)
- [MongoDB Manual — db.collection.watch()](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [MongoDB Manual — $changeStream Aggregation Stage](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/)
- [MongoDB Manual — Change Stream Invalidate Events](https://www.mongodb.com/docs/manual/reference/change-events/invalidate/)
- [MongoDB Manual — Change Stream Update Events](https://www.mongodb.com/docs/manual/reference/change-events/update/)
- [MongoDB Java Sync Driver — Open Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [MongoDB Java Sync Driver — Monitor Events](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/monitoring/)
- [Spring Data MongoDB — Change Streams](https://docs.spring.io/spring-data/mongodb/reference/mongodb/change-streams.html)
- [MongoDB Manual — Replica Set Elections](https://www.mongodb.com/docs/manual/core/replica-set-elections/)
- [MongoDB Manual — rs.stepDown()](https://www.mongodb.com/docs/manual/reference/method/rs.stepDown/)
- [MongoDB Manual — rs.printReplicationInfo()](https://www.mongodb.com/docs/manual/reference/method/rs.printReplicationInfo/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/)
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/)
