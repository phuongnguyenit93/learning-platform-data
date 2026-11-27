# Testing WebSocket subscriptions

## Objectives

After this lesson, you will be able to:

- Explain the testing scope of `WebSocketGraphQlTester`.
- Configure a WebSocket endpoint and build a tester connecting to a live running server.
- Send subscriptions with `executeSubscription()` and verify streams with `StepVerifier`.
- Synchronize tests with the moment the server subscribes to the event source.
- Verify event payloads, emission ordering, and stream completion.
- Confirm cancellation propagates to the publisher to release resources.
- Distinguish GraphQL subscription errors from WebSocket transport errors.
- Test authentication via `connection_init` and multiple operations over one connection.
- Choose the right testing level for resolvers, the WebSocket protocol, and full deployments.

## Why test over WebSocket?

Subscriptions differ from queries and mutations in that a single operation can yield multiple responses over time. Resolvers typically return a `Flux` or a Reactive Streams `Publisher`. The server subscribes to the publisher, then emits each result to the client as events arrive.

A unit test calling the `Flux`-returning method directly can verify that the publisher emits the expected data, but cannot verify whether:

- The WebSocket endpoint is enabled and reachable at the configured path.
- Client and server complete the WebSocket handshake successfully.
- Both sides speak the same GraphQL-over-WebSocket subprotocol.
- Connection initialization messages and subscription operations are handled properly.
- Events are delivered as multiple responses to the client.
- Client stream cancellation causes the server to stop the publisher.
- Closing the connection terminates active operations.

Spring for GraphQL provides `WebSocketGraphQlTester` for testing GraphQL requests over a real WebSocket connection. The tester shares the `GraphQlTester` workflow while adding WebSocket transport configuration and lifecycle management. [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)

## Distinguishing subscription testing layers

Not every subscription test needs to open a WebSocket. Choose the tester matching the boundary you want to verify:

| Testing approach | What is verified | What is not verified |
| --- | --- | --- |
| Publisher unit test with `StepVerifier` | Event emission logic, ordering, and `Flux` cancellation | GraphQL schema, resolver mapping, WebSocket protocol |
| `ExecutionGraphQlServiceTester` | Server-side GraphQL subscription execution | WebSocket handshake and message protocol |
| `WebGraphQlTester` | `WebGraphQlHandler`, interceptor chain, and server-side subscription execution | WebSocket handshake, `connection_init`, and real transport |
| `WebSocketGraphQlTester` | WebSocket connection, GraphQL operations, event stream, and cancellation | Real TLS/proxy/load balancer if tests do not traverse them |
| End-to-end test in deployment environment | Integration of server, proxy, auth, network, and real clients | Does not replace fast unit tests for publisher logic |

If your goal is testing publisher or business logic, unit tests are usually faster and easier to diagnose. When you need to prove subscriptions flow properly over WebSocket, use `WebSocketGraphQlTester` against a running server.

## Preparing the endpoint and dependencies

The application needs Spring for GraphQL and a WebSocket server transport. Spring Boot does not enable the GraphQL WebSocket endpoint by default; configure the path to register the handler:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 10s
      keep-alive: 20s
~~~

With Spring MVC, add `spring-boot-starter-websocket`. With Spring WebFlux, WebSocket transport is already included in the WebFlux stack. The application also needs `spring-boot-starter-graphql`.

On the test side, add `spring-graphql-test` and `reactor-test`:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

`WebSocketGraphQlTester` uses `WebSocketClient` from Spring WebFlux. If an MVC application lacks a WebSocket client, add Spring WebFlux and a client implementation such as Reactor Netty to the test runtime via Spring Boot's dependency management. You do not need to switch your MVC server to WebFlux just to run the tester.

Keep Spring GraphQL, Spring Boot, Spring Framework, and Reactor versions aligned through your project BOM. The example APIs below use current Spring for GraphQL APIs; if your project is on an older release line, check the matching packages and dependencies.

## Creating WebSocketGraphQlTester

