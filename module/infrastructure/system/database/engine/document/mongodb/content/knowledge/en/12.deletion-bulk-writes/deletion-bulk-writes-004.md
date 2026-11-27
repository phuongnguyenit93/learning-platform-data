# bulkWrite: Combining Inserts, Updates, Replacements, and Deletes

In a real-world system, a data sync job might need to **insert** new products, **update** inventory quantities, **replace** normalized records, and **delete** expired entries. Sending sequential `insertOne()`, `updateOne()`, `replaceOne()`, and `deleteOne()` commands from the application generates excessive network round-trips and makes tracking results harder. MongoDB provides **`bulkWrite()`** to combine multiple write operations into a single high-level call with configurable **execution ordering**, **error handling**, and **write concern**.

This lesson belongs to the **Deletion and Bulk Writes** chapter of the *Database Engine Document MongoDB* module. The main focus is **`db.collection.bulkWrite()`**, covering all six operation types: `insertOne`, `updateOne`, `updateMany`, `replaceOne`, `deleteOne`, and `deleteMany`. It then distinguishes this API from the multi-collection `Mongo.bulkWrite()` introduced in MongoDB 8.0, and guides you through handling partial results, errors, retries, transactions, batching, and the risk of accidental deletion.

After this lesson, you will be able to:

1. Construct valid **write-model arrays** combining inserts, updates, replacements, and deletes.
2. Explain `ordered: true` vs. `ordered: false`, especially when an operation fails.
3. Read the counters `insertedCount`, `matchedCount`, `modifiedCount`, `deletedCount`, `upsertedCount`, and associated IDs.
4. Understand why **a bulk write is not automatically a transaction**.
5. Use `upsert`, `arrayFilters`, `collation`, `hint`, and filter guards in the right contexts.
6. Design retry/idempotency logic and handle errors such as duplicate keys, validation failures, or write concern timeouts.
7. Choose appropriate batch sizes to optimize throughput without sacrificing domain correctness.

> **Version-specific API distinction:** `db.collection.bulkWrite()` operates on **a single collection**. Starting in **MongoDB 8.0**, the server adds the **`bulkWrite` database command** and `mongosh` adds **`Mongo.bulkWrite()`** to write across **multiple collections/databases** in a single call. The two APIs **do not share the same operation object shape**. Most examples below target `db.collection.bulkWrite()` and apply to MongoDB 7.0/8.0 and corresponding supported versions.

## 1. What Problem Does bulkWrite Solve?

Suppose an import run needs to:

~~~text
1. Insert new product P-400.
2. Increment inventory for P-100.
3. Flag accessory products as eligible for promotion.
4. Replace the entire normalized record for P-300.
5. Delete one legacy record by ID.
6. Delete selected inactive records.
7. Create P-500 via upsert if it does not exist yet.
~~~

Instead of issuing seven separate CRUD calls:

~~~javascript
// Individual calls (illustrating the concept, not bulk):
products.insertOne(...)
products.updateOne(...)
products.updateMany(...)
products.replaceOne(...)
products.deleteOne(...)
products.deleteMany(...)
products.updateOne(..., { upsert: true })
~~~

We can express them in **a single list of operation models**:

~~~javascript
const result = products.bulkWrite(
  [
    { insertOne: { document: /* ... */ } },
    { updateOne: { filter: /* ... */, update: /* ... */ } },
    { updateMany: { filter: /* ... */, update: /* ... */ } },
    { replaceOne: { filter: /* ... */, replacement: /* ... */ } },
    { deleteOne: { filter: /* ... */ } },
    { deleteMany: { filter: /* ... */ } }
  ],
  { ordered: true }
)
~~~

Key benefits:

- **Reduces client/network overhead** compared to issuing many unnecessary individual calls.
- **Combines multiple write types** against a single collection and returns an aggregated result.
- Controls whether to **stop on the first error** or **continue independent operations**.
- Simplifies batching during imports, migrations, cache/data synchronization, and bulk processing.

Key limitations:

- A `bulkWrite()` call **does not create atomicity across the entire list**. Each single-document operation retains its own atomicity; `updateMany`/`deleteMany` can affect multiple documents without turning the entire batch into a transaction.
- `ordered: false` **makes no guarantee on execution order** among operations.
- Earlier operations may succeed before an error occurs; the application must inspect the result accurately.
- Batching remains subject to **operation/command count limits, BSON size limits, cache pressure, write load, and write concern**.

## 2. General Syntax

In `mongosh`:

~~~javascript
db.collection.bulkWrite(
  [
    { insertOne: { document: { /* data */ } } },
    { updateOne: {
        filter: { /* criteria */ },
        update: { $set: { /* fields */ } },
        upsert: false
    } },
    { updateMany: {
        filter: { /* criteria */ },
        update: { $inc: { /* fields */ } }
    } },
    { replaceOne: {
        filter: { /* criteria */ },
        replacement: { /* full replacement document */ },
        upsert: false
    } },
    { deleteOne: { filter: { /* criteria */ } } },
    { deleteMany: { filter: { /* criteria */ } } }
  ],
  {
    ordered: true,
    bypassDocumentValidation: false
  }
)
~~~

The **first argument** is an array of operation objects, each containing **exactly one operation type**. The **second argument** specifies bulk-level options such as `ordered`, `bypassDocumentValidation`, and—depending on API/version—`writeConcern` or `let`.

Do not write:

~~~javascript
// Wrong: confusing single-operation helper arguments with the bulk operation shape.
db.products.bulkWrite([
  { insertOne: { _id: "P-1", name: "Book" } },
  { updateOne: { _id: "P-1", $set: { stock: 5 } } }
])
~~~

Instead, use the proper nested keys `document`, `filter`, `update`, and `replacement` for each operation:

~~~javascript
db.products.bulkWrite([
  {
    insertOne: {
      document: { _id: "P-1", name: "Book", stock: 0 }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-1" },
      update: { $set: { stock: 5 } }
    }
  }
])
~~~

This example is **order-dependent**, because the second operation expects to see the document just inserted by the first. When that dependency exists, keep `ordered: true`; **do not** switch to unordered merely hoping for higher speed.

## 3. The Six Operations in Collection bulkWrite

| Operation | Effect | Key fields | Documents potentially affected |
|---|---|---|---|
| **`insertOne`** | Inserts one document. | `document` | One new document. |
| **`updateOne`** | Updates one document matching `filter`. | `filter`, `update`, optional `upsert` | At most one document modified/created. |
| **`updateMany`** | Updates all documents matching `filter`. | `filter`, `update`, optional `upsert` | Potentially many documents. |
| **`replaceOne`** | Replaces one document's contents with `replacement`. | `filter`, `replacement`, optional `upsert` | At most one document modified/created. |
| **`deleteOne`** | Deletes at most one document matching `filter`. | `filter` | 0 or 1 document. |
| **`deleteMany`** | Deletes all documents matching `filter`. | `filter` | Potentially many documents. |

### 3.1. `insertOne` — Inserting One Document

~~~javascript
{
  insertOne: {
    document: {
      _id: "P-400",
      sku: "NOTE-400",
      name: "Ruled Notebook",
      category: "accessory",
      stock: 20,
      active: true
    }
  }
}
~~~

`document` holds the BSON document to insert. If `_id` is omitted, the client/driver or server generates an `ObjectId` as applicable; applications needing stable IDs for retries/idempotency should consider **unique business keys** and/or deterministic IDs.

If `_id` or a key in a **unique index** already exists, the operation raises a **duplicate key error** rather than overwriting the existing document. For "update if exists, insert if missing" synchronization, use **upsert** instead of unconditional repeated inserts.

### 3.2. `updateOne` — Updating at Most One Document

~~~javascript
{
  updateOne: {
    filter: { _id: "P-100", active: true },
    update: {
      $inc: { stock: 5 },
      $set: { lastRestockedAt: ISODate("2026-11-14T00:00:00Z") }
    }
  }
}
~~~

MongoDB finds a document matching `filter` and applies `update`. With `updateOne`, if multiple documents match, only one is chosen; do not rely on "the first document" if the filter does not uniquely identify the business entity. To update all matches, use `updateMany` or refine the filter.

`$inc` is **atomic per document**, avoiding lost updates caused by reading stock on the client and issuing `$set` with a stale value. However, if **the entire request is re-sent** after an ambiguous outcome, `$inc` can increment **twice** at the business level; distinguish atomicity from idempotency.

### 3.3. `updateMany` — Updating All Matching Documents

~~~javascript
{
  updateMany: {
    filter: { category: "accessory", active: true },
    update: { $set: { promotionEligible: true } }
  }
}
~~~

`updateMany` applies updates to all documents matching **as they are processed** per MongoDB semantics, and each individual document update is atomic. The set of modifications as a whole is **not a single atomic operation**. If concurrent workloads alter `category` or `active`, the actual count modified can vary by timing.

Verify filters with `find` and `countDocuments` before running large batches. An empty filter `{}` in `updateMany` updates **the entire collection**—valid if intentional, dangerous if accidental.

### 3.4. `replaceOne` — Replacing the Entire Document

~~~javascript
{
  replaceOne: {
    filter: { _id: "P-300" },
    replacement: {
      _id: "P-300",
      sku: "PEN-300",
      name: "Gel Pen",
      category: "stationery",
      stock: 15,
      active: true,
      normalized: true
    }
  }
}
~~~

`replacement` must be a **replacement document**, **not** an update expression containing `$set` or `$inc`. Existing fields **absent from `replacement` are removed** (subject to `_id` preservation rules). This is the biggest difference from `updateOne` with update operators.

The replacement document must not change `_id` to a different value. If you only want to update `name` or `stock` while keeping other fields intact, use `updateOne` with `$set`; **do not** pass a partial object to `replaceOne`.

