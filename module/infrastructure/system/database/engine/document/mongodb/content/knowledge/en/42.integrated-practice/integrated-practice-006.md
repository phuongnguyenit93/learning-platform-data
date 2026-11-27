# Concurrency Testing When Updating Inventory and Creating Orders in MongoDB

Suppose an online store has **5 units** left in stock. Right as a promotion starts, 20 customers click Place Order simultaneously. If each request reads stock, subtracts in Java, and writes back, the system might create 20 successful orders while stock only drops from 5 to 4—or even goes negative. Adding an order document insert in another collection introduces cases where **inventory was deducted without creating an order**, or **an order was created without deducting stock**.

The lesson **"Concurrency Testing When Updating Inventory and Creating Orders"** belongs to the **Integrated Practice** chapter of the **Database Engine Document MongoDB** module. It sets up a verifiable lab using code, multiple clients/threads, and business invariants. We will intentionally construct a broken approach first, fix it with a **single-document atomic conditional update**, add a **multi-document transaction**, design an **idempotency key**, and test conflicts, retries, mid-flight failures, and unknown commit outcomes.

Upon completion, you will be able to:

1. Describe and reproduce **lost updates**/overselling when multiple customers place orders concurrently.
2. Write the **`available >= quantity`** predicate combined with `$inc` in a **single MongoDB command** to prevent negative inventory.
3. Distinguish **single-document atomicity** from **atomicity across inventory and order documents**.
4. Use **MongoDB multi-document transactions** and the MongoDB Java Sync Driver to create orders and deduct inventory consistently.
5. Apply a unique business key `(tenantId, requestId)` to prevent duplicate orders on client retries.
6. Distinguish **out of stock, duplicate request, same key with different payload, write conflict, timeout, and unknown commit outcome**.
7. Write JUnit integration tests for 20–100 concurrent requests using `ExecutorService` and `CountDownLatch`.
8. Verify exact invariants: non-negative stock, no duplicate orders, and reserved quantities matching deducted stock.
9. Decide when to use transactions, atomic updates, single-document embedding, or reservation/saga workflows.

> **Safety scope:** all data, SKUs, request IDs, and setup commands are strictly for a **disposable MongoDB lab**. Never run concurrency tests against a customer-serving production cluster. Transaction examples require a **replica set or sharded cluster supporting transactions**; a standalone `mongod` generally does not meet this requirement. Snippets are presented to teach mechanics; configure dependencies, authentication, networking, URIs, and cleanup appropriately for real environments.

## 1. Establishing Invariants Before Writing Code

In a concurrency exercise, the key goal is not "all 20 threads finish without throwing errors." Rather, we define **invariants**—rules that must always hold across every accepted outcome.

For a single SKU with one product type and no restocking during the test:

```text
initialAvailable = 5
quantity per order = 1

0 <= inventory.available <= 5

Successfully placed quantity <= 5

inventory.available
  + SUM(quantity of orders in status RESERVED)
  = initialAvailable

No two orders share (tenantId, requestId)
```

In this lab, every successful order is created in status **RESERVED** with no cancellation/return step yet, so the equation above holds under this fixed model.

Once restocking, cancellations, returns, fulfillment, expirations, or holds exist, the model must expand into a transaction ledger with consistent definitions of `onHand`, `reserved`, and `available`. **Do not apply the simplified lab formula directly to a complex warehouse system.**

### Permitted Outcomes

For 20 distinct requests, each ordering one unit when initial stock is 5:

| Outcome | Expected Count |
| --- | ---: |
| Request accepted with a `RESERVED` order | 5 |
| Request rejected as out of stock | 15 |
| Final inventory | 0 |
| Negative inventory | Not allowed |
| Two orders sharing an idempotency key | Not allowed |
| Stock deducted without an order | Not allowed under transactions |

Which 5 of the 20 customers win does not matter. Business invariants are what tests must assert.

## 2. Minimal Data Model

We use two collections:

```text
inventory
  _id           -> SKU, unique by _id
  available     -> quantity still available to order
  initialStock  -> initial fixture quantity

orders
  _id           -> order ID
  tenantId      -> application scope
  requestId     -> idempotency key
  sku           -> ordered SKU
  quantity      -> positive integer quantity
  status        -> RESERVED in this lab
  createdAt     -> creation timestamp
```

An inventory document:

```javascript
{
  _id: "SKU-BOOK-001",
  available: 5,
  initialStock: 5
}
```

An order document:

```javascript
{
  _id: "order-001",
  tenantId: "tenant-demo",
  requestId: "request-001",
  sku: "SKU-BOOK-001",
  quantity: 1,
  status: "RESERVED",
  createdAt: ISODate("2026-11-14T08:00:00Z")
}
```

### Why Is `requestId` Needed?

A user might click Place Order twice, or a client might miss a response due to a timeout and retry. Two API calls can represent the **exact same ordering intent**. If you generate a new ID on every call without a unique business key, you can deduct inventory twice.

In the lab, `requestId` is the **idempotency key**: same tenant + same `requestId` + same business payload must represent **at most one order**.

## 3. Preparing the Lab Database in `mongosh`

Run in an authorized test database environment:

```javascript
use mongo_order_concurrency_lab

// Drop collections ONLY in a disposable lab database.
db.inventory.drop();
db.orders.drop();

db.inventory.insertOne({
  _id: "SKU-BOOK-001",
  available: 5,
  initialStock: 5
});

db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    name: "uk_tenant_request"
  }
);

db.inventory.findOne({ _id: "SKU-BOOK-001" });
db.orders.getIndexes();
```

`drop()` commands here are **strictly for an isolated lab**; they wipe all documents and indexes. For parallel integration tests, use a **unique SKU/tenant/`testRunId` per test** instead of dropping shared collections.

The unique index `{tenantId:1, requestId:1}` must be created successfully **before running concurrency tests**. Simply having a field named `requestId` does not enforce uniqueness.

## 4. Confirming Transaction-Capable Topology

From `mongosh`:

```javascript
db.adminCommand({ hello: 1 });
```

Check deployment:

- If a replica set, the response includes replica set fields like `setName` and appropriate member state.
- If via `mongos`, the response reflects a sharded router.
- On a standalone `mongod`, multi-document transactions are not supported as in a replica set or sharded cluster.

In a replica set:

```javascript
rs.status();
```

Not every client account has privileges to inspect full replica status; operations accounts need appropriate roles.

### Choosing Lab Topology

To test atomicity across two collections, use a test MongoDB replica set or a Testcontainers environment properly initialized as a replica set. **Do not "fix" an unsupported-transaction error by removing the transaction** while still labeling the atomicity test PASS.

Common error:

```text
Transaction numbers are only allowed on a replica set member
or mongos
```

If encountered, check topology and URI first. Running MongoDB in Docker **does not automatically mean a replica set is configured**.

## 5. Broken Approach #1: Read Then Write New Value

A naive service:

```javascript
const stock = db.inventory.findOne({
  _id: "SKU-BOOK-001"
});

if (stock.available >= 1) {
  db.inventory.updateOne(
    { _id: "SKU-BOOK-001" },
    { $set: { available: stock.available - 1 } }
  );
}
```

With a single client, this looks fine. Yet two clients can both read `available = 5` before either writes.

```text
Client A                               Client B
   |                                      |
   | findOne -> available=5               | findOne -> available=5
   |                                      |
   | compute 5 - 1 = 4                    | compute 5 - 1 = 4
   |                                      |
   | update $set available=4              |
   |                                      | update $set available=4
   v                                      v

Final stock = 4
Yet TWO requests were accepted.
Business logic expected 3 remaining.
```

A **lost update** occurs because `updateOne()` filters only by `_id` and overwrites a value computed from stale data. Each individual update is still atomic at document level; what is missing is the **race-safe condition inside the same operation**.

## 6. Broken Approach #2: Check Stock in Java Then Insert Order

Pseudo-code example:

```java
Inventory inventory = inventoryRepo.findById(sku)
    .orElseThrow();

if (inventory.getAvailable() >= quantity) {
    inventory.setAvailable(
        inventory.getAvailable() - quantity);
    inventoryRepo.save(inventory);
    ordersRepo.insert(newOrder);
}
```

There are at least two flaws:

1. **Concurrency:** multiple threads read the same stale stock count and all call `save()`.
2. **Two separate writes:** stock deduction succeeds, yet inserting the order can fail due to duplicate key, network error, process crash, or validation failure.

Adding `@Version`/optimistic locking to `inventory` reduces lost updates for framework-managed `save()` calls, but **does not provide atomicity** across two collections. Deducting stock and creating the order can still succeed independently without a transaction or compensating workflow.

## 7. Fixing Overselling with Atomic Conditional `$inc`

One command:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-BOOK-001",
    available: { $gte: 1 }
  },
  {
    $inc: { available: -1 }
  }
);
```

MongoDB checks `available >= 1` and performs the decrement **within a single atomic write on one document**.

If stock reaches 0, the predicate fails to match; the operation never drives it to -1.

### Why Is `$inc` Safer Than `$set` with a Pre-Read Value?

```text
Wrong:
  read available = N
  set available = N - 1

Right for one inventory record:
  update where available >= 1
  inc available by -1
