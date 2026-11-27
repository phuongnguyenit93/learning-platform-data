# Distinguishing Domain Events, Entity Callbacks, and Auditing

## 1. Three concepts, three responsibilities

When an entity is created, updated, or deleted in Spring Data JPA, an application may need to run additional logic. For example, when an order is confirmed, the system needs to notify the warehouse; before saving a product, the application needs to normalize the SKU code; when a customer is updated, the system needs to record the timestamp and actor.

Three common mechanisms are:

- **Domain event:** represents a business fact that has occurred so other parts of the system can react.
- **JPA entity lifecycle callback:** hooks into a point in the entity's persistence lifecycle, such as before INSERT or after load.
- **Spring Data auditing:** automatically records creation and update metadata such as timestamps and actors.

They are not three different ways of writing the same thing. A domain event answers "which business occurrence just happened?". An entity callback answers "which stage of persistence is the entity in?". Auditing answers "who created/modified the record and when?".

An application can use all three: the service confirms an order and emits `OrderPlaced`; a callback normalizes an entity field; auditing updates `createdAt`, `lastModifiedAt`, and the actor. Keeping each mechanism focused on its own responsibility makes code easier to understand and test.

## 2. Domain events: describing business facts

A domain event is an immutable object describing something that happened in the business domain. Event names are usually in the past tense, such as `OrderPlaced`, `PaymentReceived`, `CustomerActivated`, or `InventoryReserved`.

An event should contain enough data for handlers to understand and process it, typically the aggregate ID, correlation ID, and necessary business values. Avoid passing a managed JPA entity into an event: the entity may become detached by the time the handler runs, contain lazy associations, or be mutated after the event is created. Immutable DTOs/records keep event contents clearer and more stable.

Example:

```java
public record OrderPlaced(
    UUID orderId,
    Instant occurredAt
) {}
```

An aggregate can produce an event during a business state transition:

```java
@Entity
public class Order {

    @Id
    private UUID id;

    private boolean placed;

    @Transient
    private final List<Object> domainEvents = new ArrayList<>();

    protected Order() {
    }

    public Order(UUID id) {
        this.id = id;
    }

    public void place(Clock clock) {
        if (placed) {
            throw new IllegalStateException("Order already placed");
        }

        placed = true;
        domainEvents.add(new OrderPlaced(id, clock.instant()));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(domainEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        domainEvents.clear();
    }
}
```

This is an integration example requiring the corresponding imports, Spring Data repository, JPA provider, and Spring context. `@Transient` here is the JPA annotation, ensuring the event list is not mapped as a column. Pre-allocating the ID allows the event to carry a valid ID as soon as the business method emits the event; if the ID is only available after INSERT, choose a suitable emission timing or another identifier.

### Publishing events with Spring Data

Spring Data supports retrieving and publishing events from aggregate roots via `@DomainEvents`. When supported repository methods operate on an aggregate root (such as `save`, `saveAll`, `delete`, `deleteAll`), Spring Data can call the annotated method to collect events and publish them via the Spring application event infrastructure. After publication, the method annotated with `@AfterDomainEventPublication` is invoked so the aggregate clears its event list.

Example service:

```java
public interface OrderRepository extends JpaRepository<Order, UUID> {}

@Service
public class OrderService {

    private final OrderRepository repository;
    private final Clock clock;

    public OrderService(OrderRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    @Transactional
    public void place(UUID orderId) {
        Order order = repository.findById(orderId).orElseThrow();
        order.place(clock);
        repository.save(order);
    }
}
```

Calling the repository is part of Spring Data's domain event publication mechanism. Calling `EntityManager.persist()` directly or only mutating an object in memory without going through an eligible repository operation does not automatically trigger `@DomainEvents`. If the application uses other write paths, publish events explicitly or build and test a unified mechanism.

`@AfterDomainEventPublication` only clears events after Spring Data has published them. It does not prove that listeners have completed, nor does it mean the database transaction has committed. Therefore, do not use this callback as a signal that external side effects are safe to perform.

### Handling events by transaction phase

Spring lets listeners bind to the transaction lifecycle via `@TransactionalEventListener`:

```java
@Component
public class OrderPlacedHandler {

    private final NotificationService notificationService;

    public OrderPlacedHandler(NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void on(OrderPlaced event) {
        notificationService.notifyCustomer(event.orderId());
    }
}
```

Common phases:

| Phase | Handling timing |
|---|---|
| `BEFORE_COMMIT` | Before the transaction commits |
| `AFTER_COMMIT` | After the transaction commits successfully; this is the default |
| `AFTER_ROLLBACK` | After the transaction rolls back |
| `AFTER_COMPLETION` | After the transaction completes, whether committed or rolled back |

If an event is published outside a transaction, the listener does not run by default. Only enable `fallbackExecution = true` when business requirements permit the handler to run even without a transaction.

Application events in Spring are typically processed synchronously by default. If a handler uses `@Async` or an asynchronous event multicaster, work runs on another thread and does not inherit the publishing thread's transaction context. Database writes inside the worker need their own transaction, typically placed in another service bean with `@Transactional`.

After `AFTER_COMMIT`, the original transaction has completed. If the handler needs to write additional data with JPA, place that operation in a service with a new transaction, such as `REQUIRES_NEW` propagation, so changes commit independently. Do not rely on old transaction resources still being accessible in the callback to perform a write without a subsequent transaction commit.

### In-memory events and the Transactional Outbox

`@TransactionalEventListener(AFTER_COMMIT)` ensures the handler is called only after the transaction commits successfully. However, in-memory Spring events are not a durable queue. If the process stops after database commit but before the handler completes, side effects can be lost.

For critical integrations, use a Transactional Outbox:

1. In the same business transaction, save aggregate changes and an outbox record containing the event.
2. A worker reads unsent outbox records.
3. The worker sends the message to a broker or external system.
4. The worker marks the record as sent or updates retry state.
5. Consumers handle duplicates safely using an idempotency key or event ID.

An outbox ensures events and business data are written atomically in the same database transaction. Message delivery can still repeat, so consumers must be idempotent; do not claim the system achieves exactly-once solely because an outbox is used.

## 3. JPA entity lifecycle callbacks: hooking into the persistence lifecycle

Jakarta Persistence provides callbacks to execute logic at specific points in an entity's lifecycle:

| Callback | Timing |
|---|---|
| `@PrePersist` | Before the entity is persisted |
| `@PostPersist` | After INSERT has been executed |
| `@PreUpdate` | Before UPDATE is executed |
| `@PostUpdate` | After UPDATE has been executed |
| `@PreRemove` | Before DELETE is executed |
| `@PostRemove` | After DELETE has been executed |
| `@PostLoad` | After the entity is loaded into the persistence context |

Callbacks can be placed directly on the entity or in a listener class declared via `@EntityListeners`.

Example normalizing an SKU:

```java
@Entity
@EntityListeners(ProductLifecycleListener.class)
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String sku;

    protected Product() {
    }

    public Product(String sku) {
        this.sku = sku;
    }

    void normalizeSku() {
        if (sku != null) {
            sku = sku.trim().toUpperCase(Locale.ROOT);
        }
    }
}

public class ProductLifecycleListener {

    @PrePersist
    @PreUpdate
    public void normalize(Product product) {
        product.normalizeSku();
    }
}
```

The code snippet illustrates using a listener to normalize a field of the entity itself before saving. Callback methods must obey Jakarta Persistence signature and lifecycle rules. If you want to inject Spring beans into an entity listener, configure appropriate Spring/JPA integration; do not assume a listener instantiated by the JPA provider is always managed as a Spring bean.

### What logic fits callbacks?

Callbacks suit small, local logic tied to the entity itself, for example:

- Normalizing strings before saving.
- Setting default values on a field.
- Computing simple derived values from fields of the same entity.
- Generating a technical value required as the entity passes through its persistence lifecycle.

Callbacks are not appropriate for sending emails, making HTTP calls, publishing messages to a broker, coordinating multiple aggregates, or running multi-step business workflows. Those side effects may occur before transaction commit; if the transaction rolls back, external systems may already have received the effect.

JPA imposes restrictions on callbacks: in general, do not run queries or EntityManager operations from a callback, do not access other entities in the persistence context, and do not modify relationships among entities in the same persistence context. Keep callbacks short and avoid depending on the state of other objects.

### Callbacks are not domain events

`@PostPersist` indicates that an INSERT operation was executed during persistence synchronization. It does not mean an order has been confirmed, payment succeeded, or a business rule completed. An entity might be saved in draft state, the transaction might later roll back, and the same entity might be persisted or updated for many technical reasons.

