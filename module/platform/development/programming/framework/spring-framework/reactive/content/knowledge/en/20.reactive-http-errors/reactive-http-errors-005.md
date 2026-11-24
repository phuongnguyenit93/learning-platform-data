# `ProblemDetail`, `ErrorResponse`, and Standard Error Responses in Spring WebFlux

## 1. Why Does an API Need a Standard Error Response?

An API does not just return data on success. It must also consistently explain situations such as:

- The client sends malformed JSON or omits a required field.
- A resource does not exist or the user lacks access permission.
- An HTTP method or `Content-Type` is not supported by the endpoint.
- A business rule disallows the requested operation.
- The server encounters an unexpected error.

If each controller invents a different JSON shape, clients must write multiple error-parsing branches. One endpoint might return `{"message":"not found"}`, another `{"error":"ORDER_MISSING"}`, and a third HTML or an empty body. That makes automation, observability, and API evolution harder for clients.

Spring Framework supports the **Problem Details for HTTP APIs** standard, currently specified in **RFC 9457** (succeeding RFC 7807). Spring provides three core abstractions:

- **`ProblemDetail`**: object representing problem content according to RFC 9457.
- **`ErrorResponse`**: contract describing the entire HTTP error response, including status, headers, and `ProblemDetail` body.
- **`ErrorResponseException`**: base exception implementing `ErrorResponse`, allowing business exceptions to carry their HTTP response mapping.

In WebFlux, Spring's built-in HTTP exceptions also implement `ErrorResponse`. Thus an application can standardize both framework-generated errors and application-raised business errors.

## 2. RFC 9457: Structure of Problem Details

An RFC 9457 error response typically uses the media type:

```http
Content-Type: application/problem+json
```

Example:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 42",
  "instance": "/orders/42",
  "code": "ORDER_NOT_FOUND",
  "orderId": 42
}
```

Five standard members:

| Member | Meaning | Usage Rules |
|---|---|---|
| `type` | URI identifying the problem type | Should be stable and may point to error documentation; default can be `about:blank` |
| `title` | Short summary of the problem type | Should not change per error occurrence; may be localized |
| `status` | HTTP status code of the problem | Must match the actual status code sent in the HTTP response |
| `detail` | Specific explanation for this occurrence | Written for users/clients; never reveal stack traces or internal data |
| `instance` | URI reference identifying the specific occurrence | Can be the request path, e.g., `/orders/42` |

Standard fields may be omitted when no suitable value applies. `type` identifies the error category; `instance` identifies the specific occurrence. Do not use them interchangeably.

### 2.1. `type` and `title` Should Be Stable

For example, two different requests hit the same error kind:

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 42",
  "instance": "/orders/42"
}
```

and:

```json
{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 99",
  "instance": "/orders/99"
}
```

`type` and `title` describe the same problem type; `detail` and `instance` vary per specific request. Clients can rely on `type` or the extension `code` to choose behavior instead of parsing the `detail` string.

### 2.2. Extension Members

RFC 9457 allows adding API-specific fields. Example:

```json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "instance": "/orders",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "must-be-positive",
      "message": "Quantity must be greater than zero"
    }
  ],
  "traceId": "req-8f21"
}
```

Useful extensions include `code`, `errors`, `traceId`, `retryable`, or `orderId`. Choose clear, consistent names and avoid colliding with the five standard members.

Do not return entire exception objects, stack traces, SQL, filesystem paths, access tokens, or personal data in extensions. Internal diagnostic details should be recorded in server-side logs/traces and linked using a safe correlation ID.

## 3. `ProblemDetail` in Spring Framework

`org.springframework.http.ProblemDetail` models the problem. Common factory methods:

```java
ProblemDetail notFound = ProblemDetail.forStatus(
        HttpStatus.NOT_FOUND
);

ProblemDetail invalid = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "The request contains an invalid quantity"
);
```

Main properties:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.BAD_REQUEST,
        "The supplied quantity must be positive"
);

