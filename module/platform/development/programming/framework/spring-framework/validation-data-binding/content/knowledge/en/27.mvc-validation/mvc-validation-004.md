# Direct Constraints on Controller Parameters in Spring MVC

## 1. From data binding to method parameter validation

A handler in Spring MVC can receive data from URLs, query strings, HTTP headers, cookies, or request bodies. Besides converting data into Java types, applications often need to check basic business conditions such as:

- An identifier from the path must be a positive number.
- The `page` parameter must be greater than or equal to 1.
- `limit` must fall within an allowed range.
- A search keyword must not be empty or whitespace-only.
- An HTTP header that is optional at the binding layer yet required by Bean Validation rules must have content.

In Spring Framework 6.1 and later, you can attach **Jakarta Bean Validation constraints directly to controller method parameters**:

```java
@GetMapping("/products/{id}")
public String find(
        @PathVariable("id") @Positive long id,
        @RequestParam("page") @Min(1) int page,
        @RequestParam("keyword") @NotBlank String keyword) {

    return "id=" + id + ",page=" + page + ",keyword=" + keyword;
}
```

This is an illustrative handler signature snippet; a complete runnable application is in section 5. Annotations like `@Positive`, `@Min`, and `@NotBlank` **directly on method parameters** are *direct constraints*. They differ from placing `@NotBlank` on a DTO field and marking the DTO with `@Valid`.

**Core point:** Spring MVC 6.1+ has a **built-in method validation** mechanism for controllers. When there are direct constraints on parameters or on the handler's return value, Spring can validate the entire method contract without needing class-level `@Validated` to create an AOP proxy.

## 2. Distinguishing three annotation roles

Do not treat every annotation in a controller signature as doing the same thing:

| Annotation | Role |
| --- | --- |
| `@PathVariable` | Extracts a segment from the URL path and converts it to a Java type |
| `@RequestParam` | Extracts a request parameter from query/form and converts its type |
| `@RequestHeader` | Extracts an HTTP header value |
| `@CookieValue` | Extracts a cookie value |
| `@RequestBody` | Uses an HTTP message converter to read the body into an object |
| `@Min(1)`, `@Positive`, `@NotBlank`, `@Pattern`, ... | **Direct** constraint on the parameter value |
| `@Valid` | Cascade marker to validate constraints **inside** an object |
| `@Validated` (Spring) | Selects validation groups; class-level `@Validated` on a bean is usually a marker for AOP method validation |

Example:

```java
@RequestParam("page") @Min(1) int page
```

`@RequestParam` handles **extracting and converting** `page`; `@Min(1)` checks whether the **converted integer value** meets the minimum threshold.

A plain `@RequestParam("page") int page` does not implicitly force the page to be greater than 0. Conversely, writing only `@Min(1) int page` without understanding how the argument resolver obtains the value does not ensure the data comes from the intended API source. Combining the data-extraction annotation with the appropriate constraint makes the contract clear.

## 3. When does Spring MVC trigger method validation?

The Spring Framework 6.1/6.2 documentation distinguishes two main validation paths.

### 3.1. Validating an individual command object

