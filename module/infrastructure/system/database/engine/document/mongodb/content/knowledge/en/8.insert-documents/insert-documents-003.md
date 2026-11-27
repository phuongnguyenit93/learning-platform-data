# Ordered and Unordered Multi-Document Writes

When adding hundreds or thousands of documents to MongoDB, sending `insertOne()` calls one by one can generate many round trips between the application and the database. MongoDB provides `insertMany()` to add multiple documents in a single API-level operation, and `bulkWrite()` to combine multiple insert, update, replace, or delete operations.

An important option of both APIs is **`ordered`**:

- **`ordered: true`**: executes operations in the provided order and **stops at the first write error** in a normal sequence of operations.
- **`ordered: false`**: allows continuing to process remaining operations even when one or more operations fail; MongoDB **may reorder or execute them in parallel** if the environment permits, so execution order must not be relied upon as a guarantee.

Deciding between ordered and unordered affects **continuation after errors, dependencies between documents, throughput, retry strategies, and result reconciliation**. It does **not** automatically turn a multi-document batch into an atomic transaction.

## 1. From `insertOne()` to `insertMany()`

### 1.1. Adding Documents One by One

Suppose a system inserts a list of products into the `products` collection:

```javascript
db.products.insertOne({
  _id: "P1001",
  name: "Keyboard",
  price: NumberDecimal("350000.00")
});

db.products.insertOne({
  _id: "P1002",
  name: "Mouse",
  price: NumberDecimal("180000.00")
});
```

Each command is sent and processed as a separate operation. This is simple when the record count is small or each record needs separate business handling, but with thousands of records it can incur extra round trips and connection/command management overhead.

### 1.2. Adding Multiple Documents

```javascript
db.products.insertMany(
  [
    {
      _id: "P1003",
      name: "Monitor",
      price: NumberDecimal("2900000.00")
    },
    {
      _id: "P1004",
      name: "Headphones",
      price: NumberDecimal("650000.00")
    },
    {
      _id: "P1005",
      name: "Webcam",
      price: NumberDecimal("900000.00")
    }
  ],
  { ordered: true }
);
```

General syntax:

```javascript
db.collection.insertMany(
  [ document1, document2, document3 ],
  {
    ordered: true,
    // writeConcern, bypassDocumentValidation, comment...
  }
);
```

`insertMany()` accepts **an array of documents**. By default, `ordered` is `true`. When a document lacks `_id`, the driver or MongoDB adds an appropriate identifier; you should not assume generated `_id`s correspond strictly to business timestamp order.

Full success typically returns a result containing `insertedIds` details or insert counts depending on the API/driver. However, the result shape and error object can differ across `mongosh`, the Java driver, the Node.js driver, and versions; **the application must follow the API contract of the driver in use**, rather than relying on terminal error message strings.

### 1.3. One API Call Is Not Necessarily a Single Network Command

The driver may **split a large array into multiple physical batches** according to message size limits, BSON size, and server operation count limits. MongoDB still enforces the **16 MiB limit per BSON document**. Do not send a document exceeding 16 MiB expecting `insertMany()` or bulk batching to split that document automatically.

At the same time, `insertMany()` can generate multiple index entries, data allocations, and journal/replication writes depending on configuration. "One call" is only a convenient client-side interface; it does not mean all data is written in a single physical operation.

## 2. `ordered: true` — Write in Order, Stop on Error

In **ordered** mode, MongoDB processes documents in the specified order. If an insert operation causes a write error, documents following the failing operation in the normal ordered stream **are not attempted**.

Example creating a test collection and intentionally inserting a duplicate `_id`:

```javascript
db.demoOrdered.drop();

db.demoOrdered.insertOne({
  _id: "existing",
  name: "Already exists"
});

try {
  db.demoOrdered.insertMany(
    [
      { _id: "A", name: "Insert A" },
      { _id: "existing", name: "Duplicate ID record" },
      { _id: "B", name: "Insert B" },
      { _id: "C", name: "Insert C" }
    ],
    { ordered: true }
  );
} catch (error) {
  print("Insert encountered error: " + error.message);
}

db.demoOrdered.find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
```

Logical outcome:

1. `A` is written successfully.
2. The document with `_id: "existing"` violates the `_id` unique index; MongoDB reports a **duplicate key** error, typically with code `11000`.
3. `B` and `C` **are not attempted** because the ordered operation encountered an error.
4. The original `existing` document remains.