problem.setType(URI.create(
        "https://api.example.com/problems/invalid-quantity"
));
problem.setTitle("Invalid quantity");
problem.setInstance(URI.create("/orders"));
problem.setProperty("code", "INVALID_QUANTITY");
problem.setProperty("field", "quantity");
```

Spring provides matching getters/setters for `type`, `title`, `status`, `detail`, `instance`, and `properties`.

### 3.1. `status` in Body vs. HTTP Status

When creating a `ProblemDetail`, ensure the status in the body matches the actual HTTP status. For instance, a body stating `404` while the status line says `200 OK` leaves clients unsure which value to trust.

When Spring renders a `ProblemDetail` directly from `@ExceptionHandler` or `@RequestMapping`, the `status` property is used to determine the HTTP status. If `instance` is not set, Spring can initialize it from the request path.

If constructing `ResponseEntity<ProblemDetail>` manually, set the `ResponseEntity` status to match `ProblemDetail.status`.

### 3.2. Extension Properties and Jackson

Extensions can be added via:

```java
problem.setProperty("code", "ORDER_NOT_FOUND");
problem.setProperty("orderId", 42L);
```

When Jackson is on the classpath, Spring registers `ProblemDetailJacksonMixin`; the `properties` map is unwrapped into top-level JSON properties. Thus clients typically see:

```json
{
  "status": 404,
  "code": "ORDER_NOT_FOUND",
  "orderId": 42
}
```

rather than a nested `"properties"` object. If using another JSON codec or without Jackson, serialization may differ. Verify the actual representation published by your API.

## 4. `ErrorResponse`: Contract for the Full HTTP Error

`ProblemDetail` describes the **body**. `ErrorResponse` describes how to build the **entire response**:

```text
ErrorResponse
   |
   +-- getStatusCode() : HttpStatusCode
   |
   +-- getHeaders()    : HttpHeaders
   |
   +-- getBody()       : ProblemDetail
```

The `org.springframework.web.ErrorResponse` interface also provides message codes and arguments to resolve `type`, `title`, and `detail` through Spring's `MessageSource`.

This is useful because exceptions can carry their HTTP mapping information instead of forcing every controller to write `try/catch` blocks and construct responses manually.

Example creating an `ErrorResponse`:

```java
ErrorResponse error = ErrorResponse.create(
        new IllegalStateException("Order is already closed"),
        HttpStatus.CONFLICT,
        "The order cannot be changed after closing"
);

HttpStatusCode status = error.getStatusCode();
HttpHeaders headers = error.getHeaders();
ProblemDetail body = error.getBody();
```

This is an illustrative API snippet for Spring Framework 6.x. `ErrorResponse.create(...)` creates an implementation with the corresponding status, headers, and `ProblemDetail`. If you need more control, use `ErrorResponse.builder(...)` and then `build()`.

A good `ErrorResponse` ensures:

- `getStatusCode()` accurately reflects the HTTP error.
- `getBody().getStatus()` matches the status code.
- Required headers are preserved, such as `Allow` for unsupported-method errors or authentication-related headers.
- The body contains public, safe information sufficient for client handling.
- Message codes/arguments do not rely on unstable internal error strings.

## 5. `ErrorResponseException` and `ResponseStatusException`

### 5.1. `ErrorResponseException`

`ErrorResponseException` is a runtime exception implementing `ErrorResponse`. It can be thrown directly or serve as a base class for specific business exceptions.

Main constructors in Spring Framework 6.1:

```java
new ErrorResponseException(HttpStatus.NOT_FOUND);

new ErrorResponseException(
        HttpStatus.NOT_FOUND,
        cause
);

new ErrorResponseException(
        HttpStatus.NOT_FOUND,
        problemDetail,
        cause
);
```

After creation, the body can be customized:

```java
exception.setType(URI.create(
        "https://api.example.com/problems/order-not-found"
));
exception.setTitle("Order not found");
exception.setDetail("No order exists with id 42");
exception.setInstance(URI.create("/orders/42"));
```

Or use `exception.getBody().setProperty(...)` to add extension members.

### 5.2. `ResponseStatusException`

`ResponseStatusException` is a subclass of `ErrorResponseException`. It suits concise HTTP errors that do not need a dedicated exception class:

```java
throw new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Order 42 was not found"
);
```

In a reactive chain:

```java
return orderService.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Order was not found"
                )
        ));
