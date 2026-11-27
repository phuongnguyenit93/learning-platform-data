# Ordered, Unordered, and Reading bulkWrite Results or Errors in MongoDB

## Lesson Objectives

In MongoDB, `bulkWrite()` lets you batch multiple write operations into a single call. These operations can insert, update, replace, or delete documents. Two key execution modes are **ordered** and **unordered**, which govern how MongoDB handles operation order and whether execution continues when a write error occurs.

After this lesson, you will be able to:

- Use all six operation types in collection-level `bulkWrite()`.
- Distinguish `ordered: true` (default) from `ordered: false`.
- Interpret `insertedCount`, `matchedCount`, `modifiedCount`, `deletedCount`, `upsertedCount`, and ID maps.
- Distinguish **write errors**, **write concern errors**, and command/network errors.
- Analyze **partial success**, map error indexes back to source operations, and handle retries safely.
- Design bulk jobs for imports, syncs, or deletions using appropriate business keys, indexes, and checkpoints.
- Understand why `bulkWrite` does not automatically carry transaction semantics and does not replace domain postconditions.

> **Remember:** Ordered mode stops at the first write error, while unordered mode can continue independent operations, yet **both can produce partial success**. Even an error-free response does not prove every update or delete affected the number of documents your business logic expected.

---

## 1. How Does a Bulk Write Differ from Many Individual Commands?

An application syncing 1,000 products could call `updateOne()` 1,000 times, or send the operation list through `bulkWrite()`. Batching operations reduces client–server communication overhead and creates a centralized point for handling results.

Syntax in `mongosh`:

~~~javascript
db.products.bulkWrite(
  [
    {
      insertOne: {
        document: { _id: "SKU-01", name: "Keyboard", stock: 10 }
      }
    },
    {
      updateOne: {
        filter: { _id: "SKU-02" },
        update: { $set: { stock: 20 } }
      }
    },
    {
      deleteOne: {
        filter: { _id: "TEMP-01" }
      }
    }
  ],
  { ordered: true }
);
~~~

Actual throughput still depends on indexes, write concern, server load, operation types, batch size, network, and concurrency. Bulk does not turn an unindexed filter into a fast query.

**Scope:** This lesson uses the **`db.collection.bulkWrite()`** API, where every operation targets **a single collection**. Newer MongoDB/driver versions may offer client-level APIs spanning multiple namespaces, with different syntax and return shapes; do not conflate them.

## 2. The Six Common Operations

| Type | Purpose | Key properties |
|---|---|---|
| `insertOne` | Insert one document | `document` |
| `updateOne` | Update at most one document | `filter`, `update`, optional `upsert` |
| `updateMany` | Update all matching documents | `filter`, `update` |
| `replaceOne` | Replace one matching document | `filter`, `replacement` |
| `deleteOne` | Delete at most one document | `filter` |
| `deleteMany` | Delete all matching documents | `filter` |

Complete example:

~~~javascript
db.inventory.bulkWrite(
  [
    {
      insertOne: {
        document: {
          _id: "P-100",
          name: "Headphones",
          stock: 100
        }
      }
    },
    {
      updateOne: {
        filter: { _id: "P-101" },
        update: { $set: { status: "ACTIVE" } }
      }
    },
    {
      updateMany: {
        filter: { category: "LEGACY" },
        update: { $set: { archived: true } }
      }
    },
    {
      replaceOne: {
        filter: { _id: "P-102" },
        replacement: {
          _id: "P-102",
          name: "Mouse",
          stock: 25
        }
      }
    },
    {
      deleteOne: {
        filter: { _id: "TEMP-1" }
      }
    },
    {
      deleteMany: {
        filter: { expired: true, archived: true }
      }
    }
  ],
  { ordered: true }
);
~~~

Keep in mind:

- `replaceOne` replaces the document with `replacement`; existing fields omitted from `replacement` are lost.
- One `updateMany` can match many documents even though it is **a single operation**.
- `deleteMany` with an empty filter can wipe the entire collection.
- An operation that matches no document completes normally with matched/deleted counts of 0.
- `upsert: true` can create a new document when the filter matches nothing; enable it only when domain rules allow creation.

---

## 3. Ordered: Sequential Execution and Stopping After a Write Error

When `ordered` is omitted, collection-level `bulkWrite` defaults to `ordered: true`.

~~~javascript
db.collectionName.bulkWrite(operations, { ordered: true });
~~~

Semantics:

1. Operations execute in the order they appear in the array.
2. Upon encountering a **write error**, subsequent operations halt per ordered semantics.
3. Operations that succeeded before the error **are not automatically rolled back**.
4. An operation matching 0 documents is not a write error and does not stop the batch.

Illustration:

~~~text
Index 0: INSERT A            -> succeeds
Index 1: INSERT duplicate ID -> write error
Index 2: INSERT B            -> not executed
Index 3: UPDATE C            -> not executed

Already-written A may still exist.
~~~

Ordered mode fits cases where later operations depend on earlier ones, or when a job should stop early on error. However, it does not enforce domain preconditions by itself.

Example:

~~~javascript
db.workflows.bulkWrite(
  [
    {
      updateOne: {
        filter: { _id: "TASK-1", status: "READY" },
        update: { $set: { status: "RUNNING" } }
      }
    },
    {
      updateOne: {
        filter: { _id: "TASK-1" },
        update: { $set: { owner: "worker-A" } }
      }
    }
  ],
  { ordered: true }
);
~~~

If the first operation matches 0 documents, the second operation **still runs**. If you need "change owner only while status is READY," combine both fields into a single update with a shared filter:

~~~javascript
db.workflows.updateOne(
  { _id: "TASK-1", status: "READY" },
  {
    $set: {
      status: "RUNNING",
      owner: "worker-A"
    }
  }
);
~~~

A single update on one document is atomic, making it far better than two dependent updates whenever they can be merged.

## 4. Unordered: No Order Guarantee, Continuing Independent Writes

~~~javascript
db.collectionName.bulkWrite(operations, { ordered: false });
~~~

Semantics:

1. **Never infer execution order** from an operation's array index.
2. A write error does not automatically prevent other independent operations from running.
3. The bulk call can throw an **exception** even though many other operations succeeded.
4. Parallel or faster execution is not guaranteed across every workload.
5. Command-level, network, or fatal system errors can produce incomplete results without trying every operation.

Illustration:

~~~text
Index 0: INSERT A            -> may succeed
Index 1: INSERT duplicate ID -> write error
Index 2: INSERT B            -> may succeed

Unordered may yield partial success.
Actual chronological order is not guaranteed.
~~~

Unordered mode fits importing or upserting many independent records that have business keys and reconciliation/retry logic. It is **unsuitable** for a chain of operations where a later step relies on data created by an earlier step.

### 4.1. Comparison Table

| Criterion | Ordered | Unordered |
|---|---|---|
| Option | `ordered: true` | `ordered: false` |
| Default | Yes | No |
| Ordering | Follows array order | Not guaranteed |
| Write error | Halts subsequent operations | Continues independent operations |
| Writes before error | May already be persisted | May already be persisted |
| Whole-bulk atomicity | **No** | **No** |
| Dependent operations | Suitable for ordering | Avoid |
| Independent ops | Works | Well-suited |
| Throughput | Workload-dependent | Potentially higher, not guaranteed |
| Error handling | Single error location + partial result | Multiple error locations + partial result |

### 4.2. Pitfall: Dependency with Zero Matches Raises No Error

~~~javascript
const ops = [
  {
    insertOne: {
      document: { _id: "DOC-1", status: "CREATED" }
    }
  },
  {
    updateOne: {
      filter: { _id: "DOC-1" },
      update: { $set: { status: "READY" } }
    }
  }
];
~~~

In unordered mode, the update may run before the insert and match 0 documents. Next, the insert creates the document in `CREATED` status. **No write error occurs, yet the domain state is wrong.** Solution: insert directly in `READY` status, or use ordered mode / a transaction when multi-step execution is genuinely needed.

---

## 5. Hands-On Ordered Execution with a Duplicate Key

The commands below are for the lab database only. If re-running, use a new collection name or explicitly clean test data; never drop production data.

~~~javascript
use bulk_lab

db.ordered_products.insertOne({
  _id: "EXISTING-01",
  name: "Already exists"
});
~~~

The `_id` key is unique within a collection per MongoDB rules. Attempting a duplicate insert typically raises error code **11000**.

~~~javascript
const orderedOps = [
  {
    insertOne: {
      document: { _id: "NEW-01", name: "Product A" }
    }
  },
  {
    insertOne: {
      document: { _id: "EXISTING-01", name: "Duplicate ID" }
    }
  },
  {
    insertOne: {
      document: { _id: "NEW-02", name: "Product B" }
    }
  }
];

try {
  printjson(
    db.ordered_products.bulkWrite(
      orderedOps,
      { ordered: true }
    )
  );
} catch (error) {
  print(error.message);
}
~~~

