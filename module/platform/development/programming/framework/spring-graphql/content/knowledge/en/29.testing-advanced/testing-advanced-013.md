# Testing timeouts and transport errors

When testing Spring for GraphQL, a request can fail for several reasons: GraphQL returns errors in the response, the server fails to return a successful HTTP status, a connection cannot be established, an active connection drops mid-flight, or the response fails to complete within the allowed time. These scenarios mean different things and must be tested at the right layer.

`GraphQlTester` provides `responseTimeout(Duration)` to cap how long a test waits for a GraphQL response. For errors at the transport layer, clients can raise `GraphQlTransportException`. For subscriptions, distinguish GraphQL errors sent by the server via the protocol from connection failures such as `WebSocketDisconnectedException`.

This lesson covers setting test timeouts, configuring HTTP client and server timeouts, simulating transport failures, testing subscription streams, cancellation, and retries. The goal is tests with explicit time bounds that run reliably and pinpoint the exact failure category.

## 1. Distinguishing GraphQL errors, HTTP errors, and transport errors

A GraphQL request traverses multiple layers. Failures at each layer are represented differently:

~~~mermaid
flowchart TD
    A["Test / GraphQL client"] --> B["Transport client"]
    B --> C{"Connection and HTTP/WebSocket/RSocket"}
    C -->|Cannot connect / timeout / disconnect| D["Transport exception"]
    C -->|HTTP response received| E["GraphQL server"]
    E --> F{"GraphQL request"}
    F -->|Parse / validation / execution| G["GraphQL response errors"]
    F -->|Success| H["GraphQL data"]
    D --> I["Assert transport failure"]
    G --> J["Assert errors in response"]
    H --> K["Assert data"]
~~~

Three primary categories:

| Category | Examples | How to observe |
| --- | --- | --- |
| GraphQL response error | Resolver throws an exception, forbidden field, invalid input | Response contains `errors` key; use `GraphQlTester.errors()` or `ClientGraphQlResponse.getErrors()` |
| HTTP/protocol error | HTTP 401, 404, 429, 500; failed WebSocket handshake | HTTP status or exception raised by the transport client |
| Transport failure | Connection refused, DNS failure, TLS error, connect timeout, response timeout, WebSocket disconnect | `GraphQlTransportException` or WebClient/transport-layer exception |

A GraphQL response can contain both `data` and `errors`. That is a protocol-valid GraphQL execution result, not a broken connection.

Conversely, if the server is unreachable or the client never receives a response, there is no GraphQL response to inspect with `errors()`. In that case, tests must assert the exception or HTTP status at the transport layer.

## 2. Timeouts have multiple distinct scopes

No single timeout applies to the entire system. Identify precisely which duration is being bounded:

| Timeout | Scope | Where configured |
| --- | --- | --- |
| Test response timeout | How long the test waits for a GraphQL response | `GraphQlTester.Builder.responseTimeout(...)` |
| Client connect timeout | Time to establish TCP/TLS connection | HTTP/WebSocket/RSocket client |
| Client response/read timeout | Time waiting for response data from server | HTTP client or corresponding transport |
| Connection pool acquire timeout | Time waiting to borrow a connection from the pool | Connection pool |
| Overall operation timeout | Total time for a publisher/request | Reactor `timeout(...)` or blocking timeout |
| Server GraphQL request timeout | Time the server allows for request processing | `TimeoutWebGraphQlInterceptor` |
| Subscription idle/event timeout | Time waiting for the next event in a stream | Reactor `timeout(...)` or stream policy |

These timeouts protect different resources. For example, `GraphQlTester.responseTimeout` limits how long the test waits for a result; it does not configure the HTTP client's TCP timeout. Server timeouts bound server-side request processing and do not replace client timeouts.

When testing timeouts, state clearly which layer's timeout is under test. Configuring only one timeout while describing it as an end-to-end request timeout creates misleading tests.

## 3. Configuring GraphQlTester responseTimeout

All `GraphQlTester` builders support configuring the maximum wait time for a GraphQL response via `responseTimeout(Duration)`.

By default, this timeout is 5 seconds. You can override it when building the tester:

~~~java
import java.time.Duration;

import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient.Builder clientBuilder = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080/graphql");

