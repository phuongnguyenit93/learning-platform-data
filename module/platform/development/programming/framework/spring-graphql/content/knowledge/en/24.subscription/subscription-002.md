# @SubscriptionMapping in Spring for GraphQL

## Objectives

After this lesson, you will be able to:

- Explain how subscriptions differ from queries and mutations in how they return results.
- Declare subscription fields in GraphQL SDL.
- Use `@SubscriptionMapping` to map root fields of the `Subscription` type.
- Return `Publisher<T>` or `Flux<T>` as an event source.
- Understand how GraphQL executes the selection set for each emitted event.
- Connect resolvers to event sources and distinguish between cold publishers and hot publishers.
- Filter events by arguments and control backpressure.
- Handle errors, cancellation, and resource cleanup when a subscriber disconnects.
- Apply authentication, authorization, and per-subscriber data scoping.
- Test subscriptions with `GraphQlTester` and Reactor `StepVerifier`.

## 1. What is a Subscription?

GraphQL has three main operation types:

- **Query** reads data at the time it is called.
- **Mutation** modifies data.
- **Subscription** subscribes to receive new results whenever an event occurs.

A Query normally returns a single response per execution. A Subscription creates a stream of results: the server keeps an active publisher and sends a GraphQL response for every event that the publisher emits.

For example, a client wants to watch the price of a book:

~~~graphql
subscription WatchBookPrice($bookId: ID!) {
    bookPriceChanged(bookId: $bookId) {
        bookId
        price
        changedAt
    }
}
~~~

After subscribing successfully, the client can receive multiple events:

~~~json
{
    "data": {
        "bookPriceChanged": {
            "bookId": "book-42",
            "price": 125000,
            "changedAt": "2026-11-20T10:15:00Z"
        }
    }
}
~~~

Later, the same subscription can receive a new response with a different price. The client does not need to resend a query after each price change.

Subscriptions fit data that requires continuous updates such as order statuses, processing progress, notifications, market prices, or collaboration events. They do not replace queries for regular read operations.

## 2. Declaring a subscription in GraphQL SDL

Subscription fields are declared in the `Subscription` root type.

~~~graphql
type BookPriceChanged {
    bookId: ID!
    price: Float!
    changedAt: String!
}

type Subscription {
    bookPriceChanged(bookId: ID!): BookPriceChanged!
}
~~~

In this example:

- `bookPriceChanged` is the field the client subscribes to.
- `bookId` is an argument used to filter the event stream.
- `BookPriceChanged` is the payload of each event.
- `!` denotes non-null required values according to the schema contract.

A subscription operation has only one root field. The fields selected inside the root field determine what data the server returns for each event.

Valid example:

~~~graphql
subscription {
    bookPriceChanged(bookId: "book-42") {
        bookId
        price
    }
}
~~~

Do not design a subscription operation with multiple independent root fields like a regular query. If you need to watch multiple event types, design an appropriate root event type or create separate subscription operations.

## 3. Which field does @SubscriptionMapping map?

In an annotated controller, `@SubscriptionMapping` maps a method to a field on the GraphQL root type `Subscription`.

Example:

~~~java
@Controller
class BookPriceSubscriptionController {

    private final BookPriceEventService eventService;

