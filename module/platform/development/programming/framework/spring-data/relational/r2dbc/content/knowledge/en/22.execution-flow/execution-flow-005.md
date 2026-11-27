# Avoiding Manual subscribe Inside Repository and Service Layers

In Spring Data Relational R2DBC, repositories and services should return `Mono` or `Flux` so the caller decides when and in what context the work is executed. Calling `subscribe()` manually inside a repository or service creates a subscription detached from the publisher that the method returns. The caller can no longer wait for that result, does not receive errors through the reactive pipeline, struggles to control cancellation, and can lose the transaction context.

The key principle is to **compose publishers across layers and subscribe only at the execution boundary managed by the framework or a high-level coordinator**. In a WebFlux application, controllers normally return publishers for WebFlux to subscribe to. In tests, `StepVerifier` subscribes. For a standalone process without a framework consuming publishers, the component at the application boundary can own the subscription and its lifecycle. Repositories and services should not silently execute work on their own and return a different publisher.

## 1. Publishers describe work; subscription triggers work

Spring Data R2DBC reactive APIs such as `ReactiveCrudRepository`, `R2dbcEntityTemplate`, and `DatabaseClient` return publishers. For lazy database operations, calling the method typically only builds a description of the work.

Example:

```java
Mono<Customer> customerMono = customerRepository.findById(10L);
```

At the time `customerMono` is assigned, the query has usually not been executed yet. When a subscriber registers and requests data, the publisher begins executing:

```java
customerMono.subscribe();
```

In a WebFlux application, callers usually do not need to write this `subscribe()` line. The controller returns `Mono`/`Flux` to the framework; the framework subscribes and manages writing the response.

### 1.1. Lifecycle when composed properly

```text
HTTP request
    |
    v
Controller returns Mono / Flux
    |
    v
Service composes publisher
    |
    v
Repository returns database publisher
    |
    v
WebFlux subscribes at response boundary
    |
    v
Database query executes
    |
    v
Result / error / cancellation flow through the same pipeline
```

Each layer only describes its own piece of work. Publishers flow up to the caller; the subscriber at the execution boundary controls the entire chain.

## 2. Why does subscribe() inside a service cause design flaws?

Consider the following code:

```java
public Mono<Order> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.just(order);
}
```

There are two separate pieces of work:

1. `orderRepository.save(order).subscribe()` starts its own independent subscription.
2. `Mono.just(order)` is the publisher the caller receives.

The returned publisher does not represent the save operation. It can emit `order` even if the `INSERT` has not completed or has failed.

Specific problems:

- **The caller does not wait for the save operation:** the response can be returned before the database finishes writing.
- **Errors are detached from the caller:** errors from `save` do not propagate through the returned publisher.
- **Cancellation cannot be controlled:** a client cancelling the request does not automatically cancel the detached save subscription.
- **Hard to manage resources:** the separate subscription may keep using a connection after the request has already ended.
- **Hard to test:** tests subscribing only to the returned publisher might not wait for the independent save operation.
- **Risk of duplicate writes:** if the service is called multiple times or the independent publisher is recreated, each subscription can execute another write.

The fact that `subscribe()` returns a `Disposable` does not fix these problems if the service ignores it. Even if you hold onto the `Disposable`, the caller still does not receive results and errors under a single reactive contract.

### 2.1. Correct approach: return the save operation's publisher

```java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
```

The caller receives the actual publisher performing the `INSERT`/`UPDATE`. When the publisher completes, the caller gets the saved entity; when the database emits an error, it propagates to the caller; when the caller cancels the subscription, cancellation propagates through the publisher chain according to the semantics of participating components.

### 2.2. Do not subscribe and return a fake result

Another risky variation:

```java
public Mono<Boolean> register(User user) {
    userRepository.save(user).subscribe();
    return Mono.just(true);
}
```

`true` only confirms that the service called `subscribe()`, not that the database committed. A success result must be emitted only after the save operation completes:

```java
public Mono<Boolean> register(User user) {
    return userRepository.save(user)
        .thenReturn(true);
}
```

If you need to return the saved entity, return `Mono<User>` directly instead of converting it into a boolean.

## 3. Do not subscribe inside a Repository

A repository is a data access abstraction. Its responsibility is to declare or implement data operations and return publishers to the calling layer.

