# WebMvc.fn and Differences from Annotation-Based Controllers in Spring MVC

## 1. What Problem Does WebMvc.fn Solve?

In Spring Web MVC, the common way to write endpoints is to place `@RestController`, `@GetMapping`, `@PostMapping` on classes/methods. Spring reads the annotation metadata and decides the appropriate handler. **WebMvc.fn** is an alternative **functional programming model**: you describe routing rules using `RouterFunction`, then pass the request into a `HandlerFunction` to receive a `ServerResponse`.

Both models **run on the same Servlet/MVC ecosystem**, not a choice between blocking threads and a reactive server:

- **Annotated MVC:** maps requests to controller methods using annotations and argument/return-value resolvers.
- **WebMvc.fn:** maps requests using predicate/router functions and handles them through `ServerRequest`/`ServerResponse` interfaces.
- **Same infrastructure:** `DispatcherServlet`, Servlet container, HTTP message converters, filters, Spring IoC, and most MVC configuration.
- **Not identical to WebFlux.fn:** WebFlux classes live in `org.springframework.web.reactive.function.server` and use `Mono`/`Flux`; MVC uses `org.springframework.web.servlet.function` and body APIs following the Servlet stack.

This lesson covers **Spring Framework 6.1.x**, **Spring Boot 3.3.5**, **Java 17**. The goal is to understand the architecture and choose the right style, not to claim that functional MVC is faster than annotated controllers or automatically creates non-blocking I/O.

### Learning Outcomes

After this lesson, you can:

1. Distinguish `RouterFunction`, `RequestPredicate`, `HandlerFunction`, `ServerRequest`, and `ServerResponse`.
2. Build GET/POST routes with path variables, query parameters, and JSON bodies.
3. Use `route()`, `path()`, `nest()`, `and(...)`, and correct route ordering.
4. Choose status, content type, body, and `Location` using `ServerResponse`.
5. Perform validation/exception handling without `@Valid @RequestBody` on controller parameters.
6. Write functional filters using `before`, `after`, and `filter`, understanding their scope of application.
7. Compare the same API implemented with WebMvc.fn and annotated controllers.
8. Run a complete Maven example, call curl, and test with MockMvc.
9. Identify security, CORS, request binding, OpenAPI, maintainability, and migration pitfalls.
10. Understand why WebMvc.fn **can still be blocking** and how it differs from WebFlux.fn.

## 2. Background: How Does an HTTP Request Flow Through Spring MVC?

Given a request:

```http
GET /fn/books/42 HTTP/1.1
Host: localhost:8080
Accept: application/json
```

An annotated controller can be declared as:

```java
@RestController
@RequestMapping("/ann/books")
public class AnnotatedBooks {
    @GetMapping("/{id}")
    public Book get(@PathVariable long id) {
        return service.find(id);
    }
}
```

This is a **descriptive snippet**; the `Book` class and `service` are not yet defined. Spring inspects the mapping annotation, converts `"42"` to `long`, invokes the method, and serializes the body to JSON.

The functional MVC equivalent in purpose:

```java
RouterFunction<ServerResponse> routes = route()
        .GET("/fn/books/{id}", request -> {
            long id = Long.parseLong(request.pathVariable("id"));
            Book book = service.find(id);
            return ServerResponse.ok()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(book);
        })
        .build();
```

This is also a **snippet**: `service` is undefined and imports are omitted. The key point is that the route + handler live in Java values/functions, not annotation metadata.

### Path of a WebMvc.fn Request

```text
Client HTTP request
         |
         v
Servlet Filter chain / Spring Security
         |
         v
DispatcherServlet
         |
         v
RouterFunctionMapping
  - try RouterFunctions
  - evaluate RequestPredicates
  - select first matching HandlerFunction
         |
         v
HandlerFunctionAdapter
  - invoke handler.handle(ServerRequest)
         |
         v
ServerResponse.writeTo(...)
  - HTTP status / headers / body conversion
         |
         v
Servlet response
```

This is a simplified diagram. WebMvc.fn uses the corresponding MVC components to integrate with `DispatcherServlet`. With annotations, `RequestMappingHandlerMapping` and `RequestMappingHandlerAdapter` handle the mapping/invocation step. **Sharing the same DispatcherServlet does not mean sharing identical argument resolver/interceptor behavior.**

When registering a `RouterFunction<ServerResponse>` as a bean in the Spring context, MVC auto-detects the router and wires it into the mapping infrastructure. With Spring Boot web starter, a basic MVC application **does not need an extra WebFlux dependency** and usually does not need `@EnableWebMvc`. Manually adding `@EnableWebMvc` in Boot can alter auto-configurations, so do not add it arbitrarily.

## 3. Five Core Components of WebMvc.fn

### 3.1. RequestPredicate — a matching rule

`org.springframework.web.servlet.function.RequestPredicate` decides whether a request matches. `RequestPredicates` provides predicates by HTTP method, path, headers, Accept, and Content-Type.

Example:

```java
RequestPredicate rule = GET("/fn/books/{id}")
        .and(accept(MediaType.APPLICATION_JSON));
```

This is a snippet with static imports `GET` and `accept` from `RequestPredicates`. If the request satisfies both GET/path and Accept, the rule can select the handler. `and`, `or`, and `negate` allow combining predicates.

**Note:** The `accept(APPLICATION_JSON)` predicate checks the `Accept` header, i.e., the type the client wants to **receive**. The `contentType(APPLICATION_JSON)` predicate checks `Content-Type`, i.e., the type of body the client **sends**. Do not swap the two headers.

### 3.2. HandlerFunction — the work of handling a request

`HandlerFunction<T extends ServerResponse>` is a functional interface. Conceptually:

```java
ServerResponse handle(ServerRequest request) throws Exception;
```

The signature above is just to remember the concept; the exact exception declaration depends on the API, so check the 6.1 Javadoc. A handler can be a lambda or method reference:

```java
HandlerFunction<ServerResponse> hello =
        request -> ServerResponse.ok()
                .contentType(MediaType.TEXT_PLAIN)
                .body("Hello MVC");
```

An annotated controller method has multiple parameters that Spring resolves automatically; a functional handler usually takes **a single `ServerRequest`** and explicitly reads the path/query/header/body.

### 3.3. ServerRequest — reading input data

`org.springframework.web.servlet.function.ServerRequest` provides:

| API | Purpose |
| --- | --- |
| `request.pathVariable("id")` | Value of a path placeholder |
| `request.pathVariables()` | Map of path variables |
| `request.param("q")` | `Optional<String>` of a query/form param |
| `request.params()` | `MultiValueMap<String,String>` of parameters |
| `request.headers()` | `ServerRequest.Headers`, including Accept/Content-Type/custom headers |
| `request.body(MyDto.class)` | Decodes the body using `HttpMessageConverter`, may throw |
| `request.body(new ParameterizedTypeReference<List<MyDto>>() {})` | Reads a generic collection |
| `request.servletRequest()` | Accesses the Servlet request when truly needed |
| `request.principal()` | Accesses the authenticated principal if present |

