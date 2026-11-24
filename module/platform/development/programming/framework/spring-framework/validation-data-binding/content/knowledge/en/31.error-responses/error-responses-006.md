# Distinguishing Client Input Errors from Server Return-Value Errors in Spring Validation

## 1. Why must these two error types be clearly separated?

Validation in a Spring application can check **data entering** a handler/service or check **values produced by the server itself**. Both can manifest as a "constraint violation", yet their responsibilities and HTTP responses are very different.

For example, an API providing pagination:

~~~http
GET /api/contracts/page?size=0
~~~

If the controller requires `size >= 1`, the client sent a value violating the input contract. With Spring MVC built-in method validation, this typically results in **HTTP 400 Bad Request**.

Conversely, suppose the client sends a valid request:

~~~http
GET /api/contracts/report
~~~

The controller promises to return a non-blank string (for example, placing `@NotBlank` on the **return value**), but the implementation returns `""`. **The client cannot fix an invalid value produced by the server**. With Spring MVC method validation since Spring Framework 6.1+, a return-value failure can produce **`HandlerMethodValidationException` with HTTP 500 Internal Server Error**.

**Foundational rules:**

- **Input violation**: the client sent a parameter or object that fails the contract → **appropriate 4xx status**; for common validation failures, typically **400**.
- **Return-value violation**: the server failed to satisfy its own output constraints → **server error, typically 500**, never downgraded to 400 or 422.
- **Other application/dependency errors**: may be 404, 409, 401, 403, 503, or 500 depending on cause — **not every validation-related failure is 400**.

This lesson focuses on **Spring Framework validation + error responses**, covering Jakarta Bean Validation, `@Valid`, method-level constraints, `MethodArgumentNotValidException`, `HandlerMethodValidationException`, preserving the right status during exception handling, and practical testing with `MockMvc`.

## 2. Request lifecycle: responsibility follows where the error occurs

~~~text
Client
  |
  | HTTP request / query / path / header / JSON / form
  v
Spring MVC argument resolution
  ├─ Body reading, JSON parsing, type conversion, data binding
  |     └─ Input/parse error       -> typically 400
  |
  ├─ Input argument validation
  |     ├─ @Valid DTO              -> MethodArgumentNotValidException (400)
  |     └─ @Min/@NotBlank on
  |        method parameter        -> HandlerMethodValidationException (400)
  |
  v
Controller -> Service -> Repository/remote systems
  |                |
  |                ├─ Resource not found   -> typically 404
  |                ├─ State conflict       -> typically 409
  |                └─ Server/dependency    -> appropriate 5xx
  v
Handler method returns result
  |
  ├─ Return-value constraint check
  |     └─ Contract-violating output
  |        -> HandlerMethodValidationException (500)
  |
  v
HttpMessageConverter writes HTTP response
  |
  └─ Serialization/output error    -> typically 5xx
~~~

The difference does not lie in the constraint name: **`@NotBlank` can be used on either input or a return value**. The 400 vs. 500 decision depends on **which stage and target are being validated**, not simply on the name `NotBlank` or `ConstraintViolationException`.

Clearly distinguish **validation** from other failure types:

- `size=abc` cannot be parsed as `int` → **type conversion** error, before `@Min` evaluates the value.
- Syntactically invalid JSON → `HttpMessageNotReadableException` (typically 400), before Bean Validation.
- `size=0` parses as `int`, but violates `@Min(1)` → **input validation**.
- Handler returns `""` despite `@NotBlank` on the method → **return-value validation**.
- Handler returns a valid object but Jackson cannot serialize it → **response writing/serialization error**, not a client `@NotNull` error.
- Service detects a business conflict (e.g., duplicate username) → may be 409, regardless of the DTO passing `@Valid`.

## 3. Spring MVC has two key validation mechanisms

### 3.1. Individual argument validation with `@Valid`

When a parameter is a command object from `@ModelAttribute`, `@RequestBody`, or `@RequestPart` annotated with `@Valid`/`@Validated`, Spring can validate that object after binding/deserialization:

~~~java
@PostMapping("/users")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateUserRequest body) {

    // When the DTO fails constraints, execution normally never reaches here.
    return ResponseEntity.ok().build();
}
~~~

The snippet above assumes a DTO and imports; the complete program is in Section 8.

If the DTO has `@NotBlank String username`, the client sends `{"username":""}`, and there is no adjacent `BindingResult`, under **individual argument validation** Spring MVC typically throws:

~~~text
org.springframework.web.bind.MethodArgumentNotValidException
HTTP 400 Bad Request
~~~

This exception holds the `BindingResult` for **a single object**. Read `getFieldErrors()` and `getGlobalErrors()` to construct an appropriate error response. Never serialize `BindingResult` directly, as it can carry `rejectedValue`, internal details, or sensitive data.

**`@Valid` itself is not a constraint**. It tells validation to cascade into constraints nested inside the object. It **does not automatically trigger method validation** unless there are direct constraints on method parameters/return values or another condition invoking method validation.

### 3.2. Method validation with constraints directly on parameters

Since **Spring Framework 6.1**, Spring MVC supports **built-in method validation** for handlers with constraints directly on method parameters or the return value:

~~~java
@GetMapping("/page")
public String page(@RequestParam("size") @Min(1) int size) {
    return "SIZE:" + size;
}
~~~

