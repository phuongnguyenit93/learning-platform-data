# Evaluating Transaction and Connection Hold Times

In a Spring Data Relational R2DBC application, SQL execution time is not the entire duration a database connection is occupied. A connection may sit pinned while waiting to be acquired from the pool, running multiple statements, executing application logic, awaiting external services, streaming results, or committing/rolling back a transaction. If you only measure query duration, you can miss why the connection pool drains and requests stall.

To evaluate performance accurately, separate at least three intervals: connection pool wait time, connection hold/lease time, and transaction lifetime. In addition, measure individual SQL execution times, gaps between statements, active connections, and pending pool requests. These metrics pinpoint whether connections are held too long due to slow databases, overly broad transactions, external work, or prolonged streams.

## 1. Distinguishing the Time Intervals

A reactive request can pass through the following milestones:

```text
T0  Publisher is subscribed to
T1  Connection request starts against the pool
T2  Connection is granted to the operation
T3  Transaction begins (if applicable)
T4  First SQL statement begins
T5  First SQL statement completes
T6  Application logic / subsequent SQL statements
T7  Commit or rollback completes
T8  Connection is returned to the pool
T9  Publisher emits terminal signal to downstream
```

Depending on implementation and driver, some milestones may occur close together or not be directly observable at the application layer. Nevertheless, the conceptual intervals remain useful:

| Metric | Interpretation | Question It Answers |
| --- | --- | --- |
| Pool acquisition time | T2 minus T1 | How long does the request wait to get a connection? |
| Connection hold time | T8 minus T2 | How long is the connection held before returning to the pool? |
| Transaction duration | T7 minus T3 | How long does the transaction stay open from begin to commit/rollback? |
| SQL execution time | Time of one statement from execute to result completion | How long does the database/driver spend processing the statement? |
| Application gap time | Intervals between statements or between SQL and commit | What is the application doing while holding the transaction/connection? |
| End-to-end request time | T9 minus T0 | How long does the caller wait for the final result? |

Do not collapse everything into a single generic `database latency` metric. A query may take 10 ms while the transaction pins the connection for 800 ms because the service waits on an HTTP call before committing.

## 2. Connection Acquisition Time vs. Connection Hold Time

With a connection pool, the application does not necessarily open a new TCP/database connection per request. It asks the pool for an existing connection or creates one according to configuration. When no free connection exists, requests wait for a release.

**Acquisition time** is the time from requesting a connection until the pool grants one. It increases when:

- The pool has reached its allowed connection limit.
- Existing connections are held for too long.
- The database is slow or refuses new connections.
- Establishing a new connection takes a long time.
- Concurrent requests exceed pool/database capacity.

**Hold time** is the time from granting the connection until releasing it. Hold time increases when:

- Transactions contain many operations or prolonged application logic.
- Streaming queries return many rows with slow downstream consumption.
- The application calls HTTP, message brokers, or filesystems inside transactions.
- A publisher never completes or is not cancelled cleanly.
- Manually acquired connections lack proper cleanup.

These two metrics are linked yet distinct. High acquisition time is usually a symptom of pool contention; high hold time is often a root cause of that contention.

## 3. Transaction Duration Does Not Always Equal SQL Duration

A transaction can run multiple statements:

```java
return transactionalOperator.transactional(
        orderRepository.save(order)
                .flatMap(saved -> inventoryRepository.reserve(
                        saved.getProductId(), saved.getQuantity()))
                .flatMap(reservation -> auditRepository.save(
                        AuditEntry.orderCreated(order.getId())))
                .thenReturn(order)
);
```

If the three SQL operations take 20 ms, 30 ms, and 10 ms, total SQL time is roughly 60 ms. Yet if the pipeline also waits 500 ms on an external service, the transaction can last over 560 ms. The transaction manager holds the connection for the entire transaction, so it is not returned to the pool after the first SQL statement.

Transaction duration covers:

- Starting the transaction and configuring the connection.
- Executing SQL statements.
- Awaiting dependent publishers.
- Running Java logic between operations.
- Waiting on locks or database scheduling.
- Committing/rolling back and cleaning up the transaction.

SQL duration measures only a specific statement or result group. Whenever transaction duration far exceeds total SQL duration, inspect gaps in the application pipeline and awaiting operations.

## 4. Connection Lifecycle in Spring Data R2DBC

When using Spring Data repositories, `R2dbcEntityTemplate`, or `DatabaseClient`, Spring manages acquiring and releasing connections along the operation lifecycle. Outside an active transaction, an operation typically acquires a connection to execute and releases it once the result is consumed or the publisher terminates.