Example:

```java
long id = Long.parseLong(request.pathVariable("id"));
String q = request.param("q").orElse("");
CreateBookRequest dto = request.body(CreateBookRequest.class);
```

This is a snippet requiring `request` inside a functional handler. On an annotated controller, these parts might be `@PathVariable long id`, `@RequestParam(defaultValue="") String q`, and `@RequestBody CreateBookRequest dto`.

Functional style does not have automatic **magic** for parsing `long`: `pathVariable()` returns a String; you need to parse it and handle `NumberFormatException` or choose an explicit error policy. For a JSON body, `request.body(...)` uses registered converters and can report an error when JSON is invalid, the body is missing, or the media type is unsupported.

### 3.4. ServerResponse — declaring the HTTP response

`org.springframework.web.servlet.function.ServerResponse` provides builder-style APIs:

```java
ServerResponse.ok()
        .contentType(MediaType.APPLICATION_JSON)
        .body(book);

ServerResponse.created(URI.create("/fn/books/42"))
        .contentType(MediaType.APPLICATION_JSON)
        .body(book);

ServerResponse.noContent().build();

ServerResponse.status(HttpStatus.BAD_REQUEST)
        .contentType(MediaType.APPLICATION_JSON)
        .body(new ApiError("invalid_request"));
```

These are **snippets** with a `book` variable/`ApiError` class from a hypothetical application. Do not use WebFlux.fn's `ServerResponse.bodyValue(...)` in MVC: the Servlet `ServerResponse.BodyBuilder` API uses `body(...)` for regular objects.

Spring's body converters/serialization are used when writing the response. Use `ServerResponse.created(URI)` to produce HTTP 201 and the corresponding `Location` header, rather than writing `status=201` in the JSON body yourself.

### 3.5. RouterFunction — from request to handler

`RouterFunction<T>` returns an optional handler function when matching a request. In practice, the builder is commonly used:

```java
RouterFunction<ServerResponse> api = RouterFunctions.route()
        .GET("/fn/hello", request ->
                ServerResponse.ok().body("Hello"))
        .GET("/fn/status", request ->
                ServerResponse.ok().body("ready"))
        .build();
```

The builder can construct a router from multiple rules, adding nested routes and filters. **The order of functional routes is part of their behavior** — the first matching route can win.

## 4. Core Difference: Route Order

In annotated MVC, `RequestMappingHandlerMapping` has logic to compare mapping specificity. For example, `/books/latest` is typically chosen over `/books/{id}` due to specificity, regardless of the order the two methods are written in the file.

In WebMvc.fn, **routes are evaluated in order**. Therefore:

```java
// BE CAREFUL: /books/{id} placed before /books/latest
RouterFunction<ServerResponse> wrong = route()
        .GET("/fn/books/{id}", handler::getBook)
        .GET("/fn/books/latest", handler::latest)
        .build();
```

A `GET /fn/books/latest` request can match the `{id}` placeholder, passing the string `"latest"` to the ID-fetching handler. The result may be a parsing error instead of the latest endpoint.

Place the specific route first:

```java
RouterFunction<ServerResponse> correct = route()
        .GET("/fn/books/latest", handler::latest)
        .GET("/fn/books/{id}", handler::getBook)
        .build();
```

Both examples are snippets with a hypothetical `handler`. **Do not just sort alphabetically**. Tests are needed to protect the order of routes that could overlap.

When there are **multiple RouterFunction beans**, Spring MVC discovers/orders/chains them according to its infrastructure. Ordering can be affected by bean ordering/configuration. Therefore, for conflicting routes, do not assume file order or bean names; prefer clear grouping, use `@Order`/an appropriate ordering policy, and test for route collisions.

When using both annotations and functional endpoints under the same DispatcherServlet, each style has its own mapping component; do not infer cross-style precedence solely from Java declaration order. Check the behavior of your Spring version/framework config if both styles define the exact same URL + method.

## 5. Nested Routes and Composition

### 5.1. Grouping with path()

If all endpoints share the `/fn/books` prefix:

```java
RouterFunction<ServerResponse> routes = route()
        .path("/fn/books", books -> books
                .GET("/latest", handler::latest)
                .GET("/{id}", handler::getBook)
                .GET(handler::listBooks)
                .POST(handler::createBook))
        .build();
```

This is a snippet with a hypothetical handler class. `.path("/fn/books", builder -> ...)` is not just string concatenation: it creates a nested route group and applies the group's prefix/predicate. The `GET(handler::listBooks)` method in the nested builder matches the root route of the group. Prefer specific paths before variable paths.

### 5.2. Nesting by predicate

For example, a group of GET routes that all want JSON:

```java
RouterFunction<ServerResponse> routes = route()
        .path("/fn/books", books -> books
                .nest(accept(MediaType.APPLICATION_JSON), json -> json
                        .GET("/latest", handler::latest)
                        .GET("/{id}", handler::getBook)
                        .GET(handler::listBooks))
                .POST(handler::createBook))
        .build();
```

This is a snippet. `accept(APPLICATION_JSON)` restricts the **GET group**, not the POST outside `nest`. If a client sends `Accept: text/html`, the GET route may fail to match, creating behavior quite different from running the handler and letting the serializer pick a format; therefore, **404/406** responses for unmatched predicates should not be assumed to match annotated controller `produces`. Test the specific error contract.

### 5.3. Composition with and()/andRoute()

When you have two independent route groups:

```java
RouterFunction<ServerResponse> all =
        catalogRoutes.and(searchRoutes);
```

Or the builder `route().add(catalogRoutes).add(searchRoutes).build()`. This is **chaining routing behavior**, not copying annotations. Order still matters if rules can match the same requests. Split by domain/module for a testable structure.

### 5.4. RouterFunction is a Spring bean, not an annotated controller

A bean:

```java
@Configuration
class Routes {
    @Bean
    RouterFunction<ServerResponse> router(BookHandler handler) {
        return route()
                .GET("/fn/books", handler::listBooks)
                .build();
    }
}
```

This is a snippet with `BookHandler` and static-imported `route()`. Spring MVC auto-detects the router bean. You do not need to put `@RestController` on the handler function; the handler is a plain Spring bean/service or lambda, and Spring IoC still performs injection as usual.

## 6. WebMvc.fn Filters: before, after, and filter

Functional routes have the ability to attach filters at the router layer. Distinguish them from **Servlet Filters** and the **Spring Security filter chain**.

### 6.1. before: transforming the request passed to the handler

```java
RouterFunction<ServerResponse> router = route()
        .GET("/fn/hello", handler::hello)
        .before(request -> ServerRequest.from(request)
                .header("X-Internal-Marker", "functional")
                .build())
        .build();
```

This is a snippet with an existing `handler`. `before` can build a new `ServerRequest` wrapper so route handlers see enriched request metadata. Do not treat it as an authentication solution: clients can still send headers themselves; auth must rely on Spring Security/credentials and trust rules.

### 6.2. after: observing or modifying the response