```

By default, `reason` maps to `ProblemDetail`'s `detail`. If the API requires `type`, `code`, extension members, or stable reusable rules, a subclass of `ErrorResponseException` is usually clearer.

### 5.3. Which One to Choose?

| Approach | Suitable When |
|---|---|
| `ResponseStatusException` | Simple HTTP errors, one-off usage, or no custom extensions needed |
| `ErrorResponseException` directly | Need a specific body/status without a dedicated exception class yet |
| Subclass `ErrorResponseException` | Stable business errors with dedicated `type`, `code`, properties, and HTTP rules |
| Return `ProblemDetail` from `@ExceptionHandler` | Want to decouple internal exceptions from HTTP formatting |
| Custom `ErrorResponse` | Need a custom status/headers/body contract or integration with another error abstraction |

## 6. Built-in WebFlux Exceptions

Many exceptions thrown by Spring WebFlux already implement `ErrorResponse`. Examples:

| Exception | Typical Scenario | Typical Status |
|---|---|---:|
| `ServerWebInputException` | Invalid request input | 400 |
| `WebExchangeBindException` | Binding or validation failure | 400 |
| `HandlerMethodValidationException` | Method validation failure | 400 or per error context |
| `MethodNotAllowedException` | Unsupported HTTP method | 405 |
| `NotAcceptableStatusException` | No representation matching `Accept` | 406 |
| `UnsupportedMediaTypeStatusException` | Unsupported `Content-Type` | 415 |
| `MissingRequestValueException` | Missing required query/header/cookie/path value | 400 |
| `NoResourceFoundException` | Static resource not found | 404 |

The list and details may change across Spring versions. Check the exact exceptions in your project's version before depending on a specific status or message code.

A helpful benefit is that these framework exceptions already carry their corresponding status and ProblemDetail. Applications do not have to catch each one individually and rewrite arbitrary JSON.

## 7. Error-Handling Layers in Spring WebFlux

WebFlux provides multiple extension points; choose based on where the exception originates.

### 7.1. `@ExceptionHandler` and `@RestControllerAdvice`

This is a convenient choice for errors inside annotated controllers:

```java
@RestControllerAdvice
class ApiExceptionAdvice {

