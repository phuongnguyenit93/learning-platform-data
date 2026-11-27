# Publisher and subscription

## Objectives

After this lesson, you will be able to:

- Explain the roles of Reactive Streams `Publisher`, `Subscriber`, and `Subscription`.
- Distinguish `org.reactivestreams.Subscription` from a GraphQL Subscription operation.
- Understand how `Mono` and `Flux` implement `Publisher`.
- Use `@SubscriptionMapping` to return a publisher for a GraphQL subscription field.
- Describe how each event is turned into a GraphQL response.
- Distinguish between cold publishers and hot publishers.
- Understand backpressure, cancellation, errors, and the lifecycle of a subscription.
- Choose an appropriate transport and test subscriptions with `StepVerifier` and `WebSocketGraphQlTester`.

## 1. What is a Publisher?

Reactive Streams defines an asynchronous protocol for transferring data between a producer and a receiver. The central contract of this protocol is the `Publisher<T>` interface.

A Publisher can emit zero, one, or many items of type `T`. It does not push data arbitrarily into the receiver; transfer is governed by a subscription handle and a demand mechanism.

Key components:

| Component | Role |
|---|---|
| `Publisher<T>` | Data producer |
| `Subscriber<T>` | Data receiver |
| `Subscription` | Handle controlling demand and cancellation |
| `onNext(T)` | Emits one item |
| `onError(Throwable)` | Terminates the stream with an error |
| `onComplete()` | Terminates the stream normally |

A Publisher does not necessarily produce data as soon as it is instantiated. Typically, data starts being emitted when a Subscriber subscribes.

In Reactor:

- `Mono<T>` implements `Publisher` and emits at most one item.
- `Flux<T>` implements `Publisher` and can emit zero or many items.

Therefore, Spring for GraphQL can accept `Mono` or `Flux` from a controller or `DataFetcher` to coordinate asynchronous execution.

## 2. Reactive Streams lifecycle

When a Subscriber subscribes to a Publisher, the Publisher invokes `onSubscribe` and provides a `Subscription` object. The Subscriber uses that object to request how many items it wants to receive or to cancel the stream.

~~~mermaid
sequenceDiagram
    participant P as Publisher
    participant S as Subscriber
    S->>P: subscribe(subscriber)
    P-->>S: onSubscribe(subscription)
    S->>P: request(n)
    P-->>S: onNext(item 1)
    P-->>S: onNext(item 2)
    S->>P: request(more)
    P-->>S: onNext(item 3)
    P-->>S: onComplete()
~~~

A Reactive Streams stream can terminate in two ways:

- Complete normally with `onComplete()`.
- Terminate with an error via `onError(Throwable)`.

After a terminal `onComplete` or `onError` signal, the Publisher must not emit further `onNext` signals for that same subscription.

The Subscriber can also call `cancel()` on the `Subscription` to stop receiving data. Upon cancellation, the source should stop unnecessary work and release associated resources.

### Reactive Streams Subscription vs. GraphQL Subscription

The term *Subscription* appears at two different layers:

1. `org.reactivestreams.Subscription` is the object controlling demand and cancellation between a Publisher and a Subscriber.
2. GraphQL Subscription is an operation type that lets a client receive multiple responses over time.

A GraphQL Subscription is commonly implemented on top of a Reactive Streams Publisher, but the two concepts are not identical. A `Flux` can be used in a Query list without creating a GraphQL Subscription operation.

## 3. Mono and Flux as Publishers

Reactor provides two common Publisher types:

~~~java
Mono<Book> oneBook = bookService.findById("b-01");

Flux<Book> books = bookService.findAll();
~~~

`Mono<Book>` can emit one `Book` and then complete, complete empty, or signal an error.

`Flux<Book>` can emit multiple `Book` items over time, complete after the last item, or signal an error.

Simple publisher creation examples:

~~~java
Mono<String> greeting = Mono.just("Hello GraphQL");

Flux<Integer> numbers = Flux.just(1, 2, 3);
~~~

A Publisher can be created from an existing value, a collection, a reactive repository, a message broker, or an event source.

