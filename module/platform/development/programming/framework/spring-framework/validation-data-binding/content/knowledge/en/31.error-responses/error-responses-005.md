# Version-Aware `ProblemDetail` and `ErrorResponse` in Spring Framework

## Learning objectives

When a REST API receives malformed JSON, form data violating a constraint, a missing query parameter, or a request for a non-existent order, the server must return an error that clients can parse **machine-readably**, **clearly**, **safely**, and **reliably across framework versions**. In modern Spring Framework, two key concepts are `ProblemDetail` and `ErrorResponse`. They are not synonymous:

- `ProblemDetail` is the **error payload object** based on the Problem Details for HTTP APIs standard (RFC 9457, superseding RFC 7807).
- `ErrorResponse` is Spring's **error response contract**, encompassing the HTTP status, headers, and a `ProblemDetail` body. Many Spring MVC/WebFlux exceptions implement this contract.

This lesson belongs to the **Error Responses** group and specifically emphasizes **"version-aware"**: you must check whether your project uses Spring 5.x, 6.0, 6.1, 6.2, or 7.x before copying a newer API. After this lesson, you will be able to:

1. Explain the five standard fields `type`, `title`, `status`, `detail`, `instance`, and extension properties.
2. Create a `ProblemDetail` via `forStatus(...)`/`forStatusAndDetail(...)`, populate appropriate fields, and return it from `@ExceptionHandler`.
3. Distinguish `ProblemDetail`, `ErrorResponse`, `ErrorResponseException`, and `ResponseEntityExceptionHandler`.
4. Customize `@Valid @RequestBody` errors via `MethodArgumentNotValidException` and native method validation errors via `HandlerMethodValidationException` on supported versions.
5. Understand `spring.mvc.problemdetails.enabled`/`spring.webflux.problemdetails.enabled`, `@RestControllerAdvice` usage, and handler ordering.
6. Use `MessageSource` to localize `detail` without exposing private data, and add a list of field errors with a stable convention.
7. Write and test a Spring Boot 3.5 / Java 17+ API with predictable 201, 400, and 404 outcomes.
8. Choose a backward-compatible strategy for Spring 5.x or projects that do not enable standard problem responses.

## 1. Why do we need a common error format?

Without a shared contract, every endpoint can return a different shape:

~~~json
{"message":"bad input"}
~~~

~~~json
{"status":"ERROR","errorCode":12,"errors":["quantity"]}
~~~

~~~text
Order missing
~~~

Clients end up writing multiple parsers for the same class of failure. RFC 9457 defines a standard structure, typically served with media type `application/problem+json`:

~~~json
{
  "type": "https://example.org/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "The requested order does not exist.",
  "instance": "/api/orders/999",
  "code": "ORDER_NOT_FOUND"
}
~~~

The first five members are standard members; `code` is an application extension field. Spring can serialize a `ProblemDetail` object into this JSON when Jackson is on the classpath.

**Distinguish HTTP status from JSON `status`:** the actual response must be HTTP **404**, while `"status":404` merely restates the status so the body remains self-descriptive when stored or inspected outside the HTTP exchange. Never intentionally return HTTP 200 with `"status":404` in the body. RFC 9457 expects the embedded status to match the actual HTTP status produced by the server.

### 1.1. The five standard members

| Member | Purpose | Notes |
| --- | --- | --- |
| `type` | URI identifying the error **type**, relatively stable | Need not be dereferenceable, though HTTPS URLs should ideally point to documentation |
| `title` | Short summary describing the problem type | Should stay stable for the same `type` |
| `status` | Numeric HTTP status code | Must match the actual response status |
| `detail` | Explanation of the **specific occurrence** | Can be localized; must not contain stack traces or secrets |
| `instance` | URI identifying the specific occurrence/scope, typically the request path | Need not include a full domain; should not leak tokens in query strings |

The default `type` may be `about:blank`, indicating no specialized problem type is defined. The default `title` typically follows the HTTP status reason phrase when available. `instance` can be populated by Spring from the request path if unset and rendered via framework-supported paths.

### 1.2. Extension properties

The specification allows adding custom attributes such as:

~~~json
{
  "type": "https://example.org/problems/invalid-request",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "instance": "/api/orders",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerName", "code": "NotBlank"},
    {"field": "quantity", "code": "Min"}
  ]
}
~~~

`errors` is **not a mandatory RFC 9457 field**: it is a custom contract defined by the API. When defining extensions, clearly document their names, JSON types, ordering semantics if significant, and versioning policy. Avoid colliding with standard member names. The field-error list should contain machine-processable values (`field`, `code`) and, if needed, a localized message.

**Never automatically include `FieldError`'s `rejectedValue` in the payload**, because it may contain passwords, access tokens, personal health data, or unescaped user content.

## 2. Version support matrix

Distinguish **Spring Framework** (which defines the APIs) from **Spring Boot** (which provides auto-configuration and dependency management). Key milestones:

| Technology line | Capabilities | How to apply |
| --- | --- | --- |
| Spring Framework 5.3 / Boot 2.x | Lacks Spring 6's `org.springframework.http.ProblemDetail` and `org.springframework.web.ErrorResponse` | Use `@ExceptionHandler` + custom error DTO + `ResponseEntity` |
| Spring Framework 6.0 / Boot 3.0+ | Introduces `ProblemDetail`, `ErrorResponse`, `ErrorResponseException`, and Problem Details support in `ResponseEntityExceptionHandler` | Return `ProblemDetail` directly from advice/handlers |
| Spring Framework 6.1 / Boot 3.2+ | Native **controller method validation** and `HandlerMethodValidationException`; more complete APIs | Handle method-level validation explicitly when needed |
| Spring Framework 6.2 / Boot 3.4, 3.5 | Adds `ErrorResponse.Interceptor` and configuration hooks such as `WebMvcConfigurer.addErrorResponseInterceptors(...)` | Enrich or enforce policies across rendered `ProblemDetail` responses |
| Spring Framework 7.x / Boot 4.x | Continues supporting these abstractions with potential config extensions and signature/API changes per minor | Check documentation/Javadoc **for the exact release line** before migrating |

