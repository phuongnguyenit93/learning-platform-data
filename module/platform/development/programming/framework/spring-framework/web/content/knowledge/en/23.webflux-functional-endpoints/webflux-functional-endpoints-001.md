# WebFlux.fn, RouterFunction, and HandlerFunction in Spring WebFlux

> **Scope:** Functional WebFlux (WebFlux.fn), Spring Framework 6.2.x and Spring Boot 3.5.x, Java 17+. This guide explains `RouterFunction<ServerResponse>`, `HandlerFunction<ServerResponse>`, `ServerRequest`, `ServerResponse`, request predicates, route composition/nesting/filtering, reactive body reading and writing, validation and HTTP errors, `WebTestClient` testing, security, and performance. Includes a standalone runnable Spring Boot WebFlux application. **Do not confuse with WebMvc.fn:** this guide's package is `org.springframework.web.reactive.function.server`, and handlers return **`Mono<ServerResponse>`**, not synchronous `ServerResponse`.

## 1. What is WebFlux.fn?

Spring WebFlux provides two models for declaring HTTP endpoints:

1. **Annotated controllers:** using `@RestController`, `@GetMapping`, `@PostMapping`, `@RequestBody`.
2. **Functional endpoints (WebFlux.fn):** using functions that accept `ServerRequest` and return `Mono<ServerResponse>`, composed into a `RouterFunction<ServerResponse>` via a Java DSL.

Both share the same **reactive WebFlux foundation**. They are not two separate HTTP servers, and they can coexist within a single WebFlux application. The primary difference lies in how **mapping declaration and the handler contract** are expressed, not in whether one side can be non-blocking while the other cannot.

Side-by-side example:

```java
// Annotated WebFlux: the framework reads @GetMapping to register the route.
@RestController
class AnnotatedHello {
    @GetMapping("/hello")
    Mono<String> hello() {
        return Mono.just("Hello");
    }
}
```

```java
// Functional WebFlux: routes and functions are declared directly.
// Snippet inside a @Configuration class with @Bean and appropriate imports.
@Bean
RouterFunction<ServerResponse> helloRoutes() {
    return RouterFunctions.route()
            .GET("/hello", request ->
                    ServerResponse.ok().bodyValue("Hello"))
            .build();
}
```

If you put **both routes with the same `GET /hello`** into one application, handler selection can depend on mapping order/registration and cause contract conflicts. These are two **alternative approaches**; you should not copy both simultaneously for the same URL/method without a plan.

**Remember the two key function types:**

```java
// HandlerFunction<ServerResponse>:
ServerRequest -> Mono<ServerResponse>

// RouterFunction<ServerResponse>:
ServerRequest -> Mono<HandlerFunction<ServerResponse>>
```

The second signature shows that a router **does not process the body**; it selects a handler when the request matches, or returns an empty `Mono` if it does not match. In most applications, you do not implement these interfaces manually; instead, you use `RouterFunctions.route()`/builder and method references.

## 2. Diagram of a request flowing through WebFlux.fn

```text
Browser / mobile / service client
             |
      HTTP request bytes
             |
       Reactor Netty
             |
     HttpHandler + WebFilter chain
             |
      DispatcherHandler
             |
   RouterFunctionMapping
             |
  RouterFunction<ServerResponse>
    |       |       |
 predicate? |       +-> other route
    |       |
    | match v
    +--> HandlerFunctionAdapter
                  |
        HandlerFunction.handle(ServerRequest)
                  |
            Mono<ServerResponse>
                  |
        ServerResponseResultHandler
                  |
        HttpMessageWriter / codecs
                  |
         HTTP response bytes
```

In a Spring Boot application using the WebFlux starter, the WebFlux infrastructure registers:
- **`RouterFunctionMapping`:** discovers `RouterFunction<?>` beans and aggregates ordered routes.
- **`HandlerFunctionAdapter`:** invokes the selected `HandlerFunction`.
- **`ServerResponseResultHandler`:** writes the `ServerResponse` to the HTTP response.

Normally you do not need to call `RouterFunctions.toHttpHandler(...)` or initialize `DispatcherHandler` yourself; those exist for using WebFlux.fn with custom-configured adapters/servers or advanced scenarios.

### 2.1. Why is immutability useful?

`ServerRequest` and `ServerResponse` follow an immutable interface contract. A handler can return a response description without writing to the socket directly via imperative commands:

```java
HandlerFunction<ServerResponse> handler =
        request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello WebFlux.fn");
```

The framework coordinates body writers and subscriptions. **Building a pipeline** does not mean all business work has already executed; publishers are typically lazy and only run when subscribed to.

The immutability of the request/response abstraction **does not** mean code inside a handler has no side effects; database writes, emails, transactions, and shared state still need proper control.

## 3. Core API: four components

| Component | Role | Key type or API |
| --- | --- | --- |
| `RouterFunction<ServerResponse>` | Matches a request to a handler | `RouterFunctions.route()`, `andOther(...)` |
| `HandlerFunction<ServerResponse>` | Processes the request and creates an async response | `Mono<ServerResponse> handle(ServerRequest)` |
| `ServerRequest` | Reads method/URI/path variables/query/headers/cookies/body | `pathVariable`, `queryParam`, `bodyToMono`, `bodyToFlux` |
| `ServerResponse` | Builds status, headers, and reactive body | `ok`, `created`, `notFound`, `bodyValue`, `body`, `build` |
| `RequestPredicate` | Condition for whether a route is selected | `path`, `method`, `accept`, `contentType` |
| `HandlerFilterFunction` | Wraps a matched handler | `filter((request,next) -> ...)` |
| `WebFilter` | HTTP filter layer in WebFlux infrastructure | Suitable for authentication/tracing/CORS |

A route does not necessarily require a handler class. For very simple endpoints, a lambda may suffice:

```java
RouterFunction<ServerResponse> ping = RouterFunctions.route()
        .GET("/ping",
                request -> ServerResponse.ok().bodyValue("pong"))
        .build();
```

When functionality grows, extracting business logic into a `@Component` handler class makes testing and maintenance much easier.

## 4. RouterFunction: selecting path and method

### 4.1. Declaring multiple routes

```java
@Bean
RouterFunction<ServerResponse> itemRoutes(ItemHandler handler) {
    return RouterFunctions.route()
            .GET("/api/items", handler::list)
            .GET("/api/items/{id}", handler::get)
            .POST("/api/items", handler::create)
            .PUT("/api/items/{id}", handler::replace)
            .DELETE("/api/items/{id}", handler::delete)
            .build();
}
```

This is a **bean snippet** requiring `ItemHandler` and imports. Note that all handler methods follow the conceptual signature:

```java
public Mono<ServerResponse> get(ServerRequest request) {
    // non-blocking body/status handling
}
```

The builder's `GET`/`POST` shortcuts already include the HTTP method predicate and the corresponding path.

### 4.2. Routes are evaluated in order

A crucial difference: **WebFlux.fn evaluates routes in the order they are declared**. If an earlier route matches, it selects that handler before considering subsequent routes. Therefore, specific routes should come before general routes:

```java
return RouterFunctions.route()
        .GET("/api/items/popular", handler::popular)
        .GET("/api/items/{id}", handler::getById)
        .build();
```

If you reverse the order and `/{id}` comes first, the literal `popular` can be captured as an ID. With annotated controllers, the framework uses a mapping comparator to pick the most specific mapping by conditions; do not assume WebFlux.fn automatically reorders your routes like annotations do.

### 4.3. RequestPredicate

`RequestPredicates` provides builders for method, path, accept, content-type, and other conditions:

```java
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.http.MediaType.APPLICATION_JSON;

return RouterFunctions.route()
        .GET("/api/items", accept(APPLICATION_JSON), handler::list)
        .build();
```

Two predicates can be combined with `and`, `or`, or `negate` when complex logic is genuinely needed. For example:

```java
RequestPredicate jsonPost = RequestPredicates
        .method(HttpMethod.POST)
        .and(RequestPredicates.path("/api/items"))
        .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON));
```

This is a fragment requiring `HttpMethod`/`MediaType` imports. If the `contentType(APPLICATION_JSON)` predicate does not match, the route may simply be skipped and return 404 or be handled by another mapping; **do not assume** that a predicate mismatch always produces **415** as happens when a decoder does not support a content type. If your API requires exact 415/406 status codes, test and design your error handling accordingly.

### 4.4. Nested routes and prefixes

Instead of repeating `/api/items`:

```java
return RouterFunctions.route()
        .path("/api/items", b -> b
                .GET("", handler::list)
                .GET("/{id}", handler::get)
                .POST("", handler::create))
        .build();
```

Nested routes can share a path prefix or another predicate. In a nested `accept(JSON)` case, you can apply the condition only to the GET group without affecting POST:

```java
return RouterFunctions.route()
        .path("/api/items", b -> b
                .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON),
                        get -> get
                                .GET("", handler::list)
                                .GET("/{id}", handler::get))
                .POST("", handler::create))
        .build();
```

The example above is a snippet; the GET routes require a JSON-compatible `Accept` header, whereas POST does not receive the same predicate. A filter placed inside a nested builder is scoped only to routes within that nested group; a filter on the outer builder can wrap all routes built at the outer level.

### 4.5. Composing multiple RouterFunctions

Besides the `.add(otherRoute)` builder method, `RouterFunction` supports composition via `and(...)`/`andOther(...)` depending on the generic type. When multiple `RouterFunction` beans are declared, `RouterFunctionMapping` collects and orders them. In large applications, organize ordering intentionally (for example with `@Order`) so a fallback/catch-all route does not swallow routes from other modules. Do not treat bean scan order or class name order as a stable routing contract.

### 4.6. Static resources

`RouterFunctions.resources(...)` can mount a route to serve static resources. Do not place a very broad catch-all route before API routes; it can cause API errors to return a static resource response by mistake. For file upload/download, ensure path canonicalization, permissions, MIME types, and security headers; serving resources does not mean allowing clients to choose arbitrary filesystem paths.

## 5. HandlerFunction: responsibility for reading and returning responses

A handler function does not carry `@GetMapping` annotations directly on the method; `RouterFunction` already handles routing:

```java
@Component
class GreetingHandler {
    Mono<ServerResponse> hello(ServerRequest request) {
        String name = request.queryParam("name").orElse("guest");
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("Hello " + name);
    }
}
```

This is a snippet; imports are required. When a route invokes `handler::hello`, the argument received is `ServerRequest`, not a list of parameters automatically resolved via `@PathVariable` or `@RequestBody` as in an annotated controller method. **The handler must extract that data from `ServerRequest` explicitly**.

### 5.1. Do not return ServerResponse directly

One common mistake when migrating from WebMvc.fn:

```java
// Wrong for WebFlux.fn HandlerFunction:
ServerResponse get(ServerRequest request) { ... }

// Correct in WebFlux.fn:
Mono<ServerResponse> get(ServerRequest request) { ... }
```

Simply wrapping with `Mono.just(serverResponse)` may not be enough in handlers backed by reactive sources: choosing the status/body often depends on the result of a `Mono<T>`. Use proper composition:

```java
return service.find(id)
        .flatMap(found -> ServerResponse.ok().bodyValue(found))
        .switchIfEmpty(ServerResponse.notFound().build());
```

When `find(id)` is an empty `Mono`, the method returns 404; there is no need for `block()` and no manual subscription.

### 5.2. Inline lambda or separate handler class?

| Approach | Best suited for | Points to keep in mind |
| --- | --- | --- |
| Inline lambda in route | Ping, hello, very short endpoints | Do not turn a `RouterFunction` bean into a long, hard-to-test controller |
| Method reference in a component | REST domains, multiple endpoints | Allows service injection and isolated unit testing |
| Dedicated `HandlerFunction` implementation | Custom behavior or composition | Avoid unnecessary boilerplate if a method reference suffices |

Even when using a handler class, business logic belongs in services/repositories rather than embedding DB transactions into router declarations.

## 6. ServerRequest: URI, query, path, and headers

`ServerRequest` provides APIs close to HTTP semantics:

```java
String id = request.pathVariable("id");
String query = request.queryParam("q").orElse("");
String method = request.method().name();
URI uri = request.uri();
List<MediaType> accept = request.headers().accept();
Optional<MediaType> contentType = request.headers().contentType();
String trace = request.headers().firstHeader("X-Trace-Id");
```

This is a snippet requiring `java.net.URI`, `java.util.*`, and `MediaType` imports. Query/cookie/header APIs have typed variants; prefer them over hand-rolled parsers when they fit your requirements.

### 6.1. Parsing path variables and errors

```java
long id;
try {
    id = Long.parseLong(request.pathVariable("id"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue(new ApiError("invalid_id"));
}
```

This example sits inside a handler returning `Mono<ServerResponse>`; it requires an `ApiError` DTO. Avoid letting `NumberFormatException` turn into a 500, and do not expose raw exception messages to clients. In the runnable code below, route-level `onError(IllegalArgumentException.class,...)` returns 400 when an ID is invalid.

### 6.2. Multi-value query parameters

