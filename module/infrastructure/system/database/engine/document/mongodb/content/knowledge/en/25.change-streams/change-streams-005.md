# `fullDocument`, `updateLookup`, and Pre-Images and Post-Images

MongoDB **change streams** enable applications to monitor changes occurring to documents in a supported collection, database, or deployment. A **change event** can be used to synchronize a Redis cache, search index, data warehouse, or projection, send notifications, or record change history.

However, for **update** operations, events normally contain only **the fields that changed**. If a consumer needs the full document, you must choose how to obtain its contents. Specifically, there is a crucial distinction between **fetching the current document** and **retrieving a snapshot of the document at the exact moment of the change**.

In MongoDB, the relevant mechanisms are:

- **`updateDescription`**: reports which fields were modified or removed in an `update` event; it is not the full document image.
- **`fullDocument: "updateLookup"`**: retrieves the **current majority-committed state at lookup time**. That state may already reflect subsequent updates that occurred **after** the event being processed.
- **`fullDocument: "whenAvailable"` / `"required"`**: requests the **post-image**, i.e., the full document **immediately after the event** if captured and still retained.
- **`fullDocumentBeforeChange: "whenAvailable"` / `"required"`**: requests the **pre-image**, i.e., the full document **immediately before the event** if captured and still retained.
- **`changeStreamPreAndPostImages.enabled`**: collection-level configuration to begin storing pre-/post-images for changes occurring **after the feature is enabled**.

Key takeaway:

> **`updateLookup` is a lookup of current state, not the exact post-image of the event.** If you need the exact document before and after **each individual update**, you must use pre-/post-images per MongoDB's supported mechanism and ensure images have not expired.

This lesson covers event structure, `fullDocument` modes, enabling pre-/post-images, image lifecycles, handling insert/update/replace/delete, resume tokens, performance, security, hands-on examples, and production consumer design.

## 1. Change Streams in MongoDB

Change streams are supported on MongoDB deployments with appropriate replication infrastructure, such as **replica sets** and **sharded clusters**. A standard standalone `mongod` does not provide change streams in the same way.

High-level flow:

```text
Application writes document
          │
          ▼
MongoDB primary
          │
          ├── replication / oplog
          │
          ▼
Change achieves majority commit
          │
          ▼
Change stream event
          │
          ▼
Consumer
   ├── Redis invalidation
   ├── Search indexing
   ├── Analytics projection
   ├── CDC
   └── Audit pipeline
```

Change streams emit events for **majority-committed changes** as supported by the server; not every write briefly applied on the primary with `w: 1` becomes a durable emitted event.

In `mongosh`, you can open a stream:

```javascript
const stream = db.orders.watch();

while (stream.hasNext()) {
  const event = stream.next();
  printjson(event);
}
```

The loop may wait indefinitely for events. When practicing, open **two terminals**: Terminal A watching the change stream, and Terminal B writing data.

### 1.1. Operation Types to Handle

| `operationType` | Meaning | Data Typically Needed |
|---|---|---|
| `"insert"` | Document inserted | Newly inserted document |
| `"update"` | Partial document modification | `updateDescription`, pre/post if needed |
| `"replace"` | Document body replaced | New document, and pre-image if needed |
| `"delete"` | Document deleted | `documentKey`, pre-image if needed |
| `"drop"` | Collection dropped | Event metadata |
| `"rename"` | Collection renamed | Event metadata |
| `"invalidate"` | Current stream invalidated in supported contexts | Close/re-resume appropriately |

Certain expanded events and metadata structures depend on MongoDB version and options such as `showExpandedEvents`. Never assume every event is an `update`.

### 1.2. Change Event Structure

An illustrative update event:

```javascript
{
  _id: { token: "opaque-resume-token-placeholder" },
  operationType: "update",
  clusterTime: Timestamp(1772340000, 1),
  ns: {
    db: "shop",
    coll: "orders"
  },
  documentKey: {
    _id: "ORDER-274"
  },
  updateDescription: {
    updatedFields: {
      status: "PAID"
    },
    removedFields: []
  }
}
```

This is **only a simplified structural example**, not a real resume token. In practice:

- **`event._id`** is an **opaque resume token**, not the order document's `_id`.
- **`documentKey`** identifies the document; in sharded collections, it may include shard key components.
- **`clusterTime`** is a MongoDB logical timestamp, not when the consumer received the event.
- **`updateDescription`** describes the update delta.
- **`fullDocument`** and **`fullDocumentBeforeChange`** may or may not be present depending on operation type, mode, and image availability.

Never parse a resume token to infer business versions or granular timestamps.

## 2. Why Do Update Events Omit the Full Document by Default?

Suppose a document is:

```javascript
{
  _id: "ORDER-274",
  customerId: "C-10",
  status: "NEW",
  total: NumberDecimal("125000.00"),
  shipping: {
    city: "Hanoi",
    method: "STANDARD"
  }
}
```

The application runs:

```javascript
db.orders.updateOne(
  { _id: "ORDER-274" },
  {
    $set: {
      status: "PAID",
      "shipping.method": "EXPRESS"
    }
  }
);
```

An update event may look like:

```javascript
{
  operationType: "update",
  documentKey: { _id: "ORDER-274" },
  updateDescription: {
    updatedFields: {
      status: "PAID",
      "shipping.method": "EXPRESS"
    },
    removedFields: []
  }
}
```

The event avoids resending `customerId`, `total`, and every untouched field since they did not change. This keeps notifications compact when updates modify only a few fields.

### 2.1. `updatedFields`, `removedFields`, and Arrays

Common fields:

- `updatedFields`: map of field path → post-change value;
- `removedFields`: list of removed fields;
- `truncatedArrays`: metadata when certain operations shorten arrays, depending on the event;
- Additional path representations such as `disambiguatedPaths` on supporting versions.

Example:

```javascript
db.orders.updateOne(
  { _id: "ORDER-274" },
  {
    $set: { status: "SHIPPED" },
    $unset: { legacyCode: "" }
  }
);
```

The delta may correspond to:

```javascript
{
  updatedFields: { status: "SHIPPED" },
  removedFields: ["legacyCode"]
}
```

**Do not treat `updateDescription` as a standard JSON Patch in every case.** Arrays, field names with dots, embedded documents, and special BSON types follow specific representation rules. A consumer applying deltas onto a snapshot from the wrong point in time can produce a document that diverges from MongoDB's real state.

### 2.2. When Is Delta-Only Sufficient?

- Invalidating a cache by `_id`;
- Counting how often a field changes;
- Forwarding a few simple modifications downstream;
- When the consumer already holds accurate state and a proper delta-application engine.

