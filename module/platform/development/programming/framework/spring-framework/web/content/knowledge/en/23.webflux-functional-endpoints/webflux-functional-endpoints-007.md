# Spring WebFlux — Integrating RouterFunction Beans with DispatcherHandler

## 1. Problem and goals

Spring WebFlux offers two styles for declaring HTTP endpoints:

- **Annotated controller:** `@RestController`, `@GetMapping`, `@RequestBody`.
- **Functional endpoint (WebFlux.fn):** `RouterFunction<ServerResponse>` selects the route; `HandlerFunction<ServerResponse>` handles `ServerRequest` and produces `Mono<ServerResponse>`.

Both styles **can run under the same `DispatcherHandler` and HTTP server**. In a Spring Boot WebFlux application, declaring `RouterFunction<?>` as a Spring bean is usually enough; the WebFlux infrastructure beans automatically discover and compose the routers.

This lesson explains:

1. `DispatcherHandler` and its three delegate types: `HandlerMapping`, `HandlerAdapter`, and `HandlerResultHandler`.
2. The three functional endpoint components: `RouterFunctionMapping`, `HandlerFunctionAdapter`, and `ServerResponseResultHandler`.
3. How Boot picks up `RouterFunction` beans, and why you do not need to instantiate `DispatcherHandler` or call `RouterFunctions.toHttpHandler` manually.
4. Multiple router beans, composition, and **first-match routing order**.
5. Coexistence of functional and annotated endpoints, and the difference between router order and handler-mapping order.
6. Organizing handlers/services, dependency injection, filters, security/CORS, and error handling.
7. Common pitfalls involving `@EnableWebFlux`, Servlet WebMvc.fn, route prefixes, and wildcard routes.
8. A Java 17 / Spring Boot 3.5.0 / Spring Framework 6.2 Maven example, `WebTestClient` tests, and practice exercises.

**Context:** Functional WebFlux. Do not confuse the reactive package `org.springframework.web.reactive.function.server` with Servlet `org.springframework.web.servlet.function`.

## 2. RouterFunction and HandlerFunction

### 2.1. HandlerFunction

A functional handler accepts a `ServerRequest` and returns a `Mono<ServerResponse>`:

~~~java
Mono<ServerResponse> hello(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .bodyValue("Hello WebFlux");
}
~~~

This is a code fragment, not a standalone runnable Java file. `ServerRequest` exposes APIs such as `pathVariable("id")`, `queryParam("q")`, `headers()`, `bodyToMono(BookInput.class)`, `bodyToFlux(...)`, `principal()`, and other metadata.

`ServerResponse` is an immutable descriptor of status, headers, cookies, and how the body is written; the framework performs the encoding/writing rather than the `HandlerFunction` managing sockets directly.

### 2.2. RouterFunction

In essence, `RouterFunction<T>` inspects a `ServerRequest` and returns `Mono<HandlerFunction<T>>` on match or `Mono.empty()` when unmatched.

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok().bodyValue("Hello"))
                .build();
~~~

To let Spring Boot discover this router, expose it from a `@Bean`:

~~~java
@Configuration
class RouterConfiguration {
    @Bean
    RouterFunction<ServerResponse> helloRouter() {
        return RouterFunctions.route()
                .GET("/hello", req ->
                        ServerResponse.ok().bodyValue("Hello"))
                .build();
    }
}
~~~

When `RouterConfiguration` is covered by component scanning, Boot registers the bean in the `ApplicationContext`; no extra adapter or mapping boilerplate is needed.

### 2.3. Functional vs. annotated

Annotated:

~~~java
@RestController
class HealthController {
    @GetMapping("/status")
    Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "ok"));
    }
}
~~~

Functional:

~~~java
@Bean
RouterFunction<ServerResponse> statusRouter() {
    return RouterFunctions.route()
            .GET("/status", req ->
                    ServerResponse.ok()
                            .bodyValue(Map.of("status", "ok")))
            .build();
}
~~~

