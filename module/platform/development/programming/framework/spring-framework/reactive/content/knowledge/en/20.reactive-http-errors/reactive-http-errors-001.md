# Distinguishing Business, Input, and Infrastructure Errors in Spring WebFlux

## 1. Why Classify Errors Before Handling Them?

An HTTP request can fail for very different reasons. A client sends malformed JSON, a user requests an order that does not exist, a business rule rejects a transaction, or a database/upstream service loses connectivity. All of these can appear as a reactive error signal, yet their **meaning, HTTP status, retry behavior, logging approach, and remediation responsibility** are completely different.

If you lump every exception into a single generic `catch` and return 500, the API will mislead the client. If you turn every error into 400, infrastructure failures will be blamed on the user. If you retry every error, the system can repeat side effects, increase load while a dependency is failing, or delay a response for a request that can never succeed.

In this article, we use three main categories:

1. **Input/client errors:** the request violates the contract, is missing data, has the wrong type or format, or fails validation.
2. **Business/domain errors:** the request is syntactically valid, but the outcome is not permitted by the current state or domain rules.
3. **Infrastructure/dependency errors:** the application cannot complete the work because a database, message broker, external service, network, or runtime resource encounters a failure.

Beyond those three categories, there are also authentication/authorization errors and unexpected programming bugs. They must be classified separately so that not every situation is forced into one of the three categories.

The goal is not merely to pick a status code. The goal is to establish a **stable error contract**: clients know whether to fix the request, display a business message, retry later, or report an unexpected failure; operations teams have enough information to investigate the root cause without exposing sensitive data.

## 2. Error Lifecycle in a Reactor Pipeline

In WebFlux, errors typically flow through a `Mono` or `Flux` as an `onError` signal. A Publisher has only one terminal outcome: completion (`onComplete`) or error (`onError`); after that terminal signal, it stops emitting normal data.

~~~java
Mono<Order> order = repository.findById(id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
~~~

If the repository finds no data, `switchIfEmpty` replaces empty completion with an error signal. The error travels through downstream operators until it is handled or reaches the HTTP boundary.

Common operators:

| Operator | Role | Does it handle the error? |
| --- | --- | --- |
| `doOnError` | Observe/log/record metrics as the error passes through | No; the error continues downstream |
| `onErrorMap` | Transform an exception into another type, preserving cause if needed | Changes the error type, but it remains an error |
| `onErrorResume` | Select a fallback Publisher when a matching error occurs | Can recover or emit a new error |
| `onErrorReturn` | Replace the error with a default value | Can hide failures |
| `retryWhen` | Resubscribe to the source according to a retry policy | Retries; does not guarantee the next attempt succeeds |
| `timeout` | Emit an error if the source does not respond within the deadline | Creates a timeout error |
| `switchIfEmpty` | Handle the case with no elements | Not an error if the source completes empty |

For example, `doOnError` does not turn an error into success:

~~~java
return service.load(id)
    .doOnError(error -> log.error("load failed", error));
~~~

Conversely, `onErrorResume` can replace an error with a fallback response:

~~~java
return cache.find(id)
    .onErrorResume(CacheUnavailableException.class,
        error -> database.find(id));
~~~

This is intentional recovery: the cache failed, while the database remains the authoritative data source. You should not use `onErrorResume(error -> Mono.empty())` broadly because it can turn a real failure into "data not found", causing the API to return the wrong status and mask an outage.

**Reactive errors are not the same as synchronous exceptions.** Exceptions thrown inside `map`, `flatMap`, or callbacks are typically converted by Reactor into `onError`. Therefore, you must design error handling along the pipeline rather than relying on a `try/catch` wrapping Publisher creation.

## 3. Category 1 — Input Errors: The Client Needs to Fix the Request

Input errors occur when a request violates the API contract before or during conversion into application objects.

### 3.1. Common Scenarios

- Malformed JSON or body that cannot be decoded into a DTO.
- Missing required fields, blank strings, negative quantities, or out-of-range values.
- Path variables/query parameters that cannot be converted to the target type.
- `Content-Type` not supported by the endpoint.
- Request body exceeding the size limit.
- Syntactically valid data that fails request-level validation.

You must distinguish **parse/validation** from **business rules**. For example, `quantity = -1` is invalid input if the DTO contract requires a positive quantity. However, if `quantity = 5` is valid while inventory only has 2 items left, that is a business outcome, which can be represented as insufficient stock or a state conflict.

### 3.2. Appropriate HTTP Statuses

| Scenario | Typical Status | Meaning |
| --- | --- | --- |
| Malformed body, invalid DTO | 400 Bad Request | The client must fix the request content |
| Wrong request `Content-Type`/media type | 415 Unsupported Media Type | The server cannot read that body format |
| No response representation matches `Accept` | 406 Not Acceptable | The server cannot return the format requested by the client |
| Payload exceeds limit | 413 Payload Too Large | The client must reduce payload size |
| No matching route for path/method | 404 or 405 | Wrong resource or HTTP method |

Not every error occurring before entering the service shares the same status. For example, valid JSON that fails validation is usually 400; valid JSON that passes validation but is rejected by a domain rule is a business error.

### 3.3. Validation on DTOs

Use Bean Validation to express request constraints:

~~~java
public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) @Max(100) int quantity
) {}
~~~

