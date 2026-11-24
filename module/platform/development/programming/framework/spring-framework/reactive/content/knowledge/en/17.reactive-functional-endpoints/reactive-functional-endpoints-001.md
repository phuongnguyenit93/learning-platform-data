# RouterFunction, HandlerFunction, ServerRequest, and ServerResponse in Spring WebFlux

## 1. What is WebFlux.fn?

**WebFlux.fn** is Spring WebFlux's function-based model for declaring endpoints. Instead of attaching mappings to methods with `@GetMapping`, `@PostMapping`, or `@RequestMapping`, we create request-handling functions and then declare routing rules through a Java API.

Four central contracts:

- **`RouterFunction<T extends ServerResponse>`**: determines which request is dispatched to which handler.
- **`HandlerFunction<T extends ServerResponse>`**: receives a `ServerRequest` and returns a Publisher containing a `ServerResponse`.
- **`ServerRequest`**: provides HTTP request information and an API for reading the body reactively.
- **`ServerResponse`**: describes the status, headers, and body that will be written to the HTTP response.

WebFlux.fn still runs on Spring WebFlux's Reactive Core. It is not a different HTTP server, it does not replace Reactor, and it does not create new threads on its own. The main difference is **how routing and handlers are organized**.

~~~text
HTTP request
    |
    v
DispatcherHandler
    |
    v
RouterFunctionMapping
    |
    +--> RouterFunction checks RequestPredicate
    |          |
    |          +--> match: HandlerFunction
    |          |
    |          +--> no match: try the next route
    |
    v
HandlerFunction.handle(ServerRequest)
    |
    v
Mono<ServerResponse>
    |
    v
HandlerFunctionAdapter
    |
    v
ServerResponseResultHandler
    |
    v
HttpMessageWriter / response body
    |
    v
HTTP response
~~~

WebFlux.fn is a good fit when you want to centralize route rules in one clear configuration, group handlers by business area, reuse predicates/filters, or build an API with many nested routes. The annotation model is still suitable for controllers with many methods and a familiar structure. The two models can coexist in a single WebFlux application.

## 2. The Four Core Contracts

### 2.1. `RouterFunction`: mapping a request to a handler

Conceptually, the contract looks like this:

~~~java
public interface RouterFunction<T extends ServerResponse> {
    Mono<HandlerFunction<T>> route(ServerRequest request);
}
~~~

When a request matches a route, `route(request)` returns a `Mono` containing the corresponding `HandlerFunction`. If no route matches, it returns `Mono.empty()` so that the dispatch mechanism continues looking for another handler or ends with a 404.

You rarely need to implement this interface yourself. Usually, use `RouterFunctions.route()` to build routes with the builder:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/hello", request ->
        ServerResponse.ok().bodyValue("Hello WebFlux.fn"))
    .build();
~~~

A `RouterFunction` can be combined with another route using `and(...)` or be created from a predicate and a handler. When there are multiple routes, the declaration order matters: routes are evaluated one after another, so you should place specific routes before general routes that may match the same request.

### 2.2. `HandlerFunction`: handling a request that has been routed

The contract:

~~~java
@FunctionalInterface
public interface HandlerFunction<T extends ServerResponse> {
    Mono<T> handle(ServerRequest request);
}
~~~

A handler receives a request that has matched a route and returns a `Mono<ServerResponse>`. It can be a short lambda or a method reference pointing to a method in a handler class:

~~~java
HandlerFunction<ServerResponse> hello = request ->
    ServerResponse.ok().bodyValue("Hello");
~~~

In real applications, you should group handlers of the same business area into their own class, for example `ProductHandler`, `OrderHandler`, or `AccountHandler`. This keeps the router focused on mapping and lets the handler focus on HTTP/domain logic.

### 2.3. `ServerRequest`: reading a request immutably

`ServerRequest` is an immutable interface that provides information such as:

- `method()`, `methodName()`: the HTTP method.
- `uri()`, `path()`: the URI and path.
- `pathVariable(name)`: a path variable declared by the route.
- `queryParam(name)`: the query parameter value as an `Optional<String>`.
- `headers()`, `cookies()`: headers and cookies.
- `remoteAddress()`: the remote address, if available.
- `principal()`: a Publisher containing the principal when authentication is integrated.
- `attributes()` and `attribute(name)`: attributes attached to the request.
- `bodyToMono(Class)`, `bodyToFlux(Class)`: read and decode the body into a Publisher.

Example of reading the path and query:

~~~java
public Mono<ServerResponse> search(ServerRequest request) {
    String category = request.pathVariable("category");
    String keyword = request.queryParam("q").orElse("");

    return ServerResponse.ok()
        .bodyValue("category=" + category + ", q=" + keyword);
}
~~~

