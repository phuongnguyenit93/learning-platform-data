# Reading Large Datasets When Data Can Mutate Between Rounds

In MongoDB, an application may need to read millions of documents while other processes continuously insert, update, or delete data. A user reads the first page of an order list, then clicks "Next page". Between the two requests, a new order is created or an older order changes status. Without a clearly defined pagination strategy, results can **duplicate documents, skip documents, or fail to reflect the intended business point in time**.

This issue arises across many systems:

- A UI displaying the 20 newest orders while new orders are continuously created.
- An API returning a paginated customer list where accounts may be soft-deleted between requests.
- A large export job running for hours that must resume if the process stops.
- A worker processing every transaction in ID order while documents are constantly updated.
- A search service loading initial data and then streaming subsequent changes without losing events.

MongoDB provides **cursors**, `batchSize()`, `skip()/limit()`, **key-based pagination (keyset/seek pagination)**, read concerns, transactions, and change streams. No single option fits every requirement. Before selecting a technique, determine whether you **want to view live mutating data or pin a consistent snapshot at a point in time**.

## 1. Distinguishing Three Read Goals

Three requirements look similar at the API layer yet demand different guarantees.

### 1.1. Live Browsing

Users scroll through a list of posts or invoices. Upon reaching the bottom of page 1, they want records following the last item seen. If new records appear at the top of the list, they can click "Refresh" to view them.

Primary goals:

- Return consecutive pages quickly.
- Reduce duplicate records caused by page positional shifts.
- Keep the experience smooth without loading the entire collection.
- Accept that data may mutate between requests.

For this scenario, **keyset pagination with stable sorting** is usually appropriate.

### 1.2. Batch Scanning with Resumability (Resumable Scan)

A worker must read two million documents to transform data. The process might crash at document 700,000, so it must persist a checkpoint to restart.

Primary goals:

- Avoid re-reading everything from the start after a crash.
- Know which documents have already been safely processed.
- Provide retry handling that does not duplicate business side effects.
- Define whether records arriving during the scan belong in scope.

For this scenario, **keyset over an immutable key + checkpoints + idempotency** is typically used, sometimes paired with an **upper watermark** bounding the key range.

### 1.3. Point-in-Time Consistent Reading (Snapshot Export)

A report demands "all orders paid strictly as of 00:00 on the last day of the month". Documents modified after that timestamp must not alter the report figures.

Primary goals:

- All reads must observe **the same logical state**.
- Never mix older records with newer versions from different instants.
- Be able to account precisely for the cutoff state.

This scenario requires **appropriate snapshot reads/transactions or a fixed materialized dataset**. Merely adding `sort()` and `limit()` is insufficient.

| Goal | Primary technique | What it does NOT guarantee automatically |
|---|---|---|
| Live browsing | Seek pagination | Fixed snapshot |
| Resumable scan | Seek + checkpoint | Business-level exactly-once without idempotency |
| Bounded scan | Seek + watermark | Immunity from updates/deletes inside the key range |
| Snapshot export | Snapshot or immutable dataset | Holding a snapshot indefinitely at zero cost |
| Continuous sync | Initial scan + change streams | Exactly-once event processing without dedicated logic |

## 2. How Does a MongoDB Cursor Differ from an API Page?

When executing `find()`, MongoDB may return an **initial batch of results**, after which the client fetches more batches via `getMore`. Drivers typically manage these exchanges through a cursor object.

Example in `mongosh`:

```javascript
const cursor = db.orders.find(
  { tenantId: "T-A", status: "PAID" },
  { _id: 1, createdAt: 1, total: 1 }
)
.sort({ createdAt: 1, _id: 1 })
.batchSize(200);

try {
  while (cursor.hasNext()) {
    const order = cursor.next();
    print(order._id);
  }
} finally {
  cursor.close();
}
```

Key takeaways:

- `batchSize(200)` requests a target batch size; actual batches remain subject to message size limits and server/driver behavior.
- `hasNext()` may trigger the driver to fetch another batch once the current batch is consumed.
- The application holds only a slice of results in memory rather than loading everything into an array.
- `cursor.close()` frees server/client resources when no longer needed.

**A MongoDB batch is not synonymous with an API page.** An API returning 20 records may use one or multiple internal batches. Conversely, one batch may contain more records than the page the application wants to return.

### 2.1. Why Should You Avoid `toArray()` for All Data?

