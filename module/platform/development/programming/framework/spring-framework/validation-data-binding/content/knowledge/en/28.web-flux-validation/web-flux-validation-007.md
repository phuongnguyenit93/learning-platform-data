# HandlerMethodValidationException in Spring WebFlux Controllers

## 1. Scenario: HTTP 400 Can Come from Two Different Validation Mechanisms

In a **Spring WebFlux** controller, a request can be validated at the **individual argument level** or at the **whole-method level**. Since Spring Framework **6.1**, WebFlux supports built-in method validation for controllers declared with `@RequestMapping`, without requiring an AOP proxy.

Two important exceptions to distinguish:

- **`WebExchangeBindException`**: typically thrown when Spring reads/binds **a single command object** annotated with `@Valid` or `@Validated`, such as `@Valid @RequestBody CreateBookingRequest request`, and that object violates a constraint.
- **`HandlerMethodValidationException`**: thrown when validation applies **at the method level**, such as having `@Min(1)`, `@NotBlank`, `@Pattern`, or `@NotNull` **directly on controller parameters**, or a constraint on the return value.

Although both can result in **400 Bad Request**, they carry different error structures. `WebExchangeBindException` is tied to a `BindingResult` for **one object**; `HandlerMethodValidationException` holds a list of `ParameterValidationResult` entries for **method parameters** and supports inspecting errors by parameter type via `visitResults(...)`.

Example of two signatures:

```java
// Individual argument validation:
@PostMapping("/bookings")
Mono<String> create(@Valid @RequestBody CreateBookingRequest request) {
    return Mono.just("ok");
}

// Built-in method validation:
@GetMapping("/bookings")
Mono<String> list(@RequestParam @Min(1) int page) {
    return Mono.just("page=" + page);
}
```

These are two **controller fragments** illustrating the mechanisms, not a standalone project. In `create`, `@Valid` triggers constraints inside the DTO. In `list`, `@Min` placed directly on the method parameter triggers method validation. `@Valid` **is not a constraint** on the parameter itself; it primarily asks to cascade into the object to check its inner constraints.

**Scope:** this lesson uses Spring WebFlux 6.1–6.2, Java 17+, Jakarta Validation (package `jakarta.validation.*`), and Spring Boot 3.x. Do not confuse **WebFlux's** `WebExchangeBindException` with **Spring MVC's** `MethodArgumentNotValidException`. Both stacks share the `HandlerMethodValidationException` concept, yet have different request-processing pipelines.

## 2. Where Does Method Validation Actually Occur?

In a WebFlux annotated controller, the processing flow can be illustrated as:

```text
HTTP request
     |
     v
DispatcherHandler -> HandlerMapping -> RequestMappingHandlerAdapter
     |
     v
Resolve controller method arguments
     |                           |
     |                           +--> @RequestParam / @RequestHeader:
     |                           |       read and convert scalar value
     |                           |
     |                           +--> @RequestBody:
     |                                   HttpMessageReader, JSON decoder
     |
     +--> Failed to read/convert? -> read or binding error
     |
     v
If only @Valid / @Validated on command object
     |
     +--> individual object validation
     |           |
     |           +--> WebExchangeBindException if errors exist
     |
     v
If direct constraint exists on method parameter / return value
     |
     +--> built-in method validation
                 |
                 +--> HandlerMethodValidationException if errors exist
     |
     v
Controller method / reactive response handling
```

This diagram is a **conceptual model**; internal ordering also depends on argument types, reactive values, data binding, and whether errors are emitted before or after subscription. Specifically, WebFlux can resolve `Mono<T>`/`Flux<T>` asynchronously and emit errors within the reactive pipeline, so do not assume every exception is thrown immediately when Java invokes the method.

### When does method error take precedence over object error?

Under Spring WebFlux's built-in mechanism, **method validation covers both** direct parameter constraints **and** nested constraints inside `@Valid`-annotated objects. Thus, if a controller has a direct constraint on one parameter, it can **supersede the individual validation branch** and report `HandlerMethodValidationException` even when another `@Valid` DTO is also invalid.

Example:

```java
@PostMapping("/bookings")
Mono<Void> create(
        @RequestParam @Min(1) int location,
        @Valid @RequestBody CreateBookingRequest body) {
    return Mono.empty();
}
```

The snippet above is illustrative only. With `location=0`, method validation covers the direct `@Min`. If the DTO also has invalid fields simultaneously, Spring can aggregate errors across multiple parameters under `HandlerMethodValidationException`. However, if the body fails to deserialize into the DTO, the body read error happens earlier; there is no valid object to validate under Bean Validation.

## 3. Comparison Table: WebFlux Validation vs Other Input Errors