Inspect state:

~~~javascript
db.ordered_products
  .find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
~~~

Assuming no other errors:

- Index 0 inserts `NEW-01` successfully.
- Index 1 collides with `EXISTING-01`, raising a write error.
- Index 2 is not executed.
- `NEW-01` remains persisted despite the bulk error.
- `NEW-02` does not exist.

This demonstrates **stopping in order without automatic rollback**.

## 6. Hands-On Unordered Execution with the Same Error

Use a separate collection:

~~~javascript
db.unordered_products.insertOne({
  _id: "EXISTING-01",
  name: "Already exists"
});

const unorderedOps = [
  {
    insertOne: {
      document: { _id: "NEW-01", name: "Product A" }
    }
  },
  {
    insertOne: {
      document: { _id: "EXISTING-01", name: "Duplicate ID" }
    }
  },
  {
    insertOne: {
      document: { _id: "NEW-02", name: "Product B" }
    }
  }
];

try {
  printjson(
    db.unordered_products.bulkWrite(
      unorderedOps,
      { ordered: false }
    )
  );
} catch (error) {
  print(error.message);
}
~~~

Observe:

~~~javascript
db.unordered_products
  .find({}, { _id: 1, name: 1 })
  .sort({ _id: 1 });
~~~

In the lab without other errors, both independent inserts `NEW-01` and `NEW-02` can succeed while the duplicate insert fails. The call still throws an exception because one operation failed.

**Why seed the duplicate ID before the batch?** If two unordered operations both try to insert a nonexistent ID, you cannot predict from array position which insert wins. Pre-seeding the duplicate ID cleanly tests continuation behavior after an error.

---

## 7. How to Read Success Results

Illustrative example of result shape—**not output from a specific lab run**:

~~~javascript
{
  acknowledged: true,
  insertedCount: 2,
  matchedCount: 3,
  modifiedCount: 2,
  deletedCount: 1,
  upsertedCount: 1,
  insertedIds: {
    "0": "NEW-01",
    "4": "NEW-02"
  },
  upsertedIds: {
    "2": "SKU-201"
  }
}
~~~

Drivers and versions vary in how they represent IDs and metadata; check the API spec for your target environment.

| Field | Meaning |
|---|---|
| `acknowledged` | Whether the operation was acknowledged per the requested write concern |
| `insertedCount` | Number of documents inserted by insert operations |
| `matchedCount` | Total documents matched by update/replace operations |
| `modifiedCount` | Total documents actually modified |
| `deletedCount` | Number of documents deleted |
| `upsertedCount` | Number of new documents created by upserts |
| `insertedIds` | Inserted IDs, typically keyed by operation index |
| `upsertedIds` | Upserted IDs, typically keyed by operation index |

### 7.1. Counters Measure Documents, Not Operations

One `updateMany` is a single operation yet can modify 100 documents; one `deleteMany` can remove 500 documents. Thus, you cannot sum document counters as a general formula for counting how many operations succeeded.

### 7.2. Matched Differs from Modified

~~~javascript
db.count_demo.insertOne({
  _id: "A",
  status: "ACTIVE"
});

const result = db.count_demo.bulkWrite([
  {
    updateOne: {
      filter: { _id: "A" },
      update: { $set: { status: "ACTIVE" } }
    }
  }
]);

printjson(result);
~~~

The document matched, yet its value did not change, so you may observe:

~~~text
matchedCount = 1
modifiedCount = 0
~~~

This is not a write error.

Similarly, a `deleteOne` matching no document completes normally with `deletedCount: 0`.

### 7.3. Upserts Are Counted Separately

~~~javascript
db.count_demo.bulkWrite([
  {
    updateOne: {
      filter: { _id: "B" },
      update: {
        $set: { status: "ACTIVE" },
        $setOnInsert: { source: "import" }
      },
      upsert: true
    }
  }
]);
~~~

If `B` did not exist, `upsertedCount` increments and the ID appears in `upsertedIds`; do not inspect only `insertedCount` to determine newly created documents.

### 7.4. ID Maps Follow Input Array Positions

~~~javascript
const ops = [
  { insertOne: { document: { _id: "A" } } }, // index 0
  {
    updateOne: {
      filter: { _id: "B" },
      update: { $set: { x: 1 } }
    }
  }, // index 1
  { insertOne: { document: { _id: "C" } } } // index 2
];
~~~

`insertedIds` contains keys `0` and `2`. Do not treat them as "the 0th and 1st inserts" and lose alignment with the original `ops` array.