`request.queryParam("tag")` retrieves a single value depending on the API contract, whereas a request may contain `?tag=a&tag=b`. If the API allows multiple tags, inspect `request.queryParams()` (`MultiValueMap<String,String>`) and clearly define OR/AND, deduplication, and maximum count semantics. Never interpolate filter/search parameters directly into unparameterized SQL strings.

### 6.3. Headers are not security authorities

`request.headers().firstHeader("X-User-Role")` merely reads a header that any client can send. It **does not** prove the caller is an admin. Use reactive Spring Security `SecurityWebFilterChain` and resource/tenant-level authorization. If you need the principal:

```java
Mono<Principal> principal = request.principal();
```

`request.principal()` is an async `Mono`; if the API needs to distinguish anonymous users, handle emptiness according to your contract and the reactive `SecurityContext` properly. Do not trust raw `X-Forwarded-*` headers to determine identity or build redirects unless a trusted proxy has scrubbed/normalized them.

## 7. Reading request bodies reactively

### 7.1. A single JSON object: bodyToMono

For a JSON POST:

```http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"Spring WebFlux"}
```

A handler can use:

```java
Mono<CreateBook> input = request.bodyToMono(CreateBook.class);
```

The reader/codec (typically Jackson JSON) uses the media type and Java target type to decode bytes into the DTO. **The publisher is lazy**, so calling `bodyToMono(...)` does not immediately read the entire body at variable creation time; WebFlux manages subscription and backpressure.

Do not call:

```java
// ANTI-PATTERN: avoid blocking the event loop.
CreateBook input = request.bodyToMono(CreateBook.class).block();
```

Instead, compose:

```java
return request.bodyToMono(CreateBook.class)
        .flatMap(service::create)
        .flatMap(saved -> ServerResponse
                .created(URI.create("/api/books/" + saved.id()))
                .bodyValue(saved));
```

This is a snippet; `service.create` returns `Mono<Book>` and requires `URI`/imports. Apply validation before persisting.

### 7.2. Multiple values: bodyToFlux

```java
Flux<CreateBook> commands = request.bodyToFlux(CreateBook.class);
```

If the request uses NDJSON or a compatible streaming media type, the body can be decoded element by element. For a JSON array, the codec may decode multiple values according to media type/codec version rules. **Do not** assume every `Content-Type` supports per-record streaming with identical semantics.

An example processing each item:

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_NDJSON)
        .body(
                request.bodyToFlux(CreateBook.class)
                        .concatMap(service::create),
                Book.class);
```

This is a snippet: it requires a codec supporting `application/x-ndjson`, `service.create` returning `Mono<Book>`, and a contract allowing line-delimited record responses. `concatMap` preserves the order of inner writes; `flatMap` can increase concurrency but may change ordering. Enforce hard limits on element count and request size rather than allowing unbounded streams.

### 7.3. Generic types

When the body needs to be `List<CreateBook>` from a JSON array:

```java
Mono<List<CreateBook>> batch = request.bodyToMono(
        new ParameterizedTypeReference<List<CreateBook>>() {});
```

Java type erasure prevents `List.class` from carrying the generic element type; a typed reference tells Jackson that elements must be `CreateBook` rather than raw maps. Even with correct generic metadata, you must still bound element counts and payload sizes.

### 7.4. Do not read the same body twice

A reactive request body is typically a stream consumed as part of the HTTP lifecycle. Anti-pattern:

```java
request.bodyToMono(String.class).subscribe(System.out::println);
return request.bodyToMono(CreateBook.class)
        .flatMap(service::create)
        .flatMap(ServerResponse.ok()::bodyValue);
```

The manually created subscription is detached from the response lifecycle, and the second read is not guaranteed to receive the same data. For logging/auditing, use a properly designed bounded request-body decorator/observability hook; never dump raw JWTs, PII, or raw bodies into logs.

### 7.5. Validation is separate from deserialization

A JSON codec only turns bytes into a DTO; it does not mean `title` is valid or the caller is authorized to write. A manual rule:

```java
private static void validate(CreateBook input) {
    if (input == null || input.title() == null
            || input.title().isBlank()
            || input.title().length() > 120) {
        throw new IllegalArgumentException("Invalid title");
    }
}
```

If you use Jakarta Bean Validation/`@Validated`, in a functional handler you must invoke `Validator` explicitly; do not rely on the automatic `@Valid @RequestBody` behavior of annotated controller methods. The Spring reference demonstrates `Validator` + `BeanPropertyBindingResult` and `ServerWebInputException` for 400 responses. Use allowlisted DTOs and do not decode JSON directly into JPA entities containing fields such as `role`, `ownerId`, or `tenantId`.

## 8. ServerResponse: status, headers, body

### 8.1. 200 OK JSON body

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new Book(1L, "Spring"));
```

`bodyValue(Object)` is for an already-available value; it returns `Mono<ServerResponse>` and the framework encodes the body via `HttpMessageWriter`. With the demo `Book` DTO, the JSON is typically:

```json
{"id":1,"title":"Spring"}
```

### 8.2. 201 Created + Location

```java
return ServerResponse
        .created(URI.create("/api/books/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new Book(42L, "Spring"));
```

The `Location` URI may be relative; if absolute canonical links are needed, do not concatenate raw client `Host`/`X-Forwarded-Host` headers into untrusted external URLs.

### 8.3. 204 No Content

```java
return ServerResponse.noContent().build();
```

HTTP 204 has no response body. Use it for successful deletes/updates when returning the updated resource is unnecessary. If the body needs to show the new version, choose 200 with a JSON representation.

### 8.4. 400, 404, 409 with an error DTO

```java
return ServerResponse.badRequest()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new ApiError("invalid_input"));
```

```java
return ServerResponse.notFound().build();
```

```java
return ServerResponse.status(HttpStatus.CONFLICT)
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new ApiError("conflict"));
```

409 can represent a business conflict, whereas 412 fits failed HTTP conditional requests such as a stale `If-Match` version. Do not return HTTP 200 with `{"error":"not_found"}` if clients rely on HTTP status codes.

### 8.5. Headers and caching

```java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .header("Cache-Control", "no-store")
        .header("X-Example", "webflux")
        .bodyValue(book);
```

`Cache-Control` must match data sensitivity and authorization requirements. A custom header does not replace authentication. Avoid setting `Content-Length` manually using Java's `String.length()`, because Unicode character counts differ from encoded byte lengths.

### 8.6. Response body as a Publisher

```java
Flux<Book> records = service.findAll();

return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(records, Book.class);
```

Unlike `bodyValue(book)`, `body(records, Book.class)` takes a `Publisher` and an element type. **Do not confuse `bodyValue(flux)` with a Publisher body.** Use `body(Publisher, Class)` or an appropriate `BodyInserter` for reactive sources.

