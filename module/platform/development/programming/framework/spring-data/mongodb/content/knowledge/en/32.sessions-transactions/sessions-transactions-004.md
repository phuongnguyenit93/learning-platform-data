# @Transactional at the Service Layer with Multiple Repositories/Templates

## 1. When a Business Operation Requires Multiple MongoDB Writes

A customer buys two items in an e-commerce application. To record the order, the system may have to:

1. Deduct or reserve inventory quantity.
2. Create an order.
3. Write an inventory movement log.
4. Record an event for another system to process once the order is confirmed.

If the program executes each operation independently:

~~~text
MongoTemplate.updateFirst(inventory)  -> succeeded
OrderRepository.insert(order)          -> succeeded
MovementRepository.insert(movement)    -> failed

Result: inventory was reduced, the order exists, but the log is missing.
~~~

An **atomic update on a single document** does not automatically turn three writes across three different documents or collections into an **all-or-nothing** unit. When business rules require these MongoDB writes to **commit together or roll back together**, we need a **MongoDB multi-document transaction**.

Spring Data MongoDB provides **`MongoTransactionManager`** and integrates with Spring's **`@Transactional`**. Placing the annotation at the **service layer** groups repository and `MongoTemplate` calls into the same transaction, rather than scattering transactions on individual repository methods.

This lesson **@Transactional at the Service Layer with Multiple Repositories/Templates** belongs to the **Sessions and Transactions** chapter of the **SPRING_DATA_MONGODB** module. The module covers connecting and mapping documents, operating on MongoDB via repositories or `MongoTemplate`, query design, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.

After this lesson, you will be able to:

- Configure `MongoTransactionManager` with the appropriate `MongoDatabaseFactory`.
- Understand **`ClientSession`**, transactions, and Spring's session propagation mechanism.
- Use **`@Transactional`** on services calling multiple `MongoRepository` beans and `MongoTemplate`.
- Verify real commits/rollbacks rather than just seeing annotations in code.
- Explain **self-invocation** bugs, swallowed exceptions, multiple transaction managers, and crossing thread boundaries.
- Handle **write conflicts**, retries, unknown commit outcomes, and idempotency.
- Distinguish MongoDB transactions from external HTTP/payment calls.
- Build a **`ReactiveMongoTransactionManager`** variant and test on a replica set.

## 2. Distinguishing Single-Document Atomicity from a Transaction

MongoDB guarantees atomicity for **a single write operation on one document**. For example:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    tenantId: "shop-a",
    available: { $gte: 2 }
  },
  {
    $inc: { available: -2, reserved: 2 }
  }
);
~~~

This is **one update on one document**, so the changes to `available` and `reserved` happen together. A multi-document transaction is unnecessary just to update two fields of the **same document** simultaneously.

However, if you must then insert an order:

~~~javascript
db.orders.insertOne({
  tenantId: "shop-a",
  requestId: "checkout-123",
  status: "RESERVED"
});
~~~

the update and insert **do not automatically commit/roll back together** when executed independently. A failure between the two statements can leave inventory modified with no order present.

| Scenario | Mechanism to Consider |
| --- | --- |
| Only decrementing quantity on one inventory document | Predicate `available >= qty` + atomic `$inc` |
| Decrementing `available` and incrementing `reserved` in the same inventory document | Single update with two `$inc` operators |
| Decrementing inventory and creating an order in two collections | MongoDB transaction if both must commit/roll back together |
| Creating order, movement, and outbox event in MongoDB | One transaction for the related writes |
| Deducting inventory and charging via external payment gateway | Saga, business states, idempotency/outbox |
| Merely reading a few documents for a report | Do not default to long-running transactions |

**A transaction does not replace business predicates in updates.** When deducting stock, you must still check `available >= quantity`; a transaction does not automatically know "do not oversell stock."

## 3. ClientSession as the Foundation of MongoDB Transactions

A MongoDB transaction is bound to a **`ClientSession`**. Operations that belong to the same transaction must execute on the appropriate session within that transaction's scope.

~~~mermaid
flowchart TB
    A["HTTP request / job"] --> B["CheckoutService.placeOrder"]
    B --> C["@Transactional + MongoTransactionManager"]
    C --> D["ClientSession / MongoDB transaction"]
    D --> E["MongoTemplate: update inventory"]
    D --> F["OrderRepository: insert order"]
    D --> G["MovementRepository: insert movement"]
    E --> H{"Commit or rollback?"}
    F --> H
    G --> H
    H -->|No error| I["Commit all three operations"]
    H -->|Rollback| J["Discard transaction changes"]
~~~

In the **synchronous** Spring Data MongoDB stack:

1. The Spring transaction interceptor invokes the transaction manager when a `@Transactional` method is called through the right proxy.
2. `MongoTransactionManager` creates/joins the transaction and binds the session to the current **thread** via Spring's resource synchronization mechanism.
3. `MongoTemplate` and repositories configured with the same `MongoDatabaseFactory` detect the bound session and join the transaction.
4. When the service finishes, Spring commits; when an error requiring rollback occurs, Spring aborts the transaction.

**Not every call to MongoDB in the JVM automatically joins.** If you instantiate a new `MongoClient`, open an independent session manually, or execute a MongoDB operation on another thread without preserving the proper context, that operation can run outside the transaction.

### 3.1. Session Does Not Mean Transaction

`ClientSession` can also serve other capabilities such as causal consistency. **Having a session** does not mean **a transaction has started**. Distinguish:

- Regular calls without a managed session.
- Calls inside a session without an active transaction.
- Calls inside a transaction started on a session.

In this lesson, **`@Transactional` + `MongoTransactionManager`** handles creating the synchronous transaction boundary.

### 3.2. Transaction-Bound Sessions Must Not Be Shared Arbitrarily

Do not store a `ClientSession` in a singleton bean or pass it across parallel requests. For imperative transactions, Spring manages the session in the appropriate execution scope; let `MongoTemplate`/repositories participate through official integration rather than holding a session in a global field.

## 4. Environment Requirements for Running Transactions

MongoDB multi-document transactions require a **compatible deployment**, such as a replica set or sharded cluster on a supported MongoDB Server version.

A **standalone `mongod`** is not a sufficient environment to properly test multi-document transactions. Running commands may raise an error like:

~~~text
Transaction numbers are only allowed on a replica set member or mongos
~~~

Consequently, an integration test using only standalone `mongod` can test regular CRUD operations yet fail as soon as `@Transactional` is enabled.

### 4.1. Conditions to Verify

- MongoDB Server supports transactions on the active topology.
- MongoDB Driver and Spring Data MongoDB are compatible generations.
- Repositories and `MongoTemplate` are configured against the **same MongoDB deployment** and participate via the appropriate factory/session.
- `MongoTransactionManager` is declared and transaction management is enabled.
- The database user has read/write privileges on all collections in the transaction.
- Required collections/indexes have been created/migrated before opening business transactions.
- Write concern, read concern, read preference, and transaction lifetime meet operational needs.

Transaction restrictions on sharded clusters, DDL operations, and allowed durations depend on server version. **Never assume `@Transactional` code works everywhere just because `MongoTemplate` connected successfully.**

### 4.2. Never Use Production to Test Rollback

Never deliberately delete orders or trigger transaction failures on a production database to verify behavior. Use a dedicated replica set for integration tests, such as Testcontainers or an equivalent test environment.

## 5. Three Collections in the Checkout Example

We use three collections:

| Collection | Role | Key Condition |
| --- | --- | --- |
| `inventories` | `available` and `reserved` per item | `available >= requested quantity` |
| `orders` | Records checkout by `requestId` | Unique `tenantId + requestId` |
| `inventory_movements` | Reservation audit log | Links `requestId`, `inventoryId`, and `quantity` |

Inventory document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439011"),
  tenantId: "shop-a",
  sku: "BOOK-101",
  available: NumberLong("8"),
  reserved: NumberLong("0")
}
~~~

Order document after successful reservation:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439012"),
  tenantId: "shop-a",
  requestId: "checkout-123",
  inventoryId: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberLong("2"),
  status: "RESERVED",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

Movement document:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439013"),
  tenantId: "shop-a",
  requestId: "checkout-123",
  inventoryId: ObjectId("507f1f77bcf86cd799439011"),
  quantity: NumberLong("2"),
  kind: "RESERVE",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

**Invariant definition:** a request to reserve 2 items deducts 2 from `available` and adds 2 to `reserved`, while creating the corresponding order and movement. Never persist a `"RESERVED"` order if inventory was not successfully reserved.

### 5.1. Java Models

~~~java
package com.example.checkout;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventories")
public record InventoryDocument(
    @Id ObjectId id,
    String tenantId,
    String sku,
    long available,
    long reserved
) {}

@Document(collection = "orders")
@CompoundIndex(
    name = "uk_orders_tenant_request",
    def = "{ 'tenantId': 1, 'requestId': 1 }",
    unique = true
)
public record OrderDocument(
    @Id ObjectId id,
    String tenantId,
    String requestId,
    ObjectId inventoryId,
    long quantity,
    String status,
    Instant createdAt
) {}

@Document(collection = "inventory_movements")
public record InventoryMovementDocument(
    @Id ObjectId id,
    String tenantId,
    String requestId,
    ObjectId inventoryId,
    long quantity,
    String kind,
    Instant createdAt
) {}
~~~

The records above are shown in one block for readability; in real Java projects, place each **public record** in its own file per Java rules.

### 5.2. Repository Interfaces

