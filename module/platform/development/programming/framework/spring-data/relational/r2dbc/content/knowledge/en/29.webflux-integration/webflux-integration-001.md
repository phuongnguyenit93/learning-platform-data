# HTTP Request Flow from Controller through Service to Repository

In a Spring WebFlux application using Spring Data R2DBC, an HTTP request typically passes through three main layers: **Controller**, **Service**, and **Repository**. The Controller receives the HTTP request and converts the input data into parameters or a command; the Service executes business rules and coordinates operations; the Repository accesses the database following the reactive model. The result travels back through the Service and Controller so WebFlux can convert it into an HTTP response.

The key point of this flow is keeping the reactive publisher intact end-to-end. The Controller and Service return `Mono` or `Flux`; the Repository also returns publishers. The layers do not call `subscribe()` or `block()` themselves to wait for results. WebFlux manages the subscription at the request-handling boundary, while Reactor coordinates data, errors, cancellation, and backpressure within the pipeline.

## 1. Overview of the Controller → Service → Repository Architecture

A request to read product details can go through the following steps:

1. The client sends an HTTP request to an endpoint.
2. WebFlux routes the request to the Controller.
3. The Controller reads path variables, query parameters, headers, or the request body.
4. The Controller calls the Service with the received data.
5. The Service applies business rules and calls the Repository.
6. The Repository issues an R2DBC query to the database.
7. The result is mapped into entities and emitted through `Mono` or `Flux`.
8. The Service converts entities into DTOs or combines business results.
9. The Controller returns the publisher; WebFlux writes the HTTP response as the publisher emits data or completes.

~~~mermaid
sequenceDiagram
    participant Client
    participant WebFlux as WebFlux Dispatcher
    participant C as Controller
    participant S as Service
    participant R as R2DBC Repository
    participant DB as Database
    Client->>WebFlux: HTTP request
    WebFlux->>C: Route and invoke handler
    C->>S: Call service with request data
    S->>R: Repository method
    R->>DB: R2DBC query
    DB-->>R: Rows / update result
    R-->>S: Mono or Flux
    S-->>C: Reactive result
    C-->>WebFlux: Return Mono / Flux / ResponseEntity
    WebFlux-->>Client: HTTP response
~~~

The diagram illustrates the logical order. Because publishers are lazy, calling a repository method usually only creates a publisher; the SQL statement is executed when WebFlux subscribes to the pipeline at the request-handling boundary.

## 2. Responsibilities of Each Layer

| Layer | Primary Responsibility | Should Not Do |
| --- | --- | --- |
| Controller | HTTP mapping, reading input, input validation, choosing status/headers, and returning response | Contain complex business rules or write SQL |
| Service | Orchestrating use cases, checking business rules, coordinating repositories, transactions, and transforming results | Know HTTP details like paths/headers unless necessary |
| Repository | Querying and saving entities using Spring Data R2DBC | Orchestrate multi-step workflows or build HTTP responses |
| Database | Storing data, enforcing constraints, transactions, and queries | Replace business validation in the application layer |

Separating responsibilities allows changing the HTTP API without rewriting business logic; changing database queries without making the Controller depend on SQL; and testing each layer with a clear scope.

## 3. Entity and Repository

Example `Product` entity:

~~~java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        String name,
        BigDecimal price,
        String status
) {}
~~~

Reactive repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Flux<Product> findByStatus(String status);

    Mono<Product> findByName(String name);
}
~~~

`ReactiveCrudRepository` provides CRUD operations that return publishers:

- `Mono<T>` is typically used for a single entity or single result.
- `Flux<T>` is used for multiple entities.
- `Mono<Void>` is typically used for operations where you only need to know completion or error.

A repository does not spin up a separate thread to return results. It creates a publisher so the R2DBC driver executes asynchronous I/O upon subscription.

## 4. Service Orchestrating Use Cases

The Service calls the repository and keeps business rules in one place:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Mono<Product> findById(Long id) {
        return productRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)
                ));
    }

    public Flux<Product> findActiveProducts() {
        return productRepository.findByStatus("ACTIVE");
    }
}
~~~

The Service translates the not-found case into a clearly named business error. The Controller or an exception handler decides how that error becomes an HTTP 404.

