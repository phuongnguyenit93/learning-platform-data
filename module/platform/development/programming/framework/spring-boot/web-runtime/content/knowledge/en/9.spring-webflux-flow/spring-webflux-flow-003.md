# Annotated Controllers and RouterFunction Handlers in Spring WebFlux

Spring WebFlux offers **two styles for declaring HTTP endpoints** on top of the same reactive foundation:

1. **Annotated controller:** uses familiar annotations such as `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PathVariable`, and `@RequestBody`. Controller methods can return `Mono`, `Flux`, or other result types supported by the framework.
2. **Functional endpoint (WebFlux.fn):** uses `RouterFunction` to decide which requests match a route, then dispatches the request to a `HandlerFunction`. The handler works with `ServerRequest` and returns `Mono<ServerResponse>`.

These are **two ways to describe routing and request handling**, not two separate servers. Within one Spring Boot WebFlux application, annotated controllers and `RouterFunction`s can coexist. Both pass through WebFlux's reactive infrastructure, sharing codecs, web filters, and framework integrations as configured by the application.

An important distinction right from the start: **WebFlux.fn** in package `org.springframework.web.reactive.function.server` differs from **WebMvc.fn** in package `org.springframework.web.servlet.function`. Their class names look nearly identical, but their handling contracts differ: in WebFlux.fn, a handler returns `Mono<ServerResponse>`, whereas in WebMvc.fn, a Servlet handler typically returns `ServerResponse` directly.

This lesson runs on Java 17+, Spring Boot 3.5.x / Spring Framework 6.2.x. The examples expose a shared business service through two URL families: `/annotated/tasks/**` and `/functional/tasks/**`. This lets you observe the exact differences without changing business logic.

## 1. Context: How Does WebFlux Process a Request?

A Spring Boot application with `spring-boot-starter-webflux` and without `spring-boot-starter-web` typically starts a reactive web server, defaulting to Reactor Netty. Incoming requests pass through the `WebFilter` chain and WebFlux's `DispatcherHandler`; the framework then selects a handler and writes the response using appropriate result handlers and HTTP message codecs.

High-level diagram:

~~~text
HTTP client
    |
    v
Reactive HTTP server (e.g., Reactor Netty)
    |
    v
WebFilter chain
    |
    v
DispatcherHandler
    |
    +--- RequestMappingHandlerMapping
    |            |
    |            v
    |      @RestController method
    |
    +--- RouterFunctionMapping
                 |
                 v
           HandlerFunction
                 |
                 v
       Mono<ServerResponse>
    |
    v
HTTP response encoding / writing
~~~

Key components to remember:

- **DispatcherHandler** is Spring WebFlux's request dispatcher, distinct from Spring MVC's `DispatcherServlet`.
- **RequestMappingHandlerMapping** discovers endpoints declared with annotations.
- **RouterFunctionMapping** detects `RouterFunction` beans and finds matching routes.
- **HandlerFunctionAdapter** invokes the functional endpoint's `HandlerFunction`.
- **ServerResponseResultHandler** writes WebFlux.fn's `ServerResponse`.
- **HttpMessageReader/HttpMessageWriter** decode and encode bodies; both styles use WebFlux infrastructure rather than forcing you to parse JSON manually.

The reactive model allows expressing asynchronous results with publishers, but **does not guarantee non-blocking execution if code inside uses synchronous JDBC, `Thread.sleep`, blocking HTTP clients, or blocking file I/O**. Choosing a routing style alone does not determine performance or non-blocking behavior.

## 2. Annotated Controller: A Mental Model Close to Spring MVC

A WebFlux controller can still look very familiar:

~~~java
@RestController
@RequestMapping("/api/tasks")
public class TaskController {

    private final TaskService service;

    public TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Task> get(@PathVariable long id) {
        return service.findById(id);
    }

    @GetMapping
    public Flux<Task> list() {
        return service.findAll();
    }
}
~~~

This is an illustrative snippet without full imports and related classes. It shows:

- `@RestController` combines `@Controller` and `@ResponseBody`, so return values are written to the HTTP response.
- `@RequestMapping` sets a shared prefix.
- `@GetMapping`, `@PostMapping`, and similar annotations declare method/path/produces/consumes.
- `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody`, etc., let the framework bind parameters.
- `Mono<T>` represents at most one value, or an error/empty completion.
- `Flux<T>` represents a stream of multiple values.

WebFlux supports a wide variety of method signatures and reactive return types. Notably, `@RequestBody` can also be declared as `Mono<Dto>` so receiving and decoding the body integrates with the reactive pipeline.

