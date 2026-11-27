# Measuring Query Duration, Pool Acquire Time, and Transaction Duration

## 1. Why Measure These Three Durations Separately?

In a Spring Data Relational R2DBC application, a request can take a long time before returning a result. The root cause is not necessarily in the SQL statement. A request might wait for a connection from the pool, wait for the database to process, read a long result stream, perform mapping, or hold a transaction while running application logic.

The three durations that should be observed separately are:

- **Query duration:** the execution time of a database operation according to the chosen measurement boundary. At the application layer, this usually includes the time from when the publisher starts running until results are completely consumed; at the driver/proxy or database layer, the measurement may focus strictly on the statement.
- **Pool acquire duration:** the time from when the application requests a connection from the pool until it receives a connection or the request fails/times out.
- **Transaction duration:** the duration of the entire transaction, from when the transaction begins until commit or rollback completes according to the measurement boundary.

These three measurements answer different questions:

| Measurement | Question Answered |
|---|---|
| Query duration | How long did the SQL operation and reading results take? |
| Pool acquire duration | Did the application have to wait for a connection because the pool was busy? |
| Transaction duration | How long did an atomic unit of work hold the transaction/connection? |

For example, a query may run in just 15 ms, yet the request takes 400 ms because waiting on the pool took 300 ms. A transaction may take 2 seconds even though total SQL time is only 100 ms because the code waited on another service while the transaction remained open.

If you only measure full request time, it is hard to know whether to optimize the query, resize the pool, shorten the transaction, or limit concurrency. Separating these measurements helps pinpoint the exact bottleneck.

## 2. Breaking Down the Path of an R2DBC Operation

A repository operation typically goes through multiple stages:

~~~text
Caller subscribe()
       |
       v
Reactive pipeline starts
       |
       v
Request connection from ConnectionFactory
       |
       v
Wait for pool acquire (if pool is busy)
       |
       v
Receive connection
       |
       v
Send statement via R2DBC driver
       |
       v
Database executes SQL / locks / I/O
       |
       v
Read results and map rows
       |
       v
Publisher complete / error / cancel
       |
       v
Return connection to pool
~~~

For a simple query outside a transaction, the connection can be released once the operation completes. For a reactive transaction, the connection is typically held for the duration of the transaction, including between statements.

The intervals can be categorized as:

- Wait time before obtaining a connection.
- Statement round-trip and database execution time.
- Time to receive the full result stream.
- Application-side mapping/conversion time.
- Wait time between operations inside a transaction.
- Commit or rollback time.

Not every tool can measure all of these intervals. A timer wrapping a repository publisher typically measures application-observed duration, whereas a statement listener measures at the driver/proxy layer, and database statistics measure from the server perspective.

When reading dashboards, you must know exactly where the timer starts and stops. Two charts both named query duration with different boundaries cannot be compared directly.

## 3. How Lazy Publishers Affect Timing Measurement

Reactive publishers are typically lazy. Calling a repository method constructs a publisher; the SQL statement usually executes only when the publisher is subscribed to.

Example:

~~~java
Mono<Customer> query = customerRepository.findById(42L);
~~~

If you start a stopwatch when creating the `query` variable and wait before subscribing, the measured duration includes the idle time while the publisher has not executed yet. That is not query duration.

Start measurement inside `Mono.defer` or `Flux.defer` so each subscription gets its own measurement:

~~~java
return Mono.defer(() -> {
    long started = System.nanoTime();

    return customerRepository.findById(id)
            .doFinally(signal -> {
                long elapsed = System.nanoTime() - started;
                recordDuration(elapsed);
            });
});
~~~

`System.nanoTime()` is suitable for measuring elapsed durations because it is a monotonic clock unaffected by system wall-clock adjustments. Use `System.currentTimeMillis()` for recording event timestamps, not as a stopwatch for duration.

If a publisher is subscribed to multiple times, `defer` creates a new measurement per subscription. This is crucial when a repository publisher is cold and each subscription can re-execute SQL.

## 4. Measuring Operation Duration at the Repository Layer

A straightforward approach is to measure from when the repository publisher is subscribed to until it emits a terminal signal.

Example with `Mono`:

~~~java
public Mono<Customer> findCustomer(Long id) {
    return Mono.defer(() -> {
        long started = System.nanoTime();

        return customerRepository.findById(id)
                .doFinally(signal -> {
                    long elapsedNanos =
                            System.nanoTime() - started;

                    log.debug(
                            "customer.findById completed in {} ms, signal={}",
                            elapsedNanos / 1_000_000.0,
                            signal
                    );
                });
    });
}
~~~

This code illustrates the repository publisher timing boundary. It can include:

- Connection pool wait time.
- Time to send and execute SQL.
- Time to receive results.
- Mapping rows to entities.
- Driver overhead and any operators placed before `doFinally`.

