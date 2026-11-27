# Timeout execution in Spring for GraphQL

A GraphQL request may need to call multiple resolvers, databases, and external services before producing a response. If a dependency hangs or an operation consumes too many resources, the request can hold connections, threads, memory, and downstream capacity longer than the system permits. A timeout is a time limit to stop waiting for work and release resources once the deadline expires.

In Spring for GraphQL, distinguish between a whole-request timeout and timeouts for individual resolvers or dependencies. `TimeoutWebGraphQlInterceptor` provides request timeouts for web transports; `Mono.timeout(...)` can bound a reactive operation; database drivers and HTTP clients need their own timeouts for the I/O they manage. These layers complement each other. A bare HTTP client timeout does not guarantee that ongoing work on the server stops as well.

After this lesson, you will be able to:

- Distinguish request deadlines, resolver timeouts, downstream timeouts, and client/transport timeouts.
- Configure `TimeoutWebGraphQlInterceptor` in Spring Boot.
- Understand the HTTP status returned when a GraphQL request times out.
- Set timeouts for reactive resolvers and downstream calls.
- Distinguish inter-event timeouts from total stream timeouts.
- Understand cancellation and the limits of stopping ongoing work.
- Handle timeouts safely in GraphQL errors and mutations.
- Design timeout budgets, test them, and monitor timeouts in production.

## 1. What problem does timeout execution solve?

An operation may invoke multiple fields:

```graphql
query Dashboard {
    profile {
        displayName
    }
    orders {
        id
        total
    }
    recommendations {
        id
        title
    }
}
```

The `profile`, `orders`, and `recommendations` resolvers may call different dependencies. If the recommendation service takes 20 seconds to reply, the entire request may wait even though the other two branches already have data.

Timeouts help the system bound waiting times, thereby:

- Avoiding holding requests and connections indefinitely.
- Limiting queued work while a downstream dependency is degraded.
- Releasing reactive subscriptions when the request no longer needs results.
- Enabling error or fallback responses within the remaining time budget.
- Protecting the service from a group of slow requests exhausting all resources.

Timeouts do not make an inherently slow dependency faster. They bound how long the system is willing to wait and must be paired with query complexity limits, pagination, rate limits, bulkheads, and concurrency controls.

## 2. Distinguishing timeout types

A request can cross multiple layers, each with its own timeout:

| Layer | Timeout controls | Example |
| --- | --- | --- |
| Database/driver | Time spent waiting for a query or acquiring a connection | Database query max 600 ms |
| Downstream client | Time waiting for an HTTP/RPC response | Catalog API max 700 ms |
| Resolver | Time for a single field or pipeline | `Mono.timeout(Duration)` |
| GraphQL request | Maximum time to produce a request response | `TimeoutWebGraphQlInterceptor` |
| Gateway/proxy | Time the gateway waits for upstream | Reverse proxy timeout 2.5 seconds |
| Client | Time the client application waits for a response | Mobile client timeout 3 seconds |

These timeouts do not synchronize automatically. For example, a client may stop waiting after 2 seconds while the server keeps running the query for 10 seconds if there is no cancellation or server-side timeout. Conversely, the server can return a timeout before the client stops waiting.

Design deadlines from the inside out. Dependencies need shorter timeouts than resolvers; request timeouts must leave enough room for parallel resolvers and fallbacks; gateways/clients should wait slightly longer than the server request timeout so they receive the server's timeout response.

## 3. TimeoutWebGraphQlInterceptor

Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` to enforce request timeouts for web transports. The interceptor bounds the time from when a request enters the web GraphQL interceptor chain until the response is materialized.

When a timeout occurs, the interceptor sends a cancellation signal up the chain. Reactive data fetchers can receive cancellation and abort ongoing work. Over HTTP, the interceptor defaults to returning `408 Request Timeout`; an overloaded constructor lets you pick another status.

`TimeoutWebGraphQlInterceptor` was introduced in Spring for GraphQL 1.4.0. If your project uses an older version, implement timeouts at the web layer or upgrade to a version supporting this interceptor.

## 4. Configuring timeout in Spring Boot

In a Spring Boot application, simply declare the interceptor as a bean:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(3));
    }
}
```

