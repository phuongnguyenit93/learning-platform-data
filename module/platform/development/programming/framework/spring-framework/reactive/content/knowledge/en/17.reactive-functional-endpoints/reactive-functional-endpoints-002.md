# Declaring Routes with RouterFunctions.route in Spring WebFlux

## 1. WebFlux.fn and the Role of RouterFunctions.route

Spring WebFlux supports two models for building HTTP endpoints:

- **Annotation-based:** uses `@RestController`, `@GetMapping`, `@PostMapping`, and `@RequestBody`.
- **Functional endpoints (WebFlux.fn):** uses functions and immutable objects to describe how to match requests, invoke handlers, and create responses.

A functional endpoint consists of two components:

- **`RouterFunction<ServerResponse>`** receives a `ServerRequest` and finds the appropriate handler. If the route matches, the router supplies the handler function; if it does not match, the router returns an empty publisher so the framework considers the next router.
- **`HandlerFunction<ServerResponse>`** receives a `ServerRequest` and returns a `Mono<ServerResponse>`. The handler reads the path, query, headers, or body, calls a reactive service, and then creates the response.

`RouterFunctions.route()` provides a fluent builder to declare routes by HTTP method, path, and predicate. A minimal example:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/hello", request ->
            ServerResponse.ok().bodyValue("Hello WebFlux"))
        .build();
~~~

When a client calls `GET /hello`, the router matches the method and path and then invokes the lambda handler. The handler returns a `Mono<ServerResponse>`; WebFlux subscribes and writes the response using the reactive mechanism.

**Principle:** the route decides which request goes to which handler; the handler decides how to process the request and create the response. `RouterFunctions.route()` does not open sockets on its own, does not subscribe to services on its own, and does not replace the server runtime.

## 2. Core Types and Contracts

| Component | Role | Example |
| --- | --- | --- |
| `ServerRequest` | Represents the incoming request; provides the method, URI, headers, query, path variables, and body | `request.pathVariable("id")` |
| `ServerResponse` | An immutable response containing the status, headers, and a body publisher | `ServerResponse.ok().bodyValue(user)` |
| `HandlerFunction` | A function that handles one request and returns a publisher of the response | `request -> ServerResponse.ok().build()` |
| `RouterFunction` | A function that finds the appropriate handler for a request | The result of `RouterFunctions.route().build()` |
| `RequestPredicate` | A condition for matching a request | method, path, Accept, Content-Type |
| `HandlerFilterFunction` | Wraps a handler to process before/after or to block a request | logging, permission checks |
| `RouterFunctions` | Utility and builder for creating, combining, nesting, or converting a router into an HttpHandler | `RouterFunctions.route()` |

WebFlux.fn requests and responses have an immutable contract. When you need to transform a request in a filter, use `ServerRequest.from(request)` to create a new request. When you need to add a status, header, or body, use the `ServerResponse` builder.

A handler typically has the signature:

~~~java
Mono<ServerResponse> handle(ServerRequest request) {
    return ServerResponse.ok().bodyValue("ready");
}
~~~

`Mono<ServerResponse>` represents a response that is created asynchronously. A handler can wait for a repository or WebClient before deciding the status and body.

## 3. Declaring Routes with the Builder

### 3.1. Shortcuts by HTTP method

The builder provides commonly used shortcuts:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/products", handler::list)
        .GET("/products/{id}", handler::get)
        .POST("/products", handler::create)
        .PUT("/products/{id}", handler::update)
        .PATCH("/products/{id}", handler::patch)
        .DELETE("/products/{id}", handler::delete)
        .build();
~~~

Method references such as `handler::get` point to methods that take a `ServerRequest` and return a `Mono<ServerResponse>`. A path can contain variables such as `{id}`; the handler gets the value with `request.pathVariable("id")`.

The routes in the builder are combined into a single RouterFunction when `build()` is called. You can declare the router as a Spring bean:

~~~java
@Configuration
class ApiRoutes {
    @Bean
    RouterFunction<ServerResponse> apiRoutes(ProductHandler handler) {
        return RouterFunctions.route()
            .GET("/api/products", handler::list)
            .GET("/api/products/{id}", handler::get)
            .POST("/api/products", handler::create)
            .build();
    }
}
~~~

Spring detects beans of type `RouterFunction<?>` and feeds them into the WebFlux infrastructure to route requests. There is no need to call `subscribe()` yourself in the configuration bean.

### 3.2. Creating a route directly with a predicate

