# Upsert, $setOnInsert, and Duplicate Key Control Under Concurrent Requests

## 1. Problem Statement: Receiving the Same Request Multiple Times

In real-world applications, a single request may reach MongoDB more than once even when a user triggers an action only once. For example:

- A client sends a create-order request, loses the connection before receiving the response, and automatically retries.
- A system consumes events from a queue with *at-least-once delivery*; the same message can be processed again.
- Two workers concurrently read a job not yet marked complete and both write data.
- Two HTTP requests from the same customer arrive nearly simultaneously.

Suppose an application receives orders from a partner system using the business key `{tenantId, externalOrderId}`. The requirement is **at most one document per key pair**, even when multiple workers write concurrently. If the document does not exist yet, create it; if it already exists, either leave it unchanged or update a permitted subset of fields depending on requirements.

This is the classic scenario for understanding three MongoDB mechanisms:

1. **Upsert**: if the filter matches an existing document, update it; if not, insert a new document.
2. **`$setOnInsert`**: sets fields only in the **insert** branch of an upsert, such as `createdAt`, `initialStatus`, or initial origin data that must stay immutable.
3. **Unique index**: enforces a constraint forbidding two documents with the same business key, even under concurrent requests.

The key takeaway is: **`upsert: true` does not turn an arbitrary filter into a uniqueness constraint**. Under concurrent requests, a unique index and an error-handling strategy are what guarantee correctness.

After this lesson, learners will be able to write `updateOne(..., { upsert: true })`, distinguish `$set` from `$setOnInsert`, choose unique keys, handle write contention, identify `E11000` duplicate key errors, and design safely repeatable requests.

## 2. How Does Upsert Work?

### 2.1. From Standard `updateOne` to Upsert

Command to update one document:

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  { $set: { status: "RECEIVED" } }
);
```

If no document matches the filter, the command above **inserts nothing**. Add `upsert: true` so MongoDB creates a document when no match is found:

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  { $set: { status: "RECEIVED" } },
  { upsert: true }
);
```

Conceptual logic flow:

```text
updateOne(filter, update, { upsert: true })
                    |
                    v
           Any matching document?
              /          \
            Yes           No
            |               |
            v               v
      UPDATE document    INSERT new document
            |               |
            +-------+-------+
                    |
                    v
             Return write result
```

In an update using operators like `$set`, when an insert is needed, MongoDB constructs the new document from eligible equality predicates in the filter and the update operators; if `_id` is missing, the server assigns an `_id`. Do not rely on complex filters to infer every field placed into the inserted document: explicitly declare the required data in the update payload.

`upsert` is also available in methods such as `replaceOne` and `findOneAndUpdate`. This lesson focuses on `updateOne` because it clearly expresses per-field changes and generally fits business-key workflows.

### 2.2. Reading the `updateOne` Result

Example result for a new insert:

```javascript
{
  acknowledged: true,
  matchedCount: 0,
  modifiedCount: 0,
  upsertedCount: 1,
  upsertedId: ObjectId("...")
}
```

A result that found a document and updated it typically shows `matchedCount: 1`, `upsertedCount: 0`. If the update made no value changes, `modifiedCount` can be `0` even when `matchedCount` is `1`.

| Result Field | Meaning |
| --- | --- |
| `acknowledged` | Whether the write was acknowledged per write concern |
| `matchedCount` | Number of documents matching the filter in the update branch, at most 1 for `updateOne` |
| `modifiedCount` | Number of documents actually modified; can be 0 if the update changed no values |
| `upsertedCount` | Number of documents inserted by upsert; typically 0 or 1 for `updateOne` |
| `upsertedId` | The `_id` of the newly inserted document, if any |

Do not interpret `modifiedCount: 0` as "operation failed": it may simply mean an existing document already had the exact target values. In unacknowledged write environments, some result fields may be unavailable; examples in this lesson assume acknowledged writes.

### 2.3. When Should and Shouldn't Upsert Be Used?

**Appropriate:** syncing current state by a unique key, creating default settings if absent, ingesting external records, creating processing records by idempotency key.

**Use caution:** business logic only allows "create" and must error if already present; updates must check previous state; non-repeatable money or quantity mutations; filters using only time/status ranges that do not identify a unique key.

In particular, never casually add `upsert: true` to a command meant to "update only while `PENDING`". If the document with that key has already transitioned to `ACTIVE`, a filter including `status: "PENDING"` will not match, and upsert may attempt to **insert a new document**, causing duplicate key errors or unintended records.

## 3. How Do `$set` and `$setOnInsert` Differ?

