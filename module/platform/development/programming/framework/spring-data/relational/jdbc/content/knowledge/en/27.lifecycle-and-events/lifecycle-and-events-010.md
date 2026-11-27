# @TransactionalEventListener, Post-Commit Processing, and Event Reliability

In a Spring Data Relational JDBC application, a use case often writes an aggregate to the database and then needs to perform follow-up work: sending a confirmation email, emitting notifications, updating a read model, or sending a message to another system. Performing that work before the transaction commits risks publishing information about a change that ultimately rolls back. Running it simply after the service method finishes still does not guarantee the transaction committed successfully.

`@TransactionalEventListener` lets you bind a listener to a specific phase of a transaction. By default, the listener runs after the transaction commits successfully. This is useful when reacting to a persisted change. However, **running after commit does not mean reliable event delivery**: the process can still stop after commit but before the listener runs, or the listener can fail after data has committed.

This lesson explains how to publish events inside a transaction, the phases of `@TransactionalEventListener`, error and async behavior, writing follow-up data using a new transaction, and the transactional outbox to ensure events are not lost when the application crashes.

## 1. Why process events after commit?

Suppose a customer places an order. The service creates the order aggregate and saves the root and order lines. After the order is created, the application needs to:

- Send a confirmation email.
- Update a read model for the order history screen.
- Publish a message for the shipping service.
- Record activity in an analytics system.

These tasks depend on the outcome of writing the order. If the order has not committed yet, a listener might send an email or message about an order the transaction ultimately never saved.

Unsafe flow:

~~~text
BEGIN TRANSACTION
  save PurchaseOrder
  send OrderCreated to broker
  INSERT order_line -> constraint error
ROLLBACK

Broker received the event, yet the order does not exist.
~~~

If the listener is only invoked after commit:

~~~text
BEGIN TRANSACTION
  save PurchaseOrder
  publish application event
COMMIT
  |
  v
AFTER_COMMIT listener
  |
  +--> send email / update read model / notify
~~~

When the transaction rolls back, the `AFTER_COMMIT` listener does not run. That prevents listeners from reacting to uncommitted data.

## 2. Application events and transactional events

Spring has an application event mechanism:

~~~java
publisher.publishEvent(new OrderCreated(orderId));
~~~

A regular listener uses `@EventListener`:

~~~java
@EventListener
public void onOrderCreated(OrderCreated event) {
    // handles immediately when the event is published
}
~~~

`ApplicationEventPublisher.publishEvent` dispatches the event in the current flow. With a regular listener, the listener method runs during publication; publishing does not automatically wait for transaction commit.

`@TransactionalEventListener` registers the listener with the active transaction synchronization so Spring invokes it in the chosen phase:

~~~java
@TransactionalEventListener
public void onOrderCreated(OrderCreated event) {
    // runs after commit by default
}
~~~

The default phase is `TransactionPhase.AFTER_COMMIT`. If there is no active transaction, the listener is not executed by default. The `fallbackExecution` attribute can alter this behavior.

### 2.1. Events should represent something that happened

Events typically use past-tense names to express a fact:

- `OrderCreated`.
- `OrderConfirmed`.
- `PaymentCaptured`.
- `InventoryReserved`.

An event should carry the minimal data listeners need, typically the aggregate ID, event ID, and a few necessary immutable values.

~~~java
import java.time.Instant;
import java.util.UUID;

public record OrderCreated(
        UUID eventId,
        Long orderId,
        String orderNumber,
        Instant occurredAt
) {
}
~~~

Using a record keeps the payload immutable and easy to pass between components. Avoid putting an entire mutable entity/aggregate into an event if the listener only needs the ID; the listener can load the latest data when it runs. If the listener needs the exact snapshot at the time the event occurred, include those required snapshot values in the payload and define semantics clearly.

