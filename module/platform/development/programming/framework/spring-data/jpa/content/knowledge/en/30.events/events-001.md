# Publishing Events from Aggregates with @DomainEvents

In Domain-Driven Design (DDD), an aggregate root is the entry point for changing the state of an aggregate. When a meaningful business state change occurs, the aggregate can record a domain event, such as `OrderConfirmed` or `PaymentReceived`. Spring Data provides `@DomainEvents` to automatically publish recorded events when the application invokes supported repository methods.

This mechanism lets an aggregate describe business events without having to locate and invoke each listener itself. Spring Data feeds the events into Spring's application event mechanism; other beans can receive the events using `@EventListener` or `@TransactionalEventListener`.

## 1. Domain events and aggregate roots

A domain event is an event that has occurred in the business domain. Event names are typically phrased in the past tense:

- `OrderPlaced`: the order has been created.
- `OrderConfirmed`: the order has been confirmed.
- `PaymentReceived`: the payment has been recorded.
- `InventoryReserved`: the inventory has been reserved.

A domain event differs from a command. A command asks the system to perform something, for example `ConfirmOrder`; a domain event notifies that the confirmation has occurred, for example `OrderConfirmed`.

An aggregate root is responsible for enforcing invariants and modifying the aggregate's state. When a business method completes a valid transition, the aggregate records the corresponding event. The repository serves as the integration point for Spring Data to collect and publish those events.

An event should contain the data consumers need, typically the aggregate ID, the timestamp of occurrence, and immutable business values. Avoid passing an entire JPA entity or lazy proxy into an event because listeners may execute after the persistence context has closed or the transaction has completed.

## 2. The two core annotations

### @DomainEvents

`@DomainEvents` marks a method on an aggregate root so Spring Data can retrieve the events to publish.

The annotated method:

- Takes no parameters.
- May return a single event or a collection of events.
- Is invoked by Spring Data when a supported repository method is executed with the corresponding aggregate root.

Example:

```java
@DomainEvents
public Collection<Object> domainEvents() {
    return events;
}
```

### @AfterDomainEventPublication

`@AfterDomainEventPublication` marks a callback invoked after Spring Data has published all events retrieved from the aggregate. The callback is typically used to clear the published events from the internal list.

```java
@AfterDomainEventPublication
public void clearDomainEvents() {
    events.clear();
}
```

This callback is tied to publishing events into the Spring application event mechanism. It does not mean the database transaction has committed. If you need to execute listener logic based on commit/rollback outcomes, use `@TransactionalEventListener`.

## 3. Using AbstractAggregateRoot to manage events

Spring Data provides the `AbstractAggregateRoot` utility class in the `org.springframework.data.domain` package. An aggregate can extend this class to register events without manually writing the list, the `@DomainEvents` method, and the cleanup callback.

Useful methods:

- `registerEvent(event)`: adds an event to the pending publication list and returns the event itself.
- `andEvent(event)`: adds an event and returns the aggregate to support method chaining.
- `andEventsFrom(aggregate)`: adds events from another aggregate.
- `domainEvents()`: the method annotated with `@DomainEvents`, providing the list of events.
- `clearDomainEvents()`: the callback annotated with `@AfterDomainEventPublication`, clearing the list after publication.

The example below uses a Java 17 record to represent an immutable event:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID orderId,
    Instant occurredAt
) {}
```

Aggregate root:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;

import java.util.UUID;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private UUID id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public static PurchaseOrder create() {
        PurchaseOrder order = new PurchaseOrder();
        order.id = UUID.randomUUID();
        order.status = OrderStatus.DRAFT;
        return order;
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                "Only a draft order can be confirmed"
            );
        }

        status = OrderStatus.CONFIRMED;
        registerEvent(new OrderConfirmed(id, java.time.Instant.now()));
    }

    public UUID getId() {
        return id;
    }
}
```

