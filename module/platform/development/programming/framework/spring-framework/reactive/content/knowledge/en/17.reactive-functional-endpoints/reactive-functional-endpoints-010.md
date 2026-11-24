# Separating Business Logic from Routing and HTTP Conversion in Spring WebFlux

## 1. Goal: Keeping a Clear Boundary Between HTTP and Business Logic

An endpoint receives an HTTP request, determines the operation to run, reads input data, invokes business logic, and creates an HTTP response. If all of these steps live in a single function, the code quickly couples business rules to URLs, status codes, JSON DTOs, and framework APIs. When changing routing, adding another interface, or testing a use case without starting an HTTP server, you end up carrying unnecessary dependencies.

In Spring WebFlux, the functional endpoint model (`WebFlux.fn`) helps express three responsibilities clearly:

1. **Router**: identifies the request by path, HTTP method, and predicates; forwards the request to the appropriate handler.
2. **Handler**: works at the HTTP boundary. The handler reads `ServerRequest`, decodes the body, converts HTTP DTOs into commands, calls the application service, and then converts the result into `ServerResponse`.
3. **Application service / domain**: executes use cases and business rules. This layer does not need to know about `ServerRequest`, `ServerResponse`, URLs, HTTP statuses, or JSON.

A repository port and storage adapter can sit behind the service. The handler should not query the database or perform business calculations itself; the router should not contain use-case logic.

This lesson uses an order creation and lookup example. The same use case can be invoked from an HTTP functional endpoint, a message consumer, a scheduler, or another use case without rewriting pricing and order validation rules.

After this lesson, you can:

- Distinguish `RouterFunction`, `HandlerFunction`, `ServerRequest`, and `ServerResponse`.
- Organize routers, handlers, services, domain models, and repositories into classes with distinct responsibilities.
- Convert between HTTP DTOs and commands/results without leaking HTTP types into business logic.
- Place validation in the right layer and map business errors into HTTP responses at the boundary.
- Test routers/handlers with `WebTestClient` and test services with `StepVerifier`.
- Recognize signs that a handler or service is taking on too many responsibilities.

## 2. How Do Functional Endpoints in WebFlux.fn Work?

Spring WebFlux supports two models for building HTTP endpoints:

- **Annotation-based**: `@RestController`, `@GetMapping`, `@PostMapping`, `@RequestBody`...
- **Functional endpoint (WebFlux.fn)**: `RouterFunction`, `HandlerFunction`, `ServerRequest`, `ServerResponse`.

These are two ways of declaring HTTP endpoints on the same reactive WebFlux foundation. Functional endpoints are not a different server and do not replace Reactor.

In WebFlux.fn:

- `RouterFunction<ServerResponse>` is a function that takes a `ServerRequest` and finds a matching `HandlerFunction`.
- `HandlerFunction<ServerResponse>` is a function that takes a `ServerRequest` and returns a `Mono<ServerResponse>`.
- `ServerRequest` and `ServerResponse` are HTTP abstractions with immutable contracts; the body is represented by `Mono` or `Flux`.
- `RequestPredicate` represents routing conditions such as path, method, `Accept`, `Content-Type`, or headers.

Model:

```text
HTTP request
     |
     v
RouterFunction
  path + method + predicates
     |
     v
HandlerFunction
  ServerRequest -> Mono<ServerResponse>
     |
     +--> decode HTTP body / read path and query values
     |
     +--> map HTTP DTO to application command
     |
     v
Application service / domain
  execute use case and business rules
     |
     v
Repository port -> persistence adapter
     |
     v
Domain result
     |
     v
Handler maps result to HTTP response
     |
     v
ServerResponse -> HTTP response
```

The router only decides **where the request goes**. The handler coordinates **conversion at the HTTP boundary**. The service decides **what the business logic must do**.

### Short router declaration

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/orders/{id}", handler::get)
                .POST("/orders", handler::create)
                .build();
```

`handler::get` and `handler::create` are method references to handlers of the form `Mono<ServerResponse> method(ServerRequest request)`. The router does not need to know how the service calculates order totals.

Routes are evaluated in declaration order. When both a specific route and a general route can match, place the specific route first. This is worth remembering when comparing with annotation-based mapping, where Spring picks the best-fitting mapping by specificity.

## 3. Four Layers of Responsibility and What Not to Put in Each Layer

| Layer | Responsibility | Should not do |
|---|---|---|
| Router | Combines path, method, request predicates, and handler | Calculate prices, check inventory, query repositories |
| HTTP handler | Reads request, decodes body, maps DTO/command, calls service, maps result/status | Contain business rules or manage transactions itself |
| Application service / domain | Executes use cases, checks invariants and business rules | Accept `ServerRequest`, return `ServerResponse`, read headers |
| Repository adapter | Saves and retrieves data via the port | Decide HTTP status or read query parameters |

For example, the same rule "quantity per item must be from 1 to 100" can apply when orders arrive from HTTP, a message queue, or a batch job. If the rule lives in `OrderHandler`, other sources will have to duplicate it or mistakenly call HTTP code. Placing it in the service/domain lets every entry point use the same rule.

### Which direction should dependencies point?

```text
Web adapter (Router + Handler)
             |
             v
      Application service
             |
             v
        Domain model
             ^
             |
     Repository port
             ^
             |
  Persistence adapter
