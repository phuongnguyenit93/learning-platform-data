# Event Structure and Distinguishing Insert, Update, Replace, and Delete in MongoDB Change Streams

## 1. Why Does an Application Need to Know How a Document Changed?

Suppose a product management application stores data in MongoDB. When a product is created, has its price updated, has its entire record replaced, or is deleted, multiple downstream systems need to know in order to take follow-up action:

- Sync the product to a search engine.
- Update caches and read models.
- Dispatch an event to a data-processing worker.
- Record a change trail for reconciliation.
- Update summary tables without rescanning the entire collection.

One approach is having the API explicitly publish an event after every write command. However, if multiple services, batch jobs, or administrative tasks write to the database, some changes may bypass that API. **Change Streams** allow a consumer to subscribe to notifications of MongoDB data changes through an officially supported interface.

Conceptual example:

~~~text
            MongoDB collection: products
                       |
                  Write operations
                insert/update/replace/delete
                       |
                       v
                   Change Stream
                       |
              +--------+---------+
              |                  |
              v                  v
         Search Index        Cache / Read Model
~~~

The most critical point is that **not every event contains the same set of fields**:

- **insert:** the new document typically appears in **fullDocument**.
- **update:** field-level changes are described in **updateDescription**; the full new document is not included by default.
- **replace:** the replacement document is presented as a full document in **fullDocument**, rather than a list of individual modified fields.
- **delete:** the deleted document does not appear in **fullDocument** by default; primarily **documentKey** is provided to identify the document.

If a consumer assumes every event has **fullDocument.status**, it will easily misbehave or crash on **delete** events.

### Lesson Objectives

After completing this lesson, you will be able to:

1. Read the general structure of a **change event**.
2. Distinguish the **_id resume token** from **documentKey._id**.
3. Understand **operationType** and the characteristic fields of the four main change types.
4. Know when **fullDocument**, **updateDescription**, and **fullDocumentBeforeChange** are present.
5. Handle **$set, $unset, $inc**, full-document replacement, deletion, and **upsert** operations.
6. Write a consumer with **resume tokens**, checkpointing, and idempotency.
7. Run a two-session **mongosh** lab to emit and observe all four event types.
8. Analyze limitations around oplog retention, failover, pre-/post-images, and event size.

> Exercises use a dedicated database **mongo_change_stream_lab** and collection **lab_items**. All data-modifying commands are scoped to the sample IDs in this lesson. Never run them against production or someone else's collections.

## 2. Prerequisites for Change Streams to Work

### 2.1. Replica Set or Sharded Cluster

Change Streams rely on MongoDB's replication infrastructure and change history, typically running on:

- A **Replica set**.
- A **Sharded cluster** via **mongos**.

A standard **standalone mongod** does not support Change Streams the way a replica set does. If your lab connection points to a standalone instance, switch to a properly configured replica set environment; you cannot simply pass a watch option and expect it to work.

### 2.2. Data Is Durably Committed Before Events Are Emitted

Change Streams deliver changes that have been **majority-committed** under MongoDB semantics. A write newly applied on the primary that is not yet majority-committed does not appear immediately in the stream.

This has two consequences:

- Consumers must not treat a Change Stream as a synchronous callback executing **before commit**.
- The moment the application issues a write can precede the moment the event reaches the consumer due to replication, streaming, scheduling, and network latency.

**Do not equate:** "A write command returned ACK `w:1`" and "The Change Stream has already emitted that event." Events reflect changes once Change Stream eligibility conditions are met.

### 2.3. Access Privileges

The consumer account must hold appropriate privileges to **watch/read** the collection or database for the chosen scope and server version. Operations like enabling pre-/post-images, modifying collection configuration, or reading administrative metadata require different privileges.

Do not grant cluster-wide administrative privileges to a worker solely so it can read events from one collection.

### 2.4. Watch Scope

MongoDB supports watching at different scopes:

~~~javascript
// Single collection only:
const streamA = db.getCollection("products").watch();

// Collections in the current database:
const streamB = db.watch();

// Entire deployment scope, where privileges and APIs permit:
// MongoClient.watch() in drivers, or the environment's equivalent API.
~~~

Do not call **db.watch()** and assume you only receive events from the `products` collection. Watch scope affects event volume, read privileges, and consumer overhead.

## 3. General Structure of a Change Event

A change event is **a BSON document** containing fields describing the change. Not every field appears in every event type.

Illustrative shape:

~~~javascript
{
  _id: { _data: "<opaque-resume-token>" },
  operationType: "update",
  clusterTime: Timestamp({ t: 1780000000, i: 3 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-01"
  },
  updateDescription: {
    updatedFields: {
      status: "active",
      quantity: 7,
      "attributes.color": "navy"
    },
    removedFields: ["obsoleteFlag"]
  }
}
~~~

**Note:** timestamps and tokens above are purely illustrative of shape. Resume tokens are server-generated opaque values; **never construct tokens from dummy strings** and never pass placeholder values to resume a real stream.

### 3.1. Table of Key Fields

| Field | Meaning | Where Present? |
| --- | --- | --- |
| **_id** | **Resume token** identifying the event's position in the stream | Crucial for resumption; not the document's `_id` |
| **operationType** | Type of change, e.g., insert/update/replace/delete | Primary change events |
| **clusterTime** | Logical BSON Timestamp associated with the event | Most data change events |
| **ns** | Namespace containing `db` and `coll` | Events tied to a corresponding namespace |
| **documentKey** | Key identifying the affected document; typically includes `_id` | insert/update/replace/delete |
| **fullDocument** | Full document per event semantics and watch options | Normally present for insert/replace; option-dependent for update |
| **updateDescription** | Description of field and array changes for an update | update |
| **fullDocumentBeforeChange** | Pre-change document if pre-images are enabled and requested | Certain update/replace/delete events when available |
| **wallTime** | Server-provided BSON Date timestamp on supporting versions | Depends on version and event type |
| **lsid, txnNumber** | Logical session/transaction context where applicable | May appear for operations inside transactions |
| **collectionUUID** | Collection identifier in supporting cases/options | Not intended as a business key by default |

Additional fields may appear in newer MongoDB versions or other event types. **Consumers should handle schemas based on `operationType` and watch options**, rather than assuming every event matches one rigid JSON sample.

### 3.2. Event-Level `_id` Is the Resume Token

Observe:

~~~javascript
{
  _id: { _data: "<resume-token>" },
  documentKey: { _id: "cs272-item-01" }
}
~~~

Two fields named `_id` serve **different roles**:

- **event._id:** token used to resume a Change Stream after the received position.
- **event.documentKey._id:** the `_id` of the business document, such as product `cs272-item-01`.

A single document can be updated 100 times, producing 100 events with distinct resume tokens while **documentKey._id remains the same ID**.

**Never use `documentKey._id` as a stream checkpoint.** Doing so gives you no way to tell which update of that document you last processed.

### 3.3. `ns` Identifies Where the Change Occurred

~~~javascript
ns: {
  db: "mongo_change_stream_lab",
  coll: "lab_items"
}
~~~

When watching at the database or deployment level, two events can share the same `documentKey._id` while coming from **two different collections**. Therefore, a multi-collection consumer must combine **namespace + documentKey** to identify the source entity.

Even for a consumer watching a single collection, `ns` remains useful for logging and detecting configuration mistakes.

### 3.4. `clusterTime` Is Not a Unique Event ID

**clusterTime** is a logical BSON Timestamp in MongoDB's internal protocol. Multiple operations in the same transaction can share the exact same `clusterTime`; in sharded clusters, ordering and metadata also carry specific subtleties.

Therefore:

- Never use **clusterTime alone** as a deduplication key across all change events.
- Never take a timestamp and try to synthesize a resume token from it.
- Do not treat it as an exact wall-clock time for latency SLAs.
- When exact resumption is needed, persist the full **event._id** in its proper BSON form.

**wallTime**, when returned, approximates wall-clock time, but neither replaces the resume token nor serves as a unique event key.

### 3.5. `documentKey` and Sharding

For unsharded collections, `documentKey` typically looks like:

~~~javascript
documentKey: { _id: "cs272-item-01" }
~~~

For sharded collections, `documentKey` can include **_id and the required shard key fields** according to MongoDB rules for that version.

Illustrative shape:

~~~javascript
documentKey: {
  _id: "order-001",
  tenantId: "t001",
  orderNo: "SO-001"
}
~~~

This is an illustration; do not assume every sharded deployment always has those exact three fields. Consumers must read the actual `documentKey` rather than hardcoding a schema that differs from their collection.

## 4. The Four Main `operationType` Values: Comparison Table

| Type | Typical Operations | `fullDocument` | `updateDescription` | `documentKey` |
| --- | --- | --- | --- | --- |
| **insert** | `insertOne`, `insertMany`, `upsert` creating a new doc | Usually the newly inserted document | No | Yes |
| **update** | `updateOne` with `$set`/`$inc`/`$unset`, etc. | **Not included by default**; can be requested via options | **Yes** | Yes |
| **replace** | `replaceOne` replacing a document | Usually the replacement document | No field-level diff like `updateDescription` | Yes |
| **delete** | `deleteOne`/`deleteMany` | **No deleted document in `fullDocument` by default** | No | Yes |

**Note:** looking solely at the API call name is not always enough to classify the event. For example, an **upsert** emits **insert** if the server creates a new document, or **update/replace** if it modifies an existing document. Always handle events by their actual **operationType**.

### 4.1. Consumer Decision Flow

~~~text
                Change Event
                     |
             event.operationType
                     |
   +----------+------+------+----------+
   |          |             |          |
 insert     update        replace     delete
   |          |             |          |
 fullDocument updateDescription fullDocument documentKey
   |          |             |          |
 create index patch/fetch  rebuild     delete index/
 or cache     as needed    snapshot    cache key
~~~

This is **recommended logic**. A search indexer might always choose to **rebuild from `fullDocument`** when `updateLookup` is enabled rather than applying patches manually, depending on consistency needs and tolerance for stale data.

## 5. Insert: A New Document Appears

### 5.1. Source Operation

~~~javascript
db.lab_items.insertOne({
  _id: "cs272-item-04",
  dataset: "change-stream-v1",
  sku: "P-004",
  status: "draft",
  quantity: 3,
  attributes: { color: "white" }
});
~~~

### 5.2. Illustrative Event

~~~javascript
{
  _id: { _data: "<token-insert>" },
  operationType: "insert",
  clusterTime: Timestamp({ t: 1780000001, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-04"
  },
  fullDocument: {
    _id: "cs272-item-04",
    dataset: "change-stream-v1",
    sku: "P-004",
    status: "draft",
    quantity: 3,
    attributes: { color: "white" }
  }
}
~~~

The document in **fullDocument** represents the inserted record. An `insert` event needs no **updateDescription**, because there were no prior fields being modified to list.

### 5.3. How to Handle It

A consumer synchronizing a search index can:

1. Read **documentKey._id** to determine the source ID.
2. Read **fullDocument** as the payload to build an index record.
3. Use **upsert** or an idempotent sink operation to avoid failures if the event is redelivered after a reconnect.
4. Checkpoint the resume token only after processing succeeds according to policy.

**Never** use `event._id` as the product ID—that is the resume token, not the business ID.

### 5.4. `insertMany` Can Emit Multiple Insert Events

If the application executes:

~~~javascript
db.lab_items.insertMany([
  { _id: "a", status: "draft" },
  { _id: "b", status: "draft" }
]);
~~~

The Change Stream emits **two `insert` events**, one per document—not a single event containing an array of documents just because `insertMany` was called. Under batching or transactions, tokens, ordering, and `clusterTime` have nuances depending on server version and how operations commit.

## 6. Update: Field-Level Changes, Not Necessarily the Full Document

### 6.1. Source Operation

~~~javascript
db.lab_items.updateOne(
  { _id: "cs272-item-01" },
  {
    $set: {
      status: "active",
      "attributes.color": "navy"
    },
    $inc: { quantity: 2 },
    $unset: { obsoleteFlag: "" }
  }
);
~~~

### 6.2. Illustrative Event

~~~javascript
{
  _id: { _data: "<token-update>" },
  operationType: "update",
  clusterTime: Timestamp({ t: 1780000002, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-01"
  },
  updateDescription: {
    updatedFields: {
      status: "active",
      quantity: 7,
      "attributes.color": "navy"
    },
    removedFields: ["obsoleteFlag"]
  }
}
~~~

**updatedFields** contains the **resulting new values** of modified paths. For example, with **$inc: {quantity:2}**, `updateDescription` shows **quantity:7**, not "+2".

**removedFields** lists the names of removed fields, such as fields targeted by `$unset`. It does not contain their previous values.

### 6.3. Do Not Treat `updateDescription` as the Whole Document

The actual document after the update may be:

~~~javascript
{
  _id: "cs272-item-01",
  dataset: "change-stream-v1",
  sku: "P-001",
  status: "active",
  quantity: 7,
  attributes: {
    color: "navy",
    size: "M"
  },
  labels: ["new", "web"]
}
~~~

Meanwhile, `updateDescription` only describes what changed. If a consumer writes:

~~~javascript
searchIndex.replace("cs272-item-01", event.updateDescription.updatedFields);
~~~

it risks **wiping out fields absent from the delta**, such as `sku`, `labels`, or `attributes.size`.

To keep a full document synchronized, the consumer must either:

- Apply a semantically accurate **patch** to its retained copy, handling dotted paths, `removedFields`, and array changes; or
- Request **fullDocument** via an appropriate option while understanding lookup consistency limitations.

### 6.4. How Do `$set`, `$inc`, and `$unset` Appear?

| MongoDB Command | What Consumers Typically See in `updateDescription` |
| --- | --- |
| **$set: {status:"active"}** | `updatedFields.status = "active"` |
| **$inc: {quantity:2}** | `updatedFields.quantity =` final post-increment value |
| **$unset: {obsoleteFlag:""}** | `removedFields` contains `"obsoleteFlag"` |
| Nested field update | Path may use dot notation, e.g., `"attributes.color"` |
| Array structural change | Index paths, array values, or `truncatedArrays` depending on operation/version |

Do not tightly couple a consumer to an assumption that one MongoDB update operator always emits one exact entry in `updatedFields`. MongoDB describes **observable state changes** in the event, rather than promising a one-to-one mapping from source operators to output fields across all versions.

### 6.5. `removedFields` Is Not a List of Deleted Documents

When **$unset: {obsoleteFlag:""}** runs, `operationType` is still **"update"**. The `obsoleteFlag` field was removed from the document, but document `cs272-item-01` **still exists**.

Only when **deleteOne** removes the entire document is `operationType` equal to **"delete"**.

Confusing these two cases can cause a consumer to delete an entire search index record merely because one field was `$unset`.

### 6.6. Nested Fields and Dot Notation

An event may contain:

~~~javascript
updateDescription: {
  updatedFields: {
    "attributes.color": "navy"
  }
}
~~~

This path represents a nested object change under MongoDB semantics. **Never** write:

~~~javascript
copy["attributes.color"] = "navy";
~~~

and expect `copy.attributes.color` to update. In a plain JavaScript object, that creates a top-level literal property named **"attributes.color"**.

A patch processor must understand nested paths, special field names, and arrays. If your schema permits field names containing literal dots or special characters, path interpretation becomes more subtle; newer server versions/events can provide extra metadata like **disambiguatedPaths** when requested/supported.

### 6.7. Arrays and `truncatedArrays`

When an update shortens an array, events on supporting versions may include:

~~~javascript
updateDescription: {
  updatedFields: {},
  removedFields: [],
  truncatedArrays: [
    { field: "labels", newSize: 2 }
  ]
}
~~~

This is an **illustrative example** of truncation metadata, not a guarantee that every `$pop` or `$pull` produces that exact shape. Array change reporting depends on how the update executed and the MongoDB version.

Consumers applying array deltas manually must consult documentation for their server version and test operations such as:

- Appending elements to an array.
- Modifying elements by index.
- Removing elements.
- Truncating array length.
- Replacing an entire array.

**Never** apply only `updatedFields` while ignoring `truncatedArrays` if you aim to maintain an exact replica.

## 7. Replace: Replacing the Entire Document, Not Patching Fields

### 7.1. Source Operation

~~~javascript
db.lab_items.replaceOne(
  { _id: "cs272-item-02" },
  {
    _id: "cs272-item-02",
    dataset: "change-stream-v1",
    sku: "P-002",
    status: "archived",
    quantity: 0,
    attributes: { color: "gray" }
  }
);
~~~

**replaceOne** replaces the matched document with the **replacement document**. Old fields omitted from the replacement disappear from the document, subject to special constraints like `_id`.

For example, if before the replacement the document had:

~~~javascript
{
  _id: "cs272-item-02",
  sku: "P-002",
  status: "draft",
  quantity: 2,
  legacy: "temporary",
  attributes: { color: "red", size: "L" }
}
~~~

after the replacement above, **legacy** and **attributes.size** no longer exist.

### 7.2. Illustrative Event

~~~javascript
{
  _id: { _data: "<token-replace>" },
  operationType: "replace",
  clusterTime: Timestamp({ t: 1780000003, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-02"
  },
  fullDocument: {
    _id: "cs272-item-02",
    dataset: "change-stream-v1",
    sku: "P-002",
    status: "archived",
    quantity: 0,
    attributes: { color: "gray" }
  }
}
~~~

Key distinctions:

- **operationType = "replace"**, not `"update"`.
- **fullDocument** carries the replacement document.
- There is no **updateDescription** listing individual modified fields as in an update event.

### 7.3. Why Must `replace` Be Handled Differently from `update`?

Suppose the target system holds:

~~~javascript
{
  id: "cs272-item-02",
  status: "draft",
  quantity: 2,
  legacy: "temporary"
}
~~~

If a consumer receives `replace` and merely merges fields from `fullDocument` into the old target object, **legacy** can linger in the target system even though the source document removed it.

Therefore, for a **replace event**, the standard approach is to **replace the entire snapshot** in the target system rather than applying an update-style merge patch.

### 7.4. Update Differs from Replace Even When Final Values Match

Two operations may produce the exact same final document:

~~~javascript
// Update only a few fields.
db.lab_items.updateOne(
  { _id: "cs272-item-02" },
  { $set: { status: "archived", quantity: 0 } }
);

// Replace the entire document with a new version.
db.lab_items.replaceOne(
  { _id: "cs272-item-02" },
  {
    _id: "cs272-item-02",
    dataset: "change-stream-v1",
    sku: "P-002",
    status: "archived",
    quantity: 0,
    attributes: { color: "gray" }
  }
);
~~~

However, their **change semantics** differ: `update` preserves untouched fields, whereas `replace` redefines the document state from the replacement. Do not guess between them merely by comparing two fields like `status` and `quantity`.

## 8. Delete: Key Retained for Identification, Document Absent by Default

### 8.1. Source Operation

~~~javascript
db.lab_items.deleteOne({
  _id: "cs272-item-03"
});
~~~

### 8.2. Illustrative Event

~~~javascript
{
  _id: { _data: "<token-delete>" },
  operationType: "delete",
  clusterTime: Timestamp({ t: 1780000004, i: 1 }),
  ns: {
    db: "mongo_change_stream_lab",
    coll: "lab_items"
  },
  documentKey: {
    _id: "cs272-item-03"
  }
}
~~~

**There is no `fullDocument`** in a default delete event. MongoDB cannot fetch the current document for a record that was just deleted as it can for an insert. If a consumer executes:

~~~javascript
const id = event.fullDocument._id;
~~~

on a delete event, the code throws an error because **fullDocument does not exist**.

**The right way to identify a deleted document** is via **event.documentKey._id** along with namespace and shard key when applicable.

### 8.3. Handling Deletes in Target Systems

~~~javascript
if (event.operationType === "delete") {
  const sourceId = event.documentKey._id;

  // Pseudocode for a search index adapter:
  // await index.deleteById(sourceId);
}
~~~

Deletion in the target system should be **idempotent** whenever possible: deleting an already absent ID must not raise an unrecoverable error. This matters because consumers can receive the same event again during resume, checkpoint recovery, or retries.

### 8.4. What If Pre-Delete Data Is Required?

If business logic needs the **previous `status`, `sku`, or `tenantId`** of a deleted document, inspecting a default delete event is not enough.

Options:

1. **Pre-images**: enable pre-change document capture on supporting MongoDB versions and request **fullDocumentBeforeChange**.
2. **Soft-delete model**: flip `status`/`isDeleted` via an update so the document remains inspectable before physical cleanup.
3. **Emit an audit/outbox event** inside the same transaction as the business operation when stronger guarantees are required.
4. **Retain metadata in the read model** and delete by `documentKey` without needing to re-read the deleted source document.

You cannot reliably call **findOne(_id)** after a delete to fetch old attributes: the document is already gone, so `findOne` typically returns null.

## 9. `fullDocument`: When Is It Present and When Is It Absent?

### 9.1. Default Behavior

With a default change stream:

~~~javascript
const stream = db.lab_items.watch();
~~~

Summary:

| `operationType` | Default `fullDocument` |
| --- | --- |
| **insert** | Usually contains the inserted document |
| **update** | Does not contain the full document by default |
| **replace** | Usually contains the replacement document |
| **delete** | Does not contain the deleted document |

**Do not use `fullDocument` presence to classify `operationType`.** Always check **operationType** first, then read the appropriate fields.

### 9.2. `fullDocument: "updateLookup"`

When a consumer wants the current full document for an update, it can pass:

~~~javascript
const stream = db.lab_items.watch(
  [],
  { fullDocument: "updateLookup" }
);
~~~

For update events, MongoDB performs a lookup for the current full document after the event occurs and populates **fullDocument** if found under this option's semantics.

Keep in mind:

**`fullDocument` from `updateLookup` is not guaranteed to be an exact snapshot as of when the update event occurred.**

Example:

~~~text
T1: update quantity from 5 -> 7
T2: update quantity from 7 -> 9
T3: consumer processes event T1; updateLookup reads current document

fullDocument of event T1 may show quantity=9
because the lookup ran after the document was updated again.
~~~

Therefore:

- **updateDescription** reflects the exact changes associated with that update event.
- **updateLookup** retrieves current state near lookup time, not an immutable historical snapshot.
- If the document is deleted before lookup, **fullDocument** for the update can be **null**.
- For strict correctness, consider pre-/post-images or dedicated outbox events.

### 9.3. `fullDocument: "whenAvailable"` and `"required"`

On supporting MongoDB versions (e.g., pre-/post-images introduced in MongoDB 6.0), the **fullDocument** option can request the exact post-image tied to the change operation:

~~~javascript
const stream = db.lab_items.watch(
  [],
  { fullDocument: "whenAvailable" }
);
~~~

Or:

~~~javascript
const stream = db.lab_items.watch(
  [],
  { fullDocument: "required" }
);
~~~

General meaning:

- **whenAvailable:** returns the post-image when stored and still available; otherwise, the consumer must tolerate the field being absent per server semantics.
- **required:** requires the post-image; if it cannot be supplied, the stream returns an error as supported.

These options **differ from `updateLookup`**. They rely on collection-level **change stream pre-/post-image storage** and retention settings. Setting the watch option on the consumer **does not automatically enable image capture** on the source collection.

### 9.4. Do Not Use One Option for Every Requirement

| Requirement | Initial Option to Consider |
| --- | --- |
| Create search index from inserts | Default `fullDocument` |
| Sync an update via patch | `updateDescription`, with a proper patch processor |
| Refresh cache with near-current state | `fullDocument: "updateLookup"`, handling null/staleness |
| Need exact per-operation post-image for audit | Pre-/post-images with matching `fullDocument` option |
| Need document before delete | `fullDocumentBeforeChange` with pre-images |
| Only need to delete by ID | `documentKey` on delete, no images needed |

## 10. Pre-Images and Post-Images: Before/After Values

### 10.1. Pre-Image

A **pre-image** is the document **before** an update, replace, or delete operation, provided the feature is enabled and the image is stored/available in a supporting environment.

Example:

~~~javascript
{
  operationType: "delete",
  documentKey: { _id: "cs272-item-03" },
  fullDocumentBeforeChange: {
    _id: "cs272-item-03",
    dataset: "change-stream-v1",
    sku: "P-003",
    status: "active",
    quantity: 1
  }
}
~~~

With pre-images, a consumer can inspect the document prior to deletion, e.g., to emit an audit record or determine its prior tenant.

### 10.2. Post-Image

A **post-image** is the document **after** the change, tied to that specific operation—unlike looking up current state which might already include subsequent updates.

For strict per-event accuracy, a post-image lets consumers know the exact post-update state without manually applying nested/array paths.

### 10.3. Prerequisites

On versions supporting Change Stream pre-/post-images, the collection must be configured to retain images, and the consumer passes the corresponding options:

~~~javascript
// Configuration example solely for a dedicated lab collection.
// Requires appropriate admin privileges and supporting MongoDB version.
db.getSiblingDB("mongo_change_stream_lab").runCommand({
  collMod: "lab_items",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

**Never run `collMod` on production or shared collections solely for an exercise.** Enabling images incurs storage and retention overhead and requires operational sign-off.

Then the consumer can request:

~~~javascript
const stream = db.lab_items.watch(
  [],
  {
    fullDocumentBeforeChange: "whenAvailable",
    fullDocument: "whenAvailable"
  }
);
~~~

If strictness is mandatory, consider **"required"** and handle errors when images cannot be supplied. Availability depends on when the feature was enabled, when the event occurred, retention, and server image limits.

### 10.4. Cost and Retention

Pre-/post-images do not live forever. MongoDB applies separate retention and cleanup mechanisms, while Change Streams also depend on the oplog history window. A consumer paused for too long may no longer be able to resume or retrieve desired images.

Do not treat the pre-image store as an independent, infinite audit archive. For long-term compliance logging, build a dedicated durable audit/event store with appropriate access control, encryption, and retention policies.

## 11. `mongosh` Lab: Observing All Four Event Types

This is the main lab for this lesson. Use **two `mongosh` terminals** connected to **a practice replica set or sharded cluster**. One terminal opens the Change Stream; the other writes sample data.

### 11.1. Scope and Prerequisites

- Database: **mongo_change_stream_lab**.
- Collection: **lab_items**.
- Dataset: **change-stream-v1**.
- Documents with fixed IDs **cs272-item-01** through **cs272-item-04**.
- Connected to a replica set or `mongos`, not a standalone `mongod`.
- User has watch/read and CRUD privileges on the lab database.
- No need to drop collections, trigger failovers, or alter cluster settings.

First open a terminal and verify:

~~~javascript
const info = db.hello();

printjson({
  replicaSetName: info.setName,
  mongos: info.msg === "isdbgrid",
  isWritablePrimary: info.isWritablePrimary
});

if (!info.setName && info.msg !== "isdbgrid") {
  throw new Error(
    "A replica set or sharded cluster is required to practice Change Streams."
  );
}
~~~

### 11.2. Step A — Seed Data Before Watching

Run in Terminal B **before opening the watcher**:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_change_stream_lab");
  const items = lab.getCollection("lab_items");
  const tag = "change-stream-v1";

  const ids = [
    "cs272-item-01",
    "cs272-item-02",
    "cs272-item-03",
    "cs272-item-04"
  ];

  // Delete only the 4 fixed lab IDs; do not drop the collection.
  items.deleteMany(
    { _id: { $in: ids } },
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  items.insertMany(
    [
      {
        _id: "cs272-item-01",
        dataset: tag,
        sku: "P-001",
        status: "draft",
        quantity: NumberInt(5),
        obsoleteFlag: true,
        attributes: { color: "black", size: "M" },
        labels: ["new", "web"]
      },
      {
        _id: "cs272-item-02",
        dataset: tag,
        sku: "P-002",
        status: "draft",
        quantity: NumberInt(2),
        legacy: "temporary",
        attributes: { color: "red", size: "L" },
        labels: ["sale"]
      },
      {
        _id: "cs272-item-03",
        dataset: tag,
        sku: "P-003",
        status: "active",
        quantity: NumberInt(1),
        attributes: { color: "green" },
        labels: []
      }
    ],
    { writeConcern: { w: "majority", wtimeout: 10000 } }
  );

  printjson({
    seeded: items.countDocuments({ _id: { $in: ids } }),
    items: items.find(
      { _id: { $in: ids } },
      { _id: 1, sku: 1, status: 1, quantity: 1 }
    ).sort({ _id: 1 }).toArray()
  });
})();
~~~

**Expected result:** seeded = **3** (`item-01`, `item-02`, `item-03`). **item-04 does not exist yet** so the watcher receives an `insert` event for it later.

Seeding writes change entries into MongoDB's history, but because **the watcher is not open yet**, this lab does not treat them as the four target events. The goal is to observe operations occurring **after the watcher is established**.

### 11.3. Step B — Terminal A Opens the Change Stream

Open **another `mongosh` terminal**, connect to the same cluster, and run:

~~~javascript
const lab = db.getSiblingDB("mongo_change_stream_lab");
const items = lab.getCollection("lab_items");

const watchedIds = [
  "cs272-item-01",
  "cs272-item-02",
  "cs272-item-03",
  "cs272-item-04"
];

const changeStream = items.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        },
        "documentKey._id": { $in: watchedIds }
      }
    }
  ],
  {
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  }
);

