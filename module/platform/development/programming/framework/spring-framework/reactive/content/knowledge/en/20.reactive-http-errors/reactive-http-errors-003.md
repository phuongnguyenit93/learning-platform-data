# @ExceptionHandler, @ControllerAdvice, and Error-Catching Scope

**Module:** Spring Framework – reactive  
**Parent topic:** HTTP Errors

## Learning Objectives

After this lesson, you will be able to:

1. Explain how Spring WebFlux turns exceptions raised in a controller or reactive publisher into an HTTP response.
2. Use `@ExceptionHandler` inside a controller for local error handling.
3. Use `@ControllerAdvice` and `@RestControllerAdvice` for shared error handling, and restrict scope by package, annotation, or controller type.
4. Control advice ordering with `@Order` and understand how Spring selects a matching handler across the exception/cause chain.
5. Return `ResponseEntity`, `ProblemDetail`, or reactive return types with consistent statuses and error bodies.
6. Distinguish errors from controllers, WebFilters, functional endpoints, codecs, and Spring Security to pick the right handling boundary.
7. Test business errors, input errors, and unexpected failures with `WebTestClient` without leaking internal information.

## 1. How Does an Exception Become an HTTP Response?

A WebFlux request passes through the server adapter, WebFilter chain, handler mapping, and controller. When a controller returns `Mono<T>` or `Flux<T>`, processing continues in the reactive pipeline. If the pipeline emits `onError`, Spring can route that exception into the annotated controller exception-handling mechanism.

`@ExceptionHandler` marks a method capable of handling specific exception types. The method can reside inside the controller itself or inside a shared advice bean. After selecting the method, Spring processes its return value through the normal return value handler mechanism to produce a response.

```text
HTTP request
     |
     v
WebFilter chain
     |
     v
Controller method
     |
     +---- publisher succeeds ----> encode body ----> HTTP response
     |
     +---- throw exception / onError
                    |
                    v
       Exception handler resolution
                    |
           +--------+--------+
           |                 |
           v                 v
   @ExceptionHandler    ControllerAdvice
     in controller         by @Order
           |                 |
           +--------+--------+
                    |
                    v
        ResponseEntity / ProblemDetail
                    |
                    v
             HTTP error response
```

Two failure timings must be distinguished:

- **Synchronous exception:** the controller method throws an exception immediately when invoked, before returning a publisher.
- **Reactive error:** the method returns a publisher, but the publisher emits `onError` when consumed.

Example of a reactive error:

```java
@GetMapping("/orders/{id}")
public Mono<Order> find(@PathVariable long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
```

The exception does not have to be thrown using `throw` inside the controller. When the publisher emits an error, WebFlux can still route the error to the controller/advice exception handler. The key requirement is that the publisher belongs to the request lifecycle and is consumed by the framework.

Do not call `subscribe()` separately inside a controller to run work and then return a different response. A detached subscription removes the error from the request pipeline; `@ExceptionHandler` cannot handle errors detached from that lifecycle.

## 2. @ExceptionHandler in a Controller: Local Handling

`@ExceptionHandler` can be placed on a method in the same controller as the endpoint. That method handles exceptions originating from handler methods in that corresponding controller.

```java
@RestController
@RequestMapping("/exports")
public class ExportController {

    @GetMapping("/{id}")
    public Mono<String> get(@PathVariable long id) {
        if (id == 0) {
            return Mono.error(new ExportLockedException(id));
        }
        return Mono.just("export-" + id);
    }

    @ExceptionHandler(ExportLockedException.class)
    public ResponseEntity<ApiError> handleLocked(
            ExportLockedException exception) {

        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(new ApiError(
                        "EXPORT_LOCKED",
                        "Export is currently locked"));
    }

    public record ApiError(String code, String message) {}
}
```

This is a **controller snippet**; `ExportLockedException` is an application-defined business exception. When `GET /exports/0` emits an error, `handleLocked` in the same controller can convert the error into HTTP 409 Conflict.

Local handlers suit rules that are meaningful only within a single controller. For example, an export controller may handle `ExportLockedException` in a specific way that other controllers do not need to know about.

If multiple controllers must repeat the same exception-to-response conversion, the code becomes scattered. When a rule is truly shared, move it into a controller advice.

### 2.1. One Method Handling Multiple Exceptions

`@ExceptionHandler` accepts one or more exception classes:

```java
@ExceptionHandler({
        InvalidOrderException.class,
        IllegalArgumentException.class
})
public ResponseEntity<ApiError> handleInvalid(Exception exception) {
    return ResponseEntity.badRequest()
            .body(new ApiError(
                    "INVALID_REQUEST",
                    "Request parameters are invalid"));
}
```

If classes are not declared in the annotation, Spring can infer the exception type from the method's exception parameter. Explicitly declaring the error types usually helps readers immediately see the handling scope.

Do not group exceptions with different semantics into one method just to save lines. Authentication errors may be 401/403, missing resources 404, conflicting data 409, and internal errors 500.

### 2.2. Exceptions in the Cause Chain

An exception may wrap another exception:

```java
throw new OrderProcessingException(
        "Could not load order",
        new OrderNotFoundException(orderId));
```

Spring can inspect both the thrown exception and nested causes when searching for a handler. This is useful when a service/repository wraps technical errors in business exceptions.

Do not rely on cause matching as a substitute for clear exception design. If the wrapper means a system error, catching an inner cause and returning 404 can hide context. Decide which exception represents the API's HTTP contract.

## 3. @ControllerAdvice: Shared Exception Handling

`@ControllerAdvice` is a component containing exception-handling, binder, or model-attribute methods applicable across multiple controllers. By default, advice has a broad scope covering matching annotated controllers in the application context.

```java
@ControllerAdvice
public class GlobalExceptionAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            OrderNotFoundException exception) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Order was not found"));
    }
}
```

This is an **illustrative snippet**. Methods in advice handle errors across multiple controllers without requiring each controller to declare its own handler. This helps the API keep consistent statuses, error codes, logging, and body structure.

`@ControllerAdvice` does not automatically mean every return value is a response body. If you want DTOs serialized, use `@ResponseBody` on the method/class or use `@RestControllerAdvice`.

### 3.1. @RestControllerAdvice

`@RestControllerAdvice` is a convenient combination of `@ControllerAdvice` and `@ResponseBody`. It is appropriate when advice primarily produces JSON/XML or other representations via message converters:

```java
@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            OrderNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Order was not found"));
    }
}
```

With `@RestControllerAdvice`, the body of `ResponseEntity` is encoded according to content negotiation and the appropriate codec. There is no need to manually call `response.writeWith` for standard JSON.

### 3.2. Selecting Advice Scope

You can restrict advice using selectors:

| Attribute | Selects controllers by |
| --- | --- |
| `basePackages` / `value` | Package name or subpackages. |
| `basePackageClasses` | Package containing the specified marker classes. |
| `assignableTypes` | Controllers of a specific type or subtype. |
| `annotations` | Controllers annotated with a specific annotation. |

Example applying only to controllers in the order package:

```java
@RestControllerAdvice(basePackages = "demo.orders")
public class OrderExceptionAdvice {
    // @ExceptionHandler methods
}
```

Or selecting by annotation:

```java
@RestControllerAdvice(annotations = PublicApiController.class)
public class PublicApiExceptionAdvice {
    // @ExceptionHandler methods
}
```

Selectors can be combined; when multiple selectors are specified, matching conditions are combined with OR logic. Adding selectors can therefore broaden the scope more than intended. Clearly determine which controllers will receive the advice, especially in applications organized by domain packages or API versions.

## 4. Advice Ordering and How Spring Selects a Handler

An application may have multiple advice classes: advice for business errors, validation, public APIs, or specific packages. When multiple advice classes can handle an exception, ordering becomes crucial.

`@Order` or `Ordered` determines priority order:

```java
@RestControllerAdvice
@Order(Ordered.HIGHEST_PRECEDENCE)
public class ApiSpecificAdvice {
    // Prioritized handlers
}

@RestControllerAdvice
@Order(Ordered.LOWEST_PRECEDENCE)
public class FallbackAdvice {
    // Fallback handler
}
```

Lower order values have higher priority; `HIGHEST_PRECEDENCE` is evaluated before `LOWEST_PRECEDENCE`. If undeclared, advice uses default ordering according to Spring's bean sorting mechanism.

Several useful rules:

1. Local handlers inside a controller are evaluated before global controller advice.
2. Within a single controller/advice, Spring prefers the more specific matching exception type when resolving a handler.
3. Spring may inspect the exception cause chain; a handler can match either the wrapper exception or an inner cause.
4. Across global advice classes, advice order affects which advice is evaluated first. A higher-priority advice with a handler matching a cause may be selected before a handler matching the root exception in a lower-priority advice.
5. Broad catch-all handlers such as `@ExceptionHandler(Exception.class)` should live in a low-priority fallback advice.

Do not create multiple advice classes with overlapping scopes, identical order, and overlapping handlers without a clear reason. When handler selection rules become hard to predict, narrow selectors or design a clearer exception hierarchy.

## 5. Exception Handler Parameters and Return Types

An `@ExceptionHandler` method in WebFlux can accept the exception along with needed request information:

```java
@ExceptionHandler(OrderNotFoundException.class)
public Mono<ResponseEntity<ApiError>> handle(
        OrderNotFoundException exception,
        ServerWebExchange exchange) {

    String path = exchange.getRequest().getPath().value();

    return Mono.just(ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                    "ORDER_NOT_FOUND",
                    "Order was not found at " + path)));
}
```

Common parameters include the handled exception, `ServerWebExchange`, `ServerHttpRequest`, and `ServerHttpResponse`, as well as arguments supported by WebFlux. Accept only the data you need; avoid dumping entire request bodies into logs or responses.

Return types can be:

- `ResponseEntity<T>` to control status, headers, and body.
- `Mono<ResponseEntity<T>>` when creating the error response requires reactive work.
- `ProblemDetail` or `ErrorResponse` per Spring's error response mechanism.
- A DTO or `Mono<DTO>` when a default status is appropriate.
- `Mono<Void>` when the method completes the response via supported APIs.

For typical APIs, `ResponseEntity<ApiError>` or `ProblemDetail` is easy to read. If building the error body requires calling an asynchronous service, return `Mono<...>` and compose the publisher. Never call `block()` inside an exception handler.

## 6. Designing HTTP Error Responses

### 6.1. ResponseEntity and Error DTOs

An error DTO can hold a stable code, a public message, and the request path:

```java
public record ApiError(
        String code,
        String message,
        String path) {}
```

Handler:

```java
@ExceptionHandler(OrderNotFoundException.class)
public ResponseEntity<ApiError> handleNotFound(
        OrderNotFoundException exception,
        ServerWebExchange exchange) {

    ApiError body = new ApiError(
            "ORDER_NOT_FOUND",
            "Order was not found",
            exchange.getRequest().getPath().value());

    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
}
```

`code` should be stable so clients can branch programmatically; `message` is for human readers and can be localized; `path` helps identify the failing endpoint. Never return raw exception messages if they might contain SQL, internal hostnames, tokens, or personal data.

### 6.2. ProblemDetail and RFC 9457

Spring Framework 6 supports `ProblemDetail` according to RFC 9457. This representation includes properties such as `type`, `title`, `status`, `detail`, and `instance`; applications may add extension properties.

Example:

```java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "Order was not found");

problem.setTitle("Order not found");
problem.setProperty("code", "ORDER_NOT_FOUND");

return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
```

With WebFlux, Spring can serialize `ProblemDetail` through the appropriate message converter. Use `ProblemDetail` if you want a standardized error contract; use a custom DTO if your API already has a stable schema. Do not include stack traces or exception class names in the public `detail`.

### 6.3. @ResponseStatus and ResponseStatusException

