# Representing Per-Field Errors, Extension Details, and Stable Error Codes in Spring MVC

## 1. The Problem and Expected Outcome

A REST endpoint receiving an invalid request needs to return more than an HTTP 400 status. The frontend must know **which field failed**, **why it failed**, and display an understandable message; automated clients need **stable error codes** to branch on without depending on display language, exception names, or internal Java structures.

Example request:

~~~http
POST /api/registrations HTTP/1.1
Content-Type: application/json
Accept: application/problem+json

{"name":"","email":"not-an-email","seats":0}
~~~

A helpful response contract:

~~~json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/registrations",
  "code": "REQUEST_VALIDATION_FAILED",
  "violations": [
    {"field":"email","code":"INVALID_FORMAT","message":"Invalid field format"},
    {"field":"name","code":"REQUIRED","message":"This field is required"},
    {"field":"seats","code":"OUT_OF_RANGE","message":"Value is outside the allowed range"}
  ]
}
~~~

This is an **application-defined JSON contract** built on RFC 9457. Spring does not automatically add the `REQUEST_VALIDATION_FAILED` code or the `violations` array; API authors must build, maintain, and test them. `instance` can be filled in by Spring from the request path when missing; exact values and serialization depend on application configuration.

This lesson focuses on the Spring MVC Servlet stack, Java 17+, Spring Boot 3.x / Spring Framework 6.x, covering:
- HTTP status structure, RFC 9457 `ProblemDetail`, and extensions.
- Converting `FieldError`, `ObjectError`, and validation results into per-field errors.
- Stable machine-readable codes and translatable display text.
- Distinguishing JSON reading errors, DTO validation, method validation, business errors, and server errors.
- Creating `@RestControllerAdvice` cleanly while avoiding conflicting exception handlers.
- Testing the contract with MockMvc; avoiding leaking internal data or exceptions.

## 2. Separating HTTP Status, Error Type, Error Location, and Message

| Field | Intended for | Guarantee |
| --- | --- | --- |
| HTTP `status` | HTTP protocol, middleware/clients | 400 invalid input; 404 missing resource; 409 conflict; 500 server error per policy |
| Problem Details `type` | Identifying problem type by URI | Can use a stable documentation URI, or `about:blank` |
| Extension `code` | Machine logic, telemetry, operations support | Public code like `REQUEST_VALIDATION_FAILED`, invariant across locales |
| `violations[].field` | UI mapping to input fields | Uses public DTO field/path, not Java method names |
| `violations[].code` | UI and automated clients understanding failure kind | `REQUIRED`, `INVALID_FORMAT`, `OUT_OF_RANGE`... |
| `title` / `detail` / `message` | Human readers | Translatable, wording may change; clients do not parse for logic |
| `requestId` | Correlation/tracing when implemented | Obtained from trusted infrastructure, never echoing tokens |

For instance, an empty email and a malformed email both typically result in 400, yet require different UI guidance. Clients can rely on `field=email` and `code=REQUIRED` or `INVALID_FORMAT`. Clients should not search for the English substring `"is required"` because the message may be translated to Vietnamese.

The top-level code `REQUEST_VALIDATION_FAILED` indicates the **request's problem category**; `REQUIRED` inside a violation pinpoints how to fix it. An API may publish fewer top-level codes and more field-level codes when detailed UX is needed.

## 3. RFC 9457 and `ProblemDetail`

### 3.1. Five Standard Fields

RFC 9457 Problem Details for HTTP APIs defines five common members:

| Field | Meaning |
| --- | --- |
| `type` | URI reference identifying the problem type. `about:blank` interprets per default status |
| `title` | Short summary of the problem type, suitable for UI/logs |
| `status` | HTTP status code when the problem was generated; must match actual status |
| `detail` | Specific explanation for this occurrence, containing no secrets |
| `instance` | URI reference for this specific error/request occurrence |

RFC 9457 allows additional fields (*extension members*) such as `code`, `violations`, `requestId`, `retryable`, or `documentation`. Do not add extensions merely because data exists on an exception; weigh client utility and privacy.

If using a documentation URI for `type`, the backend must own and maintain that URI. For a small API, `about:blank` alongside a stable `code` can also be a reasonable convention. Pick one mechanism for clients to identify errors and document it clearly in OpenAPI.

### 3.2. How Spring MVC Handles It

Spring Framework 6 provides:
- `org.springframework.http.ProblemDetail`: represents an RFC 9457 body.
- `org.springframework.web.ErrorResponse`: contract for status, headers, and problem body of an HTTP error.
- `org.springframework.web.ErrorResponseException`: base exception carrying `ErrorResponse` info.
- `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler`: base class for advice handling many built-in Spring MVC exceptions.

When returning `ProblemDetail`, Spring MVC can write the body with media type `application/problem+json`. In Spring's standard Jackson configuration, entries in `ProblemDetail.properties` are **unwrapped into top-level JSON fields**.

