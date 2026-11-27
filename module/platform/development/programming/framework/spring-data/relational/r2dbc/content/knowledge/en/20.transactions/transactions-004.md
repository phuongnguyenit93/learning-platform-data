# Start, Commit, and Rollback Timing by Execution Subscription

In Spring Data Relational R2DBC, transactions follow the reactive model and are tied to the subscription lifecycle of a `Mono` or `Flux`. Calling a repository method, creating a `Mono`, chaining Reactor operators, or wrapping a publisher with `TransactionalOperator` only describes the work. A reactive transaction starts when the transactional publisher is subscribed; the transaction is committed when the stream completes successfully and rolled back when the stream terminates with an error or is cancelled according to transaction management mechanics.

This differs from what many developers are accustomed to with synchronous JDBC, where statements typically execute immediately during the method call. Misunderstanding subscription timing can cause an application to create a publisher without executing it, run an operation outside the transaction, swallow an error so the transaction commits, or cancel a stream in a way that causes an unexpected rollback.

## 1. Reactive transactions are bound to subscription

R2DBC operations such as repository methods, `DatabaseClient`, and `R2dbcEntityTemplate` return publishers. These publishers are typically lazy: they describe work and only execute when a subscriber requests data.

Example:

```java
Mono<Customer> customerMono = customerRepository.findById(10L);
```

At the time that line executes, the application creates a `Mono<Customer>`. The database query has usually not run yet. Once subscribed:

```java
customerMono.subscribe();
```

or when the publisher is consumed by the WebFlux framework, execution begins.

For reactive transactions, the same rule applies to transaction boundaries:

- Creating a transactional publisher: describes the work to be performed in the transaction.
- Subscribing to the publisher: the transaction manager starts the transaction and establishes the transaction context.
- Executing R2DBC operations: operations participate in the transaction if they use the right connection factory and Spring-managed connection mechanism.
- Publisher completes successfully: the transaction manager commits.
- Publisher emits an error: the transaction manager rolls back according to transaction rules.
- Subscription cancelled before completion: the transaction manager handles rollback upon receiving cancellation per reactive transaction semantics.

### 1.1. Lifecycle diagram

```text
Application calls service method
             |
             v
Creates Mono / Flux (SQL not run yet)
             |
             v
Publisher is subscribed
             |
             v
ReactiveTransactionManager begins transaction
             |
             v
R2DBC operations execute in transaction context
             |
       +-----+----------------+
       |                      |
       v                      v
Publisher onComplete      onError / cancel
       |                      |
       v                      v
    COMMIT                 ROLLBACK
```

This diagram illustrates the general rule. Operators can turn an error signal into a value or turn stopping upstream into completion; therefore, operator placement inside versus outside the transaction boundary matters greatly.

## 2. Creating a publisher does not mean starting a transaction

A common mistake is assuming a transaction has already started immediately upon calling a `@Transactional` method or creating a publisher.

Example:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request));
}
```

The method returns `Mono<Order>`. With a reactive transaction manager, the transaction is bound to the subscription process of the proxy-managed publisher. If the caller does not subscribe or the framework does not consume the publisher, the save operation does not run and no transaction executes.

This is why WebFlux controllers typically return `Mono` or `Flux` directly to the framework:

```java
@PostMapping("/orders")
public Mono<Order> create(@RequestBody CreateOrderRequest request) {
    return orderService.createOrder(request);
}
```

WebFlux manages the subscription of the response body. There is no need to call `subscribe()` manually in a controller.

### 2.1. A publisher subscribed multiple times

A regular reactive publisher can be subscribed to multiple times. With lazy database operations, each subscription may re-execute the query or write operation. If the publisher is wrapped in a transaction boundary, each subscription typically initiates a separate transaction execution.

```java
Mono<Order> savePublisher = transactionalOperator.transactional(
    orderRepository.save(order)
);
```

If two independent subscribers both subscribe to `savePublisher`, do not assume the INSERT executes only once. There may be two transactions and two writes, depending on the publisher and ID/constraint strategy.

If business logic requires exactly-once execution, manage subscription in a single place, use an idempotency key, or apply appropriate duplicate-write prevention. Do not rely on holding a `Mono` variable as a guarantee that the database executes only once.

## 3. Execution timing of method body code and Mono.defer

A reactive transaction begins when the transactional publisher is subscribed, yet the Java body of the service method still runs immediately when the method is called to assemble the publisher. Operations performed eagerly during pipeline assembly do not automatically become reactive database work.

Example:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    AuditEntry audit = createAuditEntry(request); // Runs immediately when the method is called.

    return orderRepository.save(toOrder(request))
        .doOnNext(order -> audit.setOrderId(order.getId()));
}
```

