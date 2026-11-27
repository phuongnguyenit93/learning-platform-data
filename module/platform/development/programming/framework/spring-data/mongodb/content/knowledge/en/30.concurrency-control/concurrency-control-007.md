# Decrementing stock with quantity conditions and atomic inc

## 1. Scenario: two customers concurrently buying the last item

An e-commerce application stores inventory per SKU in MongoDB. Product **BOOK-101** has only **1** unit left. Almost simultaneously, two customers submit requests to buy one unit each.

If code handles it by reading first and writing afterward:

~~~text
Initial stock: stock = 1

Request A: reads stock = 1
Request B: reads stock = 1
Request A: checks 1 >= 1, writes stock = 0, returns success
Request B: checks 1 >= 1, writes stock = 0, returns success

Database result: stock = 0
Business result: confirmed selling 2 units when only 1 existed
~~~

This bug is a variant of **race condition / lost update**: reading, checking, and writing occur at separate times, so both requests can act on stale state.

A proper fix at the **single MongoDB document** level combines the **stock condition** and **decrement operation** into **the same atomic update operation**:

~~~javascript
db.inventories.updateOne(
  {
    _id: ObjectId("507f1f77bcf86cd799439011"),
    tenantId: "shop-a",
    active: true,
    stock: { $gte: NumberLong("1") }
  },
  {
    $inc: { stock: NumberLong("-1") }
  }
);
~~~

On each update, MongoDB only selects a document that still satisfies **stock >= quantity** at write execution time. With initial stock = 1, only one request can decrement to 0; the other request no longer matches the condition and is not deducted.

The lesson **Decrementing stock with quantity conditions and atomic inc** belongs to the **Concurrency Control** chapter of the **SPRING_DATA_MONGODB** module. The module uses Spring Data MongoDB to connect, map documents, and operate via MongoTemplate or repositories; this technique relates directly to query design, indexes, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

1. Explain why **read → check → save** is unsafe under concurrent load.
2. Write a **stock >= qty** filter and **Update.inc("stock", -qty)** in a single command.
3. Use **MongoTemplate.updateFirst** and read **UpdateResult** to confirm success.
4. Use **findAndModify** when you need the remaining stock balance immediately after the update.
5. Distinguish single-document atomicity from multi-document transactions.
6. Properly handle quantity validation, multi-tenancy, unavailable stock, retries, and idempotency.
7. Extend to **stock reservation**, ReactiveMongoTemplate, and real concurrency testing.

## 2. Sample data and invariant boundaries

Collection **inventories**:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  sku: "BOOK-101",
  stock: NumberLong("8"),
  reserved: NumberLong("0"),
  active: true,
  updatedAt: ISODate("2025-06-01T08:00:00Z")
}
~~~

In this lesson:

- **stock** is the number of units **available for allocation/sale**.
- **reserved** is the number of units currently held for pending orders.
- **active** determines whether the product is eligible for allocation.
- **tenantId** scopes data ownership.

A fundamental invariant is:

\[
\text{stock}\ge0,\qquad \text{reserved}\ge0.
\]

When the model supports reservations, physical quantity can equal **stock + reserved** if those two fields represent the only two states. In reality, there are also damaged items, in-transit stock, locked items, accounting counts, or multiple warehouses; clearly define **available stock** before writing update logic.

### 2.1. Java entity

~~~java
package com.example.inventory;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventories")
public record InventoryDocument(
    @Id ObjectId id,
    String tenantId,
    String sku,
    long stock,
    long reserved,
    boolean active,
    Instant updatedAt
) {}
~~~

**@Document** specifies the collection, and **@Id** maps id to BSON _id. Quantity/stock values use **long** for integer counts; if inventory allows fractional units, use the smallest indivisible unit or a controlled exact numeric model rather than arbitrary binary floating-point numbers.

### 2.2. Choosing an identifier key

In the examples, requests update by **_id** and **tenantId**. If an API uses SKU instead of ID, enforce uniqueness per tenant via a compound unique index:

~~~javascript
db.inventories.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true, name: "uk_inventory_tenant_sku" }
);
~~~

Never assume **sku** is globally unique across a multi-tenant system. With multiple warehouses, the business key typically also includes **warehouseId** or an appropriate partition identifier.

## 3. Why can reading then saving oversell?

Here is an example **not to use** when multiple requests update the same product:

~~~java
public void unsafeDecrease(ObjectId id, long quantity) {
    InventoryDocument inventory = repository.findById(id)
        .orElseThrow();

    if (inventory.stock() < quantity) {
        throw new IllegalStateException("Out of stock");
    }

    InventoryDocument changed = new InventoryDocument(
        inventory.id(),
        inventory.tenantId(),
        inventory.sku(),
        inventory.stock() - quantity,
        inventory.reserved(),
        inventory.active(),
        inventory.updatedAt()
    );

    repository.save(changed);
}
~~~

The issue is not Java syntax, but **the gap between reading and writing**:

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant B as Request B
    participant M as MongoDB
    A->>M: findById -> stock=1
    B->>M: findById -> stock=1
    A->>A: 1 >= 1
    B->>B: 1 >= 1
    A->>M: save stock=0
    B->>M: save stock=0
    Note over A,B: Both may confirm the sale succeeded
~~~

**save() does not turn two operations (find and save) into an atomic check-and-write transaction.** If the entity uses @Version, Spring Data can detect stale saves via optimistic locking; however, conflicts and retries must still be handled properly. Without versioning, saving from a stale snapshot can overwrite other changes.

Rather than reading first, MongoDB lets you put the **precondition directly into the update command filter**. That is the central technique of this lesson.

## 4. Atomic formula: stock >= qty + negative $inc

For a purchase quantity **q > 0**:

\[
\text{If } stock\ge q \quad\Rightarrow\quad stock'=stock-q.
\]

If the condition fails, the document is not updated:

\[
\text{If } stock<q \quad\Rightarrow\quad \text{no match, no decrement}.
\]

MongoDB:

~~~javascript
const productId = ObjectId("507f1f77bcf86cd799439011");
const requested = NumberLong("3");

const result = db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    active: true,
    stock: { $gte: requested }
  },
  {
    $inc: { stock: NumberLong("-3") },
    $currentDate: { updatedAt: true }
  }
);

printjson(result);
~~~

With initial stock = 8 and no other writers, stock becomes 5. If only 2 remain, the query does not match; MongoDB will not deduct into negative values just because a request was sent.

### 4.1. Condition and update must be in the same command

~~~javascript
// UNSAFE when multiple writers run concurrently:
const item = db.inventories.findOne({ _id: productId });
if (item.stock >= 3) {
  db.inventories.updateOne(
    { _id: productId },
    { $inc: { stock: -3 } }
  );
}
~~~

The Java/JavaScript condition only checks previously read data, which may no longer be current. The final update command **carries no stock >= 3 condition**, so two requests can both still deduct.

### 4.2. Why is $inc better than $set for counters?

~~~javascript
// Can overwrite another writer's value if computedStock is stale.
{ $set: { stock: computedStock } }
~~~

~~~javascript
// Relative increment/decrement on the server's current value.
{ $inc: { stock: -3 } }
~~~

**$inc** updates a numeric field relative to the document state at execution time; it does not require the caller to calculate a new stock value from an old snapshot. **Yet negative $inc alone is not enough:** it can still drive stock negative unless paired with **stock >= quantity** in the filter.

### 4.3. Document-level atomicity

MongoDB guarantees atomicity for a single write operation on **one document**, even when modifying multiple fields of that document. When writers contend on the same document, the update's filter condition is evaluated against consistent write-time state, so **conditional decrement** prevents two operations from over-deducting.