With `R2dbcTransactionManager`, a connection is acquired when the transaction starts and bound to the reactive transaction context. Participating database operations in that context share the managed connection. The connection is released after commit/rollback and transaction cleanup finish.

Consequently, a prolonged transaction pins a connection far longer than a standalone SQL call. Never assume that once a repository emits an entity, the connection has returned to the pool if the publisher still sits inside an unfinished transaction.

## 5. Reactive Subscription Governs Execution Timing

Reactor publishers are typically lazy: calling a repository method constructs a publisher, while database work occurs upon subscription. Therefore, do not start timing when calling the method that returns `Mono`/`Flux` if you want execution duration.

Example:

```java
Mono<Order> publisher = orderRepository.findById(orderId);
```

This line does not necessarily acquire a connection yet. Subscription triggers execution:

```java
StepVerifier.create(publisher)
        .expectNextCount(1)
        .verifyComplete();
```

In an application, WebFlux or another subscriber manages subscription. Subscribing multiple times can execute the query multiple times, each with its own lifecycle. When timing operations, place instrumentation inside `Mono.defer`/`Flux.defer` so a fresh clock starts per subscription.

Never call `subscribe()` manually inside a service solely to kick off a query. Doing so detaches work from the caller's HTTP lifecycle, transaction context, cancellation, and error propagation.

## 6. Measuring End-to-End Transaction Duration with Micrometer

You can use a Micrometer `Timer` to measure from when the transaction publisher is subscribed until the transaction finishes. Place the timer outside `TransactionalOperator` so it includes execution as well as completion signals after commit/rollback.

Illustrative example:

```java
public Mono<Order> createOrder(Order order) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return transactionalOperator.transactional(
                        orderRepository.save(order)
                                .flatMap(saved -> auditRepository.save(
                                                AuditEntry.created(saved.getId()))
                                        .thenReturn(saved)))
                .doFinally(signal -> {
                    String outcome = switch (signal) {
                        case ON_COMPLETE -> "complete";
                        case ON_ERROR -> "error";
                        case CANCEL -> "cancel";
                        default -> "other";
                    };

                    sample.stop(meterRegistry.timer(
                            "app.r2dbc.transaction.duration",
                            "operation", "create-order",
                            "outcome", outcome));
                });
    });
}
```

`Mono.defer` starts a fresh `Timer.Sample` per subscription. `doFinally` wrapping the publisher returned by `transactionalOperator.transactional(...)` observes the terminal signal after the transaction operator handles completion, errors, or cancellation. Metric and tag names here are custom application metrics, not built-in Spring Boot names.

Never place order IDs, emails, arbitrary tenant IDs, or raw SQL in metric tags, as cardinality can explode and leak sensitive data. Use low-cardinality labels such as operation, outcome, and a controlled datasource label.

If a service uses `@Transactional`, you can instrument inside the method around the returned publisher, provided timing starts at subscription rather than publisher construction. When exact transaction-boundary timing is needed, explicit `TransactionalOperator` is often easier to instrument accurately.

## 7. Separating Time Inside vs. Outside the Transaction

You can measure the work body separately from the full transaction:

```java
public Mono<Order> createOrder(Order order) {
    return Mono.defer(() -> {
        Timer.Sample transactionSample = Timer.start(meterRegistry);

        Mono<Order> work = Mono.defer(() -> {
            Timer.Sample workSample = Timer.start(meterRegistry);

            return orderRepository.save(order)
                    .flatMap(saved -> auditRepository.save(
                                    AuditEntry.created(saved.getId()))
                            .thenReturn(saved))
                    .doFinally(signal -> workSample.stop(
                            meterRegistry.timer("app.r2dbc.transaction.work")));
        });

        return transactionalOperator.transactional(work)
                .doFinally(signal -> transactionSample.stop(
                        meterRegistry.timer("app.r2dbc.transaction.total")));
    });
}
```

The inner `work` metric measures the business publisher; the outer `total` metric measures until the transaction boundary terminates. The difference reflects begin/commit/rollback and cleanup overhead, though it is not an exact measurement of the underlying connection lease. To know precisely when the connection returns, inspect pool metrics or instrument connection lifecycle boundaries.

Do not attach `doFinally` only around a method call without subscription-scoped start:

```java
Mono<Order> wrongMeasurement = orderRepository.save(order)
        .doFinally(signal -> recordDuration());
```

