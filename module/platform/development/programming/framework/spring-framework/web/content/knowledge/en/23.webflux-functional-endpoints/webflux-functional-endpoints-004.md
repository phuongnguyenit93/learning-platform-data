# Nesting, Router Composition, and Feature-Oriented Routing in Spring WebFlux

## 1. Overview: why not put all routes in a single class?

A Spring WebFlux application using functional endpoints often starts with a few routes:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/books", bookHandler::list)
        .GET("/api/books/{id}", bookHandler::byId)
        .POST("/api/books", bookHandler::create)
        .GET("/api/authors", authorHandler::list)
        .GET("/api/authors/{id}", authorHandler::byId)
        .build();
~~~

This snippet assumes the handler beans are already declared. As the API grows, a single configuration file holding hundreds of `GET/POST/PUT/DELETE` routes becomes hard to read: repeating the `/api` prefix, duplicating `Accept: application/json` conditions, making route precedence hard to see, and allowing book changes to affect authors.

**Nesting** (nesting routers/predicates) and **composition** (combining multiple `RouterFunction`s) enable a cleaner layout:

~~~text
/api
├── /health
├── /books                 Book feature
│   ├── GET               list
│   ├── GET /featured     specific route
│   ├── GET /{id}         path-variable route
│   └── POST              create book
└── /authors               Author feature
    ├── GET               list
    └── GET /{id}         detail
~~~

Each feature can own its handler + router + DTOs/services, while a composition layer attaches the base path for the whole system. This approach is especially valuable in codebases with multiple bounded contexts, multiple teams, or API versions.

**Key takeaway:** routes are selected **in composition order**. Nesting only organizes matching; it does not automatically provide authentication, validation, thread isolation, or database transactions.

### Learning outcomes

After this lesson, you will be able to:
- Distinguish `RouterFunction<ServerResponse>`, `RequestPredicate`, `HandlerFunction<ServerResponse>`, and reactive `ServerResponse`.
- Use `RouterFunctions.route()`, `RouterFunctions.nest(...)`, and builder `path(...)` and `nest(...)`.
- Combine routers via `RouterFunction.and(...)`, `andRoute(...)`, and builder `add(...)`.
- Design module routers with **relative child paths**, composed at a single root.
- Understand precedence among static routes, path variables, catch-alls, `Accept`/`Content-Type`, and fallbacks.
- Know the scope of `before`/`after`/`filter`/`onError` when placed inside or outside nested groups.
- Avoid accidentally importing Servlet WebMvc.fn into reactive WebFlux.fn.
- Run a Java 17 / Spring Boot 3.3.5 example with independent Book and Author routers tested via `WebTestClient`.
- Evaluate CORS, Spring Security, error handling, tracing, and OpenAPI in multi-router systems.

## 2. You must choose WebFlux.fn, not WebMvc.fn

Both frameworks share nearly identical class names:

| Spring WebFlux.fn reactive | Spring WebMvc.fn Servlet |
| --- | --- |
| `org.springframework.web.reactive.function.server.RouterFunction` | `org.springframework.web.servlet.function.RouterFunction` |
| `org.springframework.web.reactive.function.server.RequestPredicate` | `org.springframework.web.servlet.function.RequestPredicate` |
| `org.springframework.web.reactive.function.server.ServerRequest` | `org.springframework.web.servlet.function.ServerRequest` |
| `org.springframework.web.reactive.function.server.ServerResponse` | `org.springframework.web.servlet.function.ServerResponse` |
| Handler returns `Mono<ServerResponse>` | Handler returns `ServerResponse` |
| `ServerResponse.ok().bodyValue(value)` | `ServerResponse.ok().body(value)` |
| `RequestPredicates.queryParam(...)` | `RequestPredicates.param(...)` |
| Reactor/WebFlux runtime | Servlet MVC runtime |

In **Spring WebFlux.fn**, the signature is:

~~~java
@FunctionalInterface
interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
~~~

This is a simplified form of the interface for study, not a Java file to copy into your project. The framework manages the subscription and writes the HTTP response when `Mono<ServerResponse>` completes.

Do not add `spring-boot-starter-web` to the example just because Spring contains the word "web": when both MVC and WebFlux starters are present, Spring Boot typically picks the MVC web application type by default. The WebFlux/Netty example uses only `spring-boot-starter-webflux`.

## 3. Components that appear in a router

### 3.1. `ServerRequest`

Reads path variables, query parameters, headers, and body:

~~~java
String id = request.pathVariable("id");
String q = request.queryParam("q").orElse("");
MediaType accept = request.headers().accept().stream()
        .findFirst().orElse(MediaType.ALL);
Mono<CreateBook> input = request.bodyToMono(CreateBook.class);
~~~

This code fragment requires `ServerRequest request`, `MediaType`, and `CreateBook`. `bodyToMono` uses reactive codecs and should never call `.block()` inside a handler. Path variables start as `String`; parse/validate them before looking up entities.

### 3.2. `ServerResponse`

Fluent reactive style:

~~~java
Mono<ServerResponse> ok =
        ServerResponse.ok().bodyValue(book);

Mono<ServerResponse> created =
        ServerResponse.created(URI.create("/api/books/3"))
                .bodyValue(book);

Mono<ServerResponse> missing =
        ServerResponse.notFound().build();
~~~

These three snippets assume `book` and imports are present. `ServerResponse.ok()` creates a response builder; `bodyValue(...)`/`build()` returns `Mono<ServerResponse>`. Never call `subscribe()` to manually "send a response" or `block()` to unwrap `ServerResponse` in a reactive handler.

### 3.3. `RequestPredicate`

A predicate decides whether a request matches a route:

~~~java
RequestPredicate predicate =
        RequestPredicates.GET("/api/books/{id}")
                .and(RequestPredicates.accept(
                        MediaType.APPLICATION_JSON));
~~~

Common factories: `GET`, `POST`, `PUT`, `DELETE`, `path`, `accept`, `contentType`, `headers`, `queryParam`, and `method`. Use `and`, `or`, and `negate` for complex conditions; write tests because a faulty predicate can make a handler **never get selected**, without necessarily producing the HTTP error status you expect.

### 3.4. `RouterFunction`

Abstractly, a router receives a `ServerRequest` and looks up a matching handler, returning a publisher of the handler or empty when unmatched. Example:

~~~java
RouterFunction<ServerResponse> health =
        RouterFunctions.route(
                RequestPredicates.GET("/api/health"),
                request -> ServerResponse.ok().bodyValue("OK"));
~~~

This is a standalone router ready for composition. For Spring Boot to discover and register it with WebFlux auto-configuration, you typically expose a bean of type `RouterFunction<ServerResponse>`.