After the error, the collection may contain **A** and **existing**. This is the key point to remember: **ordered does not mean "roll back the entire array if one element fails."** Inserts that succeeded before the error persist when there is no transaction protecting the entire batch.

The `find().sort()` line in the example is only to inspect the result by `_id`; it does not prove physical write order of records on disk.

### 2.1. When to Use Ordered?

Choose ordered if operations have **order dependencies** or you want "stop on error so an operator can fix it" behavior:

- Importing data according to a script with sequential checks.
- Wanting to know the front part of the batch was applied up to the failing operation without automatically attempting the rest.
- Executing bulk steps where a later operation's effect meaningfully depends on an earlier one (especially with `bulkWrite()`).
- Needing an error-handling workflow that maps easily to a stopping point in the input list.

However, if each document is independent and the goal is to ingest as many valid records as possible, ordered can cause the whole batch to halt over a single bad document.

## 3. `ordered: false` — Process Remaining Documents Despite Errors

With **unordered**, MongoDB is allowed to continue with other operations when one operation fails. Documents may be processed in an order different from the input array order; in certain deployments or when data spans multiple shards, the system can exploit that independence to increase throughput.

Example using a separate collection:

```javascript
db.demoUnordered.drop();

db.demoUnordered.insertOne({
  _id: "existing",
  name: "Already exists"
});

try {
  db.demoUnordered.insertMany(
    [
      { _id: "A", name: "Insert A" },
      { _id: "existing", name: "Duplicate ID record" },
      { _id: "B", name: "Insert B" },
      { _id: "C", name: "Insert C" }
    ],
    { ordered: false }
  );
} catch (error) {
  print("One or more operations failed: " + error.message);
}

db.demoUnordered.find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
```

In the scenario above:

- `existing` still causes a unique key collision error.
- Independent documents `A`, `B`, and `C` can be written successfully even though the middle operation failed.
- The bulk command **can still end with an error/exception**, because at least one item failed; `ordered: false` does not mean "ignore errors and always return success."
- Only determine **which records were actually written** from API results, error details, and/or re-checking data state; do not infer a physical write sequence.

You can run a confirmation query:

```javascript
db.demoUnordered.find({
  _id: { $in: ["A", "existing", "B", "C"] }
}).sort({ _id: 1 });
```

In this example with no other errors, you will see `A`, `B`, `C` alongside the pre-existing `existing` document. However, if validation, network, or write concern errors also occur, each case must be examined instead of assuming all valid records were definitely written.

### 3.1. "Unordered" Does Not Mean "Random" or "Always Parallel"

`ordered: false` **allows** MongoDB/the driver to optimize execution order and strategy; it does not promise always running multi-threaded, does not promise a fixed speedup factor, and does not mean documents are picked at random.

A small workload on a single node with few indexes and no errors may perform similarly to ordered. When distributed across a sharded cluster or a batch containing many independent records, unordered can be more beneficial. Measure on your actual topology, batch size, write concern, and workload.

### 3.2. Do Not Use Unordered When Operations Depend on Each Other

Suppose you want to insert document `A` and then update that same `A` in sequence within a single `bulkWrite()` list. If using unordered, relying on "insert happens before update" is unsafe. Use ordered, redesign so operations are independent, or use an explicit upsert instead.

## 4. Comparing Ordered and Unordered

| Criterion | `ordered: true` | `ordered: false` |
|---|---|---|
| Default value | **Yes** for `insertMany()` and `bulkWrite()` | Must be specified |
| Execution order | Follows operation list order | Must not rely on order |
| On write error | Stops remaining operations per ordered semantics | Continues independent processable operations |
| Inserts that already succeeded | Remain written if outside a transaction | Remain written if outside a transaction |
| Throws exception on partial error? | Yes, possible | Still possible |
| Auto-rolls back whole batch? | No | No |
| Can increase throughput across shards? | May be limited by sequential waiting | Can leverage additional independence depending on workload |
| Best suited for | Order matters or want to stop on error | Many independent records, want to write maximum valid portion |
| Must handle | Batch ending early with untried items remaining | Multiple errors, partial write results, no order assumptions |

Distinguish further: **"ordered" refers to write execution order**, not a promise that a subsequent `find()` returns documents in insert order. A MongoDB query requiring deterministic order must declare `sort()`.

## 5. Common Errors in Batches

A batch can fail for many reasons. These errors have different implications when designing retries.

