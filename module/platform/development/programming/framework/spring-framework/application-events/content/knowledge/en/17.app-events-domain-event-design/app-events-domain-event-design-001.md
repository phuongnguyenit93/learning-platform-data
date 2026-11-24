# Domain Events in Domain Modeling: Design and Implementation with Spring Framework Application Events

## 1. What is a domain event?

A **domain event** expresses a **significant business fact that has occurred** within the domain: an order has been placed (`OrderPlaced`), a payment has been confirmed (`PaymentConfirmed`), an account has been locked (`AccountLocked`), or a credit limit has changed (`CreditLimitChanged`).

In Domain-Driven Design (DDD), domain events help the model express **what just happened** in language that business stakeholders understand. It is not merely a technical notification. For example, `OrderPlaced` differs from `RowInserted`: "an order has been placed" is a meaningful business state transition, whereas "a row was INSERTed" is merely a persistence detail.

A good domain event answers:
- **What happened?** The event name reflects a completed state.
- **Which objects are involved?** `orderId`, `customerId`, or an aggregate identifier.
- **What information needs to be captured?** Finalized total amount, change type, business version.
- **Which boundary does the event belong to?** Which aggregate/bounded context raised it.
- **How should the system react?** Independent policies or consumers handle the consequences without replacing the aggregate's invariants.

A domain event is a concept **at the domain layer**. Spring's `ApplicationEventPublisher` and `@EventListener` are just one of several **technical mechanisms** for dispatching and handling domain events in a Java application.

## 2. Where do domain events live in a DDD model?

A typical organization:

```text
Client / Controller
        |
Application Service / Use Case
        |
Order Aggregate --------------> OrderPlaced (domain event)
  - enforces invariants                  |
  - transitions DRAFT -> PLACED          |
  - collects pending events              |
        |                                |
Repository.save(order)                   |
        |                                |
Application Service / Unit of Work ------+
        |
        +--> Publish in-process / transaction synchronization
        |        |
        |        +--> Domain policy / handler in the same application
        |
        +--> Transactional outbox (if durable delivery is required)
                 |
                 +--> Worker / broker / integration consumer
```

The **aggregate** is responsible for the correctness of its own business state. When a valid action changes the state, the aggregate **records** the domain event. An outer coordination layer (application service, unit of work, or repository integration) decides **when and by what mechanism** to publish the recorded events.

For example, `Order.place()` must verify that the order is in a state that allows placing; if not, it throws an error, **does not transition state, and does not raise `OrderPlaced`**. The aggregate creating the event reflects a business decision that has been accepted. That alone does not mean the database transaction has ultimately committed.

### Events are the result of behavior, not commands

| Message Type | Example | Semantics |
| --- | --- | --- |
| Command | `PlaceOrder` | Request to perform an action; may be rejected |
| Domain event | `OrderPlaced` | The domain has accepted the "placed" state transition |
| Integration event | `OrderPlacedIntegrationEvent` | Message intended for another system/bounded context, with its own delivery contract |
| Technical event | `EntitySaved` | Technical notification about a persistence operation; not necessarily meaningful to the domain |

Do not name a domain event like a command such as `SendEmailNow`: that is a request for processing, not a business fact. Nor should you raise an event for every minor field change if that change does not constitute a notable event in the domain language.

## 3. Choosing when to create domain events in an aggregate

An aggregate should create the event **after invariants are checked and the state transition is accepted**, inside the same business method:

```java
public void place(String eventId) {
    if (status != OrderStatus.DRAFT) {
        throw new IllegalStateException("Only DRAFT orders can be placed");
    }
    status = OrderStatus.PLACED;
    pendingEvents.add(
        new OrderPlaced(eventId, orderId, totalCents)
    );
}
```

This is an **illustrative snippet** inside the `Order` class; the complete runnable program is in section 6.

Benefits of creating the event at the moment of state transition:
1. Readers clearly see which condition leads to `OrderPlaced`.
2. The event is not raised by an arbitrary getter or SQL statement.
3. The aggregate retains control over its invariants; consumers do not have to guess the prior state.
4. Business logic can be tested in plain Java without a Spring context.

