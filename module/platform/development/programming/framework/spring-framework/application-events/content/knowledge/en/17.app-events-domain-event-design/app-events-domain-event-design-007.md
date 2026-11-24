# Collecting Domain Events Before Publishing in Spring Framework

## 1. The problem to solve

In Domain-Driven Design (DDD), a business state change can give rise to **domain events**: for instance, an order was paid (`OrderPaid`), a receipt was requested (`ReceiptRequested`), or a user changed their email (`EmailChanged`). A domain event describes **a business fact that has occurred in the domain model**, not merely a request saying "run another function."

If an aggregate calls `ApplicationEventPublisher.publishEvent(...)` directly inside a business method, the domain model becomes coupled to Spring and side effects may run before the aggregate's state is saved successfully:

```text
Order.pay()
  ├─ change order state
  ├─ publishEvent(OrderPaid)     <-- sent too early
  └─ repository.save(order)      <-- might fail/roll back
```

Consequence: a listener may have already sent an email, updated a cache, or called another system while the record was never saved or the transaction later rolled back. Writing unit tests for `Order` also becomes harder when it requires an `ApplicationEventPublisher`.

**Solution:** the domain only **collects (records/registers) events into a pending events buffer**. An orchestration layer outside the domain—such as an application service, a repository adapter, or Spring Data's mechanism—chooses when to hand events over to the publisher.

```text
Command / application service
       |
       v
Aggregate executes business behavior
  ├─ mutate state
  ├─ check invariants
  └─ register(new OrderPaid(...))
       |
       v
pendingEvents = [OrderPaid, ReceiptRequested]
       |
       v
Application service / repository infrastructure
  ├─ persist aggregate
  ├─ take snapshot of pending events
  ├─ publish / write outbox
  └─ acknowledge, clear, or transfer ownership of events
       |
       v
Spring ApplicationEventPublisher -> listeners
```

"Collecting before publishing" means **decoupling event recording in the domain from event distribution in infrastructure**, not automatically guaranteeing exactly-once or post-commit delivery.

## 2. What are pending events in an aggregate?

An aggregate root can maintain its own buffer, such as `List<DomainEvent> pendingEvents`. Each method performing valid business behavior appends events to that list without **publishing them immediately**.

Three concepts to distinguish:

- **Business state**: e.g., `paid = true`; this is the state that must be persisted or derived from an event log depending on architecture.
- **Pending domain event**: describes behavior just accepted within one processing cycle. Usually a temporary in-memory list, not automatically guaranteed to survive a process crash.
- **Published/delivered event**: an event already handed over to the publishing mechanism; whether listeners have finished handling it depends on the multicaster and async/retry strategy.

A simple aggregate with no Spring dependency can register events like this (excerpt only):

```java
private final List<DomainEvent> pendingEvents = new ArrayList<>();

private void register(DomainEvent event) {
    pendingEvents.add(Objects.requireNonNull(event));
}

public List<DomainEvent> pendingEvents() {
    return List.copyOf(pendingEvents); // read-only snapshot from outside
}
```

Business methods can call `register(new OrderPaid(...))` after checking invariants and updating valid state. Domain code does not need to know which listeners exist and does not need to import Spring.

### Designing the event payload

Use an immutable `record` (Java 17) or immutable object holding the snapshot data consumers need. Example:

```java
record OrderPaid(String orderId, String paymentId, long amountInCents) {}
```

- `orderId`: aggregate reference.
- `paymentId`: business identifier for tracking/deduplication when each payment has a unique ID.
- `amountInCents`: value snapshot when the event was created; avoids letting listeners read mutable aggregate state directly after it may have changed.

In real systems, you can add a dedicated event ID, event timestamp, schema version, and aggregate version. Do not pass mutable JPA entities or an `EntityManager` to listeners as a long-lived "event payload," because their lifecycle is tied to the transaction/persistence context.

### Do not turn pending events into an implicit part of persisted state

