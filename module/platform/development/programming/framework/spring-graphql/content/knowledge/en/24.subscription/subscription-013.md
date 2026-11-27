# Subscriptions with RSocket in Spring for GraphQL

RSocket is an asynchronous message-passing protocol that supports multiple interaction models over a single connection. Spring for GraphQL can use RSocket as a transport for GraphQL: queries and mutations are sent using `request-response`, while subscriptions are sent using `request-stream`. This lets clients receive multiple GraphQL results over a stream without building custom polling mechanisms.

RSocket can run over TCP or WebSocket. When WebSocket is used as the transport layer, payloads are still RSocket frames governed by the RSocket protocol; this is not the GraphQL over WebSocket protocol `graphql-transport-ws`. This lesson focuses on how GraphQL subscriptions map onto RSocket streams, configuring servers and clients in Spring, lifecycle management, security, backpressure, and testing.

## 1. How does RSocket fit subscriptions?

RSocket defines interaction models for two parties to exchange data asynchronously:

| Interaction model | Description | How GraphQL typically uses it |
|---|---|---|
| Request-response | One request receives at most one response | Queries and mutations. |
| Request-stream | One request opens a stream that can emit multiple responses | Subscriptions. |
| Fire-and-forget | Sends a payload without expecting a response | Not a standard GraphQL operation execution model. |
| Request-channel | Both sides exchange streams of payloads | Not the default mapping for GraphQL operations. |

Example order management system:

- Query `order(id)` fetches the order state at call time.
- Mutation `updateOrderStatus(id, status)` updates the status and returns the processed result.
- Subscription `orderStatusChanged(orderId)` opens a request-stream and receives new status events.

With RSocket, queries/mutations and subscriptions can share the same GraphQL route while being distinguished by operation type and interaction model. The server handles queries/mutations as a single response, whereas subscriptions return a `Flux` of results.

## 2. Distinguishing RSocket over TCP from RSocket over WebSocket

RSocket is the protocol, while TCP and WebSocket are transport choices for carrying RSocket frames.

| Option | Example endpoint | Characteristics |
|---|---|---|
| RSocket over TCP | `localhost:9898` | Direct TCP connection, typically suited for service-to-service communication or native clients. |
| RSocket over WebSocket | `ws://localhost:8080/rsocket` | RSocket frames travel over WebSocket, useful when infrastructure or client environments require WebSocket. |

RSocket over WebSocket is not the same as GraphQL over WebSocket. In GraphQL over WebSocket, both sides exchange messages such as `connection_init`, `subscribe`, and `next` defined by the GraphQL protocol. In RSocket over WebSocket, both sides exchange RSocket frames; GraphQL requests are encapsulated inside RSocket payloads.

RSocket also differs from HTTP polling. A session can stay open long-term, multiplex multiple requests/streams over a single connection, and support flow control. Clients do not need to open a new HTTP connection for every event.

## 3. Dependencies for Spring Boot

A GraphQL application needs the GraphQL starter and the starter providing RSocket server/client infrastructure:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-rsocket'
}
```

`spring-boot-starter-rsocket` provides RSocket infrastructure built on Spring Messaging and Reactor Netty. Spring Boot can run a standalone RSocket server over TCP/WebSocket or integrate RSocket over WebSocket into a WebFlux application.

If you are only building a client calling an external RSocket server, you need the corresponding client dependencies in the application; you do not necessarily need to enable an RSocket server inside the client application itself.

## 4. Configuring the RSocket server and GraphQL route

Spring Boot needs two pieces of information:

1. Which transport and address the RSocket server listens on.
2. Which RSocket route the GraphQL handler is bound to.

### Standalone RSocket server over TCP

Example running the server on port `9898`, with GraphQL route `graphql`:

```yaml
spring:
  rsocket:
    server:
      port: 9898
  graphql:
    rsocket:
      mapping: graphql