### 5.1. Unique Index or `_id` Collision

MongoDB has a default unique index on `_id` for regular collections. In addition, business unique indexes can be created:

```javascript
db.customers.createIndex(
  { emailNormalized: 1 },
  { unique: true }
);
```

If two documents share the same `emailNormalized`, one or both depending on initial state will not be inserted. With `ordered: true`, the batch stops at the first error. With `ordered: false`, other independent documents can still be processed.

**Code 11000** typically denotes a duplicate key. Do not treat every 11000 as "already succeeded": if the new payload differs from the existing record, it may be a real data conflict. A retry should only be considered idempotent when both identifier and business content are verified against the application's contract.

### 5.2. Collection Validation Error

If a collection has a validator, a schema-invalid document can be rejected. For example, a collection requiring `price` to be a BSON decimal:

```javascript
db.createCollection("validatedProducts", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "price"],
      properties: {
        sku: { bsonType: "string" },
        price: { bsonType: "decimal" }
      }
    }
  }
});

try {
  db.validatedProducts.insertMany(
    [
      { _id: "P1", sku: "P1", price: NumberDecimal("100.00") },
      { _id: "P2", sku: "P2", price: "100.00" },
      { _id: "P3", sku: "P3", price: NumberDecimal("150.00") }
    ],
    { ordered: false }
  );
} catch (error) {
  print(error.message);
}
```

Document `P2` has the wrong type instead of decimal, so it can trigger a document validation failure; `P1` and `P3` can be written. In demo environments, use a dedicated test collection name; avoid running `drop()` on production collections.

Permissions and options like `bypassDocumentValidation` carry their own conditions and should not be used to mask schema-invalid input data.

### 5.3. Document Exceeding BSON Size Limit

A document larger than the BSON limit cannot be rescued by switching to `ordered: false`. It must be split into multiple documents with an appropriate data model, or use GridFS/object storage for large binary data. When an element in an array is invalid, exact behavior also depends on where the error is detected: the driver may reject it before sending the command, or the server may return a write error. Therefore, **you cannot guarantee unordered always writes all remaining elements** across every client-to-server error type.

### 5.4. Network, Timeout, and Write Concern Errors

There are cases where the client receives no success response due to network disruption, yet the server **received or wrote** the data. Do not infer "an exception means nothing was inserted." Scenarios to distinguish:

- **Write error:** an individual operation was rejected, such as duplicate key or document validation.
- **Write concern error:** requested replication/journaling acknowledgement level was not reached under those conditions; some changes may already have been applied, and durability/replication status needs assessment.
- **Network/timeout:** the application is uncertain how many operations the server executed or how far the response traveled.

For errors where state is ambiguous, rely on **stable identifiers, idempotency, and reconciliation queries**, rather than blind retries that risk duplicate or missing records.

## 6. `bulkWrite()` — Combining Multiple Operation Types

`insertMany()` only accepts documents to insert. When you need to insert, update, replace, and delete in one list, use the collection's `bulkWrite()`:

```javascript
db.inventory.bulkWrite(
  [
    {
      insertOne: {
        document: {
          _id: "SKU-001",
          name: "New Product",
          stock: 20
        }
      }
    },
    {
      updateOne: {
        filter: { _id: "SKU-002" },
        update: { $inc: { stock: 5 } }
      }
    },
    {
      updateOne: {
        filter: { _id: "SKU-003" },
        update: {
          $setOnInsert: {
            name: "Additional Product",
            stock: 0
          }
        },
        upsert: true
      }
    },
    {
      deleteOne: {
        filter: { _id: "SKU-OLD" }
      }
    }
  ],
  { ordered: true }
);
```

This list contains four operations with distinct semantics. Elements passed to `bulkWrite()` can be:

- `insertOne: { document }`;
- `updateOne: { filter, update, upsert? }`;
- `updateMany: { filter, update, upsert? }`;
- `replaceOne: { filter, replacement, upsert? }`;
- `deleteOne: { filter }`;
- `deleteMany: { filter }`.

Other options exist depending on API/driver and version. When using `ordered: true`, a later operation can rely on an earlier change within the same sequential list. With `ordered: false`, **never build business logic that depends on operation order**.

### 6.1. Example of Order-Dependent Operations

Suppose the list is:

```javascript
db.steps.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "task-1", state: "NEW" }
      }
    },
    {
      updateOne: {
        filter: { _id: "task-1" },
        update: { $set: { state: "READY" } }
      }
    }
  ],
  { ordered: true }
);
```