### 7.5. Unacknowledged Writes

If you use an unacknowledged write concern, the caller cannot rely on the same counts or confirmations as with acknowledged writes. For import jobs requiring reconciliation, use an appropriate acknowledged write concern.

---

## 8. When bulkWrite Errors: Three Categories to Distinguish

### 8.1. Per-Operation Write Errors

Example error metadata might include:

~~~javascript
{
  index: 1,
  code: 11000,
  errmsg: "E11000 duplicate key error ..."
}
~~~

This is an **illustrative shape**, not a guaranteed exception schema across every shell, driver, and version.

| Property | Usage |
|---|---|
| `index` | Position of the failing operation in the input array, typically 0-based |
| `code` | MongoDB error code |
| `errmsg` / `message` | Error description |
| `op` or equivalent details | Operation info if exposed by the API |
| Partial result | Writes confirmed successful so far, if available |

Common codes:

- **11000:** duplicate key, e.g., duplicate `_id` or unique index value.
- **121:** document validation failure.
- Update path errors: invalid or conflicting field paths.
- Authorization errors: user lacks permission for the operation.
- Size/limit errors: document or message exceeds supported limits.

Never catch every exception and assume it is an ignorable duplicate key.

### 8.2. Write Concern Errors Are Not Write Errors

Example requiring `majority`:

~~~javascript
db.catalog.bulkWrite(
  operations,
  {
    ordered: false,
    writeConcern: {
      w: "majority",
      wtimeout: 5000
    }
  }
);
~~~

If the primary applied the writes but majority acknowledgment was not reached before timeout, the caller receives a write concern error. That **does not prove the writes failed to apply**. The state is indeterminate with respect to the requested acknowledgment guarantee.

Reconcile by business ID, inspect replica set health and replication lag, and consult your retry policy. Replaying a batch containing `$inc` can corrupt totals.

### 8.3. Network/Command Errors Can Leave State Unknown

If the client sends a bulk and loses the connection before receiving the response, the server may have completed part or all of it. Never deduce "no response received = zero writes occurred."

Severe command-level or system errors can also prevent remaining operations from running even in unordered mode; "continue after write error" does not cover every failure class.

---

## 9. Catching Errors in mongosh and Correlating Operation Indexes

~~~javascript
const records = [
  { sourceKey: "IMP-100", sku: "SKU-100", name: "A" },
  { sourceKey: "IMP-101", sku: "SKU-101", name: "B" },
  { sourceKey: "IMP-102", sku: "SKU-102", name: "C" }
];

const ops = records.map((record) => ({
  updateOne: {
    filter: { sku: record.sku },
    update: {
      $set: { name: record.name },
      $setOnInsert: { sourceKey: record.sourceKey }
    },
    upsert: true
  }
}));

try {
  const result = db.catalog.bulkWrite(
    ops,
    { ordered: false }
  );
  printjson(result);
} catch (error) {
  print(error.message);

  // Exact properties depend on the mongosh/driver environment.
  if (error.writeErrors) {
    printjson(error.writeErrors);
  }
  if (error.writeConcernErrors) {
    printjson(error.writeConcernErrors);
  }
  if (error.result) {
    printjson(error.result);
  }
}
~~~

If a write error reports `index: 1`, the corresponding source record is:

~~~javascript
records[1];
// { sourceKey: "IMP-101", sku: "SKU-101", name: "B" }
~~~

Access exception fields **only when present**. Different environments expose error lists, partial results, and write concern errors through different properties or methods. Network errors may carry no partial result at all. Check the contract of your driver.

Logs should record `batchId`, operation index, business key, and error code—avoid logging entire payloads if they contain sensitive data.

---

## 10. Idempotency and Controlled Retries

### 10.1. Idempotent Operations

An operation is idempotent when re-running the same request produces no unintended side effects.

Relatively retry-friendly:

~~~javascript
{
  updateOne: {
    filter: { _id: "P-1" },
    update: { $set: { status: "ACTIVE" } }
  }
}
~~~

Assuming no competing writers or other side effects, re-running sets `status` to `ACTIVE`.

Non-idempotent:

~~~javascript
{
  updateOne: {
    filter: { _id: "P-1" },
    update: { $inc: { stock: 1 } }
  }
}
~~~

If the first write succeeded but the response was lost, retrying increments `stock` a second time.

### 10.2. Upserts and Business Keys

~~~javascript
db.catalog.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_catalog_sku" }
);
~~~

An import can upsert by SKU:

~~~javascript
db.catalog.bulkWrite(
  [
    {
      updateOne: {
        filter: { sku: "SKU-A" },
        update: {
          $set: { name: "A", price: 120000 },
          $setOnInsert: { source: "import" }
        },
        upsert: true
      }
    },
    {
      updateOne: {
        filter: { sku: "SKU-B" },
        update: {
          $set: { name: "B", price: 85000 },
          $setOnInsert: { source: "import" }
        },
        upsert: true
      }
    }
  ],
  { ordered: false }
);
~~~

Distinct SKUs are independent operations. A unique index reduces duplicate risk, though two concurrent writers upserting the same SKU can still collide with a duplicate key error under certain race conditions.

### 10.3. Do Not Retry Blindly

| Error | Approach |
|---|---|
| Duplicate key 11000 | Read the existing document and verify whether its data matches requirements |
| Validation 121 | Fix input or schema through controlled process |
| Unauthorized | Fix permissions properly rather than over-privileging |
| Write concern timeout | Reconcile state before retrying |
| Network timeout | Use business key/request ID to check whether the write landed |
| Update matched 0 | Inspect filter and business state; do not assume a transport failure |

Drivers may provide retryable writes under specific prerequisites. Never assume every bulk shape and every operation is automatically safe to retry.

---

## 11. BulkWrite and Transactions

### 11.1. Not an Atomic Unit

MongoDB provides atomicity at the **single-document** level; a normal bulk containing multiple operations **does not automatically form a batch-wide transaction**.

~~~text
bulkWrite:
  insert A -> succeeds
  insert B -> succeeds
  update C -> write error
  delete D -> depends on ordered/unordered and error type

Without a transaction:
  A and B may still exist.
  Failure on C does not automatically undo A/B.
~~~

Likewise, an `updateMany` affecting multiple documents does not atomically update the entire set as one all-or-nothing unit.

### 11.2. Bulk Inside a Transaction

MongoDB supports multi-document transactions on compatible versions and topologies. When running a bulk inside a transaction, reason in terms of **transaction commit/abort semantics**, not external bulk partial-success rules. A write failure can abort the transaction; unordered mode is not a mechanism to "ignore errors and commit the good ones."

Transactions incur resource overhead, conflict/retry complexity, and execution limits. Never wrap a multi-hour massive import inside one transaction just for all-or-nothing semantics; prefer checkpointed batches and idempotency.

---

## 12. Java Sync Driver: Reading Results or Exceptions

The Java Sync Driver offers `MongoCollection.bulkWrite` taking `List<WriteModel<T>>` and `BulkWriteOptions`.

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;
import com.mongodb.bulk.BulkWriteResult;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.BulkWriteOptions;
import com.mongodb.client.model.DeleteOneModel;
import com.mongodb.client.model.InsertOneModel;
import com.mongodb.client.model.UpdateOneModel;
import com.mongodb.client.model.WriteModel;
import org.bson.Document;

import java.util.Arrays;
import java.util.List;

import static com.mongodb.client.model.Filters.eq;
import static com.mongodb.client.model.Updates.set;

public class BulkExample {

    public static void run(MongoCollection<Document> collection) {

        List<WriteModel<Document>> ops = Arrays.asList(
            new InsertOneModel<>(
                new Document("_id", "SKU-501")
                    .append("name", "Keyboard")
            ),
            new UpdateOneModel<>(
                eq("_id", "SKU-502"),
                set("status", "ACTIVE")
            ),
            new DeleteOneModel<>(
                eq("_id", "TEMP-501")
            )
        );

        try {
            BulkWriteResult result = collection.bulkWrite(
                ops,
                new BulkWriteOptions().ordered(false)
            );

            System.out.println(
                "Inserted: " + result.getInsertedCount()
            );
            System.out.println(
                "Matched: " + result.getMatchedCount()
            );
            System.out.println(
                "Modified: " + result.getModifiedCount()
            );
            System.out.println(
                "Deleted: " + result.getDeletedCount()
            );
            System.out.println(
                "Upserts: " + result.getUpserts().size()
            );

        } catch (MongoBulkWriteException error) {
            for (BulkWriteError failure : error.getWriteErrors()) {
                System.err.println(
                    "Index=" + failure.getIndex()
                    + ", code=" + failure.getCode()
                    + ", message=" + failure.getMessage()
                );
            }

            BulkWriteResult partial = error.getWriteResult();

            if (partial != null && partial.wasAcknowledged()) {
                System.err.println(
                    "Partial inserted=" + partial.getInsertedCount()
                    + ", modified=" + partial.getModifiedCount()
                    + ", deleted=" + partial.getDeletedCount()
                );
            }

            if (error.getWriteConcernError() != null) {
                System.err.println(
                    "Write concern error="
                    + error.getWriteConcernError().getMessage()
                );
            }
        }
    }
}
~~~