This table outlines **feature milestones** rather than guaranteeing compatibility across arbitrary version combinations. For instance, Spring Boot 3.5.x normally manages Spring Framework 6.2.x. Do not force a Spring Framework version different from Boot's dependency BOM without verifying compatibility.

**RFC 7807 vs. RFC 9457:** Spring Framework 6.0 was released when many references still called Problem Details RFC 7807. RFC 9457 later obsoleted, clarified, and updated the spec. Spring 6.x's `ProblemDetail` class remains the corresponding type; there is no mandatory new Java class named `Rfc9457ProblemDetail`. When older docs mention RFC 7807, check the version before assuming the code is obsolete.

### 2.1. Verify capabilities instead of guessing from API names

Before adopting sample code, check:

~~~bash
mvn dependency:tree
~~~

or inspect the Spring Framework version in the Spring Boot BOM / Gradle dependency report. Consult the Javadoc for that exact version:

~~~text
org.springframework.http.ProblemDetail
org.springframework.web.ErrorResponse
org.springframework.web.ErrorResponseException
org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler
org.springframework.web.method.annotation.HandlerMethodValidationException
org.springframework.web.servlet.config.annotation.WebMvcConfigurer
~~~

A method present in Spring 7 or 6.2 Javadoc may **not exist in 6.0**. A `"cannot find symbol"` compiler error when copying a newer hook does not necessarily mean a wrong import: the feature may simply not exist in your current dependency version.

## 3. `ProblemDetail`: creating an error body

`ProblemDetail` lives in:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
~~~

Common creation pattern:

~~~java
ProblemDetail problem = ProblemDetail.forStatusAndDetail(
        HttpStatus.NOT_FOUND,
        "The requested order does not exist.");

problem.setType(URI.create(
        "https://example.org/problems/order-not-found"));
problem.setTitle("Order not found");
problem.setInstance(URI.create("/api/orders/999"));
problem.setProperty("code", "ORDER_NOT_FOUND");
~~~

This is a **snippet** requiring `import java.net.URI`, not a standalone program. `forStatus(HttpStatus.BAD_REQUEST)` is also available when you do not want to set `detail` immediately. In Spring 6.x, `ProblemDetail` provides setters for standard members and extension properties.

### 3.1. How should `type` be used?

A good convention is using stable URIs:

~~~text
https://example.org/problems/validation-failed
https://example.org/problems/order-not-found
https://example.org/problems/order-conflict
~~~

Do not generate `type` per request detail, such as `/problems/order-999-missing`; `type` identifies the **category**, whereas `instance` identifies the **occurrence**. Clients can branch logic on `type` or the `code` extension. If using URLs as types, publish documentation explaining the error category, remediation, and versioning.

### 3.2. `getProperties` and Jackson

`ProblemDetail.setProperty("code", "ORDER_NOT_FOUND")` adds an extension to the properties map. With Spring's Jackson integration, entries in the extension map are **unwrapped into top-level JSON fields** alongside `type`/`title`/`status`/`detail`/`instance`. Other serializers may nest them under a `properties` key; therefore, test actual JSON output and do not assume non-Spring/non-Jackson frameworks behave identically.

`ProblemDetail` also supports subclassing for strongly typed extension properties via its copy constructor. This is helpful when SDKs or OpenAPI clients need a strictly modeled extension schema. For a few keys like `code` and `errors`, `setProperty(...)` is usually sufficient.

## 4. `ErrorResponse` is more than a JSON body

`org.springframework.web.ErrorResponse` is an **interface**, not a JSON bean replacing `ProblemDetail`. It represents a complete error response:

~~~text
ErrorResponse
  |
  +-- getStatusCode()    → HTTP 400/404/409...
  +-- getHeaders()       → headers to send
  +-- getBody()          → ProblemDetail
  +-- message codes      → customize type/title/detail via MessageSource
~~~

Many Spring MVC/WebFlux exceptions implement `ErrorResponse`, including `MethodArgumentNotValidException` and `HandlerMethodValidationException` on supported versions. This lets the framework handle status, headers, and body uniformly.

### 4.1. `ErrorResponseException`

`org.springframework.web.ErrorResponseException` is a `RuntimeException` that implements `ErrorResponse`. It is useful when you want to **throw an error with a defined HTTP status and body** rather than inventing a custom exception from scratch.

~~~java
ProblemDetail body = ProblemDetail.forStatusAndDetail(
        HttpStatus.CONFLICT,
        "Order cannot be modified in its current state.");

body.setType(URI.create(
        "https://example.org/problems/order-conflict"));
body.setProperty("code", "ORDER_CONFLICT");

throw new ErrorResponseException(
        HttpStatus.CONFLICT, body, null);
~~~

This snippet requires imports for `ErrorResponseException`, `HttpStatus`, `ProblemDetail`, and `URI`. The constructor taking `HttpStatusCode status`, `ProblemDetail body`, and optional `Throwable cause` has existed since Spring 6.0. When an appropriate handler is present, the exception is rendered with the `ProblemDetail` body. For pure domain exceptions, a dedicated `@ExceptionHandler` remains appropriate if you want to keep Spring HTTP classes out of your domain model.

### 4.2. Builders and i18n

Spring provides `ErrorResponse.builder(...)` / `ErrorResponse.create(...)` in supported versions; the builder lets you declare status, detail, and message codes. An `ErrorResponse` supplies codes to resolve `type`, `title`, and `detail` through `MessageSource`. This differs from a plain `ProblemDetail`, which only holds payload data and does not carry exception message-code resolution rules on its own.

