# Building BulkOperations with insert, update, upsert, replace, and remove

> **Chapter:** Bulk Writes  
> **Module:** `SPRING_DATA_MONGODB`

When a service needs to import several thousand orders, sync statuses from a partner system, or clean up expired records, looping `repository.save(...)` or `MongoTemplate.updateFirst(...)` inside a `for` loop can generate many individual write commands and increase round-trip overhead between the application and MongoDB. Spring Data MongoDB provides **`BulkOperations`** to group a sequence of **insert, update, upsert, replace, and remove** operations and execute them through `MongoTemplate`.

Bulk writes help reduce command-dispatch overhead and organize a write batch cleanly. However, **bulk does not mean “all succeed or nothing changes”**. Error behavior depends on `ORDERED`/`UNORDERED` mode, operation results, unique index constraints, and whether a transaction is used. In particular, `BulkOperations` does not provide the same per-entity handling as a `save` loop: do not assume auditing callbacks or optimistic locking with `@Version` are automatically applied.

This lesson is part of the `SPRING_DATA_MONGODB` module: connecting and mapping documents, querying and writing via repositories or `MongoTemplate`, aggregation, indexing, transactions, reactive access, testing, and performance diagnostics. The focus here is **building and operating a semantically correct bulk write**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Create `BulkOperations` via `MongoTemplate.bulkOps(...)` and choose `BulkMode.ORDERED` or `UNORDERED`.
2. Properly use `insert`, `updateOne`, `updateMulti`, `upsert`, `replaceOne`, and `remove`.
3. Distinguish **partial updates** using `$set` from **document replacement** using replacement.
4. Read `BulkWriteResult`, understand matched/modified/upserted/inserted/deleted counts, and handle **partial success**.
5. Design bulk writes with tenant scoping, unique indexes, idempotency, version control, and appropriate batch sizes.
6. Write integration tests verifying post-write BSON, result counts, duplicate key errors, and data integrity.

## 2. Where Does BulkOperations Fit in Spring Data MongoDB?

Processing flow diagram:

```text
Application Service
       |
       |  register operations:
       |  insert / updateOne / updateMulti / upsert
       |  replaceOne / remove
       v
MongoTemplate.bulkOps(BulkMode, Entity.class)
       |
       |  BulkOperations (accumulates operations, not yet written)
       |
       +-- .insert(...)
       +-- .updateOne(...)
       +-- .updateMulti(...)
       +-- .upsert(...)
       +-- .replaceOne(...)
       +-- .remove(...)
       |
       v
    .execute()
       |
       v
MongoDB Java Driver -> MongoDB Server
       |
       +-- Success: BulkWriteResult
       |
       +-- Failure: exception; partial writes may have
           occurred before or concurrently with the error
```

**Calling `insert/updateOne/upsert/...` on `BulkOperations` only registers an operation**—it is not an immediate write. Commands are sent when **`execute()`** is invoked. This differs from `MongoTemplate.insert(...)` or `repository.save(...)`, which execute immediately.

### 2.1. Core Operations

| BulkOperations API | MongoDB Concept Equivalent | Effect |
| --- | --- | --- |
| `insert(entity)` | Insert document | Adds a new document; fails on unique key collision |
| `insert(list)` | Multiple inserts | Adds multiple documents |
| `updateOne(query, update)` | Update one matching document | Modifies only fields targeted by update operators |
| `updateMulti(query, update)` | Update all matching documents | Updates in bulk within query scope |
| `upsert(query, update)` | Update or insert if unmatched | May create a new document |
| `replaceOne(query, replacement)` | Replace a single document | Writes a new representation; may drop old fields not included |
| `remove(query)` | Delete documents matching query via bulk remove | Deletes data; requires tight filters and checking overload semantics |
| `execute()` | Dispatch bulk write models | Returns summary result or throws an exception |

In the examples, to prevent unintended deletions, `remove` operations will always include a specific `_id` and **`tenantId`**. Even though a remove API can apply to multiple documents, this keeps the target to at most one document at the business-filter level.

### 2.2. When to Use BulkOperations?

Bulk writes are suitable when:

- Importing or syncing many entities into the same collection in one batch.
- Updating multiple documents under independent, validated conditions.
- Running migrations/corrections with checkpoints and result reporting.
- Needing a structured mix of insert, update, upsert, replace, or remove in one task.

You do not necessarily need bulk for a single update command or a business action that requires immediate per-entity results. When callbacks, auditing, or `@Version` protection like `repository.save(...)` are required, re-evaluate using bulk before implementing.

## 3. Choosing ORDERED vs. UNORDERED

Spring Data uses `BulkOperations.BulkMode` with two options.

| Characteristic | `ORDERED` | `UNORDERED` |
| --- | --- | --- |
| Execution order | Preserves logical order of the operation list | Driver/server allowed to reorder/optimize |
| When one operation fails | Stops subsequent operations in the same bulk per ordered rules | May continue executing other operations |
| Best suited for | Later operations depend on earlier ones | Independent operations prioritizing throughput |
| Batch-wide atomicity? | **No**, unless wrapped in a transaction | **No** |
| Prevents two operations from racing on a document? | Ordered within the bulk, though external writers can still contend | Avoid multiple operations modifying the same document if order matters |

### 3.1. Duplicate Key Error Example

Consider an ordered bulk:

```text
1. insert O-200     -> succeeds
2. insert O-101     -> duplicate _id error
3. update O-102     -> not executed after ordered error
```

Without a transaction, **insert O-200 may already be committed** when the exception is thrown. With unordered, operation 3 may still execute. This is why you cannot assume “an exception means nothing was written”.

### 3.2. Choosing a Mode for the Hands-On Example

We choose **`ORDERED`** for the mixed-batch example so the progression is easy to follow. In independent import systems, `UNORDERED` may fit well, provided you avoid order-dependent operations updating the same document or business key.

```java
import org.springframework.data.mongodb.core.BulkOperations;

BulkOperations bulk = mongoTemplate.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    OrderDocument.class
);
```

`mongoTemplate` is an injected `MongoTemplate` bean. Passing `OrderDocument.class` lets Spring Data apply entity mapping metadata, field names, and custom conversions appropriately; it does not turn bulk into a full `save` loop.

## 4. Hands-On Domain Model

We build a partner order synchronization flow:

- Insert a new order.
- Change the status of one order.
- Change the status of multiple orders waiting for retry.
- Create or update an order by its partner key.
- Replace an order's entire data when an approved **replacement snapshot** arrives.
- Delete a test/verified-deletable record.