This uses common APIs and assumes `collection` is already connected. Exact packages, methods, and exception behavior depend on your Java Driver version; verify against project documentation. Not every network or command error surfaces as `MongoBulkWriteException`, so production code must handle other exceptions too.

Mapping errors back to source keys:

~~~java
List<String> businessIds = Arrays.asList(
    "SKU-501",
    "SKU-502",
    "TEMP-501"
);

int index = failure.getIndex();

if (index >= 0 && index < businessIds.size()) {
    String businessKey = businessIds.get(index);
    System.err.println("Failed key=" + businessKey);
}
~~~

Even when a driver splits a large batch internally, it preserves **API index alignment**, letting you map errors back to business keys for reconciliation.

---

## 13. Import Reporting with Partial Success

An import job can define a reporting DTO:

~~~json
{
  "batchId": "product-import-20261114-001",
  "requestedOperations": 1000,
  "ordered": false,
  "state": "PARTIAL_SUCCESS",
  "reported": {
    "insertedCount": 700,
    "matchedCount": 200,
    "modifiedCount": 190,
    "deletedCount": 0,
    "upsertedCount": 85
  },
  "errors": [
    {
      "operationIndex": 15,
      "businessKey": "SKU-101",
      "code": 11000,
      "category": "DUPLICATE_KEY"
    }
  ],
  "reconciliationRequired": true
}
~~~

**This is an application-designed report schema**, not a raw MongoDB response. The numbers are illustrative and do not correspond to any specific lab run.

Possible states:

| Status | Meaning |
|---|---|
| `COMPLETED` | All requests acknowledged and postconditions verified |
| `PARTIAL_SUCCESS` | Some operations succeeded and some failed |
| `FAILED` | No confirmed completion or the job could not run |
| `UNKNOWN_REQUIRES_RECONCILIATION` | Missing definitive proof due to network/write concern error |
| `VALIDATION_REJECTED` | Input rejected before sending the bulk |

Record batch ID, source records, logic version, ordered flag, write concern, counters, error index/code, business keys, and reconciliation state.

**Never use** `insertedCount + matchedCount + deletedCount` as a universal total of successful operations: `updateMany` and `deleteMany` can touch multiple documents, and counters do not measure the same unit of work.

### 13.1. Reconciliation Workflow

1. Persist the original operation list or an immutable reference by batch ID.
2. Read write errors with their indexes and error codes.
3. Read partial results when exposed by the API.
4. Distinguish operations skipped due to `ordered: true` from operations in an unknown state due to lost connections.
5. Query by business key to check whether writes landed.
6. Retry only operations eligible for safe replay.
7. Mark complete only after verifying domain postconditions.

---

## 14. Batch Size and Performance

Bulk does not fix unindexed filters. For example, thousands of updates by `sku` should have an index:

~~~javascript
db.catalog.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_catalog_sku" }
);
~~~

Before creating a unique index, resolve any existing duplicate data in the collection.

MongoDB enforces a BSON document size limit (typically **16 MiB**) as well as message/batch thresholds. Drivers automatically split oversized bulks into smaller server batches. Avoid buffering millions of operations in memory without evaluating:

- Client RAM consumption.
- Request and error-response payload sizes.
- Write pressure, index maintenance, network bandwidth, and replication lag.
- Ability to resume or retry per chunk.
- Throughput and p95/p99 latency under load.
- Risk when a single operation updates or deletes huge document counts.

Use **measured** batch sizes, checkpoints, stable IDs, and error-resume logic. Unordered mode may run faster for independent writes, yet is never guaranteed; benchmark using realistic data, indexes, write concern, concurrency, and error rates.

### 14.1. Extra Caution with Bulk Deletes

Example purging expired sessions:

~~~javascript
db.sessions.bulkWrite(
  [
    {
      deleteMany: {
        filter: {
          status: "CLOSED",
          expiresAt: {
            $lt: ISODate("2026-11-01T00:00:00Z")
          }
        }
      }
    }
  ],
  { ordered: true }
);
~~~

Before writing, run `countDocuments` with the exact same filter, sample records, and verify indexes, tenant scope, backups, and restore plans:

~~~javascript
db.sessions.countDocuments({
  status: "CLOSED",
  expiresAt: {
    $lt: ISODate("2026-11-01T00:00:00Z")
  }
});
~~~

`deleteMany: {filter:{}}` can wipe every document. It is syntactically valid and completes with zero write errors despite severe business consequences.

---

## 15. Practical Scenarios

### A. Import with Duplicate Key

A batch has 1,000 independent inserts and one duplicate key insert.

- Ordered: stops at the first write error.
- Unordered: other independent inserts can still succeed.
- Action: read the failing index, inspect the existing document, and report partial success.

### B. Update Matching Zero Documents

An `updateOne` has a filter that is too strict and matches 0 documents.

- Does not raise a write error.
- Ordered execution continues.
- Action: verify postconditions; never equate "no exception" with "updated as expected."

### C. Schema Violation

A record lacks a required field and returns code 121.

- Input or validator must be fixed through proper channels.
- Retrying identically will not resolve the error.
- Unordered mode can still process the remaining valid records.

### D. Two Unordered Updates on the Same Document

~~~javascript
const ops = [
  {
    updateOne: {
      filter: { _id: "P-1" },
      update: { $set: { status: "ACTIVE" } }
    }
  },
  {
    updateOne: {
      filter: { _id: "P-1" },
      update: { $set: { status: "INACTIVE" } }
    }
  }
];
~~~

The final state depends on execution order. Never use unordered mode when ordering between two updates matters; combine into one operation or use conditional/versioned updates.

### E. Write Concern Timeout

The primary may have applied the write without reaching majority acknowledgment before timeout. Never assume nothing was written; reconcile state before retrying.

### F. Network Drops Mid-Batch

Partial writes may have occurred. Never blindly resend a batch containing `$inc` or inserts with newly generated IDs without deduplication.

### G. Bulk Inside a Transaction

When a transaction aborts, handle commit/abort per transaction semantics. Do not rely on the notion that "unordered continues past errors so it can commit the valid parts."

---

## 16. Common Misconceptions

**"Ordered = all-or-nothing."** False. Writes before the error do not automatically roll back.

**"Unordered = parallel execution."** Not guaranteed; it simply relaxes ordering requirements.

**"Unordered ignores errors and treats the whole batch as successful."** False. The bulk call still throws an exception despite partial successes.

**"One operation = one document."** False for `updateMany` and `deleteMany`.

**"Matched always equals modified."** False when field values do not change.

**"No exception means every update modified at least one document."** False; filters can match 0 documents.

**"Retrying the whole batch is always safe."** False for `$inc`, external side effects, or inserts lacking stable IDs.

**"Duplicate key proves the prior import succeeded correctly."** Not necessarily; inspect the existing document.

**"Write concern error = nothing was written."** False; writes may have applied without meeting the acknowledgment level.

**"Error index reflects execution order in unordered mode."** False; it reflects the operation's position in the input array per the API contract.

**"Logging `error.message` alone is enough."** Insufficient when handling imports with many failing records.

**"Collection `bulkWrite` works across multiple collections."** Not with the collection-level syntax in this lesson; multi-namespace client APIs are separate.

---

## 17. Safe Deployment Checklist

1. **List operations, business keys, and dependencies.** Avoid unordered mode if any operation relies on a prior one.
2. **Verify filters and indexes.** Before `updateMany`/`deleteMany`, count and sample documents.
3. **Choose `ordered` for semantics before speed.** Ordered for sequential dependencies; unordered for independent work.
4. **Design for idempotency.** Use unique business keys, request IDs, `$setOnInsert` where appropriate, and avoid blind retries.
5. **Size batches sensibly.** Manage client memory, server load, and checkpoints.
6. **Inspect full results.** Read counters and ID maps, not just whether an exception occurred.
7. **Classify errors.** Handle per-index write errors; reconcile indeterminate network or write concern errors.
8. **Verify postconditions.** Final data must match business goals even when no error was thrown.
9. **Persist reports.** Store batch ID, counters, errors, business keys, missing items, and recovery plan.

---

## 18. Exercises

### Exercise 1 — Ordered Encountering a Duplicate Key

In a lab collection, insert a document with ID `EXISTING`. Run an ordered bulk: insert `A`, insert `EXISTING`, insert `B`, update `A`. Predict which operations run and which do not. Why can `A` still exist afterward?

### Exercise 2 — Unordered with Three Independent Inserts

Create a separate collection with ID `EXISTING`. Run an unordered bulk inserting `A`, `EXISTING`, and `B`. Verify `A`/`B`, the duplicate error, and the error index. Why should you not infer the execution order of `A` and `B`?

