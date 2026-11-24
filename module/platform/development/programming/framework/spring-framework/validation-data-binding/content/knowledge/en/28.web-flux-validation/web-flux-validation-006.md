# WebExchangeBindException and Reactive Error Handling in Spring WebFlux

## 1. What Is WebExchangeBindException?

In **Spring WebFlux**, when a controller uses `@Valid` or `@Validated` to validate a command object from a request, Spring can raise:

```java
org.springframework.web.bind.support.WebExchangeBindException
```

This exception signals that **data passed the binding/deserialization step into an object, yet the object failed the applied validation rules**. The exception carries `BindingResult` details: field errors, global errors, object name, error codes, and error messages. For standard request input, Spring handles it as **HTTP 400 Bad Request**.

Example:

```java
@PostMapping("/accounts")
public Mono<AccountView> create(
        @Valid @RequestBody AccountInput input) {
    return service.create(input);
}
```

If `AccountInput` has `@NotBlank String name` and the client sends `"name": " "`, WebFlux can throw `WebExchangeBindException` **before the controller body is invoked**. If the controller declares its input as `Mono<AccountInput>`, the exception typically appears as an **error signal inside the publisher**, and can be handled with Reactor operators like `onErrorResume`.

Common pitfall: Spring MVC on the Servlet stack typically uses `MethodArgumentNotValidException` for equivalent validation failures. **Do not copy an MVC handler expecting it to catch WebFlux errors**. Both provide binding/validation details, yet the exception class and execution model differ.

**Lesson scope:** Spring Framework 6.1–6.2, Spring Boot 3.x, Java 17+, Jakarta Validation 3.x, annotated controllers on Spring WebFlux. Functional routing controllers (WebFlux.fn) have distinct traits covered separately. Examples use the `jakarta.validation` package, not the older `javax.validation`.

## 2. Where Does Validation Error Sit in the Reactive Chain?

A WebFlux REST call passes through these steps:

```text
HTTP request
    |
    v
Reactor Netty / web server adapter
    |
    v
WebFilter -> DispatcherHandler
    |
    v
Handler mapping -> annotated controller
    |
    v
Argument resolver + HttpMessageReader / codec
    |  deserializes JSON or multipart part into a Java object
    |
    +-- Malformed JSON / unreadable type
    |       -> ServerWebInputException or related codec error
    |
    v
Bean Validation (@Valid / @Validated)
    |
    +-- Object fails constraint
    |       -> WebExchangeBindException
    |       -> onError signal or exception resolution
    |
    v
Controller business flow -> Mono/Flux
    |
    v
Return serialization / ServerHttpResponse
```

The exact path also depends on the argument form:

- **`@Valid @RequestBody AccountInput input`:** the framework must resolve the argument into an object **before calling** the handler. If validation fails, the controller body does not run; an `@RestControllerAdvice` can handle the exception.
- **`@Valid @RequestBody Mono<AccountInput> input`:** the controller receives a publisher; when the body is read, decoded, and validated in the pipeline, errors can travel as `onError` signals on the `Mono`. The controller can handle them with `onErrorResume(WebExchangeBindException.class, ...)` directly on that chain.
- **`@Valid @RequestPart("metadata") Mono<Metadata> metadata`:** similar, except the object comes from **one part** of a multipart request, decoded by the appropriate codec.
- **`@Valid @ModelAttribute Form form`:** Spring WebFlux uses data binding for the form/command object; validation failures can also be represented by `WebExchangeBindException`.
- **Direct constraint on a method parameter** like `@Min(1)` on `@PathVariable int page`: since Framework 6.1+, this can activate **method validation**, yielding `HandlerMethodValidationException` instead of `WebExchangeBindException`.

The keyword "reactive" does not mean Bean Validation magically turns into an asynchronous operation. The Jakarta Validation provider usually performs checks **synchronously in-place** once the object exists. What is reactive is how the request body is read and how **errors are emitted, propagated, or recovered** within `Mono`/`Flux`.

## 3. Distinguishing Binding, Validation, Deserialization, and Business Errors

Four situations can all manifest as HTTP 400 while having very different root causes:

| Input / Event | Stage of Failure | Typical Exception | How to Respond |
| --- | --- | --- | --- |
| Valid JSON, `name=" "` with `@NotBlank` | Bean Validation | `WebExchangeBindException` | Return field errors, HTTP 400 |
| Valid JSON, `age=15` with `@Min(18)` | Bean Validation | `WebExchangeBindException` | Return field errors, HTTP 400 |
| Malformed JSON `{"name":` | Decode/parse | `ServerWebInputException` or wrapped codec error | Return unreadable payload code, HTTP 400 |
| Missing required `@RequestBody` | Argument resolution | `ServerWebInputException` | Return missing-body error, HTTP 400 |
| Unsupported Content-Type | Codec/content negotiation | `UnsupportedMediaTypeStatusException` or corresponding HTTP 415 error | Return HTTP 415 |
| Invalid `@PathVariable @Min(1) int page` | Method validation | `HandlerMethodValidationException` | Usually HTTP 400 |
| Controller returns data violating return constraint | Method return validation | `HandlerMethodValidationException` | Usually HTTP 500 |
| Account/email already exists | Business/repository | Application-designed exception or result | HTTP 409 may fit; do not lump with binding |
| Database unreachable | Runtime/infrastructure | Service/database exception | Usually 5xx; avoid returning 400 |

**Do not lump everything into `WebExchangeBindException`.** Malformed JSON yields no valid object to run `@NotBlank` against, and database-dependent uniqueness rules are not enforced by Jakarta Validation on a DTO alone.

