# Controlling Timeouts Across HTTP, Pools, and Queries

In a Spring WebFlux application using Spring Data R2DBC, a single request can wait across many layers: the client sending the request, a reverse proxy forwarding it, WebFlux processing the pipeline, the connection pool leasing a connection, the driver opening or using the connection, the database executing SQL, and downstream HTTP services returning results. Setting only one timeout on a controller or configuring only a database timeout still leaves the request exposed to hanging indefinitely at another layer.

Timeout control must start from the request's **end-to-end time budget**. Each layer receives an appropriate share of the budget, dependency timeouts should be smaller than the caller's deadline, and all retries and cleanup must fit inside the overall limit. Distinguish connection wait time, connection creation time, statement execution time, HTTP response wait time, and maximum pipeline duration.

An application-side timeout also does not automatically prove the database stopped the query or rolled back the transaction. Reactive timeouts usually cancel the upstream subscription; whether the driver sends cancellation and the database aborts the statement depends on the driver, protocol, and DBMS. For critical queries, enforce database-side or driver-supported statement timeouts and test actual cancellation behavior.

## 1. Timeouts are distinct limits

No single timeout covers every stage. An R2DBC/WebFlux system typically needs to consider:

| Layer | What does the timeout control? | Example issue |
| --- | --- | --- |
| Client | How long the caller waits for a response | Users do not wait indefinitely |
| Load balancer/reverse proxy | Upstream wait or connection time | Proxy closes hung requests |
| HTTP server | Connecting, reading requests, or writing responses per server config | Slow clients or idle connections |
| Application pipeline | Maximum duration of the use case | Service fails to finish within deadline |
| WebClient | TCP connect, response read, or entire publisher | Slow downstream service |
| R2DBC pool | Waiting to acquire a connection from the pool | Pool exhausted |
| R2DBC connection creation | Time to establish a new connection | Database refusing or dropping connects |
| SQL statement | Time the database is allowed to run a statement | Slow query or lock wait |
| Transaction | How long a database business unit may stay open | Transaction holding a connection too long |

These limits have different scopes. For instance, a pool's `maxAcquireTime` is not SQL execution time; an HTTP client's `responseTimeout` is not necessarily total request duration; a `Mono` timeout does not guarantee the database stopped processing.

### 1.1. Distinguishing timeouts from idle timeouts

Some settings limit inactivity on a connection, such as an HTTP connection idle timeout or pool max idle time. They reclaim unused resources, not enforce a deadline on an active request.

Similarly, maximum connection lifetime in a pool (`maxLifeTime`) is not a query timeout. Never see a setting containing the word "timeout" or "time" and assume it protects every stage.

### 1.2. Timeouts are not completed cancellations

When a caller times out, the application may emit `TimeoutException` and send cancellation upstream. From there:

- The publisher may stop emitting items.
- The driver may issue a cancel command or close/discard the connection.
- The database may abort the statement, or take additional time to process cancellation.
- The transaction may roll back if uncommitted and the transaction manager handles cancellation properly.
- If the connection drops right during commit, the commit outcome may be uncertain.

Thus, a timeout signals that the caller did not receive a result in time. It does not always prove a write operation did not occur.

## 2. Designing an end-to-end time budget

Start with the question: how long is this API allowed to take from the moment the server receives the request until it returns a response?

Example API with a 2.5-second application budget:

| Component | Illustrative limit |
| --- | ---: |
| Client waiting for response | 3,200 ms |
| Gateway/reverse proxy | 3,000 ms |
| Entire application pipeline | 2,700 ms |
| Single downstream HTTP call | 700 ms |
| R2DBC pool acquire wait | 250 ms |
| Opening a new connection | 500 ms |
| SQL statement | 1,200 ms |
| Remaining validation, mapping, response, and cleanup | Remaining budget |

This is an illustrative example only. Steps may run sequentially or in parallel; if sequential, their combined durations must fit inside the budget. If parallel, the overall deadline still caps the entire group's wait time.

### 2.1. Inner timeouts should be shorter than outer timeouts

A useful rule of thumb:

~~~text
Database statement timeout
          <
Transaction budget
          <
Application deadline
          <
Gateway timeout
          <
Client timeout
~~~

This ordering leaves room for the application to catch dependency errors, roll back/clean up, build an error response, and send it before the caller or gateway closes the connection.

Not every timeout is strictly nested. For example, WebClient and R2DBC may be two sequential dependencies in one service; partition the budget between them while keeping an overall deadline for the entire pipeline.

