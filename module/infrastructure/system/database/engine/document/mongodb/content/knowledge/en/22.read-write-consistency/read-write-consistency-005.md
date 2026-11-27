# Replication lag and stale read risks in MongoDB

## 1. Opening scenario: saved successfully, yet the screen still shows old data

An order management application uses a **MongoDB replica set** with one primary and two secondaries. A user changes the shipping address from "Hanoi" to "Da Nang". The update API returns **200 OK**, yet immediately upon refreshing the page, the address still shows "Hanoi". A few seconds later, refreshing again finally shows "Da Nang".

A sequence of events that can occur:

```text
Time           Write API                  Replica set              Read API
   |
   |     PATCH /orders/123
   |          |                       PRIMARY: address = "Da Nang"
   |          +----------------------> Write succeeded
   |          |                                |
   |       200 OK                              | asynchronous replication
   |                                           v
   |                                        SECONDARY A
   |                                        still "Hanoi"
   |                                            |
   |      GET /orders/123 ----------------------+
   |                                            |
   |      Returns "Hanoi" <---------------------+
   |
   |                                     SECONDARY A applies oplog
   |                                     address = "Da Nang"
   v
          Next GET sees "Da Nang"
```

This is an example of a **stale read** — reading data **older than the state expected by the application or user**. There is not necessarily a write error or data loss. The cause may be that the read request was routed to a secondary that has not yet applied the latest operation.

The topic **"Replication lag and stale read risks"** belongs to MongoDB's **Read and Write Consistency** chapter. After this lesson, you will:

- Understand asynchronous replication and distinguish replication lag from API latency.
- Explain why a successful write does not mean every replica immediately holds the new value.
- Distinguish **read preference**, **read concern**, and **write concern**.
- Understand the guarantees of `w: 1`, `w: "majority"`, `readConcern: "local"`, and `readConcern: "majority"`.
- Choose how to ensure *read-your-writes* via the primary or a **causally consistent session** when appropriate.
- Understand the limits of `maxStalenessSeconds` and why it is not a guarantee of the latest data.
- Analyze failover, rollback, concurrent requests, and continuously changing data scenarios.
- Observe replication lag with `mongosh`, interpret metrics, and design safe handling.

## 2. How does a replica set replicate?

### 2.1. Primary and secondaries

In a replica set, the **primary** is the member that receives normal client write operations. **Secondaries** replicate and apply changes from the **oplog** stream of an eligible sync source; the sync source can be the primary or another secondary in allowed configurations.

```text
                    Application
                       |
                insert / update
                       |
                       v
                    PRIMARY
                   +-------+
                   | Data  |
                   | Oplog |
                   +-------+
                    /    \
          replication    replication
             /              \
            v                v
       SECONDARY A       SECONDARY B
       +--------+        +--------+
       | Data   |        | Data   |
       | Oplog  |        | Oplog  |
       +--------+        +--------+
```

Write operations can complete on the primary before one or more secondaries finish applying them. A replica set does not maintain a state where "every node is identical at every millisecond."

### 2.2. The oplog as the basis for catching up

MongoDB maintains an **operations log** in the internal `local.oplog.rs` collection on data-bearing members. The oplog stores changes used for replication; it is not a permanent audit table.

A secondary tracks the position it has applied, fetches missing entries, and updates its local data. If incoming changes arrive faster than it can receive and apply them, the secondary **falls behind**.

Notable points:

- A secondary may have **received** an oplog entry without having **applied** it yet.
- A secondary may have applied it without yet reaching the **durable** state under the monitoring criteria in question.
- MongoDB tracks progress for **applied**, **durable**, and **majority commit point**; do not conflate them.
- Data read on a node depends on the progress that node has reached and the consistency options of the read command.

### 2.3. Replication lag

A common way to monitor lag is comparing the timestamp difference of the last applied operation between the primary and a secondary:

\[
\text{Lag}_{i}\approx
T_{\text{optime(primary)}}-T_{\text{optime(secondary }i\text{)}}
\]

Example at one observation point:

```text
Primary:       last applied = 10:00:10 UTC
Secondary A:   last applied = 10:00:09 UTC
Secondary B:   last applied = 09:58:10 UTC

Lag A ≈   1 second
Lag B ≈ 120 seconds
```

That is a **progress difference**, not "every query on B takes 120 seconds" and not the execution time of a single command. Lag can grow, shrink, or shift abruptly when nodes experience load, change sync sources, or undergo elections.

### 2.4. Oplog window differs from replication lag

The **oplog window** is the history span retained between the oldest and newest oplog entries on a member. **Lag** is how far behind a secondary is relative to the reference progress.

```text
Sync source retains history:
oldest 06:00 -------------------------------- newest 18:00
                  window ~12 hours

Secondary A applied up to 17:58 -> lag ~2 minutes
Secondary B applied up to 10:00 -> lag ~8 hours
```

Secondary B can still catch up if the entries it needs still exist on the sync source, processing capacity is sufficient, and topology permits. If write velocity shrinks the window to 5 hours while B lags by 8 hours, there is a risk that **the oplog no longer holds the required changes**. At that point, the secondary can become *too stale* and require resynchronization.

This lesson focuses on **how lag affects read results and consistency levels**, not solely oplog sizing.

## 3. "Stale data" can have multiple meanings

### 3.1. Stale relative to the user's own latest write

A user changes their name and immediately reads back the old name:

```text
write(name = "An")  -> succeeds
read(name)          -> "Anh"  (previous value)
```

This violates **read-your-writes** expectations: a client expects to observe writes it has already confirmed in subsequent reads.

### 3.2. Stale relative to another user's recent write

User A updates inventory levels; user B uses a dashboard reading from a secondary and does not see the change yet. Immediate visibility might not be expected on that dashboard, yet it is unacceptable if B makes inventory allocation decisions based on stale stock counts.

