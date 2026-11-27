# Placing Transaction Boundaries in the Service Layer

## 1. Why Place Transactions in the Service Layer?

In a Spring WebFlux application using Spring Data Relational R2DBC, a business operation often consists of multiple data-access steps. For example, confirming an order may need to:

1. Read the order.
2. Check its current status.
3. Check and update inventory.
4. Update the order status.
5. Write a history record or an outbox event.

If each repository method manages an independent transaction on its own, one step may commit successfully while the next step fails. When that happens, data can end up in an inconsistent state.

A transaction boundary should reflect **a business unit of work that must succeed or fail together**. In layered applications, the service layer usually has visibility over the entire use case and coordinates multiple repositories. It is therefore typically the right place to define the transaction boundary.

For example, when confirming an order, updating the order, deducting inventory, and writing the outbox event may all need to happen within the same database transaction. The service orchestrates those steps and wraps the publisher with the R2DBC transaction manager.

The controller only receives the HTTP request and returns the publisher. Repositories focus on persistence operations. The service decides which steps belong to the same transaction.

Placing transactions in the service layer helps:

- Protect the atomicity of a use case across multiple repositories.
- Avoid premature commits after individual steps.
- Make clear where a transaction begins and ends.
- Keep controllers thin and repositories focused on persistence.
- Test commit/rollback behavior around business rules.
- Limit connection hold duration by wrapping only the operations that require a transaction.

## 2. What Is a Transaction Boundary?

A transaction boundary is the scope of operations processed by the database as a single commit or rollback unit.

Suppose a money transfer must debit a source account and credit a destination account. Both operations must succeed together:

~~~text
HTTP request
     |
     v
TransferController
     |
     v
TransferService  <--- transaction boundary
     |
     +-- read source account
     |
     +-- check balance
     |
     +-- debit source account
     |
     +-- credit destination account
     |
     +-- write transfer history
     |
     v
COMMIT if all succeed
ROLLBACK if an error occurs
~~~

If crediting the destination fails after debiting the source, rolling back the transaction undoes the debit within the same database transaction.

A transaction does not automatically encompass every activity occurring during an HTTP request. It only manages resources enlisted through the corresponding transaction manager.

For instance, an HTTP call to another service, sending an email, or writing a file is not automatically rolled back when an R2DBC transaction rolls back.

## 3. Why Is the Service Layer the Right Place?

### 3.1. Controllers Should Not Decide Business Transactions

The controller is responsible for translating an HTTP request into an application call and converting the result into an HTTP response.

Example:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping("/{id}/confirm")
    public Mono<OrderResponse> confirm(@PathVariable Long id) {
        return orderService.confirm(id)
            .map(OrderResponse::from);
    }
}
~~~

The controller does not need to know how many repositories are called or how transactions are configured. It simply returns the publisher from the service.

Do not call `subscribe()` in the controller to execute the publisher manually. WebFlux must receive the publisher to coordinate subscription, backpressure, cancellation, and response writing.

### 3.2. Repositories Should Not Orchestrate Entire Use Cases

A repository represents data-access operations:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}

public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {
}

public interface OutboxRepository
        extends ReactiveCrudRepository<OutboxEvent, Long> {
}
~~~

A repository does not know the full business meaning of confirming an order. It provides read/write primitives for the service to coordinate.

A repository method may have its own transaction semantics depending on Spring Data configuration, but repository-level transactions do not automatically span an entire multi-repository use case. The service must define the shared scope.

### 3.3. The Service Sees the Complete Business Unit

The service has enough context to decide:

- Which aggregates must be read.
- Which changes must commit together.
- Which business rules must be checked before writing.
- When rollback is required.
- Whether external systems should be called before or after the transaction.
- Whether an outbox or compensation workflow is needed.

Therefore, the service layer is usually the best place to establish a use case's transaction boundary.

## 4. How Do Reactive Transactions Differ from Imperative Transactions?

In imperative applications using JDBC, transactions are typically bound to a thread via `ThreadLocal`. In reactive applications using R2DBC, the transaction context propagates along the subscription's Reactor Context.

This has important implications:

- A reactive pipeline may execute across multiple threads.
- Transactions do not depend on a fixed thread.
- Spring attaches transaction and connection metadata to the Reactor Context.
- R2DBC operations within the same reactive transaction can reuse the connection managed by the transaction manager.
- Do not spawn detached subscriptions or call `block()` to retrieve results.

With Spring WebFlux and R2DBC, use a reactive transaction manager such as `R2dbcTransactionManager`. Imperative JDBC transaction managers do not replace the R2DBC transaction manager.

### 4.1. Publishers Must Be Returned from the Service

Service methods should return `Mono` or `Flux` so the transaction interceptor can manage the entire publisher lifecycle.