Illustrative example (missing full imports and `violations` variable):

~~~java
ProblemDetail body = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
body.setTitle("Request validation failed");
body.setDetail("One or more fields are invalid.");
body.setProperty("code", "REQUEST_VALIDATION_FAILED");
body.setProperty("violations", violations);
~~~

The output places `code` and `violations` alongside `title` and `status`, rather than nested inside `"properties":{...}`. Avoid extension names like `type`, `status`, `title`, `detail`, or `instance` that collide with standard fields.

Spring Boot has `spring.mvc.problemdetails.enabled` to auto-configure handling certain built-in errors as problem details. When implementing your own `ResponseEntityExceptionHandler` subclass, you own the responses for overridden branches and should verify advice ordering with existing Boot configuration.

## 4. Designing the Per-Field Error Array (`violations`)

Each entry should have at minimum:

~~~json
{"field":"profile.email","code":"INVALID_FORMAT","message":"Invalid field format"}
~~~

Where:
- `field` is the public name or path of the request data; for nested objects it can be `profile.email`; for arrays it can be `items[0].quantity`.
- `code` is a machine-readable code from the API's published code set.
- `message` is a safe user-facing message that can be localized.

If an error does not belong to a single field—such as a constraint across two fields—you can adopt `field:"$"` to denote an object-level error. Do not force clients to guess when `field` is null, empty string, or omitted.

**Allow multiple errors per field.** A single value can violate multiple constraints. The backend may return multiple violations or pick a primary one, but it must define the rule and test it. In particular, the order of errors from a Bean Validation provider must not be relied upon as a UI contract; if the API guarantees an order, sort explicitly by a defined rule.

### 4.1. Public Field-Level Codes

| Internal constraint/binding | Example public code | Meaning |
| --- | --- | --- |
| `NotBlank`, `NotNull`, `NotEmpty` | `REQUIRED` | Must not be missing/empty per rule |
| `Email`, `Pattern` | `INVALID_FORMAT` | Does not match required format |
| `Min`, `Max`, `Positive` | `OUT_OF_RANGE` | Outside allowed value range |
| `Size` | `INVALID_LENGTH` | Length/element count unsuitable |
| Other constraint | `INVALID_VALUE` | A validation rule was not satisfied |
| Invalid query/method parameter | `INVALID_PARAMETER` | Input does not satisfy method condition |

`FieldError.getCode()` returns codes generated by Spring/validation like `NotBlank`, `Email`, `Min`. Codes in `getCodes()` can even embed Java object and field names. Those are **internal** data for binding and `MessageSource`, not necessarily suitable as a public API contract.

Use a mapping layer to keep `INVALID_FORMAT` stable even if a validator switches from `@Email` to a custom constraint. Conversely, changing a public code or its semantics should be treated as an API change requiring versioning/review.

### 4.2. Do Not Expose Rejected Values (`rejectedValue`)

`FieldError` may hold `getRejectedValue()`, which could be a password, token, email, ID number, or a huge object. **Never emit `rejectedValue`, stack traces, SQL exceptions, package names, or raw parser messages in public responses.** The frontend already holds what the user typed; the server only needs to report the field and error.

For JSON parser errors, the server may not have constructed a DTO yet and thus lacks an exact field name. Do not fabricate a specific violation without sufficient certainty.

## 5. Error Branches Actually Encountered in Spring MVC

A simplified pipeline:

~~~text
HTTP request
  |
  +-- Body unreadable / malformed JSON
  |     -> HttpMessageNotReadableException
  |
  +-- Missing query param or type conversion failure
  |     -> MissingServletRequestParameterException
  |     -> MethodArgumentTypeMismatchException / TypeMismatchException
  |
  +-- @Valid @RequestBody DTO, without direct method constraints
  |     -> MethodArgumentNotValidException (individual argument validation)
  |
  +-- Constraint directly on method parameter, Spring MVC 6.1+
  |     -> HandlerMethodValidationException (input: 400)
  |
  +-- Method return value violates constraint
        -> HandlerMethodValidationException (server: 500)
~~~

The diagram shows **possible branches**, not all MVC exceptions. On a controller with class-level `@Validated` and AOP method validation configured, execution can go through a proxy and throw `ConstraintViolationException` or `MethodValidationException`. Spring MVC 6.1+ recommends omitting class-level `@Validated` when you want built-in MVC method validation.

| Error | Data usable for building the contract |
| --- | --- |
| `MethodArgumentNotValidException` | `getBindingResult().getFieldErrors()`, `getGlobalErrors()` |
| `HandlerMethodValidationException` | `getAllValidationResults()`, `visitResults(Visitor)`; may contain `ParameterErrors` for nested DTOs |
| `HttpMessageNotReadableException` | Classify unreadable body; usually lacks reliable field-level details |
| `MissingServletRequestParameterException` | Name of the missing required parameter |
| `MethodArgumentTypeMismatchException` | HTTP parameter and expected Java type; do not expose sensitive raw input |
| Domain exceptions such as not found/conflict | Public domain error code and status per policy |
| Unexpected internal exception | `INTERNAL_ERROR`, status 500, safely log cause server-side |

