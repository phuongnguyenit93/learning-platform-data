# Handling Missing Data, Type Mismatches, and Constraint Violations Separately in Spring MVC

## 1. Goal: not every HTTP 400 is the same

Suppose an API accepts a quantity via a query parameter and creates orders via JSON. The following requests can all receive HTTP **400 Bad Request**, yet their **root causes differ**:

```http
GET /api/query
```

The `quantity` query parameter is missing.

```http
GET /api/query?quantity=abc
```

`quantity` is present, but `abc` cannot be converted to `Integer`.

```http
GET /api/bounded?quantity=0
```

Type conversion succeeds, yet the value violates `@Min(1)`.

```http
POST /api/orders
Content-Type: application/json

{"customer":"Mai","units":0,"delivery":{"city":"Hanoi"}}
```

The JSON decodes into the DTO, yet `units=0` violates `@Min(1)`.

```http
POST /api/orders
Content-Type: application/json

{"customer":"Mai","units":{"unexpected":1},"delivery":{"city":"Hanoi"}}
```

The JSON is **syntactically valid**, yet `units` is an object rather than an integer; Jackson/message converter cannot construct the DTO matching the schema.

If an API returns the same generic payload:

```json
{"error":"Validation failed"}
```

for every case, the frontend does not know whether to ask for a missing field, fix a format, or adjust an out-of-range value. Logs and metrics also fail to separate request errors from server contract violations.

**Learning goal:** accurately classify **missing data**, **type/binding/decoding errors**, and **constraint violations**; pick the right exception handler, define stable error codes, preserve proper HTTP statuses, prevent raw input leakage, and test each scenario in Spring MVC.

Primary scope: **Spring MVC Servlet stack**, Java 17+, Spring Framework **6.1+/6.2.x**, Spring Boot 3.x, Jakarta Validation. Spring WebFlux defines its own exceptions, so do not copy the Servlet MVC list verbatim into a reactive stack.

## 2. Four stages where a request can fail

Conceptual flow:

```text
HTTP request
   |
   v
[1] Handler mapping and argument presence
   |   - are required query/header/part arguments present?
   |   - do HTTP method and Content-Type match?
   v
[2] Decoding and binding/conversion
   |   - "42" -> Integer
   |   - JSON -> DTO via Jackson
   |   - form fields -> DTO via WebDataBinder
   v
[3] Bean Validation / handler method validation
   |   - @NotBlank, @NotNull, @Min, @Size, @Valid
   |   - return-value constraints (server error)
   v
[4] Business / persistence / downstream
       - business rules, permissions, database, ...
```

Key insight: **if an earlier step fails, later steps may never run**. For instance, `quantity=abc` never produces an `int` for `@Min(1)` to inspect. A mistyped JSON field can be rejected before `@NotNull` or `@Min` on the DTO is evaluated.

Do not lump every failure caught before the controller runs under the generic label "validation error". Spring MVC distinguishes error sources and typically provides distinct exception types.

### 2.1. Error category routing table

| Input | Stage | Typical Spring MVC exception | Response category |
| --- | --- | --- | --- |
| Missing `@RequestParam(required=true)` | Presence/argument resolution | `MissingServletRequestParameterException` | `MISSING_PARAMETER` |
| Missing `@RequestHeader(required=true)` | Presence | `MissingRequestHeaderException` | `MISSING_HEADER` |
| Missing required multipart part | Presence | `MissingServletRequestPartException` | `MISSING_PART` |
| Empty required `@RequestBody` | Request body resolution | Typically `HttpMessageNotReadableException` | `BODY_UNREADABLE` or explicit `MISSING_BODY` |
| `quantity=abc` → `Integer` | Type conversion | `MethodArgumentTypeMismatchException` (subclass of `TypeMismatchException`) | `TYPE_MISMATCH` |
| Form `units=abc` → `Integer` | `WebDataBinder` | `FieldError` with `isBindingFailure()==true`; without `BindingResult`, typically wrapped in `MethodArgumentNotValidException` | `FIELD_BINDING_ERROR` |
| Malformed JSON syntax | `HttpMessageConverter`/Jackson | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| JSON field with wrong type, e.g., object → integer | Converter/Jackson | Typically `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| JSON missing DTO field + `@NotNull` | Post-decode validation | Typically `MethodArgumentNotValidException` | `CONSTRAINT_VIOLATION` |
| `@Valid` DTO fails `@NotBlank` | Argument validation | `MethodArgumentNotValidException` | `CONSTRAINT_VIOLATION` |
| Direct `@Min` on handler parameter (MVC 6.1+) | Handler method validation | `HandlerMethodValidationException` | `METHOD_CONSTRAINT_VIOLATION` |
| Constraint on handler return value fails | Return method validation | `HandlerMethodValidationException` | `RETURN_CONTRACT_VIOLATION`, usually 500 |
| `@Service @Validated` via Spring AOP proxy | Service method validation | By default usually `ConstraintViolationException` | Depends on error origin and API contract |

These are **typical** paths, not a guarantee that every framework version or configuration throws the exact same exception. `@ControllerAdvice`, class-level `@Validated`, `BindingResult`, custom argument resolvers, and converters can change the path.

## 3. Group 1 — Missing data errors

### 3.1. Missing required query parameter

```java
@GetMapping("/query")
public Map<String, Integer> query(
        @RequestParam("quantity") Integer quantity) {
    return Map.of("quantity", quantity);
}
```

`@RequestParam` defaults to `required=true`. Request:

```http
GET /api/query
```

omits `quantity`; Spring can throw `MissingServletRequestParameterException` **before the handler is invoked**. You can read `ex.getParameterName()` and `ex.getParameterType()` to identify the field, while avoiding exposing the full exception message or stack trace.

**Distinguish:**
- **Absent parameter:** `/api/query`.
- **Empty parameter:** `/api/query?quantity=`.
- **Wrong-type parameter:** `/api/query?quantity=abc`.

For `Integer`, an empty string may be converted to `null` and still trigger `MissingServletRequestParameterException` along the *missing after conversion* branch. The exception's `ex.isMissingAfterConversion()` flag helps diagnose this case. Do not claim `?quantity=` is always treated the same as `quantity=abc`.

### 3.2. `required=false` is not validation

```java
@GetMapping("/optional")
public String optional(
        @RequestParam(name = "quantity", required = false)
        Integer quantity) {
    return quantity == null ? "missing" : "present";
}
```

With `required=false`, the parameter may be null and the controller is responsible for handling it. However, if `quantity=abc` is sent, type conversion can still fail. Dropping the presence requirement does **not** disable type conversion.

You can use `Optional<Integer>` where appropriate. Avoid primitive `int` for an optional parameter when you need to represent "absent".

### 3.3. Missing HTTP request body

With:

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest body) {
    // ...
}
```