Example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> {
            order.setStatus("CONFIRMED");
            return orderRepository.save(order);
        });
}
~~~

A reactive transaction is tied to publisher execution. In the reactive model, actual work occurs when the publisher is subscribed to.

Do not write:

~~~java
@Transactional
public Mono<Void> confirm(Long orderId) {
    orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .subscribe();

    return Mono.empty();
}
~~~

`subscribe()` creates an independent subscription. The method may return `Mono.empty()` and the transaction interceptor may finish before the save in that detached subscription completes. Errors and the transaction context of that subscription are also no longer coordinated as part of the publisher returned by the service.

Return the publisher itself:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> orderRepository.save(order))
        .then();
}
~~~

### 4.2. Never Call block() Inside a Reactive Transaction

Do not turn an R2DBC publisher into synchronous calls inside a service:

~~~java
@Transactional
public Order confirm(Long orderId) {
    Order order = orderRepository.findById(orderId).block();
    order.setStatus("CONFIRMED");
    return orderRepository.save(order).block();
}
~~~

This blocks threads, creates separate subscriptions, and misuses the reactive transaction model. In WebFlux, chain publishers with `flatMap`, `map`, `then`, or appropriate Reactor operators.

### 4.3. Reactor Context Instead of ThreadLocal Assumptions

The transaction context can follow a reactive pipeline even when Reactor operators switch schedulers. Never assume all callbacks execute on the same thread.

If you manually spawn threads, call `subscribe()`, or offload work to an executor that does not integrate with Reactor Context, transaction metadata may fail to propagate as expected.

Keeping operations inside a single pipeline returned from the service allows Spring to manage the transaction context consistently.

## 5. Configuring the R2DBC Transaction Manager

Spring Data R2DBC uses `ConnectionFactory` to obtain connections. The corresponding reactive transaction manager is `R2dbcTransactionManager`.

Example configuration:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean("r2dbcTransactionManager")
    ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

If the application has only one `ConnectionFactory`, Spring Boot may auto-configure certain components depending on version and auto-configuration conditions. Verify the actual transaction manager used by your application.

If there are multiple `ConnectionFactory` instances or multiple transaction managers, specify the manager explicitly at the transaction boundary:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> confirm(Long orderId) {
    // ...
}
~~~

The transaction manager must manage the same `ConnectionFactory` used by the repositories in the use case. If a service opens a transaction on manager A while a repository uses ConnectionFactory B, operations on repository B will not automatically participate in transaction A.

### 5.1. The Transaction Manager Must Match the Data Access Technology

| Access Technology | Corresponding Transaction Manager |
|---|---|
| Spring Data R2DBC | `R2dbcTransactionManager` |
| JDBC / `JdbcTemplate` | `DataSourceTransactionManager` or `JdbcTransactionManager` depending on configuration |
| JPA | `JpaTransactionManager` |
| Multiple data sources | Dedicated manager per source or a custom-designed coordination strategy |

Do not use a JDBC transaction manager simply because the app runs on WebFlux. The transaction manager type must match the database resource used by the publisher.

## 6. Defining Transactions with @Transactional in the Service

### 6.1. Example: Use Case Updating Multiple Repositories

Suppose confirming an order requires:

- Reading the order.
- Reading inventory.
- Checking available quantity.
- Deducting inventory.
- Updating the order.
- Writing an outbox event.

All write operations must commit or roll back together:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;
    private final OutboxRepository outboxRepository;

    public OrderService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository,
            OutboxRepository outboxRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
        this.outboxRepository = outboxRepository;
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<Order> confirm(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order ->
                inventoryRepository.findById(order.getProductId())
                    .switchIfEmpty(Mono.error(
                        new InventoryNotFoundException(order.getProductId())
                    ))
                    .flatMap(inventory -> {
                        if (inventory.getAvailable() < order.getQuantity()) {
                            return Mono.error(
                                new InsufficientInventoryException(orderId)
                            );
                        }

                        inventory.setAvailable(
                            inventory.getAvailable() - order.getQuantity()
                        );

                        order.setStatus("CONFIRMED");

                        return inventoryRepository.save(inventory)
                            .then(orderRepository.save(order));
                    })
            )
            .flatMap(savedOrder ->
                outboxRepository.save(
                    OutboxEvent.orderConfirmed(savedOrder.getId())
                ).thenReturn(savedOrder)
            );
    }
}
~~~

This example assumes all three repositories use the same `ConnectionFactory` and transaction manager. Under that setup, all write operations can participate in the same reactive transaction.

If writing the outbox fails, the error propagates out of the publisher and the transaction can roll back both the inventory and order changes.

This is why the service layer fits: it knows every operation that must succeed together.

### 6.2. Do Not Mechanically Put Transactions on Every Method