```

The diagram illustrates the dependency idea: the HTTP adapter calls the use case; the service depends on the repository abstraction; the persistence adapter implements that abstraction. In a small application, you may not need to split every interface and module yet, but you should still preserve responsibility boundaries.

You do not necessarily need to create one class per method or one interface per object. Split classes when there is a clear reason: multiple adapters need the same use case, logic needs independent testing, or persistence changes should not affect business logic.

## 4. Router: Only Routing and Combining Request Predicates

The router describes how HTTP requests are dispatched to handlers. It can declare method/path:

```java
@Bean
RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
    return RouterFunctions.route()
            .POST("/api/orders", handler::create)
            .GET("/api/orders/{id}", handler::get)
            .build();
}
```

You can add predicates for `Accept` or other conditions:

```java
@Bean
RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
    return RouterFunctions.route()
            .POST(
                    "/api/orders",
                    RequestPredicates.accept(MediaType.APPLICATION_JSON),
                    handler::create)
            .GET(
                    "/api/orders/{id}",
                    RequestPredicates.accept(MediaType.APPLICATION_JSON),
                    handler::get)
            .build();
}
```

Predicates are combined with `and` or `or`:

```java
RequestPredicate jsonOrText =
        RequestPredicates.accept(MediaType.APPLICATION_JSON)
                .or(RequestPredicates.accept(MediaType.TEXT_PLAIN));
```

Use predicates for HTTP conditions that have routing meaning. If you need to check order data, that is the job of the service/domain. Do not put database queries or logic like "does the customer have enough credit limit" into router lambdas.

### Nested routes for a shared prefix

When multiple routes share a prefix, you can group them:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .path("/api/orders", builder -> builder
                        .GET("/{id}", handler::get)
                        .POST(handler::create))
                .build();
```

Nested routes are useful when there are shared paths or predicates. Avoid nesting too many levels, which makes the routing flow hard to read; one route group per resource is usually enough.

### Route order

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/api/orders/search", handler::search)
                .GET("/api/orders/{id}", handler::get)
                .GET("/api/{resource}/{id}", handler::genericGet)
                .build();
```

Specific routes should be declared before general routes. A router function is evaluated sequentially; the first matching route can handle the request and prevent later routes from being evaluated.

### The router is not the place to handle authentication

You can use `HandlerFilterFunction` to apply shared behavior at the route boundary, but production authentication and authorization should rely on Spring Security/WebFlux Security and the security context. A predicate checking for the presence of a header does not prove the sender is authenticated.

## 5. Handler: Adapter Between HTTP and Application Service

The handler is where HTTP enters and leaves the application. A typical handler performs:

1. Read path variables, query parameters, headers, or the body from `ServerRequest`.
2. Use a codec to decode the body into a request DTO.
3. Convert the DTO into an application-layer command/query.
4. Call the application service and return the publisher.
5. Convert the domain result into a response DTO.
6. Choose the HTTP status/headers/body and map errors to match the API contract.

The handler should not call `.subscribe()` or `.block()` itself. It returns `Mono<ServerResponse>` so WebFlux manages subscription and backpressure.

Example of a handler reading the body:

```java
@Component
public class OrderHandler {

    private final OrderService orderService;

