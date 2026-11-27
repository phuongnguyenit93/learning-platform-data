# Using AbstractAggregateRoot When Appropriate for the Domain Model

In Spring Data, AbstractAggregateRoot is a utility class that helps an aggregate root record **domain events** arising from business behavior. When the aggregate is saved through a Spring Data repository, registered events can be published by Spring Data as application events in the Spring ApplicationContext.

For example, when a customer places an order, the PurchaseOrder aggregate transitions to a placed state and records an OrderPlaced event. Another component can listen to that event to send notifications, update a read model, or start a follow-up workflow.

Not every entity needs to extend AbstractAggregateRoot. Use it only when the model has clear aggregate boundaries and aggregate changes produce business-meaningful events. This class assists with registering and publishing events within the application; it does not define business logic itself, does not replace transactions, and does not provide a durable queue like a message broker.

## 1. Aggregate roots and domain events

### 1.1. What is an aggregate root?

In Domain-Driven Design (DDD), an aggregate is a cluster of domain objects treated as a consistency unit. The aggregate root is the external entry point used to access and modify the state of that cluster. Aggregate invariants are protected through the root's behavior.

For example, a PurchaseOrder may contain OrderLine items. Business code should ask PurchaseOrder to add an item, confirm the order, or cancel the order; multiple components should not arbitrarily mutate individual OrderLine items and cause totals, quantities, and order status to become inconsistent.

### 1.2. What is a domain event?

A domain event describes something that has happened in the business domain and is meaningful to other components. Event names are usually phrased in the past tense, such as OrderPlaced, OrderConfirmed, PaymentReceived, or OrderCancelled.

A domain event is useful when it captures a business occurrence that another component needs to react to. It should not merely mirror a technical operation such as RepositorySaved or EntityUpdated.

An event should contain the minimal data needed for recipients to understand what happened, usually the aggregate ID, occurrence timestamp, and essential business values. Prefer immutable events so recipients cannot inadvertently modify data still used by the publisher.

The event example below uses a Java record:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(UUID orderId, Instant occurredAt) {}
~~~

Records fit events well because record components are final and values are passed through the constructor. In a project, each public record can be placed in its own file according to Java conventions.

## 2. What does AbstractAggregateRoot support?

The org.springframework.data.domain.AbstractAggregateRoot class belongs to Spring Data Commons and is used by Spring Data JPA as a shared utility across the Spring Data ecosystem. This class helps an aggregate root manage the list of domain events it has registered.

Key behaviors:

- **registerEvent(event):** registers an event when the corresponding business behavior occurs. The method returns the passed-in event so it can be composed in expressions if needed.
- **domainEvents():** provides the registered events to Spring Data's publishing mechanism. This method is annotated with @DomainEvents in the base class.
- **clearDomainEvents():** clears the events after publication. This method is annotated with @AfterDomainEventPublication.
- **andEvent(...)** and **andEventsFrom(...)**: helper methods for registering an event or incorporating events from another aggregate where supported by the API of the version in use.

When extending this class, the entity does not have to implement the event list and the two publication/cleanup annotations manually. The aggregate simply calls registerEvent(...) when a valid business behavior completes.

Spring Data inspects aggregate roots passed to certain repository operations such as save(...), saveAll(...), and supported delete operations to find and publish domain events. The exact list of methods may depend on the Spring Data version; check your project version's documentation if relying on a specific delete variant. Bulk update operations using JPQL or native SQL directly do not go through this aggregate root saving flow automatically.

## 3. Example: an aggregate registering its own domain events

Suppose an order-management application. When creating an order, the aggregate transitions to the PLACED state and registers OrderPlaced. The ID is generated with UUID in the application so the event can include the ID even before the entity is saved.

~~~java
import java.time.Instant;
import java.util.UUID;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.springframework.data.domain.AbstractAggregateRoot;

@Entity
public class PurchaseOrder extends AbstractAggregateRoot<PurchaseOrder> {
    @Id
    private UUID id;

    private String status;

    protected PurchaseOrder() {
    }

    private PurchaseOrder(UUID id) {
        this.id = id;
        this.status = "PLACED";
    }

    public static PurchaseOrder place() {
        PurchaseOrder order = new PurchaseOrder(UUID.randomUUID());
        order.registerEvent(new OrderPlaced(order.id, Instant.now()));
        return order;
    }