When using JPA, pending events are usually transient details of the aggregate and can be marked `@Transient` on the entity. If an aggregate is reloaded from the database after a temporary buffer was lost, do not assume unpublished events will magically reappear. When crash recovery is required, you need a **durable outbox** or a proper event store.

## 3. When to collect, when to publish?

An easy-to-follow application flow:

1. Receive a command and load the aggregate.
2. Invoke domain behavior (`order.pay(...)`). The aggregate checks constraints, updates state, and **registers events**.
3. Persist state via a repository or Unit of Work.
4. Read a snapshot of pending events to decide the publishing mechanism.
5. Hand events over to `ApplicationEventPublisher`, or write them to an outbox.
6. Mark handed-off events according to the execution policy.

**This order describes only a simple flow; it does not mean "once save returns, the database has committed."** When a service uses `@Transactional`, `repository.save(...)` typically runs while the transaction is still open. Publishing directly right after `save` inside the same transaction means synchronous listeners can run **before commit**.

There are three policies to choose between explicitly:

| Approach | Behavior | Best suited for |
| --- | --- | --- |
| Publish right after `save` while transaction is open | Ordinary listeners can run before commit | In-transaction internal processing without irreversible side effects |
| Publish in transaction and use `@TransactionalEventListener(AFTER_COMMIT)` | Listener triggers only after successful commit | Post-commit behavior in the same process; no durable event storage guarantee |
| Write a **transactional outbox** in the same DB transaction; worker relays after commit | Durable event record for retries if the process crashes | Cross-service integration needing reliability and delivery control |

Simply calling `pendingEvents.clear()` after publishing does not turn an in-memory list into a durable queue. Document failure boundaries and retry strategies clearly before going to production.

## 4. Runnable example: Java 17 + Spring Framework 6.2

This example **illustrates collecting and handing off events within one process**. It uses a simulated in-memory repository with no database transaction; do not take it as proof that events and data are committed atomically.

One call to `checkout` records **two** events in order: `OrderPaid` and `ReceiptRequested`. The domain knows nothing about Spring. The application service saves the aggregate, takes a snapshot of pending events, and publishes each event. When `publishEvent` returns normally, the example removes the event that was just handed off.

### Maven structure

```text
pending-domain-events/
├── pom.xml
└── src/main/java/demo/PendingDomainEventsDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>pending-domain-events</artifactId>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.PendingDomainEventsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/PendingDomainEventsDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class PendingDomainEventsDemo {

    // Plain Java domain section, no Spring imports.
    public sealed interface DomainEvent
            permits OrderPaid, ReceiptRequested {}

    public record OrderPaid(
            String orderId, String paymentId, long amountInCents)
            implements DomainEvent {}

    public record ReceiptRequested(
            String orderId, String paymentId)
            implements DomainEvent {}

    public static final class Order {
        private final String orderId;
        private boolean paid;
        private final List<DomainEvent> pending = new ArrayList<>();

        public Order(String orderId) {
            this.orderId = Objects.requireNonNull(orderId);
        }

        public String orderId() {
            return orderId;
        }

        public void pay(String paymentId, long amountInCents) {
            Objects.requireNonNull(paymentId);
            if (paid) {
                throw new IllegalStateException("Order already paid");
            }
            if (amountInCents <= 0) {
                throw new IllegalArgumentException("Amount must be positive");
            }

            // Domain finishes valid state change, ONLY records events.
            paid = true;
            pending.add(new OrderPaid(orderId, paymentId, amountInCents));
            pending.add(new ReceiptRequested(orderId, paymentId));
        }

        public List<DomainEvent> pendingEvents() {
            return List.copyOf(pending); // snapshot, does not expose mutable list
        }

        public void acknowledge(DomainEvent event) {
            if (!pending.remove(event)) {
                throw new IllegalArgumentException("Unknown pending event");
            }
        }
    }

    public static final class InMemoryOrderRepository {
        public void save(Order order) {
            // Not real persistence and no DB transaction.
            System.out.println("repository: saved " + order.orderId());
        }
    }

    public static final class CheckoutService {
        private final InMemoryOrderRepository repository;
        private final ApplicationEventPublisher publisher;

        public CheckoutService(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            this.repository = repository;
            this.publisher = publisher;
        }

        public void checkout(
                Order order, String paymentId, long amountInCents) {
            order.pay(paymentId, amountInCents);
            System.out.println("service: pending=" +
                    order.pendingEvents().size());

            repository.save(order);

            // Snapshot so we can iterate while acknowledging the original buffer.
            List<DomainEvent> events = order.pendingEvents();
            for (DomainEvent event : events) {
                publisher.publishEvent(event);
                order.acknowledge(event); // after successful hand-off
            }
            System.out.println("service: pending=" +
                    order.pendingEvents().size());
        }
    }

    public static final class Handlers {
        @EventListener
        public void onPaid(OrderPaid event) {
            System.out.println("listener: paid " + event.orderId() +
                    " " + event.amountInCents());
        }

        @EventListener
        public void onReceipt(ReceiptRequested event) {
            System.out.println("listener: receipt " + event.orderId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        InMemoryOrderRepository repository() {
            return new InMemoryOrderRepository();
        }

        @Bean
        Handlers handlers() {
            return new Handlers();
        }

        @Bean
        CheckoutService checkoutService(
                InMemoryOrderRepository repository,
                ApplicationEventPublisher publisher) {
            return new CheckoutService(repository, publisher);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            Order order = new Order("O-42");

            System.out.println("before command: pending=" +
                    order.pendingEvents().size());
            context.getBean(CheckoutService.class)
                    .checkout(order, "PAY-9", 1500);
            System.out.println("after command: pending=" +
                    order.pendingEvents().size());
        }
    }
}
```

