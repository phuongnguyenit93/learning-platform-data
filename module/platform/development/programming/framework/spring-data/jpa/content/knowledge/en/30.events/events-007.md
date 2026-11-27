# Event Behavior on Rollback, Without a Transaction, and with @Async

In Spring Data JPA, domain events are commonly emitted when an aggregate root changes state. Spring can deliver an event to listeners immediately upon publication or bind listeners to a phase of the transaction. The outcome depends on when the event is published, the state of the transaction, and whether the listener runs synchronously or asynchronously.

Three distinct actions must be separated:

- **Publish event:** passing the event into Spring's ApplicationEventPublisher.
- **Handle event:** the listener executing event-handling logic.
- **Commit transaction:** business data being confirmed in the database.

These three actions do not necessarily happen at the same time. An event can already be published and a synchronous listener can have run, yet the transaction may still roll back afterward. Conversely, a listener bound to AFTER_COMMIT runs only after the transaction commits successfully.

## 1. Publishing events and regular listeners

Spring lets you publish events using `ApplicationEventPublisher`:

```java
public record OrderPlacedEvent(Long orderId) {
}
```

Service publishing an event after saving an order:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public Long placeOrder(Order order) {
        Order saved = orders.save(order);

        events.publishEvent(
                new OrderPlacedEvent(saved.getId())
        );

        return saved.getId();
    }
}
```

By default, Spring processes `@EventListener` synchronously right when `publishEvent()` is called:

```java
@Component
public class OrderEventListener {

    @EventListener
    public void onOrderPlaced(OrderPlacedEvent event) {
        System.out.println(
                "Received order " + event.orderId()
        );
    }
}
```

If an event is published inside a transaction, a regular listener still runs before that transaction commits. If later processing throws an exception and the transaction rolls back, the listener has already executed. Spring does not automatically undo emails, HTTP requests, messages sent to other systems, or external side effects the listener already performed.

If a synchronous listener writes data via the same transaction manager and participates in the current transaction, those writes can roll back with the transaction. However, database rollback cannot undo an external action such as sending an email or calling an API.

Therefore, `@EventListener` fits when you want an immediate reaction to an event and accept running at publish time. When business logic must execute only after data has committed, use `@TransactionalEventListener`.

## 2. @TransactionalEventListener and transaction phases

`@TransactionalEventListener` binds event processing to a transaction phase:

```java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderTransactionListener {

    @TransactionalEventListener
    public void afterCommit(OrderPlacedEvent event) {
        System.out.println(
                "Order committed: " + event.orderId()
        );
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_ROLLBACK
    )
    public void afterRollback(OrderPlacedEvent event) {
        System.out.println(
                "Order rolled back: " + event.orderId()
        );
    }

    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMPLETION
    )
    public void afterCompletion(OrderPlacedEvent event) {
        System.out.println(
                "Transaction completed: " + event.orderId()
        );
    }
}
```

If no phase is specified, Spring uses `TransactionPhase.AFTER_COMMIT`. Meaning of each phase:

| Phase | When listener runs | On transaction rollback |
|---|---|---|
| `BEFORE_COMMIT` | Right before the transaction commits | May already have run even if transaction later rolls back |
| `AFTER_COMMIT` | After successful commit | Does not run |
| `AFTER_ROLLBACK` | After rollback | Runs |
| `AFTER_COMPLETION` | After the transaction finishes | Runs on both commit and rollback |

### When the transaction commits

If the service publishes an event inside a transaction and the transaction commits successfully:

1. The event is published.
2. Spring registers transaction-bound listeners with the current transaction.
3. The transaction commits.
4. `AFTER_COMMIT` listeners are invoked.
5. `AFTER_ROLLBACK` listeners are not invoked.
6. `AFTER_COMPLETION` listeners are also invoked because the transaction has completed.

### When the transaction rolls back

Example:

```java
@Transactional
public void placeOrder(Order order) {
    Order saved = orders.save(order);
    events.publishEvent(
            new OrderPlacedEvent(saved.getId())
    );

    throw new IllegalStateException("Payment rejected");
}
```

If an exception causes the transaction to roll back:

- Regular `@EventListener` listeners already ran right when the event was published.
- `AFTER_COMMIT` listeners do not run because the transaction did not commit.
- `AFTER_ROLLBACK` listeners run to handle the rollback scenario.
- `AFTER_COMPLETION` listeners run after the rollback completes.
- Data written within the same transaction rolls back according to transaction rules.

`AFTER_ROLLBACK` can be used for business logging, updating metrics, releasing resources, or performing a compensating action. Do not send an "order created successfully" notification from a regular listener before the transaction commits.

`BEFORE_COMMIT` does not guarantee a commit will succeed. Listeners in this phase run before commit, yet another listener, a flush error, or a commit failure can still cause the transaction to roll back.

## 3. When events are published without a transaction

A regular `@EventListener` does not require a transaction. Without a transaction, the listener still runs immediately when the event is published.

With `@TransactionalEventListener`, `fallbackExecution = false` is the default. If an event is published with no active transaction, the listener is not executed because Spring has no transaction phase to register with.

Example:

```java
@Component
public class NoTransactionListener {

