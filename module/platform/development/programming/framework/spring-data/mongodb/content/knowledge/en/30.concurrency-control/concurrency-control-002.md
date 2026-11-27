# Single-document atomicity and the limits of consecutive commands

## 1. Document-level atomicity does not mean the entire business flow is atomic

In the **Concurrency Control** chapter of **Spring Data MongoDB**, many systems must concurrently handle order placement, stock deduction, state transitions, or money transfers. MongoDB provides a foundational guarantee: **a single write operation on a single document is atomic at the level of that document**. However, a `find → check → save` sequence, two `updateOne` calls, or operations across two collections **do not automatically** belong to the same transaction.

For example, a product has `stock_qty = 5`, and two customers simultaneously want to reserve 3 units each:

~~~text
Request A                         Request B
---------                         ---------
read(stock = 5)
                                  read(stock = 5)
5 >= 3 => valid                   5 >= 3 => valid
save(stock = 2)
                                  save(stock = 2)
return success                    return success
~~~

Both requests accept a total of **6** items, yet inventory only records a reduction of **3**. Each `save` call may have been atomic, yet the **read → check → write** process still suffered a *lost update*.

To preserve the "non-negative stock" invariant within **one document**, convert it into a conditional command:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

MongoDB evaluates the condition when applying the write. One request deducts 3 from 5 down to 2, and the second request will **not match** `stock_qty >= 3`; overselling does not occur if other write paths also respect this invariant.

Lesson objectives:

- Distinguish **single-document atomicity** from **multi-command/multi-document atomicity**.
- Recognize lost updates, stale reads, time-of-check/time-of-use, and dangerous retries.
- Use `MongoTemplate.updateFirst`, `$inc`, `findAndModify`, and compare-and-set conditions.
- Know when `@Version` or a MongoDB transaction is required.
- Properly handle `matchedCount`, idempotency, network errors, write concerns, and concurrency testing.

> Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and a compatible MongoDB. Framework/driver/topology-dependent details must be verified against your deployed version. This guide covers concurrency modeling patterns and does not replace testing and auditing procedures for real financial systems.

## 2. Matrix of guarantee types

| Concept | Guarantee or purpose | Does not automatically guarantee |
|---|---|---|
| Single-document atomic write | One command modifying one document never exposes partial write state from that command | That subsequent commands will also commit |
| `$inc`, `$set`, `$addToSet` | Server-side field operations in a single update | That a replayed request will not apply twice |
| Conditional update | Writes only when the filter still matches | Explaining why the filter did not match |
| `findAndModify` | Atomically finds/modifies one document and retrieves pre/post-image | Modifying other documents in the same transaction |
| `@Version` | Detects stale saves on write paths supporting optimistic locking | Automatically protecting all raw/bulk updates |
| Unique index | Prevents duplicate business keys per index | Atomic cross-collection operations |
| Write concern | Acknowledgment/durability level of writes | Business invariant correctness |
| Retryable writes | Driver may retry certain supported commands per its mechanism | Exactly-once for an entire workflow |
| Transaction | Commit/rollback across operations enlisted in the transaction | Rolling back emails or external APIs outside MongoDB |
| Idempotency key | Prevents re-applying the same business intent | Replacing transactions when multiple documents need all-or-nothing |

~~~mermaid
flowchart TD
    A["Business write needed"] --> B{"Invariant within one document?"}
    B -->|"Yes"| C["Conditional update / findAndModify"]
    B -->|"No"| D{"Multiple documents must commit together?"}
    D -->|"Yes"| E["Transaction + MongoTransactionManager"]
    D -->|"No"| F["State machine + compensation/reconciliation"]
    C --> G["Check matched/result"]
    E --> H["Handle commit/retry errors"]
    F --> H
    G --> I["Idempotency and observability"]
    H --> I
~~~

An HTTP request, a Java method, or a `BulkOperations.execute()` call does not automatically create a transaction. The scope of guarantees must be determined **by the actual MongoDB operations executed**.

## 3. A single operation can update multiple fields of one document

Document:

~~~json
{
  "_id": "p-101",
  "tenantId": "tenant-a",
  "status": "ACTIVE",
  "stock_qty": 5,
  "reserved_qty": 0
}
~~~

A command changing multiple fields simultaneously:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    stock_qty: { $gte: 3 }
  },
  {
    $inc: {
      stock_qty: -3,
      reserved_qty: 3
    },
    $set: { status: "RESERVING" }
  }
);
~~~

Within the scope of the target document, these fields are updated in **one** atomic operation. A reader will never observe a half-updated state where this command wrote `stock_qty` without writing `reserved_qty`.

Compare with **two commands**:

~~~javascript
db.inventory_products.updateOne(
  { _id: "p-101" },
  { $inc: { stock_qty: -3 } }
);

db.inventory_products.updateOne(
  { _id: "p-101" },
  { $inc: { reserved_qty: 3 } }
);
~~~

If the process crashes between the two commands, the document will have reduced stock without increased reserved quantity. Another request could also interleave between the two calls. **Two separate atomic operations do not form one combined atomic operation**.

### 3.1. Filter conditions are part of correctness

If the filter only specifies `{ _id: "p-101" }`, two `$inc: { stock_qty: -3 }` commands can both match: stock 5 → 2 → −1. MongoDB does not automatically infer the "non-negative stock" invariant.

The `stock_qty >= 3` condition must reside **inside the write command** so the second request is rejected once the first reduces inventory. A prior read cannot protect this invariant.

### 3.2. Arrays and nested documents are also within one document

~~~javascript
db.carts.updateOne(
  { _id: "cart-101", tenantId: "tenant-a" },
  {
    $addToSet: { reservedSkus: "BOTTLE-500" },
    $set: { updatedBy: "checkout-service" }
  }
);
~~~

Both changes happen atomically on the same cart document. However, if the service then deducts stock on **another product document**, the cart-level guarantee **does not automatically extend** to the product.