`WebSocketGraphQlTester` requires an endpoint URL and a `WebSocketClient`. Example test starting the application on a random port:

~~~java
import java.time.Duration;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.graphql.websocket.path=/graphql")
class BookSubscriptionWebSocketTests {

    @LocalServerPort
    int port;

    @Autowired
    TestBookEventSource eventSource;

    WebSocketGraphQlTester tester;

    @BeforeEach
    void setUp() {
        String url = "ws://localhost:" + port + "/graphql";
        tester = WebSocketGraphQlTester.builder(
                url, new ReactorNettyWebSocketClient()).build();
    }

    @AfterEach
    void tearDown() {
        if (tester != null) {
            tester.stop().block(Duration.ofSeconds(5));
        }
    }
}
~~~

`RANDOM_PORT` lets Spring Boot start a real server during the test. Client URLs use `ws://` for unencrypted connections; HTTPS environments require a `wss://` endpoint with matching TLS configuration.

`WebSocketGraphQlTester` is connection-oriented and multiplexed. Each instance maintains a shared connection across multiple requests/operations. Reuse the tester within the scope of a test suite or test class rather than creating a new instance for every event. Call `stop()` when finished to close the connection and cancel active requests.

The connection is usually established automatically when the first request is sent. You can call `tester.start().block()` if a test must open the connection explicitly before sending operations—for instance, to test handshake or initialization timing. Calling `start()` before every request is not mandatory.

## Writing sample subscription resolvers

Schema declaring the root `Subscription`:

~~~graphql
type Subscription {
  greetings: String!
}
~~~

Resolver returning a finite stream:

~~~java
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class GreetingSubscriptionController {

    @SubscriptionMapping
    public Flux<String> greetings() {
        return Flux.just("Hi", "Bonjour", "Hola");
    }
}
~~~

The resolver emits three values and completes. This is a finite event source, ideal for testing multi-response delivery and operation completion without synchronizing against a shared publisher.

For dynamic events, the schema and resolver can be declared as follows:

~~~graphql
enum BookCategory {
  TECHNOLOGY
  FICTION
}

extend type Subscription {
  bookCreated(category: BookCategory): BookCreatedEvent!
}

type BookCreatedEvent {
  eventId: ID!
  book: BookView!
}

type BookView {
  id: ID!
  title: String!
}
~~~

~~~java
import org.springframework.graphql.data.method.annotation.Argument;

@Controller
public class BookSubscriptionController {

    private final TestBookEventSource eventSource;

    public BookSubscriptionController(TestBookEventSource eventSource) {
        this.eventSource = eventSource;
    }

    @SubscriptionMapping
    public Flux<BookCreatedEvent> bookCreated(
            @Argument("category") BookCategory category) {
        return eventSource.events()
                .filter(event -> category == null
                        || event.category() == category);
    }
}
~~~

Corresponding Java data types:

~~~java
public enum BookCategory {
    TECHNOLOGY, FICTION
}

public record BookCreatedEvent(
        String eventId,
        BookView book,
        BookCategory category) {
}

public record BookView(String id, String title) {
}
~~~

In real applications, the event source should filter by permissions and tenant on the server. The example above merely illustrates filtering to test arguments; never use a client-supplied category as an authorization mechanism.

## Verifying the event stream with executeSubscription()

For subscriptions, use `executeSubscription()` instead of `execute()`. This method returns a response stream; `toFlux(path, type)` decodes the field at the given path in each response:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import org.springframework.graphql.client.SubscriptionErrorException;

@Test
void receivesAllGreetingEvents() {
    Flux<String> greetings = tester.document("""
            subscription GreetingEvents {
                greetings
            }
            """)
            .executeSubscription()
            .toFlux("greetings", String.class);

    StepVerifier.create(greetings)
            .expectNext("Hi")
            .expectNext("Bonjour")
            .expectNext("Hola")
            .verifyComplete(Duration.ofSeconds(10));
}
~~~

`StepVerifier` verifies ordering, payloads, and completion signals on the `Flux`. `verifyComplete(Duration)` enforces a time limit on the entire test so a stalled subscription never hangs the suite indefinitely.

