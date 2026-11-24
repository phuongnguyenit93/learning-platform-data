# Building the Same Contract with Controllers and Functional Endpoints in Spring WebFlux

**Module:** Spring Framework - reactive  
**Parent topic:** Integrated Practice  
**Lesson:** Building the Same Contract with Controllers and Functional Endpoints

## Learning Objectives

After this lesson, you can:

1. Describe the two HTTP programming models in Spring WebFlux: annotated controllers and functional endpoints.
2. Distinguish `@RestController`/`@RequestMapping` from `RouterFunction`/`HandlerFunction`.
3. Build the same HTTP API contract in both styles: route, method, path variable, query/body, status, header, JSON response, and errors.
4. Separate DTOs, validation, business service, and persistence from the HTTP layer so both adapters share the same logic.
5. Understand how Spring WebFlux decodes bodies, serializes Publishers, and handles `Mono`/`Flux` and backpressure.
6. Apply Bean Validation to controllers and functional handlers while keeping error responses consistent.
7. Choose how to handle 404, 400, 201 Created, the Location header, and content type.
8. Write contract tests with `WebTestClient` against a real HTTP server, comparing the two implementations.
9. Understand how to scale functional routes using nested routes, predicates, and `HandlerFilterFunction`.
10. Know when a controller or functional endpoint is more suitable, avoiding decisions based on the assumption that one style is always faster.

## 1. One API Contract, Two Ways to Declare It

Spring WebFlux supports two ways to define HTTP endpoints:

- **Annotated controller:** declares classes/methods using annotations such as `@RestController`, `@GetMapping`, `@PostMapping`, `@PathVariable`, and `@RequestBody`.
- **Functional endpoint:** describes route conditions with `RouterFunction<ServerResponse>`, then dispatches the request to a `HandlerFunction<ServerResponse>` to build the response.

Both sit on the WebFlux reactive stack, both can return `Mono<T>` or `Flux<T>`, and both use the same codecs, server runtime, Reactor, and WebClient. Functional endpoints do not mean "without Spring" or "not reactive"; controllers are not Spring MVC either if the application is running WebFlux.

### 1.1. Practice API Contract

We build a small task management API with four operations:

| Method | Resource path | Success | Not found / error |
| --- | --- | --- | --- |
| GET | `/tasks` | 200 + JSON task list | — |
| GET | `/tasks/{id}` | 200 + single task | 404 if id does not exist |
| POST | `/tasks` | 201 + created task + Location header | 400 if title is blank |
| POST | `/tasks/{id}/complete` | 200 + completed task | 404 if id does not exist |

Create task request:

```http
POST /tasks
Content-Type: application/json

{
  "title": "Prepare release"
}
```

Success response:

```http
HTTP/1.1 201 Created
Location: /tasks/1
Content-Type: application/json

{
  "id": 1,
  "title": "Prepare release",
  "completed": false
}
```

Validation error response shares a common schema:

```json
{
  "code": "VALIDATION_FAILED",
  "message": "title: must not be blank"
}
```

In the demo project, both adapters run concurrently so they have prefixes:

- Annotated controller: `/controller/tasks`.
- Functional endpoint: `/functional/tasks`.

The path after the prefix, HTTP method, status, headers, and JSON contract are identical. The prefix simply allows both adapters to coexist in one process for side-by-side testing. If deploying only one style, you can use the canonical path `/api/tasks`; do not register two handlers with the same method and path in the same router/application without clear resolution rules.

## 2. Architecture: HTTP Adapters Sharing an Application Service

An API should separate three responsibilities:

```text
                HTTP Request
                     |
            +--------+--------+
            |                 |
            v                 v
   Annotated Controller   Functional Router
            |                 |
            v                 v
     Controller methods   HandlerFunction
            |                 |
            +--------+--------+
                     |
                     v
                TaskService
                     |
                     v
             Repository / Store
                     |
                     v
              Domain response
```

Controllers and functional handlers are two **HTTP adapters**. They are responsible for routing, request binding, boundary input validation, choosing status/headers, and serializing responses. Business rules live in the service and should not be duplicated between the two adapters.

In a real application, the service can call Spring Data R2DBC, reactive repositories, WebClient, or other systems. The example in this lesson uses an in-memory store to focus on the differences between the two endpoint styles without database configuration noise.

### 2.1. Contract First, Implementation Second

Before writing a controller or router, settle the following points:

- Resources and paths.
- HTTP methods.
- Request and response types.
- Status codes for each case.
- Required headers, especially Location when creating a resource.
- Validation rules and error schema.
- Behavior when a resource does not exist.
- Content types and how data is streamed.

