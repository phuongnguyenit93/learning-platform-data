# Optimistic Locking with a Version Field and Conflict Handling in MongoDB

## 1. The problem: two people editing the same document

A product catalog management application stores a MongoDB document as follows:

```javascript
{
  _id: ObjectId("66a000000000000000000001"),
  sku: "BOOK-001",
  name: "MongoDB Fundamentals",
  priceCents: 150000,
  description: "Introductory book",
  version: 7,
  updatedAt: ISODate("2026-11-14T02:00:00Z")
}
```

Two staff members open the edit screen at the same time:

1. **Person A** reads version `7`, changes `priceCents` to `160000`.
2. **Person B** also reads version `7`, edits `description`.
3. A saves successfully.
4. B submits the entire copy of the document read initially, in which `priceCents` is still `150000`.

If the application updates without checking whether the record has changed, B's write can **overwrite A's new price with old data**. This is the *lost update* phenomenon.

MongoDB guarantees that a write operation on **a single document** is atomic. However, this **does not automatically protect read → process in app → write back logic** when multiple requests use stale snapshots. We need a convention to check whether the document has changed since it was read.

**Optimistic concurrency control (OCC)** — often called *optimistic locking* — solves this by storing a `version` field and accepting an update only if the `version` in the database still equals the version the client read.

After this lesson, you will be able to:

- Distinguish **single-document update atomicity** from **conflicts between two read–write flows**.
- Design a `version` field and **compare-and-set** (*CAS*) operations.
- Write `updateOne()` with a filter containing `_id` and `version`, using `$inc` to increment the version.
- Use `matchedCount` or `findOneAndUpdate()` results to determine whether a write was accepted.
- Distinguish missing documents, stale versions, write concern errors, and network errors with unknown outcomes.
- Choose policies among **409 Conflict**, **412 Precondition Failed**, re-read/merge, or bounded retries.
- Integrate OCC with APIs, the Node.js driver, validation, multi-document transactions, and idempotency.

## 2. At what level is MongoDB atomic?

### 2.1. A single update on a single document is atomic

For example:

```javascript
db.products.updateOne(
  { _id: productId },
  {
    $set: {
      priceCents: 160000,
      updatedAt: new Date()
    },
    $inc: { version: 1 }
  }
);
```

MongoDB applies these changes to the same document as **one atomic operation**. Readers do not see an intermediate state in which `priceCents` changed while `version` has not yet incremented due to only half of the command executing.

This helps build CAS, but is insufficient if the filter only contains `_id`. Two requests using stale data can still sequentially update the same document.

### 2.2. Why can `findOne()` followed by `updateOne()` lose updates?

Consider this code pattern:

```javascript
const product = await products.findOne({ _id: productId });

// User edits after the client receives the data...
const newPrice = computePriceFromOldData(product);

await products.updateOne(
  { _id: productId },
  { $set: { priceCents: newPrice } }
);
```

While computing or waiting on the user, the document may be modified by another request. The filter `{_id: productId}` still matches the document, so the update has no idea the previously read value is stale.

### 2.3. Atomic does not mean serializing the entire business workflow

| Property | Guaranteed by MongoDB? |
| --- | --- |
| An `updateOne` modifying multiple fields in the same document is atomic | Yes |
| Two conditional write requests on the same document have their update conditions checked at write time | Yes, within MongoDB write semantics |
| An independent `findOne` and `updateOne` are automatically treated as one transaction | No |
| A later write request always detects that the record it read earlier was modified | No, unless an appropriate condition/check is used |
| Operations across multiple documents are automatically atomic merely because they are in the same batch | No |
| The version field increments automatically whenever any writer modifies the document | No; the application must enforce a consistent version-increment convention |

**Key point:** MongoDB does not create OCC automatically just because a document has a `version` field. Every relevant write path must **follow the protocol**: check expected version and increment version on protected updates.

## 3. Compare-and-set mechanism with a version field

### 3.1. Read version then update conditionally

Suppose the client read:

```javascript
{
  _id: productId,
  name: "MongoDB Fundamentals",
  priceCents: 150000,
  version: 7
}
```

The update request passes `expectedVersion = 7`. The server executes:

```javascript
const expectedVersion = 7;

const result = db.products.updateOne(
  {
    _id: productId,
    version: expectedVersion
  },
  {
    $set: {
      priceCents: 160000,
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);

printjson(result);
```

Condition:

```text
UPDATE succeeds only if:
    _id == productId
    AND
    version == expectedVersion
```

In essence, the server performs a **conditional atomic update**: evaluating the predicate at the moment the write is applied and incrementing version alongside the data in a single operation.

If the document is still at `version = 7`, the update is applied and version becomes `8`. If the document has already advanced to `8` due to another request, the filter does not match and **no data is modified by this command**.

### 3.2. Timeline of two competing requests

```text
Time              Request A                     Request B
   |
   |          READ version=7                READ version=7
   |                 |                              |
   |                 v                              v
   |          edit priceCents               edit description
   |                 |                              |
   |                 v                              |
   |    UPDATE WHERE version=7                     |
   |    SET priceCents=160000                       |
   |    INC version +1                              |
   |                 |                              |
   |             matched=1                          |
   |             version=8                          |
   |                                                v
   |                                    UPDATE WHERE version=7
   |                                    SET description="..."
   |                                    INC version +1
   |                                                |
   v                                            matched=0

     A succeeds; B detects that the data has changed.
```

The application does not need a system-wide mutex per product; MongoDB checks and applies the update conditionally on the document.