    @EventListener
    public void onRegularEvent(OrderPlacedEvent event) {
        // Still runs when there is no transaction.
    }

    @TransactionalEventListener
    public void onTransactionalEvent(OrderPlacedEvent event) {
        // Skipped if the event is published outside a transaction.
    }
}
```

If you want the listener to still run when there is no transaction, you can enable fallback:

```java
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT,
    fallbackExecution = true
)
public void onOrderPlaced(OrderPlacedEvent event) {
    // Runs after commit if there is a transaction.
    // If there is no transaction, runs immediately via fallback.
}
```

Understand the limitation clearly: `fallbackExecution = true` neither creates a new transaction nor simulates a commit. Without a transaction, the listener runs immediately in fallback mode; the application has no AFTER_COMMIT guarantee as it does when publishing inside a real transaction.

If the listener needs to write data, open a dedicated transaction via a `@Transactional` service. If business logic requires confirming that source data committed before handling, ensure the event is published inside a business transaction rather than relying on fallback.

For Spring Data domain events, place repository calls inside a `@Transactional` service method when listeners need to bind to that business transaction. This clarifies publication timing and ensures `@TransactionalEventListener` receives the transaction it needs.

## 4. Spring Data @DomainEvents and transaction timing

Spring Data allows an aggregate root to publish events via `@DomainEvents` and clear the event list after publication via `@AfterDomainEventPublication`.

Example aggregate:

```java
import org.springframework.data.domain.AfterDomainEventPublication;
import org.springframework.data.domain.DomainEvents;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

@Entity
public class Order {

    @Id
    @GeneratedValue
    private Long id;

    @Transient
    private final List<Object> events = new ArrayList<>();

    public void place() {
        // Update business state of the order.
        events.add(new OrderPlacedEvent(id));
    }

    @DomainEvents
    Collection<Object> domainEvents() {
        return List.copyOf(events);
    }

    @AfterDomainEventPublication
    void clearDomainEvents() {
        events.clear();
    }
}
```

Spring Data calls these methods when supported repository operations execute on an aggregate root, such as `save()`, `saveAll()`, `delete()`, and `deleteAll()`. Current Spring Data versions also support certain batch delete methods that accept aggregate roots. `deleteById()` does not take an aggregate instance as an argument, so it cannot rely on this mechanism to read events from the deleted entity.

Basic flow:

1. The aggregate changes state and records events in an internal list.
2. The application calls the repository to save or delete the aggregate.
3. Spring Data retrieves events from the `@DomainEvents` method and publishes them to the Spring ApplicationContext.
4. After events are published, the `@AfterDomainEventPublication` method is invoked to clear the event list.
5. Regular listeners process immediately; transaction-bound listeners wait for the corresponding phase if published inside a transaction.

`@AfterDomainEventPublication` means the events were published into the ApplicationContext. It does not mean the database transaction has committed. If the outer transaction later rolls back, the aggregate's event list may already be cleared while `AFTER_COMMIT` listeners never run. Hence, the in-memory event list is not a durable queue and should not be used as a retry mechanism after rollback.

Use immutable event payloads, usually containing IDs and necessary data, rather than passing managed JPA entities into asynchronous processing. Entities can become detached or change after the event is published.

## 5. Using @Async with event listeners

`@Async` moves method execution into a task submitted to a Spring `TaskExecutor`. The caller can continue without waiting for the listener to finish.

Enable async support:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfig {
}
```

Regular asynchronous listener:

```java
@Component
public class OrderNotificationListener {

    @Async
    @EventListener
    public void sendNotification(OrderPlacedEvent event) {
        // Send an email or call a notification service.
    }
}
```

