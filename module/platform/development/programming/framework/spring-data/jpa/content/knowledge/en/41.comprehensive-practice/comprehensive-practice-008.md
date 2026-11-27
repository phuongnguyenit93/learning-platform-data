# Combining Auditing, Change History, and Domain Events

A Spring Data JPA application often needs to answer three questions: who created or last modified the current record, what versions the data transitioned through over time, and what business event just occurred so other components can react. These three needs are related, yet they do not share a single mechanism.

- **Auditing metadata** stores current creation/modification metadata on the entity, such as creator, creation timestamp, last modifier, and last modification timestamp.
- **Change history (audit history)** records historical revisions or an audit trail so data can be inspected as of an earlier point in time.
- **Domain events** describe meaningful business occurrences, such as an order being confirmed or an account being locked.

A sound design coordinates all three within the same transaction boundary when consistency is needed. At the same time, choose durable storage when history or messages must never be lost.

## 1. Distinguishing the Three Layers of Data

For example, when an order is confirmed:

| Requirement | Example Data | Appropriate Mechanism |
|---|---|---|
| Who modified it last and when? | `lastModifiedBy`, `lastModifiedDate` | Spring Data JPA Auditing |
| Which revisions did the order's status and fields go through? | Revision 1: `NEW`; Revision 2: `CONFIRMED` | Hibernate Envers or a dedicated history table |
| Other systems need to react to order confirmation | `OrderConfirmed` | Domain events and listeners |
| Messages must still be delivered after a process crash | Unpublished record in outbox | Transactional outbox |

Do not use a `lastModifiedDate` field as a substitute for history. That field only records the most recent edit; after the next update, the prior value is overwritten.

Similarly, a domain event is not automatically audit history. An event might carry only an ID and a new status, omitting full before/after field values. Conversely, entity revisions do not necessarily express the business semantics other services need to know.

## 2. Storing Creation and Modification Metadata with Spring Data JPA Auditing

Spring Data JPA Auditing uses an entity listener to populate audit fields as the entity moves through the JPA lifecycle. Four common annotations:

- `@CreatedBy`: the actor who created the entity.
- `@CreatedDate`: when the entity was created.
- `@LastModifiedBy`: the actor who last modified the entity.
- `@LastModifiedDate`: when the entity was last modified.

Example entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

import java.time.Instant;
import java.util.UUID;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class PurchaseOrder {

    @Id
    @GeneratedValue
    private UUID id;

    private String status;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdDate;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedDate;

    // constructors, getters and business methods
}
```

Enable auditing and provide the current actor:

```java
@Configuration
@EnableJpaAuditing(auditorAwareRef = "auditorAware")
public class JpaAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware(CurrentActor currentActor) {
        return () -> currentActor.username();
    }
}
```

`CurrentActor` is an application abstraction that resolves the current identity, typically from Spring Security or a background-task context. Define a clear policy for batch jobs and service accounts; avoid leaving the actor null or using a generic dummy account for everything if accurate traceability is needed.

Key notes:

- Audit fields must be mapped to the entity and matching columns.
- `AuditorAware` returns `Optional<T>`; type `T` must match the types of `@CreatedBy` and `@LastModifiedBy`.
- `@EnableJpaAuditing` has a `modifyOnCreate` option; by default, modified fields may also be populated on creation.
- The auditing listener runs when operations trigger JPA lifecycle callbacks. Bulk JPQL, native SQL, JDBC, and SQL from external applications can bypass the listener.
- Audit fields are not tamper-proof controls. Anyone with direct database write privileges can alter them.

## 3. Recording Entity History with Hibernate Envers

If you need to inspect entity state across revisions, Hibernate Envers is a common choice. Envers integrates with Hibernate and creates audit tables for entities annotated with `@Audited`.

Add the Envers dependency compatible with the Hibernate version managed by Spring Boot. Do not upgrade Hibernate Envers independently to a version different from the application's Hibernate ORM version.

Annotate the entity:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import org.hibernate.envers.AuditTable;
import org.hibernate.envers.Audited;
import org.hibernate.envers.NotAudited;

@Entity
@Audited
@AuditTable(value = "purchase_order_aud")
public class PurchaseOrder {

    @Id
    private UUID id;

    private String status;

    private String customerReference;

    @NotAudited
    private String transientIntegrationCache;

    // mapping and business methods
}
```

When the entity is mutated through Hibernate ORM within a transaction, Envers writes a revision to the corresponding audit table. Typically Envers creates a revision metadata table (often `REVINFO` by default) and an entity audit table recording revision information and modification type. Table names, schemas, and structures are configurable.

