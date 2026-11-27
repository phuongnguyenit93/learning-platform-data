# EntityListener, Bean Validation, and Callback Processing Limits

## 1. Lifecycle callbacks in JPA

An Entity has a lifecycle managed by the persistence context: created, saved, updated, deleted, and loaded from the database. JPA provides lifecycle callbacks to execute a small piece of logic at those points. Callbacks can be declared directly in the Entity or extracted into a listener class using `@EntityListeners`.

Commonly used callback annotations:

| Callback | Timing |
| --- | --- |
| `@PrePersist` | Before the Entity is inserted |
| `@PostPersist` | After the insert operation has been executed |
| `@PreUpdate` | Before the Entity is updated |
| `@PostUpdate` | After the update operation has been executed |
| `@PreRemove` | Before the Entity is deleted |
| `@PostRemove` | After the delete operation has been executed |
| `@PostLoad` | After the Entity is loaded or refreshed from the database |

`@PostPersist`, `@PostUpdate`, and `@PostRemove` do not mean the transaction has committed. The transaction can still roll back after the callback. This is a critical point when deciding whether sending emails, calling APIs, or publishing messages from a callback is safe.

## 2. How do Entity callbacks and EntityListener differ?

Callbacks declared directly in the Entity are the simplest option for short processing that concerns only that Entity:

```java
@Entity
public class PurchaseOrder {
    @Id
    private Long id;

    private Instant updatedAt;

    @PreUpdate
    void updateTimestamp() {
        updatedAt = Instant.now();
    }
}
```

When logic is shared or you want to separate responsibilities from the Entity, you can create a listener:

```java
@Entity
@EntityListeners(PurchaseOrderAuditListener.class)
public class PurchaseOrder {
    @Id
    private Long id;

    private Instant createdAt;
    private Instant updatedAt;

    public void setCreatedAt(Instant createdAt) {
        this.createdAt = createdAt;
    }

    public void setUpdatedAt(Instant updatedAt) {
        this.updatedAt = updatedAt;
    }
}
```

```java
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import java.time.Instant;

public class PurchaseOrderAuditListener {
    @PrePersist
    public void beforeInsert(PurchaseOrder order) {
        Instant now = Instant.now();
        order.setCreatedAt(now);
        order.setUpdatedAt(now);
    }

    @PreUpdate
    public void beforeUpdate(PurchaseOrder order) {
        order.setUpdatedAt(Instant.now());
    }
}
```

A callback method inside an Entity has the signature `void method()` with no parameters. A method inside an EntityListener has the signature `void method(EntityType entity)` or accepts `Object`. Listeners require a no-arg constructor per the JPA contract; callback methods must be `void` instance methods without extra parameters. The example above uses the concrete type `PurchaseOrder` for readability.

Listeners can be attached to an Entity or a mapped superclass. When multiple listeners are used, callback ordering follows rules based on listener configuration and hierarchy; do not rely on incidental ordering among listeners to build business dependencies.

## 3. What kind of work are callbacks suited for?

Callbacks are suited for short, deterministic technical tasks directly tied to the state of the Entity itself:

- Assigning the `createdAt` timestamp on creation.
- Updating `updatedAt` when changes occur.
- Normalizing a simple field before writing, if the rule requires no access to other data.
- Computing a simple derived value from existing fields on the same Entity.
- Recording a local technical value that all persist/update paths must satisfy.

Callbacks are not the place for business orchestration. Do not use them to query repositories, check limits by reading other Entities, call remote services, send emails, publish messages, write files, or run long tasks. That work belongs in the service/application layer or via an appropriate event mechanism.

## 4. Important limits of callbacks

JPA imposes limits so callbacks do not mutate persistence context state unpredictably. Inside a callback, you should only modify non-relationship state of the Entity currently being handled by that callback.

Limits to remember:

1. Do not invoke `EntityManager` or `Query` to query or modify other data from a callback.
2. Do not access other Entity instances in the persistence context.
3. Do not alter relationships with other Entities, such as adding/removing collection elements or changing ManyToOne properties.
4. Do not execute logic that depends on flush order, callback order, or whether a SQL operation has already committed.
5. Do not perform I/O, make HTTP calls, send emails, or publish messages directly inside a callback.

JPA allows callbacks to modify non-relationship state of the Entity being processed, such as updating `updatedAt`. Keep callbacks short, free of external side effects, and independent of other queries.

If a callback throws an unchecked exception, the persistence operation can fail and the participating transaction will be rolled back according to transaction rules. Do not swallow errors and proceed as if the Entity saved successfully; let errors be handled at the appropriate calling layer.

## 5. Why should you not send messages in @PostPersist?

`@PostPersist` runs after the insert statement has executed, yet the transaction has not necessarily committed. If a callback sends an email or message at that moment, the database may later roll back while the external system has already received a notification about a record that does not exist.

Example of an unsafe flow:

```text
persist Entity
    -> @PostPersist
        -> send message to broker
    -> transaction rollback

The broker received the message, but the database data was not committed.
```

