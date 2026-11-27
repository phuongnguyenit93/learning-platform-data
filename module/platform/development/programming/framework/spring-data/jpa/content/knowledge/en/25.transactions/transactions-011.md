# Transactions Across Threads, `@Async`, and `EntityManager` Scope

## 1. Objectives and context

In a Spring Data JPA application, a transaction is usually managed within the executing thread. When using `@Async`, Spring offloads work to another thread belonging to a `TaskExecutor`. The new thread has its own execution context, so it does not automatically share the calling thread's transaction or persistence context.

After this lesson, you should be able to explain:

- Where Spring starts, commits, and rolls back transactions.
- Why JPA's transaction context and persistence context are thread-bound in the imperative model.
- How the `EntityManager` injected by Spring into a bean differs from an actual `EntityManager` instance.
- Why `@Async` does not inherit the calling method's transaction.
- How to structure services so each asynchronous task has its own JPA transaction.
- How to handle uncommitted data, detached entities, lazy loading, and common errors during concurrent execution.

The examples use Spring Framework/Spring Data JPA with the Jakarta Persistence model. For Spring Boot 2 or Spring Data JPA 2 projects, replace `jakarta.persistence.*` imports with the corresponding `javax.persistence.*` imports.

## 2. Spring manages transactions per thread

`@Transactional` declares a transaction boundary. In standard Spring AOP configurations, calls going through a bean's proxy are handled by the transaction interceptor:

1. Before invoking the method body, the interceptor looks up or creates a transaction per the configured transaction manager and propagation.
2. With JPA, `JpaTransactionManager` manages the transaction and binds an appropriate `EntityManager` to the current thread.
3. The method executes inside that transaction. Repository and JPA operations join the active transaction if they use the same transaction manager and persistence unit.
4. When the method finishes, Spring commits on success or rolls back according to rollback rules.

By default, `@Transactional` uses `REQUIRED` propagation: join an existing transaction on the current thread, or create a new transaction if none exists. By default, Spring rolls back on `RuntimeException` and `Error`; checked exceptions do not automatically trigger rollback unless `rollbackFor` is configured.

In the imperative model, Spring stores transaction state and synchronization resources on the thread, typically via `TransactionSynchronizationManager`'s thread-bound mechanism. Therefore, two calls on two different threads do not naturally see the same transaction context.

