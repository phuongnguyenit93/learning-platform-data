# @DomainEvents and @AfterDomainEventPublication

In **Spring Data Relational JDBC**, an aggregate root can record business events produced during state transitions. For example, when an order transitions from NEW to PAID, the business domain can produce an `OrderPaid` event so other components send notifications, update a read model, or start a follow-up workflow.

Spring Data Commons provides two annotations to support this pattern:

- **`@DomainEvents`** marks a method on the aggregate root that provides one or more domain events for Spring Data to publish.
- **`@AfterDomainEventPublication`** marks a method invoked after those events have been published. Typically used to clear pending events from the aggregate.

These two annotations keep events alongside business state changes on the aggregate, while the repository infrastructure handles publishing events when supported repository methods are invoked. They do not automatically generate events from arbitrary property changes, nor do they mean the database has committed. You must clearly understand the boundaries between business actions, repository calls, application events, and transactions.

## 1. What is a domain event?

A domain event is an object representing something meaningful that happened in the business domain. It is typically named in the past tense, such as:

- `OrderPlaced`: an order was created.
- `OrderPaid`: an order was paid.
- `InventoryReserved`: inventory was reserved.
- `CustomerAddressChanged`: a customer's address changed.
- `OrderCancelled`: an order was cancelled.

A domain event should answer the question: **What happened in the domain?**

For example, changing the `status` property from NEW to PAID is a state change. The `OrderPaid` event expresses the business meaning of that change.

```java
import java.time.Instant;

public record OrderPaid(
    Long orderId,
    Instant occurredAt
) {}
```

The event record holds the aggregate's ID and the timestamp when the event occurred. Depending on the business domain, an event may include additional data consumers need, such as a payment reference or currency. Only include information consumers actually need and that has stable meaning.

### 1.1. Domain events differ from entity lifecycle events

These two concepts are not the same:

| Domain event | Lifecycle event |
|---|---|
| Describes a business event | Describes a persistence stage |
| E.g., `OrderPaid` | E.g., `AfterSaveEvent` |
| Created when a business rule occurs | Published by Spring Data when an aggregate is saved, read, or deleted |
| Meaningful to business consumers | Usually useful for logging, technical auditing, or lifecycle integration |
| Not every save necessarily produces an event | Tied to the corresponding persistence operation |

Do not emit `OrderPaid` simply because a repository was called. An order might be saved when updating a note, address, or delivery info. Only the payment action creates the `OrderPaid` event.

### 1.2. Domain events are not a message broker

When Spring Data publishes a domain event, it publishes a Spring application event inside the application context. That does not automatically send a message to Kafka, RabbitMQ, or an external system.

A listener in the same application can receive the event. If sending to a broker is required, the application must implement the corresponding integration. If delivery must survive process crashes, consider a transactional outbox.

## 2. Role of @DomainEvents

`@DomainEvents` resides in Spring Data Commons and is placed on a method of the aggregate root.

The annotated method:

- Takes no parameters.
- Can return a single event object.
- Or return a collection of event objects.

Example:

```java
class PurchaseOrder {

    private final List<Object> domainEvents = new ArrayList<>();

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(domainEvents);
    }
}
```

When the repository infrastructure handles a repository method supporting domain event publication, Spring Data invokes this method to collect pending events to publish.

`@DomainEvents` is not placed on individual event classes. It marks **the event-providing method on the aggregate root**.

### 2.1. One event or multiple events

Can return a single event:

```java
@DomainEvents
public Object domainEvent() {
    return new OrderPaid(id, Instant.now());
}
```

Or return multiple events:

```java
@DomainEvents
public Collection<Object> domainEvents() {
    return List.copyOf(events);
}
```

Returning a collection fits when a business action emits multiple events or the aggregate accumulates multiple pending events.

Return an empty collection when there are no events to publish. Do not create dummy events just so the method always returns something.

### 2.2. Events must be recorded from domain behavior

Spring Data does not automatically infer events from property mutations. The aggregate must explicitly record events when a valid business behavior occurs.

