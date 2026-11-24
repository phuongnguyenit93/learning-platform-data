# Spring MVC: Bean Validation, Error Binding, and Invalid Input Responses

## 1. Goal and Scope

In Spring MVC, a request passes through several stages **before the controller calls business logic**: handler selection → parameter extraction, JSON/form reading → type conversion (binding) → Bean Validation → controller method invocation → response construction. Invalid input at different stages can trigger **different exception types**, yet an API should return HTTP status codes and error structures that are **consistent, testable, and free of sensitive internal details**.

This lesson targets Spring Boot **3.5.x**, Spring Framework **6.2**, Java **17**, Servlet Spring MVC, JUnit Jupiter, and MockMvc. Jakarta Bean Validation uses the `jakarta.validation` package, not `javax.validation` from legacy Spring Boot 2.x projects.

By the end of this lesson, you will be able to:

1. Distinguish constraint validation from JSON parse errors and type-conversion errors.
2. Apply `@NotBlank`, `@NotNull`, `@Size`, `@Min`, `@Max`, and `@Valid` accurately.
3. Understand when `MethodArgumentNotValidException` versus `HandlerMethodValidationException` occurs.
4. Place `BindingResult` in the right parameter position when the controller decides the response itself.
5. Standardize HTTP 400 responses with `@RestControllerAdvice` without leaking rejected values or stack traces.
6. Use `@WebMvcTest` + `MockMvc` to test below/at/above boundary values, malformed JSON, form binding, and query/path conversion.
7. Prove that the service is **never invoked** when MVC rejects invalid input.

### Different Questions

| Question | Mechanism | Example |
| --- | --- | --- |
| Can the request body be parsed? | `HttpMessageConverter`/Jackson | Syntactically invalid JSON or `"quantity":"many"` |
| Can the data be converted to Java types? | `WebDataBinder`, `ConversionService`, argument resolvers | `quantity=abc` for a form field `Integer` |
| Are the converted Java values valid? | Jakarta Bean Validation provider (usually Hibernate Validator) | `@Min(1)`, `@NotBlank` |
| Does a controller parameter have direct constraints? | Spring MVC method validation | `@RequestParam @Min(1) int quantity` |
| What error will the API send to the client? | `@RestControllerAdvice` or `ResponseEntityExceptionHandler` | `400`, stable error code, and violated fields |
| Was the error caught before the business call? | MockMvc + Mockito verification | `verifyNoInteractions(service)` |

**Guiding principle:** HTTP 400 alone is insufficient proof. A thorough test verifies **status + error body + absence of side effects**.

## 2. Prerequisite: A Validation Provider on the Classpath

Annotations such as `@NotBlank` and `@Min` declare constraints, but executing Bean Validation requires a Jakarta Validation implementation. In Spring Boot 3.5, the standard way is to add:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