Here `updateOne` needs the newly created `task-1` record. Ordered supports sequential logic. If `insertOne` fails due to duplicate `_id`, the trailing update operation is stopped; the application must decide how to handle the old record.

If unordered were used, the database could process the update before the insert, causing the update to match 0 documents or produce unpredictable results. Even though `ordered: true` preserves order, **it does not guarantee atomicity across both operations** without a transaction.

### 6.2. Note Differences with Multi-Namespace Bulk Writes

Some MongoDB/driver versions support client-level bulk APIs across multiple collections/databases. Syntax, support conditions, and result structures can differ from `db.collection.bulkWrite()` used in this lesson. Before implementing, confirm the exact API and driver version; do not apply collection-level syntax to client-level APIs without checking.

## 7. Partial Write Results: How to Read and Reconcile?

When a batch is fully processed, the application can receive counts of inserted, updated/deleted documents, `upsertedIds`, and other statistics depending on the API. On error, the exception object may provide:

- Error type and error code;
- Position of the failing operation (index in the list);
- Result info for the executed portion;
- List of write errors;
- Write concern error details if present.

Exact field names differ across `mongosh`, drivers, and versions. Therefore, the following example illustrates **conceptually safe logging**, without assuming every environment shares the same error object structure:

```javascript
try {
  const result = db.ingest.insertMany(documents, {
    ordered: false
  });

  printjson(result);
} catch (error) {
  print("Bulk operation reported an error");
  print(error.message);

  // If the driver provides writeErrors/result,
  // log actual fields according to the driver's contract.
  if (error.writeErrors) {
    printjson(error.writeErrors);
  }
}
```

In production applications, log the **batch ID**, input count, list of planned IDs, success/error counts, and causes by error code. Avoid logging only `error.message` and discarding partial results, as later it becomes hard to tell which documents need retrying.

### 7.1. What Does "Error at Index N" Mean?

In ordered mode, an error at index N usually indicates preceding operations in the sequence were attempted first, and subsequent operations were not attempted because the command stopped. In unordered mode, index N **identifies the failing input element**, without proving that elements before N all succeeded or executed before it.

If the driver splits the list into multiple physical batches or an ambiguous error occurs, the application should rely on reported results and ID-based reconciliation queries rather than guessing network call order.

### 7.2. Scenario: Importing 1,000 Documents with 8 Duplicate ID Errors

Suppose there are 1,000 independent documents, of which 8 violate a unique key:

- Ordered may stop immediately at the first error, leaving many valid documents unattempted.
- Unordered can ingest the other valid documents and report the list of 8 corresponding errors.
- If the requirement is "ingest what is valid, report what is duplicate," unordered is usually advantageous.
- If the requirement is "all 1,000 must succeed together or fail together," **neither ordered nor unordered outside a transaction meets that requirement**.

To have clear completion criteria, establish a duplicate-handling policy: skip if the existing record matches, update per merge rules, or flag a conflict for intervention.

## 8. Atomicity and Transactions: Ordered/Unordered Does Not Decide Everything

Inserting **a single document** is executed atomically by MongoDB at the document level. However, calling `insertMany()` with 100 documents under normal conditions does not mean "100 documents form a single ACID transaction."

Example without a transaction:

```text
Ordered batch:
  D1 -> success
  D2 -> success
  D3 -> duplicate key error
  D4 -> not attempted

After the command:
  D1, D2 remain in the collection.
  D3 was not added.
  D4 was not attempted.
```

When the business truly requires **all-or-nothing**, use a multi-document transaction on a supported topology, along with driver-appropriate retries and commit error handling.

Conceptual example in `mongosh`:

```javascript
const session = db.getMongo().startSession();

try {
  const sessionDb = session.getDatabase(db.getName());
  const orders = sessionDb.getCollection("orders");

  session.startTransaction();

  orders.insertMany(
    [
      { _id: "ORD-101", customerId: "C1", total: 100 },
      { _id: "ORD-102", customerId: "C2", total: 200 }
    ],
    { ordered: true }
  );

  session.commitTransaction();
} catch (error) {
  try {
    session.abortTransaction();
  } catch (abortError) {
    // The transaction may have already ended or commit result may be unknown.
    // Handle according to the actual error type.
  }

  print("Transaction error: " + error.message);
} finally {
  session.endSession();
}
```