HttpGraphQlTester graphQlTester =
        HttpGraphQlTester.builder(clientBuilder)
                .responseTimeout(Duration.ofSeconds(2))
                .build();
~~~

Then use the tester as usual:

~~~java
graphQlTester.document("""
        query {
            health
        }
        """)
        .execute()
        .path("health")
        .entity(String.class)
        .isEqualTo("UP");
~~~

`responseTimeout` applies to waiting for a test request's response. It is useful when testing endpoints that might stall or when enforcing a tighter limit than the default.

Do not set timeouts overly tight just to make tests finish faster. CI runners, containers, and developer laptops exhibit varying latency. Pick a value generous enough for normal runs to pass yet short enough so failures do not stall the suite.

## 4. Testing timeouts with a non-completing resolver

One way to test response timeouts is a resolver that never emits a result:

~~~java
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class TimeoutTestController {

    @QueryMapping
    public Mono<String> neverResponds() {
        return Mono.never();
    }
}
~~~

`Mono.never()` neither emits a value nor completes or errors. It provides a clean test fixture for timeout behavior without depending on an external service.

Create a tester with a short timeout:

~~~java
HttpGraphQlTester tester =
        HttpGraphQlTester.builder(clientBuilder)
                .responseTimeout(Duration.ofMillis(300))
                .build();
~~~

In an integration test, execute `neverResponds` with this tester and verify the call terminates due to a response timeout. The exact exception type or cause may depend on the tester extension and transport in use; assert the stable type/cause emitted by your project's library version instead of coupling to internal Reactor Netty or HTTP connector messages. Avoid broad assertions that treat any `Exception` as a timeout, since that can mask configuration or test setup bugs.

This example only verifies that the test does not wait forever. If you want to verify whether the server actually cancels processing on timeout, write a dedicated test for server-side timeouts and cancellation.

## 5. Using StepVerifier for publishers and timeouts

In reactive code, you can apply timeouts directly to `Mono` or `Flux`:

~~~java
Mono<ClientGraphQlResponse> response = graphQlClient
        .document("""
                query {
                    health
                }
                """)
        .execute()
        .timeout(Duration.ofSeconds(2));
~~~

`timeout(Duration)` limits the overall time waiting for the publisher's next signal. When exceeded, the publisher terminates with `TimeoutException` and cancels the upstream subscription.

Use `StepVerifier` to verify:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;

import reactor.test.StepVerifier;

@Test
void clientOperationTimesOut() {
    Mono<String> result = Mono.<String>never()
            .timeout(Duration.ofMillis(100));

    StepVerifier.create(result)
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
}
~~~

Two bounds are active here:

- `Mono.timeout(...)` is the behavior under test.
- `StepVerifier.verify(Duration)` is the safety bound protecting the test itself so a broken pipeline cannot hang indefinitely.

For tests verifying only the timeout operator, you can use `StepVerifier.withVirtualTime(...)` to avoid waiting in wall-clock time:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(10))
)
        .thenAwait(Duration.ofSeconds(10))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(1));
~~~

Virtual time works for publishers driven by Reactor schedulers. It does not accelerate real sockets, DNS, HTTP clients, or WebSocket servers; network integration tests still require real time and a bounded `verify(Duration)`.