Spring Boot detects `WebGraphQlInterceptor` beans and adds them to `WebGraphQlHandler`'s interceptor chain. This example sets a three-second limit for GraphQL web requests.

Do not confuse this timeout with `spring.mvc.async.request-timeout`, servlet container timeouts, or reverse proxy timeouts. They belong to different layers and can coexist. Verify which layer terminated the request in logs and tests instead of tweaking one property and assuming all underlying work was cancelled.

## 5. Customizing the HTTP status on timeout

The default constructor uses `HttpStatus.REQUEST_TIMEOUT`. If your API gateway or operational conventions expect another status, specify it explicitly:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;
import org.springframework.http.HttpStatus;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(
                Duration.ofSeconds(3),
                HttpStatus.GATEWAY_TIMEOUT);
    }
}
```

Choose a status consistent with the contract between your GraphQL server, gateway, and clients. With the default configuration, the HTTP timeout response is `408 Request Timeout`. If changed to `504 Gateway Timeout`, ensure monitoring and client retry policies interpret that status properly.

A request timeout in the interceptor can terminate the HTTP request before a complete GraphQL response body exists. Clients must handle HTTP statuses at the transport layer rather than assuming every timeout appears as `errors` inside a GraphQL JSON envelope.

## 6. Configuring WebGraphQlHandler manually

If building `WebGraphQlHandler` manually instead of relying on Boot auto-configuration, add the interceptor to the chain:

```java
TimeoutWebGraphQlInterceptor timeoutInterceptor =
        new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(3));

WebGraphQlHandler handler = WebGraphQlHandler
        .builder(executionGraphQlService)
        .interceptor(timeoutInterceptor)
        .build();
```

Other interceptors such as authentication, tenant context, or tracing can also be configured on the handler. Design interceptor order explicitly so authentication and context binding run before resolvers need that data.

If you declare the interceptor as a Spring bean in Boot, do not also manually add the same instance to the handler in a way that registers the timeout twice unintentionally.

## 7. Limitations of request timeouts

`TimeoutWebGraphQlInterceptor` is a timeout at the web request boundary, not a per-resolver timeout. When the request deadline expires, the entire request is terminated. This protects the server from overly long operations.

It does not replace timeouts for:

- Database queries or waiting on connection pools.
- HTTP/RPC calls to external services.
- Blocking operations that do not support cancellation.
- Publisher subscriptions after a stream is established.
- Direct `ExecutionGraphQlService` calls that bypass the web interceptor chain.
- GraphQL requests over RSocket, since `TimeoutWebGraphQlInterceptor` is for web transports.

If the application calls `ExecutionGraphQlService` from an internal integration, scheduled job, or test bypassing `WebGraphQlHandler`, `TimeoutWebGraphQlInterceptor` is not applied automatically. Set timeouts at the caller or on the corresponding publisher/dependency.

## 8. Setting a timeout on a reactive resolver with Mono.timeout

When a single field has a shorter SLA than the request deadline, place a timeout directly on the field's publisher:

```java
import java.util.concurrent.TimeoutException;

@QueryMapping
public Mono<BookView> book(@Argument String id) {
    return bookService.findById(id)
            .timeout(Duration.ofMillis(800));
}
```

If `bookService.findById` fails to emit a result within 800 ms, Reactor emits a timeout error and cancels the upstream subscription. The GraphQL engine receives the error from the resolver and handles it via the configured exception mapping.

This is a timeout for the field publisher. Other fields in the same query can still complete; the GraphQL response can return partial data alongside errors if schema nullability allows.

Resolver timeouts do not bound the entire operation. A query with multiple parallel resolvers taking 700 ms each may finish in roughly 700 ms concurrently, or take longer when dependencies run sequentially. Use a request timeout to enforce an overall deadline.

## 9. Mapping timeouts to GraphQL errors

For resolver-level timeouts, errors can be mapped to GraphQL errors via `@GraphQlExceptionHandler` or `DataFetcherExceptionResolver`.

Example converting a timeout into a domain exception:

```java
@QueryMapping
public Mono<BookView> book(@Argument String id) {
    return bookService.findById(id)
            .timeout(Duration.ofMillis(800))
            .onErrorMap(TimeoutException.class,
                    error -> new BookServiceTimeoutException(id, error));
}
```

The handler can return a stable error code:

```java
@ControllerAdvice
public class GraphQlErrorHandler {

