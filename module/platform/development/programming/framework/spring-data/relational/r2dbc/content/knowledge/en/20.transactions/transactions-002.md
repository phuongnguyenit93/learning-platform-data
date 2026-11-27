# Configuring TransactionalOperator

In Spring Data R2DBC, reactive transactions can be managed in two ways: declaratively with the `@Transactional` annotation or explicitly with `TransactionalOperator`. The operator is well suited when you want to specify exactly which publisher belongs to a transaction, coordinate multiple repository/`DatabaseClient` operations, or choose a transaction definition per use case.

`TransactionalOperator` does not connect to the database itself and does not replace a driver. It coordinates transactions through a `ReactiveTransactionManager`. For R2DBC, the transaction manager is usually `R2dbcTransactionManager`, configured from the same `ConnectionFactory` that Spring Data repositories and `DatabaseClient` use.

## 1. Components of a reactive transaction

A reactive transaction typically involves these components:

- **ConnectionFactory:** creates or provides R2DBC connections.
- **R2dbcTransactionManager:** begins, commits, and rolls back transactions on a connection.
- **ReactiveTransactionManager:** the interface Spring uses to manage reactive transactions.
- **TransactionalOperator:** wraps a publisher in a transaction boundary.
- **Repository / DatabaseClient / R2dbcEntityTemplate:** executes database statements within the transaction context.

General diagram:

~~~mermaid
flowchart TD
    A[Service method]
    B[TransactionalOperator]
    C[ReactiveTransactionManager]
    D[R2dbcTransactionManager]
    E[ConnectionFactory]
    F[Spring Data Repository / DatabaseClient]
    G[Database]
    A --> B
    B --> C
    C --> D
    D --> E
    A --> F
    F --> E
    E --> G
~~~

The operator opens a transaction boundary around the publisher. The transaction manager manages the connection and transaction state. A repository or `DatabaseClient` participates in the transaction when it uses the same connection infrastructure managed by the transaction manager.

## 2. Configuring ReactiveTransactionManager for R2DBC

For a single `ConnectionFactory`, the standard Spring Data R2DBC transaction manager is `R2dbcTransactionManager`.

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
public class R2dbcTransactionConfiguration {

