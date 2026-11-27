# Traffic Shifting, Drift Monitoring, and Rollback Plans in MongoDB

When an application changes its document model, splits a collection, upgrades a schema, or moves MongoDB to a new cluster, copying all historical data **does not mean the migration is complete**. While the backfill runs, the application continues creating orders, updating balances, canceling transactions, and deleting records. If read traffic is shifted too early, users may see stale data. If write traffic is shifted without guardrails, the two data paths can diverge. If you immediately revert to the old source after the new source has already received acknowledged transactions, those changes can **disappear** from the application.

Therefore, MongoDB data evolution requires designing three capabilities together:

1. **Controlled traffic shifting:** defining the source of truth, performing shadow reads/canary rollouts, locking in a cutover point, and blocking unauthorized writers.
2. **Meaningful drift monitoring:** comparing keys, content, revisions, deletes, business invariants, CDC lag, and performance—not just document counts.
3. **Data-preserving rollback:** defining the rollback window, reverse sync, and policies for handling new writes committed after cutover.

This lesson belongs to the **Data Evolution** chapter of the *Database Engine Document MongoDB* module. Examples use two collections `orders_v1` and `orders_v2`, along with two-cluster scenarios. Write commands must only be run on an **isolated lab database**; thresholds and hostnames are simulated. Features such as change streams, transactions, read concern, sharding, and driver options must be verified against your actual server version and topology.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish data migration, backfill, CDC, read cutover, write cutover, and rollback.
2. Build the state machine `prepare → backfill → catch-up → verify → shadow → canary → cutover → stabilize → contract`.
3. Identify the authoritative data source in each phase and how write authority is protected.
4. Compare big-bang, expand-and-contract, blue/green, shadow reads, dual writes, and CDC.
5. Orchestrate backfill while capturing change events so no writes are missed.
6. Understand checkpoints, resume tokens, oplog window, event ordering, deletes, and idempotency.
7. Design deterministic transform functions and canonical parity for evolving schemas.
8. Measure missing/extra IDs, same-revision mismatches, lag, and business invariants.
9. Set up canary cohorts, read-your-writes policies, and GO/NO-GO thresholds.
10. Switch write authority using drain, fencing, watermarks, and verifying old writers have stopped.
11. Distinguish rollback before and after writes have shifted to v2.
12. Build reverse CDC, rollback windows, and forward-fix decisions.
13. Test fault/crash/replay scenarios, rehearse rollback, and operate dashboards.

## 2. Copied Data Differs from Shifted Traffic

| Data | Traffic | Status |
|---|---|---|
| v2 empty | Read/write v1 | Preparing |
| v2 backfilling | Read/write v1 | Insufficient data |
| Copy complete but CDC lagging | Read/write v1 | Not fresh enough |
| v2 caught up and parity met | Read/write v1, shadow v2 | Verifying |
| Canary reads v2 | Writes v1 | Checking UX/latency, handling consistency |
| Switching write authority | Drain/fence, lock watermark | High-risk moment |
| v2 authoritative | Read/write v2 | Monitoring and maintaining rollback readiness |
| Rollback window expired | Read/write v2 | Controlled cleanup of old source |

### 2.1. Source of Truth

The source of truth is the designated data path that determines **whether a business write has succeeded**. A replica with a newer revision does not automatically become authoritative if it was written by a worker on the wrong path.

### 2.2. Two Collections vs. Two Clusters

Within a single MongoDB deployment that supports transactions, multiple writes can be committed atomically in one transaction within the corresponding limits. With **two independent MongoDB clusters**, there is no standard MongoDB transaction that commits atomically across both clusters. You need a replication/outbox protocol, retries, and reconciliation.

### 2.3. State Machine

~~~mermaid
stateDiagram-v2
    [*] --> PREPARE
    PREPARE --> BACKFILL
    BACKFILL --> CATCH_UP
    CATCH_UP --> SHADOW
    SHADOW --> CANARY_READ
    CANARY_READ --> WRITE_CUTOVER
    WRITE_CUTOVER --> STABILIZE
    STABILIZE --> CONTRACT
    CANARY_READ --> READ_ROLLBACK
    WRITE_CUTOVER --> SYNC_ROLLBACK
    STABILIZE --> SYNC_ROLLBACK
    READ_ROLLBACK --> SHADOW
    SYNC_ROLLBACK --> PREPARE
    CONTRACT --> [*]
~~~

Do not jump from BACKFILL straight to CONTRACT simply because row counts are equal.

## 3. Running Example: orders_v1 → orders_v2

Old document:

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  amountCents: NumberLong(125000),
  state: "paid",
  updatedAt: ISODate("2026-11-01T10:00:00Z"),
  revision: NumberLong(7)
}
~~~

New document:

~~~javascript
{
  _id: "O-1001",
  tenantId: "t-01",
  totalMinor: NumberLong(125000),
  status: "PAID",
  updatedAt: ISODate("2026-11-01T10:00:00Z"),
  revision: NumberLong(7),
  schemaVersion: 2
}
~~~

Preserve `_id`, tenant, money units, and revision. `amountCents` becomes `totalMinor`, and `state` becomes `status`. If you change the ID, you need **stable ID mapping** and handling for foreign references. Generating a new ID on every backfill retry creates duplicate-record risks.

### 3.1. Revisions Must Be Monotonic

Backfill may deliver revision 7 to v2 **after** CDC has already applied revision 9. If the writer performs an unconditional replace, v2 regresses in state. You need a monotonic revision or per-aggregate event sequence; client-supplied timestamps are not an absolute ordering guarantee.

### 3.2. Deterministic Transform Function

~~~javascript
function toV2(source) {
  const states = {
    pending: "PENDING",
    paid: "PAID",
    shipped: "SHIPPED",
    cancelled: "CANCELLED"
  };
  const status = states[source.state];
  if (!status) throw new Error("UNKNOWN_STATE:" + source.state);
  return {
    _id: source._id,
    tenantId: source.tenantId,
    totalMinor: source.amountCents,
    status,
    revision: source.revision,
    updatedAt: source.updatedAt,
    schemaVersion: 2
  };
}
~~~

Do not silently coerce an unknown status to PENDING; send it to quarantine and alert. Do not use `new Date()` or random numbers to generate canonical business output if repeatable reconciliation is required.

## 4. Migration Strategies

| Strategy | Mechanism | Risks |
|---|---|---|
| Big-bang | Pause writes, copy, then switch once | Downtime, complex rollback |
| Expand-and-contract | Readers/writers tolerate multiple schemas across releases | Long-lived compatibility maintenance |
| Shadow read | Query v2 to compare while still returning v1 | Extra read load, lag-induced metric noise |
| Canary read | Small cohort reads live from v2 | Read-your-writes, p99 |
| Dual write | Write the same business action to v1/v2 | Partial success, ordering, authority |
| Backfill + CDC | Copy history and continuously apply changes | Checkpoints, oplog gaps |
| Blue/green | Two deployments before switching traffic | Post-cutover new data is hard to reverse |

The choice depends on writes/s, data size, downtime budget, backward compatibility, business rules, and topology.

## 5. Expand → Migrate → Contract

**Expand:** deploy readers that tolerate both old and new fields, create target indexes, and prepare migration code. **Migrate:** backfill, sync CDC, reconcile, shadow, canary, and cut over. **Contract:** remove the old path only after stabilization and the rollback window has elapsed.

~~~text
Old app:       read/write v1 ------------------------------|
Transitional:  understands v1/v2, writes by authority -----|
New app:                             read/write v2 ----------------|
Remove v1:                                                last
~~~

During a rolling deploy, an old scheduled job or consumer can still be running even after most HTTP pods are on the new version.

### 5.1. Readers Before Writers

Typically, deploy code that **can read the new schema** before writers start writing a v2-only schema. Do not drop old fields before all consumers have been migrated.

### 5.2. Dual Fields in a Single Document

If changing the schema in place, an atomic update on the same document can maintain both old and new fields:

~~~javascript
db.orders.updateOne(
  { _id: "O-1001", tenantId: "t-01" },
  { $set: {
      amountCents: NumberLong(125000),
      totalMinor: NumberLong(125000),
      state: "paid",
      status: "PAID",
      schemaVersion: 2
  }}
);
~~~