Once the contract is clear, you can swap adapters without clients changing how they call the API. This benefit matters more than comparing annotation counts or lines of code.

## 3. Annotated Controllers in WebFlux

### 3.1. How to Declare

Controllers use annotations so Spring maps HTTP methods:

```java
@RestController
@RequestMapping("/controller/tasks")
class TaskController {

    @GetMapping
    public Flux<TaskView> list() {
        // ...
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<TaskView>> get(
            @PathVariable long id) {
        // ...
    }

    @PostMapping
    public Mono<ResponseEntity<TaskView>> create(
            @Valid @RequestBody CreateTaskRequest request) {
        // ...
    }
}
```

`@RestController` combines `@Controller` and `@ResponseBody`. Return values are handled by WebFlux message writers/HTTP codecs. With reactive return types, the framework subscribes and writes results according to the HTTP lifecycle.

### 3.2. Argument Resolution

Spring can automatically bind many parts of an HTTP request to method parameters:

| Annotation / parameter type | Received data |
| --- | --- |
| `@PathVariable` | Dynamic segment in the path. |
| `@RequestParam` | Query parameter or form parameter as supported by WebFlux binding. |
| `@RequestHeader` | HTTP header. |
| `@CookieValue` | Cookie. |
| `@RequestBody` | Request body via codec. |
| `@Valid` / `@Validated` | Triggers Bean Validation appropriate for the parameter. |
| `ServerWebExchange` | Lower-level access to the request/response exchange. |

Example:

```java
@GetMapping("/search")
public Flux<TaskView> search(
        @RequestParam(required = false) String title,
        @RequestHeader(name = "X-Request-Id", required = false)
        String requestId) {
    // Use title and requestId in the service.
}
```

The snippet above illustrates argument binding; the method body must be implemented per the specific contract. For reactive bodies, the parameter can be `Mono<CreateTaskRequest>` or `Flux<Line>` if you want to process a stream rather than materializing a single object.

### 3.3. Return Types and Status

- Returning `Mono<TaskView>`: the framework typically produces a 200 response with one object if data exists.
- Returning `Flux<TaskView>`: the framework serializes multiple elements according to media type and negotiation.
- Returning `ResponseEntity<T>` or `Mono<ResponseEntity<T>>`: controls status/headers/body.
- Returning `ResponseEntity<Flux<T>>`: controls status/headers while keeping the body streaming.

For a POST that creates a resource, `201 Created` with `Location` usually expresses intent more clearly than returning 200. Do not let framework defaults decide the status if the API contract requires different rules.

### 3.4. Validation and Errors

Controllers can use `@Valid @RequestBody` to validate DTOs. On bind/validation failures, WebFlux can emit `WebExchangeBindException`. Use `@RestControllerAdvice` and `@ExceptionHandler` to map it into a unified error schema.

Example:

```java
@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ApiError> validation(
            WebExchangeBindException exception) {
        // Build ApiError with status 400.
    }
}
```

This is an abbreviated illustrative snippet; the complete project in section 8 implements all methods and imports. For domain errors such as a missing resource, you can return `ResponseEntity.notFound()` directly in the method or use a shared exception handler. Choose a consistent strategy across the whole API.

## 4. Functional Endpoints: RouterFunction and HandlerFunction

### 4.1. Two Core Components

Functional endpoints separate:

- **RouterFunction:** determines which request is routed to which handler.
- **HandlerFunction:** takes a `ServerRequest` and returns a `Mono<ServerResponse>`.

Diagram:

```text
HTTP request
    |
    v
RouterFunction
    |
    +-- method + path + headers + predicates
    |
    v
HandlerFunction
    |
    +-- read path/query/header/body
    +-- call application service
    +-- choose status/header/content type
    |
    v
Mono<ServerResponse>
```

The router does not contain business logic. The handler should not open sockets directly or serialize JSON manually; `ServerResponse` coordinates with WebFlux codecs to build the response.

### 4.2. Declaring Routes with the Java DSL

```java
@Bean
RouterFunction<ServerResponse> taskRoutes(TaskHandler handler) {
    return RouterFunctions.route()
            .GET("/functional/tasks", handler::list)
            .GET("/functional/tasks/{id}", handler::get)
            .POST("/functional/tasks", handler::create)
            .POST("/functional/tasks/{id}/complete",
                    handler::complete)
            .build();
}
```

Routes are clearly described by HTTP method and path. You can add predicates for query, header, content type, accept header, or combine multiple conditions.

A route function can combine multiple smaller routers using `and`/`andOther` or composition. As a system grows, splitting routers by resource/domain avoids an overly long route configuration.

