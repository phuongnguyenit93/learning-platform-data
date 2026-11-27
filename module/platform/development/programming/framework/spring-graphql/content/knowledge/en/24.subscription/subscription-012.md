# Subscriptions with SSE

GraphQL Subscriptions allow the server to push new results to the client whenever an event occurs, such as a book being updated or an order changing status. **Server-Sent Events (SSE)** is an HTTP-based transport that keeps a response stream open and sends multiple events from the server to the client.

Spring for GraphQL supports GraphQL Subscriptions over SSE via **GraphQlSseHandler**. The client sends a GraphQL request over HTTP and asks for a response with media type **text/event-stream**. The server returns a stream of Server-Sent Events; each event carries a GraphQL execution result. This is a great fit when data flows primarily from server to client and the application prefers HTTP instead of maintaining WebSocket connections.

This lesson covers how Subscriptions work with SSE, how to configure the endpoint, how to write resolvers with **@SubscriptionMapping**, the event format, how to call it from Spring GraphQL clients and browsers, lifecycle/cancellation, security, connection limits, and testing.

## 1. What is SSE?

**Server-Sent Events** is a standard browser and HTTP streaming mechanism. The client opens an HTTP request, and the server holds the response open and pushes events over time. The client receives continuous updates without polling repeatedly.

Key characteristics of SSE:

- One-way communication: the server sends events to the client over the response stream.
- Built on HTTP and works across standard HTTP infrastructure.
- Event data is text, typically formatted as JSON.
- Events are separated by a blank line.
- The client can close the request to stop receiving data.
- The native browser API named `EventSource` supports SSE over HTTP GET.

Example SSE stream:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache

event: update
data: {"status":"PROCESSING"}

event: update
data: {"status":"COMPLETED"}
~~~

Each event can contain an event name and one or more `data` lines. A blank line terminates an event. With GraphQL over SSE, the event types and payloads follow the GraphQL over SSE protocol.

## 2. Why use SSE for GraphQL Subscriptions?

A GraphQL Subscription creates a stream of GraphQL responses over time. SSE provides the transport to deliver those responses from server to client.

Business use cases:

- Tracking order processing status.
- Receiving notifications when a book is updated.
- Monitoring import or export progress.
- Receiving system alerts.
- Tracking build or deployment status.

If the client only needs to receive notifications from the server, SSE is often simpler to deploy than WebSocket because it uses standard HTTP request/response semantics and requires no bidirectional protocol.

### Comparing SSE, WebSocket, and RSocket

| Criterion | SSE | WebSocket | RSocket |
|---|---|---|---|
| Data direction | Server → client | Bidirectional | Bidirectional, depending on interaction |
| Transport foundation | HTTP response stream | WebSocket connection | TCP or WebSocket |
| GraphQL Subscription | Yes | Yes | Yes |
| Client-to-server messages on same stream | No | Yes | Yes |
| Browser API | `EventSource` or streaming fetch | `WebSocket` | Requires client/library |
| Best suited for | One-way feeds and notifications | Real-time bidirectional interaction | Streaming and RSocket interaction models |
| Connections | One HTTP connection per operation in Spring's supported mode | Can share one connection across multiple operations | Can multiplex multiple interactions per session |

SSE does not replace WebSocket in every scenario. If clients need to send multiple messages over the same real-time connection, WebSocket or RSocket may be more appropriate.

## 3. How does Spring for GraphQL support SSE?

Spring for GraphQL provides **GraphQlSseHandler** as a server transport. This handler receives GraphQL requests over HTTP and returns responses following the Server-Sent Events protocol.

Spring for GraphQL has supported SSE since **1.3.x**, with implementations for both Spring MVC and Spring WebFlux. With Spring Boot auto-configuration, the default HTTP endpoint is **/graphql** and can return SSE when the request specifies the matching media type.

Default SSE request shape:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{
  "query": "subscription { bookUpdated { id title } }"
}
~~~

