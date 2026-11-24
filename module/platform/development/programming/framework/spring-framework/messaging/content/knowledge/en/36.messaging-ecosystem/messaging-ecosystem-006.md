# Spring Modulith or ApplicationEvent for In-Application Events

> Scope: using events to reduce coupling between modules within the same Spring ApplicationContext, choosing the right listener and transaction phase, and deciding when Spring Modulith or a message broker is needed to guarantee recoverable publications.

## 1. Objectives

After this lesson, you will be able to:

- Explain `ApplicationEventPublisher`, `@EventListener`, and how Spring dispatches events.
- Distinguish synchronous events, post-commit events, and asynchronous events.
- Choose `ApplicationEvent` for internal communication within one ApplicationContext.
- Use Spring Modulith to decouple modules and manage transactional listener publications.
- Understand the Event Publication Registry, publication states, retries, and cleanup.
- Externalize events to Kafka, AMQP, JMS, or MessageChannel when external integration is needed.
- Design immutable, idempotent, and version-compatible event contracts.
- Test event publications and listeners across module boundaries.

## 2. What is an Event in Spring?

An event is a notification that something has happened. For example, `OrderCompleted` states that an order has completed. The module emitting the event does not need to know every module interested in it; listeners subscribe by event type to receive notifications.

Spring provides `ApplicationEventPublisher` to publish events and `ApplicationListener` or `@EventListener` to receive events. Since Spring Framework 4.2, any plain Java object can be published; classes are not required to extend `ApplicationEvent`.

