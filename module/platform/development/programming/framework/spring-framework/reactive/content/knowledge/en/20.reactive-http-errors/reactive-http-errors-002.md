# `ResponseStatusException` and `@ResponseStatus` in Spring WebFlux

## 1. Goal: Mapping Application Errors to the Right HTTP Status

A reactive controller typically returns `Mono<T>` or `Flux<T>`. During normal processing, Spring writes the value into an HTTP response. When the publisher emits `onError`, WebFlux needs to determine which status corresponds to that error and whether the response body should include error details.

Two common ways to associate an HTTP status with an exception are:

- **`ResponseStatusException`**: throw an exception with a specific status at runtime. Suitable when the status or reason depends on the request, for example when an item with the requested ID is not found.
- **`@ResponseStatus`**: declare a fixed status on an exception class or controller method. Suitable when an exception type always carries the same status, or an endpoint always returns a fixed success status such as 201/204.

Both are supported by WebFlux. However, setting the status and generating a JSON error body are two separate tasks. In Spring Framework 6.x, `ResponseStatusException` also implements `ErrorResponse` and provides `ProblemDetail`; to ensure an RFC 9457 body is written out, use `@ExceptionHandler`/`@ControllerAdvice` or the appropriate `ResponseEntityExceptionHandler` mechanism.

After this lesson, you will be able to:

1. Distinguish `ResponseStatusException` from `@ResponseStatus` on exception classes and on controller methods.
2. Emit exceptions properly in `Mono`/`Flux` without calling `subscribe()` or `block()`.
3. Understand the role of `WebFluxResponseStatusExceptionHandler`.
4. Return structured errors using `ProblemDetail` and `ResponseEntity`.
5. Choose the right status, preserve cause/headers, and avoid leaking internal information.
6. Test status, headers, and error bodies using `WebTestClient`.

## 2. Exception Handling Flow in WebFlux

WebFlux handles exceptions at two scopes:

- **Exceptions in annotated controllers**: `@ExceptionHandler` on a controller or `@ControllerAdvice` can handle errors raised when invoking a handler method or when the reactive return value completes with an error.
- **Exceptions in the WebHandler chain**: `WebExceptionHandler` wraps `WebFilter` instances and the target `WebHandler`, so it can handle exceptions raised in filters or the rest of the web pipeline.

WebFlux Config declares `WebFluxResponseStatusExceptionHandler`. This handler:

- Handles `ResponseStatusException` by setting the HTTP status from the exception.
- Is an extension that can look up `@ResponseStatus` on the exception class and set the corresponding status.
- Cannot change the status in the normal way if the response has already been committed; in that case, the error continues propagating.

Conceptual model:

```text
HTTP request
    |
    v
WebFilter chain
    |
    v
Controller / functional handler
    |
    v
Mono / Flux
    |
    +---- onComplete -----------------> response success
    |
    +---- onError
             |
             v
       @ExceptionHandler / @ControllerAdvice
             |
             +---- handled ----------> error response
             |
             +---- not handled
                       |
                       v
             WebExceptionHandler chain
                       |
                       v
       WebFluxResponseStatusExceptionHandler
                       |
             set HTTP status if recognized
```

The actual order depends on where the exception originates and which handling mechanism is configured. An error handled by `@ExceptionHandler` does not need to proceed to the outer status handler. If the response body has already started streaming, it is impossible to go back and change the status to 404 or 500.

## 3. `ResponseStatusException`: Dynamic Status at Runtime

`ResponseStatusException` belongs to the package:

```java
org.springframework.web.server.ResponseStatusException
```

It is a subclass of `ErrorResponseException`, implements `ErrorResponse`, and carries HTTP error response information. Common constructors:

```java
new ResponseStatusException(HttpStatus.NOT_FOUND);

new ResponseStatusException(
        HttpStatus.NOT_FOUND,
        "Item was not found");

new ResponseStatusException(
        HttpStatus.BAD_GATEWAY,
        "Inventory service failed",
        cause);
```

`HttpStatus` implements `HttpStatusCode`, so it can be used directly. The API also accepts `HttpStatusCode` to support status codes not necessarily represented by an `HttpStatus` constant.

Important information readable from the exception:

| API | Meaning |
|---|---|
| `getStatusCode()` | HTTP status to return |
| `getReason()` | Reason passed to the constructor, may be null |
| `getHeaders()` | Additional response headers |
| `getBody()` | `ProblemDetail` provided via `ErrorResponse` |
| `getCause()` | Root cause if passed to the constructor |

In Spring Framework 6.x, `reason` is used as the default `detail` content of the `ProblemDetail` provided by the exception. Even so, the exception having a `ProblemDetail` does not mean every default handling path automatically writes that body to the HTTP response. Rendering is covered in section 8.

### 3.1. Example: Looking Up a Non-Existent Resource

```java
@GetMapping("/items/{id}")
public Mono<Item> getItem(@PathVariable String id) {
    return itemService.findById(id)
            .switchIfEmpty(Mono.error(
                    new ResponseStatusException(
                            HttpStatus.NOT_FOUND,
                            "Item " + id + " was not found")));
}
```

`findById` returns `Mono.empty()` if no item exists. `switchIfEmpty` turns the empty case into an `onError` carrying `ResponseStatusException`. WebFlux can recognize the exception and map it to HTTP 404.

The key point is that the exception is emitted inside the reactive pipeline. You do not need to and should not call:

```java
// Do not do this:
itemService.findById(id).subscribe();
```

Manually subscribing detaches the work from the request lifecycle. Return the publisher from the controller and let WebFlux manage subscription, errors, and cancellation.

### 3.2. Passing the Cause When Translating Lower-Layer Errors

```java
return inventoryClient.lookup(sku)
        .onErrorMap(
                TimeoutException.class,
                error -> new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "Inventory lookup timed out",
                        error));
```

This example converts a dependency timeout into 504. The original cause is preserved for logging and diagnostics. Never put technical messages such as hostnames, SQL, tokens, or stack traces into the `reason` sent to the client.

Only convert the error types the API truly intends to represent. If every network error, configuration error, and bug is turned into 504, the system loses the ability to distinguish gateway failures from internal errors.

### 3.3. Choosing Statuses by HTTP Semantics

Some commonly used statuses:

| Status | Typical Suitable Case |
|---|---|
| 400 Bad Request | Request is invalid or cannot be parsed |
| 401 Unauthorized | Unauthenticated or invalid credentials |
| 403 Forbidden | Authenticated but lacks permission |
| 404 Not Found | Requested resource does not exist |
| 409 Conflict | Conflicts with current state |
| 410 Gone | Resource has been permanently removed per contract |
| 422 Unprocessable Content | Content is understood but fails API processing rules |
| 429 Too Many Requests | Request rate limit exceeded |
| 502 Bad Gateway | Gateway received an invalid response from upstream |
| 503 Service Unavailable | Service is temporarily unable to handle requests |
| 504 Gateway Timeout | Gateway waited too long for upstream |

These are semantic guidelines, not automatic rules enforced by Spring. Your API must keep status usage consistent.

## 4. `@ResponseStatus` on an Exception Class: Fixed Status for an Error Type

When an exception class always represents the same HTTP error, you can attach `@ResponseStatus` to the class:

```java
@ResponseStatus(HttpStatus.NOT_FOUND)
public class ItemNotFoundException extends RuntimeException {

    public ItemNotFoundException(String id) {
        super("Item " + id + " was not found");
    }
}
```

When the exception is thrown in WebFlux, `WebFluxResponseStatusExceptionHandler` can read the annotation and set status 404.

Using it in a reactive pipeline:

```java
@GetMapping("/legacy-items/{id}")
public Mono<Item> getLegacyItem(@PathVariable String id) {
    return itemService.findById(id)
            .switchIfEmpty(Mono.error(
                    new ItemNotFoundException(id)));
}
```

This approach fits small applications or exceptions used only at the web layer. However, there is an architectural decision to weigh: the annotation places HTTP semantics directly onto the exception class. If the exception belongs to the domain/application layer and is reused by batch jobs, message consumers, or another adapter, attaching `@ResponseStatus` couples the business layer to HTTP.

For systems with multiple adapters, it is usually better to keep domain exceptions independent and map them in `@ControllerAdvice` or the HTTP adapter.

### 4.1. Does `@ResponseStatus` on an Exception Automatically Create a JSON Body?

