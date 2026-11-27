# Handling Partial Success, Selective Retries, and Preventing Duplicate Writes in MongoDB

## 1. Why Does Batch Writing Not Mean "All Succeed Together"?

Suppose an application imports 5,000 orders from a partner system into MongoDB. To minimize database round-trips, the application batches operations and calls `bulkWrite()`. Among them, one order has a duplicate key, one document fails schema validation, and the vast majority are valid.

Which conclusion is accurate?

- You cannot assume "the whole batch failed" merely because the API threw an error.
- You cannot assume "the whole batch succeeded" merely because some operations were persisted.
- You cannot blindly re-send the entire batch if earlier operations might create extra records, deduct balances, increment counters, or delete unintended data.

**Partial success** means some operations in a batch took effect while others failed or were not executed. This can happen in non-transactional bulk writes, especially upon errors like duplicate keys or document validation failures.

To handle this properly, the application must combine:

1. **Understanding `bulkWrite()` results**, especially the difference between `ordered: true` and `ordered: false`.
2. **Assigning stable identifiers to every task** to determine which succeeded, which failed, and which have uncertain outcomes.
3. **Classifying errors and retrying selectively**, rather than retrying every operation indiscriminately.
4. **Designing idempotent operations** so reprocessing a request produces no unintended side effects.
5. **Using unique indexes** to enforce uniqueness rules in MongoDB when multiple workers run concurrently.
6. **Reconciling outcomes after network or write concern errors**, because missing a response leaves write state indeterminate.

This lesson belongs to the **Deletion and Bulk Writes** section of MongoDB, so its principles apply across `insertOne`, `updateOne`, `deleteOne`, `updateMany`, and `deleteMany` inside a batch.

## 2. Core Mechanics of `bulkWrite()`

### 2.1. What Operations Can a Batch Contain?

At the collection level, `bulkWrite()` accepts an array of operation models:

```javascript
db.orders.bulkWrite([
  {
    insertOne: {
      document: {
        orderId: "O-001",
        status: "NEW"
      }
    }
  },
  {
    updateOne: {
      filter: { orderId: "O-002" },
      update: { $set: { status: "PAID" } }
    }
  },
  {
    deleteOne: {
      filter: { orderId: "O-003" }
    }
  }
], { ordered: true });
```

Common operation types:

| Operation model | Meaning | Retry considerations |
| --- | --- | --- |
| `insertOne` | Insert one document | If a fresh `_id` is generated each attempt, retries can create business duplicates |
| `updateOne` | Update at most one matching document | Depends on whether the update uses `$set`, `$inc`, `$push`, etc. |
| `updateMany` | Update all matching documents | Can affect many documents; hard to inspect granularly after failure |
| `replaceOne` | Replace one document; supports upsert | Needs a stable business key and payload validation |
| `deleteOne` | Delete at most one document | Retrying by fixed `_id` converges to the same final state |
| `deleteMany` | Delete all matching documents | Broad filters can catch newly arrived documents on retry |

`bulkWrite()` batches operations to reduce command overhead and unlock execution optimizations. However, **multiple operations in a bulk do not automatically form an atomic transaction**. Outside a transaction, MongoDB's standard atomicity applies at the **single-document** level per write operation, even when updating multiple fields of that document.

### 2.2. How Do `ordered: true` and `ordered: false` Differ?

Suppose a batch contains:

```text
Input position:   0        1          2        3
Operation:        A        B          C        D
Status:           good   duplicate    good     good
```

**`ordered: true`** (default): MongoDB executes in the given order and halts batch processing at the first **write error**. If `A` succeeds and `B` fails, operations `C` and `D` behind `B` in the batch are normally never executed.

**`ordered: false`**: MongoDB attempts to continue remaining operations even when one fails. `A`, `C`, and `D` can succeed while `B` fails. The server may reorder execution for optimization; **never rely on actual execution order** in an unordered bulk for business rules.

| Characteristic | `ordered: true` | `ordered: false` |
| --- | --- | --- |
| When an operation hits a write error | Stops at the first error in the ordered stream | Attempts remaining operations |
| Guarantees input order | Yes, per ordered semantics | No |
| Best fit | Operations requiring sequential order; easy to identify unattempted tail | Relatively independent operations |
| Error handling | Account for executed prefix and unattempted tail | Inspect per-operation errors and reconcile remaining items |
| Guarantees whole-batch atomicity? | No | No |

**Important:** `ordered: false` does not mean "regardless of any error, the server will still run every operation." Network failures, server interruptions, command-wide errors, or write concern failures can leave outcomes uncertain. Per-write error info is reliable only to the extent reported by the server/driver.

### 2.3. Large Bulks Can Be Split Internally by the Driver

Drivers and servers impose limits on operation counts and message sizes. When the array is large, the driver splits it into smaller batches for transmission. Therefore, never assume a large `bulkWrite()` call corresponds to a single network message or a single commit unit.

If an error occurs after earlier sub-batches executed, the call can produce partial results. When logging or resuming from checkpoints, preserve **the operation's index in the original input list** along with its stable business key. Drivers map reported error indexes back to input positions, though the exact error object structure must be checked against your driver version's API.

## 3. Reading Results: What Happened vs. What Is Unknown?

### 3.1. Result When a Bulk Has Zero Errors

A `BulkWriteResult` typically holds summary counters:

```javascript
{
  acknowledged: true,
  insertedCount: 3,
  matchedCount: 2,
  modifiedCount: 1,
  deletedCount: 1,
  upsertedCount: 1,
  insertedIds: { /* input index -> _id */ },
  upsertedIds: { /* input index -> _id */ }
}
```

This is an **illustrative result shape**, not a fixed output for every batch. Fields vary by operation types and driver APIs.

| Field | Interpretation |
| --- | --- |
| `insertedCount` | Number of documents inserted by insert operations per reported result |
| `matchedCount` | Number of documents matched by update/replace operations |
| `modifiedCount` | Number of documents actually modified; can be less than `matchedCount` |
| `deletedCount` | Number of documents deleted by delete operations |
| `upsertedCount` | Number of documents inserted via upserts |
| `insertedIds`, `upsertedIds` | IDs for inserted/upserted operations, if provided by the API |

Aggregate numbers are **not a per-item status table**. For example, `matchedCount: 1` does not tell you **which order** was updated if the batch held many operations. If item-level reconciliation is required, retain the input list and each item's identifier.

### 3.2. Distinguishing Three Error Classes

| Error class | Examples | What you can and cannot conclude |
| --- | --- | --- |
| **Per-operation write error** | `E11000` duplicate key, document validation `121` | You can identify which operation was rejected via index; other operations may have succeeded |
| **Write concern error** | Failed to reach required acknowledgment, e.g., replication timeout | Writes may already have applied on some nodes; durability/acknowledgment guarantee is unconfirmed |
| **Command-wide network/server/timeout error** | Connection closed, server selection timeout, dropped before response | You may not know which operations ran on the server; state is **indeterminate** |

Duplicate key errors typically carry MongoDB code **`11000`**; document validation failures typically carry **`121`**. These errors generally will not resolve by re-sending the exact same invalid payload.

**Write concern errors differ from write errors:** an operation may already have modified data on the primary without meeting the requested acknowledgment level (such as `w: "majority"` within timeout). If your system requires majority-acknowledged commits, later reading the document on the primary does not retroactively prove the original write satisfied that durability guarantee.

### 3.3. Why "Exception Thrown = Nothing Written" Is Wrong

A driver can throw `MongoBulkWriteError` while attaching:

- counts of operations that succeeded;
- write errors keyed by operation **index**;
- write concern error details, if any.

Example on an unordered batch of three `insertOne` operations:

```text
operation[0] A -> inserted
operation[1] B -> E11000
operation[2] C -> inserted

bulkWrite(...) -> throws error due to B
database        -> still contains A and C
```

Consequently, never write logic like "if `bulkWrite` throws, retry the whole `insertOne` array with fresh ObjectIds." That can duplicate `A` and `C` or trigger additional key collisions.

## 4. Hands-On: Observing Partial Success

### 4.1. Preparing a Test Collection and Scoped Key

The examples below use `mongosh` in a dedicated database `mongo_bulk_row135_lab`. Run only in an authorized lab environment. In the shell session:

```javascript
const lab = db.getSiblingDB("mongo_bulk_row135_lab");
const orders = lab.getCollection("orders_demo");

const runId = "row135-" + new ObjectId().toHexString();
print("database=" + lab.getName());
print("runId=" + runId);

// Enforce that a sourceId appears at most once per runId.
orders.createIndex(
  { runId: 1, sourceId: 1 },
  { unique: true, name: "uniq_run_source" }
);

// Seed record B to intentionally trigger a duplicate error.
orders.insertOne({
  runId,
  sourceId: "B",
  payloadDigest: "digest-original-B",
  status: "EXISTING",
  createdAt: new Date()
});
```

`runId` isolates data for each practice run. In real systems, a stable business key is typically `{ tenantId, externalId }`, whereas `runId` is purely an exercise marker.

### 4.2. Running an Unordered Bulk with an Error

```javascript
const operations = [
  {
    insertOne: {
      document: {
        runId,
        sourceId: "A",
        payloadDigest: "digest-A",
        status: "NEW"
      }
    }
  },
  {
    insertOne: {
      document: {
        runId,
        sourceId: "B",
        payloadDigest: "digest-new-B",
        status: "NEW"
      }
    }
  },
  {
    insertOne: {
      document: {
        runId,
        sourceId: "C",
        payloadDigest: "digest-C",
        status: "NEW"
      }
    }
  }
];

try {
  const result = orders.bulkWrite(operations, { ordered: false });
  printjson(result);
} catch (error) {
  print("Bulk error: " + error.message);
  // How writeErrors/result are exposed depends on the mongosh/driver version;
  // print the full error in the lab environment to observe it.
  printjson(error);
}
```

The operation at **index 1** attempts to insert `B`, which already exists under the unique index, so it is rejected. With unordered bulk and a healthy server, `A` and `C` still succeed. `B`'s failure does not roll back `A` or `C`.

After running, verify actual state:

```javascript
printjson(
  orders.find(
    { runId },
    { _id: 0, runId: 0, sourceId: 1, payloadDigest: 1, status: 1 }
  ).sort({ sourceId: 1 }).toArray()
);
```

Normally the output contains `A`, the original `B`, and `C`. `B` retains `payloadDigest: "digest-original-B"`, not the rejected operation's payload. That illustrates the difference between **an operation succeeding** and **an operation being blocked to protect data integrity**.

### 4.3. Switching to `ordered: true`

