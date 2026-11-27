# Pool Exhaustion, Long-Held Connections, and Errors When Cancelling Streams

In Spring Data Relational R2DBC applications, the connection pool grants database connections to executing publishers. Pool exhaustion typically manifests as slow requests, acquire timeout errors, or dropping throughput even while the application still has spare CPU. However, "pool exhausted" is only a symptom: root causes can include slow queries, transactions holding connections too long, read streams consumed slowly downstream, concurrency exceeding pool capacity, blocking calls, or connections not being closed properly.

Cancellation must also be understood accurately. When a subscriber cancels a `Mono` or `Flux`, Reactor sends a cancel signal upstream. The driver may try to cancel the running query and Spring's transaction infrastructure may roll back/clean up the transaction, but how immediately execution stops depends on the driver, database, and cancellation point. A cancelled publisher does not automatically prove the database stopped working or the connection returned to the pool instantaneously.

This lesson covers R2DBC connection lifecycles, how to distinguish pool saturation from connection leaks, causes of long connection hold times, designing short transactions and streams, handling cancellation, timeouts, metrics, testing, and load testing. Examples use Spring Boot, Reactor, and PostgreSQL; verify exact property names against your project's Spring Boot/R2DBC Pool versions.

## 1. How Does a Connection Pool Work?

R2DBC uses `ConnectionFactory` to create or provide connections. When wrapping a `ConnectionFactory` in a pool, requesting a connection acquires an idle connection from the pool or waits until one is returned or a timeout expires.

Simplified lifecycle:

~~~mermaid
flowchart TD
    A[Reactive request subscribed] --> B[Acquire connection from pool]
    B --> C{Connection available?}
    C -->|Yes| D[Execute SQL]
    C -->|No| E[Wait in acquire queue]
    E --> F{Available before timeout?}
    F -->|Yes| D
    F -->|No| G[Acquire timeout error]
    D --> H[Consume result]
    H --> I[Complete, error or cancel]
    I --> J[Cleanup transaction/resource]
    J --> K[Return connection to pool]
    K --> L[Available for another request]
~~~

A connection is held from acquisition until release. That duration is not limited to SQL execution time in the database. It can include:

- Waiting for the transaction to start or finish.
- Reading results from the database.
- Waiting for downstream to demand more items due to backpressure.
- Running application logic while still inside a transaction.
- Waiting on an HTTP call or message broker if placed inside a transaction.
- Rollback or cleanup after an error or cancellation.

The pool tracks open physical connections and currently borrowed connections. When code uses Spring Data repositories, `DatabaseClient`, or `R2dbcEntityTemplate` within their standard lifecycle, the framework manages acquire/release. When interacting directly with `Connection`, the application must guarantee closure along every completion, error, and cancellation path.

## 2. Distinguishing Pool Saturation, Connection Leaks, and Slow Queries

All three conditions can produce the same acquire timeout symptom, yet their remediations differ.

| Condition | Common Symptoms | Typical Causes |
| --- | --- | --- |
| Pool saturation | Active connections hit max; pending acquires climb during peak traffic. | High concurrency, pool too small for workload, or long connection hold times. |
| Connection leak | Borrowed connections are never returned; active stays elevated even after load stops. | Missing `close`, broken resource cleanup, or publishers detached from lifecycle. |
| Slow queries / lock waits | Connections stay active for long periods; DB shows long-running queries or lock waits. | Missing SQL indexes, poor query plans, lock contention, slow I/O. |
| Slow downstream | Query stream stays active while application consumes rows slowly. | Streaming `Flux` straight to slow clients or slow per-row processing. |
| Acquire/create bottleneck | Pending grows even below max active, or new connections take too long to open. | DB refuses sessions, slow DNS/TLS/network, or connection creation failures. |

### Pool Saturation Is Not Necessarily a Leak

If traffic spikes and all connections are serving legitimate queries, the pool can saturate temporarily. Once the burst finishes, active drops and pending requests drain. That is saturation from capacity or workload.

### Leaks Leave a Persistent Signature

If requests have ended yet active connections remain held and the pool fails to recover after traffic drops, look for code paths failing to release resources or publishers that never terminate. Still, a transaction waiting on a slow query/lock or an unconsumed `Flux` can mimic a leak.

### Slow Queries Are Often the Root Cause

