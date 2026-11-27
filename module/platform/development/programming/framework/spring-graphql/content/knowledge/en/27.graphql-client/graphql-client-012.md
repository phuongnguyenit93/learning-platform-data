# `SubscriptionErrorException` in Spring GraphQL Client

When a client subscribes to a GraphQL subscription, results arrive as an asynchronous stream such as `Flux<T>`. The stream may emit multiple events and complete, be cancelled by the client, lose its connection, or terminate with an error sent by the server. Spring for GraphQL represents the case where a subscription terminates with a GraphQL `error` message using `SubscriptionErrorException`.

`SubscriptionErrorException` is a client-side exception in the `org.springframework.graphql.client` package. It carries the list of GraphQL errors that the server sent in the subscription termination message. Understanding this exception helps distinguish server-side business errors from per-event errors, field decoding errors, and connection losses, enabling you to choose the right logging, display, recovery, or re-subscription strategy.

## 1. What is `SubscriptionErrorException`?

`SubscriptionErrorException` is a subclass of `GraphQlTransportException`, used by Spring for GraphQL when a subscription stream terminates due to a GraphQL `error` message from the server. The exception provides the `getErrors()` method to read the GraphQL errors included in that payload.

Inheritance hierarchy:

```text
RuntimeException
       |
       v
NestedRuntimeException
       |
       v
GraphQlClientException
       |
       v
GraphQlTransportException
       |
       v
SubscriptionErrorException
```

Key APIs:

| API | Meaning |
|---|---|
| `getErrors()` | Returns `List<ResponseError>` containing the GraphQL errors from the subscription termination message. |
| `getRequest()` | Inherited from `GraphQlClientException`; returns the GraphQL request that encountered the error. |
| `getMessage()` | Exception message, useful for general logging; should not be used as a stable error code. |
| `getCause()` | Underlying cause if the exception has one. |

This class has existed since Spring for GraphQL 1.0.0. The Javadoc describes it as a WebSocket `GraphQlTransportException` raised when a subscription terminates with an `error` message.

Spring for GraphQL supports multiple streaming transports such as WebSocket, HTTP Server-Sent Events, and RSocket. How end-of-stream errors are represented depends on the transport and protocol; do not assume every transport produces the exact same exception subtype in all situations. The sections below focus on the terminal GraphQL `error` message case represented by `SubscriptionErrorException`.

## 2. When does a subscription raise this exception?

With GraphQL over WebSocket, the client sends a subscription operation and the server begins emitting events. If the server-side publisher terminates with an error, the transport can send a terminal `error` message containing a list of GraphQL errors. The client receives this message and terminates the `Flux` with `SubscriptionErrorException`.

Flow example:

```text
Client                         Server
  |                               |
  |---- subscribe operation ----->|
  |                               |
  |<--------- next event 1 -------|
  |<--------- next event 2 -------|
  |<--------- next event 3 -------|
  |                               |
  |<---- error [GraphQL errors] --|
  |                               |
  v                               |
Flux terminates with
SubscriptionErrorException
```

This is an operation-terminating error. The client receives no further events from that subscription after the `error` message; to continue, address the root cause and create a new subscription if appropriate.

Not every error in an event produces `SubscriptionErrorException`. A `next` response can still contain `data` and field-level `errors`. That case is observed through `ClientGraphQlResponse` or `FieldAccessException` when the client uses the shortcut to decode a field.

## 3. Using `retrieveSubscription`

`retrieveSubscription(path)` is a concise way to extract one field from each subscription response. The return value is a `Flux` that can be decoded into a Java type:

```java
Flux<OrderEvent> events = graphQlClient.document("""
        subscription WatchOrder($orderId: ID!) {
            orderStatusChanged(orderId: $orderId) {
                orderId
                currentStatus
                occurredAt
            }
        }
        """)
    .variable("orderId", "order-01")
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class);
```

`retrieveSubscription` fits when the client only needs one response path and wants Spring to convert each event into a DTO. The `events` stream can end in several ways:

- Completes normally if the subscription finishes normally.
- Emits `SubscriptionErrorException` if the server sends an `error` message terminating the operation.
- Emits `GraphQlTransportException`, such as `WebSocketDisconnectedException`, if the WebSocket connection closes or drops while the subscription is active.
- Emits `FieldAccessException` if the field path being decoded has errors or cannot be accessed in the response.

