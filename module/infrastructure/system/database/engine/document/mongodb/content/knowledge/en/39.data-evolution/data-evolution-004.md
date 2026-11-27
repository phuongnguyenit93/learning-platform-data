# Batched Backfill with Rate Limiting, Checkpoints, and Resumability in MongoDB

## 1. The Problem: Adding a New Field to Millions of Documents While the App Stays Online

An e-commerce system uses MongoDB to store orders. Legacy schema:

```javascript
{
  _id: ObjectId("673400000000000000000001"),
  tenantId: "shop-a",
  status: "PAID",
  lineItemsRevision: NumberLong("7"),
  lineItems: [
    { sku: "P01", quantity: 2, unitPriceMinor: NumberLong("125000") },
    { sku: "P02", quantity: 1, unitPriceMinor: NumberLong("80000") }
  ],
  createdAt: ISODate("2026-10-01T10:00:00Z")
}
```

The new application version wants to quickly read **the item subtotal before shipping, tax, and discounts**. It needs the `itemsSubtotalMinor` field:

```javascript
{
  _id: ObjectId("673400000000000000000001"),
  lineItemsRevision: NumberLong("7"),
  lineItems: [
    { sku: "P01", quantity: 2, unitPriceMinor: NumberLong("125000") },
    { sku: "P02", quantity: 1, unitPriceMinor: NumberLong("80000") }
  ],
  itemsSubtotalMinor: NumberLong("330000"),
  migrations: {
    orderItemsSubtotalV2: {
      version: 2,
      sourceRevision: NumberLong("7"),
      calculatedAt: ISODate("2026-11-14T06:00:00Z")
    }
  }
}
```

Formula:

\[
\text{itemsSubtotalMinor} = \sum_{i=1}^{n} \text{quantity}_i \times \text{unitPriceMinor}_i
\]

Here `unitPriceMinor` is the smallest currency unit defined by the system; the example calculates only the line-item sum and **does not** claim to be the final collectible amount. Using `NumberLong` also avoids floating-point rounding errors. With large quantities, Java must check for overflow using `Math.multiplyExact` and `Math.addExact`.

The application runs 24/7, continuously creating and updating orders. The collection holds 40 million documents. You cannot shut down the system and run an unguarded `updateMany()` without addressing:

- Documents having varying structures or missing legacy fields.
- Orders being edited while the migration runs.
- The backfill taking hours or days.
- Network drops mid-batch.
- Primary elections occurring mid-run.
- Production needing stable read/write latency.
- Pausing, resuming, and redeploying workers without double-counting totals.
- Completing a single scan without guaranteeing every new or concurrently modified document has been processed.

**Solution:** a backfill with **bounded batch sizes**, **pacing/rate limiting**, **durable checkpoints**, **idempotent updates**, **optimistic concurrency**, and **reconciliation** before shifting all traffic onto the new schema.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Place backfills within **expand → deploy compatible writers → backfill → verify → contract**.
2. Scan using **keyset pagination** with a stable sort order and suitable index.
3. Distinguish `cursor.batchSize()`, `limit()`, operation count in `bulkWrite()`, and rate limiting.
4. Prove a migration is **idempotent** across retries and duplicate batch deliveries.
5. Design **high-water mark checkpoints**, `lastScannedId`, progress state, and job ownership.
6. Handle crashes between data writes and checkpoints under at-least-once processing.
7. Maintain correctness under concurrent app updates using revision/CAS or a compatible dual-write protocol.
8. Estimate throughput, choose docs/s or bytes/s budgets, and throttle down when latency or replication lag rises.
9. Write a Java Sync Driver worker implementing batching, rate limiting, and MongoDB checkpointing.
10. Classify transient/permanent/unknown errors, set retry budgets, and handle poison documents.
11. Track progress with metrics, verify post-migration invariants, and design rollback/forward-fix plans.
12. Contrast backfills on replica sets, sharded clusters, and Atlas regarding routing, lag, and durability guarantees.

**Scope:** database name `migration_lab_426` is used strictly for testing. Data-mutating commands in this lesson **must never run in production** without a change plan, backup/PITR, approved privileges, and testing against realistic workloads.

## 3. What Is a Backfill, and How Does It Differ from a Schema Migration?

A **schema migration** changes the shape or semantics of data an application reads and writes. A **backfill** populates or updates existing data to conform to a new schema or read model.

Example:

```text
Old:
  orders.lineItems

New:
  orders.lineItems
  orders.itemsSubtotalMinor
  orders.migrations.orderItemsSubtotalV2

Backfill:
  scan old orders
  compute new value
  conditionally write new fields
  verify
```

Backfills differ from:

- **Backup/restore:** copying or restoring snapshots without necessarily altering schema.
- **One-time DDL:** creating indexes/validators, which may be required yet does not populate old records.
- **Online query transforms:** computing the new field on read without persisting it.
- **Change Data Capture (CDC):** streaming ongoing changes; can pair with a backfill for catch-up.
- **Batch ETL:** moving data between sources/targets; if targeting MongoDB, still needs idempotency/checkpoints.
- **Full collection rewrite:** rewriting entire documents; rarely the right default when adding only a few fields.

### 3.1. When Is a Backfill Unnecessary?

If the new field can be computed on read at acceptable cost, or only new documents need the field, updating all historical documents may be unnecessary.

Example:

```java
long subtotal = order.containsKey("itemsSubtotalMinor")
    ? order.getLong("itemsSubtotalMinor")
    : computeFromLineItems(order);
```

This read fallback enables gradual rollout; however, measure its cost, define how long to keep the fallback, and avoid accumulating hard-to-maintain branches.

### 3.2. Not Every Backfill Is Safe

A backfill that deletes old fields, changes currency semantics, miscalculates taxes, or mutates finalized historical records can cause damage. Define the target field's semantics and calculation proof before running.

## 4. The Big Picture: Expand → Backfill → Verify → Contract

```text
    Phase 0: Plan & backup
              |
              v
    Phase 1: Expand schema
       - app reads old/new
       - add new fields/indexes
       - validators allow transition
              |
              v
    Phase 2: Deploy compatible writers
       - writes maintain new fields
       - source revision changes
       - optional CDC/outbox
              |
              v
    Phase 3: Rate-limited backfill
       - keyset scan
       - CAS update
       - checkpoint after each completed batch
              |
              v
    Phase 4: Reconcile
       - new & concurrently edited docs
       - missing/stale/invalid values
       - DLQ handling
              |
              v
    Phase 5: Verify & switch reads
              |
              v
    Phase 6: Contract
       - require new schema when safe
       - retire old fallback
       - keep rollback evidence
```

### 4.1. Why Update the Application Before Backfilling?

If the worker finishes computing subtotal and then an old app updates `lineItems` **without updating subtotal or revision**, the new data becomes stale even though the job reported completion.

Therefore, enforce one of these policies:

1. **Dual-write:** application writers update the source and new fields atomically in the same document.
2. **Invalidate-and-recompute:** writers increment the source revision and unset/mark the computed field stale; workers recompute.
3. **CDC + catch-up:** capture writes during and after the scan window with no gaps, then apply derived updates in order/idempotently.
4. **Approved maintenance freeze:** temporarily pause conflicting writes; rarely viable for always-on systems.

### 4.2. Do Not Remove Read Fallbacks Too Early

Older documents may still await backfill or sit in poison-data triage. The application must support mixed data throughout transition.

### 4.3. Do Not Treat `status=COMPLETED` as Verification Proof

A job checkpoint only proves scanning reached a cutoff per protocol. It does not guarantee the new field is accurate across all active records or that every concurrent edit was reconciled.

## 5. Four Essential Properties

| Property | Meaning in Backfill | How to Achieve |
|---|---|---|
| **Bounded** | Each batch consumes bounded resources | `limit()`, bounded bulk, timeouts |
| **Throttled** | Never saturates all I/O and write capacity | docs/s, bytes/s, feedback controller |
| **Resumable** | Crash/restart never starts over from scratch | Durable checkpoint, ordered scan |
| **Idempotent** | Re-runs never cause double effects | Deterministic `$set`, revision CAS, unique IDs |

Three more crucial properties:

- **Observable:** visibility into batches, progress, errors, lag, throughput.
- **Correct under concurrency:** active writers are never overwritten by stale worker reads.
- **Verifiable:** an independent method to validate final results.

### 5.1. Checkpoints Do Not Automatically Give Exactly-Once

“Writing the batch” and “saving the checkpoint” are two separate operations:

```text
worker writes batch
        |
        X process crashes
        |
checkpoint not written
```

Upon restart, the batch runs again. This is **at-least-once processing**. The goal is making migration operations **safe to replay**, not pretending a batch executes only once.

### 5.2. “Executed Once” Differs from “Correct Final Result”

Calling `$set: {itemsSubtotalMinor:330000}` twice does not double the subtotal, yet if the source changed in between, writing the old value is still wrong. **Idempotency also requires guards against mutating sources.**

## 6. Designing the Migration Schema and Source Data

An order has:

```javascript
{
  _id: ObjectId("673400000000000000000001"),
  tenantId: "shop-a",
  lineItemsRevision: NumberLong("7"),
  lineItems: [
    { sku: "P01", quantity: 2, unitPriceMinor: NumberLong("125000") },
    { sku: "P02", quantity: 1, unitPriceMinor: NumberLong("80000") }
  ]
}
```

Business assumptions:

- `quantity` is a positive integer.
- `unitPriceMinor` is a non-negative 64-bit integer.
- `lineItemsRevision` always increments whenever `lineItems` changes.
- All writers capable of editing `lineItems` have been updated to obey the revision rule.
- The backfill **never** mutates `lineItems` or `lineItemsRevision`.
- `itemsSubtotalMinor` equals only the sum of `quantity × unitPriceMinor`, excluding tax/discount/shipping.
- New fields reside in the order document so single-document updates are atomic.

### 6.1. Why Is `lineItemsRevision` Needed?

The worker reads `revision=7` and computes the subtotal. While computing, the API updates `lineItems` and bumps `revision=8`. If the worker executes:

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $set: { itemsSubtotalMinor: 330000 } }
);
```

it can **overwrite a fresh value** with stale results computed from old data.

With a revision predicate:

```javascript
db.orders.updateOne(
  {
    _id: orderId,
    lineItemsRevision: NumberLong("7")
  },
  {
    $set: {
      itemsSubtotalMinor: NumberLong("330000"),
      "migrations.orderItemsSubtotalV2.version": 2,
      "migrations.orderItemsSubtotalV2.sourceRevision":
        NumberLong("7")
    },
    $currentDate: {
      "migrations.orderItemsSubtotalV2.calculatedAt": true
    }
  }
);
```

The command matches only while `revision` is still 7. If `revision` changed, the worker must **re-read and recompute**. This is **compare-and-set (CAS)** keyed on source state.

### 6.2. CAS Works Only If Every Writer Bumps Revision

If one code path edits `lineItems` without incrementing `lineItemsRevision`, the worker cannot detect the change. Never claim “CAS is enough” without enforcing and testing the invariant across every writer.

### 6.3. Legacy Documents Missing a Revision

Before using the CAS pattern, expand the schema to initialize revisions or adopt a different concurrency protocol.

Never assume missing `lineItemsRevision` equals `0` and filter `eq("lineItemsRevision",0)`; MongoDB distinguishes missing fields from `0`. You may need a pre-step stamping initial revisions with `$exists:false` while updating writers simultaneously.

### 6.4. Immutable Historical Data

If `PAID` orders are immutable snapshots and policy forbids editing `lineItems`, computation is simpler. Still, enforce that invariant in code and permissions rather than trusting the `status` string alone.

## 7. Defining Idempotency Clearly

An operation `f` is idempotent if applying it repeatedly to an unchanged source state yields the same desired target state:

\[
f(f(x)) = f(x)
\]

### 7.1. Safe to Replay

```javascript
// Same value from same sourceRevision:
db.orders.updateOne(
  { _id: orderId, lineItemsRevision: NumberLong("7") },
  {
    $set: {
      itemsSubtotalMinor: NumberLong("330000"),
      "migrations.orderItemsSubtotalV2.sourceRevision":
        NumberLong("7")
    }
  }
);
```

While the source remains at `revision=7`, re-running yields the exact same business fields.

### 7.2. Unsafe to Replay

```javascript
db.orders.updateOne(
  { _id: orderId },
  { $inc: { itemsSubtotalMinor: 330000 } }
);
```

Two executions add up to `660000`, corrupting the computed field.

### 7.3. Do Timestamps Break Idempotency?

`$currentDate` on `calculatedAt` changes metadata across retries without doubling the subtotal. Still, if **bitwise-identical state** or strict audit semantics are required, skip re-writing metadata on documents already at the matching revision.

### 7.4. Marker/Version

A marker can record:

```javascript
migrations: {
  orderItemsSubtotalV2: {
    version: 2,
    sourceRevision: NumberLong("7"),
    calculatedAt: ISODate("2026-11-14T06:00:00Z")
  }
}
```

The worker can skip when:

```text
marker.version == 2
AND marker.sourceRevision == order.lineItemsRevision
AND itemsSubtotalMinor has valid type/value
```

Markers are optimization/reconciliation aids, not substitutes for checking business invariants.

## 8. Backfill via `updateMany()`: When Is It Appropriate?

A simple default field:

```javascript
db.orders.updateMany(
  { archived: { $exists: false } },
  { $set: { archived: false } }
);
```

may be fine if `archived=false` holds for every document missing the field.

### 8.1. Why Not One `updateMany()` for Every Migration?

Across millions of documents:

- Hard to pace over time and rate limit.
- Hard to checkpoint progress.
- Some documents need per-record transformations across multiple fields.
- Data/validation errors make tracking which records need retry difficult.
- Concurrent updates require clear write-time predicates.

### 8.2. `updateMany()` Is Not One Giant Transaction

Each single-document update is atomic, yet `updateMany()` does not make the whole collection one atomic unit. If the command fails mid-way, some documents remain updated.

### 8.3. When Is `updateMany()` Still Good?

- Small, simple, idempotent changes with tight filters.
- Reasonable document counts where runtime/throttling is acceptable.
- Safely rerunnable and verifiable.
- Scan/index/write impacts are understood.

Not every migration requires a complex Java worker.

## 9. Batching: What Should a Batch Bound?

A worker loop can do:

```text
Read 100 documents
   |
