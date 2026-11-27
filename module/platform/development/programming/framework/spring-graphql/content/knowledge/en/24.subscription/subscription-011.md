# Subscriptions with WebSocket

## Objectives

After this lesson, you will be able to:

- Explain why Subscriptions require a streaming-capable transport.
- Configure a GraphQL WebSocket endpoint in Spring Boot.
- Declare a `Subscription` root and write a resolver using `@SubscriptionMapping`.
- Emit events with `Flux` and connect to an in-application event source.
- Understand connection and operation lifecycles under the `graphql-transport-ws` protocol.
- Create a client with `WebSocketGraphQlClient` and cancel subscriptions properly.
- Authenticate connections, bound resources, and handle disconnections.
- Test resolver streams and the WebSocket transport.

## Subscriptions and WebSocket

Queries and Mutations typically produce one response per execution. Subscriptions have different semantics: the client subscribes to receive results emitted over time whenever events occur.

For example, a library application can send notifications when a new book is added:

~~~graphql
type Subscription {
  bookCreated: BookCreatedEvent!
}

type BookCreatedEvent {
  eventId: ID!
  occurredAt: String!
  book: Book!
}
~~~

The client sends the operation once, and the server sends multiple results for the same subscription. WebSocket keeps a bidirectional connection open so the server can push data proactively to the client without continuous client polling.

Spring for GraphQL supports the WebSocket transport for subscriptions. This transport can also handle single-result queries and mutations, though its primary use case is streaming. For both Spring MVC and Spring WebFlux, Spring provides dedicated WebSocket handlers; WebFlux uses non-blocking I/O and Reactive Streams to transfer data.

WebSocket is a long-lived connection. A single connection can carry multiple concurrent subscription operations. Each operation has its own ID so client and server can correlate messages accurately.

## Declaring the Subscription root in SDL

The GraphQL schema must declare the `Subscription` root type and the fields clients can subscribe to:

~~~graphql
type Subscription {
  bookCreated: BookCreatedEvent!
}

type BookCreatedEvent {
  eventId: ID!
  occurredAt: String!
  book: Book!
}

enum BookCategory {
  FICTION
  TECHNOLOGY
  HISTORY
}

type Book {
  id: ID!
  title: String!
  category: BookCategory!
  author: Author
}
~~~

`bookCreated` emits a `BookCreatedEvent` whenever a book-creation event occurs. `eventId` helps the client identify the event; `occurredAt` describes when it occurred; `book` contains the book data the client needs.

Subscription fields can accept arguments like any other GraphQL field. For example, a client can subscribe to events by category or tenant scope. Any filtering criteria tied to access rights must be verified on the server; never trust a client-sent value simply because it arrived in an argument.

Each subscription operation must select one root field. If a client needs to watch two event types, it can open two separate subscription operations over the same WebSocket connection.

## Enabling the WebSocket endpoint in Spring Boot

Spring Boot does not enable the GraphQL WebSocket endpoint by default. Choose the dependency matching your application stack:

| Application | WebSocket dependency |
| --- | --- |
| Spring MVC / Servlet | `spring-boot-starter-websocket` |
| Spring WebFlux | `spring-boot-starter-webflux` already provides WebSocket transport |

The application also needs `spring-boot-starter-graphql`. Gradle example for Spring MVC:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
}
~~~

For WebFlux applications, use `spring-boot-starter-webflux` instead of the MVC starter, and no separate WebSocket starter is required.

Configure the endpoint path in `application.yml`:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 60s
      keep-alive: 25s
~~~

The `spring.graphql.websocket.path` property enables the endpoint and sets the WebSocket path. If HTTP GraphQL also uses `/graphql`, clients can send HTTP POST for queries/mutations and open a WebSocket to the same path for subscriptions; the server distinguishes transports via HTTP requests vs. WebSocket handshakes.

`connection-init-timeout` limits how long the server waits for the connection initialization message. `keep-alive` lets the server send pings when a connection is idle. Choose practical values based on timeouts of proxies, load balancers, and the network between client and server.

If using an older Spring Boot version, check properties and dependencies against your project's BOM. Never mix arbitrary versions of Spring for GraphQL, Spring Boot, and Spring Framework.

## Writing a resolver with @SubscriptionMapping