You can query revisions with `AuditReader`:

```java
AuditReader reader = AuditReaderFactory.get(entityManager);

List<Number> revisions =
        reader.getRevisions(PurchaseOrder.class, orderId);

PurchaseOrder oldVersion =
        reader.find(PurchaseOrder.class, orderId, revisions.get(0));
```

This snippet is illustrative, requires an appropriate persistence context, and needs imports for `org.hibernate.envers.AuditReader` and `AuditReaderFactory`. `getRevisions()` returns the entity's revision numbers; `find()` reads the entity's state at a specific revision. For associations, collections, and related entities, choose appropriate audit and fetch strategies so you understand the exact snapshot stored.

Envers is useful when you need to:

- Inspect an entity's state at a prior revision.
- Trace who changed data and when the revision occurred.
- Compare data across updates.
- Support incident investigations or compliance auditing requirements.

Envers does not turn every database operation into a revision automatically. Bulk DML, native SQL, direct JDBC, stored procedures, or tools outside Hibernate can bypass ORM event hooks and produce no Envers history. If a system has multiple write paths, govern every path or use database-level auditing.

## 4. Attaching the Actor to Revision History

Spring Data Auditing writes the actor onto the entity's attributes. Envers maintains separate revision metadata. To record who created each revision, define a custom revision entity and revision listener that pulls the actor from a trusted context.

Example custom revision structure:

```java
@Entity
@Table(name = "audit_revision")
@RevisionEntity(AuditRevisionListener.class)
public class AuditRevision {

    @Id
    @GeneratedValue
    @RevisionNumber
    private int id;

    @RevisionTimestamp
    private long timestamp;

    private String actor;
}
```

The revision listener retrieves the actor when Hibernate creates a revision:

```java
public class AuditRevisionListener
        implements RevisionListener {

    @Override
    public void newRevision(Object revisionEntity) {
        AuditRevision revision = (AuditRevision) revisionEntity;
        revision.setActor(CurrentActorHolder.currentActor());
    }
}
```

This is an illustrative skeleton; `CurrentActorHolder` is an application component you must implement to handle both request threads and background jobs safely. Import the annotations and interfaces from `org.hibernate.envers` along with the relevant JPA annotations. With Spring Security, extract the principal from the active context and define a system actor for jobs.

For consistent metadata, use the same actor source for both `AuditorAware` and the Envers revision listener. However, these two callbacks can run at different points in the lifecycle; avoid switching the actor context mid-transaction.

Do not store passwords, tokens, session IDs, or unnecessary personally identifiable data in revisions. Store only stable actor identifiers aligned with your system's security and retention policies.

## 5. Publishing Domain Events from the Aggregate Root

A domain event represents a meaningful business occurrence. For example, `OrderConfirmed` might trigger sending a notification, updating a read model, or starting fulfillment.

Spring Data supports events via `AbstractAggregateRoot` or the `@DomainEvents` and `@AfterDomainEventPublication` annotations. Example using `AbstractAggregateRoot`:

```java
import org.springframework.data.domain.AbstractAggregateRoot;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import java.util.UUID;

@Entity
public class PurchaseOrder
        extends AbstractAggregateRoot<PurchaseOrder> {

    @Id
    private UUID id = UUID.randomUUID();

    private String status = "NEW";

    protected PurchaseOrder() {
    }

    public void confirm() {
        if (!"NEW".equals(status)) {
            throw new IllegalStateException(
                    "Only a new order can be confirmed");
        }

        status = "CONFIRMED";
        registerEvent(new OrderConfirmedEvent(id));
    }

    public UUID getId() {
        return id;
    }
}
```

Events should be immutable payloads:

```java
public record OrderConfirmedEvent(UUID orderId) {
}
```

Generating the ID before persisting lets the event reference the aggregate even before the database assigns an ID. If using database-generated IDs, design event creation timing so the ID already exists.

Repository:

```java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, UUID> {
}
```

Spring Data publishes domain events when a supported repository operation—such as `save()` or `saveAll()`—is called on the aggregate root. `AbstractAggregateRoot` manages the event list and clears events after publication. With custom `@DomainEvents` methods, `@AfterDomainEventPublication` likewise signals only that events were published to the `ApplicationContext`; it does not prove the transaction committed.

## 6. Coordinating Auditing, Envers, and Domain Events in One Transaction

The service is the right place to define business transaction boundaries:

```java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void confirm(UUID orderId) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.confirm();

        // Repository save triggers Spring Data domain-event publication.
        // Entity is managed; JPA dirty checking writes status on flush.
        orders.save(order);
    }
}
```