### 2.2. Leave room for cleanup and sending the response

If the gateway closes requests after 2 seconds and the application also times out at exactly 2 seconds, the application may lack time to handle errors, roll back, log, or send a response. Set the application deadline sensibly lower than the gateway's timeout.

The buffer depends on real latency, network jitter, and how the gateway handles responses. No single constant fits all systems.

### 2.3. Do not add timeouts mechanically

Suppose a pipeline has:

1. Pool acquire wait up to 250 ms.
2. Query up to 1,200 ms.
3. Downstream service call up to 700 ms.

If all three run sequentially, the sum of stage limits approaches 2,150 ms before mapping and cleanup. If two dependencies run in parallel, group wait time is governed by the slowest branch, not the sum of both timeouts.

An overall timeout must still span the entire pipeline. Per-stage timeouts pinpoint bottlenecks; the overall deadline protects the caller.

## 3. Setting a timeout on the entire reactive pipeline

Reactor provides the `timeout` operator. On a `Mono`, if the source emits no result within the specified duration, the publisher emits `TimeoutException` and cancels upstream.

~~~java
public Mono<OrderResponse> getOrder(Long orderId) {
    return orderService.findOrder(orderId)
            .map(OrderResponse::from)
            .timeout(Duration.ofSeconds(2));
}
~~~

This timeout bounds the wrapped publisher starting at subscription time. It encompasses pool wait, query time, and chained steps inside `orderService`.

### 3.1. Place timeouts at the application/service boundary

Deadlines usually belong at the use-case or request boundary where all work is visible:

~~~java
public Mono<OrderResponse> handle(GetOrderQuery query) {
    return orderService.getOrder(query.orderId())
            .flatMap(this::loadCustomer)
            .map(OrderResponse::from)
            .timeout(Duration.ofMillis(2500));
}
~~~

Wrapping only the repository query leaves authorization, secondary service calls, or downstream mapping unbounded.

### 3.2. Timeouts for a specific stage

You can also enforce a dedicated limit on a single dependency:

~~~java
public Mono<Customer> loadCustomer(Long customerId) {
    return customerRepository.findById(customerId)
            .timeout(Duration.ofMillis(1200));
}
~~~

If this stage times out, the failure can be handled locally or propagated to the overall deadline. Avoid putting identical timeouts on every layer without an explicit budget; doing so makes it unclear which timeout actually triggered.

### 3.3. Mono.timeout and Flux.timeout have different semantics

For `Mono`, `timeout` generally bounds time waiting for a value or completion. For `Flux.timeout(Duration)`, the timer applies between signals: if no next element arrives within the interval, it times out. This acts as an **idle/inter-signal timeout**, not a total maximum duration for the entire stream.

Example:

~~~java
return orderRepository.findAllByCustomerId(customerId)
        .timeout(Duration.ofSeconds(3));
~~~

If rows arrive less than 3 seconds apart, the stream can run far longer than 3 seconds without timing out. To cap total stream duration, implement a separate overall deadline. `take(Duration)` stops a stream after a duration while completing normally; it does not signal a timeout error. Choose semantics matching your API contract.

### 3.4. Never silently truncate data with a timeout

If an API returns a list and times out mid-stream, never return partial results as though the query succeeded completely. Decide whether the API supports partial results. When completeness is required, emit an error so the response cannot be mistaken for a complete list.

## 4. Propagate a deadline instead of resetting full timeouts at each layer

A common design mistake is every service applying its own 2-second timeout:

~~~text
HTTP handler: 2 seconds
    -> Order service: 2 seconds
        -> Customer service: 2 seconds
            -> Repository: 2 seconds
~~~

These timeouts do not produce a 2-second request deadline. When steps run sequentially, total time can far exceed 2 seconds.

Create a single deadline at the request boundary and pass the remaining time down to dependencies. Within one process, use the monotonic clock `System.nanoTime()` to avoid skew from wall-clock adjustments.

### 4.1. A local deadline type

~~~java
public record RequestDeadline(long expiresAtNanos) {

    public static RequestDeadline after(Duration budget) {
        return new RequestDeadline(
                System.nanoTime() + budget.toNanos());
    }

    public Duration remaining() {
        long nanos = expiresAtNanos - System.nanoTime();
        return Duration.ofNanos(Math.max(0, nanos));
    }

    public Duration requireRemaining() {
        Duration remaining = remaining();
        if (remaining.isZero() || remaining.isNegative()) {
            throw new DeadlineExceededException();
        }
        return remaining;
    }
}
~~~

