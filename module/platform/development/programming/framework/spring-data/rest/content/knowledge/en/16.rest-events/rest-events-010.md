# Distinguishing REST Events, Repository Domain Events, and JPA Callbacks

In a Spring Data REST application, creating, updating, or deleting an entity can trigger multiple event mechanisms. Three mechanisms often confused are **Spring Data REST events**, **Spring Data repository domain events**, and **JPA lifecycle callbacks**.

They differ in where they originate and their purpose:

- **REST events** are published by the Spring Data REST exporter when handling requests through REST resources.
- **Repository domain events** are published by Spring Data when a repository operates on an aggregate root that publishes domain events.
- **JPA callbacks** are invoked by the persistence provider when an entity is persisted, updated, removed, or loaded.

A single REST request may pass through all three mechanisms. However, a repository call from a service may publish domain events and JPA callbacks without REST events. A direct JPA operation may run callbacks without going through a Spring Data repository.

## Objectives

After this article, you will be able to:

- Identify the origin and scope of the three event/callback types.
- Use **@RepositoryEventHandler** and **@Handle...** annotations to handle REST events.
- Publish domain events using **@DomainEvents**, **@AfterDomainEventPublication**, or **AbstractAggregateRoot**.
- Use JPA callbacks such as **@PrePersist**, **@PostPersist**, **@PreUpdate**, **@PreRemove**, and **@PostLoad**.
- Choose the right mechanism for validation, business rules, auditing, and side effects.
- Distinguish "after save" timing from "after transaction commit" timing.

## 1. Quick Comparison

| Criterion | Spring Data REST Event | Spring Data Repository Domain Event | JPA Lifecycle Callback |
| --- | --- | --- | --- |
| Who publishes it? | REST exporter | Spring Data repository infrastructure | JPA persistence provider |
| When? | Request passes through REST exporter and processes repository/association resources | Repository invokes supported operations on an aggregate root with domain events | Entity passes through persistence lifecycle |
| Depends on REST? | Yes | No | No |
| Depends on repository? | Yes | Yes | No |
| Target of interest | Entity being processed by REST exporter | Aggregate root and business events recorded by the aggregate | Entity or mapped superclass |
| Typical APIs | @RepositoryEventHandler, @HandleBeforeSave | @DomainEvents, @AfterDomainEventPublication, AbstractAggregateRoot | @PrePersist, @PostPersist, @PreUpdate, @PostUpdate, @PreRemove, @PostRemove, @PostLoad |
| Example purpose | Normalize data received via REST | Publish OrderPaid or OrderPlaced | Set timestamps, simple entity lifecycle handling |

You can remember them with three questions:

- "What is the REST request doing to the resource?" → REST event.
- "What business event did the aggregate just produce?" → Domain event.
- "What is the persistence provider doing to the entity?" → JPA callback.

## 2. Spring Data REST Events

The Spring Data REST exporter publishes Spring application events while processing entities via REST. The Spring Data REST 5.1 documentation lists eight main events:

| Event | Timing |
| --- | --- |
| BeforeCreateEvent | Before a new entity is saved for the first time via REST |
| AfterCreateEvent | After a new entity is saved via REST |
| BeforeSaveEvent | Before an existing entity is saved via REST |
| AfterSaveEvent | After an entity is saved via REST |
| BeforeLinkSaveEvent | Before saving or updating a link to a related entity |
| AfterLinkSaveEvent | After saving or updating a link |
| BeforeDeleteEvent | Before deleting an entity via REST |
| AfterDeleteEvent | After deleting an entity via REST |

For example, a client sends:

~~~http
POST /orders
Content-Type: application/json
Accept: application/hal+json

{
  "customerName": "An",
  "status": "NEW"
}
~~~

The REST exporter can publish BeforeCreateEvent, execute the save operation via the repository, and then publish AfterCreateEvent.

If a service calls directly:

~~~java
orderRepository.save(order);
~~~

then REST events are not automatically generated merely because the repository is exported by Spring Data REST. This flow does not pass through the REST exporter.

### 2.1. Handling with @RepositoryEventHandler

Create a Spring bean and place @Handle... annotations on methods:

~~~java
import org.springframework.data.rest.core.annotation.HandleAfterCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(Order.class)
public class OrderRestEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Order order) {
        if (order.getCustomerName() == null
                || order.getCustomerName().isBlank()) {
            throw new IllegalArgumentException(
                    "Customer name is required");
        }
    }

    @HandleBeforeSave
    public void beforeSave(Order order) {
        order.normalizeCustomerName();
    }

    @HandleAfterCreate
    public void afterCreate(Order order) {
        // Post-creation processing specific to the REST flow.
    }
}
~~~