When you need **the entire document**, **prior values**, or **before/after snapshots for each event**, use the options covered next.

## 3. `fullDocument`: Key Modes

The `fullDocument` option is passed when opening the stream:

```javascript
db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
```

Primary modes:

| Mode | Behavior for Updates | What to Understand |
|---|---|---|
| `"default"` | Does not fetch full document for updates; typically provides delta | `insert`/`replace` already include `fullDocument` |
| `"updateLookup"` | Looks up the **current** majority-committed document | May be newer than the state right after the event |
| `"whenAvailable"` | Returns the exact **post-image** if available | Requires capture enabled beforehand and image not yet purged |
| `"required"` | Demands the exact post-image; errors if unavailable when needed | Does not create or retain images indefinitely |

Modes using pre-/post-images require MongoDB 6.0+ with compatible deployment/FCV/driver support.

### 3.1. `fullDocument: "default"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "default" }
);
```

For updates, default events focus on `updateDescription`. For inserts and replacements, `fullDocument` normally contains the created or replacement document.

Do not misinterpret `"default"` as meaning no events have `fullDocument`.

### 3.2. `fullDocument: "updateLookup"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "updateLookup" }
);
```

On update events, MongoDB looks up the document by its key to attach a **current majority-committed copy of the document**.

Benefits:

- Consumers obtain the full document **without enabling pre-/post-image capture**.
- Works well when a projection or search index only needs to converge to current state.
- Avoids writing complex manual delta-patching logic.

Limitations:

- Not a point-in-time post-state image for the event itself.
- Adds read operations and full-document transmission overhead.
- If the document was deleted before lookup, `fullDocument` can be `null`.
- Under rapid updates, the event's delta and `fullDocument` can describe **two different points in time**.

### 3.3. `fullDocument: "whenAvailable"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "whenAvailable" }
);
```

For updates needing a post-image, the server returns the **document snapshot immediately following that specific update event** if pre-/post-image capture is enabled on the collection and the image is still retained.

If the image is unavailable, the consumer receives `null`/omitted image rather than failing the stream solely because of it.

### 3.4. `fullDocument: "required"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocument: "required" }
);
```

If no post-image is available for an event that requires one, the server raises an error so the consumer knows **the mandatory data contract was violated**.

`required` mode does not resurrect missing images. Nor does it force a delete event to produce a post-delete document: the post-state of a delete is no document.

## 4. `updateLookup` Is Not an Exact Post-Image

This is the single most critical concept for audit and CDC design.

Suppose a document changes in rapid succession:

```text
T0:
  { _id: "O1", status: "NEW",     version: 1 }

T1: Update A
  { _id: "O1", status: "PAID",    version: 2 }
  Event A is generated.

T2: Update B
  { _id: "O1", status: "SHIPPED", version: 3 }
  Event B is generated.

T3: Consumer processes event A and MongoDB executes updateLookup.
```

Because update B is already majority-committed at T3, `fullDocument` attached to **event A** may contain:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O1" },
  updateDescription: {
    updatedFields: {
      status: "PAID",
      version: 2
    }
  },
  fullDocument: {
    _id: "O1",
    status: "SHIPPED",
    version: 3
  }
}
```

There is no bug here:

- **The delta** describes change **A**: `NEW` → `PAID`.
- **The lookup full document** reflects current state: `SHIPPED`.

### 4.1. Audit Design Pitfall

If a consumer reads:

```javascript
event.fullDocument.status
```

and logs it as "the value right after update A," the audit log may record `SHIPPED` instead of `PAID`.

Solutions:

- If you only need modified fields: use `updateDescription`.
- If you need **the full document immediately after update A**: use exact post-images.
- If you need **both before and after A**: use paired pre-/post-images.
- If you only need latest state for caches/indexes: `updateLookup` may fit, provided you do not label it a historical post-image.

### 4.2. `updateLookup` Can Be Null After a Delete

Timeline:

```text
T1: Update O1.
T2: Delete O1.
T3: Consumer looks up fullDocument for the T1 update event.
```

By T3, the document no longer exists. The lookup returns no document.

**Never infer that an update event with `fullDocument: null` is a delete event.** Always check `operationType` and handle delete events explicitly.

### 4.3. Manual Demos Do Not Always Trigger the Race

In a slow manual exercise, `updateLookup` may finish before update B and return `PAID`. Under production workloads with concurrent updates and consumer lag, it **can and will** return `SHIPPED`.

This is **by design**, not a rare edge case you can ignore.

## 5. Pre-Image and Post-Image: Exact Event-Time State

Consider an update:

```text
                     UPDATE status = "PAID"
                       │
          ┌────────────┴────────────┐
          │                         │
    PRE-IMAGE                 POST-IMAGE
    status = NEW              status = PAID
    version = 1               version = 2
```

- **Pre-image**: the document as it existed **immediately before** the change.
- **Post-image**: the document as it existed **immediately after** the change.
- The pair describes **the exact observed event**, not a later document query.

If update A is immediately followed by update B, A's post-image remains the state **after A**, while B's pre-image is the state **before B** when capture is enabled.

### 5.1. Table by Event Type

| Event | Pre-Image | Post-Image / Full Document |
|---|---|---|
| `insert` | No document existed before insert | Newly created document |
| `update` | Pre-update document if captured | Exact post-update document if captured |
| `replace` | Pre-replace document if captured | Replacement document |
| `delete` | Pre-delete document if captured | No document exists after delete |
| `drop`/`rename`/`invalidate` | Not a document pre-image | Event metadata, not a document post-image |

**Delete events are where pre-images shine:** a deleted document cannot be queried from the live collection to recover old fields.

### 5.2. Pre-Image on Delete

A normal delete event has:

```javascript
{
  operationType: "delete",
  documentKey: { _id: "O1" }
}
```

If you need to update a metric grouped by `customerId` or audit the monetary value of the deleted record, `documentKey` alone may not suffice.

With a pre-image available:

```javascript
{
  operationType: "delete",
  documentKey: { _id: "O1" },
  fullDocumentBeforeChange: {
    _id: "O1",
    customerId: "C-10",
    status: "SHIPPED",
    total: NumberDecimal("125000.00")
  }
}
```

The consumer sees **exactly how the document looked right before deletion**.

### 5.3. Pre-/Post-Images Are Not Backups

Images:

- Are not retroactively generated for changes before enabling;
- Have finite retention and still depend on the oplog window;
- Incur storage overhead;
- Do not replace backups, point-in-time recovery, or long-term audit stores.

If business compliance requires multi-year history, build an independent audit/event store with dedicated retention, access control, and recoverability.

## 6. Enabling Pre-/Post-Image Capture on a Collection

