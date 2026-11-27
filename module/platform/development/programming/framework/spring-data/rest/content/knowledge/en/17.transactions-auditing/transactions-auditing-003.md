# Executing Post-Commit Tasks with the Right Transaction Mechanism

## 1. Why wait for a transaction to commit?

In a Spring Data REST application, a request may create or update an entity through a repository exposed by the exporter. Many operations need to run only after the data has been committed, for example:

- Sending confirmation emails or notifications.
- Sending messages to a broker or calling another system.
- Writing supplemental audits, updating search indexes, or updating caches.
- Starting a downstream workflow.

If you perform these tasks immediately after `repository.save()` but before the transaction ends, external systems may receive information about a change that is subsequently rolled back. For instance, a message is sent while the order record does not exist because the transaction failed.

Spring provides transaction-bound events to attach a listener to a specific phase. For tasks that must only run when data has committed successfully, the standard choice is `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`.

## 2. Distinguishing Spring Data REST repository events from transaction phases

The Spring Data REST exporter publishes events during the entity operation lifecycle:

| Event | Timing in the exporter lifecycle |
|---|---|
| BeforeCreateEvent | Before creating the entity |
| AfterCreateEvent | After the entity creation step |
| BeforeSaveEvent | Before saving the entity |
| AfterSaveEvent | After the entity save step |
| BeforeLinkSaveEvent | Before saving the association |
| AfterLinkSaveEvent | After the association save step |
| BeforeDeleteEvent | Before deleting the entity |
| AfterDeleteEvent | After the entity deletion step |

You can receive these events using `ApplicationListener`, `AbstractRepositoryEventListener`, or a handler annotated with `@RepositoryEventHandler` and annotations such as `@HandleBeforeSave` and `@HandleAfterSave`.

The name AfterSaveEvent describes a point in the Spring Data REST lifecycle. It is not a transaction phase and does not by itself prove that a transaction enclosing the request has committed. Likewise, the fact that Spring application events are published synchronously only means the listener runs on the publishing thread; it does not mean the database transaction has completed.

When you need to guarantee a task runs only after commit, you must ensure the event is published inside an active transaction. Without a transaction, `@TransactionalEventListener` does not run by default. Do not enable `fallbackExecution=true` just to mask the absence of a transaction, because the listener may then run even when no commit occurred.

## 3. Recommended approach: publish the event inside a @Transactional service

Consider using a service as the transaction boundary. The service saves the Order and publishes the event within the same transaction. A listener registered with the `AFTER_COMMIT` phase runs only after the transaction commits successfully.

Events should be immutable data carrying the ID or minimal snapshot needed:

~~~java
public record OrderCreated(Long orderId) {
}
~~~

Service executing the business operation:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher eventPublisher;

    public OrderApplicationService(
            OrderRepository orderRepository,
            ApplicationEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    @Transactional
    public Long createOrder(CreateOrderCommand command) {
        Order order = Order.create(command);
        Order saved = orderRepository.save(order);

        eventPublisher.publishEvent(new OrderCreated(saved.getId()));

        return saved.getId();
    }
}
~~~

Listener running after commit:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderCreatedListener {

    private final OrderNotificationService notificationService;

    public OrderCreatedListener(OrderNotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderCreated event) {
        notificationService.sendConfirmation(event.orderId());
    }
}
~~~

Processing flow:

1. The request calls OrderApplicationService through the Spring bean proxy.
2. The transaction begins.
3. The repository saves the entity.
4. ApplicationEventPublisher publishes OrderCreated; the listener is registered to wait for the AFTER_COMMIT phase.
5. If the transaction commits, the listener is invoked.
6. If the transaction rolls back, the AFTER_COMMIT listener is not invoked.

If there are multiple transaction managers, ensure the service and event listener bind to the exact transaction containing the data save. You can specify `transactionManager` on `@Transactional` when the application has multiple managers.

## 4. Choosing the right phase

@TransactionalEventListener supports four phases:

| Phase | When the listener runs | Use cases |
|---|---|---|
| BEFORE_COMMIT | Before commit | Validation or preparatory work that must complete prior to commit |
| AFTER_COMMIT | After a successful commit; this is the default | Sending notifications, emitting external events after data is persisted |
| AFTER_ROLLBACK | After rollback | Recording or alerting on a failed transaction |
| AFTER_COMPLETION | After the transaction finishes, whether committed or rolled back | Cleaning up resources or handling logic requiring transaction completion |

Example that runs only on rollback:

~~~java
@Component
public class OrderRollbackListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void handle(OrderCreated event) {
        // Record appropriate metrics or logs.
    }
}
~~~

If no transaction is active at publish time, a transaction-bound listener is skipped by default. Setting `fallbackExecution=true` allows handling even when there is no transaction:

~~~java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void handle(OrderCreated event) {
    // Use only when handling outside a transaction is also valid.
}
~~~

When the strict requirement is to run only after commit, keep `fallbackExecution` at its default value `false` and fix the publication point to ensure a transaction is active.

## 5. Connecting with Spring Data REST

### 5.1. Use @RepositoryEventHandler when hooking into exporter requests