Notable APIs:

~~~java
HttpStatusCode status = errorResponse.getStatusCode();
HttpHeaders headers = errorResponse.getHeaders();
ProblemDetail body = errorResponse.getBody();
~~~

This snippet assumes `errorResponse` is already in scope. In an error-handling layer, **never** mutate a shared static `ProblemDetail` instance across requests: fields such as `instance`, localized messages, and trace metadata belong to a single error occurrence, and reusing a mutable instance can leak data across requests.

## 5. Rendering via `@ExceptionHandler` and `ResponseEntityExceptionHandler`

In Spring MVC annotated controllers, there are several ways to use Problem Details:

1. Return `ProblemDetail` directly from `@ExceptionHandler`.
2. Return `ResponseEntity<ProblemDetail>` to control status and headers.
3. Throw an `ErrorResponseException` for the framework or advice to handle.
4. Extend `ResponseEntityExceptionHandler` in `@ControllerAdvice`/`@RestControllerAdvice` to handle built-in exceptions and override protected hooks as needed.

### 5.1. `@ExceptionHandler` returning `ProblemDetail`

~~~java
@RestControllerAdvice
class DomainErrors {

    @ExceptionHandler(OrderMissingException.class)
    ProblemDetail notFound(OrderMissingException ex) {
        ProblemDetail p = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND,
                "Requested order does not exist.");

        p.setTitle("Order not found");
        p.setType(URI.create(
                "https://example.org/problems/order-not-found"));
        return p;
    }
}
~~~

This is a **snippet**, assuming an application-defined `OrderMissingException`. Spring MVC understands `ProblemDetail`'s `status` and prefers Problem Details media types such as `application/problem+json` during content negotiation; for responses processed through framework mechanisms, `instance` can be populated from the request path if unset.

If you need to send headers such as `Retry-After` or `WWW-Authenticate`, you may need `ResponseEntity` or an `ErrorResponse` carrying those headers; do not put all HTTP metadata solely inside the JSON body.

### 5.2. What does `ResponseEntityExceptionHandler` solve?

A `@RestControllerAdvice extends ResponseEntityExceptionHandler` inherits handling logic for many Spring MVC exceptions (unreadable JSON, wrong media type, `MethodArgumentNotValidException`, missing parameters, etc.). The base class provides the `@ExceptionHandler` methods and protected hooks to customize responses **without copying all of the framework's exception handling logic**.

Example override for validation errors:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    ProblemDetail body = ex.getBody();
    body.setTitle("Validation failed");
    body.setDetail("One or more fields are invalid.");
    return handleExceptionInternal(
            ex, body, headers, status, request);
}
~~~

This snippet belongs inside a matching subclass with imports. `handleMethodArgumentNotValid` has this signature in Spring 6.0–6.2. Never redeclare `@ExceptionHandler(MethodArgumentNotValidException.class)` on an advice extending this base class: that can create a duplicate exception handler mapping colliding with the inherited method.

### 5.3. An HTTP error is not always a validation error

| Scenario | Typical exception | Meaning |
| --- | --- | --- |
| `@Valid @RequestBody DTO` fails a constraint | `MethodArgumentNotValidException` | Invalid input bean |
| Unparseable JSON | `HttpMessageNotReadableException` | HTTP body decoding failed before validation |
| `@RequestParam @Min(1) int count` violated (Spring 6.1+) | `HandlerMethodValidationException` | Native controller method validation |
| URL mapped but HTTP method unsupported | `HttpRequestMethodNotSupportedException` | HTTP 405 |
| `Content-Type` not accepted | `HttpMediaTypeNotSupportedException` | HTTP 415 |
| Domain cannot find entity | Custom `OrderMissingException` | Application maps to 404 |
| Unexpected bug | `NullPointerException` or internal exception | Typically HTTP 500; must not be disguised as an input error |

**Note on method validation:** `@Valid` only marks bean validation/cascading; direct constraints like `@Min` on a method parameter can trigger native method validation in Spring Framework 6.1+. Method input failures normally map to 400, whereas return-value constraint violations are server errors and can map to 500. Do not conflate the two.

## 6. Does Spring Boot enable Problem Details automatically or must it be configured?

In Spring Boot 3.x, the key property is:

~~~properties
spring.mvc.problemdetails.enabled=true
~~~

When enabled, Boot auto-configures a `ResponseEntityExceptionHandler` for common web exceptions to render Problem Details. If disabled, do not assume every Spring exception in your app automatically returns RFC 9457; default responses may be handled by `BasicErrorController` or default exception resolvers depending on configuration.

For WebFlux:

~~~properties
spring.webflux.problemdetails.enabled=true
~~~

This is the **reactive stack property**, not a replacement for the MVC property. Choose the one matching your starter and application type.

### Two alternative strategies

**Strategy A — use Boot auto-configuration:** set `spring.mvc.problemdetails.enabled=true`, then add an advice with higher precedence if you want to override specific exceptions. Boot's auto-configured advice has a specific order, typically `0` in documentation; verify your exact version before relying on ordering.

**Strategy B — self-managed advice:** leave Boot auto Problem Details disabled, write a `@RestControllerAdvice extends ResponseEntityExceptionHandler`, override the needed protected handlers, and handle domain exceptions yourself. The runnable example in Section 9 uses Strategy B.

**Do not** combine both haphazardly and hope the framework picks the handler you want. Two advices both mapping built-in exceptions can compete by order and scope. Write `MockMvc` tests for each important exception; avoid placing a catch-all `Exception.class` handler in a high-precedence advice if it would swallow existing 400/404 mappings.

## 7. Field errors: controlled extensions

RFC 9457 does not mandate a single schema for multi-field errors. An API can place a normalized list in `errors`:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "errors": [
    {"field": "customerName", "code": "NotBlank"},
    {"field": "quantity", "code": "Min"}
  ]
}
~~~