## 6. Distinguishing test timeouts from server request timeouts

Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` to bound how long the server spends handling a web request. On timeout, the interceptor returns an appropriate HTTP error and sends a cancel signal down the processing chain. Reactive DataFetchers can observe that cancellation to stop ongoing work.

In Spring Boot, register the bean:

~~~java
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
~~~

This timeout lives on the server side. It differs from `GraphQlTester.responseTimeout`:

- `GraphQlTester.responseTimeout`: the test stops waiting when no response arrives in time.
- `TimeoutWebGraphQlInterceptor`: the server actively bounds processing time and cancels upstream work upon timeout.

A client timeout can fire before the server timeout. For example, the client waits 1 second while the server allows 3 seconds. In that case, the test may abort early while the server continues working unless client disconnection propagates cancellation to the processing layer.

For HTTP statuses returned by server timeouts, use `WebTestClient` to inspect status codes directly. `HttpGraphQlTester` expects successful GraphQL responses and may fail assertions when the HTTP status is not 200.

## 7. Configuring connect and response timeouts for HTTP clients

`HttpGraphQlClient` uses `WebClient`. If your application uses Reactor Netty, configure timeouts on `HttpClient` and attach it to `WebClient`.

Example:

~~~java
import java.time.Duration;

import io.netty.channel.ChannelOption;
import reactor.netty.http.client.HttpClient;

import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.graphql.client.HttpGraphQlClient;

HttpClient httpClient = HttpClient.create()
        .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 1_000)
        .responseTimeout(Duration.ofSeconds(2));

WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .build();

HttpGraphQlClient graphQlClient =
        HttpGraphQlClient.builder(webClient).build();
~~~

In this example:

- `CONNECT_TIMEOUT_MILLIS` bounds TCP connection establishment.
- Reactor Netty's `responseTimeout` bounds waiting for response data per HTTP client policy.
- `GraphQlTester.responseTimeout`, if set, acts as a separate bound at the test layer.

Reactor Netty also offers timeouts for acquiring connections from a pool, TLS handshakes, and DNS resolution. If your application uses a different connector, configuration APIs differ. Do not apply Reactor Netty configuration blindly to every `WebClient`.

## 8. Testing HTTP transport errors

HTTP transport errors can occur before the GraphQL server returns a response:

- Server is down or connection is refused.
- Hostname resolution fails.
- TLS handshake fails.
- Server or proxy returns HTTP 502 or 503.
- Request is rejected due to authentication or rate limiting.
- Client times out waiting for a response.

For `GraphQlClient`, errors from `GraphQlTransport` are represented by or wrapped in `GraphQlTransportException`. You can test them with `StepVerifier`:

~~~java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.test.StepVerifier;

@Test
void reportsTransportFailureWhenServerIsUnavailable() {
    Mono<ClientGraphQlResponse> response = graphQlClient
            .document("""
                    query {
                        health
                    }
                    """)
            .execute();

    StepVerifier.create(response)
            .expectError(GraphQlTransportException.class)
            .verify(Duration.ofSeconds(3));
}
~~~

For reliable tests, point the client to an unused test port or a test-controlled mock server. Never rely on external Internet hostnames or public services to induce errors, as results will depend on external network conditions.

When you need to test a specific HTTP status such as 503, use `WebTestClient` or a mock HTTP server returning that status. With `HttpGraphQlTester`, non-200 HTTP statuses can fail request execution before a `GraphQlTester.Response` is available to inspect.

## 9. Distinguishing GraphQL errors from transport exceptions

Do not use the same assertion for every failure type.

Example GraphQL execution error:

~~~java
graphQlTester.document("""
        query {
            book(id: "missing") {
                id
            }
        }
        """)
        .execute()
        .errors()
        .expect(error ->
                "book".equals(error.getPath())
                        && "NOT_FOUND".equals(
                                error.getExtensions().get("code")))
        .verify();
~~~

Here, the server received and executed the GraphQL request. The test has a response whose `errors` can be inspected.

With a transport exception, the request never receives a GraphQL response:

~~~java
StepVerifier.create(
        graphQlClient.document("{ health }").execute()
)
        .expectError(GraphQlTransportException.class)
        .verify(Duration.ofSeconds(3));
~~~

Do not call `errors().expect(...)` to test connection refused or DNS failures. The `errors()` API only inspects GraphQL errors inside a received response.

Over HTTP, also distinguish HTTP status codes from GraphQL errors. Under Spring for GraphQL's GraphQL-over-HTTP behavior, an unavailable server, invalid credentials, or non-JSON body can produce HTTP 4xx/5xx. Once a GraphQL request passes validation, field execution errors typically appear in the `errors` field of the response. With `application/graphql-response+json`, parse/validation errors can use 4xx; legacy `application/json` follows different status semantics.

## 10. Checking HTTP status codes with WebTestClient

When you need to verify which status code the server returns, use `WebTestClient` directly. Example where the server or test stub returns 503:

~~~java
webTestClient.post()
        .uri("/graphql")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("query", "{ health }"))
        .exchange()
        .expectStatus()
        .is5xxServerError();
~~~

This approach works well for testing:

- Server unavailability or downstream maintenance.
- HTTP-layer authentication/authorization.
- Gateways or reverse proxies returning 502/503/504.
- Server-side timeouts mapped to HTTP statuses.

Do not hard-code an exact status code when the application contract only specifies the 5xx class. Conversely, if your project's API contract mandates a specific status for that scenario, assert that exact status.

With `HttpGraphQlTester`, requests returning non-200 statuses may fail immediately during execution. When the test's objective is verifying HTTP status codes, direct `WebTestClient` makes assertions clearer.

## 11. Testing WebSocket disconnects

`WebSocketGraphQlClient` shares a single connection across requests. If the connection closes or drops, the client can emit `GraphQlTransportException`, including subtypes such as `WebSocketDisconnectedException`.

You can test this failure at the subscription level:

~~~java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<String> events = graphQlClient
        .document("subscription { events }")
        .retrieveSubscription("events")
        .toEntity(String.class);

StepVerifier.create(events)
        .expectNext("event-1")
        .expectError(WebSocketDisconnectedException.class)
        .verify(Duration.ofSeconds(5));
~~~

This example assumes the test server emits `event-1` and then intentionally closes the WebSocket connection. In integration tests, control the server or test fixture so the disconnect happens deterministically rather than waiting on an external server to drop.

For single-response query/mutation requests, if the connection drops before the result arrives, assert the corresponding transport exception. For subscriptions, the stream may already have emitted events before failing; tests should verify both received events and the terminal error.

RSocket also uses a shared session. If the session closes while a request is in flight, assert the transport exception on that request. Once a session is lost, `RSocketGraphQlClient` can re-establish it on the next request or upon calling `start()`. Use a local RSocket server or test fixture to close the session deterministically in tests.

## 12. Distinguishing SubscriptionErrorException from WebSocketDisconnectedException

Both exceptions can terminate a subscription stream, but their causes differ:

| Exception | Meaning | What tests should verify |
| --- | --- | --- |
| `SubscriptionErrorException` | Server sent a protocol `error` message containing GraphQL errors | List of GraphQL errors and error codes in the response |
| `WebSocketDisconnectedException` | WebSocket connection was closed or lost | Connection failure, reconnect/retry behavior |
| `GraphQlTransportException` | General transport error or transport-wrapped exception | Transport type, cause, and affected request |

Example verifying a subscription terminating with a GraphQL error:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.springframework.graphql.client.SubscriptionErrorException;

StepVerifier.create(subscriptionFlux)
        .expectErrorSatisfies(error -> {
            assertThat(error)
                    .isInstanceOf(SubscriptionErrorException.class);

            SubscriptionErrorException subscriptionError =
                    (SubscriptionErrorException) error;

            assertThat(subscriptionError.getErrors())
                    .anySatisfy(graphQlError ->
                            assertThat(graphQlError.getMessage())
                                    .contains("subscription rejected"));
        })
        .verify(Duration.ofSeconds(5));
~~~

Example verifying a WebSocket disconnect:

~~~java
StepVerifier.create(subscriptionFlux)
        .expectError(WebSocketDisconnectedException.class)
        .verify(Duration.ofSeconds(5));
~~~

If a test asserts only the generic `GraphQlTransportException`, it can miss the distinction between a server-sent GraphQL error and a dropped connection. Assert the specific subtype whenever that distinction is part of the behavior under test.

## 13. Testing subscription timeouts and cancellation

A subscription is a stream spanning time, not a single-response request. Therefore, do not use a normal request's response timeout as a lifetime cap for the entire stream.

You can use Reactor's `timeout` to bound the wait between consecutive events:

~~~java
Flux<String> events = graphQlClient
        .document("subscription { events }")
        .retrieveSubscription("events")
        .toEntity(String.class)
        .timeout(Duration.ofSeconds(2));
~~~

If no new event arrives within the allowed window, the stream emits `TimeoutException`. Over WebSocket, canceling a subscription from the client sends a `complete` message telling the server to stop that subscription.

Testing cancellation after receiving the expected events:

~~~java
StepVerifier.create(events)
        .expectNext("event-1")
        .thenCancel()
        .verify(Duration.ofSeconds(3));
~~~

If you want to verify that the server observed cancellation, the test fixture can record a `doOnCancel` hook or cleanup signal on the server-side publisher:

~~~java
import reactor.core.publisher.Sinks;

Sinks.Many<String> eventSink =
        Sinks.many().multicast().onBackpressureBuffer();
Sinks.One<Void> cancellationSignal = Sinks.one();

Flux<String> eventPublisher = eventSink.asFlux()
        .doOnCancel(() -> cancellationSignal.tryEmitEmpty());

StepVerifier.create(eventPublisher)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

StepVerifier.create(cancellationSignal.asMono())
        .expectComplete()
        .verify(Duration.ofSeconds(2));
~~~

After the client cancels, the test can await `cancellationSignal` completion to verify the server cleaned up the subscription. Never use `Thread.sleep` to guess when the server received the message; synchronize with a signal or timed latch.

## 14. Retrying after transport failures

A subscription can be restarted when the transport disconnects. Spring for GraphQL client docs illustrate using Reactor `retry` for `GraphQlTransportException`, such as `WebSocketDisconnectedException`.

Example bounded retry:

~~~java
import reactor.util.retry.Retry;

Flux<String> events = graphQlClient
        .document("subscription { events }")
        .retrieveSubscription("events")
        .toEntity(String.class)
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
                .filter(WebSocketDisconnectedException.class::isInstance));
~~~

Retries should apply only to errors considered transient and recoverable:

- Temporary connection drops.
- Gateway connection resets.
- Server restarts during controlled deployment windows.

Never retry every exception unconditionally. For example, `SubscriptionErrorException` can indicate the server intentionally rejected the subscription; repeated retries will not fix a business or authorization error.

Be especially careful with mutations. If the client loses connectivity after the server executed the mutation but before the response returned, the client does not know whether the operation committed. Retrying can execute the mutation a second time. Only retry mutations when the operation uses an idempotency key or mechanism guaranteeing no duplicate side effects.

## 15. Managing tester and connection lifecycles in tests

`WebSocketGraphQlTester` and `RSocketGraphQlTester` are connection-oriented. Each tester maintains a shared connection/session across requests. Reuse a single tester for requests against the same server and close the connection once tests finish.

`RSocketGraphQlClient` also maintains a shared session. If the session is lost, the client re-establishes it on the next request or upon calling `start()`; `stop()` cancels active requests and closes the session. Accordingly, RSocket tests should clearly distinguish whether they are testing a single request failure or session reconnect behavior.

Example:

~~~java
WebSocketGraphQlTester tester =
        WebSocketGraphQlTester.builder(uri, webSocketClient).build();

try {
    tester.document("query { health }")
            .execute()
            .path("health")
            .entity(String.class)
            .isEqualTo("UP");
}
finally {
    tester.stop();
}
~~~

`RSocketGraphQlTester` also provides `stop()` to close its session. Avoid creating separate WebSocket/RSocket testers per assertion when one instance can be reused; each instance may open its own connection.

When using `WebSocketGraphQlClient`, `stop()` closes the connection and cancels active requests. Call it in teardown so connections do not stay alive after tests complete.

## 16. Designing reliable timeout tests

Timeout tests become flaky easily when coupled to machine speed, CI load, or external services. Follow these practices:

- Use `Mono.never()` or a test-controlled publisher to simulate missing responses.
- Leave a wide enough safety margin between expected latency and the timeout duration.
- Guard every `StepVerifier.verify(...)` with a maximum duration.
- Use virtual time for pure Reactor publishers whenever possible.
- Never use `Thread.sleep` to wait for asynchronous state.
- Never hit public Internet services to trigger connection failures.
- Do not assert exact Netty, DNS, or TLS error strings unless those messages are a stable contract.
- Close testers/connections in `finally`, `@AfterEach`, or lifecycle callbacks.
- Verify cancellation on timeout, not just the thrown exception.
- Keep server timeout tests separate from client response timeout tests.

With an HTTP tester, build a tester with a short `responseTimeout` as shown earlier, invoke `neverResponds`, and assert the timeout exception/cause raised by your project's transport. Avoid generic assertions accepting any `Exception` as a timeout; that can accidentally mask configuration errors, serialization failures, or broken test fixtures.

In another test, verify the client publisher timeout:

~~~java
@Test
void reactiveClientTimeoutIsBounded() {
    StepVerifier.create(Mono.<String>never()
                    .timeout(Duration.ofMillis(100)))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(2));
}
~~~

These two tests verify two different layers. Keeping them independent reveals immediately whether a failure lies in the test harness or in publisher timeout logic.

## 17. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Test hangs when resolver never completes | Missing `GraphQlTester.responseTimeout` or `StepVerifier` terminal bound | Set a response timeout and `verify(Duration)` |
| Test times out yet server keeps running | Timeout configured only on client | Test server timeout and cancellation separately |
| `errors()` fails to catch connection refused | No GraphQL response exists to inspect | Assert `GraphQlTransportException` or its cause |
| HTTP 503 treated as a GraphQL error | Confused HTTP status with response `errors` | Use `WebTestClient` to assert status codes |
| Test depends on Netty error messages | Messages vary by connector/OS | Assert stable exception types and causes |
| WebSocket test leaks open connections | Forgot to call `stop()` | Close testers/clients in teardown |
| Subscription does not stop after `thenCancel()` | Server ignores or misses cancellation | Verify publisher cleanup and await signal with a timeout |
| Retry loops indefinitely | Unbounded retries or missing exception filter | Use bounded `Retry.backoff` with a specific predicate |
| Mutation executes twice after retry | Client unsure whether first attempt committed | Use idempotency keys or avoid retrying unsafe mutations |
| Timeout test passes sporadically | Relies on `sleep`, tight margins, or external networks | Use controllable publishers and safe timeout margins |
| Server timeout confused with client timeout | Only observed request abort without knowing which layer stopped | Inspect server status and per-layer timeout configuration |

## 18. Workflow for testing timeouts and transport errors

When writing tests for a GraphQL operation, follow this order:

1. Identify whether the request is a single-response query/mutation or a subscription stream.
2. Identify whether the failure under test is a GraphQL response error, HTTP status, transport failure, or timeout.
3. Choose the tester/client matching the transport in use.
4. Set `GraphQlTester.responseTimeout` to bound how long tests wait for responses.
5. Configure connect/response timeouts on HTTP or WebSocket/RSocket clients when needed.
6. Use controllable publishers to simulate slow or non-completing resolvers.
7. Use `StepVerifier` to assert timeouts, stream errors, and cancellation.
8. Test server timeouts independently using `TimeoutWebGraphQlInterceptor` and `WebTestClient`.
9. Test transport failures via the corresponding exception/cause or HTTP status.
10. Retry only transient failures with bounded attempts; especially avoid retrying non-idempotent mutations.
11. Close connections/sessions after tests and ensure every asynchronous operation has a time bound.

## 19. Key points to remember

- `GraphQlTester.responseTimeout(Duration)` limits how long a test waits for a GraphQL response; the default is 5 seconds.
- Test timeouts, client network timeouts, and server request timeouts are three distinct scopes.
- `GraphQlTransportException` represents transport failures or transport-wrapped exceptions.
- `SubscriptionErrorException` carries GraphQL errors sent by the server over the subscription protocol.
- `WebSocketDisconnectedException` indicates a lost WebSocket connection.
- `GraphQlTester.errors()` inspects GraphQL response errors, not connection failures.
- Use `WebTestClient` directly when asserting HTTP status codes.
- Use `StepVerifier.verify(Duration)` to prevent reactive tests from hanging indefinitely.
- Subscription timeouts and cancellations must be tested as streams; WebSocket cancellation sends a `complete` message.
- Retries must be bounded and scoped to transient errors; mutations require idempotency guarantees before retrying.

Testing timeouts and transport errors well exposes faults at exact system boundaries. Separating GraphQL response errors, HTTP statuses, and transport exceptions while bounding both requests and streams produces diagnostic tests that are far less sensitive to runtime environment quirks.

## References

- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — Request Execution and GraphQL Request Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — GraphQlTransportException API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlTransportException.html)
- [Reactor Netty — Timeout Configuration](https://docs.spring.io/projectreactor/reactor-netty/docs/current/reference/html/index.html)