### 3.1. `$set` Applies to Both Branches

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  {
    $set: {
      status: "RECEIVED",
      lastSeenAt: new Date()
    }
  },
  { upsert: true }
);
```

If no document exists, MongoDB creates the document with these fields. If one already exists, `status` and `lastSeenAt` are overwritten. This is useful if business logic genuinely wants to synchronize the latest values, but **it can be dangerous for fields that should only be initialized once**.

For example: an order has already moved to `SHIPPED`, yet a "new order" message is replayed. If the worker uses `$set: { status: "RECEIVED" }` on every upsert, replay can regress the status from `SHIPPED` back to `RECEIVED`.

### 3.2. `$setOnInsert` Applies Only on Insert

```javascript
db.orders.updateOne(
  { tenantId: "TENANT-A", externalOrderId: "EXT-001" },
  {
    $setOnInsert: {
      status: "RECEIVED",
      createdAt: new Date(),
      sourceSystem: "partner-api"
    }
  },
  { upsert: true }
);
```

If absent, the new document receives `status`, `createdAt`, and `sourceSystem`. If already present, these fields **are not overwritten**.

| Case | `$set` | `$setOnInsert` |
| --- | --- | --- |
| Upsert finds no match and inserts document | Applied | Applied |
| Upsert finds match and updates document | Applied | Not applied |
| `updateOne` without upsert, document found | Applied | No effect |
| `updateOne` without upsert, not found | Nothing written | Nothing written |

For `$setOnInsert` to take effect, the operation must actually **enter the insert branch of an upsert**. It is not an operator for filling missing fields on an existing document.

### 3.3. Combining Both Operators for Controlled Updates

A common pattern:

```javascript
db.productSnapshots.updateOne(
  { source: "ERP", sourceId: "SKU-1001" },
  {
    $set: {
      displayName: "Keyboard",
      currentPriceCents: 125000,
      updatedAt: new Date()
    },
    $setOnInsert: {
      createdAt: new Date(),
      initialImportVersion: 1
    }
  },
  { upsert: true }
);
```

Here `displayName` and `currentPriceCents` are updated on every sync, while `createdAt` and `initialImportVersion` are written only upon creation. **Never place the same field path in both `$set` and `$setOnInsert`**, as that causes an update operator path conflict.

### 3.4. `$setOnInsert` Does Not Automatically Mean "Create-If-Absent" in Every Scenario

If the intent is **create-if-absent**, all initial-only fields can go under `$setOnInsert`. If the intent is **sync current data**, add `$set` for fields allowed to change. Deciding "write once" vs. "always update" must start from business rules:

- `createdAt`: usually written only once.
- `updatedAt`: updated when data actually changes according to business rules.
- State-machine `status`: should not be arbitrarily reset by replayable creation messages.
- `requestFingerprint` of an idempotency key: should be written only on first creation to verify subsequent retries.
- `lastSeenAt`: may be updated in sync models, though repeated runs will advance the timestamp.

## 4. Business Keys and Unique Indexes

### 4.1. `_id` Is Unique, but Insufficient for Another Business Key

MongoDB creates a unique index on `_id`. If each request generates a new `ObjectId` for `_id`, two requests handling the same order can create two distinct documents. A unique `_id` alone does not prevent this.

Example of two documents:

```javascript
{ _id: ObjectId("66a000000000000000000001"), tenantId: "A", externalOrderId: "ORD-1" }
{ _id: ObjectId("66a000000000000000000002"), tenantId: "A", externalOrderId: "ORD-1" }
```

Both have different `_id` values, so they satisfy the default index. If the business rule states one tenant cannot have two orders with the same external ID, you must model that exact constraint.

### 4.2. Creating a Scoped Unique Compound Index

```javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  {
    unique: true,
    name: "uniq_tenant_external_order"
  }
);
```

This index states that a given `(tenantId, externalOrderId)` pair may appear only once. Two different tenants can still use the same `externalOrderId`.

If an ID is only unique per source system, you may need `{ sourceSystem, tenantId, externalOrderId }`. If orders are scoped per batch/session, you may need `batchId`. **The key definition must match the exact business definition of "duplicate".**

### 4.3. Missing Fields, `null`, and Key Normalization

A unique index does not replace type checks or required-field validation. In a compound unique index, missing or `null` components still participate in index keys per MongoDB indexing rules; without application controls, documents missing fields can cause unexpected conflicts.

Use two layers:

1. **Application layer** validates `tenantId` and `externalOrderId`, rejects invalid input, and normalizes per policy.
2. **Schema validation** requires those fields to exist with exact BSON types; the unique index enforces uniqueness under concurrent writes.

If an email serves as a business key, decide whether `"User@Example.com"` and `"user@example.com"` represent the same identity. You can store a normalized `normalizedEmail` field under a unique index, or configure an appropriate collation. A unique index's collation directly defines uniqueness semantics; never change it arbitrarily once data exists.

### 4.4. Creating a Unique Index on an Existing Collection

If duplicate documents already exist, creating a unique index will fail. A sound workflow is:

- Define the canonical business key.
- Query for duplicates matching the exact key, types, and target collation.
- Resolve legacy duplicates per policy, preserving history or merging cleanly.
- Create the index and permit only compliant writers to continue.

Never "fix" an index creation failure by omitting `unique` if the system truly requires uniqueness.

## 5. Hands-On: Upsert Without Overwriting Existing Orders

### 5.1. Creating an Isolated Lab Environment

The following examples use only the `mongo_upsert_row121_lab` database and `orders_demo` collection owned by the learner. On a shared MongoDB instance, verify collection/index management permissions before running. In `mongosh`:

```javascript
const lab = db.getSiblingDB("mongo_upsert_row121_lab");
const orders = lab.getCollection("orders_demo");