`after` receives `(request, response)` and returns a `ServerResponse`. Example:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/fn/hello", handler::hello)
        .after((request, response) -> {
            auditService.record(
                    request.path(), response.statusCode());
            return response;
        })
        .build();
```

This is a snippet with a hypothetical `auditService`. If you need to add a header to the response, you can use the response builder/copy API per the Javadoc and test compatibility with the body/commit status. Because the response contract is immutable, do not try to mutate properties directly the way mutable annotated `HttpServletResponse` works if your code does not manage the lifecycle.

### 6.3. filter: wrapping the handler and potentially short-circuiting

`HandlerFilterFunction` receives the request and the `next` handler. A filter can call `next.handle(request)` or block:

```java
RouterFunction<ServerResponse> router = route()
        .GET("/fn/hello", handler::hello)
        .filter((request, next) -> {
            if ("true".equals(
                    request.headers().firstHeader("X-Demo-Block"))) {
                return ServerResponse.status(HttpStatus.FORBIDDEN)
                        .body("blocked");
            }
            return next.handle(request);
        })
        .build();
```

This is a snippet that only uses a **simulated header to learn short-circuiting**, and must **never be used as an actual authorization check**. A client can send or omit that header at will. In the full demo, this filter will help a test demonstrate that a functional filter applies only to its functional route group.

### 6.4. Nested filter scope

Filters placed on the root builder affect routes created by that builder; filters on a nested builder apply only to nested routes and do not automatically leak to sibling/parent routes outside that scope. This differs from Servlet Filters configured by URL mappings.

**Do not confuse the three layers:**

| Layer | Interception Point | When to Use |
| --- | --- | --- |
| Servlet `Filter` | Before DispatcherServlet; can apply to all endpoints, static routes, and annotations by mapping | Security filter chain, correlation ID, servlet-level concerns |
| `HandlerInterceptor` / `WebMvcConfigurer` | MVC handler lifecycle, by mapping and execution flow | MVC cross-cutting behavior; verify compatibility with functional dispatch |
| WebMvc.fn `HandlerFilterFunction` | Wraps a functional `HandlerFunction` already matched by a route | Per-router logging, response adaptations, routing policies |

In particular, **Spring Security** should be configured at the security filter chain/path policies; do not replace it with a WebMvc.fn header-check filter or rely on arbitrary filter ordering. Exceptions from functional handlers also need to be handled appropriately in the MVC/global/error path — do not infer that every `@ControllerAdvice`/`@ExceptionHandler` for annotated controllers will behave identically for functional endpoints; use router filters or separately tested error handling.

## 7. JSON Body, Validation, and Exception Handling

### 7.1. With an annotated controller

```java
@PostMapping("/ann/books")
public ResponseEntity<Book> create(
        @Valid @RequestBody NewBook input) {
    Book book = service.create(input);
    return ResponseEntity
            .created(URI.create("/ann/books/" + book.id()))
            .body(book);
}
```

This is a snippet with undefined `NewBook`/`service`. Spring MVC resolves `@RequestBody` via `HttpMessageConverter`, `@Valid` triggers Bean Validation when a validator is present, and if there is no `BindingResult` to capture errors, it can raise `MethodArgumentNotValidException`. The annotated pipeline integrates quite a bit of annotation metadata automatically.

### 7.2. With WebMvc.fn

```java
public ServerResponse createBook(ServerRequest request)
        throws Exception {
    NewBook input = request.body(NewBook.class);

    var errors = validator.validate(input);
    if (!errors.isEmpty()) {
        return ServerResponse.badRequest()
                .body(new ApiError("invalid_title"));
    }
    Book book = service.create(input);
    return ServerResponse.created(
            URI.create("/fn/books/" + book.id()))
            .body(book);
}
```

This is a snippet with injected `validator`/`service` and the record classes in section 10. `ServerRequest.body(NewBook.class)` uses a converter to read JSON; `@NotBlank` annotations on the DTO can still be checked by the validator, but **you must explicitly invoke `validator.validate(input)`** in the functional handler or design an appropriate validation binder/filter. Do not expect putting `@Valid` on a `HandlerFunction.handle(ServerRequest)` method parameter to automatically work like annotated controller method argument resolution.

### 7.3. Malformed JSON errors are not the same as validation errors

- **Malformed JSON:** the converter cannot deserialize it and may throw an exception before `validator.validate`.
- **Invalid DTO field:** JSON parsing succeeds and Bean Validation detects a constraint violation.
- **Missing path ID/non-numeric ID:** the functional handler parses `request.pathVariable`; you must define 400 or 404.
- **Unsupported media type:** the `contentType` predicate can cause the route not to match, so **do not assume** the response will match annotated `@PostMapping(consumes=...)`.
- **Unauthorized:** the auth/filter chain must check permissions, not just validation/serialization.

If the API requires every error to return RFC 9457 `ProblemDetail` or a consistent JSON error schema, build handlers/advice/filters with full coverage and test every path; do not promise that migrating from annotated to functional preserves all exception mappings.

## 8. Does WebMvc.fn Mean Non-Blocking or Reactive?

**No.** The Servlet `ServerRequest` class has a `body(Class)` method that reads the body through MVC converters; a handler can call synchronous JDBC/JPA or a blocking REST client. Simply having lambda route syntax does not make I/O asynchronous:

```java
HandlerFunction<ServerResponse> slow = request -> {
    Book book = blockingRepository.findById(42);
    return ServerResponse.ok().body(book);
};
```

This is an illustrative snippet; `blockingRepository` is undefined. While `findById` waits, the Servlet thread can be held just like in a normal synchronous controller. Functional **WebMvc.fn** still runs on Servlet MVC.

Compared to **WebFlux.fn**:

| Characteristic | WebMvc.fn | WebFlux.fn |
| --- | --- | --- |
| Package | `org.springframework.web.servlet.function` | `org.springframework.web.reactive.function.server` |
| Request | Servlet `ServerRequest` | Reactive `ServerRequest` |
| Response | Servlet `ServerResponse` (object) | Reactive `Mono<ServerResponse>` |
| Body object | `ServerResponse.ok().body(book)` | `ServerResponse.ok().bodyValue(book)` / publishers |
| Routing | Servlet `RouterFunction` | Reactive `RouterFunction` |
| Runtime | DispatcherServlet / Servlet stack | DispatcherHandler / reactive stack |
| I/O behavior | Synchronous/blocking code can run directly | Designed reactive, though blocking dependencies can still block the event loop |
| Testing | MockMvc | WebTestClient and reactive testing tools |
| Use case | Functional style with existing Spring MVC | End-to-end reactive pipelines when I/O supports it |

**Do not accidentally import classes by matching short names.** Both have `ServerRequest`, `ServerResponse`, and `RouterFunction`, but their packages, subtypes, and methods differ. For a Spring Boot app that already has `spring-boot-starter-web`, use WebMvc.fn without adding `spring-boot-starter-webflux` just to get router APIs.

## 9. When to Choose Functional Routes vs. Keeping Annotated Controllers?

| Criterion | Annotated controllers | WebMvc.fn |
| --- | --- | --- |
| Routing style | `@GetMapping`, `@PostMapping` on methods | `route().GET(...).POST(...)` DSL |
| Path/query binding | `@PathVariable` / `@RequestParam` auto-resolve | Explicit `request.pathVariable` / `request.param` |
| JSON request | `@RequestBody Dto` | `request.body(Dto.class)` |
| Bean Validation | `@Valid` and MVC argument resolution | Explicit validator/binding by design |
| HTTP response | `ResponseEntity`, DTO, view name | `ServerResponse` builder |
| Path grouping | `@RequestMapping` at type-level | `path()`/`nest()` |
| Route precedence | Mapping specificity comparison | **Route declaration order** |
| Cross-cutting | Servlet filters, interceptors, advice | Servlet filters + router before/after/filter; explicit error policy |
| API docs generation | Many OpenAPI tools understand annotations better | May require dedicated tooling/integration, depending on version |
| Kotlin DSL / Java lambdas | Annotations can be used on Kotlin/Java classes | Convenient functional composition, Kotlin router DSL |
| Same project | Yes | Yes, test overlapping paths |
| Non-blocking | Not automatic | **Not automatic** |

### When WebMvc.fn is useful

- Building a small API module with few handlers, wanting a clear route tree and functional composition.
- Writing API gateways/facades with many custom predicates where routing paths need detailed testing.
- Wanting to keep business handlers as plain Spring beans and centralize routing in a configuration class.
- Systems that lean heavily on DSL/functions and prefer separating the route table from logic.
- Reusing functional filters per endpoint group.

### When annotations are usually a better fit

- Large controller-based projects with existing conventions, validations, `@ControllerAdvice`, annotations, and OpenAPI tooling.
- Many DTOs, form validation, binding/cookies/multipart/model attributes needing automatic method argument mapping.
- Teams wanting code easily readable with `@GetMapping`, `@PreAuthorize`, `@Valid`, and familiar IDE tooling.
- Migrating to functional would increase manual parsing/validation/error-handling code without clear benefit.

**There is no requirement to migrate an entire application.** Both models can coexist; just keep mapping paths from overlapping and test security/exception/CORS behavior.

## 10. Runnable Project: Same API with WebMvc.fn and @RestController

We create a Spring Boot application with:
- Functional endpoints under `/fn/books` and `/fn/search`.
- Equivalent annotated endpoints under `/ann/books`.
- An in-memory book store service, using `AtomicLong` to generate IDs and `ConcurrentHashMap` to store entries.
- JSON request body `{"title":"Spring MVC"}` with Jakarta `@NotBlank`.
- Functional validation where the handler explicitly calls `jakarta.validation.Validator`.
- Annotated validation via `@Valid @RequestBody`.
- A simulated functional filter blocking requests when `X-Demo-Block: true`, solely to understand short-circuiting.
- A functional route `/fn/books/latest` placed **before** `/fn/books/{id}` to demonstrate route order.

The result is an application that can be built/tested with Java 17+ and Maven. There is no database, session, or authentication; the APIs are strictly for learning.

### 10.1. Directory Tree

```text
webmvc-fn-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/example/webfn/
    │       ├── WebFnApplication.java
    │       ├── Book.java
    │       ├── NewBook.java
    │       ├── ApiError.java
    │       ├── BookStore.java
    │       ├── BookHandler.java
    │       ├── FunctionalRoutes.java
    │       └── AnnotatedBookController.java
    └── test/
        └── java/example/webfn/
            └── WebFnTest.java
