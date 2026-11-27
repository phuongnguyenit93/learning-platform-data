# Domain Events After Mutations in Spring for GraphQL

A GraphQL mutation typically changes business state—such as placing an order, capturing a payment, or updating a profile. Once the change is successfully saved, the application may need to notify other components: send an email, update a read model, publish a message to a broker, or notify clients watching a subscription.

Domain events describe a business fact that has occurred. When a mutation executes inside a transaction, events must be handled in accordance with whether the transaction committed or rolled back. Spring provides **ApplicationEventPublisher** to publish in-application events and **@TransactionalEventListener** to bind listeners to a transaction phase. When publishing messages to external systems where events must not be lost if the process stops, consider a **Transactional Outbox**.

## 1. What Is a Domain Event?

A domain event is an event describing a business fact that has occurred, typically named in the past tense:

- `OrderPlaced`: an order was created.
- `PaymentCaptured`: a payment was recorded.
- `AccountEmailChanged`: an account's email changed.
- `BookPublished`: a book was published.

An event describes what happened, not a command instructing another component to do something. For example, `OrderPlaced` describes that an order was created; `SendOrderEmail` is a command or a listener's action.

A well-designed domain event typically:

- Is immutable after creation.
- Contains the IDs and minimal data needed for consumers to process it.
- Carries a unique event ID for tracing and deduplication.
- Includes a timestamp and, when needed, aggregate ID/version.
- Has no dependency on GraphQL request objects or HTTP contexts.
- Does not carry managed JPA entities or objects with lazy relationships.

Example:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        Long orderId,
        String customerId,
        Instant occurredAt) {
}
~~~

An event is a fact. Consumers can use it to send notifications, update projections, or emit integration events.

## 2. Domain Events, Spring Application Events, and Integration Events

These three concepts are often used together, yet they have different scopes:

| Concept | Scope | Example |
| --- | --- | --- |
| Domain event | Business model within a bounded context | `OrderPlaced`, `PaymentCaptured` |
| Spring application event | Event dispatch mechanism within the same Spring `ApplicationContext` | `ApplicationEventPublisher.publishEvent(orderPlaced)` |
| Integration event | Message contract shared across services | `commerce.order-placed.v1` |

A domain event can be emitted via a Spring application event. Listeners within the same application receive that event and perform internal tasks.

When sending information to other services, map the domain event to an integration event with a stable schema/version. Avoid publishing internal domain classes directly onto Kafka/RabbitMQ by default, because they may contain data types, entities, or implementation details unsuitable as cross-service contracts.

## 3. Mutations as Entry Points for Business Transactions

Spring for GraphQL maps mutation root fields using `@MutationMapping`. The controller should accept input, invoke the application service, and return the GraphQL result:

~~~graphql
type Mutation {
    placeOrder(input: PlaceOrderInput!): Order!
}

input PlaceOrderInput {
    customerId: ID!
    productId: ID!
    quantity: Int!
}

type Order {
    id: ID!
    status: String!
}
~~~

Controller:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class OrderMutationController {

    private final PlaceOrderService placeOrderService;

    public OrderMutationController(PlaceOrderService placeOrderService) {
        this.placeOrderService = placeOrderService;
    }

    @MutationMapping
    public Order placeOrder(@Argument("input") PlaceOrderInput input) {
        return placeOrderService.place(input);
    }
}
~~~

The transaction is usually placed on the application service to enclose the entire use case:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public PlaceOrderService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Order place(PlaceOrderInput input) {
        Order order = Order.place(
                input.customerId(),
                input.productId(),
                input.quantity());

        Order saved = orderRepository.save(order);

        eventPublisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                saved.getId(),
                saved.getCustomerId(),
                Instant.now()));

        return saved;
    }
}
~~~

This example assumes `Order` is an aggregate root with matching accessors, the repository participates in the same transaction manager, and inputs have been validated before entering the service.

