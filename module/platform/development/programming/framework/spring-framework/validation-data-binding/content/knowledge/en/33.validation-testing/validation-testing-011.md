# MockMvc for Binding Errors, Validation, and Response Contracts in Spring MVC

## 1. Goal: test the exact error cause, not just HTTP 400

A Spring MVC API can return **400 Bad Request** for many very different requests:

```http
GET /api/count
```

Missing a required query parameter.

```http
GET /api/count?count=abc
```

Query parameter present, but the String cannot convert to `Integer`.

```http
GET /api/page?page=0
```

Conversion succeeds, yet `@Min(1)` directly on the handler parameter is violated.

```http
POST /api/items
Content-Type: application/json

{"name":" ","quantity":0,"delivery":{"city":""}}
```

JSON decodes successfully, yet fields violate Jakarta Bean Validation.

```http
POST /api/items
Content-Type: application/json

{"name":"Book","quantity":{"unexpected":1},"delivery":{"city":"Hue"}}
```

JSON is syntactically valid, yet an object **cannot be converted** to `Integer quantity`; this is a JSON decode/conversion failure, not a `@Min` error.

```http
POST /api/form
Content-Type: application/x-www-form-urlencoded

name=Book&quantity=abc
```

`@ModelAttribute` can contain a `FieldError` caused by a **binding failure**, rather than a constraint violation.

If you only write:

```java
mvc.perform(post("/api/items").content(invalidJson))
   .andExpect(status().isBadRequest());
```

the test still passes even if the API accidentally switches from `CONSTRAINT_VIOLATION` to `BODY_UNREADABLE`, leaks a stack trace to the client, drops field codes, or alters the error format the frontend relies on. **HTTP status is only part of the response contract.**

This lesson focuses on **testing** with Spring Test `MockMvc`:
1. Triggering **argument presence**, **type conversion**, **data binding**, **Bean Validation**, and **handler method validation** branches accurately.
2. Distinguishing `MethodArgumentNotValidException` from `HandlerMethodValidationException` and `HttpMessageNotReadableException`.
3. Designing a stable JSON error contract with `code`, `issues[]`, and per-field categories.
4. Using `ResponseEntityExceptionHandler` to centralize error normalization.
5. Using `MockMvc` to verify status, content type, structure, error codes, field paths, ordering, forbidden content, and success responses.
6. Avoiding brittle tests tied to internal Spring messages or random constraint violation ordering.
7. Understanding the scope of `@WebMvcTest`, `@SpringBootTest`, `MockMvcBuilders.standaloneSetup`, and when real server tests are needed.

**Context:** Spring Framework 6.2.x, Spring Boot 3.5.6, Java 17+, Jakarta Validation 3.x, Spring MVC Servlet stack. APIs/annotations can differ between Spring 5, 6, and 7; do not copy imports or exception routing directly to WebFlux.

## 2. Classification table to master before writing tests

| Request / contract | Stage of failure | Typical Spring MVC exception | Suggested API code |
| --- | --- | --- | --- |
| Missing `@RequestParam(required=true)` | Argument resolution | `MissingServletRequestParameterException` | `MISSING_PARAMETER` |
| `count=abc` for `Integer` | Type conversion | `MethodArgumentTypeMismatchException` | `TYPE_MISMATCH` |
| Empty JSON body for `@RequestBody(required=true)` | Message reading | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| Malformed JSON, e.g., missing `}` | JSON parser | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| JSON field is object, Java field is Integer | Jackson deserialization | `HttpMessageNotReadableException` | `BODY_UNREADABLE` |
| `@Valid @RequestBody` DTO fails `@NotBlank` | Argument Bean Validation | `MethodArgumentNotValidException` | `VALIDATION_ERROR` |
| `@Valid @ModelAttribute` form has `quantity=abc` | DataBinder | `FieldError.isBindingFailure()==true`, possibly inside `MethodArgumentNotValidException` | `BINDING_ERROR` |
| `@Valid @ModelAttribute` form has `name=""` | Bean Validation on binder target | `FieldError.isBindingFailure()==false` | `VALIDATION_ERROR` |
| `@Min(1)` directly on `@RequestParam` | MVC method validation (6.1+) | `HandlerMethodValidationException` | `METHOD_VALIDATION_ERROR` |
| Constraint on handler return value | MVC method validation (6.1+) | `HandlerMethodValidationException`, typically status 500 | `SERVER_CONTRACT_VIOLATION` |

**Note:** These are typical behaviors when a Bean Validation provider and Spring MVC 6.1+ are present. Exact behavior also depends on handler signatures, `BindingResult`, class-level `@Validated`, conversion services, custom argument resolvers, exception advice, and app configuration. Thus **integration tests** themselves are the source of truth for your project's real contract.

### 2.1. Binding errors are not constraint errors

With a form:

```java
public class ItemForm {
    @NotBlank String name;
    @NotNull @Min(1) Integer quantity;
}
```

Request `quantity=abc`:
- `"abc"` cannot convert to `Integer`.
- The Spring binder records a `typeMismatch` error (with `FieldError.isBindingFailure()==true`).
- A `@NotNull` Bean Validation error may also appear if the bound value remains null, depending on how the binder/validator handles already-failed fields; **do not guess an exact absolute FieldError count**.
- Tests should assert **presence** of the right binding error rather than locking every case to an exact count of one error.

Request `quantity=0`:
- Conversion succeeds.
- `@Min(1)` detects an invalid value.
- This is a **constraint violation**, not a conversion error.

### 2.2. One exception class can carry multiple error kinds

`MethodArgumentNotValidException` does not always mean only Jakarta constraints: for `@ModelAttribute`, `BindingResult` can hold **type mismatch** or other binding failures.

Therefore, when mapping errors to JSON, classify **each `FieldError`** via `isBindingFailure()`, not solely by the exception class.

### 2.3. Argument validation differs from handler method validation

Spring MVC 6.1+ distinguishes:
- `@Valid @RequestBody ItemRequest` with no direct constraint on other method parameters: typically **argument validation**, throwing `MethodArgumentNotValidException` when no `Errors/BindingResult` immediately follows.
- `@RequestParam("page") @Min(1) int page`: has a **direct method constraint**, using built-in handler method validation, which can throw `HandlerMethodValidationException`.
- If a handler has both direct `@Min` and `@Valid` on a DTO, method validation can cover cascaded DTO constraints as well.

A resilient advice should therefore handle **both exception types**. Do not place class-level `@Validated` on a controller just to enable `@Min`: Spring Framework notes that class-level `@Validated` can switch to proxy-based AOP method validation, a different mechanism from MVC 6.1+.

## 3. Define the response contract before testing

We use an illustrative response shape, **not a mandatory Spring format**:

```json
{
  "code": "VALIDATION_ERROR",
  "issues": [
    {
      "field": "name",
      "code": "NotBlank",
      "category": "constraint"
    },
    {
      "field": "quantity",
      "code": "Min",
      "category": "constraint"
    }
  ]
}
```

Where:
- `code`: top-level request category, a stable **machine-readable string**.
- `issues[]`: structured list of issues so the frontend knows the field and reason.
- `field`: API-defined property path or parameter name.
- `issues[].code`: stable project error code, e.g., `NotBlank`, `Min`, `typeMismatch`, `required`, `invalid`.
- `category`: `presence`, `binding`, or `constraint`.
- `issues` is **sorted by field then code** with duplicates removed so tests never depend on provider ordering.

