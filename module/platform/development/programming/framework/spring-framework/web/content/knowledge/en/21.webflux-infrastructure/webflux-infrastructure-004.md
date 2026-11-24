# ServerHttpRequest, ServerHttpResponse, and Request/Response Data in Spring WebFlux

## 1. Why understand the two low-level HTTP interfaces?

A Spring WebFlux controller normally accepts `@RequestBody`, `@RequestHeader`, `@RequestParam`, and returns `Mono<DTO>` or `ResponseEntity<DTO>`. That style fits business APIs very well. However, when building a **WebFilter**, logging/tracing infrastructure, gateway, custom error handling, response headers, streaming, or middleware that operates at the HTTP protocol level, you encounter two abstractions:

- **`ServerHttpRequest`**: the server's incoming request, from method, URI, path, headers, and cookies to the **body as a `Flux<DataBuffer>`**.
- **`ServerHttpResponse`**: the response the server is constructing, including status, headers, cookies, and **asynchronous body-writing** methods such as `writeWith`, `writeAndFlushWith`, and `setComplete`.

In WebFlux, these two objects are connected through **`ServerWebExchange`** — the context for **one HTTP request/response interaction**. Understanding them prevents subtle bugs: reading the body twice, setting status after the response has committed, leaking pooled buffers, blocking a thread to return a request body, or accidentally caching private data.

Example reading metadata:

~~~java
@GetMapping("/inspect")
public Mono<Map<String, String>> inspect(
        ServerHttpRequest request,
        ServerHttpResponse response) {

    response.getHeaders().set("Cache-Control", "no-store");
    String method = request.getMethod().name();
    String path = request.getPath().pathWithinApplication().value();

    return Mono.just(Map.of("method", method, "path", path));
}
~~~

This is a Spring WebFlux **fragment**: place it inside a `@RestController` with appropriate imports. There are no blocking statements; Spring WebFlux can select a converter to write JSON from the Mono value. Response headers must be set **before the response is committed**, not after the body has finished sending.

### Learning outcomes

After this article, you will be able to:
1. Distinguish `ServerHttpRequest`, `ServerHttpResponse`, `ServerWebExchange`, `ServerRequest`, and Servlet MVC objects.
2. Read method/URI/path/query/headers/cookies/client address without equating client-supplied data with trusted identity.
3. Understand the `Flux<DataBuffer>` body stream: consume intentionally, work with codecs, enforce memory limits, handle reference-counting, and handle cancellation.
4. Write status, headers, `ResponseCookie`, and bodies using reactive methods on `ServerHttpResponse`.
5. Understand `beforeCommit`, `isCommitted`, and differences between `writeWith`, `writeAndFlushWith`, and `setComplete`.
6. Use `WebFilter` to set exchange attributes, mutate requests safely, and attach response headers.
7. Build a Java 17 / Spring Boot 3.3.5 app with metadata endpoints, JSON bodies, size-bounded raw bodies, cookies, and response completion.
8. Verify final responses with `WebTestClient`, including 201, 204, 413, echoed bytes, and headers.
9. Diagnose issues involving security, content types, proxy headers, logging, body consumption, and throughput.

This article uses **Spring WebFlux on Reactor Netty**, not Servlet MVC. The runnable examples use Spring Framework 6.1.x managed by Spring Boot 3.3.5; for Spring Framework 7, check the corresponding API documentation.

## 2. HTTP architecture overview in WebFlux

~~~text
HTTP client
   |
   v
Reactor Netty / HTTP server adapter
   |
   v
ServerHttpRequest ---------+
                           |  ServerWebExchange
ServerHttpResponse --------+
   |
   v
WebFilter chain
   |
   v
WebHandler / DispatcherHandler
   |
   +-- HandlerMapping
   +-- HandlerAdapter (annotated / functional endpoints)
   +-- Codec: HttpMessageReader / HttpMessageWriter
   |
   v
ServerHttpResponse.writeWith / setComplete
   |
   v
HTTP client
~~~

Spring WebFlux implements a framework-neutral **`HttpHandler`** to work with reactive HTTP server adapters; `WebHttpHandlerBuilder` typically wires WebFilters, WebExceptionHandlers, sessions, and required components. The handler-selecting layer may be `DispatcherHandler` for annotated controllers or functional routes.

### 2.1. Packages to distinguish

| Type | Important package | Role |
| --- | --- | --- |
| `ServerHttpRequest` | `org.springframework.http.server.reactive` | Low-level server HTTP request |
| `ServerHttpResponse` | `org.springframework.http.server.reactive` | Low-level server HTTP response |
| `ServerWebExchange` | `org.springframework.web.server` | Request + response + attributes + session context |
| `WebFilter` | `org.springframework.web.server` | Reactive middleware before/after handler |
| `ServerRequest` | `org.springframework.web.reactive.function.server` | Convenient request API for functional WebFlux endpoints |
| `ServerResponse` | `org.springframework.web.reactive.function.server` | Response builder for functional WebFlux |
| `HttpServletRequest` | `jakarta.servlet.http` | Servlet stack, not WebFlux core |
| `org.springframework.web.servlet.function.ServerRequest` | Servlet WebMvc.fn | Functional Servlet MVC, **different** from reactive ServerRequest |

The same program may also use `WebClient`, yet `ClientRequest`/`ClientResponse` are **outbound client** abstractions, not the two server objects studied here.

### 2.2. Why is ServerWebExchange important?

An exchange provides access to:

~~~java
ServerHttpRequest request = exchange.getRequest();
ServerHttpResponse response = exchange.getResponse();
Map<String, Object> attributes = exchange.getAttributes();
~~~

In addition, there are `exchange.getSession()` returning `Mono<WebSession>`, principal information `getPrincipal()`, locale, conditional request support like `checkNotModified(...)`, and other utilities. **Exchange attributes** are data bound to a single request/response interaction; they are not automatically a global store or user session.

Never store an entire `ServerWebExchange` in a static collection or long-lived queue: an exchange can hold request bodies, response handles, headers, contexts, and references beyond the HTTP lifecycle.

## 3. `ServerHttpRequest`: reading parts of the request

### 3.1. HTTP method

~~~java
HttpMethod method = request.getMethod();
~~~

The `HttpMethod` object represents GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS... Do not treat the method as proof that a request is safe: a poorly implemented GET that mutates data still causes side effects; conversely, a POST may need an idempotency key and authorization checks.

### 3.2. URI and path

~~~java
URI uri = request.getURI();
RequestPath path = request.getPath();
String relative = path.pathWithinApplication().value();
String fullPath = path.value();
~~~

This code fragment requires `java.net.URI` and `org.springframework.http.server.RequestPath`. `getURI()` returns the request URI according to the server abstraction; `getPath()` is a path API that can account for context paths. `pathWithinApplication()` is commonly used when application routing needs the internal path.

**Never parse paths manually with `uri.toString().split("/")`**: encoded characters, context paths, `?` characters, slash normalization, and gateway rewrites break that approach. In annotated controllers, `@PathVariable` is usually preferable in business handlers.

### 3.3. Query parameters

~~~java
MultiValueMap<String, String> query = request.getQueryParams();
String q = query.getFirst("q");
List<String> tags = query.get("tag");
~~~

`getQueryParams()` organizes URI query parameters into a structure supporting multiple values per name. For example:

~~~http
GET /api/search?q=java&tag=reactor&tag=spring HTTP/1.1
~~~

gives `q` as `"java"` and `tags` with two elements. `getFirst` retrieves the first value; it does not mean the other values were validated.

**Important:** the query string is untrusted data. Enforce length/count limits, normalize sort/filter values, validate, and never put raw queries into SQL, logs alongside secrets, or metric labels. If a client sends `?role=admin`, that grants zero authorization on its own.

### 3.4. Request headers

