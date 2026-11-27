# Flux in Spring for GraphQL

`Flux<T>` is a Project Reactor publisher type representing an asynchronous sequence that can emit from 0 to many elements. In Spring for GraphQL, `Flux` can be used as a return type for controllers and services to process data under the reactive model.

The key point is that the meaning of `Flux` depends on the GraphQL field kind. For a regular query or field with a list type, Spring for GraphQL collects the elements of the `Flux` to build a list in a single GraphQL response. For a subscription, `Flux` represents an event stream; each emitted element produces a separate subscription result. Therefore, do not confuse a query returning `Flux` with a subscription stream.

## 1. What is Flux?

Reactor provides two commonly used publisher types:

| Type | Number of elements | Common usage |
| --- | --- | --- |
| `Mono<T>` | 0 or 1 | Fetching a single object, a single result, or an operation completion. |
| `Flux<T>` | 0 to many | Fetching an asynchronous list or emitting a sequence of events. |

`Flux<T>` implements Reactive Streams `Publisher<T>`. Subscribers subscribe to receive data and control demand through backpressure. Reactor operators allow transforming, filtering, combining, handling errors, and managing the lifecycle of the data sequence.

Example creating a simple Flux:

```java
import reactor.core.publisher.Flux;

Flux<String> names = Flux.just("An", "Binh", "Chi");
```

Creating a Flux from a collection:

```java
List<Book> books = List.of(book1, book2, book3);
Flux<Book> bookFlux = Flux.fromIterable(books);
```

Creating an empty Flux or one terminating with an error:

```java
Flux<Book> empty = Flux.empty();
Flux<Book> failed = Flux.error(new IllegalStateException("Source unavailable"));
```

Flux does not automatically make operations non-blocking. If the underlying data source still calls blocking JDBC or waits on synchronous I/O, the pipeline may still occupy threads while waiting. To get end-to-end reactive benefits, use clients and persistence APIs with reactive support such as WebClient or R2DBC, and avoid blocking on event-loop threads.

## 2. Flux is a Java type, not a GraphQL scalar

GraphQL SDL does not have a `Flux` type. SDL describes the shape of data seen by the client; `Flux` is how the server supplies data asynchronously.

Example schema declaring a list field:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

The resolver can return `List<Book>` or `Flux<Book>`:

```java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
```

Spring for GraphQL handles the publisher and collects the elements to complete the list field. The client still receives a JSON array inside a normal GraphQL response. The client never sees the Java `Flux` type.

For a field returning only a single object, you can use `Mono<Book>`:

```graphql
type Query {
    book(id: ID!): Book
}
```

```java
@QueryMapping
public Mono<Book> book(@Argument("id") String id) {
    return bookService.findById(id);
}
```

`Mono<Book>` fits a field returning a single nullable object. If the source does not find the book and returns `Mono.empty()`, a nullable field can resolve to null. If the schema declares `Book!`, the application must ensure a value exists or handle the error in line with the Non-Null contract.

## 3. Using Flux for Queries returning lists

A list query typically completes once the data source finishes emitting all elements and terminates. Example service using a reactive repository:

```java
import reactor.core.publisher.Flux;

public interface BookService {
    Flux<Book> findAll();
    Flux<Book> findByAuthor(String authorId);
}
```

Controller:

```java
import reactor.core.publisher.Flux;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Flux<Book> books() {
        return bookService.findAll();
    }

    @QueryMapping
    public Flux<Book> booksByAuthor(@Argument("authorId") String authorId) {
        return bookService.findByAuthor(authorId);
    }
}
```

SDL:

```graphql
type Query {
    books: [Book!]!
    booksByAuthor(authorId: ID!): [Book!]!
}
```

Client sends query:

```graphql
query {
    booksByAuthor(authorId: "author-10") {
        id
        title
    }
}
```

The response has a normal list shape:

```json
{
  "data": {
    "booksByAuthor": [
      { "id": "book-1", "title": "Reactive Spring" },
      { "id": "book-2", "title": "GraphQL in Practice" }
    ]
  }
}
```

A query must wait for the publisher to complete in order to build the list value. Therefore, only use `Flux` for a query when the source can terminate. An infinite `Flux` such as `Flux.interval(...)` is not suitable as the result of a regular list query because the response can never complete.

## 4. Flux for nested fields