Do not embed unbounded data into a single document solely to leverage atomicity: MongoDB has a **16 MiB** BSON document size limit, and an oversized/hot document can create contention.

## 4. Lost updates and time-of-check/time-of-use

A common pattern:

~~~java
InventoryProduct current = repository.findById("p-101")
        .orElseThrow();

if (current.getStock() >= 3) {
    current.setStock(current.getStock() - 3);
    repository.save(current);
}
~~~

Assume the entity does not use `@Version`. Two requests read the same old value and save the full entity state, potentially overwriting each other's results. Even when reading from the primary, data can still be modified by another request **after the read and before the write**.

Another error-prone sequence:

~~~java
if (!repository.existsById("external-101")) {
    repository.save(newEntity);
}
~~~

Two requests can both observe `existsById == false`. If uniqueness is required, you must use a **unique index** on the business key rather than relying on read-before-insert.

### 4.1. synchronized is not a distributed lock

~~~java
public synchronized void reserve(...) {
    // find, check, save
}
~~~

`synchronized` only locks threads passing through **the same instance in one JVM**. Multiple pods, jobs, workers, and other MongoDB connections can still write concurrently. This is not a general solution for multi-instance concurrency.

### 4.2. Atomicity and CAS are different

An update filtered only by `_id` is still atomic, yet does not prevent a stale update from overwriting newer state. **Compare-and-set (CAS)** means "only change if the state still matches expectations":

~~~javascript
db.orders.updateOne(
  { _id: "ord-101", tenantId: "tenant-a", status: "PENDING" },
  { $set: { status: "PAID" } }
);
~~~

If another request already transitioned the status to `CANCELLED`, the filter no longer matches. Not modifying the document is then **a valid CAS outcome**, not necessarily a database error.

## 5. Sample entity and repository

The examples use the `inventory_products` collection. The Java property `stock` maps to BSON `stock_qty`.

**InventoryProduct.java**

~~~java
package com.example.inventory;

import java.util.ArrayList;
import java.util.List;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "inventory_products")
public class InventoryProduct {
    @MongoId(FieldType.STRING)
    private String id;
    private String tenantId;
    private String status;

    @Field("stock_qty")
    private long stock;

    private List<String> appliedCommandIds;

    protected InventoryProduct() {}

    public InventoryProduct(
            String id, String tenantId, String status, long stock) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.stock = stock;
        this.appliedCommandIds = new ArrayList<>();
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public long getStock() { return stock; }
    public List<String> getAppliedCommandIds() {
        return appliedCommandIds;
    }

    public void setStock(long stock) { this.stock = stock; }
    public void setStatus(String status) { this.status = status; }
}
~~~

**InventoryProductRepository.java**

~~~java
package com.example.inventory;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface InventoryProductRepository
        extends MongoRepository<InventoryProduct, String> {
}
~~~

`@MongoId(FieldType.STRING)` stores `id` in `_id` as a String. `@Field("stock_qty")` defines the physical BSON name. `tenantId` provides business authorization scoping, yet **does not automatically filter** queries; the service must include the trusted tenant in filters.

The `appliedCommandIds` field is used in the single-document idempotency example. It is **not** a mechanism for storing unbounded request IDs in production.

## 6. Conditional update with MongoTemplate.updateFirst

**StockReservationService.java**

~~~java
package com.example.inventory;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService {
    private final MongoTemplate mongo;

    public StockReservationService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public boolean reserve(
            String authenticatedTenantId,
            String productId,
            long quantity) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || productId == null || productId.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid request");
        }

        Query query = Query.query(
                Criteria.where("id").is(productId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("status").is("ACTIVE")
                        .and("stock").gte(quantity));

        Update update = new Update()
                .inc("stock", -quantity);

        UpdateResult result = mongo.updateFirst(
                query, update, InventoryProduct.class);

        return result.getMatchedCount() == 1;
    }
}
~~~

An equivalent shell command:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

Because the method passes `InventoryProduct.class`, Spring Data has the metadata to translate Java property `stock` to `stock_qty`. When using raw shell/driver commands, you must write the actual BSON field name.

### 6.1. Interpreting the result

`getMatchedCount() == 1` means one document satisfied **the entire** filter and the write result was recorded per the write concern. When `matchedCount = 0`, it could be because:

- The ID does not exist;
- Another tenant, unauthorized;
- The product is not ACTIVE;
- Insufficient stock.

A 0 result **is not enough to distinguish the root cause**. If you need to classify into 404/409 or idempotent replay, you need an explicit contract and a safe post-command read/reconciliation step; do not use read-before-update to replace CAS protection.

### 6.2. Matched vs. modified

~~~java
long matched = result.getMatchedCount();
long modified = result.getModifiedCount();
~~~

With a non-zero `$inc`, a matched document typically actually changes. However, a `$set` assigning the already-present value can still yield `matched=1, modified=0`. If the business asks "was the condition accepted?", check **matched**; if it asks "did the BSON change?", check **modified**.

When the write concern is unacknowledged or a network error leaves the outcome uncertain, do not assume counts are always available or accurately reflect final state.

### 6.3. updateMulti is not equivalent to a single-document CAS

`updateMulti` can affect multiple documents. Each document is written atomically, yet there is **no all-or-nothing atomicity across the whole set** outside a transaction. For a reservation targeting one ID, use `updateFirst`/update by unique key so you do not accidentally modify multiple products.

## 7. findAndModify: returning the post-image of the exact operation

When an API needs to know the remaining stock right after reserving:

~~~java
import org.springframework.data.mongodb.core.FindAndModifyOptions;

Query query = Query.query(
        Criteria.where("id").is(productId)
                .and("tenantId").is(authenticatedTenantId)
                .and("stock").gte(quantity));

InventoryProduct after = mongo.findAndModify(
        query,
        new Update().inc("stock", -quantity),
        FindAndModifyOptions.options().returnNew(true),
        InventoryProduct.class);
~~~

With valid `productId`, `authenticatedTenantId`, and `quantity`, `after != null` is the **post-image** of the document found and modified in the same operation. Without a match, `after` is `null` in the non-upsert case.