Besides the builder shortcuts, you can create a route from a predicate and a handler:

~~~java
RequestPredicate jsonGet =
    RequestPredicates.GET("/api/products")
        .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(jsonGet, handler::list);
~~~

This approach is useful when the matching condition is complex or when you need to create a separate predicate before combining routers. The builder also has an overload that accepts a predicate:

~~~java
RouterFunction<ServerResponse> route =
    RouterFunctions.route()
        .GET("/api/products",
            RequestPredicates.accept(MediaType.APPLICATION_JSON),
            handler::list)
        .build();
~~~

A predicate can additionally require a header, Content-Type, query parameter, or custom condition alongside the method and path.

## 4. RequestPredicate: Conditions for a Route to Match

`RequestPredicate` represents a condition on a request. `RequestPredicates` provides factories for common conditions.

| Predicate | Condition |
| --- | --- |
| `GET("/path")` | HTTP GET and a matching path |
| `POST("/path")` | HTTP POST and a matching path |
| `method(HttpMethod.PUT)` | A specific HTTP method |
| `path("/api/**")` | A path matching the pattern |
| `pathExtension("json")` | The path extension |
| `accept(MediaType.APPLICATION_JSON)` | The client accepts JSON |
| `contentType(MediaType.APPLICATION_JSON)` | The request body has a JSON Content-Type |
| `queryParam("mode", predicate)` | The query parameter satisfies the predicate |
| `headers(predicate)` | The headers satisfy the condition |
| `header(name, predicate)` | A specific header satisfies the condition |
| `cookie(name, predicate)` | A specific cookie satisfies the condition |

Example that only accepts POST with a JSON Content-Type and a client that accepts JSON:

~~~java
RequestPredicate jsonPost =
    RequestPredicates.POST("/api/products")
        .and(RequestPredicates.contentType(MediaType.APPLICATION_JSON))
        .and(RequestPredicates.accept(MediaType.APPLICATION_JSON));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(jsonPost, handler::create);
~~~

When a predicate does not match, that route's handler is not invoked. The RouterFunction can continue to consider the next route; if no route matches, the request is passed to WebFlux's mechanism for handling the case where no handler is found.

### 4.1. Combining and, or, and negate

- `and(other)`: both conditions must be true.
- `or(other)`: at least one condition is true.
- `negate()`: inverts the result of the condition.

~~~java
RequestPredicate jsonOrText =
    RequestPredicates.accept(MediaType.APPLICATION_JSON)
        .or(RequestPredicates.accept(MediaType.TEXT_PLAIN));

RequestPredicate apiPath =
    RequestPredicates.path("/api/**");

RequestPredicate publicPath = apiPath.negate();
~~~

Use `and` to tighten route conditions, `or` when one handler supports multiple kinds of requests, and `negate` for excluded path areas. A predicate should describe a routing condition and should not contain the entire business logic.

### 4.2. Query parameter

Example that only matches when `view=compact`:

~~~java
RequestPredicate compactView =
    RequestPredicates.GET("/api/products")
        .and(RequestPredicates.queryParam(
            "view",
            value -> value.equals("compact")
        ));

RouterFunction<ServerResponse> route =
    RouterFunctions.route(compactView, handler::compactList);
~~~

If the parameter is optional or has multiple values, you can let the route match only the path/method and then read the query with `request.queryParam("view")` in the handler.

### 4.3. Path variable

~~~java
RouterFunction<ServerResponse> route =
    RouterFunctions.route()
        .GET("/api/products/{id}", handler::get)
        .build();
~~~

The handler reads the variable:

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    String rawId = request.pathVariable("id");
    return ServerResponse.ok().bodyValue("id=" + rawId);
}
~~~

`pathVariable` returns a string. If you need a number or a UUID, the handler must parse it and handle invalid data; do not assume the path variable has already been converted to a domain type.

## 5. Route Order and How to Avoid Shadowed Routes

Router functions are evaluated in order. The first route that matches supplies the handler that is used. This differs from annotation-based mapping, where Spring has rules for choosing the most specific mapping.

An example that is prone to errors:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/users/{id}", handler::get)
        .GET("/api/users/search", handler::search)
        .build();
~~~

The `{id}` variable route can match the string `search`, so the search route after it is never invoked. Declare the specific route first:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/users/search", handler::search)
        .GET("/api/users/{id}", handler::get)
        .build();
~~~

Ordering principles:

1. Static and specific routes first.
2. Routes with additional predicates before general routes.
3. General path-variable routes after.
4. Fallback routes last.