Run with JDK 17+ and Maven in the project directory:

```bash
mvn -q clean compile exec:java
```

Output produced by the example's `System.out.println` statements:

```text
before command: pending=0
service: pending=2
repository: saved O-42
listener: paid O-42 1500
listener: receipt O-42
service: pending=0
after command: pending=0
```

Explanation:

1. `Order.pay()` changes state and records two events in `pending`, without publishing yet; no listener log lines appear yet.
2. The service observes two pending events before saving.
3. The simulated repository prints `repository: saved ...` before any listener runs.
4. `ApplicationEventPublisher.publishEvent(Object)` hands each record over to Spring; records do not need to extend `ApplicationEvent`. Spring can wrap event objects in `PayloadApplicationEvent` during dispatch.
5. With the default synchronous multicaster and these simple listeners, each event is processed during the `publishEvent` call. The order in the example follows iteration order over the pending list.
6. After each normal `publishEvent` return, the service calls `acknowledge` on the event and empties the pending buffer. `List.copyOf` lets us iterate over a snapshot without hitting `ConcurrentModificationException` when removing from the underlying list.

**Limitation of the example:** Printing `repository: saved` does not mean data was durably committed; this implementation just prints to stdout. In a real JPA repository with `@Transactional`, `save` does not necessarily mean commit. And `publishEvent` returning does not mean all async listeners have completed or that external side effects are durable.

## 5. Why collect in the aggregate instead of publishing inside the entity?

### Keep the domain framework-independent

A good aggregate expresses rules such as "do not pay the same order twice" or "amount must be positive." Injecting `ApplicationEventPublisher` into an entity forces the domain to know about infrastructure and invites mixing in network/notification code. Collecting events keeps entities plain Java and easy to test.

### Protect invariants before creating events

A business command that fails an invariant check **must not** append `OrderPaid`. If events are created before validation or before state changes consistently, listeners may observe something that never actually happened.

### Allow multiple changes before a single handoff

A command can touch multiple methods of the same aggregate and produce several events. The application service can take a snapshot after finishing a unit of business work, instead of emitting fragmented events while domain steps are still in flight.

However, the pending list **is not by itself an event log**: an event log is durable storage serving as the source of truth in an event-sourced model, whereas a pending list is usually just a temporary buffer for publishing raised notifications.