~~~java
package com.example.checkout;

import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, ObjectId> {

    Optional<OrderDocument> findByTenantIdAndRequestId(
        String tenantId, String requestId
    );
}

public interface InventoryMovementRepository
        extends MongoRepository<InventoryMovementDocument, ObjectId> {
}
~~~

Likewise, each **public interface** goes into its own source file. Spring Data generates repository implementations using the managed MongoDB mapping.

### 5.3. The Unique Index Must Actually Exist

The `@CompoundIndex` annotation is metadata; index creation depends on auto-index-creation or migrations.

~~~javascript
db.orders.createIndex(
  { tenantId: 1, requestId: 1 },
  {
    unique: true,
    name: "uk_orders_tenant_request"
  }
);
~~~

A transaction does not prevent the same `requestId` from being processed twice if the code lacks duplicate protection. A **unique index** enforces the data constraint; the **business workflow** must still compare payloads and handle retries.

## 6. Registering MongoTransactionManager

In a synchronous Spring Data MongoDB application, declare a transaction manager using the exact **`MongoDatabaseFactory`** used by `MongoTemplate`/repositories.

~~~java
package com.example.checkout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class MongoTransactionConfiguration {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory databaseFactory) {
        return new MongoTransactionManager(databaseFactory);
    }
}
~~~

**`@EnableTransactionManagement`** enables Spring to apply the transaction interceptor using the configured proxy mechanism. With Spring Boot, transaction management may already be enabled via auto-configuration; declaring it explicitly here makes the lesson easy to verify.

**The bean name `mongoTransactionManager`** lets you select the exact transaction manager when the app uses both MongoDB and another database.

### 6.1. Do Not Mistakenly Use DataSourceTransactionManager

If the application has JDBC/JPA alongside MongoDB:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public OrderDocument placeOrder(...) {
    // MongoDB operations.
}
~~~

Here `transactionManager` selects **`MongoTransactionManager`**. If omitted when multiple `PlatformTransactionManager` beans exist, default lookup can be ambiguous or pick an unintended manager.

**`DataSourceTransactionManager` or `JpaTransactionManager` cannot manage a MongoDB `ClientSession`.**

### 6.2. Do Not Arbitrarily Instantiate a New MongoClient/MongoTemplate

Bad example:

~~~java
// Do not create a separate client inside a @Transactional service.
MongoClient customClient = MongoClients.create(otherConnectionUri);
MongoDatabase rawDb = customClient.getDatabase("catalog");
rawDb.getCollection("orders").insertOne(document);
~~~

That call does not join the session bound by `MongoTransactionManager` to Spring Data operations. Use repositories/`MongoTemplate` sharing the same factory, or manage sessions/transactions manually when deliberately using the raw driver.

### 6.3. DatabaseFactory and Database Names

One transaction can work across MongoDB-supported collections on the same deployment, yet having **two `MongoDatabaseFactory` beans**, two `MongoClient` instances, or two `MongoTransactionManager` beans does not combine them into one global transaction.

If a transaction must span multiple datasources/clusters, evaluate a dedicated strategy; **one `@Transactional` on `MongoTransactionManager` is not a distributed transaction coordinator**.

## 7. Checkout Service Using MongoTemplate and Two Repositories

The service layer is where business boundaries belong. Example:

~~~java
package com.example.checkout;

import java.time.Instant;
import java.util.Optional;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;

public record CheckoutCommand(
    ObjectId inventoryId,
    String requestId,
    long quantity
) {}

@Service
public class CheckoutService {

    private final MongoTemplate mongoTemplate;
    private final OrderRepository orderRepository;
    private final InventoryMovementRepository movementRepository;

    public CheckoutService(
            MongoTemplate mongoTemplate,
            OrderRepository orderRepository,
            InventoryMovementRepository movementRepository) {
        this.mongoTemplate = mongoTemplate;
        this.orderRepository = orderRepository;
        this.movementRepository = movementRepository;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public OrderDocument reserve(
            String authenticatedTenantId,
            CheckoutCommand command) {

        validate(authenticatedTenantId, command);

        Optional<OrderDocument> existing =
            orderRepository.findByTenantIdAndRequestId(
                authenticatedTenantId, command.requestId());

        if (existing.isPresent()) {
            assertSameRequest(existing.get(), command);
            return existing.get();
        }

        Query filter = Query.query(
            Criteria.where("_id").is(command.inventoryId())
                .and("tenantId").is(authenticatedTenantId)
                .and("available").gte(command.quantity())
        );

        Update change = new Update()
            .inc("available", -command.quantity())
            .inc("reserved", command.quantity());

        var result = mongoTemplate.updateFirst(
            filter, change, InventoryDocument.class);

        if (!result.wasAcknowledged()) {
            throw new IllegalStateException(
                "Inventory write not acknowledged");
        }
        if (result.getModifiedCount() != 1) {
            throw new OutOfStockException();
        }

        Instant now = Instant.now();
        OrderDocument order = orderRepository.insert(
            new OrderDocument(
                new ObjectId(),
                authenticatedTenantId,
                command.requestId(),
                command.inventoryId(),
                command.quantity(),
                "RESERVED",
                now
            )
        );

        movementRepository.insert(
            new InventoryMovementDocument(
                new ObjectId(),
                authenticatedTenantId,
                command.requestId(),
                command.inventoryId(),
                command.quantity(),
                "RESERVE",
                now
            )
        );

        return order;
    }

    private static void validate(
            String tenantId, CheckoutCommand command) {
        if (tenantId == null || tenantId.isBlank()
                || command == null
                || command.inventoryId() == null
                || command.requestId() == null
                || command.requestId().isBlank()
                || command.quantity() <= 0) {
            throw new IllegalArgumentException(
                "Invalid checkout command");
        }
    }

    private static void assertSameRequest(
            OrderDocument existing, CheckoutCommand command) {
        if (!existing.inventoryId().equals(command.inventoryId())
                || existing.quantity() != command.quantity()) {
            throw new IllegalArgumentException(
                "Idempotency key reused with different payload");
        }
    }
}

public class OutOfStockException extends RuntimeException {
    public OutOfStockException() {
        super("Inventory unavailable");
    }
}
~~~

**Code organization note:** `CheckoutCommand`, `CheckoutService`, and `OutOfStockException` are separate public types and belong in separate Java files in a real project. The example omits HTTP/authentication layers to focus on transactions.

**`authenticatedTenantId`** must be determined by the server's authentication/authorization layer, never taken verbatim from an unverified user request parameter.

### 7.1. Three MongoDB Operations Inside One Boundary

~~~text
@Transactional CheckoutService.reserve(...)
    |
    +-- MongoTemplate.updateFirst(inventories)
    |       condition: available >= quantity
    |       update: inc(available,-quantity), inc(reserved,+quantity)
    |
    +-- OrderRepository.insert(orders)
    |
    +-- InventoryMovementRepository.insert(inventory_movements)
    |
    +-- Spring transaction interceptor: commit / rollback
~~~

All participate in the same transaction when bean wiring, transaction manager, and session binding are properly configured.

### 7.2. Do Not Omit the `available >= quantity` Predicate

**`@Transactional` does not automatically prevent overselling.** If requests simply run:

~~~java
new Update().inc("available", -quantity);
~~~

without the `available>=quantity` predicate, concurrent transactions can drive stock below zero. Keep the invariant directly in the filter and inspect `UpdateResult`.

### 7.3. Why Not Catch `OutOfStockException` Inside the Service?

`reserve` throws a `RuntimeException` when stock cannot be reserved. By default, Spring marks the transaction for rollback on this exception type.

If you catch the exception inside the service and return a normal error DTO **without marking rollback**, the transaction interceptor may see the method succeed and commit earlier writes.

### 7.4. Note on `requestId` Uniqueness

Reading for an existing order before creating **is not enough to prevent races**:

~~~text
Transaction A: does not see requestId
Transaction B: does not see requestId
Transaction A: insert order
Transaction B: insert order
~~~

A unique index on `tenantId+requestId` is mandatory protection. On duplicate/write conflict, the application must handle it **outside the failed transaction**, re-read state by `requestId`, and verify the payload. Never swallow the exception inside the transaction and keep writing.

## 8. When Are Commit and Rollback Decided?

For a service method managed by the Spring transaction interceptor:

~~~text
Proxy starts transaction
    -> service calls multiple repositories/templates
    -> method returns normally
    -> transaction manager commits
    -> proxy returns result to caller
~~~

If the method throws an exception matching rollback rules:

~~~text
Proxy starts transaction
    -> update inventory
    -> insert order
    -> insert movement fails
    -> exception exits service
    -> transaction manager aborts/rolls back
    -> caller receives exception
~~~

**MongoDB operations executed inside the transaction do not become individually committed data.** If the transaction aborts properly, the preceding inventory update and order insert also roll back.

### 8.1. Spring Default Rollback Rules

By default, Spring declarative transactions mark rollback on:

- **`RuntimeException`** and its subclasses.
- **`Error`**.

Meanwhile, checked exceptions (e.g., `IOException`) **do not always trigger rollback by default** under general `@Transactional` rules.

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    rollbackFor = Exception.class
)
public void placeAndExport(...) throws IOException {
    // When checked exceptions must also roll back the transaction.
}
~~~

Configure **`rollbackFor`** only when it genuinely fits the business contract. Avoid keeping a transaction open during slow file exports/HTTP calls hoping a checked `IOException` rolls back; you may need to separate data commit from file export.

