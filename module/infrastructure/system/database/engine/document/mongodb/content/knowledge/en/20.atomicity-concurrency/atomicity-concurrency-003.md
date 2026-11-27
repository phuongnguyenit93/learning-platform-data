# Conditional Updates and Version Comparison Before Writing in MongoDB

## 1. Concurrent write problem: lost update

Suppose a product in MongoDB has the following data:

~~~javascript
{
  _id: "P-100",
  tenantId: "SHOP-A",
  name: "Wireless Mouse",
  priceCents: NumberLong(250000),
  stock: NumberInt(10),
  status: "ACTIVE",
  version: NumberLong(7)
}
~~~

Two users A and B open the product edit page at the same time. Both read price 250000 and version 7. A changes the price to 260000; B changes it to 240000. If both requests only locate the document by _id:

~~~javascript
// Request A
db.products.updateOne(
  { _id: "P-100" },
  { $set: { priceCents: NumberLong(260000) } }
);

// Request B
db.products.updateOne(
  { _id: "P-100" },
  { $set: { priceCents: NumberLong(240000) } }
);
~~~

Both can succeed. The request that executes later will overwrite the earlier request's value without knowing it changed. This phenomenon is called a **lost update**.

This is **not an atomicity bug in MongoDB**: each write command is applied atomically, but filtering only by _id does not express the requirement "the document must still be in the state I read."

**Core principle:** place the expected value or version into **the filter of the write command itself**, then inspect matchedCount in the result.

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    version: NumberLong(7)
  },
  {
    $set: { priceCents: NumberLong(260000) },
    $inc: { version: NumberLong(1) }
  }
);
~~~

If A writes successfully, version increments to 8. Request B, still sending expectedVersion = 7, will not match and cannot silently overwrite the new price. This technique is commonly called **optimistic concurrency control (OCC)**, **optimistic locking**, or document-level **compare-and-swap (CAS)**.

### Lesson objectives

- Understand single-document atomicity and the race conditions the application must still handle itself.
- Write conditional updates based on state or prior values.
- Use version/revision to reject writes based on stale snapshots.
- Distinguish when to use **$set**, **$inc**, **findOneAndUpdate**, and transactions.
- Handle conflicts, retries, idempotency, and write concern.
- Apply MongoDB Java Sync Driver and Spring Data MongoDB with **@Version**.

## 2. Preparing the practice data

Use **mongosh** on a dedicated database:

~~~javascript
use mongo_concurrency_lab

db.products.insertMany([
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    name: "Wireless Mouse",
    priceCents: NumberLong(250000),
    stock: NumberInt(10),
    status: "ACTIVE",
    version: NumberLong(7),
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  },
  {
    _id: "P-200",
    tenantId: "SHOP-A",
    name: "Mechanical Keyboard",
    priceCents: NumberLong(1000000),
    stock: NumberInt(3),
    status: "DRAFT",
    version: NumberLong(1),
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  },
  {
    _id: "P-300",
    tenantId: "SHOP-B",
    name: "Laptop Stand",
    priceCents: NumberLong(400000),
    stock: NumberInt(8),
    status: "ACTIVE",
    version: NumberLong(2),
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  }
]);
~~~

Each example below is explained starting from **the initial state**, unless noted otherwise. Running updates modifies the lab data; reset the data in a controlled manner before testing independent examples. If you repeat insertMany with the same _id, you will encounter a duplicate key error.

Field roles:

| Field | Role |
|---|---|
| **_id** | Document identifier. |
| **tenantId** | Tenant scope that must be enforced on the server. |
| **priceCents** | Price stored in the smallest integer unit, avoiding double arithmetic for money in examples. |
| **stock** | Remaining inventory quantity. |
| **status** | Workflow state. |
| **version** | Comparison token to detect whether the document was modified since the prior read. |
| **updatedAt** | Timestamp metadata; should not replace version by default. |

**NumberLong** is BSON Int64, corresponding to **Long/long** in Java. Version must be consistent in type and initialization rules.

## 3. Document-level atomicity and its limits

MongoDB guarantees that a write operation on **a single document** is atomic, even when modifying multiple fields:

~~~javascript
db.products.updateOne(
  { _id: "P-100" },
  {
    $set: {
      name: "Wireless Mouse Pro",
      status: "ACTIVE"
    },
    $inc: {
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

The changes in the command above are applied together on a single document. Under concurrent updates, MongoDB re-evaluates the filter condition when applying the operation. This is the foundation that makes conditional updates reliable.

However, atomicity **does not automatically guarantee**:

1. That two requests both reading stale data will automatically detect a conflict.
2. That a sequence of findOne followed by updateOne at two different moments is atomic.
3. That an entire updateMany across multiple documents is a transaction.
4. That changes in email, payments, a message broker, or another database share the same atomicity.
5. That MongoDB automatically knows which state transitions are valid for your domain.

**Atomicity is a property of a write command; concurrency correctness still depends on filter conditions and business design.**

## 4. Conditional update by expected state

A typical conditional update looks like:

~~~javascript
db.collection.updateOne(
  {
    _id: targetId,
    status: expectedStatus
  },
  {
    $set: { status: newStatus }
  }
);
~~~

For example, only allowing a product transition **DRAFT → ACTIVE**:

~~~javascript
db.products.updateOne(
  {
    _id: "P-200",
    tenantId: "SHOP-A",
    status: "DRAFT"
  },
  {
    $set: { status: "ACTIVE" },
    $currentDate: { updatedAt: true }
  }
);
~~~

When P-200 is DRAFT, the command matches and transitions it to ACTIVE. If another request has already moved P-200 to REJECTED or ACTIVE, the command requiring status DRAFT no longer matches.

### 4.1. Analyzing UpdateResult

~~~javascript
const result = db.products.updateOne(
  {
    _id: "P-200",
    status: "DRAFT"
  },
  {
    $set: { status: "ACTIVE" }
  }
);

printjson(result);
~~~

Values typically checked:

- **matchedCount:** number of documents matching the filter.
- **modifiedCount:** number of documents actually modified.
- **acknowledged:** whether acknowledgment was received from the server.
- **upsertedId/upsertedCount:** only meaningful if the operation enables upsert.

With P-200 initially DRAFT, the successful update returns matchedCount = 1, modifiedCount = 1. If run again when P-200 is already ACTIVE, the status DRAFT filter no longer matches: matchedCount = 0.

**matchedCount is not the number of modified fields**, it is the number of documents. For updateOne, the value is usually 0 or 1.

### 4.2. Why is check-then-act unsafe?

~~~javascript
// Race-prone pattern:
const product = db.products.findOne({ _id: "P-200" });

if (product.status === "DRAFT") {
  db.products.updateOne(
    { _id: "P-200" },
    { $set: { status: "ACTIVE" } }
  );
}
~~~

Between findOne and updateOne, another request could have changed status to REJECTED. The client-side JavaScript check no longer protects the update command.

Better:

~~~javascript
db.products.updateOne(
  { _id: "P-200", status: "DRAFT" },
  { $set: { status: "ACTIVE" } }
);
~~~

The state condition sits directly inside **the filter of the same write command**, so it is checked at update time.

## 5. Compare-and-swap by current field value

The idea behind CAS is:

~~~text
IF currentValue == expectedValue:
    WRITE newValue
ELSE:
    DO NOT WRITE
~~~

In MongoDB:

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    priceCents: NumberLong(250000)
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    }
  }
);
~~~