```java
public void markPaid(Instant occurredAt) {
    if (status != OrderStatus.NEW) {
        throw new IllegalStateException("Only a NEW order can be paid");
    }

    status = OrderStatus.PAID;
    events.add(new OrderPaid(id, occurredAt));
}
```

Here, the state transition rule and event creation sit side by side. If the payment precondition is invalid, an exception is thrown before either status or events are changed.

This approach avoids having an application service guess events by diffing two reads of the object and accidentally emitting wrong events.

## 3. Role of @AfterDomainEventPublication

`@AfterDomainEventPublication` marks a method on the aggregate root. Spring Data invokes this method after all provided domain events have been published.

A common use is clearing the pending event list:

```java
@AfterDomainEventPublication
public void clearDomainEvents() {
    events.clear();
}
```

The reason to clear events is that an aggregate may be saved multiple times during the lifetime of the same object instance. If the list is not cleared, a subsequent save could re-publish old events.

Example:

```text
1. Aggregate records OrderPaid.
2. Repository saves the aggregate.
3. Spring Data collects events and publishes them.
4. @AfterDomainEventPublication runs.
5. Pending event list is cleared.
6. A later save does not re-publish the old OrderPaid.
```

### 3.1. This callback is not a transaction callback

The annotation name only states that the method runs after events have been published. It does **not** mean:

- The database transaction has committed.
- All listeners have finished processing.
- Messages were successfully delivered to a broker.
- External consumers have received the event.
- Side effects cannot fail.

`@AfterDomainEventPublication` is a callback for cleaning up event state inside the aggregate. It does not replace `@TransactionalEventListener` and is not a durable event delivery guarantee.

### 3.2. Do not clear events before providing them

If the `@DomainEvents` method returns an empty list because events were cleared before the repository call, nothing will be published.

Only clear events inside the `@AfterDomainEventPublication` method or via another deliberate mechanism. Avoid clearing the list immediately after calling the domain method that recorded the event.

## 4. Complete example with both annotations

Suppose an order has statuses NEW and PAID. Upon successful payment, the aggregate changes status and records an event.

### 4.1. Event object

```java
import java.time.Instant;

public record OrderPaid(
    Long orderId,
    Instant occurredAt
) {}
```

### 4.2. Aggregate root

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.annotation.Transient;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private OrderStatus status;

    @Transient
    private final List<Object> events = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Long id, OrderStatus status) {
        this.id = id;
        this.status = status;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only a NEW order can be paid"
            );
        }

        status = OrderStatus.PAID;
        events.add(new OrderPaid(id, Instant.now()));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(events);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        events.clear();
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

`@Transient` on the event list is critical in a manual implementation: this list is temporary in-memory state, not data to be mapped as a column or child table of the aggregate.

The example assumes the ID is already assigned when creating the aggregate. If the database only generates IDs on insert, an event created before the first save might not have an ID yet. In that case, consider application-generated IDs (such as UUID), or design events so they do not depend on a database-generated ID at the moment the domain action executes.

### 4.3. Repository

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

No event-publishing code is needed in the repository. Spring Data's repository infrastructure detects the annotated methods on the aggregate root and publishes events when supported repository methods are invoked.

### 4.4. Application service

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PaymentService {

    private final PurchaseOrderRepository repository;

    public PaymentService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void pay(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
            .orElseThrow(() ->
                new IllegalArgumentException("Order not found")
            );

        order.markPaid();

        repository.save(order);
    }
}
```

Processing flow:

1. Service loads the aggregate.
2. Aggregate validates business rules in `markPaid`.
3. Aggregate transitions state and appends `OrderPaid` to the event list.
4. Service calls `repository.save`.
5. Spring Data retrieves events from the `domainEvents` method and publishes them.
6. After publishing, Spring Data invokes `clearDomainEvents`.
7. The service transaction completes according to commit/rollback rules.

Events are produced by domain behavior; the repository is simply the trigger point for publication.

## 5. Using AbstractAggregateRoot instead of writing an event list manually

Spring Data Commons provides the convenience class `AbstractAggregateRoot`. This class already implements event collection and exposure based on `@DomainEvents` and `@AfterDomainEventPublication`.

Instead of declaring the list, getter, and clear method yourself, the aggregate can extend this class:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.domain.AbstractAggregateRoot;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private Long id;

    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(Long id, OrderStatus status) {
        this.id = id;
        this.status = status;
    }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                "Only a NEW order can be paid"
            );
        }

        status = OrderStatus.PAID;

        registerEvent(
            new OrderPaid(id, Instant.now())
        );
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }
}
```