**404 note:** if a controller simply returns `Mono.empty()` from a GET method without explicitly setting a status, do not assume Spring WebFlux always turns an empty result into HTTP 404. In real APIs, map not-found cases to `ResponseEntity.notFound()` or an appropriate business error.

## 3. Functional Endpoint: RouterFunction and HandlerFunction

WebFlux.fn separates HTTP route declarations from handling logic:

~~~java
@Bean
RouterFunction<ServerResponse> taskRoutes(TaskHandler handler) {
    return RouterFunctions.route()
            .GET("/api/tasks", handler::list)
            .GET("/api/tasks/{id}", handler::getById)
            .POST("/api/tasks", handler::create)
            .build();
}
~~~

A handler function takes a `ServerRequest` and returns `Mono<ServerResponse>`:

~~~java
public Mono<ServerResponse> getById(ServerRequest request) {
    long id = Long.parseLong(request.pathVariable("id"));

    return service.findById(id)
            .flatMap(task -> ServerResponse.ok().bodyValue(task))
            .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

These two snippets illustrate the structure and are not used verbatim in the full project later, where URL paths are adjusted so the two styles do not collide.

Component roles:

- **RequestPredicate** describes matching criteria for HTTP method, path, `Accept`, `Content-Type`, query params, etc. Predicates can be combined with `and`, `or`, and `negate`.
- **RouterFunction<ServerResponse>** takes a request and selects a matching handler. The `RouterFunctions.route()` builder helps organize routes cleanly.
- **HandlerFunction<ServerResponse>** represents a function that handles a `ServerRequest` and returns a publisher of `ServerResponse`.
- **ServerRequest** exposes path variables, headers, query parameters, cookies, and the request body—for example, `request.bodyToMono(NewTask.class)`.
- **ServerResponse** exposes builders for status, headers, content type, and body: `ok()`, `created(...)`, `badRequest()`, `notFound()`, `bodyValue(...)`, `body(...)`.

Unlike annotated controllers, a functional endpoint **does not automatically bind `@PathVariable` or `@RequestBody` as Java parameters**. The handler reads data from `ServerRequest` using its API methods.

## 4. Direct Comparison of the Two Styles

| Criterion | Annotated controller | RouterFunction + HandlerFunction |
|---|---|---|
| Routing | `@RequestMapping` / `@GetMapping` / `@PostMapping` | `RouterFunctions.route()`, `RequestPredicate` |
| Reading path variables | `@PathVariable long id` | `request.pathVariable("id")`, parsed manually if needed |
| Reading request body | `@RequestBody Dto` or `Mono<Dto>` | `request.bodyToMono(Dto.class)` |
| Writing response | Return `Dto`, `Mono`/`Flux`, `ResponseEntity`, or supported `Publisher` | Return `Mono<ServerResponse>` |
| HTTP status | `@ResponseStatus`, `ResponseEntity`, exception handlers | `ServerResponse.ok()`, `created()`, `notFound()`... |
| Validation | `@Valid`/`@Validated` integrated with binding/validation | Explicitly validate in handler/service or via `Validator` |
| Endpoint error handling | Reactive operators; `@ExceptionHandler` / `@RestControllerAdvice` | Reactive operators, route filters, `WebExceptionHandler`, or shared error handler |
| Local cross-cutting | Controller advice, annotations, suitable filters/interceptors | `RouterFunction` filter/before/after; global `WebFilter` |
| Code layout | HTTP mappings next to controller methods | Route definitions separated from handler classes |
| Well suited for | Apps with many controllers, annotation-driven binding/validation, teams familiar with Spring MVC | Route composition, flexible predicates, small handlers, routing DSL |
| Execution foundation | Spring WebFlux reactive | Spring WebFlux reactive |

Do not conclude that one style is always faster. Given the same reactive service and HTTP server, the cost of I/O, database access, serialization, and business logic usually outweighs routing syntax differences. Base your choice on code clarity, team conventions, and HTTP mapping requirements.

## 5. Setting Up a Runnable Project

This example uses **Spring Boot 3.5.0** (Java 17 or newer) with the WebFlux dependency and without `spring-boot-starter-web`. That keeps the focus squarely on the WebFlux server and avoids Boot preferring Spring MVC when both starters are present.

Directory structure:

~~~text
webflux-routing-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/routing/
    │   │   ├── RoutingApplication.java
    │   │   ├── Task.java
    │   │   ├── NewTask.java
    │   │   ├── TaskService.java
    │   │   ├── AnnotatedTaskController.java
    │   │   ├── FunctionalTaskHandler.java
    │   │   └── FunctionalTaskRoutes.java
    │   └── resources/application.yml
    └── test/java/com/example/routing/
        └── TaskRoutingTest.java
~~~

### 5.1. Maven pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-routing-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>webflux-routing-demo</name>

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
~~~

Dependency versions are managed by the Spring Boot parent, so no explicit versions are needed.

### 5.2. application.yml

~~~yaml
server:
  port: 8080

spring:
  application:
    name: webflux-routing-demo
~~~

The port can be changed via profiles or startup arguments. `@EnableWebFlux` is unnecessary when Spring Boot auto-configuration is active.

### 5.3. RoutingApplication.java

~~~java
package com.example.routing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RoutingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RoutingApplication.class, args);
    }
}
~~~