| Scenario | Mechanism | Typical Exception | Typical Status |
| --- | --- | --- | --- |
| `@Valid @RequestBody Dto`, object decoded but field invalid | Individual Bean Validation | `WebExchangeBindException` | 400 |
| `@Valid @ModelAttribute Form`, field invalid | Individual object validation | `WebExchangeBindException` | 400 |
| `@Valid @RequestPart Dto`, part object invalid | Individual object validation | `WebExchangeBindException` | 400 |
| `@RequestParam @Min(1) int page` with `page=0` | Built-in method validation | `HandlerMethodValidationException` | 400 |
| `@RequestHeader @Pattern(...) String region` fails pattern | Built-in method validation | `HandlerMethodValidationException` | 400 |
| Method returns value violating return constraint | Built-in return-value validation | `HandlerMethodValidationException` | **500** |
| `page=abc` with `int page` | Conversion before method validation | Usually `ServerWebInputException` or related input error | 400 |
| Missing required parameter from `@RequestParam(required=true)` | Argument resolution | Usually `ServerWebInputException`/missing value error | 400 |
| Malformed or non-deserializable JSON | Reactive codec / message reader | Usually wrapped as `ServerWebInputException`, cause like `DecodingException` | 400 |
| Unsupported `Content-Type` | Media type negotiation | `UnsupportedMediaTypeStatusException` | 415 |
| Constraint on service bean using AOP proxy | Service method validation | May be `ConstraintViolationException` or `MethodValidationException` | Application-dependent |

**Do not use a single `@ExceptionHandler(HandlerMethodValidationException.class)` for every HTTP 400 error.** This handler only catches errors from built-in controller method validation. Other errors require their appropriate handlers.

### Why do return-value violations return 500?

Parameter constraints typically represent **client request violations** → 400. Return-value constraints represent **the server returning a result violating its declared contract** → 500. `HandlerMethodValidationException#getStatusCode()` distinguishes the two cases; `isForReturnValue()` indicates whether the failure belongs to the return value.

Do not hardcode every `HandlerMethodValidationException` to 400. When writing custom handlers, **preserve `ex.getStatusCode()`**; if it is a return-value error, avoid leaking internal values in the response.

## 4. Error Metadata Inside HandlerMethodValidationException

`org.springframework.web.method.annotation.HandlerMethodValidationException` implements `org.springframework.validation.method.MethodValidationResult` and extends `ResponseStatusException`. Key APIs to know:

| API | Meaning |
| --- | --- |
| `getStatusCode()` | Corresponding HTTP status: typically 400 for input, 500 for return constraint |
| `isForReturnValue()` | Distinguishes return-value validation from argument validation |
| `getMethod()` | The Java method being validated |
| `getParameterValidationResults()` | List of validation results grouped by parameter |
| `getCrossParameterValidationResults()` | Cross-parameter errors (if any) |
| `visitResults(Visitor visitor)` | Traverses results via callbacks per argument annotation like `@RequestParam`, `@RequestHeader`, `@ModelAttribute` |
| `getBody()` | `ProblemDetail` provided per Spring's `ErrorResponse` contract |

### 4.1. ParameterValidationResult

Each `ParameterValidationResult` represents violations attached to one method parameter. Notably:

- `getMethodParameter()`: returns `MethodParameter` metadata; parameter position can be retrieved with `getParameterIndex()`.
- `getResolvableErrors()`: list of `MessageSourceResolvable` describing the errors; can be interpolated via `MessageSource` per locale.
- `getArgument()`: the validated value. **Never expose it directly in HTTP responses** as it may hold sensitive data.
- For container-typed parameters, Spring may produce separate results per element, with index/key metadata identifying positions inside the container.
- `ParameterErrors` is a subclass for objects with nested property errors; it implements `Errors` so field/global errors can be read similarly to object validation.

Diagram:

```text
HandlerMethodValidationException
  |
  +-- getParameterValidationResults(): List<ParameterValidationResult>
          |
          +-- parameter 0: @RequestParam page
          |       +-- getResolvableErrors(): @Min(1)
          |
          +-- parameter 1: @RequestHeader X-Region
          |       +-- getResolvableErrors(): @Pattern(...)
          |
          +-- parameter 2: @Valid @RequestBody BookingRequest
                  +-- ParameterErrors (if nested errors exist)
                          +-- FieldError("guest")
                          +-- FieldError("nights")
```

The branches above are illustrative. Actual results depend on the controller signature, violated constraints, request argument types, and validation configuration. **Do not assume there is always exactly one result per parameter**, since containers can generate multiple element-level results.

### 4.2. Retrieving parameter positions and error counts