This starter brings Hibernate Validator and compatible dependencies into the application. In Boot 3.x, `spring-boot-starter-web` **must not be assumed** to include a validation implementation. `spring-boot-starter-test` supplies JUnit/Mockito/Spring Test and **does not substitute** for the validation starter in the application.

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
```

Keep starter versions managed by the Spring Boot BOM/parent/plugin. Never manually mix Hibernate Validator, Jakarta Validation API, and Spring Framework from mismatched major versions.

### Common Jakarta Constraints

| Constraint | Typical Targets | Important Notes |
| --- | --- | --- |
| `@NotNull` | Objects, `Integer`, nested DTOs | Disallows `null` only; empty strings still pass |
| `@NotBlank` | `CharSequence`, e.g. `String` | Disallows null and whitespace-only strings |
| `@NotEmpty` | Strings/collections/arrays/maps | Disallows null/empty, though whitespace-only strings can pass |
| `@Size(min,max)` | Strings/collections/arrays/maps | Checks length/size; null is usually permitted |
| `@Min`/`@Max` | Integer/numeric types | Bounds are **inclusive** |
| `@Positive`/`@PositiveOrZero` | Numbers | Note zero handling difference |
| `@Pattern(regexp=...)` | Strings | Regex check only; does not replace business validation |
| `@Email` | Strings | Checks format; does not prove the email exists |
| `@Past`/`@Future` | Dates/times | Reference clock should be controlled in tests |
| `@Valid` | Nested objects or container elements | **Triggers cascading**; does not forbid null on its own |
| `@Validated` | Spring annotation | Activates validation and can select **groups** |

**Null rule:** many constraints like `@Min` and `@Size` do not reject `null`. Required fields need `@NotNull`/`@NotBlank` as appropriate. For a required quantity in `[1,10]`, use `Integer` + `@NotNull @Min(1) @Max(10)`; using primitive `int` can turn an omitted JSON field into `0` instead of distinguishing "missing" from "0".

## 3. JSON Processing Flow and Placement of @Valid

Example:

```java
public record CreateOrderRequest(
    @NotBlank(message = "sku must not be blank")
    String sku,
    @NotNull(message = "quantity required")
    @Min(value = 1, message = "quantity must be >= 1")
    @Max(value = 10, message = "quantity must be <= 10")
    Integer quantity,
    @NotNull(message = "address required")
    @Valid Address address
) {
    public record Address(
        @NotBlank(message = "city required") String city) {}
}
```

If the handler method is:

```java
@PostMapping
ResponseEntity<?> create(@Valid @RequestBody CreateOrderRequest body) {
    // Invoked only when JSON and DTO satisfy constraints.
}
```

This is an explanatory snippet; the complete runnable project is in Section 8.

Main steps:

1. `@RequestBody` asks Spring MVC to read the payload via an `HttpMessageConverter`.
2. Jackson constructs `CreateOrderRequest` and converts JSON values to Java types.
3. If the message cannot be read, Spring can throw `HttpMessageNotReadableException` **before Bean Validation runs**.
4. Once JSON is parsed, `@Valid` instructs the provider to validate constraints on the DTO.
5. If the DTO has field violations and no `Errors`/`BindingResult` immediately follows the parameter, Spring normally throws `MethodArgumentNotValidException` → HTTP 400.
6. Only when valid does the controller call `OrderService`; the controller then constructs the success response.

All of the following requests can produce **400**, but for different reasons:

| Request | Failing Stage | Typical Error |
| --- | --- | --- |
| `{"sku":"   ","quantity":2,"address":{"city":"Huế"}}` | Bean Validation | `@NotBlank` |
| `{"sku":"SKU-1","quantity":0,"address":{"city":"Huế"}}` | Bean Validation | `@Min(1)` |
| `{"sku":"SKU-1","quantity":11,"address":{"city":"Huế"}}` | Bean Validation | `@Max(10)` |
| `{"sku":"SKU-1","address":{"city":"Huế"}}` | Bean Validation | `@NotNull` on quantity |
| `{"sku":"SKU-1","quantity":2,"address":null}` | Bean Validation | `@NotNull` on address |
| `{"sku":"SKU-1","quantity":2,"address":{"city":""}}` | Nested validation | `address.city` |
| `{"sku":"SKU-1","quantity":"many",...}` | Message conversion | `HttpMessageNotReadableException` |
| `{not-json` | JSON syntax | `HttpMessageNotReadableException` |
| Missing body altogether | `@RequestBody(required=true)` | Typically `HttpMessageNotReadableException` |

In these tables, actual HTTP status and error bodies can be customized via `@ControllerAdvice`, Boot/Spring config, or converters. Our sample project defines an explicit response contract so assertions stay stable.

### Nested Validation: @Valid vs. @NotNull

`@Valid Address address` tells the validator to cascade into the object when it exists. If `"address":null` is sent, nested `city` is not validated because there is no object to cascade into. To require `address`, use both `@NotNull` **and** `@Valid`. Similarly, for `List<@Valid LineItem>`, evaluate null lists, empty lists, and individual elements using the appropriate constraints per contract.

## 4. @RequestBody and @ModelAttribute Have Different Binding Pipelines

`@RequestBody` normally reads JSON/XML through message converters. `@ModelAttribute` uses `WebDataBinder` to bind query parameters, form data, path variables, and selected request values into a Java bean/command object.

A form object:

```java
public class OrderForm {
    @NotBlank
    private String sku;

    @NotNull
    @Min(1)
    private Integer quantity;

    public OrderForm() {}
    public String getSku() { return sku; }
    public void setSku(String sku) { this.sku = sku; }
    public Integer getQuantity() { return quantity; }
    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

With `quantity=abc` in a form, the binder tries to convert the `String` into `Integer` and records a `typeMismatch` error. In the controller:

```java
@PostMapping("/form-preview")
ResponseEntity<?> preview(
        @Valid @ModelAttribute OrderForm form,
        BindingResult result) {
    if (result.hasErrors()) {
        return ResponseEntity.badRequest().body(/* error DTO */);
    }
    return ResponseEntity.ok(/* preview */);
}
```

**`BindingResult` placement is critical:** it must appear **immediately after** the bound/validated argument. Putting `Model model`, `HttpServletRequest`, or another parameter in between prevents Spring from associating the error result with the target object. Without `BindingResult`/`Errors`, invalid input throws `MethodArgumentNotValidException`. You can also use `@Valid @RequestBody Dto dto, BindingResult result` for JSON bodies if handling errors directly inside the method.

### What Does BindingResult Contain?

- `hasErrors()`: at least one error (field or global).
- `getFieldErrors()`: field errors; field names can be `quantity` or `address.city`.
- `getGlobalErrors()`: object-level rules such as cross-field constraints.
- `getFieldError("quantity")`: error for a specific field.
- `FieldError.getCode()`: typically codes like `typeMismatch`/`NotNull`/`Min`; codes can be resolved according to configuration.
- `getDefaultMessage()`: default or resolved message per validation settings.

If a controller accepts `BindingResult`, it must **actively** check `hasErrors()` before calling the service. Adding `BindingResult` without checking it silently lets invalid input reach business logic.

### Guarding Against Over-Posting / Mass Assignment

Never bind directly into a JPA entity containing all fields (such as `isAdmin`, `price`, `balance`) from client input. Use dedicated DTOs/forms exposing only permitted fields, or `@InitBinder` with an allowlist via `setAllowedFields(...)` where appropriate. Validation **does not replace** authorization or rules governing who may modify which fields.

## 5. Method Parameter Validation: @Min, @NotBlank, and HandlerMethodValidationException

Since Spring Framework 6.1, Spring MVC includes **built-in method validation**. Constraints placed **directly** on method parameters, such as:

```java
@GetMapping("/estimate")
Estimate estimate(@RequestParam @Min(1) @Max(10) int quantity) {
    return new Estimate(quantity * 100);
}
```

cause `/estimate?quantity=0` to throw `HandlerMethodValidationException` instead of `MethodArgumentNotValidException` from an isolated DTO. In MVC 6.2, when method validation applies, it also covers nested constraints via `@Valid` and can **supersede** argument-resolver-level validation.

Distinctions to keep clear:

| Scenario | Typical Exception |
| --- | --- |
| `@Valid @RequestBody CreateOrderRequest`, without other direct method constraints | `MethodArgumentNotValidException` |
| `@Valid @ModelAttribute OrderForm`, without `BindingResult`, without other method validation | `MethodArgumentNotValidException` |
| `@RequestParam @Min(1) int quantity` | `HandlerMethodValidationException` |
| `@PathVariable long id` when request sends `abc` | `MethodArgumentTypeMismatchException` |
| `@RequestParam int quantity` with missing required query parameter | `MissingServletRequestParameterException` |
| `@Valid @ModelAttribute OrderForm form, BindingResult result` with form errors | Controller reads `BindingResult` and decides response |
| Unreadable JSON | `HttpMessageNotReadableException` |

**Do not reflexively put `@Validated` at the controller class level.** In Spring MVC 6.1+, class-level `@Validated` can trigger method validation via an AOP proxy, altering behavior compared to built-in MVC method validation. To use built-in support and `HandlerMethodValidationException`, Spring documentation recommends omitting class-level `@Validated` on controllers. On service beans, class-level `@Validated` remains common to activate proxy-based method validation where appropriate.

**Watch out for return-value validation:** `HandlerMethodValidationException` for input errors usually maps to HTTP 400; when validation fails on a controller's **return value**, that is a server-side bug and typically maps to HTTP 500. Do not force every exception of this type to 400; use `ex.getStatusCode()` when handling it.

## 6. Designing a Stable Error Response

A convenient JSON response for UIs and tests:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "quantity",
      "message": "quantity must be >= 1"
    }
  ]
}
```

This example intentionally separates error codes at the API layer:

| Code | Meaning | HTTP Status |
| --- | --- | --- |
| `VALIDATION_ERROR` | Bound DTO/form violated constraints | 400 |
| `MALFORMED_BODY` | Unreadable JSON / missing body / wrong type | 400 |
| `METHOD_VALIDATION` | Constraint on controller method parameter/return | Per exception: 400 for input, 500 for return |
| `MISSING_PARAMETER` | Missing required request parameter | 400 |
| `TYPE_MISMATCH` | Path/query value could not be converted | 400 |

This is an **application-defined contract**, not a mandatory Spring Boot default format. Spring supports `ProblemDetail` (RFC 9457) and `ResponseEntityExceptionHandler`, which can substitute a standard problem response if your team adopts that format. Regardless of format, tests should assert **stable error codes, status, and key fields**, not internal exception messages or unspecified error ordering.

### Security in Error Responses

- Do not echo raw JSON, tokens, passwords, or rejected values from `FieldError.getRejectedValue()`.
- Do not expose stack traces, SQL/driver messages, or internal class/package names to clients.
- Do not return raw `HttpMessageNotReadableException.getMessage()`, as it can reveal converter internals and payload fragments.
- Return field names and curated messages; for multilingual APIs, use `MessageSource` with stable error codes and localization.
- Sort errors if the frontend expects deterministic order; multiple constraint violations on one field have no guaranteed default order.
- Never turn every `Exception` into HTTP 400; unexpected server errors must preserve server-error status codes.

## 7. Sample Project Structure

The complete example targets **Spring Boot 3.5.0, Java 17, Maven**, requiring no database, Docker, or external network. `OrderService` is a small bean; when `@WebMvcTest` runs, it is replaced by `@MockitoBean` to prove **invalid input never invokes the service**.

File tree:

```text
mvc-validation-demo/
├── pom.xml
└── src/
    ├── main/java/example/validation/
    │   ├── DemoApplication.java
    │   ├── OrderService.java
    │   ├── CreateOrderRequest.java
    │   ├── OrderForm.java
    │   ├── OrderApiError.java
    │   ├── OrderController.java
    │   └── OrderErrorHandler.java
    └── test/java/example/validation/
        └── OrderControllerTest.java