## 4. Router builder DSL: defining multiple routes

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/books", handler::list)
                .GET("/api/books/{id}", handler::byId)
                .POST("/api/books", handler::create)
                .build();
~~~

`handler` is a bean with methods taking `ServerRequest` and returning `Mono<ServerResponse>`. Each builder method accepts HTTP method/path, an optional extra predicate, and a handler; finally `build()` produces the router.

Benefits:
- Centralized route declarations, easy to review.
- Handler methods live in dedicated beans without annotating every HTTP method.
- The DSL groups shared path/header/content-type conditions cleanly.
- Easy composition with routers defined in other modules.

### 4.1. Route order is part of the contract

**Wrong** if `/{id}` precedes a static route:

~~~java
RouterFunctions.route()
        .GET("/api/books/{id}", handler::byId)
        .GET("/api/books/featured", handler::featured)
        .build();
~~~

`featured` will match `{id}` on the first route, causing the handler to fail ID parsing or return the wrong resource. **Right:**

~~~java
RouterFunctions.route()
        .GET("/api/books/featured", handler::featured)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

Unlike annotated controller `@RequestMapping`, which uses a specificity comparator across mappings, functional router composition evaluates routes **in declaration/composition order**. Place static/specific routes before variables/wildcards, and fallbacks/catch-alls last.

## 5. `path(prefix, ...)` — nesting by path

When all book endpoints share `/api/books`:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", books -> books
                        .GET("/featured", handler::featured)
                        .GET("/{id}", handler::byId)
                        .GET("", handler::list)
                        .POST("", handler::create))
                .build();
~~~

`path("/api/books", builderConsumer)` is a form of **path prefix nesting**. Inside it, `/{id}` is only a child path; HTTP clients still call `GET /api/books/3`, not `/{id}`.

In real code, some Spring examples use `GET(handler::list)` without specifying a child path for the collection. If you want the route to match only the collection root rather than acting as an overly broad fallback, specify `""` and **test** `/api/books`, `/api/books/`, and `/api/books/extra/path` against your Spring path-pattern rules. Never assume trailing-slash variants behave identically.

### 5.1. Nesting multiple prefix levels

~~~java
RouterFunctions.route()
        .path("/api", api -> api
                .path("/v1", v1 -> v1
                        .path("/books", books -> books
                                .GET("", handler::list)
                                .GET("/{id}", handler::byId))))
        .build();
~~~

This example produces `GET /api/v1/books` and `GET /api/v1/books/{id}`. It illustrates prefix nesting rather than recommending three levels everywhere. Excessive nesting makes full URLs harder to see, harder to debug, and increases the risk of mis-scoping filters.

### 5.2. The `path` builder also accepts a router module Supplier

Spring WebFlux offers a very handy overload:

~~~java
RouterFunctions.route()
        .path("/api/books", bookModule::routes)
        .path("/api/authors", authorModule::routes)
        .build();
~~~

`bookModule.routes()` and `authorModule.routes()` return `RouterFunction<ServerResponse>` with relative child routes. This is the **module composition** pattern: the application root config owns public URL prefixes, while feature modules own routing logic and handlers.

## 6. `nest(predicate, ...)` — nesting by shared conditions

Not every shared condition is a URL. You can group by `Accept`, `Content-Type`, request headers, or custom predicates.

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", b -> b
                        .nest(
                                RequestPredicates.accept(
                                        MediaType.APPLICATION_JSON),
                                json -> json
                                        .GET("/featured", handler::featured)
                                        .GET("/{id}", handler::byId)
                                        .GET("", handler::list))
                        .POST("",
                                RequestPredicates.contentType(
                                        MediaType.APPLICATION_JSON),
                                handler::create))
                .build();
~~~

Meaning:
- GET routes inside `nest(accept(JSON), ...)` match only if the client accepts a JSON response.
- POST sits at the **books builder level**, outside the nested `Accept` branch, so it is not bound by that `Accept` constraint.
- POST uses `contentType(JSON)`, checking the **request body** format, not the response `Accept`.
- Static `/featured` precedes variable `/{id}`.
- `GET("")` handles the collection root; `GET("/{id}")` handles details by matching path.
- When a branch fails to match, the router continues to the next route rather than immediately returning a custom JSON error.

### 6.1. `path` vs. `nest(path(...))`

`path("/api/books", ...)` is the dedicated DSL for path prefixes. `nest(RequestPredicates.path("/api/books"), ...)` also nests a router by path predicate; `nest` accepts any other predicate as well. Use `path` for resource trees and `nest` for shared cross-cutting matching conditions when it improves readability.

### 6.2. Combining predicates

~~~java
RequestPredicate jsonVersionTwo =
        RequestPredicates.accept(MediaType.APPLICATION_JSON)
                .and(RequestPredicates.headers(
                        h -> "2".equals(
                                h.firstHeader("API-Version"))));
~~~

This only selects the HTTP route; it does not turn a client-supplied request header into a security permission or data-access entitlement. For versioned APIs, define an explicit version parser, handling of missing/unsupported values, default versions, and cache keys. Never let one overly broad route match and silently swap incompatible DTOs.

### 6.3. `queryParam` in the reactive package

~~~java
RequestPredicate summary =
        RequestPredicates.queryParam("mode", "summary");
~~~

This is **WebFlux.fn** `queryParam`, unlike `param` commonly seen in WebMvc.fn. This condition matches `?mode=summary`; if missing or different, the route does not match and can fall through to a fallback if declared.

## 7. Route order and fallbacks inside nested groups

The clearest example is two routes sharing a path but differing by query param:

~~~java
RouterFunctions.route()
        .GET("/api/books/featured",
                RequestPredicates.queryParam("mode", "summary"),
                handler::featuredSummary)
        .GET("/api/books/featured", handler::featuredHelp)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

When `?mode=summary` is present, the first route is chosen. When absent, the first misses and the second matches; `featuredHelp` returns a 400 guidance error. Because `/{id}` follows both, `featured` is never mistaken for an ID.

**Anti-pattern:** placing `GET("/{id}")` first, or placing a `GET("/**")` catch-all before specific routes. A bug can silently return status 200 with a body from the **wrong handler**; asserting only status codes is insufficient.

### 7.1. Routing fallbacks do not replace validation

If `GET /api/books/abc` matches `/{id}`, predicate matching succeeds. When the handler fails to parse `abc` as a number, that is a **validation error inside the handler**, returning 400. Never assume `{id}` only matches numeric values.

### 7.2. Never treat a non-match as 400 arbitrarily