    @Bean
    public ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

`R2dbcTransactionManager` manages a single R2DBC `ConnectionFactory`. When a transaction starts, it acquires a connection and binds the transaction resource to the Reactor Context so participating Spring operations can use the right connection.

In a Spring Boot application, auto-configuration may already create a transaction manager when an R2DBC `ConnectionFactory` is present. Before declaring a bean manually, inspect the existing project configuration and avoid creating two competing transaction managers for the same database. If Spring Boot already provides an appropriate manager, use that bean directly.

If using a connection pool, ensure the transaction manager and repositories use the same pooled `ConnectionFactory`. Using two different factories can prevent repository operations from participating in the transaction managed by the operator.

## 3. Declaring TransactionalOperator as a bean

Once a `ReactiveTransactionManager` is available, you can create the operator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class TransactionOperatorConfiguration {

    @Bean
    public TransactionalOperator transactionalOperator(
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Spring injects the operator into services via constructor:

~~~java
@Service
public class OrderService {

    private final TransactionalOperator transactionalOperator;

    public OrderService(TransactionalOperator transactionalOperator) {
        this.transactionalOperator = transactionalOperator;
    }
}
~~~

Creating the operator once as a bean usually fits well when the application uses one transaction manager and one default transaction definition. If you have multiple databases or need different transaction policies, you can create corresponding operators with the appropriate manager/definition and name the beans clearly.

## 4. Configuring TransactionalOperator directly

If you only need an operator within a specific configuration or component, you can create it directly:

~~~java
TransactionalOperator operator =
        TransactionalOperator.create(transactionManager);
~~~

Or create an operator with a `TransactionDefinition`:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();

definition.setName("order-write");
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
);
definition.setTimeout(10);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Settings in the example:

- `name`: transaction name to aid diagnostics or logging depending on infrastructure.
- `isolationLevel`: desired isolation level.
- `timeout`: transaction time limit in seconds in `DefaultTransactionDefinition`.

The isolation value must be supported by the database. Transaction timeout is not necessarily the same as statement timeout or HTTP request timeout; each layer has its own mechanism and scope. Check the capabilities of your database, driver, and transaction manager.

## 5. Properties in TransactionDefinition

`TransactionDefinition` describes the policy of a transaction:

| Property | Meaning |
| --- | --- |
| Propagation | How a new transaction participates in or creates a transaction relative to an existing one |
| Isolation | Isolation level between concurrent transactions |
| Timeout | Maximum configured duration for the transaction |
| Read-only | Hint that the transaction is read-only |
| Name | Transaction name for identification/diagnostics |

Example read-only configuration:

~~~java
DefaultTransactionDefinition readDefinition =
        new DefaultTransactionDefinition();
readDefinition.setReadOnly(true);
readDefinition.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
);
readDefinition.setTimeout(5);

TransactionalOperator readOnlyOperator =
        TransactionalOperator.create(
                transactionManager,
                readDefinition
        );
~~~

`readOnly = true` is a hint to the transaction manager and database infrastructure. Whether the database enforces or rejects write statements inside a read-only transaction depends on the driver and database engine; do not use this attribute as a substitute for access control checks.

The default propagation of `DefaultTransactionDefinition` is typically `PROPAGATION_REQUIRED`: join an existing transaction if appropriate, or create a new one if none exists. Other modes such as `REQUIRES_NEW` or `SUPPORTS` should be chosen based on business logic and transaction manager support. Do not pick a propagation mode just to "fix" a transaction bug without understanding the call boundaries.

## 6. Using transactional(Mono) to wrap a reactive operation

The most direct usage is passing a publisher into `transactional(...)`:

~~~java
public Mono<Customer> updateCustomerName(
        Long customerId,
        String newName) {

    Mono<Customer> work = customerRepository.findById(customerId)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(customerId)
            ))
            .map(customer -> new Customer(
                    customer.id(),
                    newName,
                    customer.email()
            ))
            .flatMap(customerRepository::save);

    return transactionalOperator.transactional(work);
}
~~~

The operator starts the transaction when the publisher is subscribed, allows operations in the pipeline to share the same transaction, and commits when the publisher completes normally. If the publisher emits an error, the transaction rolls back according to the operator/transaction manager's rollback policy.

The code does not need to call `beginTransaction()`, `commitTransaction()`, or `rollbackTransaction()` manually. Those steps are the transaction manager's responsibility.

## 7. Using one transaction for multiple repository operations

A use case often requires multiple write commands to succeed together. For example, creating an order, saving order lines, and creating an audit record:

~~~java
public Mono<PurchaseOrder> createOrder(
        PurchaseOrder order,
        List<OrderLine> lines) {

    Mono<PurchaseOrder> work = orderRepository.save(order)
            .flatMap(savedOrder ->
                    orderLineRepository.saveAll(
                            lines.stream()
                                    .map(line -> new OrderLine(
                                            null,
                                            savedOrder.id(),
                                            line.productId(),
                                            line.quantity()
                                    ))
                                    .toList()
                    )
                    .thenReturn(savedOrder)
            )
            .flatMap(savedOrder ->
                    auditRepository.save(new OrderAudit(
                            null,
                            savedOrder.id(),
                            "ORDER_CREATED"
                    ))
                    .thenReturn(savedOrder)
            );

    return transactionalOperator.transactional(work);
}
~~~

Saving the order, order lines, and audit record are in one pipeline wrapped by the same operator. If any step emits an error before the transaction completes, the changes within the transaction can be rolled back together.