### 4.3. Handlers Reading Requests

`ServerRequest` provides:

- `pathVariable("id")` to read a path variable.
- `queryParam("q")` to read a query parameter.
- `headers()` to access request headers.
- `bodyToMono(Type.class)` or `bodyToFlux(Type.class)` to decode the body.
- `body(BodyExtractors...)` for advanced decoding needs.

Example:

```java
public Mono<ServerResponse> get(ServerRequest request) {
    long id = Long.parseLong(request.pathVariable("id"));

    return service.findById(id)
            .flatMap(task -> ServerResponse.ok().bodyValue(task))
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

Functional handlers require code to decide explicitly how to parse and handle input. Therefore, handle invalid input explicitly; do not let `NumberFormatException` accidentally become a 500 if the contract requires a 400.

### 4.4. Creating Responses

`ServerResponse` lets you describe status, headers, cookies, and body:

```java
return ServerResponse.created(location)
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(task);
```

Common options:

- `ServerResponse.ok()`: 200.
- `ServerResponse.created(uri)`: 201 and Location.
- `ServerResponse.noContent()`: 204.
- `ServerResponse.badRequest()`: 400.
- `ServerResponse.notFound()`: 404.
- `ServerResponse.status(HttpStatus)`: arbitrary status.
- `bodyValue(object)`: single body.
- `body(publisher, elementClass)`: reactive stream body.

If the body is a `Flux<T>`, use the overload taking a Publisher and element type; do not unconditionally `collectList()` if the stream is large or unbounded.

### 4.5. Nested Routes and Predicates

You can group routes by a shared path:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/functional", builder -> builder
                        .path("/tasks", tasks -> tasks
                                .GET("", handler::list)
                                .GET("/{id}", handler::get)
                                .POST("", handler::create)))
                .build();
```

This is a DSL structure example; add the remaining routes per the contract. Nested paths make prefixes and route relationships easier to see. Whether using a builder chain or nested routers, avoid placing an overly broad pattern before a specific route if matching order would select an unintended handler.

## 5. Comparing the Two Styles

| Criterion | Annotated controller | Functional endpoint |
| --- | --- | --- |
| Route declaration | Annotations on class/method | Router DSL or predicates |
| Binding | Argument resolvers bind automatically | Handler reads ServerRequest explicitly |
| Response | Return object/Mono/Flux/ResponseEntity | Build ServerResponse |
| Validation | `@Valid`, binding result, controller advice | Call Validator/check input in handler or use helper |
| Error handling | `@RestControllerAdvice`, `@ExceptionHandler` | `onErrorResume`, dedicated handler, or WebExceptionHandler |
| Route grouping | `@RequestMapping` at class level | Nested RouterFunction/path predicates |
| Filters | WebFilter, appropriate HandlerInterceptor | WebFilter or HandlerFilterFunction |
| Explicitness | Less boilerplate, framework binds automatically | More HTTP decisions explicit in code |
| Best fit | Common CRUD APIs, teams familiar with annotations | Complex routing, route composition, explicit adapters |
| Reactive return | Mono/Flux and ResponseEntity | Mono<ServerResponse>, Publisher body |
| Testing | WebTestClient | WebTestClient |
| Performance | Depends on workload/runtime | Depends on workload/runtime; not faster by default |

There is no rule that "functional is always faster than controller." Both use the same reactive HTTP foundation. When benchmarking, you must use the same service, payload, serialization, server, connections, JVM, and load profile. The difference usually lies in code organization and level of control rather than a performance guarantee.

## 6. Validation, Errors, and Response Contracts

### 6.1. DTOs Are Data Contracts

Request DTO:

```java
public record CreateTaskRequest(
        @NotBlank(message = "must not be blank")
        String title) {
}
```

Response DTO:

```java
public record TaskView(
        long id,
        String title,
        boolean completed) {
}
```

API error:

```java
public record ApiError(
        String code,
        String message) {
}
```

Using Java 17 records keeps DTOs concise and immutable. Do not expose internal entities or objects containing sensitive data directly in responses. DTOs are also where versioning and public fields are defined.

### 6.2. Controller Validation

In a controller:

```java
@PostMapping
public Mono<ResponseEntity<TaskView>> create(
        @Valid @RequestBody CreateTaskRequest request) {
    // Validation runs before entering business logic.
}
```

When validation fails, the handler method may not execute and WebFlux emits a binding error. Controller advice converts that error into the `ApiError` schema.

### 6.3. Functional Validation

In a functional handler, read the DTO and invoke Jakarta Validator:

```java
Set<ConstraintViolation<CreateTaskRequest>> violations =
        validator.validate(requestBody);

if (!violations.isEmpty()) {
    return ServerResponse.badRequest()
            .bodyValue(new ApiError(
                    "VALIDATION_FAILED", "title: must not be blank"));
}
```

This snippet illustrates the validation part; it must sit inside a `flatMap` on the body publisher so it neither blocks nor subscribes manually. For synchronous validation on small DTOs, calling Validator directly is reasonable. For validation requiring database/remote service queries, compose it into the reactive pipeline and bound concurrency.

### 6.4. Maintaining the Same Error Schema

Both adapters must return the same status, code, and message on invalid input. If the controller returns `WebExchangeBindException` as default JSON while the functional handler returns `ApiError`, the contracts already differ even if success responses match.

Create a shared error model and a shared mapping rule. Controllers use advice; functional handlers use a helper or an appropriate global `WebExceptionHandler`. For malformed JSON decode errors, explicitly define the 400 contract and test both adapters.

## 7. Reactive Semantics in Both Styles

### 7.1. Do Not Subscribe Manually in Controllers/Handlers

Correct:

```java
public Mono<TaskView> find(long id) {
    return repository.findById(id);
}
```

Avoid:

```java
public Mono<TaskView> find(long id) {
    repository.findById(id).subscribe();
    return Mono.empty();
}
```

`subscribe()` starts a separate subscription, preventing the framework from managing the work's lifecycle properly. It can detach Reactor Context, transactions, cancellation, and error propagation from the original request.

Controllers return publishers; functional handlers compose publishers into `Mono<ServerResponse>`. Spring WebFlux subscribes while processing the HTTP exchange.

### 7.2. Mono, Flux, and Streaming

- `Mono<T>` represents at most one value, or empty/error.
- `Flux<T>` represents 0..N values over time.
- `bodyValue` is suitable for a single object.
- `body(publisher, type)` is suitable for a response stream.
- `ServerSentEvent<T>` and media type `text/event-stream` are suitable for SSE.
- `application/x-ndjson` is suitable for line-delimited JSON streams when client/server support it.

Do not call `collectList()` just to make serialization easier if the response can be large. It collects all items into memory before sending and loses streaming/backpressure benefits.

### 7.3. Cancellation and Client Disconnect

When a client closes the connection, the HTTP adapter can cancel the response publisher. Both annotated controllers and functional handlers must handle cancellation properly. If the upstream is a database stream, file, socket, or self-managed resource, it must be released according to the reactive lifecycle. Use `usingWhen` for async cleanup; `doFinally` is useful for metrics/logging but does not replace asynchronous publisher cleanup.

Do not assume cancellation always rolls back every side effect. If a transaction already committed before the client disconnected, cancellation cannot undo the commit.

## 8. Complete Project: One Service, Two WebFlux Adapters

The project uses Java 17+, Spring Boot 3.3.5, Maven, and Spring WebFlux. Both adapters run concurrently on two different prefixes while implementing the same contract. Data is stored in memory so it is lost when the process restarts; the goal is to illustrate routing and contract testing.

### 8.1. Directory Structure

```text
webflux-two-api-styles/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── ApiApplication.java
    │   │   ├── ApiModels.java
    │   │   ├── TaskService.java
    │   │   ├── TaskController.java
    │   │   ├── TaskHandler.java
    │   │   ├── TaskRoutes.java
    │   │   └── ApiExceptionHandler.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/demo/
            └── ApiContractIntegrationTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-two-api-styles</artifactId>
    <version>1.0.0</version>

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

Do not add `spring-boot-starter-web` because this application runs WebFlux. Mixing both MVC and WebFlux starters can cause auto-configuration to pick an unintended application type unless explicitly configured.

### 8.3. application.properties

```properties
spring.application.name=webflux-two-api-styles
server.port=8080
```

### 8.4. ApiApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiApplication.class, args);
    }
}
```

### 8.5. ApiModels.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public final class ApiModels {
    private ApiModels() {
    }

    public record CreateTaskRequest(
            @NotBlank(message = "must not be blank")
            String title) {
    }

    public record TaskView(
            long id,
            String title,
            boolean completed) {
    }

    public record ApiError(
            String code,
            String message) {
    }
}
```

### 8.6. TaskService.java

```java
package demo;

import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import demo.ApiModels.TaskView;

@Service
public class TaskService {

    private final AtomicLong sequence = new AtomicLong();
    private final ConcurrentMap<Long, TaskView> tasks =
            new ConcurrentHashMap<>();