You can publish an application event from an annotated repository handler:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.rest.core.annotation.HandleAfterCreate;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler
public class OrderRepositoryEventHandler {

    private final ApplicationEventPublisher eventPublisher;

    public OrderRepositoryEventHandler(ApplicationEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @HandleAfterCreate
    public void afterCreate(Order order) {
        eventPublisher.publishEvent(new OrderCreated(order.getId()));
    }
}
~~~

Then use `OrderCreatedListener` from above to handle it according to the transaction phase. This approach satisfies the AFTER_COMMIT guarantee only when the event handler publishes inside an active transaction. Check the actual request flow of your Spring Data REST version and transaction manager. If the handler is invoked outside a transaction, the listener will not run when `fallbackExecution=false`.

Do not invoke email, HTTP APIs, or brokers directly inside `@HandleAfterCreate` or `@HandleAfterSave` if the requirement is to execute only after commit. Repository handlers are lifecycle hooks; `@TransactionalEventListener` is the mechanism that binds a listener to a transaction phase.

### 5.2. Use @DomainEvents on an aggregate root

Spring Data supports aggregate roots publishing domain events when eligible repository methods are invoked. `@DomainEvents` marks a method that returns an event or collection of events; `@AfterDomainEventPublication` marks a callback to clear the list after publication.

Condensed example:

~~~java
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class Order {

    private Long id;
    private final List<Object> domainEvents = new ArrayList<>();

    public void markCreated() {
        domainEvents.add(new OrderCreated(id));
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
~~~

Spring Data invokes these methods when supported repository operations such as save, saveAll, delete, and deleteAll are called with an aggregate instance. `deleteById` is excluded because the implementation may delete via a query without loading the aggregate instance.

Domain events help collect events raised by aggregate behavior. For a listener to run only after commit, you must still ensure the event is published within an active transaction and handled by `@TransactionalEventListener`. For endpoints generated by the Spring Data REST exporter, test the actual HTTP path rather than testing the repository in isolation.

### 5.3. Use a custom controller/service when explicit transaction boundaries are needed

If a business endpoint requires multiple operations, a custom `@RepositoryRestController` can call a `@Transactional` service. That service performs repository updates and publishes the event within the same transaction. This is the easiest approach to control when you must be certain that persistence and event publication share the same transaction.

Do not place `@Transactional` on a method and call that method from another method on the same instance expecting the proxy to open a new transaction. Under default proxy mode, self-invocation does not pass through the proxy. Call the service through another Spring bean or organize the transaction on a public method called from outside.

## 6. Post-commit data and transaction considerations

### 6.1. Pass only necessary data in the event

Pass IDs or immutable snapshots instead of keeping JPA entities with lazy associations. After commit, the persistence context may be closed; a listener accessing lazy associations can encounter a LazyInitializationException or trigger unintended queries.

For example, the event can hold `orderId`, `customerId`, `eventId`, and the version of data to process. The listener can reload data using a separate service if needed.

### 6.2. Writing to the database inside a listener requires a new transaction

After the AFTER_COMMIT callback runs, the original transaction has committed. However, transaction resources may still be bound and accessible during the callback. A new database write may join the old resource without a subsequent commit.

If the listener needs to write to the database, call a separate service bean with `REQUIRES_NEW` propagation:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderAuditWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordPublished(Long orderId) {
        // Write the audit in a new transaction.
    }
}
~~~

Separating into another bean ensures the call passes through the transaction proxy. Do not call a `REQUIRES_NEW` method on the same object expecting the proxy to trigger.

### 6.3. Listener failures cannot roll back committed data

When an AFTER_COMMIT listener runs, the original data has already committed. If sending an email or calling an external API fails, the original transaction cannot be rolled back. With a synchronous listener, an exception may propagate back to the caller even though the database committed, causing the HTTP request to return an error while the data is already persisted.

Therefore:

- Decide explicitly whether post-commit failures are allowed to affect the HTTP response.
- Catch and log errors with context/correlation IDs; do not pretend the original transaction rolled back.
- For retryable work, use bounded retries, backoff, and a dead-letter/failed state.
- Make listeners idempotent so reprocessing an event does not produce duplicate side effects.

### 6.4. Run asynchronously when work is time-consuming

You can combine `@Async` with a transaction-bound listener to offload heavy work to an executor after the transaction commits:

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AsyncOrderCreatedListener {

    @Async("applicationTaskExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(OrderCreated event) {
        // Handle slow tasks after commit.
    }
}
~~~

Enable async processing with `@EnableAsync` and configure an executor with appropriate thread bounds, queue capacity, shutdown policy, and monitoring. `@Async` does not provide a durable queue or retry guarantees by itself. If the process stops after commit but before the task executes, in-memory events can be lost.

## 7. When do you need a Transactional Outbox?

`@TransactionalEventListener` fits post-commit tasks within the same application when the risk of listener failure or process termination after commit is acceptable.

If you must guarantee that a database change turns into a durable message, consider the Transactional Outbox pattern:

1. In the same business transaction, save the entity and insert an outbox record containing event ID, type, payload, createdAt, and status.
2. Transaction commit ensures both the entity and the outbox record exist together or roll back together.
3. A worker/CDC publisher reads unsent outbox records and forwards messages to the broker.
4. After successful delivery, update the status or offset as designed.
5. Consumers process idempotently by event ID because retries can produce at-least-once delivery.

Outbox does not merge broker delivery and database commit into a single distributed transaction; it persists the intent to publish inside the same database transaction so delivery can be retried after failures. For critical emails, webhooks, or messages, outbox is generally far more reliable than an in-memory callback.

## 8. TransactionSynchronization for low-level callbacks

If you need to register a callback programmatically instead of via application events, Spring provides `TransactionSynchronization`:

~~~java
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Runs after a successful commit.
            }
        }
    );
}
~~~

