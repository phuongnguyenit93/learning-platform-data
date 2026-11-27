# HTTP status for transport errors in Spring for GraphQL

GraphQL is designed to be independent of HTTP, yet most Spring for GraphQL applications still receive requests over HTTP. Therefore, an error can be expressed in two different places: the HTTP status of the transport and the `errors` field in the GraphQL response.

HTTP status describes the outcome of processing a request at the HTTP/transport layer—for example, an unreadable request body, missing authentication, an unsupported media type, or a server timeout. GraphQL `errors` describe issues during parsing, validation, or operation execution. These two layers are related, but do not replace each other.

In Spring for GraphQL, pay special attention to the media type the client sends in the `Accept` header. `application/json` preserves legacy compatibility behavior; `application/graphql-response+json` allows the server to use HTTP 4xx for certain pre-execution GraphQL request errors. Once a request passes validation, Spring for GraphQL 2.1.0 documentation describes the HTTP status as 200, with execution errors placed in the `errors` field of the response.

## 1. Distinguishing HTTP status and GraphQL errors

A GraphQL request over HTTP goes through several steps:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[HTTP method / headers / body]
    B --> C{Valid transport request?}
    C -->|No| D[HTTP 4xx or 5xx]
    C -->|Yes| E[Parse GraphQL document]
    E --> F{Parse and validation succeeded?}
    F -->|No| G[GraphQL request errors]
    F -->|Yes| H[GraphQL execution]
    H --> I{Did a resolver fail?}
    I -->|No| J[HTTP response + data]
    I -->|Yes| K[HTTP response + data/errors]
~~~

The scenarios can be viewed as follows:

| Error type | Example | Where it typically appears |
| --- | --- | --- |
| HTTP/transport error | Malformed JSON body, unsupported `Content-Type`, missing credentials | HTTP status 4xx/5xx; body may not be a GraphQL response. |
| GraphQL request error | Syntax error in document, nonexistent field, invalid argument | GraphQL response containing `errors`; HTTP status depends on media type and Spring behavior. |
| GraphQL execution error | Resolver fails calling database, data not found, field access denied | GraphQL response containing `errors` and possibly partial `data`; Spring typically returns HTTP 200 after validation. |
| Client/connection error | DNS failure, TLS failure, closed socket | Client does not receive a valid GraphQL response; no HTTP status from the GraphQL handler if no response arrived. |

Example of a query that executes, while one field fails:

~~~json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Unable to load book",
      "path": ["book"]
    }
  ]
}
~~~

This is a GraphQL execution error. With the behavior described in Spring for GraphQL 2.1.0, the HTTP response is still `200 OK` because the GraphQL request passed validation and entered execution.

Conversely, if the request body is not valid JSON, the GraphQL engine has not received an executable GraphQL request. That is an HTTP request decoding error and is typically returned with `HTTP 400 Bad Request`.

## 2. Role of GraphQlHttpHandler

Spring for GraphQL provides `GraphQlHttpHandler` for HTTP transport. There are two variants corresponding to Spring MVC and Spring WebFlux. Both process requests asynchronously; the main difference lies in how the HTTP response is written.

`GraphQlHttpHandler` receives the GraphQL request, passes it through `WebGraphQlHandler`/the interceptor chain, and then to `ExecutionGraphQlService` to run GraphQL Java. The Spring Boot GraphQL starter auto-configures this endpoint in typical applications.

Under default configuration:

- HTTP POST is enabled.
- Request `Content-Type` is `application/json`.
- Request body contains the GraphQL document along with `operationName`, `variables`, and `extensions` if present.
- Preferred response media type is `application/graphql-response+json`.
- Older clients can request `application/json` to receive legacy HTTP compatibility behavior.

An example POST request:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{
  "query": "query FindBook($id: ID!) { book(id: $id) { id title } }",
  "variables": {
    "id": "book-10"
  }
}
~~~

Do not write a custom REST controller to parse the body and invoke GraphQL Java if the application already uses `GraphQlHttpHandler`. The handler already manages content negotiation, request decoding, execution, and response serialization according to Spring for GraphQL integration.

