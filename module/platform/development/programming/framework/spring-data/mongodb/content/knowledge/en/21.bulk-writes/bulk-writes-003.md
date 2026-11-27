# ORDERED, UNORDERED, and Behavior When an Operation Fails

## 1. Problem Statement: Bulk Writing Does Not Mean an Atomic Transaction

An e-commerce system needs to import 5,000 products into MongoDB. Sending individual insert commands inside a loop can incur numerous database round trips and make error aggregation difficult. **Bulk write** lets you group multiple insert, update, replace, or delete operations into a single bulk write request at the driver layer, making the write path easier to manage and optimize.

However, one question must be settled before implementation: **if the third operation fails, do subsequent operations continue?**

MongoDB provides two modes:

- **ORDERED:** operations are processed in their declared order; when a **write error** occurs on an operation, the bulk stops processing the remaining operations in that request.
- **UNORDERED:** operations have no execution-order guarantee; when a write error occurs on one element, MongoDB can still continue processing the remaining independent operations and aggregate errors.

**Neither mode defaults to an “all-or-nothing” transaction.** Operations that succeeded before the bulk failed are generally not rolled back automatically. Each write command on a single document remains atomic at the document level, but the batch as a whole does not automatically gain multi-document atomicity.

This topic covers **ORDERED, UNORDERED, and behavior when an operation fails**, part of the **Bulk Writes** chapter in the **SPRING_DATA_MONGODB** module. In services using Spring Data MongoDB to connect, map documents, and operate through **repositories or MongoTemplate**, understanding bulk writes is also foundational for designing queries, indexes, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

1. Choose ORDERED or UNORDERED appropriately based on inter-operation dependencies.
2. Predict the impact of duplicate keys, schema validation, and common write errors.
3. Call **MongoTemplate.bulkOps(...)** and interpret **BulkWriteResult**.
4. Distinguish operation-level errors, write concern errors, and incidents with unknown outcomes.
5. Avoid misconceptions such as assuming ORDERED rolls back or UNORDERED always completes every operation.
6. Design retries/idempotency, transactions, batch sizes, and reconciliation workflows.
7. Write integration tests proving which documents are actually written when an operation in a bulk fails.

## 2. Sample Dataset: products and Unique SKU

Suppose the **products** collection stores:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  sku: "BOOK-001",
  name: "Spring Data MongoDB",
  stock: NumberInt(10),
  active: true,
  updatedAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

SKU is the business key and must be unique. On the database, we create a **unique index**:

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true, name: "uk_products_sku" }
);
~~~

When a bulk insert attempts to write two documents with the same SKU, MongoDB can return a **duplicate key error (commonly error code 11000)**. This is an easy-to-reproduce example for comparing ORDERED and UNORDERED.

Spring Data entity:

~~~java
package com.example.catalog;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "products")
public record ProductDocument(
    @Id ObjectId id,
    String sku,
    String name,
    int stock,
    boolean active,
    Instant updatedAt
) {}
~~~

Several examples will use an **ObjectId pre-generated in Java** rather than waiting for the database to generate the ID. This makes it easier to reconcile which operations were written after a failed bulk. If your project uses String IDs or another business identifier, use the exact BSON type of your collection.

## 3. How Do the Two Modes Differ in Meaning?

| Criterion | ORDERED | UNORDERED |
| --- | --- | --- |
| Operation order | Follows declared order | No ordering guarantee |
| On write error at one element | Stops subsequent operations in the bulk | Can continue other operations |
| Already-succeeded operations | Do not roll back automatically | Do not roll back automatically |
| Recorded errors | Usually stops at the first error | Can aggregate multiple errors |
| Sequential dependency (before → after) | Better fit, though not a replacement for transactions | Must not rely on order |
| Parallelism / optimization | May limit optimization opportunities | Server/driver may reorder for optimization |
| When to use | Operations where sequence is meaningful | Independent operations, maximizing processed items |

**ORDERED does not mean writes are slow in every case**, and **UNORDERED does not mean MongoDB always runs every operation concurrently**. Execution, command grouping, and optimization also depend on driver version, deployment, operation types, and how MongoDB distributes work.

Do not pick UNORDERED merely because the name sounds “faster”. The first question must be **whether operations depend on one another, and how business logic handles partial success.**

### 3.1. Processing Flow Diagram

~~~mermaid
flowchart TD
    A["Bulk with 4 operations"] --> B{"Mode?"}
    B -->|ORDERED| C["op0 succeeds → op1 fails"]
    C --> D["op2/op3 are not executed"]
    B -->|UNORDERED| E["op1 fails, op0/op2/op3 still attempted"]
    D --> F["Succeeded writes do not roll back automatically"]
    E --> F
    F --> G["Application reconciles results and errors"]
~~~

This diagram illustrates typical **operation-level write errors**. Severe incidents such as connection loss, timeouts, top-level command errors, or transaction failures can behave differently; later sections distinguish them clearly.

## 4. Concrete Example: The Second Element Collides on Key

Suppose `products` already contains a document with SKU **BOOK-001**. We prepare a bulk of three operations:

| Position | Operation | Description |
| --- | --- | --- |
| 0 | Insert BOOK-002 | New, valid SKU |
| 1 | Insert BOOK-001 | Existing SKU → duplicate key |
| 2 | Insert BOOK-003 | New, valid SKU |

### 4.1. Using ORDERED

Execution sequence:

1. Insert BOOK-002 succeeds.
2. Insert BOOK-001 fails due to the unique index.
3. Insert BOOK-003 **is not executed** because the bulk stops at the failing operation.

After the bulk, BOOK-002 still exists. The original BOOK-001 remains unchanged. BOOK-003 has not been added.

**There is no automatic rollback** for BOOK-002. To achieve multi-operation rollback behavior, you must design an appropriate transaction rather than relying on ORDERED alone.

### 4.2. Using UNORDERED

MongoDB can still execute the other independent operations despite BOOK-001 colliding. In a normal bulk insert with healthy connectivity and server state:

- BOOK-002 can be inserted successfully.
- BOOK-001 produces a duplicate key error.
- BOOK-003 can still be inserted successfully.

**Do not interpret this as “insert in order 0 → 1 → 2 and skip errors”**. UNORDERED makes no ordering promise, so if multiple operations contend on the same key or depend on data created by another operation, the concrete outcome can vary.

In both modes, the caller still must recognize that **the bulk had errors** even if some writes succeeded; never treat “some documents were written” as full batch success.