```

Two requests do not compute the new value from stale snapshots; the server executes the increment/decrement atomically.

**Note:** single-document updates must still run with an acknowledged write concern so the application sees `matchedCount`. It does not replace a transaction when an order document must also be inserted.

## 8. Distinguishing `matchedCount` and `modifiedCount`

`updateOne()` returns:

```javascript
{
  acknowledged: true,
  matchedCount: 1,
  modifiedCount: 1
}
```

or when stock is insufficient:

```javascript
{
  acknowledged: true,
  matchedCount: 0,
  modifiedCount: 0
}
```

For conditional decrements, `matchedCount == 1` means the operation's predicate matched the document. `matchedCount == 0` can mean either **the SKU does not exist** or **stock is insufficient**.

Do not interpret every `matchedCount=0` as a network error, and never create an order when the decrement matched nothing. In a `$set` updating a field to its existing value, `modifiedCount=0` can happen even when `matchedCount=1`; therefore, checking **`matchedCount`** is essential for CAS/conditional updates.

## 9. Manual Test with Two `mongosh` Sessions

Open two connections to the **same lab database** and `inventory` collection:

**Session A:**

```javascript
db.inventory.updateOne(
  { _id: "SKU-BOOK-001", available: { $gte: 1 } },
  { $inc: { available: -1 } }
);
```

**Session B:** run the same command.

Repeat for multiple requests if desired. Once `available` hits 0, subsequent commands return `matchedCount=0`.

Verify:

```javascript
db.inventory.findOne({ _id: "SKU-BOOK-001" });
```

The value cannot go negative as long as **every writer uses the condition** and no rogue script runs an unguarded `$set` on stock.

### Limitations of Manual Testing

Two commands typed separately rarely execute truly concurrently. The JUnit section later uses a barrier to force intentional races. Manual testing helps understand filters and matched counts, but is insufficient to prove concurrency safety under load.

## 10. Atomic Decrement Still Leaves a Gap When Creating Orders

After fixing overselling:

```text
1. update inventory WHERE available >= 1, $inc -1
2. insert order
```

Failure scenario:

```text
available: 5
   |
   v
UPDATE inventory -> available: 4, ACK
   |
   v
Process crash / duplicate key / network error
   |
   X
Failed to INSERT order

Result:
  Inventory decreased by 1
  No matching order exists
```

If you reverse the order:

```text
1. insert order
2. decrement inventory
```

then when the decrement fails, you end up with an **order without reserved stock**.

**Correctness per step does not guarantee correctness across both steps.** This is precisely why transactions or explicitly designed stateful compensation workflows are needed.

## 11. Three Architectural Options

| Option | Prevents Overselling | Prevents Inventory/Order Drift | When to Consider |
| --- | --- | --- | --- |
| Conditional atomic `$inc`, then insert order | Yes, for one SKU document | **Not automatically** | Flows accepting compensation or not needing atomic order creation |
| Multi-document transaction | Yes, with proper filter | Yes, across writes in transaction | Simplest when two collections must commit together |
| Reservation ledger / saga / outbox | Must design invariants and claims | Eventual consistency with reconciliation | Distributed workflows, high write volume, external services |

Another option is **embedding order/reservation summaries directly inside the inventory document**, though that causes document bloat, high contention, or BSON size breaches, and does not fit multi-SKU orders. Choose aggregate boundaries based on business rules and workload, not merely to avoid transactions.

## 12. What Does a MongoDB Transaction Do in This Lab?

The transaction wraps both writes:

```text
BEGIN TRANSACTION
    |
    +-- INSERT orders(orderId, requestId, sku, quantity)
    |
    +-- UPDATE inventory
          WHERE sku = X AND available >= quantity
          $inc available = -quantity
    |
    +-- If sufficient stock and no errors -> COMMIT
    |
    +-- If out of stock, duplicate key, or error -> ABORT
```

When commit succeeds under appropriate durability/transaction semantics, **there is no normal outcome where only half of the two writes commit**.

If stock is insufficient, you must **throw an exception** or abort the transaction via the API to roll back the order insert already issued inside the transaction. Never return success after a stock update yields `matchedCount=0`.

### Transactions Do Not Enforce Every Business Rule Automatically

If the inventory filter omits `available >= quantity`, the transaction will happily commit a decrement into negative numbers. If two requests share an idempotency key without a unique index, the transaction **does not automatically guarantee** only one order per business key. Combine transactions with **accurate filters, unique constraints, and business validation**.

## 13. Multi-Document Transactions: Prerequisites and Limits

Keep in mind:

- A MongoDB replica set or sharded cluster supporting transactions for your version.
- A driver supporting sessions and transactions.
- Properly configured read/write concerns, read preferences, and topology.
- Every MongoDB operation participating in the transaction must pass the **same session**.
- Transactions should be **short-lived**—never held open while a user fills out a form.
- `WriteConflict`/transient errors can occur and require retries per supported semantics.
- Never call payment gateways or send emails inside a transaction callback that may be retried.

MongoDB transactions carry server overhead and time/resource bounds, especially when spanning many documents or shards. Do not turn every simple `$inc` into a multi-document transaction if the invariant can be enforced inside one document.

## 14. Defining Idempotency for Order Placement

This problem involves two concurrency patterns:

**A. Two different customers order the same SKU.**

```text
tenant-demo / request-A / SKU-BOOK-001 / qty=1
tenant-demo / request-B / SKU-BOOK-001 / qty=1
```

These are **two independent intents**, both allowed to compete for remaining stock.

**B. One customer retries the exact same request.**

```text
tenant-demo / request-A / SKU-BOOK-001 / qty=1
tenant-demo / request-A / SKU-BOOK-001 / qty=1
```

This is the **same intent** and must never deduct stock twice.

**C. Client reuses a key but alters the payload.**

```text
tenant-demo / request-A / SKU-BOOK-001 / qty=1
tenant-demo / request-A / SKU-BOOK-001 / qty=5
```

This is an **idempotency contract violation**. Never silently treat `qty=5` as the same `qty=1` request.

In the lab, business identity is `(tenantId, requestId)` and the payload is checked via `sku` and `quantity`. Production systems may also compare currency, price, address, user identity, discounts, or a canonical payload fingerprint.

## 15. Unique Index for the Idempotency Key

```javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  { unique: true, name: "uk_tenant_request" }
);
```

This constraint guarantees **no two distinct documents share the same `(tenantId, requestId)` pair** per unique key semantics.

Do not rely on:

```java
if (!orders.existsByTenantAndRequest(...)) {
    orders.insert(...);
}
```

because two threads can both observe "does not exist." The unique index remains the final safety net.

### Why Not Make SKU Unique?

One SKU must appear across **many different orders**. Making `orders.sku` unique would forbid anyone else from ordering a product someone already bought. Only `inventory._id` is unique by SKU; `orders` is unique by the idempotency key.

## 16. Status Conventions in the Lab

For straightforward reconciliation:

```text
RESERVED -> reservation succeeded, stock decremented
REJECTED_OUT_OF_STOCK -> no order created in orders collection
```

This lab does not implement cancellations, shipping, returns, or payments yet. When a real application has a full lifecycle:

```text
NEW -> RESERVED -> PAID -> SHIPPED
             \
              -> CANCELLED -> RELEASED
```

each state transition needs its own atomic/idempotent rules. Never hold a single checkout transaction open across seconds or minutes waiting on an external payment gateway.

## 17. Java Sync Driver: Dependencies and Connection

In a Java 17+ project, add a compatible version of `org.mongodb:mongodb-driver-sync`. Gradle example:

```groovy
dependencies {
    implementation("org.mongodb:mongodb-driver-sync:5.x.y")
    testImplementation("org.junit.jupiter:junit-jupiter:5.x.y")
}
```

**`5.x.y` is a placeholder**, not a resolvable artifact version. Use the concrete version pinned by your project's dependency management. The application needs a URI to the lab replica set/sharded cluster and appropriate credentials.

Minimal connection:

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import com.mongodb.client.MongoDatabase;

String uri = System.getenv("MONGO_LAB_URI");
if (uri == null || uri.isBlank()) {
    throw new IllegalStateException("Missing MONGO_LAB_URI");
}

try (MongoClient client = MongoClients.create(uri)) {
    MongoDatabase db =
        client.getDatabase("mongo_order_concurrency_lab");
    System.out.println(db.getName());
}
```

Never store MongoDB URIs containing passwords in source code or test logs. `MongoClient` should be shared across the application lifecycle; do not instantiate a new client per order without good reason.

## 18. Input and Output DTOs

Example:

```java
public record CreateOrder(
    String tenantId,
    String requestId,
    String sku,
    int quantity
) {}

public record OrderReceipt(
    String orderId,
    String status,
    boolean newlyCreated
) {}
```

Before starting a transaction, validate:

- `tenantId` comes from the authenticated principal or is authorized per contract.
- `requestId` is non-blank and within length bounds.
- `sku` is valid and canonicalized per schema.
- `quantity > 0` and within per-request limits.
- The user is authorized to order for this tenant/SKU.

Here `tenantId` is placed on the record for lab brevity; **production must never trust an arbitrary `tenantId` from the request body**.

## 19. Dedicated Exception for Insufficient Stock

```java
public final class InsufficientStockException
        extends RuntimeException {

    public InsufficientStockException(String sku) {
        super("Insufficient stock for SKU: " + sku);
    }
}
```

We use this exception to **abort the transaction** when the decrement matches nothing. In production, this maps to HTTP 409 Conflict or another contract-defined status—never leak raw stack traces to clients.

Separate business out-of-stock errors from:

- `MongoWriteException` duplicate key.
- `MongoException` from transient transaction errors.
- Timeouts/unknown network outcomes.
- Validation/authorization errors.

Never catch every `MongoException` and report "out of stock."

## 20. Java Service: Transaction Creating an Order and Deducting Stock