Two requests both expecting priceCents = 250000, yet writing two different new prices, cannot both match once one operation has actually changed priceCents.

### 5.1. A/B simulation

~~~javascript
// A:
const a = db.products.updateOne(
  { _id: "P-100", priceCents: NumberLong(250000) },
  { $set: { priceCents: NumberLong(260000) } }
);

// B:
const b = db.products.updateOne(
  { _id: "P-100", priceCents: NumberLong(250000) },
  { $set: { priceCents: NumberLong(240000) } }
);
~~~

If A writes first: A matches 1, B matches 0, final price is 260000. If B writes first: B matches 1, A matches 0, final price is 240000. Ordering depends on scheduling; never assume A always wins.

### 5.2. Limitation: only detects the compared field

If another request edits **name** while keeping **priceCents**, a filter comparing only priceCents still matches. This may be desirable when the two fields are independent, or wrong if the pricing decision depended on the old name/description.

When you need to protect **the entire snapshot**, using a shared **version** field is usually clearer than listing every old field.

### 5.3. ABA problem

Suppose the price changes sequentially:

~~~text
250000 -> 260000 -> 250000
~~~

An old client comparing only priceCents = 250000 can match again, even though the data changed twice. This is the **ABA problem**.

If every write increments version:

~~~text
price 250000, version 7
price 260000, version 8
price 250000, version 9
~~~

then a client holding version 7 cannot write based on a stale snapshot merely because the price returned to 250000.

## 6. Optimistic locking with version

### 6.1. Lifecycle of a request

~~~text
Clients A and B read:
  _id=P-100, price=250000, version=7
               |
       +-------+-------+
       |               |
       v               v
 A edits price     B edits price
       |               |
       v               v
 UPDATE WHERE       UPDATE WHERE
 version=7          version=7
       |               |
       v               v
 A writes ok        B no longer matches
 version -> 8       if A won
       |               |
       v               v
   success             conflict
~~~

The application does not hold an exclusive lock while the user has the form open. It only compares version at write time. Hence this is **optimistic locking**.

### 6.2. Complete CAS command

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7)
  },
  {
    $set: {
      name: "Wireless Mouse Pro",
      priceCents: NumberLong(260000)
    },
    $inc: {
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Each part has a responsibility:

| Component | Role |
|---|---|
| **_id** | Locates the document. |
| **tenantId** | Restricts tenant scope; server must still verify authorization. |
| **version:7** | Writes only if the document is still at the version the client read. |
| **$set** | Writes the permitted business fields. |
| **$inc version:1** | Ensures the winning write creates a new version. |
| **$currentDate** | Updates timestamp metadata server-side. |

**The new version is not chosen by the client.** The client only sends expectedVersion, while the server checks and increments the version within the same update.

### 6.3. Why must version be incremented in the same command?

Do not do this:

~~~javascript
// Inconsistent: two separate commands.
db.products.updateOne(
  { _id: "P-100", version: NumberLong(7) },
  { $set: { priceCents: NumberLong(260000) } }
);

db.products.updateOne(
  { _id: "P-100" },
  { $inc: { version: NumberLong(1) } }
);
~~~

The application can crash between the two commands. If the price changed but version did not increment, OCC will fail to detect the change.

The right way is combining **$set** and **$inc version** in a single update:

~~~javascript
{
  $set: { priceCents: NumberLong(260000) },
  $inc: { version: NumberLong(1) }
}
~~~

MongoDB guarantees both changes belong to the same atomic operation on the document.

### 6.4. All relevant write paths must increment version

If Service A uses version CAS while Service B updates directly by _id without incrementing version:

~~~javascript
// Service B bypasses version:
db.products.updateOne(
  { _id: "P-100" },
  { $set: { name: "Other Name" } }
);
~~~

then clients may still hold the old version and fail to detect that name changed. The convention must be enforced across APIs, batch jobs, migrations, admin scripts, and background workers.

If certain technical fields are allowed to change without incrementing version, that decision must be explicitly documented and proven not to affect business snapshots.

### 6.5. Initializing and storing version

One convention:

~~~javascript
db.products.insertOne({
  _id: "P-NEW",
  name: "New Product",
  version: NumberLong(0)
});
~~~

After the first successful write, version = 1. Starting at 0 or 1 is both acceptable, but it must be consistent across libraries and systems.

Rules:

1. Use an appropriate integer type, typically BSON Int64/Java Long.
2. Never leave documents requiring CAS without a version field.
3. Never let clients assign an arbitrary version.
4. Legacy document migrations must bring documents to a unified convention.
5. Avoid rolling version back to older values during restore/migration while old clients remain active.

## 7. Read and write API with version

Read side:

~~~javascript
db.products.findOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A"
  },
  {
    name: 1,
    priceCents: 1,
    status: 1,
    version: 1
  }
);
~~~

API returns:

~~~json
{
  "id": "P-100",
  "name": "Wireless Mouse",
  "priceCents": 250000,
  "status": "ACTIVE",
  "version": 7
}
~~~

Client sends:

~~~json
{
  "name": "Wireless Mouse Pro",
  "priceCents": 260000,
  "expectedVersion": 7
}
~~~

The server obtains tenant/authorization from the authenticated context, validates the payload, and builds the filter using _id, tenantId, and expectedVersion. Do not use expectedVersion as proof of access rights: version is not a secret.