```

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>webmvc-fn-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

**`src/main/java/example/webfn/WebFnApplication.java`**

```java
package example.webfn;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFnApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFnApplication.class, args);
    }
}
```

### 10.2. Shared DTOs

**`src/main/java/example/webfn/Book.java`**

```java
package example.webfn;

public record Book(long id, String title) {}
```

**`src/main/java/example/webfn/NewBook.java`**

```java
package example.webfn;

import jakarta.validation.constraints.NotBlank;

public record NewBook(@NotBlank String title) {}
```

**`src/main/java/example/webfn/ApiError.java`**

```java
package example.webfn;

public record ApiError(String code) {}
```

Java 17 `record` provides constructors/accessors, and Jackson supports deserializing/serializing them in Boot 3.3. `@NotBlank` from Jakarta Validation ensures title is not null/empty/whitespace when **the validator is invoked**. A DTO record does not self-validate simply because it has an annotation; validation must be triggered in the respective pipeline.

### 10.3. Data Storage Service, Independent of Routing Style

**`src/main/java/example/webfn/BookStore.java`**

```java
package example.webfn;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class BookStore {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentHashMap<Long, Book> books =
            new ConcurrentHashMap<>();

    public Book create(String title) {
        long id = sequence.incrementAndGet();
        Book book = new Book(id, title.strip());
        books.put(id, book);
        return book;
    }

    public Optional<Book> find(long id) {
        return Optional.ofNullable(books.get(id));
    }

    public List<Book> all() {
        List<Book> result = new ArrayList<>(books.values());
        result.sort(Comparator.comparingLong(Book::id));
        return result;
    }

    public Optional<Book> latest() {
        return all().stream()
                .max(Comparator.comparingLong(Book::id));
    }

    public List<Book> search(String query) {
        String term = query.strip().toLowerCase(
                java.util.Locale.ROOT);
        return all().stream()
                .filter(book -> book.title().toLowerCase(
                        java.util.Locale.ROOT).contains(term))
                .toList();
    }
}
```

`ConcurrentHashMap` and `AtomicLong` only demonstrate handling multiple requests in RAM. `latest()` and `search()` scan the data for simplicity, not an optimal design for millions of records. Restarting the app loses state; there are no transactions/database.

### 10.4. Functional Handler: ServerRequest → ServerResponse

**`src/main/java/example/webfn/BookHandler.java`**

```java
package example.webfn;

import java.net.URI;

import jakarta.validation.Validator;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.function.ServerRequest;
import org.springframework.web.servlet.function.ServerResponse;

@Component
public class BookHandler {

    private final BookStore store;
    private final Validator validator;

    public BookHandler(BookStore store, Validator validator) {
        this.store = store;
        this.validator = validator;
    }

