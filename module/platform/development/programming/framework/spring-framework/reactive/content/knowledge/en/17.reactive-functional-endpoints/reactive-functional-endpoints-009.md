# Comparing Functional Endpoints and Controllers for the Same HTTP Contract in Spring WebFlux

> **Module:** Spring Framework – reactive · **Parent topic:** Functional endpoints. This lesson compares WebFlux's two ways of building HTTP APIs: annotated controllers (`@RestController`, `@GetMapping`, `@PostMapping`) and functional endpoints (`RouterFunction`, `HandlerFunction`, `ServerRequest`, `ServerResponse`). Both approaches will use the same domain service and the same HTTP contract to clarify what changes by programming model and what still belongs to the shared WebFlux foundation.

## 1. Learning Objectives

After this lesson, you can:

1. Explain how annotated controllers and WebFlux.fn both run on Reactive Core, `DispatcherHandler`, the HTTP server, codecs, and the WebFilter chain.
2. Map an HTTP contract to `@RequestMapping` or `RouterFunction`/`RequestPredicate`.
3. Write the same handler using a controller method and a `HandlerFunction<ServerResponse>`.
4. Compare how path/query/header/body extraction, validation, status, headers, response bodies, errors, and streaming work.
5. Distinguish the scope of `@ControllerAdvice`, `HandlerFilterFunction`, `WebFilter`, and Spring Security.
6. Understand functional endpoint route order, annotated mapping route specificity, and route shadowing risks.
7. Verify that two implementations share the same observable contract using HTTP integration tests.
8. Choose a model based on module structure, binding complexity, and team organization.

**Comparison principle:** the same HTTP contract means the client observes the same method, status, headers, content type, body schema, error schema, and semantics when data is absent. Class names, annotations, or lambdas are not part of the HTTP contract.

## 2. Two Models, One WebFlux Foundation

Spring WebFlux offers two ways to describe endpoints:

- **Annotated controller:** declares intent via annotations. Spring finds the method by mapping, resolves parameters, invokes the method, and interprets the return value.
- **Functional endpoint (WebFlux.fn):** declares routes with `RouterFunction` and handles requests with `HandlerFunction`; the application explicitly reads `ServerRequest` and builds `ServerResponse`.

Both use Reactive Streams/Reactor, the same server such as Reactor Netty, the same `WebFilter`, Spring Security, codecs, `HttpMessageReader`/`HttpMessageWriter`, backpressure, and cancellation.

~~~text
                         HTTP request
                              |
                         HttpHandler
                              |
                    WebFilter / Security
                              |
                      DispatcherHandler
                              |
                 +------------+-------------+
                 |                          |
        Annotated mapping            RouterFunctionMapping
                 |                          |
       RequestMappingHandlerMapping     RouterFunction
                 |                          |
       RequestMappingHandlerAdapter    HandlerFunctionAdapter
                 |                          |
       Controller method               HandlerFunction
                 |                          |
         HandlerResult                Mono<ServerResponse>
                 |                          |
       Result handlers                ServerResponseResultHandler
                 |                          |
                 +------------+-------------+
                              |
                   HTTP response + codecs
~~~

A functional endpoint is not a separate HTTP server and does not bypass `DispatcherHandler` in a normal WebFlux configuration. `RouterFunctionMapping`, `HandlerFunctionAdapter`, and `ServerResponseResultHandler` connect WebFlux.fn into the same dispatch lifecycle. Both models can be used in one application as long as routes do not conflict.

## 3. Defining the HTTP Contract Before Comparing

We will build an `Item` management API with three operations:

| Method | Path after prefix | Request | Success | Not found / error |
| --- | --- | --- | --- | --- |
| GET | `/items/{id}` | No body | 200 + `Item` JSON | 404, empty body |
| POST | `/items` | `{"name":"Keyboard"}` | 201 + `Location` + `Item` JSON | 400 + ProblemDetail if name is blank |
| DELETE | `/items/{id}` | No body | 204, empty body | 404, empty body |

To run both implementations in the same server without registering two handlers for the same path, the demo uses two prefixes:

- Annotated: `/api/annotated/items`
- Functional: `/api/functional/items`

The different prefixes are only to distinguish the implementations in the demo. The remaining path, status, headers, JSON schema, error messages, and data rules are identical.

**Successful GET:**

~~~http
GET /api/annotated/items/42
Accept: application/json
~~~

and:

~~~http
GET /api/functional/items/42
Accept: application/json
~~~

Both return the same schema:

~~~json
{
  "id": "42",
  "name": "Seed item"
}
~~~

If the id does not exist, both return `404 Not Found` with an empty body.

**Successful POST:**

~~~http
POST /api/functional/items
Content-Type: application/json
Accept: application/json

{"name":"Keyboard"}
~~~

Both return status 201, a `Location` header pointing to the newly created resource, JSON content type, and a body containing the same `id`/`name`. IDs increment in the example so the exact value changes by request order; the ID in the body must match the ID in Location.