    public OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .map(this::toCommand)
                .flatMap(orderService::create)
                .flatMap(this::createdResponse);
    }
}
```

This is a condensed structure; the `toCommand` and `createdResponse` functions will be defined below. `bodyToMono` is the HTTP decode boundary; `orderService.create` is the use-case call.

### Reading path/query/header

```java
public Mono<ServerResponse> get(ServerRequest request) {
    String id = request.pathVariable("id");

    return orderService.findById(id)
            .flatMap(this::okResponse)
            .switchIfEmpty(ServerResponse.notFound().build());
}
```

The handler takes `id` from the path and passes it to the service. If `id` has a complex domain format, it can be converted into a value object in the adapter or service according to the application's conventions. Do not make the domain know about `ServerRequest.pathVariable`.

### Converting a DTO to a command

The HTTP request DTO reflects the API contract:

```java
public record CreateOrderRequest(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

The command reflects the needs of the use case:

```java
public record CreateOrderCommand(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

The handler converts:

```java
private CreateOrderCommand toCommand(CreateOrderRequest request) {
    List<CreateOrderCommand.Item> items =
            request.items() == null
                    ? null
                    : request.items().stream()
                            .map(item -> item == null
                                    ? null
                                    : new CreateOrderCommand.Item(
                                            item.sku(), item.quantity()))
                            .toList();

    return new CreateOrderCommand(request.customerId(), items);
}
```

This is mapping at the boundary. If the API later changes `customerId` into a different structure, the application service can still keep the command stable. You do not necessarily need to create separate DTOs and commands when two contracts are truly identical and there is no reason to split; just never let `ServerRequest` or HTTP response objects leak into the service.

## 6. Application Service and Domain: Keeping Business Logic Independent of HTTP

The service receives data meaningful to the use case, enforces rules, and returns the result. The service does not need to know whether the request came from `POST /api/orders` or from a message consumer.

Example:

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        return Mono.defer(() -> {
            validate(command);

            Order order = buildOrder(command);
            return repository.save(order);
        });
    }

    public Mono<Order> findById(String id) {
        return repository.findById(id);
    }

    private void validate(CreateOrderCommand command) {
        // Business rules belong here.
    }

    private Order buildOrder(CreateOrderCommand command) {
        // Build domain result; no HTTP status or ServerRequest.
        throw new UnsupportedOperationException("Illustrative only");
    }
}
```

This is an illustrative responsibility diagram, not a complete runnable class because `buildOrder` is kept abbreviated. The full program in Section 12 provides a runnable implementation.

Points to note:

- `Mono.defer` defers validation/building the order until subscription time, which is suitable when you want errors emitted as reactive errors.
- The service can return `Mono<Order>` because persistence is reactive, but should not return `Mono<ServerResponse>`.
- Domain exceptions express business problems such as `InvalidOrderException`; the handler decides how to map it to HTTP 422, 409, or another status according to the API contract.
- The service should not accept `HttpStatus`, `ServerRequest`, `ResponseEntity`, or `ProblemDetail`.

### Why can the service depend on Reactor yet not on HTTP?

A reactive application service often returns `Mono<T>`/`Flux<T>` because persistence or downstream operations are non-blocking. Reactor describes how results are executed and emitted; it is not the HTTP protocol. The service can be called from various reactive adapters.

If you want a pure Java domain model with no Reactor dependency, you can keep domain methods synchronous and place reactive composition in the application service. Choose what fits the architecture; the key is not letting domain rules depend on HTTP.

## 7. Repository Port and Persistence Adapter

The service should work with an abstraction describing storage needs:

```java
public interface OrderRepository {
    Mono<Order> save(Order order);
    Mono<Order> findById(String id);
}
```

An in-memory adapter:

```java
@Repository
public class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders = new ConcurrentHashMap<>();

    @Override
    public Mono<Order> save(Order order) {
        return Mono.fromSupplier(() -> {
            orders.put(order.id(), order);
            return order;
        });
    }

    @Override
    public Mono<Order> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(orders.get(id)));
    }
}
```

In a real application, the adapter can use R2DBC, reactive MongoDB, or WebClient to another service. The service still calls `OrderRepository`; it does not need to know whether it is `ConcurrentHashMap`, SQL, or a remote API.

### Why doesn't the handler call the repository directly?

If the handler calls the repository and calculates prices, checks customers, and saves orders itself, it becomes an application service in disguise. When a message consumer needs to create an order, that logic would have to be duplicated. The handler should only convert the HTTP request into a command and call the use case.

The repository should not return `ServerResponse.notFound()` either. Not finding an order is a query/domain result; turning it into HTTP 404 is a decision for the HTTP adapter.

## 8. Converting Domain Results into HTTP Responses

The handler turns the application result into a response DTO and appropriate status:

```java
private Mono<ServerResponse> createdResponse(Order order) {
    OrderResponse response = OrderResponse.from(order);

    return ServerResponse.created(
                    URI.create("/api/orders/" + order.id()))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(response);
}

private Mono<ServerResponse> okResponse(Order order) {
    return ServerResponse.ok()
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(OrderResponse.from(order));
}
```

`OrderResponse` is a DTO meant for the API. You are not forced to return domain entities directly; response DTOs help control which fields are exposed, data formatting, and versioning.

In a real application, when creating `Location`, use a URI builder that handles base path/host per deployment configuration instead of concatenating URLs arbitrarily. The complete example below uses `ServerRequest.uriBuilder()` to preserve the current request URI.

### Domain results should not carry HTTP status

Do not write a service like:

```java
public Mono<ResponseEntity<Order>> create(...) {
    // Business use case returns HTTP response object.
}
```

This approach forces the application layer to know Spring MVC/WebFlux HTTP APIs. Instead, the service returns `Mono<Order>`; the handler decides `201 Created`, `200 OK`, `404 Not Found`, or an error.

## 9. Error Mapping: Preserving the Cause, Changing Representation at the Boundary

You should distinguish three groups:

- **Input/transport error**: malformed JSON body, missing body, unsupported media type, or invalid path/query. The framework/HTTP adapter usually handles this group.
- **Domain/application error**: invalid quantity, nonexistent SKU, disallowed business state. The service emits a domain exception or typed error result.
- **Unexpected infrastructure error**: database/network failure or bug. Do not turn all of these into 400/422.

For example, the service emits `InvalidOrderException` when an order rule is violated. The handler maps it to `422 Unprocessable Content` according to the chosen contract:

```java
private Mono<ServerResponse> invalidOrder(InvalidOrderException error) {
    ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.UNPROCESSABLE_ENTITY,
            error.getMessage());

    problem.setTitle("Invalid order");

    return ServerResponse.status(HttpStatus.UNPROCESSABLE_ENTITY)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .bodyValue(problem);
}
```

Errors can be handled in the handler:

```java
return orderService.create(command)
        .flatMap(this::createdResponse)
        .onErrorResume(
                InvalidOrderException.class,
                this::invalidOrder);
```

Or place shared handling at the filter/router boundary if multiple routes share the same policy. Either way, the application service only emits domain errors; it does not choose HTTP statuses itself.

### 400, 404, 409, 422, and 500

| Scenario | Potentially suitable status | Where decided |
|---|---:|---|
| Malformed or undecodable JSON | 400 | HTTP adapter/framework |
| Resource does not exist | 404 | HTTP handler maps empty/not-found result |
| State violation/conflict with existing data | 409 | HTTP handler based on domain error |
| Content understood but fails business rules | 422 | HTTP handler per API contract |
| Unexpected error | 500 | General error handling |

There is no rule that every domain error must be 422. For example, a nonexistent SKU could be 422 if it is invalid reference data, or 404 if the SKU is treated as a resource to look up. Choose consistent semantics for the API.

## 10. Functional Filters: Handling Cross-Cutting Concerns at the Right Layer

The router builder supports `before`, `after`, and `filter` to apply shared behavior across routes:

- `before`: transforms/observes the request before the handler.
- `after`: observes or transforms the response after the handler.
- `filter`: wraps the next handler using `HandlerFilterFunction`.

Example of logging method/path at the boundary:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/health", request ->
                        ServerResponse.ok().bodyValue("ok"))
                .filter((request, next) -> {
                    log.info("method={} path={}",
                            request.method(), request.path());
                    return next.handle(request);
                })
                .build();