    public void confirm() {
        if (!"PLACED".equals(status)) {
            throw new IllegalStateException("Only a placed order can be confirmed");
        }

        status = "CONFIRMED";
        registerEvent(new OrderConfirmed(id, Instant.now()));
    }

    public UUID getId() {
        return id;
    }
}
~~~

The order confirmation event can be defined as follows:

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(UUID orderId, Instant occurredAt) {}
~~~

In the example, registerEvent(...) is called only after the state transition is valid. If confirmation conditions are not met, the method throws an exception and does not register OrderConfirmed. This structure ensures events reflect business changes accepted by the aggregate.

The UUID ID is generated prior to saving so the event can reference the aggregate immediately. If using a database-generated ID assigned on insert, do not create an event with a null ID. You can choose application-assigned IDs or design the event creation timing and payload to match the project's ID strategy.

## 4. Publishing events through a Spring Data repository

Standard repository declaration:

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
~~~

Service placing and saving the aggregate:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {
    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public UUID placeOrder() {
        PurchaseOrder order = PurchaseOrder.place();
        orders.save(order);
        return order.getId();
    }

    @Transactional
    public void confirmOrder(UUID id) {
        PurchaseOrder order = orders.findById(id).orElseThrow();
        order.confirm();
        orders.save(order);
    }
}
~~~

When orders.save(order) is called, Spring Data can retrieve the events from the aggregate root and publish them via the application event mechanism. After publication, the clearDomainEvents() callback clears the registered event list so they are not re-emitted on the next repository operation.

In confirmOrder, the entity is loaded within the transaction and is managed by the persistence context. Dirty checking can persist state changes when the transaction flushes or commits. Calling save(order) here illustrates when Spring Data inspects domain events; for an already managed entity, JPA does not require another save() call just for dirty checking to work. If you want to rely on repository event publication, make sure the aggregate root is passed to an operation that supports publication.

## 5. Listening to domain events

Because domain events are published as Spring application events, a bean can listen using @EventListener or @TransactionalEventListener.

Example listening after transaction commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderEventHandler {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        System.out.println("Order placed: " + event.orderId());
    }
}
~~~

@TransactionalEventListener lets you bind event handling timing to the transaction lifecycle. Common phases include:

- **BEFORE_COMMIT:** process before the transaction commits.
- **AFTER_COMMIT:** process after the transaction commits successfully.
- **AFTER_ROLLBACK:** process after the transaction rolls back.
- **AFTER_COMPLETION:** process after the transaction completes, regardless of commit or rollback.

With AFTER_COMMIT, if the transaction rolls back, the listener does not run for this phase. This is typically the right choice for tasks that should start only once business data has committed, such as sending notifications or triggering downstream work.

Unlike @TransactionalEventListener, a regular @EventListener handles the event immediately when it is published. In a save() call inside a service transaction, publication usually happens before the outer transaction commits. If a listener sends a notification to another system right then, the receiving system may observe the notification even if the transaction subsequently rolls back. Choose the phase according to consistency requirements.

If a post-commit listener needs to write data to the database, create a new transaction deliberately, typically through another service bean with REQUIRES_NEW propagation. At AFTER_COMMIT time, the original transaction has already finished; do not assume writes inside the listener will commit as part of the old transaction.

## 6. Publication timing and guarantee limits

Three points in time must be distinguished:

1. **Event registration:** business behavior calls registerEvent(...) and the aggregate holds the event in memory.
2. **Application event publication:** the Spring Data repository operation publishes the event while processing the aggregate root.
3. **Transaction commit:** the transaction manager confirms data changes in the database.

Publishing an application event does not mean the database has committed. When a service has @Transactional, repository save() is usually called inside that transaction. Spring Data publishes the event during execution of the repository method, before the service transaction finishes. Regular listeners can run at this time; AFTER_COMMIT listeners are deferred until transaction commit.

AbstractAggregateRoot keeps events in memory and clears the list after the publication callback. It does not write events to a durable table. If the process stops unexpectedly after data commits but before an external task runs, relying solely on application events does not guarantee that task will be re-dispatched.

When reliable event delivery to a message broker is required, consider the **Transactional Outbox** pattern: write aggregate changes and an outbox record in the same database transaction, then have a publisher read the outbox and send messages with retry and idempotency mechanisms. AbstractAggregateRoot helps surface business events inside the application, but it is not an outbox itself.

## 7. When should AbstractAggregateRoot be used?

Consider using it when:

- The entity is genuinely an aggregate root and controls business changes for an aggregate.
- A business action produces an event meaningful to other components.
- The application saves the aggregate via a Spring Data repository and wants to tie event publication to repository operations.
- The event can be described independently, is immutable, and holds enough data for recipients to process.

Do not use it simply because an entity is saved with JPA. If you only need logging, updating a technical field, or calling an internal function directly in the service, a domain event may add unnecessary complexity.

You may omit this base class when:

- The model has no clear aggregate root or entities do not own business behavior.
- Events must be stored durably, retried, distributed across multiple services, or protected against loss after crashes; an outbox or durable messaging mechanism is required in that case.
- Data modifications run via bulk JPQL/native SQL without loading and saving aggregate roots through repositories.
- The project needs a more customized event registration mechanism; in that case, implement @DomainEvents and @AfterDomainEventPublication manually or use an appropriate domain event dispatcher.

## 8. Common mistakes

- **Registering an event before checking invariants.** The event might describe an action that was never actually accepted. Check preconditions and update state before registering the event.
- **Putting an entire entity into an event.** This creates coupling to persistence structures, lazy associations, and mutable state. Prefer IDs and required business data.
- **Assuming events are only published after commit.** Repository publication and commit are two distinct moments. Use @TransactionalEventListener(AFTER_COMMIT) if the listener should only run after commit.
- **Assuming events are durably saved.** AbstractAggregateRoot stores events in memory. To guarantee message delivery across crashes, use an outbox or another durable solution.
- **Expecting bulk updates to emit domain events automatically.** JPQL bulk updates/deletes and direct SQL do not go through individual aggregate root lifecycles like save().
- **Registering events in arbitrary setters or persistence callbacks.** Events should be tied to named, meaningful domain behaviors such as confirm(), cancel(), or place().
- **Using an event as a substitute for transaction control.** Events do not automatically make multiple database operations atomic. Place transactions in the service along business boundaries.
- **Forgetting that the event list is cleared after publication.** If you need to retry publication or recover events after a rollback, you cannot treat the aggregate's internal list as an event store.

## 9. Project adoption workflow

1. Identify aggregate roots and the invariants each root must protect.
2. Identify which business behaviors produce events worth reacting to by other components.
3. Define immutable events named in the past tense and containing only necessary data.
4. Have the aggregate root extend AbstractAggregateRoot<AggregateType> and call registerEvent(...) after valid behavior completes.
5. Save the aggregate via a Spring Data repository within an appropriate transaction.
6. Use @TransactionalEventListener with the appropriate phase if the listener depends on commit or rollback outcomes.
7. If events must be delivered reliably to other systems, design an outbox, retries, and idempotency rather than relying solely on in-memory events.
8. Write integration tests to verify aggregate state, event publication, the cleanup callback, and listener behavior on commit/rollback.

## 10. Testing domain events

You can test published events using ApplicationEvents in Spring Test or by registering a test listener to collect events. The illustrative example below uses @RecordApplicationEvents and ApplicationEvents from Spring Test; it must run within a Spring test context with the application's real repository and transaction manager:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

@SpringBootTest
@RecordApplicationEvents
class PurchaseOrderEventTest {

    @Autowired
    PurchaseOrderService service;

    @Autowired
    ApplicationEvents events;

    @Test
    void publishesOrderPlacedWhenOrderIsSaved() {
        service.placeOrder();

        assertThat(events.stream(OrderPlaced.class)).hasSize(1);
    }
}
~~~

This is an integration test pattern, not a standalone program. Use a Spring Test version supporting ApplicationEvents and ensure events are published inside the test context. If the test runs in a framework-managed transaction that does not commit, AFTER_COMMIT listeners may not be invoked; configure an explicit commit test phase to verify post-commit listeners.

In addition to the happy path, verify these cases:

- Domain behavior failing due to violated invariants does not register an event.
- The aggregate is saved and the event is published the expected number of times.
- Events are cleared from the aggregate after publication and are not inadvertently re-emitted on subsequent saves.
- AFTER_COMMIT listeners run on successful commit and do not run on transaction rollback.
- Bulk updates do not emit events automatically; if business logic needs events, design an explicit publication path.

AbstractAggregateRoot is useful when the domain model has genuine aggregate roots and events reflect root business behaviors. Use it to connect domain behavior with Spring Data's application event mechanism, while explicitly choosing processing timing and the durability guarantees each event requires.