`@Min(1)` is a constraint placed directly on **parameter `size`**. If the client sends `size=0`, method validation fails and typically throws:

~~~text
org.springframework.web.method.annotation.HandlerMethodValidationException
isForReturnValue() == false
getStatusCode() == 400 BAD_REQUEST
~~~

`HandlerMethodValidationException` groups results by **method parameters**, not just a single DTO like `MethodArgumentNotValidException`. If a method has both `@Min` on a parameter and `@Valid` on another DTO, method validation can **cover nested validation as well**, replacing individual argument validation.

**Important note on class-level `@Validated`:** When a controller has `@Validated` at the class level, method validation may be handled through a Spring AOP proxy instead of the built-in MVC mechanism. Spring recommends **omitting class-level `@Validated`** when you want Spring 6.1+ built-in controller method validation. Exception types and handling can differ under AOP, so test your actual configuration.

### 3.3. Method validation with constraints on the return value

Example:

~~~java
@GetMapping("/report")
@NotBlank
public String report() {
    return ""; // Server produces a value violating the contract.
}
~~~

Here `@NotBlank` is placed **on the method**, so it applies to the **return value**. Once the handler runs and returns `""`, Spring MVC built-in method validation detects that the return value violates the constraint and typically throws:

~~~text
org.springframework.web.method.annotation.HandlerMethodValidationException
isForReturnValue() == true
getStatusCode() == 500 INTERNAL_SERVER_ERROR
~~~

According to the official Javadoc of `HandlerMethodValidationException` (Spring Framework 6.1+): **status 400 is for input validation errors, and status 500 is for validation errors on return values**.

A return-value violation is a **server contract failure**: server code, database state, DTO mapping, or business logic must be investigated. **Never tell the client to "fix the request"** when the request did not violate the input contract.

### 3.4. Comparison table of three easily confused cases

| Handler | Invalid data | Typical exception | HTTP |
| --- | --- | --- | --- |
| `save(@Valid @RequestBody UserDto dto)` | DTO violates `@NotBlank` | `MethodArgumentNotValidException` (if individual validation) | 400 |
| `page(@RequestParam @Min(1) int size)` | Query `size=0` | `HandlerMethodValidationException`, `isForReturnValue()=false` | 400 |
| `@NotBlank String report()` | Server returns `""` | `HandlerMethodValidationException`, `isForReturnValue()=true` | 500 |
| `save(@Valid @RequestBody UserDto dto, BindingResult result)` | DTO violates Bean Validation | Errors handled by controller via `result` if nothing else triggers an exception | Custom, usually 400 |
| `save(@NotNull @Valid @RequestBody UserDto dto)` | Direct `@NotNull` constraint alongside `@Valid` | Method validation may apply instead of individual validation | Usually 400 on input error |

This table assumes Spring MVC 6.1+ **without class-level `@Validated` AOP interference**, a Bean Validation provider present, and no custom exception handler overriding statuses.

## 4. Why is return-value validation not a client error?

Suppose an API receives a valid product code, the service fetches data, and returns a response:

~~~java
public record ProductResponse(
        @NotBlank String sku,
        @NotNull BigDecimal price) {
}
~~~

The record itself declares constraints on output data. Many causes can make a response violate them:

- The repository returns an object missing `sku` due to corrupted inventory data.
- A mapper mistakenly writes `sku=""` or `price=null`.
- A service applies the wrong business rule.
- Downstream data has an unexpected schema.
- A refactor drops a required output field.

**The client is not responsible for making the server's mapper work properly**. Therefore:

1. Returning 400 **misclassifies the failure** and leads the client to retry fixing valid input pointlessly.
2. Returning detailed validator output can **leak response structure, DB values, or server internals**.
3. Monitoring metrics become skewed if server bugs are mixed into 4xx counts.
4. Clients may assume the request was rejected before the server acted, whereas return-value validation can occur **after the service has already executed side effects**.

**Distinguish declaring annotations from activating validation:** merely putting `@NotBlank`/`@NotNull` inside `ProductResponse` does not prove every endpoint returning that record automatically validates output. To ensure a code path actually validates return values, configure/place constraints that trigger **executable return-value validation** (or invoke a validator explicitly) and test it. `@Valid` alone on a method is not a constraint, so do not assume every output is automatically checked by the method validator.

### Standardizing responses

For return-value errors, return a generic envelope:

~~~json
{
  "code": "SERVER_CONTRACT_VIOLATION",
  "message": "The request could not be completed."
}
~~~

HTTP status: **500**. Never tell the client "field `sku` had rejected value `null`" when those are internal details. Internal logs/tracing should record **error code, route template, request ID, and status**, never personal data or tokens for "quick debugging".

For input errors:

~~~json
{
  "code": "INVALID_INPUT",
  "message": "Request parameters are invalid."
}
~~~

HTTP status: **400**. In form/REST applications you can include a list of whitelisted public fields, but never return raw `rejectedValue`. Both schemas can share a consistent shape, while **status and code preserve the distinction in meaning**.

## 5. Reading `HandlerMethodValidationException` properly

`HandlerMethodValidationException` belongs to package:

~~~java
org.springframework.web.method.annotation
        .HandlerMethodValidationException
~~~