`OrderStatus` is a domain enum, for example having values `DRAFT` and `CONFIRMED`. The code above is an aggregate illustration; in a real project you need to add fields, constructors, and mappings matching your schema.

The key point is that the event is registered only after business rules allow the state transition. If `confirm()` fails because the state is invalid, the aggregate does not emit `OrderConfirmed`.

## 4. The repository as the trigger for event publication

Repository managing the aggregate root:

```java
import java.util.UUID;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
```

When a supported Spring Data repository method is called, the event publishing mechanism inspects the passed aggregate roots, invokes the `@DomainEvents` method, publishes the events, and invokes the `@AfterDomainEventPublication` callback once publication finishes.

The repository methods listed in the Spring Data documentation include:

- `save(aggregate)` and `saveAll(aggregates)`.
- `delete(aggregate)` and `deleteAll(aggregates)`.
- `deleteAllInBatch(aggregates)` and `deleteInBatch(aggregates)` for overloads that accept aggregate instances.

Passing an aggregate instance is an important condition. `deleteById(id)` is not in the list because the repository may delete via a query without loading the aggregate root. Custom bulk query methods such as `@Query("update ...")` or `@Modifying` also do not look up aggregates automatically to emit events. Operations that do not receive aggregate instances cannot rely on this mechanism to collect domain events.

Example service modifying an aggregate and saving it via the repository:

```java
import java.util.UUID;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public UUID confirm(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
            .orElseThrow(() -> new IllegalArgumentException(
                "Order not found: " + orderId
            ));

        order.confirm();

        // The save call provides the aggregate to the DomainEvents mechanism.
        orders.save(order);

        return order.getId();
    }
}
```

In this example:

1. The service loads the aggregate root.
2. The business method `confirm()` checks invariants, updates the state, and registers `OrderConfirmed`.
3. `orders.save(order)` triggers Spring Data's event publication mechanism.
4. Spring Data retrieves the event from the aggregate and publishes it into the Spring application event mechanism.
5. The aggregate's callback clears the published event according to the `AbstractAggregateRoot` mechanism.

For an entity already managed within a JPA transaction, field changes may already be detected by dirty checking without calling `save()` from a JPA perspective. However, if you want to trigger Spring Data's domain event publication mechanism, call the appropriate repository method with the aggregate instance. Do not assume that merely letting Hibernate flush will publish the events.

## 5. Receiving events with a Spring listener

Events are published by Spring Data as application events. A bean can receive an event using `@EventListener`:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderEventLogger {

    @EventListener
    public void onOrderConfirmed(OrderConfirmed event) {
        System.out.println(
            "Order confirmed: " + event.orderId()
        );
    }
}
```

With the default Spring configuration, application event listeners are invoked synchronously on the publishing thread. Therefore, the listener may execute right inside the repository call, before the outer transaction completes. If the listener throws an exception, the exception can propagate back through the publishing flow and cause the transaction to roll back depending on rollback rules.

You can use `@Async` for asynchronous processing once async processing is configured. In that case, the listener runs on another thread and does not automatically share the publishing thread's transaction or persistence context. Do not use async if the listener needs to read uncommitted state or participate in the same service transaction.

## 6. Choosing execution timing with @TransactionalEventListener

In transactional business logic, when a listener runs can matter. Spring Framework provides `@TransactionalEventListener` to bind event handling to a transaction phase.

Example of sending a notification after an order has committed:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void sendConfirmation(OrderConfirmed event) {
        // Send an email or invoke a notification service.
    }
}
```

Commonly used phases:

| Phase | Timing | Purpose |
|---|---|---|
| `BEFORE_COMMIT` | Right before the transaction commits | Validate or perform work that must complete before commit |
| `AFTER_COMMIT` | After a successful commit; this is the default | Send notifications or perform side effects only once data has committed |
| `AFTER_ROLLBACK` | After the transaction rolls back | Record or handle a rollback scenario |
| `AFTER_COMPLETION` | After the transaction completes, regardless of commit or rollback | Clean up or run general post-transaction handling |