### 8.7. SSE and NDJSON

```java
Flux<ServerSentEvent<String>> events = Flux.interval(
                Duration.ofSeconds(1))
        .take(3)
        .map(i -> ServerSentEvent.<String>builder()
                .id(i.toString())
                .event("tick")
                .data("event-" + i)
                .build());

return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(events,
                new ParameterizedTypeReference<ServerSentEvent<String>>() {});
```

This snippet requires `Duration`, `ServerSentEvent`, and `ParameterizedTypeReference` imports. SSE events use `event:`/`id:`/`data:` framing terminated by a blank line. In production, handle heartbeats, retries/resume IDs, proxy buffering, auth/tenant scope, and client disconnects. With `application/x-ndjson`, each line is a separate JSON value; do not assume it is a standard JSON array.

## 9. Reactive lifecycle, backpressure, and non-blocking I/O

In WebFlux.fn, `ServerRequest.bodyToFlux(...)` and `ServerResponse.body(flux,...)` support **Reactive Streams backpressure**. The framework manages subscriptions when reading/writing HTTP bodies. However, reactive code can still stall when:
- calling blocking JDBC/JPA on the event loop;
- calling `Thread.sleep(...)` inside a mapper;
- calling `.block()` inside a handler;
- creating an infinite `Flux` and then calling `collectList()`;
- using an unbounded `onBackpressureBuffer()`;
- executing many downstream calls without concurrency or connection limits.

### 9.1. Mono/Flux does not automatically make code asynchronous

```java
// Anti-pattern: work runs immediately before creating the Publisher.
Mono<Book> bad = Mono.just(legacyJdbc.findById(id));
```

`Mono.just(...)` accepts an **already-computed value**. If the argument expression blocks, the current thread still blocks. When temporarily integrating a blocking API:

```java
Mono<Book> bridged = Mono.fromCallable(
                () -> legacyJdbc.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This snippet wraps a blocking call with bounded concurrency; it does not turn JDBC into a reactive driver. Consider WebFlux + R2DBC, async `WebClient`, or Spring MVC if the application relies mostly on blocking integrations.

### 9.2. Avoid subscribing manually in a handler

A handler should **return a publisher** so the framework manages cancellation and errors. If you call `subscribe()` manually and return early, downstream errors are detached from the HTTP request and work may continue after client disconnect. Do not treat a valueless `Mono<Void>` as a reason to call `subscribe()` manually; use `ServerResponse.ok().build(publisher)` to tie completion to the response when appropriate.

### 9.3. Committed streaming responses

Once an SSE/NDJSON stream has sent headers/body, a late error cannot reliably change status 200 to 500 or replace the response with a JSON error. Design protocol-level error events, close/cancel handling, reconnect/resume behavior, and dedicated stream logs/metrics. Verify with a real HTTP client because proxies/ingress controllers may buffer chunks.

## 10. Route filtering, before/after, and onError

The functional router DSL provides:
- `before(Function<ServerRequest,ServerRequest>)`: transforms the request abstraction before the handler, applied within the builder scope.
- `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`: post-processes the response within the scope.
- `filter(HandlerFilterFunction)`: wraps the handler, deciding whether to call `next.handle(request)` or return an early response.
- `onError(...)`: maps matching exceptions to a response.

### 10.1. Illustrative handler filter

```java
return RouterFunctions.route()
        .GET("/api/ping",
                request -> ServerResponse.ok().bodyValue("pong"))
        .filter((request, next) -> {
            long started = System.nanoTime();
            return next.handle(request)
                    .doOnSuccess(response -> {
                        long micros =
                                (System.nanoTime() - started) / 1000L;
                        System.out.println("responseBuiltMicros=" + micros);
                    });
        })
        .build();
```

This snippet illustrates how a filter can wrap a handler and measure the time until `ServerResponse` is built. **It does not measure full body writing or network I/O time**, because the response body may be streamed afterward. In production, use Micrometer/Observation instead of stdout printing, and do not log raw headers or secrets.

### 10.2. Filter rejecting requests

```java
.filter((request, next) -> {
    if (maintenanceModeEnabled()) {
        return ServerResponse.status(HttpStatus.SERVICE_UNAVAILABLE)
                .build();
    }
    return next.handle(request);
})
```

This is a fragment; `maintenanceModeEnabled()` must be defined. Do not rely on a client-supplied header to grant access. For real authentication/authorization, use `SecurityWebFilterChain` and policies at the resource/service layer.

### 10.3. Nested filter scope

If a filter is added inside a nested `path("/api/private", ...)`, its scope does not implicitly leak to routes outside it; an outer filter can wrap routes of the outer builder. Consequently, relying solely on a nested DSL filter for auth controls makes it easy to miss newly added routes. Security should rely on a global reactive filter chain and object-level authorization.

### 10.4. onError for IllegalArgumentException

```java
return RouterFunctions.route()
        .GET("/api/books/{id}", handler::get)
        .onError(IllegalArgumentException.class,
                (ex, request) -> ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new ApiError("invalid_input")))
        .build();
