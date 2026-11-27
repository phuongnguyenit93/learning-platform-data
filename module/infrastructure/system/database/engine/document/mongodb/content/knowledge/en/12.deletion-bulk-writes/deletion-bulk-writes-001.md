# deleteOne, deleteMany, and Delete Operation Limits in MongoDB

## 1. Deleting a Document Is More Than Writing a Statement

In MongoDB, the two most common deletion operations are **deleteOne()** and **deleteMany()**. Both take a **filter** to select documents, but they differ in how many documents can be deleted, how they are used in applications, and the risk when a filter is too broad.

Example:

~~~javascript
db.orders.deleteOne({ _id: "o001" });

db.orders.deleteMany({
  tenantId: "t001",
  status: "cancelled"
});
~~~

The first statement targets at most one order. The second can delete thousands or millions of orders if they match the filter. MongoDB does not automatically infer "delete a few test records first," "keep orders needed for reconciliation," or "delete only within one tenant" unless the application expresses those conditions.

In the **Deletion and Bulk Writes** chapter, this lesson focuses on:

1. The syntax and return values of **deleteOne()** and **deleteMany()**.
2. Filter semantics, the risk of selecting the wrong documents, and non-determinism when multiple documents match.
3. The real limits of delete operations: count, sorting, atomicity, concurrency, timeouts, and scope.
4. How to cap the number of documents per batch when cleaning up large datasets.
5. Combining with **bulkWrite**, transactions, write concern, TTL, and soft delete when business requirements are complex.
6. A safety workflow before executing destructive data operations.

> The examples run using **mongosh** on a dedicated **mongo_delete_lab** database. Do not run illustrative delete commands on production collections. The sample data carries its own label so that all hands-on examples stay scoped.

## 2. deleteOne(): Deleting at Most One Document

### 2.1. Syntax

~~~javascript
db.collection.deleteOne(filter, options);
~~~

- **filter** is the query expression used to select a document.
- **options** is an options object that may include settings such as collation, hint, write concern, or comment depending on the version and driver.
- The result is returned by mongosh/the driver as a write result; when the write is acknowledged, the key property is **deletedCount**.

Example:

~~~javascript
const result = db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne({
    _id: "o001",
    dataset: "delete-lab-v1",
    tenantId: "t001"
  });

printjson(result);
print("Deleted documents: " + result.deletedCount);
~~~

If `o001` exists and matches the conditions, **deletedCount = 1**. If `o001` does not exist, has already been deleted, or has changed state so that the filter no longer matches, **deletedCount = 0**.

**deleteOne does not throw an error simply because no document was found.** The operation can be acknowledged as successful with `deletedCount` equal to 0. The application must determine whether this means "already deleted," "not found," or "status no longer allows deletion."

### 2.2. What If Multiple Documents Match?

~~~javascript
db.orders.deleteOne({ status: "cancelled" });
~~~

The command above deletes **only one document** among the matching documents. However, **you must not assume which document will be selected** if there is no sufficiently specific key constraint. `deleteOne` does not provide a `sort` option to guarantee deleting the oldest, newest, or lowest `_id` order.

In business logic, prefer filters with a stable identifier—usually **_id**—and add protective tenant/ownership/status conditions. Example:

~~~javascript
db.orders.deleteOne({
  _id: "o001",
  tenantId: "t001",
  status: "draft"
});
~~~

This command means: **delete `o001` only if the order still belongs to tenant `t001` and is still in `draft` status at the moment MongoDB applies the operation**. The status filter prevents deleting an order that transitioned to `paid` between the time the user viewed the screen and the time the server processed the request.

### 2.3. What Should You Use to Delete One Document in Order?

When the requirement is "delete **one** **oldest** `cancelled` record," consider **findOneAndDelete()** with `sort`:

~~~javascript
const removed = db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .findOneAndDelete(
    {
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "cancelled",
      legalHold: false
    },
    { sort: { createdAt: 1, _id: 1 } }
  );

printjson(removed);
~~~

This command selects one document according to the sort order and returns the **deleted document**, or **null** if nothing matches. Atomicity applies to the single-document operation. Fetching a list with `find` and calling `deleteOne` afterward is **not equivalent** to a single atomic find-and-delete operation: there is a window during which other operations can modify the data in between.

When working with a sharded collection, you must check the routing requirements and limitations of your MongoDB server/driver version; do not port a sorted delete pattern directly to a sharded environment without evaluating it.

## 3. deleteMany(): Deleting All Matching Documents

### 3.1. Syntax

~~~javascript
db.collection.deleteMany(filter, options);
~~~

Example:

~~~javascript
const result = db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteMany({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false
  });

printjson(result);
print("Deleted: " + result.deletedCount);
~~~

MongoDB attempts to delete the documents matching the filter. When the result is acknowledged as successful, **deletedCount** reports the number of documents actually deleted. If no documents match, `deletedCount` is 0.

**deleteMany has no `limit` or `sort` parameter** analogous to `find().limit().sort()`. A broad filter can wipe out an entire collection.

### 3.2. An Empty Filter Is a Dangerous Delete

~~~javascript
// WARNING: deletes every document in the collection!
// db.orders.deleteMany({});
~~~

This is a valid operation, but its meaning is **delete every document** the collection holds—not "delete empty documents." MongoDB keeps the collection and its indexes after the deletion, unlike **drop()**, which removes the collection and its indexes.

Comparison:

| Operation | Scope | Keeps collection/indexes? | Typical purpose |
| --- | --- | --- | --- |
| **deleteOne(filter)** | At most one matching document | Yes | Delete a specific entity |
| **deleteMany(filter)** | Every matching document | Yes | Delete multiple entities matching criteria |
| **deleteMany({})** | All documents in the collection | Yes | Intentionally clear all contents |
| **drop()** | Drops the collection | **No** | Remove the entire collection, including indexes |
| **dropDatabase()** | Drops the entire database | **No** | Remove all data in the database |

Do not use `deleteMany({})` as a "test command" to see whether data gets deleted. In these exercises, every delete statement includes **dataset** and **tenantId** or **_id** to reduce the risk of exceeding scope.

### 3.3. The Right Way to Think About Volume

**deleteMany** has no fixed API-level cap such as "at most N documents." The volume can be huge, but throughput and completion depend on:

- The number of matching documents and whether they can be located via an index.
- Document size and the indexes that must be updated.
- Concurrent write load, disk resources, replication, and write concern.
- Execution time, interruptions, network errors, or server errors.
- Whether the collection is sharded and whether chunks are migrating.

If you need to delete millions of documents, you need a **bounded batch** strategy, monitoring, and a recovery mechanism rather than assuming a single giant `deleteMany` is always the cheapest approach.

## 4. Sample Dataset for Practice

We use the **lab_orders** collection containing ten orders across two tenants, multiple statuses, and one order flagged with **legalHold = true**. The dataset tag is **delete-lab-v1**.

### 4.1. Creating the Sample Data

Run the following block as a whole in `mongosh`:

~~~javascript
(() => {
  const lab = db.getSiblingDB("mongo_delete_lab");
  const orders = lab.getCollection("lab_orders");
  const tag = "delete-lab-v1";

  // Clean up only the lab documents; do not drop the collection or database.
  orders.deleteMany({ dataset: tag });

  orders.insertMany([
    {
      _id: "o001", dataset: tag, tenantId: "t001",
      status: "draft", legalHold: false,
      createdAt: ISODate("2026-01-01T08:00:00.000Z")
    },
    {
      _id: "o002", dataset: tag, tenantId: "t001",
      status: "draft", legalHold: false,
      createdAt: ISODate("2026-01-02T08:00:00.000Z")
    },
    {
      _id: "o003", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2026-01-03T08:00:00.000Z")
    },
    {
      _id: "o004", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2026-01-04T08:00:00.000Z")
    },
    {
      _id: "o005", dataset: tag, tenantId: "t001",
      status: "completed", legalHold: false,
      createdAt: ISODate("2026-01-05T08:00:00.000Z")
    },
    {
      _id: "o006", dataset: tag, tenantId: "t001",
      status: "pending", legalHold: false,
      createdAt: ISODate("2026-01-06T08:00:00.000Z")
    },
    {
      _id: "o007", dataset: tag, tenantId: "t002",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2026-01-07T08:00:00.000Z")
    },
    {
      _id: "o008", dataset: tag, tenantId: "t002",
      status: "pending", legalHold: false,
      createdAt: ISODate("2026-01-08T08:00:00.000Z")
    },
    {
      _id: "o009", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: true,
      createdAt: ISODate("2026-01-09T08:00:00.000Z")
    },
    {
      _id: "o010", dataset: tag, tenantId: "t001",
      status: "cancelled", legalHold: false,
      createdAt: ISODate("2025-12-20T08:00:00.000Z")
    }
  ]);

  orders.createIndex(
    {
      dataset: 1,
      tenantId: 1,
      status: 1,
      legalHold: 1,
      createdAt: 1,
      _id: 1
    },
    { name: "ix_lab_delete_candidates" }
  );

  print("Lab document count: " +
    orders.countDocuments({ dataset: tag }));
})();
~~~