Spring MVC error source:

~~~java
List<FieldError> fields =
        ex.getBindingResult().getFieldErrors();

for (FieldError error : fields) {
    String name = error.getField();
    String code = error.getCode();
    String message = error.getDefaultMessage();
    boolean conversionFailure = error.isBindingFailure();
}
~~~

This snippet assumes `ex` is `MethodArgumentNotValidException` and requires importing `FieldError`. `getCode()` can be `NotBlank`, `Min`, `typeMismatch`, or another code produced by a validator/custom resolver. Keep `code` for machine logic; `message` can be localized for the request locale.

**Do not** put:

~~~java
error.getRejectedValue()
~~~

into JSON simply because the accessor exists. The rejected value may be a password/token, medical record, or unsanitized user input; similarly, raw exception messages may leak class names or database queries.

### 7.1. Stability of the `errors` array

Jakarta Validation's constraint violation set does not guarantee a UX-friendly order. If the JSON contract needs deterministic ordering, sort by `field` then `code`, or follow a product-defined field order. A single field can also have multiple violations. Do not automatically collapse them into a `Map<String,String>` that drops other errors if the business requires showing all of them.

### 7.2. Binding differs from Bean Validation

`quantity=abc` in an HTML form bound to `Integer quantity` is a **type conversion error** (`typeMismatch`), whereas `quantity=0` is a **`@Min` violation** after conversion succeeded. With JSON, `{"quantity":"abc"}` can fail during Jackson deserialization and raise `HttpMessageNotReadableException` instead of `MethodArgumentNotValidException`. Do not expect every bad input to produce a `FieldError`; your error response layer must recognize which phase failed.

## 8. Internationalizing `type`/`title`/`detail`

Exceptions implementing `ErrorResponse` expose message codes that `ResponseEntityExceptionHandler` and `MessageSource` can look up:

~~~text
problemDetail.type.<fully-qualified-exception-class>
problemDetail.title.<fully-qualified-exception-class>
problemDetail.<fully-qualified-exception-class>
~~~

Example for `MethodArgumentNotValidException`:

~~~properties
problemDetail.title.org.springframework.web.bind.MethodArgumentNotValidException=Invalid request
problemDetail.org.springframework.web.bind.MethodArgumentNotValidException=Request validation failed
~~~

This is a Spring 6.x example; exact default codes and detail arguments depend on the exception and version. For a `FieldError`, Spring generates codes like `NotBlank.createOrderCommand.customerName` and `NotBlank.customerName`, distinct from `ErrorResponse`'s code group.

Spring documentation notes that `ErrorResponse` supports default message codes for **type, title, and detail**, and detail arguments can be resolved via `MessageSource`. `ResponseEntityExceptionHandler` handles localization before rendering. If your code sets `title`/`detail` manually on a `ProblemDetail` without using `ErrorResponse` resolution, call `MessageSource` directly as shown in Section 9.

**Adopt a clear policy:**

- `type`: stable URI, never changes with locale.
- `code`: stable client identifier, never changes with locale.
- `title`: may be translated while keeping consistent meaning.
- `detail`: message translated per `Accept-Language`, never containing secrets.
- `errors[].code`: kept stable; `errors[].message`, if present, is translated.

## 9. Runnable demo: Spring Boot 3.5.7 / Spring MVC / Java 17+

Let's build an API with three behaviors:

1. `POST /api/orders` accepts JSON via `@Valid @RequestBody`; returns 201 on success, or a 400 `ProblemDetail` with `errors` on invalid fields.
2. `GET /api/orders/{id}`: `id=1` returns data; any other ID returns 404 with clear `type` and `code`.
3. `GET /api/orders/limits?count=...`: direct `@Min(1)` tests Spring 6.1+ native method validation, returning 400 handled by base `ResponseEntityExceptionHandler` when invalid.

The example chooses **manual `@RestControllerAdvice extends ResponseEntityExceptionHandler`** with Boot auto-advice disabled so error customization is explicit. There is no database or Spring Security in the demo; in production, add authorization and never rely on simple IDs for access control.

### 9.1. Directory structure

~~~text
problem-details-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/problems/
    │   │   ├── Application.java
    │   │   ├── CreateOrderCommand.java
    │   │   ├── OrderReceipt.java
    │   │   ├── OrderMissingException.java
    │   │   ├── OrderController.java
    │   │   └── ApiErrorAdvice.java
    │   └── resources/
    │       ├── application.properties
    │       ├── messages.properties
    │       └── messages_vi.properties
    └── test/
        └── java/com/example/problems/
            └── OrderApiTest.java
~~~

### 9.2. `pom.xml`

~~~xml
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

    <groupId>com.example</groupId>
    <artifactId>problem-details-demo</artifactId>
    <version>1.0.0</version>

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

`spring-boot-starter-web` provides Spring MVC + Jackson, `spring-boot-starter-validation` provides Jakarta Bean Validation, and the test starter provides `MockMvc`/JUnit. No extra dependency is needed for `ProblemDetail` because it is part of Spring Framework 6.x. The Spring Boot parent manages dependency versions; in production, use a patched release maintained by your organization.

### 9.3. `Application.java`

~~~java
package com.example.problems;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

### 9.4. `CreateOrderCommand.java`

~~~java
package com.example.problems;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateOrderCommand(
        @NotBlank String customerName,
        @NotNull @Min(1) Integer quantity) {
}
~~~

`@NotBlank` checks that the name is not empty/whitespace; `@NotNull` requires a quantity; `@Min(1)` requires a positive number. Using `Integer` represents `null` when the field is omitted. A `record` suits an immutable JSON API DTO. These validation annotations come from `jakarta.validation`, not Spring Boot 2's `javax.validation` package.

### 9.5. `OrderReceipt.java`

~~~java
package com.example.problems;