// Unique identifier for each practice run.
const runId = "row121-" + new ObjectId().toHexString();
const tenantId = runId;

print("database=" + lab.getName());
print("runId=" + runId);

orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uniq_tenant_external_order" }
);
```

Using `tenantId = runId` in the demo keeps separate practice runs from colliding on the same business key. In production systems, `tenantId` must come from authenticated server context, never arbitrary client-supplied input.

### 5.2. Insert If Not Exists

```javascript
const key = {
  tenantId: tenantId,
  externalOrderId: "EXT-1001"
};

const first = orders.updateOne(
  key,
  {
    $setOnInsert: {
      runId: runId,
      sourceSystem: "partner-api",
      customerId: "C-001",
      amountCents: NumberLong("125000"),
      status: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(first);
printjson(orders.findOne(key));
```

In the insert branch, MongoDB creates the document from equality conditions in `key` and the fields provided by `$setOnInsert`. Example stored document:

```javascript
{
  _id: ObjectId("..."),
  tenantId: "row121-...",
  externalOrderId: "EXT-1001",
  runId: "row121-...",
  sourceSystem: "partner-api",
  customerId: "C-001",
  amountCents: NumberLong("125000"),
  status: "RECEIVED",
  createdAt: ISODate("...")
}
```

`NumberLong("125000")` explicitly specifies a 64-bit integer in the shell; for money, systems typically choose integers in the smallest currency unit or `Decimal128` depending on requirements.

### 5.3. Re-running the Same Request

Run again with the same `key`:

```javascript
const second = orders.updateOne(
  key,
  {
    $setOnInsert: {
      runId: runId,
      sourceSystem: "partner-api",
      customerId: "C-001",
      amountCents: NumberLong("125000"),
      status: "RECEIVED",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(second);
print("matchingDocuments=" + orders.countDocuments(key));
printjson(orders.findOne(key));
```

The first call typically returns `upsertedCount: 1`; the second returns `matchedCount: 1`, `upsertedCount: 0`, and `modifiedCount: 0`. Only **one document** exists for the key pair. The `createdAt` recorded initially is not altered by the repeat call.

Note: in the example, `new Date()` is still evaluated by the client on the second call, but because MongoDB takes the matched branch, that value **is not written** by `$setOnInsert`.

### 5.4. Demonstrating `$setOnInsert` Does Not Reset Status

Suppose a workflow transitions the order from `RECEIVED` to `APPROVED`:

```javascript
const approved = orders.updateOne(
  { ...key, status: "RECEIVED" },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    }
  }
);

printjson(approved);
```

Then replay the order-creation message:

```javascript
orders.updateOne(
  key,
  {
    $setOnInsert: {
      runId: runId,
      status: "RECEIVED",
      amountCents: NumberLong("125000"),
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(orders.findOne(key, {
  _id: 0,
  status: 1,
  approvedAt: 1,
  createdAt: 1
}));
```

`status` remains `APPROVED` because the upsert matched the existing document and `$setOnInsert` did not apply. This is the pattern of **initialize once, allow creation events to arrive repeatedly**.

## 6. Race Condition: Two Upserts Both Observe "Does Not Exist"

### 6.1. The Problem Without a Unique Index

Imagine two workers W1 and W2 concurrently processing the same external order:

```text
Time            Worker W1                     Worker W2
    |       updateOne(key, upsert)        updateOne(key, upsert)
    |       no document found             no document found
    |                |                           |
    |           attempt INSERT              attempt INSERT
    |                |                           |
    v          INSERT succeeds             INSERT succeeds

Result without an appropriate unique constraint:
two documents with the same business key can coexist.
```

Do not assume MongoDB locks the entire collection between the lookup and insert steps for every upsert. A write on **one document** is atomic, but that alone does not enforce uniqueness for a predicate when no document exists yet.

`upsert` means "update if present, insert if absent". A **unique index** is the mechanism that enforces "never allow two documents with the same key".

### 6.2. What Happens With a Unique Index?

If both workers concurrently upsert `{tenantId, externalOrderId}` with a matching unique index in place, the database cannot store two documents with the same key.

One of these outcomes occurs:

- One worker inserts successfully; the other sees the document now exists and executes the update branch.
- One worker inserts successfully; the other receives a **duplicate key** error when attempting to insert the same key.

MongoDB has specific conditions under which an upsert contending on a unique key can retry into the update branch (e.g., an equality filter matching the unique key and an update not altering key fields); do not assume **every** contending upsert silently turns into an update. A safe application path must handle success, no-op, and duplicate key errors.

### 6.3. Error Code `E11000`

When an operation violates a unique index, MongoDB typically returns error code **`11000`**, commonly displayed as `E11000 duplicate key error`.

It is crucial to identify **which unique constraint** was violated. A collection can have multiple unique indexes—for example, one on external order ID and another on transaction ID. Never catch every `11000` error, assume "this order already exists", and ignore the new payload.

Upon error, the application can look up the document by the **expected business key**, verify the content matches the request, and return the appropriate response. If no document matches that key or the data differs, preserve the error for investigation or return a conflict response.

## 7. Do Not Implement Upsert as "Find First, Insert Later"

The following pattern is prone to race conditions:

```javascript
// Pseudocode prone to race condition:
const existing = await orders.findOne(key);
if (!existing) {
  await orders.insertOne(newOrder);
}
```

Two requests can both read `null` and both call `insertOne`. Without a unique index, duplicate records may be stored. With a unique index, one insert is rejected and the application still has to handle the conflict.

Better suited for initialize-once workflows is:

```javascript
await orders.updateOne(
  key,
  { $setOnInsert: insertOnlyFields },
  { upsert: true }
);
```

However, a **unique index is still mandatory** to protect against concurrent requests. Calling `updateOne` does not replace an index.

For business requirements demanding "insert only; return conflict if already exists", use `insertOne` paired with a unique index rather than upsert. Choosing between `insertOne` and upsert depends on API semantics: "create once" and "ensure exists" are not identical.

## 8. Idempotency: Repeating Requests Without Repeating Effects

### 8.1. Business Definition

An **idempotent** operation means executing it multiple times with the same input produces the same essential business outcome as executing it once. For "ensure order exists", `$setOnInsert` plus a unique index prevents creating duplicate orders.

However, "not creating a second document" **does not mean every side effect is safe**. The following example is not idempotent on retry:

```javascript
db.accounts.updateOne(
  { _id: "ACCOUNT-1" },
  { $inc: { balanceCents: -50000 } }
);
```

Each successful execution deducts money again. If a request is replayed, the deduction can happen multiple times. Adding `upsert: true` does not solve this problem.

### 8.2. Idempotency Keys and Request Payloads

A common pattern is having the client or source system send an `idempotencyKey` identifying **one business operation**. The server stores this key alongside a **canonicalized payload fingerprint**.

Example:

```javascript
{
  tenantId: "TENANT-A",
  idempotencyKey: "PAYMENT-REQUEST-8db7",
  requestFingerprint: "sha256-of-canonical-fields",
  status: "PENDING",
  createdAt: ISODate("2026-11-14T03:00:00Z")
}
```

Two requests sharing the same `tenantId` and `idempotencyKey`:

- If the business payload matches, return the previously created/processed result.
- If the business payload differs, return a **conflict** to prevent reusing the same key for two different operations.

The fingerprint must be **computed server-side from canonicalized data** using consistent canonicalization rules; never trust an arbitrary client-supplied hash string. Avoid including volatile fields like `receivedAt` in the fingerprint if they are not part of business intent.

### 8.3. Do Not Overwrite Critical Data on Replay

For the same idempotency key, a replayed request must never:

- reset an already-progressed workflow status back to its initial state;
- overwrite the amount using a different payload;
- create an additional payment transaction;
- send duplicate emails/notifications with side effects;
- emit duplicate events to downstream consumers lacking deduplication.

`$setOnInsert` is useful for creating the origin record **once**. Side effects outside MongoDB require dedicated coordination such as idempotent consumers, a transactional outbox, or controlled processing-state tracking.

## 9. Node.js Example: Ensuring an Order Exists Under Contention

The snippet below illustrates a service function using the MongoDB Node.js driver. It assumes the collection already has a **unique index** on `{tenantId: 1, externalOrderId: 1}` and inputs have been validated and normalized server-side.

```javascript
// orderService.js - MongoDB Node.js driver
async function ensureOrder(orders, input) {
  const key = {
    tenantId: input.tenantId,
    externalOrderId: input.externalOrderId
  };

  // Fingerprint computed by the application layer from the canonicalized payload.
  const requestFingerprint = input.requestFingerprint;
  const insertOnly = {
    requestFingerprint,
    amountCents: input.amountCents,
    customerId: input.customerId,
    status: "RECEIVED",
    createdAt: new Date()
  };

  async function verifyExisting() {
    const existing = await orders.findOne(key);
    if (!existing) {
      return null;
    }
    if (existing.requestFingerprint !== requestFingerprint) {
      const conflict = new Error("ORDER_PAYLOAD_CONFLICT");
      conflict.code = "ORDER_PAYLOAD_CONFLICT";
      throw conflict;
    }
    return existing;
  }

  try {
    const result = await orders.updateOne(
      key,
      { $setOnInsert: insertOnly },
      { upsert: true }
    );

    // Fetch the existing document (newly inserted or already present).
    const order = await verifyExisting();
    if (!order) {
      throw new Error("ORDER_NOT_VISIBLE_AFTER_UPSERT");
    }

    return {
      order,
      inserted: result.upsertedCount === 1
    };
  } catch (err) {
    // A concurrent unique upsert can produce E11000.
    if (err?.code !== 11000) {
      throw err;
    }

    // Treat as a safe retry only if the exact key and payload match.
    const existing = await verifyExisting();
    if (!existing) {
      // May belong to another unique index; preserve error for handling.
      throw err;
    }

    return { order: existing, inserted: false };
  }
}
```

Several assumptions in this example should be stated explicitly:

1. `tenantId` and `externalOrderId` use consistent types and normalization, and the collection actually has a matching unique index on both fields.
2. `requestFingerprint` is computed from the fields defining the **business meaning of the order**. If a request arrives with the same key but a different fingerprint, do not overwrite; raise a conflict.
3. `amountCents` must be converted to the BSON numeric type matching the project's schema (e.g., `Long` or `Int32` in the driver) to avoid unintended mixed types.
4. The function reads back the document after writing; in replica sets with specific read/write policies, configure read preference, read concern, and write concern to match desired consistency.
5. If MongoDB returns a network error or an indeterminate write outcome, the application needs bounded retry policies and lookup by idempotency key. Never assume all errors can be retried infinitely.
6. The function does not include payments, emails, or event publishing; those side effects require dedicated idempotency designs.

Because `verifyExisting()` succeeds only when a document with **the exact key and matching fingerprint** is found, a uniqueness error from another index will not be masked as success when the target document does not exist.

### 9.1. Returning the Document Immediately After Upsert

Another option is `findOneAndUpdate()` with `upsert: true` and `returnDocument: "after"`:

```javascript
const order = await orders.findOneAndUpdate(
  { tenantId, externalOrderId },
  {
    $setOnInsert: {
      status: "RECEIVED",
      createdAt: new Date(),
      requestFingerprint
    }
  },
  {
    upsert: true,
    returnDocument: "after"
  }
);
```

Depending on the Node.js driver version and `includeResultMetadata` option, this returns either the document directly or an object containing metadata/result. Match the return handling to your driver version. **Using `findOneAndUpdate` does not eliminate the need for a unique index and contention handling.**

### 9.2. How Should HTTP/APIs Return Status Codes?

An "ensure exists" API might define:

| Scenario | Common Response |
| --- | --- |
| First-time creation | `201 Created`, returning ID or resource |
| Repeated request with same key and payload | `200 OK` or replay prior result per API contract |
| Same idempotency key with different payload | `409 Conflict` |
| Malformed input / missing fields | `400 Bad Request` |
| Unauthorized for tenant | `403 Forbidden` or status matching security policy |
| MongoDB temporarily unavailable | Appropriate system error with retry/observability mechanisms |

Never expose raw unique index details, stack traces, or connection strings to clients. Internal error logs can capture operation ID, index name, and error code while avoiding sensitive data leakage.

## 10. Dangerous Trap: Upsert with a Filter Not Matching the Unique Key

### 10.1. Accidentally Adding Status to the Filter

Suppose the unique index is `{ tenantId: 1, externalOrderId: 1 }` and the collection contains:

```javascript
{
  tenantId: "TENANT-A",
  externalOrderId: "EXT-001",
  status: "APPROVED"
}
```

A worker attempts:

```javascript
db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    externalOrderId: "EXT-001",
    status: "RECEIVED"
  },
  { $set: { status: "APPROVED" } },
  { upsert: true }
);
```

The existing document **does not match** because `status` is already `APPROVED`. With `upsert: true`, the server attempts to insert a new document with the same `tenantId` and `externalOrderId`; the unique index rejects it with `E11000`. Without a unique index, duplicate records would be created.

If the true intent is "transition only from `RECEIVED` to `APPROVED`", use a **conditional update without upsert**:

```javascript
const result = db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    externalOrderId: "EXT-001",
    status: "RECEIVED"
  },
  {
    $set: {
      status: "APPROVED",
      approvedAt: new Date()
    }
  }
);

printjson(result);
```

If `matchedCount: 0`, the application handles the case where the order already transitioned, does not exist, or is invalid. Never enable upsert to "work around" a non-matching conditional update.

### 10.2. Range-Only Filters Do Not Represent a Key

```javascript
// Not suitable for "at most one order per external ID".
db.orders.updateOne(
  {
    tenantId: "TENANT-A",
    createdAt: { $gte: ISODate("2026-11-14T00:00:00Z") }
  },
  { $set: { status: "RECEIVED" } },
  { upsert: true }
);
```

This filter does not identify a specific external order; it may update an unintended document or insert a document missing the business key. To avoid duplicates, upsert filters should use equality on the **complete unique key**. Business guards such as status, version, and timestamps belong in separate conditional write steps.

### 10.3. `updateMany` with Upsert Is Not a Solution for Duplicate Keys

`updateMany` updates all matching documents; when `upsert: true` is set and zero documents match, it inserts a single document. It is not suited for turning each source record into a distinct target document through a broad filter. For batch processing, issue one upsert per **individual business key** protected by a unique index.

## 11. Write Contention, Retries, and Transactions

### 11.1. Retries Must Respect Operation Semantics

A request may fail to receive a response even though the server committed the write. On retry:

- `$setOnInsert` on a unique key with a fingerprint can generally be used to **ensure a document exists**.
- `$set` assigning the same values can be safe for final field values, though it may still update `updatedAt` or trigger downstream hooks if designed that way.
- `$inc`, `$push`, point additions, or balance deductions can cause **repeated changes on each successful run**.
- External side effects outside MongoDB such as sending emails or calling payment gateways must be protected independently.

MongoDB drivers offer *retryable writes* under supported conditions and topologies. However, driver-level retries do not replace **business-level idempotency**, especially when a client/API resends a request as a new request.

### 11.2. Do Transactions Replace Unique Indexes?

**No.** Transactions coordinate changes across multiple documents/collections as one commit unit, but they do not enforce "at most one order per `externalOrderId`" if a unique index is missing.

For example, "create an order and write an outbox event" may require a transaction so both documents succeed or roll back together. A unique index on the order key is still needed to protect against concurrent requests; the application must handle duplicate/write-conflict errors and retry appropriately.

A workflow might look like:

```text
Receive request with idempotency key
              |
              v
      Normalize + validate
              |
              v
  Upsert by key + unique index
        /           |            \
   inserted       matched       E11000
       |             |             |
       v             v             v
  Process new   Verify        Look up exact key,
                fingerprint   verify fingerprint
       \             |             /
        \------------+------------/
                     |
                     v
           Return consistent result
```

When side effects write to other collections or external systems, extend the transaction/outbox design and explicitly track "processed" state.

### 11.3. Transactions Do Not Fix Broken Business Keys

If a service makes `externalOrderId` globally unique when IDs are actually only unique per `tenantId`, a global unique index will reject valid orders from other tenants. If a service skips normalization, `"ORD-1"` and `"ord-1"` may be treated as distinct keys when business rules consider them identical. Transactions cannot fix data modeling mistakes; define the key tuple and collation/normalization first.

## 12. Common Patterns to Consider

### 12.1. Creating Default Configuration If Absent

```javascript
db.userSettings.updateOne(
  { userId: ObjectId("66a000000000000000000001") },
  {
    $setOnInsert: {
      theme: "light",
      language: "en",
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

A unique index on `userId` is required so concurrent initialization requests never create two settings documents. A later request changing `theme` to `dark` will not be reset to `light` by repeated initialization upserts.

### 12.2. Synchronizing External Data

```javascript
db.products.updateOne(
  { sourceSystem: "ERP", sourceId: "SKU-1001" },
  {
    $set: {
      displayName: "Keyboard",
      priceCents: 125000,
      sourceVersion: 12,
      syncedAt: new Date()
    },
    $setOnInsert: {
      createdAt: new Date()
    }
  },
  { upsert: true }
);
```

The unique index protects `{sourceSystem, sourceId}`. Yet if messages arrive **out of order**, a version-11 update could overwrite version 12 if `$set` is used unconditionally as above. Out-of-order protection additionally requires version comparisons and conditional updates; do not confuse "no duplicate documents" with "no stale overwrites".

### 12.3. Soft Deletes and Re-Creation Requirements

Suppose documents have `deletedAt`. Business question: after soft-deleting an `externalOrderId`, can a new record be created with the same key?

- If **no**, keep a global unique index on the business key and restore/update the existing document per workflow.
- If **yes**, include a version/attempt number in the key, or use a partial unique index covering only active records.

Conceptual partial index example:

```javascript
db.contacts.createIndex(
  { tenantId: 1, normalizedEmail: 1 },
  {
    unique: true,
    partialFilterExpression: { active: true },
    name: "uniq_active_email_per_tenant"
  }
);
```

This index enforces uniqueness only for documents matching `active: true`. Records outside that filter can share keys; transitioning from inactive back to active is still subject to the unique constraint. Upserts must align with the active condition and lifecycle rules to avoid unexpected inserts. This example illustrates indexing strategy only; do not apply it to production collections without auditing existing data.

### 12.4. Unique Indexes in Sharded Environments

When a collection is sharded, unique index enforcement imposes requirements on index structure and the shard key depending on MongoDB version and topology. Before choosing a unique key for a distributed deployment, verify what constraints your target deployment supports. Never assume an index works identically in every topology merely because it runs on a local MongoDB instance.

## 13. Common Design Mistakes

| Practice | Problem | Solution |
| --- | --- | --- |
| Upsert by external ID without a unique index | Two concurrent requests can create two documents | Add unique index on complete business key |
| Relying only on auto-generated `_id` | Every retry generates a new `_id` | Use a stable idempotency or business key |
| Putting `createdAt` inside `$set` | Every replay alters the creation timestamp | Put initialization-only fields in `$setOnInsert` |
| Using `$set` to reset initial status | Progressed orders can be regressed | Use `$setOnInsert`, transition status with conditional updates |
| Including `status` in the upsert filter | Fails to match after status change, tries insert and hits E11000 | Separate "ensure exists" from "update-if-status" |
| Catching all `E11000` and returning success | Can mask conflicts on a different unique index | Look up by exact key, check fingerprint, classify errors |
| Infinite retries on network/duplicate errors | Amplifies load, risks duplicate side effects | Bounded retries with backoff and idempotency |
| Using `$inc` in replayable requests | Values increment/decrement multiple times | Model operations with unique IDs and once-only checks |
| Unique index at wrong scope | Blocks valid records or allows duplicates | Scope key by tenant, source, period, or version as required |
| Inconsistent key types and normalization | String/ObjectId mismatch; case differences create split keys | Normalize in app, enforce schema validation and deliberate collation |
| Creating unique index on dirty duplicate data | Index creation fails | Audit and clean legacy duplicates before migration |
| Expecting transactions alone to stop duplicates | Concurrent operations can still race on business keys | Unique index remains mandatory for uniqueness invariants |

## 14. Practice Lab: Controlling Write Contention

### 14.1. Conceptual Concurrent Calls on the Same Key

If your environment has Node.js and the MongoDB Node.js driver, you can use two promises to initialize the same key in a test database. The example assumes `orders` is a Node.js driver collection with the unique index already created:

```javascript
async function attemptCreate(label) {
  try {
    const result = await orders.updateOne(
      { tenantId: "RACE-TEST-121", externalOrderId: "EXT-RACE" },
      {
        $setOnInsert: {
          status: "RECEIVED",
          createdBy: label,
          createdAt: new Date()
        }
      },
      { upsert: true }
    );
    return { label, kind: "success", result };
  } catch (error) {
    return { label, kind: "error", code: error.code };
  }
}

const outcomes = await Promise.all([
  attemptCreate("worker-A"),
  attemptCreate("worker-B")
]);

console.log(outcomes);
```

Outcomes depend on execution timing: one call may insert, while the other updates/no-ops or receives `11000`. The unique index guarantees **no two documents with the same key pair** are persisted. Use a dedicated test key per run and inspect data before cleanup; replace `"RACE-TEST-121"` with a unique test tenant if multiple users share the database.

A single run failing to reproduce a race does not prove the system is race-free. Uniqueness is guaranteed by **database constraints and proper application handling of all valid outcomes**, not by whether a race appears on one machine.

### 14.2. Exercise: Predict the Outcome

Suppose the collection has unique index `{tenantId: 1, externalOrderId: 1}` and the document:

```javascript
{
  tenantId: "T1",
  externalOrderId: "O1",
  status: "SHIPPED",
  createdAt: ISODate("2026-11-01T01:00:00Z")
}
```

Analyze these three commands:

**A.**

```javascript
db.orders.updateOne(
  { tenantId: "T1", externalOrderId: "O1" },
  { $setOnInsert: { status: "RECEIVED", createdAt: new Date() } },
  { upsert: true }
);
```

**B.**

```javascript
db.orders.updateOne(
  { tenantId: "T1", externalOrderId: "O1" },
  { $set: { status: "RECEIVED" } },
  { upsert: true }
);
```

**C.**

```javascript
db.orders.updateOne(
  { tenantId: "T1", externalOrderId: "O1", status: "RECEIVED" },
  { $set: { status: "SHIPPED" } },
  { upsert: true }
);
```

Key points to explain: A does not reset `SHIPPED`; B can overwrite the status back to `RECEIVED`; C does not match because the current status is not `RECEIVED` and can attempt an insert that hits the unique index. For state transitions, choose conditional updates **without upsert**.

### 14.3. Inspecting Indexes and Document Counts by Key

In the `mongosh` session from section 5:

```javascript
printjson(orders.getIndexes());
print("matched=" + orders.countDocuments(key));
printjson(orders.findOne(key));
```

`getIndexes()` lists the collection's indexes. With the sample data and `key` undeleted, `matched` is expected to be `1`. Counts reflect the moment of querying; data can change if another writer is active.

## 15. Safe Lab Data Cleanup

To avoid accidental deletions, clean up only documents matching your practice run's `runId`. Inspect first:

```javascript
print("database=" + lab.getName());
print("collection=" + orders.getName());
print("runId=" + runId);

const preview = orders.find(
  { runId: runId },
  { _id: 1, tenantId: 1, externalOrderId: 1, runId: 1 }
).toArray();

printjson(preview);
print("matchedByRunId=" + orders.countDocuments({ runId: runId }));
```

If it matches **one** document with `externalOrderId: "EXT-1001"` created in section 5, delete using the full key and `runId`:

```javascript
const cleanupFilter = {
  tenantId: tenantId,
  externalOrderId: "EXT-1001",
  runId: runId
};

printjson(orders.findOne(cleanupFilter));
const deletion = orders.deleteOne(cleanupFilter);
printjson(deletion);
print("remaining=" + orders.countDocuments(cleanupFilter));
```

Normally `deletedCount: 1` and `remaining: 0`. If no document remains or the preview does not match expectations, **stop and verify the environment** rather than broadening the filter. The unique index stays on the collection after deleting the document; on shared environments, do not run `drop()` or `dropDatabase()` to clean up a lab exercise.

If you ran the Node.js concurrency test in section 14 on a truly isolated database, verify the exact test tenant and test records before deleting. Never delete by a generic key like `RACE-TEST-121` if it might collide with another user's data.

## 16. Self-Check Questions

1. What does `upsert: true` do when the filter matches an existing document? What happens when it does not?
2. Does `$setOnInsert` assign a value to a missing field on an existing document?
3. Why does the default unique `_id` not prevent two records with the same `externalOrderId` and different `_id` values?
4. How does a compound unique index `{tenantId: 1, externalOrderId: 1}` define duplicates differently from an index on `externalOrderId` alone?
5. When two upserts run concurrently, why must you still be prepared to handle `E11000` even with a unique index?
6. Why does adding `status: "PENDING"` to an upsert filter risk a duplicate key error after the document changes status?
7. What is the difference between "not creating a second document" and "idempotent across all side effects"?
8. Why should `$inc` not be used in client-replayable requests without deduplication?
9. When catching `11000`, what must you verify before returning a success response for a retried request?
10. If entities must be re-creatable after a soft delete, how should the unique key or index scope be defined?

**Core takeaway:** `upsert` decides **update or insert**, `$setOnInsert` protects fields **written only on first creation**, and a **unique index** prevents persisting two documents with the same business key. Under concurrent requests, applications still need to handle race outcomes, `11000` errors, and end-to-end idempotency; only combining these layers properly prevents duplicate data and unintended state overwrites.