Compute 100 new values
   |
Write 100 guarded updates
   |
Verify batch outcome
   |
Commit checkpoint
   |
Sleep/pacing
   |
Repeat
```

### 9.1. Different Types of Bounds

| Limit | Unit | Purpose |
|---|---|---|
| Scan page size | Documents/page | Worker RAM and memory footprint |
| Cursor batch size | Documents/fetch request, per server/size | Network round trips |
| Write bulk size | Write models/call | Network overhead and error handling |
| In-flight batches | Batches | Concurrency and backpressure |
| Write rate | Docs/s or ops/s | Protect MongoDB write capacity |
| Byte rate | MiB/s | Protect network/disk bandwidth |
| Deadline | Seconds | Avoid holding resources indefinitely |
| Checkpoint interval | Batches/time | Replay cost after a crash |

**`cursor.batchSize(100)` does not throttle writes to 100 ops/s.** It only controls cursor fetch chunking.

### 9.2. Batch 100 Example

```javascript
db.orders.find({
  _id: {
    $gt: ObjectId("673400000000000000000000"),
    $lte: ObjectId("6734ffffffffffffffffffff")
  }
}).sort({ _id: 1 })
  .limit(100)
  .batchSize(100);
```

This is only the read step; computation and writes follow separately. Never confuse `limit(100)` with “the entire job updates only 100 documents.”

### 9.3. Dynamic Batch Sizing

Start with 100 docs/batch and watch:

- p95/p99 write latency.
- Actual docs/s.
- Replication lag.
- CPU/disk IOPS and cache pressure.
- Conflict/retry rate.
- p95/p99 document size.

If overloaded, lower batch size/concurrency or rate limit; if headroom exists, scale up cautiously.

## 10. `skip()` Pagination Is Unsuitable for Large Scans

Example:

```javascript
db.orders.find().sort({ _id: 1 })
  .skip(10000000)
  .limit(100);
```

### 10.1. Problems

- Large offsets force the server to scan and discard many index entries.
- Inserts/deletes shift offset positions.
- On worker restart, numeric offsets poorly track exactly which documents were processed.

### 10.2. Use Keyset Pagination

```javascript
db.orders.find({
  _id: {
    $gt: lastScannedId,
    $lte: highWatermarkId
  }
}).sort({ _id: 1 }).limit(100);
```

After completing the batch, checkpoint `lastScannedId` as the last `_id` processed.

### 10.3. Why `_id` Usually Fits

`_id` has a default unique index and is immutable, allowing stable range scans/sorts if all documents share **the same suitable BSON type**.

### 10.4. BSON Type Pitfall

If a collection mixes `ObjectId`, `String`, and `NumberLong` in `_id`, BSON comparison ordering does not match chronological order and `getObjectId("_id")` will fail on other types.

Match the actual key schema or design a composite cursor. The Java example below **assumes `_id` is `ObjectId`**.

## 11. When to Use a Composite Keyset?

If migrating by `tenantId` and `createdAt`, many documents share identical timestamps, so checkpointing `createdAt` alone is unsafe.

### 11.1. Paired Sort Keys

```javascript
db.orders.createIndex({
  tenantId: 1,
  createdAt: 1,
  _id: 1
});
```

Querying one tenant:

```javascript
db.orders.find({
  tenantId: "shop-a",
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
}).sort({
  createdAt: 1,
  _id: 1
}).limit(100);
```

### 11.2. Checkpoint Must Store **Both Fields**

```javascript
{
  lastCreatedAt: ISODate("2026-10-01T10:00:00Z"),
  lastId: ObjectId("673400000000000000000001")
}
```

Storing only `lastCreatedAt` can skip documents sharing the boundary timestamp.

### 11.3. What If the Sort Key Changes?

Keyset pagination is safest when **the scan key is immutable throughout the scan**. If `createdAt` is edited, a document can jump ahead of or behind the cursor, causing skips or duplicate visits.

### 11.4. Tenant Partitioning

With many tenants, per-tenant/range checkpoints help scope work, yet require a global fairness/rate budget and non-overlapping ownership.

## 12. High-Water Mark: Bounding the Scan Range

In long backfills, lock in `highWatermarkId` at startup:

```text
Start:
  highWatermarkId = max(_id) observed
  lastScannedId   = null

Each batch:
  _id > lastScannedId
  _id <= highWatermarkId
```

### 12.1. Goals

- Establish a clear end boundary for the scan pass.
- Prevent continuous new inserts from making the loop run forever.
- Report progress toward a well-defined cutoff.

### 12.2. High-Water Mark Is Not a Consistent Snapshot

`max(_id)` at T0 fixes only **a key value**; it does not freeze data or guarantee every new document gets an `_id` above the cutoff.

For example, a process inserting a pre-generated `ObjectId` or custom ID can insert a new document below the cutoff after the cursor already passed that position.

### 12.3. Do Not Assume `ObjectId` Is a Global Commit Order

`ObjectId` embeds a timestamp component and generally increases over time, yet is not a global commit clock and does not prove **one write reached the DB before** another.

### 12.4. Closing the Gap

Pair with one of these mechanisms:

- Application writers populate valid target fields on all new/modified documents.
- A post-scan reconciliation pass.
- CDC/change streams with resume tokens and a cutover protocol.
- A purpose-built snapshot/handoff mechanism.

A high-water mark is solely a **scan boundary**, not proof the entire collection is migrated.

## 13. Checkpoints: What Information Should Be Stored?

Example `migrationProgress` collection:

```javascript
{
  _id: "orders-items-subtotal-v2:segment-000",
  migrationVersion: 2,
  collection: "orders",
  state: "RUNNING",
  highWatermarkId: ObjectId("6734ffffffffffffffffffff"),
  lastScannedId: ObjectId("673400000000000000000001"),
  scanKeyType: "ObjectId",
  processedDocuments: NumberLong("10000"),
  matchedUpdates: NumberLong("9980"),
  skippedUpToDate: NumberLong("20"),
  conflictedRetries: NumberLong("7"),
  updatedAt: ISODate("2026-11-14T06:00:00Z"),
  owner: "migration-worker-01",
  leaseEpoch: NumberLong("3")
}
```

### 13.1. Essential Fields

| Field | Role |
|---|---|
| `_id` | Fixed identity of the job/segment |
| `migrationVersion` | Identifies code logic/version |
| `state` | RUNNING, PAUSED, FAILED, SCAN_DONE, VERIFIED |
| `highWatermarkId` | Scan cutoff boundary |
| `lastScannedId` | Last key **fully processed** |
| `updatedAt` | Heartbeat/progress monitoring |
| `owner/leaseEpoch` | Prevents two workers from claiming the same job (if implemented) |

### 13.2. Distinguish Last Read from Last Committed

`lastReadId` only means a document was **read**. A proper `lastScannedId` checkpoint must mean **every document up to this key has been resolved** per protocol.

Writing the cursor after reading yet before updating causes crashes to skip unprocessed data.

### 13.3. Checkpoints Must Be Durable

Never keep `lastScannedId` solely in RAM or a container's ephemeral local file. Persist to durable storage (typically a dedicated MongoDB collection) with an appropriate write concern.

### 13.4. Checkpoints Do Not Replace Audits

A checkpoint is a progress marker. To track who ran the job, image versions, parameters, failures, and approvals, maintain separate execution metadata/audit logs.

## 14. Where to Write the Checkpoint: After or Before the Batch?

### 14.1. Wrong: Checkpoint Before

```text
Read batch IDs 101..200
Save lastScannedId=200
Process crashes before writes
Restart begins from 201

=> 101..200 are skipped.
```

### 14.2. Right: Checkpoint After Completion

```text
Read batch IDs 101..200
Apply guarded updates
Resolve retries/conflicts
Confirm batch outcome
Save lastScannedId=200

If crash after writes but before checkpoint:
  repeat 101..200 safely.
```

### 14.3. A Batch with 1 Error

If 99 documents succeed and 1 fails:

- **Do not advance the checkpoint past the failed document** as if the batch finished.
- Or persist a **durable, identified retry/DLQ record** and enforce that the job cannot reach `VERIFIED` until all retry records are resolved.

### 14.4. Atomicity Between Data and Checkpoint?

Transactions can make tiny batches atomic across documents, yet you rarely want to wrap millions of updates in heavy transactions.

The standard pattern is **at-least-once + idempotent guarded updates + post-batch checkpoint**. It recovers cleanly and avoids long-lived transaction overhead.

## 15. Checkpoint State Machine

```text
PENDING
   |
   v
RUNNING -----> PAUSED
   |             |
   |             +-----> RUNNING
   |
   +---- transient failure -> RETRYING -> RUNNING
   |
   +---- permanent error --> FAILED
   |
   v
SCAN_DONE
   |
   v
RECONCILING
   |
   +---- unresolved issues -> PAUSED/FAILED
   |
   v
VERIFIED
   |
   v
