# Testing subscriptions with StepVerifier

A GraphQL subscription returns a stream of results rather than a single response. While a query typically finishes as soon as it returns data, a subscription can emit multiple events over time and keep running until the event source completes, errors, or is canceled. Therefore, testing subscriptions requires verifying both the event payloads and the publisher lifecycle.

In Spring for GraphQL, subscription resolvers typically return a `Flux` or `Publisher`. `GraphQlTester` can execute a subscription and turn a field in each event into a Java `Flux`. Reactor Test provides `StepVerifier` to control demand, assert event ordering, verify completion/error signals, and actively cancel the stream.

This lesson focuses on combining `GraphQlTester` with `StepVerifier`, from simple resolver/publisher tests to GraphQL execution and WebSocket transport tests. The goal is deterministic tests with bounded timeouts that never leave subscriptions running indefinitely after a test finishes.

## 1. Why do subscriptions need StepVerifier?

A subscription exhibits behaviors that ordinary assertions cannot fully check:

- Emitting one event or multiple events.
- Preserving event ordering per contract.
- Completing when the data source ends.
- Emitting an error when the event source fails.
- Stopping the data source when the subscriber cancels.
- Respecting demand/backpressure at the publisher boundary.
- Maintaining proper GraphQL selection sets and mappings on every event.

`StepVerifier` subscribes to a `Publisher` and then describes the expected sequence of signals. A test can request specific numbers of events, inspect each event's payload, await completion, or cancel the stream. If the publisher fails to emit signals matching the script, the test fails rather than checking only a single returned value.

Queries and mutations typically use `GraphQlTester.execute()`. Subscriptions use `executeSubscription()` to obtain a subscription spec, followed by `toFlux(path, type)` to extract a stream of values at a response path.

## 2. Declaring the subscription schema and resolver

Example schema for book release events:

~~~graphql
type Subscription {
    bookReleased: BookEvent!
}

type BookEvent {
    id: ID!
    title: String!
    releasedAt: String!
}
~~~

Java record representing the payload:

~~~java
public record BookEvent(
        String id,
        String title,
        String releasedAt) {
}
~~~

Controller:

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService eventService;

    public BookSubscriptionController(BookEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookEvent> bookReleased() {
        return eventService.events();
    }
}
~~~

`@SubscriptionMapping` maps the method to the field on the `Subscription` type. Each subscriber receives a publisher according to the service's semantics. GraphQL evaluates the selection set for every emitted event, so a child-field error can appear in one event's response even while the source publisher continues running.

## 3. Testing the publisher at the service level

Before testing GraphQL mapping, you can test the service's publisher independently. Such tests focus on reactive logic like ordering, filtering, completion, and cancellation.

Example with a finite event source:

~~~java
class BookEventServiceTests {

    @Test
    void emitsEventsInOrder() {
        Flux<BookEvent> events = Flux.just(
            new BookEvent("book-01", "Spring GraphQL", "2026-01-10"),
            new BookEvent("book-02", "Reactive Java", "2026-01-11"));

        StepVerifier.create(events)
            .assertNext(event -> {
                assertThat(event.id()).isEqualTo("book-01");
                assertThat(event.title()).isEqualTo("Spring GraphQL");
            })
            .assertNext(event -> {
                assertThat(event.id()).isEqualTo("book-02");
                assertThat(event.title()).isEqualTo("Reactive Java");
            })
        .expectComplete()
        .verify(Duration.ofSeconds(3));
    }
}
~~~

`assertNext` consumes each element and allows asserting multiple properties. `expectComplete()` and `verify(...)` confirm the publisher emits all expected events and terminates normally. For tests at risk of hanging, always pass a `Duration` to `verify(Duration)` to enforce a time limit.

Service-level tests do not verify the GraphQL schema, `@SubscriptionMapping`, or serialization. They are useful for isolating bugs in the business publisher before testing full GraphQL execution.

## 4. Creating a GraphQlTester for subscriptions

With a GraphQL service inside a Spring context, you can create an execution-level tester:

~~~java
@SpringBootTest
class BookSubscriptionGraphQlTests {

    @Autowired
    GraphQlService graphQlService;

    GraphQlTester graphQlTester;