When a `@Transactional` method finishes normally, the transaction interceptor commits the transaction before returning control to the caller. If the method throws a runtime exception and the transaction is marked for rollback, data changes are rolled back according to transaction configuration.

## 4. Transaction Boundaries in GraphQL

GraphQL does not predefine transaction semantics. The application decides whether each mutation runs in its own transaction or a group of mutations share a transaction.

Spring for GraphQL recommends a transaction per controller method as a simple, clear pattern. You can place `@Transactional` on the `@MutationMapping` method or on the service it calls. The service layer is often a better fit because the same use case can be invoked from REST, a scheduler, or a message consumer.

Keep in mind:

- A mutation method's transaction ends when the method returns through the Spring transaction proxy.
- Resolving nested fields in the GraphQL response happens afterward and does not automatically belong to the mutation method's transaction.
- One GraphQL request can contain multiple top-level mutation fields; do not assume they all share a single transaction.
- When multiple steps must be atomic together, create one mutation/application service executing the full use case within a single explicit transaction.

With a service wrapped by a transaction proxy, `AFTER_COMMIT` callbacks run during transaction completion before the service call returns to the controller. If the listener runs synchronously, listener duration increases mutation latency. If the listener throws an exception, the GraphQL response may report an error even though the data committed; clients need idempotency to avoid duplicating work on retry. Use `@Async` or an outbox when decoupling execution timing, selecting the mechanism based on reliability requirements.

Do not open a long synchronous transaction across the entire GraphQL request merely to keep all field resolvers inside one transaction. Field resolution can scatter and run asynchronously, prolonging transactions and holding connections and locks longer than needed.

## 5. Why Is Publishing Events Directly Inside a Mutation Insufficient?

Calling a broker directly before the database commits can leave the two systems inconsistent:

~~~java
@Transactional
public Order place(PlaceOrderInput input) {
    Order saved = orderRepository.save(Order.place(input));

    // Risk: broker receives the event, yet the database transaction later rolls back.
    messageBroker.publish(new OrderPlacedMessage(saved.getId()));

    return saved;
}
~~~

If the message is sent successfully but the database rolls back, consumers may process an order that was never committed.

Waiting until after commit before calling the broker still leaves a gap:

1. Database commit succeeds.
2. Process stops before sending the message.
3. Data exists, yet downstream systems never receive the event.

This is the dual-write problem: a single use case must write to a database and send a message to another system, yet the two operations do not sit inside a single atomic transaction.

For internal events within the same process, `@TransactionalEventListener` waits for the transaction to complete. For cross-service messages requiring high reliability, a transactional outbox bridges the gap between database commit and publishing.

## 6. Emitting Spring Application Events with ApplicationEventPublisher

`ApplicationEventPublisher` is Spring's API for forwarding events to matching listeners:

~~~java
@Service
public class PlaceOrderService {

    private final ApplicationEventPublisher eventPublisher;

    public PlaceOrderService(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Order place(PlaceOrderInput input) {
        Order order = saveOrder(input);

        eventPublisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now()));

        return order;
    }
}
~~~

Calling `publishEvent` passes the event to Spring's event multicaster. That call itself is neither a commit operation nor a guarantee of durable storage. How listeners execute depends on multicaster configuration; the default typically invokes listeners synchronously, though applications can configure an executor or use `@Async`.

Do not treat `ApplicationEventPublisher` as a message broker. Events exist only within the current application's dispatch mechanism—they are not persisted to a database, retried after a process restart, or forwarded to other instances automatically.

## 7. Using @TransactionalEventListener with AFTER_COMMIT

If a listener must run only when the mutation commits successfully, use `@TransactionalEventListener`:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPlacedListener {

    private final OrderNotificationService notificationService;

    public OrderPlacedListener(OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        notificationService.sendOrderConfirmation(
                event.orderId(),
                event.customerId());
    }
}
~~~

`AFTER_COMMIT` is the default phase, so it can be written concisely:

~~~java
@TransactionalEventListener
public void on(OrderPlaced event) {
    notificationService.sendOrderConfirmation(event);
}
~~~