    public Flux<TaskView> findAll() {
        return Flux.defer(() ->
                Flux.fromIterable(tasks.values().stream()
                        .sorted(Comparator.comparingLong(TaskView::id))
                        .toList()));
    }

    public Mono<TaskView> findById(long id) {
        return Mono.justOrEmpty(tasks.get(id));
    }

    public Mono<TaskView> create(String title) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            TaskView task = new TaskView(id, title, false);
            tasks.put(id, task);
            return task;
        });
    }

    public Mono<TaskView> complete(long id) {
        return Mono.fromSupplier(() -> {
            TaskView current = tasks.get(id);
            if (current == null) {
                return null; // Mono.fromSupplier(null) becomes empty.
            }

            TaskView updated = new TaskView(
                    id, current.title(), true);
            tasks.put(id, updated);
            return updated;
        });
    }
}
```

`ConcurrentHashMap` and `AtomicLong` allow the demo to handle multiple concurrent requests as a simple store. This is not a repository with transactions or durable persistence. `Mono.fromSupplier` is lazy: the task is only created when the request publisher is subscribed.

### 8.7. TaskController.java — annotated adapter

```java
package demo;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import demo.ApiModels.CreateTaskRequest;
import demo.ApiModels.TaskView;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/controller/tasks")
class TaskController {

    private final TaskService service;

    TaskController(TaskService service) {
        this.service = service;
    }

    @GetMapping
    public Flux<TaskView> list() {
        return service.findAll();
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<TaskView>> get(
            @PathVariable long id) {
        return service.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.<TaskView>notFound().build());
    }

    @PostMapping
    public Mono<ResponseEntity<TaskView>> create(
            @Valid @RequestBody CreateTaskRequest request) {
        return service.create(request.title())
                .map(task -> ResponseEntity
                        .created(URI.create(
                                "/controller/tasks/" + task.id()))
                        .body(task));
    }

    @PostMapping("/{id}/complete")
    public Mono<ResponseEntity<TaskView>> complete(
            @PathVariable long id) {
        return service.complete(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(
                        ResponseEntity.<TaskView>notFound().build());
    }
}
```

Controller methods do not subscribe manually. Spring WebFlux handles `Flux`/`Mono` and writes the response. `ResponseEntity` allows defining 201 and Location explicitly.

### 8.8. ApiExceptionHandler.java — validation error for controller

```java
package demo;

import java.util.stream.Collectors;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import demo.ApiModels.ApiError;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> validation(
            WebExchangeBindException exception) {
        String message = exception.getFieldErrors().stream()
                .map(error -> error.getField()
                        + ": " + error.getDefaultMessage())
                .sorted()
                .collect(Collectors.joining("; "));

        return ResponseEntity.badRequest().body(
                new ApiError("VALIDATION_FAILED", message));
    }
}
```

`@RestControllerAdvice` handles validation errors for the annotated controller. The functional handler in this lesson validates manually and produces the same `ApiError` because the two handler styles have different boundary error-handling mechanisms.

### 8.9. TaskHandler.java — functional handler

```java
package demo;

import java.net.URI;
import java.util.Set;
import java.util.function.LongFunction;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import demo.ApiModels.ApiError;
import demo.ApiModels.CreateTaskRequest;
import demo.ApiModels.TaskView;
import reactor.core.publisher.Mono;

@Component
class TaskHandler {

    private final TaskService service;
    private final Validator validator;