An API-level snippet used **inside a handler** that already has `ex`:

```java
List<Integer> positions = ex.getParameterValidationResults().stream()
        .map(r -> r.getMethodParameter().getParameterIndex())
        .distinct()
        .sorted()
        .toList();

int errorCount = ex.getParameterValidationResults().stream()
        .mapToInt(r -> r.getResolvableErrors().size())
        .sum();
```

This is a fragment requiring `java.util.List` and `HandlerMethodValidationException ex`. This count sums **direct/nested resolvable errors grouped by parameter**, and does not include `getCrossParameterValidationResults()`; if you have custom cross-parameter constraints, include that error group when aggregating.

### 4.3. Traversing with a Visitor

If you want to format errors by input source location, Spring supports a visitor:

```java
ex.visitResults(new HandlerMethodValidationException.Visitor() {
    @Override
    public void requestParam(
            RequestParam annotation,
            ParameterValidationResult result) {
        // Example: attach source="query".
    }

    @Override
    public void requestHeader(
            RequestHeader annotation,
            ParameterValidationResult result) {
        // Example: attach source="header".
    }

    @Override
    public void other(ParameterValidationResult result) {
        // Fallback for results not matching an overridden callback.
    }
});
```

This is a fragment, not a complete Java class. Corresponding imports are `org.springframework.web.bind.annotation.RequestParam`, `RequestHeader`, `org.springframework.validation.method.ParameterValidationResult`, and `HandlerMethodValidationException`. Annotation parameters in callbacks can be `null` in certain API cases, so real handling code must include fallbacks and never assume `annotation.name()` is always non-null.

The visitor also provides callbacks for `@PathVariable`, `@ModelAttribute`, `@RequestBody`, and others depending on version. For objects with nested errors, callbacks can receive `ParameterErrors`. Iterating `getParameterValidationResults()` directly is usually enough for simple API error schemas; the visitor is useful when explicit input-source tagging is needed.

## 5. Runnable Java 17 Example: Spring Boot 3 + WebFlux

We build a minimal WebFlux application with:

- `GET /bookings?page=...` and header `X-Region`: two direct constraints on a controller method to trigger `HandlerMethodValidationException`.
- `POST /bookings` receiving an `@Valid @RequestBody` DTO: DTO-only constraint failures trigger `WebExchangeBindException`.
- `@RestControllerAdvice` with two handlers returning **two distinct error codes**.
- `WebTestClient` testing the happy path, query/header constraints, DTO constraints, and malformed JSON.

### 5.1. Project structure

```text
webflux-method-validation/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── WebFluxValidationApplication.java
    │   ├── BookingRequest.java
    │   ├── BookingController.java
    │   └── ValidationAdvice.java
    └── test/java/demo/
        └── BookingControllerTest.java
```

### 5.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>webflux-method-validation</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
```

**Important:** use only `spring-boot-starter-webflux` in this project; do not accidentally add `spring-boot-starter-web`. When both starters are present, Spring Boot defaults to Spring MVC for the web application, in which case you would be testing a different pipeline. `spring-boot-starter-validation` provides the Jakarta Validation provider required to enforce constraints.

### 5.3. WebFluxValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxValidationApplication.class, args);
    }
}
```

### 5.4. BookingRequest.java

```java
package demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record BookingRequest(
        @NotBlank String guest,
        @NotNull @Min(1) Integer nights
) {}
```

`@NotBlank` rejects `guest` when `null`, `""`, or whitespace-only. `@NotNull` rejects `nights=null`; `@Min(1)` rejects numbers below 1. If JSON contains `"nights":"abc"`, the codec can fail **before Jakarta Validation runs**.

### 5.5. BookingController.java

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Pattern;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class BookingController {

    // Has direct constraints on method parameters.
    // Do not place @Validated at class level so built-in validation is used.
    @GetMapping("/bookings")
    public Mono<Map<String, Object>> list(
            @RequestParam @Min(1) int page,
            @RequestHeader("X-Region")
            @Pattern(regexp = "EU|APAC") String region) {

        return Mono.just(Map.of(
                "page", page,
                "region", region
        ));
    }

    // Only @Valid on DTO; no direct parameter constraints.
    @PostMapping("/bookings")
    public Mono<ResponseEntity<Map<String, Object>>> create(
            @Valid @RequestBody BookingRequest request) {

        return Mono.just(ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "guest", request.guest(),
                        "nights", request.nights()
                )));
    }
}
```

Explanation:

- `@Min(1)` and `@Pattern(...)` sit **directly on method parameters** of `list(...)`, so WebFlux selects method validation after parameter resolution.
- When `page=0` or `X-Region=OTHER`, constraints fail and `HandlerMethodValidationException` is routed to exception handling.
- `create(...)` only has `@Valid` on the command object, so failures on `guest`/`nights` alone result in `WebExchangeBindException`.
- Both methods return `Mono`, representing reactive responses. The demo uses `Mono.just(...)` since there is no I/O; this is not a demonstration of reactive database scalability.
- Spring `@Validated` is not placed at the class level. Adding it can cause Spring to apply method validation through an **AOP proxy** rather than WebFlux's built-in path, altering exception types and behavior.

### 5.6. ValidationAdvice.java

```java
package demo;