If you run a fresh trial with a new `runId`, pre-seed `B`, and send `A, B, C` with `ordered: true`, MongoDB stops at `B`. `A` is inserted; `C` sits after the error and **is not executed** in the ordered flow.

Never reuse a `runId` that already contains `A`/`C` from the unordered run to test ordered behavior: the starting dataset would differ, shifting where errors occur.

## 5. Designing a "Stable Identifier" for Each Operation

### 5.1. Business Identity Differs from Array Index

An input array might have an item at `operations[2]` on the first attempt, yet after stripping completed items, that same item becomes `operations[0]` on retry. Therefore, **array index is only for correlating errors within a single call**, never a durable business identifier.

Each import record should carry its own key, for example:

```javascript
{
  tenantId: "TENANT-A",
  sourceSystem: "ERP",
  externalId: "ORD-2026-001",
  payloadDigest: "sha256-of-canonical-business-fields",
  payload: {
    amountCents: 125000,
    currency: "VND"
  }
}
```

The business key can be:

```text
(tenantId, sourceSystem, externalId)
```

`payloadDigest` is a fingerprint of the canonicalized business fields; it detects same-key requests with differing payloads. If updates carry a **version** or effective timestamp, enforce version rules per domain semantics rather than treating every differing payload as a valid new creation.

### 5.2. Tracking a Task List Before Sending

A checkpoint or job-log structure:

```text
Batch: IMPORT-2026-11-14-01

Item key                             State
-------------------------------------------------
TENANT-A / ERP / ORD-001             PENDING
TENANT-A / ERP / ORD-002             PENDING
TENANT-A / ERP / ORD-003             PENDING
```

Application-layer states you can use:

| State | Meaning | Next action |
| --- | --- | --- |
| `PENDING` | Not yet sent or queued for sending | Include in batch |
| `CONFIRMED` | Domain effect confirmed as required | Do not re-send |
| `RETRYABLE` | Transient error; operation can be safely retried | Retry with cap and backoff |
| `CONFLICT` | Same key but different content or rule mismatch | Halt, reconcile, or escalate to operator |
| `INVALID` | Schema violation, bad type, or missing field | Fix source data; do not retry raw payload |
| `UNKNOWN` | Exact write outcome is unknown | Reconcile by key/ID, then decide |

A state like `CONFIRMED` must reflect **the durability guarantee your application requires**. Seeing the document on the primary after a `wtimeout` does not guarantee it achieved the majority acknowledgment your policy demands.

### 5.3. Deduplicating Within the Input Batch Itself

Before building `bulkWrite`, the application should detect **two items sharing the same key within one batch**. If both key and fingerprint match, collapse them per policy. If the key matches but payloads differ, resolve ordering/versioning or flag a conflict.

Never depend on MongoDB to "pick the right record" when an unordered batch contains two conflicting upserts for the same key: since order is not guaranteed, the winning value depends on execution timing.

## 6. Idempotency: Retries Must Not Repeat Business Side Effects

### 6.1. Distinguishing Operation Types

An operation is **idempotent** when repeating it with the same data and key yields the same final business state as running it once.

| Operation | Safe to repeat? | Crucial condition |
| --- | --- | --- |
| `$set: { status: "READY" }` | Usually yes for terminal/target values | Must not regress state machine; watch `updatedAt` and side effects |
| `$setOnInsert` in upsert by unique key | Usually good for create-once | Unique index, stable key, verify existing payload |
| `insertOne` with fixed `_id` | Prevents duplicate by `_id` | On duplicate, compare existing record; never assume every error means success |
| `$inc: { stock: -1 }` | No | Each successful run decrements again |
| `$push: { events: event }` | Not by default | Each successful run can append another copy |
| `$addToSet` with the same value | Avoids duplicate array elements | Does not replace a unique index for business records |
| `deleteOne` by specific `_id` | Usually converges to "document absent" | Retry gives `deletedCount: 0`; does not imply the first call didn't delete it |
| `deleteMany` with broad criteria | Use caution | Newly arrived items can match on retry |

Non-idempotent example:

```javascript
db.accounts.updateOne(
  { _id: "ACC-01" },
  { $inc: { balanceCents: -50000 } }
);
```

If the client times out and retries and both writes succeed, the account is debited twice. A unique index on `accounts._id` **offers zero protection** against repeating `$inc` on the same document.

When business rules require "debit once for transaction X," maintain a transaction/operation ledger with a unique ID, deduplication checks, and coordinated balance updates—potentially requiring a multi-document transaction.

### 6.2. Using `$setOnInsert` with Upsert and Unique Indexes

For order imports, enforce one document per key:

```javascript
// Create the unique index once on the test collection.
orders.createIndex(
  { runId: 1, sourceId: 1 },
  { unique: true, name: "uniq_run_source" }
);

// A new item for this practice run.
const newKey = {
  runId,
  sourceId: "D"
};

const importResult = orders.updateOne(
  newKey,
  {
    $setOnInsert: {
      payloadDigest: "digest-D",
      status: "NEW",
      createdAt: new Date()
    }
  },
  { upsert: true }
);

printjson(importResult);
```

If `D` does not exist, the server inserts it. If `D` already exists, `$setOnInsert` leaves the existing document untouched. The **unique index** ensures a `(runId, sourceId)` pair cannot be inserted twice, even if two workers issue concurrent upserts.