```javascript
// Risky on very large collections:
const allOrders = db.orders.find({ tenantId: "T-A" }).toArray();
```

The command above forces all results into client-side memory. With millions of large documents, the application can consume excessive RAM or suffer major latency spikes. For large jobs, iterate via a cursor or read checkpointed chunks.

### 2.2. Standard Cursors Do Not Automatically Freeze Data

A common misconception is: "Once `find()` is called, the server freezes all documents at that instant, so every later batch belongs to the initial snapshot."

This is **not a general guarantee of standard cursors**. When concurrent writers modify fields affecting the query or index scan, a long iteration can be affected by mutating data. Pages fetched via separate `find()` requests are even more clearly independent reads.

Cursors also have lifecycle, timeout, and session limits. A dropped network connection or server failover can invalidate an active cursor. For multi-request web APIs, prefer **logical continuation tokens** rather than trying to keep a server cursor open for a long time.

## 3. Stable Sorting Is the First Prerequisite

MongoDB does not promise result order when a query omits `sort()`. Even with `sort({ createdAt: -1 })`, multiple documents sharing the same `createdAt` tie on the sort key.

Example:

```javascript
db.orders.find(
  { tenantId: "T-A" }
)
.sort({ createdAt: -1 })
.limit(20);
```

If two orders share the exact same timestamp, MongoDB is not required to preserve the same relative order between them across queries. Fetching the next page using a single `createdAt` key can skip or duplicate tied records.

Standard solution:

```javascript
db.orders.find(
  { tenantId: "T-A" }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Now the `(createdAt, _id)` pair defines a total order **provided `_id` is unique within the result set**. MongoDB enforces `_id` uniqueness per collection rules; in sharded clusters, pay attention to cluster-wide uniqueness guarantees if the shard key does not include `_id`.

### 3.1. Sort Keys Must Be Sufficiently Stable

Two distinct requirements:

- **Having a unique tie-breaker:** every document has an unambiguous position in the sort.
- **Immutable keys:** a document's position does not shift mid-scan.

`_id` is immutable over a document's lifetime, whereas `updatedAt` changes on updates. Thus `sort({ updatedAt: -1, _id: -1 })` defines a deterministic order at any single instant, **yet documents can still change positions between pages**.

When you need stable scans, prefer `_id` or a `createdAt` designed to be immutable, paired with `_id` as tie-breaker. If your data allows editing `createdAt`, consider snapshots or duplicate/missing handling.

### 3.2. Consistent BSON Types Are Foundational

Never allow the same sort field to be a BSON Date in some documents and a String in others:

```javascript
{ _id: "A", createdAt: ISODate("2026-05-01T10:00:00Z") }
{ _id: "B", createdAt: "2026-05-01T10:00:00Z" }
```

MongoDB compares values according to BSON type comparison rules; it does not treat an ISO string as a Date automatically. Range predicates and seek cursors can behave unexpectedly. Use schema validation and data migrations to standardize Date, Number, String, and null/missing values on sort keys.

## 4. Skip/limit: Simple, Yet Prone to Duplicates or Skips

Offset pagination is typically written as:

```javascript
const page = 2;
const size = 3;

db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip((page - 1) * size)
  .limit(size);
```

Suppose at T1 the order is:

```text
[A, B, C, D, E, F, G, H]
```

Page 1, size 3:

```text
[A, B, C]
```

Before page 2, a new order `X` is inserted at the head:

```text
[X, A, B, C, D, E, F, G, H]
```

Page 2 calls `skip(3).limit(3)` and receives:

```text
[C, D, E]
```

**C is duplicated** because the offset positions shifted. If instead `A` is deleted:

```text
T2 after deleting A:
[B, C, D, E, F, G, H]

skip(3).limit(3) -> [E, F, G]
```

**D is skipped.** Both examples use a deterministic sort, yet item positions **shifted because the underlying result set changed**.

### 4.1. Large Offsets Also Incur Read Costs

```javascript
db.orders.find({ status: "PAID" })
  .sort({ createdAt: -1, _id: -1 })
  .skip(1000000)
  .limit(20);
```

To skip one million results, the server typically must walk through a large number of corresponding index keys/documents. Having an index does not make `skip(1000000)` a constant-time operation.

Offset still fits small lists, low-churn data, or UIs needing jumps to specific page numbers, provided the application accepts depth bounds and potential cross-page drift.

## 5. Keyset Pagination: Resuming After the Last Received Key

Instead of skipping N records of the **current** result set, keyset asks:

> Return records located **after the last record of the previous page** in the same order.

Example scanning ascending by `_id`:

```javascript
// First page.
db.events.find({ tenantId: "T-A" })
  .sort({ _id: 1 })
  .limit(20);