This deadline is meaningful only within the same process because `nanoTime` values cannot be sent across machines.

### 4.2. Storing the deadline in Reactor Context

~~~java
public final class DeadlineContext {

    public static final String KEY = "requestDeadline";

    private DeadlineContext() {
    }

    public static Mono<RequestDeadline> current() {
        return Mono.deferContextual(context -> {
            if (!context.hasKey(KEY)) {
                return Mono.error(new IllegalStateException(
                        "Request deadline is missing"));
            }
            return Mono.just(context.get(KEY));
        });
    }

    public static <T> Mono<T> withDeadline(
            Duration budget,
            Mono<T> work) {
        RequestDeadline deadline = RequestDeadline.after(budget);
        return work
                .timeout(deadline.requireRemaining())
                .contextWrite(context -> context.put(KEY, deadline));
    }
}
~~~

This example demonstrates a deadline in a single pipeline. In real deployments, create the deadline before starting work and share the same deadline across all stages. Do not create a fresh deadline in every service if you want to preserve the original budget.

### 4.3. Computing remaining timeout per dependency

~~~java
public Mono<Customer> loadCustomer(Long id) {
    return DeadlineContext.current()
            .flatMap(deadline -> {
                Duration stageLimit = Duration.ofMillis(700);
                Duration remaining = deadline.requireRemaining();
                Duration timeout = remaining.compareTo(stageLimit) < 0
                        ? remaining
                        : stageLimit;

                return customerClient.getCustomer(id)
                        .timeout(timeout);
            });
}
~~~

The stage has its own 700 ms cap yet cannot exceed the request's remaining budget. If only 150 ms remain, it gets at most 150 ms.

### 4.4. Propagating deadlines across services

`System.nanoTime()` applies only inside the current process. When calling another HTTP service, pass the remaining budget via an agreed header or use your protocol's native deadline mechanism.

Passing absolute timestamps exposes you to clock skew between hosts. Passing remaining duration still consumes budget over network transit; the receiving service should subtract elapsed time or follow a unified deadline convention. Never let each service reset a full new timeout.

## 5. Timeouts when acquiring a connection from the R2DBC pool

The R2DBC pool manages reusable connections. When no connection is available, requests wait for a connection to be returned or for the pool to open a new one.

R2DBC Pool allows configuring limits such as:

- `maxAcquireTime`: maximum wait time to acquire a connection.
- `maxCreateConnectionTime`: maximum time to open a new connection.
- `maxIdleTime`: idle duration before a connection is evicted.
- `maxLifeTime`: maximum connection lifetime.
- `maxValidationTime`: maximum time to validate a connection.

The first two limits directly govern how long a request may wait before starting a query. The idle/lifetime limits manage connection lifecycle, not query deadlines.

### 5.1. Configuring ConnectionPool

Example with `r2dbc-pool`:

~~~java
ConnectionPoolConfiguration configuration =
        ConnectionPoolConfiguration.builder(connectionFactory)
                .initialSize(5)
                .maxSize(30)
                .maxAcquireTime(Duration.ofMillis(250))
                .maxCreateConnectionTime(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofMinutes(5))
                .maxLifeTime(Duration.ofMinutes(30))
                .build();

ConnectionPool pool = new ConnectionPool(configuration);
~~~

Values are examples only. Builder APIs and bean declarations depend on your `r2dbc-pool`/Spring Boot versions. When Spring Boot auto-configures a pool, set the supported configuration properties rather than constructing a second parallel pool.

### 5.2. maxAcquireTime bounds pool wait time

If a pool has 30 connections and all are busy, new requests wait. Once `maxAcquireTime` is exceeded, acquire fails rather than waiting forever.

This signals pool saturation or overly long connection hold times. Raising `maxAcquireTime` often just lengthens queues and causes outer layers to time out.

### 5.3. maxCreateConnectionTime bounds opening new connections

When the pool must open a connection, the driver connects to the database. If the database is unresponsive or network issues occur, connection creation can stall. This limit differs from waiting for an existing pooled connection.

Additionally, the driver may expose its own connect timeout for TCP/network handshakes. Check your driver and version; do not assume one pool property covers DNS, TCP, TLS, and authentication.

### 5.4. Monitor the pool rather than just raising limits

When acquire timeouts occur, inspect:

- Are active/acquired connections frequently hitting `maxSize`?
- Is pending acquire rising?
- What are average and p95 connection hold times?
- Which queries or transactions hold connections too long?
- Are HTTP calls or CPU-heavy tasks running inside open transactions?
- Does total pool size across all replicas exceed database capacity?