`registerEvent` is a method provided by `AbstractAggregateRoot`. It records an event so the repository can publish it when save or delete is called with an aggregate instance.

### 5.1. registerEvent and andEvent

Two main helper methods:

| Method | Return value | Usage |
|---|---|---|
| `registerEvent(event)` | The registered event itself | When you just want to record an event |
| `andEvent(event)` | The current aggregate | When you want to chain event registration into an expression |

Example:

```java
registerEvent(new OrderPaid(id, Instant.now()));
```

Or:

```java
return andEvent(new OrderPaid(id, Instant.now()));
```

`AbstractAggregateRoot` also provides `andEventsFrom(aggregate)` to add events currently held in another aggregate to the current aggregate. Use these methods when your domain model needs to forward events intentionally.

### 5.2. When to use AbstractAggregateRoot?

This convenience class fits when:

- The aggregate root is a class that can extend a base class.
- You want to use the built-in event buffer mechanism.
- You want to avoid boilerplate managing an event list.
- You have no special requirements for how events are stored or cleared.

Using the two annotations manually fits when the aggregate already has another base class, needs custom event-buffer structures, or wants to keep the domain model independent of this helper class.

Do not both extend `AbstractAggregateRoot` and declare your own event list with the two annotations. Pick one clean implementation approach.

## 6. Which repository methods trigger domain event publication?

Spring Data ties the event publication mechanism to repository methods that receive aggregate instances. Common methods include:

| Repository method | Has aggregate instance to collect events from? |
|---|---|
| `save(aggregate)` | Yes |
| `saveAll(aggregates)` | Has the aggregates passed in |
| `delete(aggregate)` | Yes |
| `deleteAll(aggregates)` | Has the aggregates passed in |
| `deleteById(id)` | No aggregate instance passed in |
| `deleteAll()` | No list of aggregate instances passed in |

Spring Data Commons documentation explicitly notes that `deleteById` is not among methods publishing events via this mechanism, because implementations may delete by query without loading an aggregate instance. Bulk or additional methods may vary by module and version; check the contract of the version you use.

### 6.1. Why does deleteById not emit domain events automatically?

When calling:

```java
repository.deleteById(orderId);
```

The repository only receives an ID. It does not necessarily load the aggregate before deleting. Thus, there is no aggregate root object on which to invoke `@DomainEvents`.

If the business requires emitting an event such as `OrderCancelled` or `OrderDeleted` carrying data from the aggregate:

```java
PurchaseOrder order = repository.findById(orderId)
    .orElseThrow();

order.cancel();

repository.save(order);
repository.delete(order);
```

This is an illustrative example; real business domains need to decide which event fits cancellation versus deletion. If you only need to record a deletion by ID, the application service can construct and publish a separate event after enforcing necessary rules.

### 6.2. Bulk modifying queries do not emit domain events per aggregate

A bulk SQL statement like:

```java
@Modifying
@Query("""
    UPDATE purchase_orders
    SET status = 'EXPIRED'
    WHERE expires_at < :now
    """)
int expireOrders(Instant now);
```

runs directly on the database. The framework does not have each changed aggregate instance on which to invoke `@DomainEvents`. Therefore, do not expect a bulk query to automatically emit a domain event for each order.

If the business needs per-order events, design a workflow that loads and processes aggregates intentionally, or records events/outbox entries via a dedicated bulk strategy.

## 7. Events are published as Spring application events

When the repository infrastructure collects events from an aggregate, it publishes them via Spring's application event mechanism. Listeners in the same application context can receive those events.

Example:

```java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPaidLogger {

    @EventListener
    public void onOrderPaid(OrderPaid event) {
        System.out.println(
            "Order paid: " + event.orderId()
        );
    }
}
```

