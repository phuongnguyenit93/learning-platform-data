# Read concern: local, available, majority, linearizable, and snapshot in MongoDB

## 1. Why can a MongoDB read observe different data?

In an application using a MongoDB replica set, a document can exist in different states at the same point in time:

- The **primary** has received a new write.
- One **secondary** has received a copy of that write.
- Another secondary has not yet caught up.
- The new write may not yet have been acknowledged by a majority of replica set members.
- After a primary election incident, writes that were not majority-committed may be **rolled back**.

Example of an order:

~~~javascript
{
  _id: "ORD-100",
  tenantId: "SHOP-A",
  status: "PENDING",
  totalCents: NumberLong(350000)
}
~~~

The application updates it:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
);
~~~

Immediately after the operation, client A reading from the primary may see **PAID**, while client B reading from a lagging secondary may see **PENDING**. If the write has not reached majority commit and the primary changes in an eligible failure scenario, the **PAID** version that a client read at a weak level might no longer exist after rollback.

**Read concern** is the mechanism that governs **the consistency and isolation guarantees of data that a read operation is permitted to return**. It does not select which server to read from, nor does it decide when a write is acknowledged.

MongoDB has five core read concern levels:

1. **local**
2. **available**
3. **majority**
4. **linearizable**
5. **snapshot**

Choosing the right read concern means balancing **consistency**, **freshness**, **availability**, **latency**, and **operational cost** according to the actual requirements of each API.

### Lesson objectives

After this lesson, you should be able to:

- Explain what each read concern guarantees and what it does **not** guarantee.
- Distinguish read concern from **read preference** and **write concern**.
- Predict outcomes when primary, secondaries, and the majority commit point are out of sync.
- Use read concerns in `mongosh`, the MongoDB Java Sync Driver, and Spring Data MongoDB.
- Choose **majority**, **linearizable**, or **snapshot** for specific business requirements.
- Understand limitations of reading on sharded clusters, inside transactions, and in causal sessions.
- Design timeouts, retries, failover testing, and consistency monitoring.

## 2. Three easily confused settings: read preference, read concern, write concern

A MongoDB operation can be governed by all three independent choices:

| Setting | Question answered | Examples |
|---|---|---|
| **Read preference** | Read **from which node**? | primary, secondary, secondaryPreferred, nearest. |
| **Read concern** | What **consistency/isolation level** must the read data meet? | local, majority, snapshot. |
| **Write concern** | When is a write operation **acknowledged**? | w:1, w:"majority", journal. |

Example:

~~~text
Write:
  Client -- update --> Primary
                      |
                      +--> Secondary A
                      +--> Secondary B

Write concern:
  Wait for how many members to acknowledge?

Read preference:
  Read from primary or secondary?

Read concern:
  Which version of data is permitted to be returned?
~~~

If you set **readPreference: secondary**, the driver prefers reading from a secondary. If combined with **readConcern: majority**, the returned data must belong to the majority-committed portion that the secondary can already serve, **though it can still be stale** compared to the primary.

Using **writeConcern: majority** for writes **does not automatically change the read concern of subsequent queries**. Conversely, setting only readConcern majority does not force all other applications to write with w:majority.

**There is no single "strong consistency" toggle that automatically solves every aspect.**

## 3. Replica set diagram and majority commit point

Suppose a replica set has three data-bearing nodes:

~~~text
                  MongoDB Replica Set

                     PRIMARY (P)
                         |
               +---------+---------+
               |                   |
               v                   v
         SECONDARY (S1)       SECONDARY (S2)

        Majority = 2 of 3 members
~~~

Timeline illustrating a write **W1**:

| Time | P | S1 | S2 | State of W1 |
|---|---|---|---|---|
| t0 | Applied W1 | Not yet applied | Not yet applied | Not yet majority-committed. |
| t1 | Applied W1 | Applied W1 | Not yet applied | Present on two nodes; the primary can acknowledge majority once it tracks replication progress per the corresponding mechanism. |
| t2 | Knows W1 reached majority commit point | Applied W1 | Not yet applied | W1 data is eligible for the majority-committed portion. |
| t3 | Applied W1 | Applied W1 | Applied W1 | All nodes in the example have W1. |

This is an **illustrative model**, not a guarantee of replication latency or the ordering of commit notifications in MongoDB.

Key concepts:

- **Applied write:** the node has applied the change to its local data.
- **Majority-acknowledged write:** the write operation has been acknowledged under write concern **w:"majority"**.
- **Majority commit point:** the boundary at which the replica set identifies operations eligible as majority-committed.
- **Replication lag:** a secondary trailing behind the primary in applying/learning write progress.
- **Rollback:** operations not yet majority-committed may be removed from history when the replica set recovers after a failure.

Do not equate "secondary has applied W1" with "every read concern on the secondary can return W1 immediately." With **majority**, there is also the majority commit view boundary used by the node.

## 4. Quick comparison table of the five read concern levels

| Level | Primary guarantee | Can it be stale? | Can it read rolled-back data? | Limitations/notes |
|---|---|---|---|---|
| **local** | Reads data locally available on the selected node, without requiring majority commit. | Yes, especially on secondaries. | **Yes.** | Common default when no override is configured. |
| **available** | Prioritizes availability, reducing shard ownership/partition checks in sharded clusters. | Yes. | **Yes.** | Sharded collections may return **orphaned documents** or unexpected results due to routing during partitions; cannot be used in transactions/causal sessions. |
| **majority** | Only returns data that has been majority-committed by the replica set. | **Yes.** | Under majority commit guarantees, does not roll back under default durability settings. | Does not guarantee reading the latest record in real time. |
| **linearizable** | Reflects majority-acknowledged writes completed before the read began; real-time ordering when properly combined with write concern majority. | No for completed writes covered by that guarantee; reads may still wait or time out. | Aims to be stronger than majority regarding recency/real-time order. | **Primary only, query must uniquely identify a single document**, not allowed in transactions/causal sessions; requires maxTimeMS. |
| **snapshot** | A view of data **at a consistent point in time**, potentially across shards. | Yes, because the snapshot may be in the past. | Outside transactions uses majority-committed snapshots; inside transactions guarantees relate to majority commit. | Supported in transactions or outside transactions starting in MongoDB 5.0; limited by snapshot history. |

This is not a ranking where "the next level is always better than the previous." **linearizable** and **snapshot** solve **two different questions**:

- **linearizable:** "If a majority write completed before this read began, will this single-document read observe the corresponding state?"
- **snapshot:** "Does the data I am reading belong to the same consistent point in time, even across shards?"

A historical snapshot can be perfectly consistent at time T while being **older than current data**. Conversely, a single-document linearizable read does not automatically turn a multi-collection report into a consistent snapshot.

## 5. Read concern "local"

### 5.1. Meaning

**local** returns data from the selected node **without requiring that it has been acknowledged by a majority of replica set members**.

This is the common default read concern for reads on primaries and secondaries unless the deployment configures another default.

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
).readConcern("local");
~~~

Equivalent example using a database command:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "ORD-100" },
  readConcern: { level: "local" }
});
~~~

### 5.2. local on the primary

If the primary has applied W1 but it is not yet majority-committed, a local read from the primary **can see W1**.

~~~text
P: W0 -> W1 applied
S1: W0
S2: W0

readPreference primary
readConcern local
       |
       v
May return W1
~~~

Because W1 is not yet majority-committed, if a failover occurs under eligible conditions, W1 **may roll back**.

### 5.3. local on a secondary

If read preference is secondary, local reads that secondary's local copy of the data. If replication lags, the read can be **stale**:

~~~text
P: W1
S1: W1
S2: W0  <-- lagging secondary

Read local at S2 -> may see W0
~~~

**local does not mean reading the cluster's latest data.** It means reading the state of the serving node without requiring a majority commit.

### 5.4. When to use local?

Suitable when:

- The application tolerates potentially reading non-majority-committed data.
- Reports/displays can handle staleness or rollbacks.
- The goal is reducing consistency overhead for routine queries.
- Critical invariants are already enforced on the write path.

You should not rely solely on a local read to make a business decision requiring majority-durable data or real-time ordering, such as "confirming whether resource permissions have been granted on the current primary."