print("Watcher opened; run the commands in Terminal B.");

for (let i = 0; i < 4; i++) {
  const event = await changeStream.next();

  print("Event " + (i + 1) + ": " + event.operationType);
  printjson({
    operationType: event.operationType,
    eventToken: event._id,
    clusterTime: event.clusterTime,
    ns: event.ns,
    documentKey: event.documentKey,
    fullDocument: event.fullDocument,
    updateDescription: event.updateDescription,
    fullDocumentBeforeChange: event.fullDocumentBeforeChange
  });
}

await changeStream.close();
print("Received all 4 events; watcher closed.");
~~~

**Important:** Terminal A will **block** at `changeStream.next()` until a matching event arrives. Do not keep pressing Enter or reopening the stream. Leave Terminal A running and proceed to Step C.

If Terminal A does not support top-level `await` due to an older shell runtime, upgrade `mongosh` or wrap in an async IIFE for your JavaScript runtime; the core flow remains **open the cursor first, then issue writes**.

### 11.4. Step C — Terminal B Performs Four Changes

**After Terminal A prints that the watcher is open**, run sequentially:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_change_stream_lab");
  const items = lab.getCollection("lab_items");
  const tag = "change-stream-v1";
  const wc = { w: "majority", wtimeout: 10000 };

  // 1. INSERT: new item-04.
  const inserted = items.insertOne(
    {
      _id: "cs272-item-04",
      dataset: tag,
      sku: "P-004",
      status: "draft",
      quantity: NumberInt(3),
      attributes: { color: "white" },
      labels: ["featured"]
    },
    { writeConcern: wc }
  );

  // 2. UPDATE: modify a few fields, remove obsoleteFlag.
  const updated = items.updateOne(
    { _id: "cs272-item-01", dataset: tag },
    {
      $set: {
        status: "active",
        "attributes.color": "navy"
      },
      $inc: { quantity: 2 },
      $unset: { obsoleteFlag: "" }
    },
    { writeConcern: wc }
  );

  // 3. REPLACE: replace all of item-02, dropping old legacy fields.
  const replaced = items.replaceOne(
    { _id: "cs272-item-02", dataset: tag },
    {
      _id: "cs272-item-02",
      dataset: tag,
      sku: "P-002",
      status: "archived",
      quantity: NumberInt(0),
      attributes: { color: "gray" }
    },
    { writeConcern: wc }
  );

  // 4. DELETE: delete the entire item-03 document.
  const deleted = items.deleteOne(
    { _id: "cs272-item-03", dataset: tag },
    { writeConcern: wc }
  );

  printjson({
    insertedId: inserted.insertedId,
    updateMatched: updated.matchedCount,
    updateModified: updated.modifiedCount,
    replaceMatched: replaced.matchedCount,
    replaceModified: replaced.modifiedCount,
    deletedCount: deleted.deletedCount
  });
})();
~~~