This **does not automatically ensure atomicity across multiple documents**, such as deducting inventory and creating an order in another collection.

## 5. MongoTemplate.updateFirst: minimal correct Java example

~~~java
package com.example.inventory;

import com.mongodb.client.result.UpdateResult;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public class InventoryService {

    private final MongoTemplate mongoTemplate;

    public InventoryService(MongoTemplate mongoTemplate) {
        this.mongoTemplate = mongoTemplate;
    }

    public boolean tryDecreaseStock(
            ObjectId productId,
            String authenticatedTenantId,
            long quantity) {

        if (productId == null) {
            throw new IllegalArgumentException("Product ID is required");
        }
        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                "Quantity must be positive");
        }

        Query query = Query.query(
            Criteria.where("_id").is(productId)
                .and("tenantId").is(authenticatedTenantId)
                .and("active").is(true)
                .and("stock").gte(quantity)
        );

        Update update = new Update()
            .inc("stock", -quantity)
            .currentDate("updatedAt");

        UpdateResult result = mongoTemplate.updateFirst(
            query,
            update,
            InventoryDocument.class
        );

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Inventory update was not acknowledged");
        }

        return result.getModifiedCount() == 1;
    }
}
~~~

The most critical part:

~~~java
Criteria.where("_id").is(productId)
    .and("tenantId").is(authenticatedTenantId)
    .and("active").is(true)
    .and("stock").gte(quantity);

new Update().inc("stock", -quantity);
~~~

**The exact same MongoDB request carries both the condition and the decrement**. There is no prior `findById` deciding whether stock is sufficient.

### 5.1. Why use updateFirst?

Because the filter targets **_id**, at most one document can match since _id is unique in a normal collection. **updateFirst** clearly expresses the intent to modify a single inventory document.

With a filter containing only status/tenant, `updateFirst` might update an arbitrary matching document, which is wrong if the caller needs to deduct a specific SKU. Always include the ID or a uniquely guaranteed business key in the filter.

### 5.2. Do not enable upsert

**updateFirst** in this example updates an existing document; it **never auto-upserts** a new inventory record when unmatched.

If switched to an API with **upsert=true**, out-of-stock or not-found cases could insert unintended documents. A stock deduction request must never create an inventory record with negative stock or missing fields.

### 5.3. Should you use document ID or SKU?

A stable ID works well when the caller already holds the internal inventory ID. SKU works if the repository enforces a compound unique constraint by tenant/warehouse. Either way, **tenant permissions must be enforced server-side** and **stock >= quantity must reside in the same update**.

### 5.4. updatedAt

**currentDate("updatedAt")** uses MongoDB Server time to stamp the change. If the app uses auditing callbacks, do not assume MongoTemplate direct updates fire them like `repository.save`. Decide explicitly which fields update server-side and which belong to a separate audit pipeline.

## 6. Reading UpdateResult: 0 is not necessarily a database error

MongoDB returns update results containing fields such as:

- **matchedCount**: number of documents matching the filter.
- **modifiedCount**: number of documents actually modified per command contract.
- **upsertedId**: populated if upsert was used and created a new document.
- **wasAcknowledged**: whether the write operation was acknowledged.

Examples:

| Scenario | matchedCount | modifiedCount | Meaning |
| --- | ---: | ---: | --- |
| stock=8, q=3, update succeeds | 1 | 1 | Deducted exactly 3 |
| stock=2, q=3 | 0 | 0 | Insufficient stock |
| ID does not exist | 0 | 0 | Not found |
| Wrong tenant | 0 | 0 | Unauthorized or not visible in scope |
| active=false | 0 | 0 | Allocation not allowed |

Because `quantity` is always positive and the update subtracts stock, if the command is acknowledged and matches in this model, `stock` must change. **modifiedCount=1** serves as a simple success signal.

### 6.1. What to do when modifiedCount=0?

Never immediately return sensitive details like:

~~~text
"You have permission for this SKU, and another store has stock=2"
~~~

An update=0 can stem from several causes: not found, tenant mismatch, inactive, insufficient stock, or data changed concurrently. For public APIs, return a generic outcome like **409 Conflict / unavailable** or a **cannot-reserve business error** per contract.

If needed for internal diagnostics, you can re-read the document **after verifying authorization**. Keep in mind that read shows state observed after the update, not absolute proof of the cause at update time.

### 6.2. Difference between "0" and an exception

- **0 modified** on an acknowledged command: no document satisfied the update conditions.
- **Exception / timeout / network error**: the caller may not know whether the server applied the update.

**Never treat a timeout as out-of-stock**, because the decrement might have succeeded before the response was lost. Uncertain outcomes must be resolved via operation IDs/idempotency and reconciliation, not blind retries.

### 6.3. What you should not infer from a single number

`modifiedCount=1` **does not prove** the order was created, payment succeeded, events were published, or an external warehouse confirmed. It only confirms a single inventory update on MongoDB.

## 7. findAndModify: getting the balance after deduction

Many APIs want to return **remaining stock** immediately after the operation. Running `updateFirst` then `findById` lets another request deduct in between, so the balance read is **not guaranteed to be the value right after your deduction**.

Spring Data MongoDB offers **findAndModify** to apply filter + update and return the pre-update or post-update document per options.

~~~java
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public InventoryDocument decreaseAndReturnNewStock(
        MongoTemplate template,
        ObjectId productId,
        String tenantId,
        long quantity) {

    if (productId == null || tenantId == null
            || tenantId.isBlank() || quantity <= 0) {
        throw new IllegalArgumentException("Invalid request");
    }

    Query query = Query.query(
        Criteria.where("_id").is(productId)
            .and("tenantId").is(tenantId)
            .and("active").is(true)
            .and("stock").gte(quantity)
    );

    Update update = new Update()
        .inc("stock", -quantity)
        .currentDate("updatedAt");

    return template.findAndModify(
        query,
        update,
        FindAndModifyOptions.options()
            .returnNew(true)
            .upsert(false),
        InventoryDocument.class
    );
}
~~~

- When matched and updated: returns the **new post-update InventoryDocument**.
- When unmatched: returns **null** (for this overload).
- When the operation errors: throws an exception rather than masking errors with null.

### 7.1. Do not compute post-update balance by subtracting from an old read

Never compute `stockAfter = preRead.stock - quantity` and return it as committed state. Under concurrency, the old value may already be outdated.

**findAndModify(returnNew=true)** returns the document from the exact executed operation, ideal when the response requires post-decrement balance. Another write can still occur immediately afterward; the response does not hold a long-term exclusive lock on inventory.

### 7.2. Projections reduce payload size

When inventory documents contain many large fields, consider returning only needed fields via Query/options projections and a DTO. Never save a partial `InventoryDocument` back via `repository.save`, as that can overwrite unread fields.

### 7.3. updateFirst or findAndModify?

| Need | Typically suitable API |
| --- | --- |
| Only need to know if deduction succeeded | updateFirst + UpdateResult |
| Need remaining stock immediately after update | findAndModify returnNew=true |
| Need to modify multiple inventory documents in one transaction | MongoDB transaction / appropriate reserve workflow |
| Only reading balance without modifying data | Standard find/query |

**findAndModify does not make multi-document operations atomic**; its strength here is combining filter, update, and returning state for **one document**.

## 8. Why does conditional update prevent overselling?

With stock=1 and two requests both asking for quantity=1:

~~~mermaid
sequenceDiagram
    participant A as Checkout A
    participant B as Checkout B
    participant M as MongoDB
    A->>M: updateOne(_id=X, stock >= 1; $inc stock:-1)
    B->>M: updateOne(_id=X, stock >= 1; $inc stock:-1)
    M-->>A: modifiedCount=1
    Note over M: stock becomes 0
    M-->>B: modifiedCount=0
    Note over A,B: Only one checkout succeeds in deducting stock
