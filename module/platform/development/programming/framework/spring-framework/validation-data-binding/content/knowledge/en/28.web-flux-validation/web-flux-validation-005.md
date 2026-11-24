# Validating a Mono-Wrapped Body by Supported Parameter Types — Spring WebFlux

In **Spring WebFlux**, a controller can accept a JSON body via `@RequestBody` as a regular DTO or as a **reactive wrapper** such as `Mono<Dto>`. With **`@Valid @RequestBody Mono<CreateOrderRequest>`**, WebFlux not only reads and decodes the HTTP body asynchronously: the framework can also apply **Jakarta Bean Validation to the `CreateOrderRequest` instance emitted inside the `Mono`**.

A typical handler:

~~~java
@PostMapping("/orders")
public Mono<OrderResult> create(
        @Valid @RequestBody Mono<CreateOrderRequest> requestMono) {
    return requestMono.map(request ->
        new OrderResult(request.code(), request.quantity()));
}
~~~

This snippet **illustrates the signature** and requires matching DTOs and imports; the full program is in section 5. If the decoded object violates `@NotBlank` or `@Min`, WebFlux typically emits **`WebExchangeBindException`** on the `Mono`'s error channel. If unhandled, Spring defaults to returning HTTP **400 Bad Request**. To recover directly inside the handler, use `onErrorResume(WebExchangeBindException.class, ...)`.

The focus of this lesson is the phrase **"by supported parameter types"**: not every method parameter can be arbitrarily wrapped in `Mono`. `@RequestBody Mono<T>` is supported because reading the request body is an asynchronous operation; `@RequestParam Mono<Integer>` is not automatically a valid signature under the same rules.

**Applicable versions:** Spring Framework 6.2, Spring Boot 3.5, Java 17+, WebFlux on the reactive stack. With Spring MVC on the Servlet stack, argument resolution and validation exception types differ; do not copy blindly.

## 1. Request Body Processing Pipeline in WebFlux

Example HTTP request:

~~~http
POST /api/orders/local HTTP/1.1
Host: localhost:8080
Content-Type: application/json

{"code":"ORD-7","quantity":2}
~~~

Participating components:

1. `DispatcherHandler` selects the handler via `@RequestMapping` / `@PostMapping`.
2. The `@RequestBody` argument resolver uses **`HttpMessageReader`** and configured message codecs to convert JSON bytes into `CreateOrderRequest`.
3. If the parameter is annotated with `@Valid` (or appropriate Spring `@Validated`), the framework uses the Jakarta Validation provider to check the decoded object.
4. If valid, the publisher emits `onNext(CreateOrderRequest)` then `onComplete`, allowing `map`/`flatMap` operators to process it.
5. If a constraint fails, the publisher emits `onError(WebExchangeBindException)` instead of passing an invalid object down the normal branch.

~~~text
HTTP body: application/json
            |
            v
@RequestBody argument resolver (WebFlux)
            |
            v
HttpMessageReader / JSON decoder
            |
            +---- malformed JSON ----> read/decode error
            |
            v
CreateOrderRequest
            |
            v
@Valid -> Jakarta Validator
            |
     +------+------+
     |             |
   Valid        Invalid
     |             |
     v             v
Mono.onNext     Mono.onError(
    DTO          WebExchangeBindException)
     |             |
     v             +---- WebFlux default HTTP 400
map / flatMap     or onErrorResume
     |
     v
Response
~~~

This diagram is **conceptual**; internal classes and subscription timing belong to the framework. The key insight is that **errors occur as signals of a reactive publisher**, unlike a Java method body throwing an exception synchronously when `map(...)` is called.

**Avoid doing the following in a controller:** calling `requestMono.block()` to extract the DTO, calling `subscribe()` manually and returning an empty response, using `Thread.sleep(...)` to wait for the body, or treating `Mono` as a DTO with a `code()` method. Those approaches break the non-blocking flow and make testing difficult.

## 2. "Supported Parameter Type" Is a Prerequisite

Spring WebFlux publishes a table of **supported controller method arguments**. Reactive wrappers are supported for argument resolvers with asynchronous work, notably body reading. **There is no blanket rule that any Java parameter can be turned into `Mono<...>`.**

