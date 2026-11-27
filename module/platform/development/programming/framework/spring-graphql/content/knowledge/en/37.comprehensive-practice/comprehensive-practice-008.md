# Creating a Subscription with Flux

## 1. Practice Objectives

A query returns a single result at the moment the client sends a request. A subscription establishes a stream so the server can push multiple results as new events occur. In Spring for GraphQL, a method annotated with `@SubscriptionMapping` can return Project Reactor's `Flux<T>`.

We will build a book-event tracking feature. Clients subscribe to `bookEvents`, optionally filtering by `bookId`; the server emits events when books are created or updated; and each subscriber receives the matching events. This lesson focuses on `Publisher` lifecycle, transport boundaries, authentication, backpressure, error handling, cancellation, and testing.

After this hands-on practice, the same structure can be applied to order status updates, notifications, job progress, or live data feeds.

## 2. Subscriptions in GraphQL

A GraphQL schema has three root operation types: `Query`, `Mutation`, and `Subscription`. A field on `Subscription` describes the payload emitted for each event:

```graphql
type Subscription {
    bookEvents(bookId: ID): BookEvent!
}
```

A client subscribes with an operation:

```graphql
subscription WatchBook($bookId: ID) {
    bookEvents(bookId: $bookId) {
        eventId
        bookId
        eventType
        title
        occurredAt
    }
}
```

The server does not return a single list of events. Instead, each item from the `Publisher` produces a separate GraphQL payload shaped by the client's selection set. The `bookId` argument is nullable so clients can watch all books or a specific book.

`@SubscriptionMapping` is a specialized `@SchemaMapping` for the `Subscription` root type. By default, the method name is used as the field name; you can specify the field explicitly with the `value` attribute when the method name differs from the SDL name.

## 3. Why Choose Flux?

`Flux<T>` represents a `Publisher` that can emit from 0 to many elements, making it a natural fit for an event stream. `Mono<T>` emits at most one element. Spring for GraphQL supports both reactive types in annotated controllers. For subscriptions, use `Flux<T>` to emit multiple events; GraphQL Java consumes the stream as a Reactive Streams `Publisher` during execution.

| Return Type | Element Count | Use Case |
| --- | --- | --- |
| `T` | One value | Synchronous Query/Mutation resolver |
| `Mono<T>` | 0 or 1 | Single asynchronous result |
| `Flux<T>` | 0 to many | Subscriptions and data streams |

The example below returns `Flux<BookEvent>`. If you register a GraphQL Java `DataFetcher` directly instead of using an annotated controller, you can work directly with a Reactive Streams `Publisher`; with `@SubscriptionMapping` methods, `Flux` is the clear choice and directly supported by Spring for GraphQL.

Do not call `.block()`, `.collectList()`, or manually call `.subscribe()` inside a resolver. `block()` can block threads; `collectList()` collapses the stream into a single result; manual subscribing creates a stream outside the GraphQL request lifecycle. Return `Flux` directly so the framework manages subscription and cancellation.

## 4. Dependencies and Example Structure

The example uses Spring Boot, Spring for GraphQL, and WebFlux:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.boot:spring-boot-graphql-test") // Boot 4.x
    // Boot 3.x: omit the dependency above; @GraphQlTest is in spring-boot-test-autoconfigure
}
```

To serve subscriptions over WebSocket, a Servlet application needs the corresponding WebSocket starter; WebFlux includes WebSocket support in the reactive stack. Dependencies and endpoint configuration must match the server stack in use. Spring Boot manages versions via dependency management, so individual dependency versions typically do not need to be declared.

Suggested package structure:

```text
src/main/java/com/example/books/
    BookEvent.java
    BookEventType.java
    BookView.java
    UpdateBookInput.java
    BookEventPublisher.java
    BookEventService.java
    BookQueryController.java
    BookSubscriptionController.java
    BookMutationController.java
    BookService.java
    BookRepository.java
    BookApplicationService.java       # Option to publish events after commit
    BookUpdatedEventListener.java     # Option to publish events after commit
src/main/resources/graphql/
    schema.graphqls
```

## 5. Declaring the SDL Schema

Create `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    updateBook(input: UpdateBookInput!): Book!
}

type Subscription {
    bookEvents(bookId: ID): BookEvent!
}

type Book {
    id: ID!
    title: String!
}

