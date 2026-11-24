# Spring MVC — Classifying Input Errors, Business Errors, and System Errors

## 1. Objectives

A good REST API needs to return meaningful errors to clients while keeping internal details private. In Spring MVC, the same HTTP 400 or 500 can originate from different processing layers. **Classifying errors by cause and remediation responsibility** helps choose the appropriate HTTP status, exception-catching location, response payload, logging, and retry mechanism.

After this lesson, you will be able to:

- Distinguish **input errors** (invalid request), **business errors** (request is understood but violates domain rules/state), and **system errors** (infrastructure, programming bugs, unresponsive dependencies).
- Choose well-founded HTTP statuses: 400, 401, 403, 404, 409, 415, 422, 429, 500, 502, 503, 504; avoid treating every error as 400 or 500.
- Identify where errors arise in the Spring MVC flow and handle them with `@RestControllerAdvice`, `@ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, or `ResponseEntityExceptionHandler`.
- Design a JSON error contract with a stable `code`, a safe `message`, a list of field errors, and correlation information for observability.
- Separate validation/binding errors from domain/service errors without leaking sensitive data; place retries appropriately and test scenarios.
- Build a Spring Boot 3.5.0, Spring Framework 6.2, Java 17+ example with 400/404/409/422/503 errors and MockMvc tests.

**Scope:** Spring MVC Servlet stack. Security errors from Spring Security, network failures at gateways, and Spring WebFlux have additional handling points and will be distinguished where needed. This is a technical guide on error handling, not a mandatory status code set for every API: the HTTP contract must match actual resource and business semantics.

## 2. Three Error Categories: Identifying by Cause

| Category | Nature | Concrete examples | Who usually fixes it? | Common HTTP statuses |
| --- | --- | --- | --- | --- |
| **Input error** | HTTP request has invalid syntax, format, data type, or API constraints | Malformed JSON, query `page=abc`, body missing required field, negative quantity, wrong Content-Type | Client needs to fix the request | 400, 415, sometimes 422 |
| **Business error** | Request is readable, but the action is not allowed by domain rules/state, or the resource does not exist | Cancelling an already cancelled order, exceeding order limit, expired coupon code, non-existent id | Client adjusts action/data or waits for state change | 404, 409, 422 (depending on scenario) |
| **System error** | Service cannot execute due to unexpected failure or infrastructure/downstream issues | Database unreachable, another service times out, programming bug, resource exhaustion | Server/operations; client may retry conditionally | 500, 502, 503, 504 |

**Two important observations:**

1. **HTTP 4xx does not mean all of them are "validation errors".** 401/403 are authentication/authorization; 404 is resource not found; 409 is state conflict; 415 is media type.
2. **A domain error is not automatically 422.** If two operations concurrently modify a resource causing a state conflict, 409 usually expresses it better. If a resource does not exist, 404 makes sense. A rule that cannot be satisfied even though the request is syntactically valid may choose 422. Define it consistently according to the contract.

Order placement flow example:

- `POST /orders` with `{"sku":"ABC","quantity":"abc"}` → cannot convert quantity to a number → **input** (400).
- `POST /orders` with `{"sku":"ABC","quantity":0}`, where the DTO has `@Min(1)` → **input** (400).
- `POST /orders` with `{"sku":"ABC","quantity":11}`, when the rule allows at most 10 items per order → **business** (can be 422).
- `POST /orders/15/cancel` when the order is already cancelled → **business state conflict** (409).
- Cannot connect to the database when creating an order → **system** (500, or 503 if the service is temporarily unavailable and has an appropriate policy).

Classification must be based on defined rules, not inferred arbitrarily from the exception class. An `IllegalArgumentException` might come from a bug or an intentional data check; do not automatically map all of them to 400.

## 3. Where Errors Arise in Spring MVC

~~~text
Client
  |
  v
Servlet Filters / Security Filters
  |  authentication / authorization
  v
DispatcherServlet -> Handler Mapping
  |  404, 405, 415, 406 depending on route, method, media type
  v
Argument Resolution + HttpMessageConverter / Data Binding
  |  JSON parse, missing parameter, type mismatch
  v
Bean Validation (@Valid, constraints)
  |  input field errors / method validation
  v
Controller -> Service -> Domain
  |  resource missing, rule violation, state conflict
  v
Repository / Database / External Service
  |  timeout, unavailable, unexpected errors
  v
Return Value Handling + Response Serialization
  |  JSON serialization, content negotiation failures
  v
HTTP Response
~~~

From the diagram above:

- JSON parsing errors can occur **before the controller method is invoked**, so a `try/catch` inside the handler cannot catch that error.
- `@RestControllerAdvice` handles many exceptions from Spring MVC handler invocation, but it does not replace handling exceptions thrown directly inside the Security filter chain.
- Do not catch exceptions at every layer and return 200 with `{"success":false}`; doing so breaks HTTP semantics, metrics, and many HTTP clients.
- Services should not be tightly coupled to `ResponseEntity` or HTTP status codes; services can throw **meaningful domain exceptions**, and the web layer maps them to statuses.
- System errors occurring while **writing the response body** can happen after headers have already been sent, at which point the server cannot guarantee switching the response to a standard error JSON.

## 4. Input Errors: Clear Layering

### 4.1. Invalid HTTP/JSON Syntax and Media Type

Malformed request example:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"sku":"JAVA-17","quantity":
~~~

This is incomplete JSON that Jackson cannot deserialize. Spring MVC typically throws `HttpMessageNotReadableException` and returns **400 Bad Request**.

If an endpoint declares `consumes="application/json"` but the client sends `text/plain`, Spring can return **415 Unsupported Media Type**. If the client requests `Accept: application/xml` when the API only produces JSON, it can be **406 Not Acceptable**. Do not lump 415 and 406 into 400.

### 4.2. Type Mismatch

~~~java
@GetMapping("/api/orders/{id}")
public OrderDto find(@PathVariable long id) {
    return service.find(id);
}
~~~

The request `GET /api/orders/abc` matches the route with the id variable, but cannot convert `abc` to `long`. Spring MVC typically uses `MethodArgumentTypeMismatchException` in this situation, leading to HTTP 400. This is an **input binding error**, not "order id abc not found".

With `@RequestBody` JSON `{"quantity":"many"}` when the target is `Integer`, the error usually comes from Jackson and is wrapped by Spring in `HttpMessageNotReadableException`. Distinguish the error source even though both may return 400.

### 4.3. Validation After Successful Binding

DTO:

~~~java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}
~~~

Handler:

~~~java
@PostMapping("/api/orders")
public OrderDto create(@Valid @RequestBody CreateOrderRequest request) {
    return service.create(request);
}
~~~

Import `jakarta.validation.Valid`. This is an illustrative handler snippet; the standalone runnable project is in section 10.

- `quantity=0`: JSON parses into an Integer successfully, but fails `@Min(1)`.
- `quantity=null` or missing field: fails `@NotNull`.
- `sku=""`: fails `@NotBlank`.
- `quantity="abc"`: may fail right at Jackson deserialization, before reaching Bean Validation.

In Spring MVC, `@Valid @RequestBody` typically produces `MethodArgumentNotValidException` when object validation fails. When validation applies to other method arguments (for example, constraints directly on parameters), Spring MVC starting from 6.1 can use `HandlerMethodValidationException`. With method validation in Spring MVC, design exception handling to account for both rather than assuming one class is always thrown. A controller with class-level `@Validated` may trigger a different AOP validation path; consult framework documentation for your version.

### 4.4. Practical Validation Mistakes to Avoid

- Using primitive `int` when you need to distinguish "not sent" from `0`; a DTO with `Integer` + `@NotNull` expresses this more clearly.
- Using only `@NotNull` for String and expecting it to reject `""`; use `@NotBlank` when non-empty/non-whitespace text is required.
- Assuming Bean Validation replaces business checks or authorization.
- Returning rejected values verbatim in the error response: they may contain tokens, personal information, or overly long strings.
- Using validation messages as stable error codes for clients; message content may be localized or changed.

## 5. Business Errors: Expressing Domain Violations Explicitly

Example rules in the service:

~~~java
public OrderDto cancel(long orderId) {
    OrderDto order = repository.find(orderId);
    if (order == null) {
        throw new OrderNotFoundException("Order not found");
    }
    if ("CANCELLED".equals(order.status())) {
        throw new OrderConflictException("Order is already cancelled");
    }
    return repository.cancel(orderId);
}
~~~

This is Java pseudocode in the context of a service with `repository`; the complete project in section 10 uses a runnable in-memory store. How to separate exceptions:

| Domain condition | Meaningful exception | Possible HTTP mapping |
| --- | --- | --- |
| Order id not found | `OrderNotFoundException` | 404 |
| Cancelling an already cancelled order | `OrderConflictException` | 409 |
| Quantity exceeds business limit | `OrderRuleException` | 422 |
| Operation is allowed in general, but actor lacks permission | Authorization failure | 403, depending on Spring Security |
| Resource changed by version and update is stale | Version/optimistic lock conflict | 409, or precondition 412 if using `If-Match` |
| Duplicate unique key identified as a business conflict | Duplicate/conflict exception | 409 |

**Responsibility boundary:** the service knows "the order is already cancelled" is a rule-violating state; the web layer knows how to represent that as HTTP 409. The domain should not import `HttpStatus` just to throw errors.

**Do not map every `DataIntegrityViolationException` to 409.** A database constraint error can indicate many different causes, including bugs or data corruption. Only translate it to a business error code after identifying the exact constraint/context; otherwise you may hide system errors.

### 5.1. How Do 409 and 422 Differ?

- **409 Conflict:** the request conflicts with the *current state* of the resource, such as trying to cancel an already cancelled order, creating a resource with a duplicate identifier, or updating based on an old version.
- **422 Unprocessable Content:** the server understands the media type and valid syntax, but cannot process the semantically invalid content, such as a quantity exceeding a specific rule. Not every rule has to be 422; an API may choose 400 for certain business validations if the contract explains it clearly.
- **404 Not Found:** the resource at the URL does not exist, or its existence is intentionally hidden under certain access policies.

What matters is **consistency of the contract**, not using many HTTP codes just to look sophisticated.

## 6. System Errors: 500, 502, 503, 504, and Retries

System examples:

- Database driver throws an unexpected connection error: the application could not complete the operation → can return 500, or 503 depending on the cause and "temporarily unavailable" policy.
- Downstream service returns an abnormal response so the gateway/proxy does not receive a valid response: **502 Bad Gateway** is usually appropriate at the **gateway**.
- Gateway waits too long for upstream: **504 Gateway Timeout** is usually emitted by the **gateway/proxy**.
- Application actively rejects requests because it is under maintenance or temporarily short on resources: **503 Service Unavailable** (optionally with `Retry-After` when an appropriate wait time is known).
- Unexpected programming bug, NullPointerException, wrong assumption: **500 Internal Server Error**.

Do not label every `RuntimeException` as `503`, nor arbitrarily pick 504 for any `SocketTimeoutException` raised inside a service: the server's role in the HTTP chain and the status semantics must be clearly defined.

### 6.1. Information Returned to Clients

A system error response should contain a generic description:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "A server error occurred. Please try again later.",
  "status": 500,
  "path": "/api/orders"
}
~~~

Avoid including in public responses: stack traces, SQL statements, connection URLs, passwords, bearer tokens, internal class/package names, infrastructure addresses, PII, or raw `exception.getMessage()` from dependencies. Internal logs need stack traces and correlation/trace IDs for engineers to investigate, but **do not unconditionally log secrets or entire request bodies**.

### 6.2. Retrying the Right Error Types

- 400/422 caused by invalid input or fixed domain rules: generally **do not retry unchanged**.
- 401: refresh/re-login if appropriate; 403: do not automatically retry to probe permissions endlessly.
- 409 due to optimistic locking: may read the new version and retry with a controlled update; do not blindly retry dangerous commands.
- 429: honor `Retry-After` and rate-limit policies if present.
- 503/504 due to transient errors: may retry with **bounded exponential backoff + jitter**, timeouts, and circuit breakers.
- For non-idempotent POSTs, retrying after a timeout can create **duplicate orders**. Use **idempotency keys**, deduplication, or safety guarantees before retrying automatically.

Retries must be bounded, observable, and respect deadlines; avoid a "retry storm" that further overloads a failing system.

## 7. Standardizing the JSON Error Response

An API can use a **custom DTO** or the **RFC 9457 Problem Details** standard. You do not need to return both from the same endpoint.

### 7.1. Custom API Error DTO

A clear format:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Dữ liệu yêu cầu không hợp lệ",
  "status": 400,
  "path": "/api/orders",
  "violations": [
    {"field": "sku", "reason": "NotBlank"},
    {"field": "quantity", "reason": "Min"}
  ]
}
~~~

Roles of each field:

- `code`: stable machine-readable code such as `INVALID_INPUT`, `ORDER_CONFLICT`, `DEPENDENCY_UNAVAILABLE`. Clients should rely on the code, not parse Vietnamese text in `message`.
- `message`: safe, human-readable message; may be localized, so it is not a machine identifier.
- `status`: HTTP status number for observability; must **match the actual HTTP status**.
- `path`: URL path, avoiding embedding query strings that contain tokens or sensitive data.
- `violations`: list of field names and constraint codes; returning raw rejected values is not required.

In production, teams often add `requestId`/`traceId` searchable in logs or distributed tracing, an ISO-8601 timestamp, and documentation of error codes. Only trust a client-supplied request id if it has been validated/bounded/normalized; usually the system generates or controls the correlation id at the gateway/filter.

### 7.2. ProblemDetail per RFC 9457

Spring Framework 6 supports `ProblemDetail` / `ErrorResponse`. Example:

~~~java
@ExceptionHandler(OrderConflictException.class)
public ProblemDetail handleConflict(OrderConflictException ex) {
    ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.CONFLICT);
    pd.setTitle("Order state conflict");
    pd.setDetail("The order cannot be cancelled in its current state");
    pd.setProperty("code", "ORDER_CONFLICT");
    return pd;
}
~~~

This snippet illustrates a method inside `@RestControllerAdvice`; it requires importing `org.springframework.http.ProblemDetail`, `org.springframework.http.HttpStatus`, and the corresponding exception. Spring can populate `instance` from the request URL when unset; the response typically uses `application/problem+json`. Common shape:

~~~json
{
  "type": "about:blank",
  "title": "Order state conflict",
  "status": 409,
  "detail": "The order cannot be cancelled in its current state",
  "instance": "/api/orders/1/cancel",
  "code": "ORDER_CONFLICT"
}
~~~

If you want to handle many Spring MVC built-in exceptions consistently as Problem Details, look at `ResponseEntityExceptionHandler` or standard error configuration provided by the framework. **Do not simply catch `Exception.class` to return 500 and accidentally mask 400/405/406/415**. Both Custom DTO and ProblemDetail are acceptable if the API contract chooses one clearly and tests it in practice.

## 8. @RestControllerAdvice and @ExceptionHandler Scope

### 8.1. Choosing the Right Exception and HTTP Status

~~~java
@RestControllerAdvice
public class OrderAdvice {
    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(OrderNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError("ORDER_NOT_FOUND", "Order not found"));
    }

    @ExceptionHandler(OrderConflictException.class)
    public ResponseEntity<ApiError> conflict(OrderConflictException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError("ORDER_CONFLICT", "Order is already cancelled"));
    }
}
~~~

This is a condensed mapping example (requires an `ApiError` class, exceptions, and appropriate imports; the complete project is in section 10). Spring selects handlers by exception type; `@RestControllerAdvice` applies to controllers within its target scope. When an exception is caught in a controller and handled completely, it does not automatically pass through the advice.

Framework-built errors usually have their own statuses. If extending `ResponseEntityExceptionHandler`, use the appropriate protected hooks to override how the body is returned instead of declaring new `@ExceptionHandler` methods that overlap mappings already handled by the base class, as that can cause ambiguous exception handler mapping.

### 8.2. Do Not Swallow Exceptions into Fake Success

Wrong:

~~~java
try {
    service.chargeOrder(order);
} catch (Exception ex) {
    return ResponseEntity.ok(Map.of("success", false));
}
~~~

If it is a system error, returning **HTTP 200** misleads monitoring and clients. Furthermore, catching every exception can hide bugs, lose stack traces, or let transactions proceed in an inconsistent state.

Let meaningful domain errors propagate up to advice; unexpected errors should be logged/observed and handled with appropriate fallbacks. When catching an exception to **add context**, preserve the cause:

~~~java
try {
    paymentGateway.charge(order);
} catch (GatewayTimeoutException ex) {
    throw new PaymentDependencyException(
            "Payment provider temporarily unavailable", ex);
}
~~~

This illustrative snippet assumes the classes/services exist; it is not standalone code. Do not classify errors by matching strings in `ex.getMessage()`, because messages can change across versions or languages.

### 8.3. Spring Security Boundary

When Spring Security is present, Authentication and AccessDenied exceptions are typically handled by the **security filter chain** through `AuthenticationEntryPoint` and `AccessDeniedHandler`. Using `@RestControllerAdvice` does not guarantee catching errors that occur **before `DispatcherServlet`**. In secured REST APIs, standardize 401/403 responses via the corresponding Security configuration.

- **401 Unauthorized**: the request lacks valid authentication credentials; practical standards often require `WWW-Authenticate` depending on the scheme.
- **403 Forbidden**: authenticated, but insufficient permissions or forbidden.
- **404** is sometimes used intentionally to avoid revealing resource existence, but must follow a consistent policy.

## 9. Layering Exceptions and Transactions

A maintainable architecture:

~~~text
Controller / Web
  - @RequestBody, @Valid, parameter binding
  - HTTP mapping, @RestControllerAdvice
      |
      v
Application Service
  - authorization + orchestration
  - domain exceptions (NotFound, Conflict, RuleViolation)
      |
      v
Domain Model
  - invariants, state transitions
      |
      v
Repository / External Adapter
  - translate known infrastructure failures if needed
  - propagate unexpected exceptions with causal context
~~~

Do not make the domain model aware of `HttpStatus.CONFLICT`. The domain throws `OrderAlreadyCancelledException`; the web layer maps it to 409. Adapter errors bubble up as semantic exceptions or with their root cause preserved.

With Spring transactions, **unchecked exceptions** cause `@Transactional` to roll back by default; checked exceptions have different rollback rules unless configured. Never catch a serious exception inside a service and continue returning success, as that can cause the transaction to commit partial data. A business rejection may write nothing and still roll back; a safely handled conflict yields an appropriate response depending on business rules.

For concurrent updates, the business logic may need optimistic locking, DB unique constraints, and atomicity; checking "order is currently NEW" first and then updating in two steps does not mean there is no race condition. The in-memory example in section 10 uses `ConcurrentHashMap.compute` for atomic cancellation within the map.

## 10. Runnable Project: Classifying and Returning Errors over HTTP

**Requirements:** Java 17+, Maven. The example uses Spring Boot 3.5.0, Spring MVC, and Bean Validation. Data is stored in RAM, seeding order #1 to test 404/409; there is an endpoint simulating 503 for learning purposes. The exercise is self-contained and requires no database.

Structure:

~~~text
error-demo/
├── pom.xml
└── src/
    ├── main/java/demo/ErrorHandlingApplication.java
    └── test/java/demo/OrderApiTest.java
~~~

### 10.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>error-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
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
~~~

### 10.2. ErrorHandlingApplication.java

All of the code below belongs in **one file** `src/main/java/demo/ErrorHandlingApplication.java`: one public class matching the file name, with the other records/classes package-private. The endpoints expose explicit JSON so they are easy to test with curl.

~~~java
package demo;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.stereotype.Service;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@SpringBootApplication
public class ErrorHandlingApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorHandlingApplication.class, args);
    }
}

record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity) {
}

record OrderDto(long id, String sku, int quantity, String status) {
}

record FieldViolation(String field, String reason) {
}

record ApiFailure(
        String code,
        String message,
        int status,
        String path,
        List<FieldViolation> violations) {
}

class OrderMissingException extends RuntimeException {
    OrderMissingException() { super("Order not found"); }
}

class OrderConflictException extends RuntimeException {
    OrderConflictException() { super("Order is already cancelled"); }
}

class OrderRuleException extends RuntimeException {
    OrderRuleException() { super("Quantity exceeds business limit"); }
}

class DependencyUnavailableException extends RuntimeException {
    DependencyUnavailableException() { super("Dependency unavailable"); }
}

@Service
class OrderService {
    private final Map<Long, OrderDto> store = new ConcurrentHashMap<>();
    private final AtomicLong nextId = new AtomicLong(1L);

    OrderService() {
        store.put(1L, new OrderDto(1L, "JAVA-17", 2, "NEW"));
    }

    OrderDto find(long id) {
        OrderDto found = store.get(id);
        if (found == null) {
            throw new OrderMissingException();
        }
        return found;
    }

    OrderDto create(CreateOrderRequest request) {
        // Basic validation already occurred at the controller.
        // The max-10 rule is a business rule in the service.
        if (request.quantity() > 10) {
            throw new OrderRuleException();
        }
        long id = nextId.incrementAndGet();
        OrderDto created = new OrderDto(
                id,
                request.sku().trim().toUpperCase(Locale.ROOT),
                request.quantity(),
                "NEW");
        store.put(id, created);
        return created;
    }

    OrderDto cancel(long id) {
        // compute operates atomically for a single key, avoiding read-then-write.
        return store.compute(id, (key, old) -> {
            if (old == null) {
                throw new OrderMissingException();
            }
            if ("CANCELLED".equals(old.status())) {
                throw new OrderConflictException();
            }
            return new OrderDto(
                    old.id(), old.sku(), old.quantity(), "CANCELLED");
        });
    }
}

@RestController
@RequestMapping(path = "/api/orders",
                produces = MediaType.APPLICATION_JSON_VALUE)
class OrderController {
    private final OrderService service;

    OrderController(OrderService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    OrderDto one(@PathVariable long id) {
        return service.find(id);
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<OrderDto> create(
            @Valid @RequestBody CreateOrderRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(request));
    }

    @PostMapping("/{id}/cancel")
    OrderDto cancel(@PathVariable long id) {
        return service.cancel(id);
    }

    // Simulates a transient error solely for learning/testing.
    @GetMapping("/dependency-demo")
    OrderDto dependencyDemo() {
        throw new DependencyUnavailableException();
    }
}

@RestControllerAdvice
class ApiErrorAdvice {
    @ExceptionHandler(HttpMessageNotReadableException.class)
    ResponseEntity<ApiFailure> invalidJson(
            HttpMessageNotReadableException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.BAD_REQUEST, "INVALID_JSON",
                "Unable to read request JSON",
                request, List.of());
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    ResponseEntity<ApiFailure> invalidParameter(
            MethodArgumentTypeMismatchException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.BAD_REQUEST, "INVALID_PARAMETER",
                "Path or query parameter has an invalid type",
                request, List.of());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ApiFailure> invalidBody(
            MethodArgumentNotValidException ex,
            HttpServletRequest request) {
        List<FieldViolation> fields =
                ex.getBindingResult().getFieldErrors().stream()
                    .map(error -> new FieldViolation(
                            error.getField(),
                            error.getCode() == null
                                    ? "Invalid"
                                    : error.getCode()))
                    .toList();
        return fail(HttpStatus.BAD_REQUEST, "INVALID_INPUT",
                "Invalid request data",
                request, fields);
    }

    @ExceptionHandler(OrderMissingException.class)
    ResponseEntity<ApiFailure> missing(
            OrderMissingException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND",
                "Order not found", request, List.of());
    }

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ApiFailure> conflict(
            OrderConflictException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.CONFLICT, "ORDER_CONFLICT",
                "Order is already cancelled", request, List.of());
    }

    @ExceptionHandler(OrderRuleException.class)
    ResponseEntity<ApiFailure> rule(
            OrderRuleException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.UNPROCESSABLE_ENTITY, "ORDER_RULE",
                "Each order may contain at most 10 items",
                request, List.of());
    }

    @ExceptionHandler(DependencyUnavailableException.class)
    ResponseEntity<ApiFailure> dependency(
            DependencyUnavailableException ex,
            HttpServletRequest request) {
        return fail(HttpStatus.SERVICE_UNAVAILABLE, "DEPENDENCY_UNAVAILABLE",
                "Service is temporarily unavailable",
                request, List.of());
    }

    private ResponseEntity<ApiFailure> fail(
            HttpStatus status,
            String code,
            String message,
            HttpServletRequest request,
            List<FieldViolation> violations) {
        return ResponseEntity.status(status)
                .body(new ApiFailure(code, message, status.value(),
                        request.getRequestURI(), violations));
    }
}
~~~

**Explanation of design decisions in the project:**

- `@Valid @RequestBody` separates Bean Validation from domain logic; JSON parse/type errors have dedicated handlers.
- `OrderService` throws domain exceptions without importing `HttpStatus`; the advice is responsible for mapping 404/409/422.
- The `ApiFailure` shape has a stable code, safe message, and path; it does not return raw exception messages or stack traces.
- `DependencyUnavailableException` is simulated solely for 503. In a real application, dependency failures must be detected and classified by adapters/circuit breakers per contract, rather than creating intentional error endpoints.
- No catch-all `Exception.class` is declared, avoiding unintended interference with default MVC error statuses such as 405/406/415. When a generic 500 response is needed, configure error handling at the appropriate level and **preserve** the semantics of framework exceptions.
- `List<FieldViolation>` can contain multiple errors for the same field; do not assume error ordering is a contract for clients.
- There is no database or authentication in the demo. Production requires transactions, data integrity, and Spring Security as needed.

### 10.3. Running and Testing Each Error Category

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Sample calls with curl (Bash example):

**Success:**

~~~bash
curl -i 'http://localhost:8080/api/orders/1'
~~~

HTTP 200, equivalent JSON:

~~~json
{"id":1,"sku":"JAVA-17","quantity":2,"status":"NEW"}
~~~

**Input error — wrong id type:**

~~~bash
curl -i 'http://localhost:8080/api/orders/abc'
~~~

HTTP 400, equivalent body:

~~~json
{
  "code":"INVALID_PARAMETER",
  "message":"Path or query parameter has an invalid type",
  "status":400,
  "path":"/api/orders/abc",
  "violations":[]
}
~~~

**Input error — missing/invalid body constraints:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"","quantity":0}'
~~~

HTTP 400, `code=INVALID_INPUT`; `violations` typically contains `sku/NotBlank` and `quantity/Min`. Field error order is not guaranteed.

**Input error — syntactically invalid JSON:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"JAVA-17","quantity":'
~~~

HTTP 400, `code=INVALID_JSON`.

**Business error — rule exceeding limit:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  --data '{"sku":"JAVA-17","quantity":11}'
~~~

HTTP 422, `code=ORDER_RULE`, because the request is valid per DTO but exceeds the business limit.

**Business error — order not found:**

~~~bash
curl -i 'http://localhost:8080/api/orders/999'
~~~

HTTP 404, `code=ORDER_NOT_FOUND`.

**Business error — state conflict:**

~~~bash
curl -i -X POST 'http://localhost:8080/api/orders/1/cancel'
curl -i -X POST 'http://localhost:8080/api/orders/1/cancel'
~~~

The first call returns HTTP 200 with `status=CANCELLED`; the second returns HTTP 409 with `code=ORDER_CONFLICT`.

**Simulated system error — dependency unavailable:**

~~~bash
curl -i 'http://localhost:8080/api/orders/dependency-demo'
~~~

HTTP 503 with `code=DEPENDENCY_UNAVAILABLE`. In the example, this error is emitted intentionally; a real service can consider `Retry-After` and circuit breakers depending on conditions.

If running in PowerShell, use `curl.exe` instead of the `curl` alias; `\` line continuations are for Unix shells, so you can write the command on a single line to avoid shell differences.

### 10.4. MockMvc Tests for HTTP Status and Error Code

Create the file `src/test/java/demo/OrderApiTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderApiTest {
    @Autowired
    MockMvc mvc;

    @Test
    void invalidPathVariableIsBadRequest() throws Exception {
        mvc.perform(get("/api/orders/abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_PARAMETER"));
    }

    @Test
    void validationErrorIsBadRequest() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"","quantity":0}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_INPUT"))
            .andExpect(jsonPath("$.violations.length()").value(2));
    }

    @Test
    void malformedJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"JAVA-17\",\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"));
    }

    @Test
    void quantityOverBusinessLimitIs422() throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"sku":"JAVA-17","quantity":11}
                    """))
            .andExpect(status().isUnprocessableEntity())
            .andExpect(jsonPath("$.code").value("ORDER_RULE"));
    }

    @Test
    void missingResourceIs404() throws Exception {
        mvc.perform(get("/api/orders/999"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code").value("ORDER_NOT_FOUND"));
    }

    @Test
    void repeatedCancelIsConflict() throws Exception {
        mvc.perform(post("/api/orders/1/cancel"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("CANCELLED"));

        mvc.perform(post("/api/orders/1/cancel"))
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("ORDER_CONFLICT"));
    }

    @Test
    void temporaryDependencyFailureIs503() throws Exception {
        mvc.perform(get("/api/orders/dependency-demo"))
            .andExpect(status().isServiceUnavailable())
            .andExpect(jsonPath("$.code").value("DEPENDENCY_UNAVAILABLE"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests verify **actual HTTP results** rather than only checking code inside handler methods. Using `$.violations.length()` checks the error count without depending on order. Because the demo stores data in RAM within a single application context, the test that cancels id 1 only runs once in this suite; if writing multiple tests that mutate the same resource, separate the data or reset fixtures so tests remain independent.

## 11. Toward Production: Maintaining Boundaries and Observing Errors

### 11.1. Using ResponseEntityExceptionHandler to Unify Framework Errors

Spring MVC provides `ResponseEntityExceptionHandler` to handle a group of built-in errors as `ErrorResponse`/`ProblemDetail`. Skeleton example:

~~~java
@RestControllerAdvice
class GlobalProblemAdvice extends ResponseEntityExceptionHandler {
    @ExceptionHandler(OrderConflictException.class)
    public ProblemDetail conflict(OrderConflictException ex) {
        ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.CONFLICT);
        pd.setTitle("Order conflict");
        pd.setDetail("The order is in a state that does not allow this operation");
        pd.setProperty("code", "ORDER_CONFLICT");
        return pd;
    }
}
~~~

This snippet illustrates an **alternative approach** to `ApiErrorAdvice` in section 10; do not place both competing advices in the same application. Requires importing `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler`, `RestControllerAdvice`, `ExceptionHandler`, `ProblemDetail`, `HttpStatus`, and the domain exception. When customizing built-in exceptions, prefer overriding the protected handler methods with the exact signature for your Spring version; avoid creating two `@ExceptionHandler` mappings for the same exception.

### 11.2. Generic 500 Should Not Mask Existing Statuses

A catch-all `@ExceptionHandler(Exception.class)` can be useful to build a 500 body and log stack traces, but it can also intercept exceptions that the framework would map to 400, 404, 405, 406, or 415. If a global fallback is needed, design its scope clearly and handle/delegate to Spring's `ErrorResponse` first, or use `ResponseEntityExceptionHandler` to inherit default handling. Do not expose raw exception messages to clients.

### 11.3. Logging, Metrics, and Tracing

Recommended minimum structured information for server logs/metrics:

| Field | Meaning |
| --- | --- |
| `requestId / traceId` | Correlates error responses with logs/traces |
| `route / method` | Distinguishes endpoints, avoiding high cardinality from raw paths containing ids |
| `http.status` | Tracks error rates by 4xx/5xx |
| `error.code` | Groups stable errors per contract |
| `exception.class` | Supports server diagnostics, omitted from public JSON |
| `durationMs` | Identifies timeouts/slowness |
| `downstream.name` | Identifies the involved dependency |

4xx errors generally reflect request/client/domain state; 5xx errors usually warrant server alerts. However, a spike in 409 due to a concurrency bug or a sudden surge of 401s can also signal an issue worth investigating. Avoid logging passwords, tokens, cookies, or request/response bodies containing personal data; mask/redact according to policy.

### 11.4. HTTP Status and Retry Safety

Practical rules:

- Return **200/201** only when the operation actually succeeded according to the contract.
- Return **4xx** when the request fails conditions the client must fix or a domain state prevents execution.
- Return **5xx** when the server/upstream failed to complete the request.
- For transient 503s, add a valid `Retry-After` header when a reasonable wait interval is known.
- For write operations that may be resubmitted, use idempotency keys or optimistic concurrency to reduce duplicate risk.
- For async operations, you may return **202 Accepted** if the work has only been queued; describe how the client checks results and subsequent error states. Do not treat 202 as "completed".

## 12. Self-Check Exercises

**Exercise 1 — Categorization:** For each scenario, choose input/business/system error and an appropriate HTTP status: `page=abc`, JSON missing a brace, cancelled order, database connection lost, `Accept: application/xml` when the API only returns JSON.

**Exercise 2 — Contract Design:** Propose an `ApiFailure` response for `INVALID_INPUT` containing two field errors. Explain why rejected password/token values must not be included in JSON.

**Exercise 3 — Domain Exception:** Create `OrderAlreadyPaidException` in the service and map it to 409 in the advice; update the business rule so that once paid, an order cannot be cancelled.

**Exercise 4 — Framework Exceptions:** Compare `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `HttpMessageNotReadableException`, and `MethodArgumentTypeMismatchException`. Which errors occur before the controller method runs?

**Exercise 5 — System Errors:** On a payment gateway timeout after the payment request was already sent, explain why an immediate client POST retry can cause double charging; propose idempotency keys and tracing.

**Exercise 6 — Testing:** Extend the suite to check HTTP 415 with `Content-Type: text/plain`, 404 resource, 409 duplicate cancel, and 503 dependency; do not compare JSON object field order.

**Exercise 7 — Spring Security:** Explain why `@RestControllerAdvice` does not guarantee catching authentication failures from the filter chain, and identify where 401/403 error bodies should be configured.

## 13. Key Takeaways

- **Input:** request has invalid syntax/type/constraints → fix the request; Spring may raise errors before the handler, typically using HTTP 400.
- **Business:** request is understood but conflicts with state or violates a rule → meaningful domain exceptions; web mapping 404/409/422 per contract.
- **System:** server/dependency failure → appropriate 5xx, internal logging and tracing, safe client message; retries must be conditional and protect idempotency.
- **Spring MVC:** `@RestControllerAdvice`, `@ExceptionHandler`, `ResponseEntity`, `ProblemDetail`, and `ResponseEntityExceptionHandler` are the tools for designing error boundaries; do not "catch everything as 500" and lose native framework statuses.
- A good error API has **accurate HTTP status + stable error code + safe message + observability context**, tested with real requests.

## 14. Official References

- [Spring Framework 6.2 — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): `ErrorResponse`, `ProblemDetail`, `ResponseEntityExceptionHandler`.
- [Spring Framework 6.2 — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [Spring Framework 6.2 — @ExceptionHandler](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-exceptionhandler.html): exceptions in controllers/advice.
- [Spring Framework 6.2 — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-advice.html): sharing configuration across multiple controllers.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): semantics of 4xx/5xx and status codes.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standard machine-readable error object.