If you need to change the request before passing it to the handler, use `ServerRequest.from(request)` to create a builder and build a new request. Do not modify the original request object directly.

### 2.4. `ServerResponse`: describing the HTTP response

`ServerResponse` is also an immutable interface. Instead of modifying the response object in place, we use a builder to create a new response.

Common factories:

| Factory | Meaning |
| --- | --- |
| `ServerResponse.ok()` | HTTP 200 |
| `ServerResponse.created(uri)` | HTTP 201 and Location |
| `ServerResponse.accepted()` | HTTP 202 |
| `ServerResponse.noContent()` | HTTP 204 |
| `ServerResponse.badRequest()` | HTTP 400 |
| `ServerResponse.notFound()` | HTTP 404 |
| `ServerResponse.status(code)` | Custom status |

Ways to finish the builder:

- `bodyValue(value)`: writes an existing object.
- `body(publisher, elementClass)`: writes the body from a Publisher.
- `build()`: a response without a body.
- `headers(...)`, `contentType(...)`, `header(...)`: set metadata before building.

Example:

~~~java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(Map.of("status", "ready"));
~~~

`bodyValue` and `body` return `Mono<ServerResponse>`. Therefore, the handler can combine this result with `flatMap`, `switchIfEmpty`, `onErrorResume`, or other Reactor operators.

## 3. Declaring Routes with `RouterFunctions.route()`

### 3.1. Routing by HTTP method and path

The builder provides readable shortcuts:

~~~java
RouterFunction<ServerResponse> router = RouterFunctions.route()
    .GET("/products", handler::list)
    .GET("/products/{id}", handler::get)
    .POST("/products", handler::create)
    .PUT("/products/{id}", handler::update)
    .DELETE("/products/{id}", handler::delete)
    .build();
~~~

Each method reference must be compatible with `HandlerFunction<ServerResponse>`, meaning the target method takes a `ServerRequest` and returns a `Mono<ServerResponse>`.

The snippet above is an illustrative mapping; the `list`, `get`, `create`, `update`, and `delete` methods must be implemented in the handler class.

### 3.2. Combining `RequestPredicate`

A route can require multiple conditions beyond method/path:

- `accept(MediaType...)`: checks the `Accept` header.
- `contentType(MediaType...)`: checks `Content-Type`.
- `path(String)`: checks the path.
- `method(HttpMethod)`: checks the HTTP method.
- `queryParam(name, value)`: checks a query parameter.
- `headers(Predicate<ServerRequest.Headers>)`: a condition on the headers.
- `GET(path)`, `POST(path)`, ...: predicates by HTTP method.

Example:

~~~java
RouterFunction<ServerResponse> router = RouterFunctions.route()
    .GET("/products/{id}",
        accept(MediaType.APPLICATION_JSON),
        handler::get)
    .POST("/products",
        contentType(MediaType.APPLICATION_JSON),
        handler::create)
    .build();
~~~

The GET route only accepts requests that can accept JSON; the POST route requires the body's `Content-Type` to be JSON. A predicate does not decode the body or validate business rules on its own. It only decides whether the request matches the route.

### 3.3. Combining predicates with `and`, `or`, and `negate`

~~~java
RequestPredicate jsonGet = method(HttpMethod.GET)
    .and(path("/reports/**"))
    .and(accept(MediaType.APPLICATION_JSON));

RequestPredicate reportRequest =
    path("/reports/**").or(path("/exports/**"));

RequestPredicate nonHealth = path("/health").negate();
~~~

- `and` requires both predicates to be true.
- `or` requires only one predicate to be true.
- `negate` inverts the predicate's result.

Predicates help avoid repeating conditions and create routes with business meaning. Avoid stuffing complex permission checks or database queries into a synchronous predicate; those tasks belong in a filter or a reactive handler.

### 3.4. Route order matters

A router function evaluates routes in order. If a general route matches first, the specific route after it may never be used.

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/files/{id}", handler::getFile)
    .GET("/files/**", handler::listFilesUnderPath)
    .build();
~~~

Place `/files/{id}` before `/files/**` if both can match the same request. This differs from annotation dispatch, where Spring has rules for selecting the more specific mapping.

When there are multiple `RouterFunction` beans in the application context, `RouterFunctionMapping` sorts them by order and combines them. If multiple routers have overlapping paths, the bean/router order must be designed explicitly, not rely on Java file order or incidental initialization order.

## 4. Nested Routes with `path` and `nest`

### 4.1. Grouping by path prefix

`path("/api", builder -> ...)` lets you group routes with the same prefix:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .path("/api", api -> api
        .GET("/products", handler::list)
        .GET("/products/{id}", handler::get)
        .POST("/products", handler::create))
    .build();
~~~

The inner paths are interpreted relative to the `/api` prefix. Grouping routes by resource makes the configuration easier to read when the API has many endpoints.