File `OrderDocument.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String tenantId,
    String externalRef,
    String status,
    long amountMinor,
    Instant updatedAt
) {}
```

In this example, `_id` is a BSON String such as `"ORD-101"`, not a 24-character hex ObjectId string. `tenantId` and `externalRef` must be validated by business logic; never treat client-supplied strings as proof of authorization.

### 4.1. Initial Seed Data (Run on Test Database Only)

```javascript
use shop

db.orders.insertMany([
  {
    _id: "ORD-101",
    tenantId: "TENANT-A",
    externalRef: "EXT-101",
    status: "NEW",
    amountMinor: NumberLong(200000),
    updatedAt: ISODate("2026-11-19T01:00:00Z")
  },
  {
    _id: "ORD-102",
    tenantId: "TENANT-A",
    externalRef: "EXT-102",
    status: "NEW",
    amountMinor: NumberLong(300000),
    updatedAt: ISODate("2026-11-19T01:30:00Z"),
    legacy_note: "Keep if document is not replaced"
  },
  {
    _id: "ORD-103",
    tenantId: "TENANT-A",
    externalRef: "EXT-103",
    status: "TEST_ONLY",
    amountMinor: NumberLong(0),
    updatedAt: ISODate("2026-11-19T02:00:00Z")
  },
  {
    _id: "ORD-104",
    tenantId: "TENANT-A",
    externalRef: "EXT-104",
    status: "WAITING_RETRY",
    amountMinor: NumberLong(100000),
    updatedAt: ISODate("2026-11-19T02:30:00Z")
  },
  {
    _id: "ORD-105",
    tenantId: "TENANT-A",
    externalRef: "EXT-105",
    status: "WAITING_RETRY",
    amountMinor: NumberLong(150000),
    updatedAt: ISODate("2026-11-19T03:00:00Z")
  },
  {
    _id: "ORD-B01",
    tenantId: "TENANT-B",
    externalRef: "EXT-101",
    status: "NEW",
    amountMinor: NumberLong(999999),
    updatedAt: ISODate("2026-11-19T04:00:00Z")
  }
])
```

Tenant B intentionally uses the same `externalRef = "EXT-101"` as Tenant A to verify that filters must include **`tenantId`**. The dataset does not contain `ORD-200` or `EXT-201` prior to bulk execution.

### 4.2. Index Required for Business-Key Upsert

In the partner flow, `externalRef` is unique **within a tenant**, not globally across the collection:

```javascript
db.orders.createIndex(
  { tenantId: 1, externalRef: 1 },
  { unique: true, name: "uq_tenant_external_ref" }
)
```

A unique index prevents two writers from creating two orders with the same `(tenantId, externalRef)` pair. Existing data must be checked before creating the index; if duplicates exist, MongoDB may fail to build it. When fields can be missing or null, design the schema/index (such as a partial index) according to business rules rather than applying commands blindly.

## 5. Building a Mixed Bulk with All Five Operation Groups

File `OrderBulkService.java`:

```java
package com.example.shop.orders;

import com.mongodb.bulk.BulkWriteResult;
import java.time.Instant;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class OrderBulkService {

    private final MongoTemplate template;

    public OrderBulkService(MongoTemplate template) {
        this.template = template;
    }

    public BulkWriteResult executeExample() {
        String tenant = "TENANT-A";
        Instant now = Instant.parse("2026-11-20T02:00:00Z");

        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.ORDERED,
            OrderDocument.class);

        // (1) INSERT: add a document with a new ID.
        bulk.insert(new OrderDocument(
            "ORD-200", tenant, "EXT-200",
            "NEW", 250000L, now));

        // (2) UPDATE ONE: change only the required field.
        bulk.updateOne(
            Query.query(Criteria.where("id").is("ORD-101")
                .and("tenantId").is(tenant)),
            new Update()
                .set("status", "PAID")
                .set("updatedAt", now));

        // (3) UPDATE MULTI: modify all documents waiting for retry.
        bulk.updateMulti(
            Query.query(Criteria.where("tenantId").is(tenant)
                .and("status").is("WAITING_RETRY")),
            new Update()
                .set("status", "QUEUED")
                .set("updatedAt", now));

        // (4) UPSERT: look up by business key within the tenant.
        bulk.upsert(
            Query.query(Criteria.where("tenantId").is(tenant)
                .and("externalRef").is("EXT-201")),
            new Update()
                .setOnInsert("tenantId", tenant)
                .setOnInsert("externalRef", "EXT-201")
                .set("status", "NEW")
                .set("amountMinor", 450000L)
                .set("updatedAt", now));

        // (5) REPLACE: replace the entire representation of ORD-102.
        bulk.replaceOne(
            Query.query(Criteria.where("id").is("ORD-102")
                .and("tenantId").is(tenant)),
            new OrderDocument(
                "ORD-102", tenant, "EXT-102",
                "PAID", 300000L, now));

        // (6) REMOVE: delete only the specified test record.
        bulk.remove(
            Query.query(Criteria.where("id").is("ORD-103")
                .and("tenantId").is(tenant)
                .and("status").is("TEST_ONLY")));

        // Only here are the operations sent for execution.
        return bulk.execute();
    }
}
```

There are **six registration calls** here, covering the five functional groups to learn: `insert`, `update` (one/multi), `upsert`, `replace`, and `remove`. The code is presented as an example with fixed data and timestamps; production code must accept validated input operations, carry a batch ID and checkpoint, and never expose `executeExample()` as a public endpoint.

When `execute()` succeeds, it returns an aggregated `BulkWriteResult`. This example uses `ORDERED`, so `updateOne` runs before `updateMulti`; the chosen filters do not overlap unintentionally. With `UNORDERED`, do not rely on operations that depend on previous writes to implement business logic.

## 6. Insert: Add New Only, Do Not Auto-Replace Duplicate IDs

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    OrderDocument.class);

bulk.insert(new OrderDocument(
    "ORD-300", "TENANT-A", "EXT-300",
    "NEW", 100000L,
    Instant.parse("2026-11-20T03:00:00Z")));