If a command fails before the state transition, no new domain event is recorded. If the DB transaction rolls back after the aggregate records events in memory, **dispatching the events outward** must be coordinated with the transaction outcome to avoid producing invalid side effects.

### Does the domain need to know about Spring?

It is not required, and in a decoupled domain model it usually **should not**. A plain Java aggregate does not need to inject `ApplicationEventPublisher` or invoke `@EventListener`. It simply returns or temporarily holds a list of domain events. The application service can translate them to Spring's mechanism, store them in an outbox, or send them to a message broker without forcing the domain to depend on Spring.

A simple application may choose to publish events directly in the application service. What matters is **separating responsibility boundaries** and explicitly defining the publication timing relative to commit.

## 4. Designing the domain event payload

With Java 17+, `record` is well suited for events that primarily hold immutable data:

```java
public record OrderPlaced(
    String eventId,
    String orderId,
    long totalCents
) {}
```

Example data for an event:
- `eventId = "EVT-42"`: unique identifier for **a single occurrence** of the event. Keep the same ID if retrying delivery of the same event.
- `orderId = "ORD-42"`: aggregate identifier.
- `totalCents = 12500`: total amount at the time the order was placed, represented as an integer in the smallest currency unit to avoid floating-point rounding errors.

In larger systems, an event may contain `occurredAt` (when the domain recorded it), `aggregateVersion`, or correlation/causation IDs. Only include the fields that are needed. Do not put passwords, tokens, sensitive data, or entire JPA entities into the payload.

**Note:** `record` provides shallow immutability: fields referencing a `List`, `Map`, or mutable object can still change internally. Prefer immutable types, primitives, `String`, `Instant`, immutable value objects, or defensive copies (`List.copyOf(...)`) where appropriate. Field names and data types should reflect domain semantics, independent of DB table schemas.

### Should an event always contain all data?

No. There are two approaches to weigh:
- **Event contains the necessary snapshot:** consumers do not need to re-read mutable state; convenient for auditing, replay, and asynchronous processing. The payload is larger and versions must be managed.
- **Event mainly contains IDs:** consumers read data from a repository; the payload is smaller, but you must account for whether data has committed, eventual consistency latency, and the possibility that data changes between when the event occurred and when it is handled.

Do not record "new state" in the event if it can be recomputed and differ from the truth at publication time; nor force every consumer to call back into a mutable aggregate to guess historical data.

## 5. Distinguishing domain events, Spring application events, and integration events

**Domain event:** belongs to the business vocabulary and can exist completely independently of any framework. An `OrderPlaced` record can be a domain event even when no Spring bean is running.

**Spring application event:** is the event-publishing infrastructure **within an `ApplicationContext`**. `ApplicationEventPublisher.publishEvent(event)` passes the event to the multicaster. Since Spring 4.2, an event can be any object; objects that do not extend `ApplicationEvent` are wrapped in `PayloadApplicationEvent`. `@EventListener` can receive payloads using ordinary Java types.

**Integration event:** is a communication contract between systems, typically requiring serializers, schema evolution, event IDs, versioning policies, a broker/outbox, retries, and idempotency. An integration event can be created **from** a domain event after the transaction commits, but it is not implicitly that same Java instance.

| Question | Domain event | Spring application event | Integration event |
| --- | --- | --- | --- |
| Defined by | Domain model | Spring mechanism | Cross-service contract |
| Primary boundary | Aggregate/bounded context | Application context/process | Process/service/network |
| Durability guarantee | Depends on where it is stored | Not durably persisted automatically | Depends on outbox/broker |
| Spring dependency | Not required | Yes | Not required |
| Example | `OrderPlaced` | Publish `OrderPlaced` via Spring | JSON event sent to a broker after commit |

Sharing a single Java type for both domain and integration events is only appropriate after considering contracts/versioning and the scope of coupling. An internal change in an aggregate should not accidentally break consumers in another service.

## 6. Runnable Java 17+ example: plain Java aggregate, Spring only publishes

The small program below uses Spring Context without requiring Spring Boot or a DB. The domain aggregate validates rules itself and stores unpublished domain events. The application service saves the aggregate to an in-memory repository and then publishes events via Spring. Two listeners receive the same payload without depending on each other's ordering.

Structure:

```text
domain-events-demo/
├── build.gradle
└── src/main/java/demo/DomainEventDemo.java
```

Contents of `build.gradle`:

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
    mainClass = 'demo.DomainEventDemo'
}
```

Contents of `src/main/java/demo/DomainEventDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class DomainEventDemo {

    // Domain types: no Spring imports.
    public sealed interface DomainEvent permits OrderPlaced {
        String eventId();
        String aggregateId();
    }

    public record OrderPlaced(
            String eventId,
            String aggregateId,
            long totalCents
    ) implements DomainEvent {}

    public static final class Order {
        private enum State { DRAFT, PLACED }

        private final String orderId;
        private final long totalCents;
        private State state = State.DRAFT;
        private final List<DomainEvent> pendingEvents = new ArrayList<>();

        private Order(String orderId, long totalCents) {
            if (orderId == null || orderId.isBlank() || totalCents <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            this.orderId = orderId;
            this.totalCents = totalCents;
        }

        public static Order draft(String id, long totalCents) {
            return new Order(id, totalCents);
        }

        public void place(String eventId) {
            if (state != State.DRAFT) {
                throw new IllegalStateException("Order already placed");
            }
            if (eventId == null || eventId.isBlank()) {
                throw new IllegalArgumentException("Missing event id");
            }
            state = State.PLACED;
            pendingEvents.add(
                new OrderPlaced(eventId, orderId, totalCents)
            );
        }

        public String id() {
            return orderId;
        }

        public boolean isPlaced() {
            return state == State.PLACED;
        }

        public List<DomainEvent> drainEvents() {
            List<DomainEvent> copy = List.copyOf(pendingEvents);
            pendingEvents.clear();
            return copy;
        }
    }

    // Simulated storage adapter: replace with a real DB/repository in production.
    public static final class InMemoryOrderRepository {
        private final Map<String, Order> orders = new HashMap<>();

        public void save(Order order) {
            orders.put(order.id(), order);
            System.out.println(
                "SAVED " + order.id() + " placed=" + order.isPlaced()
            );
        }
    }

    // Application service decides when to persist and publish events.
    public static final class PlaceOrderUseCase {
        private final InMemoryOrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public PlaceOrderUseCase(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void place(String orderId, long amount, String eventId) {
            Order order = Order.draft(orderId, amount);
            order.place(eventId);
            repository.save(order);
            for (DomainEvent event : order.drainEvents()) {
                publisher.publishEvent(event);
            }
        }
    }

    public static final class AuditListener {
        @EventListener
        public void whenPlaced(OrderPlaced event) {
            System.out.println(
                "AUDIT " + event.eventId() + " " + event.aggregateId()
            );
        }
    }

    public static final class MetricsListener {
        @EventListener
        public void whenPlaced(OrderPlaced event) {
            System.out.println(
                "METRICS " + event.aggregateId()
                    + " totalCents=" + event.totalCents()
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public InMemoryOrderRepository repository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        public PlaceOrderUseCase placeOrderUseCase(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new PlaceOrderUseCase(repository, publisher);
        }

        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }

        @Bean
        public MetricsListener metricsListener() {
            return new MetricsListener();
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            context.getBean(PlaceOrderUseCase.class)
                .place("ORD-42", 12_500L, "EVT-42");
        }
    }
}
```

Run with JDK 17+ and Gradle installed:

```bash
gradle run --quiet
```

**Three expected business output lines** (the two listener lines may appear in either order):

```text
SAVED ORD-42 placed=true
AUDIT EVT-42 ORD-42
METRICS ORD-42 totalCents=12500
```

Explanation:
1. `Order.place(...)` checks the `DRAFT → PLACED` rule, then records `OrderPlaced` in the aggregate's event list. It has no knowledge of Spring.
2. `PlaceOrderUseCase` saves the aggregate before publishing. `drainEvents()` returns an immutable copy of the list and clears pending events to avoid duplicate publication within the demo object's lifecycle.
3. `ApplicationEventPublisher.publishEvent(Object)` accepts `OrderPlaced` even though the record does not extend `ApplicationEvent`. Spring's `@EventListener` automatically selects listeners with a matching parameter type.
4. The audit listener only reads the event ID and aggregate ID; the metrics listener only reads the total amount. They do not rely on each other's side effects.
5. The repository here **stores in RAM**, with no transaction/commit. "`SAVED`" is merely a log from `Map.put`; it does not prove the event was durably persisted or can be rolled back. `drainEvents()` clears pending events, so if the publisher fails afterward, the demo also has no retry mechanism. The production section below addresses this issue.

**What to test in the domain independently of Spring:** create `Order.draft(...)`, call `place(...)`, and assert `isPlaced()` and a single `OrderPlaced` with the right payload. Calling `place(...)` a second time must throw `IllegalStateException` and add no events. There is no need to start an `ApplicationContext` to test invariants.

## 7. Publication timing and transaction boundaries

The in-memory example only illustrates layering. With a real database, "the aggregate transitioned state in RAM" and "the transaction committed" are two different milestones.

Suppose the application service uses `@Transactional`; a common implementation pattern is:

```java
@Transactional
public void placeOrder(PlaceOrder command) {
    Order order = orderRepository.load(command.orderId());
    order.place(command.eventId());
    orderRepository.save(order);

    for (DomainEvent event : order.drainEvents()) {
        applicationEventPublisher.publishEvent(event);
    }
}
```

This is an **integration pattern**, not a standalone compilable program; it assumes `PlaceOrder`, the repository, and the fields are already defined, along with an appropriate transaction manager and Spring proxy.

In the default synchronous multicaster configuration, `@EventListener` runs **when the event is published**, which is typically **before the transaction commits**. As a result, listeners can see uncommitted data within the same transaction, and an HTTP/email call made by a listener may have already executed even if the DB eventually rolls back.

For side effects that are only valid after commit, you can use:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderPlaced(OrderPlaced event) {
    notificationJobService.enqueue(event.aggregateId());
}
```

This is also an **integration pattern**, requiring Spring beans/listeners and the corresponding service types. `@TransactionalEventListener` defaults to `AFTER_COMMIT`; if there is no active transaction, it **does not run** by default unless `fallbackExecution=true` is set. Do not enable fallback if the business requirement is "run only after a successful commit."

### Why is AFTER_COMMIT not enough to guarantee delivery?

If the DB has just committed but the process terminates before the callback finishes, post-commit work may remain undone. A failing `AFTER_COMMIT` listener also **cannot roll back the main transaction that has already committed**. Do not treat transaction callbacks or in-process Spring events as a durable queue.

If a post-commit callback needs to perform new DB writes, it must open a **new transaction** properly via a service/transaction manager—for example, a proxied method with `Propagation.REQUIRES_NEW`. The previous transaction's resources may still be bound during the lifecycle callback, and new changes will not automatically be committed again.

For tasks that must be delivered after commit (sending notifications, updating other services, reporting), consider a **transactional outbox**.

## 8. Domain events, outbox, and integration events

### 8.1. The transactional outbox pattern

The application service saves the aggregate changes and the outbox record in the **same DB transaction**:

```text
Transaction:
  1) UPDATE orders SET status = PLACED ...
  2) INSERT outbox(event_id, event_type, aggregate_id, payload, ...)
  3) COMMIT both

Separate worker:
  4) Read undelivered outbox records
  5) Publish integration event to broker
  6) Record delivery/retry
Consumer:
  7) Deduplicate by event ID or business key
  8) Update its own state
```

If the transaction rolls back, both the aggregate and the outbox record roll back. If the commit succeeds, the intent to publish the event is persisted alongside the business data; the worker can resume after a restart.

This typically provides **at-least-once delivery** semantics under retries, because the worker may publish successfully and crash before marking the record as sent. Therefore, consumers must be **idempotent**. Do not assume an outbox provides end-to-end exactly-once delivery by default.

### 8.2. Converting from domain events to integration events

You do not need to send raw domain objects externally. A mapper can produce a public payload:
- `type`: for example, `sales.order.placed`.
- `eventId`: stable ID for deduplication.
- `aggregateId` and `aggregateVersion` (if per-aggregate ordering is needed).
- `occurredAt`, `schemaVersion`, `correlationId`.
- Fields permitted to be exposed under the contract and data policies.

The domain can evolve internal classes/fields while integration events are versioned independently. If multiple bounded contexts need different meanings, you can derive tailored integration events from the same domain fact instead of forcing every consumer to understand the internal aggregate structure.

## 9. Listener independence and error policies

Multiple listeners subscribed to `OrderPlaced` should be treated as multiple consumers of **the same fact**, not mandatory steps invoked in an implicit sequence.

Common mistake:

```text
Listener A: calculate loyalty points and write to a temporary Map
Listener B: read that Map to issue a voucher
```

If B runs before A, the data is missing. Applying `@Order` only constrains invocation priority under certain configurations; it does not define a workflow with explicit retries, transactions, and durability.

When two tasks are genuinely independent, each listener receives sufficient data from the event or committed sources and owns its own side effects. When B **strictly** requires A's result, model the A→B step with an application workflow or a follow-up event (e.g., `PointsCalculated`) with an appropriate delivery mechanism.

**Synchronous listener errors:** with Spring's default multicaster, `publishEvent` can propagate an exception thrown by one listener; subsequent listeners may not run. To isolate secondary tasks, define an error handler, queue/executor, and retry policy; do not merely add `@Async` and assume the system is reliable. Asynchronous execution changes completion timing, error observability, and transaction context.

**Idempotency:** a domain event may be redelivered after a retry, or two distinct logical events may affect the same aggregate. Distinguish the occurrence's `eventId` from the entity's `aggregateId`. Consumers should use a unique constraint or transaction to ensure an operation is not unintentionally performed twice. In the example, `EVT-42` is passed as a fixed value so stdout is predictable; in production, the system must generate a unique ID per logical event occurrence and keep it unchanged across retries.

## 10. Versioning, ordering, and eventual consistency

Domain events usually describe state **at a point in time**. When an aggregate emits multiple events, such as:

```text
OrderPlaced(orderId=ORD-42, aggregateVersion=7)
OrderAddressChanged(orderId=ORD-42, aggregateVersion=8)
OrderCancelled(orderId=ORD-42, aggregateVersion=9)
```

This is an illustrative model. If a consumer receives v9 before v8, it must have an explicit policy: wait, reorder by aggregate version, ignore stale events, or query the appropriate latest state. A unique event ID prevents duplicate processing, but **does not solve ordering on its own**.

Many systems accept **eventual consistency** across bounded contexts: a consumer's data may lag behind the source aggregate. For critical operations requiring immediate consistency, consider handling them within the aggregate's transaction boundary rather than implicitly expecting async events to provide strong consistency.

### Do we need event sourcing?

**No.** Domain events and event sourcing are two distinct concepts:
- Domain events are a way to describe business facts so components can react.
- Event sourcing uses the event stream as the **primary source of truth** to reconstruct aggregate state.

A traditional CRUD application can still raise domain events and use a transactional outbox. Having `OrderPlaced` does not mean you need to rebuild aggregates from an event log. If you choose event sourcing, you must handle versioning, replay, snapshots, and per-aggregate mutations comprehensively; that is a separate architectural decision.

## 11. Designing events for maintainability

Several practical rules:

1. **Business-oriented names in the past tense:** `OrderPlaced`, `PaymentCaptured`; avoid `DoSomethingEvent`, `UpdateTableEvent`.
2. **Immutable and sufficient payloads:** IDs, meaningful snapshot data; do not pass mutable/lazy JPA entities.
3. **Respect aggregate boundaries:** events are produced by domain behavior that has satisfied invariants; listeners must not silently mutate the source aggregate while the event is still being dispatched.
4. **Decouple domain from transport:** plain Java aggregates; the application/infrastructure layer handles publishing, transactions, and outbox.
5. **Intentional publication timing:** distinguish when the domain recorded the event, when it was saved, when it committed, and when consumers completed.
6. **Version when long-lived consumers exist:** do not silently change the meaning of existing fields; support handling prior payload versions.
7. **Ensure idempotency:** handle duplicates with stable keys and proper transactions.
8. **System observability:** log/trace by `eventId` or correlation ID; measure retries, failed deliveries, and latency. Avoid tagging metrics with event IDs, which causes unbounded cardinality growth.
9. **Sensitive data:** restrict and classify payloads. Events may be retained for a long time or sent to many consumers.
10. **Do not raise events for every minor change:** choose meaningful state transitions that have real consumers/policies.

## 12. Testing domain events layer by layer

| Layer | Test case | Expectation |
| --- | --- | --- |
| Plain Java domain | `Order.draft(...).place(...)` | State becomes `PLACED`; creates exactly one `OrderPlaced` with the right payload |
| Domain invariant | Call `place(...)` a second time or pass invalid data | Throws an appropriate exception; creates no new event for the rejected operation |
| Application service | Save aggregate then publish exact pending events | Dispatches the right events; does not re-publish drained events in the same lifecycle |
| Spring integration | Open `AnnotationConfigApplicationContext`, publish `OrderPlaced` | Both `@EventListener` methods receive the right payload |
| Transaction commit | Publish inside a transaction then actually commit | `AFTER_COMMIT` listener runs at the right time |
| Transaction rollback | Publish inside a transaction then roll back | No post-commit side effects; rollback branch (if any) is handled properly |
| Outbox | Save aggregate + outbox in the same transaction | Both commit or both roll back; no outbox record when business logic fails |
| Duplicate/retry | Redeliver the same `eventId` | Consumer does not create invalid side effects a second time |
| Version/ordering | Deliver older and newer events out of order | Consumer handles them according to the defined versioning/ordering policy |

Domain tests require neither Spring nor a DB; that is a direct benefit of decoupling aggregates from infrastructure. Integration tests should use a real DB or equivalent test database to verify rollbacks and the outbox; simply mocking `publishEvent` does not prove data was committed.

If you use `@Transactional` in tests and the framework automatically rolls back at the end, `AFTER_COMMIT` listeners may not execute. Use an explicitly committed transaction or an appropriate test transaction mechanism when you need to verify the real commit branch.

## 13. Common mistakes

- **Calling the Spring publisher directly from every entity:** the domain becomes framework-dependent, harder to test, and harder to control commits.
- **Publishing events before checking invariants:** emits notifications for rejected actions.
- **Treating `@EventListener` as "after commit":** ordinary listeners may run before the transaction finishes.
- **Treating `@TransactionalEventListener(AFTER_COMMIT)` as a durable queue:** the process can still crash after commit before side effects finish.
- **Passing mutable/lazy JPA entities in events:** prone to race conditions, stale state, or lazy-initialization errors outside the transaction.
- **Not managing stable event IDs:** retries can create hard-to-detect duplicates.
- **Confusing domain events and integration events:** internal changes unexpectedly break contracts with other services.
- **Forcing listeners on the same event to run in order:** this is actually a workflow with dependencies that should be modeled explicitly.
- **Not handling exceptions during publication:** synchronous listener errors can disrupt the application service and other listeners.
- **Assuming every event requires event sourcing:** event sourcing is a separate state-storage mechanism, not a requirement of DDD domain events.

## 14. Design review checklist

- [ ] Does the event name describe a business fact that has occurred?
- [ ] Does the aggregate create the event at a valid state transition while protecting invariants?
- [ ] Is the domain event a Java type independent of Spring/broker mechanisms?
- [ ] Is the payload an immutable snapshot with a stable ID and only the necessary data?
- [ ] Does the application service clearly define save, publish, commit, and error-handling timing?
- [ ] Are external non-DB side effects deferred or stored in an outbox when business rules require it?
- [ ] Do domain events and integration events have clear contract boundaries and appropriate versioning?
- [ ] Do consumers have idempotency, ordering policies, retries, and observability?
- [ ] Do tests cover domain invariants, commits, rollbacks, duplicates, and failures?
- [ ] Are domain events not being used to disguise a mandatory chain of dependent steps?

**Remember:** a domain event records something that **happened in the business model**. The aggregate decides when that is true; the application layer and infrastructure decide how to store, publish, and handle the event safely. Spring Application Events are a convenient in-process mechanism, whereas reliable cross-system delivery usually requires transactions/outbox, versioning, and idempotency.

## References

- [Martin Fowler — Domain Event](https://martinfowler.com/eaaDev/DomainEvent.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring 6.1 API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring 6.1 API — EventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring 6.1 API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
