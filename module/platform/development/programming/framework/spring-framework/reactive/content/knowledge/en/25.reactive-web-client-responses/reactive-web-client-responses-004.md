# `WebClientResponseException` and error response content in Spring WebFlux

## 1. Goal: reading both status and error content from an external service

When using `WebClient`, not every HTTP response is a success. A service may return `404 Not Found`, `409 Conflict`, `429 Too Many Requests`, or `500 Internal Server Error` accompanied by a body describing the cause. The calling application must decide how to classify the error, extract useful information from the response, and translate it into appropriate behavior for its use case.

Spring WebFlux provides `WebClientResponseException` to hold information from a received HTTP error response. This exception can carry:

- HTTP status code and status text.
- Response headers, such as `Content-Type`, `Retry-After`, `X-Request-Id`.
- Response body as a byte array.
- Body content as a String using the response charset.
- The original request that produced the error response.

With `retrieve()`, 4xx and 5xx responses emit `WebClientResponseException` by default, with subclasses corresponding to several common statuses. You can change this policy with `onStatus(...)`. If you need full control over how to read the body per status, use `exchangeToMono(...)` or `exchangeToFlux(...)`.

This lesson will help you:

1. Understand when `WebClientResponseException` is created and when it is not.
2. Read status, headers, request, and error body.
3. Decode JSON error bodies into DTOs such as `ProblemDetail` or a custom record.
4. Distinguish `retrieve()`, `onStatus(...)`, and `exchangeToMono(...)`.
5. Turn external service HTTP errors into application exceptions/domain results.
6. Handle empty bodies, non-JSON bodies, malformed JSON, and oversized error bodies.
7. Avoid leaking response bodies, connections, credentials, and sensitive data.
8. Test behavior using `MockWebServer`, `StepVerifier`, and JUnit.

## 2. Position of `WebClientResponseException` in the request lifecycle

An outbound request can end in several ways:

```text
WebClient request
       |
       v
HTTP connector sends request
       |
       +---- No HTTP response received
       |          |
       |          v
       |    WebClientRequestException
       |    (DNS, connect, TLS, I/O...)
       |
       v
HTTP response received
       |
       +---- Status 2xx
       |       |
       |       v
       |    Decode response body
       |       |
       |       +---- success -> Mono<T> / Flux<T>
       |       |
       |       +---- decode error -> DecodingException
       |
       +---- Status 4xx / 5xx with retrieve()
               |
               v
        WebClientResponseException
        (status + headers + body + request)
```

Key point: `WebClientResponseException` represents **a received HTTP error response**. It is not a generic exception for every issue when making an HTTP call.

| Scenario | Typical exception | Is there an HTTP status response? |
|---|---|---|
| Server returns 404 and default `retrieve()` is used | `WebClientResponseException.NotFound` | Yes |
| Server returns 429 | `WebClientResponseException.TooManyRequests` | Yes |
| Server returns 500 | `WebClientResponseException.InternalServerError` | Yes |
| DNS lookup fails | `WebClientRequestException` or corresponding connector error | No |
| Unable to connect to host | `WebClientRequestException` or corresponding connector error | No |
| TLS handshake fails | Transport/security error | Usually no |
| 200 response but JSON cannot be decoded | `DecodingException` or corresponding decode error | Has 200 response |
| Reactive pipeline times out | `TimeoutException` or operator/connector timeout error | Not necessarily |

Therefore, when writing retries or error mappings, do not lump everything into one `catch` and assume the server returned 4xx/5xx. You need to know whether the failure occurred at transport, HTTP status, or body decoding.

## 3. Default behavior of `retrieve()`

`retrieve()` is a straightforward way to declare how to read a response:

```java
Mono<Item> item = webClient.get()
        .uri("/items/{id}", "42")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(Item.class);
```

If the response has a success status, WebClient decodes the body into `Item`.

If the response has a 4xx or 5xx status, `retrieve()` creates `WebClientResponseException` by default. Statuses recognized by Spring may use a specific subclass such as:

- `WebClientResponseException.BadRequest` — 400.
- `WebClientResponseException.Unauthorized` — 401.
- `WebClientResponseException.Forbidden` — 403.
- `WebClientResponseException.NotFound` — 404.
- `WebClientResponseException.MethodNotAllowed` — 405.
- `WebClientResponseException.NotAcceptable` — 406.
- `WebClientResponseException.Conflict` — 409.
- `WebClientResponseException.Gone` — 410.
- `WebClientResponseException.UnsupportedMediaType` — 415.
- `WebClientResponseException.UnprocessableEntity` — 422.
- `WebClientResponseException.TooManyRequests` — 429.
- `WebClientResponseException.InternalServerError` — 500.
- `WebClientResponseException.NotImplemented` — 501.
- `WebClientResponseException.BadGateway` — 502.
- `WebClientResponseException.ServiceUnavailable` — 503.
- `WebClientResponseException.GatewayTimeout` — 504.

If a status code has no specialized subclass, Spring may use `WebClientResponseException` or `UnknownHttpStatusCodeException` depending on the status and representation.

### Catching a subclass or catching the parent class?

You can catch 404 specifically:

```java
return catalogClient.find(id)
        .onErrorResume(
                WebClientResponseException.NotFound.class,
                error -> Mono.empty());
```

Or classify via status:

```java
return catalogClient.find(id)
        .onErrorResume(WebClientResponseException.class, error -> {
            if (error.getStatusCode().is4xxClientError()) {
                return Mono.error(new InvalidRemoteRequestException(error));
            }

            if (error.getStatusCode().is5xxServerError()) {
                return Mono.error(new RemoteServiceUnavailableException(error));
            }

            return Mono.error(error);
        });
```

Catch a clear subclass when only one status has distinct behavior. Use the parent class and `getStatusCode()` when you need a shared policy across multiple statuses.

Do not use `getRawStatusCode()` in new code. This API has been deprecated since Spring Framework 6.0; use `getStatusCode()` returning `HttpStatusCode`.

## 4. Information readable from the exception

`WebClientResponseException` holds data from the response collected by WebClient.

| API | Returns | Used to |
|---|---|---|
| `getStatusCode()` | `HttpStatusCode` | Inspect status and classify 4xx/5xx |
| `getStatusText()` | `String` | Read reason phrase/status text if present |
| `getHeaders()` | `HttpHeaders` | Read `Content-Type`, `Retry-After`, trace ID... |
| `getResponseBodyAsByteArray()` | `byte[]` | Retrieve raw body |
| `getResponseBodyAsString()` | `String` | Read body using the response charset |
| `getResponseBodyAsString(Charset)` | `String` | Choose a fallback charset when response omits charset |
| `getResponseBodyAs(Class<T>)` | `T` | Decode error body into a DTO |
| `getResponseBodyAs(ParameterizedTypeReference<T>)` | `T` | Decode generic types like `List<Violation>` |
| `getRequest()` | `HttpRequest` | Inspect method/URI of the original request |
| `getMessage()` | `String` | General exception message |

Example:

```java
.onErrorResume(WebClientResponseException.class, error -> {
    int status = error.getStatusCode().value();
    String contentType = String.valueOf(
            error.getHeaders().getContentType());
    String requestUri = error.getRequest() == null
            ? "unknown"
            : error.getRequest().getURI().toString();

    log.warn(
            "Remote HTTP failure: status={}, contentType={}, uri={}",
            status, contentType, requestUri);

    return Mono.error(error);
});
```

This example logs only metadata. Do not log all headers or the URI if the URL might contain tokens/query secrets. Avoid logging the raw body because error responses may contain emails, account details, access tokens, or personal data.

### Status and headers can be more useful than the message

Some APIs return `Retry-After` during rate limiting or maintenance:

```java
String retryAfter = error.getHeaders().getFirst("Retry-After");
```

Some APIs return a correlation ID:

```java
String remoteTraceId =
        error.getHeaders().getFirst("X-Request-Id");
```

Keep necessary metadata in controlled logs to support cross-service tracing. Do not assume every server includes these headers.

## 5. Reading the error body as String or byte array

### 5.1. Reading as String

The fastest way to inspect error content:

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .bodyToMono(Item.class)
        .onErrorResume(WebClientResponseException.class, error -> {
            String responseBody = error.getResponseBodyAsString();

            log.warn(
                    "Remote status={}, bodyLength={}",
                    error.getStatusCode().value(),
                    responseBody.length());

            return Mono.error(error);
        });
```

`getResponseBodyAsString()` uses the charset declared in the media type if present; otherwise it falls back to UTF-8. There is an overload accepting a fallback charset:

```java
String body = error.getResponseBodyAsString(
        StandardCharsets.ISO_8859_1);
```

Only choose a fallback charset other than UTF-8 when the target API has an explicit contract. Do not guess charsets based on garbled display output.

### 5.2. Reading as byte array

If you need to process binary content or control decoding yourself:

```java
byte[] rawBody = error.getResponseBodyAsByteArray();
```

This can be used when the body is non-text data, or when you need to store filtered response samples for investigation. Set size limits, retention policies, and masking before storing.

### 5.3. Empty body

Not every error response has a body. A 404, 429, or 503 response may have only status and headers.

```java
String body = error.getResponseBodyAsString();

if (body.isBlank()) {
    log.warn("Remote API returned HTTP {} without an error body",
            error.getStatusCode().value());
}
```

Do not call `getResponseBodyAsString()` and assume JSON is always present. Handle empty bodies and non-conforming bodies as normal cases.

## 6. Decoding a JSON error body into a DTO

Many REST APIs return error bodies following RFC 9457 Problem Details or a custom schema.

Example JSON:

```json
{
  "type": "https://api.example.com/problems/item-not-found",
  "title": "Item not found",
  "status": 404,
  "detail": "Item 42 does not exist",
  "code": "ITEM_NOT_FOUND",
  "traceId": "remote-trace-123"
}
```

You can declare a record:

```java
public record ApiProblem(
        String type,
        String title,
        int status,
        String detail,
        String code,
        String traceId) {
}
```

With a `WebClientResponseException` created by WebClient via `retrieve()` or `ClientResponse.createException()`, you can use:

```java
.onErrorResume(WebClientResponseException.class, error -> {
    ApiProblem problem =
            error.getResponseBodyAs(ApiProblem.class);

    if (problem != null) {
        log.warn(
                "Remote problem code={}, status={}",
                problem.code(),
                error.getStatusCode().value());
    }

    return Mono.error(error);
});
```

`getResponseBodyAs(Class<T>)` has been supported since Spring Framework 6.0. WebClient sets a decoder function on exceptions created from a response so the body can be decoded using configured codecs.

If no suitable decoder exists, the API may throw `IllegalStateException`. If the body is malformed or incompatible with the DTO, decoding may throw `DecodingException`. Therefore, only decode into a DTO when you know the service's response media type and schema.

### 6.1. Decoding collections or generic types

With a body like:

```json
{
  "errors": [
    {"field": "name", "code": "required"},
    {"field": "email", "code": "invalid"}
  ]
}
```

You can use records:

```java
public record FieldViolation(String field, String code) {
}