When an event is published inside an active transaction:

1. Spring registers the listener with the current transaction.
2. The listener does not run immediately at `publishEvent`.
3. If the transaction commits successfully, the listener is invoked at `AFTER_COMMIT`.
4. If the transaction rolls back, the `AFTER_COMMIT` listener is not invoked.

This suits side effects that may happen only after business data has committed, such as sending confirmation emails or refreshing internal caches.

## 8. Phases of TransactionalEventListener

The `@TransactionalEventListener` annotation supports four phases:

| Phase | Timing | Use Cases |
| --- | --- | --- |
| `BEFORE_COMMIT` | Immediately before the transaction commits | Validating or performing extra work that must finish prior to commit. |
| `AFTER_COMMIT` | After a successful commit | Sending notifications, updating caches, or emitting signals once data is persisted. |
| `AFTER_ROLLBACK` | After the transaction rolls back | Recording rollbacks, releasing external resources, or signaling failures. |
| `AFTER_COMPLETION` | After the transaction finishes, whether commit or rollback | Cleanup or auditing needed for both outcomes. |

Example of a listener recording only rollbacks:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlacementAttempted(
        UUID attemptId,
        Long orderId,
        Instant attemptedAt) {
}

@Component
public class OrderRollbackListener {

    private final AuditService auditService;