In an annotated controller, use `@SubscriptionMapping` to map a method to a field on the `Subscription` root. The method typically returns `Flux<T>` or a Reactive Streams `Publisher`.

~~~java
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class BookSubscriptionController {

    private final BookEventPublisher eventPublisher;

    public BookSubscriptionController(BookEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @SubscriptionMapping
    public Flux<BookCreatedEvent> bookCreated() {
        return eventPublisher.bookCreatedEvents();
    }
}
~~~

The method does not return a single event immediately. It returns a publisher representing the event stream. Each item emitted by the publisher becomes a result for the `bookCreated` field.

Do not use `@QueryMapping` for fields on the `Subscription` root. The `@SubscriptionMapping` annotation tells Spring this method supplies a streaming source for a subscription operation.

If filtering by an argument is needed, you can accept `@Argument`:

~~~java
@SubscriptionMapping
public Flux<BookCreatedEvent> bookCreated(
        @Argument("category") BookCategory category) {

    return eventPublisher.bookCreatedEvents()
            .filter(event -> event.book().category() == category);
}
~~~

This is only an example of filtering by category. For private data, apply authorization and tenant filtering inside the service or event source so events are never emitted outside the subscriber's allowed scope.

## Creating an event source in the application

The resolver needs a source emitting events. In a small single-instance example, you can use Reactor `Sinks` to bridge events from the business flow into a `Flux`:

~~~java
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class BookEventPublisher {

    private final Sinks.Many<BookCreatedEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer(256, false);

    public Flux<BookCreatedEvent> bookCreatedEvents() {
        return sink.asFlux();
    }

    public void publish(BookCreatedEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            // Log/record metrics and handle according to the application's event publishing policy.
        }
    }
}
~~~

When the service creates a book successfully, it can publish an event:

~~~java
public Book create(CreateBookInput input) {
    Book saved = bookRepository.save(mapToBook(input));

    BookCreatedEvent event = new BookCreatedEvent(
            UUID.randomUUID().toString(),
            Instant.now().toString(),
            saved);

    bookEventPublisher.publish(event);
    return saved;
}
~~~

The code above illustrates connecting a business event to a publisher. In transactional applications, choose carefully when to emit the event to avoid notifying clients about uncommitted data. If you must ensure events are not lost between database commit and publishing, consider a transactional outbox or message broker.

`Sinks.Many` in this example lives only in the memory of a single process and multicasts each event to currently active subscribers. The buffer is bounded at 256 items; setting `autoCancel=false` keeps the sink alive when the last subscriber cancels so new clients can subscribe later. If consumers are slower than producers and the buffer fills up, `tryEmitNext` can return `FAIL_OVERFLOW`. The application should log/record metrics and decide whether to retry, drop the event, or move to a broker. This is an option for simple examples, not a durable event store. A multicast sink does not replay events already delivered to active subscribers for newly arriving subscribers; the pre-first-subscriber buffer also holds only a bounded number of items. When the server restarts, in-memory events are lost.

In multi-instance deployments, a client connected to instance A receives only events that instance A knows about. Use a shared broker such as Kafka, RabbitMQ, or Redis Pub/Sub to distribute events to instances holding WebSocket connections. If replay, delivery acknowledgment, or resumption after disconnect is required, you need event IDs/cursors and a replay-capable store; WebSocket alone does not provide those guarantees.

## GraphQL over WebSocket protocol flow

Spring for GraphQL implements the GraphQL over WebSocket protocol from the `graphql-ws` project, using the `graphql-transport-ws` WebSocket subprotocol. A basic lifecycle:

This protocol is incompatible with the legacy `subscriptions-transport-ws` protocol. Use clients and servers that both support `graphql-transport-ws`.

~~~mermaid
sequenceDiagram
    participant C as GraphQL Client
    participant W as WebSocket Handler
    participant G as GraphQL Engine
    participant E as Event Publisher
    C->>W: WebSocket handshake
    C->>W: connection_init
    W-->>C: connection_ack
    C->>W: subscribe (operation ID + document)
    W->>G: Execute subscription
    G->>E: Subscribe to event Flux
    E-->>G: Event 1
    G-->>C: next (data)
    E-->>G: Event 2
    G-->>C: next (data)
    C->>W: complete (cancel operation)
    W->>G: Cancel subscription
    G-->>E: Cancel source subscription
~~~

Key messages:

| Message | Direction | Role |
| --- | --- | --- |
| `connection_init` | Client → Server | Starts the GraphQL connection and may carry an authentication payload |
| `connection_ack` | Server → Client | Confirms the connection was accepted |
| `subscribe` | Client → Server | Sends a GraphQL operation with a unique ID |
| `next` | Server → Client | Sends one execution result for an operation |
| `error` | Server → Client | Terminates the operation with an error |
| `complete` | Bidirectional | Server signals stream completion or client requests cancelling the operation |
| `ping` / `pong` | Bidirectional | Checks connectivity and keeps the connection alive |

Example initialization message:

~~~json
{
  "type": "connection_init",
  "payload": {
    "Authorization": "Bearer <access-token>"
  }
}
~~~

After the server authenticates and accepts:

~~~json
{
  "type": "connection_ack"
}
~~~

Client registers an operation:

~~~json
{
  "id": "subscription-1",
  "type": "subscribe",
  "payload": {
    "query": "subscription { bookCreated { eventId book { id title } } }"
  }
}
~~~

Each event is sent in a `next` message with the same operation ID. When the stream finishes, the server sends `complete`. If the client wants to stop receiving events, it sends `complete` for the corresponding operation ID; the server cancels the source subscription to release resources.

One WebSocket connection can have multiple active operations. Operation IDs must be unique among in-flight operations on that connection. Never reuse an ID while the previous operation has not completed.

## GraphQL client with WebSocketGraphQlClient

Spring for GraphQL provides `WebSocketGraphQlClient` to send operations over a shared WebSocket connection:

~~~java
import java.time.Duration;
import org.springframework.graphql.client.WebSocketGraphQlClient;
import org.springframework.web.reactive.socket.client.WebSocketClient;
import org.springframework.web.reactive.socket.client.ReactorNettyWebSocketClient;

String url = "ws://localhost:8080/graphql";
WebSocketClient transport = new ReactorNettyWebSocketClient();

WebSocketGraphQlClient client =
        WebSocketGraphQlClient.builder(url, transport)
                .keepAlive(Duration.ofSeconds(30))
                .build();
~~~

The client opens a connection on demand, or you can call `start()` to open the connection ahead of time. `WebSocketGraphQlClient` is multiplexed: multiple requests and subscriptions can share one connection. Reuse a single client per server instead of creating a new client for each subscription.

Subscribing to a stream:

~~~java
Flux<BookCreatedEvent> events = client.document("""
        subscription BookCreated {
            bookCreated {
                eventId
                occurredAt
                book {
                    id
                    title
                }
            }
        }
        """)
    .retrieveSubscription("bookCreated")
    .toEntity(BookCreatedEvent.class);
~~~

`retrieveSubscription` returns a `Flux` where each item corresponds to one subscription response. If you need to inspect the full response, including GraphQL errors and multiple fields, use `executeSubscription`.

To stop receiving events, cancel the reactive subscription:

~~~java
Disposable disposable = events.subscribe(
        event -> System.out.println("New book: " + event.book().title()),
        error -> log.error("Subscription failed", error));

// When the screen or use case ends:
disposable.dispose();
~~~

Cancelling the `Flux` causes the WebSocket transport to send a `complete` message for that operation. When the client calls `client.stop()`, in-flight requests are cancelled, the connection closes, and the client stops accepting new requests until restarted.

## Authenticating the WebSocket connection

The WebSocket handshake and GraphQL connection initialization are two separate steps:

1. Handshake establishes the WebSocket connection at the transport layer.
2. `connection_init` initializes the GraphQL connection at the protocol layer.

A client can send an access token in the `connection_init` payload. Spring for GraphQL provides `WebSocketGraphQlClientInterceptor` to build that payload:

~~~java
import java.util.Map;
import reactor.core.publisher.Mono;
import org.springframework.graphql.client.WebSocketGraphQlClientInterceptor;

WebSocketGraphQlClientInterceptor authenticationInterceptor =
        new WebSocketGraphQlClientInterceptor() {

            @Override
            public Mono<Object> connectionInitPayload() {
                return Mono.just(Map.of(
                        "Authorization",
                        "Bearer " + accessToken));
            }
        };
~~~

Register the interceptor with the client builder:

~~~java
WebSocketGraphQlClient client =
        WebSocketGraphQlClient.builder(url, transport)
                .interceptor(authenticationInterceptor)
                .build();