### Better testability

No need to start Spring when testing aggregates:

```java
Order order = new Order("O-42");
order.pay("PAY-9", 1500);
assert order.pendingEvents().size() == 2;
```

This snippet is illustrative and requires the same `Order` definition as the main example. In real JUnit tests, prefer `assertEquals(...)`/`assertThrows(...)` instead of Java `assert`, which can be disabled when `-ea` is off. Tests should verify the new state, event types/counts/payloads, and that no events are added when an invariant rejects the operation.

## 6. Built-in Spring Data support: @DomainEvents and @AfterDomainEventPublication

When aggregates are managed through a Spring Data repository, you can use `@DomainEvents` and `@AfterDomainEventPublication` instead of a manual publishing loop.

API structure example (excerpt; requires complete classes/interfaces/imports and a real repository):

```java
class OrderAggregate {
    private final List<Object> events = new ArrayList<>();

    void pay(String paymentId) {
        // update domain state, check invariants...
        events.add(new OrderPaid(/* immutable snapshot */));
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

**Note:** `new OrderPaid(/* ... */)` in the API example above is an illustrative placeholder, not a standalone program; run the full example in section 4 or supply a real constructor.

Annotation meanings:

- `@DomainEvents` is placed on a **no-argument** method returning a single event or collection for repository infrastructure to publish.
- `@AfterDomainEventPublication` is placed on a callback executed after infrastructure publishes the events, typically to clear the buffer.
- Per Spring Data Commons documentation, these hooks apply to repository operations that accept an aggregate instance, such as `save(...)`, `saveAll(...)`, and certain forms of `delete(...)`; **do not assume `deleteById(...)` always triggers them**, because the framework can delete by ID without passing an aggregate instance to the event mechanism.

Important: `@AfterDomainEventPublication` is the milestone **after invoking the publication mechanism**, not proof that the transaction committed successfully, the event reached a broker, or all async listeners finished processing.

### AbstractAggregateRoot reduces boilerplate

Spring Data Commons provides the base class `org.springframework.data.domain.AbstractAggregateRoot<A>`, offering:

- `registerEvent(event)` to append an event;
- `andEvent(event)` to append an event and return the aggregate;
- `domainEvents()` to expose pending events;
- `clearDomainEvents()` to clear the buffer after publication via the appropriate annotation.

Illustrative excerpt:

```java
class OrderEntity extends AbstractAggregateRoot<OrderEntity> {
    void pay(String paymentId) {
        // After updating state and checking invariants:
        registerEvent(new PaymentAccepted(orderId, paymentId));
    }
}
```

Names like `PaymentAccepted`/`orderId` must be defined in a real project. Use a standard Spring Data repository so infrastructure executes the hooks; **merely calling a method on the entity does not publish events automatically**.

Do not clear the pending list yourself in `@PostPersist` or an ORM lifecycle callback if Spring Data is responsible for publication, as doing so can easily drop events before infrastructure reads them.

## 7. Event handoff and transactions: three independent questions

### 7.1. Has the state been saved?

`repository.save(order)` is only a repository call. With JPA, SQL writes may be flushed later and the transaction only commits at the service boundary. If the service rolls back after `repository.save` returns, the final state may not be persisted.

Thus, the rule "save first, then publish" **is not enough** to guarantee external non-DB listeners only process events from a committed transaction.

### 7.2. Has the event been published?

`ApplicationEventPublisher.publishEvent(Object)` is a **handoff** to Spring's multicaster. Spring Framework documentation emphasizes this is not a promise that all listeners run synchronously, immediately, or have already finished. With the synchronous default, listener errors can propagate to the publisher; with `@Async` or an async executor, the publisher can return before listeners finish running.

If you call `clear` right after handoff, the pending list no longer retains events for retry if async processing fails later.

### 7.3. Has the consumer processed it exactly once?

Even if an event is published successfully, a consumer may fail after performing part of a side effect. Retrying after a timeout or process restart can cause duplicates. **"Exactly once" at the level of external side effects does not come automatically from a pending list, @DomainEvents, or @TransactionalEventListener.**

To protect against duplicates, each event should have a stable event ID and consumers should use idempotent operations or store processed IDs with an appropriate unique constraint.

## 8. Two safer strategies when transactions are involved

### 8.1. @TransactionalEventListener(AFTER_COMMIT) for in-process reactions

The publisher may publish events while the transaction is open, while listeners register:

```java
@Component
class NotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPaid event) {
        // Invoked only when the corresponding imperative transaction commits.
    }
}
```

This is an excerpt requiring full imports and bean definitions. With thread-bound imperative transactions, the listener registers a callback on the active transaction; handler code executes only after commit. By default `@TransactionalEventListener` does not handle events if **no transaction exists**; `fallbackExecution = true` is available when business policy permits.

This solves **running listeners before commit**, but does not fully solve the case where the process crashes after commit before the listener performs its side effect. In-memory event data can still be lost. For new database writes inside `AFTER_COMMIT`, consider a separate `REQUIRES_NEW` transaction; the previous transaction does not automatically perform another commit.

### 8.2. Transactional outbox when durable delivery is required

When the system needs events delivered to a message broker or another service even after crashes, write pending events to an **outbox table** in the same transaction as aggregate state:

```text
BEGIN TRANSACTION
  update orders
  insert into outbox(event_id, aggregate_id, type, payload, created_at)