Differences from standard HTTP GraphQL:

- The request body is still a GraphQL JSON request.
- The request `Content-Type` is `application/json`.
- The `Accept` header requests `text/event-stream`.
- The response is a stream of multiple Server-Sent Events.

In Spring for GraphQL, SSE uses **Distinct connections mode**: each operation has its own HTTP request and response stream. Therefore, each subscription holds a dedicated HTTP connection for as long as the stream remains active.

### Subscription-only transport

Spring for GraphQL's SSE handler is intended for Subscriptions. Regular Queries and Mutations should use the HTTP JSON endpoint. Do not send Queries or Mutations to the SSE endpoint expecting a normal single JSON response.

An application can share the `/graphql` path:

- `Accept: application/json`: HTTP GraphQL request/response.
- `Accept: text/event-stream`: GraphQL Subscription over SSE.

Your Spring Boot and Spring for GraphQL versions determine how routes are auto-configured. Check endpoint settings and supported HTTP methods for the version you use.

## 4. Configuring SSE in Spring Boot

The application needs Spring for GraphQL and a web transport. Example Gradle dependencies:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-graphql")
implementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

If the application uses Spring MVC, use the web starter instead of webflux:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-web")
~~~

Spring Boot configures the HTTP GraphQL endpoint at `/graphql` by default. SSE is selected when the client sends `Accept: text/event-stream`.

Example configuration for HTTP path and methods in Spring Boot versions supporting the HTTP SSE property group:

~~~yaml
spring:
  graphql:
    http:
      path: /graphql
      sse:
        methods: POST
~~~

`POST` is the sensible default for GraphQL JSON requests because clients can send the document, operation name, and variables in the request body.

If browser `EventSource` support is required, you can enable `GET` for SSE:

~~~yaml
spring:
  graphql:
    http:
      sse:
        methods: GET,POST
~~~

Property names and structure may vary across Spring Boot versions. Check the configuration metadata of your exact dependencies before applying this configuration.

### Using GraphQlSseHandler directly

When not using auto-configuration or when explicit routing control is needed, you can register `GraphQlSseHandler` as a web endpoint. Spring for GraphQL provides implementations for both MVC and WebFlux.

In newer versions, the handler offers a builder to configure supported HTTP methods; older versions may use constructors and custom routes. The SSE route predicate must match the HTTP methods accepted by the handler.

Do not expose an SSE route accepting arbitrary HTTP methods unless the application genuinely requires it. Keep routes, handlers, and security policies consistent.

## 5. Defining a Subscription in the schema

The GraphQL schema must define the `Subscription` root type and the fields clients want to watch.

~~~graphql
type Subscription {
  bookUpdated(bookId: ID!): BookUpdatedEvent!
}

type BookUpdatedEvent {
  bookId: ID!
  title: String!
  changedAt: String!
}
~~~

The `bookUpdated` field accepts `bookId` to scope the stream to a specific book. Each event contains updated data that the client is permitted to receive.

Subscription operation:

~~~graphql
subscription BookUpdated($bookId: ID!) {
  bookUpdated(bookId: $bookId) {
    bookId
    title
    changedAt
  }
}
~~~

Whenever the source event stream emits an event, GraphQL executes the Subscription's selection set on that event and produces a GraphQL execution result.

## 6. Writing a resolver with @SubscriptionMapping

In an annotated controller, use **@SubscriptionMapping** to map a method to a root Subscription field.

~~~java
@Controller
public class BookSubscriptionController {

    private final BookEventService bookEventService;

    public BookSubscriptionController(BookEventService bookEventService) {
        this.bookEventService = bookEventService;
    }

    @SubscriptionMapping
    public Flux<BookUpdatedEvent> bookUpdated(
            @Argument String bookId) {

        return bookEventService.eventsFor(bookId);
    }
}
~~~

The method returns **Flux<BookUpdatedEvent>**, a Reactive Streams Publisher emitting multiple events over time.

Components:

- `@SubscriptionMapping` maps the method to a field on the `Subscription` root.
- `@Argument` extracts the `bookId` value from the GraphQL operation.
- `BookEventService` supplies the source event stream.
- Each `BookUpdatedEvent` is used by GraphQL as the source value to resolve the client-selected fields.

SSE is a transport. It does not generate business events and does not replace the source Publisher. The application still needs an event source such as Reactor, a message broker, or an event-emitting service.

### Distinguishing the source stream from the response stream

A Subscription has two stages:

1. The source stream emits business events, such as `BookUpdatedEvent`.
2. GraphQL executes the selection set for each event and emits the corresponding GraphQL `ExecutionResult`.

The SSE transport turns those `ExecutionResult`s into events on the HTTP response stream.

~~~mermaid
flowchart TD
    A[Event source / Publisher] --> B[BookUpdatedEvent]
    B --> C[GraphQL subscription execution]
    C --> D[Resolve selection set]
    D --> E[GraphQL ExecutionResult]
    E --> F[SSE transport]
    F --> G[event: next]
    G --> H[Client receives response]
~~~

This allows clients to choose only the schema fields they need. The server re-executes the selection set for each source event instead of sending the raw internal object.

## 7. Creating a source event stream with Reactor

A simple example using Reactor `Sinks` to emit events:

~~~java
@Component
public class BookEventService {

    private final Sinks.Many<BookUpdatedEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    public Flux<BookUpdatedEvent> eventsFor(String bookId) {
        return sink.asFlux()
                .filter(event -> event.bookId().equals(bookId));
    }

    public void publish(BookUpdatedEvent event) {
        Sinks.EmitResult result = sink.tryEmitNext(event);
        if (result.isFailure()) {
            throw new IllegalStateException(
                    "Cannot emit book update event: " + result);
        }
    }
}
~~~

This is an illustrative example of an event source in a simple application. In production, choose a sink suited to your event semantics and lifecycle, control buffer capacity, handle emit failures, and account for running across multiple instances.

If multiple server instances serve subscriptions, an in-memory `Sinks.Many` emits events only on the instance holding that sink. To distribute events across multiple instances, you typically need a shared message broker or event infrastructure.

### Emitting events after updating data

When a mutation updates a book successfully, the application service can emit an event:

~~~java
public Book updateBook(String bookId, UpdateBookInput input) {
    Book updated = bookRepository.update(bookId, input);

    bookEventService.publish(new BookUpdatedEvent(
            updated.id(),
            updated.title(),
            Instant.now().toString()));

    return updated;
}
~~~

Emit the event only after the business update succeeds. If you must guarantee events are not lost when the database commits but the process stops before publishing, consider a transactional outbox or durable event delivery mechanism.

## 8. GraphQL over SSE format

With GraphQL over SSE in Distinct connections mode, the key events are:

- **next**: carries a GraphQL `ExecutionResult`.
- **complete**: signals that the stream has finished and no further results will arrive.

Example response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: next
data: {"data":{"bookUpdated":{"bookId":"book-01","title":"Spring GraphQL","changedAt":"2026-11-20T10:00:00Z"}}}

event: next
data: {"data":{"bookUpdated":{"bookId":"book-01","title":"Spring GraphQL in Practice","changedAt":"2026-11-20T10:01:00Z"}}}

event: complete
data:
~~~

Each `next` event contains one GraphQL response, typically with `data` and optionally `errors`. When the Publisher completes, the transport sends `complete` and closes the stream.

If the Publisher does not complete, the stream can remain open for a long time until the client cancels, the server closes the connection, or an error terminates the stream.

Do not confuse SSE events with business events. An SSE `next` event carries a GraphQL result; the `data` payload inside it contains the business fields and objects.

## 9. Sending SSE requests with an HTTP client

The client must send the GraphQL document and variables in the body while requesting SSE:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: text/event-stream