The path above is wrapped for readability; **in a Java file, import it on a single line**:

~~~java
import org.springframework.web.method.annotation.HandlerMethodValidationException;
~~~

Useful methods in Spring Framework 6.2:

| API | Purpose |
| --- | --- |
| `isForReturnValue()` | `true` if validation failed on the return value; `false` if on method arguments. |
| `getStatusCode()` | Returns `HttpStatusCode`: **400** for input; **500** for return value. |
| `getParameterValidationResults()` | `ParameterValidationResult` instances grouping errors by method parameters. |
| `getCrossParameterValidationResults()` | Cross-parameter errors in method-level validation. |
| `getAllValidationResults()` or `getAllErrors()` | Aggregates validation results/errors depending on API version. |
| `getMethod()` | The validated method — useful for internal diagnostics. |
| `visitResults(visitor)` | Dispatches errors by parameter annotation type such as `@RequestParam`, `@RequestHeader`, `@ModelAttribute`. |
| `getBody()` | `ProblemDetail` in the `ErrorResponse` mechanism. |

**You do not need to inspect `getParameterValidationResults()` to decide 400 vs. 500**. The right method for that distinction is `isForReturnValue()`, alongside `getStatusCode()` already chosen by Spring. Return-value violations may be represented via internal result groups; never assume `"parameter index = -1"` is a public API contract.

Example handler:

~~~java
@ExceptionHandler(HandlerMethodValidationException.class)
ResponseEntity<?> handle(HandlerMethodValidationException ex) {
    if (ex.isForReturnValue()) {
        return ResponseEntity.status(
                HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of(
                        "code", "SERVER_CONTRACT_VIOLATION"));
    }

    return ResponseEntity.badRequest()
            .body(Map.of("code", "INVALID_INPUT"));
}
~~~

This is a **snippet** inside `@RestControllerAdvice` requiring corresponding imports. It does not expose raw exception messages or parameter values. In the complete code in Section 8, the handler uses `ex.getStatusCode()` to **preserve the framework's 400/500 classification**.

### `ResponseEntityExceptionHandler` also has the matching extension point

If the application extends `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler`, Spring 6.1+ provides the protected hook:

~~~java
@Override
protected ResponseEntity<Object>
handleHandlerMethodValidationException(
        HandlerMethodValidationException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {
    // Must preserve the distinction between input and return-value errors.
    return handleExceptionInternal(
            ex, sanitizedBody(ex), headers, status, request);
}
~~~

This snippet **illustrates the signature**, assuming an enclosing subclass and a custom `sanitizedBody(ex)` helper; it is not a standalone class. In the override, use the `status` passed by Spring (400/500), or inspect `ex.isForReturnValue()` when customizing the body. **Never hardcode 400** for every `HandlerMethodValidationException`.

When extending `ResponseEntityExceptionHandler`, do not declare an additional `@ExceptionHandler(HandlerMethodValidationException.class)` in the same class if the parent already routes that exception; doing so can cause handler mapping ambiguity. Pick **one mechanism** per application.

## 6. Classifying errors more accurately than a single "validation failed" label

| Situation | Location/source | Typical exception or mechanism | Suggested HTTP |
| --- | --- | --- | --- |
| Missing required query parameter | Client input | `MissingServletRequestParameterException` | 400 |
| Query `count=abc`, expecting `int` | Argument conversion | `MethodArgumentTypeMismatchException` | 400 |
| Malformed JSON | `HttpMessageConverter` reading body | `HttpMessageNotReadableException` | 400 |
| Invalid `@Valid @RequestBody` DTO | Individual Bean Validation | `MethodArgumentNotValidException` | 400 |
| `@RequestParam @Min(1)`, client sends 0 | MVC built-in method validation on **input** | `HandlerMethodValidationException`, return flag false | 400 |
| `@NotBlank` on return method, server returns empty | MVC built-in method validation on **output** | `HandlerMethodValidationException`, return flag true | 500 |
| Service method with `@Validated` AOP returns invalid value | Method validation outside MVC | May be `ConstraintViolationException` or `MethodValidationException` depending on config | Server error 5xx; do not treat as 400 |
| `@ResponseBody` cannot be serialized | Serialization/response write | `HttpMessageNotWritableException` or similar error | Typically 500 |
| Valid resource not found | Business/resource lookup | Domain exception or mapped `ResponseStatusException` | Typically 404 |
| Duplicate resource / state clash | Business conflict | Domain exception, duplicate-key mapping | Typically 409 |
| Upstream/downstream unavailable | Server dependency failure | Timeout/connection exception | 5xx, possibly 503 per policy |
| Client sends valid syntax violating a business rule | Domain/application policy | Dedicated error code | 400, 409, or 422 per API contract |

**Critical warning:** There is no rule saying "whenever you see `ConstraintViolationException`, return HTTP 400". It can originate from **service-layer validation**, and on its own it does not tell you whether the client or the server was at fault. You must know **which execution path was validated** and **which value failed**.

### Why does `422` not replace `500` for response contracts?

HTTP 422 Unprocessable Content is chosen by some APIs for syntactically valid input that fails business rules. It is **a 4xx status** and still indicates a client/request error. It must not be used to hide a return-value constraint failure: when the server produced a contract-violating result, **500** accurately reflects responsibility.

### Authentication, authorization, and resource errors

A request can fail due to an invalid token (401), missing permissions (403), missing resource (404), or conflict (409) even if every Bean Validation constraint passes. **Input validation is one layer; HTTP error semantics are broader**. Never abuse `@Valid` to decide authorization or existence checks.

## 7. Validation timing and impact on side effects

### 7.1. Early input validation

Normally `@Valid`/method parameter constraints run before the controller body executes. Invalid requests can be rejected before querying the database or performing expensive operations.

Even so, keep guards at service/domain boundaries if there are non-HTTP callers (message queues, scheduled tasks, internal services) or authorization and consistency checks. `@Valid` on a DTO does not guarantee the caller is allowed to update a resource.

### 7.2. Return validation after processing

Return-value validation runs **after the controller returns a value** (and in the built-in MVC path, before the result is written as a complete HTTP response). The service may have already written to the DB, published events, or called external APIs **before the 500 exception is raised**.

Example scenario:

~~~text
Valid client POST
   -> MVC input validation passes
   -> Service creates transaction, persists record successfully
   -> Controller maps DTO wrongly, returns value violating constraint
   -> MVC detects violation -> HTTP 500
~~~

Do not assume a DB transaction rolled back merely because the client received 500. If the transaction already committed before return validation, the system may need idempotency keys, proper transaction boundaries, or compensation/reconciliation. Never encourage clients to blindly retry POST requests without an idempotency policy: that risks duplicate data.

**Validate output as close to where it is produced as possible**, and do not treat return-value annotations as the sole safeguard for consistency. For critical business services, establish clear invariants, tests, and transaction boundaries before committing side effects.

### 7.3. Asynchronous/streaming handlers

If a handler returns `CompletableFuture`, `Mono`, `Flux`, a stream, or `ResponseBodyEmitter`, when values are produced and validated can differ from a synchronous `String` handler. Once an HTTP response **has committed headers or sent partial body data**, an exception handler cannot arbitrarily change the status to 500. Design checks inside the reactive pipeline, cancellation/fallback handling, and proper observability.

Therefore, the complete code below uses a **synchronous controller returning `String`** to cleanly demonstrate built-in MVC 400/500 method validation without generalizing to all streaming models.

## 8. Runnable example: Spring Boot 3.2+, Java 17+, Spring MVC

This sample project verifies five distinct scenarios:

1. `@Min` violation on a method input parameter → **400**.
2. `@NotBlank` violation on a controller **return value** → **500**.
3. Invalid `@Valid @RequestBody` DTO → **400** via `MethodArgumentNotValidException`.
4. Unreadable JSON body → **400** via `HttpMessageNotReadableException`.
5. Valid input/output cases → request succeeds normally.

Uses **Spring Boot 3.2+** (Spring Framework **6.1+**), **Java 17+**, Maven. With Spring Boot 3.x, validation packages are `jakarta.validation.*`, not `javax.validation.*`.

### 8.1. Maven dependencies

In a `pom.xml` managed by Spring Boot parent or BOM, add:

~~~xml
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
~~~

Only these three starters are needed; Spring Security is omitted to keep the focus on the validation pipeline. In a real project with custom `@ControllerAdvice` or AOP validators, tests may need adjustments.

Create the Java files in package `com.example.contractvalidation`. In the demo **do not place `@Validated` on the controller class**, so Spring MVC built-in method validation is used as described in Spring 6.1+ docs.

### 8.2. `ContractValidationApplication.java`

Path: `src/main/java/com/example/contractvalidation/ContractValidationApplication.java`

~~~java
package com.example.contractvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ContractValidationApplication.class, args);
    }
}
~~~

### 8.3. `CreateUserRequest.java`

Path: `src/main/java/com/example/contractvalidation/CreateUserRequest.java`

~~~java
package com.example.contractvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateUserRequest(
        @NotBlank String username,
        @NotNull @Min(18) Integer age) {
}
~~~

This record declares constraints **on input data**. With `username=""` or `age=16`, `@Valid` on the controller argument checks and reports errors. When the JSON body has syntax errors, Jackson cannot construct the record, resulting in a **deserialization** error rather than a `@Min` error.

### 8.4. `ContractController.java`

Path: `src/main/java/com/example/contractvalidation/ContractController.java`

~~~java
package com.example.contractvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/contracts")
public class ContractController {

    // Direct input constraint on the method parameter.
    @GetMapping("/page")
    public String page(
            @RequestParam("size") @Min(1) int size) {
        return "SIZE:" + size;
    }

    // Return-value constraint, checked after the handler executes.
    @NotBlank
    @GetMapping("/healthy-report")
    public String healthyReport() {
        return "READY";
    }

    // Intentionally violates the return-value constraint to test HTTP 500.
    @NotBlank
    @GetMapping("/broken-report")
    public String brokenReport() {
        return "";
    }

    // Only @Valid on the command object -> individual argument
    // validation (no direct constraints on the method).
    @PostMapping(path = "/users",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createUser(
            @Valid @RequestBody CreateUserRequest input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "accepted"));
    }
}
~~~

**What to observe:**