    public ServerResponse listBooks(ServerRequest request)
            throws Exception {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.all());
    }

    public ServerResponse getBook(ServerRequest request)
            throws Exception {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException invalid) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("bad_id"));
        }

        Book book = store.find(id).orElse(null);
        if (book == null) {
            return ServerResponse.notFound().build();
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse latest(ServerRequest request)
            throws Exception {
        Book book = store.latest().orElse(null);
        if (book == null) {
            return ServerResponse.notFound().build();
        }
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }

    public ServerResponse search(ServerRequest request)
            throws Exception {
        String q = request.param("q").orElse("");

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(store.search(q));
    }

    public ServerResponse createBook(ServerRequest request)
            throws Exception {
        NewBook input = request.body(NewBook.class);

        if (input == null ||
                !validator.validate(input).isEmpty()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(new ApiError("invalid_title"));
        }

        Book book = store.create(input.title());
        URI location = URI.create("/fn/books/" + book.id());

        return ServerResponse.created(location)
                .contentType(MediaType.APPLICATION_JSON)
                .body(book);
    }
}
```

**Key Points:**

1. `@Component` creates the handler bean, not `@RestController`.
2. There is no `@GetMapping` on the class; URI routing lives in `FunctionalRoutes`.
3. `request.body(NewBook.class)` invokes the JSON converter for **the entire HTTP body** (not multipart), then `validator.validate(input)` runs Bean Validation explicitly.
4. `request.pathVariable("id")` returns a String. The handler parses it itself and returns `400` if it is not a number; unlike annotated `@PathVariable long id` which MVC converts before method invocation.
5. `ServerResponse.notFound().build()` creates a 404 with no body; `ServerResponse.created(location)` creates a 201 and Location header.
6. `search` uses `Optional` from `request.param("q")` to set an empty default; the demo returns all items if the query is empty.
7. Methods return ServerResponse and declare `throws Exception` because `request.body(...)`/response building have checked exceptions under the Servlet API.
8. Validation does not replace authentication, authorization, or input length/complexity limits. In a real app, limit title length, request body size, result count, and check permissions.
9. Store/handler dependency injection works like an annotated controller; functional style does not force you to write all logic inside route lambdas.

### 10.5. RouterFunction Bean, Path Precedence, and Filter

**`src/main/java/example/webfn/FunctionalRoutes.java`**

```java
package example.webfn;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.servlet.function.RouterFunction;
import org.springframework.web.servlet.function.ServerResponse;

import static org.springframework.web.servlet.function.RequestPredicates.contentType;
import static org.springframework.web.servlet.function.RouterFunctions.route;

@Configuration
public class FunctionalRoutes {

    @Bean
    RouterFunction<ServerResponse> bookRoutes(BookHandler handler) {
        return route()
                // Order matters: specific before path variable.
                .GET("/fn/books/latest", handler::latest)
                .GET("/fn/books/{id}", handler::getBook)
                .GET("/fn/books", handler::listBooks)
                .GET("/fn/search", handler::search)
                .POST("/fn/books",
                        contentType(MediaType.APPLICATION_JSON),
                        handler::createBook)
                .filter((request, next) -> {
                    // Demo filter, NOT a security control.
                    String blocked = request.headers()
                            .firstHeader("X-Demo-Block");
                    if ("true".equalsIgnoreCase(blocked)) {
                        return ServerResponse
                                .status(HttpStatus.FORBIDDEN)
                                .contentType(MediaType.APPLICATION_JSON)
                                .body(new ApiError("demo_blocked"));
                    }
                    return next.handle(request);
                })
                .build();
    }
}
```

Only one `RouterFunction<ServerResponse>` bean is in the example. The router is auto-detected by Spring MVC; there is no need to write `@RestController` for functional routes.

**Verified route order:** `/fn/books/latest` is placed before `/fn/books/{id}`. If the order is reversed, the literal `latest` can be passed to `getBook` and receive `bad_id` instead of selecting latest.

**POST constraint:** The `POST /fn/books` route uses the `contentType(APPLICATION_JSON)` predicate. The JSON body is decoded by `ServerRequest.body(NewBook.class)`. If Content-Type does not match, the route may fail to match before the handler runs, and the actual status may differ from annotated `consumes`. Do not promise status 415 in every case; the API contract needs separate testing.

**Functional filter:** If the request sends `X-Demo-Block: true`, the router returns `403` before the handler runs. This is merely a marker to test short-circuiting and filter scope, **with no security value**. For a real API, use Spring Security with authentication/authorization rules; do not treat arbitrary client-controlled headers as permissions.

### 10.6. Annotated Controller Sharing BookStore

**`src/main/java/example/webfn/AnnotatedBookController.java`**

```java
package example.webfn;

import java.net.URI;
import java.util.List;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/ann/books")
public class AnnotatedBookController {

    private final BookStore store;

    public AnnotatedBookController(BookStore store) {
        this.store = store;
    }

    @GetMapping
    public List<Book> list() {
        return store.all();
    }

    @GetMapping("/latest")
    public ResponseEntity<Book> latest() {
        return store.latest()
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @GetMapping("/{id}")
    public ResponseEntity<Book> get(@PathVariable long id) {
        return store.find(id)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }

    @PostMapping
    public ResponseEntity<Book> create(
            @Valid @RequestBody NewBook input) {
        Book book = store.create(input.title());
        return ResponseEntity.created(
                URI.create("/ann/books/" + book.id()))
                .body(book);
    }
}
```

Comparison points:

- `@RestController` + `@RequestMapping` group routes at the class level.
- `@GetMapping("/{id}")` + `@PathVariable long id` automatically convert String to long; malformed IDs are handled by Spring argument resolution.
- `@Valid @RequestBody NewBook` integrates validation according to the annotated method model, rather than invoking a validator in the method body.
- `ResponseEntity<Book>` holds status/headers/body, while functional uses `ServerResponse`.
- The two path groups `/ann/books` and `/fn/books` **do not overlap**, so they coexist cleanly in one application.
- Sharing `BookStore` proves business logic does not need to be tied to the routing style. If created via `/ann/books`, it can be read via `/fn/books/{id}` because they use the same store.

### 10.7. Running the Project and Inspecting HTTP Responses

Inside the `webmvc-fn-demo` directory with Java 17+ and Maven:

```bash
mvn test
mvn spring-boot:run
```

These are two sequential commands, not a single concurrent command. After Boot starts on the default port `8080`:

**Create a book via the functional route:**

```bash
curl -i -X POST \
  'http://localhost:8080/fn/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Spring MVC"}'
```

HTTP response for the first creation on a freshly started server:

```http
HTTP/1.1 201
Location: /fn/books/1
Content-Type: application/json

{"id":1,"title":"Spring MVC"}
```

`Location` is a valid relative URI reference for the newly created resource, using a server-owned ID. In production, if the client contract requires an absolute URL, use a trusted origin/context path (e.g., `ServletUriComponentsBuilder` with a forwarded-header trust policy); do not trust raw Host headers from the Internet.

**Fetch the resource:**

```bash
curl -i 'http://localhost:8080/fn/books/1'
```

When book ID 1 already exists, body:

```json
{"id":1,"title":"Spring MVC"}
```

**List:**

```bash
curl -i 'http://localhost:8080/fn/books'
```

Example:

```json
[{"id":1,"title":"Spring MVC"}]
```

**Search via query param:**

```bash
curl -G -i 'http://localhost:8080/fn/search' \
  --data-urlencode 'q=Spring'
```

Expected JSON array containing books with the word `Spring`, case-insensitive according to how `BookStore.search` is written.

**Annotated API creating another book:**

```bash
curl -i -X POST \
  'http://localhost:8080/ann/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"Annotated MVC"}'
```

Expected response for the second creation:

```http
HTTP/1.1 201
Location: /ann/books/2

{"id":2,"title":"Annotated MVC"}
```

If tests were already run in the same JVM or other books were created earlier, the ID may differ. What needs verification is status 201, `Location` pointing to the right resource, and matching body ID.

**Latest functional route:**

```bash
curl -i 'http://localhost:8080/fn/books/latest'
```

The body contains the book with the highest ID at the time of processing. If the `/{id}` route was declared before `/latest`, there is a risk the handler receives `"latest"` as `id` and returns 400; a test must catch that.

**Validation error:**

```bash
curl -i -X POST \
  'http://localhost:8080/fn/books' \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}'