```

Suppose the last document has `_id = lastId`. Next page:

```javascript
db.events.find({
  tenantId: "T-A",
  _id: { $gt: lastId }
})
.sort({ _id: 1 })
.limit(20);
```

If sorting descending `{ _id: -1 }`, switch to `_id: { $lt: lastId }`.

Advantages:

- Inserts at the head of the list do not shift the seek cursor position like offset does.
- Indexes can locate the next key range directly.
- No need to skip millions of documents for deep pages.
- `lastId` can be saved as a checkpoint for batch jobs.

However, **keyset does not create a snapshot**: new records inserted past `lastId` can still appear; unread records deleted will vanish; and if sort fields are mutable, records can cross the cursor boundary.

### 5.1. ObjectId Is Not an Absolute Business Timestamp

`ObjectId` usually contains a timestamp component, yet it does not guarantee **commit order or global event order**:

- IDs may be generated client-side before sending the insert.
- Multiple IDs generated within the same second may not match business ordering.
- Backfilled data may carry older IDs or IDs issued by another system.
- `_id` can also be a String, UUID, or Number per schema.

Using `_id` to scan in ID order is reasonable. To sort by business time, use a stable Date field and add `_id` as a tie-breaker.

## 6. Multi-Field Keyset: createdAt and _id

Newest-orders lists commonly use:

```javascript
.sort({ createdAt: -1, _id: -1 })
```

Suppose the last document of the previous page has:

```javascript
{
  _id: ObjectId("65a12f010000000000000041"),
  createdAt: ISODate("2026-03-01T12:30:00Z")
}
```

The "after this document" predicate in descending sort is:

```text
createdAt < lastCreatedAt
OR
createdAt == lastCreatedAt and _id < lastId
```

Example:

```javascript
const lastCreatedAt = ISODate("2026-03-01T12:30:00Z");
const lastId = ObjectId("65a12f010000000000000041");

