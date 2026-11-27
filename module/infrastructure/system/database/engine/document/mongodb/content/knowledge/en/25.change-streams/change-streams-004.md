# Filtering, Transforming Events, and Preserving Resume Tokens in MongoDB Change Streams

**MongoDB Change Streams** let applications observe data changes in near real time instead of continuously running polling queries. A consumer can filter events, keep only required fields, and synchronize search indexes, caches, read models, notification services, or analytics systems.

What sets a change stream apart from an ordinary aggregation is the **resume token**: the **_id field of the change event** holds a MongoDB-issued token pinpointing where to resume reading. If a pipeline uses `$project`, `$unset`, `$set`, or `$replaceRoot` in a way that removes or alters `_id`, resumability breaks; MongoDB explicitly rejects pipelines that modify the resume token. When building a fault-tolerant consumer, **preserving the token is necessary but not sufficient**: you must also checkpoint in order, handle retries, and enforce idempotency.

This lesson focuses on:

1. Change event structure and the difference between **event._id** and **documentKey._id**.
2. Using **$match**, **$project**, **$addFields**, **$unset**, and **$replaceRoot** to filter and normalize events while preserving the resume token.
3. **resumeAfter**, **startAfter**, **startAtOperationTime**, **post-batch resume tokens (PBRT)**, and history retention limits.
4. Checkpointing at the right time, parallel processing, failure recovery, idempotency, and implementation with the **MongoDB Java Sync Driver**.
5. Production scenarios: sharded change streams, `updateLookup`, pre-/post-images, `invalidate`, pipeline evolution, and monitoring.

All data manipulation examples use the test collection **cdc_lab.orders**. Opening a change stream requires a supported replica set or sharded cluster; a standard standalone `mongod` does not meet this requirement.

## 1. What Is a Change Stream?

A change stream is a long-lived cursor emitting events as data changes. Events span multiple operation types—such as `insert`, `update`, `replace`, `delete`, or namespace lifecycle and DDL operations within supported scopes and versions.

Watch scopes include:

| Scope | Common API | Purpose |
| --- | --- | --- |
| Collection | **db.orders.watch()** | Watch `orders` only |
| Database | **db.watch()** | Watch multiple collections within a database |
| Deployment | **MongoClient.watch()** in drivers | Watch data across the supported deployment scope |

Example in `mongosh`:

~~~javascript
use cdc_lab

const stream = db.orders.watch();

while (stream.hasNext()) {
  const change = stream.next();
  printjson(change);
}
~~~

The cursor may wait indefinitely when no changes occur. To observe it, run the watcher in one terminal and issue inserts/updates from another terminal.

### 1.1. Distinguish Source Changes from Business Events

A change event reflects a mutation in MongoDB. It does not necessarily share the exact semantics of a business event.

For instance, updating `status` to `PAID` does not by itself prove payment collection succeeded under payment rules, or that all other side effects finished. If business invariants require payment and event publishing to succeed together, design an explicit outbox/transaction/idempotency mechanism.

### 1.2. A Change Stream Is Not Infinite History

A consumer can only resume from positions still retained in the oplog/change stream history. It does not serve multi-year full-history replay on its own.

## 2. Structure of a Change Event

Order document:

~~~javascript
{
  _id: "ORD-1001",
  customerId: "C-01",
  status: "PENDING",
  totalCents: NumberLong(150000)
}
~~~

When running:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID"
    }
  }
);
~~~

An update event may take the general form:

~~~javascript
{
  _id: {
    _data: "OPAQUE_RESUME_TOKEN"
  },
  operationType: "update",
  clusterTime: Timestamp(...),
  ns: {
    db: "cdc_lab",
    coll: "orders"
  },
  documentKey: {
    _id: "ORD-1001"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
~~~

This is an illustration, not a real token you can copy to resume. Included fields depend on operation type, watch options, and server version.

### 2.1. Fields to Understand

| Field | Meaning |
| --- | --- |
| **_id** | Resume token of the **event** |
| **operationType** | `insert`, `update`, `replace`, `delete`, etc. |
| **clusterTime** | Logical timestamp of the change |
| **ns** | Target database/collection |
| **documentKey** | Key of the modified document |
| **updateDescription** | Updated fields, removed fields, and corresponding array metadata |
| **fullDocument** | Document image when supplied |
| **fullDocumentBeforeChange** | Pre-image if enabled and configured |

Not every event includes `fullDocument`. Deletes normally lack the deleted document's full body.

### 2.2. `event._id` Differs from `documentKey._id`

~~~javascript
change._id
// For example, a BsonDocument containing the resume token.

change.documentKey._id
// "ORD-1001": ID of the updated order.
~~~

If the same order is updated five times, `documentKey._id` stays identical while the resume token differs for every event.

**Never pass `documentKey._id` as the token to `resumeAfter`.** It does not identify a stream position.

### 2.3. Tokens Are Opaque BSON

Even though a token often looks like a document with a `_data` field, applications must never:

- Extract only `_data` and discard other fields.
- Decode `_data` using custom internal logic.
- Fabricate a token from `clusterTime` or `documentKey`.
- Compare two tokens by lexicographical order of JSON strings.
- Replace the token with a timestamp, `ObjectId`, or plain string for storage convenience.

Keep **the entire BSON value intact**.

## 3. Preparing the Test Environment

Use a test replica set or sharded cluster; never run the commands below against real data without authorization.

~~~javascript
use cdc_lab

db.orders.insertMany([
  {
    _id: "ORD-1001",
    customerId: "C-01",
    region: "APAC",
    status: "PENDING",
    totalCents: NumberLong(150000),
    email: "alice@example.test"
  },
  {
    _id: "ORD-1002",
    customerId: "C-02",
    region: "EMEA",
    status: "PAID",
    totalCents: NumberLong(250000),
    email: "bob@example.test"
  },
  {
    _id: "ORD-1003",
    customerId: "C-03",
    region: "APAC",
    status: "DRAFT",
    totalCents: NumberLong(99000)
  }
]);
~~~

Terminal A, open the watcher:

~~~javascript
use cdc_lab

const watcher = db.orders.watch();

while (watcher.hasNext()) {
  printjson(watcher.next());
}
~~~

Terminal B, generate changes:

~~~javascript
use cdc_lab

db.orders.updateOne(
  { _id: "ORD-1001" },
  { $set: { status: "PAID" } }
);

db.orders.insertOne({
  _id: "ORD-1004",
  status: "PENDING",
  customerId: "C-04",
  region: "APAC",
  totalCents: NumberLong(180000)
});

db.orders.deleteOne({ _id: "ORD-1003" });
~~~

A newly opened watcher does not automatically read all historical changes from before it started. Building an initial snapshot followed by gapless CDC requires an explicit snapshot+stream protocol.

## 4. The Change Stream Pipeline

The `watch` API accepts an aggregation pipeline that processes **change events**. Callers do not insert the `$changeStream` stage manually when invoking `watch()`.

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: "update"
    }
  }
]);
~~~