`retrieveSubscription` is a shortcut. When you need to clearly distinguish request errors, nullable fields, field failures, and errors at other paths, use `executeSubscription()`.

## 4. Reading GraphQL errors with `getErrors()`

Example catching the exception and reading the error list:

```java
import org.springframework.graphql.ResponseError;
import org.springframework.graphql.client.SubscriptionErrorException;

Flux<OrderEvent> events = graphQlClient.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(error -> {
        if (error instanceof SubscriptionErrorException ex) {
            ex.getErrors().forEach(graphQlError ->
                log.warn("Subscription error: message={}, path={}, extensions={}",
                    graphQlError.getMessage(),
                    graphQlError.getPath(),
                    graphQlError.getExtensions())
            );
        }
    });
```

`doOnError` only observes the error; the exception is still propagated downstream to the subscriber. This is usually a good choice when logging, metrics, or tracing are needed while leaving error handling decisions to the caller.

Avoid logging full request variables if they contain tokens, personal information, or sensitive data. `getRequest()` is useful for correlating the exception with the sent request, but select metadata carefully before writing to logs.

## 5. Contents of `ResponseError`

`getErrors()` returns `List<ResponseError>`. Each `ResponseError` provides standard GraphQL error information:

| Method | Content |
|---|---|
| `getMessage()` | Error description intended for developers. |
| `getErrorType()` | Error classification per GraphQL Java if available. |
| `getExtensions()` | Additional metadata, potentially containing server-defined error codes. |
| `getLocations()` | Line/column positions in the GraphQL document if determinable. |
| `getParsedPath()` | List of path segments; fields are `String`, list indices are `Integer`. |
| `getPath()` | Path formatted as a string, e.g., `order.events[2]`. |

Example reading error codes in `extensions`:

```java
private void logSubscriptionErrors(SubscriptionErrorException exception) {
    for (ResponseError error : exception.getErrors()) {
        Object code = error.getExtensions().get("code");

        log.warn("GraphQL subscription failed: code={}, message={}, path={}",
            code, error.getMessage(), error.getPath());
    }
}
```

The server might not send `extensions.code`; therefore, handle the case where the code is absent. Clients should rely on documented error codes rather than parsing the `message` string.

## 6. Distinguishing terminal subscription errors from per-event errors

This is the most important distinction when using the GraphQL client.

**Subscription-terminating error:** the server sends an `error` message ending the operation. `retrieveSubscription` emits `SubscriptionErrorException`; no further events arrive on that stream.

**Field error inside a `next` response:** the server sends a GraphQL execution result that can contain both `data` and `errors`. The subscription can still continue emitting subsequent events. If using `executeSubscription()`, the client can inspect each response. If using `retrieveSubscription(path)`, decoding a field with errors may produce `FieldAccessException`.

Example of an event response with partial data:

```json
{
  "data": {
    "orderStatusChanged": {
      "orderId": "order-01",
      "currentStatus": null
    }
  },
  "errors": [
    {
      "message": "Could not resolve current status",
      "path": ["orderStatusChanged", "currentStatus"],
      "extensions": { "code": "STATUS_LOOKUP_FAILED" }
    }
  ]
}
```

This response is an event result containing a field error. It differs from the terminal `error` message of the subscription protocol.

## 7. Using `executeSubscription()` to inspect each response

When you need to handle partial data or field errors while continuing to receive subsequent events, use `executeSubscription()`:

```java
Flux<ClientGraphQlResponse> responses = graphQlClient
    .document(subscriptionDocument)
    .executeSubscription();
```

Each `ClientGraphQlResponse` element represents an execution result. You can inspect the response and field before decoding:

```java
Flux<OrderEvent> events = graphQlClient
    .document(subscriptionDocument)
    .executeSubscription()
    .handle((response, sink) -> {
        if (!response.isValid()) {
            response.getErrors().forEach(error ->
                log.warn("Subscription response error: {}", error.getMessage())
            );
            sink.error(new IllegalStateException("Subscription request is invalid"));
            return;
        }

        ClientResponseField field = response.field("orderStatusChanged");

        if (field.getValue() == null) {
            if (field.getErrors().isEmpty()) {
                // Null value is valid according to the schema.
                return;
            }

            field.getErrors().forEach(error ->
                log.warn("Event field error: {}", error.getMessage())
            );
            return;
        }

        sink.next(field.toEntity(OrderEvent.class));
    });
```