Therefore, do not emit an event like `OrderPlaced` just because `@PostPersist` ran. Emit the event in the business method that confirms order placement. Callbacks can normalize data for an entity; events describe what happened in the business domain.

## 4. Spring Data auditing: who created/modified and when?

Auditing records entity creation and update metadata. Spring Data JPA provides these annotations:

- `@CreatedDate`: timestamp when the entity was created.
- `@LastModifiedDate`: timestamp when the entity was last modified.
- `@CreatedBy`: actor who created the entity.
- `@LastModifiedBy`: actor who last modified the entity.

These fields are useful for display, operational tracing, and basic audit trails. Auditing does not retain all previous versions of an entity and does not explain the business reason behind a change.

### Enabling auditing and providing the actor

```java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    public AuditorAware<String> auditorAware() {
        return () -> Optional.ofNullable(
            SecurityContextHolder.getContext().getAuthentication()
        )
        .filter(Authentication::isAuthenticated)
        .map(Authentication::getName);
    }
}
```

This example obtains the actor from Spring Security. A real application needs to define behavior explicitly for anonymous requests, background jobs, batch imports, and service accounts. You can return a conventional system identifier or `Optional.empty()` when no actor is present. Do not let `createdBy` be populated with a fake username merely to avoid null.

If you need a custom time source for tests or system time standards, configure `DateTimeProvider`. For global timestamps, `Instant` is usually an appropriate choice; standardize timezone display rules in APIs and UIs.

### Declaring audit fields in a base class

```java
@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class AuditedEntity {

    @CreatedDate
    @Column(updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @CreatedBy
    @Column(updatable = false)
    private String createdBy;

    @LastModifiedBy
    private String lastModifiedBy;

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }
}
```

Business entity extending the base class:

```java
@Entity
public class Customer extends AuditedEntity {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    protected Customer() {
    }
}
```

Corresponding imports for Jakarta Persistence, Spring Data auditing, and Spring Security are required. `@MappedSuperclass` maps audit fields into child entity tables. `@EntityListeners(AuditingEntityListener.class)` registers the listener that updates auditing fields; `@EnableJpaAuditing` enables the auditing infrastructure.

If actors are not needed, `@CreatedBy`, `@LastModifiedBy`, and `AuditorAware` can be omitted while still keeping date auditing. `@Column(updatable = false)` protects creation fields from being included in regular UPDATE statements; this is a mapping constraint, not an immutable history mechanism preventing every kind of write.

### What are auditing's limitations?

Auditing focuses on current state: who created, who last modified, and the corresponding timestamps. It does not automatically store every version, per-field diffs, or business reasons. If full history is required, consider Hibernate Envers, a dedicated audit table, or an event log with an appropriate retention policy.

Bulk JPQL or native SQL operations update the database directly without loading individual entities into the persistence context. They do not go through full entity lifecycle callbacks like normal entity operations, so auditing does not automatically update fields on bulk-updated rows either. If using bulk updates, explicitly update audit columns in the statement or choose an appropriate write path.

## 5. Comparison across real-world scenarios

| Scenario | Suitable mechanism | Reason |
|---|---|---|
| Order confirmed, need to trigger warehouse | Domain event `OrderPlaced` | A business fact requiring multiple components to react |
| Normalize SKU before writing | `@PrePersist` / `@PreUpdate` | Small logic tied directly to the entity being saved |
| Record creation and modification timestamps | Spring Data auditing | Repetitive metadata across many entities |
| Send email after order commits | Domain event + `AFTER_COMMIT` | Avoid sending when transaction rolls back |
| Store history of all changes | Envers or audit log | Auditing metadata only tracks current creation/modification state |
| Update a technical field after entity load | `@PostLoad` if truly needed | Hook into the moment the entity is loaded |

Do not use `@PostPersist` as an "order placed" event, do not use auditing to orchestrate workflows, and do not place queries or external I/O inside callbacks.

## 6. Designing a business flow combining all three mechanisms

Suppose a customer is activated. The flow might look like this:

1. The application service calls the business method `customer.activate()`.
2. The aggregate checks preconditions and changes state.
3. The aggregate creates the domain event `CustomerActivated`.
4. The repository saves the aggregate; Spring Data publishes the event via `@DomainEvents`.
5. A JPA callback performs local logic such as normalizing a field before writing.
6. The auditing listener populates `lastModifiedAt` and `lastModifiedBy`.
7. After the transaction commits, a handler processes `CustomerActivated`.