There is no need to create a new `Mono` just to wrap a repository publisher:

~~~java
// Unnecessary if merely forwarding the result.
public Mono<Product> findById(Long id) {
    return Mono.from(productRepository.findById(id));
}
~~~

You can return the publisher directly when no additional processing is needed. Use `map`, `flatMap`, `filter`, `switchIfEmpty`, or other operators when expressing logic.

## 5. Controller Receiving Requests and Returning Reactive Responses

The Controller uses WebFlux annotations:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Product>> findById(
            @PathVariable Long id) {

        return productService.findById(id)
                .map(ResponseEntity::ok);
    }

    @GetMapping
    public Flux<Product> findActiveProducts() {
        return productService.findActiveProducts();
    }
}
~~~

At the detail endpoint, the result is `Mono<ResponseEntity<Product>>`. If the Service emits a `ProductNotFoundException` error, the pipeline terminates with an error and an exception handler can map it to 404.

The list endpoint returns `Flux<Product>`. WebFlux can write the elements in a manner suitable for the media type and message writer configuration. If returning standard JSON, the framework may encode the collection according to the response format; if using a streaming media type such as NDJSON, each element can be emitted as it becomes ready.

## 6. Request Body Flow with Mono and Validation

With POST, the Controller receives a body and can use Bean Validation:

~~~java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public record CreateProductRequest(
        @NotBlank String name,
        @Positive BigDecimal price
) {}
~~~

The input DTO is separated from the database entity. Clients should not be allowed to directly send internal fields such as auto-generated IDs, system statuses, or audit information unless allowed by business rules.

Controller:

~~~java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import reactor.core.publisher.Mono;

@PostMapping
public Mono<ResponseEntity<Product>> create(
        @Valid @RequestBody Mono<CreateProductRequest> requestMono) {

    return requestMono
            .flatMap(productService::create)
            .map(saved -> ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(saved));
}
~~~

WebFlux decodes the request body into a DTO, applies validation according to the supported configuration, and passes the value into the publisher. The Service only receives the command/DTO already accepted by the Controller; it does not need to read the HTTP body itself.

Depending on the handler signature and Spring Framework version, validation can be declared with an object body or `Mono<T>`. Use the exact style supported by WebFlux in your project version and verify validation errors with integration tests.

## 7. Service Creating Records

The Service converts the request DTO into an entity and saves it:

~~~java
public Mono<Product> create(CreateProductRequest request) {
    Product product = new Product(
            null,
            request.name().trim(),
            request.price(),
            "ACTIVE"
    );

    return productRepository.save(product);
}
~~~

The ID is left `null` so the database/Spring Data handles it according to the entity mapping. The `ACTIVE` status is decided by the service based on application rules, rather than trusting a status value sent by the client.

In practice, it is better to return a response DTO instead of exposing the entity if the entity has internal fields or the database structure is not the API contract:

~~~java
public record ProductResponse(
        Long id,
        String name,
        BigDecimal price
) {}
~~~

The Service can convert the saved entity into a response DTO using `map`.

## 8. GET Flow: Controller → Service → Repository

Example of retrieving a single product:

~~~java
// Controller
@GetMapping("/{id}")
public Mono<ProductResponse> getProduct(@PathVariable Long id) {
    return productService.getProduct(id);
}

// Service
public Mono<ProductResponse> getProduct(Long id) {
    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .map(product -> new ProductResponse(
                    product.id(),
                    product.name(),
                    product.price()
            ));
}
~~~

The Repository returns an entity or an empty `Mono`. The Service turns the empty case into a business error and maps the entity to a DTO. The Controller only declares the route and returns the publisher.

If you want to return 404 using `ResponseEntity` directly in the Controller instead of throwing an exception:

~~~java
@GetMapping("/{id}")
public Mono<ResponseEntity<ProductResponse>> getProduct(
        @PathVariable Long id) {

    return productService.findResponseById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
}
~~~

Choose one consistent convention for the application. Exception mapping fits well when not-found is a business error used across many endpoints; `defaultIfEmpty` fits when the Controller wants to express the HTTP response directly for a nonexistent result.

## 9. POST Flow and HTTP 201 Created

