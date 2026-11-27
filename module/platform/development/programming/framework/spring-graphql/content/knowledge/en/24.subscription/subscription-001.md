# Subscription operation in Spring for GraphQL

GraphQL subscriptions allow a client to subscribe to new results when an event occurs, instead of sending repeated queries to check whether data has changed. In Spring for GraphQL, a subscription field is typically implemented with `@SubscriptionMapping` and returns a reactive publisher such as `Flux<T>`. Each item emitted by the publisher becomes a separate GraphQL result according to the selection set the client subscribed to.

Subscriptions are well suited for live notifications, order status updates, dashboard updates, processing progress, or business events. To design them properly, you need to understand the subscription root in SDL, how Spring connects resolvers to publishers, streaming transports, subscription lifecycle, error handling, security, and testing.

## 1. Distinguishing Query, Mutation, and Subscription

The three operation roots serve different purposes:

| Operation | Purpose | Behavior |
|---|---|---|
| `Query` | Read current data | Client sends a request and receives one response. |
| `Mutation` | Modify data | Client sends a request, the server performs the action and returns a result. |
| `Subscription` | Receive data changes over time | Client opens a long-lived operation and receives multiple responses as the publisher emits events. |

Example in an order management system:

- `order(id)` returns the current state of an order.
- `cancelOrder(id)` requests cancellation of an order.
- `orderStatusChanged(orderId)` sends new status changes to clients that are watching.

Subscriptions do not replace queries. Clients typically use a query to load the initial state, then use a subscription to receive subsequent changes.

## 2. Declaring the Subscription root in SDL

A GraphQL schema must declare the `Subscription` root type and the fields that clients can subscribe to:

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

`Subscription` is the root type dedicated to subscription fields. In a subscription operation, the root selection set must select exactly one subscription field. Child fields of the event can still be selected normally.

Example operation:

```graphql
subscription WatchOrder($orderId: ID!) {
    orderStatusChanged(orderId: $orderId) {
        orderId
        previousStatus
        currentStatus
        occurredAt
    }
}
```

The client sends this operation once. The server keeps the subscription active and sends a new result whenever a corresponding event occurs. The return type `OrderEvent!` describes the payload of each emission; it does not mean the entire subscription returns only one object.

## 3. Mapping fields with `@SubscriptionMapping`

Spring for GraphQL provides `@SubscriptionMapping` to bind a controller method to a field on the `Subscription` root. This annotation is a shorthand for `@SchemaMapping(typeName = "Subscription")`.

Example resolver:

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

By default, Spring uses the method name `orderStatusChanged` as the GraphQL field name. If the Java method name differs from the field name in SDL, you can specify it explicitly:

```java
@SubscriptionMapping(name = "orderStatusChanged")
Flux<OrderEvent> watchOrder(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId);
}
```

The field name must exist in the SDL. `@SubscriptionMapping` does not automatically add fields to the schema. Arguments are bound using `@Argument` just like in queries and mutations.

## 4. Why do subscriptions usually return `Flux<T>`?

Project Reactor's `Flux<T>` represents an asynchronous sequence that can emit zero, one, or many items and then complete or signal an error. This model fits subscriptions naturally:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId);
}
```

Each `OrderEvent` item emitted by the `Flux` is processed by GraphQL according to the subscription's selection set. For example, if the client selects `currentStatus` and `occurredAt`, each event response contains only those fields.

You should not call `subscribe()` inside the resolver. Spring for GraphQL manages subscribing to the publisher and turning emitted items into GraphQL results. You also should not call `block()` because that blocks the thread and breaks the reactive flow.

A publisher can emit the following signals:

| Signal | Meaning for a subscription |
|---|---|
| `onNext(value)` | A new event occurred; GraphQL produces a response for that event. |
| `onComplete()` | The event stream ended normally; the subscription completes. |
| `onError(error)` | The stream encountered an error; the subscription terminates with an error according to GraphQL execution semantics. |
| Cancellation | The client or server cancels the subscription; upstream receives a cancellation signal. |

## 5. Creating an event source for subscriptions

A resolver should only forward a publisher from a component responsible for supplying events. The event source can be a message broker, a reactive database change stream, an event bus, or an in-application publisher.

Simple example using Reactor `Sinks.Many` to demonstrate an in-process event bus:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
class OrderEventPublisher {

    private static final Logger log = LoggerFactory.getLogger(OrderEventPublisher.class);

    private final Sinks.Many<OrderEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    Flux<OrderEvent> eventsForOrder(String orderId) {
        return sink.asFlux()
            .filter(event -> event.orderId().equals(orderId));
    }

    void publish(OrderEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            // Log or forward to an appropriate event handling mechanism.
            log.warn("Cannot emit order event: {}", result);
        }
    }
}
```

