# Declaring @Transactional on Methods Returning a Publisher

## 1. Reactive transactions in Spring Data R2DBC

A business operation often consists of multiple database operations that must succeed or fail together. For example, creating an order might require inserting an `Order`, inserting `OrderLine` records, and updating inventory counts. If the final step fails, the application usually wants to roll back earlier changes so the database does not persist an incomplete state.

In Spring Data R2DBC, database operations return reactive types such as `Mono` and `Flux`. Consequently, transactions must also be managed under the reactive model. Spring provides the **@Transactional** annotation to declare transaction boundaries on methods that return a reactive publisher.

Example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final OrderLineRepository orderLineRepository;

    public OrderService(
            OrderRepository orderRepository,
            OrderLineRepository orderLineRepository) {
        this.orderRepository = orderRepository;
        this.orderLineRepository = orderLineRepository;
    }

    @Transactional
    public Mono<Order> createOrder(CreateOrderCommand command) {
        Order order = new Order(
                null,
                command.customerId(),
                "NEW"
        );

        return orderRepository.save(order)
                .flatMap(savedOrder -> {
                    List<OrderLine> lines = command.lines().stream()
                            .map(line -> new OrderLine(
                                    null,
                                    savedOrder.id(),
                                    line.sku(),
                                    line.quantity()
                            ))
                            .toList();

                    return orderLineRepository.saveAll(lines)
                            .thenReturn(savedOrder);
                });
    }
}
~~~

Spring manages the transaction for the publisher returned by the method. When the reactive chain completes successfully, the transaction is committed; when the chain terminates with an error, the transaction is rolled back according to the rollback rules. Repository operations must participate in the same transaction manager and the same `ConnectionFactory`.

The key point is that **the returned publisher itself is part of the transaction boundary**. Calling a repository to create a publisher does not mean the SQL statement has already executed at the time the method was invoked. Reactive publishers typically execute upon subscription.

## 2. Why is ReactiveTransactionManager needed?

Spring has two main transaction manager models:

- **PlatformTransactionManager:** manages imperative transactions, typically tied to a thread-bound transaction context.
- **ReactiveTransactionManager:** manages reactive transactions, propagating the transaction context via the Reactor Context.

With Spring Data R2DBC, the commonly used transaction manager is **R2dbcTransactionManager** from Spring Framework:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
class TransactionConfiguration {

    @Bean
    ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

`R2dbcTransactionManager` manages an R2DBC `ConnectionFactory`. It acquires a connection, starts a transaction, places the managed connection into the reactive context, and completes commit/rollback according to the publisher's lifecycle.

In a Spring Boot application, auto-configuration can create a transaction manager when appropriate conditions are met. If the application has multiple `ConnectionFactory` instances or configures persistence infrastructure manually, declare and wire the transaction manager explicitly.

Do not use JDBC/JPA transaction managers for R2DBC operations. A `JpaTransactionManager` or `DataSourceTransactionManager` does not manage an R2DBC `ConnectionFactory`.

## 3. Enabling transaction annotations

For Spring to process transaction annotations, the application needs transaction management infrastructure. In a Spring Boot application with the appropriate starter, transaction auto-configuration is usually set up when a transaction manager is present. In plain Spring configuration, enable it with `@EnableTransactionManagement`:

~~~java
@Configuration
@EnableTransactionManagement
class TransactionConfiguration {
}
~~~

The `@Transactional` annotation belongs to the package:

~~~java
import org.springframework.transaction.annotation.Transactional;
~~~

Enabling annotation configuration sets up proxy/interceptor infrastructure to intercept method calls and apply transaction policies. In Spring Boot, avoid adding duplicate configuration if auto-configuration has already enabled the required functionality.

Besides having the annotation, the application must also have an appropriate `ReactiveTransactionManager`. Without a reactive manager, or if the method is not recognized as having a reactive return type, Spring may pick an incompatible transaction manager or fail to create the transaction as expected.

## 4. Returning a Publisher is a critical requirement

Spring recognizes reactive methods based on return types supported by the reactive adapter infrastructure, typically:

- `Mono<T>`
- `Flux<T>`
- `Publisher<T>`
- Certain other reactive types supported by corresponding adapters.

Example:

~~~java
@Transactional
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    Customer customer = new Customer(
            null,
            command.name(),
            command.email()
    );