    @ExceptionHandler(OrderConflictException.class)
    ResponseEntity<ProblemDetail> handleOrderConflict(
            OrderConflictException exception,
            ServerWebExchange exchange) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT,
                "The order cannot be changed in its current state"
        );

        problem.setType(URI.create(
                "https://api.example.com/problems/order-conflict"
        ));
        problem.setTitle("Order conflict");
        problem.setInstance(
                URI.create(exchange.getRequest().getPath().value())
        );
        problem.setProperty("code", "ORDER_CONFLICT");

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .contentType(MediaType.APPLICATION_PROBLEM_JSON)
                .body(problem);
    }
}
```

This is standalone illustrative code for a business exception. `@RestControllerAdvice` applies the handler to controllers discovered via component scanning. Returning `ResponseEntity<ProblemDetail>` lets you specify status, headers, and body together.

If returning only `ProblemDetail`, Spring can infer the HTTP status from `problem.status`; use `ResponseEntity` when you want explicit control over status and headers.

### 7.2. `ResponseEntityExceptionHandler`

Spring WebFlux provides the class:

```java
org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler
```

This class is a convenient base class for `@ControllerAdvice` that handles built-in WebFlux exceptions and `ErrorResponseException` while rendering Problem Details bodies.

It can be extended:

```java
@RestControllerAdvice
class GlobalApiExceptionHandler
        extends ResponseEntityExceptionHandler {
    // Specific exception-handling hooks can be overridden
    // or handlers for business exceptions can be added.
}
```

Hooks such as `handleExceptionInternal(...)` and `createResponseEntity(...)` allow customizing general responses or the final `ResponseEntity` creation step. Exact signatures and hooks should be checked against the Javadoc for your Spring version.

Use this base class when you want consistent handling for framework exceptions. Avoid creating multiple `@ControllerAdvice` classes handling the same exception without specifying order.

### 7.3. Enabling Problem Details Automatically in Spring Boot

With Spring Boot WebFlux, Problem Details support for built-in exceptions can be enabled with:

```properties
spring.webflux.problemdetails.enabled=true
```

When enabled, Boot configures `ResponseEntityExceptionHandler` to handle built-in WebFlux exceptions and `ErrorResponseException` with problem responses.

If you want to customize how a specific built-in exception is handled, pay attention to `@ControllerAdvice` ordering. Your custom handler needs an appropriate priority relative to Boot's auto-configured advice. Do not accidentally register two handlers at the same priority for the same exception.

Enabling the property does not mean every error at every layer of the application automatically gets your desired body. Errors in filters, functional handlers, or at the server layer may require extension points in the WebFlux handler chain or Boot's error handler.

### 7.4. `WebExceptionHandler`

`WebExceptionHandler` handles exceptions in the WebFlux `WebHandler` chain, including errors from filters and the target handler. It is useful when you need to handle errors below controller advice.

Spring provides `ResponseStatusExceptionHandler` to map `ResponseStatusException` to a status. `WebFluxResponseStatusExceptionHandler` also recognizes `@ResponseStatus` on exceptions. Those handlers focus on status; if you need a uniform `ProblemDetail` body for all errors at this layer, implement the corresponding response body rendering.

### 7.5. `ErrorWebExceptionHandler` in Spring Boot

Spring Boot provides `ErrorWebExceptionHandler` and the base class `AbstractErrorWebExceptionHandler` to customize server-layer errors in functional style. This is a lower-level extension point than controller advice.

Use it only when server-wide error handling control is needed, such as errors outside DispatcherHandler or custom routing. For ordinary annotated controller business errors, `@RestControllerAdvice`/`ResponseEntityExceptionHandler` is usually simpler.

Do not let two layers write a response body for the same error. Once a response has committed, handlers cannot change the status or write a second error response.

## 8. Standardizing Business Exceptions

A large API should define a stable error catalog instead of letting each service pick statuses and messages ad hoc.

Example:

| Error Code | HTTP Status | `type` |
|---|---:|---|
| `ORDER_NOT_FOUND` | 404 | `/problems/order-not-found` |
| `ORDER_CONFLICT` | 409 | `/problems/order-conflict` |
| `INVALID_QUANTITY` | 400 | `/problems/invalid-quantity` |
| `PAYMENT_REQUIRED` | 402 or agreed business status | `/problems/payment-required` |
| `RATE_LIMITED` | 429 | `/problems/rate-limited` |
| `INTERNAL_ERROR` | 500 | `/problems/internal-error` |

Statuses must follow HTTP semantics and the API contract. Do not use `200 OK` for errors just to include a `"success": false` field in the response body.

A business exception can encapsulate the mapping:

```java
final class OrderNotFoundException extends ErrorResponseException {

    OrderNotFoundException(long orderId) {
        super(
                HttpStatus.NOT_FOUND,
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.NOT_FOUND,
                        "No order exists with id " + orderId
                ),
                null
        );