COMPLETED (application cutover approved)
```

### 15.1. State Names Are an Application Contract

MongoDB has no built-in knowledge of these states. They are a schema **defined by the migration worker**; enforce transitions so steps cannot skip validation.

### 15.2. `SCAN_DONE` Is Not `VERIFIED`

Completing a scan only means the cursor reached the cutoff key. You must still reconcile concurrent writes, poison records, new inserts, and business invariants.

### 15.3. Pause and Resume

Pausing should happen **between batches** or after safely handling/recording state. Stopping mid-batch is also fine on restart if updates are idempotent.

## 16. Ownership and Leases with Multiple Workers

If a scheduler malfunctions and launches two instances of the same job, both could read the same checkpoint.

### 16.1. Using a Lease

```javascript
{
  _id: "orders-items-subtotal-v2",
  owner: "worker-A",
  leaseUntil: ISODate("2026-11-14T06:10:00Z"),
  leaseEpoch: NumberLong("4"),
  state: "RUNNING"
}
```

A worker may claim the job only when:

- The job has no owner, **or**
- The lease expired under a consistent chosen clock mechanism, **or**
- The current owner renews its own lease.

### 16.2. Why Are Fencing Tokens Needed?

Worker A holds a lease, loses network connectivity, and the lease expires; Worker B claims `leaseEpoch=5`. Worker A wakes up and tries to checkpoint—without checking `leaseEpoch`, A could overwrite B's progress.

Checkpoint updates should filter on:

```javascript
{
  _id: jobId,
  owner: workerId,
  leaseEpoch: expectedEpoch,
  lastScannedId: previousId
}
```

If `matchedCount=0`, the worker **lost ownership or the checkpoint moved**; stop immediately instead of updating blindly.

### 16.3. Leases Do Not Block All Stale Data Writes

Leases protect progress/ownership. A stalled Worker A waking up can still emit **data updates** if data writes lack fencing logic. Idempotent CAS reduces risk, though external side effects need extra safeguards.

### 16.4. One Worker May Be Enough

If a single worker meets the schedule, keeping one worker with a simple scheduler lock is less risky than fanning out 100 workers. Parallelize only when a bottleneck is proven.

## 17. Rate Limiting: Choosing Speed Based on Capacity

A backfill must not consume all CPU, disk, and network simply because millions of documents need updating.

### 17.1. Three Ways to Set a Budget

| Type | Example | When Useful |
|---|---|---|
| Docs/s | 300 docs/s | Documents are relatively uniform in size |
| Write ops/s | 100 updates/s | Each operation has roughly equal cost |
| Bytes/s | 4 MiB/s | Document/update sizes vary widely |

Also enforce a **concurrency cap**, because 1,000 sequential updates/s behaves very differently from 1,000 concurrent updates/s.

### 17.2. Estimating Duration

With 40 million documents at a sustained **300 docs/s**:

\[
\frac{40{,}000{,}000}{300} \approx 133{,}333 \text{ seconds}
\]

That equals roughly **37 hours** of pure processing, excluding initial scanning, conflicts, downtime, validation, dynamic throttling, or long-tail documents.

Never lock a cutover date based solely on this raw division.

### 17.3. Rate Limit Differs from Batch Size

```text
batchSize = 100
rateLimit = 300 docs/s

=> Can process at most ~3 batches/s
   if each document requires one write with no other delays.
```

If processing a batch takes 0.5 seconds, actual throughput will be lower than the rate limit. A rate limiter is a **ceiling**, not a guaranteed floor.

### 17.4. Avoid Sleeping Only After 10,000 Writes

A massive burst followed by a long sleep creates load spikes on primary/secondaries. Smooth pacing or a token bucket with bounded burst capacity is preferable.

### 17.5. Watch Write Lag Too

Backfills write to the primary and replicate to secondaries, raising replication lag and oplog pressure. If secondaries fall behind, throttle down even if primary write p95 still looks healthy.

## 18. Pacing, Token Buckets, and Adaptive Throttling

### 18.1. Fixed Pacing

A 200 docs/s limit permits starting one document roughly every:

\[
\Delta t = \frac{1}{200} = 0.005\,\text{s} = 5\,\text{ms}
\]

A single-threaded worker can wait until the next deadline before processing a document. This is **pacing**, not a full token bucket.

### 18.2. Token Bucket

```text
Tokens are refilled at 200 per second.
Bucket capacity = 50 tokens.
Each processed document consumes 1 token.
No tokens -> wait for refill.
```

A token bucket allows bursts up to `capacity`, useful when operation latency varies. Still, too large a capacity lets bursts cause latency spikes.

### 18.3. Global Limit vs. Per-Worker Limit

With 10 workers at 200 docs/s each, the cluster receives up to **2,000 docs/s**, not 200.

To enforce a cluster-wide limit:

- Partition the budget carefully across workers/shards, or
- Use a distributed limiter/central scheduler, or
- Use a feedback controller measuring total write load.

### 18.4. Adaptive Throttling

A simple policy:

```text
If API write p95 above threshold:
  reduce backfill limit by 50%

Else if replication lag too high:
  reduce backfill limit by 50%

Else if stable for 5 minutes:
  increase by 10%

Never exceed approved max.
```

This is a **design pattern**, not production-ready thresholds. Add hysteresis/cooldowns to avoid oscillating on noisy metrics.

### 18.5. Application Priority

Backfills are background maintenance. When resources tighten, prioritize **user-facing transactions** and keep error rates/SLOs healthy; the migration can slow down or pause.

## 19. Control Reads Too, Not Just Writes

### 19.1. Index-Friendly Scan

```javascript
db.orders.find({
  _id: { $gt: lastScannedId, $lte: highWatermarkId }
}).sort({ _id: 1 }).limit(100);
```

Because `_id` is indexed, this range/sort typically beats a full scan plus sort on large datasets; still verify with `explain("executionStats")` on realistic data.

### 19.2. Projection

If the scan step needs only IDs:

```javascript
db.orders.find(
  { _id: { $gt: lastScannedId, $lte: highWatermarkId } },
  { _id: 1 }
).sort({ _id: 1 }).limit(100);
```

The worker can re-fetch each document by ID right before CAS. This trims scan payload yet adds extra read calls. If documents are small/cold, reading source fields directly in the batch may be more efficient.

### 19.3. Scanning Full Documents vs. IDs-Only

| Read Pattern | Pros | Trade-Off |
|---|---|---|
| ID-only page then fetch each doc | Lightweight progress, easy conflict refetch | N+1 reads |
| Page with source fields | Fewer round trips | Larger stale gap before CAS |
| Long-lived stream cursor | Low pagination overhead | Cursor lifecycle, harder restarts |
| Batched aggregation pipeline | Offloads transform to server | Must manage server load/checkpoints |

Do not choose solely by query count; measure network bytes, IOPS, batch duration, and CAS conflicts.

### 19.4. Secondary Reads Can Be Stale

Reading sources from secondaries to offload the primary can observe stale data. Revision CAS on the primary still prevents overwriting fresh updates **if the revision invariant holds**, yet conflicts/retries can rise and progress tracking gets trickier.

For migrations requiring fresh state, pick a read strategy aligned with correctness requirements rather than routing all reads to secondaries blindly.

## 20. Bulk Writes: Ordered vs. Unordered

The Java Sync Driver supports:

```java
collection.bulkWrite(
    java.util.List.of(
        new com.mongodb.client.model.UpdateOneModel<>(
            com.mongodb.client.model.Filters.eq("_id", id1),
            com.mongodb.client.model.Updates.set("migrated", true)),
        new com.mongodb.client.model.UpdateOneModel<>(
            com.mongodb.client.model.Filters.eq("_id", id2),
            com.mongodb.client.model.Updates.set("migrated", true))
    ),
    new com.mongodb.client.model.BulkWriteOptions()
        .ordered(false)
);
```

### 20.1. `ordered(true)`

Executes operations in input order; a write error halts remaining operations. Predictable ordering, though potentially less efficient on large or sharded batches.

### 20.2. `ordered(false)`

Operations may execute out of order, and independent non-failing operations proceed even if one errors. Appropriate when:

- Updates are independent.
- Order does not matter.
- Identities and idempotency are clear.
- **Partial success** handling is implemented.

### 20.3. `bulkWrite()` Is Not Atomic Across the Batch

If part of a batch succeeds and the connection drops, you cannot assume nothing executed. Inspect per-document state or replay idempotent operations.

### 20.4. Why Not Commit Checkpoints Based Solely on Matched Count?

With CAS filters, `matchedCount=0` can mean:

- Source revision changed while the worker computed.
- The document was deleted.
- The document already holds the current marker.
- The filter schema had a bug.

Never lump “0 matches” into generic success or failure. Decide per invariant.

### 20.5. `updateMany` Inside Bulk Still Lacks Identical Retryability

Not every write operation is retryable at the protocol level; multi-updates generally lack the same retry semantics as eligible single-document writes. Even when the driver retries some commands, business-level idempotency remains mandatory.

## 21. Choosing Bulk vs. Individual `updateOne()`

| Criterion | Individual `updateOne` | `bulkWrite` of `UpdateOneModel` |
|---|---|---|
| Per-document recompute needed | Easy | Still possible |
| Per-document conflict handling | Very clear | Must map index/results |
| Network round trips | More | Fewer |
| Ordered/unordered partial success | Simpler | Must handle thoroughly |
| Halting on poison documents | Easy | May yield partial success |
| Smooth per-doc throttling | Easy | Usually group-level |
| High-throughput fit | Latency-dependent | Often better |

**Pragmatic strategy:** start with a simpler sequential worker at a conservative rate; if network round trips become the bottleneck, adopt guarded idempotent bulks with explicit partial-failure and checkpoint handling.

### 21.1. A Batch of 100 Need Not Be a Bulk of 100

You can scan 100 IDs, split into two bulks of 50, rate-limit each bulk, and commit the batch checkpoint only after both bulks resolve.

### 21.2. Update Models Do Not Need to Replace Entire Documents

Prefer `$set` on new fields and markers instead of full-document `replaceOne`. Full replacement from a stale snapshot easily wipes out changes on unrelated fields.

## 22. Java Sync Driver: Single-Process Worker with Durable Checkpoints

This section provides a **complete single-worker reference implementation** with explicit assumptions:

- Runs only against the **`migration_lab_426`** database, never production.
- All `orders._id` values have type `ObjectId`.
- `lineItemsRevision` is BSON Int64/Java `Long`, incremented whenever `lineItems` changes.
- `lineItems` holds an array of documents with positive Int32 `quantity` and non-negative Int64 `unitPriceMinor`.
- Application writers already implement dual-writes or revision invalidation.
- Only one worker runs for checkpoint `orders-items-subtotal-v2`; cluster-wide leasing is omitted from this sample.
- Illustrative target is **200 scanned documents/second**, single-threaded.
- All data and checkpoint writes use `WriteConcern.MAJORITY`.
- CAS retries are bounded; non-CAS MongoDB exceptions are not swallowed—the job halts and restarts replay the batch.

### 22.1. Java Imports and Setup

```java
import com.mongodb.WriteConcern;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.Projections;
import com.mongodb.client.model.Updates;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.types.ObjectId;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

public final class OrderSubtotalBackfill426 {
    private static final String DB = "migration_lab_426";
    private static final String JOB = "orders-items-subtotal-v2";
    private static final int PAGE_SIZE = 100;
    private static final int MAX_CAS_ATTEMPTS = 8;
    private static final int DOCS_PER_SECOND = 200;

    private final MongoCollection<Document> orders;
    private final MongoCollection<Document> progress;
    private final Pacer pacer = new Pacer(DOCS_PER_SECOND);

    public OrderSubtotalBackfill426(MongoClient client) {
        this.orders = client.getDatabase(DB)
            .getCollection("orders")
            .withWriteConcern(WriteConcern.MAJORITY);
        this.progress = client.getDatabase(DB)
            .getCollection("migrationProgress")
            .withWriteConcern(WriteConcern.MAJORITY);
    }

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI missing");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            new OrderSubtotalBackfill426(client).run();
        }
    }

    // Class body continues in the following sections.
}
```

Combine the snippets in Sections 22.2–22.7 into the **same `OrderSubtotalBackfill426` class**; they are split only for presentation, not as duplicate classes in one file.

### 22.2. One-Time Checkpoint Initialization

```java
private Document initializeCheckpoint() {
    // Lock in cutoff before starting a new scan.
    Document latest = orders.find()
        .sort(Sorts.descending("_id"))
        .projection(Projections.include("_id"))
        .limit(1)
        .first();

    if (latest == null) {
        // Example treats an empty namespace as separately reportable rather than a no-op.
        throw new IllegalStateException(
            "No orders in test namespace; seed test data first");
    }

    ObjectId proposedHigh = latest.getObjectId("_id");

    progress.updateOne(
        Filters.eq("_id", JOB),
        Updates.combine(
            Updates.setOnInsert("migrationVersion", 2),
            Updates.setOnInsert("state", "RUNNING"),
            Updates.setOnInsert("highWatermarkId", proposedHigh),
            Updates.setOnInsert("createdAt", new java.util.Date())
        ),
        new UpdateOptions().upsert(true)
    );

    Document cp = progress.find(Filters.eq("_id", JOB)).first();
    if (cp == null
            || !Integer.valueOf(2).equals(
                cp.getInteger("migrationVersion"))
            || cp.getObjectId("highWatermarkId") == null) {
        throw new IllegalStateException("Invalid checkpoint");
    }
    return cp;
}
```

**Note:** `setOnInsert` preserves the original cutoff across restarts because the checkpoint document already exists, which is desired. Production systems should define empty-collection behavior and handle resuming from `SCAN_DONE` explicitly.

### 22.3. Single-Threaded Pacer

```java
private static final class Pacer {
    private final long nanosBetweenPermits;
    private long nextAllowedNano = System.nanoTime();