When combining `@EventListener` with `@Async`, work is submitted to the executor right when the event is published. If published inside a transaction, the async listener can start before the transaction commits. It may read uncommitted data or perform side effects even if the originating transaction later rolls back.

If processing should only start after data has committed, combine `@Async` with `@TransactionalEventListener(phase = AFTER_COMMIT)`:

```java
@Component
public class OrderNotificationListener {

    private final NotificationService notifications;

    public OrderNotificationListener(
            NotificationService notifications) {
        this.notifications = notifications;
    }

    @Async("eventExecutor")
    @TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT
    )
    public void sendNotification(OrderPlacedEvent event) {
        notifications.sendOrderConfirmation(event.orderId());
    }
}
```

In this example, the listener is triggered only after the transaction commits successfully, and then processing is dispatched to the executor named `eventExecutor`. If the transaction rolls back, the listener submits no work to the executor.

Declare a correspondingly named executor bean if the application wants a dedicated executor. If no name is specified, Spring uses the default executor configured for async support.

## 6. Transactions do not propagate to @Async threads

Spring's imperative transactions are usually bound to the current thread via thread-bound context. When `@Async` switches work to another thread, the calling thread's transaction does not automatically propagate to the executing thread.

Example:

```java
@Transactional
public void createOrder() {
    orders.save(new Order());
    events.publishEvent(new OrderPlacedEvent(123L));
}
```

If the listener runs with `@Async`, the listener thread does not participate in `createOrder()`'s transaction. Having the listener run after commit via `AFTER_COMMIT` only ensures the source data committed before the listener was triggered; it does not transfer the old transaction to the new thread.

If the listener needs to write to the database, invoke a `@Transactional` service from the async thread:

```java
@Service
public class NotificationService {

    @Transactional
    public void saveNotification(Long orderId) {
        // Write notification in its own transaction.
    }
}
```

When this method is called from an async thread with no transaction, the default `REQUIRED` propagation starts a new transaction. Do not rely on the event-publishing thread's transaction.

One case must be distinguished: a synchronous `AFTER_COMMIT` listener runs on the original transaction thread. When the callback is invoked, the transaction has already committed, yet transactional resources may still remain temporarily bound. If the listener performs writes and joins the old transaction via `REQUIRED`, those changes might not be committed again. For database writes inside a synchronous AFTER_COMMIT listener, invoke a separate transactional service with `Propagation.REQUIRES_NEW`.

## 7. Exception handling in @Async listeners

With synchronous listeners, an exception from the listener can propagate back to the event publisher and affect the calling flow. With `@Async` listeners, exceptions occur on an executor thread and do not propagate directly back to the caller that published the event.

If an async method returns `void`, exceptions have no return handle for the caller to observe; by default Spring logs them. You can configure an `AsyncUncaughtExceptionHandler` to handle exceptions from void methods.

If you need to observe results and errors, the async method can return `CompletableFuture`:

```java
@Async("eventExecutor")
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT
)
public CompletableFuture<Void> process(OrderPlacedEvent event) {
    notificationService.sendOrderConfirmation(event.orderId());

    return CompletableFuture.completedFuture(null);
}
```

The caller publishing the event does not directly receive this Future because Spring invokes the listener after the transaction phase. To track processing status, use a dedicated monitoring mechanism such as logs with correlation IDs, a job status table, metrics, or a message broker.

Configure the executor sensibly as well: thread count, queue capacity, task rejection policy, shutdown timeout, and overload handling. Avoid an unbounded executor that lets tasks pile up endlessly when listeners are slower than event publication.

`@Async` works through a Spring proxy. Self-invocation within the same bean such as `this.process(...)` bypasses the proxy and may not trigger async advice. Invoke the method from another Spring bean or extract async handling into a separate component.

## 8. Rollback and @Async: common scenarios

| Listener declaration | Transaction commits | Transaction rolls back | No transaction |
|---|---|---|---|
| `@EventListener` | Runs immediately at publish | Already ran before rollback | Runs immediately |
| `@TransactionalEventListener(AFTER_COMMIT)` | Runs after commit | Does not run | Skipped by default |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Does not run | Runs after rollback | Skipped by default |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Runs after completion | Runs after completion | Skipped by default |
| `@TransactionalEventListener(fallbackExecution = true)` | Follows chosen phase | Follows chosen phase | Runs immediately via fallback |
| `@Async @EventListener` | Dispatched to executor at publish | May still have been dispatched before rollback | Dispatched to executor |
| `@Async @TransactionalEventListener(AFTER_COMMIT)` | Dispatched to executor only after commit | Not dispatched to executor | Skipped by default |