If a `@ModelAttribute`, `@RequestBody`, or `@RequestPart` parameter representing a command object is marked `@Valid` or `@Validated`, and the method **does not** have conditions that enable whole-method validation, Spring normally validates that object on its own.

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody CreateOrderRequest body) {
    // CreateOrderRequest contains constraints on its fields.
}
```

This illustrative snippet requires the DTO and imports when integrated. When the object is readable yet violates constraints, without an immediately following `Errors`/`BindingResult`, the error is typically `MethodArgumentNotValidException`. Form objects and request parts follow similar dedicated rules.

### 3.2. Method validation triggered by direct constraints

When you declare a constraint directly on **a parameter** or **return value**:

```java
@GetMapping("/orders")
public String list(@RequestParam("page") @Min(1) int page) {
    return "page=" + page;
}
```

Spring MVC applies method validation to the entire handler. This mechanism can also validate nested constraints through `@Valid` on other command objects in the same signature. If validation fails without suitable local error handling, MVC throws:

```java
org.springframework.web.method.annotation.HandlerMethodValidationException
```

Errors on **input parameters** have a default HTTP status of **400 Bad Request**; validation errors on **return values** have a status of **500 Internal Server Error**, because those typically represent a server-side contract bug.

`@Valid` **is not** a direct constraint. Therefore, `@Valid` on a DTO alone does not automatically trigger method validation in every case. By contrast, `@NotNull @Valid` on the same parameter has `@NotNull` as a direct constraint and can cause whole-method validation to apply.

### 3.3. Spring MVC 6.1+ differs from AOP service method validation

A service bean typically uses class-level `@Validated` and `MethodValidationPostProcessor` to validate methods through a Spring AOP proxy. However, **for Spring MVC 6.1+ controllers**, the documentation recommends **removing class-level `@Validated`** if you want to use built-in method validation.

- Built-in MVC controller validation: typically produces `HandlerMethodValidationException`.
- Spring AOP method validation: depending on configuration, typically produces `ConstraintViolationException` or `MethodValidationException`.
- Both can rely on the same Jakarta Bean Validation provider, yet pass through different infrastructure and exception types.

Do not add `@Validated` to every `@RestController` out of habit from older versions and assume the behavior stays identical. That is a common reason `@ControllerAdvice` catches the wrong exception type.

## 4. Choosing the right constraint for each value type

| Input | Common constraint | Meaning and notes |
| --- | --- | --- |
| `int page` | `@Min(1)` or `@Positive` | Page must be 1 or higher |
| `int limit` | `@Min(1) @Max(100)` | Rejects values outside the range |
| `long id` | `@Positive` | Strictly positive numbers only |
| `String keyword` | `@NotBlank` | Not `null`, not empty, not whitespace-only |
| `String code` | `@Pattern(regexp = "...")` | Must match the regular expression; `null` is allowed unless another constraint is added |
| `String email` | `@Email` + `@NotBlank` when required | Checking email syntax and requiring presence are two separate things |
| `Integer quantity` | `@NotNull @Min(1)` | Rejects both missing values and small numbers |
| `List<String> tags` | `@NotEmpty`, `@Size(max=...)` | Collection constraints; elements may need separate constraints |
| Return value `String` | `@NotBlank` on method | Postcondition check after the handler runs |

Some differences that are easy to overlook:

- `@Min`, `@Max`, `@Positive`, and `@Pattern` **typically treat `null` as valid**. To disallow `null`, combine them with `@NotNull` or another suitable annotation.
- `@NotBlank` is for `CharSequence`; do not use it on `Integer` or `List<?>`. For collections, use `@NotEmpty`/`@Size`.
- `@Pattern` matches the entire value against a regex; for example, a code `"PRD-123"` can use `@Pattern(regexp="PRD-[0-9]{3}")`.
- Constraints are evaluated **only after** the argument resolver/converter produces a Java argument. If Spring cannot convert `"abc"` to `int`, a type conversion error occurs before `@Min` ever gets evaluated.
- A `@NotNull` annotation alone does not make an HTTP parameter "required": `@RequestParam` defaults to `required=true`, and missing parameters follow a separate error path.

**Avoid over-validation:** for instance, `@Size(min=1)` on a string still allows a string of spaces; choose `@NotBlank` if the goal is actual non-whitespace content.

## 5. Complete runnable example with Java 17 and Spring Boot 3.5.6

The following example demonstrates three practical scenarios:

1. Direct constraints on path variables, query parameters, and headers.
2. A missing header caught by `@NotBlank` even though the header is optional at the binding layer.
3. A constraint on the handler's return value.

The program uses **Spring Boot 3.5.6**, Java 17+, and Maven 3.x; no database is needed. It omits class-level `@Validated` on the controller so that **Spring MVC's built-in method validation** is used.

### 5.1. Project structure

```text
controller-direct-validation/
├── pom.xml
└── src/main/java/demo/
    ├── DirectValidationApplication.java
    ├── TicketController.java
    └── ValidationErrorHandler.java
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
    <version>3.5.6</version>
    <relativePath/>
  </parent>

  <groupId>demo</groupId>
  <artifactId>controller-direct-validation</artifactId>
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

`spring-boot-starter-web` provides Spring MVC and the embedded server; `spring-boot-starter-validation` provides the Bean Validation provider (Hibernate Validator via the starter).