    BookPriceSubscriptionController(BookPriceEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookPriceChanged> bookPriceChanged(
            @Argument("bookId") String bookId) {

        return eventService.eventsForBook(bookId);
    }
}
~~~

If the method name is `bookPriceChanged`, Spring maps the method to the field of the same name in `Subscription`. `@SubscriptionMapping` is a shortcut for mapping on the `Subscription` root type; it is not a mapping for child fields of the payload.

Key points to remember:

- The method is invoked when the client starts the subscription operation.
- `@Argument` reads arguments of the root subscription field.
- The return value is a publisher that emits payloads over time.
- Each payload becomes the source value for GraphQL to resolve the event's selection set.
- Child fields of the payload can still use `@SchemaMapping` if a dedicated resolver is needed.

Do not return a single `BookPriceChanged` object if the goal is to maintain an event stream. Return a publisher such as `Flux<BookPriceChanged>` or a compatible `Publisher<BookPriceChanged>` type.

## 4. Execution flow of @SubscriptionMapping

You can visualize the basic lifecycle as follows:

~~~mermaid
flowchart TD
    A["Client sends subscription operation"] --> B["WebSocket transport receives operation"]
    B --> C["GraphQL executes Subscription root field"]
    C --> D["@SubscriptionMapping creates Publisher"]
    D --> E["Publisher emits event"]
    E --> F["GraphQL resolves selection set for event"]
    F --> G["Send GraphQL response to client"]
    G --> H{"More events?"}
    H -->|Yes| E
    H -->|No| I["Publisher completes"]
    H -->|Client cancels| J["Cancel subscription and clean up"]
~~~

The resolver is not called again for every event to create a new operation. The resolver creates a publisher for the subscription operation; the publisher emits events. For each event, GraphQL executes the fields that the client selected on that payload.

For example, if the client selects:

~~~graphql
subscription {
    bookPriceChanged(bookId: "book-42") {
        bookId
        price
        changedAt
    }
}
~~~

then each `BookPriceChanged` payload is processed by GraphQL to produce a response containing the three selected fields.

This also means nested resolvers and DataLoaders may be invoked while processing each event. Pay attention to the cost when events fire frequently or when the selection set is large.

## 5. Publisher and Flux as primary return types

Spring for GraphQL supports subscription resolvers returning a reactive publisher. In Reactor applications, `Flux<T>` is usually the convenient choice:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId);
}
~~~

Meanings of return types:

| Return Type | Meaning for a subscription |
| --- | --- |
| `Flux<T>` | Emits zero, one, or many events and may then complete |
| `Publisher<T>` | Generic reactive contract, without direct coupling to Reactor |
| `Mono<T>` | Can emit at most one event and then complete; suited for single-emission cases rather than long-lived streams |
| `T` or `List<T>` | Synchronous values, do not represent a long-lived event stream |

Do not call `block()` to wait for events inside a subscription resolver. Doing so holds the thread and eliminates the benefits of reactive streams.

The publisher must continue emitting events over time. If the data source has only one value and completes immediately, the subscription also ends after one response.

## 6. Creating an event source with Reactor Sink

For illustration, you can use `Sinks.Many` as an event source in a single-instance application.

Define the payload:

~~~java
public record BookPriceChanged(
        String bookId,
        double price,
        String changedAt) {
}
~~~

Event service:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Service
class BookPriceEventService {

    private final Sinks.Many<BookPriceChanged> sink =
            Sinks.many().multicast().onBackpressureBuffer(256, false);

    public Flux<BookPriceChanged> eventsForBook(String bookId) {
        return sink.asFlux()
                .filter(event -> event.bookId().equals(bookId));
    }

    public Sinks.EmitResult publish(BookPriceChanged event) {
        return sink.tryEmitNext(event);
    }
}
~~~

When the business logic updates the price successfully, the service can publish an event:

~~~java
import java.time.Instant;
import reactor.core.publisher.Sinks;

Sinks.EmitResult result = eventService.publish(
        new BookPriceChanged(
                "book-42",
                125000,
                Instant.now().toString()
        )
);

if (result.isFailure()) {
    // Log or retry according to the application's policy.
}
~~~

In real business code, check the `EmitResult` returned by `publish`. If the event was not emitted, apply an appropriate policy such as retrying, logging, or storing in a broker; do not silently ignore the result.

The sink in this example is an in-memory event source within a single application instance. The buffer is bounded at 256 events; when emission fails, `tryEmitNext` returns a failure `EmitResult` so the caller can decide how to handle it. The `false` argument disables auto-cancel when the last subscriber cancels, allowing the sink to be reused by future subscribers. This is an educational example—it does not persist events durably or synchronize across multiple instances.

In multi-instance production deployments, the event source typically comes from a broker or distributed event system such as Kafka, RabbitMQ, or an appropriate messaging platform. Each instance must receive the relevant events for the subscribers connected to it.

Never ignore `EmitResult`. If the sink rejects an event, the application needs a retry policy, error logging, or forwarding to a durable mechanism. Do not assume every `tryEmitNext` call succeeds.

