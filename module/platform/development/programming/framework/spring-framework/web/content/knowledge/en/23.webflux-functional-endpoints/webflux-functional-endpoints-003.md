# Routing by Path, Method, Header, and Content Type in Functional WebFlux

## 1. Lesson objectives

**Spring WebFlux.fn** (functional endpoints) is a model for declaring HTTP routing and request handling using Java functions, alongside `@RestController`/`@RequestMapping`. In WebFlux.fn, a `RouterFunction<ServerResponse>` finds the appropriate `HandlerFunction<ServerResponse>` based on **RequestPredicate**s: path, HTTP method, headers, `Content-Type`, `Accept`, query parameters, and custom conditions. The first matching route typically determines which handler is selected.

This lesson belongs to Spring Framework **Functional WebFlux**, using **Java 17+, Spring Boot 3.x, and Spring Framework 6.x**, focusing on four routing axes: **path, method, header, and media type**. It includes a runnable WebFlux application, `curl` commands, `WebTestClient` tests, and common pitfalls when clients send invalid requests.

After this lesson, you should be able to:

- Understand `RouterFunction`, `HandlerFunction`, `ServerRequest`, `ServerResponse`, and `RequestPredicate`.
- Write routes for `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`, or `method(HttpMethod)` when needed.
- Match static paths, path variables, patterns, nested paths with `.path(...)`, and read `request.pathVariable(...)`.
- Use `RequestPredicates.headers(...)` to inspect one or more HTTP headers, and distinguish header data from authentication.
- Distinguish `contentType(MediaType.APPLICATION_JSON)` (**request body** media type) from `accept(MediaType.APPLICATION_JSON)` (**response representation the client wants**).
- Combine predicates with `and`, `or`, `negate`, and organize route ordering to prevent shadowing.
- Know when a mismatch becomes 404, 405, 406, or 415, and why HTTP integration tests are required instead of assuming a fixed status.
- Use nested builders, grouping, predicate tests, and verify routes after adding or removing an endpoint.
- Avoid blocking I/O, double subscriptions, wrong content negotiation, header spoofing, and reading the body before deciding the route.

**Scope note:** imports must come from the `org.springframework.web.reactive.function.server` package, **not** `org.springframework.web.servlet.function.server` from MVC.fn. The two API sets share similar names but belong to different stacks. Do not add `spring-boot-starter-web` if you want the demo project to use the default WebFlux reactive application type.

## 2. WebFlux.fn diagram from HTTP to handler function

```text
HTTP client
   |
   | GET /api/books/special
   | Accept: application/json
   v
Reactor Netty / reactive server adapter
   |
   v
WebFilter chain -> DispatcherHandler
   |
   v
RouterFunctionMapping
   |
   v
RouterFunction.route(ServerRequest)
   |
   +-- Route 1: method/path/headers/media predicates? ── no
   +-- Route 2: method/path/headers/media predicates? ── yes
   |                                                   |
   |                                                   v
   |                                           HandlerFunction
   |                                           handle(ServerRequest)
   |                                                   |
   |                                                   v
   |                                           Mono<ServerResponse>
   |                                                   |
   v                                                   v
HandlerFunctionAdapter                        ServerResponseResultHandler
                                                       |
                                                       v
                                              HTTP status, headers, body
                                                       |
                                                       v
                                                     Client
```

The diagram illustrates logical coordination: `RouterFunctionMapping` selects a handler; `HandlerFunctionAdapter` invokes the handler; `ServerResponseResultHandler` writes the result. This is **one reactive pipeline**, not a separate thread or transaction per box.

Simplified specification:

```java
// Conceptual signatures of existing Spring contracts:
interface RouterFunction<T extends ServerResponse> {
    Mono<HandlerFunction<T>> route(ServerRequest request);
}

interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
```

This is an **abbreviated API description**, not two interfaces to create new files for. Spring already defines them along with helper methods such as visitor/nesting/filter support.

Important: `RouterFunction` is the **router**, not the request handler. `HandlerFunction` performs business processing and returns `Mono<ServerResponse>`. A request that fails a predicate is not automatically retried after a handler has started and thrown an error; routing selects the handler before the handler reads or consumes the body.

## 3. Foundational concepts

| API | Role | Example |
| --- | --- | --- |
| `RouterFunctions.route()` | Creates a fluent multi-route builder | `.GET(...).POST(...).build()` |
| `RouterFunction<ServerResponse>` | Evaluates predicates and returns matching handler | Bean discovered by Spring Boot |
| `RequestPredicate` | Checks a condition on `ServerRequest` | `accept(JSON)`, `contentType(JSON)` |
| `RequestPredicates` | Standard predicate factories | `GET("/x")`, `headers(...)` |
| `HandlerFunction<ServerResponse>` | Executes endpoint logic | `handler::getBook` |
| `ServerRequest` | Immutable request API | `pathVariable`, `headers`, `bodyToMono` |
| `ServerResponse` | HTTP response builder | `ok()`, `status(201)`, `contentType` |
| `RouterFunctionMapping` | WebFlux handler mapping for routers | Discovers `RouterFunction` beans |
| `HandlerFunctionAdapter` | Invokes the selected functional handler | Feeds result into pipeline |
| `ServerResponseResultHandler` | Writes `ServerResponse` to HTTP | Selects message writers/codecs |

Unlike annotated routes: `@GetMapping("/books/{id}")` is analyzed via metadata in `RequestMappingHandlerMapping`. Functional routes are **checked in the order they are composed**; the first route that matches wins, even if you place a general route before a more specific one.

### When to use WebFlux.fn?

Functional routing fits teams that want to separate the **routing table** from **request handlers**, leverage Java lambda composition, and group shared predicates. Annotated controllers still make sense when a project relies heavily on method argument resolvers, Bean Validation annotations, and `@ControllerAdvice` conventions. Both run on the Spring WebFlux reactive core; functional style is not "more non-blocking" simply because it avoids annotations.

## 4. Routing by HTTP method

Concise builder form:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/api/books", handler::list)
    .POST("/api/books", handler::create)
    .PUT("/api/books/{id}", handler::replace)
    .PATCH("/api/books/{id}", handler::patch)
    .DELETE("/api/books/{id}", handler::delete)
    .build();
```

This is a **snippet** inside a configuration method with `handler` and matching methods; it is not standalone runnable source. Calling `.GET(pattern, handler)` combines the **HTTP method GET** predicate with the **path pattern**. The same applies to `POST`, `PUT`, `PATCH`, and `DELETE`.

With manual predicate composition:

```java
RouterFunction<ServerResponse> getRoute =
    RouterFunctions.route(
        RequestPredicates.method(HttpMethod.GET)
            .and(RequestPredicates.path("/api/books")),
        handler::list);