{
  "operationName": "BookUpdated",
  "query": "subscription BookUpdated($bookId: ID!) { bookUpdated(bookId: $bookId) { bookId title changedAt } }",
  "variables": {
    "bookId": "book-01"
  }
}
~~~

Items to verify:

- `Content-Type` describes the request body as JSON.
- `Accept` asks the server to return SSE.
- The document must be a Subscription operation.
- Variables must match input types in the schema.
- The response is read as a stream rather than waiting for the full body to complete.

If the client sends `Accept: application/json`, the server processes it via standard HTTP JSON transport and does not return an SSE subscription stream.

## 10. Using HttpGraphQlClient to receive Subscriptions over SSE

The Spring for GraphQL client supports Subscriptions over SSE via **HttpGraphQlClient**. Clients can use the same `GraphQlClient` workflow and call `retrieveSubscription` to obtain a `Flux` of results.

~~~java
WebClient webClient = WebClient.builder()
        .baseUrl("http://localhost:8080/graphql")
        .build();

HttpGraphQlClient client =
        HttpGraphQlClient.builder(webClient).build();

Flux<BookUpdatedEvent> events = client.document("""
        subscription BookUpdated($bookId: ID!) {
            bookUpdated(bookId: $bookId) {
                bookId
                title
                changedAt
            }
        }
        """)
    .variable("bookId", "book-01")
    .retrieveSubscription("bookUpdated")
    .toEntity(BookUpdatedEvent.class);
~~~

The `Flux` emits one `BookUpdatedEvent` for each decoded GraphQL response event. Clients can process it with Reactor operators:

~~~java
events
    .doOnNext(event -> log.info(
            "Book {} changed to {}",
            event.bookId(),
            event.title()))
    .subscribe();
~~~

In real applications, manage the `Disposable` or `Subscription` handle so you can cancel the stream when a component no longer needs events.

### Client-side error handling

The client should distinguish:

- GraphQL execution errors returned inside a GraphQL response.
- Subscription errors that can terminate the stream with `SubscriptionErrorException`.
- Transport errors such as connection loss that can terminate the stream with `GraphQlTransportException`.

If you need to inspect both `data` and `errors` for each event, use `executeSubscription` instead of calling `retrieveSubscription` on a single field.

## 11. Using browser EventSource

Browsers provide the **EventSource** API to consume SSE:

~~~javascript
const query = "subscription { bookUpdated(bookId: \"book-01\") { bookId title } }";
const url = "/graphql?query=" + encodeURIComponent(query);
const source = new EventSource(url);

source.addEventListener("next", (event) => {
  const result = JSON.parse(event.data);
  console.log(result.data);
});

source.addEventListener("complete", () => {
  source.close();
});
~~~

The example above only illustrates how a browser receives events. To work with Spring GraphQL, the SSE endpoint must be configured to accept HTTP `GET`. The GraphQL request must also be encoded according to GraphQL over HTTP `GET` rules.

### Limitations of EventSource

Native `EventSource`:

- Opens `GET` connections only.
- Does not allow customizing the request body.
- Does not support setting custom `Authorization` headers.
- Can send cookies depending on credentials configuration.
- Includes browser-managed automatic reconnection behavior.

Meanwhile, `GraphQlSseHandler` uses `POST` by default. Thus, browser `EventSource` is only suitable if the server enables `GET` and the operation can be passed safely via query parameters.

Never put bearer tokens or secrets into URL query strings because URLs can appear in access logs, proxy logs, browser history, or telemetry. When a `POST` body and `Authorization` header are required, use `HttpGraphQlClient` or a fetch-based SSE client supporting request bodies/headers instead of native `EventSource`.

## 12. GET vs. POST for SSE

`POST` is usually the preferred choice for GraphQL Subscriptions because:

- The document lives in the request body.
- Variables are sent as JSON.
- It avoids practical URL length limits imposed on `GET`.
- HTTP clients can attach `Authorization` headers.

`GET` is useful when compatibility with `EventSource` is required:

- `GET` must be enabled on the SSE handler.
- The query and variables are encoded in the URL.
- Sensitive data must never be put into the URL.
- URL length limits across browsers, proxies, and servers must be considered.

If an operation has many variables or complex input arguments, `POST` with a streaming fetch/client library is usually a better fit.

## 13. Cancellation and Subscription lifecycle

A Subscription can remain open for a long time. When the client no longer needs events, it must cancel the stream by closing the SSE connection or cancelling the client-side `Publisher`.

When the request is cancelled, the server should propagate cancellation down to the source `Publisher` to release:

- Listeners registered on an event bus.
- Consumers/subscriptions on a message broker.
- Database or network resources.
- Per-subscriber buffers and state.
- Metrics or registries tracking active subscriptions.

Example adding cleanup:

~~~java
@SubscriptionMapping
public Flux<BookUpdatedEvent> bookUpdated(
        @Argument String bookId) {

    return bookEventService.eventsFor(bookId)
            .doFinally(signalType ->
                    log.debug(
                            "Book subscription closed: {}, reason={}",
                            bookId,
                            signalType));
}
~~~

`doFinally` runs when the stream completes, errors, or is cancelled. For resources that must be opened and closed per subscriber, use a proper resource lifecycle mechanism rather than just logging.

Do not create a new global listener or message broker consumer per event. Register once per subscription and tear down promptly.

## 14. Reconnect and event recovery capabilities

Standard SSE has client-side reconnection behavior. However, an HTTP-layer reconnect does not automatically guarantee that a GraphQL Subscription resumes from its exact previous position.

In Spring for GraphQL, each operation uses its own connection in Distinct connections mode. When a connection drops and the client resends the operation, the server creates a new subscription. Applications should not assume events emitted during the disconnection window will be re-sent automatically.

If business requirements prohibit losing events, design resumption at the application layer:

- Give each event a stable sequence number or event ID.
- Have the client store the last processed cursor.
- Have the Subscription accept a cursor or timestamp argument.
- Ensure the event source can replay from a broker, log, or database.
- Verify access permissions for both the cursor and replayed data on the server.

Example schema:

~~~graphql
type Subscription {
  orderEvents(orderId: ID!, afterSequence: Long): OrderEvent!
}
~~~

This is an application-designed business contract, not an automatic replay feature of the SSE transport.

## 15. Backpressure, buffering, and slow consumers

A client may receive events slower than the source `Publisher` emits them. If the server holds an unbounded buffer, memory can grow continuously.

When designing the source stream:

- Choose a bounded buffering strategy.
- Identify which events can be coalesced or skipped.
- Never drop events if business rules require complete processing.
- Consider latest-state events if the client only needs the newest state.
- Monitor subscriber counts, queue sizes, and processing latency.
- Cancel the stream if the client disconnects or exceeds configured limits.

Spring for GraphQL uses a Reactive Streams `Publisher` for subscriptions. With WebFlux, streaming can leverage reactive/non-blocking I/O; with Spring MVC, response writing relies on async Servlets. Actual buffering behavior and limits also depend on the event source, server, and proxies.

Do not treat SSE as infinitely scalable for arbitrary subscriber counts. Load-test with concurrent connections and event rates close to production.

## 16. Distinct connections mode and scalability

Spring for GraphQL currently implements GraphQL over SSE in **Distinct connections mode**. Each Subscription has its own HTTP request/response stream.

Implications of this:

- A single user opening multiple subscriptions holds multiple HTTP streams.
- Multiple browser tabs can open multiple connections to the same origin.
- HTTP/1.1 imposes per-origin concurrent connection limits in many browsers.
- HTTP/2 multiplexes multiple streams over one TCP connection, reducing physical connection pressure.
- Proxies and load balancers must support long-lived response streaming.

Spring recommends considering scalability and HTTP/2 when adopting SSE at scale. Verify idle timeouts, maximum connections, response buffering, and infrastructure resource limits.