### 3.3. How to read the result

`updateOne()` typically returns:

```javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1,
  upsertedCount: 0,
  upsertedId: null
}
```

For an **acknowledged** CAS:

- `matchedCount: 1`: one document matched both ID and version; the update operation was accepted.
- `matchedCount: 0`: no document matched **the entire filter**.
- `modifiedCount` can be `0` if an update did not actually change any value; however, when always `$inc`ing version, a successful CAS normally modifies the document.
- `upsertedCount` must be `0` in standard OCC updates, because `upsert: true` should not be enabled.

**Never infer solely from `matchedCount: 0` that the document was edited by someone else.** The document may have been deleted, the ID wrong, a different tenant, wrong version type, or access disallowed by the filter.

### 3.4. Why is `$inc` on version needed?

If you only compare version in the filter without **incrementing version on success**:

```javascript
// Protocol bug for OCC:
db.products.updateOne(
  { _id: productId, version: 7 },
  { $set: { priceCents: 160000 } }
);
```

After the command, the document remains at version 7, so request B with expectedVersion 7 can still match and overwrite. The version check becomes meaningless without a convention to advance the version.

Rule: **every write protected by OCC must advance version in the same atomic write**. Using `$inc: {version:1}` is simpler than computing `version: oldVersion + 1` in the application, because the database handles incrementing within the update operation itself.

## 4. `mongosh` hands-on: simulating two concurrent editors

### 4.1. Preparing a dedicated database

Connect to MongoDB via `mongosh` on a practice environment you are authorized to use, for example:

```bash
mongosh "mongodb://127.0.0.1:27017/"
```

In the shell:

```javascript
const lab = db.getSiblingDB("mongo_occ_row216_lab");
const products = lab.getCollection("products_demo");
const runId = "row216-" + new ObjectId().toHexString();
const productId = new ObjectId();

products.insertOne({
  _id: productId,
  runId,
  sku: "BOOK-216-01",
  name: "MongoDB Fundamentals",
  priceCents: NumberLong("150000"),
  description: "Introductory book",
  status: "ACTIVE",
  version: NumberLong("1"),
  createdAt: new Date(),
  updatedAt: new Date()
});

print("database=" + lab.getName());
print("runId=" + runId);
printjson(products.findOne({ _id: productId, runId }));
```

`runId` marks this practice run, making it easy to clean up the exact document. `version` is stored as BSON Int64 via `NumberLong` to illustrate a stable numeric type choice. In real applications, keep BSON numeric types consistent across initialization, comparison, and increment; JavaScript/drivers also have precision limits for large integers, so never blindly coerce very large versions to JS `Number`.

### 4.2. Two clients reading the same snapshot

Simulate A and B receiving the same data:

```javascript
const snapshotA = products.findOne({ _id: productId, runId });
const snapshotB = products.findOne({ _id: productId, runId });

print("A.version=" + snapshotA.version);
print("B.version=" + snapshotB.version);
```

Both will see `version = 1` when no intervening update has occurred.

### 4.3. A updates successfully

```javascript
const resultA = products.updateOne(
  {
    _id: productId,
    runId,
    version: snapshotA.version
  },
  {
    $set: {
      priceCents: NumberLong("160000"),
      updatedAt: new Date()
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);

printjson(resultA);
printjson(products.findOne(
  { _id: productId, runId },
  { _id: 0, sku: 1, priceCents: 1, description: 1, version: 1 }
));
```

After this step, version is expected to be `2` and price `160000`. `resultA.matchedCount` is expected to be `1`.

### 4.4. B sends a change based on the stale version

```javascript
const resultB = products.updateOne(
  {
    _id: productId,
    runId,
    version: snapshotB.version
  },
  {
    $set: {
      description: "MongoDB hands-on guide",
      updatedAt: new Date()
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);

printjson(resultB);
printjson(products.findOne(
  { _id: productId, runId },
  { _id: 0, priceCents: 1, description: 1, version: 1 }
));
```

Command B is expected to have `matchedCount: 0` because the stored version is now `2` while `snapshotB.version` is still `1`. Price and description are not altered by B.

When reading the output, note that MongoDB did not "reject B because B arrived second." MongoDB declined to apply the update because **B's filter no longer matched**. Had B read version 2 before sending, the outcome would be different.

### 4.5. B re-reads and makes a decision

If business rules allow updating `description` alone without affecting `priceCents`, B can reload the document and issue a new request:

```javascript
const latest = products.findOne({ _id: productId, runId });

const retryB = products.updateOne(
  {
    _id: productId,
    runId,
    version: latest.version
  },
  {
    $set: {
      description: "MongoDB hands-on guide",
      updatedAt: new Date()
    },
    $inc: {
      version: NumberLong("1")
    }
  }
);

printjson(retryB);
printjson(products.findOne({
  _id: productId,
  runId
}));
```

The new attempt can succeed, bringing version to `3` while keeping A's price `160000`. Yet if another writer updates between `findOne` and `updateOne`, the retry can still get `matchedCount:0`; **re-reading does not create an exclusive lock**.

Automatically reapplying B's change is only appropriate here because we **established** that modifying `description` is independent of price. For orders/payments or tightly coupled fields, never automatically retry by overwriting the newer version without detailed conflict checks.

## 5. Handling `matchedCount: 0`: missing document or version conflict?

### 5.1. Three important possibilities

When the operation:

```javascript
products.updateOne(
  { _id: productId, runId, version: expectedVersion },
  { $set: { name: "New name" }, $inc: { version: NumberLong("1") } }
);
```