A larger pool can increase load on the database and slow down every query. Adjust limits only after identifying the root cause.

## 6. Timeouts when creating database connections

Connection creation can span DNS lookup, TCP connect, TLS handshake, authentication, and session initialization. Some steps are controlled by the driver or OS, not all by `maxAcquireTime`.

Check which connection options your R2DBC driver supports, such as connect timeout. Option names, types, and effective scope vary by driver. Never copy a JDBC setting like `socketTimeout` into R2DBC without confirming driver support.

### 6.1. Separate connection creation errors from query errors

If a connection was never created, the database never received the request's statement. If a connection existed and the query started, failures can happen during execution or result consumption. Both cases need separate metrics and handling.

Logs/traces should record the phase:

- Pool acquire.
- Connection creation.
- Statement execution.
- Result consumption.
- Transaction commit/rollback.

Never log credentials or URLs containing passwords.

### 6.2. Connection timeouts do not replace health checks

Connection timeouts protect requests from hanging indefinitely. Health checks detect unhealthy dependencies and steer traffic away. The two mechanisms complement each other; health checks should avoid opening excessive new connections or running heavy queries continuously.

## 7. Limiting SQL execution time

A query can be slow due to an execution plan, lock waits, I/O, large datasets, or database overload. Using only `Mono.timeout` stops the application from waiting, but does not guarantee the database stopped the statement.

Enforce database/statement-level limits where driver-supported, especially for potentially slow queries or endpoints with tight deadlines.

### 7.1. Statement timeout in R2DBC SPI

R2DBC SPI 1.0 includes `Connection.setStatementTimeout(Duration)` on supporting drivers. Support level and enforcement timing depend on the driver/database; check actual driver documentation and test rather than assuming identical behavior across implementations.

When using connection-level timeouts, apply them to the connection executing the statement and ensure scoping is clean. On pooled connections, prevent a prior request's timeout from leaking into subsequent requests; reset or scope per transaction/connection lifecycle.

### 7.2. PostgreSQL statement_timeout

PostgreSQL supports `statement_timeout`. You can set it transaction-locally so it applies only to the current transaction:

~~~sql
SET LOCAL statement_timeout = '1200ms';
~~~

Or use `set_config`:

~~~sql
SELECT set_config('statement_timeout', '1200ms', true);
~~~

The trailing `true` scopes the setting to the current transaction. Both the setting statement and the query must run on the same transaction/connection.

### 7.3. Setting PostgreSQL timeouts in a reactive transaction

Example using `DatabaseClient` and `TransactionalOperator`:

~~~java
public Mono<Order> findWithStatementBudget(Long orderId) {
    Mono<Void> setStatementTimeout = databaseClient
            .sql("SET LOCAL statement_timeout = '1200ms'")
            .fetch()
            .rowsUpdated()
            .then();

    Mono<Order> query = orderRepository.findById(orderId);

    return transactionalOperator.transactional(
            setStatementTimeout.then(query));
}
~~~

This example is PostgreSQL-specific. `SET LOCAL` is meaningful only inside a transaction. Verify that the transaction manager uses the same `ConnectionFactory` and all statements execute on the transaction-bound connection. Never run `SET` in an isolated publisher outside a transaction expecting the connection pool to preserve the setting for the next query.

### 7.4. Lock timeout differs from statement timeout

A query can spend negligible CPU while blocked on a lock. Databases typically provide a separate lock wait timeout. For example, PostgreSQL offers `lock_timeout`, whereas `statement_timeout` bounds total statement duration.

With only a large statement timeout, a lock-blocked query can burn most of its budget before being cancelled. Set lock timeout lower than statement timeout if business logic cannot tolerate long lock waits.

~~~sql
SET LOCAL lock_timeout = '300ms';
SET LOCAL statement_timeout = '1200ms';
~~~

Values must reflect SLOs and database behavior. Avoid excessively low lock timeouts if the workload has frequent legitimate concurrent contention.

### 7.5. Database query timeouts must be verified empirically

Integration tests should run a query with a predictable wait or intentional delay, verifying the database cancels the statement at the configured limit and the connection remains safely reusable afterward.

Do not only assert that WebFlux returns a timeout. Verify whether the query keeps running on the database, whether the connection is evicted or cleaned up, and whether the transaction rolls back properly.

## 8. Transaction timeouts

Long transactions hold connections and may hold locks, reducing pool and database capacity. Bound transactions according to business needs.