### 5.5. local in transactions

Transactions support read concern local, though the context differs from a standalone read. On a replica set, a local transaction can observe a view fixed when the transaction starts. On a sharded cluster, **local does not guarantee all shards use the same snapshot**; if cross-shard snapshot isolation is needed, choose **snapshot**.

## 6. Read concern "available"

### 6.1. Similarities with local

**available** also reads the instance's data **without requiring majority commit**. Returned documents **can be rolled back**.

For **unsharded collections** in standalone or replica set deployments, available and local behave equivalently per MongoDB documentation.

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
).readConcern("available");
~~~

Do not interpret available as **guaranteeing fresher data than local** or **never waiting on any operation**. The key distinction appears in **sharded clusters**.

### 6.2. Available prioritizes availability in sharded clusters

In a sharded cluster, data is partitioned into chunks across multiple shards. During chunk migration, a data range may be moving between shards and require checking which shard is the **authoritative owner**.

With read concern available, during a network partition, queries can be routed to a shard deemed appropriate based on pre-partition metadata, **without waiting for consistency checks with unreachable servers**.

~~~text
             mongos
               |
               v
     Metadata/shard routing
            /     \
           v       v
        Shard A   Shard B

Chunk migrating A -> B
Network partition occurs

ReadConcern available:
  Does not wait to verify corresponding ownership
  -> may read from a shard that is no longer the valid owner
  -> may return orphaned documents
~~~

An **orphaned document** is a data record physically residing on a shard that no longer logically belongs to a chunk owned by that shard, typically appearing in connection with migration/cleanup processes.

Results may violate application expectations: **orphaned documents**, data from the wrong owner, or broken expectations around uniqueness/completeness in sharded queries.

### 6.3. When to consider available?

Some queries accept weak consistency to prioritize responsiveness when a sharded cluster is partitioned, such as monitoring/aggregation queries where temporary inaccuracies are tolerable.

Do not use available for:

- Inventory counts requiring no duplicates or omissions.
- Billing logic, payments, and access control checks.
- Reports requiring accurate ownership of sharded data.
- Workloads that cannot tolerate orphaned records.

Unless there is a specific requirement, **local** is generally a lower-risk option when weak-consistency reads are needed on a sharded collection.

### 6.4. Usage restrictions

Per documentation, read concern available **cannot be used in causally consistent sessions or multi-document transactions**.

It is not a technique to fix replication lag or guarantee read-your-writes.

## 7. Read concern "majority"

### 7.1. Meaning

**majority** only returns data from the set **acknowledged/majority-committed by a majority of replica set members**. When reading outside a multi-document transaction, returned documents have durability guarantees and **will not be rolled back under normal replica set mechanisms**.

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
).readConcern("majority");
~~~

Or:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "ORD-100" },
  readConcern: { level: "majority" }
});
~~~

### 7.2. Case where local sees W1 while majority does not yet see it

~~~text
Time t0:

P:  W1 applied
S1: W0
S2: W0

readConcern local at P
  -> may see W1

readConcern majority at P
  -> only sees the majority-committed view,
     may still see W0
~~~

After W1 reaches the majority commit point, nodes update their majority view via the replication mechanism. A majority read on a secondary that has not yet updated its majority view for W1 **can still return W0**.

### 7.3. majority does not mean always freshest

This is a common misconception:

> "Using read concern majority means any node returns the primary's latest state."

**Incorrect.** majority focuses on returning only **majority-committed data**; it does not guarantee that a read reflects all previously completed majority writes in real-time order in all situations.

For example, a lagging secondary can return an older majority-committed snapshot while another majority write has already been acknowledged by the primary.

If the requirement is **reading the latest version with real-time ordering** for a uniquely identified document, consider **linearizable**. If the requirement is reading along the causal chain of the same user, consider a **causally consistent session** with appropriate read/write concerns.

### 7.4. Majority read and majority write

Two independent settings:

~~~javascript
// Write with majority write concern.
db.runCommand({
  update: "orders",
  updates: [
    {
      q: { _id: "ORD-100" },
      u: { $set: { status: "PAID" } }
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 10000
  }
});

// Majority read.
db.orders.find(
  { _id: "ORD-100" }
).readConcern("majority");
~~~

**writeConcern majority** controls when a write is acknowledged. **readConcern majority** controls what data can be read. Combining them properly is important, but **does not automatically create a causal session** across independent requests.

### 7.5. majority in transactions

In a multi-document transaction, **read concern majority only provides its corresponding majority guarantees when the transaction commits with write concern majority**.

Do not assume a transaction with readConcern majority that commits with w:1 will carry the same guarantees as a majority-committed transaction.

If you need a consistent snapshot across multiple documents/shards inside a transaction, use readConcern **snapshot** and commit with writeConcern **majority** per application requirements.

### 7.6. Note on durability and unusual configurations

MongoDB with appropriate default journaling settings provides majority durability guarantees. Certain special configurations such as **writeConcernMajorityJournalDefault:false** or simultaneous crashes/restarts of a majority of nodes carry specific caveats.

Do not state "majority can absolutely never lose data under any hardware failure/setting." You must verify journaling, topology, write concern, and deployment configuration.

### 7.7. When to use majority?

Examples:

- Users viewing transaction statuses that are majority-confirmed without needing real-time linearizability on every read.
- APIs that must avoid exposing writes prone to rollback.
- Systems with sessions requiring causal consistency when combining majority reads/writes.
- Reports requiring majority-committed data while tolerating reasonable staleness.

**majority does not replace business validation, transactions, OCC, or unique indexes.**

## 8. Read concern "linearizable"

### 8.1. Primary guarantee

**linearizable** aims to guarantee that a read operation reflects **all majority-acknowledged writes that completed before the read began**.

When combined with **write concern majority**, the application can treat read/write operations on **a single document** as executing in an order consistent with **real-time order**.

~~~text
Write W1 with w:majority acknowledged
                   |
                   v
             Read R1 begins
               linearizable
                   |
                   v
R1 must observe a valid state after W1
within the single-document guarantee scope
~~~

Unlike majority, MongoDB must also confirm that the serving primary node is capable of executing valid majority writes. This matters when an old primary has not yet realized it lost its primary role during a network partition.

### 8.2. Reads only from the primary

~~~javascript
db.orders.find(
  { _id: "ORD-100" }
)
.readConcern("linearizable")
.maxTimeMS(5000);
~~~

More explicitly via command:

~~~javascript
db.runCommand({
  find: "orders",
  filter: { _id: "ORD-100" },
  readConcern: { level: "linearizable" },
  maxTimeMS: 5000
});
~~~

The driver must route the operation **to the primary**. Do not combine linearizable with **readPreference: secondary**.

### 8.3. Only guaranteed for queries uniquely identifying a single document

MongoDB's linearizable guarantee **only applies** when the query filter uniquely identifies a single document. Additional conditions on the search key must also be satisfied to achieve a consistent snapshot:

- Use an **immutable field** as the search key, typically **_id**.
- Or the search key is not concurrently updated.
- Or the query uses an appropriate **unique index** on the search key.

Valid example:

~~~javascript
db.feature_flags.find(
  { _id: "checkout.enabled" }
)
.readConcern("linearizable")
.maxTimeMS(5000);
~~~

Do not assume a **find({status:"ACTIVE"})** returning thousands of documents carries the same linearizable guarantee across the entire set or across collections.

### 8.4. Why is maxTimeMS needed?

When a majority of data-bearing members are unavailable, a linearizable operation may wait indefinitely to satisfy conditions. MongoDB recommends **always setting maxTimeMS** so the operation can return a timeout error instead of blocking without bound.

If the read times out:

- Do not treat the outcome as "document does not exist" or "flag = false."
- Classify it as **unable to verify consistency within timeout**, not a business data value.
- Choose a fallback aligned with the feature's risk; sensitive operations may need to fail closed.

### 8.5. Example needing linearizable

A job coordination system has a document:

~~~javascript
{
  _id: "leader-controller",
  ownerId: "worker-A",
  epoch: NumberLong(18)
}
~~~

If multiple parties need to **read the previously majority-written leader state in real time**, linearizable can be suitable for reading that exact single document.

However, linearizable reads alone cannot build a safe lease/leader election protocol. To change ownership, you must use **conditional writes**, fencing tokens/epochs, write concern, and appropriate timeout/network partition handling.

### 8.6. Usage restrictions

- Reads only from **primary**.
- Cannot be used in **causally consistent sessions** or **multi-document transactions**.
- For aggregations with read concern linearizable, cannot use **$out** or **$merge**.
- The guarantee applies to **a single uniquely identified document**, not a snapshot of an entire report.
- Can be noticeably slower than **local/majority** due to additional verification.

### 8.7. Avoid overuse

Do not use linearizable for every product listing, log view, or dashboard table. Reserve it for reads that truly require real-time ordering with majority writes and can tolerate added latency/reduced availability.

## 9. Read concern "snapshot"

### 9.1. Goal: reading at a consistent point in time

**snapshot** provides majority-committed data at **a consistent logical point in time**; this can be a view across shards.

Suppose a system has two documents:

~~~javascript
{
  _id: "ACCOUNT-A",
  balance: NumberLong(1000)
}

{
  _id: "ACCOUNT-B",
  balance: NumberLong(500)
}
~~~

A transfer moves 200 from A to B. If a report reads A first and B later at inconsistent times, the report can observe values from different points in time.

**Snapshot reads** aim to ensure that data read within the snapshot scope reflects a single **view at time T**, rather than one document before a change and another after a change without a consistent boundary.

**Important:** a snapshot read does not by itself make a multi-document funds transfer atomic. The transfer still requires a transaction or appropriate data model if the business requires atomicity across documents.

### 9.2. Snapshot inside a transaction

Inside a multi-document transaction, you can configure:

~~~javascript
const session = db.getMongo().startSession();
const database = session.getDatabase("mongo_consistency_lab");

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" },
    readPreference: { mode: "primary" }
  });

  const accountA = database.accounts.findOne(
    { _id: "ACCOUNT-A" }
  );
  const accountB = database.accounts.findOne(
    { _id: "ACCOUNT-B" }
  );

  printjson({ accountA, accountB });

  session.commitTransaction();
} catch (error) {
  session.abortTransaction();
  throw error;
} finally {
  session.endSession();
}
~~~