`Flux` can also be used for a list field nested inside an object, for example each book having multiple tags:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    tags: [String!]!
}
```

Nested field resolver:

```java
import reactor.core.publisher.Flux;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    private final TagService tagService;

    public BookFieldController(TagService tagService) {
        this.tagService = tagService;
    }

    @SchemaMapping(typeName = "Book", field = "tags")
    public Flux<String> tags(Book book) {
        return tagService.findNamesByBookId(book.id());
    }
}
```

When GraphQL finishes resolving the `tags` field, the publisher is collected into a list to include in the query response. If many books are returned together and each `tags` resolver calls the database separately, the application can hit N+1 queries. In that case, consider `@BatchMapping`, DataLoader, or batch queries; using `Flux` by itself does not eliminate N+1.

## 5. Using Flux for Subscriptions

Subscription is the operation type meant for data emitted over time. A subscription root field can return `Flux<T>` to represent the stream of events.

SDL:

```graphql
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
```

Controller:

```java
import reactor.core.publisher.Flux;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookSubscriptionController {

    private final BookEventService bookEventService;

    public BookSubscriptionController(BookEventService bookEventService) {
        this.bookEventService = bookEventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return bookEventService.bookAddedEvents();
    }
}
```

Client subscribes:

```graphql
subscription {
    bookAdded {
        id
        title
    }
}
```

When `Flux` emits a `Book`, GraphQL executes the selection set for that event and sends a subscription response. If the publisher emits three books, the client receives three separate results over time, rather than one array containing all three books like a list query.

| Characteristic | Query returning `Flux<Book>` | Subscription returning `Flux<Book>` |
| --- | --- | --- |
| SDL | Field typically has type `[Book!]!` | Root field has type `Book!` or an appropriate event type |
| Flux meaning | Data source to build one list | Multi-emission event stream |
| Client result | One GraphQL response when Flux completes | Multiple GraphQL responses, one per event |
| Lifecycle | Typically finite | Can be long-lived until complete/cancel/error |
| When appropriate | List loaded asynchronously | Notifications or continuously changing data |

Subscriptions require a streaming-capable transport, typically WebSocket or RSocket in Spring for GraphQL. Standard HTTP request/response fits queries and mutations; configure the subscription transport and endpoint according to your deployment environment.

## 6. Creating an event stream with Reactor Sinks

In small examples or simple systems, you can use `Sinks.Many` as an event emitter source:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import org.springframework.stereotype.Service;

@Service
public class BookEventService {

    private final Sinks.Many<Book> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    public Flux<Book> bookAddedEvents() {
        return sink.asFlux();
    }

    public void publish(Book book) {
        Sinks.EmitResult result = sink.tryEmitNext(book);
        if (result.isFailure()) {
            throw new IllegalStateException("Cannot publish book event: " + result);
        }
    }
}
```

After saving a book successfully, a service can call `publish(savedBook)` to emit an event. Active subscribers will receive the event according to the sink's policy.

`multicast()` is meant for currently subscribed subscribers; new subscribers do not automatically receive the entire history of previously emitted events. If recent data needs to be replayed, design a replay/cache mechanism or read state from a database. An in-memory `Sinks.Many` fits demos or a single application instance; it does not replace a message broker when events must be shared across multiple instances, persisted durably, or recovered after restarts.

Note on sink lifecycle: a multicast sink has an auto-cancel policy when the last subscriber unsubscribes in its default configuration. If you keep the sink in a singleton service and expect it to serve subscribers that reconnect later, choose an auto-cancel configuration suitable for your Reactor version or create/manage the publisher source with an explicit lifecycle. Test both the case where the last subscriber cancels and a new subscriber later subscribes.

In production systems, the Flux source can come from Kafka, RabbitMQ, Redis Streams, RSocket, or another event service. Choose the technology based on storage, delivery, ordering, and retry requirements for events.

## 7. Cold and hot Flux

Not every Flux emits data in the same way:

- *Cold publishers* typically start work when a new subscriber arrives. Each subscriber may trigger an independent execution, such as a database query.
- *Hot publishers* emit data independently of whether subscribers have subscribed yet. Late subscribers may miss earlier events, depending on replay/buffering mechanisms.

Example cold Flux:

```java
Flux<Book> books = Flux.defer(() -> bookRepository.findAll());
```

Each time it is subscribed to, the supplier is invoked to obtain a fresh publisher. An example hot stream using `Sinks.Many` was shown in the previous section.

For subscriptions, decide whether new subscribers should receive past events. If only events from the time of subscription are needed, multicast may fit. If the client needs the current state, provide a separate query to read a snapshot and then use a subscription to receive subsequent updates. Design the boundary between snapshot and stream carefully to avoid missing or duplicating events.

Do not share a single global hot stream for sensitive data without filtering by tenant, permissions, and subscription conditions. Each subscriber may have a different data scope.

## 8. Commonly used operators

Reactor provides many operators to transform Flux. Example service filtering published books, converting to DTOs, and limiting the number of elements:

```java
public Flux<BookView> recentPublishedBooks() {
    return bookRepository.findAll()
            .filter(BookEntity::isPublished)
            .map(BookView::from)
            .take(50);
}
```

Some common operators:

| Operator | Purpose | Notes |
| --- | --- | --- |
| `map` | Transform each element synchronously | The mapping function should be fast and non-blocking. |
| `filter` | Keep elements matching a condition | Non-matching elements are skipped. |
| `flatMap` | Map to another publisher and merge results | Can run concurrently and alter ordering. |
| `concatMap` | Map each element sequentially to a publisher | Preserves ordering but may reduce concurrency. |
| `take(n)` | Take at most n elements and then complete | Useful to cap results, though not a replacement for pagination in large APIs. |
| `distinct` | Remove duplicates by equality | May require retaining state and consuming memory. |
| `timeout` | Emit an error if no signal arrives within configured time | Choose timeout based on SLA and data source. |
| `onErrorResume` | Switch to a fallback publisher on error | Avoid silently turning critical errors into empty results. |
| `doFinally` | Observe complete, error, or cancel | Suitable for cleanup and metrics, not primary business logic. |

Example of selective error handling:

```java
public Flux<Book> findBooks(String authorId) {
    return bookRepository.findByAuthorId(authorId)
            .onErrorMap(DatabaseException.class,
                    ex -> new BookCatalogUnavailableException(ex));
}
```

The exception can then be handled by Spring for GraphQL through `@GraphQlExceptionHandler`, `@ControllerAdvice`, or `DataFetcherExceptionResolver` according to application policy.

## 9. Backpressure and resource limits

Reactive Streams has a backpressure mechanism: the subscriber informs the publisher how many elements it is ready to receive. This regulates pace between producer and consumer when the entire chain properly supports Reactive Streams.

Some operators that assist with flow control:

```java
Flux<Book> stream = bookEventService.bookAddedEvents()
        .limitRate(32);
```

`limitRate(32)` tunes how the subscriber requests data from upstream in batches; it does not limit the total number of events a client can receive.

For hot sources emitting faster than processing speed, choose a policy when downstream cannot keep up: bounded buffer, drop events, keep latest event, or terminate the subscription on overflow. Example of a bounded buffer:

```java
Flux<Book> buffered = source.onBackpressureBuffer(
        100,
        dropped -> log.warn("Backpressure buffer overflow for book {}", dropped.id()));
```

When the buffer is full, this overload signals overflow; the application must handle the error per its chosen policy. Do not use unbounded buffers for long-lived streams because memory can grow continuously.

Backpressure only regulates publisher/subscriber flow inside the reactive pipeline. It does not automatically bound the size of a list query that the server must collect into a single response. For queries returning large data, use pagination, page size limits, and query complexity limits.

## 10. Errors and empty values in Flux

Flux has three important terminal states:

- Complete: the publisher finishes normally.
- Error: the publisher terminates due to an error.
- Cancel: the subscriber cancels its subscription.

`null` must never be emitted in Reactive Streams. If there are no elements, use `Flux.empty()`; if an error needs to be emitted, use `Flux.error(...)` or propagate errors via appropriate operators.

For a list-typed query field, `Flux.empty()` is collected into an empty list `[]`. For a subscription, `Flux.empty()` emits no events and ends the stream. `Flux.error(...)` terminates the publisher with an error; Spring for GraphQL / GraphQL Java handles the error according to the execution context and exception resolvers.

Example:

```java
public Flux<Book> booksByAuthor(String authorId) {
    if (authorId == null || authorId.isBlank()) {
        return Flux.error(new IllegalArgumentException("authorId is required"));
    }
    return bookRepository.findByAuthorId(authorId);
}
```

Do not replace every error with `Flux.empty()` just to avoid error responses. Doing so can mislead clients into treating a failing database or upstream outage as a valid result with no data.

## 11. Cancellation and subscription cleanup

Subscriptions can be long-lived. A client may cancel a subscription when the user leaves the screen, closes the connection, or no longer needs data. When the transport propagates cancellation down to Reactive Streams, the upstream Flux can stop work and release resources.

Example lifecycle tracking:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