returns `matchedCount:0`, it may be that:

1. The document was **deleted** or never existed.
2. The document exists, but has a **different version**.
3. The filter also includes tenant, status, or another condition that failed (e.g., document changed state, different access scope, or mismatched version type).

The application can look up the record again within **ID and authorized scope**:

```javascript
const currentValue = products.findOne({
  _id: productId,
  runId
});

if (!currentValue) {
  print("NOT_FOUND_OR_NOT_VISIBLE");
} else {
  print("VERSION_OR_PRECONDITION_CONFLICT");
  print("Current version: " + currentValue.version);
}
```

However, this second read is also subject to concurrency. It is a **snapshot at reconciliation time**, not proof that the document definitely existed or did not exist at the exact instant the update failed.

### 5.2. Do not leak existence of another tenant's resource

In a multi-tenant application, the update filter might be:

```javascript
{
  _id: productId,
  tenantId: authenticatedTenantId,
  version: expectedVersion
}
```

If it returns `0`, the server should re-read only with the **authenticated tenant** condition. Do not query solely by `_id` and respond "the document exists, but you lack permission" if your security policy requires hiding resource existence.

OCC and authorization solve two distinct problems; the filter must enforce both.

### 5.3. Error mapping at the API layer

A REST API may define:

| Situation | Typical response |
| --- | --- |
| CAS succeeds | `200 OK` with new document or `204 No Content` |
| Document does not exist in accessible scope | `404 Not Found` |
| Stale version in APIs using a dedicated version field | `409 Conflict` |
| Conditional header `If-Match` fails | `412 Precondition Failed` |
| Client must provide precondition but omitted it | `428 Precondition Required` if contract requires |
| Invalid input payload | `400 Bad Request` or `422 Unprocessable Content` per API convention |
| Transient write error | Appropriate system error response; safe retry per policy |

HTTP status is only the **interface**; correctness rests on the conditional update operation in MongoDB. An API should never report success before obtaining an appropriate level of write acknowledgment.

## 6. Designing the version field

### 6.1. Initialize version on insert

New documents should have an explicit initial version:

```javascript
db.products.insertOne({
  sku: "BOOK-002",
  name: "Advanced MongoDB",
  priceCents: NumberLong("200000"),
  version: NumberLong("1"),
  createdAt: new Date(),
  updatedAt: new Date()
});
```

You can initialize at `0` or `1`; what matters is **system-wide consistency**. If legacy data lacks `version`, establish a migration/compatibility policy before requiring all writers to use OCC.

### 6.2. Data type and increment rules

Version is typically a **monotonically increasing integer**. Common choices:

- BSON `Int32` if the value range covers the document lifecycle.
- BSON `Int64` if more headroom is desired and the driver handles an appropriate `Long` type.
- Some systems use opaque tokens or UUIDs instead of numbers, in which case update commands and token generation must be designed differently.

When using `Long` in the Node.js driver, avoid converting very large 64-bit integers to JS `Number` and comparing inaccurately. Do not use client-generated timestamps as a "version" if your goal is catching every write precisely: two writers can generate the same timestamp, clocks can skew, and resolution may be insufficient.

### 6.3. Every writer must follow the protocol

Suppose one service uses CAS and increments version, while another worker still writes:

```javascript
// Writer breaks the OCC protocol if it modifies business data
// without checking/incrementing version.
db.products.updateOne(
  { _id: productId },
  { $set: { priceCents: 99999 } }
);
```

The document changes without version incrementing. A client holding an old expectedVersion can still update successfully and overwrite the new price. Hence OCC is only trustworthy when:

- All document-editing APIs filter by version and increment version.
- Workers, imports, and maintenance scripts follow the same policy or operate via controlled change paths.
- Migrations modifying business data bump version when required.
- Schema validation, observability, and deployment checks prevent missing or mistyped versions per policy.

### 6.4. Is a separate index on version needed?

If CAS filters by:

```javascript
{ _id: productId, version: expectedVersion }
```

MongoDB normally uses the default index on `_id` to find at most one document and then checks version. **You do not necessarily need an index `{version:1}`** solely to perform CAS by `_id`.

In multi-tenant systems, queries may also include `tenantId`/shard key for routing; exact indexes depend on topology and filters. If CAS keys on `{tenantId, sku}` instead of `_id`, create a unique index on the **stable business key**. `version` does not replace a unique index to stop duplicate document inserts.

### 6.5. Never let clients choose the new version

A request can send:

```javascript
{
  expectedVersion: 7,
  patch: {
    priceCents: 160000
  }
}
```

The server must validate `expectedVersion`, never allowing the client to send `version: 9999` to write into the database. Separate `expectedVersion` (the predicate) from `nextVersion` (atomically incremented by the server).

Avoid letting update payloads contain `version`, `_id`, or other system fields without whitelisting; using `$set` directly from an unvalidated body lets clients break the OCC protocol or alter forbidden fields.

## 7. Node.js driver: writing a conflict-checked update function

### 7.1. Conditional update function

Example using the MongoDB Node.js driver. Assumptions:

- `products` is a collection from a connected `MongoClient`.
- `productId` is a valid `ObjectId` and the document already has a `version` field.
- `tenantId` comes from the authenticated context.
- `expectedVersion` is converted to the proper BSON type per application schema.
- `patch` contains only validated fields.