### 2.2. Publishing events inside a transaction

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            ApplicationEventPublisher events
    ) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public PurchaseOrder create(CreateOrderCommand command) {
        PurchaseOrder order = PurchaseOrder.create(
                command.orderNumber(),
                command.lines()
        );

        PurchaseOrder saved = orders.save(order);

        events.publishEvent(new OrderCreated(
                UUID.randomUUID(),
                saved.getId(),
                saved.getOrderNumber(),
                Instant.now()
        ));

        return saved;
    }
}
~~~

The key point is that the event is published inside the use case's transaction. `@TransactionalEventListener` receives the event and waits for the corresponding phase. If `orders.save` or a subsequent operation rolls back the transaction, the AFTER_COMMIT listener is not called.

The code snippet is illustrative; ID types and accessors should match your project's entities.

## 3. Phases of @TransactionalEventListener

The annotation has a `phase` attribute to choose when the listener runs:

| Phase | When does the listener run? | Use case |
| --- | --- | --- |
| `BEFORE_COMMIT` | Before the transaction commits | Validate or add operations in the same transaction before commit |
| `AFTER_COMMIT` | After a successful commit | Send notifications after data has been persisted |
| `AFTER_ROLLBACK` | After the transaction rolls back | Record/release tasks dependent on rollback |
| `AFTER_COMPLETION` | After the transaction finishes, whether commit or rollback | Cleanup or processing independent of commit outcome |

Example declaration:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCreated(OrderCreated event) {
    // ...
}
~~~

`AFTER_COMMIT` is the default phase if unspecified.

### 3.1. BEFORE_COMMIT

The listener runs before the transaction commits:

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void validateOrderBeforeCommit(OrderCreated event) {
    // validate or write extra data in the same transaction
}
~~~

If the listener throws an unchecked exception before commit, the transaction can roll back according to Spring's transaction mechanism. This phase can be used for work that must complete within the current transaction.

Do not use BEFORE_COMMIT to send emails or messages to external systems and expect database rollback to revoke that side effect. Side effects outside the database do not participate in the JDBC transaction.

### 3.2. AFTER_COMMIT

The listener only runs when the transaction commits successfully:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderCreated event) {
    emailService.sendOrderConfirmation(event.orderId());
}
~~~

This is the common choice for actions reacting to committed data. However, the listener runs after the transaction has finished. If the listener fails, the database cannot roll back the already-committed transaction.

### 3.3. AFTER_ROLLBACK

The listener only runs after rollback:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onOrderCreationRolledBack(OrderCreated event) {
    metrics.recordOrderCreationRollback(event.orderId());
}
~~~

Use this phase for post-processing tied to rollback, such as metrics or observability. Do not use it to undo an external side effect if that side effect should never have been emitted before commit.

### 3.4. AFTER_COMPLETION

The listener runs after the transaction finishes, regardless of commit or rollback:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void cleanup(OrderCreated event) {
    // cleanup independent of commit or rollback
}
~~~

This phase fits cleanup or work that only needs to know the transaction finished. If you need to distinguish the outcome, use AFTER_COMMIT or AFTER_ROLLBACK.

## 4. Does the listener run if there is no transaction?

By default, `@TransactionalEventListener` only activates when the event is published inside an active transaction. If there is no transaction, the listener is not called.

Example:

~~~java
public void publishWithoutTransaction() {
    events.publishEvent(new OrderCreated(...));
}
~~~

Without a transaction, the default AFTER_COMMIT listener will not run.

### 4.1. fallbackExecution

You can enable:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void onOrderCreated(OrderCreated event) {
    // runs even when there is no transaction to register synchronization
}
~~~

When there is no transaction, the listener runs under fallback behavior instead of being skipped. With this option enabled, the listener can execute immediately during publication since there is no transaction to wait to commit.

Only enable this if that behavior is valid for the use case. If the listener must guarantee data committed before running, publishing outside a transaction with fallback execution can break that assumption. In many applications, keeping the default false helps detect where events are published outside proper transaction boundaries.

## 5. Do AFTER_COMMIT listeners run synchronously?

By default, the listener is invoked synchronously on the thread handling transaction completion. Once commit completes, Spring invokes the listener before the call stack returns to the caller. This means:

- The listener can add latency to the request.
- Exceptions from the listener can surface on the calling thread, even though the transaction already committed.
- A slow listener holds the request thread longer.
- The listener has no built-in durable retry.

Example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendEmail(OrderCreated event) {
    emailService.send(event.orderId()); // may take several seconds
}
~~~

Even if the email service fails, the order may already be committed. The caller can receive an error while the order data persists. This is why response handling and retries need careful design.

## 6. Combining @Async with @TransactionalEventListener

If a listener performs slow work, it can run asynchronously:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

~~~java
@Async
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void sendConfirmation(OrderCreated event) {
    emailService.sendOrderConfirmation(event.orderId());
}
~~~

When the event is processed at AFTER_COMMIT, the listener is handed off to an executor under the async mechanism. The request thread does not have to wait for the work to finish, depending on executor configuration and how Spring proxies the method.

### 6.1. Async does not mean durable

An executor is typically an in-memory thread pool inside the process. If the application stops after commit but before the task executes, the event can be lost. If the executor rejects the task because the queue is full or the process crashes, the listener may never run.

Therefore:

- `@Async` decouples latency and thread execution.
- `@TransactionalEventListener` chooses the transaction phase.
- Neither provides a durable queue, durable retries, or delivery guarantees by itself.

If work must eventually execute even across process restarts, persist the work/event in a database or broker with suitable durability—typically a transactional outbox.

### 6.2. Exceptions in async listeners

Exceptions in async tasks cannot reach back into the committed transaction and usually are not thrown back to the request thread like synchronous exceptions. Configure proper logging, metrics, error handlers, and retries. Merely logging errors can silently drop failures without recovery.

### 6.3. Propagating data and security context

Do not assume every thread-local context propagates to an async executor. If a listener needs tenant, correlation ID, tracing, or security context, pass required data in the event or configure an appropriate task decorator/context propagation. Never put sensitive credentials into event payloads.

## 7. Writing to the database in AFTER_COMMIT: a new transaction is required

A common pitfall: in AFTER_COMMIT, the original transaction has committed, yet JDBC resources may still be bound for completion callbacks. If a listener calls a repository to write additional data without opening a new transaction, the write may reuse completed resources and fail to commit as expected.

If a listener needs to write to the database after commit, open a new transaction:

~~~java
@Component
public class OrderReadModelListener {

    private final OrderReadModelService readModel;

    public OrderReadModelListener(OrderReadModelService readModel) {
        this.readModel = readModel;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void updateReadModel(OrderCreated event) {
        readModel.apply(event);
    }
}
~~~

Service writing the read model:

~~~java
@Service
public class OrderReadModelService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void apply(OrderCreated event) {
        // INSERT/UPDATE read model in a new transaction
    }
}
~~~

`Propagation.REQUIRES_NEW` instructs Spring to create an independent transaction for this operation instead of joining the already-committed original transaction. The method must be invoked through a Spring proxy; placing it in a separate service avoids self-invocation.

Notes:

- The new transaction cannot roll back the already-committed order creation transaction.
- If the read model update fails, the order still exists.
- The listener may need retries or a recovery mechanism if the read model must eventually be updated.
- If the work has high reliability requirements, an outbox is safer than an in-memory callback.

You do not need `REQUIRES_NEW` merely to read committed data; this note primarily applies when a listener must perform follow-up writes and needs independent commits.

## 8. Reliability limits of AFTER_COMMIT

`@TransactionalEventListener` solves **execution timing relative to a transaction**, not durable storage of events.

There is an unavoidable window with callbacks alone:

~~~text
Database COMMIT succeeds
        |
        |  <-- process can crash here
        v
Spring invokes AFTER_COMMIT listener
        |
        v
Listener processes side effect
~~~

If the process crashes after commit yet before the listener is called, business data exists while the event was never handled. There is no durable record telling Spring to run the listener after restart.

Common failure modes:

| Failure | Consequence |
| --- | --- |
| Process dies right after commit | Listener may never have run |
| Listener throws an exception | Business transaction still committed |
| Async executor rejects task | Work may not execute |
| Process dies mid-flight during async task | Work may be incomplete |
| Broker call succeeds yet process dies before recording outcome | Retry may publish duplicate events |
| Email sent successfully yet response from email provider is lost | Unclear if email was sent; retry may send again |

