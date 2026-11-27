# GraphQlTransportException

## 1. What is `GraphQlTransportException`?

Spring for GraphQL provides `GraphQlClient` to send GraphQL operations over HTTP, WebSocket, or RSocket. The client builds a request, transmits it over the transport, receives the response, and decodes the data by field path or Java type.

During that process, an error may occur before the server returns a valid GraphQL response. Examples include connection refused, DNS resolution failure, timeouts, WebSocket closure, read/write I/O errors, or request encoding / response decoding failures. Spring for GraphQL uses `GraphQlTransportException` to represent errors raised by the transport or to wrap exceptions thrown by a transport implementation.

The class is in the package:

```java
import org.springframework.graphql.client.GraphQlTransportException;
```

`GraphQlTransportException` is an unchecked exception extending `GraphQlClientException`. It retains the failed request via `getRequest()` and preserves the underlying exception in `cause` if supplied by the transport.

## 2. Distinguishing transport errors and GraphQL response errors

Not every error returned from a GraphQL server is a `GraphQlTransportException`. Distinguish communication-layer errors from errors represented inside a GraphQL response:

| Error type | Example | How the client typically receives it |
| --- | --- | --- |
| Transport failure | DNS, connection refused, timeout, closed socket, I/O error | `GraphQlTransportException` or a subclass |
| Transport encode/decode error | Unable to serialize request or decode response/protocol message | Transport may fail with an exception wrapped into `GraphQlTransportException` |
| GraphQL execution error | Resolver throws an exception, or validation/authorization returned in the GraphQL response | `ClientGraphQlResponse` contains `errors`, potentially alongside partial `data` |
| Field access error | Field path does not exist or field is null with errors when using `retrieve(...)` | `FieldAccessException` |
| Java type decode mismatch | Response field exists but cannot be converted to target Java type | `GraphQlClientException` |

Example where the server returns a valid response containing an error on one field:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Unable to load book title",
      "path": ["book", "title"]
    }
  ]
}
```

This is still a GraphQL response. The transport completed sending and receiving data; the error lies in GraphQL execution results. The client can use `execute()` to inspect `isValid()`, `getErrors()`, and the returned data.

Conversely, if the server cannot be reached or the WebSocket drops before a response arrives, the client has no GraphQL response to parse. In that case, the error is emitted as a transport exception.

## 3. Position in the GraphQL client exception hierarchy

The main exception hierarchy has this structure:

```text
GraphQlClientException
├── FieldAccessException
└── GraphQlTransportException
    ├── SubscriptionErrorException
    └── WebSocketDisconnectedException
```

Meaning:

- `GraphQlClientException`: base class for errors raised by `GraphQlClient`.
- `FieldAccessException`: error accessing or decoding a field from an invalid response, null field, or field with errors.
- `GraphQlTransportException`: error from the transport or an exception wrapped from a transport implementation.
- `SubscriptionErrorException`: Subscription terminated because the server sent a WebSocket message of type `error`.
- `WebSocketDisconnectedException`: WebSocket connection closed or lost while a request/Subscription was active.

Because the two specialized WebSocket exceptions extend `GraphQlTransportException`, you can catch the superclass for general handling. If different policies are needed for Subscription errors versus disconnections, catch the specific subclasses first.

## 4. Constructors and readable data

`GraphQlTransportException` has two constructors:

```java
public GraphQlTransportException(Throwable cause, GraphQlRequest request)

public GraphQlTransportException(
    String message,
    Throwable cause,
    GraphQlRequest request)