~~~

Which request wins is not guaranteed by the example. Yet because each operation only writes when its condition holds, two requests **cannot both deduct when only one unit remains**, assuming no other writer adds stock in between.

### 8.1. The rule holds only when every deduction path obeys it

If another service still runs:

~~~javascript
db.inventories.updateOne(
  { _id: productId },
  { $inc: { stock: -100 } }
);
~~~

then the `stock >= 0` invariant can be violated. Ensure **all outbound stock paths** use proper conditions or controlled administrative policies. Data safety cannot be proven from one method if other writers ignore the rule.

### 8.2. $inc does not replace schema validation

MongoDB allows numeric updates and handles BSON numeric types per server rules. Do not assume every document stores `stock` as a non-negative long just because the Java entity declares `long`.

Migrations or direct operations can leave null, missing, String, double, or negative values. Include:

- Validation when creating inventory records.
- Database schema validation if strong invariants are required.
- Auditing/migration of legacy data.
- Restricted write privileges for services and jobs authorized to adjust stock.

## 9. Quantity validation: guard subtraction at input

**Never allow `quantity = 0` or negative `quantity`** into a stock-deduction path.

~~~java
if (quantity <= 0) {
    throw new IllegalArgumentException(
        "Quantity must be positive");
}
~~~

Why?

~~~text
quantity = 0  -> $inc: {stock: 0}; no deduction, yet may trigger other side effects
quantity = -3 -> $inc: {stock: +3}; turns a purchase request into a stock restock
~~~

Beyond positivity, enforce a **reasonable business maximum** per request:

~~~java
if (quantity > 1000) {
    throw new IllegalArgumentException(
        "Quantity exceeds policy limit");
}
~~~

The number 1000 is purely illustrative, not a MongoDB limit. Actual limits depend on SKU, warehouse, and customer rules.

### 9.1. Overflow and Long.MIN_VALUE

Once **quantity > 0** is enforced, **-quantity** cannot hit `Long.MIN_VALUE` negation issues and cannot overflow in that direction. However, **stock additions** or **increasing reserved** can still overflow if values exceed `long` bounds.

Choose numeric types, maximum bounds, and schema validation carefully. Do not use `int` if stock can exceed `Integer.MAX_VALUE`, and do not use `double` for exact integer counts.

### 9.2. Never let clients dictate the tenant

The `authenticatedTenantId` parameter must come from an **authenticated principal/session/token**, or be verified by server policy before calling the update.

The tenant filter is a database-level guard; it does not replace **authorization**. If a client can pass someone else's `tenantId`, adding `tenantId` to the query is not enough to prevent cross-tenant modifications.

## 10. SKU, multiple warehouses, and unique indexes

If each SKU spans multiple warehouses:

~~~javascript
{
  tenantId: "shop-a",
  warehouseId: "HCM-01",
  sku: "BOOK-101",
  stock: NumberLong("8")
}
~~~

then the business key may be **tenantId + warehouseId + sku**.

~~~javascript
db.inventories.createIndex(
  { tenantId: 1, warehouseId: 1, sku: 1 },
  { unique: true }
);
~~~

Calling `updateFirst` by only `tenantId+sku` when multiple warehouses exist can update the wrong warehouse's document. **Atomicity only protects the selected document; it does not decide which warehouse is business-correct.**

### 10.1. Filtering by _id and tenant usually identifies unambiguously

In systems using ObjectId, **_id already has a unique index**, so querying by `_id` selects at most one document. Tenant, active, and stock filters add security and business preconditions.

Do not create indexes blindly just because a filter adds tenant/active/stock. Use **explain, cardinality, and workload** to evaluate extra indexes, especially when `_id` lookup is already selective.

### 10.2. Updating by SKU may need a compound index

If a use case mainly looks up by **tenantId + sku + stock >= q**, an index leading with `tenantId` and `sku` helps locate the document. Since SKU is unique per tenant, appending `stock` to that index may not justify the extra write cost; measure it.

## 11. Reserving stock: decrementing available and incrementing reserved in one document

In real checkout flows, payment may not be captured immediately. Instead of permanently deducting stock on checkout click, the app **reserves** a quantity for the in-flight order.

With `stock = available` and `reserved = held quantity`:

\[
\text{stock}'=\text{stock}-q,\qquad
\text{reserved}'=\text{reserved}+q.
\]

Because both fields live **in the same document**, MongoDB can update both atomically:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    active: true,
    stock: { $gte: 2 }
  },
  {
    $inc: {
      stock: -2,
      reserved: 2
    },
    $currentDate: { updatedAt: true }
  }
);
~~~

Java:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(productId)
        .and("tenantId").is(tenantId)
        .and("active").is(true)
        .and("stock").gte(quantity)
);

Update update = new Update()
    .inc("stock", -quantity)
    .inc("reserved", quantity)
    .currentDate("updatedAt");

UpdateResult result = mongoTemplate.updateFirst(
    query, update, InventoryDocument.class
);
~~~

On a successful update, **stock+reserved** stays constant, assuming both started valid and no rogue writer broke rules. This updates **reservation counters** only—it does not yet prove a unique reservation record exists for each order.

### 11.1. Upon payment success

Once items are reserved, the reservation can transition to **consumed** and decrement `reserved` accordingly, depending on your physical-count model:

~~~text
Before reserve: stock=8, reserved=0
After reserve 2: stock=6, reserved=2
After consume:   stock=6, reserved=0
~~~

Thus two items have left `stock+reserved` after consume. **Do not deduct `stock` a second time at payment capture** if `stock` was already decremented at reservation.

### 11.2. Upon reservation cancellation

Return the stock:

\[
stock'=stock+q,\qquad reserved'=reserved-q.
\]

Never write an unconditional stock-addition update just because a "cancel" message arrived. Ensure the reservation is actually in **RESERVED** state so it cannot be cancelled twice; decrementing `reserved` must guard `reserved >= q`, though that quantity check **alone does not prevent double-refunding the same order**.

### 11.3. TTL does not automatically release stock

If a reservation has `expiresAt` and MongoDB TTL deletes the reservation document, **MongoDB TTL does not automatically add stock back or reduce reserved**. You need an explicit expiration workflow: conditionally transition the reservation state, restore the counters, and handle retries/idempotency.

## 12. Maintaining consistency across multiple documents

Conditional decrement safely updates **one inventory document**. Yet checkout typically involves:

1. Deducting stock on product A.
2. Deducting stock on product B.
3. Creating the order and order items.
4. Writing reservation or payment intent records.
5. Emitting events to external systems.

These steps do not become a single atomic operation simply because each inventory update uses `$inc`.

### 12.1. Multi-document transactions

When the MongoDB deployment supports transactions and Spring Data configures **MongoTransactionManager**, a transaction can group related MongoDB writes.

~~~java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void reserveOrder(
        String tenantId,
        OrderRequest request) {

    for (OrderLine line : request.lines()) {
        boolean ok = inventoryService.tryDecreaseStock(
            line.inventoryId(),
            tenantId,
            line.quantity()
        );

        if (!ok) {
            throw new OutOfStockException(line.inventoryId());
        }
    }

    orderRepository.insert(
        createReservedOrder(tenantId, request)
    );
}
~~~

Structural illustration: **OrderRequest, OrderLine, OutOfStockException, orderRepository, and createReservedOrder** are business components you define separately. In practice:

- Calls must go through the Spring transactional proxy.
- MongoDB operations must participate in the same transaction/session.
- Deployment must support transactions.
- If any item is out of stock, throw an appropriate exception to roll back.
- Transactions can hit write conflicts and require a controlled retry strategy.