When there are multiple RouterFunction beans, WebFlux uses the bean order and combines them in RouterFunctionMapping. If multiple beans match at once, the configuration order can affect which handler is chosen. Check for path collisions and specify ordering only when truly needed.

## 6. Nested Routes: Grouping Routes That Share a Path or Predicate

If many routes share the prefix `/api/users`, you can use `path` to avoid repetition:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/api/users", users -> users
            .GET(accept(MediaType.APPLICATION_JSON), handler::list)
            .GET("/{id}", accept(MediaType.APPLICATION_JSON), handler::get)
            .POST(handler::create))
        .build();
~~~

The inner paths are combined with the shared prefix:

| Inner declaration | Actual path |
| --- | --- |
| `GET(accept(JSON), handler::list)` | GET /api/users |
| `GET("/{id}", accept(JSON), handler::get)` | GET /api/users/{id} |
| `POST(handler::create)` | POST /api/users |

You can nest by a predicate other than a path, for example requiring Accept JSON for a group of routes:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .path("/api/users", users -> users
            .nest(RequestPredicates.accept(MediaType.APPLICATION_JSON), json -> json
                .GET("/{id}", handler::get)
                .GET(handler::list))
            .POST(handler::create))
        .build();
~~~

Nested routes are useful when a group of endpoints shares a path, header, or condition. Avoid nesting too deeply, which makes routes hard to find; one or two meaningful levels are usually enough.

## 7. Combining Multiple RouterFunctions

You can split routes by domain or module and then combine them:

~~~java
RouterFunction<ServerResponse> userRoutes = userRoutes(userHandler);
RouterFunction<ServerResponse> orderRoutes = orderRoutes(orderHandler);

RouterFunction<ServerResponse> api =
    userRoutes.and(orderRoutes);
~~~

The main APIs:

- `RouterFunction.and(other)` combines the current router with another router.
- `RouterFunction.andRoute(predicate, handler)` adds a route from a predicate and a handler.
- The builder's `add(otherRouter)` puts an already created router into the builder.
- `build()` finishes the builder and returns the RouterFunction.

Example of adding a health route:

~~~java
RouterFunction<ServerResponse> routes =
    userRoutes
        .and(orderRoutes)
        .andRoute(RequestPredicates.GET("/health"),
            request -> ServerResponse.ok().bodyValue("UP"));
~~~

The combination order still matters. If the first router has already matched, the later router is not considered for that request. Organizing routes by module aids maintenance, but you still need to check for collisions between paths.

## 8. HandlerFunction: Reading the Request and Creating a ServerResponse

A handler receives a `ServerRequest` and returns a `Mono<ServerResponse>`. You can write a small lambda:

~~~java
HandlerFunction<ServerResponse> hello =
    request -> ServerResponse.ok().bodyValue("Hello");
~~~

In real applications, you should group related handlers into a class to separate route declaration from processing logic.

### 8.1. Reading request information

`ServerRequest` provides the method, URI, path, path variables, query parameters, headers, cookies, form data, multipart data, and body.

~~~java
Mono<ServerResponse> describe(ServerRequest request) {
    String id = request.pathVariable("id");
    String agent = request.headers().firstHeader("User-Agent");
    String query = request.queryParam("q").orElse("");

    return ServerResponse.ok().bodyValue(
        "id=" + id + ", q=" + query + ", agent=" + agent
    );
}
~~~

In production code, avoid putting all sensitive headers/cookies into logs or responses. Only take the fields you need.

### 8.2. Reading the request body as a Mono

~~~java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateUserRequest.class)
        .flatMap(input -> service.create(input.name())
            .flatMap(user -> ServerResponse
                .created(URI.create("/api/users/" + user.id()))
                .bodyValue(user)));
}
~~~

`bodyToMono` decodes a body into an object. Reading and decoding happen reactively; the handler composes the publisher with `flatMap` to wait for the service without calling `block()`.

If the body may be absent, you need to decide the semantics:

~~~java
return request.bodyToMono(CreateUserRequest.class)
    .flatMap(this::save)
    .switchIfEmpty(
        ServerResponse.badRequest().bodyValue("Request body is required")
    );
~~~

If the body is required but missing, return 400 or a status appropriate for the API. If the body is malformed or cannot be decoded, WebFlux may emit an error such as `ServerWebInputException`; handle it centrally or convert it into a deliberate response.

### 8.3. Reading a streaming body as a Flux