This is a basic flow example. In real applications, driver transaction callbacks/helpers can support retry mechanisms for eligible errors; the application must still handle **unknown commit result** cases.

Inside a transaction, an operation error can cause the transaction to abort and prior writes not to commit. **Do not treat `ordered: false` as a way to guarantee partial writes continue inside an errored transaction.** If you need to process individual valid documents, consider pre-validation and running independent batches outside transactions, or scoping transactions to a smaller business boundary.

### 8.1. When Should You Avoid Putting an Entire Batch in a Transaction?

Transactions increase synchronization overhead and resource consumption; long transactions or those containing many changes can create heavy pressure, hit time limits, or incur write conflicts. Importing millions of independent records is usually better suited to **checkpointed batches and idempotent retries** than a giant transaction.

Conversely, writing an order along with its related inventory adjustments may require a transaction because the business invariant outweighs raw batch throughput.

## 9. Idempotency When Ingesting Multiple Documents

In practice, bulk requests may be retried due to timeouts, dropped connections, or consumer reprocessing. If each retry generates a new `_id`, the same business event can turn into multiple duplicate documents.

### 9.1. Using Stable IDs from the Data Source

For example, each event has a unique `eventId` from the source system:

```javascript
const events = [
  {
    _id: "event-1001",
    source: "partner-A",
    payload: { type: "CREATED", orderId: "ORD-5" }
  },
  {
    _id: "event-1002",
    source: "partner-A",
    payload: { type: "PAID", orderId: "ORD-5" }
  }
];

db.partnerEvents.insertMany(events, { ordered: false });
```

If retried with the same IDs, the unique index on `_id` can report a duplicate key error instead of creating new copies. However, **never blindly treat every duplicate key as success**: compare key attributes or payload hashes to confirm the duplicate truly represents the same event.

### 9.2. Using Upsert with `$setOnInsert` When Appropriate

If the goal is "have a record with this ID; create it if absent," you can replace insert with upsert:

```javascript
db.partnerEvents.bulkWrite(
  events.map(event => ({
    updateOne: {
      filter: { _id: event._id },
      update: { $setOnInsert: event },
      upsert: true
    }
  })),
  { ordered: false }
);
```

If a document with `_id` already exists, `$setOnInsert` leaves the old content untouched. This is an option for insert-if-absent ingestion, though if the new payload differs from the existing payload, the application still needs to detect and handle the conflict per business rules. Concurrent upsert waves also need proper unique indexes and retry handling for duplicate-key race conditions.

### 9.3. Batch ID and Progress Checkpoints

An ingestion job can track:

```text
jobId = import-2026-11-14
batchIndex = 0001
sourceRange = lines 000001–001000
documentIds = [event-1001, ..., event-2000]
status = completed / partially_completed / retry_needed
```

This is application-layer metadata, not a mandatory MongoDB structure. It supports controlled restarts, ID-based document reconciliation, and prevents data loss when a job halts mid-run.

## 10. Performance: When Is Unordered Beneficial?

A batch can be fast or slow depending on many factors:

| Factor | Impact |
|---|---|
| Document count and BSON size | Too small a batch causes many round trips; too large increases memory and processing time |
| Index count | Every insert must update indexes, including unique and multikey indexes |
| Write concern | `w: 1`, `majority`, and journal requirements have different acknowledgement/durability characteristics |
| Sharding | Unordered can leverage multiple shards for independent operations, depending on shard key and data distribution |
| Network latency | Many single inserts suffer more noticeably from round-trip overhead |
| Document validation | Schema validation adds overhead; invalid data causes batch errors |
| Concurrent writers | Multiple concurrent jobs contend for CPU/I/O/index/cache |
| Retry/duplicate | Batches with many errors spend effort classifying and reconciling |

**There is no rule that "unordered is always X times faster than ordered."** If data is small, unsharded, or bottlenecked by I/O/indexes, the difference may be negligible. When ordered hits an early error, it executes fewer operations, so comparing raw total time against unordered is unfair: measure **successful documents per second**, CPU, I/O, p95/p99 latency, and error counts.

### 10.1. Choosing Batch Size

To process millions of records, split them into batches sized appropriately for the workload and RAM/network capacity. Do not cram everything into one massive `insertMany()` because the driver may have to split commands, track result/error lists, and hold large volumes of data in memory.

A typical import process:

1. Read/parse input data via streaming or chunks.
2. Normalize schema and assign stable IDs.
3. Send a batch of independent documents.
4. Record results, errors, and checkpoints.
5. Retry items with unknown status under an idempotent policy.
6. Proceed to the next batch.

Batch size is determined not only by **document count**, but also by BSON bytes per document, indexes, and concurrency level.

### 10.2. Batch Ingestion Example in `mongosh`

This example illustrates chunking simulated data into batches; collection names are chosen for testing:

```javascript
const batchSize = 500;
let batch = [];

for (let i = 0; i < 2000; i++) {
  batch.push({
    _id: "sample-" + i,
    category: "demo",
    value: i,
    createdAt: new Date()
  });

  if (batch.length >= batchSize) {
    try {
      db.bulkDemo.insertMany(batch, { ordered: false });
    } catch (error) {
      print("Batch write issue: " + error.message);
      // In a real app: log the batch IDs and reconcile.
    }
    batch = [];
  }
}

if (batch.length > 0) {
  db.bulkDemo.insertMany(batch, { ordered: false });
}
```

In the example above, the catch block is illustrative and **not yet a production importer**: a network error can leave part of a batch in an unknown state; catching and moving on without saving checkpoints/reconciling can cause missing data. Expand the error branch instead of only printing a message when moving to production.

## 11. Effects of Ordering on Data and Queries

### 11.1. Insert Order Is Not `find()` Order

```javascript
db.logs.insertMany(
  [
    { _id: "L1", sequence: 1 },
    { _id: "L2", sequence: 2 },
    { _id: "L3", sequence: 3 }
  ],
  { ordered: true }
);

// Do not assume results always follow sequence:
db.logs.find();

// If business order is desired:
db.logs.find().sort({ sequence: 1, _id: 1 });
```

MongoDB does not promise default `find()` return order matches insert order across every run. Indexes, query plans, updates/migrations, and sharding can all affect natural scan order. Display order must be specified with `sort()`.

### 11.2. `ordered: false` and Inter-Document Dependencies

If business logic requires "create parent before creating child," sending them in an unordered batch does not enforce foreign keys or transactions. MongoDB does not have RDBMS-style foreign keys for regular collections; if referential integrity must be preserved, the application must design appropriate steps and validation.

For `insertMany()` arrays that only insert documents, operation independence favors unordered mode. For `bulkWrite()` mixing operation types, inter-item dependencies pose a clearer risk.

### 11.3. "Ordered Success" Still Does Not Guarantee Cross-Query Visibility

Outside a transaction, another client can observe the collection while a batch is still running; MongoDB does not make an entire batch appear atomically at once. For data undergoing ingestion, use a release status flag such as `importStatus: "READY"` after completion and reconciliation, or use transactions as needed, if readers must only see complete datasets.

## 12. Mode Selection Strategy by Scenario

| Scenario | Mode to Consider | Reason |
|---|---|---|
| Importing catalog from CSV, each product independent | `ordered: false` | One bad row does not halt other valid rows |
| Seeding demo data needing to stop at first mistake | `ordered: true` | Easy to catch errors without trying subsequent operations |
| Bulk containing insert followed by update on the same ID | `ordered: true` | Preserves sequential dependency |
| Ingesting across multiple shards, independent operations | `ordered: false` | Can leverage write distribution under suitable conditions |
| Requiring all documents to commit or roll back together | Appropriate transaction | Ordered/unordered alone does not provide whole-batch atomicity |
| Consumer receiving events that may retry | Unordered or idempotent upsert | Prioritizes stable IDs, reconciliation, and duplicate handling |
| Writing inventory and order with coupled invariants | Transaction or appropriate atomic design | Do not trade correctness for throughput |
| Migrating multi-million record datasets | Small batches, checkpoints, retries | Must manage memory, partial errors, and resumability |

## 13. Error-Handling Workflow for Real-World Imports

For each batch, do not merely record whole-batch "success/failed." A reliable workflow can include:

**Step 1 — Normalize input before writing.** Validate data types, required fields, size limits, unique values, and assign stable IDs. Application-level validation makes errors readable, though it does not replace database unique indexes/validators.

**Step 2 — Choose mode based on independence.** If documents are independent, `ordered: false` lets processing continue past per-document errors. If operations have dependencies, use ordered mode or switch to clearly bounded steps/transactions.

**Step 3 — Log structured results.** Record input count, attempted IDs, success count, errors by code and index (if provided by the driver), as well as write concern/network errors.

