# Migrating Data Using Export/Import, CDC, or Dual-Write Based on Requirements in MongoDB

## 1. Context: When Is Data Migration Needed?

An application stores tens of millions of documents in MongoDB. The engineering team may need to:

- Migrate from self-managed MongoDB to MongoDB Atlas.
- Redesign document and collection structures while keeping the application online.
- Split a multi-tenant system into separate databases/clusters.
- Replicate data into analytics, search, or archival stores.
- Change the shard key or partitioning model.
- Consolidate data from multiple environments.
- Evolve architecture from a monolith to services owning their own data.
- Move to a new MongoDB cluster with different security, region, or compute profiles.

These operations are all broadly called **data migration**, yet their requirements differ dramatically.

A system that can pause writes during a maintenance window can use straightforward **data export/import**. A system that must stay writable while moving terabytes needs **initial copy combined with CDC**. Systems migrating tenant-by-tenant or requiring app-layer transformation logic may evaluate **dual-write**, provided they handle partial failures where one store succeeds and the other fails.

```text
                       SOURCE MongoDB
                              |
             +----------------+----------------+
             |                |                |
             v                v                v
        Export/Import     CDC / oplog      Dual writes
             |                |                |
         File / dump      Change events     Application
             |                |                |
             +----------------+----------------+
                              |
                              v
                       TARGET datastore
                              |
                      Validate + cutover
```

**Core point:** no single tool delivers zero downtime, zero data loss, zero engineering effort, and instant rollback in every scenario. Choose a strategy based on business objectives and how well you can control mutating data.

---

## 2. Learning Objectives

Upon completing this lesson, you will be able to:

1. Distinguish logical export/import, backup/restore, CDC, and dual-write.
2. Choose a migration strategy based on downtime, data volume, RPO, and RTO.
3. Understand why a dump does not automatically represent a consistent snapshot while writes continue.
4. Use `mongodump`/`mongorestore` and `mongoexport`/`mongoimport` for their proper purposes.
5. Design full load plus CDC catch-up without missing mutations during backfill.
6. Understand Change Streams, resume tokens, oplog history windows, and delete events.
7. Build a Java migration worker using business-key upserts, batching, and checkpoints.
8. Recognize the non-atomicity of dual-writing to two independent databases.
9. Design transactional outbox, idempotency, and reconciliation.
10. Execute cutovers, validate data, and build conditional rollback plans.
11. Handle edge cases: TTL, unique indexes, sharding, transactions, schema versions, and sensitive data.

---

## 3. Three Primary Strategies

| Criterion | Export/Import | Full Load + CDC | Dual-Write |
| --- | --- | --- | --- |
| Data source | Snapshot or export file | Snapshot/backfill plus change stream | Every application write |
| Write-freeze need | Usually required for simple consistency | Minimizes write freeze to cutover | Supports incremental cohorts, needs sync |
| Complexity | Low to moderate | Moderate to high | High with failures and multiple writers |
| Large data | Limited by tools and storage | Strong with full load + sufficient oplog/CDC | Does not migrate historical data automatically |
| Document deletes | Reflected in final snapshot | Must process delete events | Must propagate deletes to both stores |
| Recovery | Re-run dump/restore or restore snapshot | Resume token + checkpoint | Retry queue/outbox/reconciliation |
| Key risk | Data changes during export | Lost resume history, ordering bugs, backfill race | Write succeeds in one store, fails in other |
| Best fit | Offline/batch migrations | High-volume online migrations | Canary migrations where app controls writes |

**Do not confuse:** CDC does not copy historical data if you only start watching events today; dual-write does not automatically migrate existing legacy data either.

---

## 4. Classify Requirements Before Choosing a Method

A migration plan should answer:

- Is the **source** standalone, a replica set, or a sharded cluster?
- Is the **target** another MongoDB deployment or another system such as PostgreSQL, Elasticsearch, or a data lake?
- What are data size, document count, index count, and growth rate?
- Must data move **as-is** or be **transformed**?
- Do collections have cross-collection business invariants?
- Are concurrent writes active? Inserts, updates, deletes, transactions?
- How long can writes pause?
- What is the maximum tolerable data loss?
- Must writes be reversible after cutover?
- Must two stores run in parallel for canarying?
- Are there legal, retention, encryption, or key-management requirements?
- Who is the single authoritative owner of each record during transition?

### 4.1. RPO and RTO

- **RPO (Recovery Point Objective):** maximum data loss acceptable during recovery or cutover.
- **RTO (Recovery Time Objective):** target time to restore service or complete failover after an incident.

Example:

```text
Business accepts:
  Planned write downtime: <= 10 minutes
  Potential data loss:     0 acknowledged business writes
  Cutover rollback window: 1 hour
  Dataset size:            500 GiB
  Write rate:              2,000 operations/second
```

Under these requirements, running `mongoexport` for hours followed by `mongoimport` while the app keeps writing **will not suffice**. You need change catch-up, writer controls, and a tight cutover protocol.

### 4.2. Never Promise “RPO = 0” Based on Tool Names

A CDC pipeline can lag, lose oplog history, or fail at the sink. A dual-write pipeline can drop writes to the second target. True RPO comes from durable write concerns, checkpoints, replayability, cutoffs, and cutover verification.

---

# PART I — MIGRATION VIA EXPORT / IMPORT

## 5. Tools That Are Easily Confused

MongoDB provides two common tool pairs:

| Tool | Format | Purpose |
| --- | --- | --- |
| `mongodump` | BSON dump + metadata | Logical dump for MongoDB data recovery |
| `mongorestore` | BSON dump | Restores from `mongodump` |
| `mongoexport` | JSON or CSV | Exports data for exchanging with other apps/systems |
| `mongoimport` | JSON/CSV/TSV per options | Imports serialized data into MongoDB |

`mongodump` **does not** create a physical filesystem snapshot. `mongoexport` **is not** a full-fidelity backup equivalent to `mongodump`.

### 5.1. When to Use `mongodump`/`mongorestore`?

- Moving a database between compatible MongoDB deployments.
- Creating a logical dump carrying index/collection metadata as supported by the tool.
- Restoring datasets into test or staging environments.
- Migrating during a maintenance window with zero concurrent writes or a clear consistency plan.

### 5.2. When to Use `mongoexport`/`mongoimport`?

- Exchanging data with external systems via CSV or JSON.
- Exporting a filtered subset of fields.
- Performing ETL with schema transformations.
- Loading sample datasets or externally supplied files.

### 5.3. When Is a Platform Snapshot/Backup Needed?

If you need point-in-time consistency, multi-node sharded clusters, PITR, or strict RPO, evaluate platform-native snapshots/backups. Never assume a CSV export preserves all metadata, indexes, roles, and cross-collection consistency.

---

## 6. `mongodump` and `mongorestore` Examples

Commands below are for **test environments or approved migrations**. Never type credentials directly into shell history.

Dump a database:

```bash
mongodump \
  --uri="$SOURCE_MONGODB_URI" \
  --db="sales" \
  --archive="./sales.archive.gz" \
  --gzip
```

Restore to target:

```bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --archive="./sales.archive.gz" \
  --gzip \
  --nsInclude="sales.*"
```

### 6.1. Restores Can Collide with Existing Data

If the target collection already holds documents with matching `_id`s, restore may hit duplicate-key errors or behave unexpectedly. **Never pass `--drop` carelessly** in production—it drops the target collection before restoring.

### 6.2. Namespace Mapping

When renaming databases/collections, Database Tools support namespace mapping, e.g.:

```bash
mongorestore \
  --uri="$TARGET_MONGODB_URI" \
  --archive="./sales.archive.gz" \
  --gzip \
  --nsFrom="sales.*" \
  --nsTo="sales_v2.*"
```

Verify patterns and support against your MongoDB Database Tools version before running; never stop at “restore completed” logs without checking actual target collection names.

### 6.3. Tool Versions

Database Tools are versioned separately from MongoDB Server. Pick a Database Tools release documented as compatible with both source and target, especially with newer BSON types or collection features.

---

## 7. Consistency When Writes Happen During a Dump

A dump can take hours. Meanwhile:

```text
10:00:00  dump starts
10:15:00  customer name updated
10:30:00  order created
11:00:00  old order deleted
11:30:00  dump ends
```

Without additional consistency mechanisms, collections can reflect **different points in time**, leaving `orders` and `customers` inconsistent.

### 7.1. `mongodump --oplog`

On eligible replica sets, `mongodump --oplog` captures oplog entries written during the dump so `mongorestore --oplogReplay` can restore a more consistent point, subject to MongoDB Database Tools limits.

However:

- Do not treat `--oplog` as an arbitrary cluster-wide sharded solution.
- Namespace/collection filters, DDL operations, topologies, and transactions carry specific restrictions.
- The oplog window must be large enough; if oplog entries wrap mid-dump, the dump fails or loses consistency guarantees.
- If the source uses features unsupported on the target, oplog replay will not magically resolve compatibility.

**Read the exact tool documentation before relying on `--oplog`/`--oplogReplay`.** It does not replace an online migration pipeline with catch-up and rollback.

### 7.2. Simplest Way to Get a Static Point in Time

When business allows:

1. Stop all writers or switch to read-only maintenance mode.
2. Confirm zero background writes remain.
3. Run dump or snapshot per procedure.
4. Restore to target.
5. Verify data, indexes, and business constraints.
6. Point applications to target.
7. Re-enable writes.

This is far easier to verify, though downtime scales with data volume and throughput.

---

## 8. Exporting JSON or CSV

Export JSON:

```bash
mongoexport \
  --uri="$SOURCE_MONGODB_URI" \
  --db="sales" \
  --collection="orders" \
  --type=json \
  --out="./orders.json"
```

Export CSV with selected fields:

```bash
mongoexport \
  --uri="$SOURCE_MONGODB_URI" \
  --db="sales" \
  --collection="orders" \
  --type=csv \
  --fields="_id,tenantId,status,totalMinor" \
  --out="./orders.csv"
```

Import JSON into target collection:

```bash
mongoimport \
  --uri="$TARGET_MONGODB_URI" \
  --db="sales_v2" \
  --collection="orders" \
  --file="./orders.json" \
  --type=json
```

For **one-document-per-line** JSON files, omit `--jsonArray`; pass the matching option only if the file is a single JSON array per Database Tools docs.

### 8.1. CSV Does Not Fully Preserve BSON Types

CSV stores plain text. `ObjectId`, `Date`, `Decimal128`, `BinData`, nested objects, and arrays cannot be preserved automatically in every case. `mongoimport` offers field-type options, yet requires explicit mapping.

### 8.2. JSON Requires Attention to Extended JSON

MongoDB Extended JSON encodes BSON types via special wrappers like `$oid`, `$date`, and `$numberDecimal`. Deserializing to plain JSON and re-serializing carelessly strips types and precision.

### 8.3. Exports Do Not Preserve All Metadata

Indexes, collection options, validators, collations, views, sharding configs, users/roles, and cluster settings are omitted from `mongoexport` JSON/CSV. Manage them via migration scripts/IaC or proper backup tools.

---

## 9. Import Modes and Idempotency

When importing into a populated collection, choose semantics carefully:

- Insert new only.
- Upsert by `_id` or business key.
- Merge fields.
- Replace whole documents.
- Reject duplicates.

For instance, `mongoimport` provides `--mode=upsert` and `--upsertFields` depending on tool version:

```bash
mongoimport \
  --uri="$TARGET_MONGODB_URI" \
  --db="sales_v2" \
  --collection="orders" \
  --file="./orders.json" \
  --type=json \
  --mode=upsert \
  --upsertFields="_id"
```

### 9.1. Do Not Confuse Upsert with Merge

Using upsert with unintended replace/merge semantics can wipe target fields or retain stale legacy fields. Verify whether **replace** or **merge** occurs on a test dataset.

### 9.2. When No Stable `_id` Exists

Define a business key such as `(tenantId, externalOrderId)` backed by a matching unique index. Never generate random `_id`s on retry if the migration must be idempotent.

### 9.3. Test Importing Twice

A critical test is running the same import file twice:

- Document count does not inflate unexpectedly.
- Zero business duplicates appear.
- Values remain accurate.
- Under replace mode, protected fields are not lost.
- Error handling reports accurately.

---

## 10. Validating Data After Export/Import

At minimum verify:

1. Collection list and namespace mappings.
2. Counts per collection, tenant, and partition.
3. Critical aggregate sums and totals.
4. `_id` and business keys.
5. Type fidelity for Dates, `Decimal128`, and `ObjectId`.
6. Indexes, validators, collations, and unique constraints.
7. TTL/index settings and retention.
8. Full-field inspection of sampled documents.
9. Permissions and read/write smoke tests.
10. Whether post-dump mutations require catch-up.

### 10.1. Matching Counts Are Not Enough

```text
Source:
  order A: total=100
  order B: total=200

Target:
  order A: total=200
  order B: total=100
```

Both have `count=2`, yet data is wrong. Run canonical comparisons keyed by ID and business fields.

### 10.2. Compute Checksums on Canonical Representations

When comparing hashes, normalize field ordering, array order semantics, and BSON types. Hashing raw JSON with differing key orders yields false mismatches; casting `Decimal128` to `double` loses precision.

---

# PART II — CHANGE DATA CAPTURE (CDC)

## 11. What Is CDC?

**Change Data Capture (CDC)** records mutations at the source and applies them to the target while the source keeps serving live writes.

Example:

```text
SOURCE MongoDB
   |
   +-- initial scan/backfill ---> TARGET MongoDB
   |
   +-- Change Streams events --> Durable CDC buffer
                                        |
                                        v
                                  Apply to TARGET
                                        |
                                        v
                                Catch-up + cutover
```

CDC typically has two distinct stages:

1. **Initial snapshot/backfill:** copy existing documents.
2. **Change replay:** process inserts, updates, replaces, and deletes occurring from the CDC start point until caught up.

**Simply opening a Change Stream today does not reconstruct five years of collection history.**

---

## 12. MongoDB Change Streams and the Oplog

In replica sets and sharded clusters, MongoDB provides **Change Streams** to watch supported mutations:

- `insert`.
- `update`.
- `replace`.
- `delete`.
- Certain collection/database events such as rename, drop, and invalidate.
- Transaction-related change events per server semantics.
- Newer event types depending on server version and options.

Change Streams read oplog history and emit resume tokens so consumers can resume from a supported point.

### 12.1. Do Not Tail the Raw Oplog Arbitrarily When Change Streams Exist

Oplog internals can shift across versions and are hard to translate cleanly into business events. Change Streams are the official API designed for application consumption.

### 12.2. Topology Requirements

Change Streams require a MongoDB deployment with oplog/change-stream support—typically a **replica set or sharded cluster**. A standalone `mongod` does not support them.

### 12.3. Do Not Assume Every Change Event Carries a Full Document

An `update` event carries `updateDescription` rather than automatically including the whole document. Depending on `fullDocument` options and timing, the full document may be looked up or missing.

---

## 13. What Is a Resume Token?

Each change event carries an `_id` event token used for resuming, typically surfaced by the Java Driver as a `BsonDocument`.

Illustrative structure:

```javascript
{
  _id: {
    _data: "8269..."
  },
  operationType: "insert",
  ns: {
    db: "sales",
    coll: "orders"
  },
  documentKey: {
    _id: ObjectId("691800000000000000000001")
  },
  fullDocument: {
    _id: ObjectId("691800000000000000000001"),
    status: "PAID"
  }
}
```

The **event** `_id` is the resume token. `documentKey._id` is the key of the **mutated document**. They serve different purposes.

### 13.1. Persist the Token in Native BSON Form

Never “extract `_data` and slice strings” or serialize tokens to plain JSON losing types. Store it in a supported BSON representation alongside pipeline metadata.

### 13.2. When to Update the Checkpoint?

Save the token **only after the event has applied to the target and been acknowledged**. Saving before applying causes crashes to skip events.

### 13.3. The Gap Between Apply and Checkpoint

If apply succeeds yet checkpointing fails, the event replays on restart. Therefore **sink writes must be idempotent** or wrapped in appropriate transaction/outbox boundaries.

---

## 14. Oplog Window: The Limit of Resumability

The oplog has finite size/retention. As writes continue, older entries age out or get overwritten.

```text
13:00    Consumer saves token T
13:10    Consumer crashes
14:00    Heavy write traffic
20:00    Consumer resumes T

If token T no longer within available history:
  resume may fail -> rebootstrap required
```

### 14.1. What to Measure

- Source oplog window.
- Peak write throughput.
- Maximum CDC lag.
- Initial scan duration.
- Durable event buffer retention strategy.
- Acceptable outage duration across deployments/restarts.
- Target apply throughput.

### 14.2. When the Initial Scan Outlasts the Oplog Window

A CDC pipeline can lose events before the scan ends if it fails to poll and persist the stream promptly. Opening the stream before the snapshot is useless if the consumer stops polling and its resume token expires.

**Ensure post-start events are persisted/replayed within buffer retention**, or use dedicated snapshot/backup migration tools that preserve history.

---

## 15. Backfill + CDC: Order Matters More Than Speed

A deceptively reasonable yet broken sequence:

```text
1. Dump old data.
2. Wait several hours.
3. Start Change Stream.
4. Replay changes.
```

Writes occurring between step 1 and step 3 can be **missed**.

### 15.1. Conceptually Safer Pattern

```text
T0: establish CDC starting point
    |
    v
Persist changes from T0 into durable log/queue
    |
    +-------------------------------+
    |                               |
    v                               v
Scan and copy baseline          Keep capturing CDC
    |                               |
    v                               |
Baseline copy completes <-----------+
    |
    v
Replay all changes since T0 in valid order
    |
    v
Reach low CDC lag and stable target state
    |
    v
Controlled write pause / drain / cutover
```

### 15.2. Never Blindly Interleave Backfill and CDC Writes

If both streams touch the same document:

```text
Backfill reads old version v1
CDC receives update v2
CDC applies v2
Backfill later writes v1 -> target regresses!
```

Solutions include:

- **Capture first, backfill baseline, then replay changes** from T0 in order.
- Or use version/sequence-aware conditional upserts so stale writes never overwrite newer state.
- Or use a dedicated migration tool guaranteeing sequencing.
- Or briefly pause writes for a clean snapshot/cutover.

Every option must address ordering, deletes, and snapshot boundaries. Two pipelines running in parallel do not automatically produce a consistent target.

---

## 16. Update Events and `fullDocument`

Change Streams can emit:

- `operationType: "update"`.
- `updateDescription` listing changed and removed fields.
- `documentKey`.
- `fullDocument` when enabled and lookup succeeds.

Java commonly uses:

```java
source.watch()
    .fullDocument(FullDocument.UPDATE_LOOKUP)
```

### 16.1. `UPDATE_LOOKUP` Is Not an Exact Historical Snapshot