**Expected write-side results starting from the seeded state:**

| Operation | Write-Side Result |
| --- | --- |
| `insertOne` item-04 | insert succeeded |
| `updateOne` item-01 | `matchedCount=1`, `modifiedCount=1` |
| `replaceOne` item-02 | `matchedCount=1`, `modifiedCount=1` |
| `deleteOne` item-03 | `deletedCount=1` |

Terminal A should receive **four events** in committed sequential write order:

~~~text
Event 1: insert
Event 2: update
Event 3: replace
Event 4: delete
~~~

If another writer modifies those fixed IDs concurrently, or you re-seed while watching, event counts and order may differ. This lab assumes **no competing writes on the four IDs**.

### 11.5. Step D — Inspect Final State

In Terminal B:

~~~javascript
db.getSiblingDB("mongo_change_stream_lab")
  .getCollection("lab_items")
  .find({
    _id: {
      $in: [
        "cs272-item-01",
        "cs272-item-02",
        "cs272-item-03",
        "cs272-item-04"
      ]
    }
  })
  .sort({ _id: 1 })
  .toArray();
~~~

Interpretation:

- **item-01:** `status=active`, `quantity=7`, `attributes.color=navy`; `obsoleteFlag` is gone.
- **item-02:** `status=archived`, `quantity=0`; `legacy` and `attributes.size` are gone due to `replace`.
- **item-03:** gone due to `delete`.
- **item-04:** exists due to `insert`.