### 8.2. Catching and Swallowing Exceptions Can Commit the Transaction

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public boolean unsafeReserve(CheckoutCommand command) {
    mongoTemplate.updateFirst(...);
    try {
        orderRepository.insert(...);
    } catch (RuntimeException ex) {
        log.warn("Order insert failed", ex);
        return false;
    }
    return true;
}
~~~

This is an **anti-pattern**. If the exception is swallowed with no rollback marker, the transaction interceptor may see the call complete normally and commit the inventory update.

A safer pattern:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public OrderDocument reserve(...) {
    mongoTemplate.updateFirst(...);
    return orderRepository.insert(...); // Let the exception propagate out.
}
~~~

If you want to translate the exception into a business exception, throw a new **`RuntimeException` subclass** or declare a matching `rollbackFor`:

~~~java
try {
    movementRepository.insert(movement);
} catch (org.springframework.dao.DataAccessException ex) {
    throw new InventoryWorkflowException(
        "Could not persist movement", ex);
}
~~~

Here `InventoryWorkflowException` should be an application-defined **`RuntimeException`**. Do not catch and return a normal error payload inside the same transaction.

### 8.3. Marking Rollback-Only When a Special Result Must Be Returned

Spring provides an API to mark the active transaction **rollback-only** in advanced cases:

~~~java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

TransactionAspectSupport.currentTransactionStatus()
    .setRollbackOnly();
~~~

However, this couples the service directly to the transaction mechanism. For business errors requiring abort of all operations, **throwing an explicit exception** is usually clearer and easier to test. When joining a transaction started elsewhere, rollback-only can also cause the caller to receive an exception when attempting to commit; the contract must be agreed upon.

### 8.4. Commit Can Also Fail

A service method finishing calculations and returning an in-memory object **does not guarantee the caller receives success**: the transaction interceptor still has to call commit.

If commit hits a network error or failover, the outcome state may be uncertain. Do not assume every commit error means guaranteed rollback; distinguish **definite transaction failure** from **unknown commit result**.

## 9. Why Place @Transactional at the Service Layer Instead of Scattering It on Repositories?

Repository methods such as `insert`/`save` may have transaction management applied in their own ways, yet when a service makes multiple calls:

~~~java
inventoryRepository.save(inventory);
orderRepository.insert(order);
movementRepository.insert(movement);
~~~

**Never assume they automatically share one multi-document transaction** merely because each method is atomic or carries a related annotation.

Place the boundary at the service:

~~~java
@Service
public class CheckoutService {

    @Transactional(transactionManager = "mongoTransactionManager")
    public void placeOrder(...) {
        // Multiple repositories + MongoTemplate share the same transaction.
    }
}
~~~

It corresponds to **one business unit**: "reserve stock and create order."

### 9.1. Do Not Make the Transaction Scope Too Wide

A service method should not keep a transaction open across:

~~~text
Read cart
-> call external discount API (2 seconds)
-> wait for bank payment (30 seconds)
-> update MongoDB
-> send email (3 seconds)
~~~

Long transactions increase snapshot/session retention time, raise contention, and easily hit transaction runtime limits.

Instead, split into business phases:

1. Validate and prepare data outside the transaction.
2. Open a **short** transaction to reserve stock and write order/movement/outbox.
3. Commit.
4. Worker/outbox calls external systems.
5. Use another transaction to transition state based on the result.

### 9.2. Do Not Annotate Every Controller Method with @Transactional Out of Convenience

Controllers handle serialization, HTTP streaming, and slow I/O. The service layer is better suited for short business boundaries reusable across APIs, schedulers, and message consumers.

## 10. Self-Invocation Bugs and the Spring Proxy

Under proxy-based `@Transactional`, the annotation only takes effect when the method is called **through the Spring-managed proxy**.

~~~java
@Service
public class CheckoutService {

    public void checkout(...) {
        reserveInTransaction(...); // Internal call via this.
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void reserveInTransaction(...) {
        // May NOT receive a transaction when called from checkout() on the same bean.
    }
}
~~~

The call **`checkout -> reserveInTransaction`** within the same object typically bypasses the transaction proxy, so the annotation on `reserveInTransaction` **is not applied** on that call.

### 10.1. Extract a Proxied Service

~~~java
@Service
public class CheckoutFacade {

    private final ReservationService reservationService;

    public CheckoutFacade(ReservationService reservationService) {
        this.reservationService = reservationService;
    }

    public void checkout(...) {
        reservationService.reserve(...); // Goes through another bean.
    }
}

@Service
public class ReservationService {

    @Transactional(transactionManager = "mongoTransactionManager")
    public void reserve(...) {
        // Mongo operations inside transaction.
    }
}
~~~

In real code, use parameters and implementations matching your application model. The key point is that the `@Transactional` method must be invoked through the proper proxy.

### 10.2. Common Proxy Pitfalls

| Invocation Pattern | Risk |
| --- | --- |
| `new CheckoutService(...)` directly | Object is not wrapped in a Spring AOP proxy |
| `this.reserve(...)` on the same bean | Self-invocation bypasses interceptor |
| `private` method | Unsuitable for proxy interception |
| `final` class/method with class-based proxy | May not be advised |
| `static` method | Not an instance method call per Spring proxy |
| Calling `MongoTemplate` on a new thread | Thread-bound session does not propagate automatically |
| `@Transactional` method called via Spring bean/proxy | Proper approach when manager is configured correctly |

Visibility details can vary by proxy strategy and Spring version. For predictability, **prefer non-final `public` service methods called through another Spring bean**.

### 10.3. Do Not Spawn Threads Inside a Synchronous Transaction

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeWork() {
    orderRepository.insert(order);

    CompletableFuture.runAsync(() -> {
        movementRepository.insert(movement);
    });
}
~~~

**The synchronous transaction's `ClientSession` is managed via thread context**; work running on another executor does not automatically join that session. Moreover, the transaction could commit before `CompletableFuture` completes.

If asynchronous work is needed, emit an event/outbox after commit or design a proper reactive transaction rather than splitting an imperative transaction across threads.

## 11. Propagation: REQUIRED, REQUIRES_NEW, and NESTED

Spring lets you specify propagation on declarative transactions. **The default is `REQUIRED`**:

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    propagation = Propagation.REQUIRED
)
public void reserve(...) {}
~~~

With `REQUIRED`:

- If the caller has no suitable active transaction, Spring starts a new one.
- If the caller already has a compatible transaction, the method joins the current transaction.

This fits cases where helper methods of a single business operation should share the same transaction.

### 11.1. REQUIRES_NEW Can Break All-or-Nothing Intent

**`REQUIRES_NEW`** expresses a desire for a transaction independent of the current one. Even when infrastructure supports suspending the active transaction, committing an independent transaction **breaks the assumption that all writes roll back together**.

Example:

~~~text
Checkout transaction A:
  -> calls independent audit method transaction B; B commits
  -> Checkout A fails and rolls back

Result: audit B may exist even though Checkout A never committed
~~~

Support for suspension/`REQUIRES_NEW` depends on the transaction manager and underlying resources. **Do not assume every JDBC propagation mode behaves identically on `MongoTransactionManager`.** If used, verify your Spring version, session binding, and actual semantics.

### 11.2. NESTED Is Not a MongoDB Savepoint

Do not assume MongoDB transactions support nested transactions with savepoints like some relational databases.

~~~java
@Transactional(propagation = Propagation.NESTED)
public void nestedOperation() {
    // Cannot arbitrarily roll back only to a MongoDB savepoint.
}
~~~

With MongoDB, check `MongoTransactionManager` limits and redesign the business workflow if partial cancellation is needed. **Do not rely on `@Transactional(NESTED)` to run an independent sub-transaction inside one session.**

### 11.3. Each Method Does Not Need Its Own Separate Transaction

If a `@Transactional` service invokes three repositories, Spring does not need to open three transactions. In the standard model, all operations share the boundary opened by the service, ensuring unified commit/rollback.

## 12. Read-Only, Read Concern, Write Concern, and Read Preference

A transaction defines **one commit unit**, while consistency/durability guarantees depend on **transaction options** and MongoDB configuration.

| Concept | Role |
| --- | --- |
| `readConcern` | Consistency level of data read inside the transaction |
| `writeConcern` | Acknowledgment and durability level of the commit |
| `readPreference` | Read target selection subject to transaction constraints |
| `maxCommitTime` | Limit related to commit processing if configured |
| `transactionLifetimeLimitSeconds` | Server-side transaction lifetime limit |

Designs requiring snapshot/majority durability must choose policies aligned with topology and MongoDB Server documentation. **Do not assume `@Transactional` alone guarantees every out-of-transaction read immediately sees changes on all replicas or provides majority durability.**

### 12.1. readOnly Does Not Turn MongoDB into a Cache

~~~java
@Transactional(
    transactionManager = "mongoTransactionManager",
    readOnly = true
)
public Report readReport(...) {
    // Synchronous MongoDB queries.
}
~~~

**`readOnly=true`** is Spring transaction metadata/intent and may influence whether a session/transaction is started or joined depending on the integration. Do not assume it is always a no-op hint or that it automatically allows secondary reads inside a MongoDB transaction.

Avoid keeping read-only transactions open during long streaming reports when a snapshot is not needed. Evaluate read concerns and appropriate report bounds.

### 12.2. Do Not Blindly Trust Default Write Concern for Every Use Case