Without a unique index, two concurrent upserts both seeing no document can both insert depending on scheduling. `upsert: true` alone is not equivalent to a uniqueness constraint.

### 6.3. On Key Collision, Compare Contents

Suppose a record already exists:

```javascript
{
  runId: "row135-abc",
  sourceId: "D",
  payloadDigest: "digest-D",
  status: "PROCESSED"
}
```

A repeated request with the same key and same `payloadDigest` can be treated as the same input already accepted. If the new payload has a different digest, returning "success" hides a data conflict. The workflow should:

1. Look up the existing document by the exact unique key.
2. Compare `payloadDigest` or business version and all fields governing request meaning.
3. If identical, record it as processed or resume any incomplete downstream steps per the state machine.
4. If different, report `CONFLICT` or apply pre-designed versioned update rules.

**Note:** compute hashes from a canonical representation of significant business fields. Never accept an arbitrary client-supplied hash and blindly trust two requests are identical. Exclude request arrival timestamps from the hash if they do not alter business semantics.

## 7. Selective Retries: Classify Errors Before Retrying

### 7.1. Not Every Error Should Be Retried

| Outcome | Typical cause | Handling |
| --- | --- | --- |
| `11000` duplicate key | Item already exists or hit another unique index | Look up by key and compare payload; confirm or flag conflict |
| `121` document validation | Missing field, wrong BSON type, invalid enum | Fix data/contract; send to error queue, do not retry raw payload |
| Authorization error | Account lacks write/delete permissions | Fix config or permissions properly; do not retry continuously |
| Recognized transient error | Primary election, brief network blip, transient error label | Bounded retry if operation is idempotent and conditions permit |
| Write concern timeout/error | May have written without meeting acknowledgment level | Mark `UNKNOWN`, reconcile per read/write concern policy |
| Disconnected before response | Unknown which operations executed | Reconcile by key; re-send only when safe |
| Filter unmatched on `updateOne` | Document changed state or does not exist | Check domain rules; do not silently switch to upsert |

Rule of thumb: **permanent data errors require fixing data**, **conflicts require reconciliation**, **transient errors merit bounded retries**, and **uncertain outcomes require reconciliation**.

### 7.2. Mapping Errors Back to Input Indexes

For an unordered batch with clear write error reporting, `writeErrors` typically pinpoints the failing operation's position in the input array. Illustrative example:

```text
Input:
 index 0 -> externalId A
 index 1 -> externalId B
 index 2 -> externalId C
 index 3 -> externalId D

writeErrors:
 { index: 1, code: 11000 }
 { index: 3, code: 121 }
```

Use the `index → business key` map for **that specific call**:

```text
B -> duplicate: need to look up existing record and reconcile
D -> invalid: route to data-repair queue
A, C -> no per-item errors reported
```

Having no write error for `A` and `C` is **not enough** to assert durability/acknowledgment requirements were satisfied if the overall call also hit a write concern error or incomplete result. With a fully acknowledged response, you can use the bulk result to advance progress; when item-level guarantees are critical, verify further via keys or processing logs.

With `ordered: true`, if `B` at index 1 fails, `C` and `D` behind it were never sent/executed in the ordered stream. They are not "succeeded because absent from `writeErrors`." When planning retries, distinguish **failed** from **not attempted**.

### 7.3. Selective Retry Workflow

```text
Save snapshot of input list + business key + fingerprint
                       |
                       v
                   Send bulk
                       |
         +-------------+--------------+
         |             |              |
         v             v              v
   Full ack     Per-item write   Uncertain result
                  errors           / write concern
         |             |              |
         v             v              v
   Mark as       Map by index     UNKNOWN, reconcile
   processed     and classify     by key
                       |              |
              +--------+----+         |
              |             |         |
              v             v         v
        NON-RETRYABLE   RETRYABLE  Verify state
        -> fix/conflict -> backoff then decide retry
              |             |         |
              +-------------+---------+
                            |
                            v
                     Save checkpoint
```

**Never convert an `E11000` error into a retry insert with a new `_id`.** If the record already exists under its business key, such a retry fails to solve the error and masks modeling bugs.

## 8. Node.js Example: Building a Safely Repeatable Bulk

The following example uses the MongoDB Node.js driver. It demonstrates **create-only-if-absent imports**, keeping the first record for a given external ID without overwriting domain state. Assumptions:

- `tenantId` is resolved server-side from a trusted context.
- `externalId`, `payloadDigest`, and `amountCents` are validated and normalized.
- The collection has unique index `{ tenantId: 1, externalId: 1 }`.
- Every item in the batch has a distinct external ID; intra-batch duplicates are rejected upfront.

### 8.1. Building the Operation List

```javascript
function buildImportOperations(tenantId, items, acceptedAt) {
  const seen = new Set();

  return items.map((item) => {
    if (seen.has(item.externalId)) {
      throw new Error("Duplicate externalId inside input batch");
    }
    seen.add(item.externalId);

    return {
      updateOne: {
        filter: {
          tenantId,
          externalId: item.externalId
        },
        update: {
          $setOnInsert: {
            payloadDigest: item.payloadDigest,
            amountCents: item.amountCents,
            status: "RECEIVED",
            createdAt: acceptedAt
          }
        },
        upsert: true
      }
    };
  });
}
```