        setType(URI.create(
                "https://api.example.com/problems/order-not-found"
        ));
        setTitle("Order not found");
        getBody().setProperty("code", "ORDER_NOT_FOUND");
        getBody().setProperty("orderId", orderId);
    }
}
```

The service can emit this exception:

```java
Mono<Order> findOrder(long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)
            ));
}
```

The service does not need to know about `ResponseEntity`, JSON serialization, or controller advice. The exception carries HTTP metadata; the web layer handles rendering it.

An important rule: put only safe data into responses. If `orderId` is a public identifier, adding it is fine; if a value is internal or sensitive, use only a generic error code.

## 9. Validation Errors: Returning Structured Errors

Validation typically arises from:

- `@Valid` on request bodies.
- `@Validated` and method validation.
- Bean Validation annotations such as `@NotBlank`, `@Positive`, `@Email`.
- Custom validators.

DTO example:

```java
public record CreateOrderRequest(
        @NotBlank String product,
        @Positive int quantity
) {}
```

Controller:

```java
@PostMapping("/orders")
Mono<OrderView> create(
        @Valid @RequestBody Mono<CreateOrderRequest> request) {

    return request.flatMap(orderService::create);
}
```

In WebFlux, binding/validation errors may be represented via `WebExchangeBindException` or `HandlerMethodValidationException` depending on the declaration and validation kind. These are `ErrorResponse` exceptions that Problem Details support can handle.

Validation bodies should present the error list as a structured extension:

```json
{
  "type": "https://api.example.com/problems/validation-failed",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid",
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "quantity",
      "code": "Positive",
      "message": "must be greater than zero"
    }
  ]
}
```

Keep field names, validation codes, and messages safe. Do not return `rejectedValue` by default because that value may contain passwords, tokens, or personal data.

If you need a custom validation error format, customize `ResponseEntityExceptionHandler`'s handler or handle `WebExchangeBindException` in `@ExceptionHandler`. Ensure all errors still use status 400 and the same extension schema.

## 10. Internationalization with `MessageSource`

An API can return Vietnamese or English messages depending on locale. `ErrorResponse` provides message codes for `type`, `title`, `detail`, and arguments for detail. `ResponseEntityExceptionHandler` can resolve those codes via Spring's `MessageSource`.

Default code patterns look like:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.detail.<fully-qualified-exception-class>
```

Suffixes can be added for exceptions with multiple message variants.

Example `messages.properties` file:

```properties
problemDetail.title.com.example.OrderNotFoundException=Order not found
problemDetail.detail.com.example.OrderNotFoundException=No order exists with id {0}
```

File `messages_vi.properties`:

```properties
problemDetail.title.com.example.OrderNotFoundException=Không tìm thấy đơn hàng
problemDetail.detail.com.example.OrderNotFoundException=Không tồn tại đơn hàng có mã {0}
```

The exception name must match the real fully qualified class name in the project. If `ErrorResponseException`'s constructor accepts a detail message code and arguments, they can pass data for resolving the detail.

Do not use localized messages as machine-readable error codes. Clients should rely on `type` or the extension `code`; `title` and `detail` are presentation text that can vary by locale.

## 11. Security and Quality of Error Responses

A good error response gives clients enough information to fix a request or decide the next step without revealing how the system works internally.

You should:

- Use stable `type` URIs and machine-readable `code` values.
- Choose semantically accurate HTTP statuses.
- Write short, specific, actionable `detail` messages.
- Include `instance` or correlation IDs to aid troubleshooting.
- Return structured validation errors.
- Keep stack traces, SQL, hostnames, filesystem paths, and sensitive causes in internal logs.
- Distinguish client errors (`4xx`) from server errors (`5xx`).
- Never turn every exception into 400 or 200.
- Never send authorization details or personal data in extensions.
- Never let third-party library exception messages pass straight to clients.

Unsafe example:

```json
{
  "status": 500,
  "detail": "org.postgresql.util.PSQLException: password authentication failed for user ..."
}
```

Safer example:

```json
{
  "type": "https://api.example.com/problems/internal-error",
  "title": "Internal server error",
  "status": 500,
  "detail": "The request could not be completed",
  "code": "INTERNAL_ERROR",
  "traceId": "req-8f21"
}
```

Full technical details can still be recorded in server logs under the trace ID with proper access controls and retention policies.

## 12. Reading Problem Details on the Client with WebClient

Clients should not rely solely on inspecting message strings. They can inspect status, headers, and the `ProblemDetail` body.