    TaskHandler(TaskService service, Validator validator) {
        this.service = service;
        this.validator = validator;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .body(service.findAll(), TaskView.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        return withId(request, id ->
                service.findById(id)
                        .flatMap(task -> ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(task))
                        .switchIfEmpty(ServerResponse.notFound().build()));
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateTaskRequest.class)
                .flatMap(body -> {
                    Set<ConstraintViolation<CreateTaskRequest>> violations =
                            validator.validate(body);

                    if (!violations.isEmpty()) {
                        String message = violations.stream()
                                .map(v -> v.getPropertyPath()
                                        + ": " + v.getMessage())
                                .sorted()
                                .collect(Collectors.joining("; "));

                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError(
                                        "VALIDATION_FAILED", message));
                    }

                    return service.create(body.title())
                            .flatMap(task -> ServerResponse
                                    .created(URI.create(
                                            "/functional/tasks/" + task.id()))
                                    .contentType(MediaType.APPLICATION_JSON)
                                    .bodyValue(task));
                })
                .switchIfEmpty(ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(new ApiError(
                                "VALIDATION_FAILED",
                                "request body is required")));
    }

    public Mono<ServerResponse> complete(ServerRequest request) {
        return withId(request, id ->
                service.complete(id)
                        .flatMap(task -> ServerResponse.ok()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(task))
                        .switchIfEmpty(ServerResponse.notFound().build()));
    }

    private Mono<ServerResponse> withId(
            ServerRequest request,
            LongFunction<Mono<ServerResponse>> action) {
        try {
            long id = Long.parseLong(request.pathVariable("id"));
            return action.apply(id);
        } catch (NumberFormatException exception) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new ApiError(
                            "INVALID_ID", "id must be a number"));
        }
    }
}
```

Key points:

- `ServerRequest` is read directly instead of annotation argument binding.
- Validator is injected from the Bean Validation provider configured by the validation starter.
- Validation errors return the same code/message contract as the controller.
- `withId` handles non-numeric IDs as 400, preventing parse errors from becoming 500.
- The service is only called inside the publisher chain; there is no nested `subscribe()`.

### 8.10. TaskRoutes.java — router function

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class TaskRoutes {

    @Bean
    RouterFunction<ServerResponse> taskRoutes(TaskHandler handler) {
        return RouterFunctions.route()
                .GET("/functional/tasks", handler::list)
                .GET("/functional/tasks/{id}", handler::get)
                .POST("/functional/tasks", handler::create)
                .POST("/functional/tasks/{id}/complete",
                        handler::complete)
                .build();
    }
}
```

The functional routes run alongside the controller because the prefixes differ. The router does not perform business logic; it only wires request predicates to handlers.

## 9. Contract Tests: Verifying Both Adapters with the Same Expectations

`WebTestClient` can test controllers bound directly or call a real server. This lesson uses `RANDOM_PORT` so both adapters go through the real HTTP stack and codecs in the test process.

### 9.1. ApiContractIntegrationTest.java

```java
package demo;

import java.util.List;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import demo.ApiModels.ApiError;
import demo.ApiModels.CreateTaskRequest;
import demo.ApiModels.TaskView;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ApiContractIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void bothStylesHonorTheSameSuccessContract() {
        assertSuccessContract("/controller");
        assertSuccessContract("/functional");
    }

    private void assertSuccessContract(String prefix) {
        AtomicLong id = new AtomicLong();

        client.post()
                .uri(prefix + "/tasks")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateTaskRequest("Prepare release"))
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists(HttpHeaders.LOCATION)
                .expectBody(TaskView.class)
                .value(task -> {
                    assertTrue(task.id() > 0);
                    assertEquals("Prepare release", task.title());
                    assertFalse(task.completed());
                    id.set(task.id());
                });

        long taskId = id.get();

        client.get()
                .uri(prefix + "/tasks/{id}", taskId)
                .exchange()
                .expectStatus().isOk()
                .expectBody(TaskView.class)
                .value(task -> {
                    assertEquals(taskId, task.id());
                    assertEquals("Prepare release", task.title());
                    assertFalse(task.completed());
                });

        client.post()
                .uri(prefix + "/tasks/{id}/complete", taskId)
                .exchange()
                .expectStatus().isOk()
                .expectBody(TaskView.class)
                .value(task -> {
                    assertEquals(taskId, task.id());
                    assertTrue(task.completed());
                });

        client.get()
                .uri(prefix + "/tasks")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(TaskView.class)
                .value(tasks -> assertTrue(
                        tasks.stream().anyMatch(task ->
                                task.id() == taskId
                                && task.completed())));
    }

    @Test
    void bothStylesReturnTheSameValidationError() {
        for (String prefix : List.of("/controller", "/functional")) {
            client.post()
                    .uri(prefix + "/tasks")
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(new CreateTaskRequest(" "))
                    .exchange()
                    .expectStatus().isBadRequest()
                    .expectBody(ApiError.class)
                    .value(error -> {
                        assertEquals(
                                "VALIDATION_FAILED", error.code());
                        assertTrue(error.message().contains("title"));
                        assertTrue(error.message()
                                .contains("must not be blank"));
                    });
        }
    }

    @Test
    void bothStylesReturn404ForMissingTask() {
        for (String prefix : List.of("/controller", "/functional")) {
            client.get()
                    .uri(prefix + "/tasks/999999")
                    .exchange()
                    .expectStatus().isNotFound();

            client.post()
                    .uri(prefix + "/tasks/999999/complete")
                    .exchange()
                    .expectStatus().isNotFound();
        }
    }

    @Test
    void functionalEndpointRejectsNonNumericId() {
        client.get()
                .uri("/functional/tasks/not-a-number")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(ApiError.class)
                .value(error ->
                        assertEquals("INVALID_ID", error.code()));
    }
}
```

