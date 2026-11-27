# Handling Events by Transaction Phase with @TransactionalEventListener

A Spring business operation often needs to perform additional work after writing data: sending emails, invalidating caches, updating a search index, writing audit records, or notifying another module. Running side effects directly inside a service method can execute them before the database commits. If the transaction subsequently rolls back, the data does not exist yet the email or message has already been sent.

Spring provides `@TransactionalEventListener` to bind application event handling to a transaction phase. By default, listeners run at `AFTER_COMMIT`. Other phases include `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.

This mechanism enables outcome-aware handling within the same application. However, application events exist only in-process and are not a durable queue. For critical messages requiring retries or guaranteed delivery across process restarts, consider a transactional outbox or a persistent broker.

## 1. Why do we need transaction-bound events?

Example of a service creating an order and sending an email directly:

~~~java
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orders.save(
            new PurchaseOrder(command.customerId(), command.total())
    );

    emailService.sendConfirmation(order.getId());
    return order.getId();
}
~~~

The email is sent before the transaction completes. If flush or commit fails, the database rolls back, yet the email has already been sent.

Instead, publish an event inside the transaction:

~~~java
import java.time.Instant;
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orders.save(
            new PurchaseOrder(command.customerId(), command.total())
    );

    events.publishEvent(new OrderPlacedEvent(order.getId(), Instant.now()));
    return order.getId();
}
~~~

Listener:

~~~java
@Component
public class OrderNotificationListener {

    private final EmailService emailService;

    public OrderNotificationListener(EmailService emailService) {
        this.emailService = emailService;
    }

    @TransactionalEventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        emailService.sendConfirmation(event.orderId());
    }
}
~~~

Omitting the phase defaults to `AFTER_COMMIT`. The listener runs only when the transaction containing the publish call commits successfully. If the transaction rolls back, the listener does not run by default.

Spring registers event handling with transaction synchronization at publish time. The listener is invoked when the transaction reaches the chosen phase.

## 2. @EventListener vs. @TransactionalEventListener

A regular `@EventListener` processes an event as soon as it is published. By default, it runs synchronously on the publishing thread.

`@TransactionalEventListener` registers a callback bound to a transaction phase. When a suitable transaction is active, the callback is deferred until that phase.

| Feature | @EventListener | @TransactionalEventListener |
|---|---|---|
| Timing | Immediately at publish time | According to transaction phase |
| Requires transaction | No | Yes, by default |
| Distinguishes commit/rollback | Does not distinguish automatically | Can choose phase |
| Without a transaction | Still runs | Skipped by default |
| Use case | Internal events independent of commit | Side effects dependent on transaction outcome |

Two listeners can receive the same event:

~~~java
@Component
public class OrderEventListeners {

    @EventListener
    public void handleImmediately(OrderPlacedEvent event) {
        System.out.println("Event was published");
    }

    @TransactionalEventListener
    public void handleAfterCommit(OrderPlacedEvent event) {
        System.out.println("Order transaction committed");
    }
}
~~~

The regular listener runs at the publish call; the transaction-bound listener waits for the corresponding phase. Do not use a plain `@EventListener` for side effects that must only occur after commit.

## 3. The four transaction phases

The `phase` attribute accepts values from `TransactionPhase`.

### 3.1. BEFORE_COMMIT

`BEFORE_COMMIT` runs before the transaction commits. Use it when work must participate in the same transaction and roll back with the original data if it fails.

Example recording an audit entry in the same transaction:

~~~java
@Component
public class OrderAuditListener {

    private final OrderAuditRepository audits;

    public OrderAuditListener(OrderAuditRepository audits) {
        this.audits = audits;
    }

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void record(OrderPlacedEvent event) {
        audits.save(new OrderAudit(event.orderId(), "ORDER_PLACED"));
    }
}
~~~

If the listener throws a runtime exception before commit, the transaction can roll back and neither the order nor the audit record is committed.

BEFORE_COMMIT does not guarantee the transaction will definitely commit. Flush, constraints, or commit can still fail after the callback. Do not send emails or call external APIs in this phase without an appropriate compensating mechanism.

### 3.2. AFTER_COMMIT

`AFTER_COMMIT` runs only after the transaction commits successfully. This is the default phase, suitable for emails, cache invalidation, search indexing, or triggering downstream work.

~~~java
@Component
public class SearchIndexListener {

    private final SearchIndexer indexer;

    public SearchIndexListener(SearchIndexer indexer) {
        this.indexer = indexer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void index(OrderPlacedEvent event) {
        indexer.indexOrder(event.orderId());
    }
}
~~~

If the transaction rolls back, the listener does not run. If the listener fails after commit, the original business data remains committed; the callback cannot undo that outcome. Error observability and retries appropriate to the criticality of the side effect are required.

### 3.3. AFTER_ROLLBACK

`AFTER_ROLLBACK` runs when the transaction ends in rollback. It can be used to record metrics, technical logs, or trigger error-handling workflows.

~~~java
@Component
public class OrderRollbackListener {

    private final FailureMetrics metrics;

    public OrderRollbackListener(FailureMetrics metrics) {
        this.metrics = metrics;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlacedEvent event) {
        metrics.increment("order.transaction.rollback");
    }
}
~~~

The listener only receives events that were already published. If an exception occurs before the publish call, there is no event for the listener to handle. If you need to write an audit record to the database after rollback, open a new transaction; the original transaction has already ended.

### 3.4. AFTER_COMPLETION

`AFTER_COMPLETION` runs after the transaction completes, regardless of commit or rollback. Use it for cleanup or metrics independent of outcome.

~~~java
@Component
public class CompletionListener {

    private final TransactionMetrics metrics;

    public CompletionListener(TransactionMetrics metrics) {
        this.metrics = metrics;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void completed(OrderPlacedEvent event) {
        metrics.recordCompletion(event.orderId());
    }
}
~~~

If you need to distinguish success from rollback, use AFTER_COMMIT and AFTER_ROLLBACK separately. AFTER_COMPLETION does not mean the transaction succeeded.

| Phase | Timing | Purpose |
|---|---|---|
| BEFORE_COMMIT | Before commit | Work within the same transaction |
| AFTER_COMMIT | After successful commit | Side effects that run only once data is committed |
| AFTER_ROLLBACK | After rollback | Post-rollback logging or handling |
| AFTER_COMPLETION | After commit or rollback | General cleanup and metrics |

## 4. Designing event payloads

Define immutable events containing only the data listeners need. Example:

~~~java
package com.example.orders;

import java.time.Instant;

public record OrderPlacedEvent(
        Long orderId,
        Instant occurredAt) {
}
~~~

Publisher:

~~~java
import java.time.Instant;
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Long placeOrder(CreateOrderCommand command) {
        PurchaseOrder order = orders.save(
                new PurchaseOrder(command.customerId(), command.total())
        );

        events.publishEvent(
                new OrderPlacedEvent(order.getId(), Instant.now())
        );

        return order.getId();
    }
}
~~~

Publishing the event before commit is intentional. Spring waits for the phase before invoking transactional listeners.

### 4.1. Why pass IDs instead of entities?

Avoid passing entire JPA entities when listeners only need an ID:

- Entities can contain lazy associations and cause lazy loading after commit.
- Entities can mutate after the event is created.
- Entity payloads tightly couple modules to persistence mappings.
- An ID lets the listener load required state in its own transaction.

If a listener needs an exact snapshot from when the event occurred, place the required fields into an immutable event. If the listener needs the latest state, pass the ID and reload it in the listener's transaction.

### 4.2. Publishing after the primary key is available

If the ID is database-generated, ensure the ID exists before constructing the event. With some key generation strategies, `save()` assigns the ID immediately; other strategies require a flush for the insert to execute.

Do not flush just to guess at IDs when the mapping already guarantees the ID is available. Check `@GeneratedValue` and the application's key generation strategy.

## 5. Event processing lifecycle

Typical flow:

~~~text
Service opens transaction
        |
        v
Write entity
        |
        v
publishEvent(event)
        |
        +--> @EventListener runs immediately
        |
        +--> @TransactionalEventListener registers phase
        |
        v
Service method finishes
        |
        v
Spring flushes and commits
        |
        +--> Rollback --> AFTER_ROLLBACK
        |                AFTER_COMPLETION
        |
        +--> Commit ----> AFTER_COMMIT
                         AFTER_COMPLETION
~~~

BEFORE_COMMIT runs before the actual commit. After this callback, the transaction can still roll back due to flush or constraint errors.

Transaction-bound listeners are invoked synchronously by default when the transaction reaches the phase. If async is used, the callback dispatches work to an executor and requires different handling for threads and transactions.

## 6. When events are published outside a transaction

By default, `@TransactionalEventListener` requires an active transaction when the event is published. If there is no transaction, the listener is skipped.

You can enable fallback execution:

~~~java
@TransactionalEventListener(fallbackExecution = true)
public void handle(OrderPlacedEvent event) {
    // Runs immediately when there is no transaction.
}
~~~

When no transaction exists, Spring cannot enforce BEFORE_COMMIT or AFTER_COMMIT semantics. With `fallbackExecution = true`, the listener runs immediately under fallback rather than waiting for a nonexistent transaction.

Enable fallback only if business rules accept both behaviors: waiting for the phase when a transaction exists, and running immediately when none exists. If the listener is only valid after a database commit, keep the default false and ensure the publisher runs inside a transaction.

### 6.1. Checking transaction boundaries

`@Transactional` is typically applied via a Spring AOP proxy. Under default proxy configuration, self-invocation (one method calling another method in the same class) bypasses the proxy and may not open a transaction as expected.

If a listener does not run, check:

- Does the publisher actually run inside a transaction?
- Is the method invoked through a Spring bean proxy?
- Did the transaction finish before publishing?
- Are reactive transactions or thread-bound transactions being used?
- Is fallback enabled?

Do not enable fallback simply to mask a misconfigured transaction boundary.

## 7. Writing to the database after AFTER_COMMIT requires a new transaction

After AFTER_COMMIT, the original transaction has committed, but transactional resources may still be held while synchronization completes. If the listener writes to the database, the operation might participate in the old transaction's resources without any subsequent commit.

If a listener needs to write to the database after commit, open an independent transaction using `Propagation.REQUIRES_NEW`:

~~~java
@Component
public class OrderHistoryListener {

    private final OrderHistoryRepository history;

    public OrderHistoryListener(OrderHistoryRepository history) {
        this.history = history;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeHistory(OrderPlacedEvent event) {
        history.save(new OrderHistory(
                event.orderId(),
                event.occurredAt()
        ));
    }
}
~~~

REQUIRES_NEW creates a separate transaction so the history record can commit independently after the order-creation transaction.

Do not use REQUIRED propagation and assume it always starts a new transaction inside an after-completion callback. When a separate commit is needed, specify REQUIRES_NEW explicitly.

### 7.1. AFTER_ROLLBACK writing audit records

Similarly, if a post-rollback listener must write an audit record to the database, use a new transaction:

~~~java
@Component
public class RollbackAuditListener {

    private final FailureAuditRepository audits;

    public RollbackAuditListener(FailureAuditRepository audits) {
        this.audits = audits;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(OrderPlacedEvent event) {
        audits.save(new FailureAudit(
                event.orderId(),
                "ORDER_TRANSACTION_ROLLED_BACK"
        ));
    }
}
~~~

This audit record can commit even though the original business transaction rolled back. Define the meaning of the record clearly because it reflects a business attempt, not a committed order.

## 8. Combining with @Async

By default, listeners run synchronously at the transaction phase. If a listener sends emails, calls APIs, or runs slowly, it can lengthen the completion time of the transactional call.

You can dispatch using `@Async`:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Component
public class AsyncOrderNotificationListener {

    private final EmailService emailService;

    public AsyncOrderNotificationListener(EmailService emailService) {
        this.emailService = emailService;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void sendNotification(OrderPlacedEvent event) {
        emailService.sendConfirmation(event.orderId());
    }
}
~~~

The listener is triggered after commit; the method is handed off to the async executor. The async thread does not inherit the committing thread's transaction or persistence context.

If the async listener needs repositories, open a new transaction:

~~~java
@Async
@Transactional(propagation = Propagation.REQUIRES_NEW)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void updateNotificationState(OrderPlacedEvent event) {
    notificationRepository.markPending(event.orderId());
}
~~~

Place the listener in a separate bean, use a public method, and ensure calls go through the Spring proxy so AOP annotations take effect. Do not call an async/transactional method directly within the same class and expect proxies to apply automatically.

### 8.1. Async does not mean durable

`@Async` only offloads work to an executor. If the JVM stops after commit but before the executor processes the listener, in-process events can be lost.

Other risks:

- The executor fills its queue or rejects tasks.
- A worker fails midway.
- Exceptions from an async void method are not returned to the caller like synchronous calls.
- There is no durable retry by default.
- Multiple threads may complete tasks in different orders.

For important notifications, retries, error monitoring, and idempotency are needed. If events must survive process crashes, use an outbox or a persistent broker.

## 9. Transaction-bound events and the transactional outbox

`@TransactionalEventListener` binds a listener to a transaction in-process. It does not persist events to the database automatically.

Window of risk:

1. Database commit succeeds.
2. The process stops before the listener sends the message.
3. Business data exists, but external systems never received the event.

If a listener calls an external API and the API fails, Spring does not put the event back into a durable queue either.

### 9.1. The outbox pattern

Write business data and the outbox message in the same transaction:

~~~java
import java.time.Instant;
@Transactional
public Long placeOrder(CreateOrderCommand command) {
    PurchaseOrder order = orders.save(
            new PurchaseOrder(command.customerId(), command.total())
    );

    outbox.save(new OutboxMessage(
            UUID.randomUUID(),
            "ORDER_PLACED",
            order.getId().toString(),
            Instant.now()
    ));

    return order.getId();
}
~~~

Both inserts belong to the same transaction:

- Rollback: the order and outbox record roll back together.
- Commit: both exist together.
- A relay reads unsent outbox rows, publishes to the broker, and marks them sent.
- After a process restart, existing records can still be read and continued.

### 9.2. AFTER_COMMIT only as a wake-up signal for the relay

You can use a local event to wake the relay early:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void wakeOutboxPublisher(OrderPlacedEvent event) {
    outboxSignal.notifyNewMessage();
}
~~~

This is only a latency optimization. The relay must still poll the outbox periodically or have an independent recovery mechanism because in-process signals can be lost.

### 9.3. Idempotency and at-least-once delivery

The relay may send a message successfully and then crash before marking the outbox row sent. On restart, the message may be sent again. Therefore, an outbox typically provides at-least-once delivery.

Consumers need idempotent handling via event ID:

~~~java
@Transactional
public void handle(OrderPlacedMessage message) {
    if (processedMessages.existsById(message.eventId())) {
        return;
    }

    updateProjection(message);
    processedMessages.save(
            new ProcessedMessage(message.eventId())
    );
}
~~~

Recording the processed event ID and updating data in the same transaction helps prevent duplicate processing. For side effects outside the database, an idempotency key or another outbox is needed.

## 10. Ordering listeners with @Order

If multiple listeners handle the same event in the same phase, you can use `@Order`:

~~~java
@Component
public class OrderedOrderListeners {

    @Order(10)
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void validate(OrderPlacedEvent event) {
        // Runs before the listener with order 20.
    }

    @Order(20)
    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void recordAudit(OrderPlacedEvent event) {
        // Runs after the listener with order 10.
    }
}
~~~

Lower order values have higher priority. Use ordering only when a real dependency exists. `@Order` does not change transaction phases; an AFTER_COMMIT listener will not run before a BEFORE_COMMIT listener just because it has a lower order value.

With async listeners, dispatch order does not guarantee completion order. If steps depend on one another, use explicit orchestration or workflow/message processing instead of relying on thread ordering.

## 11. Transaction propagation and events

Listeners bind to the transaction active at publish time:

- `PROPAGATION_REQUIRED` usually joins the current transaction; listeners wait for that transaction to complete.
- `PROPAGATION_REQUIRES_NEW` suspends the outer transaction and opens a new one. Events published inside the new transaction are handled when the new transaction ends.
- If the REQUIRES_NEW transaction commits, its AFTER_COMMIT listener can run even if the outer transaction subsequently rolls back.

Clarify which transaction an event belongs to. With nested transactions/savepoints, semantics depend on the transaction manager and how savepoints are managed; do not treat rolling back a savepoint as a completed independent transaction. If events must fire only after the final commit, test against the real transaction manager.

## 12. Filtering conditions and event classes

`@TransactionalEventListener` inherits attributes from `@EventListener`, such as SpEL conditions and event classes.

Example handling only high-value events:

~~~java
@Component
public class HighValueOrderListener {

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT,
            condition = "#event.total() >= 1000"
    )
    public void handle(HighValueOrderEvent event) {
        // Handle high-value order.
    }
}
~~~

You can declare event classes when the listener needs no parameter:

~~~java
@TransactionalEventListener(
        classes = OrderPlacedEvent.class,
        phase = TransactionPhase.AFTER_COMMIT
)
public void handle() {
    // Takes no event argument.
}
~~~

Usually you should accept the event as a parameter because listeners need the ID or metadata.

## 13. Reactive transactions and thread-bound context

Since Spring Framework 6.1, transactional event listeners can work with thread-bound transactions via `PlatformTransactionManager` and reactive transactions via `ReactiveTransactionManager`.

The two models store context differently:

- Traditional imperative transactions are bound to a thread.
- Reactive transactions use Reactor Context rather than conventional ThreadLocal.

When publishing events in a reactive transaction, carry the transaction context with the event using `TransactionalEventPublisher`. Do not assume plain `ApplicationEventPublisher.publishEvent` calls automatically propagate Reactor Context.

Spring Data JPA uses JDBC and an imperative persistence context, so examples in this guide focus on PlatformTransactionManager. Applications using R2DBC/reactive transactions should follow the corresponding reactive event publisher documentation.

## 14. Testing transaction phases

Tests must actually commit or roll back to verify callbacks. If a test method uses default `@Transactional` and Spring Test rolls back after the test, AFTER_COMMIT listeners will not run as in a committed transaction.

Use `TransactionTemplate` to control transaction completion explicitly.

### 14.1. A probe recording phases

~~~java
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

@Component
public class TransactionPhaseProbe {

    private final List<String> calls = new CopyOnWriteArrayList<>();

    @TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
    public void beforeCommit(OrderPlacedEvent event) {
        calls.add("BEFORE_COMMIT");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlacedEvent event) {
        calls.add("AFTER_COMMIT");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void afterRollback(OrderPlacedEvent event) {
        calls.add("AFTER_ROLLBACK");
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
    public void afterCompletion(OrderPlacedEvent event) {
        calls.add("AFTER_COMPLETION");
    }

    public List<String> calls() {
        return List.copyOf(calls);
    }

    public void reset() {
        calls.clear();
    }
}
~~~

This is a test helper. For tests running in parallel, use an isolated probe per test context or synchronize state.

### 14.2. Testing commit and rollback

~~~java
import java.time.Instant;
@SpringBootTest
class TransactionalEventListenerTest {

    @Autowired
    private PlatformTransactionManager transactionManager;

    @Autowired
    private ApplicationEventPublisher events;

    @Autowired
    private TransactionPhaseProbe probe;

    @Test
    void commitRunsBeforeCommitAfterCommitAndCompletion() {
        probe.reset();

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status ->
                events.publishEvent(new OrderPlacedEvent(10L, Instant.now()))
        );

        assertThat(probe.calls()).containsExactly(
                "BEFORE_COMMIT",
                "AFTER_COMMIT",
                "AFTER_COMPLETION"
        );
    }

    @Test
    void rollbackRunsAfterRollbackAndCompletion() {
        probe.reset();

        TransactionTemplate tx =
                new TransactionTemplate(transactionManager);

        tx.executeWithoutResult(status -> {
            events.publishEvent(new OrderPlacedEvent(11L, Instant.now()));
            status.setRollbackOnly();
        });

        assertThat(probe.calls()).containsExactly(
                "AFTER_ROLLBACK",
                "AFTER_COMPLETION"
        );
    }
}
~~~

The example assumes the probe has only those four listeners and callbacks run synchronously. The commit test verifies BEFORE_COMMIT, AFTER_COMMIT, and AFTER_COMPLETION. The rollback test verifies AFTER_ROLLBACK and AFTER_COMPLETION; BEFORE_COMMIT does not run when the transaction has already been marked rollback-only before commit.

### 14.3. Testing events outside a transaction

Publishing an event outside a transaction:

~~~java
import java.time.Instant;
events.publishEvent(new OrderPlacedEvent(12L, Instant.now()));
~~~

With `fallbackExecution = false`, transactional listeners are not invoked. Write separate tests if any listeners enable fallback.

### 14.4. Testing exceptions and async

Create a BEFORE_COMMIT listener that throws an exception and verify the transaction rolls back. For an AFTER_COMMIT listener, verify business data persists even if the callback fails because commit has already finished.

With `@Async`, do not assert immediately after the transaction finishes. Use a latch, Awaitility, or test synchronization to wait for the executor; avoid fixed sleeps. For critical work, test the outbox/relay and retries rather than testing only the local callback.

## 15. Common mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Listener does not run | Published outside a transaction | Check transaction boundary or intentional fallback |
| Listener runs before commit | Using regular @EventListener | Use @TransactionalEventListener |
| Side effect occurs despite rollback | Executed before commit | Move to AFTER_COMMIT |
| DB write after AFTER_COMMIT does not persist | Using completed transaction resources | Use REQUIRES_NEW |
| Email sent even when insert fails | Sent directly in service | Send via AFTER_COMMIT |
| Async listener does not see original transaction | Runs on another thread | Open a separate transaction if needed |
| Events lost on process stop | Application events exist only in-process | Use an outbox or durable broker |
| Messages processed twice | Relay retries after crash | Use event ID and idempotent consumers |
| AFTER_COMMIT test does not run | Test transaction rolls back | Use TransactionTemplate or real commits |
| AFTER_COMPLETION mistaken for success | Phase runs on both commit and rollback | Use AFTER_COMMIT |
| Listener execution order unclear | No ordering | Use @Order or orchestration |

## 16. Implementation checklist

- [ ] Event contains only the data listeners need, usually IDs or immutable snapshots.
- [ ] Publisher runs inside a transaction if a transaction phase is required.
- [ ] Choose BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, or AFTER_COMPLETION accurately.
- [ ] BEFORE_COMMIT only performs work that must share the same transaction.
- [ ] AFTER_COMMIT is used for side effects allowed only after commit.
- [ ] Do not mistake AFTER_COMPLETION for success.
- [ ] Do not enable fallbackExecution unless running outside a transaction is acceptable.
- [ ] Do not rely on lazy entity graphs after the persistence context ends.
- [ ] DB writes after completion use REQUIRES_NEW when a separate commit is needed.
- [ ] Async listeners do not assume the original transaction propagates to another thread.
- [ ] Critical side effects have retries, idempotency, and error monitoring.
- [ ] Use an outbox for events that must survive process crashes.
- [ ] @Order is used only when a real dependency exists.
- [ ] Test commit, rollback, no-transaction, exception, and async scenarios separately.
- [ ] Test real transactions rather than relying on default-rollback tests.
- [ ] Test against the application's actual transaction manager and provider.

## 17. References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — phases, fallbackExecution, and reactive transactions.
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html) — default phase, transaction requirements, and listener attributes.
- [Spring Framework — TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html) — meaning of each phase.
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html) — before/after commit and completion callbacks, post-completion resources.
- [Spring Framework — TransactionalEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html) — propagating transaction context in reactive flows.
- [Spring Framework — @Async Support](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — executor configuration and asynchronous processing.

`@TransactionalEventListener` ties event handling to transaction outcomes and prevents side effects from running before data is committed. Choose the right phase, open a new transaction when post-completion callbacks need database writes, and do not confuse application events with durable queues. For work requiring retries or guaranteed delivery to other systems, a transactional outbox paired with idempotent consumers is a more reliable foundation.