Not every aggregation stage is valid after `$changeStream`. Stages commonly supported in a change stream pipeline include:

- **$match**
- **$project**
- **$addFields / $set**
- **$unset**
- **$replaceRoot / $replaceWith**
- **$redact**

Supported stages and exact constraints depend on server version; never drop `$group`, `$sort`, `$lookup`, `$out`, `$merge`, or arbitrary stages into a change stream pipeline.

### 4.1. Invariant Condition

When building a pipeline, **never alter or remove the change event's `_id`**.

MongoDB detects and throws an error if a pipeline drops or modifies the resume token. Never rely on the consumer "reconstructing" a token from a transformed payload.

### 4.2. Source-Side Filtering vs. Client-Side Filtering

Using `$match` inside `watch` lets the server discard unwanted events before returning them to the application, reducing bandwidth and consumer processing work.

However, that does not mean every filter is free or changes how source writes happen. Underlying source history still has to be processed according to MongoDB mechanics.

## 5. `$match` by `operationType`

Interested only in `insert` and `update`:

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update"]
      }
    }
  }
]);
~~~

A search index mirror typically needs:

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

If you forget **delete**, the search index retains records after the source documents are gone.

### 5.1. `operationType` Values to Distinguish

| Operation | Common Payload/Meaning |
| --- | --- |
| `insert` | New document; typically includes `fullDocument` |
| `update` | Includes `updateDescription`; `fullDocument` depends on options |
| `replace` | Replaced document; typically includes `fullDocument` |
| `delete` | `documentKey`; no `fullDocument` by default |
| `drop` / `rename` | Lifecycle events depending on watch scope |
| `invalidate` | Stream invalidated per namespace semantics |
| Expanded DDL | Depends on server version and `showExpandedEvents` |

Do not assume a consumer only needs `update` because applications sometimes use `replaceOne` or other operations to modify documents.

### 5.2. Filtering by `documentKey`

~~~javascript
db.orders.watch([
  {
    $match: {
      "documentKey._id": "ORD-1001"
    }
  }
]);
~~~

This filters by business document ID, **not** by resume token.

In sharded collections, `documentKey` may include additional shard key fields. Never assume `documentKey` always contains only `_id`.

## 6. Filtering by Namespace at Database Scope

When watching an entire database:

~~~javascript
db.watch([
  {
    $match: {
      "ns.coll": {
        $in: ["orders", "payments"]
      },
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  }
]);
~~~

In deployment-scope watches, when distinguishing collections with identical names across different databases, filter on both **ns.db** and **ns.coll**.

A `$match` checking only `ns.coll = "orders"` is insufficient if multiple databases in the deployment contain an `orders` collection.

## 7. Filtering `updateDescription`

An update using `$set`/`$unset`:

~~~javascript
db.orders.updateOne(
  { _id: "ORD-1001" },
  {
    $set: {
      status: "PAID",
      updatedBy: "payment-service"
    },
    $unset: {
      oldNote: ""
    }
  }
);
~~~

The event may look like:

~~~javascript
{
  operationType: "update",
  updateDescription: {
    updatedFields: {
      status: "PAID",
      updatedBy: "payment-service"
    },
    removedFields: ["oldNote"]
  }
}
~~~

### 7.1. Filtering Events That Set `status` to `PAID`

~~~javascript
db.orders.watch([
  {
    $match: {
      operationType: "update",
      "updateDescription.updatedFields.status": "PAID"
    }
  }
]);
~~~

This confirms **the update event reports that `status` was just set to `PAID`**. It does not by itself prove the prior state was `PENDING`.

If business logic requires a specific transition **PENDING → PAID**, you need a source for the prior state: a pre-image, business transition metadata, or another suitable mechanism.

### 7.2. Field Names Containing Dots

For nested field updates, `updateDescription.updatedFields` may contain a literal key like **"shipping.city"**. In such cases, a regular dotted path expression:

~~~javascript
"$updateDescription.updatedFields.shipping.city"
~~~

will not necessarily access that literal key. You can use `$getField` on supporting versions:

~~~javascript
{
  $getField: {
    field: "shipping.city",
    input: "$updateDescription.updatedFields"
  }
}
~~~

Inspect actual event schemas; never assume every entry in `updatedFields` is a nested object matching dotted paths.

### 7.3. Delete Events Lack Old `status` by Default

Do not write:

~~~javascript
{
  $match: {
    operationType: "delete",
    "fullDocument.status": "PAID"
  }
}
~~~

expecting it to return all deletes of previously `PAID` orders. Deletes carry `documentKey`, while pre-delete `status` is available only if supplied by pre-images or another source.

## 8. `fullDocument` and `updateLookup`

For update events, a change stream carries only `updateDescription` by default. To fetch the current full document after an update, enable:

~~~javascript
db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace"]
        }
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

### 8.1. `updateLookup` May Read a State Newer Than the Event

Suppose:

~~~text
T1: order changes PENDING -> PAID     (event E1)
T2: order changes PAID -> REFUNDED    (event E2)
T3: updateLookup runs for E1
~~~

E1's `fullDocument` can reflect the state at lookup time, differing from the state right after E1. It may also be absent if the document was deleted afterward.

Therefore:

- **updateDescription** is appropriate for knowing which fields that event modified.
- **updateLookup** is appropriate when you want the current document.
- If you need exact pre-/post-images tied to the event, use pre-/post-image features per your server version.

### 8.2. Filtering by `fullDocument.status`

~~~javascript
db.orders.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace"]
        },
        "fullDocument.status": "PAID"
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

This filter does not exclusively select events **transitioning to `PAID`**. Another update on an order that is already `PAID` also matches if `fullDocument.status = "PAID"`.

### 8.3. Lookup Cost

Looking up `fullDocument` increases I/O and event payload size. If a consumer only needs a couple of fields from `updateDescription`, avoid enabling `updateLookup` unnecessarily.

## 9. Pre-Images and Post-Images

On supporting versions, MongoDB can store **change stream pre- and post-images** when configured on the collection.

Example configuration command in a lab:

~~~javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
~~~

This is a configuration change; never run it in production without verifying server version, retention, storage impact, and admin privileges.