**Expected result:** **10 documents**. Each document has a fixed `_id`. If you have already run some delete statements and want to compare against the initial state, re-run this entire seed block.

### 4.2. Previewing the Target Document Set

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const filter = {
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false
  };

  print("Candidate count: " + orders.countDocuments(filter));
  printjson(
    orders.find(
      filter,
      { _id: 1, tenantId: 1, status: 1, legalHold: 1, createdAt: 1 }
    )
    .sort({ createdAt: 1, _id: 1 })
    .toArray()
  );
})();
~~~

From the original seeded dataset, the candidates are **o010, o003, o004** in ascending `createdAt` order, totaling **3**. Document **o009** is excluded because `legalHold = true`; **o007** belongs to tenant `t002`, so it does not match either.

When preparing for a real deletion, previewing with `find`/`countDocuments` helps catch bad filters. However, this is **not a snapshot guaranteeing the result set will remain unchanged until `deleteMany` runs**: other writers can modify data between the check and the delete.

## 5. Hands-On with deleteOne, findOneAndDelete, and deleteMany

The following steps form **a sequential chain** after seeding; do not reset between steps unless explicitly stated.

### 5.1. Step A — Delete a Draft by _id

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const result = orders.deleteOne({
    _id: "o001",
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "draft"
  });

  printjson(result);
  print("deletedCount=" + result.deletedCount);
})();
~~~

**Expected result on the first run:** `deletedCount =` **1**. Running this command again immediately yields `deletedCount =` **0**, because `o001` is gone.

The **status: "draft"** condition acts as a guard: if the order has transitioned to `paid`, the statement will not delete it merely because the client still holds the old `_id`. This is a form of conditional single-document operation.

### 5.2. Step B — Delete Exactly One Oldest Cancelled Order

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const removed = orders.findOneAndDelete(
    {
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "cancelled",
      legalHold: false
    },
    { sort: { createdAt: 1, _id: 1 } }
  );

  printjson(removed);
})();
~~~

**Expected result:** the returned document has **_id = "o010"**, because it has the earliest `createdAt` among `t001`'s `cancelled` orders without a legal hold. If no document matches, the return value is `null`.

Unlike `deleteOne`, `findOneAndDelete` can sort, delete one document, and return the deleted document's contents. When you need neither sorting nor the old document, `deleteOne` by `_id` is usually simpler.

### 5.3. Step C — Delete Multiple Remaining Cancelled Orders

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const result = orders.deleteMany({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false
  });

  printjson(result);
  print("deletedCount=" + result.deletedCount);
})();
~~~

**Expected result when run after Steps A and B:** `deletedCount =` **2** (`o003`, `o004`). Order `o009` is protected by `legalHold = true`.

If you run Step C **directly after seeding**, `deletedCount` will be **3** because `o010` was not deleted in Step B. The number of documents deleted depends on the data state at the exact time the command executes, not on whichever example narrative you read.

### 5.4. Step D — Verify the Remaining Scope

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const filter = { dataset: "delete-lab-v1" };
  print("Remaining: " + orders.countDocuments(filter));
  printjson(
    orders.find(
      filter,
      { _id: 1, tenantId: 1, status: 1, legalHold: 1 }
    )
    .sort({ _id: 1 })
    .toArray()
  );
})();
~~~

**Expected result:** **6 documents** remain: **o002, o005, o006, o007, o008, o009**. This is a technical check of the operation scope in the lab, not proof of atomicity across the entire A–C sequence.

## 6. What Does "Limiting Delete Operations" Actually Mean?

The word **limit** can refer to several distinct requirements:

| Goal | Approach |
| --- | --- |
| Delete only one document | **deleteOne** with a filter on `_id` and business conditions |
| Delete one document in order | **findOneAndDelete** with `sort` |
| Delete all documents meeting criteria | **deleteMany** |
| Delete at most N documents in a batch | Pre-select N `_id` values, then delete by **_id: { $in: ids }** with protective conditions |
| Limit by tenant/status/time | Specific filter, evaluated beforehand with `find`/`countDocuments` |
| Limit load on the database | Batching, rate throttling, indexes, latency and replication monitoring |
| Retain records for recovery or reconciliation | Soft delete, archive, backup, or retention policy |

**There is no `deleteMany(filter).limit(N)` syntax** like a `find` cursor. The proper approximation is to **fetch a bounded list of candidates**, then delete the selected `_id`s. You must address write concurrency so you do not delete a record whose status just changed.

### 6.1. Deleting at Most N Candidates in Two Steps