    @BeforeEach
    void setUp() {
        graphQlTester =
            ExecutionGraphQlServiceTester.create(graphQlService);
    }
}
~~~

This tester executes GraphQL operations directly against the GraphQL service without checking WebSocket handshakes or HTTP upgrades. It is well suited for verifying schemas, resolvers, selection sets, event mapping, and GraphQL execution.

When you need to test the real WebSocket protocol, use `WebSocketGraphQlTester` connected to the endpoint. Both testers provide subscription APIs when supported by configuration; choose the tester based on the boundary you want to verify.

## 5. Executing subscriptions with executeSubscription()

Subscription document:

~~~graphql
subscription BookReleased {
    bookReleased {
        id
        title
        releasedAt
    }
}
~~~

Test reading the stream at the `bookReleased` path:

~~~java
Flux<BookEvent> events = graphQlTester.document("""
        subscription BookReleased {
            bookReleased {
                id
                title
                releasedAt
            }
        }
        """)
    .executeSubscription()
    .toFlux("bookReleased", BookEvent.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.id().equals("book-01")
            && event.title().equals("Spring GraphQL"))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
~~~

`executeSubscription()` initiates the GraphQL subscription operation. `toFlux("bookReleased", BookEvent.class)` reads the corresponding field from each GraphQL event response and decodes it into a `BookEvent`.

The path must match the response key in the document. If a client uses an alias, pass the alias to `toFlux`, not the original schema field name.

## 6. Testing multiple events and ordering

A finite event source keeps tests deterministic:

~~~java
@Test
void mapsEveryGraphQlEventInOrder() {
    Flux<BookEvent> source = Flux.just(
        new BookEvent("book-01", "Spring GraphQL", "2026-01-10"),
        new BookEvent("book-02", "Reactive Java", "2026-01-11"));

    // eventService is a mock injected into the GraphQL controller in the test.
    when(eventService.events()).thenReturn(source);
    Flux<BookEvent> events = graphQlTester.document("""
            subscription {
                bookReleased {
                    id
                    title
                    releasedAt
                }
            }
            """)
        .executeSubscription()
        .toFlux("bookReleased", BookEvent.class);

    StepVerifier.create(events)
        .assertNext(event ->
            assertThat(event.id()).isEqualTo("book-01"))
        .assertNext(event ->
            assertThat(event.id()).isEqualTo("book-02"))
        .expectComplete()
        .verify(Duration.ofSeconds(5));
}
~~~

If using a test fixture instead of a mock, inject that fixture into the controller before running the GraphQL operation. What matters is that the publisher returned by the resolver is the exact event source being verified by `StepVerifier`.

When ordering is part of the contract, use `assertNext` or `expectNext` in exact order. If the event source does not guarantee ordering, assert the set of events or stable attributes instead of baking an artificial order assumption into tests.

## 7. Using TestPublisher or Sinks to drive events

For long-lived streams, tests need to emit events actively after the subscriber has subscribed. Reactor provides `TestPublisher`; Reactor Core also provides `Sinks.Many`.

Example event source controllable via `Sinks.Many`:

~~~java
class BookEventSource {

    private final Sinks.Many<BookEvent> sink =
        Sinks.many().multicast().onBackpressureBuffer();

    Flux<BookEvent> events() {
        return sink.asFlux();
    }

    Sinks.EmitResult publish(BookEvent event) {
        return sink.tryEmitNext(event);
    }

    void complete() {
        sink.tryEmitComplete();
    }
}
~~~

`multicast().onBackpressureBuffer()` delivers events to active subscribers and buffers when a subscriber temporarily lags according to the sink's policy. In tests, create a fresh source per test so events from an earlier test never bleed into subsequent tests.

Example test emitting events after `StepVerifier` subscribes:

~~~java
StepVerifier.create(events)
    .then(() -> {
        assertThat(eventSource.publish(
            new BookEvent("book-01", "Spring GraphQL", "2026-01-10")))
            .isEqualTo(Sinks.EmitResult.OK);
    })
    .assertNext(event ->
        assertThat(event.id()).isEqualTo("book-01"))
    .then(() -> eventSource.complete())
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

`then(...)` executes its callback after `StepVerifier` has subscribed and processed preceding demand steps. That ensures events are emitted once the subscriber is ready. Emitting events to a multicast sink before a subscriber exists can cause those events to be missed by the new subscription.