The test suite verifies:

1. The same create → read → complete → list flow across both prefixes.
2. The same 201 status, Location header, and JSON response.
3. The same 400 validation error schema.
4. The same 404 behavior when a resource does not exist.
5. The functional handler returns an explicit 400 when the id is not numeric.

This test uses a real HTTP server on loopback with a random port. It verifies routing, binding, validation, codecs, and the response contract; it does not test a real database, production TLS, or high concurrent load.

### 9.2. Running Tests

In the project directory:

```bash
mvn test
```

With JDK 17+, Maven, and downloadable dependencies, **4 test methods passing, 0 failures, 0 errors** is expected. This is the expected outcome from the assertions in the source, not a claim that a build was executed in this environment.

## 10. Functional Filters, WebFilter, and Cross-Cutting Concerns

Functional endpoints have `HandlerFilterFunction` to wrap handlers. Example recording processing time:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> timing =
        (request, next) -> {
            long started = System.nanoTime();

            return next.handle(request)
                    .doFinally(signal -> {
                        long elapsed = System.nanoTime() - started;
                        // Record metric: route, signal, and elapsed.
                    });
        };
```

This is an illustrative filter snippet; import `HandlerFilterFunction` and `SignalType` when using it. You can attach the filter to a router with `.filter(timing)` before `.build()`. Do not log raw bodies or sensitive data.

`WebFilter` operates at the WebFlux WebHandler chain layer and can apply to both annotated controllers and functional endpoints. If a cross-cutting concern must apply application-wide (trace ID, security, CORS, logging, metrics), a global WebFilter is usually the right choice. `HandlerFilterFunction` fits when you want to scope a filter to one router/group of functional routes.

Do not confuse `HandlerFilterFunction` with Servlet Filters; a WebFlux application does not necessarily have a Servlet container.

## 11. Content Negotiation and Streaming

Both styles use the same WebFlux codecs and content negotiation:

- `Accept` determines the representation the client wants to receive.
- `Content-Type` describes the representation of the request/response body.
- The Jackson codec can serialize records/DTOs into JSON.
- `Flux<T>` can be encoded as a JSON array or a streaming format depending on media type and writer.
- `text/event-stream` is typically used for SSE.
- `application/x-ndjson` can be used for line-delimited JSON records.

Annotated controllers can declare `produces`/`consumes` directly on mappings. Functional routers can add `accept`/`contentType` predicates or set the content type when building the ServerResponse.

Controller example:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(index -> ServerSentEvent.builder(
                    "tick-" + index).build());
}
```

A functional handler can build a streaming response:

```java
return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(events, ServerSentEvent.class);
```

These are illustrative snippets; you need to define the `events` source and imports. Do not call `collectList()` on an infinite stream. Handle cancellation on client disconnect and release resources.

## 12. When to Choose Which Style?

### Choose Annotated Controllers When:

- The API is primarily standard CRUD/REST.
- You want readable argument binding, validation annotations, and method mappings.
- The team is already familiar with controllers/advice and wants to leverage conventions.
- Most methods share a similar structure.

### Choose Functional Endpoints When:

- You want an explicit route table and modular route composition.
- There are many predicates across method/path/header/content type.
- You want explicit control over how each handler reads requests and builds responses.
- An API gateway/protocol adapter has distinct, explicit routing logic.

### Use Both Together When:

Spring WebFlux allows controllers and functional routes to coexist. One module can use controllers for CRUD and functional routes for webhooks or protocol-specific endpoints. Avoid registering the same method/path in both places unintentionally; route conflicts make behavior unpredictable and tests harder to read.

### Practical Selection Criteria

Do not decide based on line counts or assumed performance. Evaluate:

- Readability and onboarding.
- How security/validation/error mapping are applied.
- Routing complexity.
- Contract testability.
- Existing codebase conventions.
- Observability and maintainability.
- Streaming and lifecycle requirements.