import java.util.List;
import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Map<String, Object>> handleMethod(
            HandlerMethodValidationException ex) {

        List<Integer> positions = ex.getParameterValidationResults()
                .stream()
                .map(result ->
                        result.getMethodParameter().getParameterIndex())
                .distinct()
                .sorted()
                .toList();

        int count = ex.getParameterValidationResults()
                .stream()
                .mapToInt(result -> result.getResolvableErrors().size())
                .sum();

        String code = ex.isForReturnValue()
                ? "RETURN_CONSTRAINT"
                : "METHOD_CONSTRAINT";

        // Preserve original status: input=400, return value=500.
        return ResponseEntity.status(ex.getStatusCode())
                .body(Map.of(
                        "code", code,
                        "parameters", positions,
                        "count", count
                ));
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<Map<String, Object>> handleBody(
            WebExchangeBindException ex) {

        List<String> fields = ex.getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return ResponseEntity.status(ex.getStatusCode())
                .body(Map.of(
                        "code", "BODY_CONSTRAINT",
                        "fields", fields
                ));
    }
}
```

**Practical notes:**

- The handlers return `ResponseEntity` synchronously, which **is supported by WebFlux** because they build a small body right inside the exception handler without blocking I/O. If a handler needs async I/O, it can return `Mono<ResponseEntity<?>>`.
- `getParameterValidationResults()` groups errors by parameter; `getResolvableErrors()` is the list of message-interpolatable errors.
- The example returns **parameter indices** rather than raw user input or annotation messages. Thus responses remain deterministic with the method signature and avoid leaking sensitive values.
- `isForReturnValue()` preserves server-side error codes. Never force every error to 400.
- `WebExchangeBindException#getFieldErrors()` gives field names from a DTO. The example returns only `fields`, never exposing rejected values to clients.
- These are **two distinct handlers**; do not merge them by forcing `WebExchangeBindException` into `HandlerMethodValidationException` or vice versa.

In apps using a configured `ResponseEntityExceptionHandler`/Problem Details, you may need `@Order` on `@ControllerAdvice` so custom handlers take precedence per your API contract. Avoid defining two competing handlers for the same exception at the same precedence.

### 5.7. BookingControllerTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class BookingControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void validQueryAndHeader() {
        client.get()
                .uri("/bookings?page=2")
                .header("X-Region", "EU")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.page").isEqualTo(2)
                .jsonPath("$.region").isEqualTo("EU");
    }

    @Test
    void invalidPageUsesHandlerMethodValidationException() {
        client.get()
                .uri("/bookings?page=0")
                .header("X-Region", "EU")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("METHOD_CONSTRAINT")
                .jsonPath("$.parameters[0]").isEqualTo(0)
                .jsonPath("$.count").isEqualTo(1);
    }

    @Test
    void twoMethodArgumentsCanHaveValidationErrors() {
        client.get()
                .uri("/bookings?page=0")
                .header("X-Region", "OTHER")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("METHOD_CONSTRAINT")
                .jsonPath("$.parameters[0]").isEqualTo(0)
                .jsonPath("$.parameters[1]").isEqualTo(1)
                .jsonPath("$.count").isEqualTo(2);
    }

    @Test
    void invalidDtoUsesWebExchangeBindException() {
        client.post()
                .uri("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"guest\":\"\",\"nights\":0}")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("BODY_CONSTRAINT")
                .jsonPath("$.fields[0]").isEqualTo("guest")
                .jsonPath("$.fields[1]").isEqualTo("nights");
    }

    @Test
    void validDtoIsCreated() {
        client.post()
                .uri("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"guest\":\"Lan\",\"nights\":3}")
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.guest").isEqualTo("Lan")
                .jsonPath("$.nights").isEqualTo(3);
    }

    @Test
    void malformedJsonIsNotAConstraintViolation() {
        client.post()
                .uri("/bookings")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"guest\":,}")
                .exchange()
                .expectStatus().isBadRequest();
        // Do not assert BODY_CONSTRAINT / METHOD_CONSTRAINT:
        // this is a JSON decoding error, not Bean Validation.
    }
}
```

Run tests from the project directory using JDK 17+ and Maven:

```bash
mvn -q test
```

**Expected:** all six tests pass and Maven exits with code 0 under the stated configuration. Do not pin Maven/JUnit stdout as it varies by Surefire version, logging, and environment. Assertions verify HTTP statuses and the **custom error schema produced by `ValidationAdvice`**, making them independent of Hibernate Validator default wording, locale interpolation, or unsorted error ordering.

When running the server:

```bash
mvn spring-boot:run
```

Send illustrative requests (POSIX shell):

```bash
curl -i 'http://localhost:8080/bookings?page=0' \
  -H 'X-Region: EU'