For simple errors with fixed statuses, you can attach `@ResponseStatus` to the exception class:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class CustomerNotFoundException extends RuntimeException {
    public CustomerNotFoundException(String id) {
        super("Customer was not found");
    }
}
```

Or emit `ResponseStatusException` in the pipeline:

```java
return repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Customer was not found")));
```

These two approaches are useful when only status mapping is needed. If the API needs error codes, standard bodies, logging, or shared mapping, `@RestControllerAdvice` is usually easier to manage. Control what message goes outward; internal exception messages are not always safe for clients.

## 7. Common WebFlux Exceptions

Beyond business exceptions, WebFlux and Spring Security can emit exceptions from different HTTP processing steps.

| Exception / Error Group | Typical Scenario | Typical HTTP Status |
| --- | --- | --- |
| `WebExchangeBindException` | DTO body or model attribute violates Bean Validation | 400 Bad Request |
| `HandlerMethodValidationException` | Constraint on controller method parameter/return value | 400 or 5xx depending on location and error type |
| `ServerWebInputException` | Unreadable/undecodable input or unsuitable request body | 400 Bad Request |
| `UnsupportedMediaTypeStatusException` | Unsupported Content-Type | 415 Unsupported Media Type |
| `NotAcceptableStatusException` | No representation matching Accept | 406 Not Acceptable |
| `ResponseStatusException` | Application explicitly attaches status to exception | Specified status |
| `AccessDeniedException` | User is authenticated but lacks permission | Usually 403 Forbidden |
| `AuthenticationException` | Authentication failed | Usually 401 Unauthorized |

This is an illustrative list, not a replacement for each endpoint's contract. Some exceptions are handled out of the box by the framework. When customizing built-in errors, you can extend `ResponseEntityExceptionHandler` in WebFlux package `org.springframework.web.reactive.result.method.annotation` and override the appropriate hooks for your Spring version.

Do not map every exception to 400. Decoding/validation failures are request errors; database failures, bugs, or dependency outages are usually server errors. Returning the wrong status misleads client retries and corrupts operational metrics.

### 7.1. Validation and Body-Reading Errors

For annotated controllers, DTO validation can emit `WebExchangeBindException`; method validation can emit `HandlerMethodValidationException`. Malformed JSON or values that cannot convert to Java types generally fall under input/decoding errors such as `ServerWebInputException`.

If the API wants a unified error schema, handle each exception type and convert them into the same response structure. Preserve the status and distinguish error codes so clients know whether to fix the payload, log in, request permissions, or retry later.

### 7.2. Spring Security

Authentication/authorization exceptions are typically handled inside the Spring Security WebFilter chain via authentication entry points and access denied handlers. `@ControllerAdvice` is not the sole handling point for security failures, especially when errors happen before reaching the controller.

Configure reactive security error handling at the proper security boundary. Do not use a broad catch-all advice that accidentally turns 401/403 errors into 500 or strips required challenge headers.

## 8. Practical Scope: Controllers, Filters, and Functional Endpoints

### 8.1. Which Controllers Does @ControllerAdvice Handle?

Controller advice applies to annotated controllers matching its selectors. Local handlers in a controller take precedence over advice. A global advice can apply across many controllers, yet it should not be assumed to catch every exception across the entire server.

Exceptions from a `WebFilter` can arise before the handler/controller is invoked. A filter can handle errors from the chain it wraps using `onErrorResume` if that is the filter's concern:

```java
return chain.filter(exchange)
        .onErrorResume(UpstreamUnavailableException.class, error ->
                writeServiceUnavailable(exchange));
```

This is a **WebFilter snippet**; `writeServiceUnavailable` must return `Mono<Void>` and check that the response has not yet committed. Do not call `subscribe()` in the recovery branch.

### 8.2. Functional Endpoints Do Not Use @ControllerAdvice Like Annotated Controllers

WebFlux.fn uses `RouterFunction`, `HandlerFunction`, and `ServerRequest`. It does not go through annotated controller exception handler resolution the same way `@RestController` does. Therefore, do not expect `@ExceptionHandler` inside `@RestControllerAdvice` to automatically handle every exception from a `HandlerFunction`.

For functional endpoints, you can handle errors inside the handler using `onErrorResume` or attach a `HandlerFilterFunction` to wrap handlers in the router:

```java
HandlerFilterFunction<ServerResponse, ServerResponse> errorFilter =
        (request, next) -> next.handle(request)
                .onErrorResume(OrderNotFoundException.class, error ->
                        ServerResponse.notFound().build());