This approach is useful for low-level integration, though you must manually guard registration with active synchronization and avoid holding unnecessary entities/resources. For domain events and decoupled listeners, `@TransactionalEventListener` is usually clearer.

## 9. Testing commit and rollback

Tests must verify that the listener runs only after commit and does not run on rollback. A common mistake is marking the test `@Transactional`: Spring Test rolls back the test transaction by default when it finishes, so AFTER_COMMIT listeners do not run.

Example using `TestTransaction` to commit explicitly:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.transaction.TestTransaction;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Transactional
class OrderAfterCommitTests {

    @Autowired
    OrderApplicationService orderService;

    @Autowired
    OrderEventProbe eventProbe;

    @Test
    void listenerRunsOnlyAfterCommit() {
        Long orderId = orderService.createOrder(new CreateOrderCommand(/* fields */));

        assertThat(eventProbe.receivedOrderIds()).doesNotContain(orderId);

        TestTransaction.flagForCommit();
        TestTransaction.end();

        assertThat(eventProbe.receivedOrderIds()).contains(orderId);
    }
}
~~~

`OrderEventProbe` is a test component injected into the test to record handled events. Add rollback tests by starting a transaction and flagging rollback or throwing a RuntimeException before commit; assert that the AFTER_COMMIT listener is not called.

Points to test:

- The event is published while a transaction is active.
- The listener runs after commit and does not run after rollback.
- Without a transaction, the listener is skipped when `fallbackExecution=false`.
- The actual Spring Data REST endpoint triggers the event through the expected path.
- The listener can run multiple times without sending duplicate notifications or creating duplicate records.
- If the listener writes to the database, the `REQUIRES_NEW` transaction actually commits.
- Tests do not unintentionally leave transactions open or rolled back at test end.

## 10. Common errors

| Symptom | Common cause | Resolution |
|---|---|---|
| @TransactionalEventListener does not run | No transaction at publish time or transactions not enabled | Check the transaction manager and event publish site; do not enable fallbackExecution to hide the bug |
| Listener runs before data commits | Using @EventListener or invoking tasks directly inside repository handler | Switch to @TransactionalEventListener(AFTER_COMMIT) |
| Listener still runs on transaction rollback | Using a regular listener or the wrong phase | Use AFTER_COMMIT phase and test rollback |
| AfterSaveEvent mistaken for after commit | Confusing lifecycle events with transaction synchronization | Inspect actual transactions and bind listeners by phase |
| @Transactional has no effect | Self-invocation, call bypasses proxy, bean not managed by Spring, or missing transaction manager | Invoke through a bean proxy and check configuration |
| Checked exceptions do not roll back | Spring rolls back RuntimeException and Error by default; checked exceptions do not auto-rollback | Declare appropriate rollbackFor or design explicit exceptions |
| Listener writes to DB, but data is not saved | Post-commit callback uses old transaction resources without another commit | Call a separate service with Propagation.REQUIRES_NEW |
| HTTP returns an error, yet data still exists | Synchronous listener throws after database commit | Handle post-commit failures, retry, or use outbox; do not treat error response as rollback |
| Duplicate messages sent on retry | Consumer or listener is not idempotent | Use event IDs, unique constraints, and deduplication |
| Events lost when application stops | Callback or @Async task exists only in memory | Use transactional outbox with a retrying worker/CDC |
| Test does not receive events | Test transaction rolls back by default | Commit via TestTransaction or test without an outer transaction |

## 11. Implementation checklist

1. Identify the transaction enclosing the repository write operation and the active transaction manager.
2. Publish an immutable application/domain event inside that transaction.
3. Use @TransactionalEventListener with AFTER_COMMIT for tasks that must run only after commit.
4. Keep fallbackExecution=false if processing without a transaction must be disallowed.
5. For Spring Data REST event handlers, check the active transaction on the real endpoint; do not infer from the AfterSaveEvent name.
6. For post-commit database writes, call a separate service using REQUIRES_NEW.
7. For slow tasks, configure an executor and retry/monitoring; for critical deliveries, use an outbox.
8. Test commit, rollback, missing transaction, and the Spring Data REST HTTP path.

## Official documentation

- [Spring Framework – Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework – Transaction Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework – TransactionSynchronization API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Data REST – Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST – RepositoryEventHandler API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryEventHandler.html)
- [Spring Data Commons – Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html)
- [Spring Framework – @TransactionalEventListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework – TransactionalEventPublisher API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventPublisher.html)