```javascript
import { Long } from "mongodb";

async function updateProduct(products, {
  productId,
  tenantId,
  expectedVersion,
  patch
}) {
  // Assumes expectedVersion was already validated as a safe integer
  // before converting to BSON Long.
  const expected = Long.fromNumber(expectedVersion);

  const filter = {
    _id: productId,
    tenantId,
    version: expected
  };

  const update = {
    $set: {
      ...patch,
      updatedAt: new Date()
    },
    $inc: {
      version: Long.ONE
    }
  };

  const result = await products.updateOne(
    filter,
    update,
    { upsert: false }
  );

  if (result.matchedCount === 1) {
    return {
      outcome: "UPDATED",
      previousVersion: expectedVersion
    };
  }

  // Read only within the authenticated tenant.
  const current = await products.findOne(
    { _id: productId, tenantId },
    { projection: { version: 1, updatedAt: 1 } }
  );

  if (!current) {
    return { outcome: "NOT_FOUND" };
  }

  return {
    outcome: "CONFLICT",
    currentVersion: current.version
  };
}
```

This is a **CAS demonstration function**, not a complete production API. Callers must validate allowed fields, value types, authorization, write concern, resource errors, and how `Long` serializes to JSON. `Long.fromNumber()` should only be used when the input is within **JavaScript's safe integer range**; for very large versions, pass strings and parse accurately via the driver.

### 7.2. Do not pass an arbitrary request body as `$set`

A common bug:

```javascript
// Unsafe:
await products.updateOne(
  { _id: productId, version: expected },
  {
    $set: request.body,
    $inc: { version: Long.ONE }
  }
);
```

A client could send `version`, `_id`, or disallowed field paths. Even if the server rejects an operator conflict on version, it remains a contract bug and can corrupt other fields.

Instead, the server constructs the update from an explicit allowlist of attributes:

```javascript
const patch = {};

if (typeof body.name === "string") {
  patch.name = body.name;
}

if (Number.isSafeInteger(body.priceCents) && body.priceCents >= 0) {
  patch.priceCents = Long.fromNumber(body.priceCents);
}

// Required fields, edit permissions, and bounds are validated separately.
```

In real systems, invalid input should return a clear error rather than **silently ignoring** invalid fields. The snippet above only illustrates building an update object from controlled fields.

### 7.3. Returning the updated document with `findOneAndUpdate`

`findOneAndUpdate` combines conditional find and update in one operation and can return the post-update document:

```javascript
const updated = await products.findOneAndUpdate(
  {
    _id: productId,
    tenantId,
    version: expected
  },
  {
    $set: { name: "New name", updatedAt: new Date() },
    $inc: { version: Long.ONE }
  },
  {
    returnDocument: "after",
    upsert: false,
    includeResultMetadata: false
  }
);

if (updated === null) {
  // No match: not found or OCC conflict.
}
```

Across different Node.js driver versions, `findOneAndUpdate` has changed in return values and metadata options. Check the API docs of **the driver version you use** rather than assuming it always returns a wrapper object with `value`.

When no document matches, `null` is the expected result in direct-document mode. Just like `matchedCount:0`, re-read (if desired) to distinguish not found from conflict.

### 7.4. Choosing `updateOne` or `findOneAndUpdate`?

| Requirement | Usually appropriate choice |
| --- | --- |
| Only need to know if CAS succeeded or failed | `updateOne` + `matchedCount` |
| Need the post-update document from the same operation | `findOneAndUpdate` + `returnDocument:"after"` |
| Need to read the latest copy after updateOne | You can read afterward, though readers may see subsequent concurrent changes |
| Want to update only if old state satisfies a condition | Put the state predicate in the filter, **no upsert** |
| Want to update multiple documents consistently | Consider transactions; single-document OCC is not enough |

Do not judge solely by round-trip count. `findOneAndUpdate` has different performance characteristics and behaviors from `updateOne` depending on topology/driver; choose based on result needs and real workload.

## 8. Conflict resolution: from detection to business decision

### 8.1. Do not retry blindly

An incorrect approach:

```javascript
// WRONG idea when using an old copy:
while (!updated) {
  await products.updateOne(
    { _id: productId },
    { $set: staleDocument }
  );
}
```

Dropping version from the filter just to "force the update through" disables OCC. Retrying with the new version while **keeping the entire stale snapshot** can still overwrite changes made by others.

### 8.2. Three common resolution policies

| Policy | How it works | When appropriate |
| --- | --- | --- |
| **Report conflict to the user** | Return current version and ask user to reload/compare | Profile edit forms, critical content, changes hard to auto-merge |
| **Re-read and reapply a reconcilable change** | Read latest document, verify invariants, build new patch, CAS on new version | Independent, well-defined changes, such as updating a field unrelated to others |
| **Rule-based merge** | Compare base/client/current, detect conflicting fields, prompt user or apply rules | Multi-field documents, collaborative workflows, or editors |

A "last write wins" policy may exist in some systems, but it is a **business decision to discard certain conflicts**, not a safe default when using OCC.

### 8.3. Distinguishing independent updates from dependent updates

Suppose:

- A changes `priceCents` from `150000` to `160000`.
- B changes `description`.

If the UI sends **only the patch of changed fields**, and business rules allow the two fields to be independent, B can fetch the new version and apply the description patch without overwriting the price.

Now consider:

- A changes `discountPercent` from `10` to `20`.
- B computes `finalPriceCents` from the old price and discount, then tries to write the final price.

Here B's update **depends on the stale snapshot**. You cannot safely fetch the new version and keep the old computed result. You must **recompute from the latest document** and verify price invariants.

### 8.4. Three-way merge