### 3.5. `deleteOne` — Deleting at Most One Document

~~~javascript
{
  deleteOne: {
    filter: { _id: "P-OLD1", legacy: true }
  }
}
~~~

The more specific the filter, the easier it is to control. If `filter` matches multiple documents, `deleteOne` deletes one document without an arbitrary user-specified order. Prefer `_id` or a unique key combined with protective guards to delete the right entity.

### 3.6. `deleteMany` — Deleting Multiple Documents

~~~javascript
{
  deleteMany: {
    filter: { active: false, archived: true }
  }
}
~~~

`deleteMany` can delete **a huge number** of documents. Multi-document deletion is not guaranteed atomic for **the entire set** without a transaction. Never pass `filter: {}` unless the approved intent is clearing **the entire collection**.

If the domain requires recovery, auditing, retention windows, or sync events, **soft delete** (e.g., `$set: { deletedAt: ... }`) may be more appropriate than hard delete. That is a separate domain decision, not an option on `deleteMany`.

## 4. End-to-End Practice: One Bulk Combining All Six Operations

### 4.1. Preparing Test Data

The commands below are strictly for the `bulk_lab` database. They insert demo documents with fixed IDs; do not run on production. To keep illustrative results reproducible, use a dedicated lab collection containing no data outside the sample list.

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
const products = lab.products

// Run only once on an empty test collection,
// or use a fresh lab collection for each practice run.
products.insertMany([
  {
    _id: "P-100", sku: "BOOK-100", name: "Book A",
    category: "book", stock: 10, active: true
  },
  {
    _id: "P-200", sku: "PENCIL-200", name: "Pencil",
    category: "accessory", stock: 5, active: true
  },
  {
    _id: "P-300", sku: "PEN-300", name: "Gel Pen Old Version",
    category: "stationery", stock: 12, active: true,
    legacyDescription: "Will be removed on replace"
  },
  {
    _id: "P-OLD1", sku: "LEGACY-OLD1", name: "Legacy Product",
    category: "legacy", stock: 0, active: false, legacy: true
  },
  {
    _id: "P-DIS1", sku: "DISABLED-1", name: "Discontinued 1",
    category: "legacy", stock: 0, active: false, archived: true
  },
  {
    _id: "P-DIS2", sku: "DISABLED-2", name: "Discontinued 2",
    category: "legacy", stock: 0, active: false, archived: true
  }
])

products.find({}, { _id: 1, sku: 1, stock: 1, active: 1 })
  .sort({ _id: 1 })
~~~

**If you re-run this after already inserting**, `insertMany` with the same `_id`s will trigger duplicate key errors. Either use another lab database or explicitly reset **only the demo data** once sure nobody shares the collection. Never run `db.dropDatabase()` on a shared environment just to test commands.

### 4.2. Executing an Ordered Bulk

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
const products = lab.products

const operations = [
  // 0. Insert a new product.
  {
    insertOne: {
      document: {
        _id: "P-400", sku: "NOTE-400", name: "Ruled Notebook",
        category: "accessory", stock: 20, active: true
      }
    }
  },

  // 1. Update one product using $inc and $set.
  {
    updateOne: {
      filter: { _id: "P-100", active: true },
      update: {
        $inc: { stock: 5 },
        $set: { lastRestockedAt: ISODate("2026-11-14T00:00:00Z") }
      }
    }
  },

  // 2. Update all active accessories.
  {
    updateMany: {
      filter: { category: "accessory", active: true },
      update: { $set: { promotionEligible: true } }
    }
  },

  // 3. Replace all of P-300 with a normalized document.
  {
    replaceOne: {
      filter: { _id: "P-300" },
      replacement: {
        _id: "P-300", sku: "PEN-300", name: "Gel Pen",
        category: "stationery", stock: 15, active: true,
        normalized: true
      }
    }
  },

  // 4. Delete exactly one legacy record.
  {
    deleteOne: {
      filter: { _id: "P-OLD1", legacy: true }
    }
  },

  // 5. Delete archived and inactive records.
  {
    deleteMany: {
      filter: { active: false, archived: true }
    }
  },

  // 6. Upsert P-500 if not present.
  {
    updateOne: {
      filter: { _id: "P-500" },
      update: {
        $setOnInsert: {
          sku: "BAG-500", name: "Document Folder",
          category: "accessory", stock: 8, active: true
        }
      },
      upsert: true
    }
  }
]

const result = products.bulkWrite(operations, { ordered: true })
printjson(result)
~~~

The operations sit in an **array**; `ordered: true` is the default and preserves the logical dependency between operations 0 and 2. Consequently, the `updateMany` at index 2 sees `P-400` inserted at index 0, provided the bulk reaches that index without errors.

When run once against the freshly seeded data, expected counts:

| Counter | Expected value | Reason |
|---|---:|---|
| `insertedCount` | 1 | Inserted `P-400`. |
| `matchedCount` | 4 | `updateOne` `P-100` (1), `updateMany` `P-200`/`P-400` (2), `replaceOne` `P-300` (1). |
| `modifiedCount` | 4 | All four matched documents changed values. |
| `deletedCount` | 3 | `deleteOne` `P-OLD1` (1), `deleteMany` `P-DIS1`/`P-DIS2` (2). |
| `upsertedCount` | 1 | `updateOne` with `upsert` created `P-500`. |

These numbers apply only to the **initial lab collection** and exact operation order. Re-running will hit duplicate key on inserting `P-400`, so you cannot expect the same counters again.

### 4.3. Inspecting State After the Bulk

~~~javascript
products.find(
  {},
  {
    _id: 1, sku: 1, name: 1, stock: 1,
    promotionEligible: 1, archived: 1, normalized: 1
  }
).sort({ _id: 1 })
~~~

Documents `P-100`, `P-200`, `P-300`, `P-400`, and `P-500` should remain. `P-100` has `stock = 15`; `P-200` and `P-400` have `promotionEligible: true`; `P-300` lost `legacyDescription` because `replaceOne` replaced the whole document; `P-OLD1`, `P-DIS1`, and `P-DIS2` were deleted; and `P-500` was created via upsert.

**Lesson from this example:** Bulk can combine many write types, but that does not make change counts invariant over time. Outcomes depend on input data, ordering, filters, and concurrent writes from other clients.

## 5. Ordered vs. Unordered: Same List, Two Different Semantics

**`ordered`** determines whether MongoDB must execute operations in array order and stop on write errors.

| Option | Execution | On operation error | Best suited when |
|---|---|---|---|
| **`ordered: true`** (default) | Executes in declared order; each step precedes the next. | Stops subsequent operations after a write error, aside from special error cases like write concern errors. | Operations **depend on one another** and ordering must be easy to reason about. |
| **`ordered: false`** | Server/driver may execute out of order, potentially in parallel depending on conditions. | Continues trying remaining operations; valid ones can still succeed. | Operations are **independent**, throughput matters, and partial results are acceptable. |

Notes:

- `ordered: true` does **not** turn the batch into a transaction; it only controls ordering and stop-on-error behavior.
- `ordered: false` carries **no guarantee** that operation 0 finishes before operation 1, even though they sit in an ordered array.
- Execution optimizations vary by deployment, sharding, batching, and driver; unordered **may** be faster, not guaranteed faster in every workload.
- If multiple operations modify the same document, the final result can depend on order. If deterministic order is needed, do not pick unordered.

### 5.1. Duplicate Key Experiment with Ordered

Test on a fresh collection separate from `products` for clear results:

~~~javascript
const lab = db.getSiblingDB("bulk_lab")

lab.orderedDemo.insertOne({ _id: "A", value: 1 })

const orderedOps = [
  { insertOne: { document: { _id: "B", value: 2 } } },
  { insertOne: { document: { _id: "A", value: 999 } } }, // duplicate
  { insertOne: { document: { _id: "C", value: 3 } } }
]

try {
  lab.orderedDemo.bulkWrite(orderedOps, { ordered: true })
} catch (err) {
  print("Ordered bulk failed: " + err.message)
}

lab.orderedDemo.find().sort({ _id: 1 })
~~~

Expected result on a new collection containing only `A`:

~~~text
Operation 0: insert B -> succeeds
Operation 1: insert A -> duplicate key
Operation 2: insert C -> NOT executed

Remaining documents: A, B.
~~~

Notice **B remains inserted** even though the overall `bulkWrite` threw an error. Ordered mode **does not roll back** operations executed prior to the error.

### 5.2. Same Data with Unordered

~~~javascript
const lab = db.getSiblingDB("bulk_lab")

lab.unorderedDemo.insertOne({ _id: "A", value: 1 })

const unorderedOps = [
  { insertOne: { document: { _id: "B", value: 2 } } },
  { insertOne: { document: { _id: "A", value: 999 } } }, // duplicate
  { insertOne: { document: { _id: "C", value: 3 } } }
]

try {
  lab.unorderedDemo.bulkWrite(unorderedOps, { ordered: false })
} catch (err) {
  print("Unordered bulk reported one or more errors")
  print(err.message)
}

lab.unorderedDemo.find().sort({ _id: 1 })
~~~

Expected result on the new demo collection:

~~~text
Insert A -> duplicate key, reports error
Insert B -> may succeed
Insert C -> may succeed

Remaining documents: A, B, C.
~~~

**Do not assume B was inserted before C.** In tests, assert only that valid independent operations were processed, never asserting chronological execution order.

If you run this multiple times on the same collection, both `B` and `C` will already exist and raise duplicate key errors on subsequent runs; use a fresh lab collection name or reset data to match your experiment goal.

### 5.3. Why Is Unordered Dangerous When Operations Depend on One Another?

Example:

~~~javascript
products.bulkWrite([
  {
    insertOne: {
      document: { _id: "P-X", stock: 0 }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-X" },
      update: { $inc: { stock: 5 } }
    }
  }
], { ordered: false })
~~~

Imagine the update runs before the insert: the update gets `matchedCount = 0`, then the insert creates `stock: 0`. The desired business outcome (`stock: 5`) **is not guaranteed**. With such dependencies, use `ordered: true`, or collapse them into an **upsert** if appropriate for the domain:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-X" },
      update: {
        $inc: { stock: 5 },
        $setOnInsert: { createdBy: "inventory-import" }
      },
      upsert: true
    }
  }
])
~~~

Because this example uses `$inc`, it is **not idempotent if the application re-sends the bulk** after it already succeeded. To ensure a stock-receipt event is applied exactly once, use an event identity key/ledger or an appropriate deduplication design.

## 6. Reading Return Values

When a bulk succeeds and is acknowledged, `db.collection.bulkWrite()` returns an object holding counters and ID mappings per the active API.

~~~javascript
const result = products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { checked: true } }
    }
  }
])

printjson(result)
~~~

Key fields:

| Field | Meaning |
|---|---|
| **`acknowledged`** | Whether the write was acknowledged per write concern (when provided by the API). |
| **`insertedCount`** | Number of `insertOne` operations that inserted a document. |
| **`matchedCount`** | Total documents matched by update/replace filters. |
| **`modifiedCount`** | Number of documents actually modified; can be less than `matchedCount` if values did not change. |
| **`deletedCount`** | Total documents deleted by `deleteOne`/`deleteMany`. |
| **`upsertedCount`** | Number of documents created by operations with `upsert: true`. |
| **`insertedIds`** | Map from insert operation index to the corresponding `_id` when provided by the API. |
| **`upsertedIds`** | Map from upsert operation index to the created `_id` when provided by the API. |

For instance, if `updateOne` matches a document and runs `$set: {checked:true}` when `checked` is already `true`, you typically get:

~~~text
matchedCount: 1
modifiedCount: 0
~~~

This is **not an error**. Conversely, an `updateOne` whose filter matches nothing produces `matchedCount = 0` and, without `upsert`, creates no document.

### 6.1. `matchedCount` Differing from `modifiedCount`

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { status: "ACTIVE" } }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { status: "ACTIVE" } }
    }
  }
])
~~~

If `P-100` initially lacked `status`, the first operation adds the field and the second makes no change; totals are typically `matchedCount = 2`, `modifiedCount = 1`. Because two **operations** matched the same document, counters reflect **the sum across operations**, not unique document IDs in the batch.

### 6.2. Upsert IDs and Operation Indexes

Suppose:

~~~javascript
const result = products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-600" },
      update: { $setOnInsert: { sku: "NEW-600" } },
      upsert: true
    }
  },
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { updated: true } }
    }
  }
])

printjson(result.upsertedIds)
~~~

If `P-600` did not exist yet, the upsert creates ID `P-600`, mapped under **operation index 0**. Do **not** confuse `upsertedIds` with `insertedIds`: an upsert triggered by `updateOne` or `replaceOne` is not an `insertOne` operation.

Property names and map types vary across language drivers. In the Java Sync Driver, for example, results use `BulkWriteResult` and a list of `BulkWriteUpsert`; always consult your driver's API docs.

### 6.3. Error Results Differ from Success Results

If an operation fails, `bulkWrite()` may **throw an exception** instead of returning a normal result object. In `mongosh`, this is typically `BulkWriteError` / `MongoBulkWriteError` depending on version. Useful details include:

- **`writeErrors`**: per-operation errors (such as duplicate key or validation failure).
- **operation index**: position in the operations array (usually 0-based; verify driver semantics).
- **`writeConcernErrors`**: write acknowledgment failures (do not equate with "nothing was written").
- **partial result**: counts of operations that succeeded, when exposed on the exception by the API.

Do not assume every driver version exposes the exact same object shape, or that every exception includes complete `result.insertedIds`. For production logging, record **error type, code, index, batch ID**, and available counts while avoiding dumping sensitive customer payloads in logs.

### 6.4. Error Handling by Category

| Error | Potential impact | Handling approach |
|---|---|---|
| Duplicate key, typically `11000` | An insert/upsert violated a unique key. | Check IDs/invariants; may treat as "already processed" if domain rules and actual DB state confirm. |
| DocumentValidationFailure, typically `121` | Document failed schema validator. | Fix data or schema; do not blindly retry the same payload. |
| Unauthorized | Account lacks permissions on operation/collection. | Fix RBAC privileges rather than granting overly broad roles. |
| Write concern timeout | Acknowledgment level not met within timeout. | Inspect actual state/replicas before re-sending non-idempotent writes. |
| Network timeout / primary stepdown | Uncertain whether client received full response. | Rely on retryable writes where supported; reconcile by ID/ledger. |
| Write conflict / transaction abort | Storage engine or transaction write contention. | Retry at the transaction or operation level per error labels/driver rules. |
| BSON document too large | Single document exceeds system threshold. | Redesign the data model; shrinking batch size alone will not fix it. |
| Hint points to nonexistent index | Operation cannot run with the requested index. | Verify index state and roll out indexes before code using `hint`. |

## 7. Upsert: "Update If Exists, Create If Missing"

`upsert: true` is supported on `updateOne`, `updateMany`, and `replaceOne`. If **no document matches the filter**, MongoDB can create a new document.

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-700" },
      update: {
        $set: { name: "Product 700", active: true },
        $setOnInsert: {
          createdAt: ISODate("2026-11-14T00:00:00Z")
        }
      },
      upsert: true
    }
  }
])
~~~

If `P-700` is missing, upsert inserts `P-700` with those fields. If it already exists, only the regular update operators apply; `$setOnInsert` **does not overwrite `createdAt`** on the existing document.

### 7.1. `updateMany` with Upsert Does Not Create "Multiple New Documents"

When `updateMany` has `upsert: true` and matches zero documents, MongoDB **creates a single new document**, not one document per hypothetical item in your filter criteria. Do not use `updateMany + upsert` expecting to turn 100 SKUs into 100 inserts; build 100 individual write models or use an appropriate insert pattern.

### 7.2. `replaceOne` with Upsert

~~~javascript
products.bulkWrite([
  {
    replaceOne: {
      filter: { _id: "P-800" },
      replacement: {
        _id: "P-800",
        sku: "REPLACE-800",
        name: "Normalized Version 800",
        stock: 4,
        active: true
      },
      upsert: true
    }
  }
])
~~~

If `P-800` does not exist, it is created using `replacement`. If it already exists, the old document is **completely replaced** (keeping `_id`), and any fields absent from `replacement` disappear. Unlike `$setOnInsert`, a replace upsert cannot selectively "preserve existing fields" if the application passes an incomplete replacement document.

### 7.3. Preventing Races When Multiple Clients Upsert Concurrently

If two clients concurrently upsert on `sku = "BOOK-100"` without an appropriate unique index on the collection, **duplicate documents sharing the same business key** can appear under race conditions. To enforce uniqueness, create a unique index matching the business rule:

~~~javascript
// Run only when existing data has no duplicate sku values.
products.createIndex({ sku: 1 }, { unique: true })
~~~

Adding a unique index **does not guarantee concurrent upserts seamlessly merge**; one client may encounter a duplicate key error and must handle it via synchronization logic. Filters should target the exact identity, never a broad predicate that could match multiple documents and modify the wrong record.

### 7.4. Idempotency Is Not Synonymous with Upsert

| Operation | Can re-running after success cause extra changes? |
|---|---|
| `$set: { status: "ACTIVE" }` on a specific ID | Normally **no** unintended state change. |
| `$inc: { stock: 1 }` | **Yes**, re-running increments again. |
| `insertOne` with the same `_id` | Second run raises duplicate key; domain logic must classify "already processed." |
| `replaceOne` with the same `replacement` | May yield the same final state, though concurrent updates must still be considered. |
| `deleteOne` by `_id` | Re-running typically deletes 0 documents; still evaluate if data/model changes. |
| `deleteMany` with a broad condition | Re-running can delete **newly arrived documents** now matching the filter. |
| `upsert + $setOnInsert` | Can converge to a stable state if the filter targets a unique identity. |
| `upsert + $inc` | Inserts once, but keeps incrementing on every replay. |

To process events with unique IDs safely, store `eventId` in a **ledger** with a unique index and coordinate business updates with appropriate transactions or conditional guards. Never treat `ordered`, `upsert`, or `retryWrites=true` as a universal deduplication solution.

## 8. Advanced Per-Operation Options

Not every option applies to all six operation types. Distinguish **bulk-level options** passed to `bulkWrite(operations, options)` from **per-operation options**.

| Option | Scope | Role |
|---|---|---|
| `ordered` | Entire bulk | Preserve order and stop on error, or allow unordered execution. |
| `writeConcern` | Entire bulk (where supported) | MongoDB write acknowledgment level. |
| `bypassDocumentValidation` | Entire bulk (if supported) | Bypass schema validation with proper authorization. |
| `upsert` | `updateOne`, `updateMany`, `replaceOne` | Create a new document if none match. |
| `collation` | Applicable operations | Locale/case/diacritic string comparison rules. |
| `arrayFilters` | `updateOne`, `updateMany` | Select array elements modified by positional updates. |
| `hint` | Updates/replaces (and deletes depending on API/version) | Force a specific index for the filter. |
| Aggregation pipeline in `update` | Update operations | Compute fields via pipeline stages instead of modifier documents. |

Do not place `ordered: false` inside `updateOne` as if it were a per-update option. Conversely, `arrayFilters` belongs to the **specific update operation**, not alongside `ordered` at the bulk options level.