This example illustrates a MongoDB transaction in **mongosh** on a supported topology. In real applications, handle transaction retries according to error labels, unknown commit results, and timeouts; never simply re-invoke external side effects outside the database.

**Read concern in a transaction is set at the transaction level**, not individually per find/aggregate inside it. Database/collection-level read concern options can be overridden by the transaction-level concern.

### 9.3. Snapshot outside transactions (MongoDB 5.0+)

Starting in **MongoDB 5.0**, snapshot read concern can also be used for certain read operations **outside multi-document transactions**, including:

- **find**
- **aggregate**
- **distinct** on **unsharded collections**

Example:

~~~javascript
db.runCommand({
  find: "orders",
  filter: {
    tenantId: "SHOP-A"
  },
  readConcern: {
    level: "snapshot"
  },
  maxTimeMS: 10000
});
~~~

With snapshot reads outside transactions, returned data belongs to a **majority-committed snapshot**. Commands outside the supported set cannot arbitrarily use snapshot concern.

**Running one snapshot query outside a transaction does not mean all subsequent queries automatically share the same snapshot T.** If multiple operations must share one point in time, use a transaction or explicitly use supported snapshot timestamp mechanisms.

### 9.4. atClusterTime: selecting a snapshot by timestamp

Outside transactions, MongoDB allows specifying **atClusterTime** to read a snapshot at a specific logical timestamp.

~~~javascript
db.runCommand({
  find: "orders",
  filter: { tenantId: "SHOP-A" },
  readConcern: {
    level: "snapshot",
    atClusterTime: Timestamp(1613577600, 1)
  },
  maxTimeMS: 10000
});
~~~

**`Timestamp(1613577600, 1)` only illustrates syntax**, and is not a valid timestamp for your current lab data. In real systems, obtain the appropriate timestamp from `operationTime`/`clusterTime` or responses/sessions per documentation; never fabricate timestamps.

If the server has not yet reached the requested timestamp, it may **wait**; if the snapshot is too old and no longer in the snapshot history, MongoDB may **return an error**.

### 9.5. Snapshot history is finite

MongoDB retains finite history, governed by **minSnapshotHistoryWindowInSeconds** and storage engine state. A snapshot read running too long or an `atClusterTime` that is too old can be rejected/terminated.

Do not use snapshot reads as a mechanism to retain historical data indefinitely. If you need reproducible reports months later, maintain **snapshots/archives/versioned data** at an appropriate architectural layer.

### 9.6. Snapshot and recency

A snapshot at time T provides consistency at T, but **may be older than the state when the request finishes**. Therefore:

~~~text
Snapshot consistency != real-time linearizability
~~~

A snapshot may be completely accurate for data at T yet not include a majority write acknowledged right after T.

### 9.7. Capped collections and versions

Current documentation notes that starting in **MongoDB 8.0**, read concern snapshot can be used with capped collections. Older versions have restrictions. When designing pipelines relying on snapshots over capped collections, verify against the **actual server version**, rather than inferring from newer version guides.

## 10. Same timeline, five levels can return different results

Suppose a three-member replica set has an order:

~~~javascript
{
  _id: "ORD-100",
  status: "PENDING"
}
~~~

Write **W1** updates status to PAID:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-100" },
  { $set: { status: "PAID" } }
);
~~~

Timeline:

~~~text
T0:
  P = PENDING
  S1 = PENDING
  S2 = PENDING

T1: Primary applies W1
  P = PAID
  S1 = PENDING
  S2 = PENDING
  W1 not yet majority-committed

T2: S1 applies W1, primary learns W1 reached majority
  P = PAID
  S1 = PAID
  S2 = PENDING
  majority commit point has advanced to W1

T3: S2 syncs and recognizes majority commit
  P = PAID
  S1 = PAID
  S2 = PAID
~~~

At **T1**:

- **local on P:** can return **PAID**, even though W1 is not yet majority-committed.
- **local on S2:** can return **PENDING**.
- **available on unsharded collection:** similar to local on the selected node.
- **majority:** returns only majority-committed state; on this timeline, this may be **PENDING**.
- **linearizable:** cannot treat W1 as a completed majority write if it has not yet been majority-acknowledged; the read may wait for appropriate conditions. Linearizable's real-time guarantee does not mean it must expose every newly applied but incomplete W1.
- **snapshot:** reads the state of a selected majority-committed snapshot, which may be **PENDING**.

At **T2**:

- **local on P/S1:** PAID.
- **local on S2:** PENDING due to lag.
- **majority on P:** can return PAID once the majority view has advanced to W1.
- **majority on S2:** can return PENDING if it has not yet applied W1 or does not yet have the updated majority view.
- **linearizable on P:** when W1 is a majority-acknowledged write completed before the read began, a single-document read must reflect W1 or a newer valid state.
- **snapshot:** depends on the chosen snapshot timestamp; may be consistent at a point before W1 and return PENDING.

**Do not assume all nodes at T2 return the same value.** Replication is asynchronous and different read concerns serve different goals.

## 11. Read concern and read preference: two independent axes of choice

Read preference commonly has these modes:

- **primary** — read from primary; the common default mode.
- **primaryPreferred** — prefer primary, may fall back to secondary under eligible conditions.
- **secondary** — read only from secondaries.
- **secondaryPreferred** — prefer secondary, may fall back to primary.
- **nearest** — driver selects an eligible node based on latency window and other criteria.

### 11.1. Illustrative combinations

| Read preference | Read concern | Notable properties |
|---|---|---|
| primary | local | May observe newly applied writes not yet majority-committed. |
| secondary | local | May be stale due to replication lag and may observe rolled-back data. |
| primary | majority | Only majority-committed view; does not guarantee linearizable. |
| secondary | majority | Majority-committed data, though potentially behind the primary. |
| primary | linearizable | Suitable when real-time ordering is needed for single-document queries. |
| secondary | linearizable | **Unsupported** because linearizable is primary-only. |
| primary or eligible secondary | snapshot outside transaction | Majority-committed snapshot at the chosen timestamp. |