When a user edits multiple fields, you can compare three versions:

1. **Base**: the document the client originally read.
2. **Client**: the version the user wants to save.
3. **Current**: the latest document on the server after CAS failed.

Idea:

```text
base.name        = "Old Book"
client.name      = "New Book"
current.name     = "Old Book"

=> Client edited name, server did not edit name:
   Can apply client.name.

base.price       = 150000
client.price     = 155000
current.price    = 160000

=> Both client and server edited price:
   CONFLICT, requires decision.
```

A merge algorithm can automatically combine only **non-overlapping** fields. When relationships exist between fields, overlap checking alone is insufficient: changes to quantities, prices, limits, or states require applying domain-specific rules.

### 8.5. Bounded retries with backoff

If policy allows automatic retries:

- Re-fetch the document by exact ID and tenant on each attempt.
- **Recompute** the change from the latest state; never resubmit the raw old copy.
- Use the new expectedVersion in the filter.
- Cap attempts, e.g. a few tries, based on load and SLA.
- Add backoff and jitter when multiple writers contend on one document.
- If conflicts persist, return a conflict or escalate to another flow instead of an infinite loop.

Retries can alter business ordering; take care when updating time-sensitive fields or request-priority rules.

## 9. Conditional retry pattern in Node.js

Suppose the business action is **setting a description** to a new value, and the product permits reapplying that change when another field changed. Illustrative code:

```javascript
import { Long } from "mongodb";

async function setDescriptionWithLimitedRetry(
  products,
  { productId, tenantId, newDescription },
  maxAttempts = 3
) {
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const current = await products.findOne({
      _id: productId,
      tenantId
    });

    if (!current) {
      return { outcome: "NOT_FOUND" };
    }

    // Policy check here: only allow updates while ACTIVE.
    if (current.status !== "ACTIVE") {
      return { outcome: "INVALID_STATE" };
    }

    const result = await products.updateOne(
      {
        _id: productId,
        tenantId,
        version: current.version,
        status: "ACTIVE"
      },
      {
        $set: {
          description: newDescription,
          updatedAt: new Date()
        },
        $inc: { version: Long.ONE }
      },
      { upsert: false }
    );

    if (result.matchedCount === 1) {
      return { outcome: "UPDATED", attempt };
    }

    // Changed between read and write; perform bounded retry.
    // In production, add appropriate backoff/jitter.
  }

  return { outcome: "TOO_MUCH_CONTENTION" };
}
```

**Limitation of this example:** the function intentionally defines a policy of "description may be set again on an ACTIVE document"—which is inappropriate if two people are simultaneously editing `description` and need overwrite detection. In a collaborative editor, instead of auto-retrying, prompt the user to resolve a conflict whenever **the exact field they edited** changed.

The snippet above handles normal CAS outcomes; it **does not automatically retry arbitrary network/write concern errors**. For uncertain write outcomes, idempotency and reconciliation are needed as covered below.

## 10. Version-based OCC and HTTP ETag/If-Match

### 10.1. Passing version from API to database

An API can return:

```http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "product-7"

{
  "id": "...",
  "name": "MongoDB Fundamentals",
  "priceCents": 150000,
  "version": 7
}
```

Client edits data and sends:

```http
PATCH /products/123 HTTP/1.1
Content-Type: application/json
If-Match: "product-7"

{
  "priceCents": 160000
}
```

The server parses the precondition, matches the version to the document, and runs CAS:

```javascript
db.products.updateOne(
  {
    _id: productId,
    tenantId: authenticatedTenantId,
    version: NumberLong("7")
  },
  {
    $set: { priceCents: NumberLong("160000") },
    $inc: { version: NumberLong("1") }
  }
);
```

If unmatched, the API can return `412 Precondition Failed` per `If-Match` semantics. If the API uses an `expectedVersion` field in the JSON body instead of a header, `409 Conflict` is a common choice. What matters is a consistent contract so clients know when to reload.

### 10.2. ETag is not always just a version string

ETag in HTTP is a **representation validator**. If responses vary by language, visibility permissions, or serialization format, a semantically valid HTTP ETag must be designed for that representation. Using `"product-7"` in the example simply illustrates representing a validator in an API with a clear contract.

Weak ETags (prefixed with `W/`) are unsuitable for `If-Match` strong comparison. When implementing HTTP conditional requests, read and apply the protocol semantics properly rather than handling an arbitrary string.

### 10.3. User interface on conflict

Instead of a generic "Save failed" message, an application can:

1. Clearly explain that the record changed on the server.
2. Fetch the newer version and highlight differing fields.
3. Let the user choose to keep their edits, accept the new data, or adjust.
4. Submit a new request with the current version once confirmed.

Never return the entire document containing sensitive fields in a conflict error if the user lacks permission to read those fields.

## 11. Combining version with business preconditions

### 11.1. Checking state before transitioning

Suppose an order can only transition from `PENDING` to `APPROVED`:

```javascript
const result = db.orders.updateOne(
  {
    _id: orderId,
    tenantId: authenticatedTenantId,
    version: expectedVersion,
    status: "PENDING"
  },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
```

The filter combines three categories of conditions:

- **Identity/authorization**: `_id` and `tenantId`.
- **OCC**: `version` equals the read version.
- **Business invariant**: `status` is still `PENDING`.

If `matchedCount: 0`, the cause may be a changed version, status no longer PENDING, or document out of scope. Re-read conditionally and classify per contract.