Here `acceptedAt` is generated once per batch and passed in, rather than shifting every time operations are rebuilt. For create-only semantics, `$setOnInsert` prevents retries from altering existing documents. If updates must also sync, add `$set` for allowed fields and an explicit versioning rule.

Create the index once during setup/migration:

```javascript
await db.collection("importOrders").createIndex(
  { tenantId: 1, externalId: 1 },
  { unique: true, name: "uniq_tenant_external" }
);
```

### 8.2. Sending an Unordered Bulk and Preserving Technical Error Context

```javascript
async function sendImportBulk(collection, tenantId, items, acceptedAt) {
  const operations = buildImportOperations(tenantId, items, acceptedAt);

  try {
    const result = await collection.bulkWrite(
      operations,
      { ordered: false, writeConcern: { w: "majority" } }
    );
    return { result, error: null, operations };
  } catch (error) {
    // Bulk may have partially written; keep error for reconciliation.
    return { result: error?.result ?? null, error, operations };
  }
}
```

The MongoDB driver's `error.writeErrors` normally contains errors mapped to input indexes; `error.result` may hold partial results. Exact structures, fields, and metadata must be verified for your driver version. This helper **does not draw per-item conclusions yet**; it retains enough context for the reconciliation step to decide.

For batches containing `updateMany` or `deleteMany`, driver retryable-write behavior differs from single-document operations. Never assume every bulk is automatically retried by the driver; inspect the operations in the batch and cluster configuration.

### 8.3. Reconciling by Business Key

After an uncertain failure or per-item error, query **the persisted state**. Example for a single-tenant batch:

```javascript
async function reconcileImport(collection, tenantId, items) {
  const ids = items.map((item) => item.externalId);

  const docs = await collection
    .find({
      tenantId,
      externalId: { $in: ids }
    })
    .project({
      _id: 0,
      externalId: 1,
      payloadDigest: 1
    })
    .toArray();

  const byId = new Map(
    docs.map((doc) => [doc.externalId, doc])
  );

  return items.map((item) => {
    const doc = byId.get(item.externalId);
    if (!doc) {
      return {
        externalId: item.externalId,
        state: "UNKNOWN_OR_MISSING"
      };
    }
    if (doc.payloadDigest !== item.payloadDigest) {
      return {
        externalId: item.externalId,
        state: "CONFLICT"
      };
    }
    return {
      externalId: item.externalId,
      state: "PRESENT_WITH_EXPECTED_PAYLOAD"
    };
  });
}
```

How to read these outcomes accurately:

- `PRESENT_WITH_EXPECTED_PAYLOAD` confirms a document with the matching key and fingerprint exists **at read time**. Useful, yet if the bulk suffered a write concern error, reading it alone does not prove the requested durability/acknowledgment level was met.
- `CONFLICT` reveals the same key holds a different payload; investigate or apply version policy rather than overwriting blindly.
- `UNKNOWN_OR_MISSING` does not prove the operation never ran—interruptions, deletions, or concurrent updates could be involved; determine the cause and retry policy.

For consistent reconciliation, choose read preference, read concern, and write concern aligned with your system guarantees. In small apps, primary reads are a good starting point; where majority confirmation is mandatory, do not equate "readable on primary" with a majority-acknowledged write.

### 8.4. Parsing `writeErrors` and Building a Retry List

The pattern below maps errors back to items **when the driver returns indexed write errors**:

```javascript
function classifyReportedWriteErrors(error, items) {
  const writeErrors = error?.writeErrors ?? [];
  const normalized = writeErrors instanceof Map
    ? [...writeErrors.values()]
    : writeErrors;

  return normalized.map((writeError) => {
    const item = items[writeError.index];
    const code = writeError.code;

    return {
      index: writeError.index,
      externalId: item?.externalId,
      code,
      decision:
        code === 11000 ? "RECONCILE_DUPLICATE" :
        code === 121 ? "INVALID_INPUT" :
        "INVESTIGATE_BEFORE_RETRY"
    };
  });
}
```

This function classifies only **reported write errors**; it does not declare every operation absent from the error array successful. Unfamiliar error codes may be transient or permanent; understand their cause before queueing retries.

For transient errors on idempotent operations, build **a new batch containing only items needing retry**. The new batch has new input indexes; continue using external ID and digest as reconciliation keys rather than reusing old array indexes as business identities.

### 8.5. Why Avoid Putting `$inc` or `$push` in This Retry Pattern?

If one item in the bulk applied but the response was lost, retrying `$inc` or `$push` repeats the effect. An import batch ensuring existence via `$setOnInsert` is vastly easier to replay safely.

For cumulative updates, solutions generally require **a unique operation ID and processed-state tracking**. For example, an inventory deduction must be tied to an order/transaction ID, recorded once, and coordinated with the stock update—possibly via a transaction or an equivalent conditional document design.

## 9. Handling Specific Error Scenarios

### 9.1. Duplicate Key `11000`

**Symptom:** the server rejects an insert or upsert due to a unique index violation.

Questions to answer:

1. Which index reported the duplicate? Is it the index protecting the expected business key?
2. Does the document at that key exist and belong to the right tenant?
3. Do `payloadDigest` and version match the incoming request?
4. If they differ, does policy dictate flagging a conflict, merging, or updating by version?

If key, payload, and "ensure exists" semantics all align, you can mark the item accepted. If payloads differ, never treat the duplicate error as success. Avoid logging full sensitive documents.

