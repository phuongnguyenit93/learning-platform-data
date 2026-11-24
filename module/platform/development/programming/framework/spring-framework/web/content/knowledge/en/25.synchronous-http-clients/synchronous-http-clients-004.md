# RestClient: retrieve, exchange, and Reading Status, Headers, and Body in Synchronous HTTP Clients

## 1. Goal: Not Just Reading JSON, but Understanding the Entire HTTP Response

An HTTP client calling a partner API usually needs more than just JSON data. It needs to know whether the request succeeded or failed, the actual status code, caching info, correlation ID, the Location of a newly created resource, and must decide whether to retry.

For example, the server returns:

```http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/products/42
X-Request-ID: req-abc123

{"id":42,"name":"Spring Book"}
```

If you only deserialize the body into a Java object, you can lose the **201 Created** and **Location** signals. Conversely, if you only inspect the status and ignore the body, you can miss business error codes. Spring provides APIs to extract these pieces as needed.

**Direct topic:** `retrieve`, `exchange`, and how to read **status, headers, and body**, within Spring Framework's **synchronous HTTP clients** group.

With **Spring Framework 6.2.x / Spring Boot 3.5.x / Java 17+**, the modern choice for a synchronous client is **`org.springframework.web.client.RestClient`** (fluent API, introduced in Spring Framework 6.1). `RestTemplate` can still be encountered in legacy systems, though its API and method names are not identical to `RestClient`; `WebClient` belongs to the non-blocking/reactive branch and has different return types.

This lesson answers:

1. When should you call `retrieve().body(Type.class)`, `retrieve().toEntity(Type.class)`, or `retrieve().toBodilessEntity()`?
2. How do you read `ResponseEntity#getStatusCode()`, `getHeaders()`, and `getBody()` properly by status?
3. When should you choose `exchange((request, response) -> ...)` to inspect the response yourself?
4. Why does `retrieve()` throw exceptions for 4xx/5xx by default, whereas `exchange()` does not apply status handlers automatically?
5. Does `onStatus(...)` error handling differ from `exchange(...)`?
6. How do you safely read a raw response body stream without letting the stream escape the callback or reading unbounded bytes?
7. How do you configure Spring Boot `RestClient.Builder`, timeouts/request factories, and test with `@RestClientTest` + `MockRestServiceServer`?
8. Why are retry decisions, caching, data security, and handling empty responses part of the HTTP contract?

## 2. Big Picture of HTTP Request and Response

```text
                         Spring application
                                  |
                         RestClient.get/post
                                  |
                    URI + request headers + body
                                  |
                                  v
                  ClientHttpRequestFactory
                      (JDK / Apache / ...)
                                  |
                           HTTP network
                                  |
                                  v
                 HTTP status + headers + bytes
                                  |
                  +---------------+---------------+
                  |                               |
             retrieve()                        exchange(...)
                  |                               |
       error status handlers                   callback receives
       + HttpMessageConverter                  request + response
                  |                               |
          .body(Type)                          manually inspect
          .toEntity(Type)                      status/headers/body
          .toBodilessEntity()                  and return value
                  |                               |
                  +--------------+----------------+
                                 |
                      domain result / exception
```

**A synchronous request can block the calling thread** until networking and body extraction complete. `RestClient` does not turn HTTP calls into non-blocking operations. In Spring MVC Servlet, it can be called on a request worker within an appropriate concurrency and timeout budget. In a Spring WebFlux/Netty event loop, **do not call `RestClient` directly** unless isolated onto a blocking-dedicated scheduler or—better—use reactive `WebClient`.

### 2.1. Underlying Mechanics

`RestClient` uses:

- `ClientHttpRequestFactory`: executes requests over a specific HTTP transport, affecting connections, TLS, timeouts, and pooling.
- `HttpMessageConverter<?>`: encodes Java objects into request bytes or decodes response bytes into `String`, `byte[]`, JSON DTOs, or other types.
- `HttpStatusCode`: represents an HTTP status, including standard and extension codes.
- `HttpHeaders`: represents response headers (multi-value, case-insensitive semantics).
- `ResponseEntity<T>`: wraps **status + headers + body**.
- `RestClientResponseException` and its subclasses: by default represent HTTP error responses on the `retrieve` path.

An HTTP status is not a JSON field. A response may be `204 No Content`, `304 Not Modified`, or an error response carrying no body; code must handle this accurately.

## 3. Creating RestClient: Using the Boot-Provided Builder

In **Spring Boot 3.5**, a project only needs `spring-boot-starter-web` or compatible Spring Web dependencies to get `RestClient`, Jackson for JSON, and an auto-configured `RestClient.Builder`.

Fragment of `build.gradle` in a Spring Initializr-generated project:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`RestClient` can also be used outside an HTTP server if you are just building a scheduled job/CLI app; in that case include the modules needed for the HTTP client and converters without having to start embedded Tomcat. This lesson uses the Boot starter for simple examples and tests.

### 3.1. Spring Boot-Provided Builder

```java
@Service
class CatalogGateway {
    private final RestClient http;

    CatalogGateway(RestClient.Builder builder) {
        this.http = builder
                .baseUrl("https://partner.example.test")
                .defaultHeader("X-Client-App", "catalog-sync")
                .build();
    }
}
```

This is a **class fragment**; `RestClient.Builder` must be imported from `org.springframework.web.client.RestClient`, and the example hostname is not a real API. Injecting the Boot-managed builder ensures you receive Boot's customizations and observability. If you call `RestClient.create()` standalone, you **do not necessarily** receive customizations configured on Boot's builder.

A built `RestClient` can be reused across multiple threads; reuse it rather than creating a new client and connections for each HTTP request. Do not attach a fixed `Authorization` token in default headers if it is user-scoped; per-request tokens must be passed according to the security context without caching or leaking across tenants.

### 3.2. Configuring Base URL and URI Variables

```java
Product product = http.get()
        .uri("/products/{id}", productId)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Product.class);
```

This is a **method fragment**; `Product` and `productId` are application-defined. Spring handles template variables better than string concatenation:

```java
// Do not concatenate user data directly into URI:
String raw = "/products/" + userSuppliedPath;
```

With queries:

```java
http.get()
    .uri(uriBuilder -> uriBuilder
        .path("/products")
        .queryParam("page", 2)
        .queryParam("q", query)
        .build())
    .retrieve()
    .toEntity(String.class);
```

This is a fragment assuming `query` is already declared. When request URLs involve untrusted data, separate path/query values from the base URI; never let users supply hosts/absolute URLs without an SSRF policy.

## 4. `retrieve()`: The Standard Way to Read Responses

Common chain:

```java
Product found = http.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(Product.class);
```

Three steps:

1. `get().uri(...)` prepares the HTTP request; it does not return a body yet.
2. `retrieve()` returns `RestClient.ResponseSpec` to configure how status/body are handled; **`retrieve()` itself does not execute the request**.
3. The **terminal operation** `body(...)`, `toEntity(...)`, or `toBodilessEntity()` triggers the HTTP exchange and extraction.

This critical point prevents an anti-pattern:

```java
http.get().uri("/products/7").retrieve();
// No terminal method called => no HTTP request is sent as expected.
```

If the response body does not matter but the HTTP request still must execute, use `toBodilessEntity()` instead of stopping at `retrieve()`.

### 4.1. `body(Class<T>)`

When you only need the content and do not need to branch on status/headers:

```java
String text = http.get()
        .uri("/health")
        .retrieve()
        .body(String.class);

Product product = http.get()
        .uri("/products/7")
        .retrieve()
        .body(Product.class);

byte[] bytes = http.get()
        .uri("/small-binary")
        .retrieve()
        .body(byte[].class);
```