Before running this example, **re-run the seed in Section 4** to restore the initial dataset.

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");
  const tag = "delete-lab-v1";
  const cutoff = ISODate("2026-01-05T00:00:00.000Z");
  const batchSize = 2;

  const eligibility = {
    dataset: tag,
    tenantId: "t001",
    status: "cancelled",
    legalHold: false,
    createdAt: { $lt: cutoff }
  };

  // Step 1: select up to 2 documents in deterministic order.
  const ids = orders.find(eligibility, { _id: 1 })
    .sort({ createdAt: 1, _id: 1 })
    .limit(batchSize)
    .toArray()
    .map(doc => doc._id);

  printjson({ ids: ids });

  // Step 2: re-check business conditions during deletion.
  const result = ids.length === 0
    ? { deletedCount: 0 }
    : orders.deleteMany({
        ...eligibility,
        _id: { $in: ids }
      });

  print("deletedCount=" + result.deletedCount);
})();
~~~

From the seeded data, the two oldest candidates are **o010** and **o003**, so `deletedCount` is expected to be **2** if no other writer intervenes. The **_id: { $in: ids }** condition caps the deletion scope to the number of IDs in the batch, while repeating `status`, `legalHold`, `tenantId`, and `cutoff` prevents deleting a candidate that transitioned to an ineligible state between the two steps.

This is **not an atomic transaction between `find` and `deleteMany`**. The following can occur:

- A document is deleted by another operation first → `deletedCount` is smaller than `ids.length`.
- A document transitions from `cancelled` to `paid` → `deleteMany` does not delete it because the filter re-checks `status`.
- A new document is inserted that is not in `ids` → it is not deleted in the current batch.
- A document is modified while still satisfying all conditions → it can still be deleted; if the business logic requires "no fields changed at all," you need a version field or an appropriate locking/transaction mechanism.

### 6.2. Looping Multiple Batches with an Explicit Budget

Instead of one statement deleting millions of records, a cleanup job can run bounded batches. The example below demonstrates **at most three batches of two IDs each**, rather than an unbounded loop:

~~~javascript
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const cutoff = ISODate("2026-01-05T00:00:00.000Z");
  const batchSize = 2;
  const maxBatches = 3;

  const eligibility = {
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false,
    createdAt: { $lt: cutoff }
  };

  let totalDeleted = 0;

  for (let batch = 1; batch <= maxBatches; batch++) {
    const ids = orders.find(eligibility, { _id: 1 })
      .sort({ createdAt: 1, _id: 1 })
      .limit(batchSize)
      .toArray()
      .map(doc => doc._id);

    if (ids.length === 0) {
      break;
    }

    const result = orders.deleteMany({
      ...eligibility,
      _id: { $in: ids }
    });

    printjson({
      batch: batch,
      selected: ids.length,
      deleted: result.deletedCount
    });

    totalDeleted += result.deletedCount;

    // Avoid continuous looping on conflicts or lack of progress.
    if (result.deletedCount === 0) {
      break;
    }
  }

  print("Total deleted in run: " + totalDeleted);
})();
~~~

In production, add **checkpoints**, **metrics**, **rate limiting**, **inter-batch pauses if needed**, **error alerting**, and a way to resume after interruptions. You do not have to load millions of IDs into application memory; each batch should hold only a modest set of IDs.

### 6.3. Why Not Use skip for Paginated Cleanup?

If you select batches using **skip(1000).limit(100)** and delete them, removing earlier documents shifts page positions. Subsequent batches can **miss** documents. That is a common bug when paginating over a result set that the job itself is mutating.

For a deletion job, you can:

- Repeatedly fetch the **first N documents still matching the filter** and delete them, as in the example above.
- Or use **keyset/cursor pagination on `(createdAt, _id)`** with checkpoints and consistent conditions if you must scan sequentially across very large datasets.

Selecting by `_id` with a deterministic sort only makes candidate selection predictable; it does not turn multiple statements into a single transaction.

## 7. deleteOne, deleteMany, and bulkWrite

### 7.1. Grouping Delete Operations in a Single Call

When you have multiple operations with different filters, **bulkWrite()** lets you submit a list of operations, including **deleteOne** and **deleteMany**:

~~~javascript
// Re-run the seed in section 4 before trying.
(() => {
  const orders = db.getSiblingDB("mongo_delete_lab")
    .getCollection("lab_orders");

  const result = orders.bulkWrite(
    [
      {
        deleteOne: {
          filter: {
            _id: "o001",
            dataset: "delete-lab-v1",
            tenantId: "t001",
            status: "draft"
          }
        }
      },
      {
        deleteMany: {
          filter: {
            dataset: "delete-lab-v1",
            tenantId: "t001",
            status: "cancelled",
            legalHold: false
          }
        }
      }
    ],
    { ordered: true }
  );

  printjson(result);
  print("Deleted: " + result.deletedCount);
})();
~~~

