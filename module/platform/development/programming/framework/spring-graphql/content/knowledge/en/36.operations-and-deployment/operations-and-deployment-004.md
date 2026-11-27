# Timeout configuration

A GraphQL request may invoke multiple resolvers, query databases, call other HTTP services, or wait for an asynchronous data source. If a dependency is slow, the request can hold resources longer than expected and force other requests to wait.

Timeouts set time bounds for each stage. In Spring for GraphQL, timeouts can be configured across multiple layers: GraphQL request, HTTP transport, Spring MVC async processing, SSE/WebSocket, WebClient, and database. Each timeout protects a different part of the system; there is no single value that automatically halts all work.

Spring Boot does not provide a single global `spring.graphql.timeout` property to automatically bound every GraphQL operation. For web transports, the direct integration approach is registering `TimeoutWebGraphQlInterceptor`; other properties apply only to the specific transport or dependency they govern.

## Distinguishing timeout types

Before configuring, identify precisely what is being waited on:

| Timeout type | What does it bound? | Example |
| --- | --- | --- |
| GraphQL request timeout | Time from receiving the request until the GraphQL response is ready | A query requiring multiple resolvers |
| MVC async timeout | Processing time for a Servlet request in async mode | A resolver returning an incomplete CompletableFuture |
| HTTP server/proxy timeout | Time for connecting, reading the request, or waiting for a response at the server/gateway | A reverse proxy waiting on the backend |
| WebClient connect timeout | Time to establish a connection to another HTTP service | TCP/TLS handshake to Author API |
| WebClient response/read timeout | Time waiting for response data from another service | Search service fails to respond |
| Database query/statement timeout | Time an SQL statement is allowed to run | A slow book search query |
| Transaction timeout | Time a transaction is allowed to live per the transaction manager | A data-writing use case |
| WebSocket connection-init timeout | Time a client has to send a CONNECTION_INIT message after opening the socket | A client opens a socket without authenticating |
| SSE response-start timeout | Time spent waiting to create the response to start an SSE stream | Subscription cannot establish a stream |
| Subscription/event timeout | Time waiting for an event or lifetime limit of a stream | Event source stops emitting data |

Do not use `spring.mvc.async.request-timeout` as a replacement for a GraphQL timeout, or use WebSocket keep-alive as a query execution time limit. Choose the right layer based on which resource is being held.