Example event contract:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderCompleted(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {}
```

Records are a good choice because events are typically immutable data. `eventId` helps identify the publication and supports idempotency; `orderId` lets consumers load needed business state; `occurredAt` records when the domain event occurred.

Do not put entire JPA entities or objects with lazy relationships into an event. Events should carry minimal, clear, and stable data. If a consumer needs more data, it can load it via a service/repository by ID and verify current state.

## 3. Publishing and consuming with ApplicationEvent

### 3.1. Publishing events

A service emits an event via `ApplicationEventPublisher`:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderService(OrderRepository orders, ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void complete(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();
        order.complete();

        events.publishEvent(new OrderCompleted(
                UUID.randomUUID(), orderId, Instant.now()));
    }
}
```

Calling `publishEvent` dispatches the event to listeners in the same `ApplicationContext`. This API itself does not write events to a broker, does not persist them durably, and does not emit events to another JVM.

### 3.2. Receiving events with @EventListener

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class OrderAuditListener {

    @EventListener
    void on(OrderCompleted event) {
        auditLog.record(event.orderId(), "ORDER_COMPLETED");
    }
}
```

By default, Spring invokes listeners synchronously on the same thread when the event is published. `publishEvent` waits for listeners to finish before returning. If a listener throws an exception, the exception can propagate back to the publisher and roll back the ongoing transaction.

This is useful when the listener is part of the same business operation and needs a synchronous result. However, slow listeners prolong requests and transactions; listeners depending on many modules also increase operational coupling.

### 3.3. Multiple listeners and module boundaries

One event can be received by multiple listeners of the same type. The producer depends only on `ApplicationEventPublisher`, without injecting each consumer service.

In modular architectures, events should represent a clearly meaningful domain or application occurrence. Place event contracts in packages/APIs that modules are allowed to depend on. Avoid turning an event into a vague command such as `DoSomething`; an event describes what happened, whereas a command requests an action.

The Spring Framework event system targets communication between Spring beans in the same ApplicationContext. If communication across processes, hosts, or other applications is required, a broker or dedicated integration mechanism is needed.

## 4. Events and transactions

### 4.1. Synchronous listeners within a transaction

With the default synchronous `@EventListener`, the listener runs in the publishing thread. If the publisher is inside a transaction, the listener sees that transaction context. Database changes in the listener can participate in the same transaction and commit/roll back together.

This is a simple consistency model: if a critical listener fails, the original transaction can roll back. In exchange, the transaction is prolonged and secondary tasks can also cause the primary operation to fail.

### 4.2. @TransactionalEventListener

When a listener should run only after a transaction commits successfully, use `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class SearchIndexListener {

    @TransactionalEventListener
    void on(OrderCompleted event) {
        searchIndex.updateOrder(event.orderId());
    }
}
```

By default, the listener runs in the `AFTER_COMMIT` phase. Available phases:

| Phase | When the listener is invoked |
| --- | --- |
| `BEFORE_COMMIT` | Before the transaction commits |
| `AFTER_COMMIT` | After the transaction commits successfully; default |
| `AFTER_ROLLBACK` | When the transaction rolls back |
| `AFTER_COMPLETION` | After the transaction finishes, whether commit or rollback |

If no transaction is active, `@TransactionalEventListener` is not invoked by default. You can enable `fallbackExecution = true`, though then the listener also runs when events are published outside a transaction; use this only when those semantics are intended.

After `AFTER_COMMIT`, the original transaction has completed. If the listener needs to write to the database in its own transaction, open a new transaction, typically via `@Transactional(propagation = Propagation.REQUIRES_NEW)`.

### 4.3. Asynchronous execution with @Async

You can combine `@Async` and `@TransactionalEventListener`:

```java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
class NotificationListener {

    @Async
    @TransactionalEventListener
    void on(OrderCompleted event) {
        notificationService.sendOrderCompleted(event.orderId());
    }
}
```

Async execution must be enabled with `@EnableAsync` and configured with a bounded thread/queue executor. Do not use an unbounded executor because event bursts can grow heap usage or spawn too many threads.

Asynchronous listeners decouple processing time from the publisher thread. Listener exceptions are not thrown back to the caller as in synchronous listeners; separate error handling, logging, metrics, and retry mechanisms are needed.

An important risk: `@TransactionalEventListener` combined with `@Async` does not by itself guarantee durable event storage. If the process dies after commit but before the listener task starts, the listener may never run. If events must not be lost, a publication registry/outbox or durable broker is needed.

### 4.4. Reactive transactions

Since Spring Framework 6.1, transactional event listeners support both thread-bound and reactive transactions. Reactive transactions store context in the Reactor Context rather than ThreadLocal. When publishing events in a reactive transaction, pass the transaction context to the event via `TransactionalEventPublisher`; do not assume listeners automatically see the transaction merely because they are invoked from a Reactor chain.

## 5. Spring Modulith and ApplicationModuleListener

### 5.1. What does Spring Modulith solve?

Spring Modulith helps build modular monolith applications: modules still run in the same application, yet have clear boundaries and APIs. Events are a way for a module to emit notifications without directly calling internal beans of another module.

Spring Modulith provides `@ApplicationModuleListener` as the default listener declaration for inter-module communication. This annotation combines asynchronous execution, transaction-bound events, and a dedicated transaction for the listener (`REQUIRES_NEW`).

```java
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryManagement {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        inventory.reserveOrAdjust(event.orderId());
    }
}
```

With this approach, the Order module only publishes `OrderCompleted`; the Inventory module registers its own listener and processes in a separate transaction after commit. Async execution must be appropriately configured for the application.

### 5.2. When to use ApplicationEvent and when to use Modulith?

| Need | Choice |
| --- | --- |
| Simple notifications between beans in the same ApplicationContext | `ApplicationEventPublisher` + `@EventListener` |
| Listener runs only after commit, no durable publication log needed | `@TransactionalEventListener` |
| Asynchronous module processing, separate transactions, and enforced module boundaries | `@ApplicationModuleListener` |
| Recording which listeners processed events, recovering failed publications after restart | Spring Modulith Event Publication Registry |
| Publishing events to other processes/services | Broker or event externalization |
| Needing advanced outbox semantics | Suitable outbox implementation, e.g., Namastack/JobRunr support in Modulith 2.1 |

You do not need Modulith just to emit a very simple internal event. Modulith's value grows when events serve as inter-module contracts, listeners need independent processing, and losing publications is a risk that must be managed.

## 6. Event Publication Registry

### 6.1. Why is a publication registry needed?

Suppose the transaction creating an order commits successfully. A listener updating inventory needs to run after commit. If the process crashes before the listener completes, using `@TransactionalEventListener` alone leaves no durable record of which publications remain unprocessed.

The Spring Modulith Event Publication Registry tracks transactional listeners. When an event is published, the registry writes a publication entry for each listener expected to receive the event within the original business transaction. When a listener completes successfully, the entry is marked completed. If the listener fails, the entry remains for recovery or resubmission.

Thus, the business transaction and publication records are written in the same transaction when using transaction-capable repositories. This is the foundation for detecting incomplete listeners after process failures.

### 6.2. Publication lifecycle

Since Spring Modulith 2.0, publications have the following statuses:

| Status | Meaning |
| --- | --- |
| `PUBLISHED` | Publication has been persisted and is awaiting processing |
| `PROCESSING` | A listener has claimed the publication and is running |
| `COMPLETED` | Listener finished successfully |
| `FAILED` | Listener failed or publication was marked stale |
| `RESUBMITTED` | Failed publication was resubmitted for processing |

The registry also tracks execution counts and resubmission timestamps. This allows limiting attempt counts and filtering by event type, publication age, or completion attempts.

### 6.3. Persistence starters

To store the publication log, add the starter matching your persistence technology. For example, JDBC:

```xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-jdbc</artifactId>
</dependency>
```

Spring Modulith also provides JPA and MongoDB starters. Use dependency management/BOM compatible with your project's Spring Boot version to manage versions; do not arbitrarily mix Spring Modulith versions.

The JDBC implementation creates the publication table if schema initialization is enabled and the table does not exist. In production, schemas can be managed with Flyway or Liquibase. The publication log stores serialized events; event schemas must remain compatible for as long as publications may still be retried.

### 6.4. Retries and stale publications

When a listener fails, the `FailedEventPublications` API can be used to resubmit failed publications:

```java
import org.springframework.modulith.events.FailedEventPublications;
import org.springframework.modulith.events.ResubmissionOptions;
import org.springframework.stereotype.Component;