The remaining classes live under the same `com.example.routing` package so component scanning detects them.

## 6. Data Model and Shared Service

**Task.java**

~~~java
package com.example.routing;

public record Task(long id, String title) {
}
~~~

**NewTask.java**

~~~java
package com.example.routing;

public record NewTask(String title) {
}
~~~

**TaskService.java**

~~~java
package com.example.routing;

import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class TaskService {

    private final ConcurrentMap<Long, Task> tasks =
            new ConcurrentHashMap<>();
    private final AtomicLong ids = new AtomicLong(1);

    public TaskService() {
        tasks.put(1L, new Task(1L, "learn-webflux"));
    }

    public Flux<Task> findAll() {
        return Flux.defer(() ->
                Flux.fromIterable(List.copyOf(tasks.values())));
    }

    public Mono<Task> findById(long id) {
        return Mono.defer(() ->
                Mono.justOrEmpty(tasks.get(id)));
    }

    public Mono<Task> create(NewTask input) {
        return Mono.defer(() -> {
            if (input == null || input.title() == null
                    || input.title().isBlank()) {
                return Mono.error(
                        new IllegalArgumentException("title is required"));
            }

            long id = ids.incrementAndGet();
            Task created = new Task(id, input.title().trim());
            tasks.put(id, created);
            return Mono.just(created);
        });
    }
}
~~~

This is an **in-memory demo**, not a production reactive repository. `ConcurrentHashMap` provides basic thread-safety under concurrent requests; `AtomicLong` issues unique IDs within a single process. Data is lost on application restart.

`Mono.defer` and `Flux.defer` defer execution until subscription, illustrating laziness. However, reading and writing a `ConcurrentHashMap` is an in-memory synchronous operation and does not magically become non-blocking I/O. For real databases, use an appropriate reactive driver or repository, or intentionally isolate blocking calls with controlled thread pools.

Both HTTP interfaces below inject the same `TaskService` bean. Therefore, a task created via the functional endpoint can be read via the annotated endpoint and vice versa.

## 7. AnnotatedTaskController.java: Defining Endpoints With Annotations

~~~java
package com.example.routing;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/annotated/tasks")
public class AnnotatedTaskController {

    private final TaskService service;

    public AnnotatedTaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<Task> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Task>> findById(
            @PathVariable long id) {

        return service.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.notFound().<Task>build());
    }

    @PostMapping
    public Mono<ResponseEntity<Task>> create(
            @RequestBody Mono<NewTask> body) {

        return body.flatMap(service::create)
                .map(task -> ResponseEntity
                        .created(URI.create(
                                "/annotated/tasks/" + task.id()))
                        .body(task))
                .onErrorResume(
                        IllegalArgumentException.class,
                        error -> Mono.just(
                                ResponseEntity.badRequest()
                                        .<Task>build()));
    }
}
~~~

**Request-by-request explanation:**

- `GET /annotated/tasks` returns `Flux<Task>`. WebFlux's codecs write the elements to the response using the negotiated media type.
- `GET /annotated/tasks/1` reads `id` via `@PathVariable` and returns `Mono<ResponseEntity<Task>>`. If a `Task` exists, it returns HTTP 200 with JSON; if the `Mono` is empty, HTTP 404.
- `POST /annotated/tasks` receives the body as `Mono<NewTask>`, passes it to the service, and returns HTTP 201 Created with a `Location` header and the created `Task` JSON.
- If `title` is invalid, the service emits `IllegalArgumentException`; the `onErrorResume` operator in this example maps that specific error to HTTP 400.
- Empty bodies or undecodable JSON are handled by framework request-body binding rules; do not assume they are identical to the service's `IllegalArgumentException`.

The Java methods do not call `subscribe()`. When processing requests, Spring WebFlux subscribes to the publisher and manages the processing/writing lifecycle.

**Note:** `HttpStatus` is imported in the example but unused in this class; removing the import has no effect on compilation. Java allows unused imports.

## 8. FunctionalTaskHandler.java: Handling ServerRequest, Building ServerResponse