This is the centerpiece example of the lesson. Assume `orders` already has the unique index `{tenantId:1, requestId:1}` and `inventory` has SKU documents with numeric `available`.

```java
import com.mongodb.ReadConcern;
import com.mongodb.ReadPreference;
import com.mongodb.TransactionOptions;
import com.mongodb.WriteConcern;
import com.mongodb.MongoWriteException;
import com.mongodb.client.ClientSession;
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import java.util.Date;
import java.util.Objects;
import java.util.UUID;

public final class OrderService {

    private final MongoClient client;
    private final MongoCollection<Document> inventory;
    private final MongoCollection<Document> orders;

    public OrderService(MongoClient client, MongoDatabase db) {
        this.client = client;
        this.inventory = db.getCollection("inventory");
        this.orders = db.getCollection("orders");
    }

    public OrderReceipt place(CreateOrder request) {
        validate(request);

        // Generated once per invocation, not inside the callback,
        // because the driver may retry the transaction.
        String orderId = UUID.randomUUID().toString();

        TransactionOptions options = TransactionOptions.builder()
            .readConcern(ReadConcern.SNAPSHOT)
            .writeConcern(WriteConcern.MAJORITY)
            .readPreference(ReadPreference.primary())
            .build();

        try (ClientSession session = client.startSession()) {
            try {
                return session.withTransaction(() -> {
                    // Step 1: insert order inside transaction.
                    Document order = new Document("_id", orderId)
                        .append("tenantId", request.tenantId())
                        .append("requestId", request.requestId())
                        .append("sku", request.sku())
                        .append("quantity", request.quantity())
                        .append("status", "RESERVED")
                        .append("createdAt", new Date());

                    orders.insertOne(session, order);

                    // Step 2: decrement stock only if sufficient.
                    UpdateResult stockResult = inventory.updateOne(
                        session,
                        Filters.and(
                            Filters.eq("_id", request.sku()),
                            Filters.gte("available",
                                request.quantity())
                        ),
                        Updates.inc("available",
                            -request.quantity())
                    );

                    if (stockResult.getMatchedCount() != 1) {
                        throw new InsufficientStockException(
                            request.sku());
                    }

                    // Both writes take effect together only
                    // once the transaction commits cleanly.
                    return new OrderReceipt(
                        orderId, "RESERVED", true);
                }, options);
            } catch (MongoWriteException ex) {
                if (ex.getError().getCode() != 11000) {
                    throw ex;
                }

                // Duplicate request key is one possibility.
                // Do not treat every E11000 as idempotent success.
                Document existing = orders.find(
                    Filters.and(
                        Filters.eq("tenantId",
                            request.tenantId()),
                        Filters.eq("requestId",
                            request.requestId())
                    )
                ).first();

                if (existing == null) {
                    throw ex;
                }

                if (!Objects.equals(
                        existing.getString("sku"),
                        request.sku())
                    || existing.getInteger("quantity")
                        != request.quantity()) {
                    throw new IllegalArgumentException(
                        "Idempotency key already used "
                        + "for a different order payload");
                }

                return new OrderReceipt(
                    existing.getString("_id"),
                    existing.getString("status"),
                    false
                );
            }
        }
    }

    private static void validate(CreateOrder r) {
        if (r.tenantId() == null
                || r.tenantId().isBlank()
                || r.requestId() == null
                || r.requestId().isBlank()
                || r.sku() == null
                || r.sku().isBlank()
                || r.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid request");
        }
    }
}
```

**Key points to understand:**

- `orders.insertOne(session, ...)` and `inventory.updateOne(session, ...)` share the **same session**.
- `withTransaction` manages begin/commit/abort and retries specific transaction error classes per driver semantics.
- `ReadConcern.SNAPSHOT` and `WriteConcern.MAJORITY` express the transaction's consistency/durability choices; match them to your actual topology and contract.
- The unique index prevents creating two orders with the same `(tenantId, requestId)`.
- The `available >= quantity` predicate prevents overselling stock.
- When out of stock, `InsufficientStockException` aborts the transaction; the order insert inside the transaction is rolled back.
- If insert throws `E11000`, the service never deducts stock in that transaction; we treat it as a valid retry only after reading the existing order and verifying the payload matches.
- On timeout or unknown commit outcome where success vs. failure is uncertain, **never default to out-of-stock or retry with a new `requestId`**.

### Limitations of This Example

This is a **lab sample**, not a complete production service. Production must handle differently wrapped duplicate errors, read concerns/preferences during reconciliation, additional order statuses, idempotency retention policies, retry time budgets, and transient disconnects. For richer order payloads, compare a canonical payload hash rather than only `sku` and `quantity`.

## 21. Why Insert the Order Before Deducting Stock?

Inside a transaction, both orders **can be safe** given proper predicates and aborts:

```text
Option A:
  INSERT order
  UPDATE stock
  COMMIT

Option B:
  UPDATE stock
  INSERT order
  COMMIT
```

We pick Option A so the unique request key rejects duplicate retries early before contending on the hot inventory document. However:

- When stock is short, the order insert still runs **inside the transaction** and is rolled back on abort.
- Never send emails or trigger shipping right after `insertOne()` inside the callback; the transaction has not committed yet.
- Never tell the client "order created" before commit is confirmed.

Neither ordering replaces a transaction when the invariant requires both writes to commit together.

## 22. When Two Transactions Decrement the Same SKU Concurrently

Example with stock = 1 and two distinct requests:

```text
Initial:
  inventory.available = 1

Transaction A            Transaction B
   |                        |
   | begin                  | begin
   | insert order-A         | insert order-B
   | update SKU -1          | update SKU -1
   |                        |
   | commit?                | conflict / retry?
   v                        v
  One transaction commits and reserves stock.
  The other must re-evaluate state and
  ultimately be rejected because stock=0.
```

Specifically under snapshot isolation, two transactions racing on the same document can hit a **write conflict / transient error**, not merely an update returning `matchedCount=0`. The driver or application retries the transaction per semantics to re-check stock against a fresh snapshot.

Desired business outcome:

```text
inventory.available = 0
count(orders RESERVED for SKU) = 1
No order-B committed without available stock.
```

**There is no guarantee Transaction B always loses.** Tests assert the invariant, not thread scheduling.

## 23. `withTransaction` and Retries

MongoDB transactions can return errors bearing retry labels:

- `TransientTransactionError`: the **entire transaction** may need retrying.
- `UnknownTransactionCommitResult`: the client is unsure of the commit outcome and may need to retry **commit** per driver guidance.

The `withTransaction` convenient transaction API in the Java Sync Driver handles retries according to these semantics, with important boundaries:

- Not every error is transient.
- Never retry indefinitely in an unbounded outer loop without a deadline.
- Never catch `InsufficientStockException` and retry it like a network error.
- Never equate `E11000` with a transient write conflict.
- Because the callback may run more than once, all code inside the callback must be **safe to re-execute**.

### When the Callback Re-Runs

```text
withTransaction(callback)
       |
       +--> attempt 1
       |      write conflict -> abort
       |
       +--> attempt 2 (if driver retries)
              reads/updates in new transaction
              commit
```

That is why the example generates `orderId` **before the callback** and avoids payment gateways or notifications inside it. The `Document` object may be re-instantiated on retry, while no write from the aborted attempt was committed.

## 24. Never Trigger External Side Effects Inside a Transaction Callback

Anti-pattern:

```java
session.withTransaction(() -> {
    orders.insertOne(session, order);
    paymentGateway.charge(card, amount); // Dangerous
    inventory.updateOne(session, filter, update);
    return orderId;
});
```

Problems:

1. The payment gateway **is not part of the MongoDB transaction**.
2. If the transaction aborts, the external charge may already have succeeded.
3. The driver may retry the callback, charging the customer multiple times.
4. On an unknown commit result, erroneous retries become even riskier.

A cleaner flow:

```text
Transaction:
  reserve inventory
  create order RESERVED
  create outbox event (if same database/transaction)
Commit
  |
  v
Worker reads outbox
  |
  v
Payment/fulfillment with idempotency key
  |
  v
Conditional status transition + audit
```

Even with an outbox, event delivery is typically **at-least-once**, so downstream consumers must be idempotent. MongoDB transactions do not automatically provide exactly-once side effects across external systems.

## 25. E11000 When Concurrent Requests Share an Idempotency Key

Scenario:

```text
T1: tenant-a / request-X / SKU-BOOK-001 / qty 1
T2: tenant-a / request-X / SKU-BOOK-001 / qty 1
```

The unique index ensures two orders can never commit with the same `(tenantId, requestId)`.

A request may:

- Insert and commit the order first.
- Hit a duplicate-key error after the other request created it.
- Hit a write conflict, get retried by the driver, and then encounter the duplicate.
- Encounter an unknown outcome if the network disconnects during commit.

On duplicate:

1. Identify **which index/key threw the error**—do not assume every `E11000` is the idempotency index.
2. Fetch the order by the unique business key.
3. Compare immutable payload/fingerprint.
4. Matching payload: return the existing order/result per contract.
5. Mismatched payload: return a conflict.
6. If the existing order cannot be read or state is uncertain: retry/reconcile within bounds, **never return a false success**.

### Why Doesn't a Duplicate Equal Data Loss?

The unique constraint is **protecting** the system. However, catching `E11000` and returning HTTP 200 without comparing payloads would mask invalid reuse of an idempotency key.

## 26. Duplicate Keys Must Not Deduct Inventory a Second Time

Idempotency invariant:

```text
Same tenantId + requestId + payload:
  first call -> order RESERVED + stock -quantity
  retry call -> return existing order
                + stock unchanged
```

