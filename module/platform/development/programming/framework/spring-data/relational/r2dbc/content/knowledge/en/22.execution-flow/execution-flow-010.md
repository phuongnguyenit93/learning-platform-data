# Handling Unsubscription and Resource Release

In reactive applications using Spring Data R2DBC, a query is typically represented by a `Mono` or `Flux`. Work begins only when a subscriber subscribes and can end in three main ways: normal completion, emitting an error, or cancellation. When a subscriber cancels its subscription, the pipeline must propagate the cancellation signal toward the source and release allocated resources, such as database connections, transactions, or data-reading resources.

Cancellation does not mean rolling back every side effect that has already occurred. It tells the publisher to stop emitting data and attempt to stop in-flight work to the extent supported by the source. The R2DBC driver may send a cancellation signal to the database, though whether an executing SQL statement stops immediately depends on the driver and database engine. Already committed changes or side effects sent to external systems cannot be undone merely by cancelling a subscription.

## 1. Subscription and cancellation in Reactive Streams

Reactive Streams uses a protocol among Publisher, Subscriber, and Subscription:

- Subscriber subscribes to Publisher and receives a Subscription.
- Subscriber requests elements using `request(n)`.
- Publisher emits `onNext`, then terminates with `onComplete` or `onError`.
- Subscriber can call `cancel()` on the Subscription to signal that it no longer wants results.

Cancellation is a one-way signal from subscriber to publisher. After cancelling, the subscriber should not expect further data signals from that subscription. The publisher and underlying sources must stop whatever work can be stopped and release resources.

Conceptual flow:

~~~mermaid
sequenceDiagram
    participant C as Subscriber / WebFlux
    participant R as Reactor pipeline
    participant D as R2DBC driver
    participant DB as Database
    C->>R: subscribe()
    R->>D: execute query
    D->>DB: SQL request
    DB-->>D: Rows / result
    D-->>R: onNext(...)
    C->>R: cancel()
    R->>D: propagate cancellation
    Note over D,DB: Driver may request query cancellation
    R->>D: release connection/resource
~~~

This is a conceptual model. When the database actually stops the statement and when the connection becomes ready for reuse depend on the driver, protocol, and database.

## 2. Situations that trigger cancellation

Cancellation can arise from many places:

- The HTTP client closes the connection while WebFlux is still producing the response.
- A downstream publisher calls `take(n)` and needs no further elements.
- `timeout(...)` expires and cancels the source publisher before emitting a timeout error.
- A composed branch is cancelled because another publisher failed or a subscriber lost interest.
- A user explicitly stops a task or the application shuts down.
- A subscription is cancelled during shutdown.

Example:

~~~java
Flux<Product> firstFive = productRepository.findAll()
        .take(5);
~~~

After receiving five elements, `take(5)` completes downstream and cancels the upstream subscription because no more reads are needed. If upstream is holding resources, it must handle the cancellation signal.

Timeout example:

~~~java
Mono<Product> product = productRepository.findById(id)
        .timeout(Duration.ofSeconds(2));
~~~

If the query emits no result within the deadline, Reactor cancels the source publisher and emits `TimeoutException` downstream. Timeout is one cause of cancellation, though downstream sees the timeout error rather than directly observing a cancel signal.

## 3. Cancellation differs from complete and error

Three outcomes must be distinguished:

| Signal | Meaning | Common handling |
| --- | --- | --- |
| Complete | Publisher finished emitting all data normally | Commit transaction if valid; release resources |
| Error | Publisher failed | Roll back transaction per policy; release resources |
| Cancel | Subscriber no longer wants to receive data | Stop cancellable work; roll back open transaction per transaction manager; release resources |

Cancellation is not a form of `onError`. The subscriber invokes `Subscription.cancel()`; the publisher does not emit `onError(CancellationException)` simply due to cancellation. If the application needs to log or count cancellations, use cancellation/finalization hooks instead of expecting an error.

## 4. Observing cancellation with Reactor