Raising `max-size` can temporarily mask slow queries while simultaneously pushing more concurrent load onto the database. Inspect query duration, execution plans, indexes, lock waits, and database load before expanding the pool.

## 3. Metrics Worth Monitoring

Looking solely at current active connections is rarely enough. Monitor both the pool and the database.

| Metric / Observation | Meaning |
| --- | --- |
| Allocated / total connections | Total physical connections managed by the pool. |
| Acquired / active connections | Connections currently borrowed by publishers. |
| Idle connections | Connections ready to be leased. |
| Pending acquires | Requests currently waiting for a connection. |
| Acquire duration | Time from connection request to grant. |
| Acquire timeout count | Times a connection could not be acquired before deadline. |
| Connection creation time / failures | Time and errors opening new physical connections. |
| Usage duration | Duration a connection remains borrowed. |
| Query duration | SQL execution duration. |
| Transaction duration | Transaction lifetime. |
| Database sessions / lock waits | State observed from the database side. |

If Micrometer/Actuator and R2DBC Pool metrics are enabled, export metrics to your project's observability stack. Exact metric names vary by version and registry; verify via the actual metrics endpoint instead of assuming fixed names.

Configure trend-based alerts—for example, rising pending acquires, active pinned near max for several minutes, increasing acquire timeouts, or usage duration exceeding thresholds. A brief deployment spike is not necessarily an incident if the pool recovers quickly.

### Correlating Application and Database Metrics

When active connections are high, inspect the database at the same time:

- How many sessions are actively running queries?
- Are there `idle in transaction` sessions?
- Are queries waiting on locks?
- Is the same query running excessively?
- Are sessions idle for long periods while still inside transactions?
- Is the database hitting connection limits or CPU/I/O saturation?

If the pool shows active connections while the database shows no running queries, the application may be holding connections during business logic, slow downstream consumption, or external calls.

## 4. Sizing Pools Based on Connection Hold Time

Pool size should not be picked mechanically from CPU count or concurrent HTTP requests. An initial estimate follows Little's Law:

\[
L = \lambda \times W
\]

Where:

- `L` is the average number of concurrent tasks in the system.
- `λ` is the average arrival/completion rate (requests/transactions per second).
- `W` is the average duration a task holds a connection (seconds).

For example, if a workload needs 100 database operations per second and each holds a connection for 0.05 seconds on average, the average concurrent connections needed is roughly 5. That is only an average; add headroom for p95/p99 latency, bursts, longer transactions, and other workloads.

One connection can serve multiple sequential statements within a single transaction, so measure hold time across the entire transaction/use case, not just a single SQL statement.

### Calculating Total Connections System-Wide

With multiple application replicas, pool sizes multiply:

\[
C_{total} = instances \times maxPoolSize + otherClients
\]

`otherClients` includes migration jobs, admin tools, background workers, reporting, monitoring, and other applications. This sum must remain safely within database limits with headroom for failover and maintenance.

For example, 6 replicas each with `max-size` 20 can open up to 120 connections, before counting workers or tools. Never raise pool size on individual instances without calculating the cluster-wide total.

### Larger Pools Are Not Always Faster

Databases have finite CPU, I/O, locks, and session overhead. Too many concurrent connections increase context switching, memory usage, and lock contention, worsening latency. Growing a pool helps only when the database still has spare capacity and the acquire queue is the genuine bottleneck.

## 5. Configuring R2DBC Pool in Spring Boot

When using R2DBC Pool, Spring Boot configuration typically looks like:

~~~yaml
spring:
  r2dbc:
    url: r2dbc:pool:postgresql://db-host:5432/orders
    username: app_user
    password: secret
    pool:
      enabled: true
      initial-size: 5
      max-size: 20
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 10m
      max-life-time: 30m
~~~

Exact property names and whether `r2dbc:pool` is needed in the URL depend on how your Spring Boot version manages R2DBC Pool. Some setups use `pool.enabled` with a plain driver URL; check the reference documentation for your project's version.

Common meanings of these properties:

- `initial-size`: initial connections created at startup.
- `max-size`: maximum connections the pool may manage.
- `max-acquire-time`: maximum wait time to acquire a connection.
- `max-create-connection-time`: timeout for creating a new physical connection.
- `max-idle-time`: maximum idle time before a connection may be evicted.
- `max-life-time`: maximum lifetime of a physical connection.
- `validation`: how connection health is checked if supported by driver/pool config.