Illustrative example:

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void markPaid(long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();
        order.markPaid();
    }
}
```

This illustrative snippet requires a Spring context, repository, and `Order` entity. When `markPaid` is called through the Spring bean proxy, the entity is loaded in the transaction's persistence context. While the entity is managed, state changes are detected by JPA dirty checking and synchronized at commit; calling `save` again is not strictly necessary.

### Proxy boundaries also matter

In proxy-based AOP, internal calls from one method to another within the same object, such as `this.otherMethod()`, do not go through the proxy. Consequently, `@Transactional` or `@Async` on `otherMethod` may not be applied as expected. Call through another Spring bean or restructure service boundaries so calls go through the proxy.

## 3. Scope and lifecycle of EntityManager

JPA distinguishes two objects:

- `EntityManagerFactory`: factory creating `EntityManager` instances, designed to be shared and thread-safe.
- `EntityManager`: represents a specific persistence context; not safe for concurrent access by multiple threads.

In standard Spring configurations, a field injected with `@PersistenceContext` is a shared EntityManager proxy. This proxy looks up the `EntityManager` bound to the current transaction/thread. Therefore, a singleton service can hold this proxy field without meaning multiple threads share a single actual `EntityManager`.

With a transaction-scoped persistence context, `JpaTransactionManager` typically creates or obtains an `EntityManager`, binds it to the thread when the transaction starts, and synchronizes and releases resources when the transaction ends. Spring Data JPA repositories participate in this mechanism as well.

Distinguish between:

- **Managed entity:** belongs to the current persistence context; changes are tracked by dirty checking.
- **Detached entity:** no longer managed by the persistence context that loaded it. Reading basic properties may still work, while lazy associations may fail to load.
- **EntityManager proxy:** intermediary object provided by Spring; routes operations to the appropriate persistence context.
- **Actual EntityManager:** object interacting with the persistence context; must never be shared across multiple threads.

Do not store an actual `EntityManager`, Hibernate `Session`, or managed entity in static variables or pass them to multiple concurrent tasks. Pass primary keys or immutable DTOs, then reload entities inside the receiving task's transaction.

### Open EntityManager in View does not propagate transactions across threads

Open EntityManager in View (OSIV) can keep an EntityManager bound to the web request thread throughout the request lifecycle to support certain lazy loading accesses after the service transaction ends. This mechanism does not make EntityManager thread-safe and does not propagate the transaction context to an `@Async` executor.

An asynchronous task running on its own thread must have its own persistence context and transaction boundary. Do not rely on request-scoped OSIV to access lazy associations from background tasks.

## 4. What happens when calling @Async?

`@Async` instructs Spring to submit the call to an executor. The method body executes on a worker thread, which may be a different thread from the controller or service that called it.

Suppose thread A is inside a `@Transactional` method and calls an `@Async` method:

- Thread A's transaction stays on thread A.
- The executor dispatches the task to thread B.
- Thread B does not receive thread A's transaction context, EntityManager, or persistence context.
- If code running on thread B calls a `@Transactional` method through a Spring proxy, Spring can start a new transaction for thread B.
- Thread B's transaction commits or rolls back independently of thread A's transaction.

Thus, `@Async` does not mean "continue running in the same transaction in the background." It means "execute the work on an executor"; that task's transaction must be designed separately.

### Propagation when running on a new thread

| Propagation | Behavior on the task's execution thread |
|---|---|
| `REQUIRED` | Joins a transaction if that thread already has one; otherwise creates a new transaction. |
| `REQUIRES_NEW` | Creates a new transaction; if that thread has a current transaction, suspends it. |
| `MANDATORY` | Throws an error if that thread has no current transaction. |
| `SUPPORTS` | Joins if a transaction exists; otherwise runs without a transaction. |
| `NOT_SUPPORTED` | Suspends any current transaction on that thread and runs without a transaction. |

If thread A has a transaction while thread B does not, `REQUIRED` on thread B creates a new transaction. `REQUIRES_NEW` also creates a new transaction on thread B; it cannot "suspend" thread A's transaction because that transaction does not belong to thread B.

### Uncommitted data scenario

A common mistake is dispatching an async task before the calling thread's transaction commits:

```java
@Transactional
public void createOrder() {
    Order order = orderRepository.save(new Order());
    orderAsyncFacade.process(order.getId());
    // The current transaction has not committed yet at this point.
}
```

The task on another thread may start before the order-creation transaction commits. Queries from the background task may not see the record yet; if the calling thread's transaction rolls back, the background task may still have executed and produced independent side effects.

If the task must run only after the data-creating transaction commits, publish an event inside the transaction and handle it in the `AFTER_COMMIT` phase:

```java
public record OrderCreatedEvent(long orderId) {}

@Service
public class OrderCommandService {

    private final OrderRepository orderRepository;
    private final ApplicationEventPublisher publisher;

    public OrderCommandService(
            OrderRepository orderRepository,
            ApplicationEventPublisher publisher) {
        this.orderRepository = orderRepository;
        this.publisher = publisher;
    }

    @Transactional
    public void createOrder() {
        Order order = orderRepository.save(new Order());
        publisher.publishEvent(new OrderCreatedEvent(order.getId()));
    }
}

@Component
public class OrderCreatedListener {

    private final OrderAsyncFacade asyncFacade;