**Do not map every error to HTTP 400.** A constraint violation on a **server return value** should be 500. A business conflict can be 409. A valid request for a non-existent resource is normally 404.

## 6. Runnable Application Example: Spring Boot 3.3 / Java 17

This example demonstrates implementing a simple registration API that builds error bodies without a database. It uses Spring Boot 3.3.5 (Spring Framework 6.1.x under the default BOM), Java 17+, Spring MVC, and Hibernate Validator.

Structure:

~~~text
registration-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/registration/
    │   ├── RegistrationApplication.java
    │   ├── api/RegistrationInput.java
    │   └── web/
    │       ├── RegistrationController.java
    │       └── ApiErrorAdvice.java
    └── test/java/com/example/registration/web/
        └── RegistrationControllerTest.java
~~~

### 6.1. Build

`settings.gradle`:

~~~groovy
rootProject.name = 'registration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-web` provides Spring MVC/Jackson. `spring-boot-starter-validation` is required for Bean Validation constraints to work (typically via Hibernate Validator). `spring-boot-starter-test` supports JUnit and MockMvc. The example assumes a compatible Gradle wrapper; Spring code cannot run standalone via plain `javac` without the Spring classpath.

### 6.2. Main Application

`src/main/java/com/example/registration/RegistrationApplication.java`:

~~~java
package com.example.registration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegistrationApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegistrationApplication.class, args);
    }
}
~~~

Placed in the root package so component scanning finds `web` and `api`.

### 6.3. Input DTO with Constraints

`src/main/java/com/example/registration/api/RegistrationInput.java`:

~~~java
package com.example.registration.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record RegistrationInput(
        @NotBlank @Size(max = 80) String name,
        @NotBlank @Email String email,
        @Min(1) int seats) {
}
~~~

`@NotBlank` checks that a string is not solely whitespace; `@Email` checks basic format without verifying mailbox ownership; `@Min(1)` requires at least 1 seat. With primitive `int`, a body omitting `seats` can deserialize to its default value depending on config and then fail `@Min`. To distinguish omitted vs. `0`, use `Integer` with `@NotNull`.

### 6.4. Controller with Two Validation Paths

`src/main/java/com/example/registration/web/RegistrationController.java`:

~~~java
package com.example.registration.web;

import com.example.registration.api.RegistrationInput;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {

    public record Receipt(String name, int seats) {}

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public Receipt submit(@Valid @RequestBody RegistrationInput input) {
        return new Receipt(input.name(), input.seats());
    }

    @GetMapping("/check")
    public Map<String, Integer> check(
            @RequestParam("minimumSeats") @Min(1) int minimumSeats) {
        return Map.of("minimumSeats", minimumSeats);
    }
}
~~~

`submit` uses individual argument validation for `@Valid @RequestBody`; invalid data can throw `MethodArgumentNotValidException`. `check` has `@Min(1)` directly on the method parameter, so with Spring MVC **6.1+** built-in method validation it can throw `HandlerMethodValidationException`.

Do not place `@Validated` at the **class level** in this demo: class-level `@Validated` can switch to AOP method validation and a different exception type. This example persists no data; default success status is 200 and the receipt response only illustrates the successful HTTP path. In a real resource-creation API, choose 201/Location and persistence per business contract.

### 6.5. Advice Mapping Two Exceptions to the Same Error Contract

`src/main/java/com/example/registration/web/ApiErrorAdvice.java`:

~~~java
package com.example.registration.web;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.springframework.core.MethodParameter;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    public record Violation(String field, String code, String message) {}

    private static Violation fieldViolation(FieldError error) {
        String stableCode = switch (
                error.getCode() == null ? "" : error.getCode()) {
            case "NotBlank", "NotNull", "NotEmpty" -> "REQUIRED";
            case "Email", "Pattern" -> "INVALID_FORMAT";
            case "Min", "Max", "Positive", "PositiveOrZero" -> "OUT_OF_RANGE";
            case "Size" -> "INVALID_LENGTH";
            default -> "INVALID_VALUE";
        };

        String safeMessage = switch (stableCode) {
            case "REQUIRED" -> "This field is required";
            case "INVALID_FORMAT" -> "Invalid field format";
            case "OUT_OF_RANGE" -> "Value is outside the allowed range";
            case "INVALID_LENGTH" -> "Invalid field length";
            default -> "Invalid field value";
        };

        return new Violation(error.getField(), stableCode, safeMessage);
    }

    private static List<Violation> sorted(List<Violation> errors) {
        return errors.stream()
                .sorted(Comparator.comparing(Violation::field)
                        .thenComparing(Violation::code))
                .toList();
    }

    private ResponseEntity<Object> problem(
            HttpStatusCode status, HttpHeaders headers, String code,
            String title, String detail, List<Violation> violations) {

        ProblemDetail body = ProblemDetail.forStatus(status);
        body.setTitle(title);
        body.setDetail(detail);
        body.setProperty("code", code);

        if (violations != null) {
            body.setProperty("violations", sorted(violations));
        }
        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<Violation> violations = new ArrayList<>();
        ex.getBindingResult().getFieldErrors()
                .forEach(e -> violations.add(fieldViolation(e)));
        ex.getBindingResult().getGlobalErrors()
                .forEach(e -> violations.add(new Violation(
                        "$", "INVALID_OBJECT", "Object-level constraint failed")));

        return problem(status, headers, "REQUEST_VALIDATION_FAILED",
                "Request validation failed",
                "One or more fields are invalid.", violations);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (ex.isForReturnValue()) {
            return problem(HttpStatus.INTERNAL_SERVER_ERROR, headers,
                    "INTERNAL_ERROR", "Internal server error",
                    "The server could not complete the request.", null);
        }

        List<Violation> violations = new ArrayList<>();

        for (ParameterValidationResult result
                : ex.getAllValidationResults()) {

            if (result instanceof ParameterErrors errors) {
                errors.getFieldErrors().forEach(e ->
                        violations.add(fieldViolation(e)));
                errors.getGlobalErrors().forEach(e ->
                        violations.add(new Violation(
                                "$", "INVALID_OBJECT",
                                "Object-level constraint failed")));
            } else {
                MethodParameter parameter = result.getMethodParameter();
                RequestParam query =
                        parameter.getParameterAnnotation(RequestParam.class);

                String field = query == null || query.name().isBlank()
                        ? "argument" + parameter.getParameterIndex()
                        : query.name();

                String code =
                        parameter.hasParameterAnnotation(Min.class)
                        || parameter.hasParameterAnnotation(Max.class)
                        ? "OUT_OF_RANGE" :
                        parameter.hasParameterAnnotation(NotBlank.class)
                        ? "REQUIRED" : "INVALID_PARAMETER";

                for (var ignored : result.getResolvableErrors()) {
                    violations.add(new Violation(
                            field, code,
                            "Parameter does not satisfy constraints"));
                }
            }
        }

        return problem(status, headers, "REQUEST_VALIDATION_FAILED",
                "Request validation failed",
                "One or more parameters are invalid.", violations);
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return problem(status, headers, "MALFORMED_REQUEST_BODY",
                "Request body cannot be read",
                "Request body is missing or malformed.", null);
    }
}
~~~

Key points:
1. Extend `ResponseEntityExceptionHandler` and **override the corresponding methods**; do not add a duplicate `@ExceptionHandler(MethodArgumentNotValidException.class)` alongside the superclass.
2. `fieldViolation()` converts internal Bean Validation codes into public codes. Messages are controlled, never returning `getRejectedValue()`.
3. `handleMethodArgumentNotValid()` extracts field errors and object-level errors from `BindingResult`.
4. `handleHandlerMethodValidationException()` distinguishes **input constraints** from **return-value violations**; return violations return 500 with a safe body.
5. For `ParameterErrors` (e.g., cascaded DTOs inside method validation), the advice reads field paths. For direct query constraints, it uses `@RequestParam` to obtain the public name.
6. The example only maps a subset of annotations and parameters well: `@RequestParam`, `@Min`, `@Max`, `@NotBlank`, and DTO field errors. For `@PathVariable`, `@RequestHeader`, and cross-parameter/nested container constraints, implement a comprehensive mapper via `HandlerMethodValidationException.Visitor` or a domain abstraction; the `argumentN` fallback should not be relied on as a long-term public field name.
7. `handleHttpMessageNotReadable()` does not fabricate per-field violations when JSON could not be parsed.
8. `problem()` keeps HTTP status and JSON `status` aligned; the `violations` extension is included only in branches where violations are known.

**Version note:** this code uses Spring MVC 6.1+ classes/APIs. If a project runs Spring 6.0, `HandlerMethodValidationException` does not behave the same way yet. If a controller has class-level `@Validated`, AOP may throw `ConstraintViolationException` or `MethodValidationException` and require a different mapper. Only switch mechanisms with regression tests in place.

## 7. Example Request/Response and Expected Results

The project includes a Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell/CMD use `.\gradlew.bat bootRun`. With Spring dependencies, plain `javac` lacks the classpath; the Gradle plugin handles compilation/running.

### 7.1. DTO Violating Three Constraints

~~~bash
curl -i -X POST 'http://localhost:8080/api/registrations' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/problem+json' \
  -d '{"name":"","email":"not-an-email","seats":0}'
~~~

The `MethodArgumentNotValidException` path is converted by the advice to HTTP 400. Primary JSON fields:

~~~json
{
  "type": "about:blank",
  "title": "Request validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "code": "REQUEST_VALIDATION_FAILED",
  "violations": [
    {"field":"email","code":"INVALID_FORMAT","message":"Invalid field format"},
    {"field":"name","code":"REQUIRED","message":"This field is required"},
    {"field":"seats","code":"OUT_OF_RANGE","message":"Value is outside the allowed range"}
  ]
}
~~~

`instance` may be added automatically from the request path. Errors are sorted by `field`, placing `email` before `name` then `seats`; that is an **application-written rule**, independent of the order in which Hibernate Validator evaluates constraints.

### 7.2. Valid Input

~~~bash
curl -i -X POST 'http://localhost:8080/api/registrations' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","seats":2}'
~~~

Demo response defaults to HTTP 200:

~~~json
{"name":"Lan","seats":2}
~~~

The demo does not persist to a database and does not claim the registration was saved. Real resource-creation APIs should decide 201/Location, transactional behavior, and conflict exceptions separately.

### 7.3. Direct Method Validation

~~~bash
curl -i 'http://localhost:8080/api/registrations/check?minimumSeats=0'
~~~

With Spring MVC 6.1+, `@Min(1)` on the method parameter typically yields HTTP 400 and extensions:

~~~json
{
  "code":"REQUEST_VALIDATION_FAILED",
  "violations":[
    {
      "field":"minimumSeats",
      "code":"OUT_OF_RANGE",
      "message":"Parameter does not satisfy constraints"
    }
  ]
}
~~~

This is an **excerpt of the extensions** from the body; the full response also contains the RFC 9457 fields. `minimumSeats` is taken from the name explicitly declared in `@RequestParam`.

### 7.4. Syntactically Invalid JSON

~~~bash
curl -i -X POST 'http://localhost:8080/api/registrations' \
  -H 'Content-Type: application/json' \
  -d '{"name":'
~~~

The parser cannot construct a DTO; the advice returns HTTP 400 with `code=MALFORMED_REQUEST_BODY` and no `violations`. Do not report this as an error on field `name` when the parser cannot confirm it reliably.

### 7.5. Unconvertible Query Parameter

`GET /api/registrations/check?minimumSeats=abc` is typically rejected by Spring MVC before method validation with a conversion error, also HTTP 400, yet **the demo advice does not map it to a custom `code`**. If a system requires **every** 400 to carry a stable code, override `handleTypeMismatch(...)` and `handleMissingServletRequestParameter(...)`, assign `QUERY_PARAMETER_INVALID` / `REQUIRED_PARAMETER_MISSING`, and write tests. Do not assume the overrides in section 6 standardize every Spring exception.

## 8. MockMvc Contract Tests

`src/test/java/com/example/registration/web/RegistrationControllerTest.java`:

~~~java
package com.example.registration.web;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidDtoReturnsStableFieldErrors() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .accept(MediaType.valueOf("application/problem+json"))
                        .content("{\"name\":\"\",\"email\":\"not-an-email\","
                                + "\"seats\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.valueOf("application/problem+json")))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.code").value("REQUEST_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations.length()").value(3))
                .andExpect(jsonPath("$.violations[0].field").value("email"))
                .andExpect(jsonPath("$.violations[0].code").value("INVALID_FORMAT"))
                .andExpect(jsonPath("$.violations[1].field").value("name"))
                .andExpect(jsonPath("$.violations[1].code").value("REQUIRED"))
                .andExpect(jsonPath("$.violations[2].field").value("seats"))
                .andExpect(jsonPath("$.violations[2].code").value("OUT_OF_RANGE"));
    }

    @Test
    void directMethodConstraintIsRepresented() throws Exception {
        mvc.perform(get("/api/registrations/check")
                        .param("minimumSeats", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("REQUEST_VALIDATION_FAILED"))
                .andExpect(jsonPath("$.violations[0].field").value("minimumSeats"))
                .andExpect(jsonPath("$.violations[0].code").value("OUT_OF_RANGE"));
    }

    @Test
    void invalidJsonHasNoFakeFieldErrors() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MALFORMED_REQUEST_BODY"))
                .andExpect(jsonPath("$.violations").doesNotExist());
    }

    @Test
    void validDtoReturnsSuccessResponse() throws Exception {
        mvc.perform(post("/api/registrations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\",\"email\":\"lan@example.com\","
                                + "\"seats\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.seats").value(2));
    }

    @Test
    void invalidQueryConversionIsStillBadRequest() throws Exception {
        mvc.perform(get("/api/registrations/check")
                        .param("minimumSeats", "abc"))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

These tests focus on **HTTP status, public codes, field paths, and structure**, without asserting English message text since messages may be replaced by translations while keeping the contract valid. `violations[0]` is asserted because the advice code explicitly sorts them. If you prefer not to promise an order, assert by set membership; **never depend on ordering from the Bean Validation provider**.

In projects with Spring Security, custom MVC configs, Jackson modules, or other advices, MockMvc needs matching setup. The example does not automatically prove every Spring Boot project produces the exact same error JSON; verify with integration tests on your actual system.

## 9. Object-Level Errors, Nested Fields, and Complex Constraints

A complex request DTO may contain:

~~~json
{
  "contact": {"email":"invalid"},
  "items": [
    {"sku":"A","quantity":0},
    {"sku":"B","quantity":2}
  ]
}
~~~

To validate nested objects, add `@Valid` on properties that need cascading and real constraints inside nested records/classes. Field errors from Spring binding can carry paths like `contact.email` or `items[0].quantity`. This is **illustrative content**, not a payload handled by the flat registration demo.

You must decide whether field paths use:
- **Dotted/bracket notation**: `items[0].quantity`, close to Spring's representation.
- **JSON Pointer** per RFC 6901: `/items/0/quantity`, convenient for mapping JSON structure; special characters `~` and `/` must be escaped.

Do not mix the two path styles across endpoints. If a public DTO field is renamed from `contact.email` to `emailAddress`, the error contract can break the frontend even when HTTP 400 remains unchanged. A mapping layer from internal binding paths to public schema paths can help.

Constraints spanning multiple fields can produce an `ObjectError`; for example, `startDate` must precede `endDate`. Responses can use `field="$"` with `code=INVALID_OBJECT` or an extension `fields:["startDate","endDate"]` if highlighting both inputs. The demo uses `"$"` for object errors; that convention must be documented clearly.

## 10. Internationalization: Invariant Codes, Flexible Messages

A Vietnamese frontend might receive:

~~~json
{
  "code":"REQUEST_VALIDATION_FAILED",
  "violations":[
    {"field":"email","code":"INVALID_FORMAT","message":"Địa chỉ email không hợp lệ"}
  ]
}
~~~

With an English locale, the message might become `"Invalid email address"`, while `INVALID_FORMAT` and `REQUEST_VALIDATION_FAILED` stay unchanged. There are two options:
1. The backend uses `MessageSource` and the request locale to resolve messages by code and return translated strings.
2. The backend returns codes alongside required public parameters; the frontend translates from a UI catalog.

`FieldError` is a `MessageSourceResolvable` with `getCodes()`, `getArguments()`, and a default message. Spring's `MessageSource` supports keys like `NotBlank.registrationInput.name` when object/field names match, though **exact keys depend on binding names**. To decouple the API from Java DTO refactoring, you can use a dedicated catalog with keys like `api.required`, `api.invalidFormat`, `api.outOfRange`.

A message requiring a parameter:

~~~json
{
  "field":"name",
  "code":"INVALID_LENGTH",
  "message":"Name must not exceed 80 characters",
  "maxLength":80
}
~~~

`maxLength` is an extension that can help frontends; expose only public parameters. **The demo advice in section 6 does not emit `maxLength`**, because the `Violation` record only has field/code/message. If adding new fields, update DTO serializers, OpenAPI, and tests. Never expose raw regexes, SQL constraints, or internal security policies.

### Do Not Use Messages as Error Codes

Frontend code should not write:

~~~javascript
if (error.message.includes("must not be blank")) {
  showRequiredHint();
}
~~~

When the language or Bean Validation provider changes, that logic breaks. The right way:

~~~javascript
const violations = problem.violations ?? [];
for (const violation of violations) {
  if (violation.code === "REQUIRED") {
    showFieldError(violation.field, violation.message);
  }
}
~~~

This is a client-side JavaScript fragment; ``showFieldError` must be a UI-defined function. `problem` is the parsed JSON response object.

## 11. Extension Details: What Is Useful and What to Avoid

| Extension | When useful | Conditions |
| --- | --- | --- |
| `code` | Most errors requiring client handling | Stable code, documented |
| `violations` | Per-field validation | Path/code/message, allow multiple errors per field |
| `requestId` / `traceId` | Support, correlation | ID generated/verified by tracing infrastructure |
| `retryable` | APIs with a retry policy | Do not mark 400 validation as retryable |
| `retryAfterSeconds` | 429/503 with retry strategy | Must stay consistent with `Retry-After` header if present |
| `documentation` | Error explanation docs exist | Stable URI, versioned |
| `min`, `max`, `allowedValues` | Public input correction hints | Do not leak sensitive internal rules |
| `resource` or `operation` | Necessary business context | Do not leak unauthorized tenants/identifiers |

For 500, the body should be safe:

~~~json
{
  "type":"about:blank",
  "title":"Internal server error",
  "status":500,
  "detail":"The server could not complete the request.",
  "code":"INTERNAL_ERROR"
}
~~~

The server logs exception class, stack trace, and needed diagnostics through controlled channels. With `requestId`, users/support can look up incidents without public exception details. Never trust an arbitrary client-sent `X-Request-Id` as a security credential or log access key.

**Never emit:** `getRejectedValue()`, passwords, OTPs, tokens, session IDs, connection strings, full SQL queries, raw exception messages, stack traces, server file names, system paths, or upload contents. Logging raw inputs carries similar risks as returning them in responses.

### Personal Information Conflict Errors

A registration API might consider `EMAIL_ALREADY_REGISTERED` with HTTP 409. However, on systems where confirming whether an email exists is sensitive data, a specific response can create an enumeration risk. Choose an appropriate policy: some flows should return a neutral message. That is a business/security decision, not a Spring Validation default.

## 12. Error Registry and Code Compatibility

A registry table can define:

| Top-level `code` | HTTP | Description | Has `violations`? |
| --- | --- | --- | --- |
| `REQUEST_VALIDATION_FAILED` | 400 | Input bound, constraints violated | Yes |
| `MALFORMED_REQUEST_BODY` | 400 | Body missing/syntactically invalid/unparseable | Not required |
| `REQUIRED_PARAMETER_MISSING` | 400 | Required query/header/part missing | Per contract |
| `QUERY_PARAMETER_INVALID` | 400 | Query cannot be converted or is invalid | Per contract |
| `REGISTRATION_NOT_FOUND` | 404 | Resource does not exist | No |
| `EMAIL_ALREADY_REGISTERED` | 409 if policy allows | Business conflict | Per contract |
| `INTERNAL_ERROR` | 500 | Server error without disclosing cause | No |

This table is a **more complete design** than the demo. The code in section 6 implements `REQUEST_VALIDATION_FAILED`, `MALFORMED_REQUEST_BODY`, and `INTERNAL_ERROR` for return-value violations. The remaining codes require additional handlers/domain logic if used. Never promise clients will receive every code in a registry before the server implements them.

Governance rules:
- A code must not change meaning across versions just because Java exceptions changed.
- Clients must have an `UNKNOWN_ERROR` fallback when the backend introduces new codes.
- Changing a public code, the HTTP status for the same error, the `violations` schema, or field paths can be a **breaking change**.
- Changing message wording/locale is not necessarily a breaking change if clients branch on codes.
- Adding new extensions is usually safer when clients ignore unknown fields, though it still must be documented and tested.
- Document deprecation/removal rules for codes and maintain compatibility while multiple clients have not upgraded simultaneously.

Include the taxonomy in your OpenAPI schema and test the JSON contract. Never let raw `Exception.getClass().getSimpleName()` become a public code; class names frequently change across library upgrades or refactors.

## 13. When Errors Belong to the Domain Rather Than Validation

Validation checks only structure and input rules. A completely valid request can still fail to be processed:

~~~text
GET  /api/registrations/999 -> 404 REGISTRATION_NOT_FOUND
POST /api/registrations     -> 409 EMAIL_ALREADY_REGISTERED
POST /api/registrations     -> 400 REQUEST_VALIDATION_FAILED
~~~

These are **business contract examples**, not additional endpoints present in the demo. When implementing them, create dedicated domain exceptions/results. Do not catch all `IllegalArgumentException`s and return HTTP 400: an `IllegalArgumentException` may be a server code bug unrelated to client input.

Java snippet illustrating a dedicated handler (requires imports and defining `RegistrationNotFoundException` in a real project):

~~~java
@ExceptionHandler(RegistrationNotFoundException.class)
public ResponseEntity<ProblemDetail> notFound(
        RegistrationNotFoundException ex) {

    ProblemDetail body = ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
    body.setTitle("Registration not found");
    body.setDetail("The requested registration does not exist.");
    body.setProperty("code", "REGISTRATION_NOT_FOUND");
    return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
}
~~~

When added to a `ResponseEntityExceptionHandler` subclass, this handler processes only the defined custom domain exception, avoiding collisions with built-in exception hooks. In production, keep `detail` safe without revealing secret identifiers or authorization reasons the client should not know.

## 14. Logging, Observability, and Operations Support

A structured log entry can include:
- HTTP method, route template, status.
- Public top-level error code.
- Count of violations grouped by a bounded code set.
- Infrastructure-provided trace/request ID.
- Exception class and stack trace in a protected logging system, when needed.

Avoid using raw input, email, user-supplied messages, or raw URLs as metric labels: high cardinality and information leakage risks. Use route templates and the error-code registry for metrics. Clients can attach the request ID when contacting support; the backend looks it up in an access-controlled system.

`ErrorResponse`/`ProblemDetail` helps standardize output, but **does not automatically protect** against attaching sensitive extensions. Every property added to JSON must undergo the same review as normal API fields.

## 15. Common Pitfalls and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Client matches English text in `message` | Missing public codes | Use stable `code`; translate `message` independently |
| Response only says `"Validation failed"` | `FieldError` not mapped | Build `violations` with field + code |
| Raw `rejectedValue` returned | Copied internal validation object | Strip from public responses/logs |
| Invalid JSON syntax reports field errors | No DTO bound to validate | Use `MALFORMED_REQUEST_BODY` |
| Spring 6.1 controller throws different exception than before | Built-in method validation active | Handle both `MethodArgumentNotValidException` and `HandlerMethodValidationException` |
| AOP controller has class-level `@Validated` | Proxy method validation changes exception path | Check class annotations and Spring version |
| Server return-value violation returns 400 | Lumped input and server constraints together | Return 500, safely log cause |
| `BindingResult` has object errors yet JSON skips them | Only iterated `getFieldErrors()` | Handle `getGlobalErrors()` with a dedicated field rule |
| Two handlers process the same built-in exception | Duplicate override and `@ExceptionHandler` | Override the proper hook in `ResponseEntityExceptionHandler` |
| Nested field errors fail to highlight UI inputs | Inconsistent path format | Publish dotted path or JSON Pointer and map consistently |
| Tests break when language changes | Asserted message instead of code | Test status/code/path; test localization separately |
| Upgrading Spring Data/Validator changes error codes | Exposed internal exception/constraint codes | Map to public registry codes |
| 500 leaks SQL exception | Returned `ex.getMessage()` directly | Safe detail + requestId and internal log |
| Endpoints place `code` in different locations | No shared schema | Choose top-level extension and verify JSON |
| Project handles only some 400s | Missed missing/type mismatch/multipart | List primary exceptions, expand advice, and test |

## 16. Implementation Checklist

1. Choose RFC 9457 or another consistent schema; document status and `Content-Type`.
2. Create a registry for top-level and field-level error codes.
3. Define `violations`: field path, code, message, object errors, and multiple-errors-per-field policy.
4. Separate parsing/conversion errors from Bean Validation and business conflicts.
5. Override the proper `ResponseEntityExceptionHandler` hooks; avoid duplicate handlers.
6. For Spring MVC 6.1+, support `HandlerMethodValidationException` and distinguish input 400 from return-value 500.
7. If using class-level AOP `@Validated`, inspect the proxy path and actual exceptions.
8. Never echo sensitive inputs/`rejectedValue`/stack traces.
9. Use `MessageSource` or UI catalogs to translate text while keeping codes invariant.
10. Write MockMvc tests for valid requests, multiple field errors, method constraints, parse errors, missing/type mismatch, and domain errors.
11. Attach a trusted correlation ID to observability where needed.
12. Document schema/field paths and versioning policy so frontends do not depend on implementation details.

### Self-Check Questions

**1.** Why should `FieldError.getDefaultMessage()` not be used as a branching key in the frontend?

**Answer:** Messages can change across locales, providers, or UX wording updates. Clients must rely on stable public codes.

**2.** How does `ProblemDetail.setProperty("code","...")` serialize to JSON?

**Answer:** With Spring's Jackson support, extension properties are normally unwrapped into top-level fields like `code` alongside `status`, rather than nested under `properties`.

**3.** Which exception is typically thrown when `@Valid @RequestBody` fails?

**Answer:** `MethodArgumentNotValidException` under individual argument validation. When a method has direct constraints in Spring MVC 6.1+, `HandlerMethodValidationException` can also wrap cascaded DTO errors.

**4.** When JSON cannot be parsed, should you emit a violation with `field=name`?

**Answer:** No, if the parser cannot determine the exact field reliably. Classify as `MALFORMED_REQUEST_BODY` rather than guessing field causes.

**5.** When a method returns a value violating a return-value constraint, should it return 400 or 500?

**Answer:** 500, because it is a server-side contract bug rather than client input that the caller can fix.

**6.** Where should `requestId` come from?

**Answer:** From tracing infrastructure or a servlet filter with a generation/verification policy; never treat arbitrary client-supplied request IDs as trusted.

## 17. Official References

- [Spring Framework — Error Responses (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`, `ErrorResponse`, `ResponseEntityExceptionHandler`, extension members, and `MessageSource`.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): individual argument validation, method validation, `BindingResult`, and MVC exceptions.
- [Spring Framework — RequestBody validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): HTTP message conversion, `@Valid`, and input errors.
- [Spring Framework — `ProblemDetail` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/ProblemDetail.html): `forStatus` and `setProperty`.
- [Spring Framework — `ResponseEntityExceptionHandler` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): hooks to override.
- [Jakarta Bean Validation Specification 3.0](https://jakarta.ee/specifications/bean-validation/3.0/): constraints, cascading, and executable validation.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html): standard structure and extension members.

**Key takeaway:** HTTP status classifies errors at the protocol level; API `code` lets machines decide behavior; `violations[].field/code` points to what needs fixing; and `message`/`detail` helps humans understand the issue. Keep these four layers cleanly separated so your API is easy to test, translate, evolve, and secure.
