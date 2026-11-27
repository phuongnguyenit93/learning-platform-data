# Subscriptions with retrieveSubscription

GraphQL Queries and Mutations typically return a single response per request. Subscriptions differ in that the server emits multiple results over time, such as notifications when a book is updated, an order changes status, or a product price changes. The client side needs a streaming-capable transport and a way to consume that data stream.

Spring for GraphQL provides `GraphQlClient` with a unified API across HTTP, WebSocket, and RSocket. To receive Subscription data as a decoded stream, the client calls `retrieveSubscription(path)` and then chooses the target type with `toEntity(...)`. The result is a `Flux<T>`: each GraphQL response event is decoded from the selected field path into an element in the Flux.

This lesson focuses on `retrieveSubscription`: preparing the GraphQL document and variables, choosing a transport, decoding each event, handling GraphQL errors and transport errors, cancelling subscriptions, controlled reconnection, using interceptors, and testing data streams.

## 1. Subscriptions produce a data stream

Example of a library API emitting events when a book is updated:

```graphql
type Subscription {
  bookUpdated(bookId: ID!): BookEvent!
}

type BookEvent {
  eventId: ID!
  occurredAt: String!
  book: Book!
}

type Book {
  id: ID!
  title: String!
  status: String!
}
```

Client subscribing:

```graphql
subscription BookUpdated($bookId: ID!) {
  bookUpdated(bookId: $bookId) {
    eventId
    occurredAt
    book {
      id
      title
      status
    }
  }
}
```

The server can send multiple responses for the same operation:

```json
{
  "data": {
    "bookUpdated": {
      "eventId": "evt-101",
      "occurredAt": "2026-11-20T10:15:00Z",
      "book": {
        "id": "book-1",
        "title": "Spring for GraphQL",
        "status": "AVAILABLE"
      }
    }
  }
}
```

One response corresponds to one event in the stream. When a subsequent update occurs, the server sends a new response matching the same selection set. A Subscription is not a Query polled periodically; it maintains an execution stream pushed by the server.

## 2. How does retrieveSubscription work?

For a Query or Mutation, the client typically uses:

```java
Mono<Book> book = client.document("""
        query {
            bookById(id: "book-1") {
                id
                title
            }
        }
        """)
        .retrieve("bookById")
        .toEntity(Book.class);
```

`retrieve(...)` decodes a single response into `Mono<T>`. For a Subscription, each response event must be decoded and emitted downstream, so the API is:

```java
Flux<BookEvent> events = client.document("""
        subscription BookUpdated($bookId: ID!) {
            bookUpdated(bookId: $bookId) {
                eventId
                occurredAt
                book {
                    id
                    title
                    status
                }
            }
        }
        """)
        .variable("bookId", "book-1")
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

API call flow:

1. `document(...)` declares the GraphQL Subscription operation.
2. `variable(...)` supplies the value for the `$bookId` variable.
3. `retrieveSubscription("bookUpdated")` selects the field in the `data` section of each response.
4. `toEntity(BookEvent.class)` decodes the field value into a Java object.
5. `Flux<BookEvent>` emits one BookEvent for each response event received.

`retrieveSubscription(path)` is a shortcut for `executeSubscription()` with a field path decoded repeatedly for each response. The path is evaluated relative to the `data` key, using dots to traverse nested fields. If a field is aliased in the operation, use the corresponding alias in the path.

Example with an alias:

```graphql
subscription {
  update: bookUpdated(bookId: "book-1") {
    eventId
    book { id title }
  }
}
```

The path must be `update`:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("update")
        .toEntity(BookEvent.class);
```

## 3. Declaring Java types for events

DTOs can be Java records:

```java
public record BookEvent(
        String eventId,
        String occurredAt,
        BookSnapshot book) {
}

public record BookSnapshot(
        String id,
        String title,
        String status) {
}
```

If a response event returns a list at the selected field, use `toEntityList(...)`:

```java
Flux<List<BookEvent>> batches = client.document("""
        subscription {
            recentBookEvents {
                eventId
                occurredAt
            }
        }
        """)
        .retrieveSubscription("recentBookEvents")
        .toEntityList(BookEvent.class);
```

For complex generic types, you can use `ParameterizedTypeReference`:

```java
ParameterizedTypeReference<Map<String, BookEvent>> eventType =
        new ParameterizedTypeReference<>() {};

Flux<Map<String, BookEvent>> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(eventType);
```

The Java type must match the actual data structure returned by the selection set. A DTO does not need to include every field of the GraphQL type; only the fields selected and intended for decoding.

## 4. Choosing a transport that supports Subscriptions

Not every `GraphQlClient` supports streaming. Spring for GraphQL provides three common choices:

| Client | Transport | When suitable |
| --- | --- | --- |
| `HttpGraphQlClient` | HTTP Server-Sent Events (SSE) | Want HTTP and unidirectional streaming from the server |
| `WebSocketGraphQlClient` | WebSocket | Need bidirectional connection, multiple subscriptions, or multiplexing |
| `RSocketGraphQlClient` | RSocket | Application uses RSocket request-stream and sessions |

`HttpSyncGraphQlClient` uses a blocking HTTP transport and is not an option for Subscription streaming. Choose a streaming-capable client transport before calling `retrieveSubscription`.

### HTTP with Server-Sent Events

`HttpGraphQlClient` uses `WebClient` and can receive Subscriptions over SSE if the server supports it:

```java
WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpGraphQlClient client = HttpGraphQlClient.builder(webClient)
        .build();
```

Then use the same `retrieveSubscription` API:

```java
Flux<BookEvent> events = client.document("""
        subscription {
            bookUpdated(bookId: "book-1") {
                eventId
                occurredAt
                book { id title status }
            }
        }
        """)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

With SSE, the client sends an HTTP POST containing the GraphQL JSON request and requests response media type `text/event-stream`. The server emits response events in Server-Sent Events format. SSE is a unidirectional stream from server to client; the client cancels the stream by closing/cancelling the HTTP response.

### WebSocket

`WebSocketGraphQlClient` uses a shared WebSocket connection across requests:

```java
URI url = URI.create("wss://api.example.com/graphql");
WebSocketClient webSocketClient = new ReactorNettyWebSocketClient();

WebSocketGraphQlClient client =
        WebSocketGraphQlClient.builder(url, webSocketClient)
                .build();
```

The WebSocket client is connection-oriented and multiplexed:

- The connection is established automatically on the first request.
- You can call `start()` to connect ahead of time.
- Multiple requests/Subscriptions share a single connection.
- When the connection is lost, the client can reconnect on the next request or when `start()` is called.
- `stop()` cancels running requests, closes the connection, and rejects new requests.

Use one `WebSocketGraphQlClient` per server to share the connection. Creating a separate client instance per Subscription opens unnecessary connections.

### RSocket

If the server exposes GraphQL over RSocket, you can create the client as follows:

```java
URI uri = URI.create("ws://localhost:7000/rsocket");
ClientTransport transport = WebsocketClientTransport.create(uri);

RSocketGraphQlClient client = RSocketGraphQlClient.builder()
        .clientTransport(transport)
        .build();
```

The RSocket client also maintains a shared session and supports request streaming. Declaring GraphQL operations and calling `retrieveSubscription` remain the same as HTTP/WebSocket; the difference lies in the transport builder and how the server configures RSocket.

## 5. Passing variables and operation name in requests

Subscriptions can take arguments just like Queries:

```graphql
subscription BookUpdated($bookId: ID!, $includeAudit: Boolean!) {
  bookUpdated(bookId: $bookId, includeAudit: $includeAudit) {
    eventId
    book {
      id
      title
    }
  }
}
```

Client passing variables:

```java
Flux<BookEvent> events = client.document(document)
        .operationName("BookUpdated")
        .variable("bookId", "book-1")
        .variable("includeAudit", false)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

Or passing all variables at once:

```java
Map<String, Object> variables = Map.of(
        "bookId", "book-1",
        "includeAudit", false);

Flux<BookEvent> events = client.document(document)
        .operationName("BookUpdated")
        .variables(variables)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

Specifying an operation name is useful when a GraphQL document contains multiple operations or when logs/tracing need to observe by operation name. GraphQL variables must match the names and types declared in the document.

## 6. Consuming the Flux and cancelling the Subscription

`retrieveSubscription` only creates a publisher. The subscription actually begins when a subscriber attaches:

```java
Disposable disposable = client.document(document)
        .variable("bookId", "book-1")
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .subscribe(
                event -> log.info("Book updated: {}", event.eventId()),
                error -> log.error("Subscription failed", error),
                () -> log.info("Subscription completed"));