From the seeded data, the first run is expected to delete **4 documents**: one draft order `o001` and three cancelled orders `o003`, `o004`, `o010`. Document `o009` remains untouched because `legalHold = true`.

**ordered: true** executes operations in list order and generally stops after a write error; **ordered: false** gives MongoDB more flexibility in execution order and continues independent operations in many error cases. Never treat `ordered: false` as a guarantee that all operations succeed, or `ordered: true` as a transaction.

### 7.2. BulkWrite Does Not Automatically Guarantee Batch-Wide Atomicity

A `bulkWrite` containing multiple `deleteOne`/`deleteMany` operations **does not automatically turn the entire group into an all-or-nothing unit**. Earlier operations may already have deleted data before a later operation fails. The application must:

- Inspect **BulkWriteResult** and any **write errors**.
- Record clearly which operations succeeded and which must be re-evaluated.
- Avoid blindly retrying an entire broad multi-condition batch without checking side effects.
- If all-or-nothing semantics across multiple documents are required, consider transactions on a MongoDB deployment that supports them.

`bulkWrite` reduces server round-trips and batches operation submission; **it does not automatically solve business correctness or cap the total number of deleted documents**.

### 7.3. When to Use Each Option?

| Need | Appropriate tool |
| --- | --- |
| Delete one user by `_id` | `deleteOne` |
| Delete the single oldest record and get its contents | `findOneAndDelete` with `sort` |
| Delete all expired temporary sessions within a specific scope | `deleteMany` with a targeted filter or a policy-driven TTL |
| Clean up millions of logs in small chunks | ID-selection batching + `deleteMany`; checkpoints and throttling |
| Send multiple delete operations with different filters | `bulkWrite` |
| Delete multiple documents with mandatory all-or-nothing semantics | Transaction with appropriate boundaries and operational cost |

## 8. Atomicity, Write Concurrency, and Transactions

### 8.1. deleteOne Is Atomic at the Document Level

MongoDB guarantees that write operations on **a single document** are atomic, even when updating multiple fields. For `deleteOne`, a document is either deleted or not deleted; the filter is evaluated when the operation executes.

This helps protect status-conditional deletions:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne({
    _id: "o002",
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "draft"
  });
~~~

If another writer has already moved `o002` to `pending` before the delete is applied, the filter no longer matches and `deletedCount` can be 0. However, if multiple services must delete a record, write an audit entry, release resources, and publish an external notification, **the atomicity of a single `deleteOne` does not cover all of those side effects**.

### 8.2. deleteMany Is Not Atomic Across the Entire Result Set

Although **each individual document deletion** inside `deleteMany` is atomic, **the multi-document delete command as a whole is not an all-or-nothing transaction**. Some documents may already be deleted while others are not if the command is interrupted or concurrent operations run.

Other applications may observe intermediate states while `deleteMany` is in progress, depending on read concern and access patterns. Never build an assumption that "either all millions of documents disappear, or none disappear" from a single `deleteMany` call.

### 8.3. When You Need a Transaction

If business rules require deleting an Order, deleting related temporary records, and inserting an `AuditEvent` to succeed or fail together, consider a **multi-document transaction** on a supported MongoDB deployment. Conceptual example at the driver layer:

~~~text
START TRANSACTION
  Delete Order while still in draft status
  Delete related temporary records
  Insert AuditEvent with reason and actor
COMMIT
~~~

Do not put a multi-million-document deletion into one giant transaction just to be "safer": transactions carry management overhead, time limits, resource usage, and conflict risk. Transaction boundaries must match the set of documents that genuinely require atomicity.

Some domains require keeping audit records **even when the delete transaction fails**; that is a separate policy and must be designed explicitly rather than assuming the audit log will roll back or persist automatically.

### 8.4. Deleting Related Documents Has No Default Cascade

In MongoDB, deleting a Customer does not automatically delete Orders via a foreign key as in some relational models. Fields such as `customerId` and `orderId` are typically logical references. If cascading or snapshotting is needed:

- Specify explicitly which child data must be deleted, retained, or anonymized.
- Determine the required ordering and atomicity.
- Avoid deleting data subject to legal, financial, or audit retention obligations.
- Design how the application handles orphaned references.

Deleting "to keep things tidy" while ignoring related data lifecycles can create business bugs that are harder to fix than retaining the document.

## 9. Write Concern, Errors, and Retryability

