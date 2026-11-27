# Synchronizing Headers, Body, and Status Code When Generating Responses at the Gateway

## 1. The problem: an HTTP response must be consistent from start to finish

In a microservices architecture, **Spring Cloud Gateway** typically receives an HTTP request, selects a route using a **route predicate**, runs a **filter chain**, and forwards to a service resolved via a static URI or service discovery. Beyond proxying data, the Gateway can also **generate responses directly at the edge**: rejecting unauthenticated requests, enforcing rate limits, returning fallbacks when backends fail, redirecting legacy URLs, or returning responses from an internal handler.

When creating or transforming a response yourself, you must synchronize **all three parts of an HTTP response**:

1. **Status code:** did the request succeed, get rejected, have no content, or ask the client to retry?
2. **Response headers:** how do they describe the content type, length, caching, security, resource location, or connection conditions?
3. **Response body:** is there content or not, and does the data match the format and semantics declared by the status/headers?

Example of a **contradictory** response:

~~~http
HTTP/1.1 204 No Content
Content-Type: application/json
Content-Length: 23

{"message":"Completed"}
~~~

Code **204 No Content** indicates there is no response content. Sending a body together with a `Content-Length` declaration as above violates HTTP semantics and can cause clients/proxies to misinterpret the data.

Another example: the Gateway modifies a JSON body yet retains `Content-Length` from upstream. The actual byte count no longer matches the header, causing truncated responses, clients hanging for more bytes, or connections closing with protocol errors.

**Goal of this lesson:** write and configure response filters in **Spring Cloud Gateway Server WebFlux** so that status, headers, and body describe **one** valid HTTP outcome; handle response commit timing properly; and avoid data leaks, broken caching, and streaming errors. This lesson belongs to the **Headers and Status** chapter, so it focuses on HTTP responses rather than covering all authentication, rate limiting, or circuit breaker mechanisms in depth.

After this lesson, you should be able to:

- Recognize the response lifecycle in the filter chain and when headers/status can no longer be changed.
- Use `ServerHttpResponse.setStatusCode(...)`, `getHeaders()`, `writeWith(...)`, `setComplete()`, and `beforeCommit(...)` appropriately.
- Produce a concise JSON error response at the Gateway without continuing to proxy the request.
- Distinguish responses with and without a body: 200, 201, 202, 204, 304, 401, 403, 429, 503, HEAD, redirects, and partial content.
- Know when `Content-Length`, `Content-Type`, `Content-Encoding`, `ETag`, `Location`, and other headers must be recomputed.
- Test direct Gateway responses, proxied upstream responses, and failures occurring after a response has begun streaming.

> **Version scope:** Java examples target **Spring Cloud Gateway Server WebFlux** with Spring WebFlux/Reactor. Across different Spring Cloud Gateway release lines, some packages, starter names, or YAML namespaces may change; Server Web MVC has a different customization model. Verify the API against your exact version.

## 2. The three parts of a response and the HTTP contract

Response model:

~~~mermaid
flowchart TD
    R[HTTP response] --> S[Status code]
    R --> H[Response headers]
    R --> B[Response body or no body]
    S --> C[Consistent HTTP contract]
    H --> C
    B --> C
~~~

Key headers to inspect:

| Header | Description | Signs to verify |
| --- | --- | --- |
| `Content-Type` | Media type of the body, optionally with charset | Is the body actually JSON, text, SSE, or binary as declared? |
| `Content-Length` | Content length in **bytes** where applicable | Did the body change while the old header stayed behind? |
| `Content-Encoding` | Content encoding such as gzip | Is the header still accurate after decompressing/recompressing the body? |
| `Transfer-Encoding` | HTTP/1.1 transfer mechanism such as chunked | Is it left to the HTTP server rather than set arbitrarily? |
| `Location` | URI of a newly created resource or redirect URL | Does status match 201/3xx; are host and query safe? |
| `Cache-Control` | Caching policy | Could responses with private data be publicly cached? |
| `ETag` | Validator for the representation | Did the body change while the old ETag remained? |
| `Vary` | Request headers influencing representation selection | Do proxies/caches know the response varies by `Origin`, `Accept-Encoding`, or `Accept-Language`? |
| `Retry-After` | Recommended retry wait (seconds or HTTP-date) | Does it align with 429/503 and the retry policy? |
| `WWW-Authenticate` | Authentication challenge details | Does a 401 response carry a challenge fitting the protection scheme? |