`@RequestBody` defaults to `required=true`. If the body is empty, MVC typically raises `HttpMessageNotReadableException` due to **required body missing**. This is not a DTO `@NotBlank` failure, because no DTO was created yet.

If your product needs a **dedicated error code for a missing body** without fragile parsing of exception message strings, you can deliberately write:

```java
@PostMapping("/orders")
public void create(
        @Valid @RequestBody(required = false) OrderRequest body) {

    if (body == null) {
        throw new MissingBodyException();
    }
    // ...
}
```

Then a completely absent request body reaches the controller with `body=null` and triggers the custom `MissingBodyException`. By contrast, a body that **is present but has invalid JSON** is still rejected by the converter before entering the handler.

**Note:** This is an API design choice for cleaner error classification, not a mandate that every endpoint use `required=false`. If you keep the default `required=true`, separating missing-body from JSON decoding errors reliably requires structured inspection of error metadata rather than matching English exception messages that can change across releases.

### 3.4. Missing field inside JSON vs. missing entire body

Suppose the DTO is:

```java
public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer units) {}
```

Body:

```json
{"customer":"Mai"}
```

The JSON is valid; Jackson constructs `OrderRequest` with `units=null` and Bean Validation catches `@NotNull`. This is typically **`MethodArgumentNotValidException`**, not `MissingServletRequestParameterException`, because `units` is a **request DTO property**, not an `@RequestParam`.

With primitive `int units` instead of `Integer`, a missing field can default to `0` under standard Jackson settings. If your API must distinguish "omitted" from "sent 0", use `Integer` with `@NotNull` and `@Min(1)`; if you also must distinguish an **absent JSON property** from explicit `null`, you need a dedicated Jackson/DTO or validation strategy rather than relying on `@NotNull` alone.

### 3.5. Missing header, part, and path

- Missing required `@RequestHeader("X-Client-Id")` → typically `MissingRequestHeaderException`.
- Missing required `@RequestPart("file")` → typically `MissingServletRequestPartException`.
- A multipart part **that is present but 0 bytes** is a separate check requiring `MultipartFile.isEmpty()`.
- For `@PathVariable`, a missing URL segment usually causes **the route not to match** (404), rather than throwing `MissingPathVariableException`. That exception can indicate an application mapping/template bug; do not assume every missing path variable is a 400 client input error.

In this lesson, the runnable demo focuses on query, body, JSON DTO, and form inputs because they cover all three target error groups cleanly.

## 4. Group 2 — Type mismatch and conversion errors

### 4.1. Query parameter type mismatch

```java
@GetMapping("/query")
public Map<String, Integer> query(
        @RequestParam("quantity") Integer quantity) {
    return Map.of("quantity", quantity);
}
```

When calling:

```http
GET /api/query?quantity=abc
```

Spring cannot convert String `"abc"` to `Integer`; the error is typically `MethodArgumentTypeMismatchException` (extending `TypeMismatchException`).

This differs from:
- `quantity` absent → missing parameter.
- `quantity=0` → conversion succeeds; with no constraint in this example, `0` is **not automatically an error**.
- `quantity=0` plus `@Min(1)` → conversion succeeds, yet the method constraint is violated.

In `ResponseEntityExceptionHandler`, the matching override hook is **`handleTypeMismatch(TypeMismatchException, ...)`**. Do not define a separate `@ExceptionHandler(MethodArgumentTypeMismatchException.class)` alongside the superclass if it collides with existing handlers; override the protected handler method to preserve consistent handling.

### 4.2. Syntactically invalid JSON

```http
POST /api/orders
Content-Type: application/json

{"customer":
```

Jackson cannot parse the body. `@Valid` on the DTO never runs; Spring MVC normally routes the failure through `HttpMessageNotReadableException`.

Do not return error code `CONSTRAINT_VIOLATION`, since type/field constraints were never the root cause.

### 4.3. Valid JSON that cannot deserialize into the DTO

```json
{
  "customer": "Mai",
  "units": {"unexpected": true},
  "delivery": {"city": "Hanoi"}
}
```

In Java `units` is declared as `Integer`, yet the client sent an object. The JSON is **syntactically valid** but **violates the API contract's data types**. The converter can throw `HttpMessageNotReadableException`, often wrapping a Jackson exception such as `MismatchedInputException`.