You can also use `TestPublisher.create()` to drive next, complete, and error signals in unit tests. Pick one consistent fixture pattern and avoid sharing a single mutable publisher across parallel tests.

## 8. Testing non-completing streams and explicit cancellation

Real-world subscriptions rarely complete on their own. When a test only needs to verify a few events, cancel immediately after the assertions:

~~~java
StepVerifier.create(events)
    .then(() -> eventSource.publish(
        new BookEvent("book-01", "Spring GraphQL", "2026-01-10")))
    .expectNextMatches(event ->
        event.id().equals("book-01"))
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Never call `verifyComplete()` on a publisher designed to run continuously unless the test explicitly completes the source. Otherwise the test will block indefinitely or wait for a global timeout.

Cancellation is a key part of the subscription lifecycle. When a client stops listening, the server should cancel the publisher and release listeners, broker consumers, or resources allocated for that subscriber.

## 9. Verifying cleanup on cancel

You can attach a callback to verify that the event source receives the cancel signal:

~~~java
AtomicInteger cancelCount = new AtomicInteger();

Flux<BookEvent> source = Flux.<BookEvent>never()
    .doOnCancel(cancelCount::incrementAndGet);

StepVerifier.create(source)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertThat(cancelCount).hasValue(1);
~~~

This tests cancellation at the publisher boundary. For a GraphQL subscription, supply a similar source with `doOnCancel`, run the operation via `executeSubscription()`, cancel the stream from `StepVerifier`, and assert that the cleanup callback ran.

If a resolver registers a listener with a message broker, keep cleanup inside the publisher lifecycle. Avoid calling `subscribe()` manually inside controllers, because GraphQL will lose control over the inner publisher and cannot propagate cancellation.

## 10. Setting timeouts on StepVerifier

A reactive test should never hang indefinitely. Specify a timeout on `verify`:

~~~java
StepVerifier.create(events)
    .expectNextCount(2)
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

Or use:

~~~java
StepVerifier.create(events)
    .expectNextCount(1)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Timeouts ensure tests fail cleanly if the publisher fails to emit events or complete as expected. Choose a duration generous enough for CI without letting failures stall the whole suite.

If using `StepVerifier.setDefaultTimeout`, remember it is a process/JVM-wide setting affecting subsequent verifications. When different tests need different timeouts, passing the timeout directly to `verify` makes intent clearer.

## 11. Testing publisher errors

Event sources can terminate with an error, such as a broker disconnect or a service failure while reading events. At the service publisher level, `StepVerifier` asserts error signals:

~~~java
RuntimeException failure =
    new IllegalStateException("event source unavailable");

StepVerifier.create(Flux.<BookEvent>error(failure))
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().equals("event source unavailable"))
    .verify(Duration.ofSeconds(3));
~~~

Avoid coupling tests to long exception messages or messages containing sensitive details. When you only need to verify the error category, use `expectError(Class)` or `expectErrorMatches` checking the expected type or code.

Testing a publisher error is not the same as testing GraphQL error mapping. When the source publisher fails, the subscription stream itself can terminate. When a child field resolver throws during a single event, GraphQL can produce an event response containing `errors` and apply null propagation per schema. Test those two scenarios separately.

## 12. Testing GraphQL event responses with errors

In GraphQL subscriptions, each emitted event is processed as a selection set execution. A child field can fail even while the event source keeps emitting subsequent events. When you need to assert `path`, `locations`, or `extensions.code`, check GraphQL response errors at the right boundary instead of only inspecting successfully mapped DTOs.

With `GraphQlTester.Subscription.toFlux(path, type)`, accessing a field that errored may surface as a field-access error on the client tester depending on the tester and version. When a test must inspect exact error payloads per event, use an API/transport test suited for observing each event's `ClientGraphQlResponse` or test error mapping separately at the execution layer.

Do not lump every failure into a stream-wide `onError`. Distinguish between:

- Source publisher emitting `onError`: the subscription source terminates with an error.
- Child field DataFetcher throwing an exception: GraphQL creates an error for that field/event per execution semantics.
- WebSocket connection closing: transport failure that can affect multiple operations sharing that connection.

## 13. Testing backpressure at the publisher boundary

