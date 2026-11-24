# Avoiding Passing Managed Entities in Spring Application Events Payloads

## 1. Lesson Objectives

In the **Payload Design** topic of **Spring Framework Application Events**, a common anti-pattern is passing a JPA/Hibernate entity directly while it is managed by a persistence context:

```java
applicationEventPublisher.publishEvent(
    new OrderPlacedWithEntity(orderEntity)
);
```

The snippet above is **illustrative code**, assuming `orderEntity` belongs to an open JPA transaction. At the Java level, the event receiver holds the exact same object reference rather than an immutable copy. At the JPA level, that object is also subject to dirty checking, lazy loading, `EntityManager` lifecycle, and transactions. When switching a design from synchronous listeners to post-commit or async listeners, previous assumptions may no longer hold.

**Design principle:** a domain event must record **a business fact at the time it occurred**; the payload should consist of IDs and **necessary immutable value objects/DTOs**, without managed entities or Hibernate proxies. If a consumer genuinely needs the latest DB state, it can query by ID inside an appropriate transaction.

After this lesson, you should know how to:
1. Distinguish managed/detached entities from immutable events.
2. Recognize bugs involving shared mutable references, lazy associations, dirty checking, and concurrency.
3. Choose between **ID-only, immutable snapshot, or ID + snapshot** payload strategies.
4. Use `@EventListener` and `@TransactionalEventListener(AFTER_COMMIT)` with clear transaction boundaries.
5. Test rollback, async execution, serialization, retries, and historical data.

## 2. What Is a Managed Entity?

A JPA **persistence context** tracks a set of currently managed entities. For example, the result of `EntityManager.find(OrderEntity.class, id)` inside an appropriate context is typically a managed instance. Entities can also be loaded from a repository within a `@Transactional` service.

Key characteristics include:

- **Identity map:** the same persistence identity within a persistence context normally maps to the same Java entity instance.
- **Dirty checking:** if a persistent property of a managed entity changes, the JPA provider can detect and synchronize it during `flush()`/commit without needing to call `save()` after every setter.
- **Lazy associations:** a `LAZY` relationship can be an unloaded proxy/collection; accessing it may require an active session to execute queries.
- **Lifecycle:** when the context closes, clears, or detaches, the entity becomes detached. Already-loaded fields remain Java data, but uninitialized lazy associations may no longer be able to load.
- **Transaction coupling:** managed state, flushing, and rollback are tied to a specific transaction boundary rather than the event itself.

Example JPA entity:

```java
@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private Long id;

    @Column(nullable = false)
    private String status;

    @OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
    private List<OrderLineEntity> lines = new ArrayList<>();

    // Constructors, getters, and business methods are omitted.
}
```

The snippet above **does not compile standalone**; it requires `jakarta.persistence.*`, `java.util.*`, the `OrderLineEntity` class, and JPA configuration. It illustrates that an entity holds **mutable state** and lazy relationships. Simply annotating a class with `@Entity` does not automatically make it managed: it must be attached to an actual persistence context.

### Managed ≠ Snapshot

An event may be retained in memory or processed later than when it was published:

```text
Transaction open
    |
    +--> OrderEntity managed, amount=12500
    |
    +--> publishEvent(new OrderPlacedWithEntity(order))
    |        |
    |        +--> Listener holds reference to same object
    |
    +--> Entity is mutated further, amount=19900
    |
    +--> Flush/commit/rollback; context cleanup
             |
             +--> Listener reads the object or lazy proxy again
```

The value read at the end may **differ** from the value when the event was created. If the listener holds the managed object and modifies it, the listener can also trigger unintended UPDATEs. Domain events are meant to record what happened, not grant mutation access to the aggregate via a live reference.

## 3. Specific Risks of Passing Managed Entities

