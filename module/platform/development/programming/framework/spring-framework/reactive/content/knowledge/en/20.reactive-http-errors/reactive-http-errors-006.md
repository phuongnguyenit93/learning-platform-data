# Customizing ResponseEntityExceptionHandler

**Context:** Spring Framework Reactive → **HTTP Errors**.

In Spring WebFlux, errors can arise while reading requests, decoding bodies, binding data, validating parameters, running controllers, or calling services. An API needs to translate those errors into consistent HTTP responses: the right status, appropriate headers, and a client-friendly body.

`ResponseEntityExceptionHandler` is a convenient base class for a `@ControllerAdvice` in **WebFlux annotated controllers**. It handles many exceptions raised by Spring WebFlux and returns a `ResponseEntity` formatted according to **Problem Details for HTTP APIs (RFC 9457)**. You can customize individual exceptions, shared handling logic, or the final response creation step.

Main extension points:

- Override `handleWebExchangeBindException(...)` or a specific `handle...Exception(...)` when you want to change how a Spring error type is handled.
- Override `handleExceptionInternal(...)` to apply a shared policy across exceptions handled by the base class.
- Override `createResponseEntity(...)` to add or adjust the body, headers, or status at the final step.
- Add `@ExceptionHandler` methods for application-specific exceptions, such as business state conflicts.

WebFlux methods return `Mono<ResponseEntity<Object>>`. This is a reactive API; do not use Spring MVC's synchronous signatures.

## 1. Position in WebFlux

In the annotated controller model, a request passes through the web handler chain, is mapped to a controller, and the framework handles exceptions raised along the way:

```text
HTTP request
    |
    v
WebFilter / Spring Security
    |
    v
DispatcherHandler
    |
    v
Argument resolvers / HttpMessageReader
    |
    v
Controller method
    |
    v
Application service
    |
    +---- success ----> ResponseEntity / body writer
    |
    +---- exception --> @ControllerAdvice
                           |
                           v
                    ResponseEntityExceptionHandler
                           |
                           v
                    Mono<ResponseEntity<Object>>
                           |
                           v
                    HTTP response
```

`ResponseEntityExceptionHandler` resides in the package:

```java
org.springframework.web.reactive.result.method.annotation
```

Do not confuse it with the Spring MVC class:

```java
org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler
```

Both classes share the same name but belong to two different stacks:

| Aspect | WebFlux | Spring MVC |
|---|---|---|
| Package | `org.springframework.web.reactive.result.method.annotation` | `org.springframework.web.servlet.mvc.method.annotation` |
| Request context | `ServerWebExchange` | `WebRequest` |
| Protected handler return type | `Mono<ResponseEntity<Object>>` | `ResponseEntity<Object>` |
| Execution | Reactive | Servlet MVC |

A minimal WebFlux advice:

```java
@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {
}
```

Spring registers this advice in the application context. The base class has an `@ExceptionHandler`-annotated `handleException(...)` method to handle many WebFlux exceptions. You do not need to declare a catch-all `@ExceptionHandler(Exception.class)` that duplicates it.

**Scope to remember:** this is the exception-handling mechanism for annotated controllers. Do not assume it catches every error everywhere on the server. Errors occurring in `WebFilter`, Spring Security, the server adapter, or functional `RouterFunction` endpoints may need handling at their respective layers such as `WebExceptionHandler`, `ErrorWebExceptionHandler`, or route-local `HandlerFilterFunction`.

## 2. ProblemDetail and RFC 9457

Spring Framework supports RFC 9457 to standardize error responses. `ProblemDetail` is the object describing an HTTP problem; `ErrorResponse` is the contract providing status, headers, and ProblemDetail for an exception.

Standard fields:

| Field | Meaning | Example |
|---|---|---|
| `type` | URI identifying the problem type | `https://api.example.com/problems/validation` |
| `title` | Short name of the problem | `Validation failed` |
| `status` | HTTP status | `400` |
| `detail` | Specific explanation for this occurrence | `One or more fields are invalid.` |
| `instance` | URI/path identifying the occurrence | `/orders` |

Example response:

```json
{
  "type": "https://api.example.com/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/orders",
  "errors": [
    {
      "field": "quantity",
      "message": "must be greater than 0"
    }
  ],
  "requestId": "request-123"
}
```

`errors` and `requestId` are application-added extensions. When using Jackson with Spring's configuration, `ProblemDetail.properties` is serialized as top-level properties as shown above.

`ProblemDetail` is not merely an arbitrary error DTO. Its status becomes the HTTP response status when Spring renders it; `instance` is populated by Spring from the current path if not already set. For JSON, the appropriate media type is `application/problem+json`.

### 2.1. ErrorResponse and ErrorResponseException

- `ErrorResponse` provides status, response headers, a ProblemDetail body, and message codes.
- Spring WebFlux's built-in HTTP exceptions implement `ErrorResponse`.
- `ErrorResponseException` is a convenient base implementation for application exceptions that want to carry response info under this contract.
- `ResponseEntityExceptionHandler` recognizes `ErrorResponse` exceptions and renders the corresponding body.

You do not need to manually convert every exception into `ProblemDetail`. If an exception already provides `ErrorResponse`, the base class can use its body and metadata.

## 3. Default Handled Exceptions

`handleException(Exception, ServerWebExchange)` is a public, final method annotated to handle registered WebFlux exceptions. Common groups:

| Exception | Typical Scenario | Typical Status |
|---|---|---:|
| `MethodNotAllowedException` | HTTP method not supported by route | 405 |
| `NotAcceptableStatusException` | No representation matches `Accept` | 406 |
| `UnsupportedMediaTypeStatusException` | Request `Content-Type` is unsupported | 415 |
| `MissingRequestValueException` | Missing required header, query value, or request value | 400 |
| `UnsatisfiedRequestParameterException` | Request parameter condition not met | 400 |
| `WebExchangeBindException` | Binding or request body/model validation failed | 400 |
| `HandlerMethodValidationException` | Handler method parameter/return value validation | Context-dependent |
| `ServerWebInputException` | Input unreadable/unconvertible | 400 |
| `ServerErrorException` | Server-side error | 5xx |
| `ResponseStatusException` | Exception carrying a specified status | Per exception |
| `ErrorResponseException` | Exception implementing ErrorResponse | Per exception |
| `MethodValidationException` | Method validation failed | Context-dependent |

Protected methods and specific exceptions vary by version. Consult the Javadoc for your exact Spring Framework version. Methods such as `handleHandlerMethodValidationException` and `handleMethodValidationException` were introduced in Spring 6.1 and do not exist in older versions.

**Preserve status and headers passed by Spring.** For example, 405 may need the `Allow` header; 415 may need supported media type info. When overriding a handler, do not accidentally discard those headers.

## 4. Three Key Customization Layers

`ResponseEntityExceptionHandler` provides three layers with different scopes:

| Method | When to Use | Scope |
|---|---|---|
| `handleXxxException(...)` | Need custom handling for one built-in exception | Single error type |
| `handleExceptionInternal(...)` | Need a shared policy for exceptions passing through the base class | Multiple error types |
| `createResponseEntity(...)` | Need to intervene at the final step of creating ResponseEntity | Post-processing body/headers/status |

General flow:

```text
Spring exception
      |
      v
handleXxxException(...)
      |
      v
handleExceptionInternal(...)
      |
      v
createResponseEntity(...)
      |
      v
ResponseEntity<Object>
```

Not every custom handling path is required to pass through every method in all cases. For instance, a custom `@ExceptionHandler` can return a response directly; if you want to reuse the shared pipeline, call `handleExceptionInternal` from that handler.

### 4.1. handleException Is Final

`handleException(Exception, ServerWebExchange)` is the entry point dispatching exceptions to specific methods. This method is `final`. Override the corresponding protected methods or shared hooks; do not attempt to override the entry point.

## 5. Overriding a Specific Exception

For example, to customize the body for `WebExchangeBindException` request-body validation errors:

```java
@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {

    @Override
    protected Mono<ResponseEntity<Object>>
    handleWebExchangeBindException(
            WebExchangeBindException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        status,
                        "One or more fields are invalid.");

        problem.setType(URI.create(
                "https://api.example.com/problems/validation"));
        problem.setTitle("Validation failed");

        List<Map<String, String>> errors =
                ex.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "message",
                                error.getDefaultMessage() == null
                                        ? "Invalid value"
                                        : error.getDefaultMessage()))
                        .toList();

        problem.setProperty("errors", errors);

        return handleExceptionInternal(
                ex, problem, headers, status, exchange);
    }
}
```

This snippet requires imports and a real advice class. Key points:

1. The signature is reactive: returns `Mono<ResponseEntity<Object>>`.
2. Use the `status` and `headers` passed in by the framework instead of guessing the status.
3. Read field errors from `getFieldErrors()`.
4. Include only safe fields and messages in the response; avoid including `rejectedValue` if it may contain passwords, tokens, or personal data.
5. Call `handleExceptionInternal` to preserve base-class shared processing and continue to `createResponseEntity`.

In WebFlux, body binding/validation errors typically go through `WebExchangeBindException`. Method parameter validation can emit `HandlerMethodValidationException`; if custom formatting is needed, override the corresponding method for your Spring version.

### 5.1. When Is Overriding Unnecessary?

If the default ProblemDetail body is sufficient, simply extend the base class:

```java
@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {
}
```

Spring already supplies bodies and statuses for built-in errors. Customize only when the API requires specific formats, extension fields, messages, or policies.

## 6. handleExceptionInternal: Shared Handling

WebFlux signature:

```java
protected Mono<ResponseEntity<Object>> handleExceptionInternal(
        Exception ex,
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange)
```

This method is the central shared-handling point for protected handlers. You can use it to:

- Normalize common ProblemDetail metadata.
- Log in a controlled manner by status and exception type.
- Preserve headers supplied by Spring.
- Delegate to the default implementation so the framework handles committed responses and bodies from `ErrorResponse`.

Example adding `path` to ProblemDetail:

```java
@Override
protected Mono<ResponseEntity<Object>> handleExceptionInternal(
        Exception ex,
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange) {

    if (body instanceof ProblemDetail problem) {
        problem.setProperty(
                "path",
                exchange.getRequest().getPath().value());
    }

    return super.handleExceptionInternal(
            ex, body, headers, status, exchange);
}
```

This is a snippet; keep nullability annotations if required by your project version. In current Javadoc, body and headers may be nullable. If non-ProblemDetail bodies must also be supported, do not force-cast.

The default implementation avoids creating a new response when the response has already committed; it can also extract the body from `ErrorResponse` when the passed-in body is null.

**Do not arbitrarily replace the default implementation completely.** When overriding, call `super` after adding your logic to preserve framework behavior unless you intentionally mean to alter that contract.

## 7. createResponseEntity: Final Step of Response Creation

WebFlux signature:

```java
protected Mono<ResponseEntity<Object>> createResponseEntity(
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange)
```

This is the final point to inspect or adjust the body, headers, and status before `ResponseEntity` is returned.

Example adding request ID and path to every ProblemDetail:

```java
@Override
protected Mono<ResponseEntity<Object>> createResponseEntity(
        Object body,
        HttpHeaders headers,
        HttpStatusCode status,
        ServerWebExchange exchange) {

    if (body instanceof ProblemDetail problem) {
        problem.setProperty(
                "path",
                exchange.getRequest().getPath().value());
        problem.setProperty(
                "requestId",
                exchange.getRequest().getId());
    }

    return super.createResponseEntity(
            body, headers, status, exchange);
}
```

`ServerHttpRequest.getId()` is a request identifier provided by the request abstraction; it is not automatically a distributed trace ID. If the API needs a cross-service trace ID, obtain it from the configured tracing/observation context and include only safe values in the response.

Use `createResponseEntity` for common metadata. Do not query databases or call business services here; this is the response-finalization layer.

## 8. Adding Business Exceptions with @ExceptionHandler

Built-in exceptions are already handled by the base class. Custom exceptions such as "order cannot be modified in its current state" can be declared with `@ExceptionHandler` in the same advice:

```java
@ExceptionHandler(OrderConflictException.class)
public Mono<ResponseEntity<Object>> handleOrderConflict(
        OrderConflictException ex,
        ServerWebExchange exchange) {

    ProblemDetail problem =
            ProblemDetail.forStatusAndDetail(
                    HttpStatus.CONFLICT,
                    "Order cannot be changed in its current state.");

    problem.setType(URI.create(
            "https://api.example.com/problems/order-conflict"));
    problem.setTitle("Order conflict");
    problem.setProperty("code", "ORDER_STATE_CONFLICT");

    return handleExceptionInternal(
            ex,
            problem,
            new HttpHeaders(),
            HttpStatus.CONFLICT,
            exchange);
}
```

This snippet requires the `OrderConflictException` class. Calling `handleExceptionInternal` ensures custom exceptions share the same response-creation step and common metadata. If you return `ResponseEntity` directly, you bypass this shared processing unless you invoke it yourself.

You can use `ErrorResponseException` for exceptions that want to carry status, headers, and ProblemDetail per Spring's contract. Pick a consistent strategy; avoid creating multiple overlapping handlers for the same exception.

### 8.1. Exceptions Emitted Inside a Reactive Chain

A controller can return errors from a publisher:

```java
@GetMapping("/orders/{id}")
public Mono<OrderView> getOrder(@PathVariable String id) {
    return orderService.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
```

When a publisher fails during request processing, WebFlux routes the exception to the annotated controller exception-handling mechanism. Do not call `subscribe()` inside the controller to handle errors manually; compose the publisher and return it to the framework.

## 9. Never Leak Internal Information

An error response is a public contract. A database error may contain SQL, table names, hostnames, file paths, or credentials. Never copy raw `ex.getMessage()` from arbitrary exceptions into `detail`.

| Error Category | What the Client Should Receive | What Should Only Be Logged Internally |
|---|---|---|
| Validation | Invalid fields and clear rules | Stack traces, sensitive rejected values |
| Not found | Resource does not exist | SQL queries or storage paths |
| Business conflict | Stable error code and remediation guidance | Internal state, other users' data |
| Dependency failure | Temporary service message | Hosts, credentials, internal requests |
| Unexpected 500 error | Generic message and request ID | Stack traces, exception chains, sensitive payloads |

Example of a safe 500 body:

```json
{
  "type": "https://api.example.com/problems/internal",
  "title": "Internal server error",
  "status": 500,
  "detail": "An unexpected error occurred.",
  "instance": "/orders",
  "requestId": "request-123"
}
```

Internal logs can record the stack trace linked with the same request ID. Never send stack traces or exception class names to clients as a way to debug production.

## 10. Internationalization with MessageSource

`ResponseEntityExceptionHandler` implements `MessageSourceAware`. It can resolve message codes for `type`, `title`, and `detail` of `ErrorResponse` using `MessageSource`.

Default code pattern:

```text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.detail.<fully-qualified-exception-class>
```

Example Vietnamese resource bundle:

```properties
problemDetail.title.org.springframework.web.bind.support.WebExchangeBindException=Yêu cầu không hợp lệ
problemDetail.detail.org.springframework.web.bind.support.WebExchangeBindException=Kiểm tra lại các trường trong yêu cầu.
```

An English resource bundle can provide the same message codes with different text. Locale resolution determines the appropriate message.

For exceptions that do not implement `ErrorResponse`, the protected `createProblemDetail(...)` method helps construct ProblemDetail and perform MessageSource lookup for detail. If business-specific message customization is needed, use stable message codes and controlled arguments.

### 10.1. ErrorResponse Interceptor

Spring WebFlux allows registering an `ErrorResponse` interceptor via `WebFluxConfigurer`. This is the right extension point when you want to apply a common operation across ProblemDetail responses without rewriting every exception handler. Avoid modifying the same fields simultaneously in an interceptor, advice, and response factory without clear rules.

## 11. Spring Boot: Avoiding Two Mechanisms Handling the Same Error

Spring Boot provides the property:

```properties
spring.webflux.problemdetails.enabled=true
```