`@EventListener` marks a listener method for Spring application events. The parameter type tells Spring which event the listener subscribes to.

You can implement `ApplicationListener<OrderPaid>` instead of using the annotation:

```java
@Component
public class OrderPaidListener
        implements ApplicationListener<OrderPaid> {

    @Override
    public void onApplicationEvent(OrderPaid event) {
        // Handle event.
    }
}
```

Choose whichever fits your application style. Do not register listeners inside the aggregate root; the aggregate only creates and exposes events.

### 7.1. By default, event listeners can run synchronously

With the default application event multicaster configuration, listeners are usually invoked synchronously on the publishing thread. If the application configures an asynchronous executor or a listener uses `@Async`, execution differs.

Do not let listeners make HTTP calls or run long tasks on the repository save path if that prolongs transactions and holds connections unnecessarily. If a listener should only run after commit, use a transactional event listener.

## 8. Distinguishing @AfterDomainEventPublication from AFTER_COMMIT

This is the most common source of confusion.

`@AfterDomainEventPublication` is invoked after Spring Data publishes the domain events retrieved from the aggregate. `@TransactionalEventListener(phase = AFTER_COMMIT)` is invoked via transaction synchronization after the transaction commits successfully.

| Mechanism | Invocation condition | Purpose |
|---|---|---|
| `@AfterDomainEventPublication` | After events from the aggregate have been published | Clear event buffer or handle internal event state |
| `@EventListener` | When a Spring application event is published | Handle events inside the application context |
| `@TransactionalEventListener(AFTER_COMMIT)` | After transaction commit | Run side effects only once data has committed |
| Transactional outbox | Outbox record commits alongside business data | Deliver messages durably with retry support |

Example of a transactional service:

```java
@Transactional
public void pay(Long orderId) {
    PurchaseOrder order = repository.findById(orderId)
        .orElseThrow();

    order.markPaid();
    repository.save(order);

    // Transaction may still not be committed here.
}
```

Repository save triggers domain event publication. The `@AfterDomainEventPublication` method may already have cleared the event buffer while the service transaction is still open.

If a subsequent operation fails and the transaction rolls back, clearing the event buffer is not rolled back with the database. Hence, this callback cannot be treated as proof that the business action committed.

### 8.1. Process only after commit