`createAuditEntry(...)` is synchronous Java code and runs before subscription. If it accesses resources or performs side effects you want deferred into the transactional flow, defer that work with `Mono.defer` or an appropriate publisher:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    return Mono.defer(() -> {
        AuditEntry audit = createAuditEntry(request);

        return orderRepository.save(toOrder(request))
            .flatMap(order -> auditRepository.save(
                audit.withOrderId(order.getId())
            ).thenReturn(order));
    });
}
```

The lambda inside `defer` is invoked when subscription begins. Repository publishers are composed within the same pipeline and can therefore share the Spring-managed transaction.

There is no need to wrap every repository call in `defer` if it already creates a lazy publisher with no eager side effects. `defer` is especially useful when you need to delay publisher creation, read runtime state, or execute synchronous code until subscription time.

## 4. Commit occurs when the publisher completes successfully

In a reactive transaction, the `onComplete` signal indicates the publisher finished normally. The transaction manager can perform commit after all work inside the transactional boundary finishes.

Example using `TransactionalOperator`:

```java
Mono<Order> work = orderRepository.save(order)
    .flatMap(saved -> orderLineRepository.saveAll(linesFor(saved))
        .then(Mono.just(saved)));

return transactionalOperator.transactional(work);
```

When the subscription completes normally, saving the order and order lines resides in the same transactional publisher. The transaction manager commits after the source publisher completes.

### 4.1. Mono.empty() is still a successful completion

An important point: `Mono.empty()` is not an error. It emits `onComplete` without emitting a value. Therefore, if a transactional publisher completes with `Mono.empty()`, the transaction is normally considered to have completed successfully and can commit.

Example:

```java
@Transactional
public Mono<Void> cancelOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.delete(order))
        .then();
}
```

If no order is found, `findById` completes empty. `flatMap` does not run and `.then()` also completes normally. This does not automatically cause a rollback.

If business logic requires a missing order to be an error, convert the empty state into an error:

```java
@Transactional
public Mono<Void> cancelOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(
            new OrderNotFoundException(orderId)
        ))
        .flatMap(order -> orderRepository.delete(order));
}
```

When the exception is emitted through the publisher inside the transaction scope, the transaction manager can roll back according to rollback rules.

### 4.2. Commit does not happen immediately after a query emits a value

A `Mono` may emit a value and then complete. With a transaction wrapping the whole pipeline, receiving an item does not mean the transaction has already committed. Commit happens when the transactional publisher terminates successfully.

With `Flux`, the transaction can remain open for the entire time elements are emitted. If downstream processing is slow, the connection and transaction may be held for a long time. Do not return an unbounded `Flux` from inside a transaction if business logic does not require holding the transaction across the entire stream.

## 5. Rollback when the publisher emits an error

When an operation inside a transaction emits an error and that error reaches the transactional boundary, the transaction manager performs rollback according to configured rules.

Example:

```java
Mono<Order> createOrder(CreateOrderRequest request) {
    Mono<Order> work = orderRepository.save(toOrder(request))
        .flatMap(order -> orderLineRepository.saveAll(
                linesFor(order, request))
            .then(Mono.just(order)))
        .flatMap(order -> inventoryRepository.reserve(
                request.productId(), request.quantity())
            .thenReturn(order));

    return transactionalOperator.transactional(work);
}
```

If saving the order succeeds but saving order lines or reserving inventory emits an error within the same transaction, the error propagates out and the transaction manager rolls back the changes belonging to that transaction.

Conditions for proper rollback:

- Operations genuinely belong to the same transactional publisher.
- They use the same connection factory managed by the transaction manager.
- Errors are not swallowed before reaching the transaction boundary.
- The database and driver support transactions for those operations.

If an operation was split off via an independent `subscribe()` or uses a different connection factory, it may not belong to the transaction under consideration.

## 6. Cancellation also affects transactions

In Reactive Streams, cancellation signals that downstream no longer needs data. It differs from `onComplete` and `onError`. When a subscriber cancels a transactional publisher before completion, Spring's reactive transaction management handles rollback to avoid committing an interrupted stream.

Common causes of cancellation:

- An HTTP client closes the connection while the request is running.
- A timeout at the web or service layer cancels the subscription.
- A downstream operator needs no more data and cancels upstream.
- A large pipeline is cancelled because another branch failed.
- The application explicitly disposes the subscription.

This is especially important with `Flux`:

```java
Flux<Order> transactionalOrders = transactionalOperator.transactional(
    orderRepository.findAll()
        .doOnNext(this::processOrder)
);