### 5.3. DirectValidationApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DirectValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(DirectValidationApplication.class, args);
    }
}
```

### 5.4. TicketController.java

```java
package demo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TicketController {

    @GetMapping("/tickets/{ticketId}")
    public String ticket(
            @PathVariable("ticketId") @Positive long ticketId,
            @RequestParam("count") @Min(1) @Max(10) int count,
            @RequestHeader(value = "X-Client", required = false)
                    @NotBlank String client) {

        return "OK:" + ticketId + ":" + count + ":" + client;
    }

    @GetMapping("/broken")
    @NotBlank
    public String broken() {
        // Intentionally violate the return value constraint.
        return "";
    }
}
```

Analyzing the `ticket` signature:

- `@PathVariable("ticketId")` resolves the data source; `@Positive` requires an ID greater than 0.
- `@RequestParam("count")` reads the query parameter and converts it to `int`, while `@Min(1) @Max(10)` checks the allowed range.
- `@RequestHeader(value="X-Client", required=false)` lets Spring pass `null` if the header is absent at the **request resolution step**. Yet `@NotBlank` still forbids `null`/empty/whitespace-only strings at the **validation step**. This intentionally separates the argument resolver's requirement from the constraint.
- `@NotBlank` on `broken()` is at the **method level**, meaning it validates the returned `String`. The method body has already executed before this constraint is evaluated.
- **There is no `@Validated` on the class**, because we want Spring 6.1+'s built-in MVC mechanism.

### 5.5. ValidationErrorHandler.java

```java
package demo;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ValidationErrorHandler {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<String> handle(HandlerMethodValidationException ex) {

        return ResponseEntity.status(ex.getStatusCode())
            .body(ex.isForReturnValue()
                ? "INVALID_RETURN"
                : "INVALID_INPUT");
    }
}
```

This handler intentionally returns a **fixed body** for easy testing. `ex.getStatusCode()` keeps the corresponding HTTP status chosen by Spring: 400 for input errors, 500 for return-value errors. In real APIs, you can convert errors into JSON with a code, location, safe message, and correlation ID. Never return the raw exception object or rejected values to a public API.

### 5.6. Running commands

In the directory containing `pom.xml`:

```bash
mvn -q spring-boot:run
```

The server listens on `localhost:8080` under default configuration if the port is free. Open another terminal (bash, zsh, or WSL) to run the requests below.

**Case A — all parameters valid:**

```bash
curl -s -X GET 'http://localhost:8080/tickets/8?count=3' \
  -H 'X-Client: demo'
```

HTTP status: **200 OK**. Exact body:

```text
OK:8:3:demo
```

**Case B — two direct constraints invalid at once:**

```bash
curl -s -X GET 'http://localhost:8080/tickets/0?count=0' \
  -H 'X-Client: demo'
```

`ticketId=0` violates `@Positive` and `count=0` violates `@Min(1)`. Spring MVC throws `HandlerMethodValidationException` before invoking the `ticket` body. The handler returns **400 Bad Request** and body:

```text
INVALID_INPUT
```

**Case C — missing header that the binding layer allows to be absent:**

```bash
curl -s -X GET 'http://localhost:8080/tickets/8?count=3'
```

Because of `required=false`, Spring can pass `client=null`. `@NotBlank` considers `null` invalid. The handler returns **400 Bad Request** and body:

```text
INVALID_INPUT
```

**Case D — return value constraint violation:**

```bash
curl -s -X GET 'http://localhost:8080/broken'
```

`broken()` is invoked and returns `""`; the `@NotBlank` postcondition is violated. `HandlerMethodValidationException#isForReturnValue()` is `true`. The handler returns **500 Internal Server Error** and body:

```text
INVALID_RETURN
```

**Case E — value cannot be converted to int:**

```bash
curl -i -X GET 'http://localhost:8080/tickets/8?count=abc' \
  -H 'X-Client: demo'
```

The failure to convert `"abc"` into `int` happens during **argument resolution/type conversion**. It is not a `@Min` or `@Max` violation; the framework normally uses `MethodArgumentTypeMismatchException` and returns HTTP 400 via default error handling. **Do not expect the `INVALID_INPUT` body from a handler that only catches `HandlerMethodValidationException`.** The actual body in the conversion branch depends on Spring Boot configuration and the application's handlers.

Similarly, omitting the `count` query parameter altogether with `@RequestParam`'s default `required=true` usually causes `MissingServletRequestParameterException` before Bean Validation. Do not conflate *not receiving an argument* with a *constraint violation on a received argument*.

The `text` blocks above show the body returned by the application. `curl -s` does not append a newline on its own; response headers, Spring/Maven logs, or default error responses are outside the shown body.

## 6. Missing parameter errors, conversion errors, and constraint errors