When applications require strong durability, design write concern according to deployment policy, test failover, and define commit outcome checks. Spring Data allows configuring transaction options appropriately; align choices with MongoDB Server and business requirements.

### 12.3. Reads Outside the Transaction Are Not Part of the Snapshot

If a step reads from another `MongoClient` with a different session and uses that data to write inside the current transaction, the read data may not come from the same snapshot. Likewise, calling Redis or an HTTP service does not participate in the MongoDB session.

## 13. Concurrency Can Still Cause Write Conflicts

Two transactions attempting to update the same inventory document:

~~~text
Transaction A: read/modify inventory X
Transaction B: read/modify inventory X
Transaction A: commit
Transaction B: may receive a write conflict or transient transaction error
~~~

Transactions do not mean every concurrent request waits neatly and always succeeds. MongoDB may require abort/retry when detecting a conflict.

### 13.1. Is `available >= quantity` Still Needed Inside a Transaction?

**Yes.** The predicate:

~~~java
Criteria.where("_id").is(inventoryId)
    .and("tenantId").is(tenantId)
    .and("available").gte(quantity);
~~~

and update:

~~~java
new Update()
    .inc("available", -quantity)
    .inc("reserved", quantity);
~~~

remain the direct way to preserve the stock invariant. When a transaction aborts due to conflict, writes inside it do not commit; a retry must recalculate and re-check the predicate against fresh state.

### 13.2. Do Not Turn Write Conflicts into "Out of Stock"

A write conflict differs from **`modifiedCount=0`** caused by insufficient stock:

- **`modifiedCount=0`:** no document matched the predicate at the time of execution inside the transaction.
- **write conflict / transient transaction error:** the transaction could not finish against current state and may be eligible for retry.

If the business API needs accuracy, do not catch every `DataAccessException` and return "out of stock." Distinguish business errors from transaction coordination errors.

### 13.3. Retries Must Start Outside the Failed Transaction

A transaction that has aborted or been marked rollback-only cannot be "repaired" by retrying the update inside the same context and committing. For a transient transaction error, you must **start a fresh transaction**, repeat the necessary steps, and re-evaluate data.

Never place an infinite `while` retry loop inside a `@Transactional` service:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeRetryInsideTransaction() {
    for (;;) {
        try {
            updateInventory();
            return;
        } catch (RuntimeException error) {
            // Still in the failed transaction; infinite loop risk.
        }
    }
}
~~~

Retries must have **bounded attempts, backoff, error classification, request identity, and telemetry**. Under high contention, measure contention rather than merely raising retry counts.

## 14. UnknownTransactionCommitResult and Idempotency

Sometimes the server commits, yet the commit response is lost due to network/failover. Callers then face an **unknown commit outcome**.

The MongoDB driver/server expose transaction error labels such as:

- **`TransientTransactionError`**: an error indicating the whole transaction may be retried.
- **`UnknownTransactionCommitResult`**: the commit outcome could not be confirmed by the caller.

Error labels, retry behavior, and Spring exception translation vary by driver/Spring Data version; never match exceptions solely by string messages.

### 14.1. Do Not Conflate the Two Retry Types

| Situation | Handling Strategy |
| --- | --- |
| Transaction definitely aborted due to conflict | Can retry the **entire transaction** from the start |
| Commit result is unknown | Per driver/API mechanism, retry **commit** appropriately or reconcile by business key |
| Insufficient quantity | Do not retry indefinitely like an infrastructure error |
| Duplicate `requestId`, same payload | Return recorded result; do not deduct again |
| Duplicate `requestId`, different payload | Report conflict; do not silently reuse |

Spring Data offers extension hooks on `MongoTransactionManager` when custom commit/retry handling is needed; advanced implementations must follow transaction labels and official MongoDB driver documentation.

### 14.2. Business Idempotency Cannot Be Skipped

Even when the driver handles technical retries, a **client-resent HTTP request** can still launch a brand-new transaction. Use **unique `(tenantId, requestId)`** and persist an identifying payload to retrieve results after commit.

**Do not simply catch `DuplicateKeyException` and assume success**: look up the existing order and compare `inventoryId`/`quantity`/`tenant` and status.

### 14.3. Re-Reading After a Commit Error Needs a Fresh/Appropriate Session

After a transaction fails or commit is unknown, avoid reusing a rollback-only context for verification queries. Exit the failed transaction boundary and perform reconciliation/idempotency lookups in a separate valid transaction or read.

## 15. TransactionTemplate: An Explicit Boundary When Needed

Not every workflow is easy to express via annotations. Spring offers **`TransactionTemplate`** with `PlatformTransactionManager`:

~~~java
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public OrderDocument reserveWithTemplate(
        MongoTransactionManager mongoTransactionManager,
        CheckoutCommand command) {

    TransactionTemplate tx =
        new TransactionTemplate(mongoTransactionManager);

    return tx.execute(status -> {
        // Example: update inventory, insert order, insert movement
        // via Spring Data beans sharing the same MongoDatabaseFactory.
        return doReserveSteps(command);
    });
}
~~~

**`doReserveSteps`** is an illustrative business helper to implement, not a built-in Spring API. `TransactionTemplate` opens/closes a synchronous boundary around the callback, making the start/end points visible right in the code.

### 15.1. When to Use It?

- A job requiring an explicit transaction boundary.
- A retry orchestrator wanting to open a **fresh transaction per attempt**.
- Separating short MongoDB steps from long I/O operations.
- Independent rollback testing.

Do not use `TransactionTemplate` inside `@Transactional` just as an "extra safety layer" without understanding propagation: by default the callback joins the existing transaction rather than creating a distinct one.

### 15.2. Do Not Wrap Transactions Around Outbound API Calls

~~~java
// Do not keep a Mongo transaction open while calling a payment gateway.
tx.execute(status -> {
    reserveInventory();
    paymentGateway.charge(...); // External HTTP, not part of Mongo transaction.
    return saveOrder();
});
~~~

If the payment gateway captures funds and MongoDB later rolls back, the MongoDB transaction **does not automatically refund the charge**. Separate phases using reservation/outbox/saga with replay handling, unknown-state handling, and compensation.

## 16. Outbox: Emitting Post-Commit Events Without Losing Track

Suppose checkout must notify the fulfillment system when an order is reserved. Do not call the message broker directly hoping it rolls back with MongoDB:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafeCheckout(...) {
    reserveInventory();
    orderRepository.insert(order);
    messageBroker.send("order-reserved", payload);
    movementRepository.insert(movement);
}
~~~

If `messageBroker.send` succeeds and `movement` insert fails, **MongoDB rolls back**, while the external message may already reach consumers. Consumers will receive a notification for an uncommitted order.

### 16.1. Transactional Outbox in MongoDB

Instead of sending immediately, insert a document into **`outbox_events`** inside the same MongoDB transaction:

~~~javascript
{
  _id: ObjectId("507f1f77bcf86cd799439014"),
  tenantId: "shop-a",
  eventId: "event-checkout-123",
  eventType: "OrderReserved",
  aggregateId: "checkout-123",
  status: "PENDING",
  createdAt: ISODate("2025-06-01T09:00:00Z")
}
~~~

The transaction comprises:

~~~text
MongoDB transaction:
    update inventory
    insert order
    insert movement
    insert outbox event
commit all
~~~

After commit, a worker reads the outbox and dispatches to the broker. If the process crashes before sending, the outbox record remains for retry.

### 16.2. Outbox Does Not Automatically Provide Broker Exactly-Once

The worker might publish the event and crash before marking the outbox record `SENT`. On the next run, it may send again.

Therefore, consumers need **idempotency by `eventId`**; the system must not assume "outbox" guarantees downstream side effects happen strictly once.

### 16.3. Is `@TransactionalEventListener` `AFTER_COMMIT` Enough?

Spring provides a post-commit listener mechanism suitable for simple side effects. However, if the process dies **after commit and before the listener sends the message**, the event can be lost if not durably persisted.

For critical workflows where events must not be lost, an **outbox persisted inside the transaction** is stronger than an in-memory post-commit callback alone.

## 17. Notes When Calling Multiple Repositories in the Same Transaction

Spring Data repositories configured properly with the same `MongoDatabaseFactory` can join a transaction managed by `MongoTransactionManager`. Still, avoid several assumptions:

### 17.1. Different Repository Interfaces Still Share the Same Transaction

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void process(...) {
    orderRepository.insert(order);
    movementRepository.insert(movement);
    mongoTemplate.updateFirst(
        inventoryFilter, inventoryUpdate, InventoryDocument.class
    );
}
~~~

You do not need three separate transactions for each repository. What matters is that they share the same session/transaction context and none creates a separate connection.

### 17.2. What If a Repository Method Has Its Own @Transactional?

If a repository method is called from a transactional service with **`REQUIRED`**, it can join the active transaction. However, if the repository is configured with a different transaction manager, different propagation, or a different `MongoClient`, behavior may not match expectations.

Avoid "trial by intuition." Inspect Spring bean wiring and write integration tests proving all collections roll back together.

### 17.3. Direct Raw Driver Usage

~~~java
mongoTemplate.getCollection("orders")
    .insertOne(rawDocument);
~~~

Accessing a raw collection via `MongoTemplate` does not automatically mean every driver operation you execute carries the Spring-bound session. With the raw MongoDB driver, overloads accepting **`ClientSession`** may need to be called explicitly; prefer Spring-integrated `MongoTemplate`/repository APIs for declarative transactions.