return transactionalOrders;
```

If the subscriber cancels the stream before completion, the transaction can roll back. Do not use a transactional `Flux` as a long or unbounded data-loading stream unless you intentionally intend to hold the transaction and connection for the entire stream lifecycle.

### 6.1. Operator placement can change the signal observed by the transaction

A transaction boundary can only react to signals emitted by the publisher inside it. For example, `onErrorResume` placed inside the boundary can turn an error into normal completion; `take` placed inside the boundary can complete downstream normally after cancelling the upstream source. Conversely, cancellation from downstream on the wrapped transactional publisher can be observed directly by the transaction operator.

Therefore, place `take`, `next`, `onErrorResume`, timeouts, and short-circuiting operators intentionally. If the goal is rollback when all work is not processed, do not convert cancellation or error into successful completion before the signal reaches the transaction boundary.

## 7. Using TransactionalOperator

`TransactionalOperator` is the explicit programmatic way to wrap a publisher in a reactive transaction. It uses a `ReactiveTransactionManager`, such as `R2dbcTransactionManager`.

### 7.1. Declaring the bean

```java
@Configuration
public class TransactionConfiguration {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
```

In an application with only one reactive transaction manager, Spring can inject the right bean. With multiple managers, use qualifiers or explicit bean names to avoid picking the wrong manager.

### 7.2. Wrapping a publisher with transactional(...)

```java
public Mono<Order> placeOrder(CreateOrderRequest request) {
    Mono<Order> work = orderRepository.save(toOrder(request))
        .flatMap(order -> saveLines(order, request)
            .thenReturn(order))
        .flatMap(order -> reserveInventory(order, request)
            .thenReturn(order));

    return transactionalOperator.transactional(work);
}
```

`transactional(work)` returns a transaction-managed publisher. When subscribed, the transaction begins. When `work` completes successfully, the transaction commits; if an error propagates through, the transaction rolls back.

### 7.3. Using as(...) to express the boundary

Reactor allows writing pipelines in this form:

```java
return orderRepository.save(order)
    .flatMap(this::saveLines)
    .thenReturn(order)
    .as(transactionalOperator::transactional);
```

`as(...)` passes the current publisher to the provided function. This style puts the transaction boundary at the end of the pipeline and makes it easy to see all wrapped work.

### 7.4. Using execute(...) when TransactionStatus is needed

`execute(...)` provides `ReactiveTransaction` in a callback:

```java
Flux<Order> result = transactionalOperator.execute(status ->
    orderRepository.findByStatus("PENDING")
        .flatMap(order -> process(order))
);
```

This API returns `Flux<T>`. Use it when you need to interact with the transaction status via the provided API. Do not manually call commit inside the callback while `TransactionalOperator` manages the lifecycle; let the operator end the transaction based on publisher signals.

## 8. Using @Transactional on reactive methods

Spring supports declarative transactions with `@Transactional`. For reactive methods returning `Mono` or `Flux`, Spring uses `ReactiveTransactionManager` and manages the transaction by subscription.

```java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository lineRepository;

    public OrderService(
            OrderRepository orderRepository,
            OrderLineRepository lineRepository) {
        this.orderRepository = orderRepository;
        this.lineRepository = lineRepository;
    }