public record OrderReceipt(
        String result,
        String customerName,
        Integer quantity) {
}
~~~

This is a demo DTO to verify 200/201 responses without a database.

### 9.6. `OrderMissingException.java`

~~~java
package com.example.problems;

public final class OrderMissingException
        extends RuntimeException {
}
~~~

The example intentionally avoids embedding raw input into the exception. Real applications can store internal diagnostic metadata separately; internal messages should not be exposed directly to clients.

### 9.7. `OrderController.java`

~~~java
package com.example.problems;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<OrderReceipt> create(
            @Valid @RequestBody CreateOrderCommand command) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new OrderReceipt(
                        "created",
                        command.customerName(),
                        command.quantity()));
    }

    @GetMapping("/{id}")
    public OrderReceipt find(@PathVariable long id) {
        if (id != 1L) {
            throw new OrderMissingException();
        }
        return new OrderReceipt("found", "Lan", 2);
    }

    @GetMapping("/limits")
    public String limits(
            @RequestParam @Min(1) int count) {
        return "limit:" + count;
    }
}
~~~

**Note:** Omit class-level `@Validated` on the controller if you want Spring 6.1+'s native controller method validation. `@Min(1)` on `count` is a direct constraint so it can trigger `HandlerMethodValidationException`; `@Valid` on the JSON DTO uses standard argument validation.

### 9.8. `ApiErrorAdvice.java`

~~~java
package com.example.problems;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.MessageSource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.context.request.WebRequest;

import java.net.URI;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

@RestControllerAdvice
public class ApiErrorAdvice extends ResponseEntityExceptionHandler {

    private final MessageSource messages;

    public ApiErrorAdvice(MessageSource messages) {
        this.messages = messages;
    }

    public record FieldIssue(String field, String code) {
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<FieldIssue> issues = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        Objects.toString(error.getCode(), "invalid")))
                .sorted(Comparator.comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        ProblemDetail body = ex.getBody();
        body.setType(URI.create(
                "https://example.org/problems/validation"));
        body.setTitle("Validation failed");
        body.setDetail("One or more fields are invalid.");
        body.setProperty("code", "VALIDATION_FAILED");
        body.setProperty("errors", issues);

        return handleExceptionInternal(
                ex, body, headers, status, request);
    }

    @ExceptionHandler(OrderMissingException.class)
    public ProblemDetail orderMissing(
            OrderMissingException ex,
            HttpServletRequest request,
            Locale locale) {

        String detail = messages.getMessage(
                "problem.orderMissing", null, locale);

        ProblemDetail body = ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, detail);

        body.setType(URI.create(
                "https://example.org/problems/order-not-found"));
        body.setTitle("Order not found");
        body.setInstance(URI.create(request.getRequestURI()));
        body.setProperty("code", "ORDER_NOT_FOUND");
        return body;
    }
}
~~~

Detailed breakdown:

- `ApiErrorAdvice` extends `ResponseEntityExceptionHandler`; it does not declare a second `@ExceptionHandler(MethodArgumentNotValidException.class)` because the base class already defines one.
- `handleMethodArgumentNotValid(...)` is overridden with the exact Spring 6.2 signature: third argument `HttpStatusCode`, last argument `WebRequest`.
- `ex.getBody()` returns a `ProblemDetail` bound to the exception; we mutate the body **for the current failure only**, never a shared static mutable object.
- `FieldIssue` holds only `field` and `code`. It never echoes `getRejectedValue()`, exception stack traces, or the target object.
- The `errors` list is sorted for deterministic tests and contracts. If a field has multiple errors, each produces an entry.
- `handleExceptionInternal(...)` preserves the status and headers selected by the framework; do not hardcode 400 and ignore the status/headers from the exception.
- `orderMissing(...)` uses `MessageSource` and `Locale` to translate `detail` for a domain exception while keeping `type`/`code` stable.
- `instance` sets the request path without query/tokens; the HTTP status comes from `ProblemDetail.status` (404).
- For other built-in exceptions such as malformed JSON and method validation, inherited logic in `ResponseEntityExceptionHandler` builds appropriate Problem Details rather than lumping every exception into `VALIDATION_FAILED`.

The `https://example.org/problems/...` URIs in the demo are illustrative namespaces; real projects replace them with controlled API documentation domains rather than keeping example URLs in production.

### 9.9. `application.properties`

~~~properties
server.port=8080
spring.mvc.problemdetails.enabled=false
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

Why explicitly set `spring.mvc.problemdetails.enabled=false`? The example already has an advice extending `ResponseEntityExceptionHandler`, so we do not want Boot to register another built-in advice that competes with it. **Disabling Boot's auto-advice does not disable the `ProblemDetail` class or custom advice logic.** If you choose Boot's auto-advice strategy, enable this property and account for advice ordering differences.

### 9.10. `messages.properties`

~~~properties
problem.orderMissing=Requested order does not exist.
~~~

### 9.11. `messages_vi.properties`

~~~properties
problem.orderMissing=Đơn hàng không tồn tại.
~~~

These are Spring `MessageSource` bundles used in `orderMissing(...)`. `Locale` is resolved by Spring MVC from request headers. There is no need to put raw messages in exceptions or controllers. Spring Boot discovers the message source via the base bundle `messages.properties`.

### 9.12. Running with Maven

~~~bash
mvn spring-boot:run
~~~

Success:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerName":"Lan","quantity":2}'
~~~

Expected status **201 Created**, JSON body:

~~~json
{
  "result": "created",
  "customerName": "Lan",
  "quantity": 2
}
~~~

Constraint violation:

~~~bash
curl -i -X POST "http://localhost:8080/api/orders" \
  -H "Content-Type: application/json" \
  -d '{"customerName":"","quantity":2}'
~~~