```

This is a snippet that needs a logger and corresponding imports. Filters are suitable for logging, correlation metadata, or a simple shared policy. Do not put pricing rules or order status decisions into a filter.

### Filters do not replace services

A filter can reject unauthorized requests or check cross-cutting conditions. However, authorization that depends on users/resources should integrate with Spring Security and appropriate use-case policies. Do not just check a client-sent `X-User-Id` and trust it as an authenticated identity.

Filters on a functional route builder only apply to routes belonging to that builder; with nested routes, filter scope depends on where the filter is attached. When splitting into multiple router beans, clearly define which filter covers which routes.

## 11. Testing by Boundary: Route, Handler, and Use Case

Separating responsibilities helps test each layer at the right cost.

### 11.1. Testing the service/domain

Service tests do not need an HTTP server, JSON, routes, or `WebTestClient`. You can create an in-memory or fake repository:

```java
StepVerifier.create(
        orderService.create(command))
        .assertNext(order -> {
            assertEquals("customer-1", order.customerId());
            assertEquals(new BigDecimal("26.20"), order.total());
        })
        .verifyComplete();
```

Tests focus on invariants and use-case results: quantities, SKUs, totals, status, and persistence. This is where HTTP-independent business logic is verified.

### 11.2. Testing functional routes with `WebTestClient`

You can start the application on a random port, send real HTTP requests to routes, and verify:

- Do path/method reach the right handler?
- Can JSON be decoded?
- Does the handler return the right status, headers, and response DTO?
- Are domain errors converted into HTTP problem responses per contract?

`WebTestClient` can also bind directly to a `RouterFunction` in an isolated test, but when testing full Spring Boot, using `@SpringBootTest` and random port verifies both route configuration and adapters.

### 11.3. Should handler tests mock the service?

You can mock the application service to check HTTP DTO → command and result → response mapping. However, there is no need to test every handler method with many redundant tests if route integration tests already verify the HTTP contract. Keep tests at the right layer to avoid testing implementation details.

### Recommended test scope

| Layer | What to test | No need to depend on |
|---|---|---|
| Domain/service | Rules, results, use-case errors, reactive composition | HTTP server, URLs, `ServerResponse` |
| Repository adapter | Querying/saving, persistence mapping, database errors | Router and HTTP DTOs |
| Handler | DTO mapping, status/header/body, error translation | Complex domain rules |
| Router | Path/method/predicates, route order, invoked handler | Real database |
| End-to-end | Key HTTP contracts, serialization, and wiring | Should not cover every tiny logic branch |

## 12. Runnable Java 17+ Project: Creating and Looking Up Orders

The following example is a small Spring Boot WebFlux application using functional endpoints. Business rules live in `OrderService`; the router only routes; `OrderHandler` handles HTTP conversion; an in-memory repository stores data so the program can run without a database.

### 12.1. Project structure

```text
webflux-order-boundaries/
├── pom.xml
└── src/
    ├── main/java/edu/demo/orders/
    │   ├── OrderApplication.java
    │   ├── OrderRoutes.java
    │   ├── OrderHandler.java
    │   ├── OrderService.java
    │   ├── OrderRepository.java
    │   ├── InMemoryOrderRepository.java
    │   ├── Order.java
    │   ├── CreateOrderCommand.java
    │   ├── CreateOrderRequest.java
    │   ├── OrderResponse.java
    │   └── InvalidOrderException.java
    └── test/java/edu/demo/orders/
        ├── OrderServiceTest.java
        └── OrderRoutesTest.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-order-boundaries</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