```

The first constructor generates a default message. The second allows specifying a custom message. Both take:

- `cause`: underlying exception from the transport, which may be null.
- `request`: the GraphQL request that failed at the transport layer.

Key methods:

| Method | Source | Purpose |
| --- | --- | --- |
| `getRequest()` | Inherited from `GraphQlClientException` | Gets the request that failed |
| `getCause()` | `Throwable` | Gets the directly wrapped exception |
| `getRootCause()` | `NestedRuntimeException` | Gets the deepest root cause if any |
| `getMostSpecificCause()` | `NestedRuntimeException` | Gets the most specific cause; returns the exception itself if there is no cause |
| `getMessage()` | `Throwable` | Reads the diagnostic message |

`GraphQlTransportException` does not expose a generic `getStatusCode()`. HTTP status, WebSocket close status, or transport-specific details must be read from a subclass, cause, or the corresponding transport API.

`getRequest()` returns a `GraphQlRequest`, which can identify the document, operation name, variables, and extensions. Be careful when logging requests, as variables may contain access tokens, personal data, or sensitive business information.

## 5. Situations that commonly raise transport exceptions

Depending on the transport, errors can arise at different stages:

**HTTP:**

- Hostname cannot be resolved or TCP connection cannot be established.
- TLS handshake fails or certificate is invalid.
- Request times out or connection is reset.
- Error writing request body or reading response body.
- Response cannot be decoded with configured codecs.

**WebSocket:**

- Unable to open WebSocket connection.
- Connection closes while an operation is running.
- Protocol/session initialization fails.
- Server or proxy drops the connection.

**RSocket:**

- Unable to establish or maintain a session.
- Connection drops while a request is executing.
- Error in the request/response or streaming interaction layer.

`GraphQlTransportException` is a general abstraction. Specific exceptions and causes depend on the transport implementation, such as WebClient, RestClient, WebSocket client, or RSocket requester. Do not rely solely on the message to determine the cause; inspect the cause and the transport in use.

## 6. Handling transport exceptions with `HttpGraphQlClient`

`HttpGraphQlClient` uses Spring `WebClient` and executes non-blockingly. Operations return `Mono`, so transport exceptions can be handled using Reactor operators.

Creating the client:

```java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
    .baseUrl("https://api.example.com/graphql")
    .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
    .build();
```

Executing a query and logging transport errors:

```java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.core.publisher.Mono;

Mono<Book> book = graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book")
    .toEntity(Book.class)
    .doOnError(GraphQlTransportException.class, exception -> {
        log.warn("GraphQL transport failed", exception);
    });
```

`doOnError` only observes the error and does not recover the stream. If you want to map the error to an application exception or return a fallback, use `onErrorMap` or `onErrorResume` per the service contract.

Example translating a transport error into a domain error at the integration layer:

```java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.core.publisher.Mono;

return graphQlClient.document(document)
    .retrieve("book")
    .toEntity(Book.class)
    .onErrorMap(
        GraphQlTransportException.class,
        exception -> new CatalogUnavailableException(
            "Catalog service is unavailable", exception)
    );
```

Do not convert every `GraphQlClient` exception into a transport error. `FieldAccessException` or decoding errors have different handling and may affect only a single field in the response.

## 7. Handling with `HttpSyncGraphQlClient`

`HttpSyncGraphQlClient` uses Spring `RestClient` and has a blocking execution chain. In this case, exceptions are thrown directly when calling `executeSync()` or `retrieveSync(...)`.

```java
import org.springframework.graphql.GraphQlRequest;
import org.springframework.graphql.client.GraphQlTransportException;
import org.springframework.graphql.client.HttpSyncGraphQlClient;
import org.springframework.web.client.RestClient;

RestClient restClient = RestClient.create("https://api.example.com/graphql");
HttpSyncGraphQlClient graphQlClient = HttpSyncGraphQlClient.create(restClient);
```

Service methods can catch the error as follows:

```java
public Book findBook(String id) {
try {
    Book book = graphQlClient.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", id)
        .retrieveSync("book")
        .toEntity(Book.class);

    return book;
}
catch (GraphQlTransportException exception) {
    GraphQlRequest failedRequest = exception.getRequest();
    Throwable rootCause = exception.getMostSpecificCause();

    log.error("Cannot reach GraphQL service for operation {}",
        failedRequest.getOperationName(), rootCause);
    throw new CatalogUnavailableException(
        "Catalog service is unavailable", exception);
}
}
```

With a blocking client, `try/catch` is the natural way to handle errors. There is no need to convert the entire call to Reactor just to catch exceptions.

## 8. `SubscriptionErrorException`: server terminates Subscription with an error

`SubscriptionErrorException` is a subclass of `GraphQlTransportException`. It is created when a WebSocket Subscription receives an `error` message from the server. The list of GraphQL errors in the message is available via `getErrors()`.

Handling example:

```java
import org.springframework.graphql.client.SubscriptionErrorException;
import reactor.core.publisher.Flux;