Points to remember:

- @RepositoryEventHandler(Order.class) scopes the handler to the Order domain type.
- If the domain type argument is omitted, Spring Data REST determines the entity type from the first parameter type of the handler method.
- The handler method receives the entity being processed.
- The bean must be managed by Spring, e.g. using @Component or declared with @Bean.
- Multiple handler methods can be declared for multiple events or domain types.

REST events fit logic tied specifically to the HTTP boundary, such as normalizing payloads or enforcing rules that apply only to REST requests. Do not place core business rules exclusively in REST handlers if services, batch jobs, or message consumers must also enforce those rules.

### 2.2. Scope and Synchronicity

REST events only run when operations pass through the Spring Data REST exporter. They do not automatically capture changes from services, batch jobs, message consumers, or direct repository calls.

By default, Spring application events are processed synchronously on the publishing thread unless the application configures an executor or moves events across another processing boundary. Therefore, handlers can impact request response latency.

AfterCreateEvent and AfterSaveEvent mean the REST exporter has completed the corresponding save step. They do not prove the transaction has committed successfully.

## 3. Spring Data Repository Domain Events

Spring Data supports aggregate roots publishing **domain events**. These are events describing what happened in the business domain, such as OrderPlaced, OrderPaid, ShipmentDispatched, or AccountClosed.

Domain events are produced by aggregate root behavior. Spring Data repository infrastructure reads those events when the repository invokes supported operations and publishes them as Spring application events.

This mechanism does not depend on HTTP requests. If a service calls repository.save(order), domain events can still be published as long as the aggregate root recorded events and the repository call belongs to the supported group.

### 3.1. Using @DomainEvents and @AfterDomainEventPublication

An aggregate root can manage its own event list:

~~~java
@Entity
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    @Transient
    private final List<Object> events = new ArrayList<>();

    public void markPaid() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                    "Only pending orders can be paid");
        }

        status = OrderStatus.PAID;
        events.add(new OrderPaid(id));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return events;
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        events.clear();
    }
}
~~~

In this example:

- The method with @DomainEvents takes no parameters.
- The method can return a single event or a collection of events.
- Spring Data retrieves events from the aggregate root when supported repository methods are invoked.
- After publishing completes, the method annotated with @AfterDomainEventPublication is invoked; the example uses it to clear published events from the list.

The events field is transient in-memory state, not business data to persist. JPA @Transient can be used to exclude it from persistence mapping when the entity uses field access; adjust according to the entity's access strategy.

### 3.2. Using AbstractAggregateRoot

Spring Data provides **AbstractAggregateRoot** so you do not have to write the event list and the two annotated methods manually:

~~~java
@Entity
public class Order
        extends AbstractAggregateRoot<Order> {

    @Id
    @GeneratedValue
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    public void markPaid() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                    "Only pending orders can be paid");
        }

        status = OrderStatus.PAID;
        andEvent(new OrderPaid(id));
    }
}
~~~

andEvent(…) registers an event for Spring Data to publish when the repository saves or deletes the aggregate root. AbstractAggregateRoot also provides registerEvent(…), andEventsFrom(…), and clearDomainEvents() when finer control is needed.

Example event as an immutable data type:

~~~java
public record OrderPaid(Long orderId) {
}
~~~

Repository:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, Long> {
}
~~~

Service modifying state and saving the aggregate:

~~~java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void markPaid(Long id) {
        Order order = repository.findById(id)
                .orElseThrow();

        order.markPaid();
        repository.save(order);
    }
}
~~~

Spring Data reads and publishes domain events registered on the aggregate root when the repository processes save.

### 3.3. Listening to Domain Events

Domain events are published as Spring application events. They can be received using @EventListener:

~~~java
@Component
public class OrderDomainEventHandler {

    @EventListener
    public void on(OrderPaid event) {
        // Update a read model or execute internal logic.
    }
}
~~~

If processing must wait until the transaction commits successfully, use **@TransactionalEventListener**:

~~~java
@Component
public class OrderNotificationHandler {

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void on(OrderPaid event) {
        // Send notification after the transaction has committed.
    }
}
~~~

By default, @TransactionalEventListener binds to the AFTER_COMMIT phase. Other phases include BEFORE_COMMIT, AFTER_ROLLBACK, and AFTER_COMPLETION. If no transaction is active, the listener is not called by default; enable fallbackExecution only intentionally.