In a Spring for GraphQL application, keep the Publisher across the service and controller layers if the data source already supports reactive streams. There is no need to block and convert a `Flux` into a `List` just for GraphQL to consume the result.

## 4. What is a GraphQL Subscription operation?

GraphQL has three main operation types:

- Query: reads data per request.
- Mutation: modifies data.
- Subscription: subscribes to receive events or updates over time.

Schema example:

~~~graphql
type Query {
  books: [Book!]!
}

type Subscription {
  bookAdded: Book!
}

type Book {
  id: ID!
  title: String!
}
~~~

The client sends a subscription operation:

~~~graphql
subscription {
  bookAdded {
    id
    title
  }
}
~~~

The server establishes an event-watching stream. Whenever a new `Book` is emitted, GraphQL executes the `id` and `title` selection set on that event and sends a response to the client.

Each event produces a separate GraphQL execution result. A subscription can produce multiple responses until the publisher completes, errors, or is cancelled.

Per the GraphQL specification, a subscription operation has exactly one root field. Child fields inside that root field can still be nested like a regular query.

## 5. Using @SubscriptionMapping in Spring for GraphQL

Spring for GraphQL provides `@SubscriptionMapping` to map a controller method to a field on the `Subscription` root type.

SDL:

~~~graphql
type Subscription {
  bookAdded: Book!
}

type Book {
  id: ID!
  title: String!
}
~~~

Controller:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventPublisher eventPublisher;

    public BookSubscriptionController(
            BookEventPublisher eventPublisher) {
        this.eventPublisher = eventPublisher;
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return eventPublisher.bookAdded();
    }
}
~~~

Spring infers the field name from the `bookAdded` method name and maps it to `Subscription.bookAdded`.

If the method name differs from the field name in SDL, you can declare it explicitly:

~~~java
@SubscriptionMapping(name = "bookAdded")
public Flux<Book> streamNewBooks() {
    return eventPublisher.bookAdded();
}
~~~

The method returns `Flux<Book>`, which is a Publisher emitting `Book` events. Spring for GraphQL and GraphQL Java coordinate to execute the selection set for each emitted item.

It can receive arguments and authentication details just like other annotated controller methods:

~~~graphql
type Subscription {
  bookAdded(authorId: ID): Book!
}
~~~

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded(@Argument String authorId) {
    return eventPublisher.bookAdded()
            .filter(book -> authorId == null
                    || authorId.equals(book.authorId()));
}
~~~

The filter is applied per subscription. In real-world applications, combine business criteria with the authenticated principal's tenant and permissions.

## 6. Event sources that produce Publishers

A subscription needs a data source capable of emitting events. That source can be:

- A message broker such as Kafka or RabbitMQ.
- An in-application event bus.
- A Reactor Sink.
- A database change stream.
- A publisher created by an external service.

Simple example using a Reactor Sink to emit new Books:

~~~java
@Component
public class BookEventPublisher {

    private final Sinks.Many<Book> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    public Flux<Book> bookAdded() {
        return sink.asFlux();
    }

    public void publish(Book book) {
        Sinks.EmitResult result = sink.tryEmitNext(book);

        if (result.isFailure()) {
            throw new IllegalStateException(
                    "Cannot publish book event: " + result);
        }
    }
}
~~~

When the business operation creates a book successfully, the application emits an event:

~~~java
public Book createBook(CreateBookInput input) {
    Book book = bookRepository.save(toEntity(input));
    eventPublisher.publish(book);
    return book;
}
~~~

This example illustrates an event flow in a simple application. In a production system, explicitly decide:

- Whether events need durable persistence.
- Whether events must be replayed for late-connecting clients.
- Whether multiple application instances must all receive the events.
- What happens when the sink is full or there are no subscribers.
- Whether the event should be published only after transaction commit or before commit.

An in-memory Reactor Sink is not a durable message broker. When the process stops, in-memory events are lost; a client connecting later does not automatically receive past event history.

## 7. Cold Publisher and Hot Publisher

The two publisher types behave differently when there are multiple Subscribers.

### Cold Publisher

A Cold Publisher typically starts independent work for each Subscriber. Each subscription can trigger a separate data-reading process.

Example:

~~~java
Flux<Book> books = Flux.defer(() ->
        bookRepository.findAll());
