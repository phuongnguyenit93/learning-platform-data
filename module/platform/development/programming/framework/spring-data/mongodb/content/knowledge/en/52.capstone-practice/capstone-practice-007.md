# Adding Versioning, Auditing, and Multi-Document Transactions

In a **Spring Data MongoDB** application, saving a single document is relatively simple: **MongoRepository.save(...)** or **MongoTemplate.save(...)** suffices for many cases. The harder problem arises when a single business operation must **read and update inventory**, **create an order**, **write an event**, while also recording **who performed it and when**, and handling two requests modifying the same document concurrently.

This capstone practice adds three capabilities to the order placement flow:

1. **Optimistic locking with @Version** to detect updates based on stale versions.
2. **Auditing with @CreatedDate, @LastModifiedDate, @CreatedBy, @LastModifiedBy** to record change metadata automatically.
3. **Multi-document transactions with MongoTransactionManager and @Transactional** so MongoDB changes commit or roll back together.

This is a practical lesson in the **SPRING_DATA_MONGODB** module: using **MongoRepository**, relating it to **MongoTemplate**, understanding replica set requirements, and testing both success and failure branches. The code examples use **Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, MongoDB 7.0**, and Testcontainers 1.x as a consistent set; when using other versions, adjust dependencies, imports, and configuration per the corresponding compatibility matrix.

> **Practice goal:** an order is created only when inventory is sufficient; reserving inventory, creating the order, and writing the event run in one transaction; key documents carry version and audit metadata; concurrent writes never silently lose updates.

## 1. Expected Outcomes and Acceptance Criteria

Upon completion, learners must demonstrate:

| Requirement | Acceptance evidence |
| --- | --- |
| Create new inventory item | Document persisted in **inventory** collection with version and creation timestamp |
| Order placement succeeds | Increments **reserved**, creates **orders**, creates **order_events** in one transaction |
| Order placement fails mid-way | No partial inventory update committed; no unexpected order or event left behind |
| Update document using stale copy | Optimistic locking or write conflict error handled according to policy |
| Record metadata | **createdAt**, **updatedAt**, **createdBy**, **updatedBy** populated validly where auditing is configured |
| Run in proper environment | Uses a MongoDB **replica set** or **sharded cluster** supporting transactions |
| Test without mocked DB | Tests actually inspect MongoDB state after the transaction ends |
| Safe retries | Distinguishes retryable errors, business errors, and already-processed requests |

Never treat **@Transactional** as an atomicity guarantee across external resources: a MongoDB transaction covers MongoDB operations sharing the same session, **not** HTTP calls, emails, Kafka, or other external systems.

## 2. Business Model and Data Invariants

Suppose a store has three collections:

| Collection | Core data | Purpose |
| --- | --- | --- |
| **inventory** | **sku**, **onHand**, **reserved**, version, audit fields | Stock on hand and reserved units |
| **orders** | **orderId**, **sku**, **quantity**, **status**, version, audit fields | Placed orders |
| **order_events** | **eventId**, **orderId**, **type**, createdAt | Internal event record in the same DB |

In this example:

- **onHand** is the total units in stock.
- **reserved** is the units held for uncompleted orders.
- **available = onHand − reserved**.
- Each request orders **one SKU** to stay focused on transactions rather than multi-item carts.
- **orderId** is supplied by the caller as a unique identifier; a dedicated idempotency policy is needed when scaling to production.

Invariants to maintain:

\[
0 \leq \text{reserved} \leq \text{onHand}
\]

\[
\text{available} = \text{onHand} - \text{reserved}
\]

A successful order transaction must satisfy:

1. Inventory **reserved** increases by exact quantity.
2. **One** order document exists for orderId.
3. **One** **ORDER_PLACED** event exists for that order.
4. If any write step inside the transaction fails, **none** of the writes commit.

~~~mermaid
sequenceDiagram
    participant API as "API / Command"
    participant SVC as "OrderPlacementService"
    participant INV as "inventory"
    participant ORD as "orders"
    participant EVT as "order_events"
    API->>SVC: "place(orderId, sku, quantity)"
    Note over SVC: "Start MongoDB transaction"
    SVC->>INV: "findById(sku)"
    SVC->>SVC: "Check available and update reserved"
    SVC->>INV: "save(inventory) with @Version"
    SVC->>ORD: "insert(order)"
    SVC->>EVT: "insert(ORDER_PLACED event)"
    alt "All three writes succeed"
        SVC->>SVC: "Commit transaction"
        SVC-->>API: "Return order"
    else "Any step fails"
        SVC->>SVC: "Abort / rollback transaction"
        SVC-->>API: "Return appropriate error"
    end