## 5. Calling bulkWrite with mongosh

MongoDB provides `collection.bulkWrite` to run multiple types of write models:

~~~javascript
db.products.bulkWrite(
  [
    {
      insertOne: {
        document: {
          sku: "BOOK-002",
          name: "MongoDB Basics",
          stock: 3,
          active: true
        }
      }
    },
    {
      insertOne: {
        document: {
          sku: "BOOK-001",
          name: "Duplicate SKU",
          stock: 1,
          active: true
        }
      }
    },
    {
      insertOne: {
        document: {
          sku: "BOOK-003",
          name: "Optimizing MongoDB",
          stock: 5,
          active: true
        }
      }
    }
  ],
  { ordered: true }
);
~~~

Replace **ordered: true** with **ordered: false** to request UNORDERED mode. Before running the two experiments, clean up or use distinct SKUs for each run; otherwise, leftover state from the first run will cause unrelated duplicate errors.

### 5.1. Bulk Can Mix Operation Types

~~~javascript
db.products.bulkWrite(
  [
    {
      updateOne: {
        filter: { sku: "BOOK-002" },
        update: { $inc: { stock: 2 } }
      }
    },
    {
      insertOne: {
        document: {
          sku: "PEN-009",
          name: "Pen",
          stock: 10,
          active: true
        }
      }
    },
    {
      deleteOne: {
        filter: { sku: "BOOK-OLD" }
      }
    }
  ],
  { ordered: false }
);
~~~

In this example, all three operations have independent targets, so UNORDERED can be suitable. Conversely, if `updateOne` targets the exact document created by `insertOne` in the same batch, never use UNORDERED while assuming the insert is guaranteed to run before the update.

### 5.2. Bulk Write Is Not Bulk Read

`bulkWrite` consists only of write operations. It does not offer a “find, compute in Java, then write” chain mid-command. When modifying data based on current state, use conditional update operators, update pipelines, or split the workflow per business requirements.

## 6. Spring Data MongoDB: MongoTemplate.bulkOps

In Spring Data MongoDB, the commonly used API is:

~~~java
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.MongoTemplate;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.ORDERED,
    ProductDocument.class
);
~~~

**BulkMode.ORDERED** and **BulkMode.UNORDERED** correspond to MongoDB's bulk write options. `ProductDocument` supplies field mapping metadata and the collection name from `@Document`.

Example using **insert**:

~~~java
import java.time.Instant;
import java.util.List;
import org.bson.types.ObjectId;
import com.mongodb.bulk.BulkWriteResult;

List<ProductDocument> products = List.of(
    new ProductDocument(
        new ObjectId(), "BOOK-101", "Book A",
        5, true, Instant.now()
    ),
    new ProductDocument(
        new ObjectId(), "BOOK-102", "Book B",
        9, true, Instant.now()
    )
);

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.ORDERED, ProductDocument.class
);

bulk.insert(products);
BulkWriteResult result = bulk.execute();
~~~

**bulk.insert(...)** registers the operations to perform. **bulk.execute()** actually executes the batch in the synchronous API. A `BulkOperations` instance is typically built for **one-time execution**; do not arbitrarily reuse it across batches or share it across requests.

### 6.1. Should You Call repository.saveAll Instead of bulkOps?

Do not equate the two APIs. **saveAll** is a repository contract with entity-saving semantics; **bulkOps** gives explicit choice over ordered/unordered and combines insert, update, and delete commands in one batch.

Some repository optimizations depend on new/existing entity state and Spring Data version. If you need specific behavior on operation errors, per-operation tracking, and ordered/unordered selection, **using the explicit bulk API** is easier to control than guessing how `saveAll` is implemented.

### 6.2. Adding Update and Delete

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED, ProductDocument.class
);

bulk.updateOne(
    Query.query(Criteria.where("sku").is("BOOK-101")),
    new Update().inc("stock", 2)
);

bulk.updateMulti(
    Query.query(Criteria.where("active").is(false)),
    new Update().set("stock", 0)
);

bulk.remove(
    Query.query(Criteria.where("sku").is("BOOK-OLD"))
);

BulkWriteResult result = bulk.execute();
~~~

**updateOne** targets a single document matching the query, **updateMulti** can modify multiple documents, and **remove** deletes matching documents. For interdependent operations, switch to ORDERED or redesign the workflow; never assume UNORDERED preserves registration order.

### 6.3. BulkOperations Does Not Have Full save Semantics

**BulkOperations does not support @Version-based optimistic locking in the same way repository.save does**: do not assume the framework automatically checks each entity's version, updates the version on Java objects, or throws stale-write exceptions like `save`. Logic relying on entity callbacks/auditing must also be verified against the bulk API's actual capabilities rather than assuming parity with single-entity saves.

If a bulk update requires a version check, put **expectedVersion into the Query filter** and explicitly design the version increment and result check. For modified timestamps, decide explicitly which operations set `updatedAt` rather than assuming every bulk write triggers all callbacks like `repository.save`.

## 7. ORDERED: What Is Guaranteed and What Is Not

Suppose a bulk contains operations A, B, C, and D, and B causes a **write error**.

In a normal ORDERED batch:

- A is attempted before B and may succeed.
- B fails.
- C and D are not executed after error B within that bulk.
- A is not rolled back just because B failed.

### 7.1. ORDERED Is Useful When Results Depend on Order

Consider a sequence on the same Product:

1. Change status to ARCHIVED.
2. Update fields compatible with ARCHIVED.

With UNORDERED, the second operation may not assume status was already updated. With ORDERED, order is preserved when no prior operation fails.

Still, two separate operations can be observed mid-way by concurrent requests and do not create batch-wide atomicity. When both modify the same document, it is usually better to combine them into **one conditional update** whenever possible.

### 7.2. ORDERED Is Not Equivalent to a Transaction

| Property | ORDERED Outside Transaction | Multi-Document Transaction |
| --- | --- | --- |
| Request ordering | Yes | Follows command sequence executed by the application |
| Error on the third command | Earlier commands may remain written | Writes inside the transaction can be rolled back if aborted |
| Atomic commit for entire batch? | No | Yes, when transactions are properly configured/supported |
| Automatic business-rule checks? | No | No |
| Operational cost and prerequisites | Standard bulk cost | Deployment prerequisites and transaction overhead |

**Do not open a transaction just to get ORDERED semantics.** Choose transactions only when business invariants genuinely require a group of multi-document writes to commit or roll back together.