If side effects need to happen after commit, the service can publish an application event within the transaction and handle it with `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`. This listener runs after the transaction commits successfully:

```java
public record PurchaseOrderCreated(Long orderId) {
}
```

```java
@Service
public class PurchaseOrderService {
    private final ApplicationEventPublisher events;

    public PurchaseOrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    @Transactional
    public Long create(PurchaseOrder order) {
        repository.save(order);
        events.publishEvent(new PurchaseOrderCreated(order.getId()));
        return order.getId();
    }
}
```

```java
@Component
public class PurchaseOrderNotificationListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(PurchaseOrderCreated event) {
        // Send notification or call external service after transaction commit.
    }
}
```

This is an illustrative example; real repositories and dependencies must be injected. `AFTER_COMMIT` avoids sending notifications when a transaction rolls back, though in-memory events are not a durable queue. If the process stops right after commit before the listener finishes, the notification can be lost. For integrations requiring high reliability, use a transactional outbox: write the event into an outbox table within the same transaction as the business data, then have a worker read and deliver events with retries/idempotency.

## 6. What is Bean Validation?

Jakarta Bean Validation provides annotations for describing constraints on data. Some common constraints:

| Annotation | Meaning |
| --- | --- |
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must not be null and must contain at least one non-whitespace character |
| `@NotEmpty` | String/collection/map must not be empty |
| `@Size(min, max)` | Bounds length or element count |
| `@Positive` | Number must be greater than 0 |
| `@PositiveOrZero` | Number must be greater than or equal to 0 |
| `@Email` | Value must match the email format checked by the provider |

Example placing constraints on an Entity:

```java
@Entity
public class PurchaseOrder {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 40)
    @Column(name = "order_number", nullable = false, length = 40)
    private String orderNumber;

    @NotNull
    @Positive
    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;
}
```

`@NotBlank` and `@Size` are Bean Validation constraints. `@Column(nullable = false, length = 40)` is JPA mapping/schema metadata. The two types of annotations address different layers: Bean Validation checks the object before writing; database constraints protect data at the storage layer.

`@Column(nullable = false)` does not replace `@NotNull`, and `@NotNull` does not automatically create a NOT NULL constraint in the schema. With migration-managed schemas, constraints must be created via migrations.

## 7. When is Bean Validation triggered in JPA?

When a Bean Validation provider is on the classpath and the JPA validation mode allows it, JPA integrates validation into lifecycle events. Under the default `AUTO` mode, the provider is used if available. You can add the `spring-boot-starter-validation` dependency in Spring Boot to include an implementation such as Hibernate Validator.

Typically, the `jakarta.validation.groups.Default` group is validated at pre-persist and pre-update points. Thus, when persisting a new Entity or flushing a modified Entity, constraints can be checked before insert/update operations. JPA does not validate before remove by default.

Validation modes have these values:

- `AUTO`: automatically uses Bean Validation if a provider is available.
- `CALLBACK`: requires validation callback integration.
- `NONE`: disables JPA validation integration.

You can configure this explicitly in persistence unit properties if your project needs it:

```yaml
spring:
  jpa:
    properties:
      jakarta.persistence.validation.mode: callback
```

There is no need to set `CALLBACK` in every application. With Spring Boot, the validation dependency and the default AUTO mode are usually enough. If your project configures custom validation groups, verify which group is activated at each lifecycle event.

When a constraint is violated during JPA validation, the provider throws `jakarta.validation.ConstraintViolationException`; the persist/update operation fails and the transaction typically rolls back. Catch the error at the service/API layer to translate it into an appropriate response, rather than treating the data as saved.

## 8. API validation and persist-time validation are two layers

At the HTTP layer, validating request DTOs returns errors early, close to user input:

```java
public record CreatePurchaseOrderRequest(
    @NotBlank @Size(max = 40) String orderNumber,
    @NotNull @Positive BigDecimal totalAmount
) {
}
```

```java
@RestController
@RequestMapping("/purchase-orders")
public class PurchaseOrderController {
    private final PurchaseOrderService service;

    public PurchaseOrderController(PurchaseOrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreatePurchaseOrderRequest request) {
        service.create(request);
        return ResponseEntity.accepted().build();
    }
}
```

`@Valid` triggers DTO validation at the web layer. If a DTO contains nested objects, place `@Valid` on the nested property to cascade validation. Services can also use `@Validated` and constraints on method parameters when method validation is needed.

DTO validation and Entity validation serve different goals. DTOs validate the API contract; Entities validate persisted state regardless of whether writes originate from REST, message consumers, batch imports, or jobs. Do not rely solely on controller validation because other write paths can bypass the controller.

## 9. @Valid is not JPA cascade

The two mechanisms have similar names but are independent:

| Mechanism | Purpose |
| --- | --- |
| Bean Validation `@Valid` | Recursively validates related objects according to constraints |
| JPA `cascade = PERSIST/MERGE/REMOVE/...` | Propagates persistence operations to related Entities |