BulkWriteResult result = bulk.execute();
```

`insert` creates a new document. If `_id` already exists, the `_id` unique index blocks the duplicate write; the bulk may throw an error instead of “converting into an update”. If you want **update on match, create on miss**, use `upsert` with proper conditions and unique indexes rather than mixing insert and upsert semantics.

### 6.1. Inserting Multiple Entities

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.UNORDERED,
    OrderDocument.class);

bulk.insert(java.util.List.of(
    new OrderDocument(
        "ORD-301", "TENANT-A", "EXT-301",
        "NEW", 130000L, Instant.parse("2026-11-20T03:00:00Z")),
    new OrderDocument(
        "ORD-302", "TENANT-A", "EXT-302",
        "NEW", 180000L, Instant.parse("2026-11-20T03:00:00Z"))
));

BulkWriteResult result = bulk.execute();
```

With `UNORDERED`, the two inserts are independent, so the driver/server can optimize ordering. If one insert fails with a duplicate key error, the other insert can still succeed. Do not assume “an error means no records were added”.

### 6.2. Identity and Mapping

The entity uses `@Id`; Spring Data maps it to BSON `_id`. If your application uses String IDs shaped like 24-character hex strings, check whether `@Id` converts them to ObjectId. When a BSON String ID is strictly required, consider `@MongoId` with explicit type configuration.

Do not assume every bulk-inserted entity goes through all lifecycle callbacks or auditing of `save`. If your data needs `createdAt`, `updatedBy`, or a version, populate those fields according to your system's bulk write contract.

## 7. UpdateOne and UpdateMulti: Operator-Based Writes

### 7.1. UpdateOne: Only the First Matching Document

```java
bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-101")
        .and("tenantId").is("TENANT-A")),
    new Update().set("status", "PAID"));
```

Because the filter specifies `_id`, at most one document matches. `$set` changes the `status` field without touching any fields outside that path.

**Do not use `updateOne` with an overly broad filter** hoping it picks the “right” document via sorting; if multiple documents match without a unique identifier/condition, the chosen document may violate business intent.

### 7.2. UpdateMulti: Every Matching Document

```java
bulk.updateMulti(
    Query.query(Criteria.where("tenantId").is("TENANT-A")
        .and("status").is("WAITING_RETRY")),
    new Update().set("status", "QUEUED"));
```

With the seed data in Section 4, this operation modifies **ORD-104 and ORD-105**. If you only want to update the first 100 records, `updateMulti` does not mean “update 100 documents by limit” simply because you attach a limit to `Query`; instead, select the IDs using an index, then issue specific `updateOne` calls or an equivalent batch strategy.

### 7.3. Common Update Operators

```java
Update patch = new Update()
    .set("status", "PAID")
    .inc("retryCount", 1)
    .unset("obsoleteFlag")
    .currentDate("updatedAt");
```

`$set` replaces a field value; `$inc` increments/decrements numbers; `$unset` removes a field; `$currentDate` sets a server-side timestamp in the configured type. None of these operators require rewriting the entire document from the application. However, `set("nested", wholeObject)` can **replace the entire subdocument**, dropping sibling fields; to modify one nested field, use dotted paths like `"nested.trackingCode"`.

### 7.4. An Update Does Not Always Modify Data

If `status` is already `PAID` and the query runs `$set status=PAID`, the document **can be matched without being modified**. Thus `matchedCount` and `modifiedCount` differ; do not treat a lower modifiedCount as an error in every case.

## 8. Upsert: Update if Matched, Create New if Not

`upsert(query, update)` expresses two outcomes:

1. A document matches the filter: apply the update operators.
2. No document matches: create a new document according to MongoDB's upsert rules, including equality values from the filter and the applicable update operators.

For partner batches, the `(tenantId, externalRef)` key must be kept unique.

```java
bulk.upsert(
    Query.query(
        Criteria.where("tenantId").is("TENANT-A")
            .and("externalRef").is("EXT-201")),
    new Update()
        .setOnInsert("tenantId", "TENANT-A")
        .setOnInsert("externalRef", "EXT-201")
        .set("status", "NEW")
        .set("amountMinor", 450000L));
```

`setOnInsert` only takes effect **when creating a new document** via upsert; if a document already exists, those fields are left untouched by the normal update branch. `set` applies in both insert and update cases.

### 8.1. When to Use setOnInsert?

Example of synchronizing an entry:

```java
Update update = new Update()
    .setOnInsert("createdAt",
        Instant.parse("2026-11-19T00:00:00Z"))
    .setOnInsert("source", "PARTNER-IMPORT")
    .set("status", "PAID")
    .set("updatedAt",
        Instant.parse("2026-11-20T02:00:00Z"));
```

`createdAt` and `source` are initialized only when the document is created; `status` and `updatedAt` are updated on each run. This is a business choice: if a sync run must not overwrite `status` once finalized, add an appropriate condition/state machine check rather than unconditionally calling `$set`.

### 8.2. Upsert Does Not Replace Database-Level Uniqueness

Two instances can run concurrently:

```text
Instance A                Instance B
     |                         |
     +-- upsert EXT-201        +-- upsert EXT-201
     |                         |
     +-- no document found     +-- no document found
     |                         |
     +-- attempts insert       +-- attempts insert
                |
                v
        Unique index protects
        (tenantId, externalRef)
```

Without a unique index, **two duplicate business records** can be created. With an appropriate index, MongoDB prevents duplicates; one writer may update the newly created record or fail with a duplicate key error depending on the exact query/update/race. **Do not assume every duplicate-key error is automatically retried successfully by the driver.**

When an upsert hits a duplicate key error, the service should re-read the document by business key, verify tenant and state, and then decide between a controlled retry or reporting a conflict.

### 8.3. Upsert Without a Fixed ID

If the query does not specify `_id`, MongoDB may assign an `ObjectId` to the new document. In a Java model with `@Id String id`, Spring Data can convert the BSON ID into a Java String on read. However, if business logic requires a fixed ID or specific format, **explicitly design new ID generation and test the BSON**, rather than assuming upsert generates IDs identically to `repository.save`.

For instance, use the external key `(tenantId, externalRef)` to look up the record after upsert; do not try to guess the ID:

```javascript
db.orders.findOne({
  tenantId: "TENANT-A",
  externalRef: "EXT-201"
})
```

## 9. ReplaceOne: Document Replacement Carries Data-Loss Risk

`replaceOne(query, replacement)` writes the **full representation** of the target document from the replacement object. It differs from `updateOne(query, new Update().set(...))`.

### 9.1. Before and After Replacement

Initially:

```javascript
{
  _id: "ORD-102",
  tenantId: "TENANT-A",
  externalRef: "EXT-102",
  status: "NEW",
  amountMinor: NumberLong(300000),
  legacy_note: "Keep if document is not replaced"
}
```