### 9.1. deletedCount Is Not a Backup

When an operation is acknowledged by the server, **deletedCount** tells you how many documents were deleted by that command. It **does not preserve the full contents** of the lost documents. If recovery is required, you need an appropriate backup policy, point-in-time recovery, snapshots, archives, or an audit/pre-image stream.

For unacknowledged writes (**unacknowledged write**, such as write concern `w: 0`), the client cannot rely on `deletedCount` as an accurate result; the application needs a write concern policy suited to the risk level.

### 9.2. Write Concern Affects Acknowledged Durability

Example illustrating a delete operation requiring write acknowledgment under the **majority** policy:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne(
    {
      _id: "o002",
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "draft"
    },
    {
      writeConcern: { w: "majority", wtimeout: 5000 }
    }
  );
~~~

The meaning of `majority` depends on the topology of the replica set or sharded deployment. On a standalone server or different environment configurations, write concern settings may need adjustment; do not copy this snippet without understanding the actual topology. A **WriteConcernError** or timeout does not guarantee the operation did not happen: you must reconcile state and handle indeterminate outcomes.

### 9.3. Retrying Delete Operations

Fundamentally, **deleteOne** is a single-document delete operation and belongs to the group eligible for **retryable writes** when driver, server, and session conditions are met. **deleteMany** is not part of the single-document retryable writes set under that same mechanism. Actual automatic retry behavior depends on driver configuration, topology, and supported versions.

Do not assume retries are harmless in all cases:

- Retrying `deleteOne` by a **fixed `_id`** after deletion typically yields `deletedCount = 0` if executed as a fresh command, though the returned result may be handled according to retryable-writes session semantics.
- Retrying a broad filter like **{ status: "cancelled" }** can delete **a different document** on the next attempt.
- Retrying `deleteMany` with a time- or status-based filter can catch additional documents that became eligible during the retry window.

For critical API requests, use stable keys, explicit status guards, idempotency keys where required by the domain, and state reconciliation after network errors.

### 9.4. Error Categories to Distinguish

| Scenario | Meaning |
| --- | --- |
| `deletedCount = 0`, no exception | No document matched at deletion time; not necessarily a system error |
| Unauthorized | The account lacks delete privileges or permissions on the collection |
| Write concern error/timeout | Write acknowledgment requirements were not met; actual state may need verification |
| Network error | It may be unknown whether the server executed the operation |
| Write conflict/transaction aborted | Must handle retries according to transaction and driver contracts |
| Invalid hint or missing index | Query option is invalid for the current index state |
| Collection/shard changes | May require retrying or coordinating with sharded cluster operations |

## 10. Large-Scale Deletion and Performance

### 10.1. Indexes Help Identify Candidate Documents

If the application frequently deletes temporary sessions by **tenantId + status + createdAt**, an index covering the key filter fields can reduce the number of documents scanned to find candidates. Example lab index:

~~~javascript
{
  dataset: 1,
  tenantId: 1,
  status: 1,
  legalHold: 1,
  createdAt: 1,
  _id: 1
}
~~~

This index mirrors the filter and sort of the batch cleanup in this lesson. However, every document deletion also has to remove its associated index entries, so **more indexes increase write amplification**. Do not create an index solely for a one-off job if long-term maintenance costs outweigh the benefit.

### 10.2. Checking explain for Candidate Selection

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .find({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    status: "cancelled",
    legalHold: false,
    createdAt: { $lt: ISODate("2026-01-05T00:00:00.000Z") }
  })
  .sort({ createdAt: 1, _id: 1 })
  .limit(2)
  .explain("executionStats");
~~~

Inspect **winningPlan**, **totalKeysExamined**, **totalDocsExamined**, and **nReturned**. With only ten documents, MongoDB may choose `COLLSCAN` because it is cheaper than an index scan; you cannot extrapolate production efficiency from a tiny lab dataset. Test on production-like data and evaluate candidate lookup speed, deletion throughput, index size, replication lag, and impact on concurrent reads.

### 10.3. Deleting in a Sharded Collection

In a sharded cluster, document placement depends on the **shard key**. A filter containing the full shard key typically enables targeted routing; broad filters or filters missing routing fields may force scatter-gather across multiple shards. Routing rules and limitations for `deleteOne`, `findOneAndDelete`, and `deleteMany` must be checked against your deployed MongoDB version.

When chunks migrate or concurrent writes occur, do not assume a single broad `deleteMany` processes every document against an immutable cluster snapshot. For long-running cleanup jobs, monitor remaining counts, re-run by filter if needed, and check for newly eligible data created during cleanup.

