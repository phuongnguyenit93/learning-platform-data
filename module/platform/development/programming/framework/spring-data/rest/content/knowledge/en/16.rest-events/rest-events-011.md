# Limitations of REST Events When Repositories Are Called Outside HTTP Flows

## Objectives

Spring Data REST provides repository events such as `beforeCreate`, `beforeSave`, `beforeDelete`, and association-change events. These are convenient hooks for applying logic tied to the lifecycle of resources manipulated through endpoints managed by Spring Data REST.

However, REST events are not a universal lifecycle mechanism for every repository call. When a service, scheduled job, message listener, batch process, or custom controller calls `repository.save(...)` directly, that flow does not pass through Spring Data REST's request handlers and should not rely on `@HandleBeforeSave` or `@HandleBeforeCreate` to enforce business rules.

## When Are REST Events Invoked?

Spring Data REST publishes events when requests pass through repository REST endpoints and the framework executes the corresponding operation. Common events include:

| Event | Timing in REST Flow |
| --- | --- |
| `BeforeCreateEvent` / `AfterCreateEvent` | Before / after creating a new resource via collection endpoint |
| `BeforeSaveEvent` / `AfterSaveEvent` | Before / after saving an existing resource |
| `BeforeDeleteEvent` / `AfterDeleteEvent` | Before / after deleting a resource via REST |
| `BeforeLinkSaveEvent` / `AfterLinkSaveEvent` | Before / after adding or replacing an association |
| `BeforeLinkDeleteEvent` / `AfterLinkDeleteEvent` | Before / after removing an association |

Example handler processing before an `Order` is saved via Spring Data REST:

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderRestEventHandler {

        @HandleBeforeSave
        public void beforeSave(Order order) {
            if (order.getStatus() == OrderStatus.CANCELLED
                    && order.hasBeenShipped()) {
                throw new IllegalStateException(
                    "A shipped order cannot be cancelled.");
            }
        }
    }

The handler above is called when the save operation goes through the appropriate REST repository lifecycle. It does not automatically execute merely because another bean calls `orderRepository.save(order)`.

## What Happens When Calling a Repository from a Service?

Suppose a service updates an order directly:

    @Service
    public class OrderService {
        private final OrderRepository orderRepository;

        public OrderService(OrderRepository orderRepository) {
            this.orderRepository = orderRepository;
        }

        @Transactional
        public void cancelOrder(Long id) {
            Order order = orderRepository.findById(id)
                    .orElseThrow();
            order.setStatus(OrderStatus.CANCELLED);
            orderRepository.save(order);
        }
    }

When `cancelOrder` is called from a custom controller, scheduled job, or message listener, the repository call does not go through Spring Data REST. Therefore `OrderRestEventHandler.beforeSave` is not a reliable place to enforce the rule forbidding cancellation of shipped orders.

This also applies to flows such as:

- Scheduled tasks calling repositories to update data on a schedule.
- Consumers receiving messages from Kafka or RabbitMQ and saving entities.
- Batch jobs importing or synchronizing data.
- Services called from a hand-written REST controller.
- Tests calling services or repositories directly instead of sending HTTP requests to Spring Data REST endpoints.

Do not assume that because HTTP is involved at the outer edge, REST events are guaranteed to be published. Only requests processed through Spring Data REST's endpoint flow pass through Spring Data REST lifecycle hooks.

## Placing Business Rules in the Domain or Service Layer

If a rule must hold for all ways data is updated, place it where every flow must pass: a domain method or business service. REST events can call that same logic to integrate with auto-exposed endpoints.

Example moving the rule into the domain object:

    @Entity
    public class Order {
        @Enumerated(EnumType.STRING)
        private OrderStatus status;

        private boolean shipped;

        public void cancel() {
            if (shipped || status == OrderStatus.SHIPPED) {
                throw new IllegalStateException(
                    "A shipped order cannot be cancelled.");
            }
            this.status = OrderStatus.CANCELLED;
        }
    }

Service invoking the domain method inside a transaction:

    @Transactional
    public void cancelOrder(Long id) {
        Order order = orderRepository.findById(id)
                .orElseThrow();
        order.cancel();
    }

For auto-exposed REST endpoints, you can use an event handler to invoke the same domain method or delegate the operation to the business service via a custom controller. Do not maintain two copies of the same rule in a REST handler and a service, as they can drift apart over time.

Domain methods fit invariants tied to the entity itself. Services fit rules that must coordinate multiple repositories, check permissions, access related data, or orchestrate multiple operations in the same transaction.

## Distinguishing REST Events from Other Event Mechanisms

The mechanisms below have different scopes and do not replace one another:

### Spring Data REST repository events

- Published within the request lifecycle processed by Spring Data REST.
- Can use `@RepositoryEventHandler` with `@HandleBeforeCreate`, `@HandleBeforeSave`, `@HandleBeforeDelete`, or link handlers.
- Suitable for handling specific to REST representations and endpoints.
- Not a hook covering every direct call to a repository.

### Spring Data domain events

An aggregate root can publish domain events using `@DomainEvents`; Spring Data repositories publish these events when supported repository methods, such as `save` or `delete`, are called on the aggregate.

    public class Order {
        private final List<Object> domainEvents = new ArrayList<>();

        public void cancel() {
            // check invariants and change state
            domainEvents.add(new OrderCancelledEvent(/* order id */));
        }

        @DomainEvents
        Collection<Object> domainEvents() {
            return domainEvents;
        }

        @AfterDomainEventPublication
        void clearDomainEvents() {
            domainEvents.clear();
        }
    }