Having three documents left in the database is unrelated to **event count = 4**: events represent **state transitions**, not a list of currently existing documents.

### 11.6. If No Events Appear

Check step by step:

1. Is Terminal A actually connected to a replica set or `mongos`?
2. Was the watcher opened **before** running Step C?
3. Are the database/collection names and four `_id`s exact?
4. Did Terminal B report `matchedCount`/`deletedCount` equal to 1?
5. Did any operation fail write concern or lack privileges?
6. Did the watch pipeline mistakenly filter on **fullDocument.dataset**, dropping `delete`?
7. Was the cursor closed, invalidated, or disconnected?

Do not alter server config, oplog settings, or force failovers just to "make events appear."

## 12. Filtering Events in a Watch Pipeline: Remember Delete Lacks `fullDocument`

### 12.1. Filtering the Four `operationType`s

~~~javascript
const stream = db.lab_items.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

This is a convenient way in a lesson to handle only document CRUD changes. Change Streams also emit other event types, so production consumers should explicitly define behavior for administrative/invalidating events.

### 12.2. Bug: Filtering Solely on `fullDocument`

Common buggy example:

~~~javascript
const stream = db.lab_items.watch([
  {
    $match: {
      "fullDocument.dataset": "change-stream-v1"
    }
  }
]);
~~~

This filter **drops deletes**, because delete events do not have `fullDocument` by default. It can also drop updates when `fullDocument` is not requested or not found.

### 12.3. Filtering by `documentKey` and `operationType`

In the lab, `_id` uses a distinct prefix, though stream queries need not rely on string regexes over tokens. With a known ID list:

~~~javascript
const stream = db.lab_items.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      },
      "documentKey._id": {
        $in: [
          "cs272-item-01",
          "cs272-item-02",
          "cs272-item-03",
          "cs272-item-04"
        ]
      }
    }
  }
]);
~~~

This preserves deletes because `documentKey` is present on deletes. In real multi-tenant systems, you may need to combine namespace/shard key and access control; **never assume every `documentKey` contains `tenantId`** if your schema/sharding differs.

### 12.4. Stream Projections Must Preserve the Resume Token

A very serious mistake:

~~~javascript
// Do not do this:
db.lab_items.watch([
  { $project: { _id: 0, operationType: 1, documentKey: 1 } }
]);
~~~

The Change Stream **_id** is the resume token. MongoDB requires consumers not to alter or strip the resume token via watch pipeline stages; doing so causes errors or breaks stream resumption.

If you only want to log a few fields, **keep the event intact in the cursor** and build a slim log object in application code. Never modify **event._id** inside the pipeline.

### 12.5. Do Not Arbitrarily Use Every Aggregation Stage

Change Stream pipelines have **different restrictions from normal aggregation pipelines**. Structural stages like `$group`, `$sort`, `$out`, `$merge`, or stages modifying event IDs/identities cannot be applied arbitrarily to `watch` like a data-reporting query.

Use stages supported by MongoDB for Change Streams—especially **$match** and token-preserving transformations—and consult your server version documentation before adding stages. For aggregations/totals, normally **compute them in the consumer or read-model update pipeline** rather than forcing a Change Stream to act like a batch aggregation.

## 13. Resume Tokens: Continuation Point After Consumer Disconnects

### 13.1. Why Are Checkpoints Needed?

A consumer can restart due to:

- Deploying a new release.
- Network disconnects.
- Primary election/failover.
- Worker crash.
- Temporary sink API unavailability.

If every restart calls a fresh **watch()** without a resume token, the consumer opens a new stream from the current time and **misses changes** that occurred while offline.

### 13.2. Store `event._id`, Not the Document ID

Example:

~~~javascript
const token = event._id;                    // Resume token
const productId = event.documentKey._id;    // Product ID
~~~

Checkpoints should store the **token in its exact BSON form** or type-preserving Extended JSON if serialization is mandatory. Never use:

~~~javascript
event.clusterTime.toString()
~~~

as a resume token, nor `documentKey._id` alone.

### 13.3. `resumeAfter`

With a valid saved resume token:

~~~javascript
const stream = db.lab_items.watch(
  [],
  {
    resumeAfter: savedResumeToken,
    fullDocument: "updateLookup"
  }
);
~~~

**resumeAfter** instructs the server to continue **after** the corresponding event. Hence, consumers normally checkpoint the token of an event **after successfully processing it**, rather than immediately upon receiving it before processing.

### 13.4. Checkpoint Before or After Processing?

Both orders involve trade-offs:

~~~text
WRONG FOR AT-LEAST-ONCE SYSTEMS:
  receive event E
  save E's token
  process E in target system

If crash after saving token but before processing:
  resumeAfter E -> E is skipped
~~~

Standard design:

~~~text
  receive event E
  process E in target system
  persist checkpoint for E's token

If crash after processing but before checkpoint:
  E may be processed again
~~~

Therefore, consumers should be **idempotent**. If the sink and checkpoint reside inside the same supported transaction, they can be combined to narrow the failure window there; however, **a MongoDB transaction cannot roll back side effects in an external system** such as a search engine or email provider.

### 13.5. Resume Tokens Do Not Last Forever

Change Streams depend on oplog history and retention settings. A consumer offline for too long may no longer be able to resume from an old token because the corresponding entry has aged out of the oplog.

When encountering an unrecoverable resume error, never:

1. Silently delete the checkpoint.
2. Start a fresh watch.
3. Still claim the read model is completely in sync.

Instead, trigger a controlled **rebuild/backfill workflow**, establish a new starting point, and reconcile potentially missed data.

### 13.6. `invalidate`, `resumeAfter`, and `startAfter`

Operations like **drop collection**, **rename collection**, or **drop database** can emit administrative events and **invalidate** the stream in corresponding cases.

Never treat `invalidate` as a normal document delete.

**resumeAfter** cannot be used to continue past an `invalidate` event the way it works for ordinary CRUD events. On supporting versions, **startAfter** can open a new stream **after an invalidate token** under MongoDB semantics.

Key differences:

- **resumeAfter:** resumes from a prior event, except invalidate tokens are not supported the same way.
- **startAfter:** can start after an `invalidate` event in applicable scenarios.
- **startAtOperationTime:** starts from an eligible oplog timestamp; not a complete replacement for token checkpointing.

All three depend on **remaining oplog history** and watch scope. You cannot recover lost data merely by choosing a newer timestamp.

### 13.7. Token Formats Can Change Across Versions

Resume tokens are **opaque**. Never parse the **_data** field to extract shards, timestamps, document IDs, or business attributes. Token formats can change between server versions.

Consumers should persist and restore tokens verbatim and pass them intact to the `watch` API. If JSON serialization is used, preserve BSON types without corrupting token structure.

## 14. Node.js Driver: Consumer Handling All Four Event Types

This section illustrates a Node.js consumer using the **mongodb** package. It is not a full production service; the goal is to demonstrate **switching on `operationType`** and checkpoint/resume. Run against a replica set/sharded lab with URI from the environment.

### 14.1. Consumer Logging Exact Details

~~~javascript
import { MongoClient } from "mongodb";

const client = new MongoClient(process.env.MONGODB_URI);
await client.connect();

const items = client
  .db("mongo_change_stream_lab")
  .collection("lab_items");

const stream = items.watch(
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
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  }
);