    @GraphQlExceptionHandler
    public GraphQLError handleBookServiceTimeout(
            BookServiceTimeoutException exception,
            DataFetchingEnvironment environment) {

        return GraphqlErrorBuilder.newError(environment)
                .message("Book service timed out")
                .extensions(Map.of("code", "BOOK_SERVICE_TIMEOUT"))
                .build();
    }
}
```

`GraphqlErrorBuilder.newError(environment)` attaches the path and location of the field being resolved. Never expose internal exception messages, downstream URLs, SQL, or stack traces to clients.

Note: this handler applies to field timeouts during GraphQL execution. Timeouts from `TimeoutWebGraphQlInterceptor` occur at the request boundary and are normally represented as an HTTP status rather than a field error.

## 10. Timeouts for Flux: idle timeout vs total timeout

With `Flux`, understand the semantics of `timeout(Duration)`: the operator signals a timeout if no next signal arrives within the specified interval. Therefore, it usually acts as an inter-event wait limit, not necessarily a total duration limit for the whole stream.

Example idle timeout:

```java
Flux<OrderEvent> events = orderEventService.events(orderId)
        .timeout(Duration.ofSeconds(10));
```

If the next event does not arrive within 10 seconds, the publisher errors with a timeout. If an event arrives every 9 seconds, the stream can continue well past 10 seconds.

If you need to cap the total time spent collecting a list for a query, apply the timeout on the publisher representing the entire collection:

```java
@QueryMapping
public Mono<List<BookView>> books() {
    return bookService.findAll()
            .collectList()
            .timeout(Duration.ofSeconds(2));
}
```

`collectList()` completes only when upstream completes; a timeout on `Mono<List<BookView>>` therefore bounds the total wait time for the list. In exchange, the list is buffered in memory before returning the response. For large datasets, use pagination/streaming instead of collecting an unbounded set.

For regular queries/mutations, Spring for GraphQL defaults to converting a data fetcher's `Flux` into a `List` in the response. Therefore, to bound total list retrieval time, place the deadline on the publisher completing the entire collection as shown above. For subscriptions, `Flux` is preserved as a stream emitting multiple response events.

For GraphQL subscriptions, inter-event timeouts and total lifetime limits are two separate policies. Subscriptions may be designed to stay open long-term; never apply a short query total timeout to such streams.

## 11. Downstream HTTP client timeouts

Resolvers frequently call external services. Configure timeouts on the HTTP client so slow connections or responses do not tie up resources indefinitely.

Example with Reactor Netty and `WebClient`:

```java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofMillis(700));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();
```

Reactor Netty's `responseTimeout` limits the maximum gap between network reads while receiving a response; it is a read-idle timeout, not the total duration of the entire HTTP call. Depending on the request, also consider connect timeout, connection pool acquire timeout, and target service timeouts. An HTTP client timeout should be shorter than the resolver timeout so the resolver still has time to run a fallback or translate errors.

If you need to bound total duration from starting the connection to receiving the full response, apply Reactor `timeout(...)` on the HTTP call's publisher. Keep both policies distinct: response read timeout detects an upstream stalling mid-response, whereas operation timeout bounds the entire call.

Do not just put `.timeout(...)` on the whole `WebClient` call while ignoring connection pool or TCP connect timeouts. If a connection cannot be established, requests can stall in stages other than response reading.

## 12. Database and connection pool timeouts

Databases can slow down due to query plans, locks, pool exhaustion, or network issues. Configure appropriate timeouts at the driver/database layer so queries can be stopped where they execute.

With JDBC, use statement query timeouts or corresponding repository/ORM settings. With R2DBC, use driver/statement configurations appropriate to your database. Pool acquire timeouts should also be configured separately because waiting for a connection differs from waiting for a SQL statement.

Illustrative JDBC example:

```java
try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setQueryTimeout(1);
    // Bind parameters and execute the query.
}
```

`setQueryTimeout` takes seconds, so `1` is only illustrative. Verify that the driver/database actually supports statement cancellation and pick a timeout aligned with your SLA. Never assume Reactor cancellation automatically stops a JDBC statement executing on another thread.

## 13. Timeout budgets and deadline propagation

Do not set every timeout to the exact same number. Allocate budgets from dependencies outward to the request boundary.

Example of a query with a 1.8-second total budget:

```text
Database query timeout       500 ms
Downstream HTTP timeout      700 ms
Resolver timeout             900 ms
GraphQL request timeout     1800 ms
Gateway/client timeout      2500 ms
```

These values are purely illustrative. A request with parallel resolvers does not necessarily require summing every resolver timeout; measure p95/p99 latencies and the actual dependency graph.

When a request crosses multiple services, propagate an absolute deadline or remaining budget rather than resetting full timeouts at each hop. If service A only has 400 ms left, service B should not wait another 2 seconds. Subtract elapsed time and reserve budget for serialization, response writing, and network return.

Retries must also fit within the same deadline. Three retries waiting 800 ms each cannot fit inside a 1.5-second request budget. Bound retry counts, backoff, and remaining time; never retry timeouts endlessly.

## 14. Cancellation and actually stopping work

Timeouts and cancellation are related, yet a timeout does not mean all work stops instantaneously.

- With reactive publishers, cancellation propagates upstream; operators and clients can release subscriptions/resources if their implementations support it.
- With `CompletableFuture`, completing a future with a timeout does not guarantee the underlying background task or I/O is cancelled.
- With blocking JDBC or synchronous SDKs, threads may keep running if the driver does not support cancellation or code does not check interruption.
- With mutations, side effects may have already committed before the response timeout fired.

Prefer APIs with native timeout/cancellation support. For blocking calls, use driver query timeouts, socket timeouts, or explicit cancellation hooks. Never treat a client closing its connection as proof that the server stopped the query.

Example verifying reactive cleanup:

```java
AtomicBoolean cancelled = new AtomicBoolean();