**Do not enable `upsert: true`** in this kind of state-transition update. When an existing document fails to match due to version/status, upsert may try to **create a new document**, causing duplicate key errors or unintended records if a matching unique constraint is missing.

### 11.2. Deducting stock: direct conditions can suffice

Suppose an operation only needs to deduct 2 items if stock is sufficient:

```javascript
db.inventory.updateOne(
  {
    _id: skuId,
    quantity: { $gte: 2 }
  },
  {
    $inc: {
      quantity: -2,
      version: 1
    }
  }
);
```

This is a **single-document atomic update**, so `quantity >= 2` is checked at write time and will not oversell available stock due to two writers reading the same old stock count.

In this case, **version is not required to guard the simple deduction**, because `$inc` and the quantity predicate directly express the invariant. Version can still be useful for other edits or state tracking.

Conversely, if the application reads old stock, computes `newQuantity = oldQuantity - 2` on the client, and calls `$set` on `quantity` without conditions, writers can overwrite each other's results.

### 11.3. OCC does not equal idempotency

If a stock-deduction request is resent after succeeding, the new version can cause the retry with the old expectedVersion **not to match**. This prevents reapplying a stale snapshot, yet does not reveal **which request** caused the change.

If after a timeout the client reads the new version and deducts 2 again, the quantity is still deducted twice. For critical operations that must execute **once per transaction ID**, store a stable operation ID/idempotency key and duplicate-prevention mechanism.

## 12. When network errors occur: did CAS succeed or not?

### 12.1. Timeouts can leave the outcome unknown

Flow:

```text
Client                          MongoDB
   |                               |
   |--- UPDATE version=7 --------> |
   |                               |  Write succeeds, version=8
   |        (response lost)        |
   | <---- timeout --------------- X
   |
   v
Client does not know whether the update committed at the desired level.
```

If the client immediately sends **a new operation** with `expectedVersion:7`, MongoDB will return `matchedCount:0`. You cannot conclude the first attempt failed; **the first attempt itself may have incremented version**.

This is the difference between:

- **Concurrency conflict**: knowing the current document no longer matches the expected version.
- **Unknown write outcome**: not knowing whether the initial write took effect or reached the required write concern.

### 12.2. Driver retryable writes do not replace idempotency

The MongoDB driver can retry certain writes via retryable writes under supported topologies and configurations. However, an API gateway, mobile client, or message queue can replay **a new business request**, not merely an internal retry of the same driver command.

A replayed action can be interpreted as a new operation if a stable `operationId` is missing. Never treat enabling retryable writes as a complete solution against duplicate business transactions.

### 12.3. Reconciling via operation ID

A design for critical operations:

```javascript
{
  _id: orderId,
  version: NumberLong("12"),
  status: "APPROVED",
  lastOperationId: "approve-order-op-82f1"
}
```

A simple approach is writing `lastOperationId` inside the same CAS update to identify the operation just performed. However, **a single lastOperationId field** cannot serve as a full log once subsequent operations overwrite it.

For long-term duplicate prevention, store an operation log or idempotency registry with a unique key and status, coordinated with the business update via a transaction or a properly designed atomic single-document model. When external side effects exist outside MongoDB, consider a transactional outbox or idempotent consumer.

### 12.4. Write concern and acknowledgment levels

The application can request a write concern such as `w: "majority"` to increase durability assurance. When receiving a `writeConcernError` or timeout, never assume "nothing was written": the operation may already have been applied on the primary without reaching the requested acknowledgment.

Re-reading the document lets you inspect current data, yet **observing the new version on a node does not prove the write achieved majority acknowledgment**. Handling policies must align with read concern, write concern, topology, and business requirements.

## 13. Optimistic locking and multi-document transactions

### 13.1. When single-document OCC is enough

Usually suitable for:

- Editing a customer profile in a single document.
- Updating user preferences.
- Editing a catalog item with clear field rules.
- Transitioning the status of one document.
- Managing a business aggregate cleanly modeled in one document.

When the entire invariant lies within **a single document**, an atomic conditional write is often the simplest and most efficient solution.

### 13.2. When a multi-document transaction is needed

For example, approving an order requires:

1. Updating order status.
2. Decrementing stock in another inventory document.
3. Writing an outbox event in another collection.

OCC on the order **does not make all three operations commit or roll back together**. Consider a multi-document transaction if the business requires atomic consistency.

With transactions, two writers can hit a **write conflict** at the database layer and the driver can retry per policy. This differs from an **OCC conflict** where the application deliberately puts version in the filter and receives `matchedCount:0`.

| Concern | Version-based OCC | Multi-document transaction |
| --- | --- | --- |
| Detecting stale updates on one document | Yes, if all writers follow the protocol | Can isolate changes, but semantics differ from CAS |
| Atomically updating multiple fields in one document | Already supported by MongoDB | No separate transaction needed just for multiple fields |
| Multiple documents succeeding or rolling back together | Not guaranteed automatically | Yes |
| Protecting unique business keys | No | No; still requires a unique index |
| Preventing client replay of side effects | Not guaranteed automatically | Not guaranteed automatically |
| Contention among concurrent writers | CAS returns no match | Can incur write conflicts / transient transaction errors |

Transactions have their own overhead and limits; do not use a multi-document transaction just to replace a CAS `updateOne` when there is no cross-document invariant.

### 13.3. Transaction retries are not arbitrary business-operation retries

When using `session.withTransaction(...)`, the driver may re-run the callback on certain transient errors. Do not place email sending, payment charging, or external notifications inside the callback unless they are idempotent: the callback can run multiple times even though the transaction ultimately commits only once.