~~~

**Important boundary:** MongoDB guarantees atomicity at the **single-document** level even without transactions. We need a transaction because we update **multiple documents/collections** with a shared commit outcome. **@Version** solves a different problem: preventing overwrites based on stale document snapshots. The two mechanisms complement rather than replace each other.

## 3. Declaring Dependencies and Environment

With Gradle Groovy DSL, an application using a compatible Spring Boot BOM needs at minimum:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
}

test {
    useJUnitPlatform()
}
~~~

The example assumes versions are managed by Spring Boot/dependency management. Never arbitrarily mix incompatible major versions of **MongoDB Java Driver**, **Spring Data MongoDB**, and **Testcontainers**. Running integration tests requires a compatible container runtime, while production requires a MongoDB cluster with transaction-capable topology and configuration.

Example local connection configuration:

~~~yaml
spring:
  data:
    mongodb:
      uri: mongodb://localhost:27017/capstone
      auto-index-creation: false
~~~

This is example syntax for **Spring Boot 3.x**. In **Spring Boot 4.x**, some connection properties move to the **spring.mongodb** namespace; never copy configuration across major versions without checking the migration guide. This lesson does not depend on auto-index creation: **_id** already has a default unique index, while business indexes should be managed separately when needed.

### 3.1. Why Do Transactions Require a Replica Set?

MongoDB multi-document transactions require a **replica set** or **sharded cluster**. A standalone MongoDB instance can save and read individual orders normally, yet starting a multi-document transaction will not work as expected. If you encounter errors mentioning **Transaction numbers are only allowed on a replica set member or mongos**, check topology before blaming Java annotations.

Points to verify:

- Connecting to a replica set (via replica set connection string) or **mongos** of a sharded cluster.
- **MongoTransactionManager** uses the exact **MongoDatabaseFactory** backing the repositories/`MongoTemplate` in use.
- Write concern, read concern, timeouts, and transaction limits fit the real system.
- Required collections and indexes are created **before transactions** per environment policy; never design business transactions that depend on implicitly creating schemas or indexes at runtime.

## 4. Adding @Version to the Inventory Entity

**Optimistic locking** is designed for scenarios where multiple actors read the same document and try to write based on stale state. When a mapping includes **@Version**, Spring Data MongoDB includes the current version in the update condition and increments it upon a successful write.

Example of two threads reading the same record:

~~~text
T0: inventory = { sku: "SKU-1", onHand: 3, reserved: 0, version: 0 }

Thread A reads version 0.
Thread B reads version 0.

A reserves 2 units and saves -> updates version 0 to version 1.
B reserves 2 units based on version 0 -> update fails
  or hits transaction conflict; must not silently overwrite A.
~~~

Without a version field or equivalent atomic write predicate, **read → calculate → save** risks lost updates.

### 4.1. InventoryItem Entity

~~~java
package example.capstone;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventory")
public class InventoryItem {
    @Id
    private String sku;

    private long onHand;
    private long reserved;

    @Version
    private Long version;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String updatedBy;

    protected InventoryItem() {
        // Spring Data mapping.
    }

    public InventoryItem(String sku, long onHand) {
        if (sku == null || sku.isBlank() || onHand < 0) {
            throw new IllegalArgumentException("Invalid inventory");
        }
        this.sku = sku;
        this.onHand = onHand;
        this.reserved = 0;
    }

    public void reserve(long quantity) {
        if (quantity <= 0 || quantity > onHand - reserved) {
            throw new IllegalStateException("Insufficient inventory");
        }
        reserved = Math.addExact(reserved, quantity);
    }

    public String getSku() { return sku; }
    public long getOnHand() { return onHand; }
    public long getReserved() { return reserved; }
    public long getAvailable() { return onHand - reserved; }
    public Long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getUpdatedBy() { return updatedBy; }
}
~~~

**Notes on @Version:**

- Choose nullable **Long** for new entities; Spring Data assigns the initial value and increments on updates. Never increment version manually in business code.
- With **@Version**, saving an existing entity includes a version check; when no document matches the old version, Spring Data typically throws **OptimisticLockingFailureException**.
- Detecting unmatched updates requires an **acknowledged write concern** so the driver receives write counts. Avoid **UNACKNOWLEDGED** on this path.
- **@Version** on an entity does not automatically guard every write path. Raw driver updates or **MongoTemplate.updateFirst(...)** outside entity save flows may not enforce the optimistic locking contract you expect; verify specific APIs and update predicates.
- Version is a number for **concurrency control**, not a change history. To record event history or who changed what, use auditing or a dedicated audit log.

## 5. Adding Auditing to Orders