If the business accepts best-effort notifications, AFTER_COMMIT may suffice. If losing an event is unacceptable, a durable mechanism is required.

## 9. Transactional outbox: persisting events alongside business changes

A transactional outbox closes the gap between database commit and event publication:

1. Write the aggregate.
2. Write an outbox row describing the event.
3. Commit both in the same database transaction.
4. A separate publisher reads the outbox and sends events to the broker.
5. The publisher marks events sent or stores retry state.

Diagram:

~~~text
Application Service (@Transactional)
        |
        +-- save PurchaseOrder
        |
        +-- insert outbox_event
        |
        v
      COMMIT
        |
        v
Outbox Publisher / Worker
        |
        +-- read pending event
        |
        +-- publish to broker
        |
        +-- mark published
~~~

If the transaction rolls back, both the aggregate and the outbox row roll back. If the process dies after commit, the outbox row remains for the publisher to process after the application restarts.

### 9.1. Outbox table

Example:

~~~sql
CREATE TABLE outbox_event (
    event_id VARCHAR(36) PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    payload TEXT NOT NULL,
    occurred_at TIMESTAMP NOT NULL,
    published_at TIMESTAMP,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP,
    last_error TEXT
);

CREATE INDEX idx_outbox_pending
    ON outbox_event(published_at, next_attempt_at);
~~~

Production schemas may also need status, lease owner, lease expiry, partition key, or event version. Payloads can be JSON; column types and indexes should match your database.

### 9.2. Writing outbox alongside the aggregate

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OutboxRepository outbox;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            OutboxRepository outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public PurchaseOrder create(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(
                PurchaseOrder.create(command.orderNumber(), command.lines())
        );

        OrderCreated event = new OrderCreated(
                UUID.randomUUID(),
                saved.getId(),
                saved.getOrderNumber(),
                Instant.now()
        );

        outbox.insert(event);
        return saved;
    }
}
~~~

`orders.save` and `outbox.insert` must share the same datasource/transaction manager so they commit or roll back together. If the outbox insert fails, the transaction rolls back the order as well.

### 9.3. Publisher sending events

A scheduled worker or background process can poll unpublished events:

~~~text
SELECT pending outbox rows
  -> publish event
  -> UPDATE published_at
~~~

To run multiple publishers concurrently, use a database-appropriate claim/lease or locking mechanism. Some databases support `FOR UPDATE SKIP LOCKED` so workers grab distinct rows; check syntax and semantics for your dialect.

Avoid keeping a database transaction open while waiting on slow broker calls whenever possible. A common strategy is claiming events in a short transaction, committing the lease, publishing, and updating state in a new transaction. Design lease timeouts to recover when a worker dies after claiming.

### 9.4. Outbox typically provides at-least-once delivery

Consider this scenario:

1. Publisher sends an event successfully to the broker.
2. Broker acknowledges the message.
3. Publisher dies before updating `published_at`.
4. Worker restarts and sends that event again.

Therefore, an outbox typically provides **at-least-once delivery**. Events can be delivered more than once. Consumers must be idempotent, for example storing processed event IDs with a unique constraint in the same transaction as business updates.

Never mark an event published before sending it, because if the process dies after marking yet before sending, the event is lost. Sending first and marking afterward can produce duplicates, making consumer deduplication essential.

## 10. Role of @TransactionalEventListener when using an outbox

The outbox is the durable source of truth. `@TransactionalEventListener` can still be helpful to:

- Signal an in-process publisher that new events are ready for immediate processing.
- Wake the worker instead of waiting for the next polling interval.
- Update best-effort metrics or caches after commit.

Example:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void wakeOutboxPublisher(OrderCreated event) {
    outboxWakeup.signal();
}
~~~

If the process crashes before the wakeup fires, the outbox row still exists and polling/workers will process it later. Thus, wakeup is purely a latency optimization, not the sole event store.