It is not pure database time. If you need to separate pool wait and statement execution, add instrumentation at the `ConnectionFactory`/pool and driver/proxy or database layers.

For `Flux`, the timer should stop when the entire stream completes, emits an error, or is cancelled. Do not stop the timer on the first row if the goal is to measure reading the full result set.

### 4.1. Distinguishing Time-to-First-Row and Time-to-Complete

A `Flux` querying 100,000 rows might emit its first row after 20 ms yet take 3 seconds to read completely. Both metrics are meaningful:

- **Time-to-first-row:** time from subscription to the first element. Useful for streaming endpoints and responsiveness.
- **Time-to-complete:** time from subscription until the entire `Flux` completes. Useful for exports, batch jobs, and total result-stream hold time.

Example:

~~~java
public Flux<Customer> streamCustomers() {
    return Flux.defer(() -> {
        long started = System.nanoTime();
        AtomicBoolean firstRow = new AtomicBoolean();

        return customerRepository.findAll()
                .doOnNext(customer -> {
                    if (firstRow.compareAndSet(false, true)) {
                        long firstRowNanos =
                                System.nanoTime() - started;
                        recordFirstRow(firstRowNanos);
                    }
                })
                .doFinally(signal -> {
                    long totalNanos =
                            System.nanoTime() - started;
                    recordStreamDuration(totalNanos, signal);
                });
    });
}
~~~

If the `Flux` completes empty, there is no time-to-first-row. Record empty outcomes separately instead of leaving the first-row metric without data and misinterpreting it as the query never running.

If downstream processes each row slowly, timer placement affects the result. Placing the timer close to the repository publisher measures reading from the repository; placing the timer after processing/export operators measures downstream work as well. Name the metric to reflect that exact boundary.

## 5. Recording Duration with a Micrometer Timer

In Spring Boot applications, Micrometer is the standard choice for recording durations and exporting metrics to observability systems such as Prometheus or an equivalent backend.

A `Timer` typically provides:

- Recording count.
- Total time.
- Maximum value over a window/implementation.
- Histograms or percentiles when configured.
- Tags to categorize metrics by operation and outcome.

Simple example using a pre-registered `Timer`:

~~~java
@Component
class CustomerRepositoryMetrics {

    private final Timer findByIdTimer;

    CustomerRepositoryMetrics(MeterRegistry registry) {
        this.findByIdTimer = Timer.builder("app.r2dbc.repository")
                .description("Repository publisher duration")
                .tag("operation", "customer.findById")
                .register(registry);
    }

    Mono<Customer> measureFindById(
            Long id,
            CustomerRepository repository) {

        return Mono.defer(() ->
                Mono.fromCallable(System::nanoTime)
                        .flatMap(started ->
                                repository.findById(id)
                                        .doFinally(signal -> {
                                            long elapsed =
                                                    System.nanoTime() - started;
                                            findByIdTimer.record(
                                                    elapsed,
                                                    TimeUnit.NANOSECONDS
                                            );
                                        })
                        )
        );
    }
}
~~~

This example shows subscription-scoped timer placement; in production code you can use a helper to avoid repetition and classify outcomes. With reactive operations, never subscribe separately just to record metrics. Attach operators to the returned publisher.

Another option is `Timer.Sample` to select the `Timer`/tags at completion time:

~~~java
Mono<Customer> measuredFind(Long id) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);
        AtomicReference<String> outcome =
                new AtomicReference<>("cancelled");

        return repository.findById(id)
                .doOnSuccess(customer ->
                        outcome.set(customer == null ? "empty" : "success"))
                .doOnError(error -> outcome.set("error"))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        outcome.set("cancelled");
                    }

                    Timer timer = Timer.builder("app.r2dbc.repository")
                            .tag("operation", "customer.findById")
                            .tag("outcome", outcome.get())
                            .register(meterRegistry);

                    sample.stop(timer);
                });
    });
}
~~~

In the `Mono` example, `doOnSuccess` receives `null` when the publisher completes empty. `doFinally` handles complete, error, and cancel. You can add tags for operation types, but keep tag values bounded.

For `Flux`, use `doOnComplete` to mark success, `doOnError` for error, and `doFinally` to record duration/cancel. Do not use `doOnNext` as the timer stop point because a `Flux` can emit multiple elements.

### 5.1. Do Not Build Metric Names or Tags from Dynamic Data

Do not use the following values as metric tags:

- Customer ID or Order ID.
- Email, username, or unbounded tenant IDs.
- Full SQL statements.
- Bind parameters.
- Trace IDs or request IDs.
- URLs containing path parameters.