### 8.1. `arrayFilters` for Updating Specific Array Elements

Suppose the `orders` collection contains:

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
lab.orders.insertOne({
  _id: "O-100",
  status: "PACKING",
  items: [
    { sku: "BK-01", qty: 2, packed: false },
    { sku: "PN-02", qty: 5, packed: false }
  ]
})
~~~

A single `bulkWrite` can mark item `BK-01` in `O-100` and update another field on the order:

~~~javascript
lab.orders.bulkWrite([
  {
    updateOne: {
      filter: { _id: "O-100" },
      update: {
        $set: { "items.$[line].packed": true }
      },
      arrayFilters: [
        { "line.sku": "BK-01" }
      ]
    }
  },
  {
    updateOne: {
      filter: { _id: "O-100", status: "PACKING" },
      update: { $set: { lastPackedAt: new Date() } }
    }
  }
], { ordered: true })
~~~

`$[line]` selects **the `items` elements with SKU `BK-01`** in each matched document. `arrayFilters` is attached to the first `updateOne`; the second operation does not use it.

If these changes must satisfy complex business conditions **atomically within the same order**, combine them into **a single `updateOne`** to leverage single-document atomicity instead of relying on two separate operations inside a bulk.

### 8.2. `collation` for String Comparisons

Suppose you need to update all products in a category regardless of letter casing:

~~~javascript
products.bulkWrite([
  {
    updateMany: {
      filter: { category: "ACCESSORY" },
      update: { $set: { season: "winter" } },
      collation: { locale: "en", strength: 2 }
    }
  }
])
~~~

This collation performs locale-aware comparison at the specified strength, though exact matching depends on `strength`, `locale`, and the data. An **index without the matching collation** may not serve the query efficiently; design indexes around access patterns and verify with `explain()` as needed.

### 8.3. `hint` for Index Selection

~~~javascript
products.createIndex({ category: 1, active: 1 })

products.bulkWrite([
  {
    updateMany: {
      filter: { category: "accessory", active: true },
      update: { $set: { inspected: true } },
      hint: { category: 1, active: 1 }
    }
  }
])
~~~

`hint` instructs the planner to use a specific index. If the index does not exist or is invalid, the operation can error. Do not add `hint` assuming "forcing an index is always faster": the query planner may choose a better index as data and load evolve. During rollouts, create the index before deploying code that hints it.

### 8.4. Aggregation Pipeline Updates in Bulk

`updateOne` and `updateMany` accept an **array of pipeline stages** in `update` on supported versions:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: [
        {
          $set: {
            stockStatus: {
              $cond: [
                { $gt: ["$stock", 0] },
                "IN_STOCK",
                "OUT_OF_STOCK"
              ]
            }
          }
        }
      ]
    }
  }
])
~~~

Here `update` is an **array of pipeline stages**, not a `{ $set: ... }` update-modifier document. Pipeline updates support **a restricted set of stages**; you cannot use arbitrary aggregation stages. `$set` inside a pipeline accepts **aggregation expressions**, letting you compute values from existing fields on the document.

If you only need to `$inc` a field, standard update operators are simpler and clearer. Use pipeline updates only when you need cross-field derivations or conditional computations.

### 8.5. `bypassDocumentValidation` Is Not a Fix for Bad Data

If a collection has a JSON Schema validator, bulk writes violating it can be rejected per `validationAction`. Some APIs support:

~~~javascript
products.bulkWrite(
  [
    {
      insertOne: {
        document: {
          _id: "P-IMPORT",
          name: "Data imported from legacy source"
        }
      }
    }
  ],
  {
    ordered: true,
    bypassDocumentValidation: true
  }
)
~~~

`bypassDocumentValidation` is a controlled exception requiring the **`bypassDocumentValidation` privilege** in addition to write permissions. It does **not** bypass unique indexes, authentication, BSON size limits, or other constraints. In newer MongoDB versions with schema `constraint` levels, bypass capabilities may be further restricted by server rules. Prefer importing into **staging** and cleansing data whenever possible rather than granting permanent bypass privileges to applications.

## 9. Batch Size, Limits, and Performance

### 9.1. One Bulk Call Is Not Necessarily One Physical Request

Per the MongoDB Manual, MongoDB caps each **write command batch** at **`maxWriteBatchSize`** operations—commonly **100,000**. High-level driver APIs automatically split larger lists into appropriately sized batches. Besides operation count, commands are bound by BSON/payload size and document size limits.

~~~text
Application builds operations[0..N-1]
               |
               v
    Collection bulkWrite API
               |
        driver splits into batches
               |
     +---------+----------+
     |         |          |
     v         v          v
  Batch A   Batch B    Batch C
     |         |          |
     +---------+----------+
               |
          MongoDB Server
~~~

Do not confuse these limits:

- **Single BSON document limit:** typically **16 MiB**.
- **Operations per server write batch:** `maxWriteBatchSize`, typically **100,000**.
- **Command/message size limit:** another constraint that can force drivers to split batches well before reaching 100,000 operations.
- **Application memory and load limits:** an array of hundreds of thousands of operations can consume substantial RAM before ever being sent.

If you invoke `db.runCommand()` directly with an oversized write command, the server rejects it instead of auto-splitting. Automatic batch splitting is a benefit of **high-level driver/shell APIs**, not raw commands.

### 9.2. Inspecting `maxWriteBatchSize` from the Server

~~~javascript
const hello = db.adminCommand({ hello: 1 })
printjson({
  maxWriteBatchSize: hello.maxWriteBatchSize,
  maxBsonObjectSize: hello.maxBsonObjectSize,
  maxMessageSizeBytes: hello.maxMessageSizeBytes
})
~~~

Do not try to pack batches right up to the technical ceiling. MongoDB may split operations by command type, size, and internal limits; exact grouping is an implementation detail that can vary across drivers and versions.

### 9.3. Choosing an Application Batch Size

Splitting changes into chunks of **1,000 operations** is a reasonable starting point for benchmarking, **not a universal optimum**:

~~~javascript
const batchSize = 1000
const allOps = [] // Generated by the application pipeline, for illustration.

for (let start = 0; start < allOps.length; start += batchSize) {
  const batch = allOps.slice(start, start + batchSize)
  const result = products.bulkWrite(batch, { ordered: false })
  print("Batch " + start + " done: " + result.insertedCount)
}
~~~

This loop **lacks error handling**; it illustrates chunking only and must not be copied verbatim for critical migrations. In production, every batch needs a **batch ID**, result/exception capture, checkpoints, and idempotent retry/reconciliation.

Benchmark on realistic workloads to choose between 100, 500, 1,000, 5,000, or another size. Larger batches reduce per-request overhead, but also increase:

- client memory usage and per-round server work;
- wait time for a single call;
- the blast radius of partial results to reconcile on failure;
- replication/journal/cache pressure and write conflicts under concurrent writers.

Smaller batches simplify tracking and granular retries at the cost of more network round-trips. Balance across **throughput, p95 latency, error rates, memory, and replication lag**, not raw insert speed alone.

### 9.4. Ordered/Unordered on Sharded Clusters

On a sharded collection, operations may route to different shards. `ordered: true` enforces logical ordering, so a later operation may wait on an earlier one; unordered allows greater optimization and parallelism when operations are independent.

Pay attention to the **shard key**, query targeting, index filters, and hot documents. A bulk containing thousands of updates to **the same `_id`** does not magically parallelize effectively just because `ordered: false` is set. The goal is balanced write distribution, not storage-engine contention.

### 9.5. Indexes and Bulk Write Cost

Every insert, update, or delete may need to update multiple indexes. Unnecessary indexes inflate write overhead, while recklessly dropping indexes slows down reads. Before large updates or deletes:

~~~javascript
products.find(
  { category: "accessory", active: true },
  { _id: 1, sku: 1 }
).limit(20)

products.countDocuments({
  category: "accessory",
  active: true
})
~~~

Check **expected counts** before running broad operations. For slow filters, run `explain()` on an equivalent read query or check the profiler/slow query logs in the right environment to measure scan cost. **Never** treat bulk writes as a cure for an unindexed filter scanning millions of documents.

### 9.6. Do Not Assume Errors Return Every Detail

For massive bulks, `writeErrors` can grow large. MongoDB imposes limits and may **truncate** error text when error payloads exceed size thresholds. Therefore, alongside exception messages, your application should track **operation index, batch ID, and input ID** to identify affected records rather than relying exclusively on server error strings.

## 10. Retryable Writes, Network Errors, and Idempotency

Retries are one of the easiest places to introduce data corruption with `bulkWrite()`. There are **three distinct retry layers**:

1. **Internal storage engine retries:** MongoDB resolves certain transient write conflicts internally; the client may never see individual attempts.
2. **Driver/server retryable writes:** MongoDB documentation defines which operations can be automatically retried on network errors or failovers when conditions are met.
3. **Application retries:** jobs, schedulers, or clients explicitly re-send an entire request or batch after an error or timeout.

These three layers are **not equivalent**; never assume "because MongoDB has retryable writes, any batch is safe to replay from scratch."

### 10.1. Which Bulk Operations Are Automatically Retryable?

Per the **Retryable Writes** documentation, a `db.collection.bulkWrite()` is eligible for **retryable writes** only when all operations in the command are **single-document write operations** (and deployment/driver/write concern requirements are met):

- `insertOne`;
- `updateOne`;
- `replaceOne`;
- `deleteOne`.

If the batch contains **multi-document** operations such as `updateMany` or `deleteMany`, any server write command carrying them **is not guaranteed retryable under retryable writes**. Drivers may split the operation list into internal write commands, and retryability is evaluated per resulting command. Never assume a mixed bulk will **definitely** be retried as a whole.