If `Accept: text/html` fails to match a nested JSON route, the result may be 404 or 406 depending on handler mappings, media type negotiation, and the error layer. When an API contract explicitly requires 406, test and configure error handling directly rather than guessing Spring maps every predicate mismatch to the same status.

### 7.3. Context paths and trailing slashes

`GET /api/books`, `GET /api/books/`, and URL-encoded segments may behave differently depending on Spring Framework path-matching version and configuration. Test every URL allowed by your contract; never rewrite paths in a proxy via naive string concatenation expecting all nested paths to still work.

## 8. Composing routers with `and(...)` and `andRoute(...)`

Routers can be built piecemeal:

~~~java
RouterFunction<ServerResponse> first =
        RouterFunctions.route(
                RequestPredicates.GET("/api/health"),
                handler::health);

RouterFunction<ServerResponse> second =
        RouterFunctions.route(
                RequestPredicates.GET("/api/status"),
                handler::status);

RouterFunction<ServerResponse> combined = first.and(second);
~~~

When a request matches the first router, it supplies the handler; otherwise evaluation moves to the second. `and(...)` preserves modularity without forcing the builder. `andRoute(...)` is handy for appending a single predicate/handler:

~~~java
RouterFunction<ServerResponse> combined =
        first.andRoute(
                RequestPredicates.GET("/api/status"),
                handler::status);
~~~

These fragments assume `handler` is defined separately. Never assume `and` executes **both handlers** or triggers both side effects; it composes logic to **select one matching handler**.

### 8.1. Composing via Builder `add(...)`

~~~java
RouterFunction<ServerResponse> finalRouter =
        RouterFunctions.route()
                .GET("/api/health", handler::health)
                .add(bookRouter)
                .add(authorRouter)
                .build();
~~~

`bookRouter` and `authorRouter` already come from other modules. When modules own their absolute paths, `add` works well. If you want the **root config to own prefixes**, use `path("/api/books", bookModule::routes)` as in the runnable example. Never apply the prefix both inside the module and outside, which produces `/api/books/api/books`.

### 8.2. Composing with static `RouterFunctions.nest(...)`

~~~java
RouterFunction<ServerResponse> child =
        RouterFunctions.route()
                .GET("/{id}", handler::byId)
                .build();

RouterFunction<ServerResponse> nested =
        RouterFunctions.nest(
                RequestPredicates.path("/api/books"), child);
~~~

This is an alternative form of nesting, useful when the child router is already constructed. It still follows the child router's path matching and order rules, and introduces no extra network round-trips, HTTP redirects, or per-request Spring beans.

## 9. Feature-oriented routing

### 9.1. Directory layout

~~~text
com.example.catalog
├── CatalogApplication.java
├── config/
│   └── ApiRoutesConfiguration.java    # composition root
├── books/
│   ├── Book.java
│   ├── CreateBook.java
│   ├── BookStore.java
│   ├── BookHandler.java
│   └── BookRoutes.java                # child router
├── authors/
│   ├── AuthorHandler.java
│   └── AuthorRoutes.java
└── health/
    └── HealthHandler.java
~~~

**Each feature owns** its DTOs, validation, handlers, and routing, while the application root owns URL prefixes and inter-module ordering. Services/domain logic should remain decoupled from HTTP routing in larger systems; the demo keeps things simple for easy execution.

### 9.2. Comparison with one global router

| Huge global router | Feature-oriented routers |
| --- | --- |
| Easy to find every route in one file early on | Routes and handlers live next to their feature |
| Prefixes and `Accept` rules tend to repeat | Prefixes/conditions can be grouped in one place |
| Conflicts are hard to review as the API grows | Clear ownership per group |
| One change causes merge conflicts | Teams work in parallel by module |
| Risk of a catch-all shadowing every group | Composition root controls ordering |
| Filter configuration can leak across the entire API | Filters can be scoped precisely |
| Simple for tiny projects | Great for multiple bounded contexts |

Do not split a single-route API into 20 classes. Use feature modules when they **reduce coupling, duplication, and conflicts**, not merely to follow a folder layout mechanically.

### 9.3. Ownership must be consistent

Choose one of two strategies:
1. **Modules own absolute paths** (`/api/books/...`) and the root combines them with `and`/`add`.
2. **The root owns prefixes** (`/api/books`), modules declare relative child paths (`""`, `/{id}`, `/featured`), and the root calls `path(prefix, supplier)`.

The example below uses **approach 2**. Never mix both accidentally or duplicate the prefix in both the module and the composition root.

### 9.4. Bean lifecycle and registration

In Boot WebFlux, `RouterFunction<ServerResponse>` **beans** are discovered by the routing infrastructure. Creating a local `RouterFunction` inside a method without registering it or attaching it to a composed bean means those routes may not exist at runtime.

The demo exposes **a single `apiRoutes` bean** at the composition root. `BookRoutes` and `AuthorRoutes` are Spring components whose `routes()` methods return child routers, **without** registering each child router as an independent `RouterFunction` bean; that prevents relative child routes like `/{id}` from leaking outside the global prefix.

## 10. Scoped `before`, `after`, and `filter` hooks

Functional WebFlux allows filters on router functions/builders:
- `before(Function<ServerRequest,ServerRequest>)`: transforms the request before the handler.
- `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`: post-processes the response object after the handler.
- `filter(HandlerFilterFunction<ServerResponse,ServerResponse>)`: wraps handler invocation and calls `next.handle(request)`.
- `onError(...)`: maps exceptions into an appropriate `Mono<ServerResponse>` reactively.

Conceptual fragment example:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", books -> books
                        .GET("/{id}", handler::byId)
                        .before(req -> ServerRequest.from(req)
                                .header("X-Route-Scope", "books")
                                .build()))
                .after((req, response) -> response)
                .build();
~~~

`before` inside the books branch applies only to routes in that branch; `after` on the outer builder applies to all routes constructed by that builder, including nested child routes. Never use synthetic headers like `X-Route-Scope` as permissions or identity; it merely illustrates how builder scoping works.

### 10.1. `filter` and error propagation

~~~java
.filter((request, next) ->
        next.handle(request)
                .doOnError(error -> {
                    // Only log policy-compliant metadata; never log tokens/bodies.
                }))
~~~

Reactive filters can observe or transform the publisher, but **must never call `block()`**. A filter that skips `next.handle(request)` can return an alternate response early, which fits rate limits or feature gates when carefully designed, yet **never replaces** Spring Security.

### 10.2. Security and request matching