Standard repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
```

You do not need to manually implement `subscribe()` for these methods. Spring Data generates the implementation and manages execution when the publisher is subscribed to.

For custom repositories, return the publisher from `DatabaseClient`:

```java
public class CustomerRepositoryCustomImpl
        implements CustomerRepositoryCustom {

    private final DatabaseClient databaseClient;

    public CustomerRepositoryCustomImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Flux<CustomerSummary> search(String prefix) {
        return databaseClient.sql("""
                SELECT id, name, email
                FROM customer
                WHERE name LIKE :pattern
                ORDER BY id
                """)
            .bind("pattern", prefix + "%")
            .map((row, metadata) -> new CustomerSummary(
                row.get("id", Long.class),
                row.get("name", String.class),
                row.get("email", String.class)
            ))
            .all();
    }
}
```

The `search` method returns `Flux<CustomerSummary>` so the caller controls subscription. If a custom repository calls `.all().subscribe()` and then returns `Flux.empty()`, it breaks the repository contract and prevents upper layers from controlling the query.

### 3.1. A repository should not decide execution timing on its own

Avoid:

```java
@Override
public Mono<Customer> findCustomer(Long id) {
    databaseClient.sql("SELECT id, name FROM customer WHERE id = :id")
        .bind("id", id)
        .map(this::mapCustomer)
        .one()
        .subscribe();

    return Mono.empty();
}
```

Prefer:

```java
@Override
public Mono<Customer> findCustomer(Long id) {
    return databaseClient.sql("SELECT id, name FROM customer WHERE id = :id")
        .bind("id", id)
        .map(this::mapCustomer)
        .one();
}
```

The repository does not know whether the HTTP request has timed out, whether the caller wants one element or wants to combine results with another source, or how errors should map to HTTP 404/409. Those decisions belong to the caller or service layer.

## 4. Use flatMap to chain dependent asynchronous operations

A service often needs to run multiple operations in sequence. If a later operation needs the result of an earlier one, use `flatMap`.

Example saving an order and then saving order lines with the newly generated order ID:

```java
public Mono<Order> createOrder(
        Order order,
        List<OrderLine> requestedLines) {

    return orderRepository.save(order)
        .flatMap(savedOrder -> {
            List<OrderLine> lines = requestedLines.stream()
                .map(line -> line.withOrderId(savedOrder.getId()))
                .toList();

            return orderLineRepository.saveAll(lines)
                .thenReturn(savedOrder);
        });
}
```

`flatMap` receives the entity after the `INSERT` completes, creates the publisher that saves the lines, waits for it to complete, and then emits `savedOrder`. No manual subscription is created.

### 4.1. Use then when you only need to wait for the previous operation to complete

If you do not need the value from the first publisher, use `then`:

```java
public Mono<Void> deleteCustomerAndAudit(Long customerId) {
    return customerRepository.deleteById(customerId)
        .then(auditRepository.save(
            AuditEntry.customerDeleted(customerId)
        ))
        .then();
}
```

`then(nextPublisher)` waits for the previous publisher to complete successfully before subscribing to the next publisher. If the first operation emits an error, the next publisher does not run and the error propagates outward.

If you need to emit a fixed value after the previous operation completes:

```java
return customerRepository.save(customer)
    .thenReturn("SAVED");
```

`thenReturn` does not create a detached subscription; it is an operator within the same pipeline.

### 4.2. Use delayUntil when needing an async side effect while keeping the original value

`delayUntil` is useful when you want to wait on a publisher dependent on the emitted value and still return the original value afterward:

```java
public Mono<Order> saveAndAudit(Order order) {
    return orderRepository.save(order)
        .delayUntil(saved -> auditRepository.save(
            AuditEntry.orderCreated(saved.getId())
        ));
}
```

The audit publisher is composed and must complete before `saved` is emitted downstream. If the audit errors, the error propagates outward. This is an alternative to `doOnNext(saved -> auditRepository.save(...).subscribe())`.

## 5. Do not call a repository inside doOnNext and subscribe

`doOnNext` is for observation or synchronous side effects tied to signals, such as logging or incrementing metrics:

```java
return orderRepository.save(order)
    .doOnNext(saved -> log.info("Created order {}", saved.getId()));
```

Do not use `doOnNext` to trigger another reactive operation:

```java
// Avoid: audit publisher is detached from the main pipeline.
return orderRepository.save(order)
    .doOnNext(saved -> auditRepository.save(
        AuditEntry.orderCreated(saved.getId())
    ).subscribe());