An API such as `GET /tickets/{id}?count=...` has at least three distinct checking layers:

| Scenario | Processing layer | Typical exception |
| --- | --- | --- |
| Missing `@RequestParam(required=true)` | Request parameter resolution | `MissingServletRequestParameterException` |
| `count=abc` when parameter is `int` | Type conversion | `MethodArgumentTypeMismatchException` |
| `count=0`, converts to `int` but violates `@Min(1)` | Built-in method validation | `HandlerMethodValidationException` |
| `@Valid @RequestBody DTO` parses fine yet has invalid field, no other direct constraints | Single-object validation | `MethodArgumentNotValidException` |
| Malformed JSON body | HTTP message conversion | `HttpMessageNotReadableException` |
| Return value violates `@NotBlank` | Built-in method validation after handler runs | `HandlerMethodValidationException`, status 500 |

These are **typical cases in Spring MVC 6.1+/Boot 3.x**, not an assertion that every version, signature, or configuration produces the exact same exception. Custom resolvers, group validation, AOP, or `@ControllerAdvice` can alter the handling path.

### When is @NotNull needed if @RequestParam has required?

- `@RequestParam(required=true)` checks **whether a request parameter value exists to resolve**. When missing, Spring can throw an exception before validation.
- `@NotNull` is a **Jakarta Validation constraint** on the resolved Java value. It catches `null` in situations where the argument is allowed to receive `null`.
- `@NotBlank` additionally requires a `String` to contain non-whitespace characters.

If you want separate control over how "missing" errors and "blank" errors are returned, define the API contract clearly and handle both paths rather than arbitrarily setting every param to `required=false` just to force them into method validation.

## 7. Direct constraints and @Valid on a DTO can coexist

Suppose we have an endpoint:

```java
@PostMapping("/purchases")
public ResponseEntity<Void> purchase(
        @Valid @RequestBody PurchaseRequest body,
        @RequestParam("priority") @Min(1) int priority) {

    // ...
    return ResponseEntity.noContent().build();
}
```

This is an illustrative integration snippet; `PurchaseRequest` and imports must be declared. Because `priority` has a direct constraint, Spring MVC can apply **method validation to the whole method**, including cascading into `PurchaseRequest` via `@Valid`.

If you only have:

```java
@PostMapping("/purchases")
public ResponseEntity<Void> purchase(
        @Valid @RequestBody PurchaseRequest body) {

    // ...
    return ResponseEntity.noContent().build();
}
```

then in the normal case, the framework applies **argument-level validation** to the DTO and can throw `MethodArgumentNotValidException` when fields are invalid. The two signatures differ only by one parameter having `@Min`, yet can trigger **different exception types** — which is why controller advice must support both.

If you add `@NotNull` directly to the DTO parameter itself:

```java
@NotNull @Valid @RequestBody PurchaseRequest body
```

then `@NotNull` is a direct constraint, while `@Valid` is a cascade marker. Still, missing or unreadable request body errors can occur in the converter/resolver before validation. `@NotNull` does not replace `@RequestBody(required=true)` or HTTP message conversion error handling.

## 8. BindingResult and Errors in the same handler

With a form object, placing `BindingResult` or `Errors` **immediately after the bound/validated parameter** lets the controller handle eligible errors in place:

```java
@PostMapping("/register")
public String register(
        @Valid @ModelAttribute("form") RegisterForm form,
        BindingResult formErrors,
        @RequestParam("page") @Min(1) int page) {

    // ...
    return "result";
}
```

This is an illustrative snippet, not a standalone program. When method validation applies, Spring MVC documentation specifies that **the handler is invoked only if all validation errors belong to method parameters that have an `Errors` parameter immediately following them**. Thus:

- If only `form` has errors and `formErrors` captures all errors for the form, the handler can run and decide the view/status itself.
- If `page=0` violates `@Min(1)`, in the signature above there is no `Errors` attached after `page` in command-object style, so `HandlerMethodValidationException` can be thrown and the handler does not run.
- If you place `Model` or another parameter between `form` and `formErrors`, the pair no longer follows Spring MVC's contract.

Do not use `BindingResult` to "catch every constraint" on the whole method. It is tied to the binding/validation result of one specific object. When you want to standardize errors across all method-level parameters, use `HandlerMethodValidationException` and its APIs.

## 9. Reading HandlerMethodValidationException per parameter

`HandlerMethodValidationException` implements `MethodValidationResult`, providing **structured** information rather than requiring message-text parsing.