**Tolerance for stale reads is a business requirement**, not a uniform technical constant across all APIs.

### 3.3. Data moving backward between two reads

Suppose an application uses `nearest` or `secondary` read preference and the driver selects different secondaries:

```text
Read 1 -> Secondary A is at version 12 -> returns version 12
Read 2 -> Secondary B is at version 10 -> returns version 10
```

Even with no new writes between the two reads, the same user can observe data **going backward from newer to older**. This relates to **monotonic reads** guarantees: reads within a contextual flow should not revert to a state earlier than a previously observed read.

### 3.4. Staleness from caches, not the replica set

An outdated value can also come from:

- Redis or an application cache not yet invalidated.
- A CDN or HTTP cache holding an old response.
- A mobile client displaying a local/offline copy.
- A queue/event processor that has not processed an event yet.
- A MongoDB query reading the right database but wrong tenant, filter, or document version.
- Unstable pagination/sorting making results look un-updated.

Do not conclude "replication lag" solely from a screenshot showing old data. Determine the **target read node**, read preference, read concern, cache layers, and when the data was written.

## 4. Read preference: which node does the application read from?

### 4.1. Five common modes

**Read preference** is the policy for selecting a member to execute a read command. It **does not determine the commit level** of the returned data.

| Read preference | Commonly selected read source | Risk of stale read |
| --- | --- | --- |
| `primary` | Current primary | Generally low risk of staleness from secondary lag; still evaluate read concern, elections, and rollbacks |
| `primaryPreferred` | Prefers primary; may use secondary when primary unavailable | When falling back, may see stale data |
| `secondary` | Eligible secondaries | Yes, depending on the selected node's progress |
| `secondaryPreferred` | Prefers secondary; may use primary if no eligible secondary exists | Yes, when reading from a secondary |
| `nearest` | Eligible member by network latency, may be primary or secondary | Yes, because low network latency does not mean fresh data |

In MongoDB drivers, `primary` is the common default read preference. However, an application can configure it at the URI, `MongoClient`, database, collection, or specific read operation level. Do not infer the read node from a single `findOne()` line.

### 4.2. Why does "nearest" not mean "latest"?

Suppose the primary is in region A, while secondary B is closer to the application:

```text
Application
   |
   +-- 5 ms  --> Secondary B (3s lag)
   |
   +-- 50 ms --> Primary (latest updated data)
```

`nearest` read preference optimizes selection by network latency under driver criteria, **not by picking the node with the newest data**. Lower round-trip time may trade off data freshness.

### 4.3. Tag sets and secondary selection

In a replica set, administrators can attach **tags** to members for location- or workload-based routing. An application can request preferring secondaries in a specific region or role.

However:

- Tags do not make a node an instantaneously synchronous copy.
- A selected secondary still has real replication lag.
- An "analytics" or deliberately delayed node is not necessarily suitable for immediate read-after-write APIs.
- If tag rules are too strict, operations may fail to find an eligible node.

Read placement must account for **freshness** and **availability**, not just locality.

### 4.4. Does `maxStalenessSeconds` solve stale reads?

MongoDB drivers support `maxStalenessSeconds` under appropriate conditions to **exclude secondaries estimated to be too stale** beyond the specified threshold.

Illustrative URI example:

```text
mongodb://db1.example:27017,db2.example:27017,db3.example:27017/
?replicaSet=rs0&readPreference=secondary&maxStalenessSeconds=120
```

In practice, the URI must be written on **one line**, with environment-appropriate TLS/authentication.

Key points to remember:

1. `maxStalenessSeconds` uses server/heartbeat information to **estimate staleness** for server selection.
2. It is **not a hard guarantee** that every returned document is at most exactly 120 seconds old.
3. The common minimum valid threshold is **90 seconds**, and it must satisfy driver heartbeat/server selection constraints.
4. If no secondary satisfies the condition, `secondary` mode may fail with server selection errors rather than silently reading from the primary.
5. This setting is incompatible with `primary` read preference because that policy does not select secondaries.
6. It does not fix stale reads from caches, browsers, or sources outside MongoDB.

If business logic requires **immediately seeing a newly acknowledged write**, setting `maxStalenessSeconds: 90` alone is not sufficient.

## 5. Read concern: which data state is permitted to be observed?

**Read concern** defines the consistency/durability semantics of data a read command can observe. It does not select the node; that is read preference's job.

### 5.1. `readConcern: "local"`

`local` is the standard, common read level. It permits reading data present on the handling member without requiring that data to be majority-committed.

If a read goes to secondary A, `local` returns results based on the state A has applied. If A lags, data can be stale.

If a read goes to the primary, `local` can see newly written data on the primary, though non-majority-committed data can undergo rollback after failover in eligible scenarios.

### 5.2. `readConcern: "majority"`

`majority` targets data that has been **majority-committed** per MongoDB semantics. It helps avoid observing uncommitted changes prone to rollback, in supported deployment configurations.

However, **majority does not mean latest**:

```text
Primary:     applied up to order version 15
Secondary A: applied up to order version 13

Read from A with readConcern majority:
    may read a majority-committed state
    that A already has, not necessarily version 15.
```

This is often misunderstood: `readConcern: "majority"` **does not force every secondary to wait until it applies all latest writes on the primary** for every read command.

### 5.3. `readConcern: "linearizable"`

MongoDB supports `linearizable` read concern under specific conditions and constraints, **applicable only when reading from the primary**. Combined with required majority writes, it supports semantics approximating real-time order: a read starting after a covered write completed will not return pre-write state for a matching read of a single document.

Characteristics:

- Intended for strong guarantees, typically scoped to **a single document**.
- Carries higher latency and availability impact.
- Cannot be used to guarantee reads from a secondary are always the freshest.
- Should set an appropriate `maxTimeMS` to avoid waiting indefinitely when conditions cannot be met.

Do not pick `linearizable` for large analytical queries simply because the name sounds "stronger"; understand its requirements and specific limits.

### 5.4. `readConcern: "snapshot"`

`snapshot` provides reading a **consistent snapshot** in supported MongoDB contexts, especially transactions and certain non-transactional reads in supported versions.

A consistent snapshot is useful when reads must see a unified baseline state, though it **does not by default mean the latest snapshot at the moment the client receives the response**.

An aggregation report may require snapshots to avoid mixing incompatible points in time, whereas a "must see immediately after save" API needs a different strategy or added causal semantics.

### 5.5. `readConcern: "available"`

`available` is a read concern level with specific differences in sharded clusters, favoring read availability over majority-committed guarantees. It is not the default choice for protecting screens needing fresh data or preventing reads of rollback-prone changes.

### 5.6. Summary table

| Read concern | Main goal | Does it automatically guarantee secondaries return the latest data? |
| --- | --- | --- |
| `local` | Reads data present on the node | No |
| `majority` | Reads majority-committed data | No |
| `linearizable` | Strong real-time order semantics within supported scope and conditions | Not applicable to secondary reads |
| `snapshot` | Observes a consistent snapshot in supported contexts | Does not mean latest |
| `available` | Read level prioritizing availability in certain contexts | No |

**Read preference picks where to read; read concern sets the reading conditions.** Choosing one while ignoring the other is a common source of false assumptions.

## 6. Write concern: when is a write command considered acknowledged?

### 6.1. `w: 1`

An operation:

```javascript
db.orders.updateOne(
  { orderId: "O-238" },
  { $set: { status: "PAID" } },
  { writeConcern: { w: 1 } }
);
```

`w: 1` typically requests acknowledgment from the primary at the corresponding write level. It **does not wait for all secondaries to finish applying**; it does not even require the operation to be majority-committed.

After the write, reading from a secondary may see the old status. If a failover occurs before the change is majority-committed, a write acknowledged at a weaker level may roll back in eligible scenarios.

### 6.2. `w: "majority"`

```javascript
db.orders.updateOne(
  { orderId: "O-238" },
  { $set: { status: "PAID" } },
  {
    writeConcern: {
      w: "majority",
      wtimeout: 10000
    }
  }
);
```

`w: "majority"` requests acknowledgment from an eligible **majority of voting data-bearing members** in the replica set. This typically strengthens assurances that the operation will not easily be lost during primary transitions.

However:

- **It does not require all secondaries to have applied it yet.**
- A lagging secondary can still return the old status.
- Majority write concern does not replace the read preference/read concern of subsequent reads.
- If waiting for majority times out, the operation **may still have been applied**; the client must not assume "nothing happened."

### 6.3. Journaling and other limits

Write concern includes factors related to durable writes to the journal/storage. The `j` field, system defaults, and `writeConcernMajorityJournalDefault` can affect how durably majority acknowledgments are persisted in specific configurations.

Do not interpret "`majority`" as meaning all data is durably saved on every disk of every node in every topology. For workloads with strict RPO/RTO targets, inspect documentation and deployment configuration.

### 6.4. Three-node illustration

```text
Write X to Primary
     |
     +---- Primary applies X
     |
     +---- Secondary A applies X
     |
     +---- Secondary B has not yet applied X

Majority of 3 voting data-bearing members = 2

The write may have met w:"majority"
yet reading from Secondary B still sees the pre-X value.
```

This is why **"a majority write succeeded" and "every read sees it immediately" are two different statements**.

### 6.5. Timeout is not an automatic rollback

If `wtimeout` expires:

```text
Primary:    wrote X
Secondary:  did not acknowledge enough for majority
Client:     receives write concern timeout/error
```

The write state may be **uncertain relative to the requested guarantee**. Never:

- immediately insert another document with a new ID assuming the previous write did not happen;
- return durable success merely because one node sees the document on a read;
- discard error metadata;
- repeat a non-idempotent credit/debit operation.

Reconcile using stable IDs/operation IDs and appropriate write/read concern policies.

## 7. Matrix combining read preference, read concern, and write concern

Suppose the application just wrote document X and wants to read it back:

| Write | Read | Can stale values appear right after writing? | Remarks |
| --- | --- | --- | --- |
| `w:1` | `primary + local` | Usually sees write on primary if primary does not change; rollback risk on failover | Not a rollback-proof guarantee in all cases |
| `w:1` | `secondary + local` | Yes | Secondary may not have applied it yet |
| `w:"majority"` | `secondary + local` | Yes | Majority ack does not mean all secondaries synced |
| `w:"majority"` | `secondary + majority` | Possible | Data read is majority-committed, though secondary may not have reached the new version yet |
| `w:"majority"` | `primary + majority` | Usually meets read-after-write when sequential and primary is healthy; still evaluate sessions/failovers | Not general linearizability for all clients |
| `w:"majority"` | `secondary + majority + causal session` | May wait; designed to guarantee read-your-writes under supported conditions | Uses the same session and executes sequentially |
| `w:"majority"` | `primary + linearizable` | Strong guarantee when supported conditions are met | Higher latency/availability cost |

This table serves as design guidance. Confirming any specific guarantee requires checking MongoDB version, topology, session semantics, effective write/read concerns, failover behavior, and whether operations completed at the requested levels.

## 8. Ensuring read-your-writes in a business flow

### 8.1. Simple approach: read back from primary

A flow:

```text
Client -> write to primary
Client <- write acknowledged
Client -> read from primary
Client <- fresh data
```

Often suits UIs where:

- a profile was just updated and must display immediately;
- after payment confirmation, the user checks the new status;
- after changing a password/access permission, the current state must be verified;
- after editing a cart, saved items must be visible.

However, reading from the primary **does not automatically solve every risk**. If the write only used `w:1` and an election/rollback occurs, or the read reaches a new primary before the write was majority-committed, results may differ from expectations. When durability and ordering matter strongly, combine appropriate write concern, read concern, and sessions.

### 8.2. Reading from secondaries while still seeing your own writes

To preserve secondary read benefits while needing ordering guarantees, MongoDB supports **causally consistent sessions**. Under supported conditions, executing causally related operations **within the same session** using:

- write concern `"majority"`;
- read concern `"majority"`;
- sequential operations within the session;

can provide guarantees such as **read-your-writes** and **monotonic reads**.

Idea:

```text
Session S:

  write X (majority)
        |
        v
  receive operationTime / causal context
        |
        v
  read from secondary (majority, same S)
        |
        +-- If secondary lacks sufficient progress:
        |      wait up to target point or error/timeout
        |
        +-- When condition is met:
               can see X per causal semantics
```

This is no magic bullet making "reading any secondary instantaneous": a lagging secondary can cause **higher latency** or prevent completion before timeout. For these semantics to work, the driver/server must pass **causal metadata** properly, not merely share a connection string.

### 8.3. Causal consistency is not a transaction

Causal sessions preserve ordering across related operations. They **do not turn multiple writes across multiple documents into an atomic transaction**.

For example:

```text
Update order
Insert audit
Update inventory
```

Three separate operations in the same session can still **partially succeed** if not enclosed in a transaction. If business rules require all three to commit or roll back together, design a multi-document transaction or an alternative suitable data model.

### 8.4. Operations must be serialized when sharing a session

Do not use a single session for concurrent operations in ways the driver does not support. Causal ordering requires an explicit sequence:

```javascript
await collection.updateOne(..., { session });
const value = await collection.findOne(..., { session });
```

Instead of:

```javascript
// Does NOT demonstrate read-after-write; both operations start concurrently.
await Promise.all([
  collection.updateOne(..., { session }),
  collection.findOne(..., { session })
]);
```

Two operations in `Promise.all` have no "read happens after write is acknowledged" relationship. Passing the same session does not establish the desired read-your-writes order.

### 8.5. Causal sessions from request A do not automatically transfer to request B

On the web, a user might call:

```text
PATCH /profile   -> server instance 1
GET   /profile   -> server instance 2
```

If the two requests use independent sessions without causal context, guarantees from the first session **do not automatically carry over** to the second request.

The application can choose to:

- Route freshness-sensitive read-after-write calls to the primary.
- Maintain a consistent session within a server-orchestrated workflow.
- Pass causal tokens/operation times using driver- and protocol-supported APIs when genuinely required.
- Render the confirmed write result directly in the UI while refreshing from an appropriate source.

Do not pass raw session IDs or internal MongoDB metadata arbitrarily through clients and treat that as a consistency guarantee; session design, authentication, and lifetimes must conform to driver/server rules.

## 9. Node.js example: majority write then secondary read in the same causal session

### 9.1. Objective

Create a document in a test collection, write with `w:"majority"`, then read from a secondary using the **same causally consistent session** with read concern `majority`.

Run only on a test replica set with **at least one eligible secondary**; if no secondary exists, selecting `secondary` will fail. This snippet uses the MongoDB Node.js driver; do not run against production business databases.

### 9.2. Configuring client and session

```javascript
import {
  MongoClient,
  ObjectId,
  ReadPreference
} from "mongodb";

const uri = process.env.MONGODB_URI; // Provided replica set URI.
const client = new MongoClient(uri, {
  serverSelectionTimeoutMS: 10000
});

await client.connect();

const database = client.db("mongo_read_consistency_row238_lab", {
  readConcern: { level: "majority" },
  writeConcern: { w: "majority", wtimeoutMS: 10000 }
});

const collection = database.collection("orders_demo");
const session = client.startSession({
  causalConsistency: true
});

const runId = "row238-" + new ObjectId().toHexString();
const orderId = new ObjectId();

try {
  const written = await collection.insertOne(
    {
      _id: orderId,
      runId,
      orderNo: "ORDER-238",
      status: "PAID",
      version: 1,
      createdAt: new Date()
    },
    {
      session,
      writeConcern: { w: "majority", wtimeoutMS: 10000 }
    }
  );

  console.log("insertedId:", written.insertedId.toString());

  const readBack = await collection.findOne(
    { _id: orderId, runId },
    {
      session,
      readPreference: new ReadPreference("secondary"),
      maxTimeMS: 10000
    }
  );

  console.log("readBack:", readBack);
} finally {
  await session.endSession();
  await client.close();
}
```

In this example, `majority` read concern is configured at the database level and inherited by the collection. The read selects `secondary`, while the session maintains causal context.

Key things to interpret accurately:

1. Write and read share the **same session**.
2. The read command starts only **after** `insertOne` has been acknowledged at the requested write concern.
3. If the secondary is lagging, the read may wait to satisfy causal semantics or fail with an error/timeout.
4. On a standalone `mongod` or without an eligible secondary, this example cannot be used to demonstrate stale reads.
5. This is not a latency benchmark; the small test only clarifies consistency contracts.

### 9.3. Errors and cleanup during practice

Production code should classify:

- `server selection timeout`: no eligible secondary found.
- `maxTimeMS`/timeout: did not finish in time; does not mean read concern is broken.
- `writeConcernError`: write may have been applied, though not acknowledged at the requested level.
- `network error`: outcome may be unknown; do not re-insert with a new `_id`.

To clean up the document created by a test run, after checking `runId` and `orderId`, use a **separate command** through an appropriate client/session:

```javascript
const doc = await collection.findOne(
  { _id: orderId, runId },
  { readPreference: new ReadPreference("primary") }
);

if (doc && doc.runId === runId) {
  const removed = await collection.deleteOne({
    _id: orderId,
    runId
  });
  console.log("deletedCount:", removed.deletedCount);
}
```

This cleanup snippet illustrates **safe deletion scoping** and should run before closing the client or in a separate script with initialized variables. Never use `deleteMany({})` or `dropDatabase()` just to clean up a test.

## 10. `mongosh` practice: measuring replication lag instead of inducing failures

### 10.1. Observing the replica set

Connect `mongosh` to a replica set where you have monitoring privileges:

```bash
mongosh "mongodb://localhost:27017,localhost:27018,localhost:27019/?replicaSet=rs0"
```

This is an illustrative local URI; replace hosts, replica set name, TLS, and authentication for your environment.

```javascript
const status = rs.status();

printjson(
  status.members.map((m) => ({
    name: m.name,
    state: m.stateStr,
    health: m.health,
    optimeDate: m.optimeDate,
    syncSourceHost: m.syncSourceHost
  }))
);
```

In versions providing these fields, the output shows:

- which member is `PRIMARY` and `SECONDARY`;
- reported applied `optime` timestamps;
- member health/heartbeats;
- each secondary's sync source if present.

Exact output varies across MongoDB versions. On an active primary, a single `rs.status()` call is only an **observational snapshot**, not a replacement for continuous monitoring.

### 10.2. Estimating lag from member progress

```javascript
const s = rs.status();
const primary = s.members.find((m) => m.stateStr === "PRIMARY");

if (!primary || !(primary.optimeDate instanceof Date)) {
  print("Insufficient primary optimeDate data.");
} else {
  const rows = s.members
    .filter((m) => m.stateStr === "SECONDARY")
    .map((m) => ({
      member: m.name,
      lastApplied: m.optimeDate ?? null,
      estimatedLagSeconds:
        m.optimeDate instanceof Date
          ? Math.max(
              0,
              (primary.optimeDate.getTime() -
                m.optimeDate.getTime()) / 1000
            )
          : null
    }));

  printjson(rows);
}
```

The subtraction uses server-reported fields; timestamps may differ in granularity and freshness. Do not treat `estimatedLagSeconds: 0` as proof that every document is identical across all members.

### 10.3. Helpers and oplog info

```javascript
rs.printReplicationInfo();
rs.printSecondaryReplicationInfo();
```

Depending on shell/server version, these helpers display oplog size/window and secondary lag.

Additional info can be retrieved via admin command:

```javascript
printjson(db.adminCommand({ replSetGetStatus: 1 }));
```

If lacking privileges, do not alter configuration or disable security to view output. Ask a DBA/SRE for metrics from Atlas or an approved observability system.

### 10.4. Why not deliberately force replication lag to rise for demonstrations?

Actions like cutting networks, filling disks, pausing secondaries, blasting millions of writes, or deleting oplogs can harm **availability, elections, oplog windows, data, and backups** across the whole replica set.

Practice should instead:

1. Observe on a test cluster.
2. Write a small document keyed by `runId`.
3. Read from primary and secondary with appropriate privileges.
4. Note cases where **no difference is seen** because replication is too fast.
5. If controlled lag reproduction is desired, follow a dedicated lab with isolated resources and an administrator-approved runbook.

You do not need to induce real faults on a shared replica set to understand consistency semantics.

## 11. Failover, rollback, and data freshness

### 11.1. When the primary changes role

A replica set can elect a new primary when the old primary is no longer eligible. Elections/failovers change the write-accepting node and can disrupt in-flight reads and writes.

```text
Before election:
  Primary P  : has write X
  Secondary A: replicated X
  Secondary B: has not replicated X

After failure:
  An eligible secondary is elected as the new primary.
```

Whether write X survives depends on factors such as replication progress, majority commit, configuration, and election progression.

### 11.2. Why is `w:1` risky?

A write acknowledged by the primary at `w:1` **may not yet be majority-committed**. If that primary loses its role before other members receive the change, MongoDB may roll back operations that are not part of the replica set's committed history.

This differs from ordinary stale reads:

- **Stale read due to lag**: new data exists on some members; the read secondary has not caught up.
- **Rollback**: an operation not committed at the required level may no longer remain in the retained history after failover.

Applications must not interpret a `w:1` response as a durability guarantee across all primary changes.

### 11.3. Is majority write plus primary read enough?

It is an appropriate choice for many standard read-after-write flows. However, if the system needs **linearizability** or strict real-time guarantees, evaluate the corresponding read concern, operation ordering, and session policies.

Do not treat the word "primary" as an absolute promise that every query hitting the primary automatically carries all commit/durability guarantees the application expects.

### 11.4. In-flight reads/writes can fail

During an election, drivers may:

- detect that the primary changed;
- select another server;
- retry certain eligible operations;
- return network/server selection/transient errors.

If the client retries an entire business operation after losing a write response, an **idempotency key** is needed when the operation has non-repeatable side effects, such as deducting inventory or creating payments.

## 12. Causal consistency, monotonic reads, and observation order

### 12.1. Four guarantees mentioned in causal consistency

MongoDB describes causal guarantees for causally related operations under suitable conditions:

| Guarantee | Intuitive meaning |
| --- | --- |
| **Read-your-writes** | After writing X in a causal context, subsequent reads do not revert to pre-X state |
| **Monotonic reads** | A read stream does not observe history moving backward |
| **Monotonic writes** | Causally related writes execute in the proper order |
| **Writes-follow-reads** | Writes after a read respect changes observed earlier |

These guarantees tie to **sessions**, read concern, write concern, and execution order. They cannot be inferred simply because MongoDB is "NoSQL" or uses a single connection pool.