Change stream pre-/post-images are supported starting in **MongoDB 6.0** on compatible deployments.

### 6.1. Creating a New Collection

On a test replica set:

```javascript
use changeImageLab;

db.createCollection(
  "orders",
  {
    changeStreamPreAndPostImages: {
      enabled: true
    }
  }
);
```

### 6.2. Enabling on an Existing Collection

```javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: true
  }
});
```

These commands alter collection configuration. Never run them in production without verifying server version, FCV, admin privileges, image storage cost, and retention planning.

### 6.3. Enabling Capture Is Not Retroactive

Suppose:

```text
T1: Document O1 is updated.
T2: changeStreamPreAndPostImages.enabled = true is set.
T3: O1 is updated again.
```

Images for event T1 **are not reconstructed retroactively**. Capture applies only to changes occurring **after enabling**, per server rules.

You cannot open a stream at T3 with `required` and expect exact pre-/post-images for last month's events if capture was off back then.

### 6.4. Disabling Capture

```javascript
db.runCommand({
  collMod: "orders",
  changeStreamPreAndPostImages: {
    enabled: false
  }
});
```

Disabling capture for future changes **does not immediately purge already stored images**. Existing images follow configured lifecycle/retention rules.

### 6.5. Collection Enablement and Consumer Request Are Two Separate Steps

Once a collection has capture enabled:

```javascript
// Lightweight consumer: delta only.
db.orders.watch();

// Consumer wanting latest lookup.
db.orders.watch([], {
  fullDocument: "updateLookup"
});

// Consumer wanting exact before/after.
db.orders.watch([], {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
});
```

Each stream selects what **is returned to that consumer**, whereas server-side capture overhead is determined by collection settings. Never enable image capture on every collection simply because one consumer wants a few extra fields.

## 7. `fullDocumentBeforeChange`: Requesting Pre-Images

Two primary modes:

```javascript
{
  fullDocumentBeforeChange: "whenAvailable"
}
```

or:

```javascript
{
  fullDocumentBeforeChange: "required"
}
```

### 7.1. `"whenAvailable"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocumentBeforeChange: "whenAvailable" }
);
```

If a pre-image was captured and still exists, `update`/`replace`/`delete` events include `fullDocumentBeforeChange`.

If the image is missing (never enabled, expired by retention, etc.), the consumer receives `null` or an omitted image field rather than failing immediately solely due to the missing image.

Appropriate when the pre-image is **enrichment**, not mandatory for every single record.

### 7.2. `"required"`

```javascript
const stream = db.orders.watch(
  [],
  { fullDocumentBeforeChange: "required" }
);
```

If the server cannot provide a pre-image **for an event that should have one**, the stream errors out. This is the right choice when **exact auditing** is a hard requirement.

However:

- Inserts naturally have no before-document.
- Deletes naturally have no after-document.
- `required` does not create images for events prior to enabling capture.
- `required` does not extend retention indefinitely.
- When an image expires, the consumer needs an explicit **recovery policy**.

### 7.3. Comparing Missing-Image Handling

| Scenario | `whenAvailable` | `required` |
|---|---|---|
| Image available | Returns image | Returns image |
| Expected image missing | Continues with null/missing image | Raises an error |
| Pipeline must keep running despite missing metadata | Better fit | May halt |
| Audit must never miss old values | Insufficient if relying on stream alone | Better fit, but needs retention/recovery |
| Risk of silently hiding missing data | Higher if code ignores nulls | Lower; failures surface explicitly |
| Collection image storage cost | Still incurred | Still incurred |

**`required` is a missing-data detection policy, not an infinite data-retention policy.**

## 8. Combining `fullDocument` and `fullDocumentBeforeChange`

When you want before/after pairs:

```javascript
const stream = db.orders.watch(
  [],
  {
    fullDocument: "whenAvailable",
    fullDocumentBeforeChange: "whenAvailable"
  }
);
```

When images are mandatory:

```javascript
const stream = db.orders.watch(
  [],
  {
    fullDocument: "required",
    fullDocumentBeforeChange: "required"
  }
);
```

An update event carrying both images:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O1" },
  updateDescription: {
    updatedFields: { status: "PAID" },
    removedFields: []
  },
  fullDocumentBeforeChange: {
    _id: "O1",
    status: "NEW",
    version: 1
  },
  fullDocument: {
    _id: "O1",
    status: "PAID",
    version: 2
  }
}
```

In real events, images contain the **complete document**; this example trims fields to highlight the state transition.

### 8.1. Can You Combine Pre-Image with `updateLookup`?

Yes, syntactically:

```javascript
db.orders.watch([], {
  fullDocument: "updateLookup",
  fullDocumentBeforeChange: "whenAvailable"
});
```

However, in that configuration:

- `fullDocumentBeforeChange` represents state **before the event**;
- `fullDocument` represents **current state at lookup time**.

They are **not guaranteed to be a before/after pair for the same change**. Never compute historical business diffs by comparing those two objects if documents continue changing concurrently.

## 9. Two-Terminal Hands-On: Observing Insert, Update, Replace, and Delete

Prerequisites: MongoDB 6.0+ replica set or sharded cluster supporting change stream images, `mongosh`, and required privileges.

### 9.1. Terminal B: Prepare the Collection

```javascript
use changeImageLab;

db.createCollection(
  "orders",
  {
    changeStreamPreAndPostImages: {
      enabled: true
    }
  }
);
```

If the collection already exists, use `collMod` instead of recreating it. To repeat exercises, pick a new `_id` to avoid duplicate-key errors or clean up only the test record cleanly:

```javascript
db.orders.deleteOne({ _id: "O-274" });
```

Avoid calling `drop()` while watching, since drop/invalidate can terminate a collection-level stream.

### 9.2. Terminal A: Open the Stream

```javascript
use changeImageLab;

const stream = db.orders.watch(
  [],
  {
    fullDocument: "whenAvailable",
    fullDocumentBeforeChange: "whenAvailable",
    maxAwaitTimeMS: 1000
  }
);

while (stream.hasNext()) {
  const e = stream.next();

  printjson({
    token: e._id,
    operationType: e.operationType,
    documentKey: e.documentKey,
    updateDescription: e.updateDescription,
    before: e.fullDocumentBeforeChange,
    after: e.fullDocument
  });
}
```

Terminal A will wait for events. `maxAwaitTimeMS` controls cursor awaiting/batching behavior per API semantics—it **does not guarantee a new event every second**.

### 9.3. Terminal B: Insert

```javascript
db.orders.insertOne({
  _id: "O-274",
  customerId: "C-10",
  status: "NEW",
  version: 1,
  total: NumberDecimal("100.00"),
  shipping: { method: "STANDARD" }
});
```