Do not set `max-acquire-time` excessively long just to hide pool exhaustion. Acquire timeout is a backpressure signal at the connection layer: if connections are held too long, waiting longer simply piles up requests and drives up latency.

### Acquire Timeouts Must Make Operational Sense

Connection wait budgets should align with the request's latency budget. If an API has a 2-second SLA, letting acquires wait 30 seconds keeps requests alive far beyond acceptable limits. Pair acquire timeouts with request timeouts and application-layer concurrency limits.

### Idle Time and Max Lifetime

`max-idle-time` and `max-life-time` allow the pool to retire stale or long-idle connections per policy. They do not fix connections currently borrowed indefinitely. An active, unreturned connection cannot be evicted like an idle one.

## 6. Ensuring Resources Are Released Properly

Spring Data repositories and `DatabaseClient` manage connection lifecycles with the publisher. For ordinary persistence code, prefer these abstractions over acquiring a `Connection` manually.

When working directly with `ConnectionFactory`, ensure `close` runs on all termination paths. In R2DBC, calling `close` on a pooled connection typically returns it to the pool rather than closing the physical socket.

### Using `usingWhen` for Reactive Resources

General example:

~~~java
Mono<ResultValue> work =
    Mono.usingWhen(
        connectionFactory.create(),
        connection -> executeWork(connection),
        Connection::close,
        (connection, error) -> rollbackIfNeeded(connection)
            .then(connection.close()),
        connection -> rollbackIfNeeded(connection)
            .then(connection.close())
    );
~~~

`usingWhen` supports asynchronous cleanup across all three paths: completion, error, and cancellation. Adapt `rollbackIfNeeded` depending on whether an active transaction was opened; do not call rollback blindly if no transaction started or it already ended.

In production code, consider Spring's `ConnectionFactoryUtils` or transaction-aware access when connections must join Spring-managed transactions. Do not call `connectionFactory.create()` manually inside a service expecting it to join the active transaction automatically.

### Do Not Use `doFinally` to Replace Async Cleanup

`doFinally` receives complete/error/cancel signals, yet its synchronous callback is not suitable for asynchronous cleanup requiring subscription—such as `Connection.close()`, which returns a `Publisher`. Calling `close` without subscribing/composing will not guarantee cleanup completes.

Use `usingWhen` or framework-provided resource management APIs.

### Do Not Store `Connection` in Fields

Never store a `Connection` in a singleton service, static field, or object shared across requests. A connection is leased for a single operation and must not be shared across arbitrary publishers/threads.

## 7. Long Transactions Hold Connections Open

When a reactive transaction begins, the transaction manager typically acquires a connection and holds it until commit or rollback. Anything inside that transaction keeps holding the connection—even when code waits on non-database work.

Bad example:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
        .flatMap(order ->
            webClient.post()
                .uri(paymentUrl)
                .bodyValue(command.payment())
                .retrieve()
                .bodyToMono(PaymentResult.class)
                .map(result -> order.withPayment(result.id()))
        )
        .flatMap(orderRepository::save);
}
~~~

The transaction can hold the database connection for the entire duration of the HTTP call to the payment service. If the external service stalls, the connection stays pinned even while the database executes no queries.

### Narrow Transaction Boundaries

Run non-transactional steps first, then open a short transaction for the atomic database operations. Still, you cannot simply move an external payment HTTP call outside and assume the entire workflow remains atomic. Integrating with external systems usually requires sagas, idempotency, or an outbox depending on business requirements.

A common pattern:

1. Validate the request and perform non-transactional checks.
2. Call the external service idempotently if appropriate.
3. Open a short transaction to save business state and an outbox/event.
4. Commit.
5. Let a worker process post-commit side effects.

If business ordering requires persisting a pending state while waiting on payment, model states and compensations explicitly rather than holding a database transaction open across network calls.

## 8. Streaming `Flux` Can Hold Connections Open While Consumed

A repository method returning `Flux` usually runs the query upon subscription. While results stream, the connection may stay held until all rows are consumed or the publisher is cancelled and cleanup finishes.

Example:

~~~java
@GetMapping("/people/export")
public Flux<Person> exportPeople() {
    return repository.findAll();
}
~~~

If clients download slowly, downstream backpressure slows down database result consumption. The connection stays occupied far longer than the time the database needed to find the rows.