### 9.1. Pre-Image

You can request `fullDocumentBeforeChange` with a supported mode such as **whenAvailable** or **required**.

If pre-images were not captured or already passed retention cleanup, consumers cannot assume prior data is available.

### 9.2. Post-Image

Modes such as **whenAvailable** or **required** for `fullDocument` can return the stored post-image when the feature is enabled. Do not confuse this post-image with `updateLookup`, which reads the current document after the change.

### 9.3. Tokens Remain Independent of Images

Even when `fullDocumentBeforeChange` and `fullDocument` are both populated, **event._id remains the resume token**. Never use document images to reconstruct stream position.

## 10. `$project`: Slimming Payloads While Preserving `_id`

A consumer needing only a few fields:

~~~javascript
db.orders.watch(
  [
    {
      $project: {
        _id: 1,
        operationType: 1,
        ns: 1,
        clusterTime: 1,
        documentKey: 1,
        updateDescription: 1,
        "fullDocument.status": 1,
        "fullDocument.totalCents": 1
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

### 10.1. Why Write `_id: 1` Explicitly?

In ordinary aggregations, `$project` keeps `_id` by default unless excluded. In a change stream, writing **_id: 1** explicitly signals that the token must be preserved and prevents future editors from mistaking it for `documentKey._id`.

### 10.2. Bad Example: Excluding `_id`

~~~javascript
{
  $project: {
    _id: 0,
    operationType: 1,
    documentKey: 1
  }
}
~~~

This strips the resume token from the output; change streams forbid altering or dropping the token.

### 10.3. Bad Example: Replacing `_id` with a Business ID

~~~javascript
{
  $project: {
    _id: "$documentKey._id",
    operationType: 1
  }
}
~~~

This replaces the event token with the order ID. Old and new events for the same order lose their distinct stream positions.

The right approach is to keep `_id` and add another field:

~~~javascript
{
  $addFields: {
    businessId: "$documentKey._id"
  }
}
~~~

## 11. `$unset`: Dropping Unnecessary Fields

Suppose `fullDocument` contains PII:

~~~javascript
{
  $unset: [
    "fullDocument.email",
    "fullDocument.phone",
    "fullDocument.address"
  ]
}
~~~

Never include **"_id"** in `$unset`. Also avoid carelessly dropping `documentKey` if the consumer needs it to delete cache keys or index entries on delete events.

Projection only trims the payload delivered downstream; it does not replace authentication, authorization, TLS, encryption, and log governance.

## 12. `$addFields` / `$set`: Adding Derived Metadata

~~~javascript
db.orders.watch([
  {
    $addFields: {
      eventKind: {
        $concat: [
          "order.",
          "$operationType"
        ]
      },
      businessId: "$documentKey._id"
    }
  }
]);
~~~

Events gain `eventKind` and `businessId` while **event._id remains untouched**.

### 12.1. Normalizing by `operationType`

~~~javascript
{
  $addFields: {
    businessAction: {
      $switch: {
        branches: [
          {
            case: { $eq: ["$operationType", "insert"] },
            then: "created"
          },
          {
            case: { $eq: ["$operationType", "delete"] },
            then: "removed"
          }
        ],
        default: "changed"
      }
    }
  }
}
~~~

### 12.2. Never Use `$set` to Overwrite the Token

Wrong:

~~~javascript
{
  $set: {
    _id: "$documentKey._id"
  }
}
~~~

To expose the business record identifier, create **businessId** instead of overwriting event `_id`.

### 12.3. Missing or Null `fullDocument`

~~~javascript
{
  $addFields: {
    visibleStatus: {
      $ifNull: [
        "$fullDocument.status",
        "UNKNOWN"
      ]
    }
  }
}
~~~

Seeing `UNKNOWN` in the output does not necessarily mean the source document holds `status: "UNKNOWN"`. It may simply mean `fullDocument` is absent or the field is null.

## 13. `$replaceRoot`: Reshaping Without Losing the Token

A very common mistake:

~~~javascript
{
  $replaceRoot: {
    newRoot: "$fullDocument"
  }
}
~~~

`fullDocument._id` is the **document ID**, not the resume token. Moreover, delete events lack `fullDocument`.

### 13.1. Replacing Root Properly

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      _id: "$_id",
      operationType: "$operationType",
      namespace: "$ns",
      businessId: "$documentKey._id",
      payload: "$fullDocument",
      changedFields: "$updateDescription.updatedFields"
    }
  }
}
~~~

The resulting root keeps **_id: "$_id"**, preserving the server-issued resume token.

### 13.2. `$mergeObjects` Overwriting `_id`

If you merge `fullDocument` into the event:

~~~javascript
{
  $replaceRoot: {
    newRoot: {
      $mergeObjects: [
        "$$ROOT",
        "$fullDocument"
      ]
    }
  }
}
~~~

**fullDocument._id** risks overwriting **event._id** because later objects in `$mergeObjects` take precedence on conflicting keys. The safe, readable pattern is constructing an explicit root keeping `_id` from the event.

### 13.3. Do Not Convert the Token to a String Inside the Root

~~~javascript
{
  $project: {
    _id: {
      $toString: "$_id"
    }
  }
}
~~~

Although convenient for logging, this alters the token's type/value and violates change stream invariants. If you need a text format for persistence, serialize the **entire BSON token** outside the pipeline's `_id` via driver APIs.

## 14. Complete Pipeline: Safe Filtering and Transformation

Requirement: receive only `insert`/`update`/`replace`/`delete`, omit email, include `businessId`, and preserve the resume token.

~~~javascript
const pipeline = [
  {
    $match: {
      operationType: {
        $in: ["insert", "update", "replace", "delete"]
      }
    }
  },
  {
    $project: {
      _id: 1,
      operationType: 1,
      clusterTime: 1,
      ns: 1,
      documentKey: 1,
      updateDescription: 1,
      "fullDocument._id": 1,
      "fullDocument.status": 1,
      "fullDocument.totalCents": 1
    }
  },
  {
    $addFields: {
      businessId: "$documentKey._id",
      eventKind: {
        $concat: [
          "orders.",
          "$operationType"
        ]
      }
    }
  }
];

const stream = db.orders.watch(
  pipeline,
  {
    fullDocument: "updateLookup"
  }
);

while (stream.hasNext()) {
  printjson(stream.next());
}
~~~

### 14.1. Fields to Keep by Business Need

| Field | Why Keep It |
| --- | --- |
| `_id` | Resume token |
| `operationType` | Distinguish insert/update/replace/delete |
| `documentKey` | Identify target document even on deletes |
| `ns` | Distinguish collections in broad watch scopes |
| `clusterTime` | Telemetry/logical time |
| `updateDescription` | Newly updated fields |
| `fullDocument` | Data to synchronize, when present |

### 14.2. Why You Usually Shouldn't Filter Out `delete`

If a search-index sync consumer filters out `delete`, deleted source documents remain stuck in the index, corrupting downstream state. Filters should reflect sink requirements, not merely minimize event volume.

## 15. Resume Tokens: Meaning

A **resume token** is a MongoDB-issued BSON value pinpointing a change stream position.

Key options:

- **resumeAfter:** continue reading after a specific token.
- **startAfter:** start after a token, crucial for continuing past `invalidate` under supported semantics.
- **startAtOperationTime:** start at a BSON operation timestamp; not a token.

A token is not a datetime, not a bare `clusterTime`, and not a `documentKey`.

### 15.1. Tokens Are Not Comparable Strings

Do not sort `_data` or JSON strings lexicographically to determine which event is newer. Processing order follows cursor delivery order and consumer checkpointing, not ad-hoc string sorting on tokens.

### 15.2. Bind Watch Scope and Pipeline to Checkpoints

A token produced by pipeline A should not be blindly reused as a checkpoint for consumer B with a different namespace or pipeline. Checkpoint metadata should record `consumerId`, `scope`, and `pipelineVersion`.

## 16. `resumeAfter` Following a Restart

Suppose a consumer reads an event:

~~~javascript
const stream = db.orders.watch();

const change = stream.next();

const token = change._id;

// Process change successfully before saving the token.
~~~

On the next startup:

~~~javascript
const resumed = db.orders.watch(
  [],
  {
    resumeAfter: token
  }
);
~~~

By resume semantics, the stream continues immediately after the specified event position.

### 16.1. Checkpoints Must Track Processing Progress

Correct sequence:

~~~text
Receive E1 -> process E1 successfully -> save E1 token
Receive E2 -> process E2 successfully -> save E2 token
Receive E3 -> crash before processing
Restart resumeAfter(E2)
E3 can be read and processed next
~~~

Dangerous sequence:

~~~text
Receive E3
Save E3 token
Crash before processing E3
Restart resumeAfter(E3)
E3 is skipped
~~~

Never persist the token immediately upon cursor delivery before the business handler commits successfully.

### 16.2. Read-Ahead and Batch Buffering

The driver may prefetch a batch before the application finishes processing each event. Checkpointed tokens must never advance past events still pending in memory.

**A checkpoint asserts that every event prior to that position has been processed successfully**, not merely "seen by the driver."

## 17. Post-Batch Resume Token (PBRT)

A consumer may apply a highly selective filter—for example, watching only transitions to `PAID`, while the source receives lots of unrelated updates.

The server can return a **postBatchResumeToken** in batch/`getMore` responses even when the batch yields zero events matching the filter.

### 17.1. Why Is PBRT Needed?

If a consumer only persists tokens of events it **receives**, the checkpoint can remain frozen for hours or days while the cursor reads newer empty batches.

Upon restart, that stale token may have fallen out of the oplog history window.

PBRT safely advances the checkpoint to the end of the processed batch without inventing synthetic events.

### 17.2. Never Checkpoint PBRT Ahead of Unprocessed Events

Only persist a cursor/post-batch token when:

1. The driver supplies a valid token.
2. Every event delivered before that point has completed processing.
3. No worker holds older pending events.
4. The checkpoint store is durable and ownership is verified.

If E101 is still pending while the cursor has already read up to E110, never checkpoint E110.

### 17.3. PBRT Does Not Extend the Oplog

PBRT keeps checkpoints from going stale during low-match periods. It does not retain extra server history and cannot resurrect expired tokens.

## 18. `startAfter` and `invalidate`

A change stream can receive **`invalidate`** during namespace lifecycle operations, such as collection drop/rename within the watched scope.

### 18.1. `resumeAfter` Does Not Cross `invalidate` Like Normal Events

Do not use `resumeAfter` to resume past an `invalidate` event in the standard way.

### 18.2. `startAfter`

When server version and scope allow watching past an `invalidate` event:

~~~javascript
db.orders.watch(
  [],
  {
    startAfter: invalidateToken
  }
);
~~~

Keep in mind the namespace may have been dropped, renamed, or recreated; consumers must not assume old schemas or data still exist.

### 18.3. Filtering Out `invalidate` and Lifecycle Events

If `$match` filters only for `update`, the consumer might never see lifecycle events before the cursor becomes invalidated. Monitor cursor completion, errors, and recovery workflows rather than counting only matched events.

## 19. `startAtOperationTime`

Some workflows support starting a stream from a valid **BSON Timestamp**:

~~~javascript
db.orders.watch(
  [],
  {
    startAtOperationTime: Timestamp({
      t: 1762000000,
      i: 1
    })
  }
);
~~~

The timestamp above is illustrative. In practice, use an operation time obtained from a server/session within retained oplog history.

### 19.1. Do Not Equate Timestamps with Tokens

A BSON `Timestamp` differs from a JavaScript `Date`. Nor does it replace a resume token, which encodes a finer-grained stream position.

### 19.2. Never Fall Back Silently from a Broken Token to "Now"

If history loss causes `resumeAfter` to fail, restarting from "now" without backfilling creates silent data gaps and corrupts downstream projections.

## 20. Oplog and History-Loss Errors

Change streams depend on replication/change-stream history retained by MongoDB.

If a consumer is offline longer than the history window, resuming fails with a **ChangeStreamHistoryLost**-class error or related error depending on version and state.

### 20.1. Common Causes

- High write throughput shrinks the oplog window.
- Extended consumer downtime.
- Checkpoints stalled due to selective filters without saving PBRT.
- Topology/namespace changes invalidating tokens.
- Pre-/post-image retention insufficient for delayed consumers.

### 20.2. Never Infinitely Retry an Unresumable Token

Wrong:

~~~text
while true:
  resumeAfter(oldToken)
  if history lost:
    sleep 1 second
    retry forever
~~~

Overwritten history will never magically reappear through retries.

### 20.3. Safe Recovery Procedure

1. Stop the consumer or mark it requiring intervention.
2. Record the error, `consumerId`, token, `pipelineVersion`, and timestamp.
3. Distinguish transient network errors from `history lost` / `invalidate`.
4. Reconcile source and sink.
5. Run a controlled resnapshot/backfill or rebuild.
6. Establish a fresh checkpoint without gaps per procedure.
7. Tune oplog sizing and lag alerts to prevent recurrence.

## 21. Resume Tokens Do Not Guarantee Exactly-Once

If a consumer performs side effects before checkpointing:

~~~text
Receive E100
Call external API successfully
Crash before saving E100 token
Restart resumeAfter(E99)
Receive E100 again
Call external API a second time
~~~

That is **at-least-once** behavior: events can be reprocessed.

### 21.1. Checkpointing Before Side Effects Is Even More Dangerous

~~~text
Receive E100
Save E100 token
Crash before performing side effect
Restart resumeAfter(E100)
E100 is never processed
~~~

Therefore, checkpoints should occur **after side effects commit successfully**, paired with idempotency to handle replays.

### 21.2. Idempotency at the Sink

You can use a business event ID or a stable event key derived safely from the token to detect already-processed events.

Conceptual example:

~~~javascript
db.processedEvents.updateOne(
  {
    consumerId: "orders-search-indexer",
    eventKey: "STABLE_EVENT_KEY"
  },
  {
    $setOnInsert: {
      processedAt: new Date()
    }
  },
  {
    upsert: true
  }
);
~~~

This marker is not automatically atomic with side effects in another collection. If both writes live in MongoDB, a transaction may help; if the sink is an external API, rely on an API-supported idempotency key.

### 21.3. Exactly-Once Is an End-to-End Property

You must account for:

- Source events.
- Retries/resumes.
- Checkpointing.
- Side effects.
- Crashes/restarts.
- Duplicates.
- Transaction boundaries/idempotency.
- Pipeline changes and replays.

Never claim exactly-once semantics merely because a consumer uses `resumeAfter`.

## 22. Parallel Processing and Committed Watermarks

Suppose three workers process events concurrently:

~~~text
E101 -> Worker A pending
E102 -> Worker B done
E103 -> Worker C done
~~~

Checkpointing token E103 and crashing would skip E101 upon resume.

### 22.1. Contiguous Prefix

Only checkpoint up to the end of a **fully completed contiguous prefix**:

~~~text
E100 done
E101 pending
E102 done
E103 done

Safe checkpoint: E100
~~~

Once E101 finishes, the checkpoint can advance to E103 if no earlier event remains pending.

### 22.2. Per-Document Ordering

If the same document has E1 updating `status` and E2 updating `total`, finishing E2 before E1 can corrupt downstream state even with careful checkpointing. Partition by `documentKey` or enforce ordering per business key where order matters.

### 22.3. PBRT and Queues

Never use PBRT to skip pending events sitting in worker queues. PBRT indicates a stream-resumable position, not completion of business side effects.

## 23. Persisting Tokens with Exact Data Types

Options:

1. Store the entire token as a BSON document.
2. Serialize as type-preserving Extended JSON and parse back using the matching BSON API.

Example checkpoint metadata:

~~~javascript
{
  _id: "orders-consumer-v3",
  tokenExtendedJson: "{...}",
  pipelineVersion: 3,
  watchScope: "cdc_lab.orders",
  updatedAt: ISODate("2026-11-14T05:00:00Z")
}
~~~

### 23.1. Why Store `pipelineVersion`?

If filter v1 excluded `delete` but v2 needs `delete`, resuming from v1's token will not bring back earlier deletes.

Checkpoints are bound to a **processing semantic**. When changing pipeline logic, evaluate whether backfill/rebuild or cutover is needed.

### 23.2. Do Not Edit `_data`

Never alter, truncate, concatenate, or intuitively compare `_data`. Token internals can evolve across versions and sharded topologies.

### 23.3. Protecting Checkpoints

Checkpoints require durable writes, restricted write permissions, backup/recovery, ownership enforcement, and metrics to detect failed saves.

## 24. Two Consumers Sharing a Checkpoint: Race Conditions

Suppose:

~~~text
Pod A reads token E100 -> processes E101..E105
Pod B reads token E100 -> processes E101..E110

Pod B saves E110
Pod A later saves E105
~~~

The checkpoint can regress, or jump ahead of work another pod has not finished.

### 24.1. A Unique Checkpoint ID Is Not Enough

A unique index on `consumerId` ensures a single checkpoint document exists, but does not prevent two processes from overwriting each other.

### 24.2. Ownership and Fencing

Common patterns:

- Single active consumer with standby instances.
- Time-bounded leases.
- Fencing epochs incremented on leadership changes.
- Conditional updates allowing writes only by the current owner/epoch.
- Idempotent sinks despite duplicates during failover.

When sharding workloads across partitions/consumers, give each partition its own checkpoint and ordering rules.

## 25. Java Sync Driver: Watcher with Filter and Projection

Java Sync Driver example on `cdc_lab.orders`. This illustrates a long-running watcher; production systems still require graceful shutdown and error policies.

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;
import java.util.concurrent.TimeUnit;

public class OrderChangeStreamReader {

    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");

        if (uri == null || uri.isBlank()) {
            throw new IllegalArgumentException(
                    "MONGODB_URI for a replica set/sharded cluster is required"
            );
        }

        List<Document> pipeline = Arrays.asList(
                new Document("$match",
                        new Document("operationType",
                                new Document("$in",
                                        Arrays.asList(
                                                "insert",
                                                "update",
                                                "replace",
                                                "delete"
                                        )
                                )
                        )
                ),
                new Document("$project",
                        new Document("_id", 1)
                                .append("operationType", 1)
                                .append("clusterTime", 1)
                                .append("ns", 1)
                                .append("documentKey", 1)
                                .append("updateDescription", 1)
                                .append("fullDocument.status", 1)
                )
        );

        try (MongoClient client = MongoClients.create(uri)) {
            MongoCollection<Document> orders = client
                    .getDatabase("cdc_lab")
                    .getCollection("orders");

            try (MongoChangeStreamCursor<
                    ChangeStreamDocument<Document>> cursor =
                    orders.watch(pipeline)
                            .fullDocument(FullDocument.UPDATE_LOOKUP)
                            .maxAwaitTime(1, TimeUnit.SECONDS)
                            .cursor()) {

                while (true) {
                    ChangeStreamDocument<Document> event =
                            cursor.tryNext();

                    if (event == null) {
                        continue;
                    }

                    System.out.println(
                            "Type: " + event.getOperationType()
                    );
                    System.out.println(
                            "Key: " + event.getDocumentKey()
                    );
                    System.out.println(
                            "Token: " + event.getResumeToken()
                    );
                }
            }
        }
    }
}
~~~