This is an in-memory event source intended for learning and experimentation. With a multicast sink, events are delivered to active subscribers; if there are no subscribers or the sink cannot accept events, `tryEmitNext` can return a failure result. The application should decide explicitly how to handle it and not ignore `EmitResult`.

In a multi-instance production deployment, an in-memory sink only sees events emitted within the same instance. If a client connects to instance A while an event is created on instance B, the client may miss it. Real-world systems usually use a shared broker or event platform such as Kafka, RabbitMQ, Redis Pub/Sub/Streams, or an appropriate messaging platform.

## 6. Connecting mutations to subscription events

A common flow is for a mutation to update state, the service to persist the data, and then publish an event so subscriptions receive it:

Data types used in the example:

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

```java
@Service
class OrderService {

    private final OrderRepository orderRepository;
    private final OrderEventPublisher eventPublisher;

    OrderService(
            OrderRepository orderRepository,
            OrderEventPublisher eventPublisher) {
        this.orderRepository = orderRepository;
        this.eventPublisher = eventPublisher;
    }

    Mono<Order> updateStatus(String id, OrderStatus newStatus) {
        return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
            .flatMap(order -> {
                OrderStatus previous = order.status();
                Order updated = order.withStatus(newStatus);

                return orderRepository.save(updated)
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

In this example, the event is published after the repository saves successfully. In systems using database transactions and a message broker, you need to consider transaction boundaries: if an event is published before the transaction commits, subscribers might observe an event for a change that is later rolled back. The Outbox pattern or transaction-aware event publishing helps keep data and events reliably synchronized.

## 7. Subscription transport: WebSocket and GraphQL protocol

Subscriptions require a transport that supports delivering multiple results over time. Standard HTTP request/response returns a single response and closes, so it is not suitable for maintaining a long-lived subscription stream.

Spring for GraphQL supports the WebSocket transport for subscriptions. The WebSocket endpoint can be configured in Spring Boot, for example:

```yaml
spring:
  graphql:
    websocket:
      path: /graphql
```

The client and server communicate using the GraphQL over WebSocket protocol `graphql-transport-ws`. The client sends this subprotocol in the WebSocket handshake; both server and client must support the same protocol. Key messages include:

| Message | Direction | Purpose |
|---|---|---|
| `connection_init` | Client → Server | Initializes the connection, optionally carrying an authentication payload. |
| `connection_ack` | Server → Client | Acknowledges that the connection is ready. |
| `subscribe` | Client → Server | Starts a GraphQL operation, typically a subscription. |
| `next` | Server → Client | Sends an execution result/event. |
| `error` | Server → Client | Reports an operation error according to the protocol. |
| `complete` | Bidirectional | Terminates an operation or confirms that the stream has completed. |
| `ping` / `pong` | Bidirectional | Checks connection health/liveness. |

Each subscription operation has an ID so the client and server can correlate events with the corresponding operation. The client can send `complete` to cancel a single subscription without closing the entire WebSocket connection.

A WebSocket connection can carry multiple concurrent operations. Therefore, you need to manage limits on the number of subscriptions per connection and the resources consumed by each subscription.

## 8. Lifecycle: starting, completing, and cancelling subscriptions

Subscriptions usually live much longer than a typical HTTP request. The full lifecycle must be handled properly:

1. The client opens a WebSocket connection.
2. The client sends `connection_init`; the server authenticates or prepares context if configured.
3. The server sends `connection_ack`.
4. The client sends `subscribe` with the GraphQL subscription document.
5. Spring invokes `@SubscriptionMapping` and subscribes to the returned publisher.
6. Each event produces a `next` response.
7. If the publisher completes or errors, the operation ends.
8. The client sends `complete` to cancel; the server cancels the upstream subscription and releases resources.

The publisher must react properly to cancellation. For example, when a client stops watching, the application should cancel the consumer or broker subscription if no other subscriber needs it. Reactor operators such as `doOnCancel` and `doFinally` can assist with cleanup, though resource release must be designed around the actual lifecycle of the event source.

Never keep an infinite subscription alive after the client disconnects. If upstream does not support cancellation or fails to release resources, the system can accumulate unused consumers, cursors, buffers, or listeners.

## 9. Passing arguments and filtering events

A subscription field can accept arguments to narrow the set of events the client wants to watch:

```graphql
type Subscription {
    orderStatusChanged(orderId: ID!): OrderEvent!
}
```

Resolver:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId);
}
```