### 7.1. Conflict response

When version does not match, the API can return:

~~~json
{
  "code": "VERSION_CONFLICT",
  "message": "Product was updated by another request.",
  "expectedVersion": 7,
  "currentVersion": 8
}
~~~

Only return **currentVersion** if the server re-reads it and the user has permission to view the resource. Re-reading is a separate operation and can race with subsequent updates; do not treat it as an immutable history.

### 7.2. HTTP status

- **200 / 204:** update succeeded.
- **409 Conflict:** stale version per API contract.
- **412 Precondition Failed:** commonly used with HTTP **If-Match** and ETag.
- **404:** not found within the authorized scope.
- **400 / 422:** payload/transition violates contract.

Conditional HTTP request example:

~~~http
PATCH /products/P-100
If-Match: "v7"
Content-Type: application/json

{"name":"Wireless Mouse Pro"}
~~~

The server parses the ETag per contract into expectedVersion = 7 and puts it into the MongoDB filter. **ETag does not create OCC on its own if the database command does not compare version.**

## 8. Correctly interpreting matchedCount and modifiedCount

~~~javascript
const result = db.products.updateOne(
  {
    _id: "P-100",
    version: NumberLong(7)
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    },
    $inc: {
      version: NumberLong(1)
    }
  }
);

printjson(result);
~~~

If matched and write succeeded, you typically see matchedCount = 1, modifiedCount = 1. If version differed, matchedCount = 0, modifiedCount = 0.

**matchedCount = 0 is not exclusive proof of a version conflict**, because other causes exist:

- _id does not exist.
- Document belongs to another tenant.
- Status/business precondition is not satisfied.
- Version has changed.
- Another condition in the filter is false.

If differentiation is needed, the server can re-read within the authorization scope:

~~~javascript
db.products.findOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A"
  },
  {
    version: 1,
    status: 1,
    stock: 1
  }
);
~~~

**matchedCount = 1, modifiedCount = 0** can still be valid when only $set assigns a field to the exact value it already holds. With CAS incrementing version via $inc on match, version actually changes and modifiedCount is usually 1.

### 8.1. Acknowledged write concern

OCC needs to know whether the operation matched. With **WriteConcern.UNACKNOWLEDGED**, the application does not receive reliable write results to classify stale versions. Use an acknowledged write concern; consider **majority** depending on durability requirements.

Write concern addresses write acknowledgment/durability and **does not replace** version filters.

## 9. $inc and atomic arithmetic: when no prior read is needed

For a counter, the application does not need to read the value and compute in RAM:

~~~javascript
db.counters.insertOne({
  _id: "PAGE_VIEWS",
  count: NumberLong(0)
});

db.counters.updateOne(
  { _id: "PAGE_VIEWS" },
  { $inc: { count: NumberLong(1) } }
);

db.counters.updateOne(
  { _id: "PAGE_VIEWS" },
  { $inc: { count: NumberLong(1) } }
);
~~~

If each command succeeds once, the final value equals **2**. Two **$inc** operations do not overwrite each other's increments the way reading count=0 and executing **$set count=1** does.

### 9.1. Comparison with read-modify-write

~~~text
Unsafe:

A reads count = 0
B reads count = 0
A computes 0+1=1
B computes 0+1=1
A $set count=1
B $set count=1
Result can be = 1

Using $inc:

A $inc count by 1
B $inc count by 1
Result = 2 if both are applied once
~~~

### 9.2. $inc is not the same as snapshot CAS

**$inc** is suitable for incrementing/decrementing a current value; it does not detect other changes across the document. If a client edits name, price, and description based on a full snapshot, version may still be required.

### 9.3. $inc is not idempotent under application replay

If a client resends a request as a **new business action**, $inc can increment again. Drivers support **retryable writes** under specific conditions by recognizing retries of the same logical write; this does not mean the application can generate new commands and replay them indefinitely while expecting exactly-once semantics.

Operations such as placing orders, posting payments, and deducting stock require an **idempotency key** or suitable duplicate-prevention mechanism.

## 10. Keeping stock non-negative with conditional updates

Suppose **stock=10** and two concurrent requests each want to purchase 7 items.

Unsafe pattern:

~~~javascript
const product = db.products.findOne({
  _id: "P-100"
});

if (product.stock >= 7) {
  db.products.updateOne(
    { _id: "P-100" },
    { $inc: { stock: -7 } }
  );
}
~~~

Between **findOne** and **updateOne**, another request may have decremented stock. Two clients both reading stock=10 and subtracting 7 will produce stock=-4 if there is no condition at write time.

**Correct:** place the condition in the filter of the update itself:

~~~javascript
const requestedQty = 7;

const result = db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    status: "ACTIVE",
    stock: { $gte: requestedQty }
  },
  {
    $inc: {
      stock: -requestedQty,
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);

printjson(result);
~~~

If A wins, stock changes from 10 to 3. B checks **stock >= 7** against the new value and **does not match**. If B wins first, A is rejected similarly.

**Simply using $inc does not keep stock non-negative.** You must combine it with **stock >= requestedQty** in the filter.

### 10.1. Validate order quantity

If a client sends requestedQty = -5, the expression **-requestedQty** becomes +5, increasing stock. The server must validate that order quantity **is a positive integer**, within allowed bounds, not NaN, and within BSON type limits.

### 10.2. Do you need a version filter when deducting stock?

For "deduct if current stock is sufficient," filtering stock >= qty with a negative $inc suffices to protect the single-document invariant without needing a snapshot version.

You can **increment version** to signal to admin UIs that the document changed, but **filtering on expectedVersion** can cause unnecessary conflicts with other purchase requests when the rule depends only on current stock.

Distinguish:

| Business operation | Appropriate approach |
|---|---|
| Deduct current stock if sufficient | **{stock:{$gte:qty}} + $inc**. |
| Admin edits stock to an absolute number from an old form | **{version:expected} + $set stock + $inc version**. |
| Change order status while still NEW | **{status:"NEW"} + $set status**. |
| Save an entire multi-field snapshot | **Version CAS**. |

## 11. findOneAndUpdate: conditional write and reading the new state

**updateOne()** returns an UpdateResult, not the updated document directly. **findOneAndUpdate()** can update and return the document before or after the update depending on options.

~~~javascript
db.products.findOneAndUpdate(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7)
  },
  {
    $set: {
      name: "Wireless Mouse Plus"
    },
    $inc: {
      version: NumberLong(1)
    }
  },
  {
    returnDocument: "after",
    projection: {
      _id: 1,
      name: 1,
      version: 1
    }
  }
);
~~~