### 3.1. A single @NotNull constraint is not enough for every empty field

Example:

```java
public record AccountInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

- `name = null`, `""`, or `"   "` fails `@NotBlank`.
- `age = 15` fails `@Min(18)`.
- `age = null` fails `@NotNull`; `@Min` itself treats null as valid per the Jakarta Validation contract.
- `age = "abc"` in JSON can fail right inside Jackson/codec because it cannot convert to Integer. That is not evidence `@Min` ran.
- If the boundary annotation triggering validation is missing, having `@NotBlank` on the record does not guarantee any controller will validate it.

### 3.2. Cascading: @Valid on child fields

```java
public record Address(
        @NotBlank String city
) {}

public record AccountInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        @NotNull @Valid Address address
) {}
```

`@Valid` on `address` instructs the validator to descend into the child object and evaluate `city`. Omitting this `@Valid` allows an `Address` with `city=""` to pass outer object validation. Conversely, `@Valid` does not forbid null on its own: `@NotNull` is needed when `address` is required.

For collections, Jakarta Validation supports container-element constraints and cascading (e.g., `List<@Valid Item>`) when structured appropriately. However, a **top-level List/Map** argument should not be assumed to follow the exact same validation path as a command object in all WebFlux signatures. For complex inputs, use a wrapper DTO and test over real HTTP.

## 4. What Information Does the Exception Contain?

`WebExchangeBindException` exposes data from `BindingResult`:

```java
ex.getBindingResult().getFieldErrors();
ex.getBindingResult().getGlobalErrors();
ex.getBindingResult().getAllErrors();
ex.getBindingResult().getObjectName();
```

That is an **illustrative snippet inside an exception handler** with `ex` of type `WebExchangeBindException`. The exception also implements corresponding binding-error methods directly.

### 4.1. FieldError

Each `FieldError` can carry:

- `getField()`: the violated property name, such as `name`, `age`, or `address.city`.
- `getCode()`: short error code generated by Spring for the constraint or binding, e.g., `NotBlank`, `Min`, `NotNull`.
- `getCodes()`: message codes usable for interpolating messages by specificity.
- `getDefaultMessage()`: interpolated message, which may vary by locale and message bundle.
- `getRejectedValue()`: the rejected value; **never echo blindly** if it may contain passwords/tokens/PII.
- `isBindingFailure()`: distinguishes certain binding/type conversion errors from validation errors; not a substitute for understanding the root exception.

`getCode()` is handy for normalizing UI feedback, though large APIs should map to **stable application-defined business error codes** rather than coupling clients completely to Spring/provider code naming.

### 4.2. ObjectError / global error

Custom class-level constraints can produce an `ObjectError` for cross-field relationships. If a handler only reads `getFieldErrors()` and ignores `getGlobalErrors()`, the response may **omit critical errors**. A well-designed error DTO represents both field and object-level errors.

Example normalized response:

```json
{
  "code": "VALIDATION_ERROR",
  "fields": [
    {"field": "age", "code": "Min"},
    {"field": "name", "code": "NotBlank"}
  ]
}
```

This is an **application-chosen format**, not a mandatory Spring WebFlux default JSON. The order of constraint violations is not guaranteed; if you want deterministic ordering for snapshots/tests, sort by field name and code as shown in the demo.

### 4.3. HTTP status and Problem Details

`WebExchangeBindException` follows Spring's HTTP error response contract, normally returning **400 Bad Request**. Spring Framework supports `ProblemDetail` and RFC 9457; you can extend the **WebFlux package's** `ResponseEntityExceptionHandler` for global customization, or write an `@RestControllerAdvice` to return a custom JSON contract.

Do not accidentally import `ResponseEntityExceptionHandler` from the Servlet MVC namespace in a WebFlux app:

```java
// WebFlux:
org.springframework.web.reactive.result.method.annotation
        .ResponseEntityExceptionHandler

// Spring MVC:
org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler
```

The simple class name is identical, yet the HTTP runtime and handler composition differ. The runnable example uses `@RestControllerAdvice` directly so responses are easy to inspect accurately.

## 5. Reactive Error Handling: onError vs try/catch

### 5.1. Error as a Publisher signal

A `Mono<T>` has three primary signal types:

```text
onSubscribe
    |
    +-- onNext(value) -> onComplete     (success)
    |
    +-- onComplete                      (no value)
    |
    +-- onError(error)                   (failure)
```

A publisher terminating with `onError` emits no further values or `onComplete`. When Spring WebFlux deserializes and validates a request from `Mono<AccountInput>`, `WebExchangeBindException` becomes that `onError` signal.

A `try/catch` wrapping the statement **building the Mono** generally cannot catch errors emitted **after the publisher is subscribed**. Example:

```java
try {
    return request.map(this::save);
} catch (WebExchangeBindException ex) {
    // Usually does not run when errors occur in the reactive pipeline.
}
```

This is an **illustration**, assuming `request` and `save` are defined. The proper reactive error-handling pattern is:

```java
return request
        .map(this::save)
        .onErrorResume(
                WebExchangeBindException.class,
                ex -> Mono.just(fallbackResponse(ex))
        );
