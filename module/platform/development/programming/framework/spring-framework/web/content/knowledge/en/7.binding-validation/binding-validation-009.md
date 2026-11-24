# Method Parameter Validation and Distinguishing Validation Exceptions Across Spring MVC Versions

## 1. The Practical Problem: Why Does the Same Bad Input Trigger Different Exceptions?

In Spring MVC, consider these three declarations:

~~~java
// (A) Validates properties of a request DTO.
public Receipt create(@Valid @RequestBody CreateOrder request) { ... }

// (B) Validates a constraint directly on an HTTP parameter.
public Receipt find(@RequestParam("page") @Min(1) int page) { ... }

// (C) Validates both a direct parameter and a DTO in the same handler.
public Receipt create(@RequestParam("batch") @Min(1) int batch,
                      @Valid @RequestBody CreateOrder request) { ... }
~~~

The three snippets above **are illustrative signatures only**, not standalone Java methods. Notably, in **Spring Framework 6.1+**, (A) typically follows **individual argument validation** and can throw `MethodArgumentNotValidException`; (B) and (C) typically follow **Spring MVC's built-in method validation** and can throw `HandlerMethodValidationException`. In (C), even property errors inside the DTO can be folded into method validation. If the controller class also carries `@Validated` at the **class level**, execution can route through an AOP proxy and throw a different exception again.

Understanding these mechanisms helps you:
- Know when single-argument validation triggers versus whole-method validation.
- Use `@Valid`, `@Validated`, and constraints like `@NotBlank`/`@Min` in the right places.
- Distinguish JSON errors, type conversion errors, field validation errors, method validation errors, and server-side failures when return values violate contracts.
- Design `@ControllerAdvice` handlers that remain stable as your project upgrades Spring Framework/Spring Boot.

**Scope:** Spring MVC on the Servlet stack. This lesson specifically distinguishes branches in **Spring Framework 6.0, 6.1, and 6.2**; Java 17+, Jakarta Bean Validation, and Spring Boot 3.x. Spring Boot 2.x/Spring 5.x are noted to clarify migration. Spring WebFlux has its own exceptions/adapters, so do not copy MVC tables blindly.

## 2. Distinguishing Three Processing Layers

Consider an example JSON request:

~~~http
POST /api/registrations?batch=0 HTTP/1.1
Content-Type: application/json

{"name":"","email":"not-an-email","tickets":0}
~~~

A handler can fail at different layers:

~~~text
HTTP request
  │
  ▼
DispatcherServlet locates handler + handler argument resolvers
  │
  ├── Read/parse/bind request, convert types, check required conditions
  │     ├── Malformed JSON / missing body        → HttpMessageNotReadableException
  │     ├── Missing query param                  → MissingServletRequestParameterException
  │     └── Unconvertible query type             → MethodArgumentTypeMismatchException
  │
  ├── Bean Validation per @RequestBody/@ModelAttribute/@RequestPart
  │     └── MethodArgumentNotValidException (when applicable)
  │
  ├── Built-in MVC method validation (Spring 6.1+, when triggered)
  │     └── HandlerMethodValidationException
  │
  └── Invoke handler; may check constraints on return value
        └── HandlerMethodValidationException (isForReturnValue = true)
~~~

This diagram shows **decision paths**, meaning a single request does not necessarily pass through every validation stage. When method validation applies, Spring MVC coordinates with argument validation to **avoid duplicate checks**, and can throw `HandlerMethodValidationException` for nested DTO errors. When using **AOP method validation** with `@Validated` on the class, another proxy participates and can throw `ConstraintViolationException`/`MethodValidationException`.

Do not equate every HTTP 400 with `MethodArgumentNotValidException`. Malformed syntax, wrong Content-Type, or failed type conversion can be rejected **before Bean Validation runs**.

## 3. Jakarta Bean Validation Foundations

### 3.1. What Is a Constraint?

Annotations in `jakarta.validation.constraints` encode rules evaluated by a validator:

| Annotation | Common usage | Notes |
| --- | --- | --- |
| `@NotNull` | Non-null reference | Allows empty strings, unlike `@NotBlank` |
| `@NotBlank` | `CharSequence` with non-whitespace characters | Not applicable to `long`/`int` |
| `@NotEmpty` | Strings, collections, maps, arrays | Does not reject whitespace-only strings |
| `@Size(min=..., max=...)` | Strings/collections/arrays | Checks length/size, not numeric value |
| `@Min(1)`, `@Max(10)` | Compatible numeric types | Compares numeric bounds |
| `@Positive`, `@PositiveOrZero` | Numbers | `0` is valid only with `PositiveOrZero` |
| `@Email` | Email-formatted strings | Combine with `@NotBlank` if missing/blank is disallowed |
| `@Pattern(regexp="...")` | Strings | Regex is a validation constraint, not an input converter |
| `@Valid` | Nested objects / collection elements | **Triggers cascade**; by itself **not a constraint** |
| Spring `@Validated` | Selects validation groups, enables class/method AOP where applicable | Not synonymous with `@Valid` in every position |

Example DTO with Bean Validation metadata:

~~~java
package com.example.validationdemo.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank @Size(max = 80) String name,
        @NotBlank @Email String email,
        @Min(1) int tickets) {
}
~~~

This sample uses a Java record. Sending JSON `{"name":"","email":"bad","tickets":0}` can produce multiple violations: blank `name`, invalid `email` format, and `tickets` below 1. **A Bean Validation provider is mandatory** (usually Hibernate Validator via `spring-boot-starter-validation`); importing the annotations alone does not ensure Spring executes validation.

With primitive `int`, an omitted JSON property can become the default zero value on certain deserialization/binding paths depending on config; if you need to distinguish "absent" from zero, choose `Integer` with `@NotNull` and test actual JSON payloads.

### 3.2. `@Valid` Does Not Trigger Method Validation by Itself

Distinguish:

~~~java
public String save(@Valid @RequestBody SignupRequest input)
~~~

from

~~~java
public String save(@NotNull @Valid @RequestBody SignupRequest input)
~~~

In Spring MVC 6.1+, the first signature **only** requests cascade validation on that single object when eligible; the second adds `@NotNull`, which is a **direct constraint on the method parameter**, thereby activating method validation. Adding one annotation can change the exception type even with the exact same DTO and JSON request.

Do not add `@NotNull` reflexively just for "extra safety." `@RequestBody` defaults to `required=true`, which already checks for a missing body. The two checks operate at different layers and can yield different error responses.

### 3.3. Groups and Placement of `@Validated`

Spring's `@Validated(Group.class)` can be placed on a parameter to specify validation groups for that argument. Class-level `@Validated` on a **controller class** means something else: it signals AOP method validation when a matching post-processor is active. Starting in Spring 6.1, if you want **built-in MVC method validation**, **omit `@Validated` at the class level**. Spring's documentation explicitly notes this requirement.

In Spring Boot 3.x, verify that your dependencies/runtime actually include a validator and MVC setup rather than assuming annotations make every constraint active.

## 4. Two Validation Modes in Spring MVC 6.1+

### 4.1. Individual Argument Validation

A method with only a DTO to validate and **no direct method constraints**:

~~~java
@PostMapping("/object")
public Receipt object(@Valid @RequestBody SignupRequest request) {
    return new Receipt(request.name(), request.tickets());
}
~~~

With a Bean Validation provider and no `Errors`/`BindingResult` immediately after the argument, constraint violations on the record typically produce:

~~~text
org.springframework.web.bind.MethodArgumentNotValidException
Default HTTP status: 400 Bad Request
~~~

`MethodArgumentNotValidException` carries a `BindingResult`. You can read:
- `getFieldErrors()`: property errors such as `name` and `tickets`.
- `getGlobalErrors()`: object-level errors.
- `getAllErrors()`: combined errors.
- `getBindingResult()`: binding/validation result to render the error response.

The same principle applies to `@Valid @ModelAttribute` and `@Valid @RequestPart` (for eligible DTO types). Exact behavior still depends on annotations, object types, method signature, and whether method validation is active.

### 4.2. Built-In MVC Method Validation

Constraints placed **directly on a method parameter** or **on the method return value**:

~~~java
@GetMapping("/page")
public PageView page(@RequestParam("page") @Min(1) int page) {
    return new PageView(page);
}
~~~

In Spring Framework **6.1+**, without class-level `@Validated` and with a suitable validator, `GET /page?page=0` violating `@Min(1)` typically produces:

~~~text
org.springframework.web.method.annotation.HandlerMethodValidationException
Default HTTP status: 400 Bad Request (input violation)
~~~

The same method can also validate a nested DTO:

~~~java
@PostMapping("/method")
public Receipt method(
        @RequestParam("batch") @Min(1) int batch,
        @Valid @RequestBody SignupRequest request) {
    return new Receipt(request.name(), request.tickets());
}
~~~