~~~java
Mono<ServerResponse> importEvents(ServerRequest request) {
    Flux<EventInput> events =
        request.bodyToFlux(EventInput.class);

    return service.importEvents(events)
        .then(ServerResponse.accepted().build());
}
~~~

`bodyToFlux` is suitable when the request contains multiple elements or streaming data. Do not collect the whole stream into a list if it is large or if you need to process element by element. Pay attention to backpressure and make sure an error in any element is handled properly.

### 8.4. Creating a ServerResponse

| API | Meaning |
| --- | --- |
| `ServerResponse.ok()` | 200 OK |
| `ServerResponse.created(uri)` | 201 Created with Location |
| `ServerResponse.accepted()` | 202 Accepted |
| `ServerResponse.noContent()` | 204 No Content |
| `ServerResponse.badRequest()` | 400 Bad Request |
| `ServerResponse.notFound()` | 404 Not Found |
| `ServerResponse.status(code)` | Custom status |

Use `bodyValue(value)` for an existing value; use `body(publisher, elementClass)` for a publisher; use `build()` when there is no body.

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    return service.findById(request.pathVariable("id"))
        .flatMap(user -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(user))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

This snippet turns an empty result into a 404. If an error occurs, it is still an onError; you need separate error mapping according to the business domain.

## 9. Validation and Error Handling in Functional Handlers

Functional endpoints can still use Spring's validation. You can inject a Validator or use Bean Validation according to the application configuration.

Example of simple validation:

~~~java
private Mono<ServerResponse> validateAndCreate(
        CreateUserRequest input) {
    if (input.name() == null || input.name().isBlank()) {
        return ServerResponse.badRequest()
            .bodyValue("name is required");
    }

    return service.create(input.name())
        .flatMap(user -> ServerResponse
            .created(URI.create("/api/users/" + user.id()))
            .bodyValue(user));
}
~~~

The handler calls:

~~~java
return request.bodyToMono(CreateUserRequest.class)
    .flatMap(this::validateAndCreate)
    .switchIfEmpty(ServerResponse.badRequest().build());
~~~

For complex validation, use a Spring Validator or Jakarta Bean Validation. When an error is detected, you can throw a `ServerWebInputException` so WebFlux handles it according to the configured error handling, or map it to a specific ServerResponse.

### 9.1. onErrorResume in a handler

~~~java
Mono<ServerResponse> response = service.findById(id)
    .flatMap(user -> ServerResponse.ok().bodyValue(user))
    .switchIfEmpty(ServerResponse.notFound().build())
    .onErrorResume(IllegalArgumentException.class,
        error -> ServerResponse.badRequest()
            .bodyValue("Invalid identifier"));
~~~

Only map the error types the handler clearly understands. Do not turn every error into a 400: database errors, network errors, and programming bugs may need a 5xx response or a common error handler.

## 10. Filters: before, after, and HandlerFilterFunction

Filters add behavior around a handler without repeating code in every route.

- `before(Function<ServerRequest, ServerRequest>)`: transforms the request before the handler, for example adding an internal header.
- `after(BiFunction<ServerRequest, ServerResponse, ServerResponse>)`: observes or transforms the response after the handler.
- `filter(HandlerFilterFunction)`: receives the request and the next handler, and can either call onward or return a response early.

Example of logging the response:

~~~java
RouterFunction<ServerResponse> routes =
    RouterFunctions.route()
        .GET("/api/hello", request ->
            ServerResponse.ok().bodyValue("hello"))
        .filter((request, next) ->
            next.handle(request)
                .doOnNext(response ->
                    System.getLogger("routes").log(
                        System.Logger.Level.INFO,
                        request.methodName() + " " + request.path()
                            + " -> " + response.statusCode()
                    )))
        .build();
~~~

A filter can block a request before the handler:

~~~java
.filter((request, next) -> {
    String token = request.headers().firstHeader("X-Internal-Token");
    if (!"expected-value".equals(token)) {
        return ServerResponse.status(HttpStatus.UNAUTHORIZED).build();
    }
    return next.handle(request);
})
~~~

This only illustrates the mechanism. In a real application, do not hard-code a token; use Spring Security or an authentication mechanism that manages secrets, expiry, and authorization. A router filter does not replace the security chain.

**Filter scope in nested routes:** a filter attached to a builder applies to the routes that builder creates. A filter placed in a nested builder may apply only to the nested group; an outer-level filter may apply to the nested routes as well. Read the filter's position in the builder tree to avoid missing routes.