Core rule: **you cannot infer the entire contract from a status code alone**. For instance, 200 may return JSON, a binary file, or SSE; 404 may carry an error body; 204 must send no body; 206 must accurately describe the partial slice returned.

### Example of a valid 429 response with a body

~~~http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Cache-Control: no-store
Retry-After: 5

{"code":"RATE_LIMITED","message":"Try again later"}
~~~

If the Gateway sends `Content-Length`, it must reflect the **encoded byte length**, not the number of Unicode characters in the string. With UTF-8, Vietnamese characters typically use multiple bytes, so `String.length()` does not equal the size on the wire.

## 3. Where are responses created in Spring Cloud Gateway?

A request can follow two paths:

- **Proxy upstream:** a route is selected; gateway filters prepare the request; the routing filter calls the microservice; headers/status/body from the backend are processed and written to the client, possibly with intentional Gateway changes.
- **Short-circuit at the Gateway:** a filter decides not to call upstream, sets status/headers, writes a body (if needed), and returns the completion publisher.

~~~mermaid
flowchart TD
    C[Client request] --> M[RoutePredicateHandlerMapping]
    M --> F[FilteringWebHandler + filter chain]
    F --> Q{Continue proxying?}
    Q -->|Yes| U[Routing filter calls upstream]
    U --> UR[Upstream status + headers + body]
    UR --> RF[Gateway response filters / write response]
    Q -->|No| L[Local response: status + headers + body]
    L --> W[ServerHttpResponse]
    RF --> W
    W --> C2[Client]
~~~

In **Server WebFlux**, `ServerWebExchange` holds `ServerHttpResponse`:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
~~~

This only **prepares metadata**. If there is a body, write it via the appropriate publisher. If there is no body, complete the response with the proper API. The completion method must match the status and headers.

A `GlobalFilter` or `GatewayFilter` typically returns `Mono<Void>`. This type represents **asynchronous completion progress**, not that the HTTP response lacks content. The body is written through `ServerHttpResponse` during publisher execution.

### Scope limitation of GlobalFilter

`GlobalFilter` participates in the filter chain **for requests routed by Spring Cloud Gateway**; it does not automatically cover every WebFlux controller or HTTP request that matches no route. To handle errors/security at the application level or for standalone WebFlux endpoints, also consider `WebFilter`, Spring Security WebFlux, and exception handling. Never treat a `GlobalFilter` as a complete replacement for security configuration.

## 4. The "committed" state: the most critical boundary

In HTTP, the status line and response headers must be sent **before** the body. Once a response has been committed, you cannot go back and alter status/headers as though nothing were sent.

In Spring WebFlux, check:

~~~java
boolean committed = exchange.getResponse().isCommitted();
~~~

Conceptual states:

~~~mermaid
stateDiagram-v2
    [*] --> NotCommitted: Response not written yet
    NotCommitted --> Preparing: setStatusCode / set headers
    Preparing --> Committing: writeWith or setComplete
    Committing --> Committed: Headers sent
    Committed --> Completed: Body finished
    Committed --> MidStreamError: Error or client cancel
    Completed --> [*]
    MidStreamError --> [*]
~~~

This diagram is conceptual: the framework may commit when starting to write the body or when completing a bodyless response. Remember **not to wait until `chain.filter(exchange)` finishes before trying to edit status or headers**, because downstream may have already committed them.

### Preparing a response before writing

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
response.getHeaders().setCacheControl("no-store");
return response.setComplete();
~~~

Because `setComplete()` intentionally terminates the response **without a body**, never call `setComplete()` and then subsequently call `writeWith(...)` on the same response.

### beforeCommit helps update headers at the right moment

Spring WebFlux provides `beforeCommit` to register work executed just before the response commits:

~~~java
@Override
public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
    ServerHttpResponse response = exchange.getResponse();

    response.beforeCommit(() -> {
        response.getHeaders().set("X-Gateway-Processed", "true");
        return Mono.empty();
    });

    return chain.filter(exchange);
}
~~~

This is a method excerpt inside a `GlobalFilter` or `GatewayFilter`; imports/bean registration are omitted to highlight the mechanism. The callback is registered **before continuing the chain**. It fits lightweight, deterministic, non-blocking operations such as adding an observability header. `beforeCommit` is not a solution for reading and reassembling an entire body after it has been sent.