These are fragments; types and endpoints are illustrative. The converter is selected based on Java type, content type, and dependencies. With an empty body, `body(Type)` **can return null** per its contract, especially on `204 No Content`. Never assume it always returns an object.

`body(byte[].class)` is unsuitable for downloading multi-GB files because it can hold the entire response in RAM. For large data, use streaming extraction via an appropriate API and bound total bytes.

### 4.2. `body(ParameterizedTypeReference<T>)` for Generics

```java
List<Product> products = http.get()
        .uri("/products")
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .body(new ParameterizedTypeReference<
                List<Product>>() {});
```

Unlike `List.class`, `ParameterizedTypeReference<List<Product>>` preserves the **element type** for the JSON converter. Using a raw list can turn elements into `LinkedHashMap`, leading to `ClassCastException` when cast to `Product`.

Do not use `body(new ParameterizedTypeReference<List<Product>>() {})` against an endpoint that can return **millions of elements** if all data is accumulated at once; use pagination, a streaming reader, or page-by-page synchronization.

### 4.3. Do Not Confuse Content-Type with Accept

- `.accept(MediaType.APPLICATION_JSON)` sets the **Accept: application/json** request header, telling the server which response format the client wants.
- `.contentType(MediaType.APPLICATION_JSON)` on POST/PUT/PATCH indicates the **request body** being sent is JSON.
- The server may return 406/415 if no matching representation exists; handling response statuses is the client's responsibility.
- Response `Content-Type` comes from the server and should not be blindly trusted when ingesting untrusted data into the system.

## 5. `retrieve().toEntity(Class<T>)`: Getting Full Status, Headers, and Body

When response metadata is needed:

```java
ResponseEntity<Product> response = http.get()
        .uri("/products/{id}", id)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .toEntity(Product.class);

HttpStatusCode status = response.getStatusCode();
HttpHeaders headers = response.getHeaders();
Product body = response.getBody();
```

From there:

```java
int code = status.value();
MediaType contentType = headers.getContentType();
String requestId = headers.getFirst("X-Request-ID");
String etag = headers.getETag();
URI location = headers.getLocation();
long length = headers.getContentLength();
```

These are **method fragments** for responses with appropriate metadata. Header values can be **null** or absent; `getContentLength()` uses a sentinel value when unknown. Each header has its own semantics (for example, a valid strong ETag includes double quotes); never assume every header is present on an HTTP response.

### 5.1. ResponseEntity Does Not Mean Body Always Exists

```java
ResponseEntity<Void> r = http.delete()
        .uri("/products/{id}", id)
        .retrieve()
        .toBodilessEntity();
```

With a 204 response, `r.getBody()` is null; `r.getStatusCode().value()` is 204. With a 202 response, do not assume processing is already finished just because the request succeeded. With 201, the `Location` header tells the client the new resource's URI.

### 5.2. HEAD and 304

A HEAD request has headers/status but **no HTTP response body**:

```java
ResponseEntity<Void> head = http.head()
        .uri("/products/7")
        .retrieve()
        .toBodilessEntity();

String etag = head.getHeaders().getETag();
```

`304 Not Modified` also carries no representation body per HTTP semantics. When using conditional GET:

```java
ResponseEntity<Product> r = http.get()
        .uri("/products/7")
        .header(HttpHeaders.IF_NONE_MATCH, cachedEtag)
        .retrieve()
        .toEntity(Product.class);
```

`cachedEtag` must be a properly formatted ETag. When the server returns 304, the response body is typically null; the application must use the prior cached value rather than treating it as “missing data” or retrying indefinitely. Caching also involves Cache-Control, Vary, validators, and tenant/auth scoping.

## 6. `toBodilessEntity()`: Executing a Request Without Decoding a Body

Many APIs succeed without needing to read a body:

```java
ResponseEntity<Void> response = http.post()
        .uri("/products")
        .contentType(MediaType.APPLICATION_JSON)
        .body(new CreateProduct("Spring Basics"))
        .retrieve()
        .toBodilessEntity();
```

When the server returns 201 Created:

```java
if (response.getStatusCode().value() == 201) {
    URI location = response.getHeaders().getLocation();
    // Validate expected host/path before following Location.
}
```

**This is a fragment**, assuming a `CreateProduct` record exists in the application. Despite the name `toBodilessEntity`, the HTTP response is still handled/released per the client API; if the server sends a 4xx/5xx error body, the default `retrieve` path **throws an exception** before returning a normal entity to the caller.

### 6.1. Why Not Just Call retrieve?

```java
http.post()
        .uri("/jobs")
        .body(command)
        .retrieve();
```

This only creates a `ResponseSpec` and **does not send the request**. Use `toBodilessEntity()` if you care about status + headers without needing a body.

### 6.2. HTTP Semantics of 201, 202, 204

| Status | Meaning | Headers to Watch |
| --- | --- | --- |
| 200 OK | Request succeeded, usually with a representation | Content-Type, ETag, Cache-Control |
| 201 Created | Resource created | Location, possibly ETag/body |
| 202 Accepted | Accepted for processing, not necessarily complete | Location/status endpoint, Retry-After per contract |
| 204 No Content | Succeeded, no representation body | ETag or other metadata if present |
| 304 Not Modified | Cached representation can be reused | ETag/Cache-Control/Vary |
| 400 Bad Request | Invalid input/protocol | Error response body |
| 401 Unauthorized | Missing/invalid authentication | WWW-Authenticate |
| 403 Forbidden | Authenticated but insufficient permissions | Safe error code |
| 404 Not Found | Resource not found or hidden | Client decides not-found semantics |
| 409 Conflict | State/uniqueness conflict | Stable error code |
| 429 Too Many Requests | Exceeded quota/rate limit | Retry-After if server provides it |
| 500 Internal Server Error | Server error | Correlation ID |
| 503 Service Unavailable | Temporarily out of capacity/downstream unavailable | Retry-After if present |

No single status-code mapping fits every service; rely on the partner's API contract.

## 7. How Does `retrieve()` Handle 4xx/5xx by Default?

In Spring Framework 6.2, `retrieve` throws a subclass of `RestClientException` by default when receiving an HTTP **4xx or 5xx** response. Common status errors include:

- `HttpClientErrorException` for 4xx, potentially specialized subclasses like `HttpClientErrorException.NotFound`.
- `HttpServerErrorException` for 5xx.
- `RestClientResponseException` as the suitable base for reading status/body/headers of an **HTTP error response**.
- `ResourceAccessException` typically wraps I/O/network errors like connect timeout, read timeout, DNS/TLS—**with no HTTP status** if the server never returned an HTTP response.
- `UnknownContentTypeException` can occur when no converter handles the expected representation.
- Jackson conversion/serialization errors may sit in the `RestClientException`/conversion exception hierarchy and should be classified by context.

### 7.1. Catching HTTP Exceptions Properly

```java
try {
    Product product = http.get()
            .uri("/products/{id}", id)
            .retrieve()
            .body(Product.class);
    // Handle product.
} catch (RestClientResponseException ex) {
    int status = ex.getStatusCode().value();
    HttpHeaders headers = ex.getResponseHeaders();
    String message = ex.getResponseBodyAsString(
            StandardCharsets.UTF_8);

    // Only classify/sanitize info to log or return to client.
} catch (ResourceAccessException ex) {
    // I/O failure: may not have received any response/status.
}
```

This is a **fragment** with imports `RestClientResponseException`, `ResourceAccessException`, `StandardCharsets`. `message` contains the raw error response body from an untrusted server; do not display it directly as a public message or log sensitive data in full.

### 7.2. A 404 Response Is an Exception, Not a Normal ResponseEntity

```java
ResponseEntity<Product> r = http.get()
        .uri("/products/999")
        .retrieve()
        .toEntity(Product.class);
```