With an `OrderDocument` entity that **does not declare `legacy_note`**, the command:

```java
bulk.replaceOne(
    Query.query(Criteria.where("id").is("ORD-102")
        .and("tenantId").is("TENANT-A")),
    new OrderDocument(
        "ORD-102",
        "TENANT-A",
        "EXT-102",
        "PAID",
        300000L,
        Instant.parse("2026-11-20T02:00:00Z")));
```

can produce this new representation:

```javascript
{
  _id: "ORD-102",
  tenantId: "TENANT-A",
  externalRef: "EXT-102",
  status: "PAID",
  amountMinor: NumberLong(300000),
  updatedAt: ISODate("2026-11-20T02:00:00Z"),
  _class: "com.example.shop.orders.OrderDocument"
  // legacy_note is no longer present.
}
```

This is **not a MongoDB bug**: replacement is designed to replace the document with new data. If legacy fields must be preserved, **do not replace using an entity representing only part of the schema**; instead, use `$set` for owned fields or a controlled BSON merge/round-trip mechanism.

### 9.2. Keeping `_id` Immutable

Replacement cannot change the `_id` of the matched document. If the replacement object carries a different ID, MongoDB can reject it because `_id` is immutable. Never use `replaceOne` to “change a document's primary key”.

For upsert-replace, design ID generation and mismatch handling separately. The example in this lesson does **not** enable upsert on replacement so it does not accidentally create unintended documents.

### 9.3. When Does Replacement Make Sense?

- The writer **owns the entire schema** of the document.
- A fully validated new snapshot has been received.
- You intentionally want to drop fields no longer in the schema contract.
- A version/CAS check or other mechanism exists to avoid overwriting a concurrent writer's snapshot.

Do not use replacement for simple tasks like “changing status”, “incrementing retryCount”, or “updating one field inside a nested object”.

## 10. Remove: Scoped Deletion, Avoid Broad Filters

To delete the test record `ORD-103` belonging to tenant A:

```java
bulk.remove(Query.query(
    Criteria.where("id").is("ORD-103")
        .and("tenantId").is("TENANT-A")
        .and("status").is("TEST_ONLY")));
```

In this example, `_id` ensures the condition targets at most one document. When cleaning up thousands of records, never run `{ status: "EXPIRED" }` directly in a multi-tenant system or when retention rules apply.

### 10.1. Checks Before Hard Deletion

For cleanup jobs:

1. Build the filter from tenant constraints, data type, and retention period.
2. Run a **count and sample preview** on test data or a verified target set.
3. Verify unique business rules, soft-delete policies, audit requirements, and backup/recovery plans.
4. Chunk by batch or select specific IDs if you need to bound each deletion run.
5. Log the batch ID, normalized filter, deleted count, and errors.

**Do not treat ordered bulk as an undo mechanism:** after a partial deletion succeeds and a subsequent operation fails, deleted documents do not come back unless wrapped in an appropriate transaction.

### 10.2. Soft Delete Instead of Remove

If business requirements call for retaining history:

```java
bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-103")
        .and("tenantId").is("TENANT-A")),
    new Update()
        .set("deleted", true)
        .set("deletedAt", Instant.parse(
            "2026-11-20T02:00:00Z")));
```

Choosing soft delete vs. hard delete must follow business contracts, security, retention, and legal requirements. When using soft delete, all business queries must consistently apply `deleted != true`/`deleted = false` filters according to an explicit data convention.

## 11. Reading BulkWriteResult Correctly

When `execute()` succeeds:

```java
import com.mongodb.bulk.BulkWriteResult;

BulkWriteResult result = bulk.execute();

int inserted = result.getInsertedCount();
int matched = result.getMatchedCount();
int modified = result.getModifiedCount();
int deleted = result.getDeletedCount();
int upserted = result.getUpserts().size();
```

| Result Field | Interpretation | Notes |
| --- | --- | --- |
| `insertedCount` | Number of documents added by insert operations | Does not necessarily include documents created via upsert |
| `matchedCount` | Total documents matched by applicable update/replace operations | Not equal to operation count; `updateMulti` can match many documents |
| `modifiedCount` | Number of documents actually changed as reported by the driver | Can be lower than matchedCount due to no-op updates |
| `deletedCount` | Total documents deleted | A single remove with a broad filter can affect many documents |
| `upserts` | Details of upserts that created new documents | Can be used to inspect the operation index and generated ID |

With the **exact seed data and ordered bulk in Sections 4–5**, assuming no concurrent writers and that all operations modify data:

```text
insertedCount        = 1  (ORD-200)
matchedCount         = 4  (1 updateOne + 2 updateMulti + 1 replaceOne)
modifiedCount        = 4  (all of those operations actually changed values)
deletedCount         = 1  (ORD-103)
upserts.size()       = 1  (EXT-201 newly created)
```

If you run the **exact same** bulk again on the modified database, the counts will differ: inserting `ORD-200` will hit a duplicate key error, `updateMulti` will no longer match `WAITING_RETRY`, `remove` will find no target, and `upsert` will take the update branch. Thus these numbers are **expectations for a single run against the seeded fixture**, not fixed properties of the method.

### 11.1. On Error, You Do Not Always Get a Normal BulkWriteResult

`execute()` can throw an exception even when some operations have already succeeded. Between ordered and unordered, stopping/continuing behavior and partial results can differ.

Handling code should:

- Distinguish **write command errors** (duplicate key, validation, BSON invariants, etc.) from connection/unknown-outcome errors.
- Record the batch ID, operation set, and error details extractable from the exception.
- Avoid blindly retrying the **entire batch**; first determine which operations were applied.
- Inspect the actual state of business keys or use idempotency keys to reconcile.

Never put a `catch` block that returns `insertedCount = 0` when an exception is thrown: that misreports state and can cause repeated runs leading to data corruption.

### 11.2. Write Acknowledgement

Bulk results and error control require an **acknowledged** write concern. `WriteConcern.UNACKNOWLEDGED` reduces your ability to determine which commands were applied and can make certain result accessors unavailable.

For critical data, choose write concern and read concern based on system requirements; `acknowledged` means the server confirmed at the configured level—it does **not** mean a multi-document bulk became atomic.

## 12. Partial Failures, Retries, and Idempotency

A bulk containing multiple independent operations should be designed as a **reconcilable unit of work**, not simply a “fire-and-forget” call.