You should not treat this annotation as an error-body contract definition. In WebFlux, `WebFluxResponseStatusExceptionHandler` is responsible for resolving and setting the status for recognized exceptions. If the API needs a JSON body with `type`, `title`, `status`, `detail`, and extra fields, use `@ExceptionHandler` returning `ProblemDetail` or `ResponseEntity<ProblemDetail>`.

Do not rely on the `reason` attribute of `@ResponseStatus` as a substitute for a JSON error response. Control the body explicitly in an exception handler.

## 5. `@ResponseStatus` on a Controller Method: Fixed Status for Normal Responses

The annotation can also be placed on an HTTP-mapped method. A common case is a fixed success status:

```java
@PostMapping("/items")
@ResponseStatus(HttpStatus.CREATED)
public Mono<Item> create(@RequestBody CreateItem request) {
    return itemService.create(request);
}
```

The method returns the item and Spring writes the body normally with status 201 Created.

Another example:

```java
@DeleteMapping("/items/{id}")
@ResponseStatus(HttpStatus.NO_CONTENT)
public Mono<Void> delete(@PathVariable String id) {
    return itemService.deleteById(id);
}
```

When the publisher completes successfully, the response has status 204 No Content.

These cases illustrate the meaning of the annotation on a handler method: setting a default/fixed status for the response produced by the handler. If the status or headers must vary based on runtime results, `ResponseEntity` is usually clearer.

### 5.1. Do Not Confuse Method Status with Exception Status

| Annotation Placement | Meaning |
|---|---|
| On a controller method | Fixed status for the method's response upon successful handling |
| On an exception class | Status used when that exception is thrown and handled by WebFlux |
| On a controller class | Can be inherited by request-mapping and exception-handler methods; use caution due to its wide scope |

Do not place `@ResponseStatus(HttpStatus.CREATED)` at the controller class level if the controller has GET, POST, and DELETE endpoints with different statuses.

### 5.2. The `reason` Attribute

`@ResponseStatus` has a `reason` attribute, but it is not a mechanism for designing JSON response bodies for REST APIs. If you need structured error messages or multiple fields, use `ProblemDetail`. If you need per-outcome control over status, headers, and body, return `ResponseEntity`.

## 6. Comparing the Two Approaches

| Criterion | `ResponseStatusException` | `@ResponseStatus` |
|---|---|---|
| Declaration | Created/emitted as an exception at runtime | Static annotation |
| Status | Can be chosen per request or outcome | Fixed per method or exception class |
| Reason | Constructor accepts a dynamic reason | Fixed annotation value |
| Cause | Constructor supports passing a cause | No cause attribute |
| Response headers | Has `getHeaders()` API; subclasses can customize | Does not declare response headers |
| ProblemDetail | Has `getBody()` via `ErrorResponse` | Does not automatically provide `ProblemDetail` |
| Best suited for | Missing resource by ID, dependency timeout, errors with dynamic status | Exception class with stable status, method always returning 201/204 |
| Flexibility | Higher | Simple, static declaration |

Quick selection rules:

- Outcome is known only at runtime and status varies per request: use `ResponseStatusException`.
- An exception class always has the same status: `@ResponseStatus` on the class can be used.
- An endpoint always returns a fixed success status: use `@ResponseStatus` on the method.
- Need error bodies, headers, or dynamic status across multiple branches: use `ProblemDetail`/`ResponseEntity` or `@ExceptionHandler`.

## 7. Emitting Exceptions in `Mono` and `Flux`

In reactive programming, exceptions must become an `onError` signal of the publisher so WebFlux handles them according to the request lifecycle.

### 7.1. Turning `Mono.empty()` into 404

```java
Mono<Item> result = repository.findById(id)
        .switchIfEmpty(Mono.error(
                new ResponseStatusException(
                        HttpStatus.NOT_FOUND,
                        "Item not found")));
```

This is the natural approach when a missing resource is represented by an empty publisher.

### 7.2. Using `Mono.defer` When the Error Depends on Execution

```java
Mono<Item> result = Mono.defer(() -> {
    if (id == null || id.isBlank()) {
        return Mono.error(
                new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "Item id is required"));
    }

    return repository.findById(id);
});
```

`defer` delays checking and creating the publisher until subscription time. For an ordinary controller request, data can be validated right inside the method; `defer` is useful when you want side effects or publisher-creation logic to execute upon subscription.