These values create very high cardinality, increasing memory usage and costs in the metrics system. Use stable operation names such as `customer.findById`, `order.save`, or bounded query groups. Trace IDs belong in logs/traces, not metric labels.

## 6. Measuring Connection Pool Acquire Duration

Pool acquire duration is the time from when code requests a connection until the pool grants a connection or returns an error.

This metric is essential when:

- Acquired connections frequently equal `max-size`.
- Pending acquire rises.
- Requests wait a long time for connections.
- Connection acquisition timeouts occur frequently.
- Database active sessions are not high yet the application is still slow.

Distinguish between:

- **Acquire latency:** time spent waiting for a connection from the pool.
- **Connection creation latency:** time to establish a new physical connection when the pool needs to open one.
- **Query duration:** time to execute an operation after obtaining a connection.
- **Connection hold duration:** time a connection is held before returning to the pool.

A pool can exhibit high acquire latency because no idle connections remain. Yet the root cause could be slow queries, long transactions, or `Flux` streams holding connections too long.

### 6.1. Observing Pool States

Pool metrics typically provide or allow deriving states such as:

| Metric | Meaning |
|---|---|
| acquired / in-use | Connections currently borrowed |
| allocated | Total connections allocated by the pool |
| idle | Idle connections |
| pending acquire | Requests waiting for a connection |
| acquire timeout | Number of times requests failed to get a connection within the deadline |
| acquire duration | Wait time to obtain a connection if supported by instrumentation |
| connection creation duration | Time to open a new connection if measured |

Exact metric names depend on Spring Boot, `r2dbc-pool`, and metrics backend versions. Inspect the metrics actually exposed by your application instead of assuming all versions use the same names.

Pool gauges are point-in-time values. They help detect saturation, but do not tell you how long each request waited. To measure acquire latency, you need a timer at the acquisition boundary or a pool-provided metric recorder.

### 6.2. Measuring at the ConnectionFactory Boundary

Conceptually, you can measure from when `ConnectionFactory.create()` is called until the publisher emits a connection:

~~~java
Mono<Connection> acquireMeasured(ConnectionFactory factory) {
    return Mono.defer(() -> {
        long started = System.nanoTime();

        return Mono.from(factory.create())
                .doOnSuccess(connection -> {
                    long elapsed = System.nanoTime() - started;
                    recordPoolAcquireSuccess(elapsed);
                })
                .doOnError(error -> {
                    long elapsed = System.nanoTime() - started;
                    recordPoolAcquireFailure(elapsed);
                });
    });
}
~~~

This illustrates the acquisition boundary, not an arbitrary replacement for Spring's `ConnectionFactory`. If repositories/transaction managers use a different `ConnectionFactory`, this timer will not measure the connections repositories actually borrow.

To apply application-wide, instrument the exact pooled `ConnectionFactory` used by Spring Data and the transaction manager, via pool metrics, Micrometer integration, or an R2DBC SPI-compatible decorator/proxy. Never open a separate connection solely to measure and infer repository wait time.

Measuring at `create()` typically reflects the time from requesting a connection until it is emitted to the caller. Depending on the pool, this may include slot waiting, validation, and creating a new connection. Label the metric clearly as acquisition latency, rather than assuming it is pure queue wait.

### 6.3. Acquire Timeout and Pending Queue

When the pool reaches `max-size`, new requests may wait in the acquire queue. If they exceed the configured deadline, the operation fails with an acquire timeout error.

Common symptoms:

- Acquired persistently near `max-size`.
- Idle near 0.
- Pending acquire rising.
- Acquire duration p95/p99 rising.
- Acquire timeouts rising.

Do not immediately increase `max-size`. First inspect connection hold duration, query duration, transaction duration, replica count, and the database connection budget. If the database is already saturated, adding connections can make queries even slower.

## 7. Measuring Statement Execution Time at the Driver Layer

A timer wrapping a repository publisher is useful for the application perspective, but it usually includes acquisition and result reading. If you need to isolate statement time, instrument at the R2DBC driver or proxy layer.

One option is an R2DBC-compatible proxy library to observe statement/execution lifecycles. Listeners can record milestones such as:

- Before statement execution.
- After statement completion.
- Execution errors.
- Statement info and affected row counts if provided by the proxy.

Exact implementation depends on the library and version. When selecting a proxy, verify it supports your application's R2DBC SPI and driver versions.

Client-side statement measurements may include network round-trip, database response, and result receipt as defined by the proxy. It does not necessarily equal the CPU time the database spent solely on SQL.

### 7.1. Comparing Three Perspectives

| Measurement Point | Typically Includes | Does Not Necessarily Include |
|---|---|---|
| Timer around repository publisher | Acquire, statement, fetch, mapping inside publisher | Downstream logic after the timer |
| Statement proxy/driver | Statement execution and result lifecycle per proxy | Pool wait time before getting a connection |
| Database server statistics | Statement duration as recorded by the server | Application/pool queuing and wait time |

