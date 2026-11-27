# Flux for subscriptions

GraphQL Subscriptions allow clients to receive data whenever a new event occurs, instead of sending repeated queries to poll for current state. For example, a client can monitor a product's inventory, order processing status, or live updates of an auction session.

In Spring for GraphQL, a method annotated with **@SubscriptionMapping** typically returns Project Reactor's **Flux<T>**. Each item emitted from the Flux becomes a result execution for the subscription field. The client receives multiple GraphQL response payloads for as long as the subscription remains active.

Flux represents a data stream that can emit multiple items over time, complete normally, or terminate with an error. Therefore, when building a subscription, you need to understand the return type, publisher lifecycle, transport, cancellation, backpressure, and how to handle errors after the stream has started.

## How does a Subscription differ from a Query?

A Query fetches the data state at execution time. A Subscription registers to receive future changes:

| Aspect | Query | Subscription |
| --- | --- | --- |
| Purpose | Read current data | Receive events over time |
| Typical result type | Object or collection | Publisher such as Flux |
| Lifecycle | Completes after one response | Can stay open until complete, error, or cancel |
| Transport | Typically HTTP | Typically WebSocket or RSocket |
| Number of responses | One GraphQL response | Multiple response payloads in one operation |

Example Query returning current stock:

~~~graphql
type Query {
  stock(productId: ID!): Stock
}
~~~

Subscription watching stock changes:

~~~graphql
type Subscription {
  stockChanged(productId: ID!): StockEvent!
}
~~~

Query returns the current snapshot. Subscription emits StockEvents when changes happen after the client subscribes.

## Declaring a Subscription field in SDL

GraphQL defines a root type named Subscription:

~~~graphql
type Subscription {
  stockChanged(productId: ID!): StockEvent!
}

type StockEvent {
  eventId: ID!
  productId: ID!
  availableQuantity: Int!
  occurredAt: String!
}
~~~

The corresponding Java DTO can use String for occurredAt because the schema declares String:

~~~java
public record StockEvent(
        String eventId,
        String productId,
        int availableQuantity,
        String occurredAt) {
}
~~~

The productId argument identifies the product the client wants to watch. The return type StockEvent! describes one event per payload. The ! requires each emission to produce a non-null StockEvent.

Per the GraphQL specification, a Subscription operation has exactly one root field. The client can select multiple child fields within that root field's payload:

~~~graphql
subscription WatchStock($productId: ID!) {
  stockChanged(productId: $productId) {
    eventId
    productId
    availableQuantity
    occurredAt
  }
}
~~~

Variables sent with the operation:

~~~json
{
  "productId": "product-42"
}
~~~

Each emitted event produces a response shaped like:

~~~json
{
  "data": {
    "stockChanged": {
      "eventId": "evt-1001",
      "productId": "product-42",
      "availableQuantity": 18,
      "occurredAt": "2026-11-20T10:15:30Z"
    }
  }
}
~~~

If the Flux emits three events, the client receives three separate payloads. The GraphQL runtime resolves the selection set for each event, so the client can select nested fields just like when querying objects from a Query.

## Mapping a Subscription with @SubscriptionMapping

Spring for GraphQL provides the @SubscriptionMapping annotation to map a field on the Subscription root to a controller method:

~~~java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class StockSubscriptionController {

    private final InventoryEventService eventService;

    public StockSubscriptionController(InventoryEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<StockEvent> stockChanged(@Argument String productId) {
        return eventService.eventsFor(productId);
    }
}
~~~

The method name stockChanged is used as the default field name. If the Java method name differs from the field name in SDL, you can declare it explicitly:

~~~java
@SubscriptionMapping("stockChanged")
public Flux<StockEvent> watchProduct(@Argument String productId) {
    return eventService.eventsFor(productId);
}
~~~

The method accepts arguments just like other annotated controllers. Spring binds productId from the GraphQL operation and invokes the resolver to obtain the publisher. The GraphQL runtime subscribes to the publisher, and its items are resolved into payloads.

Do not return a List if the goal is to emit data over time. A List is an already-materialized collection; Flux represents a publisher that can emit multiple items asynchronously.

## Building a Flux from a service

The controller should focus on mapping the GraphQL field and passing arguments down to a service. The service is responsible for obtaining events from the data source:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class InventoryEventService {

    private final InventoryEventSource eventSource;

    public InventoryEventService(InventoryEventSource eventSource) {
        this.eventSource = eventSource;
    }

    public Flux<StockEvent> eventsFor(String productId) {
        return Flux.defer(() -> eventSource.eventsFor(productId));
    }
}
~~~

InventoryEventSource is an abstraction representing the event source, such as a message broker, internal event bus, or managed publisher. Flux.defer delays calling eventsFor until a subscriber subscribes. It does not by itself turn a hot source into a cold one; whether it is cold or hot still depends on the implementation returned by eventSource.

Example interface:

~~~java
public interface InventoryEventSource {
    Flux<StockEvent> eventsFor(String productId);
}
~~~

In real-world systems, the event source should filter by topic, partition, routing key, or consumer filter to avoid reading all events and only filtering inside the application. If the source does not support filtering, the service can use filter as an additional safeguard. The exact implementation depends on the broker and the system's event distribution model.

## Cold and hot Flux

Reactor has two common categories of publishers:

- **Cold publisher:** starts generating or reading data when a subscriber subscribes. Each subscriber typically gets its own execution.
- **Hot publisher:** emits data independently of subscribers. New subscribers may miss events emitted before they subscribed.

Cold publisher example:

~~~java
Flux<StockEvent> events = Flux.defer(() ->
        eventRepository.streamEventsFor("product-42"));
~~~

If eventRepository creates a new query or subscription each time it is called, every subscriber triggers a fresh data source subscription. Simply wrapping an existing hot Flux in Flux.defer does not make it cold.

Hot publisher example:

~~~java
import reactor.core.publisher.Sinks;

Sinks.Many<StockEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<StockEvent> events = sink.asFlux();
~~~

Another component emits an event:

~~~java
import java.time.Instant;

StockEvent stockEvent = new StockEvent(
        "evt-1001", "product-42", 18, Instant.now().toString());

Sinks.EmitResult result = sink.tryEmitNext(stockEvent);
if (result.isFailure()) {
    // Log event emission failure and apply the appropriate policy
}
~~~

Sinks is a useful way to create a hot publisher for demos or in-memory event buses. For multi-instance applications, critical events, or cases requiring replay, use a broker or event store capable of appropriate persistence and distribution. Never assume an in-memory Sinks instance can replace a durable message broker.

If using a hot publisher, decide clearly:

- Do new subscribers need past events?
- Can missed events be fetched via a Query or cursor?
- Is replaying a certain number of recent events required?
- What happens when there are no subscribers or when a subscriber processes slowly?
- Do multiple server instances need to observe the same events?

Flux does not automatically guarantee history storage. To support resuming after a disconnect, the schema usually needs a cursor or event ID, and the service needs a data source capable of reading again from that position.

## Each subscription has its own lifecycle

When a client sends a subscription operation, Spring for GraphQL invokes the resolver and obtains the publisher. Once the publisher is subscribed to, the event stream starts. The stream can terminate in three ways:

1. **Complete:** the data source finishes normally.
2. **Error:** the data source raises an error and the stream terminates.
3. **Cancel:** the client unsubscribes, the connection closes, or the subscription is cancelled.

Do not write an infinite loop in the controller and manage sockets manually. Return a Flux and let the GraphQL transport manage subscribing, sending payloads, and cancelling the publisher when the operation ends.

You can observe the lifecycle with doFinally:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

private static final Logger log =
        LoggerFactory.getLogger(StockSubscriptionController.class);

@SubscriptionMapping
public Flux<StockEvent> stockChanged(@Argument String productId) {
    return eventService.eventsFor(productId)
            .doFinally(signalType ->
                    log.info("Subscription finished: {}", signalType));
}
~~~

doFinally is suitable for metrics or lifecycle logging. If you need to release asynchronous resources such as consumer registrations, cursors, or connections, use a proper resource management mechanism such as Flux.usingWhen to clean up on complete, error, or cancel.

Cancellation must propagate upstream to the event source. If a client has unsubscribed while a consumer or database cursor keeps running, the server can waste resources and retain registrations with no recipients.

## WebSocket transport for Subscriptions

GraphQL over HTTP typically handles Queries and Mutations. Subscriptions need a transport that can keep a connection open and send multiple payloads, most commonly WebSocket. Spring for GraphQL supports the WebSocket transport; Spring Boot can configure the endpoint using the spring.graphql.websocket.path property.

Common dependencies in a Spring Boot application:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-websocket")
}
~~~