```

### RSocket over WebSocket in WebFlux

For a WebFlux application running on Reactor Netty, you can attach RSocket to the web server:

```yaml
spring:
  rsocket:
    server:
      mapping-path: /rsocket
      transport: websocket
  graphql:
    rsocket:
      mapping: graphql
```

The client connects via WebSocket to `/rsocket` and sends requests to the `graphql` route. `mapping-path` is the WebSocket transport path; `spring.graphql.rsocket.mapping` is the GraphQL route inside RSocket. These two settings serve two different layers.

Attaching RSocket WebSocket to the web server is supported with WebFlux and Reactor Netty. If using standalone RSocket over TCP, configuring `spring.rsocket.server.port` is sufficient for the server transport.

## 5. Server-side GraphQL RSocket handling with `GraphQlRSocketHandler`

Spring for GraphQL provides `GraphQlRSocketHandler` to convert RSocket payloads into GraphQL requests and invoke GraphQL execution. When declaring routes manually with Spring Messaging, you can use a controller as a delegate:

```java
import java.util.Map;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import org.springframework.graphql.server.GraphQlRSocketHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
class GraphQlRSocketController {

    private final GraphQlRSocketHandler handler;

    GraphQlRSocketController(GraphQlRSocketHandler handler) {
        this.handler = handler;
    }

    @MessageMapping("graphql")
    Mono<Map<String, Object>> handle(Map<String, Object> payload) {
        return handler.handle(payload);
    }

    @MessageMapping("graphql")
    Flux<Map<String, Object>> handleSubscription(Map<String, Object> payload) {
        return handler.handleSubscription(payload);
    }
}
```

Both handlers share the `graphql` route:

- `handler.handle(payload)` processes queries/mutations and returns a single response map in a `Mono`.
- `handler.handleSubscription(payload)` processes subscriptions and returns multiple response maps in a `Flux`.

This is explicit wiring using `GraphQlRSocketHandler`. When relying on Spring Boot auto-configuration for the GraphQL RSocket route, configure the route via `spring.graphql.rsocket.mapping` per Boot documentation and avoid accidentally registering a duplicate route.

The payload holds the GraphQL request, typically with properties `query`, `operationName`, `variables`, and `extensions`. Clients do not need to assemble the payload map manually when using `RSocketGraphQlClient`; the client packages operations in the format Spring for GraphQL expects.

## 6. Subscription resolvers still use `@SubscriptionMapping`

RSocket is a transport; it does not change the schema or how annotated controllers are written. Subscription fields are still declared in SDL and mapped with `@SubscriptionMapping`.

SDL:

```graphql
type Query {
    order(id: ID!): Order
}

type Mutation {
    updateOrderStatus(id: ID!, status: OrderStatus!): Order!
}

type Subscription {
    orderStatusChanged(orderId: ID!): OrderEvent!
}

type Order {
    id: ID!
    status: OrderStatus!
}

type OrderEvent {
    orderId: ID!
    previousStatus: OrderStatus
    currentStatus: OrderStatus!
    occurredAt: String!
}

enum OrderStatus {
    CREATED
    CONFIRMED
    SHIPPING
    DELIVERED
    CANCELLED
}
```

Resolver:

```java
@Controller
class OrderSubscriptionController {

    private final OrderEventPublisher eventPublisher;

    OrderSubscriptionController(OrderEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @SubscriptionMapping
    Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
        return eventPublisher.eventsForOrder(orderId);
    }
}
```

GraphQL Java executes the subscription source and produces one execution result per event. `GraphQlRSocketHandler.handleSubscription` turns those results into an RSocket `request-stream` response.

## 7. Creating an event publisher for subscriptions

In a small single-instance example, you can use Reactor `Sinks.Many` as the event source:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
class OrderEventPublisher {

    private static final Logger log =
        LoggerFactory.getLogger(OrderEventPublisher.class);

    private final Sinks.Many<OrderEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    Flux<OrderEvent> eventsForOrder(String orderId) {
        return sink.asFlux()
            .filter(event -> event.orderId().equals(orderId));
    }

    void publish(OrderEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            log.warn("Cannot emit order event: {}", result);
        }
    }
}
```