```

This is a route snippet; it does not automatically catch errors from a `WebFilter` or decoder prior to routing. Keep catch types narrow; do not turn database failures into 400s. If an error occurs after a streaming response has committed, `onError` likewise cannot reliably change already-sent status/headers.

### 10.5. before/after do not replace the security pipeline

DSL filters attach only to a matched `RouterFunction`; `WebFilter` and Spring Security reactive filters operate at a broader HTTP handling layer. If no router matches (or a request hits a static resource or annotated controller), a DSL filter attached to a specific router does not act as a global security boundary.

## 11. Configuring ServerRequest/ServerResponse codecs

WebFlux uses reactive `HttpMessageReader`/`HttpMessageWriter` codecs. The JSON features in the demo rely on the Jackson codec from the Boot WebFlux starter.

Comparison:

| Aspect | WebFlux.fn | WebMvc.fn |
| --- | --- | --- |
| Package | `web.reactive.function.server` | `web.servlet.function` |
| Handler return | `Mono<ServerResponse>` | `ServerResponse` |
| Read one JSON DTO | `request.bodyToMono(Dto.class)` | `request.body(Dto.class)` |
| Read stream | `request.bodyToFlux(Dto.class)` | No direct `bodyToFlux` |
| Write one value | `ServerResponse.ok().bodyValue(dto)` | `ServerResponse.ok().body(dto)` |
| Write Publisher | `body(publisher,Element.class)` | MVC has adapters, but writes rely on Servlet |
| Codec | Reactive `HttpMessageReader/Writer` | `HttpMessageConverter` |
| I/O | Non-blocking reactive stack | Servlet blocking response writes |
| Async handling | Native Mono/Flux | Servlet async support when using reactive returns |

**Do not** import `org.springframework.web.servlet.function.ServerResponse` into a WebFlux project and wonder why `bodyValue`/`Mono<ServerResponse>` fails to match. They are **two different types despite sharing the same name**.

### 11.1. Codec buffer and payload size

Spring Boot 3.5 can configure:

```properties
spring.codec.max-in-memory-size=256KB
```

This is the codec buffer limit for decode/aggregate operations, **not** a hard cap for all HTTP bytes, file uploads, or every streaming request. For deeply nested JSON, large multiparts, or clients sending unbounded batches, add gateway/server/parser/stream quotas. Never collect an unbounded `Flux` with `collectList()`.

### 11.2. Content-Type, Accept, and predicates

- Request `Content-Type` indicates whether the sent body bytes are JSON, text, or another format.
- Client `Accept` indicates which representation the client can accept.
- `RequestPredicates.contentType(JSON)` restricts a route by `Content-Type`.
- `RequestPredicates.accept(JSON)` restricts a route by `Accept`.
- `ServerResponse.contentType(JSON)` declares the response media type.

If a route predicate does not match, the HTTP status depends on the rest of routing (potentially 404); if the route matches but the decoder does not support the input media type, 415 is typical; if the writer cannot produce an acceptable output, 406/5xx occurs depending on the failure. Write integration tests for your 400/404/406/415 contracts rather than inferring behavior from annotations used in the other model.

## 12. Runnable demo: Spring Boot 3.5, Java 17, WebFlux.fn

The demo builds a book API with `RouterFunction` + `HandlerFunction` **without `@RestController`**:

- `GET /api/books` — `Flux` of books as a JSON array.
- `GET /api/books/{id}` — single book JSON or 404.
- `POST /api/books` — `bodyToMono(CreateBook.class)`, validate, return 201 + `Location` + JSON.
- `PUT /api/books/{id}` — update title or 404.
- `DELETE /api/books/{id}` — 204 or 404.
- `GET /api/books/ping` — static route that must be declared before `/{id}` to demonstrate ordering.

The store is an in-memory `ConcurrentHashMap` for demonstrating routing/responses; **it has no database/authentication, CSRF, CORS, persistence, auditing, or concurrency versioning**. Do not expose this code directly to the internet.

### 12.1. Initialize the Maven project

At [Spring Initializr](https://start.spring.io/), choose Spring Boot **3.5.x**, Java **17+**, Maven, and the **Spring Reactive Web** dependency.

`pom.xml` fragment prepared by Initializr:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

Use the Spring Boot parent/BOM from Initializr to manage Reactor, Jackson, WebFlux, and Netty versions. **Do not add `spring-boot-starter-web` to this demo**, because Boot 3.x with both MVC + WebFlux starters on the classpath typically auto-configures a Servlet MVC server. `WebClient` can be used in an MVC project, but here we specifically want a real WebFlux server.

Structure:

```text
src/main/
  java/com/example/demo/
    DemoApplication.java
src/test/
  java/com/example/demo/
    FunctionalBookTest.java
```

### 12.2. Complete standalone Java source

Place the **exact** content below into `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import java.net.URI;
import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
        return RouterFunctions.route()
                // Static route before dynamic route.
                .GET("/api/books/ping", handler::ping)
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::get)
                .POST("/api/books", handler::create)
                .PUT("/api/books/{id}", handler::replace)
                .DELETE("/api/books/{id}", handler::delete)
                .onError(IllegalArgumentException.class,
                        (ex, request) -> ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError("invalid_input")))
                .build();
    }
}

record Book(long id, String title) {}

record CreateBook(String title) {}

record ApiError(String error) {}

@Component
class BookHandler {

    private final AtomicLong nextId = new AtomicLong();
    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    Mono<ServerResponse> ping(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("pong");
    }

    Mono<ServerResponse> list(ServerRequest request) {
        int limit = Integer.parseInt(
                request.queryParam("limit").orElse("20"));

        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("invalid limit");
        }

        Flux<Book> result = Flux.defer(() ->
                Flux.fromIterable(
                        books.values().stream()
                                .sorted(Comparator.comparingLong(Book::id))
                                .limit(limit)
                                .toList()));

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(result, Book.class);
    }

    Mono<ServerResponse> get(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)))
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateBook.class)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("body required")))
                .flatMap(command -> {
                    validate(command);
                    return Mono.fromSupplier(() -> {
                        long id = nextId.incrementAndGet();
                        Book created = new Book(
                                id, command.title().trim());
                        books.put(id, created);
                        return created;
                    });
                })
                .flatMap(saved -> ServerResponse
                        .created(URI.create("/api/books/" + saved.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(saved));
    }

    Mono<ServerResponse> replace(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return request.bodyToMono(CreateBook.class)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("body required")))
                .flatMap(command -> {
                    validate(command);
                    return Mono.defer(() -> Mono.justOrEmpty(
                            books.computeIfPresent(
                                    id, (key, oldBook) ->
                                            new Book(
                                                    id,
                                                    command.title().trim()))));
                })
                .flatMap(updated -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(updated))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    Mono<ServerResponse> delete(ServerRequest request) {
        long id = Long.parseLong(request.pathVariable("id"));

        return Mono.fromSupplier(() -> books.remove(id) != null)
                .flatMap(deleted -> deleted
                        ? ServerResponse.noContent().build()
                        : ServerResponse.notFound().build());
    }

    private static void validate(CreateBook command) {
        if (command == null
                || command.title() == null
                || command.title().isBlank()
                || command.title().length() > 120) {
            throw new IllegalArgumentException("invalid title");
        }
    }
}
```

### 12.3. Explaining why it is runnable

- Java 17 supports `record`; a file has one public class `DemoApplication`, and the other top-level package-private records/classes are valid.
- `@SpringBootApplication` and `@Component` detect the handler; the `@Bean RouterFunction<ServerResponse>` method registers the functional routes.
- `RouterFunctions.route()` is WebFlux.fn, not WebMvc.fn, because the imports start with `org.springframework.web.reactive.function.server`.
- Methods `ping/list/get/create/replace/delete` all return `Mono<ServerResponse>`. Neither `.block()` nor detached `.subscribe()` is used.
- `request.bodyToMono(CreateBook.class)` decodes JSON using reactive HTTP codecs.
- `ServerResponse.ok().body(flux, Book.class)` supplies the `Publisher` along with its element type so the writer serializes the response.
- `Mono.defer` and `Mono.fromSupplier` defer in-memory reads/writes until subscription. **They do not make arbitrary imperative code non-blocking**; the demo only performs very fast map operations with no JDBC/disk/network blocking.
- `onError(IllegalArgumentException.class, ...)` returns 400 JSON for path/query parsing errors or manual title validation within this router's scope.
- Malformed JSON or converter errors throw different exception types; do not assume router `onError(IllegalArgumentException)` catches every JSON parse error.
- `ConcurrentHashMap` + `AtomicLong` guarantees distinct IDs within a single JVM, not data durability or multi-instance consistency.
- `PUT` has no `If-Match`/ETag; a stale client can still overwrite. Production should use optimistic locking.
- `GET /api/books/ping` precedes `GET /api/books/{id}` per **WebFlux.fn routing order**.

### 12.4. Running the application

The project root includes the Maven wrapper:

```bash
# Linux / macOS
./mvnw spring-boot:run