## 11. Hard Delete, Soft Delete, TTL, and Archiving

Not every "delete" requirement should call `deleteOne` or `deleteMany`. Choose according to the **data lifecycle**.

### 11.1. Hard Delete

**Hard delete** removes the document from the collection:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .deleteOne({
    _id: "o001",
    dataset: "delete-lab-v1",
    status: "draft"
  });
~~~

Suitable when data truly no longer needs to be kept and policy allows permanent removal from the collection. A delete command does not guarantee external backups are purged; data erasure obligations must cover related storage systems according to policy.

### 11.2. Soft Delete

**Soft delete** marks a document as logically deleted in business terms, while keeping the document in MongoDB:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .updateOne(
    {
      _id: "o002",
      dataset: "delete-lab-v1",
      tenantId: "t001",
      status: "draft",
      deletedAt: { $exists: false }
    },
    {
      $set: {
        deletedAt: new Date(),
        deletionReason: "customer_request"
      }
    }
  );
~~~

Queries displaying active documents must include the condition:

~~~javascript
db.getSiblingDB("mongo_delete_lab")
  .getCollection("lab_orders")
  .find({
    dataset: "delete-lab-v1",
    tenantId: "t001",
    deletedAt: { $exists: false }
  });
~~~

Soft delete allows a window for undo or reconciliation, but **it does not remove data from the database or backups**. If personal data must genuinely be erased, you need a purge process and access controls during the interim retention period.

### 11.3. TTL Indexes for Expiring Data

For temporary sessions/tokens, MongoDB supports **TTL indexes** for automatic deletion based on a `Date` field:

~~~javascript
const lab = db.getSiblingDB("mongo_delete_lab");
const sessions = lab.getCollection("lab_sessions");

sessions.createIndex(
  { expiresAt: 1 },
  { expireAfterSeconds: 0, name: "ttl_lab_expires_at" }
);

sessions.insertOne({
  _id: "session-example-001",
  dataset: "delete-lab-v1",
  tenantId: "t001",
  expiresAt: new Date(Date.now() + 15 * 60 * 1000)
});
~~~

TTL cleans up data via a background thread and **does not guarantee a document disappears at the exact millisecond of expiration**. Applications must still check `expiresAt` when validating whether a session is active. A TTL index is normally defined on a single timestamp field and does not replace a multi-condition deletion strategy involving `legalHold`, `tenantId`, or business status.

Do not apply TTL to paid orders simply because they are old: retention periods, audits, refunds, and legal requirements must be determined first.

### 11.4. Archiving Before Purging

For data that must be auditable for years but rarely accessed online, **archiving** may be needed before deletion. A controlled workflow:

~~~text
Select documents eligible for archiving
  -> Write to archive storage
  -> Verify archive data is complete and readable
  -> Write checkpoint / reconciliation evidence
  -> Delete in batches from the active collection
~~~

Never execute the delete step before confirming the archive has been written and fully verified. If archiving and deleting span two different systems, you need retry/idempotency mechanisms and reconciliation because there is no default atomic transaction across two systems.

## 12. Safety Workflow Before Deleting in Production

For a multi-document delete operation, you can follow this sequence:

**Step 1 — Write the deletion policy.** Identify who requested it, the data type, retention period, legal holds, tenant, time range, recovery needs, and approval source.

**Step 2 — Lock down the scope.** Every filter must enforce tenant/owner or dataset validation per business rules. Prefer `_id` conditions for single-document deletions. Never accept an arbitrary MongoDB filter directly from an external client without restricting allowed fields and operators.

**Step 3 — Preview and count.** Use `find` with an appropriate projection, `countDocuments`, sample data, and verify time-range boundaries. In multi-tenant environments, verify that other tenants are excluded from the result set.

**Step 4 — Set a budget.** Define max documents per batch, execution window, target rate, alert metrics, pause conditions, and error recovery steps.

**Step 5 — Ensure a recovery path.** Verify backups/point-in-time restore, archives, or appropriate audit logs. Account for restoring both documents and related references.

**Step 6 — Run small batches with protective conditions.** Fetch bounded IDs, re-apply status/tenant/legalHold guards during deletion, and log `deletedCount` and checkpoints.

**Step 7 — Reconcile and record.** Monitor remaining candidates, read/write rates, replication lag, errors/timeouts, and reconcile counts against scope. Never treat `deletedCount` alone as proof that every business objective was met.

**Step 8 — Know when to stop.** If `deletedCount` looks abnormal, the scope deviates from expectations, backups are unavailable, or service health degrades, halt the job and investigate before resuming.

### 12.1. Examples of Safe vs. Risky Filters