### Exercise 3 — Matched vs. Modified

~~~javascript
db.bulk_counts.insertMany([
  { _id: 1, status: "ACTIVE" },
  { _id: 2, status: "NEW" },
  { _id: 3, status: "NEW" }
]);

db.bulk_counts.bulkWrite([
  {
    updateOne: {
      filter: { _id: 1 },
      update: { $set: { status: "ACTIVE" } }
    }
  },
  {
    updateMany: {
      filter: { status: "NEW" },
      update: { $set: { status: "ACTIVE" } }
    }
  }
]);
~~~

Explain why `matchedCount` differs from `modifiedCount`, and why both can exceed the number of operations.

### Exercise 4 — Upsert

Write a bulk with one `insertOne` and one `updateOne` using `upsert: true` that creates a new record. Inspect `insertedCount`, `upsertedCount`, and ID maps. How does the result change if you run the upsert a second time?

### Exercise 5 — Dependent Operations

Run an unordered bulk inserting `DOC-1` then updating `DOC-1`. State the two possible outcomes depending on execution order, and rewrite it as a single operation.

### Exercise 6 — Partial Failure Import

A batch of 500 operations hits 12 duplicate keys, 3 validation errors, and one write concern timeout. Design a reporting DTO, explain how to map error indexes to business keys, and define the retry strategy per failure category.

### Exercise 7 — Java Error Handler

Use `MongoBulkWriteException` in Java to read `getWriteErrors()`, `getWriteResult()`, and `getWriteConcernError()`. Explain why you still need to handle other network/command exceptions.

### Exercise 8 — Bulk Purging Old Data

A `sessions` collection holds tens of millions of documents. Purge only `CLOSED` sessions older than 90 days. Specify the filter, index, pre-delete count/sample checks, batch size, checkpointing, backup plan, and `deletedCount` reporting. How would you respond if a filter turned out to be wrong?

---

## 19. Review Questions

1. What are the six operation types in collection-level `bulkWrite`?
2. What is the default value of `ordered`?
3. What error stops `ordered` execution, and do prior writes roll back?
4. Does `unordered` guarantee parallel execution?
5. Why does matching 0 documents not halt `ordered` execution?
6. How do `matchedCount` and `modifiedCount` differ?
7. Why can a single `updateMany` increment `matchedCount` by many?
8. Which counter tracks upserted documents?
9. How does `writeErrors[].index` help batch error handling?
10. What do error codes `11000` and `121` typically mean?
11. How does a write concern error differ from a write error?
12. Why can a network error leave state indeterminate?
13. When is `unordered` inappropriate?
14. Is a standard bulk atomic across the entire batch?
15. Why can retrying `$inc` corrupt data?
16. Does a duplicate key error prove the existing record has the right data?
17. Why can you not count successful operations by summing document counters?
18. What fields belong in a partial-success report?
19. Why does bulk `deleteMany` still require filter validation and backups?
20. If a batch runs inside a transaction, how must commit/abort conditions be evaluated?

## 20. Summary

**`bulkWrite()`** is powerful when writing batches of documents, yet success must be verified at both the operation and business levels:

- **`ordered: true`:** executes sequentially and stops on a write error; completed writes do not roll back automatically.
- **`ordered: false`:** makes no ordering guarantee and can continue independent operations after a write error; it does not turn partial runs into full success.
- **Results:** read `inserted`/`matched`/`modified`/`deleted`/`upserted` counts and ID maps in document units.
- **Errors:** distinguish per-index write errors, write concern errors, and network/command errors; reconcile whenever state is uncertain.
- **Safety:** rely on unique keys, indexes, tight filters, idempotency, checkpoints, and backup/restore plans.

A well-engineered bulk job is not merely fast; it lets you answer precisely **what was written, what failed, and how to resume without duplicating or losing data**.

## Official MongoDB Documentation References

- [MongoDB Manual — db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/)
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Manual — Write Operations Atomicity](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/)
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/)
- [MongoDB Manual — Limits and Thresholds](https://www.mongodb.com/docs/manual/reference/limits/)
- [MongoDB Java Sync Driver — Bulk Operations](https://www.mongodb.com/docs/drivers/java/sync/current/crud/bulk/)
- [MongoDB Manual — db.collection.updateMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateMany/)
- [MongoDB Manual — db.collection.deleteMany()](https://www.mongodb.com/docs/manual/reference/method/db.collection.deleteMany/)