Endpoint configuration:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

After enabling the WebSocket transport, the client connects to the WebSocket endpoint and sends GraphQL subscription operations using a WebSocket subprotocol supported by Spring GraphQL. Configure reverse proxies, load balancers, and timeouts appropriately to sustain long-lived connections.

The HTTP endpoint and WebSocket endpoint may share a path depending on application configuration, but the client must use the proper scheme and protocol: HTTP(S) for query/mutation, WS(S) for WebSocket subscription.

## Flux emits values; GraphQL builds each payload

An important point: Flux emits domain objects or DTOs; it does not emit prebuilt GraphQL JSON responses. For each item, the GraphQL runtime resolves the root subscription field and the client's selection set.

Example Flux:

~~~java
import java.time.Instant;

Flux<StockEvent> events = Flux.just(
        new StockEvent("evt-1", "product-42", 20, Instant.now().toString()),
        new StockEvent("evt-2", "product-42", 18, Instant.now().toString()),
        new StockEvent("evt-3", "product-42", 15, Instant.now().toString()));
~~~

If the client selects:

~~~graphql
subscription {
  stockChanged(productId: "product-42") {
    eventId
    availableQuantity
  }
}
~~~

Each StockEvent is resolved into a response payload. The client does not need to resend the operation for each event; the open subscription receives consecutive payloads.

If StockEvent has nested fields resolved via @SchemaMapping, child field resolvers still execute for each event. If those child fields access a database, watch query costs and consider appropriate projections, fetch strategies, or DataLoaders.

## Handling errors before and after the stream starts

Two error phases must be distinguished:

**Errors when setting up the subscription**

For example, productId is invalid, the user is not authorized to subscribe, or the product does not exist. The resolver can validate before returning the Flux and raise an exception. GraphQL treats this as an error while executing the subscription operation; the stream has not started emitting events yet.

**Errors after the stream has started**

For example, the message broker disconnects or the event source emits an error. The publisher signals onError and the stream terminates. The client receives an error for the subscription and must decide whether to reconnect or display a data-loss state.

You can translate data source errors into semantic exceptions:

~~~java
public Flux<StockEvent> eventsFor(String productId) {
    return eventSource.eventsFor(productId)
            .onErrorMap(
                    BrokerUnavailableException.class,
                    error -> new SubscriptionUnavailableException(
                            "Event source is currently unavailable", error));
}
~~~

Do not mechanically use onErrorResume(error -> Flux.empty()). That turns a system error into a normal completion, leading the client to think no further events will occur. If a fallback is needed, define clear semantics and communicate the status to the client.

Retry is only appropriate for transient errors and sources that can be safely re-subscribed. Unbounded retries can cause reconnect loops, increase load, or replay duplicate events. When retrying, consider event IDs, cursors, idempotency, and backoff policies.

## Backpressure and event emission rate

Reactor Flux supports backpressure between reactive components: a subscriber can regulate the number of items requested from upstream. However, external event sources such as brokers or callback APIs may have their own buffering mechanisms and do not necessarily honor Reactor demand.

If the producer emits faster than payloads can be processed or sent, queues can grow and consume excessive memory. Choose an appropriate policy:

| Strategy | Behavior | Suitable for |
| --- | --- | --- |
| Bounded buffer | Holds events up to a limit; handles overflow per policy | Events that must be processed within resource limits |
| Drop | Discards events when downstream cannot keep up | Metrics or intermediate updates that can be skipped |
| Latest | Keeps the latest value, discarding unprocessed older ones | Dashboards needing only the current state |
| Sample/throttle | Reduces emission frequency | High-frequency charts or telemetry |
| Fail | Terminates when exceeding threshold | When you need to explicitly signal overload |