## 8. UNORDERED: Processes More Operations, Without Order

UNORDERED lets the driver/server organize operations more flexibly, which can improve efficiency especially in certain sharded environments. Commands have no ordering constraint during execution.

Consider a batch containing:

- Insert SKU A.
- Insert SKU B which already exists and triggers duplicate key.
- Insert SKU C.
- Update stock of an independent SKU D.

A write error on B **does not have to block** the remaining operations. The application still needs to inspect which operations succeeded and which reported errors.

### 8.1. Never Create Logical Dependencies Inside UNORDERED

Dangerous example:

~~~javascript
db.products.bulkWrite(
  [
    {
      insertOne: {
        document: {
          sku: "NEW-001",
          name: "New Product",
          stock: 1
        }
      }
    },
    {
      updateOne: {
        filter: { sku: "NEW-001" },
        update: { $inc: { stock: 1 } }
      }
    }
  ],
  { ordered: false }
);
~~~

If `updateOne` executes before `insertOne`, it may yield **matchedCount=0**, leaving final stock at 1. If insert executes before update, stock may become 2. Never build business rules around accidental outcomes observed in a test environment.

Better approaches are inserting the product with its final stock value, running a proper conditional upsert/update, or splitting into two verified sequential phases.

### 8.2. UNORDERED Does Not Mean “Every Operation Definitely Runs”

For normal write errors, the server can continue independent operations. However, failures such as:

- Inability to send the request due to network issues.
- Authentication/authorization errors or high-level command errors.
- Server disconnecting mid-flight.
- Write concern not satisfied.
- Transaction aborted.

can leave the caller **with no proof that every operation was attempted or committed**. Some cases even result in unknown write outcomes. Therefore, “unordered continues after errors” applies to **operation-level write errors in a bulk**, not a completion guarantee across all operational failures.

## 9. BulkWriteResult: What Do the Numbers Tell You?

When a batch completes without throwing an exception and write concern is acknowledged, **BulkOperations.execute()** returns a **BulkWriteResult** from the MongoDB Java Driver.

~~~java
import com.mongodb.bulk.BulkWriteResult;

BulkWriteResult result = bulk.execute();

boolean acknowledged = result.wasAcknowledged();
int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserts = result.getUpserts().size();
~~~

Common metrics:

| Metric | Meaning |
| --- | --- |
| wasAcknowledged | Whether the server acknowledged according to the applied write concern |
| insertedCount | Number of documents inserted in the bulk |
| matchedCount | Number of documents matched by reported update operations |
| modifiedCount | Number of documents whose data actually changed |
| deletedCount | Number of documents deleted |
| upserts | Upsert operations that created new documents, with index/ID details when returned |

**matchedCount does not equal modifiedCount.** An update may match a Product while setting stock to its already-present value, resulting in zero actual modification.

### 9.1. Do Not Deduce Per-Element Results from Total Counts

If `insertedCount=7` in a batch of 10 inserts, you **cannot tell which exact three items were not inserted** from the count alone. You must combine:

1. An input operation list with clear identifiers.
2. Write errors with their indices when provided.
3. Actual post-error database state, especially for unknown outcomes.

With Spring Data `BulkOperations`, do not expect individual `ProductDocument` instances returned with populated IDs as in `repository.save`. If you need to correlate results with inputs, **generate IDs or operation keys before sending the bulk** and reconcile using those keys.

### 9.2. Read Counts Only When Acknowledged

If the system uses an unacknowledged write concern, do not assume detailed counts are always available or that the server confirmed results. `BulkResult` and the driver restrict reading metrics for unacknowledged writes; for data imports requiring reconciliation, prefer acknowledged writes.

## 10. When an Error Occurs, execute() Can Throw an Exception

A unique index violation typically causes the bulk to **throw an exception** rather than returning a normal `BulkWriteResult` with a “success=false” field.

Example:

~~~java
import org.springframework.dao.DataAccessException;

try {
    BulkWriteResult result = bulk.execute();
    // Reached only if the bulk completes according to the API's reported result.
    recordSuccess(result);
} catch (DataAccessException ex) {
    // Some write operations may have already succeeded.
    recordFailure(ex);
    throw ex;
}
~~~

`recordSuccess` and `recordFailure` are hypothetical business methods. Spring Data may **translate MongoDB driver exceptions into the DataAccessException hierarchy**. The exact exception class and attached details depend on the error type and Spring Data/driver version.

**Do not catch an exception and assume the whole batch failed cleanly.** You must distinguish which operations definitely wrote, which definitely failed, and which have unknown outcomes.

### 10.1. Errors from the Java Driver

At the MongoDB Java Driver layer, bulk errors can be represented by **MongoBulkWriteException**, providing a list of **BulkWriteError** objects and partial write result info:

~~~java
import com.mongodb.MongoBulkWriteException;
import com.mongodb.bulk.BulkWriteError;

try {
    collection.bulkWrite(models, options);
} catch (MongoBulkWriteException ex) {
    for (BulkWriteError error : ex.getWriteErrors()) {
        int index = error.getIndex();
        int code = error.getCode();
        String message = error.getMessage();
        // Map the index back to the submitted list of write models.
    }
}
~~~

This snippet assumes **collection**, **models**, and **options** are pre-initialized MongoDB Java Driver objects. It demonstrates error inspection at the driver layer; in Spring Data, the translated exception may not directly be `MongoBulkWriteException`. Never cast exceptions blindly.

### 10.2. What Does the Error Index Mean?

In a `bulkWrite` call taking a list of write models, the write error index typically points to **the operation's position in the submitted list per the driver contract**. For example, `error.index=1` corresponds to the second operation.

When using abstractions that group, sort, split batches, or mix command types, **verify index-to-request mapping in your running driver version** instead of assuming an application-imagined order. Always keep an **operation ID → input record** lookup table so error recording remains meaningful to the business.

## 11. Three Error Categories to Distinguish

Not every bulk failure is a duplicate key on a single element.

| Category | Example | What Can Be Known |
| --- | --- | --- |
| **Operation-level write error** | Duplicate key, validation failure, invalid update | May provide index, code, and message for failing operations |
| **Write concern error** | Failed to reach configured replica acknowledgement within timeout | Data may already be written on primary; durability/acknowledgement target not met |
| **General command/connection error** | Network drop, auth failure, server unable to process request | May not know completely which operations executed |

### 11.1. Duplicate Key