| Filter | Assessment |
| --- | --- |
| **{ _id: id, tenantId: authenticatedTenantId, status: "draft" }** | Suitable for controlled single-draft deletion |
| **{ tenantId, status: "cancelled", legalHold: false, createdAt: { $lt: cutoff } }** | Properly scoped for retention batching if tenant/cutoff are validated |
| **{ status: "cancelled" }** | May delete across all tenants and all time |
| **{}** | Deletes the entire collection when used with `deleteMany` |
| **{ createdAt: { $lt: new Date() } }** | Extremely broad; may delete almost all existing data |
| Filter taken directly from an HTTP request | Risk of injection/wrong scope without validation/allowlisting |

## 13. Practice Exercises

### Exercise 1 — Predict deletedCount

Re-run the seed. Execute **deleteOne** with `_id` `o001`, then run it a second time. Record `deletedCount` for each run and explain why the second command does not throw an error even though no document was found.

### Exercise 2 — Same Filter, Different Behavior: deleteOne vs. deleteMany

From the seeded data, count the documents with `tenantId` `t001`, `status` `cancelled`, and `legalHold` `false`. Compare the outcome using `deleteOne` versus `deleteMany`. Why can you not reliably predict which exact document `deleteOne` will remove when the filter matches multiple documents?

### Exercise 3 — Delete the Single Oldest Document

From the seeded data, use **findOneAndDelete** sorting by `createdAt` ascending then `_id` ascending to delete one `cancelled` order without a legal hold. Verify the returned `_id` and explain how this differs from calling `find` first and `deleteOne` afterward.

### Exercise 4 — Delete at Most Two Documents

From the seeded data, select at most two `cancelled` documents for tenant `t001`, build the `_id` list, and delete them using `deleteMany` with **_id: { $in: ids }**. Repeat the `tenantId`/`status`/`legalHold` conditions in the delete filter. Explain why `deletedCount` can be less than the number of selected IDs under concurrent writes.

### Exercise 5 — Batch Cleanup

Write a job that runs at most five batches of up to two documents each, using `cutoff` and `legalHold`. Log the batch number, selected count, `deletedCount`, and remaining candidate count. Explain why using `skip` on a set being actively deleted can miss documents.

### Exercise 6 — BulkWrite and Transactions

Create a `bulkWrite` containing a `deleteOne` for a draft, a `deleteMany` for cancelled orders, and an `updateOne` modifying a note field. Compare `ordered: true` and `ordered: false`. If the second operation fails after the first succeeds, does `bulkWrite` automatically roll back the first operation? Propose a transaction boundary when all three operations must be all-or-nothing.

### Exercise 7 — Choosing Hard Delete vs. Soft Delete

Classify the following cases: abandoned shopping cart, expired session, paid order, account deletion request, audit event, and mistyped entry. Recommend hard delete, soft delete, TTL, or archive based on retention period and access rules. Give one scenario where soft delete fails to satisfy personal data erasure obligations.

### Exercise 8 — Network Failure During Deletion

A client sends a `deleteOne` by `_id` and loses the connection before receiving the response. What might have happened on the server? How would you inspect state and handle retries? Contrast this with retrying a `deleteMany` that uses a very broad filter while new documents continue to arrive.

### Exercise 9 — Index Design for Retention

Suppose a collection has 50 million orders, and a nightly job purges expired `cancelled` orders for a given tenant that are not on legal hold. Write the candidate-selection query, propose a compound index, inspect `explain`, and list the metrics you would monitor beyond query duration (e.g., write latency, replication lag, index size).

## 14. MongoDB References

- MongoDB Manual — [db.collection.deleteOne()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteOne/).
- MongoDB Manual — [db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/).
- MongoDB Manual — [db.collection.findOneAndDelete()](https://www.mongodb.com/docs/manual/reference/method/db.collection.findOneAndDelete/).
- MongoDB Manual — [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/).
- MongoDB Manual — [Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/).
- MongoDB Manual — [Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/).
- MongoDB Manual — [TTL Indexes](https://www.mongodb.com/docs/manual/core/index-ttl/).

**Conclusion:** **deleteOne** caps the deleted document count at one, but does not let you assume selection order when the filter matches multiple records. **deleteMany** deletes every matching document and has no API-level `limit` or `sort`; you must design your own ID-selection batching when capping N records per pass. Every deletion requires accurate filters, an understanding of atomicity boundaries, proper error/retry handling, and an appropriate retention or recovery policy. In real systems, the quality of a deletion workflow is measured not just by speed, but by **never deleting the wrong data** and **being able to account accurately for every affected record**.