Compare with:

~~~java
mongo.updateFirst(query, update, InventoryProduct.class);
InventoryProduct after = mongo.findById(
        productId, InventoryProduct.class);
~~~

This is **two commands**; another writer could update the document after `updateFirst` and before `findById`. The subsequently read object is not guaranteed to be the post-image of the initial update.

### 7.1. Before-image and after-image

`FindAndModifyOptions.options().returnNew(true)` requests the post-update object; by default the find-and-modify path may return the pre-update object. Set the option explicitly in code and tests. The return value here is an entity or null, **not an `UpdateResult` with counts**.

### 7.2. findAndModify does not cover other documents

After find-and-modify, if the service also updates `orders` or `shipments`, those changes fall outside the atomic operation just executed. If both must commit or roll back together, evaluate a transaction or another consistency workflow design.

## 8. CAS on status, version, and other invariants

Filtering by ID alone is not enough. A business state transition typically needs to check:

~~~javascript
db.orders.updateOne(
  {
    _id: "ord-101",
    tenantId: "tenant-a",
    status: "PENDING",
    expectedPaymentAmount: 150000
  },
  {
    $set: { status: "PAID" }
  }
);
~~~

This example assumes an `expectedPaymentAmount` field in the source document; the actual order schema must declare and validate this field before use. The condition preserves the expected invariant **at write time**, not just when the app read it earlier.

A CAS condition may check:

| Condition | Protects against |
|---|---|
| `status = PENDING` | Re-transitioning an already processed/cancelled state |
| `version = expectedVersion` | Overwriting a newer revision |
| `stock >= requested` | Letting stock go negative |
| `tenantId = authenticatedTenantId` | Writing to another tenant's resource |
| `requestId not yet processed` | Limiting re-application of the same command |

Not every condition fits into a single filter; an invariant spanning multiple documents or external APIs needs additional design. However, any condition that **can be checked atomically on the target document** should not be split into a separate Java read followed by an update.

## 9. Optimistic locking with @Version

Spring Data MongoDB supports `@Version`. When the framework processes `save` on a loaded entity via an optimistic-locking-enabled write path, an outdated version can be rejected instead of overwriting newer state.

**VersionedInventory.java**

~~~java
package com.example.inventory;

import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "versioned_inventory")
public class VersionedInventory {
    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;
    private long stock;

    @Version
    private Long version;

    protected VersionedInventory() {}

    public VersionedInventory(
            String id, String tenantId, long stock) {
        this.id = id;
        this.tenantId = tenantId;
        this.stock = stock;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public long getStock() { return stock; }
    public Long getVersion() { return version; }
    public void setStock(long stock) { this.stock = stock; }
}
~~~

**VersionedInventoryRepository.java**

~~~java
package com.example.inventory;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface VersionedInventoryRepository
        extends MongoRepository<VersionedInventory, String> {
}
~~~

Two copies of the entity with the same revision:

~~~java
VersionedInventory first = repository.findById("v-101")
        .orElseThrow();
VersionedInventory second = repository.findById("v-101")
        .orElseThrow();

first.setStock(4);
repository.save(first);

second.setStock(4);
// The second copy is stale: save may be rejected.
repository.save(second);
~~~

`repository` is a `VersionedInventoryRepository` bean. When the first update increments the version and write concern is acknowledged, the subsequent save using the old version will fail to match and can throw `OptimisticLockingFailureException`.

### 9.1. @Version does not replace stock invariants

Version detects that data changed **since the prior read**. It does not inherently know "stock must be >= 0", "only deduct if the order is ACTIVE", or "do not process payment twice". You must:

1. Validate invariants before the operation.
2. When a stale save fails, never report success.
3. If retrying, reload and **recompute the business decision** within bounded attempts.
4. Never retry by forcing the version or overwriting with a stale record.

### 9.2. Do not assume every update path respects @Version

Custom `MongoTemplate` updates, repository `@Update`, bulk writes, or the raw Java Driver may have different semantics from repository `save`. When explicit version CAS is needed:

~~~javascript
db.versioned_inventory.updateOne(
  {
    _id: "v-101",
    tenantId: "tenant-a",
    version: 7,
    stock: { $gte: 3 }
  },
  {
    $inc: {
      stock: -3,
      version: 1
    }
  }
);
~~~

Here the version filter and increment occur in **one** document write. With `MongoTemplate.Update` on a `@Version` entity, Spring Data may auto-increment version on some update paths if version is absent from the update; verify your version and **do not increment version twice**.

### 9.3. Optimistic locking requires an acknowledged write concern

To detect a matched count of 0 and report a stale object, the application needs an acknowledged write result. An unacknowledged write concern can silently lose the ability to detect optimistic locking failures. Do not disable acknowledgment just to boost throughput while still promising to prevent all lost updates.

## 10. Idempotency: atomic $inc does not prevent request replays

`$inc` on a single document is atomic, yet when a client retries a **business intent** such as "reserve 3 items", the command can be applied again.

~~~text
Client -> reserve 3
Server writes stock 10 -> 7
Response lost on network
Client retries as a new command
Server writes stock 7 -> 4
~~~

Each deduction was atomic, yet one intent reduced stock **twice**. Therefore, distinguish:

- **Atomicity:** a single command does not write halfway.
- **Idempotency:** replaying the same intent does not produce duplicate business effects.
- **Retryable writes:** the driver has a mechanism to retry certain operations under supported conditions, which is not a promise that all HTTP retries represent the same command.

### 10.1. Storing command markers in the same document

With a **bounded** command volume, one illustrative technique stores applied request IDs in `appliedCommandIds`:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 },
    appliedCommandIds: { $ne: "reserve-101" }
  },
  {
    $inc: { stock_qty: -3 },
    $addToSet: { appliedCommandIds: "reserve-101" }
  }
);
~~~