    return customerRepository.save(customer);
}
~~~

The method returns `Mono<Customer>`, so Spring can apply reactive transaction management to that publisher.

For an operation that does not need to emit data yet must complete within a transaction, you can return `Mono<Void>`:

~~~java
@Transactional
public Mono<Void> archiveCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .flatMap(customer -> {
                Customer archived = customer.withStatus("ARCHIVED");
                return customerRepository.save(archived);
            })
            .then();
}
~~~

Here, `then()` converts the final outcome into a completion signal. The publisher remains inside the transaction boundary.

### 4.1. Void or synchronous return methods are not reactive transaction boundaries

The following example cannot manage the reactive lifecycle of a publisher because the method returns `void`:

~~~java
@Transactional
public void createCustomer(Customer customer) {
    customerRepository.save(customer);
}
~~~

The `save` call only creates a publisher, and that publisher is discarded. No subscriber consumes it, so the operation may never run. The annotation does not automatically subscribe to an ignored publisher.

Similarly, a method returning a synchronous object:

~~~java
@Transactional
public Customer createCustomer(Customer customer) {
    customerRepository.save(customer).subscribe();
    return customer;
}
~~~

also fails to establish a proper reactive boundary. The self-created subscription runs detached from the method's return value; the transaction interceptor cannot coordinate the lifecycle of that detached operation.

With R2DBC, return `Mono`, `Flux`, or an appropriate `Publisher` from transactional methods and compose all operations within that publisher.

## 5. Transactions begin when the publisher is subscribed

Reactive execution is lazy. When calling:

~~~java
Mono<Order> result = orderService.createOrder(command);
~~~

the `result` variable is only a description of work. You cannot conclude that the database has inserted anything or that a transaction has opened yet.

In the reactive proxy transaction model, Spring wraps the returned publisher. When a subscriber consumes the publisher, the transaction manager starts the transaction and puts the transaction context into the Reactor Context. When the publisher terminates, Spring commits or rolls back.

~~~text
Caller invokes method through Spring proxy
                 |
                 v
       Method returns Publisher
                 |
                 v
       Subscriber subscribe()
                 |
                 v
       Reactive transaction begins
                 |
                 v
       Publisher executes operations
                 |
          +------+------+
          |             |
          v             v
       Complete       Error / cancel
          |             |
          v             v
        Commit        Rollback
~~~

This has a practical consequence: do not call a transactional method and discard the publisher. If nobody subscribes, no database pipeline executes and the reactive transaction does not run as the application expects.

In WebFlux, controllers can return the publisher to the framework so the framework subscribes. In tests, use `StepVerifier`. Within another service pipeline, chain the publisher with `flatMap`, `then`, or another suitable operator.

## 6. Combining multiple operations in the same transaction

Example of creating an order with a root entity and order lines:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    Order order = new Order(
            null,
            command.customerId(),
            "NEW"
    );

    return orderRepository.save(order)
            .flatMap(savedOrder -> {
                Flux<OrderLine> lines = Flux.fromIterable(command.lines())
                        .map(line -> new OrderLine(
                                null,
                                savedOrder.id(),
                                line.sku(),
                                line.quantity()
                        ));

                return orderLineRepository.saveAll(lines)
                        .thenReturn(savedOrder);
            });
}
~~~

Execution sequence:

1. Save `Order` and receive the database-generated ID.
2. Use that ID to construct `OrderLine` instances.
3. Save the `OrderLine` records.
4. Once all publishers finish, emit the saved `Order`.
5. The transaction interceptor commits when the entire publisher completes successfully.