That only works if the timer starts on the same subscription. If the timer started when the method was called and subscription happened later, the measurement includes pre-subscription idle delay and becomes misleading.

## 8. Measuring Individual SQL Statement Times

Transaction duration alone does not reveal which statement is slow. Measure query latency by operation type, repository/query name, or datasource. Options include:

- Micrometer observation/tracing integrated with Spring Framework and drivers where supported by your versions.
- Driver or database SQL and duration logging with sensitive-data redaction.
- Database query statistics such as `pg_stat_statements` on PostgreSQL.
- Custom instrumentation around `DatabaseClient` or repository methods for critical queries.
- Tracing spans correlating requests, transactions, and statements.

A query metric should cover from statement execution until result completion or cancellation—not just until the first row arrives when measuring full query streams.

For multi-row queries, separate:

- Time to first row: time until the first row arrives.
- Result consumption duration: time to consume the full result.
- Rows emitted: number of rows produced.
- Cancellation outcome: whether the result was cancelled before completion.

A query returning 100,000 rows may have a low time-to-first-row while result consumption drags on. Measuring only to the first row underestimates connection hold time.

## 9. Connection Pool Metrics Reveal Utilization Pressure

With `r2dbc-pool`, the pool can expose metrics such as acquired connections, allocated connections, idle connections, and pending requests. Exact metric names and registration depend on R2DBC Pool, Spring Boot, and Micrometer configuration.

Key quantities to monitor:

| Quantity | Interpretation |
| --- | --- |
| Acquired/borrowed | Connections currently borrowed by the application |
| Allocated | Physical connections currently created in the pool |
| Idle | Connections available to borrow |
| Pending | Requests waiting for the pool to grant a connection |
| Maximum allocated/acquired | Pool ceiling or reported peak usage |
| Acquire timeout count | Failures to obtain a connection within the timeout, if instrumented |

With Spring Boot Actuator, inspect registered metrics at `/actuator/metrics` when enabled and secured appropriately. Never assume identical metric names or tags across all versions; verify the live metric list in your application.

Pool gauges reflect point-in-time counts. High `acquired` counts do not directly report how long any single connection was held. To capture hold-time distributions, instrument acquire/release boundaries or use pool/driver observations where available.

## 10. Do Not Confuse `max-acquire-time` with Connection Hold Time

R2DBC Pool can configure wait timeouts for obtaining connections, for example:

```yaml
spring:
  r2dbc:
    pool:
      enabled: true
      initial-size: 5
      max-size: 30
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 20m
      max-life-time: 60m
```

Exact property names and duration formats depend on Spring Boot and R2DBC Pool versions. `max-acquire-time` caps how long a caller waits to borrow a connection. It does not limit how long the application can hold a connection once acquired.

Other concepts:

- `max-create-connection-time`: caps time to open a new physical connection.
- `max-idle-time`: caps how long an idle connection remains in the pool per pool settings.
- `max-life-time`: caps the physical lifetime of a pooled connection.
- `max-acquire-time`: caps how long a request waits to borrow a connection.

Never rely on `max-life-time` as a transaction timeout. A long-lived physical connection can be borrowed and returned many times; the hold time of an individual lease is a separate interval.

## 11. Using `EXPLAIN` and Database Statistics Properly

Database statistics help locate slow queries, locks, and server load. For example, PostgreSQL offers `EXPLAIN (ANALYZE, BUFFERS)` to inspect execution plans and runtime metrics on real data. `pg_stat_activity` shows active sessions/queries; `pg_stat_statements` aggregates statistics by query fingerprint when the extension is enabled.

These database-side tools do not tell you how long the application held a connection before or after a query. Pair database views with pool metrics and application tracing.

For example, a transaction holds a connection for 2 seconds while SQL takes 40 ms. Database query statistics show fast SQL; application traces reveal the service awaited a payment API for 1.8 seconds inside the transaction. Both perspectives complement each other.

Do not run `EXPLAIN ANALYZE` indiscriminately on production queries because it executes the statement and incurs overhead. Use it deliberately on representative queries or safe environments.

## 12. Recognizing Overly Broad Transactions

A transaction should encompass only database changes that must commit or roll back atomically. Never open a transaction at the start of a workflow and hold it across work that does not participate in database atomicity.

Example of an overly broad transaction:

```java
@Transactional
public Mono<Order> placeOrder(OrderCommand command) {
    return orderRepository.save(Order.pending(command))
            .flatMap(saved -> paymentClient.authorize(command.payment()))
            .flatMap(payment -> inventoryClient.reserve(command.items()))
            .flatMap(result -> orderRepository.markConfirmed(command.orderId()));
}
```