@Component
class EventRecovery {

    private final FailedEventPublications failedPublications;

    EventRecovery(FailedEventPublications failedPublications) {
        this.failedPublications = failedPublications;
    }

    void retryFailedEvents() {
        failedPublications.resubmit(ResubmissionOptions.defaults());
    }
}
```

This is an API example for Spring Modulith 2.0+. In real operations, filter appropriate publications, cap batch/concurrency, set minimum age, and cap completion attempts. Do not continuously resubmit all failures without investigating root causes.

Publications can get stuck in `PUBLISHED`, `PROCESSING`, or `RESUBMITTED` if a process dies or a listener hangs. The Staleness Monitor introduced in Modulith 2.0 can mark overdue publications as `FAILED` when non-zero staleness thresholds are configured. They can then be resubmitted or handled manually.

### 6.5. Cleaning up completed publications

The default completion mode is `UPDATE`: completed entries are kept for lookup. Without cleanup, the publication table will grow unboundedly.

Spring Modulith supports the following modes:

- `UPDATE`: keep the entry and update the completion date.
- `DELETE`: delete the entry once the listener completes.
- `ARCHIVE`: move completed entries to an archive store.

Choose the mode based on audit and retention needs. If keeping `UPDATE`, a periodic job is needed to purge old completed publications.

## 7. Externalizing events to a broker

### 7.1. When is a broker needed?

Application events are dispatched only within an ApplicationContext. If consumers live in other processes, a messaging transport such as Kafka, AMQP/RabbitMQ, or JMS is needed.

Spring Modulith supports externalizing selected application events to a broker via broker-specific artifacts and the `@Externalized` annotation. Example:

```java
import org.springframework.modulith.events.Externalized;

@Externalized("orders.completed")
public record OrderCompleted(
        UUID eventId,
        UUID orderId,
        Instant occurredAt) {}