Missing query parameter example:

```json
{
  "code": "MISSING_PARAMETER",
  "issues": [
    {
      "field": "count",
      "code": "required",
      "category": "presence"
    }
  ]
}
```

Unreadable JSON body example:

```json
{
  "code": "BODY_UNREADABLE",
  "issues": []
}
```

Form binding error example:

```json
{
  "code": "BINDING_ERROR",
  "issues": [
    {
      "field": "quantity",
      "code": "typeMismatch",
      "category": "binding"
    }
  ]
}
```

Production apps may choose **RFC 9457 Problem Details** (`ProblemDetail`), adding `type`, `title`, `status`, `detail`, `instance`, and extension codes. Whichever schema you choose, test the **published schema**, never copying Spring exception text that can change across versions or locales.

### 3.1. Do not treat display `message` as the API code

An English sentence like `"must be greater than or equal to 1"` is **display text**; a Vietnamese-locale user may receive a different sentence. Avoid asserting that Hibernate Validator's default message matches character-for-character when the contract guarantees **field + code + status**.

Instead:
- Assert `code="Min"` stably across the project boundary.
- If the app explicitly commits to a localized message contract, create resource bundles and test locales separately.
- Never turn raw `ex.getMessage()` text into an error code.

### 3.2. Never return sensitive data

`FieldError.getRejectedValue()` can contain passwords, tokens, emails, or request text. `HttpMessageNotReadableException` can contain Jackson paths or implementation details. Never expose these values, stack traces, method signatures, or Java exception class names in public JSON.

Security tests should verify raw rejected values are never echoed in the response (except where a business contract explicitly permits displaying non-sensitive text).

## 4. What can and cannot MockMvc do?

`MockMvc` sends simulated requests/responses through the Spring MVC infrastructure:
- Handler mapping and argument resolution.
- `HttpMessageConverter` (e.g., Jackson JSON).
- `ConversionService`/`WebDataBinder` for query/form data.
- Bean Validation, `@ControllerAdvice`, and exception resolvers.
- Response serialization, status, headers, and content type.

`MockMvc` **does not need to open a TCP port**; with `@SpringBootTest(webEnvironment=MOCK)` and `@AutoConfigureMockMvc`, it typically uses a mock Servlet environment.

It **does not replace** real servlet-container tests for:
- Networking/proxies, TLS, HTTP/2.
- Container-enforced request/body size limits.
- Real error-page dispatching, compression, or transfer encoding.
- Deployment-specific security/network filters absent from the test context.

Do not call MockMvc "end-to-end over the network". It is an **MVC-layer integration test**, reliable enough to verify binders, validation, and handler advice when the context is configured properly.

### 4.1. Three common setups

| Approach | Initialization | Best suited for |
| --- | --- | --- |
| `@WebMvcTest(MyController.class)` | MVC slice, MockMvc auto-configured | Testing controllers/advice without loading repositories/business beans |
| `@SpringBootTest + @AutoConfigureMockMvc` | Near-production ApplicationContext, no TCP port by default | Testing interactions across MVC config, validators, converters, and advice |
| `MockMvcBuilders.standaloneSetup(...)` | Direct controller setup; dependencies/resolvers configured manually | Narrow unit-like MVC tests requiring tight control |

For binding and validation errors, a **whole-context test can be worthwhile** to prove the validation starter, Jackson, and exception advice are genuinely registered together. The project below uses this approach to avoid missing MVC components in a partial setup.

### 4.2. When `@WebMvcTest` can give misleading results

`@WebMvcTest` does not scan every `@Service`/`@Repository` like the full application. If a controller depends on a service, provide `@MockitoBean` or matching test beans. Ensure relevant advice/converters are included. A web slice can inadvertently **omit** a global `WebMvcConfigurer` or custom bean used in production.

Conversely, `@SpringBootTest` is heavier; use it judiciously instead of booting the full context for every small validation unit case.

## 5. Structuring a clean test: Arrange → Act → Assert

Example:

```java
@Test
void missingRequiredParameterReturnsStableErrorContract()
        throws Exception {

    mvc.perform(get("/api/count"))
            .andExpect(status().isBadRequest())
            .andExpect(content().contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.code")
                    .value("MISSING_PARAMETER"))
            .andExpect(jsonPath("$.issues[0].field")
                    .value("count"))
            .andExpect(jsonPath("$.issues[0].code")
                    .value("required"));
}
```

Breakdown:
- **Arrange:** specific route and input (deliberately omitting `count`).
- **Act:** request executed through MockMvc.
- **Assert:** HTTP status, content type, machine code, and field path.

This is a snippet; the complete class and imports are in the project section. For response contracts, avoid asserting full JSON serialization via a raw string because JSON object key ordering is not guaranteed. Use `jsonPath` or `content().json(...)` with structural matching.

### 5.1. `andExpect` vs `andDo(print())`?

`andExpect(...)` makes assertions that verify the contract. `andDo(print())` only aids request/response debugging and does not make a test "pass better". When debugging:
- Use `andDo(print())` temporarily in an appropriate environment.
- Never log raw request bodies containing secrets to public CI logs.
- Once fixed, keep assertions that express the real requirement.

### 5.2. `andReturn()` is useful for deeper inspection

`MvcResult result = mvc.perform(...).andReturn();` exposes `MockHttpServletResponse` and `getResolvedException()`. You can assert the **exception type** to verify the request took the intended MVC branch:

```java
mvc.perform(get("/api/count").param("count", "abc"))
        .andExpect(result ->
                assertInstanceOf(
                        MethodArgumentTypeMismatchException.class,
                        result.getResolvedException()));
```

This illustrative snippet requires full imports and test context. **Do not treat the exception type as the entire response contract**: HTTP clients do not receive Java exception classes. When proving both, assert the error envelope and the resolved exception in the same test or separate tests.

## 6. Sample project: Java 17 + Spring Boot 3.5.6

The project implements an item-management API with:
1. Query param `count` for missing/type-mismatch cases.
2. Query param `page` annotated with `@Min(1)` for MVC method validation.
3. JSON `CreateItemRequest` with `@Valid` and nested `Delivery`.
4. Form `ItemForm` receiving setter-bound data, with both a **local BindingResult** path and an **unhandled** path going to advice.
5. Unified error envelope `ApiError`.
6. `ApiExceptionHandler` extending `ResponseEntityExceptionHandler`.
7. MockMvc test suites covering each branch and contract.

Spring Boot **3.5.6** is pinned for this example, **not implying it is always the latest release**. Do not use Spring Boot 4 imports in this project. JDK 17+ and Maven dependency resolution are required.

### 6.1. Directory layout

```text
mockmvc-contract-demo/
├── pom.xml
├── src/main/java/demo/contract/
│   ├── ContractApplication.java
│   ├── CreateItemRequest.java
│   ├── ItemForm.java
│   ├── ApiError.java
│   ├── ItemController.java
│   └── ApiExceptionHandler.java
└── src/test/java/demo/contract/
    ├── QueryAndMethodValidationTest.java
    ├── JsonValidationContractTest.java
    ├── FormBindingContractTest.java
    └── ResponseContractSecurityTest.java
```