curl -i 'http://localhost:8080/bookings?page=2' \
  -H 'X-Region: OTHER'

curl -i -X POST 'http://localhost:8080/bookings' \
  -H 'Content-Type: application/json' \
  --data '{"guest":"","nights":0}'
```

**Expected sample JSON body** when `page=0` and header is valid:

```json
{
  "code": "METHOD_CONSTRAINT",
  "parameters": [0],
  "count": 1
}
```

When the DTO fails on two fields:

```json
{
  "code": "BODY_CONSTRAINT",
  "fields": ["guest", "nights"]
}
```

JSON object **key** order is not guaranteed by the API; assertions rely only on individual field values and sorted list order. If another class or method also applies AOP validation, a global `ControllerAdvice`, or custom codecs, results may differ and should be verified in the actual configuration.

## 6. Reactive Arguments: @RequestBody DTO vs @RequestBody Mono<DTO>

WebFlux supports reactive publisher argument types, which Spring MVC does not handle with the same request-decoding semantics.

### 6.1. Plain DTO argument

```java
@PostMapping("/sync-body")
public Mono<String> create(
        @Valid @RequestBody BookingRequest body) {
    return Mono.just(body.guest());
}
```

Here WebFlux finishes reading JSON into the DTO before passing the `BookingRequest` Java argument to the controller. If the DTO is invalid and method validation does not cover it, the error is represented by `WebExchangeBindException`.

### 6.2. Mono<DTO> argument

```java
@PostMapping("/reactive-body")
public Mono<String> createReactive(
        @Valid @RequestBody Mono<BookingRequest> body) {

    return body.map(BookingRequest::guest);
}
```

This is a fragment to insert **into an existing controller** (not an endpoint in the runnable demo), requiring imports for `@Valid`, `@RequestBody`, `@PostMapping`, and `Mono`.

In this case, the object is decoded and validated **as the publisher is processed**. Validation errors can arrive as `onError` signals in the reactive stream, typically `WebExchangeBindException` for DTO errors. Consequently:

- Do not declare `Errors`/`BindingResult` immediately after a `Mono<BookingRequest>` argument as if the object were synchronously resolved.
- For Mono inputs, use Reactor operators like `onErrorResume(...)` to convert errors into an appropriate result if that fits the endpoint design.
- If unhandled in the pipeline, let WebFlux's exception handling process it appropriately.
- Never call `block()` to extract a DTO in a reactive controller; blocking on the event loop is an anti-pattern and causes performance issues or exceptions.

Example **fragment** catching only validation errors inside the publisher:

```java
return body
        .map(dto -> "accepted:" + dto.guest())
        .onErrorResume(
                WebExchangeBindException.class,
                ex -> Mono.just("invalid-body")
        );
```

The snippet above demonstrates error-signal handling, **not an HTTP contract to use verbatim**: returning `Mono<String>` can yield 200 OK if no status is set. In real REST APIs, return 400/`ProblemDetail`/`ResponseEntity` appropriately, and avoid turning unrelated errors into 200.

### 6.3. Body-reading errors still differ from validation

Malformed JSON, wrong content types, or oversized bodies can cause errors in the reactive message reader **before a DTO exists**. Do not blindly turn every `ServerWebInputException` into `HandlerMethodValidationException`. To classify:

1. Check media type.
2. Check whether the DTO could be deserialized.
3. If so, check whether object validation or method validation applies.
4. When an exception occurs, inspect its actual class and cause before defining an error code.

## 7. @Valid Only Requests Cascading; It Does Not Trigger Method Validation

Compare:

```java
// Plain @Valid: validates constraints inside the DTO.
public Mono<Void> register(
        @Valid @RequestBody BookingRequest request) {
    return Mono.empty();
}