    private Pacer(int permitsPerSecond) {
        if (permitsPerSecond <= 0) {
            throw new IllegalArgumentException("Invalid rate");
        }
        nanosBetweenPermits =
            Math.max(1L, TimeUnit.SECONDS.toNanos(1)
                / permitsPerSecond);
    }

    // Do not call concurrently from multiple threads.
    void awaitPermit() {
        long now = System.nanoTime();
        long remaining = nextAllowedNano - now;
        if (remaining > 0L) {
            LockSupport.parkNanos(remaining);
        }
        if (Thread.currentThread().isInterrupted()) {
            throw new IllegalStateException(
                "Backfill worker interrupted");
        }
        nextAllowedNano = Math.max(
            System.nanoTime(), nextAllowedNano)
                + nanosBetweenPermits;
    }
}
```

`Pacer` limits the **document-processing start rate** for a single-threaded worker, not a distributed quota on MongoDB write ops. Conflicts can trigger multiple reads, and real throughput depends on DB latency. Production systems should use battle-tested rate limiters with feedback control.

### 22.4. Computing Subtotal with Type and Overflow Checks

```java
private static long computeSubtotal(Document order) {
    Object raw = order.get("lineItems");
    if (!(raw instanceof List<?> items)) {
        throw new IllegalArgumentException(
            "lineItems missing or not an array");
    }

    long subtotal = 0L;
    for (Object rawItem : items) {
        if (!(rawItem instanceof Document item)) {
            throw new IllegalArgumentException(
                "line item not a Document");
        }

        Integer quantity = item.getInteger("quantity");
        Long unitPrice = item.getLong("unitPriceMinor");

        if (quantity == null || quantity <= 0
                || unitPrice == null || unitPrice < 0L) {
            throw new IllegalArgumentException(
                "Invalid quantity or unit price");
        }

        long lineTotal =
            Math.multiplyExact(quantity.longValue(), unitPrice);
        subtotal = Math.addExact(subtotal, lineTotal);
    }
    return subtotal;
}
```

On overflow or wrong types, **halt and investigate** rather than casting `Double` to `long` and accepting precision loss. Adapt validation to real monetary semantics (currency, decimal precision, discounts) before deployment.

### 22.5. Single Document: Fresh Read, CAS, Bounded Retries

```java
private void migrateOne(ObjectId id) {
    for (int attempt = 1; attempt <= MAX_CAS_ATTEMPTS; attempt++) {
        Document current = orders.find(eq("_id", id)).first();

        if (current == null) {
            // Document was legitimately deleted; do not recreate.
            return;
        }

        Long revision = current.getLong("lineItemsRevision");
        if (revision == null || revision < 0L) {
            throw new IllegalStateException(
                "Missing/invalid lineItemsRevision for " + id);
        }

        long subtotal = computeSubtotal(current);
        Document migrations = current.get(
            "migrations", Document.class);
        Document marker = migrations == null
            ? null
            : migrations.get("orderItemsSubtotalV2", Document.class);

        boolean upToDate = marker != null
            && Integer.valueOf(2).equals(marker.getInteger("version"))
            && revision.equals(marker.getLong("sourceRevision"))
            && Long.valueOf(subtotal)
                .equals(current.getLong("itemsSubtotalMinor"));

        if (upToDate) {
            return;
        }

        UpdateResult result = orders.updateOne(
            and(
                eq("_id", id),
                eq("lineItemsRevision", revision)
            ),
            combine(
                set("itemsSubtotalMinor", subtotal),
                set("migrations.orderItemsSubtotalV2.version", 2),
                set("migrations.orderItemsSubtotalV2.sourceRevision",
                    revision),
                currentDate(
                    "migrations.orderItemsSubtotalV2.calculatedAt")
            )
        );

        if (result.getMatchedCount() == 1L) {
            return;
        }
        // Source changed concurrently; refetch and recompute.
    }

    throw new IllegalStateException(
        "CAS conflicts exhausted for order " + id);
}
```

**Limitation:** right after confirming the marker is up to date, the source could change before `return`. **Writers must maintain or invalidate derived fields** per Phase 2 rules; you cannot rely solely on the worker's check to keep data fresh forever.

### 22.6. Scan One Page, Finish, Then Checkpoint

```java
private void scanLoop(Document initial) {
    ObjectId high = initial.getObjectId("highWatermarkId");
    ObjectId last = initial.getObjectId("lastScannedId");

    while (true) {
        var range = last == null
            ? lte("_id", high)
            : and(gt("_id", last), lte("_id", high));

        List<Document> batch = orders.find(range)
            .sort(Sorts.ascending("_id"))
            .projection(Projections.include("_id"))
            .limit(PAGE_SIZE)
            .batchSize(PAGE_SIZE)
            .into(new ArrayList<>());

        if (batch.isEmpty()) {
            UpdateResult done = progress.updateOne(
                and(
                    eq("_id", JOB),
                    eq("state", "RUNNING"),
                    eq("lastScannedId", last)
                ),
                combine(
                    set("state", "SCAN_DONE"),
                    currentDate("updatedAt")
                )
            );
            if (done.getMatchedCount() != 1L) {
                throw new IllegalStateException(
                    "Checkpoint ownership changed");
            }
            System.out.println("Scan finished. Reconcile before cutover.");
            return;
        }

        for (Document row : batch) {
            pacer.awaitPermit();
            migrateOne(row.getObjectId("_id"));
        }

        ObjectId end = batch.get(batch.size() - 1)
            .getObjectId("_id");

        UpdateResult saved = progress.updateOne(
            and(
                eq("_id", JOB),
                eq("state", "RUNNING"),
                eq("lastScannedId", last)
            ),
            combine(
                set("lastScannedId", end),
                inc("processedDocuments", batch.size()),
                currentDate("updatedAt")
            )
        );

        if (saved.getMatchedCount() != 1L) {
            throw new IllegalStateException(
                "Checkpoint moved; stop stale worker");
        }

        System.out.println(
            "Checkpoint saved up to " + end.toHexString());
        last = end;
    }
}
```

### 22.7. Entry Point `run()`

```java
public void run() {
    Document cp = initializeCheckpoint();
    String state = cp.getString("state");

    if ("SCAN_DONE".equals(state)) {
        System.out.println(
            "Already scanned. Run reconciliation/verification.");
        return;
    }
    if (!"RUNNING".equals(state)) {
        throw new IllegalStateException(
            "Job not RUNNING: " + state);
    }

    scanLoop(cp);
}
```

### 22.8. Why Can This Code Resume Safely After a Crash?

Suppose:

```text
Checkpoint = _id 100
Worker writes 101..180
Worker crashes before checkpoint 200

Restart:
  reads 101..200 again
  101..180 already have valid version+revision marker -> skip
  181..200 processed
  checkpoint moves to 200
```

No double increments occur because the worker uses deterministic `$set` and CAS.

### 22.9. When Is the Checkpoint **Not** Written?

- Invalid input data.
- Arithmetic overflow when computing subtotal.
- Exhausted CAS retries.
- Unresolved MongoDB write error or timeout.
- A document in the batch did not confirm completion.
- Job state or ownership changed.

In these cases, the worker fails and replays the batch on restart; never skip a poison document unless a durable exception workflow is explicitly defined.

### 22.10. Limitations to Address Before Production

The sample intentionally **omits**:

- Distributed leases/fencing for multiple workers.
- Durable per-document DLQ.
- Adaptive rate limiting and global budgets.
- Incremental CDC catch-up.
- Cancellation hooks and graceful pause commands.
- Detailed metrics/histograms.
- Configurable checkpoint namespaces and run manifests.
- Background reconciliation.
- Handling non-`ObjectId` `_id` types.
- Empty-collection no-op state.
- Post-`SCAN_DONE` recovery for concurrent/new documents.

It is an **illustrative, assumption-bounded foundation**, not a production-ready script to copy without preflight hardening.

## 23. Seeding Test Data for the Java Worker

Strictly in a fresh lab database, for example:

```javascript
use migration_lab_426;