Example E11000 when inserting two documents with the same **sku** on a unique index:

~~~text
E11000 duplicate key error collection: catalog.products
index: uk_products_sku dup key: { sku: "BOOK-001" }
~~~

This message is illustrative, not a fixed log format. In Java, error code **11000** is commonly used to identify duplicate keys; you still need to inspect which unique field collided to decide business handling.

### 11.2. Document Validation

If a collection requires non-negative stock via schema validation, an insert with `stock=-3` can fail even if both `_id` and `sku` are new.

~~~javascript
db.createCollection("validated_products", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["sku", "stock"],
      properties: {
        sku: { bsonType: "string" },
        stock: { bsonType: "int", minimum: 0 }
      }
    }
  }
});
~~~

Bulk writes to this collection must obey the validator. With UNORDERED, one document's validation error does not necessarily stop valid documents from being written. With ORDERED, a write error can stop subsequent operations.

### 11.3. Write Concern Timeout

If the write concern requires confirmation from multiple replicas and does not receive enough confirmations before the deadline, the server can return a **write concern error**. That does not mean the primary never applied the operations. **Do not blindly retry the whole batch** when writes may already be persisted.

These cases require reconciling database state via business identifiers or operation keys before deciding to resend.

## 12. Related Operations on the Same Key: A Huge Difference

Consider two update commands targeting the same Product:

~~~javascript
db.products.bulkWrite(
  [
    {
      updateOne: {
        filter: { sku: "BOOK-001" },
        update: { $set: { stock: 10 } }
      }
    },
    {
      updateOne: {
        filter: { sku: "BOOK-001" },
        update: { $inc: { stock: 2 } }
      }
    }
  ],
  { ordered: false }
);
~~~

The resulting stock depends on execution order:

- If **$set 10** then **$inc 2**, stock = 12.
- If **$inc 2** then **$set 10**, stock = 10.

**UNORDERED is unsuitable** if business logic requires a deterministic result from an order-dependent sequence.

For the same document, you can combine operations into **one update** matching the desired semantics—for example, setting `stock=12` directly when the final value comes from a source of truth, or using an update pipeline computing from current state if needed.

### 12.1. Does ORDERED Completely Solve Concurrency?

No. ORDERED preserves order **within that batch**, yet another request can still modify the Product between operations unless additional coordination exists. For conditional updates, include version/status predicates in the filter or use a transaction if multiple documents must be protected together.

### 12.2. Upserts in UNORDERED

Two upserts targeting the same non-existent key can race. The outcome depends on filters, unique indexes, ordering, and server execution. When a business key must be unique, always rely on a **unique index created in MongoDB**, never solely on application-level `exists` checks.

In some scenarios, competing upserts can produce duplicate key errors. The application must handle the error and re-read the document to determine whether the intent was already satisfied.

## 13. Choosing ORDERED vs. UNORDERED by Business Need

### 13.1. Choose ORDERED When

- Order among operations within the same batch is semantically meaningful.
- You want to stop immediately when invalid input is rejected by the server.
- You want an easy **stopping point** to fix bad data and resume in sequence.
- Operations have partial dependencies that cannot yet be reorganized into independent groups.

You must still accept that operations before the error may have been written; if partial commits are unacceptable, reconsider transactions or another design.

### 13.2. Choose UNORDERED When

- Each operation can succeed or fail independently.
- The system wants to process as many valid records as possible even if some fail.
- You already have input identifiers and per-record reconciliation/retry mechanisms.
- There are no before–after dependencies among operations in the same batch.

Good fit example: importing a list of new products where each has its own ID/SKU and one product's error should not block the rest.

### 13.3. Quick Decision Table

| Scenario | Preferred Mode to Consider | Notes |
| --- | --- | --- |
| Import many independent products | UNORDERED | Collect per-product errors, unique index, idempotency |
| Sequential migration where later steps depend on earlier ones | ORDERED or split into phases | Order alone does not create rollback |
| Two operations on the same document needing deterministic output | Single atomic update, or ORDERED | Avoid splitting into two commands if mergeable |
| Modifying multiple aggregates that must succeed together | Transaction / business protocol | Mode alone does not provide atomicity |
| Large batch with bad input rows | Usually UNORDERED if rows are independent | Report partial success and retry failing rows |
| Need to stop on first error to inspect | ORDERED | Writes before the error still persist |

## 14. Failed Batches Do Not Auto-Rollback: When Do Transactions Help?

MongoDB supports multi-document transactions on compatible deployments. Spring Data can use **MongoTransactionManager** to bind a group of writes to a transaction:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {

    @Bean
    MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory factory) {
        return new MongoTransactionManager(factory);
    }
}
~~~

Example of a Spring-managed service:

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public BulkWriteResult importAtomicBatch(
        List<ProductDocument> products) {
    BulkOperations bulk = mongoTemplate.bulkOps(
        BulkMode.ORDERED, ProductDocument.class
    );
    bulk.insert(products);
    return bulk.execute();
}
~~~

This example only achieves multi-document atomicity when:

1. The MongoDB deployment supports transactions and the driver is properly configured.
2. `MongoTransactionManager` is active for the participating operations.
3. The `@Transactional` method is actually invoked through the Spring proxy/transaction interceptor.
4. Rollback-triggering exceptions propagate out according to the transaction policy.

### 14.1. Bulk Errors Inside a Transaction

If a write error occurs inside a transaction, do not naively assume **UNORDERED will keep going and commit partial successes**. A write error can abort the transaction, making subsequent operations invalid inside that transaction. The application must handle the error, roll back, and retry **the entire business unit** when appropriate.

Never catch a bulk error inside a transaction and try to commit the succeeded subset thinking MongoDB will ignore the error. Transaction semantics follow strict rules.

### 14.2. When Are Transactions Unnecessary?

If each imported product is an independent entity and valid rows should be accepted, wrapping an entire 5,000-row batch in a transaction may be unnecessary—and can even raise overhead and let a single bad row fail the whole batch. Using UNORDERED without a transaction plus partial-success reporting can be a better fit.

**Choose transactions based on business invariants**, not because “a bulk has many commands” or because users want error reporting.

## 15. Retries and Idempotency: The Hardest Part After Partial Failure

Suppose a client sends a bulk of 100 operations, but the connection drops after the server has written 60 of them. The client receives no complete response. If it resends the whole batch, what happens?

- Inserts with the same `_id` may hit duplicate key errors.
- **`$inc`** updates may be applied a second time, corrupting stock counts.
- Already-executed deletes may find no document left to delete.
- Upserts may alter data depending on filters and update operators.