Once `readPreference: secondary` is set, you cannot use `readConcern: majority` to **force reads to the primary**; read concern does not control node selection.

### 11.2. Explanatory JavaScript example

~~~javascript
// Each command illustrates read level without changing read preference.
db.orders.find({ _id: "ORD-100" }).readConcern("local");
db.orders.find({ _id: "ORD-100" }).readConcern("majority");
~~~

If you need to control read preference for an application, configure driver/connection options or collection/database handles via the corresponding API. Do not expect **`readConcern("majority")`** to automatically switch a `secondaryPreferred` connection to `primary`.

### 11.3. Reading from secondaries and freshness requirements

If an application needs "data no older than 5 seconds," setting **readConcern majority** alone is insufficient: a secondary can still lag by more than 5 seconds.

MongoDB provides **maxStalenessSeconds** in read preference to assist secondary selection, but it is a **node-estimation/filtering mechanism** under specific conditions, not an SLA proving every document is fresher than 5 seconds. Minimum supported values and limits depend on driver/server.

For strict freshness requirements, design explicit consistency controls, such as primary reads, causal consistency, or linearizable within appropriate scope.

## 12. Read concern and write concern: aligning semantics properly

### 12.1. Write concern w:1

A write with **w:1** is acknowledged once the primary satisfies its acknowledgment condition; it does not require a majority of members to have replicated it yet.

~~~javascript
db.runCommand({
  update: "orders",
  updates: [
    {
      q: { _id: "ORD-100" },
      u: { $set: { status: "PAID" } }
    }
  ],
  writeConcern: { w: 1 }
});
~~~

If a write was just applied by the primary and has not yet reached majority commit, a local read may see it while a majority read may still see the old state. During an eligible failover, that write can roll back.

### 12.2. Write concern majority

~~~javascript
db.runCommand({
  update: "orders",
  updates: [
    {
      q: { _id: "ORD-100" },
      u: { $set: { status: "PAID" } }
    }
  ],
  writeConcern: {
    w: "majority",
    wtimeout: 10000
  }
});
~~~

The server must satisfy majority acknowledgment or return a timeout/unacknowledged status within the deadline. **wtimeout** does not imply the write was rolled back or definitely unapplied; the write state may have changed even if the write concern was not satisfied in time.

### 12.3. Combination table

| Read concern | Write concern | What can be concluded |
|---|---|---|
| local | w:1 | May see writes early, with risk of rollback and secondary lag. |
| local | majority | Writes are majority-acknowledged, though independent local reads still reflect node-local state. |
| majority | w:1 | Reads show only majority-committed data, so a recent w:1 write may not be visible yet. |
| majority | majority | Key foundation for durability and causal consistency when sessions are used properly. |
| linearizable | majority | Guarantees real-time ordering on a single document when conditions are met. |
| snapshot in transaction | majority on commit | Consistent snapshot isolation per transaction semantics, including across shards where supported. |

Do not describe any combination as "every read is always the freshest" without session/read routing, query constraints, and topology considerations.

## 13. Causal consistency: read-your-writes is more than readConcern majority

### 13.1. Four causal properties

MongoDB supports **causally consistent sessions** to preserve ordering for causally related operations.

The commonly described guarantees:

1. **Read your writes:** reads see results of preceding writes in the session.
2. **Monotonic reads:** subsequent reads do not revert to an older state than earlier reads in the corresponding sequence.
3. **Monotonic writes:** the order of writes within the session is respected.
4. **Writes follow reads:** writes dependent on prior reads preserve the corresponding causal relationship.

To guarantee full causal consistency properties alongside durability per MongoDB guidance, use **read concern majority** and **write concern majority** within an appropriate session.

### 13.2. Order confirmation flow example

~~~text
Client opens session S
     |
     v
Write order.status = PAID with w:majority
     |
     v
Read order in the same session S with majority
     |
     v
Read must respect causal relationship with the prior write
~~~

The driver can attach **afterClusterTime** to the read concern of operations inside a causal session, allowing secondaries to wait until replication progress reaches the required timestamp.

### 13.3. Do not arbitrarily set afterClusterTime manually

With causally consistent sessions, MongoDB drivers automatically manage **operationTime/clusterTime** and attach the appropriate `afterClusterTime` to read commands. Do not manually inject fabricated timestamps into `afterClusterTime` or combine it with **atClusterTime** on the same snapshot read.

### 13.4. Causal sessions do not automatically span across arbitrary HTTP requests

If request A uses session S1 and request B opens an independent session S2, you cannot rely solely on having the same user ID to conclude B will automatically inherit A's causal context.

To propagate causal context across clients/sessions, use mechanisms to advance operation time/cluster time per API and appropriate security models. Do not cache a single `ClientSession` to share concurrently across threads or users.

### 13.5. Do not mix linearizable with causal sessions

Per MongoDB documentation, read concern **linearizable cannot be used in causally consistent sessions**. If you need both "read-your-writes across replica set members" and "single-document real-time ordering," analyze the requirements and select the appropriate pattern; do not simply enable both simultaneously.

## 14. Read concern in multi-document transactions

### 14.1. Only supported levels

Multi-document transactions support:

- **local**
- **majority**
- **snapshot**

**available** and **linearizable** are not valid read concerns for a transaction.

Read concern in a transaction is set **at the transaction level**. Do not set separate read concerns on individual operations inside a transaction expecting them to use different levels.

### 14.2. local in transactions

On a replica set, a transaction reading with local can observe a snapshot from when the transaction began; however, on a sharded cluster, **local does not guarantee the same snapshot across shards**.

Therefore, a local transaction is not the default choice for cross-shard financial reporting requiring a consistent point in time.

### 14.3. majority in transactions

When a transaction commits with write concern **majority**, readConcern majority provides its corresponding guarantees on majority-committed data. If committing with a weak write concern, do not assume all majority read guarantees of the transaction remain intact.

### 14.4. snapshot in transactions

When a transaction commits with write concern majority, read concern snapshot provides a majority-committed view at a consistent point in time, including across shards where supported.

~~~text
Begin Transaction (snapshot)
          |
          +--> Read collection A at T
          |
          +--> Read collection B at T
          |
          +--> Write (if needed)
          |
          v
Commit with w:majority
~~~

Do not interpret a snapshot transaction as "no write conflict or abort can ever happen." Transactions can still fail under concurrent updates, excessive execution times, or failovers. Applications must handle retries using proper error labels.

### 14.5. Transaction costs

Transactions hold more state and resources than simple read operations:

- Have maximum durations and timeouts.
- Can encounter write conflicts.
- Can put pressure on snapshot history/cache.
- Retries can re-execute the application callback.
- Operations creating collections/indexes have special transaction/read concern rules.

**Do not keep a transaction open while a user edits a form.** Use a snapshot of data for display, then conditional updates/version CAS on submission; only open short transactions when cross-document atomicity is needed.

## 15. Snapshot isolation does not equal serializable for every workload

A common misconception:

> "I used snapshot reads, so all business decisions based on multiple documents are automatically safe from competing transactions."

Insufficient. Snapshot isolation ensures reads within the appropriate scope see a state at T, but **does not replace protecting all invariants when multiple transactions make concurrent decisions**.

For example, two doctors are eligible to be on call, with the rule "at least one must remain on call." Each transaction:

1. Reads **A=true, B=true** at snapshot T.
2. Transaction X sets **A=false**.
3. Transaction Y sets **B=false**.

If both transactions write to **two different documents** without creating a write conflict on the same document or encoding the invariant via a constraint mechanism, **write skew** can occur in systems using snapshot isolation.

~~~text
Snapshot T:
  Doctor A onCall=true
  Doctor B onCall=true

Tx X reads both -> writes A=false
Tx Y reads both -> writes B=false

Risk:
  A=false and B=false
  violating invariant "at least one person on call"
~~~

Solutions must be designed around the invariant:

- Consolidate the protected condition into **a single document/aggregate** that can be updated atomically.
- Design a **guard document** that competing transactions contend on.
- Use appropriate unique constraints/conditional writes.
- Or design another provably correct coordination protocol.

This is a property of **isolation levels and how invariants are modeled**, not a MongoDB bug for allowing snapshots.

## 16. Sharded clusters: orphaned documents and cross-shard snapshots

### 16.1. Local and available differ on shard ownership

In a sharded collection, `mongos` relies on metadata to route queries. Chunk migrations can leave temporary **orphaned documents** on a source shard.

Read concern **available** can serve queries without verifying shard ownership during a network partition. Per MongoDB documentation, it may return **orphaned documents** and inaccurate results in those situations.

Read concern **local** avoids this specific risk through stricter consistency/routing checks; it still does not guarantee majority durability.

### 16.2. Majority does not mean a cross-shard snapshot

Suppose a report queries data across two shards:

~~~text
Shard A:
  majority-committed view at time T1

Shard B:
  majority-committed view at time T2
~~~

Requesting readConcern majority alone does not guarantee data from A and B come from **the same logical point in time T** for every query/report.

If you need a **cross-shard point-in-time** report, choose **snapshot** within supported command/transaction boundaries, while evaluating snapshot history and resource costs.

### 16.3. Linearizable on sharded collections

Linearizable should not be treated as a general solution for a multi-shard report. The guarantee applies to read operations uniquely identifying a single document with primary routing. For cross-document/cross-shard business logic, proper data models, transactions, and invariants are required.

### 16.4. Timeouts and network partitions

When multiple shards/nodes become unavailable:

- **available** may continue returning results with weaker guarantees.
- **majority** may wait or fail to serve an appropriate view when quorum/replication has issues.
- **linearizable** may time out if primary/majority cannot be verified.
- **snapshot** may wait for a timestamp, time out, or fail if history is insufficient.

Choose whether to prioritize **availability or consistency** based on the data type; do not enable available just to "fix timeouts" on a financial API.

## 17. Java Sync Driver: setting read concern at the right scope

The MongoDB Java Sync Driver defines these constants:

~~~java
ReadConcern.LOCAL
ReadConcern.AVAILABLE
ReadConcern.MAJORITY
ReadConcern.LINEARIZABLE
ReadConcern.SNAPSHOT
~~~

Read concern can be configured on **MongoClient**, **MongoDatabase**, or **MongoCollection** per supported APIs. A collection/database object with a specific read concern is a **new view**, and does not mutate the original object's configuration.

### 17.1. Example reading majority from a collection

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import org.bson.Document;

public final class ReadConcernDemo {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI is required"
            );
        }

        try (MongoClient client = MongoClients.create(uri)) {
            MongoDatabase database = client.getDatabase(
                    "mongo_consistency_lab"
            );

            MongoCollection<Document> orders =
                    database.getCollection("orders");

            MongoCollection<Document> majorityOrders =
                    orders.withReadConcern(ReadConcern.MAJORITY)
                          .withReadPreference(ReadPreference.primary());

            Document order = majorityOrders.find(
                    new Document("_id", "ORD-100")
            ).first();

            System.out.println(order == null ? "Not found" : order.toJson());
        }
    }
}
~~~

Meaning:

- **withReadConcern(ReadConcern.MAJORITY)** requests a majority-committed view.
- **withReadPreference(ReadPreference.primary())** selects the primary.
- The query with filter **_id** uses the MongoDB Java Driver; it is not a transaction.
- The original **orders** handle is not mutated by **with...** calls; **majorityOrders** is a newly configured collection handle.

**Warning:** primary + majority does not mean every read is linearizable. If an API requires single-document real-time guarantees, consider **LINEARIZABLE** and a timeout.

### 17.2. Configuring each level on the same collection

~~~java
MongoCollection<Document> localView =
        orders.withReadConcern(ReadConcern.LOCAL);

MongoCollection<Document> availableView =
        orders.withReadConcern(ReadConcern.AVAILABLE);

MongoCollection<Document> majorityView =
        orders.withReadConcern(ReadConcern.MAJORITY);

MongoCollection<Document> snapshotView =
        orders.withReadConcern(ReadConcern.SNAPSHOT);
~~~

These handles express different read requirements. **Not every level is valid for every operation/topology**. For example, snapshot outside transactions only works with supported commands on compatible MongoDB versions.

### 17.3. Linearizable with primary and timeout

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.client.MongoCollection;
import org.bson.Document;
import java.util.concurrent.TimeUnit;

MongoCollection<Document> strongSingleDocumentView =
        orders.withReadPreference(ReadPreference.primary())
              .withReadConcern(ReadConcern.LINEARIZABLE);

Document result = strongSingleDocumentView
        .find(new Document("_id", "ORD-100"))
        .maxTime(5, TimeUnit.SECONDS)
        .first();
~~~

**maxTime** sets a server-side execution time limit for the query. If linearizable cannot be satisfied within the limit, the driver may throw an exception. Do not interpret the exception as the document not existing.

### 17.4. Secondary read preference combined with majority

~~~java
MongoCollection<Document> majoritySecondaryView =
        orders.withReadPreference(ReadPreference.secondaryPreferred())
              .withReadConcern(ReadConcern.MAJORITY);

Document order = majoritySecondaryView.find(
        new Document("_id", "ORD-100")
).first();
~~~

This is a majority read that prefers secondaries. **It can still be stale** due to secondary lag; read concern does not turn `secondaryPreferred` into `primary`.

### 17.5. Configuration inheritance

A common model:

~~~text
MongoClient defaults
      |
      v
MongoDatabase settings
      |
      v
MongoCollection settings
      |
      v
Read operation

Transaction options have their own precedence
when the operation runs inside a transaction.
~~~

If collection settings differ from client settings, the collection handle uses its specific settings for operations outside transactions. Inside a transaction, **transaction-level read concern** is the setting that applies. Therefore, do not reason from a collection handle while ignoring session/transaction context.

## 18. Java Sync Driver: causally consistent session

When you need to read a prior write in a causally related sequence of operations, use a client session with majority read/write concern:

~~~java
import com.mongodb.ClientSessionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoClient;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public final class CausalSessionExample {
    public static void run(MongoClient client) {

        MongoCollection<Document> orders = client
                .getDatabase("mongo_consistency_lab")
                .getCollection("orders")
                .withReadConcern(ReadConcern.MAJORITY)
                .withWriteConcern(WriteConcern.MAJORITY);

        ClientSessionOptions options = ClientSessionOptions.builder()
                .causallyConsistent(true)
                .build();

        try (ClientSession session = client.startSession(options)) {
            orders.updateOne(
                    session,
                    eq("_id", "ORD-100"),
                    set("status", "PAID")
            );

            Document updated = orders.find(
                    session,
                    eq("_id", "ORD-100")
            ).first();

            System.out.println(updated);
        }
    }
}
~~~

Key points to remember:

1. Operations must pass the **same ClientSession**.
2. Read concern majority and write concern majority support full causal consistency guarantees per documentation.
3. The driver manages operation time/cluster time; do not inject arbitrary timestamps manually.
4. Do not run multiple operations concurrently on the **same ClientSession** from multiple threads; drivers/sessions enforce concurrency constraints.
5. Causal sessions do not replace transactions when multiple documents must commit together.

### 18.1. Is a session a transaction?

**No.** A session can execute multiple operations without starting a transaction. Causal consistency guarantees ordering of causally related operations; a transaction is a mechanism grouping database operations into an atomic commit/abort unit.

~~~text
Causal session:
  Read/Write A -> Read/Write B
  B respects causal relationship with A

Transaction:
  Begin -> Operations -> Commit/Abort
  Has its own atomic commit scope and isolation
~~~

## 19. Java Sync Driver: transaction with snapshot

Example reading two accounts inside the same transaction:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import org.bson.Document;

import static com.mongodb.client.model.Filters.eq;

public final class SnapshotTransactionExample {