This is not strictly a leak: the publisher is still alive and working legitimately. Yet if many clients open slow exports concurrently, the pool can still saturate.

### Ways to Reduce Connection Hold Time

- Paginate in chunks so each page query finishes and releases its connection before slow downstream steps.
- Bound export sizes and request lifetimes.
- Generate export files via background jobs and let clients download the file afterward.
- Avoid external API calls while consuming a database `Flux`.
- Avoid wrapping an entire export in a long transaction unless snapshot isolation is truly needed.
- Cap concurrent exports.

If a consistent multi-page snapshot is needed, evaluate database isolation/snapshot strategies. Chunked paging releases connections between queries, though it does not automatically ensure every page sees the same snapshot.

### Do Not `collectList` Unbounded Datasets

`collectList` lets the query finish and release the connection once all rows are buffered into memory, freeing the connection earlier than slow downstream consumption—at the cost of heap proportional to dataset size. For large datasets, stream in chunks or export via background jobs instead of calling `collectList` on everything.

## 9. Backpressure and Concurrency Can Exhaust Pools

Reactive Streams regulate demand between publisher and subscriber, yet they do not automatically cap all application-level concurrency.

Example:

~~~java
return requests.flatMap(
    request -> repository.save(toEntity(request))
);
~~~

Without an explicit concurrency limit, `flatMap` permits Reactor's default number of concurrent inner publishers. With a fast source, the number of operations waiting on or holding connections can easily exceed pool capacity.

Set an explicit limit:

~~~java
return requests.flatMap(
    request -> repository.save(toEntity(request)),
    8
);
~~~

Or run sequentially:

~~~java
return requests.concatMap(
    request -> repository.save(toEntity(request))
);
~~~

Concurrency of 8 does not mean the whole system needs a pool size of 8; other requests share the pool. Coordinate per-pipeline concurrency limits with total request load, pool size, and database capacity.

### `buffer` Is Not a System-Wide Limit

`buffer(500)` groups items per batch, yet if downstream uses `flatMap` with high concurrency, many batches can run concurrently. Account for concurrent chunks, items per chunk, and internal buffers.

### Pools Are Not Unbounded Queues

When the pool runs out of connections, acquire requests wait in a queue. Unbounded queue growth drives up latency and memory before timeouts fire. Enforce concurrency/queue bounds at the application layer and set sensible acquire timeouts.

## 10. Blocking Calls Can Prolong Connection Hold Times

Reactive applications can still block if code calls:

- `block()` or `blockFirst()`/`blockLast()`.
- JDBC/`JdbcTemplate`.
- Blocking file I/O.
- Blocking HTTP clients.
- `Thread.sleep()`.
- Non-reactive third-party APIs.

If blocking occurs inside a transaction, the connection remains held for the duration of the block. If blocking runs on an event loop, it stalls other requests as well.

Never call blocking APIs on event-loop threads. When integrating blocking libraries, offload work to an appropriate scheduler like `boundedElastic` with concurrency limits. Even then, switching schedulers does not release a connection if code remains inside a transaction; redesign the transaction boundary.

Bad example:

~~~java
@Transactional
public Mono<Person> update(UUID id) {
    return repository.findById(id)
        .map(person -> {
            ExternalBlockingClient.call(); // holds transaction/connection while blocking
            return person;
        })
        .flatMap(repository::save);
}
~~~

Move blocking calls outside database transactions where business logic permits, and keep event loops non-blocking.

## 11. Cancellation in Reactor and R2DBC

Cancellation occurs when a subscriber no longer wants results. Common scenarios:

- HTTP client disconnects.
- WebFlux response is cancelled.
- Subscriber calls `dispose()`.
- `take(n)` received enough items and cancelled upstream.
- `timeout` operator cancels the source publisher.
- Test calls `StepVerifier.thenCancel()`.
- A parent pipeline cancels due to another failure.

Cancellation is a distinct signal—neither `onComplete` nor `onError`. Therefore, `doOnError` alone misses cancelled operations.

Observe cancellation explicitly:

~~~java
return repository.findAll()
    .doOnCancel(() -> log.info("Repository stream cancelled"))
    .doFinally(signal -> log.debug("Stream ended: {}", signal));
~~~

`doOnCancel` records cancellations; `doFinally` receives `SignalType.CANCEL`, `ON_COMPLETE`, or `ON_ERROR`. Observation callbacks must not perform async cleanup in place of proper resource management.