```

The functional handler returns:

```http
HTTP/1.1 400
Content-Type: application/json

{"code":"invalid_title"}
```

The annotated endpoint with the same body can also return `400` from the Bean Validation pipeline, but **Boot's default error body/schema does not necessarily match** `{"code":"invalid_title"}`. Do not write clients that depend on an exact body unless a shared error contract has been defined.

**Short-circuit functional filter:**

```bash
curl -i 'http://localhost:8080/fn/books' \
  -H 'X-Demo-Block: true'
```

Expected:

```http
HTTP/1.1 403
Content-Type: application/json

{"code":"demo_blocked"}
```

The `X-Demo-Block` header is strictly for the demonstration filter. If sent to `/ann/books`, this functional filter **does not apply** to the annotated route; an outer security filter chain has independent rules if added later.

## 11. MockMvc Tests: Coexisting Functional and Annotated Endpoints

**`src/test/java/example/webfn/WebFnTest.java`**

```java
package example.webfn;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebFnTest {

    @Autowired MockMvc mvc;

    @Test
    void functionalCreateAndRead() throws Exception {
        MvcResult created = mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Function Book\"}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.title").value("Function Book"))
                .andReturn();

        String uri = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(uri);
        assertTrue(uri.matches("/fn/books/[1-9][0-9]*"));

        mvc.perform(get(uri))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Function Book"));
    }

    @Test
    void annotatedCreateAndRead() throws Exception {
        MvcResult created = mvc.perform(post("/ann/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Annotation Book\"}"))
                .andExpect(status().isCreated())
                .andReturn();

        String uri = created.getResponse()
                .getHeader(HttpHeaders.LOCATION);
        assertNotNull(uri);
        assertTrue(uri.matches("/ann/books/[1-9][0-9]*"));

        mvc.perform(get(uri))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.title").value("Annotation Book"));
    }

    @Test
    void functionalHandlerValidatesDtoExplicitly()
            throws Exception {
        mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest())
           .andExpect(jsonPath("$.code").value("invalid_title"));
    }

    @Test
    void annotatedControllerUsesBeanValidation()
            throws Exception {
        mvc.perform(post("/ann/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"   \"}"))
           .andExpect(status().isBadRequest());
    }

    @Test
    void specificFunctionalRouteIsNotShadowed()
            throws Exception {
        mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Latest Candidate\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/fn/books/latest"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$.id").isNumber());
    }

    @Test
    void functionalFilterCanShortCircuit()
            throws Exception {
        mvc.perform(get("/fn/books")
                        .header("X-Demo-Block", "true"))
           .andExpect(status().isForbidden())
           .andExpect(jsonPath("$.code").value("demo_blocked"));

        mvc.perform(get("/ann/books")
                        .header("X-Demo-Block", "true"))
           .andExpect(status().isOk());
    }

    @Test
    void functionalSearchReadsQueryParameter()
            throws Exception {
        mvc.perform(post("/fn/books")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"Spring Searchable\"}"))
           .andExpect(status().isCreated());

        mvc.perform(get("/fn/search").param("q", "Spring Searchable"))
           .andExpect(status().isOk())
           .andExpect(jsonPath("$[0].title")
                    .value("Spring Searchable"));
    }

    @Test
    void missingBookReturns404ForBothStyles()
            throws Exception {
        mvc.perform(get("/fn/books/99999999"))
           .andExpect(status().isNotFound());
        mvc.perform(get("/ann/books/99999999"))
           .andExpect(status().isNotFound());
    }
}
```

Run:

```bash
mvn test
```

The class declares **8 test methods**. If all tests pass, Maven exits with code `0` and shows a summary similar to `Tests run: 8, Failures: 0, Errors: 0, Skipped: 0`. This content was designed/statically checked for Java 17 + Spring Boot 3.3.5, **and does not claim Maven was executed during authoring**.

### Test Characteristics

- Uses `@SpringBootTest` + `@AutoConfigureMockMvc` to go through the MVC infrastructure rather than calling Java handlers directly.
- Book-creation tests read the actual `Location` header, avoiding hardcoded ID = 1 or reliance on test execution order.
- Functional validation asserts the `invalid_title` body because the handler constructs the response explicitly.
- Annotated validation only asserts status `400` because the default error body shape depends on Boot/error handling.
- The filter test shows that scope applies only to functional routes created by the builder, not automatically to annotated controllers.
- The route order test ensures literal URL `/latest` is not captured first by `/{id}`.
- The shared `BookStore` is stateful; the search test uses a specific phrase so it does not depend on list size if other books exist.
- MockMvc does not simulate all ingress/proxy behavior, HTTP timeouts, or the full production security filter chain. Additional integration tests are needed when adding authentication, CORS, forwarded headers, or file upload/streaming.

## 12. Validation and Exception Policy for Production Systems

In the annotated style, the framework drives many steps automatically: type conversion, method argument validation, `@Valid`, `BindingResult`, method return values, and `@ControllerAdvice`. The functional style keeps the MVC infrastructure, but **the handler bears clearer responsibility** for input parsing and its error behavior.

### 12.1. Using Jakarta Validator

For the record:

```java
public record NewBook(
        @NotBlank
        @Size(max = 120)
        String title) {}
```

If you want a unified error body in a functional handler:

```java
Set<ConstraintViolation<NewBook>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .body(new ApiError("invalid_book"));
}
```

This is a snippet requiring imports `jakarta.validation.Validator`, `ConstraintViolation`, `java.util.Set`, and the existing record. Use **stable machine-readable codes** for clients; avoid returning raw rejected values or exception messages containing PII. For annotated controllers, you can use `@RestControllerAdvice` and Bean Validation exception handlers to unify errors into the same schema, but verify with real tests when both route models coexist.

### 12.2. Type conversion vs. business validation

Annotated `@PathVariable long id` is handled by the MVC conversion framework if the ID is not numeric. Functional `request.pathVariable("id")` receives a String and `Long.parseLong` resides inside the handler. Both cases can end in HTTP 400, yet **the exception class, interception point, and error body differ**.

Do not catch broad `Exception` in a functional filter and always return 400 — doing so can mask server/DB bugs and turn 5xx into 4xx. Distinguish bad input, not found, authorization, conflict, downstream failure, and timeout.

### 12.3. Transactions, DI, and tests do not disappear

A functional handler class still supports constructor injection, can call Spring `@Service`, `@Transactional` on services, and Spring Security auth context like any controller. Do not put transactions on every functional lambda or call persistence directly from route config. Business logic should live in services for easy sharing, reuse, and testing.

## 13. Security: Servlet Filters and Functional Filters Are Not the Same

When an application uses Spring Security:

```text
HTTP Request
  |
  v