```

This snippet requires `RouterFunctions`, `RequestPredicates`, and `HttpMethod` imports. Similarly, there are `RequestPredicates.GET(String)`, `POST(String)`, `PUT(String)`, `DELETE(String)`, `HEAD(String)`, and `OPTIONS(String)`.

### HTTP methods are not "minor details"

- GET: reads a resource; should not cause significant side effects.
- POST: creates a resource or performs a contract-defined operation; validate the body.
- PUT: replaces/creates a representation per semantics and idempotency.
- PATCH: partially updates a resource; define the patch document media type.
- DELETE: deletes or marks a resource deleted; still requires authorization.
- HEAD: same metadata as GET without returning a representation body; routes/tooling have dedicated handling.
- OPTIONS: method/options discovery and CORS preflight; do not confuse with business endpoints.
- A different HTTP method prevents a route from matching even when the path is identical.

**Do not assume an HTTP method mismatch in WebFlux.fn always returns an exact 405.** When no handler is selected, depending on `RouterFunctionMapping`, error handlers, and configuration, the response may behave like a no-match 404. Some Spring/HTTP server infrastructure includes additional handling for `OPTIONS`/`HEAD` and CORS. If your contract requires 405 + `Allow`, design an intentional fallback/method policy and integration-test it on your exact framework version.

## 5. Routing by static path

Example:

```java
return RouterFunctions.route()
    .GET("/api/health", req ->
        ServerResponse.ok().bodyValue("ok"))
    .GET("/api/version", req ->
        ServerResponse.ok().bodyValue("v1"))
    .build();
```

This snippet can sit inside `@Bean RouterFunction<ServerResponse> routes()`. Each URL is matched against its declared pattern. `/api/health` and `/api/health/` are **not necessarily** the same path; Spring Framework 6.x changed defaults around optional trailing separators, so test explicitly if your app needs redirects or canonical URLs.

Path matching uses `PathPattern` (not just `String.equals`) and handles URI paths in context. Percent-encoded slashes, semicolons, dot segments, and Unicode may be governed by server/gateway/firewall policies. Never use a raw path as a filesystem path or authorization key without a canonicalization policy.

## 6. Path variables and specific routes before general routes

```java
return RouterFunctions.route()
    .GET("/api/books/special", handler::special)
    .GET("/api/books/{id}", handler::getById)
    .build();
```

Place `special` **before** `/{id}`. If reversed and both predicates match `/api/books/special`, the general route consumes the request and treats `id="special"`; functional routing does not automatically choose the "most specific method" as annotated mappings typically do.

Inside the handler:

```java
public Mono<ServerResponse> getById(ServerRequest req) {
    String id = req.pathVariable("id");
    return ServerResponse.ok().bodyValue(
        new BookView(id, "Book " + id));
}
```

This is a snippet; `BookView` must be defined. `pathVariable("id")` reads the bound value; do not re-decode percent escapes or use it as a file path. If `id` must be a UUID, validate it with a converter and return 400 per contract; if the user lacks permission to view that ID, a route match does not imply authorization succeeded.

### Common path patterns

```text
/api/books              exact path
/api/books/{id}         single variable segment id
/api/books/*            wildcard single path segment per PathPattern rules
/api/files/**           multiple path segments at end of pattern
/api/{category}/{id}    multiple variables
```

When capturing multiple trailing path segments, Spring `PathPattern` also supports syntax like `{*path}`. Never use it carelessly as a "file path from URL": validate, canonicalize, and map to server-owned resources while checking security and permissions.

**Do not assume** `/api/files/a%2Fb` will always pass through encoded slashes; reverse proxies, Netty/Servlet adapters, and firewall/decoder policies may block or alter them. Prefer path-safe IDs or query/JSON bodies for free-form data containing slashes.

## 7. Nested paths: grouping instead of repeating prefixes

The functional builder provides `.path(prefix, builderConsumer)`:

```java
@Bean
RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
    return RouterFunctions.route()
        .path("/api/books", b -> b
            .GET("/special", handler::special)
            .GET("/{id}", handler::getById)
            .POST(handler::create))
        .build();
}
```

This snippet requires `@Configuration`, imports, and matching handler methods. Inner patterns are matched relative to the `/api/books` prefix.

Comparison:

```text
path("/api/books", b -> b.GET("/special", ...))
           equivalent to route GET /api/books/special

path("/api/books", b -> b.GET("/{id}", ...))
           equivalent to route GET /api/books/{id}

path("/api/books", b -> b.POST(...))
           equivalent to route POST /api/books
```

`path(...)` is useful for API versioning such as `/api/v1`, but the version segment is part of route structure, **not an arbitrary ID value** for injecting slashes.

### Nesting by non-path predicates

Besides `path`, the builder has `nest(RequestPredicate, Consumer<Builder>)`, for example:

```java
RouterFunctions.route()
    .path("/api/books", b -> b
        .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON),
              json -> json
                  .GET("/{id}", handler::getById)
                  .GET("/special", handler::special)))
    .build();
```

This is a snippet. **Ordering still matters inside nested branches!** Here `/{id}` comes before `/special` and can shadow the specific route; swap their order before using in real code.

Instead of repeating `accept(JSON)`, nesting expresses a shared condition. However, if POST routes use different content types, do not nest `contentType(JSON)` around the entire group or the form/text branch will never match.

## 8. Header predicates: filtering by request metadata

Spring WebFlux.fn provides `RequestPredicates.headers(Predicate<ServerRequest.Headers>)`. For example, checking that header `X-View` equals `trace`:

```java
RequestPredicate debugOnly =
    RequestPredicates.headers(headers ->
        "trace".equals(headers.firstHeader("X-View")));
```

If the request sends:

```http
GET /api/status HTTP/1.1
X-View: trace
```

the predicate matches. If the header is absent, `firstHeader(...)` returns `null`, and `"trace".equals(null)` evaluates to `false`.

**Header names are case-insensitive per the HTTP specification**; values must be compared according to each header's semantics. For an application-defined `X-View`, exact comparison may fit; do not arbitrarily normalize `Authorization` or signature values.

You can combine them:

```java
RequestPredicate jsonAndTrace =
    RequestPredicates.headers(h ->
        "trace".equals(h.firstHeader("X-View")))
    .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));
```

In the builder:

```java
.GET("/api/status", jsonAndTrace, handler::status)
```

This snippet requires a `handler` variable. `RequestPredicates.headers(...)` inspects **metadata**; it does not read the JSON body and does not authenticate who sent the header.

### Headers are input, not authentication

Client-supplied `X-User: admin` or `X-Role: ADMIN` headers are not proof of identity. If a trusted gateway injects identity headers, configure the trust boundary, strip client-supplied headers, secure internal links, and enforce authorization in the backend. Use Spring Security reactive `SecurityWebFilterChain` for authentication/authorization instead of writing a `headers(...)` predicate disguised as access control.

### Multi-valued headers

`ServerRequest.Headers` offers APIs for the first value or list of values per header. If a client sends two headers with the same name, proxies may fold or preserve multiple values; for security-sensitive matching, define policies to prevent request smuggling/header ambiguity. `firstHeader` suits simple metadata demos, not general canonicalization.

## 9. Content-Type: describing the request body

Request `Content-Type` describes **the representation type the client is sending**. For a POST:

```http
POST /api/books HTTP/1.1
Content-Type: application/json

{"title":"WebFlux"}
```

To make a route accept only JSON:

```java
.POST("/api/books",
      RequestPredicates.contentType(MediaType.APPLICATION_JSON),
      handler::createJson)
```

If the client sends `Content-Type: text/plain`, this predicate does not match. Do not try to run `bodyToMono(BookInput.class)` on plain text by "rerouting" when the codec does not support it.

### Charset and content-type compatibility

Media types consist of type/subtype and optional parameters such as `charset` or `boundary`. `contentType(APPLICATION_JSON)` checks compatibility semantics rather than a naive `headerString.equals("application/json")`. For JSON with a charset parameter like `application/json;charset=UTF-8`, the predicate still matches.

**Media type matching does not guarantee a valid body**: broken JSON syntax with `Content-Type: application/json` still matches the route; afterward the Jackson decoder emits an error, typically HTTP 400. Conversely, valid JSON bytes sent under `text/plain` should not be treated as JSON just because the bytes look like JSON.

### Forms and multipart

`application/x-www-form-urlencoded` and `multipart/form-data` are distinct media types. WebFlux.fn `ServerRequest.bodyToMono(...)`/`formData()`/`multipartData()` expose APIs per content type; never read multipart file contents as an unbounded `String` on the event loop. Multipart requires size/count limits and proper `DataBuffer`/`Part` cleanup.

## 10. Accept: what does the client want to receive?

`Accept` specifies **acceptable response representations**, not the request body type.

```http
GET /api/books/42 HTTP/1.1
Accept: application/json
```

Predicate:

```java
.GET("/api/books/{id}",
     RequestPredicates.accept(MediaType.APPLICATION_JSON),
     handler::getById)
```

Once matched, the handler can return JSON via:

```java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(new BookView("42", "WebFlux"));
```

**Distinguish the two phases:** `accept(JSON)` decides **whether the route matches** based on request headers; `ServerResponse.contentType(JSON)` sets the **response `Content-Type`** and selects the codecs that write the body. Writing `accept(JSON)` alone does not force the handler to emit JSON if the handler writes text instead; conversely, setting the response `Content-Type` does not guarantee the route matched on `Accept`.

### Accept wildcards, specificity, and q-values

Examples:

```http
Accept: */*
Accept: application/json
Accept: application/json, text/plain;q=0.5
Accept: text/*;q=0.8, application/json;q=0.4
```

Media type matching follows compatibility rules; wildcards can match multiple representations. Do not implement content negotiation via `request.headers().firstHeader("Accept").equals("application/json")`. Spring's `RequestPredicates.accept(...)` applies HTTP media type semantics; when choosing among multiple representations by preference, define ordered routes and test them, or use a proper content negotiation strategy.

**Important note:** Two routes sharing the same path and method with `accept(JSON)` and `accept(TEXT_PLAIN)` can **both match** a client sending `Accept: */*`. In that case, functional route ordering decides which handler wins. Do not treat `Accept` as mutually exclusive unless client contracts and route order are controlled.

## 11. Routing by both Content-Type and Accept

An endpoint accepting JSON and returning JSON:

```java
RequestPredicate jsonRequestAndResponse =
    RequestPredicates.contentType(MediaType.APPLICATION_JSON)
        .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> router = RouterFunctions.route()
    .POST("/api/books", jsonRequestAndResponse, handler::createJson)
    .build();