### Does Cancellation Stop the Query Immediately?

You cannot assume cancellation always aborts database statements instantaneously. Behavior depends on:

- How thoroughly the R2DBC driver supports statement cancellation.
- Whether the database engine supports cancelling running queries.
- Whether the query is executing, fetching, or waiting on network I/O.
- How the transaction manager runs rollback/cleanup.
- How long the driver needs to verify the connection is clean for reuse.

When a query is cancelled, the connection may require cleanup or rollback before returning to the pool. Measure usage duration after cancellations and inspect database sessions rather than assuming the connection is free as soon as the publisher is disposed.

### Cancellation Inside Transactions

If a publisher belongs to a Spring-managed reactive transaction, cancellation can trigger rollback and cleanup per transaction manager semantics. Do not detach database work via manual `subscribe()`, because detached work escapes the caller's cancellation and transaction lifecycle.

For critical transactions, test your Spring Framework, Spring Data, and driver versions with integration tests. Never assume cancel equals commit or normal completion.

## 12. `take()`, `timeout()`, and Unintended Cancellation

Certain operators cancel upstream once a condition is met:

~~~java
repository.findAll().take(10);
~~~

After receiving 10 items, `take` cancels upstream. If the repository is streaming from a connection, the driver and framework must clean up the result/connection.

Similarly:

~~~java
repository.findAll()
    .timeout(Duration.ofSeconds(5));
~~~

If signals fail to arrive in time, `timeout` emits an error and cancels the upstream source. This does not just "error to the client"; it actively sends a cancellation signal to the database publisher.

### Be Careful Limiting a `Flux` Inside a Transaction

If a transaction wraps a `Flux` and downstream uses `take(1)`, cancellation can cause the transaction to roll back depending on reactive transaction manager behavior. That can unexpectedly prevent writes from committing in code or tests.

For write workflows, finish transactional publishers cleanly before switching into a streamed response. Do not turn a transactional write publisher into an arbitrarily truncated stream.

### Do Not Use `timeout` as a Leak Fix

`timeout` caps waiting time, yet if resource cleanup is broken, timeouts can actually trigger leaks more frequently. Always verify connections return to the pool after timeouts/cancellations.

## 13. Managing Cancellation with Manual Resources

When acquiring connections manually, cleanup must handle completion, error, and cancellation. `usingWhen` is designed for resources whose cleanup returns a `Publisher`:

~~~java
Mono<Long> countPeople() {
    return Mono.usingWhen(
        connectionFactory.create(),
        connection -> executeCount(connection),
        connection -> connection.close(),
        (connection, error) -> rollbackIfActive(connection)
            .onErrorResume(cleanupError -> Mono.empty())
            .then(connection.close()),
        connection -> rollbackIfActive(connection)
            .onErrorResume(cleanupError -> Mono.empty())
            .then(connection.close())
    );
}
~~~

This is an illustrative skeleton. In production code:

- Only roll back if a transaction was started and remains active.
- Do not silently swallow cleanup errors if the system needs to observe or handle them.
- Guarantee `close` is invoked once per lifecycle.
- Never use the connection outside the resource callback scope.
- When using a Spring transaction manager, avoid manually acquiring unbound connections.

Never call `close` and discard the returned `Publisher`:

~~~java
connection.close(); // Publisher not yet subscribed; cleanup may not have run.
~~~

Compose the cleanup publisher or use an appropriate resource-management abstraction.

## 14. Timeouts Should Be Layered Intentionally

No single timeout handles every stall. A request can block or wait across multiple layers:

| Layer | What the Timeout Controls | When Expired |
| --- | --- | --- |
| Connection acquire | Waiting for a connection from the pool. | Emits acquire timeout. |
| Connection creation | Opening a physical connection. | Connection creation fails. |
| Query / statement / database | Time SQL is allowed to execute. | Driver/database cancels or errors as supported. |
| Transaction | Transaction lifetime. | Transaction manager/database may timeout/roll back. |
| Reactor publisher | Time waiting for publisher signals. | Emits `TimeoutException` and cancels upstream. |
| HTTP / request | Total request budget. | Client/server ends request and may cancel downstream. |

Timeouts must align. For example, a 3-second HTTP timeout with a 10-second acquire timeout kills the request before the pool even surfaces its error. A 30-second query timeout does little good if the API allows only 2 seconds.