Example of bounding a buffer:

~~~java
public Flux<StockEvent> eventsFor(String productId) {
    return eventSource.eventsFor(productId)
            .onBackpressureBuffer(500);
}
~~~

The example above sets a 500-item limit on the operator-managed buffer; when exceeded, the stream can signal an overflow error. This is not a universal solution. For business data that must not be lost, use a broker with retention, consumer offsets, and replay capability rather than relying solely on an in-memory buffer.

Do not create an unbounded queue per client. One slow subscription must not be allowed to grow memory without limit or impact other subscribers.

## Filtering events by argument and user

Subscription arguments usually define the event scope:

~~~java
@SubscriptionMapping
public Flux<StockEvent> stockChanged(@Argument String productId) {
    return eventService.eventsFor(productId);
}
~~~

The service should filter by productId at the data source if possible. Filtering only at the application layer after receiving every event can waste bandwidth and CPU unnecessarily.

Subscriptions also need permission checks at subscription time:

~~~java
import java.security.Principal;

@SubscriptionMapping
public Flux<StockEvent> stockChanged(
        @Argument String productId,
        Principal principal) {

    authorizationService.checkCanViewStock(principal, productId);
    return eventService.eventsFor(productId);
}
~~~

For reactive authorization, do not block waiting for permissions:

~~~java
import java.security.Principal;
import org.springframework.security.access.AccessDeniedException;

@SubscriptionMapping
public Flux<StockEvent> stockChanged(
        @Argument String productId,
        Principal principal) {

    return authorizationService.canViewStock(principal, productId)
            .flatMapMany(allowed -> allowed
                    ? eventService.eventsFor(productId)
                    : Flux.error(new AccessDeniedException(
                            "Not authorized to watch stock")));
}
~~~

If permissions can be revoked while a subscription remains open, checking only at subscription time is insufficient. You may need to check permissions per event, terminate the stream when access is revoked, or tie the subscription to a time-limited lease. Verification must balance security requirements with event-processing overhead.

Never treat a tenant or user ID self-declared by the client in an argument as proof of identity. Use Principal/Spring Security and scope queries to the authenticated tenant.

## Avoiding blocking inside Flux

If the application uses WebFlux and Reactor, avoid calling block(), Thread.sleep(), or blocking JDBC directly inside a pipeline running on an event loop. These operations degrade the ability to serve concurrent subscription connections.

If you must call a blocking API or library, isolate it explicitly with an appropriate scheduler:

~~~java
import reactor.core.scheduler.Schedulers;

return Flux.fromIterable(ids)
        .publishOn(Schedulers.boundedElastic())
        .map(blockingClient::loadEvent);
~~~

This example only illustrates offloading blocking work to a dedicated scheduler; in practice, prefer non-blocking clients and batch requests if the data source supports them. Never create a new scheduler per event or per subscription without limits.

## Resource limits and operating subscriptions

Subscriptions can live much longer than regular HTTP requests. Set limits and monitor:

- Concurrent subscriptions per user, tenant, and instance.
- Event rate and payload bytes per second.
- Maximum lifetime or idle timeout if business rules require it.
- Buffer size and overflow behavior.
- Reconnect and retry counts.
- Latency from client unsubscribe to upstream cleanup.
- Metrics for currently open, completed, failed, and cancelled streams.

Send only the fields the client needs. Large payloads or excessive nested fields increase serialization and bandwidth costs for every event.

With multiple server instances, clarify whether events should be distributed to all subscribers or only a single instance. A local Flux or Sinks lives only inside the current process; scaling horizontally typically requires a shared broker or event infrastructure.

## Testing Flux subscriptions

You can test the publisher at the service layer with StepVerifier:

~~~java
StepVerifier.create(eventService.eventsFor("product-42").take(2))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .verifyComplete();
~~~

To test the GraphQL operation and transport, use WebSocketGraphQlTester. The following example assumes the graphQlTester variable is configured as a WebSocketGraphQlTester connected to the WebSocket endpoint:

~~~java
import org.springframework.graphql.test.tester.WebSocketGraphQlTester;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<StockEvent> events = graphQlTester.document("""
        subscription WatchStock($productId: ID!) {
            stockChanged(productId: $productId) {
                eventId
                productId
                availableQuantity
            }
        }
        """)
        .variable("productId", "product-42")
        .executeSubscription()
        .toFlux("stockChanged", StockEvent.class);

StepVerifier.create(events.take(2))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .expectNextMatches(event ->
                event.productId().equals("product-42"))
        .verifyComplete();
~~~

With a live subscription, you can use thenCancel() to simulate a client cancelling after receiving a few events:

~~~java
StepVerifier.create(events)
        .expectNextCount(2)
        .thenCancel()
        .verify();
~~~

Tests should verify both results and lifecycle:

- The operation returns multiple payloads in exact event order.
- Arguments filter for the right product or tenant.
- Errors during subscription setup are returned in the expected format.
- Errors from the publisher after start terminate the stream according to policy.
- Client cancellation cancels upstream and releases resources.
- Buffer overflow or overly fast producers are handled controllably.
- Unauthorized users cannot subscribe or receive events.
- Event payloads and nested fields do not trigger unexpected N+1 queries.

When testing GraphQL subscriptions, make sure the test transport actually uses WebSocketGraphQlTester or an appropriate test server. A standard HTTP GraphQlTester cannot simulate the lifecycle of a WebSocket subscription.

## Common mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Subscription returns only one result | Resolver returns an object or collection instead of a Publisher | Return Flux<T> |
| Subscription fails to connect | WebSocket endpoint or dependency is not enabled | Check starter, path, and proxy |
| Client receives stale events or misses events | Using a hot publisher without replay | Use cursor/replay or an event source with retention |
| Stream stops unexpectedly | Publisher emits onError | Log, classify errors, and define a retry policy |
| Stream is silent even though events were emitted | Wrong filter, routing key, or subscriber not registered yet | Check productId and lifecycle |
| Memory grows over time | Unbounded buffer or slow subscriber | Bound the buffer and choose an overflow policy |
| Consumer keeps running after unsubscribe | Cancellation is not propagated to the source | Use a publisher that supports cancellation and cleanup |
| User receives out-of-scope events | Checking only arguments without checking principal/tenant | Enforce authorization at the source and per event when needed |
| Server overloaded when many clients connect | Each subscription creates unbounded resources | Limit concurrent streams and collect metrics |
| Duplicate events after reconnect | Retry or replay without cursor/idempotency | Use event IDs and deduplication rules |

## Design principles for Flux in subscriptions

When building GraphQL Subscriptions in Spring for GraphQL, apply these principles:

1. **Use @SubscriptionMapping for root fields.** The method returns a Publisher, usually Flux<T>.
2. **One root field per subscription operation.** Select the needed child fields inside the payload.
3. **Separate controller and event source.** The controller binds arguments; the service manages publishers and event filtering.
4. **Understand cold and hot publishers.** Explicitly decide on replay, missed events, and multiple subscribers.
5. **Manage the lifecycle.** Complete, error, and cancel must all terminate resources cleanly.
6. **Choose a backpressure policy.** Bound buffers and decide which events may be dropped or need replay.
7. **Distinguish setup errors from stream errors.** Do not mask source errors with Flux.empty() if the client needs to know the stream broke.
8. **Protect every subscription.** Validate principal, tenant, and event-viewing permissions.
9. **Never block the reactive pipeline.** Use non-blocking clients or isolate bounded blocking tasks.
10. **Test transport and cancellation.** Use WebSocketGraphQlTester and StepVerifier to verify multiple payloads and lifecycle behavior.

Flux is a natural return type for subscriptions because it represents an asynchronous stream capable of emitting multiple items over time. Spring for GraphQL maps the Flux from @SubscriptionMapping into consecutive GraphQL response payloads over a subscription transport. By choosing the right event source, managing cold/hot publishers, cancellation, backpressure, errors, and authorization, an application can deliver real-time updates while maintaining control over resources and data consistency.

## References

- [Spring for GraphQL - Subscription Support and Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL - WebSocket Transport](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Project Reactor - Flux and Backpressure](https://projectreactor.io/docs/core/release/reference/)