## 11. Organizing Routes by Module in Spring Boot

An easy-to-maintain structure:

~~~text
src/main/java/demo/
  DemoApplication.java
  user/
    User.java
    CreateUserRequest.java
    UserService.java
    UserHandler.java
    UserRoutes.java
  order/
    OrderHandler.java
    OrderRoutes.java
~~~

Roles:

- `UserRoutes` only declares method/path/predicate and wires them to handlers.
- `UserHandler` reads the request, calls the service, and creates the response.
- `UserService` contains the business logic and data access.
- DTOs/domain models describe the input/output data.
- `DemoApplication` starts Spring Boot.

Example bean configuration:

~~~java
@Configuration
class UserRoutes {
    @Bean
    RouterFunction<ServerResponse> userRouter(UserHandler handler) {
        return RouterFunctions.route()
            .path("/api/users", users -> users
                .GET(handler::list)
                .GET("/{id}", handler::get)
                .POST(handler::create))
            .build();
    }
}
~~~

Spring Boot's WebFlux starter auto-configures the components needed to run a RouterFunction bean in the DispatcherHandler. The infrastructure includes RouterFunctionMapping to find routers, HandlerFunctionAdapter to invoke handlers, and ServerResponseResultHandler to write responses.

You can use functional endpoints together with annotation-based controllers in one application. Plan paths and router order clearly so that no two endpoints accidentally accept the same request.

## 12. A Complete Java 17+ Spring Boot WebFlux Demo

The following example builds a user API with WebFlux.fn. It demonstrates a GET list, GET by ID, POST to create a user, a JSON predicate, a router builder, a handler class, and WebTestClient testing.

### 12.1. Directory structure

~~~text
functional-router-demo/
  build.gradle
  src/main/java/demo/
    DemoApplication.java
    User.java
    CreateUserRequest.java
    UserService.java
    UserHandler.java
    UserRoutes.java
  src/test/java/demo/
    UserRoutesTest.java
~~~

### 12.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

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

Spring Boot manages the versions of Spring Framework, Reactor, and compatible dependencies through dependency management. Do not pin separate Spring Framework or Reactor versions yourself unless there is a compatibility reason.

### 12.3. DemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 12.4. User.java and CreateUserRequest.java

~~~java
package demo;

public record User(long id, String name) {
}
~~~

~~~java
package demo;

public record CreateUserRequest(String name) {
}
~~~

### 12.5. UserService.java

~~~java
package demo;

import java.util.Comparator;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class UserService {
    private final ConcurrentMap<Long, User> users =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(1);

    public UserService() {
        users.put(1L, new User(1L, "Mai"));
    }

    public Flux<User> findAll() {
        return Flux.defer(() -> Flux.fromIterable(
            users.values().stream()
                .sorted(Comparator.comparingLong(User::id))
                .toList()
        ));
    }

    public Mono<User> findById(long id) {
        return Mono.defer(() -> Mono.justOrEmpty(users.get(id)));
    }

    public Mono<User> create(String name) {
        return Mono.fromSupplier(() -> {
            long id = sequence.incrementAndGet();
            User user = new User(id, name);
            users.put(id, user);
            return user;
        });
    }
}
~~~

The service uses a ConcurrentHashMap to demo in-memory data storage. In a real application, replace it with a reactive repository or an appropriate data source. `defer` and `fromSupplier` make the read/write operations execute when the subscription runs.

### 12.6. UserHandler.java

~~~java
package demo;

import java.net.URI;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@Component
public class UserHandler {
    private final UserService service;

    public UserHandler(UserService service) {
        this.service = service;
    }

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(service.findAll(), User.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        long id;
        try {
            id = Long.parseLong(request.pathVariable("id"));
        } catch (NumberFormatException error) {
            return ServerResponse.badRequest().build();
        }

        return service.findById(id)
            .flatMap(user -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(user))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateUserRequest.class)
            .flatMap(input -> {
                if (input.name() == null || input.name().isBlank()) {
                    return ServerResponse.badRequest()
                        .bodyValue("name is required");
                }

                return service.create(input.name())
                    .flatMap(user -> ServerResponse
                        .created(URI.create("/api/users/" + user.id()))
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(user));
            })
            .switchIfEmpty(ServerResponse.badRequest()
                .bodyValue("request body is required"))
            .onErrorResume(ServerWebInputException.class, error ->
                ServerResponse.badRequest()
                    .bodyValue("invalid request body"));
    }
}
~~~