### Budgeting Timeouts

One way to structure budgets:

- Request budget: total API execution time allowed.
- Acquire budget: a small fraction of the request budget.
- Query budget: matched to query complexity and SLA.
- Transaction budget: enough for atomic DB steps, shorter than total request timeout where possible.
- Cleanup budget: room for rollback/release after errors or cancellations.

Exact statement/database timeouts depend on driver and database. Configure them via driver options, database statement timeouts, or driver-supported APIs. Do not assume all R2DBC drivers share identical property names.

## 15. Retries Can Extend Connection Hold Times

Retrying with backoff helps with transient failures, but placement is critical.

If retries sit inside a transaction holding a connection, backoff delays lengthen the transaction and keep the connection pinned while waiting.

Do not hold a transaction open across long waits or external calls. When an entire transaction should be retried, wrap the retry around the transactional publisher so each attempt gets its own transaction lifecycle, while ensuring the operation is idempotent.

Conceptual example:

~~~java
Mono<Order> attempt =
    transactionalOperator.transactional(createOrderWork(command));

return attempt.retryWhen(
    Retry.backoff(2, Duration.ofMillis(100))
        .filter(this::isTransientDatabaseFailure)
);
~~~

This is a general pattern. Only retry genuinely transient errors; never retry validation, unique constraints, or static SQL errors. If the transaction committed before response loss, retries can create duplicates; use idempotency keys or unique business keys.

## 16. Diagnosing Connection Leaks Systematically

When the pool exhausts, do not immediately raise `max-size`. Gather evidence in order:

1. Record active, idle, allocated, and pending acquire counts.
2. Check acquire latency and timeout counts.
3. Inspect connection usage duration percentiles.
4. Correlate with query duration and transaction duration.
5. Check database sessions, lock waits, and `idle in transaction`.
6. Identify endpoints/jobs with high concurrency or long streams.
7. Search for manual `Connection` acquisition or detached `subscribe()` calls.
8. Inspect cancellation, error, and cleanup paths.
9. Reproduce with a load test and observe whether the pool recovers after load stops.

### Signs of a Suspected Resource Leak

- Active connections climb steadily over time and never drop.
- Pool stays exhausted even after request rates return to normal.
- Connection usage duration has a very long tail.
- Database retains idle or `idle in transaction` sessions.
- Errors spike after client-cancelled requests.
- One specific endpoint triggers abnormal active-connection spikes.

### Searching Manual Code Paths

Look in the codebase for patterns like:

- `ConnectionFactory.create()`.
- Uncomposed `Connection.close()`.
- `usingWhen` cleanups missing any path.
- `subscribe()` inside services/repository wrappers.
- `block()` inside reactive flows.
- `@Transactional` wrapping HTTP/file/queue operations.
- Database `Flux` returned directly to uncontrolled slow clients.
- Unbounded `flatMap` over large sources.
- Retry/backoff inside long transactions.

Not every occurrence of these APIs is a bug. Use them as starting points to trace lifecycle and subscriptions.

## 17. Distinguishing Slow Queries, Lock Waits, and Application-Held Connections

An active connection is not necessarily executing SQL. Database monitoring distinguishes:

- Active query: inspect query duration and execution plan.
- Lock wait: inspect blocker/blocked sessions.
- Idle in transaction: application opened a transaction and has not committed/rolled back.
- Idle: connection is not running SQL; if the pool marks it acquired, the application may be holding it between operations.
- No matching session: check proxy/pool metrics, connection creation, and sampling timing.

With PostgreSQL, `pg_stat_activity` and lock views show sessions, states, query start times, and wait events. Only run monitoring queries aligned with permissions and environment policies; avoid logging raw SQL with sensitive data.

If the database shows long-lived `idle in transaction` sessions, look for wide transaction boundaries or external I/O awaited inside transactions.

## 18. Testing Cancellation and Cleanup with Integration Tests

Use Testcontainers against a real database to verify connections are freed after cancellation. Tests should:

1. Run a query streaming many rows or taking sufficient time.
2. Subscribe and request a subset of items.
3. Cancel the subscription.
4. Wait for cleanup within a bounded timeout.
5. Execute a new query or check pool metrics to verify the pool still grants connections.
6. If the query ran inside a write transaction, read back data to verify expected rollback.

`StepVerifier` example:

~~~java
StepVerifier.create(repository.findAll())
    .thenRequest(1)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