When creating a resource succeeds, APIs typically return HTTP 201 and may include a `Location` header:

~~~java
@PostMapping
public Mono<ResponseEntity<ProductResponse>> create(
        @Valid @RequestBody Mono<CreateProductRequest> body) {

    return body.flatMap(productService::createResponse)
            .map(saved -> ResponseEntity
                    .created(URI.create("/api/products/" + saved.id()))
                    .body(saved));
}
~~~

Service:

~~~java
public Mono<ProductResponse> createResponse(
        CreateProductRequest request) {

    Product product = new Product(
            null,
            request.name().trim(),
            request.price(),
            "ACTIVE"
    );

    return productRepository.save(product)
            .map(saved -> new ProductResponse(
                    saved.id(),
                    saved.name(),
                    saved.price()
            ));
}
~~~

The `Location` should be constructed from a valid resource URI according to the API structure. For applications with a base path, reverse proxy, or dynamic host, you can use a URI builder from the request context instead of concatenating a fixed string.

## 10. PUT/PATCH Flow: Read, Validate, and Update

An update use case may need to load the entity, confirm existence, and apply the allowed fields:

~~~java
public record UpdateProductRequest(
        @NotBlank String name,
        @Positive BigDecimal price
) {}
~~~

Service:

~~~java
public Mono<ProductResponse> update(
        Long id,
        UpdateProductRequest request) {

    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .map(current -> new Product(
                    current.id(),
                    request.name().trim(),
                    request.price(),
                    current.status()
            ))
            .flatMap(productRepository::save)
            .map(saved -> new ProductResponse(
                    saved.id(),
                    saved.name(),
                    saved.price()
            ));
}
~~~

Controller:

~~~java
@PutMapping("/{id}")
public Mono<ProductResponse> update(
        @PathVariable Long id,
        @Valid @RequestBody Mono<UpdateProductRequest> body) {

    return body.flatMap(request ->
            productService.update(id, request)
    );
}
~~~

This is a read-modify-write pattern. If multiple requests can update concurrently, consider optimistic locking with `@Version`, pessimistic locking in a transaction, or a conditional `UPDATE` statement. Do not assume that calling `findById` then `save` automatically prevents lost updates.

## 11. DELETE Flow and Mono<Void>

The Repository can delete by ID:

~~~java
public Mono<Void> deleteById(Long id) {
    return productRepository.deleteById(id);
}
~~~

The Service can check existence first if it needs to return a 404 error:

~~~java
public Mono<Void> delete(Long id) {
    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .flatMap(product ->
                    productRepository.deleteById(product.id())
            );
}
~~~

Controller:

~~~java
@DeleteMapping("/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable Long id) {
    return productService.delete(id)
            .thenReturn(ResponseEntity.noContent().build());
}
~~~

`Mono<Void>` represents completion or error, emitting no entity. `thenReturn` creates a 204 response after the delete operation completes. If there is no need to distinguish a nonexistent ID from an already deleted one, you can call `deleteById` directly according to the repository's semantics.

Checking existence before deleting can encounter a race condition if the record is deleted between the two operations. If an exact distinction is required, you can use a `DELETE` statement returning the affected row count via `DatabaseClient` or a template and interpret the count.

## 12. map and flatMap in the Controller/Service Flow

Two operators frequently appear in multi-layer flows:

- `map`: synchronously transforms a value into another value.
- `flatMap`: takes a value, calls a function returning a publisher, and flattens the nested publisher.

Example of `map`:

~~~java
Mono<ProductResponse> response = productRepository.findById(id)
        .map(product -> new ProductResponse(
                product.id(),
                product.name(),
                product.price()
        ));
~~~

Example of `flatMap`:

~~~java
Mono<OrderResponse> response = orderRepository.findById(id)
        .flatMap(order ->
                customerRepository.findById(order.customerId())
                        .map(customer -> toResponse(order, customer))
        );
~~~

If you use `map` for a function returning a publisher, the result becomes `Mono<Mono<T>>`. `flatMap` flattens it so the caller receives `Mono<T>`.

Do not use `flatMap` for every transformation. When merely constructing a DTO from an entity, `map` is clearer and more appropriate.