- `/page` has `@Min(1)` **on the method parameter**; `size=0` triggers a method input validation error. `size=abc` fails at **type conversion** before `@Min`.
- `/healthy-report` and `/broken-report` place `@NotBlank` **directly on the method**, making it a constraint on the **`String` return value**.
- `/broken-report` intentionally returns an empty string so we have a regression test for **500**; do not expose such an endpoint in a real app.
- `/users` only attaches `@Valid` to the DTO, so with this signature Spring can use individual argument validation and `MethodArgumentNotValidException`.
- There is no class-level `@Validated`. Adding it can switch validation to an AOP proxy and require updating exception-specific tests.

### 8.5. `ContractErrorAdvice.java`: preserving 400 and 500 accurately

Path: `src/main/java/com/example/contractvalidation/ContractErrorAdvice.java`

~~~java
package com.example.contractvalidation;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ContractErrorAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<PublicError> onMethodValidation(
            HandlerMethodValidationException ex) {

        boolean returnValueFailed = ex.isForReturnValue();
        String code = returnValueFailed
                ? "SERVER_CONTRACT_VIOLATION"
                : "INVALID_INPUT";
        String message = returnValueFailed
                ? "The request could not be completed."
                : "Request parameters are invalid.";

        // Spring already selected 400 for input, 500 for return value.
        // Never force all cases to badRequest().
        return ResponseEntity.status(ex.getStatusCode())
                .body(new PublicError(code, message));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<PublicError> onInvalidDto(
            MethodArgumentNotValidException ex) {

        // Never return rejectedValue, BindingResult, or exception body.
        return ResponseEntity.badRequest().body(
                new PublicError(
                        "INVALID_BODY",
                        "Input data is invalid."));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<PublicError> onUnreadableBody(
            HttpMessageNotReadableException ex) {

        // Malformed JSON / missing body: never echo parser exception details.
        return ResponseEntity.badRequest().body(
                new PublicError(
                        "MALFORMED_BODY",
                        "Could not read the request body."));
    }

    public record PublicError(String code, String message) {
    }
}
~~~

Why is this handler safer than `@ExceptionHandler(Exception.class)` returning 400?

1. It catches the **exact exception** and distinguishes cases via `isForReturnValue()`.
2. It uses **Spring's `ex.getStatusCode()`** instead of blindly turning every error into 400.
3. Return-value errors return only a **generic code**. Never leak server-generated values, internal method names, constraints, or entity data.
4. `MethodArgumentNotValidException` targets an invalid DTO, distinct from method validation on `@Min` parameters.
5. `HttpMessageNotReadableException` comes from the converter/Jackson failing to read the body, not a `ConstraintViolation` on a deserialized field.
6. The response schema is **this example's design**, not Spring Boot's default JSON.
7. This advice **does not extend `ResponseEntityExceptionHandler`**, so it does not register duplicate handlers in the same class.

For more complex error management requirements, you can switch to `ProblemDetail`/RFC 9457 while keeping the exact same **status and category**. Never expose a list of return-value constraint violations in public problem details.

## 9. `MockMvc` tests: 400 for input, 500 for output

Create `src/test/java/com/example/contractvalidation/ContractValidationApplicationTest.java`:

~~~java
package com.example.contractvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ContractValidationApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validMethodParameterIsAccepted() throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "2"))
                .andExpect(status().isOk())
                .andExpect(content().string("SIZE:2"));
    }

    @Test
    void methodInputConstraintFailureIs400()
            throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_INPUT"));
    }

    @Test
    void negativeInputAlsoViolatesMinConstraint()
            throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "-5"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_INPUT"));
    }

    @Test
    void missingRequiredParameterIs400()
            throws Exception {
        mvc.perform(get("/api/contracts/page"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void wrongParameterTypeIs400BeforeMinValidation()
            throws Exception {
        mvc.perform(get("/api/contracts/page")
                    .param("size", "abc"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void validReturnValueIsAccepted() throws Exception {
        mvc.perform(get("/api/contracts/healthy-report"))
                .andExpect(status().isOk())
                .andExpect(content().string("READY"));
    }

    @Test
    void invalidReturnValueIs500Not400()
            throws Exception {
        mvc.perform(get("/api/contracts/broken-report"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("SERVER_CONTRACT_VIOLATION"))
                .andExpect(jsonPath("$.message")
                        .value("The request could not be completed."));
    }

    @Test
    void validJsonDtoCreatesResponse() throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"Lan","age":26}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status")
                        .value("accepted"));
    }

    @Test
    void invalidJsonDtoIs400ButNotMethodReturnError()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"","age":16}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_BODY"));
    }

    @Test
    void jsonMissingAgeIsDtoValidationError()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"username":"Lan"}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_BODY"));
    }

    @Test
    void malformedJsonIs400BeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));
    }

    @Test
    void missingRequiredBodyIs400BeforeController()
            throws Exception {
        mvc.perform(post("/api/contracts/users")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));
    }
}
~~~

From the configured Maven project root, run:

~~~bash
./mvnw test -Dtest=ContractValidationApplicationTest
~~~

On Windows PowerShell/cmd using the Maven wrapper: `mvnw.cmd test -Dtest=ContractValidationApplicationTest`. If Maven is installed globally: `mvn test -Dtest=ContractValidationApplicationTest`.

**All 12 tests are designed to pass** under Spring Boot 3.2+ MVC + Validation + Test with the source above. Expected observations:

| Group | Input/endpoint | Status | Core code/body |
| --- | --- | --- | --- |
| Valid method input | `?size=2` | 200 | `SIZE:2` |
| Invalid method input constraint | `?size=0` | 400 | `INVALID_INPUT` |
| Negative method input | `?size=-5` | 400 | `INVALID_INPUT` |
| Missing required input | No `size` | 400 | Spring handles missing required parameter. |
| Wrong input type | `size=abc` | 400 | Spring handles type conversion. |
| Valid return value | `/healthy-report` | 200 | `READY` |
| **Invalid return value** | `/broken-report` returns `""` | **500** | **`SERVER_CONTRACT_VIOLATION`** |
| Valid JSON DTO | `username=Lan`, `age=26` | 201 | `accepted` |
| Failing JSON DTO constraint | empty username, age 16 | 400 | `INVALID_BODY` |
| JSON missing `age` | `@NotNull` fails | 400 | `INVALID_BODY` |
| Malformed JSON | Body parse fails | 400 | `MALFORMED_BODY` |
| Missing JSON body | `@RequestBody(required=true)` | 400 | `MALFORMED_BODY` |

**Why assert only status in some cases?** Missing query params and type mismatches are normally handled by Spring MVC's default exception resolvers; the error body can vary by Spring Boot version, `ProblemDetail` configuration, or custom `@ControllerAdvice`. Do not couple tests to Spring's default wording for those cases.

**What the tests do not prove:** these tests do not run against a database and do not prove transaction rollback or performance. Nor do they cover async/streaming models or service-level AOP validation. Those areas require dedicated tests in real projects.

### 9.1. Trying it with curl

Once the app is running via `./mvnw spring-boot:run`:

~~~bash
curl -i "http://localhost:8080/api/contracts/page?size=0"
curl -i "http://localhost:8080/api/contracts/page?size=2"

curl -i "http://localhost:8080/api/contracts/broken-report"
curl -i "http://localhost:8080/api/contracts/healthy-report"

curl -i -X POST "http://localhost:8080/api/contracts/users" \
  -H "Content-Type: application/json" \
  -d '{"username":"","age":16}'
~~~

Expected statuses are **400, 200, 500, 200, 400** respectively. These commands use Unix shell syntax; on Windows PowerShell, `curl.exe` and quoting/line-continuation rules differ. Never use payloads containing real sensitive data just to test status codes.

## 10. Jakarta `ExecutableValidator`: view from the Bean Validation layer

At the Jakarta Validation layer, there are two separate APIs, both operating on methods but targeting different values:

~~~java
Set<ConstraintViolation<T>> validateParameters(
        T object, Method method, Object[] parameterValues,
        Class<?>... groups);

Set<ConstraintViolation<T>> validateReturnValue(
        T object, Method method, Object returnValue,
        Class<?>... groups);
~~~

These are **generalized signatures** of `ExecutableValidator`, not the complete interface definition. The two results carry distinct meanings:

- `validateParameters(...)` checks arguments supplied by the **caller**.
- `validateReturnValue(...)` checks the value returned by the **implementation**.

A pure Jakarta Validation unit test without starting a web server:

~~~java
package com.example.contractvalidation;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ExecutableContractTest {

    static class ContractService {

        @NotBlank
        public String calculate(@Min(1) int size) {
            return "";
        }
    }

    @Test
    void inputAndOutputViolationsAreDistinct() throws Exception {
        try (var factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();
            var executables = validator.forExecutables();
            var service = new ContractService();
            Method method = ContractService.class
                    .getMethod("calculate", int.class);

            var inputErrors = executables.validateParameters(
                    service, method, new Object[] {0});

            var outputErrors = executables.validateReturnValue(
                    service, method, "");

            assertEquals(1, inputErrors.size());
            assertEquals(1, outputErrors.size());
        }
    }
}
~~~

**Verification point:** this test only demonstrates that **Bean Validation separates arguments and return values**; it does **not** assign HTTP 400/500 by itself. The HTTP decision lives in Spring MVC's mapping layer. Never write service libraries expecting Jakarta `ConstraintViolation` to carry an `HttpStatus`.

If you add `ExecutableContractTest.java` to the same project, run:

~~~bash
./mvnw test -Dtest=ExecutableContractTest
~~~

Note that `ValidatorFactory` extends `AutoCloseable` in modern Jakarta Validation versions; verify the exact contract if using another provider/version. In Spring Boot production code, inject `Validator` from the Spring context rather than building a factory manually.

### Distinguishing method return validation from validating a standalone bean

~~~java
Set<ConstraintViolation<ProductResponse>> errors =
        validator.validate(productResponse);
~~~

This call validates **constraints on a bean instance**; it does not automatically become `validateReturnValue(...)` on a controller method. If a response DTO must be checked before sending, validate it explicitly in the service or configure executable validation, being clear about **when** it runs and **where** the resulting exception goes.

A controller returning `ProductResponse` with `@NotNull` record fields—but without return-value validation activated—can still serialize an invalid response. Annotations declared on a DTO **do not replace** configuring and testing the execution pipeline.

## 11. Service-layer `@Validated` and other exceptions

Spring provides **AOP-based method validation** via `@Validated` on beans and constraint annotations on methods. Example:

~~~java
@Service
@Validated
public class CatalogService {