Every write path must maintain them per contract; an old worker updating only `state` can create intra-document drift.

## 6. Write Authority by Phase

| Phase | Authoritative Writes | Reads | Secondary Path |
|---|---|---|---|
| PREPARE | v1 | v1 | v2 indexes/validators |
| BACKFILL | v1 | v1 | Batch copy |
| CATCH_UP | v1 | v1 | CDC v1→v2 |
| SHADOW | v1 | v1 | Compare v2 |
| READ_CANARY | v1 | v1/v2 | CDC v1→v2 |
| WRITE_CUTOVER | Transition with fencing | Gate-dependent | Watermark/drain |
| STABILIZE | v2 | v2 | Reverse sync if needed |
| CONTRACT | v2 | v2 | Remove old dependencies |

**Dual write** does not mean both sides get to decide independently when results differ. You must define acknowledgement, retries, conflict resolution, and a clear source of truth.

## 7. Preparing the Inventory

1. Data: collections, document sizes, variants, indexes, unique keys, TTL, validators, collation.
2. Writers: APIs, cron jobs, queues, batch scripts, ETL, admin tools, external integrations.
3. Readers: services, reports, search, caches, data warehouse, and outbox consumers.
4. Topology: replica set/sharding, shard key, FCV, regions, DNS, TLS, drivers.
5. Semantics: tenant isolation, money types, states, retention, read/write concern, idempotency.
6. Operations: backups/PITR, oplog window, throughput, on-call, rollback RPO/RTO, and owners.

### 7.1. Create Indexes and Validators Before Cutover

Copying documents does not automatically copy target indexes, collation, TTL, and access roles. A v2 collection with correct data but a missing unique index can accept double bookings once writes are enabled.

### 7.2. Protect the Source

Backfill and shadow reads add CPU, I/O, network, and connection load. Bound batch size and concurrency, test with a representative workload, and avoid overloading the source before cutover.

## 8. Backfill with Change Data Capture

~~~mermaid
flowchart LR
    V1["Source v1"] -->|"Batched scan"| V2["Target v2"]
    V1 -->|"Change streams"| CDC["CDC + checkpoint"]
    CDC -->|"Idempotent apply"| V2
    V2 --> Compare["Parity + watermark"]
~~~

If a backfill runs for two hours, data keeps changing throughout those two hours. Opening change capture **after** the copy finishes can miss inserts, updates, and deletes that occurred during the scan window.

### 8.1. Workflow

1. Establish a resumable stream/checkpoint **before the scan window**.
2. Scan the source by key/ranges; persist backfill checkpoints.
3. Receive/buffer events emitted during the scan.
4. Apply to target using stable IDs, revisions/sequences, and deletes.
5. Replay the backlog and continue CDC up to the source watermark.
6. Verify parity at a comparable boundary.

### 8.2. Not Automatically a Snapshot

Multiple `find` queries over a collection do not automatically form a point-in-time snapshot. Without an appropriate snapshot read, you need CDC and version guards to handle races between backfill and concurrent writes.

### 8.3. Oplog Retention

If a CDC worker pauses longer than the history window, the resume token can become invalid. Monitor oplog headroom and checkpoint age, alert, and keep a resync plan; **never reopen the stream from "now" and declare the data complete**.

## 9. Key-Based Backfill and Checkpoints

Isolated lab:

~~~javascript
use migration_lab
db.orders_v1.insertMany([
  {
    _id: "O-1001", tenantId: "t-01",
    amountCents: NumberLong(125000), state: "paid",
    revision: NumberLong(7),
    updatedAt: ISODate("2026-11-01T10:00:00Z")
  },
  {
    _id: "O-1002", tenantId: "t-01",
    amountCents: NumberLong(95000), state: "pending",
    revision: NumberLong(1),
    updatedAt: ISODate("2026-11-02T10:00:00Z")
  }
])
~~~

A single batch:

~~~javascript
const lastId = "O-1000";
const rows = db.orders_v1.find(
  { _id: { $gt: lastId } }
).sort({ _id: 1 }).limit(500).toArray();
print(rows.length);
~~~

### 9.1. Why Avoid Deep Skip?

`skip(5000000)` can scan millions of index entries; seeking by the last key is usually much cheaper during a scan. However, new inserts with an `_id` lower than the last key must still be covered by **CDC**.

### 9.2. Checkpoints Must Be Durable

Store the last source key, per-range progress, target apply outcomes, CDC token, and verified watermark. A worker can crash after writing to the target but before saving the checkpoint; retrying the batch must never duplicate data or regress revisions.

## 10. Change Streams

MongoDB change streams support tracking changes on compatible topologies (typically replica sets or sharded clusters). Node.js example **only receiving events**:

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGO_SOURCE_URI);
await client.connect();
try {
  const source = client.db("migration_lab").collection("orders_v1");
  const stream = source.watch(
    [],
    { fullDocument: "updateLookup", maxAwaitTimeMS: 1000 }
  );
  try {
    for await (const event of stream) {
      console.log({
        type: event.operationType,
        key: event.documentKey,
        hasResumeToken: Boolean(event._id)
      });
      // Production: validate, transform, apply, checkpoint.
    }
  } finally {
    await stream.close();
  }
} finally {
  await client.close();
}
~~~

### 10.1. `updateLookup` Does Not Guarantee the Exact Event Post-Image

`fullDocument:"updateLookup"` can return a majority-committed state **newer** than the state immediately after that event if the document was modified again. Accurate replay requires understanding `updateDescription`, pre/post images when supported, versions, and ordering.

### 10.2. Delete Events

Delete events typically provide `documentKey` and do not automatically include the full deleted document. The target must process deletes/tombstones by stable key and order; otherwise, an older backfill batch can recreate the document.

## 11. Durable Checkpoints and At-Least-Once Delivery

~~~text
Receive event E
  → Validate/transform
  → Apply to target durably
  → Persist token/checkpoint for E
  → Advance progress
~~~

Checkpointing before applying to the target can lose an event after a crash. Applying to the target before saving the token can cause the event to be replayed; therefore, the applicator needs **idempotent operations** or an atomic checkpoint+apply if supported within the same transaction boundary.

### 11.1. Tokens Are Opaque BSON

Do not manually unpack a token into a timestamp and use it like another resume token. Store it in its exact form/source/namespace and handle token invalidation and oplog gaps with pause + alert + resync.

### 11.2. Parallel Processing

If event E102 fails while E103 has already been applied, the checkpoint must not advance past E102 if restarting would skip E102. Maintain a **contiguous applied watermark** and per-aggregate-key ordering.

## 12. Preventing Stale Backfill from Overwriting Newer CDC

Scenario:

~~~text
Backfill reads revision 7
CDC applies revision 9 to v2
Backfill revision 7 arrives late
~~~

An unconditional replace will regress v2's version. Rule:

~~~text
incoming > stored → apply
incoming = stored → replay/no-op if canonical payload matches
incoming < stored → skip stale
same revision but different content → report conflict
~~~

### 12.1. CAS for an Existing Target Document

~~~javascript
const incoming = toV2(sourceDocument);
const result = db.orders_v2.replaceOne(
  {
    _id: incoming._id,
    revision: { $lt: incoming.revision }
  },
  incoming
);
~~~

If `matchedCount=0`, the target may not exist yet or may have an equal/higher version. You need insert-if-absent with a unique `_id`, version checks, and race handling. Do not blindly attach `upsert:true` to a versioned filter: when the document already has a newer version, an upsert can try to insert the same `_id` again and hit E11000.

### 12.2. Tombstones Prevent Resurrection

~~~javascript
{
  _id: "O-1001",
  deleted: true,
  revision: NumberLong(10)
}
~~~

A stale update at revision 7 must not be applied over tombstone 10. Delete events do not inherently carry a revision in every schema; the migration must define sequence/ordering and tombstone retention covering the replay window.

## 13. Dual Writes vs. Single Authority + CDC

A pattern with a clear source of authority:

~~~text
App writes authoritative v1
    → durable change/outbox
         → idempotent apply v2