```

This is an **illustrative snippet**; you must import the functional server API and attach the filter to the router using `.filter(errorFilter)`. For broader WebFlux server-level errors, you can implement `WebExceptionHandler`, which accepts `ServerWebExchange` and `Throwable` and returns `Mono<Void>`.

### 8.3. WebExceptionHandler Is a Broader Boundary

`WebExceptionHandler` participates in exception handling across the WebFlux WebHandler chain. It fits server/filter-layer errors or global error handling that also needs to cover functional endpoints. When implementing one yourself, you must:

- Check `exchange.getResponse().isCommitted()` before changing status or writing the body.
- Choose the right status and representation.
- Return the publisher that writes the response so its lifecycle is managed.
- If unable to handle the exception, propagate the error onward per the `WebExceptionHandler` contract.
- Set an appropriate order so it does not conflict with security or the default error handler.

Spring Boot WebFlux also provides server-level error handling via `ErrorWebExceptionHandler`/`DefaultErrorWebExceptionHandler`. Replace it only when you need a server-wide error contract; for annotated controller business errors, controller advice is usually simpler.

## 9. Committed Responses and Streaming Errors

A response can change its status/headers only before committing. Once the server has sent response headers or started writing the body, it cannot go back to change HTTP 200 to 500 and send a fresh JSON error body as if the response had not started.

For example, suppose a `Flux<Event>` has streamed several events and then emits `onError`. The client has already received the status and part of the body. An exception handler cannot erase the bytes already sent. For SSE or streaming protocols, if mid-stream errors must be represented, design an error event in the protocol or terminate the stream according to an agreed contract.

```java
@GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<Event> events() {
    return eventService.stream()
            .onErrorResume(error ->
                    Flux.just(Event.error("STREAM_FAILED")));
}
```

This is an **illustrative snippet**. Turning errors into events is only appropriate when the stream schema defines error events. Do not swallow errors silently or emit internal exception details to the client.

Cancellation is also not synonymous with an exception. The client may disconnect or an operator may cancel upstream; cancellation is a separate lifecycle signal and should not be automatically mapped to HTTP 500.

## 10. Runnable Spring Boot 3.3.5 Program

The example uses **Java 17+**, **Maven**, **Spring Boot 3.3.5**, and `spring-boot-starter-webflux`. The controller emits errors via a reactive publisher; `@RestControllerAdvice` converts exceptions into structured statuses and JSON bodies.

Structure:

```text
webflux-exception-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── ApiExceptionDemoApplication.java
    │   ├── OrderController.java
    │   ├── OrderExceptions.java
    │   └── ApiExceptionAdvice.java
    └── test/java/demo/
        └── OrderControllerTest.java
```

### 10.1. pom.xml

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
    <artifactId>webflux-exception-demo</artifactId>
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
```

### 10.2. ApiExceptionDemoApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ApiExceptionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiExceptionDemoApplication.class, args);
    }
}
```

### 10.3. OrderExceptions.java

```java
package demo;

class OrderNotFoundException extends RuntimeException {
    OrderNotFoundException(long id) {
        super("Order " + id + " was not found");
    }
}

class InvalidOrderIdException extends RuntimeException {
    InvalidOrderIdException(long id) {
        super("Order id must be positive: " + id);
    }
}
```

The two package-private exceptions share the same package as the controller and advice, so separate public classes are unnecessary for each exception.

### 10.4. OrderController.java

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    public record Order(long id, String status) {}

    @GetMapping("/{id}")
    public Mono<Order> find(@PathVariable long id) {
        if (id <= 0) {
            return Mono.error(new InvalidOrderIdException(id));
        }

        if (id == 404) {
            return Mono.error(new OrderNotFoundException(id));
        }

        if (id == 500) {
            return Mono.error(
                    new IllegalStateException("simulated internal failure"));
        }

        return Mono.just(new Order(id, "READY"));
    }
}
```

Error branches are emitted as `Mono.error` to simulate reactive error signals. ID 404 represents a missing order; ID 0 or negative represents invalid input; ID 500 simulates an unexpected error to test the 500 fallback.

### 10.5. ApiExceptionAdvice.java

```java
package demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

@RestControllerAdvice
public class ApiExceptionAdvice {
    private static final Logger log =
            LoggerFactory.getLogger(ApiExceptionAdvice.class);

    public record ApiError(
            String code,
            String message,
            String path) {}

    @ExceptionHandler(OrderNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            OrderNotFoundException exception,
            ServerWebExchange exchange) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        "ORDER_NOT_FOUND",
                        "Order was not found",
                        exchange.getRequest().getPath().value()));
    }

    @ExceptionHandler(InvalidOrderIdException.class)
    public ResponseEntity<ApiError> invalidId(
            InvalidOrderIdException exception,
            ServerWebExchange exchange) {

        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_ORDER_ID",
                        "Order id must be positive",
                        exchange.getRequest().getPath().value()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiError> unexpected(
            Exception exception,
            ServerWebExchange exchange) {

        String path = exchange.getRequest().getPath().value();
        log.error("Unhandled request failure at {}", path, exception);

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ApiError(
                        "INTERNAL_ERROR",
                        "An unexpected error occurred",
                        path));
    }
}
```