Not every service method needs a write transaction:

- A simple read operation may not need an explicit transaction.
- A use case writing a single entity can rely on the repository's transaction semantics if appropriate.
- A use case coordinating multiple database operations needs an explicit transaction boundary.
- A workflow calling external services over long durations usually needs to split transactions.

Decide based on business consistency requirements, not merely the number of methods called.

### 6.3. Class-Level vs. Method-Level @Transactional

`@Transactional` can be placed at the class level:

~~~java
@Service
@Transactional(transactionManager = "r2dbcTransactionManager")
public class OrderService {
    // ...
}
~~~

Eligible methods in the class inherit this default transaction setting. A method can override the configuration at the method level:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    readOnly = true
)
public Flux<Order> findOpenOrders() {
    return orderRepository.findByStatus("OPEN");
}
~~~

Use method-level annotations when use cases have different transaction requirements. Class-level configuration is convenient, but it can accidentally place read methods or long-running operations inside unnecessary transactions.

## 7. Using TransactionalOperator for Explicit Transactions

Besides annotations, Spring provides `TransactionalOperator` to wrap a publisher programmatically in a transaction.

Configuration:

~~~java
@Configuration
public class TransactionalOperatorConfiguration {

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveTransactionManager r2dbcTransactionManager) {

        return TransactionalOperator.create(r2dbcTransactionManager);
    }
}
~~~

Usage in a service:

~~~java
@Service
public class TransferService {

    private final AccountRepository accountRepository;
    private final TransactionalOperator transactionalOperator;

    public TransferService(
            AccountRepository accountRepository,
            TransactionalOperator transactionalOperator) {
        this.accountRepository = accountRepository;
        this.transactionalOperator = transactionalOperator;
    }

    public Mono<Void> transfer(
            Long sourceId,
            Long targetId,
            BigDecimal amount) {

        Mono<Void> work =
            accountRepository.findById(sourceId)
                .switchIfEmpty(Mono.error(
                    new AccountNotFoundException(sourceId)
                ))
                .flatMap(source ->
                    accountRepository.findById(targetId)
                        .switchIfEmpty(Mono.error(
                            new AccountNotFoundException(targetId)
                        ))
                        .flatMap(target -> {
                            if (source.getBalance().compareTo(amount) < 0) {
                                return Mono.error(
                                    new InsufficientBalanceException()
                                );
                            }

                            source.setBalance(
                                source.getBalance().subtract(amount)
                            );
                            target.setBalance(
                                target.getBalance().add(amount)
                            );

                            return accountRepository.save(source)
                                .then(accountRepository.save(target))
                                .then();
                        })
                );

        return transactionalOperator.transactional(work);
    }
}
~~~

`TransactionalOperator` makes it obvious which publisher is wrapped in a transaction. This approach is helpful when:

- Only one branch in a service needs a transaction.
- Transaction boundaries are determined by runtime conditions.
- You want to inject a specific transaction manager via constructor injection.
- You want to avoid proxy-annotation pitfalls in certain code structures.
- You want explicit transaction control inside publisher composition.

### 7.1. Using execute When TransactionStatus Is Needed

`TransactionalOperator` also provides `execute` with a callback receiving `TransactionStatus`:

~~~java
return transactionalOperator.execute(status ->
    performDatabaseWork()
        .onErrorResume(error -> {
            status.setRollbackOnly();
            return Mono.error(error);
        })
).then();
~~~

In this example, the error propagates forward and the transaction rolls back on the error signal. `setRollbackOnly` is useful when logic must explicitly mark rollback, though it should not substitute for designing a clear error flow.

`execute` returns a `Flux` for the callback publisher. If the callback yields only a single result, use `single()`, `singleOrEmpty()`, or an operator matching actual cardinality.

## 8. Choosing Between @Transactional and TransactionalOperator

| Criterion | `@Transactional` | `TransactionalOperator` |
|---|---|---|
| Declaration style | Annotation on service class/method | Wraps publisher in code |
| Boundary | Per proxy-managed method | Per publisher passed to operator |
| Readability | Easy to spot at method signature | Easy to see exact scope within pipeline |
| Runtime conditions | Harder to express across branching paths | Flexible when selecting which publisher to wrap |
| Manager configuration | `transactionManager`/qualifier attribute on annotation | Inject operator built from a specific manager |
| Proxy dependency | Yes | No proxy needed to apply operator |
| Status control | Via transaction rules and exceptions | Can use `execute` and `TransactionStatus` |

An application can use both. However, maintain consistent conventions so readers know where transactions start and which manager is active.

Do not wrap the same work multiple times with different transaction managers without a clear reason. Nested or chained transactions must be designed around specific propagation and resource behavior.

## 9. Transaction Propagation Between Services