~~~java
HttpHeaders headers = request.getHeaders();
MediaType contentType = headers.getContentType();
String language = headers.getFirst("Accept-Language");
String requestId = headers.getFirst("X-Request-Id");
~~~

`HttpHeaders` can hold multi-value headers; `getFirst` reads only one value. HTTP header names are case-insensitive, yet header **values carry their own semantics** — for instance, the Authorization value is a secret credential.

Important headers:

| Header | Common meaning | Safe practice |
| --- | --- | --- |
| `Content-Type` | Media type of the request body | Verify compatibility with codec/endpoint |
| `Accept` | Representation acceptable to the client | Use produces/negotiation when needed |
| `Authorization` | Credential or bearer token | Do not log; authenticate via Spring Security |
| `Cookie` | State sent by client | Do not infer user/tenant solely from cookie names |
| `Origin` | Browser origin for CORS | CORS does not replace authorization |
| `If-None-Match` | HTTP conditional request | Check ETag per resource/permission |
| `Forwarded`, `X-Forwarded-*` | Metadata that proxies may add | Trust only configured proxy chains |
| `Content-Length` | Declared body length if present | Not proof that the actual body will match |
| `Traceparent` / correlation ID | Distributed tracing | Never use raw arbitrary values as metric labels |

### 3.5. Cookies

~~~java
MultiValueMap<String, HttpCookie> cookies = request.getCookies();
HttpCookie session = cookies.getFirst("SESSION");
~~~

`HttpCookie` only describes a cookie from the request. Session cookies can be verified by Spring Security/session management, yet a controller should not read `SESSION` itself and treat its value as an authenticated user.

The demo example will only return a **boolean indicating whether a cookie named `demo` is present**, without putting raw values into JSON or logs. For real data, authentication cookies must have HTTPS, `Secure`, `HttpOnly`, and `SameSite` suited to the threat model.

### 3.6. Client address and forwarded headers

~~~java
InetSocketAddress remote = request.getRemoteAddress();
InetSocketAddress local = request.getLocalAddress();
~~~

These are socket-layer details or values processed by an adapter/transformer depending on infrastructure. Behind a CDN/reverse proxy, `getRemoteAddress()` may be the proxy address, **not necessarily the real client**. Do not blindly trust `X-Forwarded-For` sent by the client, as attackers can spoof IPs.

When constructing absolute URLs or applying IP allowlists/rate limits, properly configure trusted proxies/forwarded-header handling, bound the trusted proxy chain, and enforce at ingress. Never take the first element of `X-Forwarded-For` and treat it as verified identity.

### 3.7. Request ID

`request.getId()` supplies an ID to help correlate logs for a request depending on implementation. Do not treat it as a durable transaction ID, session ID, or security token. Tracing systems usually have independent trace/span IDs. When using `request.getLogPrefix()` or the exchange log prefix, they serve correlation and do not turn client-sent headers into trusted sources.

## 4. Body data does not live in `getHeaders()`

In WebFlux, `ServerHttpRequest.getBody()` returns:

~~~java
Flux<DataBuffer> body = request.getBody();
~~~

`DataBuffer` represents a slice of bytes emitted by the server adapter through the reactive stream. **A single DataBuffer is not necessarily a complete JSON object, HTTP chunk, or message.** TCP fragmentation, Netty read events, and codec buffering can split a body across multiple buffers depending on timing.

Therefore:
- Do not assume `getBody().next()` is the **entire body**.
- Do not read `getBody()` in a WebFilter and expect a `@RequestBody` controller to read it again as if `Flux` replayed by default.
- Do not call `getBody().blockFirst()` on the event loop.
- Do not use unbounded `buffer.collectList()` on unlimited user uploads.
- Do not turn a `DataBuffer` into a `String` via `buffer.toString()` without specifying decoding, charset, and release.
- When manipulating pooled `DataBuffer`s directly, understand **ownership/release** to prevent native memory leaks.

### 4.1. Bodies are normally read exactly once

On a real HTTP socket, the request body is a **streaming source**. Many pipelines offer no guarantee of re-reading after the first consumption. Example WebFilter logging:

~~~java
return DataBufferUtils.join(exchange.getRequest().getBody())
        .doOnNext(buffer -> logBody(buffer))
        .then(chain.filter(exchange));
~~~

This is an **anti-pattern** fragment with a hypothetical `logBody` function. It can consume the body before the handler, starving the controller of data; unbounded `join` can spike memory; logging can expose passwords/tokens; and reference-counted buffers still need releasing.

If you genuinely must log/inspect bodies, you need a request decorator emitting a **replayable stream** with strict memory management and cleanup, byte limits, redaction, cancellation, and never caching/logging sensitive content arbitrarily. Usually logging method/path/status/latency or schema-level metadata is safer and sufficient.

### 4.2. Why are high-level codecs better for JSON?

With an annotated WebFlux controller:

~~~java
@PostMapping(
        path = "/api/notes",
        consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<NoteOut> create(@RequestBody Mono<NoteIn> input) {
    return input.map(this::convert);
}
~~~

This is a fragment with undefined `NoteIn`, `NoteOut`, `convert`. Spring WebFlux uses `HttpMessageReader`/JSON decoders to parse `Flux<DataBuffer>` into objects. The framework generally handles release/aggregation per implementation, applies codec memory limits, parses media types, and forwards decoding errors to the error layer. You still need Bean Validation or explicit domain validation.

**Never read `request.getBody()` in a filter and `@RequestBody` again in a controller** without a properly engineered cache/decorator layer. Also never subscribe to the request body outside the pipeline via `subscribe()`.

## 5. `DataBuffer`: managing bytes and memory

### 5.1. DataBuffer is not just a byte array

Spring provides the `DataBuffer` abstraction with `readableByteCount()`, `read(byte[])`, `write`, and read/write indices. Depending on the runtime, implementations may wrap Netty pooled `ByteBuf`s with reference counting or heap memory. **Never assume Java GC will automatically free all direct/native buffers if you drop a reference.**

### 5.2. Joining a body with an explicit limit

When a small body is genuinely needed (for example, a raw echo demo), you can do:

~~~java
Mono<byte[]> bytes = DataBufferUtils
        .join(request.getBody(), 1024)
        .map(buffer -> {
            try {
                byte[] copy = new byte[buffer.readableByteCount()];
                buffer.read(copy);
                return copy;
            } finally {
                DataBufferUtils.release(buffer);
            }
        })
        .defaultIfEmpty(new byte[0]);
~~~

This fragment uses `ServerHttpRequest request` and imports `DataBufferUtils`/`Mono`. `join(...,1024)` caps the aggregated byte count; exceeding it emits `DataBufferLimitException`. If the stream errors/cancels before emitting the joined buffer, `join` is responsible for releasing accumulated chunks per contract; once a joined buffer is received for manual reading, the `finally` block **releases the result**.

If payloads can be large, **do not** aggregate everything into `byte[]`. For file uploads, use streaming resources/`FilePart.transferTo`, appropriate storage APIs, server/gateway limits, and stream-level validation.

### 5.3. Converting buffers to Strings requires knowing the charset

~~~java
String text = new String(bytes, StandardCharsets.UTF_8);
~~~

This fragment assumes `bytes` is a properly copied `byte[]`. Do not decode individual DataBuffers as UTF-8 and concatenate Strings if a multi-byte character can split across buffer boundaries: decoders must handle boundaries properly or aggregate within limits. For JSON/text, normally let Spring's codecs handle this.

### 5.4. Release / retain / ownership

- When you **receive and consume** a pooled `DataBuffer` at the application level (without passing it to a framework writer), you may need `DataBufferUtils.release(buffer)`.
- If you pass publishers/buffers directly to `response.writeWith(...)`, the response writer manages the write stream and ownership per contract; do not release before the body finishes writing.
- If you replay/copy/slice shared pooled buffers, `retain`/`release` must balance across the lifecycle; do not hold references after the source releases.
- On error/cancel, verify resource cleanup across operators; `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` can help in specific pipelines, yet do not add it mechanically when another component owns the buffer.
- Never write code that both releases a buffer in `doOnNext` **and** passes the same object downstream to `writeWith`: that risks use-after-release.

**Clear boundary:** body bytes are copied into a `byte[]` in the demo; after releasing the joined buffer, the application uses the **copy** to construct a new response buffer.

### 5.5. Body limits: across multiple layers

| Limit | Layer applied | Notes |
| --- | --- | --- |
| Reverse proxy/CDN maximum request body | Infrastructure | Can block requests before reaching Spring |
| Reactor Netty server config | HTTP server | Limits related to decoders/headers/form behavior |
| `spring.codec.max-in-memory-size` | Codec aggregation | Applies to certain codecs/buffer decodes, not every custom raw pipeline |
| `DataBufferUtils.join(body,maxByteCount)` | Manual aggregation code | Protects that specific buffer join |
| DTO/payload validation | Domain/service | Limits field counts, string lengths, types |
| Multipart/file storage limits | Upload pipeline | Watch disk quota, temporary files, streaming |

**Do not rely solely on the `Content-Length` header** to protect memory: clients can use chunked transfer or send misleading/duplicate headers depending on HTTP server handling. Limits must be enforced while reading and at the infrastructure layer.

## 6. `ServerHttpResponse`: a response with a commit lifecycle

`ServerHttpResponse` allows:
- `setStatusCode(HttpStatusCode)`: picks the HTTP status if the response is not yet committed; returns a boolean indicating whether setting succeeded in the API.
- `getStatusCode()`: current status, may be null if not explicitly set, depending on the abstraction.
- `getHeaders()`: adds/modifies response headers before commit.
- `getCookies()` and `addCookie(ResponseCookie)`: outbound cookies.
- `beforeCommit(Supplier<Mono<Void>>)`: registers an action before commit.
- `isCommitted()`: has the response entered committed state per the abstraction?
- `bufferFactory()`: creates DataBuffers for output.
- `writeWith(Publisher<? extends DataBuffer>)`: writes body reactively.
- `writeAndFlushWith(Publisher<? extends Publisher<? extends DataBuffer>>)`: writes buffer groups and flushes per inner publisher.
- `setComplete()`: marks output complete with no custom body.

### 6.1. Status and headers should be decided early

~~~java
response.setStatusCode(HttpStatus.ACCEPTED);
response.getHeaders().setContentType(MediaType.APPLICATION_JSON);
response.getHeaders().setCacheControl("no-store");
~~~

This is a fragment using `response` inside a controller/filter. Calling `setStatusCode` does not immediately flush bytes to the socket; commit happens when the response publisher is processed. **Once the response has committed, you cannot rely on status or header changes taking effect.** In multi-filter applications, always verify the final response with integration tests.

### 6.2. `ResponseCookie` differs from request `HttpCookie`

To send a cookie:

~~~java
ResponseCookie cookie = ResponseCookie.from("demo", "ok")
        .path("/")
        .httpOnly(true)
        .sameSite("Lax")
        .build();

response.addCookie(cookie);
~~~

On production HTTPS, when cookies traverse TLS, consider `secure(true)` and proper cookie scope/domain/path. `HttpOnly` prevents JavaScript from reading cookies via document.cookie; `SameSite` governs browser cross-site sending; **neither replaces authentication/authorization or CSRF protection**.

Never put cookie bearer tokens or session IDs into URLs for debugging. `Set-Cookie` headers can leak secrets if logged raw; filter/redact them in proxies and application logging.

### 6.3. When does `beforeCommit` run?

~~~java
response.beforeCommit(() ->
        Mono.fromRunnable(() ->
                response.getHeaders().set("X-Commit", "ready")));
~~~

`beforeCommit` **registers an action**; it does not execute immediately. The callback should return a **deferred** `Mono<Void>` (such as `Mono.fromRunnable` or `Mono.defer`), because the response commit machinery subscribes at the right moment and in order with other callbacks. Performing side effects eagerly when creating the supplier or returning an already-completed Mono can write headers at the wrong time.

**Never call `block()`, synchronous DB/JDBC, synchronous HTTP clients, or sleep inside a beforeCommit callback**: it may run on an I/O/event-loop thread. Perform only lightweight, deterministic, non-network work.

### 6.4. `isCommitted` is not a rollback tool

~~~java
if (!response.isCommitted()) {
    response.setStatusCode(HttpStatus.BAD_REQUEST);
}
~~~

This check can help decide error handling, yet races can still happen as the response stream is committing. Do not use it to promise that changing status will always succeed; `setStatusCode` returns a boolean and response writes/errors must be coordinated through the pipeline.

Once HTTP headers/body have been sent, you usually **cannot** change status 200 to 500 and write an arbitrary ProblemDetail JSON; this is especially true for SSE and streaming responses.

### 6.5. `setComplete()`

~~~java
response.setStatusCode(HttpStatus.NO_CONTENT);
return response.setComplete();
~~~

Suitable for **204 No Content** responses with no body. `setComplete()` returns `Mono<Void>`, which must be **returned** to WebFlux or composed into the pipeline so the framework executes it. Calling the method and discarding its Mono does not guarantee completion.

## 7. Writing response bodies: `writeWith` and `writeAndFlushWith`

### 7.1. `writeWith`

~~~java
byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
response.getHeaders().setContentType(
        new MediaType("text", "plain", StandardCharsets.UTF_8));

return response.writeWith(Mono.fromSupplier(
        () -> response.bufferFactory().wrap(bytes)));
~~~

This fragment belongs to a handler returning `Mono<Void>`. `Mono.fromSupplier` defers output buffer creation until subscription; `writeWith` accepts a DataBuffer publisher and writes it to the HTTP transport.

No `subscribe()` or `block()` is needed; the controller returns the Mono so WebFlux manages the lifecycle. If passing a `Flux<DataBuffer>` from request input to response output, ensure clear ownership/release of each buffer and enforce appropriate body limits.

### 7.2. `writeAndFlushWith`

When output consists of multiple buffer groups and you want to control flush boundaries per inner publisher:

~~~java
Flux<Publisher<DataBuffer>> groups = ...;
return response.writeAndFlushWith(groups);
~~~

This is **pseudocode** with undefined `groups`; it is not required for returning normal JSON. It is better suited to specific streaming scenarios; however, flushing depends on server/transport and does not guarantee each item arrives at the client as a separate TCP packet.

Do not use writeAndFlushWith for a small JSON response simply because its name mentions "flush". HTTP codecs or WebFlux `ResponseEntity<Flux<...>>`/SSE are often better controller-level APIs for streaming.

### 7.3. `Mono<Void>`, `Mono<T>`, and `ResponseEntity`

| Handler return type | Who determines body/status? |
| --- | --- |
| `Mono<DTO>` | WebFlux picks writer/codec, typically status 200 on success |
| `Mono<ResponseEntity<DTO>>` | When Mono emits, status, headers, and body from ResponseEntity are applied |
| `ResponseEntity<Mono<DTO>>` | Status/headers are available earlier, body is asynchronous |
| `Mono<Void>` after `ServerHttpResponse.writeWith(...)` | Application writes body directly to response |
| `Mono<Void>` after `ServerHttpResponse.setComplete()` | Application completes response with no body |

Never mix two response owners: if a controller has called `response.writeWith`, do not also return `Mono<ResponseEntity<?>>` from the same method, creating two paths competing to write body/status. Choose **one** approach.

## 8. `ServerWebExchange` and request attributes

A filter can attach metadata **for this request only**:

~~~java
exchange.getAttributes().put("demo.observed", Boolean.TRUE);
return chain.filter(exchange);
~~~

A downstream handler reads:

~~~java
Boolean observed =
        exchange.getAttribute("demo.observed");
~~~

Attributes live in a Map on the exchange:
- Suitable for flagging request checks, correlation metadata, or internal routing state.
- Not sent automatically to the client; response headers must be set separately.
- Not a session or cookie; they do not survive across independent requests.
- Not `Reactor Context`: switching threads in a reactive subscription does not turn attributes into ThreadLocal.
- Not a safe place to cache large byte arrays or secrets; avoid retaining unbounded body copies.

### 8.1. WebSession differs from exchange attributes

`exchange.getSession()` returns `Mono<WebSession>`. WebSession has its own lifecycle/persistence depending on the configured store. Merely **accessing** the session does not necessarily create a new session cookie right away; writing attributes or starting a new session can trigger persistence/cookies. Do not use request-scoped attributes as a session replacement, and do not use sessions to cache entire HTTP bodies.

### 8.2. Principal / security context

`exchange.getPrincipal()` returns the request's reactive principal per security integration. With Spring Security Reactive, `ReactiveSecurityContextHolder` and Reactor Context are the trusted places to access authentication in the pipeline. Never assign a principal from an `X-User` header unless it originates exclusively from a trusted authentication proxy with a protected and verified chain.

## 9. `WebFilter`: cross-cutting HTTP request/response safely

`WebFilter` has the signature:

~~~java
Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain);
~~~

