# Cancellation, Timeouts, and Their Impact on Transactions

In Spring Data R2DBC applications, database operations are represented by reactive publishers such as `Mono` and `Flux`. A publisher can complete normally, emit an error, or receive a cancellation signal from its subscriber. An operation can also exceed the wait time allowed by the application.

Cancellation and timeouts can directly affect an open transaction. With properly managed reactive transactions, Spring can roll back when a publisher is cancelled or emits an error before commit. However, cancelling a subscription cannot reverse an already-committed transaction, and an application-level timeout signal does not always prove the database stopped running the SQL query immediately.

Handling this properly requires distinguishing cancellation timing, transaction boundaries, timeout types, and driver/database capabilities.

## 1. Lifecycle of a reactive publisher

An R2DBC operation typically returns a `Mono` or `Flux`. The publisher describes work; the operation generally executes only when a subscriber subscribes.

Example:

~~~java
Mono<Long> update = databaseClient.sql("""
        UPDATE customer
        SET active = FALSE
        WHERE id = :id
        """)
    .bind("id", customerId)
    .fetch()
    .rowsUpdated();
~~~

At the time `update` is constructed, the SQL statement has not necessarily been sent to the database. When the publisher is subscribed, acquiring a connection, sending SQL, and receiving results take place.

Under Reactive Streams, a subscription has three notable termination/control signals:

- **onComplete**: the publisher completes normally.
- **onError**: the publisher terminates due to an error.
- **cancel**: the subscriber asks the publisher to stop emitting data and stop work if possible.

Cancellation is a control signal from the subscriber, not a value emitted downstream and not an `onError` failure. Therefore, code that only handles `onError` will not automatically observe every cancellation case.

### 1.1. Situations that can trigger cancellation

Cancellation can occur when:

- An HTTP client disconnects or aborts the request.
- A user navigates away and the application cancels the task.
- An upstream/downstream consumer no longer needs data.
- Code calls `dispose()` on the subscription.
- Partial-consumption operators such as `take()`, `next()`, or `first()` are used.
- A timeout operator cancels the source publisher upon expiration.
- An aggregate task is cancelled because another branch already produced enough results or failed.

Not every cancellation is an error. For example, a client closing its connection may mean the request no longer needs a response. However, if the publisher is inside a data-writing transaction, cancellation must be handled according to proper transaction boundaries.

## 2. Distinguishing cancellation, timeouts, and database errors

These three concepts are related but distinct:

| Situation | What happens | Typical application signal |
|---|---|---|
| Cancellation | Subscriber requests stopping the subscription | Cancel signal, not `onError` |
| Reactive timeout | Reactor operator deadline expires | `TimeoutException` downstream and cancellation upstream |
| Database/driver timeout | Driver or database aborts an operation exceeding allowed time | Usually emits a driver/database error |
| Connection acquire timeout | Cannot obtain a connection from pool in time | Pool-wait timeout error |
| Connect timeout | Cannot establish a new connection to database in time | Connection error |
| Transaction timeout | Transaction exceeds limit supported by transaction manager or system | Behavior depends on transaction manager/driver/database |

A single request can encounter multiple timeout layers. For example, a request has a 3-second deadline while the pool needs 4 seconds to supply a connection. The application can time out before any SQL statement is even sent to the database.

### 2.1. Cancellation does not automatically mean SQL stopped

When a subscriber cancels, the signal propagates upstream through the reactive chain. The driver may attempt to cancel the running statement or release associated resources, yet whether and when the SQL statement stops depends on the R2DBC driver, database, and operation state.

Therefore, do not conclude that:

- Because the subscriber cancelled, the database definitely never ran the SQL statement.
- Because `Mono.timeout()` emitted `TimeoutException`, the server stopped processing instantaneously.
- Because the client received no response, the transaction definitely rolled back.

If the DML statement was already executed by the database and the transaction already committed, cancellation arriving afterward cannot undo committed data.

## 3. How does cancellation affect reactive transactions?