If an event must trigger an email or call another system once the order has committed:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPaidNotificationHandler {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void sendNotification(OrderPaid event) {
        // Send notification after transaction commit.
    }
}
```

If the transaction rolls back, the AFTER_COMMIT phase listener is not invoked by default. Events published inside a transaction can be registered with transaction synchronization to run in the right phase.

If there is no active transaction, `@TransactionalEventListener` does not handle the event by default. Only enable `fallbackExecution` if the application truly intends to handle the event even without a transaction.

### 8.2. An AFTER_COMMIT listener cannot roll back the original transaction

When an AFTER_COMMIT listener runs, the transaction has already committed. If sending the email fails, the database cannot roll back the PAID status just because the email failed to send.

If retries are needed, design retries, idempotency, or a durable queue. Do not treat post-commit listener failures as errors that undo the original transaction.

## 9. Lost events problem and the Transactional Outbox

Domain events in an aggregate are normally held in memory. Spring publishing an event to the application context does not automatically persist the event to a database or broker.

There is a vulnerability window:

1. Database commits successfully.
2. Application stops before the listener sends the external message.
3. In-memory events vanish when the process terminates.
4. External consumers never receive the message.

`@TransactionalEventListener(AFTER_COMMIT)` solves the timing issue, not durable queueing.

For critical integrations, use a Transactional Outbox:

1. The aggregate performs business behavior and produces a domain event.
2. The service saves the aggregate.
3. The service writes an outbox record in the same database transaction.
4. The transaction commits both aggregate data and outbox row.
5. A worker reads unpublished records and sends them to the broker.
6. The worker marks them published or retries on failure.

Example outbox table:

```sql
CREATE TABLE outbox_events (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(150) NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP NULL
);
```

If the transaction rolls back, both the aggregate change and the outbox record roll back. If committed, the worker can resume delivering the event after the application restarts.

An outbox typically provides at-least-once delivery, not exactly-once by itself. Consumers need idempotency based on event ID or business keys.

## 10. Does @DomainEvents work when calling JdbcAggregateTemplate?

The publication mechanism is tied to the Spring Data repository proxy. When calling a supported repository method, the repository interceptor collects events exposed by the aggregate root and publishes them.

`JdbcAggregateTemplate` is a direct template API, not a repository proxy. Do not assume that calling:

```java
aggregateTemplate.save(order);
```

will trigger the same `@DomainEvents` and `@AfterDomainEventPublication` mechanism as a repository save.

If a use case uses the template directly, you can publish the event explicitly via `ApplicationEventPublisher` after the template operation runs inside the transaction:

```java
@Transactional
public void pay(Long orderId) {
    PurchaseOrder order = aggregateTemplate.findById(
        orderId,
        PurchaseOrder.class
    );

    order.markPaid();

    PurchaseOrder saved = aggregateTemplate.update(order);

    publisher.publishEvent(
        new OrderPaid(saved.getId(), Instant.now())
    );
}
```

If the event must be handled after commit, listeners should still use `@TransactionalEventListener(AFTER_COMMIT)`. If durable delivery is required, write an outbox row in the same transaction.

Another option is using a repository for use cases needing built-in event publication. The key is choosing one explicit publication point, avoiding both repository auto-publishing and manual `publishEvent` calls for the same event.

## 11. Event buffers and design considerations

### 11.1. The event buffer is not persistence data

The list of pending events is temporary in-memory state of the aggregate. With a manual implementation, mark it `@Transient` so Spring Data JDBC does not try to map it as a database property.

With `AbstractAggregateRoot`, the base class manages the event buffer. If writing your own mechanism, ensure event-tracking fields are not mapped as aggregate data.

### 11.2. Do not retain old events across multiple use cases

After events are published, `@AfterDomainEventPublication` should clear the buffer. That prevents old events from being re-published on a subsequent save.

If an aggregate is reused in memory across multiple actions, keep clear track of which events belong to which action. Typically, each aggregate instance should only be used within a controlled use-case scope.

### 11.3. Do not use events to replace domain data

An event is a record of what happened, not a substitute for current aggregate state. Consumers needing the latest state can load the aggregate via a repository if business logic requires it.

A good event usually carries a sufficient snapshot for consumers, yet should not stuff the entire aggregate into the event if that creates tight coupling.

### 11.4. Name events in the past tense

The name `OrderPaid` states a fact that happened. The name `PayOrder` sounds more like a command: it asks the system to perform an action.

Distinction:

| Command | Domain event |
|---|---|
| `PayOrder` | `OrderPaid` |
| `PlaceOrder` | `OrderPlaced` |
| `CancelOrder` | `OrderCancelled` |
| `ReserveInventory` | `InventoryReserved` |

Commands can fail or be rejected. Events should only be recorded after the corresponding business action succeeds in the domain model.

### 11.5. Events should be immutable

Java records are a great choice for many events:

```java
public record OrderPaid(
    Long orderId,
    Instant occurredAt,
    String paymentReference
) {}
```

Once an event is published, a consumer should not mutate the event object and affect other consumers. Immutability makes events easy to test, log, and serialize into messages.

## 12. Handling events with saveAll and deleting multiple aggregates

A repository method accepting multiple aggregates can trigger event publication for the aggregates passed in, according to the contract of the Spring Data module and version in use.

Example:

```java
repository.saveAll(orders);
```

If each aggregate has its own event buffer, each aggregate can supply its events. Spring Data publishes the events supplied by the aggregates and then invokes the corresponding event-clearing callbacks.

For collection deletes:

```java
repository.deleteAll(orders);
```

Because the repository receives aggregate instances, it can collect domain events from those instances via the supported event publication mechanism.

Conversely:

```java
repository.deleteAll();
repository.deleteAllById(ids);
```

do not supply a list of aggregate instances to this mechanism. If the business requires domain events for each deleted aggregate, load and process the aggregates or design a dedicated bulk business event.

For large batches, avoid loading every aggregate solely to emit events if writing an outbox or processing in bulk is more efficient. Weigh query cost, memory, and business audit/event requirements.

## 13. Testing @DomainEvents and @AfterDomainEventPublication

Three behaviors should be tested:

1. The aggregate only creates events when valid business behavior occurs.
2. Appropriate repository save/delete methods cause events to be published.
3. The event buffer is cleared after publication completes.

### 13.1. Unit testing domain behavior

```java
@Test
void payingOrderRegistersAnEvent() {
    PurchaseOrder order = new PurchaseOrder(
        42L,
        OrderStatus.NEW
    );

    order.markPaid();

    assertThat(order.domainEvents())
        .singleElement()
        .isInstanceOf(OrderPaid.class);
}
```

If using `AbstractAggregateRoot`, you can test via an appropriate test/package-private accessor or test events via integration tests through the repository.

### 13.2. Verifying repository publication

An integration test can register a test listener to record events:

```java
@Component
class TestOrderEventListener {