Example:

```java
Mono<OrderView> result = webClient.get()
        .uri("/orders/{id}", 42)
        .retrieve()
        .bodyToMono(OrderView.class)
        .onErrorResume(WebClientResponseException.class, ex -> {
            ProblemDetail problem =
                    ex.getResponseBodyAs(ProblemDetail.class);

            if (problem != null
                    && "ORDER_NOT_FOUND".equals(
                            problem.getProperties() == null
                                    ? null
                                    : problem.getProperties().get("code"))) {
                return Mono.empty();
            }

            return Mono.error(ex);
        });
```

This is a client-side illustrative snippet. It requires importing `WebClientResponseException` and `ProblemDetail`. When the Jackson mixin unwraps extension members, `getProperties()` remains the API to access the map after deserialization. Verify how your client codec configures deserialization of extension fields in your Spring version.

In production code, do not turn every 404 into empty if 404 can carry different meanings. Check the stable `type` or `code` to distinguish problem types. For unhandled errors, preserve the exception or map it to a client-side domain error.

## 13. Runnable Java 17+ Example with Spring Boot WebFlux

The example below builds an API with:

- `GET /orders/42`: returns an order normally.
- `GET /orders/404`: emits `OrderNotFoundException`, returning RFC 9457 Problem Details.
- `GET /orders/0`: emits `ResponseStatusException` with status 400.
- Problem Details enabled for built-in exceptions via Spring Boot configuration.

### Project Structure

```text
problem-details-webflux/
├── pom.xml
├── src/main/resources/application.properties
└── src/main/java/demo/Main.java
```

### File `pom.xml`

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
    <artifactId>problem-details-webflux</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### File `src/main/resources/application.properties`

```properties
server.port=8080
spring.webflux.problemdetails.enabled=true
```

### File `src/main/java/demo/Main.java`

```java
package demo;

import java.net.URI;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.ErrorResponseException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }
}

@RestController
@RequestMapping("/orders")
class OrderController {

    @GetMapping("/{id}")
    Mono<OrderView> get(@PathVariable long id) {
        if (id == 0) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Order id must be positive"
            ));
        }

        if (id == 404) {
            return Mono.error(new OrderNotFoundException(id));
        }

        return Mono.just(new OrderView(id, "created"));
    }

    record OrderView(long id, String state) {}
}

final class OrderNotFoundException extends ErrorResponseException {

    OrderNotFoundException(long orderId) {
        super(
                HttpStatus.NOT_FOUND,
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.NOT_FOUND,
                        "No order exists with id " + orderId
                ),
                null
        );

        setType(URI.create(
                "https://api.example.com/problems/order-not-found"
        ));
        setTitle("Order not found");
        getBody().setProperty("code", "ORDER_NOT_FOUND");
        getBody().setProperty("orderId", orderId);
    }
}
```

Run from the project directory with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

### Successful Request

```bash
curl -i http://localhost:8080/orders/42
```

Body:

```json
{"id":42,"state":"created"}
```

### Order Not Found Request

```bash
curl -i http://localhost:8080/orders/404
```

Key parts of the response:

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{
  "type": "https://api.example.com/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order exists with id 404",
  "instance": "/orders/404",
  "code": "ORDER_NOT_FOUND",
  "orderId": 404
}
```

`instance` is populated by Spring from the request path if the body does not already have a value. Auxiliary headers such as `Date` may vary by runtime.

### Invalid ID Request

```bash
curl -i http://localhost:8080/orders/0
```

The response has status `400 Bad Request`; `ResponseStatusException` is mapped through WebFlux's error-handling mechanism. Detail content can be customized via Problem Details configuration and message sources.

**Flow explanation:**

1. Spring Boot creates the WebFlux server and controller.
2. Property `spring.webflux.problemdetails.enabled=true` enables RFC 9457 support for built-in WebFlux exceptions.
3. `OrderNotFoundException` extends `ErrorResponseException`, carrying status 404 and a `ProblemDetail` body.
4. `setType`, `setTitle`, and `setProperty` attach problem type metadata and extensions.
5. The exception is emitted via `Mono.error`; the controller does not subscribe manually.
6. WebFlux/Boot error handling renders status, headers, and the `application/problem+json` body.

The example uses static data for predictable output. In real applications, a service/repository supplies orders and the exception is emitted only when the resource is missing.

## 14. Testing with `WebTestClient`

You can verify status, media type, and extension fields without opening a TCP port:

```java
WebTestClient client = WebTestClient
        .bindToController(new OrderController())
        .build();