If payment or inventory services take 2 seconds, the database connection remains pinned throughout that wait. External services do not join the R2DBC transaction anyway, so holding the connection buys zero cross-system atomicity.

A usually better design is:

1. Short transaction: save order as `PENDING` and write an outbox command.
2. Commit and release the connection back to the pool.
3. Worker handles payment/inventory outside any database transaction.
4. Record each outcome in its own short transaction.
5. Transition the order to its final state or run compensation upon failure.

Transactional Outbox/Saga patterns preserve durable state without pinning connections while awaiting external services.

## 13. Avoid Network Calls Inside Transactions When Unnecessary

The code below pins a connection across an HTTP call:

```java
return transactionalOperator.transactional(
        customerRepository.save(customer)
                .flatMap(saved -> profileClient.refresh(saved.getId())
                        .thenReturn(saved)));
```

If refreshing the profile does not need atomicity with inserting the customer, move it outside the transaction:

```java
return transactionalOperator.transactional(
                customerRepository.save(customer))
        .flatMap(saved -> profileClient.refresh(saved.getId())
                .thenReturn(saved));
```

In the second approach, the insert transaction finishes before the HTTP call starts. However, if the HTTP call fails, the customer is already persisted. If the business requires guaranteeing the refresh happens, persist an outbox event in the same transaction and process it asynchronously instead of relying on a post-commit synchronous HTTP call.

Never split a transaction solely to cut hold time if doing so breaks business invariants. Clarify which steps require strict atomicity and which tolerate eventual consistency.

## 14. Streaming Queries Can Hold Connections for Long Durations

A `Flux<T>` from a repository emits rows progressively. The connection must stay open long enough for the driver to consume results and finish the query. If an HTTP endpoint streams to a slow client, backpressure prolongs consumption and keeps the connection pinned.

Example:

```java
@GetMapping(value = "/orders/export", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<OrderLine> export() {
    return orderRepository.findAll()
            .map(OrderLine::from);
}
```

This streams over HTTP, yet a huge query can keep a connection busy for the entire client download. If the endpoint also runs inside a reactive transaction, that transaction stays open until the stream completes or cancels.

For large exports, consider:

- Capping row counts and stream duration.
- Using keyset pagination in small batches so queries complete and connections release between batches.
- Never wrapping an entire HTTP stream in a long transaction unless an explicit snapshot requirement exists.
- Generating export files in a background job for subsequent download when datasets are massive.
- Handling client-disconnect cancellation cleanly and verifying the driver stops results promptly.

Never assume `Flux` automatically returns connections after each row. Connections usually stay busy as long as the statement's result is still being consumed.

## 15. Using Keyset Pagination to Shorten Connection Hold Times

For large lists, a single streaming query can hold a connection for a long time. Keyset pagination splits work into finite queries:

```sql
SELECT id, created_at, total
FROM orders
WHERE (created_at, id) < (:lastCreatedAt, :lastId)
ORDER BY created_at DESC, id DESC
LIMIT :pageSize;
```

The application fetches one page, processes it, and closes that query before requesting the next page. Without a spanning transaction across the whole export, connections return to the pool between pages.

This cuts continuous hold time while changing consistency semantics: separate pages may observe data at slightly different times. If a fixed snapshot is required, design an explicit cutoff/version or snapshot strategy. Do not keep a transaction open for minutes solely for a snapshot if it starves the pool; evaluate the trade-offs and data model.

## 16. Avoiding Excessive Concurrency on a Single Transaction Connection

An R2DBC transaction typically binds to a single connection. Using high `flatMap` concurrency to issue many parallel statements on that same connection does not necessarily improve throughput; the driver or database may serialize them or behave unexpectedly under concurrent execution.

Code requiring caution:

```java
return transactionalOperator.transactional(
        Flux.fromIterable(commands)
                .flatMap(repository::save, 32));
```

This attempts to run many inner publishers concurrently within the same transaction context. Sharing one transaction-bound connection can negate parallelism or hit driver-specific limitations.

When ordering matters, use `concatMap`:

```java
return transactionalOperator.transactional(
        Flux.fromIterable(commands)
                .concatMap(repository::save)
                .then());
```

If parallelism is required, break work into independent bounded-concurrency transactions and define failure semantics for partial chunk failures. Never crank up concurrency blindly to compensate for slow queries or an undersized pool.