If matched, it returns the document **after the update**; if no matching document exists and upsert is off, it typically returns **null**.

The benefit is avoiding separate updateOne and findOne calls just to fetch the new version. Another request could modify the document between updateOne and findOne in a two-step approach.

**Note:** findOneAndUpdate does not automatically enable OCC unless a version condition is in the filter. It also has its own resource/retryable-write characteristics that should be measured on large documents and real topologies.

## 12. OCC conflicts and application handling

### 12.1. Do not silently swap expectedVersion and resend the old payload

When a client sends expectedVersion=7 while the server is at version=8, the wrong response is reading version=8 and **resubmitting the exact old payload without inspecting the new changes**.

That turns optimistic locking into **disguised last-write-wins**.

Better handling:

1. Reject the stale write with a clear error code.
2. Let the client reload the fresh snapshot or view the other user's changes.
3. If the domain allows, compute a **delta** and intentionally merge onto the fresh snapshot.
4. Perform a new CAS with the current version after resolving.
5. Cap retry attempts; never loop infinitely.

### 12.2. Distinguishing conflicts from network errors

An **acknowledged update returning matchedCount=0** is a clear outcome: no document matched the filter.

By contrast, on a **timeout or connection drop after sending the command**, the application cannot tell whether the server wrote successfully and the response was lost, or whether the operation was never applied. This is an **unknown outcome** and requires different handling from a normal OCC conflict.

### 12.3. Version CAS helps retries but does not prove the first request succeeded

Suppose a CAS request with version=7 succeeded, bumping version to 8, but the response was lost. A retry sent as a new request filtering version=7 will not match.

This prevents the same payload from being written onto the new version, yet **matchedCount=0 does not prove the original request succeeded**. Another request might have won first.

When distinguishing the two cases is required, use a **requestId/idempotency record** written consistently with the business change.

### 12.4. Bounded retries

Do not write:

~~~text
while conflict:
  readLatestVersion()
  writeOldPayloadAgain()
~~~

For an operation that can safely recompute like **increase by 1**, use $inc instead of a CAS loop. For meaningful form edits, conflicts must be resolved or surfaced to the user.

In valid retry flows, use **backoff/jitter**, cap attempts, record metrics, and never repeat external side effects outside the database.

## 13. Idempotency keys for retryable requests

Suppose an API receives:

~~~json
{
  "requestId": "REQ-001",
  "accountId": "ACC-100",
  "amountCents": 5000
}
~~~

If the same **REQ-001** is resent due to a retry, the system must not debit money a second time.

A common mechanism uses a **unique index on the idempotency key**:

~~~javascript
db.processed_requests.createIndex(
  {
    tenantId: 1,
    requestId: 1
  },
  {
    unique: true,
    name: "uq_tenant_request"
  }
);
~~~

However, adding a unique index alone does not make these two steps atomic:

~~~text
1. INSERT processed_requests
2. UPDATE account balance
~~~

If the process crashes between the two steps, the marker is saved without debiting the balance, or vice versa depending on order.

Appropriate solutions include:

- **A transaction** recording the marker and updating multiple documents together.
- **A single document** holding both the marker and modified state in the same update, if marker size/count is bounded and the domain allows.
- **A stateful business protocol** with retry reconciliation and unique business keys.

Do not store unbounded requestIds in a single array: documents still have the standard **16 MiB** BSON size limit.

## 14. updatedAt does not replace version by default

An application might attempt CAS using a timestamp:

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    updatedAt: ISODate("2026-07-01T00:00:00Z")
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

A timestamp can act as a token if it always changes and precision is preserved. However:

- **BSON Date has millisecond precision**; two writes close in time can produce the same timestamp.
- Services can experience clock skew.
- Passing through JSON/JavaScript/Java can lose precision or alter timezone formatting.
- Some write paths might forget to update updatedAt.
- Migrations/restores may preserve old timestamps.

An **integer version incremented on every write** is usually clearer for OCC. **updatedAt** remains useful for auditing, display, and monitoring.

## 15. CAS on an array of embedded documents

Suppose an order is:

~~~javascript
db.orders.insertOne({
  _id: "ORD-100",
  tenantId: "SHOP-A",
  status: "OPEN",
  version: NumberLong(3),
  items: [
    {
      lineId: "L1",
      sku: "SKU-A",
      qty: NumberInt(2),
      state: "NEW"
    },
    {
      lineId: "L2",
      sku: "SKU-B",
      qty: NumberInt(1),
      state: "RESERVED"
    }
  ]
});
~~~

Transition only **line L1 from NEW to PACKED**, if the order is still at version=3:

~~~javascript
db.orders.updateOne(
  {
    _id: "ORD-100",
    tenantId: "SHOP-A",
    version: NumberLong(3),
    items: {
      $elemMatch: {
        lineId: "L1",
        state: "NEW"
      }
    }
  },
  {
    $set: {
      "items.$[line].state": "PACKED"
    },
    $inc: {
      version: NumberLong(1)
    }
  },
  {
    arrayFilters: [
      {
        "line.lineId": "L1",
        "line.state": "NEW"
      }
    ]
  }
);
~~~

### 15.1. Why are both $elemMatch and arrayFilters needed?

**The main filter** selects a document with the matching version that contains **one item having both lineId L1 and state NEW**.

**arrayFilters** selects which item to modify **inside the already-matched document**.

If the main filter only checked _id/version and arrayFilters found no NEW item, **$set on items** would modify zero elements, yet **$inc version** would still execute because the parent document matched. Adding $elemMatch prevents incrementing version when no qualifying item exists.

### 15.2. Avoid array conditions matching across different elements

The filter:

~~~javascript
{
  "items.lineId": "L1",
  "items.state": "NEW"
}
~~~

can match a document if the two conditions hold on **two different elements**. When requiring the same element, use **$elemMatch** as shown above.

### 15.3. Version must increment together with array edits

A document with multiple embedded items is still **a single MongoDB document**. Updating items and incrementing version in the same updateOne is one document-level atomic operation. Other clients holding an old version will know the document changed, even if they were editing a different item.

If conflicts between independent items occur too frequently, consider moving items to a separate collection or using fine-grained item-level conditions when the domain permits, rather than abandoning OCC altogether.