Key APIs to know:

| API | Purpose |
| --- | --- |
| `ex.getStatusCode()` | HTTP status for input or return-value error |
| `ex.isForReturnValue()` | `true` if a postcondition on the return value was violated |
| `ex.getMethod()` | The method being validated |
| `ex.getParameterValidationResults()` | Validation results per parameter/return value |
| `ex.getAllErrors()` | Errors as `MessageSourceResolvable` |
| `result.getMethodParameter()` | Parameter metadata and index |
| `result.getResolvableErrors()` | List of errors associated with that result |
| `result.getArgument()` | Argument value; handle carefully with sensitive data |
| `result.getContainerIndex()/getContainerKey()` | Collection/map element info, if applicable |

Supplementary example for an `@ExceptionHandler`, **not a standalone program**:

```java
// Required imports: MessageSourceResolvable,
// ParameterValidationResult, HandlerMethodValidationException.
for (ParameterValidationResult result
        : ex.getParameterValidationResults()) {

    int index = result.getMethodParameter().getParameterIndex();

    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        String[] codes = error.getCodes();
        String defaultMessage = error.getDefaultMessage();

        // Create an error DTO containing only safe location/code/message.
        // Do not return raw method arguments to the client by default.
    }
}
```

Spring also provides `HandlerMethodValidationException.Visitor` to group results by parameter kind, such as request param, path variable, or model attribute; that is a good choice when formatting errors differently by input source. Error results for cascaded DTOs can include field errors, not just `@Min`/`@NotBlank` on scalar arguments.

When returning errors to clients, keep the contract independent of Java parameter names — names can depend on compiler settings and parameter-name metadata. Also avoid logging raw `getArgument()` or rejected values if they might contain passwords, tokens, emails, or personal data.

## 10. Distinguishing HTTP status for input errors vs. return-value errors

Method validation has two timing points:

```text
HTTP request
   │
   ├── argument resolution / type conversion
   │      └── can fail right at this step
   ▼
Built-in method validation: direct parameters and @Valid cascade
   │
   ├── invalid → HandlerMethodValidationException → 400
   ▼
Controller method body executes
   │
   ▼
Built-in method validation: return value
   │
   ├── invalid → HandlerMethodValidationException → 500
   ▼
MVC return value handling / HTTP response
```

**Return-value validation is a postcondition.** If a controller already called a service, updated a database, or published a message and then returned an invalid result, the postcondition detects the failure **after** those operations. It does not automatically roll back the database or undo external side effects. Transaction design, idempotency, and side-effect testing must still be handled separately.

HTTP 400 generally reflects input failing the API contract; HTTP 500 on a return value reflects a server-side logic bug or invariant failure. When customizing `@ControllerAdvice`, do not accidentally convert every `HandlerMethodValidationException` into HTTP 400, as that would mask postcondition failures.

## 11. Validation groups and advanced scenarios

Direct constraints use Jakarta Bean Validation groups; if unspecified, they belong to `Default`. Example:

```java
public interface AdvancedChecks {}

@GetMapping("/reports")
@Validated(AdvancedChecks.class)
public String report(
        @RequestParam("limit")
        @Min(value = 1, groups = AdvancedChecks.class) int limit) {

    return "limit=" + limit;
}
```

This illustrative snippet requires importing Spring's `@Validated`; placing the annotation at the **method** level selects the groups used by method validation. Do not use class-level `@Validated` on a controller merely to select groups if your goal is built-in MVC validation, because class-level `@Validated` can cause Spring to choose the AOP path.

For collections or nested parameters, distinguish:

- Constraints on the **collection itself**: `@NotEmpty`, `@Size`.
- Constraints on **elements**: for example `List<@NotBlank String>`, using type-use constraints when supported by the provider and resolution path.
- Cascading into objects: `List<@Valid ItemRequest>` or `@Valid ItemRequest`, depending on types and Bean Validation contracts.

Do not assume a scalar constraint like `@NotBlank` applies to every type; the provider may throw `UnexpectedTypeException` if no validator supports the corresponding Java type.

### Custom constraints

A custom Jakarta Bean Validation constraint declared with `@Constraint(validatedBy=...)` can be used directly on a parameter if the annotation allows `ElementType.PARAMETER`. It then participates in method validation via the same mechanism. However, validation must be executed by the provider, and custom `ConstraintValidator` implementations should be stateless/thread-safe according to their usage.