public record ValidationProblem(
        String title,
        int status,
        List<FieldViolation> errors) {
}
```

If the body is a direct collection such as `List<FieldViolation>`, use `ParameterizedTypeReference`:

```java
List<FieldViolation> violations =
        error.getResponseBodyAs(
                new ParameterizedTypeReference<List<FieldViolation>>() {
                });
```

Requires import:

```java
import org.springframework.core.ParameterizedTypeReference;
```

### 6.2. Invalid JSON or JSON not matching the DTO

Do not let a secondary body-decode failure obscure the original HTTP status. You can read the String first, then attempt parsing in a step with fallback:

```java
String raw = error.getResponseBodyAsString();

ApiProblem problem = null;

try {
    problem = objectMapper.readValue(raw, ApiProblem.class);
}
catch (JsonProcessingException ignored) {
    // Keep a length-limited/masked raw body if needed.
}
```

`ObjectMapper` here is the Jackson mapper configured in the application. In production, do not store unbounded raw bodies and do not return the raw body from an external service to your own clients.

### 6.3. Distinguishing remote error bodies from the current application's errors

If application A calls B, and then A returns an error to A's client, you should not forward B's status/body verbatim by default. B might expose service names, stack traces, or internal structure.

Typically you should:

1. Read B's status/body to classify the error.
2. Convert it into application A's exception or error result.
3. Log safely with a correlation ID.
4. Map it to A's public error contract.

## 7. `onStatus(...)`: customizing error response handling

`retrieve().onStatus(...)` lets you declare a status predicate and a function converting `ClientResponse` into a `Mono` that emits an exception.

Conceptual signature:

```java
onStatus(
        Predicate<HttpStatusCode> statusPredicate,
        Function<ClientResponse, Mono<? extends Throwable>> exceptionFunction)
```

Example mapping 404 to an application exception:

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> response.createException()
                        .map(ItemNotFoundException::new))
        .bodyToMono(Item.class);
```

`response.createException()` builds a `WebClientResponseException` with status, headers, body, and original request. The example turns it into `ItemNotFoundException` so the application layer does not depend on Spring's HTTP exception type.

### 7.1. Mapping a JSON error body to a custom exception

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 409,
                response -> response.bodyToMono(ApiProblem.class)
                        .defaultIfEmpty(new ApiProblem(
                                null,
                                "Conflict",
                                409,
                                "The remote resource conflicts with current state",
                                "REMOTE_CONFLICT",
                                null))
                        .map(problem -> new ItemConflictException(
                                problem.code(),
                                problem.detail())))
        .bodyToMono(Item.class);
```

Here the callback consumes the body itself via `bodyToMono(ApiProblem.class)` and then emits an application exception. Because the body was already read in the callback, the same response body cannot be decoded again.

Note: if the JSON body is malformed or the media type is unsupported, a decoding error may replace the intended business exception. If the external service does not guarantee an error schema, build the exception from `response.createException()` to preserve the raw response and decode with fallback elsewhere.

### 7.2. Returning `Mono.empty()` from `onStatus(...)`

If the `onStatus` callback returns `Mono.empty()`, Spring treats that status as **not an error** and continues processing the response through the normal pipeline:

```java
return webClient.get()
        .uri("/optional-items/{id}", id)
        .retrieve()
        .onStatus(
                status -> status.value() == 404,
                response -> Mono.empty())
        .bodyToMono(Item.class);
```

This does not automatically turn 404 into `Mono.empty()` if the response has a body. The response body is still passed to `bodyToMono(Item.class)` and may fail to decode if the body is Problem Details JSON. If you want 404 to reliably become an empty result without reading the body as Item, `exchangeToMono(...)` is usually clearer.

### 7.3. Predicate ordering and scope

You can declare 4xx and 5xx separately:

```java
.retrieve()
.onStatus(
        HttpStatusCode::is4xxClientError,
        response -> response.createException())
.onStatus(
        HttpStatusCode::is5xxServerError,
        response -> response.createException())
.bodyToMono(Item.class);
```

This is only an illustrative example. If your callback returns the same default `WebClientResponseException`, there is no need to redeclare these two handlers. Only use `onStatus` when you actually change the mapping, add domain context, or enforce a different response policy.

Do not create overlapping predicates without understanding which handler applies first. When special statuses like 404 or 429 exist, place specific logic clearly and test it explicitly.

## 8. `exchangeToMono(...)`: deciding how to read the response yourself

`exchangeToMono(...)` gives direct access to `ClientResponse`. It is suitable when the status determines the body type, fallback, or handling strategy.

Example:

```java
Mono<Item> item = webClient.get()
        .uri("/items/{id}", id)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Item.class);
            }

            if (response.statusCode().value() == 404) {
                return response.releaseBody()
                        .then(Mono.<Item>empty());
            }

            return response.createError();
        });