type BookEvent {
    eventId: ID!
    bookId: ID!
    eventType: BookEventType!
    title: String
    occurredAt: String!
}

enum BookEventType {
    CREATED
    UPDATED
    DELETED
}

input UpdateBookInput {
    id: ID!
    title: String!
}
```

The `bookEvents` field returns one `BookEvent` per emission. `BookEvent!` means each event payload must be non-null; it does not mean the Subscription emits only a single event. `occurredAt` uses `String` so the example does not require a custom scalar. In a real application, you can declare a `DateTime` scalar and register the corresponding scalar wiring.

## 6. Creating the Event Model

Use a Java record to represent an immutable event:

```java
public record BookEvent(
        String eventId,
        String bookId,
        BookEventType eventType,
        String title,
        String occurredAt) {
}
```

Java enum matching the GraphQL enum:

```java
public enum BookEventType {
    CREATED,
    UPDATED,
    DELETED
}
```

Input and mutation data types used in the example:

```java
public record UpdateBookInput(String id, String title) {
}

public record BookView(String id, String title) {
}
```

`BookService` provides book read and update operations; persistence implementation is omitted because the lesson focuses on publishing events from business changes:

```java
import java.util.Optional;

public interface BookService {
    Optional<BookView> findById(String id);
    BookView update(UpdateBookInput input);
}
```

In the post-commit event publishing example below, `BookRepository` has a `BookView update(UpdateBookInput input)` method to persist changes:

```java
public interface BookRepository {
    BookView update(UpdateBookInput input);
}
```

When creating an event, format the timestamp in ISO-8601 UTC:

```java
String occurredAt = Instant.now().toString();
```

Spring GraphQL maps record accessors such as `eventId()` and `bookId()` to GraphQL fields with matching names. If the model differs from the schema structure, use `@SchemaMapping` or a dedicated DTO to adapt it.

## 7. Creating an Event Publisher with Sinks.Many

A subscription needs an event source. For single-JVM hands-on practice, use Reactor's `Sinks.Many`:

```java
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class BookEventPublisher {

    private final Sinks.Many<BookEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer(256, false);

    public Flux<BookEvent> events() {
        return sink.asFlux();
    }

    public Sinks.EmitResult publish(BookEvent event) {
        return sink.tryEmitNext(event);
    }
}
```

`multicast` allows multiple active subscribers to receive new events concurrently. This sink does not replay full history to late subscribers. A bounded buffer prevents a slow subscriber from growing memory indefinitely; when an event cannot be emitted, `tryEmitNext` returns an `EmitResult` for the producer to handle.

This is an in-memory publisher within a single process. Events are lost on process restart and are not automatically synchronized across multiple replicas. For business needs requiring durable delivery, use a message broker or Transactional Outbox; each GraphQL instance can consume the stream from the broker and distribute events to its local subscribers.

## 8. Handling Emit Results

Do not ignore the return value from `tryEmitNext`:

```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Sinks;

@Service
public class BookEventService {

    private final BookEventPublisher publisher;