**Step 4 — Classify unknown states.** For network/timeout errors, look up IDs in the database or use driver-supported retry mechanisms; avoid assuming an error means the server did nothing.

**Step 5 — Controlled retries.** Only retry operations consistent with the idempotency policy; for duplicates, compare existing records to distinguish same-data retries from business conflicts.

**Step 6 — Reconcile and mark complete.** Canonical records in the database must match expected inputs after excluding legitimately rejected records. Transition the import status to complete only when business criteria are satisfied.

### 13.1. Example Classifying Three Outcome Types

```text
Input: 6 documents
  A: valid
  B: valid
  C: unique index collision
  D: valid
  E: schema error
  F: valid

If ordered=true:
  May write A, B; stop at C; D/E/F not attempted.

If ordered=false:
  May write A, B, D, F; C and E report write errors.
  Processing order has no contract matching the original list.

If network/timeout error occurs:
  Do not deduce outcome from input list alone; readback/reconciliation required.
```

The example illustrates server-side write error handling principles. Some errors detected by the driver before sending can cause the entire call to fail before any operations are attempted.

## 14. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| "`insertMany()` is a transaction." | Inserting multiple documents outside a transaction can partially succeed. |
| "`ordered: true` rolls back earlier documents on error." | Successful operations before the error remain persisted without a transaction rollback. |
| "`ordered: false` ignores errors and always returns success." | The API can still throw an exception and supply a partial error list. |
| "Unordered always runs in parallel and is always faster." | It only permits optimization; performance depends on topology, load, indexes, and write concern. |
| "Ordered guarantees `find()` returns documents in insert order." | Use `sort()` whenever deterministic query order is needed. |
| "Retrying the whole `insertMany()` is safe after a client timeout." | Some records may already have been written; stable IDs and reconciliation are required. |
| "Duplicate `_id` on retry always means success." | Must verify the existing record matches payload/business meaning. |
| "A document over 16 MiB is automatically split by MongoDB." | Must adjust the storage model or use a suitable file-storage mechanism. |
| "Ordered `bulkWrite()` makes all operations atomic." | Ordered only governs order/stopping on error; full atomicity requires another mechanism. |
| "Unordered fits every list of operations." | Should not be used when operations have sequential dependencies. |

## 15. Practice Exercises

### Exercise 1 — Observing Ordered and Unordered

Create two test collections `testOrdered` and `testUnordered`, each pre-populated with `{ _id: "existing" }`. With the same array `[A, existing, B, C]`, call `insertMany()` once with `ordered: true` and once with `false`. Predict the remaining IDs beforehand and verify with `find().sort({ _id: 1 })`.

### Exercise 2 — Duplicate Emails in Import Data

The `customers` collection has a unique index on `emailNormalized`. A CSV file has 50,000 rows, 200 of which have emails that already exist. Design the batch import, choose ordered/unordered, how to store the error list, and the conditions under which a duplicate may be treated as "previously imported" rather than flagged as a conflict.

### Exercise 3 — Dependent Bulk Operations

In `bulkWrite()`, the first operation inserts `{ _id: "task-1", status: "NEW" }`, and the second updates status to `READY`. Explain the difference between `ordered: true` and `false`; if both-or-neither is required, what mechanism would you use?

### Exercise 4 — Retry After Timeout

A client sends 1,000 events, encounters a network timeout, and does not know how far the server got. Each event has a unique ID from upstream. Design the step to confirm existing IDs, retry necessary IDs, handle duplicate IDs with differing payloads, and checkpoint the job.

### Exercise 5 — Evaluating Performance Properly

Run identical data ingestion with the same indexes, same write concern, and same volume—once ordered and once unordered—in a monitored test environment. Measure successful records/s, errors, p95 latency, and disk/CPU. Why can't the total duration of an ordered run that halted early on error be used to conclude it is faster than an unordered run that completed many more inserts?

## Conclusion

**`ordered: true`** preserves operation order and stops on write errors; **`ordered: false`** allows independent operations to continue and can help improve throughput in suitable environments. Both can leave **partial write results** outside a transaction, and neither dictates `find()` read order.

When writing multiple documents, choose the mode based on **order dependencies and tolerance for partial errors**, while designing stable IDs, unique indexes, validation, retries, and reconciliation. When all-or-nothing is required, use transactions at the appropriate business boundary. An API-level batch success only matters when the application knows precisely **which documents were written, which failed, and under what conditions to retry**.