**Do not enable transactions for every single-document deduction unnecessarily.** Single-document conditional updates are already atomic; transactions add overhead and runtime limits.

### 12.2. Payments and HTTP calls outside MongoDB

A MongoDB transaction **cannot roll back** a succeeded call to a payment gateway or external API. To link order/inventory/events, consider **outbox** or a saga/reservation workflow with explicit intermediate states and idempotent compensation steps.

### 12.3. Ordering multi-SKU updates

For multi-line orders, establish a deterministic ordering to reduce collisions and unnecessary contention. Still, sorting SKUs does not replace a transaction; if deducting the second SKU fails, you still need proper rollback/compensation for the first SKU.

## 13. MongoDB atomic updates vs. @Version optimistic locking

Spring Data MongoDB supports **@Version** for optimistic locking on entities:

~~~java
import org.springframework.data.annotation.Version;

@Document(collection = "inventories")
public record VersionedInventory(
    @Id ObjectId id,
    String tenantId,
    long stock,
    @Version Long version
) {}
~~~

Repository **save(entity)** with a matching version detects when the entity was changed by another writer. When stale, Spring Data throws **OptimisticLockingFailureException** per operation contract and write concern.

**This is a different mechanism from `stock >= qty + $inc`.**

| Goal | Mechanism |
| --- | --- |
| Never deduct beyond current stock | `stock >= qty` in filter and negative `$inc` |
| Never overwrite a changed document version | `@Version`/expectedVersion |
| Conditional status/tenant update | Put predicate in the same update |
| Commit/roll back multiple documents together | Transaction |

### 13.1. Do you need @Version for atomic decrements?

To enforce `stock >= 0` when all writers use proper conditional updates, **you do not need to read version first**. Checking version can actually increase conflict rates when multiple writers want to deduct while plenty of stock remains.

However, if other flows modify multiple related inventory fields, versioning can be useful. With MongoTemplate updates, know that Spring Data may handle incrementing version on updates depending on entity/library version. **Never assume version is automatically checked against an expected version unless the filter includes version**.

### 13.2. If you must check expectedVersion

~~~java
Query query = Query.query(
    Criteria.where("_id").is(productId)
        .and("tenantId").is(tenantId)
        .and("stock").gte(quantity)
        .and("version").is(expectedVersion)
);

Update update = new Update()
    .inc("stock", -quantity);
~~~

This is a conditional update with **both stock and version conditions**. If update=0, the cause could be insufficient stock or version mismatch. If business logic must distinguish them, perform a controlled readback; never infer the exact cause from `modifiedCount` alone.

## 14. Improper retries can deduct stock twice

Suppose warehouse stock=10 and a request wants to deduct quantity=2:

~~~text
Client sends request attempt 1
MongoDB applies update successfully: stock=8
Network drops before client receives response
Client retries same request attempt 2
MongoDB still sees stock>=2: deducts again to stock=6
~~~

**Conditional updates prevent negative stock, yet do not prevent the same request from being applied twice** while enough stock remains. These are two distinct dimensions of correctness:

| Issue | Primary solution |
| --- | --- |
| Two independent requests compete for the last unit | Atomic `stock >= qty + negative $inc` |
| One request is replayed after a timeout | **Idempotency key** and recorded operation outcome |
| Stock deducted yet order creation fails | Transaction or saga/compensation |
| Payment event published twice | Outbox, event ID, idempotent consumer |

### 14.1. Distinguishing driver retryable writes from application retries

The MongoDB driver and server support **retryable writes** for qualifying operations. However, **an HTTP request resent as a fresh request** does not automatically reuse the driver's previous transaction statement identifier.

Therefore, never use "the driver has retryable writes" as a reason to skip API/order-level idempotency. If the application invokes the service again as a new operation, you need a mechanism preventing duplicate business effects.

### 14.2. Never blindly retry when outcome is uncertain

~~~java
// Avoid: timeout can happen after server already deducted stock.
for (int i = 0; i < 3; i++) {
    try {
        return inventoryService.tryDecreaseStock(id, tenant, qty);
    } catch (RuntimeException error) {
        // Retrying without request ID or state verification.
    }
}
~~~

This snippet is dangerous because the second pass can deduct more stock. Moreover, it catches every `RuntimeException` without distinguishing input errors, network errors, or data errors.

If the driver/server returns a write error guaranteed not to have executed, the app can follow a technical retry path per contract. When **it is unknown whether the command committed**, use a request identifier and reconciliation workflow.

## 15. Idempotency key: binding stock deduction to a single request

Each reservation or checkout attempt should have a unique **requestId**, for example:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439099"),
  tenantId: "shop-a",
  requestId: "checkout-2025-000123",
  inventoryId: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberLong("2"),
  status: "RESERVED",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Unique index:

~~~javascript
db.inventory_reservations.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uk_reservation_tenant_request" }
);
~~~

### 15.1. Why isn't checking exists(requestId) enough?

~~~text
Request A: checks requestId does not exist
Request B: checks requestId does not exist
Request A: deducts stock
Request B: deducts stock
Request A/B: one side's duplicate reservation insert fails
~~~

Without a transaction or matching design, **a unique index on reservations alone cannot automatically undo stock deductions already executed in another collection**.

### 15.2. Transaction model for reservations

With a multi-document MongoDB transaction:

1. Receive authenticated **tenantId**, **requestId**, validated `inventoryId` and `quantity`.
2. Check or attempt creating the uniquely keyed idempotency/reservation record.
3. Deduct inventory via **conditional $inc** inside the same transaction.
4. Mark the reservation RESERVED and commit only if the decrement succeeded.
5. If out of stock, abort the transaction and return the business outcome.
6. On duplicate `requestId`, read the existing record and **compare payload** (SKU/quantity) to verify it truly represents the same request.
7. If commit outcome is unknown, look up by `requestId` before attempting re-execution.

~~~mermaid
flowchart TD
    A["Receive tenant + requestId + inventoryId + qty"] --> B["Begin transaction"]
    B --> C["Ensure unique idempotency record"]
    C -->|Duplicate| D["Verify existing request outcome"]
    C -->|New| E["Conditional $inc: stock >= qty"]
    E -->|No match| F["Abort, report unable to reserve"]
    E -->|Success| G["Save reservation/order in same transaction"]
    G --> H["Commit"]
    H --> I["Return result by requestId"]
~~~

**Essential point:** the idempotency policy must cover both **the inventory decrement and the business record**. Never perform a separate unique insert without handling the case where decrement succeeded yet the record was not saved.

### 15.3. Key collision is not always "success"

If a client mistakenly reuses `requestId` while changing `quantity` from 2 to 10, do not return the old result as if the two requests were identical. The idempotency record must store a fingerprint/key fields to verify payload consistency.

### 15.4. Do not store unbounded request IDs in one inventory document

You might think of appending `requestId` to an array to deduplicate inside the update itself. Yet an unbounded array of request IDs bloats the inventory document, risking the BSON size limit and write amplification.

A separate reservation/idempotency collection with transactions or a well-designed workflow is much more manageable at scale.

## 16. Releasing reservations must be idempotent

An order-cancellation message can be delivered more than once. If every delivery runs:

~~~javascript
db.inventories.updateOne(
  { _id: productId },
  { $inc: { stock: 2, reserved: -2 } }
);
~~~

then the second execution can **over-credit stock** and push `reserved` negative, even though the first already completed.

A proper design requires a reservation state machine:

~~~text
NEW -> RESERVED -> CONSUMED
                 -> CANCELLED
                 -> EXPIRED
~~~

Permit only a valid transition from **RESERVED** to **CANCELLED/EXPIRED**, and only after that transition succeeds perform the stock restoration once, inside a transaction or equivalent idempotent/compensating mechanism.