**Invalid POST:** `{"name":" "}` must return `400 Bad Request` and a ProblemDetail with `title`, `detail`, `status` along with `code=ITEM_NAME_INVALID`. The client does not need to know whether the error was converted into a response by `@RestControllerAdvice` or a functional route filter.

## 4. Keeping the Domain Service Identical

For a fair comparison, both endpoints share:
- The `Item` and `CreateItemRequest` DTOs.
- `ItemService` containing name validation rules, ID generation, item reading, and deletion.
- A factory for creating ProblemDetail.
- The same JSON codecs and HTTP server.
- The same HTTP test suite checking status/header/body.

Only **routing, extracting request data, calling the handler, and creating the response** are expressed according to each model. If each implementation wrote its own validation/service, differences in results could come from business logic rather than the endpoint model.

## 5. How Annotated Controllers Express the Contract

A controller typically uses:
- `@RestController` to write the return value to the body.
- `@RequestMapping` to declare a prefix.
- `@GetMapping`, `@PostMapping`, `@DeleteMapping` to declare HTTP method/path.
- `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` to bind the request.
- `ResponseEntity<T>` to control status, headers, and body.
- `@ExceptionHandler`/`@RestControllerAdvice` to turn errors into responses.

GET example:

~~~java
@GetMapping("/{id}")
Mono<ResponseEntity<Item>> get(@PathVariable String id) {
    return service.findById(id)
        .map(ResponseEntity::ok)
        .defaultIfEmpty(ResponseEntity.notFound().<Item>build());
}
~~~

The method focuses on parameters and business results. Spring resolves the path variable, invokes the method, and uses the return-value handler to write the response.

Annotations keep code short and readable when endpoints follow common CRUD/REST patterns and have many parameters supported by the framework. In return, part of the behavior lives in annotations, argument resolvers, validation, advice, and WebFlux configuration; readers need to understand framework conventions.

## 6. How Functional Endpoints Express the Same Contract

WebFlux.fn uses two main contracts:

~~~java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
~~~

`HandlerFunction` takes a `ServerRequest` and returns an asynchronous response, typically `Mono<ServerResponse>`.

~~~java
@FunctionalInterface
public interface RouterFunction<T extends ServerResponse> {
    Mono<HandlerFunction<T>> route(ServerRequest request);
}
~~~

`RouterFunction` inspects the request and returns the matching handler; if there is no match, it completes empty so the next router has a chance to handle it.

Equivalent GET example:

~~~java
Mono<ServerResponse> get(ServerRequest request) {
    String id = request.pathVariable("id");

    return service.findById(id)
        .flatMap(item -> ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

The handler reads the path variable directly from `ServerRequest`, calls the service, and builds `ServerResponse`. Functional endpoints make the processing flow more explicit, especially when a request has multiple branches or routes are composed by module.

## 7. Mapping: Annotations and RouterFunction

| Aspect | Annotated controller | Functional endpoint |
| --- | --- | --- |
| Routing | `@RequestMapping`, `@GetMapping`, ... | `RouterFunction` and `RequestPredicate` |
| Matching HTTP method/path | Framework analyzes mapping metadata | Predicates created by the router builder |
| Path variable | `@PathVariable` | `request.pathVariable("id")` |
| Query parameter | `@RequestParam` | `request.queryParam("page")` |
| Header | `@RequestHeader` | `request.headers().firstHeader("X-...")` |
| Content-Type / Accept | `consumes`, `produces` | `contentType(...)`, `accept(...)` predicates |
| Route order | Framework picks the most specific mapping; ambiguous mappings can fail | RouterFunction is evaluated in composition order |
| Route grouping | Controller class + base mapping | Builder `.path(...)`, `.nest(...)`, `.and(...)` |

### 7.1. Annotated mapping

~~~java
@RestController
@RequestMapping("/api/annotated/items")
class ItemController {

    @GetMapping("/{id}")
    Mono<Item> get(@PathVariable String id) {
        return service.findById(id);
    }

    @GetMapping(params = "active=true")
    Flux<Item> active() {
        return service.findActive();
    }
}
~~~

The framework builds mappings from annotations and method/path/query/header/media type conditions. For close mappings, Spring checks specificity and detects ambiguous cases.

### 7.2. Functional mapping

~~~java
@Bean
RouterFunction<ServerResponse> itemRoutes(ItemHandler handler) {
    return RouterFunctions.route()
        .path("/api/functional/items", builder -> builder
            .GET("/{id}", handler::get)
            .GET(RequestPredicates.queryParam("active", "true"),
                handler::active))
        .build();
}
~~~

The router builder lets you combine routes and group them by path/predicate. Routes are evaluated in composition order: place specific routes before general routes to avoid having a general route catch the request first.

**Important difference:** annotated mappings usually pick the most specific matching mapping; functional routing makes the order of composed routers explicit. When refactoring, check route overlaps, `and`/`andRoute` order, `nest` predicates, and fallbacks.

## 8. Extracting Request Data and Reading the Body

Annotated controllers bind the request to parameters:

~~~java
@PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
Mono<Item> create(@RequestBody Mono<CreateItemRequest> body) {
    return body.flatMap(service::create);
}
~~~

Functional handlers read the request explicitly:

~~~java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateItemRequest.class)
        .flatMap(service::create)
        .flatMap(item -> ServerResponse.created(
                URI.create("/api/functional/items/" + item.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item));
}
~~~

Both use message readers/codecs to decode JSON. `@RequestBody Mono<T>` and `ServerRequest.bodyToMono(T.class)` are both reactive body extractions; they do not force reading the entire body synchronously before the method runs.

The annotated model provides resolvers for path variables, query parameters, headers, cookies, principal, session, exchange, validation, model attributes, and request bodies. The functional model gathers information in `ServerRequest`; code explicitly calls `pathVariable`, `queryParam`, `headers`, `bodyToMono`, `bodyToFlux`, `principal`, `session`, or `exchange`.

For endpoints with a few standard parameters, annotations are usually shorter. For pipelines that read a body, check multiple predicates, and branch, explicit calls can make the processing order easier to follow.


## 9. Response: ResponseEntity and ServerResponse

Both models can emit the same HTTP status, headers, and body.

### 9.1. ResponseEntity in controllers

~~~java
Mono<ResponseEntity<Item>> find(String id) {
    return service.findById(id)
        .map(item -> ResponseEntity.ok()
            .header("X-Api-Version", "1")
            .body(item))
        .defaultIfEmpty(ResponseEntity.notFound().<Item>build());
}
~~~

`ResponseEntity` works well with method return values and nested reactive forms such as `Mono<ResponseEntity<T>>`, `ResponseEntity<Mono<T>>`, and `ResponseEntity<Flux<T>>`.

### 9.2. ServerResponse in functional handlers

~~~java
Mono<ServerResponse> find(ServerRequest request) {
    return service.findById(request.pathVariable("id"))
        .flatMap(item -> ServerResponse.ok()
            .header("X-Api-Version", "1")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

`ServerResponse` is WebFlux.fn's response abstraction. Builders `ok`, `created`, `accepted`, `noContent`, `notFound`, `badRequest`, and `status` help create statuses and headers. `bodyValue` accepts an existing object; `body` accepts a Publisher/BodyInserter when the body is asynchronous or streaming.

### 9.3. Status/header/body mapping table

| Intent | Controller | Functional |
| --- | --- | --- |
| 200 + body | `ResponseEntity.ok(body)` | `ServerResponse.ok().bodyValue(body)` |
| 201 + Location | `ResponseEntity.created(uri).body(body)` | `ServerResponse.created(uri).bodyValue(body)` |
| 202 | `ResponseEntity.accepted().build()` | `ServerResponse.accepted().build()` |
| 204 | `ResponseEntity.noContent().build()` | `ServerResponse.noContent().build()` |
| 400 | `ResponseEntity.badRequest().body(error)` | `ServerResponse.badRequest().bodyValue(error)` |
| 404 | `ResponseEntity.notFound().build()` | `ServerResponse.notFound().build()` |
| Custom header | `ResponseEntity.ok().header(...).body(...)` | `ServerResponse.ok().header(...).bodyValue(...)` |

In both models, status/headers must be decided before the response commits. If a streaming body starts writing and then emits an error, the server cannot change the already-sent status.

## 10. Validation and Errors: Different Wiring, Same Contract

### 10.1. Annotated controller

Annotated controllers can use Bean Validation via `@Valid`/`@Validated` and handle errors with `@ExceptionHandler` or `@RestControllerAdvice`.

~~~java
@PostMapping
Mono<ResponseEntity<Item>> create(
        @Valid @RequestBody Mono<CreateItemRequest> request) {
    return request.flatMap(service::create)
        .map(item -> ResponseEntity
            .created(URI.create("/api/annotated/items/" + item.id()))
            .body(item));
}
~~~

The example above requires a validation provider on the classpath and a DTO with constraints such as `@NotBlank`. Body resolution/validation errors are routed through the annotated controller's exception handling.

### 10.2. Functional endpoint

A functional handler receives a `ServerRequest`, so the application explicitly calls `Validator`, a validation service, or a domain constructor after decoding the body. Example:

~~~java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateItemRequest.class)
        .flatMap(service::create)
        .flatMap(item -> ServerResponse.created(
                URI.create("/api/functional/items/" + item.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(item));
}
~~~

Validation rules should live in a shared layer if both endpoint styles must maintain the same contract.

### 10.3. Exception handling has different scopes

- `@RestControllerAdvice`/`@ControllerAdvice` is tied to annotated controller invocations and errors from their return values.
- `HandlerFilterFunction` wraps the route functions composed into the router builder; `onErrorResume` can be used to convert exceptions into `ServerResponse`.
- `WebExceptionHandler` runs in the WebHandler chain and can handle errors at a broader scope, including the filter/handler chain.
- `WebFilter` is suitable for request-wide logic such as correlation IDs, authentication/authorization, metrics, and CORS; it does not replace all exception mapping.

A `@ControllerAdvice` is not automatically an error-handling mechanism for every `HandlerFunction`. If both models must produce the same ProblemDetail, share the error-body factory/mapper and invoke it from both `@ExceptionHandler` and the functional filter, or use a deliberate shared `WebExceptionHandler`.

### 10.4. Example with the same ProblemDetail

~~~java
final class ApiProblems {
    private ApiProblems() {}

    static ProblemDetail invalidName(IllegalArgumentException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, error.getMessage());
        problem.setTitle("Invalid item");
        problem.setProperty("code", "ITEM_NAME_INVALID");
        return problem;
    }
}
~~~

Annotated side:

~~~java
@RestControllerAdvice
class ApiExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    ProblemDetail invalidName(IllegalArgumentException error) {
        return ApiProblems.invalidName(error);
    }
}
~~~

Functional side:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .POST("/api/functional/items", handler::create)
    .filter((request, next) -> next.handle(request)
        .onErrorResume(IllegalArgumentException.class, error ->
            ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(ApiProblems.invalidName(error))))
    .build();
~~~

Both return status 400 and the same ProblemDetail structure. The functional filter only wraps the router it is attached to; it does not automatically apply to other route beans without composition.

## 11. Filters, Cross-Cutting Concerns, and Security

### 11.1. Shared WebFilter

`WebFilter` wraps the WebHandler chain, so it can apply to both annotated controllers and functional routes. Example request ID:

~~~java
@Component
class RequestIdFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {
        String requestId = UUID.randomUUID().toString();
        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);
        return chain.filter(exchange);
    }
}
~~~