If you need to adjust status/headers based on upstream results, understand **filter ordering** and when metadata becomes available. A `beforeCommit` callback can inspect the status already set by downstream right as commit begins, but should not be used to arbitrarily override every backend status.

## 5. Creating JSON responses and short-circuiting properly

The complete example below illustrates a `GlobalFilter` returning **429** for a test path `/api/demo/limited`. It intentionally **does not call `chain.filter(exchange)`** on the rejection branch:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class DemoRateLimitResponseFilter implements GlobalFilter, Ordered {

    @Override
    public int getOrder() {
        return -100;
    }

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String path = exchange.getRequest().getPath().value();

        if (!"/api/demo/limited".equals(path)) {
            return chain.filter(exchange);
        }

        String json = "{\"code\":\"RATE_LIMITED\",\"message\":\"Try again later\"}";
        byte[] payload = json.getBytes(StandardCharsets.UTF_8);

        ServerHttpResponse response = exchange.getResponse();
        response.setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
        response.getHeaders().setContentLength(payload.length);
        response.getHeaders().setCacheControl("no-store");
        response.getHeaders().set(HttpHeaders.RETRY_AFTER, "5");

        DataBuffer buffer = response.bufferFactory().wrap(payload);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

**Consistency analysis:**

1. `HttpStatus.TOO_MANY_REQUESTS` is code 429, fitting rate-limit rejection.
2. `Content-Type: application/json` matches the generated JSON string.
3. `Content-Length` comes from **`payload.length`**, which is the exact UTF-8 byte count in an example **with no later body-compressing or transforming layer**.
4. `Cache-Control: no-store` reduces the risk of error responses with private content being cached.
5. `Retry-After: 5` is a hint to retry after 5 seconds; it is not a guarantee the backend will be ready at second five.
6. `response.writeWith(...)` returns a `Mono<Void>` tying the body write lifecycle to the WebFlux pipeline.
7. Because the rejected branch does not return `chain.filter(exchange)`, the Gateway does not call upstream on that path.

**Important:** Path-based rejection above is strictly for **learning response creation**, not a rate-limiting algorithm. In real applications, use `RequestRateLimiter` or an appropriate quota mechanism keyed by trusted identity across instances. For this filter to run in the example, the application must have a **route matching `/api/demo/limited`**; without a route, a Gateway `GlobalFilter` will not necessarily be invoked.

Never create a `DataBuffer` and call `subscribe()` yourself inside a filter. **Return the publisher** created by `writeWith` so the framework manages writing, errors, and cancellation. When working directly with pooled `DataBuffer`s, understand retain/release lifecycles; the snippet above wraps a byte array and hands lifecycle management to the response writer.

### When there is no body

A simple rejection response can carry only status and headers:

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.FORBIDDEN);
response.getHeaders().setCacheControl("no-store");
return response.setComplete();
~~~

Do not set `Content-Type: application/json` and then omit JSON content if the contract expects an error payload. Conversely, if the contract allows an empty body, do not attach a `Content-Type` describing an imaginary body.

## 6. Choosing status codes consistent with having or omitting a body

Status determines response semantics. A practical reference table:

| Status/method | Can it send a body? | What to keep consistent |
| --- | --- | --- |
| **200 OK** | Yes | Accurate Content-Type, encoding, body, and length if declared |
| **201 Created** | Yes | If returning Location, URI must accurately identify the created resource |
| **202 Accepted** | Yes | Expresses request accepted but processing incomplete; response must not pretend final completion |
| **204 No Content** | **No** | Do not write a body; do not send Content-Length as if a payload existed |
| **304 Not Modified** | **No response body** | Keep proper cache validator info, write no body; Content-Length valid only under standard HTTP rules |
| **HEAD (any applicable status)** | **No response body** | Metadata describes the corresponding GET response where applicable; do not force Content-Length to 0 if the real representation has another size |
| **206 Partial Content** | Yes, per range | Content-Range, Content-Length, and actual transmitted bytes must match |
| **301/302/307/308** | May carry explanatory content | Location must be accurate; account for method/body when clients follow redirects |
| **401 Unauthorized** | Usually may carry a body | WWW-Authenticate challenge matching the authentication scheme |
| **403 Forbidden** | Yes | Do not leak sensitive resource details or internal permissions in the body |
| **429 Too Many Requests** | Yes | Retry-After when appropriate; do not obscure rate-limit policy source |
| **503 Service Unavailable** | Yes | Indicate unavailability; avoid fallback bodies with misleading business data |