By inspecting Jackson's root cause and path, you *can* separate syntax errors from schema/type errors, though you must maintain that mapping carefully since cause chains and coercion rules evolve across releases. The demo picks a stable `BODY_UNREADABLE` code for both decoding failures while keeping them distinct from query type mismatches and Bean Validation.

**Never return the raw body or Jackson exception messages to clients:** exception messages can reveal internal Java types/paths or user data. Expose only safe messages and a correlation ID.

### 4.4. Form `@ModelAttribute` type mismatch

```java
public class OrderForm {
    private Integer units;
    public Integer getUnits() { return units; }
    public void setUnits(Integer units) { this.units = units; }
}
```

With form field `units=abc`, Spring's `WebDataBinder` typically records a `FieldError` with:
- `getField()` = `"units"`.
- `isBindingFailure()` = `true`.
- `getCode()` or `getCodes()` containing a `typeMismatch`-related code.

If the controller uses `@Valid @ModelAttribute` without an adjacent `BindingResult`, Spring typically throws `MethodArgumentNotValidException` including those field binding errors. Therefore, **never assume every `MethodArgumentNotValidException` contains only Jakarta constraint violations**.

To separate them, check `FieldError.isBindingFailure()`:
- `true` → binding failure, typically a type mismatch.
- `false` → validator failure, typically a constraint violation.

A single request can contain **both kinds of `FieldError`** on different fields. You can design an error response with a summary category and per-field issue types rather than forcing all errors under one label.

### 4.5. Converter configuration errors vs. client type mismatches

`ConversionNotSupportedException` can occur if the application lacks a required converter/`PropertyEditor` or does not support the conversion properly. That can be a **server configuration bug** and should by default be handled differently from `MethodArgumentTypeMismatchException` caused by a client sending `abc`.

Never write a catch-all for `TypeMismatchException` that always returns 400 if Spring passed status 500. In your handler override, **respect the `HttpStatusCode status`** supplied by the framework; classify internal codes by exception and context.

## 5. Group 3 — Jakarta Bean Validation violations

### 5.1. DTO argument validation

```java
public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer units) {}

@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest request) {
    // ...
}
```

With JSON:

```json
{"customer":"  ","units":0}
```

Jackson constructs the object. `@NotBlank` forbids whitespace-only strings and `@Min(1)` forbids `0`. Spring MVC argument validation can throw `MethodArgumentNotValidException` if the handler lacks an immediately following `BindingResult`.

**Differences between annotations:**
- `@NotNull` catches null, but allows blank strings.
- `@NotBlank` applies to `String`/`CharSequence`, catching null, empty, and whitespace-only values.
- `@Min(1)` checks numeric bounds and normally allows null; add `@NotNull` if required.
- `@Valid` cascades into nested objects/fields; it is not a direct `@Constraint`.
- `@Email` checks email format but does not require non-null on its own; pair with `@NotBlank` when required.

### 5.2. Nested DTOs and cascading

```java
public record Delivery(@NotBlank String city) {}

public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Min(1) Integer units,
        @NotNull @Valid Delivery delivery) {}
```

If `delivery=null`, `@NotNull` catches the missing object. If `delivery={"city":""}`, `@Valid` descends into it and `@NotBlank` on `city` reports an error at path `delivery.city`.

Do not add `@Valid` without `@NotNull` and expect null to be rejected. When the nested reference itself is null, cascading does not evaluate its inner fields.

### 5.3. Direct constraints on handlers since Spring MVC 6.1+

```java
@GetMapping("/bounded")
public Map<String, Integer> bounded(
        @RequestParam("quantity") @Min(1) int quantity) {
    return Map.of("quantity", quantity);
}
```

`@Min(1)` is placed directly on the method parameter. In Spring MVC 6.1+ (with a Bean Validation provider), Spring provides **built-in method validation**; `quantity=0` can trigger `HandlerMethodValidationException`, not `MethodArgumentNotValidException`.

This lesson **does not place class-level `@Validated` on the controller**. Per Spring documentation, class-level `@Validated` can route method validation through a Spring AOP proxy, changing the exception and handling compared to built-in MVC validation. To use the newer MVC mechanism, omit class-level `@Validated` on the controller.

### 5.4. Handler with both a `@Valid` DTO and a direct constraint

```java
@PostMapping("/mixed")
public void mixed(
        @RequestParam("batch") @Min(1) int batch,
        @Valid @RequestBody OrderRequest request) {
    // ...
}
```

Because `batch` carries a direct constraint, Spring MVC 6.1+ applies **method validation** to the handler, which can cover the `@Valid` DTO as well. DTO failures may then also surface inside `HandlerMethodValidationException`.

Consequently, an API `@RestControllerAdvice` should handle **both `MethodArgumentNotValidException` and `HandlerMethodValidationException`**. Handling only one can leave endpoints without the expected error format when controller signatures evolve.

### 5.5. Constraints on return values: server error

```java
@NotNull
@GetMapping("/reference")
public String reference() {
    return null;
}
```

This is an **intentionally broken endpoint for illustration**; never ship it in production. A failing return-value constraint is typically reported via `HandlerMethodValidationException` with status **500 Internal Server Error**. Never turn every constraint violation into 400, as this is a server-side postcondition failure.

## 6. Designing stable error codes

A simple schema for this lesson:

```json
{
  "code": "CONSTRAINT_VIOLATION",
  "fields": [
    {"field": "customer", "code": "NotBlank"},
    {"field": "units", "code": "Min"}
  ]
}
```