Test with:

```text
Initial available = 5
Call place(requestId="dup-01", quantity=2)
Call place(requestId="dup-01", quantity=2)

Expected:
  orders unique key count = 1
  available = 3
  both responses return the same logical order ID
```

If `available = 1` afterward, the service deducted twice despite creating one order—a critical bug. Transactions plus a unique index prevent it, yet error handling and retries still require explicit testing.

## 27. Same Key with Different Payload Must Be Rejected

Example:

```text
tenant-a / req-123 / SKU-BOOK-001 / qty=1
tenant-a / req-123 / SKU-BOOK-001 / qty=4
```

Sharing `requestId` does not make two requests equivalent. The API should return an explicit **idempotency conflict**, never an upsert `$set` overwriting the existing order's quantity.

What to consider when normalizing payloads:

- Currency, price snapshot, discounts, shipping address, user identity.
- Canonicalization of monetary numbers, Unicode, and optional fields.
- Hash version and schema version.
- Never log raw PII inside duplicate-key error messages.

In this lab we compare only `sku` + `quantity` because other attributes are not modeled.

## 28. Updating Inventory When an Order Has Multiple SKUs

If an order contains:

```json
{
  "items": [
    { "sku": "SKU-A", "quantity": 2 },
    { "sku": "SKU-B", "quantity": 1 }
  ]
}
```

you must decrement **two inventory documents**. Running separate atomic updates per SKU without a transaction can leave:

```text
SKU-A decremented successfully
SKU-B out of stock
Order rejected
Yet SKU-A remains decremented
```

Inside a transaction:

1. Create the order in the appropriate status.
2. For each item, update inventory with `available >= quantity`.
3. If any item lacks stock, throw/abort the transaction.
4. If all succeed, commit.

### Avoiding Contention/Thrashing Under Multi-SKU Workloads

When concurrent requests touch overlapping sets of SKUs, contention and write conflicts increase. Ordering SKU updates in a **consistent sorted order**, keeping transactions short, and capping items per order can help. Because MongoDB handles concurrency differently from traditional lock-based databases, do not treat SKU ordering as a guarantee that zero write conflicts will occur.

## 29. Never Use Upsert to "Auto-Create Inventory" When Stock Runs Out

Anti-pattern:

```javascript
db.inventory.updateOne(
  { _id: "SKU-BOOK-001", available: { $gte: 2 } },
  { $inc: { available: -2 } },
  { upsert: true }
);
```

When no document matches because **`available < 2`**, an upsert attempts to insert a new document with the same `_id` and throws `E11000`. If the SKU does not exist, it creates an invalid record with negative `available`.

When reserving stock, always use **`upsert:false`**. A missing SKU or insufficient stock is a reason to reject the order, not an invitation to synthesize an inventory document.

## 30. Distinguishing Reserve, Release, and Cancel

In real workflows, cancelling an order may require returning stock:

```text
Order status RESERVED
       |
       v
Conditional transition to CANCELLED
       |
       v
Increment available by quantity
```

Do not write:

```java
orders.updateOne(eq("_id", orderId),
    Updates.set("status", "CANCELLED"));
inventory.updateOne(eq("_id", sku),
    Updates.inc("available", quantity));
```

as two separate unguarded commands if policy requires atomicity. If cancel is submitted twice, stock gets incremented twice.

### Idempotent Cancellation Rule

Inside a transaction:

1. Update the order with filter `{_id:orderId,status:"RESERVED"}` to `CANCELLED`.
2. Only if `matchedCount=1`, `$inc inventory.available` by `quantity`.
3. Commit both writes.
4. If the order is already `CANCELLED`, do not increment again.

If an order is `SHIPPED` or `PAYMENT_CAPTURED`, cancellation requires dedicated refund/return workflows, not a simple `$inc`.

## 31. Transaction Example for Order Cancellation

Brief code illustrating the invariant:

```java
session.withTransaction(() -> {
    Document order = orders.find(
        session,
        Filters.eq("_id", orderId)
    ).first();

    if (order == null) {
        throw new IllegalArgumentException(
            "Order does not exist");
    }

    UpdateResult changed = orders.updateOne(
        session,
        Filters.and(
            Filters.eq("_id", orderId),
            Filters.eq("status", "RESERVED")
        ),
        Updates.set("status", "CANCELLED")
    );

    if (changed.getMatchedCount() == 0) {
        // Already processed or status forbids cancellation.
        return false;
    }

    inventory.updateOne(
        session,
        Filters.eq("_id", order.getString("sku")),
        Updates.inc("available",
            order.getInteger("quantity"))
    );

    return true;
}, options);
```

`orders`, `inventory`, `session`, `options`, and `orderId` are initialized in the service context as in earlier examples. This is an **illustrative transaction snippet**, not a standalone method to paste into any arbitrary Java file.

In production, verify the inventory increment result, tenant scope, cancellation authorization, and whether the SKU might have been deleted. Never allow an out-of-transaction update to change order status without synchronizing inventory.

## 32. Java Test Harness: Generating Real Concurrency

To test 40 concurrent requests for a SKU with stock 10, use:

- `ExecutorService` to spawn multiple workers.
- `CountDownLatch` so workers start nearly simultaneously.
- `Future` to collect outcomes and propagate exceptions.
- Real MongoDB with the unique index and transaction support.
- Fixtures with unique SKU and tenant ID per test.

Run with a **single shared `MongoClient`**, since the Java driver is thread-safe; each transaction must use its **own session**—never share a `ClientSession` across threads.

### JUnit Test Code: Concurrency Harness

```java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Filters;
import org.bson.Document;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class OrderConcurrencyIntegrationTest {

    // Injected/initialized in actual test setup.
    private MongoClient client;
    private MongoDatabase db;
    private OrderService service;

    @Test
    void fortyRequestsMustNotOversellTenUnits() throws Exception {
        String tenantId = "test-" + UUID.randomUUID();
        String sku = "SKU-" + UUID.randomUUID();

        MongoCollection<Document> inventory =
            db.getCollection("inventory");
        MongoCollection<Document> orders =
            db.getCollection("orders");

        inventory.insertOne(
            new Document("_id", sku)
                .append("available", 10)
                .append("initialStock", 10)
        );

        int attempts = 40;
        ExecutorService pool = Executors.newFixedThreadPool(20);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<String>> futures = new ArrayList<>();

        try {
            for (int i = 0; i < attempts; i++) {
                final int index = i;

                Callable<String> task = () -> {
                    start.await();
                    try {
                        service.place(new CreateOrder(
                            tenantId,
                            "req-" + index,
                            sku,
                            1
                        ));
                        return "SUCCESS";
                    } catch (InsufficientStockException ex) {
                        return "OUT_OF_STOCK";
                    }
                };

                futures.add(pool.submit(task));
            }

            start.countDown();

            long success = 0;
            long outOfStock = 0;

            for (Future<String> future : futures) {
                String outcome = future.get(
                    90, TimeUnit.SECONDS);

                if ("SUCCESS".equals(outcome)) {
                    success++;
                } else if ("OUT_OF_STOCK".equals(outcome)) {
                    outOfStock++;
                } else {
                    fail("Unexpected outcome: " + outcome);
                }
            }

            Document finalStock = inventory.find(
                Filters.eq("_id", sku)).first();

            assertNotNull(finalStock);
            assertEquals(0, finalStock.getInteger("available"));

            long reservedOrders = orders.countDocuments(
                Filters.and(
                    Filters.eq("tenantId", tenantId),
                    Filters.eq("sku", sku),
                    Filters.eq("status", "RESERVED")
                )
            );

            assertEquals(10L, success);
            assertEquals(30L, outOfStock);
            assertEquals(10L, reservedOrders);
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
```

**Harness notes:**

- Configure real `client`, `db`, `service`, and the unique index before running. In Spring/JUnit, use appropriate dependency injection/test setup.
- `get(90, TimeUnit.SECONDS)` is an **illustrative deadline**, not a universal SLA. Slow CI runners may need different timeout policies.
- Unexpected transaction/network/driver errors must **fail** the test rather than being swallowed as `OUT_OF_STOCK`.
- Expecting 10 successes and 30 out-of-stock responses assumes **all attempts complete per policy** with no external writers touching the same SKU.
- If excessive write conflicts exhaust retry budgets, the test should report an **infrastructure/contention issue**, not count them as out-of-stock.
- Never run this stress test against production. Use isolated test SKUs/tenants with controlled cleanup.

## 33. Why Are 10 Successes Expected?

In the lab:

```text
Initial stock = 10
40 distinct requests
Each qty = 1
No restock / no cancellation
Successful reservation = committed transaction
```

When transactions and retries behave properly:

```text
10 order transactions commit:
  10 * decrement(1) = 10

Remaining 30 requests:
  insufficient stock -> no order committed

Final available = 0
Reserved orders = 10
```

Never rely on "`available >= 0`" as the sole assertion: a broken service could **deduct stock properly** while creating **0 orders** if inserts always fail outside a transaction. Assert `available`, order count, summed quantity, and uniqueness **together**.

## 34. Testing Concurrent Duplicate Requests

Another test shares the same `requestId`:

```text
Initial stock = 5

Task A -> tenant=test-X / requestId=dup-01 / qty=2
Task B -> tenant=test-X / requestId=dup-01 / qty=2

Expected after settle:
  exactly one order for (tenant, requestId)
  order quantity = 2
  stock = 3
  no repeated external side effects
```