`execute()` is meant for single-response operations like queries or mutations. Using it for subscriptions will not test the response stream. Whenever a subscription emits continuous data, always test the stream with `executeSubscription()` and Reactor Test.

## Testing variables and arguments

Subscriptions can accept arguments just like queries:

~~~graphql
extend type Subscription {
  bookCreated(category: BookCategory): BookCreatedEvent!
}
~~~

Client passing a variable:

~~~java
Flux<BookCreatedEvent> events = tester.document("""
        subscription BookCreated($category: BookCategory) {
            bookCreated(category: $category) {
                eventId
                book {
                    id
                    title
                }
            }
        }
        """)
        .variable("category", "TECHNOLOGY")
        .executeSubscription()
        .toFlux("bookCreated", BookCreatedEvent.class);
~~~

Tests should verify that the event source applies the right filter and does not emit out-of-scope events:

- Emit a `TECHNOLOGY` event.
- Emit a `FICTION` event.
- Verify the subscriber receives only the `TECHNOLOGY` event.
- Verify other subscribers with different filters do not receive each other's data.

Do not test only the event payload. When filtering is part of the contract, test the filtering behavior itself to prevent cross-subscriber data leaks.

## Synchronizing tests with when the server subscribes

A common pitfall in asynchronous tests is emitting events too early. `StepVerifier.create(flux)` subscribes to the client-side `Flux`, which does not mean the server has already received the subscribe message and subscribed to the event publisher.

If a test emits an event immediately after creating the `Flux`, the event may fire before the server subscribes. With a non-replaying multicast sink, that event will be missed and the test can time out.

A test fixture can signal when the publisher is subscribed to and when cancellation arrives:

~~~java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class TestBookEventSource {

    private final Sinks.Many<BookCreatedEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer(16, false);

    private final CountDownLatch subscribed = new CountDownLatch(1);
    private final CountDownLatch cancelled = new CountDownLatch(1);

    public Flux<BookCreatedEvent> events() {
        return sink.asFlux()
                .doOnSubscribe(subscription -> subscribed.countDown())
                .doOnCancel(cancelled::countDown);
    }

    public void publish(BookCreatedEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            throw new IllegalStateException("Could not publish test event: " + result);
        }
    }

    public boolean awaitSubscribed(Duration timeout) throws InterruptedException {
        return subscribed.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }

    public boolean awaitCancelled(Duration timeout) throws InterruptedException {
        return cancelled.await(timeout.toMillis(), TimeUnit.MILLISECONDS);
    }
}
~~~

This fixture illustrates a single test; if multiple tests share the same bean, recreate the latches or reset state between tests. `onBackpressureBuffer(16, false)` bounds the buffer and keeps the sink active after the last subscriber cancels. Test fixtures must check `EmitResult` so failed emissions are never silently ignored.

The subscription test can await the subscribe signal before emitting:

~~~java
@Test
void receivesEventAndCancelsSource() throws Exception {
    BookCreatedEvent expected = new BookCreatedEvent(
            "event-1",
            new BookView("book-101", "Spring for GraphQL"),
            BookCategory.TECHNOLOGY);

    Flux<BookCreatedEvent> events = tester.document("""
            subscription {
                bookCreated {
                    eventId
                    book {
                        id
                        title
                    }
                }
            }
            """)
            .executeSubscription()
            .toFlux("bookCreated", BookCreatedEvent.class);

    StepVerifier.create(events)
            .then(() -> {
                assertThat(eventSource.awaitSubscribed(Duration.ofSeconds(5)))
                        .isTrue();
                eventSource.publish(expected);
            })
            .expectNext(expected)
            .thenCancel()
            .verify(Duration.ofSeconds(10));

    assertThat(eventSource.awaitCancelled(Duration.ofSeconds(5))).isTrue();
}
~~~

When the client cancels the subscription, the transport sends a `complete` message for that operation. The server cancels its subscription to the publisher; the test fixture observes the cancellation via `doOnCancel`. This proves the event source is released once the client stops listening.