This snippet illustrates a policy of skipping events with field errors and continuing to receive subsequent events. Applications can choose to emit a domain result containing errors, record metrics, or terminate the stream depending on the client contract. Never silently ignore errors if missing an event could corrupt business state.

Note: `response.isValid()` detects request-level errors; `field.getErrors()` reports errors associated with a field path. A `next` response containing errors does not automatically mean the entire subscription has ended.

## 8. Distinguishing from `FieldAccessException`

`FieldAccessException` is an exception from reading/decoding a field of a GraphQL response. It commonly occurs when:

- The response is invalid.
- The field path does not exist.
- The field is `null` with associated errors.
- There are errors at, above, or below the accessed field path.

The exception provides:

- `getResponse()` to inspect the `ClientGraphQlResponse`.
- `getField()` to inspect the failing `ClientResponseField`.

Meanwhile, `SubscriptionErrorException` indicates that the subscription stream received a terminal `error` message from the server. The two exceptions serve different purposes:

| Exception | When | Readable data |
|---|---|---|
| `SubscriptionErrorException` | Subscription terminates with a protocol error message | `getErrors()`, `getRequest()`. |
| `FieldAccessException` | Shortcut cannot access/decode a field in a response | `getResponse()`, `getField()`. |
| `GraphQlTransportException` | Transport or encoding/decoding error | Request and cause depending on exception type. |

When partial data and field errors must be handled explicitly, prefer `executeSubscription()` over relying solely on `retrieveSubscription(path)`.

## 9. Distinguishing from `WebSocketDisconnectedException`

`WebSocketDisconnectedException` is another `GraphQlTransportException`, emitted when the WebSocket closes while a request or subscription is running. It typically does not carry a list of GraphQL errors from the server; instead, it provides the close status via `getCloseStatus()`.

| Scenario | Typical exception | Handling approach |
|---|---|---|
| Server sends a GraphQL `error` message to end the subscription | `SubscriptionErrorException` | Read `getErrors()`, identify the error, and decide whether to re-subscribe. |
| WebSocket closes or loses connectivity | `WebSocketDisconnectedException` | Check close status, reconnect, and restart the subscription if safe. |
| Field in an event response has an error | `FieldAccessException` when using `retrieveSubscription` | Read response/field or switch to `executeSubscription`. |
| Other GraphQL client error | `GraphQlClientException` or subtype | Check request, cause, and specific error type. |

Do not lump all errors into a single `onErrorResume(GraphQlTransportException.class, ...)` branch and retry unconditionally. `SubscriptionErrorException` and connection loss have different meanings, so their recovery policies also differ.

## 10. Handling the exception while still propagating the error to the caller

When you need to log and then let upper layers decide, use `doOnError`:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(SubscriptionErrorException.class, this::logSubscriptionErrors);
```

Or use a generic callback:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(error -> {
        if (error instanceof SubscriptionErrorException ex) {
            logSubscriptionErrors(ex);
        }
    });
```

`doOnError` does not replace the exception with another value. The final subscriber still receives the error and can display an appropriate status.

## 11. When to use `onErrorResume`?

`onErrorResume` transforms an error into another publisher. Use it only when the application has an explicit fallback policy.

Example of a monitoring screen that accepts ending the stream and showing a disconnected state:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .onErrorResume(SubscriptionErrorException.class, exception -> {
        logSubscriptionErrors(exception);
        return Flux.empty();
    });