Auditing populates metadata when entities are created or modified through supported Spring Data paths:

| Annotation | When applied | Meaning |
| --- | --- | --- |
| **@CreatedDate** | On new document creation | Creation timestamp |
| **@LastModifiedDate** | On creation and updates per auditing policy | Last modification timestamp |
| **@CreatedBy** | On new document creation | Creating user/actor |
| **@LastModifiedBy** | On updates per auditing policy | Modifying user/actor |
| **@Version** | When saving/updating versioned entities | Detects stale writes and increments version |

**Auditing does not replace an immutable audit trail**: if you need a full chronological list of changes, **updatedBy/updatedAt** alone are insufficient; design historical events, change logs, or an event store with its own policy.

### 5.1. PurchaseOrder Entity

~~~java
package example.capstone;

import java.time.Instant;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public class PurchaseOrder {
    public enum Status { PLACED, CANCELLED }

    @Id
    private String id;

    private String sku;
    private long quantity;
    private Status status;

    @Version
    private Long version;

    @CreatedDate
    private Instant createdAt;
    @LastModifiedDate
    private Instant updatedAt;
    @CreatedBy
    private String createdBy;
    @LastModifiedBy
    private String updatedBy;

    protected PurchaseOrder() {}

    public PurchaseOrder(String id, String sku, long quantity) {
        if (id == null || id.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order");
        }
        this.id = id;
        this.sku = sku;
        this.quantity = quantity;
        this.status = Status.PLACED;
    }

    public void cancel() {
        if (status != Status.PLACED) {
            throw new IllegalStateException("Not cancellable");
        }
        status = Status.CANCELLED;
    }

    public String getId() { return id; }
    public String getSku() { return sku; }
    public long getQuantity() { return quantity; }
    public Status getStatus() { return status; }
    public Long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getCreatedBy() { return createdBy; }
    public String getUpdatedBy() { return updatedBy; }
}
~~~

### 5.2. Internal Event in the Same Transaction

~~~java
package example.capstone;

import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "order_events")
public class OrderEvent {
    @Id
    private String id;

    private String orderId;
    private String type;

    @CreatedDate
    private Instant createdAt;

    protected OrderEvent() {}

    public OrderEvent(String orderId, String type) {
        this.id = "order-placed:" + orderId;
        this.orderId = orderId;
        this.type = type;
    }