## 7. Cold publisher and hot publisher

Understand how the event source is shared across subscribers.

A **cold publisher** typically starts its own work when a new subscriber subscribes. Each subscriber may receive an independent stream.

A **hot publisher** emits events independently of when subscribers register. Multiple subscribers can observe the same running event source; late subscribers may miss events emitted earlier.

| Characteristic | Cold publisher | Hot publisher |
| --- | --- | --- |
| When emission starts | Usually starts on subscribe | Can emit before any subscriber connects |
| Data source | Can be created separately per subscriber | Usually shares an event source |
| Late subscribers | Start their own stream per publisher | May miss events emitted before subscribing |
| Examples | `Flux.defer`, certain polling streams | `Sinks.Many`, shared event stream |
| Considerations | Cost of creating a source per subscriber | Fan-out, buffering, replay, and missed events |

In the `Sinks.Many` example, multiple subscribers can receive events concurrently and filter by `bookId`. If a subscriber needs event history prior to subscribing, a pure hot stream cannot satisfy that requirement. Combine historical lookups via Query or use a broker with retention/replay as needed.

## 8. Filtering events with arguments

A subscription often needs to restrict events to the specific entity the client cares about.

Example:

~~~graphql
subscription WatchBookPrice($bookId: ID!) {
    bookPriceChanged(bookId: $bookId) {
        bookId
        price
        changedAt
    }
}
~~~

The resolver receives `bookId` via `@Argument` and asks the service for a filtered publisher:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId);
}
~~~

Filtering events on the server ensures the client receives only relevant data. However, client-supplied arguments are not proof of authorization. Before returning the publisher, the server must verify whether the user is allowed to watch that book.

If the event source is a broker, prefer subscribing or filtering at the appropriate layer to avoid sending all events to every instance and filtering too late under high traffic.

## 9. Nested fields of an event payload

A payload may contain simple fields or relationships that require dedicated resolvers.

SDL:

~~~graphql
type BookPriceChanged {
    bookId: ID!
    price: Float!
    changedAt: String!
    book: Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Subscription resolver emitting the payload:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId);
}
~~~

If `book` is not already present in the payload, it can be resolved with `@SchemaMapping`:

~~~java
@SchemaMapping(typeName = "BookPriceChanged", field = "book")
public Book book(BookPriceChanged event) {
    return bookService.findById(event.bookId());
}
~~~

For each event, GraphQL resolves `BookPriceChanged.book` according to the client's selection set. If many consecutive events load the same book, consider efficient data-fetching approaches, while keeping in mind that each event may have its own execution context and DataLoader lifecycle depending on how the framework executes subscriptions.

Do not stuff the entire entity graph into the payload if only a few fields are needed. Small payloads reduce memory usage, serialization overhead, and WebSocket transmission costs.

## 10. Configuring the WebSocket transport

`@SubscriptionMapping` defines how to handle a subscription field. The client also needs a transport capable of delivering multiple responses over time. WebSocket is a common choice in Spring for GraphQL applications.

With Spring Boot, you can configure the WebSocket endpoint in `application.yml`:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

The WebSocket path must match the endpoint configuration and the URL the client uses. The application also needs a WebSocket runtime compatible with the servlet or reactive stack in use.

Example:

- HTTP POST `/graphql` is typically used for request/response Queries and Mutations.
- WebSocket `/graphql` is configured to maintain a connection and transmit Subscription events.
- Some systems may use another transport such as RSocket if configured accordingly.

Merely declaring `@SubscriptionMapping` does not automatically enable the WebSocket endpoint. Verify the transport configuration, dependencies, and the protocol supported by both client and server.

## 11. Cancellation and cleanup

Subscriptions can be long-lived. When a client cancels an operation or the connection closes, the publisher must be cancelled to release resources.