Do not add these measurements together. They can cover overlapping intervals across different layers.

### 7.2. Determining Completion Time for Flux Queries

For a `SELECT` returning multiple rows, statement execution may finish before the full result stream is consumed. A listener stopping when `execute` returns a result object can report a different time than a timer running until the `Flux` completes.

For streaming systems, measure separately:

- Time to send statement / receive initial response.
- Time to first row.
- Time to read the entire result stream.
- Downstream processing completion time if needed by the business case.

Metric names must accurately reflect the stop boundary.

## 8. Measuring Reactive Transaction Duration

Transaction duration measures the entire scope of a transaction, not just individual SQL statements. It can include:

- Connection acquisition.
- Transaction begin.
- One or more statements.
- Wait time between statements.
- Application logic running inside the transaction.
- Commit or rollback.

With `TransactionalOperator`, you can wrap the publisher and measure the subscription lifecycle:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work =
            orderRepository.save(toOrder(command))
                    .flatMap(saved ->
                            orderLineRepository.saveAll(toLines(saved.id(), command))
                                    .thenReturn(saved)
                    );

    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return transactionalOperator.transactional(work)
                .doOnError(error ->
                        recordTransactionOutcome("error"))
                .doFinally(signal -> {
                    if (signal == SignalType.CANCEL) {
                        recordTransactionOutcome("cancelled");
                    }

                    sample.stop(transactionTimer);
                });
    });
}
~~~

This example measures from when the subscriber starts the `TransactionalOperator`-wrapped publisher until the observed terminal signal. Depending on operator placement and transaction manager cleanup semantics, if you need exact commit/rollback completion timing, use transaction synchronization or transaction manager instrumentation instead of relying solely on a service-layer timer.

With `@Transactional`, you can measure the publisher returned from the service at the caller boundary. Start the clock inside `Mono.defer` so you do not count time spent waiting for subscription.

### 8.1. Transaction Duration Differs from Sum of Query Durations

Suppose a transaction executes three queries:

| Component | Duration |
|---|---:|
| Acquire connection | 20 ms |
| Query 1 | 15 ms |
| Application logic | 300 ms |
| Query 2 | 20 ms |
| Query 3 | 10 ms |
| Commit and cleanup | 5 ms |

The transaction can last around 370 ms even though total statement time is only 45 ms. The connection was held during the 300 ms of application logic.

This is why transaction duration is a distinct metric. If transactions are long, check whether non-atomic work sits inside the transaction boundary.

### 8.2. Do Not Hold Transactions While Waiting on External Services

Avoid HTTP calls, sending emails, waiting on messages, or long CPU processing inside a transaction unless strictly necessary. Those operations extend connection hold time and can hold locks or snapshots.

Instead of a single long transaction, consider:

- Splitting into short transactions.
- Using sagas or workflows with compensating steps.
- Using a transactional outbox for publishing messages.
- Moving CPU-heavy work outside the transaction.
- Introducing explicit intermediate domain states.

Do not split a transaction if business rules truly require atomicity across database operations; define boundaries based on data integrity.

## 9. Measuring Commit, Rollback, and Cancellation

Not every transaction finishes successfully. Classify outcomes:

- Successful commit.
- Rollback due to error.
- Rollback due to cancellation.
- Transaction begin/commit/rollback failure.
- Acquire or begin failure before any statement runs.

Recording only a `Timer` without outcome tags makes it hard to distinguish successful transactions from failed or cancelled ones.

In reactive transactions, cancellation is an important signal. When a subscriber cancels, the transaction manager typically needs to clean up and roll back the open transaction. However, when downstream receives cancellation does not necessarily mean the database has finished rolling back. If you need accurate metrics for cleanup/rollback time, instrument the transaction manager or after-completion synchronization callbacks.

Never record cancellation as success. Also do not assume every request timeout rolls back a transaction that already committed earlier.

## 10. Distinguishing Query Duration, Connection Hold Duration, and Transaction Duration

Three durations are frequently confused:

- **Query duration:** duration of a statement/result operation measured at a specific boundary.
- **Connection hold duration:** duration a connection is held from acquisition to release.
- **Transaction duration:** duration a transaction exists from begin to completion.

A single transaction can run multiple queries on the same connection:

~~~text
Transaction duration
  ├── Acquire connection
  ├── Query A
  ├── Application work
  ├── Query B
  ├── Application work
  ├── Query C
  └── Commit / rollback / cleanup
~~~

Connection hold duration is usually close to transaction duration if the connection is bound for the entire transaction, though the two concepts are not always identical across all implementations or nested/resource-management cases.