Spring defines propagation to decide whether a transactional method joins an existing transaction or starts a new one.

### 9.1. REQUIRED

`REQUIRED` is the default propagation. If a suitable transaction already exists, the method joins it; otherwise, Spring starts a new transaction.

Example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> confirm(Long orderId) {
    return inventoryService.reserve(orderId)
        .then(orderRepository.findById(orderId))
        .flatMap(order -> {
            order.setStatus("CONFIRMED");
            return orderRepository.save(order);
        });
}
~~~

If `inventoryService` also uses the same transaction manager and `REQUIRED` propagation, its operations can join the outer transaction.

This is useful when a use case calls sub-services while requiring a single commit/rollback unit.

### 9.2. REQUIRES_NEW

`REQUIRES_NEW` requests an independent transaction, suspending any existing transaction per the transaction manager's semantics.

Do not use `REQUIRES_NEW` just "to be safe." It can cause a secondary operation to commit even when the outer transaction rolls back. While this may fit certain technical audit or logging cases, you must evaluate consistency requirements and whether the transaction manager supports suspension in a reactive context.

If an audit record must persist even when business logic fails, clarify the intent. An audit record in an independent transaction can record an attempt, yet it could also describe business data that never committed. A transactional outbox is often more suitable when recording an event to process after commit.

### 9.3. NESTED and Savepoints

`NESTED` may rely on savepoints if supported by the transaction manager and driver. Do not assume all R2DBC drivers support every nested transaction or savepoint feature identically.

Before using it, verify driver/database capabilities and write integration tests. If the use case just needs one shared transaction, `REQUIRED` is usually simpler.

### 9.4. Different Transaction Managers Do Not Share a Transaction

Two methods both annotated with `@Transactional` but specifying different managers do not form a single shared transaction. Each manager governs its own resource.

For instance, the outer method uses `ordersTransactionManager` while the inner method uses `auditTransactionManager`. The two databases have separate transactions. If one commits and the other fails, there is no automatic rollback across both.

## 10. Rollback When a Reactive Publisher Emits an Error

In a reactive transaction, errors propagate via the publisher's `onError` signal. The transaction manager observes that signal to decide rollback according to rollback rules.

Example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> confirm(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> {
            order.setStatus("CONFIRMED");

            return orderRepository.save(order)
                .flatMap(saved ->
                    inventoryRepository.reserve(saved.getProductId())
                        .thenReturn(saved)
                );
        });
}
~~~

If `reserve` emits an error and the error propagates out of the publisher, the transaction can roll back the earlier order update.

### 10.1. Errors Must Reach the Transaction Boundary

Do not swallow errors inside a transaction if rollback is intended.

Inappropriate example:

~~~java
@Transactional
public Mono<Order> confirm(Long orderId) {
    return orderRepository.save(createOrder(orderId))
        .onErrorResume(error -> Mono.just(fallbackOrder()));
}
~~~

`onErrorResume` turns the error into a normal result. The transaction manager sees the publisher complete successfully and may commit earlier changes.

If an error needs to be turned into an HTTP response, handle it outside the transaction boundary:

~~~java
public Mono<OrderResponse> confirm(Long orderId) {
    return transactionalConfirm(orderId)
        .map(OrderResponse::from)
        .onErrorResume(
            InsufficientInventoryException.class,
            error -> Mono.error(
                new OrderConflictException(error.getMessage())
            )
        );
}

@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> transactionalConfirm(Long orderId) {
    // Perform all database operations that must be atomic.
    return performConfirmation(orderId);
}
~~~

In this example, the error leaves the transactional method before being mapped to an API error in the calling method. The transaction has a chance to roll back before the outer layer translates the error.

The same principle applies with `TransactionalOperator`: place `onErrorResume` outside the wrapped publisher if the operator must see the original error.

### 10.2. onErrorMap and doOnError

`onErrorMap` transforms the error type while keeping the error signal. `doOnError` performs observational side effects like logging without swallowing the error.

Example:

~~~java
return transactionalOperator.transactional(work)
    .doOnError(error -> log.error("Order transaction failed", error))
    .onErrorMap(
        OptimisticLockingFailureException.class,
        OrderConflictException::new
    );
~~~

The publisher still emits an error after mapping, so the transaction operator observes the error and can roll back.

### 10.3. Rollback Rules and Checked Exceptions

With annotation-based transactions, Spring's default rollback rules focus on `RuntimeException` and `Error`. Checked exceptions do not trigger rollback by default.

If a service emits a wrapped checked exception or must roll back on a checked exception, configure `rollbackFor` appropriately:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    rollbackFor = BusinessCheckedException.class
)
public Mono<Order> process(Long orderId) {
    // ...
}
~~~

In reactive code, exceptions are emitted as error signals. Verify the actual exception types and rollback rules applied by Spring.