## GraphQL request timeout with TimeoutWebGraphQlInterceptor

Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` to bound request processing time across web transports. When the timeout expires, the interceptor ends the request with a default HTTP status of 408 Request Timeout and sends a cancel signal upstream through the processing chain. Reactive data fetchers can receive the cancellation signal and stop ongoing work.

This class has been available since Spring for GraphQL 1.4.0. In a Spring Boot application, simply register the interceptor as a bean:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(
                Duration.ofSeconds(5));
    }
}
~~~

In this example, a GraphQL request has at most 5 seconds to produce a response. This value is only an example; choose it based on your SLA, dependency latency, and application operation types.

You can specify a different HTTP status if your application has its own conventions:

~~~java
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
                Duration.ofSeconds(5),
                HttpStatus.REQUEST_TIMEOUT);
    }
}
~~~

The two configuration snippets above are alternatives; register only one `TimeoutWebGraphQlInterceptor` bean. In the second configuration, the status is still 408; the constructor accepting `HttpStatus` is useful when you need to set the status according to your system's HTTP conventions.

### How far does the timeout reach?

`TimeoutWebGraphQlInterceptor` bounds the time spent waiting for a GraphQL response to be produced. It is not a thread-killing tool and cannot guarantee that every blocking operation stops immediately.

When a timeout occurs:

- Reactive data fetchers returning `Mono` or `Flux` can receive the cancel signal and cancel upstream subscriptions.
- A reactive HTTP call can stop waiting if the client supports cancellation.
- A running blocking JDBC/JPA query may continue on its thread or on the database if the driver/database does not support corresponding cancellation.
- A `CompletableFuture` does not automatically halt its internal work just because the GraphQL response timed out.

Therefore, request timeouts must be paired with WebClient, database, and transaction timeouts. If only the response is closed, background work can continue occupying connections, threads, or CPU.

### Limits with subscriptions

Subscriptions return a stream instead of a single complete response. `TimeoutWebGraphQlInterceptor` applies only until the response stream is established. Once the stream starts, the interceptor does not enforce a total lifetime limit on the subscription.

To manage streams, separate policies are needed: event wait limits, lifetime limits, closing subscriptions on client cancellation, limiting subscriptions per session, and transport keep-alive. These are covered in the WebSocket and SSE sections.

## Timeout for Spring MVC async requests

Spring for GraphQL can execute requests asynchronously on Spring MVC. When the GraphQL engine returns an incomplete `CompletableFuture`, Spring MVC switches the Servlet request to async mode and keeps the response open waiting for the result.

Spring Boot provides the property:

~~~yaml
spring:
  mvc:
    async:
      request-timeout: 6s
~~~

`spring.mvc.async.request-timeout` limits how long a Servlet async request can be processed. If not configured, the timeout depends on the Servlet container and current configuration.

This is a Spring MVC layer limit. It can end async waiting for an HTTP response, but it does not replace a dedicated GraphQL timeout. A GraphQL request that completes synchronously within the GraphQL Java invocation may not go through MVC async processing; therefore, do not rely solely on this property to protect every GraphQL operation.

If using Spring MVC, you can combine the MVC async timeout property with a `TimeoutWebGraphQlInterceptor` bean set to a shorter duration, such as 5 seconds. That gives GraphQL a chance to end the request and return a timeout error before the MVC async timeout triggers.

Do not set the MVC async timeout shorter than the GraphQL request timeout if you want clients to receive the timeout response generated by the GraphQL interceptor. If MVC closes the request first, the transport layer may terminate the response without any opportunity to send a result per GraphQL policy.

## Timeout for WebFlux

WebFlux handles HTTP through a reactive pipeline and does not use Servlet async requests. Consequently, `spring.mvc.async.request-timeout` does not apply to WebFlux applications.

With WebFlux, use `TimeoutWebGraphQlInterceptor` to bound GraphQL request processing time. Additionally, configure separate timeouts for reactive dependencies such as `WebClient` and database clients.

Example of a resolver returning `Mono`:

~~~java
import java.time.Duration;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Mono<BookView> slowBook() {
        return bookService.findBook()
                .timeout(Duration.ofSeconds(3));
    }
}
~~~

`Mono.timeout` bounds the duration for the resolver's publisher. If the publisher does not emit a result within the specified time, it emits a timeout error and cancels the upstream subscription. This error flows through GraphQL's exception handling mechanism; if you want a custom error code in the response, map the timeout in a `DataFetcherExceptionResolver` or exception handler.

A resolver timeout does not replace a full-request timeout. A query can have multiple parallel or sequential resolvers; each resolver might take less than 3 seconds while the overall request still exceeds the deadline. Therefore, combine per-dependency timeouts with a request timeout.

## Timeout for downstream HTTP via WebClient

GraphQL resolvers frequently call other services to fetch data. `WebClient` needs separate connect and response timeouts.

With Reactor Netty, you can configure `CONNECT_TIMEOUT_MILLIS` and `responseTimeout`:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
public class DownstreamClientConfiguration {

    @Bean
    WebClient authorWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
                .option(
                        ChannelOption.CONNECT_TIMEOUT_MILLIS,
                        500)
                .responseTimeout(Duration.ofSeconds(2));

        return builder
                .baseUrl("https://author.internal")
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient))
                .build();
    }
}
~~~

In this example:

- A 500 ms connect timeout limits connection establishment time.
- A 2-second response timeout limits waiting for a response at the HTTP client layer.
- This is the timeout for connecting to the Author service, not the timeout for the entire GraphQL request.

The resolver can invoke the client:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class AuthorClient {

    private final WebClient authorWebClient;

    public AuthorClient(WebClient authorWebClient) {
        this.authorWebClient = authorWebClient;
    }

    public Mono<AuthorView> findById(String id) {
        return authorWebClient.get()
                .uri("/authors/{id}", id)
                .retrieve()
                .bodyToMono(AuthorView.class);
    }
}
~~~

When using Reactor Netty, `responseTimeout` is the right choice to bound waiting for a response at the HTTP client layer. You can use `ReadTimeoutHandler` or `WriteTimeoutHandler` when channel-level read/write timeouts are needed, but clearly understand each handler's scope and avoid unnecessary overlapping configuration.

With Reactor Netty, `responseTimeout` limits the wait time between reads of response data at the network layer. It does not necessarily limit the total time from sending the request until the body finishes if the server continuously streams data. If you need a hard deadline for the entire publisher, also use `Mono.timeout` or a request-level deadline.

Reactor also provides the `timeout(Duration)` operator on `Mono`/`Flux` to bound the entire publisher:

~~~java
return authorWebClient.get()
        .uri("/authors/{id}", id)
        .retrieve()
        .bodyToMono(AuthorView.class)
        .timeout(Duration.ofSeconds(2));
~~~

This operator limits the time from when the publisher is subscribed until a terminal signal arrives. Dedicated HTTP client timeouts provide finer control over stages like connect and response; do not use a single overall timeout to replace all of them.

## Timeouts for database and transactions

A GraphQL request can miss its deadline because of a slow SQL query or waiting on a connection pool. Distinguish:

- Connection acquisition timeout: time spent waiting to obtain a connection from the pool.
- Statement/query timeout: time the database is allowed to execute a statement.
- Transaction timeout: time a transaction is allowed to exist per the transaction manager.
- GraphQL request timeout: time spent waiting for the GraphQL response to complete.

For example, if a request has a 5-second deadline yet a database query is allowed to run for up to 5 seconds, the request has no remaining time for mapping, calling other dependencies, and serializing the response. Set database timeouts lower than the request deadline.

With Spring JDBC, you can set the query timeout on `JdbcTemplate` or on a `JdbcTemplate`/`JdbcClient` configured specifically for the use case. With JPA/Hibernate, use query timeout hints or the provider/database-specific configuration. Verify whether the driver actually sends a statement cancel to the database or merely stops waiting on the application side.

Transaction timeouts can be declared on a service:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookCommandService {

    @Transactional(timeout = 3)
    public BookView publish(String bookId) {
        // Read, validate, and update data within the transaction.
        return publishBook(bookId);
    }
}
~~~

The value `timeout = 3` is in seconds. Transaction timeout is a limit enforced by the transaction manager for a new transaction; whether it propagates down to JDBC/JPA statements depends on the transaction manager, provider, and driver. Do not treat this annotation as a guarantee that every running SQL query will be stopped after exactly 3 seconds.

Set connection pool acquisition timeouts, query timeouts, and transaction timeouts according to database policy. Avoid keeping transactions open while waiting on downstream HTTP calls whenever possible; long transactions hold connections and locks longer.

## Timeouts for SSE

Spring for GraphQL supports GraphQL over Server-Sent Events (SSE). With SSE, distinguish the initial response creation time from the event stream's lifetime.

Spring Boot provides:

~~~yaml
spring:
  graphql:
    http:
      sse:
        timeout: 5s
        keep-alive: 15s
~~~

Meaning:

- `spring.graphql.http.sse.timeout` bounds how long the handler waits to create the response that starts the SSE stream.
- `spring.graphql.http.sse.keep-alive` configures the interval for sending heartbeats when there are no events.

The SSE timeout is not a limit on how long a subscription is allowed to live in total. Keep-alive is not a timeout either; heartbeats only prevent idle connections from being mistaken for dead by some proxies or clients.

At the handler level, `GraphQlSseHandler` has a constructor accepting timeout and keep-alive durations. The timeout here limits how long the application waits to produce the `ServerResponse` to start the stream; once the stream has started, it does not automatically cap the subscription's total lifetime.

If the application creates `GraphQlSseHandler` manually or uses functional endpoints, configure it directly:

~~~java
import java.time.Duration;

import org.springframework.graphql.server.WebGraphQlHandler;
import org.springframework.graphql.server.webflux.GraphQlSseHandler;

GraphQlSseHandler sseHandler = new GraphQlSseHandler(
        webGraphQlHandler,
        Duration.ofSeconds(5),
        Duration.ofSeconds(15));
~~~

This snippet illustrates the WebFlux handler constructor. For Spring MVC, use the class in package `org.springframework.graphql.server.webmvc`. If using Spring Boot auto-configuration, prefer `spring.graphql.http.sse.*` properties.

## Timeouts and WebSocket resource management

WebSocket connections can be long-lived and carry multiple operations or subscriptions. Connection timeouts differ from per-GraphQL-operation timeouts.

Spring Boot supports:

~~~yaml
spring:
  graphql:
    websocket:
      connection-init-timeout: 10s
      keep-alive: 20s
~~~

- `connection-init-timeout` is how long the client has to send the `CONNECTION_INIT` message after the WebSocket is established. This is a connection initialization timeout, not the maximum duration of a GraphQL query.
- `keep-alive` is the maximum idle interval before the server sends a keep-alive ping. This is a heartbeat, not an operation timeout.

`TimeoutWebGraphQlInterceptor` also participates in the interceptor chain for WebSocket requests. For queries/mutations returning a single response, it can bound response generation time. For subscriptions, the timeout applies only until the stream is established; event emission duration afterward requires a separate policy.

A WebSocket session can hold multiple subscriptions. In addition to timeouts, limit connection counts, message sizes, and concurrent subscriptions per session. `GraphQlWebSocketHandler` provides a `maxSubscriptionsPerSession` option; by default, subscriptions per session are unbounded.

When a client sends a cancel message or closes the socket, the application should cancel the subscription and release upstream resources. For self-managed publishers, ensure cleanup runs in `doFinally`, `usingWhen`, or an equivalent mechanism.

## Timeouts for subscription publishers

For subscriptions, you can apply timeouts per event wait interval or for the entire stream depending on business requirements.

Example bounding the duration without an event:

~~~java
import java.time.Duration;

import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class NotificationController {

    private final NotificationService notificationService;

    public NotificationController(
            NotificationService notificationService) {
        this.notificationService = notificationService;
    }

    @SubscriptionMapping
    public Flux<NotificationView> notifications() {
        return notificationService.events()
                .timeout(Duration.ofSeconds(60));
    }
}
~~~

`Flux.timeout(Duration)` emits a timeout error if no item arrives within that window. This is an idle/event-gap timeout; a stream can still continue indefinitely if it regularly emits an event at least every 60 seconds.

If you need to limit the stream's total lifetime, use an absolute deadline or `take(Duration)` according to business needs. Do not confuse the two policies:

| Policy | Behavior |
| --- | --- |
| Event-gap timeout | Closes the stream if too much time passes without an event |
| Absolute lifetime | Closes the stream after a duration measured from when it started |
| WebSocket keep-alive | Sends heartbeats to maintain/check the connection |
| Client cancellation | Cancels the stream when the client is no longer interested |

If a stream emits events frequently, an event-gap timeout cannot substitute for a lifetime limit. Conversely, an absolute lifetime can close a stream even while the event source is still active.

Reactor `Flux.take(Duration)` completes the stream after the specified duration; it does not emit a `TimeoutException` like `Flux.timeout(Duration)`. Choose the operator based on the desired contract: normal completion versus terminating with a timeout error.

## Timeouts for RSocket

`TimeoutWebGraphQlInterceptor` is a `WebGraphQlInterceptor`, so it applies only to web transports such as HTTP and WebSocket. GraphQL over RSocket goes through `RSocketQlInterceptor` and RSocket request handling, so it does not receive a timeout merely by registering a `TimeoutWebGraphQlInterceptor` bean.

For RSocket, configure wait times on the RSocket requester/client or the transport matching the interaction model in use. You can add timeouts to `Mono`/`Flux` inside resolvers when needing to bound a specific dependency. Do not use `spring.graphql.websocket.*` properties to control RSocket; those settings are for WebSocket.

## Building a timeout budget

A GraphQL request can traverse multiple dependencies. Timeouts should be coordinated under a shared budget to avoid each layer waiting too long on its own.

Illustrative budget example for a typical query:

| Layer | Example timeout | Purpose |
| --- | --- | --- |
| Connection pool acquisition | 300 ms | Avoid waiting too long for the pool |
| HTTP connect | 500 ms | Bound connection establishment |
| HTTP downstream response | 1.5 s | Bound waiting on another service |
| Database statement | 2 s | Bound the SQL query |
| GraphQL request | 4 s | Bound the entire response |
| MVC async request | 5 s | Outer safety guard outside GraphQL |
| Gateway/client deadline | 6 s | Leave margin to receive the timeout response |

These values are not Spring defaults. They only illustrate priority ordering: dependency timeouts must be shorter than the request deadline; transport/gateway timeouts should be long enough for the application to return a result or error.

When a request calls multiple dependencies sequentially, total wait times can add up. If two dependencies run in parallel, actual elapsed time depends on the slowest dependency plus subsequent sequential processing. Therefore, do not simply add up timeout numbers; measure the real flow and reserve budget for mapping, serialization, and the network response.

Propagate remaining deadlines across layers if the application spans multiple internal services. For example, if a request has already spent 3 seconds of a 4-second budget, downstream should not start a new operation with a 4-second timeout.

## Timeouts do not replace query complexity limits

Timeouts only bound wait time. A very large GraphQL document or a query with high fan-out can still consume CPU and memory before the request hits its deadline. Therefore, combine timeouts with cost-limiting measures:

- Enforce query depth and complexity/cost limits per application policy.
- Require pagination and cap page sizes.
- Use DataLoader or batch resolvers to prevent N+1 issues.
- Limit concurrent requests and apply rate limiting per client/user.
- Monitor operation names and query patterns causing high p95/p99 latency.

Timeouts are the final safety net when a request exceeds its budget; they do not replace proper query design and input resource limits.

## Handling timeout errors

Timeouts can occur across multiple layers and need to be classified:

| Timeout source | Common representation | Where handled |
| --- | --- | --- |
| GraphQL request timeout | HTTP 408 from TimeoutWebGraphQlInterceptor | Web transport/client |
| Resolver publisher timeout | Timeout exception during GraphQL execution | DataFetcherExceptionResolver or @GraphQlExceptionHandler |
| WebClient timeout | WebClientRequestException, TimeoutException, or connector error | Service/client adapter and GraphQL exception resolver |
| Database query timeout | Exception from JDBC/JPA/provider | Repository/service and exception resolver |
| MVC async timeout | Servlet async request timeout | Spring MVC async handling |
| SSE/WebSocket handshake timeout | Transport closes or rejects stream/connection setup | Transport handler/client |

Do not return internal details such as hostnames, SQL, stack traces, or database names to GraphQL clients. Log the root cause on the server with an execution ID/correlation ID, then return a public error with a stable code and appropriate message.

Example mapping a resolver timeout into a GraphQL error:

~~~java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;
import org.springframework.graphql.data.method.annotation.GraphQlExceptionHandler;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Controller;

import java.util.List;

@Controller
public class GraphQlTimeoutExceptionHandler {

    @GraphQlExceptionHandler
    public List<GraphQLError> handleTimeout(
            java.util.concurrent.TimeoutException exception,
            DataFetchingEnvironment environment) {

        GraphQLError error = GraphqlErrorBuilder.newError(environment)
                .message("The service is temporarily responding too slowly.")
                .errorType(ErrorType.INTERNAL_ERROR)
                .extensions(java.util.Map.of(
                        "code", "DEPENDENCY_TIMEOUT"))
                .build();

        return List.of(error);
    }
}
~~~

`TimeoutWebGraphQlInterceptor` handles request timeouts at the transport layer and returns the HTTP status configured on the interceptor. The exception handler above is only for timeouts raised inside a resolver, such as `Mono.timeout` or a dependency timeout error. The two cases do not follow the same handling path.

If using `DataFetcherExceptionResolver`, you can map exceptions using the same principle instead of placing handlers in controllers.

## Retries and mutations

Retrying is not the default cure for timeouts. Retrying an operation that already took a long time can consume extra resources and exceed the deadline.

For read-only queries, retries can be appropriate if the failure is transient, the operation is idempotent, and time budget remains. For mutations, be especially careful:

- The client may not know whether the mutation committed when a connection times out.
- Retrying the same mutation can create duplicate records or trigger side effects twice.
- Use an idempotency key or command ID if business requirements call for safe retries.
- Do not retry once the overall deadline has expired.
- Limit retry attempts and add backoff with jitter when appropriate.

A client-side timeout does not prove the server failed to execute the mutation. Mutation design should provide a way to query state or enforce idempotency when operations have critical side effects.

## Testing timeouts

Testing must verify both the response and cancellation/cleanup. A request that times out while a database query keeps running for minutes is still an operational bug.

### Testing a resolver publisher

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ResolverTimeoutTests {

    @Test
    void publisherTimesOut() {
        Mono<String> result = Mono.delay(Duration.ofSeconds(2))
                .map(ignored -> "done")
                .timeout(Duration.ofMillis(100));

        StepVerifier.create(result)
                .expectError(java.util.concurrent.TimeoutException.class)
                .verify();
    }
}
~~~

This test verifies the Reactor publisher's timeout. It does not replace an integration test for `TimeoutWebGraphQlInterceptor`.

### Testing GraphQL HTTP request timeout

In a Spring Boot application, you can use `WebTestClient` to send a request to the endpoint and assert HTTP 408:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.util.Map;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlRequestTimeoutTests {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void slowQueryReturnsRequestTimeout() {
        webTestClient.post()
                .uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("query", "{ slow }"))
                .exchange()
                .expectStatus()
                .isRequestTimeout();
    }
}
~~~

This test assumes the application has a `slow` query field returning a publisher that takes longer than the configured timeout. If using Spring MVC, you can use `MockMvc` or an equivalent HTTP client test; the key is that the request passes through the web interceptor chain.

In Spring MVC tests, if you want to inject `WebTestClient`, enable the `WebTestClient` test configuration appropriate for your Spring Boot version; otherwise, use `MockMvc` or build a `WebTestClient` against the running server.

### Scenarios to test

- Queries completing before the deadline still return successful results.
- Queries exceeding the deadline return HTTP 408 as configured.
- Resolver publishers receive cancellation when the request times out.
- `WebClient` connect timeout and response timeout are distinguished.
- Database query timeout releases or returns connections properly per the driver/provider.
- MVC async timeout does not fire before the GraphQL timeout.
- SSE response-start timeout is not mistaken for subscription lifetime.
- WebSocket connection-init timeout applies only to the initialization phase.
- Subscription event-gap timeout and absolute lifetime behave differently.
- Client cancellation closes the subscription and frees upstream resources.
- Mutation timeouts do not cause duplicate side effects when clients retry.

## Observability and operations

To detect timeouts before users report errors, monitor:

- Timeout counts by operation name and transport.
- GraphQL execution latency at p50, p95, and p99.
- Timeout counts by dependency: database, HTTP client, message broker.
- Connections waiting in the pool and connection acquisition time.
- Active subscriptions, stream age, and client cancellations.
- Timeouts occurring before versus after the GraphQL response stream is established.
- Retry counts and retry success rates.

Log timeouts along with execution ID/correlation ID, operation name, dependency, and elapsed time. Do not log full variables if they contain tokens, personal data, or sensitive information.

Set alerts when timeout rates or p99 latency spike abnormally. Raising timeouts only makes requests wait longer; if the root cause is pool exhaustion, unindexed queries, or overloaded dependencies, fix the root cause.

## Common configuration pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| GraphQL requests wait too long | `TimeoutWebGraphQlInterceptor` is not registered | Add the interceptor bean |
| `spring.mvc.async.request-timeout` has no effect on WebFlux | That property belongs to Servlet MVC | Use the GraphQL interceptor and timeouts for reactive dependencies |
| MVC timeout triggers before GraphQL timeout | MVC async timeout is set shorter | Set MVC timeout longer than the GraphQL request timeout |
| HTTP response times out, yet SQL keeps running | Blocking JDBC/JPA call does not stop on cancel signal | Configure statement/query timeouts at the database layer |
| WebClient times out, yet the GraphQL request stays open | No overall request timeout | Combine WebClient timeout with GraphQL request timeout |
| Subscription closes automatically after a few seconds | Confused request timeout with stream lifetime | Understand the timeout applies until stream setup and configure the publisher separately |
| SSE fails to start | Handler waits too long to initialize the response | Check `spring.graphql.http.sse.timeout` |
| SSE gets closed by proxy while idle | Missing heartbeat or keep-alive is too long | Configure `spring.graphql.http.sse.keep-alive` and proxy idle timeout |
| WebSocket closes before sending an operation | Client does not send CONNECTION_INIT in time | Check `spring.graphql.websocket.connection-init-timeout` |
| WebSocket holds too many subscriptions | Subscriptions per session are unbounded | Configure `maxSubscriptionsPerSession` and manage cancellation |
| Retried mutations create duplicate data | Client retries after timeout without idempotency | Use an idempotency key/command ID |
| Raising timeouts leaves the system slow | Timeouts mask slow queries or slow dependencies | Measure p95/p99, pools, query plans, and downstream latency |

## Timeout configuration checklist

When rolling out timeouts for a Spring for GraphQL application:

1. **Measure real timings.** Collect p95/p99 for critical queries, mutations, and dependencies.
2. **Set a request deadline.** Register `TimeoutWebGraphQlInterceptor` for web transports.
3. **Set matching transport timeouts.** For MVC, review async timeout; for WebFlux, review server/proxy timeouts; for SSE/WebSocket, configure the corresponding handler properties.
4. **Set downstream timeouts.** Bound `WebClient` connect/response and database query/statement/transaction limits.
5. **Leave budget for response processing.** Dependency timeouts must be shorter than the GraphQL request deadline.
6. **Handle cancellation.** Use reactive pipelines where appropriate and ensure blocking work has its own timeout.
7. **Manage subscriptions.** Distinguish event-gap, absolute lifetime, keep-alive, and client cancellation.
8. **Standardize errors.** Separate HTTP request timeouts from GraphQL execution errors thrown by resolvers.
9. **Run integration tests.** Verify status codes, cancellation, cleanup, and idempotency.
10. **Monitor after deployment.** Watch p95/p99, pool usage, and timeout rates to tune the budget.

Effective timeout configuration requires an overall deadline for the entire GraphQL request and smaller timeouts for dependencies. `TimeoutWebGraphQlInterceptor` bounds response generation time for web transports, while MVC async, SSE, WebSocket, `WebClient`, and databases have their own timeouts. Cancel signals help reactive work stop, but do not guarantee that blocking tasks or running SQL queries will terminate on their own. For subscriptions, the request timeout only protects stream establishment; event-gap, lifetime, and keep-alive must be managed separately. Measure real latency, coordinate timeouts within a budget, test cancellation, and track timeout rates after deployment.

## References

- [Spring for GraphQL - Request Execution and GraphQL Request Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL - Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL - TimeoutWebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/TimeoutWebGraphQlInterceptor.html)
- [Spring Boot - Application Properties](https://docs.spring.io/spring-boot/4.0/appendix/application-properties/)
- [Spring Framework - Asynchronous Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
- [Spring Framework - WebClient Timeouts](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html)
- [Reactor Netty - HTTP Client Timeout](https://projectreactor.io/docs/netty/release/reference/http-client.html#http-client-timeout)