~~~

If the app sends two direct writes to **two clusters**, v1 can succeed while v2 times out. There is no default cross-cluster MongoDB transaction making them atomic; you need durable retries/reconciliation and a policy defining business success.

### 13.1. Do Not Drift into Two Sources of Truth

Two services writing independently to v1 and v2 can cause split-brain. Even with dual writes, you must define the authoritative path, partial-write handling, per-key ordering, and idempotency.

### 13.2. Event Deduplication Differs from HTTP Request Deduplication

A CDC event can replay after a crash; a checkout request can also be retried by a user after a timeout. You must distinguish event identity from the business operation/request ID.

## 14. Shadow Reads: Compare Without Serving v2

~~~mermaid
flowchart LR
    Req["Client"] --> API["Backend"]
    API --> Old["v1 read"]
    API -.-> New["v2 shadow read"]
    Old --> Response["Response"]
    Old -.-> Compare["Canonical diff"]
    New --> Compare
    Compare --> Metrics["Metrics + redacted samples"]
~~~

Rules:

- Users still receive **v1 output**.
- v2 reads are sampled and bounded by timeout and concurrency.
- Preserve the exact same tenant filter, projection, sort, and authorization context.
- Compare canonical business representations rather than raw JSON.
- Do not log PII/tokens/payment payloads; log hashed IDs, revisions, paths, and approved metadata.
- Shadow reads should be async/bounded so v2 does not degrade v1 p99 latency.

### 14.1. Shadow Does Not Create a Distributed Snapshot

Two near-simultaneous reads can still observe different revisions due to CDC lag. Comparisons must account for **expected lag** instead of flagging every diff as data corruption.

## 15. Node.js Canonical Comparison

~~~javascript
function canonicalOrder(doc, isOld) {
  if (!doc) return null;
  return {
    id: doc._id,
    tenant: doc.tenantId,
    money: String(isOld ? doc.amountCents : doc.totalMinor),
    status: isOld
      ? String(doc.state).toUpperCase()
      : doc.status,
    revision: String(doc.revision)
  };
}

async function compareOne(oldColl, newColl, tenantId, id) {
  const filter = { _id: id, tenantId };
  const [oldDoc, newDoc] = await Promise.all([
    oldColl.findOne(filter), newColl.findOne(filter)
  ]);
  const left = canonicalOrder(oldDoc, true);
  const right = canonicalOrder(newDoc, false);
  return {
    equal: JSON.stringify(left) === JSON.stringify(right),
    oldRevision: left?.revision ?? null,
    newRevision: right?.revision ?? null
  };
}
~~~

This is only a demo using an object with fixed field ordering from the canonical function. Production must handle ObjectId, Decimal128, timestamps, arrays, null/missing values, and money without converting to imprecise floating-point types.

### 15.1. Classifying Diffs

- v1 revision > v2: target is likely lagging.
- Same revision but different content: suspect mapper bug or data corruption.
- v2 revision > v1 while v1 is still authoritative: suspect an unauthorized target writer.
- Record missing on one side: inspect checkpoints, deletes, and backfill.

## 16. Canonicalization by Business Contract

| Component | Rules to Decide |
|---|---|
| Money | Units, Decimal128, rounding, currency |
| Timestamp | UTC/millisecond precision, null semantics |
| Status | Exhaustive mapping, unknown states |
| Strings | Case/Unicode normalization only when permitted |
| Arrays | Is order significant or is it a set? |
| IDs | Stable IDs/mapping |
| Missing/null | Are they equivalent? |
| Deletes | Tombstone and visibility policy |
| Metadata | Intentionally ignore migration-only fields |

Do not over-normalize in ways that hide bugs: if the business distinguishes `"ABC"` from `"abc"`, lower-casing both masks a real mismatch.

## 17. Monitoring Drift Beyond Counts

| Category | Metric | What It Checks |
|---|---|---|
| Key parity | Missing IDs, extra IDs | Same set of records at a verified watermark? |
| Revision parity | Target behind/ahead | Lagging or out-of-policy writer? |
| Content parity | Canonical mismatch at same revision | Is the mapping accurate? |
| Delete parity | Pending deletes, resurrected IDs | Deleted records are not recreated |
| CDC health | Checkpoint age, capture/apply lag, dead letters | Is the pipeline keeping up? |
| Business invariant | Money totals, uniqueness, status transitions | Any business rules violated? |
| Performance | p95/p99, CPU, I/O, connection pool wait | Does target meet SLOs? |
| Safety | Old writer attempts, routing epoch conflicts | Any split-brain writes? |

### 17.1. Equal Counts Do Not Prove Equal Data

~~~text
v1 IDs = {A, B, C}
v2 IDs = {A, B, D}
~~~

Both sides have count=3, yet C is missing and D is extra. Even when IDs match, money or status can still differ.

### 17.2. Bucketed Reconciliation

Partition by `tenantId`, shard, `_id` range, or creation date. Each bucket tracks source count, target count, missing/extra IDs, canonical checksum, and mismatch count. Isolate only mismatched buckets to reconcile instead of rescanning the entire collection each time.

### 17.3. Sampling vs. Full Coverage

Shadow sampling provides early signals but does not prove every document is correct. Before a critical cutover, consider full deterministic reconciliation or risk-appropriate coverage. Measure both coverage percentage and the age of reconciliation results.

## 18. Watermarks and Replication Lag

A simple model:

~~~text
sourceWatermark = latest acknowledged source change
targetWatermark = latest contiguous change durably applied on v2
lag = defined distance between the two marks
~~~

Do not arbitrarily subtract timestamps from two hosts with clock skew, or treat cluster times from two independent MongoDB clusters as a single shared clock without an explicit mapping.

### 18.1. Four Types of Lag

1. Capture lag: committed on source, not yet read by listener.
2. Queue lag: captured, waiting for worker.
3. Apply lag: not yet committed on target.
4. Visibility lag: present on target, not yet visible to API/secondary/cache.

Zero queue lag does not automatically guarantee **read-your-writes** on the customer read path.

### 18.2. Contiguous Applied Watermark

A worker processes E101, E102, E103. If E103 finishes while E102 is still failing, do not checkpoint past E102 if restarting would drop E102.

### 18.3. Per-Key Skew

A continuously updated order can stay behind even when overall pipeline p50 lag is low. Monitor tail latency, hot keys, failure queues, and critical tenants.

## 19. Meaningful Reconciliation Checks

In the lab:

~~~javascript
const dbLab = db.getSiblingDB("migration_lab");
print(dbLab.orders_v1.countDocuments({ tenantId: "t-01" }));
print(dbLab.orders_v2.countDocuments({ tenantId: "t-01" }));
~~~

Counting at two different instants while writes are active is only a **preliminary signal**. Verification must be anchored to a watermark or a stable dataset.

### 19.1. Aggregation by Business Status

~~~javascript
db.orders_v2.aggregate([
  { $match: { tenantId: "t-01" } },
  {
    $group: {
      _id: "$status",
      count: { $sum: 1 },
      sumTotalMinor: { $sum: "$totalMinor" }
    }
  },
  { $sort: { _id: 1 } }
]);
~~~

Compare against the canonical v1 aggregation at the **same boundary**; do not conclude money was lost while v1 continues accepting new orders before v2 catches up.

### 19.2. Business Invariants

- No lost `tenantId` and no changed currency units.
- No statuses undefined in the mapper.
- Unique business keys such as `(tenantId,orderNo)` remain enforced.
- No confirmed order missing a ledger entry.
- No accidental record deletions from mismatched TTL or validators.
- No duplicate payments caused by CDC/retries.

### 19.3. Metadata and Sharding

The target must have the right indexes, unique/partial index constraints, collation, validators, TTL, and roles. When changing the shard key or topology, cluster-wide uniqueness and routing behavior can change; verify unique index rules against the actual server and shard key.

## 20. Classify Mismatches Before Fixing