## 11. Idempotency at the consumer

An outbox publisher can deliver duplicates. Consumers need to record processed event markers:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(36) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Inside one consumer transaction:

1. Insert `(consumer_name, event_id)`.
2. If insert succeeds, apply business changes.
3. Commit both the processed marker and the changes.
4. On unique conflict, the event was already processed; do not apply again.

The processed marker and business write must share the same transaction. If the marker is recorded first and the business write fails while committing the marker, the event is permanently skipped. If the business write commits first and recording the marker fails, redelivery can apply the effect twice.

This follows the same idempotency and unique constraint principle: the database must atomically guard both the deduplication marker and business changes in one transaction.

## 12. Designing safe listeners

When writing a listener, answer:

- Should the listener run only after commit?
- Without a transaction, should the event be ignored?
- Can this work fail without affecting the request response?
- Does the listener write to the database; if so, does it need a new transaction?
- Is the work safe to re-run?
- Is losing this work on a process crash acceptable?
- Is an outbox or durable queue required?

Example best-effort listener:

~~~java
@Component
public class OrderNotificationListener {

    private final NotificationService notifications;

    public OrderNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyCustomer(OrderCreated event) {
        notifications.sendOrderCreated(event.orderId());
    }
}
~~~

Example listener writing to the database in a new transaction:

~~~java
@Component
public class OrderProjectionListener {

    private final OrderProjectionWriter writer;

    public OrderProjectionListener(OrderProjectionWriter writer) {
        this.writer = writer;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void project(OrderCreated event) {
        writer.apply(event);
    }
}
~~~

~~~java
@Service
public class OrderProjectionWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void apply(OrderCreated event) {
        // Write projection in a new transaction.
    }
}
~~~

If projections can be rebuilt from source tables, a reconciliation job can fix drift. If event delivery is mandatory, an outbox is more reliable than relying solely on listeners.

## 13. Ordering and multiple listeners

An event may have multiple listeners:

- A listener updating a read model.
- A listener sending notifications.
- A listener recording metrics.

If execution order matters among synchronous listeners, use `@Order`:

~~~java
@Order(1)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void updateProjection(OrderCreated event) {
    // ...
}

@Order(2)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyCustomer(OrderCreated event) {
    // ...
}
~~~

`@Order` orders listeners within the corresponding dispatch mechanism; it does not create a shared transaction for post-commit side effects and does not guarantee completion order if listeners run async. If business order is critical, model dependencies explicitly in a single handler or workflow.

With async listeners, multiple events may run concurrently or finish out of order. If per-aggregate ordering is required, use sequence/version numbers in events and partitioning/serialization in publishers/consumers.

## 14. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Using `@EventListener` for work that must only run after commit | Listener may run before the transaction rolls back | Use `@TransactionalEventListener` with `AFTER_COMMIT` |
| Publishing event outside a transaction while expecting listener to wait for commit | No transaction exists to register synchronization | Publish inside the use case transaction or define explicit fallback |
| Enabling `fallbackExecution` without reviewing semantics | Listener may run immediately when no transaction exists | Only enable if running outside a transaction is valid |
| Thinking `AFTER_COMMIT` can roll back business writes | Transaction already committed before listener | Design separate retries/compensation |
| Listener writes DB after commit without opening a new transaction | Writes may not commit as expected | Use `REQUIRES_NEW` via a Spring proxy |
| Thinking `@Async` makes events durable | Process crash can lose in-memory tasks | Use an outbox or durable broker |
| Async listener fails and only logs | No retries or recovery | Add error handlers, retries, metrics, and outbox |
| Sending messages before commit | May emit events for rolled-back changes | Emit after commit or write outbox inside transaction |
| Thinking `AFTER_COMMIT` cannot lose events | Crash window exists right after commit | Transactional outbox |
| Publisher marks sent before sending | Crash can lose events | Send first, then mark; accept duplicates and deduplicate at consumer |
| Consumer does not deduplicate | Redelivered events apply effects multiple times | Unique processed-event key inside transaction |
| Putting mutable entities into events | Listeners see mutating payloads or depend on object lifecycle | Use immutable events with needed ID/snapshot |
| Relying on `@Order` to guarantee async completion order | Listeners can finish out of order | Design workflows/partitioning per aggregate |