    public BookEventService(BookEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void publish(BookEvent event) {
        Sinks.EmitResult result = publisher.publish(event);
        if (result.isFailure()) {
            throw new IllegalStateException(
                    "Cannot publish book event: " + result);
        }
    }
}
```

Common failure outcomes:

| Result | Cause | Handling |
| --- | --- | --- |
| `FAIL_OVERFLOW` | Buffer has no room for a new event | Review consumer speed and buffer/drop policy |
| `FAIL_NON_SERIALIZED` | Multiple producers emit concurrently | Serialize emit calls or use an emission handler with retry |
| `FAIL_TERMINATED` | Sink already completed or errored | Check lifecycle; recreate publisher if intended by design |
| `FAIL_CANCELLED` | Sink was cancelled | Check auto-cancel configuration and lifecycle |
| `OK` | Event was accepted | Continue processing |

For important events, maintain metrics, logs with correlation IDs, and retry/durable persistence mechanisms. Do not silently drop events when the producer receives a failure result.

## 9. Writing a @SubscriptionMapping Resolver Returning Flux

The controller maps the `Subscription.bookEvents` field:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class BookSubscriptionController {

    private final BookEventPublisher publisher;

    public BookSubscriptionController(BookEventPublisher publisher) {
        this.publisher = publisher;
    }

    @SubscriptionMapping
    public Flux<BookEvent> bookEvents(
            @Argument("bookId") String bookId) {

        Flux<BookEvent> events = publisher.events();
        if (bookId == null) {
            return events;
        }
        return events.filter(event -> bookId.equals(event.bookId()));
    }
}
```

Because the method name matches the SDL field, Spring can infer the mapping. `@Argument` reads the value sent by the client. `filter` runs per event, so the subscriber only receives events with a matching `bookId`.

If the method name differs from the field name, declare it explicitly:

```java
@SubscriptionMapping("bookEvents")
public Flux<BookEvent> streamBookChanges(
        @Argument String bookId) {
    return publisher.events()
            .filter(event -> bookId == null || bookId.equals(event.bookId()));
}
```

A resolver only produces the `Publisher`. You do not need to spawn threads, maintain subscriber lists, or push payloads over sockets manually; Spring for GraphQL and the transport handler handle the wiring.

The root query in SDL can be mapped by a book-reading controller:

```java
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
    public BookView book(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

`Query.book` is nullable in the SDL, so the controller can return `null` when a book is not found. `BookView` exposes `id` and `title` properties matching the `Book` GraphQL type.

## 10. Publishing Events from a Mutation

When a Mutation updates a book successfully, the application can emit an event:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;
    private final BookEventService eventService;

    public BookMutationController(
            BookService bookService,
            BookEventService eventService) {
        this.bookService = bookService;
        this.eventService = eventService;
    }

    @MutationMapping
    public BookView updateBook(@Argument UpdateBookInput input) {
        BookView updated = bookService.update(input);

        eventService.publish(new BookEvent(
                UUID.randomUUID().toString(),
                updated.id(),
                BookEventType.UPDATED,
                updated.title(),
                Instant.now().toString()));

        return updated;
    }
}
```

In this example, if `bookService.update` is a transactional service method invoked through a Spring proxy and there is no outer transaction wrapping the controller, the service's transaction commits before the method returns; the subsequent publish call therefore runs after commit. If the event is published inside a transaction or an outer transaction wraps the entire mutation, subscribers could receive the event before the final transaction commits. Production systems should make this boundary explicit using application events and `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, or use a Transactional Outbox when events must not be lost between commit and publish.

In this direct path, if `eventService.publish` fails after the service has committed, the mutation may return an error even though the book data was already updated. An outbox records the intent to publish within the same business transaction so a worker can retry independently.

An approach using application events to publish to the sink only after transaction commit:

Place `BookUpdatedApplicationEvent`, `BookApplicationService`, and `BookUpdatedEventListener` in separate files. Imports are grouped at the top of the snippet:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public record BookUpdatedApplicationEvent(BookView book) {
}

@Service
public class BookApplicationService {

    private final BookRepository bookRepository;
    private final ApplicationEventPublisher applicationEvents;

    public BookApplicationService(
            BookRepository bookRepository,
            ApplicationEventPublisher applicationEvents) {
        this.bookRepository = bookRepository;
        this.applicationEvents = applicationEvents;
    }

    @Transactional
    public BookView update(UpdateBookInput input) {
        BookView updated = bookRepository.update(input);
        applicationEvents.publishEvent(new BookUpdatedApplicationEvent(updated));
        return updated;
    }
}

@Component
public class BookUpdatedEventListener {

    private final BookEventService eventService;