```

`doOnNext` takes a callback returning `void`. Reactor cannot wait for a publisher created inside that callback. Use `flatMap` or `delayUntil`:

```java
return orderRepository.save(order)
    .flatMap(saved -> auditRepository.save(
        AuditEntry.orderCreated(saved.getId())
    ).thenReturn(saved));
```

In this example, the `Order` result is emitted only after saving the audit completes. If the audit is a mandatory side effect in the same transaction, ensure both operations participate in the same transaction. If the audit goes to an external system, consider an outbox or a separate workflow.

## 6. Combining multiple Publishers without manual subscribe

If there are two independent operations and you need both results, you can use `Mono.zip`:

```java
public Mono<CustomerDashboard> loadDashboard(Long customerId) {
    Mono<Customer> customer = customerRepository.findById(customerId);
    Mono<AccountBalance> balance = accountService.findBalance(customerId);

    return Mono.zip(customer, balance)
        .map(tuple -> new CustomerDashboard(
            tuple.getT1(),
            tuple.getT2()
        ));
}
```

`zip` manages subscribing to both sources within the same composition. The caller only needs to subscribe to the final publisher.

If you only need to wait for multiple operations to finish without needing emitted values:

```java
public Mono<Void> refreshCustomerData(Long customerId) {
    Mono<Void> updateSearchIndex = searchIndexService.refresh(customerId);
    Mono<Void> clearCache = cacheService.evictCustomer(customerId);

    return Mono.when(updateSearchIndex, clearCache);
}
```

`Mono.when` combines completion across publishers. If one branch errors, the error propagates downstream and the other branches may be cancelled according to the operator's semantics.

### 6.1. When operations must run sequentially

Do not use `Mono.when` or `zip` merely to avoid subscribing. If the second operation depends on the result of the first, use `flatMap`/`then`.

```java
return customerRepository.save(customer)
    .flatMap(saved -> addressRepository.save(
        address.withCustomerId(saved.getId())
    ).thenReturn(saved));