This is an illustrative in-memory event bus. `multicast()` distributes events to active subscribers; late subscribers do not automatically receive previously emitted events. `tryEmitNext` can return a failure `EmitResult`, so the application must handle the result instead of assuming emission always succeeds.

In multi-instance systems, each process has its own sink. If a mutation runs on instance A while the client's subscription sits on instance B, events in A's memory do not automatically travel to B. Production systems typically need a shared broker or event platform such as Kafka, RabbitMQ, or Redis Streams/Pub/Sub, depending on replay, ordering, and delivery guarantee requirements.

## 8. Emitting events after a mutation modifies data

Mutations typically persist the new state first and then publish an event. Reactive service example:

Illustrative data types:

```java
public enum OrderStatus {
    CREATED, CONFIRMED, SHIPPING, DELIVERED, CANCELLED
}

public record Order(String id, OrderStatus status) {
    public Order withStatus(OrderStatus newStatus) {
        return new Order(id, newStatus);
    }
}

public record OrderEvent(
    String orderId,
    OrderStatus previousStatus,
    OrderStatus currentStatus,
    String occurredAt
) {}
```

The repository in this example can be a reactive repository:

```java
interface OrderRepository extends ReactiveCrudRepository<Order, String> {}
```

```java
@Service
class OrderService {

    private final OrderRepository repository;
    private final OrderEventPublisher eventPublisher;

    OrderService(OrderRepository repository, OrderEventPublisher eventPublisher) {
        this.repository = repository;
        this.eventPublisher = eventPublisher;
    }

    Mono<Order> updateStatus(String id, OrderStatus newStatus) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
            .flatMap(order -> {
                OrderStatus previous = order.status();
                Order updated = order.withStatus(newStatus);

                return repository.save(updated)
                    .doOnNext(saved -> eventPublisher.publish(
                        new OrderEvent(
                            saved.id(),
                            previous,
                            saved.status(),
                            Instant.now().toString()
                        )
                    ));
            });
    }
}
```

Mutation controller:

```java
@Controller
class OrderMutationController {

    private final OrderService orderService;

    OrderMutationController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MutationMapping
    Mono<Order> updateOrderStatus(
            @Argument("id") String id,
            @Argument("status") OrderStatus status) {
        return orderService.updateStatus(id, status);
    }
}
```

The `Order`, `OrderEvent`, `OrderStatus` types and repository must be defined according to your application domain. In systems with database transactions and brokers, avoid emitting events before the transaction commits if subscribers could observe an event for a change that later rolls back. The Outbox pattern or transaction-aware event publishing helps reduce the risk of inconsistent data and events.

## 9. Creating an RSocket GraphQL client

Spring for GraphQL provides `RSocketGraphQlClient`, an implementation of `GraphQlClient`. This client uses `RSocketRequester` to send GraphQL requests over RSocket.

### Connecting over TCP

```java
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
    .tcp("localhost", 9898)
    .route("graphql")
    .build();
```

### Connecting over WebSocket

```java
RSocketGraphQlClient client = RSocketGraphQlClient.builder()
    .webSocket(URI.create("ws://localhost:8080/rsocket"))
    .route("graphql")
    .build();
```

When using Spring Boot, you can inject an auto-configured `RSocketGraphQlClient.Builder<?>` and call `tcp(...)` or `webSocket(...)` plus `route(...)` to build the client.

The RSocket client is connection-oriented and multiplexed. A single client instance maintains a shared session across multiple requests. Reuse one `RSocketGraphQlClient` per server instead of creating a new instance for every operation whenever session sharing is desired.

## 10. Sending queries and mutations via request-response

`RSocketGraphQlClient`'s API uses the same `GraphQlClient` workflow as other transports.

Query:

```java
Mono<Order> order = client.document("""
        query {
            order(id: "order-01") {
                id
                status
            }
        }
        """)
    .retrieve("order")
    .toEntity(Order.class);
```