### 7.3. Difference Between `onErrorMap` and `onErrorResume`

`onErrorMap` transforms one error into another exception:

```java
return service.load(id)
        .onErrorMap(
                StorageTimeoutException.class,
                error -> new ResponseStatusException(
                        HttpStatus.GATEWAY_TIMEOUT,
                        "Storage timed out",
                        error));
```

`onErrorResume` recovers using another publisher:

```java
return service.load(id)
        .onErrorResume(CacheUnavailableException.class,
                error -> service.loadFromDatabase(id));
```

If `onErrorResume` returns a fallback value and completes successfully, the response may be 2xx; the original exception is no longer used to determine the status. Only recover when the fallback is genuinely the intended behavior.

Do not catch every exception and return `Mono.just(defaultValue)`. That can hide failures and produce fake success responses.

### 7.4. Do Not Wrap Away Status-Bearing Exceptions

If a `ResponseStatusException` is wrapped in a generic exception that breaks the cause relationship or is not recognized by handlers, the intended status may no longer be mapped as expected. Preserve the exception or translate it intentionally, and test the final status.

## 8. Returning Structured Error Bodies with `ProblemDetail`

Spring Framework 6 supports RFC 9457 Problem Details through these abstractions:

- `ProblemDetail`: standard error body with `type`, `title`, `status`, `detail`, `instance`, and extension properties.
- `ErrorResponse`: contract providing HTTP status, headers, and `ProblemDetail`.
- `ErrorResponseException`: base exception capable of carrying an `ErrorResponse`.
- `ResponseEntityExceptionHandler`: base class for `@ControllerAdvice` that handles WebFlux exceptions and renders Problem Details.