    @Transactional
    public Mono<Order> create(CreateOrderRequest request) {
        return orderRepository.save(toOrder(request))
            .flatMap(order -> lineRepository.saveAll(
                    toLines(order, request))
                .then(Mono.just(order)));
    }
}
```

When the method is called through a Spring proxy and the publisher is subscribed, operations in the pipeline can join the same reactive transaction.

### 8.1. Selecting the right transaction manager

An application may use both JDBC/JPA and R2DBC concurrently. `PlatformTransactionManager` is for imperative transactions, while R2DBC requires a `ReactiveTransactionManager`, typically `R2dbcTransactionManager`.

If multiple managers exist, specify explicitly:

```java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> create(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request));
}
```

The bean name must match the application's actual configuration. Do not assume the annotation automatically picks the right manager just because the method returns `Mono`.

### 8.2. Must pass through a Spring proxy

`@Transactional` relies on proxying in standard Spring configurations. Calling a transactional method from outside the bean through the proxy triggers the interceptor. Calling another method internally on the same instance (`this.someTransactionalMethod()`) typically bypasses the proxy, so the annotation on the called method may not take effect.

If a separate transaction boundary is needed, structure service beans appropriately or use `TransactionalOperator` explicitly. Do not rely on self-invocation to start a new transaction.

### 8.3. Methods must return a publisher

For reactive transactions, the method should return a publisher that Spring can wrap and manage. If a method returns `void` or calls `subscribe()` and returns immediately, the transaction interceptor cannot manage the full asynchronous work as intended.

## 9. Differences between TransactionalOperator and @Transactional

| Criterion | `TransactionalOperator` | `@Transactional` |
|---|---|---|
| Declaration | Explicitly wraps publisher in code | Annotation on method/class |
| Boundary | Position of `transactional(...)` or `as(...)` | Method boundary managed by Spring proxy |
| Suitable for | Pipelines needing mid-flow transactions or flexible boundaries | Use cases/service methods with clear boundaries |
| Proxy required | No AOP proxy needed for the operator | Yes under default proxy mechanism |
| Choosing manager | Pass `ReactiveTransactionManager` when creating operator | Choose manager via config/annotation attribute |
| Readability | Boundary visible right inside the pipeline | Annotation shows boundary at method/class level |

Both rely on Spring's reactive transaction management. Choose the one fitting the structure of your use case; do not wrap the same publisher in multiple nested transaction boundaries just to feel "safer". Transaction propagation and nesting must be designed intentionally.

## 10. Placement of onErrorResume determines whether the transaction sees errors

One of the hardest bugs to spot is catching an error inside a transactional publisher and turning it into a success value. When that happens, the transaction boundary may only see `onComplete` and commit.

### 10.1. Catching errors inside the transaction: may commit

```java
Mono<Order> work = orderRepository.save(order)
    .flatMap(this::saveLines)
    .onErrorResume(error -> {
        log.error("Failed to save order details", error);
        return Mono.empty();
    });

return transactionalOperator.transactional(work);
```

`onErrorResume` is inside the wrapped publisher. If it turns the error into `Mono.empty()`, the `work` publisher completes normally. The transaction operator may commit changes made before the error occurred.

This can leave an inconsistent state if the order was INSERTed while order lines failed and the error was swallowed.

### 10.2. Catching errors outside the transaction: rollback before fallback

```java
return transactionalOperator.transactional(
        orderRepository.save(order)
            .flatMap(this::saveLines)
    )
    .onErrorResume(error -> {
        log.error("Failed to create order", error);
        return Mono.empty();
    });