```

Meaning:

- 2xx: decode into `Item`.
- 404: release the body and return `Mono.empty()`.
- Other statuses: `createError()` emits `WebClientResponseException` containing status, headers, body, and request.

### 8.1. The response body must be consumed or released

After the publisher returned by the `exchangeToMono`/`exchangeToFlux` callback completes, WebClient checks the response body. If the body has not been consumed, the framework releases it to prevent memory/connection leaks.

That means the callback must decide how to handle the body right inside itself. Do not return `ClientResponse` outside and expect to read the body after the callback finishes.

Common choices:

- `response.bodyToMono(Type.class)` to decode the body.
- `response.bodyToFlux(Type.class)` to stream multiple objects.
- `response.createException()` or `response.createError()` to create an HTTP error.
- `response.releaseBody()` to discard the body when unneeded.
- `response.toEntity(...)` or `toBodilessEntity()` when status/headers/body are needed via the respective abstraction.

### 8.2. Do not use the legacy `exchange()`

The older `exchange()` API has been deprecated since Spring Framework 5.3 due to memory/connection leak risks if the caller fails to consume or release the body properly. Use `exchangeToMono()` or `exchangeToFlux()`.

### 8.3. When to choose `retrieve()` and when to choose `exchangeToMono()`?

| Need | Suitable API |
|---|---|
| Read body as DTO, 4xx/5xx use default exception | `retrieve()` |
| Map a few statuses to application exceptions | `retrieve().onStatus(...)` |
| Read status first and choose different body types | `exchangeToMono(...)` |
| 404 returns empty, 2xx returns DTO, other statuses emit exception | `exchangeToMono(...)` |
| Handle a stream response by status | `exchangeToFlux(...)` |
| Need only status + headers and no body | `retrieve().toBodilessEntity()` or corresponding API |

## 9. `WebClientResponseException` and other error types

When building an HTTP client for an application service, classify at least the following categories:

| Error category | Example | Common handling |
|---|---|---|
| 4xx from external service | 400, 401, 403, 404, 409, 429 | Check input, credentials, permissions, resource, or rate limit |
| 5xx from external service | 500, 502, 503, 504 | Evaluate retry, circuit breaker, fallback, and alerting |
| Transport error | DNS, connect, TLS, connection reset | Check network, timeouts, DNS, and upstream availability |
| Timeout/cancel | Request exceeds deadline or is cancelled | Adjust timeout, propagate cancellation, avoid infinite retries |
| Response decode | HTTP 200 but JSON fails schema | Check contract/version/codec; do not treat as HTTP error |
| Error body decode | HTTP 404 but body mismatches error DTO | Preserve status and raw body safely; parse with fallback |

### 9.1. Not every 4xx is a retryable error

For example:

- 400: fix the request before resending.
- 401: refresh credentials per auth flow; retry once in a controlled way if appropriate.
- 403: check permissions; retrying usually does not help.
- 404: depending on the use case, return empty or domain not-found.
- 409: resolve conflict or re-read state.
- 429: may retry per `Retry-After` and policy.
- 422: fix data/business logic.

### 9.2. Not every 5xx is safe to retry

GET is generally idempotent under HTTP semantics. POST may have already executed side effects even if the client only saw a timeout or 502. If retrying POST, an idempotency key or deduplication mechanism supported by the target API is required.

Use bounded retries with backoff and jitter; set an overall timeout across the retry chain. Avoid immediate, unbounded retries when the upstream is overloaded.

## 10. Reading error bodies without leaking data

An error response is data sent by another service and should not be trusted by default.

Guidelines:

- Log only diagnostic fields such as status, error code, request ID, and route.
- Do not log `Authorization`, cookies, API keys, access tokens, or raw request/response bodies indiscriminately.
- If storing error bodies is necessary, mask personal data and enforce size/retention limits.
- Do not return raw upstream bodies to external clients without sanitizing content.
- Never expose internal hostnames, stack traces, SQL, filesystem paths, or configuration details in public responses.
- Check `Content-Type` before decoding JSON into a DTO.
- Handle empty bodies, malformed JSON, unexpected media types, and missing charsets.
- Set appropriate codec limits; large error bodies can exceed `maxInMemorySize` when WebClient buffers content to build the exception.

`WebClientResponseException` holds the body as a byte array, so reading error bodies by default can require buffering. It is not a streaming mechanism for large error payloads. Error contracts should be concise, structured, and size-bounded.

### A controlled logging pattern

```java
private void logRemoteFailure(WebClientResponseException error) {
    String requestId =
            error.getHeaders().getFirst("X-Request-Id");

    log.warn(
            "Remote request failed: status={}, requestId={}, method={}",
            error.getStatusCode().value(),
            requestId,
            error.getRequest() == null
                    ? "unknown"
                    : error.getRequest().getMethod());
}
```

Do not include `error.getResponseBodyAsString()` in default logs. If body diagnostics are needed, log only parsed and vetted error codes.

## 11. Designing application exceptions when calling external services

Not every application layer should depend directly on `WebClientResponseException`. You can keep Spring's exception inside the HTTP client adapter and convert it into a business-meaningful exception.

Example:

```java
public final class RemoteCatalogException extends RuntimeException {

    private final HttpStatusCode statusCode;
    private final HttpHeaders responseHeaders;
    private final String responseBody;

    public RemoteCatalogException(WebClientResponseException cause) {
        super("Catalog service returned HTTP "
                + cause.getStatusCode().value(), cause);

        this.statusCode = cause.getStatusCode();
        this.responseHeaders =
                HttpHeaders.readOnlyHttpHeaders(cause.getHeaders());
        this.responseBody = cause.getResponseBodyAsString();
    }