If the server returns 404, **by default execution never reaches `r.getStatusCode()==404`** because `toEntity` throws an exception. To turn 404 into a domain exception, use `onStatus`. To receive 404 as a **normal value** for multi-status handling, use `exchange`.

### 7.3. Never Catch-All and Return Null

```java
// Anti-pattern:
try {
    return callPartner();
} catch (Exception ignored) {
    return null;
}
```

This turns 401/403/429/503/DNS timeouts all into “product not found”, causing corrupted data, broken retries, and hidden outages. Use typed exceptions/codes, record status metrics, and alert appropriately.

## 8. `onStatus(...)`: Custom Status Handling in retrieve

Each `retrieve()` can attach status-specific handling:

```java
Product value = http.get()
        .uri("/products/{id}", id)
        .retrieve()
        .onStatus(
            status -> status.value() == 404,
            (request, response) -> {
                throw new ProductMissingException(id);
            })
        .body(Product.class);
```

This is a **fragment**; the custom exception is declared in the demo. The handler receives **request and response**, and can inspect HTTP status, headers, and error body if needed. Rather than surfacing raw partner error JSON to users, map it to a safe domain error such as PRODUCT_NOT_FOUND.

### 8.1. Handler Precedence

When multiple status handlers exist, precedence depends on configuration and registration order. Place specific handlers before broad ones, and verify with unit tests for 404/409/429/500.

If default status handlers are configured on `RestClient.Builder`, per-response handlers may run before defaults depending on the Spring 6.2 contract. Never assume “this status handler always runs” if an earlier handler already matched and threw.

### 8.2. onStatus Is Not exchange

`retrieve().onStatus(...)` is right when you only need to change how **errors become exceptions** while still using `body(Class)`/`toEntity(Class)` for success.

`exchange(...)` is right when you need to **branch by status**, inspect headers/raw bytes directly inside the callback, or return different domain result types without letting default 4xx/5xx throwing fire first.

### 8.3. Do Not Collapse Every 4xx into “Not Found”

Avoid:

```java
.onStatus(HttpStatusCode::is4xxClientError,
    (req, res) -> {
        throw new ProductMissingException(id);
    })
```

Because 401, 403, 409, and 429 mean something completely different from 404. Avoid masking authentication, conflict, or quota causes. Identify them accurately and retain safe diagnostic details in logs/metrics.

## 9. `exchange(...)`: Full Access to Request and Raw Response

Spring 6.2 `RestClient.RequestHeadersSpec#exchange(...)` accepts a callback:

```java
T result = http.get()
        .uri("/products/{id}", id)
        .exchange((request, response) -> {
            HttpStatusCode status = response.getStatusCode();
            HttpHeaders headers = response.getHeaders();
            InputStream body = response.getBody();
            // Manually read/transform/handle here.
            return someResult;
        });
```

This is a **fragment**; `someResult` must be concretely defined. `exchange` gives stronger control and requires the developer to understand the HTTP response contract.

**Critical rule to remember: `exchange(...)` does not apply default status handlers or `retrieve().onStatus`.** If the server returns 404 or 500, the callback still receives the HTTP response normally for you to handle; the client does not automatically throw `HttpClientErrorException.NotFound` just because the status is 404 on this path.

### 9.1. A Callback Can Return a Custom Result Type

```java
record StatusProbe(
        int status,
        String requestId,
        String contentType,
        String body) {}
```

Example:

```java
StatusProbe probe = http.get()
        .uri("/probe/{id}", id)
        .exchange((request, response) -> {
            HttpHeaders headers = response.getHeaders();

            byte[] bytes = response.getBody()
                    .readNBytes(1025);

            if (bytes.length > 1024) {
                throw new OversizedProbeException();
            }

            MediaType contentType = headers.getContentType();

            return new StatusProbe(
                response.getStatusCode().value(),
                headers.getFirst("X-Request-ID"),
                contentType != null
                    ? contentType.toString() : null,
                new String(bytes, StandardCharsets.UTF_8));
        });
```

This is a **method fragment** with `OversizedProbeException` declared in the demo. `InputStream#readNBytes` (Java 17) can throw `IOException`; the callback API allows throwing IOException. Read at most **1,025 bytes** and reject if over 1,024; never call unbounded `readAllBytes()` on untrusted responses.

`new String(bytes, UTF_8)` is suitable only for expected text data; for binary files, decoding as String can corrupt data. For complex JSON payloads, prefer message converters via `retrieve` or an appropriate converter API rather than manual String parsing.

### 9.2. Who Closes the Response and InputStream?

In Spring 6.2, the `exchange(callback)` overload closes `ClientHttpResponse` by default after the callback finishes. Therefore:

- Finish reading/copying **inside the callback**.
- **Do not return `response.getBody()`** outside the callback to read later: the stream may already be closed.
- When using the `exchange(callback, false)` overload, **the caller is responsible** for closing the response; only use it when you understand resource ownership.
- Failing to consume/close a response properly can leak HTTP connections and exhaust the connection pool.
- For large files, stream/copy data to a controlled sink **inside the callback** rather than accumulating everything on the heap.

### 9.3. exchange Does Not Turn Status Errors into Exceptions Automatically

```java
record CheckResult(int status, boolean retryable) {}

CheckResult result = http.get()
        .uri("/health")
        .exchange((request, response) -> {
            int code = response.getStatusCode().value();

            return new CheckResult(
                code,
                code == 429 || code == 503);
        });
```

On 503, the callback can still return `CheckResult(503,true)` instead of throwing. However, **do not automatically retry the request** just because `retryable=true`. You must check method safety/idempotency, Retry-After, retry budget, backoff, and downstream health.

### 9.4. exchange Is Not the Same as RestTemplate.exchange

Distinguish between:

```java
// RestClient:
restClient.get()
        .uri("/products/7")
        .exchange((request, response) ->
                response.getStatusCode().value());
```

and:

```java
// RestTemplate:
ResponseEntity<Product> r =
        restTemplate.exchange(
                "/products/7",
                HttpMethod.GET,
                HttpEntity.EMPTY,
                Product.class);
```

`RestTemplate.exchange(...)` is a **template-style** method that can return `ResponseEntity` directly and uses `ResponseErrorHandler` by default. `RestClient.exchange(...)` takes a callback and **bypasses default status handlers**. Never copy assumptions about exception/error handling from one API to the other.

## 10. Reading Status: HttpStatusCode and Non-Trivial Cases

`HttpStatusCode` represents a status; prefer:

```java
HttpStatusCode status = response.getStatusCode();

boolean success = status.is2xxSuccessful();
boolean clientError = status.is4xxClientError();
boolean serverError = status.is5xxServerError();
int code = status.value();
```

These are fragments. Do not force every status into the `HttpStatus` enum via `HttpStatus.valueOf`, because extension HTTP status codes exist outside the enum. For unusual codes returned by partners, handle safely by family/status.

### 10.1. `2xx` Does Not Always Mean the Same Thing

- 200: usually has a representation body.
- 201: inspect Location/new resource.
- 202: request accepted for later processing, possibly with a job ID.
- 204: no body; `body(Product.class)` can return null.
- 206 Partial Content: uses Range/Content-Range; do not treat received bytes as the full resource.

If a service returns 204 while your code requires `body != null`, change the API contract to `Optional<Product>` or a result type distinguishing the empty case.

### 10.2. 3xx Responses and Redirects

Redirect handling depends on the `ClientHttpRequestFactory`/HTTP client and redirect policy configuration. Do not assume a request always returns 302 to your code, nor that it always follows redirects. When redirecting to another host, never accidentally forward Authorization headers/cookies; configure the client/transport per security policy.

### 10.3. 401 and 403

- 401 often requires checking `WWW-Authenticate` to understand the authentication scheme/challenge; never log bearer credentials.
- 403 indicates lack of permission in the current context; auto-retrying with the same credentials rarely helps.
- Partners sometimes hide resources with 404 to avoid information disclosure; clients must follow the contract without guessing privileges from responses.