```

For Kafka, add `spring-modulith-events-kafka`; for AMQP, add `spring-modulith-events-amqp` and the appropriate Spring AMQP dependency; for JMS, use `spring-modulith-events-jms`. `@Externalized` selects events to emit and specifies the logical routing target per broker integration.

Target semantics depend on the broker: Kafka uses the target as the topic and can use a routing key as the message key; AMQP uses a routing key; JMS integration does not support routing keys. Configure broker topics/exchanges/queues, bindings, serializers, and security according to your actual infrastructure.

### 7.2. Externalization and outbox

Native Spring Modulith event externalization is implemented via transactional event listeners and the Event Publication Registry, allowing tracking and resubmitting failures when interacting with a broker. However, Spring Modulith documentation explicitly notes that this native approach does not cover every feature users expect from a dedicated outbox implementation.

Since Spring Modulith 2.1, externalization is supported via Namastack Outbox and JobRunr. If advanced outbox semantics are needed, evaluate those integrations or implement a transactional outbox tailored to your database and broker.

Even when using an outbox, do not assume consumers receive messages only once. Publishers may resend after timeouts or crashes; consumers need idempotency by `eventId` or business key.

### 7.3. Contracts when events leave the application

Externalized events are APIs between systems. You need to:

- Use stable event and field names, with versioning for breaking changes.
- Publish only data consumers are permitted to know; do not send secrets or unnecessary personal data.
- Use IDs and necessary snapshots instead of serializing entity graphs.
- Include `eventId`, `occurredAt`, and aggregate ID for tracing/correlation.
- Define serialization format, schema compatibility, and routing targets.
- Provide idempotency, retries, dead-letter handling, and error observability.
- Avoid renaming classes/packages arbitrarily if the default routing target is derived from the event type.

## 8. Idempotency and processing order

Event listeners can be invoked again during publication retries, broker redeliveries, or application crash recovery. A well-designed listener must be safe when receiving the same event multiple times.

A simple pattern is storing processed `eventId` values with a unique constraint in the same transaction as business updates:

```sql
CREATE TABLE processed_event (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
```

Upon receiving an event, insert `eventId`. If the key already exists, do not repeat side effects. If the insert succeeds, execute business processing and commit in the same transaction. If processing fails, the transaction rolls back so retries can run again.

If side effects occur outside the database, such as sending emails or calling payment APIs, use idempotency keys on the target system or store state/outbox records to manage uncertain outcomes.

Multiple listeners can run in parallel; retries can also cause newer events to finish before older ones. If per-aggregate ordering is mandatory, partition by aggregate key, serialize processing, or check versions/sequences in the domain model.

## 9. Testing events

### 9.1. Testing published events

Spring Modulith provides `@ApplicationModuleTest` and `PublishedEvents` to verify events emitted within a module test:

```java
@ApplicationModuleTest
class OrderModuleTests {

    @Test
    void publishesOrderCompleted(PublishedEvents events) {
        // Execute the operation that completes an order.

        assertThat(events.ofType(OrderCompleted.class))
                .hasSize(1);
    }
}
```

This snippet illustrates testing publications; configure test modules, data, and AssertJ according to the project. You can filter `PublishedEvents` by order ID to verify the exact event produced by the operation under test.

### 9.2. Testing listeners and failure paths

Tests should cover:

1. Synchronous `@EventListener` runs when the event is published.
2. `@TransactionalEventListener` runs only after commit and does not run after rollback.
3. Events published outside a transaction are skipped if `fallbackExecution` is disabled.
4. Async listeners handle errors via the proper executor/error handler.
5. Modulith listeners create publication entries and mark them completed upon success.
6. Failing listeners leave publications available for resubmission.
7. Resubmission does not cause duplicate side effects thanks to idempotency.
8. Event externalization serializes payload, headers, and routing targets accurately.
9. Old event schemas still deserialize if publications persist across multiple deployments.

For module integration tests, Spring Modulith provides the Scenario API to test publishing and handling events as a flow rather than merely checking that an event object appeared.

## 10. Common mistakes

| Symptom | Cause | Solution |
| --- | --- | --- |
| Listener does not run | Using `@TransactionalEventListener` without a transaction | Check transaction boundaries or consider `fallbackExecution` |
| Listener runs before commit | Using synchronous `@EventListener` | Use `@TransactionalEventListener` with the right phase |
| Unusually slow requests | Synchronous listener performing heavy I/O or processing | Move to async listeners/module listeners or a broker |
| Events lost on process restart | Using only `@Async`/`@TransactionalEventListener` without publication persistence | Use Event Publication Registry or an outbox/broker |
| Listener fails after main transaction committed | Listener runs `AFTER_COMMIT` or asynchronously | Design retries, registry, and idempotency |
| DB writes in after-commit fail to commit | Using the publisher's already-completed transaction | Open a new transaction with `REQUIRES_NEW` |
| Event processed twice | Retries, resubmissions, or broker redeliveries | Deduplicate by event ID/business key |
| Publication table grows continuously | Keeping completed entries in `UPDATE` mode without purging | Choose retention, cleanup, or another completion mode |
| External consumer fails to understand payload | Breaking changes to event contract | Version schemas, map payloads, and test contracts |
| Events do not reach broker | Missing broker-specific Modulith artifact, routing target, or broker configuration | Check externalization selection, serializers, topics/exchanges/queues, and registry |

## 11. Choosing tools by need

| Criterion | ApplicationEvent | Spring Modulith | Broker (Kafka/AMQP/JMS) |
| --- | --- | --- | --- |
| Scope | One ApplicationContext | Modules within one Spring application | Multiple processes/systems |
| Setup | Built into Spring Framework | Add Modulith dependencies | Requires broker and client integration |
| Default | Synchronous | Module listeners can be async/transaction-bound | Asynchronous over network |
| Durability | No default publication log | Event Publication Registry if persistence configured | Depends on broker durability/ack/retention |
| Retry | Custom or executor policy | API to manage publications and resubmit | Broker/client retries, DLQ, and consumer policies |
| Best suited for | Simple internal events | Modular monolith needing event contracts and listener recovery | Distributed integration, replay, and multiple independent consumers |

Do not introduce a broker merely to replace a simple internal method call. Conversely, do not use `ApplicationEvent` as a cross-process message bus or expect it to survive restarts.

## 12. Deployment checklist

- [ ] Events describe what happened and have clear domain names.
- [ ] Event payloads are immutable, small, and free of entity graphs/lazy references.
- [ ] Event ID, aggregate ID, and timestamp exist when tracing/idempotency is needed.
- [ ] Producers depend only on `ApplicationEventPublisher` or public module contracts.
- [ ] Decided between synchronous, transaction-bound, or async listeners.
- [ ] `@TransactionalEventListener` uses the right phase and fallback policy.
- [ ] Listeners writing to DB after commit open their own transaction if needed.
- [ ] Async executors are bounded and have error handling.
- [ ] If events must not be lost, publication registry/outbox/broker durability is in place.
- [ ] Listeners are idempotent and safe on retry.
- [ ] Cleanup/retention exists for completed publication records.
- [ ] Externalized events have schemas/versioning, routing, and data protection.
- [ ] Tests cover commit, rollback, failure, retry, and duplicates.
- [ ] Metrics/logs/traces monitor pending, failed, and completed publications.

## 13. References

- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `ApplicationListener`, `@EventListener`, synchronous/asynchronous listeners.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, transaction phases, and reactive transaction context.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): `@ApplicationModuleListener`, Event Publication Registry, retries, externalization, and testing.
- [Spring Modulith — EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html): API to persist, query, and complete publications.
- [Spring Modulith — FailedEventPublications API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/FailedEventPublications.html): resubmit failed publications.

Current Spring Modulith documentation varies in features by version branch. Publication lifecycles and `FailedEventPublications` require Modulith 2.0+; Namastack/JobRunr outbox integration was added in 2.1. Use BOM/dependency versions compatible with Spring Boot and check the API for your project's version before implementing.
