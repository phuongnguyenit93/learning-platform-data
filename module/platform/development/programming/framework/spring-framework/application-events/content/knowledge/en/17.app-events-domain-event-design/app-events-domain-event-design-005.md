# Aggregates and Domain Events in Spring Application Events

## 1. The problem: business state changes and announcing what happened

Suppose an e-commerce system handles orders. When payment succeeds, the order status transitions from `PENDING` to `PAID`; other features need to know so they can update reports, send notifications, or trigger fulfillment. If all of those actions are placed inside the payment method itself, the codebase quickly becomes tightly coupled to email, inventory, shipping, and many other services.

An **Aggregate** in Domain-Driven Design (DDD) defines the boundary responsible for protecting business rules. A **domain event** expresses an occurrence meaningful to the business, typically a fact that happened inside an aggregate, such as `OrderPaid`. Spring's `ApplicationEventPublisher` provides a mechanism to deliver that notification to interested components **within the application**.

Three concepts have distinct roles:

1. **Aggregate:** decides whether an action is valid and updates state according to business *invariants*.
2. **Domain event:** records the business outcome achieved, without commanding recipients to execute a specific instruction.
3. **Application event mechanism:** delivers the event object to listeners; this is Spring's technical mechanism and does not by itself provide transactions, durable queues, or delivery guarantees.

For example, `Order.pay()` verifies the order is unpaid, updates its status, and records `OrderPaid`. An application service saves the aggregate and uses Spring to publish the event. Another listener handles notifications without having to modify `Order.pay()` every time a new side effect is added.

## 2. What is an aggregate and why does it have a boundary?

In DDD, an aggregate is a **cluster of entities and value objects managed as a single consistency unit**; one entity in the cluster acts as the **aggregate root**. External components interact with the aggregate through its root rather than mutating internal details directly.

For example, an `Order` aggregate might contain:

- `Order` (root): order ID, status, total amount, and operations `addItem()`, `confirm()`, `pay()`, `cancel()`.
- `OrderLine`: order line items attached to the order; quantity changes must go through the root to maintain the total amount and validity rules.
- `Money`, `Address`: value objects representing values, preferably immutable.

Typical **invariants**: a cancelled order cannot be paid; do not record two payments for the same state transition; total amount is non-negative; unpaid orders cannot be shipped (depending on business rules).

### Consistency boundary

Ordinarily, rules that must hold immediately when an operation finishes are checked **within one aggregate**. Other aggregates such as `Inventory`, `Shipment`, or `CustomerLoyalty` can react to domain events and achieve consistency afterward. Do not assume every aggregate must belong to a single transaction.

Key point: **an aggregate is not synonymous with a database row**, nor is it all entities in a bounded context. An aggregate may span multiple tables; the boundary size is chosen based on invariants, write contention, and consistency needs.

## 3. What should a domain event describe?

A good domain event expresses a **fact in the past**, named in the business language:

| Message type | Example | Meaning |
| --- | --- | --- |
| Command | `PayOrder` | Requests an action; may be rejected |
| Domain event | `OrderPaid` | The order has been confirmed as paid under business rules |
| Domain event | `OrderCancelled` | The order has been cancelled |
| Integration event | `order.paid.v1` | Message published to external systems with its own schema and delivery contract |

An event usually carries only **the data recipients need to understand the occurrence**: `eventId` for duplicate detection, `aggregateId`, transaction or business IDs, timestamp, version, or immutable values. Copying the entire entity is not necessary.

Java 17+ example:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        String orderId,
        long amountCents,
        Instant occurredAt) {
}
```

This is an **illustrative data definition**, not a standalone program. Java `record` fixes fields at a shallow level (*shallow immutability*); if a record holds a `List` or mutable object, make defensive copies when needed. When creating an actual event, supply data right when business rules confirm it, without requiring listeners to access mutable entities or lazy-loading proxies.

**A domain event is not required to extend `ApplicationEvent`.** Spring allows `publishEvent(Object)` to accept POJOs/records; when needed, Spring wraps them internally. Avoid putting Spring annotations or APIs into every domain class if you can keep the domain in plain Java.

## 4. Who creates and who publishes domain events?

A common organization by boundary:

```text
HTTP/API/Job
    |
    v
Application Service: PayOrder
    |
    v
Repository.load(orderId)
    |
    v
Order Aggregate Root
  - check invariants
  - transition PENDING -> PAID
  - record OrderPaid
    |
    v
Repository.save(order)
    |
    v
Publish recorded events
    |
    v