If there is no active transaction, `@TransactionalEventListener` is not invoked by default. The `fallbackExecution = true` attribute allows the listener to run even without a transaction, but should only be enabled when business requirements truly accept that case.

### Distinguishing @EventListener and @TransactionalEventListener

- `@EventListener` handles the event when Spring publishes it. With the default multicaster, the listener runs synchronously at that moment.
- `@TransactionalEventListener` waits for the specified phase. The default is `AFTER_COMMIT`, so the listener handles the event only if the transaction commits successfully.

Choose `@EventListener` when you want synchronous processing directly inside the business flow and accept that the listener affects the call outcome. Choose `@TransactionalEventListener(AFTER_COMMIT)` when side effects must occur only after data has committed, such as sending emails, webhooks, or updating a search system.

Note for post-commit listeners: the original transaction has already completed. Transactional resources may still be accessible during the callback, but database changes made at that point are not committed under the finished transaction. If the listener needs to write to the database, call a service that opens a new transaction, typically using `Propagation.REQUIRES_NEW`.

## 7. Event lifecycle and guarantee limits

### The cleanup callback is not a commit confirmation

`@AfterDomainEventPublication` is called after events have been passed to Spring's publication mechanism. When using `AbstractAggregateRoot`, the event list is cleared in this callback. That moment may still be before the outer transaction commits.

Therefore, do not interpret the callback as "the event has been processed successfully after data committed." For example, a `@TransactionalEventListener(AFTER_COMMIT)` may not even have run yet when the callback clearing the event list is invoked.

### Spring application events are not a durable queue

Domain events are held in the aggregate's memory and published within the current process. This mechanism does not automatically provide:

- Durable storage of events in a database.
- Automatic retries when a listener or external system fails.
- Exactly-once delivery guarantees across multiple systems.
- Recovery of lost events when the application stops abruptly.

If a transaction rolls back after events have been published and the aggregate has cleared its event list, the events do not automatically reappear when the application restarts. An `AFTER_COMMIT` listener will not run for a rolled-back transaction, yet the event list on the held object may already have been cleared.

For critical integrations requiring no message loss, consider the Transactional Outbox pattern: persist aggregate changes and an outbox record within the same database transaction; a separate publisher reads the outbox and sends messages to the broker, then marks them processed. Consumers should be idempotent because distributed systems generally need to tolerate redelivery.

## 8. Organizing events in an aggregate

Several principles help keep events maintainable:

- **Name after what happened:** use `OrderConfirmed`, not command names like `ConfirmOrder`.
- **Emit only after a valid transition:** register events after the aggregate has verified preconditions and successfully updated state.
- **Use immutable payloads:** Java records fit small events well; include only data consumers actually need.
- **Prefer IDs and business snapshots:** avoid passing JPA entities with lazy associations or mutable state.
- **Keep events scoped to the owning aggregate:** one aggregate should not emit internal events on behalf of another aggregate.
- **Make listeners idempotent when needed:** the same event may be processed again due to application-layer or integration retries.

Avoid having a listener mutate back into the aggregate that just emitted the event in a hard-to-control loop. If a new business transition is required, express it via an explicit use case and corresponding event.

## 9. Manual implementation using the two annotations

If you do not want the aggregate to extend `AbstractAggregateRoot`, you can manage the event list yourself and annotate two methods:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.List;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

public class CustomAggregate {

    private final transient List<Object> events = new ArrayList<>();