Example of attaching cleanup to the publisher:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class BookPriceSubscriptionController {

    private static final Logger log =
            LoggerFactory.getLogger(BookPriceSubscriptionController.class);

    private final BookPriceEventService eventService;

    BookPriceSubscriptionController(BookPriceEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookPriceChanged> bookPriceChanged(
            @Argument("bookId") String bookId) {

        return eventService.eventsForBook(bookId)
                .doFinally(signalType ->
                        log.debug(
                                "Book price subscription finished bookId={} signal={}",
                                bookId,
                                signalType
                        )
                );
    }
}
~~~

`doFinally` is invoked when the stream completes, errors, or is cancelled. You can use it to record the subscription lifecycle and clean up resources allocated specifically for that subscriber.

Resources to release may include:

- Listener registrations on a message broker.
- Consumers or channels created specifically for a subscriber.
- Polling resources or timers.
- Per-subscription buffers.
- Callbacks or listeners registered on internal services.

Never create a new listener without a corresponding cancellation mechanism. If a publisher is shared across multiple subscribers, cancelling one subscriber must not accidentally close the shared event source for all subscribers.

## 12. Backpressure and slow subscribers

An event source can emit faster than a client can receive and process events. In that case, an explicit backpressure policy is needed.

Common options:

- **Buffer:** hold events in a queue for the subscriber to receive later; must have a bounded capacity.
- **Drop:** discard events when the subscriber cannot keep up; only appropriate if the business logic tolerates lost events.
- **Latest:** keep only the latest state and drop intermediate states; suitable for some status-update streams.
- **Reject or disconnect:** disconnect the subscriber when resource limits are exceeded.
- **Durable broker:** use storage/offset mechanisms so the subscriber can resume according to system policy.

Do not use an unbounded buffer for long-lived subscriptions. Slow subscribers can cause memory usage to grow continuously.

If every event matters—for example, financial transactions or state changes requiring auditing—do not rely on an in-memory sink with temporary buffering. Use an event broker with retention, acknowledgments, or an appropriate replay mechanism.

## 13. Error handling in subscription streams

Errors can occur when creating the publisher or while the publisher is emitting events.

Common error categories:

- The user lacks permission to start the subscription.
- Invalid arguments or non-existent target entity.
- Message broker disconnects.
- Failure while processing an individual event.
- The publisher emits an error signal.
- The client cancels the connection.

Distinguish between errors at subscription initialization and errors occurring after the stream is already active. When the event source emits a terminal error, the publisher normally terminates and the subscription stops receiving further events from that stream.

You can map business exceptions to safe messages before returning the stream while logging diagnostics on the server:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId)
            .onErrorMap(
                    EventSourceException.class,
                    exception -> new SubscriptionUnavailableException(
                            "The event source is currently unavailable.",
                            exception
                    )
            );
}
~~~

Do not expose exception messages, broker hostnames, or stack traces in event payloads. Subscription error handling must still adhere to the GraphQL contract and the application's security policies.

If a single event fails due to isolated bad data, decide explicitly whether to skip that event, emit a payload representing an error state, or terminate the entire stream. Never catch every error and return an empty object, as the client would not know the stream encountered a failure.

## 14. Securing subscriptions

Subscriptions often hold connections open for a long time, so access must be controlled both at subscription time and during event emission.

Principles:

1. Authenticate the connection according to the transport mechanism in use.
2. Check the principal's permissions when starting the subscription.
3. Do not trust client-supplied `bookId`, `tenantId`, or filters as verified data.
4. Filter events by tenant and subscriber permissions on the server.
5. Account for permissions that may change while the subscription remains active.
6. Cancel or continue filtering the stream if the user's permissions are revoked.
7. Never send payloads containing data belonging to another tenant or user.
8. Limit the number of concurrent subscriptions and connections per user.
9. Avoid logging tokens, cookies, and full event payloads.

If access rights can change during a subscription, checking permissions once when opening the stream may not be enough. You may need to re-check per event or revoke active subscriptions when permissions change.

## 15. Testing subscriptions with GraphQlTester

Spring GraphQL provides `GraphQlTester` with an API to execute subscriptions returning a stream of responses. When testing reactive streams, you can combine it with Reactor `StepVerifier`.

Example operation:

~~~java
Flux<GraphQlTester.Response> responses =
        graphQlTester.document("""
                subscription WatchBookPrice($bookId: ID!) {
                    bookPriceChanged(bookId: $bookId) {
                        bookId
                        price
                    }
                }
                """)
                .variable("bookId", "book-42")
                .executeSubscription();