This structure cleanly separates business changes, entity lifecycle rules, and persistence metadata. Handlers can be added or changed without the aggregate needing to know their names or how they work.

If a handler updates the database after commit, invoke a separate service with a new transaction. If a handler sends external messages and cannot lose events if the process stops, persist an outbox row inside the business transaction and dispatch via a worker with retries. If a handler runs asynchronously, pass immutable IDs/DTOs and never pass managed entities or assume transaction/security contexts propagate across threads.

## 7. Testing at the right timing

### Testing domain events

- Call the business method and verify the aggregate creates the right event.
- Verify invalid operations do not emit events.
- If using `@DomainEvents`, call the appropriate repository method and verify the event is published.
- Verify `AFTER_COMMIT` listeners run only after commit and do not run when the transaction rolls back.

Spring tests are often annotated with `@Transactional` and rolled back at the end. As a result, a rolled-back test transaction will not trigger `AFTER_COMMIT` listeners. To test the commit phase, use `TestTransaction.flagForCommit()` and `TestTransaction.end()`, or call the service from an integration test without a surrounding transaction.

### Testing lifecycle callbacks

Persist the entity, flush, and reload to verify values produced by the callback. For example, if a callback normalizes SKU, save a string with spaces/lowercase, read it back, and verify the normalized value. Testing through the JPA provider confirms the callback is actually invoked at the right time.

### Testing auditing

- Enable `@EnableJpaAuditing` in the test context.
- Provide a test `AuditorAware` returning a fixed actor.
- Persist the entity, flush, and reload; verify `createdAt`, `createdBy`.
- Update the entity in another transaction; verify `lastModifiedAt`, `lastModifiedBy`.
- Test background jobs lacking a SecurityContext and verify the conventional system actor is recorded.

Skeleton auditing test example:

```java
@DataJpaTest
class CustomerAuditingTest {

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void recordsCreationTime() {
        Customer customer = new Customer();
        // Set up required data for Customer.

        entityManager.persist(customer);
        entityManager.flush();
        entityManager.clear();

        Customer reloaded =
            entityManager.find(Customer.class, customer.getId());

        assertThat(reloaded.getCreatedAt()).isNotNull();
    }
}
```

This is an illustrative skeleton; getters, constructors, and auditing configuration in the test context are needed. Calling clear before reading prevents retrieving the same managed object from the persistence context.

## 8. Common mistakes and how to avoid them

| Mistake | Consequence | Fix |
|---|---|---|
| Sending email in `@PostPersist` | Email may be sent even if the transaction later rolls back | Emit a domain event and handle after commit |
| Emitting events just because `save()` was called | Save may be a technical state save rather than a new business event | Emit events inside the business method confirming that fact |
| Assuming `@AfterDomainEventPublication` means handlers succeeded | Annotation only clears events after publication | Monitor handlers, retry, and use an outbox if reliability is required |
| Using callbacks to query other entities | Violates callback rules and creates hard-to-control persistence coupling | Move logic to a service or handler |
| Not configuring `AuditorAware` while expecting an actor | createdBy/lastModifiedBy lack the expected identity | Configure user or service-account actor resolution |
| Using auditing as a full change log | Cannot reconstruct previous versions | Use Envers or an audit log |
| Using bulk SQL and expecting auditing to auto-update | Bulk DML bypasses normal entity lifecycles | Update audit columns explicitly or use the entity write path |

## 9. Mechanism selection checklist

- [ ] Does the logic describe a business fact? Use a domain event.
- [ ] Does the logic only handle local state right at entity persist/load? Consider a lifecycle callback.
- [ ] Do you need to record who created/modified and when? Use Spring Data auditing.
- [ ] Must the handler run only after data commits? Use `@TransactionalEventListener(AFTER_COMMIT)`.
- [ ] Must the event be delivered durably? Use a Transactional Outbox and idempotent consumers.
- [ ] Are entity listeners kept short without querying other entities or calling external systems?
- [ ] Do tests verify real commit/rollback behavior and actors in background flows?

## 10. Takeaways

Domain events announce a business fact; JPA callbacks run at persistence lifecycle milestones; Spring Data auditing records creation and update metadata. Emit events where business facts are confirmed, use callbacks for small entity-level logic, and let auditing manage actor/timestamp fields. Choose the right transaction phase for handlers and use an outbox when events require durable reliability. The three mechanisms work well together when each does its own job.