| Type | Example | Action |
|---|---|---|
| Expected lag | v1 revision 9, v2 revision 8, event E9 still queued | Wait within budget / alert if overdue |
| Missing target | ID A absent after watermark | Targeted backfill/replay |
| Extra target | v1 deleted B, v2 still has B | Replay delete/tombstone |
| Same-revision difference | Same revision but different amount | PAUSE cutover, inspect mapper |
| Target ahead | v2 revision 10, v1 9 while v1 authoritative | Track down unauthorized writer |
| Unknown state | `state:"refunded"` not mapped yet | Quarantine + migration rule |
| Precision mismatch | Date/Decimal converted improperly | Fix normalization/transform |
| Transient count mismatch | Data changed during count | Compare at the same watermark |

### 20.1. Do Not Arbitrarily Pick Last-Write-Wins

For payments, inventory, and workflows, "higher timestamp wins" can hide double charges or invalid cancellations. Reconciliation must follow domain rules with an audit trail, review, and a kill switch for automated repairs.

### 20.2. Repairs Must Also Be Idempotent

A reconciliation worker can crash and retry; preserve stable IDs, version guards, and a repair log. Do not turn a reconciliation script into an unguarded third writer with no authority.

## 21. GO/NO-GO Gates

An **illustrative-only** threshold set:

~~~yaml
cutoverGates:
  checkpointHealthy: true
  maxP99ApplyLagSeconds: 2
  missingKeysAtVerifiedWatermark: 0
  sameRevisionCanonicalMismatch: 0
  unknownStateMappings: 0
  targetIndexesReady: true
  maxP95LatencyRegressionPercent: 10
  oldWriterFencingReady: true
  rollbackRehearsalPassed: true
~~~

Do not treat 2 seconds and 10% as production defaults. Thresholds must come from SLA/read consistency requirements, business risk, and throughput.

### 21.1. Metric Freshness and Coverage

A dead exporter can make a dashboard show 0 errors. Gates must check measurement age, tenant/shard coverage, sample counts, and collector health. **Missing telemetry must never count as PASS**.

### 21.2. Not Just Averages

A 1% canary might touch only one healthy shard. Track p95/p99 by cohort, read path, update/delete operations, and rare document shapes.

### 21.3. Auto-Pause

If lag rises continuously, checkpoints stall, same-revision mismatches appear, or target p99 degrades: halt rollout expansion, revert canary reads to v1 if safe, investigate, and reconcile before resuming.

## 22. Canary Reads by Stable Cohort

~~~text
0%  v2 reads: shadow only
1%  v2 reads: internal/low-risk users
5%  v2 reads: representative cohort
25% v2 reads: expand after gates pass
50% v2 reads: monitor per shard/tenant
100% v2 reads: only when consistency contract allows
~~~

Percentages are illustrative, not a mandatory schedule.

### 22.1. Sticky Routing

Use a stable hash of tenant/user and rollout salt to select the cohort. If a user randomly reads v1 on one request and v2 on the next, CDC lag can make the UI "flicker." Never allow the frontend to set `source=v2` and bypass authorization.

### 22.2. Read-Your-Writes

If a POST writes to v1 successfully and an immediate GET is canary-routed to v2, the GET might not see the order yet. Options:

1. Route post-write reads to v1 for a short session window or until target reaches the watermark.
2. Wait for v2 catch-up to the operation watermark within a deadline.
3. Exclude read paths requiring immediate consistency from read canary.
4. Shift authority per tenant via a dedicated atomic/fencing protocol, if needed.

Low average CDC lag **does not imply** every request has a read-your-writes guarantee.

### 22.3. Read Canary Differs from Write Canary

Serving 5% of reads from v2 while writes remain on v1 is relatively easy to revert. Sending 5% of writes to v2 can create two authoritative paths unless per-aggregate/per-tenant routing and synchronization are rigorously engineered.

## 23. Feature Flags and Routing Epochs

A control-plane configuration might look like:

~~~text
routingMode = V1_ONLY | SHADOW_V2 | V2_READ_CANARY | V2_PRIMARY
readCanaryPercent = 5
cutoverEpoch = 42
~~~

Java illustration:

~~~java
enum RoutingMode {
    V1_ONLY, SHADOW_V2, V2_READ_CANARY, V2_PRIMARY
}

// Pseudocode: security, repositories, and lifecycle are managed separately.
Order readOrder(String tenantId, String id, RoutingConfig cfg) {
    if (cfg.mode() == RoutingMode.V1_ONLY) {
        return readV1(tenantId, id);
    }
    if (cfg.mode() == RoutingMode.SHADOW_V2) {
        scheduleBoundedShadowCompare(tenantId, id);
        return readV1(tenantId, id);
    }
    if (cfg.mode() == RoutingMode.V2_READ_CANARY &&
            !isStableCanaryTenant(tenantId, cfg.canaryPercent())) {
        return readV1(tenantId, id);
    }
    return readV2(tenantId, id);
}
~~~

### 23.1. Feature Flags Do Not Stop In-Flight Writes

When a flag flips, an older request may have already selected v1 and still be executing. A worker with cached config can also keep running. Write cutover requires drain/fencing/permission enforcement honored by **all write paths**.

### 23.2. Audit Config Changes

Record config revision, epoch, percentage, tenant cohort, approver, timestamp, instances that received the config, and rollback reason.

## 24. Switching Write Authority: Safe Sequence

A reference runbook:

1. Freeze unrelated deploys/configs; announce cutover.
2. Confirm CDC v1→v2 is healthy and parity gates pass.
3. Pause write admission or accept into a **durable queue** with explicit deadlines and ack policies.
4. Drain in-flight v1 writes; reconcile requests with unknown outcomes.
5. Fence old writers, including APIs, background consumers, cron jobs, and admin scripts.
6. Record source watermark W.
7. Wait for v2 to fully apply all changes through W, including deletes and relevant transactions.
8. Run final parity/invariant checks at the defined boundary.
9. Flip the routing epoch so v2 becomes authoritative.
10. Open new writes to v2; validate with stable request IDs and smoke tests.
11. Ramp traffic per plan while keeping reverse-sync capability and monitoring active.

### 24.1. Fencing Is Not Just a Flag

`cutoverEpoch=42` on a dashboard does not stop a scheduled script with direct credentials from writing to v1. Enforce fencing at the write gateway, lease protocol, network permissions, or policy layer that every writer must pass through; simultaneously monitor attempts from old epochs.

### 24.2. Never Use `Thread.sleep(30000)` as a Gate

Waiting 30 seconds does not prove queues are empty or the target has applied everything. Use observed state: in-flight requests, acknowledged writes, watermarks, checksums, and deadlines.

### 24.3. True Durable Queuing

If the application returns success before a request is durably persisted, a crash can lose an acknowledged write. Define when the queue acknowledges, how backpressure behaves, and how timeouts are handled.

## 25. Cutover Watermark: Timeline Diagram

~~~mermaid
sequenceDiagram
    participant API as Write ingress
    participant V1 as MongoDB v1
    participant CDC as CDC worker
    participant V2 as MongoDB v2
    API->>API: Pause/drain
    API->>V1: Complete inflight writes
    V1-->>API: Acknowledged outcomes
    API->>CDC: Capture source watermark W
    CDC->>V2: Apply through W
    V2-->>CDC: Durable apply + parity
    CDC-->>API: Target caught up to W
    API->>API: Fence old writers, flip epoch
    API->>V2: Resume write traffic
~~~

### 25.1. Unknown Outcomes

A command that returned a timeout may still have committed on v1. Do not assume it failed when locking the watermark: inspect the idempotency ledger, request identity, or source state per business contract.

### 25.2. Writes Blocked During Cutover

If ingress rejects requests, return errors with a clear retry policy; if queuing, the queue must be durable and bounded so the system does not lose requests it accepted responsibility for.

### 25.3. After Opening v2 Writes

If smoke tests fail, rollback is **no longer a simple flag flip** once any new write has been acknowledged on v2. You must execute the post-cutover rollback plan.

## 26. Monitoring After v2 Accepts Writes

100% reads and writes on v2 still does not mean the migration is over:

- Reconcile **new writes**, not just backfilled historical data.
- Monitor reverse-sync backlog if the rollback plan requires it.
- Alert on old-writer attempts and changes outside the allowed epoch.
- Keep the source and compatibility code through the rollback window.
- Verify performance, index plans, p95/p99, error rates, and resource budgets.
- Cut over caches, search, event consumers, reports, and data warehouse.
- Maintain backups/PITR and updated runbooks.