This test verifies the publisher can be cancelled without hanging. By itself, it does not prove the database query stopped or the connection returned to the pool. Follow up with a new query, pool metrics checks, or database session checks.

### Testing with a Small Pool to Expose Bugs Faster

A test profile with a tiny `max-size`, such as 1 or 2, exposes held connections quickly. If one test holds a connection and a second operation acquires, it reliably reproduces acquire timeouts.

Never use a tiny pool as a default production configuration. It is purely a resource-lifecycle testing technique.

### Testing Errors During Cleanup

Force an error inside a transaction and verify the connection returns to the pool. Afterward, run another simple query. If the follow-up query cannot acquire a connection, inspect rollback/close paths.

## 19. Designing Pipelines Resistant to Pool Exhaustion

Design principles:

- Use repositories/`DatabaseClient` so the framework manages connections.
- Keep transactions tightly scoped around atomic database work.
- Never call HTTP, file I/O, or sleep inside transactions.
- Cap concurrency on `flatMap` and write jobs.
- Paginate/chunk instead of holding database `Flux` streams open indefinitely.
- Avoid N+1 queries and unindexed queries.
- Configure sensible acquire, request, and query timeouts.
- Never call `subscribe`/`block` inside reactive services.
- Use `usingWhen` for manual resources.
- Monitor active, idle, pending, acquire time, and usage time.
- Verify both cancellations and errors trigger cleanup.
- Sum connections across all replicas and workers before enlarging pools.

### Input-Side Backpressure

When APIs ingest streams or jobs continuously consume messages, bound concurrent write work. Use bounded concurrency, bounded queues, or rate limiting aligned with database capacity.

Never dump unbounded messages into an infinite queue expecting the pool to cope. When the database slows down, backlogs grow and exhaust memory.

### Isolating Workloads

Read-heavy exports, write-heavy ingestion, and latency-sensitive APIs can contend for the same pool. Depending on architecture, you can separate pools/`ConnectionFactory` beans for specialized workloads or cap concurrency independently. Splitting pools does not increase database capacity; total connections must still fit within the database budget.

## 20. Common Mistakes

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Acquire timeouts spike | Pool out of connections or slow connection creation. | Inspect active/pending, query duration, and DB sessions. |
| Active pinned at max | High concurrency, long transactions, or leak. | Find long usage durations and holding requests. |
| Pool fails to recover after load | Unreleased resources or non-terminating publishers. | Inspect `close`/`usingWhen`/cancel paths. |
| Database shows `idle in transaction` | Transactions open too long. | Narrow transactions and remove network calls from them. |
| Export API drains the pool | `Flux` holds connections for slow clients. | Chunk/page or use background export jobs. |
| `flatMap` drives pending up | More concurrent saves/queries than pool size. | Cap concurrency. |
| Increasing `max-size` worsens latency | Database already overloaded. | Lower concurrency, optimize queries/indexes. |
| Client cancels, yet query keeps running | Driver/DB cancellation not instant or signal not propagated. | Check driver, query cancellation, and DB sessions. |
| Timeout fires, yet connection not returned | Broken transaction/resource cleanup or driver still cleaning up. | Fix resource lifecycle and measure release time. |
| Cleanup in `doFinally` fails to run | `close` `Publisher` not composed. | Use `usingWhen` or framework resource APIs. |
| Retries drain the pool | Backoff inside transactions or high retry concurrency. | Retry outside transactions; bound retries and ensure idempotency. |
| Pool fails creating connections | DB limit, network/TLS/DNS, or credentials. | Inspect connection creation metrics and server logs. |

## 21. Pool Exhaustion Incident Playbook

When production reports acquire timeouts, proceed in order:

1. **Assess scope:** single instance or all replicas; single endpoint or entire system.
2. **Read pool metrics:** active, idle, pending, allocated, acquire duration, and timeouts.
3. **Read database state:** active queries, lock waits, `idle in transaction`, session count, and connection limits.
4. **Compare latencies:** query duration vs transaction duration vs connection usage duration.
5. **Find connection-holding workloads:** exports, imports, long transactions, `flatMap` concurrency, retries, or blocking calls.
6. **Check cancellations:** client disconnects, timeouts, and post-cancel cleanup.
7. **Check manual resources:** `ConnectionFactory.create`/`close` and `usingWhen`.
8. **Shed load safely:** cap concurrency or pause background jobs if the database is overloaded.
9. **Fix the root cause:** optimize queries, narrow transactions, fix lifecycles, or chunk streams.
10. **Evaluate pool size:** increase only when database headroom exists and total cluster connections stay within budget.
11. **Re-run load tests:** verify active drops, pending does not accumulate, and the pool recovers after bursts.
12. **Alert on trends:** acquire timeouts, pending duration, usage duration, and DB locks/sessions.