If saving an order line fails and the error propagates out of the transactional publisher, the transaction rolls back earlier operations in the same transaction.

Under Spring Data Relational's aggregate model, design saving the aggregate root and its components according to the appropriate mapping. The example above demonstrates transaction sequencing; how collections are persisted in practice depends on your entity mappings and repositories.

## 7. Using flatMap, then, and map properly inside transactions

Reactor operators determine which publishers belong to the transaction-managed chain.

### 7.1. flatMap when the next operation returns a Publisher

~~~java
@Transactional
public Mono<OrderReceipt> placeOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    paymentAttemptRepository.save(
                            toPaymentAttempt(order.id(), command)
                    ).map(attempt ->
                            new OrderReceipt(order.id(), attempt.id())
                    )
            );
}
~~~

Saving the payment attempt is chained onto the order-saving publisher. Since the final publisher is returned, both can share the same transaction when using the proper infrastructure.

### 7.2. then when you only need to wait for completion

~~~java
@Transactional
public Mono<Void> deleteCustomerData(Long customerId) {
    return addressRepository.deleteByCustomerId(customerId)
            .then(orderNoteRepository.deleteByCustomerId(customerId))
            .then(customerRepository.deleteById(customerId));
}
~~~

`then` ignores the preceding publisher's value and only runs the next publisher after the preceding one completes. If any operation emits an error, the error propagates and the transaction can roll back.

### 7.3. map when only transforming data synchronously

~~~java
@Transactional
public Mono<OrderResponse> create(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .map(saved -> new OrderResponse(
                    saved.id(),
                    saved.status()
            ));
}
~~~

`map` only transforms the emitted object; do not use it to invoke another reactive operation. Returning a `Mono` inside `map` produces a nested `Mono`; use `flatMap` in that case.

## 8. Do not self-subscribe or block inside transactional methods

This mistake easily breaks transaction boundaries.

### 8.1. Do not subscribe manually

Avoid:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    orderRepository.save(toOrder(command)).subscribe();

    return Mono.just(new Order(null, command.customerId(), "NEW"));
}
~~~

The subscription created by `subscribe()` is an independent execution flow. The transaction interceptor only manages the publisher returned by the method; a separately subscribed operation may run outside the transaction, will not roll back with other steps, and its errors will not reach the caller.

Correct approach:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command));
}
~~~

### 8.2. Do not block to obtain a result

Avoid:

~~~java
@Transactional
public Order createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command)).block();
}
~~~

`block()` blocks the thread waiting for the result and breaks reactive composition. In WebFlux, it can block the event loop and cause throughput degradation or runtime errors.

Return the publisher to the caller. If one step needs the result of a previous step, use `flatMap` to express the dependency.

### 8.3. Do not create a publisher and ignore it

Avoid:

~~~java
@Transactional
public Mono<Void> createOrder(CreateOrderCommand command) {
    orderRepository.save(toOrder(command));
    return Mono.empty();
}
~~~

The publisher returned by `save` is not chained into the return value and is therefore never consumed. Return it directly or compose it:

~~~java
@Transactional
public Mono<Void> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command)).then();
}
~~~

## 9. Reactor Context and thread switching

Imperative transactions typically bind state to a thread. Reactive transactions do not rely on the assumption that every operation runs on the same thread. Spring stores the transaction context in the **Reactor Context**, and standard Reactor operators propagate context along the subscription.

Therefore, using `publishOn` or `subscribeOn` in a pipeline does not automatically drop the transaction just because a callback runs on a different thread:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .publishOn(Schedulers.parallel())
            .flatMap(saved ->
                    orderLineRepository.saveAll(toLines(saved.id(), command))
                            .thenReturn(saved)
            );
}
~~~

Even so, do not move blocking work into a reactive transaction. Thread switching does not turn JDBC calls or blocking file/network I/O into reactive operations. When database access is needed, use R2DBC clients/repositories that participate in the transaction context.