### 4.2. Nesting by a shared condition

`nest(predicate, builder -> ...)` applies one predicate to a whole group of routes:

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .path("/api", api -> api
        .nest(accept(MediaType.APPLICATION_JSON), json -> json
            .GET("/products", handler::list)
            .GET("/products/{id}", handler::get))
        .POST("/products",
            contentType(MediaType.APPLICATION_JSON),
            handler::create))
    .build();
~~~

The two GET routes in the group require `Accept: application/json`. The POST route sits outside that `nest` group and has its own `Content-Type` predicate.

Do not overuse multiple `nest` levels that make paths and conditions hard to follow. If a route has only one specific condition, the overload that accepts a predicate directly is usually easier to read.

### 4.3. Splitting a router into multiple modules

You can build separate RouterFunctions per business domain:

~~~java
RouterFunction<ServerResponse> productRoutes = productRouter.routes();
RouterFunction<ServerResponse> orderRoutes = orderRouter.routes();

RouterFunction<ServerResponse> api = productRoutes.and(orderRoutes);
~~~

`and` creates a combined router: when the left router does not find a handler, the right router is tried. If paths collide, the left router may win; therefore the composition order must be determined.

In a Spring Boot application, each router can be a `RouterFunction<ServerResponse>` bean. The framework will discover, sort, and combine them through `RouterFunctionMapping`.

## 5. Reading a Request with `ServerRequest`

### 5.1. Path variables and query parameters

~~~java
public Mono<ServerResponse> getById(ServerRequest request) {
    String id = request.pathVariable("id");

    return repository.findById(id)
        .flatMap(product -> ServerResponse.ok().bodyValue(product))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

`pathVariable` gets a variable declared in the route such as `/products/{id}`. For an optional query parameter:

~~~java
String sort = request.queryParam("sort").orElse("name");
~~~

If you need to handle multiple values with the same name, use the appropriate query parameters API instead of assuming there is always only one value.

### 5.2. Headers, cookies, and principal

~~~java
String requestId = request.headers().firstHeader("X-Request-Id");
String userAgent = request.headers().firstHeader("User-Agent");
HttpCookie session = request.cookies().getFirst("SESSION");
~~~

`request.principal()` returns a Publisher because obtaining the principal can be asynchronous and depends on Spring Security. Do not assume a request always has a logged-in user; handle the case where the Publisher is empty.

Do not use a header sent by the client as proof of authentication unless it has been verified by a trusted gateway or the security layer. A router predicate can check technical headers, but authorization should use reactive Spring Security.

### 5.3. Reading the body as `Mono<T>`

~~~java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateProduct.class)
        .flatMap(product -> repository.save(product))
        .flatMap(saved -> ServerResponse
            .created(URI.create("/products/" + saved.id()))
            .bodyValue(saved));
}
~~~

`bodyToMono` uses a codec to decode the request body into an object. The Publisher is only consumed when the subscription reaches it. Therefore, chain it into the Publisher chain that the handler returns; do not call `subscribe()` yourself.

If the body may be empty, handle it with `switchIfEmpty` or check the endpoint contract. If the JSON is invalid or the media type is not supported, the decode error goes into the reactive error path.

### 5.4. Reading the body as `Flux<T>`

~~~java
public Mono<ServerResponse> importRows(ServerRequest request) {
    return request.bodyToFlux(ImportRow.class)
        .flatMap(repository::save, 8)
        .count()
        .flatMap(total -> ServerResponse.ok().bodyValue(
            Map.of("saved", total)));
}
~~~

`bodyToFlux` is suitable when the request represents multiple elements. `flatMap(..., 8)` limits the concurrency of the save operation to at most 8 concurrent inner Publishers; if you need to preserve order, consider `concatMap` or `flatMapSequential`.

Do not collect a large stream with `collectList()` just for convenience if you can process item by item. Choose a codec and media type suited to the input format, for example NDJSON for line-delimited JSON objects.

### 5.5. The request body can usually only be consumed once

The body is a data stream tied to the HTTP request. You should not create two independent branches and then subscribe to the same body Publisher. Decode once and process the value in the same chain:

~~~java
return request.bodyToMono(CreateProduct.class)
    .flatMap(input ->
        repository.save(input)
            .flatMap(saved -> audit(saved)
                .thenReturn(saved)))
    .flatMap(saved -> ServerResponse.ok().bodyValue(saved));
~~~

If you need to use the data in multiple places, share the decoded object within the same `flatMap` or build a result structure containing the needed values. Only cache the body once you understand the memory limits, the number of subscribers, and the request lifecycle.

## 6. Creating a Response with `ServerResponse`

### 6.1. A successful response with an object

~~~java
return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product);
~~~

`bodyValue` takes an existing object and the framework chooses an `HttpMessageWriter` to encode it. If the object has no suitable codec, the response may fail when written.