Flux<Book> events = graphQlClient.document("""
        subscription BookAdded {
            bookAdded {
                id
                title
            }
        }
        """)
    .retrieveSubscription("bookAdded")
    .toEntity(Book.class)
    .doOnError(SubscriptionErrorException.class, exception -> {
        exception.getErrors().forEach(error ->
            log.warn("Subscription error: {}", error.getMessage())
        );
    });
```

This is an error actively sent by the server per protocol to terminate the operation. Causes may include an invalid operation, insufficient permissions, business errors, or a subscription resolver failure. Do not automatically retry all `SubscriptionErrorException` instances; inspect `getErrors()` to decide whether retrying is viable or whether the request/permissions must be fixed.

## 9. `WebSocketDisconnectedException`: connection lost

`WebSocketDisconnectedException` is another subclass of `GraphQlTransportException`. It is emitted when the WebSocket connection closes or drops while a request or Subscription is running.

Besides the inherited `getRequest()`, this exception provides:

```java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import org.springframework.web.socket.CloseStatus;

try {
    // Execute request via WebSocketGraphQlClient.
}
catch (WebSocketDisconnectedException exception) {
    CloseStatus closeStatus = exception.getCloseStatus();
    log.warn("WebSocket closed: {}", closeStatus);
}
```

`getCloseStatus()` returns the `CloseStatus` used to close the WebSocket session. This is useful when distinguishing normal closure, server/proxy closure, or protocol errors.

Example:

```java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;

Flux<Book> events = graphQlClient.document(subscriptionDocument)
    .retrieveSubscription("bookAdded")
    .toEntity(Book.class)
    .doOnError(WebSocketDisconnectedException.class, exception -> {
        log.warn(
            "GraphQL WebSocket disconnected: {}",
            exception.getCloseStatus()
        );
    });
```

When the connection drops, active requests or Subscriptions on that connection may fail with errors. `WebSocketGraphQlClient` can re-establish the connection for the next request; that does not mean an in-flight operation resumes from the exact last received event.

## 10. Distinguishing `FieldAccessException` and `GraphQlTransportException`

Both exceptions extend `GraphQlClientException`, but their causes differ:

```text
GraphQlClientException
├── FieldAccessException       // reading a field from the response failed
└── GraphQlTransportException  // communication with the transport failed
```

For example, `retrieve("book")` can emit `FieldAccessException` when:

- The `book` path does not exist in the response.
- The `book` value is null and the field has GraphQL errors.
- The response is invalid for the requested decoding operation.

`FieldAccessException` provides `getResponse()` and `getField()` to read the response and the failing field. If the field exists but cannot be decoded into the target Java type, the client may throw a regular `GraphQlClientException`.

Example handling field access separately:

```java
import org.springframework.graphql.client.ClientResponseField;
import org.springframework.graphql.client.FieldAccessException;
import reactor.core.publisher.Mono;

return graphQlClient.document(document)
    .retrieve("book")
    .toEntity(Book.class)
    .onErrorResume(FieldAccessException.class, exception -> {
        ClientResponseField field = exception.getField();
        log.warn("Cannot access GraphQL field: {}", field);
        return Mono.empty();
    });
```

Do not use `onErrorResume(GraphQlClientException.class, ...)` to return a generic fallback for all cases without classifying the error. Doing so can hide connection errors, data errors, and decoding errors behind the same empty result.

## 11. When the full response is needed, use `execute()`

`retrieve(path)` is a shortcut to access a single field and decode it to a Java type. When you need to distinguish responses with no data, errors on one field, or valid null values, use `execute()`.

```java
import java.util.Optional;
import org.springframework.graphql.client.ClientResponseField;
import reactor.core.publisher.Mono;

Mono<Optional<Book>> book = graphQlClient.document(document)
    .variable("id", "book-42")
    .execute()
    .map(response -> {
        if (!response.isValid()) {
            log.warn("GraphQL returned errors: {}", response.getErrors());
        }

        ClientResponseField field = response.field("book");
        Book value = field.toEntity(Book.class);
        return Optional.ofNullable(value);
    });
