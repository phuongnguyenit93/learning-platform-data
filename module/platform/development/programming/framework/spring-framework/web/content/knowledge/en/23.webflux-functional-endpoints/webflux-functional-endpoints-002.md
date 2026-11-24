# ServerRequest, ServerResponse, and the Asynchronous Contract in Functional WebFlux

## 1. What is Functional WebFlux and what problem does this lesson solve?

Spring WebFlux offers two common ways to create HTTP endpoints: annotated controllers (`@RestController`, `@GetMapping`, `@RequestBody`) and **functional endpoints** or **WebFlux.fn**. In WebFlux.fn, you express route selection and request handling as Java functions without placing annotations on each HTTP handler.

Three core types belong to the package **`org.springframework.web.reactive.function.server`**:

- `ServerRequest` describes an HTTP request with a convenient, immutable contract: method, path, URI, query, headers, path variables, cookies, and body publishers.
- `HandlerFunction<T extends ServerResponse>` accepts a `ServerRequest` and returns **`Mono<T>`**, a publisher representing an **asynchronously** produced response.
- `ServerResponse` describes an HTTP response including status, headers, cookies, and body. Its builder also returns **`Mono<ServerResponse>`**.

The connecting component is `RouterFunction<T extends ServerResponse>`: it takes a `ServerRequest` and returns **`Mono<HandlerFunction<T>>`** when matched; if not matched, the publisher completes empty. In normal applications you do not invoke the router per request yourself; instead you register a `RouterFunction<ServerResponse>` Spring bean or deploy an `HttpHandler`.

**Most important goal:** understand *two distinct asynchronous contracts*:

1. **Routing phase:** `Mono<HandlerFunction<ServerResponse>>` — finds the handler matching the request; may be empty when nothing matches.
2. **Handling phase:** `Mono<ServerResponse>` — after matching, the handler can await reactive data and then produce a response with the appropriate status/headers/body.

From this, you can see why `Mono.empty()` for **no route match** differs from `Mono.empty()` for **entity not found**, and why a response can in turn hold a `Flux<T>` body emitting multiple elements.

### 1.1. Learning outcomes

After this lesson, you will be able to:

1. Explain using standard Java signatures: `ServerRequest → Mono<HandlerFunction> → Mono<ServerResponse>`.
2. Distinguish WebFlux.fn from **WebMvc.fn** on Servlet without mixing up package imports.
3. Read HTTP requests using `pathVariable`, `queryParam`, `headers`, `bodyToMono`, and `bodyToFlux`.
4. Build HTTP responses 200/201/204/400/404/409/429; compare `bodyValue`, `body(publisher, elementClass)`, and `build()`.
5. Understand assembly, subscription, non-blocking execution, error/completion/cancellation, codecs, backpressure, and streaming media types.
6. Register `RouterFunctions.route()`, understand first-match ordering, `RequestPredicates`, nested/composed routes, and `HandlerFilterFunction`.
7. Separate handlers/services and safeguard validation, authentication, authorization, CORS, CSRF, and shared resources.
8. Build a Spring Boot 3/Java 17 project with reactive CRUD without a database, `WebTestClient` HTTP tests, and Reactor `StepVerifier` tests.

**Scope:** Spring Framework 6.x, Spring Boot 3.3.x, Project Reactor 3.x. The main example runs with **spring-boot-starter-webflux** on Reactor Netty by default, without porting to Spring MVC Servlet. The project uses an in-memory store to isolate WebFlux.fn principles cleanly; production uses reactive database/HTTP clients with real timeouts and security.

## 2. Comparing the contract with WebMvc.fn: same names, different nature

A common mistake is importing `org.springframework.web.servlet.function.ServerRequest` instead of `org.springframework.web.reactive.function.server.ServerRequest`. The two APIs share similar names but are not interchangeable.

| Aspect | WebMvc.fn (Servlet) | WebFlux.fn (Reactive) |
| --- | --- | --- |
| Package | `org.springframework.web.servlet.function` | `org.springframework.web.reactive.function.server` |
| HTTP infrastructure | `DispatcherServlet` | `DispatcherHandler` |
| Route result | `Optional<HandlerFunction<ServerResponse>>` | `Mono<HandlerFunction<ServerResponse>>` |
| Handler result | `ServerResponse` | `Mono<ServerResponse>` |
| Read DTO body | `request.body(MyDto.class)` | `request.bodyToMono(MyDto.class)` |
| Read sequence body | `request.body(new ParameterizedTypeReference<...>())` | `request.bodyToFlux(MyDto.class)` |
| Response with data | `ServerResponse.ok().body(dto)` | `ServerResponse.ok().bodyValue(dto)` |
| Response with Publisher | Has separate integrations, not core contract | `.body(flux, Item.class)` |
| Functional routing filter | Synchronous Servlet `HandlerFilterFunction` | WebFlux `HandlerFilterFunction` returning `Mono<ServerResponse>` |
| Application-wide web filtering | Servlet `Filter` or interceptor | Reactive `WebFilter` |
| Purpose | Functional routing on Servlet | Functional routing on a reactive HTTP runtime |

**Correct imports:**

```java
import org.springframework.web.reactive.function.server.HandlerFunction;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
```

**Wrong imports in this lesson:**

```java
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;
```

Both share the type name `ServerResponse`, but in WebFlux the builder completes with a **`Mono`**. Therefore:

```java
// WEBFLUX.FN — correct signature
HandlerFunction<ServerResponse> hello =
    request -> ServerResponse.ok().bodyValue("Hello");

// WEBMVC.FN — signature from a DIFFERENT stack
// HandlerFunction<ServerResponse> hello =
//    request -> ServerResponse.ok().body("Hello");
```

The snippet above is illustrative inside a class with the proper reactive imports and can be used inside a method with matching types. Having the WebFlux dependency alone is not enough if Spring Boot also pulls in `spring-boot-starter-web`: when both starters are present, Boot typically prefers Servlet MVC. Verify the web application type via configuration and startup logs rather than guessing from controller names.

## 3. Mapping the two phases: routing and handling

Basic flow:

```text
HTTP GET /api/notes/7
      │
      ▼
Reactor Netty inbound Channel
      ▼
WebFlux HttpHandler / WebHandler / WebFilter
      ▼
DispatcherHandler
      ▼
RouterFunctionMapping
      │
      └── RouterFunction.route(ServerRequest)
             │
             ├── No match: Mono.empty()
             │       → tries next route/mapping, eventually may return 404
             │
             └── Match: Mono.just(HandlerFunction)
                          │
                          ▼
                  HandlerFunction.handle(ServerRequest)
                          │
                          └── Mono<ServerResponse>
                               │
                               ├── DB/WebClient publisher completes
                               ├── selects HTTP status + headers
                               ├── ServerResponseResultHandler
                               └── ServerResponse.writeTo(response,...)
                                      │
                                      ▼
                                HTTP codecs + response body Publisher
                                      │
                                      ▼
                                  Client
```

From the official API perspective, the abbreviated contracts:

```java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}

// Abbreviated conceptual signature of RouterFunction:
Mono<HandlerFunction<T>> route(ServerRequest request);
```

This is **signature-level pseudocode** for study: Spring's actual interfaces have generic types, annotations, and additional methods depending on the version. Do not copy these declarations as two new interfaces shadowing Spring's names.

### 3.1. What does "asynchronous" mean?

`Mono<ServerResponse>` is a **Reactive Streams promise** to produce a response in the future, not a blocking `Future.get()`. The handler can assemble the publisher immediately, while data reading only begins when downstream subscribes:

```java
Mono<ServerResponse> response = service.find(id)
    .flatMap(note ->
        ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(note))
    .switchIfEmpty(ServerResponse.notFound().build());
```

If `service.find(id)` uses a reactive data driver, network/database waits do not require holding a thread idle. However, the code **does not turn blocking JDBC into non-blocking**; you must inspect dependencies and any synchronous mapping/validation functions.

### 3.2. "One response" does not mean "one body item"

`Mono<ServerResponse>` emits at most **one `ServerResponse` descriptor**; inside that descriptor, the body may contain:

- `String` or `Note`: single object/string body.
- `Mono<Note>`: async single-entity source.
- `Flux<Note>`: multiple entities or streaming data.
- `Flux<DataBuffer>`: byte chunks.
- No body: `ServerResponse.noContent().build()`.

Diagram:

```text
HandlerFunction:
  Mono<ServerResponse>                  (0..1 descriptor)

ServerResponse.body:
  Publisher<T>                          (0..N onNext, depending on publisher)

HTTP exchange:
  status/headers are sent once; body can stream until completion
```

**Do not confuse "router did not match" with "response body has no items".** If a route matches and the handler explicitly returns `ServerResponse.notFound().build()`, that is a valid HTTP 404 response. If the handler itself returns `Mono.empty()` instead of creating a descriptor, HTTP result behavior has no clearly defined status; avoid relying on that to represent entity-not-found.

### 3.3. Publishers have three core signals

```text
Subscriber receives onSubscribe
  → onNext(value) zero or more times
  → onComplete() OR onError(error)
```

A `Mono` emits at most one `onNext`, a `Flux` 0..N. Null cannot be emitted as `onNext`. Cancellation is a subscription-management signal, not equivalent to `onComplete`. On HTTP client disconnect, the transport can cancel the body publisher; cleanup must account for both error and cancel signals.

## 4. ServerRequest: reading method, URL, headers, params, and body reactively

`ServerRequest` is an immutable interface from the handler's perspective, offering more ergonomic APIs than accessing `ServerWebExchange` directly. It does not imply that the request body has already been parsed or cached into a Java object.

Common APIs:

| Data to read | API | Type / meaning |
| --- | --- | --- |
| HTTP method | `request.method()` | `HttpMethod` |
| URI | `request.uri()` | `URI` |
| Path | `request.path()` | path string |
| Path variable | `request.pathVariable("id")` | `String`, parse as needed |
| Query param | `request.queryParam("q")` | `Optional<String>` |
| All query params | `request.queryParams()` | `MultiValueMap<String,String>` |
| Headers | `request.headers()` | `ServerRequest.Headers` |
| First header | `request.headers().firstHeader("X-Trace-Id")` | nullable String |
| Content-Type | `request.headers().contentType()` | `Optional<MediaType>` |
| Accept | `request.headers().accept()` | `List<MediaType>` |
| Cookies | `request.cookies()` | `MultiValueMap<String,HttpCookie>` |
| Single-object body | `request.bodyToMono(Command.class)` | `Mono<Command>` |
| Multi-item body | `request.bodyToFlux(Event.class)` | `Flux<Event>` |
| Low-level HTTP | `request.exchange()` | `ServerWebExchange` |

These APIs can return an empty `Optional` when a query param is absent, or throw when a required path variable is missing from the mapping; do not treat them as already-validated input.

### 4.1. Reading path variables and validating types

Route:

```java
.GET("/api/notes/{id}", handler::get)
```

Inside the handler:

```java
String raw = request.pathVariable("id");
long id;
try {
    id = Long.parseLong(raw);
} catch (NumberFormatException e) {
    return ServerResponse.badRequest()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(Map.of("error", "invalid_id"));
}
```

This snippet lives inside a `Mono<ServerResponse> get(ServerRequest request)` method and cannot run standalone. Unlike annotated `@PathVariable long id`, a functional handler receives a `String` and converts/validates it manually. Place business invariants (positive ID, valid tenant) in the appropriate service/handler.

### 4.2. Query parameters

```java
String query = request.queryParam("q").orElse("").trim();
```

`?q=webflux` is a query param; `/api/notes/{id}` is a path variable. For multi-valued query parameters:

```java
List<String> tags = request.queryParams().getOrDefault(
        "tag", List.of());
```

This snippet requires `List` imports and a `ServerRequest request`. Never concatenate raw query strings into SQL. With R2DBC, use parameter binding from the repository/database API rather than building SQL manually from requests.

### 4.3. Headers

```java
String traceId = request.headers().firstHeader("X-Request-Id");

List<MediaType> accepted = request.headers().accept();

Optional<MediaType> contentType =
    request.headers().contentType();
```

Do not trust a client-supplied `X-Admin`/`X-Role` header for authorization. Authentication must rely on trusted credentials/context via Spring Security; business authorization must also check resource ownership.

### 4.4. JSON body to Mono<DTO>

```java
Mono<CreateNote> command =
    request.bodyToMono(CreateNote.class);
```

Key points:

- This is a **Publisher**; body decoding happens during reactive processing.
- An empty body can produce `Mono.empty()`. For POST endpoints requiring a body, define an explicit 400 error contract.
- Malformed JSON typically yields a codec decode error, not a successful empty completion.
- Unsupported media types can cause corresponding errors; test actual statuses in the running application.
- A request body stream normally cannot be read twice arbitrarily; the request body is a subscription-driven stream resource.
- Never call `request.bodyToMono(CreateNote.class).block()` on the WebFlux event loop.

### 4.5. Multiple objects with bodyToFlux

When the client sends compatible streaming JSON/NDJSON:

```java
Flux<Event> events = request.bodyToFlux(Event.class);
```

Each item is emitted according to the appropriate codec/media type. **An HTTP JSON array** and **an NDJSON stream** have different buffering, codec, and flush semantics, even though both can decode into a `Flux`. Do not build an API accepting a million items using an unbounded `collectList()` before validation; consider limits, backpressure, batching, timeouts, and mid-stream error handling.

### 4.6. ParameterizedTypeReference

For generic types:

```java
Mono<List<CreateNote>> items =
    request.bodyToMono(new ParameterizedTypeReference<
        List<CreateNote>>() {});
```

Requires importing `org.springframework.core.ParameterizedTypeReference`. Using `List<CreateNote>` as input decodes the whole JSON array into a `List`, which can hold large payloads in memory; enforce request body size limits and check codec buffer limits. For long streams, design an appropriate input media type and use `Flux`.

## 5. ServerResponse: status, headers, cookies, body, and completion

`ServerResponse` follows an immutable interface contract. Typically you obtain a builder from static factories and call a terminal method **returning `Mono<ServerResponse>`**.

| Goal | WebFlux.fn |
| --- | --- |
| 200 with an existing object | `ServerResponse.ok().bodyValue(note)` |
| 200 JSON from Flux | `ServerResponse.ok().contentType(APPLICATION_JSON).body(flux, Note.class)` |
| 201 + Location | `ServerResponse.created(uri).bodyValue(note)` |
| 202 Accepted | `ServerResponse.accepted().build()` |
| 204 No Content | `ServerResponse.noContent().build()` |
| 400 Bad Request | `ServerResponse.badRequest().bodyValue(error)` |
| 404 Not Found | `ServerResponse.notFound().build()` |
| 409 Conflict | `ServerResponse.status(HttpStatus.CONFLICT).bodyValue(error)` |
| 429 Too Many Requests | `ServerResponse.status(TOO_MANY_REQUESTS).bodyValue(error)` |
| 500 Internal Error | `ServerResponse.status(INTERNAL_SERVER_ERROR).build()` |

### 5.1. bodyValue: with an existing value

```java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("status", "ready"));
```

`bodyValue` is for an already-present object such as a DTO, `Map`, or `String`. **Do not pass a `Mono<Note>` to `bodyValue` expecting Reactor to serialize the data when the `Mono` completes.** For publishers, use `body(publisher, type)`.

### 5.2. body: a Publisher that can emit multiple values

```java
Flux<Note> notes = repository.findAll();

return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(notes, Note.class);
```

This snippet assumes an appropriate reactive repository. Spring uses message writers/codecs to serialize items. With `application/json` and a finite `Flux`, output is typically a **JSON array**. **Do not claim** that each item flushes immediately as in SSE when using `application/json`.

A `Mono`:

```java
Mono<Note> note = repository.findById(id);
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(note, Note.class);
```

If `note` is empty, the HTTP status in this example was already chosen as 200; to return 404 per business logic, await the source with `flatMap` before creating `ServerResponse`, as shown next.

### 5.3. Returning 404 based on reactive values

```java
return repository.findById(id)
    .flatMap(note ->
        ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(note))
    .switchIfEmpty(ServerResponse.notFound().build());
```

This is a critical WebFlux.fn idiom: **the response choice depends on whether the `Mono` emits an item or is empty**. If the source errors, the error propagates rather than turning into a 404.

### 5.4. 201 + Location when creating a resource

```java
return service.create(command)
    .flatMap(saved ->
        ServerResponse.created(
            URI.create("/api/notes/" + saved.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(saved));
```

`ServerResponse.created(uri)` sets status 201 and the `Location` header. Relative URIs work in demos; in production consider host, context path, and reverse proxies if clients require an absolute `Location`. Never take an untrusted `Host` header and assemble it directly into `Location`/an open redirect.