## 17. Transaction Timeout vs. Query Timeout

Transaction timeouts, statement/query timeouts, pool acquire timeouts, and HTTP timeouts govern distinct scopes:

| Timeout | Scope |
| --- | --- |
| Pool acquire timeout | Wait time to borrow a connection |
| Connection creation timeout | Time to establish a physical connection |
| Statement/query timeout | Execution time of a single SQL statement, if supported by driver/database |
| Transaction timeout | Transaction duration per transaction manager/driver support |
| Reactor `.timeout(...)` | Allowed publisher runtime before emitting timeout error and cancelling upstream |
| HTTP/proxy timeout | Request/response duration or idle timeout on the network path |

Do not assume Reactor `.timeout` instantly cancels the running SQL statement on the database. It triggers an error/cancellation signal in the reactive pipeline; statement cancellation depends on driver and database support. Similarly, a proxy timeout does not roll back an already committed transaction.

Choose timeouts aligned with goals and verify via integration tests. When a timeout occurs during commit, the client may not know whether the database committed; retryable writes require idempotency keys or unique business keys.

## 18. Diagnostic Patterns from Combined Metrics

Reading metrics together narrows down bottlenecks faster:

| Observation | Likely Area to Investigate |
| --- | --- |
| Rising acquisition time, rising pending, acquired near max | Pool saturation; inspect hold time, concurrency, and max size |
| Rising hold time with low/flat SQL latency | Broad transactions, network calls, or application logic pinning connections |
| Rising transaction duration alongside rising SQL latency | Query plans, lock contention, database load, or DB network latency |
| Low time-to-first-row with very high result duration | Large results, slow client/downstream, or prolonged fetching/encoding |
| High pool acquired yet flat request throughput | Long hold times, locked queries, or ineffective concurrency |
| Acquire timeouts while database CPU is low | Undersized pool, leaked/long-held connections, or application-side limits |
| Fast database queries with slow HTTP responses | Encoding, proxy buffering, slow clients, or post-query logic |
| Transaction duration far above sum of SQL durations | Gaps in the application pipeline or external waits |
| Cancellations rising alongside hold times | Client disconnects or long streams; verify cleanup and driver cancellation |

These are diagnostic hypotheses, not automatic conclusions. Cross-check traces, logs, and database activity before changing pool sizes or transaction boundaries.

## 19. Using Tracing to Pinpoint Where Connections Are Held

Distributed tracing breaks a request down into spans:

```text
HTTP POST /orders                 950 ms
  R2DBC transaction create-order  900 ms
    INSERT order                   18 ms
    SELECT inventory               12 ms
    HTTP payment authorize        820 ms
    UPDATE order                    9 ms
    COMMIT                         25 ms
```

The trace shows SQL accounts for only a small fraction; the HTTP payment call inside the transaction drives almost all of the transaction duration. Moving payment outside the transaction or switching to an outbox/saga lets the connection release much earlier.

Spans should use stable operation names and safe tags such as datasource label, outcome, and transaction type. Never attach raw SQL parameters, customer data, or tokens to spans. Use trace IDs to correlate across logs and metrics.

If instrumentation emits spans only for queries and omits transaction spans, gaps between queries stay hidden. Add transaction-boundary spans/timers for critical use cases.

## 20. Measuring Connection Hold Time More Precisely

Pool gauges report how many connections are borrowed, not necessarily individual acquire/release timestamps. To capture p50/p95/p99 hold-time distributions, instrument lease boundaries.

Options:

- Use R2DBC Pool or instrumentation library metrics/observations if your version exposes acquire/release timings.
- Wrap `ConnectionFactory` with a decorator recording timestamps when `create()` emits a connection and when `Connection.close()` completes.
- Use tracing/driver instrumentation emitting acquire and release spans.
- In custom SPI code managing connections directly, measure around `ConnectionFactory.create()` and `Connection.close()`.

When writing a decorator, preserve full SPI semantics: transactions, metadata, statements, batches, validation, close, cancellation, and errors. Never slap on a naive `close()` wrapper that drops other `Connection` interfaces or methods. Prefer built-in pool/driver metrics unless custom instrumentation is truly required.

Conceptual SPI example:

```java
Mono.usingWhen(
        Mono.defer(() -> {
            long acquireStarted = System.nanoTime();
            return Mono.from(connectionFactory.create())
                    .doOnNext(connection ->
                            metrics.recordAcquireTime(
                                    System.nanoTime() - acquireStarted));
        }),
        connection -> executeWork(connection),
        connection -> Mono.from(connection.close())
                .doFinally(signal -> metrics.recordRelease(signal)),
        (connection, error) -> Mono.from(connection.close())
                .doFinally(signal -> metrics.recordRelease(signal)),
        connection -> Mono.from(connection.close())
                .doFinally(signal -> metrics.recordRelease(signal))
);
```

This is a conceptual skeleton; measuring lease hold time requires storing the acquire timestamp inside a resource wrapper paired with the connection and computing elapsed time once close finishes. With `DatabaseClient`/repositories, Spring manages acquire/release so services must not wrap connections manually; apply a `ConnectionFactory` decorator or pool-level instrumentation instead to measure accurately while keeping lifecycles intact.

## 21. Separating Connection Creation Time from Pool Wait Time

When the pool has no idle connections, it may open a new connection if below max size. Acquisition time can include both waiting for a pooled connection and establishing a new connection.

Distinguish between:

- Pool wait: time waiting for a connection to be returned or a slot to open.
- Connection creation: time opening the physical connection, authenticating, and initializing the session.
- Validation: time validating the connection before lending it, if configured.
- Lease duration: time the application holds the connection after borrowing it.

If connection creation is slow, check DNS, TLS, database connection limits, network, and authentication. If pool wait is high while creation time is low, inspect hold time and pool capacity. Never raise `max-size` when the database is already hitting connection or CPU limits; opening more connections worsens contention.

## 22. Estimating Pool Demand from Throughput and Hold Time

A simple estimate from Little's Law:

\[
N \approx \lambda \times W
\]

Where:

- (N) is the average number of borrowed connections.
- (lambda) is the rate of operations needing connections (per second).
- (W) is the average connection hold time (seconds).

For example, if the system processes 80 transactions per second and each transaction holds a connection for an average of 0.25 seconds:

\[
N \approx 80 \times 0.25 = 20
\]

Roughly 20 connections is the average usage under those assumptions—not the `max-size` setting. Add headroom for bursts, tail latency, background tasks, and other queries. Inspect p95/p99 hold times to understand long-lease spikes while respecting database limits.

Across 8 application instances with `max-size` 30 each, theoretical connections reach 240 before counting jobs, migrations, and operational tools. Size pools system-wide rather than per pod in isolation.

This is an initial estimate, not a substitute for load testing. Larger pools do not always boost throughput; databases often perform better with fewer active connections and lower lock contention.

## 23. Avoid Holding Connections While Awaiting Clients

A reactive transaction must never span waiting on a user, another HTTP request, or an unbounded stream. Example:

```java
return transactionalOperator.transactional(
        orderRepository.findById(orderId)
                .flatMap(order -> confirmationGateway.waitForUser(order)
                        .flatMap(confirmed -> orderRepository.save(
                                order.withConfirmed(confirmed)))));
```

If `waitForUser` takes several minutes, the transaction and connection stay pinned for minutes. Persist the awaiting state in a short transaction, close the transaction, and handle the callback/user confirmation in a new request with its own short transaction.

Transactions protect atomic database step sequences; they are not workflow engines waiting on external actors.

## 24. Impact of Locks and Long Transactions

Long transactions can hold locks or snapshots longer depending on database, isolation level, and operation type. Consequences can include:

- Other transactions blocking on locks.
- Higher deadlock probability when multiple transactions hold locks longer in differing orders.
- Retaining older row versions longer in MVCC engines.
- Disrupting cleanup/vacuum or transaction ID management depending on the database.
- Longer connection pool occupancy, forcing other requests to queue.

Not every long transaction locks every row; read/write mode, isolation level, and engine internals determine exact behavior. Still, long transactions widen the window during which resources and snapshots stay pinned, so monitor `idle in transaction`, lock waits, and transaction age in the database whenever symptoms arise.

## 25. Distinguishing `idle in transaction` from Pool Idle Connections

These two states are completely different:

- **Idle connection in pool:** a connection not currently borrowed by the application and ready to serve another request.
- **Idle in transaction:** a database session inside an open transaction that is currently executing no statements; the application may be waiting on another publisher or external logic.

An `idle in transaction` connection remains pinned by that transaction and cannot be lent by the pool to another request. On PostgreSQL, inspect sessions in `pg_stat_activity` for `idle in transaction` states.

If many long-lived `idle in transaction` sessions appear, look for gaps between SQL calls in services, HTTP calls inside transactions, non-terminating publishers, or slow response streams. Never confuse them with healthy idle connections in the pool.