Because `@Min(1)` is on `batch`, method validation **covers** both `batch` errors and cascaded errors from `@Valid SignupRequest`. Consequently, sending `batch=1` with an invalid DTO can still produce **`HandlerMethodValidationException`**, not `MethodArgumentNotValidException`. This is an easily missed migration subtlety: **the exception type depends on the entire handler signature, not solely on the DTO's annotations**.

`HandlerMethodValidationException` groups results by parameter (`ParameterValidationResult`; bean errors may be represented as `ParameterErrors`). It exposes `getAllValidationResults()` and `visitResults(Visitor)` to inspect sources like `@RequestParam`, `@PathVariable`, `@RequestHeader`, and `@ModelAttribute`; do not assume there is only one DTO field error.

### 4.3. Return Value Validation

A method can also declare constraints on its **return value**:

~~~java
@GetMapping("/returned")
@NotBlank
public String returned() {
    return "";
}
~~~

In this demo, the handler returns a blank string, violating `@NotBlank`. With built-in MVC method validation (Spring 6.1+), this can raise `HandlerMethodValidationException` with `isForReturnValue() == true`. **The default status is 500 Internal Server Error**, because this is a **server-side** contract failure rather than invalid client input (400). Never write an advice catching all validation exceptions and forcing HTTP 400.

This distinction is vital for monitoring: 4xx generally reflects client input issues; 5xx from return violations must be alerted on and fixed in application/service code.

### 4.4. `BindingResult` / `Errors` Immediately After a Parameter

~~~java
@PostMapping("/form")
public ResponseEntity<?> form(
        @Valid @ModelAttribute SignupForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().body("Form invalid");
    }
    return ResponseEntity.ok("Accepted");
}
~~~

This is an illustrative fragment; `SignupForm` must be a bindable form DTO. With `BindingResult`/`Errors` **immediately after** the validated object, the controller can handle errors for that object itself. When method validation also applies, Spring still invokes the handler only if all errors can be delivered to matching `Errors` parameters; **any error on another parameter without an immediately following `Errors` still throws `HandlerMethodValidationException`**. Do not append `BindingResult` arbitrarily at the end of a signature or treat it as a catch-all for `@RequestParam @Min`.

Commonly misunderstood case:

~~~java
// This is not a universal error catcher for every method parameter:
public String submit(
        @Valid @ModelAttribute SignupForm form,
        BindingResult result,
        @RequestParam("page") @Min(1) int page) {
    ...
}
~~~

If `page=0`, the controller is not automatically invoked just because `form` has a `BindingResult`.

## 5. Exception Matrix by Version and Mechanism

| Context | Spring Framework before 6.1 (especially 5.x/6.0) | Spring Framework 6.1+/6.2 | Typical status |
| --- | --- | --- | --- |
| `@Valid @RequestBody DTO`, no direct method constraint and no `BindingResult` | `MethodArgumentNotValidException` | `MethodArgumentNotValidException` | 400 |
| `@Valid @ModelAttribute DTO`, no `BindingResult` | May see `BindException` (especially legacy MVC); Spring 6.0 moved many branches to `MethodArgumentNotValidException` | `MethodArgumentNotValidException` when individual validation applies | 400 |
| Direct `@Min`/`@NotBlank` on method parameter, no class-level AOP `@Validated` | Before 6.1 **no new built-in MVC method validation**; required separate setup, typically AOP | `HandlerMethodValidationException` | 400 on input violation |
| Direct method constraint **and** `@Valid` DTO on the same handler | DTO validation may run in argument resolver; direct constraints need appropriate AOP setup | Method validation covers both direct and cascaded constraints → `HandlerMethodValidationException` | 400 |
| Constraint on handler **return value** | Typically required separate AOP/executable validation | Built-in MVC method validation → `HandlerMethodValidationException` | 500 if server returns invalid value |
| `@Validated` **on class**, AOP method validation active | Commonly: `ConstraintViolationException` | Can still route through AOP: `ConstraintViolationException`, or `MethodValidationException` if AOP adapts | Depends on exception handler; **do not assume 400 by default** |
| Malformed JSON syntax or missing required body | `HttpMessageNotReadableException` | `HttpMessageNotReadableException` | Usually 400 |
| Missing required `@RequestParam` | `MissingServletRequestParameterException` | `MissingServletRequestParameterException` | Usually 400 |
| `@RequestParam int` receiving `abc` | `MethodArgumentTypeMismatchException`/conversion error | Same | Usually 400 |