Routing predicates determine the **handler**, not whether the **user is authorized**. Spring Security WebFlux uses `SecurityWebFilterChain` and `ServerHttpSecurity`, typically enforcing security before functional handlers run. For tenant-owned books, verify ownership/tenant at the service or auth layer even when `/api/books/{id}` matches.

Custom router filters do not automatically provide CSRF/session/cookie protections. For cross-origin frontends, coordinate `CorsWebFilter` and preflight requests with reactive security; configure per WebFlux conventions rather than copying Servlet MVC `HttpSecurity`.

### 10.3. `onError` does not catch every error across the stack

An `onError` on a router handles exceptions from handlers/filters within that router's scope. Errors in gateways, proxies, pre-router security filters, or after a response has committed require separate error mechanisms. For a consistent JSON error contract, establish common error models/handlers and integration tests; never catch `Throwable` indiscriminately and return HTTP 200.

### 10.4. Filter scope by nested group

To transform only Books JSON GET endpoints, attach the filter inside **`nest(accept(JSON), ...)`**. To cover all Books routes including POST, attach it to the **`BookRoutes` builder**. To cover both Books and Authors, attach it to the **`apiRoutes` composition builder**.

Diagram:

~~~text
API builder-level filter
|
+-- /health
+-- /books    <- Books builder-level filter
|    |
|    +-- nest(accept(JSON)) <- GET JSON-only filter
|    |     +-- /featured
|    |     +-- /{id}
|    |     +-- collection list
|    +-- POST
|
+-- /authors  <- Authors builder-level filter
~~~

Always verify filter order and scope with tests (headers/trace logging) as modules are added. Avoid broad wildcard filter scopes that accidentally apply audit/payload logging to login endpoints or sensitive data.

## 11. Runnable example: Java 17 / Spring Boot 3.3.5 / WebFlux.fn

We will build an application with:
- `GET /api/health` returning plain text `OK`.
- `GET /api/books` returning a JSON list.
- `GET /api/books/featured?mode=summary` returning the featured book.
- `GET /api/books/featured` without the parameter returning 400 with a deterministic error code, **without falling into `/{id}`**.
- `GET /api/books/{id}` returning the book or 404; invalid ID format returns 400.
- `POST /api/books` accepting JSON and creating a book, returning 201 + `Location`; blank title returns 400.
- `GET /api/authors` and `GET /api/authors/{id}` declared in an independent feature router.
- A single `@Bean RouterFunction<ServerResponse> apiRoutes` composing all three modules.

The example uses an in-memory store with no authentication or database. Although the in-memory store is thread-safe within one JVM, it is **not** shared across multiple instances/pods and does not replace a production repository. HTTP tests verify behavior without relying on test execution order.

~~~text
webflux-feature-router/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/catalog/
    │   ├── CatalogApplication.java
    │   ├── config/ApiRoutesConfiguration.java
    │   ├── books/
    │   │   ├── Book.java
    │   │   ├── CreateBook.java
    │   │   ├── BookStore.java
    │   │   ├── BookHandler.java
    │   │   └── BookRoutes.java
    │   ├── authors/
    │   │   ├── AuthorHandler.java
    │   │   └── AuthorRoutes.java
    │   └── health/HealthHandler.java
    └── test/java/com/example/catalog/
        └── FeatureRouterIntegrationTest.java
~~~

### 11.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-feature-router'
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

Do not add the Spring MVC starter. Spring Boot manages compatible Spring WebFlux and Reactor versions. You will need a Gradle wrapper compatible with Java 17/Boot 3.3.5 when running `./gradlew` commands.

### 11.2. Main application

`src/main/java/com/example/catalog/CatalogApplication.java`:

~~~java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
~~~

### 11.3. Book domain types

`src/main/java/com/example/catalog/books/Book.java`:

~~~java
package com.example.catalog.books;

public record Book(long id, String title) {}
~~~

`src/main/java/com/example/catalog/books/CreateBook.java`:

~~~java
package com.example.catalog.books;

public record CreateBook(String title) {}
~~~

The record DTOs use Java 17. When deserializing JSON `{"title":"Reactive Routing"}`, Jackson supports canonical record constructors via the WebFlux starter. The example validates `title` in the handler; production should apply schema/Bean Validation, length/character rules, authorization, and request-size limits.

### 11.4. BookStore: thread-safe mock repository

`src/main/java/com/example/catalog/books/BookStore.java`:

~~~java
package com.example.catalog.books;

import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class BookStore {

    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicLong sequence = new AtomicLong(2);

    public BookStore() {
        books.put(1L, new Book(1L, "Spring WebFlux"));
        books.put(2L, new Book(2L, "Reactor Patterns"));
    }

    public Flux<Book> all() {
        return Flux.defer(() -> Flux.fromIterable(
                books.values().stream()
                        .sorted(Comparator.comparingLong(Book::id))
                        .toList()));
    }

    public Mono<Book> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)));
    }

    public Mono<Book> create(String title) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            Book book = new Book(id, title);
            books.put(id, book);
            return book;
        });
    }
}
~~~