Spring ApplicationEventPublisher
    |
    +--> Listener updates projection
    +--> Listener creates notification request
    +--> Adapter prepares integration/outbox
```

**Aggregate's responsibility:** detect and describe valid state changes. The aggregate does not need to know specific listeners and should not call an email client, HTTP API, or Spring's `ApplicationEventPublisher` directly inside domain methods.

**Application service / infrastructure responsibility:** load the aggregate, establish a transaction when a DB is used, persist changes, and coordinate publication. With Spring Data, repository infrastructure can also extract domain events from the aggregate root to publish them.

**Listener's responsibility:** execute separate side effects or projections, managing errors and duplicates. Listeners should not arbitrarily re-mutate the source aggregate's invariants via a directly passed entity object.

Simply flipping `order.paid = true` and manually publishing an event without going through an invariant-enforcing method is a design smell to fix: outside code can already bypass the aggregate boundary.

## 5. Runnable example: plain Java aggregate + Spring ApplicationEventPublisher

This example uses **Spring Boot 3.x, Java 17+**, with no DB connection so domain boundaries and execution order can be observed clearly. The in-memory repository only simulates persistence; it **does not provide transactions, write locks, or durability**.

Business requirements:

- An unpaid order with a positive total can transition to `PAID`.
- A second payment attempt does not create another `OrderPaid`.
- The aggregate records the event; the service saves and publishes; the listener only prints a notice.
- Fixed output pattern to verify the event appears only once.

### File structure

```text
aggregate-domain-event-demo/
├── pom.xml
└── src/main/java/example/events/AggregateEventDemo.java
```

### pom.xml

The example pins Spring Boot 3.3.13 and JDK 17:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>aggregate-domain-event-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### AggregateEventDemo.java

```java
package example.events;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class AggregateEventDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(AggregateEventDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);

        try (ConfigurableApplicationContext context = app.run(args)) {
            // Runner executed during startup; context closes upon exiting try.
        }
    }

    // Immutable business message; no need to extend ApplicationEvent.
    public record OrderPaid(String orderId, long amountCents) {
    }

    // Plain Java aggregate root: only the root decides whether payment is allowed.
    public static final class Order {
        private final String id;
        private final long amountCents;
        private boolean paid;
        private final List<Object> pendingEvents = new ArrayList<>();

        public Order(String id, long amountCents) {
            if (id == null || id.isBlank() || amountCents <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            this.id = id;
            this.amountCents = amountCents;
        }

        public String id() {
            return id;
        }

        public boolean pay() {
            if (paid) {
                return false; // Repeated operation does not emit a second event.
            }
            paid = true;
            pendingEvents.add(new OrderPaid(id, amountCents));
            return true;
        }

        public List<Object> drainEvents() {
            List<Object> result = List.copyOf(pendingEvents);
            pendingEvents.clear();
            return result;
        }
    }

    // Persistence illustration only; not equivalent to JPA/database.
    public static final class InMemoryOrderRepository {
        private final Map<String, Order> orders = new ConcurrentHashMap<>();

        public void save(Order order) {
            orders.put(order.id(), order);
        }

        public Order getRequired(String id) {
            Order order = orders.get(id);
            if (order == null) {
                throw new IllegalArgumentException("Order not found: " + id);
            }
            return order;
        }
    }

    // Application service knows the repository and Spring publisher;
    // the domain aggregate has no framework dependency.
    public static final class PayOrderService {
        private final InMemoryOrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public PayOrderService(InMemoryOrderRepository repository,
                               ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public boolean pay(String id) {
            Order order = repository.getRequired(id);
            if (!order.pay()) {
                return false;
            }
            repository.save(order);
            for (Object event : order.drainEvents()) {
                publisher.publishEvent(event);
            }
            return true;
        }
    }

    public static final class OrderPaidListener {
        @EventListener
        public void on(OrderPaid event) {
            System.out.printf("EVENT order=%s amount=%d%n",
                    event.orderId(), event.amountCents());
        }
    }

    @Bean
    InMemoryOrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }

    @Bean
    PayOrderService payOrderService(
            InMemoryOrderRepository repository,
            ApplicationEventPublisher publisher) {
        return new PayOrderService(repository, publisher);
    }

    @Bean
    OrderPaidListener orderPaidListener() {
        return new OrderPaidListener();
    }

    @Bean
    CommandLineRunner demo(InMemoryOrderRepository repository,
                           PayOrderService service) {
        return args -> {
            repository.save(new Order("ORD-42", 12500));
            System.out.println("FIRST pay=" + service.pay("ORD-42"));
            System.out.println("SECOND pay=" + service.pay("ORD-42"));
        };
    }
}
```

### Run and observe

In the directory containing `pom.xml`:

```bash
mvn -q package
java -jar target/aggregate-domain-event-demo-1.0.0.jar
```

Aside from Spring Boot's own logs, the three lines **printed by the demo code** are:

```text
EVENT order=ORD-42 amount=12500
FIRST pay=true
SECOND pay=false
```

Why does `EVENT` appear before `FIRST`? By default, Spring uses `SimpleApplicationEventMulticaster` to invoke `@EventListener` synchronously on the `publishEvent(...)` thread. The call `service.pay(...)` does not return to the runner until the listener finishes. The second call sees `paid == true`, so it returns `false` and creates no new event.

**Boundary of the example:** `InMemoryOrderRepository` holds references to `Order` without DB transactions, optimistic locking, concurrency control, rollback, or an outbox. `drainEvents()` removes events from the list right before publishing; if the process dies or a listener throws an error, the event can be lost. Choose a different mechanism when tasks must not be lost.

## 6. Business invariants belong in the aggregate, not in listeners

An error-prone design:

```java
// Anti-pattern: application service mutates state directly,
// leaving a listener to decide whether payment is allowed.
order.setPaid(true);
publisher.publishEvent(new OrderPaid(order.getId(), total));
```

This snippet only illustrates a **flawed design direction**, not part of the demo in section 5. If multiple threads or services can call the setter, the rule "cancelled orders cannot be paid" is bypassed on some paths. A listener is where reactions occur, not the sole barrier protecting source state.

A better approach:

```java
public boolean pay() {
    if (status == Status.CANCELLED) {
        throw new IllegalStateException("Cancelled order cannot be paid");
    }
    if (status == Status.PAID) {
        return false;
    }
    status = Status.PAID;
    registerDomainEvent(new OrderPaid(orderId, amountCents));
    return true;
}
```

This is **Java pseudocode for a domain method**: it assumes `Status`, `orderId`, `amountCents`, and `registerDomainEvent(...)` are defined inside the aggregate. The core flow is **check invariants → update state → record event**. Persistence and publishing are separate steps managed by the service or repository adapter.

An event is usually created **once the business decision takes effect in memory**, yet **the change only becomes durable when the persistence transaction commits successfully**. Therefore, distinguish "the aggregate transitioned state" from "the DB committed" when placing listeners with side effects.

## 7. Spring Data: @DomainEvents and @AfterDomainEventPublication

Spring Data Commons provides a mechanism to publish domain events from an aggregate root through a repository. A root can declare:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

public class OrderAggregate {
    private final List<Object> events = new ArrayList<>();

    public void markPaid(String orderId, long amountCents) {
        // After checking invariants and updating state:
        events.add(new OrderPaid(orderId, amountCents));
    }

    @DomainEvents
    Collection<Object> domainEvents() {
        return List.copyOf(events);
    }

    @AfterDomainEventPublication
    void clearDomainEvents() {
        events.clear();
    }
}
```