### 25.1. Event APIs to Distinguish

~~~java
event.getResumeToken();     // Stream position
event.getDocumentKey();     // Document ID/key
event.getOperationType();   // Operation type
event.getFullDocument();    // May be null
event.getUpdateDescription();
~~~

Never substitute `getDocumentKey()` for `getResumeToken()`.

### 25.2. Projection and `_id`

In the Java pipeline, projecting **_id: 1** is intentional. Adding a projection that excludes `_id` strips the token and causes MongoDB to reject the pipeline.

### 25.3. `fullDocument` Can Be Null

Deletes or `updateLookup` misses can cause `getFullDocument()` to return null. Consumers must handle null cleanly instead of assuming every event carries a payload.

## 26. Java: Resuming from a Checkpoint

Example function accepting a `MongoCollection` and a saved `BsonDocument` token:

~~~java
import com.mongodb.client.ChangeStreamIterable;
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.BsonDocument;
import org.bson.Document;

import java.util.Collections;

public class ResumeConsumer {

    public static void consume(
            MongoCollection<Document> orders,
            BsonDocument savedToken
    ) {

        ChangeStreamIterable<Document> watch =
                orders.watch(Collections.emptyList())
                        .fullDocument(FullDocument.UPDATE_LOOKUP);

        if (savedToken != null) {
            watch = watch.resumeAfter(savedToken);
        }

        try (MongoChangeStreamCursor<
                ChangeStreamDocument<Document>> cursor =
                watch.cursor()) {

            while (true) {
                ChangeStreamDocument<Document> event =
                        cursor.tryNext();

                if (event == null) {
                    continue;
                }

                handleBusinessEvent(event);

                // Checkpoint only after the business event
                // has been processed/committed successfully.
                saveCheckpoint(event.getResumeToken());
            }
        }
    }