```

Here `Flux.empty()` makes the stream complete normally after logging. Only use this if the UI or caller already has a way to distinguish an error-terminated stream from a normal completion, such as separate state/metrics. Otherwise, server errors are masked and the client may mistakenly assume no new events exist.

If recovery is not possible or no safe fallback exists, propagate the exception onward:

```java
.onErrorResume(SubscriptionErrorException.class, exception -> {
    logSubscriptionErrors(exception);
    return Flux.error(exception);
})
```

Do not use `onErrorContinue` as a general way to keep a subscription alive after a terminal error. Once the protocol has terminated the operation, the client must register a new operation if it wants to continue.

## 12. Retrying on disconnection

Spring for GraphQL documents that when a WebSocket connection is closed or lost, the `Flux` can terminate with `WebSocketDisconnectedException`. You can use Reactor `retry` to reconnect and start a new subscription.

Example retrying only disconnect errors with a bounded count:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
        .filter(WebSocketDisconnectedException.class::isInstance));
```

This example does not retry `SubscriptionErrorException`. If the server actively sends a GraphQL error, the application should read the error code and explicitly decide whether the error is recoverable by re-subscribing.

Retrying subscriptions can introduce gaps or duplicate events:

- Events emitted after the last one the client processed but before the connection dropped may not reach the client.
- Upon re-subscribing, the server may replay old events if the source supports replay.
- If the source only emits live events, the client may miss events during the reconnection window.

If business logic cannot afford to lose events, subscriptions should include an event ID, cursor, offset, or resume token. The client stores the last processed position and sends that position back when re-subscribing. Retry only restores connectivity; it does not provide exactly-once delivery or resume semantics on its own.

## 13. Cancellation is not an error

The client can proactively cancel the `Flux` to end a subscription. This is cancellation, not `SubscriptionErrorException`.

Example taking only 10 events:

```java
Flux<OrderEvent> firstTen = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .take(10);
```

After the tenth element, `take(10)` cancels upstream. With GraphQL over WebSocket, the transport sends a `complete` message so the server ends the operation. Cancellation can also occur via `Subscription` inside a `Subscriber` or other cancellation-capable operators.

Do not log cancellation as a system error, and do not auto-reconnect when the user deliberately navigated away or stopped watching.

## 14. Distinguishing client-side exceptions from server-side resolvers

`SubscriptionErrorException` is the exception seen by the GraphQL client. On the server, the origin may be a `@SubscriptionMapping` publisher emitting `onError`.

`DataFetcherExceptionResolver` handles exceptions from the initial data fetcher invocation, but cannot handle errors emitted later from the subscription publisher. Spring for GraphQL provides `SubscriptionExceptionResolver` to translate errors from subscription publishers into a list of `GraphQLError` sent over the transport.

Overall flow:

```text
Server @SubscriptionMapping
          |
          v
     Flux<Event>
          |
          | onError(exception)
          v
SubscriptionExceptionResolver
          |
          | List<GraphQLError>
          v
WebSocket transport sends error message
          |
          v
GraphQlClient receives terminal error
          |
          v
SubscriptionErrorException
          |
          v
client reads getErrors()
```

Example registering an adapter to map a publisher exception into a GraphQL error:

```java
@Bean
SubscriptionExceptionResolver subscriptionExceptionResolver() {
    return SubscriptionExceptionResolverAdapter.forSingleError(exception ->
        GraphqlErrorBuilder.newError()
            .message("Order event stream is temporarily unavailable")
            .extensions(Map.of("code", "ORDER_STREAM_UNAVAILABLE"))
            .build()
    );
}
```

This resolver runs on the server. When the GraphQL error is sent in a terminal WebSocket error message, the client can receive `SubscriptionErrorException` and read `ORDER_STREAM_UNAVAILABLE` from `getErrors()`.

In a Spring Boot application using the GraphQL starter, Boot discovers `SubscriptionExceptionResolver` beans and adds them to `GraphQlSource` to handle publisher errors. If building `GraphQlSource` manually, register resolvers via `GraphQlSource.Builder.subscriptionExceptionResolvers(...)`.

Do not confuse `SubscriptionExceptionResolver` with `SubscriptionErrorException`: one is the server-side error-handling contract, and the other is the client-side exception.

## 15. Testing with `StepVerifier`

Because subscriptions return `Flux`, `StepVerifier` is well suited to verify both normal events and terminal errors.

Example verifying a stream terminating with `SubscriptionErrorException`:

```java
StepVerifier.create(subscriptionEvents)
    .expectNextMatches(event -> event.orderId().equals("order-01"))
    .expectErrorSatisfies(error -> {
        assertThat(error).isInstanceOf(SubscriptionErrorException.class);

        SubscriptionErrorException exception =
            (SubscriptionErrorException) error;

        assertThat(exception.getErrors())
            .anySatisfy(graphQlError ->
                assertThat(graphQlError.getExtensions())
                    .containsEntry("code", "ORDER_STREAM_UNAVAILABLE")
            );
    })
    .verify();
```

This is an integration test example; `subscriptionEvents` must be created from a `WebSocketGraphQlClient` pointing to a test server configured with `SubscriptionExceptionResolver` and a publisher that emits an event then errors. Ensure the subscription is registered before the test emits events to avoid race conditions.

Test separately:

- Publisher completes normally: `Flux` completes with no exception.
- Server sends terminal `error`: client receives `SubscriptionErrorException` and can read the error code.
- WebSocket closes mid-stream: client receives `WebSocketDisconnectedException`.
- Field in a `next` response has an error: `executeSubscription()` still allows checking the response and field errors.
- `retrieveSubscription` encounters a field error: verify `FieldAccessException` along with response/field.
- Client cancels subscription: upstream is cancelled and no spurious errors are raised.
- Retry applies only to permitted error groups, not every `GraphQlTransportException`.

## 16. Notes on handling and logging

`SubscriptionErrorException` contains error messages and extensions from the server. Because this data may originate from external systems or resolvers, treat it as untrusted input:

1. Prefer stable `extensions.code` values for classification; do not rely on free-form messages.
2. Do not expose verbatim internal details or stack traces to end users.
3. Do not log tokens, sensitive variables, or entire GraphQL requests.
4. Attach correlation IDs or safe operation identifiers to correlate client and server logs.
5. Track metrics by error code and transport to detect abnormal error spikes.
6. Cap retry attempts and use backoff to avoid amplifying load when the server is struggling.
7. Distinguish terminal server errors from network errors and intentional cancellations.

## 17. Common mistakes

**Catching `SubscriptionErrorException` as if it were a disconnection error.** This exception carries GraphQL errors from the subscription termination message. Read `getErrors()` before deciding to retry.

**Assuming every field error produces `SubscriptionErrorException`.** A field error in a `next` response may affect only that event. Use `executeSubscription()` to read individual `ClientGraphQlResponse` objects or handle `FieldAccessException` from the shortcut.

**Reading only `getMessage()` and ignoring `getErrors()`.** Error codes, paths, locations, and extensions live inside `ResponseError`; this is critical data for classification.

**Unconditional retries.** Retrying terminal business errors can create an endless subscribe/terminate loop. Only retry error groups known to be transient.

**Swallowing errors with `Flux.empty()`.** The stream appears to finish successfully and the UI layer may not realize the subscription failed. Only use a fallback if separate state indicates error termination.

**Assuming retries will not lose or duplicate events.** Reconnecting can create gaps or duplicate events. Use cursors/offsets if business logic needs replay.

**Confusing cancellation with an error.** A client intentionally cancelling a subscription is normal behavior, not a failure to retry.

**Using `DataFetcherExceptionResolver` for errors emitted after the publisher starts.** Subscription publisher errors require `SubscriptionExceptionResolver` on the server.

## Conclusion

`SubscriptionErrorException` is the Spring GraphQL Client exception raised when a subscription terminates with a GraphQL `error` message from the server. It extends `GraphQlTransportException`, providing `getErrors()` to read `ResponseError` instances and `getRequest()` to correlate with the original request. Distinguish it from `FieldAccessException` on a field in an event response, `WebSocketDisconnectedException` from connection loss, and intentional cancellation. Use `retrieveSubscription` for simple cases, `executeSubscription` when inspecting individual responses, `doOnError` for observation, `onErrorResume` when an explicit fallback exists, and conditional retries for transient connection errors. On the server, use `SubscriptionExceptionResolver` to map publisher errors into GraphQL errors that the client can read via this exception.

## References

- [Spring for GraphQL — Client: Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL API — `SubscriptionErrorException`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SubscriptionErrorException.html)
- [Spring for GraphQL API — `ResponseError`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/ResponseError.html)
- [Spring for GraphQL API — `FieldAccessException`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/FieldAccessException.html)
- [Spring for GraphQL — Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