### 10.4. A Rejected Business Result Is Not Always a Reactive Error

If a service returns:

~~~java
return Mono.just(ConfirmationResult.rejected("Insufficient stock"));
~~~

the publisher completes normally. The transaction manager cannot automatically know that the business outcome has a rejected status and needs rollback.

If a branch already wrote data and business logic subsequently requires rollback, emit an error or explicitly mark rollback-only as designed. Never return a normal response object and expect the transaction to roll back automatically.

## 11. Transactions and Ordering of Reactive Operations

A transaction can wrap multiple repository operations. Chain them according to their actual dependencies.

### 11.1. Use flatMap and then for Sequential Operations

Example:

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        outboxRepository.save(
            OutboxEvent.orderCreated(saved.getId())
        ).thenReturn(saved)
    );
~~~

The outbox record is written only after saving the order succeeds. If saving the outbox fails and the error propagates out, the transaction can roll back both.

### 11.2. Be Careful with Mono.zip or Mono.when on the Same Transaction Connection

Independent operations should not always run concurrently inside the same reactive transaction.

In an R2DBC transaction, repositories typically share the same connection bound to the Reactor Context by the transaction manager. Many drivers/connections do not support executing multiple statements concurrently on a single connection.

Example requiring caution:

~~~java
return Mono.zip(
    orderRepository.save(order),
    inventoryRepository.save(inventory)
);
~~~

`Mono.zip` subscribes to both sources simultaneously to collect results. If both use the same transaction connection, they may contend on the connection or hit driver limitations.

If operations require the same transaction and concurrent statement support is not guaranteed, serialize them:

~~~java
return inventoryRepository.save(inventory)
    .then(orderRepository.save(order));
~~~

Or use `flatMap` to express dependency ordering.

If parallel execution is needed, explicitly verify that the driver, transaction manager, and connection semantics support it. Never assume reactive automatically means sending multiple concurrent statements over one connection.

### 11.3. Long Flux Streams Can Hold Transactions Open

If a service returns a large `Flux` inside a transaction, the transaction may remain open for as long as the publisher is being consumed.

This can hold connections and transactions longer than expected, especially when HTTP clients read slowly or downstream applies backpressure.

For large lists, consider:

- Pagination.
- Reading in small batches.
- Opening transactions only for parts requiring consistency.
- Avoiding holding transactions while waiting on non-database processing.
- Not loading entire datasets into memory unnecessarily.

Transaction boundaries should have bounded lifetimes tied to a well-defined unit of work.

## 12. Read-Only Transactions and Other Attributes

### 12.1. readOnly

For read-only use cases, you can declare:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    readOnly = true
)
public Flux<Order> findOpenOrders() {
    return orderRepository.findByStatus("OPEN");
}
~~~

`readOnly` is metadata/a hint for the transaction manager and underlying resource. How strictly the database enforces or optimizes based on this hint depends on the driver and database. Do not treat it as a security mechanism blocking all writes.

If the use case performs writes, do not mark it `readOnly`.

### 12.2. isolation

The isolation level governs how visible another transaction's changes are according to database semantics.

Example:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    isolation = Isolation.READ_COMMITTED
)
public Mono<Order> confirm(Long orderId) {
    return performConfirmation(orderId);
}
~~~

Supported isolation levels and exact semantics depend on the database/driver. Choose based on business invariants and concurrency tests. Raising isolation can increase locking, contention, or overhead.

### 12.3. timeout

A timeout can be configured for a transaction:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    timeout = 5
)
public Mono<Order> updateOrder(Long orderId) {
    return performUpdate(orderId);
}
~~~

Transaction timeout does not replace HTTP client timeouts, query timeouts, or external SDK timeouts. It bounds transaction duration per the transaction manager and resource capabilities.

If transactions frequently hit timeouts, inspect queries, lock contention, connection pool health, and scope of work. Do not simply raise the timeout to mask long-running transactions.

### 12.4. noRollbackFor

In some business cases, a specific exception should not trigger rollback. `noRollbackFor` can be used, though with great care:

~~~java
@Transactional(
    transactionManager = "r2dbcTransactionManager",
    noRollbackFor = DuplicateNotificationException.class
)
public Mono<Void> recordNotification(Long orderId) {
    // ...
}
~~~

Use this only when committing despite that exception is valid for business rules. If the exception indicates incomplete data, allowing commit can create inconsistent state.

## 13. Avoid Holding Transactions During External System Calls

An R2DBC transaction cannot roll back an HTTP call, payment, email, or message broker action that does not participate in that transaction.

Do not wrap an entire request in a single transaction when it contains slow calls outside the database:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Order> pay(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order ->
            paymentClient.authorize(order)
                .flatMap(payment -> {
                    order.setStatus("PAID");
                    return orderRepository.save(order);
                })
        );
}
~~~