Mono<BookView> source = Mono.<BookView>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source.timeout(Duration.ofMillis(50)))
        .expectError(TimeoutException.class)
        .verify();

assertThat(cancelled).isTrue();
```

This test verifies that the timeout operator cancels the upstream subscription. It does not prove an external JDBC query or HTTP server always stops; write integration tests with real clients/drivers.

## 15. Timeouts in mutations and idempotency

Mutation timeouts carry special risk. The server may have already persisted changes successfully while the response fails to reach the client before the deadline. The client sees a timeout and cannot tell whether the mutation committed.

If the client retries the mutation immediately, the same action can execute twice. Mutations creating orders, processing payments, sending emails, or launching jobs should use an idempotency key or unique command ID.

Example input:

```graphql
input CreateOrderInput {
    idempotencyKey: ID!
    productId: ID!
    quantity: Int!
}
```

The server stores results keyed by idempotency key and returns the previously created result when receiving the same key again. Timeouts must never be treated as proof that a mutation failed; clients should query status or retry safely according to the API contract.

Do not expect a timeout to automatically roll back an already committed side effect. Transaction timeouts, database cancellation, and business compensation are separate mechanisms that must be designed intentionally.

## 16. Timeouts for subscriptions and streaming transports

`TimeoutWebGraphQlInterceptor` only applies to the request phase until the response stream is established. For subscriptions, once the stream starts, the interceptor does not bound the total lifetime of the stream.

Subscriptions typically need different policies:

- Initial subscription setup timeout.
- Idle timeout if no events occur for a given period.
- Heartbeat/keepalive to detect dead connections.
- Lifetime or event count limits if required by business rules.
- Dedicated timeouts on WebSocket/SSE transport handlers.
- Cleanup when the client sends complete/cancel or closes the connection.

Spring for GraphQL offers transport-specific timeout settings on handlers such as `GraphQlWebSocketHandler` and `GraphQlSseHandler`. Check the transport in use and framework version. Never apply a short HTTP request deadline to a subscription stream meant to remain open long-term.

## 17. GraphQL Java Instrumentation and timeouts

GraphQL Java `Instrumentation` provides hooks to observe parsing, validation, execution, and data fetchers. It is useful for measuring total request or per-field durations, recording metrics, and enforcing pre-execution checks.

Timing instrumentation does not automatically cancel running work. Wrapping a `CompletableFuture` with `orTimeout(...)` may complete the future exceptionally without stopping the underlying database query, HTTP call, or background task. For web transport request timeouts, prefer `TimeoutWebGraphQlInterceptor`; for bounding a dependency, use native publisher or client timeouts/cancellation.

Query depth/complexity limits and pagination should be checked before or during execution planning. They block expensive queries upfront; timeouts only terminate work after the deadline budget has already been spent.

## 18. Handling timeouts and partial data

If one resolver times out while others succeed, GraphQL execution can return partial data alongside `errors`. Exact output depends on field nullability.

Example schema:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    recommendations: [Book!]
}
```