When the transaction commits successfully:

1. The service loads the aggregate and executes the state transition.
2. The Spring Data repository publishes the domain event to the `ApplicationContext`.
3. Spring Data Auditing populates creation/modification metadata via JPA lifecycle callbacks.
4. Hibernate Envers writes a revision for the entity change.
5. Transaction commit confirms both entity changes and the revision in the same transaction.
6. `AFTER_COMMIT` listeners run after commit succeeds.

Both auditing metadata and Envers revisions execute within the Hibernate/JPA transaction lifecycle. If the transaction rolls back, entity changes and Envers revisions in that transaction also roll back. `AFTER_COMMIT` listeners do not run.

Note a timing detail: `@LastModifiedDate` and `@LastModifiedBy` may be populated during lifecycle callbacks at flush time. Domain events are published at the repository call, which can happen before flush. Therefore, do not build event payloads by reading JPA-populated audit fields assuming they already hold new values. Put the required business data in the event; if you genuinely need the revision's timestamp or actor, define an explicit metadata source or read after flush within the same transaction with a clear understanding of the lifecycle.

When an entity is already managed, dirty checking normally suffices to persist changes; calling `save()` is not strictly required by JPA. However, Spring Data domain-event publication is tied to repository operations. When using `AbstractAggregateRoot` to register events, invoke a supported repository operation such as `save()` so Spring Data collects and publishes the events.

## 7. Executing Side Effects Only After Commit

Standard `@EventListener` listeners run immediately when the event is published. If a listener sends an email or calls an external API and the originating transaction then rolls back, that side effect is not automatically undone.

Use `@TransactionalEventListener` when a listener must react based on the transaction outcome:

```java
@Component
public class OrderConfirmedListener {

    private final NotificationService notifications;

    public OrderConfirmedListener(
            NotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void onOrderConfirmed(OrderConfirmedEvent event) {
        notifications.sendConfirmation(event.orderId());
    }
}
```

Main phases:

| Phase | Behavior |
|---|---|
| `BEFORE_COMMIT` | Runs before commit; the transaction can still roll back afterward |
| `AFTER_COMMIT` | Runs after a successful commit; this is the default phase |
| `AFTER_ROLLBACK` | Runs after the transaction rolls back |
| `AFTER_COMPLETION` | Runs after transaction completion, whether committed or rolled back |

By default, `@TransactionalEventListener` does not execute if an event is published outside a transaction. `fallbackExecution = true` allows it to run immediately when no transaction is active, though that does not create a commit or provide `AFTER_COMMIT` guarantees.

If a synchronous `AFTER_COMMIT` listener needs to write to the database, call a separate transactional service configured with `Propagation.REQUIRES_NEW`. The originating transaction has already committed; do not rely on the old transaction's resources to commit additional writes.

You can combine `@Async` with `@TransactionalEventListener(AFTER_COMMIT)` to offload work to an executor after commit. Imperative transactions are bound to the current thread and do not propagate automatically to async threads. If the async worker needs database writes, open a fresh transaction inside the service called from that thread.

## 8. When Is a Transactional Outbox Needed?

`@TransactionalEventListener(AFTER_COMMIT)` guarantees execution timing, not durable event persistence. Consider this failure scenario:

1. The order transaction and Envers revision commit successfully.
2. The process crashes immediately after commit.
3. The listener never sends the notification or publishes the message.
4. The order is saved, yet the message is never delivered.

If losing events is unacceptable, use a transactional outbox. In the same business transaction, write an outbox record:

```java
@Transactional
public void confirm(UUID orderId) {
    PurchaseOrder order = orders.findById(orderId)
            .orElseThrow();

    order.confirm();
    orders.save(order);

    outboxRepository.save(
            OutboxEvent.pending(
                    UUID.randomUUID(),
                    "OrderConfirmed",
                    orderId.toString()
            )
    );
}
```

The example above illustrates the pattern; `OutboxEvent.pending(...)` and the outbox entity/repository are application components to define. The outbox record and order changes commit or roll back atomically.

A worker/relay polls unpublished records, publishes them to the message broker, and marks them published. The design needs:

- A unique event ID so consumers can detect duplicate messages.
- A status (`pending`/`published`) or publish timestamp.
- Attempt counts, retry schedules, and dead-letter handling for persistent failures.
- A claim/lock mechanism so multiple workers do not process the same record concurrently by mistake.
- Idempotent consumers, because delivery is typically at-least-once.
- Retention and cleanup policies for completed outbox rows.