```

Here the transaction operator receives the error from the inner work and performs rollback. Only after the transactional publisher terminates with an error does the outer `onErrorResume` turn the error into an empty result for the caller.

### 10.3. Error-handler placement guidelines

- If an error must cause rollback, let the error cross the transaction boundary.
- If a fallback is needed after rollback, place the fallback outside the transactional publisher.
- If intentionally handling an error and continuing the transaction, clarify what data has changed and whether the transaction state remains valid.
- Do not turn persistence errors into `Mono.empty()` merely to avoid returning errors to the API.
- Log and map errors at the right layer without hiding signals needed by the transaction manager.

With `@Transactional`, the same principle applies: if the publisher returned by the method already converted an error into completion before the interceptor observes it, the transaction may commit. Define clearly which errors count as use-case failures.

## 11. Rollback rules with @Transactional

With declarative transactions, Spring applies rollback rules. By traditional default, unchecked exceptions (`RuntimeException`) and `Error` trigger rollback; checked exceptions do not trigger rollback automatically unless configured accordingly.

Example:

```java
@Transactional(rollbackFor = Exception.class)
public Mono<Order> create(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request))
        .flatMap(order -> validateAndSaveLines(order, request));
}
```

`rollbackFor` extends the rollback rule to the specified exception types. `noRollbackFor` can be used when an exception is defined as not requiring rollback, but consider carefully because the transaction may commit partial data even though the caller receives an error.

When working with `TransactionalOperator`, an error emitted by the publisher is a pipeline failure signal and the operator handles rollback according to programmatic transaction semantics. If special exception-type rollback rules are needed, design error classification and transaction definitions to match your Spring API/version; do not assume annotation rollback rules and every custom operator share identical configuration mechanics.

## 12. Mono.empty(), business errors, and affected row counts

Not every "no change" result is a technical error. For example, an update may return 0 affected rows:

```java
Mono<Long> updated = template.update(query, update, Order.class);
```

If the result is `0L`, the transaction can still complete normally. If business logic requires updating exactly one row, convert that outcome into an error before the transaction ends:

```java
Mono<Void> markPaid(Long orderId) {
    return orderRepository.updateStatus(orderId, "PAID")
        .flatMap(rows -> rows == 1
            ? Mono.empty()
            : Mono.error(new OrderStateConflictException(orderId)))
        .then();
}
```

When the error reaches the transaction boundary, the transaction can roll back. If you only log `rows == 0` and return `Mono.empty()`, the transaction may commit because the publisher completed successfully.

## 13. All operations must participate in the same transaction context

Reactive transactions do not rely on `ThreadLocal` like traditional imperative transaction management. Spring binds transaction resources to the subscription's Reactor Context.

This means:

- Reactor operators composed in the same subscription can carry the transaction context across different threads.
- `publishOn` or `subscribeOn` do not automatically lose the transaction context when using Reactor properly.
- Creating a new subscription via manual `subscribe()` creates an independent execution flow that does not inherit the parent flow's transaction.
- Operations using a different `ConnectionFactory` do not participate in the current transaction.
- Operations accessing connections directly must use a Spring-aware mechanism if they need the transaction-bound connection.

### 13.1. Using DatabaseClient/repositories/template

Spring Data R2DBC abstractions are designed to work with Spring-managed connections. Example:

```java
@Transactional
public Mono<Void> createOrderAndAudit(Order order, AuditEntry audit) {
    return orderRepository.save(order)
        .flatMap(saved -> auditRepository.save(
            audit.withOrderId(saved.getId())
        ))
        .then();
}
```

If both repositories use the same `ConnectionFactory` and transaction manager, the operations can share the same transaction.

### 13.2. Be careful when calling ConnectionFactory.create() directly

The following code creates a connection directly:

```java
Mono.from(connectionFactory.create())
    .flatMap(connection -> ...);