```

### 6.2. Be careful running in parallel on the same transaction-bound connection

`zip` or `when` can subscribe to multiple independent database operations. If the operations participate in the same reactive transaction and share a connection, parallel execution capability depends on the driver/connection. Some drivers require statements on the same connection to be serialized or do not support multiple concurrent operations.

If strict ordering is needed or the driver does not support concurrent statements on the same connection, compose sequentially with `flatMap`/`then`. Do not assume a transaction automatically creates multiple connections for each branch.

## 7. Using flatMap and concatMap for Flux

When each element of a `Flux` requires an asynchronous operation, return the publisher from the mapper instead of subscribing inside a callback.

Example processing each order:

```java
public Flux<OrderReceipt> processOrders(Flux<Long> orderIds) {
    return orderIds.flatMap(orderId ->
        orderRepository.findById(orderId)
            .flatMap(order -> paymentService.capture(order)
                .map(payment -> new OrderReceipt(order, payment)))
    );
}
```

`flatMap` subscribes to and merges inner publishers, and can run multiple elements in parallel. Output order does not necessarily match the order of `orderIds`.

If processing order must be preserved:

```java
public Flux<OrderReceipt> processOrdersInOrder(Flux<Long> orderIds) {
    return orderIds.concatMap(orderId ->
        orderRepository.findById(orderId)
            .flatMap(order -> paymentService.capture(order)
                .map(payment -> new OrderReceipt(order, payment)))
    );
}
```

`concatMap` waits for the current inner publisher to complete before processing the next element. It preserves order while reducing concurrency.

### 7.1. Limiting flatMap concurrency

With large sources, you should not let thousands of database or HTTP operations run simultaneously:

```java
return orderIds.flatMap(this::processOneOrder, 8);
```

The number `8` is the maximum concurrency for inner publishers in this operator. Choose the value based on connection pool size, external service limits, latency, and database load.

Limiting concurrency remains part of the same pipeline. There is no need to create a separate `subscribe()` for each element.

### 7.2. Do not call subscribe inside a loop

Avoid:

```java
public Mono<Void> importOrders(List<Order> orders) {
    for (Order order : orders) {
        orderRepository.save(order).subscribe();
    }
    return Mono.empty();
}
```

The method can complete immediately while separate subscriptions are still running. Errors from individual `INSERT`s are not aggregated into the returned result; there is no backpressure or shared concurrency limit.

Prefer:

```java
public Mono<Void> importOrders(List<Order> orders) {
    return Flux.fromIterable(orders)
        .concatMap(orderRepository::save)
        .then();
}
```

Or bound concurrency if the operations are independent and the driver/pool permit it:

```java
public Mono<Void> importOrders(List<Order> orders) {
    return Flux.fromIterable(orders)
        .flatMap(orderRepository::save, 8)
        .then();
}
```

For large lists, you can use `buffer(batchSize)` to process in batches and bound memory usage.

## 8. subscribe() breaks error and result propagation

A publisher has a clear signal contract:

- `onNext`: emits a value.
- `onComplete`: completes successfully.
- `onError`: terminates with an error.
- `cancel`: downstream no longer wants data.

When a service self-subscribes without returning that subscription, those signals are no longer inside the publisher received by the caller.

Example:

```java
public Mono<Void> saveCustomer(Customer customer) {
    customerRepository.save(customer)
        .subscribe(
            saved -> log.info("Saved {}", saved.getId()),
            error -> log.error("Save failed", error)
        );

    return Mono.empty();
}
```

The error callback may log the error, yet the caller still sees `Mono.empty()` complete normally. A controller could return HTTP success even though the `INSERT` failed. A test subscribing to `Mono.empty()` will neither wait for nor assert on the save operation.

Return the publisher instead:

```java
public Mono<Void> saveCustomer(Customer customer) {
    return customerRepository.save(customer)
        .doOnNext(saved -> log.info("Saved {}", saved.getId()))
        .then();
}
```

If an error occurs, the caller receives it and can decide whether to retry, map it to a business error, or return an appropriate HTTP status.

## 9. subscribe() breaks cancellation

Suppose a client sends a request to create an order and then closes the connection before the database finishes. If the service returns the save operation's publisher, cancellation can propagate upstream to the R2DBC operation. The driver and transaction manager handle cancelling the statement, rolling back, or releasing the connection as supported.

If the service already called `subscribe()` separately:

```java
public Mono<Order> create(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.just(order);
}
```

The returned publisher has no link to the save operation. When the client cancels the response, the separate save subscription can continue running. The service has no clean way to cancel it, and does not know whether the data was written or not.

Cancellation does not mean every database operation is always aborted instantaneously; the driver may already be performing I/O or the database may have processed the statement. However, keeping the work in the same pipeline gives the framework and driver a chance to handle cancellation properly within the lifecycle, while letting the caller know the publisher was cancelled.

## 10. subscribe() breaks reactive transaction boundaries

Spring reactive transactions bind transaction resources to the subscription and Reactor Context. `@Transactional` on a method returning `Mono`/`Flux` manages the publisher returned by the method. `TransactionalOperator` likewise wraps the publisher passed to it.

Example to avoid:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.just(order);
}
```

Calling `subscribe()` inside the method body creates a separate subscription as soon as the Java method body executes to build the returned publisher. The transactional publisher managed by the Spring proxy is only subscribed to later. The detached subscription does not automatically join the transaction context of the outer publisher. Therefore, the save operation can run outside the transaction the caller thinks is managing it.

Compose instead:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
```

### 10.1. Multiple operations within the same transaction

```java
@Transactional
public Mono<Order> createOrder(
        Order order,
        List<OrderLine> requestedLines) {

    return orderRepository.save(order)
        .flatMap(savedOrder -> {
            List<OrderLine> lines = requestedLines.stream()
                .map(line -> line.withOrderId(savedOrder.getId()))
                .toList();

            return orderLineRepository.saveAll(lines)
                .thenReturn(savedOrder);
        });
}
```

When the returned publisher is subscribed to through the Spring proxy, repository operations in the pipeline can join the same reactive transaction provided they use the same `ConnectionFactory` and transaction manager. If saving order lines emits an error and the error propagates out, the transaction manager can roll back both the order and the lines.

### 10.2. Swallowing errors can cause a transaction to commit

Even without calling `subscribe()`, the placement of `onErrorResume` still matters:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(this::saveLines)
        .onErrorResume(error -> Mono.empty());
}
```

If an error is converted to `Mono.empty()` inside the transactional publisher, the transaction boundary may see only a normal completion and commit the changes made before the error. If you want to roll back first and then fall back, let the error pass through the transaction boundary and place the handler outside the transactional publisher or outside the transactional method.