### 26.1. Do Not Drop the Old Source Immediately

v1 remains valuable for rollback, auditing, and drift investigation. Remove it only when no dependencies remain, the rollback window has ended, post-cutover gates have passed, and approvals are granted.

### 26.2. Do Not Treat Snapshot Restore as a Traffic-Undo Button

Restoring a snapshot can wipe valid writes committed after the backup time. A data rollback must account for **acknowledged writes created after cutover**, not merely restore an old image.

## 27. Scoping Rollback Properly

There are four layers:

1. **Traffic rollback:** revert read/write routing to the old path.
2. **Application rollback:** deploy the previous code version.
3. **Data rollback:** ensure the old source contains all required new changes.
4. **Infrastructure rollback:** restore DNS, networking, credentials, endpoints, or clusters.

### 27.1. Before Write Cutover

While v1 is still authoritative and canary only reads from v2, turning off canary and returning reads to v1 is usually straightforward, provided v2 had no unintended side effects.

### 27.2. After Write Cutover

An order is acknowledged on v2 at 10:05 but does not exist on v1. Reverting reads/writes to v1 at 10:06 makes that order vanish for the customer. You must reverse-sync/reconcile or forward-fix based on an explicit RPO/RTO decision.

### 27.3. Contract / Source Removal

Once the old schema is removed, new features may no longer map backward. Full rollback may require complex data transformation or become infeasible; treat contract as a **nearly irreversible milestone** absent specialized recovery.

## 28. Rollback Matrix by Phase

| Phase | Actionable Steps | Complexity |
|---|---|---|
| BACKFILL | Stop job, keep v1 authoritative | Low |
| SHADOW | Disable shadow, stay on v1 | Low |
| READ_CANARY | Revert reads to v1, inspect caches | Low–medium |
| WRITE_CUTOVER | Fence writes, reverse-sync v2→v1, verify | High |
| STABILIZE | Reconcile new writes, backward compatibility | High |
| CONTRACT | Forward-fix/rebuild/restore depending on capability | Very high |

Do not collapse all of these into a single "Rollback" button without checking whether new writes have occurred on v2.

## 29. Reverse CDC to Preserve Rollback Readiness

Before cutover:

~~~text
v1 authoritative → CDC v1→v2
~~~

After cutover (if rollback readiness is required):

~~~text
v2 authoritative → reverse CDC v2→v1
~~~

Reverse sync requires deterministic reverse transforms, stable IDs, revision mapping, idempotent apply, ordered events, tombstones, checkpoint lag tracking, and dead-letter handling.

### 29.1. Preventing Replication Feedback Loops

If both streams blindly mirror every update, a v2→v1 event can trigger a v1→v2 event and loop infinitely. Tag origin/epoch, disable the non-authoritative direction, or use a tested loop-suppression protocol.

### 29.2. Encoding New States

v2 has `PARTIALLY_REFUNDED` whereas v1 does not understand it. A reverse transform cannot be lossless without an extended representation. Options: feature-freeze new states until the rollback window ends, store supplemental data, expand the v1 schema, or accept a controlled forward-fix policy.

### 29.3. Backlog Sizing

If the reverse queue holds 20 million events, "roll back in 5 minutes" may be unrealistic. Measure apply throughput, bandwidth, target index pressure, and backlog aging before cutover.

## 30. Rollback Runbook After Writes on v2

1. Declare an incident; designate an incident commander, communication channel, and rollback vs. forward-fix decision.
2. Halt traffic ramp; pause or queue writes with strict durability and deadline policies.
3. Fence v2 writes at the current epoch to establish a boundary.
4. Capture the watermark of **all acknowledged writes on v2**; reconcile unknown outcomes.
5. Run reverse CDC/replay through the watermark or perform controlled data repair.
6. Reconcile IDs, revisions, business fields, deletes, and invariants on v1.
7. Verify v1 indexes, validators, query plans, and compatibility with the rolled-back code.
8. Only after gates pass, switch authority/routing back to v1 and confirm old/new writers do not overlap.
9. Reopen traffic in small cohorts / emergency plan; monitor error rates and latency.
10. Keep v2 and logs for investigation—do not drop them immediately; record any unresolved request IDs.

### 30.1. If Reverse Sync Cannot Catch Up in Time

Do not flip back to v1 merely out of time pressure. You may keep v2 and switch to read-only mode, restrict features, or forward-fix; the choice depends on approved RPO/RTO. Accepting loss of acknowledged writes must be an **explicitly approved data-impact decision**, never a routine operational shortcut.

### 30.2. Caches and Downstream State

Rolling back MongoDB routing does not automatically invalidate Redis caches, search indexes, warehouse snapshots, or event consumers reading v2. The runbook must switch, version, or invalidate those derived read models as well.

## 31. RPO, RTO, and the Rollback Window

- **RPO:** maximum acceptable data loss during recovery.
- **RTO:** maximum acceptable time to restore service.
- **Rollback window:** the period during which sufficient source data, compatibility, CDC history, recovery capacity, and staffing remain available to roll back.

Example **not to be taken as defaults**:

~~~text
RPO: zero acknowledged orders lost
RTO: 15 minutes read-only at most
Rollback window: 72 hours after cutover
~~~

### 31.1. RPO=0 Cannot Be Achieved by 15-Minute Backups

Restoring a backup older than acknowledged writes loses data. RPO=0 requires mechanisms that preserve all acknowledged writes within a provable scope and topology.

### 31.2. Keeping v1 for 72 Hours Is Not Enough

If v1 stops receiving reverse changes, it grows progressively staler. A rollback window requires **synchronized data, runbooks, compatible code, and replay capacity**.

## 32. When Is Forward-Fix Better Than Rollback?

| Scenario | Considerations |
|---|---|
| v2 missing an index that can be built/fixed quickly | Forward-fix can be far lower risk than reversing millions of writes |
| One field mapped incorrectly but source records exist | Pause/repair target + verify may suffice |
| v2 already holds states unrepresentable in v1 | Rollback risks losing information |
| Prolonged v2 outage with v1 already reverse-synced | Watermark-based rollback may fit |
| Signs of double charges or missing ledger entries | Business incident; halt sensitive flows and reconcile |

The decision is not based on latency alone. Weigh data-loss risk, external side effects outside MongoDB, RPO/RTO, compatibility, and real recovery time.

## 33. Cross-Cluster and Sharding Considerations

Two clusters can differ in server version/FCV, indexes, shard keys, chunk distribution, TLS, roles, timeouts, read/write concerns, and cross-region network latency.

### 33.1. No Default Cross-Cluster Atomic Commit

A source write can succeed while the target write fails. With direct dual writes, the app must handle partial success; a durable outbox/CDC with a single clear authority is usually easier to verify.

### 33.2. Cluster Times and Resume Tokens

Do not treat source `clusterTime` as a universal shared clock or apply a source resume token to a target stream. Define migration checkpoints on the source stream and map applied progress on the target.

### 33.3. Shard Keys and Uniqueness

Changing the shard key can alter query routing and unique index constraints. Copying documents alone is not enough; test uniqueness, chunk distribution, cross-shard query latency, and data access through `mongos`.

## 34. Consumers Dependent on the Old Schema

Commonly overlooked dependencies:

- Redis caches and materialized views.
- Search indexing and CDC consumers.
- Warehouse ETL and BI dashboards.
- Outbox/event schemas and notification services.
- Legacy scheduled workers with hardcoded collection names.
- Export scripts or BI accounts granted read access only on v1.

### 34.1. Everything Is Part of the Cutover

An API reading v2 while reports still read v1 can produce conflicting business numbers. Inventory all readers and writers, migrate them in sequence, and reconcile outputs.

### 34.2. Do Not Blindly Dual-Publish Business Events

A single logical order update might emit on both v1 and v2 change streams; if Kafka consumers process both, side effects can duplicate. Enforce event identity, schema versions, and deduplication.

## 35. Signals to Pause the Rollout