If `paymentClient` takes 10 seconds, the transaction may hold a connection for that entire time. If the payment succeeds but saving fails, rolling back the database does not refund the payment.

### 13.1. Splitting into Clear Steps

One design approach is:

1. Write a `PENDING` status and outbox event in a short transaction.
2. A worker processes the payment request after commit.
3. The worker updates the outcome in its own transaction.
4. On failure, transition state and run an appropriate compensation flow.

The transactional outbox guarantees the follow-up processing request is persisted alongside the business change. The worker needs idempotency to avoid duplicate payments or processing.

### 13.2. Sagas Across Multiple Systems

If a use case spans multiple steps across multiple systems, consider a saga. Each step has its own local transaction and corresponding compensating action.

A saga is not a single ACID transaction. It is a stateful business workflow with retries, timeouts, and compensations.

## 14. Transaction Boundaries and Multiple Repositories

A service can call multiple repositories inside the same transaction if they share the same transaction manager and `ConnectionFactory`.

Example:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Purchase> createPurchase(Purchase purchase) {
    return customerRepository.findById(purchase.getCustomerId())
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(purchase.getCustomerId())
        ))
        .flatMap(customer ->
            inventoryRepository.findById(purchase.getProductId())
                .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(purchase.getProductId())
                ))
                .flatMap(inventory -> {
                    if (inventory.getAvailable() < purchase.getQuantity()) {
                        return Mono.error(
                            new InsufficientInventoryException()
                        );
                    }

                    inventory.reserve(purchase.getQuantity());

                    return inventoryRepository.save(inventory)
                        .then(purchaseRepository.save(purchase));
                })
        );
}
~~~

All repositories must route to the same database to participate in a single R2DBC transaction. If a repository uses a different `ConnectionFactory`, the current transaction manager does not automatically cover that source.

If a use case must write to two databases, evaluate outbox, saga, or a dedicated coordination mechanism. Never assume being inside the same service method makes multiple databases atomic.

## 15. AOP Proxies and Cases Where @Transactional Is Not Applied

In Spring's proxy-based configuration, `@Transactional` applies only when calls pass through the transaction proxy.

### 15.1. Self-Invocation

Example:

~~~java
@Service
public class OrderService {