The "command not yet used" condition and both updates happen atomically on **one document**. If the command ID is resent concurrently, once one command succeeds, the other no longer matches `appliedCommandIds: { $ne: ... }`.

### 10.2. Java method reserveOnce

The following method is **added to `StockReservationService`** from section 6, reusing the `mongo` field and imports:

~~~java
public boolean reserveOnce(
        String authenticatedTenantId,
        String productId,
        long quantity,
        String commandId) {
    if (authenticatedTenantId == null
            || authenticatedTenantId.isBlank()
            || productId == null || productId.isBlank()
            || commandId == null || commandId.isBlank()
            || quantity <= 0) {
        throw new IllegalArgumentException("Invalid request");
    }

    Query query = Query.query(
            Criteria.where("id").is(productId)
                    .and("tenantId").is(authenticatedTenantId)
                    .and("status").is("ACTIVE")
                    .and("stock").gte(quantity)
                    .and("appliedCommandIds").ne(commandId));

    Update update = new Update()
            .inc("stock", -quantity)
            .addToSet("appliedCommandIds", commandId);

    UpdateResult result = mongo.updateFirst(
            query, update, InventoryProduct.class);
    return result.getMatchedCount() == 1;
}
~~~

Here a `false` result could mean duplicate command, insufficient stock, wrong tenant, or inactive status. If the API must **replay the original response on duplicate calls**, you must record the outcome per command ID or design an appropriate idempotency record. A boolean cannot express all of these states.

### 10.3. Do not store unbounded command IDs inside one document

An unbounded `appliedCommandIds` array makes the document grow, increases write cost, and can hit the **16 MiB** BSON limit. For high-volume systems, consider:

- A separate idempotency collection with a unique key and explicit retention;
- A transaction if the idempotency record and resource document must commit together;
- Stable event sequence/revision numbers and reconciliation checkpoints;
- Bounded history with pruning rules aligned to the retry contract.

Do not prune command markers prematurely while clients might still retry. Idempotency retention window and key scope are **business decisions**.

## 11. Two consecutive commands on the same document still have an intermediate state

A dangerous example:

~~~java
mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")),
        new Update().set("status", "RESERVED"),
        InventoryProduct.class);

// Process can crash or another writer can interleave here.

mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")),
        new Update().inc("stock", -3),
        InventoryProduct.class);
~~~

A possible timeline:

~~~text
T0: status = ACTIVE,   stock = 5
T1: update #1 runs -> status = RESERVED, stock = 5
T2: process stops abruptly
T3: update #2 never runs
~~~

Two commands modifying the same ID **do not automatically form a transaction**. If both fields belong to the same document, combine them:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    status: "ACTIVE",
    stock_qty: { $gte: 3 }
  },
  {
    $set: { status: "RESERVED" },
    $inc: { stock_qty: -3 }
  }
);
~~~

The combined command preserves the invariant in one operation. However, `status = RESERVED` on a **shared product** is not always the right model for concurrent bookings; a dedicated reservation entity may be needed. Atomicity does not replace proper aggregate/domain modeling.

### 11.1. Same Java method or same connection is not enough

Two calls using the same `MongoTemplate`, the same thread, the same ordinary client session, or the same HTTP request **do not have a transaction by default**. A Spring Service method is merely a code boundary, not a MongoDB atomicity boundary.

### 11.2. try/catch does not roll back the preceding command

~~~java
try {
    firstMongoWrite();
    secondMongoWrite();
} catch (RuntimeException exception) {
    // Catch does not automatically roll back firstMongoWrite().
}
~~~

Rollback requires a real transaction, or an intermediate-state/compensating-action model with retry and reconciliation mechanisms. A compensating operation can also fail, so it is not synonymous with an ACID transaction.

## 12. updateMany and BulkOperations: no whole-batch atomicity

A command:

~~~javascript
db.inventory_products.updateMany(
  { tenantId: "tenant-a", status: "ACTIVE" },
  { $set: { status: "INACTIVE" } }
);
~~~

can modify multiple documents. **Each document is updated atomically**, yet there is no all-or-nothing guarantee across **the entire document set** unless the operations run inside a transaction. Readers can observe some documents changed while others have not yet changed.

### 12.1. BulkOperations ORDERED is not a transaction

~~~java
BulkOperations bulk = mongo.bulkOps(
        BulkOperations.BulkMode.ORDERED,
        InventoryProduct.class);

bulk.updateOne(queryA, updateA);
bulk.updateOne(queryB, updateB);
bulk.execute();
~~~

This is an illustrative service fragment assuming `queryA`/`queryB` and `updateA`/`updateB` are already created, requiring `org.springframework.data.mongodb.core.BulkOperations`.

`BulkMode.ORDERED` governs **execution order and stopping on error**; it does not automatically roll back previously succeeded operations. `BulkMode.UNORDERED` can continue attempting independent writes even if one write fails; it does not create a transaction either.

Example:

~~~text
Insert A => succeeds
Insert B => duplicate key
Update C => depending on ordered/unordered, may not be attempted or may already run
~~~

If the application retries the entire batch containing `$inc`, operations A or C that already succeeded can be applied twice. Per-operation idempotency, tracking IDs, and reconciliation are needed.

### 12.2. MatchedCount does not equal input request count

An `updateMany` can match 100 documents and modify 95 documents. A bulk with 10 write models might match only 8 documents. These counts differ from **API call count**, **command count**, **input entity count**, and **completed business operations**. Read `UpdateResult`/`BulkWriteResult` with exact semantics.

### 12.3. Do not confuse bulk with cross-collection transactions

Even when a bulk batch is sent over the driver in fewer network round trips, **reducing round trips does not turn it into all-or-nothing**. Only a true transaction design provides a commit/rollback boundary for participating documents.

## 13. Unique indexes and upserts under contention

Two requests both want to create an order with business key (`tenantId`, `externalOrderId`):

~~~java
if (repository.findByExternalOrderId(externalId).isEmpty()) {
    repository.save(newOrder);
}
~~~

This is a check-before-write and does not protect against races. A MongoDB index is the actual source of guarantee:

~~~javascript
db.orders.createIndex(
  { tenantId: 1, externalOrderId: 1 },
  { unique: true, name: "uq_order_tenant_external_id" }
);
~~~

### 13.1. Upsert does not replace a unique index

~~~javascript
db.orders.updateOne(
  { tenantId: "tenant-a", externalOrderId: "ERP-101" },
  {
    $setOnInsert: {
      status: "PENDING",
      createdBy: "erp-sync"
    }
  },
  { upsert: true }
);
~~~

Without a proper unique index on the business key, concurrent upserts can create duplicate documents. A unique index prevents duplicate keys on the server, but code must handle duplicate-key exceptions and reconcile state after failure rather than relying solely on pre-checks.

### 13.2. Idempotent upsert requires defining field ownership

If an older source event arrives after a newer event, an upsert using `$set` without a revision guard can overwrite newer data. The atomicity of a single upsert does not automatically guarantee **event ordering**, **correct version**, or **non-repeating side effects**.

When importing from external systems, include:

1. A stable business key and unique index.
2. A reliable source revision/timestamp if events can arrive out of order.
3. Field ownership rules (which fields may the external source modify?).
4. An event/command ID to handle replays.
5. Classification rules for duplicate keys and uncertain outcomes after timeouts.

## 14. Money transfer example: two documents requiring a cross-document invariant

Suppose:

~~~text
Account A = 100,000 VND
Account B = 20,000 VND
Transfer 30,000 VND from A to B

Expected result:
  A = 70,000
  B = 50,000
  Total = 120,000
~~~

If using two separate updates:

~~~javascript
db.money_accounts.updateOne(
  { _id: "A", balance_vnd: { $gte: 30000 } },
  { $inc: { balance_vnd: -30000 } }
);

db.money_accounts.updateOne(
  { _id: "B" },
  { $inc: { balance_vnd: 30000 } }
);
~~~

A failure after debiting A and before crediting B causes **an imbalance**. Each document update was atomic, yet the "total balance conserved" invariant spans **two documents**.

### 14.1. Account entity

**MoneyAccount.java**

~~~java
package com.example.finance;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "money_accounts")
public class MoneyAccount {
    @MongoId(FieldType.STRING)
    private String id;
    private String tenantId;

    @Field("balance_vnd")
    private long balanceVnd;

    protected MoneyAccount() {}

    public MoneyAccount(
            String id, String tenantId, long balanceVnd) {
        this.id = id;
        this.tenantId = tenantId;
        this.balanceVnd = balanceVnd;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public long getBalanceVnd() { return balanceVnd; }
}
~~~

### 14.2. Transaction manager

In Spring Data MongoDB, you can configure `MongoTransactionManager`:

**MongoTransactionConfig.java**

~~~java
package com.example.finance;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
public class MongoTransactionConfig {
    @Bean
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

MongoDB transactions require a **supported replica set or sharded cluster**, plus properly configured sessions and transaction manager. Standalone MongoDB is not an appropriate environment for testing multi-document transactions. Ensure all related operations participate in the same transaction.

### 14.3. Transactional money transfer service

**MoneyTransferService.java**

~~~java
package com.example.finance;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MoneyTransferService {
    private final MongoTemplate mongo;

    public MoneyTransferService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional
    public void transfer(
            String authenticatedTenantId,
            String fromId,
            String toId,
            long amountVnd) {
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || fromId == null || fromId.isBlank()
                || toId == null || toId.isBlank()
                || fromId.equals(toId)
                || amountVnd <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        Query debitQuery = Query.query(
                Criteria.where("id").is(fromId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("balanceVnd").gte(amountVnd));
        UpdateResult debit = mongo.updateFirst(
                debitQuery,
                new Update().inc("balanceVnd", -amountVnd),
                MoneyAccount.class);

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Invalid source account or insufficient balance");
        }

        Query creditQuery = Query.query(
                Criteria.where("id").is(toId)
                        .and("tenantId").is(authenticatedTenantId));
        UpdateResult credit = mongo.updateFirst(
                creditQuery,
                new Update().inc("balanceVnd", amountVnd),
                MoneyAccount.class);

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Destination account not found");
        }
        // Spring commits the transaction when the method completes normally.
    }
}
~~~

In an **actually working MongoDB transaction**, if the credit fails to match and the method throws an unchecked exception, the transaction aborts and the debit rolls back. When it commits successfully, both changes belong to the same transaction boundary.

**This example is for learning atomicity/transactions and is not sufficient for a production transfer system.** You also need a transfer ID/idempotency, immutable ledger, authorization checks, overflow protection, currency handling, auditing, fraud prevention, and policies for transaction retry/unknown commit outcome.

## 15. Conditions for @Transactional to actually protect data

`@Transactional` is a Spring annotation, not database magic.

Conditions to verify:

1. A matching `MongoTransactionManager` is configured, without another transaction manager accidentally taking precedence.
2. The MongoDB topology supports transactions (compatible replica set/sharded cluster).
3. `MongoTemplate`/repository operations participate in the same session/transaction.
4. Transactions are activated through a Spring proxy/interceptor; **self-invocation** generally bypasses default transactional proxying.
5. Errors trigger rollback per configured rules. With unchecked exceptions in this example, rollback is the typical default behavior.
6. Transactions do not stay open too long and handle write conflicts, transient errors, and unknown commit results.

### 15.1. Transactions do not roll back external systems

If a service sends an email or calls a payment API mid-transaction, a MongoDB rollback cannot retract the sent email or HTTP request. A common pattern is **transactional outbox**:

~~~mermaid
flowchart LR
    A["Business transaction"] --> B["Write Order"]
    A --> C["Write Outbox event"]
    B --> D["Commit MongoDB transaction"]
    C --> D
    D --> E["Worker reads outbox"]
    E --> F["Publish with retry and dedup"]
    F --> G["Idempotent consumer"]
~~~

Even an outbox does not mean a message is delivered exactly once in all systems. A worker can publish and then crash before marking delivered; consumers require idempotency/deduplication.

### 15.2. Transactions are not automatically idempotent

A transfer request can **commit successfully** while the HTTP response is lost. A client retry starts a new transaction and transfers money **again** unless protected by a transfer ID.

~~~text
transaction = all-or-nothing for participating MongoDB operations
idempotency = a business intent is not applied twice
~~~

Both must be distinguished and are often combined.

### 15.3. Transactions have overhead

Multi-document transactions can increase latency, contention, memory usage, and the likelihood of write conflicts. Certain administrative operations, collection/index creations, or aggregation stages have restrictions inside transactions. Do not wrap every MongoDB operation unconditionally in a transaction just to feel safe.

If an invariant lives entirely within one document, **a conditional update** is usually simpler and has an easier-to-control failure boundary.

## 16. Write concern, read concern, and unknown outcomes

Distinguish:

- **Atomicity:** a single document is never half-written.
- **Write concern:** the acknowledgment/durability level requested by the client.
- **Read concern:** the level of data visibility allowed for a read.
- **Read preference:** the read target (primary/secondary...) and potential exposure to replication lag.

A conditional update command can complete on the server while the client never receives the response:

~~~text
Client sends updateOne($inc)
MongoDB executes update
Network connection drops before acknowledgment
Client observes timeout
Server may already have modified the data
~~~

**A timeout does not prove "the command did not run".** Retrying the whole business operation immediately after a timeout, especially with `$inc`, can apply the effect twice.

### 16.1. Retryable writes and application-level retries

The MongoDB Driver supports retryable writes for **certain command types** on suitable topologies/versions. However:

- An HTTP handler calling `updateFirst` again as **a new operation** is not treated by default as a driver retry of the previous operation.
- A debit → credit sequence does not become a single retryable write.
- A multi-document batch or transaction has its own error/retry rules.
- If a transaction commit outcome is unknown, retries must follow transaction and idempotency protocols rather than blindly re-issuing the entire transfer.

For financial or reservation flows, use a **command ID and durable state** to distinguish already processed, not yet processed, or needing reconciliation.

### 16.2. Read-after-write and secondary lag

Even after a successful update, a reader targeting a secondary may see stale data when replication lags behind. Atomicity does not mean every replica updates at the exact same instant. Define the API's consistency contract and configure appropriate read/write concerns, sessions, and read preferences.

### 16.3. Two reads do not prove the result of a write

~~~java
long before = repository.count();
performUpdate();
long after = repository.count();
~~~

The difference `after - before` is not `modifiedCount`; state updates do not change total document count, and concurrent tasks can interleave between reads. Use `UpdateResult` or `DeleteResult` to measure the effect of the write itself, and use readback/reconciliation for unknown outcomes.

## 17. Integration testing conditional updates on real MongoDB

Mocking a repository or `MongoTemplate` can verify that the service called `updateFirst`, yet does not prove two writers compete and MongoDB **re-evaluates the filter during the write**. You need integration tests with real MongoDB, such as Testcontainers. In Spring Boot 3.x, `@DataMongoTest` configures the test slice but **does not automatically start a MongoDB server**.

### 17.1. Two requests both reserving 3 from stock=5

**StockReservationIntegrationTest.java**

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

@DataMongoTest
@Import(StockReservationService.class)
class StockReservationIntegrationTest {
    @Autowired MongoTemplate mongo;
    @Autowired StockReservationService stock;