| Signal | Reason |
|---|---|
| CDC checkpoint not advancing | Worker failure / poison event |
| Insufficient oplog retention | History gap, resume failure |
| Target behind growing continuously | Pipeline no longer catching up |
| Same-revision mismatch | Mapping/transform bug |
| Target ahead while v1 authoritative | Out-of-policy writer |
| Delete resurrection | Tombstone/ordering bug |
| Unexpected old writers after cutover | Split-brain authority |
| p99 or error rate spike | SLO impact |
| Missing unique index or duplicate IDs | Business invariant unprotected |
| Loss of metric freshness | Insufficient evidence for GO |

Do not "auto-heal" with last-write-wins before authority is established. Pause, preserve diagnostic metadata/redacted samples, trace root cause, and reconcile.

## 36. What Should the Dashboard Cover?

~~~text
Traffic:
  read_v1/read_v2, write_v1/write_v2, canary cohort, routing epoch
Data:
  missing_keys, extra_keys, canonical_mismatch, target_revision_ahead
  target_revision_behind, pending_deletes, business_invariants
Pipeline:
  capture_lag, queue_depth, apply_lag, checkpoint_age
  retry_count, poison_events, oplog_window_remaining
Application:
  errors, p95/p99, timeouts, connection_pool_wait
Safety:
  old_writer_attempts, in_flight_writes, reverse_sync_lag
~~~

### 36.1. Slice by Tenant and Shard

System-wide averages can hide failures affecting a critical tenant or a single shard. Label metrics by cohort, deployment version, writer type, namespace, and cluster for investigation.

### 36.2. Missing Metrics Are Not Success

If an exporter fails, 0 mismatches may simply mean no data is arriving. Gates must fail closed if fresh samples are missing.

## 37. Pre-Cutover Runbook

1. Verify cluster IDs, namespaces, credentials, owners, and recovery contacts.
2. Check latest backups/PITR and run an appropriate restore drill.
3. Verify backfill/CDC checkpoints and oplog headroom.
4. Check key parity, canonical content, deletes, and business invariants.
5. Verify target indexes, validators, TTL, and read/write concerns.
6. Run synthetic API checks against v2 with non-sensitive data.
7. Pass shadow and canary SLO gates.
8. Test feature-flag rollback while writes are still on v1.
9. Rehearse write drain, fencing, and reverse sync.
10. Document GO/NO-GO status, approvers, and the freeze window.

### 37.1. Evidence to Archive

Config revision, canary cohort, binary versions, source/target watermarks, parity report, open issues, rollback drill result, throughput estimates, and responsible owners.

## 38. Write Cutover Runbook

~~~text
1. Declare cutover started
2. Pause admission or durable queue
3. Drain source writes; reconcile uncertain outcomes
4. Fence old writers
5. Record source watermark W
6. Wait for target catch-up to W
7. Verify parity/invariants at W
8. Set v2 authoritative routing epoch
9. Controlled new writes with stable request IDs
10. Reopen traffic and monitor
~~~

### 38.1. If Failing Before Step 8

Do not open v2 write traffic. Keep/reopen v1 per protocol and process queued/rejected requests. Investigate checkpoints or mismatches.

### 38.2. If Failing After Step 9

Acknowledged writes may already exist on v2. Execute the **post-write-cutover rollback plan** instead of flipping the flag back to v1 immediately.

## 39. Stabilization Phase and Exit Criteria

During the first days after cutover:

1. Monitor read/write latency p50/p95/p99, error rates, connection pools, CPU, I/O, and slow query plans.
2. Reconcile both historical records and **writes created only after cutover**.
3. Verify CDC/reverse CDC if required by the rollback plan, including checkpoint age and tombstones.
4. Alert on old-writer attempts, unauthorized target writes, and routing epoch conflicts.
5. Check tenant isolation, financial totals, status transitions, and business reports.
6. Track search/cache/warehouse consistency and event consumers.
7. Keep the old source, compatibility code, and rollback owners active throughout the rollback window.
8. Do not enable irreversible schema/business features unless reverse transforms are ready.

### 39.1. When Can You CONTRACT?

Remove the old schema/source only when:

- No writers or consumers still depend on v1.
- The rollback window has elapsed or explicit sign-off is given.
- Zero unresolved mismatches or unknown business outcomes remain.
- SLOs have remained stable under representative workloads.
- Dedicated backups/PITR and a disaster recovery plan exist for v2.
- Docs, runbooks, monitoring, and ownership have moved to the new system.

### 39.2. Removing the Source Is an Independent Change

Do not bundle "switch reads," "switch writes," and "drop v1" into one unstoppable deployment. Cleanup should be a separate change step with review, retention checks, and backup approval.

## 40. Rehearsing Rollback Before Production

In staging or a representative test cluster:

1. Populate v1 with historical records, including edge-case states, deletes, and revisions.
2. Enable CDC, run backfill, and verify parity.
3. Enable shadow reads, then canary reads.
4. Execute write cutover with drain/watermark/fencing.
5. Generate **new confirmed orders on v2** that did not exist in the original v1 dataset.
6. Simulate a severe v2 failure.
7. Capture the v2 acknowledged watermark and run reverse CDC.
8. Reconcile that v1 has all new orders, updates, and deletes.
9. Switch authority back to v1 and reopen reads/writes under control.
10. Verify zero lost acknowledged orders, zero duplicate ledger entries, and zero resurrected deletes.
11. Measure replay duration and incident workflow against RTO/RPO.

### 40.1. Test Correctness, Not Just Counts

If v1 has the expected document count after rollback but a `SHIPPED` order regressed to `PAID`, the rehearsal **failed**. Compare canonical fields and revisions, not just row counts.

### 40.2. Test Operations

The runbook must be executable by on-call engineers with realistic permissions. Rehearse credentials, feature-flag propagation, cache invalidation, and dashboards—not just MongoDB commands.

## 41. Fault Injection: Crashes at Critical Points

| Crash Point | Expected Post-Restart Behavior |
|---|---|
| Before target apply | Event remains in stream/queue and is reprocessed |
| After target apply, before checkpoint | Event may replay without duplicating side effects |
| After durable checkpoint | No committed event lost and no prior event skipped |
| During delete handling | No record resurrection from older backfill |
| After newer revision, before stale backfill | Revision does not regress |
| During read canary | Can safely fall back to v1 per safety policy |
| After write cutover, before reverse catch-up | Do not declare rollback safe yet |
| While old writer remains active | Attempt is fenced or detected and reconciled |

### 41.1. Testing Lost Stream History

In an authorized test environment, simulate pausing CDC until history is no longer resumable. Expected behavior is **PAUSE + ALERT + RESYNC**, never silently skipping the gap.

### 41.2. Testing Network Partitions

If the application loses connectivity after a source commit but before receiving the response, the outcome may be unknown. Reconcile via a stable `requestId`/ledger before retrying a side-effecting command.

### 41.3. Testing CDC in a Sharded Cluster

Test across chunk migrations, topology failovers, stream resumes, and `mongos` routing. Do not assume a standalone `mongod` test proves cross-shard behavior.

## 42. The "Cannot Roll Back with a Flag Alone" Scenario

Suppose:

~~~text
10:00 v1 authoritative; v2 caught up
10:01 write cutover -> v2 authoritative
10:05 v2 receives 5,000 new orders, acknowledged successfully
10:06 target p99 spikes due to a missing index
10:07 proposal to switch source from v2 back to v1
~~~

If v1 lacks those 5,000 new orders, flipping back to v1 makes the API fail to find them. One option:

1. Stop v2 writes cleanly and record a final watermark.
2. Reverse-sync the new orders, updates, and deletes to v1.
3. Verify unique/foreign keys and canonical parity.
4. Only after v1 is ready, switch writes and reads back to v1.

Another option is to keep v2 authoritative and **forward-fix the index**, if doing so is safer and faster than reverse replay. Base the decision on RPO/RTO, business correctness, and real recovery capability—not whichever button is fastest on the dashboard.

## 43. Lessons on Transactions and Consistency

### 43.1. Same Deployment Does Not Mean Every Cutover Is Atomic