**How to read this table:** actual validation errors depend on signature, resolvers, Bean Validation provider, filters/AOP, `BindingResult`, handlers, and exception configuration. Never deduce an exception class from HTTP status alone or from a single annotation.

### 5.1. Which Spring Boot Versions Correspond?

As a migration orientation (never replace inspecting your dependency tree with this table):
- **Boot 2.x** uses Spring Framework **5.x**, commonly with the `javax.validation.*` Bean Validation namespace.
- **Boot 3.0–3.1** uses Spring Framework **6.0.x**; uses `jakarta.validation.*`, **without Spring MVC 6.1's built-in method validation**.
- **Boot 3.2–3.3** uses Spring Framework **6.1.x** in standard baselines.
- **Boot 3.4–3.5** typically uses Spring Framework **6.2.x** under standard dependency management.

Projects overriding dependencies may differ. **Verify the actual Spring version at runtime** (e.g., `./gradlew dependencies --configuration runtimeClasspath` or Maven dependency tree) and consult the matching versioned docs. Do not change code based solely on a Spring Boot major version number.

### 5.2. AOP `@Validated` and `ConstraintViolationException`

In older setups, Spring AOP method validation typically requires:
1. A `jakarta.validation.Validator` (or `javax.validation.Validator` in older generations).
2. A `MethodValidationPostProcessor` or equivalent auto-configuration.
3. The controller/service bean being proxied and method calls **going through the proxy**.
4. Usually `@Validated` at the class level on the bean to be proxied.

Method constraint violations via `MethodValidationInterceptor` **default** to throwing `jakarta.validation.ConstraintViolationException`. Starting in Spring 6.1, `MethodValidationPostProcessor.setAdaptConstraintViolations(true)` can be configured to adapt them into `org.springframework.validation.method.MethodValidationException`. Both exceptions **differ** from built-in MVC's `HandlerMethodValidationException`.

For Spring MVC 6.1+ controllers, if you keep class-level `@Validated`, you may still receive `ConstraintViolationException` after upgrading even when expecting `HandlerMethodValidationException`. Spring documentation recommends **removing class-level `@Validated`** to adopt MVC method validation. **Do not remove `@Validated` from services** just because controllers changed: AOP method validation remains useful in the service layer, where HTTP method argument resolvers do not exist.

### 5.3. History of `BindException` and Upgrade Notes

Many long-lived MVC applications contain:

~~~java
@ExceptionHandler(org.springframework.validation.BindException.class)
public ResponseEntity<?> handleForm(BindException ex) { ... }
~~~

This illustrates the concept; full imports and handlers are needed in a real project. In Spring MVC 6.0, many `@ModelAttribute` paths switched to `MethodArgumentNotValidException` (which is a subclass of `BindException` in that hierarchy). During migration, verify actual exception classes, handler scopes, and interactions with `ResponseEntityExceptionHandler`. Avoid keeping multiple `@ExceptionHandler` methods with overlapping scopes in the same advice if they cause ambiguity.

**`MethodValidationException` is not a renamed `MethodArgumentNotValidException`.** It represents the method validation API/AOP path and requires separate handling. Do not use string matching like `ex.getClass().getSimpleName()` or catch `Exception` wholesale and return 400.

## 6. Spring Boot 3.3 / Spring Framework 6.1 Example: Running and Reproducing Both Key Exceptions

The example below uses **Spring Boot 3.3.5** (Spring Framework 6.1.x baseline) with Java 17+. Files have self-contained packages/classes and can run in a corresponding Gradle Spring Boot project. Do not put `@Validated` on the controller class so built-in MVC method validation is active.

Structure:

~~~text
validation-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/validationdemo/
    │   ├── ValidationDemoApplication.java
    │   ├── api/SignupRequest.java
    │   └── web/
    │       ├── ValidationController.java
    │       └── ValidationErrorAdvice.java
    └── test/java/com/example/validationdemo/web/
        └── ValidationControllerTest.java
~~~

### 6.1. Build Config

`settings.gradle`:

~~~groovy
rootProject.name = 'validation-demo'
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

`spring-boot-starter-validation` is essential: Hibernate Validator provides runtime enforcement of `@NotBlank`/`@Email`/`@Min`. The example assumes Gradle 8.x compatible with Java 17 and Spring Boot 3.3, with a Gradle wrapper generated for your project. If using an existing project with its own plugin/dependency management, add only the needed starters while preserving your managed versions.