client.get()
        .uri("/orders/42")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo(42);

client.get()
        .uri("/orders/404")
        .exchange()
        .expectStatus().isNotFound()
        .expectHeader()
        .contentTypeCompatibleWith(MediaType.APPLICATION_PROBLEM_JSON)
        .expectBody()
        .jsonPath("$.type").isEqualTo(
                "https://api.example.com/problems/order-not-found"
        )
        .jsonPath("$.status").isEqualTo(404)
        .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND")
        .jsonPath("$.orderId").isEqualTo(404);
```

This is an illustrative test snippet requiring `spring-test` (typically included via `spring-boot-starter-test`) and importing `WebTestClient` and `MediaType`. `bindToController` tests the controller and local exception mapping; to verify Boot auto-configuration, advice ordering, codecs, and the full server error chain, write integration tests that start the application context.

You should have tests for:

- Domain errors 404/409 and extension fields.
- Built-in binding/validation errors.
- Malformed JSON and unsupported `Content-Type`.
- `Allow` header or status-specific headers.
- Different locales and message sources.
- Error responses containing no stack traces or secrets.
- Errors originating outside controllers if the application uses custom filters/functional routes.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
|---|---|---|
| Using different JSON bodies for each controller | Clients must write multiple parsers | Standardize with `ProblemDetail` |
| Body reports a different status than the HTTP response | Clients receive conflicting information | Use the same status in `ResponseEntity` and `ProblemDetail` |
| Using `detail` as the error code | Clients depend on prose wording/translations | Add a stable `type` or extension `code` |
| Including stack traces in the body | Leaks internal structure and details | Log server-side; return safe details |
| Using `ResponseStatusException` for every domain error | Lacks stable type/code/extensions | Subclass `ErrorResponseException` |
| Assuming `ProblemDetail` handles exceptions automatically | Have a body model without anything rendering the exception | Use `@ExceptionHandler`, `ResponseEntityExceptionHandler`, or an appropriate error handler |
| Enabling Boot property and expecting every error across all layers to be handled | Filter/functional/server errors may go through another layer | Identify the right error-handling layer |
| Registering multiple advice classes handling the same exception | Selected handler is unpredictable | Design clear ordering and scopes |
| Returning rejected values for all validation errors | May leak passwords/tokens | Return only safe field, code, and message |
| Using localized messages as `type` | Clients lack a stable identifier | Use stable URIs/codes, localize title/detail |
| Dropping headers from `ErrorResponse` | May lose `Allow` or required HTTP metadata | Preserve ErrorResponse headers when rendering |
| Converting every exception into 400 | Server failures are mislabeled as client errors | Classify errors by status and semantics |
| Trying to write an error response after the response committed | Cannot alter already-sent status/body | Decide status before commit; for streaming errors terminate or emit an error event |
| Naming extension fields the same as `status`, `type`, `detail` | Causes schema ambiguity | Pick distinct names like `code`, `traceId`, `errors` |
| Failing to test media type | Clients receive body with wrong content type | Test `application/problem+json` |

## 16. Error Contract Design Checklist

Before publishing an API, check:

1. Does every error have an appropriate HTTP status?
2. Does `ProblemDetail.status` match the actual status?
3. Are `type` and extension `code` stable across versions?
4. Is `title` concise and `detail` actionable?
5. Does `instance` identify the error occurrence?
6. Do extension fields share a consistent schema across endpoints?
7. Do validation errors include field/code/message without leaking sensitive rejected values?
8. Are specific `ErrorResponse` headers preserved?
9. Do framework errors and business errors share the same format?
10. Are controller, filter, functional route, and server errors handled at the right layers?
11. Does `MessageSource` support the required locales?
12. Can clients branch on `type`/`code` instead of parsing `detail`?
13. Are 4xx, 5xx, media type, and extension fields tested?
14. Are stack traces, SQL, and secrets absent from responses?

## 17. Self-Check Exercises

**Question 1.** How do `ProblemDetail` and `ErrorResponse` differ?

**Answer:** `ProblemDetail` represents the RFC 9457 body; `ErrorResponse` describes the entire HTTP error including status, headers, and that body.

**Question 2.** What is the role of `ErrorResponseException`?

**Answer:** It is a runtime exception implementing `ErrorResponse`, used directly or as a base class for specialized exceptions.

**Question 3.** How is `ResponseStatusException` related to `ErrorResponseException`?

**Answer:** It is a subclass accepting status and reason; by default, reason maps to `ProblemDetail.detail`.

**Question 4.** Why is an extension field `code` needed when `detail` already exists?

**Answer:** `detail` is a human-readable explanation that may be localized; `code` is a stable identifier for client logic.

**Question 5.** Can `ProblemDetail.status` be 404 while the HTTP response is 200?

**Answer:** It should not be. The status in the body must match the actual HTTP status.

**Question 6.** To standardize built-in WebFlux exceptions in Spring Boot, which property must be enabled?

**Answer:** `spring.webflux.problemdetails.enabled=true`.

**Question 7.** Which package does WebFlux's `ResponseEntityExceptionHandler` live in?

**Answer:** `org.springframework.web.reactive.result.method.annotation`, distinct from Spring MVC's package.

**Question 8.** Do errors originating in a WebFilter necessarily pass through `@RestControllerAdvice`?

**Answer:** No. They may require `WebExceptionHandler` or Spring Boot WebFlux-layer error handling.

**Question 9.** Should stack traces be returned in `ProblemDetail.detail`?

**Answer:** No. Return safe information and use a trace ID to look up internal logs.

**Question 10.** When validation fails, what should be returned so clients can handle it?

**Answer:** Status 400, a stable problem type/code, and a structured list of errors by field/code/message; avoid including sensitive user input values.

## 18. Rules of Application

- Use `ProblemDetail` to represent RFC 9457 error bodies.
- Use `ErrorResponse` to bundle status, headers, and body into one contract.
- Use `ErrorResponseException` or `ResponseStatusException` so exceptions carry HTTP metadata.
- Subclass `ErrorResponseException` for business errors needing stable `type`, `code`, and extensions.
- Use `@RestControllerAdvice`/`ResponseEntityExceptionHandler` for annotated controllers; use `WebExceptionHandler` or `ErrorWebExceptionHandler` when errors occur at lower layers.
- Enable `spring.webflux.problemdetails.enabled=true` if you want Boot to configure Problem Details for built-in WebFlux exceptions.
- Standardize validation errors, message codes, and extension fields.
- Never expose stack traces, SQL, tokens, or personal data.
- Test status, headers, `application/problem+json`, and the schema clients actually receive.

**Key Takeaways:** `ProblemDetail` is the error content; `ErrorResponse` is the HTTP contract; `ErrorResponseException` attaches that contract to an exception. Spring WebFlux can standardize framework and business errors into RFC 9457, helping clients receive consistent statuses, error codes, and actionable details.

## 19. Official References

- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457)
- [Spring Framework — Error Responses in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.1 — `ProblemDetail` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.13/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework 6.1 — `ErrorResponse` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework 6.1 — `ErrorResponseException` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/ErrorResponseException.html)
- [Spring Framework 6.1 — WebFlux `ResponseEntityExceptionHandler` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — Reactive exception handling](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html)
- [Spring Boot — Reactive Web Applications and Problem Details](https://docs.spring.io/spring-boot/reference/web/reactive.html)