Never rely on restarting the application alone without finding the root cause. Restarting releases held connections temporarily without fixing the bug; exhaustion returns under the same load.

## 22. Load Testing and Recovery Verification Procedure

A useful load test measures more than steady-state throughput. It verifies recovery after bursts and cancellations.

Scenario design:

- Warm up so pool and database stabilize.
- Ramp request rate in steps.
- Sustain load long enough to observe pending/acquire behavior.
- Inject a burst exceeding expected capacity.
- Cancel a portion of requests/streams mid-flight.
- Drop load back to baseline.
- Observe whether active, idle, and pending recover.
- Check the database for orphaned transactions/sessions.
- Confirm no partial writes or retry duplicates occurred.

Metrics to compare before and after changes:

- Throughput.
- p95/p99 request latency.
- Acquire wait and timeout rate.
- Connection usage duration.
- Active/pending over time.
- Database CPU, I/O, and lock waits.
- Cancelled request counts and cleanup duration.
- Error and retry rates.

A healthy configuration meets load targets and recovers cleanly after bursts. If throughput looks high yet the pool never returns to idle after traffic stops, investigate lifecycle leaks.

## 23. Quick Diagnostic Checklist

| Question | If Yes |
| --- | --- |
| Active connections hit max and pending climbs? | Pool saturation is occurring; locate connection-holding workloads. |
| Pending climbs while active stays below max? | Check connection creation, validation, and DB session limits. |
| Connection usage duration far exceeds query duration? | Application holds connections outside SQL, e.g. transactions/downstream. |
| Are there `idle in transaction` sessions? | Transaction boundary may be too wide or waiting on non-DB work. |
| Does a slow streaming endpoint drain the pool? | Consider paging, chunking, or background export jobs. |
| Are there unbounded `flatMap` calls? | Cap concurrency and queue depth. |
| Are there `block`/JDBC calls in reactive flows? | Isolate blocking work and avoid holding transactions while blocking. |
| Are connections acquired manually? | Verify `close`/`usingWhen` across complete/error/cancel. |
| Clients cancel yet active stays elevated? | Check driver cancellation, transaction rollback, and DB sessions. |
| Growing the pool increases DB latency? | Reduce concurrency and optimize database instead of adding connections. |

## 24. Sustainable Operations Workflow

To reduce pool exhaustion risks in Spring Data Relational R2DBC:

1. **Choose a bounded pool:** size `max-size` and timeouts to database capacity.
2. **Sum total connections:** multiply by replicas and add background/migration/admin clients.
3. **Measure hold times:** separate query duration from transaction/usage duration.
4. **Keep transactions short:** never wait on HTTP, files, queues, or users inside transactions.
5. **Bound concurrency:** coordinate `flatMap`, batch jobs, and pool limits.
6. **Bound streams:** paginate/chunk whenever downstream can lag.
7. **Manage manual resources:** use `usingWhen` and cleanup across complete/error/cancel.
8. **Layer timeouts:** acquire, query, transaction, Reactor, and HTTP.
9. **Observe cancellations:** track cancel counts and connection release latency.
10. **Test on real databases:** use Testcontainers, `StepVerifier`, and small pools to reproduce.
11. **Load test bursts:** confirm the pool recovers when traffic drops.
12. **Alert on trends:** pending acquires, active/max ratio, usage duration, and DB locks/sessions.

Pool exhaustion signals that connections are being demanded faster than they are returned. Effective troubleshooting starts by measuring acquire latency and connection hold time, then distinguishing slow queries, long transactions, slow downstream consumers, excessive concurrency, and resource leaks. Cancellation must be tracked as its own termination path: it cancels the publisher, yet stopping queries and returning connections depend on the driver, transaction manager, and cleanup paths. With short transactions, bounded concurrency, stream backpressure, sound resource management, and pool sizes matched to database capacity, R2DBC applications stay stable under load and recover cleanly from errors or cancelled requests.