    @NotBlank
    public String displayName(long productId) {
        return ""; // Intentionally violates the contract.
    }
}
~~~

This is a snippet assuming imports and `@Service`, not part of the main program. When invoked through a Spring proxy with method validation configured, the invalid return value can be caught. However, the thrown exception may be **`ConstraintViolationException`** or **`MethodValidationException`** depending on validator/interceptor configuration (and may differ when using Spring's `MethodValidationAdapter`).

**Never attach `@ExceptionHandler(ConstraintViolationException.class)` returning 400 for every case**. The exact same exception class can originate from:

- a service method receiving web input (possibly client-related, though still subject to authorization and mapping);
- a service method invoked by a scheduler or queue (no HTTP client);
- a **service return-value violation** (server produced bad data);
- a custom constraint validator or metadata configuration bug (server bug).

Instead:

1. Place validation at explicit layers and know who the caller is.
2. Distinguish input vs. return value via method/executable validation context.
3. Use dedicated domain errors for problems the client can fix.
4. Let invariant violations and code anomalies surface as server errors with monitoring.
5. Never blindly convert every `ValidationException` into HTTP 400.

In Spring MVC 6.1+, if you want built-in handler method validation, do not put class-level `@Validated` on a controller just to "turn on validation"; Spring MVC supports it directly, and class-level `@Validated` can switch the mechanism to AOP.

## 12. Spring WebFlux: 400/500 semantics still hold, APIs differ

In **Spring WebFlux**, individual object validation typically throws **`WebExchangeBindException`** instead of Servlet MVC's `MethodArgumentNotValidException`.

However, for method validation, **`HandlerMethodValidationException`** plays a similar role:

- Direct constraint on a request method parameter → input error, typically **400**.
- Constraint on a handler return value → output error, typically **500**.
- Spring WebFlux built-in validation and exception handling have their own configuration and execution paths, especially with `Mono`/`Flux`.

Conceptual example:

~~~java
@GetMapping("/items")
Mono<String> items(@RequestParam @Min(1) int size) {
    // Architectural example; requires a matching WebFlux controller.
    return Mono.just("count=" + size);
}
~~~

This is a snippet, not a standalone runnable example, and it **does not imply** that a constraint on an outer `Mono` automatically validates every emitted item. For reactive publishers, understand validation level (publisher vs. element), timing, and response commitment.

WebFlux can throw `WebExchangeBindException` when `@Valid @RequestBody Mono<Dto>` or `@ModelAttribute` is invalid, depending on signature, argument resolution, and version. Do not import MVC's `MethodArgumentNotValidException` expecting it to be the standard exception in every reactive handler.

Across both stacks, **server-generated return-value errors must never be disguised as client errors just because validation raised them**.

## 13. Customizing responses with `ProblemDetail` and message localization

Spring Framework 6.x supports `org.springframework.http.ProblemDetail` and `org.springframework.web.ErrorResponse` for building HTTP problem responses per **RFC 9457**. `HandlerMethodValidationException` implements `ErrorResponse`, exposing `getStatusCode()` and `getBody()`.

An API can use a consistent structure for both 400 and 500:

~~~json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Request parameters are invalid."
}
~~~

~~~json
{
  "type": "about:blank",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "The request could not be completed."
}
~~~

These are **examples of JSON an application might choose**, not a guarantee that Spring Boot's default response always looks identical. With `ProblemDetail`/custom handlers, you can add `instance`, error codes, or trace IDs, while keeping internal method names, DB values, and raw rejected inputs out of 500 responses.

### Locale and `MessageSource`

- For **input errors**, you can return public field names, error codes, and appropriate localized messages.
- For **return-value errors**, return a **generic** localized public message; detailed causes belong in secure internal telemetry.
- Use server-controlled `MessageSource`/message codes; never let clients supply keys pointing into internal bundles.
- Never interpolate `FieldError#getRejectedValue()` or `ConstraintViolation#getInvalidValue()` into messages or structured error JSON.

Example message keys:

~~~properties
error.input=Tham số yêu cầu không hợp lệ.
error.body=Dữ liệu đầu vào không hợp lệ.
error.serverContract=Không thể hoàn tất yêu cầu.
~~~

The corresponding `messages_en.properties` file could be:

~~~properties
error.input=Request parameters are invalid.
error.body=Request body is invalid.
error.serverContract=The request could not be completed.
~~~

Select the error code on the server, pass the MVC-resolved request `Locale`, and keep status 400/500 intact. **Localization never changes responsibility** between client and server.

## 14. Handling return-value errors in production

### 14.1. Monitoring

A return-value contract failure must be monitored as a server error:

- Tag with error category `SERVER_CONTRACT_VIOLATION`.
- Track 5xx rate and counts by route template, service version, and release.
- Include a trace/request ID without tokens.
- Never serialize the full `HandlerMethodValidationException` if it contains sensitive target or parameter results.
- Record actionable technical diagnostics in logs protected by access control, retention, and redaction.
- Alert on sudden spikes after deployments or mapper/schema changes.

### 14.2. Never retry blindly

Clients may retry certain 5xx errors per policy, but for **POST requests with side effects**, a return-value failure can occur **after data was persisted**. Therefore, a 500 status alone does not guarantee safe retries. Use idempotency keys, reconciliation, or status-query endpoints where appropriate.