Therefore, **never blindly retry an entire bulk** when the outcome is unknown.

### 15.1. Classifying Operations by Replay Safety

| Operation | Safe to Repeat? | Conditions |
| --- | --- | --- |
| `$set` a field to the same value | Usually idempotent on field value | No concurrent writer overwritten; timestamps/versions considered separately |
| `$inc` stock by 1 | **Not idempotent** | Repeating twice can add 2 |
| Insert with same `_id` | Second run typically hits duplicate key | Must reconcile document/payload to confirm “already completed” |
| Delete by `_id` | Usually reaches the same “absent” state | External side effects or audit/events outside DB need separate handling |
| `$push` an item | Not idempotent | May append duplicates on retry |
| `$addToSet` an identical value | Deduplicates by exact value | Does not deduplicate by business key inside objects |
| Upsert with `$setOnInsert` + unique key | Can build reasonable idempotency | Requires proper keys and update rules |

### 15.2. Using Operation IDs

In an import system, each row can carry:

- **batchId**: ID of the import run.
- **rowId** or **sourceId**: stable identifier of the row from the source.
- **targetId**: target document ID, pre-generated or normalized.
- **payloadHash**: digest verifying the processed content.

A progress-tracking collection or a unique key on target data helps distinguish **already written**, **not yet written**, and **conflicting data**. If retries span multiple processes, deduplication must itself be atomic; merely logging `batchId` to a file will not prevent two workers from writing concurrently.

### 15.3. Duplicate Errors Do Not Always Mean “Already Succeeded”

When retrying an insert with the same `_id`, a duplicate key error can mean two different things:

1. The previous attempt already wrote **the exact expected payload**.
2. A different document or a different data version already occupies that key.

You must **read and compare** the ID, business key, and relevant content before treating a duplicate error as idempotent success. Ignoring all duplicate keys blindly can mask real data conflicts.

## 16. Upsert and Replace: Pay Attention to Each Operation's Semantics

`BulkOperations` supports common update styles:

~~~java
BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED, ProductDocument.class
);

bulk.upsert(
    Query.query(Criteria.where("sku").is("BOOK-401")),
    new Update()
        .set("name", "Deep Dive into MongoDB")
        .setOnInsert("stock", 0)
        .setOnInsert("active", true)
);

BulkWriteResult result = bulk.execute();
~~~

In this example:

- If a Product with SKU BOOK-401 is found, the specified fields are updated per MongoDB semantics.
- If not found, upsert can create a new document from the filter and update operators.
- **$setOnInsert** applies only on new inserts, making it well suited for default initialization.

**Do not confuse upsert with insert.** Upsert can overwrite existing data; if an import feed is not allowed to overwrite `name`, you must design a different filter/update.

### 16.1. ReplaceOne Can Erase Existing Fields

`replaceOne` replaces the document with a new document according to replacement semantics (respecting `_id` rules). If the replacement omits a previously existing field, that field can disappear.

During schema migrations or imports from sources providing only a few columns, **field-level `$set` updates** are generally safer than full-document replacement. Conversely, replacement can be appropriate when the new source owns the complete state and must replace it wholesale.

### 16.2. Matched and Modified Are Different

An `updateOne` whose filter matches yet writes the exact same value increments **matchedCount** without incrementing **modifiedCount**. An `updateOne` that matches nothing without upsert is not a write error either: it can complete cleanly with `matched=0`.

**Do not use ORDERED expecting it to “stop when matchedCount=0”** as if that were an exception. If business rules require every update to match, inspect per-operation outcomes or design an explicit error/protocol check rather than inferring from bulk totals.

## 17. Unique Indexes, Validation, and Pre-Write Checks

Bulk writes do not replace database-level data protection.

### 17.1. Unique Indexes Protect Against Concurrency

~~~javascript
db.products.createIndex(
  { sku: 1 },
  { unique: true }
);
~~~

If the application does:

1. `findOne` to check that SKU does not exist;
2. `insert` inside a bulk;

another writer can still insert the same SKU between those two steps. A **unique index** is the final constraint guaranteeing uniqueness under concurrency.

### 17.2. Pre-Batch Validation Remains Very Valuable

Validate data in the application layer before adding it to a bulk:

- SKU is non-empty and properly formatted.
- Stock is non-negative if required by business rules.
- Price/currency units match expected types and bounds.
- No duplicate SKUs within the import file itself, if disallowed.
- Every row has a `sourceId` for reconciliation.
- No writes target unauthorized tenants or collections.

Application validation catches errors early and produces clear messages. **MongoDB validators and unique indexes** protect invariants when concurrent writers or application bugs strike.

### 17.3. Why Does UNORDERED Still Need Detailed Error Reporting?

If 498 out of 500 rows succeed while 2 fail, the response must not simply return “success”. It should report:

~~~json
{
  "batchId": "import-2025-06-01",
  "status": "PARTIAL",
  "submitted": 500,
  "confirmedSucceeded": 498,
  "confirmedFailed": 2,
  "unknown": 0
}
~~~

This JSON illustrates **an application-defined API contract**. Counts should only be published once the application holds corresponding evidence; never compute `confirmedSucceeded = submitted - errors` during connection drops with unknown outcomes.

## 18. Splitting Large Batches and Operational Orchestration

The driver enforces limits on command size, operations per batch, and BSON size. It can **split a large bulk request into chunks fitting server limits**. Applications also routinely split files of hundreds of thousands of rows into small chunks to track progress.

Example:

~~~text
Source 25,000 products
    |
    +-- Chunk 1: rows 1..500
    +-- Chunk 2: rows 501..1000
    +-- ...
    +-- Chunk 50: rows 24501..25000
~~~

### 18.1. Why Not Accumulate Unboundedly in One Bulk?

- Hard to track progress or resume after errors.
- Input data consumes large amounts of memory.
- A network failure makes the state of a huge batch hard to determine.
- Per-row error aggregation and retries become complicated.
- Write concern, index maintenance, and server capacity impose practical ceilings.

There is no single **optimal batch size for every system**. The number 500 above is illustrative; measure against document size, operation type, network, deployment, and contention level.

### 18.2. Keeping Source Row Mapping

An import record can be modeled as:

~~~java
public record ImportRow(
    String sourceId,
    String sku,
    String name,
    int stock
) {}
~~~