    private final List<OrderPaid> received = new CopyOnWriteArrayList<>();

    @EventListener
    public void on(OrderPaid event) {
        received.add(event);
    }

    public List<OrderPaid> receivedEvents() {
        return List.copyOf(received);
    }

    public void clear() {
        received.clear();
    }
}
```

Test:

```java
@Test
void repositorySavePublishesAggregateEvents() {
    PurchaseOrder order = repository.findById(42L).orElseThrow();

    order.markPaid();
    repository.save(order);

    assertThat(testListener.receivedEvents())
        .extracting(OrderPaid::orderId)
        .containsExactly(42L);
}
```

This test illustrates publication through the repository. Database fixtures and initial state must ensure order 42 starts in NEW status.

### 13.3. Verifying the event buffer is cleared

With a manual implementation:

```java
order.markPaid();

assertThat(order.domainEvents()).hasSize(1);

order.clearDomainEvents();

assertThat(order.domainEvents()).isEmpty();
```

In an integration test, you can verify that a second save on the same aggregate instance does not re-publish old events after the buffer-clearing callback has run.

### 13.4. Testing transaction rollback

Register a `@TransactionalEventListener(AFTER_COMMIT)` and run a use case inside a rolled-back transaction:

- The event may have been published by the repository.
- `@AfterDomainEventPublication` may have cleared the event buffer.
- The AFTER_COMMIT listener is not invoked because the transaction did not commit.

This test demonstrates that publication, clearing the buffer, and committing are three distinct moments.

## 14. Common mistakes

| Symptom | Cause | How to fix |
|---|---|---|
| Saving aggregate produces no events | Domain behavior did not register events or repository method is unsupported | Check event buffer and save/delete methods |
| Event is re-emitted on a later save | Event buffer was not cleared | Use `@AfterDomainEventPublication` |
| `deleteById` emits no events | Only ID passed, no aggregate instance | Load aggregate or publish event explicitly |
| Every save emits `OrderPaid` | Creating events inside getters or the wrong callback | Register events inside domain behavior during state transition |
| Event listener runs even though transaction rolled back | Using standard `@EventListener` in a transaction | Use `@TransactionalEventListener(AFTER_COMMIT)` for post-commit side effects |
| Thinking `@AfterDomainEventPublication` runs after commit | Confusing publication callback with transaction phase | Distinguish buffer-clearing callback from `AFTER_COMMIT` |
| Event list is persisted to database | Event buffer is not marked transient | Use `@Transient` for manually managed event fields |
| `JdbcAggregateTemplate.save` does not publish like repository | Template does not go through repository event interceptor | Publish explicitly or use a repository |
| Bulk update has no per-row events | Query updates database directly without aggregate instances | Design events/outbox for bulk operations |
| Events sent to broker are lost on app crash | Application events exist only in-process | Use a transactional outbox |
| Consumer processes duplicate messages | Retries or multiple deliveries | Design idempotent consumers |
| Event lacks aggregate ID | ID is only generated by the database after insert | Use application IDs or design events for that timing |
| Domain event contains the whole aggregate | Event is tightly coupled to the persistence model | Create a dedicated event payload with only needed fields |

## 15. Practice exercises

**Exercise 1.** Where is `@DomainEvents` placed?

*Answer:* On a method of the aggregate root. The method takes no parameters and returns a single event or a collection of events.

**Exercise 2.** What is `@AfterDomainEventPublication` used for?

*Answer:* Marks a method called after events have been published. Typically used to clear the event buffer to avoid duplicate publication.

**Exercise 3.** When should an aggregate create `OrderPaid`?

*Answer:* When valid payment behavior actually transitions the order to PAID status, not every time `repository.save` is called.

**Exercise 4.** Does `deleteById` automatically publish domain events from the aggregate?

*Answer:* Not via this standard mechanism, because the repository only receives an ID and may not load the aggregate instance. You must load the aggregate or publish a separate event according to business rules.

**Exercise 5.** Does `@AfterDomainEventPublication` mean the database has committed?

*Answer:* No. It is only called after publication. The service transaction may still be open and may roll back.

**Exercise 6.** What should a listener that must only send emails after commit use?

*Answer:* `@TransactionalEventListener(phase = AFTER_COMMIT)`. If message delivery must survive crashes, consider an outbox.

**Exercise 7.** What does `AbstractAggregateRoot` provide?

*Answer:* It provides an event buffer and `registerEvent`, `andEvent`, and `andEventsFrom` methods along with event exposure and clearing built on the two annotations.

**Exercise 8.** Why should a manual event buffer be marked `@Transient`?

*Answer:* It is temporary in-memory state, not a property for Spring Data JDBC to persist into the schema.

**Exercise 9.** Does calling `JdbcAggregateTemplate.save` directly guarantee triggering `@DomainEvents` publication?

*Answer:* Do not assume so. The built-in mechanism relies on the repository proxy. When using the template directly, publish events explicitly or use an outbox.

## 16. Things to remember

- `@DomainEvents` marks an aggregate root method returning one event or a collection of events; the method takes no parameters.
- Events must be recorded from valid business behavior, not emitted automatically just because properties changed or a repository saved.
- `@AfterDomainEventPublication` runs after events are published and is typically used to clear the event buffer.
- This callback is not a transaction callback and does not prove the database committed.
- `AbstractAggregateRoot` is a built-in helper class for managing the event buffer via `registerEvent`, `andEvent`, and `andEventsFrom`.
- Spring Data publication is tied to repository methods accepting aggregate instances such as save/delete; `deleteById` has no aggregate from which to collect events.
- Domain events are published as Spring application events inside the application context; they do not automatically send messages to a broker.
- Use `@TransactionalEventListener(AFTER_COMMIT)` when consumers must only process after commit.
- For messages requiring durability guarantees, use a transactional outbox and idempotent consumers.
- When managing an event buffer manually on an aggregate, mark the field `@Transient` so it does not become persistence data.
- When using `JdbcAggregateTemplate` directly, do not assume the repository event publication interceptor will run.

### Official references

- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): rules for using `@DomainEvents` and `@AfterDomainEventPublication`.
- [Spring Data Commons — AbstractAggregateRoot API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/AbstractAggregateRoot.html): `registerEvent`, `andEvent`, `andEventsFrom`, and the event buffer.
- [Spring Data Commons — EventPublishingRepositoryProxyPostProcessor API](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/repository/core/support/EventPublishingRepositoryProxyPostProcessor.html): repository proxy mechanism publishing events from aggregate roots.
- [Spring Framework — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): application event publisher and listeners in the Spring context.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` and transaction phases.
- [Spring Data Relational — JDBC Reference](https://docs.spring.io/spring-data/relational/reference/jdbc.html): repositories and aggregate persistence in Spring Data JDBC.

When implementing, clearly establish which domain behavior creates each event, which repository method triggers publication, which callback clears the buffer, and which listeners must wait for commit. Keeping those steps distinct prevents duplicate emission, pre-commit side effects, or lost messages when the application fails.