Outside a transaction, a long `Flux` can also hold a connection while reading results. Thus, connection hold duration can be long even without an explicit transaction.

Measuring all three reveals cases where queries are fast yet connections are held for a long time.

## 11. Using Database Server Metrics for Cross-Checking

Client-side instrumentation tells you how long the application waited. Database server metrics tell you what the database was actually doing during that period.

For PostgreSQL, inspect sources such as:

- `pg_stat_activity`: active sessions, states, and wait events.
- `pg_stat_statements`: aggregated statistics per normalized query if the extension is enabled.
- Slow query logging or log duration.
- `EXPLAIN (ANALYZE, BUFFERS)` on suitable queries in a safe environment.
- Lock monitoring and transaction age.

For MySQL, inspect Performance Schema, statement digests, process list, lock waits, and the slow query log. Other RDBMS engines provide equivalent tools.

Server-side duration does not necessarily match client-side duration. For example:

- Client measures 200 ms.
- Server records query execution of 40 ms.
- The remainder may be pool acquire, network, driver, result transfer, mapping, or client stream consumption time.

Conversely, if server-side duration is high with lock waits, tuning the application pool will not solve the root cause.

## 12. Correlating Metrics Across Layers

To find root causes, place charts side by side over the same time range:

- Request latency p50/p95/p99.
- Repository/query duration.
- Pool acquire duration.
- Pool acquired/idle/pending.
- Transaction duration.
- Database active sessions.
- Database CPU/I/O.
- Lock waits/deadlocks.
- Error and timeout rates.

Diagnostic patterns:

| Observation | Possible Cause | Investigation Direction |
|---|---|---|
| High acquire duration, low query duration | Busy pool or long connection holds | Check pending, transactions, and streams |
| Low acquire duration, high query duration | Slow SQL, locks, network, or large fetch | Check query plans and server metrics |
| Low query duration, high transaction duration | Application logic or waits between queries | Narrow transaction boundaries |
| Acquired consistently near max, rising pending | Pool saturation | Check hold time and DB headroom |
| Pool has idle yet requests are slow | Bottleneck in SQL, app, or network | Compare statement and request timings |
| High DB CPU, latency rises when pool grows | Saturated database | Reduce concurrency, optimize queries |
| Long transaction duration, rising idle-in-transaction | Transaction waiting on external work | Move non-DB I/O out of transactions |
| High query p99 yet low median | Specific queries/parameters/data skew | Group queries stably and inspect slow queries |

Do not draw conclusions from a single metric alone. For example, rising pending acquire can be caused by a small pool, or by slow queries or long transactions preventing connections from returning.

## 13. Designing Low-Cardinality Metric Names and Tags

A metric set can be organized as follows:

| Suggested Metric | Type | Suggested Tags |
|---|---|---|
| `app.r2dbc.query.duration` | Timer | operation, outcome |
| `app.r2dbc.pool.acquire` | Timer | pool, outcome |
| `app.r2dbc.transaction.duration` | Timer | transaction, outcome |
| `app.r2dbc.connection.hold` | Timer | pool, outcome |
| `app.r2dbc.pool.pending` | Gauge | pool |
| `app.r2dbc.pool.acquired` | Gauge | pool |
| `app.r2dbc.operation.errors` | Counter | operation, error_type |

These are suggested application-defined names; actual metric names may differ by convention and backend.

Good tags:

- `operation`: `customer.findById`, `order.save`.
- `outcome`: `success`, `empty`, `error`, `cancelled`.
- `pool`: `primary`, `reporting`.
- `database`: `orders`, `customers` if the set is fixed.

Bad tags:

- Full SQL with literals.
- Individual entity IDs.
- Request paths containing IDs.
- User emails.
- Trace IDs.
- Free-form exception messages.
- Bind parameter values.

If you need to inspect specific SQL, use controlled traces or logs with sensitive data masked. Never put SQL or personal data into metric labels.

## 14. Histograms and Percentiles: Look at p95/p99 Instead of Averages Alone

Average duration can hide very slow requests. For example, 99 queries taking 10 ms and one query taking 2 seconds raises the average, without showing the distribution.

Observe:

- p50: typical latency.
- p95: the slowest 5% of operations exceed this threshold.
- p99: tail latency.
- Max: slowest point in the window, read with caution.
- Count: number of samples in the window.

With Micrometer, enable histograms or percentiles suited to your backend. Example:

~~~java
Timer queryTimer = Timer.builder("app.r2dbc.query.duration")
        .description("R2DBC query publisher duration")
        .publishPercentileHistogram()
        .tag("operation", "customer.findById")
        .register(meterRegistry);
~~~

Enabling histograms generates extra bucket time series and storage overhead. Only enable them for metrics needed for SLOs/alerts or tail-latency analysis. Choose buckets aligned with your system's time units and goals.