These are two **alternative** approaches; avoid declaring both for the same `GET /status` unless you have a tested precedence plan. A functional handler explicitly reads `ServerRequest` and builds `ServerResponse`; an annotated controller relies on the framework's argument resolvers and return-value handlers.

## 3. How does DispatcherHandler process a request?

### 3.1. General flow

~~~text
Browser or HTTP client
        |
        v
Reactive HTTP server (typically Reactor Netty)
        |
        v
WebHttpHandlerBuilder-created HttpHandler
        |
        v
WebFilter/WebExceptionHandler chain
        |
        v
DispatcherHandler
        |
        +--> HandlerMapping: find handler
        |
        +--> HandlerAdapter: invoke handler
        |
        +--> HandlerResultHandler: write response
        |
        v
HTTP status + headers + body
~~~

`DispatcherHandler` is WebFlux's front controller, **not `DispatcherServlet`**. It retrieves delegate beans from the `ApplicationContext` and has no direct knowledge of individual `RouterFunction`s or annotations.

| Component | Purpose |
| --- | --- |
| `HandlerMapping` | Selects a matching handler for the request |
| `HandlerAdapter` | Invokes the selected handler |
| `HandlerResult` | Wraps the handler's return value and context |
| `HandlerResultHandler` | Chooses how to render the response and completes HTTP writing |

According to the Spring Framework 6.2 documentation, `DispatcherHandler` queries `HandlerMapping` beans in order and **uses the first match**.

### 3.2. The WebFlux.fn infrastructure trio

| Class | Role |
| --- | --- |
| `RouterFunctionMapping` | Discovers, orders, and composes `RouterFunction` beans and routes requests |
| `HandlerFunctionAdapter` | Enables `DispatcherHandler` to invoke a `HandlerFunction` |
| `ServerResponseResultHandler` | Writes `Mono<ServerResponse>` via `ServerResponse.writeTo(...)` |

Flow:

~~~text
GET /api/fn/books/42
    |
    v
DispatcherHandler
    |
    v
RouterFunctionMapping
    |
    v
RouterFunction.route(request)
    |
    v
HandlerFunction for GET /api/fn/books/{id}
    |
    v
HandlerFunctionAdapter
    |
    v
Mono<ServerResponse>
    |
    v
ServerResponseResultHandler -> codecs -> HTTP response
~~~

If the composite router does not match, `RouterFunctionMapping` returns no handler so `DispatcherHandler` can try other mappings.

### 3.3. Other annotated components

Annotated controllers use `RequestMappingHandlerMapping` and `RequestMappingHandlerAdapter`; `@ResponseBody`/`@RestController` results are handled by `ResponseBodyResultHandler`. `ServerResponseResultHandler` handles functional `ServerResponse`s. All work together inside the same `DispatcherHandler` thanks to the shared delegate contracts.

**Never** call `ServerResponse.writeTo(...)` directly inside a normal `HandlerFunction`; let the framework manage codecs, write lifecycles, and error handling.

## 4. What does Spring Boot auto-configure?

Use `spring-boot-starter-webflux` so Spring Boot 3.5 configures the reactive HTTP runtime, WebFlux `DispatcherHandler`, handler mappings/adapters/result handlers, codecs, and Boot utilities.

**You do not need to**:

- Register `RouterFunctionMapping` manually.
- Register `HandlerFunctionAdapter`/`ServerResponseResultHandler` manually.
- Create an extra `DispatcherHandler` manually.
- Convert router beans into `HttpHandler` manually.
- Add `@EnableWebFlux` just to run functional routing.

With Boot, if you need to customize CORS/formatters/codecs, use `@Configuration implements WebFluxConfigurer` **without `@EnableWebFlux`**, preserving Boot-specific WebFlux auto-configuration conveniences.

### 4.1. When is `@EnableWebFlux` used?