    public static void run(MongoClient client) {
        MongoCollection<Document> accounts = client
                .getDatabase("mongo_consistency_lab")
                .getCollection("accounts");

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.startTransaction(options);

            try {
                Document accountA = accounts
                        .find(session, eq("_id", "ACCOUNT-A"))
                        .first();

                Document accountB = accounts
                        .find(session, eq("_id", "ACCOUNT-B"))
                        .first();

                System.out.println(accountA);
                System.out.println(accountB);

                session.commitTransaction();
            } catch (RuntimeException ex) {
                session.abortTransaction();
                throw ex;
            }
        }
    }
}
~~~

This is a minimal example showing **TransactionOptions.readConcern(SNAPSHOT)** and **writeConcern(MAJORITY)**. It is not a full transaction retry pattern.

In production:

- Only use transactions on supported deployments.
- Handle **TransientTransactionError** and **UnknownTransactionCommitResult** per retry guidelines/driver helpers.
- Do not execute external side effects outside MongoDB inside a transaction callback if they could be repeated.
- Bound duration, operation count, and data size within transactions.
- Do not specify a different readConcern on individual finds expecting to override the transaction-level snapshot.

## 20. Spring Data MongoDB: using concerns and transactions

Spring Data MongoDB builds on the MongoDB Java Driver, so read concern/read preference/write concern concepts remain the same.

### 20.1. Configuring transaction manager with snapshot

Java configuration example:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfiguration {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {

        TransactionOptions options = TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .build();

        return new MongoTransactionManager(factory, options);
    }
}
~~~

Declaring **MongoTransactionManager** enables Spring to manage transactions in services with valid transaction configuration.

### 20.2. Reading inside @Transactional

~~~java
import org.bson.Document;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountReportService {

    private final MongoTemplate mongoTemplate;

    public AccountReportService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    @Transactional(readOnly = true)
    public long readTotalBalance() {
        Document a = mongoTemplate.findOne(
                Query.query(
                        Criteria.where("_id").is("ACCOUNT-A")
                ),
                Document.class,
                "accounts"
        );

        Document b = mongoTemplate.findOne(
                Query.query(
                        Criteria.where("_id").is("ACCOUNT-B")
                ),
                Document.class,
                "accounts"
        );

        long aBalance = a == null ? 0L
                : ((Number) a.get("balance")).longValue();

        long bBalance = b == null ? 0L
                : ((Number) b.get("balance")).longValue();

        return aBalance + bBalance;
    }
}
~~~

This example assumes the `balance` field uses a compatible BSON numeric type and the domain permits treating two missing accounts as 0; in real financial applications, **do not silently default a missing account to 0** if that represents an error state. The goal is illustrating two reads participating in a Spring-managed transaction.

**Note:** **@Transactional(readOnly=true)** is a hint and can still open a MongoDB transaction in corresponding configurations. Actual read concern is determined by the transaction manager/options and overrides, not simply by the annotation flag.

### 20.3. Do not confuse raw driver collections with MongoTemplate transactions

~~~java
mongoTemplate.getCollection("orders")
        .withReadConcern(ReadConcern.MAJORITY);
~~~

This call obtains a **native driver** collection handle with read concern majority. If you invoke raw driver operations directly without passing the Spring-managed transaction's session, you may step outside the intended transaction boundary. When transactions are needed, use session-aware Spring Data APIs or integrate client sessions properly per documentation.

### 20.4. Configuring different read concerns per use case

In an application with multiple endpoints, it is rarely appropriate to set **LINEARIZABLE** globally just because one API requires it.

Design suggestions:

- Repositories reading routine list views: read concern aligned with SLAs and data sensitivity.
- Services coordinating single-document state: native driver handle with LINEARIZABLE + maxTimeMS when needed.
- Multi-document transactional services: MongoTransactionManager with SNAPSHOT + majority commit.
- Services with causal chains: ClientSession/driver APIs accordingly.

Document explicitly which **consistency property** each endpoint requires, rather than repeating a single implicit setting across all operations.

## 21. Default configuration and precedence

MongoDB supports configuring **global default read concern** and **global default write concern** for replica sets/sharded clusters via administrative commands.

By default without overrides, read concern on primary/secondary is usually **local**, though **you must never blindly assume local** on deployments with custom defaults or connection settings.

Configuration sources can include:

1. Deployment-level defaults.
2. MongoClient settings or connection string.
3. MongoDatabase handle.
4. MongoCollection handle.
5. Transaction options when the operation belongs to a transaction.

### 21.1. Inspecting the deployment

With appropriate administrative privileges:

~~~javascript
db.adminCommand({
  getDefaultRWConcern: 1
});
~~~

The response can show default read/write concerns and the source of those settings. Field names and display format may vary by MongoDB version/deployment.

Do not modify global defaults just to test a single API: that change can impact multiple applications.

### 21.2. Centralized defaults with controlled overrides

An operational policy might:

- Set a default suited for the majority of workloads.
- Require critical reads to declare an explicit concern at the repository/service layer.
- Attach timeouts to reads that could wait extensively.
- Log/collect metrics for special concern levels.
- Verify that drivers and topologies support the chosen levels.

Do not rely solely on implicit defaults if an endpoint carries a strict consistency contract.

## 22. Choosing read concern by business requirement

### 22.1. Product listing page

Requirements:

- Users view product names, images, and descriptions.
- Tolerates slight delay for recent updates to appear.
- Requires high throughput and low latency.

A viable option is **local** with an appropriate read preference. If displayed data must strictly avoid rollbacks, consider **majority**.

There is no need to default to **linearizable** for the entire catalog because it does not provide a collection-wide linearizable snapshot.

### 22.2. Payment confirmation

Requirements:

- Display PAID only once the write state is sufficiently durable per policy.
- Never confirm payment based solely on a local write not yet majority-committed.

A possible design:

1. Write status with **writeConcern majority**.
2. Read with **readConcern majority** or a causal session if read-your-writes is required.
3. When verifying **single-document** state in real-time order, consider **linearizable** on the primary.
4. Design idempotency and integration with the payment provider.

Do not use **a majority read alone** as proof that funds were captured by a third party. Payment status must be verified per business protocol and authoritative sources.

### 22.3. Checking a feature flag or leader state

Requirements:

- A majority write changing a flag/leader has completed.
- Subsequent reads must reflect the new state in real time.
- The document has a single unique key.

**linearizable + primary + maxTimeMS** can be an appropriate choice.

However, combine it with **conditional writes**, leases/fencing tokens, and timeout handling. If the read cannot verify within the deadline, select a fallback following system safety principles.

### 22.4. Multi-collection revenue report

Requirements:

- Order totals, payment details, and refunds must belong to the same point-in-time view.
- Can tolerate a snapshot slightly behind current real-time state.

**snapshot** inside a transaction or snapshot reads suited to the operation scope is worth considering.

Do not use linearizable on a single-document find and assume the entire multi-collection report is linearizable.

### 22.5. Dashboards not requiring absolute precision

Requirements:

- Near real-time statistics.
- Tolerates slight staleness or periodic self-refresh.

Can use **local** or **majority** depending on whether rollbacks must be avoided. If reading from secondaries, replication lag must be tolerated.

**available** should only be considered when tolerating sharded-cluster-specific risks and genuinely prioritizing availability over accuracy.

### 22.6. Re-reading saved changes in the same session

Requirements:

- User clicks Save and receives success.
- Immediately afterward, the same workflow reads back the saved state.

Using a **causally consistent session + majority read/write** is the standard choice when causal consistency across replica set members is required. Even when using the primary within the same request flow, you must still understand failover, caching, session boundaries, and durability requirements.

### 22.7. Cached data or data tolerating staleness

If a response has a cache TTL or business rules allow staleness, a stronger read concern will not make a stale cache fresh. You must clarify:

- How stale can the cache be at most?
- How does cache invalidation work?
- Does reading from secondaries add extra lag beyond caching?
- Does rollback risk impact business decisions or only UI display?

**Database consistency and cache freshness are two distinct issues.**

## 23. Decision tree for choosing read concern