## 16. updateMany and cross-document atomicity

~~~javascript
db.products.updateMany(
  {
    tenantId: "SHOP-A",
    status: "DRAFT"
  },
  {
    $set: {
      status: "ACTIVE"
    },
    $inc: {
      version: NumberLong(1)
    }
  }
);
~~~

Each document is updated atomically, but **the group of multiple documents does not automatically become a transaction**. Some documents may change while other operations interleave.

With updateMany, do not use **a single shared expectedVersion** if documents hold different versions unless explicitly intended. If business logic requires all documents to commit or roll back together, design a **multi-document transaction** or an appropriate application-level mechanism.

## 17. CAS does not replace unique indexes

Suppose two requests simultaneously check whether an email already exists:

~~~javascript
db.users.findOne({
  emailNormalized: "user@example.test"
});
~~~

Both can read null and then attempt to insert. This is the race condition of the "check non-existence then create" pattern.

A unique index:

~~~javascript
db.users.createIndex(
  {
    tenantId: 1,
    emailNormalized: 1
  },
  {
    unique: true,
    name: "uq_tenant_email"
  }
);
~~~

allows MongoDB to reject documents with duplicate unique keys within the indexed scope. For sharded collections, unique constraints must follow specific shard key/index rules.

| Technique | Protected invariant |
|---|---|
| **Version CAS** | Prevents writing a stale snapshot over a modified document. |
| **Unique index** | Prevents creating prohibited duplicate keys across multiple documents. |
| **Business filter + $inc** | Prevents negative stock within a single document. |
| **Transaction** | Multi-document changes commit/roll back together per transaction semantics. |

## 18. When is a transaction needed?

If an order-placement flow must simultaneously:

1. Deduct product stock.
2. Create an order.
3. Record an inventory movement.

then a single updateOne on product only protects stock on that document; it **does not guarantee** that the order and inventory movement are also created.

On MongoDB topologies supporting transactions, consider:

~~~text
BEGIN TRANSACTION
  UPDATE products with stock >= qty
  INSERT orders
  INSERT inventory_movements
COMMIT / ABORT
~~~

Transactions come with overhead, timeout/retry behavior, and operational constraints. A transaction callback can be re-executed on transient errors, so **do not directly charge a card or send non-idempotent emails inside the callback**.

Transactions provide multi-document atomicity, but do not replace version CAS when the business rule is **preventing a user from saving a form from a stale snapshot**. Never keep a transaction open while a user edits a form; use read snapshot → user edits → conditional write or a short transaction on submit.

## 19. Java Sync Driver: conditional updates and version CAS

The MongoDB Java Sync Driver provides **Filters**, **Updates** builders, and the **UpdateResult** response object.

### 19.1. Service updating price when version still matches

~~~java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;
import org.bson.conversions.Bson;

public final class ProductCasService {
    private final MongoCollection<Document> products;

    public ProductCasService(MongoDatabase database) {
        this.products = database.getCollection("products");
    }

    public boolean updatePrice(
            String productId,
            String tenantId,
            long expectedVersion,
            long newPriceCents) {

        if (newPriceCents < 0) {
            throw new IllegalArgumentException(
                    "Price must be nonnegative"
            );
        }

        Bson filter = Filters.and(
                Filters.eq("_id", productId),
                Filters.eq("tenantId", tenantId),
                Filters.eq("version", expectedVersion)
        );

        Bson update = Updates.combine(
                Updates.set("priceCents", newPriceCents),
                Updates.inc("version", 1L),
                Updates.currentDate("updatedAt")
        );

        UpdateResult result = products.updateOne(
                filter,
                update
        );

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                    "Optimistic locking needs acknowledged writes"
            );
        }

        return result.getMatchedCount() == 1;
    }
}
~~~

Explanation:

- **expectedVersion** comes from the snapshot the client read.
- **Filters.eq("version", expectedVersion)** is the CAS condition.
- **Updates.inc("version",1L)** increments version in the same write operation.
- **Updates.currentDate("updatedAt")** updates metadata on the MongoDB server.
- **matchedCount=1** means the filter matched; **0** may indicate conflict, missing resource, or another unsatisfied condition.

This is a sample persistence class. Production applications also need authorization, validation, exception handling, write concern, and metrics.

### 19.2. Deducting stock in Java

Another method using the same products field of the service:

~~~java
public boolean reserveStock(
        String productId,
        String tenantId,
        int requestedQty) {

    if (requestedQty <= 0) {
        throw new IllegalArgumentException(
                "requestedQty must be positive"
        );
    }

    Bson filter = Filters.and(
            Filters.eq("_id", productId),
            Filters.eq("tenantId", tenantId),
            Filters.eq("status", "ACTIVE"),
            Filters.gte("stock", requestedQty)
    );

    Bson update = Updates.combine(
            Updates.inc("stock", -requestedQty),
            Updates.inc("version", 1L)
    );

    UpdateResult result = products.updateOne(
            filter,
            update
    );

    if (!result.wasAcknowledged()) {
        throw new IllegalStateException(
                "Acknowledged write required"
        );
    }

    return result.getMatchedCount() == 1;
}
~~~

This method does not need to read stock before deducting. If stock is insufficient, the update does not match. However, if a client replays the same intent as a new request while stock is still sufficient, it can deduct again; business-level idempotency is needed.

### 19.3. findOneAndUpdate returning the updated document

~~~java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Document updated = products.findOneAndUpdate(
        Filters.and(
                Filters.eq("_id", "P-100"),
                Filters.eq("version", 7L)
        ),
        Updates.combine(
                Updates.set("status", "ACTIVE"),
                Updates.inc("version", 1L)
        ),
        new FindOneAndUpdateOptions()
                .returnDocument(ReturnDocument.AFTER)
);

if (updated == null) {
    // No document matched the filter.
}
~~~

This is a conditional write that returns the document in the same operation. It does not enable OCC unless expectedVersion is in the filter.

### 19.4. replaceOne with a stale snapshot: a major risk

~~~java
Document old = products.find(
        Filters.eq("_id", productId)
).first();

if (old != null) {
    old.put("priceCents", 260000L);
    products.replaceOne(
            Filters.eq("_id", productId),
            old
    );
}
~~~

**replaceOne** replaces the entire document from the old snapshot, overwriting fields modified by other workers between find and replace. If you must replace, include a version condition:

~~~java
long expected = old.getLong("version");