Reactor provides several operators for lifecycle observation:

### doOnCancel

`doOnCancel` runs when the subscription is cancelled:

~~~java
return productRepository.findAll()
        .doOnCancel(() ->
                log.info("Product stream was cancelled")
        );
~~~

This hook suits lightweight metrics, logging, or observational state updates. The callback is synchronous and does not return a cleanup publisher. Do not use it as the primary mechanism for closing connections asynchronously.

### doFinally

`doFinally` runs when the stream ends via complete, error, or cancel:

~~~java
return productRepository.findAll()
        .doFinally(signalType ->
                log.debug("Stream finished with signal {}", signalType)
        );
~~~

`SignalType` distinguishes `ON_COMPLETE`, `ON_ERROR`, and `CANCEL`. This is the right place to record stream completion metrics, processing duration, or cancellation counts.

### doOnTerminate

`doOnTerminate` is invoked when the publisher completes or errors, but it is not a hook for cancellation. If you need to observe all three outcomes, use `doFinally`.

Do not place asynchronous cleanup inside `doFinally`:

~~~java
// Unsuitable for closing a connection asynchronously.
source.doFinally(signal -> connection.close());
~~~

`doFinally` takes a callback returning `void`. The publisher returned by `connection.close()` is neither awaited nor coordinated as a cleanup step in the pipeline. Use `usingWhen` when cleanup returns a publisher.

## 5. Spring Data R2DBC manages connections automatically in repositories

When using Spring Data R2DBC repositories, `R2dbcEntityTemplate`, or `DatabaseClient`, you normally do not need to acquire and close connections manually:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Spring Data and the R2DBC infrastructure manage acquiring connections, executing statements, consuming results, and releasing connections when operations finish or are cancelled. With a connection pool, calling close on a pooled connection typically returns it to the pool for reuse; it does not necessarily close the physical socket.

Therefore, do not acquire an extra connection manually just to run repository queries, and do not manually close a connection managed by Spring Data. Keep publishers reactive and let the infrastructure manage resource lifecycles.

## 6. When is manual Connection management needed?

Only use the R2DBC SPI directly when you have needs unmet by repositories, templates, or `DatabaseClient`, such as low-level statement/result control or integrating a specialized operation.

When calling `ConnectionFactory.create()`, the application owns responsibility for releasing the acquired connection. You must handle all three outcomes:

- Publisher completes normally.
- Publisher emits an error.
- Subscriber cancels the subscription.

Do not rely solely on `doOnSuccess` or `doOnError` to close connections because those hooks do not fully cover cancellation and do not coordinate asynchronous cleanup.

## 7. Using usingWhen to release connections

Reactor provides `Mono.usingWhen` and `Flux.usingWhen` for resources with asynchronous cleanup. `usingWhen` takes:

1. A resource-supplying publisher.
2. A function using the resource and returning the result publisher.
3. A cleanup function on complete.
4. A cleanup function on error.
5. A cleanup function on cancel.

PostgreSQL example with R2DBC SPI:

~~~java
public Mono<Long> updateCustomerStatus(Long id, String status) {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> Flux.from(
                            connection.createStatement("""
                                    UPDATE customer
                                    SET status = $1
                                    WHERE id = $2
                                    """)
                                    .bind(0, status)
                                    .bind(1, id)
                                    .execute()
                    )
                    .concatMap(result ->
                            Mono.from(result.getRowsUpdated())
                    )
                    .reduce(0L, Long::sum),
            connection -> Mono.from(connection.close()),
            (connection, error) ->
                    Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
~~~

In this example:

- `ConnectionFactory.create()` provides a connection.
- The usage function runs the `UPDATE` statement and sums affected row counts.
- Cleanup is invoked on complete, error, or cancel.
- `Connection.close()` returns a publisher coordinated by `usingWhen`.

The example uses PostgreSQL-style placeholders (`$1`, `$2`). Placeholders and bind style depend on the driver. With a pool, `close()` normally returns the connection to the pool.

Do not duplicate cleanup with `doFinally` outside `usingWhen`; doing so can close the same connection multiple times or produce hard-to-control side effects.

## 8. Why is usingWhen better than try/finally in reactive code?

An imperative snippet might write:

~~~java
Connection connection = factory.create().block();
try {
    // execute SQL
} finally {
    connection.close().block();
}
~~~

This is unsuitable in reactive flows:

- `block()` blocks a thread waiting to acquire a connection.
- `close().block()` blocks a thread during cleanup.
- Subscriber cancellation does not automatically enter the `finally` block following publisher lifecycle semantics.
- Errors and cancellation can happen while an asynchronous publisher is in flight.

`usingWhen` ties the resource to the publisher lifecycle. When the subscription ends, Reactor executes the corresponding cleanup publisher and coordinates it with the terminal signal.

## 9. What does Connection.close() mean in a pool?

In R2DBC, `Connection.close()` ends usage of the connection. If the connection came from a pool, the pool typically implements close as returning the connection to the pool:

- The connection may be validated before reuse.
- If still valid, the pool places it back in the idle set.
- If broken or past its max lifetime, the pool may evict and physically close it.
- If the connection belongs to an open transaction, the transaction must be completed or rolled back per the management mechanism before the connection can be reused.

Do not hold connections longer than necessary. Connections retained after cancellation can starve the pool, forcing other requests to wait or hit acquire timeouts.

## 10. Does cancelling a publisher during a query stop SQL immediately?

There is no universal guarantee that a Reactor cancel signal stops a SQL statement on the server instantaneously.

Cancellation propagates through the `Subscription` to the R2DBC driver. The driver may:

- Send a cancel signal over the database protocol if supported.
- Stop reading results and close/release resources.
- Wait for network activity or the server to respond before the connection can be reused.
- Be unable to immediately interrupt an actively executing server operation in certain cases.

Exact behavior depends on the R2DBC driver, database, version, and statement type. Thus, cancellation stops the application from consuming further results and lets the driver halt work where possible; it is not a deterministic guarantee of instant SQL termination.

If a statement can run long, combine statement/query timeouts, request timeouts, database resource limits, and monitoring of active queries. Do not treat cancellation as a substitute for database-side timeouts.

## 11. Cancellation and reactive transactions

If a publisher runs inside a reactive transaction, cancellation carries special significance. Spring's transaction infrastructure manages transactions via the Reactor Context. When a subscriber cancels the publisher before the transaction completes, the transaction manager can roll back the open transaction and release the connection according to its mechanism.

Example:

~~~java
public Flux<Order> streamOrders() {
    Flux<Order> work = orderRepository.findAll()
            .doOnCancel(() ->
                    log.info("Order stream cancelled")
            );

    return transactionalOperator.transactional(work);
}
~~~

If downstream cancels before the `Flux` completes, the reactive transaction is cancelled and the transaction manager handles rollback. Therefore, avoid wrapping very long read streams or unbounded streams inside a transaction unless such a long transaction boundary is truly needed.

With a short write `Mono`, cancellation often arrives before the result is emitted or while the database is processing. The final outcome depends on the transaction manager and driver; if the transaction already committed before cancel arrived, cancellation cannot undo that commit.

Do not call `subscribe()` inside a transactional method. A detached subscription may run outside the caller's transaction context.

## 12. Placement of onErrorResume affects rollback

If an error propagates outside `TransactionalOperator`, the operator observes the error and rolls back:

~~~java
return transactionalOperator.transactional(work)
        .onErrorResume(error -> {
            log.error("Transaction failed and was rolled back", error);
            return Mono.empty();
        });
~~~

Here, error handling sits outside the operator. The operator receives the error first, performs rollback, and then the outer publisher recovers to completion.

If you recover from the error inside the publisher wrapped by the transaction:

~~~java
return transactionalOperator.transactional(
        work.onErrorResume(error -> Mono.empty())
);
~~~

the operator may only see the publisher complete normally and commit. If you want a rollback even when the error was handled internally, use transaction status and mark rollback-only via `TransactionalOperator.execute(...)`.

This rule applies to error recovery. Cancellation does not pass through `onErrorResume` like a normal exception; use cancellation-aware cleanup and transaction management.

## 13. Cancelling a composed stream using flatMap

When using `flatMap`, a publisher may have multiple active inner publishers:

~~~java
return customerRepository.findAll()
        .flatMap(customer ->
                orderRepository.findRecentByCustomerId(customer.id())
        );
~~~

If the subscriber cancels the outer stream, Reactor propagates cancellation to the source and active inner subscriptions. The driver gets the chance to cancel corresponding queries and release resources.

If an inner publisher already completed and committed its own transaction before cancellation arrived, those committed changes are not reversed by cancelling the outer stream. Cancellation is not a global rollback mechanism for independent side effects.

When an atomic unit is required, place coordinated operations within the same reactive transaction instead of giving each inner publisher its own separate transaction.

## 14. Cancellation does not undo side effects outside the database

Suppose a pipeline both saves an order and sends an email:

~~~java
return orderRepository.save(order)
        .flatMap(saved ->
                emailClient.sendConfirmation(saved)
                        .thenReturn(saved)
        );
~~~

If the client cancels the request after the email was sent, cancellation cannot recall the email. Similarly, payment calls, published messages, or external system updates do not automatically roll back with an R2DBC transaction.

For business flows coordinating the database with external systems, consider:

- Writing the order and an outbox event in the same transaction.
- A separate process dispatching events after commit.
- Idempotency keys to avoid duplicate processing.
- Bounded retries with backoff.
- Sagas or compensating actions if a workflow spans multiple services.

Avoid placing slow HTTP calls inside a transaction holding connections or row locks whenever they can be separated out.

## 15. Cleanup when using other resources

The `usingWhen` pattern is not limited to `Connection`. It suits any resource with an asynchronous release operation, such as:

- Cursors or streaming results managed by a specific API.
- Files or streams with asynchronous cleanup.
- Sessions or handles issued by a reactive library.
- Any resource created from a publisher that must close on complete, error, or cancel.

For Java resources with synchronous, non-blocking cleanup, `using` or `doFinally` may fit depending on semantics. When cleanup returns a publisher, prefer `usingWhen` so Reactor awaits release.

Never hold a connection in a singleton service field. Connections are short-lived resources typically allocated for a specific operation or transaction.

## 16. Cancellation, timeout, and backpressure

Backpressure regulates how many elements a subscriber wants to receive; cancellation terminates the subscription's demand for elements.

Example:

~~~java
return eventRepository.findAll()
        .limitRate(64)
        .take(100);
~~~

- `limitRate(64)` paces upstream demand in chunks.
- `take(100)` completes after 100 elements and cancels upstream.

Backpressure does not release a connection automatically while the publisher remains active. Once the stream is actually cancelled, the source must perform cleanup.

Timeouts can generate upstream cancellation:

~~~java
return databaseCall()
        .timeout(Duration.ofSeconds(3))
        .onErrorMap(
                TimeoutException.class,
                error -> new DatabaseRequestTimeoutException()
        );
~~~

Reactor's timeout limits how long the publisher waits. If you need to limit statement duration on the server, configure appropriate query/statement timeouts on the database and driver. Both limits work together, though they are not synonymous.

## 17. Monitoring cancellation and resources in production

Collect signals that reveal whether cancellation is leaking resources:

| Metric/log | What to observe |
| --- | --- |
| Cancelled subscription count | Client disconnects, timeouts, or consumer stops |
| Query duration | SQL statements continuing to run long after requests cancel |
| Active/idle/pending connections | Whether connections return to the pool |
| Connection acquire latency | Whether other requests wait for connections after cancellations |
| Transaction rollback count | Transactions rolled back due to errors/cancellations |
| Cleanup failures | Errors closing resources or returning connections to the pool |
| Timeout/deadlock count | Database experiencing waits or contention |

Simple metric example:

~~~java
return orderRepository.findAll()
        .doFinally(signal -> {
            if (signal == SignalType.CANCEL) {
                cancellationCounter.increment();
            }
        });
~~~

Do not log full sensitive row payloads or SQL bind parameters solely to investigate cancellations. Logging correlation IDs, timestamps, operation types, and resource states is sufficient in most cases.

## 18. Testing cancellation

Unit tests can use `StepVerifier` to verify the publisher receives cancellation:

~~~java
StepVerifier.create(service.streamOrders())
        .expectNextCount(1)
        .thenCancel()
        .verify();
~~~

You can check hooks:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> source = Flux.<Integer>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
~~~

This test only proves cancellation propagated through the publisher and the callback fired. It does not prove the driver cancelled SQL on the server or returned the connection to the pool.

Integration tests against a real database should:

1. Create a sufficiently long streaming query or a controlled connection-holding publisher.
2. Subscribe and consume partial results.
3. Cancel the subscription.
4. Wait for cleanup to complete within a test deadline.
5. Verify active connections drop or a connection can be acquired again.
6. Verify the transaction rolled back if the publisher was inside a transaction.
7. Observe the database to check whether the query kept running or was cancelled by the driver.

Avoid arbitrary long sleeps. Use latches, sinks, barriers, or timed coordination signals for deterministic tests. Run tests against the same driver and database engine as production.

## 19. Common mistakes

1. **Using `doOnSuccess`/`doOnError` to clean up connections.** These hooks do not cover cancellation completely and do not coordinate asynchronous cleanup.
2. **Using `doFinally` to call `close()`.** The returned cleanup publisher is not awaited; use `usingWhen`.
3. **Calling `block()` in reactive services.** Blocks threads and breaks cancellation coordination.
4. **Calling `subscribe()` manually in services.** Creates detached subscriptions whose lifecycle callers cannot control.
5. **Forgetting the cancel branch of `usingWhen`.** Resources may stay held when subscribers cancel.
6. **Manually closing connections managed by `DatabaseClient`.** Can corrupt Spring/pool connection lifecycles.
7. **Assuming cancel always stops SQL instantaneously.** Drivers/databases may take time or not support cancelling certain operations.
8. **Assuming cancellation rolls back already committed side effects.** Completed commits cannot be reversed by cancel.
9. **Swallowing errors inside a transaction.** Operators may see completion and commit unless marked rollback-only.
10. **Holding a transaction across a long `Flux`.** Connections and locks can be held for the entire time the client consumes data.
11. **Treating Reactor timeout as a statement timeout.** Configure timeouts at the appropriate layers.
12. **Not measuring the connection pool after cancellation.** Leaks or slow cleanup can occur without showing up in request logs.

## Quick Selection Rules

- Use `doOnCancel` to observe cancellation and `doFinally` to record complete/error/cancel.
- Use `usingWhen` when manually managing resources whose cleanup returns a publisher.
- With repositories, `DatabaseClient`, and templates, let Spring Data manage connections.
- Use reactive transactions to wrap operations that must roll back on error/cancel.
- Place `onErrorResume` outside the transaction if the transaction should observe the error and roll back before recovery.
- Use Reactor timeout for publisher deadlines and database/driver query timeout for SQL execution duration.
- Do not assume cancel definitely stops SQL immediately or undoes external side effects outside the database.
- Verify pool, transactions, and drivers with integration tests exercising real cancellation.

Cancellation is a normal part of the reactive stream lifecycle. In Spring Data R2DBC, cancellation must propagate to the source publisher so the driver has the opportunity to stop reading or executing, the transaction manager can roll back open transactions, and resources are released. For standard repository operations, Spring manages connections; when using the R2DBC SPI directly, use `usingWhen` to clean up across complete, error, and cancel. Monitor cancellation alongside connection pool health and test on the real driver/database to spot resources held too long.