Spring's transaction definition includes a `timeout` attribute usable on methods:

~~~java
@Transactional(timeout = 3)
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(Order.from(command))
            .flatMap(saved -> orderAuditRepository.save(
                    OrderAudit.created(saved.getId()))
                    .thenReturn(saved));
}
~~~

The annotation's timeout is specified in seconds. Exact enforcement depends on the reactive transaction manager, R2DBC driver, and how transaction timeouts are applied. Do not treat this annotation as a substitute for database statement timeouts or overall request deadlines.

### 8.1. Transactions should not wait on slow HTTP services

Avoid:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(Order.from(command))
            .flatMap(saved -> paymentWebClient.authorize(saved)
                    .thenReturn(saved));
}
~~~

This holds a database transaction open while waiting on HTTP payment authorization. If the payment service stalls, the connection and transaction stay pinned.

Consider persisting the order and an outbox event within the transaction, then processing payment via a workflow/outbox worker. If synchronous behavior is mandatory, enforce tight timeouts, cap concurrency, and design proper compensation/idempotency.

### 8.2. Timeouts/cancellation inside transactions

When a pipeline times out, cancellation can cause the transaction manager to roll back if the transaction has not committed. Yet if failure occurs right during commit or connection drop, callers cannot tell whether commit succeeded.

For critical writes, use a stable idempotency key or business reference so callers can safely query/retry. Never generate a brand-new insert key simply because the first request timed out.

## 9. Timeouts for HTTP clients in WebFlux

WebFlux apps frequently call other services with `WebClient`. Distinguish:

- TCP connect timeout: time to open the socket.
- TLS handshake timeout: time to complete TLS, per client/config.
- Response/read timeout: time waiting for response data per client semantics.
- Reactive publisher timeout: total time for the wrapped operation.

### 9.1. Configuring Reactor Netty HttpClient

Example:

~~~java
HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 300)
        .responseTimeout(Duration.ofMillis(700));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
~~~

Connect timeout bounds only the connect phase. Reactor Netty's `responseTimeout` bounds reading the response per Reactor Netty semantics; do not automatically assume it is an overall deadline covering every request step.

### 9.2. Adding an overall timeout to a WebClient publisher

~~~java
public Mono<CustomerResponse> getCustomer(Long customerId) {
    return webClient.get()
            .uri("/customers/{id}", customerId)
            .retrieve()
            .bodyToMono(CustomerResponse.class)
            .timeout(Duration.ofMillis(900));
}
~~~

This overall timeout spans the publisher from subscription across the HTTP exchange steps within it. It does not replace connect/read timeouts, since granular timeouts reveal exactly which stage hung.

### 9.3. WebClient timeouts must fit within the parent request deadline

If the parent request has only 200 ms left, never call `WebClient` with a fresh 900 ms timeout. Use the remaining deadline—typically the minimum of the stage limit and remaining time.

### 9.4. HTTP retries also consume budget

If `WebClient` retries twice, every connect/response timeout consumes time. Wrap the overall timeout outside the retry chain; never reset a full deadline for each attempt.

For write requests or payment calls, retry only when the operation is idempotent or the provider supports idempotency keys. A timeout does not prove the target server never processed the request.

## 10. Timeouts at the HTTP server, gateway, and client

Inbound timeouts involve several separate settings:

- Reverse proxies can limit upstream response wait time.
- Load balancers may enforce idle timeouts or request timeouts.
- HTTP servers can bound connections, request reads, response writes, or idle durations.
- Application pipelines need use-case deadlines.
- Clients may stop waiting before the server finishes.

A server connection idle timeout is not necessarily total request processing time. Read the exact semantics of your server/runtime—whether Reactor Netty, Tomcat, or Jetty.

### 10.1. Placing deadlines at the request boundary

You can use a filter to attach a deadline to reactive context or wrap pipelines per application policy. Take care because filters may encompass response body writing; test with streaming responses and cancellation.

Illustrative deadline in an application service/handler:

~~~java
public Mono<ServerResponse> handle(ServerRequest request) {
    Mono<OrderResponse> result = orderService.getOrder(
            Long.valueOf(request.pathVariable("id")));

    return result.timeout(Duration.ofMillis(2500))
            .flatMap(body -> ServerResponse.ok().bodyValue(body));
}
~~~

This bounds the business publisher. Reverse proxies and servers still require their own configurations.

### 10.2. HTTP status codes on timeout

No single status fits all timeouts:

| Scenario | Status commonly considered |
| --- | --- |
| Client failed to send full request in time | `408 Request Timeout` |
| Gateway waited too long on upstream | `504 Gateway Timeout` |
| Application temporarily unable to serve due to dependency/capacity | `503 Service Unavailable` per API contract |
| Unclassified internal failure | `500 Internal Server Error` |
| Client sent a precondition no longer valid | `412 Precondition Failed`, not a timeout |

If your application acts as a gateway to another service and the dependency times out, `504` may fit. If the service is temporarily unavailable or overloaded, `503` may fit. Maintain a consistent error contract and never return stack traces.

## 11. Combining timeouts with retries

Retries help overcome transient faults, yet can also push requests past deadlines and add load during overload.

Bounded retry example:

~~~java
Mono<Order> attempt = orderRepository.findById(orderId);

return attempt
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100))
                .maxBackoff(Duration.ofMillis(400))
                .filter(this::isTransientFailure))
        .timeout(Duration.ofSeconds(2));
~~~

Placing `timeout` outside the retry chain bounds the combined duration of all attempts and backoff delays. Placing a fresh timeout inside each retry attempt without an overall deadline lets total time blow past the budget.

### 11.1. Do not retry every timeout

A timeout often signals that the database or pool is already saturated. Retrying immediately piles on more waiting requests and worsens the situation.

Retry only when:

- The failure is classified as transient.
- Sufficient deadline remains.
- Retry count is bounded.
- Backoff is bounded and optionally jittered.
- The operation is safe to re-execute.

### 11.2. Do not blindly retry pool saturation

When a pool is out of connections, retrying acquire repeatedly swells wait queues. It is usually better to fail fast, return an appropriate service-unavailable error, and let load shedding/backpressure protect the system.

### 11.3. Data writes require idempotency

If a timeout happens after database commit but before the application gets the response, retrying an `INSERT` can create a second record. Use a stable idempotency key, unique constraint, or business reference so duplicate requests return the original outcome.

For HTTP providers, pass the same idempotency key across retries if supported. A reactive timeout is no proof the request never reached the destination service.

## 12. Cancellation and resource cleanup

Reactor timeouts cancel upstream subscriptions when deadlines expire. Drivers can receive cancellation and abort queries, though exact behavior must be verified.

### 12.1. Never swallow cancellation

Avoid spawning detached publishers via manual `subscribe()`:

~~~java
public Mono<Order> load(Long id) {
    orderRepository.findById(id).subscribe();
    return Mono.just(new Order());
}
~~~

This detaches the database operation from the request lifecycle. Caller timeouts or disconnects cannot cancel the independent subscription.

Always return publishers within the same chain so cancellation propagates upstream:

~~~java
public Mono<Order> load(Long id) {
    return orderRepository.findById(id);
}
~~~

### 12.2. Inspecting connections after query timeouts

After a statement timeout or cancellation:

- Is the connection still valid or closed?
- Does the pool discard broken connections?
- Did the transaction roll back?
- Is a query still running on the database?
- Do subsequent requests acquire and use connections normally?

If the driver cannot guarantee a connection is in a clean state after cancellation, it must discard the connection from the pool per driver behavior. Test against your real database and driver.

### 12.3. Client disconnects

When a client closes the socket, the server can receive cancellation depending on runtime and timing. Ensure publishers do not continue unnecessary work. For already-committed writes, client disconnects cannot undo persisted data; idempotency and business state tracking remain essential.

## 13. Observing timeouts in production

A single `request_timeout_total` metric is not enough to locate bottlenecks. Categorize by phase:

| Metric/log category | Meaning |
| --- | --- |
| `http_request_deadline_exceeded` | End-to-end deadline expired |
| `webclient_connect_timeout` | Failed to connect to downstream service in time |
| `webclient_response_timeout` | Waited too long for response per client config |
| `r2dbc_pool_acquire_timeout` | Pool failed to lease a connection in time |
| `r2dbc_connection_create_timeout` | Failed to open a new connection in time |
| `r2dbc_statement_timeout` | Statement exceeded limit |
| `transaction_timeout` | Transaction exceeded budget |
| `request_cancelled` | Request cancelled by client disconnect or upstream cancellation |

Metric names are illustrative conventions; match your project's instrumentation naming.

### 13.1. Recording per-stage durations

Traces or observations can record:

- Connection acquire duration.
- Statement execution and result consumption duration.
- Transaction duration.
- WebClient connect/response duration.
- Total use-case duration.

Separating pool wait time from query execution time prevents optimizing the wrong component.

### 13.2. Avoid high cardinality