Never use `Thread.sleep()` to guess when the server has subscribed. Use latches, signals, or conditional synchronization so tests remain reliable on slow machines and in CI.

## Testing multiple subscriptions on one connection

`WebSocketGraphQlTester` multiplexes multiple operations over a single connection. Each subscription operation has its own protocol ID, so the server must route each event stream to the right operation.

You can test two concurrent subscriptions:

~~~java
Flux<BookCreatedEvent> technologyEvents = tester.document("""
        subscription {
            bookCreated(category: TECHNOLOGY) {
                eventId
                book { id title }
            }
        }
        """)
        .executeSubscription()
        .toFlux("bookCreated", BookCreatedEvent.class);

Flux<BookCreatedEvent> fictionEvents = tester.document("""
        subscription {
            bookCreated(category: FICTION) {
                eventId
                book { id title }
            }
        }
        """)
        .executeSubscription()
        .toFlux("bookCreated", BookCreatedEvent.class);
~~~

Subscribe to both streams in the same test, wait until both sources are subscribed, then emit events for each category. Verify each stream receives only its matching events. When done, cancel both streams and confirm the publisher has no remaining subscribers.

Do not create a separate `WebSocketGraphQlTester` per operation when your goal is to test multiplexing. Sharing the same tester proves multiple operations run over a single connection.

## Testing cancellation and cleanup

Cancellation is part of the subscription contract. When a user leaves a page, closes a screen, or aborts a task, the client must stop receiving events. The server must release:

- Listeners registered with event sources or message brokers.
- Database cursors or external system streams.
- Per-operation buffers and queues.
- Contexts, tracing spans, and stream-bound callbacks.

A cancellation test should verify two things:

1. The client-side `Flux` terminates upon the test's cancellation.
2. The server-side publisher or adapter receives cancellation and cleans up listeners/resources.

`StepVerifier.thenCancel()` only cancels the subscription on the client side. To prove server-side cleanup, observe the source using a latch, counter, spy, or resource test fixture. Never conclude the server released resources merely because the test client called dispose or cancel.

When testing multiple operations, cancel individual streams or call `tester.stop()` to close the connection. `stop()` cancels active requests, closes the WebSocket connection, and rejects new requests on that tester. After calling `stop()`, create a new tester if a test needs to reconnect.

## Testing subscription errors

Distinguish errors occurring inside the GraphQL subscription from errors at the WebSocket layer:

| Error type | Example | Client-side outcome |
| --- | --- | --- |
| GraphQL error in publisher | Publisher terminates with an error translated by `SubscriptionExceptionResolver` into GraphQL errors | `SubscriptionErrorException` |
| WebSocket closed mid-stream | Server restart, proxy closes connection, or client stops | `WebSocketDisconnectedException`, a `GraphQlTransportException` |
| Connection open or protocol init failure | Wrong endpoint, failed handshake, or rejected connection init | Transport/connection initialization error |
| Invalid query document | Unknown field or wrong variable type | GraphQL request error; operation never starts a normal stream |

Errors raised after the subscription `Publisher` is created do not pass through regular `DataFetcherExceptionResolver` instances, because the data fetcher only creates the initial `Publisher`. Spring for GraphQL provides `SubscriptionExceptionResolver` to translate `Publisher` errors into GraphQL errors sent in the terminal `error` message. [Request Execution – Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)

`SubscriptionErrorException` is a `GraphQlTransportException` carrying the list of GraphQL errors received from the operation's `error` message. `WebSocketDisconnectedException` is also a `GraphQlTransportException`, indicating the connection was closed or lost while the stream was active. Separating these two causes lets clients choose the right recovery strategy.

Example testing an error translated into a subscription error by a resolver:

~~~java
Flux<String> greetings = tester.document("""
        subscription {
            greetings
        }
        """)
        .executeSubscription()
        .toFlux("greetings", String.class);

StepVerifier.create(greetings)
        .expectNext("Hi")
        .expectError(SubscriptionErrorException.class)
        .verify(Duration.ofSeconds(10));