The insert event carries `fullDocument` for the new document. No pre-image exists because the document did not exist prior to insert.

### 9.4. Terminal B: First Update

```javascript
db.orders.updateOne(
  { _id: "O-274" },
  {
    $set: {
      status: "PAID",
      "shipping.method": "EXPRESS"
    },
    $inc: { version: 1 }
  }
);
```

Illustrative event:

```javascript
{
  operationType: "update",
  updateDescription: {
    updatedFields: {
      status: "PAID",
      "shipping.method": "EXPRESS",
      version: 2
    },
    removedFields: []
  },
  before: {
    _id: "O-274",
    status: "NEW",
    version: 1,
    shipping: { method: "STANDARD" }
  },
  after: {
    _id: "O-274",
    status: "PAID",
    version: 2,
    shipping: { method: "EXPRESS" }
  }
}
```

This is abridged; actual pre-/post-images also include fields like `customerId` and `total`.

### 9.5. Terminal B: Second Update

```javascript
db.orders.updateOne(
  { _id: "O-274" },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 }
  }
);
```

The next event carries **pre-image `PAID`** and **post-image `SHIPPED`**. Meanwhile, the earlier event still retains post-image **`PAID`**—it does not mutate into `SHIPPED` the way `updateLookup` can.

### 9.6. Terminal B: Replace

```javascript
db.orders.replaceOne(
  { _id: "O-274" },
  {
    _id: "O-274",
    customerId: "C-10",
    status: "DELIVERED",
    version: 4,
    total: NumberDecimal("100.00")
  }
);
```

For `replace`, `fullDocument` holds the replacement document, while any pre-image describes the state right before replacement.

MongoDB can emit `replace` events for certain operations an application might informally think of as "updates" under specific conditions, so consumers should never handle only `operationType: "update"`.

### 9.7. Terminal B: Delete

```javascript
db.orders.deleteOne({ _id: "O-274" });
```

The delete event provides `documentKey` and the **pre-image** if captured. There is no post-delete document.

A search-index consumer may only need `documentKey` to delete the entry, whereas an audit consumer may need the full pre-image.

## 10. Comparing Three Streams on the Same Workload

Open three independent consumers:

```javascript
// Consumer 1: delta only.
const s1 = db.orders.watch([], {
  fullDocument: "default"
});

// Consumer 2: lookup latest state.
const s2 = db.orders.watch([], {
  fullDocument: "updateLookup"
});

// Consumer 3: event-time images.
const s3 = db.orders.watch([], {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
});
```

Give each consumer its own loop/terminal so it does not block commands in the same shell.

Issue rapid consecutive updates:

```javascript
db.orders.insertOne({
  _id: "FAST-1",
  status: "NEW",
  version: 1
});

db.orders.updateOne(
  { _id: "FAST-1" },
  {
    $set: { status: "PAID" },
    $inc: { version: 1 }
  }
);

db.orders.updateOne(
  { _id: "FAST-1" },
  {
    $set: { status: "SHIPPED" },
    $inc: { version: 1 }
  }
);
```

| Stream | For the Update Event Setting `PAID` |
|---|---|
| Default | Contains delta `status: PAID`; no full document lookup |
| Update lookup | May observe `PAID` **or `SHIPPED`** depending on lookup timing |
| Pre-/post-images | Before `NEW`, after `PAID` when images are captured |

A manual demo does not guarantee reproducing the race so `updateLookup` observes `SHIPPED`. Outcome depends on update timing and consumer/lookup lag rather than failing identically every run.

## 11. Lifecycle and Retention of Pre-/Post-Images

MongoDB manages image data internally, described via mechanisms such as `config.system.preimages` in the documentation. Images are not retained forever by default in every configuration.

There are **two distinct limits** to separate:

1. **Oplog window**: how long change events retain history needed to resume.
2. **Pre-/post-image retention**: how long captured images remain stored for retrieval.

A consumer might still hold a valid resume token while **an event's image** has already expired; conversely, image TTL might be configured longer while the **oplog entry** needed to resume has fallen out of the oplog.

### 11.1. `expireAfterSeconds`

On supporting versions/deployments, image TTL can be managed via a cluster parameter:

```javascript
db.adminCommand({
  setClusterParameter: {
    changeStreamOptions: {
      preAndPostImages: {
        expireAfterSeconds: 3600
      }
    }
  }
});
```

This is an admin-privileged example for test environments. `3600` seconds is illustrative, not a universal recommendation.

Inspect the configuration where supported:

```javascript
db.adminCommand({
  getClusterParameter: "changeStreamOptions"
});
```

Command availability or management UI controls can differ between self-managed MongoDB and managed services. Check the guide for your deployment.

### 11.2. `"off"` Does Not Mean Keep Forever

Setting `expireAfterSeconds` to `"off"` in supported configurations means no separate second-based TTL is imposed; **images still remain bound to the lifecycle of their corresponding oplog events**.

Once the corresponding oplog entry is evicted, images do not provide unlimited history. Never build multi-year audit retention policies on top of `"off"`.

### 11.3. Never Modify the Internal Image Store Directly

Never manually delete or update documents inside the internal collection storing pre-/post-images. Rely on MongoDB's official retention and maintenance mechanisms while monitoring storage and capacity.

### 11.4. Image Capture Can Consume Heavy Storage

A collection averaging 200 KB per document under heavy update traffic can accumulate huge image volumes, even when each update changes only one small field.

Estimate:

- Average and p95/p99 document size;
- Updates/replaces/deletes per second;
- Share of updates touching large documents;
- Desired retention window;
- Disk/network/replication overhead;
- Demand across multiple consumers.

Do not enable images on every collection just to "have extra info" without a clear use case.

## 12. Change Event Size Limits

A MongoDB event must obey the BSON document size limit. Returning both a full pre-image and a full post-image—plus `updateDescription`, `documentKey`, and metadata—can make the combined event very large.

Example:

```text
Pre-image:         large document
Post-image:        large document
Metadata/delta:    additional bytes
          │
          ▼
May exceed BSON event size limit
```

The fact that a single document fits within the limit **does not guarantee** an event carrying two copies of a large document fits.

Collections with documents/arrays approaching the maximum BSON size require worst-case testing when requesting both images. Consumer-side pipeline projections do not necessarily eliminate server-side capture overhead.

## 13. Cost of `updateLookup` vs. Image Capture

### 13.1. Update Lookup

Advantages:

- Requires no prior image-capture setup.
- Fetches latest state suitable for projections.
- Not constrained by image TTL for state lookup (still constrained by oplog/resume).

Costs:

- Additional read lookups against the source collection;
- Extra network/serialization overhead for full documents;
- Can add latency when documents are large or shards are busy;
- Not accurate for event-time historical state;
- Returns `null` if the document has already been deleted.

### 13.2. Pre-/Post-Images

Advantages:

- Exact event-time before/after states while retained.
- Ideal for auditing, rollback analysis, and historical CDC.
- Avoids querying live documents to guess past states.

Costs:

- Write/storage amplification because the server persists images;
- Retention management;
- Larger event payloads;
- Heightened PII exposure surface;
- `required` mode halts consumers if images become unavailable.

There is no blanket rule that "pre-/post-images are always faster than `updateLookup`." Benchmark against your document sizes, update rates, consumer count, replication/storage budget, and SLOs.

## 14. Missing Images: Causes and Responses

Common causes:

1. Capture was not enabled on the collection when the event occurred.
2. Capture was enabled too late.
3. Capture was turned off before the event.
4. Image TTL expired.
5. Corresponding oplog entry/image was evicted.
6. Event type inherently lacks a pre- or post-document.
7. Consumer pipeline filtered/projected out the image fields.

### 14.1. `whenAvailable`: Fallback Handling

```javascript
function handleEvent(event) {
  if (event.operationType !== "update") {
    return;
  }

  const after = event.fullDocument;

  if (after == null) {
    // Exact post-image is missing.
    // Depending on business rules: flag for reconciliation,
    // fetch latest state, or skip enrichment.
    print("Post-image unavailable");
    printjson(event.documentKey);
    return;
  }

  // Process exact post-state of the event.
}
```

Falling back to reading current state is valid only when consumers accept latest state. Never pass off a delayed state lookup as a "historical post-image" in an audit log.

### 14.2. `required`: Failure Signals a Contract Violation

If compliance auditing demands before/after images for every change, missing images must never be silently ignored.

Example runbook:

```text
Missing required image
     │
     ▼
Change stream error
     │
     ├── Alert and mark pipeline DEGRADED
     ├── Do not advance checkpoint past unprocessed event
     ├── Reconcile against source/backups/other audit logs
     ├── Identify the window of lost image history
     └── Rebuild or formally report recovery boundaries
```

You cannot force the server to regenerate an exact pre-image after retention expires unless another historical source exists.

## 15. Resume Tokens and Checkpointing

A change stream may run for days, yet applications must survive restarts, deployments, network blips, and primary stepdowns.

Each event carries `_id` as an **opaque resume token**:

```javascript
const event = stream.next();
const token = event._id;
```

Consumers must persist the token after side effects succeed according to contract.

### 15.1. Resuming After a Restart

Illustrative example:

```javascript
const tokenFromCheckpointStore = null; // Replace with saved BSON token.

const options = {
  fullDocument: "whenAvailable",
  fullDocumentBeforeChange: "whenAvailable"
};

if (tokenFromCheckpointStore != null) {
  options.resumeAfter = tokenFromCheckpointStore;
}

const stream = db.orders.watch([], options);
```

Serialize and deserialize tokens using supported BSON APIs rather than converting tokens to arbitrary strings and guessing how to parse them back.

### 15.2. Checkpointing Order

Wrong:

```text
Receive event E
    ↓
Save token(E)
    ↓
Process E fails
```

On restart, the stream resumes **after E**, skipping E.

Better:

```text
Receive event E
    ↓
Process side effect idempotently
    ↓
Confirm side effect committed
    ↓
Save token(E)
```

If the process crashes **after committing the side effect but before saving the checkpoint**, E will be redelivered. Thus consumers need idempotency/at-least-once semantics, or must commit both checkpoint and side effect inside the same transaction if the target store supports it.

### 15.3. Resume Tokens Are Not Business Versions

Never use event `_id` as:

- Document modification count;
- UTC timestamp;
- Global client business sequence;
- User ID.

If per-document ordering is needed, maintain an incrementing `version` field or serialize processing per key in the application.

### 15.4. `resumeAfter` and `startAfter`

Distinguish normal resumption from opening a stream **after an `invalidate` event** via supported APIs. In invalidation scenarios, `startAfter` follows specific rules; never assume `resumeAfter` works across every event/token.

### 15.5. Old Tokens Exceeding the Oplog Window

If a consumer stays down too long, the oplog entry needed to resume vanishes. You cannot drop the token, open a fresh stream, and claim the projection is "in sync" while missing intermediate changes.

Design a **full resync**: snapshot current data, align a CDC starting boundary, replay deltas, and reconcile before declaring the projection complete.

## 16. Event Ordering and Consumer Races

Even when the server delivers change events in order, **consumer applications** can scramble order when processing concurrently.

```text
Event A: O1, version=2, status=PAID
Event B: O1, version=3, status=SHIPPED

Worker 1 receives A but runs slowly.
Worker 2 receives B and writes projection version 3.
Worker 1 writes projection version 2 last.
```

The final projection **regresses to version 2**.

Solutions:

- Partition work by document key so events for the same key process sequentially.
- Or use atomic conditional version updates at the sink.
- Enforce idempotency so replayed events cause no duplicate side effects.
- With `updateLookup`, remember an older event can return a newer state from the lookup; never attach a delta's version and treat the looked-up document as belonging to that version.

Conceptual snippet:

```javascript
if (eventVersion > projectionVersion) {
  // Atomic conditional upsert by document key.
  applyNewerProjection();
} else {
  ignoreOlderEvent();
}
```

`version` on source documents is **an application-managed field**, not an automatic MongoDB counter on every document.

## 17. Using `operationType` Properly

### 17.1. Insert

```javascript
db.orders.insertOne({
  _id: "O-1",
  status: "NEW"
});
```

Insert events carry `fullDocument` for the new document; no pre-image exists.

### 17.2. Update

```javascript
db.orders.updateOne(
  { _id: "O-1" },
  { $set: { status: "PAID" } }
);
```

Update events carry `updateDescription`. For the whole document, use `updateLookup` or post-images. For before/after, use pre-/post-images.

### 17.3. Replace

```javascript
db.orders.replaceOne(
  { _id: "O-1" },
  {
    _id: "O-1",
    status: "SHIPPED"
  }
);
```

Replace events carry the new full document; pre-images show the pre-replace document when captured. Consumers must handle `replace` separately from `update` because `replace` does not use the same delta format.

### 17.4. Delete

```javascript
db.orders.deleteOne({ _id: "O-1" });
```

Delete events provide `documentKey`. If consumers need deleted fields, use pre-images; `updateLookup` cannot bring back a deleted document.

### 17.5. Invalidate and DDL

A `drop`/`rename` can generate lifecycle control events. `invalidate` can close the stream depending on watch scope. Consumers must not ignore it and block on `hasNext()` forever as if the stream were healthy.