When translating into write models or `BulkOperations`, keep metadata in **registration order**. When an error occurs and the driver supplies an index, map that index back to `sourceId`. With chunks, store both **`chunkId` + `localIndex`** so index 3 of one chunk is never confused with index 3 of another.

### 18.3. A Single execute() Can Partially Write Multiple Internal Chunks

If the driver splits a batch, an error/timeout can occur after several internal chunks have already been written. **Do not rely on a single boolean `success` variable** to represent all 25,000 records. Persist checkpoints and reconcile by document ID or `sourceId`.

## 19. WriteConcern and Response Certainty

MongoDB uses **write concern** to describe the expected level of write acknowledgement. Examples:

- **Acknowledged**: caller receives confirmation per the chosen write concern.
- **Majority**: requires confirmation from a replica majority appropriate to the deployment.
- **Unacknowledged**: does not receive detailed result acknowledgements in the usual way.

Distinguishing between a **single-document write error** and **failing to meet write concern** is crucial.

### 19.1. Acknowledged Does Not Mean Subsequent Failures Cannot Occur

An operation acknowledged at the configured level does not automatically mean every business requirement succeeded. For example, if one record in a batch writes while others fail, the caller must still handle the failures. If durability across failovers is required, both write concern and operational environment must match.

### 19.2. WriteConcernError and Possible Persistence

When the server fails to satisfy the write concern within the allotted time, some writes may still have been applied. Never blindly re-invoke **`$inc`** or **`$push`**. Investigate database state or use idempotency mechanisms before retrying.

### 19.3. Do Not Rely on Unacknowledged Writes for Accurate Reporting

If a workflow must report how many rows inserted, how many failed, and which remain unknown, use a write concern that provides acknowledgement and error details. You cannot build reliable reconciliation merely from pushing bytes onto a socket.

## 20. Reactive Bulk Write: Same Semantics, Different Execution Model

Reactive Spring Data MongoDB exposes a corresponding bulk API via **ReactiveMongoTemplate**:

~~~java
import java.util.List;
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.ReactiveBulkOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import reactor.core.publisher.Mono;

public Mono<BulkWriteResult> insertBulkReactive(
        ReactiveMongoTemplate template,
        List<ProductDocument> products) {

    ReactiveBulkOperations bulk = template.bulkOps(
        BulkMode.UNORDERED,
        ProductDocument.class
    );
    bulk.insert(products);
    return bulk.execute();
}
~~~

**Mono<BulkWriteResult>** represents the write result once subscribed. `ORDERED`/`UNORDERED` keep the exact same meanings for ordering, write errors, and partial success. Reactive execution does not turn a bulk into a transaction.

### 20.1. Do Not Call block() in WebFlux

Avoid:

~~~java
BulkWriteResult result =
    insertBulkReactive(template, products).block();
~~~

In reactive services/controllers, return the `Mono` or compose it with `map`/`flatMap`. To produce an HTTP response, map success/partial/failure states upon receiving signals from the publisher.

### 20.2. Avoid Subscribing Multiple Times to a Write Publisher

If the same `Mono` is subscribed to twice, the write code may execute twice. In particular:

- Two **`$inc`** runs can increment twice.
- Two **`$push`** runs can append duplicates.
- Two inserts can trigger duplicate key errors.

Do not call `subscribe()` yourself to “pre-trigger” work and then return the `Mono` for WebFlux to subscribe again. Let the framework manage subscription, and design idempotency if callers can retry.

### 20.3. Reactive Transactions

If multi-document atomicity is needed in a reactive stack, configure **ReactiveMongoTransactionManager** and manage transaction context through reactive mechanisms. Do not expect imperative `MongoTransactionManager` to apply automatically to reactive publishers.

Transactions also do not turn unordered write errors into safe partial successes to commit; handle rollback and retries at the business boundary.

## 21. Integration Testing ORDERED and UNORDERED

Because the key difference lies in **which writes persist before/after an error**, test against real MongoDB in a test environment. Mocking `BulkOperations` does not prove the server stops at the exact position.

In the examples below, we use **duplicate `_id`** instead of SKU to provoke duplicate keys. Standard MongoDB collections have a default unique index on `_id`, avoiding dependency on SKU index creation in the test fixture.

### 21.1. Testing That ORDERED Stops After Error

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.BulkOperations.BulkMode;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class BulkModeTest {
    @Autowired MongoTemplate template;

    private ProductDocument product(ObjectId id, String sku) {
        return new ProductDocument(
            id, sku, "Test " + sku, 1, true, Instant.now()
        );
    }

    @Test
    void orderedStopsAfterDuplicateId() {
        String suffix = UUID.randomUUID().toString();

        ProductDocument existing = product(
            new ObjectId(), "EXIST-" + suffix
        );
        ProductDocument first = product(
            new ObjectId(), "FIRST-" + suffix
        );
        ProductDocument duplicateId = product(
            existing.id(), "DUP-" + suffix
        );
        ProductDocument last = product(
            new ObjectId(), "LAST-" + suffix
        );

        template.insert(existing);
        try {
            BulkOperations bulk = template.bulkOps(
                BulkMode.ORDERED, ProductDocument.class
            );
            bulk.insert(List.of(first, duplicateId, last));

            assertThatThrownBy(bulk::execute)
                .isInstanceOf(RuntimeException.class);

            assertThat(template.exists(
                Query.query(Criteria.where("_id").is(first.id())),
                ProductDocument.class
            )).isTrue();

            assertThat(template.exists(
                Query.query(Criteria.where("_id").is(last.id())),
                ProductDocument.class
            )).isFalse();
        } finally {
            for (ObjectId id : List.of(
                    existing.id(), first.id(), last.id())) {
                template.remove(
                    Query.query(Criteria.where("_id").is(id)),
                    ProductDocument.class
                );
            }
        }
    }
}
~~~

This test proves **FIRST was written**, the duplicate-`_id` operation threw an error, and **LAST was not written** under ORDERED. It also demonstrates that a failed bulk **does not roll back FIRST**.

The test intentionally uses **RuntimeException** as a general exception type because the goal is verifying post-error database state; in real systems, assert the specific translated exception and error code 11000 for your Spring Data/driver stack.

### 21.2. Testing That UNORDERED Attempts Independent Items

Add the following method **to the same `BulkModeTest` class** from the previous example to reuse `template` and `product(...)`:

~~~java
@Test
void unorderedStillWritesIndependentItems() {
    String suffix = UUID.randomUUID().toString();

    ProductDocument existing = product(
        new ObjectId(), "EXIST-U-" + suffix
    );
    ProductDocument first = product(
        new ObjectId(), "FIRST-U-" + suffix
    );
    ProductDocument duplicateId = product(
        existing.id(), "DUP-U-" + suffix
    );
    ProductDocument last = product(
        new ObjectId(), "LAST-U-" + suffix
    );

    template.insert(existing);
    try {
        BulkOperations bulk = template.bulkOps(
            BulkMode.UNORDERED, ProductDocument.class
        );
        bulk.insert(List.of(first, duplicateId, last));

        assertThatThrownBy(bulk::execute)
            .isInstanceOf(RuntimeException.class);

        assertThat(template.exists(
            Query.query(Criteria.where("_id").is(first.id())),
            ProductDocument.class
        )).isTrue();

        assertThat(template.exists(
            Query.query(Criteria.where("_id").is(last.id())),
            ProductDocument.class
        )).isTrue();
    } finally {
        for (ObjectId id : List.of(
                existing.id(), first.id(), last.id())) {
            template.remove(
                Query.query(Criteria.where("_id").is(id)),
                ProductDocument.class
            );
        }
    }
}
~~~

This is a **test under normal test MongoDB conditions**, where independent inserts encounter no other errors. It proves UNORDERED does not stop on `duplicateId`'s write error like ORDERED does. Do not generalize this test to conclude that network failures, write concern errors, or transactions also allow remaining operations to complete.

### 21.3. Isolating Fixture Data and Maintaining Order

Tests should:

1. Use unique IDs/SKUs to avoid interfering with other tests.
2. Seed the colliding document **before creating the bulk**.
3. Use **a single simple operation type** when verifying stopping points, avoiding unrelated dependencies.
4. Inspect **post-error database state** rather than only asserting exceptions.
5. Clean up test data in `finally`, and only on a test database.
6. Add tests for `updateOne`, `updateMulti`, `upsert`, and `delete` with matched/modified counters.
7. For transaction tests, use a transaction-capable deployment and verify rollback explicitly.

### 21.4. Testing Unknown Errors

Safe retries cannot be concluded from duplicate-key tests alone. Include chaos/fault-injection integration tests at an appropriate layer: dropping connections, timeouts, node restarts, or simulating write concern errors. Run these tests in controlled environments—**never in production**.

## 22. Performance and Operational Diagnostics

### 22.1. Metrics to Measure

| Metric | Meaning |
| --- | --- |
| Total registered operations | Logical batch size |
| Acknowledged operations count | Confirmed write volume |
| Write error count | Operations rejected by the server |
| Execute duration | Batch latency |
| Batch size and BSON size | Memory and network usage |
| Duplicate key rate | Import data quality or retry issues |
| Write concern errors | Confirmation/replication issues |
| Unknown outcome count | Reconciliation burden from timeouts/disconnects |
| Retry count | Extra load generated by retry policy |

Never measure performance solely by **records/second**. An UNORDERED workflow with high throughput that ignores errors or creates duplicates on retry can incur huge data-repair costs.

### 22.2. Indexes Still Matter for Bulk Updates

Example of a bulk `updateOne` by `sku`:

~~~javascript
db.products.createIndex({ sku: 1 }, { unique: true });

db.products.find({ sku: "BOOK-001" })
  .explain("executionStats");
~~~

Indexes speed up locating target documents. **`explain` on `find`** illustrates the corresponding lookup plan, though it does not capture the full execution cost of a bulk write. To measure bulk updates, also observe write duration, lock contention, index maintenance, and document size.

### 22.3. Ordered vs. Unordered: Benchmark the Right Workload

A reliable benchmark should:

- Use identical batch sizes and document sizes.
- Have the same indexes and comparable initial data.
- Separate independent batch inserts from updates contending on the same keys.
- Measure errors and partial successes separately.
- Control write concern.
- Run on a deployment similar to the target environment.

A “UNORDERED was 30% faster than ORDERED” finding on one fixture cannot be generalized to all workloads. On small batches or paths bottlenecked elsewhere, the difference may be negligible.

## 23. Common Conceptual and Technical Pitfalls

| Symptom / Assumption | What Is Wrong? | How to Handle It |
| --- | --- | --- |
| “ORDERED means rolling back the whole batch” | ORDERED only governs ordering/stopping after a write error | Use transactions if multi-document atomicity is needed |
| “UNORDERED ignores all errors” | Caller still receives errors; not every failure lets remaining ops run | Collect errors and handle unknown outcomes |
| “UNORDERED runs in exact input order” | No ordering guarantee | Group only independent operations |
| “BulkWriteResult has per-insert results” | Aggregate counts cannot identify individual records | Store operation IDs/indices and reconcile |
| “execute() throwing means nothing was written” | Partial success may have already happened | Re-read data and log |
| “Retrying the whole batch is always safe” | `$inc`/`$push` are not idempotent | Use deduplication/operation keys and reconciliation |
| “Duplicate key always means already imported” | Payloads might conflict | Compare against existing document |
| “matchedCount=0 is a write error” | Unmatched updates are typically not errors | Check per business rules |
| “@Version works automatically like save” | `BulkOperations` does not guarantee `repository.save` version checks | Manage versioning explicitly |
| “Validating in Java is enough” | Other writers can race | Create unique indexes/validators in MongoDB |
| “Write concern timeout means nothing wrote” | Writes may already have occurred | Reconcile before retrying |
| “Creating a reactive Mono means MongoDB wrote” | Publisher is lazy; requires subscription | Compose pipeline properly |
| “Bulk has no limits” | Driver/server have batch/BSON limits | Chunk and measure sizes |
| “Transaction + UNORDERED lets succeeded parts commit” | Write errors can abort the transaction | Design rollback/retry for the whole transaction |

### 23.1. Procedure for Investigating a Failed Batch

1. Identify **batchId, chunkId, mode**, and the registered operations list.
2. Classify the error: **write error**, **write concern error**, or **unknown outcome**.
3. Check whether the exception contains indices, error codes, messages, and partial results.
4. Inspect target documents by **`_id/sourceId/sku`** on an authorized database.
5. Classify each record: confirmed success, confirmed failure, or unknown.
6. Determine whether each operation is idempotent on retry.
7. Retry only eligible records after reconciliation; never resend an entire batch blindly.
8. Verify unique indexes, schema validators, permissions, and write concern.
9. Add regression tests for that exact error type and mode.