Additional notes:

**204 No Content:** Do not call `writeWith` to send JSON or text. Do not attach `Content-Length` as if sending a body. With no additional content, set status and allowed headers and call `setComplete()`.

**304 Not Modified:** Appropriate only when cache/validator preconditions apply. Send no body. Unlike 204, HTTP allows certain representation metadata, including `Content-Length` **if** its value matches the 200 response that would have been sent; do not mechanically force 0 or copy arbitrary lengths.

**HEAD:** The response carries no body, while metadata may describe the size of the body a corresponding GET would produce. Attempting to "fix" every HEAD with `Content-Length: 0` can violate the contract.

**206 Partial Content:** If a gateway filter edits a file or compresses part of the body after upstream computed ranges, `Content-Range`, `Accept-Ranges`, or `Content-Length` risk becoming wrong. Do not rewrite ranged responses unless you thoroughly handle byte-range semantics.

**401 and 403:** 401 typically pairs with an authentication requirement/challenge, 403 with access denial. Use the accurate status and set response metadata according to your security scheme. With Spring Security, prefer letting authentication entry points / access denied handlers manage them instead of emitting ad-hoc 401/403 from random filters.

## 7. Synchronizing Content-Length with actual bytes sent

**`Content-Length` is the number of bytes**, not characters or elements in a `Flux`.

Example:

~~~java
String text = "Processed";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);

response.getHeaders().setContentType(
        new MediaType("text", "plain", StandardCharsets.UTF_8));
response.getHeaders().setContentLength(bytes.length);
return response.writeWith(
        Mono.just(response.bufferFactory().wrap(bytes)));
~~~

Because Unicode characters can span multiple UTF-8 bytes, using `text.length()` to populate `Content-Length` will be wrong.

When **the length is not known beforehand**—such as SSE or long streaming responses—you should usually **not set `Content-Length` manually**. The HTTP runtime can pick the right transfer mechanism: HTTP/1.1 can use chunked transfer encoding where appropriate, while HTTP/2 uses data frames and flow control without `Transfer-Encoding: chunked`.

### When can Content-Length become stale?

| Scenario | Why it can become wrong | How to handle |
| --- | --- | --- |
| Gateway adds a field to JSON body | New byte count differs from old byte count | Recompute length after transformation or omit Content-Length so the writer chooses framing |
| Gateway changes charset | Encoding can change byte count | Use actual bytes after encoding |
| Gateway decompresses and sends plain body | Body is no longer content-encoded | Sync Content-Encoding, Content-Length, validators, and related headers |
| Gateway additionally compresses response | Wire bytes differ from pre-compression | Let the compression component/HTTP writer manage metadata |
| Backend returns SSE/NDJSON streaming | Total byte count is unknown | Do not manually set an arbitrary Content-Length |
| Gateway modifies a partial response | Content-Range and segment size no longer match | Avoid modifying ranges or implement compliant range handling |

**Never guess and attach both `Content-Length` and `Transfer-Encoding`.** These are protocol metadata fields managed/modifiable by HTTP servers and proxies. Conflicting length declarations are also tied to HTTP request/response smuggling risks across inconsistent infrastructure.

## 8. When the Gateway transforms a response body

A body-altering filter must treat the body as **a complete representation with linked metadata**, not merely a character string. For instance, backend returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 15
ETag: "old-v1"

{"status":"ok"}
~~~

If the Gateway adds `"source":"gateway"` to the JSON, the new body is longer. Besides `Content-Length`, the `ETag` validator may no longer describe the same representation. If `Content-Encoding: gzip` is present, the bytes read or written by the filter may already be compressed depending on pipeline position; never simply edit the JSON string and forward the old gzip header.

Essential steps when transforming a body:

1. Determine whether the body is raw bytes, codec-decoded, or decompressed.
2. Choose the right data types and media types (JSON, text, binary, SSE...) eligible for transformation.
3. Produce the new body using an appropriate encoder/serializer.
4. Update or let the framework recompute `Content-Length` and `Content-Encoding` as needed.
5. Handle `ETag`, cache validators, `Content-Range`, and checksums: retain only if still valid, recompute if a valid mechanism exists, or remove when invalidated.
6. Test errors, cancellation, and cases where the response starts streaming before the filter finishes.