| Operation | When Re-Run with Same Data | What Must Be Protected |
| --- | --- | --- |
| `insert` with fixed ID | May hit duplicate key error | Batch ID, check existing document, never blindly treat every duplicate as success |
| `$set field=value` | Usually idempotent for the same field/value | Concurrent writers and updates to other fields |
| `$inc counter=1` | **Not idempotent**, may increment twice | CAS/version, operation ID, or deduplication |
| `upsert` by business key | May shift from insert to update on retry | Unique index, exact filter, `setOnInsert` |
| `replaceOne` | May write the same snapshot repeatedly | Avoid overwriting newer changes from another writer |
| `remove` by ID | Next run may find no target | Audit/retention, avoid deleting a new document reusing the business key |

### 12.1. Do Not Blindly Retry an Entire Unordered Bulk

Suppose an unordered bulk includes inserts, `$inc`, and upserts. If a timeout occurs **after the server has executed some commands**, the application does not know exactly which subset committed. Retrying everything can:

- Insert duplicate IDs.
- Increment counters twice.
- Overwrite the status of a record just edited by a user.
- Trigger different unique index errors than the first run.

A resilient approach:

1. Assign business-meaningful `operationId`/`batchId` values.
2. Prefer **replayable** operations whenever possible.
3. Persist checkpoints or a tracking table of processed operations as required.
4. Reconcile business keys after an error before retrying.
5. Cap retry attempts, apply backoff, and surface actionable errors.

### 12.2. Order-Dependent Operations

If the same document receives:

```text
1. updateOne(status = PAID)
2. replaceOne(status = NEW)
```

execution order changes the outcome. With `UNORDERED`, you must not depend on this order. Better options are to **merge the logic into a single conditional operation** or split into independent stages with checkpoints.

`ORDERED` preserves order within the batch itself, yet it **does not stop** other writers from concurrently modifying the document. To guard against concurrency, use expected version/CAS or an appropriate transaction.

## 13. BulkOperations Does Not Automatically Replace @Version and Entity Callbacks

A very easy mistake: assuming that annotating an entity with `@Version` gives **every write operation** automatic optimistic locking. Under the `BulkOperations` contract, operations requiring per-entity outcomes—such as **optimistic locking with `@Version`**—are not supported the same way as standard `save` operations. Do not rely on bulk to automatically attach version predicates and bump versions per entity.

### 13.1. A Versioned Model

File `VersionedOrder.java`:

```java
package com.example.shop.orders;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record VersionedOrder(
    @Id String id,
    String tenantId,
    String status,
    @Version Long version
) {}
```

With standard `repository.save(...)`, `@Version` helps detect stale writes in the way Spring Data supports. Inside **bulk**, however, the author must explicitly design expected-version checks.

### 13.2. Explicit CAS Inside Bulk

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    VersionedOrder.class);

bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-101")
        .and("tenantId").is("TENANT-A")
        .and("version").is(3L)),
    new Update()
        .set("status", "PAID")
        .inc("version", 1L));

BulkWriteResult result = bulk.execute();

if (result.getMatchedCount() != 1) {
    throw new IllegalStateException(
        "Matching order/version not found");
}
```

In this snippet, **matching `version=3`** and **incrementing version via `$inc`** are written **explicitly**, rather than performed automatically by `BulkOperations` from `@Version`. If another writer incremented the version earlier, the filter misses and `matchedCount` can be 0.

**Note:** `BulkWriteResult` only aggregates counts for the entire batch. If it contains 100 version-guarded `updateOne` calls, `matchedCount = 95` shows 5 operations did not match (assuming each query targets one distinct document), yet it **does not identify the IDs of those 5 operations**. To identify individual records:

- Maintain an `operationId → business key / expectedVersion` mapping.
- Chunk batches sensibly and reconcile unmatched IDs.
- For workflows needing exact per-update feedback or entity-level optimistic locking, consider another API for those writes.

### 13.3. Auditing and Lifecycle Callbacks

On regular entity save paths, a system may have `@CreatedDate`, `@LastModifiedDate`, `BeforeConvertCallback`, `BeforeSaveCallback`, or other events. Bulk writes **do not have a “call save on each entity” contract**, so do not expect the full callback/auditing lifecycle to run as with individual `repository.save` calls.

If bulk writes need `createdAt`, `updatedAt`, `updatedBy`, tenant, version, or audit metadata, prepare those values explicitly in your DTO/entity/`Update` and test the resulting BSON. For upserts, `setOnInsert("createdAt", ...)` is typically appropriate; for updates, `set("updatedAt", ...)` makes the change explicit.

## 14. Bulk, Transactions, and Atomicity

MongoDB guarantees **atomicity of a single write operation on a single document**. A bulk containing multiple inserts/updates/removes is not implicitly atomic across the whole batch.

### 14.1. Without a Transaction

Example:

```text
Bulk ORDERED:
  INSERT A -> succeeded
  UPDATE B -> succeeded
  INSERT C -> duplicate key
  DELETE D -> not executed

Result:
  A was added
  B was modified
  C failed
  D remains untouched
```

Even when `execute()` throws an exception, **A and B do not roll back automatically**. With unordered, successes and errors may interleave and execution order will not match the input list.

### 14.2. When All-or-Nothing Is Truly Needed

If business requirements genuinely demand committing multiple documents together, you can use a **MongoDB multi-document transaction** when your deployment supports it (suitable replica set/sharded cluster) and Spring Data is configured with a transaction manager/session.

Conceptual example inside a service that already has a `TransactionTemplate`:

```java
transactionTemplate.executeWithoutResult(status -> {
    BulkOperations bulk = template.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        OrderDocument.class);

    bulk.insert(new OrderDocument(
        "ORD-401", "TENANT-A", "EXT-401",
        "NEW", 100000L, Instant.parse(
            "2026-11-20T02:00:00Z")));

    bulk.updateOne(
        Query.query(Criteria.where("id").is("ORD-101")
            .and("tenantId").is("TENANT-A")),
        new Update().set("status", "PAID"));

    bulk.execute();
});
```

This snippet illustrates **transaction boundaries only**. To run in practice, you must configure `MongoTransactionManager` and Spring transaction management, ensure MongoDB supports transactions, and point `TransactionTemplate` at the right manager. Do not copy it and assume transactions work without verifying infrastructure.

Transactions carry overhead; do not use them just to “make bulk faster”. Furthermore, transactions do not automatically make retried requests idempotent, nor do they prevent replacements from dropping unknown fields.

### 14.3. Transactions and Oversized Bulks

A bulk with many large documents inside a long-running transaction increases resource usage, conflict probability, and snapshot retention time. For reconcilable ETL/import jobs, **checkpointed batch splitting** is usually more practical; reserve transactions for scopes that truly require invariants.

## 15. Batch Splitting, Load Limits, and Performance Tuning

Do not build a `BulkOperations` holding millions of operations before calling `execute()`. Even though the driver/server can split commands per protocol limits, the application still consumes memory holding operations, struggles to checkpoint, and cannot easily isolate failures by group.

### 15.1. Simple Chunking

```java
import java.util.List;
import org.springframework.data.mongodb.core.BulkOperations;