This is an **illustrative structural fragment**, not a complete JPA entity and not used directly in the section 5 demo. A `@DomainEvents` method takes no parameters and returns a single event object or collection; after infrastructure publishes the events, the `@AfterDomainEventPublication` method can clear the recorded events.

Spring Data supports extracting events when appropriate repository methods are invoked with a root instance, such as `save(...)`, `saveAll(...)`, and certain forms of `delete(...)`. **Do not assume `deleteById(...)` always publishes domain events**: that method may execute a delete by ID directly without loading the aggregate instance.

Important point: calling `aggregate.markPaid(...)` **does not automatically** publish events merely because `@DomainEvents` is present. You must go through a repository method that supports publication. Similarly, `@AfterDomainEventPublication` only indicates events were handed off to the publication infrastructure—it **does not prove the database committed or that all listeners succeeded**.

### AbstractAggregateRoot reduces boilerplate code

Spring Data Commons also provides `AbstractAggregateRoot<A>`. This class provides a built-in event list and the methods `registerEvent(...)`, `andEvent(...)`, `domainEvents()`, and `clearDomainEvents()`.

```java
import org.springframework.data.domain.AbstractAggregateRoot;

public class OrderEntity extends AbstractAggregateRoot<OrderEntity> {

    public void markPaid(String orderId, long amountCents) {
        // Check invariants and update state here.
        registerEvent(new OrderPaid(orderId, amountCents));
    }
}
```

This is an **illustrative inheritance snippet**, assuming `OrderPaid` is already defined. In a real JPA application, the entity also needs `@Entity`, an `@Id` key, proper mappings, and a repository. You do not need to rewrite `@DomainEvents` / `@AfterDomainEventPublication` when using `AbstractAggregateRoot`'s built-in behavior.

