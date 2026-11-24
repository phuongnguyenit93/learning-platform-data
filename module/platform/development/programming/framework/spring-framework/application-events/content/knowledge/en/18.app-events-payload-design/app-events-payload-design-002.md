# Business Object Identifiers in Spring Application Events Payloads

## 1. Goal: Events Carry IDs Instead of Wrapping Entire Entities

When a business operation changes state, a Spring application can publish an event via `ApplicationEventPublisher` and handle it with `@EventListener` or `ApplicationListener`. A crucial design decision is: **should the event carry the entire business object or only the identifier of that object?**

For example, after creating an order:

~~~java
// Simple and easy to control: payload contains IDs and necessary event information.
public record OrderPlaced(
    UUID eventId,
    UUID orderId,
    long aggregateVersion
) {}
~~~

Contrast with:

~~~java
// Caution: payload carries a reference to a mutable JPA entity.
public record OrderPlaced(OrderJpaEntity order) {}
~~~

These snippets are **illustrative code**, not standalone programs. `OrderJpaEntity` is assumed to be an application entity.

Passing an ID keeps listeners **decoupled from the same entity instance, persistence context, lazy-loading proxies, or overly large object graphs**. It also clarifies module boundaries: the publisher announces "order with ID X has been created", while the consumer chooses how to retrieve data according to its needs.

However, the rule "always pass only the ID" is not absolute. If a consumer needs the exact state at the moment the event occurred, re-reading the object by ID at processing time might see a newer version or find the object deleted. In such cases, combine **ID + eventId + version**, an immutable snapshot, or an outbox depending on the data contract.

This lesson focuses on choosing, generating, naming, passing, and validating **business object identifiers** in Spring Application Events.

## 2. Defining the Types of IDs to Distinguish

A real-world payload may contain several fields ending in `Id` that serve completely different responsibilities.

| Field | What Does It Identify? | Example | Key Property |
|---|---|---|---|
| `orderId` / `aggregateId` | A specific business object or aggregate | Order UUID | Stable across the object's lifecycle |
| `eventId` | A specific event **occurrence** | UUID of `OrderPlaced` | Used for per-event deduplication/idempotency |
| `customerId` | Another related business object | Customer ID | Must keep owner/ID type clear |
| `tenantId` | The tenant space the object belongs to | Organization ID | Used for access scoping and data routing |
| `correlationId` | A request flow or workflow spanning multiple events | Saga/request ID | Supports business tracing |
| `causationId` | The event or command that caused the current event | Source event ID | Supports tracing causal relationships |
| `aggregateVersion` | The version of the object when the event was published | 12 | Supports ordering/staleness checks; **not an ID** |

**Do not use `orderId` in place of `eventId`.** One order can emit `OrderPlaced`, `OrderPaid`, `OrderShipped`, and multiple `OrderUpdated` events; all share the same `orderId` yet must be uniquely identifiable per emission.

Example:

~~~json
{
  "eventId": "22222222-2222-4222-8222-222222222222",
  "eventType": "OrderPaid",
  "orderId": "11111111-1111-4111-8111-111111111111",
  "aggregateVersion": 7,
  "correlationId": "checkout-req-391",
  "occurredAt": "2026-11-11T05:20:00Z"
}
~~~

This JSON only illustrates the design; the UUIDs and timestamp here are hypothetical. The **business ID** answers "which object?", the **event ID** answers "which change occurrence?", and the **version** answers "which state revision?".

## 3. Technical IDs and Business Codes Can Be Two Different Things

Many systems have both a storage key and a display code:

~~~text
orders.id             = 9be6d7ce-...
orders.order_number   = SO-2026-000137
~~~

- `id`: a stable technical key for referencing across modules, tables, and events.
- `orderNumber`: a user-entered or user-visible code that may encode rules by year, branch, order type, or external systems.

If a business code can change, be reassigned, or is not globally unique, **do not treat it as the primary identity** of the aggregate. Events should carry a guaranteed-unique, stable key; display codes belong only as supplementary information when genuinely needed.

Some commonly used ID types:

| Type | Pros | Considerations |
|---|---|---|
| DB-generated `long`/`Long` | Short, efficient storage/indexing, easy with SQL relations | Often unavailable before insert; hard to merge across systems without a namespace |
| App-generated `UUID` | Can be created before persistence; suits distributed systems | Longer; need to evaluate index locality and generation strategy |
| Business code `String` | Easy to attach meaning and integrate with external systems | Format may change; easy to confuse display codes with stable keys |
| `record OrderId(UUID value)` | Type-safe, prevents mixing `OrderId` with `CustomerId` | Requires converters/serializers and JSON contract definition |
| Composite key, e.g., `(tenantId, orderId)` | Fits multi-tenant systems or tenant-scoped unique IDs | Consumers must receive all parts, with matching indexes and uniqueness rules |

**Principle:** the ID type must reflect the domain's *true identification rules*. Do not assume every numeric ID is a primary key; do not assume a UUID automatically makes events durable or deduplicated.

## 4. Recommended Payload Pattern with Java Records

Java 17 provides `record`, well-suited for simple events that are immutable at the level of record components:

~~~java
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPaid(
    UUID eventId,
    UUID orderId,
    long aggregateVersion,
    Instant occurredAt
) {
    public OrderPaid {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        if (aggregateVersion < 1) {
            throw new IllegalArgumentException("version must be positive");
        }
    }
}
~~~

This is an **illustrative record snippet**. When choosing a payload, establish:

1. **Clear domain naming:** `orderId` is better than `id` if an event involves multiple related objects.
2. **Non-null:** validate at construction time rather than waiting for listeners to discover nulls.
3. **Stable types:** consider converters among `OrderId`/`UUID`/`String` across module or JSON boundaries.
4. **Event occurrence:** provide `eventId` when replay, observability, or deduplication is needed.
5. **Version:** if listeners need to distinguish older vs. newer updates, carry the persisted or properly assigned aggregate version.
6. **Timestamp:** `occurredAt` is when the event was recorded, **does not prove commit completion**, and is not an absolute global clock.
7. **No secrets:** avoid passwords, access tokens, and unnecessary personal data; IDs themselves can also be sensitive depending on the domain.

### Records Are Shallowly Immutable

A `record` makes its **reference fields** final and provides a constructor/accessors, yet if a field is a `List` or a mutable entity, the referenced object itself can still be mutated. For identifier events, prefer immutable components such as `UUID`, `String`, primitives, or genuinely immutable value objects.

Example to avoid:

~~~java
public record OrderChanged(UUID orderId, List<OrderLineEntity> lines) {}
// The List and the OrderLineEntity objects inside may still be mutable.
// Do not treat this as an immutable snapshot just because it uses a record.
~~~

The snippet above is illustrative; `OrderLineEntity` and imports must be defined in the application.

## 5. Why Avoid Passing JPA Entities Through Events by Default?

Consider the payload:

~~~java
record OrderPlaced(Order order) {}
~~~

If `Order` is a JPA entity, this event can run into several issues:

- **Mutable reference:** publisher and listener hold the same Java object; the listener sees state changes made after the event was created.
- **Persistence context:** the entity is managed in transaction T1 but becomes detached in another worker/transaction.
- **Lazy loading:** accessing `order.getItems()` after the session closes can throw `LazyInitializationException`.
- **Coupling:** listeners become tied to the entity type and internal mapping of the event-producing module.
- **Serialization:** entities contain complex associations/proxies, circular references, or data you do not intend to send.
- **Timing:** async listeners may execute after commit; the passed entity does not automatically reattach.

Instead of sharing the object, the publisher emits:

~~~java
publisher.publishEvent(new OrderPlaced(order.getId(), order.getVersion()));
~~~

and the consumer uses its own repository if needed:

~~~java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Order order = repository.findById(event.orderId())
        .orElseThrow();
    // Only use data that is truly needed; pay attention to transaction boundaries and read timing.
}
~~~

These two snippets are an **integration pattern**; `Order`, `OrderPlaced`, and `repository` must be defined consistently. **Passing an ID does not automatically solve all timing issues:** when an event is published before commit, an async consumer reading the database might not see the record yet; after commit, it might already have changed again.

## 6. Runnable Java 17 Example: Distinguishing `eventId`, `orderId`, and Current State

This example uses Spring Framework **6.2.8**, Maven, Java 17, and an in-memory repository to clarify the boundary between identifier payloads and entity state. No Spring Boot, database, or transactions are needed to run the core example.

The program performs:

1. Creates a type-safe `OrderId`.
2. Stores order state in the repository.
3. Publishes an `OrderPlaced` containing `eventId`, `orderId`, and `aggregateVersion`.
4. The listener receives only the ID-carrying event, then **queries the repository by ID**.
5. After the event is handled, the service updates the order state further; the already-published event is not mutated along with the new record.

