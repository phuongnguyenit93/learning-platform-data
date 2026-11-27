# Cleaning Up Events with @AfterDomainEventPublication

In Spring Data JPA, an aggregate root can record domain events generated during state changes. Spring Data provides `@DomainEvents` to retrieve the events to publish and `@AfterDomainEventPublication` to invoke a callback after those events have been published. The callback is commonly used to clear the pending event list, preventing the same event from being re-emitted on the next repository call.

`@AfterDomainEventPublication` belongs to Spring Data Commons (`org.springframework.data.domain`) and is used by Spring Data JPA when working with aggregate roots through repositories. This annotation neither publishes events on its own nor manages transactions.

> The Java snippets in this article are for Java 17+ projects using Spring Boot 3+ and `spring-boot-starter-data-jpa`. They illustrate classes to integrate into an application, not standalone programs that can be run directly with `javac`/`java`.

## 1. Roles of @DomainEvents and @AfterDomainEventPublication

An aggregate root can produce an event when a business action changes its state. For example, when an order transitions from `DRAFT` to `CONFIRMED`, the aggregate can record `OrderConfirmedEvent` so other components can update indexes, send notifications, or build read models.

Spring Data provides two cooperating annotations:

- `@DomainEvents` marks a method on an aggregate root that returns a single event or a collection of events to publish. This method takes no parameters.
- `@AfterDomainEventPublication` marks a callback invoked after Spring Data has published all events retrieved from the aggregate. The callback typically clears the sent event list.

Overview flow:

1. A business action on the aggregate creates an event and adds it to a pending list.
2. The application calls a Spring Data-supported repository method to publish domain events.
3. Spring Data invokes the `@DomainEvents` method and publishes the events as Spring application events.
4. After publishing all events, Spring Data invokes the `@AfterDomainEventPublication` method.
5. The aggregate removes the published events from its pending list.

The callback allows the aggregate to clean up its internal event state. Without clearing the list, a subsequent `save()` call may re-publish old events if the aggregate still holds them.

## 2. Manual setup on an aggregate root

The example below models an order that can transition from draft to confirmed. The event list is temporary in-memory data, so it is marked `@Transient` so JPA does not map it to a column or database relation.

**Event — `OrderConfirmedEvent.java`:**

```java
import java.time.Instant;

public record OrderConfirmedEvent(
        String orderNumber,
        Instant occurredAt) {
}
```

**Aggregate root — `PurchaseOrder.java`:**

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Objects;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

@Entity
@Table(name = "purchase_order")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String orderNumber;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status = OrderStatus.DRAFT;

    @Transient
    private final List<Object> pendingEvents = new ArrayList<>();

    protected PurchaseOrder() {
        // JPA requires a no-arg constructor.
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = Objects.requireNonNull(orderNumber);
    }

    public void confirm() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException(
                    "Only orders in DRAFT status can be confirmed");
        }

        status = OrderStatus.CONFIRMED;
        pendingEvents.add(
                new OrderConfirmedEvent(orderNumber, Instant.now()));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(pendingEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        pendingEvents.clear();
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

**Enum — `OrderStatus.java`:**

```java
public enum OrderStatus {
    DRAFT,
    CONFIRMED
}
```

In the example:

- `confirm()` checks business preconditions, changes the state, and records an event.
- `domainEvents()` returns an unmodifiable copy of the event list. Spring Data reads this list to publish.
- `clearDomainEvents()` is annotated with `@AfterDomainEventPublication` and clears the list after publication completes.
- `pendingEvents` is annotated with `@Transient` because this list is only a temporary event queue inside the aggregate.

Using `List.copyOf()` prevents readers from mutating the internal list directly. If the application needs to support a specific event type, `Object` can be replaced with a common interface type such as `DomainEvent`.

## 3. Repository triggers event publication

Spring Data publishes domain events when repository methods taking an aggregate root as an argument are called. The Spring Data JPA documentation lists methods such as `save(…)`, `saveAll(…)`, `delete(…)`, `deleteAll(…)`, `deleteAllInBatch(…)`, and `deleteInBatch(…)`.

Example repository:

```java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
```

The service modifies the aggregate and calls `save()` so Spring Data processes the events:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void confirmOrder(String orderNumber) {
        PurchaseOrder order = repository.findByOrderNumber(orderNumber)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.confirm();

        // save() triggers Spring Data's domain event publication mechanism.
        repository.save(order);
    }
}
```

When `repository.save(order)` is invoked, Spring Data finds the `@DomainEvents` method, publishes the events, and then invokes the `@AfterDomainEventPublication` callback. For a managed entity, JPA can still persist changes via dirty checking upon transaction flush/commit; calling `save()` here also serves as the trigger point for Spring Data's domain event mechanism.

### Why is deleteById not in the list?

`deleteById(id)` does not accept an aggregate root as an argument. Spring Data may execute the deletion via a query without loading the aggregate instance, so there is no object from which to read the event list or invoke the callback. If you need to emit domain events tied to deletion, load the aggregate, perform the appropriate business action, and call a repository method that accepts the aggregate instance.

With batch delete methods, check the exact overload being used and consider the semantics of bulk deletes. Bulk operations may bypass JPA lifecycle callbacks, ORM cascading, and persistence context synchronization differently from deleting entities one by one. Spring Data repository support for publishing domain events does not change these bulk DML limitations.

## 4. Using AbstractAggregateRoot to reduce boilerplate

Spring Data provides the `AbstractAggregateRoot` utility class in `org.springframework.data.domain`. This class already implements event storage, exposes events via `@DomainEvents`, and clears the list via an `@AfterDomainEventPublication` callback.

An aggregate can extend this class and call `registerEvent()` when raising an event:

```java
import java.time.Instant;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
public class Shipment extends AbstractAggregateRoot<Shipment> {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String trackingCode;