    private static void handleBusinessEvent(
            ChangeStreamDocument<Document> event
    ) {
        // Replace with real idempotent processing.
    }

    private static void saveCheckpoint(BsonDocument token) {
        // Persist token durably, preserving BSON types.
    }
}
~~~

`handleBusinessEvent` and `saveCheckpoint` are illustrative extension points. Production consumers require termination conditions, error-classified retries, checkpoint ownership, shutdown hooks, and duplicate prevention.

### 26.1. Never Call `resumeAfter(null)`

If no checkpoint exists yet, choose an explicit start strategy (watch from current time, valid operation timestamp, or snapshot+CDC). Never pass a null token expecting the server to guess.

### 26.2. Never Clear Tokens on History Loss

If resuming cannot continue, the consumer must reconcile/backfill rather than resetting the token to null and silently skipping history.

## 27. Java: Encoding and Decoding Tokens Intact

~~~java
import org.bson.BsonDocument;

public class ResumeTokenCodec {

    public static String encode(BsonDocument token) {
        return token == null ? null : token.toJson();
    }

    public static BsonDocument decode(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return BsonDocument.parse(value);
    }
}
~~~

Extended JSON relies on matching BSON serializers/parsers. Never extract only `_data` and try to rebuild a new token.

### 27.1. Why Can't You Compare Token Strings?