```

This is a snippet inside a class with `handler`. Requests must send both a matching `Content-Type` and compatible `Accept`:

```http
POST /api/books HTTP/1.1
Content-Type: application/json
Accept: application/json

{"title":"Routing"}
```

If the client sends `Content-Type: text/plain` and `Accept: application/json`, the JSON route does not match because the request body type is wrong. If the client sends `Content-Type: application/json` and `Accept: text/plain`, the JSON route does not match because the output representation is unacceptable.

**The route contract is logical AND**, yet the default HTTP status on non-match cannot be deduced from the boolean alone. Depending on other routes, fallbacks, handlers, and WebFlux version, a mismatch may surface as a no-handler 404 or a 406/415 from media-mismatch handling. If the API contract strictly requires 406/415, integration tests must prove it and an explicit error policy should be configured when needed.

## 12. Combining predicates with and, or, and negate

`RequestPredicate` supports composition:

```java
RequestPredicate wantsJson =
    RequestPredicates.accept(MediaType.APPLICATION_JSON);

RequestPredicate internalView =
    RequestPredicates.headers(h ->
        "internal".equals(h.firstHeader("X-View")));

RequestPredicate strict =
    wantsJson.and(internalView);

RequestPredicate either =
    wantsJson.or(RequestPredicates.accept(MediaType.TEXT_PLAIN));

RequestPredicate notInternal = internalView.negate();
```

These variables are code snippets inside a Java method with static or regular imports.

- `A.and(B)`: request must satisfy **both**.
- `A.or(B)`: at least one matches.
- `A.negate()`: inverts the condition.
- Composition can short-circuit; do not put important side effects inside a predicate assuming it will always run.
- Predicates should be fast checks that never block on I/O or mutate resource state.
- Complex combined conditions should be named clearly (`jsonOnly`, `traceView`, `businessVersion`) and unit-tested individually.

### When you need a custom RequestPredicate

```java
RequestPredicate validApiKeyFormat = request ->
    request.headers().firstHeader("X-Api-Key") != null;
```

This only checks **presence** of the header, **not secret validity**, and is insufficient to protect an API. Restrict custom predicates to stable request-routing criteria; perform authentication via Spring Security and business validation after a route matches. A predicate should never make blocking DB calls or manually subscribe to a reactive pipeline just to decide routing.

## 13. Functional routing prioritizes declaration order

Per the Spring Framework reference, routes are evaluated **in order**. Once the first route matches, later routes are not preferred simply because their pattern is more specific.

Wrong:

```java
RouterFunctions.route()
    .GET("/api/books/{id}", handler::getById)
    .GET("/api/books/special", handler::special)
    .build();
```

A `GET /api/books/special` request enters `getById` with `id="special"`.

Right:

```java
RouterFunctions.route()
    .GET("/api/books/special", handler::special)
    .GET("/api/books/{id}", handler::getById)
    .build();