    protected void register(Object event) {
        events.add(event);
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return Collections.unmodifiableList(events);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        events.clear();
    }
}
```

The event list is transient in-memory state; the Java `transient` keyword prevents it from being serialized via Java serialization and prevents JPA from treating it as a persistent field. A practical implementation still needs to ensure the collection cannot be modified externally, events are only registered through business methods, and the callback clears the published events properly.

Choose one management approach: extend `AbstractAggregateRoot` or use the two annotations manually. There is no need to implement both mechanisms for the same event list.

## 10. Testing domain event publication

You can test two separate layers of behavior:

1. **Aggregate registers events properly:** call a valid business method and assert the aggregate exposes the expected event; call an invalid method and assert no spurious event is created.
2. **Repository triggers publication:** call `save(aggregate)` within a Spring context, register a listener or use `ApplicationEvents` in tests to assert the event was published.
3. **Cleanup callback clears the list:** after the repository publishes the event, save the aggregate again and assert the event is not re-emitted if the callback cleared the list.
4. **Transaction phase:** use an integration test to verify an `AFTER_COMMIT` listener runs only when the transaction commits and does not run on rollback.
5. **Do not confuse save with flush:** modifying an entity and only flushing the persistence context is not a repository call that triggers the `@DomainEvents` mechanism.

Unit-level aggregate test example (assuming `PurchaseOrder` is the aggregate class above):

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class PurchaseOrderTest {

    @Test
    void confirmRegistersDomainEvent() {
        PurchaseOrder order = PurchaseOrder.create();

        order.confirm();

        assertEquals(1, order.domainEvents().size());
        assertEquals(
            order.getId(),
            ((OrderConfirmed) order.domainEvents().iterator().next()).orderId()
        );
    }

    @Test
    void cannotConfirmTwice() {
        PurchaseOrder order = PurchaseOrder.create();
        order.confirm();

        assertThrows(IllegalStateException.class, order::confirm);
        assertEquals(1, order.domainEvents().size());
    }
}
```

Note that `domainEvents()` in `AbstractAggregateRoot` may be declared `protected`. If tests need access, provide a package-private or protected method on the aggregate for testing, or verify events through a listener in a Spring integration test. The test snippet above needs visibility adjusted according to your project's package structure; avoid exposing domain internals unnecessarily just for tests.

## 11. Common mistakes

- **Registering an event without calling a repository:** the event remains on the aggregate; Spring Data has no supported repository invocation to collect and publish it.
- **Using `deleteById()` and expecting aggregate events to be emitted:** the method only receives an ID and does not provide an aggregate instance to the event publishing mechanism.
- **Using bulk JPQL update/delete and expecting automatic event emission:** bulk queries operate directly against the database without going through the aggregate root; publish events explicitly or route the operation through the aggregate.
- **Forgetting to clear the event list:** the same event may be re-published on the next save/delete. Use `@AfterDomainEventPublication` or `AbstractAggregateRoot`.
- **Assuming the callback runs after commit:** the callback runs after Spring Data publishes events, not as a transaction callback. Use `@TransactionalEventListener` to bind to a transaction phase.
- **Sending email directly in a synchronous listener:** the email may already be sent even if the transaction later rolls back. Use `AFTER_COMMIT` for side effects that must only run on successful commit.
- **Assuming in-memory events are durable:** events can be lost on process crash or transaction rollback. Use an outbox when durable delivery is required.
- **Passing an entire entity into an event:** listeners can encounter lazy loading, detached entities, or read mutated state later. Prefer IDs and immutable snapshots.

## 12. Implementation workflow

1. Identify the aggregate root and business-meaningful state transitions.
2. Create immutable events named after what happened and containing the data consumers need.
3. Inside business methods, check invariants, update state, and register the event.
4. Extend `AbstractAggregateRoot` or manually implement `@DomainEvents` together with `@AfterDomainEventPublication`.
5. Call `save(aggregate)` or a supported repository method that takes the aggregate instance.
6. Write the appropriate listener: `@EventListener` for immediate handling; `@TransactionalEventListener` for transaction-phase handling.
7. If a post-commit listener needs to write to the database, open a new transaction. If durable integration with a broker or external system is needed, consider a transactional outbox.
8. Test that events are registered, published the expected number of times, cleared by the callback, and handled in the right transaction phase.

## References

- [Spring Data Commons – Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Data Commons – AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AbstractAggregateRoot.html)
- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