Advantage: less work managing the event list. Trade-off: the domain class depends on Spring Data. If you want the domain completely framework-independent, keep a plain Java event queue and use an adapter/application service to publish as in the earlier example.

## 8. Publication timing, transactions, and AFTER_COMMIT

There are three distinct points:

1. The aggregate creates a domain event when performing a business state transition.
2. The Spring application event is **published** when the application service/repository invokes the publisher.
3. The database transaction **commits** at the end of the unit of work, if a transaction actually exists.

These milestones may not coincide. For instance, an application service with `@Transactional` modifies an aggregate and calls `repository.save(order)`. Spring Data may publish events during the repository call, **before the outer transaction commits**.

If a listener uses the default `@EventListener` and executes side effects immediately (sending email, calling an API), the side effect may happen **before the DB commits**; if the transaction later rolls back, the sent email still happened.

For reactions valid only after commit, Spring Framework supports:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AfterCommitOrderListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPaid(OrderPaid event) {
        // Call a notification/sync adapter after commit.
        // Retries/idempotency are needed if events cannot be lost.
    }
}
```

This is an **illustrative class**, requiring Spring's transaction dependency, an active transaction when the event is published, and the corresponding `OrderPaid` type. Do not drop this directly into the section 5 in-memory demo: that demo **opens no transaction**, so a default `@TransactionalEventListener` will **not be invoked**.

Supported phases: `BEFORE_COMMIT`, `AFTER_COMMIT` (default), `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. If no transaction is active, the listener **ignores the event** by default; `fallbackExecution = true` can be set, provided you accept running without a commit to wait for.

**Warning about DB writes after commit:** At `AFTER_COMMIT`, some transactional resources may still be bound to the thread. If a listener needs to execute a **new DB write transaction**, invoke a separate service annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)` (via a Spring proxy) or use an appropriate `TransactionTemplate`. Simply putting default `@Transactional` on the listener method does not guarantee the write commits in a new transaction.

## 9. Why AFTER_COMMIT is still not a delivery guarantee

`@TransactionalEventListener(AFTER_COMMIT)` prevents firing side effects when a transaction rolls back, but **does not guarantee durability** for events after commit. A process can crash right after the DB commits, before the listener sends an email or dispatches a message. In that case, the order change is saved, yet the event never leaves the process.

For important events that must be delivered reliably, consider the **Transactional Outbox**:

```text
Database transaction:
  UPDATE orders SET status='PAID' WHERE ...
  INSERT INTO outbox(event_id, type, payload, status)
  COMMIT
            |
            v
Worker / CDC reads committed outbox
            |
            v
Message broker / integration adapter
            |
            v