The handler returns a `Mono<ServerResponse>` on every branch. GET parses the ID and returns 404 when the service is empty. POST reads the JSON body, validates the name, creates the user, and returns 201 with a Location. Request decode errors are mapped to 400. A real application should use a validator and a standardized error body.

### 12.7. UserRoutes.java

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class UserRoutes {
    @Bean
    RouterFunction<ServerResponse> userRoutes(UserHandler handler) {
        return RouterFunctions.route()
            .GET("/api/users", handler::list)
            .GET("/api/users/{id}", handler::get)
            .POST("/api/users",
                RequestPredicates.contentType(MediaType.APPLICATION_JSON),
                handler::create)
            .build();
    }
}
~~~

The POST route only matches when the request has a JSON Content-Type. The predicate belongs to routing; the handler is responsible for decoding and processing the body. If you need to check the Accept header, additionally combine `RequestPredicates.accept(MediaType.APPLICATION_JSON)`.

### 12.8. Running the application

In the project directory:

~~~bash
./gradlew bootRun
~~~

Or if Gradle is installed:

~~~bash
gradle bootRun
~~~

Call the API:

~~~bash
curl -i http://localhost:8080/api/users
curl -i http://localhost:8080/api/users/1
curl -i http://localhost:8080/api/users/99
curl -i -X POST http://localhost:8080/api/users -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"An"}'
~~~

Key results:

| Request | Expected status | Content |
| --- | --- | --- |
| GET /api/users | 200 | A JSON array containing user Mai |
| GET /api/users/1 | 200 | JSON user Mai |
| GET /api/users/99 | 404 | No such user |
| POST /api/users with name An | 201 | New user JSON, Location /api/users/2 |
| POST without a body | 400 | Message: request body required |
| POST with an empty name | 400 | Message: name is required |

The data in the demo is only stored in RAM and is re-initialized when the application restarts.

## 13. Testing Routes with WebTestClient

You can test a functional router directly or test the whole application. With Spring Boot, use `@SpringBootTest` and `@AutoConfigureWebTestClient` to send HTTP requests through a test server.