If two adapters must share the same business behavior, keep a common service and test the same contract so switching styles does not introduce regressions.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking functional endpoints are Spring MVC functional views | Wrong API and runtime chosen | Use WebFlux's `RouterFunction`/`ServerRequest`/`ServerResponse`. |
| Thinking a WebFlux controller is an MVC controller | Mixed dependencies and blocking expectations | Use the WebFlux starter and reactive return types. |
| Registering the same route in both controller and RouterFunction | Route conflict or unexpected handler selected | Use prefixes/profiles or enable only one adapter on the canonical path. |
| Putting business logic in the router | Hard to test and reuse | Router only routes; handler calls service. |
| Duplicating business logic across both handlers | Behavior drift | Extract a shared service/application layer. |
| Functional handler forgetting to parse input | NumberFormatException can become 500 | Map parse errors to 400. |
| Controller and functional returning different error schemas | Clients have to handle two contracts | Use a shared ApiError and test both. |
| Forgetting Location when creating a resource | Client has no standard URI to access the resource | Return 201 + Location per contract. |
| Calling subscribe in a handler | Detaches lifecycle, loses cancellation/error context | Return and compose Mono/Flux. |
| Blocking in WebFlux | Blocks the event loop | Use reactive APIs or an appropriate scheduler for blocking work. |
| Calling collectList on a large/infinite stream | Increases memory, loses streaming | Return an appropriate Publisher body. |
| Only unit-testing handlers | Misses routing/codec/status/headers | Add WebTestClient integration tests. |
| Only testing success cases | Misses 400/404/error contract | Test invalid input, missing resources, and decode errors. |
| Assuming functional is always faster | Conclusion without data | Benchmark with the same workload and environment if performance matters. |
| Using WebFilter instead of HandlerFilterFunction without considering scope | Filter applies more broadly than intended | Choose global or router-local based on responsibility. |
| Not testing for route conflicts | Production may invoke the wrong handler | Test method/path for all enabled adapters. |

## 14. Self-Check Questions

**Question 1.** What are the two ways to create endpoints in Spring WebFlux?  
**Answer:** Annotated controllers and functional endpoints with RouterFunction/HandlerFunction.

**Question 2.** Can a WebFlux controller return a Flux?  
**Answer:** Yes. The framework handles the Publisher and serializes the body according to codec/media type.

**Question 3.** What is the role of RouterFunction?  
**Answer:** Matches request predicates (method/path/header/content type...) to a HandlerFunction.

**Question 4.** What does HandlerFunction accept and return?  
**Answer:** Accepts ServerRequest and returns Mono<ServerResponse>.

**Question 5.** How does a functional handler read a path variable?  
**Answer:** Uses `request.pathVariable("id")` and then parses/validates the data type manually.

**Question 6.** Why is a shared service needed between the two adapters?  
**Answer:** Avoids duplicating business rules and keeps behavior consistent when changing HTTP declaration styles.

**Question 7.** Where are controller validation errors usually handled?  
**Answer:** WebExchangeBindException can be mapped via RestControllerAdvice/ExceptionHandler.

**Question 8.** How does a functional handler validate a DTO?  
**Answer:** Decodes the body into a DTO, invokes Jakarta Validator or a helper, and returns the appropriate status/error contract.

**Question 9.** Can both adapters run together in the same app?  
**Answer:** Yes, as long as routes do not conflict; the demo lesson uses two separate prefixes.

**Question 10.** Are functional endpoints always faster than controllers?  
**Answer:** No. Both use the same reactive runtime; benchmarking under identical conditions is required to draw conclusions.

**Question 11.** When should WebFilter be used instead of HandlerFilterFunction?  
**Answer:** WebFilter for cross-cutting concerns across the entire WebFlux chain; HandlerFilterFunction for a group of functional routes.

**Question 12.** Why should you not subscribe manually inside a handler?  
**Answer:** Because it detaches lifecycle, cancellation, context, and error propagation from the current HTTP request.

## 15. Takeaways

- Annotated controllers declare endpoints with annotations; functional endpoints separate route predicates from handlers.
- Both are WebFlux, supporting Mono/Flux, codecs, non-blocking I/O, and cancellation.
- RouterFunction routes requests; HandlerFunction reads ServerRequest and creates ServerResponse.
- Separate DTOs, validation, business service, and persistence so both adapters share the same logic.
- Maintain a consistent contract for method/path, status, Location, content type, JSON, and error schema.
- Use WebTestClient to verify both adapters against the same contract test suite.
- Do not call subscribe/block in handlers, and do not collect unbounded streams into a list.
- Choose the style based on clarity, route organization, maintainability, and conventions; do not assume functional is faster by default.

## References

1. [Spring Framework – Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html): request mapping, argument binding, return values, and validation.
2. [Spring Framework – Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): RouterFunction, HandlerFunction, ServerRequest, and ServerResponse.
3. [Spring Framework – WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): validation in WebFlux controllers.
4. [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing controllers and HTTP servers.
5. [Spring Boot 3.3 – Testing Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): RANDOM_PORT and WebTestClient integration.
6. [Project Reactor – Core Reference](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, scheduling, cancellation, and backpressure.
7. [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/3.0/): constraint annotations and the Validator API.