## 11. Reading Headers with Explicit Types

`HttpHeaders` supports typed getters and value collections:

```java
HttpHeaders headers = entity.getHeaders();

MediaType type = headers.getContentType();
URI location = headers.getLocation();
String etag = headers.getETag();
long contentLength = headers.getContentLength();
long modifiedEpochMillis = headers.getLastModified();
String requestId = headers.getFirst("X-Request-ID");
List<String> cacheControl = headers.get(HttpHeaders.CACHE_CONTROL);
```

These are fragments; several values may be null or sentinel values. When a header name appears multiple times, `headers.get(name)` can return a **list**; `getFirst` discards subsequent values. Choose based on header semantics, and never arbitrarily join Set-Cookie headers with commas.

### 11.1. Location Must Be Interpreted Properly

A server may return:

```http
Location: /api/products/42
```

This is a **relative** URI, not an absolute URL. If you need to follow the link, resolve it against the verified request URI/public base URI. For external absolute Location values, **never follow to arbitrary hosts automatically**; SSRF or token leakage can occur if a server or compromised upstream returns an internal host.

### 11.2. Retry-After Has Two Formats

The `Retry-After` header can represent:
- **delta-seconds**, e.g., `Retry-After: 5`.
- **HTTP-date**, e.g., a GMT date in standard HTTP format.

Do not blindly call `Integer.parseInt(headers.getFirst("Retry-After"))` because a date value will throw an error. Design a parser with an upper bound, clock skew handling, jitter, and retry budget. Never retry resource-creating POST requests without an idempotency strategy.

### 11.3. ETag, Last-Modified, and Caching

`ETag` is a validator for a representation. Conditional GET can send `If-None-Match`, receive 304, and reuse the corresponding cached bytes. Caches must be keyed by URI, representation-affecting headers (`Vary`), authentication/tenant, and `Cache-Control` policies; never share private data across users simply because the path matches.

### 11.4. Correlation ID

`X-Request-ID`/`traceparent` helps correlate calls, but if an upstream returns an arbitrary requestId, do not trust it as an authenticated identity. When logging, sanitize length/characters and keep raw URIs/queries/tokens out of logs.

## 12. Typed Body Reading: String, DTO, List, Bytes, and Empty

| Body Target | When to Use | Risk |
| --- | --- | --- |
| `String.class` | Plain text or small debug responses | Text may contain secrets; memory if oversized |
| `Product.class` | JSON object | Jackson schema mismatch / missing fields |
| `byte[].class` | Small binary payloads | Buffers all bytes onto the heap |
| `ParameterizedTypeReference<List<Product>>` | Small/medium JSON list | Heap grows with element count |
| `Void.class` / `toBodilessEntity()` | Body not needed | Do not expect a DTO on 204 |
| `exchange(callback)` with InputStream | Custom parsing/stream copy/bounded inspection | Must manage status, resource, and size |
| `Resource.class` | Resource response per converter | Must check transport, streaming, and close semantics |

Do not treat a Java type as proof of safe data. A DTO can deserialize cleanly while still violating business constraints. If validation is required, run Jakarta Validation/service validation after reading the body and before side effects.

### 12.1. Consumed Body and Closed Response

`RestClient` synchronous extraction can close the response after a terminal operation. Do not expect to do:

```java
RestClient.ResponseSpec spec =
        http.get().uri("/products/7").retrieve();

Product p = spec.body(Product.class);
String raw = spec.body(String.class); // Do not do this: reusing spec.
```

Each terminal invocation can trigger a separate exchange or enter unexpected behavior; never use this pattern to “read the body twice” assuming the same HTTP response. If you need both body + headers, use **one** `toEntity`. If you need raw bytes + status, use **one** `exchange` callback.

### 12.2. Do Not Automatically Trust Content-Length

Content-Length can be absent, chunked/HTTP2 responses omit it, compressed sizes differ from decoded sizes, or the server may report an inaccurate value. **Enforce actual limits while reading bytes**, rather than only checking `getContentLength()` before calling `readAllBytes()`.

The `readNBytes(MAX+1)` pattern in the `exchange` section caps retained data; for large stream copies, count bytes per chunk and abort if the quota is exceeded.

### 12.3. JSON Not Matching the Schema

HTTP 200 does not guarantee the JSON body matches the DTO. Jackson can raise `HttpMessageNotReadableException` or a conversion-related exception depending on call path/framework version. Classify **decoder/schema errors** separately from network timeouts or 404s, and never retry endlessly over a field type mismatch.

## 13. When to Use retrieve vs When to Use exchange?

| Need | Recommended Approach | Reason |
| --- | --- | --- |
| Only need JSON object from success response | `retrieve().body(Product.class)` | Concise, converter handles decoding |
| Need status/headers and DTO body | `retrieve().toEntity(Product.class)` | `ResponseEntity` includes all three |
| POST returning 201 + Location, no body needed | `retrieve().toBodilessEntity()` | Gets metadata without decoding body |
| Reading a generic JSON list | `retrieve().body(ParameterizedTypeReference)` | Preserves generic type |
| 404 to domain exception | `retrieve().onStatus(...).body(...)` | Customizes error mapping while keeping converters |
| Want 404/503 as values without default throws | `exchange(...)` | Inspect status manually |
| Raw stream processing and byte caps | `exchange(...)` | Full callback, scoped resource lifecycle |
| Choosing parser based on status/headers | `exchange(...)` or suitable reader design | Inspects response metadata before decoding |
| Simply getting text body while keeping metadata | `retrieve().toEntity(String.class)` | No need for exchange |
| Need non-blocking response streaming | `WebClient`/reactive body | Sync RestClient can hold a thread |

**Do not choose exchange just because “it is more powerful”.** It forces you to take responsibility for HTTP status policies, body parsing, resource closing, and input size limits—things `retrieve` already handles conveniently for standard use cases.

## 14. Complete Application Example: Java 17 + Spring Boot 3.5

Demo goal: call a **mock partner API in unit tests**, with no real network connection. Create `PartnerCatalogClient` using Spring Boot-managed `RestClient.Builder`:

- `find`: `retrieve().body`, returns DTO on 200.
- `withMetadata`: `retrieve().toEntity`, retrieves status + headers + DTO.
- `list`: `ParameterizedTypeReference<List<Product>>`.
- `create`: POST `toBodilessEntity`, reads 201 + Location.
- `findOrThrow`: `onStatus(404)` maps to a custom exception.
- `probe`: `exchange` reads status/headers/body up to 1,024 bytes, even on 404 or 503.
- `inspectWithPolicy`: `exchange` explicitly throws on 5xx, demonstrating developer responsibility.

**Scope limits:** the demo uses `https://partner.example.test` for mocking, not a live Internet endpoint. There is no authentication, retry, network transport tuning, or persistent DB. Tests mock HTTP responses via Spring's test infrastructure without relying on the Internet.

### 14.1. File Structure

```text
restclient-response-demo/
├── build.gradle
└── src/
    ├── main/java/demo/restread/
    │   └── RestReadApplication.java
    └── test/java/demo/restread/
        └── PartnerCatalogClientTests.java
```

### 14.2. Complete Java Source

Create `src/main/java/demo/restread/RestReadApplication.java`:

```java
package demo.restread;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@SpringBootApplication
public class RestReadApplication {
    public static void main(String[] args) {
        SpringApplication.run(RestReadApplication.class, args);
    }
}

record Product(long id, String name) {}

record CreateProduct(String name) {}

record Probe(
        int status,
        String requestId,
        String contentType,
        String body) {}

final class ProductMissingException extends RuntimeException {
    ProductMissingException(long id) {
        super("Product " + id + " not found");
    }
}

final class PartnerUnavailableException extends RuntimeException {
    PartnerUnavailableException(int status) {
        super("Partner unavailable, HTTP " + status);
    }
}

final class OversizedProbeException extends RuntimeException {
    OversizedProbeException() {
        super("Probe response exceeds 1024 bytes");
    }
}

@Service
class PartnerCatalogClient {
    private static final int MAX_PROBE_BYTES = 1024;

    private final RestClient http;

    PartnerCatalogClient(RestClient.Builder builder) {
        // Host is for mock HTTP tests only.
        this.http = builder
                .baseUrl("https://partner.example.test")
                .build();
    }

    Product find(long id) {
        return http.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(Product.class);
    }

    ResponseEntity<Product> withMetadata(long id) {
        return http.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .toEntity(Product.class);
    }

    List<Product> list() {
        return http.get()
                .uri("/products")
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(new ParameterizedTypeReference<
                        List<Product>>() {});
    }

    ResponseEntity<Void> create(CreateProduct input) {
        return http.post()
                .uri("/products")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(input)
                .retrieve()
                .toBodilessEntity();
    }

    Product findOrThrow(long id) {
        return http.get()
                .uri("/products/{id}", id)
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                    status -> status.value() == 404,
                    (request, response) -> {
                        throw new ProductMissingException(id);
                    })
                .body(Product.class);
    }

    Probe probe(long id) {
        return http.get()
                .uri("/probe/{id}", id)
                .exchange((request, response) -> {
                    HttpHeaders headers = response.getHeaders();

                    byte[] bytes = response.getBody()
                            .readNBytes(MAX_PROBE_BYTES + 1);
                    if (bytes.length > MAX_PROBE_BYTES) {
                        throw new OversizedProbeException();
                    }

                    MediaType type = headers.getContentType();

                    return new Probe(
                        response.getStatusCode().value(),
                        headers.getFirst("X-Request-ID"),
                        type != null ? type.toString() : null,
                        new String(bytes,
                                StandardCharsets.UTF_8));
                });
    }

    int inspectWithPolicy(long id) {
        return http.get()
                .uri("/probe/{id}", id)
                .exchange((request, response) -> {
                    HttpStatusCode status =
                            response.getStatusCode();

                    if (status.is5xxServerError()) {
                        throw new PartnerUnavailableException(
                                status.value());
                    }

                    return status.value();
                });
    }
}
```

**Why does this file compile on Java 17?**

- There is one top-level `public class RestReadApplication` matching the filename.
- The `record`s/exceptions/`PartnerCatalogClient` are package-private under `demo.restread`.
- `@SpringBootApplication` component scanning discovers `@Service PartnerCatalogClient`.
- Spring Boot 3.5 supplies the `RestClient.Builder` bean via auto-configuration.
- `@RestClientTest(PartnerCatalogClient.class)` in the test creates the service and a builder with mock customization.
- The `exchange` callback permits throwing `IOException` from `InputStream.readNBytes` per the Spring 6.2 method signature.
- `Probe` is constructed **inside the callback**, without returning a soon-to-close `InputStream`.
- `onStatus` handles exactly 404 without swallowing 401, 409, or 429.
- `ResponseEntity<Void>` for POST makes clear that no body is used when reading Location.

### 14.3. Usage Pattern

```java
ResponseEntity<Product> response =
        partner.withMetadata(7);

if (response.getStatusCode().is2xxSuccessful()) {
    String id = response.getHeaders()
            .getFirst("X-Request-ID");
    Product product = response.getBody();
    // Persist/cache/return product per policy.
}
```

Here `partner` is an injected `PartnerCatalogClient` in a service; this fragment is not a standalone `main`. On status 404, `withMetadata` throws an exception by default so the `if` branch does not handle 404; use `probe` or `findOrThrow` if different behavior is needed.

## 15. Comprehensive Testing with @RestClientTest and MockRestServiceServer

`@RestClientTest` in Boot 3.5 auto-configures `RestClient.Builder`, JSON converters, and `MockRestServiceServer` to test a **synchronous** HTTP client without opening a real server socket. It is a slice test: typically it registers only the specified component rather than all application beans.

Create `src/test/java/demo/restread/PartnerCatalogClientTests.java`:

```java
package demo.restread;

import java.net.URI;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.client.RestClientTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClientResponseException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.http.HttpMethod.GET;
import static org.springframework.http.HttpMethod.POST;

@RestClientTest(PartnerCatalogClient.class)
class PartnerCatalogClientTests {
    private static final String BASE =
            "https://partner.example.test";

    @Autowired
    PartnerCatalogClient partner;

    @Autowired
    MockRestServiceServer server;

    @Test
    void retrieveBodyMapsJsonToDto() {
        server.expect(requestTo(BASE + "/products/7"))
                .andExpect(method(GET))
                .andRespond(withStatus(HttpStatus.OK)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {"id":7,"name":"Guide"}
                        """));

        Product result = partner.find(7);

        assertEquals(new Product(7, "Guide"), result);
        server.verify();
    }

    @Test
    void toEntityProvidesStatusHeadersAndBody() {
        server.expect(requestTo(BASE + "/products/8"))
                .andRespond(withStatus(HttpStatus.OK)
                    .header("X-Request-ID", "req-8")
                    .header(HttpHeaders.ETAG, "\"v8\"")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {"id":8,"name":"Metadata"}
                        """));

        ResponseEntity<Product> response =
                partner.withMetadata(8);

        assertEquals(200,
                response.getStatusCode().value());
        assertEquals("req-8",
                response.getHeaders()
                        .getFirst("X-Request-ID"));
        assertEquals("\"v8\"",
                response.getHeaders().getETag());
        assertEquals(new Product(8, "Metadata"),
                response.getBody());
        server.verify();
    }

    @Test
    void listPreservesGenericProductType() {
        server.expect(requestTo(BASE + "/products"))
                .andRespond(withStatus(HttpStatus.OK)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        [{"id":1,"name":"A"},
                         {"id":2,"name":"B"}]
                        """));

        List<Product> values = partner.list();

        assertEquals(
                List.of(new Product(1, "A"),
                        new Product(2, "B")),
                values);
        server.verify();
    }

    @Test
    void postReadsCreatedStatusAndLocationWithoutBody() {
        server.expect(requestTo(BASE + "/products"))
                .andExpect(method(POST))
                .andRespond(withStatus(HttpStatus.CREATED)
                    .header(HttpHeaders.LOCATION,
                            "/products/41"));

        ResponseEntity<Void> response =
                partner.create(
                        new CreateProduct("Created"));

        assertEquals(201,
                response.getStatusCode().value());
        assertEquals(URI.create("/products/41"),
                response.getHeaders().getLocation());
        assertEquals(null, response.getBody());
        server.verify();
    }

    @Test
    void retrieveDefaultsToExceptionFor404() {
        server.expect(requestTo(BASE + "/products/404"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body("""
                        {"code":"NOT_FOUND"}
                        """));

        RestClientResponseException error =
                assertThrows(
                    RestClientResponseException.class,
                    () -> partner.find(404));

        assertEquals(404,
                error.getStatusCode().value());
        server.verify();
    }

    @Test
    void onStatusMaps404ToTypedDomainError() {
        server.expect(requestTo(BASE + "/products/99"))
                .andRespond(
                    withStatus(HttpStatus.NOT_FOUND));

        ProductMissingException error =
                assertThrows(
                    ProductMissingException.class,
                    () -> partner.findOrThrow(99));

        assertTrue(error.getMessage()
                .contains("99"));
        server.verify();
    }

    @Test
    void exchangeSees404WithoutDefaultException() {
        server.expect(requestTo(BASE + "/probe/4"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND)
                    .header("X-Request-ID", "req-4")
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("missing"));

        Probe response = partner.probe(4);

        assertEquals(404, response.status());
        assertEquals("req-4",
                response.requestId());
        assertEquals("text/plain",
                response.contentType());
        assertEquals("missing", response.body());
        server.verify();
    }

    @Test
    void exchangeLetsApplicationReject503() {
        server.expect(requestTo(BASE + "/probe/5"))
                .andRespond(
                    withStatus(
                        HttpStatus.SERVICE_UNAVAILABLE));

        PartnerUnavailableException error =
                assertThrows(
                    PartnerUnavailableException.class,
                    () -> partner.inspectWithPolicy(5));

        assertTrue(error.getMessage()
                .contains("503"));
        server.verify();
    }

    @Test
    void probeRefusesPayloadOver1024Bytes() {
        server.expect(requestTo(BASE + "/probe/6"))
                .andRespond(withStatus(HttpStatus.OK)
                    .contentType(MediaType.TEXT_PLAIN)
                    .body("A".repeat(1025)));

        assertThrows(
                OversizedProbeException.class,
                () -> partner.probe(6));
        server.verify();
    }
}
```