**ModifyResponseBody:** Spring Cloud Gateway Server WebFlux provides the **`ModifyResponseBody` GatewayFilter Factory** to transform bodies via codecs. Its API/registration is tied to **Java DSL**; do not assume every version supports equivalent YAML configuration. When using it, consider memory footprint, response types, and body buffering; **never assume a body-transforming filter preserves streaming semantics for SSE or large files**.

If you only need to modify a header, prefer built-in response header filters instead of reading and rewriting the body. If you need to return an error message at the edge, it is usually simpler and safer to **build a consistent error response at the Gateway** before proxying rather than patching a backend response after sending has begun.

## 9. Built-in filters for adjusting status and headers

Spring Cloud Gateway provides several response-level filters. The names below illustrate common capabilities; verify against documentation for your exact version when configuring:

| Filter | Purpose | Consistency notes |
| --- | --- | --- |
| `SetStatus` | Overrides HTTP status per route configuration | **Does not automatically edit the body** to match the new code |
| `AddResponseHeader` | Adds a response header | Can create multiple values; only add valid headers |
| `SetResponseHeader` | Replaces a response header | Does not automatically guarantee the new header matches the body |
| `RemoveResponseHeader` | Removes a response header | Avoid accidentally deleting mandatory response metadata |
| `RewriteResponseHeader` | Edits header values via regex/replacement | Useful for Location/Cookie in specific cases; must control encoding |
| `DedupeResponseHeader` | Deduplicates response header values | Often useful when both Gateway and upstream add CORS headers |
| `ModifyResponseBody` | Transforms the body representation | Revisit Content-Length, encoding, validators, and buffering |

Example route receiving a backend response and adding an informational header:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - AddResponseHeader=X-Gateway-Route, orders-api
                - RemoveResponseHeader=Server
~~~

`lb://` requires configured service-instance resolution and load balancing (such as Spring Cloud LoadBalancer paired with service discovery). The example above only edits headers; **it does not automatically alter response content**. In older Spring Cloud Gateway WebFlux versions, the route namespace may be `spring.cloud.gateway.routes` instead of `spring.cloud.gateway.server.webflux.routes`.

### Caution with SetStatus

Suppose the backend returns:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"O-42","state":"CREATED"}
~~~

If you add `SetStatus=503` without changing the body, the client may see **503** paired with JSON describing a succeeded order. That is semantically inconsistent at the business level even if the HTTP packet is syntactically valid. **Never use `SetStatus` to mask the real outcome**; design error/fallback policies with matching status, body, and metadata.

Conversely, changing **404** to **200** does not magically create a resource or valid data. Keep the result contract reliable for clients.

## 10. CORS, caching, and security headers

The Gateway is often where CORS, TLS, authentication, and certain security response headers are enforced for web/mobile clients. If multiple layers write these headers, they can produce conflicts or data exposure.

### CORS: Gateway and upstream must not emit conflicting values

Bad response example:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Duplicate/conflicting `Access-Control-Allow-Origin` headers can cause browsers to reject the response. When `Access-Control-Allow-Credentials: true`, never use wildcard `*` as Allowed-Origin. With Origin-dependent policies, validate allowed origins and include an appropriate `Vary: Origin` so caches differentiate responses.

Designate **one CORS policy owner** (e.g., the Gateway) or coordinate explicitly. `DedupeResponseHeader` can reduce duplicate values when both Gateway and downstream emit CORS headers, but it **cannot fix an invalid CORS policy**.

### Caching: status, body, and validators must agree

- Responses containing personal data, tokens, or per-user authorization results generally require strict caching policies, such as `Cache-Control: no-store` when appropriate.
- If representations vary by `Accept-Language`, `Origin`, or `Accept-Encoding`, set `Vary` accurately and consistently.
- If the Gateway transforms the body, **the upstream `ETag` may no longer be valid**; do not keep asserting the new content shares the same validator.
- For conditional GETs, `304 Not Modified` must match the real validator of the cached representation; never turn an error body into 304 just to save bandwidth.

### Security headers and hop-by-hop headers