Baseline prerequisites also include:

- A **replica set or sharded cluster** supporting sessions and retryable writes; **standalone** servers do not support this mechanism in the same way.
- An **acknowledged write concern**; `w: 0` disables retryable writes.
- Supported driver and server versions, with `retryWrites` enabled.
- **Writes inside a transaction are not individually retried** via retryable writes; only commit/abort follow transaction retry rules.

`retryWrites=true` does not guarantee **exactly-once business processing** across an entire workflow, especially when external side effects exist or higher layers re-submit requests.

### 10.2. A Timeout Does Not Tell You Whether the Write Happened

Suppose the application calls:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $inc: { stock: 5 } }
    }
  }
])
~~~

The server may have incremented `stock`, yet **lost the network connection before sending the response**. If the client blindly re-sends `$inc: 5`, `stock` increases twice. Along driver-supported retryable write paths, the driver and server correlate retries using session and statement identifiers. However, **manually retrying a brand-new request** after losing track of state is not treated as retrying the same statement.

### 10.3. Designing Idempotency with Target State

If the sync source provides the **exact inventory at time T** alongside a monotonically increasing version per product, you can use a **conditional update**:

~~~javascript
products.bulkWrite([
  {
    updateOne: {
      filter: {
        _id: "P-100",
        inventoryVersion: { $lt: 42 }
      },
      update: {
        $set: {
          stock: 125,
          inventoryVersion: 42
        }
      }
    }
  }
])
~~~

This works when the document already exists and `inventoryVersion` is a valid ordered number: if the job replays version 42, the document already at version 42 no longer matches. Note that this snippet **does not handle documents missing `inventoryVersion`**; schema and predicates must account for legacy records if present. If multiple producers can update inventory, establish a single authoritative version source so producers do not collide.

Another pattern uses **events with unique IDs**:

~~~javascript
// Illustrates the dedupe key only; insufficient on its own for a multi-document workflow.
db.getSiblingDB("bulk_lab").processedEvents.createIndex(
  { eventId: 1 },
  { unique: true }
)
~~~

Recording a unique `eventId` detects duplicate processing. However, if you must simultaneously insert the ledger entry and update stock in **two separate documents**, you need a transaction or a consistent compensating workflow; a unique index on the ledger alone does not make both changes atomic together.

### 10.4. Recovering After a Failed Bulk

For critical workloads, a recovery runbook might look like:

~~~text
Input batch B-123 stored with an ID for each operation
               |
        Call collection.bulkWrite
               |
        +------+------+
        |             |
       OK          Error / Timeout
        |             |
  Save checkpoint   Collect error codes, indexes,
                    partial counts if available
                      |
               Reconcile DB state using
               business key / event ID
                      |
             Retry only missing operations
             or idempotent ones
~~~

When using unordered execution, never interpret "reached operation index 150" as meaning indexes 0–149 all succeeded. Outcomes in unordered mode can be non-contiguous; maintain a mapping from **operation index → business identity** and inspect actual DB state.

## 11. Transactions and bulkWrite: When Must the Whole Group Commit or Abort?

**`bulkWrite()` is not a transaction by default.** For example, deleting 10 documents and inserting 3 documents in one bulk can expose **intermediate states** to other clients while operations execute. `ordered: true` does not prevent that.

### 11.1. When a Bulk Does Not Need a Transaction

A bulk does not require group-wide atomicity when:

- Operations are independent, such as refreshing metadata on 500 distinct products.
- Partial results are acceptable and errors can be resolved via retries or reconciliation.
- Work can span multiple checkpointed batches.
- Intermediate states do not violate critical business invariants.

These are ideal candidates for `ordered: false` when operations are genuinely independent.

### 11.2. When a Multi-Document Transaction Is Needed

Suppose you must:

1. Deduct 10 units from inventory document `P-100`.
2. Create reservation document `R-100`.
3. Update order `O-100` to `RESERVED`.

If **all three committing or aborting together** is a hard invariant, a single collection-scoped `bulkWrite()` cannot satisfy it—especially across **multiple collections**. Use a transaction on a supported deployment, or redesign the domain workflow.

Simple **single-collection** example showing a bulk inside a session transaction:

~~~javascript
// Run on a replica set/sharded deployment supporting transactions.
// Demo uses a dedicated database. Production transaction retry logic omitted.
const session = db.getMongo().startSession()
const coll = session.getDatabase("bulk_lab").transactionDemo

try {
  session.startTransaction({
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })

  coll.bulkWrite([
    {
      insertOne: {
        document: { _id: "TX-A", value: 1 }
      }
    },
    {
      updateOne: {
        filter: { _id: "TX-A" },
        update: { $inc: { value: 1 } }
      }
    }
  ], { ordered: true })

  session.commitTransaction()
  print("Transaction committed")
} catch (error) {
  try { session.abortTransaction() } catch (_) {}
  print("Transaction did not complete normally: " + error.message)
} finally {
  session.endSession()
}
~~~

This is a **session/transaction structural example**, not a full production retry template. Do not set `writeConcern` on **individual bulk calls inside a transaction**; configure write concern at the **transaction/commit** level per MongoDB docs. On standalone servers or unsupported topologies, this example will fail.

### 11.3. Errors Inside vs. Outside a Transaction

Outside a transaction:

- **Ordered** stops after a write error; preceding operations remain committed.
- **Unordered** continues attempting remaining operations even if some fail.

Inside a multi-document transaction, a write error can cause the **transaction to abort**; never view unordered mode as a way to "skip errors and commit the valid operations" inside a transaction. Drivers and versions enforce specific rules when exceptions occur mid-transaction; follow the transaction API contract.

### 11.4. Retrying Transactions

MongoDB distinguishes:

| Signal | Right mental model |
|---|---|
| `TransientTransactionError` | The transaction failed transiently; you may need to re-run **the entire transaction**. |
| `UnknownTransactionCommitResult` | Uncertain whether commit succeeded; **retry the commit** per driver API rather than blindly re-running business logic. |
| `DuplicateKey` or validation error | Invalid data or constraint violation; do not blindly retry. |
| Transaction too large or too long | Shrink transaction scope/duration; identical retries usually fail again. |

Drivers offering a **convenient transaction API** can automatically retry based on error labels. Because the callback may execute multiple times, never send emails, call payment gateways, or emit unguarded external messages inside that callback.

### 11.5. Oversized Bulks Should Not Be Forced into One Giant Transaction

A transaction holds snapshots, locks, and resources within strict time limits; massive update sets strain cache and heighten conflict rates. For checkpointable, batch-recoverable migrations, **many small idempotent bulks** are usually far better than one giant transaction intended to "make everything succeed together."

When a genuine multi-document invariant exists, include **only the essential documents** in the transaction. Align batches with business transaction boundaries, not arbitrary operation counts.

## 12. MongoDB 8.0+: Distinguishing Multi-Namespace `Mongo.bulkWrite()`

MongoDB **8.0** adds the `bulkWrite` database command and `Mongo.bulkWrite()` in `mongosh`, letting a single call write across **multiple collections and even multiple databases**.

### 12.1. Direct Comparison

| Aspect | `db.collection.bulkWrite()` | `Mongo.bulkWrite()` |
|---|---|---|
| Scope | **Single collection**. | **Multiple namespaces** as `database.collection`. |
| Version | Available prior to 8.0. | Requires **MongoDB 8.0+**. |
| Operation shape | `{ insertOne: { document: ... } }`. | `{ namespace: "...", name: "insertOne", document: ... }`. |
| Operation types | `InsertOne`, `UpdateOne`, `UpdateMany`, `ReplaceOne`, `DeleteOne`, `DeleteMany`. | Supports the corresponding operations via the `name` field. |
| Options/results | Collection API; results like `insertedIds`/`upsertedIds`. | Connection API; offers `verboseResults` and option-dependent result maps. |
| Transactions | Usable with sessions/transactions on supported deployments. | Inside transactions, use `Session.bulkWrite()` per docs. |

Do not confuse `db.collection.bulkWrite()` with MongoDB 8.0's raw `bulkWrite` database command. The raw command uses `ops` and `nsInfo` structures, differing from both `mongosh` helpers.

### 12.2. Multi-Collection Example

~~~javascript
// Runs on MongoDB Server 8.0+ only.
const mongo = db.getMongo()

const result = mongo.bulkWrite([
  {
    namespace: "bulk_lab.products",
    name: "insertOne",
    document: {
      _id: "P-MULTI-1",
      name: "Additional Product",
      stock: 2
    }
  },
  {
    namespace: "bulk_lab.auditEvents",
    name: "insertOne",
    document: {
      _id: "E-MULTI-1",
      type: "IMPORT",
      productId: "P-MULTI-1",
      at: new Date()
    }
  },
  {
    namespace: "bulk_lab.products",
    name: "updateOne",
    filter: { _id: "P-MULTI-1" },
    update: { $set: { active: true } }
  }
], {
  ordered: true,
  verboseResults: true
})

printjson(result)
~~~

The call above writes to both **products** and **auditEvents**. Yet the critical rule still holds: **a single `Mongo.bulkWrite()` call does not automatically provide multi-collection atomicity**. If inserting the product succeeds and inserting the audit event fails, `ordered: true` merely halts subsequent steps; to commit or abort both together, use a **transaction** or an appropriate event-recording pattern.

`Mongo.bulkWrite()` returns summary counters and, with `verboseResults: true`, per-operation result maps. Do **not** assume the exact same response shape as `db.collection.bulkWrite()`; for instance, `upsertedIds`/`insertedIds` on the collection API differ from verbose results on the new API. Check docs for your exact server and `mongosh` versions.