Document replacement = new Document(old);
replacement.put("priceCents", 260000L);
replacement.put("version", expected + 1L);

UpdateResult result = products.replaceOne(
        Filters.and(
                Filters.eq("_id", productId),
                Filters.eq("version", expected)
        ),
        replacement
);
~~~

Even so, full-document replacement risks dropping fields not loaded by a mapper/DTO. When editing only a few fields, **$set + $inc** has clearer scope and is easier to control.

### 19.5. BSON type of version

If documents store version as BSON Int64, Java uses **Long/long**. With org.bson.Document, **getLong("version")** may fail if legacy documents store BSON Int32; perform controlled migration/conversion.

Do not use the string **"7"** when the database stores version as a number: a string and a BSON number are not the same value type.

## 20. Spring Data MongoDB: optimistic locking via @Version

Spring Data MongoDB supports **@Version** in appropriate CRUD operations, similar to JPA's optimistic locking concept.

### 20.1. Sample entity

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public class ProductDocument {

    @Id
    private String id;

    private String tenantId;
    private String name;
    private Long priceCents;

    @Version
    private Long version;

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Long getPriceCents() {
        return priceCents;
    }

    public void setPriceCents(Long priceCents) {
        this.priceCents = priceCents;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

The **@Version** field instructs Spring Data to add a version condition during supported entity save operations and increment version upon a successful save.

### 20.2. Two copies reading and saving concurrently

~~~java
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

ProductDocument copyA = mongoTemplate.findOne(
        Query.query(Criteria.where("_id").is("P-100")),
        ProductDocument.class
);

ProductDocument copyB = mongoTemplate.findOne(
        Query.query(Criteria.where("_id").is("P-100")),
        ProductDocument.class
);

copyA.setName("Wireless Mouse Pro");
mongoTemplate.save(copyA);

copyB.setName("Wireless Mouse V2");
mongoTemplate.save(copyB);
~~~

Suppose both copies had version 7 before saving. If copyA saves successfully and version increments to 8, saving copyB throws **OptimisticLockingFailureException**, instead of overwriting data from the stale version.

### 20.3. Catching and handling the exception

~~~java
import org.springframework.dao.OptimisticLockingFailureException;

try {
    mongoTemplate.save(copyB);
} catch (OptimisticLockingFailureException ex) {
    // Map to HTTP 409 or 412 per API contract.
    // Do not silently overwrite with the old payload.
    throw ex;
}
~~~

### 20.4. How does Spring Data initialize version?

According to Spring Data MongoDB documentation, an unset **@Version** on insert initializes to:

- **Wrapper types** like Long/Integer: **0**.
- **Primitive types** like long/int: **1**.

This is a framework convention, not a mandatory rule enforced by the MongoDB server. For legacy collections, standardize data/version values before relying on OCC.

### 20.5. Raw template updates do not automatically become snapshot CAS

Spring Data notes that **only specific CRUD operations** handle version per framework semantics. Some template updates may auto-increment version if the version field is absent from Update, **but that does not mean every updateFirst/updateMulti automatically adds the client-read entity's expectedVersion to the filter**.

Example without explicit CAS:

~~~java
Query query = Query.query(
        Criteria.where("_id").is("P-100")
);

Update update = new Update()
        .set("name", "Another Name");

mongoTemplate.updateFirst(
        query,
        update,
        ProductDocument.class
);
~~~

To use template update for CAS:

~~~java
import org.springframework.data.mongodb.core.query.Update;
import com.mongodb.client.result.UpdateResult;

Query query = Query.query(
        Criteria.where("_id").is("P-100")
                .and("tenantId").is("SHOP-A")
                .and("version").is(7L)
);

Update update = new Update()
        .set("priceCents", 260000L)
        .inc("version", 1L);

UpdateResult result = mongoTemplate.updateFirst(
        query,
        update,
        ProductDocument.class
);
~~~

Because version is explicitly specified in Update, Spring Data does not need to auto-increment it under the version-absent rule. Check the API documentation for your exact Spring Data version to avoid duplicate version logic.

### 20.6. Acknowledged writes and deletes

Optimistic locking requires **write acknowledgement** to detect stale operations. With WriteConcern.UNACKNOWLEDGED, Spring Data may fail to detect conflicts properly.

To delete a document only if unchanged:

~~~javascript
db.products.deleteOne({
  _id: "P-100",
  tenantId: "SHOP-A",
  version: NumberLong(7)
});
~~~

Check **deletedCount** to verify whether a matching document was removed. In Spring Data, **delete(entity)** checks version, whereas **deleteById(id)** has different semantics and can bypass version checks. Choose the API matching your business requirements.

## 21. False conflicts and version scope

A single version across the entire document can cause conflicts even when two users edit independent fields:

- A edits name, version 7 → 8.
- B read version 7, intending to edit stock.
- B fails to match even though name and stock may be independent.

This can be a **false conflict** in the domain. Ways to reduce it:

1. Use update operators modifying only the needed fields instead of replacing the entire document.
2. Use **$inc** for counters and filter invariants against current values.
3. Split data regions with independent write lifecycles into separate documents.
4. Use a version for a sub-aggregate if there is a clear convention followed by all writers.
5. Rebase deltas onto the fresh snapshot when business rules allow.

Never reduce false conflicts by removing version checks altogether and accepting lost updates.

### 21.1. Version does not validate payloads

Even if expectedVersion matches, a client can still send a negative price, invalid quantity, or forbidden status transition.

Combine:

- **Authorization** to control who may update.
- **Business preconditions** in the filter to control current state.
- **Schema validation** to enforce types/structure.
- **Unique indexes** for uniqueness.
- **Version CAS** for snapshot freshness.
- **Transactions** when coordinating across multiple documents.

## 22. Production workflow

### Step 1 — Define invariants

List everything that must be guaranteed:

- Stock must remain non-negative.
- Never transition from CANCELLED to PACKED.
- A payment/reservation request must not be processed twice.
- Stale edit forms must not overwrite newer changes.
- Business keys must not duplicate.

Choose conditional updates, CAS, idempotency, unique indexes, or transactions depending on the invariant.

### Step 2 — Standardize schema

~~~javascript
{
  _id: "P-100",
  tenantId: "SHOP-A",
  priceCents: NumberLong(250000),
  stock: NumberInt(10),
  version: NumberLong(7),
  updatedAt: ISODate("2026-07-01T00:00:00Z")
}
~~~

Version must have a stable type, exist on all documents requiring OCC, and never be arbitrarily chosen by clients. Audit batch jobs and migrations as well.

### Step 3 — Read data with version

When a client opens a form, the API returns the editable fields and version from the same snapshot. If using a cache, define freshness guarantees and conflict resolution.

### Step 4 — Write with preconditions in the same operation

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7),
    status: "ACTIVE"
  },
  {
    $set: {
      priceCents: NumberLong(260000)
    },
    $inc: {
      version: NumberLong(1)
    },
    $currentDate: {
      updatedAt: true
    }
  }
);
~~~