**@AfterDomainEventPublication does not mean AFTER_COMMIT.** That annotation only marks that Spring Data has published the domain events collected from the aggregate. It does not confirm that the database transaction has committed.

### 3.4. Which Repository Methods Publish Domain Events?

Spring Data documentation describes checking domain events for repository operations such as save(…), saveAll(…), delete(…), and certain delete variants accepting an aggregate root or collection of aggregate roots.

**deleteById(…) is not in the supported list for domain event publication.** Some implementations may delete via direct query without loading the aggregate instance; in that case Spring Data has no object from which to read domain events.

If business logic needs to publish OrderCancelled or OrderDeleted, perform the operation on the aggregate root and then call a repository method accepting that aggregate instance, rather than assuming every delete command publishes domain events automatically.

Domain events are suited for expressing aggregate-level business events. Do not use them merely to emit a signal that "Hibernate just ran a SQL UPDATE"; that is a different concept.

## 4. JPA Lifecycle Callbacks

JPA callbacks are invoked by the persistence provider when an entity goes through stages of its persistence lifecycle. Callbacks can be declared directly on an entity, mapped superclass, or entity listener class.

Standard annotations:

| Callback | When Invoked |
| --- | --- |
| @PrePersist | Before an entity is persisted |
| @PostPersist | After an entity has been inserted into the database |
| @PreUpdate | Before an entity data update operation |
| @PostUpdate | After an entity data update operation |
| @PreRemove | Before an entity is removed |
| @PostRemove | After an entity is removed |
| @PostLoad | After an entity is loaded or refreshed |

These callbacks are managed by the JPA provider. They can run whether the entity is modified from Spring Data REST, a service calling a repository, EntityManager directly, or another persistence path.

### 4.1. Declaring Callbacks on an Entity

Example automatically assigning timestamps:

~~~java
@Entity
public class Customer {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private Instant createdAt;
    private Instant updatedAt;

    @PrePersist
    protected void beforeInsert() {
        createdAt = Instant.now();
        updatedAt = createdAt;
    }

    @PreUpdate
    protected void beforeUpdate() {
        updatedAt = Instant.now();
    }
}
~~~

JPA invokes beforeInsert when the entity is first persisted and beforeUpdate prior to the entity data update operation.

Callback methods placed on an entity or mapped superclass have a no-argument signature returning void. Methods may use public, protected, package-private, or private visibility; they must not be declared static or final.

### 4.2. Separating Callbacks into an EntityListener

Shared logic can be extracted into a listener:

~~~java
public class CustomerAuditListener {

    @PrePersist
    public void beforePersist(Customer customer) {
        Instant now = Instant.now();
        customer.setCreatedAt(now);
        customer.setUpdatedAt(now);
    }

    @PreUpdate
    public void beforeUpdate(Customer customer) {
        customer.setUpdatedAt(Instant.now());
    }
}
~~~

Attach the listener to the entity:

~~~java
@Entity
@EntityListeners(CustomerAuditListener.class)
public class Customer {

    // Entity fields and methods.
}
~~~

Methods in an entity listener accept the entity instance as a parameter. A listener can apply to multiple compatible entities if declared on a mapped superclass or configured as an appropriate listener.

### 4.3. Callback Timing and Flushing

Not every callback runs at the exact moment the application calls repository.save():

- @PrePersist is called synchronously during persist or merge when a new entity becomes a managed instance.
- @PostPersist runs after the INSERT operation. INSERT may happen immediately during persist or later when the persistence context flushes, such as near the end of the transaction.
- @PreUpdate and @PostUpdate are tied to the UPDATE operation; the SQL may run at flush time.
- @PreRemove and @PostRemove are tied to the entity removal process.
- @PostLoad runs after an entity is loaded into the persistence context or after a refresh.

With the IDENTITY strategy, auto-generated primary keys do not yet exist in @PrePersist; the primary key exists in @PostPersist. With SEQUENCE, TABLE, or UUID, the ID may already exist prior to @PrePersist depending on the generation strategy per the specification.

### 4.4. Limitations of JPA Callbacks

JPA callbacks are designed for logic tied to the entity's persistence lifecycle. Do not turn callbacks into complex business orchestrators.

According to the Jakarta Persistence specification:

- Callbacks can modify non-relationship state of the entity receiving the callback.
- In general, portable callbacks should not invoke EntityManager or queries, access other entities, or modify relationships within the same persistence context.
- Runtime exceptions from a callback inside a transaction can cause the transaction to be marked for rollback.
- Callback ordering across related entities during cascades is somewhat implementation-dependent; do not write logic relying on ordering not guaranteed by the specification.