Principles:
1. **HTTP status** expresses the error class at the HTTP layer; bad input is usually 400, unsupported media type 415, server return invariant failure 500.
2. **`code`** is a stable, machine-readable identifier such as `MISSING_PARAMETER`, `TYPE_MISMATCH`, `BODY_UNREADABLE`, `FIELD_BINDING_ERROR`, `CONSTRAINT_VIOLATION`.
3. **`fields[]`** contains field names and error codes; sort them deterministically for stable tests.
4. **Display messages** can be localized via `MessageSource`, and must never be how the frontend classifies error types.
5. Never attach `getRejectedValue()`, request bodies, stack traces, or internal Java class names to public responses.
6. For traceability, add a correlation/request ID in logging/observability; never put secrets into metric labels.
7. When a request has multiple `FieldError`s, preserve **per-field granularity**; a single response can contain both binding failures and validation failures.

In production systems, consider **RFC 9457 Problem Details** via `ProblemDetail` or `ErrorResponse`. The examples below use concise JSON to focus on classification. Do not claim this JSON is Spring's default body.

## 7. Sample project: Java 17 + Spring Boot 3.5.6

The example implements four main endpoints:
- `GET /api/query`: missing parameter and query type-conversion errors.
- `GET /api/bounded`: `@Min` method constraint errors.
- `POST /api/orders`: distinguishes missing body, unreadable body, and DTO constraint violations.
- `POST /api/form`: handles type binding and constraint errors in `@ModelAttribute`.

A `@RestControllerAdvice` extending `ResponseEntityExceptionHandler` overrides the appropriate protected hooks while preserving Spring's chosen HTTP status.

**Why Boot 3.5.6?** It is a concrete existing Boot 3.5 release using Java 17+ and Spring Framework 6.2.x—without implying it is the latest release. The sample includes `spring-boot-starter-validation` to ensure the Jakarta provider is present in a standard setup.

### 7.1. Directory structure

```text
mvc-error-categories/
├── pom.xml
└── src/
    ├── main/java/demo/errors/
    │   ├── ErrorCategoryApplication.java
    │   ├── OrderRequest.java
    │   ├── OrderForm.java
    │   ├── MissingBodyException.java
    │   ├── ExampleController.java
    │   └── ApiExceptionHandler.java
    └── test/java/demo/errors/
        └── ErrorCategoryTest.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>mvc-error-categories</artifactId>
    <version>1.0-SNAPSHOT</version>

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
```

### 7.3. `ErrorCategoryApplication.java`

```java
package demo.errors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ErrorCategoryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ErrorCategoryApplication.class, args);
    }
}
```

### 7.4. `OrderRequest.java`

```java
package demo.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderRequest(
        @NotBlank(message = "customer.required")
        String customer,

        @NotNull(message = "units.required")
        @Min(value = 1, message = "units.min")
        Integer units,

        @NotNull(message = "delivery.required")
        @Valid
        Delivery delivery) {

    public record Delivery(
            @NotBlank(message = "delivery.city.required")
            String city) {
    }
}
```

`Integer units` distinguishes `null` from `0`. `@Min` does not catch null on its own, so `@NotNull` is added. `@NotNull @Valid Delivery` separates "missing nested object" from "invalid nested city".

### 7.5. `OrderForm.java`

```java
package demo.errors;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderForm {
    @NotBlank(message = "label.required")
    private String label;

    @NotNull(message = "units.required")
    @Min(value = 1, message = "units.min")
    private Integer units;

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public Integer getUnits() {
        return units;
    }

    public void setUnits(Integer units) {
        this.units = units;
    }
}
```

The form DTO uses setter binding so `FieldError.isBindingFailure()` can be observed clearly when `units=abc`.

### 7.6. `MissingBodyException.java`

```java
package demo.errors;

public class MissingBodyException extends RuntimeException {
    public MissingBodyException() {
        super("Required order body is absent");
    }
}
```

This custom exception implements the application's **missing-body classification policy**. It does not replace `HttpMessageNotReadableException` thrown by the JSON converter when a body is present with invalid structure.

### 7.7. `ExampleController.java`

```java
package demo.errors;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api")
public class ExampleController {

    // Intentionally omits class-level @Validated.

    @GetMapping("/query")
    public Map<String, Integer> query(
            @RequestParam("quantity") Integer quantity) {
        return Map.of("quantity", quantity);
    }

    @GetMapping("/bounded")
    public Map<String, Integer> bounded(
            @RequestParam("quantity") @Min(1) int quantity) {
        return Map.of("quantity", quantity);
    }

    @PostMapping(path = "/orders",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, Object> orders(
            @Valid @RequestBody(required = false)
            OrderRequest body) {

        if (body == null) {
            throw new MissingBodyException();
        }

        return Map.of(
                "customer", body.customer(),
                "units", body.units(),
                "city", body.delivery().city());
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> form(
            @Valid @ModelAttribute("orderForm")
            OrderForm form) {

        return Map.of(
                "label", form.getLabel(),
                "units", form.getUnits());
    }
}
```

**Explanation:**
- `query()` has no `@Min`, so `quantity=0` is valid input; only **presence and type** are checked during argument resolution.
- `bounded()` has a direct `@Min`, triggering MVC built-in method validation once the number has been converted successfully.
- `orders()` uses `@RequestBody(required=false)` to receive `null` when the body is absent, then explicitly throws `MissingBodyException`. Malformed bodies still fail inside Jackson.
- `orders()` uses `@Valid` to validate `OrderRequest` once constructed.
- `form()` omits `BindingResult`, so the framework routes binding/validation errors to the exception handler, which distinguishes `FieldError.isBindingFailure()`.
- Success responses use `Map.of` with fields already validated to be non-null.