Domain events describe what happened in the domain, such as `OrderCancelledEvent`. They differ from REST events in that their goal is communicating domain events to other components. This mechanism still depends on operations passing through repository methods that support domain event publication; direct operations via `EntityManager` or SQL do not automatically trigger it.

Do not use domain events to replace validation before saving. Invariants should be checked synchronously in domain/service methods; events are usually used to notify the rest of the system.

### JPA lifecycle callbacks

JPA has callbacks such as `@PrePersist`, `@PreUpdate`, `@PostPersist`, and `@PostUpdate`. Callbacks are invoked by the persistence provider as the entity goes through its corresponding lifecycle, regardless of whether the change started from HTTP or a service.

    @Entity
    public class Customer {
        @PrePersist
        @PreUpdate
        void normalizeEmail() {
            if (email != null) {
                email = email.trim().toLowerCase(Locale.ROOT);
            }
        }
    }

Lifecycle callbacks fit local operations on the entity, such as normalizing values or setting internal fields. Avoid using callbacks to invoke other repositories, perform network I/O, check permissions, or orchestrate transactions; such actions are hard to control and can create persistence lifecycle coupling.

### Auditing and database constraints

Spring Data auditing annotations such as `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` apply across persistence flows with auditing enabled, without requiring requests to go through Spring Data REST. Configure `@EnableJpaAuditing` or auditing appropriate for the module in use and supply an auditor when needed.

Database constraints such as `NOT NULL`, `UNIQUE`, foreign keys, and check constraints are the final line of defense for data integrity. They still apply when writing from REST, services, batches, or direct SQL.

## Handling Work After Transaction Commit

If you need to send emails, publish messages to a broker, or call external systems after saving succeeds, avoid performing side effects before the transaction commits. If the transaction rolls back after sending a message, the external system may receive an event for a change that was never persisted.

You can use `@TransactionalEventListener` to process after commit:

    @Component
    public class OrderNotificationListener {

        @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT)
        public void onOrderCancelled(OrderCancelledEvent event) {
            // send notification after the transaction has committed
        }
    }

The service or domain layer publishes `OrderCancelledEvent` inside the transaction. The listener processes only when the transaction commits successfully. When high reliability is required for sending messages to external systems, consider a transactional outbox rather than relying solely on an in-memory listener.

`@TransactionalEventListener` does not automatically turn every event into an after-commit event; the event must be published within an active transaction and use the right phase. For events that must be processed even without a transaction, configure fallback execution deliberately and understand the consistency implications.

## How to Combine the Mechanisms

For an important business rule, responsibilities can be divided as follows:

1. Domain methods check invariants and perform valid state transitions.
2. `@Transactional` services load entities, invoke domain methods, coordinate repositories, and save changes.
3. Spring Data REST events handle integration specific to REST endpoints; if needed, delegate into the same service/domain logic.
4. Domain events announce what happened so other components can react.
5. `@TransactionalEventListener(AFTER_COMMIT)` executes side effects after data has committed.
6. JPA callbacks handle local entity lifecycle operations; auditing and database constraints protect metadata and integrity.

Do not place the same business logic across multiple event layers. Clarify what each mechanism is responsible for to avoid duplicate execution, event-order dependencies, or missed call paths.

## Testing Different Invocation Flows

Write separate tests for each path because an HTTP test does not prove that service or batch paths are protected:

- **Spring Data REST HTTP test:** send POST, PUT/PATCH, DELETE, or association requests to REST endpoints; confirm REST handlers are invoked on the right events.
- **Service test:** call services directly; confirm domain invariants still block invalid states even without REST events.
- **Repository/domain event test:** call repository methods supporting `@DomainEvents`; confirm domain events are published once and cleared per the aggregate lifecycle.
- **Persistence test:** save entities via JPA; confirm callbacks, auditing, and database constraints work.
- **Transaction test:** force transaction rollback; confirm `AFTER_COMMIT` listeners do not run and no external side effects occur.
- **Batch/message test:** run the actual job or consumer entry point to confirm it invokes the shared service/domain logic.

Do not just assert that a REST handler method ran. Check the final state in the database, published events, rollback behavior, and that side effects occur only after commit.

## Implementation Workflow

1. List all entry points that can write the entity: Spring Data REST, custom controllers, services, jobs, consumers, and batches.
2. Put business invariants into shared domain methods or services.
3. Keep `@RepositoryEventHandler` for handling specific to Spring Data REST.
4. Use `@DomainEvents` to publish business events from aggregates when operating through repositories that support this mechanism.
5. Use JPA callbacks for local handling and auditing for creation/modification metadata.
6. Keep database constraints to protect data across all write paths.
7. Use `@TransactionalEventListener(AFTER_COMMIT)` or an outbox for side effects that must occur after commit.
8. Test HTTP and non-HTTP flows independently.

Spring Data REST events should be viewed strictly as REST lifecycle hooks. If a rule must hold whenever a repository is called from anywhere, put the rule in the domain/service layer and use REST events as a thin integration layer for auto-exposed endpoints.