Do not store transaction context in self-managed `ThreadLocal` variables or assume a specific thread will hold the connection. Let Spring and Reactor manage the context.

## 10. Operations must share the same transaction-aware infrastructure

A reactive transaction only manages operations that participate in the proper transaction context and `ConnectionFactory`.

Spring Data R2DBC APIs such as:

- `ReactiveCrudRepository`.
- `R2dbcEntityTemplate`.
- `DatabaseClient` configured with the same `ConnectionFactory`.

can participate in transactions managed by `R2dbcTransactionManager`.

If code acquires a connection directly from `ConnectionFactory.create()` and executes statements manually, it may not use the connection bound to the transaction context. When transactional connection access is needed, use Spring mechanisms such as `ConnectionFactoryUtils` or APIs designed to join the active context.

For example, a `DatabaseClient` built from the corresponding `ConnectionFactory` typically integrates with Spring's connection management:

~~~java
@Bean
DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
    return DatabaseClient.create(connectionFactory);
}
~~~

What matters is that `DatabaseClient`, template, and transaction manager are configured with the exact same `ConnectionFactory`. If the template uses factory A while the transaction manager manages factory B, template operations do not participate in manager B's transactions.

## 11. Rollback when the Publisher emits an error

By default, Spring rolls back a transaction when a transactional method terminates with an unchecked exception (`RuntimeException`) or `Error`. Checked exceptions do not trigger rollback by default unless a rollback rule is configured.

Example:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    validateAndSaveLines(order, command)
                            .thenReturn(order)
            );
}
~~~

If `validateAndSaveLines` emits an `IllegalStateException`, the error exits the publisher and the transaction is rolled back.

You can declare rollback rules:

~~~java
@Transactional(rollbackFor = BusinessRuleException.class)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return performCreate(command);
}
~~~

Or exclude a specific exception type:

~~~java
@Transactional(noRollbackFor = DuplicateNotificationException.class)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return performCreate(command);
}
~~~

Only configure `noRollbackFor` when business logic genuinely wants to commit despite that exception occurring. Do not use this rule to mask database errors or data integrity failures.

### 11.1. Errors must cross the transaction boundary

If code catches an error and turns it into a successful value inside the transactional publisher, the transaction manager may only observe normal completion and commit.

Example:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order -> saveLines(order, command))
            .onErrorResume(error -> Mono.empty());
}
~~~

Here the error from `saveLines` is converted into an empty completion. Without marking rollback-only or letting the error escape the transactional publisher, the transaction may commit earlier operations.

If you need to turn an error into a business response, handle it after the transactional publisher has rolled back, or use a mechanism to mark the transaction rollback-only appropriate to the transaction API. The simplest and most predictable design is to let the error cross the boundary and transform it in the caller layer.

Example:

~~~java
public Mono<OrderResponse> create(CreateOrderCommand command) {
    return transactionalOrderWriter.createOrder(command)
            .map(OrderResponse::from)
            .onErrorMap(
                    BusinessRuleException.class,
                    OrderRejectedException::new
            );
}
~~~

In this example, the writer method acts as a separate transaction boundary. The caller can map the error after the transaction interceptor has observed the error and rolled back.

## 12. Rollback when a subscriber cancels the subscription

Reactive Streams allows subscribers to cancel a subscription—for instance, an HTTP client closing the connection or the caller no longer needing the result. For reactive transactions, cancellation is treated as an unsuccessful termination for an open transaction; Spring's reactive transaction manager performs rollback where applicable.

This differs from a publisher completing normally. Do not treat a client stopping to wait as proof that the database committed.

Also note that cancellation cannot reverse an already-committed transaction. If the transaction already finished before cancellation was processed, rollback no longer applies. Hence, write APIs need status lookup or idempotency mechanisms when clients cannot tell the outcome due to timeouts/disconnects.

## 13. Scope of @Transactional at class and method levels

The annotation can be placed at the class level:

~~~java
@Service
@Transactional
public class CustomerService {

    public Mono<Customer> create(CreateCustomerCommand command) {
        return customerRepository.save(toCustomer(command));
    }

    public Mono<Customer> find(Long id) {
        return customerRepository.findById(id);
    }
}
~~~

A class-level annotation provides default transaction metadata for eligible methods of the class. It can be overridden at the method level:

~~~java
@Transactional(readOnly = true)
public Mono<Customer> find(Long id) {
    return customerRepository.findById(id);
}

@Transactional
public Mono<Customer> create(CreateCustomerCommand command) {
    return customerRepository.save(toCustomer(command));
}
~~~

Method-level metadata takes precedence over class-level metadata when resolving transaction attributes.

For read-heavy applications, query methods can be marked `readOnly`:

~~~java
@Transactional(readOnly = true)
public Flux<Customer> findActive() {
    return customerRepository.findByStatus("ACTIVE");
}
~~~

`readOnly = true` is a transaction hint. Whether the database/driver enforces or optimizes based on this hint depends on the transaction manager and database engine. Do not treat it as a security mechanism that blocks all writes; proper authorization, database permissions, and query design remain necessary.

## 14. Propagation and nested transactions

`@Transactional` supports propagation to determine behavior when a method is invoked while a transaction already exists.

Common values:

| Propagation | General meaning |
|---|---|
| REQUIRED | Join the existing transaction or create a new one |
| REQUIRES_NEW | Suspend the existing transaction and create an independent transaction if supported by the transaction manager |
| SUPPORTS | Join a transaction if one exists; otherwise run without a transaction |
| MANDATORY | Require an existing current transaction |
| NOT_SUPPORTED | Suspend the current transaction and run without a transaction |
| NEVER | Disallow an existing current transaction |
| NESTED | Request a nested transaction/savepoint if supported by the transaction manager |

Example:

~~~java
@Transactional(propagation = Propagation.REQUIRED)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command));
}
~~~

`REQUIRED` is the default. If another service calls this method within the same reactive transaction context and the same transaction manager, the operation can join the existing transaction.

Do not assume every propagation mode is supported identically across all R2DBC drivers or transaction managers. In particular, `NESTED` depends on savepoint capability and transaction manager/driver support. Verify against your actual database before using it.

## 15. Isolation, timeout, and readOnly

You can specify transaction attributes:

~~~java
@Transactional(
        isolation = Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = true
)
public Flux<OrderSummary> findRecentOrders() {
    return orderRepository.findRecentSummaries();
}
~~~

- **isolation:** requests a transaction isolation level, such as `READ_COMMITTED` or `REPEATABLE_READ`.
- **timeout:** limits transaction duration as supported by the transaction manager.
- **readOnly:** hints a read-only transaction.
- **propagation:** specifies how to join or create a transaction.
- **rollbackFor/noRollbackFor:** defines exception types that trigger or do not trigger rollback.

These attributes do not guarantee every database supports every value identically. Actual isolation depends on the database engine, driver, and transaction manager. Transaction timeout also does not replace query timeout, connection acquisition timeout, or HTTP deadlines.

Do not increase transaction timeout to mask a slow query without understanding the root cause. Measure the query plan, pool wait times, and execution times separately.

## 16. Multiple transaction managers and multiple ConnectionFactories

An application can connect to multiple databases. Each `R2dbcTransactionManager` manages one `ConnectionFactory`. A transaction on database A does not automatically span operations on database B.

You can name transaction manager beans:

~~~java
@Bean("customerTransactionManager")
ReactiveTransactionManager customerTransactionManager(
        @Qualifier("customerConnectionFactory")
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}

@Bean("orderTransactionManager")
ReactiveTransactionManager orderTransactionManager(
        @Qualifier("orderConnectionFactory")
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

Then specify the manager on the method:

~~~java
@Transactional(transactionManager = "orderTransactionManager")
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command));
}
~~~