Create `src/test/java/demo/UserRoutesTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class UserRoutesTest {
    @Autowired
    WebTestClient client;

    @Test
    void listUsersReturnsJson() {
        client.get()
            .uri("/api/users")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$[0].id").isEqualTo(1)
            .jsonPath("$[0].name").isEqualTo("Mai");
    }

    @Test
    void existingUserReturns200() {
        client.get()
            .uri("/api/users/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody(User.class)
            .isEqualTo(new User(1L, "Mai"));
    }

    @Test
    void missingUserReturns404() {
        client.get()
            .uri("/api/users/999")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .isEmpty();
    }

    @Test
    void createUserReturns201AndLocation() {
        client.post()
            .uri("/api/users")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateUserRequest("An"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().valueEquals("Location", "/api/users/2")
            .expectBody(User.class)
            .isEqualTo(new User(2L, "An"));
    }

    @Test
    void emptyCreateBodyReturns400() {
        client.post()
            .uri("/api/users")
            .contentType(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

Run `./gradlew test`. The five tests check that the route is registered, the handler is invoked, the status/header/body, and the empty-body branch. With a RAM-backed service, if you run tests in parallel or reuse the same context for a long time, you need to isolate the test data or reset the repository between tests.

You can test a router in isolation with `WebTestClient.bindToRouterFunction(router).build()` when you want to verify a route without starting the Spring Boot server. That approach is useful for fast unit tests; an integration test additionally verifies that Spring discovers the RouterFunction bean and connects it with the WebFlux runtime.

## 14. Combining Functional Endpoints with Annotation-Based Controllers

WebFlux.fn and annotated controllers both run on the reactive core. An application can have annotated controllers for ordinary CRUD endpoints, a functional router for a group of endpoints that need centralized declaration, and handler classes to reuse request-handling logic.

The WebFlux infrastructure uses RouterFunctionMapping to discover router beans, HandlerFunctionAdapter to invoke handlers, and ServerResponseResultHandler to write responses. There is no need to call the router from a controller yourself or to write the body into the server response yourself.

If both mechanisms declare the same path/method, the handling depends on the mapping order and configuration. Avoid duplicate declarations or deliberately check the mapping order. When routes belong to separate modules, setting a clear prefix such as `/api/internal` or `/api/events` helps reduce conflicts.

## 15. Serving Resources and Advanced Route Features

A functional router can also serve static resources. For example, map `/resources/**` to a resource directory:

~~~java
Resource location = new FileUrlResource("public-resources/");
RouterFunction<ServerResponse> resources =
    RouterFunctions.resources("/resources/**", location);
~~~

You can use `RouterFunctions.route().resource(predicate, resource).build()` to redirect a group of paths to a resource, for example the index of a Single Page Application. Configure the paths and file access permissions carefully; do not casually expose sensitive directories.

Some other features:

- **API version predicate:** a route can match a version when API versioning has been enabled in the WebFlux configuration.
- **CORS:** functional endpoints support CORS through `CorsWebFilter`.
- **Custom predicate:** create your own RequestPredicate when the route condition is not covered by the available factories.
- **Nested predicate:** group routes by path, Accept header, or a shared condition.
- **Router composition:** combine the routers of modules with `and`, `add`, or `andRoute`.

Do not put complex business conditions into a RequestPredicate. The route should decide which endpoint the request belongs to; the handler/service decides whether the request is valid and how to carry out the business logic.

## 16. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Declaring a general route before a specific route | The specific route may be shadowed by the earlier route | Put static/specific routes first |
| Forgetting to call `build()` | The RouterFunction builder is not finished | End the builder with `build()` |
| A handler returns a type other than `Mono<ServerResponse>` | Violates the reactive WebFlux.fn contract | Return a publisher of ServerResponse |
| Calling `subscribe()` in a handler | Detaches the side effect from the HTTP request lifecycle | Compose Mono/Flux and return the publisher |
| Calling `block()` in a handler | Blocks the event loop | Use map/flatMap and reactive services |
| Using a path variable without parsing/validating | A parse error may become an unintended 500 | Parse in a controlled way and return 400 |
| Not handling empty from a repository | No clear business response | Use switchIfEmpty to return 404 or an appropriate empty result |
| Confusing a predicate with business validation | The request is routed incorrectly or logic is hidden in the route | A predicate only checks routing conditions |
| Forgetting to check Content-Type | The handler may decode a body in the wrong format | Add a contentType predicate and handle decode errors |
| Combining multiple routers without considering order | The first route may receive another module's request | Check path collisions and order |
| Placing a filter at the wrong nested-route scope | Some endpoints do not go through the intended filter | See which builder creates the route and where the filter sits |
| Using a router filter as a security replacement | Standard authentication/authorization may be missed | Use Spring Security; a route filter only adds local logic |
| Collecting a large Flux body into a List | Consumes RAM and loses streaming | Process the publisher directly |
| Ignoring JSON decode errors | The client receives inconsistent responses | Map ServerWebInputException/validation errors |
| Using the same path in a controller and a functional route | The mapping depends on order and is hard to debug | Avoid duplicate paths or configure the order deliberately |
| Creating a route bean that is not in component scan | Spring does not detect the router | Put @Configuration in a scanned package or import the configuration |
| Thinking an unmatched route always creates a 404 from a handler | The handler has not been called; the request goes through another mapping or a fallback | Check all router/handler mappings |
| Returning a body publisher without choosing an appropriate media type | The codec or client may not handle it correctly | Choose a suitable Content-Type/Accept and codec |

## 17. RouterFunction Design Checklist

Before putting a route into the application, check:

1. Do the method and path describe the endpoint correctly?
2. Are there predicates for the required Accept/Content-Type/header/query?
3. Is the route shadowed by a general route declared earlier?
4. Can routes with the same prefix be grouped with a nested route?
5. Does the handler have the correct `Mono<ServerResponse>` signature?
6. Is the request body decoded into an appropriate data type?
7. How are an empty body, malformed JSON, and validation failure handled?
8. Does an empty service result mean 404, an empty list, or a fallback?
9. Does the handler compose reactive publishers and avoid manual block/subscribe?
10. Does the filter have the right scope and not replace the security chain?
11. Do the RouterFunction beans have path collisions with each other or with annotated controllers?
12. Have you tested the status, header, body, and unmatched route with WebTestClient?

| Need | How to declare |
| --- | --- |
| A simple GET route | `GET("/path", handler)` |
| A POST route with a predicate | `POST("/path", predicate, handler)` |
| A combined condition | `predicate.and(other)` / `or(other)` |
| A shared prefix | `path("/prefix", builder -> ...)` |
| Combining module routers | `routerA.and(routerB)` |
| Adding a route to an existing router | `andRoute(predicate, handler)` |
| Adding logging/blocking a request | `filter((request, next) -> ...)` |
| Changing the request before the handler | `before(request -> ...)` |
| Observing the response after the handler | `after((request, response) -> ...)` |
| Serving static resources | `RouterFunctions.resources(...)` |
| Testing a functional route | `WebTestClient.bindToRouterFunction(router)` |

## 18. Self-Check Questions with Answers

**Question 1.** How do `RouterFunction` and `HandlerFunction` differ?

**Answer:** RouterFunction finds the handler that fits the request. HandlerFunction handles the request and returns a `Mono<ServerResponse>`.

**Question 2.** Why does a WebFlux.fn handler return a `Mono<ServerResponse>`?

**Answer:** Reading data, calling services, and creating the response may be asynchronous. The Mono represents a response that is emitted after the reactive chain completes.

**Question 3.** Does `GET("/users/{id}")` automatically convert the id to a long?

**Answer:** No. `request.pathVariable("id")` returns a String; the handler must parse it and handle invalid data.

**Question 4.** How do `accept(APPLICATION_JSON)` and `contentType(APPLICATION_JSON)` differ?

**Answer:** Accept describes the response format the client accepts; Content-Type describes the format of the body of the request being sent.

**Question 5.** Why should the `/users/search` route come before `/users/{id}`?

**Answer:** RouterFunction evaluates routes in order. The variable route can match the string search, so the search route after it would never be invoked.

**Question 6.** When should you use a nested route?

**Answer:** When many routes share the same path prefix or the same predicate. A nested route reduces repetition and makes the endpoint group clearer.

**Question 7.** How does a filter differ from a handler?

**Answer:** The handler performs the endpoint logic. A filter wraps the handler to add common behavior, and can call the next handler or return a response early.

**Question 8.** Can a RouterFunction bean be used together with @RestController?

**Answer:** Yes. Spring WebFlux supports both functional endpoints and annotated controllers in the same application; you need to avoid route collisions and check the mapping order.

**Question 9.** If a service returns Mono.empty() when getting a resource by ID, what should the handler do?

**Answer:** If the contract specifies that a nonexistent resource is a 404, use `switchIfEmpty(ServerResponse.notFound().build())`. For a collection search, an empty list may be a 200.

**Question 10.** Should you call `subscribe()` in a handler to save data and then return the response immediately?

**Answer:** No. A side effect detached from the request lifecycle can cause the response to be returned before the save completes, and errors are no longer propagated correctly. Compose the publisher and only create the response after the necessary operation completes.

**Question 11.** When a route does not match, is that route's handler invoked?

**Answer:** No. The RouterFunction does not supply a handler for that request; the framework continues to consider other routers or handles the request as unrouted.

**Question 12.** What do you use to test a functional route without starting a real server?

**Answer:** `WebTestClient.bindToRouterFunction(router).build()` can bind the RouterFunction directly to verify the request/response.

## 19. Key Takeaways and Official Documentation

- `RouterFunctions.route()` creates a builder to declare HTTP routes by method, path, and predicate.
- `RouterFunction` finds the handler; `HandlerFunction` handles the request and returns a `Mono<ServerResponse>`.
- `RequestPredicate` describes the matching condition; use `and`, `or`, and `negate` to combine conditions.
- Routers are evaluated in order; put specific routes before general routes.
- Use nested routes to group a shared path/predicate; use `and` or `add` to combine routers by module.
- `ServerRequest` reads path/query/headers/body; `ServerResponse` creates the status, headers, and reactive body.
- `before`, `after`, and `filter` add common behavior; make sure the filter has the right scope.
- Spring Boot WebFlux automatically detects RouterFunction beans and integrates them into the DispatcherHandler.
- Test routes with WebTestClient; do not call `block()` or `subscribe()` manually in a handler.

Official documentation:

1. [Spring Framework Reference — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): overview, RouterFunction, HandlerFunction, RequestPredicate, nested routes, filters, and how to run.
2. [Spring Framework Javadoc — RouterFunctions](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RouterFunctions.html): builder, route composition, resources, and utilities.
3. [Spring Framework Javadoc — RequestPredicates](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/RequestPredicates.html): factories for method, path, headers, query, and media type.
4. [Spring Framework Javadoc — ServerRequest](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html): the API for reading the HTTP request and body.
5. [Spring Framework Javadoc — ServerResponse](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): response builder, status, headers, and body.
6. [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): testing WebFlux endpoints and routers.
7. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): Spring Boot WebFlux runtime auto-configuration.