public void insertChunks(
        MongoTemplate template,
        List<OrderDocument> orders) {

    int chunkSize = 500; // Example; measure based on document size.

    for (int from = 0; from < orders.size(); from += chunkSize) {
        int to = Math.min(from + chunkSize, orders.size());
        List<OrderDocument> chunk = orders.subList(from, to);

        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            OrderDocument.class);

        bulk.insert(chunk);
        BulkWriteResult result = bulk.execute();

        // Record checkpoint/reconciliation after each successful chunk.
        System.out.println("Inserted: " + result.getInsertedCount());
    }
}
```

`orders` in this example is a normalized, authorized list ready to write. This snippet omits retry logic and intentionally **does not catch and ignore exceptions**; production code must persist reconcilable checkpoints and handle per-chunk failures.

### 15.2. Why Is There No Single Optimal Chunk Size?

Cost depends on:

- Average and maximum document size (MongoDB enforces a per-document BSON size limit).
- Number of fields/indexes updated per write.
- Server load, network latency, connection pool, and write concern.
- Rates of duplicate keys, conflicts, upserts, and multi-document `updateMulti`.
- Application memory and checkpoint/retry requirements.

Batch/message limits published by the MongoDB server/driver may cause the driver to split a bulk into multiple parts. Never equate **one `execute()` call** with exactly **one network packet** or one transaction.

### 15.3. Grouping Multiple Collections?

`MongoTemplate.bulkOps(mode, Entity.class)` binds a bulk to a single entity/target collection. If you need to write to multiple collections, create separate bulks accordingly; do not mix orders, customers, and inventory into one builder expecting the framework to route them automatically.

If multiple collections must be updated consistently, design service-level sessions/transactions or an event/saga workflow instead of calling it “one bulk”. This also makes per-collection error monitoring clearer.

### 15.4. Measuring Properly

When benchmarking:

1. Compare against a `save` loop using the **same data size**, same write concern, and same indexes.
2. Record `execute()` duration, throughput (operations/s), p95/p99 latency, CPU, and processed document count.
3. Track duplicate keys, write errors, write concern errors, memory, queue depth, and lock contention.
4. Separate **BSON mapping** cost from driver/network/server cost when diagnosing bottlenecks.
5. Evaluate index impact: adding indexes speeds up reads but increases write cost.

`explain("executionStats")` is useful for **queries/filters** used in updates or ID-selection steps, though it does not replace measuring the full bulk write. Performance also depends on index maintenance and concurrency levels.

## 16. Failure Recovery Plan

A production bulk job should capture at minimum:

| Operational Data | Why It Is Needed |
| --- | --- |
| `batchId` and data source | Trace a specific import/sync run |
| ID/business key per operation | Identify which operations need reconciliation |
| Operation type and expected version | Distinguish insert/update/upsert, prevent stale writes |
| Start/end timestamps | Measure latency and investigate incidents |
| Summary counts and driver errors | Reconcile execution counts |
| Last confirmed checkpoint | Avoid reprocessing everything on restart |
| Retry/quarantine status | Isolate malformed records for separate handling |

**Be careful with sensitive information:** logs should store IDs or sanitized metadata—never dump full customer payloads, tokens, or secret data into bulk error logs.

### 16.1. When a Duplicate Key Error Occurs

Do not automatically treat a duplicate key as a success. Verify:

- Does the existing document match the expected business key and tenant?
- Is the existing data compatible with the operation?
- Is this a retry of the **same operation** or a conflict between two different requests?
- For an upsert, was the unique index created correctly?

Then decide whether to *skip as already completed*, *conditionally retry*, *merge*, or *send to an error queue*. With `ORDERED`, writes after the error must be treated as not executed; with `UNORDERED`, reconcile each operation rather than guessing execution order.

## 17. Integration Testing with MongoDB: Results and Post-Write BSON

Mocking `MongoTemplate` cannot verify that the server applies `$set` correctly, upserts create documents, replacement drops legacy fields, or `ORDERED` stops after a duplicate key error. Test against real MongoDB in an **isolated instance/database**. You can use Testcontainers following your Spring Boot project's test connection setup.

The example below uses JUnit 5, AssertJ, and `@DataMongoTest`. Note that `@DataMongoTest` in this snippet belongs to the Spring Boot package `org.springframework.boot.test.autoconfigure.data.mongo`; verify the appropriate package if upgrading major versions.

### 17.1. Fixture Containing Data Outside the Java Model

File `OrderBulkOperationsTest.java`:

```java
package com.example.shop.orders;

import com.mongodb.bulk.BulkWriteResult;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import org.bson.Document;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@DataMongoTest
class OrderBulkOperationsTest {

    @Autowired
    MongoTemplate template;

    private static Document order(
            String id,
            String tenantId,
            String externalRef,
            String status,
            long amountMinor) {

        return new Document("_id", id)
            .append("tenantId", tenantId)
            .append("externalRef", externalRef)
            .append("status", status)
            .append("amountMinor", amountMinor)
            .append(
                "updatedAt",
                Date.from(Instant.parse(
                    "2026-11-19T01:00:00Z")))
            .append("legacy_note", "legacy-owned-data");
    }

    private Document rawById(String id) {
        return template.getCollection("orders")
            .find(new Document("_id", id))
            .first();
    }

    @BeforeEach
    void seed() {
        // Delete data only in an ISOLATED test database.
        var collection = template.getCollection("orders");
        collection.deleteMany(new Document());

        collection.insertMany(List.of(
            order("ORD-101", "TENANT-A", "EXT-101",
                  "NEW", 200000L),
            order("ORD-102", "TENANT-A", "EXT-102",
                  "NEW", 300000L),
            order("ORD-103", "TENANT-A", "EXT-103",
                  "TEST_ONLY", 0L),
            order("ORD-104", "TENANT-A", "EXT-104",
                  "WAITING_RETRY", 100000L),
            order("ORD-105", "TENANT-A", "EXT-105",
                  "WAITING_RETRY", 150000L),
            order("ORD-B01", "TENANT-B", "EXT-101",
                  "NEW", 999999L)
        ));
    }