### 5.5. 204 without a body

```java
return ServerResponse.noContent().build();
```

On successful `DELETE`, 204 is the appropriate HTTP status when the contract returns no body. Here `Mono<ServerResponse>` **emits one descriptor** with status 204, while the response body has zero elements.

### 5.6. Headers and cookies

```java
return ServerResponse.ok()
    .header("X-API-Version", "1")
    .cacheControl(CacheControl.noCache())
    .bodyValue(Map.of("ok", true));
```

This snippet requires `CacheControl`/`Map` imports. `Set-Cookie` has `cookie(ResponseCookie)` on the builder, and session/auth cookies must carry appropriate `Secure`, `HttpOnly`, `SameSite`, and path/domain policies. `Cache-Control: no-cache` allows caching with revalidation, unlike `no-store`.

## 6. When is ServerResponse actually sent?

Several distinct moments occur:

1. Controller/Handler **assembly**: wires up the Reactor pipeline; may not yet invoke the service or read the body.
2. Subscription: the framework starts executing the `Publisher`.
3. `Mono<ServerResponse>` emits the descriptor: the framework knows the HTTP status, headers, and body publisher.
4. `ServerResponseResultHandler` writes the response through codecs as the body `Publisher` emits.
5. Body completes/errors/cancels; the HTTP exchange finishes or is aborted.

```text
Handler assembly             Mono<ServerResponse>
                                    │
Subscription                        ▼
Service I/O async             emits ServerResponse
                                    │
Response headers/status             ▼
HTTP writer subscribes        Flux<Note> body
                                    │
Output                             onNext() onNext() onComplete()
```

**Do not confuse "created the `Mono`" with "actually sent the HTTP response".** If a DB create/write side effect lives inside a reactive `Publisher`, it usually only executes when the corresponding subscription is triggered. Conversely, a side effect executed directly outside a factory (such as `Mono.just(blockingCall())`) still runs **before** subscription.

### 6.1. Eager vs lazy

Wrong for lazy I/O:

```java
Mono<Note> note = Mono.just(
    legacyBlockingRepository.load(id)); // load runs immediately
```

How to defer the call:

```java
Mono<Note> note =
    Mono.fromCallable(() -> legacyBlockingRepository.load(id));
```

However, `fromCallable` only makes the work lazy; **it does not make blocking JDBC non-blocking**. If you must bridge a synchronous API:

```java
Mono<Note> note =
    Mono.fromCallable(() -> legacyBlockingRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

These are **explanatory snippets** requiring real variables/classes, not standalone programs. `boundedElastic` has bounded threads/queues and still requires configured DB pools and timeouts; only R2DBC/reactive drivers provide true non-blocking I/O.

### 6.2. Do not call subscribe inside HandlerFunction to "run faster"

Anti-pattern:

```java
Mono<ServerResponse> create(ServerRequest request) {
    service.save(data).subscribe(); // fire-and-forget loses HTTP lifecycle
    return ServerResponse.accepted().build();
}
```

This risks duplicate execution, hides success/failure, breaks cancellation propagation, and responds "accepted" before confirming the business event. If the real goal is an async job, use a durable queue/job store and an HTTP 202 contract; if you want to finish saving and return 201, compose with `flatMap` or `then` instead of subscribing manually.

## 7. HTTP status, empty, and error: three easily confused layers

### 7.1. Router does not match

`RouterFunction.route(request)` can complete empty because path/method/media predicates do not match. The framework then tries other routers/handler mappings. If no handler fits, HTTP may end with 404 or a mapping-specific status.

### 7.2. Handler matches but business source is empty

`repository.findById(id)` returning `Mono.empty()` indicates the entity was not found. The handler is responsible for mapping this to HTTP 404 or an appropriate alternative. **Do not** return `Mono.empty()` as a response descriptor relying on the framework to infer 404.

### 7.3. Handler source errors

`repository.findById` returning `Mono.error(ex)` means **failure**, not "data does not exist". The error can pass through WebFlux exception handling into 4xx/5xx per policy. Avoid:

```java
return repository.findById(id)
    .onErrorResume(error -> Mono.empty());
```

because it can turn a database failure into HTTP 404 and mask an outage. Classified business errors (such as `DuplicateKeyException`) can map to 409; unknown errors should remain 5xx with safe internal logging.

### 7.4. Decision matrix

| Scenario | Reactive stream | Recommended HTTP contract |
| --- | --- | --- |
| No GET route matches | Router `Mono.empty` | 404 or status from mapping infrastructure |
| GET existing ID | `Mono<Note>` emits note | 200 + JSON |
| GET missing ID | `Mono<Note>` empty | Handler returns 404 |
| POST without body | `request.bodyToMono` empty | Handler returns 400 |
| POST blank title | Valid JSON DTO but invalid business data | Handler returns 400 |
| POST succeeds | Service `Mono<Note>` emits saved note | 201 + `Location` |
| DELETE succeeds | Service `Mono<Boolean>` true | 204 |
| DELETE missing ID | Service `Mono<Boolean>` false | 404 or 204 per defined contract |
| Service cannot reach DB | `Mono.error` | 5xx + monitoring; do not fake 404 |
| Stream already started then errors | `Flux` emits some items then errors | Status may be committed; protocol error/close |

## 8. RouterFunction: selecting handlers in order

Spring provides the `RouterFunctions.route()` builder:

```java
@Bean
RouterFunction<ServerResponse> routes(NoteHandler h) {
    return RouterFunctions.route()
        .GET("/api/notes/search", h::search)
        .GET("/api/notes", h::list)
        .GET("/api/notes/{id}", h::get)
        .POST("/api/notes", h::create)
        .DELETE("/api/notes/{id}", h::delete)
        .build();
}
```

WebFlux.fn **evaluates routes in declaration order**. `/api/notes/search` must precede `/api/notes/{id}`, because the path variable can capture the string `"search"`. Unlike annotated controller mappings, which typically select the most specific method.

### 8.1. RequestPredicate

Routes can match HTTP method, path, `Accept`, and `Content-Type`:

```java
return RouterFunctions.route()
    .GET("/api/notes", RequestPredicates.accept(
         MediaType.APPLICATION_JSON), handler::list)
    .POST("/api/notes", RequestPredicates.contentType(
         MediaType.APPLICATION_JSON), handler::create)
    .build();
```

This snippet replaces the route definition above and is not a standalone file. `Accept` specifies the representation the client wants; `Content-Type` describes the body format the client sends. Overly strict predicates cause requests to **not match** rather than fail decoding; actual statuses may depend on other mappings and WebFlux exception infrastructure. Test behavior end-to-end.

### 8.2. Nested routes

```java
return RouterFunctions.route()
    .path("/api/notes", b -> b
        .GET("/search", handler::search)
        .GET(handler::list)
        .GET("/{id}", handler::get)
        .POST(handler::create)
        .DELETE("/{id}", handler::delete))
    .build();
```

This is an **alternative** configuration; do not register it alongside a non-nested bean for the same URLs. Nested routes reduce prefix repetition. For root paths or trailing slashes, test the actual matcher rather than assuming all slashes normalize identically.

### 8.3. Composition

You can compose routers:

```java
RouterFunction<ServerResponse> apiRoutes = ...;
RouterFunction<ServerResponse> adminRoutes = ...;

RouterFunction<ServerResponse> all =
    apiRoutes.and(adminRoutes);