Tokens are opaque. Track older/newer order by cursor delivery sequence and checkpoint ownership—not by string comparisons on JSON representations.

## 28. Java: Checkpointing into MongoDB

Example storing `tokenExtendedJson` in a checkpoint collection:

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.Updates;
import org.bson.BsonDocument;
import org.bson.Document;

public class MongoCheckpointStore {

    private final MongoCollection<Document> checkpoints;

    public MongoCheckpointStore(
            MongoCollection<Document> checkpoints
    ) {
        this.checkpoints = checkpoints;
    }

    public BsonDocument load(String consumerId) {
        Document row = checkpoints.find(
                Filters.eq("_id", consumerId)
        ).first();

        if (row == null) {
            return null;
        }

        String json = row.getString("tokenExtendedJson");

        return json == null ? null : BsonDocument.parse(json);
    }

    public void save(
            String consumerId,
            BsonDocument token,
            int pipelineVersion
    ) {
        checkpoints.updateOne(
                Filters.eq("_id", consumerId),
                Updates.combine(
                        Updates.set(
                                "tokenExtendedJson",
                                token.toJson()
                        ),
                        Updates.set(
                                "pipelineVersion",
                                pipelineVersion
                        ),
                        Updates.currentDate("updatedAt")
                ),
                new UpdateOptions().upsert(true)
        );
    }
}
~~~

### 28.1. What Doesn't This Example Handle Yet?

- Two instances writing the same checkpoint concurrently.
- Checkpoints regressing due to concurrent writes.
- Checkpoints and side effects in separate collections outside a single transaction.
- Insufficient checkpoint write concern for durability requirements.
- Duplicate business effects when crashing before checkpointing.
- Pipeline version upgrades and offset migrations.
- Ambiguous save state on server timeouts.

It is a starting point for understanding token persistence, not a complete exactly-once framework.

## 29. Java: PBRT and `cursor.getResumeToken()`

The MongoDB Java Sync Driver exposes a method to retrieve the change stream cursor's current resume token:

~~~java
BsonDocument token = cursor.getResumeToken();
~~~

Depending on context, this reflects either the last event token or the post-batch resume token known to the driver.

When `tryNext()` returns null, a sequential consumer can consider persisting the cursor token to advance idle progress:

~~~java
ChangeStreamDocument<Document> event = cursor.tryNext();

if (event != null) {
    handleBusinessEvent(event);
    saveCheckpoint(event.getResumeToken());
} else {
    BsonDocument idleToken = cursor.getResumeToken();

    if (idleToken != null && noPendingEvents()) {
        saveCheckpoint(idleToken);
    }
}
~~~

**noPendingEvents()** is an application-defined queue check, not a MongoDB API.

If a consumer processes events concurrently, guarantee the token never leaps ahead of pending events. Never treat PBRT as an excuse to skip incomplete business events.

## 30. Retry Policy and State Machine

A consumer can structure its lifecycle as:

~~~text
START
  |
LOAD CHECKPOINT + PIPELINE VERSION
  |
OPEN WATCH OR RESUME
  |
READ EVENT / IDLE TOKEN
  |
  +--- EVENT ---> PROCESS IDEMPOTENTLY
  |                    |
  |                 COMMIT EFFECT
  |                    |
  |                 SAVE TOKEN
  |
  +--- IDLE ----> IF NO PENDING EVENTS
                       |
                    SAVE SAFE CURSOR TOKEN
  |
NEXT READ

Transient resumable error:
  reopen with safe checkpoint and backoff

History lost / invalid pipeline / incompatible scope:
  stop, investigate and reconcile