Headers such as `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, or `Referrer-Policy` must be configured according to application policy and how TLS is deployed. Do not copy an arbitrary header set onto every response without evaluating context.

**Hop-by-hop headers**, such as `Connection` and fields named in `Connection`, belong to each individual HTTP connection; proxies must not arbitrarily forward them onto another connection. The HTTP stack/Gateway handles these automatically. Never keep `Transfer-Encoding: chunked` when the client-facing response uses HTTP/2.

When generating redirects or absolute URLs, trust `Forwarded`, `X-Forwarded-Proto`, and `X-Forwarded-Host` only from controlled proxies; otherwise clients can spoof them to craft wrong URLs or **open redirects**.

## 11. Errors, retries, and fallbacks: once committed, the response cannot be swapped

A response can encounter errors at two points:

~~~mermaid
flowchart TD
    A[Gateway processing request] --> B{Response committed?}
    B -->|No| C[Can craft a new error response]
    B -->|Yes| D[Cannot change already-sent status/headers]
    C --> E[Set error status + headers + body]
    D --> F[Log error, close or cancel stream, client handles partial data]
~~~

### Errors before response commit

Suppose the Gateway calls the backend and hits a connection error before sending data to the client. Depending on configuration, an error handler, `CircuitBreaker` fallback, or error-handling mechanism can generate a **503** JSON response:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Cache-Control: no-store
Retry-After: 10

{"code":"UPSTREAM_UNAVAILABLE","message":"Temporarily unavailable"}
~~~

Status 503, `Retry-After`, and the message body must all match the classified situation. Do not arbitrarily convert every exception into 503: validation errors, authorization errors, and programming bugs carry distinct semantics. If retries are enabled, protect **non-idempotent** operations like order creation and payments.

### Errors after response commit

With SSE or NDJSON, the Gateway may have already sent status 200 and several events before the backend disconnects:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

event: progress
data: 20

<connection interrupted>
~~~

After this point, **you cannot go back and return status 503 on the already-committed response**. Record the mid-stream error, cancellation, and disconnect timing, and let clients apply reconnect/resume contracts when supported. Retrying an entire stream that already emitted events can duplicate events or records.

Basic defensive pattern in a custom filter:

~~~java
return chain.filter(exchange)
        .onErrorResume(error -> {
            ServerHttpResponse response = exchange.getResponse();
            if (response.isCommitted()) {
                return Mono.error(error);
            }
            // Illustrative only: real logic must classify the error.
            response.setStatusCode(HttpStatus.SERVICE_UNAVAILABLE);
            response.getHeaders().setCacheControl("no-store");
            return response.setComplete();
        });
~~~

**Do not use this snippet verbatim as a production error handler.** It turns every pre-commit error into 503 without guaranteeing stale metadata was cleared or that the status fits the error. In real environments, error handling should classify exceptions, inspect/update related headers, emit metrics/traces, and use appropriate exception-handling mechanisms. This snippet solely illustrates **checking commit state**.

## 12. Creating redirects or bodyless responses

### Redirects with Location

An HTTP redirect can be generated by the Gateway via `RedirectTo` or appropriate response logic:

~~~yaml
predicates:
  - Path=/old-docs
filters:
  - RedirectTo=308, https://docs.example.test/guide
~~~

Points to synchronize:

- Code **308** signifies a permanent redirect; following clients must preserve method/body per HTTP rules.
- `Location` must point to a valid URL and never take arbitrary hosts from untrusted clients.
- Do not assume the old URL's query string automatically appears in the new `Location`.
- When writing a redirect response manually, ensure status, `Location`, and body (if any) do not contradict.

### Returning 204 for successful actions with no content

~~~java
ServerHttpResponse response = exchange.getResponse();
response.setStatusCode(HttpStatus.NO_CONTENT);
response.getHeaders().remove(HttpHeaders.CONTENT_LENGTH);
return response.setComplete();
~~~

This illustrates setting 204 when **no body has been written yet**. If upstream actually returned content, do not switch status to 204 and still let the response writer emit a body. Choose 204 on the proper execution path and let the HTTP stack manage framing.

### 201 Created and Location

If an API creates resource `/api/orders/O-42` and needs to send 201, the URL in `Location` must be meaningful to the client. Never leak internal URIs like `http://orders-service:8080/orders/O-42` when the public endpoint goes through `https://api.example.test/api/orders/O-42`. When the Gateway sits behind an ingress, derive the public scheme/host from configuration or a trusted proxy.