Bulk JPQL update/delete statements or native SQL do not go through individual managed entity lifecycles in the usual way. Do not expect @PreUpdate or @PostRemove to run for each row changed by a bulk statement.

If you need to react to bulk operations, publish application/domain events at the layer executing the command or use a database-appropriate audit mechanism.

## 5. Do Not Confuse "After Save" with "After Commit"

This is an easy source of bugs when sending emails, calling external services, publishing messages, or updating other systems.

| Milestone | What Is Confirmed |
| --- | --- |
| AfterSaveEvent | Spring Data REST has passed the REST exporter's save step |
| @AfterDomainEventPublication | Spring Data has published domain events retrieved from the aggregate |
| @PostPersist / @PostUpdate | The persistence provider has executed the corresponding INSERT/UPDATE |
| TransactionPhase.AFTER_COMMIT | The transaction has committed successfully |

A save operation may only synchronize the entity into the persistence context; the actual SQL may execute on flush. Even when INSERT/UPDATE has executed, the transaction can still roll back later.

Spring application events are processed synchronously on the publishing thread by default. Therefore, a listener running right after an event is published may still be inside the publisher's transaction. If the listener sends an email or calls an external API before the transaction commits, the external system may receive a notification about a change that ultimately rolls back.

When side effects must only run after commit, use @TransactionalEventListener with the AFTER_COMMIT phase. For reliable messaging across database and broker boundaries, consider a transactional outbox or equivalent transaction integration solution; do not treat synchronous callbacks/events as delivery guarantees.

## 6. Choosing the Mechanism for Each Job

| Need | Appropriate Mechanism | Reason |
| --- | --- | --- |
| Normalize data applicable only to Spring Data REST requests | @HandleBeforeCreate or @HandleBeforeSave | Logic tied to the REST exporter flow |
| Validate payload before REST exporter saves an entity | REST event handler or Validator integration | Runs at the REST boundary, can reject the request with errors |
| Publish OrderPaid when aggregate transitions to PAID | @DomainEvents or AbstractAggregateRoot | Event reflects business behavior, independent of HTTP |
| Update read model when aggregate emits events | Listener receiving domain events | Reacts to business events from supported repository flows |
| Send notification after transaction succeeds | @TransactionalEventListener(AFTER_COMMIT) | Avoids sending side effects for rolled-back transactions |
| Set createdAt/updatedAt along persistence lifecycle | @PrePersist, @PreUpdate | Simple logic tied to entity state |
| Compute transient values after entity loads | @PostLoad, if fitting the model | Callback invoked after entity is loaded |
| Audit all SQL changes, including bulk SQL | Database audit/CDC or specialized solution | Entity callbacks do not cover bulk statements or SQL outside entity lifecycle |
| Handle every entity save regardless of REST or service | Service/domain layer, repository domain events, or JPA callbacks depending on intent | REST events do not cover other entry points |

No single mechanism replaces the other two. Choose based on the source event that the business requirement truly cares about.

## 7. A Single Flow Can Pass Through All Three Mechanisms

Suppose a client sends a POST to create an order through Spring Data REST:

~~~http
POST /orders
Content-Type: application/json
Accept: application/hal+json

{
  "customerId": 42,
  "status": "NEW"
}
~~~

In this flow:

1. The REST exporter handles the request and publishes BeforeCreateEvent; handlers with @HandleBeforeCreate may run.
2. The REST exporter calls the repository to save the aggregate.
3. Spring Data repository infrastructure may read and publish domain events registered on the aggregate root.
4. The JPA persistence provider invokes corresponding callbacks on persist/remove/update/load; SQL operations may happen immediately or on flush.
5. The REST exporter publishes AfterCreateEvent after its save step.
6. The transaction may commit or roll back at the transaction boundary managed by the application.

These steps show the scope of each mechanism, not a guarantee of absolute ordering across every callback and event. SQL may be deferred until flush; transaction boundaries may be determined by services or application configuration; listeners may also be configured to run asynchronously.

If a service calls repository.save(order) instead of a REST request, the REST exporter part does not run. Domain events and JPA callbacks can still run according to their respective configurations.

## 8. Testing the Three Mechanisms

Test each mechanism at its appropriate layer.

**REST events**

- Use integration tests calling REST endpoints.
- Verify pre-create/pre-save handlers are called.
- Verify data is normalized or requests are rejected as expected.
- Call the repository directly in a separate test to verify REST handlers are not triggered outside the REST exporter.

**Repository domain events**