~~~

### 30.1. Separating Transient Errors from Non-Self-Healing Errors

| Error | Strategy |
| --- | --- |
| Network hiccup/election | Bounded retry with backoff per resumability rules |
| Authentication/authorization | Fix credentials/privileges; do not retry infinitely |
| Pipeline alters `_id` | Fix code and configuration |
| History lost | Resnapshot/backfill/reconcile |
| Invalidate | Handle lifecycle/`startAfter` per scope |
| Sink API error | Retry with idempotency; do not checkpoint ahead |
| Checkpoint store error | Do not advance token unless persisted safely |

### 30.2. Crucial Monitoring Signals

Track:

- Consumer running/retrying/blocked state.
- Last processed event/time.
- Last checkpoint/token update time.
- Consumer lag and oplog window.
- Resume attempts and error labels.
- Sink processing latency and failures.
- Duplicate/idempotency hits.
- Pipeline version and watch scope.
- Owner/lease/fencing epoch.

A watcher with zero matched events for hours **is not necessarily dead**. Use cursor heartbeats/PBRT, `getMore` activity, and oplog lag to distinguish quiet periods from hung consumers.

## 31. Change Streams on Sharded Clusters

A sharded collection distributes ranges across multiple shards. Cluster- or collection-level change streams are coordinated by MongoDB under supported semantics.

### 31.1. Never Merge Per-Shard Oplogs Manually

Do not open separate oplog streams per shard and merge them by `clusterTime`, as ordering and resume semantics are far more subtle.

Use the standard change stream API via `mongos`/driver as supported by the topology.

### 31.2. Tokens in Sharded Clusters Remain Opaque

Never assume `_data` is a simple timestamp or retains an identical layout across topologies and versions.

### 31.3. Migrations Do Not Require Consumers to Track Shard Owners

Chunk migrations and metadata routing belong to the sharding layer. Consumers should not rely on static tenant-to-shard mappings to fetch events.

### 31.4. Observing Resource Consumption

When a change stream merges across shards, monitor write volume, networking, lag, per-shard health, and `mongos` performance across the deployment.

## 32. Pipeline Version Changes and Backfills

Suppose:

~~~text
V1 filter:
  receives operationType update only

V2 filter:
  receives update and delete
~~~

If consumer V2 resumes from V1's token, it will not automatically receive deletes that **occurred prior to V1's checkpoint**.

### 32.1. Change Management Policy

1. Attach pipeline versions to checkpoints.
2. Assess what prior data was filtered out that the new version needs.
3. Perform snapshot/backfill/rebuild if downstream lacks state.
4. Cut over consumers carefully to avoid gaps or rule-breaking duplicates.
5. Run reconciliation checks after deployment.

### 32.2. Not Every Projection Change Requires a Stream Reset

If you simply add a new field without requiring historical backfill, you can apply it from the cutover point forward. The choice depends on downstream contracts.

### 32.3. Running Two Versions Simultaneously

If V1 and V2 run concurrently, give them separate checkpoint IDs/ownership unless an explicit coordination protocol exists.

## 33. Security and PII Reduction

A `users` change stream might inadvertently emit `fullDocument` payloads containing email, phone, address, or sensitive attributes.

Example slim projection:

~~~javascript
db.users.watch(
  [
    {
      $match: {
        operationType: {
          $in: ["insert", "update", "replace", "delete"]
        }
      }
    },
    {
      $project: {
        _id: 1,
        operationType: 1,
        documentKey: 1,
        "fullDocument.displayName": 1,
        "fullDocument.status": 1
      }
    }
  ],
  {
    fullDocument: "updateLookup"
  }
);
~~~

### 33.1. Payload Filtering Does Not Replace RBAC

An over-privileged service remains a risk even if its pipeline trims output fields. Enforce RBAC, TLS, secret management, and log controls independently.

### 33.2. Safe Logging

Never dump full `fullDocument`, pre-images, or tokens alongside PII into debug logs lacking strict retention and access controls.

### 33.3. Schema Evolution

Consumers must tolerate missing/null fields, new `operationType`s, and evolving document shapes. Do not hardcode rigid assumptions about an older application version's `updateDescription` layout.

## 34. Common Mistakes Table

| Mistake | Consequence |
| --- | --- |
| Using `documentKey._id` as resume token | Does not represent event position |
| Projecting `_id: 0` | Strips token; pipeline fails |
| `$replaceRoot` with `$fullDocument` | Replaces/drops `event._id` |
| Setting `_id` to a business ID | Corrupts resume token |
| Storing only the `_data` string | Couples to internal structure |
| Checkpointing before business side effect | Skips unprocessed events on crash |
| Checkpointing cursor token while workers have pending events | Advances past incomplete work |
| Omitting PBRT in heavily filtered streams | Checkpoint stays stale too long |
| Retrying `history lost` forever | Lost history never returns |
| Using `resumeAfter` past `invalidate` | Violates resume semantics |
| Using `clusterTime` instead of token | Lacks exact stream position |
| Filtering only `update` and forgetting `replace`/`delete` | Downstream state drifts |
| Treating `fullDocument.status` as a transition | `updateLookup` may read a later state |
| Two pods writing same checkpoint without leases | Checkpoint regresses or skips ahead |
| Changing pipeline without backfilling | Previously filtered events never arrive |
| Treating `watch()` as an initial snapshot | Pre-existing history is not replayed automatically |
| Treating a silent watcher as dead | Selective filters may simply emit nothing |
| Assuming tokens last forever | Oplog has finite retention |
| Assuming `resumeAfter` gives exactly-once | Side effects can still be duplicated |
| Tailing each shard's oplog and merging by timestamp | Violates sharded change stream semantics |

## 35. Practice Exercises: Events and Pipelines

### Exercise 1 – Token vs. Document ID

Open a watch on `orders`. Update a single order three times. Record `event._id`, `documentKey._id`, `clusterTime`, and `operationType`. Why is the document ID identical while the resume tokens differ?

### Exercise 2 – `$match` on `operationType`

Write a pipeline accepting only `insert`, `update`, and `replace`. Then explain why a search-index sync consumer also needs to handle `delete`.

### Exercise 3 – Filtering Transitions to `PAID`

Compare:

~~~javascript
{
  $match: {
    "updateDescription.updatedFields.status": "PAID"
  }
}
~~~

and:

~~~javascript
{
  $match: {
    "fullDocument.status": "PAID"
  }
}
~~~

Explain the difference between "an event changing status" and "a current document having status `PAID`."

### Exercise 4 – Projection