## 3. Effect of Accept and response media type

The `Accept` header tells the server which response formats the client can read. Spring for GraphQL supports two key media types:

| Response media type | Meaning |
| --- | --- |
| application/graphql-response+json | Dedicated media type for GraphQL responses, supporting GraphQL over HTTP behavior. |
| application/json | Traditional media type, retained for compatibility with older clients. |

Clients can send:

~~~http
Accept: application/graphql-response+json, application/json;q=0.9
~~~

This prioritizes the dedicated GraphQL media type while still allowing fallback to `application/json` if an older server or environment does not support the newer media type.

Spring for GraphQL 2.1.0 documentation describes the behavior as follows:

- If the server is unavailable, credentials are missing, or the request body is not valid JSON, the client may receive HTTP 4xx/5xx.
- If `Accept` is `application/graphql-response+json`, a GraphQL document that fails to parse or fails GraphQL engine validation receives HTTP 4xx.
- If `Accept` is `application/json`, the same GraphQL parse/validation error still uses HTTP 200 for legacy compatibility.
- Once a GraphQL request passes validation, the HTTP status is always 200; errors arising during execution are placed in `errors`.

This means two clients sending the exact same invalid GraphQL document with different `Accept` headers can observe different HTTP status codes, even though the GraphQL error in the body is fundamentally the same.

## 4. Common HTTP status codes

The table below distinguishes statuses commonly seen from Spring GraphQL from statuses produced by web servers, security filters, or gateways. Not every status in the table is generated directly by `GraphQlHttpHandler`.

| HTTP status | Meaning | Common scenario |
| --- | --- | --- |
| 200 OK | HTTP exchange succeeded | Query/mutation passed validation; GraphQL `errors` may still be present in the body. |
| 400 Bad Request | Request cannot be read or parsed | Malformed JSON body or invalid HTTP request. |
| 401 Unauthorized | Unauthenticated or invalid credentials | Spring Security blocks the request before GraphQL execution. |
| 403 Forbidden | Authenticated but not permitted to access the endpoint | HTTP-layer security policy rejects the request. |
| 405 Method Not Allowed | HTTP method or operation not allowed via that method | Mutation sent via GET when GET transport is enabled; handler rejects the method and returns an `Allow` header. |
| 406 Not Acceptable | No matching response media type | Handler cannot satisfy the `Accept` header and rejects content negotiation. |
| 408 Request Timeout | GraphQL web request exceeded configured time limit to produce a response | `TimeoutWebGraphQlInterceptor` uses this status by default. |
| 413 Content Too Large | Request body exceeds limit | Web server, reverse proxy, or gateway rejects an oversized body. |
| 415 Unsupported Media Type | Request `Content-Type` is not supported | Client sends `text/plain` instead of `application/json`. |
| 429 Too Many Requests | Client exceeded rate limit | API gateway, filter, or rate limiter rejects the request. |
| 500 Internal Server Error | Server encountered an unhandled error | Infrastructure failure or unhandled exception at the HTTP layer. |
| 503 Service Unavailable | Server temporarily unable to accept requests | Maintenance, load shedding, or unavailable dependency/infrastructure. |

Statuses 401, 403, 413, 429, 500, and 503 are typically determined by the security or web infrastructure layers. Do not assume every resolver error turns into HTTP 500; GraphQL execution errors are normally represented in the response body.

## 5. Request errors and behavior of the two media types

A GraphQL request error happens before the operation starts executing, for example:

- Document cannot be parsed.
- Query references a field that does not exist in the schema.
- Argument or variable does not match the operation definition.
- Target operation cannot be determined when the document contains multiple operations without `operationName`.

Example of an invalid document:

~~~graphql
query {
    unknownBookField
}
~~~

With `Accept: application/graphql-response+json`, Spring for GraphQL 2.1.0 returns HTTP 4xx for this kind of request error. The transport documentation describes the status as being in the 4xx range; exact status codes should be confirmed per error kind and handler version. The GraphQL body may look like:

~~~json
{
  "data": null,
  "errors": [
    {
      "message": "Cannot query field 'unknownBookField' on type 'Query'."
    }
  ]
}
~~~

The response still declares the GraphQL media type:

~~~http
Content-Type: application/graphql-response+json
~~~

The key point from Spring documentation is that this error category uses 4xx with `application/graphql-response+json`.

If the client requests `application/json`, Spring keeps legacy behavior and returns HTTP 200 for GraphQL parse/validation errors:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "data": null,
  "errors": [
    {
      "message": "Cannot query field 'unknownBookField' on type 'Query'."
    }
  ]
}
~~~

The body still contains GraphQL `errors`. Therefore, clients using `application/json` cannot rely solely on HTTP 200 to conclude that an operation was valid or successful.

## 6. Execution errors normally do not change HTTP status

After document parsing and validation succeed, the GraphQL engine begins execution. If a resolver throws an exception, Spring for GraphQL normally places the error into `errors` in the GraphQL response.

Resolver example:

~~~java
@Controller
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public Book book(@Argument("id") String id) {
        return bookService.findById(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }
}
~~~

If the exception is mapped to a GraphQL error, the response may look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/graphql-response+json

{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "Book not found",
      "path": ["book"],
      "extensions": {
        "code": "BOOK_NOT_FOUND"
      }
    }
  ]
}
~~~

HTTP 200 here does not mean every field succeeded. It indicates the HTTP request was processed and GraphQL execution ran. Clients must read both `data` and `errors`.

If the field is nullable, GraphQL can return `null` for the failed field while preserving other fields. If the field or parent is declared Non-Null, null propagation can turn a larger portion of `data` into `null`. This is still an execution error and does not automatically become HTTP 500 under the described Spring behavior.

## 7. Note on the newer GraphQL over HTTP specification

GraphQL over HTTP has a September 2026 edition. This edition recommends status `294 Partial Success` when a GraphQL result contains both `data` and `errors`, while request error results without `data` use an appropriate 4xx or 5xx status.

However, current Spring for GraphQL 2.1.0 documentation states that once a GraphQL request has been successfully validated, the HTTP response status is always 200, even when execution has errors. Therefore:

- Do not assume Spring for GraphQL 2.1 automatically returns 294.
- Verify the behavior of the actual Spring for GraphQL version your application uses.
- If the system must conform to a specific GraphQL over HTTP edition, test the status and response media type against the actual handler.
- Do not arbitrarily turn every execution error into 4xx/5xx just to make HTTP dashboards look REST-like; doing so can mislead clients into treating partial GraphQL results as transport failures.

This difference matters when upgrading frameworks, clients, gateways, or API standards. Spring documentation and the specification edition your system commits to must be cross-checked.

## 8. Authentication and authorization errors at two layers

Distinguish endpoint access permissions from permissions on a specific field or resource.

### Authentication at the HTTP security layer

Spring Security can block requests before the GraphQL engine runs:

- Missing credentials or invalid token: typically `401 Unauthorized`.
- Authenticated user lacking permission to access the endpoint: typically `403 Forbidden`.

In these cases, the client may receive an HTTP error response from the security filter. GraphQL resolvers may never be called.

### Authorization during GraphQL execution

A user may be allowed to access the endpoint, yet not permitted to read a specific field or resource. In that case, the application can enforce permissions in services, method security, or data fetchers.

Example:

~~~java
@QueryMapping
public Book privateBook(@Argument("id") String id, Principal principal) {
    return bookService.findVisibleBook(id, principal.getName())
            .orElseThrow(() -> new AccessDeniedException("Access denied"));
}
~~~

If the exception is handled inside GraphQL execution, the outcome is typically GraphQL `errors` inside an HTTP 200 response per Spring's post-validation behavior. This is field/resource authorization, distinct from a security filter blocking the entire HTTP request.

Do not use HTTP status codes as a substitute for per-field permission checks. A single GraphQL operation can select many fields, where some fields are permitted and others are denied.