Reactive transactions are managed around a publisher chain. With Spring, a transaction typically begins when the publisher is subscribed, database operations join the same transaction context, and the transaction commits when the chain completes normally or rolls back when it terminates in a rollback-triggering way.

Spring Framework supports rolling back when a reactive transactional publisher is cancelled. Since Spring Framework 5.3, a cancellation signal in a reactive transaction is treated as a reason to roll back the active transaction. This is important because cancellation does not flow through the regular `onError` path.

Service example using `@Transactional`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Order> createOrder(Order order) {
        return orderRepository.save(order)
            .flatMap(saved ->
                auditRepository.recordCreated(saved.id())
                    .thenReturn(saved)
            );
    }
}
~~~

Suppose saving the order has run, yet the publisher is cancelled before the transaction commits. Spring's transaction infrastructure can roll back the open transaction. Changes belonging to that transaction are undone according to database semantics.

Important conditions:

- The method must actually execute inside a reactive transaction.
- Repositories/templates/`DatabaseClient` must share the same transaction manager and `ConnectionFactory`.
- The publisher must be returned and kept in the same reactive chain.
- Cancellation must arrive before the transaction finishes committing.
- The driver and database must support transactions/rollback for those operations.

### 3.1. When does a transaction commit?

In a reactive transaction, commit typically occurs when the publisher inside the transaction completes normally. If the publisher emits an error and that error is not converted into a successful result, the transaction manager can roll back according to rollback rules.

Cancellation prior to commit causes the transaction manager to roll back. However, if commit has already completed, a subsequent cancellation cannot reverse the outcome.

You can visualize it as:

~~~mermaid
flowchart TD
    A["Subscribe to publisher"]
    B["Begin transaction"]
    C["Execute SQL in transaction"]
    D{"How does publisher terminate?"}
    E["onComplete"]
    F["Commit"]
    G["onError"]
    H["Rollback"]
    I["cancel"]
    J["Rollback active transaction"]
    K["Transaction outcome"]

    A --> B --> C --> D
    D --> E --> F --> K
    D --> G --> H --> K
    D --> I --> J --> K
~~~

This is a conceptual model. Exact commit/rollback timing and whether the driver cancels an in-flight statement also depend on the implementation.

### 3.2. Using TransactionalOperator

If you want to define transactions programmatically, use `TransactionalOperator`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class PaymentService {

    private final TransactionalOperator transactionalOperator;
    private final PaymentRepository paymentRepository;
    private final LedgerRepository ledgerRepository;

    public PaymentService(
            TransactionalOperator transactionalOperator,
            PaymentRepository paymentRepository,
            LedgerRepository ledgerRepository) {
        this.transactionalOperator = transactionalOperator;
        this.paymentRepository = paymentRepository;
        this.ledgerRepository = ledgerRepository;
    }

    public Mono<Payment> pay(Payment payment) {
        Mono<Payment> work =
            paymentRepository.save(payment)
                .flatMap(saved ->
                    ledgerRepository.record(saved)
                        .thenReturn(saved)
                );

        return transactionalOperator.transactional(work);
    }
}
~~~

`TransactionalOperator` wraps the `work` publisher. If the publisher completes normally, the transaction commits; if the publisher emits an error or is cancelled before commit, the transaction manager handles rollback.

Do not create transactions by calling `subscribe()` manually inside a service. When self-subscribing, the publisher can run detached from the caller's transaction context, and the caller loses control over completion timing.

## 4. Using timeout in reactive pipelines

Reactor provides the `timeout` operator to bound how long to wait for signals from a publisher.

Example:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<Order> result =
    orderRepository.findById(orderId)
        .timeout(Duration.ofSeconds(3));
~~~

If the publisher does not emit an expected signal within the allowed duration, the `timeout` operator emits a `TimeoutException` downstream and cancels the source publisher.

For writes inside a transaction, you can place a timeout around the transactional work:

~~~java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            auditRepository.recordCreated(saved.id())
                .thenReturn(saved)
        )
        .timeout(Duration.ofSeconds(5));
}
~~~