### 9.2. Document Validation `121`

Suppose the schema requires `amountCents` to be a non-negative BSON integer, but the import sends `"125000"` as a string. MongoDB rejects the document for failing validation. Re-sending the same string will not fix it.

Proper actions:

- record the failing item in an error queue/report with source reference and reason;
- fix the parser or normalization in the application;
- re-submit only after the payload conforms to the schema contract;
- never disable validators casually just to push an import through.

### 9.3. Network Timeout or Connection Reset

When the client does not know how many operations the server received or wrote, **you cannot treat all of them as failed**. Mark them uncertain, query by key, check fingerprints, and retry with idempotent operations if needed.

MongoDB drivers support retryable writes under certain conditions, but that does not replace business-level idempotency. Clients/APIs can spawn new requests after timeouts, queues can redeliver messages, and workers can crash between writing data and saving checkpoints.

### 9.4. Write Concern Timeout

An operation may already have applied locally without reaching `w: "majority"` before timeout. Never interpret `writeConcernError` as "MongoDB rolled everything back." Manage uncertain states against your desired guarantee, monitor topology health, and reconcile before declaring completion.

### 9.5. Ordered Bulk Stopping at Operation N

If an ordered batch hits a write error at index `N`, earlier operations succeeded, operation `N` failed, and the tail after `N` was never executed. When error reporting is clear, you can build a new batch from the unattempted tail after handling the failing operation.

Never re-send the whole batch using non-idempotent operations. If a command-wide error or connection drop occurred, do not blindly assume "the tail did not run"; reconcile actual state first.

## 10. Bulk Deletion: Safe Retries Start with Delete Scope

### 10.1. Distinguishing `deleteOne` and `deleteMany`

Suppose you want to clean up 100 test documents from a known ID list. A batch of 100 `deleteOne` operations using fixed `_id`s has a helpful property:

- Once deleted on the first call, retrying the same filter finds nothing; the "document absent" end state holds.
- `deletedCount: 0` on a retry **does not prove** the first call failed to delete it: it may simply have been deleted already.
- If auditing requires "deleted by this exact job," maintain an operation log or job ID rather than relying solely on the current call's `deletedCount`.

Conversely:

```javascript
db.events.deleteMany({
  createdAt: { $lt: new Date() }
});
```

Here the filter shifts on every run because `new Date()` advances the threshold. A retry can delete **newer documents** outside the original scope. This illustrates why retrying a "broad-filter delete" may violate the original business intent.

### 10.2. Snapshotting the Target List Before Deleting

For test data, you can fetch concrete `_id` values first and build a `deleteOne` batch targeting those IDs:

```javascript
// Use only in the lab database, with your own runId.
const targetIds = orders.find(
  { runId },
  { _id: 1 }
).toArray().map((doc) => doc._id);

const deleteOperations = targetIds.map((id) => ({
  deleteOne: {
    filter: { _id: id, runId }
  }
}));

print("candidateCount=" + deleteOperations.length);
```

Benefit: each delete targets one pre-inspected `_id` paired with `runId` confirming test-data ownership. Never run bulk deletes in a shared environment without reviewing the candidate list first.

Once verified as **your own test data**:

```javascript
if (deleteOperations.length > 0) {
  try {
    printjson(orders.bulkWrite(
      deleteOperations,
      { ordered: false }
    ));
  } catch (error) {
    print("Bulk delete error: " + error.message);
    printjson(error);
  }
}

// Reconcile IDs from the snapshot list.
print("remainingFromSnapshot=" + orders.countDocuments({
  _id: { $in: targetIds },
  runId
}));
```

If any ID from the snapshot remains, inspect its state and error reason before retrying **only the remaining IDs**. Never swap `_id` for a wide filter like `{}` or `deleteMany({})` just to "clear everything out."

**Model limitation:** if a document is deleted and another process recreates a document with the same `_id`, retrying a delete by `_id` can delete that new record. Where IDs can be reused, add version predicates or use tombstones/operation logs. `_id` is an identifier key, not a complete lifecycle guarantee.

### 10.3. Bulk Conditional Deletion by Policy

When purging expired data, **lock down the scope**:

- compute the cutoff timestamp once per campaign, never recalculating `new Date()` per retry;
- enforce tenant, data type, status, and legal-hold conditions;
- persist batch ID, cutoff, expected count, and checkpoints;
- batch by ID/cursor or an index-friendly approach suited to data size;
- verify and measure counts after each batch.

For critical deletions, consider soft delete, history archives, and explicit approval workflows. These are domain decisions; never assume `deleteMany` has batch rollback just because it is a single call.

## 11. Multi-Worker Contention: Unique Indexes and Job State

### 11.1. Two Workers Submitting the Same Item

```text
             Worker A                   Worker B
                |                          |
                v                          v
        upsert externalId=X         upsert externalId=X
                |                          |
                +------------+-------------+
                             |
                             v
                  Unique index in MongoDB
                             |
                     At most one key X
```

With an upsert on a unique key using `$setOnInsert`, one worker inserts while the other either matches the existing document or hits `E11000`. Under specific conditions, concurrent upserts transition cleanly into the update branch when the equality filter matches the unique key and the update does not change the key; **never assume every race automatically resolves as a clean update**.

The application must inspect results and errors, then confirm the stored document matches expected payload/version.

### 11.2. Claiming a Job with a Conditional Update