    private InventoryProduct saved() {
        return mongo.findById("p-101", InventoryProduct.class);
    }

    @BeforeEach
    void prepare() {
        // Perform only on an isolated test database.
        mongo.remove(new Query(), InventoryProduct.class);
        mongo.insert(new InventoryProduct(
                "p-101", "tenant-a", "ACTIVE", 5));
    }

    @Test
    void secondRequestFailsWhenStockIsInsufficient() {
        assertThat(stock.reserve("tenant-a", "p-101", 3)).isTrue();
        assertThat(stock.reserve("tenant-a", "p-101", 3)).isFalse();
        assertThat(saved().getStock()).isEqualTo(2L);
    }

    @Test
    void concurrentRequestsCannotBothReserveThree() throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try {
            Future<Boolean> a = pool.submit(() -> {
                ready.countDown();
                start.await();
                return stock.reserve("tenant-a", "p-101", 3);
            });
            Future<Boolean> b = pool.submit(() -> {
                ready.countDown();
                start.await();
                return stock.reserve("tenant-a", "p-101", 3);
            });

            assertThat(ready.await(5, TimeUnit.SECONDS)).isTrue();
            start.countDown();

            boolean aSucceeded = a.get(10, TimeUnit.SECONDS);
            boolean bSucceeded = b.get(10, TimeUnit.SECONDS);

            assertThat(aSucceeded ^ bSucceeded).isTrue();
            assertThat(saved().getStock()).isEqualTo(2L);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }

    @Test
    void wrongTenantOrInactiveStatusCannotChangeStock() {
        assertThat(stock.reserve("tenant-b", "p-101", 1)).isFalse();
        assertThat(saved().getStock()).isEqualTo(5L);

        mongo.updateFirst(
                Query.query(Criteria.where("id").is("p-101")),
                new Update().set("status", "INACTIVE"),
                InventoryProduct.class);

        assertThat(stock.reserve("tenant-a", "p-101", 1)).isFalse();
        assertThat(saved().getStock()).isEqualTo(5L);
    }