    @Test
    void mixedBulkAppliesSixOperationsInCorrectScope() {
        BulkWriteResult result =
            new OrderBulkService(template).executeExample();

        assertThat(result.wasAcknowledged()).isTrue();
        assertThat(result.getInsertedCount()).isEqualTo(1);
        assertThat(result.getMatchedCount()).isEqualTo(4);
        assertThat(result.getModifiedCount()).isEqualTo(4);
        assertThat(result.getDeletedCount()).isEqualTo(1);
        assertThat(result.getUpserts()).hasSize(1);

        assertThat(rawById("ORD-200")).isNotNull();
        assertThat(rawById("ORD-103")).isNull();

        assertThat(rawById("ORD-101").getString("status"))
            .isEqualTo("PAID");
        assertThat(rawById("ORD-104").getString("status"))
            .isEqualTo("QUEUED");
        assertThat(rawById("ORD-105").getString("status"))
            .isEqualTo("QUEUED");

        Document upserted = template.getCollection("orders")
            .find(new Document("tenantId", "TENANT-A")
                .append("externalRef", "EXT-201"))
            .first();
        assertThat(upserted).isNotNull();
        assertThat(upserted.getString("status"))
            .isEqualTo("NEW");

        // Does not leak to tenant B despite matching externalRef.
        assertThat(rawById("ORD-B01").getString("status"))
            .isEqualTo("NEW");
    }

    @Test
    void updatePreservesUnknownFieldsButReplaceRemovesThem() {
        new OrderBulkService(template).executeExample();

        Document updated = rawById("ORD-101");
        assertThat(updated).isNotNull();
        assertThat(updated.getString("legacy_note"))
            .isEqualTo("legacy-owned-data");

        Document replaced = rawById("ORD-102");
        assertThat(replaced).isNotNull();
        assertThat(replaced.getString("_id"))
            .isEqualTo("ORD-102");
        assertThat(replaced.getString("status"))
            .isEqualTo("PAID");

        // Replacement does not preserve fields absent from OrderDocument.
        assertThat(replaced.containsKey("legacy_note"))
            .isFalse();
    }

    @Test
    void orderedBulkStopsAfterDuplicateKeyButEarlierInsertPersists() {
        BulkOperations bulk = template.bulkOps(
            BulkOperations.BulkMode.ORDERED,
            OrderDocument.class);

        bulk.insert(new OrderDocument(
            "ORD-300", "TENANT-A", "EXT-300",
            "NEW", 100000L,
            Instant.parse("2026-11-20T02:00:00Z")));

        // ORD-101 already exists; second insert will fail with duplicate _id.
        bulk.insert(new OrderDocument(
            "ORD-101", "TENANT-A", "EXT-DUPLICATE",
            "NEW", 100000L,
            Instant.parse("2026-11-20T02:00:00Z")));

        // Must not run if ordered stops at the second operation.
        bulk.updateOne(
            Query.query(Criteria.where("id").is("ORD-104")
                .and("tenantId").is("TENANT-A")),
            new Update().set("status", "PAID"));

        assertThatThrownBy(() -> bulk.execute())
            .isInstanceOf(RuntimeException.class);

        // Bulk is not a transaction: operations before the error can still be written.
        assertThat(rawById("ORD-300")).isNotNull();
        assertThat(rawById("ORD-104").getString("status"))
            .isEqualTo("WAITING_RETRY");
    }
}
```

**Explicit warning:** `collection.deleteMany(new Document())` deletes all `orders` in whichever test database it connects to. Ensure you have a test profile and an isolated database; **never run these tests against production**.

The counts asserted in `mixedBulkAppliesSixOperationsInCorrectScope` apply specifically to the fixture above with no concurrent writers and no extra mapping/version behavior. `modifiedCount` can differ from `matchedCount` when updates do not alter values.

### 17.2. Why Must the Fixture Be Inserted via the Driver?

`OrderDocument` does not declare `legacy_note`. If seeded via `template.insert(new OrderDocument(...))`, the document would lack that field; after `replaceOne`, the test could not verify whether out-of-model fields get stripped.

Calling `template.getCollection("orders").insertMany(...)` writes `org.bson.Document` directly through the driver, producing **typed BSON** including String, Int64, Date, and the extra field. Reading back via the raw driver after bulk execution proves which fields survive or disappear.

### 17.3. A Dedicated Test for Manual CAS

Suppose a document has `version: NumberLong(3)`. Test two updates with the same `expectedVersion`:

```java
BulkOperations bulk = template.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    OrderDocument.class);

Query v3 = Query.query(Criteria.where("id").is("ORD-101")
    .and("tenantId").is("TENANT-A")
    .and("version").is(3L));

bulk.updateOne(v3,
    new Update().set("status", "PAID")
        .inc("version", 1L));

bulk.updateOne(
    Query.query(Criteria.where("id").is("ORD-101")
        .and("tenantId").is("TENANT-A")
        .and("version").is(3L)),
    new Update().set("status", "CANCELLED")
        .inc("version", 1L));