```

### 12.3. `OrderApplication.java`

```java
package edu.demo.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
```

### 12.4. `Order.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.List;

public record Order(
        String id,
        String customerId,
        List<Line> items,
        BigDecimal total) {

    public Order {
        items = List.copyOf(items);
    }

    public record Line(
            String sku,
            int quantity,
            BigDecimal unitPrice) {
    }
}
```

The domain object holds order data and order lines. It knows nothing about JSON requests, HTTP statuses, or `ServerResponse`.

### 12.5. `CreateOrderCommand.java`

```java
package edu.demo.orders;

import java.util.List;

public record CreateOrderCommand(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

The command is the use-case input. It describes what the application needs to create an order, without containing headers, URLs, or HTTP bodies.

### 12.6. `CreateOrderRequest.java`

```java
package edu.demo.orders;

import java.util.List;

public record CreateOrderRequest(
        String customerId,
        List<Item> items) {

    public record Item(String sku, int quantity) {
    }
}
```

The request DTO reflects the JSON API. This contract can be changed without changing the command/domain if the handler keeps the mapping consistent.

### 12.7. `OrderResponse.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.List;

public record OrderResponse(
        String id,
        String customerId,
        List<Item> items,
        BigDecimal total) {

    public record Item(
            String sku,
            int quantity,
            BigDecimal unitPrice) {
    }

    public static OrderResponse from(Order order) {
        List<Item> items = order.items().stream()
                .map(line -> new Item(
                        line.sku(),
                        line.quantity(),
                        line.unitPrice()))
                .toList();

        return new OrderResponse(
                order.id(),
                order.customerId(),
                items,
                order.total());
    }
}
```

The response DTO defines the data exposed through the API. If the domain later gains internal data, it does not automatically appear in the response.

### 12.8. `InvalidOrderException.java`

```java
package edu.demo.orders;

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
```

The exception expresses a business error. It does not contain an HTTP status; the HTTP adapter decides how to represent this error to the client.

### 12.9. `OrderRepository.java`

```java
package edu.demo.orders;

import reactor.core.publisher.Mono;

public interface OrderRepository {

    Mono<Order> save(Order order);

    Mono<Order> findById(String id);
}
```

This is the repository port used by the application service. In the example, the reactive API lets the service compose without blocking.

### 12.10. `InMemoryOrderRepository.java`

```java
package edu.demo.orders;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Repository;
import reactor.core.publisher.Mono;

@Repository
public class InMemoryOrderRepository implements OrderRepository {

    private final Map<String, Order> orders =
            new ConcurrentHashMap<>();

    @Override
    public Mono<Order> save(Order order) {
        return Mono.fromSupplier(() -> {
            orders.put(order.id(), order);
            return order;
        });
    }

    @Override
    public Mono<Order> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(orders.get(id)));
    }
}
```

This adapter only uses one process's memory for illustration. When the application restarts, data is lost; production needs an appropriate database adapter.

### 12.11. `OrderService.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private static final Map<String, BigDecimal> CATALOG = Map.of(
            "BOOK", new BigDecimal("12.50"),
            "PEN", new BigDecimal("1.20")
    );

    private final OrderRepository repository;
    private final AtomicLong ids = new AtomicLong();

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public Mono<Order> create(CreateOrderCommand command) {
        return Mono.defer(() -> {
            if (command == null
                    || command.customerId() == null
                    || command.customerId().isBlank()) {
                return Mono.error(
                        new InvalidOrderException("Customer is required"));
            }

            if (command.items() == null || command.items().isEmpty()) {
                return Mono.error(
                        new InvalidOrderException("At least one item is required"));
            }

            List<Order.Line> lines = new ArrayList<>();
            BigDecimal total = BigDecimal.ZERO;

            for (CreateOrderCommand.Item item : command.items()) {
                if (item == null
                        || item.sku() == null
                        || item.sku().isBlank()) {
                    return Mono.error(
                            new InvalidOrderException("SKU is required"));
                }

                if (item.quantity() < 1 || item.quantity() > 100) {
                    return Mono.error(
                            new InvalidOrderException(
                                    "Quantity must be between 1 and 100"));
                }

                String sku = item.sku()
                        .trim()
                        .toUpperCase(Locale.ROOT);

                BigDecimal price = CATALOG.get(sku);
                if (price == null) {
                    return Mono.error(
                            new InvalidOrderException("Unknown SKU: " + sku));
                }

                lines.add(new Order.Line(sku, item.quantity(), price));
                total = total.add(
                        price.multiply(BigDecimal.valueOf(item.quantity())));
            }

            Order order = new Order(
                    Long.toString(ids.incrementAndGet()),
                    command.customerId().trim(),
                    lines,
                    total);

            return repository.save(order);
        });
    }

    public Mono<Order> findById(String id) {
        return repository.findById(id);
    }
}
```

All customer, quantity, SKU, and total calculation rules reside in the service. There are no `ServerRequest`, `ServerResponse`, `HttpStatus`, or JSON mappings in this class.

`Mono.defer` ensures validation and order creation occur upon subscription. When a rule fails, the service emits a reactive error; the handler maps it into an HTTP response.

### 12.12. `OrderHandler.java`

```java
package edu.demo.orders;