MongoDB transactions can commit multiple data writes together within one deployment, but flipping a routing flag across hundreds of service instances **is not itself a MongoDB transaction**. In-flight requests, cached configs, and external consumers still require coordination.

### 43.2. Two Clusters Do Not Have an Automatic Distributed Snapshot

Reading v1 and v2 almost simultaneously does not guarantee both reflect the same logical time. Compare against a source watermark and versioned records rather than treating a `Promise.all` call as a snapshot.

### 43.3. Majority Does Not Replace Event Ordering

Write concern `majority` is a replication acknowledgement/durability policy; it does not prevent a late stale event from overwriting newer state on the target. Version guards, per-key sequencing, and checkpoints remain essential.

### 43.4. Backups Do Not Replace CDC

Snapshots and PITR serve recovery; they do not automatically capture every change during a live backfill. Choose copy and capture mechanisms tailored to your topology and RPO target.

## 44. Exercise A — Design the State Machine

Diagram the phases PREPARE, BACKFILL, CATCH_UP, SHADOW, CANARY_READ, WRITE_CUTOVER, STABILIZE, CONTRACT. For each phase, specify:

- Source of truth.
- Read path.
- Write path.
- CDC direction.
- GO/NO-GO criteria.
- Whether rollback requires reverse sync.

## 45. Exercise B — Schema Mapping

Given v1 with `amountCents`/`state` and v2 with `totalMinor`/`status`, write a deterministic mapping preserving money, ID, tenant, and revision. Add the case where v1 has an unmapped `state:"refunded"`; how should it be handled without silently defaulting to PENDING?

## 46. Exercise C — Backfill and CDC

Backfill takes 2 hours while the source generates 200 changes per minute. Calculate the illustrative total changes and explain the risk if the change stream is opened only after the copy completes. Design pre-backfill checkpointing and revision-guarded idempotent replay.

## 47. Exercise D — Checkpoint After Crash

CDC successfully applies E10 to v2 and crashes before persisting the resume token. Upon restart, E10 is redelivered. What outcome is expected? Conversely, what can happen if the checkpoint is persisted before applying E10 to the target?

## 48. Exercise E — Stale Revision Arriving Late

CDC writes order revision 9, and later a backfill batch containing revision 7 reaches the target. Why does unconditional replace cause a regression? Write CAS/skip/no-op logic for incoming revisions smaller than, equal to, and greater than the current revision.

## 49. Exercise F — Delete Resurrection

The source deleted order O-10. The target receives the delete, yet an older backfill batch still containing O-10 is in flight. Propose a tombstone/version sequence to prevent recreating the order. What must be designed if the change stream delete event carries no explicit version?

## 50. Exercise G — Shadow Canary

Design a 1% shadow GET orders experiment and 5% canary reads. Requirements:

- Return v1 responses in shadow mode, v2 responses in selected canary cohorts.
- Canonical diff covering money/status/ID.
- Redacted logging and bounded shadow timeouts.
- Sticky cohort by tenant.
- Measure read-your-writes violations.

## 51. Exercise H — Deceptive Count Parity

Both collections have 1 million documents, yet 300 IDs in v1 are missing from v2 and 300 different IDs in v2 do not exist in v1. Create a bucket-partitioning / key-comparison / canonical-hash plan to locate the drift. Why would a count-only dashboard miss this?

## 52. Exercise I — GO/NO-GO Decision

Suppose:

~~~text
CDC p99 lag = 1.2s
Same revision diffs = 0
Missing keys = 0
Target p99 latency = 2x baseline
Rollback rehearsal = incomplete
~~~

Should you switch 100% of writes to v2 immediately? Name at least two failed gates, how to pause, and how to investigate.

## 53. Exercise J — Old Writer After Cutover

API pods have switched to v2, yet a legacy cron job keeps writing to v1 for 10 minutes. Identify the split-brain risk, how to detect old-writer attempts, fencing mechanisms, and how to reconcile leaked writes without corrupting newer v2 writes.

## 54. Exercise K — Rollback After v2 Commits

v2 has already received 5,000 acknowledged orders. Someone wants to flip the feature flag back to v1 immediately. Write a runbook preserving those 5,000 orders and verifying the reverse-sync watermark. If v2 only suffers slow queries due to a missing index, when is a forward-fix better than rolling back?

## 55. Exercise L — Lossy Reverse Transform

v2 allows `PARTIALLY_REFUNDED`, while v1 only knows PAID/REFUNDED. List three approaches to preserve rollback readiness and the consequences if v1 has no way to represent the new state.

## 56. Exercise M — Fault Injection

Simulate failures at three points:

1. After target write, before checkpoint.
2. During delete handling, before the tombstone is durably stored.
3. After cutover, before reverse CDC catches up.

For each scenario, state the postconditions to verify after recovery.

## 57. Exercise N — Observability Plan

Design a dashboard covering:

- Read/write traffic by v1/v2 and routing epoch.
- Capture/apply lag, checkpoint age, and oplog headroom.
- Missing/extra keys, same-revision mismatches, and target ahead.
- Old-writer attempts, tombstones, and rollback sync lag.
- API p95/p99, timeout/error rates, and business invariants.

Define at least one auto-pause threshold and one scenario where the incident commander must decide between rollback and forward-fix.

## 58. Suggested Exercise Solutions

**A:** Before WRITE_CUTOVER, v1 is authoritative so read rollbacks usually do not require reverse sync; after WRITE_CUTOVER, v2 is authoritative and reverting writes to v1 is only safe once new data is reverse-synced and reconciled.

**B:** Mapping preserves stable `_id`/tenant/revision/money units; unknown statuses must quarantine and alert, and mappings should be expanded with tests rather than applying misleading defaults.

**C:** 2 hours × 60 minutes × 200 changes/minute = **24,000 changes** (illustrative). CDC must start from before the scan window; opening it afterward risks losing intermediate changes.

**D:** Applying and crashing before saving the token replays E10; an idempotency guard prevents duplicate business effects. Checkpointing before applying risks dropping E10 completely.

**E:** Unconditional replace regresses v2 9→7. For incoming smaller: skip; equal: no-op if canonically equal, otherwise conflict; larger: CAS apply.

**F:** A tombstone carries a sequence/revision higher than the stale backfill record; delete events lacking revisions need a sequencing/ordering protocol to establish authoritative order.

**G:** Shadow does not affect HTTP responses; canary uses stable cohorts and enforces consistency checks. Comparisons need canonical fields + watermarks and must never log PII.

**H:** Equal counts can hide distinct key sets; partition ranges and compare missing/extra IDs plus content hashes/canonical fields at a verified watermark.

**I:** NO-GO because p99 regression and the rollback rehearsal failed; pause rollout, investigate query/index/network issues, run the rollback rehearsal, and re-measure.

**J:** An old writer creates writes on a non-authoritative source; fence/deny by epoch/permissions, measure leaked writes, and reconcile using business ordering without blindly overwriting v2.

**K:** Never flip back to v1 missing 5,000 acknowledged orders; fence v2, reverse-sync to a watermark, verify keys/revisions/invariants, then cut back. If only an index is missing and can be built safely and fast, forward-fix carries less risk.

**L:** Feature-freeze new states during the rollback window, extend the v1 schema or store supplemental representation, or choose forward-fix; never claim a reverse transform is lossless when v1 cannot represent the state.

**M:** Replay must not duplicate effects; deletes must not resurrect; rollback must preserve all acknowledged writes created on v2.

**N:** Dashboards need freshness/coverage checks and alerts; pause and investigate when lag/mismatch/latency exceeds gates. Business invariant breaches such as double charges or lost confirmed orders require an incident and formal approved resolution.