If the timeout occurs before the transaction commits, the timeout error propagates through the publisher and the transaction can roll back. If the timeout is placed on the caller outside the transactional method, it cancels the publisher managed by the transaction interceptor; Spring can observe the cancellation and roll back the open transaction.

The `timeout` operator is a reactive-layer deadline. It does not configure a server-side statement timeout and does not guarantee the database stopped processing the SQL statement at the exact moment `TimeoutException` is emitted.

### 4.1. Choosing timeout fallbacks carefully

Reactor allows providing a fallback publisher upon timeout:

~~~java
Mono<Order> result =
    orderRepository.findById(orderId)
        .timeout(
            Duration.ofSeconds(2),
            Mono.error(new RequestTimedOutException())
        );
~~~

An important point is how timeout errors are handled inside a transaction. If the application uses `onErrorResume` to replace a timeout with a normal result before the transaction manager observes publisher termination, the transaction may be treated as having completed successfully and commit.

Example requiring caution:

~~~java
@Transactional
public Mono<String> updateWithFallback(Long id) {
    return updateOrder(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.just("Timed out")
        );
}
~~~

In this example, the timeout was turned into a normal value. The transaction manager may see the publisher complete normally with no error left to trigger rollback. If timeout must roll back the transaction, let the error cross the transaction boundary or mark the transaction rollback-only via the appropriate mechanism.

Do not swallow timeout errors if business logic requires rollback.

### 4.2. Per-request timeout vs. per-operation timeout

A whole-request timeout bounds the total duration of the processing chain. A per-operation database timeout bounds the wait time for one specific publisher.

Example:

~~~java
Mono<OrderSummary> response =
    orderRepository.findById(orderId)
        .timeout(Duration.ofSeconds(2))
        .flatMap(order ->
            paymentRepository.findByOrderId(order.id())
                .timeout(Duration.ofSeconds(2))
                .map(payment -> toSummary(order, payment))
        )
        .timeout(Duration.ofSeconds(5));
~~~

The two 2-second timeouts apply individually to each operation; the 5-second timeout caps the entire chain. Total time is not simply always 4 seconds because operations may run sequentially, mapping or scheduling overhead may exist, and the overall timeout can expire before a child timeout.

Set timeouts according to each layer's latency requirements, avoiding conflicting or overly short timeouts that cause frequent request cancellations.

## 5. Timeout layers in R2DBC connections

An application can have multiple independent timeout layers. Configure the right layer instead of using one number for every problem.

| Timeout type | What does it limit? | Example cause |
|---|---|---|
| Pool acquire timeout | Time waiting to borrow a connection from pool | Pool exhausted |
| Connect timeout | Time to establish a new connection | Network/DNS/database unresponsive |
| Statement/query timeout | Time database/driver allows a SQL query to run | Slow query or long lock wait |
| Transaction timeout | Time a transaction is allowed to remain open | Transaction holds locks too long |
| Reactive timeout | Time waiting for publisher to emit signals | Application receives no result within deadline |
| HTTP/request timeout | Total request processing time | Overall pipeline exceeds SLA |

### 5.1. Pool acquire timeout

If using `r2dbc-pool`, you can configure how long to wait for a connection. In Spring Boot, a common configuration is:

~~~yaml
spring:
  r2dbc:
    pool:
      enabled: true
      max-size: 20
      max-acquire-time: 3s
~~~

`max-acquire-time` limits how long to wait to acquire a connection from the pool. It does not limit how long a SQL query runs after the connection is granted.

Property names and availability depend on Spring Boot and `r2dbc-pool` versions. Check the property reference for your project's exact versions.

### 5.2. Connect timeout

Connect timeout limits the time to establish a new connection to the database. It can be configured via driver options or `ConnectionFactoryOptions` if supported by the driver.

Connect timeout does not replace pool acquire timeout. If the pool already has an idle connection, an operation may not need to open a new connection; conversely, if the pool needs to open a new connection, connect timeout becomes relevant.

### 5.3. Statement/query timeout

Statement timeout aims to cap how long the database or driver processes a SQL statement. Configurability depends on the R2DBC driver and database engine.