## 9. HTTP methods and status when using GET

`GraphQlHttpHandler` enables only POST by default. GET can be enabled if the application genuinely needs it, but both the handler and the route predicate must be configured.

Example:

~~~java
GraphQlHttpHandler httpHandler =
        GraphQlHttpHandler.builder(webGraphQlHandler)
                .httpMethods(HttpMethod.GET, HttpMethod.POST)
                .build();

RequestPredicate predicate =
        GraphQlRequestPredicates.graphQlHttp(
                "/graphql", Set.of(HttpMethod.GET, HttpMethod.POST));
~~~

GET is reserved for safe operations like queries. Mutations must not be executed over GET because GET is expected to have no side effects.

If a client sends a mutation via GET, Spring returns `405 Method Not Allowed` along with an `Allow` header listing the methods accepted by the endpoint.

Before enabling GET, consider:

- Query strings and variables may appear in access logs, browser history, `Referer` headers, and proxies/caches.
- Never send passwords, tokens, or sensitive data in the query string.
- GET is a CORS simple request in many cases; understand cookie and CSRF implications.
- Queries can still consume heavy resources and require rate limits, auditing, and complexity/depth limits.

POST is more suitable for mutations and requests with sensitive variables.

## 10. HTTP timeouts with TimeoutWebGraphQlInterceptor

Spring for GraphQL provides `TimeoutWebGraphQlInterceptor` to bound request processing time at the web transport layer. The constructor taking only a `Duration` uses `HTTP 408 Request Timeout` by default. Overloads allow choosing a different status.

Spring Boot configuration:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.server.TimeoutWebGraphQlInterceptor;

@Configuration(proxyBeanMethods = false)
public class GraphQlTimeoutConfiguration {

    @Bean
    TimeoutWebGraphQlInterceptor timeoutWebGraphQlInterceptor() {
        return new TimeoutWebGraphQlInterceptor(Duration.ofSeconds(5));
    }
}
~~~

To choose a different status for timeouts, use the constructor accepting an `HttpStatus` in supported versions:

Replace the bean in the previous example with the configuration below if you want to use 503; do not register both timeout beans simultaneously for the same handler.

~~~java
@Bean
TimeoutWebGraphQlInterceptor timeoutWithServiceUnavailable() {
    return new TimeoutWebGraphQlInterceptor(
            Duration.ofSeconds(5), HttpStatus.SERVICE_UNAVAILABLE);
}
~~~

This example requires importing `org.springframework.http.HttpStatus`. Choose a status matching your API contract; 408 usually fits a request timeout, while 503 indicates the server is temporarily unable to serve the request.

The timeout interceptor sends a cancellation signal up the chain when time expires. Reactive data fetchers can observe cancellation and stop ongoing work. This avoids continuing to hold resources for a response the client is no longer waiting on.

For streaming responses such as subscriptions, this timeout applies only until the response stream is established. Afterward, configure separate timeouts on the transport handler such as WebSocket or SSE if business rules require them.

`TimeoutWebGraphQlInterceptor` does not replace timeouts on reverse proxies, load balancers, databases, or HTTP clients calling downstream services. Timeouts must be coordinated so gateways do not drop connections before the application handles its own timeout.

## 11. Request-level errors and WebGraphQlInterceptor

Request errors such as parse/validation failures happen before any data fetcher is invoked. Consequently, `DataFetcherExceptionResolver` does not handle these global errors.

Spring for GraphQL allows using `WebGraphQlInterceptor` to observe or transform `ExecutionResult` after the GraphQL engine processes the request:

~~~java
import java.util.List;

import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import reactor.core.publisher.Mono;

class RequestErrorInterceptor implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        return chain.next(request).map(response -> {
            if (response.isValid()) {
                return response;
            }

            List<GraphQLError> errors = response.getErrors().stream()
                    .map(error -> GraphqlErrorBuilder.newError()
                            .message("Invalid GraphQL request")
                            .build())
                    .toList();

            return response.transform(builder ->
                    builder.errors(errors).build());
        });
    }
}
~~~