import java.net.URI;
import java.util.ArrayList;
import java.util.List;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;

import reactor.core.publisher.Mono;

@Component
public class OrderHandler {

    private final OrderService orderService;

    public OrderHandler(OrderService orderService) {
        this.orderService = orderService;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .switchIfEmpty(Mono.error(
                        new ServerWebInputException("Request body is required")))
                .map(this::toCommand)
                .flatMap(orderService::create)
                .flatMap(order -> {
                    URI location = request.uriBuilder()
                            .path("/{id}")
                            .build(order.id());

                    return ServerResponse.created(location)
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(OrderResponse.from(order));
                })
                .onErrorResume(
                        InvalidOrderException.class,
                        error -> problem(
                                HttpStatus.UNPROCESSABLE_ENTITY,
                                "Invalid order",
                                error.getMessage()))
                .onErrorResume(
                        ServerWebInputException.class,
                        error -> problem(
                                HttpStatus.BAD_REQUEST,
                                "Invalid request",
                                "Request body could not be read."));
    }

    public Mono<ServerResponse> get(ServerRequest request) {
        String id = request.pathVariable("id");

        return orderService.findById(id)
                .flatMap(order -> ServerResponse.ok()
                        .contentType(MediaType.APPLICATION_JSON)
                        .bodyValue(OrderResponse.from(order)))
                .switchIfEmpty(ServerResponse.notFound().build());
    }

    private CreateOrderCommand toCommand(CreateOrderRequest request) {
        List<CreateOrderCommand.Item> items = null;

        if (request.items() != null) {
            items = new ArrayList<>();

            for (CreateOrderRequest.Item item : request.items()) {
                items.add(item == null
                        ? null
                        : new CreateOrderCommand.Item(
                                item.sku(), item.quantity()));
            }
        }

        return new CreateOrderCommand(request.customerId(), items);
    }

    private Mono<ServerResponse> problem(
            HttpStatus status,
            String title,
            String detail) {

        ProblemDetail body =
                ProblemDetail.forStatusAndDetail(status, detail);
        body.setTitle(title);

        return ServerResponse.status(status)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .bodyValue(body);
    }
}
```

The handler converts the HTTP request DTO into a command, invokes the service, and maps the domain result into a response. Domain exceptions are turned into `422`; body-reading errors are turned into `400`. This is the example's policy; an application can choose other statuses per the API contract.

`get` returns 404 when the repository does not have the order. The service simply returns `Mono.empty()`; it does not need to know the concept of HTTP 404.

### 12.13. `OrderRoutes.java`

```java
package edu.demo.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRoutes(OrderHandler handler) {
        return RouterFunctions.route()
                .POST(
                        "/api/orders",
                        RequestPredicates.accept(MediaType.APPLICATION_JSON),
                        handler::create)
                .GET(
                        "/api/orders/{id}",
                        RequestPredicates.accept(MediaType.APPLICATION_JSON),
                        handler::get)
                .build();
    }
}
```

The router only connects HTTP method/path/Accept predicate to the handler. There is no order creation, pricing, or persistence query logic.

### 12.14. `OrderServiceTest.java`

```java
package edu.demo.orders;