### 16.1. Transactional approach

- Update reservation from RESERVED to CANCELLED conditioned on `status=RESERVED`.
- If `modifiedCount=1`, restore the inventory's `stock`/`reserved` counters.
- If `modifiedCount=0`, do not restore; verify whether the reservation was already processed or does not exist.
- Commit both MongoDB changes in the same transaction when cross-document invariants require it.

### 16.2. When transactions cannot be used

You need a saga/state machine with **operation IDs**, intermediate states, and crash recovery between steps. Never write a naive cron job that "sees expired and adds stock" without a durable marker proving whether restoration already ran.

## 17. Error handling and HTTP responses

An API service must distinguish **bad input**, **unable to reserve**, **uncertain outcome**, and **system failure**.

| Scenario | Suggested response |
| --- | --- |
| quantity <= 0 | 400 Bad Request |
| Malformed productId | 400 Bad Request |
| Unauthenticated tenant | 401 Unauthorized or 403 per policy |
| Product missing or belongs to another tenant | 404/403 per non-disclosure policy |
| Insufficient stock, inactive product | 409 Conflict or 422 per API contract |
| Duplicate requestId with identical payload | Return recorded result; do not deduct again |
| Duplicate requestId with different payload | 409 Conflict |
| Network timeout after write command | Mark outcome uncertain; look up by requestId |
| Unrecoverable database error | 5xx, telemetry; do not turn into out-of-stock |

These are **API design suggestions**, not mandatory Spring Data MongoDB HTTP mappings. What matters is avoiding losing technical truth by turning every exception into "insufficient stock".

### 17.1. Never leak cross-tenant inventory levels

If a user passes another tenant's ID, do not reply with details like "shop-b has 12 units left". Scope the tenant filter in the update, enforce authorization beforehand, and return neutral responses to prevent data enumeration.

### 17.2. Metrics do not replace business state

Measure:

- Number of accepted decrement requests.
- Number of requests failing the condition.
- Conflicts / duplicate idempotency keys.
- Timeouts / unknown outcomes.
- Update latency per SKU/warehouse while protecting sensitive data.

Metrics help track hotspots and errors, yet must never replace durable order/reservation state.

## 18. ReactiveMongoTemplate: identical principles, different API

In WebFlux stacks, use **ReactiveMongoTemplate** and let the caller subscribe:

~~~java
package com.example.inventory;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public class ReactiveInventoryService {

    private final ReactiveMongoTemplate template;

    public ReactiveInventoryService(ReactiveMongoTemplate template) {
        this.template = template;
    }

    public Mono<Boolean> tryDecreaseStock(
            ObjectId productId,
            String authenticatedTenantId,
            long quantity) {

        if (productId == null || authenticatedTenantId == null
                || authenticatedTenantId.isBlank() || quantity <= 0) {
            return Mono.error(
                new IllegalArgumentException("Invalid request")
            );
        }

        Query query = Query.query(
            Criteria.where("_id").is(productId)
                .and("tenantId").is(authenticatedTenantId)
                .and("active").is(true)
                .and("stock").gte(quantity)
        );

        Update update = new Update()
            .inc("stock", -quantity)
            .currentDate("updatedAt");

        return template.updateFirst(
            query, update, InventoryDocument.class
        ).map(result -> {
            if (!result.wasAcknowledged()) {
                throw new IllegalStateException(
                    "Inventory update was not acknowledged");
            }
            return result.getModifiedCount() == 1;
        });
    }
}
~~~

**Mono<Boolean>** emits true/false only once subscribed and completed. Atomic update semantics are enforced by MongoDB Server regardless of whether Java uses blocking threads or reactive streams.

### 18.1. Do not block on the WebFlux event loop

~~~java
// Avoid inside reactive request handlers:
Boolean ok = reactiveService
    .tryDecreaseStock(id, tenant, quantity)
    .block();
~~~

Compose with **flatMap/map** or return the `Mono` to the controller. Blocking reduces request concurrency and can cause event-loop errors.

### 18.2. Do not manually subscribe twice

~~~java
// Wrong: can trigger two updates for the same business request.
Mono<Boolean> decrement =
    reactiveService.tryDecreaseStock(id, tenant, quantity);

decrement.subscribe();
return decrement;
~~~

When the caller subscribes the second time, MongoDB can receive two decrement operations. **Mono does not automatically provide idempotency**. Maintain a single subscription lifecycle and use `requestId` for retries when needed.

### 18.3. Reactive findAndModify

~~~java
Mono<InventoryDocument> updated =
    reactiveTemplate.findAndModify(
        query,
        update,
        FindAndModifyOptions.options()
            .returnNew(true)
            .upsert(false),
        InventoryDocument.class
    );
~~~

When the filter misses, `ReactiveMongoTemplate` typically emits **Mono.empty()**. If business logic needs distinct outcomes, use **switchIfEmpty** or an explicit result type rather than treating empty as success.

### 18.4. Reactive transactions

When updating inventory and reservations in a reactive MongoDB transaction, configure **ReactiveMongoTransactionManager** and use reactive transaction boundaries. Never use blocking `@Transactional` expecting reactive operations to enlist automatically when sessions are not bound properly.

## 19. Indexes and performance under concurrency

An inventory update by **_id** uses the default `_id` index to find the document. For:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    stock: { $gte: 2 }
  },
  { $inc: { stock: -2 } }
);
~~~

MongoDB locates by `_id` and evaluates tenant/stock on that single document. A compound index **{_id,tenantId,stock}** is unnecessary; extra indexes add write amplification without meaningful lookup benefit.

### 19.1. Updating by tenant + SKU

For queries using **tenantId + sku**, a compound unique index:

~~~javascript
db.inventories.createIndex(
  { tenantId: 1, sku: 1 },
  { unique: true }
);
~~~

both enforces the business key and supports fast lookup of the inventory document. If stock is tracked per warehouse, include `warehouseId` matching the unique key.

### 19.2. Do not index stock out of habit

Stock changes on nearly every checkout. Indexing `stock` adds update overhead on every decrement. Only index `stock` if an actual **query workload** demonstrably requires it, such as listing in-stock SKUs with a specific filter and sort.

### 19.3. Hot documents

A flash-sale SKU may have thousands of writers updating the same document. Even though atomic, concurrent writes to one document compete for resources.

If p95/p99 latency spikes:

- Measure updates/sec, matched/modified counts, write conflicts, and latency.
- Consider queueing/reservation throttling to smooth load.
- Eliminate redundant writers and unnecessary application retries.
- Evaluate partitioning by warehouse/lot if **real business rules** allow it.

**Sharding does not remove contention if every request still writes to one document for the same SKU.** Partitioning must pair with an allocation policy so combined partitions cannot oversell.

## 20. Write concern, failover, and limits of acknowledged results

A **modifiedCount=1** result reflects a write acknowledged under the active write concern. It does not mean every replica holds the data permanently across every failover scenario.

When high durability is required:

- Pick an appropriate **write concern** (e.g., majority) per deployment policy.
- Understand rollback possibilities for non-majority-committed writes on primary failover.
- Never treat a 200 HTTP response as proof external systems have received the stock state.
- Use idempotency/operation logs and reconciliation to recover when commit outcomes are uncertain.

**Write concern does not turn multi-document updates into a transaction** and does not replace `stock >= qty`.

### 20.1. Reading after write from another replica

If stock is deducted on primary and immediately read from a lagging secondary, the read may miss the latest update depending on read preference/read concern. When an API needs the balance **immediately after decrement**, **findAndModify returnNew(true)** is safer than updating and then issuing a separate read elsewhere.

### 20.2. Telemetry and business state