### 6.2. Main Application

`src/main/java/com/example/validationdemo/ValidationDemoApplication.java`:

~~~java
package com.example.validationdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` sits at the root package so component scanning discovers the controller and advice.

### 6.3. Request DTO with Constraints

`src/main/java/com/example/validationdemo/api/SignupRequest.java`:

~~~java
package com.example.validationdemo.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SignupRequest(
        @NotBlank @Size(max = 80) String name,
        @NotBlank @Email String email,
        @Min(1) int tickets) {
}
~~~

### 6.4. Controller: Contrasting Individual vs. Method Validation

`src/main/java/com/example/validationdemo/web/ValidationController.java`:

~~~java
package com.example.validationdemo.web;

import com.example.validationdemo.api.SignupRequest;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/validation")
public class ValidationController {

    public record Receipt(String name, int tickets) {}
    public record PageView(int page) {}

    // Validates DTO only: individual argument validation.
    @PostMapping("/object")
    public Receipt object(@Valid @RequestBody SignupRequest request) {
        return new Receipt(request.name(), request.tickets());
    }

    // @Min is a direct constraint: enables MVC method validation.
    @PostMapping("/method")
    public Receipt method(
            @RequestParam("batch") @Min(1) int batch,
            @Valid @RequestBody SignupRequest request) {
        return new Receipt(request.name(), request.tickets());
    }

    @GetMapping("/page")
    public PageView page(@RequestParam("page") @Min(1) int page) {
        return new PageView(page);
    }

    // Return-value constraint: server-side failure must produce 500.
    @GetMapping("/returned")
    @NotBlank
    public String returned() {
        return "";
    }

    // Adjacent BindingResult handles form errors inside the controller.
    @GetMapping("/form")
    public ResponseEntity<Map<String, Boolean>> form(
            @Valid @ModelAttribute FormInput form,
            BindingResult result) {
        return ResponseEntity.ok(Map.of("valid", !result.hasErrors()));
    }

    public static class FormInput {
        @NotBlank
        private String keyword;

        public FormInput() {}

        public String getKeyword() {
            return keyword;
        }

        public void setKeyword(String keyword) {
            this.keyword = keyword;
        }
    }
}
~~~

Note **no `@Validated` on the class**. `@Min(1)` on `batch` and `page` are direct constraints. `@NotBlank` on `returned()` is a return-value constraint. `FormInput` is a form/query DTO with a `keyword` field, and `BindingResult` sits right next to it.

### 6.5. Handling Both MVC Exceptions with One JSON Contract

`src/main/java/com/example/validationdemo/web/ValidationErrorAdvice.java`:

~~~java
package com.example.validationdemo.web;

import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ValidationErrorAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Map<String, Object> body = Map.of(
                "kind", "argument",
                "fieldErrors", ex.getBindingResult().getFieldErrorCount());

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Map<String, Object> body = Map.of(
                "kind", "method",
                "resultGroups", ex.getAllValidationResults().size(),
                "returnValue", ex.isForReturnValue());

        return new ResponseEntity<>(body, headers, status);
    }
}
~~~

Advantages:
- Overrides the **exact hooks** of `ResponseEntityExceptionHandler`, rather than declaring duplicate `@ExceptionHandler` methods already managed by the superclass.
- Preserves the status computed by the framework; for method validation, status can be **400 for input** or **500 for return values**.
- Uses `getBindingResult()` for individual argument validation and `getAllValidationResults()` for method validation, matching each exception's error model.
- Does not put `rejectedValue` (which could contain secrets) directly into JSON returned to clients.

This JSON structure is an **illustrative application contract**, not the default error body of every Spring Boot project. In production, prefer `ProblemDetail`/RFC 9457, message codes, localization, trace IDs, and stable field paths. You can write a shared converter so both branches emit a unified error schema while keeping the root cause distinguishable in logs/telemetry.

## 7. Running the Application and Observing Real Errors

From the project directory with the appropriate wrapper:

~~~bash
./gradlew bootRun
~~~

Send an invalid DTO request **with no direct method constraints**:

~~~bash
curl -i -X POST 'http://localhost:8080/api/validation/object' \
  -H 'Content-Type: application/json' \
  -d '{"name":"","email":"bad","tickets":0}'
~~~

Expected result is **HTTP 400** with the response produced by `ValidationErrorAdvice`, shaped like:

~~~json
{"kind":"argument","fieldErrors":3}
~~~

With the default provider and constraints in this example, blank `name`, invalid `email`, and `tickets` below 1 produce three field violations. **Do not rely on field error ordering** when building UIs.

Call the method with a direct parameter constraint:

~~~bash
curl -i -X POST 'http://localhost:8080/api/validation/method?batch=0' \
  -H 'Content-Type: application/json' \
  -d '{"name":"An","email":"an@example.com","tickets":2}'
~~~

Expected **HTTP 400**, body:

~~~json
{"kind":"method","resultGroups":1,"returnValue":false}
~~~

`resultGroups` counts **parameters with errors**, not total field violations. Sending `batch=1` with an invalid DTO also triggers method validation with `kind=method`; group count depends on which parameters failed.

Call return-value validation:

~~~bash
curl -i 'http://localhost:8080/api/validation/returned'
~~~

Expected **HTTP 500** (sample application response):

~~~json
{"kind":"method","resultGroups":0,"returnValue":true}
~~~

`resultGroups=0` in this return-only example reflects that **parameter** results may be empty; return-value violations have their own APIs and should never be interpreted as "no errors" based on parameter group count. In public APIs, keep return violation details in server logs and return a safe 500 message to clients.

Call a failing form query that has `BindingResult`:

~~~bash
curl -i 'http://localhost:8080/api/validation/form?keyword='
~~~

Expected:

~~~json
{"valid":false}
~~~

HTTP status is **200 OK** because the controller itself intentionally chose `ResponseEntity.ok(...)` to prove it was invoked. In real systems, choosing `400` or re-rendering a form with HTTP 200 depends on application style; here 200 does not mean the data is valid.

**Distinguish error categories:** malformed JSON syntax or a missing body can raise `HttpMessageNotReadableException` **before** validation runs. Query `page=abc` can trigger a conversion error **before** `@Min` is checked. Do not expect the two overrides in `ValidationErrorAdvice` above to convert those errors into `kind=method`/`kind=argument`.

## 8. MockMvc Tests Asserting Behavioral Exceptions

`src/test/java/com/example/validationdemo/web/ValidationControllerTest.java`:

~~~java
package com.example.validationdemo.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ValidationController.class)
@Import(ValidationErrorAdvice.class)
class ValidationControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void invalidDtoWithoutDirectConstraintUsesArgumentValidation() throws Exception {
        mvc.perform(post("/api/validation/object")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"email\":\"bad\",\"tickets\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.kind").value("argument"))
                .andExpect(jsonPath("$.fieldErrors").value(3));
    }

    @Test
    void directConstraintUsesBuiltInMethodValidation() throws Exception {
        mvc.perform(post("/api/validation/method")
                        .param("batch", "0")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"An\",\"email\":\"an@example.com\","
                               + "\"tickets\":2}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.kind").value("method"))
                .andExpect(jsonPath("$.returnValue").value(false));
    }

    @Test
    void nestedDtoUsesMethodValidationWhenDirectConstraintExists() throws Exception {
        mvc.perform(post("/api/validation/method")
                        .param("batch", "1")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"email\":\"bad\",\"tickets\":0}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.kind").value("method"));
    }

    @Test
    void invalidReturnValueIsServerFailure() throws Exception {
        mvc.perform(get("/api/validation/returned"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.kind").value("method"))
                .andExpect(jsonPath("$.returnValue").value(true));
    }

    @Test
    void adjacentBindingResultHandlesFormErrorsLocally() throws Exception {
        mvc.perform(get("/api/validation/form").param("keyword", ""))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.valid").value(false));
    }

    @Test
    void validDtoWorks() throws Exception {
        mvc.perform(post("/api/validation/object")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\",\"email\":\"lan@example.com\","
                               + "\"tickets\":2}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("Lan"))
                .andExpect(jsonPath("$.tickets").value(2));
    }
}
~~~

Remove the unused `ObjectMapper` import if your IDE/linter warns; the test sends raw JSON strings directly and does not serialize Java objects. Each test verifies both **status and the exception category classified by the advice**, avoiding assertions on default error bodies that change across configurations.

Run:

~~~bash
./gradlew test
~~~

Tests assume the sample app, a Bean Validation provider, and complete Spring MVC test auto-configuration. If your project adds Spring Security, custom `@ControllerAdvice`, custom validators, or filters, `@WebMvcTest` may require additional configuration. Do not run tests under a different configuration and conclude Spring 6.1 is broken without verifying whether method validation and proxies are active.

### 8.1. Asserting Exact Exception Details When Needed

Beyond the response body, you can assert the resolved exception:

~~~java
// Excerpt from a @Test configured with MockMvc:
// .andExpect(result ->
//     assertInstanceOf(MethodArgumentNotValidException.class,
//                      result.getResolvedException()));
~~~

`assertInstanceOf` comes from JUnit 5 and `MethodArgumentNotValidException` from Spring. This is a commented illustration requiring the corresponding imports. For method errors, substitute `HandlerMethodValidationException.class`. Assert exact exception classes when verifying **migrations or mechanism regressions**; for API clients, prioritize testing stable schemas and statuses.

## 9. Normalizing Errors for Frontends Without Losing Semantics

A practical error contract can look like:

~~~json
{
  "type": "https://example.org/problems/validation",
  "title": "Invalid request",
  "status": 400,
  "violations": [
    {"field": "name", "message": "must not be blank"},
    {"field": "tickets", "message": "must be greater than or equal to 1"}
  ]
}
~~~

The JSON above is a **design example**, not an automatic Spring response body. Identifying the field or method parameter depends on the exception:
- `MethodArgumentNotValidException`: use `BindingResult` / `FieldError` to get object paths.
- `HandlerMethodValidationException`: use `getAllValidationResults()` or `visitResults(Visitor)`; errors may be direct on parameters, nested beans, or cross-parameter.
- `ConstraintViolationException`: iterate `ConstraintViolation<?>`; Jakarta Bean Validation property paths can contain internal method/parameter names differing from external HTTP names.
- `MethodValidationException`: exposes `MethodValidationResult`; this is not an HTTP-specific exception.

Never expose internal paths like `methodName.arg0` directly as an API contract if you want stability across refactors. Map names to HTTP semantics (`@RequestParam`/`@PathVariable`) or DTO fields when valid and consistent with privacy policies.

In Spring MVC 6.1+/6.2, `ResponseEntityExceptionHandler` provides `handleMethodArgumentNotValid` and `handleHandlerMethodValidationException` hooks, covering both built-in validation paths. When a subclass overrides a hook, do not add another `@ExceptionHandler` with a conflicting signature in the same advice, since the superclass already uses `@ExceptionHandler` to dispatch.

`ConstraintViolationException` from AOP requires a separate handling path, such as an advice scoped to service boundaries with deliberate error-code mapping. Never blindly turn every `ConstraintViolationException` into 400: it may arise from an internal service call rather than client input.

## 10. Errors Easily Confused with Validation

| Observed symptom | Typical exception | Meaning | Resolution |
| --- | --- | --- | --- |
| Missing/malformed JSON body | `HttpMessageNotReadableException` | Converter cannot construct object | Check raw request, `Content-Type`, JSON parser |
| DTO constructed, constraints fail | `MethodArgumentNotValidException` or `HandlerMethodValidationException` | Bean Validation / method validation | Check signature, Spring version, AOP, `BindingResult` |
| Query `page=xyz` for `int` | `MethodArgumentTypeMismatchException` | Type conversion failed | Check converter/formatter and HTTP contract |
| Missing `@RequestParam(required=true)` | `MissingServletRequestParameterException` | Required source missing | Supply input / adjust default/required intentionally |
| Unsupported Content-Type | `HttpMediaTypeNotSupportedException` | No compatible mapping/converter | Fix header/payload/`consumes` |
| Return-value constraint violated | `HandlerMethodValidationException` with `isForReturnValue=true` in 6.1+ | Server violated its contract | Return 500, log, and fix producer |
| Class-level `@Validated` + AOP method | `ConstraintViolationException` or `MethodValidationException` | Proxy validation path | Check proxy, `MethodValidationPostProcessor`, and version |
| `BindingResult` receives no errors | Exception still thrown | Misplaced or error is on another parameter | Place immediately after DTO and handle method violations separately |
| `@Valid` has no effect | Missing provider, missing constraint/cascade, or wrong placement | Validation not triggered as expected | Check dependencies, imports, DTO, and tests |
| Handler is never entered | Rejected before controller or by method validation | Expected for invalid input in many cases | Safely log exception class + status + route |

Notably, Spring Boot may render different error bodies depending on `spring.mvc.problemdetails.enabled`, custom advices, `MessageSource`, and version. To protect frontend contracts, test your application's API output; to diagnose mechanisms, test/log the **exception class**.

## 11. Safe Spring MVC Upgrade Checklist

1. **Record before and after versions**: `spring-webmvc`, `spring-context`, `jakarta.validation-api`, and the actual provider. Migrating from Boot 2 to 3 requires changing `javax.validation` → `jakarta.validation` along with compatible library versions.
2. **Inventory controllers with class-level `@Validated`** and direct constraints on method parameters/returns. On Spring 6.1+, consider removing the class annotation to adopt built-in MVC validation. Keep AOP validation on services that genuinely need it.
3. **Audit full handler signatures**, not only DTOs: `@Min` on a `@RequestParam` can shift `@Valid @RequestBody` in the same method to `HandlerMethodValidationException`.
4. **Check `BindingResult` placement right after arguments** when controllers handle form/body errors directly. If all errors should route through advice, remove local handling intentionally and standardize the contract.
5. **Update advices** to handle both `MethodArgumentNotValidException` and `HandlerMethodValidationException`. Separate return-value violations (500) from client input errors (400).
6. **Verify methods/proxies and validation groups**. AOP self-invocation bypasses standard proxies; interface vs. class proxies change interception points. Do not blame Bean Validation for proxy behavior.
7. **Run comparative tests**: valid requests, invalid DTOs, direct query constraints, both combined, return-value violations, malformed JSON, missing required queries, and binding errors.
8. **Inspect actual exceptions** in logs/tests when differences appear, as custom `ControllerAdvice` and framework versions affect outcomes. Never read sensitive `rejectedValue` into logs.
9. **Keep public error formats stable**: status, type, machine-readable codes, field names, locale/message sources; never let exception class names become your API contract.
10. **Verify validation happens at the right boundaries**: request validation for HTTP inputs; business invariants and transaction validation in services/domains; response validation failures as server bugs.

### Self-Check Questions

**1.** What exception does `@Valid @RequestBody Dto` with no direct method constraints and no `BindingResult` normally raise in Spring 6.1+?

**Answer:** `MethodArgumentNotValidException` when Bean Validation finds violations on the DTO.

**2.** With the same DTO, what if the method also accepts `@RequestParam @Min(1) int quantity`?

**Answer:** Built-in method validation is triggered; errors on the direct parameter or cascaded DTO errors can produce `HandlerMethodValidationException`.

**3.** Why might a project upgrade Boot and suddenly observe `ConstraintViolationException`?

**Answer:** The controller may be undergoing AOP method validation due to class-level `@Validated`/`MethodValidationPostProcessor`; check proxy configuration and version before changing exception-handling logic.

**4.** Is `@Valid` alone enough to trigger method validation when there are no direct constraints?

**Answer:** No. `@Valid` requests cascade validation; it is not a direct `@Constraint` like `@NotNull`.

**5.** Why should return-value constraint violations produce 500?

**Answer:** Clients cannot control the server returning a value that violates its own published contract; that is a server-side bug.

**6.** Can a `BindingResult` after `@Valid Dto` handle a `@Min` violation on a third parameter?

**Answer:** No. It binds only to the immediately preceding DTO, not to all errors on the method.

## 12. Official Versioned Documentation

- [Spring Framework 6.2 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): distinguishing individual argument vs. method validation, `BindingResult`, class-level `@Validated`, and both MVC exceptions.
- [Spring Framework 6.1 — HandlerMethodValidationException Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html): `isForReturnValue`, `getAllValidationResults`, `visitResults`, 400/500 statuses.
- [Spring Framework 6.1 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): hooks for handling `MethodArgumentNotValidException`/`HandlerMethodValidationException`.
- [Spring Framework 6.1 — MethodValidationPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html): AOP method validation, `ConstraintViolationException`, and `setAdaptConstraintViolations`.
- [Spring Framework — `@RequestBody` validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): validation, `BindingResult`, and converter handling.
- [Spring Framework 6.x Upgrade Notes](https://github.com/spring-projects/spring-framework/wiki/Upgrading-to-Spring-Framework-6.x): migration guide for 6.x and method validation integration.
- [Jakarta Bean Validation specification](https://jakarta.ee/specifications/bean-validation/3.0/): distinguishing constraints, cascading, groups, and executable validation.

**Key takeaway:** Identify **(1) when decoding/binding occurs, (2) whether a direct method constraint exists, (3) whether `BindingResult` sits right after the argument, (4) whether the controller has class-level `@Validated`/AOP, and (5) the exact Spring MVC version**. Those five factors usually explain why the same bad input routes through different exceptions.