    public HttpStatusCode getStatusCode() {
        return statusCode;
    }

    public HttpHeaders getResponseHeaders() {
        return responseHeaders;
    }

    public String getResponseBody() {
        return responseBody;
    }
}
```

Then map in the client adapter:

```java
return webClient.get()
        .uri("/items/{id}", id)
        .retrieve()
        .onStatus(
                HttpStatusCode::is4xxClientError,
                response -> response.createException()
                        .map(RemoteCatalogException::new))
        .bodyToMono(Item.class);
```

Benefits:

- The application layer gets a stable application exception type.
- The original cause is preserved for investigation.
- Status and headers remain available when needed.
- The adapter can swap WebClient for another HTTP client without rewriting all use cases.

You do not have to store the raw response body in the domain exception. If the body might contain sensitive data, keep only selected error codes and trace IDs.

## 12. Handling specific cases

### 12.1. 404: resource not found

If not found is considered a normal outcome in the use case:

```java
public Mono<Item> findOptional(String id) {
    return webClient.get()
            .uri("/items/{id}", id)
            .exchangeToMono(response -> {
                if (response.statusCode().is2xxSuccessful()) {
                    return response.bodyToMono(Item.class);
                }

                if (response.statusCode().value() == 404) {
                    return response.releaseBody()
                            .then(Mono.<Item>empty());
                }

                return response.createError();
            });
}
```

If 404 is a business error that must be reported outward, keep `WebClientResponseException.NotFound` or map it to `ItemNotFoundException`.

### 12.2. 429: rate limiting and `Retry-After`

```java
return webClient.get()
        .uri("/reports")
        .retrieve()
        .bodyToFlux(Report.class)
        .onErrorResume(
                WebClientResponseException.TooManyRequests.class,
                error -> {
                    String retryAfter =
                            error.getHeaders().getFirst("Retry-After");

                    log.warn("Rate limited; retryAfter={}", retryAfter);
                    return Flux.error(error);
                });
```

`Retry-After` can be a number of seconds or an HTTP date per HTTP semantics. If implementing retries, parse the format properly, cap wait times, and limit total attempts. Never block a thread to wait; use `Mono.delay(...)` or a retry operator with backoff.

### 12.3. 401: expired token

A 401 response may indicate that the access token is no longer valid. If the application uses Spring Security OAuth2 Client, let the authorized client manager/filter manage acquiring or refreshing tokens. Never write an infinite retry loop whenever 401 is received.

If handling manually:
- Only refresh according to a supported authentication flow.
- Ensure the request retries at most once after refresh.
- Never log old/new tokens.
- Never retry requests with side effects without an idempotency guarantee.

### 12.4. 5xx: preserving status and cause

```java
return webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(Inventory.class)
        .onErrorMap(
                WebClientResponseException.class,
                error -> error.getStatusCode().is5xxServerError()
                        ? new InventoryServiceException(error)
                        : error);
```

Only map 5xx to the application exception. 4xx continues propagating so callers can handle input/authorization/not-found separately.

## 13. Runnable Java 17+ project: reading error bodies and mapping WebClient errors

This sample project uses Java 17, Spring Boot 3.3.5, Spring WebFlux, JUnit 5, Reactor Test, and OkHttp MockWebServer. MockWebServer spins up a local HTTP server in tests, allowing controlled responses of 200, 404, 429, or 500 without calling the Internet.

The example demonstrates three behaviors:

1. `find(...)` uses default `retrieve()` and receives `WebClientResponseException`.
2. `findWithMapped4xx(...)` uses `onStatus(...)` to turn 4xx into an application exception, preserving cause/status/headers/body.
3. `findOrEmpty(...)` uses `exchangeToMono(...)` to turn 404 into `Mono.empty()` and create exceptions for other statuses.

### 13.1. Project structure

```text
webclient-error-response/
├── pom.xml
└── src/
    ├── main/java/edu/demo/catalog/
    │   ├── CatalogItem.java
    │   ├── ApiProblem.java
    │   ├── RemoteApiException.java
    │   └── CatalogClient.java
    └── test/java/edu/demo/catalog/
        └── CatalogClientTests.java
```

### 13.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webclient-error-response</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
        <mockwebserver.version>4.12.0</mockwebserver.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>com.squareup.okhttp3</groupId>
            <artifactId>mockwebserver</artifactId>
            <version>${mockwebserver.version}</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 13.3. `CatalogItem.java`

```java
package edu.demo.catalog;

public record CatalogItem(String id, String name) {
}
```

### 13.4. `ApiProblem.java`

```java
package edu.demo.catalog;

public record ApiProblem(
        String type,
        String title,
        int status,
        String detail,
        String code,
        String traceId) {
}
```

This record represents part of the sample API's error contract. In real systems, match the DTO to the called service's schema.

### 13.5. `RemoteApiException.java`

```java
package edu.demo.catalog;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.WebClientResponseException;

public final class RemoteApiException extends RuntimeException {

    private final HttpStatusCode statusCode;
    private final HttpHeaders responseHeaders;
    private final String responseBody;

    public RemoteApiException(WebClientResponseException cause) {
        super(
                "Remote catalog returned HTTP "
                        + cause.getStatusCode().value(),
                cause);

        this.statusCode = cause.getStatusCode();
        this.responseHeaders =
                HttpHeaders.readOnlyHttpHeaders(cause.getHeaders());
        this.responseBody = cause.getResponseBodyAsString();
    }