It runs around handlers and can:
- Inspect method/path/header metadata before the handler.
- Set exchange attributes.
- Modify response headers **before commit**.
- Produce a short response and stop the chain when a decision is permitted at this layer.
- Measure duration with `doFinally` without blocking.

### 9.1. Setting response headers in the proper commit phase

~~~java
@Bean
WebFilter traceFilter() {
    return (exchange, chain) -> {
        exchange.getAttributes().put("demo.observed", true);

        exchange.getResponse().beforeCommit(() ->
                Mono.fromRunnable(() ->
                        exchange.getResponse().getHeaders().set(
                                "X-Demo-Filter", "observed")));

        return chain.filter(exchange);
    };
}
~~~

This code is nearly complete, needing `@Bean`, `WebFilter`, and `Mono`/a `@Configuration` class in a demo. **Do not read the body in the filter**; the response header is set at commit time so it applies to normal responses and many error responses if commit is still possible.

### 9.2. Why might `then(Mono.fromRunnable(...))` be too late?

An easy-to-misuse pattern:

~~~java
return chain.filter(exchange)
        .then(Mono.fromRunnable(() ->
                exchange.getResponse().getHeaders()
                        .set("X-Late-Header", "value")));
~~~

For many handlers, the chain completes **after the response has already been written/committed**, so setting a header in `then` may have no effect or encounter a read-only state. To add a header right before commit, use `beforeCommit`.

### 9.3. Do not manipulate bodies arbitrarily in filters

To adjust request headers/URI via a request wrapper, use the builder:

~~~java
ServerHttpRequest request = exchange.getRequest().mutate()
        .header("X-Internal-Demo", "checked")
        .build();

ServerWebExchange updated =
        exchange.mutate().request(request).build();

return chain.filter(updated);
~~~

This is a fragment inside a WebFilter; only add internal headers when you have a clear trust boundary. For pre-existing untrusted headers, **remove/replace** them using the appropriate API rather than appending a second value and trusting `getFirst`: duplicate headers can cause request smuggling or identity confusion if different layers pick different values.

To actually **alter the body**, you need a `ServerHttpRequestDecorator` overriding `getBody()` with proper buffer retain/release, backpressure, content length, and cleanup. Never change a body while leaving a stale `Content-Length` or incompatible content encoding.

### 9.4. Filter order and Spring Security

Apps using reactive Spring Security have a `SecurityWebFilterChain` and WebFilters requiring clear ordering. Custom filters must not be treated as replacements for authorization/CSRF/CORS. Decorating requests/responses does not alter user permissions on its own.

If a filter returns 401/403 itself, ensure proper response format, auth challenges, correlation headers, and no private detail leaks; better yet, use Spring Security's dedicated exception handlers/entry points.

## 10. Servlet vs WebFlux: easily confused similarities

| Topic | Servlet MVC | WebFlux |
| --- | --- | --- |
| Low-level request | `HttpServletRequest` | `ServerHttpRequest` |
| Low-level response | `HttpServletResponse` | `ServerHttpResponse` |
| Request/response bridge | Servlet request + response arguments | `ServerWebExchange` |
| Body | `ServletInputStream` or argument resolver | `Flux<DataBuffer>` or reactive codecs |
| Filter | `jakarta.servlet.Filter` | `WebFilter` |
| Controller input body | `@RequestBody DTO` | `@RequestBody Mono<DTO>` or DTO per contract |
| Low-level response body | `ServletOutputStream` | `writeWith(Publisher<DataBuffer>)` |
| Completion | Servlet return/async lifecycle | `Mono<Void>` completion |
| Buffer ownership | Servlet streams/server implementation | DataBuffer lifecycle requiring explicit release care |
| Async dispatch | Servlet `DispatcherType.ASYNC` may apply | Reactor/Reactive server pipeline, not identical to MVC async dispatch |

Never import `org.springframework.web.servlet.function.ServerRequest` into WebFlux or try to construct `HttpServletRequest` in a Reactor Netty app with no Servlet container.

**Point to remember:** "Reactive HTTP server" does not mean you may handle bodies synchronously via `.block()`. `ServerHttpRequest.getBody().collectList().block()` on the event loop both blocks a thread and accumulates unbounded memory.

## 11. Complete example: Spring Boot 3.3.5 / Java 17 / WebFlux

The demo application has five routes:
1. `GET /api/request`: reads method, path, query `q`, checks custom header/cookie presence, reads an exchange attribute set by WebFilter; response includes `Cache-Control: no-store`.
2. `POST /api/notes`: JSON body into a record via `@RequestBody Mono<NoteInput>`, returns HTTP 201 with DTO, without reading raw DataBuffers.
3. `POST /api/raw-echo`: reads `ServerHttpRequest.getBody()` **bounded to 1024 bytes**, copies and releases the joined DataBuffer; creates a UTF-8 response body via `ServerHttpResponse.writeWith`, returning 413 if exceeded.
4. `GET /api/commit`: sets status 204, `beforeCommit` adds a header, `setComplete` returns Mono.
5. `GET /api/cookie`: uses `ResponseCookie` to emit Set-Cookie with HttpOnly, SameSite, and Path.

Every route gets `X-Demo-Filter: observed` attached by WebFilter at commit time. The demo needs no database, accounts, or network dependencies. Spring Security starter is omitted in the example project; **production requires proper security**.

~~~text
webflux-http-foundation/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/httpfoundation/
    │   ├── HttpFoundationApplication.java
    │   ├── web/ExchangeObservationFilter.java
    │   └── web/HttpFoundationController.java
    └── test/java/com/example/httpfoundation/
        └── HttpFoundationIntegrationTest.java
~~~

### 11.1. Gradle build

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-http-foundation'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use only `spring-boot-starter-webflux`; do not add `spring-boot-starter-web`. If both starters are present, Boot may default to the MVC application type, defeating the Reactor Netty WebFlux demo goal.

### 11.2. Main application

`src/main/java/com/example/httpfoundation/HttpFoundationApplication.java`:

~~~java
package com.example.httpfoundation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HttpFoundationApplication {

    public static void main(String[] args) {
        SpringApplication.run(HttpFoundationApplication.class, args);
    }
}
~~~

### 11.3. WebFilter setting exchange attribute and header before commit

`src/main/java/com/example/httpfoundation/web/ExchangeObservationFilter.java`:

~~~java
package com.example.httpfoundation.web;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class ExchangeObservationFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getAttributes().put("demo.observed", Boolean.TRUE);

        exchange.getResponse().beforeCommit(() ->
                Mono.fromRunnable(() ->
                        exchange.getResponse().getHeaders().set(
                                "X-Demo-Filter", "observed")));

        return chain.filter(exchange);
    }
}
~~~