| Issue | Why It Happens | Consequence |
| --- | --- | --- |
| Mutable reference | Event holds the same object instance | Consumer reads values no longer matching publication time |
| Dirty checking | Listener alters a field on a managed entity | An UPDATE gets flushed in the same transaction unintended by the publisher |
| Lazy loading | Consumer accesses an uninitialized relation outside the right context | `LazyInitializationException` or unexpected queries |
| Transaction lifecycle | Listener runs before, during, or after commit | Behavior depends on timing/rollback |
| Not thread-safe | JPA `EntityManager`/Hibernate Session is not safe to share arbitrarily across threads | Race conditions and invalid access |
| Oversized object graph | Bidirectional relations, cascading, lazy proxies | N+1 queries, infinite recursion, performance, memory, serialization failures |
| Architectural coupling | Consumer knows too much about entity mappings | Persistence model changes force event handler changes |
| Poor replayability | Current entity differs from historical data | Recovery/retries may process wrong information |
| Excessive data | Entity contains PII/internal fields | Unnecessary data leaks in logs or when sent to brokers |

A synchronous listener might run smoothly with an entity today, yet that is **no proof the payload is safe**. Changing multicaster configuration, executors, transaction lifecycles, or adding more listeners can expose hidden dependencies.

### 3.1. Listener Accidentally Mutates the Transaction

```java
@EventListener
public void on(OrderPlacedWithEntity event) {
    event.order().setInternalNote("audited");
}
```

This is an illustrative anti-pattern, assuming the entity is managed in the same transaction and `internalNote` is JPA-mapped. The setter call can be dirty-checked and persisted on flush. A consumer meant merely to "listen to an event" has interfered with aggregate state.

Good domain design controls aggregate mutations through **explicit business methods and transactions**, never letting listeners accidentally mutate source entities by grabbing references from payloads.

### 3.2. A Record Wrapping an Entity Does Not Make the Entity Immutable

```java
public record UnsafeOrderPlaced(OrderEntity order) {}
```

`record` only prevents reassigning the component reference via a setter on the record; it **does not deep-copy** the referenced object. If `order` is mutable, the event still holds mutable data. Likewise, `record Event(List<OrderLineEntity> lines)` is unsafe if the `List` or its elements are mutable.

### 3.3. Lazy Loading After Transaction

If a listener reads `event.order().getLines()` after the persistence context closes, Hibernate may fail to load the lazy relation and throw `LazyInitializationException`. However, **using `AFTER_COMMIT` does not guarantee it will always throw**: some contexts/resources might remain bound until cleanup, or the collection might already have been loaded. Precisely because behavior depends on runtime conditions, passing entities as an event API is unreliable.

### 3.4. Async or Background Threads

`@Async`/executors do not automatically propagate `EntityManager` and transactions from the publisher to another thread. Although the object reference reaches the other thread, a JPA session is not a thread-safe resource for arbitrary concurrent use; the object may be detached or concurrently modified on the source thread. Never treat an entity passed across an executor as an immutable payload.

### 3.5. Serialization and Object Graphs

If an event is sent to JSON/outbox/broker, serializing an entity can trigger lazy getters, follow bidirectional associations infinitely, pull in huge data graphs, or expose PII. Jackson annotations can hide certain fields, yet **do not change the entity's nature as a persistence model**. Integration events need dedicated schema/value DTOs and explicit versioning.

## 4. Designing Immutable Event Payloads

Example of a suitable domain event:

```java
public record OrderPlaced(
    String eventId,
    Long orderId,
    long totalCents,
    String currency
) {}
```

This is a **standalone Java 17+ record**; it imports neither Spring nor Hibernate. Meaning:
- `eventId`: identifies **one business occurrence**. When retrying that same event, keep the same ID so consumers can deduplicate.
- `orderId`: identity of the aggregate the event refers to.
- `totalCents`: **snapshot** of the amount when the order was placed. Use an integer in minor units to avoid `double` rounding errors.
- `currency`: currency unit of the snapshot.