Run:

```bash
./gradlew test
```

**Nine tests are designed to pass** on Boot 3.5 / Spring Framework 6.2 / Java 17. This is an **expectation from API/source review, not a log from a Gradle execution**.

The tests verify:

- Converter decodes JSON DTO via `retrieve().body`.
- `toEntity` preserves status, headers, and body; ETag retains double quotes per spec.
- Generic list deserializes into `List<Product>`.
- POST reads 201 + Location via `toBodilessEntity`.
- 404 on `retrieve` **throws an exception by default**.
- `onStatus` converts 404 into `ProductMissingException`.
- 404 on `exchange` **is not converted into an exception by default status handlers**.
- `exchange` can explicitly throw on 503 per policy.
- `exchange` reads a bounded body, avoiding arbitrary buffering.

### 15.1. What Slice Tests Do Not Prove

`MockRestServiceServer` mocks the HTTP transport without opening TLS/real sockets. They **do not verify** DNS, proxies, SSL handshakes, connection pooling, connect/read timeouts, redirect policies, or real remote server behavior. To test those, write integration tests with an embedded server or mock HTTP server and a real client transport (with network fault injection if needed).

`@RestClientTest` also does not load every `@Configuration` in the application. If the production client depends on other config beans, use `@Import` or configure the slice test scope properly.

### 15.2. Avoid Tests Depending on the Live Internet

If tests send requests to public API URLs, results become flaky due to networking, rate limits, changing data, and credentials. Use `MockRestServiceServer` for deterministic contract tests, plus targeted integration tests against a partner sandbox/staging environment for compatibility. Never commit secrets into the repo or mock expectations.

### 15.3. Test Status and Headers, Not Just the Body

A solid integration test should also check:
- HTTP method and path.
- `Accept`, `Content-Type`, and appropriate auth/correlation headers.
- Exact status code.
- Location/ETag/Retry-After if required by contract.
- JSON DTO/field types.
- 4xx/5xx mapping and timeouts/cancellation/retries per policy.
- Empty bodies and unknown media types.
- Resource cleanup for raw exchange streams.

Not every endpoint needs assertions on every header; assert only what belongs to the feature's contract.

## 16. Reading Error Response Bodies Safely

A partner may return:

```http
HTTP/1.1 409 Conflict
Content-Type: application/problem+json

{
  "type": "https://partner.example.test/problems/duplicate",
  "title": "Conflict",
  "status": 409,
  "detail": "Product name already exists"
}
```

With `retrieve()`, you can:

1. Use `onStatus` for **409** to map to a domain `DuplicateProductException`.
2. Or catch `RestClientResponseException` and inspect status/headers/bytes, then parse an error DTO after checking max size, Content-Type, and schema.

Avoid:

```java
catch (RestClientResponseException ex) {
    throw new RuntimeException(
            ex.getResponseBodyAsString());
}
```

The error body comes from a remote server; it can contain HTML, stack traces, IDs, request data, or unexpected characters. Never forward it verbatim to browsers, logs, or metrics tags. Map it to a stable error code such as `PARTNER_CONFLICT` and record a safe `requestId` for lookup.

### 16.1. Reading Body After HTTP Exception vs Raw Response Callback

`RestClientResponseException` stores the status/headers/body extracted by the framework for error cases; developers can read them from the exception. `exchange` gives direct access to the response stream inside the callback. **Never pass `ClientHttpResponse` or `InputStream` from exchange outside** when the default overload closes resources.

### 16.2. Network Errors Have No HTTP Status

`ResourceAccessException` on connect timeout/DNS/TLS/read failures must not always be assigned status 503 as if from the remote server: **no HTTP response may have been received at all**. Record an internal error category and apply a bounded retry policy rather than fabricating a status code the server never returned.

## 17. Configuring Timeouts and HTTP Transport

`RestClient` abstracts over `ClientHttpRequestFactory`. How timeouts are configured depends on the chosen HTTP backend: JDK `HttpClient`, Apache HttpComponents, Simple/JDK request factory, or another library.

**Do not invent a generic property and assume every RestClient now has proper timeouts.** Verify against Spring Boot 3.5 auto-configuration and the chosen HTTP client library.

Java fragment using the JDK request factory:

```java
JdkClientHttpRequestFactory requestFactory =
        new JdkClientHttpRequestFactory();

requestFactory.setReadTimeout(
        Duration.ofSeconds(3));

RestClient client = RestClient.builder()
        .requestFactory(requestFactory)
        .baseUrl("https://partner.example.test")
        .build();
```

This is a **fragment**, requiring `java.time.Duration` and `org.springframework.http.client.JdkClientHttpRequestFactory`. In addition to read timeout, **connect timeout** is configured on the underlying `java.net.http.HttpClient` when needed. For the Apache HttpComponents request factory, constructors/settings differ and require the corresponding dependency; do not copy JDK code onto Apache.

Distinguish between:
- DNS lookup/connection establishment.
- TLS handshake.
- Connection pool acquisition.
- Socket/read inactivity timeout.
- Overall request deadline.
- Retries/backoff and circuit breaker.
- HTTP response body streaming time.

A 3-second timeout does not guarantee every phase/case completes in at most three seconds if the backend defines it as a read timeout; test real failure modes.

### 17.1. RestClient Is Blocking; Do Not Misuse It on the WebFlux Event Loop

If a WebFlux controller temporarily needs to call a synchronous API:

```java
Mono<Product> result = Mono
        .fromCallable(() -> partner.find(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This is a **fragment**, not a long-term recommendation when WebClient is available. `boundedElastic` isolates the blocking call but still has thread/queue capacity and needs concurrency/timeout limits. If the project is already reactive, non-blocking `WebClient` is a better fit.

## 18. Retries, Idempotency, and Statuses in System Integration

An API may return 429/503/504, but retrying must account for the HTTP method and side effects:

| Method/Case | How Retries Should Behave |
| --- | --- |
| Idempotent GET, transient 503 | Can retry with budget/backoff/jitter |
| HEAD, transient network failure | Can retry if safe and server policy permits |
| Resource-creating POST | Retry only with idempotency key/deduplication or clear contract |
| Endpoint-defined idempotent PUT | Can retry with identity/version/ETag safeguards |
| DELETE | Check semantics/not-found state and actual idempotency |
| 400 malformed input | Do not retry the same payload |
| 401 token expired | Controlled token refresh, never an infinite loop |
| 403 forbidden | Do not retry indefinitely |
| 404 missing | Usually a domain outcome, unless a special eventual consistency policy applies |
| 409 conflict | Needs reconciliation and optimistic locking, not blind retry |
| 429 quota | Respect Retry-After/rate budgets |
| 503 overload | Backoff; avoid retry storms |

`retrieve`/`exchange` **do not automatically provide a business-safe retry policy**. To automate retries, use a retry library/circuit breaker like Resilience4j, while designing idempotency, tracing, timeouts, hedging, and max attempts.

### 18.1. Handling HTTP 202

A 202 response may contain a job ID or Location of a status endpoint. The client should poll with a bounded cadence or use callbacks/webhooks rather than treating 202 as a final result. Read `Retry-After` as a hint if supported. If polling uses blocking `RestClient`, configure a scheduler and cap concurrent polling jobs.

## 19. Observability/Metrics/Logging When Reading Status/Headers/Body

Recommended telemetry to collect:
- Logical downstream service name (low cardinality).
- Route template or operation name, method.
- Status family 2xx/4xx/5xx and normalized error code.
- Latency p50/p95/p99 and timeout/retry counts.
- HTTP client connection pool pending/active counts if available.
- Validated/sanitized downstream request ID.
- Body size/chunk counts when relevant.

Never log:
- Authorization, Proxy-Authorization, Cookie, Set-Cookie.
- Raw query strings if they contain tokens/PII.
- JSON bodies containing passwords, emails, phone numbers, or tokens.
- Raw error HTML/stack traces returned by partners.
- URIs with embedded credentials.
- Metrics tags taken directly from product IDs/user IDs creating unbounded cardinality.

In Spring Boot, injecting the builder preserves customizations and observability. When constructing a custom request factory, verify that interceptors, TLS/proxy settings, and tracing still apply.

## 20. Security: SSRF, Redirects, Response Limits, Schema Trust

### 20.1. SSRF from User-Supplied URIs

If code builds a URI from a user parameter:

```java
String url = request.getParameter("url");

http.get()
    .uri(url)
    .retrieve()
    .body(String.class);
```

This is an **anti-pattern**; a user could force the server to call metadata services, loopback, or internal hosts. Even with baseUrl configured, an absolute URL passed to `uri(...)` can override the host. Use an allowlist of base hosts, URI template path/query variables, and DNS/IP/redirect policies; never let clients pick arbitrary schemes/hosts.

### 20.2. HTTP Redirects Can Leak Credentials

Control redirect following via the request factory; never allow bearer tokens, cookies, or client certificates to be sent to untrusted hosts. If a partner returns an unexpected Location, verify scheme/hostname/port/path before following; never assume GET on Location is safe.

### 20.3. Response Size and Decompression

A server can return huge or heavily compressed payloads. `body(String.class)`/`byte[].class`/`List<Product>` can aggregate data and cause OOM. Bound decompressed bytes, record counts, JSON depth, and concurrency; checking Content-Length before reading **is not enough**.

### 20.4. Valid JSON Objects Can Still Be Invalid Business-Wise

Jackson decoding into Product does not validate authorization, allowed identifiers, or business constraints. Validate fields/schema/server provenance against the contract. Never automatically persist every remote-returned field onto an entity carrying permissions/roles/tenant IDs.

## 21. RestClient vs RestTemplate vs WebClient

| Feature | RestClient | RestTemplate | WebClient |
| --- | --- | --- | --- |
| Model | Synchronous, fluent | Synchronous, template methods | Reactive, non-blocking |
| Since Spring Framework | 6.1+ | Long-standing | 5+ |
| Reading body | `retrieve().body(Type)` | `getForObject(...)`, `exchange(...)` | `retrieve().bodyToMono(Type)` |
| Reading status + headers | `retrieve().toEntity(Type)` | `getForEntity` / `exchange` | `retrieve().toEntity(Type)` returning `Mono<ResponseEntity<T>>` |
| Raw response access | `exchange(callback)` | `execute(callbacks)` | `exchangeToMono/Flux` |
| Default 4xx/5xx | Throws at retrieve terminal | `ResponseErrorHandler` | Error signal on Mono/Flux |
| Status handler scope | `onStatus` on retrieve | `setErrorHandler` | `onStatus` on retrieve |
| Return types | T / ResponseEntity<T> | T / ResponseEntity<T> | Mono<T> / Flux<T> |
| Thread blocking | Yes | Yes | Non-blocking I/O by design |
| Typical environment | MVC/scheduled sync clients | Legacy MVC code | WebFlux/reactive integrations |

**Specifically:** `RestTemplate.exchange(...)` and `RestClient.exchange(...)` share a name but differ in signatures and default error handling. `WebClient.exchangeToMono(...)` also differs from `RestClient.exchange(...)` in callback typing and body/resource lifecycle.

### 21.1. Migrating RestTemplate to RestClient

| Legacy RestTemplate | RestClient Equivalent |
| --- | --- |
| `getForObject(url,Product.class)` | `get().uri(url).retrieve().body(Product.class)` |
| `getForEntity(url,Product.class)` | `get().uri(url).retrieve().toEntity(Product.class)` |
| `postForEntity(url,input,Product.class)` | `post().uri(url).body(input).retrieve().toEntity(Product.class)` |
| `delete(url)` | `delete().uri(url).retrieve().toBodilessEntity()` |
| `exchange(url,GET,entity,Product.class)` | `method(GET).uri(url).headers(...).retrieve().toEntity(Product.class)` |
| `execute(url,method,callback,extractor)` | `method(method).uri(url).exchange(exchangeFunction)` |

Migration is not merely renaming APIs. You must preserve auth headers, error mapping, pooling/timeouts, URI encoding, interceptors, and testing contracts.

## 22. Practical Decision Tree

```text
Need a synchronous API call?
  |
  +-- No -> use WebClient / suitable reactive client
  |
  +-- Yes -> use RestClient
              |
              +-- Only need success body?
              |      |
              |      +-- yes -> retrieve().body(Type)
              |
              +-- Need status + headers + body DTO?
              |      |
              |      +-- yes -> retrieve().toEntity(Type)
              |
              +-- Don't need body, only status/Location?
              |      |
              |      +-- yes -> retrieve().toBodilessEntity()
              |
              +-- Need custom 404/409 -> domain exception?
              |      |
              |      +-- yes -> retrieve().onStatus(...)
              |
              +-- Need all statuses as values,
              |   or raw body stream/conditional extraction?
                     |
                     +-- yes -> exchange(callback)
                                  |
                                  +-- inspect status manually
                                  +-- bound body size
                                  +-- finish reading in callback
                                  +-- never leak resources