~~~

This test assumes the server publisher emits `"Hi"` and then terminates with an error handled by `SubscriptionExceptionResolver`. You can inspect the GraphQL errors inside `SubscriptionErrorException` to assert application-specific error codes.

For transport disconnects, assert `WebSocketDisconnectedException` or its parent `GraphQlTransportException` depending on the level of detail your test requires. Do not assert that every subscription failure is a GraphQL error; a dropped connection is a distinct transport failure.

## Testing authentication via connection_init

The WebSocket protocol sends a `connection_init` message at connection startup. When the server extracts tokens from this payload, the test client must send that payload properly.

Spring for GraphQL provides `WebSocketGraphQlClientInterceptor` to supply connection initialization payloads. The `WebSocketGraphQlTester` builder allows registering client interceptors:

~~~java
import java.util.Map;

import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;
import reactor.core.publisher.Mono;

WebSocketGraphQlClientInterceptor authInterceptor =
        new WebSocketGraphQlClientInterceptor() {

            @Override
            public Mono<Object> connectionInitPayload() {
                return Mono.just(Map.of(
                        "Authorization", "Bearer test-token"));
            }
        };

WebSocketGraphQlTester authenticatedTester =
        WebSocketGraphQlTester.builder(
                url, new ReactorNettyWebSocketClient())
                .interceptor(authInterceptor)
                .build();
~~~

The server needs a matching WebSocket authentication interceptor to read the payload, validate the token, and propagate `SecurityContext` to subscription requests. Built-in `AuthenticationWebSocketInterceptor` implementations exist for WebMVC and WebFlux; applications can also implement a custom `WebSocketGraphQlInterceptor`.

Tests should cover at least two cases:

- Valid token: the connection is accepted and the subscription receives only events permitted for that principal.
- Invalid or missing token: connection init is rejected or the operation is denied according to server policy.

Do not check only that the client sent a header or payload. Verify that the server actually enforces identity and authorization on the subscription results. WebSocket handshake headers and the `connection_init` payload are two different places; target whichever one your server authentication interceptor reads.

## Connection lifecycle, reconnects, and timeouts

`WebSocketGraphQlTester` maintains a shared connection. You can open it explicitly with `start()` and close it with `stop()`. When the connection drops, the tester/client may reconnect for the next request or upon calling `start` again; active subscriptions may terminate with a transport error.

Reconnecting does not automatically guarantee event delivery:

- Events emitted while the client is disconnected can be missed.
- If the event source replays history, the client may receive already-processed events again.
- Retrying a subscription does not automatically provide exactly-once delivery.

When an application supports resuming, events should carry an ID or cursor. The client persists its last processed checkpoint and sends that cursor upon re-subscribing; the server uses an event store or replay-capable broker to resume from the right position. Reconnect tests should verify the application's actual replay/idempotency contract instead of assuming WebSocket preserves history automatically.

Configure timeouts for both responses and streams:

- `responseTimeout` on the tester bounds response wait times globally.
- `StepVerifier.verify(Duration)` bounds stream test duration.
- Server-side `connection-init-timeout` bounds waiting for connection initialization.
- `keep-alive` and proxy/load balancer timeouts must align to avoid unexpected idle disconnects.

Tests should always use finite timeouts to fail fast if the server stops emitting events or the handshake stalls.

## Protocol checks and tester boundaries

`WebSocketGraphQlTester` tests the WebSocket client transport and GraphQL operations using the protocol supported by Spring for GraphQL. It abstracts message framing so tests do not have to hand-craft JSON for `connection_init`, `subscribe`, `next`, `error`, and `complete`.

When you need to verify exact frames, close codes, or low-level protocol details, add tests using a low-level WebSocket client or protocol conformance tests. Do not couple business tests to raw internal JSON strings of every message.

Spring for GraphQL supports GraphQL over WebSocket using the `graphql-transport-ws` protocol from the `graphql-ws` project. The older `subscriptions-transport-ws` protocol is a different protocol; client and server must agree on the protocol. [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)