Never put request IDs, user IDs, or individual tenant IDs in metric tags if cardinality is high. Use traces/logs for per-request detail and keep metric tags bounded—such as operation, dependency, outcome, and timeout phase.

### 13.3. Log remaining deadline

On timeout, log initial deadline/budget, remaining time at the dependency, failing phase, and correlation ID. Never log tokens, passwords, or sensitive data.

## 14. Testing timeouts and cancellation

Test both reactive logic and real driver/database behavior. A unit test for `timeout` does not prove the database actually cancels a query.

### 14.1. Unit testing Mono.timeout with virtual time

~~~java
@Test
void shouldTimeoutWhenPublisherDoesNotRespond() {
    StepVerifier.withVirtualTime(() ->
                    Mono.<String>never()
                            .timeout(Duration.ofSeconds(2)))
            .thenAwait(Duration.ofSeconds(2))
            .expectError(TimeoutException.class)
            .verify();
}
~~~

Virtual time works for operators backed by Reactor schedulers. External publishers or real drivers may not use virtual schedulers, so unit tests never replace integration tests.

### 14.2. Testing overall timeouts wrapping retries

Create an attempt publisher with deterministic latency and retry policy. Verify total duration is bounded by the outer deadline rather than resetting per attempt.

Also assert actual attempt count to confirm retries stop once the request deadline expires.

### 14.3. Testing pool acquire timeouts

With a small pool, hold all connections using controlled test operations, then issue a new acquire. Verify the acquire fails within the configured bound and pending/acquire timeout metrics are recorded.

Never let tests hang indefinitely; always guard tests themselves with timeouts.

### 14.4. Testing statement timeouts with a real database

With PostgreSQL, you can use a sleeping statement like `SELECT pg_sleep(2)` inside a transaction with a shorter `statement_timeout`. Verify:

1. The statement is cancelled at the database limit.
2. The application receives the corresponding timeout error.
3. The transaction rolls back or ends cleanly.
4. No broken connection is returned to the pool.
5. Subsequent queries on the pool execute normally.

This test is PostgreSQL-specific. For other databases, use equivalent queries/tools for that DBMS.

### 14.5. Testing cancellation on client disconnect

Create a streaming endpoint or controlled slow query, then cancel the request from `WebTestClient` or an HTTP test client. Observe publisher cancellation, database statements, and the connection pool. Verify no detached subscription continues running.

### 14.6. Testing deadline propagation

Attach a short deadline to the request context and invoke multiple mock dependencies. Verify downstream dependencies receive only the remaining time, never the full initial timeout. Test both sequential and parallel branches.

## 15. Common pitfalls when configuring timeouts

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Requests wait long despite short SQL timeout | Pool wait or other services are unbounded | Set per-phase timeouts and an overall deadline |
| Pool acquire timeouts occur before queries | Pool exhausted or connections held too long | Track pending/hold time and shorten transactions |
| Raising acquire timeout makes API slower | Queue grows instead of adding capacity | Keep budget tight, find bottleneck, and shed load |
| WebClient waits longer than expected | Only connect timeout set, missing response/overall timeout | Configure connect, response, and publisher deadlines |
| Mono times out while DB keeps running query | Cancellation does not stop server statement immediately | Enforce database statement timeout and test driver |
| Flux never times out despite long total runtime | `Flux.timeout(Duration)` is an inter-signal timeout | Implement a separate overall stream deadline |
| Retries push requests past deadline | Each attempt resets a full timeout | Wrap overall timeout around retry chain and use remaining budget |
| Write timeout followed by retry duplicates rows | Commit succeeded even though ACK was lost | Use idempotency keys/unique business keys |
| Transactions hold connections during HTTP calls | External call runs inside transaction | Shorten transactions, use outbox/saga or tight timeouts |
| Pool behaves oddly after timeout | Connection/session state or cancellation not cleaned up | Inspect driver and pool lifecycle |
| Gateway returns 504 before application | Gateway timeout shorter than app deadline | Order budgets and leave cleanup margin |
| HTTP server idle timeout mistaken for request deadline | Setting only bounds connection inactivity | Enforce deadlines in the application pipeline |
| Long database lock waits | Large statement timeout or missing lock timeout | Set lock timeout aligned with business rules |
| Timeout tests pass while production hangs | Unit tests do not exercise real driver/database | Run integration tests on a production-like database |

## 16. Process for designing timeouts for an endpoint