# Windows PowerShell/CMD
mvnw.cmd spring-boot:run
```

If no port is configured, the server normally listens on `http://localhost:8080`. This is a Spring Boot WebFlux reactive application; `@EnableWebFlux` is not needed to create default handler mappings, and enabling it unnecessarily can interfere with auto-configuration.

### 12.5. Testing routes with curl

**Static ping:**

```bash
curl -i 'http://localhost:8080/api/books/ping'
```

Expected status 200, `Content-Type` compatible with `text/plain`, body:

```text
pong
```

If `/{id}` were placed earlier in the router, `ping` would be parsed as an ID, causing 400. This clearly demonstrates why WebFlux.fn routing order matters.

**Initial list:**

```bash
curl -i 'http://localhost:8080/api/books?limit=10'
```

Status 200, empty JSON array:

```json
[]
```

**POST to create a book:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"WebFlux Functional"}'
```

If the app just started without creating other resources, status 201, `Location`, and corresponding JSON:

```http
HTTP/1.1 201 Created
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"WebFlux Functional"}
```

Status, `Location`, and JSON fields are what to assert; header order, `Date` header, charset, or JSON whitespace depend on the runtime/converter.

**GET by ID:**

```bash
curl -i 'http://localhost:8080/api/books/1'
curl -i 'http://localhost:8080/api/books/9999'
```

For existing ID 1: status 200 JSON. For non-existent ID: 404.

**PUT title:**

```bash
curl -i -X PUT 'http://localhost:8080/api/books/1' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"Updated title"}'
```

When ID exists: status 200 JSON with the new title. For non-existent ID: 404. For blank title: 400 from validation.

**DELETE:**

```bash
curl -i -X DELETE 'http://localhost:8080/api/books/1'
```

First call if ID exists: status 204 No Content. Subsequent call with same ID: 404 per the demo contract.

**Invalid query limit:**

```bash
curl -i 'http://localhost:8080/api/books?limit=0'
curl -i 'http://localhost:8080/api/books?limit=abc'
```

Expected 400 with JSON error DTO:

```json
{"error":"invalid_input"}
```

**Invalid title:**

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  --data-binary '{"title":"  "}'
```

Expected 400, `{"error":"invalid_input"}`. With malformed JSON (for example `{"title":`), decoding failure is handled by the error infrastructure; **do not assume the error body matches manual validation** without shared configuration.

### 12.6. Windows PowerShell

Use `curl.exe` instead of the `curl` alias to keep standard syntax:

```powershell
curl.exe -i "http://localhost:8080/api/books/ping"
curl.exe -i "http://localhost:8080/api/books?limit=10"
```

For POST/PUT JSON, create a UTF-8 `request.json` file:

```json
{"title":"WebFlux Functional"}
```

Send it:

```powershell
curl.exe -i -X POST "http://localhost:8080/api/books" -H "Content-Type: application/json" --data-binary "@request.json"
```

This avoids quote-escaping differences across Bash, PowerShell 5, and PowerShell 7.

## 13. Testing WebFlux.fn with WebTestClient

Spring WebFlux provides `WebTestClient`, supporting either binding directly to a router function or sending requests against a real embedded server. To test Spring Boot auto-configuration, codecs, and routes end-to-end, use an integration test with `RANDOM_PORT`.

### 13.1. Test dependency

With Spring Boot 3.5, add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

In Boot 4, starter/test auto-configuration packages have been modularized, so verify dependencies/imports if upgrading; the test snippet below targets Boot 3.5.

### 13.2. FunctionalBookTest.java file

Save `src/test/java/com/example/demo/FunctionalBookTest.java`:

```java
package com.example.demo;

import java.net.URI;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FunctionalBookTest {

    @Autowired
    WebTestClient client;

    @Test
    void staticRouteShouldNotBeCapturedAsNumericId() {
        client.get().uri("/api/books/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("pong");
    }

    @Test
    void createThenReadUsesRealLocation() {
        EntityExchangeResult<byte[]> created = client.post()
                .uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"Test Book\"}")
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Test Book")
                .returnResult();

        URI location = created.getResponseHeaders().getLocation();
        assertNotNull(location);

        client.get().uri(location.toString())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Test Book");
    }

    @Test
    void unknownResourceReturns404() {
        client.get().uri("/api/books/999999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void invalidTitleReturns400() {
        client.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":\"   \"}")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("invalid_input");
    }

    @Test
    void invalidLimitReturns400() {
        client.get().uri("/api/books?limit=0")
                .exchange()
                .expectStatus().isBadRequest();
    }
}
```

The test avoids hardcoding `ID=1` because the store may already hold data created by other tests sharing the Spring context. `returnResult().getResponseHeaders().getLocation()` reads the actual URI from the 201 response, then GETs that URI. The `/ping` test protects static/dynamic route ordering.

### 13.3. Unit testing a router without starting a server

You can use:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(routerFunction)
        .build();