| Handler Signature | Supported? | Remarks |
|---|---|---|
| `@Valid @RequestBody Mono<OrderDto> body` | **Yes** | Core form: decodes a body into a DTO, validates, and emits in `Mono` |
| `@Valid @RequestBody OrderDto body` | **Yes** | Direct DTO; framework resolves/validates before invoking handler |
| `@RequestBody Flux<MessageDto> messages` | Yes, when content type and codec support multiple elements | Do not assume element-level validation works identically to `Mono` |
| `@Valid @RequestPart("metadata") Mono<MetaDto> metadata` | Yes when the multipart part is decoded as a DTO | This is a named request part, distinct from a single JSON request body |
| `@RequestParam("page") int page` | Yes | WebFlux reads a **query parameter**, no `Mono<Integer>` needed |
| `@PathVariable("id") long id` | Yes | URI template variables are typically resolved directly |
| `@RequestHeader("X-Id") String id` | Yes | HTTP headers do not need a reactive wrapper |
| `@RequestParam("page") Mono<Integer> page` | **Do not assume** | The query parameter resolver does not resolve `Mono` like a body resolver |
| `Mono<ResponseEntity<T>>` as **return type** | Yes | Allows deciding status and body once async processing finishes |
| `ResponseEntity<Mono<T>>` as **return type** | Yes | Status/headers are decided earlier than the body content |

**Why is `@RequestBody` different from `@RequestParam`?** The body may require reading bytes with non-blocking I/O and decoding via `HttpMessageReader`. Query/path/header values are already present in request metadata and have synchronous resolvers at the argument level. WebFlux also has `ConversionService`, but **type conversion does not imply `Mono` support for every annotation**.

### `Mono<T>` or `Flux<T>`?

- `Mono<T>` emits **0 or 1** value: suitable for **one JSON object**.
- `Flux<T>` emits **0 to many** values: suitable for streams when the HTTP codec/content type and API contract are designed for multiple elements.
- A regular JSON array and an NDJSON stream do not necessarily share the same encoding/decoding contract. Do not switch to `Flux<T>` just to return a list, nor assume `Mono<List<T>>` automatically validates each element without proper constraints/cascading.

Spring WebFlux docs explicitly specify reactive type support on `@RequestBody` and arguments requiring async reading; this is a **per-resolver capability**, not a built-in feature of Java generics.

## 3. `@Valid` Goes on the Parameter, Yet Validates the Object Inside Mono

Standard syntax documented by Spring WebFlux:

~~~java
@PostMapping("/accounts")
public Mono<AccountResult> handle(
        @Valid @RequestBody Mono<AccountRequest> accountMono) {
    return accountMono.map(this::toResult);
}
~~~

Explanation:

- `@RequestBody` selects the **HTTP request body** as the source, not the query string.
- `Mono<AccountRequest>` indicates the decoded data arrives via a **single-value publisher**.
- `@Valid` on the **method parameter** triggers validation of the `AccountRequest` produced by the resolver.
- Constraints like `@NotBlank`/`@Min` live inside the **DTO definition**, not attached directly to the `Mono` class.
- `accountMono.map(this::toResult)` receives the DTO **only after it is emitted**.

Do not use `@Valid` as a "non-null input" check: `@Valid` is a **cascade marker**, not `@NotNull`. Requiring the body itself is governed by `@RequestBody(required=true)` and argument resolution. "Body must not be missing", "field must not be null", and "code must be valid per business rules" are three distinct requirements.

### What if `@Valid` is forgotten?

~~~java
@PostMapping("/unchecked")
public Mono<OrderResult> unchecked(
        @RequestBody Mono<CreateOrderRequest> body) {
    return body.map(this::toResult);
}
~~~

This is an illustrative snippet. Without validation triggered at another layer, an object with `code=""` can still be emitted into processing logic, even if `CreateOrderRequest` declares `@NotBlank`. **Having annotations on a DTO does not cause `Mono.just(dto)` to trigger Jakarta Validation automatically.**

### What if there is only a JSON parse error?

A body `{` does not produce a syntactically valid DTO. It is rejected by the decoder **before Bean Validation**. Thus the error can be an input read/decode exception other than `WebExchangeBindException`; do not rely on `getFieldErrors()` to analyze malformed JSON syntax errors.