## 12. Testing the MVC path properly

There are two distinct testing levels:

1. **Direct Java unit test of the method** (for example `new TicketController().ticket(0, 0, "")`) only tests code inside the handler body. It does not automatically run Spring MVC argument resolvers or built-in method validation.
2. **Integration tests via HTTP or MockMvc** actually verify that constraints are detected and check the exception types and HTTP statuses produced by MVC.

A test suite should cover:

| Input | Outcome to verify |
| --- | --- |
| `ticketId=8, count=3`, with header `X-Client: demo` | HTTP 200, handler returns result |
| `ticketId=0` | Direct `@Positive` fails, HTTP 400 |
| `count=0` | Direct `@Min` fails, HTTP 400 |
| `count=11` | Direct `@Max` fails, HTTP 400 |
| Missing header with `required=false @NotBlank` | Constraint fails, HTTP 400 |
| `count=abc` | Type conversion error, not a `@Min` error |
| Missing query `count` | Missing required parameter before validation |
| `GET /broken` | Return value `@NotBlank` fails, HTTP 500 |
| `@Valid @RequestBody` with invalid field, no other direct constraints | `MethodArgumentNotValidException` path |
| `@Valid @RequestBody` combined with direct `@Min` on another parameter | Whole-method validation path when applicable |
| Controller accidentally has class-level `@Validated` | Verify whether AOP or built-in MVC actually runs |

If tests depend on exception types, avoid sprinkling `@Validated` casually onto controllers. For APIs needing multi-language messages, use error codes/message bundles and `MessageSource` instead of relying on default `ConstraintViolation#getMessage()` or parsing `ex.getMessage()`.

## 13. Common errors and troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `@Min(1)` appears not to run | Missing Bean Validation provider or wrong integration | Use `spring-boot-starter-validation` and test via MVC |
| Missing param produces an error other than `@Min` | `@RequestParam(required=true)` failed at argument resolution | Handle missing-parameter errors separately |
| `count=abc` does not produce a Min violation | Could not convert to a number | Handle type mismatch |
| Using only `@Valid` and expecting direct method validation | `@Valid` is a cascade marker, not a constraint | Add appropriate constraints if direct validation is intended |
| Controller has class-level `@Validated`, unexpected exception | AOP validation replaces/affects built-in MVC validation | For Spring MVC 6.1+, consider removing the class-level marker |
| Only catching `MethodArgumentNotValidException` | Handler also has direct parameter constraints | Also catch `HandlerMethodValidationException` |
| `BindingResult` after DTO yet exception still thrown | Error on another method parameter without adjacent `Errors` | Understand the all-errors rule and method validation |
| `@Min` allows null | Specification allows null for numeric constraints | Combine with `@NotNull` or `required` as appropriate |
| `@NotBlank` placed on Integer | Unsupported target type | Choose a numeric constraint |
| Return value fails yet API returns 400 | Custom advice forces all validation errors to 400 | Check `isForReturnValue()` and preserve HTTP 500 |
| Returning rejected arguments to clients | Exposes sensitive data | Output only normalized field/code/message |
| Test calls controller directly and sees no error | Bypassed Spring MVC runtime | Test through MockMvc or HTTP |

## 14. Summary

**Direct constraints on controller parameters** means placing Jakarta Bean Validation constraint annotations — such as `@Min`, `@Positive`, `@NotBlank` — directly on handler parameters alongside data-extraction annotations like `@RequestParam` or `@PathVariable`. Starting in Spring MVC 6.1, these constraints can trigger **built-in method validation**, throwing `HandlerMethodValidationException` for input or postcondition errors.

Clearly separate **argument resolution**, **type conversion**, **constraint validation**, and the **controller body**. Further distinguish `@Valid` on command objects from direct constraints, avoid class-level `@Validated` when wanting built-in MVC validation, and handle both `MethodArgumentNotValidException` and `HandlerMethodValidationException` at the API boundary. Testing through actual Spring MVC is the reliable way to confirm the contract is enforced.

## References

- Spring Framework 6.2 Reference — Spring MVC Validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 Reference — Request parameters: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestparam.html
- Spring Framework 6.2 Reference — Type conversion: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework 6.2 Reference — Request body and validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework 6.2 Javadoc — `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Reference — Configuring MVC validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Jakarta Bean Validation 3.0 Specification — Constraint declaration and executable validation: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html