This property enables auto-configuration for Problem Details and registers a handler for built-in exceptions. Once Boot registers its advice, adding another advice handling the same exceptions requires explicit ordering. Spring Boot documentation notes that the auto-configured handler has order 0; an advice intended to handle a specific exception before it must have higher precedence.

Two common approaches:

1. **Self-managed via subclass:** create a `@RestControllerAdvice` extending `ResponseEntityExceptionHandler` and configure it so no other auto-configured handler competes over the same built-in exceptions.
2. **Keep Boot auto-configuration:** use `ErrorAttributes` or a dedicated `@ControllerAdvice` for exceptions needing customization; if overriding a built-in exception, order it before Boot's handler and avoid unnecessary overlapping mappings.

Do not enable the property and simultaneously register multiple catch-all handlers without checking their order.

### 11.1. When Lower-Level Customization Than the Controller Layer Is Needed

`ResponseEntityExceptionHandler` does not replace `ErrorWebExceptionHandler`. If you need to handle errors at the broader WebFlux server layer—such as errors from the filter chain or functional routing—use `ErrorWebExceptionHandler`. Spring Boot provides `AbstractErrorWebExceptionHandler` to build fallback error handlers in functional style.

With WebFlux.fn, `HandlerFilterFunction` is a route-local filter; it does not automatically behave like `@ControllerAdvice`. Choose the right layer for errors from routes, filters, or annotated controllers.

## 12. Runnable Java 17+ Program: Validation and Business Errors

The example below uses Spring Boot 3.5.x, Spring Framework 6.2.x, WebFlux, and Bean Validation. It demonstrates:

- `@RestControllerAdvice` extending `ResponseEntityExceptionHandler`.
- Overriding `handleWebExchangeBindException` to build a validation ProblemDetail.
- Overriding `createResponseEntity` to add path and request ID.
- Adding `@ExceptionHandler` for a business exception.
- Testing status and body with `WebTestClient`.

Project structure:

```text
webflux-error-handler-demo/
├── pom.xml
└── src
    ├── main/java/demo/ErrorHandlingApplication.java
    ├── main/java/demo/OrderController.java
    ├── main/java/demo/ApiExceptionHandler.java
    ├── main/java/demo/CreateOrderRequest.java
    ├── main/java/demo/OrderView.java
    └── main/java/demo/OrderConflictException.java
    └── test/java/demo/ErrorHandlingIntegrationTest.java
```

### 12.1. pom.xml

```xml
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

    <groupId>demo</groupId>
    <artifactId>webflux-error-handler-demo</artifactId>
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
</project>
```

### 12.2. ErrorHandlingApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorHandlingApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ErrorHandlingApplication.class, args);
    }
}
```

### 12.3. CreateOrderRequest.java

```java
package demo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @Positive int quantity) {
}
```

### 12.4. OrderView.java

```java
package demo;

public record OrderView(
        String id,
        String status) {
}
```

### 12.5. OrderConflictException.java

```java
package demo;

public class OrderConflictException extends RuntimeException {

    public OrderConflictException() {
        super("Order state does not allow this operation");
    }
}
```

### 12.6. OrderController.java

```java
package demo;

import jakarta.validation.Valid;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @PostMapping
    public Mono<OrderView> create(
            @Valid @RequestBody CreateOrderRequest request) {

        if ("blocked".equals(request.customerId())) {
            return Mono.error(new OrderConflictException());
        }

        return Mono.just(
                new OrderView("order-100", "ACCEPTED"));
    }
}
```

### 12.7. ApiExceptionHandler.java

```java
package demo;

import java.net.URI;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.bind.support.WebExchangeBindException;