## 26. Controlling Connection Leaks and Cleanup

With repositories/`DatabaseClient`, Spring manages connection lifecycles. With direct R2DBC SPI usage, the application is responsible for releasing connections properly.

Resource management example using `usingWhen`:

```java
public Mono<Void> runDirectStatement() {
    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement(
                        "DELETE FROM expired_token WHERE expires_at < CURRENT_TIMESTAMP");

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.getRowsUpdated()))
                        .then();
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

`usingWhen` defines cleanup for completion, error, and cancellation. Never acquire a raw connection and forget `close()`. Never manually close a connection managed by Spring's transaction manager in the middle of a transaction.

If pool `acquired` climbs continuously and never drops after requests finish, inspect raw SPI code, unsubscribed or non-terminating publishers, cleanup callbacks, and driver behavior. A long-held connection is not always a leak; distinguish legitimate long hold times from connections that never release.

## 27. Cancellation and Release Timing

When a subscriber cancels a publisher, Spring and the driver cancel the statement and release the connection according to lifecycle hooks. However, cancellation is asynchronous; stopping the physical query and completing cleanup may not happen instantaneously.

With HTTP streams, clients can drop sockets. WebFlux cancels the subscription, yet the database driver may need time to halt the result. Measure the lag from cancellation until the connection returns to the pool on endpoints prone to mid-stream disconnects.

Do not use `doOnCancel` as your connection-release mechanism when Spring or `usingWhen` already manages resources. Reserve that callback for metrics, logging, or cancelling application-owned resources.

## 28. Optimizing After Identifying Root Causes

Choose fixes backed by metrics and traces:

| Confirmed Root Cause | Improvement Path |
| --- | --- |
| Slow queries from scans/sorts | Optimize SQL, indexes, filters, projections, and execution plans |
| High lock waits | Shorten transactions, standardize lock ordering, reduce contention |
| Transaction contains HTTP calls | Move calls outside transactions or use outbox/saga |
| Oversized streaming queries | Bound results, use keyset pagination, move exports to background jobs |
| High pool wait due to long hold times | Shorten connection leases and transactions before raising pool size |
| Undersized pool with spare DB headroom | Tune `max-size` after load testing while budgeting across all instances |
| Slow connection creation | Use appropriate pooling; inspect network/TLS/credentials and DB limits |
| Unfinished publishers / slow cancel cleanup | Fix pipelines, timeouts/cancellations, and resource lifecycles |
| Excessive `flatMap` concurrency | Bound concurrency or serialize operations sharing a connection |
| Only a few endpoints hold connections long | Isolate separate use cases, queries, or transaction boundaries |

Never raise pool size to cover up a transaction holding a connection for several seconds. That often shifts the bottleneck straight to the database while inflating session counts.

## 29. Testing and Load-Testing Connection Hold Times

Functional tests verifying correct return values do not evaluate hold times. Combine:

1. Service unit tests verifying publishers do not invoke external services inside transaction boundaries.
2. Integration tests with a real R2DBC driver verifying commit, rollback, and cleanup.
3. Cancellation tests verifying connections release when clients/subscribers cancel.
4. Concurrent load tests monitoring acquired, idle, pending, and acquisition latency.
5. Large-stream tests with fast and slow clients to measure connection hold times.
6. Traces of long transactions comparing total SQL duration against transaction duration.
7. Database session/lock checks for `idle in transaction` sessions.

Example using `StepVerifier` to confirm publisher completion:

```java
StepVerifier.create(orderService.createOrder(command))
        .expectNextMatches(order -> order.getId() != null)
        .verifyComplete();