public Flux<Book> bookAddedEvents() {
    return eventSource.events()
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    metrics.recordSubscriptionCancelled("bookAdded");
                }
            });
}
```

`doFinally` is invoked when the stream completes, errors, or is cancelled. Use it for metrics, closing resources, or cleanup tied to the subscription. Do not use mutable fields in a singleton controller to store per-subscriber state.

If the event source opens an external connection or registers an external listener, ensure cancellation closes the corresponding listener/connection. Otherwise, the user has unsubscribed yet the server keeps holding resources.

## 12. Security and data scope for Subscriptions

A subscription creates a persistent stream connection, so permissions must be checked both at subscription time and within the scope of emitted data:

1. Authenticate the user when starting the subscription.
2. Determine the tenant, user, or resources the user is permitted to observe.
3. Filter events by authorization scope on the server before emitting to the client.
4. Do not trust a `userId` or `tenantId` sent by the client without verifying permissions.
5. Monitor duration, number of subscriptions, and resource limits.
6. Define behavior when tokens expire or user permissions are revoked.

Example filtering events by tenant:

```java
@SubscriptionMapping
public Flux<Book> bookAdded(@Argument("tenantId") String tenantId, Principal principal) {
    tenantAccessService.requireAccess(principal.getName(), tenantId);
    return bookEventService.bookAddedEvents()
            .filter(book -> book.tenantId().equals(tenantId));
}
```

The example assumes `Principal` is present and the service verifies tenant access. In real systems, tenant may be read from the security context instead of an argument; if accepted from the client, verify permissions before creating the stream. Event filtering must be performed on the server—never send all events to the client and let the client filter them.

## 13. Testing Flux and Subscriptions

There are two distinct testing layers:

- Testing service publishers with `StepVerifier` to verify emitted values, ordering, completion, errors, and cancellation.
- Testing GraphQL subscriptions over a streaming-capable transport to verify schema, resolvers, and event responses.

Example service test:

```java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void bookEventsEmitExpectedBooks() {
    StepVerifier.create(bookEventService.bookAddedEvents())
            .then(() -> bookEventService.publish(book1))
            .then(() -> bookEventService.publish(book2))
            .expectNext(book1, book2)
            .thenCancel()
            .verify();
}
```

This example assumes a multicast sink is in use and the test subscribes before events are published. With hot publishers, emitting events before a subscriber subscribes can cause events to be missed.

Example testing a GraphQL subscription using `GraphQlTester` configured over WebSocket or RSocket transport:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void subscriptionStreamsBookAddedEvents() {
    Flux<String> titles = graphQlTester.document("""
            subscription {
                bookAdded {
                    title
                }
            }
            """)
            .executeSubscription()
            .toFlux("bookAdded.title", String.class);

    StepVerifier.create(titles)
            .then(() -> bookEventService.publish(book1))
            .expectNext(book1.title())
            .thenCancel()
            .verify();
}
```

Tests must synchronize on the moment the subscription is established before publishing events; in integration tests you can use a latch or signal confirming subscriber registration. Do not rely on accidental timing by emitting events immediately when creating the publisher if you are not sure the client has subscribed yet.

## 14. Common errors when using Flux

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Query never returns a response | Query's Flux never completes | Only use finite Flux for list queries; use Subscription for long-lived streams. |
| Client receives an array instead of continuous events | Flux is used on a regular query/list field | Declare a `Subscription` root and use `@SubscriptionMapping`. |
| Subscription receives no events | Hot source emits before subscriber registers or transport does not support subscriptions | Check lifecycle, WebSocket/RSocket transport, and replay policy. |
| Subscriber receives events from another tenant | Missing per-subscriber filtering/authorization | Verify permissions and filter events on the server. |
| Memory grows over time | Unbounded buffer or slow subscriber | Choose bounded buffer/drop policy and monitor lag. |
| Events lost on reconnect | Stream only emits new events with no replay/durable offset | Use an event store/broker with replay or snapshot query plus subscription. |
| Blocking slows down the entire system | Calling JDBC or synchronous APIs on reactive threads | Use reactive clients or offload blocking work to a suitable scheduler. |
| Errors turned into empty lists | Overly broad `onErrorResume` fallback | Only handle expected errors and preserve system errors that must be reported. |
| Resources not released after unsubscribe | Not handling upstream cancellation | Use `doFinally` or `usingWhen` to clean up properly across the lifecycle. |

## 15. Checklist for using Flux in Spring for GraphQL

1. Use `Flux<T>` when needing to emit 0 to many elements; use `Mono<T>` for 0 or 1 result.
2. Remember that `Flux` is a Java type, while SDL still declares lists/objects per the GraphQL contract.
3. For regular `Query` and list fields, only return finite Fluxes because the server must collect them into one response.
4. For long-lived event streams, declare a `Subscription` root and use `@SubscriptionMapping`.
5. Configure WebSocket or RSocket transport for subscriptions according to the environment.
6. Use reactive repositories/clients to avoid blocking on reactive pipelines.
7. Choose cold/hot semantics, replay, and buffering based on event requirements.
8. Bound resources, backpressure, and list query sizes.
9. Handle errors, completion, and cancellation intentionally.
10. Authenticate and filter events according to each subscriber's permissions.
11. Test publishers with `StepVerifier` and subscriptions over real transports.

`Flux` helps Spring for GraphQL integrate reactive data sources. For list queries, it is a way to supply multiple elements asynchronously for a single response; for subscriptions, it is a source emitting multiple responses over time. Choosing the right operation type, managing backpressure and cancellation, and protecting each subscriber will help the application process data streams efficiently and reliably.

References: [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html) and [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