db.orders.insertMany([
  {
    _id: ObjectId("673400000000000000000001"),
    tenantId: "shop-a",
    lineItemsRevision: NumberLong("1"),
    lineItems: [
      {
        sku: "P01",
        quantity: 2,
        unitPriceMinor: NumberLong("125000")
      },
      {
        sku: "P02",
        quantity: 1,
        unitPriceMinor: NumberLong("80000")
      }
    ]
  },
  {
    _id: ObjectId("673400000000000000000002"),
    tenantId: "shop-b",
    lineItemsRevision: NumberLong("3"),
    lineItems: [
      {
        sku: "P09",
        quantity: 3,
        unitPriceMinor: NumberLong("90000")
      }
    ]
  },
  {
    _id: ObjectId("673400000000000000000003"),
    tenantId: "shop-a",
    lineItemsRevision: NumberLong("2"),
    lineItems: []
  }
]);
```

Expected output:

| ID Suffix | Subtotal |
|---|---:|
| ...001 | 330000 |
| ...002 | 270000 |
| ...003 | 0 |

### 23.1. Do Not Reset Shared Databases by Dropping

This is a lab seed. If `migration_lab_426` contains colleagues' data, **never** call `dropDatabase()` carelessly. Use a run-specific namespace or an isolated test container.

### 23.2. Inspecting Markers

```javascript
db.orders.find(
  {},
  {
    lineItemsRevision: 1,
    itemsSubtotalMinor: 1,
    "migrations.orderItemsSubtotalV2": 1
  }
).sort({ _id: 1 });
```

### 23.3. Second Startup

Once a run reaches `SCAN_DONE`, restarting the worker immediately exits on `SCAN_DONE`. To test **mid-batch** replay, use a fault-injection lab before checkpointing and recover with a new process; never manually edit a production checkpoint's `state` to fake a test.

## 24. Re-Running the Full Job After `SCAN_DONE`

A clean design that **preserves old checkpoints** assigns a **new `runId`**:

```text
orders-items-subtotal-v2:run-2026-11-14-a
orders-items-subtotal-v2:run-2026-11-16-reconcile
```

### 24.1. Why Keep Run History?

Helps audit:

- Each run's cutoff.
- Number of documents processed.
- Start and end timestamps.
- Code version/checksum.
- Errors and skip approvals.
- Reconciliation and cutover evidence.

### 24.2. Re-Running the Migration Does Not Mean Reusing the Same Checkpoint

A `SCAN_DONE` run may need reconciliation over the live dataset; starting a fresh run or scanning missing/stale markers is better than blindly rewinding a production checkpoint.

### 24.3. Idempotent Updates Remain the Foundation

A new run must never double-count or overwrite fresher data. A new checkpoint does not create correctness by itself; deterministic transforms, revisions, and writer protocols do.

## 25. CAS Conflicts and Resolution

### 25.1. Timeline

```text
T0 worker reads order revision=7, subtotal=330000
T1 API updates lineItems, revision=8, subtotal=350000
T2 worker update where revision=7 -> matchedCount=0
T3 worker refetch revision=8
T4 worker compute subtotal=350000
T5 worker CAS where revision=8 -> success
```

### 25.2. Why Not Skip Conflicts Immediately?

If `matchedCount=0` simply advances `lastScannedId`, the document may still lack the derived field for its new revision.

### 25.3. Strategy

1. Bounded refetch/recompute.
2. If deleted, classify as a legitimate deletion.
3. If mutating too rapidly, defer and record a durable retry ID.
4. Never spin forever on one hot document and stall the whole job.
5. Reconcile all deferred IDs before transitioning to `VERIFIED`.

### 25.4. “Hot” Sources

A document updated hundreds of times per second causes constant CAS conflicts. Separate hot fields, rely on application dual-writes, or move hot items to a dedicated policy-driven queue rather than retrying infinitely.

## 26. Poison Documents and Durable Retry Queues

A failing document:

```javascript
{
  _id: ObjectId("673400000000000000000004"),
  lineItemsRevision: NumberLong("2"),
  lineItems: [
    { quantity: "many", unitPriceMinor: "100000" }
  ]
}
```

Java `getInteger("quantity")` hits a type mismatch; the migration must never guess `"many"` as a number.

### 26.1. Two Operational Modes

**Fail-fast:** halt the batch immediately without advancing the checkpoint. Advantage: zero skipped work, strong invariants.

**Continue-with-DLQ:** persist a durable record describing document ID, error category, retry policy, and source revision. Only after the DLQ write **is acknowledged** and policy allows does the checkpoint advance.

### 26.2. Example DLQ Schema

```javascript
{
  _id: "orders-items-subtotal-v2:673400000000000000000004",
  jobId: "orders-items-subtotal-v2",
  documentId: ObjectId("673400000000000000000004"),
  sourceRevision: NumberLong("2"),
  reasonCode: "INVALID_LINE_ITEM_TYPE",
  attempts: 1,
  state: "OPEN",
  recordedAt: ISODate("2026-11-14T06:30:00Z")
}
```

### 26.3. Do Not Log Entire Raw Documents Into DLQ

Documents may carry PII, pricing, addresses, or secrets. Log IDs, reason codes, and controlled metadata; if payloads are required, enforce strict RBAC and retention.

### 26.4. Durable Enqueue Is Not Automatically Atomic with Checkpoint

If the DLQ record persists before the checkpoint saves, the worker may re-enqueue on replay, so use deterministic DLQ `_id` upserts. If the checkpoint advances before the DLQ record is durable, you lose the work item.

### 26.5. Never Mark `VERIFIED` While DLQ Has `OPEN` Items

“Scanned 40M docs” does not mean migration complete if 200 poison records await resolution or formal waivers.

## 27. Network Errors, Retryable Writes, and Uncertain Outcomes

### 27.1. Failures Happen at Many Steps

```text
Fetch document
Compute value
Send update
Wait for majority
Receive response
Save checkpoint
```

Each failure point implies something different:

- Fetch failed: no data update sent yet.
- Validation failed: fix data or logic.
- Connection lost after sending update: **write may have succeeded**.
- Majority write concern timeout: write may be applied yet lacked acknowledgment before timeout.
- Checkpoint timeout: checkpoint may already be saved; re-read before deciding.

### 27.2. Driver Retryable Writes

The MongoDB driver provides protocol-level retryable writes for eligible single-document writes on supported topologies. However, not all commands and bulk shapes share identical automatic retry behavior.

### 27.3. Why Backfills Still Need Idempotency

Process crashes, scheduler restarts, and application-level retries occur **outside the driver's retry protocol**.

### 27.4. `UnknownTransactionCommitResult`

If using transactions for part of a migration, a lost commit response does not mean the transaction aborted. Retry commit per the transaction API rather than re-running non-idempotent side effects.

### 27.5. Bounded Backoff

Example policy:

```text
attempts <= 5
initial delay 200 ms
exponential backoff
random jitter
total request deadline
retry only classified transient failures
```

Do not copy fixed numbers blindly into production. What matters is **a bounded deadline/budget** and never infinitely retrying validation or permission errors.

## 28. Consistency Under Concurrent Writes

Core challenge of online backfills:

```text
Worker snapshot of document at T0
Application updates source at T1
Worker writes derived fields at T2
```

### 28.1. Options

| Strategy | Pros | Risks |
|---|---|---|
| Application dual-write | Derived field stays updated with business write | Must update all writers |
| Revision + worker recompute | Blocks worker from overwriting fresher source | Requires revision increment discipline |
| Change streams catch-up | Captures changes during scan | Token/oplog retention & idempotency |
| Freeze updates | Easy logical snapshot | May cause downtime |
| Transform on read | No immediate backfill needed | Ongoing read cost & fallback debt |

### 28.2. Atomic Dual-Write Example

When the API recalculates subtotal from new `lineItems`:

```javascript
db.orders.updateOne(
  {
    _id: orderId,
    lineItemsRevision: NumberLong("7")
  },
  {
    $set: {
      lineItems: newLineItems,
      itemsSubtotalMinor: newSubtotal
    },
    $inc: { lineItemsRevision: NumberLong("1") },
    $unset: { "migrations.orderItemsSubtotalV2": "" }
  }
);
```

All changes on the same document apply atomically. Unsetting the marker prompts the backfill to re-scan and stamp the new revision; or the app can stamp `version=2` and the new `sourceRevision` in the same update once the new code is fully trusted.

### 28.3. Do Not Dual-Write with Two Separate Writes When Atomicity Is Needed

```javascript
// Not safe enough if readers require both fields immediately synchronized.
db.orders.updateOne({ _id: orderId }, { $set: { lineItems: newItems } });
db.orders.updateOne({ _id: orderId }, { $set: { itemsSubtotalMinor: newTotal } });
```

Between the two commands, crashes or network splits leave readers seeing mismatched values. Combine updates on the same document into a single `updateOne` whenever business logic permits.

### 28.4. Recompute from Source of Truth

If a derived value is wrong, recompute from authoritative `lineItems`; never try to “offset” a total when you do not know how many times it was mutated.

## 29. Change Streams for Post-Backfill Catch-Up

If some writers are not dual-writing yet, or data is moving into a separate collection, combine backfill with CDC.

### 29.1. The Gap Problem

```text
T0 begin backfill
T1 app updates order #42
T2 backfill scans #42 before/after T1 unpredictably
T3 backfill ends
```

Without a handoff mechanism, changes can slip through the cracks.

### 29.2. Conceptual Protocol

1. Open the change stream or capture a resume/start point **before data can mutate past the scan baseline**.
2. Persist the resume token/checkpoint durably with proper semantics.
3. Execute bounded-page backfill.
4. Process relevant change events idempotently keyed by document/revision.
5. Catch up to the target point, verifying data parity and event lag.
6. Cut over readers once zero gap remains, then keep writers/CDC running or switch write paths.

### 29.3. Resume Tokens Do Not Last Forever

Change streams require sufficient oplog history to resume from a token. If a worker stays offline longer than the oplog window, resume fails; plan a re-snapshot/reconciliation fallback rather than simply bumping retry counts.

### 29.4. Never Commit a Token for an Unapplied Event

Saving the token before applying the event to the target causes crashes to **skip the event** on resume. Checkpoint event progress **after confirming side effects**, or use suitable transactional atomicity.

### 29.5. At-Least-Once Event Processing

If an event applies yet saving the token fails, the consumer replays it. Target updates must therefore be idempotent and revision-aware.

### 29.6. CDC Does Not Automatically Guarantee Global Ordering Across Targets

Parallel processing, network retries, sharded topologies, and partitioning can alter arrival order. Rely on domain source revisions/sequences if correctness requires ordering.

## 30. High-Watermark Scan Plus CDC: Two Progress Streams

A clear design:

```text
Scan progress:
  highWatermarkId = ...
  lastScannedId   = ...
  scanState       = SCAN_DONE

CDC progress:
  resumeToken     = ...
  lastAppliedRev  = per document
  changeLag       = ...

Cutover:
  Scan complete
  AND CDC caught up
  AND validation passing
  AND no unresolved DLQ
```

### 30.1. Do Not Mix `ObjectId` and Resume Tokens Into One Key

`lastScannedId` checkpoints the **keyset scan**. `resumeToken` tracks the **change stream**. They have completely different semantics.

### 30.2. Align the Source of Truth

If `orders.lineItems` is the source, both batch and CDC must run the exact same transform rules; never let the batch compute vA while the stream consumer computes vB.

### 30.3. Guard Against Stale Updates

Targets can store `sourceRevision` and accept updates only when the incoming revision is newer. If revisions can ever reset/reuse, include a source epoch/version.

### 30.4. “CDC Lag = 0” Does Not Mean All Data Is Complete

The consumer may be caught up on recent events while the batch scan is still halfway done or poison events sit in DLQ. All combined gates must pass.

## 31. Backfilling Into a New Collection and Deterministic IDs

Not every migration updates in place. For example, building a search read model:

```text
orders (source)
   |
   v
orderSummaries (target)
```

### 31.1. Upsert with Stable Keys

```javascript
db.orderSummaries.updateOne(
  { _id: sourceOrder._id },
  {
    $set: {
      tenantId: sourceOrder.tenantId,
      itemsSubtotalMinor: computedSubtotal,
      sourceRevision: sourceOrder.lineItemsRevision
    }
  },
  { upsert: true }
);
```

A stable `_id` prevents retries from creating duplicate summary documents for the same order.

### 31.2. Guard Against Stale Overwrites

If CDC already wrote `revision=9` to the target, a delayed batch reading `revision=7` and blindly running `$set` could revert the target back to `revision=7`.

Enforce a **conditional target update** based on version or sequencing policy:

```javascript
db.orderSummaries.updateOne(
  {
    _id: sourceOrder._id,
    $or: [
      { sourceRevision: { $lt: sourceOrder.lineItemsRevision } },
      { sourceRevision: { $exists: false } }
    ]
  },
  {
    $set: {
      sourceRevision: sourceOrder.lineItemsRevision,
      itemsSubtotalMinor: computedSubtotal
    }
  }
);
```

This snippet applies only to **existing target documents**; never combine `upsert: true` with non-`_id` revision predicates without handling duplicate-key conflicts and concurrent inserts.

### 31.3. Insert + Conflict Protocol

One safe protocol:

1. Attempt insert with deterministic `_id`.
2. On duplicate key, read the target's current revision.
3. Update only if `sourceRevision` is newer.
4. Use CAS on target revision to prevent races.

### 31.4. Never Generate Fresh `_id`s on Each Run

Calling `insertOne({_id:ObjectId(), ...})` creates duplicates on replay. Deterministic identity is fundamental to idempotency when writing to a new collection.

### 31.5. Source Deletions and Tombstones

If a source document is deleted after the batch reads it, the target can become orphaned. Propagate deletes via CDC/tombstones or periodic reconciliation—do not handle only inserts/updates.

## 32. Checkpointing in a Separate Collection vs. Source Collection

| Approach | Pros | Limitations |
|---|---|---|
| Separate `migrationProgress` | Easy monitoring, RBAC, single-doc atomic updates | Requires ownership protection |
| Marker on each source doc | Tracks per-document status | No global cursor or throughput metric |
| Durable work queue per ID | Fine-grained retry for poison docs | Extra storage and coordination |
| External orchestrator checkpoint | Built-in schedulers/leases | Must stay consistent with MongoDB writes |

### 32.1. Combining Two Layers

A practical design:

- **Global/segment checkpoint:** `lastScannedId` for resuming scans.
- **Per-document marker:** `sourceRevision`/version to skip completed records and detect staleness.
- **DLQ/retry:** durable unresolved IDs.
- **Verification report:** business invariants and remaining counts.

### 32.2. Do Not Rely Solely on Markers

Repeatedly querying `"migrations.orderItemsSubtotalV2.version": {$ne:2}` can miss indexes if poorly designed and skips documents whose revision bumped while the marker stayed at version 2.

### 32.3. Indexing Markers If Needed

Indexing an unmigrated-queue field can accelerate lookups, yet updating an indexed field millions of times adds write amplification. Weigh query shapes against index drop/retention plans.

## 33. Sharded Clusters: Scanning, Routing, and Checkpointing

### 33.1. Shard Key Matters

In a sharded collection, an `_id`-range query lacking the shard key can scatter-gather across all shards. Never assume `_id` automatically targets a single shard.

### 33.2. Partitioning by Shard/Tenant

A strategy:

```text
worker-1: tenant range A–F
worker-2: tenant range G–M
worker-3: tenant range N–Z
```

Tenant sizes can skew heavily; account for skew, shard key distribution, and per-worker rate budgets.

### 33.3. Per-Partition Checkpoints

```javascript
{
  _id: "subtotal-v2:tenant-shop-a",
  tenantId: "shop-a",
  highWatermarkId: ObjectId("6734ffffffffffffffffffff"),
  lastScannedId: ObjectId("673400000000000000000001"),
  state: "RUNNING"
}
```

Partitions must not overlap—or must use an idempotent protocol safe under overlap.

### 33.4. Rebalancing and Chunk Migrations

Chunk moves do not inherently break keyset scans, yet can affect latency and routing. Evaluate behavior while the balancer runs; never disable the production balancer simply because a worker slowed down.

### 33.5. Do Not Automatically Shard the Checkpoint Collection

Checkpoints typically hold very few documents and can live in an unsharded or dedicated collection per deployment; if sharded, respect unique/transaction constraints. Match the schema to ownership and scale.

## 34. Write Concern, Read Concern, and Committed Data

### 34.1. Data Write vs. Checkpoint Write

If data updates use `w:1` while checkpoints use `w:"majority"`, a primary failover can roll back un-replicated data writes while the majority-acknowledged checkpoint survives.

Result: the checkpoint points past a document whose update disappeared.

### 34.2. Choice in This Example

The Java worker sets:

```java
MongoCollection<Document> orders = client.getDatabase("migration_lab_426")
    .getCollection("orders")
    .withWriteConcern(com.mongodb.WriteConcern.MAJORITY);