```

This verifies the publisher completes normally; pool metrics, traces, or pool instrumentation reveal when the connection actually releases. Do not rely on `Thread.sleep` to guess when connections return. To verify pool release in tests, read pool metrics or run a controlled follow-up operation after publisher completion.

During load tests, ramp concurrency incrementally while watching throughput, p95/p99 latency, pending acquires, DB CPU/locks, and timeouts. When throughput stalls while pending rises, the system has hit either database capacity or connection-lease limits.

## 30. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Measuring only SQL execution time | Misses connection time held between queries | Measure transaction duration and connection hold time separately |
| Timing from repository method invocation | Publisher may not have been subscribed to yet | Start timers inside `defer` upon subscription |
| Confusing acquisition time with hold time | Fixes the wrong pool contention cause | Measure pool wait and lease duration separately |
| Assuming transaction duration equals query duration | Overlooks HTTP calls, lock waits, and app logic | Compare transaction spans against SQL spans |
| Raising pool `max-size` as soon as pending rises | Can overload the database further | Inspect hold time, queries, concurrency, and DB limits first |
| Treating `max-acquire-time` as a hold-time cap | Connections can still stay held indefinitely after borrow | Configure transaction/query timeouts and shorten hold times |
| Making HTTP calls inside transactions | Pins connections while awaiting network I/O | Split transactions or use outbox/saga |
| Streaming unbounded results inside transactions | Connections held indefinitely | Never wrap event streams in long transactions |
| Calling `collectList()` on large datasets | Raises memory usage and prolongs query consumption | Process via `Flux` or keyset batches |
| High `flatMap` concurrency in one transaction | Contention on a single connection or unpredictable driver behavior | Use `concatMap` or bounded independent transactions |
| Reading `acquired` gauge as hold duration | Gauges do not show lease age | Use acquire/release instrumentation or tracing |
| Wrapping connections manually without cancel cleanup | Connection leaks | Use `usingWhen` or lifecycle-preserving decorators |
| Using `doOnCancel` instead of proper release | Resources may fail to close cleanly | Let Spring or `usingWhen` manage cleanup |
| Measuring publisher creation instead of subscription | Metrics ignore actual runtime | Use `Mono.defer`/`Flux.defer` with per-subscription timers |

## 31. Process for Evaluating an R2DBC Endpoint

When an endpoint exhibits high latency or rising pool pending counts, follow these steps:

1. Record end-to-end request latency and throughput per endpoint.
2. Measure pool acquisition time, acquired/idle/pending counts, and acquire timeouts.
3. Measure transaction duration from subscription to commit/rollback completion.
4. Measure connection hold time via pool/driver instrumentation or acquire/release tracing.
5. Measure individual SQL spans, time-to-first-row, and result consumption durations.
6. Compare total SQL duration against transaction duration to uncover application-side waits.
7. Inspect network calls, schedulers, `collectList`, long streams, `flatMap` concurrency, and non-terminating publishers.
8. Inspect database query plans, lock waits, and `idle in transaction` sessions.
9. Adjust transaction boundaries, queries, pagination, or pool settings according to confirmed causes.
10. Re-run load tests and compare p50/p95/p99, throughput, pending acquires, connection counts, and database load.

## 32. Practical Principles

- Distinguish pool acquisition time, connection hold time, transaction duration, SQL duration, and request latency.
- Start measuring reactive work on publisher subscription, not method invocation.
- Measure transactions outside `TransactionalOperator` to capture commit/rollback and cleanup boundaries.
- Measure SQL separately and compare against transaction duration to find application gaps between queries.
- Track pool acquired/allocated/idle/pending; remember gauges do not measure hold duration directly.
- Verify exact metric and tag names in your R2DBC Pool/Spring Boot version rather than assuming cross-version uniformity.
- Never confuse `max-acquire-time`, `max-idle-time`, or `max-life-time` with transaction/lease limits.
- Avoid external service calls or user waits inside database transactions when atomicity is unnecessary.
- Avoid holding transactions or connections open across long HTTP streams or unbounded exports.
- Use bounded keyset pagination/batches when appropriate and explicitly accept the consistency semantics.
- Cap concurrency, prefetch, and buffers; avoid competing parallel statements on a single transaction connection.
- Use `usingWhen` for raw SPI connections with cleanup on complete, error, and cancel.
- Correlate lock waits, `idle in transaction`, query plans, and connection creation with application metrics.
- Size pools across total instance counts within database limits; never enlarge pools to hide long hold times.
- Test commits, rollbacks, cancellation, and load using a production-compatible driver and database.

## 33. Conclusion

Evaluating R2DBC performance requires separating connection wait times, connection hold times, transaction lifetimes, and individual SQL execution times. High pool acquisition points to requests waiting on connections; high hold time shows connections stay borrowed too long; transaction duration exceeding SQL duration usually exposes application waits or logic inside transactions.

Instrument around reactive subscriptions, combining Micrometer and tracing with pool metrics and database statistics. Reactive transactions pin connections until commit/rollback and cleanup finish; consequently, network calls, user waits, long HTTP streams, or unclosed publishers can exhaust the pool even when every SQL query is fast. Shortening transactions, bounding results and concurrency, paginating appropriately, and tuning pools from real measurements improve throughput without shifting unnecessary pressure onto the database.