    public OrderCreatedListener(OrderAsyncFacade asyncFacade) {
        this.asyncFacade = asyncFacade;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        asyncFacade.process(event.orderId());
    }
}
```

The snippets above are integration examples in a Spring application; corresponding entities, repositories, and event configuration are required. By default, the listener is bound to a transaction; if the event is published outside a transaction, this listener will not run unless `fallbackExecution` is explicitly enabled.

`AFTER_COMMIT` ensures the listener is invoked only after the transaction commits successfully, though this is still in-process application handling. If durable event delivery is required when the application stops unexpectedly, consider Transactional Outbox and a process/consumer reading the outbox. Do not treat in-memory event listeners as durable queues.

## 5. Recommended service structure

A clear structure separates the asynchronous coordinator bean from the bean performing business work inside a transaction:

1. The coordinator bean receives the request and is annotated with `@Async`.
2. The business worker bean receives an ID or immutable data, loads entities on the worker thread, and is annotated with `@Transactional`.
3. Each background task has its own transaction boundary; entities are used inside that task's own persistence context.

### Configuring the executor

```java
@Configuration
@EnableAsync
public class AsyncConfiguration {

    @Bean("jpaTaskExecutor")
    public Executor jpaTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("jpa-async-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(30);
        return executor;
    }
}
```

The numbers are merely starter examples, not optimal values for every system. Size the pool and queue based on processing duration, actual load, and database connection limits. If concurrent workers exceed connection capacity, tasks may wait or overload the system. Monitor queue depth, wait times, rejected task errors, and processing durations.

### Async bean and transactional bean

```java
@Service
public class OrderAsyncFacade {

    private final OrderTransactionalWorker worker;

    public OrderAsyncFacade(OrderTransactionalWorker worker) {
        this.worker = worker;
    }