MongoCollection<Document> progress = client.getDatabase("migration_lab_426")
    .getCollection("migrationProgress")
    .withWriteConcern(com.mongodb.WriteConcern.MAJORITY);
```

The goal is ensuring checkpoints are never more durable than the data writes they represent. This does not make multiple updates a single multi-document snapshot; each update remains an individual operation.

### 34.3. Write Concern Timeouts

If `w:"majority"` times out, the command **may still have applied** on the primary. Never advance the batch checkpoint until the ambiguous outcome is resolved.

### 34.4. Read Concern

Suitable read concern depends on correctness needs, lag, and transaction/snapshot design. `readConcern:"majority"` reads majority-committed data, yet **does not turn multiple separate queries into a single consistent snapshot**.

### 34.5. Per-Batch Transactions?

MongoDB supports multi-document transactions, yet long transactions over thousands of documents incur overhead and lock conflicts. Never invoke atomicity as an excuse to wrap 40 million updates into one transaction.

## 35. Observing Progress: Processed Differs from Modified

A backfill might scan 100,000 documents yet update only 20,000 because 80,000 already carry valid markers. Separate your metrics:

| Metric | Unit | Meaning |
|---|---|---|
| `scanned_docs_total` | Docs | Read/traversed |
| `updated_docs_total` | Docs | Actually modified |
| `already_current_docs_total` | Docs | Valid, skipped |
| `deleted_docs_total` | Docs | Missing upon refetch |
| `cas_conflicts_total` | Attempts | Match failures due to revision changes |
| `retried_docs_total` | Docs | Retried documents |
| `poison_docs_total` | Docs | Uncomputable/invalid |
| `dlq_open` | Docs | Awaiting resolution |
| `checkpoint_advances_total` | Batches | Successful checkpoint commits |
| `batch_duration_seconds` | Seconds | Batch processing latency |
| `actual_docs_per_second` | Docs/s | Observed throughput |
| `throttle_sleep_seconds` | Seconds | Time spent pacing/throttling |
| `estimate_remaining_docs` | Docs | Rough estimate |
| `verification_mismatches` | Docs | Source/target discrepancies |

### 35.1. `matchedCount` Does Not Equal `modifiedCount`

During an update, matching a document where the target field already holds the identical value yields `matchedCount=1`, `modifiedCount=0`. Never report `matchedCount` as “modified” when tracking actual writes.

### 35.2. Instantaneous vs. Average Throughput

Dashboards should show recent docs/s alongside cumulative totals. If a worker throttled heavily during peak hours, a 24-hour average hides the slowdown.

### 35.3. ETA Is Not a Commitment

```text
ETA ≈ remaining estimated documents / recent processed docs/sec
```

ETA shifts with app traffic, conflicts, document sizes, replication lag, and worker count.

### 35.4. Checkpoint Stagnation

If `lastScannedId` stalls for 20 minutes while the worker still emits heartbeats, likely causes include:

- A poison document blocking the batch.
- CAS contention on a hot document.
- Prolonged network retries.
- Rate limiter configured too low.
- Lost checkpoint ownership.

Never blindly crank up the rate to cure stagnation without diagnosing the root cause.

## 36. Place MongoDB Metrics Beside Application SLOs

A backfill can “run cleanly” while hurting production APIs. Pair metrics on one dashboard:

```text
+---------------------------------------------------+
| Backfill dashboard                                |
+---------------------------------------------------+
| progress: lastScannedId / highWatermarkId         |
| scanned, updated, skipped, failed, DLQ            |
| actual docs/sec, batch duration, throttled time   |
+---------------------------------------------------+
| MongoDB                                           |
| primary CPU, WiredTiger cache, disk IOPS          |
| network throughput, write concern latency        |
| replication lag, oplog window, flow control       |
| slow queries, connections, write errors           |
+---------------------------------------------------+
| Application                                       |
| API p95/p99 latency, error rate, checkout failures|
| queue depth, request timeouts, business SLO       |
+---------------------------------------------------+
```

### 36.1. Replication Lag

If backfill write bursts outpace secondaries, lag climbs. Systems using secondary reads or CDC feel downstream impact even while the primary looks healthy.

### 36.2. Oplog Window

Backfills generate large oplog volume whenever documents mutate. Higher oplog churn shrinks the retention window, leaving offline secondaries and Change Stream consumers less recovery margin.

### 36.3. Disk/Cache

Range scans reading cold history and applying updates shift WiredTiger cache residency, driving disk reads/evictions that slow down hot queries. Never watch CPU alone.

### 36.4. Command Monitoring

Java Driver `CommandListener` and `ConnectionPoolListener` surface command duration, pool wait times, and retries; never log raw BSON payloads containing PII.

### 36.5. Use Bounded Labels

Keep Prometheus labels bounded: migration ID, allowlisted collection, outcome, error family, partition. Never use per-document IDs, unbounded `tenantId`s, or raw exception strings as metric labels.

## 37. Production Preflight Checklist

### 37.1. Business Contract

1. Exact definition of the new field, including edge cases.
2. Schema compatibility for old and new apps.
3. Confirmed source of truth and write authorities.
4. Monotonic version/epoch on every source write path.
5. Policies for deleted, archived, and malformed source records.
6. Independent verification method separate from the worker.
7. Rollback/forward-fix plan.

### 37.2. MongoDB Readiness

1. Backups/PITR aligned with policy and restore-tested.
2. Healthy cluster with no ongoing elections or recovery issues.
3. Secondary replication lag and oplog window within SLO.
4. Sufficient disk/headroom for data, index, and oplog growth.
5. Scan queries backed by proper indexes with verified `explain` plans.
6. Defined write concern and checkpoint durability.
7. Least-privilege access scoped to required collections.

### 37.3. Worker Readiness

1. Pinned container image version / commit SHA.
2. Locked job ID, cutoff policy, batch size, and global rate budget.
3. Assigned operator owner and approved maintenance/background window.
4. Pause/resume/stop controls; never checkpoint on partial failure.
5. Metrics, scrubbed logs, and alerts wired up.
6. DLQ and reconciliation policies in place.
7. Stress tests and crash/restart tests passed in a staging environment.

### 37.4. Stop Conditions Must Be Pre-Defined

Never improvise “wait and see” while API error rates breach SLO or replication lag climbs steadily. Define stop/throttle thresholds before launch and agree who can adjust them.

## 38. Dry-Run: Measure Before Writing

### 38.1. True Dry-Run

A dry-run mode should:

- Scan a representative subset.
- Compute target values in memory.
- Validate types, overflow, and business rules.
- Count documents needing modification.
- Estimate expected write payload size.
- **Send zero data updates or progress checkpoints.**

### 38.2. Why Include Outliers?

Uniform random sampling misses huge arrays or legacy-schema tenants. Deliberately sample:

- The oldest documents.
- The newest documents.
- Documents with long `lineItems` arrays.
- Both large and small tenants.
- Documents from intermediate schema versions.
- Missing/null/wrong-type values.

### 38.3. Dry-Runs Do Not Prove Write Performance

Reading and computing incur none of the index maintenance, oplog, or replication costs of writes. Run a **low-rate canary write** to measure real write impact.

### 38.4. Pre-Check Schema Distribution

```javascript
db.orders.aggregate([
  {
    $project: {
      lineItemsType: { $type: "$lineItems" },
      revisionType: { $type: "$lineItemsRevision" },
      subtotalType: { $type: "$itemsSubtotalMinor" }
    }
  },
  {
    $group: {
      _id: {
        lineItemsType: "$lineItemsType",
        revisionType: "$revisionType",
        subtotalType: "$subtotalType"
      },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
]);
```

This aggregation scans the collection and can be costly at scale; run per capacity policy or on a bounded sample/range, never casually at peak traffic.

## 39. Verify: Counting Missing, Stale, and Wrong Values

### 39.1. Missing Field

```javascript
db.orders.countDocuments({
  itemsSubtotalMinor: { $exists: false }
});
```

### 39.2. Wrong Marker Version

```javascript
db.orders.countDocuments({
  "migrations.orderItemsSubtotalV2.version": { $ne: 2 }
});
```

### 39.3. Marker vs. Source Revision Mismatch

```javascript
db.orders.countDocuments({
  $expr: {
    $ne: [
      "$migrations.orderItemsSubtotalV2.sourceRevision",
      "$lineItemsRevision"
    ]
  }
});
```

### 39.4. Do Not Sum Counts Blindly

A document missing `itemsSubtotalMinor` can simultaneously lack the marker and have a stale revision. Adding the three counts **double-counts**, rather than giving unique broken documents.

### 39.5. Verification Has Real Cost

Running `countDocuments` and `$expr` over tens of millions of documents triggers heavy scans. Schedule appropriately, partition, or budget compute—never poll every second.

### 39.6. Independent Recomputation

Verify a sample—and eventually the full eligible set—via an independent code path:

```text
expected = calculateFrom(lineItems)
actual   = itemsSubtotalMinor

assert actual == expected
AND marker.sourceRevision == lineItemsRevision
AND marker.version == 2
```

If verification checks only `marker=2` without recomputing amounts, transform bugs slip through.

### 39.7. Illustrative Verification Aggregation

For documents where `lineItems` is a schema-valid array:

```javascript
db.orders.aggregate([
  { $match: { lineItems: { $type: "array" } } },
  {
    $project: {
      actual: "$itemsSubtotalMinor",
      expected: {
        $reduce: {
          input: "$lineItems",
          initialValue: NumberLong("0"),
          in: {
            $add: [
              "$$value",
              {
                $multiply: [
                  "$$this.quantity",
                  "$$this.unitPriceMinor"
                ]
              }
            ]
          }
        }
      }
    }
  },
  { $match: { $expr: { $ne: ["$actual", "$expected"] } } },
  { $limit: 100 }
]);
```

This check targets validated data; on malformed/overflow records, aggregation can error or follow arithmetic rules differing from Java. Report invalid documents separately, and never treat zero rows from a small sample as proof of whole-collection correctness.

## 40. Canary Rollout: Bound Scope Before Scaling Up

### 40.1. Recommended Sequence

```text
1. Unit tests for transform
2. Disposable MongoDB integration test
3. Staging benchmark with production-like data
4. Production dry-run on bounded sample
5. Canary: a small partition at low docs/s
6. Verify business values and operational metrics
7. Gradually expand partitions/rate
8. Full scan
9. Catch-up/reconciliation
10. Cutover approval
```

### 40.2. Canary Selection

Do not just pick the first 100 docs and declare victory. Include:

- Orders with few and many line items.
- Small and large document sizes.
- Prior schema versions.
- Large, medium, and small approved tenants.

### 40.3. Rate Ladder

Example schedule:

```text
50 docs/s  -> 10 minutes
100 docs/s -> 20 minutes
200 docs/s -> observe
... increase only if safe
```

Numbers are illustrative only; never use as performance benchmarks without establishing your own baseline.

### 40.4. Hold Points

Each rate bump needs operator confirmation or automated gating on trustworthy metrics. If the metrics pipeline drops data, halt rate increases.

## 41. Clean Pause and Resume

### 41.1. Pause Between Batches

Workers should check:

```text
Check pause flag
  |
  +-- RUNNING -> process next batch
  |
  +-- PAUSED  -> finish/abort current safe unit, stop
```

### 41.2. Preserve Checkpoints on `SIGTERM`

In container orchestrators, `SIGTERM` arrives during deployments. The worker should:

- Stop pulling new batches.
- Finish or abort the current batch per idempotent replay policy.
- Never commit a checkpoint for an incomplete batch.
- Close `MongoClient`/cursors cleanly.
- Log the last durable checkpoint ID.

### 41.3. Restart

On restart:

1. Load durable checkpoint.
2. Verify `migrationVersion`/code compatibility.
3. Verify lease/ownership.
4. Verify `highWatermarkId` and `scanKeyType`.
5. Resume after committed `lastScannedId`.
6. Safely replay any uncheckpointed batch.

### 41.4. Do Not Reuse Progress When New Code Changes Logic

If the subtotal formula changes from V2 to V3, never run the new binary against a V2 checkpoint as if outputs matched. Assign a new `migrationVersion`, rollback/cutover plan, and scope check.

## 42. Runbook A — Worker Crashes Mid-Batch

### Symptoms

```text
Checkpoint lastScannedId=1000
Data updates applied through 1077
Process killed before checkpoint 1100
```

### Response

1. Confirm actual durable checkpoint.
2. Check job ownership/lease before restarting.
3. Restart **the exact same migration version**.
4. Worker re-scans `1001..1100`, skipping valid docs via marker+CAS.
5. Confirm checkpoint advances only after full batch completion.

### Do Not

Never manually edit the checkpoint to `1100` just because logs said “last updated 1077,” and never run `$inc` to “patch” attempted records.

## 43. Runbook B — Primary Election or Network Timeout

### Symptoms

- `MongoTimeoutException` selecting primary.
- `MongoSocketException` after sending update.
- Write concern timeout.
- Network error saving checkpoint.

### Response

1. Stop increasing concurrency/rate.
2. Check MongoDB topology/quorum and app error metrics.
3. Classify ambiguous data writes; never assume timeout means unapplied.
4. Re-read durable checkpoint after recovery.
5. Replay uncheckpointed work via idempotent writes.
6. Reconcile affected ranges by `sourceRevision`/marker.

### Do Not

Never issue business `$inc` calls as fresh requests, force primary step-downs just to keep the worker moving, or weaken write concern recklessly.

## 44. Runbook C — Replication Lag Climbs During Backfill

### Symptoms

```text
Backfill actual 1500 docs/s
Primary write latency stable
Secondary lag grows 1s -> 90s
CDC backlog grows
```

### Response

1. Cut rate sharply or pause the worker.
2. Inspect oplog write volume/window and secondary I/O.
3. Check disk, network, CPU, and WiredTiger cache.
4. Wait for lag to return to baseline.
5. Restart with a lower budget once headroom returns.

### Do Not

Never raise docs/s simply because primary p95 looks low; secondaries and CDC feel delayed stress.

## 45. Runbook D — One Poison Document Blocks Progress

### Symptoms

```text
Batch starts at _id 1001
Every retry hits document 1037
Validation error: unitPriceMinor string
Checkpoint remains 1000
```

### Response

1. Identify document ID safely without logging raw PII.
2. Inspect historical schema and business semantics.
3. Decide whether to fix the source per procedure or adjust transform code.
4. If controlled skipping is approved, persist a durable DLQ record with reason/owner.
5. Resume batch only once zero work items can be lost.
6. Clear DLQ and verify before cutover.

### Do Not

Never coerce decimals/strings blindly with `parseInt`, and never advance the checkpoint past errors without a durable record.

## 46. Runbook E — CAS Conflicts Spike

### Symptoms

```text
High conflict rate on recently edited orders
matchedCount=0 often
time spent refetching increases
```

### Response

- Audit writer rollout: do all mutations bump revision?
- Reduce concurrency on hot keys.
- Enforce bounded retry/backoff.
- Partition by `archived`/`active` status if business permits.
- Route hot IDs to a durable retry queue if designed.
- Check if writers keep unsetting markers rapidly.

### Do Not

Never drop the revision filter to “reduce conflicts”: it is your safeguard against stale overwrites.

## 47. Runbook F — Job Reports `SCAN_DONE` Yet Data Remains Missing

### Possible Causes

- High-water mark missed inserts or backdated IDs after the cursor passed.
- Writers are not dual-writing properly.
- Source edits arrived after the scan.
- DLQ still has open entries.
- Transform code missed a legacy schema variant.
- Scanner filter accidentally excluded valid documents.

### Response

1. Keep read fallback enabled; do not contract old schemas.
2. Run missing/stale/semantic verification queries.
3. Audit source revisions, writer rollout, and CDC lag.
4. Run a reconciliation pass/new run targeting remaining bad docs.
5. Clear DLQ.
6. Transition to `VERIFIED` only once approved invariants pass.

### Do Not

Never manually flip state to `COMPLETED` merely because “the scan reached the end of `_id`.”

## 48. Runbook G — Checkpoint Update Fails or Lease Lost

### Symptoms

```text
data batch completed
checkpoint update matchedCount=0
another owner/epoch observed
```

### Response

1. Halt the stale worker immediately.
2. Read the actual checkpoint and current owner/lease epoch.
3. Diagnose duplicate schedulers, expired leases, timeouts, or config drift.
4. Never overwrite the checkpoint with an unguarded `$set`.
5. The rightful owner can safely replay records written by the old worker because updates are idempotent.
6. Investigate overlapping writes if source/target version controls were loose.

### Do Not

Never let two workers race updating the same `lastScannedId` under “last write wins.”

## 49. Test Plan: Proving Safe Replay

### 49.1. Idempotency Test

With 1,000 test orders:

1. Seed sources and revisions.
2. Run backfill.
3. Snapshot expected values and markers.
4. Run a second reconciliation pass.
5. Assert subtotals never doubled or drifted semantically.

### 49.2. Crash After Write, Before Checkpoint Test

```text
Read batch 100 docs
Apply first 65 updates
Inject process termination
Restart worker with same checkpoint
Verify all 100 docs correct
Verify no double increments/duplicates
```

### 49.3. Concurrent Update Test

Run a writer updating `lineItems` and `lineItemsRevision` while the worker executes.

Assertions:

- No stale-revision subtotal stamped with a newer revision.
- CAS mismatches trigger refetch/retry or durable deferral.
- Final values match the authoritative source.

### 49.4. Poison Data Test

Insert a document missing `lineItemsRevision` or holding an invalid BSON type; confirm the checkpoint **does not advance past it** and DLQ/halt policies trigger properly.

### 49.5. Network/Error Test

In an authorized Testcontainers replica set lab:

- Restart a MongoDB node or inject network faults.
- Checkpoints must not advance if batch writes are unconfirmed.
- Upon recovery, the worker resumes cleanly.
- Timed-out MongoDB updates are never assumed unapplied.

### 49.6. Rate Limit Test

Run 10,000 docs capped at 200 docs/s and measure observed docs/s over a sufficiently long window; allow jitter from timers/OS scheduling/DB load instead of asserting strict 5 ms intervals.

### 49.7. Empty Dataset Test

Zero documents in range must transition cleanly to `SCAN_DONE` or no-op per contract without crashing or looping forever. Section 22's Java sample intentionally requires seeded data; production must handle empty ranges.

### 49.8. Multi-Worker Test

If using partitions+leases:

- Two workers claim the same partition.
- Only the valid owner can advance the checkpoint.
- Expired-lease workers fail checkpoint updates.
- Replayed data writes never corrupt state.

## 50. Testcontainers and JUnit: Lightweight Integration Harness

An integration test can use the Testcontainers Java MongoDB module for a real MongoDB instance:

```java
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.mongodb.MongoDBContainer;
import org.testcontainers.utility.DockerImageName;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class BackfillReplay426IT {
    @Container
    static MongoDBContainer mongo =
        new MongoDBContainer(DockerImageName.parse("mongo:7.0"))
            .withReplicaSet();

    @Test
    void shouldComputeSubtotal() {
        try (MongoClient client =
                 MongoClients.create(mongo.getReplicaSetUrl())) {
            var orders = client.getDatabase("migration_lab_426")
                .getCollection("orders");

            orders.insertOne(new Document(
                    "_id", new org.bson.types.ObjectId())
                .append("lineItemsRevision", 1L)
                .append("lineItems", java.util.List.of(
                    new Document("quantity", 2)
                        .append("unitPriceMinor", 125000L)
                )));

            new OrderSubtotalBackfill426(client).run();

            Document current = orders.find().first();
            assertNotNull(current);
            assertEquals(250000L,
                current.getLong("itemsSubtotalMinor"));
        }
    }
}
```

### 50.1. Requirements to Verify

- Testcontainers dependencies/APIs/imports match your version (e.g., Testcontainers Java 2.x uses `org.testcontainers.mongodb`).
- A single-node replica set exercises core transaction and write concern semantics, yet **does not** simulate multi-node primary elections.
- Tests must use isolated namespaces and clean up only resources they own.
- Testing mid-batch crashes requires worker fault-injection hooks; the snippet above is an end-to-end smoke test.

### 50.2. Never Point Integration Tests at Production

Never swap a test URI for production credentials. Test seeds and cleanups must touch only test-owned containers/namespaces.

## 51. Production Scenarios That Reshape Design

### 51.1. 500-Million-Document Collections

A single worker still works, though its ETA may be long. Partition by tenant/shard key/immutable ranges to scale, enforcing non-overlap and a global rate budget.

### 51.2. Huge Arrays Inside Documents

Computation cost and p99 read payloads spike. Adapt batch sizes by byte volume or isolate outliers rather than blindly sticking to “100 docs.”

### 51.3. High-Churn Sources (Multiple Edits/Second)

CAS conflict rates climb; application dual-write or CDC may outperform workers racing live writers.

### 51.4. Migrations That Grow Document Size Significantly

Adding large fields or indexes increases disk/cache pressure and risks breaching MongoDB's 16 MiB BSON document limit. Preflight must measure p99 document size, compression/IO, and index growth.

### 51.5. Sharded Target Collections

Shard targeting, shard keys, unique indexes, `bulkWrite` ordering, and chunk balance all shape throughput and semantics. Verify update/upsert commands carry the shard key as required by your server version.

### 51.6. Currency Conversions

Never multiply by a hardcoded constant. You need transaction-time exchange rates, precision/rounding rules, currency codes, and audit trails. Without historical data, **never fabricate backfill results**.

### 51.7. Schemas Lacking Source Revisions

Add a preliminary phase introducing revisions or a dual-write protocol before running computed backfills. Never fake missing revisions with `updatedAt` unless timestamps are strictly unique and monotonic.

## 52. Cutover: When Can the App Drop Read Fallbacks?

An acceptance checklist:

| Requirement | Expected Evidence |
|---|---|
| All writers compatible | Deployment inventory, integration tests |
| Scan completed | Durable progress, cutoff, metadata |
| New changes covered | Dual-write/CDC lag and protocol |
| No unresolved poison docs | DLQ count = 0 or approved waiver |
| Values verified | Missing/stale/mismatch checks |
| API correctness | Canary reads/outputs |
| Operational health | p95/p99, write rate, replication lag |
| Recovery possible | Backup/PITR, rollback/forward-fix plan |
| Ownership confirmed | Change ticket, operator approval |

### 52.1. Two Cutover Stages

**Read cutover:** the application begins preferring the new field while keeping fallbacks or guards.

**Contract cutover:** legacy-schema support code is removed, and new validators/index rules can be tightened.

Do not force both to occur simultaneously.

### 52.2. Progressive Rollout

Percentage rollouts or canary tenants are great. However, if tenants differ in data mix and consistency needs, verify readiness per cohort rather than trusting cluster-wide percentages alone.

### 52.3. Backfills Must Respect Immutability Policies

If orders are immutable, adding a precomputed field to accelerate reads is fine; if business/compliance treats orders as signed legal records, verify audit/legal requirements before mutating them.

## 53. Rollback and Forward-Fix

### 53.1. Code Rollback Does Not Require Data Rollback

If the new app and worker added `itemsSubtotalMinor`, rolling back app code rarely requires deleting that field. Removing it blindly could break another service already reading it.

### 53.2. Forward-Fix

If the V2 formula has a bug, typically:

1. Stop the V2 worker.
2. Maintain old/new compatibility.
3. Ship the fixed V3 transform with a new marker version.
4. Recompute from the authoritative source.
5. Re-verify, then cut over upon approval.

### 53.3. Never Patch Formulas with Unverified Offsets

If V2 misrounded values, subtracting a flat constant across records usually fails; recompute cleanly from source inputs and contracts.

### 53.4. Backup/PITR

Backups recover from catastrophic loss or corruption. However, cluster-wide restores discard valid post-backup writes; treat them strictly as emergency recovery, never as an easy Undo button.

## 54. Common Anti-Patterns

| Anti-Pattern | Risk | Remedy |
|---|---|---|
| Blind collection-wide `updateMany({})` | Hard to throttle/checkpoint | Bounded batches or idempotent scoped updates |
| `skip(10000000)` | Huge scan, shifting offsets | Keyset pagination |
| Cursor sort lacking tie-breaker | Missed/duplicate records | Composite stable key |
| Checkpoint before writes | Skips data on crash | Checkpoint after batch |
| Checkpoint despite 1 failed doc | Lost work item | Fail batch or durable DLQ |
| Cursor stored only in RAM | Restarts from zero | Durable progress store |
| Missing high-water mark | Infinite scan on growing data | Fixed cutoff + catch-up |
| Treating high-water mark as snapshot | Misses concurrent inserts/updates | Writers/CDC/reconciliation |
| Treating `ObjectId` as strict commit clock | Ordering flaws | State bounds & proper handoff |
| `$inc` for derived subtotals | Double counts on retry | Deterministic `$set` |
| `replaceOne` from old snapshot | Overwrites concurrent edits | Field-level CAS update |
| Skipping source revision bumps on mutation | Renders CAS useless | Enforce writer invariant |
| Dropping CAS when conflicts rise | Stale overwrites | Throttle/partition/defer |
| Infinite retries | Load storms, hung jobs | Bounded retries + DLQ |
| TTL-deleting poison records | Destroys failure evidence | Durable triage & retention |
| Assuming `bulkWrite` is batch-atomic | Partial success hazards | Per-document idempotency |
| `ordered(false)` with order dependencies | Non-deterministic state | Independent operations |
| Throttling only via batch size | Uncapped docs/s | Pacing / token bucket |
| 10 workers each taking full cluster budget | Cluster overload | Global rate budget |
| Increasing speed while metrics are blind | Uncontrolled impact | Pause or safe default |
| Watching only primary latency | Hidden secondary lag / CDC stall | Replication & oplog metrics |
| Data write `w:1`, checkpoint `majority` | Data rolled back past checkpoint | Consistent durability policy |
| Unguarded multi-worker checkpoints | Overwritten progress | Leases/fencing/CAS |
| Assuming leases guard data writes | Stalled worker can still write | Revision guards/fencing |
| Stale CDC overwriting newer target | Version regression | Monotonic target revisions |
| Saving resume token before applying event | Drops event on crash | Commit token after apply |
| Conflating resume tokens and scan cursors | Broken semantics | Two separate checkpoints |
| Dropping fallback immediately after scan | Missing/stale/DLQ exposed | Verification/cutover gates |
| Checking only markers, not values | Transform bugs slip through | Independent recomputation |
| Logging raw orders in monitoring | Data exposure | IDs, reason codes, redaction |
| Pointing integration tests at prod URI | Corrupts live data | Test-owned containers/namespaces |
| Rolling back via broad field drops | Breaks shared consumers | Planned forward-fix |

## 55. Hands-On Exercises

### Exercise 1 — Define Source Data and Target Field

Given orders with `lineItems`, `discount`, and `shipping`, define `itemsSubtotalMinor` precisely and distinguish it from `grandTotalMinor`.

### Exercise 2 — Calculation

Line items are `(2×125000)` and `(1×80000)`. Compute the subtotal and explain when `Math.multiplyExact` is needed.

### Exercise 3 — Expand–Contract Design

Outline a plan moving from code reading only `lineItems` to reading the new subtotal, covering fallback, dual-write, backfill, verification, and contract.

### Exercise 4 — Skip Backfill?

When can subtotal be computed on read instead of backfilling tens of millions of documents? Explain read latency trade-offs.

### Exercise 5 — Idempotency

Compare `$set` subtotal vs. `$inc` subtotal when the same document executes three times.

### Exercise 6 — CAS

Worker reads `revision=5`; API edits `lineItems` to `revision=6`. Write an `updateOne` that writes subtotal only if `revision` is still 5.

### Exercise 7 — Revision Invariant

An import job edits `lineItems` without bumping revision. Why can CAS still write a stale total? Design the rollout fix.

### Exercise 8 — Keyset

Write a query fetching 100 documents with `_id` greater than the checkpoint and up to the high-water mark, sorted ascending.

### Exercise 9 — Composite Cursor

Documents share identical `createdAt` values. Why does checkpointing only `createdAt` skip records? Write a filter using `createdAt` and `_id`.

### Exercise 10 — BSON Types

A collection mixes `ObjectId` and `String` in `_id`. Which assumptions in the Java worker break?

### Exercise 11 — High-Water Mark

Worker locks `max(ObjectId)`, then the API inserts a document carrying a 1-day-old `ObjectId`. Where is the risk of missing it?

### Exercise 12 — Checkpoint Ordering

Compare crashing when checkpointing before vs. after data writes. Which case recovers cleanly via idempotency?

### Exercise 13 — Durable State

Design a checkpoint document holding `migrationVersion`, `state`, `highWatermarkId`, `lastScannedId`, and `updatedAt`.

### Exercise 14 — Leases

Worker A's lease expires and Worker B claims `epoch=9`. Write the checkpoint filter preventing A from overwriting B's progress.

### Exercise 15 — Throttling

12 million docs must finish in 8 hours. Compute the minimum average rate (ignoring overhead) and explain why you should not hardcode that exact number as the rate limit.

### Exercise 16 — Token Bucket

Design a 100 docs/s token bucket with capacity 20; contrast it with sleeping after every 1,000 writes.

### Exercise 17 — Batch Size

Compare 100 docs/batch vs. 5,000 docs/batch when document sizes vary widely and frequent checkpoints are required.

### Exercise 18 — Ordered Bulk

An ordered bulk of 100 updates hits a duplicate/validation error at operation 37. Which operations may have run? Should the checkpoint advance to doc 100?

### Exercise 19 — Unordered Bulk

An unordered bulk reports partial success. Design how to identify IDs needing retry without causing double effects.

### Exercise 20 — Poison Data

An order has `quantity="two"`. Contrast fail-fast vs. DLQ and explain why you must never auto-parse `"two"` as `2`.

### Exercise 21 — Crash Test

Worker writes 78/100 docs and crashes before checkpointing. Design a Testcontainers test proving safe replay.

### Exercise 22 — Unknown Write Outcome

`updateOne` returns a network timeout after sending the request. Can you assume it did not write? What must you check before checkpointing?

### Exercise 23 — CDC Token

Explain why saving a resume token before applying an event loses data, and why applying before saving requires idempotency.

### Exercise 24 — Two Progress Streams

Design separate checkpoints for scan `lastScannedId` and CDC `resumeToken`. When is cutover allowed?

### Exercise 25 — Sharding

A collection is sharded on `tenantId`. What is the risk of an `_id`-only range scan? Design an appropriate `tenantId`-scoped partition/query.

### Exercise 26 — Write Concern

Data updates use `w:1` while checkpoints use `w:majority`. How can a primary failover corrupt progress accuracy?

### Exercise 27 — Metrics

Design a dashboard displaying scanned/updated/skipped/errors, checkpoint progress, API p95, MongoDB disk IOPS, replication lag, and CDC lag.

### Exercise 28 — Adaptive Throttling

Backfill runs at 800 docs/s, yet API p99 rises and oplog window shrinks. Propose reduce/pause policies and ramp-up conditions.

### Exercise 29 — Verification

Write three queries counting missing subtotals, wrong marker versions, and stale `sourceRevision`. Why does summing all three double-count?

### Exercise 30 — Independent Recomputation

Write a verifier that ignores markers and recomputes subtotal from `lineItems`, testing overflow and bad types.

### Exercise 31 — Rollback

Migration V2 miscalculated by omitting one line-item type. Should you subtract a fixed value from every subtotal? Design a V3 forward-fix.

### Exercise 32 — Capstone

Design a backfill for 50 million orders in a continuously written production database without adding more than 5% to p99 latency:

1. Access patterns and source of truth.
2. Writer compatibility / dual-write rollout.
3. Deterministic transform and version markers.
4. Keyset / high-water mark and cursor schema.
5. Batch size / rate / global budget.
6. Checkpointing / leases / fencing.
7. Retry / CAS / DLQ policy.
8. CDC or reconciliation for concurrent writes.
9. Metrics / alerts / stop conditions.
10. Load tests, crash/restart tests, verification/cutover/rollback.

## 56. Summary Execution Flow

### Preparation

```text
1. Define business invariant
2. Confirm source schemas and type distributions
3. Deploy backward-compatible readers/writers
4. Validate backup/recovery and production capacity
5. Select immutable scan key and cutoff strategy
6. Fix version, job ID, checkpoint and rate budget
7. Run dry-run and canary
```

### Each Batch

```text
Read durable checkpoint
      |
      v
Select next bounded page in stable key order
      |
      v
For each document:
  throttle
  fetch current source
  validate transform
  skip if already correct
  guarded write with CAS
  retry/defer only under defined policy
      |
      v
All documents resolved?
      |
   No +-----> Stop or durable DLQ, no unsafe advance
      |
     Yes
      |
      v
Persist checkpoint with majority write concern + ownership CAS
      |
      v
Continue or pause
```

### Completion

```text
Scan reaches cutoff
      |
      v
Reconcile concurrent inserts/updates/deletes
      |
      v
Resolve DLQ and stale revisions
      |
      v
Independent validation
      |
      v
Canary read cutover
      |
      v
Contract after approval
```

## 57. Summary

**A successful online backfill is not a fast bulk write command.** It is a schema evolution workflow capable of running alongside live applications, respecting resource limits, recovering from failures, and proving final data correctness.

**Batching and rate limiting** bound workload safely: `limit()` and `batchSize()` govern only read/cursor pacing, whereas token buckets, pacing, and global budgets govern MongoDB write impact. Watch application SLOs, disk/cache, replication lag, and oplog windows—not just worker throughput.

**Checkpoints must advance only after the batch fully resolves.** Crashing before checkpointing makes replay normal; combine deterministic `$set` and revision CAS so values neither double nor overwrite newer data. With multiple workers, enforce partition ownership, leases/fencing, and checkpoint CAS.

**High-water marks are not snapshots.** Concurrent inserts, updates, and deletes create gaps requiring dual-writes, CDC catch-up, or explicit reconciliation. `SCAN_DONE` does not mean `VERIFIED`.

**Cutover requires verifiable gates**, not merely a 100% progress bar: valid markers/`sourceRevision`, accurate computed values, resolved DLQ entries, caught-up CDC, healthy API SLOs, and a tested recovery plan. When a transform formula has bugs, prefer a versioned forward-fix over blind deletions or ad-hoc compensating offsets.

A reliable MongoDB backfill is one that **can pause, restart, replay, and account accurately for every processed slice of data** while the system preserves business correctness.

## 58. References

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/): single-document atomicity and CAS conditions.
- [MongoDB Manual — updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/): non-atomic multi-document updates and idempotent retries.
- [MongoDB Manual — bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/): ordered/unordered operations and partial failures.
- [MongoDB Java Sync Driver — Bulk Write Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/): `UpdateOneModel`, `BulkWriteOptions`, and bulk error handling.
- [MongoDB Java Sync Driver — Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update/): `updateOne` and `UpdateResult`.
- [MongoDB Manual — Update with an Aggregation Pipeline](https://www.mongodb.com/docs/manual/tutorial/update-documents-with-aggregation-pipeline/): server-side transforms when appropriate.
- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/): resume tokens, oplog retention, and resumability.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): protocol retries and operation limits.
- [MongoDB Manual — Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/): majority-committed reads and consistency.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): majority acknowledgments, durability, and timeouts.
- [MongoDB Manual — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/): ObjectId/Int64/Decimal128 and BSON ordering.
- [MongoDB Manual — Explain Results](https://www.mongodb.com/docs/manual/reference/explain-results/): evaluating scan/index plans.
- [MongoDB Manual — Sharding](https://www.mongodb.com/docs/manual/sharding/): shard targeting, range migrations, and load distribution.
- [MongoDB Manual — Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/): oplog window and replication.
- [Testcontainers Java — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): MongoDB integration tests and local replica set setup.