If `recommendations` times out and the field is nullable, `book.id` and `book.title` can still be returned while `recommendations` is null and `errors` includes the path to the timed-out field.

If the field is declared non-null, null propagation bubbles up to the nearest nullable parent. Schema nullability should reflect whether a field depends on a slow or unreliable service.

Never turn every timeout into `Mono.empty()` merely to suppress errors. Doing so makes clients confuse nonexistent data with dependency timeouts. Use a dedicated error code such as `RECOMMENDATIONS_TIMEOUT` if clients need to distinguish them.

## 19. Testing request timeouts over HTTP

To test `TimeoutWebGraphQlInterceptor`, requests must pass through the web handler/HTTP transport. A test invoking resolver methods or `ExecutionGraphQlService` directly will not trigger web interceptors.

In a test application, configure a short timeout and a resolver returning a non-completing publisher:

```java
@TestConfiguration
static class TimeoutTestConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofMillis(100));
    }
}
```

Then send a request with `WebTestClient` or `MockMvc` to `/graphql`:

```java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ slowField }"))
        .exchange()
        .expectStatus().isEqualTo(HttpStatus.REQUEST_TIMEOUT);
```

This test assumes `slowField` uses a publisher that emits nothing within the timeout window and the application uses the default status. If configured with a custom status, update the assertion accordingly.

Also verify that the resolver receives cancellation and stops holding resources after timeout. To avoid flaky tests, pick a timeout large enough for the test scheduler yet still short; avoid `Thread.sleep()` to fake slowness when `Mono.never()` or a controllable publisher can be used.

## 20. Testing resolver timeouts and downstream timeouts

Resolver-level timeouts can be tested with `StepVerifier`:

```java
import java.util.concurrent.TimeoutException;

@Test
void timesOutSlowBookLookup() {
    StepVerifier.create(
            Mono.<BookView>never()
                    .timeout(Duration.ofMillis(50)))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(1));
}
```

This test verifies the Reactor operator. To verify exception mapping, execute a GraphQL operation with `GraphQlTester` and assert `errors[].extensions.code` and path. To test HTTP client or database driver timeouts, test against real adapters/drivers or a test server simulating a slow dependency.

Tests should cover:

1. Request completes before deadline and returns normal data.
2. Request exceeds deadline and returns the expected timeout HTTP status.
3. Reactive publisher receives cancellation on timeout.
4. One resolver times out while independent fields still return partial data.
5. Timeout error has the right code and path when mapped to a GraphQL error.
6. Downstream HTTP call is cancelled or terminated per client timeout.
7. Database query timeout releases statement/connection per driver behavior.
8. Subscription stream is not cut off after setup just because of a setup request timeout.
9. Mutation timeout can be safely retried using an idempotency key.
10. Gateway/client timeout exceeds server request timeout so the server's timeout response is received.