```

**Nesting does not automatically fix route ordering.** Inside `.path(prefix, b -> ...)`, still declare `special` before variable segments. When splitting across multiple `RouterFunction` beans, `RouterFunctionMapping` can order/combine beans via `Ordered`; do not expect lexical bean names or source file order to always win. If route ordering carries business meaning, keep routes in one clear router builder or use tested `@Order` annotations.

### Header/media conditions can shadow one another

If a broad route `GET("/api/books", handler::all)` precedes `GET("/api/books", headers(...), handler::special)`, every request matching the broad route goes to `all`, even with the special header present. Place the specific header-predicated route **first**, or use distinct paths to avoid ambiguity.

If you place GET JSON before GET text on the same path and a client sends `Accept: */*`, JSON wins. That is not a codec bug; it is route-order logic.

## 14. Routing by query parameter (auxiliary)

Although the focus is path/method/header/media, query parameters often appear in route conditions:

```java
RouterFunctions.route()
    .GET("/api/books",
        RequestPredicates.queryParam("view", "compact"),
        handler::compact)
    .GET("/api/books", handler::list)
    .build();
```

A `?view=compact` request selects the first route; absent or different values fall through to the second. Put the conditional route before the fallback route. `queryParam` inspects **parsed** query parameters, not raw URI substrings. Data containing `&` or `=` must be properly component-encoded; never call `URLDecoder` twice.

With multiple values for the same name, do not treat a `queryParam` predicate as full validation of repeated-parameter policies. Handlers can inspect `request.queryParams()`/`queryParam(...)` and define whether duplicates are allowed.

**Never place identity or authorization in query parameters insecurely**: `?role=admin` is not a permission, and query strings frequently appear in logs and browser history.

## 15. Writing responses with ServerResponse

A functional handler returns `Mono<ServerResponse>`, typically built via the fluent builder:

```java
public Mono<ServerResponse> okBook(ServerRequest request) {
    BookView body = new BookView(
        request.pathVariable("id"), "Read book");

    return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(body);
}
```

This is a snippet requiring the corresponding `BookView` record.

Patterns:

| Builder | Meaning |
| --- | --- |
| `ServerResponse.ok()` | HTTP 200 |
| `ServerResponse.status(HttpStatus.CREATED)` | HTTP 201 |
| `ServerResponse.accepted()` | HTTP 202 |
| `ServerResponse.noContent()` | HTTP 204 without body |
| `ServerResponse.badRequest()` | HTTP 400 |
| `ServerResponse.notFound()` | HTTP 404 |
| `ServerResponse.status(HttpStatus.UNSUPPORTED_MEDIA_TYPE)` | HTTP 415 if returned explicitly by app |
| `.header("X-Request-Id", id)` | Response header |
| `.contentType(MediaType.APPLICATION_JSON)` | Response representation |
| `.bodyValue(dto)` | Encodes a regular body value via codecs |
| `.body(flux, Dto.class)` | Writes a reactive body stream |

Creating a `Mono<ServerResponse>` does not immediately write bytes; the HTTP infrastructure subscribes, invokes `ServerResponseResultHandler` and codecs, and writes data during the response lifecycle.

### Reading the request body after a route matches

```java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateBook.class)
        .flatMap(input ->
            ServerResponse.status(HttpStatus.CREATED)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new BookView("book_1", input.title())));
}
```

This snippet does not handle empty or invalid bodies yet. In real apps, add `switchIfEmpty(ServerResponse.badRequest().build())` and validation. The router's `contentType` predicate **does not replace** JSON decoding or Bean Validation.

Never call `request.bodyToMono(...).block()` inside a handler; the Netty event loop is not meant for blocking work.

## 16. Complete Spring Boot 3 Java 17+ application

Maven project generated with Spring Initializr, dependencies:

- `spring-boot-starter-webflux` (runtime).
- `spring-boot-starter-test` (test scope).
- `io.projectreactor:reactor-test` if not pulled in by the test starter.

No database, Spring Security, Servlet MVC, or template engine is needed. Files:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  BookHandler.java
  BookRoutes.java
src/test/java/com/example/demo/
  BookRoutesTest.java
```

**Demo endpoints:**

| Method | URL | Additional predicate | Result |
| --- | --- | --- | --- |
| GET | `/api/books/special` | `Accept` JSON | Special book JSON |
| GET | `/api/books/{id}` | `Accept` JSON | Book JSON with ID |
| POST | `/api/books` | `Content-Type` JSON **and** `Accept` JSON | 201 JSON |
| POST | `/api/books` | `Content-Type` text/plain **and** `Accept` text/plain | 200 text |
| GET | `/api/status` | `X-View: trace` | Status JSON |
| GET | `/api/stream` | `Accept` SSE | Three SSE events |
| GET | `/api/docs/hello` | Nested path | Greeting JSON |

The POST routes share the same path and method, **distinguished explicitly by `Content-Type`**; representation is never guessed from body contents alone. Tests send explicit `Accept` headers to avoid wildcard ambiguity.

### 16.1. DemoApplication.java

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 16.2. BookHandler.java

```java
package com.example.demo;

import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    public Mono<ServerResponse> special(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new BookView("special", "Special book"));
    }

    public Mono<ServerResponse> getById(ServerRequest request) {
        String id = request.pathVariable("id");

        if (!id.matches("[A-Za-z0-9_-]{1,64}")) {
            return ServerResponse.badRequest().build();
        }

        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new BookView(id, "Book " + id));
    }

    public Mono<ServerResponse> createJson(ServerRequest request) {
        return request.bodyToMono(CreateBook.class)
            .flatMap(input -> {
                if (input.title() == null ||
                    input.title().isBlank() ||
                    input.title().length() > 120) {
                    return ServerResponse.badRequest().build();
                }

                return ServerResponse.status(HttpStatus.CREATED)
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new BookView("book_1",
                                             input.title()));
            })
            .switchIfEmpty(ServerResponse.badRequest().build());
    }

    public Mono<ServerResponse> createText(ServerRequest request) {
        return request.bodyToMono(String.class)
            .flatMap(raw -> {
                if (raw.isBlank() || raw.length() > 120) {
                    return ServerResponse.badRequest().build();
                }
                return ServerResponse.ok()
                    .contentType(MediaType.TEXT_PLAIN)
                    .bodyValue("text:" + raw);
            })
            .switchIfEmpty(ServerResponse.badRequest().build());
    }

    public Mono<ServerResponse> status(ServerRequest request) {
        // X-View is request metadata, not authentication.
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new StatusView("trace"));
    }

    public Mono<ServerResponse> events(ServerRequest request) {
        Flux<NumberEvent> data = Flux.range(1, 3)
            .delayElements(Duration.ofMillis(60))
            .map(NumberEvent::new);

        return ServerResponse.ok()
            .contentType(MediaType.TEXT_EVENT_STREAM)
            .body(data, NumberEvent.class);
    }

    public Mono<ServerResponse> docsHello(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new StatusView("docs-hello"));
    }

    public record BookView(String id, String title) {}
    public record CreateBook(String title) {}
    public record StatusView(String mode) {}
    public record NumberEvent(int value) {}
}
```

Explanation:

- `BookHandler` is a Spring bean whose methods accept `ServerRequest` and return `Mono<ServerResponse>`.
- `getById` validates a path-safe ID, which **does not** replace domain resource authorization in production.
- `createJson` reads a JSON body and returns 201; every demo request emits the same ID `book_1` for simplicity, with **no** durable persistence. Production requires DB uniqueness, idempotency, and permissions.
- `createText` reads `text/plain` without deserializing JSON.
- `status` does not read or infer roles from `X-View`; the header only distinguishes the demo route.
- `events` returns a finite `Flux` with SSE `Content-Type`; the delay is only for observation, not a latency guarantee.
- `switchIfEmpty(ServerResponse.badRequest().build())` handles empty bodies without creating a second subscription on the body stream.
- For malformed JSON, the decoder may emit an error before `flatMap` runs; HTTP error status/body depends on WebFlux error handling. For a unified error contract, add a `WebExceptionHandler` or functional routing error handler per your policy.

### 16.3. BookRoutes.java

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicate;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class BookRoutes {

    @Bean
    public RouterFunction<ServerResponse> functionalBookRoutes(
            BookHandler handler) {

        RequestPredicate jsonInputAndOutput =
            RequestPredicates.contentType(MediaType.APPLICATION_JSON)
                .and(RequestPredicates.accept(
                    MediaType.APPLICATION_JSON));

        RequestPredicate textInputAndOutput =
            RequestPredicates.contentType(MediaType.TEXT_PLAIN)
                .and(RequestPredicates.accept(MediaType.TEXT_PLAIN));

        RequestPredicate traceHeader =
            RequestPredicates.headers(h ->
                "trace".equals(h.firstHeader("X-View")));

        return RouterFunctions.route()

            // Place /special before /{id} so the specific route wins.
            .path("/api/books", b -> b
                .GET("/special",
                     RequestPredicates.accept(
                         MediaType.APPLICATION_JSON),
                     handler::special)
                .GET("/{id}",
                     RequestPredicates.accept(
                         MediaType.APPLICATION_JSON),
                     handler::getById)
                .POST(jsonInputAndOutput, handler::createJson)
                .POST(textInputAndOutput, handler::createText))

            .GET("/api/status", traceHeader, handler::status)

            .GET("/api/stream",
                 RequestPredicates.accept(
                     MediaType.TEXT_EVENT_STREAM),
                 handler::events)

            .path("/api/docs", b -> b
                .GET("/hello", handler::docsHello))

            .build();
    }
}
```

Why this is a good example for the topic:

1. **Path**: nested `/api/books`, `/api/docs`; `/special` precedes `/{id}`.
2. **Method**: GET and POST are kept distinct.
3. **Header**: `/api/status` matches only when `X-View` equals `trace`.
4. **Content-Type**: selects POST JSON vs. POST text.
5. **Accept**: requires the client to accept the matching representation, plus a dedicated SSE route.
6. **Composition**: `and` enforces both input and output media-type conditions.
7. **No shadowing**: routes sharing path/method are disambiguated by explicit predicates.
8. **No unnecessary `@EnableWebFlux`**: lets Spring Boot WebFlux auto-configuration set up the infrastructure cleanly.

### 16.4. Running the demo

In the Maven project directory with the wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

The default port is usually `8080` unless `server.port` is changed. Spring sources need the dependency classpath; do not run `javac BookRoutes.java` standalone without Spring/Reactor libraries.

## 17. curl: GET path and Accept

### Special route

```bash
curl -i 'http://localhost:8080/api/books/special' \
  -H 'Accept: application/json'
```

Expected HTTP 200 and JSON:

```json
{"id":"special","title":"Special book"}
```

Test purpose: `/special` matched **before** `/{id}`. If the route order were reversed, the same request would hit the generic handler and return `{"id":"special","title":"Book special"}`. That is a clear symptom of shadowing.

### Variable route

```bash
curl -i 'http://localhost:8080/api/books/book_42' \
  -H 'Accept: application/json'
```

Expected:

```json
{"id":"book_42","title":"Book book_42"}
```

The path variable is validated by the application against `[A-Za-z0-9_-]{1,64}`. `/api/books/../../secret` is not a valid way to read resources and may be stripped early by a gateway normalizer/canonicalizer; server-side authorization and ID mapping are still required.

### Nested path

```bash
curl -i 'http://localhost:8080/api/docs/hello'
```

Expected HTTP 200:

```json
{"mode":"docs-hello"}
```

The endpoint requires no `Accept` predicate, yet the handler sets `Content-Type: application/json`. If a client rejects JSON via a different `Accept` header, codec/content negotiation or error handlers may respond differently; a route match does not replace writing a suitable representation.

## 18. curl: testing the header predicate

```bash
curl -i 'http://localhost:8080/api/status' \
  -H 'X-View: trace'
```

Expected HTTP 200:

```json
{"mode":"trace"}
```

If `X-View` is omitted or sent as `X-View: debug`, the predicate does not match. In this demo project there is no fallback route for `/api/status`, so it typically returns HTTP 404 (depending on the error layer); verify directly with integration tests rather than assuming a missing header yields 403.

**Why not 403?** A header predicate only routes requests; it is not an authorization mechanism. To protect endpoints, declare Spring Security policies and verify user/role/tenant. Returning 404 for an unmatched route and 403 for an unauthorized user are two different concerns.

## 19. curl: POST Content-Type and Accept

### 19.1. JSON in, JSON out

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"title":"Learn Spring WebFlux"}'
```

Expected status **201 Created** and JSON:

```json
{"id":"book_1","title":"Learn Spring WebFlux"}
```

Why are both headers included? `Content-Type` describes the JSON body, and `Accept` indicates the client accepts JSON. A client sending `Accept: */*` still matches the JSON route by compatibility; this is not a literal string switch requiring `Accept: application/json`.

### 19.2. Plain text in, plain text out

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: text/plain' \
  -H 'Accept: text/plain' \
  --data-binary 'hello'
```