The repository/template in this method must use the corresponding order `ConnectionFactory`. If a method calls both the customer database and the order database, a single local transaction manager cannot atomically commit both.

To coordinate changes across multiple databases/services, architectures like saga, outbox, or compensating workflows are typically required. Do not assume a single `@Transactional` annotation provides a distributed transaction.

## 17. Self-invocation and proxy limitations

Under default transaction annotation configuration, Spring typically uses a proxy to intercept calls from external beans. Consequently, a method calling another transactional method on the same instance can bypass the proxy.

A misleading example:

~~~java
@Service
public class OrderService {

    public Mono<Order> submit(CreateOrderCommand command) {
        return this.createInTransaction(command);
    }

    @Transactional
    public Mono<Order> createInTransaction(CreateOrderCommand command) {
        return orderRepository.save(toOrder(command));
    }
}
~~~

Calling `this.createInTransaction(...)` is self-invocation and bypasses the Spring proxy. The annotation on the called method may not be applied.

A clearer approach is placing the transaction boundary in a separate bean:

~~~java
@Service
public class OrderWriter {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Mono<Order> create(CreateOrderCommand command) {
        return repository.save(toOrder(command));
    }
}
~~~

~~~java
@Service
public class OrderFacade {

    private final OrderWriter writer;

    public OrderFacade(OrderWriter writer) {
        this.writer = writer;
    }

    public Mono<OrderResponse> submit(CreateOrderCommand command) {
        return writer.create(command).map(OrderResponse::from);
    }
}
~~~

Calling through a bean proxy ensures the interceptor has an opportunity to apply transaction metadata. With proxy-based transaction management, also pay attention to method visibility and how beans are called; `public` methods invoked from another bean are the most predictable choice.

## 18. Transactions and concurrency inside reactive pipelines

Reactive code allows combining multiple publishers. However, running multiple database operations concurrently within the same transaction requires careful thought.

Example:

~~~java
Mono.zip(
        customerRepository.findById(customerId),
        inventoryRepository.findBySku(sku)
)
~~~

If both repositories use the same `ConnectionFactory` and transaction context, the operations may share the connection bound to the transaction. Not every R2DBC driver/connection supports multiple concurrent statements on the same connection. Using `zip` or `flatMap` with concurrency can cause errors or unintended behavior depending on the driver.

For dependent operations or ones needing sequential execution on the same transaction connection, chain `flatMap`:

~~~java
return customerRepository.findById(customerId)
        .flatMap(customer ->
                inventoryRepository.findBySku(sku)
                        .map(inventory -> new OrderDraft(customer, inventory))
        );
~~~

If you genuinely want parallel execution, confirm that the driver and transaction manager connection provisioning support that model. Do not assume reactive concurrency means a single transaction can use multiple independent connections while remaining atomic.

Long transactions also hold connections and may hold locks or snapshots longer. Only include database operations that require atomicity inside a transaction; avoid HTTP calls, sending emails, or waiting on user input while a transaction is open.

## 19. Combining DatabaseClient and R2dbcEntityTemplate in a transaction

Both APIs can participate in the same transaction if they use the same `ConnectionFactory` and transaction-aware infrastructure.

Example updating an entity with the template and recording an audit entry with `DatabaseClient`:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    return template.selectOne(
                Query.query(Criteria.where("id").is(id)),
                Customer.class
            )
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .flatMap(customer ->
                    template.update(Customer.class)
                            .matching(Query.query(Criteria.where("id").is(id)))
                            .apply(Update.update("status", newStatus))
                            .flatMap(rows -> {
                                if (rows != 1) {
                                    return Mono.error(
                                            new IllegalStateException(
                                                    "Expected one updated row"
                                            )
                                    );
                                }

                                return databaseClient.sql("""
                                        INSERT INTO customer_audit
                                            (customer_id, action)
                                        VALUES (:id, :action)
                                        """)
                                    .bind("id", id)
                                    .bind("action", "STATUS_CHANGED")
                                    .fetch()
                                    .rowsUpdated()
                                    .thenReturn(new Customer(
                                            customer.id(),
                                            customer.name(),
                                            customer.email(),
                                            newStatus
                                    ));
                            })
            );
}
~~~