In non-Boot Spring Framework Java configuration, `@EnableWebFlux` imports the WebFlux infrastructure beans. Using it inside Boot opts into deeper manual control over WebFlux configuration; some Boot auto-configurations back off, and defaults for static resources, codecs, and errors must be managed manually. Do not use it for this lesson.

### 4.2. Beware of `starter-web`

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Boot typically defaults to MVC. In that case, a WebFlux `RouterFunction<ServerResponse>` will not run inside a WebFlux `DispatcherHandler` as expected. For a reactive demo, include only the WebFlux starter.

### 4.3. Wrong imports are a common mistake

WebFlux.fn:

~~~java
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;
~~~

WebMvc.fn:

~~~java
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;
~~~

The signatures and lifecycles differ; always double-check IDE auto-imports.

## 5. Multiple RouterFunction beans

### 5.1. RouterFunctionMapping discovers and composes them

Spring documentation notes that `RouterFunctionMapping` collects one or more `RouterFunction<?>` beans, **sorts** them, and combines them using `RouterFunction.andOther`.

Example:

~~~text
catalogRoutes  -> GET /api/catalog
orderRoutes    -> GET /api/orders
systemRoutes   -> GET /internal/ping
~~~

One WebFlux `DispatcherHandler` serves all of them. When paths are disjoint, bean order has little effect; when routes overlap, order determines the outcome.

### 5.2. Specific before variable

Wrong:

~~~java
return RouterFunctions.route()
        .GET("/api/books/{id}", handler::byId)
        .GET("/api/books/latest", handler::latest)
        .build();
~~~

`GET /api/books/latest` will enter `byId` with `id="latest"`. Right:

~~~java
return RouterFunctions.route()
        .GET("/api/books/latest", handler::latest)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

**Functional routes are evaluated in order**; they do not use the "most specific wins" comparator of annotated controller mappings within the same router builder.

### 5.3. Ordering multiple beans and `@Order`

When separate beans have overlapping paths or predicates, do not rely on filenames, registration order, or assume `@Order` behaves identically across versions. Whenever precedence truly matters:

- Place overlapping routes inside **the same builder**.
- Or compose explicitly with `andOther`/`add`.
- Or pick a sorting contract supported by your Framework version and write HTTP integration tests.
- Best of all, assign **one clear owner per method/path**.

### 5.4. Explicit composition

~~~java
RouterFunction<ServerResponse> first =
        RouterFunctions.route()
                .GET("/api/a", handler::a)
                .build();

RouterFunction<ServerResponse> second =
        RouterFunctions.route()
                .GET("/api/b", handler::b)
                .build();

RouterFunction<ServerResponse> combined =
        first.andOther(second);
~~~

This code fragment assumes handler methods exist. The composite checks the first router and falls back to the second if unmatched. The builder also provides `add(second)` when composing.

### 5.5. Nested routers

~~~java
return RouterFunctions.route()
        .path("/api/books", b -> b
                .GET("/latest", handler::latest)
                .GET("/{id}", handler::byId)
                .POST(handler::create))
        .build();
~~~

Nesting avoids repeating path prefixes while preserving route order.

## 6. Functional and annotated controllers can run together

Suppose we have:

~~~java
@RestController
class AnnotatedStatus {
    @GetMapping("/api/annotated/status")
    Mono<Map<String, String>> status() {
        return Mono.just(Map.of("mode", "annotated"));
    }
}
~~~

and:

~~~java
@Bean
RouterFunction<ServerResponse> functionalStatus() {
    return RouterFunctions.route()
            .GET("/api/fn/status", request ->
                    ServerResponse.ok()
                            .bodyValue(Map.of("mode", "functional")))
            .build();
}
~~~

These two routes do not conflict and share the same WebFlux `DispatcherHandler`.

**If the exact same `GET /api/status` appears in both**, `DispatcherHandler` picks whichever `HandlerMapping` matches first according to mapping order. Never promise that one style always wins. Verify actual `HandlerMapping` order with regression tests, or eliminate the overlap.

Distinguish three levels of handler selection:

1. **Inside a functional router:** first matching request predicate wins.
2. **Across `HandlerMapping`s:** first matching handler mapping wins.
3. **Inside annotated `RequestMappingHandlerMapping`:** mapping specificity/conditions select the method per the annotation matching algorithm.

`WebFluxConfigurer#configurePathMatching(...).addPathPrefix` typically targets **annotated controller type predicates**; do not assume it adds prefixes to functional `RouterFunction` paths automatically.

## 7. HandlerFilterFunction and WebFilter

The functional route builder provides `filter`, `before`, and `after`:

~~~java
return RouterFunctions.route()
        .GET("/api/books", handler::list)
        .filter((request, next) ->
                next.handle(request)
                        .doOnError(error -> metrics.increment()))
        .build();
~~~

This is a fragment; `metrics` is undefined. This filter applies only to this router's scope, not automatically to `@RestController`s or other `RouterFunction` beans.

A filter can short-circuit:

~~~java
.filter((request, next) -> {
    if (maintenance.isActive()) {
        return ServerResponse.status(503)
                .bodyValue(Map.of("code", "MAINTENANCE"));
    }
    return next.handle(request);
})
~~~

Distinction:

| Mechanism | Scope |
| --- | --- |
| `HandlerFilterFunction` | Filtered `HandlerFunction`s within the router or nested route |
| `WebFilter` | `WebHandler` chain, covering both annotated and functional endpoints |
| `SecurityWebFilterChain` | Reactive authentication/authorization |
| `CorsWebFilter` | CORS for WebFlux functional endpoints per Spring docs |

A router filter is not a Spring Security policy. In apps with cross-origin frontends, CORS preflights require an allowlist of origins/methods/headers and proper ordering relative to Security; CORS does not replace auth or CSRF.

## 8. Errors and HTTP statuses in functional handlers

### 8.1. Do not rely solely on `@RestControllerAdvice`

`@RestControllerAdvice` belongs to annotated controller exception resolution; do not assume it handles every exception thrown by a `HandlerFunction`. A route filter can handle domain input errors:

~~~java
.filter((request, next) ->
        next.handle(request)
                .onErrorResume(BadInputException.class,
                        ex -> ServerResponse.badRequest()
                                .bodyValue(Map.of(
                                        "code", "INVALID_INPUT"))))
~~~

For public HTTP APIs, prefer RFC 9457 `ProblemDetail` with matching HTTP and body statuses, never echoing raw exception messages or secrets.

### 8.2. No-match vs. domain not-found

- `GET /api/fn/books/999` matches the router, but the store lacks the record → domain 404 with `BOOK_NOT_FOUND`.
- `GET /api/fn/unknown` matches no handler → framework 404, potentially with a different body.

An HTTP 404 alone does not tell clients the error source; apps need domain codes when clients branch on the distinction.

### 8.3. `Accept` and `Content-Type` predicates

If a functional route includes `RequestPredicates.accept(APPLICATION_JSON)` and a client sends another media type, the router may simply **not match**, producing a 404 or another error depending on mappings. Never assume every mismatch automatically yields 406. Likewise, a `Content-Type` predicate does not guarantee 415 in every topology. Test exact methods, paths, predicates, and codecs.

### 8.4. Errors after the response has committed

Once an SSE or stream response has sent HTTP 200 and body bytes, you cannot switch it to a new HTTP 500 JSON response on the same exchange. If the channel is still usable, emit an SSE error event per your application protocol; if the client dropped the transport, cancel, clean up, and log. `DispatcherHandler`/`ServerResponseResultHandler` cannot undo already-flushed HTTP headers.

## 9. Standalone runnable Maven project

The project uses **Java 17 + Spring Boot 3.5.0 + Spring WebFlux** with:

- Two `RouterFunction` beans: `bookRoutes` and `systemRoutes`.
- One annotated controller: `AnnotatedPingController`.
- `BookHandler` injected with `BookStore` by Spring.
- Specific `/latest` route placed before variable `/{id}`.
- JSON POST creating a `Book` in an in-memory `Map`, returning 201 + relative `Location`.
- `HandlerFilterFunction` mapping invalid input to an HTTP 400 `ProblemDetail`.
- `WebTestClient` integration tests verifying `DispatcherHandler`/`RouterFunctionMapping` and all endpoints.

### 9.1. Layout

~~~text
functional-router-demo/
├── pom.xml
└── src/
    ├── main/java/demo/FunctionalRouterApplication.java
    └── test/java/demo/FunctionalRouterTest.java
~~~

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>functional-router-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
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
~~~

### 9.3. FunctionalRouterApplication.java

Put all of the following Java code into `src/main/java/demo/FunctionalRouterApplication.java`. Only one top-level `public` class; the remaining records and classes are package-private.

~~~java
package demo;

import java.net.URI;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class FunctionalRouterApplication {
    public static void main(String[] args) {
        SpringApplication.run(FunctionalRouterApplication.class, args);
    }
}

record Book(long id, String title) {
}
record NewBook(String title) {
}
class BadInputException extends RuntimeException {
}

@Service
class BookStore {
    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong(10);

    BookStore() {
        books.put(1L, new Book(1L, "Spring WebFlux"));
    }

    Mono<Book> find(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(books.get(id)));
    }

    Mono<Book> create(String title) {
        return Mono.fromSupplier(() -> {
            long id = ids.incrementAndGet();
            Book book = new Book(id, title);
            books.put(id, book);
            return book;
        });
    }
}

@Component
class BookHandler {
    private final BookStore store;

    BookHandler(BookStore store) {
        this.store = store;
    }

    Mono<ServerResponse> latest(ServerRequest request) {
        return store.find(1L)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book));
    }

    Mono<ServerResponse> byId(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException exception) {
            return Mono.error(new BadInputException());
        }

        if (id <= 0) {
            return Mono.error(new BadInputException());
        }

        return store.find(id)
                .flatMap(book -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(book))
                .switchIfEmpty(problem(HttpStatus.NOT_FOUND,
                        "BOOK_NOT_FOUND", "Book not found"));
    }

    Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(NewBook.class)
                .switchIfEmpty(Mono.error(new BadInputException()))
                .flatMap(input -> {
                    if (input.title() == null
                            || input.title().isBlank()) {
                        return Mono.error(new BadInputException());
                    }
                    return store.create(input.title())
                            .flatMap(book -> ServerResponse
                                    .created(URI.create(
                                            "/api/fn/books/" + book.id()))
                                    .contentType(
                                            MediaType.APPLICATION_JSON)
                                    .bodyValue(book));
                });
    }

    Mono<ServerResponse> badInput() {
        return problem(HttpStatus.BAD_REQUEST,
                "INVALID_INPUT", "Invalid input data");
    }

    private Mono<ServerResponse> problem(
            HttpStatus status, String code, String detail) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                status, detail);
        p.setProperty("code", code);
        return ServerResponse.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(p);
    }
}

@Configuration(proxyBeanMethods = false)
class FunctionalRoutes {
    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler books) {
        return RouterFunctions.route()
                .GET("/api/fn/books/latest", books::latest)
                .GET("/api/fn/books/{id}", books::byId)
                .POST("/api/fn/books", books::create)
                .filter((request, next) ->
                        next.handle(request)
                                .onErrorResume(
                                        BadInputException.class,
                                        error -> books.badInput()))
                .build();
    }

    @Bean
    RouterFunction<ServerResponse> systemRoutes() {
        return RouterFunctions.route()
                .GET("/api/fn/ping", request ->
                        ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(Map.of(
                                        "style", "functional",
                                        "ok", true)))
                .build();
    }
}