Expected status **400 Bad Request**, media type compatible with `application/problem+json`, body containing at least:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more fields are invalid.",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerName", "code": "NotBlank"}
  ]
}
~~~

Spring may also populate `instance` from the request path. Do not write tests matching the entire JSON verbatim if default fields may vary across framework versions; assert the contract members defined by your application.

Domain 404:

~~~bash
curl -i -H "Accept-Language: vi" \
  "http://localhost:8080/api/orders/999"
~~~

Expected body:

~~~json
{
  "type": "https://example.org/problems/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "Đơn hàng không tồn tại.",
  "instance": "/api/orders/999",
  "code": "ORDER_NOT_FOUND"
}
~~~

For syntactically broken JSON, such as `{"quantity":`, the expected response is HTTP 400 from `HttpMessageNotReadableException`; the exact default body may vary across Spring minor versions. `ResponseEntityExceptionHandler` builds a suitable error response, though the demo does not assert a fixed error message string.

## 10. `MockMvc`: verifying HTTP status and JSON contract

File `src/test/java/com/example/problems/OrderApiTest.java`:

~~~java
package com.example.problems;

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
class OrderApiTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validJsonCreatesOrder() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerName":"Lan","quantity":2}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.result").value("created"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void invalidBeanReturnsProblemDetails() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerName":"","quantity":2}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400))
                .andExpect(jsonPath("$.title").value(
                        "Validation failed"))
                .andExpect(jsonPath("$.code").value(
                        "VALIDATION_FAILED"))
                .andExpect(jsonPath("$.errors[0].field").value(
                        "customerName"))
                .andExpect(jsonPath("$.errors[0].code").value(
                        "NotBlank"));
    }

    @Test
    void missingQuantityAlsoProducesFieldError()
            throws Exception {

        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"customerName":"Lan"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field").value(
                        "quantity"))
                .andExpect(jsonPath("$.errors[0].code").value(
                        "NotNull"));
    }

    @Test
    void domainNotFoundUsesEnglishMessage()
            throws Exception {

        mvc.perform(get("/api/orders/999")
                        .header("Accept-Language", "en"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.code").value(
                        "ORDER_NOT_FOUND"))
                .andExpect(jsonPath("$.detail").value(
                        "Requested order does not exist."))
                .andExpect(jsonPath("$.instance").value(
                        "/api/orders/999"));
    }

    @Test
    void domainNotFoundUsesVietnameseMessage()
            throws Exception {

        mvc.perform(get("/api/orders/999")
                        .header("Accept-Language", "vi"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.detail").value(
                        "Đơn hàng không tồn tại."));
    }

    @Test
    void existingOrderSucceeds() throws Exception {
        mvc.perform(get("/api/orders/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.result").value("found"));
    }

    @Test
    void malformedJsonIsBadRequest() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void nativeMethodValidationRejectsCount()
            throws Exception {

        mvc.perform(get("/api/orders/limits")
                        .param("count", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_PROBLEM_JSON))
                .andExpect(jsonPath("$.status").value(400));
    }

    @Test
    void nativeMethodValidationAcceptsCount()
            throws Exception {

        mvc.perform(get("/api/orders/limits")
                        .param("count", "3"))
                .andExpect(status().isOk())
                .andExpect(content().string("limit:3"));
    }
}
~~~

Run:

~~~bash
mvn test
~~~

**Nine tests** verify: 201 creation, 400 `NotBlank` with extension, missing quantity producing `NotNull`, domain 404 in English and Vietnamese, 200 valid order, 400 malformed JSON, and failing/passing native method validation. Crucially, tests **assert the real HTTP status, media type, and contract fields**, not merely the `status` field inside the JSON.

Several tests rely on Spring 6.2 behavior (such as `HandlerMethodValidationException`), so do not copy the suite verbatim to Spring 5.x and expect it to compile. These files target Spring Boot 3.5.7 with Java 17+; Maven commands were not executed inside this lesson environment.

## 11. `ErrorResponse.Interceptor`: use only when supported by your version

Starting in Spring Framework **6.2**, the `ErrorResponse.Interceptor` interface allows intercepting a `ProblemDetail` error response right before rendering. In Spring MVC, `WebMvcConfigurer` provides the `addErrorResponseInterceptors(...)` hook.

**Optional** example:

~~~java
@Configuration
class ProblemMetadataConfiguration
        implements WebMvcConfigurer {

    @Override
    public void addErrorResponseInterceptors(
            List<ErrorResponse.Interceptor> interceptors) {

        interceptors.add((detail, errorResponse) -> {
            detail.setProperty("service", "orders-api");
        });
    }
}
~~~

This snippet requires importing `@Configuration`, `WebMvcConfigurer`, `List`, and `ErrorResponse`. It is **not** a required file in the demo and must not be used on Spring 6.0/6.1 where that interface/hook does not exist.

Applications can attach metadata such as a service name or sanitized correlation ID. An interceptor **does not directly receive `HttpServletRequest` in its signature**, so do not assume you can read headers or the current user directly from parameters; if request context is required, design a stack-safe propagation mechanism and test it separately.

An interceptor does not replace `@ExceptionHandler` for choosing HTTP status or mapping exceptions; its main purpose is enriching or adjusting `ProblemDetail` before rendering.

## 12. Differences between MVC and WebFlux

Both Spring MVC and Spring WebFlux provide `ProblemDetail`, `ErrorResponse`, and `ResponseEntityExceptionHandler`, but **do not share the same exception handler class import**.

| Concern | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| HTTP stack | Servlet | Reactive WebFlux |
| Base advice class | `org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler` | `org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler` |
| Request bean validation | Typically `MethodArgumentNotValidException` | Typically `WebExchangeBindException` |
| Native handler method validation | `HandlerMethodValidationException` (Spring 6.1+) | `HandlerMethodValidationException` (Spring 6.1+) |
| Boot switch | `spring.mvc.problemdetails.enabled` | `spring.webflux.problemdetails.enabled` |
| Request context | `WebRequest`/`HttpServletRequest` | `ServerWebExchange` |
| Testing | `MockMvc` | `WebTestClient` |