`UPDATE_LOOKUP` fetches the document's **current** state when the event is read, not necessarily the exact after-image of that specific update if newer writes followed.

Example:

```text
T1 status = PENDING
T2 update status = PAID
T3 update status = REFUNDED
T4 CDC processes event from T2 using updateLookup
```

The `fullDocument` at T4 may show `REFUNDED`, not `PAID`.

### 16.2. `fullDocument` Can Be `null`

If the document was deleted before lookup or under other edge conditions, `fullDocument` may be absent. Workers must never treat `null` as “delete target immediately” without checking event type and ordering.

### 16.3. When Pre/Post Images Are Needed

Modern MongoDB versions support **Change Stream pre- and post-images** when configured on the collection, subject to retention policies and version constraints. Choose APIs/metadata matching your release if exact before/after images are required.

### 16.4. Do Not Use CDC to Rewrite Uncontrolled Transaction History

If the target replays individual state transitions to trigger business side effects, relying on `updateLookup` instead of immutable event payloads corrupts semantics. Separate state replication from event sourcing.

---

## 17. CDC Must Handle Deletes

A pipeline upserting only `insert` and `update` leaves deleted source records behind.

Example:

```text
Source:
  insert order A
  update order A
  delete order A

Target without delete handler:
  order A still exists -> stale record
```

### 17.1. Applying Deletes

Use `documentKey` (containing `_id` and any shard key fields) to identify the target record:

```java
BsonDocument key = change.getDocumentKey();
target.deleteOne(key);
```

This works conceptually when source and target share identical keys/schemas. If the migration **changes `_id`** or merges documents, maintain a durable mapping from source keys to target keys.

### 17.2. Do Not Lose Delete Events Under Lag

In high-churn systems, a document may be inserted and deleted before backfill reaches it. CDC replay must process deletes so the target converges to final state.

### 17.3. Soft-Delete Differs from Hard-Delete

If the source sets `deletedAt` or `active:false`, that emits an **update**, not `operationType: delete`. Transform per business rules rather than blindly turning updates into hard deletes.

---

## 18. CDC and DDL Operations

Besides inserts/updates/deletes, migrations can encounter:

- Collection rename/drop.
- Database drop.
- Index creation/removal.
- Validator updates.
- Collation changes.
- Shard metadata changes.
- Change Stream `invalidate` events.

**Schema/metadata** changes do not automatically replicate completely merely by watching document streams.

### 18.1. Rules During the Migration Window

You may need a **DDL freeze** or separate schema migration pipeline:

- Deploy index definitions via IaC/migration scripts.
- Never rename collections mid-backfill.
- Do not enable TTL too early and purge target records prematurely.
- Never apply different sharding options on target without verifying keys.
- Never alter validators mid-flight without updating transform code.

### 18.2. Resuming After `invalidate`

Per the Change Streams API, `resumeAfter` cannot resume past an `invalidate` event; `startAfter` handles certain post-invalidate cases per server rules. Never assume a single resume token survives drops or renames.

---

## 19. Java Example: Reading Change Streams

Below is a **minimal CDC example** when both collections share compatible `_id`s. It illustrates lifecycle and idempotent apply, not a production-grade connector.

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.OperationType;
import com.mongodb.client.model.ReplaceOptions;
import com.mongodb.client.model.Filters;

import org.bson.BsonDocument;
import org.bson.Document;

public final class SimpleCdcReplication {

    public static void run(
            MongoCollection<Document> source,
            MongoCollection<Document> target
    ) {
        try (MongoChangeStreamCursor<
                 ChangeStreamDocument<Document>> cursor =
                 source.watch()
                     .fullDocument(FullDocument.UPDATE_LOOKUP)
                     .cursor()) {

            while (cursor.hasNext()) {
                ChangeStreamDocument<Document> event =
                    cursor.next();

                OperationType type =
                    event.getOperationType();

                if (type == OperationType.INSERT
                        || type == OperationType.REPLACE
                        || type == OperationType.UPDATE) {

                    Document full =
                        event.getFullDocument();

                    if (full == null) {
                        // Do not silently skip.
                        throw new IllegalStateException(
                            "Missing fullDocument for " + type
                        );
                    }

                    target.replaceOne(
                        Filters.eq("_id", full.get("_id")),
                        full,
                        new ReplaceOptions().upsert(true)
                    );

                } else if (type == OperationType.DELETE) {
                    BsonDocument key =
                        event.getDocumentKey();

                    if (key == null) {
                        throw new IllegalStateException(
                            "DELETE event without document key"
                        );
                    }
                    target.deleteOne(key);

                } else {
                    // DDL/invalidate and other event types need
                    // dedicated policy; do not treat as success.
                    throw new IllegalStateException(
                        "Unsupported CDC type: " + type
                    );
                }

                // Production: persist resume token durably AFTER
                // target apply succeeds; do not merely log token.
            }
        }
    }
}
```

### 19.1. Limitations of This Sample

- No checkpoint store.
- No retry/backoff.
- No schema transformation.
- No multi-worker ordering.
- No pre/post-image semantics.
- No initial snapshot/backfill logic.
- No recovery for collection `invalidate`/rename.
- No rollback/cutover handling.
- No progress tracking.

Treat it strictly as an **API learning sample**, not a complete CDC engine.

---

## 20. Java: `resumeAfter` Checkpoint

Once resume tokens are durably persisted as `BsonDocument`:

```java
import org.bson.BsonDocument;

BsonDocument savedToken =
    checkpointStore.loadResumeToken();

var iterable = source.watch()
    .fullDocument(FullDocument.UPDATE_LOOKUP);

if (savedToken != null) {
    iterable.resumeAfter(savedToken);
}

try (var cursor = iterable.cursor()) {
    while (cursor.hasNext()) {
        var event = cursor.next();

        applyToDestination(event);

        // Only after target acknowledges success.
        checkpointStore.saveResumeToken(
            event.getResumeToken()
        );
    }
}
```

`checkpointStore` and `applyToDestination` are application-provided interfaces, not built-in MongoDB Driver APIs.

### 20.1. Tokens Must Be Durable

Never keep tokens only on the Java heap:

```java
BsonDocument lastToken;
```

because process crashes wipe them. Use a backed-up durable store with ownership/leasing if multiple CDC consumers exist.

### 20.2. Post-Apply Checkpoints Imply At-Least-Once

If apply succeeds and the process crashes before saving the token, the event replays on restart. Target operations must therefore be idempotent.

### 20.3. When Checkpoint Store and Target Share a Database

You can evaluate wrapping target updates and token checkpoints inside a transaction where deployment, driver, and workload permit. Across separate clusters, **no single MongoDB transaction spans both clusters**.

---

## 21. Idempotent Apply via Replace/Upsert

For state replication between two MongoDB collections sharing `_id`:

```java
target.replaceOne(
    Filters.eq("_id", doc.get("_id")),
    transformedDoc,
    new ReplaceOptions().upsert(true)
);
```

Replaying the same event leaves the target unchanged **if**:

- Transformations are deterministic.
- Newer writes are never overwritten by older events.
- No concurrent target writers interfere.
- `_id` mapping is stable.
- No external side effects run.
- Event ordering is preserved.

### 21.1. Idempotency Does Not Replace Ordering

Given two events:

```text
E1: order status=PAID
E2: order status=REFUNDED
```

If a worker applies E2 then E1, `replaceOne` is still “idempotent on E1 retries,” yet the final state is **wrong**.

Solutions:

- Ordered per-key/partition consumer.
- Version/sequence fields with conditional writes.
- Migration connectors guaranteeing order.
- Sequential replay where throughput permits.

### 21.2. Version-Aware Conditional Update

A schema-dependent pattern:

```javascript
db.targetOrders.updateOne(
  {
    _id: "O100",
    appliedVersion: { $lt: 42 }
  },
  {
    $set: {
      status: "REFUNDED",
      appliedVersion: 42
    }
  }
);
```

Note: combining `upsert` with a version predicate alongside `_id` can trigger duplicate-key errors when the existing document fails the version filter. Production implementations must handle that safely and rely on **trustworthy monotonic versions**, never unsynchronized `updatedAt` clocks across hosts.

---

## 22. From Full Copy to CDC Catch-Up: Ordering Matters

A minimal architecture:

```text
STAGE 1: CAPTURE
  Start CDC at point T0
  Write every change to durable log
  Watch oplog retention and consumer lag

STAGE 2: BACKFILL
  Scan source documents
  Transform and write to target
  Persist per-range progress

STAGE 3: REPLAY
  Read stored events since T0
  Apply in supported order, including deletes
  Catch up to current source

STAGE 4: CUTOVER
  Temporarily stop/drain source writes
  Reach final CDC marker
  Verify target
  Switch writes/read traffic

STAGE 5: MONITOR
  Stop old writes, monitor and reconcile
```

### 22.1. Why Start CDC Before Full Scan?

So mutations occurring immediately after backfill starts are never missed.

### 22.2. Why a Durable Buffer?

So the source keeps accepting writes during multi-hour backfills without losing change history if consumers restart.

### 22.3. Why a Cutover Barrier?

You must prove the final writes were applied—not merely glance at “CDC lag ~0” on a chart. A controlled marker/handoff and write drain establish a verifiable boundary.

---

## 23. Marking the Final Synchronization Point

Systems may use:

- A source write freeze followed by confirming zero in-flight writers.
- A marker event written **after** all prior writes are acknowledged per policy.
- Corresponding resume tokens / high-water marks.
- CDC connectors with supported cutover checkpoints.
- Per-partition reconciliation after catch-up.

### 23.1. OS Timestamps Alone Are Not Enough

If application host clocks skew, `updatedAt <= now` does not guarantee every pre-cutover write was copied.

### 23.2. Markers Only Work If Ordered Properly

Across multiple source partitions or shards, a marker in one collection is not always a cluster-wide barrier. Align marker design with the ordering and boundaries your CDC service actually guarantees.

### 23.3. Never Stop Source Writes and Enable Target Writes Too Early

If unapplied change events remain or target indexes are not ready, new target writes can be overwritten by stale replays. Cutover plans must enforce **writer ownership and replay order**.

---

## 24. CDC and Cross-Collection Transactional Consistency

A business operation may execute:

```text
Transaction:
  insert orders
  decrease inventory
  insert payment record