Mutation:

```java
Mono<Order> updated = client.document("""
        mutation {
            updateOrderStatus(id: "order-01", status: SHIPPING) {
                id
                status
            }
        }
        """)
    .retrieve("updateOrderStatus")
    .toEntity(Order.class);
```

These two operations are sent as RSocket `request-response`, because each produces a single GraphQL response. For mutations with side effects, still follow idempotency rules and handle timeouts/retries carefully: the client does not always know whether the server already executed the mutation if the connection drops before the response returns.

## 11. Subscribing via RSocket request-stream

To receive multiple events, use `retrieveSubscription(...)` instead of `retrieve(...)`:

```java
Flux<OrderEvent> events = client.document("""
        subscription WatchOrder($orderId: ID!) {
            orderStatusChanged(orderId: $orderId) {
                orderId
                previousStatus
                currentStatus
                occurredAt
            }
        }
        """)
    .variable("orderId", "order-01")
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class);
```

`retrieveSubscription` returns a `Flux<OrderEvent>`. Each event from the server is decoded into an object. At the RSocket layer, this operation uses the `request-stream` interaction model, allowing the server to emit multiple responses on the same request.

If you need to inspect the full GraphQL response, including errors and multiple fields, use `executeSubscription()` instead of the `retrieveSubscription()` shortcut:

```java
Flux<ClientGraphQlResponse> responses = client.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                currentStatus
            }
        }
        """)
    .executeSubscription();
```

With `executeSubscription`, the client reads fields and checks errors as needed. With `retrieveSubscription`, the client conveniently extracts a single response path.

## 12. Session lifecycle: `start()`, `stop()`, and reconnect

`RSocketGraphQlClient` has its own lifecycle:

- `start()` proactively opens the session before sending the first request.
- If `start()` has not been called, the session is established automatically when the client begins sending a request.
- `stop()` closes the session, cancels running requests, and rejects new requests through that client.
- If a session is lost, the next request or a call to `start()` can re-establish the session.

Example:

```java
Mono<Void> started = client.start();

// Once start completes, queries or subscriptions can be sent.

Mono<Void> stopped = client.stop();
```

Do not call `stop()` immediately after creating a subscription that needs to keep running, as that cancels active requests and closes the session. In applications, manage the client as a bean with a well-defined lifecycle and stop it during component/application shutdown.

Session reconnection does not mean an old subscription automatically resumes from the exact last received event. When the connection drops, the stream may terminate with a transport error. If business logic requires resuming from a specific position, the event source must support cursors, offsets, or resume tokens, and the client must open a new subscription from that position.

## 13. Cancellation and backpressure

RSocket `request-stream` supports flow control. The client requests items according to demand; the server emits data via RSocket and Reactive Streams request-n semantics. This regulates the event flow when a consumer processes slowly.

When the client cancels the subscription `Flux`, cancellation propagates to the RSocket stream. The server can cancel the GraphQL publisher and upstream event source if those components support cancellation.

Example of a client receiving at most 10 events:

```java
Flux<OrderEvent> firstTenEvents = client.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                orderId
                currentStatus
            }
        }
        """)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .take(10);
```

`take(10)` completes after 10 items and cancels upstream. For unbounded subscriptions, the application must manage buffers, emission rates, and active stream counts; avoid unbounded buffers if the event source can emit faster than clients for extended periods.

## 14. Handling errors and disconnections

Distinguish GraphQL errors from RSocket transport errors:

| Error type | Example | Client response |
|---|---|---|
| GraphQL request/execution error | Schema-invalid query, resolver throws exception | Inspect `errors`, `path`, and `extensions` in the GraphQL response. |
| Server subscription error | Publisher terminates with an error sent as an operation error | `Flux` can terminate with `SubscriptionErrorException`; inspect attached GraphQL errors. |
| Transport error | RSocket session closed, server unreachable | Handle `GraphQlTransportException`, reconnect, or recreate subscription if safe. |
| Timeout/cancellation | Client times out or proactively cancels | Determine whether the operation completed; never auto-retry mutations without idempotency. |