```

`toEntity` returns `null` if the field is null without errors; if the field is null in an invalid response or has field errors, it throws `FieldAccessException`. `Mono` cannot emit a `null` value, so use `Optional` or a dedicated result type to represent missing data.

Errors in `response.getErrors()` do not automatically mean the transport failed. The response may still contain partial `data` that needs to be processed by business logic.

## 12. Retrying: when should you retry?

Not every transport exception is safe to retry. Evaluate the cause, operation type, and idempotency of the request.

| Scenario | Retry? | Reason |
| --- | --- | --- |
| Query encounters a transient connection error | Possibly | Queries normally produce no side effects, though attempts and duration must be bounded |
| Query timeout | Conditionally | Server might still be processing; retries may duplicate load |
| Mutation loses connection after sending | Not automatically | Server may have committed the mutation while the response was lost |
| `SubscriptionErrorException` from validation/authorization | Usually no | Resending the same operation will not fix the cause |
| `WebSocketDisconnectedException` | Can re-subscribe | Connection can recover, though events during the interruption may be lost |
| Decode error due to wrong Java type | No | Needs fixing the DTO or response mapping |

For operations with side effects, implement an idempotency key or server-side deduplication before enabling retries. Otherwise, the client might create duplicate orders, payments, or other mutations.

## 13. Retrying a Subscription after WebSocket disconnection

Spring for GraphQL allows using Reactor `retry` to restart a Subscription after the transport disconnects. Example capping at three retries with exponential backoff:

```java
import java.time.Duration;
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

Flux<Book> events = graphQlClient.document(subscriptionDocument)
    .retrieveSubscription("bookAdded")
    .toEntity(Book.class)
    .retryWhen(
        Retry.backoff(3, Duration.ofSeconds(1))
            .filter(WebSocketDisconnectedException.class::isInstance)
    );
```

When retrying, the client registers the operation again. This is a new Subscription; there is no guarantee the server replays events that occurred while the connection was down. If business logic cannot lose events, the schema should support cursors/sequence IDs, `after`, or `lastEventId`, and the server needs an event store or replay-capable broker.

Never configure infinite retries without backoff, limits, or a stop condition. A struggling server can be further overloaded if thousands of clients continuously reconnect.

## 14. Handling transport errors in the service layer

An integration service should translate technical exceptions into an error contract appropriate for the rest of the application, while preserving the cause for diagnostics.

Example:

```java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.core.publisher.Mono;