### 12.2. An example of monotonic reads

```text
Session S:
  Read 1 at Secondary A -> version 20
  Read 2 at Secondary B -> must not regress to version 18
```

When a causal session is used properly, server/driver enforce causal ordering, or the read waits/fails if the member lacks progress. Without causal context, two reads selecting different secondaries can return states from different points in time.

### 12.3. What causal sessions do not do

They do not:

- make all secondaries synchronize instantaneously;
- replace multi-document transactions;
- automatically create unique indexes;
- guarantee all independent clients' data obeys a single global real-time order in all cases;
- prevent another HTTP request using a new session from reading stale data;
- fix data cached in the application layer.

**Causal consistency is a specific guarantee model**, not a "strong consistency for everything" switch.

## 13. Choosing consistency levels by API type

There is no single optimal read/write pair for all applications. Describe the **impact of stale reads** first, then select a policy.

### 13.1. User profiles: immediate visibility required

After `PATCH /profile`, the user expects to see the new name/avatar:

- Write with a write concern matching business durability needs.
- Read back from primary or use a causal session when reading secondaries.
- Update UI state from the server response while managing cache invalidation.
- If GET routes to another server, maintain session/token consistency or appropriate routing.

A GET hitting an arbitrary secondary immediately after PATCH can cause "I saved it, yet the data reverted."

### 13.2. Balances or inventory: accuracy required for decisions

For balances, payment limits, or inventory allocation, **never make critical decisions solely from a potentially stale replica**.

Better:

- Enforce business conditions inside the atomic write on the primary, such as `updateOne` with a sufficient-stock filter.
- Use transactions if invariants span multiple documents.
- Choose write concerns and required reads according to correctness requirements.
- Never treat a balance displayed from a secondary as the authoritative source allowing a debit.

Example preventing over-deduction within a single document:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-238",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2
    }
  }
);
```

The `available >= 2` condition is checked inside the same atomic write. Even if the client previously read stale stock, MongoDB still validates current stock during the update rather than trusting a snapshot taken from a secondary.

### 13.3. Feeds, leaderboards, reports: staleness tolerable

A KPI dashboard refreshing every minute or an aggregated feed can tolerate data delayed by a few seconds:

- Can read from secondaries to offload traffic.
- Configure read preference and max staleness appropriately.
- Display "updated at ..." so users understand freshness.
- Do not use such analytical data as the sole condition for financial operations or inventory control.

Define a **freshness SLO** with real measurements, rather than merely writing "eventually consistent."

### 13.4. Auditing: latest is not necessarily the only goal

An audit report typically cares more about committed data and consistent snapshots than immediately seeing every unacknowledged write. This may require:

- `readConcern: "majority"` or appropriate snapshot semantics;
- defining a report cutoff timestamp;
- materialized views or clearly sourced reporting copies;
- retaining history outside the oplog for long-term auditing.

Simply reading "latest on primary" does not automatically provide a stable snapshot across multiple queries spanning multiple collections.

### 13.5. Selection matrix

| Workload | Tolerates stale reads? | Initial approach |
| --- | --- | --- |
| User just edited profile and reloads | Undesirable | Primary read or causally consistent session |
| Checking condition to deduct inventory | No | Condition inside atomic write/transaction |
| Hourly reporting page | Yes, if clearly bounded | Secondary + freshness monitoring |
| Near real-time leaderboard | Possibly | Secondary + cache + display last updated timestamp |
| Viewing order immediately after creation | Usually no | Read primary, or causal majority session |
| Multi-collection report at a cutoff point | Needs snapshot more than real-time | Snapshot/read concern and reporting architecture |
| Reading rarely changing public info | Usually yes | Secondary, cache, reasonable TTL |
| Checking access permissions before sensitive writes | Do not trust stale copies | Verify auth/permissions and conditions at write time |

These are architectural guidelines, not substitutes for testing and version-specific MongoDB documentation.

## 14. How does a multi-region application make trade-offs?

### 14.1. Network distance and replication

Placing secondaries near users on another continent lowers read network latency. However:

- cross-region network latency increases the time for secondaries to receive changes;
- traffic load and network jitter cause lag to fluctuate;
- a single region can experience isolated outages;
- `nearest` reads may return older data than the primary in another region.

Example:

```text
Primary in region A
    |
    +-- Secondary in A: low RTT, lag ~0-1 seconds
    |
    +-- Secondary in B: cross-region RTT, lag ~2-5 seconds

Users in B:
    local reads are faster, but may be stale.