    public Mono<Order> process(Long orderId) {
        return confirmInTransaction(orderId);
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<Order> confirmInTransaction(Long orderId) {
        return orderRepository.findById(orderId);
    }
}
~~~

When `process` calls `confirmInTransaction` directly on the same instance, the internal call bypasses the proxy. The `@Transactional` annotation on the inner method may not take effect as expected.

This can be resolved by:

- Moving the transactional use case into a separate service bean and injecting that bean.
- Calling the transactional method through the Spring proxy from outside.
- Using `TransactionalOperator` to wrap the publisher explicitly.

Do not inject a bean into itself just to bypass self-invocation if cleaner service boundaries can be designed.

### 15.2. Creating Services with new

Never instantiate a service using `new` and expect Spring to apply `@Transactional`:

~~~java
OrderService service = new OrderService(...);
~~~

A manually constructed instance is not managed by Spring as a proxied bean. Inject the service bean from `ApplicationContext` or via constructor injection.

### 15.3. Methods Not Returning a Reactive Publisher

R2DBC reactive transactions need to manage a publisher. Service methods return `Mono` or `Flux` so the transaction interceptor can wrap reactive execution.

A method returning `void` or a synchronous value does not automatically become a reactive transaction just because it has `@Transactional`. With imperative JDBC, that is a different transaction model.

### 15.4. Method Visibility and Proxy Strategy

Declare transactional service methods in a way compatible with your application's proxy strategy, typically `public` methods invoked from other beans. CGLIB/JDK proxies have different restrictions regarding `final` classes, `final` methods, and interface methods.

If transactions are not behaving as expected, verify that the bean is Spring-managed, the call passes through the proxy, and the correct reactive transaction manager is selected.

## 16. Transaction Boundaries and Validation

Not all validation needs to run inside a transaction.

Checks can be categorized as:

- Pure input validation: run before the transaction.
- Validation requiring database reads to decide writes: run inside the transaction or pair with constraints/optimistic locking.
- Validation calling external systems: usually run outside the transaction unless strict coupling is required.
- Validation based on concurrently mutable state: protect with transactions, versions, or appropriate constraints.

For example, checking available inventory and then deducting stock must prevent race conditions. Simply reading the count in the service and updating later may be insufficient if another request runs concurrently. Consider `@Version`, conditional `UPDATE` statements, or appropriate locking mechanisms.

Transactions protect groups of operations under isolation semantics, but they do not replace all concurrency rules. Select invariant protections matching business requirements.

## 17. Testing Transactions in the Service Layer

Transaction tests must verify database state after the publisher completes or emits an error. Simply asserting an exception is not enough to prove rollback occurred.

### 17.1. Testing Rollback When a Later Step Fails

Suppose the service updates inventory and then writes the order. If saving the order fails, inventory must be restored.

Example:

~~~java
@Test
void shouldRollbackInventoryWhenOrderSaveFails() {
    StepVerifier.create(orderService.createPurchase(failingPurchase))
        .expectError()
        .verify();

    StepVerifier.create(inventoryRepository.findById(productId))
        .assertNext(inventory ->
            assertThat(inventory.getAvailable()).isEqualTo(10)
        )
        .verifyComplete();
}
~~~

Tests should use a real database integration setup or R2DBC-compatible test environment. Transaction manager and repository configurations must match the application's runtime path.

### 17.2. Do Not Let a Test Transaction Hide Results

If the test method itself is wrapped in a test transaction, data may be rolled back when the test ends. This can make it hard to tell whether the service's own transaction committed or rolled back properly.

Design tests to observe state after the service publisher finishes. Depending on the test framework and setup, you may need to execute verification queries outside the test's transaction or use explicit transaction setup.

### 17.3. Testing Commit on Success

Besides rollback, test the happy path:

- All changes are persisted.
- Outbox records are created.
- Entity versions increment when using optimistic locking.
- No partial data exists when a step fails.

### 17.4. Checking the Transaction Context

Verify that a service is invoked through a Spring bean proxy and uses the right transaction manager. Do not test with a manually instantiated object when verifying annotation-driven transactions.

When using `TransactionalOperator`, test the publisher wrapped by the corresponding operator.

### 17.5. Testing Multiple Operations and Concurrency

Tests should cover scenarios such as:

- First repository succeeds, second repository fails.
- Validation emits an error before writing.
- Two requests update the same entity concurrently.
- Publisher is cancelled or times out.
- An external non-database call fails.
- Errors are translated outside the transaction boundary.

## 18. Common Mistakes

| Mistake or Misconception | Consequence | Fix |
|---|---|---|
| Placing transactions only in the controller | Controller knows too much about persistence and use cases | Place transactions in the service orchestrating business logic |
| Each repository has its own transaction | Steps of one use case can commit independently | Wrap the whole publisher in the service |
| Using a JDBC transaction manager for R2DBC | R2DBC connections do not join that transaction | Use `R2dbcTransactionManager` |
| Transactional method returns a synchronous type | Reactive transaction model is not applied properly | Return `Mono`/`Flux` |
| Calling `subscribe()` inside the service | Creates a subscription detached from the transaction | Return the publisher from the method |
| Calling `block()` in the pipeline | Blocks threads and breaks the reactive flow | Use `flatMap`/`map`/`then` |
| Service calls an internal transactional method | Self-invocation bypasses the proxy | Split beans or use `TransactionalOperator` |
| Swallowing errors with `onErrorResume` inside transaction | Transaction can commit despite a failed step | Let errors cross the boundary and handle outside |
| Returning a normal rejected result expecting rollback | Transaction sees publisher complete normally | Emit an error or mark rollback-only |
| Wrapping HTTP calls in a long transaction | Holds connections and cannot roll back external systems | Split transactions, use outbox/saga |
| Using multiple managers thinking commit is atomic | Each manager runs an independent transaction | Design explicit distributed coordination |
| Using `Mono.zip` for multiple statements on one connection unchecked | Driver may not support concurrent statements | Serialize with `flatMap`/`then`/`concatMap` |
| Returning a large `Flux` inside a transaction | Connection can stay open per consumer speed | Paginate or narrow the transaction |
| Omitting manager name when multiple managers exist | Transaction can be ambiguous or pick the wrong source | Specify `transactionManager` or inject an operator |
| Tests only assert the exception | Does not prove data actually rolled back | Re-query the database after publisher completion |

## 19. Workflow for Placing Transaction Boundaries in the Service Layer

When designing a WebFlux use case with R2DBC, follow this order:

1. Identify all database operations belonging to the same business unit.
2. Identify which changes must commit or roll back together.
3. Move repository coordination into a service method.
4. Confirm repositories use the same `ConnectionFactory` if a single R2DBC transaction is required.
5. Select the appropriate `R2dbcTransactionManager`.
6. Use `@Transactional` on the reactive service method or `TransactionalOperator` around the publisher.
7. Return `Mono`/`Flux` from service and controller; never manually `subscribe` or `block`.
8. Chain dependent operations using `flatMap`, `then`, or `concatMap`.
9. Allow errors requiring rollback to propagate past the transaction boundary.
10. Only translate errors into HTTP responses after the transaction has ended.
11. Avoid holding transactions while waiting on HTTP, email, payments, or non-database blocking I/O unless strictly needed.
12. Use outbox/saga when coordinating external side effects or multiple databases.
13. Verify proxies, self-invocation, and the active transaction manager.
14. Write integration tests asserting both commit and rollback.
15. Monitor transaction duration, connection pool, and lock waits at runtime.

## 20. Self-Check Exercises

### Exercise 1: Choosing the Layer for Transactions

An order confirmation request needs to update the order, inventory, and outbox. Should the transaction be placed in the controller, repository, or service?

Hint: The service, because it orchestrates the entire use case and knows which operations must commit/roll back together.

### Exercise 2: Choosing the Transaction Manager

An application uses Spring Data R2DBC. Which transaction manager should be used?

Hint: `R2dbcTransactionManager` bound to the `ConnectionFactory` used by the repositories.

### Exercise 3: Publishers and Transactions

A service method has `@Transactional`, calls `subscribe()` internally, and returns `Mono.empty()`. What can go wrong?

Hint: The internal subscription detaches from the Spring-managed publisher; the transaction may finish before the work completes.

### Exercise 4: Rollback and onErrorResume

A save operation fails, but the service uses `onErrorResume` to return `Mono.just(fallback)`. Will the transaction definitely roll back?

Hint: No. The error was converted into normal completion before the transaction boundary observed the publisher. Handle errors outside the transaction if rollback is needed.

### Exercise 5: Two Repositories

Two repositories share the same `ConnectionFactory` and are called inside a `@Transactional` service method. Can they participate in the same transaction?

Hint: Yes, if they share the same transaction manager/resource and the publishers are composed within the same reactive transaction context.

### Exercise 6: Two Databases

A use case writes to an orders database and an audit database with two transaction managers. Does one `@Transactional` automatically roll back both?

Hint: No. Each manager governs a separate transaction. An outbox, saga, or dedicated distributed strategy is required.

### Exercise 7: HTTP Calls

A service opens a transaction and waits 10 seconds for a payment gateway. What are the potential impacts?

Hint: The transaction and connection may be held for a long time; a database rollback will not refund an external payment. Split the external call outside the transaction and use idempotency/outbox/saga.

### Exercise 8: Self-Invocation

Method A in a service directly calls method B annotated with `@Transactional` on the same instance. Is B's annotation guaranteed to apply?

Hint: Not in proxy-based transactions when it is a self-invocation. Extract a separate bean or use `TransactionalOperator`.

### Exercise 9: Parallel Operations

Two repositories participate in the same R2DBC transaction and are invoked inside `Mono.zip`. Can you assume the driver always executes them concurrently safely?

Hint: No. The same transaction typically uses a single connection; check driver support or serialize the statements.

### Exercise 10: Testing Rollback

After a service emits an error, is checking `expectError` alone enough to confirm rollback?

Hint: No. Re-query the database to verify that changes prior to the error were undone.

## 21. Key Takeaways

- A transaction boundary should reflect a business unit of work that must succeed or fail together.
- The service layer is usually the right place to coordinate multiple repositories within a use case.
- Controllers receive requests and return publishers; repositories focus on persistence.
- Spring Data R2DBC requires a reactive transaction manager such as `R2dbcTransactionManager`.
- Reactive transaction context propagates via Reactor Context rather than relying on a fixed thread.
- Transactional service methods should return `Mono` or `Flux` and be invoked through a Spring proxy.
- Use `@Transactional` or `TransactionalOperator` to wrap publishers needing atomicity.
- Repositories must use the right `ConnectionFactory`/transaction manager to participate in the same transaction.
- Never call `subscribe()` or `block()` inside a reactive service.
- Errors must reach the transaction boundary to trigger rollback; apply fallbacks outside the transaction.
- `onErrorResume` inside the boundary can turn an error into completion and cause the transaction to commit.
- `REQUIRED` typically joins an existing transaction of the same manager; different managers do not automatically share a transaction.
- Be cautious with concurrent statements on the same R2DBC connection and with long `Flux` streams holding transactions open.
- Never hold transactions while waiting on external systems; transactions cannot roll back HTTP, email, or payment calls.
- Use outbox/saga and idempotency to coordinate external side effects or multiple systems.
- Test both commit and rollback by inspecting database state after the publisher completes.

When placing transaction boundaries in the service layer, wrap exactly the database operations that form a business unit and let the reactive publisher run its full lifecycle through the Spring transaction manager. Controllers do not need to manage transactions, repositories do not need to orchestrate entire use cases, and services can clearly express which steps must commit or roll back together. Short transactions, paired with the right manager and tested against real data state, help WebFlux and R2DBC applications preserve consistency without holding connections longer than necessary.