BulkWriteResult result = bulk.execute();
// Expect matchedCount = 1, version goes from 3 to 4.
```

This is an **additional illustrative snippet**; it does not run directly on the Section 17.1 fixture because that fixture lacks a `version` field. Seed a document with `version` first and inspect the post-write BSON. It demonstrates how to build **manual** CAS in bulk, rather than promising `@Version` handles it automatically.

### 17.4. Matrix of Scenarios to Test

| Scenario | What to Verify |
| --- | --- |
| Insert with new ID | `insertedCount` increments, BSON mapping is correct |
| Insert with duplicate `_id` | Duplicate key error; ordered stops subsequent operations |
| UpdateOne with exact ID and tenant | Only the target document is modified |
| UpdateMulti by status within tenant | All matching documents change; other tenants remain untouched |
| First-time upsert | `upserted` entry exists and new document has required fields |
| Second upsert | Takes update branch, creates no duplicate business key |
| ReplaceOne on document with extra fields | Detects that fields omitted from replacement are removed |
| UpdateOne `$set` on document with extra fields | Extra fields are preserved |
| Remove with unmatched filter | Nothing deleted, `deletedCount` reflects zero |
| Unordered bulk with one duplicate key | Other independent operations may still execute |
| Update using expected version | Stale writer fails to match, version is not incremented twice |
| Network failure mid-batch | Never assume 0 writes succeeded; reconcile |
| Empty batch | Service does not call `execute()` with an empty operation list |
| Large batch | Chunking, memory bounds, and checkpointing work |

## 18. Reactive Bulk Write: Same Semantics, Asynchronous API

In reactive Spring Data MongoDB, `ReactiveMongoTemplate.bulkOps(...)` provides the corresponding bulk builder `ReactiveBulkOperations`, whose `execute()` returns a publisher, typically `Mono<BulkWriteResult>`.

Example:

```java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<BulkWriteResult> markQueuedReactive(
        ReactiveMongoTemplate template, String tenantId) {

    return template.bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            OrderDocument.class)
        .updateMulti(
            Query.query(Criteria.where("tenantId").is(tenantId)
                .and("status").is("WAITING_RETRY")),
            new Update().set("status", "QUEUED"))
        .execute();
}
```

This snippet lives inside a Java service/class and must validate `tenantId` before executing. The publisher **does not execute until subscribed to** under Reactor's contract. Reactive tests can use `StepVerifier`; never call `block()` on a production non-blocking thread merely to obtain a synchronous result.

Whether reactive or imperative, **ORDERED/UNORDERED, partial failures, unique indexes, lack of automatic optimistic locking, and idempotency** remain the exact same problems to solve. The main difference lies in orchestrating results and non-blocking resources.

## 19. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Calling multiple `bulk.insert` methods without DB changes | `execute()` was never called | Execute the builder and inspect results/errors |
| `ORDERED` throws error yet first record remains | Bulk is not a transaction | Design partial failure handling, checkpoints, or a transaction |
| `UNORDERED` yields unpredictable final state | Order-dependent operations targeted the same document | Merge logic or split into ordered phases |
| Insert fails with duplicate ID | Unique `_id`/business key collision | Handle duplicates; consider proper upsert semantics |
| Upsert creates two duplicate business records | Missing unique index or unstable filter | Add tenant-scoped unique key and handle concurrent upsert races |
| Replace deletes legacy fields | Replacement lacks fields outside the Java model | Use `$set` or controlled BSON merging |
| Bulk does not increment `@Version` like `save` | No automatic per-entity optimistic locking in bulk | Explicit expected-version CAS and `$inc` |
| `matchedCount` exceeds `modifiedCount` | No-op update or value already matched | Interpret both metrics according to their distinct meanings |
| Retry increments counters twice | `$inc` is not idempotent | Deduplication/operation ID, CAS |
| Tenant B order modified during Tenant A batch | Filter missing `tenantId` | Enforce tenant scoping on all updates/removes/upserts |
| Remove deletes too many records | Overly broad query or flawed retention logic | Target explicit IDs/bounds, preview samples, check authorization |
| Huge batch exhausts resources | Accumulating too many operations in memory | Chunk, bound payloads, checkpoint |
| Missing auditing timestamps | Bulk does not run entity save callbacks | Set timestamps/audit fields explicitly |
| Catching exception and reporting “no writes succeeded” | Misunderstanding partial results | Reconcile actual DB state and avoid blind retries |

## 20. Practice Exercise

An inventory operations system receives a sync file of 10,000 products across multiple suppliers. Each product has `tenantId`, `sku`, `priceMinor`, `available`, `updatedAt`, and `sourceRevision`. The collection also contains `supplierMetadata` managed by another service.

Requirements:

1. Propose an appropriate unique index for the business key `(tenantId, sku)`.
2. Design a **bulk upsert** that updates price and stock status while setting `createdAt` only on initial insert.
3. If only price needs updating, explain why you should not use `replaceOne` on the entire document.
4. Given two rows in the same file referencing the same `sku`, should you use `ORDERED` or `UNORDERED`? Propose a deduplication or file-rejection policy.
5. Suppose a price is modified using `$inc` with an adjustment delta; what error can a retry after timeout cause?
6. Design chunk size, checkpointing, and how to handle a row failing schema validation.
7. If `sourceRevision` must prevent overwrites from an older file, write the explicit CAS/version condition in `Query` and describe how to verify the result.
8. Write an integration test seeding BSON with `supplierMetadata`, run a bulk update and verify the metadata remains; then run a replace with an entity lacking that field to observe the data-loss risk.

**Solution guidance:** use `$set`/`setOnInsert` with a unique index, keep every update scoped by tenant, deduplicate inputs before building the bulk, and prefer idempotent operations wherever possible. `UNORDERED` is only appropriate when operations are independent; if the same SKU appears multiple times and order matters, normalize data or handle separately instead of relying on bulk order. Versioning/CAS must be implemented explicitly, because `BulkOperations` does not substitute for `save`'s optimistic locking.

## 21. References

- Spring Data MongoDB — [Bulk Operations](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.bulk-operations): how to use `BulkOperations` and notes on optimistic locking.
- Spring Data MongoDB — [BulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/BulkOperations.html): `BulkMode`, `insert`, `updateOne`, `updateMulti`, `upsert`, `replaceOne`, `remove`, and `execute`.
- Spring Data MongoDB — [ReactiveBulkOperations API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveBulkOperations.html): non-blocking publisher-based bulk writes.
- MongoDB Manual — [Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/): ordered/unordered semantics and error behavior.
- MongoDB Manual — [db.collection.bulkWrite()](https://www.mongodb.com/docs/manual/reference/method/db.collection.bulkWrite/): result structure, ordered flag, and operation list.
- MongoDB Manual — [Transactions](https://www.mongodb.com/docs/manual/core/transactions/): atomic boundaries and infrastructure requirements for multi-document transactions.

## Key Takeaways

**`BulkOperations` is a tool for grouping write operations**, not a transaction mechanism or an automatic per-entity `save` loop. Use `insert` for new additions, `updateOne`/`updateMulti` for selective modifications, `upsert` when updating or creating on miss, `replaceOne` when you genuinely intend to replace the whole document, and `remove` for verified deletions. Choose `ORDERED` when order matters and `UNORDERED` when commands are independent; always inspect `BulkWriteResult` and account for partial failures. For critical data, enforce tenant scoping, unique business keys, CAS/versioning, idempotency, real BSON testing, and checkpointing so bulk operations run safely in production.