    private boolean dispatched;

    protected Shipment() {
    }

    public Shipment(String trackingCode) {
        this.trackingCode = trackingCode;
    }

    public void dispatch() {
        if (dispatched) {
            throw new IllegalStateException("Shipment has already been dispatched");
        }

        dispatched = true;
        registerEvent(
                new ShipmentDispatchedEvent(trackingCode, Instant.now()));
    }
}
```

Corresponding event:

```java
import java.time.Instant;

public record ShipmentDispatchedEvent(
        String trackingCode,
        Instant occurredAt) {
}
```

`registerEvent(event)` adds the event to the internal list and returns the registered event. `andEvent(event)` also registers the event but returns the aggregate to enable method chaining. When the repository publishes events, `AbstractAggregateRoot` automatically invokes the cleanup callback.

Choose an event management approach suited to your aggregate model:

- Implement `@DomainEvents` and `@AfterDomainEventPublication` directly when you need to customize the event list or cleanup logic.
- Extend `AbstractAggregateRoot` when you want to use Spring Data's built-in registration and cleanup mechanism.

There is no need to declare a parallel event list when already using `AbstractAggregateRoot`.

## 5. Callback execution time vs. transaction commit time

This is the most common source of confusion: `@AfterDomainEventPublication` is called after Spring Data publishes the events, **not when the database transaction has committed**.

For example, in a service with `@Transactional`:

1. The service loads the aggregate inside the transaction.
2. The aggregate changes state and registers an event.
3. The service calls repository `save()`.
4. Spring Data publishes the event and calls the cleanup callback.
5. Only afterward does the service method finish and the transaction commit.

Therefore, a regular listener using `@EventListener` can process the event while the originating transaction has not yet committed. If the transaction subsequently rolls back, the listener may already have performed an external side effect even though the business data was not committed.

If a listener should run only when the transaction succeeds, use `@TransactionalEventListener`:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        // Process only after the event-publishing transaction commits successfully.
        System.out.println("Order confirmed: " + event.orderNumber());
    }
}
```

`AFTER_COMMIT` is the default phase of `@TransactionalEventListener`. You can also choose `BEFORE_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION` depending on your goal. If no transaction is active, a transactional listener is not invoked by default; `fallbackExecution = true` can change that behavior when truly appropriate.

The event cleanup callback still runs right after Spring Data publishes events into the application event mechanism. It does not wait for transaction commit and does not prove that all listeners have finished processing. If a listener runs asynchronously, the callback is not a signal confirming that the async work has finished either.

## 6. Does clearing the list guarantee durable event delivery?

No. The event list in an aggregate is typically only transient in-memory state. `@AfterDomainEventPublication` prevents re-emitting already published events from the same list on the next save, but it does not turn events into durably persisted data.

Consider this important scenario:

- The service registers an event and calls `repository.save()`.
- Spring Data publishes the event and the callback clears the event list.
- Afterward, the database transaction rolls back.

The event list on the object has already been cleared, even though the data was not committed. Therefore, do not rely on this list as a queue that can be recovered after a rollback. With a `@TransactionalEventListener(AFTER_COMMIT)` listener, the listener will not handle the event when the transaction rolls back, yet the cleanup callback itself is still not a retry mechanism.

If you need to guarantee message delivery to a broker or external system even if the application stops between commit and sending the message, consider the Transactional Outbox pattern. An outbox writes events into a table in the same transaction as business data; a separate process reads unsent records and dispatches them according to a retry policy. That is a durable mechanism distinct from an aggregate's transient event list.

Events should be immutable objects carrying necessary data such as order number, change type, and timestamp. Avoid putting JPA entities or lazy proxies directly into payloads because listeners may execute after the persistence context has closed.

## 7. Testing event publication and cleanup

You can test with an integration test containing a Spring Data repository and a recording listener:

1. Create the aggregate and invoke the business action to register an event.
2. Verify that `domainEvents()` returns the event before calling the repository.
3. Call `repository.save(aggregate)` within a transaction.
4. Verify that the listener receives the right event type and payload.
5. After publication, verify that the aggregate's event list is empty.
6. Call `save()` again without registering a new event; the old event must not be re-published.
7. Test transaction rollback separately: a `@TransactionalEventListener(AFTER_COMMIT)` listener does not handle the event when the transaction rolls back.

When writing tests, ensure the aggregate is passed to a repository method that supports domain events. Simply mutating a managed entity and ending the transaction without calling a publication-triggering repository method is not a valid way to test this mechanism.

## 8. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Events are published repeatedly across multiple saves | Callback does not clear the event list | Implement `@AfterDomainEventPublication` to clear events |
| Callback does not run | Aggregate is not passed through a supported repository method or method annotation is not detected | Verify `@DomainEvents`, the repository method, and how it is called |
| Event is not published when calling `deleteById()` | Method only takes an ID, with no aggregate instance to read events from | Load the aggregate and call a repository method accepting the instance if business logic requires an event |
| Listener runs even though transaction later rolls back | Using regular `@EventListener` inside a transactional flow | Use `@TransactionalEventListener(AFTER_COMMIT)` when processing only after commit |
| Listener does not run without a transaction | Transactional listener requires a transaction for the chosen phase | Invoke inside a transaction or consider `fallbackExecution` |
| Event lost after rollback and retry | Callback already cleared the list after publication; the list is not a durable outbox | Re-register the event in business logic or use a Transactional Outbox |
| Listener receives a detached entity or hits lazy loading error | Payload contains an entity/proxy instead of standalone event data | Use immutable events with IDs or required data |
| Assuming callback runs after async listeners finish | Confusing publication with completion of processing | Manage acknowledgments and retries separately for async consumers |

## 9. Implementation checklist

- Aggregate registers events at the exact point business state changes.
- `@DomainEvents` method takes no parameters and returns an event or collection of events.
- Temporary event list is not mapped by JPA as persistent data.
- `@AfterDomainEventPublication` callback clears published events properly.
- Service calls a publication-supporting repository method such as `save()` or `saveAll()`.
- Listeners that should run only after commit are annotated with `@TransactionalEventListener` with the appropriate phase.
- Do not treat the event cleanup callback as proof that the transaction committed or that events were durably processed.
- For integrations requiring reliable delivery, evaluate a Transactional Outbox along with retry and idempotency policies.
- Integration tests verify publication, cleanup, no duplicate emission, and rollback behavior.

`@AfterDomainEventPublication` is a small but important extension point in Spring Data's domain event lifecycle. Use the callback to clean up the event list after publication, use `@TransactionalEventListener` when binding handling to transaction outcomes, and use an Outbox when durable reliability is needed for integration messages.

## References

- [Spring Data JPA — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/jpa/reference/4.0/repositories/core-domain-events.html)
- [Spring Data Commons — AfterDomainEventPublication API](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/domain/AfterDomainEventPublication.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Data Commons — AbstractAggregateRoot source](https://github.com/spring-projects/spring-data-commons/blob/main/src/main/java/org/springframework/data/domain/AbstractAggregateRoot.java)