## 13. Combining Multiple Repositories

A Service may need data from multiple repositories. If the queries are independent, you can use `Mono.zip`:

~~~java
public Mono<DashboardResponse> dashboard() {
    Mono<Long> productCount = productRepository.count();
    Mono<Long> orderCount = orderRepository.count();

    return Mono.zip(productCount, orderCount)
            .map(tuple -> new DashboardResponse(
                    tuple.getT1(),
                    tuple.getT2()
            ));
}
~~~

`zip` waits for the publishers to emit values and then combines them. If one publisher completes empty, `zip` may complete without creating a tuple; if one publisher emits an error, the error propagates downstream and related subscriptions may be cancelled.

If the second operation depends on the result of the first, use `flatMap`:

~~~java
public Mono<OrderResponse> findOrder(Long id) {
    return orderRepository.findById(id)
            .flatMap(order ->
                    customerRepository.findById(order.customerId())
                            .map(customer -> toResponse(order, customer))
            );
}
~~~

For a list of many Orders, the pattern of calling `customerRepository` for each Order can cause N+1 queries. In that case, use a JOIN or load Customers by a set of IDs.

## 14. Validation in the Controller and Business Rules in the Service

Input validation typically has two tiers:

**Request validation** checks structure and simple values:

- Required fields.
- String length.
- Email format.
- Positive values or values within a range.
- Data types and request format.

**Business validation** checks business context:

- Does the customer exist and remain active?
- Is the product allowed to be sold?
- Is there sufficient stock remaining?
- Does the user have permission to perform the operation?
- Does the current state allow transitioning to the new state?

The Controller can trigger Bean Validation on request DTOs. The Service verifies business rules using repositories or domain logic. Database constraints continue to protect integrity under concurrent requests.

Do not rely solely on existence checks in the Service to guarantee uniqueness. For example, two requests might both check that an email does not exist yet and both insert; a unique constraint in the database is the final line of defense.

## 15. Centralized Error Handling with RestControllerAdvice

The Service should emit meaningful business errors:

~~~java
public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(Long id) {
        super("Product not found: " + id);
    }
}
~~~

An exception handler translates errors into HTTP responses:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    public Mono<ApiError> handleNotFound(
            ProductNotFoundException error) {
        return Mono.just(new ApiError(
                "PRODUCT_NOT_FOUND",
                error.getMessage()
        ));
    }

    @ExceptionHandler(ServerWebInputException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public Mono<ApiError> handleBadInput(
            ServerWebInputException error) {
        return Mono.just(new ApiError(
                "INVALID_REQUEST",
                "Request body or parameter is invalid"
        ));
    }
}
~~~

Error DTO:

~~~java
public record ApiError(String code, String message) {}
~~~

In real-world applications, never return stack traces, SQL, table names, or connection details to the client. Log error details internally with a correlation ID; the response should only contain information appropriate for the API.

Besides exceptions emitted by the Service, WebFlux also has body decoding, binding, validation, and framework errors. Define handlers matching the error types of the Spring version in use.

## 16. Placing Transactions in the Service

A use case involving multiple database operations that must commit/rollback together should place its transaction in the Service layer:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(
                            toOrderLines(order.id(), command.items())
                    ).thenReturn(order)
            )
            .flatMap(order ->
                    auditRepository.save(toAudit(order))
                            .thenReturn(order)
            );
}
~~~

The R2DBC transaction manager must be properly configured and the repositories must use the same connection factory. Spring manages reactive transactions via the Reactor Context. The publisher must be returned so the framework can coordinate commit/rollback.

Do not call `subscribe()` inside a `@Transactional` method. Calling `subscribe()` manually can detach the operation from the transaction context, and the caller can no longer track errors or results.

If using `TransactionalOperator`, you can wrap the pipeline explicitly:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    Mono<Order> work = orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderLineRepository.saveAll(
                            toOrderLines(order.id(), command.items())
                    ).thenReturn(order)
            );

    return transactionalOperator.transactional(work);
}
~~~

Choose the annotation or operator as needed. Do not wrap the same publisher with both approaches without a clear intent regarding propagation and transaction boundaries.

## 17. Never Block or Subscribe in Controller/Service