Both calls may return the same order ID if the application handles duplicates idempotently, or one may await reconciliation if commit state is uncertain. **Never treat `stock=1` as valid** just because the unique index kept only one order—that indicates stock was deducted twice.

### Testing Same Key / Different Payload

```text
Task A: requestId=dup-02, qty=1
Task B: requestId=dup-02, qty=3
```

Expected:

- Only one valid request succeeds under first-writer-wins policy.
- The existing order keeps the winning request's payload.
- The other request receives a conflict without overwriting the order.
- Stock decreases by **the exact quantity of the committed order**.

Under concurrency, never assert that Task A must always be the winner.

## 35. Testing Failure After Order Insert but Before Stock Decrement

Transactions allow intentional fault injection:

```java
try (ClientSession session = client.startSession()) {
    session.withTransaction(() -> {
        orders.insertOne(
            session,
            new Document("_id", "fault-order-001")
                .append("sku", "SKU-BOOK-001")
                .append("quantity", 1)
        );

        throw new IllegalStateException(
            "Injected fault before decrement");
    }, options);
}
```

In an isolated test setup, after the exception:

```text
Order fault-order-001 must not be committed
Inventory must not be decremented
```

This is a business/runtime exception thrown before commit; the convenient transaction API aborts per driver mechanics. Never simulate this by **killing a real `mongod` or pod** on a shared cluster just to demonstrate rollback.

### Testing Failure After Stock Decrement

If ordering is decrement-then-insert, throw the exception after the decrement and before the insert. Because both operations share the same transaction, the uncommitted inventory decrement must be aborted.

## 36. Testing Commit Failures and Unknown Outcomes

A harder failure mode:

```text
All transaction writes succeed
      |
      v
Client sends commitTransaction
      |
      v
Network disconnect
      |
      v
Client does not know if commit succeeded
```

You cannot handle this by **generating a new `requestId` and re-submitting the order**. That can create two orders if the first transaction actually committed.

Remediation approach:

1. Let the driver handle supported retryable conditions, especially on commit.
2. If still uncertain, preserve the correlation/idempotency key and report a pending-confirmation state per API contract.
3. Reconcile using the stable `(tenantId, requestId)` with appropriate read concern/routing.
4. If the existing order committed, verify payload match and return it.
5. If not yet visible and connectivity has not recovered, **do not definitively declare failure**.
6. Never trigger duplicate external payments/emails while outcome is unknown.

This is why idempotency and unique indexes remain essential **even when using transactions**.

## 37. Errors That Must Be Classified Separately

| Signal | Possible Meaning | Handling |
| --- | --- | --- |
| `matchedCount=0` on decrement | Missing SKU or insufficient stock | Business rejection, abort |
| `E11000` on `uk_tenant_request` | Request key already exists | Read, compare payload, idempotency/conflict |
| `E11000` on another index | Another business constraint | Never treat as idempotent replay |
| `TransientTransactionError` | Transaction retryable per driver contract | Bounded full-transaction retry |
| `UnknownTransactionCommitResult` | Commit outcome uncertain | Retry commit / reconcile |
| `WriteConflict` | Concurrent writes on same documents | Follow transient semantics, avoid retry storms |
| `MongoTimeoutException` | Server selection or connection failure | Check topology/network, bounded retry |
| `MongoSocketTimeoutException` | I/O timeout | Outcome may be unknown; reconcile |
| Write concern timeout | Acknowledgment policy unmet | Never assume write did not occur |
| Unauthorized | Service lacks DB privileges | Fix RBAC; do not keep retrying |
| Validation error | Invalid data/schema | Return input/domain error |

Exceptions may be wrapped by Spring Data or other driver layers. Classify by structured error codes, labels, and context—not simply substring matching `"timeout"` or `"duplicate"` in error messages.

## 38. Spring Data MongoDB: Configuring Transaction Manager

If the application uses Spring Boot / Spring Data MongoDB, configure `MongoTransactionManager`:

```java
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
```

With a supported MongoDB topology, Spring manages sessions and transactions for participating Spring Data operations.

**Simply adding `@Transactional` to a method is not enough in every project.** Verify the transaction manager bean, session binding, driver URI, MongoDB topology, and versions.

## 39. Spring Data: Inventory Reservation and Order Creation Service

Condensed example:

```java
import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class SpringOrderService {

    private final MongoTemplate template;

    public SpringOrderService(MongoTemplate template) {
        this.template = template;
    }

    @Transactional
    public String place(CreateOrder r) {
        String id = java.util.UUID.randomUUID().toString();

        OrderEntity order = new OrderEntity(
            id, r.tenantId(), r.requestId(),
            r.sku(), r.quantity(), "RESERVED");

        template.insert(order, "orders");

        Query filter = Query.query(
            Criteria.where("_id").is(r.sku())
                .and("available").gte(r.quantity())
        );

        Update decrement = new Update()
            .inc("available", -r.quantity());

        UpdateResult result = template.updateFirst(
            filter, decrement, "inventory");

        if (result.getMatchedCount() != 1) {
            throw new InsufficientStockException(r.sku());
        }

        return id;
    }
}
```

`OrderEntity` here is a project-defined domain class/constructor. Unlike raw Java Sync Driver code, this relies on **Spring transactional proxies**: the method must be invoked through the Spring-managed proxy, avoiding internal self-invocation that bypasses transaction advice.

### Warning When Retrying Spring Transactions

If a full transaction needs retrying, place the retry boundary **outside** the transaction boundary so each attempt opens a **fresh transaction**. Never slap on `@Retryable` assuming annotation ordering, proxies, and exception classifiers automatically align; test actual AOP ordering and Spring Data/driver error behavior.

Never treat `InsufficientStockException` as infinitely retryable.

## 40. Does Spring Data `@Version` Replace Transactions?

No. On an inventory entity:

```java
@Version
private Long version;
```

Spring Data applies optimistic locking when calling `save()` on versioned entities, preventing lost updates across supported entity saves.

However:

```text
Update inventory version N -> N+1
Insert order -> fail
```

remain two independent operations without a transaction. `@Version` does not roll back stock when the order insert fails.

When using raw `MongoTemplate.updateFirst()` or the Java driver, verify who manages the version field and filter. Incrementing a version without an expected-version predicate **does not enforce optimistic CAS**. For simple stock decrements, `available >= quantity` is the direct business predicate.

## 41. Using `findOneAndUpdate` to Return Updated Inventory

Not every order endpoint needs to return the stock document. When you do want the post-decrement document in a single operation:

```java
import com.mongodb.client.model.FindOneAndUpdateOptions;
import com.mongodb.client.model.ReturnDocument;

Document updated = inventory.findOneAndUpdate(
    Filters.and(
        Filters.eq("_id", sku),
        Filters.gte("available", quantity)
    ),
    Updates.inc("available", -quantity),
    new FindOneAndUpdateOptions()
        .returnDocument(ReturnDocument.AFTER)
);

if (updated == null) {
    throw new InsufficientStockException(sku);
}
```

This is an **atomic update on the inventory document**. It does **not** automatically bind to an order insert in another collection. To share a transaction, pass `ClientSession` to every operation or use an active Spring transaction scope.

### Why Not Return `available` as an Authoritative Final Value?

Right after your request commits, another request may order and reduce stock further. The returned `available` represents only **the instant of your update**, not an immutable count guaranteed to hold until the frontend renders.

## 42. Test Validity: Inspect All States

An inadequate assertion:

```java
assertTrue(inventory.available >= 0);
```

Suppose a buggy service never decrements stock while inserting orders:

```text
initial=10, finalAvailable=10
orders RESERVED=100
available>=0 -> FALSE PASS
```

A stronger post-settlement check:

```text
finalAvailable >= 0
SUM(reservedOrder.quantity) <= initialStock
finalAvailable + SUM(reservedOrder.quantity) == initialStock
COUNT_DISTINCT(tenantId,requestId) == COUNT(orders)
No committed order for failed reservations
No stock decrement for aborted transactions
```

### Aggregation for Reconciliation

On the lab database:

```javascript
db.orders.aggregate([
  {
    $match: {
      sku: "SKU-BOOK-001",
      tenantId: "tenant-demo",
      status: "RESERVED"
    }
  },
  {
    $group: {
      _id: "$sku",
      reservedQuantity: { $sum: "$quantity" },
      orderCount: { $sum: 1 }
    }
  }
]);
```

If multiple tenants draw from a shared SKU pool, checking the warehouse invariant requires summing **every reserved order on that SKU**, not only `tenant-demo`. In a tenant-isolated lab fixture, filtering by tenant verifies that test's exact scope.

## 43. Testing Uniqueness by Business Key

Count duplicate `(tenantId, requestId)` orders:

```javascript
db.orders.aggregate([
  {
    $group: {
      _id: {
        tenantId: "$tenantId",
        requestId: "$requestId"
      },
      count: { $sum: 1 },
      orderIds: { $push: "$_id" }
    }
  },
  { $match: { count: { $gt: 1 } } }
]);
```

Expect **zero duplicate groups**. Note that this pipeline does not verify that the unique index actually exists. On very large production collections, `$push`ing all IDs creates memory pressure; apply bounds/batching and check index definitions directly.

### Never Treat an Aggregation Count as Concurrency Control

Checking counts before inserting still has a race condition. This aggregation is a **post-test audit**, while the unique index is the **write-time enforcement**.

## 44. High-Pressure Batch Testing

When scaling up test volume:

```text
initial=100
parallelism=8, 16, 32, 64
total requests=1_000
qty=1
```

Measure:

- Success rate and out-of-stock rejection count.
- Transient write conflicts / transaction retry counts.
- p50/p95/p99 latency.
- Throughput in commits/second.
- Connection pool wait times.
- Disk I/O and WiredTiger cache pressure.
- CPU and memory.
- Duplicate idempotent request rate.
- Disconnects, timeouts, and unknown outcomes.

### Do Not Simply Crank Up Threads Until the Server Crashes

The learning goal is **verifying invariants**, not causing a denial-of-service. Run against a lab replica set with clear resource budgets, ramp-ups, timeouts, and cleanup. High thread counts can spike transaction retries without indicating broken database atomicity.

## 45. Testing a Retry Storm

A realistic scenario:

```text
50 original requests
Each client times out and retries 3 times
=> up to 200 API calls
```

With stable idempotency keys:

- At most 50 **logical orders**, never 200.
- Retries return existing results.
- Stock is never deducted multiple times for one `requestId`.
- Payments/emails are never sent multiple times.

A test can generate 50 distinct `requestId`s and submit each four times. Once all calls settle, assert:

```text
orders count <= 50
unique(tenantId, requestId) count == orders count
total stock decremented == SUM(reserved quantities)
```

Do not assume all 50 orders succeed if initial stock is lower. Expected successes depend on `initialStock` and `quantity`.

## 46. Testing Concurrent Cancellation and Stock Release

Two requests cancel the same `RESERVED` order concurrently:

```text
Order status RESERVED, qty=2
Stock available=3

Cancel A -------------------\
                             --> both observe RESERVED
Cancel B -------------------/

Expected:
  Order transitions to CANCELLED once
  Stock rises from 3 to 5 once
```

Stock must never reach `available=7`. To guarantee this, the conditional status update and stock increment must execute in the **same transaction**, or via an idempotent workflow enforcing equivalent invariants.

### Testing Concurrent Placement and Cancellation

In real systems, these interleave:

```text
Reserve new order / release old order / restock
```

All touch the same inventory document, raising write contention. Verify invariants across multi-transition workloads, not only "20 buys, 5 items."

## 47. Can a Single Document Avoid Transactions?

One model:

```javascript
{
  _id: "SKU-BOOK-001",
  available: 5,
  reservations: [
    { requestId: "REQ-1", quantity: 1 }
  ]
}
```

If everything needed together sits in one document, an update pipeline or conditional update modifies stock and the reservation list **atomically**.

However:

- The `reservations` array can grow unboundedly.
- A hot SKU suffers high contention.
- BSON documents have size limits.
- Orders also need addresses, payments, fulfillment, and audits in separate scopes.
- Multi-SKU orders span multiple documents.

This pattern fits narrow cases, **not as a universal replacement for an `orders` collection**.

## 48. Reservation Ledger or Saga: When Is It Appropriate?

Very large systems often decouple:

```text
Order intent / idempotency record
       |
       v
Reservation command
       |
       v
Atomic stock claim + reservation ledger
       |
       v
Payment / fulfillment events
       |
       v
Final state / compensation
```

This forms an **eventually consistent workflow** featuring:

- Idempotency keys.
- Per-SKU conditional updates.
- A state machine for `NEW`/`RESERVED`/`FAILED`/`RELEASED`.
- Outbox and at-least-once delivery.
- Bounded retries and dead-letter handling.
- Reconciliation between ledger and materialized stock.

The invariant `stock.available + SUM(active reservations) = initial + restocks` still applies, though steps commit asynchronously; the system must define **valid intermediate states** and compensation procedures.

## 49. Writing a Consistency Contract for the API

Example:

```http
POST /api/orders
Idempotency-Key: req-1001
Content-Type: application/json

{
  "sku": "SKU-BOOK-001",
  "quantity": 1
}
```

The server derives `tenant` from the authenticated principal, never trusting client-supplied values.

Sample response:

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "orderId": "order-1001",
  "status": "RESERVED"
}
```

On retry with matching key and payload, the API returns the existing order/result per contract (e.g., `200 OK` or the stored status code). When out of stock, return a consistent business error (`409`/`422` per API spec). On same key with different payload, return a conflict. On unknown commit outcome, never declare definitive success or failure until reconciled.

### When May the API Return Success?

Return `RESERVED` success only after transaction commit is confirmed under the durability contract. Never return "reserved" right after `insertOne()` inside an uncommitted callback.

## 50. Read Concern and Write Concern in Practice

A transaction may specify:

```java
TransactionOptions.builder()
    .readConcern(ReadConcern.SNAPSHOT)
    .writeConcern(WriteConcern.MAJORITY)
    .readPreference(ReadPreference.primary())
    .build();
```

Meaning:

- `SNAPSHOT` gives reads inside the transaction a consistent snapshot per MongoDB semantics.
- `MAJORITY` configures commit acknowledgment durability across the replica set.
- `primary` is required for transactions performing writes.

Never assume `SNAPSHOT` alone prevents overselling: **the `available >= quantity` filter** directly guards stock levels. Never assume `MAJORITY` eliminates network failures; `UnknownTransactionCommitResult` can still require retry/reconciliation.

### Post-Test Reconciliation

Once all futures finish and no fixture writers remain active, read final state from the primary with appropriate read/write concerns. Never assert cross-collection invariants from two separate `find()` queries while concurrent writers are still committing, as snapshot timestamps will differ.

## 51. Sharded Clusters and Cross-Shard Transactions

If `inventory` and `orders` are sharded:

- Transactions can span multiple shards under supported topology/conditions.
- Cross-shard transactions incur higher overhead and latency.
- `mongos` routing, shard keys, and unique index constraints must be reviewed.
- A unique idempotency key on a sharded collection must satisfy your MongoDB version's **unique index / shard key rules**.
- Queries by tenant/`requestId` should support targeted shard routing.

Never assume creating `{tenantId:1,requestId:1}` as unique on a sharded collection with an incompatible shard key guarantees global uniqueness without verifying constraints and topology.

In the lab, start with an **unsharded replica set** to observe concurrency mechanics clearly before scaling to shards.

## 52. Mock Tests vs. Real Integration Tests

A mocked repository can return:

```text
findStock -> 5
updateStock -> success
insertOrder -> success
```

yet **fails to simulate**:

- Two concurrent clients reading the same stale snapshot.
- Write conflicts across transactions.
- Real unique index enforcement.
- Replica set sessions and transaction commits.
- Network disconnects and unknown commit results.
- Replication durability / majority behavior.

Therefore:

| Test Level | Purpose |
| --- | --- |
| Unit test | Quantity validation, idempotency payload checks, API mapping |
| MongoDB integration | Atomic `$inc`, unique index, transaction rollback |
| Concurrency integration | 20–100 writers on one SKU and same-key retries |
| Fault injection | Mid-transaction exception leaves zero partial state |
| Load/stress | Throughput, retries, contention, operational stability |
| E2E API | Status codes, tenant auth, idempotency header, zero overselling |

Mock tests are valuable, but never sufficient proof that MongoDB transactions behave correctly.

## 53. Control Exercise: Intentionally Reproducing a Lost Update

In an isolated lab, you can write:

```java
Document stock = inventory.find(
    Filters.eq("_id", sku)).first();

int current = stock.getInteger("available");

// Synchronize threads here so both read the same stale count.
readBarrier.await();

inventory.updateOne(
    Filters.eq("_id", sku),
    Updates.set("available", current - 1)
);
```

With two tasks both reading `available=2`, both set it to `1`. Then run the `$inc` + filter version to compare:

```java
inventory.updateOne(
    Filters.and(
        Filters.eq("_id", sku),
        Filters.gte("available", 1)
    ),
    Updates.inc("available", -1)
);
```

Expected:

- The read–modify–write version loses one decrement.
- The conditional `$inc` from two independent orders reduces stock cleanly to 0 when both succeed.

**This exercise exists solely to reproduce the bug on synthetic data**—never ship the intentionally broken pattern to production.

## 54. Control Exercise: Without Transactions

Create a deliberately non-transactional flow:

```text
update stock via conditional $inc -> success
raise injected exception
insert order -> skipped
```

Expected result **without a transaction**:

```text
stock decremented
no order created
invariant failed
```

Then wrap the exact same fault injection inside a transaction:

```text
BEGIN
update stock
raise injected exception
ABORT