Example of handling stream errors:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(error -> log.warn("Order subscription ended", error));
```

Do not retry every error unconditionally. When reconnecting after a transport failure, the server may have already emitted events the client did not finish processing. Use event IDs or cursors if zero loss and deduplication are required. Retrying mutations is even more sensitive because it can trigger side effects a second time.

## 15. Securing RSocket GraphQL

RSocket has its own security support in Spring Security. You can use `@EnableRSocketSecurity` to enable payload authentication and authorization. Security infrastructure integrates with the RSocket server via `SecuritySocketAcceptorInterceptor`.

When using Spring Boot with the appropriate RSocket Security dependency, Boot can automatically register `SecuritySocketAcceptorInterceptor` on the RSocket server. If configuring the server outside Boot auto-configuration, attach this interceptor to the socket acceptor per Spring Security documentation.

Spring Security supports authentication at setup time, per request, or both. The choice depends on how sessions are used:

- Connection belongs to a single user, such as a mobile app: authenticate at setup time and bind the identity to the session.
- One connection is shared by multiple users, such as a downstream gateway/service: credentials must be sent and authenticated per request to avoid mixing identities across users.
- Systems with both a service identity and an end-user identity: authenticate the service at setup and pass verified user details per request.

The RSocket `graphql` route is shared across many queries, mutations, and subscriptions. Therefore, route-level authorization is only the first layer of defense. Field- and resource-level access rights must still be checked inside services using method security or business logic. Never rely on client-sent GraphQL arguments as proof of identity.

For long-lived subscriptions, define what happens when tokens expire, permissions are revoked, or tenant memberships change. Depending on security requirements, you can close the stream, require client re-authentication, or check permissions when emitting events.

## 16. Interception and GraphQL context over RSocket

`WebGraphQlInterceptor` is for HTTP/WebSocket. For RSocket, Spring for GraphQL provides `RSocketQlInterceptor` to intercept requests before and after GraphQL Java executes.

`RSocketQlInterceptor` can be used to:

- Read metadata from the RSocket request when metadata is configured and accessible through the transport integration.
- Enrich `ExecutionInput` or `GraphQLContext`.
- Observe or transform `ExecutionResult`.
- Record metrics or correlation metadata for the request.

Do not use `WebGraphQlInterceptor` expecting to intercept RSocket routes. Choose the interceptor matching the transport. For authentication/authorization, prefer Spring Security RSocket integration; GraphQL interceptors do not replace credential verification.

## 17. Testing subscriptions over RSocket

Spring for GraphQL provides `RSocketGraphQlTester` to send GraphQL requests over RSocket. Test dependency:

```groovy
testImplementation 'org.springframework.graphql:spring-graphql-test'
```

Example creating a tester using the RSocket WebSocket transport:

```java
URI uri = URI.create("ws://localhost:8080/rsocket");
WebsocketClientTransport transport = WebsocketClientTransport.create(uri);

RSocketGraphQlTester tester = RSocketGraphQlTester.builder()
    .clientTransport(transport)
    .build();