In the controller:

~~~java
@PostMapping("/orders")
public Mono<OrderView> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Spring WebFlux decodes the body and then performs validation before invoking the controller method. If the data is invalid, the framework emits a binding/validation error, typically `WebExchangeBindException`, to be handled at the HTTP boundary.

With a reactive parameter such as `@RequestBody Mono<CreateOrderRequest>`, validation is applied to the decoded value according to WebFlux's supported mechanism. Regardless of which form you use, do not manually subscribe to the body just to invoke a validator; let the framework and pipeline manage reading.

### 3.4. Validation Does Not Replace Business Checks

For example:

- `sku` must not be blank: input validation.
- `quantity` must be greater than 0: input validation.
- SKU is no longer for sale: domain rule.
- User does not own the order: authorization/domain depending on the contract.
- Out of stock after checking state: business outcome.

Putting every domain rule into Bean Validation tightly couples DTOs to database state or external services. Request-level validation should be fast, deterministic, and check basic shape/bounds. Rules that depend on current state belong in the service/domain flow.

## 4. Category 2 — Business Errors: The Request Is Valid, but Cannot Be Executed

Business errors occur when the system understands the request but cannot or is not allowed to complete the operation given the current state.

### 4.1. Examples

- The order does not exist.
- The product is out of stock.
- Cannot transition state from `CANCELLED` to `SHIPPED`.
- The transaction ID has already been used.
- The account has insufficient balance.
- A duplicate request conflicts with the existing resource.

These errors are not necessarily bugs or infrastructure outages. The system may be operating completely normally while rejecting a syntactically valid operation.

### 4.2. Status Codes Are Part of the Domain Contract

| Scenario | Typical Status | Notes |
| --- | --- | --- |
| Resource does not exist | 404 Not Found | May be a resource lookup error |
| Current state conflicts with the operation | 409 Conflict | For example, the order is already cancelled but the client requests shipping |
| Syntactically valid content that cannot be processed under API rules | 422 Unprocessable Content | Used when the API contract clearly distinguishes it from 400 |
| User is authenticated but lacks permission | 403 Forbidden | Belongs to authorization/security, not a normal input error |

There is no single mapping table that fits every domain. For example, "out of stock" might be treated by an API as 409 due to conflicting inventory state, 422 due to an unmet business condition, or 200 with a rejected order status in an asynchronous workflow. Choose according to your API contract and stay consistent.

### 4.3. Use Clearly Named Domain Exceptions

~~~java
public final class OrderNotFoundException extends RuntimeException {
    public OrderNotFoundException(long id) {
        super("Order not found: " + id);
    }
}

public final class OrderConflictException extends RuntimeException {
    public OrderConflictException(String message) {
        super(message);
    }
}
~~~

The service emits exceptions with domain meaning:

~~~java
public Mono<Order> findRequired(long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(id)));
}
~~~

Do not use `IllegalArgumentException` for all business errors. Overly generic exceptions leave the HTTP layer unable to tell whether to return 400, 404, or 409. Clearly named error types make mapping, testing, and logging easier to understand.

### 4.4. Do Not Let the HTTP Layer Decide Domain Rules

A controller can call the service and return a Publisher:

~~~java
@GetMapping("/orders/{id}")
public Mono<OrderView> get(@PathVariable long id) {
    return orderService.findRequired(id)
        .map(OrderView::from);
}
~~~

The service decides whether the order exists and whether the operation is valid. The HTTP layer only translates domain outcomes into status/body. Avoid scattering conditions like "if order status is CANCELLED then return 409" across multiple controllers.

## 5. Category 3 — Infrastructure Errors: The Application Cannot Complete Due to a Dependency or Environment Issue

Infrastructure errors occur when the application cannot perform the work because a dependent resource or service is unavailable.

### 5.1. Common Error Sources

- Database unreachable, connection pool exhausted, or transaction timeout.
- Redis/cache, message broker, or object storage unresponsive.
- External HTTP service returning 5xx errors, closing connections, or timing out.
- Issues with DNS, TLS, network routes, or dependency credentials.
- Thread pools, queues, or resource limits exhausted.
- Circuit breaker open because a dependency has a high failure rate.

Do not classify every library exception as an infrastructure error immediately. For example, an HTTP 404 from an upstream may mean a domain resource does not exist; it can also indicate a misconfigured URL. You need to understand the dependency's contract before translating it into a public API error.

### 5.2. Common Status Codes

| Scenario | Typical Status | Meaning |
| --- | --- | --- |
| Service temporarily unavailable | 503 Service Unavailable | Client can retry later |
| Gateway/proxy waited too long for upstream | 504 Gateway Timeout | Upstream did not respond in time |
| Unclassified internal error | 500 Internal Server Error | Server could not complete the request |
| Load limit / rate limit | 429 Too Many Requests | Client must slow down or wait per Retry-After |

If the API acts as a gateway calling another service, 504 can describe an upstream timeout. If a simple application times out during internal processing, 503 or 500 may be more appropriate depending on API semantics. Do not map every `TimeoutException` to 504 without considering the service's role.