The template performs operations using entity metadata; `DatabaseClient` runs the audit SQL. Both can share the transaction managed by the same R2DBC `ConnectionFactory`.

If the audit insert fails and the error propagates out, the status update can roll back with the transaction. If code catches the audit error and turns it into normal completion, the transaction may commit the status without the audit record; explicitly decide whether that is the desired semantics.

## 20. Using TransactionalOperator instead of annotations

When you need flexible transaction boundaries around specific sections of a publisher, you can use **TransactionalOperator**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class OrderWriter {

    private final TransactionalOperator transactionalOperator;
    private final OrderRepository orderRepository;
    private final OrderLineRepository orderLineRepository;

    public OrderWriter(
            TransactionalOperator transactionalOperator,
            OrderRepository orderRepository,
            OrderLineRepository orderLineRepository) {
        this.transactionalOperator = transactionalOperator;
        this.orderRepository = orderRepository;
        this.orderLineRepository = orderLineRepository;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        Mono<Order> work = orderRepository.save(toOrder(command))
                .flatMap(order ->
                        orderLineRepository.saveAll(toLines(order.id(), command))
                                .thenReturn(order)
                );

        return transactionalOperator.transactional(work);
    }
}
~~~

`TransactionalOperator` wraps a publisher and applies a transaction to that portion of the publisher. It is useful when:

- You do not want to use proxy annotations.
- You need to define a transaction boundary inside a large method.
- You need to control transactions on a specific publisher branch.
- You want explicit testability or composition.

Annotations suit transaction boundaries at the service method level; `TransactionalOperator` suits wrapping a pipeline segment. Both require the right `ReactiveTransactionManager`.

Do not wrap the same piece of work in multiple unnecessary transaction boundaries. Understand propagation and transaction context before nesting operators.

## 21. Testing reactive @Transactional methods

Tests must subscribe to the publisher and verify both committed and rolled-back data.

### 21.1. Testing commit on success

~~~java
@Test
void shouldCommitOrderAndLines() {
    CreateOrderCommand command = sampleCommand();

    StepVerifier.create(orderWriter.createOrder(command))
            .assertNext(order -> assertThat(order.id()).isNotNull())
            .verifyComplete();

    StepVerifier.create(orderRepository.count())
            .expectNext(1L)
            .verifyComplete();

    StepVerifier.create(orderLineRepository.count())
            .expectNext(2L)
            .verifyComplete();
}
~~~

Assertions after the publisher finishes verify that data has been committed and can be read back via another transaction or appropriate test context.

### 21.2. Testing rollback when a later step fails

You can create a command containing an order line that violates a constraint so the line-saving step emits an error:

~~~java
@Test
void shouldRollbackOrderWhenLineInsertFails() {
    CreateOrderCommand invalid = commandWithInvalidLine();

    StepVerifier.create(orderWriter.createOrder(invalid))
            .expectError()
            .verify();

    StepVerifier.create(orderRepository.count())
            .expectNext(0L)
            .verifyComplete();
}
~~~

This test verifies that the earlier inserted `Order` no longer exists after the subsequent step fails. Use a real test database or Testcontainers to validate the driver's transaction semantics.

### 21.3. Testing cancellation when needed by the use case

For long publishers or streaming endpoints, you can test cancellation and rollback. Tests should deliberately construct a publisher that can be cancelled after an operation has begun, then confirm the database state was not accidentally committed.

Not every test requires cancellation cases; prioritize testing paths that callers can actually cancel.

### 21.4. Avoiding outer test transactions that mask results

Some test frameworks automatically open a transaction for test methods. If the test's transaction wraps the operation being tested, data may not yet be committed or may roll back when the test finishes, making observed behavior differ from real requests.