**Note on reactiveness:** `ConcurrentHashMap` uses local memory and executes very fast; `Mono.defer/fromSupplier` defers reads/writes until subscription, but **does not automatically make blocking database calls non-blocking**. Never replace `books.get(id)` with JDBC `jdbcTemplate.queryForObject` inside a lambda running on the event loop. For legacy JDBC, isolate with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`; for end-to-end reactive DBs, use R2DBC with the proper driver/transaction stack.

### 11.5. BookHandler

`src/main/java/com/example/catalog/books/BookHandler.java`:

~~~java
package com.example.catalog.books;

import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class BookHandler {

    public record ApiError(String code, String message) {}

    private final BookStore store;

    public BookHandler(BookStore store) {
        this.store = store;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all(), Book.class);
    }

    public Mono<ServerResponse> featured(ServerRequest request) {
        return store.find(1L)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> featuredHelp(ServerRequest request) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(
                        "FEATURED_MODE_REQUIRED",
                        "Use mode=summary"));
    }

    public Mono<ServerResponse> byId(ServerRequest request) {
        String raw = request.pathVariable("id");
        long id;

        try {
            id = Long.parseLong(raw);
        } catch (NumberFormatException ex) {
            return invalidId();
        }

        if (id <= 0) {
            return invalidId();
        }

        return store.find(id)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    private Mono<ServerResponse> invalidId() {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(
                        "INVALID_BOOK_ID", "id must be a positive integer"));
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateBook.class)
                .flatMap(input -> {
                    if (input.title() == null
                            || input.title().isBlank()
                            || input.title().length() > 100) {
                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError(
                                        "INVALID_BOOK_TITLE",
                                        "title is required and max 100 chars"));
                    }

                    return store.create(input.title().trim())
                            .flatMap(book ->
                                    ServerResponse.created(
                                            URI.create("/api/books/" + book.id()))
                                            .contentType(MediaType.APPLICATION_JSON)
                                            .bodyValue(book));
                })
                .switchIfEmpty(ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new ApiError(
                                "MISSING_BODY", "JSON body is required")));
    }
}
~~~

Key points:
- All handler methods return `Mono<ServerResponse>` (or a `Mono` from a body publisher), never synchronous Servlet `ServerResponse`.
- `ServerResponse.ok().body(store.all(), Book.class)` lets the framework stream/encode `Flux<Book>` via the JSON codec; this produces an array response for normal Jackson/WebFlux use cases.
- In `create`, **subscription only happens when the HTTP framework processes the request**; `request.bodyToMono(...).block()` is never called.
- Bad IDs map to 400, missing books map to 404, and missing `mode=summary` maps to 400 with a stable error code.
- The demo performs no authentication or tenant authorization. Before returning a real `Book`, a production service must verify the principal and resource permissions.

### 11.6. BookRoutes: child paths without `/api/books`

`src/main/java/com/example/catalog/books/BookRoutes.java`:

~~~java
package com.example.catalog.books;

import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;
import static org.springframework.web.reactive.function.server.RequestPredicates.queryParam;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Component
public class BookRoutes {

    private final BookHandler handler;

    public BookRoutes(BookHandler handler) {
        this.handler = handler;
    }

    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route()
                .nest(accept(MediaType.APPLICATION_JSON), json -> json
                        .GET("/featured",
                                queryParam("mode", "summary"),
                                handler::featured)
                        .GET("/featured", handler::featuredHelp)
                        .GET("/{id}", handler::byId)
                        .GET("", handler::list))
                .POST("", contentType(MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
    }
}
~~~

This is a **child router**, so `/api/books` does not appear in its paths. It is mounted at the composition root via `path("/books", bookRoutes::routes)` inside the `path("/api", ...)` branch.

**Intentional ordering:**
1. Featured with query param `mode=summary` is the most specific route.
2. Featured fallback without mode follows next.
3. Variable route `/{id}` comes after static `/featured`.
4. Collection route `GET("")` comes after the other GETs.
5. POST has `contentType(JSON)` and sits **outside the `nest(Accept(JSON))` branch** because `Accept` and `Content-Type` play different roles.

If you reorder `/{id}` to the top, `GET /api/books/featured` enters `byId`, yielding a different API error code. The `WebTestClient` suite below asserts the exact error message to catch this regression.

### 11.7. AuthorHandler: independent feature

`src/main/java/com/example/catalog/authors/AuthorHandler.java`:

~~~java
package com.example.catalog.authors;

import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class AuthorHandler {

    public record Author(long id, String name) {}

    private static final List<Author> AUTHORS =
            List.of(new Author(1L, "An"),
                    new Author(2L, "Binh"));

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(AUTHORS);
    }

    public Mono<ServerResponse> byId(ServerRequest request) {
        String id = request.pathVariable("id");

        return AUTHORS.stream()
                .filter(author ->
                        Long.toString(author.id()).equals(id))
                .findFirst()
                .map(author -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(author))
                .orElseGet(() -> ServerResponse.notFound().build());
    }
}
~~~

Here `byId` compares the path variable as a string; malformed input returns 404, unlike the Book handler's 400 policy. This illustrates **why per-feature policies must be unified when publishing a shared API**. For consistent error contracts, use a common validation/error model and tests. The author list is an in-memory fixture, not a DB.

### 11.8. AuthorRoutes: simple child router

`src/main/java/com/example/catalog/authors/AuthorRoutes.java`:

~~~java
package com.example.catalog.authors;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Component
public class AuthorRoutes {

    private final AuthorHandler handler;

    public AuthorRoutes(AuthorHandler handler) {
        this.handler = handler;
    }

    public RouterFunction<ServerResponse> routes() {
        return RouterFunctions.route()
                .GET("/{id}", handler::byId)
                .GET("", handler::list)
                .build();
    }
}
~~~

No `RouterFunction` bean is declared in this module: only `@Component AuthorRoutes` with a method returning a router when invoked by the root composer.

### 11.9. HealthHandler: separating operational concerns

`src/main/java/com/example/catalog/health/HealthHandler.java`:

~~~java
package com.example.catalog.health;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class HealthHandler {

    public Mono<ServerResponse> health(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("OK");
    }
}
~~~

The demo `/api/health` makes no network or JDBC calls. For production liveness/readiness, consider Spring Boot Actuator `/actuator/health`, Kubernetes probes, and appropriate security policies; do not mistake an `"OK"` response for proof that all downstream dependencies are healthy.

### 11.10. Composition root — the layer deciding public URLs

`src/main/java/com/example/catalog/config/ApiRoutesConfiguration.java`:

~~~java
package com.example.catalog.config;

import com.example.catalog.authors.AuthorRoutes;
import com.example.catalog.books.BookRoutes;
import com.example.catalog.health.HealthHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class ApiRoutesConfiguration {

    @Bean
    RouterFunction<ServerResponse> apiRoutes(
            BookRoutes books, AuthorRoutes authors,
            HealthHandler health) {

        return RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/health", health::health)
                        .path("/books", books::routes)
                        .path("/authors", authors::routes))
                .build();
    }
}
~~~

**Why this is the composition root:**
- Only a single `@Bean RouterFunction<ServerResponse>` is exposed to the WebFlux routing infrastructure.
- The `/api` prefix wraps the entire API; `/books` and `/authors` are defined here, not inside child modules.
- `BookRoutes` and `AuthorRoutes` remain Spring-managed components for dependency injection, while their `routes()` methods are not auto-registered as top-level router beans.
- `/api/health` is a standalone route unaffected by Books' `accept(JSON)` predicate.
- The router tree is easy to review; composition order here matters if child routers contain overlapping or catch-all paths.

To add `/api/v2/books`, compose a `BookRoutesV2` under a new prefix while keeping v1. Never reuse an incompatible DTO module thinking adding `/v2` alone suffices to version an API.

## 12. WebTestClient verifying nesting, order, and module boundaries

`WebTestClient` is tailored for reactive Spring WebFlux. We run an embedded server on a random port to test real HTTP routing, bodies, and statuses. Never use Servlet `MockMvc` as though they shared the same programming model.

`src/test/java/com/example/catalog/FeatureRouterIntegrationTest.java`:

~~~java
package com.example.catalog;

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
class FeatureRouterIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void healthIsIndependentFromBooksJsonCondition() {
        client.get().uri("/api/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("OK");
    }

    @Test
    void bookCollectionIsUnderNestedPrefix() {
        client.get().uri("/api/books")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].id").isEqualTo(1)
                .jsonPath("$[1].id").isEqualTo(2);
    }

    @Test
    void bookDetailMatchesVariableRoute() {
        client.get().uri("/api/books/2")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactor Patterns");
    }

    @Test
    void featuredQueryPredicateBeatsFallback() {
        client.get().uri("/api/books/featured?mode=summary")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1);
    }

    @Test
    void featuredWithoutModeDoesNotHitIdHandler() {
        client.get().uri("/api/books/featured")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                    .isEqualTo("FEATURED_MODE_REQUIRED")
                .jsonPath("$.message")
                    .isEqualTo("Use mode=summary");
    }

    @Test
    void invalidIdHasExplicitBusinessError() {
        client.get().uri("/api/books/abc")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_BOOK_ID");
    }

    @Test
    void missingBookReturnsNotFound() {
        client.get().uri("/api/books/9999")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void postBookCreatesResourceWithLocation() {
        client.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "Reactive Routing"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueMatches(
                        HttpHeaders.LOCATION, "/api/books/[0-9]+")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Reactive Routing");
    }

    @Test
    void blankBookTitleReturns400() {
        client.post().uri("/api/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("title", "   "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_BOOK_TITLE");
    }

    @Test
    void authorListIsIndependentModule() {
        client.get().uri("/api/authors")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$[0].name").isEqualTo("An")
                .jsonPath("$[1].name").isEqualTo("Binh");
    }

    @Test
    void authorDetailIsNestedUnderAuthors() {
        client.get().uri("/api/authors/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("An");
    }
}
~~~

### 12.1. Why assert JSON rather than status alone?

If `GET("/{id}")` were moved before `GET("/featured")`, the `/featured` URL would enter the ID handler and still return **400**. If a test only asserted `status().isBadRequest()`, it would pass despite the wrong route matching. Hence the test checks both `code=FEATURED_MODE_REQUIRED` and `message`; this serves as a **contract test for route ordering**.

### 12.2. Why tests do not depend on execution order

`BookStore` seeds IDs 1 and 2, neither of which is deleted. The POST test creates additional books with `AtomicLong` without asserting a fixed ID 3. Tests for initial IDs inspect the first two elements sorted ascending, so they remain stable even if POST runs first. If you add delete/mutate fixtures or multiple test classes, reset the repository per test or use isolated contexts.

### 12.3. Trying negative Accept in integration tests

A helpful follow-up exercise is sending `Accept: text/html` to `GET /api/books/1` to verify that the **nested JSON branch does not match**. The final HTTP status can vary depending on handler mappings and global error handling, so do not hardcode an unverified status. Start by asserting the response is **not** 200 with JSON `Book`, and once a clear policy exists, assert the exact status/error contract.

### 12.4. Running tests

In a project with a Java 17-compatible Gradle wrapper:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

This guide lists all class/code files, without bundling the Gradle wrapper scripts. If no wrapper is present, generate one from a compatible Gradle installation; `build.gradle` does not generate `gradlew` automatically. Because there are no DB migrations or external APIs, HTTP outputs are deterministic aside from newly created process-state IDs.

## 13. Running with curl

### 13.1. Health

~~~bash
curl -i 'http://localhost:8080/api/health'
~~~

Expected HTTP 200, `Content-Type: text/plain`, body:

~~~text
OK
~~~

### 13.2. Books collection and details

~~~bash
curl -i 'http://localhost:8080/api/books' \
  -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/books/2' \
  -H 'Accept: application/json'
~~~

Initial list:

~~~json
[
  {"id":1,"title":"Spring WebFlux"},
  {"id":2,"title":"Reactor Patterns"}
]
~~~

Detail for ID 2:

~~~json
{"id":2,"title":"Reactor Patterns"}
~~~

Actual JSON responses may be single-line; this is a readable layout. The handler returns 404 if the ID does not exist, rather than forcing every query to return 200.

### 13.3. Featured with valid query and fallback

~~~bash
curl -i 'http://localhost:8080/api/books/featured?mode=summary' \
  -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/books/featured' \
  -H 'Accept: application/json'
~~~

With `mode=summary`, JSON response for book ID 1. Without `mode`, 400 response:

~~~json
{"code":"FEATURED_MODE_REQUIRED","message":"Use mode=summary"}
~~~

This proves the static routes matched before the `/{id}` variable route.

### 13.4. Creating a book

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Functional WebFlux"}'
~~~

Expected HTTP 201, `Location: /api/books/3` on a fresh JVM with no prior POSTs, with JSON:

~~~json
{"id":3,"title":"Functional WebFlux"}
~~~

The ID changes if earlier POSTs ran; never hardcode fixed IDs in client business logic. The demo endpoint uses an in-memory store with no auth; production needs proper DB, validation, authorization, and idempotency.

### 13.5. Author routes

~~~bash
curl -i 'http://localhost:8080/api/authors'
curl -i 'http://localhost:8080/api/authors/1'
~~~

Initial authors list:

~~~json
[
  {"id":1,"name":"An"},
  {"id":2,"name":"Binh"}
]
~~~

Detail:

~~~json
{"id":1,"name":"An"}
~~~

This demonstrates that **AuthorRoutes** and **BookRoutes** can be composed under the same `/api` without sharing a single handler class.

## 14. Composing across multiple RouterFunction beans: dos and don'ts

In Spring Boot WebFlux you can declare multiple `RouterFunction<ServerResponse>` beans, and the framework collects and combines them via its routing infrastructure. However, if routers have overlapping paths, relying on implicit registration order can cause your API to shift during refactoring.

**Practical recommendation:** in multi-module systems sharing a path prefix, use a single composition root bean as in the example; ordering stays explicit in code and covered by integration tests. If you intentionally define multiple top-level `RouterFunction` beans, document `@Order`/ordering semantics for your framework version, add conflict detection/tests, and keep path ownership clear.

A common mistake: a child module declares a bean with `GET("/{id}")` while the root also mounts it under `/api/books`; the relative `/{id}` route can then be registered outside the prefix because the bean exists independently. If a module only provides child routes for root composition, **do not annotate the child `RouterFunction` as a standalone `@Bean`**.

### 14.1. Versioning via the root composer

Two API versions can live in separate modules:

~~~java
RouterFunctions.route()
        .path("/api/v1/books", v1BookRoutes::routes)
        .path("/api/v2/books", v2BookRoutes::routes)
        .build();
~~~

This fragment requires two components. Some projects use header/query/media-type versioning; Spring Framework 7 introduces newer version-specific routing infrastructure. **Do not use `RequestPredicates.version(...)` from Spring 7 docs in Spring Boot 3.3.x** unless you upgrade to a compatible platform.

### 14.2. Sharing business logic when appropriate

v1 and v2 routers can share a domain service while using separate DTO adapters. Never expose persistence entities directly across all API versions; an entity refactor can unintentionally break v1. If business semantics truly diverge, establish clear policies rather than merely renaming the router.

## 15. CORS, authentication, and errors across multiple feature routers

### 15.1. CORS for WebFlux functional endpoints

Spring WebFlux.fn typically configures global/functional CORS via `CorsWebFilter`. CORS policies are not created automatically by `path("/api", ...)` or `nest(accept(JSON), ...)`. Cross-origin browser JSON POSTs trigger preflight requests; allow the appropriate Origins/Methods/Headers and coordinate with reactive Spring Security.

**Never use `Access-Control-Allow-Origin: *` with credentialed browser requests.** With cookie authentication, evaluate `SameSite`, `Secure`, CSRF protection, and third-party cookie behavior. CORS never proves a user is authorized.

### 15.2. Spring Security filter chain

Functional WebFlux routes still flow through reactive `SecurityWebFilterChain` when configured. Policies can be structured as:
- `/api/health` public per threat model.
- `/api/books/**` authenticated, POST requiring write permissions.
- `/api/authors/**` independent read policy.
- Everything outside the allowlist denied by default.

This is only a design guideline; the demo ships without security configuration so endpoints are open. Never run production systems handling private data like the demo without auth.

### 15.3. Errors and `ProblemDetail`

An unmatched router is a routing miss; a handler throwing an exception is a runtime failure; security 401/403 responses occur before the handler. If your product uses a JSON schema such as RFC 9457 `ProblemDetail` with stable `code` fields, design unified error handling per layer and test 400/401/403/404/405/406/415/500. Avoid catching `Throwable` and returning 200 just to "standardize" the body.

### 15.4. Filters and auditing

Router-level filters can attach `X-Trace-Id`, measure latency, and audit modules. However:
- Never log bodies, `Authorization`, `Cookie`, or tokens.
- Never use raw unbounded headers as metric labels.
- Never rely on `ThreadLocal` to hold security context across Reactor pipelines that may switch schedulers.
- For tracing, use Reactor `Context` and compatible integrations (Micrometer/Spring Security).
- Errors after a response has committed cannot alter already-sent status/headers like pre-commit errors can.

## 16. Functional routing and annotated controllers can coexist

Spring WebFlux supports both annotated controllers and functional routes. Avoid:
- Registering the same `GET /api/books/{id}` in both models.
- A global catch-all `RouterFunction` accidentally shadowing static resources and annotated endpoints.
- Applying an error formatter only to annotated controllers while forgetting functional handlers.
- Expecting `@Valid @RequestBody` behavior when a functional handler only calls `bodyToMono` without invoking a validator.
- Relying on Spring WebFlux mapping order without tests.

In large codebases, agree on **ownership per URL/method** and rules for migrating APIs. Do not mass-refactor everything to `RouterFunction` just for shorter syntax; if annotations work well and fit your OpenAPI tooling, keep them.

## 17. Performance and reactive streams are not altered by nesting

Nesting and composing routers are primarily about **matching and declaration**, not speeding up network I/O. Common misconceptions:

| Misconception | Reality |
| --- | --- |
| "`RouterFunction` makes JDBC non-blocking" | No; JDBC can block the event loop and must be offloaded or replaced with a reactive driver |
| "Nesting creates dedicated thread pools" | No; it only organizes match predicates |
| "Each feature's `RouterFunction` gets isolated resource quotas" | No; they still share Netty loops, schedulers, and DB pools |
| "`and()` runs handlers in parallel" | No; it selects the first matching handler |
| "Because `Flux` has backpressure, the DB cannot overload" | You still need concurrency/connection-pool budgets, bounded buffers, and admission control |
| "`before`/`after` filters automatically secure all routes" | No; `SecurityWebFilterChain`/domain auth are separate |
| "One request executes both module A and module B" | Usually only one matched route handler executes |
| "Router order doesn't matter because Spring picks the most specific pattern" | Declaration order in functional composition is critical |

If a feature calls a blocking service from a handler, use Reactor `Mono.fromCallable(...).subscribeOn(boundedElastic)` or a dedicated worker pool sized for that dependency. With non-blocking `WebClient`/R2DBC, return publishers and avoid `block()`. Measure p95/p99, Netty event-loop starvation, connection pools, memory pressure, and error rates rather than assuming router layout improves throughput.

## 18. Troubleshooting: wrong routes and wrong module ownership

| Symptom | Cause | Remediation |
| --- | --- | --- |
| `RouterFunction` is not recognized | Imported WebMvc.fn package or forgot `@Bean` | Use reactive package and composition bean |
| `GET /api/books` returns 404 | Wrong nested prefix or child path | Trace full URL at every level |
| `/api/books/featured` enters ID handler | `/{id}` placed before static route | Put static first and assert error code |
| `GET /api/books` returns Authors data | Broad/catch-all router composed wrong | Explicit ownership and prefixes |
| `path("/api/books", ...)` doubles prefix | Module also declared `/api/books` | Use relative child paths in modules |
| `GET /api/books/1` misses on `Accept: text/html` | `nest(accept(JSON))` applied to GET | Check client `Accept` and 406 policy |
| POST JSON body gets 415 | Wrong `Content-Type` or unsupported codec | Check `contentType(JSON)` and codecs |
| Query `mode=summary` is ignored | Imported `param` or missing query | Use reactive `queryParam` |
| `@Bean` child routes match outside prefix | Registered child router standalone outside composition | Keep only root bean for relative routers |
| GET filter affects POST by mistake | Filter placed on parent builder instead of nested GET group | Move into the proper `nest` scope |
| Security policy only protects annotations | Request matchers miss functional URLs | Test `SecurityWebFilterChain` with `WebTestClient` |
| CORS preflight gets 401 | Auth runs on `OPTIONS` before CORS | Configure `CorsWebFilter`/Security properly |
| Errors differ across modules | Each handler invents its own status/body | Shared error contract and tests |
| `GET byId` with `"abc"` returns unpredictable status | Path variable not validated | Parse/validate and return typed 400 |
| Test IDs shift depending on order | Shared mutable in-memory store | Isolate tests, avoid asserting absolute next ID |
| Two `RouterFunction` beans conflict | Undefined registration order | Single composition root or tested `@Order` |
| Spring Boot starts MVC | Mixed `starter-web` with WebFlux starter | Choose the right platform |
| WebFlux handler calls `block()` | Confused reactive types with non-blocking execution | Return publishers, offload legacy blocking |
| HTTP 200 but wrong payload | Earlier route matched wrong handler | Assert body, schema, error code, and headers |
| OpenAPI misses functional routes | Tool scans only controller annotations | Explicit OpenAPI registration/annotations as needed |

### Debugging workflow

1. Verify Gradle dependencies and imports belong to **WebFlux.fn**.
2. Check that only the expected `RouterFunction` beans are registered.
3. Sketch the route tree from the composition root down through relative child paths.
4. Audit route order within each module: static → constrained → variable → fallback.
5. Inspect method, full path, query, `Accept`, `Content-Type`, and headers — without logging secrets.
6. Check nested predicates and filter scopes layer by layer.
7. Distinguish route non-match, handler validation errors, and security filter errors.
8. Verify `bodyToMono`/codecs and return type `Mono<ServerResponse>` with no blocking.
9. Run positive and negative `WebTestClient` tests asserting exact handlers and schemas.
10. If a gateway/CDN/rewrite layer sits in front, test real HTTP end-to-end after embedded integration tests.

## 19. Module router design checklist

- [ ] Either root owns public prefixes or modules own full paths — pick one consistently.
- [ ] Module handlers/services/repositories do not depend on another feature's routes.
- [ ] Expose a single clear composition `RouterFunction<ServerResponse>` bean when child paths are relative.
- [ ] All static/constrained routes precede variable/wildcard/catch-all routes.
- [ ] Nested path prefixes are accurate without duplicating `/api/books`.
- [ ] Nested `Accept`/`Content-Type` predicates apply only to the intended group.
- [ ] Reactive WebFlux `queryParam` from the right package; never Servlet `param`.
- [ ] Handlers return `Mono<ServerResponse>`, without manual `subscribe()` or `block()`.
- [ ] DTOs, inputs, paths, and headers are validated; JSON codecs read the body once.
- [ ] HTTP statuses 400/404/201 and `Location`/error codes have clear contracts.
- [ ] Router filters are narrowly scoped and do not replace auth/CSRF/CORS.
- [ ] Error mapping never leaks exception internals or user data.
- [ ] No unbounded queues or schedulers for blocking services.
- [ ] `WebTestClient` asserts route correctness and **body**, not just status codes.
- [ ] Tests cover `featured` vs. ID and collection vs. detail/fallback.
- [ ] Auth and tenant ownership are enforced on nested routes as well.
- [ ] API versioning does not break existing DTO contracts or business semantics.
- [ ] Docs/OpenAPI cover functional routes and client examples.
- [ ] CI runs tests whenever modules are added/removed to catch route conflicts.
- [ ] Production observability uses trace IDs and bounded metric labels.

### Self-check questions

**1.** What does `path("/api/books", builder)` do?

**Answer:** It creates a router group sharing a common path prefix; child paths inside are matched under `/api/books` without repeating the prefix on every child route.

**2.** Does `nest(accept(APPLICATION_JSON), ...)` force a POST on the same builder to require JSON?

**Answer:** Only routes inside the `nest` block inherit that `Accept` condition. A POST outside the `nest` branch does not receive that predicate merely for sharing the parent path.

**3.** When should you use `RouterFunction.and(...)` vs. Builder `add(...)`?

**Answer:** Both compose routers in order. `and` conveniently chains two `RouterFunction`s; `add` adds a prebuilt router into the DSL builder. `path(..., supplier)` is best when the composition root owns the URL prefix for child routers.

**4.** What happens if `GET("/{id}")` precedes `GET("/featured")`?

**Answer:** Requests to `/featured` match the `{id}` variable first, invoking the wrong handler. Tests asserting body/error codes catch that regression.

**5.** Why shouldn't a child router be a `@Bean` itself when the root also applies a path prefix?

**Answer:** A child `RouterFunction` bean would be registered independently at its relative URLs. Having a single root `RouterFunction` bean and child modules as regular components prevents routes from leaking outside the prefix.

**6.** What does a WebFlux.fn handler return?

**Answer:** Typically `Mono<ServerResponse>`; Servlet WebMvc.fn returns synchronous `ServerResponse`. Choose matching imports and response builders.

**7.** Is a router header predicate authorization?

**Answer:** No. It only decides route matching; auth and tenant access checks belong in `SecurityWebFilterChain` and the domain layer.

**8.** How does `queryParam("mode","summary")` differ from `ServerRequest.queryParam("mode")`?

**Answer:** `RequestPredicates.queryParam` is a factory used to **select a route**; the method on `ServerRequest` is used to **read** the query parameter after a handler is selected.

**9.** Does composing routers automatically introduce concurrency?

**Answer:** No. It organizes matching/dispatching; it does not spawn worker threads or turn blocking I/O into non-blocking I/O.

**10.** Why is asserting only HTTP 400 on `/featured` insufficient?

**Answer:** The wrong ID handler can also return 400. Asserting the error code and message proves the router chose the intended fallback.

## 20. Official documentation

- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `RouterFunction`, nested path/`Accept`, composition, filters, handlers.
- [Spring Framework 6.1 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.1/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.Builder.html): `path`, `nest`, `add`, `GET`/`POST`, filter/`onError`.
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.html): `route`, `nest`, `toHttpHandler`.
- [Spring Framework 6.1 — RequestPredicates Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html): `GET`, `POST`, `accept`, `contentType`, `queryParam`.
- [Spring Framework 6.1 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): request path/query/headers/body decoding.
- [Spring Framework 6.1 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): reactive body/status/headers.
- [Spring Framework — WebFlux DispatcherHandler](https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html): handler mappings/adapters/results.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive HTTP-level integration testing.
- [Spring Boot 3.3 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): Boot WebFlux configuration and server.
- [Spring Security — Reactive Security](https://docs.spring.io/spring-security/reference/reactive/index.html): reactive `SecurityWebFilterChain`.
- [Spring Framework — WebFlux CORS](https://docs.spring.io/spring-framework/reference/web/webflux-cors.html): CORS policies for reactive endpoints.

**Remember:** in WebFlux.fn, `path` groups routes by prefix, `nest` groups routes by `RequestPredicate`, and `and`/`andRoute`/`add` compose router modules. **Matching order and prefix ownership are the core design concerns.** A clear composition root, relative child routes, intentional filter scopes, and handler-accurate `WebTestClient` assertions keep multi-feature APIs both extensible and maintainable.