import java.math.BigDecimal;
import java.util.List;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderServiceTest {

    private final OrderService service =
            new OrderService(new InMemoryOrderRepository());

    @Test
    void createsOrderAndCalculatesTotal() {
        CreateOrderCommand command = new CreateOrderCommand(
                "customer-1",
                List.of(
                        new CreateOrderCommand.Item("BOOK", 2),
                        new CreateOrderCommand.Item("PEN", 1)));

        StepVerifier.create(service.create(command))
                .assertNext(order -> {
                    assertEquals("customer-1", order.customerId());
                    assertEquals(
                            new BigDecimal("26.20"),
                            order.total());
                    assertEquals(2, order.items().size());
                })
                .verifyComplete();
    }

    @Test
    void rejectsInvalidQuantity() {
        CreateOrderCommand command = new CreateOrderCommand(
                "customer-1",
                List.of(new CreateOrderCommand.Item("BOOK", 0)));

        StepVerifier.create(service.create(command))
                .expectError(InvalidOrderException.class)
                .verify();
    }
}
```

This is an HTTP-independent application service test. It checks business rules and totals without starting the WebFlux server or creating a `ServerRequest`.

### 12.15. `OrderRoutesTest.java`

```java
package edu.demo.orders;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderRoutesTest {

    @Autowired
    WebTestClient client;

    @Test
    void createsAndThenFindsOrder() {
        CreateOrderRequest request = new CreateOrderRequest(
                "customer-1",
                List.of(new CreateOrderRequest.Item("BOOK", 2)));

        OrderResponse created = client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody(OrderResponse.class)
                .returnResult()
                .getResponseBody();

        assertNotNull(created);

        client.get()
                .uri("/api/orders/{id}", created.id())
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.customerId").isEqualTo("customer-1")
                .jsonPath("$.total").isEqualTo(25.00);
    }

    @Test
    void invalidBusinessRuleBecomes422() {
        CreateOrderRequest request = new CreateOrderRequest(
                "customer-1",
                List.of(new CreateOrderRequest.Item("BOOK", 0)));

        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(request)
                .exchange()
                .expectStatus().isEqualTo(422)
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title").isEqualTo("Invalid order");
    }

    @Test
    void malformedJsonBecomes400() {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue("{")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void missingOrderBecomes404() {
        client.get()
                .uri("/api/orders/does-not-exist")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound();
    }
}
```

Integration tests check routes, HTTP decoding, response status, headers, and bodies. Service tests independently verify business logic. This separation ensures that when a service test fails, we know the bug is in the use case; when a route test fails, we investigate HTTP mapping or adapters.

### 12.16. Running the application and tests

From the project directory:

```bash
mvn test
```

Start the server:

```bash
mvn spring-boot:run
```

Create an order:

```bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"customerId":"customer-1","items":[{"sku":"BOOK","quantity":2},{"sku":"PEN","quantity":1}]}'
```

A successful response has status `201 Created`, a `Location` header, and JSON similar to:

```json
{
  "id": "1",
  "customerId": "customer-1",
  "items": [
    {"sku":"BOOK","quantity":2,"unitPrice":12.50},
    {"sku":"PEN","quantity":1,"unitPrice":1.20}
  ],
  "total": 26.20
}
```

The ID is an incrementing number per in-memory instance; it may differ if the application has already created orders earlier.

Look up an order:

```bash
curl -i \
  -H "Accept: application/json" \
  "http://localhost:8080/api/orders/1"