`ResponseStatusException` extends `ErrorResponseException`, so it has `getBody()` to access `ProblemDetail`. A clean way to return the body is via advice:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ProblemDetail> handle(
            ResponseStatusException exception) {

        ProblemDetail problem = exception.getBody();

        return ResponseEntity
                .status(exception.getStatusCode())
                .headers(headers ->
                        headers.addAll(exception.getHeaders()))
                .body(problem);
    }
}
```

The advice above:

1. Receives the status-bearing exception.
2. Retrieves the `ProblemDetail` provided by the exception.
3. Preserves the status and response headers.
4. Returns the body formatted as Problem Details.

When Jackson is configured with Spring WebFlux defaults, `ProblemDetail` is written with media type `application/problem+json` (or XML when appropriate). The `instance` property can be populated by Spring from the current URL path if not already set.

### 8.1. Adding Custom Error Codes

Custom properties can be added:

```java
ProblemDetail problem = exception.getBody();
problem.setProperty("code", "ITEM_NOT_FOUND");
problem.setProperty("retryable", false);
```

When using Spring's built-in Jackson integration, the `properties` map is serialized as top-level fields in the Problem Detail JSON.

Example body:

```json
{
  "type": "about:blank",
  "title": "Not Found",
  "status": 404,
  "detail": "Item 42 was not found",
  "instance": "/api/items/42",
  "code": "ITEM_NOT_FOUND",
  "retryable": false
}
```

Keep error codes stable for machine-readable client handling. `detail` may change or be localized, so clients should not depend on parsing prose sentences.

### 8.2. Using `ResponseEntityExceptionHandler` for Standard WebFlux Errors

If you want to standardize framework-generated errors as well—such as unreadable bodies, unsupported methods, validation, or media types—you can extend `ResponseEntityExceptionHandler`:

```java
@RestControllerAdvice
public class GlobalWebFluxExceptionHandler
        extends ResponseEntityExceptionHandler {
}
```

This base class provides an `@ExceptionHandler` for WebFlux exceptions and `ErrorResponseException`, returning RFC 9457 responses. You can override specific handler methods or add handlers for application business exceptions.

Do not create an `@ExceptionHandler(Exception.class)` that returns 400 for every error. Unexpected errors, bugs, and infrastructure failures must remain 5xx so they can be investigated.

## 9. How Do `@ExceptionHandler` and `WebExceptionHandler` Differ?

Both abstractions handle errors, but they have different scopes:

| Abstraction | Scope | Suitable Use Case |
|---|---|---|
| `@ExceptionHandler` | Errors from controller methods in an annotated controller | Map domain exceptions to ProblemDetail |
| `@ControllerAdvice` / `@RestControllerAdvice` | Apply `@ExceptionHandler` across multiple controllers | Shared error schema for REST APIs |
| `ResponseEntityExceptionHandler` | Base class for advice handling standard WebFlux errors | Standardize framework errors per RFC 9457 |
| `WebExceptionHandler` | Entire WebHandler chain, including WebFilters and target handler | Errors raised before/after controller or inside filters |
| `WebFluxResponseStatusExceptionHandler` | `WebExceptionHandler` dedicated to status exceptions/annotations | Map status from `ResponseStatusException` and `@ResponseStatus` on exception classes |

`@ControllerAdvice` is not a global interceptor for every error across every layer of the server. If an error occurs inside a `WebFilter` before the request reaches an annotated controller, the `WebExceptionHandler` mechanism is the appropriate layer.

Functional endpoints (`WebFlux.fn`) can configure exception handlers through `HandlerStrategies`; do not assume `@ControllerAdvice` automatically covers every functional route in the same way as annotated controllers.

## 10. Committed Responses: Why Can't Status Be Changed Afterward?

The HTTP status and headers must be sent before or at the moment the response begins to commit. For an endpoint returning a single JSON payload, errors typically occur before the body finishes writing and can be mapped into an error response.

For a streaming response:

```java
@GetMapping(
        path = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<Event>> events() {
    return eventService.stream();
}
```

Suppose the stream has already emitted several events before emitting `onError`. By then, the status/headers have likely already been sent. WebFlux cannot go back to change HTTP 200 to 500 and replace the already-sent body. The client may see the stream terminate abnormally or receive a transport/protocol-level error depending on the situation.

Therefore:

- Determine the status before starting streaming whenever possible.
- Handle mid-stream errors according to the stream protocol when needed, such as emitting an error event per your application contract.
- Do not rely on a late `ResponseStatusException` to fix an already-committed status.
- Test both the case of an error before the first event and an error after streaming has begun.

## 11. Common Mistakes When Using `ResponseStatusException` and `@ResponseStatus`

| Mistake | Consequence | Fix |
|---|---|---|
| Using `@ResponseStatus` on a controller class with multiple endpoints | Unintentionally applies the same status to multiple methods | Place it on specific methods or exception classes |
| Using `@ResponseStatus` for status depending on runtime outcome | Annotation cannot express multiple status branches | Use `ResponseStatusException` or `ResponseEntity` |
| Assuming `@ResponseStatus` automatically creates a JSON error body | Client gets status without expected error schema | Use `ProblemDetail`/`@ExceptionHandler` |
| Assuming `ResponseStatusException` always renders a body on every handling path | May only see status set by `WebExceptionHandler` | Use advice returning `ProblemDetail` if a body is part of the contract |
| Putting SQL or internal info in `reason` | Exposes system internals to the client | Use safe detail, keep cause in logs |
| Throwing synchronous exceptions outside the reactive pipeline where inappropriate | Hard to control error timing and subscription | Use `Mono.error`, `switchIfEmpty`, `defer` |
| Using `onErrorResume` to return a fallback for all errors | Real failures get turned into success responses | Only recover errors that have a valid fallback |
| Wrapping `ResponseStatusException` in a generic exception | Status mapping may be lost | Preserve the exception or remap intentionally |
| Changing status after the response commits | Cannot modify already-sent status/headers | Decide status before streaming the body |
| Attaching HTTP annotations to domain exceptions across all layers | Couples domain to transport | Map domain exceptions at the HTTP boundary |
| Using `ResponseStatusException` for all unexpected errors | Masks bugs as client errors | Classify input, domain, and infrastructure errors |
| Logging full stack traces for every 404 | Heavy log noise | Use appropriate log levels and reserve traces for unexpected errors |

## 12. Runnable Java 17+ Project: ResponseStatusException and @ResponseStatus

The Maven project below uses Spring Boot 3.3.5, Spring WebFlux, and `WebTestClient`. It demonstrates three approaches:

1. `ResponseStatusException` producing a dynamic 404 when an item does not exist.
2. `@ResponseStatus` on an exception class producing a fixed 404.
3. `@ResponseStatus` on controller methods producing statuses 201 and 204 on success.

A `@RestControllerAdvice` renders `ProblemDetail` from `ResponseStatusException` so the error body has a clear contract.

### 12.1. Project Structure

```text
webflux-response-status/
├── pom.xml
└── src/
    ├── main/java/edu/demo/status/
    │   ├── StatusApplication.java
    │   ├── Item.java
    │   ├── CreateItem.java
    │   ├── ItemService.java
    │   ├── ItemController.java
    │   ├── LegacyItemNotFoundException.java
    │   └── ApiExceptionHandler.java
    └── test/java/edu/demo/status/
        └── ItemStatusTests.java
```

### 12.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-response-status</artifactId>
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

### 12.3. `StatusApplication.java`

```java
package edu.demo.status;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StatusApplication {

    public static void main(String[] args) {
        SpringApplication.run(StatusApplication.class, args);
    }
}
```

### 12.4. `Item.java` and `CreateItem.java`

```java
package edu.demo.status;

public record Item(String id, String name) {
}
```

```java
package edu.demo.status;

public record CreateItem(String name) {
}
```

### 12.5. `ItemService.java`

```java
package edu.demo.status;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ItemService {

    private final ConcurrentMap<String, Item> items =
            new ConcurrentHashMap<>();

    private final AtomicLong sequence = new AtomicLong();

    public Mono<Item> create(CreateItem request) {
        return Mono.fromSupplier(() -> {
            String id = Long.toString(sequence.incrementAndGet());
            Item item = new Item(id, request.name());
            items.put(id, item);
            return item;
        });
    }

    public Mono<Item> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(items.get(id)));
    }

    public Mono<Boolean> deleteById(String id) {
        return Mono.fromSupplier(() -> items.remove(id) != null);
    }
}
```

The service only provides business outcomes: item exists, item missing, or whether deletion succeeded. It does not decide HTTP statuses on its own. The HTTP adapter maps empty/false outcomes to the appropriate exception or response.

### 12.6. `LegacyItemNotFoundException.java`

```java
package edu.demo.status;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