When workers pull tasks from a `jobs` collection, use `findOneAndUpdate` with a status filter to **claim** a job:

```javascript
const claimed = db.jobs.findOneAndUpdate(
  {
    state: "READY"
  },
  {
    $set: {
      state: "PROCESSING",
      workerId: "worker-01",
      claimedAt: new Date()
    }
  },
  {
    sort: { createdAt: 1 },
    returnDocument: "after"
  }
);
```

This transitions one document conditionally and atomically at the document level. Real job queues should add **leases**, expiration timestamps, heartbeats, retry counters, and crash recovery rules so jobs never stay stuck in `PROCESSING` if a worker dies.

Even with conditional claiming, redelivery can still occur if a lease expires or a task is replayed. Thus **target writes must still enforce idempotency**.

### 11.3. Retries with Backoff and Attempt Caps

When an item is classified as retryable, track:

- `attempt` count and last attempt timestamp;
- exponential backoff with jitter to avoid retry storms across workers;
- time and max-attempt caps;
- a dead-letter queue or `FAILED_PERMANENTLY` state when unrecoverable;
- alerts when `UNKNOWN` or `RETRYABLE` counts exceed thresholds.

Do not trap every error in an endless retry loop. Bad data, genuine payload conflicts, or missing permissions require different remediation.

## 12. When Are Transactions Needed Instead of Regular Bulk Writes?

### 12.1. "All-or-Nothing" Requirements

If business rules require **an entire group of operations to commit together**, such as:

- transferring funds between two accounts;
- creating an order and deducting inventory as a single invariant;
- persisting a domain write alongside its outbox record consistently;

then non-transactional `bulkWrite()` is insufficient. MongoDB supports multi-document transactions on compatible topologies (replica sets or sharded clusters), committing or aborting all writes in the transaction together.

However, transactions do not automatically provide:

- uniqueness constraints without a unique index;
- idempotency keys if a client re-submits a request as a brand-new transaction;
- "send email only once" guarantees for external side effects outside the database;
- valid filter logic or state-machine correctness.

### 12.2. Retry Differences in Transactions

A transaction can fail due to write conflicts, transient errors, or unknown commit results. Transaction/commit retries must follow driver guidelines and error labels, avoiding unguarded external side effects inside callbacks that may re-execute.

Never assume "wrapping bulk in a transaction eliminates all partial-outcome edge cases": a request can commit on the server while the response is lost, so the application still needs idempotency when clients retry business actions.

### 12.3. Choosing the Solution Matching Required Guarantees

| Requirement | Typical fit |
| --- | --- |
| Import many independent records; tolerate individual failures | Unordered `bulkWrite`, unique keys, checkpoints, selective retries |
| Sequential updates with dependencies | Ordered bulk or transaction depending on invariant |
| Update one document conditionally by state | `updateOne` with state/version filter |
| Create at most one record per external ID | Unique index + idempotent upsert |
| Update multiple documents atomically together | Multi-document transaction |
| Retryable deletion of known IDs | `deleteOne` with fixed ID/ownership filters + reconciliation |
| Emit an event reliably to an external system | Outbox/inbox + idempotent consumer and separate delivery handling |

## 13. Tracking Progress and Recovering After Worker Crashes

### 13.1. Do Not Keep Progress Only in RAM

Suppose a worker receives a successful bulk response but crashes before writing its checkpoint to the coordinator. On restart, the job may appear `PENDING` again. Without stable keys and idempotent writes, re-running the import creates duplicates.

Persist progress durably by **batch ID and item key** in a database or reliable queue. A typical flow:

```text
Read PENDING/RETRYABLE items
             |
             v
Build operations from source data snapshot
             |
             v
bulkWrite (ordered false if independent)
             |
             v
Classify result / error / unknown
             |
             v
Reconcile by business key and fingerprint
             |
             v
Persist per-item checkpoint
             |
             v
Re-queue only items needing retry
```

Even saving checkpoints can fail or race. That is why **the final source of truth** must be unique constraints and target document state, while checkpoints support orchestration and recovery.

### 13.2. Batch IDs and Item Keys Serve Different Purposes

- **Batch ID** identifies a run, useful for metrics and recovery.
- **Item key** identifies a domain operation and must remain stable across retries.
- **Input index** identifies only an array slot within one specific call.
- **MongoDB `_id`** identifies a document in the collection, auto-generated or application-assigned.
- **Payload digest** verifies payload equality under the same item key.

Never use `batchId + arrayIndex` as a unique key if upstream systems can reorder items or split batches differently on subsequent runs. Even if an item moves from Batch A to Batch B, its business identity must stay anchored by a stable external ID or operation ID.

### 13.3. Operational Metrics to Track

| Metric | Meaning |
| --- | --- |
| Total input items | Expected volume |
| Confirmed items | Actual progress at required durability level |
| Duplicate items with matching payload | Rate of benign duplicate deliveries |
| Conflicting items with differing payload | Risk of upstream data drift |
| Validation-error items | Schema or parser bugs |
| Unknown-outcome items | Reconciliation volume after network/write concern errors |
| Retry counts and retry latency | Recovery health and retry-storm risk |
| Missing documents vs. snapshot | Completeness after import or deletion |

Useful logs include `batchId`, `itemKey`, `attempt`, operation type, error code, timestamp, and correlation ID. Never log tokens, passwords, credentialed URIs, or unnecessary personal payload data.