If timestamps or versions are needed, add `occurredAt: Instant`, `aggregateVersion`, `schemaVersion`, `correlationId` per specific requirements. Never put the entire `OrderEntity`, `EntityManager`, or Hibernate collections into the event.

### 4.1. Collections Need Defensive Copying

Records are **shallowly immutable**. For collections, copy to the appropriate depth:

```java
public record OrderPlacedWithItems(
    Long orderId,
    List<String> productCodes
) {
    public OrderPlacedWithItems {
        productCodes = List.copyOf(productCodes);
    }
}
```

This compiles when importing `java.util.List`. `List.copyOf` creates an unmodifiable collection and rejects null elements. Because `String` is also immutable, consumers cannot mutate the snapshot through the stored `List`. If elements are mutable objects, use immutable value objects or deep copying; copying only the container is not enough.

For `byte[]`, `Date`, or other arrays, make defensive copies on receipt and return; prefer `Instant` and immutable value objects where applicable.

### 4.2. Capture at the Right Domain Moment

An immutable payload can still be **semantically wrong** if captured before business rules finish executing. For example, an order still calculating discounts is not yet a placed order. Publish `OrderPlaced` after the aggregate validates invariants and finalizes the total, not merely after an arbitrary SQL statement.

Do not generate a new `eventId` each time an old event is redelivered; one occurrence of a domain fact must preserve a stable identity across retries.

## 5. ID-Only, Snapshot, or Combined Payloads?

| Style | Example | When to Use | Trade-offs |
| --- | --- | --- | --- |
| **ID-only** | `OrderPlaced(eventId, orderId)` | Consumer wants to read **current state** or only invalidate a cache | Must query; read state may be newer than publication time or object may be deleted |
| **Snapshot** | `OrderPlaced(eventId, orderId, amount, currency)` | Consumer needs historical facts at order placement time | Must ensure snapshot accuracy and maintain schema |
| **ID + minimal snapshot** | `OrderPlaced(eventId, orderId, totalCents)` | Consumer needs certain fixed facts and occasionally needs to query more | Must document which fields are historical and which are queried |

Suppose the total at order placement was **12,500 cents**, and later the source data is updated to **19,900 cents**. A listener generating a receipt at purchase time must use `totalCents=12500` from the event; if it re-queries the current entity, it could fetch 19,900 and issue an incorrect receipt.

Conversely, a listener invalidating an order-status cache only needs `orderId`. Passing a full entity just to read its ID is wasteful. For workflows needing the **latest state**, re-querying after commit in a separate transaction is reasonable, provided **eventual consistency** and version conflicts are accepted or handled.

### 5.1. Database-Generated IDs

When using `@GeneratedValue`, understand when the ID is actually assigned under the chosen strategy; not all cases have an ID prior to persist/flush. Build the payload once required IDs exist, or generate domain identifiers in the application before persistence. Avoid blindly flushing just to obtain an ID while ignoring performance and SQL timing impacts.

If the payload needs an exact `@Version`, note that the version value may increment at flush time. Verify in integration tests and pick a clear snapshot point; never guess that the new version is already populated immediately after a setter.

## 6. Runnable Java 17+ Program: Mutable Reference Bug

This is a standalone Spring Context program demonstrating the bug of **holding the same reference to a mutable object**. It **does not configure JPA**: `OrderEntity` in the example is a POJO simulating mutable behavior; thus the example does not demonstrate dirty checking or lazy loading. Real JPA usage is covered via integration patterns in the next section.

Structure:

```text
entity-event-payload-demo/
├── build.gradle
└── src/main/java/demo/EntityPayloadDemo.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.EntityPayloadDemo'
}
```

`src/main/java/demo/EntityPayloadDemo.java`:

```java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EntityPayloadDemo {

    // Mutable POJO simulating part of JPA entity behavior.
    public static final class OrderEntity {
        private final String id;
        private long totalCents;

        public OrderEntity(String id, long totalCents) {
            this.id = id;
            this.totalCents = totalCents;
        }

        public String id() {
            return id;
        }

        public long totalCents() {
            return totalCents;
        }

        public void changeTotal(long newTotalCents) {
            this.totalCents = newTotalCents;
        }
    }

    public record UnsafeOrderPlaced(OrderEntity order) {}

    public record OrderPlaced(
            String eventId,
            String orderId,
            long totalCents
    ) {}

    public static final class UnsafeConsumer {
        private OrderEntity savedReference;

        @EventListener
        public void on(UnsafeOrderPlaced event) {
            savedReference = event.order();
        }

        public String readLater() {
            return "UNSAFE later totalCents="
                    + savedReference.totalCents();
        }
    }

    public static final class SafeConsumer {
        private OrderPlaced savedSnapshot;

        @EventListener
        public void on(OrderPlaced event) {
            savedSnapshot = event;
        }

        public String readLater() {
            return "SAFE snapshot totalCents="
                    + savedSnapshot.totalCents();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public UnsafeConsumer unsafeConsumer() {
            return new UnsafeConsumer();
        }

        @Bean
        public SafeConsumer safeConsumer() {
            return new SafeConsumer();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            OrderEntity order = new OrderEntity("ORD-42", 12_500);
            context.publishEvent(new UnsafeOrderPlaced(order));
            context.publishEvent(new OrderPlaced(
                "EVT-42", order.id(), order.totalCents()
            ));

            // After publishing, the original object is mutated.
            order.changeTotal(19_900);

            System.out.println(
                context.getBean(UnsafeConsumer.class).readLater()
            );
            System.out.println(
                context.getBean(SafeConsumer.class).readLater()
            );
        }
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle run --quiet
```

**Business stdout:**

```text
UNSAFE later totalCents=19900
SAFE snapshot totalCents=12500
```

Output explanation:

1. `UnsafeOrderPlaced` holds a reference to `OrderEntity`. `UnsafeConsumer` stores that reference, so when reading **after** `order.changeTotal(19900)`, it sees 19,900.
2. `OrderPlaced` receives the ID/total values **copied** when the record was created. `SafeConsumer` sees 12,500 regardless of later mutations to the original entity.
3. Both listeners receive events synchronously in the same Spring context; the bug happens simply by **retaining the reference to read later**, without even needing an async thread.
4. In a real JPA application, a synchronous listener could also mutate the managed entity and cause the provider to flush changes. The simulated program does not do that because there is no `EntityManager`.

For unit tests, you can also assert that `UnsafeConsumer.readLater()` changes with the source object while `SafeConsumer.readLater()` keeps the snapshot. Never use a singleton retaining events indefinitely in production; here listeners store a single reference solely to illustrate the difference.

## 7. Real JPA Pattern: Publishing Events from an Application Service

### 7.1. Anti-Pattern Inside a Transaction

```java
@Transactional
public void placeOrder(Long id) {
    OrderEntity order = orderRepository.findById(id)
        .orElseThrow();

    order.place();
    publisher.publishEvent(new OrderPlacedWithEntity(order));
}
```

This is an integration snippet, not a standalone Java file: it requires a JPA entity, repository, event, Spring service, `@Transactional`, and a transaction manager. `order` is normally a managed entity in the transaction. Regular listeners can inspect and mutate the object **before commit**.

### 7.2. Passing an Immutable DTO Instead of an Entity

```java
public record OrderPlacedEvent(
    String eventId,
    Long orderId,
    long totalCents
) {}

@Service
public class PlaceOrderService {

    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    public PlaceOrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void place(Long id) {
        OrderEntity order = repository.findById(id).orElseThrow();
        order.place();

        publisher.publishEvent(new OrderPlacedEvent(
            java.util.UUID.randomUUID().toString(),
            order.getId(),
            order.getTotalCents()
        ));
    }
}
```

This is an **integration pattern**, assuming `OrderRepository`, `OrderEntity`, corresponding Spring/JPA imports, and Spring-managed beans. It does not let the entity escape the service; the publisher sends only the ID and total snapshot. `OrderPlacedEvent` is a pure data record.