### 12.3. `Session.bulkWrite()` for Multi-Namespace Transactions

In `mongosh`, MongoDB 8.0+ documentation directs you to **`Session.bulkWrite()`** to bind a multi-namespace bulk to a session/transaction. When using it in a transaction:

- The deployment must support multi-document transactions.
- Manage start/commit/abort through the session.
- Handle transaction retries per error labels and driver/shell APIs rather than blindly replaying uncertain commits.
- Include only operations belonging to the same atomic business unit.

Never take an operations array formatted for `Mongo.bulkWrite()` and pass it directly to `db.collection.bulkWrite()`: the two APIs expect different object shapes. This is a common mistake when copying MongoDB 8.0 examples into code using the older collection API.

## 13. Using Collection bulkWrite with the MongoDB Java Sync Driver

In Java, the MongoDB Sync Driver provides **`MongoCollection.bulkWrite()`**, accepting **`List<WriteModel<TDocument>>`** and `BulkWriteOptions`. This is the collection-scoped counterpart to `db.collection.bulkWrite()` in `mongosh`.

### 13.1. Mapping from mongosh to Java

| Mongosh operation | Java driver model |
|---|---|
| `{insertOne:{document: ...}}` | `new InsertOneModel<>(document)` |
| `{updateOne:{filter,update}}` | `new UpdateOneModel<>(filter, update)` |
| `{updateMany:{filter,update}}` | `new UpdateManyModel<>(filter, update)` |
| `{replaceOne:{filter,replacement}}` | `new ReplaceOneModel<>(filter, replacement)` |
| `{deleteOne:{filter}}` | `new DeleteOneModel<>(filter)` |
| `{deleteMany:{filter}}` | `new DeleteManyModel<>(filter)` |
| `{ordered:false}` | `new BulkWriteOptions().ordered(false)` |
| `{upsert:true}` on update | `new UpdateOptions().upsert(true)` |

### 13.2. Java Example: Mixing All Six Write Types

Assume `database` is a `com.mongodb.client.MongoDatabase` connected to the test database:

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;
import com.mongodb.bulk.BulkWriteResult;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.DeleteManyModel;
import com.mongodb.client.model.DeleteOneModel;
import com.mongodb.client.model.InsertOneModel;
import com.mongodb.client.model.ReplaceOneModel;
import com.mongodb.client.model.UpdateManyModel;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.UpdateOptions;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.Arrays;
import java.util.Date;
import java.util.List;

import static com.mongodb.client.model.Filters.and;
import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.combine;
import static com.mongodb.client.model.Updates.inc;
import static com.mongodb.client.model.Updates.set;
import static com.mongodb.client.model.Updates.setOnInsert;

// database: MongoDatabase pointing to "bulk_lab".
MongoCollection<Document> products = database.getCollection("products");

List<WriteModel<Document>> operations = Arrays.asList(
    new InsertOneModel<>(
        new Document("_id", "P-J400")
            .append("sku", "NOTE-J400")
            .append("name", "Java Notebook")
            .append("category", "accessory")
            .append("stock", 20)
            .append("active", true)
    ),

    new UpdateOneModel<>(
        eq("_id", "P-100"),
        combine(
            inc("stock", 5),
            set("lastRestockedAt", new Date())
        )
    ),

    new UpdateManyModel<>(
        and(
            eq("category", "accessory"),
            eq("active", true)
        ),
        set("promotionEligible", true)
    ),

    new ReplaceOneModel<>(
        eq("_id", "P-300"),
        new Document("_id", "P-300")
            .append("sku", "PEN-300")
            .append("name", "Normalized Gel Pen")
            .append("stock", 15)
            .append("active", true)
    ),

    new DeleteOneModel<>(
        and(
            eq("_id", "P-OLD1"),
            eq("legacy", true)
        )
    ),

    new DeleteManyModel<>(
        and(
            eq("active", false),
            eq("archived", true)
        )
    ),

    new UpdateOneModel<>(
        eq("_id", "P-J500"),
        combine(
            setOnInsert("sku", "BAG-J500"),
            setOnInsert("name", "Java Bag"),
            setOnInsert("stock", 8),
            setOnInsert("active", true)
        ),
        new UpdateOptions().upsert(true)
    )
);

BulkWriteOptions options = new BulkWriteOptions().ordered(true);

try {
    BulkWriteResult result = products.bulkWrite(operations, options);

    System.out.println("inserted=" + result.getInsertedCount());
    System.out.println("matched=" + result.getMatchedCount());
    System.out.println("modified=" + result.getModifiedCount());
    System.out.println("deleted=" + result.getDeletedCount());
    System.out.println("upserts=" + result.getUpserts().size());
} catch (MongoBulkWriteException ex) {
    for (BulkWriteError error : ex.getWriteErrors()) {
        System.err.println(
            "operation index=" + error.getIndex()
            + ", code=" + error.getCode()
        );
    }
    // Inspect partial successes via ex.getWriteResult()
    // when provided by the driver, and check writeConcernError separately.
    // Do not blindly retry the whole list if it contains $inc or deleteMany.
    throw ex;
}
~~~

This is an **API illustration**, not a complete production job: `database` must be initialized from a properly managed `MongoClient` lifecycle, and partial-failure policy must be defined. Do not run repeatedly on the same demo collection, as inserting `P-J400` will fail with a duplicate key error on the second run.

### 13.3. Notes When Using POJOs Instead of `Document`

If the collection is `MongoCollection<Product>` backed by a POJO codec, models become `WriteModel<Product>`, while filters and updates still serialize per driver mapping. With class inheritance, annotations, field aliases, or `_id` mapping, inspect the actual BSON emitted by the codec. Never pass an incomplete POJO to `replaceOne` expecting the database to retain omitted fields.

### 13.4. Reading Errors in the Java Driver

With `MongoBulkWriteException`, distinguish:

- **`getWriteErrors()`**: list of per-operation errors; `getIndex()` maps back to the input list element.
- **`getWriteConcernError()`**: write acknowledgment error, if any.
- **`getWriteResult()`**: results from operations that succeeded, per the API contract.

Exact details depend on driver version. For robust handling, record **batchId + operationId + business key** before calling `bulkWrite`; the exception is only part of the evidence. Never log full documents containing personal data just to debug a duplicate key error.

### 13.5. Bulk API in Spring Data MongoDB

In Spring Data, `MongoTemplate.bulkOps(...)` provides a builder API distinct from `MongoCollection.bulkWrite()`. Keep in mind:

- Operation types and options may differ from using the Java Sync Driver directly.
- `BulkMode.ORDERED` and `BulkMode.UNORDERED` express similar ordering intent, but verify behavior against your framework version.
- Entity lifecycle callbacks, auditing, and versioning have specific limitations on bulk operations per Spring Data documentation.
- When relying on optimistic locking via `@Version`, do not assume bulk operations automatically apply all lifecycle and concurrency checks of `save()`.

Whenever unsure what an abstraction does, inspect **the BSON command actually sent** and check the docs for your dependency version. Do not copy a MongoDB shell snippet and assume 100% behavioral parity with a framework wrapper.

## 14. Workflow for Running a Safe Data-Mutation Bulk

A reliable bulk job should be designed as a **recoverable data-mutation pipeline**, not merely a `for` loop gathering write models.

### 14.1. Step 1 — Define Input and Identity

For each operation, track:

~~~text
batchId: import-2026-11-14-001
operationIndex: 17
operationId: inventory-event-987
type: updateOne
targetBusinessKey: P-100
expectedVersion: 42
desiredEffect: set stock = 125
~~~

**Operation index** correlates exceptions; **operationId/business key** enables real-world reconciliation after errors or replays. When input comes from Kafka, queues, or ETL files, preserve stable source IDs and explicit checkpoints.

### 14.2. Step 2 — Verify Update/Delete Scope

Before `updateMany`/`deleteMany`, query counts and samples:

~~~javascript
const lab = db.getSiblingDB("bulk_lab")
const filter = {
  active: false,
  archived: true
}

print("Expected candidates=" + lab.products.countDocuments(filter))
printjson(
  lab.products.find(filter, { _id: 1, sku: 1, active: 1 })
    .limit(20)
    .toArray()
)
~~~

Pre-flight counts and actual deleted counts can **differ** if concurrent writes occur between the two moments. Pre-flighting does not lock the result set; if you must delete only an exact approved snapshot, capture **an explicit list of IDs**, enforce `version`/`updatedAt` predicates, or use an appropriate transaction.

### 14.3. Step 3 — Use Protective Filter Conditions

Instead of:

~~~javascript
{
  deleteMany: {
    filter: { active: false }
  }
}
~~~

add stricter guards:

~~~javascript
{
  deleteMany: {
    filter: {
      active: false,
      archived: true,
      archivedAt: { $lt: ISODate("2025-01-01T00:00:00Z") },
      legalHold: { $ne: true }
    }
  }
}
~~~

However, a longer filter is **only safe if it matches policy accurately**. For instance, `legalHold: {$ne:true}` matches documents where `legalHold` is missing; if policy requires explicit `false`, use `legalHold: false` alongside schema enforcement. Never treat `$ne` as automatically rejecting records with missing fields.

### 14.4. Step 4 — Choose Ordered vs. Unordered Intentionally

~~~text
Do operations have dependencies?
    |
    +-- Yes --> ordered: true
    |           or combine into one atomic update/transaction
    |
    +-- No --> consider ordered: false for higher throughput
                  but partial-result handling is mandatory
~~~

**Dependencies** can be data-based (updating a newly inserted document), state-machine ordered (`PENDING` → `PAID` → `SHIPPED`), or business-rule driven. If ordering is required, running unordered can corrupt state even if every individual operation succeeds.