Include in the filter every condition that another request could change when the update depends on it.

### Step 5 — Classify the result

**matchedCount=1:** the operation matched the filter.

**matchedCount=0:** may be a version conflict, unmet precondition, missing document, or out-of-scope tenant. Re-read in a controlled way if needed to classify; do not unconditionally retry the stale payload.

### Step 6 — Monitor metrics

| Metric | Meaning |
|---|---|
| **OCC conflict rate** | Rate of classified stale-version conflicts. |
| **Precondition failures** | Insufficient stock, invalid status, or domain rejections. |
| **Update latency p95/p99** | Contention on hot documents. |
| **Retry count** | Track retry storms or retrying non-retryable errors. |
| **Idempotency duplicates** | Count of previously processed requestIds. |
| **Write concern latency** | Acknowledgment/durability cost. |
| **WriteConflict/timeout errors** | Transaction health, network issues, and server load. |

### Step 7 — Test concurrent requests

Scenarios to include in the test suite:

1. Two clients read version 7 and write concurrently: only one CAS succeeds.
2. Version increments atomically with the change, with no half-applied state.
3. Two requests buying 7 from stock 10: only one request deducts.
4. Retrying the same business requestId does not double charge/double deduct.
5. Cannot modify a document belonging to another tenant even with known ID and version.
6. Batch jobs/migrations do not bypass version.
7. Spring Data @Version detects stale saves under acknowledged writes.

## 23. Indexes for conditional updates

For the operation:

~~~javascript
db.products.updateOne(
  {
    _id: "P-100",
    tenantId: "SHOP-A",
    version: NumberLong(7)
  },
  {
    $set: { name: "New Name" },
    $inc: { version: NumberLong(1) }
  }
);
~~~

MongoDB can normally use the **default unique index on _id** to locate the candidate document and then check tenant/version. You do not need to create a compound index **{_id:1,version:1}** on every collection just because you use OCC.

**Indexes help locate documents; CAS filters decide whether the write is permitted.** A version index alone does not prevent lost updates if the write command still filters only on _id.

If the application frequently updates by multiple fields without _id, for example:

~~~javascript
db.jobs.updateOne(
  {
    tenantId: "SHOP-A",
    queue: "EMAIL",
    status: "PENDING"
  },
  {
    $set: {
      status: "RUNNING"
    }
  }
);
~~~

then an index matching the tenant/queue/status query may be needed. Note that if multiple jobs match, **updateOne does not automatically pick FIFO**. If you want to claim jobs by priority or creation time, consider **findOneAndUpdate** with an explicit sort and matching index.

## 24. Common mistakes

### 24.1. Filtering only by _id and replacing with a stale snapshot

~~~javascript
db.products.replaceOne(
  { _id: "P-100" },
  staleDocumentFromClient
);
~~~

Can overwrite fields modified by another request. Use expectedVersion CAS and update only permitted fields.

### 24.2. Checking stock with find then deducting with update

The client-side check can become stale between the two commands. Put **stock >= requestedQty** into the update filter.

### 24.3. Incrementing version after the main write command

The application can crash between the two writes. Use **$set + $inc version** in a single update.

### 24.4. A service or migration bypassing version

Document-wide OCC stops reflecting all modifications. Standardize write paths and plan migrations carefully.

### 24.5. Automatically retrying a stale payload onto the new version

Defeats the purpose of OCC. Re-read, resolve conflicts per business rules, or notify the user.

### 24.6. Enabling upsert:true for CAS updates

~~~javascript
// Do not do this:
db.products.updateOne(
  {
    _id: "P-100",
    version: NumberLong(7)
  },
  {
    $set: { name: "New" },
    $inc: { version: 1 }
  },
  { upsert: true }
);
~~~

If the document already has a newer version, the filter fails to match. **upsert:true causes MongoDB to attempt inserting a new document**, resulting in duplicate key errors or unintended documents depending on filters/constraints. For CAS updates on existing documents, **do not enable upsert**; clearly separate create and update paths.

### 24.7. Using modifiedCount=0 as proof of conflict

When $set assigns the exact same value already stored, the document matches without being modified. Understand the difference between matchedCount and modifiedCount.

### 24.8. Using updatedAt without guaranteed resolution

Timestamps can collide due to millisecond resolution or type/precision conversion bugs. An explicit incrementing integer version is usually better suited for OCC.

### 24.9. Assuming @Version protects every raw driver update

@Version only assists framework-supported CRUD APIs. Custom driver updates, scripts, and migrations must still follow the versioning strategy.

### 24.10. Using unacknowledged writes

There is no reliable matchedCount result to detect stale versions.

### 24.11. Keeping a transaction open while a user fills out a form

Long transactions consume resources and are prone to timeouts/conflicts. Use a snapshot + conditional write on submit.

### 24.12. Confusing unique indexes with CAS

Unique indexes prevent duplicate keys across documents; version CAS prevents stale updates on an existing document. The two techniques do not replace each other.

### 24.13. Ignoring tenant and authorization

Version is not a credential. The API must authenticate and authorize callers rather than trusting client-supplied _id/version alone.

### 24.14. Failing to validate input quantity

Negative or oversized requestedQty values can break calculations or exceed BSON type bounds. Validate inputs before building filters/updates.

### 24.15. Inferring the first request succeeded from a single retry

When retrying a CAS with the old expectedVersion yields matchedCount=0, the first request might have succeeded—or another request might have won. Distinguishing them requires a consistent requestId/idempotency record.

## 25. Practice exercises

### Exercise 1 — Simulating a lost update

Starting from P-100, two clients both read priceCents=250000 and sequentially $set two different new prices filtering only by _id. Predict the final price if B writes after A. Why does MongoDB still guarantee atomicity?

### Exercise 2 — CAS by prior value