## 59. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Opening CDC only after copy finishes | Lost writes during copy | Start capture before backfill |
| Comparing counts only | Hidden missing/extra IDs | Key and content parity |
| Unversioned backfill replaces | Overwriting newer state | CAS/version guard |
| Checkpointing before apply | Events dropped after crash | Durable apply then checkpoint |
| Advancing parallel checkpoint by fastest worker | Failing events skipped | Contiguous watermark |
| Dropping delete events | Resurrected documents | Tombstones / ordered deletes |
| Using untrusted `updatedAt` as authority | Wrong business last-write-wins | Monotonic version / domain policy |
| Blocking shadow queries | v1 p99 spike | Bounded async shadow |
| Comparing raw JSON across schemas | False mismatches | Canonical comparison |
| Logging PII in shadow diffs | Data leak | Redact/hash IDs and fields |
| Per-request random canary | Inconsistent UI | Sticky cohorts |
| Ignoring read-your-writes | Missing record right after POST | Route to v1 / wait for watermark |
| Dual writes without clear authority | Divergence | Single authority + CDC/outbox |
| Flag flip without draining | In-flight old writes | Fencing / watermark |
| Forgetting scheduled writers | Split-brain | Inventory/fence all write paths |
| Treating missing metrics as green | Premature cutover | Monitor freshness and coverage |
| Treating snapshot restore as full rollback | Lost post-snapshot writes | Reverse sync / RPO |
| Flipping back to v1 after v2 commits | Disappearing acknowledged data | Reverse-sync before flipping |
| Bidirectional mirroring without loop suppression | Replication storm | Epoch/origin loop suppression |
| Dropping v1 as soon as reads hit 100% v2 | No fallback path | Contract only after rollback window |
| Reverse transform omitting new states | Information loss | Compatibility / forward-fix |

## 60. Review Questions

**1. Does finishing data copy mean the migration is complete?** — No; you still have CDC, parity, cutover, stabilization, and rollback readiness.

**2. What is a source of truth?** — The authoritative data path designated to confirm and resolve business writes.

**3. How does backfill differ from CDC?** — Backfill copies historical data; CDC captures ongoing changes.

**4. Why start CDC before backfill?** — To avoid missing events occurring during the scan window.

**5. Do change streams automatically copy all prior history?** — No.

**6. Why must the resume token be persisted after apply?** — To avoid checkpointing past an event not yet durably written to the target.

**7. Why must event application be idempotent?** — Crashes can cause events to be replayed.

**8. Does `updateLookup` always return the exact per-event post-image?** — No; it may reflect a newer state.

**9. How should stale backfill arriving after newer CDC be handled?** — Compare revisions and skip/CAS rather than overwriting.

**10. What is delete resurrection?** — A deleted record being recreated by a stale event or backfill batch.

**11. Do equal v1/v2 counts prove parity?** — No.

**12. What should you do on a same-revision mismatch?** — Pause cutover and investigate transforms and consistency.

**13. Is target-ahead concerning while v1 is authoritative?** — Yes; it can indicate an unauthorized writer or split-brain.

**14. What are shadow reads?** — Querying v2 for comparison while still returning v1 to users.

**15. How does a read canary differ from a write canary?** — A write canary changes authority and is much harder to roll back.

**16. Is read-your-writes automatic when writes hit v1 and reads hit v2?** — Not when CDC is asynchronous.

**17. Do all old writers stop once a routing flag changes?** — No; fencing, draining, and verification are required.

**18. What is the source watermark for?** — Defining all source changes that must exist on the target before cutover.

**19. Why is rollback after write cutover complex?** — v2 already holds acknowledged writes that v1 does not yet have.

**20. Does PITR snapshot restore preserve writes after the snapshot?** — No.

**21. What must reverse CDC guard against?** — Out-of-order events, duplicates, deletes, data loss, and feedback loops.

**22. What is forward-fix?** — Repairing v2 and keeping it authoritative instead of reverting traffic and data to v1.

**23. What does RPO=0 mean?** — Zero tolerated loss of acknowledged writes within the defined scope.

**24. Does the end of the rollback window mean v1 can be dropped immediately?** — Only after verifying dependencies, stabilization, backups, and approvals.

**25. Is zero lag enough for GO?** — No; parity, invariants, performance, and observability health must also pass.

## 61. Quick Reference

| Concept | Rule |
|---|---|
| Expand | App tolerates both old and new schemas |
| Backfill | Checkpointed scan of historical data |
| CDC | Live change tracking and replay |
| Source of truth | One clear write authority per phase |
| Shadow | Compare v2 while serving v1 |
| Canary | Live cohort reading v2 |
| Sticky cohort | Deterministic hash routing by tenant/user |
| Read-your-writes | Route to source or wait for watermark |
| Revision guard | Never overwrite newer data with stale data |
| Tombstone | Prevent deleted records from resurrecting |
| Resume token | Opaque stream checkpoint |
| Contiguous watermark | Do not skip failing events under parallel apply |
| Canonical diff | Compare by business schema |
| Write cutover | Drain → fence → W → catch-up → parity → flip |
| GO/NO-GO gate | Correctness, lag, performance, and readiness |
| Reverse CDC | Sync v2→v1 after switching authority |
| Rollback window | Retain data, code, CDC, and runbook to revert |
| Forward-fix | Fix v2 when rollback is riskier |
| RPO/RTO | Acceptable data loss / recovery duration |
| Contract | Remove old path after stabilization |

## 62. Production Implementation Checklist

- [ ] Are source/target namespaces, clusters, and owners defined?
- [ ] Are all writers, readers, consumers, and dependencies inventoried?
- [ ] Are schema mappings, reverse mappings, and unique business IDs clear?
- [ ] Are monotonic revisions/sequences and delete semantics designed?
- [ ] Are target indexes, validators, TTL, collation, and permissions created?
- [ ] Does backfill support batching, checkpoints, resume, and idempotent apply?
- [ ] Does CDC cover the full backfill window with sufficient oplog history?
- [ ] Are resume tokens persisted after durable apply?
- [ ] Do applicators preserve per-key ordering and contiguous progress?
- [ ] Do tombstones prevent stale resurrection?
- [ ] Are unknown mappings and target-ahead conflicts quarantined?
- [ ] Is key/content parity measured at a logical watermark?
- [ ] Are business invariants on money, status, and uniqueness verified?
- [ ] Do metrics enforce sample freshness, tenant/shard coverage, and alerts?
- [ ] Are shadow reads async, bounded, and free of PII logs?
- [ ] Does canary use sticky cohorts with p95/p99 monitoring?
- [ ] Is the read-your-writes policy tested?
- [ ] Are GO/NO-GO gates explicit, with owners empowered to halt rollout?
- [ ] Has read rollback been tested while writes stay on v1?
- [ ] Is a write drain/queue plan ready with durability and deadlines?
- [ ] Have all old writers, including scripts and cron jobs, been identified and fenced?
- [ ] Is cutover watermark W captured and target apply verified through W?
- [ ] Are requests with unknown commit outcomes reconciled?
- [ ] Is reverse CDC sufficient to protect newly acknowledged v2 writes?
- [ ] Does the reverse transform handle new schema features, or are they frozen?
- [ ] Have rollback window, RPO/RTO, and replay throughput been verified?
- [ ] Are post-cutover runbooks, cache invalidation, and downstream migrations ready?
- [ ] Have crash/replay, deletes, out-of-order, and split-brain drills been executed?
- [ ] Are dedicated v2 backups/PITR and a disaster recovery plan in place?
- [ ] Is v1 cleanup gated on zero remaining dependencies and explicit approval?

## 63. Conclusion

In MongoDB data evolution, **traffic shifting is more than swapping a connection string or collection name**. It is the process of transferring responsibility for where a business write is acknowledged, where sufficiently fresh data is read from, and how the system responds if part of the migration fails. Shadow and canary phases can shift reads gradually, but write cutover demands **a single authority, drain/fencing, a watermark, and parity verification**.

A new copy is trustworthy only when measured by **key parity, canonical fields, revisions, deletes, CDC lag, business invariants, and SLOs**—not document counts alone. Change streams, resume tokens, and checkpoints bridge backfill with live writes, yet you must still handle event replay, oplog gaps, out-of-order delivery, and stale backfill.

Finally, **rollback must preserve every newly acknowledged business write created after cutover**. Once v2 has accepted writes, returning to v1 may require reverse synchronization and reconciliation; at times, forward-fix is safer. Complete the contract phase and drop v1 only when compatibility, the rollback window, downstream consumers, backups, and recovery plans have been verified through drills and operational evidence.
