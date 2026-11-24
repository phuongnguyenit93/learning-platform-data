# RouterFunction, RequestPredicate, and Nested Routes in Spring MVC

## 1. What Is Functional MVC?

In **Spring MVC**, you usually build HTTP APIs with `@RestController` and `@GetMapping`:

~~~java
@RestController
class BookController {
    @GetMapping("/api/books")
    List<Book> books() {
        return bookService.findAll();
    }
}
~~~

The code above is a fragment because `Book` and `bookService` are not yet defined. Spring MVC also supports the **functional endpoints** model, commonly called **WebMvc.fn**. Instead of placing annotations on individual handler methods, you declare handler selection as **functions mapping an HTTP request to a handler**.

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/api/health"),
                request -> ServerResponse.ok().body("OK"));
~~~

This is a standalone route using the `org.springframework.web.servlet.function` API. It connects:
- **`RequestPredicate`**: the condition matching a request, e.g., HTTP GET method and path `/api/health`.
- **`HandlerFunction<ServerResponse>`**: processes the matched request and creates a `ServerResponse`.
- **`RouterFunction<ServerResponse>`**: finds the appropriate handler for the request.
- **`ServerRequest`**: functional-style request object providing path variables, query parameters, headers, and body.
- **`ServerResponse`**: builder for status, headers, body, or response rendering.

Routes are **evaluated in declaration order**: if the first route matches, it is chosen first. Unlike annotated MVC where the framework uses mapping specificity to select a handler, in functional routing composition order is part of the design. Hence `/api/books/featured` must be placed before the general route `/api/books/{id}` if both can match.

### Learning Objectives

After this lesson you can:
1. Distinguish Servlet WebMvc.fn from reactive WebFlux.fn.
2. Understand `RouterFunction`, `HandlerFunction`, `RequestPredicate`, `ServerRequest`, and `ServerResponse`.
3. Read and write predicates by HTTP method, path, `Accept`, `Content-Type`, header, and query/form parameter.
4. Use `and`, `or`, `negate`, `andRoute`, the `RouterFunctions.route()` builder, and `GET`/`POST` methods.
5. Declare **nested** routes using `path(prefix, builder)` and `nest(predicate, builder)` without repeating paths or header constraints.
6. Understand how to distinguish unmatched handlers, handler errors, invalid request bodies, missing permissions, and exception mapping.
7. Build a Java 17+ Spring Boot 3.3.5 application with BookStore, BookHandler, nested RouterFunction, and MockMvc integration tests.
8. Know when functional MVC fits and when annotated controllers are easier to maintain.

**Version:** WebMvc.fn has existed since Spring Framework 5.2; the examples run on Spring Boot 3.3.5 / Spring Framework 6.1.x. Some "current" Spring Framework docs have moved to newer APIs; the examples below use only APIs present in the 6.1 line.

## 2. WebMvc.fn Belongs to the Servlet Stack, Not WebFlux.fn

The two ecosystems have very similar class names, yet **different packages**:

| Servlet WebMvc.fn | Reactive WebFlux.fn |
| --- | --- |
| `org.springframework.web.servlet.function.RouterFunction` | `org.springframework.web.reactive.function.server.RouterFunction` |
| `org.springframework.web.servlet.function.ServerRequest` | `org.springframework.web.reactive.function.server.ServerRequest` |
| `org.springframework.web.servlet.function.ServerResponse` | `org.springframework.web.reactive.function.server.ServerResponse` |
| Handler normally returns `ServerResponse` synchronously | Handler normally returns `Mono<ServerResponse>` |
| Servlet container + `DispatcherServlet` | Reactive HTTP runtime and reactive adapters |
| `spring-boot-starter-web` | `spring-boot-starter-webflux` |

**Do not let your IDE auto-import `org.springframework.web.reactive.function.server.*` by mistake** into a Spring MVC app. WebFlux's Java generic signatures, body builders, and test setup are different. Using WebMvc.fn does not make all I/O non-blocking; `ServerRequest.body(Class)` and synchronous JDBC/HTTP clients can still block on the servlet thread.

A Spring Boot application can use WebMvc.fn alongside `@RestController` if desired, but you must manage URL conflicts, mapping order, SecurityFilterChain, error handling, and API docs. Do not turn mixing both API styles into a "self-healing" workaround for route bugs.

## 3. Processing Flow of a Functional MVC Endpoint

~~~text
HTTP client
   |
   v
Servlet container / filters / Spring Security (if present)
   |
   v
DispatcherServlet
   |
   v
RouterFunctionMapping
   |
   +-- RouterFunction #1: match RequestPredicate?
   |       | yes -> HandlerFunction
   |       + no
   |
   +-- RouterFunction #2: match?
   |       | yes -> HandlerFunction
   |       + no -> Other HandlerMappings / 404 per configuration
   |
   v
HandlerFunctionAdapter / ServerRequest
   |
   v
HandlerFunction.handle(request)
   |
   v
ServerResponse (status + headers + body)
   |
   v
HTTP message converters / response writing
   |
   v
HTTP client
~~~

Simplified diagram: Spring MVC has multiple `HandlerMapping` implementations (annotated methods, functional routes, static resources...) with their own `order`. `RouterFunctionMapping` finds handlers from router functions; `HandlerFunctionAdapter` invokes the functional handler; the response is then written through MVC infrastructure. Do not claim functional endpoints always win or always lose to every annotated controller under every configuration — especially when mapping bean orders are customized.

### Three Key Stages

1. **Routing:** `RequestPredicate` decides which requests enter a handler. This is not yet authentication or body validation.
2. **Handling:** `HandlerFunction` reads data via `ServerRequest`, calls services, and creates a `ServerResponse`.
3. **Writing:** Spring Web MVC writes status, headers, and body using the appropriate converters/view facilities.

If a route **does not match**, the handler does not run; a 404/405/406/415 response can come from the mapping or error-handling mechanism. If a route **matched** but the handler throws an exception, that is a different branch requiring separate error mapping. Do not treat every 404 as the same error.

## 4. What Is `RequestPredicate`?

`RequestPredicate` is a condition on a request; conceptually it resembles `Predicate<ServerRequest>`, though Spring adds support for composition, path nesting, and introspection. Static factories from `RequestPredicates`:

| Factory (Servlet MVC) | Used For |
| --- | --- |
| `GET("/path")` | Match GET and path |
| `POST("/path")` | Match POST and path |
| `PUT("/path")`, `PATCH("/path")`, `DELETE("/path")` | Match method + path |
| `method(HttpMethod.GET)` | Match method without path constraint |
| `methods(GET,HEAD)` | Match a set of methods |
| `path("/api/**")` | Match URL path |
| `accept(MediaType.APPLICATION_JSON)` | Match Accept negotiation |
| `contentType(MediaType.APPLICATION_JSON)` | Match request Content-Type |
| `headers(h -> ...)` | Custom predicate on request headers |
| `param("view","summary")` | Match a WebMvc.fn request parameter |
| `all()` | Always match |
| `predicate.and(other)` | Both must be true |
| `predicate.or(other)` | At least one must be true |
| `predicate.negate()` | Negate condition |

**Note on API names:** `org.springframework.web.servlet.function.RequestPredicates` has `param(...)`. `WebFlux.fn` documentation has `queryParam(...)`, **but do not copy `RequestPredicates.queryParam(...)` from the reactive package into Servlet WebMvc.fn 6.1**. `ServerRequest.param("name")` reads a request parameter; it can include query/form parameters per Servlet semantics.

### 4.1. Matching method + path

~~~java
RequestPredicate findBook =
        RequestPredicates.GET("/api/books/{id}");
~~~

`GET("/api/books/{id}")` is a combination checking the GET method and the path pattern. Once the handler is chosen, `request.pathVariable("id")` retrieves the matched value.

Do not assume `{id}` is numeric: a path variable starts as a string; the handler must parse and validate its type/bounds.

### 4.2. Combining predicates with `and`

~~~java
RequestPredicate onlyJson =
        RequestPredicates.GET("/api/books")
                .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));
~~~

The route matches only if both the GET path and client Accept match JSON. `Accept` is a request for the **response** format, not a description of the request body.

### 4.3. Combining with `or` and `negate`

~~~java
RequestPredicate simpleReads =
        RequestPredicates.method(HttpMethod.GET)
                .or(RequestPredicates.method(HttpMethod.HEAD));

RequestPredicate notAdminPath =
        RequestPredicates.path("/admin/**").negate();
~~~

These are fragments requiring corresponding imports. `or`/`negate` change matching logic, **not security boundaries**. A `notAdminPath` route does not replace Spring Security authorization for `/admin/**`.

### 4.4. Header predicate

~~~java
RequestPredicate versionTwo = RequestPredicates.headers(
        headers -> "2".equals(headers.firstHeader("API-Version")));
~~~

If a browser from another origin sends a custom `API-Version` header, it typically triggers a CORS preflight. A router matching a version header does not automatically configure CORS or authorize the user.

### 4.5. Request parameter predicate

~~~java
RequestPredicate summary = RequestPredicates.param("view", "summary");
~~~

It can be combined with a GET path:

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route(
                RequestPredicates.GET("/api/books/featured").and(summary),
                handler::featured);
~~~

If `view` is missing, this route does not match; a more general route after it **can** match the same path. That is why proper ordering and explicit fallbacks are needed, rather than assuming an unmatched predicate automatically returns a desired 400 error.

### 4.6. Content-Type and Accept are different

| HTTP header | Predicate | Meaning |
| --- | --- | --- |
| `Accept: application/json` | `accept(APPLICATION_JSON)` | Client wants to **receive** JSON |
| `Content-Type: application/json` | `contentType(APPLICATION_JSON)` | Client is **sending a body** as JSON |

For POST/PUT with a JSON body, `contentType` is usually helpful. For GET returning JSON, `accept` is usually appropriate. Both are **routing conditions only**; if the content is syntactically invalid JSON, the handler/body converter can still raise an error after matching.

## 5. Declaring Routes with `RouterFunctions.route(predicate, handler)`

Minimal form:

~~~java
RouterFunction<ServerResponse> hello =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok().body("Hello MVC.fn"));
~~~

For a single route, this is easy to read. When there are multiple handlers, use `RouterFunction.andRoute` to chain:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route(
                RequestPredicates.GET("/hello"),
                request -> ServerResponse.ok().body("Hello"))
            .andRoute(
                RequestPredicates.GET("/ping"),
                request -> ServerResponse.ok().body("pong"));
~~~

The snippets here do not declare a class/bean; for Spring Boot to discover routes, register `RouterFunction<ServerResponse>` as a bean or integrate it via the equivalent mechanism. The full example in section 10 explicitly uses `@Bean`.

### 5.1. A router function selects a handler, it does not execute business logic itself

`RouterFunction.route(request)` returns an `Optional<HandlerFunction<...>>` by contract; the handler performs the work only when MVC invokes it. Avoid database/network calls with side effects inside `RequestPredicate` or during route registration, because predicates may be evaluated multiple times and do not represent a business transaction.

### 5.2. Composition with `and`

~~~java
RouterFunction<ServerResponse> composed =
        firstRoutes.and(secondRoutes);
~~~

This is a fragment assuming `firstRoutes`/`secondRoutes` are already defined. `and` tries the first router and then the second if needed, preserving route order. You can use `andRoute(predicate, handler)` to conveniently add a single route.

## 6. Builder DSL: `RouterFunctions.route()`

With many paths/methods, the builder DSL is cleaner:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/health", handler::health)
                .GET("/api/books/{id}", handler::byId)
                .GET("/api/books", handler::all)
                .POST("/api/books",
                        RequestPredicates.contentType(
                                MediaType.APPLICATION_JSON),
                        handler::create)
                .build();
~~~

`handler` is an application bean with methods `ServerResponse health(ServerRequest)`, `byId(...)`, `all(...)`, `create(...)`; this is an abbreviated fragment, while the full code is in section 10.

Each builder method specifies method, path, additional predicate (if any), and handler. Finally, `build()` returns a complete `RouterFunction<ServerResponse>`.

### 6.1. Route order is a mandatory rule

**Incorrect** example:

~~~java
RouterFunctions.route()
        .GET("/api/books/{id}", handler::byId)
        .GET("/api/books/featured", handler::featured)
        .build();
~~~

`/api/books/featured` can be matched by `{id}` in the first route. If `byId` parses a number, you may get a NumberFormatException instead of the featured response.

Corrected:

~~~java
RouterFunctions.route()
        .GET("/api/books/featured", handler::featured)
        .GET("/api/books/{id}", handler::byId)
        .build();
~~~

**Review rule:** static/specific routes first, broad variable/wildcard routes after; fallbacks or catch-alls must go last. This differs from annotation-based mappings in `@RequestMappingHandlerMapping`, which select by specificity according to internal rules.

## 7. Nested Routes with `path(prefix, builder)`

If an API has multiple routes under the same prefix:

~~~text
GET  /api/health
GET  /api/books
GET  /api/books/{id}
POST /api/books
~~~

We can avoid repeating `/api` and `/books`:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/health", handler::health)
                        .path("/books", books -> books
                                .GET("/{id}", handler::byId)
                                .GET("", handler::all)
                                .POST("", handler::create)))
                .build();
~~~

`path("/api", ...)` is **path prefix grouping**. Inside this branch, child paths are interpreted relative to the prefix. `/api/books/{id}` remains the full URL the client calls; you **do not send `/books/{id}`** just because the nested builder writes it that way.

Point to watch: when both dynamic and specific routes share a prefix, still preserve specificity by order. To match `GET /api/books` properly, the child builder typically uses `GET("", handler::all)` as in Spring's official path-nesting examples.

### 7.1. Why are nested routes useful?

- Organize routes by domain/module/resource.
- Reduce prefix duplication when changing `/api/v1` to `/api/v2`.
- Apply shared conditions (e.g., `Accept`) to a group of routes.
- Attach logging/header filters to one branch rather than the entire API.
- Split routes by module and assemble them with `add` or `path(prefix, supplier)`.

Drawback: overly deep nesting makes routing hard to trace, especially with multiple `nest` and filter scopes. Keep the route tree shallow, name branches clearly, and write exact tests for each URL.

### 7.2. How does `path` differ from `nest(path(...))`?

`path("/api", builder)` is a dedicated convenience for a path prefix. `nest(RequestPredicates.path("/api"), builder)` enables nested routing using a path predicate. For many use cases they express the same goal, though `nest` is more flexible because it can use **any predicate** (headers, Accept...), not just a URL prefix.

Do not confuse `nest` with a Servlet FORWARD/HTTP redirect. It only organizes route matching and handler selection.

## 8. Nested Routes with `nest(predicate, builder)`

Beyond paths, we can set a shared condition for GETs that return JSON:

~~~java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/books", books -> books
                        .nest(
                                RequestPredicates.accept(
                                        MediaType.APPLICATION_JSON),
                                json -> json
                                        .GET("/{id}", handler::byId)
                                        .GET("", handler::all))
                        .POST("",
                                RequestPredicates.contentType(
                                        MediaType.APPLICATION_JSON),
                                handler::create))
                .build();
~~~

Logic:
- Both GET `/{id}` and GET `""` must have an Accept header compatible with JSON to match the `nest(accept(...))` branch.
- POST sits **outside the Accept branch** yet still inside `path("/api/books")`; it only requires Content-Type JSON.
- If a client sends `Accept: text/html` and no other route exists, GET may fail to match; the final HTTP status depends on mapping/error infrastructure, so do not assume the handler surely returns 406.
- Enabling nested Accept does **not** automatically serialize objects to JSON; the handler must still return a `ServerResponse` with a body and suitable converter.
- A filter attached to a nested builder has a different scope from a filter attached to the parent builder.

### 8.1. Combining nested path and header

For example, if an API varies by header:

~~~java
RouterFunctions.route()
        .path("/api", api -> api
                .nest(
                        RequestPredicates.headers(
                                h -> "2".equals(
                                        h.firstHeader("API-Version"))),
                        v2 -> v2
                                .GET("/books", handler::booksV2)))
        .build();
~~~

This fragment requires a `booksV2` method on the handler. If a broad v1 `GET("/books")` route sits before the v2 branch, the v1 route can match first; **specific version conditions must precede the fallback**. For large APIs, use an explicit versioning strategy and tests instead of stuffing custom predicates into every route.

## 9. HandlerFunction, ServerRequest, and ServerResponse

### 9.1. `HandlerFunction<ServerResponse>`

A functional interface essentially taking a `ServerRequest` and producing a `ServerResponse`:

~~~java
ServerResponse health(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.TEXT_PLAIN)
            .body("OK");
}
~~~

No `@GetMapping` is needed on the handler method. The router bean links the URL to the method via `handler::health`. The handler can still reside in a Spring-managed `@Component`/`@Service`, use constructor injection, and call application services.

### 9.2. Reading path and query parameters

~~~java
String rawId = request.pathVariable("id");
long id = Long.parseLong(rawId);

String page = request.param("page").orElse("1");
~~~

These are illustrative fragments inside a method taking `ServerRequest request`. `pathVariable` returns the matched route's path variable value, not automatically a `long`. `param` returns an Optional; calling `get()` immediately when missing will cause an exception. Parse numbers and validate ranges before calling the database.

### 9.3. Reading headers

~~~java
String requestId = request.headers().firstHeader("X-Request-Id");
MediaType contentType = request.headers().contentType()
        .orElse(MediaType.APPLICATION_OCTET_STREAM);
~~~

`headers().contentType()` returns an Optional for the request content type. A client-sent `X-Request-Id` header is not proof of identity; if you need a trace ID, validate/enforce trust boundaries instead of putting raw values into metric labels. Never log Authorization/Cookie headers to debug routing.

### 9.4. Reading the body

~~~java
CreateBook dto = request.body(CreateBook.class);
~~~

This is a fragment requiring a `CreateBook` record/class and may throw Servlet/IO/conversion errors. In WebMvc.fn, JSON conversion uses Spring MVC's `HttpMessageConverter`. **Having `contentType(APPLICATION_JSON)` on the route alone does not check all business rules**, and a functional handler does not automatically behave like `@Valid @RequestBody` on an annotated controller. Validate DTOs in code or with Jakarta Validator in the service/handler as needed.

### 9.5. Building the response

~~~java
return ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(book);
~~~