```

When the corresponding order does not exist, the endpoint returns `404 Not Found`.

Sending a quantity of 0 passes routing and decodes successfully, but the service rejects it per business rules; the handler maps it to `422 Unprocessable Content` with `application/problem+json`.

The example program demonstrates the complete structure and run commands. The Maven commands here are instructions for the learner to execute; there is no claim that the test suite was run in the documentation authoring environment.

## 13. Why Is This Separation Easier to Change?

### Changing paths without changing business logic

If the API moves from `/api/orders` to `/v2/orders`, you only need to change the router or add a new route pointing to the handler. `OrderService.create` and pricing rules do not change.

### Adding another adapter

Suppose a message consumer receives order-creation events. The consumer can convert the message into a `CreateOrderCommand` and call `OrderService.create`. No need to create a `ServerRequest`, no need to fake HTTP statuses.

### Changing the JSON contract

If the API changes `customerId` from a string to an object containing `id`, only the handler mapping `CreateOrderRequest` to `CreateOrderCommand` needs updating. The domain/service continues to receive a stable command.

### Changing the database

Replace `InMemoryOrderRepository` with an R2DBC adapter implementing `OrderRepository`. The service does not need to know SQL, row mapping, or connection pools.

### Faster business tests

Service tests do not have to start a server or construct JSON requests. Tests simply pass a command and assert the result. This makes tests less coupled to the framework and focused on business behavior.

## 14. Signs That Boundaries Are Being Broken

| Sign | Problem | How to fix |
|---|---|---|
| Router calls a repository or calculates prices | Routing is containing use-case logic | Move calls through the handler and service |
| Handler has hundreds of lines of business rules | HTTP adapter is swallowing the domain | Extract use cases/domain services |
| Service returns `ServerResponse` or `ProblemDetail` | Application layer depends on HTTP | Return domain results/exceptions |
| Domain object contains `ServerRequest` or headers | Domain knows about transport | Convert needed data into commands/value objects |
| Service chooses HTTP 404/422 itself | Business errors are coupled to statuses | Emit results/exceptions; adapter maps them |
| Handler calls `subscribe()` itself | Detaches pipeline from the request lifecycle | Compose and return `Mono<ServerResponse>` |
| Handler calls `.block()` | Blocks the WebFlux thread | Use reactive repositories/clients and compose publishers |
| HTTP DTOs are used as domain models everywhere | API contract and domain change together | Create commands/results/domain models where boundaries are needed |
| Every route duplicates validation logic | Rules have no clear owner | Put invariants in the service/domain; input shape in the adapter |
| Service knows URLs, query strings, or JSON field names | Use case depends on transport contract | Convert the request into a command before calling the service |
| Repository returns `ServerResponse` | Persistence depends on HTTP | Repository returns entities/domain results or publishers |
| Every error becomes 400 | Hides domain/server errors | Separate input, domain conflict, and unexpected errors |

Not every short controller/handler needs extra abstractions. If an endpoint only returns a static health status, there is no need to create fake services and repositories. Split layers to protect valuable logic, not to increase file counts.

## 15. Functional Endpoint Design Checklist

Before putting a route into production, check:

- The router only contains paths, methods, predicates, and handler links.
- Specific routes are declared before general routes.
- The handler reads `ServerRequest`, decodes, and maps DTOs to commands.
- The handler returns `Mono<ServerResponse>` and does not subscribe/block manually.
- The service does not depend on `ServerRequest`, `ServerResponse`, `HttpStatus`, or URLs.
- Business invariants are checked in the service/domain, not only in one route.
- The repository port does not depend on HTTP; a persistence adapter implements the port.
- Response DTOs only expose necessary fields.
- Domain/application errors are mapped at the HTTP boundary.
- Unexpected errors are not unconditionally turned into 400.
- Request body decode failures are distinguished from business validation.
- Cross-cutting logging/security live in the appropriate filter/security layer.
- Service tests do not require an HTTP server; route tests verify the HTTP contract.
- There are tests for success, invalid input, domain error, and resource not found.
- Reactive chains are composed; cancellation and errors can propagate through the pipeline.

## 16. Self-Check Exercises

**Exercise 1.** A router receives `POST /orders`, checks whether the customer has enough credit limit, and then selects a handler. Where should the credit-limit check be placed?

**Answer:** In the application service/domain policy invoked by the use case. The router only selects a handler based on the HTTP request.

**Exercise 2.** A handler receives `ServerRequest`, decodes JSON into `CreateOrderRequest`, and then converts it into `CreateOrderCommand`. Is this business logic?

**Answer:** No. This is conversion at the HTTP boundary. Business rules such as quantity, pricing, and ordering permissions belong to the service/domain.

**Exercise 3.** `OrderService.create` returns `Mono<ServerResponse>`. Why is this a wrong boundary?

**Answer:** The service depends on HTTP representation. It should return `Mono<Order>` or a use-case result; the handler decides status, headers, and response body.

**Exercise 4.** The same order creation use case is invoked from HTTP and a message consumer. Where should the total-calculation logic live?

**Answer:** In the service/domain. Each adapter converts its own input into a command and invokes the same use case.

**Exercise 5.** An order does not exist. What does the repository return and what does the HTTP handler decide?

**Answer:** The repository/service can return `Mono.empty()`. The HTTP handler turns empty into `404 Not Found`; a message consumer might handle that result under a different contract.

**Exercise 6.** When changing the path `/api/orders` to `/v2/orders`, do you need to modify `OrderService`?

**Answer:** No, if the command and business logic have not changed. Update the router or HTTP adapter.

**Exercise 7.** Why should you not call `.subscribe()` in a handler?

**Answer:** It creates a subscription detached from the response pipeline. WebFlux no longer has full control over errors, cancellation, and completion timing of that work.

**Exercise 8.** Should an `InvalidOrderException` contain `HttpStatus.UNPROCESSABLE_ENTITY`?

**Answer:** Not necessary. The exception should describe the business error; the HTTP adapter decides the status according to the API contract. The same error can be represented differently in a message consumer or batch adapter.

## 17. Key Takeaways

- **Router** selects the handler based on path, HTTP method, and request predicates.
- **Handler** is the HTTP adapter: reads the request, decodes, maps DTO/command, calls the service, and creates the response.
- **Application service/domain** executes use cases and business rules; does not depend on HTTP.
- **Repository port/adapter** separates storage needs from persistence technology.
- `Mono`/`Flux` can flow through the application service because this is reactive composition; it does not mean the service has to know HTTP.
- Domain exceptions/results are translated into HTTP statuses at the boundary.
- Test services with `StepVerifier`; test routes/HTTP with `WebTestClient`.
- Do not split layers mechanically: keep code small when there is no logic to protect or reuse.

When reading an endpoint, ask: **is this snippet routing, converting HTTP, or making a business decision?** If a single method answers all three questions, that is a signal to separate responsibilities.

## Official Documentation

- Spring Framework, **Functional Endpoints (WebFlux.fn)**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework 6.2, **Functional Endpoints**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html
- Spring Framework, **WebFlux `ServerRequest` and `ServerResponse`**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework, **WebFlux Handler Filters**: https://docs.spring.io/spring-framework/reference/web/webflux-functional.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Project Reactor, **Testing with StepVerifier**: https://projectreactor.io/docs/core/3.6.6/reference/testing.html