An outbox durably records the intent to emit an event in the same transaction as business data. It does not by itself guarantee exactly-once processing in downstream receivers; consumers still need idempotency.

## 9. Bulk DML and Non-Hibernate Writes Create Audit Gaps

JPQL bulk `UPDATE`/`DELETE`, native SQL, JDBC, stored procedures, and external applications can bypass JPA lifecycle listeners and Hibernate Envers. This creates three risks:

- `@LastModifiedBy` and `@LastModifiedDate` are not automatically updated.
- Envers may record no revision for that change.
- Domain events are not created automatically because aggregate methods and repository event publication do not run.

If you use bulk updates, update audit columns explicitly in the statement and implement separate history tracking if required. Bulk DML also does not automatically synchronize Entities sitting in the persistence context and does not enforce optimistic locking via `@Version` the way regular entity updates do.

If multiple applications or tools write to the same table and auditing must cover every write path, consider database triggers, temporal tables, database audit logs, or CDC. These capture changes at the database layer, though they do not infer high-level business meaning such as `OrderConfirmed`. You can combine database history with application-emitted domain events, provided you establish an authoritative source for actor, timestamp, and event semantics.

## 10. Consistency Rules for Actor, Timestamps, and History Data

To correlate current records, revisions, and events cleanly:

- Use one reliable actor identity source across user requests, batch jobs, and background tasks.
- Normalize timestamps—typically using `Instant` stored in UTC.
- Include aggregate ID, event ID, and correlation/trace ID in events or metadata as appropriate.
- Never edit past revisions to "rewrite history"; if a correction is needed, create a new change with a reason and actor.
- Specify explicitly which fields Envers audits and which use `@NotAudited`.
- Protect audit and outbox tables with dedicated access controls, retention policies, and backups.
- Avoid storing secrets, tokens, or unnecessary personal data in event payloads and history.
- Define retention and deletion policies aligned with legal and business obligations.

If you need semantic before/after records—such as "who raised the credit limit from 10M to 15M and why"—create a supplementary business audit log table. Envers stores state revisions; the business audit log records intent and business context. Avoid stuffing sensitive fields into domain events solely for debugging convenience.

## 11. Integration Testing All Three Mechanisms

Test against a real database or Testcontainers using the target deployment engine, especially when using Envers, triggers, native SQL, or an outbox.

Critical scenarios:

1. **Create entity:** `createdBy`/`createdDate` are populated; Envers creates a revision; event is published and the `AFTER_COMMIT` listener runs after commit.
2. **Update entity:** `lastModifiedBy`/`lastModifiedDate` update; Envers writes a new revision; event reflects the business action.
3. **Rollback:** entity changes and the transaction's Envers revision roll back; `AFTER_COMMIT` listener does not run; `AFTER_ROLLBACK` listener can run.
4. **No active transaction:** `AFTER_COMMIT` listener does not run by default; test separately if `fallbackExecution` is enabled.
5. **Process/event failure:** outbox row persists after transaction commit; relay worker can retry; consumers handle duplicate deliveries safely.
6. **Bulk/native/JDBC:** verify auditing and Envers do not automatically record these like standard Hibernate writes; verify alternative audit mechanisms.
7. **Actor context:** user requests, batch jobs, and async workers record the expected actor per contract.
8. **Permissions and retention:** business users cannot arbitrarily alter/delete audit history or read unauthorized data.

Do not just assert that a method was called. Re-read the entity, revision, and outbox from a fresh transaction/persistence context to confirm data committed accurately.

## 12. Choosing an Architecture by Requirement

| Requirement | Recommended Design |
|---|---|
| Only need creator and last modifier | Spring Data JPA Auditing |
| Need to inspect entity snapshots by revision | Hibernate Envers |
| Need to know what business action occurred | Domain events |
| Only need an in-process listener after commit | `@TransactionalEventListener(AFTER_COMMIT)` |
| Need background processing after commit | `AFTER_COMMIT` combined with `@Async` and error monitoring |
| Cannot lose messages if process stops | Transactional outbox and durable relay |
| Multiple write paths outside Hibernate | Triggers, temporal/audit tables, or CDC; supplement with domain events where business intent is known |

## Conclusion

Spring Data JPA Auditing answers who created or last edited the current record; Envers or history tables preserve revisions; domain events communicate business actions for other components to react to. Keep entity changes, revisions, and outbox records inside the same transaction when consistency is required. Use `AFTER_COMMIT` for side effects that must happen only after data is saved, and use a transactional outbox when messages must be delivered durably. Test rollbacks, bulk DML, actor context, and non-Hibernate write paths so you know precisely what is recorded.