// @NotNull is a direct constraint, which can trigger method validation
// for the controller method alongside @Valid cascading.
public Mono<Void> registerWithDirectConstraint(
        @NotNull @Valid @RequestBody BookingRequest request) {
    return Mono.empty();
}
```

These are **two illustrative method signatures** requiring distinct mappings in a real app; do not copy both onto the same URL when integrating.

**Key difference:** `@NotNull` is an actual Jakarta `@Constraint` on the parameter. Thus method validation can activate, producing `HandlerMethodValidationException` when violated. `@Valid` is not a constraint and on its own usually only triggers checking inside the object.

Keep in mind `@RequestBody` defaults to `required=true`. When a body is genuinely absent, WebFlux can reject it during argument resolution **before `@NotNull` runs**. For optional payloads, design `required=false`, nullability, and validation per contract rather than expecting one annotation to cover everything.

## 8. Errors and BindingResult When Method Validation Is Active

In Spring WebFlux, a controller can declare `Errors` or `BindingResult` **immediately after** a bound/validated command object, for example:

```java
@PostMapping("/forms")
public Mono<String> submit(
        @Valid @ModelAttribute("form") BookingForm form,
        BindingResult result) {

    if (result.hasErrors()) {
        return Mono.just("invalid");
    }
    return Mono.just("accepted");
}
```

This is a fragment; `BookingForm` must be defined separately. Important rules:

- `BindingResult` must immediately follow the parameter it binds to.
- The controller can be invoked to handle object validation errors locally instead of Spring throwing the default exception, if method conditions allow.
- When built-in method validation applies, the controller is only invoked if **all errors** belong to parameters that have an immediately following `Errors`/`BindingResult`.
- If **any error** occurs on a parameter **without an adjacent `Errors`** (e.g., `@Min(1) @RequestParam int page`), WebFlux throws `HandlerMethodValidationException`.
- With `Mono<BookingForm>`, do not expect an adjacent `BindingResult` to work like a synchronous command object.

Example with multiple error sources:

```java
@GetMapping("/search")
public Mono<String> search(
        @RequestParam @Min(1) int page,
        @Valid @ModelAttribute("filters") FilterForm filters,
        BindingResult filterErrors) {

    if (filterErrors.hasErrors()) {
        return Mono.just("invalid filters");
    }
    return Mono.just("ok");
}
```

This is a fragment. If `page=0`, `filterErrors` does not cover errors on `page`, so the controller may not be invoked regardless of `BindingResult` on `filters`. Designing a **whole-method** error schema requires handling `HandlerMethodValidationException` in addition to per-object errors.

## 9. Return-Value Validation: Server-Side Errors

Suppose a method returning a string has an `@NotBlank` constraint:

```java
@GetMapping("/generated-code")
@NotBlank
public String generateCode() {
    return "";
}
```

This is a WebFlux controller fragment deliberately returning a constraint-violating string for illustration. When built-in method validation evaluates the synchronous return value and `@NotBlank` fails, the exception is `HandlerMethodValidationException` with `isForReturnValue() == true`, defaulting to status **500 Internal Server Error**.

Do not generalize that every `Mono<T>` or `Flux<T>` automatically validates every emitted item just like a plain `String` return value. Reactive wrappers, container-element constraints, and per-signal validation must be designed and tested specifically per data type and framework version support.

**Operations:** a 500 from return-value validation typically signals a service/server bug, not a client input error. In public responses, return a generic message; record details in server logs with a correlation ID without dumping internal data.

## 10. Class-Level @Validated and the Difference Between Built-In and AOP

Spring offers multiple method-validation paths:

1. **Built-in WebFlux controller method validation** (Spring Framework 6.1+): runs inside the controller pipeline and can produce `HandlerMethodValidationException`.
2. **AOP method validation** via `MethodValidationPostProcessor`, typically applied to service beans with class-level Spring `@Validated`: advice runs at the proxy call boundary. Exceptions are usually `ConstraintViolationException` or `MethodValidationException` depending on configuration.
3. **Direct Jakarta Validation API**: code invokes `Validator`/`ExecutableValidator` and handles `ConstraintViolation` sets manually.

To leverage **built-in controller method validation**, Spring docs recommend **not placing class-level `@Validated` on controllers**. That avoids adding an AOP proxy layer at the controller level and keeps the exception surface consistent with WebFlux.

In services, `@Validated` and AOP may still be appropriate. However, never use exceptions from AOP services as proof that controllers will necessarily throw `HandlerMethodValidationException`; they come from separate mechanisms.

**Self-invocation note:** AOP proxies have limitations when a method in the same service calls `this.otherMethod()`; WebFlux's built-in controller method validation triggers when WebFlux invokes the handler method, which does not mean internal Java calls to controller methods are automatically validated either.

## 11. Exception Classification and API Error Response Design

A stable error response should include at minimum:

- `code`: client-facing code, e.g., `METHOD_CONSTRAINT`, `BODY_CONSTRAINT`, `INVALID_REQUEST_BODY`.
- `status`: source-accurate HTTP status, especially keeping 500 for return-value errors.
- `errors` or `parameters`: enough context for clients to fix the right parameter without leaking sensitive values.
- `traceId`/request id if the app uses tracing; never construct it by copying raw input.

Example for a query parameter error:

```json
{
  "code": "METHOD_CONSTRAINT",
  "parameters": [0],
  "count": 1
}
```

This is the schema of section 5's runnable example. In production, you can return a richer object:

```json
{
  "type": "https://example.org/problems/invalid-parameter",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more request parameters are invalid",
  "invalidParams": [
    {"source": "query", "name": "page", "code": "Min"}
  ]
}
```

The second sample is a **suggested contract**, not the output of `ValidationAdvice` in the demo. When using Spring `ProblemDetail` per **RFC 9457**, keep standard fields `type/title/status/detail/instance` and add controlled extension properties. Keys like `invalidParams`/`source` are application conventions, not mandatory RFC properties.

### Do not return getArgument() directly

`ParameterValidationResult#getArgument()` can contain passwords, tokens, document numbers, user profiles, or large objects. Likewise, `WebExchangeBindException`'s `FieldError#getRejectedValue()` can leak sensitive information. Extract **parameter index, field name, normalized error code**, and controlled interpolated messages instead of serializing exceptions.