```

Numbers are illustrative only. Do not use network latency as an accurate measure of replication lag; monitor oplog/optime metrics and application behavior.

### 14.2. Read routing strategy by criticality

One approach:

```text
GET /public-catalog        -> secondaryPreferred
GET /dashboard             -> secondary
GET /profile/after-update  -> primary
POST /checkout             -> primary/atomic operation
GET /order/just-created    -> primary or causal session
```

Not every route must share the same read preference; where drivers/frameworks permit, configure per collection or per operation using simple, auditable rules.

### 14.3. Fallback can alter freshness

`secondaryPreferred` can fall back to the primary when no eligible secondary is available. Consequently, an API may switch between sources with differing freshness as topology changes. "Still able to read" does not prove data meets a freshness contract.

If a critical API must not use a lagging secondary, define an explicit policy to **return an error/bounded wait** if no qualifying source exists rather than silently serving stale data.

## 15. Observability and alerting for stale reads

### 15.1. Tracking replication lag per member

Metrics to collect:

| Metric | Purpose |
| --- | --- |
| Applied optime lag per secondary | Progress gap in applying changes |
| Durable optime and majority commit point | Distinguish applied from commit/durability milestones |
| Oplog window on sync source | Remaining history for members to catch up |
| Oplog generation rate vs. apply rate | Determine whether backlog is growing or shrinking |
| Network RTT/bandwidth/packet loss | Investigate network bottlenecks |
| Disk IOPS, latency, CPU, cache pressure | Investigate slow secondary apply rates |
| Elections/rollbacks/sync source changes | Correlate topology events |
| Server selection errors | Detect when no node satisfies read preference |
| Causal read wait time/timeouts | Detect latency spikes from waiting for progress |
| Application-layer cache/response age | Separate MongoDB lag from cache staleness |

Do not check only the replica set's average lag: a single secondary can lag by minutes while other members are healthy.

### 15.2. Alerting according to application requirements

An application has:

- A profile API requiring strict read-after-write.
- A dashboard tolerating data up to ~1 minute stale per internal SLO.
- A 2-hour delayed secondary intended for point-in-time recovery.

These three data paths require **three distinct alerting policies**. Applying a blanket "lag over 60s is an incident" alert to all members triggers false alarms on the delayed secondary while missing read-after-write issues on sensitive APIs when lag is only a few seconds.

### 15.3. Headroom relative to the oplog window

An estimate:

\[
\text{Headroom} \approx \text{Oplog window}-\text{Lag}
\]

If the window is 6 hours and lag is already 5 hours, the secondary may soon run out of history to catch up. Do not wait until lag exceeds the window to alert; the window can shrink rapidly when the primary generates heavy oplog volume.

Time-based headroom is a **coarse indicator**, while actual catch-up feasibility depends on exact oplog positions and valid sync sources.

### 15.4. Logging the right details for debugging

For consistency-related requests, where policies permit, log:

- correlation ID and API name;
- write timestamp and outcome;
- effective write concern/read concern/read preference;
- server selected for the read (via tracing/driver command monitoring);
- session/causal context at a safe metadata level, without logging credentials;
- returned document version or business revision;
- cache hit/miss indicators and cache age;
- execution duration and timeout errors.

Do not log full URIs containing passwords, access tokens, or personal data just to prove a request read from a secondary.

## 16. Investigation workflow: "I just saved, yet I still see stale data"

### 16.1. Step 1: verify the write command

Ask:

1. Did the API receive an acknowledgment or a write concern error?
2. What did `matchedCount`/`modifiedCount`/`upsertedId` report?
3. Did the write filter match the right ID, tenant, and status?
4. Could another worker have overwritten it with an older snapshot afterward?
5. Did duplicate requests or retries cause unexpected effects?

Do not blame replication hastily if the update never matched the document or was overwritten by another request.

### 16.2. Step 2: verify the read source

Check:

- Read preference on URI/client/database/collection/operation.
- Active read concern.
- Whether the read ran inside a causal session in the proper sequence.
- Which secondary was chosen, and whether tags/max staleness applied.
- Whether the response passed through Redis/CDN/browser caches.

If reading from a secondary, compare that node's progress against the primary over the same time window.

### 16.3. Step 3: inspect data on primary and secondaries

In authorized environments, check the same business key and projection across sources with appropriate read permissions. If the primary holds version 9 while the secondary holds version 8, that is direct evidence of an **observed progress difference** at check time.

If both primary and secondary hold version 9 yet the API still returns version 8, re-examine caches, API response mapping, selected database/tenant, or which node the request actually hit.

Never run test writes on production or alter election settings just to investigate.

### 16.4. Step 4: classify the root cause

| Symptom | Initial suspicion | Appropriate action |
| --- | --- | --- |
| Write matched nothing | Wrong version/state/ID | Inspect query and handle conflict |
| Write succeeded, primary updated, secondary stale | Replication lag | Adjust read routing/causal consistency, monitor lag |
| All nodes updated, API returns old data | Cache or application layer | Check TTL, invalidation, response caching |
| Value vanished after failover | Non-majority-committed write rolled back or other logic | Review write concern, election logs, reconcile |
| Causal read waits then times out | Secondary lacks progress or unavailable | Inspect server selection, lag, timeout, primary read option |
| Secondary lag climbs continuously | Apply capacity cannot keep up | Check network/disk/CPU/workload |
| Data "moves backward" across GETs | Reading secondaries at different progress or caches | Use causal sessions/select source per contract |

### 16.5. Step 5: fix the root cause, not just the symptom

If an API requires read-your-writes, fix routing or sessions rather than adding `sleep(1000)` and hoping secondaries always catch up. Fixed sleeps:

- add wasted latency when the replica set is healthy;
- can **still be insufficient** when lag spikes;
- increase latency without providing a clear consistency guarantee.

If you must wait for data to reach a specific milestone, use MongoDB's causal/consistency mechanisms or conditional version checks with timeouts and proper policies, rather than relying on "sleeping one second."

## 17. Common mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Writing then reading any secondary expecting fresh data | Sees stale value | Read primary or use causal session when needed |
| Treating `w:"majority"` as all secondaries updated | Misses changes on lagging secondaries | Understand majority is not all |
| Treating `readConcern:"majority"` as always latest | Confuses committed data with freshest data | Coordinate read preference/causal sessions |
| Picking `nearest` wanting "closest in time" data | Network-close node may still lag | Understand `nearest` optimizes network latency |
| Setting `maxStalenessSeconds` as a hard TTL | Can read data staler than intuitive threshold | Understand it is a server selection estimate |
| Adding fixed `sleep` after every write | Higher latency, no guarantee | Use explicit consistency mechanisms |
| Checking `rs.status()` once and declaring healthy | Misses fluctuating lag and elections | Monitor time-series metrics |
| Treating `lag=0` as all operations durable/majority | Confuses different indicators | Distinguish applied/durable/commit optimes |
| Using app timestamps alone to measure replication | Clock skew, caching, varying latencies | Use replication metrics and tracing |
| Re-inserting with a new `_id` after write timeout | Can create business duplicates | Stable IDs, idempotency/reconciliation |
| Using secondary reads to decide inventory deductions | Can act on stale stock counts | Enforce conditions inside atomic writes |
| Blaming MongoDB lag for stale caches | Misdiagnosis, futile DB tuning | Identify cache layers and read nodes |
| Assuming sessions automatically span HTTP requests | Loses causal guarantees between requests | Propagate context or route reads properly |
| Using one session for concurrent parallel ops | Fails to establish intended causal order | Execute sequentially |
| Treating snapshot as equivalent to latest | Consistent report yet behind current time | Choose the right consistency level |
| Using `w:1` for data that must never roll back under any circumstance | Risk of losing changes after failover | Evaluate majority and durability design |
| Lowering write concern to "fix lag" without business review | Weakens write guarantees without fixing bottleneck | Address replication/capacity root causes |
| Ignoring oplog window while lag grows | Secondary may lose catch-up history | Monitor window/headroom and workload |

## 18. Reasoning practice exercises

### Exercise A. Majority write succeeded yet read is stale

A replica set has primary P and secondaries A and B. A write X is acknowledged by P and A; B lags by 90 seconds.

1. In a standard voting config with three data-bearing members, can `w:"majority"` be satisfied?
2. If `GET` routes to B with `readConcern:"local"`, is it guaranteed to see X?
3. If switched to `readConcern:"majority"` on B, is it guaranteed to see X immediately?
4. How can an API ensure read-your-writes right after writing?

**Hint:** majority does not mean every member; B can still lag despite majority acknowledgment. `readConcern:"majority"` does not force B to catch up to write X; consider reading from primary or using a causal majority session where appropriate.

### Exercise B. Read preference `nearest`

Application in region B:

```text
Primary A:         RTT 70 ms, reference lag 0
Secondary B:       RTT  4 ms, lag 8 seconds
```

1. Why might `nearest` select B?
2. Which screens could tolerate that result?
3. Which screens should not rely on it?
4. If a user just updated their profile, should routing change or what causal mechanism should be used?

### Exercise C. Reading data backward

A client reads a profile the first time from secondary A and sees `version: 12`, then a second time from B and sees `version: 10`.

1. Which expectation does this violate?
2. Did data on the primary automatically roll back?
3. Why can causal context and majority reads help?
4. If the two GETs hit different HTTP servers, what factor requires attention?

### Exercise D. Limits of `maxStalenessSeconds`

An application sets:

```text
readPreference=secondary
maxStalenessSeconds=120
```

1. Is this a hard age limit for **each document** or a secondary selection criterion?
2. If all secondaries are estimated as too stale, what will the request do?
3. Should this setting replace a "read after write X" condition?
4. Why can you not configure an arbitrarily small threshold like 1 second?

### Exercise E. Inventory operations

Two requests concurrently read `available: 3` from a secondary. Each wants to deduct 2.

1. If both compute `newAvailable=1` and `$set` by `_id`, can a lost update happen?
2. How does `updateOne({available:{$gte:2}},{$inc:{available:-2}})` help?
3. If a request retries after timeout, does the stock condition replace an operation ID for preventing double deductions?
4. When invariants span multiple documents, what mechanism is needed?

### Exercise F. Post-failover triage

Users notice a newly created order vanished after the replica set elected a new primary.

Distinguish among:

- stale read from a secondary;
- non-majority-committed write rolled back;
- write request that timed out;
- cache holding an old result;
- selecting the wrong tenant/namespace.

Propose metrics/logs to gather before concluding.

## 19. Official references

When applying to production systems, consult documentation **matching your MongoDB and Node.js driver versions**:

- [Replica Set Data Synchronization](https://www.mongodb.com/docs/manual/core/replica-set-sync/) — how secondaries replicate data.
- [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — oplog history and retention windows.
- [Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — primary/secondary selection and modes.
- [Read Preference maxStalenessSeconds](https://www.mongodb.com/docs/manual/reference/read-preference/#maxstalenessseconds) — secondary selection based on estimated staleness.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — read consistency levels.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — write acknowledgment.
- [Causal Consistency and Read and Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/) — guarantees in causally consistent sessions.
- [Linearizable Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/) — limits and semantics of linearizable reads.
- [rs.status()](https://www.mongodb.com/docs/manual/reference/method/rs.status/) — inspecting replica set progress.
- [MongoDB Node.js Driver Sessions](https://www.mongodb.com/docs/drivers/node/current/fundamentals/transactions/#causal-consistency) — working with sessions and causal consistency in the driver.

## 20. Conclusion

**Replication lag** means secondaries may not yet contain the latest writes processed by the primary. Therefore, **stale reads** can occur even immediately after a write API reports success, particularly when using `secondary`, `secondaryPreferred`, or `nearest`. When reading across multiple secondaries, a user can even observe data "going backward" between consecutive reads.

To design properly, separate three layers: **write concern** sets write acknowledgment; **read preference** selects the read node; **read concern** governs readable data semantics. `w:"majority"` does not mean every secondary has caught up, and `readConcern:"majority"` does not automatically guarantee a secondary returns the latest data. When **read-your-writes** is required, read from the primary at an appropriate consistency level or use a **causally consistent session** with supported majority settings and sequential operation ordering.

Freshness must be defined by **business needs**: a dashboard may tolerate a few seconds of lag, whereas inventory checks, access permissions, or payment statuses must avoid decisions based on stale snapshots. Monitor lag, oplog windows, per-member progress, election events, and cache layers, and enforce conditions **at write time** for critical invariants. **Never handle stale reads with fixed sleep delays or by assuming "write succeeded" automatically means "every replica is updated."**