import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiExceptionHandler
        extends ResponseEntityExceptionHandler {

    @Override
    protected Mono<ResponseEntity<Object>>
    handleWebExchangeBindException(
            WebExchangeBindException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        status,
                        "One or more fields are invalid.");

        problem.setType(URI.create(
                "https://api.example.com/problems/validation"));
        problem.setTitle("Validation failed");

        List<Map<String, String>> errors =
                ex.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "message",
                                error.getDefaultMessage() == null
                                        ? "Invalid value"
                                        : error.getDefaultMessage()))
                        .toList();

        problem.setProperty("errors", errors);

        return handleExceptionInternal(
                ex, problem, headers, status, exchange);
    }

    @ExceptionHandler(OrderConflictException.class)
    public Mono<ResponseEntity<Object>> handleOrderConflict(
            OrderConflictException ex,
            ServerWebExchange exchange) {

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(
                        HttpStatus.CONFLICT,
                        "Order cannot be changed in its current state.");

        problem.setType(URI.create(
                "https://api.example.com/problems/order-conflict"));
        problem.setTitle("Order conflict");
        problem.setProperty("code", "ORDER_STATE_CONFLICT");

        return handleExceptionInternal(
                ex,
                problem,
                new HttpHeaders(),
                HttpStatus.CONFLICT,
                exchange);
    }

    @Override
    protected Mono<ResponseEntity<Object>> createResponseEntity(
            Object body,
            HttpHeaders headers,
            HttpStatusCode status,
            ServerWebExchange exchange) {

        if (body instanceof ProblemDetail problem) {
            problem.setProperty(
                    "path",
                    exchange.getRequest().getPath().value());
            problem.setProperty(
                    "requestId",
                    exchange.getRequest().getId());
        }

        return super.createResponseEntity(
                body, headers, status, exchange);
    }
}
```

In the code above:

- Validation errors keep the status and headers selected by Spring.
- Business conflicts are mapped to 409.
- Both pass through `handleExceptionInternal` and `createResponseEntity`, so they share consistent path/requestId metadata.
- `requestId` in the example is the request abstraction's ID, not a distributed trace ID.
- Internal exception messages and rejected values are excluded from the body.

### 12.8. ErrorHandlingIntegrationTest.java

```java
package demo;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ErrorHandlingIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void invalidBodyReturnsProblemDetail() {
        client.post()
                .uri("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "customerId", "",
                        "quantity", 0))
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Validation failed")
                .jsonPath("$.status")
                .isEqualTo(400)
                .jsonPath("$.errors")
                .exists()
                .jsonPath("$.path")
                .isEqualTo("/orders");
    }

    @Test
    void businessConflictReturns409() {
        client.post()
                .uri("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "customerId", "blocked",
                        "quantity", 1))
                .exchange()
                .expectStatus().isEqualTo(409)
                .expectBody()
                .jsonPath("$.title")
                .isEqualTo("Order conflict")
                .jsonPath("$.code")
                .isEqualTo("ORDER_STATE_CONFLICT");
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn test
```

The two tests confirm:

1. An invalid body produces HTTP 400 with Problem Details media type, title, status, errors, and path.
2. A business exception is translated into HTTP 409 with a stable error code.

These are integration tests running against the embedded WebFlux server. They verify that argument validation, advice dispatch, and response serialization work together rather than just calling protected methods directly.

## 13. Testing Essential Scenarios

A production error handler should have tests for these categories:

| Case | What to Verify |
|---|---|
| Malformed JSON | Status 400, detail does not leak parser internals |
| Field validation failure | 400 and field error list |
| Unsupported method | 405 and preserves `Allow` header |
| Unsupported media type | 415 and related headers |
| Unacceptable Accept header | 406 |
| Missing resource | 404 per contract |
| Domain conflict | 409 and stable business error code |
| Unexpected failure | 500 with generic detail, log includes correlation ID |
| Exception after response commit | Does not attempt to write a new response body |
| Client disconnect | Proper cancellation/cleanup, not turned into a fake business error |

Use `WebTestClient` to verify status, headers, and body. For pure ProblemDetail-building logic, you can unit-test separately; however, at least one integration test must go through actual WebFlux handler mapping and codecs.

Do not assert only the status. A 400 response can still violate the contract if it lacks the media type, drops required headers, or leaks internal data.

## 14. Common Mistakes

1. **Importing the Spring MVC class by mistake.** WebFlux must use package `org.springframework.web.reactive.result.method.annotation`.
2. **Overriding with a synchronous return type.** WebFlux protected handlers return `Mono<ResponseEntity<Object>>`.
3. **Trying to override `handleException`.** This method is final; override specialized protected methods or shared hooks.
4. **Creating a catch-all @ExceptionHandler overlapping the base class.** Can cause ambiguous mapping or break built-in dispatch.
5. **Dropping passed-in headers.** Can lose `Allow`, supported media types, or important HTTP metadata.
6. **Hard-coding status 400 for every error.** Keep the status passed in by the framework; validation, 404, 405, 406, 415, and server errors differ.
7. **Modifying the body in only one specialized method.** If every ProblemDetail needs path/request ID, consider `createResponseEntity`.
8. **Overriding handleExceptionInternal without calling super.** May skip committed-response handling and ErrorResponse body extraction.
9. **Returning exception.getMessage() for all errors.** May expose SQL, internal paths, tokens, or infrastructure details.
10. **Including rejectedValue in the validation body.** The value may be sensitive data; return only necessary fields and messages.
11. **Customizing status in createResponseEntity without rules.** Status must follow the API contract and matching headers.
12. **Assuming @RestControllerAdvice handles all WebFlux errors.** Filters, security, functional endpoints, and transport errors may belong to other layers.
13. **Enabling Boot Problem Details and adding overlapping advice.** Understand auto-configured handler ordering and choose one clear strategy.
14. **Confusing RFC 7807 with RFC 9457.** Spring Framework currently supports RFC 9457; use matching media types and documentation.
15. **Ignoring MessageSource.** Hard-coded messages are hard to localize; use message codes for title/detail when needed.
16. **Failing to handle errors in reactive chains.** Exceptions emitted from Mono/Flux still need to be composed and returned to the framework.
17. **Creating a new response after the stream has committed.** Already-sent status/body cannot be changed; use protocol-level errors or log/connection handling.
18. **Using advice to handle exceptions from RouterFunction without checking scope.** Functional routing has different handler/error mechanisms than annotated controllers.
19. **Logging full bodies or sensitive exception details.** Limit logs and mask data per policy.
20. **Failing to test headers and content type.** A right body with wrong headers is still a broken API response.

## 15. Design Checklist

Before customizing, determine:

- Does the application use WebFlux annotated controllers or WebFlux.fn?
- Does the exception originate in argument resolution, controller/service, filter, or server layer?
- Is this a built-in Spring exception or a business exception?
- Can default ProblemDetail behavior be used before writing a custom handler?
- Should you override a `handleXxx`, `handleExceptionInternal`, or `createResponseEntity`?
- Are original status and headers preserved?
- Does ProblemDetail have appropriate type/title/status/detail/instance?
- Are extension fields stable and free of sensitive data leaks?
- Is MessageSource/i18n or an ErrorResponse interceptor needed?
- Does Spring Boot enable `spring.webflux.problemdetails.enabled` and register another handler?
- Has the response committed yet? Can status/body still be modified?
- Are WebTestClient tests covering the embedded server, validation, custom exceptions, and headers?

**Key Takeaways:** `ResponseEntityExceptionHandler` is the reactive foundation for exception handling in annotated controllers. Override `handleXxx` to handle one error kind, `handleExceptionInternal` for shared policy, and `createResponseEntity` for final-step metadata. Use `ProblemDetail` per RFC 9457, preserve sensible statuses/headers, add safe custom fields, use `@ExceptionHandler` for business errors, and verify scope when working with WebFlux.fn, filters, or Spring Boot auto-configuration.

## References

- Spring Framework — [Error Responses in WebFlux: ProblemDetail, ErrorResponse, ResponseEntityExceptionHandler](https://docs.spring.io/spring/reference/web/webflux/ann-rest-exceptions.html).
- Spring Framework — [ResponseEntityExceptionHandler Javadoc (Reactive WebFlux)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html).
- Spring Framework — [WebFlux Controller Exception Handling](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-exceptions.html).
- Spring Boot — [Reactive Web Applications and Problem Details configuration](https://docs.spring.io/spring-boot/reference/web/reactive.html).
- IETF — [RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html).