## 14. Common Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Treating a bulk exception as full-batch rollback | Re-sending already succeeded operations | Read partial results, classify errors, reconcile |
| Assuming `ordered: false` always runs every item | Dropping items on command/network errors | Use checkpoints and handle `UNKNOWN` state |
| Assuming no `writeErrors` proves majority commit | Misjudging durability on write concern errors | Handle write concern errors and read with appropriate concern |
| Retrying `insertOne` with a fresh `_id` | Creating business duplicates | Use stable keys, unique indexes, or upserts |
| Relying on `upsert: true` alone to stop duplicates | Concurrent upserts can insert duplicates without constraints | Add a unique index on the business key |
| Catching all `11000` errors and returning success | Masking collisions on other indexes or differing payloads | Look up by exact key and compare fingerprints |
| Retrying `121` indefinitely | Never fixes schema-invalid documents | Repair parser or source data |
| Retrying `$inc` after timeout without reconciliation | Double-incrementing or double-debiting | Use operation IDs and idempotency mechanisms |
| Using `deleteMany({})` to clean up after a failed bulk | Wiping unintended data | Snapshot IDs and enforce explicit ownership filters |
| Recalculating cutoff on cleanup retries | Deleting newer records | Freeze one campaign cutoff timestamp |
| Using input array index as a durable ID | Misalignment when retrying in a new batch | Track business keys and batch IDs separately |
| Trusting driver retries alone against duplicates | APIs/queues can still replay the same business request | Enforce domain-level idempotency |
| Ignoring target record state/version during updates | Overwriting newer state with stale events | Conditional updates and version/ordering policies |
| Sending emails inside a transaction callback | Callback retries send duplicate emails | Use outbox + idempotent consumers |

## 15. End-to-End Scenario: Partner Order Ingestion

A system receives 10,000 orders per hour from an ERP. Design choices:

1. Normalize `tenantId`, `sourceSystem`, `externalId`, and business fields.
2. Create a unique index on `{tenantId, sourceSystem, externalId}` so the same order cannot appear twice in the collection.
3. Store `payloadDigest` and initial fields inside `$setOnInsert`.
4. Split into sensible batch sizes using `ordered: false` since orders are independent.
5. Keep the `index → itemKey` map per batch alongside a snapshot of source data.
6. On `11000`, read back by key and compare digests: matching digest confirms acceptance; differing digest marks conflict.
7. On `121`, route the item to a data-repair queue rather than retrying infinitely.
8. On transient errors, retry **only eligible items** with backoff and attempt limits.
9. On lost responses or write concern errors, mark `UNKNOWN` and reconcile at the required consistency level before confirming.
10. Use durable checkpoints for crash recovery while relying on unique keys and idempotency to prevent duplicate writes.

### Example Operational Outcome

```text
Batch IMPORT-042 (5 items):

Item     Initial response            Conclusion after reconciliation
----------------------------------------------------------------
O-101    Insert/upsert succeeded     CONFIRMED
O-102    E11000                      CONFIRMED (same digest)
O-103    E11000                      CONFLICT (different digest)
O-104    Validation 121              INVALID (wrong amount type)
O-105    No response received        UNKNOWN -> safe reconcile/retry
```

Here, "O-102 already exists" is a conclusion reached **after reconciliation**, not blindly from code `11000`. `O-103` is not silently overwritten. `O-104` requires source data repair. `O-105` is never assumed failed and replayed with cumulative mutations.

Once all items are classified, the system reports exact counts for confirmed, conflicted, invalid, and unknown items—accurately reflecting domain state far better than a single batch-level `success/failure` flag.

## 16. Practice Questions

1. With `ordered: true`, a batch `A, B, C` hits a duplicate key on `B`. Could `A` have succeeded? Did `C` run?
2. With `ordered: false`, why can a `bulkWrite` that throws an error still leave newly inserted documents in the collection?
3. How do `matchedCount` and `modifiedCount` differ? Are they sufficient to verify each individual item?
4. Why must `writeErrors` be distinguished from `writeConcernError`?
5. If the connection drops after sending a bulk, can you conclude all operations failed?
6. Why can retrying `$inc` be dangerous even when the filter always targets a single unique `_id`?
7. What prevents two workers from creating two orders with the same `externalId` when using upsert?
8. Upon hitting `E11000`, how do you distinguish "already processed the same request" from "conflict between two different payloads"?
9. Why does a `deleteOne` returning `deletedCount: 0` on retry not prove the document was never deleted?
10. How do batch ID, input index, and business key differ in a retry-capable system?
11. When can you use unordered bulk with selective retries, and when must you consider a transaction?
12. Why is adding a transaction alone insufficient to prevent a replayed payment request from causing duplicate side effects?

## 17. Conclusion

When working with **deletion and bulk writes** in MongoDB, design under the assumption that **both failures and request replays will happen**. `bulkWrite` executes batches efficiently without making the whole batch atomic; `ordered` controls continuation after write errors, while responses and error metadata expose part of what occurred.

To avoid losing or duplicating data, give every item a **stable business key**, use **safely retryable writes**, protect invariants with unique indexes, and implement **reconciliation for uncertain states**. Retry only genuinely retryable items while preserving checkpoints and tracking permanent failures. Where multiple documents must succeed together, use transactions and business-level idempotency rather than relying on a single unguarded bulk call.