If you must use the raw driver, verify how to retrieve/reuse the session from Spring Data or design programmatic sessions per official docs, instead of assuming raw inserts join the transaction automatically.

### 17.4. Repository.save and Read-Modify-Write

Transactions do not eliminate the need to enforce business invariants. Two concurrent transactions reading a snapshot and calling `save` on an entity can conflict; applications still need retries or optimistic locking where appropriate.

For inventory, using **conditional `$inc`** rather than reading stale stock and saving is a clearer way to enforce the invariant right inside MongoDB.

## 18. Transactions and Aggregation, Count, and Index Commands

Not every MongoDB command or aggregation stage is allowed inside a transaction on every server version.

### 18.1. Aggregation Inside Transactions

Read aggregations are supported inside transactions where MongoDB permits, subject to:

- The transaction's read preference and read concern.
- Stages restricted inside transactions.
- Long execution times holding transactions/sessions open.
- Output stages such as **`$out`** or **`$merge`** having restrictions in transactions.

For large reporting aggregations, do not wrap the entire report in `@Transactional` by default; consider cutoffs/snapshots or running outside transactions as appropriate.

### 18.2. Count Inside Transactions

MongoDB restricts the legacy `count` command inside transactions. Spring Data MongoDB uses safer alternatives (such as aggregation with `$match`/`$count` where applicable) on supported versions.

**Do not invoke raw `count` commands inside a transaction assuming all server versions allow it.** Use existing Spring Data APIs and run integration tests in your target environment.

### 18.3. Create Collections/Indexes Before Checkout

Creating indexes is schema administration, not a routine step in every checkout.

~~~java
// Do not put this in the middle of an order placement method:
mongoTemplate.indexOps(OrderDocument.class)
    .ensureIndex(...);
~~~

Creating collections/indexes inside transactions has restrictions depending on MongoDB Server, topology, and version. **Provision collections and unique indexes via migrations before accepting checkout traffic.** This is also required for idempotency enforcement to take effect on time.

### 18.4. Do Not Hold Transactions Open During Long Streams

If a `@Transactional` method returns a Java `Stream` for the caller to consume **after the method returns**, the transaction may already have committed/rolled back and the session may no longer be valid.

Never return a cursor-backed resource out of transaction scope without managing its lifecycle. For large exports, design a dedicated flow, typically without holding a business transaction open across file streaming.

## 19. Reactive: Transactions Use Reactor Context, Not ThreadLocal

In the `ReactiveMongoRepository`/`ReactiveMongoTemplate` stack, Spring Data provides **`ReactiveMongoTransactionManager`**. It uses reactive transaction context instead of relying purely on the imperative stack's `ThreadLocal`.

### 19.1. Configuring the Reactive Manager

~~~java
package com.example.checkout;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class ReactiveMongoTransactionConfiguration {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory databaseFactory) {
        return new ReactiveMongoTransactionManager(databaseFactory);
    }
}
~~~

This is an **alternative configuration for the reactive stack**; if the app contains both imperative and reactive flows, explicitly choose the right manager per method. Do not assume a synchronous `MongoTransactionManager` can coordinate `ReactiveMongoTemplate`.

### 19.2. Reactive Repositories

~~~java
package com.example.checkout;

import org.bson.types.ObjectId;
import org.springframework.data.mongodb.repository.ReactiveMongoRepository;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveMongoRepository<OrderDocument, ObjectId> {

    Mono<OrderDocument> findByTenantIdAndRequestId(
        String tenantId, String requestId
    );
}

public interface ReactiveMovementRepository
        extends ReactiveMongoRepository<InventoryMovementDocument, ObjectId> {
}
~~~

### 19.3. Reactive Service: Compose, Do Not Manually Subscribe

~~~java
package com.example.checkout;

import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCheckoutService {

    private final ReactiveMongoTemplate template;
    private final ReactiveOrderRepository orders;
    private final ReactiveMovementRepository movements;

    public ReactiveCheckoutService(
            ReactiveMongoTemplate template,
            ReactiveOrderRepository orders,
            ReactiveMovementRepository movements) {
        this.template = template;
        this.orders = orders;
        this.movements = movements;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager"
    )
    public Mono<OrderDocument> reserve(
            String authenticatedTenantId,
            CheckoutCommand command) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || command == null
                || command.inventoryId() == null
                || command.requestId() == null
                || command.requestId().isBlank()
                || command.quantity() <= 0) {
            return Mono.error(
                new IllegalArgumentException("Invalid request"));
        }

        Query filter = Query.query(
            Criteria.where("_id").is(command.inventoryId())
                .and("tenantId").is(authenticatedTenantId)
                .and("available").gte(command.quantity())
        );

        Update change = new Update()
            .inc("available", -command.quantity())
            .inc("reserved", command.quantity());

        return template.updateFirst(
            filter, change, InventoryDocument.class
        ).flatMap(result -> {

            if (!result.wasAcknowledged()) {
                return Mono.error(
                    new IllegalStateException(
                        "Inventory write not acknowledged"));
            }
            if (result.getModifiedCount() != 1) {
                return Mono.error(new OutOfStockException());
            }

            Instant now = Instant.now();
            OrderDocument order = new OrderDocument(
                new ObjectId(), authenticatedTenantId,
                command.requestId(), command.inventoryId(),
                command.quantity(), "RESERVED", now);

            InventoryMovementDocument movement =
                new InventoryMovementDocument(
                    new ObjectId(), authenticatedTenantId,
                    command.requestId(), command.inventoryId(),
                    command.quantity(), "RESERVE", now);

            return orders.insert(order)
                .flatMap(saved ->
                    movements.insert(movement)
                        .thenReturn(saved)
                );
        });
    }
}
~~~

As in earlier examples, place each public type in its own file. The reactive variant demonstrates commit/rollback on failure, **without complete idempotency retry lookup** like the synchronous service's existing-record check. Add that in real systems where requests can be resent.

### 19.4. Why Must It Return Mono?

The reactive transaction interceptor attaches the transaction context to the returned publisher. Upon subscription, operations composed inside the chain participate in the same reactive transaction.

**Never call `subscribe()` manually inside the service**:

~~~java
@Transactional(
    transactionManager = "reactiveMongoTransactionManager"
)
public Mono<OrderDocument> unsafeReserve(...) {
    template.updateFirst(filter, update, InventoryDocument.class)
        .subscribe(); // Detaches subscription, may run outside expected context.

    return orders.insert(order);
}
~~~

An update executed on a manually created subscription may not share the same reactive transaction as the returned `Mono`. Worse, it can race against the insert and commit.

### 19.5. Do Not Block or Mix Stacks Arbitrarily

~~~java
// Do not do this inside a reactive service/controller:
reactiveCheckoutService.reserve(tenant, command).block();
~~~

Blocking on the event loop violates the reactive model. Furthermore, **synchronous `MongoTemplate` does not automatically join a `ReactiveMongoTransactionManager` reactive transaction**.

If an application needs both imperative and reactive paths, define clear boundaries and use the matching transaction manager rather than hoping both contexts merge automatically.

## 20. TransactionalOperator in the Reactive Stack

Besides annotations, Spring provides **`TransactionalOperator`** to wrap publishers in transactions:

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import reactor.core.publisher.Mono;

TransactionalOperator operator =
    TransactionalOperator.create(reactiveMongoTransactionManager);

Mono<OrderDocument> result = reservePipeline(command)
    .as(operator::transactional);
~~~

**`reservePipeline`** is an example helper returning a `Mono` of composed reactive operations, and `reactiveMongoTransactionManager` must be injected from configuration. Do not mistake it for a built-in Spring method.

### 20.1. When to Use It?

- You need a transaction boundary around part of a pipeline rather than an entire method.
- You want explicit composition of Reactor operations.
- In a reactive service where annotations are prone to self-invocation or unclear boundaries.

### 20.2. Do Not Stretch a Transaction Over an Infinite Flux

If you wrap an infinite or hours-long `Flux` in a transaction, it may never reach a completion signal to commit and can exceed server limits.

Keep transactions **short and finite**, aligned to one business unit; never wrap change streams or unbounded HTTP streaming outputs in a transaction.

### 20.3. Cancellation Must Be Tested

Clients can cancel publishers mid-flight. Reactive transaction machinery handles cancellation per Spring/Reactor/version semantics; **never design checkout assuming clients always keep subscriptions open until completion without idempotency and durable status lookup**.

A request may already have sent operations to the server before cancellation. Always have a `requestId` to reconcile state.

## 21. Testing Transactions with Replica Set and Testcontainers

**Seeing `@Transactional` in source code does not prove transactions work.** You need an integration test running against a transaction-capable MongoDB topology.

One option is **Testcontainers `MongoDBContainer`** configured with a replica set for testing.

### 21.1. Starting the Test MongoDB

~~~java
package com.example.checkout;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class CheckoutTransactionIntegrationTest {

    @Container
    static MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongoProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.data.mongodb.uri",
            mongo::getReplicaSetUrl
        );
    }

    @Autowired CheckoutService checkout;
    @Autowired MongoTemplate template;
    @Autowired OrderRepository orders;
    @Autowired InventoryMovementRepository movements;

    // Tests and index setup follow in the next sections.
}
~~~

This example assumes a **Spring Boot application**, dependencies `spring-boot-starter-data-mongodb`, `testcontainers-mongodb`, `testcontainers-junit-jupiter`, JUnit 5, and a Docker environment for tests. `MongoTemplate`, repository imports, and following methods belong in the same class.