## 24. Practice Exercises

### Exercise 1: ORDERED and Failure on the Third Operation

A bulk insert has five operations: 0, 1 valid; 2 duplicate key; 3, 4 valid. ORDERED mode, no transaction. What happens?

**Answer:** operations 0 and 1 may have been written successfully; operation 2 fails; operations 3 and 4 are not executed after the error. There is no automatic rollback of 0 and 1.

### Exercise 2: Same Data with UNORDERED

If UNORDERED is used for the five independent operations in Exercise 1, can you conclude all succeeded?

**Answer:** no. Operation 2 still fails. The other valid operations may continue and be written under normal conditions; the caller must handle the error and verify outcomes.

### Exercise 3: Spotting Broken Order Expectations

An UNORDERED batch inserts Product X and then calls `updateOne` on Product X to increment stock. Why is the outcome nondeterministic?

**Answer:** the update might run before the insert and match nothing, or after the insert and match. Never use UNORDERED when one operation depends on an earlier one.

### Exercise 4: Picking a Mode for Imports

A file has 2,000 independent Products; business rules want to keep every valid row even if some SKUs collide. Which mode should be considered?

**Answer:** UNORDERED, combined with unique indexes, validation, per-input-row error reporting, and reconciliation/retry.

### Exercise 5: Interpreting Counts

A bulk has 20 `updateOne` operations and reports `matchedCount=12, modifiedCount=9`. How many operations definitely failed?

**Answer:** you cannot tell from these two numbers. An update can match zero documents yet complete validly, and some matched updates may make no value change. You must understand filters, operation types, and actual errors.

### Exercise 6: Write Concern Timeout

A bulk stock update encounters a write concern timeout. Should the client resend all `$inc` operations?

**Answer:** no. Some updates may already have applied; retrying `$inc` can increment twice. Reconcile and apply an appropriate idempotency strategy.

### Exercise 7: Transactions

Three bulk operations must succeed or roll back together because they belong to one business action. Is choosing `BulkMode.ORDERED` sufficient?

**Answer:** no. You need a properly configured/supported MongoDB transaction and rollback boundary, or a compensating protocol if transactions cannot be used.

### Exercise 8: Duplicate ID on Retry

A client retries an insert and gets `E11000` on `_id`. Can the record immediately be marked completed?

**Answer:** not necessarily. You must read and compare the existing document against the expected payload and operation ID; the data could be in conflict.

### Exercise 9: Spring Data Code

Write the first few lines to create an UNORDERED bulk for `ProductDocument`, then register an insert.

~~~java
BulkOperations bulk = mongoTemplate.bulkOps(
    BulkMode.UNORDERED, ProductDocument.class
);
bulk.insert(new ProductDocument(
    new ObjectId(), "BOOK-999", "New Book",
    5, true, Instant.now()
));
~~~

The write command executes when **`bulk.execute()`** is called in the synchronous API.

### Exercise 10: Reactive Subscriptions

A `Mono` from `ReactiveBulkOperations.execute()` is subscribed to twice. What is the risk?

**Answer:** the batch may execute twice. Inserts can hit duplicate keys; `$inc`/`$push` can apply updates twice. Avoid duplicate subscriptions and enforce idempotency on retries.

### Exercise 11: Which Operation Can Be Repeated?

Compare retrying `update $set stock=10` vs. `update $inc stock=1`.

**Answer:** `$set` with the same value is usually idempotent for the `stock` field if no other writer intervenes; `$inc` is not idempotent because it can add multiple times. Both still require considering versions, timestamps, side effects, and real concurrency.

### Exercise 12: Split Batches

The driver splits a large batch into multiple parts; connection drops mid-run. Can you rely solely on the last error to deduce which input rows were written?

**Answer:** no. You need checkpoints, `sourceId`/`chunkId` mappings, and ID reconciliation in the database because unknown-outcome operations may exist.

## 25. Production Implementation Checklist

Before running a production bulk write, confirm:

- **Business goal:** is partial success acceptable, or is all-or-nothing required?
- **Mode:** do operations have order dependencies?
- **Validation:** is input validated before registering write models?
- **Database constraints:** do unique indexes/validators protect invariants?
- **Operation ID:** can every row be reconciled after a timeout or error?
- **Write concern:** does the acknowledgement level match durability/reconciliation needs?
- **Error handling:** do you distinguish write errors, write concern errors, and unknown outcomes?
- **Retry:** have you identified which operations are idempotent and how duplicates are prevented?
- **Chunking:** does batch size fit memory, BSON size, and latency targets?
- **Transaction:** if multi-document atomicity is needed, is transaction infrastructure verified?
- **Monitoring:** are success, failure, unknown, duration, and retry-rate metrics captured?
- **Testing:** have you tested ORDERED/UNORDERED with duplicate keys and inspected post-error data?

This checklist is especially important when importing from CSV, message queues, or multi-system syncs. A fast batch that is hard to recover can cause far more damage than smaller chunks with clear observability.

## 26. Summary

1. **ORDERED** preserves declared order and stops subsequent operations when a write operation fails under normal bulk rules.
2. **UNORDERED** provides no ordering guarantee and can continue independent operations after a write error.
3. **Neither mode automatically rolls back the entire bulk** when prior writes have already been applied outside a transaction.
4. **Execute can throw an exception even when part of the data wrote**; inspect write errors and reconcile real state.
5. **BulkWriteResult** holds aggregate counts; it does not provide complete per-input-row outcomes.
6. **Duplicate keys, validation, and write concern** must be classified; disconnects can produce unknown outcomes.
7. **Pick UNORDERED for truly independent operations**, never relying on order across shared keys or before–after dependencies.
8. **Transactions** are a separate mechanism for multi-document atomicity where needed and supported, not a property of ORDERED.
9. **Retries must rest on idempotency and reconciliation**. `$inc`/`$push` can double-write; duplicate keys do not automatically mean success.
10. **Reactive bulk writes keep the same semantics**, while requiring subscription management and no `block()`.
11. **Tune batch size, indexes, write concern, and monitoring** against real workloads.
12. **Test against real MongoDB** to prove which operations remain after a bulk error rather than merely asserting `execute()` throws.

Mastering **ORDERED, UNORDERED, and failure behavior** enables **SPRING_DATA_MONGODB** services to choose the right bulk write strategy, allow or prevent partial success per business needs, recover safely from incidents, and build testable, reconcilable, operable, and scalable write pipelines.