    public OrderRollbackListener(AuditService auditService) {
        this.auditService = auditService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void on(OrderPlacementAttempted event) {
        auditService.recordOrderPlacementRolledBack(event.orderId());
    }
}
~~~

In this example, `OrderPlacementAttempted` represents an attempt to place an order and is published inside the transaction. The `AFTER_ROLLBACK` listener receives that event if the transaction rolls back. Avoid naming an event `OrderPlaced` for a rolled-back attempt because the order was never actually created.

`BEFORE_COMMIT` is unsuitable for sending emails or publishing irreversible messages. If the external side effect executes and the transaction then rolls back, the system again enters an inconsistent state.

## 9. What Happens When There Is No Transaction?

By default, `@TransactionalEventListener` does not run if an event is published without an active transaction. Spring cannot guarantee the `AFTER_COMMIT` phase when there is no transaction to track.

You can enable `fallbackExecution`:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void on(OrderPlaced event) {
    // Runs via fallback when the event is published outside a transaction.
}
~~~

When `fallbackExecution` is enabled, the listener is invoked immediately via fallback if no transaction is active. However, the listener is no longer guaranteed to run after a transaction commits.

Enable `fallbackExecution` only when business logic accepts processing the event both inside and outside a transaction. If the event represents a data change that must commit before consumers run, keep the default `false` and ensure the event is always published inside an appropriate transaction.

## 10. AFTER_COMMIT Listeners Cannot Roll Back Committed Data

By the time `AFTER_COMMIT` executes, the original transaction has already committed. If the listener throws an exception, the committed transaction cannot revert to its prior state.

This creates a situation requiring careful handling:

- The order has been saved.
- The listener sending an email or calling an external service fails.
- The GraphQL mutation committed the data, even though the synchronous listener's thrown error affects the request's response.
- The client might retry the mutation and duplicate the action if the API lacks idempotency.

Therefore, listeners should classify and handle errors explicitly. For best-effort side effects, log/emit metrics and retry under a separate policy. For critical side effects that must not be lost, use an outbox rather than relying solely on in-process callbacks.

Another point: during `AFTER_COMMIT`, transaction resources may remain bound until cleanup. If the listener needs to perform additional database writes, those writes will not commit inside the already-completed transaction.

## 11. Writing to the Database from a Post-Commit Listener

If a listener must execute a new database write, call a service that opens an independent transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderProjectionService {

    private final OrderProjectionRepository repository;

    public OrderProjectionService(OrderProjectionRepository repository) {
        this.repository = repository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateProjection(OrderPlaced event) {
        repository.save(OrderProjection.from(event));
    }
}
~~~

Listener:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionService projectionService;

    public OrderProjectionListener(OrderProjectionService projectionService) {
        this.projectionService = projectionService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        projectionService.updateProjection(event);
    }
}
~~~

`REQUIRES_NEW` instructs Spring to open a new transaction for the projection write. Placing the transactional method on a separate bean ensures the call goes through a Spring proxy. Never call a `REQUIRES_NEW` method via self-invocation on the same object expecting the proxy to apply propagation.

If the projection update must eventually succeed, retries or an outbox are still required so work is not lost if the listener fails.

## 12. Asynchronous Listener Handling with @Async

A listener may perform slow work such as sending emails, making HTTP calls, or generating reports. You can combine `@Async` with `@TransactionalEventListener`:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AsyncOrderNotificationListener {

    private final OrderNotificationService notificationService;

    public AsyncOrderNotificationListener(
            OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        notificationService.sendOrderConfirmation(event);
    }
}
~~~

Enable async execution:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

When combining both annotations:

- The event becomes eligible for dispatch only after the transaction commits.
- The listener executes on the configured async executor.
- The work does not tie up the mutation thread while sending emails.
- Exceptions in the async listener cannot roll back the committed transaction.
- Executor settings, queue capacity, shutdown behavior, and error handling must be configured.

For `@Async` methods returning `void`, exceptions are not returned to the caller; configure an `AsyncUncaughtExceptionHandler` or corresponding observability so executor failures are not silently lost.

Do not default to an unbounded executor. Under load spikes, unbounded queues can grow memory indefinitely. Use bounded thread pools and queues, queue/rejection metrics, and an appropriate retry policy.

## 13. What Should an Event Payload Contain?

Listeners typically run after the original transaction ends and, if async, on another thread. Therefore, events should carry enough data for consumers to work without depending on the request's persistence context.

Recommended:

~~~java
public record OrderPlaced(
        UUID eventId,
        Long orderId,
        String customerId,
        String orderNumber,
        Instant occurredAt) {
}
~~~

Avoid passing JPA entities:

~~~java
// Avoid passing a managed entity to an async listener.
public record OrderPlaced(OrderEntity order) {
}
~~~

Reasons:

- The entity may be detached when the listener runs.
- Lazy relationships may no longer be accessible.
- Consumers might accidentally trigger database queries outside the original transaction.
- Mutable entities can change after the event was created.
- Serializing entities easily drags along large object graphs or circular references.

If the listener needs additional data, pass the ID and re-read it via a service with its own transaction. For integration events, define dedicated DTOs/contracts and expose only permitted fields.

## 14. Post-Mutation Domain Events Are Not GraphQL Subscriptions

Spring application events and GraphQL Subscriptions are two distinct mechanisms:

| Mechanism | Role |
| --- | --- |
| Domain event | Records a business fact that occurred inside the application. |
| `@TransactionalEventListener` | Runs listeners based on transaction outcomes. |
| Message broker | Distributes events across processes or services. |
| GraphQL Subscription | Maintains a response stream for clients over time. |

A listener can translate a domain event into a signal for a Subscription publisher, but that requires a separate publisher/transport. `ApplicationEventPublisher` does not automatically turn an event into a GraphQL response.

If using Reactor Sinks to bridge events into subscriptions, remember that an in-memory sink works only within one instance, offers no durable replay, and can lose events on process restarts. For multiple instances or replay requirements, use an appropriate broker/pub-sub or event store and filter data by each subscriber's permissions.

## 15. Limitations of AFTER_COMMIT When Sending External Messages

Suppose an `AFTER_COMMIT` listener sends events to Kafka:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void publish(OrderPlaced event) {
    kafkaTemplate.send("orders", event.orderId().toString(), event);
}
~~~

This approach ensures nothing is sent if the transaction rolls back. However, it still does not guarantee events cannot be lost:

1. Database commit succeeds.
2. Process crashes before the listener sends to Kafka.
3. No transaction remains recording the intent to publish.
4. Downstream never receives that event.

If the listener sends to Kafka and the process crashes before recording completion in another system, retries can also produce duplicates. `AFTER_COMMIT` callbacks are not durable queues.

Using this for best-effort notifications can be acceptable. For critical integration events, persist the event in the same database transaction as the aggregate.

## 16. Transactional Outbox Solves Dual-Write

The Transactional Outbox pattern stores events in an outbox table within the same transaction as the business change:

~~~mermaid
flowchart TD
    A[GraphQL mutation] --> B[Application service]
    B --> C[Begin database transaction]
    C --> D[Save aggregate]
    D --> E[Insert outbox event row]
    E --> F{Commit transaction}
    F -->|Rollback| G[Aggregate and outbox roll back together]
    F -->|Commit| H[Outbox row ready]
    H --> I[Outbox publisher / CDC]
    I --> J[Message broker]
    J --> K[Consumer]
    K --> L[Idempotent processing]
~~~

If the aggregate is saved successfully, the outbox row is also committed. If the transaction rolls back, both roll back together. A worker or CDC connector reads the outbox after commit and publishes events to the broker.

Example outbox table:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    aggregate_version BIGINT,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE,
    attempts INTEGER NOT NULL DEFAULT 0
);
~~~