**`MongoDBContainer`** provides a replica set as supported by Testcontainers; verify the API for your exact Testcontainers version, as container configuration methods can vary between releases.

### 21.2. Creating Collections/Indexes Before Transactions

In test environments, create required unique indexes before the service executes checkout:

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.index.Index;

@BeforeEach
void ensureIndexes() {
    template.indexOps(OrderDocument.class).ensureIndex(
        new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("requestId", Sort.Direction.ASC)
            .unique()
            .named("uk_orders_tenant_request")
    );

    template.indexOps(InventoryMovementDocument.class).ensureIndex(
        new Index()
            .on("tenantId", Sort.Direction.ASC)
            .on("requestId", Sort.Direction.ASC)
            .unique()
            .named("uk_movements_tenant_request")
    );
}
~~~

If MongoDB Server/index metadata already exists with different options, `ensureIndex` can report a conflict. In an isolated test instance, create indexes matching your schema and avoid changing definitions between tests.

**Do not put `@Transactional` on the test method itself just because the service has it.** A test-managed transaction wrapping the test method can mask whether the service's transaction actually commits/rolls back and alter verification semantics.

## 22. Integration Test: Synchronous Commit Across Three Collections

Add the following test to `CheckoutTransactionIntegrationTest`. In a real source file, add the corresponding imports.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;
import java.time.Instant;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@Test
void commitsInventoryOrderAndMovementTogether() {
    String tenant = "TEST-" + UUID.randomUUID();
    String requestId = "checkout-" + UUID.randomUUID();
    ObjectId inventoryId = new ObjectId();

    template.insert(new InventoryDocument(
        inventoryId, tenant, "BOOK-101", 5L, 0L
    ));

    try {
        OrderDocument saved = checkout.reserve(
            tenant,
            new CheckoutCommand(inventoryId, requestId, 2L)
        );

        InventoryDocument after = template.findById(
            inventoryId, InventoryDocument.class
        );

        assertThat(after).isNotNull();
        assertThat(after.available()).isEqualTo(3L);
        assertThat(after.reserved()).isEqualTo(2L);

        assertThat(saved.status()).isEqualTo("RESERVED");
        assertThat(
            orders.findByTenantIdAndRequestId(tenant, requestId)
        ).isPresent();

        long movementCount = template.count(
            Query.query(
                Criteria.where("tenantId").is(tenant)
                    .and("requestId").is(requestId)
            ),
            InventoryMovementDocument.class
        );

        assertThat(movementCount).isEqualTo(1L);
    } finally {
        cleanupTenantAndInventory(tenant, inventoryId);
    }
}
~~~

Test cleanup helper:

~~~java
private void cleanupTenantAndInventory(
        String tenant, ObjectId inventoryId) {

    template.remove(
        Query.query(Criteria.where("tenantId").is(tenant)),
        OrderDocument.class
    );
    template.remove(
        Query.query(Criteria.where("tenantId").is(tenant)),
        InventoryMovementDocument.class
    );
    template.remove(
        Query.query(Criteria.where("_id").is(inventoryId)),
        InventoryDocument.class
    );
}
~~~

Cleanup runs **outside the service transaction** and targets only the randomly generated test tenant. Run only on a dedicated test database; never apply arbitrary tenant-deletion logic to production.

### 22.1. What Does This Test Prove?

Starting from `available=5`, `reserved=0`, when checkout reserves `quantity=2` successfully:

~~~text
inventories: available=3, reserved=2
orders: one order with the corresponding requestId
inventory_movements: one RESERVE movement
~~~

However, a passing happy-path test **is not enough to prove rollback**. Three independent writes can also all succeed. You must test a failure occurring **after at least two prior writes have executed**.

## 23. Integration Test: Failure on the Final Write Must Roll Back Earlier Steps

To induce a predictable failure at the **insert movement** step, the test seeds a movement with the same unique `tenantId+requestId` key. When the service tries to insert the second movement, MongoDB rejects it due to the unique index.

The service method in section 7 executes in this order:

~~~text
1. update inventory
2. insert order
3. insert movement -> duplicate key error
4. transaction abort
~~~

Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Instant;
import java.util.UUID;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

@Test
void rollsBackAllWritesWhenLastRepositoryInsertFails() {
    String tenant = "TEST-" + UUID.randomUUID();
    String requestId = "checkout-" + UUID.randomUUID();
    ObjectId inventoryId = new ObjectId();

    template.insert(new InventoryDocument(
        inventoryId, tenant, "BOOK-101", 5L, 0L
    ));

    // Seed fixture outside the checkout transaction.
    movements.insert(new InventoryMovementDocument(
        new ObjectId(), tenant, requestId, inventoryId,
        2L, "RESERVE", Instant.now()
    ));

    try {
        assertThatThrownBy(() -> checkout.reserve(
            tenant,
            new CheckoutCommand(inventoryId, requestId, 2L)
        )).isInstanceOf(RuntimeException.class);

        InventoryDocument after = template.findById(
            inventoryId, InventoryDocument.class
        );

        assertThat(after).isNotNull();
        assertThat(after.available()).isEqualTo(5L);
        assertThat(after.reserved()).isEqualTo(0L);

        assertThat(
            orders.findByTenantIdAndRequestId(tenant, requestId)
        ).isEmpty();

        long movementCount = template.count(
            Query.query(
                Criteria.where("tenantId").is(tenant)
                    .and("requestId").is(requestId)
            ),
            InventoryMovementDocument.class
        );
        assertThat(movementCount).isEqualTo(1L);
    } finally {
        cleanupTenantAndInventory(tenant, inventoryId);
    }
}
~~~

**Verification point:** the pre-seeded movement still exists (`count=1`), while the failing transaction's inventory update and order insert **did not** commit. If stock remains 3 or the order persists after the error, suspect that the transaction is inactive or a write ran outside the session.

### 23.1. Why Must the Test Have the Unique Index First?

Without the unique index on **(tenantId, requestId)** in `inventory_movements`, the second insert succeeds, and the transaction encounters no error to roll back. The test would accidentally become a success test.

### 23.2. Exception Assertions

The example uses a broad `RuntimeException` assertion to stay focused on verifying rollback. In real projects, prefer asserting the Spring-translated exception (such as `DuplicateKeyException` or an appropriate `DataAccessException` subtype) once library/driver versions are fixed.

Never assert on error message text, as wording can change across MongoDB Server and driver versions.

### 23.3. No @Transactional on the Test Method

If the test method opens its own transaction, `reserve` may simply **join the test's transaction**, meaning observations before commit or rollback do not reflect production behavior.

Here the test invokes the service through the Spring bean so the service's own annotation controls the boundary.

### 23.4. Testing Insufficient Inventory Too

Insert inventory with `available=1` and call `reserve` with `quantity=2`:

~~~java
assertThatThrownBy(() -> checkout.reserve(
    tenant, new CheckoutCommand(inventoryId, requestId, 2L)
)).isInstanceOf(OutOfStockException.class);
~~~

After the exception, inventory must remain `available=1`, `reserved=0` with no new order/movement. This confirms the business guard remains enforced inside the transaction.

## 24. Testing When Two Checkouts Contend for Inventory

Transactions roll back multi-write sets, yet **do not guarantee every concurrent transaction succeeds**.

With `available=1` and two distinct requests each requesting `quantity=1`:

| Possible Outcome | Interpretation |
| --- | --- |
| One transaction commits, the other finds no stock | The `available>=1` guard rejects the later request |
| One transaction commits, the other hits a write conflict | Conflict must be classified and can be retried in a fresh transaction |
| Transaction fails due to infrastructure error | Requires retry/reconciliation per policy |

In a concurrency test:

1. Create inventory with `available=1`.
2. Use two threads calling two distinct `requestId` values through the Spring proxy.
3. Wait for both to finish and classify results/exceptions.
4. Assert **the count of committed `RESERVED` orders does not exceed 1**.
5. Assert inventory `available` is non-negative.
6. If a `RESERVED` order exists, verify its matching movement and `reserved` counter.

**Never hard-assert that every failure must be `OutOfStockException`** when two MongoDB transactions run concurrently; MongoDB may report a retryable write conflict.

### 24.1. Retries Can Change the Outcome

If the application retries the entire transaction after a transient conflict, the unresolved request may then observe `available=0` and turn into a business out-of-stock failure.

This is more accurate than treating a conflict as "out of stock" on the first attempt. However, retries need time/attempt bounds and must not trigger non-idempotent external side effects.

### 24.2. Do Not Measure Concurrency with Sequential Tests

A test calling the service twice in a row creates no contention. Use `CountDownLatch`/`ExecutorService` against the real transactional service and observe how your test MongoDB instance behaves.