Do not compare p99 across two sources with vastly different sample counts without checking sample volume. A p99 over 10 samples is far less stable than a p99 over thousands of samples.

## 15. Logging Slow Queries Safely

Metrics reveal trends; logs help investigate a specific query execution. You can log when duration exceeds a threshold:

~~~java
.doFinally(signal -> {
    long elapsed = System.nanoTime() - started;

    if (elapsed > slowQueryThresholdNanos) {
        log.warn(
                "Slow repository operation: operation={}, durationMs={}, signal={}",
                "customer.findById",
                elapsed / 1_000_000.0,
                signal
        );
    }
});
~~~

Operation names should be stable and free of IDs. To correlate with a request, include trace/span context in logs per observability policy.

Avoid logging passwords, emails, tokens, personal data, or full bind parameters. If SQL must be logged, use statements stripped of literals and apply masking rules. Slow logs need sampling or rate limiting under high query volume to avoid extra I/O and log backend overload.

## 16. Measuring Retries Properly

Retries can make user-experienced wait time much longer than a single query execution.

Example:

~~~java
return repository.findById(id)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
~~~

Two measurement boundaries are useful:

- **Per attempt:** measures each execution of the underlying query individually. Useful for knowing how long each attempt took and how many attempts occurred.
- **Whole operation:** measures from initial subscription to the final outcome after retries/backoff. Useful for caller-experienced latency.

If the timer sits inside the source before `retryWhen`, each resubscription records a new sample. If the timer wraps the full publisher after `retryWhen`, duration includes all attempts and backoff intervals.

Record attempt counts using a counter with bounded tags. Never retry constraint or validation errors. For writes, evaluate idempotency and the case where the database committed yet the client did not receive the response.

Retries can make per-attempt average query latency look normal while whole-operation latency spikes. Monitor both.

## 17. Measuring Writes and Stream Reads

Reads and writes have different timing profiles:

- An `INSERT` typically emits few results and completes quickly.
- An `UPDATE`/`DELETE` may wait on locks or affect many rows.
- A `SELECT` returning `Flux` may span a duration proportional to row count and subscriber speed.
- A batch save may involve multiple statements or multiple round-trips depending on implementation.

For `Flux`, measure emitted row count alongside duration:

~~~java
AtomicLong rowCount = new AtomicLong();

return repository.findAll()
        .doOnNext(row -> rowCount.incrementAndGet())
        .doFinally(signal -> {
            recordRowsReturned(rowCount.get());
            recordStreamOutcome(signal);
        });
~~~

With metrics, you can record a distribution summary of row counts or rows per operation. Do not use arbitrary row counts as a tag because cardinality can explode; record them as a histogram/distribution or controlled log.

For batches, record batch size alongside duration. A batch of 10 rows and a batch of 10,000 rows cannot be compared by duration without considering work size.

## 18. Measuring Connection Hold Duration

Low acquire latency does not guarantee a healthy pool. Connections can be borrowed quickly yet held for a long time.

Connection hold duration can be measured where the pool lends and reclaims connections, or via a proxy/wrapper tracking connection lifecycle. Distinguish:

- Time from when the pool lends a connection until it is returned.
- Statement execution time.
- Transaction lifetime.

Inside a transaction, connection hold duration typically reflects how long the transaction used the connection. For long streams outside a transaction, reading results can keep the connection held until stream complete/cancel.

If the pool or proxy does not expose a hold timer directly, it can be partially inferred from the `acquired` gauge, query/transaction durations, and appropriate instrumentation. Do not treat `max-life-time` or `max-idle-time` as connection hold duration; those are connection age/idle eviction policies, not how long a request borrows a connection.

## 19. Avoiding Instrumentation That Alters Behavior

Instrumentation should observe a publisher without adding extra subscriptions or altering semantics.

Avoid:

~~~java
Mono<Customer> result = repository.findById(id);
result.subscribe(); // Creates a separate subscription just to log
return result;
~~~

The code above can execute the query twice: once for the logging subscription and once for the caller's subscription.

Attach operators directly to the returned publisher:

~~~java
return repository.findById(id)
        .doOnNext(customer -> log.debug("Customer found"))
        .doFinally(signal -> recordCompletion(signal));
~~~

Additional rules:

- Do not call `block()` just to measure time.
- Do not consume a `Flux` in one branch and return the original `Flux` to the caller.
- Do not open an extra connection to infer pool wait for the main query.
- Do not alter exceptions or empty signals solely to record a metric.
- Do not perform heavy synchronous logging on the event loop.
- Do not create dynamic per-request tags.
- Ensure timers are created per subscription when a publisher can be subscribed to multiple times.

If using an instrumentation helper, verify it preserves `onNext`, `complete`, `error`, cancellation, and backpressure.