## 11. subscribeOn and publishOn are not subscribe()

Operator names can be confusing:

- `subscribe()` creates a subscription and activates the publisher.
- `subscribeOn(scheduler)` specifies the scheduler used for subscription/source subscription per Reactor semantics.
- `publishOn(scheduler)` switches downstream signal processing to the specified scheduler.

Example:

```java
return customerRepository.findById(id)
    .publishOn(Schedulers.parallel())
    .map(this::calculateView);
```

`publishOn` does not subscribe to the publisher on its own. The caller still needs to subscribe at the execution boundary. With R2DBC, the driver already provides non-blocking I/O; do not mechanically add `subscribeOn(Schedulers.boundedElastic())` the way blocking JDBC is offloaded to a thread pool. Only choose a scheduler when there is a specific reason, such as calling an irreplaceable blocking API or running suitable CPU computation.

Do not use `subscribeOn` to disguise calling `subscribe()` manually in a service. Those are two completely different things.

## 12. block(), toFuture(), and other ways of triggering subscriptions

Avoid simply replacing `subscribe()` with another API that still breaks composition.

### 12.1. block()

`block()` subscribes to a publisher and waits synchronously for the result:

```java
// Avoid in a reactive service/controller.
Customer customer = customerRepository.findById(id).block();
```

This behavior blocks a thread, loses non-blocking benefits, and can throw an error when called on a Reactor non-blocking thread. Return `Mono<Customer>` or compose with `flatMap`.

### 12.2. toFuture()

`Mono.toFuture()` also triggers a subscription to complete a `CompletableFuture`. If you call it and discard the future or fail to compose the result, the work is still detached from the reactive pipeline:

```java
// Avoid: triggers work without bringing the result into the pipeline.
customerRepository.findById(id).toFuture();
return Mono.empty();
```

If you need to integrate with an API returning `CompletionStage`, convert at the integration boundary and ensure the future is returned/composed with proper error and cancellation handling. In purely reactive repository and service layers, prefer keeping `Mono`/`Flux` throughout.

### 12.3. subscribe() without an error handler

The statement:

```java
publisher.subscribe();
```

provides nowhere for caller business error handling. Errors may go to Reactor's dropped-error hook or default logging, depending on context. Do not treat those logs as application error handling.

## 13. When might manual subscription be appropriate?

Subscription is the execution trigger in Reactive Streams, so something somewhere must subscribe. What should be avoided is repositories or services creating hidden subscriptions detached from the caller's contract.

Explicit subscription can be appropriate at an application boundary when:

- A command-line process needs to run a publisher and then exit.
- A background worker or component is responsible for owning the task lifecycle.
- An integration adapter must bridge an imperative callback source with a reactive pipeline.
- An application does not use WebFlux or a framework that consumes publishers automatically.

In these cases, the boundary component must take responsibility for:

- Tracking the `Disposable` if the work needs to be cancelled.
- Handling errors completely and feeding them into appropriate logging/metrics/alerts.
- Limiting concurrency and queued work.
- Closing subscriptions when the application shuts down or tasks expire.
- Never reporting success before the publisher completes.
- Ensuring transaction and resource lifecycles stay inside the subscribed publisher.

Example of an imperative runner owning waiting for task completion:

```java
@Component
public class DataImportRunner implements CommandLineRunner {

    private final ImportService importService;

    public DataImportRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) {
        importService.importData()
            .block(); // Only at the imperative boundary of the process.
    }
}
```

This example uses `block()` at an imperative entry point to wait for startup import work to finish before the runner exits. It is not a pattern for repositories/services. In an end-to-end reactive application, let the framework manage subscriptions instead of creating them in many places.

If using `subscribe()` in a background component, retain the `Disposable` and enforce clear shutdown/error policies. Do not assign a subscription to a local variable and forget about it.

## 14. Reliable background work: use a queue or transactional outbox

A common reason developers call `subscribe()` in a service is wanting to “save data and then send an email/push an event in the background” without waiting.

Example to avoid:

```java
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .doOnNext(saved -> emailService.sendReceipt(saved).subscribe());
}
```

The email is sent via a separate subscription. The service does not know whether the email succeeded or failed; the request can finish before sending; the process can stop mid-flight; and sending can happen before the order-saving transaction commits.