`WebSocketGraphQlTester` does not test TLS certificates, reverse proxies, load balancers, firewalls, or production connection limits unless tests actually traverse them. Those deployment risks require dedicated integration or end-to-end tests.

## Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Handshake returns 404 | WebSocket endpoint is disabled or path is wrong | Configure `spring.graphql.websocket.path` and verify URL |
| Handshake fails | Used `http`/`https` scheme or server is not ready | Use `ws`/`wss` and wait for server startup |
| Test times out with no events | Event emitted before server subscribed | Synchronize using latches or subscription signals |
| Test receives one response and stops | Used `execute()` instead of `executeSubscription()` | Use `executeSubscription()` and `StepVerifier` |
| Test hangs when publisher never completes | Called `verifyComplete` on an infinite stream | Use `thenCancel()` or explicit timeout |
| Cancellation does not release listeners | Source ignores cancel or test only canceled client side | Observe `doOnCancel`/`doFinally` and real cleanup |
| Events from different subscriptions mix | Wrong filtering or improper operation correlation | Share tester, filter explicitly, and assert each stream |
| Publisher error turns into transport error | `SubscriptionExceptionResolver` not configured or server closed connection | Distinguish `SubscriptionErrorException` from `GraphQlTransportException` |
| Auth test stays anonymous | Credentials sent in handshake while server reads `connection_init` | Send payload via `WebSocketGraphQlClientInterceptor` |
| Reconnect test misses or duplicates events | Missing cursor or idempotency | Add event IDs/checkpoints and test replay contract |
| Test passes with `WebGraphQlTester` yet WS fails in prod | Test bypassed WebSocket transport | Add `WebSocketGraphQlTester` tests against a real server |

## Putting it all together

Build an integration test for a new-book notification feature:

1. Enable the endpoint via `spring.graphql.websocket.path=/graphql`.
2. Declare `Subscription.bookCreated` and `BookCreatedEvent` in the SDL.
3. Build a publisher that emits events and exposes subscribe/cancel hooks in a test fixture.
4. Write a `@SubscriptionMapping` resolver returning `Flux<BookCreatedEvent>`.
5. Boot the application with `@SpringBootTest(webEnvironment = RANDOM_PORT)`.
6. Create `WebSocketGraphQlTester` using the `ws://` endpoint and `ReactorNettyWebSocketClient`.
7. Send the subscription via `executeSubscription()` and verify events with `StepVerifier`.
8. Wait until the server subscribes before emitting events to eliminate race conditions.
9. Cancel the stream with `thenCancel()` and verify the server publisher receives cancellation.
10. Create a category-filtered subscription and verify each client receives only matching events.
11. Send a token in the `connection_init` payload and test valid/invalid tokens.
12. Test `SubscriptionErrorException`, `WebSocketDisconnectedException`, and connection cleanup.
13. Call `tester.stop()` after tests to close the connection.

Once finished, explain why `StepVerifier` must synchronize with the server-side subscription, the difference between `Publisher` errors and transport errors, and how to prove cancellation actually reached the event source.

## Key takeaways

`WebSocketGraphQlTester` tests subscriptions over a real WebSocket connection. Create the tester with an endpoint URL and `WebSocketClient`, send operations via `executeSubscription()`, and use `StepVerifier` to verify events, ordering, and terminal signals. For asynchronous publishers, synchronize with server subscription timing before emitting events; avoid `sleep` guesses. Use `thenCancel()` to cancel streams and verify the server publisher observes cancellation. Distinguish `SubscriptionErrorException` from GraphQL publisher errors vs. `WebSocketDisconnectedException` from lost transport connections. Use `WebSocketGraphQlClientInterceptor` to supply `connection_init` payloads when testing authentication. Reuse connections within tests, enforce finite timeouts, and always call `stop()` for cleanup.

## References

- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [WebSocketGraphQlTester API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/test/tester/WebSocketGraphQlTester.html)
- [GraphQlClient.RequestSpec – executeSubscription](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [Spring for GraphQL – Client WebSocket](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL – Request Execution, Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