## 15. Testing transactional event listeners

Tests should cover commit, rollback, and no-transaction scenarios.

### 15.1. Listener runs after commit

An integration test:

1. Call a `@Transactional` service.
2. Service saves the aggregate and publishes the event.
3. Verify the listener is invoked after commit.
4. Inside the listener or a test probe, re-read the aggregate to verify data has committed.

Use a test listener or spy depending on test structure. Avoid testing only that `publishEvent` was called, as that does not verify phase listener behavior.

### 15.2. Listener does not run on rollback

Create a test service method:

~~~java
@Transactional
public void createThenFail() {
    repository.save(order);
    events.publishEvent(new OrderCreated(...));
    throw new IllegalStateException("rollback");
}
~~~

Call the method and verify:

- Transaction rolls back.
- Aggregate does not exist after the test.
- AFTER_COMMIT listener was not invoked.
- AFTER_ROLLBACK listener is invoked only if a handler exists for that phase.

### 15.3. Testing that AFTER_COMMIT cannot roll back the business transaction

Have the listener throw an exception after commit. Verify:

- Caller may observe the exception depending on dispatch mechanism.
- Aggregate still exists because the transaction already committed.
- Do not assume a listener failure undoes persisted data.

This test clarifies the boundary between business transactions and post-processing.

### 15.4. Testing REQUIRES_NEW

Have a listener call a writer with `REQUIRES_NEW`; verify projection data commits independently. Then inject a failure in another step of the listener and verify the new transaction rolls back within its own boundary.

### 15.5. Testing outbox and duplicate delivery

Verify:

- Aggregate and outbox row commit together.
- When the business transaction rolls back, no outbox row exists.
- A publisher that sends an event and crashes before marking published can resend it.
- A consumer receiving the same event ID twice applies the business effect only once.
- Workers resume processing pending events after restart.

Concurrency and dialect tests should run against a production-like database or suitable Testcontainers.

## 16. Process for choosing an event handling mechanism

When a use case needs to emit an event after saving an aggregate:

1. **Define the event:** describe the fact that occurred and the data listeners need.
2. **Publish inside the transaction:** emit the application event from the use case writing the aggregate.
3. **Choose the phase:** AFTER_COMMIT for reacting after data commits; BEFORE_COMMIT/AFTER_ROLLBACK/AFTER_COMPLETION only when semantics match.
4. **Decide sync vs. async:** sync is simple yet adds latency; async reduces wait time yet is not durable.
5. **If the listener writes to DB:** open a new transaction with `REQUIRES_NEW` when an independent commit is required.
6. **Assess the failure window:** is losing the work if the process crashes after commit acceptable?
7. **Use an outbox if reliability is required:** write the event alongside the aggregate in one transaction.
8. **Design retries and deduplication:** stable event IDs, idempotent consumers.
9. **Monitor operations:** logs, metrics, retry counts, dead-letter queues, or failure states.
10. **Integration test:** commit, rollback, listener failure, restart/retry, and duplicate delivery.

## Key takeaways

`@TransactionalEventListener` ties event handling to the transaction lifecycle. By default, `AFTER_COMMIT` runs only when the transaction commits successfully, preventing listeners from reacting to rolled-back changes. Phases `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` serve distinct needs; `fallbackExecution` governs whether the listener runs when no transaction exists.

After commit, the business transaction cannot be rolled back by a listener. If a listener needs to write to the database, use a new transaction such as `REQUIRES_NEW`. `@Async` offloads work from the request thread yet relies on an in-memory executor, so it does not guarantee delivery across process crashes. When losing events is unacceptable, write an outbox row alongside the aggregate in the transaction and use a publisher/consumer with retries and event-ID deduplication. That way, events are persisted durably with business changes, while `@TransactionalEventListener` can act as a fast post-commit trigger.