A common mistake is turning reactive code into imperative code:

~~~java
// Do not use in a WebFlux service.
public Product getProduct(Long id) {
    return productRepository.findById(id).block();
}
~~~

Or:

~~~java
// Do not subscribe manually in a Controller.
public void create(CreateProductRequest request) {
    productRepository.save(toProduct(request)).subscribe();
}
~~~

These approaches have problems:

- `block()` blocks the thread waiting for the database, reducing concurrency capacity.
- `subscribe()` creates an independent subscription; the Controller no longer manages the result.
- Errors may occur after the HTTP response has already been sent.
- Transactions, cancellation, and tracing may become detached from the request flow.
- The client does not receive a response reflecting the actual database result.

Return the publisher instead:

~~~java
public Mono<Product> create(CreateProductRequest request) {
    return productRepository.save(toProduct(request));
}
~~~

WebFlux subscribes at the framework boundary and coordinates the response with the publisher.

## 18. Flux and How WebFlux Writes Responses

`Mono<T>` represents at most one element; `Flux<T>` represents zero, one, or many elements. For list endpoints, the Controller can return `Flux`:

~~~java
@GetMapping(value = "/stream", produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<ProductResponse> streamProducts() {
    return productService.streamProducts();
}
~~~

NDJSON allows writing each JSON object on its own line as the publisher emits data. Clients can process each element without waiting for the entire list.

When returning standard `application/json`, the message writer may encode `Flux` into a JSON array; the response may need to buffer or handle the collection structure according to the codec's behavior. Choose the media type based on the API contract and client capabilities.

Streaming is beneficial for large datasets, but it also means the HTTP connection may stay open for a long time. Results must be limited, paginated, or given an appropriate timeout. Do not keep a database transaction open just to hold the transaction for the entire duration the client receives the stream unless strictly necessary.

## 19. Backpressure from HTTP to Database

Reactive Streams allows a subscriber to request elements according to demand. WebFlux and Reactor can coordinate backpressure in the pipeline; however, the entire HTTP stack, codec, and R2DBC driver must support this mechanism appropriately.

Example:

~~~java
public Flux<ProductResponse> streamProducts() {
    return productRepository.findAll()
            .map(this::toResponse)
            .limitRate(64);
}
~~~

`limitRate(64)` throttles upstream requests in batches. It does not replace SQL `LIMIT` or pagination if the API should only return a bounded dataset. When data is large, push limits down to the database using Query/SQL to avoid reading too many rows.

If the client disconnects, WebFlux can cancel the subscription; cancellation propagates through the pipeline, giving the R2DBC infrastructure a chance to stop reading/release the connection. Whether the SQL statement stops immediately on the server depends on the driver/database.

## 20. Per-Request Timeout and Cancellation

A timeout can be set on a use case:

~~~java
public Mono<ProductResponse> findProduct(Long id) {
    return productRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
            ))
            .map(this::toResponse)
            .timeout(Duration.ofSeconds(3));
}
~~~

A Reactor timeout limits how long to wait for the publisher; upon expiration, upstream is cancelled and downstream receives a timeout error. This is not necessarily a database-side statement timeout. If you need to limit SQL execution time on the server, configure the corresponding timeout on the driver/database.

When the client closes the connection, cancellation can occur without emitting a normal business error. Do not catch cancellation and blindly retry, because the client may no longer need the result.

## 21. Distinguishing HTTP Errors, Business Errors, and Database Errors

Do not turn every exception into the same HTTP 500:

| Error Group | Examples | Common HTTP Mapping |
| --- | --- | --- |
| Request invalid | Malformed JSON, missing required field | 400 Bad Request |
| Resource not found | Product ID does not exist | 404 Not Found |
| Business conflict | Email already exists, invalid state | 409 Conflict |
| Forbidden | User lacks permission | 403 Forbidden |
| Database unavailable | Connection refused, pool exhausted | 503 Service Unavailable or 500 per policy |
| Unexpected error | Null bug, mapping bug | 500 Internal Server Error |

Mapping must be based on the API contract. Do not return 404 for every repository error; a connection error does not mean the resource does not exist. Also never return raw SQL exception messages to the client.