~~~

On the server side, `WebSocketGraphQlInterceptor` adds connection lifecycle callbacks in addition to intercepting each GraphQL request. Spring for GraphQL provides `AuthenticationWebSocketInterceptor` for both WebMVC and WebFlux to extract credentials from the `connection_init` payload, authenticate them, and propagate `SecurityContext` to subsequent requests on the connection.

If custom authentication is needed, verify the token in the connection initialization callback and bind the verified identity to the security context or request context. Never trust a `userId`, `tenantId`, or role self-declared by the client in the payload unless verified from a token or server-side source.

A `WebSocketGraphQlInterceptor` can handle lifecycle and cancellation; at most one interceptor of this type can be in a chain. You can combine regular `WebGraphQlInterceptor`s for request processing, provided ordering and scope are clearly designed.

### Long-lived connections and expired tokens

WebSocket authentication is typically bound to the connection, whereas a connection can outlive an access token's expiration. The application must decide how to handle expired tokens:

- Close the connection and require the client to re-authenticate.
- Have the client open a new connection with a refreshed token.
- Cap maximum connection lifetime.
- Check authorization per operation and, when needed, per emitted event.

Never assume authenticating once during `connection_init` means every subsequent subscription remains authorized forever. User permissions can change; events can carry private data; each stream source must enforce proper tenant and security scoping.

In production, use `wss://` to encrypt traffic on the network. Validate the WebSocket handshake origin, authenticate, and authorize on the server. HTTP CORS does not replace WebSocket origin validation and authentication.

## Cancelling subscriptions and releasing resources

A subscription can hold onto several resources:

- Registrations with an event publisher or message broker.
- Database cursors or streams from external systems.
- Event buffers and queues.
- Context, tracing spans, and security metadata.

When the client sends `complete`, closes the connection, or cancels the `Flux`, the source publisher should receive cancellation and release the corresponding resources. When building streams from external APIs, use proper cleanup operators/callbacks and never let a cancelled subscription keep consuming resources.

A WebSocket connection can hold multiple concurrent subscriptions. Spring lets you configure `maxSubscriptionsPerSession` on `GraphQlWebSocketHandler`; by default there is no limit. Consider bounding open connections on the server, message buffer sizes, and concurrent operations per session.

With WebFlux, leverage Reactive Streams and backpressure. Avoid `.block()` in pipelines and avoid unbounded buffers when producers can emit faster than consumers. Monitor connection counts, active subscriptions, event rates, queue sizes, cancellations, and transport errors.

## Handling errors and disconnections

Distinguish between two error groups:

- GraphQL operation errors: invalid document, unauthorized subscription, or resolver failing to create the stream. The server can send an error for the operation.
- Transport errors: WebSocket closed, proxy timeout, network interruption, or server restart. The client receives a connection error and must decide whether to reconnect.

`WebSocketGraphQlClient` can automatically re-establish the connection when the next request is sent or when `start()` is called after a connection loss. An interrupted subscription `Flux` may terminate with a `GraphQlTransportException`, such as `WebSocketDisconnectedException`.

If the server sends an `error` message to terminate a subscription operation, the client-side `Flux` may terminate with `SubscriptionErrorException`; this exception exposes the relevant GraphQL errors. If the connection drops, the client receives a transport error such as `WebSocketDisconnectedException`. Handle these two error types under different policies.

Clients can use retry to re-subscribe, but must understand the consequences:

- Events emitted during the disconnection window may be missed.
- If the source replays events, the client may receive events it already processed.
- Retry does not automatically guarantee exactly-once delivery.

For stronger reliability, events should carry a unique ID or sequence/cursor. The client stores the last processed checkpoint and sends the cursor when re-subscribing; the server uses a replay-capable event source to resume from the right position. Design idempotency so clients do not process duplicate events twice.

## Testing Subscriptions

Separate testing of stream sources/resolvers from testing the WebSocket transport.

### Testing the publisher and resolver

`StepVerifier` tests a `Flux` and cancellation without opening a WebSocket:

~~~java
StepVerifier.create(bookEventPublisher.bookCreatedEvents().take(1))
        .then(() -> bookEventPublisher.publish(expectedEvent))
        .expectNext(expectedEvent)
        .verifyComplete();
~~~