### 5.3. Create Semantic Infrastructure Exceptions

~~~java
public final class InventoryUnavailableException extends RuntimeException {
    public InventoryUnavailableException(Throwable cause) {
        super("Inventory dependency is unavailable", cause);
    }
}

public final class UpstreamTimeoutException extends RuntimeException {
    public UpstreamTimeoutException(Throwable cause) {
        super("Inventory dependency timed out", cause);
    }
}
~~~

Preserve `cause` for logging and investigation. However, **never return technical messages or the cause to the client**. Clients only need to know that the service is temporarily unavailable or the upstream timed out—not database hostnames, SQL statements, stack traces, or tokens.

### 5.4. Translate Library Exceptions into Application Exceptions at the Dependency Boundary

Example with WebClient:

~~~java
public Mono<Inventory> loadInventory(String sku) {
    return webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .onStatus(HttpStatusCode::is5xxServerError,
            response -> Mono.error(
                new InventoryUnavailableException(
                    new IllegalStateException("upstream 5xx"))))
        .bodyToMono(Inventory.class)
        .onErrorMap(WebClientRequestException.class,
            error -> new InventoryUnavailableException(error));
}
~~~

This is illustrative code for translating transport/5xx errors into application exceptions. In practice, distinguish upstream statuses according to the contract: 404 may become `InventoryNotFoundException`; 429 may require backoff; upstream 401/403 is usually a credential/service configuration error and should not be forwarded verbatim to public API callers.

## 6. Summary Classification Table

| Diagnostic Question | Error Category | Handling Strategy |
| --- | --- | --- |
| Does the request match syntax, types, and bounds? | Input | Return appropriate 400/413/415/406; indicate fields to fix |
| Is the request valid, yet rejected by domain state? | Business | Return 404/409/422 or domain outcome per contract |
| Is the dependency available and responding in time? | Infrastructure | Timeout, bounded retry, circuit breaker, 503/504 |
| Is the error unexpected with no mapping? | Bug/unknown | 500, full server-side logging |
| Does the caller have valid identity and permissions? | Security | 401/403, do not reveal sensitive resources |

A practical way to classify is to look at **who can fix it**:

- Client fixes body/header/path: input error.
- User or business process changes state/makes a different choice: business error.
- Operations team restores database/network/upstream or reduces load: infrastructure error.
- Developer fixes logic: programming bug.

## 7. Building a Stable Error Contract for the API

### 7.1. Never Return Exception Classes or Stack Traces

A good error response should contain:

- `timestamp`: time of the error.
- `status`: HTTP status.
- `code`: stable error code for client handling.
- `message`: safe, human-readable message.
- `path`: called endpoint.
- `traceId`/`requestId`: correlation ID to assist log lookup.

Example response:

~~~json
{
  "timestamp": "2026-11-08T02:00:00Z",
  "status": 503,
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Inventory service is temporarily unavailable.",
  "path": "/api/orders",
  "traceId": "9b8d..."
}
~~~

The timestamp and trace ID above only illustrate the format. Real APIs should keep field names and error codes stable across versions.

### 7.2. Stable Error Codes Matter More Than Messages

Clients should rely on `code` such as `ORDER_NOT_FOUND`, `ORDER_CONFLICT`, `REQUEST_VALIDATION_FAILED`, or `INVENTORY_UNAVAILABLE`, rather than parsing the `message` string. Messages can be localized or reworded; codes are the machine-readable part of the contract.

Do not put Java exception names into the response like `"error": "InventoryUnavailableException"` because it couples the public API to internal implementation details.

### 7.3. Never Expose Internal Information

Do not return to clients:

- Stack traces or internal class/package names.
- SQL, table names, connection strings, internal hostnames, or IPs.
- Access tokens, cookies, passwords, secrets, or sensitive headers.
- Raw messages from dependencies if they may contain user or infrastructure data.
- Data from resources the caller is not authorized to view.

Log details on the server with the trace ID, while the response contains only the information needed for the client to act.

### 7.4. `Retry-After` and Retry Hints

For transient errors like 503 or 429, the server can send `Retry-After` if an appropriate delay is known. You should not encourage clients to retry continuously without delay. For business or validation errors, retrying the exact same unchanged request is usually pointless.

## 8. Handling Errors at the Right Layer in Spring WebFlux

There are multiple error-handling layers; each has its own scope.

### 8.1. Local Handling with Reactor

Use `onErrorResume` when a component has a concrete recovery strategy:

~~~java
return cache.get(key)
    .onErrorResume(CacheUnavailableException.class,
        error -> database.find(key));
~~~

If the cache is an optimization and the database is the primary source of truth, this fallback is reasonable. If both cache and database fail, let the error propagate; do not return a fake empty value.

Use `onErrorMap` to normalize errors at a boundary:

~~~java
return repository.save(entity)
    .onErrorMap(DuplicateKeyException.class,
        error -> new OrderConflictException("Order already exists"));
~~~

Preserve the cause when translating exceptions. Do not turn every database error into `OrderConflictException`; only convert when the exact duplicate condition matches the contract.

### 8.2. `@RestControllerAdvice` and `@ExceptionHandler`