The example above demonstrates normalizing request errors. In real applications, consider preserving helpful developer details such as error locations or error codes while avoiding exposing sensitive data to clients.

An interceptor transforms the GraphQL `ExecutionResult`; that does not mean it arbitrarily sets the HTTP status. The HTTP status is still governed by the transport handler and media type rules. If you need to change the timeout status, use the timeout interceptor or an appropriate transport mechanism rather than trying to assign an `ErrorType` to a GraphQL error.

## 12. ErrorType is not an HTTP status

Spring for GraphQL has `ErrorType` values such as `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, and `INTERNAL_ERROR`. These are GraphQL error classifications, not `HttpStatus` objects.

Example:

~~~java
GraphqlErrorBuilder.newError()
        .message("You do not have permission to view this book")
        .errorType(ErrorType.FORBIDDEN)
        .build();
~~~

`ErrorType.FORBIDDEN` helps clients understand the error category in the GraphQL response. It does not automatically force `GraphQlHttpHandler` to return HTTP 403 for the entire request.

Similarly, `ErrorType.NOT_FOUND` does not mean HTTP 404. A field that cannot find a resource can return `null` or a GraphQL error inside HTTP 200. HTTP 404 normally describes a nonexistent endpoint or HTTP-layer resource, not every missing GraphQL entity.

## 13. In what order should clients read status and body?

Clients must check HTTP status, `Content-Type`, and the GraphQL response body.

A sensible handling workflow:

1. If there is no HTTP response due to DNS/TLS/socket failure, handle it as a connection error.
2. If the response is 4xx/5xx, inspect `Content-Type` before assuming the body is GraphQL JSON.
3. If `Content-Type` is `application/graphql-response+json`, you can parse the body according to the GraphQL response contract even when status is not 2xx.
4. If `Content-Type` is `application/json`, note that 4xx/5xx errors may come from a gateway, reverse proxy, or security middleware.
5. If the body is a GraphQL response, inspect `errors` and `data`; do not check only HTTP 200.
6. Distinguish retryable errors like timeouts/503 from non-retryable errors like validation, authentication, or forbidden.

HTTP client example:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json;q=0.9

{
  "query": "{ book(id: \"missing\") { id title } }"
}
~~~

Upon receiving a response, the application should inspect:

- Status code: was the request accepted at the HTTP layer?
- `Content-Type`: is the body a GraphQL response?
- `errors`: are there any request or execution errors?
- `data`: is complete or partial data present?
- `extensions`: are there error codes or metadata exposed by the server?

Do not retry every 200 response that contains `errors`. Some errors are permanent business errors like `NOT_FOUND` or `FORBIDDEN`; retrying does not help. Likewise, do not retry every 5xx indefinitely, as that can amplify load when the server is already overloaded.

## 14. Testing HTTP status with WebTestClient

`GraphQlTester` is suited for testing GraphQL execution, but if your goal is to verify HTTP status codes, `Content-Type`, and HTTP headers, test through the HTTP handler. With Spring WebFlux, use `WebTestClient`; with Spring MVC, use `MockMvc` or an appropriately configured `WebTestClient`.

Example testing that an execution error still returns HTTP 200:

~~~java
@Test
void executionErrorIsReturnedInGraphQlBody() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.parseMediaType(
                    "application/graphql-response+json"))
            .bodyValue(Map.of(
                    "query",
                    "{ book(id: \"missing\") { id title } }"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.parseMediaType(
                            "application/graphql-response+json"))
            .expectBody()
            .jsonPath("$.errors").exists();
}
~~~

Example testing a GraphQL validation error with the newer media type:

~~~java
@Test
void invalidDocumentUsesClientErrorWithGraphQlResponseJson() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.parseMediaType(
                    "application/graphql-response+json"))
            .bodyValue(Map.of("query", "{ unknownBookField }"))
            .exchange()
            .expectStatus().is4xxClientError()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.parseMediaType(
                            "application/graphql-response+json"))
            .expectBody()
            .jsonPath("$.errors").exists();
}
~~~

Example testing legacy behavior:

~~~java
@Test
void invalidDocumentWithLegacyJsonUsesOkStatus() {
    webTestClient.post()
            .uri("/graphql")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("query", "{ unknownBookField }"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.errors").exists();
}
~~~

These tests assume the `/graphql` endpoint, `WebTestClient`, and schema are configured; the `book` query is executable and `unknownBookField` is invalid. The exact 4xx status for request errors should be verified against your Spring for GraphQL version.

Additionally, include tests for:

- Malformed JSON request body returning 400.
- Unsupported `Content-Type` returning 415.
- Endpoint rejecting credentials returning 401/403 per security policy.
- GET mutation returning 405 with an `Allow` header when GET is enabled.
- Timeout interceptor returning 408 by default.
- Query execution where one field fails still returning HTTP 200 per Spring 2.1 behavior.
- Incompatible `Accept` header handled properly according to content negotiation.
- Reverse proxy or gateway not altering `Content-Type` or status of GraphQL responses incorrectly.

## 15. Common errors

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Seeing HTTP 200 while query has `errors` | GraphQL execution error placed in body | Read `errors` and `data` instead of only checking status. |
| Older client gets 200 for an invalid document | Client requests `application/json` per legacy behavior | Prefer `application/graphql-response+json` if supported by client. |
| Client expects GraphQL JSON on 4xx but gets HTML | Gateway/security middleware returns an error before the GraphQL handler | Check `Content-Type` and response source before parsing. |
| Resolver throws an error, but no HTTP 500 appears | Execution errors do not automatically convert to HTTP 5xx | Handle GraphQL errors in the body per contract. |
| `ErrorType.FORBIDDEN` yet HTTP is still 200 | `ErrorType` is a GraphQL classification, not `HttpStatus` | Separate field authorization from endpoint-level security. |
| Timeout does not return the expected status | `TimeoutWebGraphQlInterceptor` not configured or proxy timeout triggers first | Configure interceptor and align timeouts across layers. |
| Mutation over GET is rejected | GET is a safe method and must not execute mutations | Use POST for mutations. |
| Client retries endlessly | Not distinguishing transport, request, and business errors | Retry only transient errors, limit attempts, and use backoff. |
| `GraphQlTester` test passes, but HTTP status is wrong | Test only verifies execution, not transport | Use `WebTestClient` or `MockMvc` for HTTP behavior. |

## 16. Checklist for designing HTTP status in GraphQL

1. Distinguish transport errors, GraphQL request errors, and GraphQL execution errors.
2. Use POST with `Content-Type: application/json` for default requests.
3. Send `Accept: application/graphql-response+json` when supported by clients.
4. Keep `application/json` when legacy client compatibility is needed.
5. Read HTTP status, `Content-Type`, `data`, and `errors` on the client.
6. Use Spring Security for authentication and endpoint-level authorization.
7. Use GraphQL error classifications for field/resource errors; do not confuse `ErrorType` with HTTP status.
8. Configure `TimeoutWebGraphQlInterceptor` when request processing time needs to be bounded.
9. Enable GET only with a clear reason and understanding of query string risks.
10. Do not force every GraphQL execution error into HTTP 4xx/5xx.
11. Test status codes and media types through the actual HTTP handler.
12. Cross-check your Spring for GraphQL version's behavior against the GraphQL over HTTP version your system commits to support.

HTTP status indicates how a request fared at the transport layer; GraphQL `errors` explain problems in the document or during operation execution. Spring for GraphQL uses content negotiation to balance newer behavior with legacy compatibility. When you classify errors properly, configure timeouts and security at the right layers, and test both HTTP status and GraphQL body, clients and observability systems will accurately understand API health.

References:
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Request Execution and Timeout](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [TimeoutWebGraphQlInterceptor API](https://docs.spring.io/spring-graphql/docs/1.4.x/api/org/springframework/graphql/server/TimeoutWebGraphQlInterceptor.html)
- [GraphQL over HTTP — September 2026](https://http-spec.graphql.org/September2026/)