Expected status 200, `Content-Type: text/plain`, body:

```text
text:hello
```

Same URL + POST, but a different `Content-Type`, so a different handler is chosen.

### 19.3. Mismatched Content-Type/Accept

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/plain' \
  -d '{"title":"not-matched"}'
```

No route in the demo satisfies **both** conditions simultaneously. **Do not hardcode a single status code across all WebFlux versions**, because no-match/media-mismatch handling can flow through `RouterFunctionMapping`/`WebExceptionHandler`; inspect the real HTTP response and decide whether a dedicated error contract is needed.

Specifically, 415 represents an unsupported request media type, 406 represents an unacceptable response representation, and 404 represents no matching resource/route. Their HTTP meanings differ, yet a functional predicate mismatch is **not** identical to controller `consumes/produces` annotations generating the same statuses automatically.

### 19.4. Malformed JSON

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"title":'
```

The `Content-Type` and `Accept` predicates still match; the **body parser** fails while decoding `CreateBook`, typically returning 400 via WebFlux error infrastructure. Never write predicates that inspect JSON body contents once the body is consumed once.

### 19.5. Request missing body

```bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data-binary ''
```

The route still matches on `Content-Type`; `bodyToMono` completes empty and the handler's `switchIfEmpty` returns 400. Do not confuse "route matched" with "body passes validation".

## 20. curl: Server-Sent Events and media negotiation

```bash
curl -N -i 'http://localhost:8080/api/stream' \
  -H 'Accept: text/event-stream'
```

Expected status 200, `Content-Type: text/event-stream`, and events:

```text
data:{"value":1}

data:{"value":2}

data:{"value":3}

```

Reactor `Flux.range(1,3).delayElements(...)` emits three elements in order. `curl -N` disables buffering in `curl`, though **each SSE event does not equate to a single TCP packet**, and timing is not guaranteed to be exactly 60ms. If the client disconnects early, downstream can cancel the subscription.

SSE requires connection limits, buffer bounds, idle timeouts, authentication, and reconnect/replay policies. Content negotiation selects the codec; it does not bound memory on its own.

## 21. WebTestClient: verifying route selection and predicate differences

File `src/test/java/com/example/demo/BookRoutesTest.java`:

```java
package com.example.demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BookRoutesTest {

    @Autowired
    WebTestClient client;

    @Test
    void specificPathWinsBeforeIdPath() {
        client.get().uri("/api/books/special")
            .accept(MediaType.APPLICATION_JSON)
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("special")
            .jsonPath("$.title").isEqualTo("Special book");
    }

    @Test
    void pathVariableIsBoundIntoHandler() {
        client.get().uri("/api/books/book_42")
            .accept(MediaType.APPLICATION_JSON)
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.id").isEqualTo("book_42")
            .jsonPath("$.title").isEqualTo("Book book_42");
    }

    @Test
    void headerPredicateSelectsRoute() {
        client.get().uri("/api/status")
            .header("X-View", "trace")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.mode").isEqualTo("trace");
    }

    @Test
    void missingHeaderDoesNotMatchThisRoute() {
        client.get().uri("/api/status")
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void jsonInputAndJsonAcceptUseJsonHandler() {
        client.post().uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of("title", "WebFlux"))
            .exchange().expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("book_1")
            .jsonPath("$.title").isEqualTo("WebFlux");
    }

    @Test
    void textInputAndTextAcceptUseTextHandler() {
        client.post().uri("/api/books")
            .contentType(MediaType.TEXT_PLAIN)
            .accept(MediaType.TEXT_PLAIN)
            .bodyValue("hello")
            .exchange().expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_PLAIN)
            .expectBody(String.class).isEqualTo("text:hello");
    }

    @Test
    void emptyJsonBodyFailsValidation() {
        client.post().uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue("")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void nestedPathIsMatched() {
        client.get().uri("/api/docs/hello")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.mode").isEqualTo("docs-hello");
    }

    @Test
    void sseStreamEmitsThreeItems() {
        Flux<BookHandler.NumberEvent> events = client.get()
            .uri("/api/stream")
            .accept(MediaType.TEXT_EVENT_STREAM)
            .exchange().expectStatus().isOk()
            .returnResult(BookHandler.NumberEvent.class)
            .getResponseBody();

        StepVerifier.create(events)
            .expectNext(new BookHandler.NumberEvent(1))
            .expectNext(new BookHandler.NumberEvent(2))
            .expectNext(new BookHandler.NumberEvent(3))
            .verifyComplete();
    }
}
```

**This is a sample test suite that has not been executed in the user's repository.** Spring Boot 3/`WebTestClient`/Netty codecs require the dependencies listed earlier.

**Caveat on the empty JSON test:** `bodyValue("")` with `contentType(APPLICATION_JSON)` may be encoded by a JSON encoder as a JSON string literal `""` rather than a 0-byte request body; the `CreateBook` decoder still produces a 400 error, but does not prove the `switchIfEmpty` branch. To test an exact zero-length request body, use `BodyInserters.empty()` or an empty body accordingly and assert. Depending on codec/version, test malformed JSON and empty bodies separately.

**Caveat on the SSE codec:** some `WebTestClient` configurations may decode SSE as `ServerSentEvent<NumberEvent>` or require `ParameterizedTypeReference` instead of the DTO class directly. If a codec mismatch occurs, use `ServerSentEvent<BookHandler.NumberEvent>` and assert `event.data()`; never equate a network chunk with a single event. Conceptually, the `returnResult`/`StepVerifier` pattern is sound.

**Caveat on no-match:** the missing-header test expects 404 in the standard demo configuration; if the application adds an exception handler or fallback router, update the contract. Do not force 404 on an app customized to return a different status.

Run tests:

```bash
./mvnw test
```

Windows PowerShell:

```powershell
.\mvnw.cmd test
```

If reactive Spring Security is enabled, POST endpoints may require a CSRF token and unauthenticated requests may receive 401/403 before reaching the router; tests must configure authentication/CSRF according to policy. The demo has no Spring Security.

## 22. Testing pure RouterFunction without an HTTP server

To test route selection quickly, Spring lets you create a mock `ServerRequest` via `MockServerRequest` (in `spring-test`) or use `WebTestClient.bindToRouterFunction(routes)` without opening a port.

Concept:

```java
WebTestClient client = WebTestClient
    .bindToRouterFunction(bookRoutes)
    .build();
```

This snippet uses a `bookRoutes` variable and imports `org.springframework.test.web.reactive.server.WebTestClient`. With `bindToRouterFunction`, you can verify predicates and handlers without starting Netty; however, it **does not necessarily** include the full security, filter, and exception infrastructure of a Boot app. Combine router unit tests with HTTP integration tests to verify statuses, media negotiation, CORS, or proxy behavior.

### Testing the contract with a matrix instead of a single happy path