## 22. Avoiding N+1 in the Service

Example:

~~~java
public Flux<OrderResponse> findOrders() {
    return orderRepository.findAll()
            .flatMap(order ->
                    customerRepository.findById(order.customerId())
                            .map(customer -> toResponse(order, customer))
            );
}
~~~

With 100 Orders, this can trigger 1 query for Orders and 100 queries for Customers. `flatMap` may execute the queries asynchronously, but the total number of round trips remains high.

Better options:

- JOIN using `DatabaseClient` to build a DTO/read model.
- Fetch Orders in pages, collect customer IDs, and query Customers in batches.
- Design a query projection if the response data needs fields from multiple tables.

JOIN example:

~~~sql
SELECT o.id AS order_id,
       o.status,
       c.id AS customer_id,
       c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id;
~~~

Layer separation does not mean calling strictly one repository for every response. A Service can use repositories or `DatabaseClient` depending on the query shape, as long as business logic stays in the right place.

## 23. Passing Data Between Layers with DTOs and Commands

Do not use the same class for requests, database entities, and responses when those structures serve different purposes:

| Type | Data Direction | Example Fields |
| --- | --- | --- |
| Request DTO | Client → Controller | name, price |
| Command | Controller → Service | name, price, actorId, context |
| Entity | Service ↔ Repository | id, name, price, status, version |
| Response DTO | Service → Controller → Client | id, name, price |

Separating data types helps:

- Prevent clients from modifying internal fields.
- Avoid exposing sensitive columns in entities.
- Keep the API stable when the schema changes.
- Tailor validation to each operation.
- Simplify testing and API versioning.

For small applications, a single DTO can be used for command/response if the contract is truly identical. Do not split classes merely to increase file count when there is no difference in responsibility.

## 24. Logging, Tracing, and Correlation IDs

An HTTP request passes through multiple layers. When an error occurs, logs from the Controller, Service, and Repository need to be correlated using a correlation ID or trace ID.

Useful information:

- HTTP method and route template.
- Trace/correlation ID.
- Use case name.
- Service and database processing duration.
- Classified error type.
- Transaction or retry status if applicable.

Do not log passwords, access tokens, sensitive personal data, or entire request bodies by default. When logging SQL, avoid recording sensitive parameters.

Reactor Context can carry correlation/observability information across the pipeline. Do not arbitrarily use `ThreadLocal` to hold request context in a reactive flow because operators may run on different threads.

## 25. Testing Each Layer

Each layer should be tested according to its responsibility:

### Repository integration test

Verify entity mapping, derived queries, constraints, insert/update/delete, and SQL against a real database or Testcontainers.

~~~java
StepVerifier.create(productRepository.findByStatus("ACTIVE"))
        .expectNextMatches(product ->
                product.status().equals("ACTIVE")
        )
        .verifyComplete();
~~~

### Service unit test

Mock repositories to test business rules, empty/error cases, and publisher composition. Do not use mocks to prove that SQL or database transactions work properly.

### Controller/WebFlux test

Use `WebTestClient` to send HTTP requests and verify status, headers, body, validation, and exception mapping:

~~~java
webTestClient.get()
        .uri("/api/products/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);
~~~

Not-found test:

~~~java
webTestClient.get()
        .uri("/api/products/999")
        .exchange()
        .expectStatus().isNotFound();
~~~

### End-to-end test

Verify the entire HTTP → Controller → Service → Repository → database flow to confirm WebFlux configuration, serialization, mapping, transactions, and exception handlers work together properly.

## 26. A Complete Flow Example

Data types:

~~~java
public record CreateProductRequest(
        @NotBlank String name,
        @Positive BigDecimal price
) {}

public record ProductResponse(
        Long id,
        String name,
        BigDecimal price
) {}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {
}
~~~

Service:

~~~java
@Service
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductResponse> create(CreateProductRequest request) {
        Product product = new Product(
                null,
                request.name().trim(),
                request.price(),
                "ACTIVE"
        );

        return repository.save(product)
                .map(saved -> new ProductResponse(
                        saved.id(),
                        saved.name(),
                        saved.price()
                ));
    }

    public Mono<ProductResponse> findById(Long id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new ProductNotFoundException(id)
                ))
                .map(product -> new ProductResponse(
                        product.id(),
                        product.name(),
                        product.price()
                ));
    }
}
~~~