This is a component fragment. Production should extract or verify the request ID from a trusted header and avoid treating an arbitrary string as a verified identity.

### 11.2. HandlerFilterFunction specific to WebFlux.fn

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/api/functional/items/{id}", handler::get)
    .filter((request, next) -> {
        if (!accessAllowed(request)) {
            return ServerResponse.status(HttpStatus.FORBIDDEN).build();
        }
        return next.handle(request);
    })
    .build();
~~~

`HandlerFilterFunction` receives a `ServerRequest` and the next handler; it can modify the request, short-circuit with a response, or observe the response. `before`, `after`, and `filter` on the builder are ways to compose filters with route functions. Their scope depends on where they are attached in the builder/nested router.

Annotated controllers can use `@ControllerAdvice`, mapping-based `HandlerInterceptor`, method security, and `WebFilter`/Spring Security. Use Spring Security in the WebFilter chain for shared security policies; do not turn a route filter into an application-wide security handler.

### 11.3. Principal and security context

Both models can obtain the principal/security context through Spring Security's reactive mechanism. Annotated controllers can receive `Principal`/`Authentication` in method parameters; functional handlers can read `request.principal()` or the corresponding context. The security filter chain applies outside the endpoint model so the same policy can protect both.

## 12. Streaming and Backpressure

Both models return Publishers and support streaming bodies.

Controller:

~~~java
@GetMapping(value = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<Item>> events() {
    return service.events().map(item ->
        ServerSentEvent.<Item>builder()
            .id(item.id())
            .event("item")
            .data(item)
            .build());
}
~~~

Functional:

~~~java
Mono<ServerResponse> events(ServerRequest request) {
    Flux<ServerSentEvent<Item>> body = service.events().map(item ->
        ServerSentEvent.<Item>builder()
            .id(item.id())
            .event("item")
            .data(item)
            .build());

    return ServerResponse.ok()
        .contentType(MediaType.TEXT_EVENT_STREAM)
        .body(body, ServerSentEvent.class);
}
~~~

The functional fragment illustrates passing a Publisher into `ServerResponse.body`; for complex generic bodies, use `ParameterizedTypeReference`/`BodyInserter` if the codec cannot infer the element type from a raw class. Both use the same codecs, network backpressure, cancellation, and resource lifecycles.

**Similarities:**
- `Flux<T>`/Publisher can emit multiple elements; the body is written progressively.
- A slow client affects demand/flow control and can cause buffers to grow.
- Client disconnect can cancel the subscription.
- Errors after the response has committed cannot change the status and replace the entire body.
- `collectList()` buffers data in memory and changes streaming semantics.
- `text/event-stream`, NDJSON, and JSON have different framing/flush behavior.

The main difference is how code creates the body: annotated controllers return a Publisher directly or wrapped in ResponseEntity; functional handlers pass the Publisher to `ServerResponse.body(...)`.

## 13. Composition and Module Organization

Annotated controllers are usually organized by resource/bounded context:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // GET/POST/DELETE methods for the Order resource.
}
~~~

Functional endpoints usually separate route declarations and handlers:

~~~java
@Configuration(proxyBeanMethods = false)
class OrderRoutes {
    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return RouterFunctions.route()
            .path("/api/orders", b -> b
                .GET("/{id}", handler::get)
                .POST(handler::create)
                .DELETE("/{id}", handler::delete))
            .build();
    }
}
~~~