~~~

Verify one event and then cancel the subscription:

~~~java
StepVerifier.create(responses)
        .assertNext(response -> {
            response.path("bookPriceChanged.bookId")
                    .entity(String.class)
                    .isEqualTo("book-42");

            response.path("bookPriceChanged.price")
                    .entity(Double.class)
                    .isEqualTo(125000.0);
        })
        .thenCancel()
        .verify();
~~~

Real tests require a tester configured with a subscription-capable transport, such as a WebSocket tester, or a test setup that executes GraphQL subscriptions directly when testing the execution layer in isolation. A standard request/response `HttpGraphQlTester` does not replace a long-lived subscription transport.

Cases worth testing:

- A subscriber receives events matching its argument filters.
- Subscriber A does not receive events intended for subscriber B.
- Multiple events are emitted in the exact order guaranteed by the event source.
- When the publisher completes or errors, the client receives the corresponding status.
- When the client cancels the subscription, cleanup runs.
- A slow subscriber does not cause unbounded buffer growth.
- Unauthorized users cannot subscribe or receive events.
- Payloads do not contain fields outside the selection set or sensitive data.

## 16. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Subscription returns only one response and ends | Publisher emits only one event or is a `Mono` that completes | Check the event source and publisher lifecycle |
| `@SubscriptionMapping` is not invoked | Field name does not match SDL or operation does not target the `Subscription` root type | Check the schema and method mapping |
| Client receives transport error when running subscription | WebSocket endpoint is not enabled or URL/protocol mismatches | Check transport and client configuration |
| Every subscriber receives unrelated events | Shared event source lacks argument filtering | Filter by target entity and permissions on the server |
| Late subscribers do not receive past events | Using a hot publisher without replay | Use a Query for snapshots or a broker with retention |
| Memory grows over time | Unbounded buffer or slow subscribers | Bound buffers and set an overflow policy |
| Client cancels but listener keeps running | Cancellation/cleanup not handled | Use `doFinally` and release per-subscriber resources |
| One subscriber closing causes others to lose events | Cleanup accidentally closes a shared publisher source | Separate per-subscriber resources from shared resources |
| Event source error stops the stream | Publisher emits a terminal error | Design retry/reconnect or handle errors per business rules |
| Data from another tenant is sent to the client | Filtering only by client-provided arguments | Derive tenant from the principal and filter on the server |

## 17. Workflow for implementing @SubscriptionMapping

When building a subscription, follow this sequence:

1. **Identify the event.** Choose a business-meaningful event and the payload to send.
2. **Declare SDL.** Create the root field in `Subscription`, defining arguments and payload types.
3. **Write the controller mapping.** Use `@SubscriptionMapping` and `@Argument` for filters.
4. **Create the event source.** Connect to a Reactor sink, broker, or suitable publisher.
5. **Return a Publisher.** Use `Flux<T>` or `Publisher<T>`; never block waiting for events.
6. **Filter data on the server.** Combine arguments with principal and tenant scope.
7. **Choose the transport.** Configure WebSocket or another subscription transport supported by the system.
8. **Design backpressure.** Limit buffers, concurrency, and subscription counts.
9. **Handle errors and cancellation.** Define policies for terminal errors and cleanup.
10. **Test end-to-end.** Verify events, access control, cancellation, and transport.

## 18. Summary

`@SubscriptionMapping` maps a method in an annotated controller to a field on the GraphQL `Subscription` root type. The method typically accepts arguments via `@Argument` and returns a `Publisher<T>` such as `Flux<T>`. The publisher emits payloads over time; for each payload, GraphQL resolves the selection set and sends a new response to the subscriber.

Subscriptions require an event source and a transport that supports streaming data, typically WebSocket in Spring for GraphQL applications. Distinguish between hot and cold publishers, filter events by the subscriber's permissions, control backpressure, and release resources when the client cancels the stream. Using `GraphQlTester` with `StepVerifier` helps test multiple events, errors, and cancellation. `@SubscriptionMapping` is the GraphQL mapping layer; overall subscription quality also depends on the event source, transport, security, and publisher lifecycle management.