    public BookUpdatedEventListener(BookEventService eventService) {
        this.eventService = eventService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(BookUpdatedApplicationEvent event) {
        BookView book = event.book();
        eventService.publish(new BookEvent(
                UUID.randomUUID().toString(),
                book.id(),
                BookEventType.UPDATED,
                book.title(),
                Instant.now().toString()));
    }
}
```

`BookRepository.update` represents the application's persistence operation. The application event is published inside the transaction; the `AFTER_COMMIT` listener converts it into a stream event only after the transaction succeeds. If the process stops after commit but before the listener publishes the event, an in-memory sink can still lose the event; use an Outbox and broker if durable delivery is required.

When using this approach, the mutation calls `BookApplicationService.update(...)` and removes the direct `eventService.publish(...)` call in the controller to avoid duplicate events. An error in the post-commit listener cannot roll back an already completed database transaction.

## 11. Transport Boundary: WebSocket, SSE, and RSocket

GraphQL Subscriptions need a transport capable of delivering multiple payloads over the lifetime of an operation. Spring for GraphQL provides integrations for WebSocket and RSocket. Spring Boot also supports HTTP Server-Sent Events (SSE) for Subscriptions when the client requests the `text/event-stream` media type; exact capabilities and properties depend on the Spring Boot/Spring for GraphQL version.

| Transport | Delivery Mechanism | What to Check |
| --- | --- | --- |
| WebSocket | GraphQL over WebSocket, typically `graphql-transport-ws` | Handshake, subprotocol, `connection_init`, `connection_ack`, payloads, and close |
| SSE | HTTP `text/event-stream` response | `Accept` header, initial event, timeout, and client closing the stream |
| RSocket | `request-stream` | Session, route, and demand/cancel |
| Standard HTTP JSON request/response | One response per request | Suitable for Query/Mutation; not a continuous Subscription stream |

Example WebSocket endpoint configuration:

```yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 10s
      keep-alive: 20s
```

WebSocket must be enabled via dependencies and configuration appropriate for Servlet or WebFlux. Boot starters do not expose the WebSocket endpoint by default; configure `spring.graphql.websocket.path` to enable the endpoint and choose a path. `connection_init` can carry authentication credentials; the server replies with `connection_ack` when accepting connection initialization. The ack only confirms connection initialization—it does not prove resolvers can execute.

SSE is a unidirectional stream from server to client, suited for Subscriptions over HTTP when the client sends `Accept: text/event-stream`; check the `spring.graphql.http.sse.*` properties available in your Boot version. RSocket carries Subscriptions via the `request-stream` interaction model. Clients must connect to the right transport endpoint; sending a regular HTTP POST JSON request to `/graphql` does not automatically turn the request into a stream.

## 12. Authentication and Authorization

Authenticating the connection and authorizing event access are related but distinct tasks. You can authenticate users during the HTTP handshake/WebSocket connection initialization or through the application's security mechanism. After authentication, a Subscription resolver can receive a `Principal`:

```java
public interface BookAuthorization {
    boolean canReadBook(java.security.Principal principal, String bookId);
}
```

The method below lives in `BookSubscriptionController`, with `BookEventPublisher` and `BookAuthorization` injected via constructor:

```java
import java.security.Principal;

// Place this method in a controller that injects BookEventPublisher and BookAuthorization.
@SubscriptionMapping
public Flux<BookEvent> bookEvents(
        @Argument String bookId,
        Principal principal) {

    return publisher.events()
            .filter(event -> bookId == null || bookId.equals(event.bookId()))
            .filter(event -> authorization.canReadBook(
                    principal, event.bookId()));
}
```

Here `authorization.canReadBook` is a business service returning a boolean. In a reactive application, if permission checking is asynchronous, use `filterWhen` with `Mono<Boolean>` so you do not block threads.

Do not treat a client-supplied `bookId` as proof of authorization. Clients can guess IDs belonging to other users or tenants. Permissions must be determined from the authenticated principal and server-side ownership data.

For long-lived Subscriptions, permissions can change after connection establishment. If business rules require immediate revocation, re-check permissions per event or close the subscription upon receiving a revocation signal. Never log tokens or `connection_init` payloads; avoid placing bearer tokens in URL query strings.

## 13. Backpressure and Slow Subscribers

Reactive Streams has a demand mechanism: subscribers signal how many elements they want, and publishers/operators coordinate so emissions do not outpace demand unboundedly. However, backpressure in `Flux` does not mean every transport propagates demand end-to-end to the browser.

- RSocket `request-stream` has protocol-level demand semantics.
- The GraphQL over WebSocket protocol does not define a demand message equivalent to Reactive Streams; the server, framework, socket, and client may each maintain separate buffers.
- SSE runs over HTTP streaming; client read speed and server/proxy buffers still affect resource usage.

Emission order from the source `Flux` also does not always guarantee payload delivery order to the client: GraphQL Java can resolve child fields asynchronously. If event ordering is part of the contract, you can enable `SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED` in `GraphQLContext` via `Instrumentation`; in exchange, the engine may have to buffer results to preserve order.

Therefore, bound buffers, event sizes, subscriptions per connection, and emission rates. With a multicast sink, a slow subscriber can affect shared emission. If `tryEmitNext` returns `FAIL_OVERFLOW`, the producer must enforce an explicit policy:

| Policy | When Appropriate |
| --- | --- |
| Bounded buffer | Brief slowdowns where events should be held temporarily |
| Drop events | Events can be reloaded or are best-effort |
| Keep latest state | Only the latest value matters, such as current price |
| Terminate stream and reconnect | Correctness can no longer be guaranteed |
| Durable broker + cursor | Events must be persisted and consumers can resume from an offset |

Do not grow buffers indefinitely. One slow subscriber can exhaust memory and degrade other requests.

## 14. Cancellation and Resource Cleanup

A subscription ends when the client sends complete/cancel, closes the WebSocket, closes the SSE response, closes the RSocket interaction, or when the publisher completes/errors. The framework cancels the upstream subscription when the transport cancels the operation.

You can observe the lifecycle with `doFinally`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Place these members inside BookSubscriptionController.
private static final Logger logger =
        LoggerFactory.getLogger(BookSubscriptionController.class);

@SubscriptionMapping
public Flux<BookEvent> bookEvents(@Argument String bookId) {
    return publisher.events()
            .filter(event -> bookId == null || bookId.equals(event.bookId()))
            .doFinally(signal ->
                    logger.debug("bookEvents finished: {}", signal));
}
```

`doFinally` runs when the stream completes, errors, or is cancelled. You can use it to decrement a subscriber counter, record metrics, or release per-subscriber resources. If the `Publisher` registers callbacks with an external system, unregister them when the stream is cancelled; consider `Flux.using` or `Flux.usingWhen` for resource management.

Do not keep subscriptions open indefinitely if clients leave. Configure timeouts/maximum lifetimes when operations require bounded sessions, and design clients to reconnect with backoff.

## 15. Handling Errors in the Stream

Errors can occur when creating the `Publisher` or after the Subscription has already emitted some events. Distinguish initial request errors, single-payload execution errors, and terminal errors that end the `Publisher`.

You can log stream errors:

```java
return publisher.events()
        .doOnError(error ->
                logger.warn("Book event stream failed", error));
```

Do not automatically turn every error into `Flux.empty()` because the client may assume the stream completed normally and miss events. If recovery is possible, clearly define the retry/reconnect strategy and how clients resynchronize state. Note that `DataFetcherExceptionResolver` and `@GraphQlExceptionHandler` handle errors raised while the resolver creates the `Publisher`; they do not handle `onError` signals emitted later in the stream. To map errors from a Subscription `Publisher` into GraphQL errors sent to the client, register a `SubscriptionExceptionResolver` bean. Sanitize returned information and never expose stack traces or internal data.

Specific business errors can be represented as status events if that is part of the contract. Errors that corrupt the stream source should terminate the stream and be tracked via metrics/logs. Clients should reconnect with exponential backoff and execute a Query to fetch a snapshot before resuming events to avoid data gaps.

## 16. Testing the Publisher with StepVerifier

Reactor Test's `StepVerifier` tests the publisher without starting a GraphQL server:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

class BookEventPublisherTests {