```

## 23. Common Mistakes and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Called retrieve but server never receives request | No terminal operation invoked | `body/toEntity/toBodilessEntity` |
| 404 returned but `if(status==404)` never runs | `retrieve` throws default exception | `onStatus` or `exchange` |
| `exchange` returns 503 and app treats it as success | `exchange` skips default status handlers | Inspect status explicitly |
| Cannot read 201 Location | Only called `body(Product.class)` | `toEntity` or `toBodilessEntity` |
| Generic JSON list maps to LinkedHashMap | Used raw `List.class` | `ParameterizedTypeReference<List<Product>>` |
| `body(...)` returns null on 204 | No response body | Use `ResponseEntity<Void>`, handle empty |
| Lost correlation ID | Only extracted body | Read `getHeaders().getFirst(...)` |
| HTTP 429 treated as missing product | Status mapping too broad | Typed 429/rate-limit policy |
| I/O exception assigned server 503 | No HTTP response guaranteed | Distinguish `ResourceAccessException` |
| Reading body after `exchange` callback fails | Response auto-closed | Read/copy inside callback |
| Downloading large file causes OOM | `body(byte[].class)`/readAllBytes | Bounded streaming with exchange or suitable HTTP client |
| POST retry creates duplicate resource | Timed out after server committed | Idempotency key / dedupe |
| Retry-After header fails to parse | Assumed always numeric | Support delta-seconds or HTTP-date |
| ETag cache serves wrong tenant | Cache key missing auth/Vary | Design cache key/policy |
| Slice test fails to inject service | `@RestClientTest` scans narrow scope | Specify component/`@Import` |
| Real HTTPS fails even though MockRestServiceServer passes | Mock does not test TLS/transport | Real transport integration tests |
| WebFlux lags badly calling RestClient | Blocking on event loop | `WebClient` or temporary boundedElastic |
| Authorization header appears in logs | Unredacted logging | Sanitize request/response logs |
| Partner URI uses user-supplied host | SSRF | Allowlist scheme/host/IP/redirect policy |
| Connection pool exhausted | Large timeouts/unclosed responses | Proper resource ownership, pool metrics |
| `onStatus` configured but ignored by exchange | Retrieve status handlers don't apply to exchange | Check status inside callback |
| Upgrading Spring major breaks method overload | API version changes | Check Javadoc/BOM and run tests |

### 23.1. Debugging Order

1. Confirm actual runtime is Spring Framework 6.2/Spring Boot 3.5 and client type is `RestClient`.
2. Check `baseUrl` + template variables + method/path/query/headers.
3. Ensure a terminal operation was invoked.
4. Identify whether `retrieve` or `exchange` is used to understand the error policy.
5. Inspect HTTP status/headers before assuming body semantics.
6. For 4xx/5xx, inspect typed exceptions or callback status policies.
7. For network failures, check DNS/TLS/connect/read timeouts and request factory.
8. For null body/JSON errors, check status 204/304, Content-Type/schema.
9. For large files, check byte aggregation, direct memory, and resource closure.
10. For tests, use MockRestServiceServer for logic and real HTTP transport integration for networking.

## 24. Pre-Production Integration Checklist

- [ ] Choose `RestClient` for synchronous requests and `WebClient` when reactive non-blocking is needed.
- [ ] Inject Boot's `RestClient.Builder` when auto-configured customizations are needed.
- [ ] Reuse RestClient instances; avoid unbounded per-request client/connection creation.
- [ ] Invoke a terminal operation after `retrieve()`.
- [ ] Use `toEntity` when status, headers, and body are all needed.
- [ ] Use `toBodilessEntity` for 201/202/204 when no body is needed.
- [ ] Understand `retrieve` throws 4xx/5xx by default; apply `onStatus` per business rules.
- [ ] When using `exchange`, classify statuses manually and read the body inside the callback.
- [ ] Never return a raw InputStream/ClientHttpResponse from the default callback.
- [ ] Never read large files unbounded into `byte[]`/String/List.
- [ ] Use `ParameterizedTypeReference` for generic JSON bodies.
- [ ] Encode URI variables and enforce base URL/redirect allowlists against SSRF.
- [ ] Configure and separately test connect/read/deadline/pool timeouts.
- [ ] Configure HTTP retries with max attempts/backoff/jitter/idempotency.
- [ ] Distinguish 401/403/404/409/429/500/503 and I/O failures.
- [ ] Parse Retry-After properly for both delta-seconds and HTTP-date if used.
- [ ] Verify ETag/304/cache Vary/auth scoping properly.
- [ ] Never log Authorization/cookies/PII/raw error bodies.
- [ ] Test with @RestClientTest + MockRestServiceServer for success/errors/headers/body.
- [ ] Run integration tests with TLS/proxies/connection pools/real transport as needed.
- [ ] Review Spring versions/migrated APIs and header semantics after upgrades.

## 25. Self-Assessment Exercises

1. Does `RestClient.retrieve()` send the HTTP request immediately? Which methods are terminal?
2. Why is `body(Product.class)` alone insufficient when a creation API returns 201 + Location?
3. Write a `retrieve().toEntity(Product.class)` snippet reading ETag, Content-Type, and X-Request-ID.
4. Distinguish `toBodilessEntity()` from `body(Void.class)` when status/Location are needed.
5. Why can `ResponseEntity<Product>.getBody()` be null when the status is 204?
6. When an API returns a JSON array, what bug does `ParameterizedTypeReference<List<Product>>` solve compared to `List.class`?
7. When `retrieve` hits 404, does code after `toEntity` run normally?
8. Add `onStatus` mapping 404 to ProductMissingException while keeping 401/429 on default behavior.
9. Call `exchange` on a 503 response. Why is no default HttpServerErrorException thrown?
10. Build a `Probe` containing status, requestId, and body text capped at 1,024 bytes inside the callback.
11. If you return `InputStream` from an `exchange` callback, what can happen when the caller reads it afterward?
12. When handling multi-GB files, why is `body(byte[].class)` unsafe?
13. Compare `HttpHeaders#getFirst` with `get` when a header has multiple values.
14. The server returns `Retry-After: Wed, 21 Oct 2026 08:00:00 GMT`; will integer parsing work?
15. When using ETag and 304, why must you care about Vary and tenant/auth cache keys?
16. If `RestClient` raises `ResourceAccessException` before an HTTP response arrives, where do you get a status code from?
17. A POST times out, yet the server may already have created the resource. How should retries be designed?
18. Distinguish tenant-quota 429 from downstream-overload 503 when designing retry logic.
19. Why does `@RestClientTest` not guarantee DNS/TLS/redirects work properly in production?
20. Use MockRestServiceServer to test default 404, custom onStatus 404, and exchange 404 as three distinct cases.
21. A REST API returns an HTML body despite Accept JSON. What should the client inspect before deserializing?
22. What benefits does building `RestClient` via Boot's Builder have over `RestClient.create()` in a large application?
23. If a WebFlux application uses RestClient on the Netty event loop, what are the symptoms and solutions?
24. Distinguish `RestTemplate.exchange(...)` and `RestClient.exchange(...)` by signature and error policy.
25. Add exact timeouts for your HTTP backend, and test connect/read timeouts with a real mock server.
26. Design a circuit breaker/retry policy for a partner API returning 200, 404, 429, 503, and network timeouts.
27. If a Location response points to `http://127.0.0.1/...`, why must it not be followed automatically?
28. Expose status/headers/body in an application object without letting raw headers containing secrets reach the frontend.
29. Write a test proving a 1,025-byte response body triggers `OversizedProbeException` from bounded reading.
30. When upgrading from Spring Boot 3.5 to Boot 4, which APIs, starters, test imports, and request factories must be verified?

## 26. Official Documentation

- [Spring Framework 6.2 — REST Clients reference](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html): RestClient synchronous API, retrieve/body/toEntity, status/error handling, exchange, and RestTemplate comparison.
- [Spring Framework 6.2 — RestClient Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.html): builder, fluent API.
- [Spring Framework 6.2 — RestClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.ResponseSpec.html): `body`, `toEntity`, `toBodilessEntity`, `onStatus`.
- [Spring Framework 6.2 — RestClient.RequestHeadersSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/client/RestClient.RequestHeadersSpec.html): `retrieve`, `exchange`, response lifecycle.
- [Spring Framework 6.2 — HttpHeaders Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/HttpHeaders.html): ETag, Location, Content-Type, contentLength, retry semantics.
- [Spring Framework 6.2 — ResponseEntity Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/http/ResponseEntity.html): status, headers, body.
- [Spring Framework 6.2 — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html#rest-message-conversion): converter selection and JSON mapping.
- [Spring Boot 3.5 — RestClientTest](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@RestClientTest` and MockRestServiceServer.
- [Spring Framework — MockRestServiceServer Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/web/client/MockRestServiceServer.html): request expectations, fake responses, and verify.
- [Spring Framework — Client Request Factories](https://docs.spring.io/spring-framework/reference/6.2/integration/rest-clients.html#rest-client-request-factories): request transport/timeouts.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): response status, Location, Retry-After, ETag, and caching semantics.
- [Spring Framework — Reactive WebClient](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-webclient.html): when asynchronous/non-blocking I/O is needed.