This test verifies that the publisher emits an event and the consumer receives the item. You can also test that cancellation detaches listeners or registrations from the event source.

### Testing over WebSocket

Integration tests should start the application with a real WebSocket endpoint, create a `WebSocketGraphQlClient`, register a subscription, and publish events from a test fixture. Verify:

1. Handshake succeeds and the client receives connection acknowledgement.
2. Valid subscription operations receive the expected event payloads.
3. Variables and arguments are passed accurately.
4. Multiple operations on one connection are correlated properly by ID.
5. Cancelling the `Flux` on the client stops the corresponding server stream.
6. Unauthenticated connections are rejected.
7. Tenant A does not receive events belonging to Tenant B.
8. Resolver errors are translated into GraphQL errors.
9. Closing the connection releases stream resources.
10. Reconnect replay/resume behaves per contract if supported by the application.

In asynchronous tests, synchronize on when the subscription has actually registered before publishing events. Publishing before the server finishes subscribing causes race conditions and missed events.

## Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| WebSocket handshake returns 404 | `spring.graphql.websocket.path` is not configured | Enable the endpoint and verify the path |
| Cannot open WebSocket on MVC | Missing `spring-boot-starter-websocket` | Add the starter matching the Servlet stack |
| `@SubscriptionMapping` is not called | Wrong root type or accidentally used `@QueryMapping` | Check SDL and annotation |
| Client connects but receives no events | Publisher has not emitted or emitted before subscribe | Check the event source and registration lifecycle |
| Client and server do not understand messages | Both sides use different protocols | Use `graphql-transport-ws` on both client and server |
| Token present in handshake but server fails auth | Server reads token from `connection_init` payload per different config | Align where credentials are sent and read |
| Subscription keeps running after user leaves page | `Flux` not cancelled or source does not clean up | Dispose `Disposable`/`Flux` and verify cancellation |
| One client consumes excessive resources | Unbounded connections or subscriptions | Set limits on sessions, buffers, and timeouts |
| Client misses events on reconnect | WebSocket does not persist event history | Use a broker/event store and cursors if replay is needed |
| Duplicate events after retry | Client lacks idempotency or event IDs | Use event IDs/sequences and persist checkpoints |
| Only one instance receives events | Using an in-memory publisher in a multi-node deployment | Use a shared broker to fan out to all instances |

## Hands-on practice

Build a new-book notification feature:

1. Declare `Subscription.bookCreated` returning `BookCreatedEvent`.
2. Create `BookCreatedEvent` containing `eventId`, `occurredAt`, and `book`.
3. Create `BookEventPublisher` returning `Flux<BookCreatedEvent>`.
4. Publish events after the book-creation action completes according to the application's transaction policy.
5. Write a controller using `@SubscriptionMapping` to return the stream.
6. Enable the WebSocket endpoint via `spring.graphql.websocket.path`.
7. Create a client with `WebSocketGraphQlClient` and subscribe to the stream.
8. Use `Disposable.dispose()` to cancel the subscription when the use case ends.
9. Add authentication via the `connection_init` payload and verify permissions on the server.
10. Write tests for the event stream, WebSocket transport, cancellation, and auth errors.
11. Try dropping the connection and reconnecting; observe missed events and design a cursor if replay is needed.

Once finished, explain the difference between a WebSocket connection and a subscription operation, why `connection_init` is not a GraphQL query message, and why an in-memory `Flux` is insufficient for multi-instance systems needing reliable event delivery.

## Key takeaways

Subscriptions allow the server to emit multiple results over time. In Spring for GraphQL, declare root fields in SDL, write resolvers with `@SubscriptionMapping`, and return `Flux` or `Publisher`. Enable the WebSocket endpoint via `spring.graphql.websocket.path` and use the `graphql-transport-ws` protocol. Clients can use `WebSocketGraphQlClient` to share connections, subscribe to streams, and cancel via cancellation. Authenticate connections via `connection_init`, while still enforcing authorization and tenant scoping per operation/event. Long-lived connections require resource limits, heartbeats, and cleanup. WebSocket does not store history or guarantee event delivery on its own; if replay and reliable processing are needed, use event IDs/cursors alongside an appropriate broker or event store.

## References

- [Spring for GraphQL – Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL – Client, WebSocket and Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring Boot – Spring for GraphQL, WebSocket endpoint](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