## 13. Testing response consistency

Tests should not verify only a `200` status. Verify **status, headers, and body as a trio**.

### Example curl checks

Assume the app defines a route matching `/api/demo/limited` and registers `DemoRateLimitResponseFilter` from section 5:

~~~bash
# Check status line, response headers, and JSON body:
curl -i http://localhost:8080/api/demo/limited

# Inspect exact response headers and protocol execution path:
curl -v http://localhost:8080/api/demo/limited

# For SSE streams, disable curl output buffering:
curl -i -N http://localhost:8080/api/stream/events
~~~

The commands above are **verification guides**, not actual run outputs of the lesson. `curl -I` sends HEAD; it is **not** equivalent to inspecting headers of an ordinary GET if the server handles HEAD differently. When testing bodyless responses, use the specific method and status rather than relying on a generic content check.

For the 429 demo:

| Component | Expectation |
| --- | --- |
| Status | `429 Too Many Requests` |
| Content-Type | `application/json` |
| Retry-After | `5` |
| Cache-Control | `no-store` |
| Content-Length | Equals exact UTF-8 byte length of the emitted JSON if no further transform layer runs |
| Body | Valid JSON with `code` and `message` |
| Upstream | **Not called** on the short-circuit branch |

### Testing with WebTestClient

In an integration test against a running or properly bound Gateway, you can verify:

~~~java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .build();

client.get()
        .uri("/api/demo/limited")
        .exchange()
        .expectStatus().isEqualTo(429)
        .expectHeader().contentType(MediaType.APPLICATION_JSON)
        .expectHeader().valueEquals("Retry-After", "5")
        .expectBody()
        .jsonPath("$.code").isEqualTo("RATE_LIMITED");
~~~

This illustrative test needs `WebTestClient` and `MediaType` dependencies/imports, plus **the Gateway must have a matching route and active filter**. The test above does not yet verify byte-exact `Content-Length`, prove upstream was not called, or test mid-stream errors; add matching tests using stub backends and proper HTTP/client tests.

### Recommended test matrix

| Scenario | Status | Headers to check | Body to check |
| --- | --- | --- | --- |
| Successful proxied GET JSON | 200 | Content-Type, Content-Length if present, Cache-Control | Contract-compliant JSON |
| Rate-limit short-circuit | 429 | Retry-After, Content-Type, Cache-Control | Proper error JSON |
| Missing authentication | 401 | WWW-Authenticate per chosen scheme | No token/stack trace leakage |
| Insufficient permissions | 403 | Cache-Control if needed | No sensitive info disclosed |
| Success with no content | 204 | No invalid Content-Length | **No body** |
| Valid conditional GET | 304 | Accurate ETag/Vary/caching metadata | **No body** |
| HEAD to resource | Matches corresponding GET | Valid metadata, may include representation size | **No body** |
| Partial download | 206 | Matching Content-Range, Content-Length | Exact requested bytes |
| Legacy URL redirect | 301/302/307/308 | Safe Location | Body per contract |
| Upstream SSE fails mid-stream | May already be 200 | Headers committed, cannot swap | Partial stream and disconnect recorded |
| Gateway edits upstream JSON | Matches new contract | Recomputed/updated Content-Length, ETag, Content-Encoding | Valid JSON after transformation |

## 14. Common bugs and anti-patterns

| Anti-pattern | Consequence | How to resolve |
| --- | --- | --- |
| `response.setStatusCode(204)` then sending JSON | Body violates 204 semantics | Return 200/202 with body or 204 without body |
| Calling `setComplete()` then `writeWith(...)` | Response already/nearly complete, body not written properly | Choose only one completion path |
| Modifying headers in `.then(...)` after downstream | May be too late due to response commit | Register `beforeCommit` at the right time |
| Modifying JSON yet keeping upstream Content-Length | Wrong length header | Recompute length or omit so the HTTP writer handles it |
| Modifying body yet keeping old Content-Encoding/ETag | Client fails decoding or caching breaks | Sync/strip/recompute metadata |
| Setting Content-Length from `String.length()` | Wrong byte count with UTF-8 | Use `byte[].length` of the actual encoded body |
| Returning 401 without challenge when scheme requires it | Client does not know how to re-authenticate | Use Spring Security and proper WWW-Authenticate |
| Gateway and upstream write different CORS values | Browser rejects response | Single policy owner, controlled dedupe |
| Retry/fallback after SSE already sent data | Cannot swap status; may duplicate events | Check commit state, design reconnect/resume |
| Trusting client Forwarded/Host to build Location | Open redirect or info leak | Trust only controlled proxies; allowlist URLs |
| Logging full body, Authorization, or Set-Cookie | Data leak and memory pressure | Safely log route ID/status/latency |
| Turning upstream 503 into 200 while body reports error | Client misreads state | Design semantically aligned fallback policies |