### Do not confuse the two GraphQL over SSE modes

The GraphQL over SSE specification describes Distinct connections mode and Single connection mode. Spring for GraphQL implements Distinct connections mode.

| Aspect | Distinct connections | Single connection |
|---|---|---|
| SSE connections | One per operation | One connection can carry multiple operations |
| Sending operations | Separate HTTP request | Separate HTTP request with reservation token/operation ID |
| Operation management | Per connection | Requires reservation token and operation ID |
| Spring for GraphQL | Supported | Not implemented |

Do not design clients assuming multiple Subscriptions are multiplexed over a single SSE connection when using Spring's `GraphQlSseHandler`.

## 17. Securing Subscriptions over SSE

Because SSE runs over HTTP, it integrates with Spring Security, CORS, and `WebGraphQlInterceptor` just like other web requests. However, a subscription's lifetime is longer than a normal HTTP response.

### Authentication

Authenticate the request before opening the stream. With `POST`, HTTP clients can send an `Authorization` header. Native `EventSource` does not allow arbitrary headers; if using `EventSource`, consider secure cookies or another client that supports headers.

Never put bearer tokens in query strings. If using cookies, configure `SameSite`, `Secure`, `HttpOnly`, and CSRF/CORS appropriately for your application model.

### Authorization

Do not only check permission to open the Subscription. Ensure the user can only subscribe to topics/resources they are authorized to view.

Example:

~~~java
@SubscriptionMapping
public Flux<OrderEvent> orderEvents(@Argument String orderId) {
    authorizationService.checkCanReadOrder(orderId);
    return orderEventService.eventsFor(orderId);
}
~~~

If permissions can be revoked while the stream is open, consider per-event permission checks or terminating the stream when the principal loses access. Checking only at subscribe time may be insufficient for sensitive data.

### Tenant isolation

Obtain the tenant ID from a verified principal or request context. Never trust a tenant ID directly from a GraphQL argument without verifying that the user has access to that tenant.

### CORS and proxies

If browsers make cross-origin requests, configure CORS with the proper origins, methods, and headers. Ensure proxies do not buffer the entire SSE response or close idle connections prematurely.

## 18. Testing Subscriptions with SSE

Because a subscription is a stream, testing with **HttpGraphQlClient** and **StepVerifier** is typically more suitable than standard `GraphQlTester`, which focuses on single responses.

Example:

~~~java
@Test
void shouldReceiveBookUpdates() {
    Flux<BookUpdatedEvent> events = graphQlClient.document("""
            subscription BookUpdated($bookId: ID!) {
                bookUpdated(bookId: $bookId) {
                    bookId
                    title
                    changedAt
                }
            }
            """)
        .variable("bookId", "book-01")
        .retrieveSubscription("bookUpdated")
        .toEntity(BookUpdatedEvent.class);

    StepVerifier.create(events)
            .then(() -> bookEventService.publish(
                    new BookUpdatedEvent(
                            "book-01",
                            "Updated title",
                            Instant.now().toString())))
            .expectNextMatches(event ->
                    event.bookId().equals("book-01")
                            && event.title().equals("Updated title"))
            .thenCancel()
            .verify();
}
~~~

Tests must ensure the subscription is registered before publishing events. In integration tests, use a latch, sink test hook, or appropriate synchronization signal to avoid race conditions.

Things to verify:

1. The request sends `Accept: text/event-stream`.
2. The response has `Content-Type: text/event-stream`.
3. Each source event produces a GraphQL response event.
4. Variables filter the stream properly.
5. Field selection returns only the fields requested by the client.
6. GraphQL errors within events are handled properly.
7. Publisher completion terminates the stream.
8. Client cancellation cancels the source subscription.
9. Disconnecting and reconnecting does not leak old listeners.
10. Authorization and tenant isolation hold throughout the stream.
11. Multiple subscribers receive events according to expected semantics.
12. Slow consumers do not cause unbounded buffer growth.