try {
  for await (const event of stream) {
    const id = event.documentKey?._id;

    switch (event.operationType) {
      case "insert":
        console.log("INSERT", id, event.fullDocument);
        break;
      case "update":
        console.log("UPDATE", id, event.updateDescription);
        console.log("Current document:", event.fullDocument ?? null);
        break;
      case "replace":
        console.log("REPLACE", id, event.fullDocument);
        break;
      case "delete":
        console.log("DELETE", id);
        break;
      default:
        console.log("OTHER EVENT", event.operationType);
    }

    // Print token for illustration only; this example does NOT checkpoint yet.
    console.log("Resume token:", event._id);
  }
} finally {
  await stream.close();
  await client.close();
}
~~~

This consumer runs continuously until stopped or an error occurs. A production application needs signal handling, retries, checkpointing, metrics, secure logging, and lifecycle management.

### 14.2. Distinguishing Search Index Update Paths

Logic example:

~~~javascript
async function applyChange(event, sink) {
  const namespace = event.ns;
  const id = event.documentKey?._id;

  if (!id) {
    throw new Error("Event missing documentKey._id");
  }

  const sinkId = namespace.db + "." + namespace.coll + ":" + id;

  switch (event.operationType) {
    case "insert":
      if (!event.fullDocument) {
        throw new Error("Insert event missing fullDocument");
      }
      await sink.replaceById(sinkId, event.fullDocument);
      return;

    case "update":
      // Option A: apply delta (sink must accurately support updateDescription).
      // await sink.applyMongoPatch(sinkId, event.updateDescription);

      // Option B: use near-current state from updateLookup.
      // NOTE: may be null or reflect a newer update.
      if (!event.fullDocument) {
        throw new Error("Update missing document to synchronize");
      }
      await sink.replaceById(sinkId, event.fullDocument);
      return;

    case "replace":
      if (!event.fullDocument) {
        throw new Error("Replace event missing fullDocument");
      }
      await sink.replaceById(sinkId, event.fullDocument);
      return;

    case "delete":
      await sink.deleteById(sinkId);
      return;

    default:
      // Other operationTypes require explicit policy.
      return;
  }
}
~~~

**sink** here is a hypothetical adapter, not an API from the `mongodb` package. The function clarifies the difference between **patch** and **replace**.

In production:

- **insert/replace:** idempotent upsert or replace.
- **update:** apply semantically accurate patches or refresh from `fullDocument` while accounting for lookup staleness.
- **delete:** delete by `documentKey`; never expect `fullDocument`.
- **other events:** explicit policy; never treat `drop`/`invalidate` as a single-document delete.

### 14.3. Checkpointing in MongoDB

A skeleton consumer persisting tokens in a checkpoint collection:

~~~javascript
import { MongoClient } from "mongodb";

async function consumeWithCheckpoint(uri) {
  const client = new MongoClient(uri);
  await client.connect();

  const lab = client.db("mongo_change_stream_lab");
  const items = lab.collection("lab_items");
  const checkpoints = lab.collection("lab_checkpoints");
  const consumerId = "cs272-lab-consumer";

  const checkpoint = await checkpoints.findOne({
    _id: consumerId
  });

  const options = {
    fullDocument: "updateLookup",
    maxAwaitTimeMS: 1000
  };

  if (checkpoint?.resumeToken) {
    options.resumeAfter = checkpoint.resumeToken;
  }

  const stream = items.watch(
    [
      {
        $match: {
          operationType: {
            $in: ["insert", "update", "replace", "delete"]
          }
        }
      }
    ],
    options
  );

  try {
    for await (const event of stream) {
      // processAndPersistChange is application-implemented.
      // It must either complete processing or throw an error.
      await processAndPersistChange(event);

      // Persist token ONLY AFTER event processing succeeds.
      await checkpoints.updateOne(
        { _id: consumerId },
        {
          $set: {
            resumeToken: event._id,
            lastOperationType: event.operationType,
            lastDocumentId: event.documentKey?._id,
            updatedAt: new Date()
          }
        },
        {
          upsert: true,
          writeConcern: {
            w: "majority",
            wtimeoutMS: 10000
          }
        }
      );
    }
  } finally {
    await stream.close();
    await client.close();
  }
}

// Illustrative skeleton: must implement processAndPersistChange.
// await consumeWithCheckpoint(process.env.MONGODB_URI);
~~~

**Important:** this is an ordering skeleton, not an exactly-once guarantee.

If sink processing succeeds and the process crashes before checkpointing, the event can be processed **again** on recovery. Sink side effects must be idempotent or deduplicated by an appropriate key. If both the checkpoint and sink live in the same MongoDB cluster, a transaction can commit them together under supported conditions; for external systems, a dedicated application protocol is required.

### 14.4. Do Not Use `documentKey` to Deduplicate Business Operations

A Change Stream may contain:

~~~text
E1: insert document X       token R1
E2: update document X       token R2
E3: update document X       token R3
E4: replace document X      token R4
E5: delete document X       token R5
~~~

If a consumer deduplicates by `documentKey._id = X`, it processes E1 and drops E2–E5—completely wrong.

If a consumer deduplicates by **token** yet records the token before sink processing succeeds, it risks losing events. Design **token checkpointing, idempotent processing, and application order** together.

## 15. Upsert: Why Can an Update Command Emit an Insert Event?

### 15.1. Upsert Creating a New Document

~~~javascript
db.lab_items.updateOne(
  { _id: "cs272-upsert-01" },
  {
    $set: {
      sku: "P-100",
      status: "draft",
      dataset: "change-stream-v1"
    }
  },
  { upsert: true }
);
~~~

If the document does not exist, MongoDB creates a new document. Change Streams reflect **the actual data change**, so `operationType` will be **"insert"**, even though the API called was **updateOne**.

### 15.2. Upsert Matching an Existing Document

When the document already exists and the same `updateOne` with `upsert: true` matches it, modifying fields emits an **update** event.

Therefore:

- Never infer the event type from the API method name logged by a service.
- Always inspect **operationType** in the Change Stream.
- Also inspect **documentKey** and **updateDescription/fullDocument** to understand the effect.

### 15.3. No Actual Modification

An update writing identical existing values may not produce a meaningful data change under server semantics. Never assume **every `updateOne` call always emits an update event**.

If a workflow needs to audit **every request including no-ops**, Change Streams are not a business request log. Write an explicit audit/outbox record instead.

## 16. Event Ordering, Transactions, and `clusterTime`

### 16.1. Ordering Within a Single Stream

A Change Stream yields events in the order of change history provided by the server within the watched scope. This works well when a consumer processes a single stream sequentially to maintain an event-driven replica.

However:

- Multiple independent consumers may progress at different speeds.
- If you fan out events to multiple parallel workers, **application order at the sink may change**.
- Two events for the same document must be applied in order so stale states do not overwrite newer ones.
- Sharded clusters and transactions introduce specific ordering and metadata rules; never rely purely on wall clocks.

### 16.2. Transactions Emit Multiple Events

A transaction can modify two documents:

~~~text
BEGIN TRANSACTION
  update Order A
  update Order B
COMMIT
~~~

After commit, the Change Stream emits **multiple change events** for the modified documents—not a single event with `operationType: "transaction"`.

Related events may carry metadata such as **lsid, txnNumber** and share a **clusterTime** under version semantics.

Never use **clusterTime** as a unique event key. Use the **resume token** to pinpoint stream position.

### 16.3. Do Not Treat a Change Stream as a Distributed Transaction with the Sink

MongoDB commits a source transaction; the consumer reads events and sends updates to a search engine. Sending those updates **is not part of the source transaction**. If the search engine fails, MongoDB does not roll back the committed transaction.

For recoverable data synchronization:

- Persist checkpoints.
- Retry with bounds and backoff.
- Enforce idempotent processing.
- Rebuild/backfill on oplog history loss.
- Monitor lag and dead-letter/quarantine unprocessable events.

### 16.4. Do Not Use `wallTime` as a Strict Global Order

Wall clocks can skew across hosts. For ordered event processing, rely on **stream/resume semantics** and system-provided ordering guarantees rather than sorting cluster-wide solely by **wallTime**.

## 17. Event Types Beyond the Four CRUD `operationType`s

A production consumer must not assume Change Streams only emit `insert`, `update`, `replace`, and `delete`.

Depending on server version, watch scope, and options such as **showExpandedEvents**, you may encounter:

- **drop:** collection dropped.
- **rename:** collection renamed.
- **dropDatabase:** database dropped.
- **invalidate:** stream can no longer continue normally after certain namespace-changing operations.
- Expanded DDL/metadata events such as `create`, `createIndexes`, `dropIndexes`, `modify`, or sharding operations on supporting versions.