### 6.2. `pom.xml`

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
    <artifactId>mockmvc-contract-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

- `spring-boot-starter-web` provides Spring MVC Servlet + Jackson converters and Tomcat for running the server.
- `spring-boot-starter-validation` provides the Jakarta Validation provider in standard setups; **without it**, `@NotBlank` alone does not guarantee validation runs as expected.
- `spring-boot-starter-test` includes JUnit Jupiter, Spring Test MockMvc, and Hamcrest/AssertJ.
- No database, credentials, or Testcontainers are needed.

### 6.3. `ContractApplication.java`

```java
package demo.contract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(ContractApplication.class, args);
    }
}
```

### 6.4. `CreateItemRequest.java`

```java
package demo.contract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateItemRequest(

        @NotBlank(message = "name.required")
        @Size(max = 12, message = "name.tooLong")
        String name,

        @NotNull(message = "quantity.required")
        @Min(value = 1, message = "quantity.tooSmall")
        Integer quantity,

        @NotNull(message = "delivery.required")
        @Valid
        Delivery delivery) {

    public record Delivery(
            @NotBlank(message = "delivery.city.required")
            String city) {
    }
}
```

**Why `Integer` instead of `int`?** JSON omitting `quantity` or passing `null` yields `null` (under standard Jackson configuration), allowing `@NotNull` to distinguish it from `quantity=0`. `@Min` alone treats null as valid and does not replace `@NotNull`.

`@NotBlank` rejects null, empty, and whitespace-only strings. `@Size(max=12)` rejects overly long names without rejecting whitespace like `@NotBlank`. Both constraints can sit on one field; do not rely on violation collection ordering.

`@NotNull @Valid Delivery` distinguishes:
- Missing the entire nested `delivery` object → `NotNull` at path `delivery`.
- Object present with `city=""` → `NotBlank` at path `delivery.city`.

### 6.5. `ItemForm.java`

```java
package demo.contract;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ItemForm {

    @NotBlank(message = "name.required")
    private String name;

    @NotNull(message = "quantity.required")
    @Min(value = 1, message = "quantity.tooSmall")
    private Integer quantity;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

This mutable JavaBean is a minimal form request DTO. It exposes no privilege/owner/id fields; sensitive fields like `approved`, `role`, or `ownerId` must never belong to a public input DTO.

### 6.6. `ApiError.java` — defining a testable schema

```java
package demo.contract;

import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.stream.Stream;

public record ApiError(String code, List<Issue> issues) {

    public record Issue(
            String field,
            String code,
            String category) {
    }

    public static ApiError simple(String code) {
        return new ApiError(code, List.of());
    }

    public static ApiError one(
            String code,
            String field,
            String issueCode,
            String category) {
        return new ApiError(code,
                List.of(new Issue(field, issueCode, category)));
    }