During rollbacks/failovers, metrics may have already counted a previously reported success. Critical business flows need durable reservation/order records and reconciliation rather than relying solely on monitoring counters.

## 21. Atomicity does not mean stock is preserved forever

Conditional decrement solves **not deducting more than available at write time**. It does not solve every scenario:

- Physical goods damaged but not yet recorded.
- Two separate warehouse systems out of sync.
- Expired reservations not yet released.
- Admins editing stock from stale screens.
- Orders cancelled after deduction.
- Duplicate payment webhooks received.

Thus an inventory model must combine order/reservation states, auditing, stock adjustments, and reconciliation tools.

### 21.1. Never use unguarded $set from admin screens

An admin screen reads `stock=10`; meanwhile a checkout deducts to 9. If the admin saves the stale form with:

~~~javascript
{ $set: { stock: 10 } }
~~~

it overwrites the valid checkout change. For stock adjustments, use **delta `$inc`** or **compare-and-set** with expected version/current value, plus audit trails, authorization, and operator confirmation.

### 21.2. Inbound stock also needs idempotency

If the same receiving note is processed twice and both execute **$inc stock:+100**, inventory inflates erroneously. **$inc is atomic yet does not prevent replaying restock events**. The same requestId/unique operation principle applies to inbound as well as outbound movements.

## 22. Bulk updates do not replace multi-document transactions

Spring Data MongoDB supports **BulkOperations** to execute batches efficiently:

~~~java
mongoTemplate.bulkOps(
    BulkOperations.BulkMode.ORDERED,
    InventoryDocument.class
);
~~~

Each **updateOne** inside a bulk batch can carry `stock >= qty` and negative `$inc` to protect **each individual inventory document**. However, the batch itself lacks multi-document atomicity; if one item fails or misses, preceding items may already be persisted.

| Approach | Primary guarantee |
| --- | --- |
| `updateFirst` with `_id + stock>=q` | Single-document atomicity |
| `findAndModify` with conditions | Single-document atomicity plus returned state |
| `bulkOps` with multiple `updateOne` | Reduces multi-command overhead, **not all-or-nothing** |
| MongoDB transaction | Groups supported MongoDB writes to commit/roll back together |
| Saga / compensation | Orchestrates across systems, recovering/compensating per workflow |

Do not assume **BulkMode.ORDERED** rolls back previously written items when a later item fails.

## 23. Handling missing, mistyped, and invalid schema data

Some legacy documents may omit `stock`, or have `stock = null`:

~~~javascript
{ _id: productId, tenantId: "shop-a", stock: null }
~~~

MongoDB **$inc** requires the existing field to be a valid numeric type; on `null` it can error, and on missing fields an unconditional update creates the field with the delta value.

In this lesson, **stock: {$gte: positive quantity}** prevents matching typical missing/null documents instead of creating negative stock. Still, never treat it as a substitute for:

- Schema validation.
- Migrating old documents.
- BSON type enforcement and numeric bounds.
- Testing malformed data.

### 23.1. Database-level validation

To protect even against writers outside Spring Data, define a **MongoDB collection validator** requiring `stock` to be a non-negative integer, `reserved` non-negative, and required fields properly typed. Design valid BSON constraints compatible with existing data and roll out via controlled migrations.

Validators do not enforce request idempotency or order states; those invariants span multiple documents and workflows.

### 23.2. Avoid unit mismatches

If `stock` counts **individual units**, `quantity` must use the same unit. Never mix `stock=100` grams with `quantity=2` packs in a direct comparison and `$inc`. Standardize units/pack sizes and convert before building filters/updates.

## 24. Integration test: 20 requests competing for 5 items

A unit test mocking `MongoTemplate` only verifies the service constructed the expected Query/Update; it **does not prove** MongoDB enforces `stock>=q` properly under concurrent writers.

A thorough integration test should:

1. Insert inventory with `stock=5`.
2. Prepare **20 tasks** each attempting to deduct `quantity=1`.
3. Use a `CountDownLatch` so they start nearly simultaneously.
4. Invoke **the actual service** using `MongoTemplate.updateFirst`.
5. Count `true` results.
6. Read actual `stock` after all tasks finish.
7. Assert exactly **5** requests succeeded and final `stock` is **0**.
8. Clean up fixtures only in the dedicated test MongoDB.

### 24.1. JUnit 5 template with @DataMongoTest

~~~java
package com.example.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.bson.types.ObjectId;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
class ConcurrentStockDecrementTest {

    @Autowired
    MongoTemplate template;

    @Test
    void neverSellsMoreThanStockUnderConcurrentRequests()
            throws Exception {

        ObjectId id = new ObjectId();
        String tenant = "TEST-" + UUID.randomUUID();
        InventoryService service = new InventoryService(template);

        template.insert(new InventoryDocument(
            id,
            tenant,
            "CONCURRENT-BOOK",
            5L,
            0L,
            true,
            Instant.parse("2025-06-01T09:00:00Z")
        ));

        int requests = 20;
        ExecutorService workers =
            Executors.newFixedThreadPool(requests);
        CountDownLatch ready = new CountDownLatch(requests);
        CountDownLatch go = new CountDownLatch(1);

        try {
            List<Future<Boolean>> results = new ArrayList<>();

            for (int i = 0; i < requests; i++) {
                results.add(workers.submit(() -> {
                    ready.countDown();
                    go.await();
                    return service.tryDecreaseStock(
                        id, tenant, 1L
                    );
                }));
            }

            assertThat(ready.await(15, TimeUnit.SECONDS))
                .isTrue();
            go.countDown();

            int accepted = 0;
            for (Future<Boolean> future : results) {
                if (future.get(30, TimeUnit.SECONDS)) {
                    accepted++;
                }
            }

            assertThat(accepted).isEqualTo(5);

            InventoryDocument after = template.findById(
                id, InventoryDocument.class
            );

            assertThat(after).isNotNull();
            assertThat(after.stock()).isEqualTo(0L);
            assertThat(after.reserved()).isEqualTo(0L);
        } finally {
            go.countDown();
            workers.shutdownNow();
            template.remove(
                Query.query(Criteria.where("_id").is(id)),
                InventoryDocument.class
            );
        }
    }
}
~~~

**Run only against a test MongoDB instance**, such as a Testcontainers environment with a compatible MongoDB version. The test omits container setup to keep focus on the logic; test connection configuration must be supplied by the project.

### 24.2. Why use a latch?

Running 20 sequential requests would also allow 5 to succeed without creating real contention pressure. **CountDownLatch** aligns tasks to start on the same signal.

It still cannot guarantee every thread executes on the exact same CPU cycle, yet provides far better contention coverage than a sequential loop.

### 24.3. Correctness criteria for concurrency tests

If initial stock is **N**, every request asks for `quantity=1`, and no restocks happen concurrently, then:

\[
\text{successCount}\le N,\quad stock_{\mathrm{final}}=N-\text{successCount}.
\]

In the example with 20 requests and no infrastructure errors, we expect **successCount=5** and final stock=0. If the test hits timeouts/exceptions, classify and fail on those errors instead of treating them silently as `false` updates.

### 24.4. Limitations of this test

The test proves contention across concurrent **conditional decrements on the same document** in test MongoDB. It **does not prove**:

- No double decrement when an HTTP request is retried.
- Inventory + order committing together in a transaction.
- Idempotent reservation cancellation.
- Actual p99 throughput under thousands of requests/sec.
- Consistency with external warehouse systems.

Those requirements need dedicated tests of their own.

## 25. Boundary testing: out-of-stock, tenant, and quantity

For the same `InventoryService`, include tests for:

| Case | Expectation |
| --- | --- |
| stock=3, quantity=3 | modifiedCount=1, stock=0 |
| stock=3, quantity=4 | No update, stock remains 3 |
| stock=0, quantity=1 | No update, stock remains 0 |
| active=false, stock=10 | No update |
| Mismatched tenantId | No update, no stock leakage |
| Non-existent ID | No update |
| quantity=0 | IllegalArgumentException, no update sent |
| quantity=-1 | IllegalArgumentException, stock does not increase |
| quantity exceeds policy | Rejected before update |
| Missing/null/mistyped stock | Not treated as valid positive stock; migration/validation needed |
| Network error on update | Not silently converted to false or blindly retried |
| Resent requestId | Does not deduct again if already processed |

### 25.1. Insufficient stock test example

~~~java
@Test
void doesNotDecrementWhenQuantityExceedsStock() {
    ObjectId id = new ObjectId();
    String tenant = "TEST-" + UUID.randomUUID();

    template.insert(new InventoryDocument(
        id, tenant, "BOOK-LOW", 2L, 0L, true, Instant.now()
    ));

    try {
        InventoryService service = new InventoryService(template);

        boolean accepted =
            service.tryDecreaseStock(id, tenant, 3L);

        assertThat(accepted).isFalse();

        InventoryDocument after = template.findById(
            id, InventoryDocument.class
        );
        assertThat(after).isNotNull();
        assertThat(after.stock()).isEqualTo(2L);
    } finally {
        template.remove(
            Query.query(Criteria.where("_id").is(id)),
            InventoryDocument.class
        );
    }
}
~~~

This method belongs **inside the same ConcurrentStockDecrementTest class** from the previous section, where `template` and shared imports are already available.

### 25.2. Testing tenant enforcement

Insert an `InventoryDocument` for tenant A, then call the service as tenant B with the same `ObjectId`. Expect `false` and unchanged stock. Then call as tenant A to confirm only the authenticated tenant can deduct.

### 25.3. Idempotency testing differs from concurrency testing

Sending **the same requestId** twice is not two independent purchases. Tests must:

1. Deduct stock and record the reservation on the first call.
2. Resend the exact same `requestId`/payload.
3. Verify the same reservation/result is returned.
4. Verify stock decreased only once.
5. Send the same `requestId` with a different payload and verify conflict detection.

This test requires the reservation/transaction layer or full idempotency workflow; simply calling `tryDecreaseStock` twice will not recognize the duplicate request.

## 26. Diagnosing issues under concurrent load

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Negative stock | A writer uses `$inc` without `stock>=q` | Audit all write paths, add validation and migration |
| Two checkouts succeed when 1 item remained | read-check-save or condition outside update | Use conditional atomic decrement |
| `modifiedCount=0` despite UI showing stock | Concurrent writer just deducted, wrong tenant/status, or stale UI cache | Inspect filter and post-write state |
| `modifiedCount=1` yet no order exists | Operations span two collections without transaction/workflow | Transaction, outbox, or saga |
| Same order deducted twice | HTTP retry, duplicate webhook, missing idempotency | RequestId/unique reservation and workflow |
| Timeout after update then retry loses extra stock | Unknown outcome treated as failure | Check operation log before retrying |
| Cancelling one order adds stock twice | Release lacks reservation state check | Idempotent state transition |
| Negative reserved | Multiple releases or missing `reserved>=q` guard | Conditional state, validation, transaction |
| Writes fail with write conflict | Multiple writers contending inside transactions | Backoff retry and idempotency |
| p99 spikes on hot SKU | Contention on a single inventory document | Load shedding, queueing, sensible partitioning |
| Slow update queries | Missing suitable lookup index | Inspect query plan, lookup key, indexes |
| Admin adjustment overwrites recent checkout | Used `$set` from stale snapshot | Delta update or CAS/version |
| Reactive deducts twice | Double subscription on write publisher | Return Mono with single lifecycle, idempotency |
| Expired session fails to restore stock | TTL merely deleted reservation record | Expiration workflow + compensation |
| Read-after-write sees stale stock | Replica lag / read preference | `findAndModify returnNew` or fitting read policy |
| Cross-warehouse mismatch | Separate documents without allocation policy | Multi-warehouse design and transaction/saga |

### 26.1. Practical investigation workflow

1. Confirm the **business invariant**: does `stock` mean available or physical?
2. List all inventory write sources (checkout, import, cancel, admin, migration).
3. Inspect whether actual updates combine **stock >= qty and negative $inc in one command**.
4. Verify queries include exact tenant, ID/SKU/warehouse, and status.
5. Inspect `UpdateResult` and distinguish **0** from exceptions/timeouts.
6. Check whether a requestId/idempotency ledger exists.
7. Across multiple documents, verify transaction/session or compensation workflow.
8. Check indexes, hot SKUs, and transaction durations.
9. Reproduce with concurrent tests, duplicate requests, and uncertain network/commit failures.
10. Optimize performance only afterward; never drop preconditions for throughput.

## 27. Key design questions

### 27.1. What if restocking and deducting happen concurrently?

Restocking via `$inc stock:+q` and deducting via conditional `$inc stock:-q` both target the same document, so the server serializes them atomically. A deduction succeeds or misses depending on ordering relative to the restock. This is sensible if newly received goods are immediately sellable.

If incoming goods require inspection before sale, do not add directly to available `stock`; model a separate inventory state.

### 27.2. Should you always use findAndModify to return stock?

No. If the caller only needs to know whether deduction succeeded, `updateFirst + UpdateResult` suffices and avoids returning the full entity. Use `findAndModify` when the post-update balance is part of the API contract.

### 27.3. Should you wait until payment completes before deducting?

Depends on requirements. If payment takes a long time, not reserving can let stock sell out mid-payment. A **reserve → consume/cancel/expire** model is usually cleaner, though it requires transactions/idempotency/cleanup.

### 27.4. Can @Version replace the stock>=q condition?

`@Version` detects changes between read and write on supported operations, yet without logic validating stock on reload and proper retries, it **does not automatically enforce the business invariant**. Conditional decrement directly expresses the invariant and is typically simpler for counter updates.

### 27.5. Is a transaction needed for a single decrement?

No, if the goal is solely conditional updates on one inventory document. MongoDB already provides atomicity for one operation on one document. Transactions are needed when coordinating multiple documents/collections to commit or roll back together.

### 27.6. Can upsert be used to deduct stock for a new SKU?

Unsuitable for this model. If inventory does not exist, a deduction should never auto-create a document with negative values. Create inventory through a dedicated inbound workflow with validation and unique keys.

## 28. Practice exercises

### Exercise 1: spot the race condition

A service reads `stock=2` and, if enough, calls `save(stock-1)`. Two concurrent requests both buy 2 items—what can go wrong?

**Answer:** Both evaluate against `stock=2` and report success; stale saves can write a value that fails to reflect total units sold. Move `stock>=quantity` directly into the atomic update command.

### Exercise 2: write MongoDB updateOne

Deduct 3 units for `productId` only when sufficient stock remains and `active=true`:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    active: true,
    stock: { $gte: 3 }
  },
  { $inc: { stock: -3 } }
);
~~~

**Explanation:** filter and update execute in one write operation.

### Exercise 3: Java MongoTemplate

Fill in the two key expressions:

~~~java
Query query = Query.query(
    Criteria.where("_id").is(id)
        .and("tenantId").is(tenant)
        .and("stock").gte(quantity)
);

Update update = new Update()
    .inc("stock", -quantity);
~~~

**Answer:** `gte(quantity)` in `Query` and negative `inc` in `Update`.

### Exercise 4: insufficient stock

Current stock=2, quantity=3. What `modifiedCount` does an `updateFirst` with `stock>=quantity` and negative `$inc` return?