Functional composition lets you combine routers with `and`, `andRoute`, `nest`, and attach before/after filters at the router scope. Annotated controllers excel in method signatures, argument resolvers, mapping metadata, built-in validation, and advice.

There is no rule that functional is always easier to test or annotated is always easier to read. Request complexity, route count, team skills, and module organization decide.


## 14. Runnable Java 17+: Same Service, Two Endpoint Implementations

This project runs both annotated and functional endpoints in one Spring Boot WebFlux application. The two route groups share the same service and return the same status/body semantics. Prefixes differ so the two implementations can coexist on one server.

### 14.1. Project structure

~~~text
webflux-endpoint-comparison/
├── pom.xml
├── src/main/java/com/example/compare/ComparisonApplication.java
├── src/main/java/com/example/compare/Item.java
├── src/main/java/com/example/compare/CreateItemRequest.java
├── src/main/java/com/example/compare/ItemService.java
├── src/main/java/com/example/compare/ApiProblems.java
├── src/main/java/com/example/compare/AnnotatedItemController.java
├── src/main/java/com/example/compare/ApiExceptionHandler.java
├── src/main/java/com/example/compare/FunctionalItemHandler.java
├── src/main/java/com/example/compare/FunctionalItemRoutes.java
└── src/test/java/com/example/compare/EndpointContractTest.java
~~~

### 14.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>webflux-endpoint-comparison</artifactId>
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
~~~

### 14.3. ComparisonApplication.java

~~~java
package com.example.compare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ComparisonApplication {
    public static void main(String[] args) {
        SpringApplication.run(ComparisonApplication.class, args);
    }
}
~~~

### 14.4. Item.java and CreateItemRequest.java

~~~java
package com.example.compare;

public record Item(String id, String name) {}
~~~

~~~java
package com.example.compare;

public record CreateItemRequest(String name) {}
~~~

### 14.5. ItemService.java — shared business logic

~~~java
package com.example.compare;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ItemService {
    private final ConcurrentMap<String, Item> items =
        new ConcurrentHashMap<>();
    private final AtomicLong sequence = new AtomicLong(100);

    public ItemService() {
        items.put("42", new Item("42", "Seed item"));
        items.put("43", new Item("43", "Second seed"));
        items.put("delete-annotated",
            new Item("delete-annotated", "Delete annotated"));
        items.put("delete-functional",
            new Item("delete-functional", "Delete functional"));
    }

    public Mono<Item> findById(String id) {
        return Mono.justOrEmpty(items.get(id));
    }

    public Mono<Item> create(CreateItemRequest request) {
        return Mono.defer(() -> {
            String name = request == null ? null : request.name();
            if (name == null || name.isBlank()) {
                return Mono.error(
                    new IllegalArgumentException("name must not be blank"));
            }

            String id = Long.toString(sequence.incrementAndGet());
            Item item = new Item(id, name.trim());
            items.put(id, item);
            return Mono.just(item);
        });
    }

    public Mono<Boolean> deleteById(String id) {
        return Mono.fromSupplier(() -> items.remove(id) != null);
    }
}
~~~

`ConcurrentHashMap` and `AtomicLong` make the example safer when tests/requests run concurrently. `Mono.defer` defers validation and data writing until subscription. This is an in-memory demo, not durable persistence; restarting the application re-initializes the seed items.

### 14.6. ApiProblems.java — shared error factory

~~~java
package com.example.compare;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;

final class ApiProblems {
    private ApiProblems() {}

    static ProblemDetail invalidName(IllegalArgumentException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST, error.getMessage());
        problem.setTitle("Invalid item");
        problem.setProperty("code", "ITEM_NAME_INVALID");
        return problem;
    }
}
~~~

### 14.7. AnnotatedItemController.java

~~~java
package com.example.compare;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/annotated/items")
public class AnnotatedItemController {
    private final ItemService service;

    public AnnotatedItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Item>> get(@PathVariable String id) {
        return service.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().<Item>build());
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ResponseEntity<Item>> create(
            @RequestBody Mono<CreateItemRequest> body) {
        return body.flatMap(service::create)
            .map(item -> ResponseEntity
                .created(URI.create("/api/annotated/items/" + item.id()))
                .body(item));
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(@PathVariable String id) {
        return service.deleteById(id).map(deleted -> {
            if (deleted) {
                return ResponseEntity.noContent().<Void>build();
            }
            return ResponseEntity.notFound().<Void>build();
        });
    }
}
~~~

Controller methods bind the request, call the service, and express the response using `ResponseEntity`. GET uses `Mono<ResponseEntity<Item>>` because status 200/404 depends on the async result. POST returns 201 with Location. DELETE returns 204 if deleted, otherwise 404.

### 14.8. ApiExceptionHandler.java

~~~java
package com.example.compare;

import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    public ProblemDetail invalidName(IllegalArgumentException error) {
        return ApiProblems.invalidName(error);
    }
}
~~~