    public String getId() { return id; }
    public String getOrderId() { return orderId; }
    public String getType() { return type; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

The event key is constructed simply from orderId and event type in this lesson. Real systems emitting multiple events per order need a richer key, such as **orderId + event type + sequence** or an event UUID, plus explicit deduplication policies.

### 5.3. Enabling Auditing and Providing AuditorAware

~~~java
package example.capstone;

import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.mongodb.config.EnableMongoAuditing;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;

@Configuration
@EnableMongoAuditing(auditorAwareRef = "capstoneAuditor")
public class MongoInfrastructureConfiguration {

    @Bean
    public AuditorAware<String> capstoneAuditor() {
        // Fixed actor for demo so tests remain repeatable.
        return () -> Optional.of("capstone-operator");
    }

    @Bean(name = "mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

**In production:** replace the fixed actor with an **AuditorAware** reading the identity from the active security context (such as Spring Security), or a **system/job identity** for batch jobs. Define behavior for unauthenticated requests: intentionally use a system actor or reject per policy; never record a fake ID as if it were a real user.

Auditing timestamps are generated in the application; **Instant** fits absolute points in time and maps to BSON Date (millisecond precision). If tests need exact clock comparisons, configure a controlled **DateTimeProvider** rather than relying on **Instant.now()** and random sleeps.

**Never assume every update path triggers auditing.** With pipeline updates or raw MongoDB driver calls, entity callbacks may not run. Verify each API in use; if updating directly via **MongoTemplate.updateFirst(...)**, explicitly manage **updatedAt/updatedBy** and version updates.

## 6. Repositories and Transaction Service

### 6.1. Declaring Repositories

~~~java
package example.capstone;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface InventoryRepository
        extends MongoRepository<InventoryItem, String> {
}

public interface PurchaseOrderRepository
        extends MongoRepository<PurchaseOrder, String> {
}

public interface OrderEventRepository
        extends MongoRepository<OrderEvent, String> {
}
~~~

To compile as a real Java project, put **each public interface in its own file** matching its name; they are grouped together here to save space. The repositories share the database factory and MongoClient configured by Spring Boot.

### 6.2. Order Placement Service with a Single Transaction

~~~java
package example.capstone;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPlacementService {
    private final InventoryRepository inventoryRepository;
    private final PurchaseOrderRepository orderRepository;
    private final OrderEventRepository eventRepository;

    public OrderPlacementService(
            InventoryRepository inventoryRepository,
            PurchaseOrderRepository orderRepository,
            OrderEventRepository eventRepository) {
        this.inventoryRepository = inventoryRepository;
        this.orderRepository = orderRepository;
        this.eventRepository = eventRepository;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public PurchaseOrder place(
            String orderId, String sku, long quantity) {
        if (orderId == null || orderId.isBlank()
                || sku == null || sku.isBlank()
                || quantity <= 0) {
            throw new IllegalArgumentException("Invalid place request");
        }

        InventoryItem inventory = inventoryRepository.findById(sku)
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown SKU"));

        inventory.reserve(quantity);
        inventoryRepository.save(inventory);

        PurchaseOrder order = orderRepository.insert(
            new PurchaseOrder(orderId, sku, quantity)
        );

        eventRepository.insert(
            new OrderEvent(orderId, "ORDER_PLACED")
        );
        return order;
    }
}
~~~

**Why this order:**

1. Read inventory inside the transaction.
2. Check available quantity, then save the **@Version** entity.
3. **insert** the order instead of **save** so a duplicate **orderId** fails rather than overwriting an existing order.
4. Write the event in the same transaction.
5. If any step throws a runtime exception and the transaction manager controls the session, Spring marks the transaction for rollback per default rules.

**Never catch exceptions inside place and return a success result**: swallowing errors can allow prior changes in the transaction to commit. If translating exception types, throw an appropriate exception and configure rollback rules for checked exceptions.

**Important note on @Transactional:** with Spring's proxy model, **place(...) must be called via the Spring-managed bean**, never from another method on the same object via **this.place(...)** expecting the annotation to start a transaction. The proxied method must genuinely be invoked from outside the proxy. Check transaction logs/monitoring and re-read database state after the method returns.

## 7. How Does @Version Work with Transactions?

**Optimistic locking** and **multi-document transactions** address two distinct dimensions:

| Mechanism | Primary protection | Typical scenario |
| --- | --- | --- |
| **@Version** | Prevents overwriting a document modified since it was read | Two actors updating stock, balance, or status |
| **MongoDB transaction** | Consistent commit/rollback across multiple documents | Reserve stock + create order + write event |
| **Unique _id / unique index** | Blocks duplicate records by business key | orderId or payment request ID |
| **Idempotency** | Handles retried requests without running business logic twice | Timeout after commit before caller receives response |

Inside a transaction, two concurrent requests may hit a **write conflict** or MongoDB-initiated abort rather than always surfacing as **OptimisticLockingFailureException**. Do not write a handler catching only one exception type and assume all conflicts are covered.

~~~mermaid
flowchart TD
    A["Two requests reserve the same SKU"] --> B["Both read inventory"]
    B --> C["Both check available"]
    C --> D["First request updates and commits"]
    D --> E["Second request hits version/write conflict"]
    E --> F["Abort current transaction"]
    F --> G{"Can it be retried?"}
    G -- "Yes, transient error and request still valid" --> H["Start new transaction, re-read latest state"]
    G -- "No" --> I["Return categorized error"]
    H --> J["Re-check available, orderId, and idempotency"]
~~~

After a conflict, never retry saving **the same stale entity with its old version** inside an aborted transaction. When retries are allowed, start a **new transaction**, reload inventory, and re-verify all invariants. If another request already claimed the stock, the retry may legitimately turn into **Insufficient inventory**—which is a valid business outcome.

## 8. Integration Testing with a MongoDB Replica Set

Unit tests mocking repositories can verify **reserve(...)** branches, yet **cannot** prove transaction commit/rollback, BSON mapping, auditing callbacks, or server-side conflicts. For acceptance testing, use **@SpringBootTest + Testcontainers** with a replica set.

In the Spring Boot 3.x/Testcontainers 1.x example, **MongoDBContainer.getReplicaSetUrl()** provides the test replica set URI. Starting containers requires Docker or a compatible runtime. Pin a MongoDB version compatible with production; **mongo:7.0** is just one example.

### 8.1. End-to-End Service Integration Test

~~~java
package example.capstone;

import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class OrderPlacementIntegrationTest {

    @Container
    static final MongoDBContainer mongo = new MongoDBContainer(
        DockerImageName.parse("mongo:7.0")
    );

    @DynamicPropertySource
    static void mongodbProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.mongodb.uri", mongo::getReplicaSetUrl);
    }

    @Autowired OrderPlacementService service;
    @Autowired InventoryRepository inventoryRepository;
    @Autowired PurchaseOrderRepository orderRepository;
    @Autowired OrderEventRepository eventRepository;
    @Autowired MongoTemplate template;

    @BeforeEach
    void prepareFixture() {
        // Prepare collections outside business transactions.
        if (!template.collectionExists(InventoryItem.class)) {
            template.createCollection(InventoryItem.class);
        }
        if (!template.collectionExists(PurchaseOrder.class)) {
            template.createCollection(PurchaseOrder.class);
        }
        if (!template.collectionExists(OrderEvent.class)) {
            template.createCollection(OrderEvent.class);
        }

        eventRepository.deleteAll();
        orderRepository.deleteAll();
        inventoryRepository.deleteAll();
        inventoryRepository.save(new InventoryItem("SKU-1", 3));
    }

    @Test
    void shouldCommitInventoryOrderAndEventTogether() {
        PurchaseOrder order = service.place("O-101", "SKU-1", 2);

        InventoryItem stock = inventoryRepository
            .findById("SKU-1").orElseThrow();
        PurchaseOrder persisted = orderRepository
            .findById("O-101").orElseThrow();
        OrderEvent event = eventRepository
            .findById("order-placed:O-101").orElseThrow();

        assertEquals(2, stock.getReserved());
        assertEquals(1, stock.getAvailable());
        assertEquals("O-101", order.getId());
        assertEquals(PurchaseOrder.Status.PLACED,
            persisted.getStatus());
        assertEquals("ORDER_PLACED", event.getType());

        assertNotNull(stock.getVersion());
        assertNotNull(persisted.getVersion());
        assertNotNull(stock.getCreatedAt());
        assertNotNull(stock.getUpdatedAt());
        assertNotNull(persisted.getCreatedAt());
        assertNotNull(persisted.getUpdatedAt());
        assertNotNull(event.getCreatedAt());
        assertEquals("capstone-operator", persisted.getCreatedBy());
    }

    @Test
    void shouldRollBackInventoryWhenOrderIdIsDuplicate() {
        orderRepository.insert(
            new PurchaseOrder("O-DUP", "SKU-1", 1)
        );

        assertThrows(DuplicateKeyException.class,
            () -> service.place("O-DUP", "SKU-1", 2));

        InventoryItem stock = inventoryRepository
            .findById("SKU-1").orElseThrow();

        assertEquals(0, stock.getReserved());
        assertEquals(1, orderRepository.count());
        assertFalse(eventRepository.existsById("order-placed:O-DUP"));
    }

    @Test
    void shouldRejectInsufficientStockWithoutPartialWrites() {
        assertThrows(IllegalStateException.class,
            () -> service.place("O-LOW", "SKU-1", 4));

        assertEquals(0, inventoryRepository
            .findById("SKU-1").orElseThrow().getReserved());
        assertFalse(orderRepository.existsById("O-LOW"));
        assertFalse(eventRepository.existsById("order-placed:O-LOW"));
    }

    @Test
    void staleInventoryVersionMustFail() {
        InventoryItem first = inventoryRepository
            .findById("SKU-1").orElseThrow();
        InventoryItem stale = inventoryRepository
            .findById("SKU-1").orElseThrow();

        first.reserve(1);
        inventoryRepository.save(first);

        stale.reserve(1);
        assertThrows(OptimisticLockingFailureException.class,
            () -> inventoryRepository.save(stale));

        assertEquals(1, inventoryRepository
            .findById("SKU-1").orElseThrow().getReserved());
    }
}
~~~

Prerequisites to run the sample: a **@SpringBootApplication** class in an appropriate parent package scanning **OrderPlacementService**, the repositories, and **MongoInfrastructureConfiguration**. If your project defines other beans requiring Kafka, HTTP, or cloud credentials, supply appropriate test doubles or test configuration; failures in unrelated dependencies do not indicate MongoDB transactions are broken.

**Never annotate the test class itself with @Transactional** when verifying actual service commit/rollback behavior. Tests should call the service through its Spring proxy, let the method complete, and then **re-read database state outside that transaction**. In particular, avoid asserting solely on returned objects or in-memory state.

### 8.2. Testing Optimistic Locking with Two Reads

`staleInventoryVersionMustFail` is already included in **OrderPlacementIntegrationTest** in Section 8.1, so it runs against the same MongoDB Testcontainer, **SKU-1** fixture, and auditing config. The test intentionally:

1. Loads two copies from the database with **the same version**.
2. Reserves stock and saves the first copy, incrementing the version.
3. Attempts to save the stale second copy, expecting **OptimisticLockingFailureException**.
4. Re-reads inventory from MongoDB to confirm `reserved` remains **1** and was not overwritten.

No outer transaction wrapping the test is needed: the goal is observing version checks on each real save.

### 8.3. Verifying Optimistic Locking After Transactions

If you support updating orders, add a scenario:

1. Read the order twice into two separate entities with the same version.
2. Save the first order and confirm version increments.
3. Save the second order using the stale version and expect an optimistic locking failure.
4. Re-read MongoDB to confirm final state was not overwritten.
5. Verify audit **updatedAt/updatedBy** reflect only the committed write; in-memory audit fields on an unsaved object do not prove database persistence.

## 9. Auditing: Which Fields to Test and When?

Automatic auditing is convenient, yet you should define clear acceptable assertions:

| Scenario | Expectation |
| --- | --- |
| Insert new inventory | createdAt/updatedAt populated per auditing config, version initialized |
| Save existing inventory | version incremented, updatedAt and updatedBy updated per auditing policy |
| Insert order | createdAt, updatedAt, createdBy, updatedBy populated per policy; status PLACED |
| Insert event | createdAt populated when inserted via Spring Data |
| Transaction rollback | Audit changes are not committed to DB; stale in-memory Java objects may still show edits |
| Raw update bypassing mapping callbacks | Never assume auditing fires automatically; test and maintain metadata explicitly |

Example assertions for a post-update record:

~~~java
InventoryItem before = inventoryRepository
    .findById("SKU-1").orElseThrow();
Long oldVersion = before.getVersion();

before.reserve(1);
inventoryRepository.save(before);

InventoryItem after = inventoryRepository
    .findById("SKU-1").orElseThrow();
assertNotNull(after.getVersion());
assertTrue(after.getVersion() > oldVersion);
assertEquals("capstone-operator", after.getUpdatedBy());
assertNotNull(after.getUpdatedAt());
~~~

This snippet is a test body using the existing **SKU-1** fixture. Do not assert **updatedAt > createdAt** down to the millisecond: two rapid operations can share the same BSON Date millisecond timestamp. Check presence, non-decreasing order, or use a fixed **DateTimeProvider** when exact timestamps must be verified.

**Auditing does not enforce security.** An `AuditorAware` reading a username from requests can be spoofed if taken from an untrusted header. In production, read the actor from a verified authentication context, and use a distinct system actor for batch/maintenance jobs.

## 10. Error Handling, Retries, and Idempotency

### 10.1. Categorizing Errors Instead of Retrying Everything

| Error | Example | Appropriate action |
| --- | --- | --- |
| **Insufficient stock** | quantity > available | Return business error; do not blind-retry |
| **Unknown SKU** | No inventory document exists | Return input or domain error |
| **DuplicateKeyException** | orderId already exists | Check idempotency: does request match the stored order? |
| **OptimisticLockingFailureException** | Save attempted with stale version | Reload entity in a new transaction if policy allows |
| **Transient transaction/write conflict** | Multiple transactions contend on same document | Eligible for bounded retry with backoff and jitter |
| **Unknown transaction commit result** | Timeout during commit | Never assume rollback; verify orderId state |
| **No replica set** | Transaction fails on standalone | Fix topology/configuration; never retry endlessly |

**One critical edge case:** a client-side timeout after sending commit does not prove the server failed to commit. If a caller sees an error and retries with a **different orderId**, stock may be reserved twice. Use a stable **idempotency key** per request, store the request fingerprint and outcome, and distinguish **the same request** from a new request on retry.

Example design-level idempotency policy:

~~~text
requestKey = "checkout-request-123"
payload    = { sku: "SKU-1", quantity: 2 }

First attempt:
  transaction commits -> create order, reserve inventory, store requestKey.

Retry after timeout:
  look up committed requestKey;
  if payload matches, return previous result;
  if payload differs, report conflict;
  never create a second order or reserve stock twice.
~~~

The service code above uses **orderId** as a unique business key, which suffices to demonstrate duplicate scenarios. It is **not yet** a complete production idempotency mechanism: you still need concurrent retry handling, payload matching, unknown-commit responses, and key retention policies.

### 10.2. Retrying Outside the Transaction

With **@Transactional**, an aborted invocation cannot reuse the old session/transaction. To retry, an orchestration layer **outside the transaction** must invoke the proxied method afresh, reload documents, and re-check invariants. Use bounded retries, **exponential backoff with jitter**, metrics, timeouts, and error classification via driver labels.

Never put a **retry loop** inside **place(...)** and keep reusing old repositories/entities after an exception, because the transaction is already aborted. If combining retry and transaction interceptors/templates, verify **interceptor ordering** so each retry attempt starts a fresh transaction.

### 10.3. MongoDB Transactions Do Not Include Kafka or Email

If the next requirement is "send a confirmation email when an order succeeds," **never** call the email API inside the MongoDB transaction expecting atomicity. The email can be sent while the transaction rolls back.

A scalable pattern is the **transactional outbox**:

1. Same MongoDB transaction: reserve stock, insert order, and insert **outbox event**.
2. After commit: a worker reads the outbox and sends the email/Kafka message.
3. The worker manages its own retries and idempotency, marking events sent or tracking processing state.

The **order_events** collection in this lesson is a data starting point, though turning it into a production outbox requires delivery status, claim/lease tracking, retries, idempotent consumers, duplicate handling, lag monitoring, and retention. A transaction guarantees writing the event **in the same database**, not once-only delivery to external brokers.

## 11. Observability and Diagnostics in Deployment

When errors occur, logs and metrics must distinguish:

- Unknown SKU vs insufficient stock.
- Duplicate orderId.
- Optimistic version conflicts.
- MongoDB write conflicts / transaction aborts.
- Timeouts / unknown commit results.
- Replica set connectivity or authorization failures.

Log **correlation ID, orderId, SKU, error category, transaction retry count, latency, and application version**. Avoid logging secrets, sensitive payment details, raw credentials, or full user payloads.

Example **mongosh** commands to inspect state after a test:

~~~javascript
db.inventory.findOne({ _id: "SKU-1" });

db.orders.findOne({ _id: "O-101" });

db.order_events.findOne({ _id: "order-placed:O-101" });
~~~

Check server/topology when transactions fail to start:

~~~javascript
db.adminCommand({ hello: 1 });
db.adminCommand({ buildInfo: 1 });

// Requires suitable privileges; restricted on some managed services.
db.adminCommand({
  getParameter: 1,
  featureCompatibilityVersion: 1
});
~~~

**Rollback caveat:** after a failed transaction, in-memory Java objects may already have mutated **reserved**, audit fields, or versions before the driver throws. Treat **documents re-read from MongoDB after rollback** as the sole proof of committed state. Never return uncommitted objects as a "success" response.

## 12. Performance and Limits of Multi-Document Transactions

Transactions carry resource, snapshot, locking/conflict, and commit costs. For an order spanning many SKUs or thousands of documents, a long transaction increases conflict rates, memory pressure, and latency.

| Issue | Recommended design |
| --- | --- |
| Long-running transactions | Keep only MongoDB operations genuinely needing atomicity; never wait on HTTP/email inside |
| High contention on a single SKU | Monitor write conflicts; consider **atomic conditional updates** on a single document |
| High-frequency read-modify-write updates | Use **@Version** with proper transactions/retries, or atomic conditional updates |
| Continuous outbound events | Persist outbox events in the same DB and dispatch externally |
| Thousands of orders in one batch | Chunk workloads and avoid huge transactions; revisit the domain's atomic unit |
| Unacknowledged write concern | Cannot reliably enforce optimistic locking conflict detection |

**Advanced option for hot inventory:** when reserving within **one document**, you can use **MongoTemplate.findAndModify** or **updateFirst** with a sufficient-stock condition so checking and incrementing `reserved` happen in **a single atomic document operation**. For example, you could store **available** directly and apply **available ≥ quantity** with **$inc**; in that case, explicitly define data invariants and version/audit updates. In this capstone, **read + @Version + transaction** clearly demonstrates optimistic locking and multi-document atomicity, rather than claiming it is always optimal for ultra-hot SKUs.

## 13. Common Implementation Pitfalls

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `@Transactional` present yet inventory still updates when order fails | Method bypassed Spring proxy; wrong DB factory or transaction manager | Verify bean/proxy, transaction manager, shared MongoClient/session; test real rollback |
| Transaction reports replica set error | Connected to standalone instance | Run replica set or transaction-capable sharded cluster |
| Empty audit fields | Missing **@EnableMongoAuditing**, missing AuditorAware for actor fields, entity bypassed callbacks | Verify auditing config and entity write path |
| Version never increments | Direct updates bypassed versioned entity save, or wrong version mapping | Check **@Version** and actual update commands |
| Two requests both succeed when only enough stock for one | Missing concurrency/invariant control or ignored write conflicts | Test concurrently; check version/conditional updates and final state |
| Version error retries forever | Not reloading state, retrying inside aborted transaction | Retry outside transaction with bounded attempts and backoff |
| Double order after timeout | Missing idempotency key / commit verification | Use unique orderId/request key and compare payloads |
| After rollback, test still sees incremented `reserved` on Java object | In-memory object mutated though DB did not commit | Re-read from repository outside transaction when asserting |
| Incompatible Spring Boot/Spring Data major versions | Mismatched Testcontainers or Mongo property names/imports | Check BOM and migration guide; avoid arbitrary library mixing |

## 14. Extension Exercises

### Exercise A — Order Cancellation

Add **OrderCancellationService** in a MongoDB transaction:

1. Read an order with status **PLACED**.
2. Verify current version and transition to **CANCELLED**.
3. Decrement **reserved** in the corresponding inventory without letting reserved go negative.
4. Save order, inventory, and insert an **ORDER_CANCELLED** event in the same transaction.
5. Test successful cancellation, duplicate cancellation, missing order, version conflict, and rollback when event insertion fails.

**Note:** event IDs like **"order-placed:" + orderId** must be extended to a distinct identifier for **ORDER_CANCELLED**, never reusing the placement event key.

### Exercise B — Testing Two Concurrent Requests

Use **CountDownLatch** or a coordinated executor so two requests simultaneously attempt to reserve **2** units of an SKU with only **3** units in stock. Requirements:

- At most one request commits successfully for quantity 2 unless stock is replenished.
- The other request fails with a conflict or insufficient stock after retry.
- Final **reserved** never exceeds **onHand**.
- Order/event counts match committed transactions.

Never write a test that calls two requests sequentially or mocks `MongoRepository`: that does not prove race safety. Likewise, concurrency tests must not depend on which thread wins; assert **final invariants**.

### Exercise C — Security-Integrated Auditing

Replace **capstone-operator** with an **AuditorAware<String>** reading the user ID from a verified security context. Handle unauthenticated requests and batch jobs with a system identity; test user A editing a document created by user B:

- **createdBy** stays B.
- **updatedBy** changes to A.
- **createdAt** is not overwritten by **updatedAt**.
- Version increments on real updates via entity save.

### Exercise D — Handling Events Outside the Transaction

Design an outbox worker forwarding events to a broker or email service; describe retries, idempotency, processing states, duplicate delivery handling, and crash recovery. Never claim MongoDB transactions provide "exactly once delivery" to external systems.

## 15. Capstone Acceptance Checklist

- [ ] Inventory uses **@Version** and upholds **0 ≤ reserved ≤ onHand**.
- [ ] Order uses **@Version**; new writes use unique identifiers and never overwrite duplicate orders.
- [ ] Audited entities have **@CreatedDate / @LastModifiedDate** and appropriate actor metadata.
- [ ] **@EnableMongoAuditing** and contextual **AuditorAware** are configured and callbacks verified.
- [ ] **MongoTransactionManager** is configured and **@Transactional** runs through a Spring proxy.
- [ ] Test MongoDB is a transaction-capable replica set or sharded cluster.
- [ ] Happy-path test re-reads inventory, order, and event after commit.
- [ ] Failure test during order insertion proves inventory is **not** partially committed.
- [ ] Stale-version test proves updates are never silently lost.
- [ ] Concurrency test asserts final invariants.
- [ ] Policies exist for conflict handling, transient retries, and unknown commit results.
- [ ] Plans exist for request idempotency and outbox integration with external systems.
- [ ] No external network, email, or broker calls sit inside a MongoDB transaction expecting atomicity.
- [ ] Logs and metrics support diagnostics without leaking sensitive data.

## 16. References

1. [Spring Data MongoDB — Optimistic Locking](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html#mongo-template.optimistic-locking): **@Version** annotation, stale update detection, and write concern.
2. [Spring Data MongoDB — Auditing](https://docs.spring.io/spring-data/mongodb/reference/mongodb/auditing.html): **@EnableMongoAuditing**, **AuditorAware**, creator/modifier metadata, and timestamps.
3. [Spring Data MongoDB — Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): **MongoTransactionManager**, sessions, transactions, and execution limits.
4. [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): proxies, **@Transactional**, rollback rules, and transaction propagation.
5. [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): topology, multi-document atomicity, errors, and limits.
6. [MongoDB Manual — Production Considerations for Transactions](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/): locking, timeouts, concurrency, resources, and operational traits.
7. [MongoDB Manual — Retryable Writes and Transaction Errors](https://www.mongodb.com/docs/manual/core/retryable-writes/): distinguishing retryable writes from transaction errors; check driver docs.
8. [Testcontainers — MongoDB Module](https://java.testcontainers.org/modules/databases/mongodb/): creating test MongoDB environments, including replica set URLs.

**Conclusion:** **@Version** protects updates from acting on stale reads; **auditing** records who changed what and when; **MongoDB transactions** keep multi-document saves consistent. A passing capstone does more than place annotations properly: it **proves against real MongoDB data** that successes commit completely, failures roll back cleanly, conflicts never lose updates, and audit metadata reflects persisted writes.