~~~

Each subscribing client can trigger a fresh query. Cold publishers are well suited for reads or processing that must run independently per subscription.

### Hot Publisher

A Hot Publisher can emit data independently of when Subscribers subscribe. Multiple subscribers can observe the same active event source together.

Reactor Sink example:

~~~java
Sinks.Many<Book> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<Book> sharedEvents = sink.asFlux();
~~~

When the application calls `tryEmitNext`, active subscribers participating in the multicast stream receive the event according to the sink's policy.

| Criterion | Cold Publisher | Hot Publisher |
|---|---|---|
| When emission starts | Usually starts when subscribed | Can emit independently of subscribers |
| Multiple subscribers | Each subscriber can have its own source | Can share the same source |
| Events emitted before subscribing | New subscribers usually do not see them | Can be missed without replay |
| Examples | Reactive repository queries | Event bus, live notifications |

If newly connected clients still need past event history, choose replay or separate event storage. Avoid unbounded in-memory replay if the stream can run indefinitely.

## 8. GraphQL Subscriptions require a streaming-capable transport

A GraphQL Subscription is long-lived and emits multiple responses. The transport must support keeping a connection open or exchanging multiple messages.

Spring for GraphQL supports options such as:

- WebSocket with the GraphQL WebSocket protocol, commonly using the `graphql-transport-ws` subprotocol.
- RSocket with the request-stream model.

Example of configuring a WebSocket endpoint in Spring Boot:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

The client opens a WebSocket connection to the configured endpoint, sends operation registration messages, receives events, and can send a complete message to stop the subscription.

A standard HTTP request-response cannot keep a single response open indefinitely to stream events in the same way. Choose a streaming-capable transport and client for subscription use cases, and check endpoint, subprotocol, and proxy/load balancer policies.

Do not assume that returning a `Flux` from a controller is enough for every transport to automatically support subscriptions. You must configure a streaming transport and matching client.

## 9. How does GraphQL process each event?

The subscription's publisher emits an object or payload. GraphQL uses that payload as the source for the root subscription field and then executes the selection set.

Example:

~~~graphql
subscription {
  bookAdded {
    id
    title
    author {
      name
    }
  }
}
~~~

When the publisher emits a `Book`:

~~~java
new Book("b-01", "GraphQL in Practice", "a-01")
~~~

GraphQL processes it as follows:

1. Uses the `Book` as the source of the `Subscription.bookAdded` field.
2. Reads `Book.id` and `Book.title`.
3. Resolves the `Book.author` field.
4. Uses the `Author` object as the source for `Author.name`.
5. Produces a response containing the data for that event.

If child fields need to load related data, you can use `@SchemaMapping`, DataLoader, or `@BatchMapping` just like in a Query. However, each event can trigger additional resolvers, so monitor processing cost when events fire continuously.

Example response for one event:

~~~json
{
  "data": {
    "bookAdded": {
      "id": "b-01",
      "title": "GraphQL in Practice",
      "author": {
        "name": "Nguyen An"
      }
    }
  }
}
~~~

The next event produces the next response with the same selection set, while the payload may be a different `Book`.

## 10. Backpressure and event emission rate

Reactive Streams provides backpressure so a Subscriber can tell a Publisher how many items it is ready to receive.

The Subscriber calls `request(n)` to request at most `n` more items. This lets producer and consumer coordinate their rates and prevents pushing unbounded data into a slow consumer.

In real subscriptions, the event rate can exceed the server's processing speed or the client's receiving speed. Define a policy for slow downstreams:

- Buffer a bounded number of events.
- Drop oldest or newest events if business rules allow.
- Signal an error when the buffer is full.
- Use a broker with event retention and consumer offsets.
- Throttle frequency or coalesce multiple events into one update.

For example, a dashboard displaying the latest status may accept coalescing consecutive changes. Financial systems or audit logs usually cannot silently drop events.

Do not use an unbounded buffer for long-lived event sources. If a consumer remains slow for a long period, memory can grow continuously.

## 11. Cancellation and resource cleanup

A GraphQL subscription can end when:

- The publisher emits `onComplete`.
- The publisher emits `onError`.
- The client sends a complete/unsubscribe message.
- The WebSocket or RSocket connection closes.
- The server proactively cancels the operation or the application shuts down.

When the client cancels the subscription, cancellation must propagate backward through the reactive chain so upstream stops unnecessary work.

You can observe the lifecycle with `doFinally`:

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return eventPublisher.bookAdded()
            .doFinally(signalType -> {
                if (signalType == SignalType.CANCEL) {
                    log.debug("Book subscription cancelled");
                }
            });
}
~~~

Do not manually call `subscribe()` in the controller to spin off a detached stream. Return the `Publisher` to Spring for GraphQL so the framework manages the subscription lifecycle.

If an event source opens per-subscriber resources such as listeners, cursors, or broker consumers, ensure those resources are closed when the publisher is cancelled or terminates. For application-wide shared sources, cancelling one subscriber must not accidentally close the shared source for other subscribers.

## 12. Error handling in subscription streams

Two error categories should be distinguished:

1. Errors when creating or subscribing to the publisher source.
2. Errors occurring while processing an event and resolving its fields.

If the source publisher emits `onError`, the stream normally terminates. The client receives an error according to GraphQL/transport semantics and will not receive further events from the terminated publisher.

If a field resolver throws an error while processing an event, GraphQL can produce an execution result containing both `data` and `errors` for that event. The exact behavior depends on the field, nullability, and configured exception resolvers.

Example of handling recoverable errors:

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded() {
    return eventPublisher.bookAdded()
            .onErrorResume(
                    TemporaryEventSourceException.class,
                    error -> fallbackPublisher.reconnect()
            );
}
~~~

This example is only suitable if the fallback publisher can continue delivering the same event type with a clear reconnection policy. Avoid turning every error into `Flux.empty()`, because the stream will complete normally and the client may not realize the data source failed.

When handling errors:

- Use stable error classifications for clients.
- Never leak stack traces, SQL, or internal details.
- Define which errors are retryable.
- Establish reconnect and resume policies when needed.
- Test both publisher-source errors and field-resolver errors.

## 13. Securing long-lived subscriptions

A subscription can outlive an ordinary request. Therefore, consider access rights both at start time and throughout the stream's active lifetime.

Key principles:

- Authenticate the connection and subscription operation per application policy.
- Filter events by the authenticated tenant or user.
- Never use client-sent arguments as proof of access permission.
- If user permissions can change, consider re-checking permissions per event.
- When a token expires or a principal loses access, define how to terminate the subscription.
- Never share a publisher containing private data without per-subscriber filtering.
- Keep unnecessary sensitive data out of event payloads.

Example of filtering by authenticated tenant:

~~~java
@SubscriptionMapping
public Flux<Book> bookAdded(
        @ContextValue("tenantId") String tenantId) {

    return eventPublisher.bookAdded()
            .filter(book -> tenantId.equals(book.tenantId()));
}
~~~

`tenantId` must be populated in `GraphQLContext` by a trusted security component. If the event source emits across multiple tenants, the filter must be applied individually for each subscription.

## 14. Testing Publishers and GraphQL Subscriptions

You can test a `Publisher` at the Reactor layer using `StepVerifier`. This tool lets you assert items, ordering, errors, completion, and cancellation.

Example:

~~~java
@Test
void shouldPublishBookEvent() {
    StepVerifier.create(eventPublisher.bookAdded())
            .then(() -> eventPublisher.publish(
                    new Book("b-01", "GraphQL in Practice", "a-01")))
            .assertNext(book ->
                    assertThat(book.id()).isEqualTo("b-01"))
            .thenCancel()
            .verify();
}
~~~

To test GraphQL operations over a real transport, use `WebSocketGraphQlTester` and verify the response stream with `StepVerifier`.

Example with a `graphQlTester` variable already configured to connect via WebSocket:

In real integration tests, synchronize event emission with the moment the server has registered the subscription. The snippet below illustrates the test flow; a test fixture can use a signal confirming the subscriber is ready. Avoid fixed `sleep` calls because handshakes and async scheduling can vary.