    public static ApiError fromBindingResult(BindingResult result) {

        Stream<Issue> fieldIssues = result.getFieldErrors().stream()
                .map(error -> new Issue(
                        error.getField(),
                        error.isBindingFailure()
                                ? "typeMismatch"
                                : Objects.requireNonNullElse(
                                        error.getCode(), "invalid"),
                        error.isBindingFailure()
                                ? "binding"
                                : "constraint"));

        Stream<Issue> globalIssues = result.getGlobalErrors().stream()
                .map(error -> new Issue(
                        "_object",
                        Objects.requireNonNullElse(
                                error.getCode(), "invalid"),
                        "constraint"));

        List<Issue> issues = Stream.concat(fieldIssues, globalIssues)
                .distinct()
                .sorted(Comparator.comparing(Issue::field)
                        .thenComparing(Issue::code)
                        .thenComparing(Issue::category))
                .toList();

        boolean hasBindingFailure = result.getFieldErrors()
                .stream()
                .anyMatch(FieldError::isBindingFailure);

        String responseCode = hasBindingFailure
                ? "BINDING_ERROR"
                : "VALIDATION_ERROR";

        return new ApiError(responseCode, issues);
    }
}
```

This is the **complete implementation** of the demo error schema:
- `record` keeps response data immutable at the record-reference level.
- `issues` is sorted deterministically by field/code/category.
- `FieldError.isBindingFailure()` separates bind/type errors from constraint validation.
- Object-wide `ObjectError` entries get logical field `_object` so they are never dropped.
- `getRejectedValue()`, exception messages, stack traces, and internal Java types are omitted from the payload.
- When multiple errors hit the same field, issues with distinct codes are preserved; only exact duplicates are removed.

**Avoid misunderstanding:** `FieldError.getCode()` depends on the applied annotation/validator. The demo uses Jakarta constraints `@NotBlank`, `@Min`, `@NotNull`, and `@Size`, whose standard codes are `NotBlank`, `Min`, `NotNull`, and `Size`. If a project uses a custom `MessageCodesResolver` or custom Spring `Validator`, define explicit machine-code mappings rather than treating every `getCode()` as an immutable public contract.

### 6.7. `ItemController.java` — error branches to test

```java
package demo.contract;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class ItemController {

    // No class-level @Validated:
    // uses MVC built-in method validation from Spring 6.1+.

    @GetMapping("/count")
    public Map<String, Integer> count(
            @RequestParam("count") Integer count) {
        return Map.of("count", count);
    }

    @GetMapping("/page")
    public Map<String, Integer> page(
            @RequestParam("page") @Min(1) int page) {
        return Map.of("page", page);
    }

    @PostMapping(path = "/items",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody CreateItemRequest request) {

        Map<String, Object> body = Map.of(
                "name", request.name(),
                "quantity", request.quantity(),
                "city", request.delivery().city());

        return ResponseEntity.status(HttpStatus.CREATED).body(body);
    }

    @InitBinder("itemForm")
    void restrictForm(WebDataBinder binder) {
        binder.setAllowedFields("name", "quantity");
    }

    @PostMapping(path = "/form-local",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formLocal(
            @Valid @ModelAttribute("itemForm") ItemForm form,
            BindingResult errors) {

        // Suppressed fields are not necessarily FieldErrors.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(ApiError.simple("UNEXPECTED_FIELD"));
        }

        if (errors.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(ApiError.fromBindingResult(errors));
        }

        return ResponseEntity.ok(Map.of(
                "name", form.getName(),
                "quantity", form.getQuantity()));
    }

    @PostMapping(path = "/form-unhandled",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Map<String, Object> formUnhandled(
            @Valid @ModelAttribute("itemForm") ItemForm form) {

        // No BindingResult immediately after DTO:
        // MVC can throw MethodArgumentNotValidException.
        return Map.of(
                "name", form.getName(),
                "quantity", form.getQuantity());
    }

    @NotNull
    @GetMapping("/server-contract")
    public String brokenReturnContract() {
        // Endpoint intentionally violating postcondition, FOR TEST ONLY.
        return null;
    }
}
```

**Why two similar form endpoints?**
- `form-local()` places `BindingResult` **immediately after** `@ModelAttribute`. The controller reads and handles errors locally.
- `form-unhandled()` omits `BindingResult`; Spring typically throws `MethodArgumentNotValidException` for global advice to handle.

Do not use `@RequestBody` to prove `setAllowedFields` blocks Jackson: JSON deserialization uses a different pipeline. `@InitBinder("itemForm")` restricts setter/property binding for the form. In production, still enforce authorization and dedicated input DTOs.

**Why an endpoint returning null?** It is a fixture intentionally violating `@NotNull` on the return value, used to test HTTP **500** instead of turning every constraint error into 400. **Never deploy such an endpoint in production**.

### 6.8. `ApiExceptionHandler.java` — returning a unified error contract

```java
package demo.contract;

import org.springframework.beans.TypeMismatchException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

@RestControllerAdvice
public class ApiExceptionHandler extends ResponseEntityExceptionHandler {

    private ResponseEntity<Object> reply(
            HttpHeaders headers,
            HttpStatusCode status,
            ApiError error) {

        return new ResponseEntity<>(error, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMissingServletRequestParameter(
            MissingServletRequestParameterException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status, ApiError.one(
                "MISSING_PARAMETER",
                ex.getParameterName(), "required", "presence"));
    }

    @Override
    protected ResponseEntity<Object> handleTypeMismatch(
            TypeMismatchException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (status.is5xxServerError()) {
            // For example, unsupported server-side conversion config.
            return reply(headers, status,
                    ApiError.simple("SERVER_CONVERSION_ERROR"));
        }

        String field =
                ex instanceof MethodArgumentTypeMismatchException mismatch
                        ? mismatch.getName()
                        : "parameter";

        return reply(headers, status, ApiError.one(
                "TYPE_MISMATCH",
                field, "typeMismatch", "binding"));
    }

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Do not echo raw body, Jackson exception text, or stack trace.
        return reply(headers, status,
                ApiError.simple("BODY_UNREADABLE"));
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return reply(headers, status,
                ApiError.fromBindingResult(ex.getBindingResult()));
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        if (ex.isForReturnValue()) {
            // Return server contract error; do not expose return data.
            return reply(headers, status,
                    ApiError.simple("SERVER_CONTRACT_VIOLATION"));
        }

        List<ApiError.Issue> issues = new ArrayList<>();

        for (var parameterResult : ex.getAllValidationResults()) {
            var parameter = parameterResult.getMethodParameter();
            var query = parameter.getParameterAnnotation(
                    RequestParam.class);

            String field = "arg" + parameter.getParameterIndex();

            if (query != null) {
                if (!query.value().isBlank()) {
                    field = query.value();
                } else if (!query.name().isBlank()) {
                    field = query.name();
                }
            }

            for (var error : parameterResult.getResolvableErrors()) {
                // Preserve nested DTO detail if MVC provides FieldError.
                if (error instanceof FieldError fieldError) {
                    issues.add(new ApiError.Issue(
                            field + "." + fieldError.getField(),
                            fieldError.getCode() == null
                                    ? "invalid"
                                    : fieldError.getCode(),
                            fieldError.isBindingFailure()
                                    ? "binding"
                                    : "constraint"));
                } else {
                    issues.add(new ApiError.Issue(
                            field, "invalid", "constraint"));
                }
            }
        }

        List<ApiError.Issue> ordered = issues.stream()
                .distinct()
                .sorted(Comparator.comparing(ApiError.Issue::field)
                        .thenComparing(ApiError.Issue::code)
                        .thenComparing(ApiError.Issue::category))
                .toList();

        return reply(headers, status,
                new ApiError("METHOD_VALIDATION_ERROR", ordered));
    }
}
```

**Intentional decisions in the handler:**
- Extend `ResponseEntityExceptionHandler` and **override protected methods** instead of adding duplicate `@ExceptionHandler` mappings for superclass-handled exceptions.
- Preserve the `HttpStatusCode status` provided by Spring; do not turn a 500 return-value violation into 400.
- Preserve `HttpHeaders` passed by Spring rather than creating empty headers in every handler.
- `handleMethodArgumentNotValid` classifies errors from the real `BindingResult` rather than treating every FieldError as a Jakarta constraint.
- `handleHandlerMethodValidationException` uses `getAllValidationResults()` to inspect parameter-specific results instead of parsing exception text.
- Because a handler method can validate multiple arguments, results are sorted deterministically.
- For direct `@Min` on `page`, the demo uses a generic `invalid` issue code; if an API needs specific codes like `Min` for method validation, write a tested mapper over `MessageSourceResolvable`/ConstraintViolation/visitor metadata.

**Demo limitations:** `@RequestParam` is matched by annotation to extract explicit `value/name`; for `@RequestHeader`, `@PathVariable`, or complex `@ModelAttribute`, extend parameter-name and nested-path mapping per handler contract. Never treat `arg0` as a user-facing field name in production APIs. `getAllValidationResults()` is a Spring MVC method-validation API, not applicable to AOP `ConstraintViolationException` from services.

### 6.9. Response consistency

With the code above, errors detected by:
- Argument resolvers for query params.
- Jackson message converters for JSON.
- WebDataBinder for forms.
- Jakarta validators on DTOs.
- MVC method validation.

all conform to one shape:

```json
{
  "code": "SOME_STABLE_CODE",
  "issues": []
}
```

There is no `timestamp`, `trace`, or `exception` in the demo JSON. If a production API adopts `ProblemDetail`, change the schema centrally and update client contract tests rather than varying per controller.

## 7. MockMvc: testing missing/wrong-type/query and method validation

### 7.1. `QueryAndMethodValidationTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.bind.MissingServletRequestParameterException;

import static org.hamcrest.Matchers.aMapWithSize;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QueryAndMethodValidationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validCountReturnsSuccess() throws Exception {
        mvc.perform(get("/api/count").param("count", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(2));
    }

    @Test
    void missingCountHasOwnCodeAndField() throws Exception {
        mvc.perform(get("/api/count"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("count"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("required"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("presence"))
                .andExpect(result -> assertInstanceOf(
                        MissingServletRequestParameterException.class,
                        result.getResolvedException()));
    }

    @Test
    void invalidCountIsTypeMismatchNotMissing() throws Exception {
        mvc.perform(get("/api/count").param("count", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("count"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("typeMismatch"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentTypeMismatchException.class,
                        result.getResolvedException()));
    }

    @Test
    void zeroIsAllowedWhenOnlyConversionIsRequired() throws Exception {
        mvc.perform(get("/api/count").param("count", "0"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(0));
    }

    @Test
    void validPagePassesDirectMin() throws Exception {
        mvc.perform(get("/api/page").param("page", "1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.page").value(1));
    }

    @Test
    void zeroPageTriggersMvcMethodValidation() throws Exception {
        mvc.perform(get("/api/page").param("page", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("page"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("invalid"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("constraint"))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }

    @Test
    void wrongTypeIsRejectedBeforeMinConstraint() throws Exception {
        mvc.perform(get("/api/page").param("page", "not-an-int"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("TYPE_MISMATCH"));
    }

    @Test
    void returnValueConstraintFailureStaysServerError()
            throws Exception {

        mvc.perform(get("/api/server-contract"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("SERVER_CONTRACT_VIOLATION"))
                .andExpect(jsonPath("$.issues", hasSize(0)))
                .andExpect(result -> assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException()));
    }
}
```

This layer tests **argument presence**, **type mismatch**, **handler method validation**, and **return-value contract violations**. Asserting the resolved exception catches regressions where a signature change routes requests down a different framework path, while `jsonPath` checks the API contract seen by clients.

**Nuance:** A request `count=` (parameter present but empty) can enter the *missing after conversion* path for wrapper `Integer`. If adding that test, inspect `MissingServletRequestParameterException.isMissingAfterConversion()` on your exact version rather than assuming every empty string produces `MethodArgumentTypeMismatchException`.

## 8. MockMvc: JSON decoder and Bean Validation

### 8.1. `JsonValidationContractTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class JsonValidationContractTest {

    @Autowired
    MockMvc mvc;

    private static final String VALID = """
            {
              "name":"Book",
              "quantity":2,
              "delivery":{"city":"Hue"}
            }
            """;

    @Test
    void validJsonCreatesItem() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Book"))
                .andExpect(jsonPath("$.quantity").value(2))
                .andExpect(jsonPath("$.city").value("Hue"));
    }

    @Test
    void missingBodyIsNotAConstraintViolation() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(""))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"))
                .andExpect(jsonPath("$.issues", hasSize(0)))
                .andExpect(result -> assertInstanceOf(
                        HttpMessageNotReadableException.class,
                        result.getResolvedException()));
    }

    @Test
    void malformedJsonIsUnreadable() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void jsonFieldWrongJavaTypeIsUnreadable() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "quantity":{"unexpected":true},
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"));
    }

    @Test
    void blankNameHasNotBlankViolation() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"  ",
                              "quantity":2,
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("constraint"))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void missingQuantityTriggersNotNull() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotNull"));
    }

    @Test
    void zeroQuantityTriggersMinNotTypeMismatch() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "quantity":0,
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].code").value("Min"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("quantity"));
    }

    @Test
    void missingDeliveryHasOwnNotNullPath() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {"name":"Book","quantity":2}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].field")
                        .value("delivery"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotNull"));
    }

    @Test
    void nestedCityHasNestedFieldPath() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"Book",
                              "quantity":2,
                              "delivery":{"city":""}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].field")
                        .value("delivery.city"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"));
    }

    @Test
    void tooLongNameTriggersSize() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"VeryLongProductName",
                              "quantity":2,
                              "delivery":{"city":"Hue"}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("Size"));
    }

    @Test
    void multipleViolationsAreReturnedAsStableFieldList()
            throws Exception {

        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "name":"",
                              "quantity":0,
                              "delivery":{"city":""}
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("name")))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("delivery.city")));
    }

    @Test
    void validJsonStillUsesSameSuccessContract() throws Exception {
        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.name").value("Book"));
    }
}
```

The tests intentionally distinguish:
- **Empty body / malformed JSON / wrong Java type** → `BODY_UNREADABLE`.
- **DTO instantiated but violates constraints** → `VALIDATION_ERROR`.
- **Nested cascade**: path `delivery.city`.
- **Multiple violations**: asserts presence of each field rather than tying tests to arbitrary provider ordering.

In the multi-error test, `issues[]` is sorted inside `ApiError.fromBindingResult`, so order assertions can be added if ordering is part of the published contract. Still, frontends should rely on **field/code** rather than inferring business meaning from array indexes.

## 9. MockMvc: local BindingResult and global exception advice

### 9.1. `FormBindingContractTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.hamcrest.Matchers.hasItem;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FormBindingContractTest {

    @Autowired
    MockMvc mvc;

    private org.springframework.test.web.servlet.request
            .MockHttpServletRequestBuilder form(String path) {

        return post(path)
                .contentType(MediaType.APPLICATION_FORM_URLENCODED);
    }

    @Test
    void localFormBindingSucceeds() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Book"))
                .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void localFormWrongTypeIsBindingFailure() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("typeMismatch")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("binding")));
    }

    @Test
    void localFormConstraintViolationIsDifferent() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "")
                        .param("quantity", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("name"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotBlank"))
                .andExpect(jsonPath("$.issues[0].category")
                        .value("constraint"));
    }

    @Test
    void localFormMinConstraintIsNotBindingError() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("Min"));
    }

    @Test
    void localFormMissingQuantityIsNotNullViolation() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "Book"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.issues[0].code")
                        .value("NotNull"));
    }

    @Test
    void localFormCanContainBindingAndConstraintIssues() throws Exception {
        mvc.perform(form("/api/form-local")
                        .param("name", "")
                        .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("name")))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("binding")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("constraint")));
    }

    @Test
    void localFormRejectsSuppressedFieldsEvenIfKnownFieldsValid()
            throws Exception {

        mvc.perform(form("/api/form-local")
                        .param("name", "Book")
                        .param("quantity", "2")
                        .param("role", "admin"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_FIELD"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }

    @Test
    void globalAdviceHandlesUnhandledFormBindingError()
            throws Exception {

        mvc.perform(form("/api/form-unhandled")
                        .param("name", "Book")
                        .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].field",
                        hasItem("quantity")))
                .andExpect(result -> assertInstanceOf(
                        MethodArgumentNotValidException.class,
                        result.getResolvedException()));
    }

    @Test
    void globalAdviceHandlesUnhandledFormConstraint() throws Exception {
        mvc.perform(form("/api/form-unhandled")
                        .param("name", "")
                        .param("quantity", "2"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.issues[*].code",
                        hasItem("NotBlank")));
    }

    @Test
    void globalAdviceKeepsBindingAndConstraintDetails()
            throws Exception {

        mvc.perform(form("/api/form-unhandled")
                        .param("name", "")
                        .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("BINDING_ERROR"))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("binding")))
                .andExpect(jsonPath("$.issues[*].category",
                        hasItem("constraint")));
    }

    @Test
    void validUnhandledFormStillSucceeds() throws Exception {
        mvc.perform(form("/api/form-unhandled")
                        .param("name", "Book")
                        .param("quantity", "5"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.quantity").value(5));
    }
}
```

**Key points of the form tests:**
- `@ModelAttribute` uses setter/property binding; String `"abc"` fails to convert to `Integer`.
- `BindingResult` right after the DTO lets the handler process errors locally.
- Without `BindingResult`, `MethodArgumentNotValidException` can contain **both binding failures and constraint violations**.
- `hasErrors()` is not enough to catch every allowlist-suppressed field; check `getSuppressedFields()` separately.
- A single request can produce errors across **multiple fields and multiple categories**, so the response preserves each issue instead of returning a single String.
- Client contract tests should assert stable codes; exception internals are only for debugging or asserting framework routing.

## 10. MockMvc: response contract and security

### 10.1. `ResponseContractSecurityTest.java`

```java
package demo.contract;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.aMapWithSize;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ResponseContractSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void errorEnvelopeHasOnlyStableTopLevelFields() throws Exception {
        mvc.perform(get("/api/count"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$", aMapWithSize(2)))
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.issues", hasSize(1)))
                .andExpect(jsonPath("$.timestamp").doesNotExist())
                .andExpect(jsonPath("$.trace").doesNotExist())
                .andExpect(jsonPath("$.exception").doesNotExist());
    }

    @Test
    void everyErrorIsSerializedAsJson() throws Exception {
        mvc.perform(get("/api/count").param("count", "wrong"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON));
    }

    @Test
    void untrustedInputIsNotEchoedInTypeError() throws Exception {
        String raw = "SENSITIVE_REQUEST_PAYLOAD_938472";

        String body = mvc.perform(get("/api/count")
                        .param("count", raw))
                .andExpect(status().isBadRequest())
                .andReturn().getResponse().getContentAsString();

        assertFalse(body.contains(raw));
        assertFalse(body.contains("MethodArgumentTypeMismatchException"));
    }

    @Test
    void unreadableJsonDoesNotLeakRawParserMessage()
            throws Exception {

        mvc.perform(post("/api/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$", aMapWithSize(2)))
                .andExpect(jsonPath("$.code")
                        .value("BODY_UNREADABLE"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }

    @Test
    void serverReturnViolationIsNotMisclassifiedAsClient400()
            throws Exception {

        mvc.perform(get("/api/server-contract"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("SERVER_CONTRACT_VIOLATION"))
                .andExpect(jsonPath("$.issues", hasSize(0)));
    }
}
```

Security tests do not certify the entire system as "completely secure". They verify useful invariants of the **error contract we control**:
- Never echo the request field value `raw` into JSON.
- Never leak Java exception class names into the body.
- Error envelopes always contain `code` and `issues`.
- Method return constraint violations remain server errors.
- Jackson parse errors return a minimal schema without pushing stack traces.

Production systems also need dedicated tests for authentication/authorization, content negotiation, CORS, headers, rate limiting, and logging policies.

## 11. Running tests and interpreting results

Across the four test classes defined above, there are **multiple `@Test` methods** covering success, missing parameters, wrong types, validation, nested field paths, response envelopes, security, and 500 server contracts. "Tests pass" can only be confirmed **after running Maven in your environment**; this is explained reference code, not a claim that a build was executed while authoring the lesson.

In `mockmvc-contract-demo`:

```bash
mvn test
```

Run an individual test class to isolate failures:

```bash
mvn -Dtest=QueryAndMethodValidationTest test
mvn -Dtest=JsonValidationContractTest test
mvn -Dtest=FormBindingContractTest test
mvn -Dtest=ResponseContractSecurityTest test
```

Run the application:

```bash
mvn spring-boot:run
```

Commands require JDK 17+ and Maven dependency access. Do not lock expectations to Maven/Spring Boot stdout; standard Surefire reports under `target/surefire-reports` report exact counts and any failures.

### 11.1. When an assertion fails, inspect by layer

| Failing check | What to inspect |
| --- | --- |
| Wrong HTTP status | Handler mapping, controller return, exception type, whether advice is registered |
| Wrong `$.code` | Argument resolution/converter/validator path, overridden handler mapping |
| Wrong `issues[*].field` | Object name, nested path, method parameter name, `@ModelAttribute` |
| Wrong `issues[*].category` | `FieldError.isBindingFailure()`, issue mapping |
| Direct `@Min` throws a different exception | Spring MVC version, class-level `@Validated`, method validation config |
| Form test reports missing `typeMismatch` code | DataBinder conversion, errorCode mapping, DTO field type |
| Malformed JSON returns 500 | Bug in custom exception handler/mapper, logging, or serialization |
| Status right but no JSON body | Advice returned null body; message converter not loaded |
| Web slice test passes while full-context test fails | Bean registration, filters, security, custom config, validation provider |
| Valid form rejected due to disallowed field | `@InitBinder` allowed fields, suppressed fields, and property names |

### 11.2. `MockMvc` must never force a failure to be "200 OK"

An anti-pattern:

```java
mvc.perform(post("/api/items")
                .contentType(MediaType.APPLICATION_JSON)
                .content(invalidJson))
   .andExpect(status().isOk());
```

If input violates the contract and the server is designed to return 400, changing the test to expect 200 just to pass does not fix the cause. Changing status/error semantics must be a reasoned **API contract** decision, not a sloppy test edit.

## 12. Trying the API with curl

### 12.1. Missing query param

```bash
curl -i 'http://localhost:8080/api/count'
```

Expected HTTP 400 with a body like:

```json
{
  "code": "MISSING_PARAMETER",
  "issues": [
    {"field":"count","code":"required","category":"presence"}
  ]
}
```

### 12.2. Wrong-type query param

```bash
curl -i 'http://localhost:8080/api/count?count=abc'
```

Expected HTTP 400:

```json
{
  "code": "TYPE_MISMATCH",
  "issues": [
    {"field":"count","code":"typeMismatch","category":"binding"}
  ]
}
```

### 12.3. Direct `@Min`

```bash
curl -i 'http://localhost:8080/api/page?page=0'
```

Expected HTTP 400:

```json
{
  "code": "METHOD_VALIDATION_ERROR",
  "issues": [
    {"field":"page","code":"invalid","category":"constraint"}
  ]
}
```

### 12.4. Valid JSON

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Book","quantity":2,"delivery":{"city":"Hue"}}'
```

Expected HTTP 201 and body:

```json
{"name":"Book","quantity":2,"city":"Hue"}
```

### 12.5. JSON with valid types but failing constraint

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Book","quantity":0,"delivery":{"city":"Hue"}}'
```

Expected HTTP 400, error category `VALIDATION_ERROR`, and issue `quantity/Min/constraint`.

### 12.6. Undecodable JSON

```bash
curl -i -X POST \
  'http://localhost:8080/api/items' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Book","quantity":{"oops":1},"delivery":{"city":"Hue"}}'
```

Expected HTTP 400, code `BODY_UNREADABLE`, and no `Min` issue because the value was never decoded into `Integer`.

### 12.7. Form wrong type

```bash
curl -i -X POST \
  'http://localhost:8080/api/form-local' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Book' \
  --data-urlencode 'quantity=abc'
```

Expected HTTP 400, error category `BINDING_ERROR`, and issue `quantity/typeMismatch/binding`.

### 12.8. Form blocked due to unexpected field

```bash
curl -i -X POST \
  'http://localhost:8080/api/form-local' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'name=Book' \
  --data-urlencode 'quantity=2' \
  --data-urlencode 'role=admin'
```

Expected HTTP 400, code `UNEXPECTED_FIELD`, empty issues. This is the demo's explicit policy: do not silently ignore suppressed property paths.

## 13. Avoiding flaky tests: assertions to write and avoid

### 13.1. Do not rely on validation provider ordering

A field can violate both `@NotBlank` and `@Size`, and constraints may be evaluated/returned in no fixed order.

Avoid:

```java
.andExpect(jsonPath("$.issues[0].code").value("NotBlank"))
.andExpect(jsonPath("$.issues[1].code").value("Size"))
```

if the API does **not** publish a sort order. In the demo, `ApiError` **intentionally sorts** issues by field and code, so ordering could be treated as a contract; still, when testing a multi-error request, using Hamcrest `hasItem` expresses intent better:

```java
.andExpect(jsonPath("$.issues[*].code",
        hasItem("NotBlank")))
.andExpect(jsonPath("$.issues[*].code",
        hasItem("Size")));
```

This is a snippet requiring imports for `hasItem` and `jsonPath`. If a sorting policy is published, write a dedicated test for sorting rather than coupling all tests to serialization details.

### 13.2. Do not assert provider default message text

Avoid pinning exact text like:

```text
must be greater than or equal to 1
```

because locale and Hibernate Validator message interpolation can change. If the app explicitly defines translations and commits to display phrasing, test **the application's message bundles**, not the provider's default text.

### 13.3. Avoid raw full-string JSON comparisons

JSON object key ordering is not a default contract. The following is fragile:

```java
assertEquals(
  "{\"code\":\"MISSING_PARAMETER\",\"issues\":[]}",
  responseText);
```

Use `jsonPath` or `content().json(expectedJson)` with the appropriate matching mode. If the schema allows optional fields to be added, decide whether strict or lenient matching applies; for example `aMapWithSize(2)` in the demo **intentionally** locks top-level keys to detect schema drift.

### 13.4. Do not assert Spring exception raw messages

Strings from `MethodArgumentTypeMismatchException#getMessage()` can expose argument names, Java classes, and internal details. Use the exception **type** when debugging routing, the **API's** machine code for the contract, and the HTTP status for semantics. Never parse English substrings from Spring exceptions to infer a field name.

### 13.5. Synthetic inputs that actually catch bugs

Use distinct inputs to catch distinct bugs:
- Missing: omit `param` or send empty body.
- Wrong type: `quantity=abc`.
- Constraint violation: `quantity=0`.
- Valid: `quantity=2`.
- Nested invalid: `delivery.city=""`.
- Suppressed: `role=admin`.

If both "wrong type" and "violation" use `quantity=0`, tests might never exercise the conversion-failure branch.

## 14. Inspecting exact exception paths with `getResolvedException()`

When debugging, code like:

```java
MvcResult result = mvc.perform(
        get("/api/count").param("count", "abc"))
        .andReturn();

Exception ex = result.getResolvedException();
assertInstanceOf(MethodArgumentTypeMismatchException.class, ex);
```

helps confirm Spring MVC received the request, failed type conversion, and resolved that exception. However:
- If the controller handles errors itself with `BindingResult`, there may be **no resolved exception** despite a 400 response.
- If custom advice catches errors without going through the same resolver, the exception path can differ.
- `getResolvedException()` does not replace body contract tests.
- Under `@SpringBootTest(webEnvironment=RANDOM_PORT)` over real HTTP, there is no `MvcResult.getResolvedException()` on the client.

Never use the resolved exception as the sole proof that an HTTP error was normalized properly.

## 15. Testing that the controller did not process invalid requests like valid ones

In real APIs, checking status/messages is still not enough to guarantee **no database writes** occurred when binding/validation failed. If a controller calls a service:

```java
@RestController
public class CreateController {

    private final ItemService service;

    public CreateController(ItemService service) {
        this.service = service;
    }

    @PostMapping("/items")
    public ResponseEntity<?> create(
            @Valid @RequestBody CreateItemRequest request) {

        service.create(request);
        return ResponseEntity.status(201).build();
    }
}
```

This is an **architectural fragment** requiring `ItemService` and imports; it is not another file in section 6's runnable project.

In `@WebMvcTest`, you can use `@MockitoBean ItemService service`, send invalid JSON, and assert:

```java
verifyNoInteractions(service);
```

to prove validation stopped the request **before** writing business data. With a local `BindingResult`, the controller method is still entered, so your code must explicitly return on errors; MockMvc tests should assert not only the response but also that the service is never called when that is a security/data-integrity requirement.

When testing authorization or transaction rollbacks, add service/repository integration tests; MockMvc response checks alone do not prove the DB stayed untouched.

## 16. How do security filters, CORS, and authentication affect tests?

If Spring Security is on the classpath, Boot's `MockMvc` can auto-configure security filters. Unauthenticated requests may then receive **401/403 before controller binding/validation runs**. That is right for the system, yet it causes tests "expecting 400" to fail unless the setup provides valid credentials.

Options:
- For **binding/validation** tests, supply a valid authenticated principal (`spring-security-test`, `@WithMockUser`, or a request post-processor) so requests reach the controller.
- Test 401/403 in a dedicated security test suite.
- Never disable security completely just to make tests pass when production requires protection.
- `@WebMvcTest` can scan security filters; verify the slice configuration includes required beans.

The demo project **has no Spring Security dependency**, so tests focus solely on the MVC validation contract.

## 17. Spring MVC `ProblemDetail` and extensible error contracts

Spring Framework supports RFC 9457 `ProblemDetail`. An API can choose:

```json
{
  "type": "about:blank",
  "title": "Bad Request",
  "status": 400,
  "detail": "Some fields are invalid",
  "code": "VALIDATION_ERROR",
  "issues": [
    {"field":"quantity","code":"Min","category":"constraint"}
  ]
}
```

This is an **illustrative design schema**, not JSON emitted automatically by Spring in every configuration.

Advantages:
- Standard `status`/`title`/`type`/`detail` fields per RFC 9457.
- Supports custom `code`/`issues` extensions for the frontend.
- Built-in localization strategy via `MessageSource`.
- Consistent error handling across controllers.

When migrating from a custom `ApiError` to `ProblemDetail`, tests must verify:
1. HTTP status matches `ProblemDetail.status`.
2. `Content-Type: application/problem+json` when part of the contract.
3. Accurate machine codes and issues.
4. No leaked internal details.
5. 500 vs 400 error handling remains consistent.

Do not make large schema changes in a code review without updating OpenAPI/client tests and your versioning policy.

## 18. Checking consistency across multiple endpoints

A sound error contract holds across all controllers, not just one:

| Endpoint | Invalid request | HTTP | `code` |
| --- | --- | --- | --- |
| `GET /api/count` | missing count | 400 | `MISSING_PARAMETER` |
| `GET /api/count` | count=abc | 400 | `TYPE_MISMATCH` |
| `GET /api/page` | page=0 | 400 | `METHOD_VALIDATION_ERROR` |
| `POST /api/items` | malformed JSON | 400 | `BODY_UNREADABLE` |
| `POST /api/items` | quantity=0 | 400 | `VALIDATION_ERROR` |
| `POST /api/form-local` | quantity=abc | 400 | `BINDING_ERROR` |
| `POST /api/form-local` | role=admin | 400 | `UNEXPECTED_FIELD` |
| `POST /api/form-unhandled` | name="" | 400 | `VALIDATION_ERROR` |
| `GET /api/server-contract` | return null | 500 | `SERVER_CONTRACT_VIOLATION` |

These rows are **expected outcomes of the demo code**. When an app has custom message converters/advice or upgrades MVC versions, MockMvc regression tests catch divergences.

### 18.1. Subtle contract drift

A refactor might change:

```java
public String create(@Valid @RequestBody CreateItemRequest dto)
```

into:

```java
public String create(
        @RequestParam @Min(1) int amount,
        @Valid @RequestBody CreateItemRequest dto)
```

Adding the direct method constraint `@Min` can switch the exception path to `HandlerMethodValidationException`. If advice only handles `MethodArgumentNotValidException`, the API can suddenly return a completely different error JSON.

That is why test suites must cover **both validation modes** and preserve error schema consistency whenever controller signatures change.

## 19. Common testing mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Asserting only `400` | Misses wrong category, missing fields, or data leaks | Assert `code`, `issues`, content type |
| Testing `@Min` with `"abc"` | Conversion fails first, never tests constraint | Use `"0"` for Min, `"abc"` for conversion |
| Treating every `MethodArgumentNotValidException` as Bean Validation | Misses form type mismatches | Check `FieldError.isBindingFailure()` |
| Testing `@Valid` DTOs without testing direct method constraints | Misses `HandlerMethodValidationException` | Test `@RequestParam @Min` separately |
| Testing direct `@Min` without testing nested DTOs | Misses `@Valid` cascading and property paths | Test `delivery.city` |
| Forgetting `BindingResult` right after `@ModelAttribute` | Fails to catch errors locally as expected | Place adjacent or use global advice |
| Having `BindingResult` without checking `getSuppressedFields()` | Extra fields silently ignored when API should reject | Test suppression explicitly |
| Using `@RequestBody` to test setter allowlists | Jackson deserializes differently from DataBinder | Use `@ModelAttribute` form/query |
| `@WebMvcTest` missing advice/validator | Response differs from production | Import/mock/configure required beans |
| `MockMvcBuilders.standaloneSetup` missing resolvers | Tests pass/fail due to non-production setup | Use web slice or full configuration |
| Relying on `ConstraintViolation` ordering | Flaky tests | Use `hasItem` or a sorted contract |
| Asserting raw exception text | Breaks after upgrades/provider/locale changes | Assert machine codes |
| Returning HTTP 400 for return-value constraints | Blames client for server bug | Keep status 500 |
| Echoing `getRejectedValue()` | Leaks PII/secrets | Restrict response and test no leaks |
| Testing only error cases, skipping happy paths | Unknown if valid conversion/serialization works | Test 200/201 with valid data |
| Testing only happy paths, skipping malformed JSON | Bad input handling unverified | Cover missing, malformed, and wrong-type bodies |
| Enabling security while expecting anonymous 400 | 401/403 blocks before validation | Set up valid auth; test security separately |
| Editing assertions to pass without understanding the exception | Masks regressions | Trace layer by layer and confirm API contract |

## 20. Pre-merge review checklist

1. Do tests use `spring-boot-starter-test` and a Jakarta Validation provider properly?
2. Do test annotations match the Spring Boot major version and Java 17?
3. Do requests use the right HTTP method, route, Content-Type, and parameters?
4. Are missing `@RequestParam` tests kept distinct from converter failures?
5. Is `count=abc` treated as type mismatch rather than `@Min`?
6. Is `page=0` tested with direct `@Min`, verifying the MVC method-validation branch?
7. Is malformed JSON on `@Valid @RequestBody` separated from constraint errors?
8. Are missing JSON fields tested with `@NotNull` and exact field paths?
9. Is `@Valid` cascading into nested objects tested with nested error paths?
10. Is local `BindingResult` placed immediately after the model attribute?
11. Is form `quantity=abc` verified via `FieldError.isBindingFailure()`?
12. Is a request with both binding and constraint errors tested so the response preserves both?
13. Are suppressed extra fields tested if the API requires rejecting them?
14. Does global exception advice override the exact Spring-version signatures?
15. Are response code/issue schemas, status, and content types asserted?
16. Are machine-readable codes tested to be locale-independent?
17. Are sorting/deduplication tested if guaranteed by the contract?
18. Are tests verifying no raw rejected values, internal exception names, or stack traces leak?
19. Are return-value constraints verified to return 500?
20. Are 200/201 success cases, JSON bodies, and field mappings tested?
21. Are multiple endpoints tested to detect schema drift?
22. When Spring Security is active, are authenticated requests set up cleanly?
23. If a service performs writes, is it verified that invalid requests never call the service or alter data?
24. When the error schema changes, are OpenAPI, SDK/client tests, and versioning policies updated?
25. Are real-server tests added separately for network/container concerns that MockMvc does not simulate?

## 21. Practice exercises

1. Add `GET /api/optional` with `@RequestParam(required=false) Integer count`. Test missing, empty, and invalid text; explain the differences.
2. Change `CreateItemRequest.quantity` from `Integer` to `int`. Send JSON omitting the field; observe the difference between 0 and null.
3. Write a JSON test triggering two constraint failures on the same field; assert with `hasItem` instead of fixed indexes.
4. Migrate `ApiError` to `ProblemDetail` and assert `Content-Type: application/problem+json`.
5. Add `@Size(min=3)` on `name` and test boundary lengths using `@ParameterizedTest`.
6. Write a form test `quantity=abc&name=` and compare `getFieldErrors()` with `isBindingFailure()` for each field.
7. Add a `String→CurrencyCode` converter via `WebMvcConfigurer#addFormatters`; test invalid conversion requests and code `TYPE_MISMATCH`.
8. Add a direct `@Min` to a handler receiving `@Valid @RequestBody`, then observe whether exception routing changes.
9. Add class-level `@Validated` on the controller in a separate test config, observe the AOP method-validation path, and avoid old assumptions.
10. Add a required `@RequestHeader("X-Correlation-Id")` endpoint; emit code `MISSING_HEADER` and MockMvc-test missing headers.
11. Add a multipart form with a missing file part and a 0-byte file; explain why presence differs from content validation.
12. Add a business error `ITEM_ALREADY_EXISTS` mapped to 409; keep the `code/issues` schema consistent without calling it a Jakarta violation.
13. Write tests with `Accept-Language: vi` and `en` if localized display messages exist; assert the machine `code` never changes.
14. Inject a service into the controller and use `@MockitoBean` + `verifyNoInteractions` to prove invalid requests never persist data.
15. Rename a few fields in the DTO and verify contract tests catch the API backward-compatibility break.
16. Add a 415 status test when sending `text/plain` to an endpoint consuming only `application/json`; ensure it is not mislabeled `BODY_UNREADABLE`.
17. Add a 405 status test for the wrong HTTP method; never classify routing errors as validation.
18. Write a strict JSON contract test verifying exact `code` and `issues` without `trace`.
19. Add high-volume negative-input tests while bounding request size and keeping raw PII out of test logs.
20. Use Testcontainers/a sandbox database to verify invalid forms create no records; keep that test separate from the MockMvc response contract where appropriate.

**Conclusion:** `MockMvc` validates both **the path through Spring MVC** and **the actual response contract**. For strong coverage, send inputs clearly separating **missing**, **unconvertible**, **constraint-violating**, **form-binding**, **method-validation**, and **server-error** cases; then assert HTTP status, `Content-Type`, `code`, `issues`, field paths, stability, and zero information leaks. That is how you catch regressions when changing controller signatures, converters, validators, or global exception handlers.

## Official references

- [Spring Framework 6.2 — Validation for MVC Handler Methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Error Responses, RFC 9457](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — HandlerMethodValidationException API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Framework 6.2 — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — ModelAttribute Methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — RequestBody Methods](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — MockMvc setup](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework/server-setup-options.html)
- [Spring Framework 6.2 — MockMvc performing requests](https://docs.spring.io/spring-framework/reference/6.2/testing/spring-mvc-test-framework/performing-requests.html)
- [Spring Boot 3.5 — Testing Spring Boot applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Jakarta Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)