public Mono<Book> loadBook(String id) {
    return graphQlClient.documentName("bookById")
        .variable("id", id)
        .retrieve("book")
        .toEntity(Book.class)
        .onErrorMap(
            GraphQlTransportException.class,
            exception -> new RemoteCatalogException(
                "Catalog transport failed", exception)
        );
}
```

The controller or API layer can translate `RemoteCatalogException` into an application business error. Do not expose raw stack traces, internal hosts, query variables, or credentials to end clients.

If a fallback is required, clearly verify whether the fallback value is valid for business logic. For example, a recommendations list might allow an empty fallback; inventory levels or payment outcomes usually should not pretend to be empty when the source system is unreachable.

## 15. Logging and observability

When logging transport exceptions, capture enough detail for diagnostics without leaking request data.

Recommended fields to record:

- Target service name or configured transport.
- Operation name or persisted operation ID.
- Specific exception type.
- Root cause class and sanitized message.
- Timestamp, duration, and retry count.
- WebSocket close status if it is a `WebSocketDisconnectedException`.
- Error code/path from `SubscriptionErrorException.getErrors()` if applicable.

Avoid logging full `GraphQlRequest` objects, variables, or authorization headers. To correlate requests, use a correlation ID or trace ID instead of printing entire payloads.

Useful metrics include transport failure counts by type, timeout rates, reconnection counts, terminated Subscriptions, and retries used. Do not attach raw queries or sensitive user IDs as metric tags, as they can cause high cardinality and leak information.

## 16. Testing `GraphQlTransportException` handling

Test three layers of behavior separately:

1. **Error classification:** transport failures are recognized as `GraphQlTransportException`; field failures are recognized as `FieldAccessException`.
2. **Recovery policy:** queries retry within bounds; mutations are not unintentionally retried; Subscriptions retry only permitted error types.
3. **Diagnostic information:** the request is retained in the exception, the cause is preserved, and subclass close statuses/errors are read properly.

For unit tests of a service, you can mock the transport or `GraphQlClient` to return `Mono.error(...)`/`Flux.error(...)`, then use Reactor `StepVerifier` to verify the exception is mapped or retried the expected number of times.

For integration tests, use an HTTP test server or WebSocket test server to reproduce scenarios:

- Server is not listening or closes the connection.
- Server delays the response beyond the client timeout.
- Response body is malformed.
- WebSocket closes while a Subscription is active.
- Server sends an `error` message for a Subscription.
- Server returns a valid response containing GraphQL `errors` and partial `data`.

The last two cases are especially important: a Subscription `error` message produces `SubscriptionErrorException`, whereas a regular GraphQL response containing `errors` can still be read via `ClientGraphQlResponse`.

## 17. Common issues

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Catching `GraphQlTransportException` does not trigger | Actual error is `FieldAccessException` or response contains GraphQL errors | Check response and exception hierarchy |
| Query has `errors` without a transport exception | Server returned a valid GraphQL response with execution errors | Use `execute()` and inspect `getErrors()` |
| Cannot tell which request failed | Did not inspect `getRequest()` | Log safe operation name/ID from the request |
| Root cause is missing | Only logged the parent exception message | Inspect `getCause()` or `getMostSpecificCause()` |
| Lost HTTP status information | Only inspected `GraphQlTransportException` | Inspect the specific cause from the HTTP transport |
| Subscription stops without reconnecting | Flux terminated with `WebSocketDisconnectedException` | Use retry with backoff if business logic allows |
| Subscription misses events after retry | Client starts a new operation, server does not replay old events | Use cursors/sequences and an event store or replay broker |
| Mutation executed twice | Retried after timeout even though server committed the first attempt | Use an idempotency key or deduplication |
| Continuous retries overload server | Missing limits or backoff | Use bounded retries, backoff, and jitter |
| Fallback masks system outage | Every transport error replaced with empty data | Fall back only when business logic permits and record degraded state |

## 18. Checklist for handling transport exceptions

- [ ] Distinguish transport failures from GraphQL response errors.
- [ ] Understand that `GraphQlTransportException` extends `GraphQlClientException`.
- [ ] Recognize `FieldAccessException` as a separate exception branch.
- [ ] Read `getRequest()` to identify the failing request.
- [ ] Preserve `cause` and use `getMostSpecificCause()` for diagnostics.
- [ ] Catch `SubscriptionErrorException` separately when reading GraphQL errors is needed.
- [ ] Catch `WebSocketDisconnectedException` separately when reading close status is needed.
- [ ] Use `execute()` when analyzing responses with partial data and errors.
- [ ] Do not blindly retry every transport exception.
- [ ] Do not retry Mutations without ensuring idempotency.
- [ ] Retry Subscriptions with bounds, backoff, and an event replay strategy.
- [ ] Do not log tokens, sensitive variables, or entire requests.
- [ ] Test connection failures, timeouts, protocol errors, Subscription errors, and partial GraphQL responses.

## Conclusion

`GraphQlTransportException` is the client-side exception used for errors raised by `GraphQlTransport` or exceptions wrapped from transport implementations. It extends `GraphQlClientException`, retains the request via `getRequest()`, and preserves the cause for diagnostics. Two key subclasses are `SubscriptionErrorException` for WebSocket Subscriptions ending with an `error` message, and `WebSocketDisconnectedException` when the connection drops while a request is active.

Do not confuse transport exceptions with GraphQL errors inside the response or field access errors. For Queries/Mutations, use `execute()` when partial data and `errors` need to be read; with `retrieve()`, handle `FieldAccessException` separately. For Subscriptions, distinguish server-sent errors from dropped connections. Retries are only safe when the cause is recoverable and the operation is idempotent; in particular, re-subscribing can drop events unless the server supports replay. Preserve the cause, log sanitized diagnostics without sensitive data, and test each error category so the client recovers properly.

## References

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — `GraphQlTransportException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlTransportException.html)
- [Spring for GraphQL — `GraphQlClientException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClientException.html)
- [Spring for GraphQL — `FieldAccessException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/FieldAccessException.html)
- [Spring for GraphQL — `SubscriptionErrorException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SubscriptionErrorException.html)
- [Spring for GraphQL — `WebSocketDisconnectedException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketDisconnectedException.html)
- [Spring for GraphQL — `GraphQlTransport` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlTransport.html)