```

If migration applies events **independently without preserving transaction boundaries**, the target can briefly show the order without the inventory decrement.

### 24.1. When Is This Acceptable?

If the target serves eventually consistent analytics, brief cross-collection lag is fine.

### 24.2. When Is It Not?

If the target serves live inventory/payment transactions requiring cross-collection invariants:

- Replay along transaction boundaries if your connector supports it; or
- Lock cutover at a consistency barrier; or
- Migrate via a consistent snapshot; or
- Prevent reads on target until the consistency barrier clears.

### 24.3. Do Not Assume Independent CDC Events Preserve Atomic Commits

MongoDB transactions enforce atomicity at the source where supported, yet downstream pipelines need corresponding mechanisms to preserve that invariant at the target.

---

## 25. CDC with MongoDB Kafka Connector or Migration Services

Not every team needs to write a custom Java consumer.

Options include:

- MongoDB Kafka Source Connector streaming Change Streams into Kafka.
- Matching Kafka Connect Sink connectors for target stores.
- Managed CDC/ETL services.
- Native MongoDB migration tooling matching your release, such as `mongosync` for supported cluster-to-cluster flows.
- Custom Java consumers when specialized transformation logic is needed.

### 25.1. Evaluating Connectors

- Supported source and target versions?
- Replica set / sharded cluster support?
- Built-in initial copy?
- Resume/checkpoint recovery?
- Handling for deletes, updates, DDL, and transactions?
- Schema transforms and `_id` remapping?
- Detection of lost oplog history?
- Lag and retry observability?
- Cutover barriers and reverse sync?
- True exactly-once guarantees or at-least-once?

### 25.2. Never Blindly Label Kafka or Connectors “Exactly Once”

End-to-end exactly-once requires specific transaction boundaries, offset commits, and sink semantics. Most production pipelines rely on **at-least-once delivery + idempotent apply**.

### 25.3. `mongosync` Does Not Fit Every Scenario

`mongosync` has specific purposes, licensing/feature support, restrictions, FCV/version/topology prerequisites, and commit/cutover steps per release. Never assume it handles arbitrary architectures, schema redesigns, or dual-write rollbacks.

---

# PART III — DUAL-WRITE

## 26. What Is Dual-Write?

During migration, the application writes every change to both source and target:

```text
                  APPLICATION
                        |
              +---------+---------+
              |                   |
              v                   v
        SOURCE MongoDB       TARGET MongoDB
              |                   |
          primary write       secondary write
```

Example when creating an order:

```text
1. Write order to old database.
2. Write equivalent order to new database.
3. Return HTTP response.
```

Appeal: the target receives new mutations without tailing the oplog. Yet these are **two independent operations**, not a shared transaction.

### 26.1. Questions You Must Answer

- If source succeeds and target fails, what HTTP status is returned?
- If source fails and target succeeds, how do you roll back the target?
- On timeouts with unknown outcomes, how do retries work?
- What if writes arrive out of order at the target?
- What if a user edits the same record mid-retry?
- What if an old client/service still writes only to source?
- What if background jobs bypass dual-write code?
- What if the target has different unique indexes or validators?

---

## 27. Four Outcome States of Dual-Write

| Source Write | Target Write | Consequence |
| --- | --- | --- |
| Success | Success | Both persisted the change |
| Success | Failure | Target is missing data |
| Failure | Success | Target has phantom data absent from source |
| Failure | Failure | Neither persisted; safe to retry |
| Unknown due to timeout | Unknown | Must read/reconcile by operation ID |

### 27.1. No Transactions Across Two Independent Clusters

A MongoDB transaction is scoped to a single supported deployment. You cannot `startTransaction()` on cluster A and expect atomic commits across an independent cluster B.

### 27.2. Returning 500 Does Not Undo Writes

If source insert succeeds and target times out, returning an error prompts client retries. On retry, `_id` collides at source while target may or may not already hold the write. Idempotency—not `try/catch`—is required.

---

## 28. Naive Dual-Write and Its Risks

```java
public void createOrder(
        MongoCollection<Document> oldOrders,
        MongoCollection<Document> newOrders,
        Document order
) {
    oldOrders.insertOne(order);
    newOrders.insertOne(order);
}
```

**Never use this pattern in production** because:

- Target failures leave silent divergence.
- No queue or retry mechanism.
- `_id` may be mutated onto `Document` during the first insert.
- No partial-timeout handling.
- No ordering or versioning.
- No audit trail or reconciliation.
- Ignores deletes and updates.
- Retries cause duplicates.

If dual-write is mandatory, explicitly designate **one source of truth** and build replayability.

---

## 29. Safer Pattern: Source-of-Truth + Outbox

Concept:

```text
Application request
       |
       v
BEGIN transaction on SOURCE
       |
       +--> Update business document
       |
       +--> Insert durable outbox event
       |
       v
COMMIT SOURCE
       |
       v
Outbox worker reads event
       |
       v
Apply idempotently to TARGET
       |
       v