## 4. Validation Errors Differ Between Reactive Bodies and Direct Bodies

### Direct DTO

~~~java
@PostMapping("/direct")
public OrderResult direct(
        @Valid @RequestBody CreateOrderRequest request) {
    return service.process(request);
}
~~~

WebFlux resolves and validates the DTO before invoking the handler. If invalid, the handler is typically **not invoked**; the exception goes through the error pipeline outside the method or an appropriate `@ExceptionHandler`/`@ControllerAdvice`.

### DTO inside Mono

~~~java
@PostMapping("/reactive")
public Mono<OrderResult> reactive(
        @Valid @RequestBody Mono<CreateOrderRequest> body) {

    return body
        .map(service::process)
        .onErrorResume(
            WebExchangeBindException.class,
            ex -> Mono.just(OrderResult.invalid(
                ex.getFieldErrorCount())));
}
~~~

This is an illustrative snippet requiring matching classes and services. With `Mono<Dto>`, the controller **constructs the pipeline before the body emits a value or error**. Hence `onErrorResume` in the pipeline can handle a validation failure when it is emitted.

**HTTP status warning:** the `Mono<OrderResult>` example above produces a fallback value and can turn the response into HTTP **200** if no status is set. To return **400** on invalid input, use `Mono<ResponseEntity<OrderResult>>` as in section 5's full program, or let the exception reach a global error handler.

### Why not use try/catch?

~~~java
// Anti-example: fails to catch asynchronous errors emitted inside Mono.
try {
    return body.map(service::process);
} catch (WebExchangeBindException ex) {
    return Mono.just(fallback);
}
~~~

`map(...)` assembles the pipeline, whereas the error can be emitted **after the method returns** and the framework subscribes. Use Reactor operators:

| Operator | Meaning | Keep in Mind |
|---|---|---|
| `onErrorResume(WebExchangeBindException.class, handler)` | Recover from error with another publisher | Suitable for building structured 400 responses |
| `onErrorMap(...)` | Transform error type and stay on error channel | Does not turn the response into success |
| `doOnError(...)` | Observe/log the error | Does not consume the error |
| `onErrorReturn(...)` | Return a fixed fallback value | Unsuitable if you need field errors |
| `switchIfEmpty(...)` | Handle an **empty completion** | Empty is not an error signal |

Do not use `onErrorResume(Exception.class,...)` to swallow all decoder, programming, DB connection, and validation errors and return 200. Error boundaries should stay sharp: DTO constraints, malformed JSON, missing body, and domain/service failures normally warrant different responses.

## 5. Runnable Spring Boot Program: Three Ways to Receive a Body

This example uses **Spring Boot 3.5.x + Spring Framework 6.2.x + Java 17+** with **only the WebFlux starter**, without adding the Servlet MVC starter. It provides three endpoints:

- `POST /api/orders/local` accepts `Mono<DTO>` and handles `WebExchangeBindException` inside the publisher, returning **201** or **400**.
- `POST /api/orders/default` also accepts `Mono<DTO>` but lets WebFlux handle the validation error by default as **400**.
- `POST /api/orders/direct` accepts the DTO directly, demonstrating that validation occurs before handler invocation.

### 5.1. Gradle dependencies

In a Spring Boot project with Boot's plugin and dependency version management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The WebFlux starter provides the reactive web stack and Reactor; the validation starter provides the Jakarta Validation implementation. The Java files below require the Spring/Boot classpath: **they cannot be compiled with bare JDK `javac` alone**. Use an existing Boot project's Gradle wrapper or generate one with Spring Initializr.

Do not add `spring-boot-starter-web` to this demo: when both WebFlux and Spring MVC are present, Boot normally prefers the Servlet web application type, and validation will no longer follow the WebFlux pipeline described here.

### 5.2. `MonoBodyApplication.java`

Create `src/main/java/com/example/webfluxmono/MonoBodyApplication.java`:

~~~java
package com.example.webfluxmono;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MonoBodyApplication {

    public static void main(String[] args) {
        SpringApplication.run(MonoBodyApplication.class, args);
    }
}
~~~

### 5.3. `CreateOrderRequest.java`

Create `src/main/java/com/example/webfluxmono/CreateOrderRequest.java`:

~~~java
package com.example.webfluxmono;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String code,
    @Min(1) int quantity
) {
}
~~~

The DTO has two constraints: `code` must have non-whitespace text, and `quantity` must be ≥1. Request:

~~~json
{"code":"","quantity":0}
~~~

decodes into the record, yet **violates both constraints**. Both errors are respective `FieldError` instances; there are no class-level constraints in this demo.

### 5.4. `CreateOrderController.java`

Create `src/main/java/com/example/webfluxmono/CreateOrderController.java`:

~~~java
package com.example.webfluxmono;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public class CreateOrderController {

    @PostMapping(
        path = "/local",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<OrderReply>> createLocally(
            @Valid @RequestBody Mono<CreateOrderRequest> body) {

        return body.map(request ->
                ResponseEntity.status(HttpStatus.CREATED).body(
                    new OrderReply(
                        true, request.code(), request.quantity(), 0)))
            .onErrorResume(
                WebExchangeBindException.class,
                ex -> Mono.just(
                    ResponseEntity.badRequest().body(
                        new OrderReply(
                            false, null, 0,
                            ex.getFieldErrorCount()))));
    }

    @PostMapping(
        path = "/default",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<OrderReply> createWithDefaultError(
            @Valid @RequestBody Mono<CreateOrderRequest> body) {

        return body.map(request ->
            new OrderReply(
                true, request.code(), request.quantity(), 0));
    }

    @PostMapping(
        path = "/direct",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public OrderReply createWithDirectBody(
            @Valid @RequestBody CreateOrderRequest request) {

        return new OrderReply(
            true, request.code(), request.quantity(), 0);
    }

    public record OrderReply(
        boolean accepted,
        String code,
        int quantity,
        int errorCount
    ) {
    }
}
~~~

**Explaining the reactive `/local` path:**

1. `@Valid @RequestBody Mono<CreateOrderRequest>` is a **WebFlux-supported** handler argument.
2. If decoding and validation succeed, `map` runs, creating a `ResponseEntity` with status **201 Created** and `OrderReply(accepted=true,...)`.
3. If validation fails, `map` never receives the DTO; `onErrorResume(WebExchangeBindException.class,...)` returns `Mono.just(ResponseEntity.badRequest().body(...))`.
4. `getFieldErrorCount()` returns the number of field errors. With `code=""` and `quantity=0` in the demo, the result is **2**.
5. `Mono<ResponseEntity<OrderReply>>` allows the status **to be chosen after knowing the outcome**. Do not use `ResponseEntity<Mono<OrderReply>>` if the status must change after validation.
6. The handler never calls `block()`/`subscribe()`. The framework manages subscription and response rendering.

**The `/default` path** has no error recovery, so WebFlux automatically returns HTTP 400 for `WebExchangeBindException`. The default error body varies by Spring Boot configuration, so do not depend on a specific JSON structure.

**The `/direct` path** receives the DTO directly; if validation fails, the method is never invoked to construct `OrderReply`. This is a key difference from handling via Reactor operators in a handler with a `Mono` input.

### 5.5. Running and testing with curl

From the Spring Boot project directory with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Assuming the default port, try a valid request:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/local" \
  -H "Content-Type: application/json" \
  -d '{"code":"ORD-7","quantity":2}'
~~~

Expected HTTP **201 Created**, JSON (key order is not a contract):

~~~json
{
  "accepted": true,
  "code": "ORD-7",
  "quantity": 2,
  "errorCount": 0
}
~~~

Try a request that decodes but fails both constraints:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/local" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Expected HTTP **400 Bad Request**, application-designed JSON:

~~~json
{
  "accepted": false,
  "code": null,
  "quantity": 0,
  "errorCount": 2
}
~~~

Send the same payload to `/default`:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/default" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Expect **HTTP 400** from the framework; there is no guarantee that the default body contains `accepted` or `errorCount`.

Send to `/direct`:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/direct" \
  -H "Content-Type: application/json" \
  -d '{"code":"","quantity":0}'
~~~

Expect **HTTP 400** from DTO validation, though the direct handler has no `Mono` input to attach `onErrorResume` to.

Malformed JSON syntax:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders/local" \
  -H "Content-Type: application/json" \
  -d '{'
~~~

Expect **400** due to a decoder/input error, **not** an `OrderReply` JSON response from the `WebExchangeBindException` branch. No valid DTO was created, so there are no field constraints to evaluate.

Omitting the body for `@RequestBody` with `required=true` (the default) normally also causes WebFlux to reject the request with HTTP 400 during input reading/resolution, rather than instantiating an empty `CreateOrderRequest`.

## 6. Testing with WebTestClient

To truly verify that `@Valid @RequestBody Mono<T>` passes through **argument resolver, JSON decoder, validator, and reactive error channel**, use HTTP integration tests. A unit test calling `controller.createLocally(Mono.just(dto))` directly bypasses Spring request-body validation and can give misleading results.

File `src/test/java/com/example/webfluxmono/CreateOrderControllerTest.java`:

~~~java
package com.example.webfluxmono;

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
class CreateOrderControllerTest {

    @Autowired
    private WebTestClient client;

    @Test
    void validMonoBodyProducesCreatedResponse() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("ORD-7", 2))
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo(true)
            .jsonPath("$.code").isEqualTo("ORD-7")
            .jsonPath("$.quantity").isEqualTo(2)
            .jsonPath("$.errorCount").isEqualTo(0);
    }

    @Test
    void invalidMonoBodyCanBeRecoveredLocally() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo(false)
            .jsonPath("$.errorCount").isEqualTo(2);
    }

    @Test
    void invalidMonoBodyDefaultsToBadRequest() {
        client.post()
            .uri("/api/orders/default")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void directDtoIsAlsoValidated() {
        client.post()
            .uri("/api/orders/direct")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("", 0))
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void malformedJsonIsADecodingError() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{")
            .exchange()
            .expectStatus().isBadRequest();
    }

    @Test
    void missingRequiredBodyIsBadRequest() {
        client.post()
            .uri("/api/orders/local")
            .contentType(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Windows:

~~~powershell
.\gradlew.bat test
~~~

With Spring Boot 3.5/WebFlux/Validation starters and default configuration, all six tests are expected to **PASS**. `RANDOM_PORT` runs a real server; `WebTestClient` sends HTTP requests rather than calling Java methods directly. The tests intentionally **do not** assert on `/default`'s default error body, because Boot/ProblemDetail error JSON can vary; only the custom `/local` response is checked for specific field values.

## 7. Why Do `Errors` or `BindingResult` Not Follow `Mono<Dto>`?

Spring WebFlux documentation allows `Errors`/`BindingResult` for a **non-Mono-wrapped** body argument, given an appropriate method signature:

~~~java
@PostMapping("/form")
public AccountReply form(
        @Valid @RequestBody AccountRequest request,
        org.springframework.validation.Errors errors) {

    if (errors.hasErrors()) {
        return AccountReply.invalid(errors.getErrorCount());
    }
    return AccountReply.success(request);
}
~~~

This is an **illustrative snippet**, requiring `AccountRequest`/`AccountReply` to be defined. When the body is a direct DTO, the framework can resolve and validate before invoking the method and supply `Errors` synchronously.

Do not copy this into:

~~~java
// Anti-example for error-handling intent:
@PostMapping("/wrong")
public Mono<AccountReply> wrong(
        @Valid @RequestBody Mono<AccountRequest> accountMono,
        org.springframework.validation.BindingResult errors) {
    // Cannot assume errors already holds the result
    // of a Mono<AccountRequest> that has not emitted data yet.
}
~~~

With `Mono<Dto>`, the body and validation errors can be emitted **after the handler has been invoked**. A synchronous `BindingResult` next to a reactive argument does not offer the same contract as with a direct DTO. Spring explicitly states that to receive `Errors` right after `@RequestBody`, **the body must not be a Mono**.

Correct approach for a Mono body:

~~~java
return accountMono
    .map(AccountReply::success)
    .onErrorResume(
        WebExchangeBindException.class,
        ex -> Mono.just(
            AccountReply.invalid(ex.getErrorCount())));
~~~

This is an optional snippet; it can build an error body, yet **does not turn the HTTP status into 400** when the return type is merely `Mono<AccountReply>`. Use `Mono<ResponseEntity<AccountReply>>` or let errors propagate to global error handling if HTTP status is part of the contract.

## 8. Understanding `WebExchangeBindException` and Other Errors

`WebExchangeBindException` lives at:

~~~java
import org.springframework.web.bind.support.WebExchangeBindException;
~~~

It represents binding/validation errors on a method argument and carries `BindingResult`-style data. Useful APIs:

~~~java
int allErrors = ex.getErrorCount();
int fieldErrors = ex.getFieldErrorCount();

for (var error : ex.getFieldErrors()) {
    String field = error.getField();
    String messageCode = error.getCode();
    String defaultMessage = error.getDefaultMessage();
}
~~~

The above is a snippet inside a handler with variable `ex`. Use field/message codes to build stable, localized responses; do not rely on error ordering or translated message text.

| API | Meaning |
|---|---|
| `getErrorCount()` | Total field + global/object errors |
| `getFieldErrorCount()` | Number of field error entries, **not necessarily equal to distinct invalid fields** |
| `getFieldErrors()` | Errors bound to specific fields |
| `getGlobalErrors()` | Object-level errors |
| `getFieldError("code")` | One error related to `code`, if present |
| `getAllErrors()` | Errors suitable for Spring message resolution |

If a single field violates two constraints, there can be two `FieldError` entries for that same field. If the DTO declares a class-level constraint, there can be **global errors**. Therefore, do not equate "number of invalid fields" with `getFieldErrorCount()` across all projects.

### Distinguishing decode errors from validation

| HTTP Input | Phase | Typical Behavior |
|---|---|---|
| `{"code":"ORD-7","quantity":2}` | Decode → validate OK | `Mono` emits DTO |
| `{"code":"","quantity":0}` | Bean Validation fails | `WebExchangeBindException`, default HTTP 400 |
| `{` | JSON decode fails | Read/decode error, typically HTTP 400 |
| Missing body with `@RequestBody(required=true)` | Required-body check | Typically HTTP 400 |
| JSON type incompatible with Java property | Decode/convert | Input error before constraints |
| Valid DTO rejected by business policy | Service/domain policy | Application-designed exception/status |
| Direct constraint on another handler parameter | Method validation | May emit `HandlerMethodValidationException` |

One `onErrorResume(WebExchangeBindException.class, ...)` **should not** handle every error listed above. It only handles errors matching that exact exception type. When uniform responses across multiple error kinds are required, implement a Spring WebFlux `@RestControllerAdvice` with dedicated handlers or use `ErrorResponse`/ProblemDetail appropriately.

### Global advice or local recovery?

If only one endpoint needs a custom error response, local recovery is convenient and controls status when returning `Mono<ResponseEntity<T>>`. If multiple controllers must share JSON error formatting, let the exception escape the publisher and use `@RestControllerAdvice`/`@ExceptionHandler(WebExchangeBindException.class)`. **Errors recovered locally will not propagate to global advice**. Choose a deliberate boundary.

## 9. Distinguishing `WebExchangeBindException` from Method Validation

Spring WebFlux 6.1+ also includes **built-in method validation**. `@Valid` on a DTO is a cascade marker, **not a direct constraint**. If a handler only has `@Valid @RequestBody Mono<Dto>`, the usual case is single-argument validation and `WebExchangeBindException`.

If a handler has a direct constraint like `@Min`/`@NotBlank` on another parameter:

~~~java
@PostMapping("/submit")
public Mono<OrderReply> submit(
        @Valid @RequestBody Mono<CreateOrderRequest> body,
        @RequestParam("channel")
        @NotBlank String channel) {
    return body.map(this::toReply);
}
~~~

this is an **illustrative snippet distinct** from the demo app. The direct constraint on `channel` can activate **method validation**, yielding **`HandlerMethodValidationException`** when the corresponding built-in mechanism applies. Do not assume catching `WebExchangeBindException` alone suffices for every signature containing `Mono<Dto>`.

If a controller has **class-level Spring `@Validated`**, method validation may run through an **AOP proxy** instead of WebFlux/MVC 6.1+'s built-in mechanism; exception types and timing can also differ. Do not add class-level `@Validated` unnecessarily to a demo meant to show `@RequestBody Mono<Dto>` validation.

Comparison:

| Environment | Body DTO Validation | Typical Exception |
|---|---|---|
| Spring WebFlux `@Valid @RequestBody Mono<Dto>` | Reactive body resolver + Jakarta Validation | `WebExchangeBindException` inside publisher |
| Spring WebFlux `@Valid @RequestBody Dto` | Argument-level validation | `WebExchangeBindException` at resolution |
| Spring MVC `@Valid @RequestBody Dto` | Servlet MVC argument validation | `MethodArgumentNotValidException` |
| WebFlux/MVC built-in method validation | Direct method constraints + related cascades | `HandlerMethodValidationException` |
| Spring AOP service method validation | `@Validated` bean via proxy | Usually `ConstraintViolationException` by default |

**Key check:** if testing `@Valid @RequestBody Mono<Dto>` expects `MethodArgumentNotValidException` from a Spring MVC example, you are on the wrong web stack or confusing validation paths.

## 10. Performance, Non-Blocking, and Security

### 10.1. Validation is not authorization

`@NotBlank` and `@Min` only guard data shape. An order with a valid code can still be rejected because the user lacks permission, the code is duplicated, or inventory is exhausted. Authorization and domain validation belong in the service/security layer, not solely in DTO constraints.

### 10.2. Avoid blocking custom validators

Jakarta Validation's `ConstraintValidator.isValid(...)` is a **synchronous** API. If a custom validator makes blocking JDBC or HTTP client calls, it can stall the Reactor event loop even when the handler returns `Mono`. Keep structural constraints fast; move I/O-dependent business checks into `flatMap(service::check)` with reactive drivers/clients or an appropriate scheduler.

### 10.3. Do not log rejected secrets

`WebExchangeBindException` can retain rejected values. Never log or expose full request bodies, passwords, or tokens in logs or public responses. Use vetted field names, message codes, and correlation IDs.

### 10.4. Do not treat Mono as a large-body streaming guarantee

A very large JSON object still must be decoded into a DTO within codec/buffer limits. `Mono<Dto>` does not automatically cut memory usage simply because it is wrapped reactively. When continuous streaming is needed, design appropriate HTTP content types and `Flux<T>`, and plan how each element is validated and how errors are handled once a response begins.

## 11. Common Issues and How to Check

| Symptom | Common Cause | Resolution |
|---|---|---|
| `@Valid @RequestBody Mono<Dto>` does not validate fields | Missing provider, wrong annotation placement, DTO lacks constraints | Install validation starter; check `jakarta.validation.*` |
| Invalid DTO still enters service | Body resolver validation not triggered | Put `@Valid` on handler parameter; test via WebTestClient |
| `onErrorResume(WebExchangeBindException.class, ...)` misses body `{` | JSON decoding failure, no DTO created | Handle decoder errors separately or let WebFlux respond |
| `try/catch` around `map` lets errors escape | Errors are emitted when publisher is subscribed | Use Reactor error operators |
| Invalid JSON returns HTTP 200 with `accepted=false` | Returning fallback DTO without changing status | Return `Mono<ResponseEntity<...>>` or use global error handling |
| `BindingResult` after `Mono<Dto>` misbehaves | Validation result is not synchronously available | Use `onErrorResume` in the pipeline |
| `block()` fails or slows down server | Blocking the reactive event loop | Never block; return publisher and use map/flatMap |
| Query constraint error is not `WebExchangeBindException` | Direct method constraint triggers method validation | Inspect `HandlerMethodValidationException` |
| Spring Boot starts MVC instead of WebFlux | Both web and webflux starters present | Use WebFlux-only or explicitly configure application type |
| Test calling Java method directly emits no validation error | Bypasses argument resolver + HTTP pipeline | Use WebTestClient integration tests |
| Default error body test breaks | Framework/locale/problem details config differs | Test status and app-defined contracts |
| `FieldErrorCount` differs from invalid field count | One field has multiple violations or object-level errors exist | Iterate `getFieldErrors()`/`getGlobalErrors()` |
| `@RequestParam Mono<Integer>` fails to resolve | Not all arguments support reactive wrappers | Consult supported method arguments table |
| App stalls after adding custom I/O constraint | Blocking validator on reactive pipeline | Move I/O business checks to reactive service |
| Global exception advice never runs | Local `onErrorResume` already recovered the error | Choose one consistent handling boundary |

**Debug sequence:** verify WebFlux stack → Jakarta provider dependency → supported handler argument → `@Valid` placement → JSON decode success → `WebExchangeBindException` on error channel → `onErrorResume`/global handler location → status decided before or after publisher → end-to-end WebTestClient test.

## 12. Practice Questions

**1. Why does Spring WebFlux support `@Valid @RequestBody Mono<Dto>` without guaranteeing `@RequestParam Mono<Integer>` works too?**

Because reactive wrapper support is a property of **each `HandlerMethodArgumentResolver`**; reading a body involves async I/O, while query params are resolved by a separate mechanism.

**2. Does `@Valid` validate `Mono` itself?**

In this use case, the framework validates **the DTO produced inside the Mono by the decoder**, rather than treating `Mono` as a JavaBean with a `code` field.

**3. Does `Mono.just(dto)` in a unit test automatically check `@NotBlank`?**

No. Reactor does not run Bean Validation automatically. Validation must be triggered by a WebFlux resolver, service, or `jakarta.validation.Validator`.

**4. For body `{"code":"","quantity":0}`, which exception is expected?**

`WebExchangeBindException`, because the DTO decodes cleanly but violates both `@NotBlank` and `@Min(1)`.

**5. For body `{`, is it `WebExchangeBindException`?**

Not necessarily. A syntactically invalid body may be rejected by the JSON decoder **before validation**.

**6. Why should `BindingResult` not be placed immediately after `Mono<Dto>`?**

Because validation of the object inside the publisher can happen asynchronously. Use `onErrorResume` instead of a synchronous error holder.

**7. What is the difference between `Mono<ResponseEntity<T>>` and `ResponseEntity<Mono<T>>`?**

The first allows deciding both status and body **after** the publisher produces a result; the latter fixes status/headers **before** the inner publisher emits the body.

**8. When should `flatMap` be used?**

When the downstream action returns a publisher, such as `service.createReactive(request)`. `map` fits lightweight synchronous transformations that do not return a reactive type.

**9. Does adding a direct `@NotBlank` on a query parameter always throw `WebExchangeBindException`?**

No. Built-in method validation may activate and produce `HandlerMethodValidationException`.

**10. Why is testing with WebTestClient better than calling the handler directly?**

It exercises real HTTP codecs, argument resolvers, body validation, the Reactor error channel, and response handling rather than just executing the Java method body.

## 13. Implementation Checklist

- [ ] Application actually runs Spring WebFlux with a Spring 6/Boot 3-compatible validation provider.
- [ ] Request carries a JSON object: use `Mono<Dto>` and `@RequestBody` on the handler parameter.
- [ ] Place `@Valid` or `@Validated` properly, with constraints on the DTO.
- [ ] Do not arbitrarily wrap query/path/header arguments in `Mono` if the resolver does not support it.
- [ ] Distinguish decode errors, missing bodies, and Bean Validation errors.
- [ ] Handle `WebExchangeBindException` via Reactor operators or a global error handler, not plain `try/catch`.
- [ ] Do not place synchronous `BindingResult` after a `Mono` body argument.
- [ ] If status depends on validation, return `Mono<ResponseEntity<T>>`.
- [ ] Never use `block()`/`subscribe()` inside controllers.
- [ ] Check whether other direct method constraints could lead to `HandlerMethodValidationException`.
- [ ] Keep authorization/domain policies separate from DTO structural constraints.
- [ ] Test valid HTTP requests, invalid DTOs, malformed JSON, missing bodies, and default error behavior with WebTestClient.

**Remember:** `@Valid @RequestBody Mono<T>` is a signature **supported by Spring WebFlux**. The framework decodes the body with `HttpMessageReader`, validates `T` via Jakarta Validation, and delivers either the value or `WebExchangeBindException` into the reactive pipeline. Handle errors with **`onErrorResume` or a global handler**, not a synchronous `BindingResult` after `Mono`; choosing `Mono<ResponseEntity<T>>` preserves proper HTTP status control.

## Official References

- [Spring Framework 6.2 — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — Supported Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — WebFlux Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux ResponseEntity](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html)
- [Spring API — WebExchangeBindException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Project Reactor — Error Handling Operators](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