`JSONB` and `UUID` column types depend on the database; adjust column types for your database engine.

## 17. Writing Aggregate and Outbox in the Same Transaction

The service can create the integration event and save the outbox row alongside the aggregate:

~~~java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PlaceOrderService {

    private final OrderRepository orderRepository;
    private final OutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;

    public PlaceOrderService(
            OrderRepository orderRepository,
            OutboxRepository outboxRepository,
            ObjectMapper objectMapper) {
        this.orderRepository = orderRepository;
        this.outboxRepository = outboxRepository;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public Order place(PlaceOrderInput input) {
        Order order = orderRepository.save(Order.place(input));

        OrderPlacedIntegrationEvent event = new OrderPlacedIntegrationEvent(
                UUID.randomUUID(),
                order.getId(),
                order.getCustomerId(),
                Instant.now());

        outboxRepository.save(OutboxEvent.pending(
                event.eventId(),
                "Order",
                order.getId().toString(),
                "OrderPlaced",
                serialize(event),
                event.occurredAt()));

        return order;
    }

    private String serialize(Object event) {
        try {
            return objectMapper.writeValueAsString(event);
        }
        catch (JsonProcessingException exception) {
            throw new IllegalStateException("Cannot serialize outbox event", exception);
        }
    }
}
~~~

This example assumes matching repository and entity methods. If serialization fails, the runtime exception rolls back the transaction, so no order commits without its outbox row.

This snippet uses the Jackson 2 namespace (`com.fasterxml.jackson`). If your application uses Jackson 3, use the `ObjectMapper`/serializer matching your configured dependencies; the transaction principle remains unchanged.

You can use internal domain events and map them to integration events before writing to the outbox. Store an explicit event type and schema version so consumers can handle payload evolution over time.

## 18. Outbox Publisher and Delivery Semantics

A periodic background worker or CDC connector reads unpublished outbox rows:

~~~java
import java.util.List;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

@Configuration
@EnableScheduling
class OutboxSchedulingConfiguration {
}

@Component
class OutboxPublisher {

    private final OutboxService outboxService;
    private final MessagePublisher messagePublisher;

    OutboxPublisher(OutboxService outboxService, MessagePublisher messagePublisher) {
        this.outboxService = outboxService;
        this.messagePublisher = messagePublisher;
    }

    @Scheduled(fixedDelay = 1000)
    public void publishPendingEvents() {
        List<OutboxEvent> batch = outboxService.claimPendingBatch(100);

        for (OutboxEvent event : batch) {
            try {
                messagePublisher.publish(event);
                outboxService.markPublished(event.eventId());
            }
            catch (Exception exception) {
                outboxService.recordFailure(
                        event.eventId(),
                        exception.getClass().getSimpleName());
            }
        }
    }
}
~~~

This is an illustrative skeleton. In multi-worker environments, `claimPendingBatch` must use safe locking/claiming so two workers do not process the same row simultaneously. Publishing and `markPublished` must also account for the process stopping between the two operations.

If the broker receives an event and the process crashes before marking the row published, the worker may resend the event. Thus, a transactional outbox typically provides at-least-once delivery rather than end-to-end exactly-once guarantees.

Consumers must be idempotent:

- Use unique `eventId` values.
- Store processed `eventId` values in an inbox/processed-event table.
- Enforce a unique constraint to prevent processing the same event multiple times.
- Combine persisting consumer state and marking the event processed within the same transaction.
- Execute side effects only if the event has not already been processed.

When event ordering matters, store `aggregateVersion` or a sequence number and publish in per-aggregate order. Do not rely solely on timestamps, as multiple events can share the same timestamp or workers may publish out of order.

## 19. Reactive Transactions and Transactional Events

With synchronous transactions using `PlatformTransactionManager`, Spring tracks transactions via a thread-bound context. With reactive transactions, transaction state lives in the Reactor Context rather than `ThreadLocal`.

Since Spring Framework 6.1, `@TransactionalEventListener` also supports reactive transactions. However, the transaction context must be injected into the event source. Spring provides `TransactionalEventPublisher` for this purpose.

Publisher configuration example:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.reactive.TransactionalEventPublisher;

@Configuration
public class ReactiveEventConfiguration {

    @Bean
    TransactionalEventPublisher transactionalEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        return new TransactionalEventPublisher(applicationEventPublisher);
    }
}
~~~