### 6.2. A response body from a Publisher

~~~java
Flux<Product> products = repository.findAll();

return ServerResponse.ok()
    .contentType(MediaType.APPLICATION_JSON)
    .body(products, Product.class);
~~~

`body` takes a Publisher and the element class so the writer knows which type to encode. You can use `Mono` or `Flux`. For a JSON array, the codec may aggregate; if you want to stream element by element, choose a suitable media type such as NDJSON or SSE and test the actual writer.

### 6.3. A response without a body

~~~java
return ServerResponse.noContent().build();
~~~

Common cases:

~~~java
return ServerResponse.notFound().build();
return ServerResponse.accepted().build();
return ServerResponse.status(HttpStatus.CONFLICT).build();
~~~

A response without a body is still a `Mono<ServerResponse>` and the framework writes the status/headers following the normal lifecycle.

### 6.4. A created response and Location

~~~java
URI location = URI.create("/api/products/" + saved.id());

return ServerResponse.created(location)
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(saved);
~~~

`created(uri)` creates a 201 response and sets Location. The URI should reflect the newly created resource and match the application's base path/public URL. If the application runs behind a reverse proxy with a context path, consider how to build the URI according to the deployment configuration.

### 6.5. Headers and cookies

~~~java
return ServerResponse.ok()
    .header("X-Result-Source", "catalog")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(product);
~~~

You can set headers through the builder before finishing it. Do not try to modify headers after the body has started being written and the response is committed. For cookies/sessions, consider dedicated APIs and security policies such as Secure, HttpOnly, and SameSite.

## 7. Filters in WebFlux.fn

The functional routing builder provides three commonly used ways to intervene: `before`, `after`, and `filter`.

### 7.1. `before`: transforming the request before the handler

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/hello", handler::hello)
    .before(request -> ServerRequest.from(request)
        .header("X-Route-Source", "functional")
        .build())
    .build();
~~~

`before` receives the request that has matched a route and returns a new request to forward. Because `ServerRequest` is immutable, use the `ServerRequest.from(request)` builder instead of modifying the original request.

`before` is useful for adding metadata or normalizing the request within the router's scope. If you need to apply it to the whole HTTP pipeline, including annotated controllers or other routes, consider a `WebFilter`.

### 7.2. `after`: observing or transforming the response

~~~java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
    .GET("/hello", handler::hello)
    .after((request, response) -> {
        System.out.println(
            request.method() + " " + request.path()
            + " -> " + response.statusCode());
        return response;
    })
    .build();
~~~

`after` receives the request and response after the handler, and can return a different response if needed. Here we only log the status. The response is still an immutable description; if you want to change it, use a builder from the appropriate response instead of assuming it can be mutated directly.

Note: `after` observes the response object at the handler level. It is not confirmation that all bytes have been received or successfully processed by the client.

### 7.3. `filter`: wrapping a HandlerFunction

`filter` receives a `ServerRequest` and the next handler. It can call the handler, transform the result, or short-circuit:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> authFilter =
    (request, next) -> {
        String token = request.headers().firstHeader("X-Api-Key");

        if ("demo-secret".equals(token)) {
            return next.handle(request);
        }

        return ServerResponse.status(HttpStatus.UNAUTHORIZED).build();
    };
~~~

This is only an illustrative example of a predicate that checks a key; do not use a hard-coded secret as a production authentication mechanism. In real applications, use reactive Spring Security, a token verifier, and trustworthy authorization rules.

You can handle errors in a filter:

~~~java
HandlerFilterFunction<ServerResponse, ServerResponse> badRequestFilter =
    (request, next) -> next.handle(request)
        .onErrorResume(IllegalArgumentException.class, error ->
            ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("error", error.getMessage())));
~~~

The filter above only maps `IllegalArgumentException`. Other errors continue to propagate outward so that the framework's exception handling can process them.

### 7.4. Scope of nested filters

A filter declared on a given builder applies to the routes belonging to that builder. A filter in a nested route group does not automatically apply to routes at the outer level or to a separate router.

Place filters at the right level:

- Application-wide cross-cutting concerns: `WebFilter`.
- Concerns of a group of functional routes: a filter on that group's builder.
- Concerns of a single handler: handle them directly in the handler or compose a separate function.

CORS for functional endpoints is supported through WebFlux's CORS mechanism, typically using `CorsWebFilter` or the corresponding configuration; you should not rewrite the whole CORS logic with a route filter if the framework already provides the policy.

## 8. Error Handling in Handlers and Route Filters

### 8.1. Business errors in a handler

A handler can return an error Publisher:

~~~java
public Mono<ServerResponse> get(ServerRequest request) {
    return repository.findById(request.pathVariable("id"))
        .flatMap(product -> ServerResponse.ok().bodyValue(product))
        .switchIfEmpty(ServerResponse.notFound().build());
}
~~~