COMMIT

background relay
  read committed outbox rows
  publish to broker / external destination
  mark delivered or delete after acknowledgement
  retry with backoff on failure
```

Benefits and prerequisites:

1. State and outbox commit/roll back **together**; if the transaction rolls back, the outbox event row rolls back too.
2. After a crash, the relay can re-read the outbox and continue.
3. The relay may deliver an event more than once if publishing succeeded before it marked the row complete; **consumers must be idempotent**.
4. You need a job/relay, monitoring, retry policy, dead-letter handling, per-aggregate ordering where critical, and throughput/retention control.
5. Event payloads/schemas should be immutable and versioned so consumers do not depend directly on entity structure.

An outbox is not an automatic feature of `@DomainEvents`. It is a dedicated storage and messaging design structured around transactions.

## 9. Policy for clearing pending events: options and pitfalls

| Scenario | Correct response |
| --- | --- |
| Aggregate creates event, then command is rejected before state change | Create no event |
| Repository save fails | Do not assume events can be published; retain or discard buffer per rollback/reload policy |
| `publishEvent` throws an exception mid-list | Earlier events may have already been handled; do not blindly wipe the entire buffer |
| `publishEvent` returns with an async executor | Only proves handoff, not listener completion |
| Transaction later rolls back | Early-published events may cause wrong side effects; use after-commit/outbox |
| Event consumer receives the same event again | Use event ID and idempotency/deduplication |
| Aggregate is reloaded from DB in another process | Temporary pending list may be gone; use an outbox to recover |
| Multiple concurrent commands on one aggregate | Use optimistic/pessimistic concurrency and suitable isolation |

Two common policies exist:

**(A) Acknowledge each event after handoff**, as in section 4's example. Advantage: a failure on the third item does not wipe two unhanded items. Drawback: the first two events may have already run, yet retrying the whole batch could re-publish them because in-memory state/transactions are not durable. Therefore, prevent duplicate processing or record handoff status safely.

**(B) Take a snapshot and clear at a well-defined boundary.** For example, Spring Data infrastructure provides `@AfterDomainEventPublication`. Advantage: avoids accidental re-publication within the same persistence context. Drawback: does not guarantee after-commit or exactly-once.

Do not automatically "clear upfront to avoid duplicates": if publishing fails after clearing, you have lost the information needed to retry. Conversely, "clear after calling the publisher" is also insufficient if an async listener fails afterward. Base the policy on retry, idempotency, and durability needs—not merely API convenience.

## 10. Collect in the aggregate or in a Unit of Work?

### Aggregate-owned event buffer

This is the common choice when events reflect the invariants and state of **a single aggregate**. Events are created directly inside domain behavior; the application service collects and hands them off at the persistence boundary.

Pros: clear logic, simple testing, framework-independent domain, easy integration with `AbstractAggregateRoot`.

Cons: requires managing the pending list lifecycle, aggregate state after errors, and ORM mapping if persisting entities. Never share the same mutable aggregate instance across multiple requests/threads without concurrency control.

### Unit-of-Work/event collector at the application layer

In business operations touching multiple aggregates or needing a centralized publishing policy, you can use one collector per unit of work. Each aggregate records events into a collector passed through a domain interface or returned as part of the result. The application service publishes or writes to an outbox after everything succeeds.

Pay special attention to collector scoping: never use a shared mutable singleton list across requests, or you will mix events from different transactions. Give it clear scoping (command/transaction), thread safety, and cleanup, and do not rely on `ThreadLocal` across async/reactive context switches without propagating the needed context.

**Selection rule:** use an aggregate buffer when protecting single-aggregate semantics; use a Unit of Work when gathering events from multiple domain units; use a transactional outbox when prioritizing durability and cross-service communication. These approaches can be combined, provided exactly one place is responsible for transitioning events from pending to published/outbox.

## 11. Testing critical cases

Beyond happy-path tests, verify these scenarios:

1. **No premature publishing:** call `order.pay(...)` and assert `pendingEvents` grows while listeners have not been invoked before the application service publishes.
2. **Accurate payload:** ID, payment ID, amount, and snapshot match the data when the domain operation completes.
3. **Invariant failure:** invalid amount or already-paid order creates no new event.
4. **Save failure:** simulate the repository throwing an exception; verify the publisher receives no events.
5. **Mid-batch publish failure:** verify your acknowledge/retain-pending strategy and explicit retry behavior; do not claim zero duplicates without idempotency.
6. **Rollback:** with a real transaction, verify `AFTER_COMMIT` listeners do not run when the transaction rolls back.
7. **Crash/retry:** if using an outbox, verify the event row persists after commit and the relay re-sends after restart.
8. **Duplicate delivery:** consumer processes the same event ID twice while side effects apply according to the idempotency policy.
9. **Concurrent commands:** aggregate versioning or row locks prevent invariants from being violated when two commands run concurrently.

Split tests into plain-domain unit tests, integration tests for Spring publisher/repository, and integration/contract tests for outbox/broker where used.

## 12. Summary and self-check questions

**Mental model:** valid domain change → record pending events → persistence boundary → choose publish or outbox → acknowledge/cleanup per defined policy. Separating event creation from event publishing keeps the domain clean and improves timing control, yet **does not automatically provide atomic commits or durable delivery**.

Questions:

1. **Why should an aggregate not call ApplicationEventPublisher directly in `pay()`?** — To avoid coupling to Spring and prevent side effects before persistence/commit.
2. **Is a pending list an event store?** — No; it is typically just an in-memory buffer.
3. **Can a single domain operation collect multiple events?** — Yes, e.g., `OrderPaid` and `ReceiptRequested`.
4. **Does `save` returning mean the transaction has committed?** — No.
5. **Does `publishEvent` returning prove all listeners have finished processing?** — No, especially when async is involved.
6. **Does `@AfterDomainEventPublication` mean "successfully sent to the broker"?** — No, it is a callback after Spring Data's publication step.
7. **Why does `deleteById` not guarantee the @DomainEvents mechanism?** — The repository can delete purely by ID without receiving an aggregate instance.
8. **When events must not be lost across DB commits and process crashes, what should you choose?** — A transactional outbox with a relay, retries, and idempotent consumers.
9. **If there is no active transaction, does `@TransactionalEventListener` run by default?** — No, unless fallback is explicitly configured.
10. **Why is a duplicate-handling policy important?** — Retries can cause redelivery, making event IDs and idempotent handlers essential mechanisms.

## References

- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Data Commons — AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