```

Inside an active Spring transaction, calling raw `create()` may acquire an independent connection rather than the connection bound to the Reactor Context by the transaction manager. If the operation needs to join the transaction, use `DatabaseClient`, `R2dbcEntityTemplate`, repositories, or Spring utilities like `ConnectionFactoryUtils` as appropriate for your version.

This is a common mistake that causes part of the data to roll back while the operation on the independent connection still commits.

## 14. Do not call subscribe() inside a transactional service

Do not manually subscribe to a database operation inside a method and return immediately:

```java
@Transactional
public Mono<Void> createOrder(Order order) {
    orderRepository.save(order).subscribe();
    return Mono.empty();
}
```

In this example, the `save` subscription is detached from the publisher managed by the transaction interceptor. The method returns `Mono.empty()` which can complete immediately; the transaction boundary does not wait for the independent save operation. Errors from the separate subscription are also not propagated properly to the caller.

Instead, compose the publisher:

```java
@Transactional
public Mono<Void> createOrder(Order order) {
    return orderRepository.save(order).then();
}
```

The same rule applies to `block()`: do not block a reactive pipeline waiting for database results. Chain publishers with `map`, `flatMap`, `then`, `zip`, or other suitable operators.

## 15. Nested transactions and propagation

When one transactional service calls another transactional service, Spring applies the configured propagation. With reactive transactions, context and resources propagate along the subscription.

Common propagation modes:

| Propagation | General meaning |
|---|---|
| `REQUIRED` | Join existing transaction; create a new one if none exists |
| `REQUIRES_NEW` | Create a new independent transaction, temporarily detaching the current transaction as supported by the manager |
| `SUPPORTS` | Join if a transaction exists; otherwise run without a transaction |
| `MANDATORY` | Require an existing current transaction |
| `NOT_SUPPORTED` | Run outside the current transaction |
| `NEVER` | Disallow an existing current transaction |
| `NESTED` | Nested transaction/savepoint if supported by the transaction manager |

Actual support depends on the `ReactiveTransactionManager` and driver. Do not assume all propagation modes or nested savepoints are supported identically across all R2DBC drivers.

Example:

```java
@Transactional(propagation = Propagation.REQUIRED)
public Mono<Void> createOrder(...) {
    return orderRepository.save(...)
        .flatMap(order -> auditService.writeAudit(order));
}
```

If `auditService.writeAudit` also uses `REQUIRED` and the same transaction manager, it can join the current transaction. If the audit step emits an error that propagates out, the shared transaction can roll back.

`REQUIRES_NEW` must be used intentionally. If the outer transaction rolls back while the independent audit transaction already committed, the audit record remains. This may suit failure audits or retry states, but not when audits must be atomic with primary data.

## 16. Transactions and concurrent Publishers

Independent operations can be combined with `Mono.zip`, but you should not assume an R2DBC connection can safely execute multiple statements concurrently. Many drivers/connections require statements on the same connection to be serialized or have protocol limits.

Example:

```java
@Transactional
public Mono<DashboardData> loadData(Long id) {
    Mono<Customer> customer = customerRepository.findById(id);
    Mono<List<Order>> orders = orderRepository.findByCustomerId(id)
        .collectList();

    return Mono.zip(customer, orders)
        .map(tuple -> new DashboardData(tuple.getT1(), tuple.getT2()));
}
```

This is an example of composition inside a transaction. However, if both queries use the same transaction-bound connection, the driver may serialize them or disallow concurrent execution. When clear ordering is needed, compose sequentially:

```java
@Transactional
public Mono<CustomerDetail> loadDetail(Long id) {
    return customerRepository.findById(id)
        .flatMap(customer -> orderRepository.findByCustomerId(id)
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders)));
}
```

The choice depends on the driver, workload, and consistency requirements. A transaction does not mean every child `Publisher` runs concurrently on the same connection.

## 17. Long-running transactions and resources

Transactions typically hold a connection until commit or rollback. If a transactional publisher includes slow work such as HTTP calls, waiting for users, reading large files, or long CPU processing, the connection may be held for that entire duration.

Example showing why a transaction should not be held across a slow HTTP call unnecessarily:

```java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    return orderRepository.save(toOrder(request))
        .flatMap(order -> paymentClient.authorize(order)
            .thenReturn(order));
}
```

In this example, the transaction can hold the connection while waiting on the payment service. If the payment service is slow, the database pool can become saturated.

Consider splitting the workflow:

1. Save initial order status in a short transaction.
2. Commit the transaction.
3. Call the payment service outside the transaction.
4. Open a new transaction to update the payment result.
5. Use intermediate states, idempotency, and compensating processes if a step fails.

This is a business-level workflow/saga approach, not an ACID transaction across an HTTP service.

## 18. Testing commit and rollback timing

Transaction tests must verify database state after the publisher terminates, not merely verify the values emitted by the publisher.

### 18.1. Testing rollback on error

Service test example:

```java
StepVerifier.create(orderService.createOrder(requestThatFailsAfterOrderInsert()))
    .expectError(OrderLinePersistenceException.class)
    .verify();

StepVerifier.create(orderRepository.count())
    .expectNext(0L)
    .verifyComplete();
```

This example assumes the order was INSERTed before the error occurred in the next step, and both operations shared the same transaction. The subsequent count query verifies that data was rolled back.

### 18.2. Testing commit on complete

```java
StepVerifier.create(orderService.createOrder(validRequest))
    .assertNext(order -> assertNotNull(order.getId()))
    .verifyComplete();

StepVerifier.create(orderRepository.count())
    .expectNext(1L)
    .verifyComplete();