1. Determine SLOs and maximum caller wait time.
2. Set the application deadline below gateway/client timeouts to reserve cleanup margin.
3. List dependencies and identify sequential vs. parallel steps.
4. Allocate budgets for HTTP clients, pool acquire, connection creation, SQL, and transactions.
5. Wrap an overall timeout around the entire use case.
6. Propagate remaining deadline rather than creating new full timeouts per layer.
7. Configure database/driver statement and lock timeouts where supported.
8. Ensure retries are bounded, fit inside the deadline, and are idempotent-safe.
9. Monitor timeouts by phase, pool metrics, and database health.
10. Test timeouts, cancellation, rollbacks, and connection reuse with real drivers/databases.

## 17. Example unified timeout budget configuration

Suppose an order-read endpoint has a 2,500 ms application budget:

~~~text
Client timeout:                3,200 ms
Gateway upstream timeout:     3,000 ms
Application deadline:         2,500 ms
  |
  +-- R2DBC pool acquire:       250 ms
  |
  +-- Database transaction:   1,600 ms
  |     |
  |     +-- Statement timeout: 1,200 ms
  |     +-- Lock timeout:       300 ms
  |
  +-- WebClient dependency:     700 ms
  |
  +-- Mapping/response/cleanup: remaining budget
~~~

In this example, R2DBC and WebClient may run sequentially or in parallel depending on the use case. If sequential, adjust stage limits so worst-case sum stays under the application deadline. If parallel, the overall deadline still caps the whole group.

Never copy these numbers into production without measuring. Base limits on actual p95/p99 latencies, SLOs, and capacity.

## 18. Operational checklist

- [ ] End-to-end deadlines exist for each critical API group.
- [ ] Gateway/proxy/client timeouts are ordered relative to the application deadline.
- [ ] Per-dependency timeouts do not reset the full budget.
- [ ] R2DBC pool acquire wait is bounded.
- [ ] Connection creation is bounded per driver capabilities.
- [ ] Pool idle/lifetime settings are understood as connection management, not query deadlines.
- [ ] Database or driver statement timeouts are configured where appropriate.
- [ ] Lock timeouts are configured if business logic rejects long lock waits.
- [ ] Transactions are short and avoid unnecessary external service waits.
- [ ] WebClient has appropriate connect, response, and overall timeouts.
- [ ] Retries are bounded and fit within the overall deadline.
- [ ] Write retries use idempotency/business keys.
- [ ] Cancellation propagates within the same reactive chain.
- [ ] Metrics distinguish pool, connect, SQL, HTTP, and application timeouts.
- [ ] Integration tests run against real drivers/databases.
- [ ] Connection reuse is tested after statement timeouts/cancellation.

## 19. End-to-end timeout handling flow

~~~mermaid
flowchart TD
    A[Client sends HTTP request] --> B[Gateway timeout budget]
    B --> C[Application creates deadline]
    C --> D[Reactive service]
    D --> E[Acquire R2DBC connection]
    E --> F{Connection acquired in time?}
    F -->|No| G[Pool acquire timeout]
    F -->|Yes| H[Execute SQL]
    H --> I{Statement finishes in time?}
    I -->|No| J[Statement timeout/cancel]
    I -->|Yes| K[Call dependency if needed]
    K --> L{Dependency finishes in time?}
    L -->|No| M[HTTP dependency timeout]
    L -->|Yes| N[Map and build response]
    G --> O[Rollback/cleanup and map error]
    J --> O
    M --> O
    N --> P[Return response before gateway deadline]
    O --> Q[Return error before gateway deadline if connected]
~~~

## 20. Conclusion

Controlling timeouts in Spring Data R2DBC is far more than calling `Mono.timeout`. A request traverses HTTP, the application, the connection pool, connection creation, SQL, transactions, and potentially downstream services. Each stage needs semantically appropriate bounds; the overall deadline must span the entire use case while leaving margin for cleanup and response delivery.

Distinguish pool acquire timeouts, connection creation timeouts, statement timeouts, transaction timeouts, HTTP connect/read timeouts, and application deadlines. Use Reactor timeouts to bound publishers, configure pools to avoid unbounded connection waits, enforce database statement/lock timeouts where supported, and verify real cancellation behavior. With `Flux`, distinguish inter-signal idle timeouts from total stream duration.

Retries must fit inside the overall deadline, apply only to transient failures, and reuse idempotency keys for writes. A timeout does not prove the database did not commit or the target service did not process the request. Finally, track timeouts by phase and test with real databases/drivers to guarantee queries stop, transactions resolve cleanly, and connections remain safe for reuse.