Some databases expose settings at the session, role, or statement level. For instance, PostgreSQL has the `statement_timeout` setting. Exact configuration should follow PostgreSQL and driver documentation.

There is no single portable statement timeout configuration that applies identically across all R2DBC drivers. Verify:

- Whether the driver supports statement-level timeouts.
- What server-side settings the database provides.
- Whether the timeout applies while waiting on locks.
- What error the driver emits on timeout and whether the connection remains usable.
- Whether the current transaction must roll back or is marked failed.

### 5.4. Reactive timeout is not a statement timeout

Example:

~~~java
databaseClient.sql("SELECT * FROM large_table")
    .fetch()
    .all()
    .timeout(Duration.ofSeconds(2));
~~~

This snippet limits how long the publisher may wait for signals under Reactor. Upon expiration, Reactor emits `TimeoutException` and cancels upstream. It is not a portable setting telling the database server to halt the query after exactly 2 seconds.

To protect the database from runaway queries, use driver/database statement timeouts where supported alongside application-layer reactive deadlines to bound request duration.

## 6. Cancellation when writes happen outside a transaction

If a DML statement runs in auto-commit mode or outside an application-managed transaction, cancellation does not provide the same rollback guarantee as an open transaction.

Example:

~~~java
Mono<Long> update =
    databaseClient.sql("""
            UPDATE account
            SET balance = balance - :amount
            WHERE id = :id
            """)
        .bind("amount", amount)
        .bind("id", accountId)
        .fetch()
        .rowsUpdated();
~~~

If the statement executes and commits in auto-commit mode before cancellation is processed, the data has already changed. The subscriber may not receive the row count, yet that does not prove the operation never happened.

This is a critical scenario for HTTP APIs: a client can time out or disconnect after the database write already finished. The client sees a failed request while the server may have already executed the business action.

If multiple operations must succeed or roll back together, put them in a transaction. Still, even with a transaction, if commit finished before the client received the response, cancellation arriving after commit cannot undo it.

## 7. Timeouts and uncertain outcome states

A client-side timeout can produce an "unknown outcome" state:

1. Application sends a write command.
2. Database executes and possibly commits.
3. Response is delayed or lost in transit.
4. Client times out waiting.
5. Client does not know whether the command committed.

This is not the same as a failure confirming the command never ran. Consequently, blindly retrying a non-idempotent operation can create duplicate records or execute business logic twice.

For example, if a client sends "deduct 100 from balance" and times out, resending the command may deduct another 100 if the first attempt already committed.

### 7.1. Designing idempotent operations

An idempotent operation can be repeated without altering business state beyond its first execution.

Design techniques:

- Use a unique idempotency key for payment/order creation requests.
- Enforce a unique constraint on a business key.
- Store the request key and processing outcome within the same transaction.
- Use conditional updates to prevent applying a state transition more than once.
- Re-query state by ID/idempotency key before deciding to retry.

Schema example storing an idempotency key:

~~~sql
CREATE TABLE payment_request (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

When a request is resent with the same idempotency key, the unique constraint prevents creating two records for the same request. The application can read the stored status and return the previous outcome.

### 7.2. Retries must sit at the right transaction boundary

Reactor has retry operators, yet retry placement affects subscription count and transactions.

Conceptual example:

~~~java
Mono<Order> work =
    orderRepository.save(order)
        .flatMap(saved -> reserveInventory(saved));

return transactionalOperator.transactional(work)
    .retryWhen(retrySpec);
~~~

Placing retry outside the transactional publisher can usually re-subscribe to the entire transactional unit, depending on how the publisher and transaction manager are configured. Placing retry inside the transaction may retry a statement inside the same transaction after an error that already caused the database/driver to invalidate that transaction.

Do not automatically retry all errors. Retry only clearly identified transient failures, ensure operations are idempotent, and understand transaction boundaries. A timeout also does not prove an operation failed to commit, so retrying after timeouts requires explicit policy.

## 8. Observing cancellation and timeouts

Cancellation does not pass through `onError`. To record completion, error, and cancel alike, use `doFinally`:

~~~java
import reactor.core.publisher.SignalType;

return orderRepository.findById(orderId)
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            log.info("Order lookup was cancelled");
        }
    });