@RestController
class AnnotatedPingController {
    @GetMapping(path = "/api/annotated/ping",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Mono<Map<String, Object>> ping() {
        return Mono.just(Map.of(
                "style", "annotated", "ok", true));
    }
}
~~~

### 9.4. Code explanation

- The two `RouterFunction` beans have disjoint paths, so bean order does not matter.
- `RouterFunctionMapping` discovers both beans; `HandlerFunctionAdapter` invokes the functional handlers; `ServerResponseResultHandler` encodes and writes the response.
- `AnnotatedPingController` runs in the same `DispatcherHandler` via `RequestMappingHandlerMapping`/Adapter.
- `/latest` precedes `/{id}` so `"latest"` is not parsed as a `long`.
- `BookHandler` is a `@Component` singleton and never stores mutable per-request `ServerRequest` state in fields.
- `BookStore` uses `AtomicLong` + `ConcurrentHashMap` for illustration, with no database or transactions.
- `Mono.defer` and `Mono.fromSupplier` defer work until subscription.
- The router-specific filter catches only `BadInputException` for book routes; it does not catch errors from annotated controllers or security.
- `ProblemDetail` and HTTP statuses are constructed safely without exposing exception messages.
- `ServerResponse.created(URI.create(...))` returns a relative 201 `Location` URL, avoiding hardcoding an internal backend origin.
- Neither `@EnableWebFlux` nor manually created infrastructure beans are added.
- The demo has no authentication, CORS, or persistence; production systems must design those explicitly.

### 9.5. Running

~~~bash
mvn spring-boot:run
~~~

Functional:

~~~bash
curl -i http://localhost:8080/api/fn/ping
curl -i http://localhost:8080/api/fn/books/latest
curl -i http://localhost:8080/api/fn/books/1
~~~

Example body:

~~~json
{"id":1,"title":"Spring WebFlux"}
~~~

Annotated:

~~~bash
curl -i http://localhost:8080/api/annotated/ping
~~~

Body:

~~~json
{"style":"annotated","ok":true}
~~~

Errors:

~~~bash
curl -i http://localhost:8080/api/fn/books/999
curl -i http://localhost:8080/api/fn/books/not-a-number
~~~

Expected 404/`BOOK_NOT_FOUND` and 400/`INVALID_INPUT` respectively.

POST:

~~~bash
curl -i -X POST http://localhost:8080/api/fn/books \
  -H 'Content-Type: application/json' \
  --data '{"title":"Reactive Book"}'
~~~

The first creation can return:

~~~http
HTTP/1.1 201 Created
Location: /api/fn/books/11
Content-Type: application/json

{"id":11,"title":"Reactive Book"}
~~~

IDs increment across requests; never hardcode 11 in tests.

## 10. WebTestClient integration tests

Create `src/test/java/demo/FunctionalRouterTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.DispatcherHandler;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.support.HandlerFunctionAdapter;
import org.springframework.web.reactive.function.server.support.RouterFunctionMapping;
import org.springframework.web.reactive.function.server.support.ServerResponseResultHandler;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class FunctionalRouterTest {
    @Autowired WebTestClient http;
    @Autowired ApplicationContext context;

    @Test
    void webfluxInfrastructureIsManagedBySpring() {
        assertNotNull(context.getBean(DispatcherHandler.class));
        assertNotNull(context.getBean(RouterFunctionMapping.class));
        assertNotNull(context.getBean(HandlerFunctionAdapter.class));
        assertNotNull(context.getBean(ServerResponseResultHandler.class));
        assertTrue(context.getBeansOfType(RouterFunction.class)
                .size() >= 2);
    }

    @Test
    void functionalAndAnnotatedBothRespond() {
        http.get().uri("/api/fn/ping").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.style").isEqualTo("functional");

        http.get().uri("/api/annotated/ping").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.style").isEqualTo("annotated");
    }

    @Test
    void exactRouteWinsOverVariableRoute() {
        http.get().uri("/api/fn/books/latest").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.title").isEqualTo("Spring WebFlux");
    }

    @Test
    void variableRouteWorks() {
        http.get().uri("/api/fn/books/1").exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1);
    }

    @Test
    void missingBookReturnsDomain404() {
        http.get().uri("/api/fn/books/999999").exchange()
                .expectStatus().isNotFound()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.code").isEqualTo("BOOK_NOT_FOUND");
    }

    @Test
    void invalidBookIdReturns400() {
        http.get().uri("/api/fn/books/abc").exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }

    @Test
    void createReturns201WithLocation() {
        http.post().uri("/api/fn/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewBook("Test"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().valueMatches(
                        HttpHeaders.LOCATION,
                        "/api/fn/books/[0-9]+")
                .expectBody()
                .jsonPath("$.title").isEqualTo("Test");
    }

    @Test
    void invalidPostReturns400() {
        http.post().uri("/api/fn/books")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewBook(" "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_INPUT");
    }

    @Test
    void unmatchedPathReturns404() {
        http.get().uri("/api/fn/no-such-route").exchange()
                .expectStatus().isNotFound();
    }
}
~~~

Run:

~~~bash
mvn test
~~~

This is a Spring Boot HTTP integration test: it verifies exact beans in the `ApplicationContext` and real routing through the server rather than merely invoking controller methods directly.

### 10.1. Why not only `bindToRouterFunction`?

`WebTestClient` offers:

~~~java
WebTestClient client =
        WebTestClient.bindToRouterFunction(router).build();
~~~

This approach fits fast **isolated route tests**, yet does not prove that a `RouterFunction` bean is discovered by Spring Boot, that multiple beans are composed properly by `RouterFunctionMapping`, or that annotated controllers share `DispatcherHandler`. Since this lesson focuses on bean integration, `@SpringBootTest(RANDOM_PORT)` is an essential check.

## 11. Troubleshooting scenarios

| Symptom | What to check |
| --- | --- |
| Router bean exists yet returns 404 | Component scan, package, exact routes/predicates |
| `RouterFunctionMapping` missing | App type is MVC or wrong WebFlux dependencies |
| Wrong `RouterFunction` import | `web.servlet.function` vs. `web.reactive.function.server` |
| `/latest` gets parsed as `long` | Variable route declared before static route |
| Router A hijacks Router B | Overlapping predicates and bean composition ordering |
| Annotated beats functional on same path | `HandlerMapping` order; avoid overlaps |
| JSON body fails | Jackson/codec configuration or media types |
| Handler filter does not run on annotated route | `HandlerFilterFunction` scope is router-only |
| `@RestControllerAdvice` misses functional errors | Use route filters or `WebExceptionHandler` at the right layer |
| CORS preflight fails | `CorsWebFilter`/Security `OPTIONS` policy |
| Static resources vanish after `@EnableWebFlux` | Boot auto-configuration backed off |
| Blocking DB slows the entire app | Netty event loop is blocked |
| `bindToRouterFunction` passes while Boot app 404s | Isolated test does not verify bean discovery |
| SSE fails after 200 and cannot send 500 | Response has already committed |

## 12. Exercises

**Exercise 1.** Describe the three steps `RouterFunctionMapping` → `HandlerFunctionAdapter` → `ServerResponseResultHandler` and `DispatcherHandler`'s role.

**Exercise 2.** Register two `RouterFunction` beans in two different modules with disjoint paths; verify both with `WebTestClient`.

**Exercise 3.** Add a `@RestController` to the same application, proving both styles share one server/`DispatcherHandler`.

**Exercise 4.** Place a variable route before a static route, observe `GET /books/latest`, then fix it and write a test.

**Exercise 5.** Create two `RouterFunction` beans with an overlapping method/path and measure actual precedence; refactor to a single owner.

**Exercise 6.** Compose routers via `andOther`/`builder.add` instead of duplicating broad routes.

**Exercise 7.** Use `HandlerFilterFunction` to map `BadInputException` to a 400 `ProblemDetail`; verify the filter does not apply to annotated controllers.

**Exercise 8.** Compare `WebFilter` and `HandlerFilterFunction` in terms of scope, cross-cutting logging, and Security.

**Exercise 9.** Create a functional POST JSON handler and verify request `Content-Type`, body decoding, and error handling.

**Exercise 10.** Add CORS preflight via `CorsWebFilter` allowlisting a SPA origin; explain why it does not replace authorization.

**Exercise 11.** Compare `bindToRouterFunction` with `@SpringBootTest` `RANDOM_PORT`. What can only integration tests verify?

**Exercise 12.** Try calling `RouterFunctions.toHttpHandler` directly in a custom adapter; list the configs, filters, and codecs you must manage yourself.

**Exercise 13.** Create a wildcard route and test that it does not shadow annotated or static endpoints.

**Exercise 14.** Wrap a blocking legacy call with `Mono.fromCallable` + `boundedElastic`, verifying the event loop is not blocked.

## 13. Production checklist

- [ ] Spring Boot uses reactive WebFlux with the right packages and dependencies.
- [ ] `RouterFunction` beans actually exist in the `ApplicationContext`.
- [ ] `DispatcherHandler`, `RouterFunctionMapping`, `HandlerFunctionAdapter`, and `ServerResponseResultHandler` are managed by the framework.
- [ ] Functional and annotated routes have clear path ownership with no accidental overlaps.
- [ ] Inside functional builders, static/specific routes precede variable/wildcard routes.
- [ ] All route methods, predicates, `Accept`, and `Content-Type` combinations have integration tests.
- [ ] Handlers use DI and never store per-request mutable state in singletons.
- [ ] Handlers return `Publisher`s and never fire-and-forget `subscribe()` for request work.
- [ ] HTTP statuses/`ErrorResponse`/`ProblemDetail` are safe and never leak stack traces or secrets.
- [ ] `SecurityWebFilterChain` and `CorsWebFilter` have appropriate scopes and ordering.
- [ ] Reactive I/O is non-blocking, with timeout, backpressure, and cancellation policies.
- [ ] Post-commit streams never attempt to alter HTTP statuses/headers.
- [ ] Static resources and actuator/health mappings are never shadowed by wildcards.
- [ ] `WebTestClient` against the HTTP server/Boot context verifies bean discovery and annotated coexistence.
- [ ] Metrics use low-cardinality route templates, and logs carry safe correlation IDs.

## 14. Key takeaways

- `RouterFunctionMapping` collects Spring-managed `RouterFunction` beans, orders/composes them, and finds handlers.
- `HandlerFunctionAdapter` invokes functional handlers; `ServerResponseResultHandler` writes `ServerResponse`s.
- Functional and annotated controllers share **the same `DispatcherHandler`**, while using different `HandlerMapping`s and `HandlerAdapter`s.
- Functional builders use **first match**, `DispatcherHandler` uses **first matching `HandlerMapping`**, and annotated selection uses specificity.
- You do not need `@EnableWebFlux` or a custom `HttpHandler` to run `RouterFunction` beans with Boot.
- Never rely on incidental bean ordering for overlapping routes; avoid overlaps or compose explicitly with tests.
- `HandlerFilterFunction` differs in scope from `WebFilter`/`SecurityWebFilterChain`.
- Isolated router tests do not prove Spring Boot bean discovery; use HTTP `WebTestClient` integration tests.
- Design reactive publishers, error handling, cancellation, and sensitive-data protection from the start.

## 15. References

- [Spring Framework 6.2 — Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html).
- [Spring Framework 6.2 — DispatcherHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/dispatcher-handler.html).
- [Spring Framework 6.2 — WebFlux Configuration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html).
- [Spring Boot 3.5 — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html).
- [RouterFunctionMapping Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/support/RouterFunctionMapping.html).
- [HandlerFunctionAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/support/HandlerFunctionAdapter.html).
- [ServerResponseResultHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/reactive/function/server/support/ServerResponseResultHandler.html).
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/).