Mental model:

~~~text
deleteOne({_id:"X"})
  -> delete event for document X

drop collection "products"
  -> drop/invalidate and related events
  -> NOT millions of individual delete events per product
~~~

Thus, if a search index maps 1:1 to a collection, **drop** requires a dedicated invalidation/rebuild workflow; you cannot wait for per-document `delete` events to clear the index.

### 17.1. Suggested Policy

| `operationType` | Consumer Behavior |
| --- | --- |
| `insert`/`update`/`replace`/`delete` | Handle CRUD as covered in this lesson |
| `drop`/`rename`/`dropDatabase` | Handle namespace/metadata change, report status, and decide on rebuild |
| `invalidate` | Close/recreate stream per supported semantics, verify token and scope |
| Expanded DDL events | Enable option only when needed; add explicit handlers and schemas |
| Unknown event in newer version | Log/alert cleanly; never delete target data by default |

In `switch` statements, the `default` branch **must never** assume "if not insert, then delete."

## 18. Syncing Search Indexes, Caches, and Read Models Across the Four Types

### 18.1. Search Index

A secondary index storing products for search:

~~~text
MongoDB products  --->  Change Stream  --->  Search Index
~~~

Strategy:

- **insert:** create/upsert document in search index.
- **update:** patch modified fields or rebuild snapshot when appropriate `fullDocument` is present.
- **replace:** replace the entire indexed content for the product.
- **delete:** remove the product by `documentKey`.

You cannot reuse the exact same **"merge all fields"** handler for both `replace` and `update` if replacements can drop previously existing fields.

### 18.2. Cache Invalidation

For a cache that simply evicts keys on data changes, a handler can be concise:

~~~javascript
if (["insert", "update", "replace", "delete"].includes(
  event.operationType
)) {
  const id = event.documentKey?._id;
  // await cache.delete("product:" + id);
}
~~~

However:

- Cache keys may need `tenantId`/namespace prefixes.
- Event delivery lag means the cache may be temporarily stale.
- Cache invalidation following an update does not guarantee transactional read-your-writes.
- If a document is deleted and its ID reused, track a generation/version to stop old events from deleting newer data.

### 18.3. Materialized Views

Suppose a view tracks **active product count per tenant**:

- insert active: increment count.
- update draft → active: increment count.
- update active → draft: decrement count.
- replace: must know both before and after states to compute delta.
- delete: must know previous state to decide whether to decrement.

**Looking only at `updateDescription.updatedFields.status = "active"` is not enough to know whether the prior status was `draft` or `active`**, especially if intermediate transitions or event replays occur.

Approaches:

1. Use pre-images/post-images where appropriate.
2. Maintain per-document state in the sink and apply idempotent state transitions.
3. Emit explicit business events (`stateFrom`/`stateTo`) in an outbox.
4. Periodically reconcile by recomputing from MongoDB.

Never blindly increment counters on every update, as retries will double-count.

### 18.4. Auditing

Change Streams are useful for detecting that a document changed, but **are not a complete audit system**:

- Events do not include `userId`/actor or business reason by default.
- Deletes do not include the old document by default.
- Change stream history has a finite retention window.
- API requests that make no data changes emit no events.
- Rollback/replication and schema events require careful interpretation.

For compliance logging, design explicit audit records with **actor, requestId, reason, timestamp, appropriate payload, and retention**, alongside dedicated security controls.

## 19. Initial Backfill and Catching Up with the Change Stream

### 19.1. `watch` Does Not Automatically Send the Whole Existing Collection

Opening:

~~~javascript
const stream = db.products.watch();
~~~

does not cause MongoDB to emit insert events for **all products created last year**. A Change Stream tracks changes from its determined start point forward.

Therefore, to build a new search index from a collection with millions of existing documents, you need to:

1. **Backfill** a snapshot of current documents.
2. **Consume changes** occurring while the backfill runs.
3. Reconcile ordering/timestamps so nothing is missed and stale events do not overwrite newer data.
4. Transition to continuous streaming consumption.

### 19.2. Race Condition During Backfill

Gap-prone pattern:

~~~text
T1: Begin scanning existing products
T2: Product X is updated
T3: Scan completes
T4: Change Stream opened afterward

The update at T2 may be missing from both
the snapshot and the stream, depending on scan order.
~~~

Never simply "scan first, then open watch" when zero lost deltas are required. Use a designed workflow combining **stream start point + consistent snapshot + replay** matching your server version and guarantees.

### 19.3. When the Resume Token Expires

If a consumer is offline longer than the oplog window, recovery steps typically include:

- Stop advertising the read model as fully up-to-date.
- Flag a degraded/rebuilding state.
- Start a fresh snapshot/backfill workflow with proper time boundaries.
- Monitor token/lag once back in continuous streaming mode.
- Reconcile document counts and sample records against the source.

Never ignore resume errors and proceed as if no events were lost.

## 20. Latency, Size, and Resource Limits

### 20.1. Not an Infinite Event Bus

Change Streams leverage MongoDB's oplog and replication. They **do not replace** a dedicated event broker with long retention, partition management, and custom replay policies for every use case.

If multiple independent consumers need separate workflows, you can forward change events into a durable intermediate pipeline aligned with your organization's architecture, complete with dead-letter queues and observability.

### 20.2. Event Size

Events include metadata, `fullDocument`, `updateDescription`, and potentially pre-/post-images. When images are enabled on large documents, event sizes grow substantially; account for the BSON document size limit and Change Stream large-event rules in your server version.

**Do not** enable pre-/post-images on all large collections without measuring costs.

### 20.3. Slow Consumers

A slow consumer widens the gap between **latest server events** and **checkpointed resume token**. If it falls behind past the oplog window, resuming ceases to be supported.

Metrics to monitor:

- Time from source change to consumer completion.
- Age of the checkpointed token.
- Events/second and event-processing failure count.
- Reconnect/resume count.
- Frequency of stale-token errors.
- Replication/Change Stream lag across topology.
- Sink update failure rate.

### 20.4. Many Watchers

Each watcher consumes a cursor/connection and filtering/processing resources. Thousands of watchers on the same collection create far more pressure than a single consumer fanning out to internal services.

Never open a new Change Stream per incoming HTTP request without strict connection, timeout, and lifecycle management.

### 20.5. Sharded Clusters

When watching a sharded collection or entire deployment:

- Changes originate from multiple shards.
- `mongos` and cluster components collaborate to merge the event stream.
- Tokens, ordering, and resuming must follow supported semantics—never parse manually.
- Data chunks can migrate between shards.
- Consumers must account for namespace/`documentKey` and sharding changes.

Never infer a document's current shard placement from a token or from where it was initially inserted.

## 21. Common Errors and Remediation

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `watch` reports unsupported | Standalone MongoDB or improper topology/permissions | Use a valid replica set/sharded cluster |
| Newly inserted event not seen | Watcher opened after write, or wrong filter | Open watch first; check scope and IDs |
| Delete dropped by `$match` | Filter checks `fullDocument` only | Filter by `operationType`/`documentKey`; handle delete explicitly |
| Crash when handling delete | Code accesses `event.fullDocument._id` | Use `event.documentKey._id` |
| Update wipes fields in sink | Using `updatedFields` as a replacement | Apply semantic patch or fetch snapshot |
| Replace leaves removed fields behind | Merging replacement into old sink object | Replace full snapshot in sink |
| `quantity` in `updatedFields` is 7 instead of 2 | Event reports new value, not `$inc` operand | Distinguish operator delta from resulting value |
| `updateDescription` omits unchanged fields | Only modified fields are described | Do not treat it as the full document |
| `fullDocument` `updateLookup` shows newer state | Lookup ran after subsequent updates | Use pre-/post-images or versioned logic |
| `fullDocument` `updateLookup` is null | Document deleted before lookup or unretrievable | Handle null cleanly; don't treat event as invalid |
| Pre-image not received | Feature not enabled or image expired | Verify config, version, and retention |
| Cursor fails due to modifying `_id` in pipeline | Resume token altered or stripped | Keep `event._id` intact in watch |
| Resuming after restart skips events | Checkpointed before processing | Checkpoint after processing succeeds |
| Event processed twice | Crash after sink success before checkpoint | Enforce idempotency/deduplication in sink |
| Token cannot resume | Oplog window no longer contains history | Controlled rebuild/backfill |
| Restarting stream after `invalidate` fails | Passing invalidate token to `resumeAfter` | Use `startAfter` or open a new stream per policy |
| Upsert emits `insert` | Upsert created a new document | Branch on actual `operationType` |
| Error using `clusterTime` as dedup key | Multiple events can share `clusterTime` | Use resume token and distinct business IDs |
| Active counter incremented twice | Event retried or prior state unknown | Pre-image/state tracking/idempotent aggregation |
| No event seen for no-op `$set` | No meaningful data modification occurred | Log explicit audit requests if every call must be tracked |
| Slow consumer loses history | Oplog retention insufficient | Monitor lag; scale capacity or rebuild |
| Mistaking collection drop for document deletes | Confusing DDL/`invalidate` with CRUD | Separate handlers for `drop`/`rename`/`invalidate` |