### 7.8. `ApiExceptionHandler.java` — classifying errors by true origin

```java
package demo.errors;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> response(
            HttpStatusCode status,
            String code,
            List<Map<String, String>> fields) {

        Map<String, Object> payload =
                Map.of("code", code, "fields", fields);
        return new ResponseEntity<>(payload, status);
    }

    private static Map<String, String> issue(
            String field, String code) {
        return Map.of("field", field, "code", code);
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return response(status, "MISSING_PARAMETER",
                List.of(issue(ex.getParameterName(), "required")));
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Read query parameter name from the MVC exception when available.
        String field = ex instanceof MethodArgumentTypeMismatchException m
                ? m.getName() : "parameter";

        return response(status, "TYPE_MISMATCH",
                List.of(issue(field, "typeMismatch")));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Never leak raw JSON or Jackson messages to the client.
        return response(status, "BODY_UNREADABLE", List.of());
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        var fieldErrors = ex.getBindingResult().getFieldErrors();

        var issues = fieldErrors.stream()
                .map(e -> issue(
                        e.getField(),
                        e.isBindingFailure()
                                ? "typeMismatch"
                                : e.getCode() == null
                                        ? "invalid"
                                        : e.getCode()))
                .distinct()
                .sorted(Comparator.comparing(m -> m.get("field")))
                .toList();

        boolean bindingFailure = fieldErrors.stream()
                .anyMatch(FieldError::isBindingFailure);

        // A response may contain both binding and validation issues.
        String code = bindingFailure
                ? "FIELD_BINDING_ERROR"
                : "CONSTRAINT_VIOLATION";

        return response(status, code, issues);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        String code = ex.isForReturnValue()
                ? "RETURN_CONTRACT_VIOLATION"
                : "METHOD_CONSTRAINT_VIOLATION";

        // Preserve framework status: input is typically 400, return typically 500.
        return response(status, code, List.of());
    }

    @ExceptionHandler(MissingBodyException.class)
    public ResponseEntity<Object> missingBody(
            MissingBodyException ex) {
        return response(HttpStatus.BAD_REQUEST,
                "MISSING_BODY", List.of());
    }
}
```

**Why extend `ResponseEntityExceptionHandler`?**

Spring already provides an MVC exception handler with protected override hooks. If a subclass adds a new `@ExceptionHandler` for an exception already handled by the superclass, mapping conflicts can occur. Overriding `handleTypeMismatch`, `handleHttpMessageNotReadable`, `handleMethodArgumentNotValid`, `handleHandlerMethodValidationException`, etc., keeps Spring's flow intact.

**Why take `status` from the `status` parameter?**

A normal `TypeMismatchException` from a client sending `abc` may be 400, whereas an unsupported conversion from server misconfiguration can carry a different status. Return-value method validation can be 500. Preserving `status` prevents accidentally turning backend errors into client errors.

**Why check `FieldError.isBindingFailure()`?**

For forms, `MethodArgumentNotValidException` can contain both conversion and constraint failures. Inspecting each field before assigning a summary category distinguishes them. In production, add a per-issue category (such as `binding`/`constraint`) when a response can hold multiple error types; the example keeps the payload compact for testing.

## 8. End-to-end testing with `MockMvc`

`MockMvc` sends requests through Spring MVC argument resolvers, message converters, data binders, Jakarta Validator, and exception resolvers without opening a real HTTP port.

### 8.1. `ErrorCategoryTest.java`

```java
package demo.errors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ErrorCategoryTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID_JSON = """
        {
          "customer":"Mai",
          "units":2,
          "delivery":{"city":"Hanoi"}
        }
        """;

    @Test
    void missingRequiredQueryParameterHasOwnCode() throws Exception {
        mvc.perform(get("/api/query"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("quantity"));
    }

    @Test
    void nonNumericQueryParameterHasTypeCode() throws Exception {
        mvc.perform(get("/api/query").param("quantity", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("quantity"));
    }

    @Test
    void zeroIsNotInvalidWithoutConstraint() throws Exception {
        mvc.perform(get("/api/query").param("quantity", "0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.quantity").value(0));
    }

    @Test
    void directMinConstraintHasSeparateCode() throws Exception {
        mvc.perform(get("/api/bounded").param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_CONSTRAINT_VIOLATION"));
    }

    @Test
    void wrongTypeStillFailsBeforeMinConstraint() throws Exception {
        mvc.perform(get("/api/bounded").param("quantity", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"));
    }

    @Test
    void missingBodyHasExplicitCode() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("MISSING_BODY"));
    }

    @Test
    void malformedJsonIsNotBeanValidation() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"customer\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BODY_UNREADABLE"));
    }

    @Test
    void wrongJsonFieldTypeIsBodyUnreadable() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "units":{"unexpected":true},
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("BODY_UNREADABLE"));
    }

    @Test
    void missingDtoFieldIsConstraintViolation() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].field").value("units"))
                .andExpect(jsonPath("$.fields[0].code").value("NotNull"));
    }

    @Test
    void zeroDtoValueViolatesMin() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "units":0,
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].code").value("Min"));
    }

    @Test
    void blankCustomerViolatesNotBlank() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"  ",
                              "units":2,
                              "delivery":{"city":"Hanoi"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field").value("customer"))
                .andExpect(jsonPath("$.fields[0].code").value("NotBlank"));
    }

    @Test
    void nestedDtoValidationHasFieldPath() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "customer":"Mai",
                              "units":2,
                              "delivery":{"city":""}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields[0].field")
                        .value("delivery.city"));
    }

    @Test
    void validOrderSucceeds() throws Exception {
        mvc.perform(post("/api/orders")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.customer").value("Mai"))
                .andExpect(jsonPath("$.units").value(2));
    }

    @Test
    void formFieldWrongTypeIsBindingError() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "Box")
                        .param("units", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("FIELD_BINDING_ERROR"))
                .andExpect(jsonPath("$.fields[0].field")
                        .value("units"));
    }

    @Test
    void formConstraintHasDifferentCode() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "")
                        .param("units", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].code")
                        .value("NotBlank"));
    }

    @Test
    void formMissingFieldIsNotNullViolation() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "Box"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.fields[0].field").value("units"));
    }

    @Test
    void validFormSucceeds() throws Exception {
        mvc.perform(post("/api/form")
                        .contentType(
                                MediaType.APPLICATION_FORM_URLENCODED)
                        .param("label", "Box")
                        .param("units", "3"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.units").value(3));
    }
}
```