Reactor Test lets you start with zero initial demand and request elements explicitly:

~~~java
StepVerifier.create(source, 0)
    .thenRequest(1)
    .expectNextMatches(event ->
        event.id().equals("book-01"))
    .thenCancel()
    .verify(Duration.ofSeconds(3));
~~~

This verifies that the publisher under test responds to demand as expected. It tests the Reactor `Publisher` boundary. Do not extrapolate an in-process test to claim that WebSocket, browsers, or message brokers enforce identical end-to-end backpressure; each transport has its own buffering and flow-control mechanics.

If an event source cannot backpressure upstream directly, define an explicit buffer, drop, or overflow policy. Tests should verify that policy rather than assuming every event is buffered infinitely.

## 14. Using virtual time for time-based publishers

When a business publisher relies on `Flux.interval` or `delay`, `StepVerifier.withVirtualTime` enables testing without waiting in real wall-clock time:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .map(index -> "event-" + index))
    .thenAwait(Duration.ofSeconds(3))
    .expectNext("event-0", "event-1", "event-2")
    .thenCancel()
    .verify(Duration.ofSeconds(1));
~~~

The publisher must be constructed inside the `withVirtualTime` supplier so the virtual scheduler replaces the real scheduler before subscription. Creating `Flux.interval` beforehand and passing it in can cause the test to use the real clock anyway.

Virtual time works well for publisher unit tests. It does not control the clock of a WebSocket server, network I/O, or external schedulers; never use it to assert transport-level timeouts.

## 15. Testing GraphQL selection sets and aliases

`toFlux` accepts a response path. If the document defines an alias, the path must use that alias:

~~~graphql
subscription {
    released: bookReleased {
        id
        title
    }
}
~~~

Test:

~~~java
Flux<BookEvent> events = graphQlTester.document("""
        subscription {
            released: bookReleased {
                id
                title
            }
        }
        """)
    .executeSubscription()
    .toFlux("released", BookEvent.class);

StepVerifier.create(events)
    .expectNextMatches(event ->
        event.id().equals("book-01"))
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

GraphQL returns only fields present in the selection set. Test DTOs should reflect the requested payload. If a test expects a field that the document omitted, the value will not magically appear just because the Java event object has that property.

## 16. Testing authorization and event filtering

When a subscription is allowed to emit events only for specific users or tenants, tests must verify both permitted events and filtered-out events. Example publisher filtering by principal:

~~~java
Flux<OrderEvent> visibleEvents(
        String username,
        Flux<OrderEvent> source) {

    return source.filterWhen(event ->
        authorizationService.canRead(username, event));
}
~~~

Unit tests can emit events from two tenants and assert the subscriber receives only events within its scope:

~~~java
Flux<OrderEvent> source = Flux.just(
    new OrderEvent("order-01", "tenant-a"),
    new OrderEvent("order-02", "tenant-b"));

StepVerifier.create(service.visibleEvents("user-a", source))
    .assertNext(event ->
        assertThat(event.tenantId()).isEqualTo("tenant-a"))
    .expectComplete()
    .verify(Duration.ofSeconds(5));
~~~

In GraphQL integration tests, set the principal via your application's security test support and execute the operation through the appropriate tester. Verify that unauthorized users cannot open the subscription or never receive out-of-scope events. When permissions can be revoked mid-stream, alter the policy between two events and verify subsequent events are filtered out or the stream is terminated per contract.

## 17. Testing through WebSocketGraphQlTester

`ExecutionGraphQlServiceTester` tests GraphQL execution, not handshakes, subprotocols, or connection initialization. When an application serves subscriptions over WebSocket, add integration tests with `WebSocketGraphQlTester`.

WebSocket tests should verify:

- Handshakes reach the right endpoint.
- Origin checks and authentication follow policy.
- Client and server negotiate the expected GraphQL WebSocket subprotocol.
- Connection initialization is accepted or rejected properly.
- Subscription operations receive the expected events.
- Canceling operations releases server-side publishers/listeners.
- Closing the connection terminates operations bound to that connection.

Once `WebSocketGraphQlTester` is built using the application's WebSocket client configuration, you can still use `executeSubscription().toFlux(...)` and `StepVerifier` to assert the event stream. Configure the tester against the real test endpoint and close/release it after tests according to your Spring for GraphQL version's lifecycle.