### Localized validation messages

Errors from `getResolvableErrors()` implement `MessageSourceResolvable`. Spring can use `MessageSource` and the request locale to interpolate messages. Do not test logic by comparing exact English message wording if the app supports multiple locales; asserting error codes, parameter indices, or constraint codes is much more stable.

## 12. Troubleshooting: Why Is HandlerMethodValidationException Not Seen?

### 12.1. Only @Valid on DTO

If there is no direct `@Constraint` on a method parameter or return value, WebFlux normally uses **individual validation**, raising `WebExchangeBindException`. That is expected behavior, not a misconfiguration.

### 12.2. Missing Bean Validation provider

Adding Jakarta annotations to a project without installing Hibernate Validator/a provider can prevent constraints from running as expected. With Spring Boot WebFlux, add `spring-boot-starter-validation` and inspect the dependency tree.

### 12.3. Using class-level @Validated

Spring's `@Validated` on the controller can route method validation through AOP, producing exceptions different from the built-in path. Remove class-level `@Validated` from the controller to retry Spring 6.1+'s built-in path.

### 12.4. Putting @Min on a String that fails conversion

If `@RequestParam int page` receives `page=abc`, type conversion fails to produce an int. Conversion failures may be represented by `ServerWebInputException` rather than `HandlerMethodValidationException`. Test `page=0` to observe `@Min(1)` validation properly.

### 12.5. @RequestBody Mono<Dto> and Errors

With a publisher, the DTO is not decoded yet when the controller receives `Mono<Dto>`. Do not place `Errors` right after `Mono<Dto>` expecting synchronous-object behavior. Use Reactor operators or WebFlux exception handling appropriately.

### 12.6. Has @Valid but forgot @NotNull

`@Valid` does not treat `null` as an error on its own. To require the DTO's presence, verify `@RequestBody(required=true)`, nullability, and `@NotNull` as appropriate. When only inner fields need validation, `@Valid` is sufficient in many cases.

### 12.7. AOP service error mistaken for controller error

Service Bean Validation via AOP proxies can throw `ConstraintViolationException`. A handler catching only `HandlerMethodValidationException` will not catch that exception automatically. Distinguish the source and preserve appropriate statuses.

### 12.8. Unknowingly running Spring MVC instead of WebFlux

If a project has `spring-boot-starter-web` alongside `spring-boot-starter-webflux`, Boot defaults to Servlet/MVC. Check the actual runtime stack (DispatcherServlet vs DispatcherHandler) and dependencies before concluding "WebFlux does not throw the documented exception".

### 12.9. Validation group mismatch

A constraint belonging only to a custom group will not run in the Default group. When using `@Validated(Group.class)`, check active groups/hints and constraint definitions; do not assume every annotation belongs to every group.

### 12.10. Error is on the return value, not the request

If `isForReturnValue() == true`, the appropriate status is usually 500. Do not turn server bugs into "bad request" just to keep all error responses at 400.

### 12.11. Container-element or nested bean errors

A `List`/`Map` parameter can generate multiple `ParameterValidationResult` entries per element position. When mapping to an API response, extract container index/key and field path if needed; do not assume "one parameter = one error".

### 12.12. Handler placed on wrong stack or shadowed by another handler