Arguments help filter events by order ID. Additional filters such as event type or status can be added, while bounding subscription scope so a single client cannot subscribe to an overly broad stream unnecessarily.

Do not rely solely on client-supplied arguments to decide whether a user is authorized to watch a resource. The service must verify read access to the order before creating the publisher, and may need to re-check authorization when events are emitted if permissions can change while the subscription is active.

## 10. Authentication and authorization for subscriptions

A subscription can remain open for minutes or hours. Authenticating once when opening the connection does not mean the user remains authorized to receive every event indefinitely.

With WebSocket, Spring for GraphQL can integrate `AuthenticationWebSocketInterceptor` to extract credentials from `connection_init`, authenticate using an `AuthenticationManager` or `ReactiveAuthenticationManager`, and propagate the `SecurityContext` to subsequent requests.

A resolver can receive the principal:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(
        @Argument("orderId") String orderId,
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    return orderService.eventsVisibleTo(subject, orderId);
}
```

`eventsVisibleTo` must verify that the user has permission to read the order and only emit events within the allowed scope. Never use a client-provided `userId` as a substitute for an authenticated principal.

For long-lived subscriptions, you need a policy for expired tokens, revoked permissions, or users removed from a tenant. You can close the stream, require the client to reconnect, or apply periodic/per-event authorization checks. The choice depends on your system's security requirements and latency constraints.

## 11. Error handling in subscription streams

Distinguish between errors before the stream starts and errors that occur while the stream is running:

- Parse errors, validation errors, argument coercion errors, or authentication failures at subscription time prevent the operation from starting.
- Exceptions during publisher creation or initial authorization checks can be mapped to GraphQL errors.
- An `onError` emitted after the stream has been active terminates the publisher with an error; the subscription does not resume automatically unless the pipeline includes a retry/fallback policy.

Example of translating an infrastructure error into a meaningful exception:

```java
@SubscriptionMapping
Flux<OrderEvent> orderStatusChanged(@Argument("orderId") String orderId) {
    return eventPublisher.eventsForOrder(orderId)
        .onErrorMap(
            BrokerUnavailableException.class,
            ex -> new OrderEventStreamException("Order event stream unavailable", ex)
        );
}
```

Exception handlers can map initialization errors or errors observed by GraphQL into appropriate GraphQL errors. For errors occurring after the stream has already emitted some events, understand the behavior of the transport and GraphQL execution: the error terminates the publisher and the client receives an operation error notification, while previously emitted events have already been delivered.

Only retry when the event source can reconnect safely and supports a resume/offset mechanism to avoid losing or duplicating events. Blind retries can create data gaps or send duplicate notifications. Avoid turning every error into `Flux.empty()` because the client would assume the stream completed normally.

## 12. Backpressure and resource limits

`Flux` supports Reactive Streams backpressure: a subscriber can regulate the number of items it requests. However, an external event source can still emit faster than the client can consume data. In such cases, you need an explicit buffering or limiting policy.

Common options:

| Policy | When suitable | Risks to consider |
|---|---|---|
| Bounded buffer | Need to retain events during short traffic spikes | Must define how overflow is handled when full. |
| Drop latest events | Only the most recent state is needed or data can be re-fetched | Client may miss events. |
| Drop oldest events | Prioritize the newest events | Unsent history is lost. |
| Latest value | Dashboards that only need the latest state | Not suitable for audit trails or events requiring completeness. |
| Disconnect slow client | Cannot accept backlog or growing memory usage | Client needs to reconnect and resume. |

Do not use an unbounded buffer for subscriptions that can remain open for a long time. A slow client can cause memory usage to grow continuously. Bound the number of subscriptions, emission rate, event size, and number of buffered events.

## 13. Testing subscriptions with `GraphQlTester`

For subscriptions, use `executeSubscription()` to obtain a `Flux` of responses instead of calling `execute()` as in regular queries. You can combine it with `StepVerifier` to assert events in order:

```java
Flux<String> statuses = graphQlTester.document("""
        subscription {
            orderStatusChanged(orderId: "order-01") {
                currentStatus
            }
        }
        """)
    .executeSubscription()
    .toFlux("orderStatusChanged.currentStatus", String.class);