    @Test
    void repeatedCommandDoesNotDeductTwiceEvenWithEnoughStock() {
        assertThat(stock.reserveOnce(
                "tenant-a", "p-101", 1, "cmd-101")).isTrue();

        // 4 units left, enough to deduct 1 more, but the command is already stored.
        assertThat(stock.reserveOnce(
                "tenant-a", "p-101", 1, "cmd-101")).isFalse();

        assertThat(saved().getStock()).isEqualTo(4L);
        assertThat(saved().getAppliedCommandIds())
                .containsExactly("cmd-101");
    }
}
~~~

**Why assert with XOR?** The test does not control whether request A or B runs first; it only requires **exactly one request** to get `matchedCount = 1`, leaving final stock at 2 and non-negative. Asserting a specific thread must win would make the test scheduler-dependent and flaky.

**Why does the replay test use quantity=1?** If it still used quantity=3 when only 2 remained, the second request would also fail to match due to **insufficient stock**; that would not prove the command ID condition worked. Using quantity=1 ensures the second call **still has enough stock** and is rejected solely by the applied ID.

### 17.2. Verifying Java → BSON mapping

After inserting `InventoryProduct`, you can read the raw document:

~~~java
org.bson.Document raw = mongo.getCollection("inventory_products")
        .find(new org.bson.Document("_id", "p-101"))
        .first();

assertThat(raw).isNotNull();
assertThat(raw.containsKey("stock_qty")).isTrue();
assertThat(raw.containsKey("stock")).isFalse();
~~~

Spring Data typed `Query`/`Update` must reference Java properties and map properly to `stock_qty` on the server. When you need to verify the exact filter, use the MongoDB Java Driver `CommandListener` in tests and inspect the `update` BSON command.

### 17.3. Do not share the test database with production

`mongo.remove(new Query(), InventoryProduct.class)` deletes **all documents** in the collection. Only do this in an isolated test database/collection; parallel tests require explicit isolation. **Do not copy this @BeforeEach into an environment with real data.**

## 18. Testing @Version and distinguishing no-op updates

### 18.1. Testing optimistic locking

An integration test class can use `VersionedInventoryRepository` against test MongoDB:

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.dao.OptimisticLockingFailureException;

@DataMongoTest
class VersionedInventoryTest {
    @Autowired VersionedInventoryRepository repository;

    @BeforeEach
    void prepare() {
        // Isolated test database.
        repository.deleteAll();
        repository.save(new VersionedInventory(
                "v-101", "tenant-a", 5));
    }