This example uses `List.stream()` to illustrate creating order lines. If the input is very large, avoid materializing all data in memory; use publishers and an appropriate batching strategy.

A crucial requirement is that the repositories must share the same transaction manager and the same database connection factory. If one repository is configured with a different factory, its operations may run outside the transaction.

## 8. Using execute when access to transaction status is needed

`TransactionalOperator.execute(...)` lets a callback receive a `ReactiveTransaction`. This is useful when you need to mark rollback-only or inspect/interact with transaction status:

~~~java
public Mono<Customer> createCustomer(Customer customer) {
    return transactionalOperator.execute(status ->
            customerRepository.save(customer)
                    .onErrorResume(error -> {
                        status.setRollbackOnly();
                        return Mono.error(error);
                    })
    ).singleOrEmpty();
}
~~~

`execute` returns `Flux<T>`, so if the callback emits at most one item and the service needs `Mono<T>`, you can convert it via `singleOrEmpty()`. If the callback emits multiple items, keep the result as `Flux<T>`.

Normally there is no need to call `setRollbackOnly()` when the error propagates out of the callback: the operator sees the error signal and rolls back. This method is useful when logic needs to explicitly mark rollback-only or when the application handles an error inside the callback yet still wants the transaction to roll back.

The example below intentionally recovers an error into an empty result while still marking the transaction for rollback:

~~~java
return transactionalOperator.execute(status ->
        customerRepository.save(customer)
                .onErrorResume(error -> {
                    status.setRollbackOnly();
                    log.warn("Customer write failed", error);
                    return Mono.empty();
                })
).then();
~~~

If you do not call `setRollbackOnly()` after swallowing an error inside the callback, the operator may only see normal publisher completion and commit the transaction. Therefore, only recover errors inside a transaction when the desired commit/rollback outcome is explicitly determined.

## 9. A transaction starts when the publisher is subscribed

Reactive publishers are typically lazy. Creating a publisher does not mean the SQL statement has run or the transaction has begun:

~~~java
Mono<Customer> result = transactionalOperator.transactional(
        customerRepository.save(customer)
);
~~~

The transaction begins when a subscriber consumes `result`. In WebFlux, the framework subscribes while handling the request; in tests, `StepVerifier` subscribes when verifying the publisher.

Do not call `subscribe()` inside a service to "start" a transaction:

~~~java
// Do not use this approach in a reactive service.
transactionalOperator.transactional(
        customerRepository.save(customer)
).subscribe();
~~~

Manual subscription creates an execution flow detached from the publisher the caller is tracking. The caller can no longer coordinate completion timing, errors, or cancellation; the transaction may also finish independently of the main processing flow.

Return the publisher from the service and let the framework at the application boundary decide when to subscribe.

## 10. Reactor Context and the transaction connection

Spring's reactive transactions bind resources to the Reactor Context instead of relying on `ThreadLocal` like the traditional synchronous model. Therefore:

- Operations in the same pipeline can participate in the transaction even if they run on different threads.
- `publishOn` or `subscribeOn` do not automatically drop the transaction context when the Reactor pipeline is properly chained.
- Creating an independent subscription with `subscribe()` can detach an operation from the original transaction context.
- Crossing into an imperative API or a callback outside Reactor can lose context if it is not propagated properly.

Flow diagram:

~~~mermaid
sequenceDiagram
    participant Caller
    participant Operator as TransactionalOperator
    participant TM as R2dbcTransactionManager
    participant Repo as Repository / DatabaseClient
    participant DB as Database
    Caller->>Operator: Subscribe publisher
    Operator->>TM: Begin transaction
    TM->>DB: Acquire connection and begin
    TM-->>Operator: Bind connection in Reactor Context
    Operator->>Repo: Execute first query
    Repo->>DB: SQL on transaction connection
    DB-->>Repo: Result
    Operator->>Repo: Execute next query
    Repo->>DB: SQL on same transaction connection
    DB-->>Repo: Result
    Operator->>TM: Commit on successful completion
    TM->>DB: COMMIT
    Operator-->>Caller: Complete