This filter does **not** touch the body, does not block, and does not manually subscribe. It sets a marker on the exchange and registers a callback to write a header before commit. In real apps, if a filter needs to observe status/timeouts, consider `doFinally`, tracing libraries, and ensuring correlation data contains no secrets.

### 11.4. Controller: request metadata, JSON body, bounded raw body, commit, cookie

`src/main/java/com/example/httpfoundation/web/HttpFoundationController.java`:

~~~java
package com.example.httpfoundation.web;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.buffer.DataBufferLimitException;
import org.springframework.core.io.buffer.DataBufferUtils;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.http.ResponseEntity;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class HttpFoundationController {

    public record RequestSnapshot(
            String method, String path, String query,
            boolean hasDemoHeader, boolean hasDemoCookie,
            boolean observed) {}

    public record NoteInput(String text) {}

    public record NoteOutput(String text, int length) {}

    @GetMapping(path = "/request",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<RequestSnapshot> inspect(ServerWebExchange exchange) {
        ServerHttpRequest request = exchange.getRequest();
        ServerHttpResponse response = exchange.getResponse();

        String q = request.getQueryParams().getFirst("q");
        String safeQuery = q == null ? ""
                : q.substring(0, Math.min(q.length(), 64));

        response.getHeaders().setCacheControl("no-store");

        return Mono.just(new RequestSnapshot(
                request.getMethod().name(),
                request.getPath().pathWithinApplication().value(),
                safeQuery,
                request.getHeaders().containsKey("X-Demo-Client"),
                request.getCookies().containsKey("demo"),
                Boolean.TRUE.equals(
                        exchange.getAttribute("demo.observed"))));
    }

    @PostMapping(path = "/notes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<NoteOutput>> notes(
            @RequestBody Mono<NoteInput> input) {

        return input.map(note -> {
            String text = note.text();
            if (text == null || text.isBlank()
                    || text.length() > 120) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST, "Invalid note text");
            }

            String normalized = text.trim();
            NoteOutput output =
                    new NoteOutput(normalized, normalized.length());

            return ResponseEntity.created(URI.create("/api/notes/1"))
                    .header(HttpHeaders.CACHE_CONTROL, "no-store")
                    .body(output);
        });
    }

    @PostMapping(path = "/raw-echo",
            consumes = MediaType.TEXT_PLAIN_VALUE)
    public Mono<Void> rawEcho(
            ServerHttpRequest request, ServerHttpResponse response) {

        response.getHeaders().setContentType(
                new MediaType(
                        "text", "plain", StandardCharsets.UTF_8));
        response.getHeaders().setCacheControl("no-store");

        Mono<byte[]> content =
                DataBufferUtils.join(request.getBody(), 1024)
                        .map(buffer -> {
                            try {
                                byte[] bytes =
                                        new byte[buffer.readableByteCount()];
                                buffer.read(bytes);
                                return bytes;
                            } finally {
                                DataBufferUtils.release(buffer);
                            }
                        })
                        .defaultIfEmpty(new byte[0]);

        return content
                .flatMap(bytes -> response.writeWith(
                        Mono.fromSupplier(() ->
                                response.bufferFactory().wrap(bytes))))
                .onErrorResume(DataBufferLimitException.class, error -> {
                    response.setStatusCode(
                            HttpStatus.valueOf(413));
                    return response.setComplete();
                });
    }

    @GetMapping("/commit")
    public Mono<Void> commit(ServerHttpResponse response) {
        response.setStatusCode(HttpStatus.NO_CONTENT);
        response.beforeCommit(() ->
                Mono.fromRunnable(() ->
                        response.getHeaders().set(
                                "X-Commit-Phase", "ready")));
        return response.setComplete();
    }

    @GetMapping("/cookie")
    public Mono<Void> cookie(ServerHttpResponse response) {
        response.addCookie(ResponseCookie.from("demo", "ok")
                .path("/")
                .httpOnly(true)
                .sameSite("Lax")
                .build());
        response.setStatusCode(HttpStatus.NO_CONTENT);
        return response.setComplete();
    }
}
~~~

### 11.5. Explaining ownership properly in raw echo

`rawEcho` is the most critical part:
1. Only this endpoint calls `request.getBody()` directly; no `@RequestBody` competes for the same body.
2. `DataBufferUtils.join(...,1024)` caps aggregated bytes. Exceeding 1024 raises `DataBufferLimitException`.
3. `map(buffer -> {... finally release(buffer)})` **copies** bytes into a Java array and releases the joined DataBuffer.
4. `response.writeWith(Mono.fromSupplier(...wrap(bytes)))` allocates a **new output buffer** and lets the response writer consume it.
5. When the body is empty, `defaultIfEmpty(new byte[0])` ensures a clean completion path instead of trying to write JSON.
6. If aggregation exceeds the limit before response commit, `onErrorResume` selects 413 and completes the response.
7. No manual `subscribe`, `block`, or `Thread.sleep`; Spring manages the reactive lifecycle.
8. This is an example for **small bodies**. For real file uploads/streaming, do not aggregate onto the heap, do not echo sensitive data, and use storage/stream APIs with request-size limits at ingress and in the application.

**Note on Java memory:** copying to `byte[]` means the data still briefly resides on the heap even though the original pooled buffer is released. Do not retain or log byte arrays containing credentials/PII. `no-store` on the response only instructs compliant HTTP caches not to store it; it does not erase copies from heap/application stores.

### 11.6. Why doesn't `@RequestBody Mono<NoteInput>` need DataBufferUtils.join?

In `/api/notes`, WebFlux's JSON reader parses the body for you. You work purely with DTOs:
- `@RequestBody Mono<NoteInput>` receives JSON asynchronously.
- Invalid input emits errors from the decoder or from `ResponseStatusException` inside `map`.
- `ResponseEntity.created(...)` sets 201, Location, and Cache-Control cleanly without manually calling `ServerHttpResponse.writeWith`.
- Because the demo has no DB, Location `/api/notes/1` only illustrates the contract; **there is no GET notes/1 endpoint**. In production, do not return a fake 201/Location without persisting the resource; use a repository and a real ID, or choose another response.

If automatic validation is desired, use Bean Validation with the Spring validation starter and `@Valid` on the DTO, while testing input constraints, media types, and error schemas. The demo checks text concisely without adding an extra dependency.

### 11.7. Why does `/api/commit` use 204 and write no body?

HTTP 204 No Content should not contain a response payload. `setComplete` returns a Mono for Spring to commit, invoke `beforeCommit`, and finish. Calling `writeWith` alongside `setComplete` on the same response creates two paths competing to commit; avoid that.

### 11.8. Safe cookies also depend on HTTPS and auth

The demo cookie named `demo` holds no secrets; `httpOnly(true)` and `sameSite("Lax")` simply illustrate the response cookie builder. For session cookies on production HTTPS, you usually need `secure(true)`, SameSite policies matching cross-site flows, rotation, expiration, and proper CSRF protection. Never assume a client holding a cookie automatically has authorization to read resources.

## 12. Testing WebFlux with WebTestClient

`WebTestClient` is the test HTTP client tailored for Spring WebFlux, capable of binding to an application context or connecting to an embedded server. Here we use `RANDOM_PORT` so requests travel through real Reactor Netty, verifying response body/headers after commit.

`src/test/java/com/example/httpfoundation/HttpFoundationIntegrationTest.java`:

~~~java
package com.example.httpfoundation;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class HttpFoundationIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void inspectUsesRequestMetadataAndExchangeAttribute() {
        client.get().uri("/api/request?q=hello")
                .header("X-Demo-Client", "yes")
                .cookie("demo", "ok")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .valueEquals(HttpHeaders.CACHE_CONTROL, "no-store")
                .expectHeader()
                    .valueEquals("X-Demo-Filter", "observed")
                .expectBody()
                .jsonPath("$.method").isEqualTo("GET")
                .jsonPath("$.path").isEqualTo("/api/request")
                .jsonPath("$.query").isEqualTo("hello")
                .jsonPath("$.hasDemoHeader").isEqualTo(true)
                .jsonPath("$.hasDemoCookie").isEqualTo(true)
                .jsonPath("$.observed").isEqualTo(true);
    }

    @Test
    void jsonBodyIsDecodedAndResponseStatusIs201() {
        client.post().uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("text", "Spring WebFlux"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader()
                    .valueEquals(HttpHeaders.LOCATION, "/api/notes/1")
                .expectHeader()
                    .valueEquals(HttpHeaders.CACHE_CONTROL, "no-store")
                .expectBody()
                .jsonPath("$.text").isEqualTo("Spring WebFlux")
                .jsonPath("$.length").isEqualTo(14);
    }

    @Test
    void invalidJsonDomainValueIsRejected() {
        client.post().uri("/api/notes")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("text", "  "))
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void smallRawBodyIsCopiedAndReturned() {
        client.post().uri("/api/raw-echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.TEXT_PLAIN)
                .expectBody(String.class).isEqualTo("hello");
    }

    @Test
    void rawBodyLimitIsEnforced() {
        client.post().uri("/api/raw-echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("a".repeat(1200))
                .exchange()
                .expectStatus().isEqualTo(413);
    }

    @Test
    void beforeCommitRunsAndNoContentHasNoBody() {
        client.get().uri("/api/commit")
                .exchange()
                .expectStatus().isNoContent()
                .expectHeader()
                    .valueEquals("X-Commit-Phase", "ready")
                .expectHeader()
                    .valueEquals("X-Demo-Filter", "observed")
                .expectBody().isEmpty();
    }

    @Test
    void responseCookieContainsSecurityAttributes() {
        client.get().uri("/api/cookie")
                .exchange()
                .expectStatus().isNoContent()
                .expectHeader().valueMatches(
                        HttpHeaders.SET_COOKIE, ".*demo=ok.*")
                .expectHeader().valueMatches(
                        HttpHeaders.SET_COOKIE, ".*HttpOnly.*")
                .expectHeader().valueMatches(
                        HttpHeaders.SET_COOKIE, ".*SameSite=Lax.*");
    }
}
~~~

**Checking test accuracy:** `"Spring WebFlux"` has 14 UTF-16 characters (`6 + 1 + 7`), so `length` is expected to be 14. If you change the input content, update the expected length according to Java `String.length()`; it is not the UTF-8 byte length when Vietnamese diacritics are present. Do not assert header ordering, timestamps, or server-generated IDs.

Run in a project with a Java 17-compatible Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

These tests do not prove under-load performance or proxy configuration. They verify application contracts on an embedded server. To verify real uploads, security, retries/cancellation, or streaming clients, separate integration/load tests are required.

## 13. Observing with curl

Start the project with `./gradlew bootRun` and invoke:

### 13.1. Metadata endpoint

~~~bash
curl -i 'http://localhost:8080/api/request?q=java' \
  -H 'X-Demo-Client: yes' \
  -H 'Cookie: demo=ok'
~~~

Expected HTTP 200, JSON like:

~~~json
{
  "method": "GET",
  "path": "/api/request",
  "query": "java",
  "hasDemoHeader": true,
  "hasDemoCookie": true,
  "observed": true
}
~~~

Important headers:

~~~http
Cache-Control: no-store
X-Demo-Filter: observed
Content-Type: application/json
~~~

The response may include other headers, compression, or chunked transfer depending on the server. Do not rely on JSON field order or header order.

### 13.2. Creating a JSON note

~~~bash
curl -i -X POST 'http://localhost:8080/api/notes' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Spring WebFlux"}'
~~~

Expected 201 Created, `Location: /api/notes/1`, `Cache-Control: no-store`, and body:

~~~json
{"text":"Spring WebFlux","length":14}
~~~

This is a **non-persistent demo**, so do not copy this hardcoded Location verbatim into production: use a repository to create a real resource or change the semantics/status.

### 13.3. Raw body echo and 413

~~~bash
curl -i -X POST 'http://localhost:8080/api/raw-echo' \
  -H 'Content-Type: text/plain' \
  --data-binary 'hello'
~~~

Result 200 text body:

~~~text
hello
~~~

If the body exceeds 1024 bytes, Spring code explicitly sets HTTP 413. You can generate a larger payload with OS tools to test (without sending private data). The demo limit does **not** represent all product request-size policies.

### 13.4. Commit and cookie

~~~bash
curl -i 'http://localhost:8080/api/commit'
curl -i 'http://localhost:8080/api/cookie'
~~~

`/api/commit` returns 204, headers `X-Commit-Phase: ready`, `X-Demo-Filter: observed`, and no body.

`/api/cookie` returns 204 with `Set-Cookie` containing `demo=ok`, `Path=/`, `HttpOnly`, and `SameSite=Lax`. The demo cookie omits `Secure` because the example runs over plain HTTP localhost. In real HTTPS/session products, enforce additional security policies.

## 14. The worst mistakes when handling request/response data

### 14.1. Reading the request body twice

**Wrong:**

~~~java
return DataBufferUtils.join(request.getBody())
        .doOnNext(this::logRaw)
        .then(chain.filter(exchange));
~~~

After the filter consumes it, the handler can receive an empty body, decoder errors, or complex lifecycle issues. The fragment also lacks release and byte limits. **Fix:** do not log raw bodies; if unavoidable, use a custom decorator with well-tested replay/buffer ownership, redaction, and limits.

### 14.2. `subscribe()` inside a WebFilter

~~~java
exchange.getRequest().getBody().subscribe(this::auditBuffer);
return chain.filter(exchange);
~~~

**Wrong** because it detaches a subscription outside the HTTP request lifecycle; the request source can be consumed/raced, errors/cancellations become hard to manage, and auditing is unreliable. Never use `subscribe` to "peek" at an HTTP body. Compose properly within the chain's Mono/Flux.

### 14.3. Unreleased buffers when consuming manually

~~~java
request.getBody().map(buffer -> {
    byte[] bytes = new byte[buffer.readableByteCount()];
    buffer.read(bytes);
    return bytes;
});
~~~

The code fragment above never releases pooled `DataBuffer`s; on Netty this risks memory leaks. Once taking ownership to process buffers, call `DataBufferUtils.release` per ownership rules, typically inside `finally`, and handle cancellation/discard properly.

### 14.4. Releasing a buffer before the writer uses it

~~~java
Flux<DataBuffer> broken = request.getBody()
        .doOnNext(DataBufferUtils::release);
return response.writeWith(broken);
~~~

**Wrong**: the writer may read an already-released buffer. When forwarding raw bodies directly, publisher ownership and lifecycle must stay consistent; never release upstream and then hand the exact same buffer to a downstream writer.

### 14.5. Writing headers after `chain.filter(...)` completes

~~~java
return chain.filter(exchange).then(
        Mono.fromRunnable(() ->
                exchange.getResponse().getHeaders()
                        .set("X-Late", "value")));
~~~

This can be too late because the response has already committed. Use `response.beforeCommit(() -> Mono.fromRunnable(...))` before calling the chain.

### 14.6. Setting status without returning the write/complete Mono

~~~java
response.setStatusCode(HttpStatus.NO_CONTENT);
response.setComplete();
return Mono.empty();
~~~

This code discards the `Mono<Void>` returned by `setComplete`; it may appear to work depending on external framework behavior yet **fails to express proper completion composition**. Prefer:

~~~java
response.setStatusCode(HttpStatus.NO_CONTENT);
return response.setComplete();
~~~

### 14.7. Combining manual writes with typed return bodies

Do not both call `response.writeWith(...)` and return `Mono<SomeDto>` from the same handler. The two mechanisms can race to commit/write the body, making consistent error/status handling difficult for the framework. If you want WebFlux to encode JSON, return a Mono DTO or ResponseEntity. If you want raw bytes, return `Mono<Void>` from the response writer.

### 14.8. Thinking ResponseCookie grants access by itself

A cookie value sent by a client can be tampered with or forged without proper signing/session infrastructure. `HttpCookie`/`ResponseCookie` are merely HTTP cookie representations; application authorization must use Spring Security and check principal/resource ownership.

### 14.9. Blindly trusting `X-Forwarded-For` or `Forwarded`

These headers can be injected by clients if a proxy has not stripped them. Configure trusted ingress and forwarded-header transformers/strategies properly; never base rate limits/authorization on an easily spoofed IP from raw headers.

### 14.10. Logging raw request bodies containing credentials

JSON bodies can contain passwords, OTPs, addresses, card data, or tokens. A WebFilter logging bodies across all routes easily leaks sensitive info through log pipelines. Log only necessary metadata, allowlist non-sensitive fields, enforce byte limits, and protect retention/access.

## 15. Buffering, streaming, and backpressure

### 15.1. A reactive body is not "one chunk = one message"

A `Flux<DataBuffer>` can emit buffers of varying sizes depending on Netty transport, TCP frames, and producer speed. One JSON line can span multiple buffers; one buffer can hold multiple lines. When parsing streaming JSON, use suitable codecs, delimiter-aware parsers, or protocol framing — never split by `onNext` events.

### 15.2. When to aggregate?

Aggregate when:
- Payloads are small, with a **maxByteCount**.
- A single DTO or whole-payload checksum is required.
- Streaming cannot be used and the memory budget is acceptable.
- A clear 413 error policy exists.

Do not aggregate when:
- Uploads are many MB/GB or of unknown size.
- High concurrency makes N × payload memory large.
- Data should stream to a file/object store or downstream.
- Bodies contain sensitive data that should not sit whole on the heap.

### 15.3. Backpressure

`Flux<DataBuffer>` is a Reactive Streams publisher, so downstream can regulate demand; however, do not assume every external source has infinite capacity or can always slow down without buffering. When response output is slow, Netty/codecs and subscriber cancellation propagate upstream. Any custom `flatMap`/`buffer`/`onBackpressureBuffer` needs explicit concurrency/buffer bounds.

### 15.4. `writeAndFlushWith` and SSE

For Server-Sent Events, what matters are event framing, flush cadence, heartbeats, error handling, and client reconnect. A custom `writeAndFlushWith` does not build the SSE protocol by itself. Spring WebFlux supports `ServerSentEvent<T>` and `text/event-stream` at the higher controller level; use that when appropriate instead of manual byte-level framing.

### 15.5. Once the response commits, error bodies are limited

If 200 status/headers and some bytes have already been sent, a subsequent exception usually cannot turn the response into a standard JSON 500. Streaming may need in-band error events, connection closure, or retry protocols. Always treat **errors before commit** and **errors after commit** as two distinct operational scenarios.

## 16. Request/response under errors and cancellation

### 16.1. Errors before request body decoding completes

Malformed JSON, wrong Content-Type headers, or bodies exceeding codec limits can cause decoders/handlers to emit errors before the application creates a response. WebFlux provides `WebExceptionHandler` and `@ExceptionHandler`, yet not every HTTP error is caught by a single advice (especially at security/proxy layers).

When returning errors:
- Keep statuses meaningful (400/401/403/404/413/415/422/429/500...).
- Do not echo raw bodies/SQL/internal stack traces.
- Do not return 200 with payload `{"error":"bad"}` when the contract is an HTTP error.
- Ensure appropriate Cache-Control when body/status relates to a user.
- Run integration tests through the real filter chain and gateway.

### 16.2. Client disconnect

If the client closes the connection mid-flight:
- The subscription may be canceled; exact behavior depends on server/adapter/timing.
- `doFinally` can observe `SignalType.CANCEL` in the relevant pipeline.
- Native/pooled buffers must be released via proper operators.
- Business side effects already committed to a DB will not roll back automatically.
- Do not assume the server can always send a 500 body after the client has disconnected.

### 16.3. Timeouts do not interrupt blocking calls

Adding `.timeout(Duration.ofSeconds(2))` to a request body or downstream publisher emits onError/cancel on timeout. However, blocking JDBC/client calls that ignore interruption can keep running. Avoid `block()` in WebFilters, response preCommit callbacks, and event-loop code. For legacy blocking work, use bounded workers and dependency-side timeouts.

## 17. Security and privacy when working with raw HTTP

### 17.1. Untrusted information coming from clients

The following are **not sufficient on their own for authentication/authorization**: `X-User`, `X-Tenant`, `X-Role`, `X-Forwarded-For`, `Cookie`, query parameter `?user`, URL segment `{tenant}`, hostname, or custom Origin.

If the infrastructure has a trusted identity proxy, ensure the proxy strips/rewrites spoofed identity headers, locks down origin network paths, and the application validates signed/trusted identity per contract. Never use `request.getHeaders().getFirst("X-Role")` to grant ADMIN directly.

### 17.2. Protecting cookies and tokens

- Session cookies: `Secure` over HTTPS, `HttpOnly`, appropriate `SameSite`.
- Bearer tokens: `Authorization` must be redacted in logs/traces.
- Error responses: do not echo tokens in `ProblemDetail.detail`.
- `Cache-Control: no-store` for highly sensitive content, or `private` if policy allows browser caching while forbidding shared caches.
- Do not use `Vary: Cookie` to replace no-store/private for user-specific bodies.
- Never send raw user details in custom trace headers.

### 17.3. CORS

Spring WebFlux provides CORS infrastructure; `Origin` is request metadata and `Access-Control-Allow-Origin` is a browser-policy response header. **CORS is not a user authorization mechanism**. Never write a WebFilter that echoes any arbitrary `Origin` with credentials enabled; use a proper allowlist, handle preflight, and ensure proper reactive Spring Security integration.

### 17.4. Header injection and response splitting

Never concatenate untrusted header/query values directly into response headers, `Location`, or `Set-Cookie` without validation/encoding. HTTP server runtimes often reject invalid header characters, yet you should not rely entirely on parsers for safety. When constructing redirect URLs, use a URI builder and allowlisted destinations; prevent open redirects and CRLF injection.

## 18. Troubleshooting: errors and how to investigate

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `@RequestBody` receives empty body | WebFilter already read `getBody()` | Avoid double consumption; use a proper replay decorator |
| Upload API increases direct memory | Pooled DataBuffers not released | Audit ownership/release/discard/cancel |
| `DataBufferLimitException` | Codec/join exceeded max bytes | Set sensible limits, stream large payloads, return 413 per policy |
| Controller returns no body despite setting headers | Returned unsubscribed/uncomposed Mono | Return `writeWith`/`setComplete` or typed response |
| Filter header does not appear | Set after response commit | Use `beforeCommit` |
| `IllegalStateException` modifying response headers | Headers already read-only/committed | Set earlier, check beforeCommit |
| 204 response still has a body | Wrote payload despite HTTP 204 | Only `setComplete`, no body |
| JSON POST returns 415 | Content-Type mismatches route/decoder | Check consumes and Content-Type |
| text/plain POST parses body wrong | Wrong charset or decoding per chunk manually | Decode UTF-8 properly via codec/bounded join |
| Duplicate GET query param ignored | Used `getFirst` | Define duplicate parameter policy |
| Cookies logged to files | Logging request headers/body unredacted | Allowlist logging and secrets policy |
| Response cookie not sent back by browser | Mismatched domain/path/SameSite/Secure/TLS | Check cookie attributes and browser behavior |
| Client IP is always the proxy | Reading `getRemoteAddress` behind CDN | Trusted forwarded-header configuration |
| Low CPU yet high latency | Blocking I/O / event-loop starvation | Thread dumps, eliminate blocking, bounded pools |
| WebFilter counts requests multiple times? | Non-idempotent custom instrumentation | Design per-request attributes and clear lifecycle |
| CORS header present yet browser blocks | Preflight/method/credentials mismatch | Inspect OPTIONS and CORS policy |
| Advice misses 401 from Security | Exception raised before handler | SecurityWebFilterChain handlers |
| Response already streaming when handler wants 500 | Headers/body already committed | Streaming-aware error protocol |
| WebTestClient passes yet CDN misbehaves | Cache/proxy has custom rules | End-to-end test via CDN, check Vary/Cache-Control |
| Buffer splits a UTF-8 character in half | Decoding chunks independently | Streaming codec / charset-aware decoder |
| Mono `block()` hangs Netty loop | Blocking API in reactive chain | Return/compose publishers; offload legacy calls |

### Practical debugging workflow

1. Confirm the app actually runs **Spring WebFlux/Netty** vs MVC/Servlet: check starters and runtime.
2. Identify the failing layer: gateway, WebFilter, handler mapping, decoder, controller, response writer, Security, or client.
3. Log method, path, Content-Type, Accept, status, request ID/trace ID; **never log raw credentials**.
4. Check if any code subscribes to the request body outside the pipeline.
5. Verify `DataBufferUtils.join`/`collectList` has a max size and releases on success/error/cancel.
6. If response headers are missing, verify they are set before commit or inside `beforeCommit`.
7. Confirm responses write via either typed returns or manual `writeWith`/`setComplete`, not mixed.
8. For unexpected statuses, check Spring Security/WebExceptionHandler/filter order.
9. For wrong client IP/redirect URLs, verify trusted forwarded headers and proxy rewrites.
10. Use WebTestClient integration tests on an embedded server, then test real gateway/CDN/browsers if present in production.

## 19. Checklist when writing WebFlux HTTP infrastructure

- [ ] Import the right `org.springframework.http.server.reactive.ServerHttpRequest/Response`.
- [ ] Use `ServerWebExchange` for request + response + attributes of one interaction.
- [ ] Never treat query/headers/cookies as authenticated identity.
- [ ] Never parse URIs by string splitting or trust all forwarded headers.
- [ ] Never read raw bodies across multiple filters/controllers at once.
- [ ] Use `@RequestBody Mono<T>`/codecs for JSON when raw bytes are unnecessary.
- [ ] When aggregating DataBuffers, set max bytes; release joined buffers after copying/consuming.
- [ ] Never release buffers whose ownership was transferred to the response writer.
- [ ] Never write raw bodies/tokens/PII to logs.
- [ ] Set status/headers/cookies before response commit; keep `beforeCommit` callbacks lazy/lightweight.
- [ ] Return `Mono<Void>` from `writeWith`/`setComplete`; never subscribe/block manually.
- [ ] Never mix manual writes with returning another body from an annotated controller.
- [ ] Distinguish error responses before vs after headers commit.
- [ ] Reject oversized uploads at gateway/server/application layers.
- [ ] Configure CORS, reactive Spring Security, cookies, and cache privacy explicitly.
- [ ] Bound memory/concurrency, measure cancellations/timeouts, and check reference leaks.
- [ ] Test metadata/query/headers/cookies, JSON, 204, 201, 413, and error behavior.
- [ ] For streaming/file uploads, use dedicated protocols/codecs rather than blind aggregation.
- [ ] Verify final headers after WebFilters/security/proxies, not just controller code.

### Self-check questions

**1.** Which package do `ServerHttpRequest` and `ServerHttpResponse` belong to?

**Answer:** `org.springframework.http.server.reactive`, not Servlet `HttpServletRequest`/`HttpServletResponse`.

**2.** Why is `request.getBody().next()` not a way to read complete JSON?

**Answer:** It only takes the first DataBuffer chunk; the body may span multiple buffers that do not align with JSON boundaries.

**3.** Can a WebFilter read the request body and let the controller read it again normally?

**Answer:** Not guaranteed. Raw bodies are normally single-consumer streams; a properly engineered replay decorator is needed if strictly required, otherwise do not consume in the filter.

**4.** When manually reading a joined pooled DataBuffer into a byte array, what must you do?

**Answer:** Copy the bytes, ensure `DataBufferUtils.release` in `finally`; also handle size limits and error/cancellation.

**5.** How does `response.beforeCommit(...)` differ from `chain.filter(exchange).then(...)`?

**Answer:** The beforeCommit callback runs right before commit; `then` after the chain may be too late to modify response headers.

**6.** Why does `writeWith(...)` return `Mono<Void>`?

**Answer:** Writing the body is a reactive operation with completion/errors; you must return/compose the Mono so the framework subscribes along the proper lifecycle without blocking.

**7.** When returning `Mono<DTO>`, is it necessary to call `ServerHttpResponse.writeWith` manually?

**Answer:** No. Spring WebFlux codecs encode the DTO; only use raw writes when lower-level byte/streaming control is needed.

**8.** How do `HttpCookie` and `ResponseCookie` differ?

**Answer:** HttpCookie is a cookie read from the request; ResponseCookie builds a cookie the server sends via Set-Cookie with attributes like Path, HttpOnly, SameSite, and Secure.

**9.** Is `exchange.getAttributes()` a session?

**Answer:** No. Attributes belong to a single request/response interaction; WebSession has its own lifecycle and is obtained via `getSession()`.

**10.** Can `X-Forwarded-For` be used directly as a trusted client IP?

**Answer:** No without trusted proxy configuration; attackers can spoof the header.

**11.** Why can't you change HTTP status from 200 to 500 after streaming bytes?

**Answer:** The response has already committed headers/status and possibly sent body bytes; streaming-appropriate error handling is needed instead of promising status changes post-commit.

## 20. Official documentation

- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): WebFlux model, HTTP server adapters, handler infrastructure.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): HandlerMapping, HandlerAdapter, HandlerResultHandler.
- [Spring Framework — WebFlux Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): `ServerHttpRequest`, `ServerHttpResponse`, and `ServerWebExchange` in annotated controllers.
- [Spring Framework — ServerHttpRequest 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpRequest.html): request method/URI/headers/cookies/body APIs.
- [Spring Framework — ServerHttpResponse 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/server/reactive/ServerHttpResponse.html): status, cookies, headers, response writing, commit.
- [Spring Framework — ServerWebExchange 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/ServerWebExchange.html): request/response interaction, session, attributes, mutator.
- [Spring Framework — WebFilter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebFilter.html): reactive middleware contract.
- [Spring Framework — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html): DataBufferFactory, pooled buffers, release, join, and codecs.
- [Spring Framework — DataBufferUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/buffer/DataBufferUtils.html): bounded join, retain/release, and stream utilities.
- [Spring Framework — ReactiveHttpOutputMessage Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/http/ReactiveHttpOutputMessage.html): `beforeCommit`, `isCommitted`, `writeWith`, `writeAndFlushWith`, `setComplete`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP integration testing.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): dependencies/runtime server and configuration.
- [Spring Framework — CORS for WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): browser cross-origin and reactive security integration.
- [Spring Security — WebFlux](https://docs.spring.io/spring-security/reference/reactive/index.html): reactive SecurityWebFilterChain and context.

**Takeaway:** `ServerHttpRequest` provides incoming metadata and the body as `Flux<DataBuffer>`; `ServerHttpResponse` is where you set status/headers/cookies and write reactive output. `ServerWebExchange` connects them to the lifecycle of one HTTP request. Prefer Spring codecs/DTOs whenever possible, avoid consuming bodies multiple times, respect buffer ownership, enforce size limits, and decide headers before commit. When working with raw HTTP infrastructure, test on real WebFlux/Netty rather than trusting a method merely because it returns `Mono`.