- Create an aggregate root, invoke business methods, and register events.
- Call repository.save(aggregate).
- Use a test listener or ApplicationEventPublisher test hook to verify the expected event type is published.
- Verify @AfterDomainEventPublication clears the event list so subsequent saves do not re-publish.
- Test deleteById separately since it should not be assumed to publish domain events.

**JPA callbacks**

- Use integration tests with a real persistence provider or an appropriate test slice.
- Call persist, modify the entity and flush, remove, and load to trigger the corresponding callbacks.
- Use flush when tests need to observe exact SQL and update/insert callback timing.
- Verify callbacks do not depend on a specific repository or REST handler having been called.

**Transactions and side effects**

- Write tests for both transaction commit and rollback.
- Verify AFTER_COMMIT listeners only run after commit.
- Verify listeners do not run when transactions roll back.
- If listeners call brokers or external services, test retry/idempotency per integration design.

## 9. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| @RepositoryEventHandler does not run when service calls repository.save | REST exporter is not involved in this flow | Move shared logic to service/domain events; keep REST handlers for REST-boundary-specific handling |
| REST event runs but domain event does not | Aggregate did not register event or repository method is unsupported | Check @DomainEvents, registerEvent/andEvent, and repository method |
| Domain events published twice | Event list not cleared after publish or aggregate retains old events | Use @AfterDomainEventPublication or AbstractAggregateRoot properly |
| deleteById does not publish domain events | Repository may delete by query without loading aggregate instance | Load the aggregate and call delete(entity) if domain events are needed |
| @PostUpdate does not run immediately after save | SQL update deferred until flush or entity is not actually dirty | Check dirty checking and flush in tests |
| @PreUpdate does not run on bulk update | Bulk statements do not pass through individual managed entity lifecycles | Publish events at the command layer or use database-level auditing |
| Email sent despite transaction rollback | Listener ran synchronously before commit | Use @TransactionalEventListener(AFTER_COMMIT) or transactional outbox |
| JPA callback calling queries causes errors or unpredictable side effects | Callback doing too much outside entity lifecycle | Keep callbacks short, only mutating simple state on the entity |
| REST AfterSaveEvent treated as committed data | Confusing post-repository-save with post-transaction-commit | Use transaction-bound listeners if business logic needs the commit milestone |

## 10. Quick Checklist

- [ ] Identified whether the event comes from the REST exporter, Spring Data repository, or JPA provider.
- [ ] Core business rules are not placed solely in REST event handlers if services/batches also need them.
- [ ] Aggregate roots register domain events at the right moment inside business behavior.
- [ ] @DomainEvents methods take no parameters and return an event or collection of events.
- [ ] Events are cleared after publishing using @AfterDomainEventPublication or AbstractAggregateRoot.
- [ ] Not relying on deleteById to publish domain events.
- [ ] JPA callbacks have appropriate signatures and annotations.
- [ ] Not calling EntityManager/queries or modifying complex relationships inside JPA callbacks.
- [ ] Not expecting callbacks to run for bulk JPQL/native SQL.
- [ ] Side effects requiring transaction commit are tied to AFTER_COMMIT or an outbox.
- [ ] Separately tested REST requests, repository calls, persistence flush, and transaction rollbacks.

## 11. Takeaways

Three mechanisms solve three layers of problems:

1. **Spring Data REST events**: hook into requests/resources handled by the REST exporter.
2. **Spring Data repository domain events**: aggregate roots announce a business event when a repository operates on the aggregate.
3. **JPA lifecycle callbacks**: the persistence provider announces that an entity is persisting, updating, removing, or loading.

Choose REST events for HTTP-boundary logic, domain events for business events, and JPA callbacks for small actions tied to the entity lifecycle. When work must only happen after a transaction commits successfully, use transaction-bound listeners or an outbox according to reliability requirements.

## References

- Spring Data REST Reference — Events: https://docs.spring.io/spring-data/rest/reference/events.html
- Spring Data REST API — Repository event package: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/event/package-summary.html
- Spring Data Commons Reference — Publishing Events from Aggregate Roots: https://docs.spring.io/spring-data/jpa/reference/data-commons/repositories/core-domain-events.html
- Spring Data Commons API — DomainEvents: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/DomainEvents.html
- Spring Data Commons API — AfterDomainEventPublication: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/AfterDomainEventPublication.html
- Spring Data Commons API — AbstractAggregateRoot: https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/domain/AbstractAggregateRoot.html
- Jakarta Persistence Specification 3.2 — Entity Listeners and Callback Methods: https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.pdf
- Spring Framework Reference — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Reference — Application Events: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