~~~

Repositories and `DatabaseClient` configured via Spring mechanisms can find and use the connection bound in the context. If you acquire a connection directly via driver APIs bypassing Spring's connection management, that operation may not participate in the current transaction.

## 11. Using the same ConnectionFactory for transaction manager and repositories

An R2DBC transaction manager manages one `ConnectionFactory`. For statements in a transaction to use the same connection:

- `R2dbcTransactionManager` must be created from the factory of the database being transacted.
- Repositories and `DatabaseClient` must use the corresponding factory.
- If pooling is used, components must share the same factory wrapped by the pool.
- Do not create a new standalone factory inside a service for individual queries.

An architecturally broken setup is when the transaction manager uses factory A while a `DatabaseClient` is manually built with factory B. The two operations may use two connections and will not commit or roll back together.

With multiple databases, each database typically needs its own factory and transaction manager. One `TransactionalOperator` only coordinates transactions for the manager passed to it. It does not automatically create an atomic distributed transaction across two independent databases.

## 12. Rollback when the publisher emits an error

When a publisher inside a transaction emits an error and that error propagates out of the operator, the transaction rolls back:

~~~java
public Mono<Void> createThenFail(Customer customer) {
    Mono<Void> work = customerRepository.save(customer)
            .then(Mono.error(
                    new IllegalStateException("Simulated failure")
            ));

    return transactionalOperator.transactional(work);
}
~~~

In this example, the save statement may have executed on the database, but the transaction has not committed yet. The subsequent error causes the operator to roll back the transaction, so the new row is not persisted after a successful rollback.

Do not convert an error into a success value before the transaction manager receives the error signal if rollback is the goal. If you need to handle the error and still roll back, use `setRollbackOnly()` in an `execute` callback, or let the error propagate out of the operator and recover outside it:

~~~java
return transactionalOperator.transactional(work)
        .onErrorResume(error -> {
            log.error("Transaction rolled back", error);
            return Mono.empty();
        });
~~~

In the second approach, `onErrorResume` sits outside the operator. The operator has already observed the error and performed the rollback before the outer layer recovers the publisher.

## 13. Rollback-only and handling business errors

Not every error requires rolling back a transaction. Some flows need to record a business status and complete normally; in other cases, an error is handled inside the transaction, yet previous operations must no longer be allowed to commit.

When using `execute`, you can call:

~~~java
status.setRollbackOnly();
~~~

This marks the current transaction to roll back when the callback finishes. Even if the callback completes normally, if the status was marked rollback-only, the transaction manager will not commit the changes as usual.

Distinguish between:

- **Propagating an error outside the operator:** the operator receives the error and rolls back according to rules.
- **Recovering an error inside the callback:** the publisher may complete normally; if rollback is still wanted, it must be marked rollback-only.
- **Marking rollback-only:** instructs the transaction not to commit even though the callback may complete.

Only use rollback-only when business logic genuinely needs to keep the transaction open to complete error-handling logic. Otherwise, letting the error propagate out is usually simpler and easier to understand.

## 14. Cancellation and transactions on Flux

A reactive transaction is held for as long as the publisher is being consumed. With `Mono`, the duration is usually short. With a `Flux` emitting many items, the transaction may stay open until the stream completes.

If a subscriber cancels the subscription—such as an HTTP client disconnecting or a pipeline using `take(1)`—the transaction operator receives a cancellation signal and performs rollback according to its behavior.

Example:

~~~java
Flux<Customer> stream = transactionalOperator.transactional(
        customerRepository.findAll()
);
~~~

If the consumer reads the entire `Flux`, the transaction can complete and commit. If the consumer cancels before the `Flux` completes, the transaction may roll back. Therefore, avoid wrapping a very long or unbounded read stream in a transaction just to hold a transaction context for the entire duration of client consumption.