    @Test
    void emitsAnEventAndSupportsCancellation() {
        BookEventPublisher publisher = new BookEventPublisher();
        BookEvent event = new BookEvent(
                "event-1", "book-10", BookEventType.UPDATED,
                "Spring GraphQL", "2026-11-20T10:00:00Z");

        StepVerifier.create(publisher.events())
                .then(() -> assertThat(publisher.publish(event))
                        .isEqualTo(Sinks.EmitResult.OK))
                .expectNext(event)
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }
}
```

The test above verifies that the event is emitted to subscribers and checks cancellation. It does not yet test the SDL, `@SubscriptionMapping` binding, or the WebSocket protocol.

## 17. Testing GraphQL Subscriptions with GraphQlTester

Spring GraphQL Test provides `GraphQlTester.executeSubscription()` to verify the result stream. `toFlux(path, type)` converts a field in each payload into a Java `Flux`. You can use a tester backed by the execution service to test the GraphQL layer; when you need to verify the real transport, configure `WebSocketGraphQlTester` and run tests against a live WebSocket server.

Example testing a GraphQL subscription with a `GraphQlTester` configured in the test context:

```java
// Spring Boot 4.x:
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
// Spring Boot 3.x:
// import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import reactor.core.publisher.Sinks;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@GraphQlTest(BookSubscriptionController.class)
@Import(BookEventPublisher.class)
class BookSubscriptionTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Autowired
    BookEventPublisher publisher;