db.orders.find({
  tenantId: "T-A",
  status: "PAID",
  $or: [
    { createdAt: { $lt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $lt: lastId }
    }
  ]
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

If you only use `createdAt: { $lt: lastCreatedAt }`, other records with **the same `createdAt` and smaller IDs** are skipped. Using `$lte` without a tie-breaker can duplicate the last record of the previous page.

### 6.1. Indexes Supporting Keyset

Example:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

In this common query, `tenantId` and `status` are equality predicates; `createdAt` and `_id` serve as sort keys. Depending on other filters and real data distribution, different indexes may be needed; never create indexes blindly from one example while ignoring the overall workload.

### 6.2. Ascending Sort

If sorting by `{ createdAt: 1, _id: 1 }`, the continuation predicate flips direction:

```javascript
{
  $or: [
    { createdAt: { $gt: lastCreatedAt } },
    {
      createdAt: lastCreatedAt,
      _id: { $gt: lastId }
    }
  ]
}
```

The seek condition and sort **must match direction on each field**. When sorting mixes ascending and descending directions, build each component's comparison according to actual lexicographic order rather than swapping the same operator across all fields.

## 7. Page-Reading Function with Next Cursor in mongosh

Example implementing an order page fetch with configurable size:

```javascript
function fetchOrdersPage(tenantId, after, pageSize) {
  const filter = {
    tenantId: tenantId,
    status: "PAID"
  };

  if (after) {
    filter.$or = [
      { createdAt: { $lt: after.createdAt } },
      {
        createdAt: after.createdAt,
        _id: { $lt: after.id }
      }
    ];
  }

  const docs = db.orders.find(
    filter,
    {
      _id: 1,
      createdAt: 1,
      status: 1,
      total: 1
    }
  )
  .sort({ createdAt: -1, _id: -1 })
  .limit(pageSize + 1)
  .toArray();

  const hasMore = docs.length > pageSize;
  const items = docs.slice(0, pageSize);
  const tail = items.length
    ? items[items.length - 1]
    : null;

  return {
    items: items,
    hasMore: hasMore,
    next: hasMore && tail
      ? { createdAt: tail.createdAt, id: tail._id }
      : null
  };
}
```

This function demonstrates **reading `pageSize + 1` documents** to check whether more data follows. Return at most `pageSize` documents, and build the token from the keys of the **last actually returned document**.

Never use the keys of the extra (`pageSize + 1`th) lookahead document, or you will skip that document on the next page.

For production:

- Bound `pageSize` to prevent arbitrarily huge requests.
- Resolve tenant from the authenticated/authorized identity context, never trusting user-supplied parameters alone.
- Sign or validate continuation tokens; never accept arbitrary MongoDB filter predicates from clients.
- Parse timestamps into BSON Date and `_id` into `ObjectId` or its exact schema type.
- Define clear rules for missing, null, or mistyped `createdAt` fields.
- Optionally include a watermark and filter version if the pagination session needs bounds.

## 8. Data Mutating Between Rounds: Four Scenarios

### 8.1. New Insert Before the Cursor

T1:

```text
[A, B, C, D, E]
Page 1: A, B, C
Cursor: C
```

At T2, the newest item `X` is inserted:

```text
[X, A, B, C, D, E]
```

The keyset page after `C` returns `D, E`. It **does not duplicate `C`** as `skip/limit` might. However, `X` does not appear in subsequent scrolling. This is often the desired behavior for live feeds: users refresh from the top to see newer items.

### 8.2. New Insert Whose Key Falls After the Cursor

A backfill job inserts `Y` with an older `createdAt` falling after the cursor. The next page can see `Y` even though that record did not exist when page 1 was read.

Thus, keyset does not guarantee "every result existed as of time T1". It only positions the query by key values.

### 8.3. Hard Delete or Soft Delete Before Reading

If `D` has not been read yet and is physically deleted, the next page cannot return `D`. If the API filters `isDeleted: false` and `D` is soft-deleted, it likewise leaves the active result set.

This is acceptable for live lists. If a job must export "every document that existed at T1", use an appropriate snapshot or historical source.

### 8.4. Updating the Sort Key or Filter Field

Suppose sorting descending by `updatedAt`:

```text
T1: [A, B, C, D, E]
Page 1: [A, B, C]
Cursor = C
```

If `D.updatedAt` is updated to a timestamp newer than `C`, `D` moves **ahead of the cursor**. The next-page query seeking keys smaller than the cursor can **skip D**.

If `B`, already read, later has its sort key changed to something older than `C`, it can move **behind the cursor** and reappear on a later page.

Similarly, if `status` changes from `PAID` to `CANCELLED`, a document leaves the filter; changing the reverse way lets it enter mid-scan. **The `_id` tie-breaker only resolves duplicate sort keys—it cannot prevent sort fields from being mutated.**

## 9. Snapshots, Majority, and a Fixed Read Point

Many developers mistakenly assume `readConcern: "majority"` guarantees consecutive pages read from the same snapshot. That is **false**.

Example:

```text
T1: page 1 reads majority-committed records.
T2: a batch insert becomes majority-committed.
T3: page 2 reads with majority.
```

Both queries read majority-committed data, yet page 2 can observe a newer state than page 1. `majority` does not bind them into a single snapshot.

### 9.1. Concepts to Distinguish

| Mechanism | Primary effect | Does NOT automatically provide |
|---|---|---|
| `readConcern: "local"` | Reads local node state per deployment rules | Snapshot across requests |
| `readConcern: "majority"` | Reads data with majority-commit guarantees | Same timepoint across multiple pages |
| `readConcern: "snapshot"` | Enables reading a consistent snapshot within supported scope | Indefinite snapshot retention |
| Causally consistent session | Causal ordering across operations when conditions hold | Frozen snapshot for an entire scan |
| `readPreference` | Picks target node, e.g. primary/secondary | Snapshot consistency guarantees |

Reading from secondaries via `readPreference` can encounter replication lag. If requests hit different secondaries without appropriate session coordination, results can also vary due to differing replication states.

### 9.2. Snapshot Transactions

In MongoDB environments supporting snapshot transactions, a simple flow is:

```javascript
const session = db.getMongo().startSession();

try {
  const sessionDb = session.getDatabase(db.getName());
  const orders = sessionDb.getCollection("orders");

  session.startTransaction({
    readConcern: { level: "snapshot" }
  });

  const cursor = orders.find({
    tenantId: "T-A",
    status: "PAID"
  })
  .sort({ createdAt: 1, _id: 1 })
  .batchSize(200);

  while (cursor.hasNext()) {
    const order = cursor.next();
    // Process quickly within transaction boundaries.
  }

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (ignored) {
    // Transaction may have already ended due to the underlying error state.
  }
  throw error;
} finally {
  session.endSession();
}
```

The example above **is not a recommendation to hold a transaction open for hours to export millions of documents**. Long transactions incur resource costs, lifetime limits, and failure risks from snapshot history and write pressure. On supported versions and topologies, MongoDB also offers non-transactional snapshot reads with specific constraints; consult documentation for your exact version.

If you need a large fixed report as of T1, better alternatives may include:

- A snapshot backup or logical export frozen at a specific point in time.
- An immutable collection/dataset materialized for the export run.
- Supported point-in-time snapshot reads with bounded runtime and history retention.
- A snapshot + change-capture architecture when both an initial image and an ongoing change stream are needed.

## 10. Upper Watermark: Bounding the Key Range, Not a Snapshot

When a job only needs to scan IDs within the range existing at startup, you can record the highest key `H`:

```javascript
const newest = db.events.find(
  { tenantId: "T-A" },
  { _id: 1 }
)
.sort({ _id: -1 })
.limit(1)
.toArray();

const upperId = newest.length ? newest[0]._id : null;
```

If `upperId` exists, reads use:

```javascript
db.events.find({
  tenantId: "T-A",
  _id: {
    $gt: lastId,
    $lte: upperId
  }
})
.sort({ _id: 1 })
.limit(500);
```

Meaning: the job only scans IDs **greater than `lastId` and at most `upperId`**.

This excludes newly arriving documents with IDs above `H`. However:

1. Writers can still insert IDs **lower than `H`**.
2. Documents with IDs inside the range can still be updated or deleted.
3. Other filter fields like `status` can still change.
4. Reading `upperId` and scanning the data are not a single atomic snapshot operation.

Therefore, an upper watermark is a **scan-range bound**, not a guarantee that every document from T1 stays untouched.

If business rules forbid backfilling and keys are monotonically increasing and immutable, watermarks are very helpful. Otherwise, a stronger design is required.

## 11. Batch Jobs with Checkpoints After Safe Processing

A long-running scan job needs durable progress tracking; a server cursor is not a long-term checkpoint.

Example:

```javascript
// lastId loaded from persisted checkpoint.
const filter = { tenantId: "T-A" };

if (lastId !== null) {
  filter._id = { $gt: lastId };
}

const batch = db.customers.find(
  filter,
  { _id: 1, tenantId: 1, emailNormalized: 1 }
)
.sort({ _id: 1 })
.limit(500)
.toArray();
```

When paired with an upper watermark, the `_id` predicate must include both `$gt` and `$lte` as shown earlier.

### 11.1. Safe Checkpointing Sequence

```text
1. Read checkpoint lastProcessedKey.
2. Read batch after lastProcessedKey.
3. Process each document.
4. After the side effects of the document/batch are safely committed:
     persist the corresponding checkpoint.
5. Repeat.
```

If you save the checkpoint **before the side effect** and the worker crashes, documents already past the checkpoint can be skipped. If the side effect succeeds before saving the checkpoint, retries may reprocess the document. Thus, practical designs rely on **at-least-once delivery + idempotent processing**.

### 11.2. Idempotency Example

Suppose a job recomputes search cards for each user. Instead of appending a new record every run:

```javascript
db.searchCards.insertOne({
  userId: user._id,
  title: user.displayName
});
```

use a stable key:

```javascript
db.searchCards.updateOne(
  { _id: user._id },
  {
    $set: {
      title: user.displayName,
      sourceVersion: user.version
    }
  },
  { upsert: true }
);
```

Updating by the same ID helps avoid duplicate output records; however, if an older event arrives after a newer one, you also need `sourceVersion` guards or conditional updates so stale values never overwrite newer state. Stable IDs are only part of idempotency.

If side effects and checkpoints reside in two separate collections, you may need appropriate transactions or reconciliation/dedup workflows. Cursors themselves never guarantee downstream exactly-once semantics.

### 11.3. Per-Batch vs. Per-Document Checkpoints

| Checkpointing granularity | Benefit | Trade-off |
|---|---|---|
| After every document | Minimal replay on crash | High state-write frequency |
| After every batch | Lower checkpointing overhead | May replay an entire batch |
| Every N documents / interval | Balances both goals | Must clearly bound replay window |

Checkpoints should include filter/sort versions and necessary keys to avoid resuming under changed query logic across deployments.

Example metadata:

```javascript
{
  _id: "reindex-users-T-A",
  tenantId: "T-A",
  filterVersion: 2,
  sort: { _id: 1 },
  lastProcessedId: ObjectId("65a12f010000000000000041"),
  upperId: ObjectId("65a12f010000000000000099"),
  status: "RUNNING",
  processedCount: NumberLong("150000"),
  updatedAt: ISODate("2026-11-14T08:00:00Z")
}
```

This is an application-defined schema, not a built-in MongoDB checkpoint document.

## 12. When Sort Keys Change: Seek Alone Is Insufficient

If you must scan by `updatedAt` while writers actively modify it, documents can jump across the cursor boundary and cause duplicates or misses.

Solutions depending on requirements:

- **Immutable keys:** scan by `_id` or an immutable `createdAt`.
- **Snapshots:** hold a consistent version of data as of time T.
- **Versioned records:** every mutation creates an immutable versioned record with its own ID.
- **Change streams:** consume insert/update/delete events instead of scanning live data to catch all mutations.
- **Replay/dedup:** tolerate re-reads and track versions/IDs so effects are not duplicated.
- **Periodic reconciliation:** useful when eventual consistency is acceptable yet drift must be detected.

Do not try to solve this by enlarging page sizes or adding `_id` and claiming all risk is gone. Deterministic ordering at an instant differs from **immutability over time**.

## 13. Change Streams for Continuous Synchronization

When you need changes occurring after an initial data load, MongoDB supports **change streams** on eligible deployments. A change stream observes mutation events and provides resume tokens.

Example:

```javascript
const changeStream = db.orders.watch(
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

while (changeStream.hasNext()) {
  const event = changeStream.next();

  printjson({
    type: event.operationType,
    key: event.documentKey,
    token: event._id
  });

  // Process the event before marking the resume token as committed.
}
```

Important notes:

- Requires a replica set or sharded cluster/deployment supporting change streams.
- `fullDocument: "updateLookup"` fetches the current document at lookup time, not necessarily the exact image at the moment the update occurred.
- Delete events include `documentKey`, not the full deleted document.
- Resume tokens depend on available change history/oplog retention and server config; you cannot resume indefinitely once history is purged.
- Events can be re-delivered when consumers retry or reconnect; idempotent handling is required.
- Saving a resume token before the event's side effects complete safely can lose updates on a crash.

### 13.1. Initial Scan + Stream Must Handle the Overlap Window

A typical sync pipeline:

```text
MongoDB source
   |
   +--> Initial snapshot/scan ------> initial target data
   |
   +--> Change stream -------------> apply insert/update/delete
                                     occurring after the right anchor
```

If you **scan first and open the stream afterward**, changes occurring between the two steps can be lost. If you **open the stream first and scan afterward**, you must buffer or deduplicate events while preserving apply order between snapshot and events.

A sound CDC pipeline defines the start point, matching snapshot marker, token persistence, dedup/version checks, and resync capability. Simply running `find()` followed by `watch()` does not guarantee zero lost events.

## 14. Counts and Final Pages When Data Mutates

Traditional paginated APIs often return:

```json
{
  "items": [],
  "page": 3,
  "size": 20,
  "total": 1742,
  "totalPages": 88
}
```

Yet `total` is computed by a separate read:

```javascript
db.orders.countDocuments({
  tenantId: "T-A",
  status: "PAID"
});
```

If inserts, updates, or deletes occur between counting and fetching the page, the total may not accurately describe the set of returned items. Across subsequent requests, the total keeps changing.

For live scrolling, the contract may simply be:

```json
{
  "items": [],
  "nextCursor": "opaque-token",
  "hasMore": true
}
```

If the product still requires `total`, clarify that it represents the total at **count time** (or approximate/snapshot-bound), rather than implicitly promising fixed page counts.

When `hasMore: false` at T1, it does not mean the collection will never receive new documents. To see new records at the head, clients should refresh or subscribe to a separate event stream.

## 15. Continuation Tokens: Never Trust Unvalidated Client Data

A well-structured token represents a position in logical ordering:

```json
{
  "version": 1,
  "tenantId": "T-A",
  "status": "PAID",
  "sort": ["createdAt:desc", "_id:desc"],
  "after": {
    "createdAt": "2026-03-01T12:30:00.000Z",
    "id": "65a12f010000000000000041"
  },
  "expiresAt": "2026-11-15T00:00:00.000Z"
}
```

This is the **pre-encoded payload**, not a recommendation to expose raw JSON to clients. Production APIs typically issue opaque signed tokens or equivalent authenticated structures.

Validation workflow:

1. Authenticate the user and verify tenant access permissions.
2. Verify token signature, version, and expiration.
3. Ensure the token's filter/sort matches the requested endpoint and parameters.
4. Parse Date back as UTC and ID back to its exact BSON type.
5. Build the seek predicate strictly from allowlisted fields.
6. Cap items per page and never let a token escalate tenant permissions.

**Base64 is only a representation encoding, not a security signature.** Clients can tamper with Base64 payloads freely if no integrity verification exists. Never embed unnecessary secrets inside tokens.

An API token describes a **continuation key**, not a server cursor ID with an unlimited lifetime.

## 16. Choosing Indexes by Filter, Sort, and Workload

For an order listing page:

```javascript
db.orders.find({
  tenantId: "T-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

A candidate index:

```javascript
db.orders.createIndex({
  tenantId: 1,
  status: 1,
  createdAt: -1,
  _id: -1
});
```

Verify with:

```javascript
db.orders.find({
  tenantId: "T-A",
  status: "PAID"
})
.sort({ createdAt: -1, _id: -1 })
.limit(20)
.explain("executionStats");
```

Observe:

| Field in explain | Question |
|---|---|
| `winningPlan` | Which plan was selected? |
| `IXSCAN` | Is an appropriate index scanned? |
| `FETCH` | Must documents be fetched outside the index? |
| `COLLSCAN` | Is a collection scan occurring? |
| `SORT` | Is there an extra memory-consuming sort stage? |
| `totalKeysExamined` | How many index keys were examined? |
| `totalDocsExamined` | How many documents were examined? |
| `nReturned` | Did it return the expected count? |

Two-field seeks typically use `$or`. The query planner may evaluate branches using different plans; efficiency depends on server version, data distribution, and indexes. Never see one `IXSCAN` and assume the entire query is optimal if heavy `FETCH` or `SORT` stages remain.

### 16.1. Projection Cuts Payload Size, Not Necessarily All I/O

```javascript
db.orders.find(
  { tenantId: "T-A" },
  { _id: 1, createdAt: 1, total: 1 }
)
.sort({ createdAt: -1, _id: -1 })
.limit(20);
```

Projection prevents the client from downloading large unused arrays or subdocuments. If an index covers filter, sort, and projection, some queries can avoid `FETCH`. However, projection does not mean the storage engine reads only a few bytes of the underlying BSON record; inspect the actual execution plan.

### 16.2. Sharded Clusters Add Merge Overhead

In sharded clusters, queries may have to read from multiple shards and merge sorted streams. The shard key governs targeted routing vs. scatter-gather, and per-shard indexes do not eliminate coordination overhead.

If most queries filter by `tenantId`, an appropriate shard key can enable targeted routing, though it must also balance write load and avoid hot shards. Keyset pagination does not automatically create a distributed snapshot while shards mutate concurrently.

## 17. Cursor Lifecycle and Timeouts in Long Jobs

Server cursors can expire due to timeouts, sessions, or operational events. Options like `noCursorTimeout()` do not remove every session and connection limit.

When writing long jobs:

- Close cursors on completion or errors.
- Do not hold cursors idle for long periods while calling external APIs.
- Size batches considering byte payload, not just document count.
- Avoid calling `toArray()` on entire collections.
- Support recreating the query from checkpoints if a cursor is lost.
- Measure round trips, memory, and latency when tuning batch size.
- Bound snapshot/transaction duration if using those mechanisms.

Example:

```javascript
const cursor = db.events.find({
  tenantId: "T-A"
})
.sort({ _id: 1 })
.batchSize(500);

try {
  while (cursor.hasNext()) {
    const event = cursor.next();
    // Process event, persist checkpoint per job contract.
  }
} finally {
  cursor.close();
}
```

In Java applications, use cursor-closing patterns like `try-with-resources` where supported by the `MongoCursor` type. On mid-run failures, recover via **persisted checkpoint keys**, not old server cursor IDs.

## 18. Selecting a Solution by Scenario

| Scenario | Approach | Limitation to disclose |
|---|---|---|
| Post list receiving new inserts | Keyset on `createdAt + _id` | Refresh to see new posts ahead of cursor |
| Product list allowing soft deletes | Keyset + active filter | Unread documents may leave the result set |
| Small set needing pages 1–10 directly | `skip/limit` | Can drift on concurrent inserts/deletes |
| Worker migrating millions of accounts | Keyset on immutable ID + checkpoint | Requires replay/idempotency handling |
| Scanning only keys in range at startup | Upper watermark | Not a snapshot against backfills/updates |
| Financial report frozen at a point in time | Snapshot / immutable dataset | Snapshot retention costs and limits |
| Syncing all changes to a search index | Initial scan + change streams | Must handle overlap window and resume tokens |
| Displaying total record count | Count with explicit point-in-time semantics | Live totals can change |
| Large sharded collection | Seek, indexes, proper shard key | Measure merge/routing and concurrency |

## 19. Practice Exercises

### Exercise 1 — Demonstrating Offset Drift

Create a `pageLab` collection with documents having `sequence` from 1 to 10. Fetch page 1 with `sort({ sequence: 1 }).limit(3)`. Before page 2, insert a document with `sequence` less than 1 or delete the leading record. Call `skip(3).limit(3)` and explain which documents can be duplicated or skipped.

### Exercise 2 — Keyset by `_id`

Create 100 documents with `_id` from 1 to 100. Write a loop fetching 10 documents per step via `_id: { $gt: lastId }`. Insert ID 105 mid-scan and delete ID 30 before reaching it. Contrast actual output with the dataset as of start time.

### Exercise 3 — Seek by `createdAt` and `_id`

Create multiple orders sharing the same `createdAt`. Write two queries fetching page 1 and page 2 under `{ createdAt: -1, _id: -1 }`. Explain why using only `createdAt: { $lt: lastCreatedAt }` drops records sharing that timestamp.

### Exercise 4 — Updating Sort Keys

Scan a collection by `updatedAt DESC`. After page 1, update an unread document so `updatedAt` jumps ahead of the cursor, and update an already-read document so it moves behind the cursor. Predict which items are missed or duplicated. Propose fixes using immutable keys or snapshots.

### Exercise 5 — Worker with Checkpoints

A job processes 500 documents per batch and crashes after processing 387 documents before saving its checkpoint. Explain why replay must be supported and how to design idempotent side effects. Propose where to store checkpoints and filter versions.

### Exercise 6 — Snapshot or Live?

An order dashboard only needs the latest PAID data. An accounting report requires exact state as of 00:00 on month-end. Pick a read strategy for each case and explain why live keyset pagination is insufficient for closing reports.

### Exercise 7 — Initial Scan Combined with Change Streams

Design a pipeline syncing MongoDB data to a search index: scan 1 million initial records, then continuously apply inserts/updates/deletes. Describe how to avoid losing events between phases, persist resume tokens, and handle duplicate events.

### Exercise 8 — Designing Continuation Tokens

Design a token for a multi-tenant API filtering `status: "PAID"` and sorting `createdAt DESC, _id DESC`. List required fields, token validation steps, and risks of Base64-encoding tokens without signing.

## 20. MongoDB Reference Documentation

- [db.collection.find()](https://www.mongodb.com/docs/manual/reference/method/db.collection.find/)
- [Cursor Methods](https://www.mongodb.com/docs/manual/reference/method/js-cursor/)
- [cursor.batchSize()](https://www.mongodb.com/docs/manual/reference/method/cursor.batchSize/)
- [cursor.skip()](https://www.mongodb.com/docs/manual/reference/method/cursor.skip/)
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/)
- [Snapshot Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern-snapshot/)
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Indexes and Query Optimization](https://www.mongodb.com/docs/manual/indexes/)

## Conclusion

When MongoDB data can mutate during reads, you cannot rely solely on `sort()`, `skip()`, and `limit()` and expect consecutive pages to behave like an immutable set. **Offset pagination** is vulnerable to positional shifting on inserts/deletes; **keyset pagination** resumes from the last received key and generally fits large datasets better, yet it remains affected by updates/deletes and is not a snapshot.

For live UIs, use deterministic ordering, matching indexes, and authorization-checked continuation tokens. For scan workers, use sufficiently immutable keys, post-effect checkpoints, and idempotent handling; watermarks bound the key range without preventing mutations inside it. For point-in-time reports, use snapshots or immutable datasets; for continuous sync, align initial scans and change streams cleanly across their boundary. Explicitly defining **freshness visibility, duplicate/miss tolerance, and read point-in-time** upfront is the foundation for reading large datasets safely.