Structure:

~~~text
business-id-event-demo/
├── pom.xml
└── src/main/java/demo/BusinessIdEventDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>business-id-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/BusinessIdEventDemo.java

~~~java
package demo;

import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class BusinessIdEventDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {

            OrderId orderId = new OrderId(UUID.fromString(
                "00000000-0000-0000-0000-000000000197"
            ));

            OrderService service = context.getBean(OrderService.class);
            OrderRepository repository = context.getBean(OrderRepository.class);

            service.place(orderId);

            repository.changeStatus(orderId, "PACKED");
            OrderState current = repository.find(orderId).orElseThrow();

            System.out.println("after update: " + current.status()
                + " (version=" + current.version() + ")");
        }
    }

    public record OrderId(UUID value) {
        public OrderId {
            Objects.requireNonNull(value, "value");
        }
    }

    public record OrderPlaced(
        UUID eventId,
        OrderId orderId,
        long aggregateVersion
    ) {
        public OrderPlaced {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            if (aggregateVersion < 1) {
                throw new IllegalArgumentException("aggregateVersion < 1");
            }
        }
    }

    public record OrderState(OrderId id, String status, long version) {
    }

    public static final class OrderRepository {
        private final Map<OrderId, OrderState> orders =
            new ConcurrentHashMap<>();

        public void save(OrderState state) {
            orders.put(state.id(), state);
        }

        public Optional<OrderState> find(OrderId id) {
            return Optional.ofNullable(orders.get(id));
        }

        public void changeStatus(OrderId id, String newStatus) {
            orders.compute(id, (key, current) -> {
                if (current == null) {
                    throw new IllegalStateException("Order not found");
                }
                return new OrderState(id, newStatus, current.version() + 1);
            });
        }
    }

    public static final class OrderService {
        private final OrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public OrderService(OrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void place(OrderId orderId) {
            repository.save(new OrderState(orderId, "PLACED", 1L));
            publisher.publishEvent(new OrderPlaced(
                UUID.fromString("00000000-0000-0000-0000-000000000901"),
                orderId,
                1L
            ));
        }
    }

    public static final class OrderPlacedListener {
        private final OrderRepository repository;

        public OrderPlacedListener(OrderRepository repository) {
            this.repository = repository;
        }

        @EventListener
        public void handle(OrderPlaced event) {
            OrderState state =
                repository.find(event.orderId()).orElseThrow();

            System.out.println("received orderId: "
                + event.orderId().value());
            System.out.println("received eventId: " + event.eventId());
            System.out.println("event version: "
                + event.aggregateVersion());
            System.out.println("state at handling: " + state.status());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderRepository orderRepository() {
            return new OrderRepository();
        }

        @Bean
        public OrderService orderService(
                OrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new OrderService(repository, publisher);
        }

        @Bean
        public OrderPlacedListener orderPlacedListener(
                OrderRepository repository) {
            return new OrderPlacedListener(repository);
        }
    }
}
~~~

Run from the `business-id-event-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.BusinessIdEventDemo
~~~

Lines printed by the application when running properly:

~~~text
received orderId: 00000000-0000-0000-0000-000000000197
received eventId: 00000000-0000-0000-0000-000000000901
event version: 1
state at handling: PLACED
after update: PACKED (version=2)
~~~

### Reading the Results Correctly

- `OrderPlaced` is an ordinary payload record; Spring Framework allows `ApplicationEventPublisher.publishEvent(Object)` to accept objects that do not extend `ApplicationEvent`. Spring wraps it in a `PayloadApplicationEvent` and dispatches it to matching listeners.
- `OrderId` is a value object wrapping a UUID. Two different order IDs cannot be accidentally treated as the same domain type merely because both use `UUID`.
- `eventId` identifies the specific event, **not equal to** `orderId`. In the demo, two fixed UUIDs keep stdout deterministic; real systems must have a unique event ID generation policy such as `UUID.randomUUID()` or system-assigned IDs.
- Because the listener is synchronous by default, it queries the repository while the state is still `PLACED`. Only after the publish call finishes does the program transition the state to `PACKED`/version 2.
- The published event retains `aggregateVersion=1`. If a listener processes late and re-queries the repository, it may read `PACKED`/version 2. That is precisely why **the event that occurred** must be distinguished from **the state at lookup time**.
- The in-memory repository uses immutable records, `ConcurrentHashMap`, and `compute` for illustration, **not a DB transaction**. This example does not claim atomicity or crash-recovery replay.

When you need to prove real commit/rollback behavior, replace the repository with JDBC/JPA/R2DBC plus a transaction manager and test at the DB boundary. Never assume guarantees in an in-memory demo are database guarantees.

## 7. Where Are IDs Generated and When Can Events Be Published?

### Case A: Application-Generated ID Before Saving

~~~java
UUID orderId = UUID.randomUUID();
Order order = new Order(orderId, ...);
repository.save(order);
publisher.publishEvent(new OrderPlacedEvent(UUID.randomUUID(), orderId));
~~~

The illustrative snippet above requires defining `Order` and `OrderPlacedEvent`. Advantage: the ID is available upfront, convenient for writing an outbox record in the same transaction. However, if the DB save fails or the transaction rolls back, a directly published event may already have been received by synchronous listeners. **Having an ID early does not mean the record has committed.**

### Case B: Database-Assigned ID

~~~java
@Transactional
public void createOrder(CreateOrder command) {
    Order order = new Order(command);
    Order saved = orderRepository.save(order);

    // Only publish once the ID has actually been assigned per the ORM's ID strategy.
    if (saved.getId() == null) {
        throw new IllegalStateException("Order ID was not assigned");
    }

    publisher.publishEvent(new OrderCreated(
        UUID.randomUUID(), saved.getId()
    ));
}
~~~

This is **integration code**, not a standalone program. With JPA ID generation, when the ID becomes available depends on the strategy (`IDENTITY`, sequence, UUID generator, etc.). When interacting with a real DB, `save`, `flush`, and commit carry distinct semantics:

- **ID assigned:** the application has a key to identify the entity.
- **SQL flushed:** the ORM has sent the necessary SQL to the DB inside the transaction; it can still roll back.
- **Transaction committed:** the transaction's changes are confirmed as successfully completed.

Do not use `flush()` as a substitute for commit. Do not publish events with a `null` ID, and do not assume every entity has an ID immediately upon calling its constructor.

### Events When Deleting an Object

With `OrderDeleted(orderId)`, listeners generally **cannot re-read the entity** after commit because the record has been deleted. If consumers need extra values such as name, pre-deletion state, or routing metadata, the event should carry a minimal immutable snapshot or sufficient tombstone/metadata for processing. This case illustrates why the "ID-only is enough" rule depends on the use case.

## 8. Transactions: Publishing an Event with an ID Before Commit Does Not Guarantee That ID Is Readable

In Spring, regular `@EventListener` methods are invoked synchronously when using the default multicaster. If the service is inside `@Transactional`, a synchronous listener may run **inside the still-open transaction**. If a listener uses `@Async` or a multicaster executor, work may run on another thread without the same transaction. In that case, a `SELECT` by ID might not see uncommitted rows or might encounter unexpected data.

Risky pattern:

~~~java
@Transactional
public void place(long orderId) {
    repository.insert(orderId);
    publisher.publishEvent(new OrderPlaced(orderId));
    // T1 has not committed yet at publish time.
}
~~~

This is an illustrative architectural pattern. If the listener sends a message externally and then the transaction rolls back, the external system may receive the ID of a record that never existed in a committed state.

When post-processing should occur **only after a successful commit**, consider:

~~~java
@Component
class SearchIndexerListener {
    private final CommittedOrderReader reader;

    SearchIndexerListener(CommittedOrderReader reader) {
        this.reader = reader;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        OrderSnapshot snapshot = reader.load(event.orderId());
        // Update the index using the snapshot read after commit.
    }
}
~~~

Here `OrderPlaced`, `OrderSnapshot`, and `CommittedOrderReader` are hypothetical application types that must be defined; this is not standalone runnable code. **By default, `@TransactionalEventListener` only handles events published within an appropriate transaction**; without a transaction, it does not run unless `fallbackExecution=true` is enabled. An event is not guaranteed "exactly-once processing" merely because `AFTER_COMMIT` is used.

### Re-reading from the DB Should Have an Explicit New Transaction

Spring notes that during `AFTER_COMMIT`, the transaction has committed, yet resources may still be bound to the thread prior to cleanup. If the consumer needs a `SELECT` with a fresh transaction boundary, extract it into another bean:

~~~java
@Service
public class CommittedOrderReader {
    private final OrderRepository repository;

    public CommittedOrderReader(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        readOnly = true
    )
    public OrderSnapshot load(OrderId id) {
        Order order = repository.findById(id).orElseThrow();
        return new OrderSnapshot(order.getId(), order.getStatus());
    }
}
~~~

This is integration code; it requires Spring transaction imports, `OrderRepository`, `Order`, `OrderId`, and `OrderSnapshot` matching the application. `REQUIRES_NEW` establishes an independent transaction via the appropriate transaction manager, separating this read from the old persistence context. The call must go through a **Spring proxy**: self-invocation `this.load(...)` inside the same bean may bypass the annotation.

Keep in mind: **AFTER_COMMIT does not mean reading the exact event version**. If another transaction updates that ID right after commit and before the `SELECT`, the listener may see a newer version. If reading from a read replica, it may even see stale data due to replication lag. An ID only points to *which object*, without carrying a historical snapshot.

## 9. Versioning, Concurrency, and Correctness When Re-reading

Suppose the business sequence is:

~~~text
T1: Order #42 = PLACED, version 1; commit
    +--> publish OrderPlaced(orderId=42, version=1)
T2: Order #42 = PAID, version 2; commit
OrderPlaced listener reads DB by ID #42
    +--> receives version 2 instead of version 1
~~~

If the listener's job is "build a projection of the **latest state**", seeing version 2 may be valid. If its job is "send a notification that **the order was just placed** with exact placement details", carrying only the ID is insufficient.

Common strategies:

| Consumer Goal | Suitable Design |
|---|---|
| Fetch latest state | ID + repository lookup, accepting eventual consistency |
| Process only if version matches | ID + `aggregateVersion` + version check before applying |
| Replay exact change history | Event containing durably persisted immutable snapshot/delta |
| Recover when consumer was offline | Outbox/broker combining `eventId` and versioned payload |
| Sync multiple updates without reordering | Sequence/version with partitioning by aggregate ID; design reorder/dedup |
| Handle delete when record is gone | Tombstone event containing ID and minimal metadata |

### Version Checking Rules

For example, a projection consumer stores `lastAppliedVersion`. It receives event version 11 when the DB/projection is currently at version 10:

~~~text
incoming.version <= lastAppliedVersion  -> already applied or stale event; skip/check
incoming.version == lastAppliedVersion+1 -> apply next update
incoming.version > lastAppliedVersion+1  -> missing gap; wait or resync
~~~

This is **one strategy**, not a default Spring rule. It works when versions are assigned contiguously within the aggregate scope and the consumer processes a stream following that contract. If the application skips certain event types or versions do not increment on every event, you cannot strictly require `+1`. When multiple valid events share the same version, add an event/aggregate-level sequence.

### Why Not Use Timestamps Instead of Versions?

Timestamps can collide, drift between node clocks, or be recorded at a different moment from commit. `occurredAt` is great for audit/observability, but not as the sole basis for deciding absolute ordering in a distributed system.

## 10. `eventId` and Idempotency: One Entity Has Many Valid Events

A consumer receives the same `eventId` twice due to a retry. It must recognize duplicates and handle them safely.

Example:

~~~text
OrderPaid(eventId=E1, orderId=O1, version=4)
OrderShipped(eventId=E2, orderId=O1, version=5)
Retry: OrderPaid(eventId=E1, orderId=O1, version=4)
~~~

If deduplicating by `orderId=O1`, the consumer would mistakenly drop the valid `OrderShipped`. If deduplicating by `eventId`, only the retry of E1 is flagged as a duplicate.

One state-tracking model:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

When a consumer processes a critical event in a database, it can record the event and execute DB side effects **within the same local transaction**; the unique constraint ensures it is applied only once for that consumer. If the side effect sends an email, calls an API, or publishes to another system, a local DB transaction **does not automatically make those side effects exactly-once**. You need idempotency keys on the target API, an outbox for the next step, or controlled retry mechanisms.

Distinguish clearly:

- **`eventId`** is unique per occurrence; retries of the same occurrence keep the same `eventId`.
- **`commandId`** identifies a request to trigger a change; it may relate to `eventId` but should not be assumed identical.
- **`orderId`** identifies the aggregate, used for lookup and partitioning/ordering.
- **`messageId`** assigned by a broker may differ from `eventId`; broker hops should not destroy the event's business identity.

Name identifier fields accurately in payloads to prevent flawed deduplication.

## 11. Multi-Tenant Cases and Composite Keys

In a multi-tenant SaaS, the same `orderId=42` might exist in tenant A and tenant B if IDs are only unique per tenant. In that case, the true identity is the pair `(tenantId, orderId)`.

~~~java
public record OrderKey(UUID tenantId, long orderId) {
    public OrderKey {
        Objects.requireNonNull(tenantId, "tenantId");
        if (orderId <= 0) {
            throw new IllegalArgumentException("orderId must be positive");
        }
    }
}

public record OrderPlaced(UUID eventId, OrderKey orderKey) {}
~~~

These are illustrative records importing `UUID` and `Objects`. Consumers **must not** call `findById(orderId)` if the data store requires a tenant:

~~~java
repository.findByTenantIdAndId(
    event.orderKey().tenantId(),
    event.orderKey().orderId()
);
~~~

Having `tenantId` in an event **does not automatically authenticate access rights**. When events arrive via a broker or external system, verify the source, authorization, and consumer tenant scope. Do not trust every `tenantId` from a payload as validated input.

Even when using globally unique UUIDs for orders, `tenantId` may still be needed for routing, data filtering, security policies, and auditing; design according to the system contract.

## 12. IDs as Value Objects: Type Safety and Serialization

Instead of passing indistinguishable `UUID`s throughout the codebase, you can create:

~~~java
public record OrderId(UUID value) {
    public OrderId {
        Objects.requireNonNull(value, "value");
    }
}

public record CustomerId(UUID value) {
    public CustomerId {
        Objects.requireNonNull(value, "value");
    }
}
~~~

Java prevents passing a `CustomerId` into a method expecting an `OrderId`, helping avoid ID mix-ups during refactoring or when adding related objects.

However, value objects need conversion conventions:

- With JPA: map via `AttributeConverter` or an appropriate mapping; do not assume Hibernate understands every record ID wrapper out of the box.
- With JDBC: bind the actual SQL type (`UUID`/`VARCHAR`...) and convert to/from `OrderId` in the repository layer.
- With JSON: define the contract explicitly as a flat UUID string (e.g., `"f7..."`) or an object `{"value":"f7..."}`; configure serializers/deserializers consistently.
- With Kafka/AMQP/HTTP: maintain schema versions, field names, and compatible lengths/formats so old consumers do not break.

If multiple services use different languages, sharing the Java `OrderId` class is unnecessary; you only need to agree on the **wire format** and field semantics. Strong domain types belong inside the application, while public message schemas must remain resilient across deployment versions.

### UUID, ULID, and Key Generation

Random UUIDs are convenient for identification prior to DB inserts. Time-ordered variants (such as UUIDv7), ULIDs, or sequences offer trade-offs in sortability, storage, and distribution. Do not choose solely by string length; evaluate allocation capability, collisions, database indexing, metadata sensitivity, and library/system support.

**Do not use sequential IDs as an access-control mechanism.** Guessable IDs will not expose other records if APIs enforce proper authorization; still, systems should avoid exposing sensitive IDs unnecessarily.

## 13. Minimal Snapshot or Query by ID?

Depending on business requirements, one of three forms may be appropriate:

### A. ID-Only

~~~java
public record CustomerAddressChanged(UUID customerId) {}
~~~

Pros: small payload and loosely coupled. Cons: consumer must query; if the address changes again before the consumer reads, the event does not describe the old/new values.

### B. ID + Necessary Immutable Attributes

~~~java
public record OrderPaid(
    UUID eventId,
    UUID orderId,
    long version,
    String currency,
    long amountMinorUnits
) {}
~~~

Pros: consumers can process using exact values at event time. Cons: contract carries more data, requiring schema management, PII control, and accurate snapshot creation.

### C. ID + Version with Consumer Querying Historical State

~~~java
public record OrderChanged(
    UUID eventId,
    UUID orderId,
    long version
) {}
~~~

Suitable when the repository has **historical snapshots/an event store** or a version-aware API; if only a single row holds the latest state, `version=5` alone cannot help `SELECT` state version 5 once the row has moved to version 6.

**Selection rule:** if downstream logic must make decisions based on values that cannot shift over time, send the minimal necessary snapshot/delta or maintain an appropriate historical store. If the goal is merely a trigger saying "an update happened, sync the latest state", an ID is usually enough.

## 14. Durable Delivery: Transactional Outbox with `aggregateId`

`ApplicationEventPublisher` is an in-JVM event mechanism, not a durable queue. For events spanning microservices, the practical approach is typically writing to an outbox **in the same transaction** as the aggregate change.

Example schema:

~~~sql
CREATE TABLE orders (
    id VARCHAR(36) PRIMARY KEY,
    state VARCHAR(20) NOT NULL,
    version BIGINT NOT NULL
);

CREATE TABLE outbox_events (
    event_id VARCHAR(36) PRIMARY KEY,
    event_type VARCHAR(80) NOT NULL,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(36) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    payload_json CLOB NOT NULL,
    created_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
~~~

Within one transaction T1:

~~~text
1. Create/update orders(id, state, version)
2. Generate eventId and immutable payload
3. INSERT outbox_events(eventId, aggregateId, version, payload)
4. COMMIT T1
5. An independent worker reads outbox, publishes message, marks published
6. Consumer deduplicates by eventId and processes idempotently
~~~

Because `orders` and `outbox_events` share the same DB/transaction, rolling back T1 rolls back both. If the process dies after commit but before publishing, the outbox record remains for later processing. However, if the worker publishes successfully and crashes before marking it published, it may resend the message: **at-least-once handling and idempotency are required**; an outbox does not automatically grant end-to-end exactly-once delivery.

Key identifiers:

- `event_id`: PK of the event record; ideal for deduplication.
- `aggregate_id`: object key, used for partitioning/routing.
- `aggregate_version`: ordering/version control if the system maintains that contract.
- `event_type`/`schemaVersion`: message classification and compatibility.
- `payload_json`: minimal facts so consumers do not depend directly on the publisher's database.

If the outbox pipeline uses CDC, the broker partition key is typically the aggregate ID to improve ordering for the same object, yet **there is no automatic guarantee that the entire end-to-end pipeline always processes strictly in order**; consumers must still manage retries, partitions, fan-out, and versions.

## 15. Designing Events for Internal Modules vs. External Integration

Internal Java events and integration events do not have to use the exact same class:

~~~text
OrderService
  |
  | domain event: OrderPaid(orderId, eventId, version)
  v
In-process @EventListener
  |
  | map to integration event schema v2
  v
Outbox / Broker
  |
  | JSON/Avro/Protobuf containing ID, type, version, occurredAt
  v
Other service
~~~

A dedicated mapper can convert a type-safe `OrderId` to a UUID/string per the wire schema. Separating internal events from integration events keeps the domain from constantly exposing entity models or internal schema changes.

Properties that should be defined in an event contract:

| Property | Questions to Answer |
|---|---|
| Owner | Which module has authority to define the meaning of `orderId`? |
| Uniqueness | Is the ID unique system-wide, per tenant, or per aggregate type? |
| Lifetime | Can an ID be reused after deletion? |
| Format | Standard UUID, integer, prefixed string, base64…? |
| Serialization | String or number? Is precision lost across JS? |
| Versioning | When and by what rules does aggregate version increment? |
| Deduplication | Does the consumer use `eventId` or a composite key? |
| Authorization | Is the consumer allowed to read this ID? |
| Missing state | If the entity is deleted or not yet replicated, retry/skip/tombstone? |

Specifically when crossing into JavaScript, 64-bit integers larger than `Number.MAX_SAFE_INTEGER` can lose precision if serialized as JSON numbers and parsed by the client as `Number`. For `long` IDs crossing JS-facing boundaries, consider string representation and publish an explicit contract.

## 16. Testing Payloads Containing IDs

A useful test suite should prove the following properties.

### Test 1 — Event Does Not Share a Mutable Entity

Publisher emits `OrderPlaced(orderId, version=1)`, then the repository changes state to version 2. Assert the event still holds version 1; late-processing listeners must have a clear reading policy.

### Test 2 — Correct ID and Correct Type

Use type-safe `OrderId` and `CustomerId`, or test with valid request IDs to confirm the consumer looks up the right aggregate. Avoid ambiguous `String id` in APIs handling multiple ID types.

### Test 3 — Rollback Does Not Trigger `AFTER_COMMIT` Post-Processing

In a real Spring transaction test, publish an event in T1 and roll back. The `@TransactionalEventListener(AFTER_COMMIT)` listener does not execute. Test the commit branch and verify the event is handled once the transaction completes.

### Test 4 — Duplicate Events

Send two copies with the same `eventId`. An idempotent consumer applies the side effect only once; a different event with the **same `orderId` but a different `eventId`** is still processed.

### Test 5 — Missing or Deleted Entity

Publish an event carrying a deleted ID; the consumer should not blindly call `orElseThrow()` and loop retries forever. Define how to distinguish transient errors (replication lag) from objects that truly no longer exist (tombstone/terminal state).

### Test 6 — Concurrency and Versioning

Deliver event version 5 after version 6. The consumer must not accidentally overwrite the newer projection with stale data. Also test two valid events for the same aggregate arriving out of order.

### Test 7 — JSON Format and Multi-Tenancy

Round-trip the payload through the serializer; verify IDs do not change type, truncate digits, lose `tenantId`, or mix up IDs between two object types. At external APIs, verify access permissions rather than blindly trusting IDs.

With async processing, use `CountDownLatch` or bounded-timeout await utilities; never just call `publishEvent`, immediately assert, and assume the listener has finished.

## 17. Common Pitfalls and Remedies

| Symptom / Mistake | Possible Cause | Fix |
|---|---|---|
| Event has `orderId=null` | DB-generated ID not yet assigned; published too early | Check ID strategy and save/flush timing |
| Consumer reads and finds no record | Published before commit; async or replica lag | Use proper transaction phase, bounded retries, read primary when needed |
| Consumer reads a different state from event time | Record updated further after event | Carry version/snapshot or query history |
| `LazyInitializationException` | Payload carries lazy entity/proxy across transactions | Switch to ID + immutable DTO, fetch within consumer's transaction |
| Valid event mistakenly dropped | Deduplicating by `aggregateId` instead of `eventId` | Store processed `eventId` per consumer |
| Changing order number breaks links | Display code used as primary identity | Use a stable ID and keep business codes separate |
| Customer ID used as order ID | APIs both accept `UUID`/`String` | Use value objects or clearly named fields |
| Mixing orders across tenants | ID only unique per tenant; query missing `tenantId` | Define `OrderKey`; query and authorize by tenant |
| Event after deletion cannot be looked up | Object is already gone | Tombstone/minimal snapshot event or not-found policy |
| Duplicate side effects on retry | Not storing `eventId`/idempotency key | DB uniqueness + idempotent side effects |
| Slow listener slows down publisher | `@EventListener` is synchronous by default | Decouple via appropriate async/queue; understand errors and transactions |
| Consumer loses events after crash | Application events are not durable | Outbox/broker/retry and processing state tracking |
| JSON rounds `long` IDs | Consumer uses JS `Number` for large numbers | Serialize IDs as strings, document schema |
| Exposes another user's object | Knows ID but lacks authorization | Enforce permission checks at every boundary and consumer |

## 18. Quick Design Checklist

Before finalizing an event with an entity ID, ask:

1. **Which object?** `orderId`, `customerId`, or a composite key?
2. **Where is it stable and unique?** System-wide or within a tenant?
3. **When is the ID ready?** Available before saving, after insert/flush, or only after a business step?
4. **What state does the consumer need?** Latest state, state at event time, or just knowing the event happened?
5. **Is there a dedicated `eventId`?** Can retries and deduplication accurately identify a single emission?
6. **Is there a version?** If concurrency matters, does the version have a clear contract?
7. **What happens on rollback?** Should listeners run before/after commit, or does the event require an outbox?
8. **Can the entity be deleted before reading?** Is there a tombstone/snapshot or not-found policy?
9. **Is it multi-tenant?** Do IDs and lookups include tenant scoping and authorization?
10. **Does it cross out of the JVM?** Have schema, serialization, privacy, idempotency, and durability been addressed?

### Summary

In Spring Application Events, a payload carrying a **business object identifier** is a key approach to reducing coupling between publishers and listeners. It keeps events lightweight, avoids references to mutable entities/persistence contexts, and lets consumers retrieve data via their own repositories or APIs.

However, distinguish **`aggregateId`** ("which object"), **`eventId`** ("which event occurrence"), **`version`** ("which state revision"), and **snapshot** ("values when the event occurred"). An ID alone does not prove data committed, does not preserve historical state, and does not guarantee delivery. Combine proper transaction phases, immutable data, idempotency, and an outbox when business requirements demand it.

### Official References

- [Spring Framework 6.2 — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html) — `ApplicationEventPublisher`, `@EventListener`, payload events, and dispatching.
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html) — `@TransactionalEventListener` and `AFTER_COMMIT`.
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html) — publication contract.
- [Spring Data JPA Reference — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/jpa/reference/repositories/core-domain-events.html) — `@DomainEvents` and events from aggregates.