```

### 7.1. Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>mvc-validation-demo</artifactId>
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
</project>
```

### 7.2. Application and Service

`src/main/java/example/validation/DemoApplication.java`:

```java
package example.validation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`src/main/java/example/validation/OrderService.java`:

```java
package example.validation;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final AtomicLong nextId = new AtomicLong(100);

    public long create(String sku, int quantity, String city) {
        // Demo version: generate ID in memory; no database.
        return nextId.incrementAndGet();
    }
}
```

The real `OrderService` bean can run when the application starts; in the MVC slice test it is mocked. Do **not** mistake the ID increment in the sample service for persistence testing: this lesson intentionally tests only Spring MVC's input/output contract.

### 7.3. JSON DTO with Nested Validation

`src/main/java/example/validation/CreateOrderRequest.java`:

```java
package example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank(message = "sku must not be blank")
        @Size(min = 3, max = 20, message = "sku length must be 3..20")
        String sku,

        @NotNull(message = "quantity required")
        @Min(value = 1, message = "quantity must be >= 1")
        @Max(value = 10, message = "quantity must be <= 10")
        Integer quantity,

        @NotNull(message = "address required")
        @Valid Address address
) {
    public record Address(
            @NotBlank(message = "city required") String city) {
    }
}
```

Record constructors and Java 17 are supported. JSON property names are `sku`, `quantity`, and `address`. `@NotNull` on `address` makes dereferencing `request.address().city()` inside the controller safe once validation passes.

### 7.4. Form DTO

`src/main/java/example/validation/OrderForm.java`:

```java
package example.validation;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderForm {
    @NotBlank(message = "sku must not be blank")
    private String sku;

    @NotNull(message = "quantity required")
    @Min(value = 1, message = "quantity must be >= 1")
    @Max(value = 10, message = "quantity must be <= 10")
    private Integer quantity;

    public OrderForm() {
    }

    public String getSku() {
        return sku;
    }

    public void setSku(String sku) {
        this.sku = sku;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
```

`OrderForm` has a no-arg constructor and setters so Spring binds form parameters cleanly. With `quantity=abc`, conversion fails and `BindingResult` records a field error before any service runs.

### 7.5. Response Contract

`src/main/java/example/validation/OrderApiError.java`:

```java
package example.validation;

import java.util.List;

public record OrderApiError(
        String code,
        List<Violation> errors
) {
    public record Violation(String field, String message) {
    }
}
```

No rejected values or internal exception messages appear in the response. This is an example API contract; in a codebase standardized on `ProblemDetail`, follow the product standard instead of inventing a second format.

### 7.6. Controller

`src/main/java/example/validation/OrderController.java`:

```java
package example.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    public record Created(long id) {}
    public record Estimate(int total) {}
    public record Preview(String sku, Integer quantity) {}

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Created> create(
            @Valid @RequestBody CreateOrderRequest request) {
        long id = service.create(
                request.sku(),
                request.quantity(),
                request.address().city());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(new Created(id));
    }

    // Constraint directly on @RequestParam: MVC method validation.
    @GetMapping("/estimate")
    public Estimate estimate(
            @RequestParam
            @Min(value = 1, message = "quantity must be >= 1")
            @Max(value = 10, message = "quantity must be <= 10")
            int quantity) {
        return new Estimate(quantity * 100);
    }

    // Endpoint illustrating type-conversion error on @PathVariable.
    @GetMapping("/by-id/{id}")
    public Created byId(@PathVariable long id) {
        return new Created(id);
    }

    @PostMapping(
        path = "/form-preview",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> formPreview(
            @Valid @ModelAttribute OrderForm form,
            BindingResult result) {
        // BindingResult MUST immediately follow OrderForm.
        if (result.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(OrderErrorHandler.fromBinding(result));
        }

        return ResponseEntity.ok(
                new Preview(form.getSku(), form.getQuantity()));
    }
}
```

We **omit `@Validated` at the controller class level**, allowing `@RequestParam @Min/@Max` to go through Spring Framework 6.2's built-in MVC method validation. On older Spring versions or projects with custom AOP method validation, verify the actual mechanism before applying.

### 7.7. @RestControllerAdvice Handling Each Error Kind

`src/main/java/example/validation/OrderErrorHandler.java`:

```java
package example.validation;

import java.util.Comparator;
import java.util.List;

import example.validation.OrderApiError.Violation;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class OrderErrorHandler {

    public static OrderApiError fromBinding(BindingResult result) {
        List<Violation> fields = result.getFieldErrors().stream()
                .map(e -> new Violation(
                        e.getField(), e.getDefaultMessage()))
                .sorted(Comparator.comparing(Violation::field))
                .toList();

        return new OrderApiError("VALIDATION_ERROR", fields);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<OrderApiError> invalidDto(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.badRequest()
                .body(fromBinding(ex.getBindingResult()));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<OrderApiError> invalidMethod(
            HandlerMethodValidationException ex) {

        List<Violation> violations = ex.getAllValidationResults().stream()
                .flatMap(p -> p.getResolvableErrors().stream()
                        .map(e -> new Violation(
                                p.getMethodParameter().getParameterName()
                                        != null
                                ? p.getMethodParameter().getParameterName()
                                : "arg" + p.getMethodParameter()
                                        .getParameterIndex(),
                                e.getDefaultMessage())))
                .sorted(Comparator.comparing(Violation::field))
                .toList();

        // Return 400 for input validation, preserve 500 for return validation.
        return ResponseEntity.status(ex.getStatusCode())
                .body(new OrderApiError(
                        "METHOD_VALIDATION", violations));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<OrderApiError> unreadableBody(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.badRequest()
                .body(new OrderApiError(
                        "MALFORMED_BODY",
                        List.of(new Violation(
                                "body", "invalid or missing JSON body"))));
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<OrderApiError> missingQuery(
            MissingServletRequestParameterException ex) {
        return ResponseEntity.badRequest()
                .body(new OrderApiError(
                        "MISSING_PARAMETER",
                        List.of(new Violation(
                                ex.getParameterName(),
                                "required parameter missing"))));
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<OrderApiError> typeMismatch(
            MethodArgumentTypeMismatchException ex) {
        return ResponseEntity.badRequest()
                .body(new OrderApiError(
                        "TYPE_MISMATCH",
                        List.of(new Violation(
                                ex.getName(), "invalid value type"))));
    }
}
```

Technical notes:

- `fromBinding` is shared by both the `MethodArgumentNotValidException` handler and the form endpoint using `BindingResult`; thus JSON and form endpoints return identical field-error shapes.
- When a single field has multiple violations, `Comparator.comparing(Violation::field)` stabilizes order **across fields**, not between two messages on the same field. Tests check `field`/`message` when a single specific constraint is triggered.
- `HandlerMethodValidationException.getStatusCode()` preserves 400 vs. 500 for input vs. return validation.
- The JSON handler never exposes `ex.getMessage()` to clients.
- Do not catch all `Exception` and return 400: system failures or controller bugs must surface as server errors.

`@RestControllerAdvice` is picked up by Spring Boot's MVC slice; for predictability, place it in a package scanned by both the application and test slice. If a project customizes component scanning, `@Import(OrderErrorHandler.class)` in the test can include it explicitly, while avoiding unintended duplicate or out-of-scope imports.

## 8. MockMvc Test Suite for Success, Validation, and Binding Errors

File `src/test/java/example/validation/OrderControllerTest.java`:

```java
package example.validation;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    OrderService service;

    @Test
    void validJsonReturns201AndCallsService() throws Exception {
        when(service.create("SKU-1", 2, "Ha Noi")).thenReturn(101L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":2,
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(101));

        verify(service).create("SKU-1", 2, "Ha Noi");
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 10})
    void boundariesOneAndTenAreAccepted(int quantity)
            throws Exception {
        when(service.create("SKU-1", quantity, "Ha Noi"))
                .thenReturn(102L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":%d,
                         "address":{"city":"Ha Noi"}}
                        """.formatted(quantity)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(102));

        verify(service).create("SKU-1", quantity, "Ha Noi");
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 11})
    void outOfRangeQuantityIsRejectedBeforeService(int quantity)
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":%d,
                         "address":{"city":"Ha Noi"}}
                        """.formatted(quantity)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void blankSkuIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"   ","quantity":2,
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("sku must not be blank"));

        verifyNoInteractions(service);
    }

    @Test
    void skuTooLongIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"ABCDEFGHIJKLMNOPQRSTU",
                         "quantity":2,"address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("sku length must be 3..20"));

        verifyNoInteractions(service);
    }

    @Test
    void missingQuantityIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1",
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("quantity required"));

        verifyNoInteractions(service);
    }

    @Test
    void missingAddressIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":2}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("address required"));

        verifyNoInteractions(service);
    }

    @Test
    void nestedCityValidationIsApplied() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":2,
                         "address":{"city":""}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address.city"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("city required"));

        verifyNoInteractions(service);
    }

    @Test
    void malformedJsonIsRejectedBeforeService() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{not-json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));

        verifyNoInteractions(service);
    }

    @Test
    void incompatibleJsonTypeIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-1","quantity":"many",
                         "address":{"city":"Ha Noi"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));

        verifyNoInteractions(service);
    }

    @Test
    void missingRequiredJsonBodyReturns400() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_BODY"));

        verifyNoInteractions(service);
    }

    @Test
    void missingQueryParameterReturns400() throws Exception {
        mvc.perform(get("/api/orders/estimate"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MISSING_PARAMETER"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void directConstraintOnQueryParameterUsesMethodValidation()
            throws Exception {
        mvc.perform(get("/api/orders/estimate")
                    .param("quantity", "0"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("METHOD_VALIDATION"));

        verifyNoInteractions(service);
    }

    @Test
    void pathVariableWrongTypeReturns400() throws Exception {
        mvc.perform(get("/api/orders/by-id/not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("TYPE_MISMATCH"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("id"));

        verifyNoInteractions(service);
    }

    @Test
    void formTypeConversionErrorIsHandledByBindingResult()
            throws Exception {
        mvc.perform(post("/api/orders/form-preview")
                    .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                    .param("sku", "SKU-1")
                    .param("quantity", "not-a-number"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void validFormReturnsPreviewWithoutServiceCall()
            throws Exception {
        mvc.perform(post("/api/orders/form-preview")
                    .contentType(
                        MediaType.APPLICATION_FORM_URLENCODED)
                    .param("sku", "SKU-1")
                    .param("quantity", "2"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("SKU-1"))
                .andExpect(jsonPath("$.quantity").value(2));

        verifyNoInteractions(service);
    }
}
```

These tests form a practical class with zero database dependencies. They exercise **MockMvc through real Spring MVC request binding**, rather than invoking controller methods directly in Java. `@MockitoBean` overrides the service bean in the MVC slice context. Mockito state is reset between tests by Spring test infrastructure defaults, preventing one stub from polluting other methods.

Assertions avoid matching the entire `errors` array order when multiple violations occur. When an input violates a single constraint, `errors[0]` is clear enough. When testing multiple invalid fields simultaneously, use JSONPath checks verifying the presence of each expected field and message without asserting an uncontracted order.

### What Must Not Be Inferred from the MVC Slice

- Does not prove database writes succeed: the service is mocked.
- Does not prove `@Transactional` on the service works.
- Does not prove real network connections, TLS, or API gateways.
- Does not prove authorization if the application has no active security policy/filters.
- Does not prove validation runs on a DTO if the controller **forgot `@Valid`**: tests in that case will catch the service being invoked or the status no longer being 400.

If you need to test controller + service + DB together, use `@SpringBootTest` and `@AutoConfigureMockMvc` with a proper test database/cleanup; do not force `@WebMvcTest` to load all repositories just to verify persistence.

## 9. Expected Results and How to Run

From the directory containing `pom.xml`:

```bash
mvn test
```

Or run just the test class:

```bash
mvn test -Dtest=OrderControllerTest
```

The sample includes **16 test methods**: 14 `@Test` methods and 2 `@ParameterizedTest` methods. Since each parameterized test executes two inputs, total invocations are **18 test invocations**. Expected result is **18 PASS, 0 FAILED, 0 SKIPPED** given JDK 17+, dependencies, and a compatible build. The code does not print with `System.out.println`, so there is no fixed application stdout; Maven Surefire writes reports to `target/surefire-reports`.

### Verification Matrix

| Category | Sample Request | Expected HTTP/JSON | Service Called? |
| --- | --- | --- | --- |
| Success | POST SKU-1, quantity=2, city=Ha Noi | 201, id=101 | Yes, once |
| Min/max boundaries | quantity=1/10 | 201 | Yes |
| Out of bounds | quantity=0/11 | 400, VALIDATION_ERROR, field quantity | No |
| Whitespace SKU | `"sku":"   "` | 400, field sku | No |
| SKU > 20 chars | 21 chars | 400, field sku | No |
| Missing quantity | Omitted quantity | 400, field quantity | No |
| Missing address | Omitted address | 400, field address | No |
| Empty nested city | `"address":{"city":""}` | 400, field address.city | No |
| Malformed JSON | `{not-json` | 400, MALFORMED_BODY | No |
| Wrong JSON type for quantity | `"many"` | 400, MALFORMED_BODY | No |
| Missing JSON body | POST with no body | 400, MALFORMED_BODY | No |
| Missing query | GET estimate without quantity | 400, MISSING_PARAMETER | No |
| Query violates @Min | quantity=0 | 400, METHOD_VALIDATION | No |
| Wrong path type | /by-id/not-a-number | 400, TYPE_MISMATCH | No |
| Form type mismatch | quantity=not-a-number | 400, field quantity | No |
| Valid form | sku=SKU-1, quantity=2 | 200, preview | No (preview has no service call) |

An important goal is **catching regressions in validation and request binding**. Changing `@Min(1)` to `@Min(0)` must cause the `quantity=0` case to FAIL. Removing `@Valid` from the request body must make the invalid tests FAIL because the mock service gets called or the response is no longer 400.

## 10. @Validated, Validation Groups, and When to Use Them

`@Valid` is the standard Jakarta Validation annotation that triggers object validation and cascading. `@Validated` is Spring's annotation, which besides triggering validation can also select validation groups.

Conceptual example:

```java
public interface CreateGroup {}
public interface UpdateGroup {}

public record UserInput(
    @NotBlank(groups = CreateGroup.class)
    String initialPassword,

    @NotBlank(groups = UpdateGroup.class)
    String currentPassword
) {}

@PostMapping("/users")
public void create(@Validated(CreateGroup.class)
                   @RequestBody UserInput request) {
    // Validates the CreateGroup group.
}
```

This is a **snippet** without full imports/controller/service. Groups allow reusing a DTO with differing rules, though you should not overuse them when create and update genuinely have distinct contracts: two separate DTOs are usually clearer and safer.

Further distinctions:

- `@Validated` on a **service class** typically enables proxy-based method validation (when provider/config supports it).
- `@Validated` on a **controller class** can route method validation through an AOP proxy rather than the MVC 6.1+ mechanism; to use `HandlerMethodValidationException` per MVC docs, omit class-level `@Validated`.
- When a controller method has `@Min`/`@NotBlank` directly on parameters, built-in method validation applies even without `@Validated` on the class.
- `@Valid` itself **is not a constraint**, so `@Valid` alone does not trigger built-in method validation on all parameter types; it generally signals object validation at the resolver stage when no other method constraints exist.

## 11. Tricky Cases: Collections, Null, Cross-Field, and Data Formats

### Collections

Do not assume `@Valid List<OrderItem>` without container constraints will behave across all variants identically to a standard command object. When the request is a top-level JSON array, a cleaner option is a wrapper DTO:

```java
public record BatchRequest(
    @NotEmpty
    java.util.List<@Valid Item> items
) {}

public record Item(@NotBlank String sku) {}
```

This is a **snippet** requiring the appropriate Jakarta Validation imports. A wrapper gives you a standard command-object validation path while also letting you cap batch size and attach request-level custom constraints.

### Cross-Field Validation

If a rule says "end date must follow start date" or "token is required when paying by card," a single `@NotBlank` on an individual field is not enough. You can write a custom class-level constraint + `ConstraintValidator` or enforce it via domain/service validation; either way, test both valid and invalid combinations. Cross-field violations can produce object/global errors rather than field errors; if the API expects a field mapping, the validator must build an appropriate property node.

**Note on the sample error handler:** `fromBinding` currently returns only `getFieldErrors()` to stay concise, so a class-level/global error would yield `errors=[]`. In production, also map `getGlobalErrors()` with a location such as `"_object"` and a stable code/message if you use class-level constraints. For the JSON/form field errors in this lesson, it satisfies the defined matrix.

### Null and Strings

- `@NotNull` does not forbid `""` or `"   "`.
- `@NotBlank` forbids null and whitespace-only strings.
- `@Size(min=3)` does not forbid null by default.
- `@NotNull @Valid Nested` both requires the object and validates its inner constraints.
- Use `Integer` when you must distinguish an **omitted** numeric field from `0`.

### Conversion and Binding Errors

- Form `quantity=abc`: the binder fails to convert `Integer` and stores a field error in `BindingResult` when the controller declares an adjacent parameter.
- JSON `"quantity":"abc"`: Jackson fails to deserialize `Integer`, raising `HttpMessageNotReadableException` before validation.
- Query `?quantity=abc` with `@RequestParam int quantity`: typically `MethodArgumentTypeMismatchException`, not `MethodArgumentNotValidException`.
- Missing query with required `@RequestParam`: typically `MissingServletRequestParameterException`.
- Multipart/form-data `@RequestPart` follows part-specific binding/validation rules; test multipart separately if endpoints handle uploads.

Never "fix" parse failures by catching them generically and defaulting to `0`; that risks silently accepting corrupt data and invoking business logic wrongly.

## 12. ProblemDetail and ResponseEntityExceptionHandler

Spring Framework 6.x supports `ProblemDetail` to emit error responses following Problem Details (RFC 9457), featuring status/title/detail/instance and extension properties. If your API team uses this format, you can extend `ResponseEntityExceptionHandler` to customize MVC errors:

```java
@RestControllerAdvice
class StandardProblemHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {
        ProblemDetail body = ProblemDetail.forStatus(status);
        body.setTitle("Validation failed");
        return handleExceptionInternal(
                ex, body, headers, status, request);
    }
}
```

This is a **snippet requiring imports**; do not add it into the sample project alongside `OrderErrorHandler`, which would create two exception advices and obscure the contract. In Spring Framework 6.2, overridden methods receive `HttpHeaders`, `HttpStatusCode`, and `WebRequest` as shown; verify signatures when upgrading major versions.

If you **already extend `ResponseEntityExceptionHandler`**, do not declare a separate `@ExceptionHandler(MethodArgumentNotValidException.class)` in the same class, which would conflict with the inherited handler. Pick either **overriding the protected hook** or **standalone `@ExceptionHandler`** as in the sample project—do not mix both redundantly.

## 13. Checking Additional Response Statuses and Security

Usually invalid client input returns HTTP 400, yet **not every request error is 400**:

| Scenario | Typical Appropriate Code | Rule |
| --- | --- | --- |
| Invalid JSON, missing required body, type mismatch | 400 | Client must fix the request |
| DTO Bean Validation failure | 400 | Do not invoke business logic |
| Missing authentication | 401 | Decided by Spring Security/API contract |
| Missing permission | 403 | Do not turn into validation 400 |
| Unsupported `Content-Type` | 415 | Do not catch generically as 400 |
| Unsupported HTTP method | 405 | Preserve method contract |
| Resource does not exist | 404 | Do not confuse with invalid ID format |
| Business conflict, e.g. SKU out of stock | 409 or defined domain code | Business rule, not just Bean Validation |
| Return-value validation failure | Usually 500 | Server bug / internal contract violation |
| Unhandled DB/remote error | Appropriate 5xx | Do not mask with `@ExceptionHandler(Exception.class)` returning 400 |

Not every 400 response comes from Bean Validation. When writing tests for `@Valid`, assert specific fields/codes; asserting only 400 would allow wrong `Content-Type` or malformed JSON requests to PASS without the validator ever running.

With Spring Security, POST requests in MockMvc can be blocked by CSRF or authentication before validation. When testing with Spring Security, use legitimate test utilities such as `spring-security-test`, `@WithMockUser`, and CSRF request post-processors per project policy. Never disable security filters to make a validation test pass and then cite it as proof the endpoint is secure.

## 14. Common Mistakes and How to Fix Them

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| `@Valid` has no effect | Missing provider or missing `@Valid` on controller parameter | Add validation starter; check annotations/imports |
| Missing DTO `quantity` still accepted | Primitive `int` used or `@NotNull` missing | Use `Integer` + `@NotNull` for required fields |
| Nested object not validated | Missing `@Valid` on field; `null` is not blocked by `@Valid` | Add `@Valid` + `@NotNull` per contract |
| Form `quantity=abc` throws no exception as expected | Controller has adjacent `BindingResult` capturing errors locally | Check `result.hasErrors()` and return 400 |
| `BindingResult` does not work | Placed after another parameter or wrong argument | Place immediately after the validated form/body |
| `HandlerMethodValidationException` thrown instead of `MethodArgumentNotValidException` | Direct constraints on parameters or method validation applies | Handle both exception types |
| Controller `@Validated` alters behavior | Method validation routed via AOP proxy | Remove class-level `@Validated` to use built-in MVC validation |
| Wrong JSON type returns 400 without field details | Jackson error happened before Bean Validation | Return `MALFORMED_BODY` code and safe message |
| `@Size` on empty string behaves unexpectedly | `@Size` does not replace `@NotBlank` | Pick the right constraint and test null/empty/whitespace |
| Unexpected message text | Message interpolation, locale, or bundle differences | Use stable error codes; assert messages only when contracted |
| Tests flake due to `FieldError` order | Multiple violations on one field have unspecified order | Do not assert order unless API explicitly sorts |
| `@WebMvcTest` cannot find service | Slice does not scan regular services | Use `@MockitoBean` or `@Import` within intended scope |
| Advice not applied | Component scan/slice filter differs from expectation | Check `@RestControllerAdvice` package/import |
| Every invalid input becomes 500 | Missing validator or exception mapping, or misrouted handler | Inspect resolved exception in MockMvc and add proper handlers |
| Test calls controller method directly | Bypasses `HttpMessageConverter` and MVC binding | Send real requests via MockMvc |
| Password values leak in errors | Echoing rejected values or raw exception messages | Never return `getRejectedValue()` or stack traces |
| Boot 4 `@WebMvcTest` import error | Test module layout changed | Use focused starter and Boot 4 package names |

## 15. Extended Exercises

1. **Multiple errors in one request:** send blank SKU and quantity 0, verifying the response contains **both field names** without relying on default ordering.
2. **Global error:** add a custom class-level constraint relating SKU and quantity; extend the handler to cover `getGlobalErrors()`.
3. **Validation groups:** create Create vs. Update contracts; compare two separate DTOs against `@Validated(Group.class)`.
4. **JSON null vs. missing:** test both cases and ensure responses stay deterministic.
5. **Invalid numeric query:** add a test for `/estimate?quantity=abc` to contrast type mismatch with range constraints.
6. **Nested collection:** add `List<@Valid Item>` with `@NotEmpty` and check error paths containing element indices.
7. **Content-Type:** send JSON with `text/plain` and verify 415 rather than 400 validation.
8. **Locale:** if using message bundles, test `Accept-Language` and confirm error codes remain locale-independent.
9. **Security:** integrate `spring-security-test` and verify 401/403 are not turned into 400 by validation handlers.
10. **Integration:** use `@SpringBootTest + @AutoConfigureMockMvc` with the real service to verify valid requests cause exact side effects while invalid requests write nothing.

When doing these exercises, separate **validation rule tests** from **service business tests**. Validation must never substitute for domain authorization, inventory consistency, or transactional invariants.

## 16. Acceptance Checklist

- [ ] Does the project include `spring-boot-starter-validation` / a provider compatible with the Boot version?
- [ ] Are imports `jakarta.validation.*` for Boot 3/4?
- [ ] Is `@Valid` placed on controller DTOs requiring validation, and also on nested fields?
- [ ] Do required fields use `@NotNull`/`@NotBlank` rather than relying solely on `@Min`/`@Size`?
- [ ] Are tests covering just below, at, and just above `[1,10]`?
- [ ] Are malformed JSON, type errors, missing bodies, and DTO constraint violations distinguished?
- [ ] Does `@ModelAttribute` form handling place `BindingResult` immediately after the argument and check `hasErrors()`?
- [ ] Are both `MethodArgumentNotValidException` and `HandlerMethodValidationException` tested?
- [ ] Do direct parameter constraints run via MVC built-in validation without unintended class-level AOP `@Validated` interference?
- [ ] Does controller advice return stable status, code, and fields without leaking rejected values?
- [ ] Does the error handler avoid collapsing all exceptions into 400?
- [ ] Do MockMvc tests assert both responses and `verifyNoInteractions(service)` on invalid cases?
- [ ] Do tests avoid confusing MVC slices with persistence or HTTP transport integration?
- [ ] Do error messages/localization match the API contract without depending on nondeterministic order?
- [ ] When upgrading Spring Boot, were test starters, exception APIs, and imports verified?

## 17. Official References

1. [Spring Framework 6.2 — Controller Method Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` vs. `HandlerMethodValidationException`, `@Valid`, and direct constraints.
2. [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): JSON conversion, `@Valid`, `BindingResult`.
3. [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): data binding, conversion errors, and local `BindingResult`.
4. [Spring Framework — Web MVC Validator](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html): configuring global/local `Validator`.
5. [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html): `ProblemDetail`/`ResponseEntityExceptionHandler`.
6. [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html): provider and `@Validated` for service methods.
7. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, MockMvc, and bean mocking.
8. [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): constraints, nested validation, groups, and validators.
9. [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/): updated test module structure if using Boot 4.

### Spring Boot 4 Note

Spring Boot 4 uses technology-focused test starters; for Spring MVC, check `spring-boot-starter-webmvc-test` and the new package for `@WebMvcTest`. The sample project above **targets 3.5.x**; do not change only the version number while keeping old imports. Jakarta Validation logic and error-classification principles remain foundational, but always verify official documentation for your exact version.

**Remember:** Bean Validation answers **"are the Java values valid?"**; binding/conversion answers **"can the request produce Java values?"**; controller advice determines **"how does the client receive safe, stable error notifications?"** MockMvc must test all three, along with **not invoking business logic** on invalid input.