Project only `_id`, `operationType`, `documentKey`, `clusterTime`, and `fullDocument.status`. Why must `_id` never be replaced with `documentKey._id`?

### Exercise 5 – Replace Root

Fix:

~~~javascript
{
  $replaceRoot: {
    newRoot: "$fullDocument"
  }
}
~~~

into a normalized root that preserves `event._id` and exposes a separate `businessId`.

### Exercise 6 – Delete Events

A consumer clears cache entries on `delete`, but its projection dropped `documentKey`. What information is it missing? Fix the pipeline.

## 36. Practice Exercises: Resume and Checkpointing

### Exercise 7 – Crash Before Checkpoint

~~~text
E1 processed -> E1 token saved
E2 processed -> crash before saving E2 token
~~~

After `resumeAfter(E1)`, what happens? How do you apply idempotency?

### Exercise 8 – Crash After Checkpoint

~~~text
Receive E3 -> save E3 token -> crash before processing E3
~~~

Why might E3 be skipped? Fix the ordering.

### Exercise 9 – Parallel Watermark

~~~text
E100 done
E101 pending
E102 done
E103 done
~~~

Which token can be checkpointed safely? Once E101 finishes, how far can the checkpoint advance?

### Exercise 10 – Idle PBRT

A consumer matches only one event every few hours, while the source produces thousands of events per second. Why is checkpointing only observed `event._id` risky? When is it safe to checkpoint the cursor token?

### Exercise 11 – Oplog History Lost

A consumer is offline for four days while the oplog retains only one day of history. Design a recovery workflow that avoids silent data gaps.

### Exercise 12 – Invalidate

A collection is dropped while a watcher is active. Compare `resumeAfter`/`startAfter`, namespace lifecycle rules, and when resnapshot is required.

## 37. Practice Exercises: Java and Operations

### Exercise 13 – Java Watch

Use the MongoDB Java Sync Driver to create a watcher with `$match`, `$project` preserving `_id: 1`, and `FullDocument.UPDATE_LOOKUP`. Explain how `getResumeToken()` differs from `getDocumentKey()`.

### Exercise 14 – Token Codec

Implement `BsonDocument` encode/decode using `toJson()`/`parse()`, storing `tokenExtendedJson` in a checkpoint store. Why not store `_data` alone?

### Exercise 15 – Checkpoint Ownership

Two pods both load E100, process events, and write checkpoints under the same ID. Analyze the race condition and propose leases/fencing.

### Exercise 16 – Payment Side Effects

A consumer calls a payment API; the call succeeds, and the process crashes before saving the token. How do you prevent double-charging when the event is replayed?

### Exercise 17 – Pipeline Evolution

V1 only watches `update`, while V2 adds `delete`. Why is keeping V1's checkpoint insufficient to rebuild downstream state? Propose a backfill strategy.

### Exercise 18 – Reducing PII

Write a projection on `users` keeping only `displayName`/`status` alongside `event._id` and `documentKey`. List remaining RBAC and logging requirements.

### Exercise 19 – Capacity

Peak write rates spike and a consumer may be offline for 8 hours. How should you monitor the oplog window, consumer lag, and checkpoint progress?

### Exercise 20 – Sharded Stream

A collection is sharded across multiple shards with active chunk migrations. Why should consumers avoid routing by static shard mappings or comparing `_data` strings?

## 38. Pre-Production Checklist

1. Source is a replica set or sharded cluster supporting change streams.
2. Watch scope is explicitly defined.
3. Pipeline uses only supported stages.
4. `event._id` preserves its exact value and BSON type.
5. `documentKey` is retained when the sink needs record IDs.
6. Operation types cover `insert`/`update`/`replace`/`delete`/lifecycle events appropriately.
7. `updateLookup` and pre-/post-images are enabled intentionally.
8. Filters do not accidentally drop events required downstream.
9. Projections trim payload size and PII.
10. Checkpoints occur only after successful processing.
11. Cursor/PBRT checkpoints never leap ahead of pending events.
12. Tokens are persisted in exact BSON or type-preserving Extended JSON.
13. Idempotency or coordinated transactions are implemented.
14. Parallel processing tracks a contiguous committed watermark and ordering.
15. Multi-instance deployments enforce leases, fencing, and ownership.
16. `resumeAfter`/`startAfter` are applied in the right scenarios.
17. History-loss/backfill procedures exist.
18. Pipeline versions are stored alongside checkpoints.
19. Oplog window and consumer lag are monitored.
20. Retry backoff and error classification are configured.
21. Graceful shutdown and cursor cleanup are implemented.
22. Post-incident reconciliation procedures exist.
23. RBAC, TLS, and logging policies are enforced.
24. Tests cover restarts, crashes, duplicates, and zero-match idle periods.
25. Operational health relies on metrics, not merely "watcher process is alive."

## 39. Conclusion

Filtering and transforming MongoDB Change Streams with **$match**, **$project**, **$addFields**, and other supported stages reduces unnecessary events, normalizes payloads, and limits sensitive data sent to consumers.

Yet the single most important rule remains:

> **The `_id` field at the root of a change event is the resume token. Never alter or remove it when filtering or transforming events.**

To expose business record identifiers, place **documentKey._id** in a separate field like `businessId`. When reshaping with `$replaceRoot`, explicitly retain **_id: "$_id"**. To resume, persist the complete BSON token and use `resumeAfter`/`startAfter` according to their exact semantics.

A resilient consumer also requires:

- Checkpointing after side effects commit.
- PBRT during idle/heavily filtered periods without jumping past pending events.
- Idempotency to tolerate event replays.
- Oplog/history monitoring and backfill recovery when tokens expire.
- Pipeline version tracking and checkpoint ownership across multiple instances.

**Preserving the token merely lets you resume at the right stream position; guaranteeing zero lost or duplicated business side effects is the responsibility of end-to-end consumer design.**

## References

- [MongoDB Manual — Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [MongoDB Manual — Change Stream Events](https://www.mongodb.com/docs/manual/reference/change-events/)
- [MongoDB Manual — $match](https://www.mongodb.com/docs/manual/reference/operator/aggregation/match/)
- [MongoDB Manual — $project](https://www.mongodb.com/docs/manual/reference/operator/aggregation/project/)
- [MongoDB Manual — $replaceRoot](https://www.mongodb.com/docs/manual/reference/operator/aggregation/replaceRoot/)
- [MongoDB Manual — $getField](https://www.mongodb.com/docs/manual/reference/operator/aggregation/getField/)
- [MongoDB Manual — Change Stream Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Java Sync Driver — Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/logging-monitoring/change-streams/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