## 21. Observing timeouts in production

Track timeouts at each layer to pinpoint bottlenecks:

- GraphQL request timeout count and ratio to total requests.
- Execution p50, p95, and p99 latencies by operation/field.
- Resolver timeouts by field path.
- Downstream HTTP timeouts by service and endpoint.
- Database query timeouts, connection acquire timeouts, and pool saturation.
- Number of cancellations emitted and downstream work actually halted.
- Retry counts, fallback counts, and remaining request budget.

Attach `executionId` or trace ID to correlate logs between GraphQL requests and dependency calls. Avoid using sensitive query variables, user IDs, or resource IDs as high-cardinality metric labels.

Distinguish server-deadline timeouts from client disconnects, gateway timeouts, and dependency timeouts. Recording only a generic `request_failed` metric makes it hard to identify which layer needs tuning.

## 22. Common pitfalls

- **Setting timeouts only on the client:** the server may keep processing after the client gives up.
- **Setting only a request timeout:** database or HTTP calls may continue running if cancellation is unsupported.
- **Confusing request timeout with resolver timeout:** one bounds the whole request, the other bounds a single publisher/field.
- **Assuming `CompletableFuture.orTimeout` cancels underlying work:** future timeouts do not guarantee underlying I/O stops.
- **Using `Flux.timeout` as a total duration timeout:** it typically measures gaps between signals.
- **Applying a short request timeout to subscription lifetimes:** the interceptor only bounds stream establishment.
- **Not letting clients/gateways wait longer than the server:** gateways can close connections before the server sends its timeout status.
- **Retrying past the deadline:** each retry starts a new timeout and pushes the request over budget.
- **Swallowing timeouts into null:** clients cannot distinguish missing data from slow dependencies.
- **Retrying mutations without idempotency:** side effects may be executed twice.
- **Using timing-only instrumentation expecting auto-cancellation:** observation is not timeout enforcement.
- **Skipping cancellation tests:** the request ends while downstream resources remain held.

## 23. Workflow for designing timeout execution

When implementing timeouts in Spring for GraphQL, follow these steps:

1. Measure real latencies and define SLAs for queries and mutations.
2. Set a web-boundary request deadline with `TimeoutWebGraphQlInterceptor` if using Spring GraphQL 1.4+.
3. Choose the default `408` timeout status or a custom status matching your API contract.
4. Configure dedicated timeouts for slow resolvers and downstream clients/databases.
5. For `Flux`, distinguish idle timeouts from total collection duration.
6. Propagate remaining deadlines across services without resetting budgets on retries.
7. Ensure reactive cancellation and driver/client timeouts actually release ongoing work.
8. Map field timeouts to GraphQL errors with stable codes when partial data is desired.
9. Design idempotency for mutations that may time out after committing.
10. Configure dedicated timeouts for WebSocket/SSE subscription transports.
11. Test request, resolver, downstream, cancellation, and transport layers individually.
12. Monitor timeout rates, latency, dependencies, and cancellations in production.

Timeout execution in Spring for GraphQL must be designed in layers. `TimeoutWebGraphQlInterceptor` bounds response generation time for web requests and emits cancellation on expiration; resolver and database/HTTP client timeouts bound specific work. Ensure downstream dependencies support cancellation, propagate a shared deadline across calls, handle partial data according to schema nullability, and design mutations for safe retries. Testing each boundary and monitoring timeouts by layer protects resources while keeping the GraphQL contract clear.

## References

- [Spring for GraphQL — Request Execution and GraphQL Request Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html#graphql-request-timeout)
- [Spring for GraphQL 1.4.x — TimeoutWebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/TimeoutWebGraphQlInterceptor.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html#execution.exceptions)
- [Project Reactor — Handling Errors and Timeout](https://projectreactor.io/docs/core/release/reference/)
- [Reactor Netty — HTTP Client Timeout](https://projectreactor.io/docs/netty/release/reference/http-client.html#_httpclient_timeout)
- [GraphQL Java — Instrumentation](https://graphql-java.com/documentation/instrumentation/)