For example, placing `@Valid` on a relationship can cause constraints on the related Entity to be checked when validation cascades. It does not automatically persist that Entity. Conversely, `cascade = PERSIST` does not mean constraints on every nested object will automatically be checked without appropriate validation cascade configuration.

Do not use `@Valid` as a substitute for cascade persist, and do not use `CascadeType.ALL` as a substitute for Bean Validation.

## 10. How do EntityListener and Bean Validation work together?

An EntityListener can normalize or assign technical values before writing; Bean Validation checks constraints during lifecycle validation. However, do not design correctness to depend on the ordering between a custom callback and the Bean Validation listener if that ordering is not explicitly controlled.

For example, a listener can assign timestamps:

```java
public class PurchaseOrderTimestampListener {
    @PrePersist
    public void beforeInsert(PurchaseOrder order) {
        Instant now = Instant.now();
        order.setCreatedAt(now);
        order.setUpdatedAt(now);
    }

    @PreUpdate
    public void beforeUpdate(PurchaseOrder order) {
        order.setUpdatedAt(Instant.now());
    }
}
```

If a field populated in a callback is required, ensure the value is reliably initialized before validation runs; you can initialize it in a constructor/factory or service instead of relying on callback ordering. Do not use callbacks to query other data to decide a value.

## 11. Limits of validation and callbacks with bulk DML

Bulk JPQL `UPDATE`/`DELETE` and native SQL run directly against the database, bypassing individual Entity lifecycles. As a result, they do not trigger per-Entity lifecycle callbacks, do not run JPA Bean Validation for each row, and do not automatically synchronize Entities currently sitting in the persistence context.

Example:

```java
@Modifying
@Query("update PurchaseOrder p set p.status = :status where p.id = :id")
int updateStatus(Long id, String status);
```

This is a bulk update; `@PreUpdate`, `@PostUpdate`, and validation on the Entity are not called for each updated row. To uphold invariants, validate inputs before running the bulk query, enforce matching constraints in the database, and consider clearing/refreshing the persistence context afterward.

Bulk operations are often useful when updating many rows, yet they bypass Entity cascades and callbacks. Do not use bulk DML when business logic depends on logic executed in callbacks or per-Entity dirty checking.

## 12. What NOT to do in callbacks

- Do not call repositories or EntityManager to read/write other Entities.
- Do not modify relationships or collections of other Entities in the persistence context.
- Do not call remote APIs, send emails, publish messages, or write files.
- Do not perform heavy computation, large batch processing, or blocking I/O.
- Do not rely on `@PostPersist`/`@PostUpdate` meaning the transaction has committed.
- Do not assume Spring dependency injection works inside listeners across every JPA provider; verify integration if you genuinely use injection.

Keep callbacks short and deterministic. Multi-step business logic belongs in the service/domain layer; post-commit side effects use transactional events, and integrations requiring guaranteed event delivery should use an outbox.

## 13. Common errors and troubleshooting

**Validation does not run when saving an Entity.** Check `spring-boot-starter-validation`, verify a provider is on the classpath, validation mode is not NONE, and the operation goes through JPA persist/update.

**API returns validation errors yet batch import still saves invalid data.** Batch import may bypass the controller. Keep constraints on the Entity/domain and validate import paths as well; bulk SQL still requires separate validation or database constraints.

**Callback timestamps are not updated.** Check whether the Entity is actually dirty and whether an update occurred. `@PreUpdate` is not a hook that runs on every setter call; it is tied to the provider's update operation.

**Message sent even though transaction rolled back.** Do not send from `@PostPersist`/`@PostUpdate`; move to `AFTER_COMMIT` or a transactional outbox.

**Relationship data is wrong after a callback.** Check whether a callback modifies associations or queries other Entities; move that logic to the service and update the owning side properly.

**Database constraint still fails even though Bean Validation passed.** Check for race conditions, unique/FK/check constraints, writes from other clients, and discrepancies between validation rules and schema. Database constraints remain the final line of defense.

## 14. Design checklist

- Use callbacks for short, technical tasks that only modify non-relationship state of the current Entity.
- Use EntityListener when callbacks need to be separated from the Entity or reused.
- Use Bean Validation to validate data at the API and during persist/update.
- Distinguish `@Valid` from JPA cascade.
- Align Bean Validation constraints with NOT NULL, CHECK, UNIQUE, and FKs in the schema.
- Do not place queries, external side effects, or heavy processing inside callbacks.
- Remember that bulk JPQL/native DML bypasses callbacks and JPA Bean Validation.
- Use `AFTER_COMMIT` for post-commit tasks; use an outbox if guaranteed event delivery is required.

EntityListener and Bean Validation complement each other: listeners handle small technical lifecycle adjustments, while validation protects data integrity. Understanding callback limits and write paths that bypass the lifecycle keeps application data consistent without introducing hard-to-control side effects.