For annotated controllers, `@RestControllerAdvice` is the right place to map exceptions into a consistent HTTP status and error body.

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<ApiError> notFound(
        OrderNotFoundException error,
        ServerWebExchange exchange
    ) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(ApiError.of(
                "ORDER_NOT_FOUND",
                "Order was not found.",
                exchange
            ));
    }
}
~~~

Spring WebFlux supports synchronous or reactive exception handlers. Pick a consistent return style across the application. With multiple errors, define specific handlers and a final fallback for unexpected exceptions.

### 8.3. `WebExceptionHandler`

`WebExceptionHandler` sits at the outer layer of the WebFlux handler/filter chain. It is suitable for errors escaping from filters or parts of the web pipeline that `@ControllerAdvice` does not handle, and can be used in global configuration.

Distinction:

| Mechanism | Scope |
| --- | --- |
| `onErrorResume` / `onErrorMap` | A single Publisher or service boundary |
| `@ExceptionHandler` / `@RestControllerAdvice` | Annotated controller dispatch |
| `HandlerFilterFunction` | Functional routes attached to the filter |
| `WebFilter` | Broader WebFlux chain, before/after the handler |
| `WebExceptionHandler` | Errors escaping outside the filter/handler chain |

Functional endpoints are not annotated controllers; if you need router-specific error handling, you can use `HandlerFilterFunction`. For pipeline-wide errors, consider `WebExceptionHandler`.

### 8.4. Do Not Catch Errors Too Early

If a service catches every exception and returns `Mono.empty()`, the HTTP layer can no longer tell a missing resource apart from a broken dependency or a bug. Only handle locally the errors that the component can genuinely recover from; all other errors must keep propagating upward.

## 9. Retry, Timeout, and Circuit Breaker: Apply Only to Recoverable Errors

### 9.1. Do Not Retry Input or Business Errors

Cases that generally should not be retried automatically:

- DTO missing fields or malformed.
- Insufficient stock under current state.
- Order does not exist.
- User lacks permission.
- Domain state conflict.

Retrying the same request under the same conditions usually just adds load and repeats the rejection.

### 9.2. Conditionally Retry Infrastructure Errors

Reactor supports `retryWhen`:

~~~java
return webClientCall()
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(this::isTransientFailure)
            .onRetryExhaustedThrow((spec, signal) -> signal.failure())
    );
~~~

This is an illustrative pattern. `isTransientFailure` must be an application-defined predicate that matches only recoverable errors, such as certain connection failures or temporary 503s. Two retries mean at most three total attempts including the initial one.

Retries need:

- Bounded attempt count and total duration.
- Exponential backoff and jitter to avoid many clients retrying simultaneously.
- Per-attempt timeouts and an overall request deadline.
- Metrics for retry counts, exhausted retries, and latency.
- A clear policy when the client has already cancelled the request.

### 9.3. Be Careful with Side Effects and Idempotency

A POST operation creating an order may have already committed to the database even if the upstream response was lost. Retrying the entire operation risks creating duplicate orders. For write operations, design appropriate idempotency keys, unique constraints, transactions, or deduplication mechanisms.

Never retry a Publisher arbitrarily just because it emitted an error. You must understand how far side effects have progressed and whether the source can be re-executed safely.

### 9.4. Timeout Alone Does Not Solve Resource Leaks

~~~java
return inventoryClient.reserve(sku, quantity)
    .timeout(Duration.ofMillis(500));
~~~

Timeout emits an error when the operation does not complete within the deadline. The driver/client must support cancellation properly to abort the request or release resources. Not all external systems roll back work that has already started when a subscriber cancels.

### 9.5. Circuit Breaker and Bulkhead

A circuit breaker can temporarily pause calls to a dependency that keeps failing, preventing the system from wasting resources on a broken upstream. A bulkhead limits concurrent operations so a single dependency cannot exhaust all application resources.

These mechanisms are typically implemented with libraries such as Resilience4j or gateway/client policies. They do not replace error classification: input errors remain input errors, domain conflicts remain conflicts, and circuit-open is a signal that the dependency is temporarily unavailable.

## 10. Observing Errors: Logs, Traces, and Metrics

### 10.1. Use Request ID / Correlation ID

A request ID should accompany logs across filters, controllers, services, and dependency calls. You can generate an ID in a `WebFilter` and place it in an exchange attribute and response header. If receiving an ID from a gateway, verify whether the gateway is trusted and sanitize the incoming value.

Do not store the request ID in a mutable field of a singleton service because concurrent requests will overwrite each other.

### 10.2. Log Once at the Appropriate Boundary

If every layer logs the same exception at ERROR level, a single failure produces duplicate log entries. A good approach:

- The service logs necessary context when translating a dependency failure into an application exception.
- The global exception handler logs unexpected errors or errors requiring alerts.
- Validation/business errors can be logged at INFO/WARN per policy, not necessarily ERROR.
- Always include a trace ID to correlate logs belonging to the same request.

Do not log request bodies or sensitive headers by default.

### 10.3. Metrics Should Use Low-Cardinality Labels

You can count requests by status and stable error code:

- `http.server.requests` by method, route template, status.
- `api.errors` by category `INPUT`, `BUSINESS`, `INFRASTRUCTURE`, `UNKNOWN`.
- `dependency.calls` by dependency, outcome, and timeout/retry.
- `retry.exhausted` and `circuit.breaker.state`.

Do not use user IDs, order IDs, URLs containing path variables, or exception messages as metric tags; the number of values can grow unbounded and put pressure on the metrics backend.

## 11. Complete Spring Boot 3.5.7 + Java 17 Example

The example simulates an API for creating and looking up orders. It distinguishes:

- Input validation: blank SKU or out-of-range quantity → 400.
- Business errors: missing order → 404; simulated conflicting SKU → 409.
- Infrastructure errors: simulated unavailable inventory service → 503; overly slow response → 504.
- Unexpected errors → 500 with a safe message.

The project uses Spring Boot **3.5.7**, Java 17, WebFlux, and Bean Validation.

### 11.1. Project Structure

~~~text
webflux-error-taxonomy/
├── pom.xml
└── src/main/java/example/errors/
    ├── OrderApiApplication.java
    ├── OrderController.java
    ├── OrderService.java
    ├── InventoryGateway.java
    ├── RequestIdWebFilter.java
    ├── ApiExceptionHandler.java
    ├── ApiError.java
    ├── CreateOrderRequest.java
    ├── OrderView.java
    ├── OrderNotFoundException.java
    ├── OrderConflictException.java
    ├── InventoryUnavailableException.java
    └── UpstreamTimeoutException.java
└── src/test/java/example/errors/
    └── OrderApiIntegrationTest.java
~~~

### 11.2. `pom.xml`

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
    <artifactId>webflux-error-taxonomy</artifactId>
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
~~~

### 11.3. `OrderApiApplication.java`

~~~java
package example.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApiApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApiApplication.class, args);
    }
}
~~~

### 11.4. `CreateOrderRequest.java`

~~~java
package example.errors;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String sku,
    @Min(1) @Max(100) int quantity
) {}
~~~

### 11.5. `OrderView.java`

~~~java
package example.errors;

public record OrderView(
    long id,
    String sku,
    int quantity,
    String status
) {}
~~~

### 11.6. Meaningful Exceptions

`OrderNotFoundException.java`:

~~~java
package example.errors;

public final class OrderNotFoundException extends RuntimeException {

    public OrderNotFoundException(long id) {
        super("Order not found: " + id);
    }
}
~~~

`OrderConflictException.java`:

~~~java
package example.errors;

public final class OrderConflictException extends RuntimeException {

    public OrderConflictException(String message) {
        super(message);
    }
}
~~~

`InventoryUnavailableException.java`:

~~~java
package example.errors;

public final class InventoryUnavailableException extends RuntimeException {

    public InventoryUnavailableException() {
        super("Inventory dependency is unavailable");
    }

    public InventoryUnavailableException(Throwable cause) {
        super("Inventory dependency is unavailable", cause);
    }
}
~~~

`UpstreamTimeoutException.java`:

~~~java
package example.errors;

public final class UpstreamTimeoutException extends RuntimeException {

    public UpstreamTimeoutException(Throwable cause) {
        super("Inventory dependency timed out", cause);
    }
}
~~~

### 11.7. `InventoryGateway.java`

This is a simulated dependency gateway so the example runs standalone without needing a real database or inventory service:

~~~java
package example.errors;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Mono;

@Component
public class InventoryGateway {

    public Mono<Void> reserve(String sku, int quantity) {
        Mono<Void> operation;

        if ("DOWN".equalsIgnoreCase(sku)) {
            operation = Mono.error(
                new InventoryUnavailableException());
        } else if ("SLOW".equalsIgnoreCase(sku)) {
            operation = Mono.delay(Duration.ofSeconds(2)).then();
        } else if ("CONFLICT".equalsIgnoreCase(sku)) {
            operation = Mono.error(
                new OrderConflictException(
                    "Inventory reservation conflicts with current state"));
        } else {
            operation = Mono.empty();
        }

        return operation
            .timeout(Duration.ofMillis(250))
            .onErrorMap(
                TimeoutException.class,
                UpstreamTimeoutException::new
            );
    }
}
~~~

In a real system, replace the simulated gateway with WebClient, R2DBC, or the appropriate client. Only convert identified connection/timeout/5xx errors into infrastructure exceptions. Do not turn all dependency errors into 503.

### 11.8. `OrderService.java`

~~~java
package example.errors;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class OrderService {

    private record StoredOrder(
        long id,
        String sku,
        int quantity
    ) {}

    private final InventoryGateway inventory;
    private final AtomicLong sequence = new AtomicLong(100);
    private final ConcurrentMap<Long, StoredOrder> orders =
        new ConcurrentHashMap<>();

    public OrderService(InventoryGateway inventory) {
        this.inventory = inventory;
    }

    public Mono<OrderView> create(CreateOrderRequest request) {
        return inventory.reserve(request.sku(), request.quantity())
            .then(Mono.fromSupplier(() -> {
                long id = sequence.incrementAndGet();
                StoredOrder order = new StoredOrder(
                    id, request.sku(), request.quantity());
                orders.put(id, order);

                return new OrderView(
                    id, order.sku(), order.quantity(), "CREATED");
            }));
    }

    public Mono<OrderView> findById(long id) {
        StoredOrder order = orders.get(id);

        if (order == null) {
            return Mono.empty();
        }

        return Mono.just(new OrderView(
            order.id(), order.sku(), order.quantity(), "CREATED"));
    }
}
~~~