**All 17 test cases are expected to pass** with Java 17, Maven, and matching dependency versions. This is an illustrative test suite matching expected behavior, **not evidence of having been run in a live environment**.

Each test triggers only a single field error when asserting `fields[0]`, avoiding ordering assumptions across multiple violations. When real systems emit multiple `FieldError`s, assert sets/paths and error codes instead of assuming provider ordering.

### 8.2. Running Maven

From the `mvc-error-categories` directory:

```bash
mvn test
```

Run the application:

```bash
mvn spring-boot:run
```

Maven/Surefire outputs results according to machine settings. Do not depend on exact Spring Boot stdout logs; JUnit/`MockMvc` assertions are what matter.

## 9. Testing with curl and reading the responses

### 9.1. Missing query parameter

```bash
curl -i 'http://localhost:8080/api/query'
```

Expected HTTP 400:

```json
{
  "code":"MISSING_PARAMETER",
  "fields":[{"field":"quantity","code":"required"}]
}
```

### 9.2. Query type mismatch

```bash
curl -i 'http://localhost:8080/api/query?quantity=abc'
```

Expected HTTP 400:

```json
{
  "code":"TYPE_MISMATCH",
  "fields":[{"field":"quantity","code":"typeMismatch"}]
}
```

### 9.3. Direct method constraint violation

```bash
curl -i 'http://localhost:8080/api/bounded?quantity=0'
```

Expected HTTP 400:

```json
{
  "code":"METHOD_CONSTRAINT_VIOLATION",
  "fields":[]
}
```

### 9.4. Missing JSON body

```bash
curl -i -X POST \
  'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json'
```

Expected HTTP 400 with code `MISSING_BODY` because the controller explicitly throws the custom exception.

### 9.5. Wrong JSON field type

```bash
curl -i -X POST \
  'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Mai","units":{"x":1},"delivery":{"city":"Hanoi"}}'
```

Expected HTTP 400 with code `BODY_UNREADABLE`. This is **not** an `@Min` failure because the converter could not construct `Integer units`.

### 9.6. Valid JSON violating a constraint

```bash
curl -i -X POST \
  'http://localhost:8080/api/orders' \
  -H 'Content-Type: application/json' \
  -d '{"customer":"Mai","units":0,"delivery":{"city":"Hanoi"}}'
```

Expected HTTP 400 with code `CONSTRAINT_VIOLATION` and field code `Min` for `units`.

The JSON responses in this section are produced by the **demo's `ApiExceptionHandler`**; they are not mandatory Spring MVC defaults. JSON key order is not part of the contract.

## 10. `BindingResult`: handling errors locally without throwing exceptions

In another controller, if you want to handle form errors directly:

```java
@PostMapping("/form-local")
public ResponseEntity<?> local(
        @Valid @ModelAttribute("orderForm") OrderForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        boolean wrongType = errors.getFieldErrors().stream()
                .anyMatch(FieldError::isBindingFailure);

        return ResponseEntity.badRequest().body(
                Map.of("code", wrongType
                        ? "FIELD_BINDING_ERROR"
                        : "CONSTRAINT_VIOLATION"));
    }

    return ResponseEntity.ok().build();
}
```

This is an **illustrative fragment**, not included in the Section 7 project. Import `BindingResult`, `FieldError`, `Map`, and the corresponding Spring annotations.

`BindingResult` must be placed **immediately after the bound/validated argument**. Without `BindingResult` in the right spot, the framework typically throws an exception. With it present, the controller can inspect `errors.getFieldErrors()`, `getGlobalErrors()`, and `getSuppressedFields()` and build a custom response.

**Warning:** If the method also has **direct method constraints**, Spring MVC 6.1+ may use `HandlerMethodValidationException`; not all errors are necessarily gathered into a single `BindingResult`. Adding a direct `@Min` to another parameter can change the handler's validation mechanism.

## 11. Better handling when a request has multiple simultaneous errors

For example, a form submits:

```text
label=
units=abc
```

One field fails a constraint, while the other has the wrong type. Returning only a single top-level code `FIELD_BINDING_ERROR` may hide that `label` also needs fixing. A richer response includes a per-field category:

```json
{
  "code":"INPUT_INVALID",
  "fields":[
    {"field":"label","category":"constraint","code":"NotBlank"},
    {"field":"units","category":"binding","code":"typeMismatch"}
  ]
}
```

This is a **proposed design**, not the response of the Section 7 project. You can model it as:

```java
public record Issue(
        String field,
        String category,
        String code) {}
```

and map `FieldError` as:
- `isBindingFailure()==true` → `category="binding"`.
- Otherwise → `category="constraint"`.
- Global `ObjectError` without a specific field → `category="object"`.