    public HttpStatusCode getStatusCode() {
        return statusCode;
    }

    public HttpHeaders getResponseHeaders() {
        return responseHeaders;
    }

    public String getResponseBody() {
        return responseBody;
    }
}
```

The application exception holds status, headers, and raw body so the adapter/caller can classify further. In production, you may keep only filtered error codes and trace IDs instead of holding the entire body.

### 13.6. `CatalogClient.java`

```java
package edu.demo.catalog;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient webClient) {
        this.webClient = webClient;
    }

    public Mono<CatalogItem> find(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(CatalogItem.class);
    }

    public Mono<CatalogItem> findWithMapped4xx(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                        HttpStatusCode::is4xxClientError,
                        response -> response.createException()
                                .map(RemoteApiException::new))
                .bodyToMono(CatalogItem.class);
    }

    public Mono<CatalogItem> findOrEmpty(String id) {
        return webClient.get()
                .uri("/items/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToMono(response -> {
                    if (response.statusCode().is2xxSuccessful()) {
                        return response.bodyToMono(CatalogItem.class);
                    }

                    if (response.statusCode().value() == 404) {
                        return response.releaseBody()
                                .then(Mono.<CatalogItem>empty());
                    }

                    return response.createError();
                });
    }
}
```

The three methods demonstrate three different policies:

- `find`: lets `retrieve()` create the default `WebClientResponseException`.
- `findWithMapped4xx`: converts all 4xx responses into `RemoteApiException`, while 5xx continues using `retrieve()` defaults.
- `findOrEmpty`: 404 means no item found; other statuses create an error from `ClientResponse`.

### 13.7. `CatalogClientTests.java`

```java
package edu.demo.catalog;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CatalogClientTests {

    private MockWebServer server;
    private CatalogClient catalogClient;

    @BeforeEach
    void setUp() throws IOException {
        server = new MockWebServer();
        server.start();

        WebClient webClient = WebClient.builder()
                .baseUrl(server.url("/").toString())
                .build();

        catalogClient = new CatalogClient(webClient);
    }

    @AfterEach
    void tearDown() throws IOException {
        server.shutdown();
    }

    @Test
    void successfulResponseIsDecodedToItem() throws Exception {
        server.enqueue(new MockResponse()
                .setResponseCode(200)
                .addHeader("Content-Type", "application/json")
                .setBody("""
                        {"id":"42","name":"Keyboard"}
                        """));

        StepVerifier.create(catalogClient.find("42"))
                .expectNext(new CatalogItem("42", "Keyboard"))
                .verifyComplete();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/items/42", request.getPath());
        assertEquals(
                MediaType.APPLICATION_JSON_VALUE,
                request.getHeader("Accept"));
    }

    @Test
    void defaultRetrieveCreatesNotFoundExceptionWithReadableBody()
            throws Exception {

        String body = """
                {
                  "type": "https://api.example.test/problems/not-found",
                  "title": "Item not found",
                  "status": 404,
                  "detail": "Item 42 does not exist",
                  "code": "ITEM_NOT_FOUND",
                  "traceId": "remote-trace-123"
                }
                """;

        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .addHeader("Content-Type", "application/problem+json")
                .addHeader("X-Request-Id", "request-404")
                .setBody(body));

        StepVerifier.create(catalogClient.find("42"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException exception =
                            assertInstanceOf(
                                    WebClientResponseException.class,
                                    error);

                    assertInstanceOf(
                            WebClientResponseException.NotFound.class,
                            error);

                    assertEquals(
                            404,
                            exception.getStatusCode().value());

                    assertEquals(
                            "request-404",
                            exception.getHeaders()
                                    .getFirst("X-Request-Id"));

                    assertEquals(
                            "GET",
                            exception.getRequest().getMethod().name());

                    assertTrue(
                            exception.getResponseBodyAsString()
                                    .contains("ITEM_NOT_FOUND"));

                    ApiProblem problem =
                            exception.getResponseBodyAs(ApiProblem.class);

                    assertEquals("ITEM_NOT_FOUND", problem.code());
                    assertEquals(404, problem.status());
                    assertEquals("remote-trace-123", problem.traceId());
                })
                .verify();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("/items/42", request.getPath());
    }

    @Test
    void customOnStatusMaps4xxAndPreservesOriginalResponse()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(429)
                .addHeader("Content-Type", "application/problem+json")
                .addHeader("Retry-After", "30")
                .setBody("""
                        {
                          "title": "Rate limited",
                          "status": 429,
                          "detail": "Try again later",
                          "code": "RATE_LIMITED"
                        }
                        """));

        StepVerifier.create(
                        catalogClient.findWithMapped4xx("42"))
                .expectErrorSatisfies(error -> {
                    RemoteApiException remote =
                            assertInstanceOf(
                                    RemoteApiException.class,
                                    error);

                    assertEquals(
                            429,
                            remote.getStatusCode().value());

                    assertEquals(
                            "30",
                            remote.getResponseHeaders()
                                    .getFirst("Retry-After"));

                    assertTrue(
                            remote.getResponseBody()
                                    .contains("RATE_LIMITED"));

                    assertInstanceOf(
                            WebClientResponseException.class,
                            remote.getCause());
                })
                .verify();
    }

    @Test
    void exchangeToMonoTurns404IntoEmptyAndReleasesBody()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(404)
                .addHeader("Content-Type", "application/problem+json")
                .setBody("""
                        {"title":"Not found","status":404}
                        """));

        StepVerifier.create(catalogClient.findOrEmpty("missing"))
                .verifyComplete();

        RecordedRequest request =
                server.takeRequest(2, TimeUnit.SECONDS);

        assertNotNull(request);
        assertEquals("/items/missing", request.getPath());
    }

    @Test
    void serverErrorRemainsWebClientResponseException()
            throws Exception {

        server.enqueue(new MockResponse()
                .setResponseCode(500)
                .addHeader("Content-Type", "text/plain; charset=UTF-8")
                .addHeader("X-Request-Id", "server-failure-500")
                .setBody("database temporarily unavailable"));

        StepVerifier.create(catalogClient.find("42"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException exception =
                            assertInstanceOf(
                                    WebClientResponseException.class,
                                    error);

                    assertInstanceOf(
                            WebClientResponseException.InternalServerError.class,
                            error);

                    assertEquals(
                            500,
                            exception.getStatusCode().value());

                    assertEquals(
                            "database temporarily unavailable",
                            exception.getResponseBodyAsString());

                    assertEquals(
                            "server-failure-500",
                            exception.getHeaders()
                                    .getFirst("X-Request-Id"));
                })
                .verify();
    }
}
```

### 13.8. Running tests

From the directory containing `pom.xml`:

```bash
mvn test
```

The test suite has five test cases:

1. A 200 response is decoded into `CatalogItem`.
2. A 404 response produces `WebClientResponseException.NotFound`; the test reads status, headers, request, body String, and decodes the body into `ApiProblem`.
3. `onStatus` maps 429 to `RemoteApiException`, preserving status, `Retry-After`, body, and original cause.
4. `exchangeToMono` turns 404 into `Mono.empty()` and releases the response body.
5. A 500 response preserves `WebClientResponseException.InternalServerError` along with body and request ID.

Expected output after running Maven:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected result to compare against when running in an environment that can download dependencies. The article does not claim the test suite was executed in the authoring environment.

## 14. Calling the API and reading errors in the application

Example of using the client inside a service:

```java
@Service
public class ItemFacade {