~~~java
package com.example.routing;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class FunctionalTaskHandler {

    private final TaskService service;

    public FunctionalTaskHandler(TaskService service) {
        this.service = service;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(service.findAll(), Task.class);
    }

    public Mono<ServerResponse> findById(ServerRequest request) {
        final long id;

        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException ex) {
            return ServerResponse.badRequest().build();
        }

        return service.findById(id)
                .flatMap(task -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(task))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(NewTask.class)
                .flatMap(service::create)
                .flatMap(task -> ServerResponse
                        .created(URI.create(
                                "/functional/tasks/" + task.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(task))
                .onErrorResume(
                        IllegalArgumentException.class,
                        error -> ServerResponse.badRequest().build())
                .switchIfEmpty(ServerResponse.badRequest().build());
    }
}
~~~

Key differences:

1. There is no `@GetMapping` in the handler; routes are declared in a separate class.
2. `request.pathVariable("id")` returns a `String`, so it must be parsed to `long`. If invalid, the handler returns 400.
3. `request.bodyToMono(NewTask.class)` decodes the JSON body via codecs.
4. `ServerResponse.ok()`, `ServerResponse.created(...)`, and `ServerResponse.notFound()` express the status directly.
5. `.body(publisher, Task.class)` writes a multi-element `Publisher` of `Task`; `.bodyValue(task)` writes a single concrete value.
6. `switchIfEmpty` handles the missing-data or empty-body branches.
7. `onErrorResume` handles the illustrative business error; real applications should design safer, consistent error codes and messages.

**Do not call `block()`** inside the handler. The handler returns a `Mono` so WebFlux executes asynchronously. Using `ServerResponse` does not mean the response is flushed to the socket on the line calling `bodyValue`; the method creates a `Mono` representing response completion.

## 9. FunctionalTaskRoutes.java: The RouterFunction Bean

~~~java
package com.example.routing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalTaskRoutes {

    @Bean
    RouterFunction<ServerResponse> taskRoutes(
            FunctionalTaskHandler handler) {

        return RouterFunctions.route()
                .GET("/functional/tasks", handler::list)
                .GET("/functional/tasks/{id}", handler::findById)
                .POST("/functional/tasks", handler::create)
                .build();
    }
}
~~~

Spring Boot detects the `RouterFunction` bean when setting up WebFlux infrastructure. These GET/POST routes invoke the corresponding methods in `FunctionalTaskHandler`.

In this example, the annotated controller uses `/annotated/tasks` and the functional router uses `/functional/tasks`. Separating the two route families makes testing straightforward without mapping conflicts.

**Route ordering in WebFlux.fn matters.** When overlapping patterns exist in the same builder, routes are evaluated in registration order. Place specific routes before general routes—for example, `/functional/tasks/search` before `/functional/tasks/{id}` if `search` is a literal keyword. Annotation-based mappings follow their own method-specificity rules. Do not assume all routing styles share the same precedence rules.

## 10. Running and Testing HTTP From the Terminal

From the `webflux-routing-demo` directory:

~~~bash
mvn test
mvn spring-boot:run
~~~

Assuming the app runs on port 8080, create a task via the annotated route:

~~~bash
curl -i -X POST "http://localhost:8080/annotated/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"annotated-created"}'
~~~

Expected outcome: HTTP 201, `Location` pointing to the new task, and JSON containing `id`/`title`. Do not assume a fixed ID if prior creation requests already ran.

Create a task via the functional route:

~~~bash
curl -i -X POST "http://localhost:8080/functional/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"functional-created"}'
~~~

Read the default task through both styles:

~~~bash
curl -i "http://localhost:8080/annotated/tasks/1"
curl -i "http://localhost:8080/functional/tasks/1"
~~~

Both read from the same `TaskService`, so the JSON body contains:

~~~json
{"id":1,"title":"learn-webflux"}
~~~

Missing task case:

~~~bash
curl -i "http://localhost:8080/annotated/tasks/99999"
curl -i "http://localhost:8080/functional/tasks/99999"
~~~

Both are designed to return HTTP 404. The error response body depends on error handling/codecs; do not rely on a single fixed error JSON format unless you standardize the API contract.

Blank title case:

~~~bash
curl -i -X POST "http://localhost:8080/functional/tasks" \
  -H "Content-Type: application/json" \
  -d '{"title":"   "}'
~~~

The functional handler converts `IllegalArgumentException` from `TaskService` into HTTP 400. The annotated controller handles this case similarly. All examples keep state strictly in memory; restarting the app loses user-created tasks.

## 11. When You Need Complex Predicates or Nested Routes

The `RouterFunctions.route()` builder supports many `RequestPredicate`s:

~~~java
import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;

RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .GET("/api/tasks", accept(APPLICATION_JSON), handler::list)
        .POST("/api/tasks", handler::create)
        .build();
~~~

This is an isolated illustrative snippet and does not replace the running project's `routes` bean.

Here `GET` only matches when the `Accept` header satisfies JSON. If a client sends an incompatible `Accept` header, this route will not match; failing to match a route is not an exception thrown directly by the handler.

Routes can be nested by path:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .path("/api/tasks", builder -> builder
                .GET("/{id}", handler::findById)
                .GET(handler::list)
                .POST(handler::create))
        .build();
~~~

With nested routing, the `/api/tasks` prefix is declared only once. To use this builder, handler methods must accept `ServerRequest` and return `Mono<ServerResponse>`.

**Composition options:** `RouterFunction.and(...)`, `RouterFunction.andRoute(...)`, `RouterFunctions.route().add(...)`, or multiple `RouterFunction` beans gathered by Spring Boot. As a module grows, split routers by bounded context and mind route ordering rather than keeping one several-hundred-line class.

## 12. Binding, Validation, and Errors: What Advantages Do Annotations Have?

Annotated controllers leverage Spring Framework's ability to bind and validate parameters directly in the method signature.

Example with the `spring-boot-starter-validation` dependency:

~~~java
public record NewTaskRequest(
        @NotBlank String title,
        @Size(max = 120) String description) {
}

@PostMapping
public Mono<Task> create(
        @Valid @RequestBody Mono<NewTaskRequest> body) {
    return body.flatMap(service::createValidated);
}
~~~

This is a separate example illustrating Bean Validation; `createValidated` and `NewTaskRequest` are not declared in the complete project above. Do not copy this snippet into `AnnotatedTaskController` without adding the service contract and `jakarta.validation.*` imports.

In WebFlux, `@Valid` combined with `@RequestBody` can raise `WebExchangeBindException`. With method-level constraints, `HandlerMethodValidationException` can also occur. A project should handle both according to its error response policy.

For functional endpoints, handlers do not automatically evaluate validation annotations on `ServerRequest` parameters. You can:

- Parse the body into a DTO with `request.bodyToMono(Dto.class)`.
- Use a Spring-managed `Validator` to validate the DTO.
- Or place validation inside the application service and map errors to an appropriate `ServerResponse`.
- Standardize error responses so both routing styles return the same error codes and messages.

**Do not assume `@Valid` automatically applies to functional handlers.** Validation requires an explicit execution step.

### 12.1. Two Approaches to Error Handling

Annotated controllers can use `@ExceptionHandler` inside a controller or `@RestControllerAdvice` to centralize exception handling. This is a familiar pattern for turning business errors into consistent HTTP responses.

Functional handlers typically use `onErrorResume`, build statuses directly via `ServerResponse`, or use a `WebExceptionHandler` / shared error-handling mechanism across routes. Route filters can also wrap handlers when a local policy is needed.

If both styles must return RFC 9457 Problem Details, design a shared error contract and test every endpoint. Do not assume `@ControllerAdvice` applies identically to errors from functional handlers: their execution paths differ.

## 13. Filters: WebFilter and HandlerFilterFunction

The goal of "running before/after a request" has two distinct layers:

- **WebFilter:** sits in Spring WebFlux's filter chain; can affect both annotated controllers and functional endpoints depending on scope, order, and configuration. This is the choice for application-wide cross-cutting concerns.
- **HandlerFilterFunction:** a WebFlux.fn filter applied to a router or functional route group. It accepts `ServerRequest` and the next `HandlerFunction`, returning `Mono<ServerResponse>`. This is the choice when logic is tightly bound to a group of functional endpoints.

A simple functional filter:

~~~java
return RouterFunctions.route()
        .GET("/api/health", request ->
                ServerResponse.ok().bodyValue("up"))
        .filter((request, next) -> {
            if ("blocked".equals(
                    request.headers().firstHeader("X-Mode"))) {
                return ServerResponse.status(403).build();
            }
            return next.handle(request);
        })
        .build();
~~~

The snippet above illustrates syntax inside a method returning `RouterFunction<ServerResponse>`, not a standalone Java file. It only checks a hypothetical header, not a real authorization system.

Spring Security WebFlux uses `SecurityWebFilterChain` and reactive security components. Do not use a simple `HandlerFilterFunction` to replace authentication, authorization, CSRF, CORS, and security context propagation.

**Flow note:** do not call `subscribe()` inside a filter and return a different response. Return the publisher produced by `next.handle(request)`, optionally adding operators like `doOnNext`/`doOnError` to observe without breaking the pipeline.

## 14. JSON, HTTP Status, and Content Negotiation

In an annotated controller:

~~~java
@GetMapping(path = "/items", produces = MediaType.APPLICATION_JSON_VALUE)
public Flux<ItemDto> items() {
    return service.findAllItems();
}
~~~

The framework relies on annotations, return types, and codecs to produce the response. You can use `ResponseEntity` or `@ResponseStatus` to control status and headers.

In a functional handler:

~~~java
public Mono<ServerResponse> items(ServerRequest request) {
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(service.findAllItems(), ItemDto.class);
}
~~~

Status, content type, and body are configured via the `ServerResponse` builder. Both snippets only illustrate API usage; `ItemDto` and `findAllItems` are not part of the complete demo.

For streaming, understand the difference between a publisher **emitting multiple items** and the wire protocol **delivering each item to the client**. A `Flux<T>` with `application/json` may be serialized as a JSON array; do not assume every `onNext` translates into an individual response frame received immediately by the client.

When you need **Server-Sent Events**, use media type `text/event-stream` with an appropriate `Flux`. With functional endpoints, write the publisher as SSE; with annotated controllers, use `@GetMapping(produces = MediaType.TEXT_EVENT_STREAM_VALUE)`.

### 14.1. When Do You Need ResponseEntity or ServerResponse?

- Annotated controllers returning a DTO or `Mono<DTO>` are concise for a default HTTP 200.
- When you need 201 Created, `Location`, `ETag`, or an explicit 404, `ResponseEntity<T>` and `Mono<ResponseEntity<T>>` are appropriate choices.
- Functional endpoints always return `Mono<ServerResponse>`; set status and body using the builder.
- Do not confuse `Mono<ResponseEntity<Flux<T>>>` with `Mono<ResponseEntity<T>>`: where the publisher appears in the return type determines when the body is written.

## 15. Reactive Semantics: Do Not Block, Do Not Manually Subscribe

This matters more than routing syntax.

**Mono** represents at most one value signal; **Flux** represents multiple signals. Publishers are typically lazy: work requires subscription to start.

A common mistake in WebFlux handlers:

~~~java
Task task = webClient.get()
        .uri("/tasks/1")
        .retrieve()
        .bodyToMono(Task.class)
        .block();  // Avoid in reactive request processing.
~~~

Waiting on `block()` can stall the event-loop thread or be rejected by Reactor as illegal blocking. The right approach is returning a publisher:

~~~java
return webClient.get()
        .uri("/tasks/1")
        .retrieve()
        .bodyToMono(Task.class)
        .flatMap(task -> ServerResponse.ok().bodyValue(task));
~~~

In the annotated style:

~~~java
@GetMapping("/remote")
public Mono<Task> remote() {
    return webClient.get()
            .uri("/tasks/1")
            .retrieve()
            .bodyToMono(Task.class);
}
~~~

These examples illustrate integrating `WebClient` into a controller/handler, assuming a `webClient` bean and DTO exist. Do not copy all three snippets into the full demo without defining a `WebClient` bean.

**Avoid calling `subscribe()` manually:**

~~~java
Mono<Task> result = service.findById(1);
result.subscribe(task -> log.info("{}", task));
return Mono.empty();
~~~

This snippet intentionally illustrates an anti-pattern. Calling `subscribe()` inside a handler and returning a different `Mono` prevents the framework from managing completion, errors, and cancellation of the detached work.

**If the system must call a blocking library**, do not pretend `Mono.just(blockingCall())` is non-blocking. You can consider `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` as a temporary isolation measure, but you must control thread concurrency limits, timeouts, and load. Long term, choose reactive drivers when true end-to-end non-blocking is desired.

## 16. Backpressure and Cancellation

Both annotated controllers and functional handlers rely on Reactive Streams. The application layer can express data via `Flux`, supporting demand control, error propagation, and cancellation according to each publisher's and transport's capabilities.

Example event-stream service:

~~~java
Flux<String> events = Flux.interval(Duration.ofSeconds(1))
        .map(index -> "tick-" + index);
~~~

This is a standalone Reactor example requiring `java.time.Duration` and `reactor.core.publisher.Flux`. `Flux.interval` uses a scheduler to emit periodically; do not use it for durable business notifications without persistence.

With an annotated controller, you can return `Flux<ServerSentEvent<String>>`; with a functional endpoint, set `contentType(MediaType.TEXT_EVENT_STREAM)` and `body(events, String.class)`. When a client disconnects, cancellation can propagate upstream to release resources as designed.

**Do not equate backpressure with infinite network capacity.** Buffering, codec limits, network write behavior, and the data source itself all play a role. If the upstream source is an API without backpressure support, the application may still need bounded buffers, drop policies, or rate control.

## 17. Testing Both Styles With WebTestClient

`WebTestClient` works with annotated controllers, functional routers, and live HTTP servers. With Spring Boot, you can use an integration test on a random port to verify both routing styles work together in the same `ApplicationContext`.

**src/test/java/com/example/routing/TaskRoutingTest.java**

~~~java
package com.example.routing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class TaskRoutingTest {

    @Autowired
    WebTestClient client;

    @Test
    void bothStylesCanReadTheSameTask() {
        client.get()
                .uri("/annotated/tasks/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("learn-webflux");

        client.get()
                .uri("/functional/tasks/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("learn-webflux");
    }

    @Test
    void functionalCreationIsVisibleThroughAnnotatedRoute() {
        Task created = client.post()
                .uri("/functional/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewTask("reactive-routing"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(Task.class)
                .returnResult()
                .getResponseBody();

        assertThat(created).isNotNull();

        client.get()
                .uri("/annotated/tasks/{id}", created.id())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("reactive-routing");
    }

    @Test
    void bothStylesReturnNotFound() {
        client.get()
                .uri("/annotated/tasks/99999")
                .exchange()
                .expectStatus().isNotFound();

        client.get()
                .uri("/functional/tasks/99999")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void functionalHandlerRejectsBlankTitle() {
        client.post()
                .uri("/functional/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new NewTask("  "))
                .exchange()
                .expectStatus().isBadRequest();
    }
}
~~~

With `RANDOM_PORT`, Spring Boot starts a server on a random port and configures `WebTestClient` for HTTP testing. Tests do not need to hard-code port 8080.

The test suite checks key behaviors: both routes reading the same data, a functional POST creating data readable by the annotated route, explicit 404 handling, and rejection of invalid bodies. These are more meaningful criteria than merely asserting a `RouterFunction` bean exists.

Run:

~~~bash
mvn test
~~~

When tests succeed, Maven exits with code 0. Do not assert log line counts, random port numbers, or task ordering in the list, as those values are unstable across runs.

### 17.1. Testing Without Starting a Real Server

Spring Framework supports:

~~~java
WebTestClient.bindToController(new MyController(...)).build();
WebTestClient.bindToRouterFunction(routerFunction).build();
~~~

These are test API examples, not copy-pasteable classes without instantiating the controller or router first. `bindToController` fits when isolating a single annotated controller; `bindToRouterFunction` fits testing a route plus functional handler. Full-application integration tests using `ApplicationContext` or `RANDOM_PORT` catch auto-configuration and bean-routing issues that isolated unit tests can miss.

With `@WebFluxTest`, keep in mind it is a WebFlux test slice and does not automatically load all custom repositories, services, or `RouterFunction`s. Import the configurations under test or use `SpringBootTest` when comparing both styles inside the full application.

## 18. CORS, Security, and Observability

Neither style removes application security responsibilities.

**Spring Security WebFlux:** configure `SecurityWebFilterChain` to protect HTTP requests at the reactive layer. It applies regardless of whether the final handler is an annotated controller or a functional route. Do not assume that because a router lacks `@PreAuthorize`, authorization is unnecessary.

**CORS:** annotated controllers can use `@CrossOrigin` or WebFlux CORS configuration. Functional routes can use WebFlux CORS configuration or appropriate filters. Avoid mismatched CORS rules where one route family accepts browser requests while the other gets blocked.

**Logging/tracing:** you can use a `WebFilter` or Spring Boot's observation/tracing mechanisms; propagate correlation IDs properly via the reactive context instead of assuming `ThreadLocal` survives scheduler switches.

**Rate limiting / auditing:** requirements spanning all requests belong in `WebFilter`, an API gateway, or an appropriate service security layer. `HandlerFilterFunction` is useful for router groups, not as a substitute for the global security layer.

**Timeouts:** if a controller or handler invokes `WebClient`, set appropriate outbound HTTP client timeouts and per-request time budgets. Using only Reactor's `timeout` operator does not guarantee all underlying socket timeouts on every client connector are configured.

## 19. Choosing Annotations vs. RouterFunction for Your Project

**Prefer annotated controllers when:**

- The team is already comfortable with `@RestController` and Spring MVC annotations.
- Many methods rely on annotation-driven validation, argument binding, or OpenAPI documentation.
- Each controller aligns cleanly with a business slice and mappings are straightforward.
- You want to follow the conventional controller-service-repository structure.

**Prefer RouterFunction when:**

- You want routes expressed as a centralized declaration table or clean DSL.
- Routes require combining conditions like path, `Accept`, and `Content-Type`.
- You want modular router composition/nesting with localized filters.
- You want handlers modeled simply as functions taking `ServerRequest` and returning `Mono<ServerResponse>`.

**Using both together makes sense when:**

- The application is migrating incrementally from annotated to functional (or vice versa).
- Different bounded contexts are owned by different teams.
- Rules are in place to avoid URL collisions and keep error contracts, security, and response formats consistent.

Do not use both merely to duplicate every endpoint without a real need. In the example, exposing the same `TaskService` via both APIs is purely for learning and testing.

## 20. Common Pitfalls

| Symptom | Common cause | Fix |
|---|---|---|
| `RouterFunction` bean exists, yet requests return 404 | Wrong path, HTTP method, predicate, or reactive configuration | Check method/path/headers, `RouterFunctionMapping`, and WebFlux starter |
| `RouterFunction` class name looks right, yet handler return type fails | Wrongly imported `org.springframework.web.servlet.function.*` | Use `org.springframework.web.reactive.function.server.*` and `Mono<ServerResponse>` |
| `GET /tasks/{id}` catches `/tasks/search` and returns 400 | General route registered before specific route | Put `/tasks/search` before `/tasks/{id}`, or constrain the predicate |
| Controller returns `Mono.empty()` but response is not 404 | Not-found status not mapped explicitly | Use `ResponseEntity.notFound()` or a business exception |
| Functional handler returns 500 instead of 400 on bad DTO | Missing validation and error mapping | Add validation/service rules and return `ServerResponse.badRequest()` |
| Both `starter-web` and `starter-webflux` added, yet no WebFlux server starts | Boot defaults to Spring MVC | Keep only the WebFlux starter for a reactive server; verify application type |
| Endpoint returns `Mono` yet bottlenecks under load | Inner code calls JDBC, file I/O, or `block()` | Use reactive drivers or isolate blocking calls and monitor schedulers |
| Handler manually calls `subscribe()` and returns `Mono.empty()` | Detaches work from the request lifecycle | Return the original publisher so the framework subscribes |
| Router filter does not run on annotated controllers | `HandlerFilterFunction` only applies to routes on that router | Use `WebFilter` when filtering across all endpoints |
| JSON responses differ between annotation and functional endpoints | Different codecs, statuses, content types, or error contracts | Define a unified response contract and test both styles |
| `@ControllerAdvice` does not handle functional errors as expected | Different handler execution path | Use `WebExceptionHandler` / shared error handling and map in handlers |
| Tests pass only when run in isolation | Shared in-memory state or hard-coded IDs/ports | Assert using IDs from responses; use `RANDOM_PORT` and isolated test data |
| Streaming does not emit message by message | Wrong media type or buffering | Use `text/event-stream` for SSE; inspect client/proxy buffering |
| Using Spring MVC annotations in a reactive app | Imports/configuration from the servlet stack | Check WebFlux packages and runtime `DispatcherHandler` |

## 21. Project Adoption Checklist

1. Confirm the server stack is truly Spring WebFlux, not an MVC app merely using `WebClient`.
2. When using WebFlux.fn, import `org.springframework.web.reactive.function.server`, never `org.springframework.web.servlet.function`.
3. Keep controllers and handlers thin; place business logic in shared services/repositories.
4. For annotations, use `@RequestBody`, `@PathVariable`, `@RequestParam`, and `ResponseEntity` where appropriate.
5. For functional routes, separate `RouterFunction` from `HandlerFunction`; handlers read `ServerRequest` and build `ServerResponse`.
6. Define explicit HTTP statuses for 200/201/400/404 and upstream failures.
7. Order functional routes from specific to general to prevent pattern shadowing.
8. Never call `block()` or `subscribe()` inside WebFlux request processing.
9. Provide request-body validation and consistent error handling across both endpoint styles.
10. Use `WebFilter`/`SecurityWebFilterChain` for app-wide policies; use route filters only for router-scoped behavior.
11. Test controllers, routers, and the full app with `WebTestClient`; use `RANDOM_PORT` to verify the live server.
12. Monitor throughput/latency, codec limits, cancellation, backpressure, and I/O performance in production.

## 22. Conclusion

**Annotated controllers and `RouterFunction`s are two HTTP entry styles on the same Spring WebFlux reactive stack.** Annotated controllers map requests and bind method parameters via annotations; WebFlux.fn defines `RouterFunction`s that dispatch to `HandlerFunction`s taking `ServerRequest` and returning `Mono<ServerResponse>`.

There is no rule that "`RouterFunction` is inherently more reactive than a controller." Both use `Mono`/`Flux`, WebFlux codecs, and `WebFilter`s. Choose based on clarity and routing requirements, avoid accidentally importing WebMvc.fn, keep blocking code off event loops, and keep HTTP statuses, validation, security, and tests consistent.

## Official Documentation

- [Spring Framework 6.2 — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html)
- [Spring Framework 6.2 — Annotated Controllers](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-controller.html)
- [Spring Framework 6.2 — WebTestClient](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