```

To stop from the client side, cancel the subscription:

```java
disposable.dispose();
```

With WebSocket, cancelling the Flux causes the client to send a `complete` message for the corresponding operation. The transport can keep the connection open so other Subscriptions continue running.

Some operators automatically cancel upstream:

```java
Flux<BookEvent> firstTenEvents = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .take(10);
```

`take(10)` completes after ten events and cancels the upstream Subscription. You can use `timeout(...)` to limit wait time:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .timeout(Duration.ofMinutes(5));
```

A timeout emits `TimeoutException` and cancels upstream. Distinguish cancelling a single operation from closing the entire WebSocket client with `stop()`.

Do not call `subscribe()` inside a service and discard the `Disposable`. Let the caller own the stream lifecycle or store the cancellation handle in a component that manages subscriptions with a clear lifecycle.

## 7. Handling SubscriptionErrorException and transport errors

A Subscription Flux can terminate for several reasons. Two key groups:

| Error type | Cause | How to handle |
| --- | --- | --- |
| `SubscriptionErrorException` | WebSocket server terminated the Subscription with an `error` message containing GraphQL errors | Read errors, classify business or operation errors |
| `GraphQlTransportException` | Transport or connection error, e.g. WebSocket disconnected | Consider reconnect/retry if appropriate |
| `WebSocketDisconnectedException` | WebSocket connection closed or lost before the stream ended | Reconnect and re-subscribe when permitted by policy |
| `FieldAccessException` | Field path has no valid value or has field errors during decoding | Inspect the response and affected field |
| `GraphQlClientException` | Response field cannot be decoded into the requested Java type | Check selection set and DTO |

`SubscriptionErrorException` contains the GraphQL errors received from the WebSocket error message. This class extends `GraphQlTransportException`, so if retrying on the base class, exclude this specific exception. It represents an error where the server actively terminated the stream, unlike a dropped connection. Do not unconditionally retry business or authorization errors, as they will repeat without resolving themselves.

Example bounded retry for transport errors:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                .filter(error ->
                        error instanceof GraphQlTransportException
                                && !(error instanceof SubscriptionErrorException)));
```

Retry re-executes the Subscription operation when a transport error occurs. It does not guarantee receiving all events or receiving them exactly once during the disconnection window. If business logic cannot tolerate missed events, design event IDs/cursors and a resume mechanism or catch-up query after reconnecting.

You can log the server's GraphQL errors before the stream terminates:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .doOnError(SubscriptionErrorException.class,
                error -> log.warn("Subscription errors: {}", error.getErrors()));
```

`getErrors()` returns the list of GraphQL response errors included in the WebSocket `error` message. Log selectively and do not expose sensitive data from error extensions into public logs.

## 8. When to use executeSubscription instead of retrieveSubscription?

`retrieveSubscription(path)` is suitable when only one selected field is needed from each response. If you need to read the entire response, inspect GraphQL errors, or handle null fields or metadata, use `executeSubscription()`:

```java
Flux<ClientGraphQlResponse> responses = client.document(document)
        .variable("bookId", "book-1")
        .executeSubscription();
```

Example handling each response:

```java
Flux<BookEvent> events = client.document(document)
        .executeSubscription()
        .map(response -> {
            if (!response.isValid()) {
                // Request-level failure: inspect response.getErrors().
                throw new IllegalStateException("Subscription response is invalid");
            }

            ClientResponseField field = response.field("bookUpdated");
            if (field.getValue() == null) {
                if (field.getErrors().isEmpty()) {
                    // Field is optional and has no value for this event.
                    return null;
                }
                // Field failure: inspect field.getErrors().
                throw new IllegalStateException("bookUpdated field failed");
            }

            return field.toEntity(BookEvent.class);
        })
        .filter(Objects::nonNull);
```

This snippet illustrates checking the response and field; in real applications, replace the sample exception with a domain exception or custom error type. `ClientGraphQlResponse` lets you check response validity and access `ClientResponseField`.

Comparison:

| API | Result | Use when |
| --- | --- | --- |
| `retrieveSubscription(path).toEntity(Type.class)` | `Flux<Type>` | Only need to decode a single field in each event |
| `retrieveSubscription(path).toEntityList(Type.class)` | `Flux<List<Type>>` | The selected field is a list |
| `executeSubscription()` | `Flux<ClientGraphQlResponse>` | Need to inspect the full response and multiple fields |

## 9. Interceptors for Subscription streams

`GraphQlClientInterceptor` has two methods:

- `intercept(...)` for requests returning a single response.
- `interceptSubscription(...)` for Subscriptions returning `Flux<ClientGraphQlResponse>`.

Example logging each response event:

```java
public class SubscriptionLoggingInterceptor implements GraphQlClientInterceptor {

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {
        return chain.next(request);
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {

        return chain.next(request)
                .doOnNext(response -> log.debug(
                        "Received GraphQL subscription response"));
    }
}
```

Register the interceptor via the builder:

```java
WebSocketGraphQlClient client = WebSocketGraphQlClient.builder(url, webSocketClient)
        .interceptor(new SubscriptionLoggingInterceptor())
        .build();
```

Interceptors are suited for logging, tracing, correlation metadata, and client-level error observation. Do not log full payloads if events contain personal or sensitive data. For WebSocket connection-specific messages such as `connection_init` and `connection_ack`, use `WebSocketGraphQlClientInterceptor`. Each `WebSocketGraphQlClient` may register at most one interceptor of that specialized type.

## 10. Authentication with WebSocket connections

A WebSocket client can send headers during the handshake:

```java
WebSocketGraphQlClient client = WebSocketGraphQlClient.builder(url, webSocketClient)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .build();
```

Some servers require the token in the `connection_init` payload instead of HTTP handshake headers. In that case, implement `WebSocketGraphQlClientInterceptor`:

```java
public class WebSocketAuthInterceptor implements WebSocketGraphQlClientInterceptor {

    private final String accessToken;

    public WebSocketAuthInterceptor(String accessToken) {
        this.accessToken = accessToken;
    }

    @Override
    public Mono<Object> connectionInitPayload() {
        return Mono.just(Map.of("Authorization", "Bearer " + accessToken));
    }

    @Override
    public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
        return Mono.empty();
    }
}
```

Use only the exact mechanism configured on the GraphQL WebSocket server. Do not arbitrarily send the same credentials in multiple places. When a token expires, update credentials and re-establish the connection/session according to the client/server mechanism; an already-authenticated connection does not automatically pick up a new token.

## 11. WebSocket client lifecycle

`WebSocketGraphQlClient` maintains a shared connection across multiple operations. It can be managed explicitly:

```java
client.start()
        .thenMany(client.document(document)
                .retrieveSubscription("bookUpdated")
                .toEntity(BookEvent.class))
        .subscribe(this::handleEvent);
```

When the application stops:

```java
Mono<Void> stopSession = client.stop();
```

`stop()` returns `Mono<Void>` and closes the connection while cancelling in-flight requests. You must subscribe to or compose this publisher into the shutdown pipeline; merely calling `client.stop()` and ignoring the Mono does not wait for shutdown to complete. In a Spring application, manage the client as a singleton bean and close it during lifecycle shutdown. Do not create a new client for each message or method call.

If the client reconnects after a network drop, running subscriptions may have been terminated. Reopening the connection does not guarantee automatically resuming the exact previous stream position. Re-subscribe to operations and use a cursor/event ID if resuming is required.

## 12. Testing Subscription Flux

You can use Reactor `StepVerifier` to test how consumers process event streams:

```java
StepVerifier.create(bookEventService.eventsFor("book-1"))
        .expectNextMatches(event ->
                event.book().id().equals("book-1"))
        .expectNextMatches(event ->
                event.book().status().equals("AVAILABLE"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

The example above tests a publisher exposed by a service. To test that `retrieveSubscription` integrates properly with the transport, write an integration test with a GraphQL server exposing a Subscription endpoint and a real client:

1. Start the WebSocket or SSE server in the test.
2. Create a `WebSocketGraphQlClient` or `HttpGraphQlClient`.
3. Subscribe using `retrieveSubscription`.
4. Trigger a mutation or server-side event publisher.
5. Use `StepVerifier` to assert the client receives the expected events.
6. Cancel the Flux and verify the server receives cancellation/complete.
7. Test server errors and transport disconnects separately.

Do not use `Thread.sleep` to wait for events in tests. Use `StepVerifier`, bounded timeouts, and synchronization signals for reliable tests.

## 13. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `retrieveSubscription` receives no events | Client transport does not support streaming or server has not enabled Subscription transport | Use compatible HTTP SSE, WebSocket, or RSocket |
| Error when using `HttpSyncGraphQlClient` | Blocking HTTP client does not support Subscription streams | Switch to `HttpGraphQlClient` with SSE or WebSocket |
| `FieldAccessException` while decoding | Wrong path, alias, or field returned an error | Check response path; use `executeSubscription()` if full response is needed |
| DTO fails to decode | Selection set and Java type do not match | Fix field selection or DTO |
| Flux does not start | No subscriber attached | Subscribe or return the Flux to the framework to consume |
| Server does not stop stream after client leaves | Consumer did not cancel or server resource did not handle cancellation | Dispose the Disposable/Flux and check publisher cleanup |
| Subscription terminates with `SubscriptionErrorException` | Server sent an error message | Inspect GraphQL errors; retry only if recoverable |
| `WebSocketDisconnectedException` | Connection was lost | Handle transport error, reconnect with limits, and re-subscribe |
| Missing events after reconnect | Subscription recreated from current point | Use event IDs/cursors and a resume/replay mechanism |
| Too many WebSocket connections created | Creating client instances repeatedly | Use one shared client per server |
| Credentials not recognized | Server expects a different handshake header or connection-init payload | Align authentication with the WebSocket server |
| Test hangs waiting for events | Missing timeout or publisher not emitting signals | Use StepVerifier with a timeout and cleanup |

## 14. Principles for using retrieveSubscription

- Choose a streaming-capable transport: HTTP SSE, WebSocket, or RSocket.
- Write operations using `subscription` and pass properly typed variables.
- Select the exact field path beneath `data` in `retrieveSubscription(path)`.
- Use `toEntity` for a single object or `toEntityList` for a list in each event.
- Use `executeSubscription()` when you need to read the full response, GraphQL errors, or null fields.
- Handle `SubscriptionErrorException` and `GraphQlTransportException` separately.
- Retry with bounded limits and filter error types; do not unconditionally retry business errors.
- Cancel the Flux when the stream is no longer needed to free server resources.
- Use one shared `WebSocketGraphQlClient`/`RSocketGraphQlClient` per server.
- Manage client lifecycle and credential rotation.
- Use event IDs/cursors if the application needs resume or protection against missed events after reconnect.
- Test events, errors, cancellation, and disconnects with `StepVerifier` and integration tests.

## 15. Practice exercise

Build a client that receives book update notifications:

1. Declare the Subscription `bookUpdated(bookId: ID!)` and type `BookEvent` on the server.
2. Create a `WebSocketGraphQlClient` pointing to the server endpoint.
3. Write a GraphQL document with variable `$bookId`.
4. Call `retrieveSubscription("bookUpdated").toEntity(BookEvent.class)`.
5. Consume the Flux and print the event ID and book status.
6. Try passing an operation name and multiple variables.
7. Cancel the Flux after five events and verify the server stops the Subscription.
8. Try `executeSubscription()` to read responses alongside GraphQL errors.
9. Simulate the server emitting a Subscription error and handle `SubscriptionErrorException`.
10. Disconnect WebSocket and handle `WebSocketDisconnectedException`.
11. Add bounded retry only for transport errors.
12. Design an event ID so the consumer can resynchronize after reconnecting.
13. Write StepVerifier tests for the event stream, errors, and cancellation.

After completing the exercise, you should understand how `retrieveSubscription` decodes each response event into a Flux, how to choose the right transport, manage stream lifecycles, and distinguish GraphQL errors from connection errors.

## 16. References

- [Spring for GraphQL — Client: Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — GraphQlClient.RequestSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [Spring for GraphQL — RetrieveSubscriptionSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RetrieveSubscriptionSpec.html)
- [Spring for GraphQL — WebSocketGraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketGraphQlClient.html)
- [Spring for GraphQL — SubscriptionErrorException API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SubscriptionErrorException.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)

Method signatures and transport behavior may vary across Spring for GraphQL versions. Check the reference documentation/Javadoc matching the dependency managed by Spring Boot, especially when upgrading the client or WebSocket protocol.