```

`RSocketGraphQlTester` works well for testing request-response over RSocket. For end-to-end subscription stream tests, you can use `RSocketGraphQlClient` and `StepVerifier`:

```java
Flux<OrderEvent> events = client.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                currentStatus
            }
        }
        """)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class);

StepVerifier.create(events)
    .expectNextMatches(event -> event.currentStatus() == OrderStatus.CONFIRMED)
    .thenCancel()
    .verify();
```

This is an illustrative example; the server, RSocket route, client session, and event publisher must be started in the test context. Publish events from the test fixture only after the subscription has been registered to avoid race conditions. You can use a test-controlled `Sinks.Many` to control exactly which events are emitted.

Spring for GraphQL's testing documentation includes `RSocketGraphQlTester`, while current subscription testing guides primarily describe `WebSocketGraphQlTester` and server-side testers. Therefore, when verifying live RSocket streams, testing with `RSocketGraphQlClient` alongside `StepVerifier` is clear and direct; do not assume every tester API offers identical subscription support.

## 18. When to choose RSocket over WebSocket or SSE?

| Criterion | RSocket | GraphQL WebSocket | GraphQL SSE |
|---|---|---|---|
| Transport | TCP or WebSocket | WebSocket | HTTP streaming |
| Query/mutation | Request-response | Possible as single response | Not primary use case; SSE handler is for subscriptions. |
| Subscription | Request-stream | GraphQL WebSocket protocol | Server-Sent Events stream |
| Multiplexing | Multiple interactions per session | Multiple operations per connection | SSE handler uses distinct connections mode. |
| Flow control | RSocket request-n and Reactive Streams | Depends on WebSocket transport and implementation | Depends on HTTP streaming/server. |
| Client ecosystem | `RSocketRequester`, `RSocketGraphQlClient` | GraphQL WebSocket clients | HTTP/EventSource clients. |

RSocket fits well when applications need message-based communication, request-stream, multiplexing, and flow control between services or RSocket-capable clients. GraphQL over WebSocket is usually easier to integrate with browsers and the mainstream GraphQL subscription ecosystem. SSE can be simpler for clients that only need to receive events over HTTP without bidirectional messaging.

Do not choose RSocket solely for subscriptions. Evaluate client environments, proxies/firewalls, connection operations, security, observability, and infrastructure support.

## 19. Common mistakes

**Confusing RSocket WebSocket with GraphQL over WebSocket.** RSocket sends RSocket frames over WebSocket; it does not exchange `connection_init`/`subscribe` messages from `graphql-transport-ws`.

**Route mismatch between server and client.** `spring.graphql.rsocket.mapping` must match the route the client calls, such as `graphql`.

**Configuring only the GraphQL route without enabling the RSocket server.** You need the starter and `spring.rsocket.server.*` settings matching TCP or WebSocket.

**Using `request-response` for subscriptions.** Subscriptions require `request-stream`; the server handler must return a `Flux` via `handleSubscription`.

**Creating a new `RSocketGraphQlClient` for every operation.** Each client instance creates its own session. Reuse one client per server when session sharing is desired.

**Calling `block()` or `subscribe()` in a resolver.** Return `Flux` so GraphQL and RSocket manage the publisher, cancellation, and backpressure.

**Assuming session reconnect resumes events automatically.** On disconnect, subscriptions can terminate. Resuming requires cursors/offsets and re-subscription logic.

**Skipping per-request authentication on shared connections.** Setup-time authentication alone is insufficient if multiple users share one session; end-user credentials must be bound to each request.

**Using an in-memory sink across multiple instances.** Local sinks do not propagate events across processes. Use a shared broker when cross-instance delivery or replay is needed.

**Failing to control backpressure and stream counts.** Long-lived subscriptions can exhaust memory, CPU, and broker resources. Set limits and cancellation/overflow policies.

## Conclusion

Spring for GraphQL maps queries and mutations to RSocket `request-response`, and subscriptions to `request-stream`. On the server, `GraphQlRSocketHandler` executes GraphQL payloads and returns a `Mono` or `Flux`; on the client, `RSocketGraphQlClient` uses the same GraphQL API while supporting subscriptions via `retrieveSubscription`. Configure the RSocket server, GraphQL route, and TCP/WebSocket transport properly; reuse client sessions, handle cancellation/backpressure, secure at setup or per request, and design resumption when required. Use `RSocketGraphQlClient` with `StepVerifier` to test live streams.

## References

- [Spring for GraphQL — Server Transports: RSocket](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring Boot — Spring for GraphQL: RSocket](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Spring for GraphQL — Client: RSocket and Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Security — RSocket Security](https://docs.spring.io/spring-security/reference/reactive/integrations/rsocket.html)