For large streaming queries, consider:

- Paginating into short read units.
- Not holding transactions longer than consistency requires.
- Avoiding letting client consumption speed dictate connection hold time.
- Clarifying whether cancellation should roll back the entire unit of work.

## 15. Configuring isolation levels

The isolation level governs how much one transaction sees changes from other transactions. Common levels:

| Isolation level | General meaning |
| --- | --- |
| READ_UNCOMMITTED | May allow reading uncommitted data if supported by the database |
| READ_COMMITTED | Reads only committed data |
| REPEATABLE_READ | Guarantees repeated reads of the same rows remain stable per database semantics |
| SERIALIZABLE | High isolation level limiting concurrency anomalies further, though it may reduce concurrency |
| DEFAULT | Uses the database/transaction manager default level |

Example:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_REPEATABLE_READ
);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Not every database implements isolation levels the same way. Some database engines map or promote isolation levels in their own way. Check the database documentation and measure impacts on locks, contention, and performance before applying them.

Isolation levels do not replace constraints. For example, a unique constraint remains the way to guarantee that no two rows share a unique key across concurrent transactions.

## 16. Timeout, read-only, and propagation

You can create a specialized operator for a group of use cases:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setName("report-query");
definition.setReadOnly(true);
definition.setTimeout(5);
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED
);

TransactionalOperator reportOperator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Some notes:

- Transaction timeout is a transaction manager limit; it does not necessarily cancel every SQL query at the exact same moment.
- Read-only can be a hint, and enforcement depends on the database/driver.
- Propagation determines whether a transaction joins or creates a new one. Choosing `REQUIRES_NEW` can create an independent boundary when supported by the manager, but it alters commit/rollback semantics.
- The transaction definition must align with business requirements and database capabilities.

Do not create excessive operators that differ only by a minor property unless needed. Name beans clearly and configure them explicitly so services do not accidentally pick the wrong policy.

## 17. TransactionalOperator compared to @Transactional

Both approaches can use the same `ReactiveTransactionManager`, but their expression differs:

| Criterion | TransactionalOperator | @Transactional |
| --- | --- | --- |
| Usage | Wraps a publisher in code | Annotates a method/class |
| Scope | The publisher passed to the operator | The method managed by proxy/AOP |
| Rollback-only control | Can use `execute` callback and transaction status | Typically uses exceptions or `TransactionAspectSupport` where appropriate |
| Dynamic transaction definition | Can create operators with specific definitions | Can configure annotation attributes |
| Best suited for | Transaction boundaries expressed inside a pipeline | Stable per-method transaction rules |

Annotation example:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Operator example:

~~~java
public Mono<Order> createOrder(Order order) {
    return transactionalOperator.transactional(
            orderRepository.save(order)
    );
}
~~~

Do not wrap the same publisher with both `@Transactional` and `TransactionalOperator` without a clear intent. Nested transactions may join the existing transaction under default propagation or create a new boundary if configured; unclear combinations make commit/rollback harder to reason about.

The programmatic operator does not require enabling transaction annotation proxies. If using `@Transactional`, ensure declarative transaction management is enabled and calls pass through a Spring proxy.

## 18. Transactions do not span HTTP calls or message brokers

An R2DBC transaction manager manages transactions for a single database resource. It does not automatically make HTTP calls, sending emails, or publishing messages to a broker an atomic part of the database transaction.

Example showing why a transaction should not remain open during remote service calls:

~~~java
return transactionalOperator.transactional(
        orderRepository.save(order)
                .flatMap(savedOrder ->
                        paymentClient.charge(savedOrder)
                                .thenReturn(savedOrder)
                )
);
~~~

This code holds the database transaction open while waiting on a network call. If the payment service is slow, the database connection and transaction can be held for a long time. If payment succeeds while the database transaction rolls back, the two systems can diverge in state.