Handling DDL/`invalidate` and `startAfter` must follow exact server-version semantics.

## 18. Change Streams on Sharded Clusters

In a sharded cluster:

- `mongos` merges events from multiple shards.
- `documentKey` can include `_id` plus relevant shard key fields.
- Modifying shard key values follows specific rules depending on version and operation type.
- Event ordering must rely on change stream mechanics, never inferred from per-node wall clocks.
- A single document's pre-/post-image is not a **cluster-wide** consistent snapshot.
- Resume tokens are server-managed—never constructed from business IDs.

Example when the shard key is `{tenantId: 1, orderId: 1}`:

```javascript
{
  documentKey: {
    tenantId: "TENANT-A",
    orderId: "O-9",
    _id: ObjectId("65a12f010000000000000001")
  }
}
```

Consumers must not assume `documentKey` contains only `_id`.

### 18.1. A Transaction Is Not a Single Change Event

A transaction modifying `orders` and `payments` emits separate events for the respective documents and collections. An order's pre-/post-image **does not carry the payment snapshot**.

If downstream systems require cross-document invariants, use transactions/outboxes, grouping, or reconciliation. Never treat one document's before/after images as a "cluster-wide transaction snapshot."

## 19. Sensitive Data in Pre-Images

Pre-images can retain user data that was **modified or deleted**:

```javascript
{
  _id: "USER-1",
  email: "old@example.com",
  phone: "0123456789",
  homeAddress: "Old street address"
}
```

If the application deletes an address from the live document, pre-images within the retention window still contain the old value. Consequences:

- Grant change-stream read privileges strictly to services that need them.
- Never `printjson(event)` containing PII into production logs.
- Define explicit retention and privacy policies.
- Enforce encryption, access controls, and auditing on checkpoints and downstream storage.
- When fulfilling data-erasure requests, check whether erased data lingers in images, backups, or audit logs.
- Never treat event payloads as authorization for every downstream service to persist sensitive data.

### 19.1. Use Watch Pipelines Carefully

You can filter operation types:

```javascript
const stream = db.orders.watch(
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
    fullDocument: "whenAvailable",
    fullDocumentBeforeChange: "whenAvailable"
  }
);
```

Do not use `$project` recklessly to remove or alter **event `_id`** (the resume token); modifying the token causes stream errors or breaks resumption.

A watch pipeline reduces what downstream receives, yet **does not eliminate server-side image capture overhead** enabled on the source collection.

### 19.2. Change Streams Do Not Supply Business Actors Automatically

An event tells you a document was updated, not the `userId` of whoever clicked the button, the request ID, or the business justification unless the application stores that metadata.

If audits require "who changed it, when, and why," write explicit domain audit records with actor/correlation IDs instead of relying solely on change streams.

## 20. Java MongoDB Driver: `updateLookup`

The Java Sync Driver provides `ChangeStreamIterable` and `ChangeStreamDocument<T>`.

Skeleton example:

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import org.bson.Document;

MongoCollection<Document> orders =
    database.getCollection("orders");

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         orders.watch()
             .fullDocument(FullDocument.UPDATE_LOOKUP)
             .cursor()) {

    while (cursor.hasNext()) {
        ChangeStreamDocument<Document> event = cursor.next();

        System.out.println("operation=" + event.getOperationType());
        System.out.println("key=" + event.getDocumentKey());
        System.out.println("delta=" + event.getUpdateDescription());
        System.out.println("full=" + event.getFullDocument());
    }
}
```

In this mode, `getFullDocument()` on update events returns the **current lookup**, not a historical exact post-image.

### 20.1. Java Driver: Event-Time Images

On supporting Java Driver versions:

```java
import com.mongodb.client.MongoChangeStreamCursor;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.FullDocumentBeforeChange;
import org.bson.Document;

MongoCollection<Document> orders =
    database.getCollection("orders");