Do not grab the final exception message and parse text to determine the error category. Use the metadata provided by Spring and keep event logs/metrics grouped by stable categories.

## 12. `HandlerMethodValidationException` is structured by parameter

In Spring MVC 6.1+, `HandlerMethodValidationException` provides:
- `getAllValidationResults()`, returning `ParameterValidationResult` instances.
- `isForReturnValue()`, distinguishing parameter errors from return-value errors.
- `getStatusCode()`, reflecting the appropriate status.
- `visitResults(...)`, a visitor dispatching by handler argument annotation such as `@RequestParam`, `@RequestHeader`, `@ModelAttribute`.

To return richer errors, iterate `ParameterValidationResult.getResolvableErrors()` or use the visitor to separate direct query-parameter errors from nested object errors. Never use a regex on exception messages to guess field names.

Conceptual example:

```java
for (var parameterResult : exception.getAllValidationResults()) {
    var parameter = parameterResult.getMethodParameter();

    for (var error : parameterResult.getResolvableErrors()) {
        // Map MethodParameter + MessageSourceResolvable
        // to the API's stable code/path.
    }
}
```

This is a **fragment** assuming `exception` of type `HandlerMethodValidationException`; it is not a complete snippet from the runnable project. Choose an appropriate error schema, locale, and message source when implementing. Never treat return-value violations as user input errors, and never expose internal return values.

## 13. Errors from service method validation and business validation

### 13.1. `@Validated` on a Spring service via proxy

```java
@Service
@Validated
public class InventoryService {

    public void reserve(@Min(1) int count) {
        // ...
    }
}
```

If the bean is managed by method-validation AOP and called through a proxy, input `count=0` typically triggers `jakarta.validation.ConstraintViolationException`. This is not the same pipeline as MVC handler `HandlerMethodValidationException`, and this exception **is not automatically 400**.

If the service is invoked by a scheduler or message listener without an HTTP client, errors require a different policy. If it is an internal bug (e.g., a service returns a contract-violating value), 500 may apply; if directly caused by bad client input at a verified boundary, you can map it to an input validation error.

### 13.2. Business rules vs. Jakarta annotation constraints

An order with `units=3` can exceed available stock even though `@Min(1)` passes completely. This is a **business conflict** or domain rule, not type conversion. Depending on your API, choose 409 Conflict, 422 Unprocessable Content, or another business code, consistent with your contract and HTTP semantics.

Do not classify authorization failures or database connectivity errors as `CONSTRAINT_VIOLATION` simply because "validation" appears in a log.

## 14. Standardizing with RFC 9457 Problem Details

If an API prefers not to invent a custom JSON envelope from scratch, Spring Framework provides `ProblemDetail` and `ErrorResponse` supporting RFC 9457.

Conceptual example:

```java
ProblemDetail problem =
        ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
problem.setTitle("Invalid input");
problem.setDetail("One or more fields are invalid");
problem.setProperty("code", "CONSTRAINT_VIOLATION");
problem.setProperty("fields", List.of("customer", "units"));
```

This is a **fragment** requiring imports. Spring MVC can serialize `ProblemDetail` as `application/problem+json` with standard fields `type`, `title`, `status`, `detail`, `instance`, and extension properties.

Using RFC 9457 lets tools and clients interpret standard HTTP statuses while keeping application-specific error codes. Never put raw exception messages that might leak sensitive details into a shared `detail` field. For multilingual responses, resolve `detail`/`title` via `MessageSource` and `Locale`, while keeping `code` constant across languages.

When a subclass already extends `ResponseEntityExceptionHandler` as in the main project, overriding protected handler methods is safer than adding competing `@ExceptionHandler` methods that cause ambiguous mappings.

## 15. Security, privacy, and logging concerns

### 15.1. Never blindly echo rejected values

`FieldError.getRejectedValue()` and `ConstraintViolation.getInvalidValue()` may hold passwords, tokens, document IDs, or personal records. Logging entire objects or form bodies can expose personal data.

In responses, prefer:
- Public field names defined by the API contract.
- Error codes and valid bounds.
- Generic localized messages containing no raw input values.
- Request ID / correlation ID so operators can inspect logs.

### 15.2. Log server-side separately; never send stack traces to clients

For `HttpMessageNotReadableException`, emit structured safe logs with endpoint, error category, request ID, content-type, and source exception class when needed. Never log raw bodies by default, and never put stack traces in HTTP responses.

You can track categorized metrics:
- `missing_parameter`
- `body_unreadable`
- `type_mismatch`
- `binding_failure`
- `constraint_violation`
- `handler_method_validation`

Keep metric label cardinality low; never use raw request values or dynamic exception messages as labels.

### 15.3. Do not overuse 422

HTTP 400 fits malformed/missing/constraint request errors under Spring defaults. 422 Unprocessable Content can fit a specific API contract when the payload has valid types and syntax yet fails business rules. Still, **do not turn every `MethodArgumentNotValidException` into 422**, especially when it includes binding failures.

If you adopt 422, define a clear boundary against 400 and test it consistently across endpoints.

## 16. Quick debugging checklist