### 14.5. Step 5 — Design Chunking and Checkpoints

For hundreds of thousands of operations, split into manageable batches:

~~~javascript
function runBatches(collection, batches) {
  for (const batch of batches) {
    // batch must carry an ID, operations, and external logging/checkpoint.
    try {
      const result = collection.bulkWrite(
        batch.operations,
        { ordered: false }
      )
      printjson({
        batchId: batch.id,
        inserted: result.insertedCount,
        matched: result.matchedCount,
        deleted: result.deletedCount
      })
      // Production: save checkpoint after verifying the result.
    } catch (err) {
      print("Batch failed: " + batch.id)
      print(err.message)
      // Production: reconcile per operation; do not mark complete automatically.
      throw err
    }
  }
}
~~~

This snippet illustrates **the control-loop structure** only; `catch` outcomes must be persisted in durable state storage, not just printed to `stdout`. If the job crashes after the server writes but before the checkpoint saves, re-runs must **reconcile/be idempotent** rather than assuming the batch never executed.

### 14.6. Step 6 — Observe and Reconcile

Track at least:

| Metric | Question |
|---|---|
| `insertedCount` / `upsertedCount` | How many documents were newly created? |
| `matchedCount` / `modifiedCount` | How many documents matched, and how many actually changed? |
| `deletedCount` | Does the deleted count fall within policy limits? |
| Bulk error rate by code | Are duplicate keys, validation errors, or infra errors occurring? |
| p95 latency per batch | Are batches breaching SLO limits? |
| Replication lag / disk / CPU | Is the batch straining cluster health? |
| Write conflicts / lock waits | Are there hot documents or unusual contention? |
| Invalid/missing counts post-import | Did schema drift or omissions happen? |
| Job checkpoint + reconcile count | Were any operations dropped or duplicated after errors? |

For deletions, retain audit records meeting legal and domain requirements. Never rely on `deletedCount` alone to prove **the right entities** were deleted; maintain an ID list or query evidence.

## 15. Common Misconceptions

| Misconception | Reality |
|---|---|
| "`bulkWrite` is a transaction." | False. A bulk can routinely succeed partially. |
| "With `ordered: true`, an error rolls back prior steps." | False. Ordered halts subsequent operations; it does not undo earlier ones. |
| "`ordered: false` is just ordered but faster." | Unordered can **reorder** execution; dependencies may break. |
| "`bulkWrite` always runs in a single server command." | The driver may split it into multiple server batches. |
| "`insertOne` in bulk doesn't need the `document` key." | The required shape is `{insertOne:{document:{...}}}`. |
| "`updateOne` and `updateMany` differ only in expected count." | One updates at most one document; the other updates **every matching document**. |
| "`replaceOne` keeps fields omitted from `replacement`." | False; replace swaps the entire body aside from `_id` rules. |
| "`deleteOne` picking an arbitrary document is always fine." | Use an identifying filter to delete the exact target. |
| "`deleteMany` with an empty filter is harmless." | `{}` can wipe the entire collection. |
| "`matchedCount` always equals `modifiedCount`." | No-op updates match without modifying. |
| "`upsertedCount` counts as `insertedCount`." | Upserts are counted separately from `insertOne`. |
| "`upsert: true` turns `updateMany` into inserting many records." | On zero matches, `updateMany` upsert creates **one** document. |
| "If no exception appeared, retry the whole bulk to be sure." | Replaying `$inc` can double-increment; understand acknowledgments and retry policies. |
| "`retryWrites=true` auto-retries bulks containing `updateMany`." | Multi-document writes are outside standard retryable-write guarantees. |
| "`writeConcern: 'majority'` gives bulk-wide atomicity." | Write concern governs durability acknowledgment, not transactions. |
| "`Mongo.bulkWrite` and `collection.bulkWrite` share the same write model." | Their operation shapes and scopes differ. |
| "`bypassDocumentValidation` skips unique indexes." | False; unique indexes and other constraints still apply. |
| "An error at operation index 5 means 0–4 all succeeded." | Under unordered execution there is no order guarantee; inspect results and reconcile. |
| "The biggest possible bulk is always fastest." | Huge batches inflate error-recovery blast radius, memory, and latency; benchmark your workload. |
| "A write concern error means nothing was written." | Uncertain. Writes may have applied without meeting the requested acknowledgment threshold. |

## 16. Frequently Asked Questions

**Q1. Can I mix inserts, updates, replacements, and deletes in one bulk?**  
Yes. `db.collection.bulkWrite()` accepts an array of models spanning all six operation types against **the same collection**.

**Q2. How does `bulkWrite()` differ from `insertMany()`?**  
`insertMany()` only **inserts multiple documents**; `bulkWrite()` mixes **inserts, updates, replacements, and deletes**. If you only need to insert documents, `insertMany()` is usually simpler.

**Q3. If one operation in a bulk fails, do the others still run?**  
With `ordered: true`, a write error stops subsequent operations. With `ordered: false`, independent remaining operations continue executing. Neither automatically rolls back already-committed writes outside a transaction.

**Q4. Can I replace `updateOne` with `replaceOne`?**  
Only when you intend to **replace the entire document** and provide every field you want to keep. If you only want to modify a few fields, use update operators.

**Q5. Does `deleteMany` delete all documents atomically?**  
No; each individual document deletion is atomic, not the entire set. If the domain requires all-or-nothing semantics, design an explicit transaction and account for its cost.

**Q6. Is unordered safe for two updates targeting the same `_id`?**  
Only if the updates are **commutative/order-independent** and verified. Two different `$set` values on the same field can yield different final states depending on execution order.

**Q7. Why can `matchedCount` exceed `modifiedCount`?**  
Because a matched document may already hold the target field values, resulting in no modification. A single document can also be matched by **multiple operations** within the same bulk.

**Q8. Can I bulkWrite across multiple collections in MongoDB 7.0?**  
Not via multi-namespace `Mongo.bulkWrite()`, which was introduced in MongoDB 8.0. In MongoDB 7.0, call `db.collection.bulkWrite()` per collection; if multi-collection atomicity is required, use a supported transaction.

**Q9. If the client times out, should I re-run the whole batch?**  
Not automatically. Classify the write types, check driver/server retryability, and reconcile actual DB state. With `$inc` or `deleteMany`, blind replays can cause extra side effects.

**Q10. Does `bulkWrite` preserve order when sharded?**  
`ordered: true` preserves logical execution order across operations; `ordered: false` allows out-of-order execution. Physical routing and execution depend on shard keys, `mongos` routing, and the driver.

**Q11. Should I drop all indexes to speed up bulk inserts?**  
There is no blanket rule. Indexes add write overhead, yet enforce queries and unique constraints. For massive imports, follow an evaluated data/index runbook rather than dropping indexes that guard business invariants just for speed.

**Q12. Does `bulkWrite` prevent duplicate key errors?**  
No. Unique indexes and `_id` checks behave just like standalone CRUD commands; `ordered: false` simply lets valid operations proceed rather than fixing duplicate data.

## 17. Practice Exercises with Suggested Answers

Use the `bulk_lab` database from earlier sections. Update/delete exercises must be run against a **dedicated test collection** or freshly reset fixture data; these commands actually mutate/delete documents in the target collection. Never use production to test demo queries.

### Exercise 1 — Mixing Insert and Update on One Document

Requirement: insert `_id = "TASK-1"` with `count: 0`, then increment `count` by 2 in **the same `bulkWrite`**. The increment must happen after the insert.

**Answer:**

~~~javascript
db.getSiblingDB("bulk_lab").taskDemo.bulkWrite([
  {
    insertOne: {
      document: { _id: "TASK-1", count: 0 }
    }
  },
  {
    updateOne: {
      filter: { _id: "TASK-1" },
      update: { $inc: { count: 2 } }
    }
  }
], { ordered: true })
~~~

The final document is expected to have `count: 2`. With `ordered: false`, there is no guarantee the update executes after the insert.

### Exercise 2 — Replace vs. Update

Initial document:

~~~javascript
{ _id: "A", name: "An", city: "Hanoi", tier: "GOLD" }
~~~

Two operations:

~~~javascript
// Operation X
{ updateOne: {
    filter: { _id: "A" },
    update: { $set: { city: "Da Nang" } }
} }

// Operation Y
{ replaceOne: {
    filter: { _id: "A" },
    replacement: { _id: "A", city: "Da Nang" }
} }
~~~

**Question:** how does the final document differ if only one of the two runs?

**Answer:** X preserves `name` and `tier`, updating only `city`. Y replaces the whole document, leaving only `_id` and `city`.

### Exercise 3 — Stopping on Duplicate Key

Collection contains only `{_id: "A"}`, and the bulk is:

~~~javascript
[
  { insertOne: { document: { _id: "B" } } },
  { insertOne: { document: { _id: "A" } } },
  { insertOne: { document: { _id: "C" } } }
]
~~~

**Question:** what happens under ordered vs. unordered?

**Answer:**

- `ordered: true`: `B` is inserted, `A` fails with duplicate key, `C` is skipped; documents `A` and `B` exist.
- `ordered: false`: `A` still fails, while `B` and `C` can succeed; do not infer execution order from array position.
- In both cases, `bulkWrite` can throw an error **after partial writes have occurred**.

### Exercise 4 — Is a Multi-Delete Filter Safe?

A job needs to delete all products archived before Jan 1, 2025, while never deleting products with `legalHold: true`.

**Suggested answer:**

~~~javascript
const filter = {
  archived: true,
  archivedAt: { $lt: ISODate("2025-01-01T00:00:00Z") },
  legalHold: false
}

db.getSiblingDB("bulk_lab").products.bulkWrite([
  { deleteMany: { filter } }
])
~~~