The advice has two specialized handlers and one fallback handler. The response does not return internal messages from the catch-all exception; full details are written only to the server log. Real applications should add a request/correlation ID and appropriate logging rules for tracing.

### 10.6. Trying It Out

In the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

Successful request:

```bash
curl -i http://localhost:8080/api/orders/12
```

Result is HTTP **200 OK**:

```json
{
  "id": 12,
  "status": "READY"
}
```

Missing order:

```bash
curl -i http://localhost:8080/api/orders/404
```

Result is HTTP **404 Not Found**:

```json
{
  "code": "ORDER_NOT_FOUND",
  "message": "Order was not found",
  "path": "/api/orders/404"
}
```

Invalid ID:

```bash
curl -i http://localhost:8080/api/orders/0
```

Result is HTTP **400 Bad Request**:

```json
{
  "code": "INVALID_ORDER_ID",
  "message": "Order id must be positive",
  "path": "/api/orders/0"
}
```

Unexpected error:

```bash
curl -i http://localhost:8080/api/orders/500
```

Result is HTTP **500 Internal Server Error**:

```json
{
  "code": "INTERNAL_ERROR",
  "message": "An unexpected error occurred",
  "path": "/api/orders/500"
}
```

The server log contains the simulated error's stack trace; the client receives only the controlled error contract.

## 11. Testing with WebTestClient