Mark event processed / checkpoint
```

### 29.1. Benefits

- Business write and outbox event commit atomically in **one** supported MongoDB deployment.
- If the target is temporarily down, the outbox retains events for retry.
- Application avoids pretending two clusters commit atomically.
- Backlog and retry counts are observable.
- Deterministic event IDs enable deduplication.

### 29.2. Trade-Offs

- Target is eventually consistent rather than instantaneously consistent after every request.
- Must operate the outbox worker.
- Needs retention and outbox cleanup.
- Must manage retries and ordering.
- Services must handle “target not yet caught up” on reads.

### 29.3. When Is Outbox Better Than Direct Dual-Write?

Whenever you must guarantee sync requests are never lost to transient target errors and can tolerate **small, monitored lag**.

---

## 30. Outbox Document Example

```javascript
{
  _id: "evt-2026-10001",
  aggregateType: "ORDER",
  aggregateId: "O10001",
  operation: "ORDER_UPSERTED",
  version: NumberLong("42"),
  payload: {
    _id: "O10001",
    tenantId: "T100",
    status: "PAID",
    totalMinor: NumberLong("199000")
  },
  state: "PENDING",
  attempts: 0,
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

### 30.1. Snapshot Payload vs. Patch Payload?

Two approaches:

- **Snapshot event:** carries full latest document state; easy to `replaceOne`, needs version/ordering guards.
- **Patch event:** carries relative deltas; saves bytes, yet hard to make idempotent if using unguarded increments.

For instance, a `$inc` patch is dangerous on event replay: each replay increments again. Snapshots plus version gating are usually easier to keep idempotent for state replication.

### 30.2. Keep Event IDs Deterministic

When retrying the same business action, never mint random event IDs if doing so causes double-processing. Enforce idempotency end-to-end from HTTP request through outbox to target.

---

## 31. Java: Transactional Write to `orders` and `outbox`

Assumes a MongoDB replica set/sharded deployment supporting transactions, with `orders` and `outbox` on the same source deployment:

```java
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.TransactionBody;
import com.mongodb.client.TransactionOptions;
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.ReadPreference;

import org.bson.Document;

public final class OrderOutboxWriter {

    public static void create(
            MongoClient client,
            MongoCollection<Document> orders,
            MongoCollection<Document> outbox,
            Document order,
            Document event
    ) {
        TransactionOptions options =
            TransactionOptions.builder()
                .readConcern(ReadConcern.SNAPSHOT)
                .writeConcern(WriteConcern.MAJORITY)
                .readPreference(ReadPreference.primary())
                .build();

        try (ClientSession session = client.startSession()) {
            session.withTransaction(
                () -> {
                    orders.insertOne(session, order);
                    outbox.insertOne(session, event);
                    return null;
                },
                options
            );
        }
    }
}
```

### 31.1. Retry Caveats Inside `withTransaction`

The driver may retry the callback based on error labels and transaction semantics. The callback **must never invoke external APIs or non-idempotent side effects**. Generate `order`/`event` IDs before calling or via stable policies so retries never spawn extra business records.

### 31.2. Never Put Target Writes Inside the Callback

If `targetOrders.insertOne(...)` hits **another cluster**, it is outside the source transaction. Driver retries can send duplicates or corrupt target state.

### 31.3. Dedicated Consumer Worker

A worker claims outbox events via leases, applies them to the target, and marks `PROCESSED` after acknowledgment. Include crash recovery and idempotency.

---

## 32. When Is Direct Dual-Write Acceptable?

In simpler systems, direct dual-write can work **only if**:

- One store is designated the authoritative source of truth.
- Failed target writes go to a durable retry queue.
- Every operation carries an idempotency key.
- Versioning/ordering is enforced.
- Reconciliation runs continuously.
- Reads can stay off the target if lag occurs.
- All writers funnel through the exact same pathway.
- Failure-injection tests pass.

Never allow “log target failure and move on” while claiming zero data loss.

### 32.1. Dual-Writing Does Not Guarantee Identical Ordering

Two HTTP requests A/B edit the same order. Source applies A before B, yet target receives B before A due to network jitter. Enforce conflict/version rules whenever target state depends on order.

### 32.2. Last-Write-Wins Is Not Free

Using app-supplied `updatedAt` for last-write-wins breaks under clock skew. Prefer monotonic versions incremented at the single source of truth, or an ordered per-key stream.

---

## 33. Dual-Read for Canary Validation Before Switching Traffic

A useful strategy:

```text
Production request
       |
       v
Read SOURCE -> response to user
       |
       +--> Shadow read TARGET (async)
                    |
                    v
           Compare normalized result
                    |
                    v
             Metrics / diff logs
```

### 33.1. Shadow Read Differs from Dual-Write

Shadow reads verify whether the target returns results equivalent to the source. They neither repair target data nor guarantee catch-up.

### 33.2. What to Compare

- Document presence/absence.
- Transformed field values.
- `Decimal128` and timezones.
- Array ordering where business-critical.
- Soft-delete and TTL rules.
- Query pagination and sorting.
- Aggregation totals.
- Index and collation behavior.
- p95/p99 latency.

### 33.3. Never Log Raw Sensitive Data

When logging diffs, emit document key, rule ID, field names, and canonicalized hashes—never raw PII or payment fields.

---

## 34. Versioning Data to Protect Ordering

A record with `version`:

```javascript
{
  _id: "O100",
  version: NumberLong("42"),
  status: "PAID"
}
```

Every source update increments `version` atomically under matching logic.

CDC/dual-write events:

```text
E41: O100 version 41, PENDING
E42: O100 version 42, PAID
E43: O100 version 43, REFUNDED
```

Target accepts changes **only when newer than the currently stored version**.

### 34.1. This Is a Business Protocol

MongoDB does not auto-generate a monotonic `version` field across all documents. The application must enforce strict increments under concurrency.

### 34.2. Do Not Forget Deletes

If a delete event simply removes the target document, a delayed stale upsert arriving later can **resurrect** the record.

Use **tombstones** or versioned deleted states:

```javascript
{
  _id: "O100",
  version: NumberLong("44"),
  deleted: true
}
```

Clean up tombstones per retention policy only after migration/cutover converges. Never purge tombstones prematurely while stale events can still replay.

---

# PART IV — END-TO-END MIGRATION WORKFLOW

## 35. Recommended Phases

```text
DISCOVER
    |
    v
PREPARE source/target + backup
    |
    v
INITIAL COPY / BACKFILL
    |
    v
CDC OR DUAL-WRITE CATCH-UP
    |
    v
RECONCILE
    |
    v
SHADOW READ / CANARY
    |
    v
CUTOVER (single writer authority)
    |
    v
MONITOR & ROLLBACK WINDOW
    |
    v
DECOMMISSION source (after approval)
```

Each phase has distinct exit gates; never equate “copy script finished” with overall success.

---

## 36. Phase 1 — Discovery and Inventory

Collect:

| Area | Questions |
| --- | --- |
| Topology | Standalone / replica set / sharded? FCV? |
| Volume | Document counts, avg/max size, storage/index footprint |
| Write patterns | Inserts/updates/deletes, TPS, peak load |
| Data shape | BSON types, arrays, references, GridFS |
| Constraints | Unique/partial/TTL, validators, collation |
| Partitioning | Shard keys, tenant ownership, zones |
| Transactions | Multi-document/cross-collection invariants |
| Operations | Backups, PITR, KMS, auditing, monitoring |
| Consumers | Java services, jobs, BI, CDC, Change Streams |
| Retention | TTL, legal holds, data residency |
| Performance | Read/write p95/p99, indexes, disk throughput |

### 36.1. Find Every Writer

Not just the main API. Include:

- Scheduled jobs.
- Admin scripts.
- Batch loaders.
- Import pipelines.
- Direct-writing mobile clients, if any.
- Background retry workers.
- Change Stream processors writing derived data.
- Data repair tasks.

If one writer bypasses CDC or dual-write pathways, the target misses mutations.

---

## 37. Phase 2 — Prepare Target

Before backfilling:

1. Select compatible server versions/FCV for your data and tools.
2. Create namespaces per mapping.
3. Design indexes, collations, and validators.
4. Decide when to activate unique and TTL indexes.
5. Provision sufficient disk, RAM, IOPS, and network bandwidth.
6. Configure TLS, access controls, and encryption.
7. Wire monitoring and alerts.
8. Run CRUD smoke tests on a test collection.
9. Verify transaction/change-stream support if needed.
10. Schedule pre-cutover backups.

### 37.1. Unique Indexes Can Block Dirty Data

If the source contains records violating the target's unique key, target index builds or writes fail. Profile, deduplicate, and define conflict policies prior to import.

### 37.2. TTL Can Delete Backfilled Documents Prematurely

If the source retains logically expired records awaiting cleanup, creating an active TTL index on target immediately can wipe records mid-reconciliation.

Decide:

- Must the target retain an exact pre-cutover snapshot?
- Can expired documents be excluded?
- When should TTL activation occur?
- Should TTL definitions wait until after validation?

### 37.3. Shard Keys Affect Upserts

When targeting a sharded collection, upsert/update/delete filters must follow version-specific shard routing and uniqueness rules. Never filter solely by `_id` if target sharding/uniqueness dictates otherwise.

---

## 38. Phase 3 — Batched Backfill Without Holding Everything in RAM

With the Java Sync Driver, a typical approach:

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Sorts;
import com.mongodb.client.model.WriteModel;
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.ReplaceOptions;
import org.bson.Document;
import java.util.ArrayList;
import java.util.List;

public final class MongoBackfill {

    public static long copy(
            MongoCollection<Document> source,
            MongoCollection<Document> target
    ) {
        final int BATCH = 500;
        long count = 0;
        List<WriteModel<Document>> writes =
            new ArrayList<>(BATCH);

        try (MongoCursor<Document> cursor =
                 source.find()
                     .sort(Sorts.ascending("_id"))
                     .batchSize(BATCH)
                     .cursor()) {

            while (cursor.hasNext()) {
                Document original = cursor.next();
                Document migrated = transform(original);

                writes.add(
                    new ReplaceOneModel<>(
                        Filters.eq("_id", migrated.get("_id")),
                        migrated,
                        new ReplaceOptions().upsert(true)
                    )
                );

                if (writes.size() >= BATCH) {
                    target.bulkWrite(writes);
                    count += writes.size();
                    writes.clear();
                }
            }

            if (!writes.isEmpty()) {
                target.bulkWrite(writes);
                count += writes.size();
                writes.clear();
            }
        }

        return count;
    }

    private static Document transform(Document source) {
        Document result = new Document(source);
        result.put("schemaVersion", 2);
        return result;
    }
}
```

### 38.1. This Sample Is Not a Full Production Migration

It lacks CDC catch-up, checkpoints, retries, concurrency, conflict management, snapshot boundaries, and rollback. It demonstrates **basic batched copying**, not guaranteed online consistency.

### 38.2. `bulkWrite` Can Partially Succeed

On duplicate keys, validation failures, or network timeouts, some documents may persist before the exception throws. Never assume full-batch rollback. Rely on idempotency and checkpoints tied to acknowledged results.

### 38.3. Avoid Holding One Cursor for Hours

On massive datasets, split keyset ranges by `_id`, tenant, or partition with durable checkpoints so workers resume without starting over.

---

## 39. Backfill Checkpointed by `_id`

Pattern:

```text
Page size = 1000
Checkpoint = last fully applied _id

Read 1000 documents where _id > checkpoint
Transform + bulk upsert
Confirm destination writes
Persist checkpoint
Repeat
```

Java query:

```java
Bson filter = lastId == null
    ? new Document()
    : Filters.gt("_id", lastId);

List<Document> page = source.find(filter)
    .sort(Sorts.ascending("_id"))
    .limit(1000)
    .into(new ArrayList<>());
```

Here `into(List)` is bounded by `limit(1000)`, keeping memory safe per page.

### 39.1. Never Checkpoint Before Bulk Write Succeeds

```text
WRONG:
  store lastId
  -> target bulkWrite fails
  -> restart skips missing docs
```

### 39.2. Page Replay Must Be Idempotent

```text
RIGHT:
  apply target
  -> persist checkpoint
  -> if checkpoint persist fails, retry same page
```

### 39.3. When Schema Transforms Alter `_id`

You cannot resume using the target `_id` alone. Persist **source keys**, target mappings, and a stable idempotency protocol.

---

## 40. Invariants to Preserve During Transformation

A migration from:

```javascript
{
  _id: "O100",
  amount: 19.99,
  currency: "USD"
}
```

to:

```javascript
{
  _id: "O100",
  totalMinor: NumberLong("1999"),
  currency: "USD",
  schemaVersion: 2
}
```

must define:

- Rounding policy.
- Precision / `Decimal128` conversion.
- Null/missing handling.
- Default fields.
- Timezones.
- Boolean/string conversions.
- Nested arrays/maps.
- Referential integrity.
- Validation rules.
- Search index metadata.
- Privacy masking.

### 40.1. Never Convert Money Using `double` Arbitrarily

If the source uses `Decimal128`, use `BigDecimal` per business rounding rules; never cast `(long)(double * 100)` where precision can drift.

### 40.2. Version Your Mappings

Record transformation versions for traceability:

```text
source schema v1
  -> transform v2.3
  -> target schema v2
```

Deploying new transform logic mid-backfill risks converting identical source records differently. Freeze transform versions per run or reprocess affected partitions explicitly.

---

## 41. Phase 4 — CDC Catch-Up and Lag

Post-backfill, the target trails the source by a backlog of events. Monitor:

```text
Source event rate:       2,000 changes/s
Destination apply rate:  3,000 changes/s
Backlog:                600,000 events

Net drain speed:         ~1,000 events/s
Estimated drain:         ~10 minutes
```

This is an idealized estimate assuming steady throughput, not a guaranteed ETA.

### 41.1. Metrics to Track

- Events captured per second.
- Events applied per second.
- Last durable resume token.
- CDC backlog size/age.
- Oldest unprocessed event age.
- Source oplog window.
- Retry/error rates.
- Apply conflicts.
- Target write latency.
- Dead-letter/quarantine counts.
- Delete/update/insert event counts.
- Per-partition lag if parallelized.

### 41.2. `lag = 0` Does Not Prove Target Correctness

A consumer may be dropping unsupported events or applying buggy transforms. Always pair lag monitoring with data reconciliation.

---

## 42. Phase 5 — Reconciliation

Reconcile at multiple levels:

### Level 1: Inventory

- Collections exist.
- Indexes and options match.
- Validators and collations match.
- Sharding and TTL settings match.
- Data residency and permissions verified.

### Level 2: Counts

- Total document count.
- Count per tenant.
- Count per time bucket.
- Count per status/category.
- Deleted/tombstone counts.

### Level 3: Business Aggregates

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: "$tenantId",
      count: { $sum: 1 },
      totalMinor: { $sum: "$totalMinor" }
    }
  }
]);
```

### Level 4: Samples and Hashes

- Compare documents via source-key/target-key mapping.
- Canonicalize fields per transform rules.
- Verify money, date, and `ObjectId` fidelity.
- Hash per partition or per record.
- Flag mismatches and retry/rebuild cleanly.

### Level 5: Application

- Critical read/write workflows.
- Transactions and unique constraints.
- Search indexes.
- Pagination and sorting.
- Change Streams / CDC consumers.
- Access controls.

### 42.1. Compare Only at the Same Logical Cut

While the source keeps accepting writes, source counts at 13:00 and target counts at 13:05 naturally differ even with healthy CDC. Align reconciliation to a common watermark or paused writer window.

---

## 43. Phase 6 — Shadow Reads and Canarying

During this stage:

```text
User request
   |
   v
SOURCE read -> user response
   |
   +-- TARGET shadow read
             |
             v
       Compare under same filter
```

Once diff rates meet thresholds:

- Route an internal user cohort.
- Route a canary tenant/cohort.
- Keep metric alerts active.
- Never allow both sides to freely write the same owned records without a conflict policy.

### 43.1. Eventual Lag on Target

Shadow-reading the target milliseconds after a source write can see stale state. Compare only once events settle or within a defined lag tolerance.

### 43.2. Test Performance Too

A target with exact counts yet missing indexes or mismatched collations can spike API p99. Validate latency, capacity, TTL, and query plans.

---

## 44. Phase 7 — Controlled Cutover

Example runbook:

1. Announce maintenance/cutover window.
2. Freeze non-essential schema changes and index builds.
3. Stop or drain source writes per application policy.
4. Wait for in-flight transactions to complete.
5. Capture final source checkpoint/watermark.
6. Wait for CDC to apply past the final watermark.
7. Confirm zero event gaps and zero unresolved DLQ items.
8. Reconcile critical partitions.
9. Verify target indexes, validators, and backups.
10. Switch single **writer authority** to target.
11. Switch read/API traffic to target.
12. Run smoke tests on critical workflows.
13. Monitor p95/p99, error rates, replication, and CDC.
14. Keep source read-only during the rollback window per policy.

### 44.1. Cutover Means “One Source of Truth”

Never let two app versions write independently to source and target in opposite directions without conflict resolution.

### 44.2. If a Mixed-Traffic Window Is Mandatory

Use deterministic per-tenant/cohort routing:

```text
tenant T1 -> source owns writes
tenant T2 -> target owns writes
```

with ownership tracked in a control plane. This is complex—thoroughly test ownership handoffs, retries, and read consistency.

---

## 45. Post-Cutover Rollback Is Harder Than Expected

Before cutover:

```text
SOURCE authoritative
TARGET follower
```

After cutover:

```text
TARGET authoritative
SOURCE no longer receiving writes
```

Once the target receives fresh writes, the old source is **out of date**. Swapping the connection string back loses post-cutover writes.

### 45.1. Rollback Options

- Verified reverse CDC from target back to source.
- Reverse dual-write with idempotency and versioning.
- Pause target writes, reconcile backward, then flip routing.
- Backup/PITR restore with business-approved loss/replay bounds.
- Forward-fix on target when rollback is unsafe.

### 45.2. Define Rollback Boundaries

Runbooks must state clearly **where simple rollback ends** and where the “point of no return” begins, requiring reverse sync or forward-fix.

### 45.3. Side Effects Outside the Database

Payments, emails, Kafka events, cache invalidations, and webhooks do not automatically roll back with database restores. Reconcile at the business layer, not MongoDB alone.

---

# PART V — SPECIALIZED RISKS

## 46. Unique Indexes and Duplicate Data

If the target enforces a unique index absent at the source:

```javascript
db.users.createIndex(
  { tenantId: 1, emailNormalized: 1 },
  { unique: true }
);
```

backfill will fail on source duplicates. Handle this by:

1. Detecting conflicts before migration.
2. Defining business resolution rules: merge, reject, or quarantine.
3. Recording decision audits and mappings.
4. Never deleting records automatically just to pass index builds.
5. Testing concurrent writers during cutover.

### 46.1. Never Build a Unique Index Over Duplicates Expecting Server Auto-Repair

MongoDB unique index builds fail on duplicate keys. Clean the data or adjust the schema properly first.

---

## 47. TTL and Retention During Migration

TTL cleanup runs asynchronously. A logically expired document may still linger at the source while the target TTL monitor purges it immediately post-import.

Consequences:

- Source/target counts diverge.
- Reconciliation flags false “missing target” errors caused by TTL.
- Backfill re-inserts a record right as source TTL deletes it.
- A unique key remains occupied at source while freed at target.

### 47.1. Choose a Policy

- Migrate expired docs or live docs only?
- Temporarily disable TTL on target during backfill?
- Must records stay under legal hold?
- At which timestamp are counts reconciled?
- Does CDC receive TTL delete events from source?
- When post-cutover does target TTL turn on?

Never treat TTL as second-accurate expiration or expect raw counts to match unconditionally.

---

## 48. Sharded Clusters and Routing

When source or target is sharded:

- Migrations scan across multiple shards.
- Cluster-level Change Streams coordinate behavior, resume tokens, and ordering via `mongos`.
- Unique indexes must obey shard key constraints.
- Upsert/delete filters must support proper shard routing.
- Balancers and resharding can impact performance.
- Config server metadata and target sharding configs must be deployed accurately.
- Never treat `mongodump --oplog` as a cluster-wide consistent sharded snapshot.

### 48.1. Avoid Hot Shards

If all migrated records funnel into a single shard key value, one target shard saturates despite idle capacity elsewhere in the cluster.

### 48.2. Cross-Shard Transactions

If business logic relies on cross-shard transaction semantics, a pipeline updating collections independently will not hold invariants continuously. Gate when targets become readable/writable.

---

## 49. Driver and BSON Compatibility

Easily overlooked conversion pitfalls:

| Type | Risk |
| --- | --- |
| `ObjectId` | Converted to string, breaking key/join matches |
| `Decimal128` | Converted to `double`, losing precision |
| BSON `Date` | Timezone / epoch millisecond shifts |
| `Int32` vs. `Int64` | Overflow or type mismatch |
| `Binary`/`BinData` | Wrong subtype encoding |
| Arrays | Unintended reordering |
| Nested documents | `null` vs. missing semantics |
| DBRef / references | Wrong target key mapping |
| UUID | Binary representation / subtype |
| Encrypted fields | Missing KMS/CSFLE keys |
| Time-series | Bucket, retention, and schema constraints |
| Collation | Different query, sort, and unique behavior |
| Text/search indexes | Require rebuilding beyond raw document data |

### 49.1. Test Lossless Conversion

Build fixtures covering null/missing, Unicode, boundary `Decimal128`, long arrays, optional fields, and timezone-edge Dates. Assert against BSON types and business rules, not plain JSON strings.

---

## 50. Change Streams and Schema Transformations

If source and target schemas differ, an update event such as:

```javascript
{
  $set: { "address.city": "Da Nang" }
}
```

may not map directly when the target extracts `addresses` into its own collection.

Build a transformation protocol:

- Identify affected target documents.
- Map source key → target keys.
- Apply in order.
- Enforce version/concurrency guards.
- Handle deletes and moves.
- Support rebuilding from source.
- Quarantine unknown schema versions.

### 50.1. Full-Document Transformation

One option is reading `fullDocument` and rebuilding target projections. Remember `updateLookup` is not an exact historical after-image and can be `null` if the document was deleted.

### 50.2. Transactional Consistency

If one source document fans out into multiple target documents, define target write atomicity or expose documents only once the entire group finishes.

---

## 51. Security and Compliance

Migrations often move sensitive records over networks and temporary storage.

Checklist:

- TLS for both source and target.
- Least-privilege roles for dump/CDC/write accounts.
- Secrets managed via environment variables or vaults.
- Never leak URI credentials into logs or shell history.
- Encrypt archive files and temporary staging files.
- Verify KMS/CMK key rotation and restore access.
- Enforce data residency and cross-region boundaries.
- Audit all migration operations.
- Enforce retention and securely delete temporary dumps post-verification.
- Restrict access to monitoring dashboards.
- Never log raw documents on diff mismatches.
- Separate CDC reader credentials from target writer credentials.
- Never run destructive restores or cleanups outside approved namespaces.

### 51.1. Dedicated Migration Identities

Grant migration accounts only necessary permissions. Never default to root/admin credentials out of convenience.

### 51.2. Temporary Dumps Are Real Data Copies

An `.archive.gz` file may hold PII, tokens, and financial records. Protect it as strictly as the primary database—never leave it on shared drives or public CI artifacts.

---

# PART VI — TESTING AND OPERATIONS

## 52. Pre-Migration Test Matrix

| Test Case | Scenario | Expected |
| --- | --- | --- |
| Initial copy | 1,000 docs, zero writes | Target matches all records |
| Update during backfill | Doc mutates post-scan | CDC catches up to latest version |
| Insert during backfill | New doc at end of scan | Not missed |
| Delete during backfill | Doc deleted | Target holds no stale record |
| Rapid updates | v1→v2→v3 | Final state is v3 |
| CDC restart | Crash after target write before token save | Replay causes zero harmful duplicates |
| Oplog lost | Consumer offline too long | Detects failure rather than silently skipping |
| Duplicate source keys | Target unique index rejects | Quarantined or resolved per policy |
| TTL expiration | Source/target monitors out of sync | Reconciled per retention policy |
| Changed BSON types | `Decimal128`/Date/`ObjectId` | Exact types and precision preserved |
| Shard routing | Upserts carry shard keys | No routing errors or conflicts |
| Concurrent writes | Two writers hit same key | Ordering/versions stay valid |
| Partial target outage | Target down while source live | Durable retry/backlog catches up |
| Cutover drain | In-flight source writes | Zero missed writes |
| Rollback rehearsal | Fresh writes post-cutover | Zero acknowledged writes lost |
| Application canary | Shadow reads / critical endpoints | Diffs and latency within SLO |

---

## 53. Failure Injection: Where to Test Faults?

Migration workers should test:

1. Process crash before applying event.
2. Crash after applying event yet before checkpointing.
3. Target timeout after write actually succeeded.
4. Network partition between source and target.
5. Primary failover while holding a change stream.
6. Source oplog history expiration.
7. Target disk full / IOPS throttling.
8. Schema validator or unique constraint rejecting a document.
9. Poison document causing decode/transform error.
10. Retry queue backlog exceeding thresholds.
11. Concurrent source updates arriving out of order at target.
12. Unsupported DDL changes.
13. Worker lease timeout with two instances applying concurrently.
14. Aborted cutover mid-flight.
15. App connection strings cached long past switch.
16. Broken reverse sync during rollback.

### 53.1. Never Use Production for Unapproved Chaos Testing

Run fault tests in staging or approved drills. Never sever a production primary's network “to see if CDC recovers” without a change ticket and rollback plan.

---

## 54. Monitoring Migrations

Key dashboards:

| Metric | Purpose |
| --- | --- |
| Backfill docs/s | Measure copy rate |
| Backfill checkpoint | Detect stalled jobs |
| Source write rate | Estimate CDC load |
| CDC queue depth/age | Track lag |
| Last durable resume token | Verify resumability point |
| Oldest unprocessed event age | Spot oplog-expiration risk |
| Source oplog window | Measure safety margin |
| Target apply errors | Surface unique/schema/permission errors |
| Retry/DLQ | Ensure failed records are never ignored |
| Mismatches by partition | Spot localized divergence |
| Target disk/CPU/IOPS | Capacity headroom |
| Critical API p95/p99 | End-user latency |
| Duplicate business effects | Correctness |
| Cutover readiness | Go/no-go decision |

### 54.1. Low Lag with Non-Empty DLQ Is Unsafe

A pipeline can apply 99.99% of events fast while dropping one critical transaction into DLQ. Never treat `lag = 0` as cutover-ready while unresolved errors exist.

### 54.2. Actionable Alerts

Examples:

```text
CDC lag > safe threshold
  -> Stop cutover
  -> Scale/repair consumer
  -> Check oplog window
  -> Do not drop source

Unresolved transform error
  -> Quarantine + investigate
  -> Reprocess from checkpoint
  -> Block final reconciliation

Target unique violation
  -> Inspect source/target key
  -> Apply explicit conflict policy
  -> Do not silently ignore
```

---

## 55. Choosing the Right Method by Scenario

### Scenario A: Moving 5 GiB in a 2-Hour Maintenance Window

- Writes can pause.
- Schema barely changes.
- Few collections.

**Approach:** verified dump/restore or backup restore, validate, cut over. Skip complex CDC if downtime fits cleanly.

### Scenario B: Moving 2 TiB with Continuous Writes

- Full copy takes hours/days.
- Tight RPO.
- Heavy writes.

**Approach:** initial copy + CDC or supported migration tooling; closely watch oplog window, durable capture, throughput, and final cutover barriers.

### Scenario C: Migrating Tenant-by-Tenant

- T1 canaries before T2.
- Application controls routing.
- Explicit ownership map exists.

**Approach:** tenant-by-tenant migration combining CDC/dual-write/outbox, shadow reads, and explicit writer ownership.

### Scenario D: Replicating to Search/Analytics

- Eventual consistency acceptable.
- Heavy schema transformation.
- Target is not a transactional source of truth.

**Approach:** CDC/streaming connector with an idempotent sink, DLQ, and rebuild path; avoid direct dual-write on every request.

### Scenario E: Redesigning Document Schema Within the Same Cluster

- Old and new collections share one MongoDB deployment.
- App can read both schemas temporarily.

**Approach:** expand–migrate–contract, backfill + change propagation, feature flags, and controlled read cutover. Short transactions can help for grouped writes within one deployment.

---

## 56. Exercise 1 — Choose a Strategy

A system has an 8 GiB database, a 3-hour maintenance window, and zero writes during that window.

**Question:** Is CDC required?

**Answer:** Not necessarily. Verified export/import or dump/restore is usually simpler and sufficient if duration, compatibility, and restore tests pass.

---

## 57. Exercise 2 — Gap Between Dump and Stream

A team dumps from 10:00 to 11:00, then starts Change Streams at 11:05.

**Question:** What is the risk?

**Answer:** Writes between 10:00 and 11:05 may be missed or inconsistent. Establish a snapshot boundary and capture changes from a point before/during backfill.

---

## 58. Exercise 3 — CDC Lag Exceeds Oplog Window

Backfill takes 24 hours, the oplog retains only ~6 hours of history, and the consumer does not persist events.

**Answer:** High risk of losing change history needed for replay. Increase oplog retention/capacity, stream/persist events continuously, or switch migration strategy/tooling.

---

## 59. Exercise 4 — Apply Before Checkpoint

Target apply succeeds, then the worker crashes before saving the resume token.

**Answer:** The event replays on restart; sink writes must be idempotent or commit offset and target together within supported transaction boundaries.

---

## 60. Exercise 5 — Save Token Before Apply

Worker saves the token first, then writes to target, which fails.

**Answer:** Events can be permanently skipped after restart. Never checkpoint before effects are acknowledged.

---

## 61. Exercise 6 — Delete Events

Source deletes an order; CDC consumer handles only inserts and updates.

**Answer:** Target keeps a stale ghost document. Map deletes/tombstones per schema and ordering rules.

---

## 62. Exercise 7 — Update Lookup

An update event for v2 is processed after the document already moved to v3.

**Answer:** `fullDocument: updateLookup` may return v3 instead of the exact v2 after-image. Use appropriate state replication, versioning, or pre/post-images.

---

## 63. Exercise 8 — Direct Dual-Write

Source write succeeds, target times out, API returns 500, client retries.

**Answer:** Risk of duplicates and unknown state. Design a single source of truth, idempotent request keys, durable retry/outbox, and reconciliation.

---

## 64. Exercise 9 — Transactions Across Two Clusters

Does a MongoDB transaction on the source cluster commit target writes on a separate cluster atomically?

**Answer:** No. Use outbox, connectors, or dedicated distributed coordination; never assume cross-cluster ACID.

---

## 65. Exercise 10 — Out-of-Order Events at Target

An order has versions 40 and 41. Target applies 41 first, then 40.

**Answer:** Final state is wrong even if each operation is idempotent. Enforce per-key ordering or version-gated conditional writes.

---

## 66. Exercise 11 — TTL Causes Count Skew

Source and target hold the same expired docs, yet the target TTL monitor deletes sooner.

**Answer:** Differing counts do not necessarily mean migration data loss. Reconcile per retention policy and consistent watermarks rather than raw counts alone.

---

## 67. Exercise 12 — CSV Loses Data Types

`Decimal128("19.99")` round-trips through CSV/spreadsheets and turns into floating-point `19.9900000002`.

**Answer:** CSV does not preserve BSON precision. Use BSON/Extended JSON with explicit type mappings or `BigDecimal` conversions per policy.

---

## 68. Exercise 13 — Same Document, New `_id`

Each retry generates a fresh target `ObjectId`.

**Answer:** Creates duplicate records. Use deterministic source→target key mappings and idempotency.

---

## 69. Exercise 14 — Cutover with Pending Errors

Dashboard shows lag = 0 on a partition while failed events sit in DLQ.

**Answer:** Not ready for cutover. Resolve/reprocess DLQ items and verify final source markers/partitions.

---

## 70. Exercise 15 — Rollback by Swapping URI Only

After target receives 10,000 new writes, the team points app URIs back to the old source.

**Answer:** The old source lacks post-cutover writes; you need reverse sync/reconciliation or a planned forward-fix.

---

## 71. Exercise 16 — Outbox Written After Business Write

App updates an order and crashes before inserting the outbox event.

**Answer:** Target may never receive the event. For guaranteed propagation, commit business writes and outbox events atomically in the same supported transaction.

---

## 72. Exercise 17 — Shadow Read Right After Write

Target has 5 seconds of eventual lag; immediate shadow reads flag mismatches.

**Answer:** Likely normal replication lag. Compare at aligned watermarks or lag tolerances rather than mistaking transient staleness for permanent data loss.

---

## 73. Exercise 18 — Migrating Before Indexing

Target enforces a new unique key while source holds duplicates.

**Answer:** Detect and resolve conflicts per business policy—never delete blindly or let events fail endlessly.

---

## 74. Exercise 19 — Lingering Old Writer

A scheduled job keeps writing to source post-cutover.

**Answer:** Creates split-brain data. Inventory all writers and block source writes upon ownership switch, or enforce explicit routing/CDC bridges.

---

## 75. Exercise 20 — One Document Splits Into Two Target Records

Migration turns one source order into order + invoice on target; only order succeeds.

**Answer:** Target violates invariants. Use a target transaction if supported, or staged publishing/completion markers with retries and reconciliation.

---

## 76. Pre-Migration Checklist

- [ ] Identified source/target topologies, versions, and FCV?
- [ ] Defined RPO/RTO and downtime budgets?
- [ ] Complete inventory of writers and consumers?
- [ ] Complete data and namespace inventory?
- [ ] Defined schema and transform versions?
- [ ] Planned `_id` and business-key mappings?
- [ ] Inventoried unique, partial, sparse, TTL, collation, and validators?
- [ ] Captured read/write throughput baselines?
- [ ] Verified restorable backups and key/KMS access?
- [ ] Verified Database Tools / CDC tool compatibility?
- [ ] Chosen snapshot consistency strategy?
- [ ] Verified sufficient target capacity and network bandwidth?
- [ ] Planned DDL freeze?
- [ ] Defined data privacy and retention policies?
- [ ] Completed staging rehearsal with representative data?

---

## 77. CDC / Dual-Write Checklist

- [ ] CDC start point established before backfill?
- [ ] Changes durably captured and persisted?
- [ ] Oplog window sufficient and monitored?
- [ ] Resume tokens checkpointed after apply?
- [ ] Retries, backoff, and DLQ implemented?
- [ ] Inserts, updates, replaces, and deletes handled?
- [ ] Policies defined for DDL and `invalidate`?
- [ ] Handled `null` `fullDocument` and `updateLookup` semantics?
- [ ] Per-key ordering / version guards enforced?
- [ ] Idempotent target apply?
- [ ] Bounded worker concurrency?
- [ ] Durable outbox used if dual-writing?
- [ ] External side effects made idempotent?
- [ ] Backfill/CDC overwrite races prevented?
- [ ] Per-partition checkpoints maintained?
- [ ] Lag and error monitoring active?
- [ ] Detection and rebootstrap plan for lost oplog history?

---

## 78. Cutover and Post-Verification Checklist

- [ ] Backfill completed across all partitions?
- [ ] CDC applied past final watermark?
- [ ] Zero unresolved DLQ/transform errors?
- [ ] Counts, hashes, and business aggregates matched?
- [ ] Unique, TTL, indexes, and validators aligned?
- [ ] Search and analytics indexes ready?
- [ ] Critical workflows passed smoke/integration tests?
- [ ] All source writers drained?
- [ ] Single writer authority active post-cutover?
- [ ] Routing, DNS, and config caches switched?
- [ ] Rollback boundary and reverse sync plan defined?
- [ ] Source protected read-only during rollback window?
- [ ] Alerts active for p95/p99, errors, and CDC?
- [ ] Access controls, KMS, and backups verified on target?
- [ ] Formal sign-off for ownership, retention, and decommissioning?

---

## 79. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| “Export/import is always a consistent backup.” | Depends on tooling, concurrent writes, and snapshot policy. |
| “`mongoexport` is just JSON `mongodump`.” | JSON/CSV omits full BSON metadata and indexes. |
| “Copying documents means migration is done.” | Indexes, constraints, security, catch-up, and cutover remain. |
| “Just start CDC after copying.” | Misses mutations between snapshot and stream start. |
| “CDC always gives exact historical full documents.” | `updateLookup` reflects current state, not historical after-images. |
| “Resume tokens live forever.” | Bound by oplog/change history and `invalidate` events. |
| “Checkpointing before apply is faster.” | Crashes drop events permanently. |
| “Idempotent apply removes ordering needs.” | Stale events can still overwrite newer state. |
| “Handling inserts/updates is enough.” | Deletes, DDL, and schema changes need policies. |
| “CDC lag = 0 means both DBs match.” | Faulty transforms or DLQ drops can hide divergence. |
| “Dual-write is a cross-database transaction.” | Zero atomicity across independent clusters. |
| “Writing both sides prevents divergence.” | Reordered writes or missed deletes still cause drift. |
| “App retries alone make dual-write safe.” | Needs idempotency, ordering, and durable retry queues. |
| “Outbox guarantees exactly-once automatically.” | Usually at-least-once; sinks must be idempotent. |
| “Equal counts mean equal data.” | Values and types can still differ. |
| “TTL deletes source and target simultaneously.” | TTL runs asynchronously per node clock/monitor. |
| “Target unique keys automatically match source.” | Must design indexes, partial filters, collation, and sharding. |
| “`ObjectId` is always commit order.” | False; client-generated IDs and clock skew exist. |
| “Adding workers always boosts throughput.” | Can saturate storage, CPU, or downstreams. |
| “Switching reads before writes is risk-free.” | Target may lag or lack write ownership. |
| “Rollback is just swapping connection strings.” | Target may hold post-cutover writes absent from source. |
| “Backup archives are not sensitive.” | They hold live data and require encryption/retention. |

---

## 80. Official References

1. [MongoDB Database Tools — mongodump](https://www.mongodb.com/docs/database-tools/mongodump/) — logical dumps, archives, gzip, and oplog limits.
2. [MongoDB Database Tools — mongorestore](https://www.mongodb.com/docs/database-tools/mongorestore/) — restore, namespace mapping, and oplog replay.
3. [MongoDB Database Tools — mongoexport](https://www.mongodb.com/docs/database-tools/mongoexport/) — JSON/CSV export and limitations.
4. [MongoDB Database Tools — mongoimport](https://www.mongodb.com/docs/database-tools/mongoimport/) — import modes, type handling, upserts.
5. [MongoDB — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/) — operations, resume tokens, pipelines, and topology.
6. [MongoDB — Change Streams Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/) — oplog, deployment, and operations.
7. [MongoDB — Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream) — `resumeAfter`, `startAfter`, and `invalidate` considerations.
8. [MongoDB — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images) — image options and retention.
9. [MongoDB — Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/) — history windows and replication.
10. [MongoDB — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — atomicity and session/transaction scope.
11. [MongoDB — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — business key constraints.
12. [MongoDB — TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/) — asynchronous retention cleanup.
13. [MongoDB — Sharded Cluster Unique Constraints](https://www.mongodb.com/docs/manual/core/index-unique/#sharded-clusters-and-unique-indexes) — shard key restrictions.
14. [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/) — consumption and resume.
15. [MongoDB Java Sync Driver — Bulk Write](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/) — batch errors and ordered/unordered writes.
16. [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/) — `withTransaction` and session scope.
17. [MongoDB Kafka Connector](https://www.mongodb.com/docs/kafka-connector/current/) — connector-based change pipelines.
18. [MongoDB mongosync](https://www.mongodb.com/docs/mongosync/current/) — supported migration paths and tool limits.
19. [MongoDB Atlas — Migrate or Import Data](https://www.mongodb.com/docs/atlas/import/) — Atlas migration options.
20. [MongoDB — BSON Types](https://www.mongodb.com/docs/manual/reference/bson-types/) — fidelity of `Decimal128`, Date, `ObjectId`, and Binary.

**Version note:** `mongosync` support, Change Stream pre/post-images, Database Tools options, resume semantics, sharding constraints, and connector versions vary across MongoDB Server/FCV/driver releases. Verify exact documentation for your source, target, and release before production migrations.

---

## 81. Summary

To migrate MongoDB data safely, match the mechanism to your requirements:

- **Export/import (`mongodump`/`mongorestore`, `mongoexport`/`mongoimport`)** fits static snapshots, maintenance windows, or controlled batch loads. It does not capture writes occurring after export.
- **CDC (Change Streams, connectors, or migration tools)** replicates ongoing changes during backfill, yet demands **a proper start point, durable capture, oplog retention, resume tokens, ordering, delete handling, and a catch-up barrier**.
- **Dual-write** supports gradual cutovers yet lacks atomicity across independent clusters. To prevent data loss, combine **single source of truth + outbox/durable retries + idempotency + version controls + reconciliation**.

Whichever path you choose, a migration is done only when **the target holds accurate data and behavior, all writers have switched ownership, unresolved errors are cleared, business workflows pass, backup/rollback posture is verified, and metrics stabilize**.

**A successful migration does not merely copy documents; it preserves the business integrity of your data throughout every live mutation.**