Spring Security FilterChain
  - authentication
  - authorization
  - CSRF (when applicable)
  - session/cookie protection
  |
  v
DispatcherServlet
  |
  +--> Annotated controllers
  |
  +--> WebMvc.fn RouterFunction
          |
          +--> HandlerFilterFunction (module policies)
          |
          +--> HandlerFunction
```

**Do not place all security in a functional filter**: if an annotated endpoint lies outside the router, that filter will not run; if there are static resources/admin endpoints, they may also bypass the filter. Use Spring Security path authorization and method/service-level checks for business permissions.

### CORS

WebMvc.fn has CORS support via Servlet `CorsFilter`; do not assume `@CrossOrigin` on an annotated controller automatically applies to other functional routes. CORS can be configured at the Servlet filter/Spring Security layer according to topology. CORS **is not authentication**; it only restricts browser cross-origin reads per HTTP policy; non-browser clients can still send requests.

### CSRF

With cookie/session authentication, a POST functional route still carries the same CSRF risk as an annotated `@PostMapping`. The Spring Security CSRF policy lives in the security filter chain, independent of whether a route uses annotations or lambdas. Do not disable CSRF just to make a `curl` demo pass when adding real login.

### Host and Location headers

`ServerResponse.created(URI)` generates Location, yet the URI must still come from a trusted source. If using request host/forwarded headers to build absolute URLs, the reverse proxy must strip/sanitize untrusted headers to prevent host-header poisoning/phishing. The demo uses relative `/fn/books/{id}` deliberately to avoid trusting arbitrary hosts.

## 14. CORS, Content Negotiation, Route Predicates, and Errors

When an annotated controller declares:

```java
@GetMapping(path = "/ann/books",
            produces = MediaType.APPLICATION_JSON_VALUE)
```

Spring uses the mapping conditions and content negotiation of the annotated infrastructure. A functional equivalent might be:

```java
.GET("/fn/books",
        accept(MediaType.APPLICATION_JSON),
        handler::listBooks)
```

However, requests that do not match the predicate **do not necessarily return the same status** as an annotated mapping, even though both use DispatcherServlet. When building an API that needs a clear 404/405/406/415 contract, test every combination:

- Path exists, different HTTP method (405 or not matched?).
- `Accept` does not accept JSON.
- Wrong or missing `Content-Type` on POST.
- Malformed JSON body.
- Valid JSON that fails DTO constraints.
- Authorization/CSRF rejection occurring in filters before the router.
- Conditional requests `If-None-Match`, ETag, caching/Range.
- OPTIONS/preflight CORS, HEAD, and trailing slash in paths.

Do not take passing tests on an annotated controller as "proof" that the functional router behaves 100% identically. The application can establish an error contract using exceptions/filters/advice/custom mappings if consistency is required.

## 15. Practical Application: Package Organization and Refactoring

A maintainable structure for functional MVC:

```text
example.book/
├── api/
│   ├── BookRoutes.java       # RouterFunction beans, predicates, filter composition
│   ├── BookHandler.java      # Request -> Response, validation/HTTP errors
│   ├── NewBook.java          # Inbound DTO
│   └── BookView.java         # Outbound DTO if needed
├── application/
│   └── BookService.java      # Business rules
├── domain/
│   └── Book.java
└── infrastructure/
    └── BookRepository.java