| Method | Path | X-View | Content-Type | Accept | Expected route |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/books/special` | — | — | JSON | `special` |
| GET | `/api/books/book_42` | — | — | JSON | `getById` |
| POST | `/api/books` | — | JSON | JSON | `createJson` |
| POST | `/api/books` | — | text/plain | text/plain | `createText` |
| GET | `/api/status` | trace | — | */* | `status` |
| GET | `/api/status` | absent | — | */* | Does not match `status` route |
| GET | `/api/stream` | — | — | text/event-stream | `events` |
| GET | `/api/docs/hello` | — | — | */* | `docsHello` |

Dashes `—` indicate headers not required by the predicate under test. Specifically for HTTP GET requests without a body, `Content-Type` is normally irrelevant; never force GET clients to send `Content-Type` just to match a response type. `Accept` typically defaults to a wildcard if omitted by the client.

Be sure to test `Accept: */*`, lowercase/uppercase headers, duplicate query params, encoded paths, trailing slashes, `OPTIONS`/CORS preflight, and wrong HTTP methods to uncover ambiguities.

## 23. Plain Java 17: demonstrating deterministic route order

This section does not use Spring. It uses plain Java 17 to demonstrate a simple functional router scanning conditions **in order** and picking the first one that matches.

File `RouteOrderDemo.java`:

```java
import java.util.List;
import java.util.function.Predicate;

public class RouteOrderDemo {

    record Request(String method, String path, String accept) {}
    record Route(String name, Predicate<Request> matches) {}

    public static void main(String[] args) {
        List<Route> wrongOrder = List.of(
            new Route("byId",
                r -> r.method().equals("GET") &&
                     r.path().startsWith("/books/")),
            new Route("special",
                r -> r.method().equals("GET") &&
                     r.path().equals("/books/special"))
        );

        List<Route> rightOrder = List.of(
            wrongOrder.get(1),
            wrongOrder.get(0)
        );

        Request req = new Request(
            "GET", "/books/special", "application/json");

        System.out.println("wrong=" + choose(wrongOrder, req));
        System.out.println("right=" + choose(rightOrder, req));
    }

    private static String choose(
            List<Route> routes, Request request) {
        return routes.stream()
            .filter(route -> route.matches().test(request))
            .map(Route::name)
            .findFirst()
            .orElse("not-found");
    }
}
```

Compile and run:

```bash
javac RouteOrderDemo.java
java RouteOrderDemo
```

Exact stdout:

```text
wrong=byId
right=special
```

This program illustrates the **first matching predicate** idea rather than implementing Spring `PathPattern`, MIME compatibility, header parsing, or Reactor. To verify real WebFlux.fn behavior, run the Boot project tests above.

## 24. Security when routing by headers and paths

Routing by headers, paths, or content types **does not replace authentication, authorization, or input validation**:

- Client-asserted `X-User`, `X-Tenant`, and `X-Role` headers are not trustworthy identities.
- `RequestPredicates.headers(h -> "admin".equals(...))` is branch selection, not a security guard.
- Use Spring Security `SecurityWebFilterChain`, protect routes, and check resource-level permissions after binding IDs.
- Account for both functional and annotated routes in the same WebFlux app; a rule matching only annotation metadata can miss functional routes if misconfigured.
- CORS preflight `OPTIONS` may be handled by `CorsWebFilter`/security chains before routing; never create an `OPTIONS` route returning "allow all" to bypass policy.
- `Content-Type` does not prove a body is safe: validate size, JSON syntax, schema, and business rules.
- `Accept` does not prevent HTML/XSS if you write unescaped data into `text/html`; apply context-appropriate output encoding.
- Raw paths, encoded slashes, and trailing slashes require consistent canonicalization across proxy, server, and security layers.
- Control method overrides from gateways/proxies if enabled; avoid infrastructure interpreting POST differently as PUT/PATCH.
- Do not log full `Authorization`, `Cookie`, or query strings containing secrets when debugging route mismatches.
- For multipart uploads and form parsing, enforce size/count limits and clean up `DataBuffer`s.
- Path variables must never be concatenated directly into filesystem paths to open files.

**Trust policies** belong in authentication/security layers; predicates should only inspect request metadata for dispatch.

## 25. When do 404, 405, 406, and 415 occur?

HTTP semantics:

| Status | Meaning | Scenario |
| --- | --- | --- |
| `404 Not Found` | No matching representation/resource disclosed | No route matches or server intentionally hides resource |
| `405 Method Not Allowed` | URL/resource exists, but method is unsupported | Needs an appropriate `Allow` header |
| `406 Not Acceptable` | No response representation acceptable to client | Incompatible `Accept` |
| `415 Unsupported Media Type` | Request body `Content-Type` is unsupported | Client sends wrong content type |
| `400 Bad Request` | Invalid input format/schema/validation | Malformed JSON, invalid path ID, missing required field |
| `401 Unauthorized` | Unauthenticated per policy | Security entrypoint |
| `403 Forbidden` | Authenticated but lacks permission | Authorization failure |

**Do not deduce** that `RequestPredicates.accept(...)` returning false **always** produces 406, or that `contentType(...)` returning false **always** produces 415. In WebFlux.fn, a false predicate usually just causes the router to check subsequent routes; the error produced when all routes fail depends on mapping/error infrastructure and other registered routes. Annotated controllers have different mismatch diagnostics in Spring, so do not transfer that behavior verbatim to functional endpoints.

If your API strictly requires 405/406/415:
1. Define the expected contract explicitly.
2. Test the method/path/`Content-Type`/`Accept` matrix against a real HTTP server.
3. Add fallback routes, error handlers, or infrastructure configuration if defaults differ from expectations.
4. Never return 200 for malformed JSON or unacceptable media types just to make the API "easier to call".
5. Never place a catch-all route before specific routes, as it will shadow specialized status handling.

## 26. Debugging routing when results are unexpected

Diagnostic steps from simplest to deepest:

1. Confirm the application is actually running **WebFlux** (Boot starter, application type, Reactor Netty) rather than MVC.
2. Confirm `RouterFunction<ServerResponse>` is registered as a Spring bean in the application context, not left as an unregistered local variable.
3. Check the HTTP method from the client (`GET` vs. `POST`; `HEAD`/`OPTIONS` have special handling).
4. Check paths and ordering: static before variables, nested base paths, trailing slashes, context paths, encoded separators.
5. Inspect raw `Content-Type` and `Accept` actually sent; client libraries often add default `Accept` or content-type headers.
6. Verify custom `headers(...)` predicates compare names/values properly and handle null missing headers.
7. Confirm `and`/`or`/`negate` express the intended logic; `Accept: */*` can match multiple routes.
8. Check `RouterFunctionMapping` ordering when the app has multiple router beans or annotated controllers.
9. If the route matched but the body fails, check `bodyToMono`, codecs, validation, and `ServerResponse.contentType`.
10. Check whether `WebFilter`, Spring Security, or CORS rejects the request before the router runs.
11. If the response already committed and the stream errors, status/body cannot always be changed; focus on logging/cancellation cleanup.
12. Use `WebTestClient` with explicit request headers instead of testing only through a caching/proxying browser.
13. Enable route-mapping diagnostics carefully in test/staging without exposing secrets.
14. For redirects/proxies, verify trusted forwarded headers to prevent wrong host/scheme/path generation.
15. Compare the exact same HTTP request against direct Netty vs. production ingress when suspecting proxy rewrites.

### Anti-pattern: checking headers inside the handler instead of routing

```java
.GET("/api/status", request -> {
    if ("trace".equals(
            request.headers().firstHeader("X-View"))) {
        return handler.status(request);
    }
    return ServerResponse.notFound().build();
})
```

This works, yet if the intent is a *route selection condition*, using `headers(...)` expresses the contract more clearly and allows fallback routes. **Never** use header predicates for auth; both approaches still require dedicated security policies.

## 27. Common mistakes

1. **Importing MVC.fn packages in a WebFlux project:** classes share names but have different reactive/servlet APIs.
2. **Defining a `RouterFunction` without `@Bean`:** WebFlux does not discover the router.
3. **Placing `/{id}` before `/special`:** the generic route swallows the request.
4. **Assuming functional routing picks the most specific pattern:** declaration order wins.
5. **Placing a predicate-free GET route before a header-predicated GET route:** the header route is never reached.
6. **Confusing `Content-Type` with `Accept`:** one describes the request body, the other the accepted response.
7. **Comparing `Accept` literals with `equals`:** wildcards, quality factors, and media compatibility are ignored.
8. **Assuming `Content-Type: application/json` guarantees valid JSON:** decoding and validation are still required.
9. **Routing only on `Content-Type` while returning a body incompatible with `Accept`:** clients may fail to handle it.
10. **Omitting response `contentType` when returning JSON/SSE:** causes codec/media mismatches.
11. **Using `X-Role` headers for auth:** client-supplied headers are trivial to spoof.
12. **Assuming HTTP 415/406 always appears when a predicate is false:** the router may treat it merely as no-match.
13. **Not testing POST method mismatches:** 405/404/`OPTIONS` behavior varies across stacks.
14. **Not testing `HEAD`/`OPTIONS`/CORS:** browsers send preflights before actual requests.
15. **Not validating path variables:** malformed IDs can break parsing or enable resource traversal.
16. **Manually double-decoding URI paths:** can turn encoded data into path separators.
17. **Placing broad wildcard route patterns before protected routes:** shadows matching and security expectations.
18. **Wrapping text POST routes in a nested `accept(JSON)`:** the text branch gets excluded beforehand.
19. **Writing custom `RequestPredicate`s that call JDBC or block:** stalls the reactive event loop.
20. **Calling `subscribe()` inside `HandlerFunction`:** detaches completion/error/cancel from HTTP.
21. **Calling `block()` on the Netty event loop:** degrades throughput or triggers Reactor exceptions.
22. **Applying `contentType(JSON)` to bodyless GET routes:** may reject valid requests.
23. **Not bounding request body size before decoding:** causes memory/CPU pressure.
24. **Accepting malformed JSON and returning 200 empty:** hides validation failures.
25. **Conflating query parameters with header predicates:** different request metadata.
26. **Creating overlapping `RouterFunction` beans without `@Order`:** route choice depends on undefined order.
27. **Assuming clients always send a specific `Accept`:** many clients send `*/*`.
28. **Hardcoding JSON property order or stdout timestamps in tests:** creates flaky, brittle tests.
29. **Assuming each SSE element is one TCP packet:** network framing differs from message boundaries.
30. **Not cleaning up on client disconnect:** leaks event subscriptions and timers.
31. **Treating a 201 response as real persistence:** the demo has no database.
32. **Skipping authenticated principal/resource permission checks after route match:** route matching grants no privileges.
33. **Turning 404 into a catch-all 200 for unknown APIs:** hides client errors.
34. **Assuming path routing handles all encoded characters:** requires canonicalization and URL-safe IDs.
35. **Confusing `RouterFunctionMapping` with `RequestMappingHandlerMapping`:** functional and annotated routes do not share precedence rules.
36. **Modifying WebFlux SPI just to add a GET/POST route:** the builder is sufficient.
37. **Inferring a trusted tenant from header metadata:** tenant must come from trusted identity/authorization.
38. **Skipping multi-representation content negotiation tests:** wildcard `Accept` creates ambiguity.

## 28. Production and code review checklist

### Routing

- [ ] Using `org.springframework.web.reactive.function.server` for the WebFlux stack?
- [ ] `@Bean RouterFunction<ServerResponse>` registered and discovered by Boot?
- [ ] Static paths placed before path variables and generic wildcards?
- [ ] Nested path prefixes free of unintended repeated or double slashes?
- [ ] HTTP method routes match API contract (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS)?
- [ ] Header predicates short, pure, and never used as authentication?
- [ ] `contentType` used for request body type, `accept` for response type?
- [ ] Combined `and/or/negate` predicates covered by dedicated tests?
- [ ] No routes shadowing one another when clients send `Accept: */*`?
- [ ] Multiple `RouterFunction` beans explicitly ordered if overlapping?

### HTTP responses and security

- [ ] `ServerResponse` sets accurate status and response `Content-Type`?
- [ ] Body readers/codecs parse JSON/form/multipart for the appropriate media types?
- [ ] Body size, validation, and authorization checked after route matching?
- [ ] No blocking I/O, `block()`, or manual `subscribe()` inside handlers?
- [ ] Custom headers or path IDs never trusted as authenticated identity?
- [ ] Spring Security/CORS/CSRF policies aligned with functional routes?
- [ ] Committed responses, stream cancellations, and errors have proper cleanup?
- [ ] Tokens, cookies, and raw queries with secrets excluded from logs?

### Testing

- [ ] Tested that static `/special` beats generic `/{id}`?
- [ ] Tested POST JSON and POST text with explicit `Content-Type`/`Accept`?
- [ ] Tested header present, absent, and wrong value?
- [ ] Tested wildcard `Accept`, swapped text/JSON, and wrong HTTP methods?
- [ ] Tested 400 on malformed/empty body and domain-invalid fields?
- [ ] Tested unknown path/no-match, nested routes, and trailing slashes?
- [ ] Tested with `WebTestClient` + a real HTTP server to exercise the error pipeline?
- [ ] Tested through proxy/gateway if path rewrites or forwarded headers exist?
- [ ] Tested SSE events and cancellation when streaming is used?

## 29. Self-check questions

**1.** How does `RouterFunction` differ from `HandlerFunction`?

**Answer:** `RouterFunction` selects a handler using predicates; `HandlerFunction` processes the request and returns `Mono<ServerResponse>`.

**2.** Why should `GET("/books/{id}")` come after `GET("/books/special")`?

**Answer:** Functional routes are evaluated in order; the generic route would match `"special"` as an ID rather than picking the most specific pattern automatically.

**3.** What does `contentType(APPLICATION_JSON)` check?

**Answer:** The type of **request body** sent by the client, not the body type the server will return.

**4.** What does `accept(APPLICATION_JSON)` check?

**Answer:** The `Accept` header indicating the representation the client can receive.

**5.** Does `ServerResponse.contentType(APPLICATION_JSON)` replace the `accept(JSON)` predicate?

**Answer:** No. It specifies the response representation/codec, whereas the predicate participates in route selection.

**6.** Can the `X-Role: ADMIN` header be used as a permission condition?

**Answer:** No; clients can forge it. Spring Security and business authorization determine permissions.

**7.** How do `and` and `or` differ in `RequestPredicate`?

**Answer:** `and` requires both to be true, `or` requires at least one; verify order and test compositions.

**8.** Which routes can an `Accept: */*` request match?

**Answer:** It can match multiple compatible representations; functional route order decides when multiple routes match.

**9.** When sending `Content-Type: text/plain` to a JSON-only route, is the status guaranteed to be 415?

**Answer:** You cannot conclude that from a false predicate alone. It may become a no-match depending on infrastructure; the HTTP contract must be tested/configured.

**10.** Can annotated controllers and functional routes be used together?

**Answer:** Yes, on the same WebFlux `DispatcherHandler`, though with different mapping/adapter/result handlers. Avoid unintended overlaps.

**11.** Is using `@RequestBody` inside a `HandlerFunction` valid?

**Answer:** The functional model uses `ServerRequest.bodyToMono(...)` or `bodyToFlux(...)`, not controller-style method parameter annotations.

**12.** Should a `HandlerFunction` call `Mono.subscribe()` manually to write the body?

**Answer:** No. Return `Mono<ServerResponse>` to the WebFlux HTTP infrastructure.

**13.** When should `.path(prefix, builder)` be used?

**Answer:** When multiple routes share a path prefix such as `/api/books`; specific-before-general ordering is still needed inside.

**14.** Why is a route match insufficient to guarantee a 200 response?

**Answer:** The body may be malformed, validation may fail, authorization may be missing, a codec may be unsupported, or a downstream error may occur.

**15.** When should `WebTestClient.bindToRouterFunction` be used?

**Answer:** When you want fast router/handler logic tests without starting a server, complemented by HTTP integration tests to cover security, filters, and transport.

## 30. References

- Spring Framework 6.2 — Functional Endpoints (WebFlux.fn) and route ordering/nesting/predicates: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework 6.2 — `RequestPredicates` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html
- Spring Framework 6.2 — `RouterFunctions.Builder` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html
- Spring Framework 6.2 — `ServerRequest` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html
- Spring Framework 6.2 — `ServerResponse` (reactive API Javadoc): https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html
- Spring Framework 6.2 — DispatcherHandler and WebFlux routing SPI: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html
- Spring Framework — Path Patterns: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-requestmapping.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Security — Reactive/WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/index.html
- Reactor Core Reference — reactive lifecycle, backpressure and schedulers: https://projectreactor.io/docs/core/release/reference/
- RFC 9110 — HTTP Semantics, Accept, Content-Type, status codes and methods: https://www.rfc-editor.org/rfc/rfc9110.html