    private final CatalogClient catalogClient;

    public ItemFacade(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    public Mono<ItemView> getItem(String id) {
        return catalogClient.find(id)
                .map(item -> new ItemView(item.id(), item.name()))
                .onErrorMap(
                        WebClientResponseException.NotFound.class,
                        error -> new ItemMissingException(id))
                .onErrorMap(
                        WebClientResponseException.class,
                        error -> error.getStatusCode().is5xxServerError()
                                ? new CatalogUnavailableException(error)
                                : error);
    }
}
```

The service turns 404 into an application-meaningful exception. 5xx errors are converted into `CatalogUnavailableException` so higher layers can decide on fallbacks or error responses. Remaining 4xx errors continue propagating so they can be handled separately.

If you want your application's endpoint to return RFC 9457 `ProblemDetail`, map `ItemMissingException`/`CatalogUnavailableException` at the HTTP boundary using `@RestControllerAdvice`. Do not return the catalog service's raw body to your application's clients without filtering.

## 15. Common mistakes and fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking every WebClient error is `WebClientResponseException` | Misses DNS, TLS, connect, and timeout errors | Distinguish response errors, request/transport errors, and decode errors |
| Reading only `getMessage()` | Fails to extract structured body/headers | Use `getStatusCode()`, `getHeaders()`, `getResponseBodyAsString()` |
| Using `getRawStatusCode()` in new code | Uses a deprecated API | Use `getStatusCode()` |
| Assuming the error body is always JSON | Empty/text/HTML bodies break decoding | Check Content-Type and provide a fallback |
| Decoding error body into a DTO without handling parse errors | `DecodingException` masks original error status | Read raw String first or use `createException()` |
| Using `onStatus` without consuming the body | Response body is not handled as expected | Read body in callback or create exception with `createException()` |
| Returning `Mono.empty()` from `onStatus` thinking the body becomes empty | Downstream still continues decoding response body | Use `exchangeToMono()` and `releaseBody()` for status-as-empty |
| Using legacy `exchange()` | Risk of body/connection leaks | Use `exchangeToMono()`/`exchangeToFlux()` |
| Reading `ClientResponse` after the `exchangeToMono` callback ends | Body may already be released | Decode/consume/release immediately inside callback |
| Logging the entire error body | Leaks PII, tokens, or internal details | Log error code, status, trace ID; mask body |
| Retrying all 4xx/5xx | Pointless retries or side effects | Classify statuses and retry only per semantics |
| Retrying POST without idempotency | Creates duplicate resources or transactions | Use idempotency keys/deduplication contracts |
| Forwarding upstream errors verbatim to external clients | Leaks internal structure and details | Map to the application's error contract |
| Oversized error body | Can exceed `maxInMemorySize` when buffering | Keep error payloads small, set codec limits, stream if truly needed |
| Testing only status codes | Misses wrong headers/body/error mapping | Test status, headers, raw body, typed body, and original request |

## 16. Error response handling checklist

### Classifying errors

- Was an HTTP response received?
- Is the status 4xx, 5xx, or a successful response whose body failed to decode?
- Is it a transport error such as DNS, connect, TLS, or timeout?
- Should 404, 409, 429, or 5xx be handled separately?

### Reading the response

- Is `getStatusCode()` used instead of `getRawStatusCode()`?
- Was `Content-Type` checked before decoding the body?
- Could the body be empty or non-JSON?
- Do you need `getResponseBodyAsString()`, byte array, or a DTO?
- Do you need to read `Retry-After` or a trace ID?
- Is the original request retained when needed for investigation?

### Reactive and resource lifecycle

- Does the `onStatus` callback consume the body or create an exception?
- Does the `exchangeToMono` callback decode/release the body before completing?
- Are `subscribe()` and `block()` avoided in reactive services?
- Do you avoid re-reading the body after it has been consumed/released?
- Is the error payload size bounded?

### Security and retry

- Do logs redact Authorization, cookies, API keys, and PII?
- Is the raw upstream body kept from being returned directly to clients?
- Are retries bounded in attempts, backoff, jitter, and deadline?
- Is the request idempotent or backed by an idempotency key?
- Are 401/403/404/409/429 properly distinguished?

### Testing

- Are 2xx, 404, 429, and 5xx tested?
- Are empty bodies and non-JSON bodies tested?
- Is JSON body decoding into an error DTO tested?
- Are custom `onStatus` and `exchangeToMono` behaviors tested?
- Are request/response headers and body release behavior tested?
- Are transport failures tested separately if the application must retry network errors?

## 17. Self-check exercises

**Exercise 1.** `retrieve().bodyToMono(Item.class)` receives status 404. What is the typical default exception?

**Answer:** `WebClientResponseException.NotFound`, a subclass of `WebClientResponseException`.

**Exercise 2.** Which API is called to read the raw error body as a String?

**Answer:** `getResponseBodyAsString()`. The charset is taken from the media type if available, otherwise defaulting to UTF-8.

**Exercise 3.** Which API is used to retrieve the response body as `ApiProblem` in Spring Framework 6.x?

**Answer:** `getResponseBodyAs(ApiProblem.class)`, provided the exception was created by WebClient with a suitable decoder function and the body is properly formatted.

**Exercise 4.** Does `WebClientResponseException` occur when DNS lookup fails?

**Answer:** No. There is no HTTP response; it is typically `WebClientRequestException` or the corresponding transport error.

**Exercise 5.** What does an `onStatus` callback returning `Mono.empty()` mean?

**Answer:** That status is not treated as an error by `retrieve()`; the response continues through subsequent body extraction. It does not automatically turn the response into `Mono.empty()`.

**Exercise 6.** When should `exchangeToMono()` be used?

**Answer:** When status determines decoding or the outcome, e.g., 2xx decodes a DTO, 404 releases the body and returns empty, and remaining statuses create an error.

**Exercise 7.** Why should you not return the upstream's raw error body to your own clients?

**Answer:** The body may contain stack traces, internal hostnames, PII, or structures that do not belong to the application's public contract.

**Exercise 8.** The server returns 429 with `Retry-After: 30`. Should you retry immediately?

**Answer:** No. Respect Retry-After, limit retries, use backoff and an overall deadline; also ensure the request can be retried safely.

**Exercise 9.** Is a 200 response with a malformed JSON body a `WebClientResponseException`?

**Answer:** No. The status is 2xx; the failure occurs during decoding, typically `DecodingException` or the corresponding codec error.

**Exercise 10.** Why must the body be consumed or released in `exchangeToMono()`?

**Answer:** WebClient automatically releases unconsumed bodies when the callback publisher completes. If you need the content, you must decode/consume it inside the callback; this avoids holding unnecessary buffers and connections.

## 18. Key takeaways

- `WebClientResponseException` stores information from a received HTTP error response: status, headers, body, and request.
- `retrieve()` converts 4xx/5xx into `WebClientResponseException` and status-specific subclasses for common codes by default.
- Use `getStatusCode()`; `getRawStatusCode()` is deprecated.
- `getResponseBodyAsString()` reads the body using the response charset or UTF-8; `getResponseBodyAsByteArray()` retrieves raw bytes.
- `getResponseBodyAs(Class<T>)` and `ParameterizedTypeReference<T>` decode error bodies into DTOs/generic types in Spring Framework 6.x when a suitable decoder exists.
- `onStatus(...)` lets you map HTTP statuses to application exceptions; returning `Mono.empty()` means not treating that status as a default error.
- `exchangeToMono(...)` gives control over decoding/releasing per status; consume or release the body inside the callback.
- `WebClientRequestException`, timeouts, and `DecodingException` are distinct error categories from HTTP response errors.
- Do not log or return sensitive raw bodies; keep only necessary status/error code/trace ID details.
- Retries must depend on status, idempotency, `Retry-After`, backoff, and deadlines.
- Keep error payloads small to avoid buffering past codec limits.

When debugging a failed outbound request, ask in order: **was an HTTP response received; what is the status; was the body read/decoded properly; was the error mapped accurately to the use case; was the response body consumed or released?**

## Official documentation

- Spring Framework 6.2, **`retrieve()` and `onStatus`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-retrieve.html
- Spring Framework 6.2, **`exchangeToMono()` and `exchangeToFlux()`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-exchange.html
- Spring Framework 6.2.19, **`WebClientResponseException` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/WebClientResponseException.html
- Spring Framework 6.2.19, **`ClientResponse` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/client/ClientResponse.html
- Spring Framework 6.2, **WebClient Filters and response body lifecycle**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-filter.html
- Spring Framework 6.2, **WebClient testing**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient/client-testing.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html