**Warning:** the event is published **before the transaction finishes**. If a normal listener triggers side effects outside the DB, those side effects will not roll back with the transaction. An immutable payload solves object coupling, **not commit timing**. Handle phases or persist to an outbox as business rules require.

If the domain accumulates pending events inside an aggregate, the application service can translate those domain events into application payloads or outbox records. Avoid injecting `ApplicationEventPublisher` into an aggregate just to emit a managed entity.

## 8. Transaction Boundaries of Listeners

### 8.1. Regular Listeners Run at Dispatch Time

With the default synchronous `SimpleApplicationEventMulticaster`, `@EventListener` receives the event during the `publishEvent(...)` call, typically on the same thread and within the active transaction if the publisher was invoked inside a `@Transactional` method.

Consequences:
- Can observe uncommitted state.
- Can access lazy relations under certain conditions.
- If given a managed entity, can trigger dirty checking.
- An error in a listener may propagate to the publisher, affecting the transaction flow depending on error-handler configuration.

Therefore, never conclude a payload contract is sound merely because "currently the listener can read the entity".

### 8.2. Post-Commit Listeners

When business requirements demand that work only occur after commit:

```java
@Component
public class OrderNotificationListener {

    private final NotificationGateway notifications;

    public OrderNotificationListener(
            NotificationGateway notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderPlaced(OrderPlacedEvent event) {
        notifications.confirm(
            event.orderId(),
            event.totalCents()
        );
    }
}
```

This pattern requires a `NotificationGateway` bean and Spring imports. The listener **uses only the DTO**. `@TransactionalEventListener` defaults to `AFTER_COMMIT`; if no suitable transaction is active, it **does not run by default** (`fallbackExecution=false`).

**Important:** `AFTER_COMMIT` indicates the originating DB transaction committed; it does **not** automatically guarantee the notification was sent, the broker persisted the message, or an HTTP request succeeded. If the callback fails, the already-committed original transaction cannot be rolled back.

### 8.3. Reading the DB After Commit: Use a New Transaction When Needed

If the event carries only an ID and the consumer needs current data, organize the query into a separate Spring service:

```java
@Service
public class OrderSnapshotReader {

    private final OrderRepository orders;

    public OrderSnapshotReader(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(
        readOnly = true,
        propagation = Propagation.REQUIRES_NEW
    )
    public OrderSummary read(Long id) {
        OrderEntity order = orders.findById(id).orElseThrow();
        return new OrderSummary(
            order.getId(),
            order.getStatus(),
            order.getTotalCents()
        );
    }
}

public record OrderSummary(
    Long id,
    String status,
    long totalCents
) {}
```

This is an integration pattern, not a standalone file; it requires matching repositories/entities/imports. The `AFTER_COMMIT` listener invokes `OrderSnapshotReader` **through a Spring proxy** so the new transaction takes effect. Because old transaction resources may still be bound during part of the after-completion callback, `REQUIRES_NEW` ensures the post-commit DB operation gets an independent transaction. Self-invocation within the same bean can bypass proxy advice and fail to open a new transaction.

Distinguish **two business questions**: `OrderPlacedEvent.totalCents()` answers "what was the price at order placement?", while `OrderSnapshotReader.read(id)` answers "what is the price stored at read time?". If data changed between those moments, seeing two different numbers is expected.

## 9. Async, Lazy Loading, and Serialization

### 9.1. Async Does Not Inherit Transaction Context

`@Async` or executor tasks may run after the original transaction closes. The entity remains a Java object, yet does not automatically carry the matching `EntityManager` across threads. Sharing a session or concurrent entity state is unsafe; specifically, lazy proxies can depend on a Session not owned by this thread.

Solution: pass immutable DTOs; if database access is needed, have the handler query by ID inside its own appropriate transaction. If processing is critical, use a managed queue/worker with retries and observability. Switching from sync to async does not inherently provide reliability.