Controller:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<ProductResponse>> create(
            @Valid @RequestBody Mono<CreateProductRequest> request) {

        return request.flatMap(service::create)
                .map(response -> ResponseEntity
                        .created(URI.create(
                                "/api/products/" + response.id()
                        ))
                        .body(response));
    }

    @GetMapping("/{id}")
    public Mono<ProductResponse> findById(@PathVariable Long id) {
        return service.findById(id);
    }
}
~~~

POST flow:

1. WebFlux receives `POST /api/products`.
2. The body is decoded into `CreateProductRequest`.
3. Bean Validation checks `name` and `price`.
4. The Controller passes the request publisher to the Service.
5. The Service creates a `Product` entity and calls `repository.save`.
6. Spring Data R2DBC converts the entity into write data and the driver executes `INSERT`.
7. The database returns the result; the saved entity is emitted.
8. The Service maps the entity into `ProductResponse`.
9. The Controller builds an HTTP 201 with a `Location` header.
10. WebFlux serializes the response and sends it to the client.

No layer calls `subscribe()` itself. The publisher remains intact from repository through service to controller so WebFlux coordinates subscription, errors, and cancellation.

## 27. Common Mistakes in the Request Flow

1. **Controller calling multiple repositories directly.** Business rules and orchestration become scattered outside the Service.
2. **Service returning database entities directly for all endpoints.** The API becomes coupled to persistence structure and may leak internal fields.
3. **Using `block()` in Controller/Service.** Blocks threads and defeats reactive benefits.
4. **Calling `subscribe()` manually inside a service.** The caller loses tracking of results and errors.
5. **Using `map` when a function returns a publisher.** Creates nested publishers; `flatMap` is needed.
6. **Using `flatMap` for pure transformations.** `map` is simpler and clearer.
7. **Checking uniqueness only in Java.** Concurrent requests can still create duplicates; a unique constraint is required.
8. **Reading then saving without concurrency control.** Lost updates can occur.
9. **Returning an unbounded `Flux` for list endpoints.** Can consume too much data and hold HTTP connections open for a long time.
10. **Confusing database errors with not-found.** A connection failure does not mean the entity does not exist.
11. **Calling a repository in a loop causing N+1.** Use JOINs or batch queries.
12. **Placing transactions in the Controller for all cases.** Transactions usually belong to the use case in the Service.
13. **Triggering external side effects before commit.** Emails/messages might be sent even if the transaction rolls back.
14. **Ignoring cancellation.** Client disconnects can cancel the pipeline; do not blindly retry or hold resources indefinitely.
15. **Not testing the HTTP boundary.** Service unit tests do not prove routing, serialization, and status codes work properly.

## Quick Selection Rules

- The Controller receives HTTP input, calls the Service, and returns `Mono`/`Flux`.
- The Service orchestrates use cases, business validation, and transactions.
- The Repository performs reactive CRUD/queries on entities.
- Use request/response DTOs to keep the API decoupled from the schema.
- Use `map` for synchronous transformations and `flatMap` for operations returning a publisher.
- Use `switchIfEmpty` to handle missing data according to business rules.
- Use `@Transactional` or `TransactionalOperator` in the Service when multiple operations must commit/rollback together.
- Never call `block()` or `subscribe()` in Controller/Service.
- Use JOINs or batch queries to avoid N+1.
- Limit or paginate `Flux` when datasets are large.
- Map business errors to HTTP statuses using an exception handler.
- Test repositories, services, and HTTP endpoints at the appropriate layer.

The Controller → Service → Repository flow clearly separates HTTP, business, and persistence boundaries in a Spring WebFlux application with Spring Data R2DBC. The Controller receives requests and returns HTTP responses; the Service coordinates business rules, publishers, and transactions; the Repository accesses the database via R2DBC. By keeping `Mono`/`Flux` end-to-end, using appropriate DTOs, handling errors purposefully, and letting WebFlux manage subscriptions, the application can leverage asynchronous I/O while keeping the codebase readable, testable, and extensible.