## 20. Transaction Annotations and Timer Placement

With `@Transactional` methods, the Spring transaction interceptor wraps the reactive publisher returned by the method. To measure caller-observed duration, place the timer at the caller boundary:

~~~java
public Mono<Order> submit(CreateOrderCommand command) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(meterRegistry);

        return orderService.createOrder(command)
                .doFinally(signal -> sample.stop(orderTransactionTimer));
    });
}
~~~

In this example, `orderService.createOrder` must be invoked through the Spring proxy. Calling the method inside `Mono.defer` keeps invocation and subscription inside the same measurement lifecycle.

If the timer is started inside the method before the publisher is subscribed to, idle time waiting for subscription can skew the measurement. If the timer sits inside an operator before the transaction interceptor, it may miss full commit/rollback cleanup.

For exact transaction completion measurement, consider transaction synchronization/observation at the transaction manager layer. Document clearly whether a metric measures service operation duration or transaction manager duration.

## 21. Transaction Synchronization for Completion Events

Spring reactive transactions support transaction synchronization in Reactor Context while a transaction manager is active. Synchronizations can receive post-completion notifications to distinguish commit vs. rollback across the transaction lifecycle.

Usage concept:

- Register a synchronization within the active transaction context.
- Record a timestamp when the transaction starts or when synchronization is registered at the proper boundary.
- In the after-completion callback, record duration and commit/rollback status.
- Do not store transaction synchronization in an imperative `ThreadLocal`.
- Do not register a synchronization outside a reactive transaction and expect callbacks to run.

Exact APIs and callbacks depend on Spring Framework version and how transactions are created. When exact commit/rollback timing is required, use the reactive transaction synchronization API for your running version and verify with integration tests.

Never start a secondary transaction just to time the primary transaction. Doing so alters connection usage and skews measurements.

## 22. Example Analysis of a Slow Request

Suppose a dashboard shows:

| Metric | Value |
|---|---:|
| Request duration p95 | 900 ms |
| Pool acquire p95 | 500 ms |
| Query duration p95 | 70 ms |
| Transaction duration p95 | 760 ms |
| Pending acquire | Rising steadily |
| Database CPU | 40% |

Interpretation:

1. Requests are slow largely due to waiting on the pool.
2. Queries are not overly slow based on current measurements.
3. Transactions last much longer than total SQL time, suggesting logic or waits between queries.
4. Database CPU is not high yet, though locks, sessions, and other workloads should still be checked.
5. Increasing the pool may help if the database has headroom, but first inspect connection hold duration and transaction boundaries.

Another case:

| Metric | Value |
|---|---:|
| Request duration p95 | 850 ms |
| Pool acquire p95 | 8 ms |
| Query duration p95 | 720 ms |
| Transaction duration p95 | 780 ms |
| Database CPU | 95% |
| Lock wait | Low |

In this case, the pool is not the main bottleneck. Inspect query plans, indexes, data volume, rows read, and concurrency. Increasing `max-size` may saturate the database further.

These numbers are illustrative examples. Real conclusions require comparing metrics from the same time window, workload, and measurement boundaries.

## 23. Alerting on Symptoms and SLOs

Do not alert just because a single query crosses a fixed threshold. A batch operation can legitimately run longer than a lookup.

Define SLOs by operation type:

- ID lookup: p95/p99 latency.
- Order write: latency and error rate.
- Batch import: throughput and batch completion time.
- Transaction: duration and rollback rate.
- Pool: acquire timeouts, pending queue, and saturation.

Alerts should combine:

- Duration exceeding thresholds over a sustained window.
- Rising error/timeout rates.
- Persistently high pending acquire.
- Acquired persistently near `max-size`.
- Abnormal database resource usage or lock waits.
- Request SLO violations.

Use a wide enough time window to avoid alerting on brief spikes. For histogram metrics, compute percentiles from buckets or backend queries as configured. Avoid alerting on `max` alone because a single outlier sample can cause noisy alerts.

## 24. Testing Instrumentation

Instrumentation must be tested to ensure it does not alter publisher semantics.

You can use a synthetic publisher with delay to verify the timer:

~~~java
@Test
void shouldRecordPublisherDuration() {
    Mono<String> source = Mono.delay(Duration.ofMillis(20))
            .map(ignored -> "ok");

    StepVerifier.create(metrics.measure("test.operation", source))
            .expectNext("ok")
            .verifyComplete();

    assertThat(registry.get("app.r2dbc.operation")
            .timer()
            .count())
            .isEqualTo(1);
}
~~~

Adapt this illustrative example to your actual metric helper. Cases to verify:

- `Mono` success.
- `Mono` empty.
- `Flux` complete.
- Error.
- Cancellation.
- Publisher subscribed to multiple times.
- Retry: per-attempt and whole-operation measured at exact boundaries.
- Instrumentation does not create extra subscriptions.
- Tags always remain low cardinality.

To test real pool acquire, query, and transaction timing, use integration tests with an R2DBC driver/database. Generate controlled load or intentionally configure a small pool in tests to observe pending acquire and timeouts. Avoid arbitrary sleeps; use `StepVerifier`, latches, or coordinated test utilities.

## 25. Workflow for Investigating a Slow Database Operation

When a slow query/request is detected, proceed in order:

1. Identify the exact operation and measurement boundary.
2. Compare request duration with repository/query duration.
3. Check pool acquire latency and pending acquire.
4. Check acquired, idle, and `max-size` connections.
5. Check transaction duration and connection hold duration.
6. Identify which query takes the most time inside the transaction.
7. Cross-check statement timing with database server statistics.
8. Check lock waits, slow queries, and execution plans.
9. Check result size, streaming, and downstream consumers.
10. Check whether retries/backoff are extending the operation.
11. Change one factor, re-run the same workload, and compare p95/p99.
12. Monitor post-deployment to confirm improvement.

Do not enlarge the pool just because requests are slow. Do not optimize queries just because transactions are long. First pinpoint whether the time is spent in acquire, statement execution, fetching, application work, or transaction completion.

## 26. Common Measurement Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Query duration includes time before subscription | Timer starts at publisher creation | Start inside `defer` |
| Query metric recorded twice | Extra `subscribe()` added for logging | Attach operators to the original publisher |
| Timer does not record on cancellation | Using only `doOnSuccess`/`doOnComplete` | Use `doFinally` and classify cancel |
| Empty `Mono` counted as error or data success | Not distinguishing `null` in `doOnSuccess` | Record `empty` outcome separately |
| `Flux` duration reflects only first row | Stopping timer in first `doOnNext` | Measure until complete/error/cancel |
| Pool wait mistaken for slow SQL | Repository timer includes acquisition | Measure pool acquire separately |
| Transaction duration exceeds sum of queries | Logic/waits between statements or cleanup | Measure transaction boundaries and connection hold |
| Pool pending rises yet queries are fast | Connections held long or small pool | Check hold time and transactions |
| Metric backend overloaded | Tags contain IDs/SQL/traces | Use low-cardinality tags |
| Unstable p99 | Too few samples or unsuitable histogram | Check count, buckets, and measurement window |
| Retries raise user latency while query timer looks normal | Timer measures per attempt only | Measure both attempt and whole operation |
| Slow-query logs slow down the app | Excessive logging or heavy synchronous writes | Use sampling, rate limits, and async logging |
| Client metrics differ from server metrics | Different measurement boundaries | Document client/server boundaries and compare |

## 27. R2DBC Observability Implementation Checklist

Before shipping metrics to production, confirm:

1. Query timers start at subscription, not publisher construction.
2. Query timers have clear boundaries: repository operation, statement, or full stream.
3. `Flux` streams track time-to-first-row and time-to-complete when needed.
4. Pool acquire duration is measured separately from query duration.
5. Pool gauges track acquired, idle, allocated, and pending if supported by driver/pool.
6. Transaction duration is measured at the right boundary.
7. Commit, rollback, error, and cancellation outcomes can be distinguished when needed.
8. Connection hold duration is observed or reliably inferred.
9. p50/p95/p99 and sample counts are available for critical operations.
10. Metric tags have low cardinality.
11. Sensitive SQL/bind data is never written to metrics/logs.
12. Retries are measured per attempt and for the whole operation.
13. Instrumentation never calls `subscribe`/`block` or triggers extra queries.
14. Pool, application, and database metrics are aligned to the same timestamps.
15. Dashboards and alerts follow SLOs and symptoms.
16. Instrumentation is tested for success, empty, error, cancel, and multiple subscriptions.

## 28. Conclusion

Measuring query duration, pool acquire duration, and transaction duration separates three sources of latency that are frequently conflated in Spring Data R2DBC applications. A timer around a repository publisher shows application-layer duration; instrumentation at the `ConnectionFactory`/pool shows acquisition time; statement proxies and database metrics reveal SQL execution time; timers or transaction synchronizations show how long transactions live and how they finish.

Start measurements upon subscription, use a monotonic clock, record complete/error/cancel outcomes, and avoid extra subscriptions. Combine durations with pool gauges, transaction durations, database CPU/locks, and request p95/p99 latency. Keep metric tags low-cardinality and protect sensitive SQL data. When measurements have clear boundaries and are correlated together, you can decide whether to optimize queries, shorten connection holds, adjust concurrency/pool size, or narrow transaction boundaries instead of guessing configuration changes.