For business logic that needs to coordinate a database and messaging, you can use a transactional outbox: store business data and an outbox event in the same database transaction, and have a separate process read the outbox and send messages. For multi-service workflows, consider sagas and compensating actions as needed.

## 19. Testing commit and rollback with StepVerifier

Integration tests need to verify both the publisher's outcome and the data state after the transaction.

Example testing rollback when the pipeline emits an error:

~~~java
@SpringBootTest
class CustomerTransactionTest {

    @Autowired
    CustomerService customerService;

    @Autowired
    CustomerRepository customerRepository;

    @Test
    void shouldRollbackWhenWorkFails() {
        Customer customer =
                new Customer(null, "Test", "test@example.com");

        StepVerifier.create(customerService.createThenFail(customer))
                .expectError(IllegalStateException.class)
                .verify();

        StepVerifier.create(
                customerRepository.findByEmail("test@example.com")
        )
                .verifyComplete();
    }
}
~~~

The test assumes the `createThenFail` service saves the customer and then emits an error within the same operator. After rollback, querying outside the transaction confirms no row remains.

When writing integration tests:

- Use a database and driver matching the deployment environment.
- Do not only check the exception; re-query the data to confirm rollback.
- Ensure verification queries run after the test transaction has finished.
- Test successful commits and multiple operations within the same transaction.
- Test cancellation if the use case has long publishers and cancellation behavior matters.

Mocking repositories cannot confirm that the transaction manager actually rolls back the database connection.

## 20. Common configuration mistakes

1. **Missing ReactiveTransactionManager.** The operator cannot begin a transaction without an appropriate manager.
2. **Transaction manager uses a different ConnectionFactory than repositories.** Operations may not participate in the same transaction.
3. **Creating an operator without using it to wrap the publisher.** Simply injecting or instantiating the operator does not start a transaction.
4. **Calling subscribe() manually inside a service.** The subscription detaches from the flow managed by the caller.
5. **Calling block() mid-pipeline.** Loses reactive benefits and can break context coordination.
6. **Swallowing errors inside an execute callback.** The operator may see normal completion; mark rollback-only if rollback is still wanted.
7. **Assuming every error automatically rolls back even after recovery.** The position of `onErrorResume` relative to the operator determines whether the operator observes the error.
8. **Holding a transaction open across a long Flux.** Cancellation can roll back, and the connection is held throughout consumption.
9. **Using readOnly as a security mechanism.** It does not replace database permissions or authorization.
10. **Configuring timeouts uncoordinated with HTTP/SQL timeouts.** One layer may expire before another.
11. **Expecting a transaction to span two independent databases.** One R2DBC transaction manager only manages the resource it is configured with.
12. **Mixing annotations and operators unintentionally.** Can produce unpredictable nested transactions.

## Configuration and usage workflow

1. Identify the `ConnectionFactory` used by Spring Data repositories and `DatabaseClient`.
2. Ensure an appropriate `ReactiveTransactionManager` exists, typically `R2dbcTransactionManager`.
3. Create a `TransactionalOperator` bean with `TransactionalOperator.create(transactionManager)`.
4. Inject the operator into services that require explicit transaction management.
5. Chain all database operations into a single publisher.
6. Wrap the publisher with `transactional(...)`, or use `execute(...)` when access to transaction status is needed.
7. Return the publisher to the caller; do not self-subscribe or block.
8. Verify commit, rollback, errors, and cancellation with integration tests.

`TransactionalOperator` provides a way to manage reactive transactions at publisher boundaries. It uses `ReactiveTransactionManager` to manage connections, commits, and rollbacks; for R2DBC, the transaction manager must share the same `ConnectionFactory` as repositories and `DatabaseClient`. When configured properly and all operations reside in the same pipeline, the application can coordinate multiple database statements as a single transactional unit while preserving the reactive model and handling errors/cancellation according to transaction rules.