If notifications must be sent reliably after data commits, consider a transactional outbox:

1. In the same transaction, save the order and an outbox record describing the event to publish.
2. Commit the transaction.
3. A separate worker reads the outbox in batches and sends the events/emails.
4. Once sending succeeds, mark the record as processed.
5. On transient errors, retry with limits; use event IDs/idempotency to guard against duplicate sends.

Service example:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved -> outboxRepository.save(
            OutboxEvent.orderCreated(saved.getId())
        ).thenReturn(saved));
}
```

The worker reads the outbox and publishes events in a separate workflow. This ensures saving the data and recording the intent to emit an event commit together, while actual delivery can be retried independently. It does not magically provide absolute exactly-once delivery; consumers still need idempotency because messages can be redelivered.

If a side effect is strictly best-effort and losing it on application shutdown is acceptable, you can use a background executor/worker with an explicit lifecycle. Still, keep subscription, error handling, and shutdown responsibilities inside that component rather than hiding them inside a repository.

## 15. Handling errors properly within the same pipeline

When keeping publishers in one pipeline, errors can be handled at the right layer:

```java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorMap(DataAccessException.class,
            error -> new CustomerStoreUnavailableException(error));
}
```

The caller receives a publisher that can emit `CustomerNotFoundException` or `CustomerStoreUnavailableException`. Controller advice can map them to appropriate HTTP statuses.

If the service calls `subscribe()` internally, errors no longer propagate to the caller in the same way. The service might log an error while the response still returns success, or the error hits a global hook without request context.

### 15.1. Fallbacks must be part of the pipeline

Example checking cache first, then reading the database on a cache miss:

```java
public Mono<Customer> findCustomer(Long id) {
    return cacheService.findCustomer(id)
        .switchIfEmpty(customerRepository.findById(id))
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

The database publisher is subscribed to when the fallback branch is selected. No manual `subscribe()` inside `switchIfEmpty` is needed.

### 15.2. Do not convert all errors into empty

```java
// Avoid if database errors need to be reported to the caller.
return customerRepository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

This code prevents the caller from distinguishing “customer does not exist” from “the database is failing”. Only fall back for specific, business-meaningful error types.

## 16. Testing services without manual subscribe in production code

In tests, `StepVerifier` is an intentional subscriber. It activates the publisher and verifies signals:

```java
@Test
void createOrderReturnsSavedEntity() {
    StepVerifier.create(orderService.createOrder(order, lines))
        .assertNext(saved -> assertNotNull(saved.getId()))
        .verifyComplete();
}
```

Testing errors:

```java
@Test
void propagatesDatabaseFailure() {
    StepVerifier.create(orderService.createOrder(order, lines))
        .expectError(DataAccessException.class)
        .verify();
}
```

Testing operation order can use mocks or a test database to verify that `saveAll(lines)` only runs after `save(order)` emits an entity with an ID.

With R2DBC integration tests, wait for the publisher to complete before inspecting database state. Do not call `subscribe()` inside a service and then use `Thread.sleep()` in tests to wait for background operations; that creates flaky tests and hides lifecycle bugs.

## 17. Observing subscriptions and reactive work

When an application exhibits “the request returned success but data was not written”, check:

- Did a service call `subscribe()` and then return a different publisher?
- Are there hidden `block()`, `toFuture()`, or subscriptions inside callbacks?
- Was the publisher returned all the way to the controller/framework?
- Is there an `onErrorResume` branch turning errors into empty/default?
- Was an inner publisher created without being composed?
- Was the subscription disposed/cancelled before completion?
- Does the transaction boundary wrap the publisher containing the database operations?
- Are there logs/metrics for rows written, errors, and completion time?

Log at observation points in the pipeline:

```java
return orderRepository.save(order)
    .doOnSubscribe(subscription -> log.debug("Saving order"))
    .doOnNext(saved -> log.info("Saved order {}", saved.getId()))
    .doOnError(error -> log.error("Order save failed", error))
    .doFinally(signal -> log.debug("Order save finished: {}", signal));
```

`doFinally` can observe complete, error, or cancel. These callbacks are strictly for synchronous observation; do not use them to launch another publisher via `subscribe()`.

## 18. Common mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Calling `repository.save(...).subscribe()` then returning `Mono.just(...)` | Caller does not wait for database and may receive a false success | Return the publisher from the repository |
| Calling `subscribe()` in a custom repository | Breaks the reactive contract of the repository | Return `Mono`/`Flux` from `DatabaseClient` or SPI |
| Calling repository inside `doOnNext` and subscribing | Inner publisher is neither composed nor awaited | Use `flatMap`/`delayUntil` |
| Subscribing inside a loop | Multiple scattered tasks without shared backpressure | Use `Flux.fromIterable` and `flatMap`/`concatMap` |
| Ignoring `Disposable` | Cannot actively manage cancellation of background tasks | Let caller own the publisher or manage `Disposable` at the boundary |
| Not providing an error handler for background subscriptions | Errors can be dropped or only show up in hooks/logs | Return errors via publisher or handle thoroughly in the worker owner |
| Using `block()` in reactive service | Blocks thread and can cause non-blocking errors | Compose with Reactor operators |
| Calling `toFuture()` and discarding the result | Triggers subscription outside the pipeline | Return publisher or compose the future at the integration boundary |
| Using `Mono.empty()` to mask errors | Caller thinks data does not exist instead of knowing the system failed | Only fall back for errors/empty with explicit semantics |
| Swallowing errors inside a transaction | Transaction may commit after normal completion | Let errors propagate across the boundary when rollback is needed |
| Thinking `subscribeOn` subscribes automatically | Publisher still does not run without a subscriber | Subscribe at the execution boundary |
| Calling `subscribe()` inside a `@Transactional` method | Inner subscription may run outside the transaction context | Return the proxy-managed publisher |
| Calling `Mono.when` for same-connection statements assuming safe parallelism | Driver may not support concurrent statements | Serialize when needed and test the driver |
| Using background subscriptions for critical emails/events | Side effects may be lost or run before commit | Use an outbox/queue and a lifecycle-managed worker |

## 19. Process for designing a reactive service

When writing a Repository or service method, follow these steps:

1. Identify the value or signal the caller needs: entity, DTO, row count, `Void`, or error.
2. Return `Mono`/`Flux` from the repository and do not self-subscribe inside the implementation.
3. Chain dependent operations using `flatMap`, `then`, or `delayUntil`.
4. Combine independent sources using `zip`/`when` when semantics and driver allow.
5. For multi-element sources, choose `flatMap` with finite concurrency or `concatMap` if order is required.
6. Place error handling in the pipeline while letting rollback-triggering errors reach the transaction boundary.
7. Apply `@Transactional` or `TransactionalOperator` to the exact publisher to be managed.
8. Return the publisher to the caller/framework; do not call `subscribe()`, `block()`, or discard `toFuture()` inside services.
9. If background work is genuinely required, move it to a worker/queue/outbox with a clear owner.
10. Test using `StepVerifier` and an integrated database; verify completion, errors, cancellation, and transactions.

## 20. Principles to remember

- `Mono` and `Flux` describe reactive work; subscription triggers work.
- Repositories and services should return publishers, not call `subscribe()` themselves to run in the background.
- `subscribe()` creates a separate subscription; the caller loses control over that work's result, errors, and cancellation through the returned publisher.
- Use `flatMap` for async operations depending on a previous result; use `then` when you only need to wait for completion.
- Use `delayUntil` when waiting on a reactive side effect while still emitting the original value.
- `doOnNext` is for synchronous observation/side effects; do not use it to launch another `Publisher`.
- Use `zip`, `when`, `flatMap`, and `concatMap` according to their semantics; limit concurrency when necessary.
- `block()` and `toFuture()` can also trigger subscriptions; avoid them in reactive layers.
- `subscribeOn` and `publishOn` control schedulers, not subscription ownership.
- Reactive transactions manage the returned publisher; a detached subscription may run outside the transaction context.
- Let errors pass through the transaction boundary if rollback is desired; do not unintentionally convert errors into completion.
- WebFlux, `StepVerifier`, or a responsible application boundary is the right place to subscribe.
- Important background work should use a queue/outbox and a worker with lifecycle, retry, and idempotency.
- Do not call `subscribe()` inside a loop; compose the source with `Flux` to preserve backpressure and error propagation.

Avoiding manual `subscribe()` inside repositories and services keeps a single continuous reactive flow from the data access layer up to the caller. When all operations are composed with Reactor operators, the caller can control execution timing, receive errors, cancel work, and participate in transactions properly. Subscriptions should only be created at an execution boundary responsible for managing results and their lifecycle.