**Answer:** 0 when acknowledged with no other writers; stock stays unchanged. Do not call this a driver error.

### Exercise 5: reading balance after write

An API must return the exact stock value produced by this deduction. Should it run `updateFirst` then `findById`?

**Answer:** Prefer **findAndModify(returnNew=true)** to get the state immediately after that exact operation. A separate read might observe a subsequent update.

### Exercise 6: negative quantity

If `quantity=-5` and code runs `inc("stock", -quantity)`, what happens?

**Answer:** `$inc` adds 5 to stock. Validate `quantity>0` before constructing queries/updates.

### Exercise 7: tenant

A `shop-a` user sends an `inventoryId` belonging to `shop-b`. Is filtering only by `_id` safe?

**Answer:** No. Enforce authorization and server-side tenant constraints in the update; never trust client-supplied `tenantId`.

### Exercise 8: reserved stock

Stock=10, reserved=0; reserve 4 units. After the atomic update, what should both fields be?

**Answer:** stock=6, reserved=4, via a single update **$inc stock:-4, reserved:+4**.

### Exercise 9: cancelling twice

If a reservation is already cancelled, may a second cancel callback add stock back again?

**Answer:** No. Restore only when the transition `RESERVED→CANCELLED` succeeds; requires a transaction/workflow with idempotency.

### Exercise 10: retry timeout

The client receives no response even though the server may have deducted stock. Should it resend the update without a `requestId`?

**Answer:** Do not retry blindly. Use an idempotency key and reconcile operation state; resending can deduct again.

### Exercise 11: @Version

An entity has `@Version`, yet a `MongoTemplate.updateFirst` method filters only by ID, tenant, and stock. Will the update automatically reject any stale `expectedVersion`?

**Answer:** No. If version compare-and-set is required, put `expectedVersion` into the filter or use an API with an appropriate version contract; do not confuse auto-incrementing version with checking expectedVersion.

### Exercise 12: multiple SKUs

Checkout successfully deducts SKU A, then SKU B is out of stock. Does `updateOne` on A roll back automatically?

**Answer:** No. Requires a multi-document transaction or saga with compensation and idempotency.

### Exercise 13: reactive

What return type does `ReactiveMongoTemplate.updateFirst` produce in the example, and what can the service map it to?

**Answer:** `Mono<UpdateResult>`, which can **map** `modifiedCount` into `Mono<Boolean>`. Never call `block()` in WebFlux.

### Exercise 14: reactive double subscribe

Creating a `Mono` containing a stock deduction and subscribing twice can cause what issue?

**Answer:** Two subscriptions can trigger two updates. Reactive streams do not automatically prevent duplicate business requests.

### Exercise 15: concurrency test

Stock=3; 10 independent concurrent requests arrive, each deducting 1. No restocks or infrastructure errors occur. Afterward, how many succeed and what is final stock?

**Answer:** 3 requests succeed, 7 fail to match the filter, and final stock=0.

### Exercise 16: admin adjustment

An admin reads stock=12, then a checkout reduces it to 11. The admin calls `save(stock=12)` from the stale form. Propose a safer approach.

**Answer:** Use a delta update with `$inc` or conditional compare-and-set/`@Version`, with authorization and auditing. Never `$set` from a stale snapshot without concurrency checks.

### Exercise 17: TTL reservations

An expired reservation is automatically deleted by MongoDB TTL. Is stock automatically restored?

**Answer:** No. TTL does not invoke `$inc` on inventory; an explicit stateful expiration/release workflow with idempotency is needed.

### Exercise 18: legacy data

A document has `stock=null`. Is an unconditional negative `$inc` safe?

**Answer:** No. `$inc` on null can fail; validate/migrate data and always guard queries with an appropriate stock predicate.

## 29. Pre-production checklist

- **Invariant:** does `stock` mean available, physical, or total including reserved?
- **Input:** is `quantity` a positive integer within policy bounds and matching units?
- **Authorization:** are tenant/warehouse derived from a trusted context?
- **Identity:** does the query target at most one exact inventory document?
- **Atomicity:** are `stock>=quantity` and negative `$inc` in **the same command**?
- **Upsert:** is auto-creating negative inventory on no-match disabled?
- **Results:** do you distinguish `modifiedCount=0`, acknowledged, and exceptions?
- **Responses:** do you avoid leaking another tenant's stock counts?
- **Idempotency:** is there a `requestId`/`reservationId` preventing double checkout?
- **Timeouts:** is there an unknown-outcome strategy rather than blind retries?
- **Reservations:** do reserve/consume/cancel/expire have explicit state transitions?
- **Transactions:** do multi-document writes share commit/rollback or compensation?
- **Outbox:** are external events/payments handled consistently?
- **Admin:** are `$set` operations from stale snapshots blocked without CAS/version?
- **Schema:** are `stock`/`reserved` stored as valid non-negative BSON numbers?
- **Indexes:** do lookup queries use `_id` or a proper compound key?
- **Hot SKUs:** are write contention, p95/p99, and conflicts measured?
- **Reactive:** are `block()` and double-subscribing to updates avoided?
- **Durability:** do write/read concerns fit business requirements?
- **Testing:** are concurrency, out-of-stock, tenant, retry, and duplicate-cancel cases tested?
- **Monitoring:** is inventory reconciled against orders/reservations and physical warehouse counts?

## 30. Summary

1. **Read then check then save** is unsafe for stock when multiple writers update the same document.
2. **Atomic stock decrement** is a single MongoDB operation combining **stock >= quantity** in the filter and **$inc stock:-quantity** in the update.
3. On a single inventory document, condition and update execute atomically, preventing overselling when all writers obey the rule.
4. **MongoTemplate.updateFirst** returns `UpdateResult`; **modifiedCount=1** in this model indicates a successful decrement.
5. **modifiedCount=0 is not automatically a system error**, while timeouts can leave uncertain write outcomes.
6. **findAndModify(returnNew=true)** fits when the remaining stock is needed right after the update.
7. **Validating quantity>0**, scoping tenant, targeting the exact ID/SKU/warehouse, and disabling upsert are baseline safety requirements.
8. **stock and reserved can update atomically in the same document** via two `$inc` modifiers, yet multi-document reservation workflows still need consistent design.
9. **Atomic is not synonymous with idempotent**: resent HTTP requests can still deduct again while stock lasts.
10. **Unique requestId + transaction or controlled workflow** is needed to prevent re-applying reservations/orders.
11. **@Version** provides optimistic locking in supported cases, rather than directly replacing quantity predicates.
12. **ReactiveMongoTemplate** keeps identical MongoDB semantics via `Mono` and subscriptions; never block or double-subscribe.
13. **A single update does not make multiple collections/orders/payments atomic**; use transactions, outbox, or sagas where needed.
14. **Indexes, schema validation, and observability** support stable operations without replacing business invariants.
15. **Concurrency integration tests** on real MongoDB must prove successful requests never exceed stock and final stock is exact.

Mastering **decrementing stock with quantity conditions and atomic inc** helps **SPRING_DATA_MONGODB** services prevent overselling at the point of update, cleanly signal out-of-stock outcomes, and establish a solid foundation for reservations, payments, transactions, reactive access, and concurrency testing.

### References

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/) — single-document atomicity and placing expected values in filters.
- [MongoDB Manual — $inc Update Operator](https://www.mongodb.com/docs/manual/reference/operator/update/inc/) — numeric increment/decrement and behavior with null/missing fields.
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/) — finding and updating one document, `returnNew`.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html) — `MongoTemplate.updateFirst`, `findAndModify`, `Update.inc`.
- [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking) — `@Version` and update conflicts.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/) — scope of driver and server retryable writes.