stock unchanged
no order created
invariant holds
```

These two control tests clarify what transactions solve: **cross-document atomicity**, not just avoiding stale reads on one counter.

## 55. Comprehensive Test Matrix

| ID | Scenario | Pass Invariant / Condition |
| --- | --- | --- |
| CONC-01 | 1 request qty=1 when stock=5 | 1 order, `available=4` |
| CONC-02 | 1 request qty=6 when stock=5 | 0 orders, `available=5` |
| CONC-03 | 20 distinct-key requests, stock=5 | 5 orders, `available=0` |
| CONC-04 | 2 distinct-key requests, stock=1 | 1 order, `available=0` |
| CONC-05 | 2 requests same key/payload | 1 order, stock decremented once |
| CONC-06 | Same key, different quantity | Only one payload accepted |
| CONC-07 | Nonexistent SKU | No order and no inventory document created |
| CONC-08 | Quantity=0 or negative | Rejected before transaction |
| CONC-09 | Fault after order insert | Neither order nor stock change committed |
| CONC-10 | Fault after stock decrement | Neither order nor stock change committed |
| CONC-11 | Retry on transient write conflict | Final outcome never oversells |
| CONC-12 | Commit outcome unknown | Reconciled by stable request key |
| CONC-13 | 40 requests, stock=10 | 10 orders, `available=0` |
| CONC-14 | 100 duplicate API retries | Does not create 100 orders for one request |
| CONC-15 | Cancel twice | Stock released exactly once |
| CONC-16 | Concurrent place and cancel | Consistent per state machine |
| CONC-17 | Multi-SKU order | Either all SKUs reserved or none |
| CONC-18 | Bulk test hits unexpected timeout | Test fails/unknown, never disguised as OOS |
| CONC-19 | Unique request index missing | Test setup fails; never claim idempotency |
| CONC-20 | Raw writer mutates stock outside contract | Audit detects broken invariant |
| CONC-21 | App restarts after commit | Retry does not double-order |
| CONC-22 | Replica set failover in lab | Outcome/retry and consistency verified |
| CONC-23 | Read from lagging secondary | Do not prematurely declare failure |
| CONC-24 | Multi-tenant same `requestId` | Uniqueness properly scoped per tenant |

**There is no need to cram every concurrency case into one giant JUnit method.** Give each case isolated fixtures, timeouts, cleanup, expected business outcomes, and clear error classification for fast root-cause isolation.

## 56. Observing Throughput and Contention

Metrics to collect:

| Metric | Meaning |
| --- | --- |
| Successful reservations/s | Business throughput |
| Out-of-stock rejections/s | Legitimate inventory exhaustion rate |
| Duplicate idempotent requests/s | Client retry rate |
| Same-key different-payload conflicts | API misuse signal |
| Transaction retries/s | Contention or transient errors |
| Write conflict errors/s | Competing writes on same documents |
| Unknown commit results | Network/replication issues needing reconciliation |
| p50/p95/p99 latency | Customer experience |
| MongoDB pool checkout wait | Connection pool bottleneck |
| CPU, memory, disk IOPS | Resource ceilings |
| Orders lacking matching stock reservation | Invariant breach requiring investigation |
| `available` below zero | Critical violation |

### A Hot SKU Is a Natural Contention Point

A single inventory document targeted by tens of thousands of buyers concurrently becomes a **logical serialization point** for decrements. Atomicity prevents overselling, not unbounded throughput bottlenecks.

Optimization paths include:

- Admission control / rate limiting at the API.
- Idempotent ordering queues.
- Partitioned quotas/tokens with explicit reconciliation.
- Dedicated reservation services.
- Shorter transactions touching fewer documents.
- Avoiding unbounded thread pools.

These techniques trade off consistency vs. availability, so keep invariants guarded with tests and audits.

## 57. Access Control and Tenant Scope in Practice

A query like:

```javascript
db.orders.findOne({ requestId: "req-001" });
```

can match another tenant's order if `requestId` is only unique **within a tenant**. When reconciling:

```javascript
db.orders.findOne({
  tenantId: "tenant-demo",
  requestId: "req-001"
});
```

In APIs, `tenantId` must come from the authenticated principal or authorized context, never from an unchecked client parameter.

### The Database Account Does Not Know HTTP Users

A Java service typically connects to MongoDB with a single service credential granted collection access. MongoDB RBAC restricts that service account, **not which HTTP user owns which order**. Tenant/owner authorization must be enforced in application queries and commands.

### Cross-Tenant Tests

Two tenants may reuse `requestId="req-1"` when the unique key includes `tenantId`. Yet user A must never read or cancel user B's order; test GET/PATCH/DELETE and error responses explicitly.

## 58. Designing Safe Cleanup for Concurrency Tests

A JUnit test failing midway can leave fixtures behind. Never call:

```javascript
db.dropDatabase();
```

in a lab environment shared across multiple CI jobs.

Instead:

1. Each test generates a unique `tenantId` and `sku`.
2. After all futures complete, clean up `orders` scoped to that `tenantId`/`testRunId`.
3. Clean up `inventory` scoped to the test SKU.
4. Never delete documents outside test scope.
5. If failures require preserving evidence, capture sanitized IDs and results.
6. Use a fixture-admin identity distinct from the service account tested for business authorization.

If cleanup runs while a worker thread is still writing, tests produce baffling results. Ensure all workers have finished or been cleanly cancelled before cleanup.

## 59. Common Design Mistakes

| Mistake | Consequence | Better Approach |
| --- | --- | --- |
| Read stock then `$set(available-1)` | Lost update | Conditional `$inc` |
| `$inc(-qty)` without `available >= qty` | Negative stock | Conditional query predicate |
| Decrement then insert order without transaction | Stock deducted, no order | Transaction or compensation |
| Insert order then decrement without transaction | Order without stock | Transaction or state machine |
| New `requestId` on retry of same intent | Double order | Stable idempotency key |
| Have `requestId` without unique index | Duplicate orders | Database unique constraint |
| Catch all duplicates and return success | Key reuse with changed payload hidden | Read + compare payload |
| Enable `upsert:true` on stock decrement | Synthesizes bad stock / duplicate key | `upsert:false` |
| Retry transaction containing payment call | Double charge | External idempotency / outbox |
| Map all errors to out-of-stock | Masks network/transaction failures | Classify exceptions explicitly |
| Use `@Version` instead of two-collection transaction | Partial writes | Multi-document transaction |
| Assert only `available>=0` | Misses order/stock mismatch | Assert sum invariant |
| Run 100 threads on one `ClientSession` | Violates session concurrency rules | One session per transaction |
| Test on standalone and drop transaction | Atomicity untested | Replica set / sharded lab |
| Read lagging secondary to assert order missing | False negative | Reconcile per consistency policy |
| Call `dropDatabase` in shared CI | Wipes other jobs' data | Per-test IDs, scoped cleanup |
| Include `CANCELLED` orders in reservation sum | Skewed reconciliation | Sum active reservation statuses |
| Assert only order count | Misses wrong quantities or stock | Assert count + quantities + stock |
| Trust unverified client `tenantId` | Cross-tenant access | Derive scope from principal |
| Hold transaction open waiting on payment | Contention / timeouts | Commit reservation, then async workflow |

## 60. Runbook When Overselling or Inventory/Order Drift Is Detected

### Step 1 — Classify the Symptom

```text
inventory.available < 0?
SUM(active reservations) exceeds initial + restocks?
Duplicate (tenantId,requestId) orders exist?
RESERVED orders exist without stock deduction?
Stock deducted without corresponding orders?
```

### Step 2 — Contain Impact

- Pause or rate-limit ordering on the affected SKU per incident policy.
- Do not run bulk stock-increment scripts before reconciling.
- Preserve sanitized request IDs, correlation IDs, timings, and driver errors.
- Check retry storms, message redeliveries, and recent deployments.

### Step 3 — Audit All Write Paths

- Do all writers enforce `available >= qty`?
- Are any read–modify–write paths using `repository.save()` remaining?
- Do order inserts and stock decrements share the **same session/transaction**?
- Does the unique idempotency index actually exist?
- Did any code path enable `upsert:true` inappropriately?
- Were timeouts/unknown commits retried with new request IDs?

### Step 4 — Reconcile Data

- Choose an appropriate snapshot or write-pause window to evaluate invariants.
- Group orders by SKU, tenant, and status.
- Check stock movements, returns, and restocks.
- Separate in-flight transactions/CDC lag from committed data.
- Verify downstream payment/fulfillment state before adjusting stock.

### Step 5 — Recover Safely

- Issue only business-approved **compensating records/adjustments**.
- Never delete paid orders just to "make numbers match."
- Use transactions and idempotency for compensating steps.
- Add regression integration tests reproducing the bug before rolling out fixes.
- Monitor invariant violations and alerts post-deployment.

## 61. Exercises and Answers

### Exercise 1. Lost Update

Stock is 3. Two threads both read 3 and run `$set:{available:2}`. How many units are actually deducted?

**Answer:** Only 1 may be reflected on the document, even though both threads believe they sold 1. That is a lost update.

### Exercise 2. Atomic Update

Write a MongoDB command deducting 2 units only if at least 2 remain.

**Answer:**

```javascript
db.inventory.updateOne(
  { _id: "SKU-A", available: { $gte: 2 } },
  { $inc: { available: -2 } }
);
```

### Exercise 3. Out of Stock

Does `matchedCount=0` for `{_id:sku,available:{$gte:qty}}` definitely mean the SKU does not exist?

**Answer:** No. The SKU may exist with insufficient stock. Handle according to business policy.

### Exercise 4. Deduct Stock Then Insert Order

Stock deduction succeeds, but order insert fails. Which invariant breaks?

**Answer:** Inventory decreased without a corresponding reservation/order. Use a multi-document transaction or controlled compensating workflow.

### Exercise 5. Insert Order Then Deduct Stock

Order insert succeeds, stock decrement fails. Can you return `201 Created` normally?

**Answer:** No, if the order status implies reserved inventory. Abort or transition state per business workflow rather than returning a false success.

### Exercise 6. 20 Requests

`stock=5`, 20 distinct requests, `qty=1`. With proper transaction + unique index, what is the final expected state?

**Answer:** 5 `RESERVED` orders, 15 out-of-stock rejections, and `stock=0`, assuming all attempts settle per policy.

### Exercise 7. Unique SKU

Should you create a unique index on `orders.sku`?

**Answer:** No, one SKU can appear in many orders. A unique idempotency key is appropriate instead.

### Exercise 8. Idempotency

Two HTTP calls share `(tenant, requestId, sku, quantity)`. Afterward, stock is deducted twice. Is this valid?

**Answer:** No. The same logical request must create at most one order and deduct stock once.

### Exercise 9. Different Payload

Same `requestId`, but the second call sends `quantity=10` instead of `1`. Should an upsert overwrite quantity?

**Answer:** No. Return an idempotency conflict per contract.

### Exercise 10. Unique Index

The app runs `existsByRequestId` before inserting, without a unique index. Can concurrent clients create duplicates?

**Answer:** Yes, due to the race between check and insert. A database unique constraint is required.

### Exercise 11. Session

Inside a transaction, order insert uses `session`, while inventory update omits `session`. Is atomicity guaranteed?

**Answer:** No. An operation omitting the session executes outside the transaction.

### Exercise 12. Mid-Transaction Failure

Order insert succeeds inside a transaction, then an exception is thrown before updating stock. Is the order committed?

**Answer:** No, assuming the transaction aborts properly. Tests confirm the order does not exist in committed state.

### Exercise 13. Write Conflict

Two transactions update the same inventory document concurrently. One hits a transient write conflict. Does that mean overselling occurred?

**Answer:** No. It is a concurrency signal requiring retry/abort per semantics; final invariants determine correctness.

### Exercise 14. Retry Side Effect

Code calls a payment gateway inside a `withTransaction` callback. What is the risk?

**Answer:** The callback can re-execute on retries, while external payments do not roll back with MongoDB transactions—risking double charges.

### Exercise 15. Unknown Commit

A client disconnects right after sending commit. Should it generate a new `requestId` and retry?

**Answer:** No. The transaction may have committed; keep the stable idempotency key and reconcile.

### Exercise 16. Out-of-Stock Exception

When stock update returns `matchedCount=0`, the service catches the exception and still returns the order ID from the transaction. Is this right?

**Answer:** No. The transaction must abort so no `RESERVED` order commits without stock.

### Exercise 17. Negative Quantity

A request with `quantity=-2` reaches `$inc:{available: -quantity}`. What goes wrong?

**Answer:** Subtracting a negative number increases stock and breaks invariants. Validate `quantity > 0` before operating.

### Exercise 18. Inventory Upsert

Why should `upsert:true` never be enabled on conditional stock decrements?

**Answer:** No match can mean insufficient stock; upsert would try creating a record, causing duplicate-key errors or corrupt negative stock.

### Exercise 19. Transaction vs. `@Version`

Does `@Version` on inventory automatically roll back an order insert in another collection?

**Answer:** No. It manages optimistic locking on entity save paths, not multi-document transactions.

### Exercise 20. Multi-SKU

An order has `SKU-A qty 1` and `SKU-B qty 2`. A has stock, B does not. With a proper transaction, does A's stock decrease?

**Answer:** Neither change commits; the entire transaction must abort.

### Exercise 21. Cancellation

Two requests cancel a `qty=2` order concurrently. Stock increases by 4. What is the bug?

**Answer:** Non-idempotent release. The conditional status transition and stock increment must run in the same transaction, adding stock once.

### Exercise 22. Concurrency Testing

A JUnit test creates two entity copies without real MongoDB. Has it proven unique index and transaction behavior?

**Answer:** No. Integration tests against a transaction-capable MongoDB replica set/sharded deployment are required.

### Exercise 23. Barrier

Why use `CountDownLatch` when testing 40 requests?

**Answer:** To release workers nearly simultaneously, maximizing race and contention conditions to stress invariants.

### Exercise 24. Assertions

A test asserts only that stock is non-negative. Is that enough?

**Answer:** No. Check order count, summed quantities, uniqueness, and the stock–order relationship.

### Exercise 25. Reconciliation

Initial stock 10, final 4, three `RESERVED` orders of qty 2 each. Does the invariant hold?

**Answer:** Yes in a lab with no restocks or cancellations: `4 + 3*2 = 10`.

### Exercise 26. Broken Reconciliation

Initial stock 10, final 2, three `RESERVED` orders of qty 2 each. What is wrong?

**Answer:** `2 + 6 = 8`, leaving 2 units unaccounted for. Audit stock mutations, order statuses, failed writes, and compensation logic.

### Exercise 27. One Hot SKU

Increasing threads 10x increases write conflicts and latency. Did MongoDB break atomicity?

**Answer:** No. That is contention on the single inventory document. Verify final invariants, throughput, and add backpressure.

### Exercise 28. Tenant Scope

Two tenants use the same `requestId`. Does a unique index on `requestId` alone fit all models?

**Answer:** No, if keys only need per-tenant uniqueness. Use a compound unique index on `(tenantId, requestId)` and enforce tenant authorization.

### Exercise 29. Replica Set

A transaction test on standalone fails with `"transaction numbers only allowed ..."`. Can you remove the transaction and keep asserting cross-document atomicity?

**Answer:** No. A transaction-capable topology is required.

### Exercise 30. Cleanup

Multiple CI jobs share the lab database. Should each test call `db.dropDatabase()`?

**Answer:** No. Use per-test `tenantId`/`SKU`/`testRunId` values and run scoped cleanup only after threads finish.

## 62. Implementation Checklist for the Practice Lab

### Environment

- [ ] Lab MongoDB is a transaction-capable replica set or sharded deployment.
- [ ] Client uses a dedicated URI and least-privilege credentials without logging secrets.
- [ ] `orders` has a unique index matching the approved idempotency scope.
- [ ] `inventory` has numeric `available` and consistent SKU IDs.
- [ ] Fixtures are isolated from production; each test uses its own SKU/tenant.

### Data Correctness

- [ ] `quantity` is validated as a positive integer.
- [ ] Decrement uses atomic `$inc` with `available >= quantity`.
- [ ] No unguarded read–modify–write without CAS.
- [ ] Inventory decrement never uses `upsert:true`.
- [ ] Order insert and inventory decrement share the same session/transaction.
- [ ] `matchedCount=0` aborts rather than committing a `RESERVED` order.
- [ ] Unique request ID blocks duplicate orders.
- [ ] Same key / different payload returns a conflict.
- [ ] Cancel/release increments stock at most once.

### Retries and Transactions

- [ ] Transaction callbacks are short and contain zero external side effects.
- [ ] Driver retry semantics/labels are understood and bounded.
- [ ] Unknown commit outcomes are never assumed to be guaranteed failures.
- [ ] Retries preserve the exact idempotency key.
- [ ] Outbox/downstream consumers are idempotent for events and payments.
- [ ] Write/read concerns meet business RPO and consistency requirements.

### Testing

- [ ] Baseline single-request and out-of-stock tests exist.
- [ ] Intentionally broken lost-update control test exists in lab for contrast.
- [ ] Concurrency tests cover competing requests under scarce stock.
- [ ] Tests cover duplicate `requestId` and mismatched payloads.
- [ ] Fault injection tests run after each write inside the transaction.
- [ ] Tests cover multi-SKU orders and cancellations.
- [ ] Assertions verify `finalStock + SUM(reserved) = initial`.
- [ ] Unexpected MongoDB errors fail tests rather than masquerading as OOS.
- [ ] Test cleanup never deletes other jobs' data.

### Observability and Operations

- [ ] Conflicts, duplicate keys, transaction retries, and p99 latency monitored.
- [ ] Dashboards/jobs monitor stock anomalies and reconciliation.
- [ ] Hot-document throughput limits and load shedding understood.
- [ ] Runbooks exist for overselling, timeouts, and unknown outcomes.
- [ ] Compensation never runs before reconciling payments/fulfillment.

## 63. Summary

Concurrency testing when **updating inventory and creating orders** exercises several core MongoDB concepts together: single-document atomic writes, conditional predicates, unique indexes, multi-document transactions, sessions, retryable errors, and idempotency.

If an application reads stock and issues `$set` from Java, concurrent requests cause **lost updates**. Switching to **`updateOne({_id,available:{$gte:qty}},{$inc:{available:-qty}})`** prevents overselling on a single inventory document. Yet when an **order must also be inserted in another collection**, two separate writes still leave partial failure states. Multi-document transactions ensure both operations **commit or abort together**, provided both share the same session and business predicates are enforced.

Transactions **do not replace** unique idempotency keys: retried requests must create at most one order and deduct stock once. Nor do transactions replace backpressure, domain validation, or protecting external payments/emails from duplicate execution. When multiple transactions contend on the same SKU, write conflicts and retries are normal behaviors to handle—not evidence that MongoDB broke atomicity.

Lab completion is not "40 calls threw zero exceptions." Success means **once all operations settle, stock is never negative, zero duplicate business orders exist, total deducted stock matches active reservations, and zero partial commits occur between orders and inventory**. From there, teams can apply the exact same testing rigor to e-wallets, ticket caps, quotas, room holds, resource allocation, and other concurrent workflows.

### Official References

- [MongoDB Manual — Atomicity and Transactions](https://www.mongodb.com/docs/manual/core/write-operations-atomicity/)
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/)
- [MongoDB Manual — Transactions Production Considerations](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/)
- [MongoDB Manual — updateOne](https://www.mongodb.com/docs/manual/reference/method/db.collection.updateOne/)
- [MongoDB Manual — $inc](https://www.mongodb.com/docs/manual/reference/operator/update/inc/)
- [MongoDB Manual — Unique Indexes](https://www.mongodb.com/docs/manual/core/index-unique/)
- [MongoDB Manual — findAndModify](https://www.mongodb.com/docs/manual/reference/method/db.collection.findAndModify/)
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
- [MongoDB Java Sync Driver — Transactions](https://www.mongodb.com/docs/drivers/java/sync/current/crud/transactions/)
- [MongoDB Java Sync Driver Documentation](https://www.mongodb.com/docs/drivers/java/sync/current/)
- [Spring Data MongoDB Reference — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