    @Test
    void streamsBookEvents() {
        Flux<BookEvent> events = graphQlTester.document("""
                subscription {
                    bookEvents(bookId: "book-10") {
                        eventId
                        bookId
                        eventType
                        title
                        occurredAt
                    }
                }
                """)
                .executeSubscription()
                .toFlux("bookEvents", BookEvent.class);

        StepVerifier.create(events)
                .then(() -> assertThat(publisher.publish(new BookEvent(
                        "event-other", "book-99", BookEventType.UPDATED,
                        "Other book", "2026-11-20T10:00:30Z")))
                        .isEqualTo(Sinks.EmitResult.OK))
                .then(() -> assertThat(publisher.publish(new BookEvent(
                        "event-2", "book-10", BookEventType.UPDATED,
                        "Reactive GraphQL", "2026-11-20T10:01:00Z")))
                        .isEqualTo(Sinks.EmitResult.OK))
                .assertNext(event -> {
                    assertThat(event.eventId()).isEqualTo("event-2");
                    assertThat(event.title()).isEqualTo("Reactive GraphQL");
                })
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }
}
```

`@GraphQlTest` auto-configures `GraphQlTester` to test server-side execution, but does not automatically scan `@Component` beans; `@Import(BookEventPublisher.class)` brings the publisher into the test slice. Ensure the publisher is subscribed to before the test emits events; `StepVerifier.then` runs actions after the subscription is established. In real test suites, use a dedicated publisher per test so events from other tests do not leak into the stream.

When testing the transport, use `WebSocketGraphQlTester` created with the appropriate URL/subprotocol and WebSocket client. Transport tests should verify handshake, authentication, payload receipt, complete/cancel, and connection closure. `GraphQlTester` at the execution layer does not prove on its own that networking, reverse proxies, or WebSocket handshakes are working.

## 18. Checklist and Common Mistakes

| Issue | Common Cause | How to Fix |
| --- | --- | --- |
| Subscription returns only once | Resolver collects `Flux` into a list or returns `Mono` | Return `Flux<T>` directly |
| No events received | Producer hasn't emitted, subscriber registered at the wrong time, or sink terminated | Check lifecycle and `EmitResult` |
| Clients receive wrong-tenant data | Filtering only by client-supplied argument | Check permissions based on server-side `Principal` |
| Events lost across replicas | Using an in-memory sink in one JVM | Use a durable broker or outbox |
| Memory grows when client is slow | Unbounded buffer or emissions outpacing consumers | Bound buffer, rate, and subscription count |
| Resources keep running after client closes | Manual `.subscribe()` or missing callback cleanup | Return `Publisher` to framework and handle cancellation |
| Test hangs | No events emitted, missing cancel, or missing timeout | Use `StepVerifier` with timeout and trigger events after subscribing |
| HTTP endpoint does not stream | Using standard JSON request/response | Enable and use WebSocket, SSE, or RSocket as appropriate |

Before going to production, verify the following:

- [ ] SDL declares root `Subscription` and event types matching the contract.
- [ ] `@SubscriptionMapping` resolver returns `Flux<T>` directly.
- [ ] Events are published only after business operations have committed.
- [ ] Producers check `Sinks.EmitResult` or broker publish outcomes.
- [ ] Clients connect over a transport that supports streaming.
- [ ] Authentication and authorization are enforced per user/tenant.
- [ ] Buffers, event sizes, connection counts, and subscription counts are bounded.
- [ ] Cancellation cleanly releases listeners, resources, and metrics.
- [ ] Errors are observed, sanitized, and paired with a reconnect/resync strategy.
- [ ] Tests cover `Publisher`, GraphQL execution, and transport integration.

## Conclusion

In Spring for GraphQL, `@SubscriptionMapping` maps a field on the root `Subscription` type. The resolver returns `Flux<T>`; Spring GraphQL connects that stream to the transport and manages operation lifecycle. `Sinks.Many` makes single-JVM event publishing easy to practice, whereas distributed systems or critical events should use a broker and durable storage.

Designing Subscriptions requires attention to both the GraphQL schema and the transport: WebSocket, SSE, and RSocket have different connection and streaming semantics. Connection authentication does not replace per-event authorization; Reactor backpressure does not guarantee identical semantics across every transport; cancellation must free resources; and stream errors must be observed with a reconnect strategy. `StepVerifier` tests the `Publisher`, while `GraphQlTester` and `WebSocketGraphQlTester` test GraphQL execution and transport respectively.

## References

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