The concurrent map and `AtomicLong` are only for a single-process demo. Data will be lost when the application restarts. Production systems should use an appropriate repository/database and transactions.

### 11.9. `OrderController.java`

~~~java
package example.errors;

import java.net.URI;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public Mono<ResponseEntity<OrderView>> create(
        @Valid @RequestBody CreateOrderRequest request
    ) {
        return service.create(request)
            .map(order -> ResponseEntity
                .created(URI.create("/api/orders/" + order.id()))
                .body(order));
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<OrderView>> get(
        @PathVariable long id
    ) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(id)))
            .map(ResponseEntity::ok);
    }
}
~~~

`@Valid` handles input errors before the method runs. Exceptions from the service continue traveling in the reactive pipeline and are mapped into HTTP responses by `ApiExceptionHandler`.

### 11.10. `RequestIdWebFilter.java`

~~~java
package example.errors;

import java.util.UUID;

import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(0)
public class RequestIdWebFilter implements WebFilter {

    public static final String ATTRIBUTE =
        RequestIdWebFilter.class.getName() + ".requestId";

    @Override
    public Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    ) {
        String requestId = UUID.randomUUID().toString();

        exchange.getAttributes().put(ATTRIBUTE, requestId);
        exchange.getResponse().getHeaders()
            .set("X-Request-Id", requestId);

        return chain.filter(exchange);
    }
}
~~~

Each request receives its own ID. The filter does not subscribe on its own; it returns the Publisher from `chain.filter(exchange)` so the framework manages the lifecycle.

### 11.11. `ApiError.java`

~~~java
package example.errors;

import java.time.Instant;

public record ApiError(
    Instant timestamp,
    int status,
    String code,
    String message,
    String path,
    String traceId
) {}
~~~

### 11.12. `ApiExceptionHandler.java`

~~~java
package example.errors;

import java.time.Instant;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
        OrderNotFoundException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.NOT_FOUND,
            "ORDER_NOT_FOUND",
            "Order was not found.",
            exchange
        );
    }

    @ExceptionHandler(OrderConflictException.class)
    public ResponseEntity<ApiError> conflict(
        OrderConflictException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.CONFLICT,
            "ORDER_CONFLICT",
            "The requested operation conflicts with the current order or inventory state.",
            exchange
        );
    }

    @ExceptionHandler(InventoryUnavailableException.class)
    public ResponseEntity<ApiError> inventoryUnavailable(
        InventoryUnavailableException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.SERVICE_UNAVAILABLE,
            "INVENTORY_UNAVAILABLE",
            "Inventory service is temporarily unavailable.",
            exchange
        );
    }

    @ExceptionHandler(UpstreamTimeoutException.class)
    public ResponseEntity<ApiError> upstreamTimeout(
        UpstreamTimeoutException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.GATEWAY_TIMEOUT,
            "INVENTORY_TIMEOUT",
            "Inventory service did not respond in time.",
            exchange
        );
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> validationFailed(
        WebExchangeBindException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.BAD_REQUEST,
            "REQUEST_VALIDATION_FAILED",
            "One or more request fields are invalid.",
            exchange
        );
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ApiError> invalidInput(
        ServerWebInputException error,
        ServerWebExchange exchange
    ) {
        return response(
            HttpStatus.BAD_REQUEST,
            "INVALID_REQUEST_BODY",
            "The request body or parameter could not be read.",
            exchange
        );
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(
        Exception error,
        ServerWebExchange exchange
    ) {
        // Log full details server-side with the request ID.
        // Never send error.getMessage() or the stack trace to the client.
        return response(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
            "An unexpected server error occurred.",
            exchange
        );
    }

    private ResponseEntity<ApiError> response(
        HttpStatus status,
        String code,
        String message,
        ServerWebExchange exchange
    ) {
        String traceId = String.valueOf(
            exchange.getAttribute(RequestIdWebFilter.ATTRIBUTE));

        ApiError body = new ApiError(
            Instant.now(),
            status.value(),
            code,
            message,
            exchange.getRequest().getPath().value(),
            traceId
        );

        return ResponseEntity.status(status).body(body);
    }
}
~~~

In this class, specific exceptions are handled before the `Exception` fallback. Never use `error.getMessage()` as the response message. In a real application, add a logger in the fallback and log details only once according to policy. You can add handlers for method validation, security, or rate-limit errors depending on the API.

### 11.13. Running the Application and Testing Each Error Category

From the directory containing `pom.xml`, run:

~~~bash
mvn spring-boot:run
~~~

**A. Valid request — create an order:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"PEN","quantity":2}'
~~~

Expected main result: HTTP 201 Created, with `Location: /api/orders/101` and a body similar to:

~~~json
{"id":101,"sku":"PEN","quantity":2,"status":"CREATED"}
~~~

**B. Input error — blank SKU and quantity equal to 0:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":0}'
~~~

Expected result: HTTP 400, `code` is `REQUEST_VALIDATION_FAILED`.