~~~java
return ServerResponse.created(URI.create("/api/books/3"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(createdBook);
~~~

~~~java
return ServerResponse.noContent().build();
~~~

These fragments assume `book` and `createdBook` variables are defined. `ServerResponse` provides fluent builders for status/headers/body; do not return `ResponseEntity` directly as the standard return type of a WebMvc.fn handler. `ServerResponse.ok().body(...)` in the Servlet API is a synchronous builder, unlike `bodyValue(...)` in reactive WebFlux.fn examples.

### 9.6. Comparing annotated and functional signatures

| Annotation MVC | Functional MVC |
| --- | --- |
| `@GetMapping("/{id}")` | `GET("/{id}", handler::byId)` |
| `@PathVariable long id` | `request.pathVariable("id")` then parse |
| `@RequestParam String q` | `request.param("q")` |
| `@RequestBody DTO input` | `request.body(DTO.class)` |
| `ResponseEntity.ok(dto)` | `ServerResponse.ok().body(dto)` |
| `@ControllerAdvice`, `@ExceptionHandler` | `onError(...)` on the router builder and MVC exception infrastructure per config |
| `HandlerInterceptor` | `before/after/filter` on the router builder, alongside Servlet filters |
| `@RequestMapping` grouping | `path(...)` and `nest(...)` |

This does not mean the functional model lacks integration with Spring Security, MVC message converters, or DI. The difference is **how routing and handler signatures are declared**.

## 10. Runnable Java 17 Example: Book API Using Nested RouterFunction

The small application demonstrates completely:
- `GET /api/health` → text `OK`.
- `GET /api/books` → JSON list of books.
- `GET /api/books/{id}` → JSON single book or 404.
- `GET /api/books/featured?view=summary` → JSON featured book when parameter matches.
- `GET /api/books/featured` missing `view=summary` → 400 with illustrative error code.
- `POST /api/books` with JSON body creates a book in an in-memory store, HTTP 201 and Location.
- `GET` routes nest an `Accept: application/json` condition; the POST route nests under the prefix yet constrains `Content-Type: application/json`.
- Error mapping `onError(BookMissingException.class, ...)` and `onError(InvalidBookInputException.class, ...)`.

The demo runs on **Spring Boot 3.3.5 / Java 17**, uses `spring-boot-starter-web`, and has no Spring WebFlux dependency. Data is in-memory to show HTTP flow; restarting resets it. Do not treat this as a production database, auditing, or authentication.

Structure:

~~~text
mvc-fn-books/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/mvcfn/
    │   ├── MvcFnBooksApplication.java
    │   ├── data/BookStore.java
    │   └── web/
    │       ├── BookHandler.java
    │       └── BookRoutes.java
    └── test/java/com/example/mvcfn/
        └── BookRoutesTest.java
~~~

### 10.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'mvc-fn-books'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Do not add `spring-boot-starter-webflux` just because you see the name RouterFunction. On Boot 3, imports from `org.springframework.web.servlet.function` are what matter most.

### 10.2. Main application

`src/main/java/com/example/mvcfn/MvcFnBooksApplication.java`:

~~~java
package com.example.mvcfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcFnBooksApplication {
    public static void main(String[] args) {
        SpringApplication.run(MvcFnBooksApplication.class, args);
    }
}
~~~

### 10.3. BookStore: thread-safe in-memory data source

`src/main/java/com/example/mvcfn/data/BookStore.java`:

~~~java
package com.example.mvcfn.data;

import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Component;

@Component
public class BookStore {

    public record Book(long id, String title) {}

    private final ConcurrentMap<Long, Book> books =
            new ConcurrentHashMap<>();

    private final AtomicLong ids = new AtomicLong(2);

    public BookStore() {
        books.put(1L, new Book(1L, "Spring Web"));
        books.put(2L, new Book(2L, "Functional MVC"));
    }

    public List<Book> all() {
        return books.values().stream()
                .sorted(Comparator.comparingLong(Book::id))
                .toList();
    }

    public Optional<Book> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    public Book create(String title) {
        long id = ids.incrementAndGet();
        Book book = new Book(id, title);
        books.put(id, book);
        return book;
    }
}
~~~

This is in-memory state used to demonstrate routes/handlers. `ConcurrentHashMap` and `AtomicLong` avoid common errors when concurrent requests generate IDs **within one JVM**. They do not share data across multiple pods/nodes and do not provide persistence/transactions. In real production deployments, replace with a repository/database, access control checks, validation, unique constraints, and transactions.

### 10.4. BookHandler: where HTTP requests are handled

`src/main/java/com/example/mvcfn/web/BookHandler.java`:

~~~java
package com.example.mvcfn.web;

import com.example.mvcfn.data.BookStore;
import com.example.mvcfn.data.BookStore.Book;
import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class BookHandler {

    public record NewBook(String title) {}
    public record ApiError(String code, String message) {}

    public static final class BookMissingException
            extends RuntimeException {
        public BookMissingException(long id) {
            super("Book not found: " + id);
        }
    }

    public static final class InvalidBookInputException
            extends RuntimeException {
        public InvalidBookInputException(String message) {
            super(message);
        }
    }

    private final BookStore store;

    public BookHandler(BookStore store) {
        this.store = store;
    }

    public ServerResponse health(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("OK");
    }

    public ServerResponse all(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all());
    }

    public ServerResponse byId(ServerRequest request) {
        String raw = request.pathVariable("id");
        long id;
        try {
            id = Long.parseLong(raw);
        } catch (NumberFormatException badId) {
            throw new InvalidBookInputException(
                    "id must be an integer");
        }

        if (id <= 0) {
            throw new InvalidBookInputException(
                    "id must be positive");
        }

        Book book = store.find(id)
                .orElseThrow(() -> new BookMissingException(id));

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse featured(ServerRequest request) {
        Book book = store.find(1L)
                .orElseThrow(() -> new BookMissingException(1L));
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse invalidFeatured(ServerRequest request) {
        throw new InvalidBookInputException(
                "featured requires view=summary");
    }

    public ServerResponse create(ServerRequest request)
            throws Exception {

        NewBook input = request.body(NewBook.class);
        if (input == null || input.title() == null ||
                input.title().isBlank()) {
            throw new InvalidBookInputException(
                    "title is required");
        }

        Book book = store.create(input.title().trim());
        return ServerResponse.created(
                        URI.create("/api/books/" + book.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }
}
~~~

Not every runtime will invoke the handler when the JSON body is malformed; request conversion may throw an exception before `NewBook` exists. The error mapping in the router below handles two illustrative business error types, without trying to "catch everything" and hide 500s.

The `ApiError` objects in the demo contain only safe information. Never return raw stack traces, SQL errors, credentials, or filesystem paths from exceptions in JSON. Full validation can use Jakarta Bean Validation separately with `Validator` or validation in the service; **functional routing does not automatically replace `@Valid @RequestBody` of an annotated controller**.

### 10.5. BookRoutes: path prefix, nested Accept, parameter predicate, and onError

`src/main/java/com/example/mvcfn/web/BookRoutes.java`:

~~~java
package com.example.mvcfn.web;

import static org.springframework.web.servlet.function.RequestPredicates.accept;
import static org.springframework.web.servlet.function.RequestPredicates.contentType;
import static org.springframework.web.servlet.function.RequestPredicates.param;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.RouterFunctions;
import org.springframework.web.servlet.function.ServerResponse;

@Configuration
public class BookRoutes {

    @Bean
    RouterFunction<ServerResponse> bookRouter(BookHandler handler) {
        return RouterFunctions.route()
                .path("/api", api -> api
                        .GET("/health", handler::health)
                        .path("/books", books -> books
                                .nest(accept(MediaType.APPLICATION_JSON),
                                        json -> json
                                                .GET("/featured",
                                                        param("view", "summary"),
                                                        handler::featured)
                                                .GET("/featured",
                                                        handler::invalidFeatured)
                                                .GET("/{id}", handler::byId)
                                                .GET("", handler::all))
                                .POST("",
                                        contentType(MediaType.APPLICATION_JSON),
                                        handler::create)))
                .onError(BookHandler.BookMissingException.class,
                        (ex, request) ->
                                ServerResponse.status(404)
                                        .contentType(
                                                MediaType.APPLICATION_JSON)
                                        .body(new BookHandler.ApiError(
                                                "BOOK_NOT_FOUND",
                                                "Book does not exist")))
                .onError(BookHandler.InvalidBookInputException.class,
                        (ex, request) ->
                                ServerResponse.badRequest()
                                        .contentType(
                                                MediaType.APPLICATION_JSON)
                                        .body(new BookHandler.ApiError(
                                                "INVALID_BOOK_INPUT",
                                                ex.getMessage())))
                .build();
    }
}
~~~

**Important order checks:**
1. `path("/api", ...)` groups the root API.
2. `GET("/health")` has no JSON Accept condition because it returns plain text.
3. `path("/books", ...)` groups the resource.
4. `nest(accept(JSON), ...)` applies a shared Accept condition to **the entire GET group**; it does not apply to POST outside it.
5. `GET("/featured", param("view","summary"),...)` must come before the `GET("/featured",...)` fallback.
6. Both featured routes must come before `GET("/{id}", ...)`; otherwise "featured" is interpreted as an ID.
7. `GET("", ...)` only matches the list at the `/api/books` prefix.
8. `POST("", contentType(JSON),...)` only matches POST requests at the prefix with a matching JSON Content-Type.
9. `onError` on the router builder maps the two exception types thrown by the handler to JSON with machine-readable codes.
10. `build()` produces a single `RouterFunction<ServerResponse>` and Spring Boot discovers the bean.

**Do not assume `onError` replaces all global error handlers.** It handles exceptions passing through the router filter chain of these routes; exceptions raised by security filters, the Servlet container, or other components may follow different error paths. Test the entire HTTP stack thoroughly when Spring Security is enabled.

### 10.6. Request → route → handler → response

| Request | Matched Route | Handler | Expected HTTP |
| --- | --- | --- | --- |
| GET `/api/health` | `/api` + `/health` | health | 200 text `OK` |
| GET `/api/books`, Accept JSON | `/api` + `/books` + nested Accept + GET empty | all | 200 JSON list |
| GET `/api/books/1`, Accept JSON | GET `/{id}` | byId | 200 book 1 |
| GET `/api/books/999`, Accept JSON | GET `/{id}` | byId + onError | 404 JSON code `BOOK_NOT_FOUND` |
| GET `/api/books/not-a-number`, Accept JSON | GET `/{id}` | byId + onError | 400 JSON code `INVALID_BOOK_INPUT` |
| GET `/api/books/featured?view=summary`, Accept JSON | parameter-aware featured | featured | 200 JSON book 1 |
| GET `/api/books/featured`, Accept JSON | featured fallback | invalidFeatured | 400 JSON |
| POST `/api/books`, Content-Type JSON | POST empty + Content-Type | create | 201 JSON + Location |
| GET `/api/books`, Accept text/html | nested Accept does not match | not all | Response depends on mapping/error path; do not assume 200 JSON |
| POST `/api/books`, Content-Type text/plain | POST Content-Type does not match | not create | Routing/error status depends on Spring MVC config |

The table illustrates traversal through nested routing, and does not cover authentication, CORS, or production validation. The demo does not include the Spring Security starter, so all GET/POST calls work without login; **that is not safe for real user data**.

## 11. Trying It with curl

In a project with a Java 17-compatible Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

### 11.1. Health

~~~bash
curl -i http://localhost:8080/api/health
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

OK
~~~

`charset`, transfer headers, and HTTP header order may vary by server; what to check is HTTP 200 and response text `OK`.

### 11.2. Book list

~~~bash
curl -i 'http://localhost:8080/api/books' \
  -H 'Accept: application/json'
~~~

Expected 200:

~~~json
[
  {"id":1,"title":"Spring Web"},
  {"id":2,"title":"Functional MVC"}
]
~~~

Actual JSON formatting is usually single-line. If books were POSTed earlier, the list includes the new books; on a clean restart, the two default books above are always present.

### 11.3. Details and 404

~~~bash
curl -i 'http://localhost:8080/api/books/1' \
  -H 'Accept: application/json'

curl -i 'http://localhost:8080/api/books/999' \
  -H 'Accept: application/json'
~~~

ID 1 returns 200:

~~~json
{"id":1,"title":"Spring Web"}
~~~

ID 999 returns 404:

~~~json
{"code":"BOOK_NOT_FOUND","message":"Book does not exist"}
~~~

Non-numeric ID:

~~~bash
curl -i 'http://localhost:8080/api/books/abc' \
  -H 'Accept: application/json'
~~~

Expected 400:

~~~json
{"code":"INVALID_BOOK_INPUT","message":"id must be an integer"}
~~~

### 11.4. Featured route with param and fallback

~~~bash
curl -i 'http://localhost:8080/api/books/featured?view=summary' \
  -H 'Accept: application/json'
~~~

Expected 200, book ID 1. When the param is missing:

~~~bash
curl -i 'http://localhost:8080/api/books/featured' \
  -H 'Accept: application/json'
~~~

Expected 400 with `INVALID_BOOK_INPUT`. Because the fallback stands **before** `/{id}`, the string `featured` is not parsed as an ID.

### 11.5. POST JSON to create a book

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"MVC.fn Handbook"}'
~~~

On a fresh instance with no prior POSTs, status 201, header `Location: /api/books/3`, and body:

~~~json
{"id":3,"title":"MVC.fn Handbook"}
~~~

Verify again:

~~~bash
curl -i 'http://localhost:8080/api/books/3' \
  -H 'Accept: application/json'
~~~

Expected 200 with the newly created book. The actual ID increases with the number of POSTs, not fixed at 3 if the application has been running awhile. This is memory-local data; restarting loses new books.

If the POST body has an empty title:

~~~bash
curl -i -X POST 'http://localhost:8080/api/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
~~~

Expected 400 and `INVALID_BOOK_INPUT`. The route code catches only this exception type; broken JSON syntax can lead to a different error response depending on Spring MVC converter/container config.

## 12. MockMvc: Testing Nested Routes and Matching Order

MockMvc runs through Spring MVC handler mappings without opening an HTTP port. Since we register a `RouterFunction<ServerResponse>` bean, `RouterFunctionMapping` receives the real routes and tests can invoke them like an HTTP client.

`src/test/java/com/example/mvcfn/BookRoutesTest.java`:

~~~java
package com.example.mvcfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookRoutesTest {

    @Autowired
    MockMvc mvc;

    @Test
    void healthIsOutsideJsonAcceptNest() throws Exception {
        mvc.perform(get("/api/health"))
                .andExpect(status().isOk())
                .andExpect(content().string("OK"));
    }

    @Test
    void nestedBookListMatchesJsonGet() throws Exception {
        mvc.perform(get("/api/books")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].id").value(1))
                .andExpect(jsonPath("$[0].title").value("Spring Web"));
    }

    @Test
    void dynamicIdMatchesAfterSpecificRoutes() throws Exception {
        mvc.perform(get("/api/books/2")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(2))
                .andExpect(jsonPath("$.title").value("Functional MVC"));
    }

    @Test
    void featuredWithParamBeatsVariableRoute() throws Exception {
        mvc.perform(get("/api/books/featured")
                        .param("view", "summary")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1));
    }

    @Test
    void featuredWithoutParamGetsExplicitBadRequest() throws Exception {
        mvc.perform(get("/api/books/featured")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BOOK_INPUT"));
    }

    @Test
    void invalidNumericIdGetsBadRequest() throws Exception {
        mvc.perform(get("/api/books/not-a-number")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BOOK_INPUT"));
    }

    @Test
    void unknownBookGets404FromRouterOnError() throws Exception {
        mvc.perform(get("/api/books/99999")
                        .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("BOOK_NOT_FOUND"));
    }

    @Test
    void postJsonCreatesResourceAndLocation() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"New MVC.fn Book\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location",
                        startsWith("/api/books/")))
                .andExpect(jsonPath("$.title").value("New MVC.fn Book"));
    }

    @Test
    void postBlankTitleGets400() throws Exception {
        mvc.perform(post("/api/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"   \"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("INVALID_BOOK_INPUT"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

**What the tests prove:** route prefix nesting, JSON Accept predicate, query/form param predicate, route order, handler execution, custom error responses, and POST Content-Type. Do not infer that MockMvc proves reverse proxy URL rewriting, CORS preflight, cookie policies, TLS, or database transactions.

The test suite creates a memory-local book in one method; tests reading IDs 1 and 2 remain stable because the store never deletes old entries. If you need to assert exact counts across all tests, reset the store or isolate the application context/store per test; avoid depending on JUnit execution order.

### 12.1. Testing order with a negative case

A valuable regression test is `featuredWithoutParamGetsExplicitBadRequest`: if someone changes the order so `/{id}` comes before the `/featured` fallback, the request can be misprocessed as a string ID. The error code/status in the example might still be 400 because both branches map to 400; to catch exactly **which handler** was chosen, assert the message `"featured requires view=summary"` as well rather than only status/code.

In real products, tests must verify **response content and handler semantics**, not just HTTP status.

## 13. Filters in the RouterFunction Builder

Functional MVC allows filters around handlers:
- `before(Function<ServerRequest,ServerRequest>)`: transforms the request before the handler.
- `after(BiFunction<ServerRequest,ServerResponse,ServerResponse>)`: transforms/observes the response after the handler.
- `filter(HandlerFilterFunction<ServerResponse,ServerResponse>)`: wraps the handler and invokes `next.handle(request)`.
- `onError(Predicate<Throwable>, BiFunction<Throwable,ServerRequest,ServerResponse>)` or `onError(Class<? extends Throwable>,...)`: produces an alternate response for matching exceptions.

Illustrative logging fragment:

~~~java
RouterFunction<ServerResponse> route =
        RouterFunctions.route()
                .GET("/hello", request ->
                        ServerResponse.ok().body("Hello"))
                .filter((request, next) -> {
                    long start = System.nanoTime();
                    try {
                        return next.handle(request);
                    } finally {
                        long elapsed = System.nanoTime() - start;
                        // Record elapsed metric with allowlisted labels.
                    }
                })
                .build();
~~~

A `HandlerFilterFunction` only wraps **the routes within the builder** to which it is attached. When attached to a nested builder, its scope is limited to that branch; when attached to a parent, it covers child routes as well. This is an important distinction when writing audit/logging, correlation IDs, or filters returning secondary responses.

### 13.1. Filters in WebMvc.fn do not replace Servlet Filters/Spring Security

`filter((request,next)->...)` does not replace Spring Security authentication/authorization. It applies only to functional routes built at that point, not to all MVC controllers/Servlet endpoints. Security protection typically lives in `SecurityFilterChain` and runs before `DispatcherServlet`. For object/tenant-level access control, service/domain rules are still needed.

Do not log raw credentials in tracing logs. Do not measure handler duration alone and call it "HTTP response latency" if response writing/network time is excluded from the measurement.

### 13.2. `before` does not make a read body unread

If a request filter reads the entire `ServerRequest.body(...)`, the downstream handler may not be able to re-read the input stream depending on the implementation. It is better to validate metadata/headers in route filters, or use a properly designed caching request-body wrapper if the app genuinely must inspect the body twice. Also avoid mutating the `Authorization` header or user identity unsafely in a before filter.

### 13.3. `onError` and exception scopes

`RouterFunctions.Builder.onError(...)` helps produce specific responses when a handler/filter throws an exception within scope. However:
- Errors occurring **before** reaching the router (auth filter, CORS preflight) usually lie outside the handler filter.
- Errors when the response body is already streaming/committed may not be able to change the status.
- Catch-all `onError(Throwable.class,...)` can hide serious programming bugs; use typed exceptions and a safe default 500 + logging.
- A handler can construct `ServerResponse.status(400)` directly instead of throwing an exception, in which case `onError` does not run.
- Error branches from message conversion and global HandlerExceptionResolver behave according to implementation/version; test specific error cases.

## 14. `@ControllerAdvice` and Functional Endpoints

In annotated MVC, `@RestControllerAdvice`/`@ExceptionHandler` are commonly used for exception mapping. In functional MVC, `onError` on the router builder is a very clear place to wrap a group of functional routes; other MVC exception resolvers still exist and participate per Spring's request processing.

Do not assume:
- Every `@ControllerAdvice` selects only annotated handlers and ignores functional routes.
- Or that an arbitrary advice will always catch every error thrown from RouterFunction, including errors in Security filters.
- Or that a catch-all `onError` can return a JSON error even after a partial network body has been sent.

Write integration tests for the final HTTP response of each specific error. When aiming for a unified ProblemDetail schema across annotated MVC, functional MVC, and Spring Security, design a shared error model yet configure **each** error entry point/handler layer properly.

## 15. RouterFunctions and Spring Security/CORS

### 15.1. SecurityFilterChain is still required

Even though routes are declared with `RouterFunction` instead of `@RestController`, requests still pass through Servlet filters and Spring Security if dependencies/configs are present. Conceptual security policy example:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/health").permitAll()
    .requestMatchers("/api/books/**").authenticated()
    .anyRequest().denyAll())
~~~

This fragment requires SecurityConfig and `HttpSecurity`. It is **not** automatically included in the security-free demo in section 10. If POST/DELETE require CSRF tokens for cookie-authenticated browser clients, do not skip them merely because the handlers are functional.

### 15.2. CORS with a cross-origin frontend

A cross-origin browser sending `POST /api/books` with `Content-Type: application/json` usually must perform an OPTIONS preflight. The `contentType(APPLICATION_JSON)` predicate on POST does **not** handle CORS for the browser/framework. CORS must be configured at the proper filter/MVC/Security layer for the right origins/methods/headers, and the actual request still checks authentication/authorization/CSRF.

If an OPTIONS request only ambiguously matches GET/POST routes, do not create an `all()` fallback that blindly echoes arbitrary origins. Use Spring MVC CORS infrastructure or proper Security `cors()` configuration, and test with a browser/MockMvc.

### 15.3. Functional handlers and user identity

`ServerRequest` has access to the corresponding Servlet request/principal APIs; identity should be taken from a trusted authentication context, not from a client-supplied `?user=...` parameter. If a route handles `/api/books/{id}` by owner/tenant, authorize against the real data before returning the body, even on GET.

## 16. Functional MVC vs. Annotation MVC: When to Choose?

| Aspect | Functional MVC | Annotation MVC |
| --- | --- | --- |
| Route declaration | `RouterFunction` bean, predicate DSL | `@RequestMapping`/`@GetMapping` on methods |
| Prefix grouping | `path/nest` | `@RequestMapping` on class |
| Media/header conditions | `accept/contentType/headers` | `produces/consumes/headers` |
| Matching order | Composition order | Framework specificity selection |
| Handler signature | `ServerRequest -> ServerResponse` | Parameters can use `@PathVariable`, `@RequestBody`, `Model`... |
| Binding/validation | Explicit `ServerRequest.body/bind` and validator | Argument resolvers, `@Valid`... |
| Route-group filters | `before/after/filter/onError` | Servlet filters/interceptors/advice |
| OpenAPI/codegen ecosystem | May need explicit docs/metadata | Many tools infer cleanly from annotations |
| Best suited for | Routing DSL, composition, modular split | Everyday CRUD controllers, conventional DI/validation |

Do not convert all controllers to WebMvc.fn just because the functional syntax looks shorter. If most of your codebase uses `@Valid`, `@RequestBody`, Springdoc metadata, and annotated method security, annotated controllers can be easier to follow. If you need to compose many routes from modules, filter by group, and separate routing declarations from handlers, functional MVC is worth considering.

A codebase can combine both models, but route ownership must be clear and overlaps must be tested to avoid surprising behavior.

## 17. Splitting Routers Across Multiple Modules

A large application can define:
- `BookRoutes` for `/books`.
- `AuthorRoutes` for `/authors`.
- `HealthRoutes` for `/health`.

Then combine them using `RouterFunctions.Builder.add(...)` or `RouterFunction.and(...)`, and set prefixes with `path(...)`. Conceptual fragment example:

~~~java
RouterFunction<ServerResponse> combined =
        RouterFunctions.route()
                .path("/api/books", bookRoutes::routes)
                .path("/api/authors", authorRoutes::routes)
                .build();
~~~

Here `bookRoutes.routes()` and `authorRoutes.routes()` must return `RouterFunction<ServerResponse>` with relative child paths, and handler beans are injected. The fragment does not run standalone because the two classes do not exist yet. When there are multiple `RouterFunction` beans, check bean registration/order and avoid overlapping catch-all routes; do not assume source file order or bean names form a business contract.

### 17.1. Do not embed business logic in the Router bean

`@Bean RouterFunction` is constructed at application startup, not on each HTTP request. Therefore:
- Do not query the database for books while building the DSL and freeze the result for every request.
- Do not use `System.currentTimeMillis()` in routing configuration to decide per-request policy.
- Do not construct a new service/thread pool inside a handler lambda on every request.
- Inject handlers/services via constructors for easier testing and maintenance.
- Route predicates should be pure, cheap, and free of side effects; business logic belongs in handlers/services.

## 18. Path Patterns and Broad-Route Risks

Spring Framework 6.x uses path matching infrastructure with `PathPattern`. A path variable `/{id}` can match many strings, not necessarily only numbers. A wildcard path `/**` can match a wide range; if placed before specific routes in a functional chain, many requests hit the wrong handler.

Anti-pattern example:

~~~java
RouterFunctions.route()
        .GET("/api/{anything}", handler::catchAll)
        .GET("/api/health", handler::health)
        .build();
~~~

With this order, `/api/health` can be matched by the first route. Fix it by putting specific routes first. If a catch-all is genuinely required, place it last and check URL normalization, encoded segments, trailing slashes, and method matching for your framework/server version.

Do not assume functional routes and annotation mappings share equal priority when both register the same path; test with the full Spring application context.

## 19. Common Errors and How to Handle Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `RouterFunction` does not run in MVC | Imported `web.reactive.function.server` by mistake | Use `web.servlet.function`, Web starter |
| GET `/featured` parsed as `id` | Route `/{id}` placed before specific route | Reverse order |
| Nested route always returns 404 | Repeated/missing prefix or wrong child path | Trace full paths across all `path` calls |
| GET JSON does not match | `Accept` incompatible with nested predicate | Check Accept and `nest` group |
| POST JSON does not match | Missing/wrong Content-Type | Check contentType predicate |
| Handler cannot read body a second time | Filter/interceptor already consumed input stream | Avoid reading twice; use proper caching wrapper |
| `param("view","summary")` does not match | Missing param or different value | Check actual request parameter, fallback |
| `queryParam(...)` fails to compile | Used WebFlux.fn API in Servlet package | Use `param(...)` |
| `ServerResponse.bodyValue(...)` missing | Copied WebFlux.fn builder | Use `ServerResponse.ok().body(...)` |
| JSON record fails to serialize | Missing Jackson converter or wrong Content-Type | Check starter, converter, and response |
| `@Valid` does not run automatically | Functional body decode is not equivalent to annotated resolver | Call validator/validate in service |
| Unexpected 404/406/415 | Route did not match; other mappings/resolvers handle differently | Test actual response/mapping context |
| Catch-all `onError` hides 500 | Swallowing every exception | Typed exceptions and safe default logging |
| Route works but is insecure | Confused predicate with authorization | Spring Security + domain auth |
| Browser reports CORS on POST | OPTIONS preflight not configured | CORS/Security filter integration |
| GET tests pass but POST creates duplicate data | In-memory IDs, shared state across tests | Test isolation and proper persistence |
| API docs miss functional endpoints | Tool only introspects annotations | Explicit OpenAPI mappings/config |
| One request runs two routes | Misunderstood composition | Router picks first matching route; audit side effects |
| Errors when combining annotated routes | HandlerMapping order/overlap | Check mappings, integration tests |
| Using blocking JDBC in WebMvc.fn thinking it's reactive | Confused programming models | Servlet MVC remains blocking |
| Multiple router beans have unclear order | Implicit registration/order | Compose explicitly and test |

### Ordered Debugging Process

1. Confirm Spring Web/Boot dependencies and **Servlet WebMvc.fn imports**.
2. Confirm the `RouterFunction<ServerResponse>` bean is created in the Spring context.
3. Trace full paths across all `path(prefix)`/`nest(path)` calls.
4. Check order: static/specific before variable/wildcard.
5. Record the actual method, path, Accept, Content-Type, query/form params, and custom headers sent.
6. Check whether nested Accept/Content-Type/header predicates prevent the route from matching.
7. Distinguish unmatched routes from exceptions inside handlers; check the exact status/error code.
8. If Security is present, verify filter chain/CORS/CSRF before MVC.
9. Check message converters and body validation.
10. Add MockMvc tests for positive, negative, and route ordering cases, then E2E tests through any proxy/gateway.

## 20. Pre-Production Review Checklist

- [ ] Correct package `org.springframework.web.servlet.function` is used.
- [ ] RouterFunction beans are Spring-managed; handlers are constructor-injected.
- [ ] Specific routes precede wildcard/variable routes; fallbacks go last.
- [ ] Nested path prefixes are exact; child paths do not duplicate prefixes.
- [ ] `accept`/`contentType` are used with accurate HTTP semantics, not as substitutes for validation.
- [ ] `RequestPredicates.param` matches the Servlet API, not confused with WebFlux's `queryParam`.
- [ ] Path/query/body inputs are parsed, validated, and bounded before domain operations.
- [ ] Error mappings for 400/404/500 are safe and do not leak exception details.
- [ ] SecurityFilterChain, CSRF/CORS, and tenant/object authorization are enforced properly.
- [ ] Router filters have explicit scope and do not replace Spring Security.
- [ ] API docs/OpenAPI can describe functional routes; contract tests exist.
- [ ] Handler and converter performance is measured rather than assuming functional MVC is non-blocking.
- [ ] MockMvc verifies nesting, param/header/media predicates, conflicts, statuses, and response bodies.
- [ ] Integration tests cover any proxy/gateway if routes require rewriting.
- [ ] Large modules are composed in explicit order without catch-alls shadowing critical routes.

### Self-Check Questions

**1.** How does `RouterFunction` differ from `HandlerFunction`?

**Answer:** RouterFunction finds a HandlerFunction matching the request; HandlerFunction processes the ServerRequest and returns a ServerResponse.

**2.** Why should `GET("/books/{id}")` not precede `GET("/books/featured")`?

**Answer:** Functional routes are evaluated in order, so `{id}` can capture `featured`, causing the wrong handler to be selected.

**3.** How do `path("/api", ...)` and `nest(accept(JSON), ...)` differ?

**Answer:** `path` groups a URL prefix; `nest` applies an arbitrary RequestPredicate (here Accept) to child routes.

**4.** Which predicates do `Content-Type` and `Accept` affect?

**Answer:** The request body's Content-Type uses `contentType`; Accept describing the client's desired response uses `accept`.

**5.** In Servlet WebMvc.fn, do you use `param` or `queryParam`?

**Answer:** Use `RequestPredicates.param` from `org.springframework.web.servlet.function`. Do not confuse it with WebFlux.fn's `queryParam` API.

**6.** Does nested Accept JSON automatically serialize DTOs to JSON?

**Answer:** No. It only checks the match condition; `ServerResponse` and MVC HttpMessageConverter produce the response body.

**7.** Do router filters replace `SecurityFilterChain`?

**Answer:** No. Router filters belong to functional routes, whereas Spring Security protects HTTP requests via the Servlet filter chain and service/domain authorization.

**8.** Why should you not only assert HTTP 200 when testing functional routing?

**Answer:** The wrong handler might match while still returning status 200. Assert body/headers and contrasting route cases.

**9.** Does WebMvc.fn automatically use non-blocking I/O like WebFlux.fn?

**Answer:** No. It is a Servlet MVC programming model and can still block on JDBC or synchronous network I/O.

## 21. Official Documentation

- [Spring Framework 6.2 — Functional Endpoints (Spring MVC)](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc-functional.html): handler functions, request predicates, router functions, nested routing, filtering.
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.html): route/nest API.
- [Spring Framework 6.1 — RouterFunctions.Builder Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.Builder.html): `GET/POST/path/nest/onError/filter`.
- [Spring Framework 6.1 — RequestPredicates Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/function/RequestPredicates.html): `GET/POST/path/param/headers/accept/contentType`.
- [Spring Framework 6.1 — ServerRequest Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html): path variables, parameters, headers, body.
- [Spring Framework 6.1 — ServerResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html): response status, headers, body builders.
- [Spring Framework 6.2 — MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html): overall MVC handler mapping and adapter pipeline.
- [Spring Framework — MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): integration-style MVC test without opening a server port.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request authorization independent of router syntax.
- [Spring Framework — CORS in Servlet MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): cross-origin request policies.

**Key Takeaway:** WebMvc.fn uses `RouterFunction` to select a `HandlerFunction` via `RequestPredicate` and return a `ServerResponse`. `path` groups prefixes, `nest` groups shared conditions, and **route order must be designed deliberately**. Only use predicates to select routes — security, validation, error semantics, and business data still require separate layers and thorough HTTP testing.