```

where `fallbackResponse` must match the pipeline's result type; the code above is a **snippet**, not a standalone method.

### 5.2. Important operators

| Operator | Role | When to Use |
| --- | --- | --- |
| `onErrorResume(Type.class, ex -> alternateMono)` | Switch matching error to another publisher | Returning structured 400 / intentional fallback |
| `onErrorMap(Type.class, mapper)` | Transform exception type | Keeping error flow while normalizing to a domain exception |
| `doOnError(Type.class, consumer)` | Side effect observing error without recovering | Logging/metrics free of sensitive data |
| `onErrorReturn(value)` | Return an unconditional fallback value for matching errors | Only when fallback is genuinely valid in business logic |
| `switchIfEmpty(alternate)` | Handle publisher completing **with no value** | Completely distinct from validation errors |
| `onErrorContinue` | Drop errored elements in some operators | **Not appropriate by default** for ignoring input validation errors |
| `retry(...)` | Re-subscribe after error | Never retry invalid client request errors |

Example of what **not to do**:

```java
return validatedInput
        .onErrorReturn(new AccountInput("guest", 18, new Address("X")));
```

This snippet turns an invalid request into a fake accepted account, hiding user mistakes and creating unintended data. In resource-creation APIs, return an explicit HTTP 400 or let an exception handler handle it.

### 5.3. Do not swallow every exception

```java
.onErrorResume(Throwable.class, error ->
        Mono.just(badRequest()))
```

The anti-example above turns **every error** (database, bug, permission, server failure) into HTTP 400, falsely blaming the client. Catch strictly `WebExchangeBindException` when handling validation locally; other errors should reach appropriate handlers or propagate.

When using `doOnError` for logging, avoid printing `FieldError#getRejectedValue()` for sensitive fields, and avoid dumping full stack traces for every 400 input error into logs.

## 6. Three Places to Handle Errors in WebFlux

### 6.1. Inside the controller: local recovery

When the argument is `Mono<AccountInput>`, the controller can handle errors in-place:

```java
@PostMapping("/accounts/reactive")
public Mono<ResponseEntity<Map<String, Object>>> create(
        @Valid @RequestBody Mono<AccountInput> body) {

    return body
        .map(this::created)
        .onErrorResume(WebExchangeBindException.class, ex -> {
            Map<String, Object> error =
                    Map.of("code", "LOCAL_VALIDATION_ERROR");
            return Mono.just(ResponseEntity.badRequest().body(error));
        });
}
```

This is an illustrative snippet; `created` is assumed to return `ResponseEntity<Map<String,Object>>`. When a matching error emits from the publisher, `onErrorResume` **replaces** the error signal with a response. Because the error is already handled, a global `@RestControllerAdvice` will no longer receive it.

Pros: local logic sits right beside the endpoint, handy if only one flow needs a special response. Cons: duplicates error mapping across controllers; hard to keep consistent if every method writes different logic.

### 6.2. @RestControllerAdvice: standardized responses across annotated controllers

```java
@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    Mono<ResponseEntity<ApiError>> invalid(
            WebExchangeBindException ex) {
        // ...
    }
}
```

This is a snippet; the demo below provides the full class. The advice handles exceptions raised while Spring resolves arguments or errors propagated out of handlers. Using a shared mapping ensures clients receive a consistent 400 contract.

### 6.3. WebExceptionHandler / ErrorWebExceptionHandler: general web layer

Spring WebFlux also has a lower-level error-handling layer:

- `org.springframework.web.server.WebExceptionHandler`: handles exceptions in the web handling chain via `Mono<Void>`.
- `org.springframework.boot.web.reactive.error.ErrorWebExceptionHandler`: Spring Boot provides reactive web error infrastructure, including default error handling.
- `@ControllerAdvice` is a mechanism **for annotated controllers**; do not assume it catches all errors from WebFlux.fn, WebFilters, or failures occurring before a controller is selected.

WebFlux.fn lacks built-in `@Valid @RequestBody` argument resolution like annotated controllers because handlers use `ServerRequest` and assemble their own pipeline. To validate a functional endpoint, you typically invoke `Validator` explicitly and build the response in `Mono<ServerResponse>`, or use an appropriate web error handler component.

Once a response is committed, a global handler may no longer be able to change the status or rewrite the body. Therefore validate input **before side effects**, and avoid writing partial responses before knowing the request is valid.

## 7. Runnable Spring Boot Project: Global Advice and Local onErrorResume

This example uses Java 17, Spring Boot **3.3.6**, Spring WebFlux 6.1.x, and Jakarta Validation. The app includes:

- `POST /api/accounts` with a **direct DTO**: errors handled by `@RestControllerAdvice`.
- `POST /api/accounts/reactive` with **`Mono<DTO>`**: validation errors handled by `onErrorResume` inside the controller.
- `GET /api/pages/{page}` with a direct `@Min(1)` constraint to contrast `HandlerMethodValidationException`.
- `WebTestClient` tests covering happy paths, field/nested constraints, malformed JSON, local recovery, and method validation.

### 7.1. Project structure

```text
webflux-validation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/webfluxvalidation/
    │   ├── WebfluxValidationApplication.java
    │   ├── Address.java
    │   ├── AccountInput.java
    │   ├── FieldIssue.java
    │   ├── ApiError.java
    │   ├── AccountController.java
    │   └── ApiErrorAdvice.java
    └── test/java/com/example/webfluxvalidation/
        └── AccountControllerTest.java
```

### 7.2. Gradle

File `settings.gradle`:

```groovy
rootProject.name = 'webflux-validation-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use only `spring-boot-starter-webflux`; **do not add `spring-boot-starter-web`** to the example. Spring Boot normally prefers Servlet MVC when both web and webflux starters are present; adding both and assuming the app runs reactively is wrong. If both libraries are genuinely required, you can explicitly configure the reactive application type and test runtime behavior, though that is unnecessary here.

`spring-boot-starter-validation` places the Jakarta Validation provider on the classpath (typically Hibernate Validator). Without an appropriate provider, `@Valid` in controllers may not work as expected.

### 7.3. Application

File `src/main/java/com/example/webfluxvalidation/WebfluxValidationApplication.java`:

```java
package com.example.webfluxvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebfluxValidationApplication.class, args);
    }
}
```

### 7.4. DTO with nested validation

File `src/main/java/com/example/webfluxvalidation/Address.java`:

```java
package com.example.webfluxvalidation;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String city
) {}
```

File `src/main/java/com/example/webfluxvalidation/AccountInput.java`:

```java
package com.example.webfluxvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record AccountInput(
        @NotBlank String name,
        @NotNull @Min(18) Integer age,
        @NotNull @Valid Address address
) {}
```

With request:

```json
{
  "name": " ",
  "age": 15,
  "address": {"city": ""}
}
```

the object deserializes successfully yet violates `@NotBlank`, `@Min(18)`, and nested `Address.city`. `@NotNull @Valid` on `address` both forbids a missing object and enables cascading into the child component.

### 7.5. Error DTO decoupled from internal exceptions

File `src/main/java/com/example/webfluxvalidation/FieldIssue.java`:

```java
package com.example.webfluxvalidation;

public record FieldIssue(String field, String code) {}
```

File `src/main/java/com/example/webfluxvalidation/ApiError.java`:

```java
package com.example.webfluxvalidation;

import java.util.List;