Write two updates with the same filter **priceCents:250000**: A wants 260000, B wants 240000. After one request writes successfully, what is the matchedCount of the other request?

### Exercise 3 — ABA problem

Suppose price changes along the sequence **250000 → 260000 → 250000**. Why might comparing only the old price fail to detect the change, whereas comparing version 7 against version 9 succeeds?

### Exercise 4 — Version-based CAS

Write an update on P-100 checking version=7, changing name, and incrementing version in the same operation. What happens if you run it again with expectedVersion=7?

### Exercise 5 — State transition

Starting from P-200 DRAFT, transition to ACTIVE only if status is still DRAFT. After it becomes ACTIVE, does the same command still match?

### Exercise 6 — Non-negative stock

Two requests each want to buy 7 items from stock=10. Write an updateOne using stock >= requestedQty and negative $inc. Explain why only one request can succeed if both are applied once.

### Exercise 7 — Request validation

If requestedQty = -5 or 0, what should reserveStock do? Explain why concurrency control does not replace validation.

### Exercise 8 — Classifying matchedCount=0

An update with filter:

~~~javascript
{
  _id: "P-100",
  tenantId: "SHOP-A",
  version: NumberLong(7),
  status: "ACTIVE"
}
~~~

returns matchedCount=0. List at least four possible causes and how to classify them safely without leaking another tenant's data.

### Exercise 9 — Versioned array update

For ORD-100, transition only line L1 from NEW to PACKED when version=3. Use **$elemMatch** in the main filter, **$[line]** and **arrayFilters** in the update, incrementing version to 4. Why are both condition layers required?

### Exercise 10 — Java Sync Driver

Write an updateName method accepting productId, tenantId, expectedVersion, and newName; validate name, use Filters.and, Updates.combine, and UpdateResult. Distinguish conflicts from validation errors.

### Exercise 11 — Spring Data @Version

Two entities both read version 7; copyA saves successfully, then copyB saves. Predict copyB's exception. Why must write concern be acknowledged?

### Exercise 12 — Retries

Request REQ-001 already deducted stock via $inc, but the response was lost. The client resends it as a new request while stock is still sufficient. What can happen? Design an idempotency key and consistent recording approach.

### Exercise 13 — HTTP If-Match

The API returns ETag **"v7"**, the client sends If-Match **"v7"**, yet MongoDB is now at version=8. Propose a **412** or **409** response per API contract. Why is checking ETag in the controller without putting version into the MongoDB filter still unsafe?

### Exercise 14 — Multi-document transaction

A workflow must deduct stock in products, insert into orders, and record in inventory_movements. Why does updateOne on product not guarantee all three changes? When should a transaction be used?

### Exercise 15 — Migrations and OCC

A batch job updates directly by _id without incrementing version. Describe how the UI could miss changes. Propose a version convention across all write paths.

## 26. Review questions

1. What is a lost update? Does it contradict MongoDB's document-level atomicity?
2. Why does filtering only by _id fail to detect stale snapshots?
3. How does a conditional update differ from findOne followed by a check in Java?
4. What are the limitations of CAS by old field value?
5. What is the ABA problem?
6. Which conditions and update operators are needed for a version CAS update?
7. Why must version increment in the same command as the business fields?
8. Does matchedCount=0 always mean a version conflict?
9. Does modifiedCount=0 always mean a failed update?
10. Why is $inc better than read-modify-write for counters?
11. What condition prevents stock deduction from making stock negative?
12. What advantage does findOneAndUpdate have over updateOne when the new document is needed?
13. Why is upsert:true inappropriate for stale-version CAS?
14. Why is an idempotency key needed for requests that may be replayed?
15. Why is updatedAt not always suitable as a version token?
16. What role does $elemMatch play in conditional updates on embedded arrays?
17. Is updateMany atomic across all multiple documents?
18. How does @Version in Spring Data help detect conflicts?
19. Does raw updateFirst always check expectedVersion automatically?
20. How does write concern affect optimistic locking detection?
21. Which race condition does a unique index solve that version CAS does not?
22. When is a transaction more appropriate than a single updateOne?

## 27. Summary

In MongoDB, **every write on a single document is atomic**, yet an application can still lose updates if it writes based on stale data without checking conditions at write time.

Three core techniques:

~~~text
1. Conditional state transition
   WHERE status = expectedStatus
   SET status = newStatus

2. Atomic arithmetic with invariant
   WHERE stock >= qty
   INC stock BY -qty

3. Optimistic locking
   WHERE version = expectedVersion
   SET new payload
   INC version BY 1
~~~

General CAS pattern:

~~~javascript
db.collection.updateOne(
  {
    _id: documentId,
    tenantId: authorizedTenantId,
    version: expectedVersion
    // Required business preconditions.
  },
  {
    $set: {
      // Only fields permitted to change.
    },
    $inc: {
      version: 1
    }
  }
);
~~~

Key takeaways:

1. **The filter is where you express conditions that must still hold at write time.**
2. **Data and version must change in the same atomic update.**
3. **Version is only reliable if all relevant write paths increment version.**
4. **matchedCount=0 must be classified**, not blindly retried with stale payloads.
5. **Retryable writes differ from application replay**; non-idempotent operations need duplicate-write protection.
6. **Spring Data @Version** assists supported CRUD APIs but does not replace checking raw updates and write concern.
7. **Single-document atomicity is not a multi-document transaction.**
8. **Authorization, validation, unique constraints, and metrics** must be designed alongside OCC for production correctness.

### Official references

- [MongoDB: Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — document-level atomicity and conditional updates.
- [db.collection.updateOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/) — filter/update/options and UpdateResult.
- [db.collection.findOneAndUpdate()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndUpdate/) — conditional update returning the document.
- [$inc Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/inc/) — atomic increment/decrement.
- [MongoDB Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — coordinating changes across multiple documents.
- [MongoDB Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — retrying logical writes.
- [MongoDB Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/) — uniqueness.
- [MongoDB Java Sync Driver: Update Documents](https://www.mongodb.com/docs/drivers/java/sync/current/crud/update-documents/) — Filters, Updates, UpdateResult.
- [Spring Data MongoDB: Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — @Version, save, optimistic locking exceptions, and write concern.

When writing an update operation, do not ask only **"what value do I want to write?"**—also ask **"what must still be true at the moment of writing?"**. Putting the answer into MongoDB's filter prevents overwriting stale snapshots, protects business invariants, and handles concurrent requests predictably.