Conceptual example in WebFlux:

~~~java
@RestControllerAdvice
class ReactiveErrors
        extends org.springframework.web.reactive.result
                .method.annotation.ResponseEntityExceptionHandler {

    // Override protected handlers taking ServerWebExchange
    // per the Javadoc of the active Spring WebFlux version.
}
~~~

This is an **architectural snippet**, not a standalone runnable file and missing imports. In real code, keep the fully qualified class name on one line or import the exact class; the wrapped FQN above is only for readability in docs. Avoid copying Servlet MVC `WebRequest` signatures into WebFlux and trying to force compilation.

In WebFlux, streaming responses may already have sent headers/body when a late error occurs. Once an HTTP response is committed, you cannot easily switch the status to 400/500 and emit a full `ProblemDetail`. If an API requires the entire batch to be valid before responding, validate/buffer before streaming or use an event-level error protocol.

## 13. Spring 5.x compatibility: do not use APIs that do not exist yet

In Spring Framework 5.3 / Boot 2.x, Spring 6's `ProblemDetail` and `ErrorResponse` do not exist. **Do not fake those classes by changing packages or copying Spring 6 source code directly.**

A compatible option is a custom DTO with `ResponseEntity`:

~~~java
public record ApiError(
        int status,
        String code,
        String message) {
}

@RestControllerAdvice
class LegacyErrors {

    @ExceptionHandler(OrderMissingException.class)
    ResponseEntity<ApiError> notFound(
            OrderMissingException ex) {

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(new ApiError(
                        404,
                        "ORDER_NOT_FOUND",
                        "Requested order does not exist."));
    }
}
~~~

This snippet assumes relevant Spring MVC/JDK imports and an application-defined exception class. With Java 17, a `record` works in a compatible Spring 5.3 project; if your project still uses Java 8/11, replace it with a regular Java class with fields, getters, and a constructor. The key point is that **your custom JSON contract can mirror RFC 9457** even without the `ProblemDetail` class.

When upgrading to Spring 6, plan to:

1. Migrate namespaces from `javax.validation` → `jakarta.validation` and related Jakarta APIs.
2. Preserve stable error codes that clients already depend on.
3. Align response statuses/`type`/`instance`; do not silently force clients to rewrite parsers.
4. Adopt `ProblemDetail`/`ErrorResponse` where it adds real value.
5. Retest `Content-Type`, exception precedence, and `MessageSource`.

## 14. Security and error response contracts

`ProblemDetail` standardizes format, **it does not automatically make every error response secure**.

### 14.1. Avoid leaking internals

Never return:

- Full stack traces, JVM package/class names, database SQL, or JDBC URLs.
- Unsanitized `Exception.getMessage()` from third-party libraries.
- `FieldError.getRejectedValue()` for passwords, tokens, OTPs, or sensitive data.
- Authentication secrets, internal hostnames, connection strings, or API keys.
- Query strings in `instance` if URLs may contain tokens.

For debugging, return a safe correlation ID to the client and log details in internal logs/observability. Never turn every `Exception.class` into HTTP 400 just so clients can "parse it easily"; ensure 4xx and 5xx accurately reflect the error source.

### 14.2. Choose status codes by error category

| Error category | Common HTTP status | Notes |
| --- | --- | --- |
| JSON syntax / invalid payload | 400 | Input decoding failed |
| Bean Validation / missing parameter | 400 | Per framework/mapping, or 422 when intentionally contracted |
| Unauthenticated | 401 | Include required headers, e.g., `WWW-Authenticate` when appropriate |
| Unauthorized | 403 | Avoid leaking existence of resources the caller cannot view |
| Not found | 404 | May mask resource existence to prevent enumeration per security policy |
| State conflict | 409 | Domain conflict, optimistic locking depending on design |
| Payload too large | 413 | Upload/body limits |
| Server error | 500 | Never leak internal exceptions |

No RFC rule forces every Bean Validation error to be 422. `MethodArgumentNotValidException` defaults to HTTP 400; if you want 422, adopt it as an explicit policy rather than modifying headers and bodies inconsistently.

### 14.3. OpenAPI/SDK clients

To support clients well:

- Document the `application/problem+json` media type for endpoint errors, or define a shared schema in OpenAPI.
- Define schemas for extension fields like `code`/`errors`; do not treat them as default standard members.
- Keep `type` URIs stable. If a `type`'s meaning changes, consider versioning.
- Use stable machine-readable `code`s while localizing `title`/`detail`.
- Test that client libraries tolerate new extension keys added by the server.

## 15. Common pitfalls and diagnostics