Business operations need idempotency keys; external communication needs an outbox/inbox or dedicated protection.

## 14. OCC with subdocuments and arrays

### 14.1. Modifying one array element still changes the document's version

Suppose the document is:

```javascript
{
  _id: projectId,
  version: 5,
  tasks: [
    { taskId: "T1", title: "Design", done: false },
    { taskId: "T2", title: "Testing", done: false }
  ]
}
```

To mark T1 done:

```javascript
db.projects.updateOne(
  {
    _id: projectId,
    version: 5,
    "tasks.taskId": "T1"
  },
  {
    $set: { "tasks.$.done": true },
    $inc: { version: 1 }
  }
);
```

If version changed because another writer modified T2, the T1 operation conflicts even though **the two tasks are different**. This is a property of **document-level OCC**: version represents a revision of the entire document.

### 14.2. False conflicts on two independent fields

A document containing thousands of sub-elements may receive many parallel updates. If every operation increments the same `version`, conflict frequency can be high.

Consider:

- Allowing independent patches without whole-document version **only when** invariants permit.
- Splitting elements into separate documents to reduce contention.
- Managing version at the sub-element/sub-aggregate level with exact path and semantic update rules.
- Using atomic operators like `$inc`, `$addToSet`, or conditional updates instead of read-modify-write whenever possible.

Do not split documents solely to reduce conflicts if splitting breaks atomicity for invariants that must be maintained together. This is a trade-off between **atomicity granularity** and **contention frequency**.

### 14.3. Choosing the business aggregate boundary

If an order and all line items live in one document, the order's version can protect edits across all line items together. If line items live in a separate collection, the order's version will not automatically detect individual line-item changes unless the system enforces coordinated update/transaction rules.

Document modeling, invariant selection, and concurrency protocols must be designed as **a cohesive whole**.

## 15. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Reading document then `$set` by ID without version check | Lost update when two requests use stale snapshots | CAS with version filter |
| Having a version field but forgetting `$inc` on update | Subsequent writers still match the old version | Increment version in the same atomic operation |
| One writer updates data without incrementing version | OCC protocol is broken | Standardize all write paths |
| Always returning "modified by someone else" on `matchedCount:0` | May actually be not found/wrong tenant/invalid state | Reconcile by ID and access scope |
| Enabling `upsert:true` for CAS | Can attempt an insert when version is stale | CAS uses update **without upsert** |
| Automatically overwriting with the whole stale snapshot on conflict | Loses other users' changes | Rule-based patch rebase or report conflict |
| Infinite retries on contended documents | Increases load, latency, and loop risk | Cap attempts, backoff/jitter |
| Taking version from client timestamps | Clock skew, duplicate timestamps, insufficient precision | Controlled integer/token per protocol |
| Letting clients set version in the payload | Can break concurrency protocol | Whitelist fields, server increments |
| Creating `{version:1}` index for every `_id`-based CAS | Unnecessary index overhead | Evaluate `_id`/business key indexes and workload |
| Equating `matchedCount:0` with MongoDB write conflict error | Confuses business conflict with database error | Distinguish CAS outcome from error/label |
| Treating timeout as certain non-write | Retries can duplicate effects | Reconcile, idempotency key, suitable write concern |
| Thinking version stops duplicate charges | A new request can read the new version and debit again | Operation ID, unique registry/transaction |
| Using order OCC to guard multiple collections | Loses cross-document atomicity | Transaction or proper aggregate design |
| Auto-retrying edits on conflicting fields | Overwrites user intent | Three-way merge or ask confirmation |
| Putting external side effects inside transaction callback | Callback retries can invoke side effects multiple times | Outbox/idempotent consumer |
| Failing to migrate legacy documents missing version | CAS fails to match or resets inconsistently | Migration and validation prior to rollout |

## 16. Phased OCC rollout

### 16.1. Step 1: define invariants and version scope

Clarify:

- Does version represent **one document**, a sub-element, or a business aggregate?
- Which changes must increment version?
- Which independent writes are allowed to auto-merge?
- Which operations must return a conflict for user confirmation?
- Which business/tenant conditions must appear alongside version in CAS?

Without clear rules, services can interpret version differently and lose protection against lost updates.

### 16.2. Step 2: initialization and migration

Ensure new documents have a standard version. For existing documents:

1. Audit existing `version` types and documents missing the field.
2. Pick a migration policy, e.g. assigning an appropriate initial version where missing.
3. Coordinate rollout timing between old and new writers.
4. Add schema validation if requiring version presence and exact BSON type.
5. Monitor conflicts during the transition period.

Do not assign a fixed version to old documents while non-compliant writers remain active and assume OCC is already fully protecting data.

### 16.3. Step 3: API returns version and requires precondition

GET outputs must include version or ETag per contract. Update APIs accept expectedVersion/If-Match and **require sending it** for operations needing OCC. Never silently substitute the latest version on the server when a request omits the precondition, as that re-enables undetected overwrites.

### 16.4. Step 4: update via CAS

Use:

```javascript
{
  filter: {
    _id: targetId,
    tenantId: authenticatedTenantId,
    version: expectedVersion
  },
  update: {
    $set: allowedChanges,
    $inc: { version: 1 }
  },
  options: { upsert: false }
}
```

This is a **descriptive structure template**, not a direct MongoDB command. In a driver, pass the three parts into `updateOne(filter, update, options)` and inspect the acknowledged result.

### 16.5. Step 5: observe and handle conflicts

Logs can include:

- request ID or correlation ID;
- document/tenant ID per security policy;
- expectedVersion;
- outcome `UPDATED / CONFLICT / NOT_FOUND / UNKNOWN`;
- retry count and processing latency;
- MongoDB error code when an actual error occurs.

Do not log full sensitive payloads or credentials just to debug version. Monitor **conflict rate**, update latency, and average attempts to spot "hot" documents.

### 16.6. Step 6: audit special write paths

Paths easily overlooked:

- data import scripts;
- bulk writes or batch jobs;
- event consumers;
- aggregation pipeline updates;
- admin tools;
- migrations;
- document replace operations;
- older apps not yet updated to the new API.

For each path, explicitly decide whether it requires CAS, must bump version, or is a governed exception. Otherwise, one non-compliant writer can undermine guarantees across the whole system.

## 17. Self-check with real-world scenarios

### 17.1. Scenario A: two users editing price concurrently

A document has `version:10`. A and B both read version 10. A sets price 100000, B sets price 120000. Both use filter `{_id,version:10}` and `$inc` version.

Questions:

1. How many CAS updates can match and increment version from 10 to 11 in this race?
2. What `matchedCount` does the losing request receive?
3. Should B automatically retry with version 11 and price 120000 without asking the user?

**Hint:** only one operation can succeed at version 10. A request can re-read and decide whether to retry per policy; when two people edit **the same price field**, automatic overwriting usually requires careful consideration.

### 17.2. Scenario B: price and description are independent fields

A edits price and B edits description from the same snapshot. After A saves, B gets a conflict. Design a policy allowing B to load the new version and reapply **only the description field**, without altering the price A saved.

Answer for yourself: why would resubmitting the entire old document lose the new price? Under what condition is a seemingly independent patch actually unsafe?

### 17.3. Scenario C: document deleted

A client holds `expectedVersion:5`. While the user is editing, an admin deletes the document. CAS on `_id + version` returns `matchedCount:0`. If the server looks only at this result, what wrong error type might it report? How should it re-query without exposing cross-tenant resources?

### 17.4. Scenario D: inventory stock

A document has `quantity:3`. Two requests both want to deduct 2.

- If using `findOne`, computing, and `$set`, why can it write incorrectly?
- If using `updateOne({quantity:{$gte:2}},{$inc:{quantity:-2}})`, what does the condition protect?
- If a request is replayed by the client after a timeout, why is the quantity condition alone insufficient to replace an operation ID/idempotency?

### 17.5. Scenario E: transactions and side effects

A request approves an order, deducts inventory in another document, and sends an email. Identify:

- Which parts can go inside a MongoDB transaction?
- Which part requires an outbox/idempotent consumer?
- Why does incrementing `order.version` alone fail to protect the entire workflow?

## 18. Safely cleaning up practice data

The examples in section 4 only insert a single document in the test collection `mongo_occ_row216_lab.products_demo`. Before deleting, verify the database and ID created in **the same `mongosh` session**:

```javascript
print("database=" + lab.getName());
print("collection=" + products.getName());
print("runId=" + runId);
printjson(
  products.findOne(
    { _id: productId, runId },
    { _id: 1, runId: 1, sku: 1, version: 1 }
  )
);
```

Once confirmed to be the document you created, delete using a filter containing **both ID and runId**:

```javascript
const removed = products.deleteOne({
  _id: productId,
  runId
});

printjson(removed);
print("remaining=" + products.countDocuments({
  _id: productId,
  runId
}));
```

If the document does not match or `runId` can no longer be identified, stop and verify data ownership. Never run `deleteMany({})`, `drop()`, or `dropDatabase()` in a shared environment.

## 19. Review questions

1. How does a lost update happen when two requests read the same document?
2. Does MongoDB's single-document `updateOne` atomicity mean a `findOne` followed by `updateOne` sequence is also atomic?
3. Why must `version` be placed in the filter rather than only in the update payload?
4. Why must version be incremented in the **same** CAS operation?
5. Is `matchedCount:0` always a version conflict?
6. Why must `upsert:true` not be enabled when updating against an old version?
7. When can a patch be automatically rebased? When is user reconciliation needed?
8. Why is an index `{version:1}` usually unnecessary when every CAS already filters by `_id`?
9. When is `findOneAndUpdate` more convenient than `updateOne`?
10. Why can a timeout after a write lead to an unknown state even if a subsequent read sees a new version?
11. How do driver retryable writes differ from API-level idempotency?
12. Can a single document's version protect atomicity across multiple other documents?
13. Why can updating stock with `$inc` avoid lost updates in some cases without OCC?
14. Why must all writers, including migrations and background jobs, follow the same protocol?
15. When a document contains thousands of sub-elements, what are the pros and cons of using a single document-wide version?
16. How do ETag/If-Match relate to expectedVersion and HTTP `412` responses?

## 20. Conclusion

**Optimistic locking with a `version` field** is a concurrency control pattern in MongoDB: **read document with version → submit changes with expectedVersion → update atomically while version still matches → increment version in the same write**. As a result, a request built from stale data can be detected instead of silently overwriting another request's changes.

OCC does not automatically decide how conflicts are resolved. The application must distinguish **conflict**, **not found**, **unmet business condition**, and **unknown write outcome**; and choose to notify the user, re-read/merge, or perform bounded retries according to operation semantics. All writers must adhere to the shared version convention, and multi-document operations or those with external side effects require transactions, unique constraints, and idempotency as appropriate. **Version helps prevent lost updates, but ultimate correctness depends on both the data model and business workflow.**