### 9.2. Do Not Rely on Open Session in View

Open EntityManager in View (OSIV) may keep the persistence context open until the end of a web request in some configurations. It **does not** promise that background jobs or async events will have a corresponding session, and it is not a fix for turning managed entities into safe event payloads. Lazy relations should be handled intentionally via proper queries/fetches or snapshots within the required transaction.

### 9.3. JSON / Integration Events

Never serialize entities directly for partners or brokers: it can cause unexpected queries, circular relationship loops, proxy-specific types, PII leaks, and schemas tightly bound to database mappings. Define dedicated integration event DTOs with explicitly allowed public fields, versioning, serialization tests, and data-protection policies. Event snapshots must suffice for consumers needing history; ID-only may fit consumers needing current data.

## 10. When Side Effects Must Be Durable: Transactional Outbox

Spring's `ApplicationEventPublisher` is a dispatch mechanism **within a single application context**, not a durable message broker. `@TransactionalEventListener(AFTER_COMMIT)` selects the phase, yet still leaves a gap if the process crashes after the DB commit before the callback finishes sending.

When an event must reliably reach external consumers:

```text
Within the same DB transaction:
  1. Aggregate transitions to a valid business state.
  2. Create immutable OrderPlacedEvent (without JPA entity).
  3. INSERT outbox(eventId, aggregateId, type, payloadJson, version).
  4. COMMIT aggregate + outbox atomically.

Outbox publisher/worker:
  5. Read unsent records.
  6. Publish integration DTO to broker.
  7. Record outcome or retry/backoff.

Consumer:
  8. Deduplicate based on eventId.
  9. Process idempotently within an appropriate transaction.
```

If the transaction rolls back, the outbox rolls back too. If it commits, the intent to publish is persisted and can be retried after a restart. However, the worker could publish successfully and crash before marking the record sent, leading to **at-least-once delivery**; consumers still require idempotency. Do not treat an outbox as end-to-end exactly-once by default.

Never serialize an entity object into an outbox hoping to restore it as a managed instance. An outbox stores payloads independent of any JPA persistence context.

## 11. Event ID, Snapshot, Version, and Consistency

An `OrderPlaced` event should have a stable `eventId` for that occurrence. If the record is retried 3 times, use the **same `eventId`** so consumers detect duplicates. `orderId` identifies the aggregate and does not distinguish multiple events on the same order.

For aggregates undergoing consecutive changes, `aggregateVersion` or a sequence may be needed to detect out-of-order arrivals. With JPA `@Version`, however, the version number may increment at flush time: do not assume reading it immediately before flush yields the new version. For consumers needing history, snapshots preserve facts at occurrence time; consumers needing the latest state must accept eventual consistency or use ordering/optimistic locking mechanisms.

An immutable event is only safe when its **semantics** are also clear. For instance, a snapshot of the total at order placement differs from the current DB value; confusing them causes business bugs even when the code compiles cleanly.

## 12. Essential Tests

| Scenario | How to Test | Expected Result |
| --- | --- | --- |
| Mutable reference | Publish an event containing an object, then mutate the source object | Prove the bad event reads the new value; the snapshot DTO keeps the original value |
| Domain invariant | An operation fails before transitioning state | No bogus domain event is created |
| Dirty checking | Integration test with a JPA managed entity and a listener mutating a field | Verify the risk of unintended changes being flushed; proper code does not pass entities |
| Lazy association | Close persistence context, then access an unloaded collection | The bad case can throw `LazyInitializationException`; DTOs have no such dependency |
| Commit | Publish inside a transaction and genuinely commit | `AFTER_COMMIT` listener handles the event properly |
| Rollback | Publish inside a transaction and roll back | No `AFTER_COMMIT` side effects occur |
| Async | Offload consumer to an executor | Needs no publisher session/transaction; receives only DTO |
| Serialization | Serialize event via a real serializer | No proxies/entities; accurate schema, no PII leaks |
| Retry | Replay the same `eventId` | Consumer does not repeat invalid side effects |
| Historical snapshot | Mutate entity after event creation time | History consumer uses snapshot data, not the new state |
| Outbox | Commit and roll back both aggregate and outbox | No outbox row on rollback; record present on commit |