@ResponseStatus(HttpStatus.NOT_FOUND)
public class LegacyItemNotFoundException extends RuntimeException {

    public LegacyItemNotFoundException(String id) {
        super("Item " + id + " was not found");
    }
}
```

This exception illustrates attaching a fixed status onto an exception class. Because this class uses `@ResponseStatus`, WebFlux can set status 404 when the exception escapes. The example does not use `reason` to produce an error body; the error body will be managed by advice if needed.

### 12.7. `ItemController.java`

```java
package edu.demo.status;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/items")
public class ItemController {

    private final ItemService service;

    public ItemController(ItemService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<Item> get(@PathVariable String id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND,
                                "Item " + id + " was not found")));
    }

    @GetMapping("/legacy/{id}")
    public Mono<Item> getLegacy(@PathVariable String id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new LegacyItemNotFoundException(id)));
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Mono<Item> create(@RequestBody CreateItem request) {
        return service.create(request);
    }

    @DeleteMapping("/{id}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public Mono<Void> delete(@PathVariable String id) {
        return service.deleteById(id)
                .flatMap(deleted -> {
                    if (deleted) {
                        return Mono.empty();
                    }

                    return Mono.error(
                            new ResponseStatusException(
                                    HttpStatus.NOT_FOUND,
                                    "Item " + id + " was not found"));
                });
    }
}
```

The two item lookup paths demonstrate both exception styles:

- `/api/items/{id}` emits `ResponseStatusException` with status and detail determined at runtime.
- `/api/items/legacy/{id}` emits an exception class annotated with `@ResponseStatus`.

POST and DELETE demonstrate fixed statuses on methods: 201 and 204.

### 12.8. `ApiExceptionHandler.java`

```java
package edu.demo.status;