## 25. Diagnostic Table: @Transactional Present Yet Data Partially Written

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Final step fails, yet inventory still decrements | Transaction inactive, self-invocation, operation outside session | Check proxy/manager/factory and rollback tests |
| Transaction reports unsupported topology | Standalone MongoDB | Use a supported replica set/sharded deployment |
| Two managers present and wrong one chosen | JDBC/JPA manager selected instead of Mongo | Specify `transactionManager` explicitly |
| Annotated method does not roll back | Called via `this` or `new` instead of Spring proxy | Extract bean or call through proxy |
| Error logged and service returns normally | Exception swallowed | Throw exception or mark rollback-only |
| `IOException` still commits | Checked exception excluded from default rollback rules | Configure `rollbackFor` appropriately |
| Repository A rolls back, raw driver B does not | Session/connection not shared | Use Spring Data APIs sharing factory/session |
| `CompletableFuture` insert remains after rollback | New thread does not join synchronous transaction | Do not offload operations to async threads |
| Order exists without movement | One method uses a different manager or runs outside tx | Check wiring + integration tests |
| Client times out and retries, creating two orders | Missing idempotency or unique request ID | Unique key, payload check, reconcile |
| Commit response lost | Unknown commit result | Reconcile `requestId`, retry commit per contract |
| Transaction hits write conflict | Concurrent writers on same document | Bounded whole-transaction retry |
| Transaction runs too long | External HTTP, heavy aggregation, long export | Narrow transaction scope |
| Transaction fails creating index dynamically | DDL/index inside workflow | Provision schema beforehand |
| `@Transactional` in WebFlux misbehaves | Imperative manager used or blocking/detached subscribe | `ReactiveMongoTransactionManager` + single publisher chain |
| `@Transactional(readOnly=true)` still opens session/tx | Misunderstood `readOnly` | Check integration semantics and use case |
| Tests "pass" without proving rollback | Only tested commit or test method itself is transactional | Inject failure after two writes and assert DB state |

### 25.1. Quick Investigation Procedure

1. Verify the service bean is created by Spring and `@Transactional` is invoked via proxy.
2. Verify the selected `transactionManager` is `MongoTransactionManager`.
3. Verify the MongoDB topology supports transactions.
4. Verify `MongoTemplate` and repositories share the same `MongoDatabaseFactory`/session context.
5. Check whether exceptions are caught and swallowed or rollback rules are misaligned.
6. Check for `CompletableFuture`, `@Async`, raw driver calls, or HTTP calls mid-transaction.
7. Reproduce rollback in a replica-set test by failing on the third write.
8. Verify required unique indexes were created before checkout.
9. Classify write conflicts and unknown commit results; avoid infinite retries.
10. Only after data correctness is proven, optimize performance and load capacity.

## 26. Performance, Contention, and Transaction Scope

Multi-document transactions are a correctness tool and **not free**:

- They require session and snapshot/transaction state management.
- They can increase contention or write conflicts.
- Long transactions raise resource costs and limit-exceeded risks.
- Writing across multiple collections still incurs index, network, and disk costs.
- Commit and durability policies affect latency.

### 26.1. Keep Transactions Short

~~~text
Avoid:
@Transactional
  -> call external API
  -> sleep/retry on client
  -> run full-history aggregation query
  -> update inventory
  -> insert order

Prefer:
Prepare input/authorization beforehand
@Transactional
  -> conditional update inventory
  -> insert order
  -> insert movement/outbox
commit
Worker calls external API afterward
~~~

Short business transactions are easier to observe, safer to retry, and hold resources far more briefly than transactions wrapping an entire HTTP checkout request.

### 26.2. Indexes Supporting Lookups

In the example, inventory is looked up by **`_id`**, which uses the default index. `tenantId`/`available` predicates are evaluated after locating the document.

Order lookups by `tenantId+requestId` need a unique compound index to enforce idempotency and speed up reading existing records. Do not routinely index `available` unless a real workload requires it, as counters update frequently.

### 26.3. Choose Isolation/Consistency Per Requirements

A transaction does not automatically mean every out-of-transaction report sees the same snapshot. Explicitly define read concern/write concern and when an order's state may be surfaced to clients.

### 26.4. Monitor Metrics

Useful metrics:

- Transaction commit/abort counts.
- Transaction duration and p95/p99.
- Write conflict / transient transaction error rate.
- Retry counts and backoff durations.
- Unknown commit result / reconciliation count.
- Conditional out-of-stock count.
- Duplicate `requestId` or payload-conflict count.
- Unpublished outbox event count.

Never log sensitive details, raw payment tokens, or full session internals solely for debugging transactions.

## 27. Security and Tenant Isolation

Transactions provide all-or-nothing atomicity for covered writes; **they do not provide authorization**.

In the service example, the update filter must contain:

~~~java
Criteria.where("_id").is(command.inventoryId())
    .and("tenantId").is(authenticatedTenantId)
    .and("available").gte(command.quantity());
~~~

If only `_id` is checked and a caller supplies another tenant's ID, the transaction would very consistently commit a cross-tenant stock deduction — yet **violate security**.

### 27.1. Tenant From a Trusted Source

Never treat a client-supplied `tenantId` field as proof of access rights. The tenant must come from the principal, session, or server policy after authentication/authorization.

### 27.2. Unique Keys Also Need Tenant Scope

If `requestId` is only unique within a tenant, use a **unique `{tenantId:1,requestId:1}`** index. If `requestId` is designed as globally unique, a global unique index may fit, provided the contract is explicit.

### 27.3. Errors Must Avoid Data Leakage

An "inventory not found" exception can represent either a nonexistent ID or an ID belonging to another tenant. Public APIs must not disclose stock, currency, or order metadata of other tenants through overly detailed error messages.

## 28. Anti-Patterns to Avoid

### 28.1. Treating @Transactional Like Magic

~~~java
@Transactional
public void checkout(...) {
    updateInventory();
    orderRepository.insert(order);
}
~~~

This is insufficient to prove correctness **without `MongoTransactionManager`, a supported MongoDB topology, shared session, and proxied invocation**.

### 28.2. Catching Every Exception and Returning false

~~~java
try {
    reserveOrder();
} catch (Exception e) {
    return false;
}
~~~

If this sits inside a transaction and swallows the exception, the caller may not realize whether commit occurred. Outside a transaction, catching everything and returning `false` blurs business rejections with network/commit uncertainty.

### 28.3. Creating a New MongoClient Inside Each Repository/Service

This breaks Spring Data's synchronous session/resource management and creates redundant connection pools. Use configured beans and let Spring manage their lifecycle.

### 28.4. Wrapping a Payment Call Inside a Transaction

External HTTP is outside MongoDB transactions. Holding a transaction while waiting on payment wastes resources and never yields system-wide rollback.

### 28.5. Running Long Transactions to Wait for Events

Never use a MongoDB transaction as a queue "waiting until a consumer replies." Use an outbox/message broker and business states.

### 28.6. Wrapping a Flux in a Transaction While Subscribing Separately to Branches

Reactive transaction context does not flow across two independent subscriptions. Compose all operations into **one publisher chain** or apply `TransactionalOperator` appropriately.

### 28.7. Assuming Transactions Replace Unique Indexes

Two transactions concurrently reading "requestId does not exist" can race. Unique indexes and idempotency mechanisms remain essential.

## 29. Practice Exercises

### Exercise 1: Does One Document Need a Transaction?

An inventory document has `available=10`, `reserved=0`. The service runs:

~~~javascript
db.inventories.updateOne(
  {
    _id: productId,
    available: { $gte: 3 }
  },
  {
    $inc: { available: -3, reserved: 3 }
  }
);
~~~

**Question:** Is a multi-document transaction required just so these two fields change together?

**Answer:** No. A single update on one document is applied atomically by MongoDB. Only consider a multi-document transaction when you also need to create order/movement documents and commit/roll back them together.

### Exercise 2: Transaction Manager

A Spring Boot app has `MongoTemplate` and `OrderRepository` without a declared manager. What configuration is missing?

~~~java
@Bean("mongoTransactionManager")
MongoTransactionManager mongoTransactionManager(
        MongoDatabaseFactory factory) {
    return new MongoTransactionManager(factory);
}
~~~

**Note:** you also need transaction management enabled properly and a supported MongoDB topology. Do not just add the bean and ignore infrastructure.

### Exercise 3: Service with Three Writes

A service needs to update inventory, insert an order, and insert a movement, rolling back together. Where should `@Transactional` go?

**Answer:** On the public service method representing the checkout/reserve business operation, invoked through a Spring proxy with the right `MongoTransactionManager`. Repositories/templates join that boundary when sharing the session/factory.

### Exercise 4: Self-Invocation

~~~java
public void checkout() {
    reserve();
}

@Transactional(transactionManager = "mongoTransactionManager")
public void reserve() {}
~~~

**Question:** Is the annotation guaranteed to apply when `checkout` calls `reserve` on the same bean?

**Answer:** No, not under typical Spring proxy mechanics. Internal calls via `this` bypass the interceptor. Extract `ReservationService` into a separate bean and invoke via proxy, or redesign the boundary.

### Exercise 5: Catching Exceptions

After updating inventory, inserting the movement fails. The code catches `RuntimeException` and returns `false`. Why is this dangerous?

**Answer:** The exception never reaches the transaction interceptor, so the transaction may commit the inventory modification. Throw a `RuntimeException` or mark rollback-only properly with an explicit API contract.

### Exercise 6: Checked Exceptions

A `@Transactional` service throws `IOException` after inserting an order. Does Spring always roll back by default?

**Answer:** No, under default rules for checked exceptions. If business logic requires rollback, configure `rollbackFor=IOException.class` or `Exception.class` as appropriate. Avoid holding transactions open just to wrap external I/O.

### Exercise 7: Multiple Datasources

An application has `JpaTransactionManager` and `MongoTransactionManager`. Does an unqualified `@Transactional` guarantee MongoDB coordination?

**Answer:** No. You must specify the selected transaction manager, e.g., `transactionManager="mongoTransactionManager"`. A MongoDB manager does not create a distributed transaction with a SQL database.

### Exercise 8: Another Thread