~~~text
What do you need to read?
        |
        +-- Need a consistent point-in-time view
        |   across multiple documents / shards?
        |         |
        |         +-- YES --> SNAPSHOT
        |         |           + transaction if multiple commands needed
        |         |           + majority commit & history limits
        |         |
        |         +-- NO
        |               |
        |               v
        +-- Need real-time order for a single
        |   uniquely identified document?
        |         |
        |         +-- YES --> LINEARIZABLE
        |         |           + PRIMARY
        |         |           + maxTimeMS
        |         |           + majority writes
        |         |
        |         +-- NO
        |               |
        |               v
        +-- Need to avoid rollback-prone data?
        |         |
        |         +-- YES --> MAJORITY
        |         |           + causal session if
        |         |             read-your-writes needed
        |         |
        |         +-- NO
        |               |
        |               v
        +-- Tolerate staleness / rollback?
                  |
                  +-- YES --> LOCAL
                  |
                  +-- If sharded partition and need
                      extreme availability despite
                      orphaned documents risk
                           |
                           +-- AVAILABLE
~~~

This is a **thinking guide**, not a substitute for reading version documentation and testing your workload. An API may carry simultaneous requirements—such as timeouts, authorization, write concerns, and cross-document invariants—that need architecture beyond a single read concern.

## 24. Common misconceptions

### 24.1. "Read concern majority reads the latest version"

**False.** Majority only returns majority-committed data. A secondary or majority view that has not caught up can still return older data.

For real-time ordering on one document, look at linearizable; for read-your-writes along a causal chain, look at causal sessions.

### 24.2. "Choosing primary is enough to guarantee linearizable"

**False.** During certain network partitions, an old primary may temporarily not realize it lost its role and serve stale data. Linearizable requires additional verification and only holds for qualifying query shapes.

### 24.3. "Read concern local means reading only from the local machine"

**False.** `local` does not specify which node to read from. **Read preference** controls primary/secondary routing. `local` describes what data can be read on whichever node was selected.

### 24.4. "Available is like majority but faster"

**False.** Available carries weaker data guarantees, can return rolled-back data, and in sharded clusters can return orphaned documents.

### 24.5. "Available is always the fastest option for every deployment"

Do not generalize. On unsharded collections, available and local have equivalent semantics. Actual performance depends on network, query plans, caching, replication, and topology—not just the read concern name.

### 24.6. "WriteConcern majority automatically makes all reads majority"

**False.** Write concern and read concern are separate settings. Reads still use their configured default or override level.

### 24.7. "Majority always guarantees reading the write I just sent from a new session"

Not necessarily. For **read-your-writes** in a causal sequence, consider a **causal session** with majority reads/writes or other routing/protocol guarantees. An independent new session does not automatically inherit causal context.

### 24.8. "Linearizable applies to a collection-wide aggregation"

Do not rely on linearizable guarantees for thousands of documents in a single report. Per MongoDB, the guarantee only applies to query filters uniquely identifying a single document and corresponding search key conditions.

### 24.9. "Linearizable does not need a timeout because we want strong consistency"

On the contrary, because it must verify majority and primary conditions, MongoDB recommends **always using maxTimeMS**. When unable to satisfy conditions, return a timeout error rather than inferring data is absent.

### 24.10. "Snapshot is always the latest data"

**False.** A snapshot can be at a point T in the past. It guarantees a point-in-time view, not real-time recency.

### 24.11. "Snapshot outside a transaction on one query automatically applies to subsequent queries"

Not by default. Sharing a timestamp across multiple reads requires a transaction or managing snapshot timestamps via supported APIs.

### 24.12. "Using snapshot transactions automatically makes all cross-document invariants safe"

Snapshot isolation does not automatically make every workload serializable. You must design guard documents, write conflicts, conditional writes, or business protocols for cross-document invariants.

### 24.13. "You can set different readConcern levels on each find inside a transaction"

No. Read concern is set at the **transaction level**. MongoDB does not permit arbitrary per-operation read concern levels inside a transaction.

### 24.14. "Causal sessions and transactions are the same thing"

No. Causal sessions preserve causal ordering; transactions have commit/abort semantics and isolation at the chosen level. A causal session does not atomically commit multiple writes by itself.

### 24.15. "Seeing PAID with local means it cannot roll back"

No. Locally applied data may not yet be majority-committed and can roll back under eligible failover scenarios.

### 24.16. "Read concern fixes slow queries caused by missing indexes"

No. Read concern does not replace indexes, query optimization, or data modeling. A `COLLSCAN` query can still be slow at any level.

### 24.17. "Read concern prevents double charges"

No. Double charges typically relate to idempotency, payment provider protocols, retries, and business atomicity. Read concern is only one piece of read data consistency.

## 25. Monitoring and testing read concern choices

### 25.1. Observing replication

In `mongosh`, with appropriate privileges:

~~~javascript
rs.status();
~~~

Observe primary/secondary status, replication progress info, and member health. Do not rely solely on a single `rs.status()` check in production; use a monitoring system that collects metrics over time.

In MongoDB Atlas or managed services, use corresponding dashboards/provider metrics for replication lag, node availability, and read/write latency.

### 25.2. Tracking key indicators

| Metric | Meaning |
|---|---|
| **Secondary replication lag** | Risk of stale reads, especially when readPreference selects secondaries. |
| **Majority commit point progress** | Ability to read majority-committed writes. |
| **Read latency p95/p99 by level** | Latency impact when using majority/linearizable/snapshot. |
| **Timeouts/maxTimeMS errors** | Queries not completing within limits or consistency conditions unmet. |
| **Primary elections/failovers** | Context for rollbacks/stale primaries and availability. |
| **Transaction abort/retry rate** | Concurrency load and snapshot transaction behavior. |
| **SnapshotTooOld/history errors** | Snapshot T too old or long-running operations. |
| **Sharded chunk migrations** | Context for orphaned documents and routing consistency. |

Exact metric names depend on server version, telemetry provider, and driver. Map them to your actual observability sources.

### 25.3. Testing read concern local before failover

In a test replica set environment where failovers can be orchestrated:

1. Write data with a weak write concern like `w:1`.
2. Induce controlled replication lag / slow member conditions.
3. Read with `local` on the primary or secondary.
4. Observe differences before W1 is majority-committed.
5. Trigger failover **in an authorized test environment**.
6. Observe how non-majority-committed data can roll back.

Never break production replication or primaries just to test lesson concepts.

### 25.4. Testing majority and secondary lag

1. Write a document with `w:"majority"`.
2. Read from primary with majority.
3. Read from secondary with majority.
4. Observe that a secondary may lag in recognizing/reflecting W1.
5. Compare with a causal session executing a read-after-write sequence.

**Do not write assertions like "secondary majority must immediately see W1 after exactly N ms"** without corresponding lag/timeout guarantees.

### 25.5. Testing linearizable

1. Write a field on a document identified by `_id` with `w:"majority"`.
2. After the write is acknowledged, read with `linearizable` on the primary with `maxTimeMS`.
3. Verify the result reflects that write or a newer valid state.
4. When quorum is lost, verify the read can time out and the application handles errors differently from "does not exist."

### 25.6. Testing snapshot

1. Create two documents with states whose sum can be checked.
2. Inside a transaction with snapshot read concern, read both.
3. In another thread, intentionally update their states.
4. Verify snapshot reads do not arbitrarily mix data from different points in time.
5. Verify transactions can encounter conflicts/aborts under competing concurrent writes.

For sharded setups, test across multiple shards and snapshot history; do not test solely on local standalone instances.

## 26. Practice exercises

### Exercise 1 — Distinguishing the three settings

Explain what each of the following controls:

~~~text
readPreference = secondary
readConcern = majority
writeConcern = majority
~~~

Why does readConcern majority not force the driver to read from the primary?

### Exercise 2 — local on primary and secondary

A write W1 has been applied on the primary but not yet replicated to a secondary. Predict how local reads on the two nodes can return different results.

### Exercise 3 — rollback

W1 was acknowledged only with `w:1`, and then the primary failed over before majority commit. A local read before failover returned W1. Why does this not contradict MongoDB atomicity?

### Exercise 4 — available and orphaned documents

Describe a chunk migrating from Shard A to Shard B during a network partition. Why can `available` return data from a shard that no longer owns the chunk? In which scenarios should `available` be avoided?

### Exercise 5 — Is majority always the freshest?