~~~

Or use `doOnCancel` if you only need an action when upstream receives cancel:

~~~java
return repository.findById(id)
    .doOnCancel(() -> log.debug("Lookup cancelled"));
~~~

These callbacks are appropriate for logging or metrics. Do not use them as a manual rollback mechanism replacing Spring's transaction manager.

Metrics worth tracking:

- Cancellation counts by endpoint and operation type.
- Timeout counts across pool acquire, connect, query, and request layers.
- Connection acquisition times and SQL execution durations.
- Transaction rollbacks due to errors versus cancellations.
- Pool active/idle/pending acquire counts.
- Requests that timed out where writes may have already committed.
- Driver and database errors following cancellation.

Logs should include a correlation/request ID to tie requests to queries and transactions. Avoid logging credentials or sensitive data.

## 9. Releasing connections and resources

When using `DatabaseClient`, Spring manages acquiring and releasing connections according to the operation and transaction lifecycle. When a publisher is cancelled, the resource-management infrastructure is notified to release the connection or return it to the pool as supported by the driver.

If using the R2DBC SPI directly, the application must ensure the connection closes across all three paths: normal completion, error, and cancellation. You can use Reactor `usingWhen`:

~~~java
import io.r2dbc.spi.Connection;
import io.r2dbc.spi.ConnectionFactory;
import reactor.core.publisher.Mono;

Mono<Integer> ping(ConnectionFactory connectionFactory) {
    return Mono.usingWhen(
        Mono.from(connectionFactory.create()),
        connection -> Mono.from(
                connection.createStatement("SELECT 1").execute()
            )
            .flatMap(result ->
                Mono.from(result.map((row, metadata) ->
                    row.get(0, Integer.class)
                ))
            ),
        connection -> Mono.from(connection.close()),
        (connection, error) -> Mono.from(connection.close()),
        connection -> Mono.from(connection.close())
    );
}
~~~

`usingWhen` provides cleanup hooks for completion, error, and cancellation. This illustrates direct SPI access; when using `DatabaseClient` or Spring Data repositories, manual connection lifecycle management like this is usually unnecessary.

Do not store a `Connection` in a singleton service or share a connection across multiple requests. Let the framework or resource operator manage lifecycle.

## 10. Operators that easily trigger unexpected cancellation

Some operators only need part of the data and cancel the source publisher once they have received enough results:

~~~java
Flux<Customer> source = repository.findAll();

Mono<Customer> firstCustomer = source.next();
~~~

`next()` takes the first element and cancels the source because remaining elements are not needed. If `source` sits inside a reactive transaction, cancellation can cause the transaction to roll back under Spring's reactive transaction rules.

Similarly, `take(n)` can cancel upstream after receiving `n` elements. If a transaction is designed to read a full dataset and perform writes afterward, cutting off the publisher early can cause unexpected transaction rollback.

Since Spring Framework 5.3, a cancellation signal inside a reactive transaction triggers transaction rollback. Consequently, avoid using `next()`, `take()`, or source-truncating operators inside a transactional publisher if your actual intent is committing after consuming partial results. Design transaction boundaries to match the exact amount of data to be read.

Not every use case needs a transaction wrapping a long read stream. For queries only needing the first item, consider avoiding a wide transaction if multi-operation consistency is not required.

## 11. Transactions and HTTP request timeouts

In a WebFlux application, a request can be cancelled when the client disconnects. The server can propagate cancellation down to the controller publisher and underlying repository operations.

If a controller calls a service with a reactive transaction:

~~~java
@PostMapping("/orders")
public Mono<Order> create(@RequestBody Order order) {
    return orderService.createOrder(order);
}
~~~

If the client disconnects before the transaction finishes, cancellation can propagate down the publisher chain and cause the open transaction to roll back.