WebFlux uses `org.springframework.web.reactive.*` for many reactive APIs; Spring MVC uses `org.springframework.web.servlet.*`. Do not extend MVC's `ResponseEntityExceptionHandler` in a WebFlux advice using `WebRequest`/Servlet signatures. When using Spring Boot's built-in global handlers, check `@ControllerAdvice` ordering and Problem Details formatting.

## 13. Testing and Monitoring Strategy

A WebFlux test suite should cover these cases:

| Case | Data | Expected |
| --- | --- | --- |
| Valid query | `page=2` | HTTP 200, controller runs |
| Query violates direct constraint | `page=0` | `HandlerMethodValidationException` → 400 |
| Header violates direct constraint | `X-Region: OTHER` | `HandlerMethodValidationException` → 400 |
| Multiple parameters fail together | `page=0` and `X-Region: OTHER` | Result includes both parameter error groups |
| Invalid `@Valid` DTO | `guest=""` and `nights=0` | `WebExchangeBindException` → 400 |
| Valid `@Valid` DTO | `guest="Lan"`, `nights=3` | HTTP 201 |
| Malformed JSON | `{"guest":,}` | Decoding error 400, not a method constraint |
| Wrong query type | `page=abc` | Conversion error 400, not `@Min` |
| Return value fails constraint | Return value fails `@NotBlank` | Built-in method return validation → 500 (for supported return types) |
| Reactive body | `@Valid @RequestBody Mono<Dto>` | Validation error typically emitted in reactive stream |
| Controller with class-level `@Validated` | AOP proxy may intercept | Test actual exception type; do not assume built-in defaults |
| Missing validation provider | No runtime engine | Should fail build/startup/tests; never assume constraints work automatically |

**Good tests do more than assert 400.** Assert the exact **error code** and error class mapped by your handlers so you know whether the failure came from JSON codecs, individual DTO validation, direct method constraints, or business logic.

In real reactive services, test both request/response flows and **avoid blocking I/O in controllers or exception handlers**. Monitor validation error counts by endpoint, client version, and error code (without logging sensitive raw payloads). If a new client release causes a spike in `METHOD_CONSTRAINT`, it likely indicates a query/header contract mismatch rather than a database outage.

## 14. Implementation Checklist

- [ ] Application genuinely runs **Spring WebFlux**, not MVC due to dependencies.
- [ ] Spring Framework version includes built-in controller method validation (6.1+).
- [ ] Jakarta Validation provider is present, e.g., via `spring-boot-starter-validation`.
- [ ] Distinguish `@Valid`/`@Validated` on command objects from direct `@Min`/`@Pattern` on method parameters.
- [ ] Do not place class-level Spring `@Validated` on controllers if using the built-in path.
- [ ] Handle both `HandlerMethodValidationException` and `WebExchangeBindException` if the error contract must be consistent.
- [ ] For method validation, use `getParameterValidationResults()` or `visitResults(...)`; do not force it into a single DTO `BindingResult`.
- [ ] Preserve status from `ex.getStatusCode()`, especially **400 input / 500 return**.
- [ ] When using `@RequestBody Mono<Dto>`, recognize validation errors travel in the reactive stream and use appropriate Reactor operators.
- [ ] Separate parsing/conversion errors from constraint errors.
- [ ] For `Errors`/`BindingResult` in controllers, place immediately after the target argument and watch for errors on other arguments.
- [ ] Expose only useful error details; never log/serialize raw rejected values or stack traces to clients.
- [ ] Use `WebTestClient` to verify status + JSON response per branch without depending on locale-specific messages.

## 15. Conclusion

**`HandlerMethodValidationException` in WebFlux** signals that Spring performed **method-level validation** on a controller handler, typically triggered by constraints such as `@Min`/`@NotBlank`/`@Pattern` directly on parameters or return values. It organizes errors across **method parameters**, supports `visitResults(...)`, and distinguishes input vs return constraints to pick the right status.

**`WebExchangeBindException`** is the standard error when **an individual command object** from `@Valid @RequestBody`/`@ModelAttribute`/`@RequestPart` is invalid. Handle both for a consistent API error contract; never conflate them with JSON decoding errors, AOP service validation, or Spring MVC exceptions.

The key to debugging: **identify where the constraint sits in the controller signature and when validation runs**, then inspect the exact exception type. Once boundaries are clear, returning normalized responses, localizing errors, and testing with WebTestClient become much more consistent.

## References

- [Spring Framework 6.2 — WebFlux Controller Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux Error Responses / RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — HandlerMethodValidationException API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — ParameterValidationResult API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring Framework 6.2 — WebFlux Config and Validator integration](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/config.html)
- [Spring Framework 6.2 — Bean Validation and AOP-based Method Validation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