    @Test
    void staleSaveIsRejected() {
        VersionedInventory a =
                repository.findById("v-101").orElseThrow();
        VersionedInventory b =
                repository.findById("v-101").orElseThrow();

        assertThat(a.getVersion()).isNotNull();
        assertThat(b.getVersion()).isEqualTo(a.getVersion());

        a.setStock(4);
        repository.save(a);
        b.setStock(4);

        assertThatThrownBy(() -> repository.save(b))
                .isInstanceOf(OptimisticLockingFailureException.class);
        assertThat(repository.findById("v-101")
                .orElseThrow().getStock()).isEqualTo(4L);
    }
}
~~~

The test requires an **acknowledged write concern**. Do not generalize from this test that every update written with the raw driver or `BulkOperations` automatically checks `@Version`.

### 18.2. Testing matchedCount and modifiedCount on a no-op $set

~~~java
UpdateResult noOp = mongo.updateFirst(
        Query.query(Criteria.where("id").is("p-101")
                .and("tenantId").is("tenant-a")),
        new Update().set("status", "ACTIVE"),
        InventoryProduct.class);

assertThat(noOp.getMatchedCount()).isEqualTo(1L);
assertThat(noOp.getModifiedCount()).isEqualTo(0L);
~~~

This snippet assumes a test environment seeded with an ACTIVE product, with `mongo` in scope and imports for `UpdateResult`/`Query`/`Criteria`/`Update`. Because `InventoryProduct` has no additional auditing/version fields, setting the same status again can be a no-op. If the framework's write/version path modifies another metadata field automatically, adjust the test to match actual data and semantics.

### 18.3. A post-update read only explains the error diagnostically

When `reserve` returns false, the API layer can re-read state to distinguish out-of-stock/INACTIVE/not-found. However, that read result could already have been changed by another writer after the update; it is **diagnostic information at a different point in time**, not atomic proof of why the original update failed to match.

If failure state must be determined under a strict contract, design an appropriate protocol/state machine/transaction rather than simply appending a `findById` afterward.

## 19. Testing transactions and mid-flight failures

### 19.1. Do not test transactions on standalone and assume success

A transaction rollback test requires a MongoDB **replica set** or topology compatible with multi-document transactions, `MongoTransactionManager` configuration, and `MongoTemplate`/repositories participating in the session:

~~~text
Given:
  A.balanceVnd = 100000
  B.balanceVnd = 20000

When:
  MoneyTransferService.transfer(tenant-a, A, B, 30000)

Then:
  A.balanceVnd = 70000
  B.balanceVnd = 50000
~~~

Failure scenario:

~~~text
Given:
  A.balanceVnd = 100000
  Account B does not exist

When:
  transfer(A -> B, 30000) throws an unchecked exception

Then:
  A.balanceVnd remains = 100000
  no un-rolled-back debit
~~~

If run on standalone where transactions are unsupported, that is an **environment error**; do not remove `@Transactional` and claim the test proves multi-document atomicity.

### 19.2. Test correctness before testing throughput

A transfer can be fast and concurrent while still being wrong if it only debits without crediting on failure. Test:

1. Successful commit updates both accounts accurately.
2. Missing destination account causes transaction to roll back the debit.
3. Transferring to the same account or invalid amount is rejected.
4. Insufficient balance never makes the balance negative.
5. Two concurrent transfers from the same source follow write conflict/retry policy.
6. Duplicate transfer ID does not create a second transfer on retry.
7. Unknown commit result is reconciled before re-issuing.

For items 6–7, the `MoneyTransferService` example above **has not yet implemented idempotency/ledger**, so architecture and tests must be added before using it for real transactions.

### 19.3. Two requests or two servers?

Tests using two threads in one JVM are a starting point, yet insufficient for:

- Multiple application replicas/pods;
- Failover/replication lag;
- Timeout after write but before acknowledgment;
- Unknown transaction commit outcome;
- Application crash mid-operation;
- Event replay days later;
- Data modified by another service not sharing the same conventions.

Each failure mode requires its own verification strategy rather than collapsing everything into "already tested concurrently".

## 20. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming MongoDB is atomic so read → save is safe | Lost update | CAS or `@Version` |
| Reading stock first then `$inc` without sufficient-stock filter | Oversell/negative stock | `stock >= quantity` in filter |
| Treating `synchronized` in one pod as a distributed lock | Races across multiple JVMs | Place conditions in MongoDB |
| Filtering only by ID, omitting tenant | Modifies another tenant's data | Tenant from auth context in write query |
| Treating two updates on the same document as one transaction | Intermediate state exposed | Combine changes into one update |
| Assuming `updateMany` is atomic across the whole collection | Partial state visible | Transaction if all-or-nothing is needed |
| Assuming `BulkMode.ORDERED` rolls back writes prior to an error | Partial success | Transaction/idempotency/reconcile |
| Always treating `matched=0` as not found | Wrong 404 when out of stock or status changed | Classify per contract |
| `matched=1` means the whole workflow succeeded | Email/order/shipment may remain incomplete | Separate technical and business results |
| `save` full unversioned entity based on stale state | Overwrites newer data | Optimistic locking/partial updates |
| Assuming all custom updates automatically check `@Version` | Stale writes slip through | Explicit version CAS |
| Retrying `$inc` as a new request after timeout | Deducts/adds twice | Idempotency key and reconciliation |
| Unbounded command ID array | Resource bloat, hitting 16 MiB | Separate idempotency collection/retention |
| Relying on `existsBy...` for uniqueness | Race inserts duplicates | Unique index |
| Assuming upsert prevents duplicates without unique index | Can create two documents | Unique index on business key |
| Adding `@Transactional` without manager/topology | Rollback does not work | Configure session/manager and test replica set |
| Sending email inside a transaction expecting rollback | External side effect persists | Outbox/idempotent consumer |
| Assuming timeout means the server definitely did not write | Retry causes duplicates | Distinguish unknown outcome |
| Reading a secondary, seeing stale state, thinking write failed | Wrong conclusion | Configure read/write concerns |
| Testing only with Mockito mocks | Does not prove MongoDB CAS/concurrency | Real integration tests |

## 21. Practice exercises

**Exercise 1 — Three atomicity scopes.** Compare one `updateOne` changing 3 fields on a single document, two `updateOne` calls on the same document, and one `updateMany` across 100 documents. Identify where intermediate states can be observed.

**Exercise 2 — Lost update.** Seed stock=5, load two snapshots both with stock=5, and use unversioned read-modify-save. Write a timeline showing both requests reporting success while stock drops only to 2.

**Exercise 3 — Atomic stock reservation.** Use `MongoTemplate.updateFirst` filtering by tenant, status, and stock. Two requests each deducting 3 from 5 must produce exactly one `matched=1` and non-negative final stock.

**Exercise 4 — findAndModify.** Return the post-image after updating. Compare with update-then-find and describe an interleaving where the subsequent read is no longer the exact post-image of the first command.

**Exercise 5 — Status CAS.** Allow an order to transition `PENDING → PAID` only once. Run a competing cancel request; analyze matched=0 and how to return 409/404/idempotent replay per contract.

**Exercise 6 — Optimistic locking.** Create a `@Version Long` entity, load two copies, save sequentially, and verify the stale save fails; propose a bounded retry.

**Exercise 7 — Idempotent command.** Use `$addToSet` + `$inc` in a single update with a condition that `appliedCommandIds` does not yet contain the command ID. Prove that retrying when stock is still sufficient does not deduct a second time.

**Exercise 8 — Idempotency history size.** Analyze how many command IDs can accumulate in one document. Design moving to a separate collection with a unique key, retention, and transactions when needed.

**Exercise 9 — Multiple updates.** Create a method that sets status then increments stock; inject an intentional exception between the two calls. Measure the remaining state; then combine both fields into one update.

**Exercise 10 — Bulk partial success.** Create a bulk batch with insert A, duplicate-unique-key insert B, and update C. Compare ORDERED vs. UNORDERED and design retries keyed by operation ID.

**Exercise 11 — Transfer transaction.** Configure a replica set, `MongoTransactionManager`, and `@Transactional`. Test successful transfer, insufficient funds, and missing destination rollback.

**Exercise 12 — Unknown commit result.** Describe a lost response after the server writes. Design a transfer ID/idempotency record so a retry request does not transfer funds a second time.

**Exercise 13 — Outbox.** Diagram updating Order and Outbox in one transaction, with a worker publishing events with retry. Explain why consumers still need deduplication.

**Exercise 14 — Read consistency.** On a test replica set, compare read-after-write from primary vs. secondary by read preference. Explain how atomicity differs from replication freshness.

**Exercise 15 — Load test.** Seed stock=50; send 100 concurrent requests, each deducting 1. Assert exactly 50 requests succeed and final stock is 0. Measure contention/latency and verify all other write paths also preserve the invariant.

## 22. Key takeaways

**A single write command on a single MongoDB document is atomic at the document level.** If an invariant lives within one document, combine **conditions in the filter** and **changes in the same update**: `stock >= quantity` with `$inc` is a classic example. `findAndModify` returns the pre/post-image of that exact operation; `@Version` detects stale entities on write paths with optimistic locking.

**Two or more consecutive commands — even on the same document, in the same Java method, on the same thread, or in the same HTTP request — do not automatically form a transaction.** `updateMany` and bulk writes can still produce partial success because each document is updated atomically on its own. If an invariant must protect **multiple documents**, use a properly configured MongoDB transaction or an eventual-consistency workflow with explicit state machine/compensation/outbox/reconciliation.

Finally, **atomicity does not replace idempotency, uniqueness, authorization, acknowledgment, or retry policies**. A successful update does not prove the entire business workflow completed; a timeout does not prove the server did not write. Interpret `matchedCount`/exceptions by their exact semantics, avoid blind `$inc` retries, and verify with integration tests on real MongoDB before deploying to production.