Data not found is represented by a 404 response. If the error is a system error or a business error that needs separate handling, you can use `onErrorResume` in the pipeline or let the error go to outer exception handling.

### 8.2. Mapping errors with a filter

A filter can handle a group of errors that applies to one router:

~~~java
.filter((request, next) -> next.handle(request)
    .onErrorResume(ProductValidationException.class, error ->
        ServerResponse.badRequest()
            .bodyValue(Map.of("error", "INVALID_PRODUCT"))))
~~~

Do not return internal messages, SQL, or stack traces to the client. Use stable error codes; log details on the server side with a correlation ID.

### 8.3. Distinguishing route filter, WebFilter, and WebExceptionHandler

| Mechanism | Scope | Use when |
| --- | --- | --- |
| `HandlerFilterFunction` | The handlers in the RouterFunction the filter is attached to | Logic before/after a functional handler, short-circuiting, per-route error handling |
| `WebFilter` | The whole WebFlux web handler chain | Request ID, CORS, logging, security integration, application-wide logic |
| `WebExceptionHandler` | Errors that escape the filter/handler chain | Converting web-level errors into an HTTP response or propagating the error |

If an error arises in a handler function and the filter has mapped it to a response, the error does not continue to the WebExceptionHandler. If the filter does not handle it, the error continues along the reactive error path. Do not use multiple layers that all write a response for the same error.

### 8.4. Route not found and an error in a handler are two different things

If no RouterFunction matches, the framework does not call a handler for that route; the request usually ends with a 404. If a route has matched but the handler throws an error, that is an error during processing and follows the error pipeline. Distinguish a 404 caused by no route from a 404 that the handler deliberately returns when the resource is not found.

## 9. Combining WebFlux.fn with Spring Boot

### 9.1. Declaring a RouterFunction bean

In a Spring Boot application, you only need to declare a bean:

~~~java
@Configuration
public class ApiRoutes {

    @Bean
    RouterFunction<ServerResponse> routes(ProductHandler handler) {
        return RouterFunctions.route()
            .GET("/products", handler::list)
            .GET("/products/{id}", handler::get)
            .POST("/products", handler::create)
            .build();
    }
}
~~~

The Spring Boot WebFlux starter provides the functional endpoint infrastructure. In the WebFlux Java configuration, the main components include:

- `RouterFunctionMapping`: finds and combines `RouterFunction<?>` beans.
- `HandlerFunctionAdapter`: lets `DispatcherHandler` invoke the matched `HandlerFunction`.
- `ServerResponseResultHandler`: writes the `ServerResponse` result to the HTTP response.

Therefore, functional endpoints remain within the `DispatcherHandler` lifecycle. They can be used together with annotated controllers in the same application.

### 9.2. No need to create an HTTP server for the router yourself

`RouterFunctions.toHttpHandler(router)` can convert a RouterFunction into an `HttpHandler` to install into a server adapter when you need to set up the infrastructure manually.

But in a normal Spring Boot application, making the router a bean is enough. Boot and WebFlux Config will wire the routes to the server in use, for example Reactor Netty. Creating a second server or `HttpHandler` yourself can complicate the configuration and leave routes outside the pipeline you expect.

### 9.3. Using functional routes together with annotated controllers

The two models are both based on the Reactive Core and can coexist:

- Annotated controllers are suitable when you want to group endpoints by class and method mapping.
- WebFlux.fn is suitable when you want routes/handlers to be represented as objects and composable functions.
- `WebFilter` and `WebExceptionHandler` still have pipeline-wide scope regardless of which model a route uses.

If you declare two endpoints with the same path/method in the two models, the mappings may compete. Avoid overlap or define the order explicitly so you do not depend on arbitrary configuration.

## 10. A Complete Spring Boot 3.5.7 + Java 17 Example

The example builds a small product management API with WebFlux.fn:

- `GET /api/products`: list products.
- `GET /api/products/{id}`: get one product.
- `POST /api/products`: create a product from JSON.
- A route filter maps validation errors to HTTP 400.
- `before` attaches a request header to the route group; `after` logs the status.

Use Spring Boot **3.5.7**, Java 17, and Maven. The project only uses `spring-boot-starter-webflux`; do not add `spring-boot-starter-web`, because the MVC starter can make the application pick the wrong web stack.

### 10.1. Directory structure

~~~text
webflux-functional-api/
├── pom.xml
└── src/main/java/example/functional/
    ├── FunctionalApiApplication.java
    ├── ProductHandler.java
    └── ProductRoutes.java
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>webflux-functional-api</artifactId>
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

### 10.3. `FunctionalApiApplication.java`

~~~java
package example.functional;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FunctionalApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(FunctionalApiApplication.class, args);
    }
}
~~~