```

Route config should be **short**: path grouping, method predicates, filter configuration. Do not stuff hundreds of lines of JDBC, file I/O, or auth policy into a long lambda inside `@Bean RouterFunction`. The handler class should receive dependencies via constructor injection and delegate to the service; validation and response contracts can be extracted into tested helpers.

With annotated controllers, the package structure is similar, though `BookController.java` usually both declares paths and performs HTTP adaptation via annotations. Functional style cleanly separates the route table, though it can create more Java files for a small API; that is a trade-off, not an absolute pro/con.

### Do not share a mutable RouterFunction builder across requests

`RouterFunctions.route()` provides a builder used during bean initialization; `build()` produces the RouterFunction. Do not store a mutable builder in a singleton and mutate the route graph per request. Dynamic routing at runtime requires a dedicated architecture and synchronization. Also do not build a new RouterFunction on every HTTP request; declare beans at startup.

### OpenAPI and documentation

Many OpenAPI generators/springdoc integrations detect annotated endpoints and `@Operation` metadata more easily. Functional routes may also be supported depending on tool/version or require explicit route documentation; verify the specific tool rather than assuming. For a large migration, test OpenAPI output along with client SDK contracts and security schemes before switching.

## 16. Notable Use Cases and Limitations

### 16.1. Gateway/facade with multiple predicates

A facade can have routes based on path, Accept, Content-Type, and custom headers. Functional route composition makes predicates/traversal order clear. However, if it makes blocking HTTP calls, the router DSL still runs synchronously — design downstream timeouts, connection pooling, cancellation, and circuit breakers.

### 16.2. Static resources

WebMvc.fn supports serving `Resource` via router utilities, fitting some SPA fallback/custom route cases. Avoid writing a catch-all functional route too broadly that shadows `/api/**`, 404s, or security routes. For ordinary static assets, Spring MVC static resource handlers already handle caching, ETag, and byte ranges; choose the simpler appropriate mechanism.

### 16.3. SSE/streaming

Spring MVC has async response APIs, and WebMvc.fn also provides response facilities depending on version. Yet a functional route lambda **does not automatically guarantee** end-to-end non-blocking streaming. To serve SSE to thousands of clients or handle complex backpressure, evaluate MVC vs. WebFlux, network write behavior, executor resource usage, reconnects, and timeouts — this is an architectural choice separate from router style.

### 16.4. API versioning

For `/api/v1` and `/api/v2`, functional route grouping with `path("/api/v1",...)` is convenient. With annotations, use type-level `@RequestMapping("/api/v1")`. Both still require contract tests for version routing and backward compatibility; changing a path prefix alone does not make all models/services/schemas compatible.

## 17. Common Pitfalls

| Symptom | Cause | How to Check |
| --- | --- | --- |
| `RouterFunction` bean has no effect | Wrong type/package declared, bean not scanned, Spring MVC infrastructure not active | Verify `org.springframework.web.servlet.function` and Spring-managed bean |
| Using WebFlux `ServerResponse.bodyValue(...)` | Imported `org.springframework.web.reactive.function.server` by mistake | In WebMvc.fn use `ServerResponse.ok().body(...)` |
| `GET /books/latest` returns `bad_id` | Route `/{id}` comes before `/latest` | Place literal routes first, test ordering |
| `@Valid` does not validate body automatically in functional handler | Only called `request.body(...)` and forgot to validate | Explicitly use Validator/appropriate binding |
| POST JSON returns 404 instead of 415 | `contentType` predicate does not match | Review request predicate semantics and error contract |
| `@ControllerAdvice` does not cover all functional errors | Error handling path differs from annotated argument flow | Test malformed JSON, conversion, uncaught exceptions |
| Does header route filter block annotated controllers? No | Functional filter only applies to its router | Use security Servlet filter chain if app-wide scope is needed |
| CORS preflight blocked | Relied only on `@CrossOrigin` on annotated controller | Configure `CorsFilter`/Security CORS for functional endpoints |
| CSRF POST fails after adding Security | CSRF still applies to session endpoints | Send valid token, do not disable policy arbitrarily |
| Short route but messy business logic | All logic stuffed into lambda | Separate Handler/Service/Repository |
| Functional is no faster than annotated | Same Servlet MVC, blocking I/O stays blocking | Benchmark/measure service/downstream bottlenecks |
| OpenAPI docs missing endpoints | Tool does not detect functional routes by default | Verify docs generator/version/integration |
| Desired Accept header not received | Confused `accept` with `contentType` | Inspect HTTP request and predicates |
| Two groups (annotated/functional) share same URL | Unclear HandlerMapping precedence | Avoid route overlap; test framework-specific order |
| Inconsistent error responses | Validation/errors handled in two different pipelines | Define shared error DTO and tests |
| Route filter writes response without running handler | `next.handle` was not called | Check if short-circuit is intentional or a bug |
| Response Location points to foreign host | Trusted Host/Forwarded from client | Trusted proxy, canonical base URL, or relative URI |
| Returns 201 in JSON but HTTP status 200 | Forgot to use `ServerResponse.created` | Assert actual HTTP status/Location in MockMvc |
| Input DTO contains privilege fields | Mass assignment/over-posting | DTO allowlist, server-side user/tenant auth |
| Tests only call Handler directly, mapping still broken | Did not test DispatcherServlet route predicates | MockMvc + integration tests |

Systematic debugging steps:

1. Confirm the correct `web.servlet.function` namespace and that the router is a Spring-scanned bean.
2. Trace the HTTP request method/path/headers and actual route order.
3. If `latest` fails, check whether a wildcard/variable route comes before or after it.
4. Check `Content-Type` for POST JSON and `Accept` for GET.
5. Verify `request.body(Dto.class)` has a valid converter and data type.
6. Distinguish parse exceptions, validation errors, and handler business errors.
7. Check filter scope, `next.handle(request)` invocation, and the security chain.
8. Test both functional and annotated paths, especially if the app combines both.
9. Behind a reverse proxy, verify forwarded headers, context path, CORS, and Location.
10. Measure real latency/throughput before concluding a routing style change improves performance.

## 18. Production Checklist for WebMvc.fn

1. Choose WebMvc.fn for route composition/maintainability needs, not under the illusion it is non-blocking.
2. All Spring MVC functional classes use `org.springframework.web.servlet.function`.
3. Place specific routes before routes with placeholders/wildcards.
4. Write tests for route collisions and ordering when multiple router beans exist.
5. Use constructor injection for handlers and separate services/repositories.
6. Read bodies via converters; declare Content-Type/Accept expectations accurately.
7. Trigger Bean Validation explicitly in functional handlers.
8. Standardize JSON errors/status/Location and verify with MockMvc.
9. Do not use functional filters as a substitute for the Spring Security filter chain.
10. Test CORS/CSRF/auth/tenant rules from external HTTP calls.
11. Do not trust request Host/Forwarded headers when constructing redirects/absolute URLs.
12. Do not place long blocking business logic on Servlet threads just because the route is a lambda.
13. Check compatibility of OpenAPI/Actuator/tracing tools.
14. When migrating, do not convert everything just to replace annotations — weigh costs and benefits.
15. Include integration tests for proxy/Servlet runtime if production deployment is complex.
16. Do not dynamically create builders/routers per request without a clear requirement.

## 19. Self-Check Exercises

1. How does `RouterFunction` differ from `HandlerFunction`?
2. Which converter mechanism do `ServerRequest.body(MyDto.class)` and `@RequestBody MyDto` share, and where do they differ?
3. Why must `/books/latest` come before `/books/{id}` in the functional route builder?
4. What HTTP status/header does `ServerResponse.created(location)` set?
5. Does `@NotBlank` in a DTO run automatically when a functional handler calls `request.body(...)`?
6. Why does WebMvc.fn run on DispatcherServlet yet is not WebFlux.fn?
7. Which request header does `accept(APPLICATION_JSON)` differ from `contentType(APPLICATION_JSON)` on?
8. How do a functional `filter` and a Servlet `Filter` differ in scope?
9. What happens if a filter does not call `next.handle(request)`?
10. Why can a `HandlerFunction` block a Servlet thread even though it is written as a lambda?
11. When migrating from annotated to functional, what should be tested regarding 400/404/405/406/415?
12. Why should URL overlap between annotated controllers and functional routes be avoided?
13. Can a single Spring `@Service` be used by both handler types?
14. Does WebMvc.fn automatically generate full OpenAPI docs like annotated controllers in every generator?
15. If Spring Security is added, does a functional POST remain subject to the app's CSRF policy?

**Answer hints:** (1) Router selects the handler; handler processes the request into a response. (2) Same MVC converters, but functional reads explicitly whereas annotations use method argument resolution. (3) First-match order. (4) 201 + Location. (5) Not automatic; requires explicit validator/binding. (6) Servlet package/sync pipeline differs from reactive. (7) Accept header vs. Content-Type body header. (8) Router group vs. Servlet/filter chain scope. (9) Short-circuit. (10) Blocking APIs still block. (11) Route predicates, media types, validation, exceptions, and security. (12) Cross-style HandlerMapping precedence cannot be predicted by declaration order. (13) Yes, like the BookStore demo. (14) Depends on tooling. (15) Yes, per security config.

## 20. Official Documentation

- [Spring Framework — Functional Endpoints, Servlet MVC](https://docs.spring.io/spring-framework/reference/web/webmvc-functional.html)
- [Spring Framework 6.1 — RouterFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/RouterFunction.html)
- [Spring Framework 6.1 — RouterFunctions Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/RouterFunctions.html)
- [Spring Framework 6.1 — ServerRequest Javadoc (Servlet)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/ServerRequest.html)
- [Spring Framework 6.1 — ServerResponse Javadoc (Servlet)](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/ServerResponse.html)
- [Spring Framework 6.1 — HandlerFunction Javadoc](https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/web/servlet/function/HandlerFunction.html)
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework — Spring MVC DispatcherServlet](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring MVC Testing with MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)

**Summary:** WebMvc.fn is a functional routing and handling model in **Spring MVC Servlet**, where `RouterFunction`/`RequestPredicate` selects a `HandlerFunction` that receives a `ServerRequest` and returns a `ServerResponse`. It changes how routing/HTTP adaptation is declared, **it does not replace DispatcherServlet or turn blocking I/O into reactive**. The key differences to remember compared to annotated controllers are **route matching order**, **explicit parameter extraction/validation**, **functional filter scope**, and **how error contracts are managed**. Both styles can run side by side, but behavior should be protected with MockMvc tests while keeping security, validation, and business logic cleanly separated.