try (MongoChangeStreamCursor<ChangeStreamDocument<Document>> cursor =
         orders.watch()
             .fullDocument(FullDocument.WHEN_AVAILABLE)
             .fullDocumentBeforeChange(FullDocumentBeforeChange.WHEN_AVAILABLE)
             .cursor()) {

    while (cursor.hasNext()) {
        ChangeStreamDocument<Document> event = cursor.next();

        Document before = event.getFullDocumentBeforeChange();
        Document after = event.getFullDocument();

        System.out.println("key=" + event.getDocumentKey());
        System.out.println("before=" + before);
        System.out.println("after=" + after);
    }
}
```

This is not a complete production consumer. You still need:

- A restart/resume loop;
- Error classification;
- Proper token persistence timing;
- Idempotency;
- Per-document-key ordering control;
- Timeouts and health metrics;
- Shutdown and connection lifecycle management;
- Sensitive data redaction;
- Null-image fallbacks;
- Memory and batching controls.

### 20.2. Resume Tokens in Java

Inside event handling:

```java
var token = event.getResumeToken();
```

Tokens must be persisted in BSON or a driver-supported representation; never assume you can parse arbitrary stringified tokens.

On restart, use the appropriate resume API and verify the oplog still retains required history.

### 20.3. Spring Data MongoDB

Spring Data MongoDB provides change stream APIs and document mapping options. However, builder support for `fullDocumentBeforeChange`, `whenAvailable`/`required` modes, and DTO mapping depends on your Spring Data and Java Driver versions.

When deploying, verify:

1. Server version and FCV;
2. Driver/framework versions;
3. That watch options are passed through accurately to MongoDB;
4. BSON types such as `Decimal128`, `Date`, and `ObjectId`;
5. Resume token handling;
6. Subscription lifecycle;
7. Consumer lag and error handling.

Never assume `updateLookup` in an older builder provides the same behavior as exact post-images in MongoDB 6.0+.

## 21. Design by Use Case

### 21.1. Cache Invalidation

If the goal is simply deleting a Redis key whenever an order changes:

```javascript
{
  operationType: "update",
  documentKey: { _id: "O1" }
}
```

is usually enough. There is no need to enable image capture or `updateLookup`.

Exception: cache keys derived from **old** field values (e.g., `customerId` prior to reassignment) may require pre-images or a separate lookup mapping.

### 21.2. Latest-State Search Index

Consumers can:

- Insert/replace: upsert from `fullDocument`.
- Update: use `updateLookup` if current state is acceptable, or exact post-images if event-time state is required.
- Delete: delete by `documentKey`.
- Use versions/idempotency to prevent delayed processing from overwriting newer state.

If `updateLookup` on an update event returns `null` because the document was deleted, distinguish that from the delete event itself and ensure the final search index state is consistent.

### 21.3. Before/After History Auditing

If every single change step must be captured accurately:

```javascript
db.orders.watch([], {
  fullDocument: "required",
  fullDocumentBeforeChange: "required"
});
```

Requires capture enabled on the collection beforehand, sufficient retention, monitoring, and recovery plans.

Not every operation has both before and after: inserts lack before, deletes lack after. Audit schemas must model these natural cases cleanly.

### 21.4. CDC to a Data Warehouse

A complete CDC pipeline must:

1. Bootstrap a snapshot of documents existing before the stream opened.
2. Establish a change-stream starting boundary so nothing is lost between snapshot and CDC.
3. Handle `insert`, `update`, `replace`, and `delete`.
4. Choose latest lookup or exact images per requirements.
5. Normalize BSON types and handle schema evolution.
6. Persist checkpoints after downstream commits.
7. Rebuild if an old token can no longer resume or required images are lost.

Opening `watch()` today **does not automatically export the existing collection** into the warehouse.

### 21.5. Event Sourcing and Auditing Differ from CDC

Change streams are not an infinite event store:

- The oplog has finite retention;
- Images have finite retention;
- Technical updates are not necessarily business events;
- Actor/reason metadata may be absent;
- Schema changes complicate delta replay.

If you need event sourcing, design durable, versioned domain events with explicit contracts—potentially bridged by change streams, but never treating the oplog as a permanent ledger.

## 22. Planning Retention by Rate and Consumer Lag

Suppose:

```text
Producer rate:       10,000 events/sec
Consumer rate:        8,000 events/sec
Backlog growth:       2,000 events/sec
```

After one hour:

\[
2.000 \times 3.600 = 7.200.000\ \text{events}
\]

Even without a crash, the consumer falls further behind. If events or images expire before processing, CDC loses completeness.

### 22.1. Tracking Backlog Age

A backlog of 1 million events corresponds to:

- 10 seconds at 100,000 events/sec;
- 1,000 seconds at 1,000 events/sec.

Therefore, track metrics:

- Lag from event timestamp/`clusterTime` to processing completion;
- Age of the oldest unprocessed event;
- Oplog window;
- Pre-/post-image TTL;
- Retry rate;
- Required-image failures;
- Resume failures;
- Consumer throughput;
- Storage growth over time.

### 22.2. Retention Needs Safety Margin

If your SLA allows 24 hours of downtime, an exact 24-hour retention window is insufficient due to:

- Time to detect the outage;
- Time to fix and redeploy;
- Backlog replay catch-up time;
- Peak update bursts;
- Disk constraints as image count grows.

No single TTL fits every workload. Size retention from real telemetry and acceptable cost bounds.

## 23. Decision Matrix

| Requirement | `updateDescription` Only | `updateLookup` | Event-Time Pre/Post |
|---|---|---|---|
| Invalidate cache by `_id` | **Sufficient in most cases** | Unnecessary | Unnecessary |
| Know which fields changed | **Good** | Does not replace delta | Does not replace delta |
| Fetch latest state for indexing | Possible if state is maintained | **Good fit** | Good fit if ordering handled |
| Audit exact before/after | Missing before | **Insufficient** | **Preferred** |
| Know deleted document content | `documentKey` only | Cannot recover deleted doc | **Pre-image helps** |
| Minimize network payload | **Good** | Sends full document | Sends full images |
| Avoid extra image storage | **Good** | No capture needed | Capture required |
| Extended consumer downtime | Depends on oplog | Depends on oplog | Depends on oplog **and** image retention |
| PII exposure risk | Lower | Includes current full doc | Includes modified/deleted old values |

**Do not force one mode onto all consumers.** A single collection may feed multiple downstream pipelines with different contracts; base server-side image capture on use cases that genuinely require it.

## 24. Common Mistakes

| Misconception | Impact | Remedy |
|---|---|---|
| `updateLookup` is an exact post-image | Inaccurate audit on rapid updates | Use pre-/post-images |
| `whenAvailable` automatically enables capture | Receives null because capture is off | Enable `changeStreamPreAndPostImages` on collection |
| Enabling capture covers past events | Missing historical images | Enable before changes occur or use another audit source |
| `required` keeps images forever | Stream errors when images expire | Plan retention and recovery |
| Inserts have pre-images | Consumer logic crashes | No before-document exists on insert |
| Deletes have full post-documents | Consumer tries looking up deleted doc | Use pre-images |
| Null `fullDocument` on update means delete | Misclassified event types | Always inspect `operationType` |
| Default updates include full documents | Missing fields during sync | Choose lookup or image mode |
| Oplog window equals image TTL | Resumability and image expiry diverge | Monitor both independently |
| TTL `"off"` means infinite retention | Images disappear when oplog evicts events | Never treat the image store as an audit archive |
| Resume token is a business version | Broken ordering | Tokens are opaque; keep separate business versions |
| Saving token before side effect | Skipped events after crash | Save after commit; process idempotently |
| Change streams give exactly-once external effects | Duplicates on retry | Use idempotency or coordinated transactions |
| Arbitrarily patching deltas onto stale state | Corrupted nested/array state | Use exact post-images or proper state/replay |
| Handling only `update` | Drops insert/replace/delete | Handle each `operationType` explicitly |
| Logging full pre-images | Leaks deleted/modified PII | Redact, restrict permissions, enforce retention |
| Image capture is free | Storage and write amplification | Benchmark and capacity-plan |
| One document's images are a cluster-wide txn snapshot | Broken multi-doc invariants | Use transactions/outbox/reconciliation |
| `$project` stripping event `_id` | Breaks stream/resumption | Preserve resume token |

## 25. Practice Exercises

### Exercise 1 — Distinguishing Exact Post-Image and Lookup

Document:

```javascript
{ _id: 1, status: "NEW", version: 1 }
```

Then:

```text
Update A: NEW → PAID, version 2
Update B: PAID → SHIPPED, version 3
```

1. What does A's `updateDescription` say?
2. Which version can A's `updateLookup` return?
3. What state must A's exact post-image have?
4. What must B's pre-image be?
5. Why is lookup unsuitable for per-change auditing?

### Exercise 2 — Enabling Images and Testing Insert/Update/Replace/Delete

On a MongoDB 6.0+ replica set:

1. Create a collection with `changeStreamPreAndPostImages.enabled: true`.
2. Open a stream with `fullDocument` and `fullDocumentBeforeChange` set to `"whenAvailable"`.
3. Insert a document.
4. Update two fields.
5. Replace the document.
6. Delete the document.
7. Record before/after payloads and `operationType` for each event.

### Exercise 3 — Non-Retroactive Capture

Suppose update T1 happens before capture is enabled at T2, followed by update T3 after enabling.

1. Can you obtain T1's pre-image from the feature enabled at T2?
2. Is `updateLookup` at T3 the post-image of T1?
3. If auditing T1 is mandatory, what other historical source is needed?

### Exercise 4 — `required` vs. `whenAvailable`

A delete event needs a pre-image, but the image TTL has expired.

1. How does `whenAvailable` let the consumer behave?
2. How does `required` differ?
3. Is it valid to reconstruct a missing pre-image from current live state?
4. If the oplog event is also gone, can you resume with the old token?

### Exercise 5 — Redis Cache Invalidation

A service only needs to delete cache key `order:{_id}` when an order changes.

1. Is `updateLookup` necessary?
2. Are pre-/post-images necessary?
3. If the cache key depended on the old `customerId`, how does the choice change?
4. How do you avoid logging PII?

### Exercise 6 — Search Index Race

A consumer concurrently processes events for version 2 and version 3. Version 3 writes to the index before version 2.

1. What happens if version 2 writes last?
2. Use versioning/idempotency/key-partitioning to prevent the bug.
3. If an update's lookup returns null because the document was deleted, how should you handle it?
4. How does a delete event differ from an update event?

### Exercise 7 — Checkpointing and Replay

Consumer:

```text
Receive event E
Save token(E)
Process E
```

If it crashes after step 2:

1. Will E be processed after resuming?
2. Does reversing process/save-token order completely eliminate duplicates?
3. Why is idempotency required?
4. When can checkpoint and side effect commit together?

### Exercise 8 — Oplog and Image TTL

Suppose:

```text
Oplog window:       4 hours
Image TTL:         12 hours
Consumer downtime:  6 hours
```

1. Is resuming after six hours guaranteed?
2. Why doesn't a longer image TTL rescue an evicted oplog event?
3. If oplog is 24 hours and image TTL is two hours, how is `required` affected?
4. Design an alert for backlog age.

### Exercise 9 — Image Storage Cost

A collection receives 5,000 updates/sec, average document size 50 KB, keeping images for 12 hours.

1. Estimate raw data volume under these illustrative assumptions.
2. Explain how overhead/compression/replication can shift actual storage usage.
3. Compare with `updateLookup` when 5 consumers exist.
4. Which metrics should be measured before enabling in production?

### Exercise 10 — Auditing and Privacy

A user deletes their home address, yet the event's pre-image retains the old address.

1. Who should be authorized to view it?
2. Can image retention and audit log retention differ?
3. Why must raw events not be logged?
4. How do you restrict downstream consumers from retaining images?

### Exercise 11 — Array Updates

Document:

```javascript
{
  _id: 5,
  items: [
    { sku: "A", qty: 1 },
    { sku: "B", qty: 2 }
  ]
}
```

1. Update `items.0.qty` and inspect `updateDescription`.
2. Modify array structure and inspect delta representation.
3. Why can applying deltas onto a stale snapshot yield wrong results?
4. When is an exact post-image more useful?

### Exercise 12 — Multi-Document Transaction

A transaction updates `orders` and `payments`.

1. Does the order's pre-/post-image include the payment?
2. How can consumers preserve invariants across both collections?
3. Are outbox/reconciliation patterns needed?
4. Why can't one document's image pair serve as a full transaction snapshot?

## 26. Production Checklist

Before promoting a change stream consumer to production, verify:

1. Server/FCV/driver support the required image modes.
2. Deployment is a supported replica set or sharded cluster.
3. Collection capture was enabled **before** changes requiring images occurred.
4. Event contract clearly distinguishes current lookup from exact post-images.
5. All types (`insert`/`update`/`replace`/`delete`/`invalidate`) are handled properly.
6. Image retention and oplog window include sufficient safety margin.
7. `required` vs. `whenAvailable` reflects missing-image tolerance.
8. Checkpoints advance only after side effects commit.
9. Idempotency handles event replays.
10. Ordering/versioning prevents projection regressions.
11. PII, privacy, and access controls are designed.
12. Combined event sizes stay within BSON limits.
13. Metrics track event lag, backlog, missing images, and resume failures.
14. Snapshot bootstrap strategy exists for pre-existing data.
15. Full resync plan exists when resuming fails.
16. Rapid updates, delete-after-update, crash/restart, and failovers are tested in staging.
17. The image store is never treated as an infinite audit archive.

## 27. MongoDB Reference Documentation

- [Change Streams](https://www.mongodb.com/docs/manual/changeStreams/)
- [Document Pre- and Post-Images](https://www.mongodb.com/docs/manual/changeStreams/#change-streams-with-document-pre--and-post-images)
- [Change Events](https://www.mongodb.com/docs/manual/reference/change-events/)
- [Change Stream Update Event](https://www.mongodb.com/docs/manual/reference/change-events/update/)
- [Change Stream Replace Event](https://www.mongodb.com/docs/manual/reference/change-events/replace/)
- [Change Stream Delete Event](https://www.mongodb.com/docs/manual/reference/change-events/delete/)
- [Collection Watch](https://www.mongodb.com/docs/manual/reference/method/db.collection.watch/)
- [Resume a Change Stream](https://www.mongodb.com/docs/manual/changeStreams/#resume-a-change-stream)
- [collMod Command](https://www.mongodb.com/docs/manual/reference/command/collMod/)
- [setClusterParameter Command](https://www.mongodb.com/docs/manual/reference/command/setClusterParameter/)
- [Java Driver Change Streams](https://www.mongodb.com/docs/drivers/java/sync/current/usage-examples/watch/)

## Conclusion

**`updateDescription`**, **`fullDocument: "updateLookup"`**, and **pre-/post-images** solve distinct problems.

- **`updateDescription`** provides the delta of an update event, ideal when you only need modified fields or cache invalidation.
- **`updateLookup`** retrieves the **current majority-committed state at lookup time**, useful for latest-state projections, yet **never guaranteed to be the exact state right after the event being processed**.
- **Pre-images and post-images** deliver the exact **before and after states for that specific event**, vital for accurate auditing and historical CDC. They require enabling `changeStreamPreAndPostImages.enabled` on the collection beforehand, and requesting `fullDocumentBeforeChange`/`fullDocument` with `"whenAvailable"` or `"required"`.

Equally important is image lifecycle: pre-/post-images and the oplog have finite retention, so prolonged consumer pauses can lose resumability or required images. Production consumers must manage checkpoints, opaque resume tokens, idempotency, ordering, privacy, event size limits, and full resync workflows.

**When you need the latest state, lookup may suffice. When you need exact before/after history for every change, never substitute current lookup for exact event-time images.**