### 10.4. `ProductHandler.java`

~~~java
package example.functional;

import java.net.URI;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class ProductHandler {

    public record Product(String id, String name, int price) {}

    public record CreateProduct(String name, int price) {}

    private final List<Product> products =
        new CopyOnWriteArrayList<>(List.of(
            new Product("1", "Keyboard", 120),
            new Product("2", "Mouse", 45)
        ));

    private final AtomicLong sequence = new AtomicLong(2);

    public Mono<ServerResponse> list(ServerRequest request) {
        return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .body(Flux.fromIterable(products), Product.class);
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        String id = request.pathVariable("id");

        return Mono.justOrEmpty(
                products.stream()
                    .filter(product -> product.id().equals(id))
                    .findFirst())
            .flatMap(product -> ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(product))
            .switchIfEmpty(ServerResponse.notFound().build());
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateProduct.class)
            .switchIfEmpty(Mono.error(
                new IllegalArgumentException("Request body is required")))
            .flatMap(input -> {
                if (input.name() == null || input.name().isBlank()
                        || input.price() < 0) {
                    return Mono.error(new IllegalArgumentException(
                        "name is required and price must be non-negative"));
                }

                Product saved = new Product(
                    Long.toString(sequence.incrementAndGet()),
                    input.name(),
                    input.price()
                );
                products.add(saved);

                URI location = URI.create("/api/products/" + saved.id());

                return ServerResponse.created(location)
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(saved);
            });
    }
}
~~~

The list in the example uses `CopyOnWriteArrayList` to demo simple reads/writes with a small volume. It is not the optimal choice for write-heavy workloads; real applications should use a reactive repository/database or a suitable storage structure.

### 10.5. `ProductRoutes.java`

~~~java
package example.functional;

import static org.springframework.http.MediaType.APPLICATION_JSON;
import static org.springframework.web.reactive.function.server.RequestPredicates.accept;
import static org.springframework.web.reactive.function.server.RequestPredicates.contentType;

import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.HandlerFilterFunction;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class ProductRoutes {

    @Bean
    RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
        HandlerFilterFunction<ServerResponse, ServerResponse> badRequestFilter =
            (request, next) -> next.handle(request)
                .onErrorResume(IllegalArgumentException.class, error ->
                    ServerResponse.badRequest()
                        .contentType(APPLICATION_JSON)
                        .bodyValue(Map.of("error", error.getMessage())));

        return RouterFunctions.route()
            .path("/api", api -> api
                .nest(accept(APPLICATION_JSON), json -> json
                    .GET("/products", handler::list)
                    .GET("/products/{id}", handler::get))
                .POST("/products",
                    contentType(APPLICATION_JSON),
                    handler::create)
                .filter(badRequestFilter))
            .before(request -> ServerRequest.from(request)
                .header("X-Functional-Route", "products")
                .build())
            .after((request, response) -> {
                System.out.println(
                    request.method() + " " + request.path()
                    + " -> " + response.statusCode());
                return response;
            })
            .build();
    }
}
~~~

Points to observe:

1. `path("/api", ...)` groups routes that share a prefix.
2. `nest(accept(APPLICATION_JSON), ...)` applies the Accept condition to the two GET routes.
3. The POST route checks the JSON `Content-Type` separately.
4. `HandlerFilterFunction` converts validation errors into a 400 response.
5. `before` creates a new request with the `X-Functional-Route` header.
6. `after` observes the status after the handler and returns the response onward to the writer.

### 10.6. Running the application

Install JDK 17+ and Maven, then from the directory containing `pom.xml` run:

~~~bash
mvn spring-boot:run
~~~

Get one product:

~~~bash
curl -i http://localhost:8080/api/products/1 -H "Accept: application/json"
~~~

Expected response body:

~~~json
{"id":"1","name":"Keyboard","price":120}
~~~

List:

~~~bash
curl -i http://localhost:8080/api/products -H "Accept: application/json"
~~~

The body contains the two initial products. The order from the initial list is Keyboard then Mouse.

Create a product:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"name":"Pen","price":15}'
~~~

The expected response has status `201 Created`, a `Location` header pointing to `/api/products/3`, and the body:

~~~json
{"id":"3","name":"Pen","price":15}
~~~

Try invalid data:

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"","price":-1}'
~~~

The expected response is HTTP 400 with a body similar to:

~~~json
{"error":"name is required and price must be non-negative"}
~~~

Try a nonexistent id:

~~~bash
curl -i http://localhost:8080/api/products/999
~~~

The handler returns HTTP 404 with an empty body.

## 11. Testing Functional Endpoints with `WebTestClient`

You can test the whole running application with `@SpringBootTest` and `WebTestClient`:

~~~java
package example.functional;