```

This is a snippet; it requires a created or injected `RouterFunction<ServerResponse> routerFunction`. It tests routing and handlers without opening a real socket. However, it does not prove that proxies, Netty configuration, TLS, or the production `WebFilter`/security chain are applied properly; combine router-level tests with integration tests as needed.

### 13.4. Running tests

```bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
```

Add tests for PUT/DELETE, wrong content type, malformed JSON, oversized batches, CORS/security, client disconnects, and concurrency if moving the store to a database. With shared in-memory state, ensure fixture isolation if tests run in parallel.

## 14. Comparison with WebMvc.fn and annotated WebFlux

| Criterion | WebFlux.fn | WebMvc.fn | Annotated WebFlux |
| --- | --- | --- | --- |
| Router declaration | `RouterFunction` | `RouterFunction` | `@RequestMapping` |
| Handler | `Mono<ServerResponse> handle(ServerRequest)` | `ServerResponse handle(ServerRequest)` | Java method with annotated args/return |
| Request body | `bodyToMono/bodyToFlux` | `body(Class)/body(ParameterizedTypeReference)` | `@RequestBody Mono<Dto>` |
| Response body | `bodyValue/body(Publisher,Class)` | `body(Object)` | `Mono<Dto>`/`Flux<Dto>`/`ResponseEntity` |
| HTTP stack | Reactive WebFlux | Servlet MVC | Reactive WebFlux |
| Codec | `HttpMessageReader/Writer` | `HttpMessageConverter` | `HttpMessageReader/Writer` |
| Route ordering | **Declared earlier is checked first** | Functional routing by order | Mapping comparator |
| Filter DSL | `before/after/filter/onError` | Has functional filters | `@ControllerAdvice`, `WebFilter` |
| HTTP I/O | Non-blocking when runtime supports it | Servlet blocking writes | Non-blocking when runtime supports it |
| Route contract clarity | Centralized DSL | Centralized DSL | Annotations adjacent to methods |
| Controller argument binding | Explicit via `ServerRequest` | Explicit via `ServerRequest` | Framework resolves annotated params |

WebFlux.fn and annotated WebFlux can **coexist** within `DispatcherHandler`; avoid overlapping paths/methods without clear routing ownership. Many teams prefer the annotated model for straightforward CRUD/heavy Bean Validation, and WebFlux.fn for gateways, route composition, filters, or dynamically constructed handlers. Neither model is "always faster" merely due to declaration style; benchmark I/O, codecs, data access, thread/connection pools, and backpressure.

### 14.1. Kotlin router DSL

In addition to the Java DSL, Spring supports the Kotlin `router { }` / `coRouter { }` (coroutines) DSLs. Coroutine handlers can be `suspend fun` returning responses with a dedicated DSL. **Do not** copy calls like `bodyValueAndAwait` directly from Kotlin coroutine examples into Java WebFlux.fn expecting them to compile; Java uses `Mono<ServerResponse>`.

### 14.2. Spring Framework 7 API versioning

Spring Framework 7 adds version predicates/mappings with configurable API version strategies. **Do not** use `RequestPredicates.version("1.0")` if your Spring Framework 6.2/Boot 3.5 codebase does not yet have that API. On Spring 6.x, implement versioning via path/query/header/media type or a well-tested custom route policy; when upgrading to Spring 7, consult the new documentation for supported versions, baselines, and deprecation semantics.

## 15. CORS, Security, and transactions

Functional routing is **a way to select handlers**, not a security boundary.

### 15.1. Reactive Spring Security

With a WebFlux server, Spring Security uses `SecurityWebFilterChain` and reactive security context APIs. When writing business handlers:
- authenticate users according to your token/cookie policy;
- authorize by method/path and object ID/tenant;
- fail closed when the permission service is unavailable;
- avoid logging `Authorization` tokens;
- do not treat `X-User-Role` or `API-Version` as proof of authority.

If the app accepts cookies/sessions and performs state-changing operations, configure an appropriate CSRF policy. The CORS origin allowlist must be separate from authentication and must not arbitrarily reflect every `Origin` with credentials.

### 15.2. CORS with WebFlux.fn

The Spring reference describes CORS for functional endpoints via `CorsWebFilter`. Some MVC annotation mechanisms such as `@CrossOrigin` on a controller method **do not** configure CORS for a `RouterFunction` declared via the DSL. When using Spring Security, CORS configuration must integrate with the reactive security filter chain and `OPTIONS` preflight requests; test cross-origin behavior from a real client.

### 15.3. Transactions and consistency

WebFlux.fn does not automatically provide database transactions. Use reactive transactional services/`TransactionalOperator` compatible with R2DBC when atomic changes are required; for external side effects, use outbox/saga/idempotency patterns when required by business logic. The demo uses an in-memory map and provides no transaction isolation across multiple pods, nor ETag/`If-Match` to prevent lost updates.

### 15.4. Uploads/multipart

For multipart requests, `ServerRequest` can access parts via reactive APIs; use `Part`/`FilePart` or `PartEvent` streaming as needed. With `PartEvent`, consume, relay, and release contents completely to prevent memory leaks. Never load large file uploads into an unbounded `byte[]`; enforce file size quotas, file type validation, safe server-generated filenames, scanning if policy requires it, and private storage.

## 16. Common mistakes and fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| IDE cannot find `bodyToMono` | Imported WebMvc.fn `ServerRequest` | Use `web.reactive.function.server.ServerRequest` |
| Handler method reports wrong return type | Used `ServerResponse` instead of `Mono<ServerResponse>` | Compose and return `Mono` |
| `bodyValue(flux)` is inappropriate | Passed a `Publisher` as a plain value | Use `body(flux, Element.class)` |
| Static route `/ping` gets parsed as an ID | Dynamic route `/{id}` comes first | Place static routes first |
| Two overlapping routes conflict | Uncontrolled DSL order/registration | Define clear paths/predicates and write tests |
| POST route does not match | Wrong `contentType` predicate, HTTP method, or path | Test the route with `Content-Type` |
| GET with XML-only `Accept` misses JSON route | `accept(JSON)` evaluates false | Align media types and test status codes |
| Bad POST JSON produces 5xx | Decoder/validation errors not handled properly | Define dedicated error policy for parse/body errors |
| `Mono.empty()` returns wrong response | Absence not mapped to 404 | `switchIfEmpty(notFound().build())` |
| Handler calls `subscribe()` and returns empty response | Subscription detached from HTTP lifecycle | Return the `Publisher` |
| Handler uses `block()` and stalls | Blocking the event loop | Compose `Mono`/`Flux` |
| Infinite `Flux` never completes | Collecting/buffering JSON response without termination | Streaming media, timeouts/quotas |
| Slow client causes memory pressure | Unbounded queues/buffers | Backpressure, bounded buffers/concurrency |
| Generic JSON deserializes as `List<Map>` | Lost element type | `ParameterizedTypeReference` |
| Router filter does not apply to other endpoints | Nested/router-local filter scope | Global `WebFilter`/security |
| CORS preflight rejected | Missing `CorsWebFilter`/security configuration | Proper CORS chain for functional routes |
| Null result from `Mono` mapper | Reactor forbids null `onNext` | Use `Mono.empty`/`justOrEmpty` |
| JSON decodes fine but bypasses permissions | Missing DTO/ACL checks | Validate and authorize |
| Header role spoofing | Trusting `X-User-Role` from client | Spring Security and tenant scope |
| 201 missing `Location` | Returning only status 201 | `ServerResponse.created(uri)` |
| 204 has a body | Using `body` on `noContent` | `ServerResponse.noContent().build()` |
| Trying to change status after streaming started | Response already committed | Stream error protocol/close |
| Both MVC and WebFlux starters present, running MVC | Boot picks Servlet MVC | Choose web application stack explicitly |
| `@EnableWebFlux` breaks Boot conventions | Unnecessary config override | Keep WebFlux Boot auto-config when sufficient |
| Tests depend on `ID=1` | Shared in-memory store | Use `Location` header and fixture isolation |
| Malformed path id returns 500 | Parse failure not mapped to 400 | Narrow `onError`/manual parse |
| Data race with concurrent writers | Unversioned map/DB updates | Optimistic locking/CAS |
| Proxy buffers SSE | Reverse proxy/HTTP client buffering | Test streaming end-to-end |

## 17. Code review and operations checklist

- [ ] Imports belong to `org.springframework.web.reactive.function.server`, not mixed with WebMvc.fn.
- [ ] A `RouterFunction<ServerResponse>` bean is registered and discovered by Spring Boot.
- [ ] Every route has explicit method/path/predicates and follows **static-before-dynamic ordering**.
- [ ] No catch-all/fallback route accidentally shadows other APIs.
- [ ] Handlers return `Mono<ServerResponse>` and never call `block()` or detached `subscribe()`.
- [ ] Request metadata is read from `ServerRequest`, and bodies via `bodyToMono`/`bodyToFlux` with proper codecs.
- [ ] DTOs and generic types are accurate, never binding entities with server-managed fields.
- [ ] Validation/ACLs and request body size/quotas are enforced before side effects.
- [ ] Response status, `Content-Type`, `Location`, `Cache-Control`, and empty-body semantics are valid.
- [ ] SSE/NDJSON streaming handles timeouts, heartbeats, cancellation, reconnects, and backpressure.
- [ ] `onError`/filters have clear scopes and do not replace `SecurityWebFilterChain`.
- [ ] Global CORS `OPTIONS` preflight integrates with security and never reflects arbitrary `Origin`s.
- [ ] No blocking JDBC/JPA runs directly on the Netty event loop.
- [ ] Concurrency for fan-out/gateway traffic is bounded; backpressure queues are not unbounded.
- [ ] `WebTestClient` tests cover 200/201/204/400/404, invalid payloads, and router ordering.
- [ ] Production writes use DB transactions, optimistic locking, and idempotency.
- [ ] Monitoring tracks latency, 4xx/5xx, active requests, upstream errors, and client disconnects without logging secrets.
- [ ] When upgrading to Spring Framework 7, review request versioning and starter/test packages.

## 18. Review questions

**Question 1.** How does WebFlux.fn differ from WebMvc.fn in imports and handler signatures?

**Answer:** WebFlux.fn uses `org.springframework.web.reactive.function.server`, and handlers take `ServerRequest` and return `Mono<ServerResponse>`; WebMvc.fn uses `org.springframework.web.servlet.function` and handlers return `ServerResponse`.

**Question 2.** Why place `GET /api/books/ping` before `GET /api/books/{id}`?

**Answer:** WebFlux.fn checks routes **in order**; the dynamic route would match the literal `ping` if placed first.

**Question 3.** How do you read a single JSON object into `CreateBook` in WebFlux.fn?

**Answer:** `request.bodyToMono(CreateBook.class)`, then validate and compose the result with `flatMap`.

**Question 4.** How do you return a `Flux<Book>` via `ServerResponse`?

**Answer:** `ServerResponse.ok().contentType(APPLICATION_JSON).body(books,Book.class)`; do not treat `Flux` as a plain DTO for `bodyValue`.

**Question 5.** Does `Mono.empty()` automatically mean HTTP 404?

**Answer:** No. The handler must return `ServerResponse.notFound().build()` or handle absence explicitly.

**Question 6.** What happens when a route filter calls `next.handle(request)`?

**Answer:** The next handler/filter in the chain executes; if omitted, the filter can return an early response to short-circuit the request.

**Question 7.** Does `RequestPredicates.contentType(JSON)` evaluating to false guarantee a 415?

**Answer:** No. The router may simply not match, and error handling depends on other routes; write tests if the API requires 415.

**Question 8.** Does a functional handler automatically run `@Valid` on DTOs decoded by `bodyToMono`?

**Answer:** Not in the same way as annotated argument validation. You must apply `Validator` or manual validation explicitly.

**Question 9.** Can you use an annotated controller's `@CrossOrigin` instead of `CorsWebFilter` for WebFlux.fn?

**Answer:** Not by default; functional endpoints require corresponding reactive CORS configuration, typically via `CorsWebFilter`.

**Question 10.** Since WebFlux.fn is non-blocking, is calling JDBC inside `Mono.just(...)` safe?

**Answer:** No. The JDBC call executes before `Mono.just` is constructed and can block the event loop; use reactive I/O, a controlled `boundedElastic` bridge, or an MVC architecture as appropriate.

## 19. Official documentation

- [Spring Framework 6.2 — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `RouterFunction`/`HandlerFunction`/`ServerRequest`/`ServerResponse`, predicates, nested routes, filters, validation.
- [Spring Framework — WebFlux Overview](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive HTTP foundation, non-blocking I/O, backpressure.
- [Spring Framework 6.2 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): `bodyToMono`/`bodyToFlux`, query/path/header, multipart.
- [Spring Framework 6.2 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): response builder/status/body/headers.
- [Spring Framework 6.2 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): `GET`/`POST`/`nest`/`filter`/`onError` methods.
- [Spring Framework 6.2 — RequestPredicates Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html): method/path/accept/contentType composition.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): Reactive `HttpMessageReader`/`Writer` foundation.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): `CorsWebFilter` and cross-origin security.
- [Spring Boot 3.5 — Reactive Web](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): starter, `RouterFunction` beans, and WebFlux server.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `WebTestClient` integration testing.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): reactive `SecurityWebFilterChain` and access controls.
- [Project Reactor — Core Reference](https://projectreactor.io/docs/core/release/reference/): `Mono`/`Flux`, cancellation, scheduling, backpressure, and tests.

**Conclusion:** WebFlux.fn expresses routing with `RouterFunction<ServerResponse>` and behavior with `HandlerFunction<ServerResponse>`; each handler takes a `ServerRequest` and returns **`Mono<ServerResponse>`**. Route matching is evaluated in DSL order; request bodies are read via `bodyToMono`/`bodyToFlux`, and responses use `bodyValue` or `body(Publisher,Class)`. To operate safely in production, you need DTOs/validation/auth, resource/concurrency limits, proper error handling, and tests — not just lambdas wired together assuming you have a production-ready REST API.