However, if the transaction already finished committing right before the client disconnected prior to receiving the response, the data remains persisted. The client may not know the outcome. That is why payment/order creation APIs should support idempotency keys or status-lookup endpoints.

Do not hold a transaction open while waiting on long non-database work such as calling HTTP services, downloading files, or awaiting user confirmation. Long transactions hold connections and locks, raising the risk of pool exhaustion and deadlocks. Keep transactions short, enclosing only operations requiring database atomicity.

## 12. Common mistakes

### 12.1. Assuming cancel always rolls back everything

Cancellation can only roll back an active, properly managed transaction. It cannot reverse an already-committed transaction or statements already committed in auto-commit mode.

### 12.2. Assuming Mono.timeout is a server-side query timeout

The `timeout` operator bounds how long a publisher waits for signals and cancels upstream. To cap SQL execution time in the database, configure appropriate driver/database timeouts.

### 12.3. Using onErrorResume and committing accidentally

If a timeout/error is turned into a normal value inside a transaction boundary, the transaction manager may see normal completion. Let the error pass through the transaction manager or mark rollback-only when needed.

### 12.4. Retrying immediately after timeout

A timeout can occur after the database committed while the response had not arrived yet. Retrying non-idempotent operations can execute business logic twice.

### 12.5. Using next()/take() inside a transaction without realizing cancellation occurs

These operators can cancel upstream once enough data is received. Inside a reactive transaction, cancellation can trigger rollback.

### 12.6. Calling subscribe() inside a service

Self-subscribing spawns an execution flow detached from the publisher managed by the caller, potentially losing transaction context, cancellation propagation, and consistent error handling. Return the publisher or compose with `flatMap`/`then`.

### 12.7. Using one timeout for every layer

Pool acquire timeout, connect timeout, statement timeout, transaction timeout, and request timeout control different phases. Set appropriate limits per layer.

### 12.8. Failing to release connections when using the SPI directly

When using `ConnectionFactory`/`Connection` manually, handle cleanup across success, error, and cancel paths. Otherwise, the pool can leak and exhaust connections.

## 13. Practical design principles

- Keep reactive publishers in one continuous chain from controller/service to repository.
- Use `@Transactional` or `TransactionalOperator` to manage reactive transactions.
- Understand that cancellation before commit can roll back an open transaction; cancellation after commit cannot undo it.
- Do not treat a client timeout as certainty that the database did not write data.
- Use application-layer timeouts to cap request duration and configure separate pool/connect/query timeouts where supported by the driver/database.
- Distinguish pool acquire timeouts from statement timeouts.
- Do not swallow `TimeoutException` inside a transaction if business logic requires rollback.
- Avoid `next()`/`take()` inside transactional publishers if cancelling upstream will cause unintended rollback.
- Do not call `block()` or `subscribe()` casually inside reactive services.
- Retry only well-defined transient errors and ensure operations are idempotent.
- Use idempotency keys or unique constraints for write operations that may be resent after timeouts.
- Keep transactions short and avoid calling external services while holding a transaction/connection.
- Use `doFinally(CANCEL)` or metrics to observe cancellations; do not use such callbacks in place of transaction cleanup.
- When using the R2DBC SPI directly, release connections across all success/error/cancel paths.
- Test cancellation, timeouts, and rollbacks against the exact production database/driver.

## 14. Key takeaways

Cancellation is a subscriber signal requesting the publisher to stop; Reactor timeouts typically emit `TimeoutException` and cancel the source publisher. Inside a Spring-managed reactive transaction, cancellation before commit can roll back the transaction, yet cannot reverse already-committed data. Cancellation also does not guarantee the driver/database stops a SQL statement immediately.

Timeouts must be configured per layer: pool connection acquisition, connection establishment, statement execution, transaction duration, and overall request deadline. Reactive timeouts do not replace server-side statement timeouts. If a client times out during a write, the outcome may be uncertain; use idempotency and check state before retrying. Keep publishers in the same transaction chain, avoid swallowing errors that must roll back, and do not self-subscribe inside services so transactions and resources are managed properly.