Consumer with idempotency, retry, DLQ
```

When the state-change record and outbox record are saved in **the same transaction**, a successful commit ensures both appear together. A worker publishing afterward can retry on failure. Because of retries, delivery usually requires *at-least-once* thinking: consumers must process idempotently using `eventId` or a sufficiently stable business key.

**Do not confuse:**

- `@EventListener`: in-application dispatch, synchronous by default.
- `@Async @EventListener`: dispatches work via an in-memory executor, not automatically durable.
- `@TransactionalEventListener(AFTER_COMMIT)`: binds callback to the transaction commit phase, does not durably persist events.
- **Outbox + broker/worker:** model for persisting and delivering events that can recover after crashes, at the cost of operational overhead, latency, and duplicate handling.

## 10. Are domain events and integration events the same?

Not necessarily.

A **domain event** describes what happened within the domain model; recipients may reside in the same bounded context. It can carry data convenient for internal processing without being tied to a public network schema.

An **integration event** is a contract between applications/bounded contexts. It typically needs:

- A stable event type name and schema version, e.g., `OrderPaidV1`.
- `eventId`, timestamp, aggregate ID, and data required by the contract.
- Backward-compatibility rules, retries, deduplication, and consumer monitoring.
- Security rules, minimization of personal data, masking or encryption of sensitive fields.

An adapter can translate an internal `OrderPaid` into `order.paid.v1` sent via an outbox. Do not let internal Java object changes force every external consumer to upgrade immediately.

Because an event is a **past fact**, listeners should not assume they can always undo the original business action. If a flow requires reversal, design a separate command and compensating state transition (such as a refund), depending on the domain.

## 11. Common design mistakes

**1. Using domain events to replace aggregate invariants.** For example, a listener checking payment limits after the root already recorded payment. Mandatory immediate rules belong where the business decision is made, usually inside the aggregate or an appropriate domain service.

**2. Publishing events directly inside an entity using ApplicationEventPublisher.** This couples the domain to the Spring container, makes testing harder, and obscures whether the entity was saved successfully. Let the aggregate record events, while an adapter/service manages publishing.

**3. Publishing events as soon as a command arrives.** `OrderPaid` must appear only after business logic confirms the state transitioned, not immediately when a `PayOrder` request arrives.

**4. Ignoring transactions and rollbacks.** Synchronous `@EventListener` methods can run before commit. Use an appropriate phase listener or an outbox if side effects depend on commit.

**5. Treating Spring Data @DomainEvents as automatic durable delivery.** This mechanism publishes events when a repository operates on an aggregate root; it does not replace transaction commits, message brokers, or an outbox.

**6. Duplicate publishing on save or retry.** Avoid re-registering the same event on every `save(...)` if state did not change. Use idempotent commands, preserve event IDs, and handle deduplication when consumers may receive redeliveries.

**7. Passing raw JPA entities to listeners.** This risks lazy-loading errors, stale/mutable state, circular references, or data leaks. Prefer immutable snapshots of needed data or aggregate IDs with clear querying rules.

**8. A listener directly modifying multiple aggregates in an async flow and assuming immediate consistency.** Each step needs its own transaction/coordination, and latency or partial failures can occur; consider workflows/sagas or another consistency model.

**9. Equating "published" with "listener succeeded."** An asynchronous listener can fail after the publisher returns. Track separate metrics for events created, published, processed, failed, retried, and sent to DLQ.

**10. Equating an aggregate with one table or cramming the whole system into one aggregate.** Boundaries that are too small scatter invariants; boundaries that are too large cause contention and complex transactions. Decide based on real consistency requirements.

## 12. Testing aggregates and publication across levels

A solid strategy includes:

### Pure domain unit tests without starting Spring

Test `Order.pay()` itself across cases:

| Case | State outcome | Domain event |
| --- | --- | --- |
| `PENDING` order, positive total | Transitions to `PAID` | Exactly one `OrderPaid` |
| Second `pay()` call | No state change | No new event |
| `CANCELLED` order | Rejected by rule | No `OrderPaid` created |
| Invalid data | Appropriate exception/validation | No event created |

The section 5 example illustrates the first two rows; the `CANCELLED` case requires adding the corresponding state and rule before writing tests. Unit tests should assert payload fields and immutability without booting a Spring container.

### Integration tests with Spring Application Events

Use a real context or `ApplicationEvents` in Spring Boot Test to verify that the application service publishes the right event type, data, and count. When using `@DomainEvents`, actually invoke the Spring Data-supported repository method rather than only calling the domain method.

### Testing transactions, rollbacks, and retries

In integration tests with real DB transactions:

1. Successful commit → `@TransactionalEventListener(AFTER_COMMIT)` is invoked per contract.
2. Transaction rollback → AFTER_COMMIT does not run.
3. No transaction → transactional listener does not run by default.
4. Process crashes after commit before sending → outbox model can recover.
5. An event is delivered again → consumer does not execute side effects twice.

Do not use a test that automatically wraps and rolls back a transaction to conclude that an AFTER_COMMIT callback works; many Spring tests with `@Transactional` roll back by default. Design a test that genuinely commits or use appropriate test transaction utilities.

## 13. Adoption checklist

1. Is the aggregate root the place enforcing invariants that must hold immediately?
2. Are domain events named for **what happened**, with minimal and immutable payloads?
3. Are events **recorded when state validly transitions**, avoiding re-creation on repeated calls?
4. Do application services/repositories clearly separate persistence from event publication?
5. With Spring Data, do you understand which repository methods trigger `@DomainEvents` and the role of `@AfterDomainEventPublication`?
6. Do commit-dependent listeners use the appropriate transaction phase?
7. If events must not be lost, are outbox/retry/idempotency/deduplication in place?
8. Are there tests for plain Java domain logic, integration events, commit/rollback, and reprocessing?
9. Have ordering, concurrency, sensitive data, and bounded context scope been evaluated?

**Conclusion:** The aggregate decides valid state and records domain events; Spring delivers that information to listeners. Publishing internal events, committing data, and reliably delivering messages are three distinct responsibilities. Distinguishing them properly keeps invariants intact and lets behavior expand as business rules evolve.

## References

- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): `@DomainEvents` and `@AfterDomainEventPublication`.
- [Spring Data Commons — AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html): how domain events are registered.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, commit/rollback, and fallback.