~~~java
@Test
void shouldReceiveBookAddedSubscriptionEvent() {
    Flux<GraphQlTester.Response> responses =
            graphQlTester.document("""
                    subscription {
                      bookAdded {
                        id
                        title
                      }
                    }
                    """)
                    .executeSubscription();

    StepVerifier.create(responses)
            .then(() -> eventPublisher.publish(
                    new Book("b-01", "GraphQL in Practice", "a-01")))
            .assertNext(response -> {
                response.path("bookAdded.id")
                        .entity(String.class)
                        .isEqualTo("b-01");
            })
            .thenCancel()
            .verify();
}
~~~

Scenarios worth testing:

1. Publisher emits events in the expected order.
2. A subscriber receives only events matching its filter criteria.
3. Two subscribers each receive data within their allowed scope.
4. Client cancellation stops upstream work.
5. Publisher completes normally.
6. Publisher emits an error and the stream terminates properly.
7. A field resolver error produces a GraphQL error for that event.
8. Backpressure or buffer overflow is handled per policy.
9. WebSocket reconnect does not automatically replay events unless a replay mechanism exists.
10. Tenant isolation and authorization are enforced across the entire subscription lifecycle.

Tests at the Publisher layer do not replace integration tests over the transport. A Publisher might pass in `StepVerifier` while the WebSocket endpoint or GraphQL protocol is still misconfigured.

## 15. Common mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| Subscription returns only one event | Publisher is a `Mono` or the source completes after one item | Use a long-lived publisher when multiple events are needed |
| Client receives no events | Sink has not emitted, client has not subscribed, or transport does not support streaming | Check event source and WebSocket/RSocket |
| Late-connecting client misses past events | Hot publisher without replay/history | Use replay or an event store if business rules require it |
| Query `Flux` is mistaken for a subscription | A `Flux` in a Query is aggregated into a list | Use a GraphQL Subscription operation |
| Subscription does not stop when client leaves | Cancellation is not propagated or source self-subscribes | Return the publisher directly and verify cleanup |
| Memory grows continuously | Unbounded buffer with slow consumers | Set limits and an overflow policy |
| One tenant sees another tenant's events | Missing principal/tenant filter | Filter by authenticated context |
| Stream ends unexpectedly | Publisher emits `onError` or `onComplete` | Check source errors and lifecycle |
| Duplicate events after reconnect | Client/server replays without event ID or resume policy | Design cursors and idempotency |

## 16. Design principles for Publishers and subscriptions

When implementing subscriptions in Spring for GraphQL:

- Return `Publisher<T>` or `Flux<T>` from `@SubscriptionMapping`.
- Use `Mono<T>` only when the intent is a publisher emitting at most one event and completing.
- Distinguish GraphQL Subscription from Reactive Streams `Subscription`.
- Choose a hot or cold publisher according to business requirements.
- Use a streaming-capable transport such as WebSocket or RSocket.
- Understand that each event triggers GraphQL execution for the selection set.
- Define backpressure and buffering policies.
- Propagate cancellation to stop work and release resources.
- Handle publisher-source errors and field-resolver errors separately.
- Enforce access control and tenant scoping throughout the subscription lifetime.
- Use `StepVerifier` for publishers and `WebSocketGraphQlTester` for integration tests.
- Implement replay/resume only when required and backed by appropriate event storage.

## Conclusion

Reactive Streams defines how a Publisher emits data to a Subscriber via a Subscription handle. Reactor provides `Mono` and `Flux` to implement this protocol. Spring for GraphQL uses `Publisher` as the foundation for GraphQL Subscriptions: `@SubscriptionMapping` returns a publisher, and each event is processed by GraphQL into a response matching the client's selection set.

For reliable subscriptions, understand cold and hot publishers, choose a streaming transport, define backpressure policies, propagate cancellation, handle errors, and enforce access control throughout the lifecycle. Testing both the publisher and the WebSocket/RSocket transport helps ensure the event stream behaves properly under real conditions.

## References

- [Spring for GraphQL — Subscription and Request Execution](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Annotated Controllers, Subscription Mapping](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring Boot — Spring for GraphQL WebSocket](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [GraphQL Specification — Subscription](https://spec.graphql.org/October2021/#sec-Subscription)