Integration tests using Spring Test's `@Transactional` often auto-rollback at the end of the test, preventing `AFTER_COMMIT` from firing. To test commits, use `TransactionTemplate` or the test framework's transaction completion options, then assert DB state and callback counts. Mocking `publishEvent` alone does not verify transactions or lazy lifecycles.

### Static Review

Whenever you spot an event with a field typed as `OrderEntity`, `CustomerEntity`, `HibernateProxy`, `PersistentCollection`, or a whole mutable aggregate, ask: does the consumer truly need that object? If only an ID or a few facts are needed, switch to a DTO. Domain-defined immutable value objects are not JPA entities and are usually suitable event components.

## 13. Common Pitfalls

1. **Using `record Event(OrderEntity entity)` and calling it immutable**: records are only shallowly immutable.
2. **Letting listeners arbitrarily modify managed entities**: dirty checking can persist unintended DB writes.
3. **Believing entities can always be lazy-loaded**: depends on session/context and loaded data.
4. **Passing entities to `@Async` threads**: transactions/sessions do not follow automatically.
5. **Enabling OSIV to silence `LazyInitializationException`**: does not fix the event payload contract.
6. **Serializing entire entities**: graphs and proxies fail and risk leaking data.
7. **Sending ID-only when consumers need historical facts**: re-querying may read state newer than the event.
8. **Taking snapshots before business rules finalize price/state**: payload is immutable yet semantically wrong.
9. **Assuming `@EventListener` runs after commit**: regular listeners can run before DB commit.
10. **Treating `@TransactionalEventListener` as a durable queue**: post-commit callbacks can be lost on crashes.
11. **Writing to DB in after-commit without a new transaction**: old resources do not automatically start a new commit.
12. **Republishing events with a new `eventId`**: breaks deduplication.
13. **Using entity mappings as public event schemas**: database changes break external consumers.

## 14. Implementation Checklist

- [ ] Does the domain event express a business fact rather than just "entity saved"?
- [ ] Is the payload **free of** JPA managed entities, lazy proxies, Hibernate Sessions, or persistence contexts?
- [ ] Does it carry an ID and minimal immutable snapshot matching historical vs. current-state needs?
- [ ] Are records/lists/value objects defensively copied to the proper depth?
- [ ] Are generated IDs ready and `eventId` stable across retries?
- [ ] Is the snapshot captured **after** business decisions are finalized?
- [ ] Is there a clear distinction between in-transaction `@EventListener` and post-commit `@TransactionalEventListener`?
- [ ] If a post-commit listener reads/writes the DB, does it use a separate transaction when needed?
- [ ] Are async consumers independent of the publisher's thread/session?
- [ ] Does the payload have a schema/version without leaking PII or bloated object graphs?
- [ ] If events must never be lost, is there an outbox/durable messaging and idempotency?
- [ ] Do tests cover rollback, lazy loading, serialization, retries, and mutable references?

**Conclusion:** a managed entity is a live object within a persistence/transaction lifecycle; a domain event is a **fact** that must retain its meaning across time and consumers. Avoid passing managed entities directly in Spring event payloads. Pass **IDs alongside an appropriate immutable snapshot**, re-query within an explicit transaction when the latest state is needed, and use an outbox when events must be delivered durably.

## References

- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring 6.1 API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring 6.1 API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Jakarta Persistence 3.1 specification](https://jakarta.ee/specifications/persistence/3.1/)
- [Hibernate ORM 6.4 User Guide](https://docs.jboss.org/hibernate/orm/6.4/userguide/html_single/Hibernate_User_Guide.html)