```

These snippets only illustrate composition when two router variables already exist. Ordering still matters, especially with `/**` or overly broad wildcards. Spring Boot can detect multiple `RouterFunction` beans, ordering/combining them via `RouterFunctionMapping`; if URLs overlap, define explicit ownership/order and write regression tests.

### 8.4. A router is not a business service

A sound design keeps `RouterFunction` focused on dispatching method/path/predicates; handlers read requests, validate, and call services; services handle business logic/transactions; repositories handle data access. Avoid stuffing a large CRUD surface into a single multi-hundred-line route lambda that becomes hard to test.

## 9. HandlerFilterFunction, before/after hooks, and WebFilter

Functional middleware:

```java
.filter((request, next) -> {
    String blocked = request.headers()
        .firstHeader("X-Demo-Flow");
    if ("reject".equals(blocked)) {
        return ServerResponse.status(HttpStatus.TOO_MANY_REQUESTS)
            .bodyValue(Map.of("error", "demo_filtered"));
    }
    return next.handle(request);
})
```

In WebFlux.fn, `next.handle(request)` returns `Mono<ServerResponse>`; a filter can short-circuit **by not calling `next`**. This example demonstrates observing middleware, **not real rate limiting or security**. The `X-Demo-Flow` header is client-controlled and must never be used for authentication or authorization.

### 9.1. Filters are asynchronous

A handler filter can compose operators:

```java
.filter((request, next) ->
    next.handle(request)
        .doOnNext(response -> {
            // lightweight diagnostics; response descriptor is available
        }))
```

This snippet requires a builder context and is not standalone. Never call `.block()` inside a filter, and avoid synchronous network I/O in callbacks. For exception handling, you can use Reactor `onErrorResume` with a clear filter policy or a framework `WebExceptionHandler`, without swallowing arbitrary errors.

### 9.2. before and after

The router builder offers hooks:

```java
.before(request -> ServerRequest.from(request)
    .header("X-Internal-Marker", "demo")
    .build())
.after((request, response) -> {
    // lightweight metrics/logging, do not log sensitive data
})
```

These snippets illustrate usage inside the `RouterFunction` builder; scope depends on root vs. nested builders. Check lifecycle behavior for your specific WebFlux version and never attempt to mutate the immutable request object directly.

### 9.3. Comparing layers

| Tool | Layer | When to use |
| --- | --- | --- |
| `HandlerFilterFunction` | A `RouterFunction` or route group | Pre/post or short-circuit logic attached to a group of routes |
| `WebFilter` | WebFlux `WebHandler` chain | Request ID, logging, security integration, CORS |
| `WebExceptionHandler` | Reactive exception handling | Error responses before commit |
| `SecurityWebFilterChain` | Reactive Spring Security | Authentication/authorization/CSRF |
| Servlet `Filter` | Servlet container/MVC | **Not** the primary mechanism when running WebFlux on Reactor Netty |
| MVC `HandlerInterceptor` | Servlet MVC handler chain | Not used for WebFlux.fn on Netty |

Spring WebFlux functional endpoints use `CorsWebFilter` when CORS is needed; do not rely on `@CrossOrigin` on a Java `HandlerFunction` as you would with annotated controllers. CORS is a browser policy, not a replacement for authorization.

## 10. How do request and response bodies handle backpressure?

A reactive request body is typically read as `Flux<DataBuffer>` and decoded into typed `Mono`/`Flux` objects. A response body `Flux<Note>` is passed by the encoder to the socket according to write readiness and the HTTP codec. **Reactive Streams provides demand** between publisher and subscriber; the HTTP/TCP transport also maintains its own buffers and flow control.

```text
Client upload body
   ↓ network packets / Reactor Netty
   ↓ Flux<DataBuffer> request body
   ↓ HttpMessageReader decode
   ↓ request.bodyToFlux(Event.class)
   ↓ Handler/service operators
   ↓ ServerResponse.body(publisher,Event.class)
   ↓ HttpMessageWriter / encoder
   ↓ socket write readiness / client
```

### 10.1. "Publisher" does not mean unbounded buffering is safe

- `bodyToMono(List.class)` may need to aggregate a large request body.
- `Flux.collectList()` must wait for completion and retain all items.
- `onBackpressureBuffer()` can grow heap memory without bound if unconfigured.
- Servers, proxies, and clients all have request body size/time limits that must align.
- External push producers may not fully respect demand; design overflow policies and metrics.

Spring Boot provides `spring.codec.max-in-memory-size` to configure codec aggregation limits in certain operations. This is **not** a total JVM RAM quota, nor are all long streams buffered in full.

### 10.2. JSON array and SSE are not the same

With `Content-Type: application/json`, a finite `Flux` typically encodes as a JSON array. Clients may only process it once the entire array arrives. If you need event streaming, choose `MediaType.TEXT_EVENT_STREAM` or `application/x-ndjson` when supported by client and server:

```java
Flux<String> events = Flux.interval(Duration.ofSeconds(1))
    .map(index -> "tick-" + index);

return ServerResponse.ok()
    .contentType(MediaType.TEXT_EVENT_STREAM)
    .body(events, String.class);
```

This snippet is used inside a handler and requires `Flux`, `Duration`, and `MediaType` imports. The demo in section 14 intentionally bounds events so connections do not stay open forever. For SSE in production, handle heartbeats, authorization, disconnect/cancel, replay policies, slow-consumer behavior, and reverse-proxy idle timeouts.

### 10.3. Committed responses and mid-stream errors

Once an HTTP 200 SSE stream has emitted headers and two events, an error on the third cannot reliably change the status to HTTP 500. Define a protocol-level error event or stream close/retry semantics; do not inject a raw JSON error object into an SSE stream without a defined protocol contract.

## 11. Asynchrony, schedulers, ThreadLocal, and error handling

### 11.1. Mono/Flux do not automatically spawn new threads

`Mono.just("ok").map(...)` may run on the subscribing thread. `Flux.range` typically emits synchronously on demand. Only truly async sources (`WebClient`/R2DBC/`interval`) or scheduler operators change execution threads.

- `subscribeOn(scheduler)` affects subscription and upstream execution.
- `publishOn(scheduler)` switches the execution context for downstream operators after it.
- `Schedulers.boundedElastic()` is more suitable for bridging **blocking** APIs with bounded concurrency.
- `Schedulers.parallel()` is meant for appropriate CPU-bound work, not for parking blocking JDBC threads.

### 11.2. Avoid block()

Anti-pattern inside a handler:

```java
Mono<ServerResponse> bad(ServerRequest request) {
    Note note = service.find(1L).block();
    return ServerResponse.ok().bodyValue(note);
}
```

On the Reactor Netty event loop, `block()` can throw `IllegalStateException` or cause event-loop starvation. Fix:

```java
Mono<ServerResponse> good(ServerRequest request) {
    return service.find(1L)
        .flatMap(note -> ServerResponse.ok().bodyValue(note))
        .switchIfEmpty(ServerResponse.notFound().build());
}
```

Both snippets assume a class with an appropriate `service`; only `good` reflects the recommended idiom. In `main` or tests at an imperative boundary, `block()` may be used when intentionally waiting, never inside reactive request handling.

### 11.3. Context is not an immutable thread-local

A request may switch threads. Do not expect `ThreadLocal`, MDC, Servlet-style Spring Security context, or JPA transaction holders to always retain the same values. Reactor uses a per-subscriber `Context`; Spring Security reactive context propagation has its own infrastructure. For auditing user/resource access, read the trusted principal and pass information via reactive APIs; do not casually copy mutable `SecurityContext` instances across worker threads.

### 11.4. Errors as Publisher signals

If the JSON body is invalid, `bodyToMono(Command.class)` can emit `onError` during decoding. If a service fails, `Mono.error(...)` propagates. Use `onErrorResume(SpecificBusinessException.class, ex -> ServerResponse.status(...).bodyValue(...))` for classified exceptions. Unclassified errors need a global error handler and correlated logs without leaking stack traces to clients.

### 11.5. Timeouts and cancellation

`Mono.timeout(Duration.ofSeconds(2))` is a publisher-level timeout, distinct from TCP connect/HTTP client response timeouts, pool acquisition timeouts, and business deadlines. When timeout/cancel propagates, a remote service may have already received the POST and side effects may continue; use idempotency, transactions, and retry policies. `doFinally` runs on complete/error/cancel for cleanup, but avoid blocking inside the callback.

## 12. Which real-world applications suit WebFlux.fn?

| Use case | Suitable? | Reason |
| --- | --- | --- |
| REST CRUD with reactive repositories | Suitable | Composes `Mono`/`Flux` cleanly with HTTP contracts |
| API proxy with non-blocking `WebClient` | Suitable | Avoids holding workers idle waiting on remote networks |
| Event streaming (SSE) | Suitable | Multi-item body `Publisher`, cancellation/backpressure |
| API entirely backed by blocking JPA/JDBC | Reconsider | Reactive wrappers do not make I/O non-blocking on their own |
| HTML SSR with templates | Possible with integration | WebFlux view resolvers/rendering or annotated controllers |
| Large legacy Servlet Filter/JSP stack | MVC may be smoother | Servlet integrations do not map 1:1 to Netty |
| Centralized/composable routing declarations | Suitable | `RouterFunction` builder groups routes cleanly |
| A few simple annotated controllers | Migration not mandatory | Annotated WebFlux API is also supported |
| Long-running multi-minute background jobs | Prefer durable job stores over holding HTTP | 202 + job ID, poll/status/events |

### 12.1. When should you use annotated WebFlux controllers?

If the team is already comfortable with DTO validation via `@Valid`, `@RequestBody`, controller advice, and OpenAPI generators, annotated WebFlux can feel more natural. WebFlux.fn is not the only way to get non-blocking I/O. Choose the style based on consistency and tooling; choosing the **WebFlux reactive stack** is a separate decision from choosing **functional vs. annotation routing**.

### 12.2. Manual validation in HandlerFunction

With functional routes, you typically read a DTO via `bodyToMono` and validate explicitly. For Jakarta Bean Validation, inject `jakarta.validation.Validator`, call `validator.validate(command)`, and map violations. Do not assume placing `@Valid` on a record makes `bodyToMono` automatically trigger method argument validation like `@RequestBody @Valid` in an annotated controller.

For uploads/forms, `ServerRequest.formData()`/`multipartData()` follow reactive semantics; manage file buffers, sizes, and `Part` lifecycles carefully.

## 13. Layered troubleshooting guide

| Symptom | Common cause | What to check |
| --- | --- | --- |
| Method returns `ServerResponse` but compiler wants `Mono<ServerResponse>` | Imported WebFlux.fn but used WebMvc.fn signature | Return the builder `Publisher` |
| Wrong `org.springframework.web.servlet.function` import | Mixed up stacks | Switch to `web.reactive.function.server` |
| `GET /api/notes/search` reports `invalid_id` | `/{id}` route declared before `/search` | Place static routes before variable routes |
| GET for missing entity returns 200 | Response built before `Mono.empty` resolves | Use `flatMap` + `switchIfEmpty` |
| Empty JSON request yields no response | `Mono.empty` not handled | Return explicit `badRequest` |
| `bodyValue(flux)` behaves unexpectedly | Passed publisher instead of plain value | Use `body(flux, Note.class)` |
| Spring Boot runs `DispatcherServlet` | Accidentally added `starter-web` | Keep only `starter-webflux` for reactive apps |
| Handler not found | `RouterFunction` is not a Spring bean | Register `@Bean`/router config |
| Record fails to serialize | Missing Jackson/codec dependency or incompatible DTO | Check `starter-webflux`, model, `Content-Type` |
| Client sends `text/plain` to JSON body route | Media type mismatch | `Content-Type` and codec handlers |
| `onErrorResume` masks DB error as 404 | Swallowed errors | Convert only specific business errors |
| Infinite `Flux` with `collectList` hangs | Waiting for completion that never arrives | Stream or take finite slice |
| Callback calls synchronous `RestTemplate`/JDBC | Blocks event loop | Use `WebClient`/R2DBC or offload appropriately |
| Browser CORS error while `curl` works | CORS is a browser policy | `CorsWebFilter`, `OPTIONS`, Security |
| Filter does not apply as expected | Nested filter scope differs from root | Inspect builder composition |
| `WebClient` times out despite idle inbound threads | Outbound connection pool/pending acquire full | Pool metrics, remote latency |
| Test uses `MockMvc` for Netty WebFlux | Wrong testing stack | Use `WebTestClient` |
| Router 404 while annotated handler returns 200 | Different mapping ordering | Check `RouterFunctionMapping`/`DispatcherHandler` |
| Handler fails after headers sent | Response already committed | Streaming protocol/error contract |
| Unexpected item delivery in response | `Flux` JSON vs. SSE writer | Media type, codec, backpressure |

## 14. Runnable demo: Spring Boot 3 + Java 17 + WebFlux.fn

Project goal: **demonstrate directly in code and HTTP responses that the WebFlux.fn contract is asynchronous** while services and middleware maintain proper HTTP semantics.

Endpoints:

- `GET /api/notes` → `Flux<Note>`, JSON array.
- `GET /api/notes/search?q=Spring` → filtered `Flux` from the in-memory service.
- `GET /api/notes/{id}` → `Mono<Note>` or `ServerResponse.notFound()`.
- `POST /api/notes` → JSON `CreateNote`, 400 when invalid, 201+`Location` when valid.
- `DELETE /api/notes/{id}` → 204 when deleted, 404 when absent.
- `GET /api/notes/events` → three SSE events from a `Flux` timer, demonstrating a multi-value body `Publisher`.
- `GET /api/ping` → uses `Mono.defer` to illustrate a `Publisher`-based response builder.
- `GET /annotated/ping` → an annotated WebFlux controller alongside the functional router.
- Functional filter demo `X-Demo-Flow: reject` → 429, not real security.

In-memory data resets on restart; `ConcurrentHashMap` and `AtomicLong` are used because multiple requests can execute concurrently. This is a self-study sample and **does not provide production authentication or rate limiting**.

### 14.1. File structure

```text
webflux-fn-contract/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── WebFluxFnApplication.java
    │   ├── Note.java
    │   ├── CreateNote.java
    │   ├── NoteService.java
    │   ├── NoteHandler.java
    │   ├── NoteRoutes.java
    │   └── AnnotatedPing.java
    └── test/java/example/
        ├── NoteApiTest.java
        └── NoteServiceTest.java
```

### 14.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>webflux-fn-contract</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

Do not add `spring-boot-starter-web` so Boot does not switch to Servlet MVC by default. `reactor-test` provides `StepVerifier`; `starter-test` provides JUnit 5 and `WebTestClient` testing support.

### 14.3. WebFluxFnApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxFnApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxFnApplication.class, args);
    }
}
```

### 14.4. Note.java and CreateNote.java

File `Note.java`:

```java
package example;

public record Note(long id, String title) {}
```

File `CreateNote.java`:

```java
package example;

public record CreateNote(String title) {}
```

The two records form separate DTO contracts. Never take owner/role from a client-supplied body and trust it as an authorization context. In production, add schema validation, whitespace constraints, and title length limits.

### 14.5. NoteService.java

```java
package example;

import java.util.Comparator;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class NoteService {

    private final Map<Long, Note> notes = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(2);

    public NoteService() {
        notes.put(1L, new Note(1L, "Spring WebFlux"));
    }

    public Flux<Note> list(String query) {
        String wanted = query.toLowerCase(Locale.ROOT);
        return Flux.defer(() ->
            Flux.fromIterable(notes.values())
                .filter(note -> note.title()
                    .toLowerCase(Locale.ROOT).contains(wanted))
                .sort(Comparator.comparingLong(Note::id))
        );
    }

    public Mono<Note> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(notes.get(id)));
    }

    public Mono<Note> create(CreateNote command) {
        return Mono.fromSupplier(() -> {
            long id = nextId.getAndIncrement();
            Note note = new Note(id, command.title().trim());
            notes.put(id, note);
            return note;
        });
    }

    public Mono<Boolean> delete(long id) {
        return Mono.fromSupplier(() -> notes.remove(id) != null);
    }
}
```

- `Flux.defer`/`Mono.defer` ensures each subscription observes the snapshot/value at subscription time; code does not query eagerly before subscribing.
- `ConcurrentHashMap` protects basic map operations and `AtomicLong` issues unique IDs within **one JVM instance**, not distributed persistence/transactions.
- `sort(...)` buffers the entire sequence. For 1 to a few notes in memory this is fine; with large datasets, sort and paginate **in the database query**, rather than pulling millions of records and sorting in a `Flux`.
- `create` must not be subscribed to twice if you want to avoid creating two notes. The HTTP framework manages normal subscriptions; production service APIs need idempotency keys for retried POSTs.
- This is a **cold reactive wrapper over small in-memory operations**, not proof of non-blocking DB I/O. Replace with R2DBC/reactive repositories in real systems.

### 14.6. NoteHandler.java

```java
package example;

import java.net.URI;
import java.time.Duration;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class NoteHandler {

    private final NoteService service;

    public NoteHandler(NoteService service) {
        this.service = service;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        String q = request.queryParam("q").orElse("").trim();

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(service.list(q), Note.class);
    }

    public Mono<ServerResponse> search(ServerRequest request) {
        return list(request);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        return service.find(id)
            .flatMap(note ->
                ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(note))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateNote.class)
            .flatMap(command -> {
                if (command.title() == null ||
                        command.title().isBlank()) {
                    return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                            "error", "title_required"));
                }

                if (command.title().trim().length() > 120) {
                    return ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                            "error", "title_too_long"));
                }

                return service.create(command)
                    .flatMap(saved -> ServerResponse.created(
                                URI.create("/api/notes/" + saved.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(saved));
            })
            .switchIfEmpty(ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("error", "body_required")));
    }

    public Mono<ServerResponse> delete(ServerRequest request) {
        Long id = parseId(request);
        if (id == null) {
            return badId();
        }

        return service.delete(id)
            .flatMap(existed -> existed
                ? ServerResponse.noContent().build()
                : ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> events(ServerRequest request) {
        Flux<String> source = Flux.interval(Duration.ofMillis(20))
            .take(3)
            .map(index -> "tick-" + index);

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(source, String.class);
    }

    public Mono<ServerResponse> ping(ServerRequest request) {
        return Mono.defer(() ->
            ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("status", "ready")));
    }

    private Long parseId(ServerRequest request) {
        try {
            long id = Long.parseLong(request.pathVariable("id"));
            return id > 0 ? id : null;
        } catch (NumberFormatException ex) {
            return null;
        }
    }

    private Mono<ServerResponse> badId() {
        return ServerResponse.badRequest()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("error", "invalid_id"));
    }
}
```

#### Why is this handler genuinely reactive?

Notice that the return type of **every** method is `Mono<ServerResponse>`. The handler never returns `ServerResponse` directly, and never calls `block()` or `subscribe()`.

- `list()` creates a response descriptor carrying a `Flux<Note>` body; the framework subscribes to the body when writing.
- `get()` awaits `service.find(id)`; only when the entity is empty does it build a 404 response. There is no accidental 200 response when data is absent.
- `create()` uses `bodyToMono(CreateNote.class)`, validates, and `flatMap`s to `service.create`. When the body is empty, `switchIfEmpty` returns 400.
- `delete()` converts `Mono<Boolean>` into 204/404 according to business rules.
- `events()` returns one response descriptor, while the body streams three additional values from a `Flux`.
- `ping()` uses `Mono.defer` to illustrate constructing the descriptor at subscription time.

**HTTP error note:** syntactically invalid JSON decoded by codecs can produce HTTP 400 via WebFlux exception handling, whereas the example only customizes `error: body_required/title_required/title_too_long` for cases checked by the handler. Do not hardcode expectations that every malformed JSON payload yields the exact same JSON error schema.

### 14.7. NoteRoutes.java

```java
package example;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class NoteRoutes {

    @Bean
    RouterFunction<ServerResponse> noteRouter(NoteHandler handler) {
        return RouterFunctions.route()
            .GET("/api/notes/search", handler::search)
            .GET("/api/notes/events", handler::events)
            .GET("/api/notes", handler::list)
            .GET("/api/notes/{id}", handler::get)
            .POST("/api/notes", handler::create)
            .DELETE("/api/notes/{id}", handler::delete)
            .GET("/api/ping", handler::ping)
            .filter((request, next) -> {
                if ("reject".equals(request.headers()
                        .firstHeader("X-Demo-Flow"))) {
                    return ServerResponse.status(
                            HttpStatus.TOO_MANY_REQUESTS)
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(Map.of(
                            "error", "demo_filtered"));
                }
                return next.handle(request);
            })
            .build();
    }
}
```

This uses a single router bean, avoiding ambiguity in concurrency/ordering across multiple beans. `/api/notes/search` and `/api/notes/events` are placed before `/api/notes/{id}`. The functional filter on the root builder applies to all routes built here (including `/api/ping`), but does not apply to the separate annotated controller in the next section.

`ServerResponse.status(429)` can be returned immediately from the filter; **there is no real authentication or security**. In a public app, never use a demo header like this for rate-limiting decisions, as clients can freely set or omit headers.

### 14.8. AnnotatedPing.java

```java
package example;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class AnnotatedPing {

    @GetMapping("/annotated/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("style", "annotated-webflux"));
    }
}
```

Spring Boot WebFlux can run `RouterFunction` and `@RestController` side by side on the same `DispatcherHandler`. Do not declare overlapping routes between the two styles unless you have an explicit handler-mapping order policy. A functional route returns `Mono<ServerResponse>`; an annotated REST route returns `Mono<DTO>` and lets the HTTP writer handle serialization.

### 14.9. Running the application

In the directory containing `pom.xml`, with JDK 17+, Maven, and dependency download access:

```bash
mvn test
mvn spring-boot:run
```

By default, the Netty server is expected to listen on port 8080 unless reconfigured. This is the **default configuration expectation**, not a claim that the tests were run in the current environment.

Read the seeded note:

```bash
curl -i http://localhost:8080/api/notes/1
```

HTTP 200 and JSON body structure:

```json
{"id":1,"title":"Spring WebFlux"}
```

Read non-existent ID:

```bash
curl -i http://localhost:8080/api/notes/999
```

HTTP 404; body may be framework-generated or empty, so do not assert raw error format.

List:

```bash
curl -i http://localhost:8080/api/notes
```

HTTP 200:

```json
[{"id":1,"title":"Spring WebFlux"}]
```

Static search route:

```bash
curl -i "http://localhost:8080/api/notes/search?q=Spring"
```

Expected HTTP 200 with one note. If the router order placed `/{id}` before `/search`, the string `"search"` would be parsed wrongly and lead to 400, so ordering is part of the contract behavior.

Create:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"Reactor API"}'
```

HTTP 201, `Location: /api/notes/2` on a freshly started app, body:

```json
{"id":2,"title":"Reactor API"}
```

If concurrent requests have already created notes, the ID is no longer guaranteed to be 2. Real clients should read the `Location` header.

Empty request body or blank title:

```bash
curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{}'

curl -i -X POST http://localhost:8080/api/notes \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
```

Both reach the handler with `CreateNote.title() == null` or blank, returning HTTP 400 with `error: title_required`. If **no request body at all** is sent, `bodyToMono` is empty and the handler returns `body_required`.

Delete the newly created ID:

```bash
curl -i -X DELETE http://localhost:8080/api/notes/2
```

If ID 2 exists, the result is 204 with no body. Calling `DELETE` again returns 404 per the demo policy. In another API, an idempotent `DELETE` might return 204 for both; **idempotent semantics do not require identical status codes** on repeated requests, only that the intended side effect remains stable.

Test filter:

```bash
curl -i -H "X-Demo-Flow: reject" \
  http://localhost:8080/api/notes
```

HTTP 429:

```json
{"error":"demo_filtered"}
```

SSE:

```bash
curl -N -i -H "Accept: text/event-stream" \
  http://localhost:8080/api/notes/events
```

Response `Content-Type` `text/event-stream`, body containing data for ticks 0, 1, 2. Event formatting and chunk boundaries are determined by codecs and transport; do not assert raw chunk byte boundaries as an API contract unless a strict event schema is designed.

Annotated endpoint:

```bash
curl -i http://localhost:8080/annotated/ping
```

JSON body:

```json
{"style":"annotated-webflux"}
```

The `curl` commands use POSIX shell syntax. On PowerShell, use `curl.exe` and adjust line continuations.

## 15. WebTestClient tests: verifying the final HTTP contract

Use `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `@AutoConfigureWebTestClient` to test the real embedded WebFlux server, codecs, `RouterFunction` bean, and handlers. Do not use `MockMvc` to draw conclusions about Reactor Netty in this demo.

File `src/test/java/example/NoteApiTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class NoteApiTest {

    @Autowired
    WebTestClient client;

    @Test
    void seededItemIsReadable() {
        client.get().uri("/api/notes/1")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.title").isEqualTo("Spring WebFlux");
    }

    @Test
    void missingEntityIsExplicit404() {
        client.get().uri("/api/notes/999999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void invalidPathVariableIs400() {
        client.get().uri("/api/notes/not-number")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
                .jsonPath("$.error").isEqualTo("invalid_id");
    }

    @Test
    void listEmitsJsonArray() {
        client.get().uri("/api/notes")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$[0].id").isEqualTo(1);
    }

    @Test
    void staticSearchRoutePrecedesIdRoute() {
        client.get().uri("/api/notes/search?q=Spring")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$[0].title").isEqualTo("Spring WebFlux");
    }

    @Test
    void noSearchResultsIsAnEmptyArray() {
        client.get().uri("/api/notes/search?q=NoMatchAtAll")
            .exchange()
            .expectStatus().isOk()
            .expectBody().json("[]");
    }

    @Test
    void blankTitleIs400() {
        client.post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"   \"}")
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
                .jsonPath("$.error").isEqualTo("title_required");
    }

    @Test
    void createReturns201LocationAndGetWorks() {
        String location = client.post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"New note\"}")
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
                .jsonPath("$.title").isEqualTo("New note")
                .returnResult()
                .getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);
        assertTrue(location.startsWith("/api/notes/"));

        client.get().uri(location)
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.title").isEqualTo("New note");
    }

    @Test
    void deletingCreatedItemReturns204Then404() {
        String location = client.post().uri("/api/notes")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"title\":\"Delete me\"}")
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
                .returnResult()
                .getResponseHeaders()
                .getFirst(HttpHeaders.LOCATION);

        assertNotNull(location);

        client.delete().uri(location)
            .exchange()
            .expectStatus().isNoContent()
            .expectBody().isEmpty();

        client.get().uri(location)
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void functionalFilterCanShortCircuit() {
        client.get().uri("/api/notes")
            .header("X-Demo-Flow", "reject")
            .exchange()
            .expectStatus().isEqualTo(429)
            .expectBody()
                .jsonPath("$.error").isEqualTo("demo_filtered");
    }

    @Test
    void pingReturnsReactiveResponseBuilder() {
        client.get().uri("/api/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.status").isEqualTo("ready");
    }

    @Test
    void annotatedHandlerCanCoexistWithFunctionalRouter() {
        client.get().uri("/annotated/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
                .jsonPath("$.style").isEqualTo("annotated-webflux");
    }

    @Test
    void eventStreamUsesSseMediaType() {
        client.get().uri("/api/notes/events")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM);
    }
}
```

**13 HTTP tests** in the class above verify the routes, statuses, and JSON fields. The create test reads `Location` from the response instead of hardcoding ID 2 to avoid test-order coupling. Because controller/service state in `@SpringBootTest` is shared across tests, a larger production suite should add cleanup/isolation or separate contexts. Do not assert thread/event-loop counts, as those are runtime implementation details.

### 15.1. Testing a RouterFunction in isolation without starting a server

Spring WebFlux allows `WebTestClient.bindToRouterFunction(router).build()` to test routers/handlers without starting a real network listener.

Snippet:

```java
WebTestClient client =
    WebTestClient.bindToRouterFunction(noteRouter).build();

client.get().uri("/api/ping")
    .exchange()
    .expectStatus().isOk();
```

Requires a constructed or injected `noteRouter` `RouterFunction` bean and matching imports. This is useful for routing-level unit/integration tests; the embedded Netty tests above add validation of server integration and auto-configuration.

### 15.2. Testing SSE in greater depth

To verify the **three actual events**, not just the media type, you can use:

```java
FluxExchangeResult<String> result =
    client.get().uri("/api/notes/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNext("tick-0", "tick-1", "tick-2")
    .verifyComplete();
```

This snippet requires `FluxExchangeResult`, `reactor.test.StepVerifier`, `MediaType` imports, and an existing `client` variable. Decoding SSE as `String` can depend on codec/accept setup; if discrepancies arise, prefer returning the body as `ServerSentEvent<String>` and asserting `event.data()` according to the negotiated SSE representation. Even when testing streams, avoid infinite runs and waiting without timeouts.

## 16. StepVerifier: testing reactive completion, empty, and side effects

HTTP tests ensure the app returns proper statuses/bodies; Reactor tests verify `Publisher` signals and are also useful for proving there is no hidden blocking `get()` in the code.

File `src/test/java/example/NoteServiceTest.java`:

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class NoteServiceTest {

    private NoteService service;

    @BeforeEach
    void setup() {
        service = new NoteService();
    }

    @Test
    void findExistsEmitsOneValueThenCompletes() {
        StepVerifier.create(service.find(1L))
            .expectNext(new Note(1L, "Spring WebFlux"))
            .verifyComplete();
    }

    @Test
    void findMissingCompletesEmptyNotError() {
        StepVerifier.create(service.find(777L))
            .verifyComplete();
    }

    @Test
    void listEmitsOneSeedItem() {
        StepVerifier.create(service.list("spring"))
            .expectNext(new Note(1L, "Spring WebFlux"))
            .verifyComplete();
    }

    @Test
    void createIsLazyAndDoesNotRunBeforeSubscribe() {
        var publisher = service.create(new CreateNote("Lazy"));
        StepVerifier.create(service.list("lazy"))
            .verifyComplete();

        StepVerifier.create(publisher)
            .assertNext(note -> {
                assertEquals(2L, note.id());
                assertEquals("Lazy", note.title());
            })
            .verifyComplete();
    }

    @Test
    void deleteIsFirstTrueThenFalse() {
        StepVerifier.create(service.delete(1L))
            .expectNext(true)
            .verifyComplete();

        StepVerifier.create(service.delete(1L))
            .expectNext(false)
            .verifyComplete();
    }
}
```

**5 Reactor `StepVerifier` tests** confirm that empty is not an error, note creation is lazy, and delete results are explicit. This does not prove high throughput or low latency on Netty; load testing, profiling, and fake/real reactive I/O drivers are needed to measure actual capacity.

## 17. Evolving into a production service

A real API needs additional layers rather than copying the in-memory demo verbatim:

### 17.1. Persistence

Use `ReactiveCrudRepository<NoteEntity,Long>`/R2DBC when you want a reactive relational database. For paginated resources, write queries with `LIMIT`/cursors rather than `findAll().collectList()` over an entire table. For transactions, use reactive transaction integration and verify context propagation.

### 17.2. Security and ownership

Spring Security WebFlux configures `SecurityWebFilterChain`. Route-level `HandlerFilterFunction` can add domain-specific checks, but it **does not** replace authentication, CSRF, or authorization by principal and resource/tenant. On POST/DELETE APIs, clients must not be granted privileges via a custom `X-Role` header.

### 17.3. HTTP preconditions and caching

If ETag/`Last-Modified` revalidation is needed for GETs, return appropriate headers/conditional responses based on a stable resource version. Do not hash an expensive full body and assume DB computation was saved; only early validation from metadata enables short-circuiting. For user-specific responses, consider `private`/`no-store` and `Vary`/`Accept-Encoding`.

### 17.4. Observability

Record metrics: route match/status/error counts, inbound active requests, event-loop lag, outbound `WebClient` pool active/pending counts, downstream latency, Reactor cancellations, buffer pressure, retries/backoff, and p95/p99. For tracing, use Reactor `Context` and Spring observability integrations rather than assuming `ThreadLocal` MDC propagates automatically.

### 17.5. Tests beyond WebTestClient

Add tests for malformed JSON, `Content-Type` mismatches, missing bodies, unknown/delete races, SSE complete/error/cancel, CORS preflight, CSRF, auth/role/tenant checks, and large-body limits. Load test with proxies/TLS/HTTP2 if your deployment includes those layers. Assert not only 200/201 paths, but also error paths, timeouts, and idempotency keys.

## 18. Common mistakes: from signatures to production

| Misconception | Why it is wrong | Fix |
| --- | --- | --- |
| "WebFlux.fn `HandlerFunction` returns `ServerResponse`" | It returns `Mono<ServerResponse>` | Use the reactive signature |
| "WebFlux `RouterFunction` returns `Optional`" | `Mono<HandlerFunction>` | Distinguish from WebMvc.fn |
| "`Mono<ServerResponse>` means a single-item response body" | The descriptor holds a 0..N body `Publisher` | Separate response and body lifecycles |
| "Router `Mono.empty` equals entity not found" | Two different phases | Separate route matching from service lookup |
| "`bodyToMono` returns the DTO immediately" | It returns a `Publisher` | `flatMap`/`map` |
| "`bodyToFlux` always has multiple items" | A `Flux` can be empty or emit one item | 0..N |
| "`ServerResponse.ok().bodyValue(flux)` auto-subscribes the `Flux`" | `bodyValue` is for value objects | Use `body(flux, Class)` |
| "Service `Mono.empty` automatically yields 404" | Status is not yet decided | `switchIfEmpty(notFound)` |
| "`Mono.error` also means no data" | Error differs from empty | Propagate/map errors properly |
| "Add `@RestController` to `HandlerFunction`" | `RouterFunction` bean defines the mapping | Register router and handler |
| "Having `starter-webflux` alone guarantees reactive" | `starter-web` can make Boot choose MVC | Check dependencies/context |
| "The `/search` route can go after `{id}`" | First match wins | Static routes first |
| "Request body can be read repeatedly" | Stream does not auto-replay | Decode once and reuse DTO |
| "`Mono.just(blocking())` is lazy" | Argument is eager | `defer`/`fromCallable` and scheduler |
| "`Mono.fromCallable` makes JDBC non-blocking" | Only defers execution | Offload or use a reactive driver |
| "Calling `block()` in Netty is normal" | Blocks event loop / throws exception | Compose reactive operations |
| "Calling `subscribe()` in a handler saves faster" | Breaks lifecycle/error/retry handling | Return/compose the `Publisher` |
| "Streams with backpressure can never OOM" | Hot sources/buffers still have limits | Bounded resource policies |
| "A `Flux` JSON array flushes on every `onNext`" | Codec/media type buffering differs | SSE/NDJSON when needed |
| "HTTP 200 SSE can switch to 500 after commit" | Headers are already committed | Event-level error/close |
| "A filter reading `X-Role` is security" | Clients can forge headers | `SecurityWebFilterChain`/authz |
| "Few event-loop threads makes responses free" | CPU/memory/buffers/connections still cost | Profile and cap concurrency |
| "CORS equals authorization" | CORS is a browser policy | Separate AuthN/AuthZ |
| "Reactor `Context` is `HttpSession`" | Different scope/lifecycle | Proper `Context`/principal |
| "Retrying POST is automatically safe" | Can duplicate side effects | Idempotency keys and dedupe |
| "`WebTestClient` passing proves Netty is fast" | Only verifies correctness | Load/performance tests |
| "Every R2DBC query streams row-by-row without buffering" | Drivers/queries/operators can aggregate | Measure data flow and paginate |

## 19. WebFlux.fn design checklist

Before finalizing an API:

1. [ ] Correct `org.springframework.web.reactive.function.server` imports.
2. [ ] Every `HandlerFunction` returns `Mono<ServerResponse>`; no blocking and no manual subscribing.
3. [ ] `RouterFunction` bean is detected by Boot/WebFlux; no duplicate annotated routes.
4. [ ] Specific routes come before `/{id}` and wildcards.
5. [ ] `RequestPredicate`s clearly distinguish method/path/`Accept`/`Content-Type`.
6. [ ] Path/query/header parsing and input validation have explicit error contracts.
7. [ ] Body decoded once with `bodyToMono`/`bodyToFlux` as appropriate.
8. [ ] `bodyValue` chosen for single values, `body(publisher,type)` for reactive bodies.
9. [ ] Statuses 404/400/201+`Location`/204 are constructed **explicitly**.
10. [ ] DB/network errors are never swallowed into `Mono.empty()`.
11. [ ] End-to-end reactive services, or blocking bridges are offloaded and bounded.
12. [ ] Streaming media types, client cancellation, and backpressure are designed.
13. [ ] Functional filters/`WebFilter`/`SecurityWebFilterChain` are placed at the right layers.
14. [ ] CSRF/CORS/authentication/authorization respect trust boundaries.
15. [ ] Connections, buffers, concurrency, timeouts, retries, and event-loop latency have metrics.
16. [ ] Tests cover success, invalid, missing, empty, error, and stream cases.
17. [ ] POST retries and DELETE semantics/idempotency have clear policies.
18. [ ] Domain services are separated from `RouterFunction`s and DTOs from persistence entities.
19. [ ] Actual Spring Boot application type is reactive rather than accidentally MVC.
20. [ ] Performance is measured rather than assumed from methods returning `Mono`.

## 20. Review questions with answers

**1.** What return type does `HandlerFunction<ServerResponse>` have in WebFlux.fn?  
**Answer:** `Mono<ServerResponse>`.

**2.** What result type does `RouterFunction<ServerResponse>.route` produce on match?  
**Answer:** `Mono<HandlerFunction<ServerResponse>>` emitting one handler.

**3.** How is a non-matching route represented?  
**Answer:** The routing publisher completes empty so the framework can try other mappings.

**4.** What is the WebFlux.fn `ServerRequest` package?  
**Answer:** `org.springframework.web.reactive.function.server.ServerRequest`.

**5.** What is the WebMvc.fn `ServerRequest` package?  
**Answer:** `org.springframework.web.servlet.function.ServerRequest`.

**6.** What is used to read a JSON body into a DTO in WebFlux.fn?  
**Answer:** `request.bodyToMono(Dto.class)`.

**7.** When the body contains multiple records, what is used?  
**Answer:** `request.bodyToFlux(Record.class)` when the codec/media type supports it.

**8.** What builds a response with an existing DTO?  
**Answer:** `ServerResponse.ok().bodyValue(dto)`.

**9.** What builds a response with a `Flux` body?  
**Answer:** `ServerResponse.ok().body(flux, Item.class)`.

**10.** Does `Mono<ServerResponse>` mean the response has only one body record?  
**Answer:** No; the `ServerResponse` descriptor can wrap a 0..N `Flux`.

**11.** Does a service returning `Mono.empty()` after a route match automatically produce HTTP 404?  
**Answer:** No; the handler must choose the status using `switchIfEmpty`.

**12.** What status and header does a create response typically include?  
**Answer:** 201 Created and `Location`.

**13.** What should a successful `DELETE` without a body return?  
**Answer:** `ServerResponse.noContent().build()` for 204 per API policy.

**14.** Why must `/search` come before `/{id}`?  
**Answer:** WebFlux.fn routes are evaluated in order; first match wins.

**15.** Can a `HandlerFilterFunction` skip calling `next`?  
**Answer:** Yes, it can short-circuit a request.

**16.** Does `HandlerFilterFunction` replace Spring Security?  
**Answer:** No; authentication and authorization must rely on trusted context.

**17.** Is `Mono.just(legacyJDBC.query())` non-blocking?  
**Answer:** No; the JDBC query executes before the `Mono` is created.

**18.** Does `Mono.fromCallable` by itself make a blocking call non-blocking?  
**Answer:** No; it needs an appropriate scheduler or a reactive I/O driver.

**19.** What is wrong with calling `block()` on the Reactor Netty event loop?  
**Answer:** It can block the event loop or be rejected by Reactor with an exception.

**20.** Can a 200 SSE response that has already sent data always change its status to 500 on error?  
**Answer:** Not once headers have been committed.

**21.** Does CORS replace owner/tenant checks?  
**Answer:** No; CORS is a browser access policy.

**22.** What is `WebTestClient` used for?  
**Answer:** Testing routing, HTTP statuses, headers, bodies, and integration across the reactive stack.

**23.** What does `StepVerifier` verify differently from `WebTestClient`?  
**Answer:** `onNext`/`onComplete`/`onError`/empty signals on a `Publisher`.

**24.** If you need continuous events from a `Flux`, which media types should you use?  
**Answer:** Typically `text/event-stream` or NDJSON depending on client/protocol.

**25.** Does reactive routing change the nature of CPU-heavy tasks?  
**Answer:** No; CPU-bound tasks still require CPU capacity and planning.

## 21. Official documentation

- [Spring Framework 6.2 — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): asynchronous nature of `RouterFunction` and `HandlerFunction`, `ServerRequest`/`ServerResponse`, handlers, predicates, routing, filters, resources.
- [Spring Framework 6.2 — WebMvc Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): comparing Servlet `Optional`/`ServerResponse` signatures and reactive `Mono`.
- [Spring Framework 6.2 — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html): `RouterFunctionMapping`, `HandlerFunctionAdapter`, and `ServerResponseResultHandler`.
- [Spring Framework 6.2 — WebFlux WebHandler API](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/web-handler-api.html): HTTP server chain and `WebFilter`.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): HTTP testing API for WebFlux.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): WebFlux auto-configuration and runtime.
- [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Mono`/`Flux`, lazy subscription, schedulers, backpressure, error/cancel.
- [Reactive Streams specification](https://www.reactive-streams.org/): `Publisher`/`Subscriber`/`Subscription` and demand.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status codes, HTTP request/response, conditional and idempotency semantics.

**Summary:** Functional WebFlux is not merely lambda syntax replacing `@RestController`. Its core is a **two-layer asynchronous contract**: the router produces `Mono<HandlerFunction>`, the handler produces `Mono<ServerResponse>`, and the response body can be a separate `Publisher` emitting 0..N items. Choose status/headers at the right moment based on completion/empty/error; use genuine reactive I/O, never block the event loop, and place routes, filters, and security at their proper layers.