    @Async("jpaTaskExecutor")
    public CompletableFuture<Void> process(long orderId) {
        worker.process(orderId);
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class OrderTransactionalWorker {

    private final OrderRepository orderRepository;

    public OrderTransactionalWorker(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void process(long orderId) {
        Order order = orderRepository.findById(orderId)
            .orElseThrow();
        order.markProcessing();
    }
}
```

These illustrative classes must be registered in the Spring context and require `Order`, `OrderRepository`, and corresponding business methods. When `process` is called via `OrderAsyncFacade`'s proxy, Spring dispatches the call to `jpaTaskExecutor`. On the worker thread, calling the `OrderTransactionalWorker` bean goes through the transaction proxy and opens a transaction for the JPA work.

`CompletableFuture` allows callers to observe completion timing and errors:

```java
CompletableFuture<Void> task = orderAsyncFacade.process(orderId);

// Wait only when the calling thread truly needs completion results.
task.join();
```

Do not call `join()` or `get()` right after every async call if the goal is freeing the calling thread; doing so turns the operation into synchronous waiting. For methods returning `void`, errors are not returned to the caller; configure an `AsyncUncaughtExceptionHandler` along with logging/monitoring. With `CompletableFuture`, handle exceptional completion appropriately.

Avoid putting both `@Async` and `@Transactional` on the same method while assuming the caller's transaction is preserved. A clear boundary between the async bean and transactional bean clarifies which thread opens the transaction, simplifies testing, and avoids proxy/advisor confusion.

## 6. Safety rules when using JPA in background tasks

### Pass IDs or DTOs, load entities inside the worker

Do not pass managed entities from the calling thread's transaction to a worker. After leaving the original persistence context, the entity can become detached; lazy associations may no longer load. Even if fully loaded, two threads updating the same object still risk race conditions.

Pass the ID instead:

```java
asyncFacade.process(order.getId());
```

Then the worker queries it fresh:

```java
@Transactional
public void process(long orderId) {
    Order order = orderRepository.findById(orderId)
        .orElseThrow();
    order.recalculate();
}
```

If required data is already computed and entities are not needed, pass an immutable DTO. DTOs make the exact data snapshot received by the task explicit.

### Control concurrent updates

Two workers may read and update the same record simultaneously. If business logic needs to detect overwrites, use optimistic locking with `@Version`:

```java
@Entity
public class Order {

    @Id
    private Long id;

    @Version
    private long version;

    // Other fields and business methods.
}
```

When a transaction updates a stale version, the JPA provider can detect the conflict and throw an optimistic locking exception. The application must decide whether to retry, report a conflict, or drop the task. Retrying is only safe when the operation is idempotent or has duplicate-processing protection. Database unique constraints remain essential to protect data invariants.

### Keep transactions short

Do not hold transactions and connections while waiting on external APIs, sending emails, or running slow tasks. Separate database reads/writes from external I/O when business rules permit. For batch processing, divide data into appropriately sized batches and explicitly decide whether each batch is a separate transaction or the entire job is one transaction.

### Do not share transaction context via TaskDecorator

An executor can use `TaskDecorator` to propagate certain contexts such as MDC or observability metadata. This does not make a JPA transaction a safe shared resource. Do not copy `EntityManager`, Hibernate `Session`, or transaction synchronizations onto worker threads. Each worker must open its own transaction via the Spring transaction manager.

## 7. Common errors and fixes

| Symptom | Common cause | Resolution |
|---|---|---|
| Worker does not see newly created record | Async runs before caller's transaction commits | Publish an event and handle at `AFTER_COMMIT`, or use outbox when high reliability is required |
| `LazyInitializationException` | Worker uses a detached entity or lacks a suitable persistence context | Pass ID/DTO and reload the entity in the worker's transaction; fetch needed data |
| `@Transactional` has no effect | Internal call via `this`, calling a `new`-instantiated object, or bean bypassing proxy | Call through Spring bean proxy and verify transaction management config |
| `@Async` executes synchronously | Self-invoking async method in same bean or async processing not enabled | Enable `@EnableAsync` and call through proxy from another bean |
| Error when using `MANDATORY` in worker | Worker thread has no transaction propagated from caller | Use appropriate propagation, typically `REQUIRED`, so worker opens its own transaction |
| Data overwrites between workers | Multiple transactions updating the same entity | Use appropriate optimistic/pessimistic locking, database constraints, and controlled retries |
| Background task fails without caller knowing | Async method returns `void` or Future is unhandled | Return `CompletableFuture`, handle errors, and add logging/monitoring |
| Connection pool exhausted | Too many workers or transactions held too long | Bound executor, shorten transactions, and size according to connection pool |

## 8. Testing async behavior and transactions

Tests should synchronize on task completion rather than using `Thread.sleep` to guess when a worker finishes. With `CompletableFuture`, you can await with a timeout and then re-read data in a separate verification transaction.

A common pitfall is Spring tests annotated with `@Transactional` that roll back at the end. The test transaction running on the test thread does not propagate to the worker. If the worker needs to read data created by the test, commit the data before triggering the task or design the test without relying on uncommitted transactions. Workers can commit independently even if the test transaction later rolls back; clean up test data explicitly.

Test at least these cases:

- Worker reads committed data and saves changes successfully.
- Worker does not run when the event-publishing transaction rolls back if using an `AFTER_COMMIT` listener.
- Errors inside the worker cause the worker's transaction to roll back.
- Task accepts an ID/DTO and loads its own data; does not depend on the calling thread's managed entities.
- Concurrent tasks updating the same record are handled according to the application's locking and retry policy.

## 9. Design checklist

Before shipping asynchronous JPA processing to production, verify:

- [ ] Async processing is enabled and methods are called through Spring proxies.
- [ ] Executor has appropriate thread limits, queue bounds, and rejection policy.
- [ ] Worker's transaction boundary is clearly declared in a business bean.
- [ ] Worker passes/receives IDs or DTOs; never shares EntityManager, Session, or managed entities across threads.
- [ ] Tasks needing newly created data are dispatched only after commit, or use an outbox for durable delivery.
- [ ] Update conflicts, duplicate handling, retries, and async errors have explicit policies.
- [ ] Tests await Future/event completion and verify data after commit.

## 10. Key takeaways

In imperative Spring Data JPA, transactions and persistence contexts are bound to the executing thread. `@Async` dispatches work to a worker thread and therefore does not carry over the caller's transaction. Have the worker load entities in its own persistence context and invoke a `@Transactional` service through the Spring proxy. If a task depends on newly created data, launch it only after commit; if guaranteed delivery across process crashes is required, use a durable mechanism such as Transactional Outbox.