### 14.3. Clarify the response contract

If an endpoint requires fields `status`, `id`, `amount`:

- Use a dedicated response DTO with explicit invariants.
- Never construct a response from an incomplete entity without checking.
- Test mappers for null, empty, and edge cases.
- Place contract checks where transactions/side effects can be controlled when needed.
- Distinguish 500s from output validation from 500s caused by Jackson/serialization or downstream dependencies.

### 14.4. Never swallow exceptions to fake success

If return-value validation fails, never `catch` it and return `200 OK` with an arbitrary empty DTO. That misleads clients into thinking the call succeeded and can corrupt downstream invariants. If a valid business fallback exists, explicitly define when it applies and ensure the fallback still satisfies the contract.

## 15. Common mistakes in exception handling design

| Anti-pattern | Why it is wrong | Right approach |
| --- | --- | --- |
| `@ExceptionHandler(HandlerMethodValidationException.class)` always returns 400 | Turns server return-value violations into client errors. | Use `ex.getStatusCode()`/`isForReturnValue()`. |
| `@ExceptionHandler(ConstraintViolationException.class)` always returns 400 | `ConstraintViolationException` can originate from return values or services. | Distinguish violation layer/origin; never infer from class alone. |
| Handling only `MethodArgumentNotValidException` | Misses direct method validation, including return values. | Also handle `HandlerMethodValidationException`. |
| Putting `@Validated` on controller while expecting MVC 6.1 behavior | Switches execution to AOP proxy path. | Align on one validation mechanism and test actual exceptions. |
| Returning `ex.getMessage()` when return value fails | Can leak method names, internal objects, or values. | Return generic public code/message; log safely internally. |
| Labeling every 4xx as "Bean Validation error" | Conversion, missing parameter, auth, and conflict are distinct. | Classify by originating stage. |
| Using 422 to mask return-value failures | 422 still indicates a request-side error. | Return 500 when the server contract fails. |
| Assuming `@Valid` on a returned DTO always runs | Return-value executable validation may not be active. | Configure/place activating constraints and write tests. |
| Assuming 500 automatically rolls back transactions | Exception can occur after commit. | Manage transaction boundaries and idempotency explicitly. |
| Catching all `Exception` as 400 | Hides server bugs and skews observability. | Specific handlers + controlled 5xx fallback. |
| Changing status after streaming response committed | HTTP status cannot be changed once headers are sent. | Validate early or design a reactive error channel. |
| Returning raw rejected values and internal field paths | Leaks user data and internal structure. | Redact sensitive data and allowlist public error schemas. |

## 16. Testing and review checklist

- [ ] Identify whether each constraint belongs to a **request parameter**, **input DTO**, **service method**, or **return value**.
- [ ] On Spring MVC 6.1+, check `HandlerMethodValidationException#isForReturnValue()` and `getStatusCode()`.
- [ ] Never hardcode 400 for every method validation exception.
- [ ] Test that input `@Min` failure → 400; output `@NotBlank` failure → **500**.
- [ ] Test `@Valid @RequestBody` failure → `MethodArgumentNotValidException` or corresponding handler.
- [ ] Test malformed JSON, missing required parameters, and conversion failures; keep them distinct from output validation.
- [ ] Class-level `@Validated` on controllers must be deliberate, with tests verifying AOP vs. built-in MVC behavior.
- [ ] Server-error return handlers must never echo target objects, rejected values, internal responses, or exception causes.
- [ ] Preserve HTTP status and generic public messages for 500; keep error codes stable for monitoring.
- [ ] Input errors may include field-level details, limited to fields and values approved for public exposure.
- [ ] Never treat a service `ConstraintViolationException` as an input error without knowing the calling method's origin.
- [ ] Design transaction boundaries and idempotency for side-effecting endpoints; 500 does not prove rollback.
- [ ] For async/streaming endpoints, check return validation timing and whether the response has already committed.
- [ ] Monitor 4xx and 5xx separately with regression tests and redacted logs/telemetry.
- [ ] Never confuse `400`, `409`, `422`, `500`, and `503`; each status describes a distinct layer of responsibility.

**Conclusion:** Whenever Spring validation detects a violation, ask **who supplied the invalid value?** If it is client-controlled input, a 4xx response (usually 400) helps the client fix the request. If it is a **server-generated return value**, it is a server contract failure and must remain **500**. With Spring MVC 6.1+, `HandlerMethodValidationException#isForReturnValue()` and `getStatusCode()` preserve this boundary; `MethodArgumentNotValidException` is just one separate branch for validating input objects.

## References

- Spring Framework 6.2 Reference — **Spring MVC Validation** (`MethodArgumentNotValidException` vs `HandlerMethodValidationException`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Javadoc — **HandlerMethodValidationException** (400 input, 500 return value): https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Javadoc — **ResponseEntityExceptionHandler** (handlers for method validation): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework Reference — **Spring MVC Error Responses** (`ProblemDetail`/`ErrorResponse`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html
- Spring Framework Reference — **Validation with @RequestBody**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework Reference — **WebFlux Validation** (`WebExchangeBindException`, method validation): https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework Reference — **Spring Core Method Validation**: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Jakarta Bean Validation — **ExecutableValidator** contract: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/executable/executablevalidator