| Symptom | Cause | Fix |
| --- | --- | --- |
| Cannot find `ProblemDetail` | Spring Framework 5.x or wrong dependency | Use a custom DTO or upgrade cleanly to Spring 6+ |
| Cannot find `addErrorResponseInterceptors` | Spring Framework below 6.2 | Use interceptors only on 6.2+ |
| Missing `HandlerMethodValidationException` | Spring below 6.1 | Check method validation for your stack/version |
| Body is still `{"timestamp":...,"error":...}` | Boot auto Problem Details not enabled or request fell through to `BasicErrorController` | Check properties, advice, and exception routing |
| Two advices handle built-in exceptions | Enabled Boot property while also extending `ResponseEntityExceptionHandler` | Set explicit order/scope or pick one strategy |
| Domain exception returns HTTP 500 | Missing mapping or handler in wrong stack | Add `@ExceptionHandler` or appropriate `ErrorResponseException` |
| JSON has `status=400` but HTTP is 200 | Returning a plain DTO instead of `ProblemDetail`/`ResponseEntity` with proper status | Keep HTTP status and body aligned |
| `errors` missing on some 400 responses | Not every 400 is Bean Validation (e.g., malformed JSON) | Standardize each failure category by policy |
| Raw exception message returned | Exposes internal system details | Use safe `detail` and separate internal logs |
| `instance` contains a token | Copying raw URL/query into body | Use non-sensitive path or tracking identifier |
| `typeMismatch` missing from Bean Validation list | Conversion failed before validation | Distinguish binder/Jackson/validator stages |
| Flaky tests due to error ordering | Violations lack deterministic ordering | Sort by `field`/`code` or assert order-independently |
| `MessageSource` does not translate | Key, base bundle, or locale mismatch | Check message codes and `Accept-Language` |
| Copied `WebRequest` signature into WebFlux | MVC and WebFlux use different base classes and signatures | Use the reactive package with `ServerWebExchange` |
| Client receives text/HTML instead of JSON | Content negotiation, exception handler, or container error page | Test content types by `Accept` header and status |
| Adding class-level `@Validated` to controller unexpectedly changes exception | Spring AOP method validation intervened | Use native Spring 6.1+ method validation when appropriate |
| Status 500 after stream already started | Response already committed | Validate before writing or use stream-level error events |
| HTTP 404 has a different format from other errors | Some errors routed through Boot error path instead of advice | Check routing, advice, properties, and contract tests |

### Version-aware upgrade checklist

1. Inspect the effective Spring Framework version via dependency tree / BOM.
2. Are `ProblemDetail` and `ErrorResponse` available? If not, use a compatible error DTO.
3. Is native controller method validation (`HandlerMethodValidationException`) available? If so, test direct constraints.
4. Is `ErrorResponse.Interceptor` available on 6.2+? Use it only if pre-render interception is genuinely needed.
5. Does the project use MVC or WebFlux? Pick the right `ResponseEntityExceptionHandler` package.
6. Does Boot auto-create a problem advice? Verify properties and advice ordering.
7. Does any custom exception handler swallow built-in handlers? Check `@Order` and `@ControllerAdvice` scopes.
8. Map input errors to 400/422 per contract; never hide server/postcondition errors as 400.
9. Test content negotiation and `application/problem+json`.
10. Verify localization, zero secret leakage, and backward compatibility of `code`/`type`/`errors` extensions.

## 16. Practice exercises

**Exercise 1.** Explain the difference between `ProblemDetail` and `ErrorResponse`. Why is a JSON body alone insufficient to represent the headers and status of an HTTP error response?

**Exercise 2.** Run the example with `customerName=""` and `quantity=0`. Why can the `errors` list contain two entries? Sort them by field/code to keep the JSON deterministic.

**Exercise 3.** Send a syntactically invalid JSON body. Why does that produce `HttpMessageNotReadableException` instead of `MethodArgumentNotValidException`? Describe how to test HTTP status and media type without depending on internal error text.

**Exercise 4.** Add a direct `@Min(1)` constraint on a query parameter. Compare behavior on Spring 6.0 vs. 6.1+; why should you not assume every validation exception shares the same class?

**Exercise 5.** Replace a domain 404 with an `ErrorResponseException` carrying a `ProblemDetail`; ensure both HTTP status and body status are 404. When is throwing an exception with HTTP semantics more convenient than custom domain advice?

**Exercise 6.** Enable `spring.mvc.problemdetails.enabled=true` in a project that already has an advice extending `ResponseEntityExceptionHandler`. Inspect resolution ordering and pick a strategy to avoid competing handlers.

**Exercise 7.** Create two translations for `problem.orderMissing`. Send `Accept-Language: vi` and `en`; why should `type` and `code` stay constant even when `detail` changes?

**Exercise 8.** Add a `traceId` extension to `ProblemDetail` without leaking JWTs, session IDs, or stack traces. Ensure the value is server-issued rather than blindly trusting user-supplied trace IDs.

**Exercise 9.** On Spring Framework 5.3, build an error DTO mirroring the five standard fields. Plan a migration to Spring 6 so API clients do not have to change error-handling logic immediately.

**Exercise 10.** Write contract tests for HTTP 400, 404, 409, and 500; verify internal errors never leak exception messages, JSON `status` matches HTTP status, and extension `errors` appear only when appropriate.

## Conclusion

Keep these three layers in mind:

~~~text
Domain / binding / validation exception
                  |
                  v
        ErrorResponse contract
        (status + headers + body)
                  |
                  v
        ProblemDetail (RFC 9457)
        type/title/status/detail/instance
        + extension properties
                  |
                  v
       HTTP 4xx/5xx + problem+json
~~~

`ProblemDetail` is the body model, `ErrorResponse` is the complete HTTP error contract, and `ResponseEntityExceptionHandler` is the tool for handling common web exceptions. **Version capabilities** dictate which APIs exist: Spring 5.x needs custom DTOs; 6.0 introduces Problem Details; 6.1 adds native controller method validation; 6.2 adds `ErrorResponse` interceptors. Pick the right MVC/WebFlux stack and Boot configuration, then test status, media type, content, and privacy to achieve stable error responses.

## References

- [Spring Framework 6.2 — MVC Error Responses and RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — WebFlux Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework 6.2 — ProblemDetail Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/http/ProblemDetail.html)
- [Spring Framework 6.2 — ErrorResponse Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/ErrorResponse.html)
- [Spring Framework 6.2 — ErrorResponseException Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/ErrorResponseException.html)
- [Spring Framework 6.2 — ErrorResponse.Interceptor (since 6.2)](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/ErrorResponse.Interceptor.html)
- [Spring Framework 6.2 — MVC ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — WebMvcConfigurer.addErrorResponseInterceptors](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/servlet/config/annotation/WebMvcConfigurer.html)
- [Spring Framework 6.2 — MVC Validation and HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