Reactive service:

~~~java
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class ReactivePlaceOrderService {

    private final ReactiveOrderRepository orderRepository;
    private final TransactionalEventPublisher eventPublisher;

    public ReactivePlaceOrderService(
            ReactiveOrderRepository orderRepository,
            TransactionalEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Mono<Order> place(PlaceOrderInput input) {
        return orderRepository.save(Order.place(input))
                .flatMap(order -> eventPublisher.publishEvent(
                                new OrderPlaced(
                                        UUID.randomUUID(),
                                        order.getId(),
                                        order.getCustomerId(),
                                        Instant.now()))
                        .thenReturn(order));
    }
}
~~~

Ensure the reactive method actually runs inside a transaction managed by `ReactiveTransactionManager`. Compose the `Mono` returned by `publishEvent` into the pipeline; never call `subscribe()` manually or discard the publisher `Mono`. Using `ApplicationEventPublisher` directly inside a reactive pipeline does not propagate the Reactor transaction context like thread-bound transactions do.

## 20. Testing Domain Events with Transactions

Tests should confirm that events are emitted on commit and not emitted on rollback.

Key scenarios:

| Scenario | Expected Outcome |
| --- | --- |
| Mutation/service commits successfully | `AFTER_COMMIT` listener receives the event once in synchronous tests. |
| Transaction rolls back | `AFTER_COMMIT` listener is not called. |
| Event published outside a transaction | Listener does not run when `fallbackExecution=false`. |
| `AFTER_ROLLBACK` listener | Runs when the transaction rolls back. |
| Listener writes DB post-commit | Writes inside an independent transaction when new changes must commit. |
| Outbox insert and aggregate save | Commit or roll back together. |
| Publisher sends successfully then crashes before marking | May send duplicates; consumer must be idempotent. |
| Async listener fails | Original transaction remains committed; failure must be observed and handled separately. |

Commit integration test example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class PlaceOrderEventTests {

    @Autowired
    PlaceOrderService placeOrderService;

    @Autowired
    RecordingOrderPlacedListener recordingListener;

    @Test
    void publishesEventAfterServiceTransactionCommits() {
        Order order = placeOrderService.place(validInput());

        assertThat(recordingListener.events())
                .extracting(OrderPlaced::orderId)
                .contains(order.getId());
    }
}
~~~

This test does not place `@Transactional` at the test level. The transaction opened by the service commits when the service method returns through the proxy, allowing the `AFTER_COMMIT` listener to run before the assertion. If a test class or test method carries its own transaction, the test transaction typically rolls back at the end; assertions inside the method may run before commit when the listener has not yet been invoked. In such cases, end the test transaction explicitly with `TestTransaction` or design the test without an outer transaction.

For async listeners, do not immediately assert that the event was processed; use Awaitility or test synchronization primitives to wait with a bounded timeout. Never use fixed `Thread.sleep` for synchronization.

## 21. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Listener runs even when mutation rolls back | Used `@EventListener` or sent to broker inside the transaction | Use `@TransactionalEventListener(AFTER_COMMIT)` for listeners requiring successful commit. |
| Listener never runs | Event published outside a transaction with `fallbackExecution=false` | Check transaction boundaries; enable fallback only if business rules allow. |
| Email sent while order does not exist | Side effect executed before transaction commit | Wait for `AFTER_COMMIT` or use an outbox. |
| Order committed but broker missed the event | Process stopped after commit before publishing | Use a transactional outbox or CDC. |
| Listener writes DB but changes do not commit | Wrote after `AFTER_COMMIT` into an already-completed transaction's resource | Call a service using `REQUIRES_NEW`. |
| GraphQL returns an error while order was saved | Synchronous listener threw an error after commit | Handle listener errors; use async/outbox where appropriate and design idempotent mutations. |
| Async listener lacks tenant/user context | `ThreadLocal` or request context does not propagate to executor | Include needed metadata explicitly in the event payload. |
| Event consumer processes duplicates | Broker/outbox retries can redeliver events | Use `eventId` and an idempotent consumer/inbox. |
| Events arrive out of order | Multiple workers or partitions do not preserve aggregate ordering | Use aggregate version/sequence and appropriate partitioning/claiming. |
| Test misses `AFTER_COMMIT` listener | Test runs inside a transaction that rolls back at test end | Avoid wrapping tests in a transaction or commit explicitly before asserting. |
| Reactive listener misses transaction | Relied on thread-bound assumptions in a Reactor pipeline | Use `TransactionalEventPublisher` from Spring 6.1 and propagate transaction context properly. |

## 22. Checklist for Post-Mutation Domain Events

1. Place a clear transaction boundary on the application service or mutation method.
2. Create events describing occurred business facts with immutable payloads.
3. Publish events inside the transaction persisting the aggregate.
4. Use `@TransactionalEventListener(AFTER_COMMIT)` for listeners that should run only on successful commit.
5. Understand `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.
6. Keep `fallbackExecution=false` when events strictly require a transaction.
7. Never send emails or broker messages before commit.
8. Never pass JPA entities or mutable request contexts into async listeners.
9. Use `REQUIRES_NEW` when a post-commit listener must perform new database writes.
10. Use `@Async` with proper executors and error handling for slow work.
11. Use a transactional outbox for integration events that must never be lost.
12. Design idempotent consumers and handle duplicates/ordering.
13. For reactive transactions from Spring 6.1 onward, use `TransactionalEventPublisher` to attach Reactor transaction context to events.
14. Test commit, rollback, no-transaction, async failures, and outbox retries.
15. Never confuse Spring application events with GraphQL Subscriptions or message brokers.

Domain events let a mutation announce a business fact without forcing controllers to know every component that needs to react. Transaction boundaries ensure events are handled according to proper commit outcomes; `@TransactionalEventListener` is a clean choice for in-process listeners. When events must be delivered to a broker with high reliability, a transactional outbox combined with idempotent consumers handles rollbacks, process crashes, and duplicate deliveries.

References:
- [Spring for GraphQL — Transaction Management](https://docs.spring.io/spring-graphql/reference/data.html#data.transaction)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)
- [Spring Framework — ApplicationEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [AWS Prescriptive Guidance — Transactional Outbox Pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)