1. **Inspect the actual request:** HTTP method, URL, query string, `Content-Type`, and whether a body is present.
2. **Locate where the field lives:** `@RequestParam`/`@RequestHeader`, JSON `@RequestBody`, form `@ModelAttribute`, or multipart `@RequestPart`.
3. **Missing before binding?** Is a required parameter/part/header absent?
4. **Did the input convert to the Java type?** `abc` failing to become `Integer` is a type mismatch, not `@Min`.
5. **Did JSON parse into the DTO?** Malformed JSON and JSON type mismatches belong to the message converter.
6. **Is the DTO property null because it was omitted?** Add `@NotNull` if the field is required.
7. **Nullable wrapper or primitive?** `Integer` distinguishes null from 0; `int` typically does not.
8. **Are `@Valid`/`@Validated` in the right place?** Field annotations alone do not guarantee argument validation runs.
9. **Are there direct method constraints?** `@Min` on a handler parameter can switch the exception to `HandlerMethodValidationException`.
10. **Is there class-level `@Validated` on the controller?** It can route execution through an AOP proxy outside built-in MVC validation.
11. **With `@ModelAttribute`, check `FieldError.isBindingFailure()`** so type mismatches are not confused with constraints.
12. **With `BindingResult`, is it immediately after the argument?** Otherwise the controller may never be invoked.
13. **With `ResponseEntityExceptionHandler`, use protected overrides matching your Spring version's signatures.**
14. **Never hardcode every exception to 400:** especially conversion config errors and return-contract errors.
15. **Write tests per root cause**, not just checking HTTP status.
16. **Verify messages/codes per locale** if responses are localized.
17. **Never expose raw input or stack traces**; use stable error codes and request IDs.

## 17. Common misconceptions

| Misconception | Reality |
| --- | --- |
| "A missing JSON field is a missing `@RequestParam`" | JSON properties are deserialized into a DTO and checked via `@NotNull`/`@NotBlank`; typically Bean Validation |
| "A wrong JSON field type is always `MethodArgumentTypeMismatchException`" | JSON goes through Jackson/`HttpMessageConverter` → `HttpMessageNotReadableException` |
| "`MethodArgumentNotValidException` only holds constraint errors" | Form binders can place type mismatches into `BindingResult` |
| "`@Min` also validates string `abc`" | The value must convert to the target type before `@Min` runs |
| "`@Valid` automatically forbids null on all fields" | `@Valid` cascades; fields need `@NotNull`/appropriate constraints |
| "`@Min` forbids null by itself" | `@Min` normally ignores null; pair with `@NotNull` |
| "Every `@Validated` failure is MVC method validation" | `@Service @Validated` usually runs via AOP proxy with different exceptions |
| "An HTTP 400 tells you the exact failure kind" | Missing data, type mismatch, decoding, binding, and validation can all return 400 |
| "`BindingResult` at the end of a method catches everything" | It must immediately follow the argument and has a specific scope |
| "Catching `TypeMismatchException` always means returning 400" | Some conversion errors stem from server config; respect `status` |
| "A failing return constraint is also a client bad request" | It is a server postcondition violation, typically 500 |
| "`MissingPathVariableException` always means the URL missed a segment" | Missing URL segments usually fail route matching; this exception can indicate a mapping bug |
| "Returning `ex.getMessage()` helps clients debug" | It can leak internal details/PII; return stable codes and log safely |
| "Any `@RestControllerAdvice` can define duplicate handlers" | It can cause ambiguous mappings; when extending `ResponseEntityExceptionHandler`, override protected methods |
| "Always use 422 for Bean Validation" | Spring defaults to 400; adopt a clear classification contract and test it |

## 18. Practice exercises

1. Change `@RequestParam("quantity") Integer` to `@RequestParam(required=false) Integer` and test missing vs. `quantity=abc`.
2. Send `?quantity=` to observe `MissingServletRequestParameterException.isMissingAfterConversion()` when conversion yields null.
3. Change `Integer units` to `int units` in the record, send JSON omitting `units`, and explain why the error behavior changes.
4. Remove `@NotNull` from `units` while keeping `@Min(1)`. Why can JSON omitting the field slip past?
5. Send `{"units":{"unexpected":true}}` and then `{"units":0}`, comparing the decoder error and validator error.
6. Add `@Valid` on nested `delivery`, then remove `@NotNull` and `@Valid` one at a time to observe each annotation's role.
7. Add `@Size(min=3)` on `customer`; test a single field failing two constraints simultaneously and inspect error ordering.
8. Test `@ModelAttribute OrderForm` with `units=abc` and `label=""`; inspect `FieldError.isBindingFailure()` on each field.
9. Replace the single top-level error code with a list of issues carrying `category=type/binding/constraint` per field.
10. Add a direct `@Min` on another parameter of a controller receiving a `@Valid` DTO; observe whether the exception switches to `HandlerMethodValidationException`.
11. Create an intentionally failing return-value constraint in a separate test to verify the 500 response and `RETURN_CONTRACT_VIOLATION`.
12. Add a required `@RequestHeader` and a missing multipart part; write dedicated exception mappings for each.
13. Test well-typed form data that violates a custom Spring `Validator`; verify the resulting `FieldError` type.
14. Implement an error DTO or `ProblemDetail` carrying `instance`/request ID without exposing raw rejected values.
15. Write tests for both a Vietnamese locale and an English locale while keeping machine-readable `code` unchanged.

**Remember:** "Missing data", "wrong type", and "constraint violation" are **three distinct failure kinds at different stages**. Classify them using annotation placement, argument resolvers, converters, `BindingResult`, and exception types—not by guessing from message text. Spring MVC provides `ResponseEntityExceptionHandler` to standardize errors while preserving HTTP status, especially separating client input failures from server return-contract failures.

## 19. Official references

- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — REST error responses and RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — FieldError JavaDoc / isBindingFailure](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — MVC Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Framework 6.2 — RequestBody and BindingResult](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — ModelAttribute binding](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — HandlerMethodValidationException JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Boot 3.5 — Testing Spring MVC via MockMvc](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)