With streaming responses, an error **after commit** cannot be fixed by "appending" a JSON error body at the end of the stream. Closing the connection and recording the error/cancel signal is part of the contract; clients must know how to handle incomplete data.

## 15. Comprehensive hands-on exercise

**Context:** A Gateway fronts Orders, Catalog, and Notification services. The Gateway handles authentication, rate limiting, circuit breaking, retries, TLS, and tracing; the team needs every edge-to-client response to be consistent.

### Part A — Creating responses at the Gateway

1. Add a test route matching `/api/demo/limited` and register `DemoRateLimitResponseFilter`.
2. Use GET to verify the Gateway returns 429, `Retry-After: 5`, valid JSON, and `Content-Length` equal to the byte count.
3. Use a stub/spy backend to prove the short-circuit branch **does not call upstream**.
4. Try replacing the JSON message with a longer Vietnamese message. Ensure `Content-Length` changes by UTF-8 byte count rather than character count.

### Part B — Creating statuses with different body rules

1. Create a 204 response for a bodyless successful action; verify the client receives no payload.
2. Create a 503 response when a dependency fails **before commit**, with an appropriate body and cache headers.
3. Call HEAD on a test endpoint that has a matching GET; verify no body is sent while metadata remains meaningful.
4. Create a 307 or 308 redirect to an allowlisted URL; check `Location`, method, and behavior when the client does not auto-follow redirects.

### Part C — Transforming upstream responses

1. Backend returns JSON with `Content-Length` and `ETag`. In a **test environment**, modify the JSON through an appropriate filter.
2. Verify metadata is updated or stripped properly; never let an old validator vouch for the new body.
3. Test compressed responses and a 206 response. Document why bodies should not be modified without handling `Content-Encoding` or ranges.

### Part D — Mid-stream errors and security

1. Backend sends SSE and disconnects after a few events; confirm the Gateway cannot change the already-committed status.
2. Test CORS when both Gateway and upstream add headers; configure a single clear policy owner.
3. Test spoofed `Host`/`Forwarded` values at the edge and ensure `Location` never points to arbitrary hosts.
4. Enable per-route traces/metrics, while never logging bodies containing personal data, `Authorization`, or `Cookie`.

**Passing criteria:** Every branch returns the right status, headers accurately describe the emitted body (or absence of body); no stale `Content-Length`/`Content-Encoding`/`ETag`; consistent CORS and cache policies; post-commit responses handled as partial streams without protocol-violating status rewrites; all checks backed by evidence from HTTP clients and backend stubs.

## 16. Summary

- A response at an API Gateway is an **inseparable trio**: **status, headers, body**. Changing one part requires checking the other two.
- Only **uncommitted responses** allow reliable status/header adjustments. Register `beforeCommit` early; do not arbitrarily edit responses after downstream finishes.
- In WebFlux, `writeWith(...)` writes the body via a publisher; `setComplete()` is used when intentionally completing a bodyless response. **Return `Mono<Void>` to the framework**, never subscribe manually.
- **204, 304, and HEAD carry no response body**; 206 must keep ranges consistent; 201/3xx with `Location` must use accurate, safe origins.
- **`Content-Length` is a byte count**, not a character count. When modifying a body, re-verify `Content-Type`, `Content-Encoding`, `ETag`, cache metadata, and length.
- Filters such as `SetStatus`, `SetResponseHeader`, `DedupeResponseHeader`, and `ModifyResponseBody` have distinct responsibilities; **no filter automatically guarantees a valid business contract just because status changed**.
- For post-commit errors, streaming, redirects, CORS, and forwarded headers, verify **end-to-end** through the Gateway and backend. Correctness, security, and observability must go together.