**C. Business error — inventory conflict:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"CONFLICT","quantity":1}'
~~~

Expected result: HTTP 409, `code` is `ORDER_CONFLICT`.

**D. Infrastructure error — inventory service unavailable:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"DOWN","quantity":1}'
~~~

Expected result: HTTP 503, `code` is `INVENTORY_UNAVAILABLE`.

**E. Infrastructure error — upstream timeout:**

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"SLOW","quantity":1}'
~~~

Expected result: HTTP 504 after about 250 ms, `code` is `INVENTORY_TIMEOUT`.

**F. Business error — order does not exist:**

~~~bash
curl -i http://localhost:8080/api/orders/999999
~~~

Expected result: HTTP 404, `code` is `ORDER_NOT_FOUND`.

The error bodies share the same `ApiError` structure; timestamp, path, and traceId values vary per request. Example 503:

~~~json
{
  "timestamp": "2026-11-08T02:00:00Z",
  "status": 503,
  "code": "INVENTORY_UNAVAILABLE",
  "message": "Inventory service is temporarily unavailable.",
  "path": "/api/orders",
  "traceId": "..."
}
~~~

## 12. Testing the Error Contract with WebTestClient

Test status and error code instead of depending on internal exception strings:

~~~java
package example.errors;

import static org.springframework.http.MediaType.APPLICATION_JSON;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderApiIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void invalidInputReturns400() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.code")
            .isEqualTo("REQUEST_VALIDATION_FAILED");
    }

    @Test
    void businessConflictReturns409() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("CONFLICT", 1))
            .exchange()
            .expectStatus().isEqualTo(409)
            .expectBody()
            .jsonPath("$.code").isEqualTo("ORDER_CONFLICT");
    }

    @Test
    void dependencyUnavailableReturns503() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("DOWN", 1))
            .exchange()
            .expectStatus().isEqualTo(503)
            .expectHeader().exists("X-Request-Id")
            .expectBody()
            .jsonPath("$.code").isEqualTo("INVENTORY_UNAVAILABLE");
    }

    @Test
    void dependencyTimeoutReturns504() {
        client.post()
            .uri("/api/orders")
            .contentType(APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("SLOW", 1))
            .exchange()
            .expectStatus().isEqualTo(504)
            .expectBody()
            .jsonPath("$.code").isEqualTo("INVENTORY_TIMEOUT");
    }

    @Test
    void missingOrderReturns404() {
        client.get()
            .uri("/api/orders/999999")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND");
    }
}
~~~

Run tests:

~~~bash
mvn test
~~~

Integration tests verify the HTTP boundary. Additionally, you should unit-test the service separately with `StepVerifier` to verify that domain Publishers emit values, complete empty, or error with the expected type. For example:

~~~java
StepVerifier.create(service.findById(999999))
    .expectNextCount(0)
    .verifyComplete();
~~~

For the `findById` method, empty completion is the repository contract; the controller translates that state into `OrderNotFoundException`. Testing the two layers separately helps pinpoint whether a bug lies in the domain service or in HTTP mapping.

## 13. Common Design Mistakes

**Mistake 1 — Returning 500 for every exception.** Clients cannot tell whether the request needs fixing or the server is failing. Establish a clear exception taxonomy and mapping.

**Mistake 2 — Returning 400 for database errors.** Clients cannot fix the request to recover the database. Classify dependency failures and return appropriate statuses such as 503/504.

**Mistake 3 — Returning 500 for validation.** Invalid data is the client's responsibility; use 400 or the status defined by the API contract.

**Mistake 4 — Using `IllegalArgumentException` for both input and business rules.** The HTTP layer cannot distinguish them reliably. Use exceptions named after the domain and error kind.

**Mistake 5 — Treating "not found" as an infrastructure failure.** A repository returning empty may be a normal result. Only convert it to 404 when the endpoint requires the resource to exist.

**Mistake 6 — Retrying every error with unbounded `retry()`.** This can cause a retry storm, amplify load, and repeat side effects. Use conditional, bounded retries with backoff and deadlines.

**Mistake 7 — Retrying POST without idempotency.** A write may have already succeeded even if the response was lost. Use idempotency keys, unique constraints, or appropriate transactions.

**Mistake 8 — Swallowing errors with `onErrorResume(error -> Mono.empty())`.** The API may return 404 or an empty response while a dependency has actually failed. Only fall back when semantics are clear.

**Mistake 9 — Using `doOnError` as if it handled the error.** `doOnError` only observes; the error keeps propagating. To recover, use `onErrorResume` or an appropriate operator.

**Mistake 10 — Catching `Throwable` and returning a default value.** This can mask serious runtime errors. Catch known application exception types; let unexpected errors reach the global fallback.

**Mistake 11 — Returning `exception.getMessage()` to the client.** The message may contain SQL, internal URLs, tokens, or personal data. Use safe public messages and log details server-side.

**Mistake 12 — Using HTTP status as the sole error code.** Many different scenarios share 409 or 400. Add a stable `code` so clients can tell them apart.

**Mistake 13 — Logging the same exception at every layer.** This creates duplicate entries and noise. Choose a primary logging boundary, propagate the trace ID, and add context when translating errors.