The table assumes the event is published while listeners are registered and an imperative transaction is active when a transaction phase is required. If configuring a shared executor on ApplicationEventMulticaster or using reactive transactions, account for the corresponding context mechanics.

## 9. Are post-commit events guaranteed to be processed?

`@TransactionalEventListener(AFTER_COMMIT)` solves the timing issue: the listener runs only once the transaction has committed. However, Spring ApplicationContext events are an in-process memory mechanism. They do not durably persist events to a database or broker automatically.

For example, the transaction commits an order, yet the application stops before the async task processes the event. The order data persists, while sending notifications or syncing to another system may never have occurred. `@Async` does not provide retries or delivery guarantees either.

If business requirements dictate that events cannot be lost after transaction commit, consider a transactional outbox:

1. Within the same transaction creating/updating business data, insert a record into an outbox table.
2. Commit once so both business data and the outbox record exist or roll back together.
3. A worker reads unprocessed outbox records and sends them to a message broker or target service.
4. Mark records processed after successful delivery; retry on transient failures.
5. Receiving listeners must be idempotent because retries can produce duplicate messages.

An outbox durably persists the intent to emit an event alongside the business transaction. It is a better fit when lost notifications due to process crashes are unacceptable. For simpler requirements, `@TransactionalEventListener` combined with `@Async` remains useful, provided you recognize it is not a durable message queue.

## 10. Common mistakes and fixes

**Using @EventListener and sending email before commit.** If the transaction rolls back, the email has still been sent. Use `@TransactionalEventListener(AFTER_COMMIT)` when notifications make sense only after a successful save.

**Using @TransactionalEventListener without a transaction.** The listener is skipped by default. Publish inside a transactional service or enable `fallbackExecution = true` if running immediately without a transaction is genuinely acceptable.

**Assuming @Async inherits the caller's transaction.** Executor threads do not automatically receive the publishing thread's transaction context. Open a dedicated transaction in a service called from the async listener when database writes are needed.

**Assuming an AFTER_COMMIT listener can write into the just-committed transaction.** The transaction has already completed; writes need a new transaction. For synchronous listeners, use `REQUIRES_NEW`; for async listeners, a `@Transactional` service running on the worker thread starts a new transaction if none exists.

**Assuming a dispatched async listener means the task succeeded.** The caller only submits the task to an executor. The listener can fail afterward. Track errors, metrics, retries, and processing status.

**Using in-memory events as a durable queue.** Process crashes can lose post-commit work. Use an outbox or durable broker when delivery guarantees are needed.

**Clearing the event list too early and expecting rollback to restore events.** `@AfterDomainEventPublication` runs after publishing to the ApplicationContext, without waiting for transaction commit. Use an outbox if reliable recovery and re-emission are needed.

**Putting @Async and @Transactional on the same bean and calling internally.** Self-invocation can bypass proxies. Extract handling into a separate bean so async and transaction proxies work properly.

## 11. Listener design workflow by business need

1. Decide whether the event may be processed before commit or must wait for data to commit successfully.
2. If handling depends on transaction outcome, use `@TransactionalEventListener` and choose the phase explicitly.
3. Ensure the event is published inside a business transaction if AFTER_COMMIT or AFTER_ROLLBACK is needed.
4. Enable `fallbackExecution` only when no-transaction behavior is clearly defined.
5. Use `@Async` for slow or independent tasks, and configure a bounded executor.
6. Open a new transaction for database writes in async workers; for synchronous AFTER_COMMIT listeners, use `REQUIRES_NEW` when writes are required.
7. Handle exceptions and monitor async outcomes instead of assuming successful publication equals successful processing.
8. Use a transactional outbox when events must be delivered durably after commit.
9. Test commit, rollback, and no-transaction cases separately; also test async listeners, executor saturation, and processing errors.

## Conclusion

`@EventListener` runs when an event is published, so it can execute before the transaction commits. `@TransactionalEventListener` binds handling to AFTER_COMMIT, AFTER_ROLLBACK, or other phases; by default it does not run without a transaction. `@Async` moves listeners to another thread and does not propagate the publishing thread's transaction. Combine AFTER_COMMIT with async when background work is needed after data commits, open a dedicated transaction for worker writes, and use a transactional outbox if business requirements cannot tolerate lost events.