```

Tests must verify the operation was subscribed and completed before re-reading state.

### 18.3. Testing Mono.empty()

If business logic treats an empty result as success, verify that the transaction commits as designed. If missing data must roll back, the test must verify the service turns empty into an exception before the transaction boundary.

### 18.4. Testing cancellation

Cancellation is harder to test than complete/error. You can use `StepVerifier` with subscription control to cancel before the source completes, then verify the transaction rolls back and the connection returns to the pool. Tests should run against a real database/driver or compatible integration environment, as cancellation and cleanup behavior can depend on the driver.

### 18.5. Avoid letting the test itself wrap the transaction under test

Some test frameworks can automatically open a transaction for the test method and roll it back after the test. This can obscure how the service committed or rolled back. When testing service transaction boundaries, design tests to observe state after the service's transaction has ended, rather than letting an outer transaction make results hard to interpret.

## 19. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking a transaction starts when creating a `Mono` | Misunderstanding execution timing and side effects | Remember reactive transactions start when the transactional publisher is subscribed |
| Creating a publisher without subscribing | SQL does not run; transaction does not execute | Return the publisher to the framework or compose into a consumed pipeline |
| Calling `subscribe()` inside a service | Creates an independent flow; transaction does not wait or see errors | Compose publishers with Reactor operators |
| Calling `block()` inside a reactive transaction | Blocks threads and breaks the reactive model | Use `flatMap`, `then`, `zip`, or appropriate operators |
| Returning `Mono.empty()` when rollback is desired | Publisher completes normally so transaction may commit | Convert into an error if it is a business failure |
| Swallowing errors with `onErrorResume` inside the boundary | Transaction may see completion and commit | Place fallback outside the boundary if rollback must happen first |
| Using the wrong transaction manager | R2DBC operations are not managed by the intended manager | Use `ReactiveTransactionManager` and specify bean when multiple exist |
| Calling transactional methods via self-invocation | Proxy does not intercept internal calls | Structure beans or use `TransactionalOperator` |
| Using raw `ConnectionFactory.create()` | May acquire a connection outside the transaction context | Use Spring-aware clients or `ConnectionFactoryUtils` |
| Using different ConnectionFactories in the same workflow | Operations do not share the same transaction | Use the same connection factory or design separate consistency |
| Holding a transaction during long HTTP calls | Holds connections, increasing pool pressure | Separate short transactions from non-database workflows |
| Assuming `Mono.zip` creates a transaction | Composition does not create transactions | Use `@Transactional` or `TransactionalOperator` |
| Assuming all propagation/savepoint modes are supported | Behavior can vary by driver/manager | Verify transaction manager and driver capabilities |
| Returning long-lived `Flux` inside a transaction | Holds transaction/connection for stream duration | Bound the stream or split transactions into batches |

## 20. Checklist for defining transaction boundaries

When designing a reactive use case, answer these questions in order:

1. Which database operations must succeed or roll back together?
2. Do all operations use the same `ConnectionFactory`?
3. Should the boundary be placed on a service method with `@Transactional` or at a pipeline location with `TransactionalOperator`?
4. Is the publisher returned to the caller and subscribed the intended number of times?
5. Is there any eager code running before subscription that needs to move into `defer`?
6. Is a no-data outcome a valid completion or an error requiring rollback?
7. Which errors must reach the boundary, and which have fallbacks outside the boundary?
8. Can downstream cancel or time out midway?
9. Does the transaction hold a connection while waiting on HTTP, file I/O, or long CPU work?
10. Are concurrent operations compatible with the driver and transaction-bound connection?
11. Have commit, rollback, empty, error, and cancellation been tested against the target database?

## 21. Key principles to remember

- Reactive transactions are tied to publisher subscription, not started merely by creating a `Mono` or `Flux`.
- An unsubscribed publisher typically does not run lazy database operations.
- Each subscription may re-execute work and create a separate transaction.
- `Mono.defer` delays creating/executing work until subscription time when needed.
- Normal publisher completion (`onComplete`), including `Mono.empty()`, usually leads to commit.
- Errors crossing a transaction boundary lead to rollback according to transaction rules.
- Cancellation of a transactional publisher before completion is handled per reactive transaction rollback semantics.
- Placement of `onErrorResume`, `take`, timeout, and short-circuit operators can alter the signals received by the transaction boundary.
- Reactive `@Transactional` requires a `ReactiveTransactionManager`, appropriate proxying, and a method returning `Mono`/`Flux`.
- `TransactionalOperator` wraps publishers explicitly and does not require an AOP proxy.
- Do not call `subscribe()` or `block()` inside a transactional service.
- Use the same `ConnectionFactory` and Spring-aware data access so operations join the transaction context.
- Do not assume raw `ConnectionFactory.create()` obtains a transaction-bound connection.
- Reactive transaction context follows the Reactor Context rather than relying on `ThreadLocal`.
- Avoid holding transactions/connections during unnecessary network tasks or long streams.
- Test database state after commit/rollback and verify cancellation/cleanup on the actual driver.

In Spring Data Relational R2DBC, start, commit, and rollback timing is governed by the reactive execution lifecycle. Creating a publisher only registers work; subscription activates the transaction; successful completion allows commit; error or cancellation is handled by the transaction manager according to rollback rules. When boundaries are placed properly, errors reach the transaction manager, and all operations share the same transaction context, the application maintains atomicity while leveraging R2DBC's non-blocking model.