## 22. Practice Exercises

### Exercise 1 — Reading an Event

Given an event with **_id resume token**, **operationType update**, and **documentKey._id = X**, explain all three fields and why `documentKey._id` must never be used to resume the stream.

### Exercise 2 — Observing All Four `operationType`s

Run the two-terminal lab in Section 11. Record the `operationType` of the four events, which fields appear in each, and the final state of the four documents.

### Exercise 3 — Update vs. Replace

An initial document has fields `sku`, `status`, `quantity`, `legacy`, and `attributes.size`. If `updateOne` only `$set`s `status`, which fields remain? If `replaceOne` omits `legacy` and `attributes.size`, which fields remain? How must a consumer handle them differently?

### Exercise 4 — Delete Without `fullDocument`

Write a delete handler using **documentKey** to evict a cache key. If you also need the document's `status` prior to deletion, propose two implementable solutions.

### Exercise 5 — Nested `updatedFields`

An event's `updateDescription` contains `updatedFields["attributes.color"] = "navy"`. Write an algorithm to apply nested paths cleanly to a JavaScript object, and state risks when field names contain literal dots/special characters or when array elements change.

### Exercise 6 — `$inc`

A document has `quantity=5`, and the API executes `$inc: {quantity:2}`. What value appears in `updateDescription`? Why must you not add `quantity` again if the consumer mistakenly treats `updatedFields.quantity` as an operand?

### Exercise 7 — Truncated Arrays

An update shortens the `labels` array from 5 elements down to 2. Which field besides `updatedFields`/`removedFields` must the consumer inspect on supporting versions? Why does ignoring array truncation leave stale elements in the sink?

### Exercise 8 — `updateLookup` Is Not a Point-in-Time Snapshot

T1 updates `quantity` 5→7, T2 updates 7→9, and then the consumer processes event T1 with `fullDocument: "updateLookup"`. Which `quantity` may `fullDocument` contain and why? If business rules require the exact state at T1, which feature should be used?

### Exercise 9 — Upsert

Run `updateOne` with `upsert: true` on a non-existent `_id`, then run another update on the same `_id`. Predict the `operationType` of both events and explain why the API name `updateOne` does not guarantee an `update` event.

### Exercise 10 — Watch Filter

A consumer watches with `$match` on **fullDocument.tenantId = t001**. Identify at least two event situations that can be lost when `fullDocument` is absent. Redesign using `documentKey`, event types, or an appropriate data model.

### Exercise 11 — Resume Token

A consumer processes E1, E2, and E3, then disconnects after persisting E2's token. When resuming with `resumeAfter(E2)`, which event may be reprocessed? Design an idempotent sink.

### Exercise 12 — Checkpointing Order

Compare "checkpoint before writing sink" against "write sink before checkpoint." For each, describe the resulting state if a crash occurs in between. Which is better for avoiding lost events, and why must duplicate processing be tolerated?

### Exercise 13 — Oplog Retention

A consumer stops for three days, while the oplog holds a shorter history window. Resuming with the old token fails. Why is it wrong to delete the checkpoint, open a fresh stream, and still claim the read model is synchronized? Propose rebuild/backfill steps.

### Exercise 14 — Invalidate

A collection is dropped while a watcher is running. Is that equivalent to a stream of individual delete events for every document? How should you handle `drop`/`invalidate`, `startAfter`/`resumeAfter`, and consumer recreation?

### Exercise 15 — Pre-Image and Delete

Enable pre-/post-images in an isolated lab on a supporting version. Watch with `fullDocumentBeforeChange: "whenAvailable"`, delete a document, and inspect the pre-image if stored. When the image is absent, what should the consumer do?

### Exercise 16 — Audit and Actor

You need to know "who changed status from draft to paid." Why does `updateDescription` not include `userId`/reason by default? Design a business audit/outbox record with `requestId`, `actor`, old/new status, and appropriate retention.

### Exercise 17 — Materialized Count

An `activeProductsByTenant` counter receives `insert`, `update`, `replace`, and `delete` events. Explain why checking only `operationType` and post-change `status` is insufficient to compute the delta in all cases. Propose state tracking, pre-images, or reconciliation.

### Exercise 18 — Concurrent Processing

Two events E1 and E2 for the same product are dispatched to two parallel workers. Worker 2 finishes E2 before Worker 1 finishes E1. What happens to the search index? Propose sequential per-key ordering or versioning/conditional writes to prevent stale state overwrites.

### Exercise 19 — Sharded `documentKey`

A collection is sharded on `tenantId`/`orderNo`. Which fields besides `_id` can `documentKey` contain? Why should a consumer not rely solely on `_id` to identify source records when namespace and shard key are required by business logic?

### Exercise 20 — Backfill vs. Stream Boundary

A new search indexer starts by scanning the entire collection and opening the stream afterward. During the scan, product X changes price. Describe the race condition, then propose a snapshot/boundary + replay workflow that loses no deltas.

### Exercise 21 — Monitoring

Design a consumer dashboard covering event lag, checkpoint age, oplog window, resume failures, sink retries, duplicate handling, and event counts by `operationType`. Which alert should take priority to prevent losing resumability?

### Exercise 22 — Handling Unknown Events

After upgrading MongoDB, a consumer encounters a new DDL `operationType`. Why is a `default` branch that "deletes the indexed document" dangerous? Explain how to log/alert/quarantine without silently corrupting data.

### Exercise 23 — End-to-End Test

Build a lab test scenario:

1. Seed three items.
2. Open the watcher.
3. Emit insert/update/replace/delete.
4. Verify event shapes.
5. Stop the consumer after checkpointing the second event.
6. Resume and observe subsequent events.
7. Replay an event to an idempotent sink.
8. Verify sink state matches source state.

Specify how you verify **exact event types** and **no lost or duplicated side effects**, rather than merely counting four log lines.

## 23. Official References

- MongoDB Manual — [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/).
- MongoDB Manual — [Change Events](https://www.mongodb.com/docs/manual/reference/change-events/).
- MongoDB Manual — [$changeStream](https://www.mongodb.com/docs/manual/reference/operator/aggregation/changeStream/).
- MongoDB Manual — [Change Streams Production Recommendations](https://www.mongodb.com/docs/manual/administration/change-streams-production-recommendations/).
- MongoDB Manual — [Change Streams with Document Pre- and Post-Images](https://www.mongodb.com/docs/manual/changestreams/#change-streams-with-document-pre--and-post-images).
- MongoDB Manual — [Replica Set Oplog](https://www.mongodb.com/docs/manual/core/replica-set-oplog/).
- MongoDB Node.js Driver — [Monitor Data with Change Streams](https://www.mongodb.com/docs/drivers/node/current/monitoring-and-logging/change-streams/).
- MongoDB Manual — [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/).

**Conclusion:** A Change Stream is a stream of **change events**, not a list of existing documents and not an infinitely retained audit log. Each event carries a **resume token in `_id`**, **`operationType`**, **`namespace`**, **`documentKey`**, and operation-specific fields. **Insert** usually carries the new document in **fullDocument**; **update** uses **updateDescription** to describe changes without including the full document by default; **replace** provides the replacement document without field-level update deltas; **delete** relies primarily on `documentKey` because the document is gone. A resilient consumer requires **switching cleanly on `operationType`, preserving resume tokens, checkpointing after successful processing, idempotency, and a rebuild plan when oplog history expires**. Whenever exact before/after states are required, clearly distinguish **`updateLookup` from pre-/post-images** and choose according to your business contract.