Do not rely on in-process tests to prove WebSocket transport, proxy upgrades, or Origin policies work. Those are transport-layer behaviors that require endpoint tests.

## 18. Avoiding flaky tests and subscription leaks

Subscription tests easily turn flaky if events are emitted before a subscriber subscribes, if a singleton publisher is shared across tests, or if tests fail to cancel streams.

Key practices:

- Create a dedicated publisher fixture for each test.
- Emit events after `StepVerifier` subscribes, using `then(...)` where appropriate.
- Never use `Thread.sleep` to wait for events; drive the publisher explicitly or use virtual time.
- Pass timeouts to every `verify` call that might wait.
- Cancel infinite streams as soon as the required events are verified.
- Assert cleanup callbacks when testing cancellation.
- Avoid running tests in parallel against a shared mutable sink without isolating data.
- Clean up broker listeners, schedulers, or connections after each test.

When testing timed event arrival, use a controllable publisher or virtual scheduler at the unit boundary. `Thread.sleep` only slows tests down without guaranteeing subscriber readiness.

## 19. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Test hangs on `verifyComplete` | Subscription publisher never completes naturally | Use `thenCancel` or explicitly complete the source |
| First event is missed | Event emitted before subscriber subscribed | Emit inside `StepVerifier.then` or use a deliberate replay source |
| Events from another test appear | Shared singleton sink/publisher | Create fresh fixtures per test |
| Test checks service only, skipping GraphQL mapping | Operation never executed via `GraphQlTester` | Add `executeSubscription` and `toFlux` tests |
| In-process test passes while WebSocket fails | Handshake/protocol/Origin untested | Add `WebSocketGraphQlTester` integration tests |
| Cleanup not verified | Canceled without observing source | Attach `doOnCancel` or a cleanup counter |
| Virtual time test still waits in real time | Publisher built before `withVirtualTime` or uses external scheduler | Build publisher inside the supplier and control the scheduler |
| Backpressure assertion misrepresents transport | Tested only Reactor `Publisher` | Separate publisher tests from transport tests |
| All errors treated as stream failures | Confused source `onError` with GraphQL event errors | Test source errors and field execution errors separately |
| Test receives wrong event field | `toFlux` used schema field instead of response alias/path | Use the exact response path in the document |

## 20. Subscription testing matrix

A test suite can be organized by boundary and behavior:

| Boundary | Behavior | Appropriate tool |
| --- | --- | --- |
| Service publisher | Ordering, filtering, completion, errors, cancellation | `StepVerifier` |
| GraphQL execution | Schema, `@SubscriptionMapping`, selection set, event mapping | `GraphQlTester` with `executeSubscription` |
| WebSocket transport | Handshake, Origin, subprotocol, connection init, disconnect | `WebSocketGraphQlTester` |
| Authorization | Principal, tenant scope, revocation, event filtering | Spring Security test support + `StepVerifier` |
| Time-based publisher | Intervals, delays, scheduled events | `StepVerifier.withVirtualTime` |
| Backpressure | Demand, buffer/overflow policy | `StepVerifier` at the publisher boundary |

You do not need to cram every behavior into one huge integration test. Publisher unit tests give fast feedback; GraphQL execution tests verify mapping; transport tests verify WebSocket. Clear boundaries pinpoint the exact failing layer whenever a test breaks.

## 21. Principles for designing subscription tests

Use `StepVerifier` to script the expected signals of a subscription: which events arrive, in what order, whether the publisher completes or errors, and when the subscriber cancels. Use `GraphQlTester.executeSubscription().toFlux(path, type)` to inspect events after GraphQL applies the schema and selection set. For long-lived publishers, cancel explicitly instead of waiting for completion; for finite publishers, assert completion and specify a timeout.

Keep service publisher tests separate from GraphQL execution tests and WebSocket transport tests. Use `Sinks.Many` or `TestPublisher` to drive events, create isolated fixtures per test, and assert cleanup on cancellation. Use virtual time for publishers driven by controllable schedulers; test backpressure at the publisher boundary without extrapolating it to transport flow control.

A well-designed subscription test verifies every critical stream behavior: accurate payloads, contract-compliant ordering, properly classified errors, released resources, and deterministic termination within a bounded timeout.