Understand the transaction boundaries of the test, subscription, and service. For commit/rollback tests, structure data reads to verify outcomes after the service's transaction has completed.

## 22. Common mistakes when using @Transactional with Publishers

| Symptom | Possible cause | Resolution |
|---|---|---|
| Repository operation does not run | Publisher is ignored or never subscribed | Return the publisher or compose it into a consumed pipeline |
| Operations do not roll back together | One publisher was subscribed separately | Do not call `subscribe()` inside services |
| Thread gets blocked | Calling `block()` inside a reactive flow | Use `flatMap`, `map`, `then` and return a `Publisher` |
| Annotation has no effect | Self-invocation bypassing the proxy | Call through another bean or reorganize service boundaries |
| No reactive transaction | Missing `ReactiveTransactionManager` or wrong manager configured | Configure `R2dbcTransactionManager` with the right `ConnectionFactory` |
| Only part of operations roll back | One operation uses a different `ConnectionFactory` | Use the same factory/manager or design separate transactions |
| Error swallowed but data still commits | `onErrorResume` turns error into successful completion | Let error cross the boundary or mark rollback-only |
| Transaction holds connection too long | Publisher waits on external I/O or long streaming | Narrow the transaction boundary |
| Concurrent connection usage error | Multiple queries run in parallel on the same transactional connection | Serialize them or verify driver support |
| Checked exception does not roll back | Default rollback rules exclude checked exceptions | Declare an appropriate `rollbackFor` |
| `readOnly` does not prevent writes | `readOnly` is only a hint or database does not enforce it | Use DB permissions and authorization; do not rely on hints |
| Transaction hits the wrong database | Multiple managers/factories and the method selects the wrong one | Specify `transactionManager` and qualifiers explicitly |
| Timeout does not stop query as expected | Confusing transaction timeout with statement/HTTP timeout | Configure appropriate timeouts at each layer |

## 23. Transaction boundary design checklist

When adding `@Transactional` to a reactive service method, check:

1. Does the method return a Spring-supported `Publisher`?
2. Is an appropriate `ReactiveTransactionManager` present?
3. Does the manager manage the exact `ConnectionFactory` used by repositories/templates/clients?
4. Are all database operations that must be atomic included in the returned publisher?
5. Is any publisher ignored, separately subscribed, or blocked?
6. Which errors must roll back and which are allowed to commit?
7. Is `onErrorResume` or another operator swallowing errors before the transaction boundary?
8. Is the method called through a Spring proxy or only via self-invocation?
9. Are there multiple transaction managers or databases?
10. Are HTTP calls, messaging, emails, or long tasks inside the transaction?
11. Are queries running concurrently on the same connection?
12. Have commits, rollbacks, cancellations, and retries been tested against a real database/driver?

A good transaction boundary typically sits on a service method representing an atomic business unit. A single repository method does not necessarily need to open its own transaction if called within a larger transaction.

## 24. Conclusion

With Spring Data R2DBC, `@Transactional` can be declared on service methods returning `Mono`, `Flux`, or a supported reactive `Publisher`. Spring uses a `ReactiveTransactionManager`, typically `R2dbcTransactionManager`, to open a transaction when the publisher is subscribed and commit/roll back when the publisher completes, emits an error, or is cancelled according to the reactive lifecycle.

All operations requiring atomicity must be chained into the publisher returned by the method and use the same `ConnectionFactory`/transaction manager. Do not call `subscribe()`, `block()`, or discard publishers inside the method; avoid self-invocation bypassing the proxy; define rollback rules and avoid swallowing errors before the transaction boundary. With multiple databases, each transaction manager only manages its own `ConnectionFactory`.

Annotations help establish clear transaction boundaries at the service level. When you need to wrap a pipeline segment more flexibly, use `TransactionalOperator`. Regardless of approach, test commits, rollbacks, and cancellation against a real database/driver to confirm reactive operations truly participate in the same transaction.