`WebTestClient` verifies the status and body received by an HTTP client, confirming that the advice is invoked when a reactive publisher emits an error.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OrderControllerTest {
    @Autowired
    WebTestClient client;

    @Test
    void successReturnsOrder() {
        client.get()
                .uri("/api/orders/12")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(12)
                .jsonPath("$.status").isEqualTo("READY");
    }

    @Test
    void missingOrderReturnsNotFound() {
        client.get()
                .uri("/api/orders/404")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("ORDER_NOT_FOUND")
                .jsonPath("$.path").isEqualTo("/api/orders/404");
    }

    @Test
    void invalidIdReturnsBadRequest() {
        client.get()
                .uri("/api/orders/0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_ORDER_ID");
    }

    @Test
    void unexpectedFailureDoesNotExposeInternalMessage() {
        client.get()
                .uri("/api/orders/500")
                .exchange()
                .expectStatus().is5xxServerError()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INTERNAL_ERROR")
                .jsonPath("$.message")
                    .isEqualTo("An unexpected error occurred");
    }
}
```

Run tests:

```bash
mvn test
```

The four tests verify the success response, 404 error, 400 error, and 500 fallback. Tests focus on the HTTP contract rather than calling advice methods directly.

## 12. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Placing `@ExceptionHandler` in controller A and expecting it to handle controller B | Local handlers only bind to their owning controller | Use `@ControllerAdvice`/`@RestControllerAdvice` if shared handling is needed. |
| Using `@ControllerAdvice` but forgetting `@ResponseBody` | DTO may be resolved via normal view/controller semantics | Use `@RestControllerAdvice` or add `@ResponseBody`. |
| Assuming advice catches every exception across the entire server by default | Filter, security, or functional route errors may occur outside controller handler resolution | Pick the right boundary: WebFilter, security handler, HandlerFilterFunction, or WebExceptionHandler. |
| Creating multiple advice classes with overlapping scopes and no declared order | Selected handler is hard to predict | Narrow selectors and use explicit `@Order`. |
| Placing the `Exception.class` handler in a high-priority advice | Can shadow specialized handlers in other advice classes | Keep the catch-all fallback at low priority. |
| Catching only the root exception and ignoring wrappers/causes | Wrapped errors may miss the intended handler | Design clear exception chains and inspect cause matching. |
| Mapping every exception to HTTP 400 | Server failures are treated as client errors | Distinguish 4xx and 5xx by cause. |
| Returning `exception.getMessage()` for every error | May expose SQL, hosts, tokens, or internal details | Use safe public messages and log details server-side. |
| Calling `block()` inside an exception handler | Blocks the event loop | Return/compose `Mono` or already-available data. |
| Calling `subscribe()` to log or send a response | Detaches the error from the request lifecycle | Use `doOnError` for side effects or `onErrorResume` to recover. |
| Using `@RestControllerAdvice` to catch errors from all functional endpoints | Functional routes do not go through annotated controller exception resolution | Handle in handlers/filters or `WebExceptionHandler`. |
| Changing status after the response commits | Client already received the old status/headers | Handle errors before commit or define an error event for streams. |
| Swallowing exceptions and returning 200 | Client thinks the operation succeeded | Only recover when a valid outcome and status exist. |
| Catching security exceptions in advice while bypassing the security chain | May lose challenge statuses/headers or ordering | Configure reactive authentication entry point/access denied handlers. |
| Combining validation, decoding, and system errors into one code | Clients do not know how to fix requests or whether to retry | Keep distinct error codes per error category. |
| Logging the same exception at every layer | Duplicate logs and harder tracing | Pick one boundary responsible for logging and attach a correlation ID. |

## 13. Self-Check Questions

**Question 1.** What scope does an `@ExceptionHandler` placed inside a controller handle?  
**Answer:** It handles exceptions from handler methods belonging to that controller. To share across multiple controllers, use controller advice.

**Question 2.** How do `@ControllerAdvice` and `@RestControllerAdvice` differ?  
**Answer:** `@RestControllerAdvice` combines `@ControllerAdvice` and `@ResponseBody`, making it suitable for serialized error response bodies.

**Question 3.** Can advice be restricted to just one package?  
**Answer:** Yes, using `basePackages`/`value`; you can also select by marker-class packages, controller types, or annotations.

**Question 4.** What does `@Order(Ordered.HIGHEST_PRECEDENCE)` mean?  
**Answer:** Higher-priority advice is evaluated before lower-order advice; smaller order values have higher priority.

**Question 5.** If a controller returns `Mono.error(...)`, can `@ExceptionHandler` handle it?  
**Answer:** Yes, provided the reactive error belongs to the annotated controller's request lifecycle and the exception matches the handler.

**Question 6.** Why should `@ExceptionHandler(Exception.class)` not be placed in a high-priority advice?  
**Answer:** A catch-all handler may intercept errors before specialized advice, losing specific statuses and error contracts.

**Question 7.** What is `ProblemDetail` used for?  
**Answer:** It represents HTTP errors per RFC 9457 with standard fields such as type, title, status, detail, and instance, and can be extended with custom properties.

**Question 8.** Does `@ControllerAdvice` automatically catch errors from a `WebFilter`?  
**Answer:** You should not rely on it. Filters run at a boundary before/outside annotated controllers; use reactive filter error handling or an appropriate WebExceptionHandler.

**Question 9.** Are functional endpoints automatically handled by `@ExceptionHandler` in controller advice?  
**Answer:** Not through the annotated controller mechanism. Use `onErrorResume`, `HandlerFilterFunction`, or `WebExceptionHandler`.

**Question 10.** What happens if a streaming Flux emits an error after the response has committed?  
**Answer:** Already-sent status/headers cannot be changed, nor can the body be replaced with a new JSON error response. The streaming protocol must define error events or how the stream ends.

## Key Takeaways

- `@ExceptionHandler` in a controller handles local errors; `@ControllerAdvice`/`@RestControllerAdvice` share handling across matching annotated controllers.
- `@RestControllerAdvice` applies response body semantics automatically; use selectors to limit by package, controller type, or annotation.
- `@Order` controls global advice ordering. Local handlers are evaluated first; specific exception types and the cause chain affect selection.
- Reactive errors from `Mono`/`Flux` can still reach exception handlers as long as the publisher belongs to the request lifecycle; never call `subscribe()` or `block()`.
- Use `ResponseEntity` or `ProblemDetail` to return consistent statuses/bodies. Do not expose internal exception messages or stack traces.
- Controller advice targets annotated controllers. Functional endpoints, WebFilters, and Spring Security have their own handling boundaries; errors after response commit cannot alter the already-sent status.

### References

1. [Spring Framework – WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html): exception handling, `@ExceptionHandler`, controller advice, and RFC 9457.
2. [Spring Framework – @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-advice.html): advice scope, selectors, ordering, and exception matching.
3. [Spring Framework – WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): `HandlerFunction`, router filters, and functional error handling.
4. [Spring Framework – WebExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebExceptionHandler.html): exception handling boundary in the WebFlux WebHandler chain.
5. [Spring Framework – ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/reactive/result/method/annotation/ResponseEntityExceptionHandler.html): built-in exception handling for annotated WebFlux controllers.
6. [RFC 9457 – Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): standardized HTTP error structure.
7. [Spring Security – Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html): handling authentication and access denied in the reactive security chain.