The advice converts validation errors from the service into ProblemDetail 400 for the annotated controller. The functional route uses the same factory but has its own filter.

### 14.9. FunctionalItemHandler.java

~~~java
package com.example.compare;

import java.net.URI;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class FunctionalItemHandler {
    private final ItemService service;

    public FunctionalItemHandler(ItemService service) {
        this.service = service;
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        return service.findById(request.pathVariable("id"))
            .flatMap(item -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(item))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateItemRequest.class)
            .flatMap(service::create)
            .flatMap(item -> ServerResponse
                .created(URI.create(
                    "/api/functional/items/" + item.id()))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(item));
    }

    public Mono<ServerResponse> delete(ServerRequest request) {
        return service.deleteById(request.pathVariable("id"))
            .flatMap(deleted -> deleted
                ? ServerResponse.noContent().build()
                : ServerResponse.notFound().build());
    }
}
~~~

The functional handler reads `ServerRequest` itself, decodes the body, retrieves the path variable, and builds `ServerResponse`. Business rules remain in `ItemService` and are not duplicated.

### 14.10. FunctionalItemRoutes.java

~~~java
package com.example.compare;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class FunctionalItemRoutes {

    @Bean
    RouterFunction<ServerResponse> functionalItemRoutes(
            FunctionalItemHandler handler) {

        return RouterFunctions.route()
            .GET("/api/functional/items/{id}", handler::get)
            .POST("/api/functional/items",
                RequestPredicates.contentType(MediaType.APPLICATION_JSON),
                handler::create)
            .DELETE("/api/functional/items/{id}", handler::delete)
            .filter((request, next) -> next.handle(request)
                .onErrorResume(IllegalArgumentException.class, error ->
                    ServerResponse.badRequest()
                        .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                        .bodyValue(ApiProblems.invalidName(error))))
            .build();
    }
}
~~~

`RequestPredicates.contentType` maintains a Content-Type condition matching the annotated route's `consumes`. `HandlerFilterFunction` catches `IllegalArgumentException` from the handler/service and returns the same ProblemDetail. The filter is attached only to this router.

## 15. Testing the HTTP Contract for Both

Tests go through a real server to check route mapping, body codecs, status, and headers. Calling controller methods/handler functions directly would skip part of the pipeline that clients actually use.

### 15.1. EndpointContractTest.java