import static org.springframework.http.MediaType.APPLICATION_JSON;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductRoutesIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void getsExistingProduct() {
        client.get()
            .uri("/api/products/1")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void createsProduct() {
        client.post()
            .uri("/api/products")
            .contentType(APPLICATION_JSON)
            .bodyValue(new ProductHandler.CreateProduct("Pen", 15))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.name").isEqualTo("Pen");
    }

    @Test
    void mapsInvalidInputToBadRequest() {
        client.post()
            .uri("/api/products")
            .contentType(APPLICATION_JSON)
            .bodyValue(new ProductHandler.CreateProduct("", -1))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.error")
            .isEqualTo("name is required and price must be non-negative");
    }

    @Test
    void returnsNotFoundForUnknownId() {
        client.get()
            .uri("/api/products/999")
            .accept(APPLICATION_JSON)
            .exchange()
            .expectStatus().isNotFound();
    }
}
~~~

This is an integration test using a random-port server. You can test a RouterFunction in isolation with `WebTestClient.bindToRouterFunction(router).build()` when you want to test routing without building the whole ApplicationContext. Integration testing is still useful to verify that bean discovery, codecs, handler adapter, and response writer work together.

Run the tests:

~~~bash
mvn test
~~~

The assertions focus on the HTTP contract: status, headers, and JSON body. You should not check thread order or the absolute timing of a reactive pipeline in ordinary routing tests.

## 12. Distinguishing WebFlux.fn from Annotated Controllers

| Criterion | WebFlux.fn | Annotated controller |
| --- | --- | --- |
| Route declaration | `RouterFunction` + predicate | `@RequestMapping`, `@GetMapping`, ... |
| Handler | `HandlerFunction` or a handler class | A method in a `@Controller` |
| Request | `ServerRequest` | Method parameters supplied by resolvers |
| Response | `ServerResponse` | Return value processed by a HandlerResultHandler |
| Route grouping | `path`, `nest`, composition | Class/package/controller structure |
| Per-route filter | `HandlerFilterFunction`, before/after | `WebFilter`, interceptor/advice by scope |
| Best for | Routing composition, functional style, endpoint modules | Traditional CRUD/controllers, annotations and argument resolvers |

Both use `Mono`/`Flux`, codecs, backpressure, WebFilter, and WebFlux's server runtime. Choose a model based on how the code is organized and the project's requirements; there is no rule that functional endpoints are always faster or always better than controllers.

## 13. Common Mistakes and How to Avoid Them

**Mistake 1 — Confusing `RouterFunction` with a handler that processes the body.** The router only decides which route fits and supplies the handler; the logic for reading the body/writing the response lives in `HandlerFunction`.

**Mistake 2 — A handler returns an object directly instead of a Publisher.** `HandlerFunction` returns `Mono<ServerResponse>`. Use `ServerResponse.ok().bodyValue(value)` or `body(publisher, type)`.

**Mistake 3 — Forgetting to build the router.** The builder only describes routes; you need to call `build()` to get the complete `RouterFunction`.

**Mistake 4 — A general route placed before a specific route.** The router evaluates sequentially; a general route may catch the request first. Put specific mappings first.

**Mistake 5 — Confusing `Accept` with `Content-Type`.** Accept describes the format the client wants to receive; Content-Type describes the format of the request body being sent. Use `accept(...)` for response conditions and `contentType(...)` for the request body.

**Mistake 6 — Reading the body twice.** The body is usually a one-time stream. Decode once and then chain the operations into the same pipeline.

**Mistake 7 — Calling `subscribe()` in a handler.** It creates a subscription outside the response lifecycle, making it easy for the response to be returned before the business logic completes. Return the Publisher to the framework.

**Mistake 8 — Calling `block()` to get data.** It blocks WebFlux's non-blocking thread. Compose with `map`, `flatMap`, `then` and return a Publisher.

**Mistake 9 — Using `bodyValue` for a Publisher and expecting it to stream like `body`.** `bodyValue` takes an existing value; `body(publisher, elementClass)` is for a reactive body.

**Mistake 10 — Forgetting to handle an empty body.** `bodyToMono` can complete empty. Use `switchIfEmpty` when the request body is required.

**Mistake 11 — Not distinguishing decode errors from business errors.** Malformed JSON can fail before the handler receives the object. Business validation happens after decoding; it can be handled through a filter or an appropriate error pipeline.

**Mistake 12 — Using a route filter in place of a security framework.** `HandlerFilterFunction` is useful for per-router logic but does not replace full authentication/authorization. Use reactive Spring Security.

**Mistake 13 — Placing a filter at the wrong nested builder level.** A filter in a route group only applies to that scope. Put application-wide filters in `WebFilter`.

**Mistake 14 — Thinking `after` proves the client received the response.** It observes the `ServerResponse` at the handler level; the bytes still have to pass through the writer, server, network, and client.