public record ApiError(
        String code,
        List<FieldIssue> fields
) {}
```

Clients receive error codes and field names, without `rejectedValue`, stack traces, or internal details. Although the DTO holds `List<FieldIssue>`, that list is constructed **after catching errors**; it is not a request payload.

### 7.6. Controller: direct data and publisher

File `src/main/java/com/example/webfluxvalidation/AccountController.java`:

```java
package com.example.webfluxvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class AccountController {

    // Direct DTO: exception occurs during argument resolution.
    // @RestControllerAdvice handles it if validation fails.
    @PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> create(
            @Valid @RequestBody AccountInput input) {

        return Mono.just(created(input));
    }

    // Mono<DTO>: validation error can travel via the onError signal,
    // so the controller handles it via onErrorResume.
    @PostMapping(
        path = "/accounts/reactive",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> createReactive(
            @Valid @RequestBody Mono<AccountInput> input) {

        return input
                .map(AccountController::created)
                .onErrorResume(WebExchangeBindException.class, ex -> {
                    Map<String, Object> error = new LinkedHashMap<>();
                    error.put("code", "LOCAL_VALIDATION_ERROR");
                    error.put("fieldCount",
                            ex.getBindingResult().getFieldErrorCount());
                    return Mono.just(
                            ResponseEntity.badRequest().body(error)
                    );
                });
    }

    // Direct constraint -> WebFlux 6.1+ method validation.
    @GetMapping("/pages/{page}")
    public Mono<Map<String, Integer>> page(
            @PathVariable("page") @Min(1) int page) {

        return Mono.just(Map.of("page", page));
    }

    private static ResponseEntity<Map<String, Object>> created(
            AccountInput input) {

        Map<String, Object> response = new LinkedHashMap<>();
        response.put("name", input.name());
        response.put("age", input.age());
        response.put("city", input.address().city());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(response);
    }
}
```

Detailed analysis:

- `create(...)` accepts a direct DTO; on validation failure, Spring handles it before running the method body. Centralized handling lives in `ApiErrorAdvice`.
- `createReactive(...)` accepts a publisher. `onErrorResume(WebExchangeBindException.class, ...)` recovers only from this validation exception type, without catching unrelated service failures.
- `fieldCount` demonstrates extracting data from `BindingResult`; in real APIs, prefer returning a list of field errors with stable codes rather than just a count.
- `page(...)` deliberately places `@Min(1)` **directly on the method parameter**. It triggers method validation in WebFlux 6.1+ and demonstrates `HandlerMethodValidationException`.
- The controller does **not** carry class-level `@Validated`, keeping Spring Framework 6.1+'s built-in method validation path. Putting `@Validated` on the class can switch Spring to a different AOP mechanism.

### 7.7. Global error handler

File `src/main/java/com/example/webfluxvalidation/ApiErrorAdvice.java`:

```java
package com.example.webfluxvalidation;

import java.util.Comparator;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.server.ServerWebInputException;
import reactor.core.publisher.Mono;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public Mono<ResponseEntity<ApiError>> validation(
            WebExchangeBindException exception) {

        List<FieldIssue> fields =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(this::fieldIssue)
                        .sorted(Comparator
                                .comparing(FieldIssue::field)
                                .thenComparing(FieldIssue::code))
                        .toList();

        return Mono.just(
                ResponseEntity.badRequest()
                        .body(new ApiError("VALIDATION_ERROR", fields))
        );
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public Mono<ResponseEntity<ApiError>> methodValidation(
            HandlerMethodValidationException exception) {

        String code = exception.isForReturnValue()
                ? "SERVER_CONTRACT_VIOLATION"
                : "METHOD_VALIDATION_ERROR";

        return Mono.just(
                ResponseEntity.status(exception.getStatusCode())
                        .body(new ApiError(code, List.of()))
        );
    }

    @ExceptionHandler(ServerWebInputException.class)
    public Mono<ResponseEntity<ApiError>> unreadable(
            ServerWebInputException exception) {

        // Do not return exception.getMessage() or raw JSON to the client.
        return Mono.just(
                ResponseEntity.status(exception.getStatusCode())
                        .body(new ApiError("INVALID_PAYLOAD", List.of()))
        );
    }

    private FieldIssue fieldIssue(FieldError error) {
        String code = error.getCode() == null
                ? "invalid"
                : error.getCode();

        return new FieldIssue(error.getField(), code);
    }
}
```

Because `WebExchangeBindException` is a subclass of `ServerWebInputException`, Spring picks the more specific handler when the error is actually `WebExchangeBindException`. The broader `ServerWebInputException` handler covers other input deserialization/binding failures, such as malformed JSON in typical configurations.

Design choices in the demo:

- **VALIDATION_ERROR:** command-object Bean Validation, HTTP 400, with a sorted list of field errors.
- **LOCAL_VALIDATION_ERROR:** same validation nature, yet recovered directly inside the `/accounts/reactive` endpoint's publisher. The advice does not run for locally caught errors.
- **METHOD_VALIDATION_ERROR:** direct constraint on a method parameter failed; for invalid input, HTTP 400.
- **SERVER_CONTRACT_VIOLATION:** constraint on a method return value failed; HTTP 500. Although the demo does not trigger an output violation, the handler is structured properly so server errors are never misreported as 400.
- **INVALID_PAYLOAD:** input that codecs/resolvers cannot read; HTTP 400 matching the exception status in the demo.

**Global errors:** this example intentionally uses `getFieldErrors()` because the DTO only has field constraints. If your project uses class-level constraints, the handler should also read `getGlobalErrors()` so violations are not missed.

## 8. Testing WebFlux with WebTestClient

`WebTestClient` suits reactive controllers; it tests status, headers, and JSON bodies without manual network calls. File `src/test/java/com/example/webfluxvalidation/AccountControllerTest.java`:

```java
package com.example.webfluxvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class AccountControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void validRequestIsCreated() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "age": 25,
                          "address": {"city": "Hanoi"}
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan")
                .jsonPath("$.age").isEqualTo(25)
                .jsonPath("$.city").isEqualTo("Hanoi");
    }

    @Test
    void invalidDtoIsCaughtByAdvice() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": " ",
                          "age": 15,
                          "address": {"city": ""}
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR")
                .jsonPath("$.fields.length()").isEqualTo(3);
    }

    @Test
    void nestedConstraintProducesPropertyPath() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "age": 25,
                          "address": {"city": ""}
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.fields[0].field").isEqualTo("address.city")
                .jsonPath("$.fields[0].code").isEqualTo("NotBlank");
    }

    @Test
    void invalidMonoInputIsRecoveredLocally() {
        client.post().uri("/api/accounts/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "",
                          "age": 15,
                          "address": {"city": "Hanoi"}
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("LOCAL_VALIDATION_ERROR")
                .jsonPath("$.fieldCount").isEqualTo(2);
    }

    @Test
    void validMonoInputPasses() {
        client.post().uri("/api/accounts/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Mai",
                          "age": 30,
                          "address": {"city": "Danang"}
                        }
                        """)
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Mai");
    }

    @Test
    void malformedJsonIsNotValidationError() {
        client.post().uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":\"Lan\",\"age\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INVALID_PAYLOAD");
    }

    @Test
    void directParameterConstraintUsesMethodValidation() {
        client.get().uri("/api/pages/0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("METHOD_VALIDATION_ERROR");
    }

    @Test
    void validMethodParameterPasses() {
        client.get().uri("/api/pages/2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2);
    }
}
```

Run:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

**Expected:** all eight tests PASS when the project has the Gradle wrapper, Java 17, and properly configured dependencies. The `$.fields.length()` check observes error count, while the nested constraint test isolates a specific field path. Because the handler sorts fields, only when input has **one** error on `address.city` should it be asserted at index 0; do not treat raw provider ordering as deterministic.

When the app runs, try:

```bash
./gradlew bootRun
```

With `curl` on a shell supporting POSIX quoting:

```bash
curl -i http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","age":25,"address":{"city":"Hanoi"}}'
```

Expected HTTP `201 Created`, body containing:

```json
{"name":"Lan","age":25,"city":"Hanoi"}
```

If you send:

```bash
curl -i http://localhost:8080/api/accounts \
  -H 'Content-Type: application/json' \
  -d '{"name":" ","age":15,"address":{"city":""}}'
```

Expected HTTP `400 Bad Request` with `code = VALIDATION_ERROR`. The `fields` array lists errors for `name`, `age`, and `address.city`. Do not treat Hibernate Validator's English default messages as a client contract.

**QA note:** the code is a complete sample project in terms of classes, files, imports, and tests, though identical runtime behavior on every machine and dependency version cannot be inferred without running. When upgrading to Spring Boot 4/Framework 7, verify API changes, Java baseline, and exception paths with real tests.

## 9. Handling BindingResult Directly in the Controller

WebFlux also allows accepting `Errors`/`BindingResult` right after a **non-reactive** argument:

```java
@PostMapping("/accounts/manual")
public Mono<ResponseEntity<ApiError>> manual(
        @Valid @RequestBody AccountInput input,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(
                ResponseEntity.badRequest().body(
                        new ApiError("VALIDATION_ERROR", List.of())
                )
        );
    }

    return Mono.just(ResponseEntity.ok(
            new ApiError("OK", List.of())
    ));
}
```

This is an **illustrative method**, not present in `AccountController.java` in section 7. It requires importing `org.springframework.validation.BindingResult` and the remaining types. `BindingResult` must sit **immediately after** the corresponding `@RequestBody AccountInput`; placing another parameter in between prevents Spring from associating errors properly.

**Do not apply that recipe directly to `@RequestBody Mono<AccountInput>`:** when the argument is a publisher, deserialization/validation occurs asynchronously inside the publisher. To handle errors locally, use `onErrorResume`; a `BindingResult` parameter paired with `Mono<DTO>` is not an equivalent substitute in WebFlux.

Also distinguish: if JSON **cannot be parsed**, `BindingResult` cannot handle it because no object exists yet. A `ServerWebInputException` handler or codec-layer error handling is still required.

## 10. Validation Groups in the Reactive Pipeline

`@Valid` normally uses the `Default` group. When a DTO has different rules per operation, place Spring's `@Validated` directly on the argument:

```java
public interface Create {}

public record AccountInput(
        @NotBlank(groups = Create.class) String name,
        @NotNull(groups = Create.class) Integer age
) {}

@PostMapping("/accounts")
public Mono<Void> create(
        @Validated(Create.class)
        @RequestBody Mono<AccountInput> input) {

    return input.then();
}
```

This is an **illustrative snippet**, not meant to replace the demo classes in section 7. When `Create` is selected, constraints belonging to `Default` **are not automatically included**, unless appropriate group inheritance or a sequence is configured. `@Validated` is a Spring annotation, not a separate validation provider.

If the controller has direct method constraints or return constraints, Framework 6.1+ **method validation** may be selected, changing the exception path. Avoid putting `@Validated` on the controller class merely to make `@Valid @RequestBody` run: it can route the controller through AOP method validation, making it unpredictable whether the handler triggers `WebExchangeBindException` or an AOP exception without testing.

### 10.1. Do not assume Mono<T> is already "valid" upon creation

A `Mono<AccountInput>` can exist before the request body has even been read or validated. Validation only executes when the publisher is subscribed and flows through the relevant operators. Therefore:

- Place side effects **after** the data-receiving/validation step.
- Do not call `subscribe()` manually inside a controller to "force validation to run", as that decouples lifecycle, errors, and cancellation from WebFlux.
- **Return the publisher** to the framework; Spring handles subscribing and mapping signals.
- On invalid input, use `onErrorResume` to build a 400 response or propagate to `@RestControllerAdvice`.
- Never call `block()` inside a WebFlux handling flow just to unwrap the DTO, as it can block the event loop and hurt performance.

## 11. Handling @RequestPart and Multipart in WebFlux

In Spring WebFlux, file parts are normally represented by `org.springframework.http.codec.multipart.FilePart`, **not** Servlet MVC's `MultipartFile`. Example handler receiving JSON metadata and a file:

```java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public Mono<ResponseEntity<String>> upload(
        @Valid @RequestPart("metadata") Mono<DocumentMetadata> metadata,
        @RequestPart("file") FilePart file) {

    return metadata.map(value ->
            ResponseEntity.ok("metadata:" + value.title()))
        .onErrorResume(
            WebExchangeBindException.class,
            ex -> Mono.just(
                ResponseEntity.badRequest().body("Invalid metadata"))
        );
}
```

This is an **illustrative method**, assuming `DocumentMetadata` is a record with `@NotBlank String title` and the controller imports `FilePart` and Spring annotations. It does not save the file; in real applications, you must process the upload stream and verify size, actual Content-Type, filename, permissions, and safe storage.

For a metadata part to be JSON-decoded by a converter, **the part's Content-Type must be application/json**. If the client sends JSON as text/plain, Spring may lack a matching message reader to deserialize `DocumentMetadata`; that failure is not an `@NotBlank` violation.

`@RequestPart` in annotated WebFlux can apply `@Valid` and produce `WebExchangeBindException` when the metadata object is invalid; `onErrorResume` handles the signal when using `Mono<Metadata>`. For very large multiparts, WebFlux also offers `PartEvent` and data buffer streams; you must **consume or release buffers properly**, rather than buffering unboundedly before validating.

## 12. Functional Endpoints: No Automatic @Valid Argument Resolution

A WebFlux.fn route:

```java
RouterFunction<ServerResponse> routes = RouterFunctions.route()
        .POST("/functional/accounts", request ->
                request.bodyToMono(AccountInput.class)
                        .flatMap(input -> ServerResponse.ok()
                                .bodyValue(input.name())))
        .build();
```

This is a snippet in Java configuration needing imports for `RouterFunction`, `RouterFunctions`, and `ServerResponse`; it is not a standalone app. Here `bodyToMono(AccountInput.class)` **only deserializes** and does not automatically invoke Bean Validation like annotated `@Valid @RequestBody`.

To validate inside a functional handler, inject `jakarta.validation.Validator` and call:

```java
return request.bodyToMono(AccountInput.class)
        .flatMap(input -> {
            var violations = validator.validate(input);
            if (!violations.isEmpty()) {
                return ServerResponse.badRequest()
                        .bodyValue(Map.of("code", "VALIDATION_ERROR"));
            }
            return ServerResponse.ok()
                    .bodyValue(Map.of("name", input.name()));
        });
```

This is an **illustrative handler body**, assuming `validator` is injected and `request` is a `ServerRequest`. It shows that calling `Validator#validate` is synchronous yet placed at a deliberate point in the reactive pipeline. For custom validation involving blocking I/O such as JDBC queries, never run blocking work on an event-loop thread.

Exceptions thrown inside WebFlux.fn are not automatically caught by `@ControllerAdvice` for annotated controllers. Normalize errors in functional handlers/filters or an appropriate WebFlux `WebExceptionHandler`, and test error paths with `WebTestClient`.

## 13. Designing JSON Errors for Clients and ProblemDetail

### 13.1. Stable API error codes

A validation error response should present:

```json
{
  "code": "VALIDATION_ERROR",
  "fields": [
    {"field": "address.city", "code": "NotBlank"},
    {"field": "age", "code": "Min"}
  ]
}
```

Use field paths and codes so clients can highlight form fields. Never return rejected values when they may contain passwords, tokens, or sensitive data. For class-level constraints, include global error reporting—such as entries with `field = null` or a dedicated `objectErrors` structure.

When localization is needed, clients can translate from stable error codes, or the server can interpolate messages via `MessageSource`/locale. **Never** use exact Vietnamese or English message text as client branching logic.

### 13.2. Spring Problem Details (RFC 9457)

Spring 6 supports `ProblemDetail` with standard fields `type`, `title`, `status`, `detail`, and `instance`. You can:

- Subclass WebFlux's `ResponseEntityExceptionHandler` to leverage built-in error response infrastructure;
- Or write `@ExceptionHandler` methods returning `ProblemDetail`;
- Or retain a custom DTO like the demo's `ApiError` to preserve existing contracts.

Do not assume every `WebExchangeBindException` automatically serializes to JSON containing `fields` like the demo. Default responses depend on Spring/Boot version, ProblemDetail settings, and global error customization.

### 13.3. Prefer error codes over exception class names

Clients should not know internal Java classes like `WebExchangeBindException`, `ServerWebInputException`, or `HandlerMethodValidationException`. Those are server-side Spring details. Clients only need stable codes and HTTP statuses:

| Suggested Error Code | HTTP | Meaning |
| --- | --- | --- |
| `VALIDATION_ERROR` | 400 | Input DTO parsed cleanly but violated constraints |
| `INVALID_PAYLOAD` | 400 | Payload malformed / failed to deserialize |
| `METHOD_VALIDATION_ERROR` | 400 | Direct parameter constraint failed |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | Codec does not support Content-Type |
| `SERVER_CONTRACT_VIOLATION` | 500 | Server returned a value violating return constraint |
| `CONFLICT` | 409 | Conflicting business state such as duplicate email |

These codes **are not Spring default error code names**. They are API design recommendations to prevent coupling frontend logic to locale-specific Jakarta Validation messages.

## 14. Safety and Performance of Validation in Reactive Runtimes

### 14.1. Bean Validation is normally synchronous

Hibernate Validator/Jakarta providers run standard `ConstraintValidator` implementations as synchronous Java work. Even when invoked inside a WebFlux request pipeline, a custom validator performing blocking I/O does **not automatically become non-blocking**.

Do not write:

```java
@Override
public boolean isValid(String value, ConstraintValidatorContext ctx) {
    return jdbcRepository.existsByName(value); // Blocking JDBC on the event loop!
}
```

This is an **anti-example**, not a complete class. Database-backed invariant checks belong in a reactive service (e.g., using R2DBC/WebClient appropriately) with dedicated check and conflict-handling pipelines, rather than abusing `ConstraintValidator#isValid` for blocking I/O on the event loop. Deterministic checks (regex, range, length, format) are the right fit for Bean Validation.

### 14.2. Do not retry validation errors

Retrying `WebExchangeBindException` does not change client input—it only repeats parsing and validation. Retries can help for transient network errors, **not** for known-invalid input. On write flows, avoid side effects before validation and verify idempotency if retries exist at another layer.

### 14.3. Do not let exceptions leak sensitive information

Never return raw:

```java
ex.getBindingResult().getFieldError().getRejectedValue();
ex.getMessage();
```

to the client. They can expose sensitive inputs or internal details. For logging and observability, log only field names, error codes, and request correlation IDs where appropriate—never full bodies, passwords, or uploads.

### 14.4. Limit input size

Because JSON must be decoded into an object before validation, `@Size(max = ...)` constraints **are not enough** to protect against oversized requests before parsing. Configure request size limits, codec memory limits like `spring.codec.max-in-memory-size`, multipart limits, parser nesting limits, and timeouts per deployment profile. Do not collect an entire `Flux<DataBuffer>` into an unbounded buffer before checking size.

### 14.5. Cancellation and side effects

In Reactor, client disconnection can cancel the publisher. Never place database writes, email sending, or other side effects **before** data has passed validation. And do not assume `onErrorResume` after a side effect automatically rolls back committed writes. Transaction and authorization invariants must still be enforced at the appropriate layers.

## 15. Symptom-Based Debugging

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| Invalid DTO still gets HTTP 200/201 | Missing `@Valid`, provider, or binding took a different path | Check parameter annotations, validation starter, WebTestClient |
| Malformed JSON misses `@ExceptionHandler(WebExchangeBindException)` | Parse error occurred before Bean Validation | Catch `ServerWebInputException`/appropriate codec error |
| `onErrorResume` in controller never runs | Controller uses direct DTO, error occurred before method invocation | Switch to `Mono<DTO>` for local recovery or use advice |
| `BindingResult` misses errors for `Mono<DTO>` | Reactive argument is handled as a publisher | Use `onErrorResume` |
| Nested field is not reported | Missing `@Valid` on nested property | Add `@Valid`, test `address.city` |
| `@Min` does not catch null | `@Min` permits null | Add `@NotNull` |
| Handler catches all errors and returns 400 | Overly broad `onErrorResume(Throwable.class, ...)` | Catch strictly WebExchangeBindException and keep 5xx distinct |
| Method argument `@Min` raises a different exception | WebFlux 6.1+ built-in method validation | Handle `HandlerMethodValidationException` |
| Class-level `@Validated` on controller changes error path | AOP method validation is intercepting | Review annotations, version, proxies, and tests |
| WebFlux file upload fails with type error | Imported MVC `MultipartFile` or missing part Content-Type | Use `FilePart`/`Part`, test multipart |
| Both Spring MVC and WebFlux starters present | Boot selects Servlet MVC as web application | Inspect dependencies; remove unneeded starter or configure reactive explicitly |
| Oversized body fails before `@Valid` | Codec/memory/request size limit | Configure size limits; do not treat as a field violation |
| WebFlux.fn does not produce `WebExchangeBindException` | No annotated argument validation | Call validator explicitly and map HTTP error |

### Concise investigation steps

1. Confirm whether the runtime is truly **Spring WebFlux** or Servlet MVC.
2. Locate the entrypoint: annotated controller `@RequestBody`/`@RequestPart` or functional `ServerRequest`.
3. Determine whether the argument is a **direct DTO** or `Mono<DTO>`.
4. Distinguish parse/conversion errors, Bean Validation failures, and direct method constraints.
5. Identify where the error is handled: local `onErrorResume`, `@RestControllerAdvice`, `WebExceptionHandler`, or Spring Boot default.
6. Verify the HTTP status/error code seen by clients alongside server logs with correlation IDs.
7. Write `WebTestClient` tests for each failure mode rather than asserting only a generic HTTP 400.

## 16. Review Questions and Answers

**Q1.** When does WebFlux typically raise `WebExchangeBindException`?

When a command object of an annotated controller is bound/deserialized successfully and then fails Bean Validation requested via `@Valid`/`@Validated`, provided it is not handled by an adjacent `Errors`/`BindingResult` or superseded by method validation.

**Q2.** Why does a `try/catch` around `Mono.map` not always catch validation errors?

Because the error is emitted **when the publisher is subscribed**, not necessarily when the `Mono` object is constructed. Use `onErrorResume` or let Spring exception resolution handle it.

**Q3.** What is the difference between `@Valid @RequestBody AccountInput` and `@Valid @RequestBody Mono<AccountInput>`?

A direct DTO argument must normally resolve before invoking the handler and errors go through exception resolvers; a publisher argument carries errors into the pipeline, making local handling with Reactor error operators convenient.

**Q4.** Why should you not catch `WebExchangeBindException` for syntactically invalid JSON?

Because no Java object has been fully deserialized yet; the error usually comes from the message reader/codec, such as `ServerWebInputException`.

**Q5.** Why does `@Min(18)` not replace `@NotNull`?

Under Jakarta Validation, `@Min` considers null valid; rejecting missing values requires another constraint.

**Q6.** How does `HandlerMethodValidationException` differ from `WebExchangeBindException`?

One covers **method validation** with direct constraints on parameters/return values; the other covers **validation of a single command-object argument**. Since Spring 6.1+, WebFlux applications should handle both depending on handler signatures.

**Q7.** Should rejected values from `FieldError#getRejectedValue()` be returned?

Not by default. Those values may contain secrets or PII; returning field names and stable error codes is safer.

**Q8.** Does `@ControllerAdvice` automatically validate objects in WebFlux.fn?

No. Functional handlers use `ServerRequest` and must explicitly invoke `Validator` and build error responses in their pipeline, or rely on an appropriate general web error handler.

## 17. Implementation Checklist

1. Use `spring-boot-starter-webflux` and `spring-boot-starter-validation`; confirm Servlet MVC is not accidentally active.
2. Separate input DTOs from domain entities; use appropriate Jakarta constraints and `@Valid` for nested objects.
3. Decide between a direct DTO or `Mono<DTO>` based on whether local reactive recovery is needed.
4. For direct DTOs, use `@RestControllerAdvice` to handle `WebExchangeBindException` and standardize HTTP 400 responses.
5. For `Mono<DTO>`, use `onErrorResume(WebExchangeBindException.class, ...)` when local fallback is needed; never catch `Throwable` broadly.
6. Handle malformed JSON and input conversion errors separately from Bean Validation; do not force every failure into `VALIDATION_ERROR`.
7. When using direct method constraints, support `HandlerMethodValidationException`, returning 400 for input and 500 for return violations.
8. For multipart, distinguish WebFlux's `FilePart` from MVC's `MultipartFile`; ensure JSON parts carry the proper media type.
9. Avoid blocking I/O in custom validators or on the WebFlux event loop; never call `block()` or manual `subscribe()` in controllers.
10. Never echo rejected values or stack traces; sanitize logs and traces of sensitive data.
11. Enforce request size, codec memory, multipart, and timeout limits to guard against huge inputs before validation.
12. Write `WebTestClient` tests for happy paths, field/nested violations, malformed JSON, local recovery, method validation, and multipart if used.
13. Track behavior across Spring/Boot upgrades: exception types and built-in method validation evolved starting in Framework 6.1.
14. For functional endpoints, explicitly decide where `Validator` runs and how violations map to `ServerResponse`.

**Conclusion:** `WebExchangeBindException` represents **command-object binding/Bean Validation failures in WebFlux**, carrying a `BindingResult` and defaulting to HTTP 400. Proper reactive handling means recognizing that errors can travel as `onError` signals in `Mono`/`Flux`, recovering selectively with `onErrorResume` or delegating to `@RestControllerAdvice`. Distinguish it from codec errors (`ServerWebInputException`) and method validation (`HandlerMethodValidationException`), keeping your error contract safe, consistent, and covered by `WebTestClient` tests.

## References

- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html): `HttpMessageReader`, validation, and reactive arguments.
- [Spring Framework — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html): `WebExchangeBindException` vs `HandlerMethodValidationException`.
- [Spring Framework — WebFlux Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html): `@RequestPart`, `FilePart`, and `PartEvent`.
- [Spring Framework — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, WebFlux `ResponseEntityExceptionHandler`.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-functional.html): `ServerRequest`, `ServerResponse`, reactive routes.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@AutoConfigureWebTestClient` and `@WebFluxTest`.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, `onErrorMap`, `doOnError`, and terminal error rules.