If you need to inspect wire format or HTTP headers, use `WebTestClient` to send a `POST` with `Accept: text/event-stream` and read the response body as a stream. Verify status, content type, and event payloads.

## 19. Common mistakes when using Subscriptions with SSE

| Symptom | Possible cause | Resolution |
|---|---|---|
| Response returns JSON instead of a stream | `Accept` is missing `text/event-stream` | Check the `Accept` header |
| SSE endpoint rejects `GET` | Handler accepts `POST` only by default | Enable `GET` only if `EventSource` is truly needed |
| Client receives one response and stops | Resolver returns an object/`Mono` instead of a `Publisher` stream | Return `Flux`/`Publisher` for Subscriptions |
| Query or Mutation fails to run over SSE | SSE handler is intended for Subscriptions | Use HTTP JSON transport |
| Events do not appear | Source `Publisher` has not emitted or filter is wrong | Check the event source and arguments |
| Browser `EventSource` does not send token | API does not support custom `Authorization` headers | Use secure cookies or a fetch-based SSE client |
| Events lost after reconnect | No replay/cursor at application layer | Design sequence IDs and resume support |
| Server keeps listener after client leaves | Cancellation is not handled | Clean up with `doFinally`/resource lifecycle |
| Many subscribers raise memory usage | Unbounded buffer or overly fast events | Bound buffers and set an overload policy |
| One instance receives events, another does not | Event source lives only in local memory | Use a shared broker/event infrastructure |
| Connection closes after a short time | Proxy/load balancer idle timeout | Tune timeouts and test infrastructure |
| Multiple tabs fail to open streams | HTTP/1.1 connection limit | Consider HTTP/2 and subscription limits |

## 20. Workflow for implementing Subscriptions with SSE

When implementing GraphQL Subscriptions over SSE:

1. Confirm the use case genuinely requires one-way server-to-client event streaming.
2. Declare the root `Subscription` field and payload types in SDL.
3. Build the source event `Publisher` using Reactor or event infrastructure.
4. Write the `@SubscriptionMapping` resolver returning `Flux`/`Publisher`.
5. Configure Spring for GraphQL's SSE handler or use Boot auto-configuration.
6. Send HTTP requests with `Content-Type: application/json` and `Accept: text/event-stream`.
7. Use HTTP `POST` by default; enable `GET` only when `EventSource` compatibility is needed.
8. Use `HttpGraphQlClient.retrieveSubscription` or a suitable SSE client to consume the stream.
9. Handle `next` events, GraphQL errors, and `complete` events.
10. Design cancellation to release listeners, consumers, and resources.
11. Authenticate requests and enforce resource- and tenant-level authorization.
12. Decide on a reconnect/replay strategy if business rules prohibit losing events.
13. Bound buffers, monitor subscribers, and verify HTTP/2 and proxy timeouts.
14. Test event delivery, cancellation, errors, reconnection, and concurrent load.

SSE is a natural HTTP transport for GraphQL Subscriptions when clients primarily receive data from the server. Spring for GraphQL provides `GraphQlSseHandler` and supports Distinct connections mode, in which each operation gets its own response stream. The `@SubscriptionMapping` resolver returns a `Publisher` of business events; GraphQL produces an `ExecutionResult` for each event, and SSE sends those results via `next` events until the stream completes or is cancelled. Configure the `Accept` header properly, manage cancellation, enforce authorization and tenant isolation, and design reconnection/replay plus resource limits around business requirements.

## References

- Spring for GraphQL — Server Transports: https://docs.spring.io/spring-graphql/reference/transports.html
- Spring for GraphQL — Client and Subscription Requests: https://docs.spring.io/spring-graphql/reference/client.html
- Spring Boot — Spring for GraphQL and HTTP/SSE endpoint: https://docs.spring.io/spring-boot/reference/web/spring-graphql.html
- GraphQL over SSE protocol: https://github.com/enisdenjo/graphql-sse/blob/master/PROTOCOL.md