Do not use `legalHold: {$ne:true}` if documents missing the `legalHold` field must **not** be deleted per policy. Pre-flight with `countDocuments(filter)` and sample IDs first.

### Exercise 5 — Upsert with `$setOnInsert`

Design an operation that creates a product if missing, yet **never overwrites `createdAt`** if the product already exists.

**Answer:**

~~~javascript
db.getSiblingDB("bulk_lab").products.bulkWrite([
  {
    updateOne: {
      filter: { _id: "P-TASK5" },
      update: {
        $set: { active: true },
        $setOnInsert: {
          sku: "TASK-5",
          createdAt: new Date()
        }
      },
      upsert: true
    }
  }
])
~~~

If unmatched, it inserts a new document. If matched, only `$set active` runs; `$setOnInsert` leaves any existing `createdAt` untouched.

### Exercise 6 — `matchedCount` and `modifiedCount`

Suppose `P-100` already has `status: "ACTIVE"`. A bulk runs two `updateOne` operations targeting `P-100`, each setting `$set: {status:"ACTIVE"}`. What counters do you expect?

**Answer:** `matchedCount = 2` because both operations match; `modifiedCount = 0` since neither changes the field. One document can be matched multiple times within the same bulk.

### Exercise 7 — Matching the Right Element in an Array Update

In the `orders` collection:

~~~javascript
{
  _id: "O-ARRAY",
  items: [
    { sku: "BK-01", packed: false },
    { sku: "PN-02", packed: false }
  ]
}
~~~

Write an update model inside a bulk that sets `packed: true` only for item `BK-01`.

**Answer:**

~~~javascript
{
  updateOne: {
    filter: { _id: "O-ARRAY" },
    update: {
      $set: { "items.$[line].packed": true }
    },
    arrayFilters: [
      { "line.sku": "BK-01" }
    ]
  }
}
~~~

Place this model inside the array passed to `db.orders.bulkWrite([...])`. `arrayFilters` belongs to the **update operation**, not the shared `options` object containing `ordered`.

### Exercise 8 — `updateMany` and Upsert

No document matches `{sku:"UNKNOWN"}`. How many documents will `updateMany` with `upsert:true` create?

**Answer:** When zero documents match, it creates **one** document. `upsert` does not turn an `updateMany` into an `insertMany`.

### Exercise 9 — Retrying After a Network Timeout

A bulk contains an `updateOne` with `$inc:{stock:10}` and a `deleteMany`. The client times out without knowing the outcome. Is it safe to re-send the entire batch verbatim?

**Answer:** Not automatically safe. `$inc` could increment again if the prior call succeeded; `deleteMany` could delete additional documents that became eligible between attempts. Mixed bulks containing multi-document writes are not guaranteed retryable like single-document-only bulks. Reconcile by business key/event ID and replay only idempotent operations.

### Exercise 10 — Choosing Transactions vs. Independent Bulks

A workflow must deduct stock from `products` and insert a reservation into `reservations` so either both succeed or neither appears. Do two consecutive `bulkWrite` calls meet this requirement?

**Answer:** No. Two separate calls share no atomicity. Use a transaction on a supporting deployment or an appropriate workflow/compensation design; MongoDB 8.0's multi-namespace `Mongo.bulkWrite()` **does not replace transactions** either.

### Exercise 11 — Moving from Collection API to Multi-Namespace API

Write a `Mongo.bulkWrite()` on MongoDB 8.0+ inserting into `products` and `auditEvents`.

**Answer:**

~~~javascript
db.getMongo().bulkWrite([
  {
    namespace: "bulk_lab.products",
    name: "insertOne",
    document: {
      _id: "P-TASK11",
      name: "Product 11"
    }
  },
  {
    namespace: "bulk_lab.auditEvents",
    name: "insertOne",
    document: {
      _id: "EV-TASK11",
      productId: "P-TASK11",
      event: "CREATED"
    }
  }
], { ordered: true })
~~~

Unlike the collection API, each operation carries **`namespace` and `name`**. If both inserts must commit or abort together, use a transaction/`Session.bulkWrite()` per the docs.

### Exercise 12 — Batch Splitting and Error Recovery

An import file has 250,000 operations, each updating a distinct product. The driver supports batching. Propose a recoverable execution plan.

**Suggested answer:**

1. Assign a **batchId** and **operationId/business key** to every operation; ensure input can be reconstructed.
2. Split into application-managed chunks, e.g., **1,000–5,000 operations** per chunk for observability; benchmark on real load.
3. Use `ordered:false` **only if** operations are independent and order-agnostic.
4. On failure, capture `writeErrors` and partial results, then reconcile DB state by ID.
5. Perform bounded retries only on operations not yet in the target state; never blindly replay `$inc`.
6. Persist checkpoints durably **after reconciliation** before advancing to the next batch.
7. Monitor latency, write conflicts, replication lag, memory, and total modified documents.

### Exercise 13 — Correctness with Unordered

Given two updates targeting `P-100`:

~~~javascript
[
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { state: "PENDING" } }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-100" },
      update: { $set: { state: "SHIPPED" } }
    }
  }
]
~~~

**Question:** can this run unordered since each update only touches one document?

**Answer:** No, if the final state must be `SHIPPED`. The two operations are **order-dependent**; unordered makes no ordering guarantee. Use ordered execution or, even better, conditional state updates enforcing valid state transitions.

### Exercise 14 — One Validation Failure

An unordered bulk has three inserts: one violates the collection schema, while two are valid. Is the whole batch guaranteed to roll back?

**Answer:** No. The two valid inserts can still succeed while the invalid one is rejected per `validationAction`. Inspect the bulk exception to identify succeeded vs. failed elements rather than treating the batch as a transaction.

## 18. Quick Selection Table

| Need | Recommended choice | Caveat |
|---|---|---|
| Insert many documents only, no updates/deletes | `insertMany()` | Handle duplicates and `ordered` per import needs. |
| Mix insert/update/delete on **one collection** | `db.collection.bulkWrite()` | Not automatically atomic across the batch. |
| Independent ops; finish as much as possible despite errors | `bulkWrite(...,{ordered:false})` | Order is non-deterministic; handle partial results. |
| Order-dependent operations | `bulkWrite(...,{ordered:true})` | Ordered still does not roll back on errors. |
| Change a few fields while keeping the rest | `updateOne`/`updateMany` | `replaceOne` drops omitted fields. |
| Sync "update if present, insert if missing" | `upsert:true` with unique identity | Watch for races and update idempotency. |
| Delete one specific record | `deleteOne` filtered by ID | Broad filters can delete the wrong document. |
| Delete a group per policy | `deleteMany` with preflight/audit | Account for retention and recovery. |
| Write across multiple collections/databases in 8.0+ | `Mongo.bulkWrite()` | Operation objects differ from collection API; not transactional by default. |
| Commit/abort multiple documents together | Multi-document transaction | Resource limits and dedicated retry/commit semantics apply. |
| Huge resumable migration across errors | Small bulks + checkpoints/idempotency | Reconcile operations after partial failures. |

## 19. Official MongoDB Documentation

The following pages come from the MongoDB Database Manual and driver docs. In production, verify against your exact **MongoDB Server version**, `mongosh` version, and **driver version**. Links under `/docs/manual/` track the current release; use `/docs/v7.0/` or `/docs/v8.0/` to pin a release line.

1. [`db.collection.bulkWrite()` — mongosh method](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/) — syntax for the six operation models, `ordered`, `writeConcern`, counters, batching, and errors.
2. [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/) — overview of ordered/unordered execution, collection scope, and 8.0 multi-namespace support.
3. [`Mongo.bulkWrite()` — mongosh method](https://www.mongodb.com/docs/manual/reference/method/mongo.bulkwrite/) — `namespace`/`name` format, `verboseResults`, and multi-collection examples.
4. [`bulkWrite` Database Command](https://www.mongodb.com/docs/manual/reference/command/bulkwrite/) — raw `ops`/`nsInfo` command introduced in MongoDB 8.0; distinct from the collection helper.
5. [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — prerequisites and limitations for bulks containing `updateMany`/`deleteMany`.
6. [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity, transaction retries, and lifecycle.
7. [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — `w`, `j`, and acknowledgment levels.
8. [Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/) — `maxWriteBatchSize`, BSON document limits, and system thresholds.
9. [`db.collection.insertMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.insertMany/) — when only inserting multiple documents.
10. [`db.collection.updateOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/), [`updateMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/) — update operators, upserts, array filters, and atomicity.
11. [`db.collection.replaceOne()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.replaceOne/) — differences between full replacement and modifier updates.
12. [`db.collection.deleteMany()`](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/) — multi-document delete scope and concurrency effects.
13. [Bulk Write Operations — Java Sync Driver](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/) — `WriteModel`, `BulkWriteResult`, `MongoBulkWriteException`, and driver APIs.
14. [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — when bulk writes must satisfy validators or use authorized bypass.
15. [MongoDB 7.0 — Bulk Write Operations](https://www.mongodb.com/docs/v7.0/core/bulk-write-operations/) and [MongoDB 8.0 — `db.collection.bulkWrite()`](https://www.mongodb.com/docs/v8.0/reference/method/db.collection.bulkWrite/) — version-pinned reference examples.

**Conclusion:** `bulkWrite` is a tool for **organizing and optimizing write submission**, not an automatic guarantee that every change succeeds together. Sound design requires choosing accurately among **the six operation types**, identifying **ordering dependencies**, preparing for **partial results**, distinguishing **retryable from idempotent**, and setting **transaction boundaries** around genuine business invariants. When deleting or updating many documents, an accurate filter and reliable reconciliation matter far more than cramming as many commands as possible into one batch.