**Mistake 14 — Putting retry in the controller without understanding the service.** Retries belong at the dependency boundary or use case that has full knowledge of idempotency and transient errors.

**Mistake 15 — Mapping all upstream 4xx statuses to public client errors.** 401/403/404 from a dependency may reflect credential or internal contract issues. Translate statuses according to your own API's semantics.

**Mistake 16 — Failing to handle an already-committed response.** Once a stream has sent part of its body, you cannot change the status and write a replacement error JSON. Design streaming protocols with error events or stream termination.

**Mistake 17 — Treating cancellation as a 500 server error.** Client disconnects can cancel the subscription; this is a lifecycle signal requiring cleanup, not an exception for sending a new response.

**Mistake 18 — Using metric tags containing order IDs or error messages.** Cardinality grows unbounded. Use route templates, status, and error codes with finite value sets.

## 14. Design and Review Checklist

When adding a new endpoint, ask yourself:

1. Does the DTO check basic syntax, types, and bounds?
2. Which rules are input validation, and which rules depend on domain state?
3. Do business outcomes have clear exception/result types?
4. Are dependency failures translated into application exceptions at the client boundary?
5. Are appropriate timeouts and deadlines configured for external calls?
6. Are retries bounded and applied only to transient errors?
7. Are write operations idempotent or protected by deduplication?
8. Does the global exception handler map safe statuses, codes, and messages?
9. Do unexpected errors return 500 without exposing internal details?
10. Does the request ID/trace ID connect logs across layers?
11. Are there metrics for validation, business conflicts, dependency errors, and timeouts?
12. Do tests verify status, error code, response shape, and non-disclosure of secrets?
13. If the response streams, is behavior defined when an error occurs after commit?
14. If the client cancels, are resources and subscriptions cleaned up properly?

## 15. Self-Check Exercises

1. Which category and status does malformed JSON usually belong to? **Input error; usually 400 Bad Request.**
2. Which category does `quantity = 0` belong to when the contract requires at least 1? **Input validation; usually 400.**
3. A valid request for an already-cancelled order that cannot be shipped belongs to which category? **Business error; usually 409 Conflict.**
4. Which status does looking up a missing order usually map to? **404 Not Found.**
5. Which category does a temporarily disconnected database belong to? **Infrastructure error; usually 503 or 500 depending on contract/role.**
6. Which status can a gateway return after waiting past the upstream deadline? **504 Gateway Timeout.**
7. Does `doOnError` make a Publisher succeed? **No; it only observes the error.**
8. How does `onErrorMap` differ from `onErrorResume`? **One translates the error type; the other switches to another Publisher to recover or emit a new error.**
9. Should validation errors be retried? **No; the request needs to be fixed.**
10. Should a POST order creation be retried? **Only when side effects are protected by idempotency/deduplication and the retry policy is bounded.**
11. Why should `error.getMessage()` not be returned to the client? **It may leak internal information or sensitive data.**
12. What role does `ORDER_CONFLICT` play when statuses are all 409? **It tells the client the exact scenario per contract without parsing messages.**
13. What scope does `@RestControllerAdvice` handle? **Exceptions within annotated controller dispatch.**
14. When is `WebExceptionHandler` used? **For errors at the web pipeline layer escaping outside the filter/handler chain.**
15. Should client stream cancellation be mapped to 500? **No; handle it as lifecycle cancellation and clean up.**
16. Does a circuit breaker replace error classification? **No; it only controls calling a dependency when signs of failure appear.**

## 16. Key Takeaways and References

- **Input errors:** malformed syntax/types/validation; usually 400, 413, 415, or 406.
- **Business errors:** valid request rejected by domain state/rules; usually 404, 409, or 422 per contract.
- **Infrastructure errors:** dependency/network/resource unavailable; may be 503, 504, or 500 depending on role and cause.
- **Unexpected errors:** 500, full server-side logging, no internal disclosure.
- Use meaningful exception types, preserve the cause, and map at the HTTP boundary.
- `doOnError` only observes; `onErrorMap` normalizes; `onErrorResume` recovers; `retryWhen` retries according to policy.
- Retries must be bounded and have backoff, timeouts, and idempotency for side effects.
- `@RestControllerAdvice` handles controllers; `WebExceptionHandler` handles broader WebFlux pipeline errors.
- Responses need status, stable error code, safe message, and trace ID.
- Cancellation is a lifecycle signal; do not confuse it with a server error.

Official documentation:

1. [Spring Framework Reference — WebFlux Exceptions](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html): exception handling in annotated controllers and `@ExceptionHandler`.
2. [Spring Framework Reference — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): Bean Validation, request binding, and validation errors.
3. [Spring Framework Reference — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): error responses, Problem Details, and `ResponseEntityExceptionHandler`.
4. [Spring Framework Reference — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): reactive pipeline, Publisher, codecs, and lifecycle.
5. [Project Reactor Reference — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorMap`, `onErrorResume`, retry, and error signals.
6. [Project Reactor API — Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html): retry policies, backoff, and retry limits.
7. [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): semantics of HTTP status codes such as 400, 404, 409, 413, 415, 422, 429, 500, 503, and 504.