Inside a synchronous `@Transactional` method, code spawns a `CompletableFuture` running `movementRepository.insert` on a thread pool. Is the movement guaranteed to share the transaction?

**Answer:** No. Imperative transaction sessions are bound to the thread context and do not propagate across async tasks. Never split writes belonging to the same transaction across threads.

### Exercise 9: Insufficient Inventory

Inventory has `available=1`, checkout requests `quantity=2`. Why is the `available>=quantity` filter still necessary despite `@Transactional`?

**Answer:** A transaction only governs commit/rollback of operations; it does not inject business rules into updates. The filter must enforce non-negative stock and the service must check `modifiedCount`.

### Exercise 10: Real Rollback

In a test, inventory update and order insert succeed, then movement insert intentionally triggers a duplicate key. What is the expected state after transaction abort?

**Answer:** Inventory holds its pre-transaction values, the order is not committed, and the pre-seeded movement fixture remains. If inventory/order persisted, inspect proxy, manager, and session configuration.

### Exercise 11: Retrying Transactions

A MongoDB transaction receives `TransientTransactionError` mid-way through updating inventory. Can you stay in the same transaction and re-call order insert?

**Answer:** No. This error type typically requires retrying a **brand-new transaction**, including re-reading/re-validating, with bounded retries and backoff. Distinguish it from business out-of-stock errors.

### Exercise 12: Uncertain Commit Outcome

A client receives a timeout after the service executes commit. Should it immediately submit a fresh checkout with a new `requestId`?

**Answer:** No. Commit may have succeeded. Look up the outcome by the old `requestId`, verify the payload, and follow an `UnknownTransactionCommitResult` handling strategy.

### Exercise 13: Unique `requestId`

Two transactions both observe that `requestId` does not exist prior to insert. How do you prevent creating two orders?

**Answer:** A unique index on `(tenantId, requestId)`. In addition, handle duplicate/write conflicts and never treat pre-checks as sufficient. On retry, read the committed result.

### Exercise 14: Calling a Payment Gateway

A service opens a MongoDB transaction, deducts inventory, calls HTTP payment, and saves the order. If MongoDB rolls back after the gateway captured funds, does the gateway automatically refund?

**Answer:** No. HTTP/payment gateways are outside MongoDB transactions; use reservation, saga/compensation, and outbox with idempotency.

### Exercise 15: Outbox

Why insert an outbox event inside the same transaction instead of calling the message broker directly after updating inventory?

**Answer:** The outbox commits atomically with inventory/order, preventing lost events if the process crashes post-commit. A worker dispatches later and consumers handle duplicate `eventId` deliveries.

### Exercise 16: Reactive

Which transaction manager do `ReactiveMongoTemplate` and `ReactiveMongoRepository` require?

~~~java
@Bean("reactiveMongoTransactionManager")
ReactiveMongoTransactionManager reactiveMongoTransactionManager(
        ReactiveMongoDatabaseFactory factory) {
    return new ReactiveMongoTransactionManager(factory);
}
~~~

**Answer:** `ReactiveMongoTransactionManager` or `TransactionalOperator` built on the reactive manager. Operations must stay inside the managed publisher chain without blocking or detached subscribes.

### Exercise 17: `readOnly`

A read-only report uses `@Transactional(readOnly=true)`. Is MongoDB guaranteed to always read from a secondary without opening a session/transaction?

**Answer:** No. `readOnly` is Spring metadata and MongoDB integration has its own semantics. Verify read preference/concern, topology, and test on your version.

### Exercise 18: When Are Indexes Created?

A checkout service tries to call `ensureIndex` mid-transaction so `requestId` uniqueness is guaranteed. Is that recommended?

**Answer:** No. Schema/indexes must be prepared via migrations before traffic. Index creation inside transactions has restrictions and is unsuitable for checkout paths.

### Exercise 19: `NESTED`

You want to reserve one line item and roll back only that line via `@Transactional(NESTED)`. Can MongoDB be assumed to create SQL-style savepoints?

**Answer:** No. MongoDB transactions do not provide nested savepoints like those expected in some RDBMSs. Design separate business boundaries/compensation.

### Exercise 20: Testing Multiple Transactions

Two customers try to buy the last item simultaneously. One succeeds and the other hits a write conflict. Should tests assert that the second failed transaction always throws `OutOfStockException`?

**Answer:** No. A write conflict differs from an unmet stock predicate. You can retry a fresh transaction within bounds, after which the retry sees `stock=0` and throws the appropriate business error.

## 30. Production Deployment Checklist

- **Business logic:** which MongoDB operations strictly need to commit/roll back together?
- **Scope:** is a single-document update enough, or is a multi-document transaction truly needed?
- **Topology:** is MongoDB a compatible replica set/sharded deployment?
- **Driver:** are Spring Data MongoDB, driver, and MongoDB Server compatible?
- **Manager:** is `MongoTransactionManager` registered and referenced by the right bean name?
- **Proxy:** is `@Transactional` placed on a public service method called through a Spring proxy?
- **Factory:** do all `MongoTemplate`/repositories share the same `MongoDatabaseFactory`/session?
- **Raw driver:** are any operations using a separate `MongoClient`/session outside the transaction?
- **Async:** are any threads/`CompletableFuture` tasks inadvertently escaping the context?
- **Rollback:** are any exceptions caught and swallowed causing unwanted commits?
- **Checked errors:** does `rollbackFor` match the exception-handling policy?
- **Propagation:** do helper methods join `REQUIRED` instead of unintentionally starting independent transactions?
- **Nested:** have you avoided assuming MongoDB supports RDBMS savepoints?
- **Business guard:** do inventory updates still enforce `available >= quantity`?
- **Unique:** has the unique index on `tenantId+requestId` actually been created?
- **Idempotency:** do identical `requestId`/payload replays return the prior result without deducting again?
- **Commit unknown:** is there a reconciliation mechanism when a commit response is lost?
- **Retry:** are transient errors, unknown commit results, and business failures clearly distinguished?
- **Retry scope:** does each attempt use a fresh transaction with bounded retries/backoff?
- **Outbox:** are outbound system events durably recorded?
- **External I/O:** are payment gateway calls kept out of long transactions?
- **Options:** do `readConcern`/`writeConcern`/`readPreference` fit requirements?
- **Lifetime:** are transactions short enough to avoid server limits and long client waits?
- **Schema:** are collections/indexes migrated before checkout traffic?
- **Reactive:** using `ReactiveMongoTransactionManager` and a single publisher chain with no `block()` or detached `subscribe()`?
- **Testing:** do replica-set integration tests cover commit, rollback, business guards, idempotency, and concurrency?
- **Metrics:** are commits, aborts, write conflicts, retries, and p95/p99 tracked?
- **Security:** is the tenant obtained from authentication context rather than trusting client-supplied `requestId`/tenant?

## 31. Summary

1. **`@Transactional` at the service layer** fits when a business operation requires multiple `MongoRepository`/`MongoTemplate` operations to **commit or roll back together**.
2. **`MongoTransactionManager`** manages MongoDB `ClientSession`/transactions in the synchronous stack; operations must participate via the right session/factory.
3. **A compatible MongoDB replica set or sharded deployment** is an infrastructure prerequisite; standalone `mongod` is unsuitable for multi-document transactions.
4. **Transactions** do not replace business guards. For inventory, you still need **`available >= quantity`** and atomic `$inc`.
5. **`MongoTemplate` + multiple `MongoRepository` beans** can share one transaction when properly managed by Spring, without needing separate transactions per repository.
6. **Spring proxies** govern `@Transactional` interception; self-invocation, manual `new` instantiation, and `final`/`private` methods can prevent the annotation from firing.
7. **`RuntimeException` triggers rollback by default**, whereas checked exceptions need `rollbackFor` review. Swallowing exceptions can cause unintended commits.
8. **Transactions do not automatically include new threads, other raw `MongoClient` instances, HTTP calls, or payment gateways**.
9. **`REQUIRED`** is usually the appropriate propagation; do not assume `REQUIRES_NEW`/`NESTED` carry JDBC-identical semantics or support.
10. **Write conflicts and `UnknownTransactionCommitResult`** are distinct states; retries require error classification, bounds, and idempotency.
11. **Unique `requestId` + outbox + state machine** address request replays and external side effects, without removing the need for reconciliation.
12. **`ReactiveMongoTransactionManager`** uses the Reactor Context; compose publishers and avoid arbitrary `subscribe()` or `block()` calls.
13. **Shorter transactions are easier to operate**; pre-create indexes and avoid waiting on HTTP/heavy aggregations/long exports inside transactions.
14. **Integration tests on a replica set** must prove rollback across all collections when a final operation fails.
15. **End-to-end correctness** requires proper transaction boundaries, business predicates, authorization, unique constraints, consistency options, and retry strategies.

Mastering **`@Transactional` at the service layer with multiple repositories/templates** enables **`SPRING_DATA_MONGODB`** applications to structure multi-document workflows safely, ensuring required MongoDB updates commit or roll back together while avoiding confusion between database transactions and whole-workflow consistency.

### References

- [Spring Data MongoDB — Client Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html) — `MongoTransactionManager`, `ClientSession`, imperative/reactive transactions.
- [Spring Data MongoDB — Transactions API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/MongoTransactionManager.html) — synchronous transaction contract and lifecycle.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — `@Transactional`, proxies, rollback rules, and propagation.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — server support, sessions, transaction limits, and best practices.
- [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/) — resources, topology, and operational limits.
- [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/) — `MongoDBContainer` and replica set testing.