StepVerifier.create(statuses)
    .expectNext("CONFIRMED", "SHIPPING")
    .thenCancel()
    .verify();
```

This is an illustrative example; `graphQlTester` needs to be configured with a subscription handler and an event source controllable in tests. `executeSubscription()` returns the response stream; `toFlux(path, type)` extracts a value from each event response.

Things to verify:

- The subscription returns events in the right order and matching the selection set.
- Filtering arguments deliver only matching events.
- Events for unauthorized resources are not sent to the user.
- When the publisher completes, the subscription terminates.
- When the publisher emits an error, the client receives an error according to the contract.
- Client cancellation triggers upstream cleanup.
- A slow subscriber does not cause unbounded buffer growth.

To test the real transport, use `WebSocketGraphQlTester` connected to a running WebSocket endpoint. These tests can verify `connection_init`, authentication, `subscribe`, multiple `next` messages, and cancellation. Tests at the `GraphQlTester` layer verify resolvers and execution; WebSocket tests verify both the protocol and transport.

## 14. Common mistakes

**Using `@QueryMapping` for the subscription root.** Fields on `Subscription` must be mapped with `@SubscriptionMapping` or `@SchemaMapping(typeName = "Subscription")`.

**Returning a single object instead of a publisher.** A subscription requires a source that emits multiple results over time. Use `Flux<T>` or an appropriate `Publisher<T>`.

**Calling `subscribe()` or `block()` inside a resolver.** Spring must manage the publisher. Return the `Flux` directly so the framework controls its lifecycle.

**Not configuring a streaming transport.** Standard HTTP request/response does not maintain a subscription stream. Configure WebSocket or another streaming-capable transport.

**Assuming every client receives all events from an in-memory sink.** A local multicast sink does not replace a shared message broker across multiple instances and does not provide event persistence on its own.

**Not handling cancellation.** If a client disconnects while the consumer keeps running, resources will leak. Ensure cancellation propagates to the event source.

**Not bounding buffers and subscription counts.** Slow clients or excessive subscriptions can exhaust system resources. Enforce limits and an overflow policy.

**Authenticating only at connection open and ignoring permission changes.** Long-lived subscriptions need policies for token expiration, permission revocation, and tenant membership changes.

**Retrying the stream without a resume strategy.** This can lose or duplicate events. Use offsets/cursors or a replay mechanism when continuity is required.

## Conclusion

Subscription operations allow clients to receive multiple GraphQL results over time. In Spring for GraphQL, declare fields on the `Subscription` root, map them with `@SubscriptionMapping`, and return `Flux<T>` or `Publisher<T>`. The event source can be a Reactor sink for simple examples or a message broker for multi-instance systems. You should configure a transport such as WebSocket, manage lifecycle and cancellation, handle errors within the stream, control backpressure, and enforce authentication/authorization based on the principal. Use `GraphQlTester` with `StepVerifier`, and then run real WebSocket tests to verify the entire operation end-to-end.

## References

- [Spring for GraphQL — Annotated Controllers: Subscription Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [GraphQL Specification — Subscription](https://spec.graphql.org/October2021/#sec-Subscription)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