The primary acknowledged W1 with majority, but a lagging secondary cannot serve W1 yet. If reading with majority on that secondary, can an older state be observed? Explain.

### Exercise 6 — linearizable and real-time

A `w:"majority"` write to **`{_id:"flag.checkout"}`** has completed. A `linearizable` read starts afterward. What guarantees can the application expect? Why should `maxTimeMS` be used?

### Exercise 7 — Why does linearizable require a single-document query?

Compare:

~~~javascript
db.flags.find(
  { _id: "checkout.enabled" }
).readConcern("linearizable").maxTimeMS(5000);
~~~

with:

~~~javascript
db.flags.find(
  { status: "ACTIVE" }
).readConcern("linearizable").maxTimeMS(5000);
~~~

Why should you not apply the guarantee of the first query to the entire set of documents returned by the second query?

### Exercise 8 — Multi-document snapshot

Two accounts are updated in a funds transfer transaction. Explain why a report reading both at a single snapshot T is more appropriate than independent reads at different times.

### Exercise 9 — Snapshot does not mean latest data

A snapshot is selected at T. Write W2 is majority-committed at T+1. Must snapshot T return W2? Explain.

### Exercise 10 — atClusterTime

Write a **`find`** command with read concern snapshot and `atClusterTime` (using a valid timestamp obtained from a real server). State two scenarios in which the server might wait or return an error.

### Exercise 11 — Causal consistency

Write pseudo-code:

~~~text
start session
write with majority
read with majority in same session
end session
~~~

Explain the role of `afterClusterTime` automatically added by the driver and why opening a separate new session does not automatically inherit causal context.

### Exercise 12 — Java Driver

From a `MongoCollection<Document>`, create:

- A handle with read concern majority, read preference `secondaryPreferred`.
- A handle with read concern linearizable, read preference `primary`.
- A single-document find command with `maxTime` 5 seconds.

### Exercise 13 — Transactions in Java

Create `TransactionOptions` with:

~~~java
ReadConcern.SNAPSHOT
WriteConcern.MAJORITY
ReadPreference.primary()
~~~

Explain why you should not specify a separate read concern on `find` inside the transaction.

### Exercise 14 — Choosing concerns per API

Map the following requirements to one or more appropriate mechanisms:

1. A product catalog listing that tolerates staleness.
2. Checking a single-document flag after a majority write.
3. A multi-document financial report at the same point in time.
4. Read-your-writes via secondaries within the same working session.
5. A sharded dashboard prioritizing availability despite orphaned record risk.

For each choice, state at least one limitation.

### Exercise 15 — Default configurations

Explain why a deployment with a modified global default read concern may differ from application assumptions. Use `getDefaultRWConcern` to inspect it if privileged.

### Exercise 16 — Failover testing

Propose a test plan verifying readConcern `local`, `majority`, and `linearizable` in a test replica set environment. Show how to distinguish a **timeout** from **document does not exist**.

## 27. Review questions

1. What is read concern used to control?
2. How does read concern differ from read preference?
3. How does read concern differ from write concern?
4. Does `local` always read from the primary?
5. Why can `local` return writes that later roll back?
6. In what scenario does `available` differ most significantly from `local`?
7. What is an orphaned document, and how can `available` expose it?
8. What kind of data does `majority` guarantee to return?
9. Can a majority read on a secondary be stale?
10. Why does `majority` not automatically equal `linearizable`?
11. Which writes completed before a read begins does `linearizable` reflect?
12. Does `linearizable` require the primary?
13. Why is a query filter uniquely identifying a single document required for the linearizable guarantee?
14. Why should `linearizable` specify `maxTimeMS`?
15. What property does `snapshot` guarantee that `majority` alone does not automatically guarantee?
16. Does `snapshot` always include the latest majority write?
17. Starting in MongoDB 5.0, which read operations support `snapshot` outside transactions?
18. How does `atClusterTime` differ from `afterClusterTime`?
19. What errors can finite snapshot history cause?
20. Which read concern levels do multi-document transactions support?
21. Why is transaction-level concern more important than collection-level concern?
22. What are the four commonly cited properties of causal consistency?
23. How must read/write concerns be combined for full causal consistency with durability?
24. Why is a causal session not a transaction?
25. Why does snapshot isolation not automatically ensure all business invariants are serializable?
26. In Spring Data MongoDB, what must you watch out for when using `MongoTransactionManager` and raw driver collections?
27. How would you choose levels for a product listing API, a leader-check API, and a financial reporting API?

## 28. Summary

MongoDB's five read concerns are not simply five tiers from "fast to slow"; they represent distinct consistency goals:

~~~text
local
  -> Node-local data on the selected node.
  -> Can be stale and roll back.

available
  -> Prioritizes availability, especially on sharded clusters.
  -> Can return orphaned documents during partitions/migrations.

majority
  -> Only returns majority-committed data.
  -> Protects against rollback under normal mechanisms.
  -> Does not guarantee always freshest.

linearizable
  -> Real-time ordering with majority writes for
     queries uniquely identifying a single document.
  -> Primary only, higher latency, requires maxTimeMS.

snapshot
  -> Majority-committed point-in-time view.
  -> Useful for transactions/multi-document reports,
     including across shards where supported.
  -> Can be in the past, bounded by snapshot history.
~~~

**Principles to remember:**

1. Always distinguish **which node to read from (read preference)**, **what data consistency level to read (read concern)**, and **when writes are acknowledged (write concern)**.
2. **majority** provides durability for the data being read, but does not automatically provide real-time ordering.
3. **linearizable** targets real-time ordering for a single document, requiring primary routing and a timeout.
4. **snapshot** targets a consistent view at a single timestamp, not necessarily the latest version.
5. **available** is a choice accepting weaker consistency, particularly requiring caution regarding orphaned documents on sharded clusters.
6. **Causal sessions + majority read/write** help causally related operations observe the proper order.
7. **Transaction-level read concern** determines isolation inside a transaction; do not set different read concerns per operation.
8. Depending on business requirements, you still need **unique indexes, conditional writes, transactions, idempotency, cache invalidation**, and failover testing.

### Official MongoDB documentation

- [MongoDB Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — overview of levels and applicability.
- [Read Concern "local"](https://www.mongodb.com/docs/manual/reference/read-concern-local/) — local views and rollbacks.
- [Read Concern "available"](https://www.mongodb.com/docs/manual/reference/read-concern-available/) — availability, sharded clusters, and orphaned documents.
- [Read Concern "majority"](https://www.mongodb.com/docs/manual/reference/read-concern-majority/) — majority commit, durability, and lag.
- [Read Concern "linearizable"](https://www.mongodb.com/docs/manual/reference/read-concern-linearizable/) — real-time ordering, single-document, primary, maxTimeMS.
- [Read Concern "snapshot"](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/) — point-in-time, atClusterTime, and snapshot history.
- [MongoDB Read Preference](https://www.mongodb.com/docs/manual/core/read-preference/) — primary/secondary/nearest and routing.
- [MongoDB Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — w:1, majority, and acknowledgment.
- [Read Isolation, Consistency, and Recency](https://www.mongodb.com/docs/manual/core/read-isolation-consistency-recency/) — stale reads, causal consistency, and isolation.
- [Causal Consistency and Read/Write Concerns](https://www.mongodb.com/docs/manual/core/causal-consistency-read-write-concerns/) — guarantees in client sessions.
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — transaction read concern and commit write concern.
- [MongoDB Java Sync Driver: CRUD Settings](https://www.mongodb.com/docs/drivers/java/sync/current/crud/crud-settings/) — withReadConcern/withReadPreference/withWriteConcern.
- [MongoDB Java Sync Driver: Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — sessions, TransactionOptions, and retries.
- [Spring Data MongoDB: Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — MongoTransactionManager and Spring transaction behavior.

When designing a MongoDB read, the most important question is not "which level is the strongest," but **"what exact guarantee does the application need regarding observed data?"** If you need to avoid rollbacks, consider **majority**; if you need real-time ordering for a single document, use **linearizable**; if you need a consistent point-in-time view across multiple documents/shards, use **snapshot**. Choose according to your requirements and verify against your actual topology, version, and workload.



