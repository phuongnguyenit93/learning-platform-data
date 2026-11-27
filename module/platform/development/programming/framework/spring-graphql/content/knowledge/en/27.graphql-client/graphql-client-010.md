# Client error handling

A GraphQL client cannot simply inspect the HTTP status code and conclude whether a request succeeded or failed. GraphQL can return data alongside errors in a single response: one field fails while other fields still have data. Conversely, a request can fail before receiving a GraphQL response due to DNS, TLS, timeouts, HTTP transport, or protocol errors.

With Spring for GraphQL, GraphQlClient provides two common handling approaches: using execute() to receive the full ClientGraphQlResponse and decide how to handle data/errors yourself, or using retrieve(path) to extract a specific field and receive an error if that field cannot be accessed. Choosing the right approach helps the client retain partial data, classify errors consistently, and retry safely.

## 1. Distinguishing GraphQL errors and transport errors

This is the most important distinction when designing a client:

| Error type | When it occurs | Example | How to handle |
| --- | --- | --- | --- |
| GraphQL request error | Server received the request but could not execute the document | Parse error, validation error, variable coercion error | Fix the document or variables; do not blindly retry the same request |
| GraphQL execution error | A field resolver failed during execution | NOT_FOUND, FORBIDDEN, downstream failure on one field | Read errors, path, extensions; partial data may still be usable |
| Transport error | Client did not receive a valid GraphQL response | DNS, TLS, connection reset, timeout, WebSocket close | Classify the root cause; consider retrying if the operation is safe |
| HTTP/protocol error | Transport returned an unexpected status or payload | 401, 403, 413, 429, 502, malformed response body | Handle by status, authentication, rate limit, or server configuration |
| Client-side mapping error | Response received but cannot convert to Java types | Wrong DTO type, incompatible data | Fix schema/DTO or mapping; do not retry network calls |

A GraphQL execution error usually lives inside response errors and does not necessarily transition the client's Mono/CompletableFuture into an error state. Meanwhile, connection errors flow through the error channel of the reactive publisher.

For example, the server returns a valid HTTP response with:

~~~json
{
  "data": {
    "bookById": null,
    "latestBooks": [
      { "id": "book-01", "title": "Spring in Action" }
    ]
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["bookById"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

The client received a response. This is not a DNS or timeout error; the client must decide whether to display the latest books list even though bookById failed.

## 2. Creating GraphQlClient

Spring for GraphQL provides GraphQlClient as a unified API across transports. For HTTP, you can use HttpGraphQlClient backed by WebClient:

~~~java
@Configuration
public class GraphQlClientConfiguration {

    @Bean
    HttpGraphQlClient catalogGraphQlClient(WebClient.Builder builder) {
        WebClient webClient = builder
            .baseUrl("https://catalog.example.com/graphql")
            .build();

        return HttpGraphQlClient.builder(webClient).build();
    }
}
~~~

An application can also use WebSocketGraphQlClient for subscriptions or RSocketGraphQlClient when communicating over RSocket. Transport configuration differs, while building operations and reading GraphQL responses via GraphQlClient share the same model.

Configure base URLs, TLS, connection pools, timeouts, authentication, and tracing at the transport/client configuration layer. Do not create a new client per resolver or per request if the client can be safely reused as a shared bean.

## 3. Two ways to read responses: execute and retrieve

GraphQlClient has two API styles:

| API | Purpose | Error behavior |
| --- | --- | --- |
| execute() | Receives the full ClientGraphQlResponse | GraphQL errors stay inside the response for the application to inspect |
| retrieve("path") | Extracts one field from the response by path | May throw FieldAccessException if that field has associated errors |

Use execute() when the client needs partial data, multiple independent fields, or wants to classify all GraphQL errors itself. Use retrieve(path) when only one field is needed and you want processing to stop if that specific field cannot be accessed.

Example using retrieve:

~~~java
public Mono<Book> findBook(String id) {
    return graphQlClient.document("""
            query BookById($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", id)
        .retrieve("bookById")
        .toEntity(Book.class);
}
~~~

retrieve("bookById") focuses on the requested field. If that field has a GraphQL error, the client may receive FieldAccessException; an error on an unrelated field does not necessarily cause the retrieved field to fail. If you need to inspect all errors or keep partial data, use execute() instead of only retrieving a single field.

## 4. Reading the full ClientGraphQlResponse

With execute(), the client can check getErrors(), extract data, and branch on extensions.code:

~~~java
public Mono<BookLookupResult> findBookAndLatestBooks(String id) {
    return graphQlClient.document("""
            query BookLookup($id: ID!) {
                bookById(id: $id) {
                    id
                    title
                }
                latestBooks {
                    id
                    title
                }
            }
            """)
        .variable("id", id)
        .execute()
        .map(response -> {
            List<ResponseError> errors = response.getErrors();

            Object bookValue = response.field("bookById").getValue();
            Object latestValue = response.field("latestBooks").getValue();

            Book book = bookValue == null
                ? null
                : objectMapper.convertValue(bookValue, Book.class);
            List<Book> latestBooks = objectMapper.convertValue(
                latestValue, new TypeReference<List<Book>>() {});

            return new BookLookupResult(book, latestBooks, errors);
        });
}
~~~

This example illustrates extracting raw field values and converting them into DTOs. Declare ObjectMapper and the corresponding types in your application. For responses with multiple errors, retain the error list rather than looking only at isValid() or ignoring getErrors().

ClientGraphQlResponse provides overall response details, including data, errors, and extensions. response.field("...") accesses a field by response path. When using execute(), GraphQL errors are response data; they do not automatically turn into exceptions in the reactive chain.

Avoid throwing an exception on every error if the application wants to display partial data. For example, a dashboard page can still render the profile even if the orders widget fails. Preserve both the successful data and the errors attached to their respective fields.

## 5. Field paths, aliases, and list indices

A GraphQL error includes a path identifying the failing field's location in the response. Paths use response keys, meaning aliases if the client specified aliases:

~~~graphql
query {
    featured: bookById(id: "missing") {
        id
        title
    }
    recent: latestBooks {
        id
        title
    }
}
~~~

If featured fails, the path can be ["featured"]. For nested fields, the path can be ["recent", 2, "author", "name"]. Integer indices represent element positions inside lists.

The client should use paths to attach errors to the right UI section or log the exact field. Do not infer paths solely from schema field names, as aliases and nested selections can alter response paths.

## 6. Classifying errors with extensions.code

Messages are written for humans and may change across languages. Clients should rely on stable codes in extensions.code:

~~~json
{
  "message": "The requested book could not be found",
  "path": ["bookById"],
  "extensions": {
    "code": "BOOK_NOT_FOUND",
    "category": "NOT_FOUND"
  }
}
~~~

A client-side enum avoids scattered string comparisons:

~~~java
public enum ApiErrorCode {
    BOOK_NOT_FOUND,
    FORBIDDEN,
    UNAUTHENTICATED,
    VALIDATION_FAILED,
    RATE_LIMITED,
    INTERNAL_ERROR,
    UNKNOWN
}
~~~

The conversion function should tolerate unknown codes:

~~~java
public ApiErrorCode parseCode(ResponseError error) {
    Object rawCode = error.getExtensions().get("code");
    if (!(rawCode instanceof String code)) {
        return ApiErrorCode.UNKNOWN;
    }

    try {
        return ApiErrorCode.valueOf(code);
    }
    catch (IllegalArgumentException ex) {
        return ApiErrorCode.UNKNOWN;
    }
}
~~~

Never let a newly introduced error code from the server crash the client. When a code is unknown, retain a safe message if display is needed, record telemetry, and use a general fallback.

Do not parse messages looking for keywords like "not found" or "forbidden". Messages can be translated or reworded without changing semantics.

## 7. Field errors and partial data

An operation can contain multiple independent fields. When one field fails, the client must decide how to use the rest:

~~~java
return graphQlClient.document(DASHBOARD_QUERY)
    .execute()
    .map(response -> {
        DashboardView view = mapAvailableData(response);
        List<ClientFieldError> errors = response.getErrors().stream()
            .map(this::toClientFieldError)
            .toList();

        return new DashboardResult(view, errors);
    });
~~~

mapAvailableData must check for nulls and field availability before converting to DTOs. GraphQL nullability can propagate null upward to parent fields; an error on a non-null nested field can turn the entire parent object into null. Clients should never assume a nested object always exists merely because the query requested that field.

Common UI strategies:

- Retain stale data and show a refresh-failed indicator.
- Display the successful data sections and mark the failing widget.
- For authorization errors, hide the denied section and show an appropriate notice.
- For operation-wide errors such as parse/validation, display a general request error and discard incomplete data.

Do not turn every null into "not found". Null can result from a nullable field, a resolver legitimately returning null, an execution error, or null propagation. Inspect errors and paths to distinguish them.

## 8. Handling FieldAccessException when using retrieve

retrieve(path) is a convenient shortcut, but when the field has associated errors, toEntity can throw FieldAccessException. Catch this exception to map it to an application client exception:

~~~java
public Mono<Book> findBook(String id) {
    return graphQlClient.document(BOOK_QUERY)
        .variable("id", id)
        .retrieve("bookById")
        .toEntity(Book.class)
        .onErrorMap(FieldAccessException.class, ex ->
            new RemoteBookLookupException(
                "Could not read book from catalog", ex));
}
~~~

When you need to distinguish BOOK_NOT_FOUND, FORBIDDEN, and other errors, read the response errors available on the exception according to your Spring for GraphQL version's API, or use execute() to inspect them directly. Do not collapse every FieldAccessException into NOT_FOUND, as a field can fail for many reasons.

FieldAccessException is an error accessing a field in a GraphQL response. It differs from transport exceptions: the server may have returned a valid response containing field errors.

## 9. Handling transport exceptions in Reactor

With a reactive client, connection or protocol errors travel through the Mono/Flux error channel. You can use onErrorMap, onErrorResume, doOnError, and retryWhen:

~~~java
public Mono<ClientGraphQlResponse> executeQuery(String id) {
    return graphQlClient.document(BOOK_QUERY)
        .variable("id", id)
        .execute()
        .doOnError(error ->
            log.warn("Catalog GraphQL transport failed", error))
        .onErrorMap(GraphQlTransportException.class, error ->
            new CatalogUnavailableException(
                "Catalog service is unavailable", error));
}
~~~

Specific transport exception names and subtypes depend on the transport implementation and library version. Besides GraphQL transport exceptions, WebClient can emit its own HTTP or network exceptions. Classify based on the actual exception types in your stack rather than catching every RuntimeException.

doOnError is only appropriate for side effects such as logging/metrics. onErrorMap transforms the error type; onErrorResume replaces the error with another publisher. Only use a fallback if the alternative result makes business sense:

~~~java
return recommendationClient.loadForBook(bookId)
    .onErrorResume(CatalogUnavailableException.class, error -> {
        log.info("Recommendations unavailable; using empty section");
        return Mono.just(List.of());
    });
~~~

An empty fallback may fit an optional recommendation widget. Do not use it for mandatory data, authorization failures, or mutations with side effects.

## 10. Do not confuse GraphQL errors with reactive onError

The two snippets below have different semantics:

~~~java
// GraphQL errors are inside ClientGraphQlResponse.
graphQlClient.document(BOOK_QUERY)
    .execute()
    .doOnNext(response -> {
        if (!response.getErrors().isEmpty()) {
            log.warn("GraphQL execution returned field errors");
        }
    });

// Transport or client execution failure flows through reactive onError.
graphQlClient.document(BOOK_QUERY)
    .execute()
    .doOnError(error ->
        log.error("Could not obtain GraphQL response", error));
~~~

If you only add onErrorResume, the client may fail to handle GraphQL errors inside the response. Conversely, if you only check getErrors(), the client may miss timeouts or connection failures because there is no response to inspect.

A clean way to organize this is separating two layers:

1. The transport layer translates network/protocol failures into typed client errors.
2. The GraphQL response mapper analyzes data/errors and maps error codes according to the contract.

## 11. Safe retries

Retries can help recover from transient failures, but retrying every error is dangerous. Distinguish carefully:

| Scenario | Retry? | Reason |
| --- | --- | --- |
| Transient DNS, connection reset | Possibly | Request may not have reached the server or was interrupted |
| Timeout on a read-only query | Possibly, bounded | Queries should have no side effects under GraphQL semantics |
| HTTP 429 | Possibly | Respect Retry-After and backoff |
| HTTP 502/503/504 | Possibly | Transient upstream failure |
| GraphQL validation error | No | The same document/variables will continue failing |
| FORBIDDEN/UNAUTHENTICATED | Do not retry blindly | Requires changing credentials or permissions |
| BOOK_NOT_FOUND | Usually no | Immediate retry will not make the resource appear |
| Mutation timeout after sending request | Do not retry arbitrarily | Server may have executed the side effect while the response was lost |

Example bounded retry for transient transport errors:

~~~java
return graphQlClient.document(BOOK_QUERY)
    .variable("id", id)
    .execute()
    .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .filter(this::isTransientTransportFailure));
~~~

isTransientTransportFailure must check specific failure types such as timeouts, connection resets, or transient HTTP statuses. Do not retry all exceptions and do not retry GraphQL errors merely because the response contains errors.

For mutations, only retry when an appropriate idempotency mechanism is in place. An idempotency key must be persisted and enforced by the server at the command boundary; merely resending the same GraphQL document does not guarantee the side effect happens only once.

## 12. Timeouts, cancellation, and deadlines

You can set a timeout in the reactive pipeline:

~~~java
return graphQlClient.document(BOOK_QUERY)
    .variable("id", id)
    .execute()
    .timeout(Duration.ofSeconds(3));
~~~

A timeout on the publisher limits how long the client waits for a result. It does not guarantee the server stopped its resolvers or rolled back in-progress work. Configure timeouts on the HTTP/WebSocket client, proxies, and downstream dependencies; the server also needs appropriate deadlines and cancellation propagation.

When a client cancels a subscription or disposes a request, the transport may abort reading the response. That does not mean an already-sent mutation will be safely cancelled. For write operations, design idempotency, command status tracking, and post-timeout result querying.

Do not apply a single overly short timeout across all transports. Fast read queries, long-running mutations, and WebSocket subscriptions have different lifecycles.

## 13. Handling authentication and authorization errors

If a GraphQL response contains UNAUTHENTICATED or FORBIDDEN, the client should handle it according to policy:

- UNAUTHENTICATED: attempt to refresh credentials if supported by the system; otherwise, prompt for re-login.
- FORBIDDEN: inform the user they lack permission and do not retry with the same credentials.
- NOT_FOUND: display a missing state or conceal the resource according to contract.
- VALIDATION_FAILED: bind violations to form fields.
- INTERNAL_ERROR: show a generic message and log the correlation/trace ID for support.

If the HTTP layer returns 401 before GraphQL execution runs, the client may not receive a GraphQL error body. Handle HTTP authentication failures separately at the transport layer.

Do not trigger unbounded or concurrent token refreshes from hundreds of requests. Use a single-flight token refresh mechanism when multiple requests detect an expired token simultaneously; if refreshing fails, stop retrying and require fresh authentication.

## 14. Client error model

Applications usually prefer not to couple UI or domain code directly to ResponseError. You can map GraphQL errors into an internal type:

~~~java
public record ClientGraphQlError(
        String code,
        String message,
        List<Object> path,
        Map<String, Object> extensions) {
}

public record GraphQlCallResult<T>(
        T data,
        List<ClientGraphQlError> errors) {

    public boolean hasErrors() {
        return !errors.isEmpty();
    }
}
~~~

Mapper:

~~~java
private ClientGraphQlError toClientError(ResponseError error) {
    Object code = error.getExtensions().get("code");

    return new ClientGraphQlError(
        code instanceof String value ? value : "UNKNOWN",
        error.getMessage(),
        error.getPath(),
        error.getExtensions());
}
~~~

If extensions might contain data not permitted in logs/UI, filter by an allowlist instead of copying the entire Map. You can keep only standardized code, category, and violations.

Keeping data and errors together in the result lets the presentation layer decide whether to use partial data. For use cases requiring complete success, translate GraphQL errors into a domain exception at an appropriate boundary.

## 15. Logging and observability

When a client encounters errors, logs should distinguish transport failures from GraphQL field errors:

~~~java
log.warn(
    "GraphQL operation returned errors: operation={}, codes={}, correlationId={}",
    operationName, errorCodes, correlationId);
~~~

For transport exceptions, also log the dependency, elapsed time, and exception type. Never log access tokens, cookies, passwords, full variables, or sensitive response data.

Correlation IDs help link client and server logs when propagated via headers per policy. Distributed tracing should use Micrometer Tracing/OpenTelemetry and standard trace context. Do not use correlation IDs as metric labels, as each request creates a unique value, causing high cardinality.

Metrics to track:

- Transport failure counts by dependency and exception category.
- GraphQL execution error counts by operation and error code.
- Latency and timeout rate.
- Retry count and retry exhaustion.
- Subscription disconnects/reconnects and missed event counts if cursors exist.

Do not attach user IDs, emails, or raw resource IDs as metric tags. Use low-cardinality tags and keep detailed data in controlled logs/traces.

## 16. Subscription client errors

With WebSocketGraphQlClient, errors can occur across a long-lived lifecycle:

- Connection fails to establish.
- Authentication or connection initialization is rejected.
- A subscription operation returns a GraphQL error.
- Stream completes normally.
- WebSocket closes or loses connectivity.
- Publisher emits a transport error.

The client must distinguish an error on a single operation from a connection-wide failure. If the connection drops, multiple operations may be affected; reconnecting may require re-subscribing to subscriptions.

When reconnecting, consider:

- Are credentials still valid?
- Is the subscription permitted to re-subscribe?
- Is there a cursor/sequence ID to resume from the last received event?
- Can duplicate events arrive after reconnecting?
- Does the client process events idempotently?

Do not assume reconnecting automatically recovers all missed events accurately. If no events may be dropped, the protocol/application needs a resume cursor, replay window, or state resynchronization after reconnecting.

## 17. Testing client error handling

Test GraphQL response errors and transport failures separately. A test that only simulates HTTP 500 does not prove the client handles partial data or error extensions.

Scenarios to cover:

1. Successful response with no errors.
2. Response with data and a GraphQL field error.
3. Response with a validation error and extensions.code.
4. Unknown error code mapped to UNKNOWN without crashing the client.
5. Retrieving a failing field produces the expected FieldAccessException.
6. Transport timeout mapped to an unavailable error.
7. HTTP 401/403/429 classified according to policy.
8. Query transient failures retried the right number of times.
9. Mutations not automatically retried when post-timeout outcome is unknown.
10. Partial data preserved when permitted by the use case.
11. Error paths containing aliases and list indices handled properly.
12. Missing or null fields in responses mapped safely.
13. Subscription reconnection does not leak credentials and handles duplicates/resume per contract.

You can use a mock HTTP server like MockWebServer or WireMock to return fixture GraphQL responses, error statuses, delays, and connection closes. For WebSocket clients, use an appropriate test server/transport to simulate connection initialization, event streams, and reconnection.

Also verify the outgoing requests: operationName, variables, authorization headers, correlation headers, and content type. Never place real tokens or production data into test fixtures.

## 18. Common issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| onErrorResume does not run when a GraphQL field fails | Error is inside ClientGraphQlResponse.errors | Check getErrors() after execute() |
| Partial data is lost | Throwing an exception for every response containing errors | Retain data and map errors per field |
| Only FieldAccessException is seen | Using retrieve(path) on a failing field | Inspect error details or use execute() |
| Retrying validation errors repeatedly | Failing to distinguish execution errors from transport errors | Retry only transient errors |
| Mutation executed twice | Retrying after timeout without idempotency | Use an idempotency key or disable automatic retries |
| Null treated as NOT_FOUND | Ignoring errors/path/nullability | Inspect response errors and field contract |
| Client crashes when server adds an error code | Enum parsing without fallback | Map unknown codes to UNKNOWN |
| Logs contain sensitive data | Logging raw variables/responses | Allowlist and mask data |
| Subscription loses events after reconnect | No cursor/replay semantics | Design resume tokens or resync |

## 19. Design principles

Clearly separate GraphQL errors in the response from transport/protocol failures on the error channel. Use execute() when partial data is needed and classify errors explicitly; use retrieve(path) when only one field is needed and FieldAccessException is acceptable for failures on that field. Classify using stable extensions.code values rather than parsing messages.

Retry only transient transport errors with bounded attempts and backoff. Never blindly retry validation, authorization, or NOT_FOUND errors; do not retry mutations after timeouts without idempotency. Set timeouts per operation type, recognize that cancellation does not guarantee the server stopped side effects, and manage subscription reconnection with cursors/replay when needed.

Retain partial data when valuable, normalize errors at the client boundary, and log with correlation/trace IDs while never logging credentials or sensitive variables. With Spring for GraphQL, solid client error handling combines GraphQL response semantics, transport behavior, and the application's retry and presentation policies.