import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<ProblemDetail> handle(
            ResponseStatusException exception) {

        ProblemDetail problem = exception.getBody();

        return ResponseEntity
                .status(exception.getStatusCode())
                .headers(headers ->
                        headers.addAll(exception.getHeaders()))
                .body(problem);
    }
}
```

This advice ensures that `ResponseStatusException` instances from annotated controllers are returned with their corresponding status, headers, and ProblemDetail. In larger applications, handle each exception group separately or extend `ResponseEntityExceptionHandler` to standardize framework exceptions as well.

### 12.9. `ItemStatusTests.java`

```java
package edu.demo.status;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ItemStatusTests {

    @Autowired
    WebTestClient client;

    @Test
    void postUsesResponseStatusCreated() {
        client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItem("Keyboard"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").exists()
                .jsonPath("$.name").isEqualTo("Keyboard");
    }

    @Test
    void responseStatusExceptionMapsTo404AndProblemDetail() {
        client.get()
                .uri("/api/items/not-found")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo(404)
                .jsonPath("$.detail")
                .isEqualTo("Item not-found was not found");
    }

    @Test
    void responseStatusOnExceptionClassMapsTo404() {
        client.get()
                .uri("/api/items/legacy/not-found")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void deleteUsesResponseStatusNoContent() {
        Item created = client.post()
                .uri("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateItem("Mouse"))
                .exchange()
                .expectStatus().isCreated()
                .expectBody(Item.class)
                .returnResult()
                .getResponseBody();

        org.junit.jupiter.api.Assertions.assertNotNull(created);

        client.delete()
                .uri("/api/items/{id}", created.id())
                .exchange()
                .expectStatus().isNoContent()
                .expectBody().isEmpty();
    }

    @Test
    void deleteMissingItemUsesDynamic404() {
        client.delete()
                .uri("/api/items/missing-delete")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader()
                .contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON)
                .expectBody()
                .jsonPath("$.status").isEqualTo(404);
    }
}
```

### 12.10. Running the Program

In the directory containing `pom.xml`:

```bash
mvn test
```

When dependencies download and assertions match, Maven Surefire will report five tests run with no failures or errors:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected output to compare against after execution; the document does not claim Maven was executed in the authoring environment.

Start the application:

```bash
mvn spring-boot:run
```

Create an item:

```bash
curl -i -X POST "http://localhost:8080/api/items" \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard"}'
```

The response has status `201 Created` and JSON containing `id` and `name`.

Look up a non-existent ID:

```bash
curl -i "http://localhost:8080/api/items/unknown"
```

The response has status `404 Not Found`; with the advice in the example, the body is rendered as `application/problem+json`.

## 13. Testing and Diagnostics

When testing status mapping, do not check only the status code. For an API with an error contract, verify:

- Correct HTTP status.
- Correct Content-Type, typically `application/problem+json`.
- `ProblemDetail.status` matches the HTTP status.
- `detail` contains no internal information.
- Stable error codes or extra fields if clients depend on them.
- Required headers are preserved.
- No response body when the status requires an empty body such as 204.

Cases to test:

| Case | Assertion |
|---|---|
| `ResponseStatusException` 404 | Status 404; ProblemDetail body if advice is present |
| Exception class with `@ResponseStatus(404)` | Status 404 |
| Method with `@ResponseStatus(201)` | Status 201 and body is still written |
| Method with `@ResponseStatus(204)` | Status 204, empty body |
| Response committed then stream emits error | Do not expect status to change to 4xx/5xx |
| Unexpected exception | Status 5xx, not turned into 400 |

If the status is not as expected, trace:

1. Was the exception actually emitted as `onError`?
2. Was the exception converted into a success value by `onErrorResume`?
3. Which `@ExceptionHandler` caught the exception?
4. Did `WebFluxResponseStatusExceptionHandler` receive the exception?
5. Was the response already committed before the exception occurred?
6. Did any filter or custom `WebExceptionHandler` handle it first and alter the result?

## 14. Checklist for Choosing Status Mapping

- Is the status fixed for a successful endpoint? Consider `@ResponseStatus` on the method.
- Does an exception type always carry the same status and is it used only in the web layer? Consider `@ResponseStatus` on the exception class.
- Does the status depend on runtime results or request data? Use `ResponseStatusException` or `ResponseEntity`.
- Do you need an RFC 9457 standard error body? Use `ProblemDetail`, `@ExceptionHandler`, or `ResponseEntityExceptionHandler`.
- Do you need custom response headers? Use `ResponseEntity` or preserve headers from `ResponseStatusException`.
- Does the exception contain sensitive information? Use safe details and do not send causes/stack traces to the client.
- Is the domain/application layer forced to depend on HTTP annotations? If so, move the mapping to an adapter/advice.
- Can an error be emitted after body streaming begins? Design a dedicated stream protocol.
- Are there tests for status, body, content type, and committed-response scenarios?
- Are unexpected errors kept as 5xx for investigation?

## 15. Self-Check Exercises

**Exercise 1.** A repository returns `Mono.empty()` when an item is not found. To return 404 based on the request ID, what should you use?

**Answer:** `switchIfEmpty(Mono.error(new ResponseStatusException(HttpStatus.NOT_FOUND, ...)))`, or map empty to an exception class annotated with `@ResponseStatus` if the status is fixed and architecturally appropriate.

**Exercise 2.** Does `@ResponseStatus(HttpStatus.CREATED)` placed on a POST method prevent Spring from writing a response body?

**Answer:** No; when `reason` is not used, the method can still return an object/`Mono<T>` so Spring writes the body with status 201.

**Exercise 3.** Does `@ResponseStatus(HttpStatus.NOT_FOUND)` on an exception class automatically generate a JSON `ProblemDetail`?

**Answer:** You should not assume so. The WebFlux status handler resolves and sets the status; if you want a clearly defined error body schema, use `@ExceptionHandler` returning `ProblemDetail` or `ResponseEntity`.

**Exercise 4.** Why is `ResponseStatusException` more suitable than a static annotation when the status depends on runtime conditions?

**Answer:** Its constructor lets you choose `HttpStatusCode`, reason, and cause at the moment the exception is created.

**Exercise 5.** `ResponseStatusException` has a `ProblemDetail` body, yet the actual response has no JSON body. What should you check?

**Answer:** Check the exception handling path. If only `WebFluxResponseStatusExceptionHandler` runs, it sets the status; add `@ExceptionHandler`/`ResponseEntityExceptionHandler` to render the body.

**Exercise 6.** An SSE stream has emitted 10 events and then throws `ResponseStatusException(500)`. Can WebFlux change the status to 500?

**Answer:** Usually no, because the response is already committed. Errors must be handled according to the stream protocol, or the status must be decided before sending the body.

**Exercise 7.** An unexpected database error is converted into `ResponseStatusException(BAD_REQUEST)`. Why is that bad?

**Answer:** It falsely signals that the client sent an invalid request, masks infrastructure outages, and corrupts metrics/status meaning. Only map errors according to their actual cause and contract.

**Exercise 8.** Why should domain exceptions not always carry `@ResponseStatus`?

**Answer:** The domain may be used by multiple non-HTTP adapters. Placing HTTP annotations on exceptions couples the domain to transport; mapping at the HTTP boundary is usually more flexible.

## 16. Key Takeaways

- `ResponseStatusException` is the way to emit exceptions with a dynamic status in a reactive pipeline.
- `@ResponseStatus` on an exception class binds a fixed status to an error type; WebFlux provides `WebFluxResponseStatusExceptionHandler` to recognize it.
- `@ResponseStatus` on a controller method suits fixed statuses for successful responses such as 201 or 204.
- `ResponseStatusException` implements `ErrorResponse` and holds a `ProblemDetail`; to have the JSON body rendered explicitly, use `@ExceptionHandler`, `@ControllerAdvice`, or `ResponseEntityExceptionHandler`.
- `WebExceptionHandler` covers the `WebHandler` chain scope; `@ExceptionHandler`/`@ControllerAdvice` handle controller errors via the annotated controller mechanism.
- Do not change status after the response has committed, especially with SSE/NDJSON streaming.
- Preserve the cause for investigation, but send only safe details to the client.
- Do not turn every exception into 400; separate input, domain, and infrastructure errors.

When handling errors in WebFlux, identify three things: **where the exception is emitted, which handler receives it, and whether the response has already committed**. From there, choose appropriately among status exceptions, annotations, advice, and ProblemDetail.

## Official Documentation

- Spring Framework 6.2, **WebFlux Reactive Core – Exception Handling**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html
- Spring Framework 6.2, **`ResponseStatusException` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/server/ResponseStatusException.html
- Spring Framework 6.2, **`WebFluxResponseStatusExceptionHandler` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/reactive/handler/WebFluxResponseStatusExceptionHandler.html
- Spring Framework 6.2, **`@ResponseStatus` API**: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/bind/annotation/ResponseStatus.html
- Spring Framework 6.2, **WebFlux Controller Exceptions**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-exceptions.html
- Spring Framework 6.2, **WebFlux Error Responses and Problem Details**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html