~~~java
package com.example.compare;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class EndpointContractTest {
    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @Value("${local.server.port}")
    int port;

    private HttpResponse<String> send(
            String method, String path, String body) throws Exception {

        HttpRequest.Builder builder = HttpRequest.newBuilder(
                URI.create("http://localhost:" + port + path))
            .header("Accept",
                "application/json, application/problem+json");

        HttpRequest.BodyPublisher publisher = body == null
            ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(body);

        if (body != null) {
            builder.header("Content-Type", "application/json");
        }

        return CLIENT.send(
            builder.method(method, publisher).build(),
            HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void getExistingItemHasSameContract() throws Exception {
        HttpResponse<String> annotated = send(
            "GET", "/api/annotated/items/42", null);
        HttpResponse<String> functional = send(
            "GET", "/api/functional/items/42", null);

        assertEquals(200, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertEquals(annotated.body(), functional.body());
        assertTrue(annotated.body().contains("\"name\":\"Seed item\""));
    }

    @Test
    void missingItemReturnsSameNotFoundContract() throws Exception {
        HttpResponse<String> annotated = send(
            "GET", "/api/annotated/items/missing-xyz", null);
        HttpResponse<String> functional = send(
            "GET", "/api/functional/items/missing-xyz", null);

        assertEquals(404, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertEquals("", annotated.body());
        assertEquals(annotated.body(), functional.body());
    }

    @Test
    void createReturnsCreatedLocationAndJsonFromBothModels()
            throws Exception {
        HttpResponse<String> annotated = send(
            "POST", "/api/annotated/items", "{\"name\":\"Keyboard\"}");
        HttpResponse<String> functional = send(
            "POST", "/api/functional/items", "{\"name\":\"Keyboard\"}");

        assertEquals(201, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertTrue(annotated.headers()
            .firstValue("Location").orElse("")
            .startsWith("/api/annotated/items/"));
        assertTrue(functional.headers()
            .firstValue("Location").orElse("")
            .startsWith("/api/functional/items/"));
        assertTrue(annotated.body().contains("\"name\":\"Keyboard\""));
        assertTrue(functional.body().contains("\"name\":\"Keyboard\""));
        assertTrue(annotated.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("application/json"));
        assertTrue(functional.headers()
            .firstValue("Content-Type").orElse("")
            .startsWith("application/json"));
    }

    @Test
    void invalidInputReturnsEquivalentProblemDetail()
            throws Exception {
        String invalid = "{\"name\":\" \"}";
        HttpResponse<String> annotated = send(
            "POST", "/api/annotated/items", invalid);
        HttpResponse<String> functional = send(
            "POST", "/api/functional/items", invalid);

        assertEquals(400, annotated.statusCode());
        assertEquals(annotated.statusCode(), functional.statusCode());
        assertTrue(annotated.body().contains("name must not be blank"));
        assertTrue(functional.body().contains("name must not be blank"));
        assertTrue(annotated.body().contains("ITEM_NAME_INVALID"));
        assertTrue(functional.body().contains("ITEM_NAME_INVALID"));
    }

    @Test
    void deleteUsesSameNoContentAndNotFoundSemantics()
            throws Exception {
        HttpResponse<String> annotatedDelete = send(
            "DELETE", "/api/annotated/items/delete-annotated", null);
        HttpResponse<String> functionalDelete = send(
            "DELETE", "/api/functional/items/delete-functional", null);

        assertEquals(204, annotatedDelete.statusCode());
        assertEquals(204, functionalDelete.statusCode());
        assertTrue(annotatedDelete.body().isEmpty());
        assertTrue(functionalDelete.body().isEmpty());

        HttpResponse<String> annotatedAgain = send(
            "DELETE", "/api/annotated/items/delete-annotated", null);
        HttpResponse<String> functionalAgain = send(
            "DELETE", "/api/functional/items/delete-functional", null);

        assertEquals(404, annotatedAgain.statusCode());
        assertEquals(404, functionalAgain.statusCode());
    }
}
~~~

The test uses the `HttpClient` built into JDK 17; `RANDOM_PORT` starts the embedded server. Two separate seed IDs for DELETE keep tests independent of execution order.

### 15.2. Running the application

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

The application listens on port 8080 by default. Test requests:

~~~bash
curl -i http://localhost:8080/api/annotated/items/42
curl -i http://localhost:8080/api/functional/items/42
curl -i -X POST http://localhost:8080/api/annotated/items -H "Content-Type: application/json" -d "{\"name\":\"Keyboard\"}"
curl -i -X POST http://localhost:8080/api/functional/items -H "Content-Type: application/json" -d "{\"name\":\"Keyboard\"}"
~~~

**Key results:**

| Request | Annotated | Functional |
| --- | --- | --- |
| GET item 42 | 200 + JSON | 200 + same JSON |
| GET missing id | 404 + empty body | 404 + empty body |
| POST valid name | 201 + Location + JSON | 201 + Location + JSON |
| POST blank name | 400 + ProblemDetail | 400 + same ProblemDetail schema |
| DELETE existing item | 204 + empty body | 204 + empty body |
| DELETE deleted item again | 404 + empty body | 404 + empty body |

Location contains the implementation's own prefix; that is an intentional difference in the demo so both routes can run on one server.

## 16. Choosing a Model by Scenario

| Scenario | Usually more convenient | Reason |
| --- | --- | --- |
| Standard CRUD REST, many path/header/body bindings | Annotated controller | Method signatures and resolvers do most of the work. |
| Endpoint needing to read requests with clear multi-branching | Functional | `ServerRequest` and Mono chains make processing order explicit. |
| Many routes composed by predicate/nested path | Functional | Router composition is a core API. |
| Heavy use of `@Valid`, `@ModelAttribute`, `@ExceptionHandler` | Annotated | Built-in convention and integration support. |
| A group of routes needing custom before/after/filter | Functional | `HandlerFilterFunction` attaches directly to the router. |
| Team familiar with controllers and Spring annotations | Annotated | Fewer convention changes, easy onboarding. |
| Module wanting to express routing by composition | Functional | Routes can be composed into independent parts. |
| Cross-cutting security/logging for the whole app | Both | Use WebFilter/Spring Security outside the endpoint model. |
| Same service/domain serving multiple route types | Both | Share the service and test the shared contract. |

You do not need to pick one model for the entire application. One codebase can use annotated controllers for ordinary CRUD and a functional router for streaming modules or gateways that need explicit composition. Standardize conventions within each module to avoid two accidentally different error/validation handling styles.

## 17. Mistakes When Migrating or Deploying Side by Side

| Mistake | Consequence | How to check/fix |
| --- | --- | --- |
| Only comparing JSON body, ignoring status/headers | Two endpoints look alike but have different contracts | Test status, Location, Content-Type, and error headers. |
| Different validation | Same input produces different results | Move domain validation into a shared service/validator. |
| Thinking `@ControllerAdvice` catches functional handler errors | Functional route may return different errors | Use a functional filter or a shared WebExceptionHandler. |
| Thinking functional routes always pick the most specific route | General route declared earlier catches requests | Check composition order and predicates. |
| Duplicate path/method across both models | Route shadowing or unpredictable dispatch | Use clear prefixes during coexistence or configure order deliberately. |
| Using WebFilter instead of a route-specific filter | Endpoint logic applies too broadly | HandlerFilterFunction for routers; WebFilter for cross-cutting. |
| Reading the request body multiple times | Body already consumed, later handlers cannot read it | Decode once or cache/decorate deliberately. |
| Writing the response yourself and continuing to write the body | Response committed twice/errors | Pick one response owner. |
| Calling `block()`/`subscribe()` in a handler | Loses reactive lifecycle, blocks the event loop | Compose Publishers and return the result to the framework. |
| Only testing handlers directly | Skips mapping, codecs, and HTTP headers | Add HTTP integration tests via RANDOM_PORT. |
| Ignoring cancellation in streaming | Listeners/connections may leak | Attach cleanup to the Publisher and test client disconnect. |
| Functional route without a content-type predicate | Accepts out-of-contract requests | Use `contentType`/`accept` predicates or check in the handler. |
| Using different prefixes and comparing Location literally | Tests report false differences | Normalize prefixes or compare contract parts separately. |

## 18. Parity Matrix Before Migrating an Endpoint

When migrating a controller to a functional route or vice versa, record parity per endpoint:

1. **Request matching:** method, path, query, header, content type, Accept, version.
2. **Input binding:** path variables, query parameters, body type, cookies, principal, validation.
3. **Success:** status, Location, cache headers, content type, JSON schema, empty body.
4. **Failure:** 400/401/403/404/409/415/406/5xx, ProblemDetail, correlation ID.
5. **Reactive behavior:** Mono/Flux cardinality, backpressure, timeout, cancellation, cleanup.
6. **Security:** authentication, authorization, CSRF/CORS if applicable, method security.
7. **Observability:** logs, metrics, tracing, request ID, and latency.
8. **Compatibility:** serialization naming, date/time format, enums, null handling, and versioned responses.

Check empty results, body decode errors, validation failures, unmatched routes, wrong media types, client disconnects, and mid-stream response errors. These are where two implementations easily diverge in contract even if the happy path has the same body.

## 19. Production Checklist

- [ ] Both implementations share the domain service and business rules.
- [ ] Method/path/predicates match the HTTP contract.
- [ ] Functional route order and nested predicates are checked.
- [ ] Annotated mappings are unambiguous and not shadowed by other routes.
- [ ] Body is decoded properly by message readers/codecs.
- [ ] Validation has the same semantics.
- [ ] Status, headers, Location, content type, and body schema are identical.
- [ ] Error mapping produces the same ProblemDetail/status; scope of @ControllerAdvice and functional filters is understood.
- [ ] Security/cross-cutting concerns use the appropriate WebFilter/Spring Security layer.
- [ ] Streaming preserves backpressure, timeouts, cancellation, and cleanup.
- [ ] No blocking or manual subscribing on the request path.
- [ ] Integration tests run through the HTTP server for both endpoint styles.
- [ ] Logging, metrics, tracing, and request IDs do not depend on the handler model.
- [ ] Can roll out route by route and compare contracts before deleting the old implementation.

## 20. Hands-on Exercises

**Exercise 1 – GET parity.** Write GET `/items/{id}` in both models. Verify 200 when present and 404 when absent; compare status and JSON body.

**Exercise 2 – POST parity.** Write POST accepting JSON, validating name, returning 201 and Location. Send an empty name; ensure both sides return the same ProblemDetail.

**Exercise 3 – DELETE parity.** Write DELETE returning 204 when deleted and 404 when absent. Check the empty body and call a second time.

**Exercise 4 – Route specificity.** Declare routes `/items/search` and `/items/{id}`. Put the general route first and then reverse the order; observe how RouterFunction chooses the handler. Compare with annotated mapping.

**Exercise 5 – Validation.** Annotated uses `@Valid`; functional uses Validator or a domain service. Ensure the same constraints and error codes.

**Exercise 6 – Filter scope.** Add a WebFilter writing a request ID for both routes. Add a HandlerFilterFunction only for the functional route; verify the different scopes.

**Exercise 7 – Streaming.** Return the same SSE Flux through a controller and ServerResponse. Disconnect the client, verify upstream cleanup, and compare framing.

**Exercise 8 – Migrating a real endpoint.** Pick an existing endpoint, write a parity matrix, implement the second model under a test path, and run the same HTTP contract test suite before switching traffic.

## 21. Official References

1. Spring Framework – Functional Endpoints (WebFlux.fn): https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
2. Spring Framework – Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/webflux/controller.html
3. Spring Framework – WebFlux overview and the two programming models: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
4. Spring Framework – DispatcherHandler: https://docs.spring.io/spring-framework/reference/web/webflux/dispatcher-handler.html
5. Spring Framework – WebFlux Config: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
6. Spring Framework – Error Responses / ProblemDetail: https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html
7. Spring Framework – Reactive Libraries: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
8. Spring Security – Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html

**Final self-assessment:** If a client sends the same GET or POST to both implementations, what must be identical for them to count as having the same HTTP contract? Why doesn't `@ControllerAdvice` replace every functional route filter? When does WebFlux.fn's route composition make code easier to control, and when do annotated method signatures save effort? Answer using status/header/body/error tests, not just by having two methods return the same object.