**Mistake 15 — Returning internal errors directly to the client.** Do not expose stack traces, SQL, or tokens. Use stable error codes and log safely on the server.

**Mistake 16 — Declaring a route that duplicates an annotated controller.** The mappings may compete and produce hard-to-predict results. Avoid overlap or configure the order deliberately.

**Mistake 17 — Creating multiple router beans with overlapping paths without checking the order.** Spring combines routers in order; manage the order and composition explicitly.

**Mistake 18 — Using functional endpoints but building an unnecessary HTTP server yourself.** In Boot, the router bean is already integrated into the DispatcherHandler. Only use `RouterFunctions.toHttpHandler` when you truly manage the server adapter yourself.

## 14. Self-Check Exercises

1. What does `RouterFunction` take and return, conceptually? **It takes a `ServerRequest` and returns a `Mono<HandlerFunction>`; empty if there is no match.**
2. What type does `HandlerFunction` take and what type does it return? **It takes a `ServerRequest` and returns a `Mono<ServerResponse>`.**
3. Can the `ServerRequest` and `ServerResponse` interfaces be mutated directly? **No; the contracts are immutable, use a builder to create a new instance.**
4. When do you use `accept(APPLICATION_JSON)`? **When the route requires the client to accept a JSON response.**
5. When do you use `contentType(APPLICATION_JSON)`? **When the route requires the request body being sent to have a JSON Content-Type.**
6. If two routes can both match, which one is tried first? **The route declared/combined first in the router order.**
7. Does `request.bodyToMono(Product.class)` read the body as soon as the method is called? **It creates a Publisher; the body is consumed when the subscription reaches that Publisher.**
8. How does `ServerResponse.ok().bodyValue(product)` differ from `body(flux, Product.class)`? **One writes a single object; the other writes the body from a Publisher.**
9. Where do `before` and `after` operate? **Before the handler to transform the request, and after the handler to observe/transform the response within the router.**
10. Can a `HandlerFilterFunction` block a request without calling the next handler? **Yes; it can return a response directly.**
11. Does a route filter automatically apply to annotated controllers? **No; it is attached to a specific RouterFunction. Use WebFilter for the whole pipeline.**
12. Can functional endpoints be used together with annotated controllers? **Yes, both run within the same DispatcherHandler infrastructure.**
13. What happens if no RouterFunction matches? **There is no handler for the request; the result is typically a 404.**
14. Why not subscribe yourself in a handler? **So the framework manages errors, cancellation, and the response lifecycle within the same subscription.**
15. What is the common way to test a functional router? **`WebTestClient.bindToRouterFunction` for a standalone router, or `@SpringBootTest`/`WebTestClient` for integration.**
16. Should `HandlerFilterFunction` be used as the entire production authorization mechanism? **No; use reactive Spring Security and only use route filters for appropriate cross-cutting parts.**

## 15. Key Takeaways and References

- **`RouterFunction`** routes a `ServerRequest` to a `HandlerFunction`; a route that does not match returns an empty Publisher.
- **`HandlerFunction`** handles the request and returns a `Mono<ServerResponse>`.
- **`ServerRequest`** and **`ServerResponse`** are immutable contracts that support reactive bodies and backpressure.
- Use `RouterFunctions.route()`, predicates, `path`, and `nest` to create clear routes.
- Use `bodyToMono`/`bodyToFlux` to read the request and `bodyValue`/`body` to write the response.
- `before`, `after`, and `HandlerFilterFunction` apply logic within the router's scope; `WebFilter` covers the entire pipeline.
- In Spring Boot, a RouterFunction bean is integrated through `RouterFunctionMapping`, `HandlerFunctionAdapter`, and `ServerResponseResultHandler`.
- The framework manages the subscription; do not subscribe/block yourself in a handler.

Official documentation:

1. [Spring Framework Reference — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): the overall model, HandlerFunction, ServerRequest, ServerResponse, RouterFunction, predicates, nested routes, filters, and how to run the server.
2. [Spring Framework Reference — Reactive Core](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html): the reactive foundation, backpressure, and how WebFlux handles Publishers.
3. [Spring Framework Javadoc — RouterFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/RouterFunction.html): the route contract and composition.
4. [Spring Framework Javadoc — HandlerFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/HandlerFunction.html): the contract for handling a ServerRequest.
5. [Spring Framework Javadoc — ServerRequest](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html) and [ServerResponse](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html): the API for reading requests, bodies, and building responses.
6. [Spring Framework Javadoc — HandlerFilterFunction](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/function/server/HandlerFilterFunction.html): filters in the functional handler chain.
7. [Spring Boot Reference — Reactive Web Applications](https://docs.spring.io/spring-boot/3.5/reference/web/reactive.html): how Spring Boot auto-configures WebFlux and functional endpoints.
