# HandlerMethodValidationException During Method Validation in Spring MVC

In **Spring MVC starting with Spring Framework 6.1**, controllers can be validated **directly at the method level** (*built-in handler method validation*) without creating an AOP proxy just to validate controllers. When one or more Jakarta Validation constraints on a handler's **parameters** or **return value** fail, Spring can raise **`HandlerMethodValidationException`**.

Example:

~~~java
@GetMapping("/items/{id}")
public ItemDto getItem(
        @PathVariable("id") @Min(1) long id,
        @RequestParam(name = "count", defaultValue = "1")
        @Min(1) @Max(10) int count) {
    return itemService.load(id, count);
}
~~~

If the request is `GET /items/0?count=0`, both `id` and `count` convert to Java numbers successfully, yet both **violate `@Min(1)`**. With MVC method validation properly configured, the framework collects errors per parameter and throws `HandlerMethodValidationException`; the handler does not run with that invalid parameter set.

By contrast, `GET /items/abc?count=2` fails **during type conversion** from `"abc"` to `long`, before the validator evaluates `@Min`. That error is normally `MethodArgumentTypeMismatchException`, **not** `HandlerMethodValidationException`.

This lesson focuses on the exception name, trigger conditions, error data structure, HTTP handling, distinguishing it from other error types, and a runnable/testable **Spring Boot 3.4+/Spring Framework 6.2, Java 17+** example. Spring Framework 6.1 shares the same foundational model, though you should verify exact version-specific API signatures.

## 1. Locating the exception in the Spring MVC lifecycle

`HandlerMethodValidationException` belongs to the package:

~~~java
import org.springframework.web.method.annotation.HandlerMethodValidationException;
~~~

It is thrown by Spring MVC within its **handler method** validation mechanism, not an exception that a Jakarta Validation provider always throws on arbitrary Java methods. Even though validation uses Jakarta Validation underneath, Spring exposes the results through the **`MethodValidationResult` / `ParameterValidationResult`** model.

A request passes through a generalized sequence:

~~~text
HTTP request
    |
    v
DispatcherServlet -> selects @RequestMapping handler
    |
    v
HandlerMethodArgumentResolver
    |  reads @PathVariable / @RequestParam / @RequestBody...
    |  binds data, converts String -> Java type
    v
Spring MVC built-in method validation
    |  checks direct constraints on parameters
    |  and @Valid cascades inside relevant arguments
    |
    +-- no violations: invoke controller method
    |
    +-- violations exist, not fully handled by BindingResult:
    |          |
    |          v
    |     HandlerMethodValidationException (input -> HTTP 400)
    |
    v
Controller method executes, produces return value
    |
    v
Checks return-value constraints if present
    |
    +-- violation -> HandlerMethodValidationException
    |                (return value -> HTTP 500)
    |
    v
HTTP message conversion / rendering
~~~

The diagram depicts common synchronous behavior. If an argument resolver cannot read JSON or convert types (`page=xyz` to `int`), it can throw a different exception **before** method validation. Likewise, business exceptions inside the handler body do not automatically become validation exceptions.

**Important:** Spring MVC has built-in method validation since **Spring Framework 6.1**. If `@Validated` is placed at the **controller class level**, Spring can activate **AOP-based method validation** instead of this built-in branch. Spring documentation recommends **removing class-level `@Validated` from controllers** if you want the built-in MVC mechanism.

## 2. When does `HandlerMethodValidationException` occur?

For the typical built-in mechanism, you need:

1. A supported Spring MVC version (Spring Framework 6.1+).
2. A suitable `jakarta.validation.Validator` in MVC configuration, such as `LocalValidatorFactoryBean` auto-configured by Spring Boot when a validation starter/provider is present.
3. The handler declares a **direct constraint** on a parameter such as `@Min`, `@NotBlank`, `@Size`, `@Pattern`, or on the method return value such as `@NotNull`.
4. Data passed argument resolution/type conversion, and validation detected at least one violation not handled by `Errors`/`BindingResult` per the rules.
5. The controller was not switched to the alternative AOP validation path by class-level `@Validated` when built-in MVC is intended.

Parameter example:

~~~java
@GetMapping("/search")
public String search(
        @RequestParam("q") @NotBlank String q,
        @RequestParam(defaultValue = "1") @Min(1) int page) {
    return "q=" + q + ",page=" + page;
}
~~~

`@NotBlank` on `q` and `@Min` on `page` are **direct constraints**. If `q` is empty and `page=0`, method validation applies at the handler level; both arguments can contribute separate errors.

Return-value example:

~~~java
@GetMapping("/current-code")
@NotNull
public String currentCode() {
    return null;
}
~~~

`@NotNull` on the method is a **return-value constraint**. If the method executes and returns `null`, the violation is detected **after the method runs**. This is usually a **server contract bug**, so `HandlerMethodValidationException` provides HTTP **500** rather than 400.

> **Do not equate "having `@Valid`" with "definitely triggering method validation".** `@Valid` itself is an annotation requesting cascading into a nested object, **not a `@Constraint`**. A DTO argument bearing only `@Valid` normally takes the argument resolver's standalone validation path. When the same handler has direct constraints on another argument or return value, MVC method validation can encompass nested constraints inside the `@Valid` DTO as well.

## 3. Three easily confused cases: `@Valid`, direct constraints, and conversion errors

### 3.1. Only `@Valid @RequestBody`: usually `MethodArgumentNotValidException`

~~~java
@PostMapping("/dto-only")
public String create(@Valid @RequestBody CreateRequest body) {
    return body.customerCode();
}
~~~

Suppose `CreateRequest` is a record:

~~~java
public record CreateRequest(
        @NotBlank String customerCode,
        @Min(1) int quantity) {
}
~~~

Both snippets are illustrative; full code is in section 6. If you send JSON:

~~~json
{
  "customerCode": "",
  "quantity": 0
}
~~~

Jackson can deserialize the object, and then `@Valid` instructs Bean Validation to check the DTO. When **no other direct constraint makes method-level validation necessary**, errors typically go through `MethodArgumentNotValidException`. That exception is tied to a **single object argument** and its `BindingResult`.

### 3.2. Adding a direct constraint: becomes method-level validation

~~~java
@PostMapping("/checkout")
public Receipt checkout(
        @Valid @RequestBody CreateRequest body,
        @RequestParam("channel")
        @Pattern(regexp = "web|store") String channel) {
    return new Receipt(body.customerCode(), body.quantity(), channel);
}
~~~

`@Pattern` on the `channel` parameter is a **direct** constraint. In MVC 6.1+, method validation can replace the DTO's standalone validation step to **evaluate both `channel` and constraints inside `body`**. With an invalid body and `channel=other`, `HandlerMethodValidationException` carries results grouped by the affected **method parameters**.

This does not mean Spring validates twice. Spring MVC coordinates argument validation and method validation to avoid duplication when method-level validation is the right path.

### 3.3. Unparseable input: never reaches Bean Validation

~~~text
GET /api/items/not-a-number?count=2
               |
               v
@PathVariable long id
               |
         Type conversion FAILED
               |
               v
MethodArgumentTypeMismatchException
               |
             HTTP 400
~~~

A string that cannot parse into `long` is an **argument resolution / conversion** error. Never test it expecting a `@Min(1)` `ConstraintViolation`: Spring does not yet have a valid `long` value to pass to `@Min`.

| Scenario | Checking mechanism | Typical exception |
|---|---|---|
| `@Valid @RequestBody Dto`, object-only validation | Argument-level Bean Validation | `MethodArgumentNotValidException` |
| `@Min(1) @RequestParam int page`, sending `0` | Built-in handler method validation | `HandlerMethodValidationException` |
| `@NotBlank @RequestHeader String code`, sending empty header | Built-in handler method validation | `HandlerMethodValidationException` |
| `@NotNull` on return value, method returns `null` | Built-in handler return-value validation | `HandlerMethodValidationException` |
| `@RequestParam int page`, sending `abc` | Type conversion | `MethodArgumentTypeMismatchException` |
| Missing required `@RequestParam` | Argument resolution | `MissingServletRequestParameterException` |
| Unparseable JSON body | HTTP message conversion | `HttpMessageNotReadableException` |
| `@Validated` service called via AOP proxy | Spring AOP method validation | Usually `ConstraintViolationException` by default |

This table describes **default Spring MVC paths**. Applications can alter error handling through `@ControllerAdvice`, providers, and AOP configuration. So when debugging, always determine **which phase the error originated in**.

## 4. Structure of `HandlerMethodValidationException`

`HandlerMethodValidationException` extends `ResponseStatusException` and implements `MethodValidationResult` as well as `ErrorResponse`. Thus the exception carries both **HTTP status/problem details** and **grouped validation errors per parameter**.

Useful APIs in Spring Framework 6.2:

| API | Meaning |
|---|---|
| `ex.getStatusCode()` | HTTP status: **400** when input parameters fail, **500** when return value fails |
| `ex.isForReturnValue()` | `true` if this is a return-value violation; `false` if input |
| `ex.getMethod()` | The Java `Method` being validated |
| `ex.getTarget()` | Target of the method invocation |
| `ex.getParameterValidationResults()` | List of `ParameterValidationResult`, grouped **by parameter / return descriptor** with errors |
| `ex.getCrossParameterValidationResults()` | Cross-parameter errors, if a constraint evaluates multiple parameters together |
| `ex.getAllErrors()` | Validation errors as `MessageSourceResolvable`/corresponding result model |
| `ex.visitResults(visitor)` | Visits results by controller argument type such as `@RequestParam`, `@RequestHeader`, `@ModelAttribute` |
| `ex.getBody()` | `ProblemDetail` per the `ErrorResponse` contract; can be configured/localized |
| `ex.getDetailMessageArguments(...)` | Arguments for interpolating error messages, with overloads taking `MessageSource` and `Locale` |

**The number of `ParameterValidationResult` entries does not necessarily equal the number of violations.** A `@Valid` DTO with two invalid fields can still appear as **one parameter result** containing two field errors. Conversely, two different failing `@RequestParam`s typically produce two parameter results. To display messages for every error, traverse deeper rather than merely calling `size()`.

Example of checking status:

~~~java
HandlerMethodValidationException ex = /* caught exception */;

int status = ex.getStatusCode().value();
boolean isReturnFailure = ex.isForReturnValue();
int affectedParameters =
    ex.getParameterValidationResults().size();
~~~

This is an **API-explaining snippet** inside an exception handler, not a standalone Java class. When building client-facing APIs, expose **which input was invalid** rather than leaking internal Java method/provider details.

### 4.1. `ParameterValidationResult` and `ParameterErrors`

`ParameterValidationResult` represents errors tied to **one validated parameter**; from it you can access method parameter metadata, the argument value, and a list of `MessageSourceResolvable` errors. When the argument is a bean validated via nested `@Valid`, MVC can use `ParameterErrors` to represent **field/object errors** similarly to Spring's `Errors`.

Conceptual layout:

~~~text
HandlerMethodValidationException
├── ParameterValidationResult: @PathVariable id
│   └── @Min(1) failed
├── ParameterValidationResult: @RequestParam page
│   └── @Min(1) failed
└── ParameterErrors: @RequestBody CreateRequest (if present)
    ├── customerCode -> @NotBlank
    └── quantity -> @Min(1)
~~~

This diagram shows an **illustrative composite scenario**, not an assertion that one specific handler has all three inputs above. Results are structured validation data, not log lines or raw `ConstraintViolationException` strings needing message parsing.

### 4.2. `Visitor`: classifying errors by controller annotation

For APIs returning different error shapes for query, header, model attribute, etc., Spring provides a visitor. Abbreviated snippet for use inside a handler:

~~~java
ex.visitResults(
    new HandlerMethodValidationException.Visitor() {

        @Override
        public void requestParam(
                RequestParam annotation,
                ParameterValidationResult result) {
            // Error belonging to a @RequestParam parameter.
        }

        @Override
        public void requestHeader(
                RequestHeader annotation,
                ParameterValidationResult result) {
            // Error belonging to @RequestHeader.
        }

        @Override
        public void modelAttribute(
                ModelAttribute annotation,
                ParameterErrors errors) {
            // Field/object errors of @ModelAttribute.
        }

        @Override
        public void other(ParameterValidationResult result) {
            // Fallback for argument types without a dedicated callback.
        }
    }
);
~~~

This is an illustrative snippet needing imports for `HandlerMethodValidationException`, `RequestParam`, `RequestHeader`, `ModelAttribute`, `ParameterValidationResult`, and `ParameterErrors` in real code. Some callback annotation parameters can be `null`, so never blindly dereference the annotation in handling logic; verify signatures against your Spring version.

Spring also supports callbacks for other parameter types such as path variable, request body, and request part. The Visitor avoids forcing every method parameter into a single fixed field-error shape.

If you only need to know the request is invalid to return a minimal response, using the visitor is optional. `getParameterValidationResults()` suffices for counting by parameter; the visitor shines when generating normalized messages/paths.

## 5. HTTP 400 and HTTP 500: not an arbitrary difference

By Spring Framework's API contract, `HandlerMethodValidationException.getStatusCode()` returns:

- **HTTP 400 Bad Request** when **method input** violates constraints.
- **HTTP 500 Internal Server Error** when a **method return value** violates constraints.

Example:

~~~java
@GetMapping("/profiles/{id}")
@NotNull
public ProfileDto find(@PathVariable("id") @Min(1) long id) {
    return repository.findById(id).orElse(null);
}
~~~

This is an illustrative method needing a `ProfileDto` and suitable `repository`; it is not part of the runnable demo below. Two paths:

1. `id=0` → input violates `@Min(1)`, handler does not run → **400**.
2. `id=5` → input is valid; handler runs and returns `null`, violating `@NotNull` on return → **500**.

Note that a **non-existent resource** should normally be handled in business logic (such as HTTP 404) rather than deliberately returning `null` and relying on `@NotNull` to generate 500. Return-value validation expresses **a broken server contract**. A method that already caused side effects does not automatically roll back just because a return-value constraint failed: transaction/side-effect behavior depends on transaction configuration and commit boundaries.

**When customizing responses**, do not hardcode every `HandlerMethodValidationException` to HTTP 400. Always respect `ex.getStatusCode()` or the `status` parameter provided by Spring, because the return-value branch carries distinct server-error semantics.

## 6. Runnable example with Spring Boot 3.4+ and Java 17+

The sample application demonstrates:

- GET `/api/items/{id}` with `@Min` on a path variable and query parameter.
- POST `/api/dto-only` with only `@Valid @RequestBody` to observe `MethodArgumentNotValidException`.
- POST `/api/checkout?channel=...` with `@Valid @RequestBody` **and** a direct `@Pattern` constraint to observe `HandlerMethodValidationException`.
- GET `/api/broken` with return-value `@NotNull` intentionally returning `null` to prove HTTP 500.
- A `@RestControllerAdvice` unifying the JSON response while preserving exception types and statuses.

The example is designed for **Spring Boot 3.4/3.5, Spring Framework 6.2, Java 17+** with web/validation dependencies. Class-level `@Validated` is not used on the controller. Files are placed in the same `com.example.mvcmethodvalidation` package so Spring component scan discovers them.

### 6.1. Gradle dependencies

In a Spring Boot project already configured with the Boot Gradle plugin and dependency management, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

`spring-boot-starter-web` provides Servlet MVC/web server, while the validation starter provides the Jakarta Validation provider. Without a provider, constraint annotations are just metadata and will not suffice for the method validation demo.

Run through the Gradle wrapper of a valid Boot project; **plain `javac` from the JDK cannot compile** classes importing Spring/Jakarta without supplying the full dependency classpath.

### 6.2. File `MvcMethodValidationApplication.java`

Path: `src/main/java/com/example/mvcmethodvalidation/MvcMethodValidationApplication.java`

~~~java
package com.example.mvcmethodvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcMethodValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcMethodValidationApplication.class, args);
    }
}
~~~

### 6.3. DTO `CheckoutRequest.java`

Path: `src/main/java/com/example/mvcmethodvalidation/CheckoutRequest.java`

~~~java
package com.example.mvcmethodvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CheckoutRequest(
    @NotBlank String customerCode,
    @Min(1) int quantity
) {
}
~~~

`customerCode` must not be empty/whitespace, and `quantity` must be at least 1. Java records simplify JSON deserialization and validation; constraints attach to record components/constructors/properties per the corresponding Java annotation targets.

### 6.4. Controller `DemoController.java`

Path: `src/main/java/com/example/mvcmethodvalidation/DemoController.java`

~~~java
package com.example.mvcmethodvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {

    @GetMapping("/items/{id}")
    public ItemView findItem(
            @PathVariable("id") @Min(1) long id,
            @RequestParam(
                name = "count", defaultValue = "1")
            @Min(1) @Max(10) int count) {

        return new ItemView(id, count);
    }

    @PostMapping("/dto-only")
    public Receipt dtoOnly(
            @Valid @RequestBody CheckoutRequest request) {

        return new Receipt(
            request.customerCode(),
            request.quantity(),
            "direct");
    }

    @PostMapping("/checkout")
    public Receipt checkout(
            @Valid @RequestBody CheckoutRequest request,
            @RequestParam("channel")
            @Pattern(regexp = "web|store") String channel) {

        return new Receipt(
            request.customerCode(),
            request.quantity(),
            channel);
    }

    @GetMapping("/broken")
    @NotNull
    public String brokenReturnValue() {
        return null;
    }

    public record ItemView(long id, int count) {
    }

    public record Receipt(
        String customerCode,
        int quantity,
        String channel
    ) {
    }
}
~~~

Key differences:

1. `@Min(1)` on `id`/`count` are constraints **directly on method parameters**, triggering MVC method validation.
2. `@Valid` in `dtoOnly` requests DTO validation yet **does not** create a direct parameter constraint itself; that case usually follows argument-level validation.
3. `@Pattern` on `channel` makes `checkout` require **method validation**, which can also include cascading from `@Valid CheckoutRequest`.
4. `@NotNull` on `brokenReturnValue` is a constraint **on the method return value**, checked after the controller method executes.
5. There is no class-level `@Validated`, because the goal is **built-in Spring MVC method validation**, not AOP service validation.

If Spring Security or additional advice/proxies are added in a real project, check their configurations; this plain demo uses only Spring Web + Validation.

### 6.5. Advice `ApiErrors.java`: handling both error kinds separately

Path: `src/main/java/com/example/mvcmethodvalidation/ApiErrors.java`

~~~java
package com.example.mvcmethodvalidation;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrors extends ResponseEntityExceptionHandler {

    public record ApiError(
        String code,
        int status,
        boolean returnValue,
        int affectedParameters
    ) {
    }

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ApiError body = new ApiError(
            "METHOD_VALIDATION",
            status.value(),
            ex.isForReturnValue(),
            ex.getParameterValidationResults().size());

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        ApiError body = new ApiError(
            "ARGUMENT_VALIDATION",
            status.value(),
            false,
            1);

        return handleExceptionInternal(
            ex, body, headers, status, request);
    }
}
~~~

This is a **complete class** for the Spring Framework 6.2 demo. `ResponseEntityExceptionHandler` already has a central `@ExceptionHandler` covering many Spring MVC exceptions; we **override its protected methods** to customize body construction rather than registering a duplicate `@ExceptionHandler(HandlerMethodValidationException.class)` inside the same subclass.

The `affectedParameters` field counts **the number of arguments with error groups**. It does **not** represent the count of individual constraint violations: a `CheckoutRequest` with two invalid fields is still one method parameter. For `MethodArgumentNotValidException` on a single DTO, the demo returns `1` because one object argument failed.

The example uses the status supplied by the framework: if return-value validation fails, `status.value()` is **500**; if input fails, it is **400**. Never "fix" 500 to 400 simply because both involve validation.

In a real product, the body should include user-safe details such as path/field/messageCode and a correlation ID. The demo intentionally returns only the count of failing parameter groups so it **does not depend on message interpolator language** or error ordering.

### 6.6. Running the program and observing responses

From the root of a Spring Boot project with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

The application uses port 8080 by default unless configured otherwise. With valid input:

~~~bash
curl -i "http://localhost:8080/api/items/12?count=3"
~~~

Expected **HTTP 200** and JSON (property ordering may vary):

~~~json
{
  "id": 12,
  "count": 3
}
~~~

Input with **two failing parameter groups**:

~~~bash
curl -i "http://localhost:8080/api/items/0?count=0"
~~~

Expected **HTTP 400** and JSON:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedParameters": 2
}
~~~

Standalone DTO failure (no other direct method constraints):

~~~bash
curl -i -X POST "http://localhost:8080/api/dto-only" \
  -H "Content-Type: application/json" \
  -d '{"customerCode":"","quantity":0}'
~~~

Expected **HTTP 400** and JSON:

~~~json
{
  "code": "ARGUMENT_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedParameters": 1
}
~~~

Mixed direct constraint and nested DTO:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/checkout?channel=other" \
  -H "Content-Type: application/json" \
  -d '{"customerCode":"","quantity":0}'
~~~

Expected **HTTP 400** with:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 400,
  "returnValue": false,
  "affectedParameters": 2
}
~~~

`CheckoutRequest` has **two field violations** and `channel` has **one direct violation**; however, `affectedParameters` is **2** because two method parameters were affected. This is an important distinction when designing error contracts.

Testing return-value violation:

~~~bash
curl -i "http://localhost:8080/api/broken"
~~~

Expected **HTTP 500** with:

~~~json
{
  "code": "METHOD_VALIDATION",
  "status": 500,
  "returnValue": true,
  "affectedParameters": 1
}
~~~

`brokenReturnValue()` executed and returned `null`; the error belongs to the **server contract**, so the framework chooses 500. This is an **intentionally broken** endpoint for learning the mechanism, not a business API design pattern.

**Do not interpret a 400 response from `page=abc` as the same handling path as `@Min`.** That is usually a type conversion exception; the demo advice only replaces bodies for the two validation exceptions, so other error types may be handled by the base `ResponseEntityExceptionHandler` using default `ProblemDetail`.

## 7. Testing Spring MVC with MockMvc

A unit test directly calling `new DemoController().findItem(0, 0)` will **not** trigger argument resolution or built-in MVC method validation. You must test through `MockMvc` or real HTTP.

File: `src/test/java/com/example/mvcmethodvalidation/MethodValidationMvcTest.java`

~~~java
package com.example.mvcmethodvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MethodValidationMvcTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validInputPasses() throws Exception {
        mvc.perform(get("/api/items/12")
                .param("count", "3"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(12))
            .andExpect(jsonPath("$.count").value(3));
    }

    @Test
    void directConstraintsUseMethodValidation()
            throws Exception {
        mvc.perform(get("/api/items/0")
                .param("count", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedParameters")
                .value(2))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void dtoOnlyUsesArgumentValidation()
            throws Exception {
        mvc.perform(post("/api/dto-only")
                .contentType("application/json")
                .content(
                    "{\"customerCode\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("ARGUMENT_VALIDATION"))
            .andExpect(result -> assertInstanceOf(
                MethodArgumentNotValidException.class,
                result.getResolvedException()));
    }

    @Test
    void directConstraintAlsoValidatesNestedDto()
            throws Exception {
        mvc.perform(post("/api/checkout")
                .param("channel", "other")
                .contentType("application/json")
                .content(
                    "{\"customerCode\":\"\",\"quantity\":0}"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.affectedParameters")
                .value(2))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
    }

    @Test
    void invalidReturnValueIsServerError()
            throws Exception {
        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(jsonPath("$.code")
                .value("METHOD_VALIDATION"))
            .andExpect(jsonPath("$.returnValue").value(true))
            .andExpect(result -> assertInstanceOf(
                HandlerMethodValidationException.class,
                result.getResolvedException()));
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

With Spring Boot 3.4/3.5, Spring Framework 6.2, the Validation starter, and no class-level `@Validated` on the controller, all five tests are expected to **PASS**. The tests directly verify the **resolved MVC exception class** alongside HTTP status/body, so another exception accidentally producing the same 400 code cannot slip by unnoticed.

When applying to a real project with Spring Security, custom filters, other `@ControllerAdvice` classes, or AOP proxy configurations, tests may need matching setup. If using Boot 4 / Spring Framework 7, check test imports/modules and API compatibility before copying.

## 8. `BindingResult`, `Errors`, and local handling rules

Not every violation must become an exception. Spring MVC lets you combine method validation with `Errors` or `BindingResult` on model/DTO arguments.

Example:

~~~java
@PostMapping("/preview")
public String preview(
        @Valid @ModelAttribute("form") PreviewForm form,
        BindingResult errors,
        @RequestParam("priority") @Min(1) int priority) {

    if (errors.hasErrors()) {
        return "preview-form";
    }
    return "preview-result";
}
~~~

This is an **illustrative handler inside a view-rendering `@Controller`**, requiring a `PreviewForm` DTO and proper imports; it is not part of the runnable project in section 6. `BindingResult` sits **immediately after** `form` so it can receive errors for that object.

Spring MVC's rule when method validation is required:

- The handler can still be invoked if **all validation errors** belong to method parameters that have `Errors`/`BindingResult` **immediately following** them and are handled locally.
- If there is an error on **any other parameter** lacking a corresponding `Errors`, the framework throws `HandlerMethodValidationException` and the handler is not invoked.
- `BindingResult` is not a general-purpose catcher for a primitive `@RequestParam int`. It binds to a specific object argument rather than automatically collecting errors from all parameters in the signature.

In the snippet above, if `form` is invalid while `priority=2` is valid, the controller can inspect `errors` to re-render the view. If `priority=0`, the direct constraint on `priority` fails and Spring can throw `HandlerMethodValidationException` even though `form` has `BindingResult` right after it.

When using `@RequestBody` or `@ModelAttribute` with validation, always inspect **`BindingResult` placement** and **any other direct constraints** in the handler signature. Never guess the exception class just by looking at `@Valid` on one parameter.

## 9. `ResponseEntityExceptionHandler` and `@RestControllerAdvice`

Spring provides `ResponseEntityExceptionHandler` to handle common Spring MVC exceptions. In Spring Framework 6.2, the dedicated method for this case has the signature:

~~~java
protected ResponseEntity<Object>
    handleHandlerMethodValidationException(
        HandlerMethodValidationException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request)
~~~

Because the method is `protected` and the base class already defines the central `@ExceptionHandler`, the proper extension pattern is:

~~~java
@RestControllerAdvice
public class GlobalErrors extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object>
            handleHandlerMethodValidationException(
            HandlerMethodValidationException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        return handleExceptionInternal(
            ex,
            ex.getBody(),
            headers,
            status,
            request
        );
    }
}
~~~

This is an **alternative** example to `ApiErrors.java` in section 6; do not register two overriding advice classes simultaneously unless intentional. The illustrative snippet needs full imports as in `ApiErrors`. It preserves the standard `ProblemDetail` from the exception; real projects can enrich it per API contract while avoiding leaking sensitive data.

### Why not just write `@ExceptionHandler(Exception.class)`?

A catch-all exception handler easily obscures the difference between:

- Input validation (400).
- Return-value contract violation (500).
- Argument type mismatch / malformed JSON (400, yet a **different category**).
- Not-found domain errors (typically 404 by design).
- Internal non-validation failures (500).

Returning 200 or 400 for everything makes it hard for clients and observability tools to separate user errors from server bugs. Structured exception handling preserving accurate statuses is much better.

### `ProblemDetail` and RFC 9457

`HandlerMethodValidationException` implements `ErrorResponse` and carries a `ProblemDetail`. `ResponseEntityExceptionHandler` supports creating RFC 9457 **problem details** responses, including core fields like `type`, `title`, `status`, `detail`, and `instance` depending on configuration.

If an application chooses a custom contract such as the `ApiError` demo, that is an **application choice**, not the default JSON Spring always returns. Do not write tests asserting fixed `detail` strings or localized messages when the app configures `MessageSource` and changes locales.

### Internationalization and message sources

Validation errors can include `MessageSourceResolvable` instances with message codes/arguments. To display Vietnamese/English messages, use `MessageSource` and proper locale configuration instead of parsing `ex.getMessage()` and showing raw strings.

With constraint message templates, interpolation output can depend on the Jakarta message interpolator and locale. Never expose class names, password/token values, or stack traces directly in public responses. When logging, keep correlation IDs, request paths, and safe error categories instead of logging entire request bodies.

## 10. Validating return values

Input validation normally blocks execution before the handler body runs, whereas return validation runs **after the handler produces a result**. Example:

~~~java
@GetMapping("/inventory")
@NotEmpty
public List<String> inventory() {
    return List.of();
}
~~~

If built-in MVC method validation is configured, an empty list violates return-value `@NotEmpty`. The method has already executed, and the exception has:

~~~java
ex.isForReturnValue() == true
ex.getStatusCode().value() == 500
~~~

This is an illustrative snippet, not a standalone test. For a method accessing/writing to a database, do not assume Spring MVC return validation automatically **rolls back transactions** or undoes side effects that already occurred.

**Do not use return constraints instead of logic returning 404 when data does not exist.** Express "not found" results explicitly in the service/controller per your HTTP contract. Return-value validation is useful for catching broken internal assumptions (e.g., a method promises non-null yet the implementation returns null).

Cases like `ResponseEntity<T>`, streaming, async, and reactive returns require checking **which object** is actually validated and when data is produced/written to the response; do not extrapolate from a simple `String` return example to every async wrapper.

## 11. How does AOP method validation differ from built-in MVC?

Same Jakarta Validation constraints, different execution machinery.

| Characteristic | Built-in Spring MVC (6.1+) | Spring AOP method validation |
|---|---|---|
| Typical target | `@RequestMapping` controller handler | Service/Spring bean configured with `@Validated` |
| Interception point | Inside the MVC handler invocation pipeline | Calls going through a Spring AOP proxy |
| Core components | `HandlerMethodValidator` / MVC infrastructure | `MethodValidationPostProcessor`, `MethodValidationInterceptor` |
| Class-level `@Validated` needed? | **No**; remove from controllers to use built-in | Typically **yes** on the bean |
| Typical input error | `HandlerMethodValidationException` | `ConstraintViolationException` by default |
| Return error | `HandlerMethodValidationException` with status **500** | Exception depends on interceptor configuration |
| `BindingResult`/argument resolver integration | Native in the MVC pipeline | No automatic equivalent |
| Proxy self-invocation limit | No AOP proxy needed just to validate handlers | Calling `this.method()` inside target usually bypasses advice |

AOP service example:

~~~java
@Service
@Validated
public class OrderService {

    public void place(@NotBlank String code) {
        // Business logic.
    }
}
~~~

In a setup with `MethodValidationPostProcessor`, callers must obtain the Spring bean/proxy and invoke through the proxy for method validation to trigger. It does **not** become `HandlerMethodValidationException` merely because the class lives in the same web application. By default, AOP services typically raise `jakarta.validation.ConstraintViolationException`, unless an adapter is configured to translate it into Spring's corresponding exception.

A common deployment mistake is putting `@Validated` at the controller class level per older guides and then expecting HTTP errors to always arrive as Spring MVC 6.1+'s `HandlerMethodValidationException`. Distinguish AOP mode from built-in mode, pick one intentionally, and test the actual exception class.

## 12. `@Valid`, `@Validated`, `@NotNull`, and validation groups

### `@Valid`

`jakarta.validation.Valid` requests cascading validation of an object's properties. It is **not a direct constraint** and is insufficient by itself to trigger built-in method validation as a standalone method constraint. For a DTO with only `@Valid @RequestBody`, the common error type remains `MethodArgumentNotValidException`.

### `@NotNull`

`jakarta.validation.constraints.NotNull` is a real constraint. When placed **directly** on a method argument alongside `@Valid`, `@NotNull` can cause method validation to apply while `@Valid` traverses into the nested object. Do not replace `@NotNull` with `@Valid` expecting null to be rejected: cascade validation does not report a violation when the value is null.

### `@Validated`

`org.springframework.validation.annotation.Validated` is Spring's annotation that can specify validation groups. Using it on a service bean is the standard way to mark a target for AOP method validation. On Spring MVC 6.1+ controllers, **avoid class-level `@Validated`** when wanting built-in handler method validation.

### Groups

Constraints with `groups` are selected according to Jakarta Validation rules. Example:

~~~java
public interface CreateChecks {
}

public record NewOrder(
    @NotBlank(groups = CreateChecks.class)
    String code) {
}
~~~

These are two separate illustrative Java types, not part of the main demo. A handler can use `@Validated(CreateChecks.class)` on a **DTO argument** to request the appropriate group. However, group selection and enabling AOP via class-level `@Validated` are two separate concerns that should not be conflated. Always test both the `Default` group and custom groups so constraints are never accidentally skipped.

## 13. Inspecting each error group to build field/path responses

If an API wants to return a list of field errors instead of just the count of affected parameters, it can build a structure like:

~~~json
{
  "type": "https://example.com/problems/validation",
  "status": 400,
  "errors": [
    {
      "parameter": "count",
      "messageCode": "Min"
    }
  ]
}
~~~

This is an **application-designed JSON model**, not Spring's default output. In practice, you iterate over `ParameterValidationResult` and `MessageSourceResolvable`/`ParameterErrors` to derive:

- **Method argument location**: query, path, header, model attribute, request body.
- **Field name** inside a DTO if nested validation failed.
- **Message code/constraint** rather than only the interpolated message, if clients need localization.
- **Status** corresponding to input vs. return value.
- **Values to redact**: never return passwords, tokens, or private data.

For `@RequestParam`, you can check the annotation's `name()` or `value()` when explicit; when unspecified, use method parameter metadata with a fallback. Never assume `MethodParameter.getParameterName()` is always non-null if bytecode was compiled without `-parameters`. For `@ModelAttribute` and nested constraints, `ParameterErrors`/`FieldError` are far better than assigning one synthetic field name to the whole DTO.

If you only need a standard Spring RFC 9457 response, you can start from `ex.getBody()`/`ResponseEntityExceptionHandler` and add vetted extension properties instead of needlessly reimplementing all error serialization.

## 14. Common real-world mistakes

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@Valid @RequestBody` placed yet exception is `MethodArgumentNotValidException` | Single-object validation only; method validation not needed | This is expected behavior; handle both exceptions |
| Added `@Min` on query param and saw `HandlerMethodValidationException` | Direct constraint activated built-in method validation | Handle the corresponding exception |
| Controller class has `@Validated` and throws `ConstraintViolationException` | Method validation ran via Spring AOP proxy | Remove class-level `@Validated` if wanting MVC 6.1+ built-in |
| `@Min` does not run | Missing validation provider/MVC validator or unsupported version | Check validation starter, Spring version, and bean validator |
| `page=abc` does not appear in validation results | Failed at type conversion step | Catch type mismatch separately |
| HTTP status is 500 despite "validation-related" error | Return-value constraint violated | Check `isForReturnValue()`, fix server logic |
| `getParameterValidationResults().size()` is smaller than message count | One parameter can contain multiple field errors | Iterate results and nested errors; do not use size as total violations |
| `@Valid` and `@NotNull` behave differently | `@Valid` cascades, `@NotNull` is a direct constraint | Declare both intents explicitly when needed |
| Handler has `BindingResult` yet still throws exception | Error on another parameter lacking matching `Errors` | Inspect entire signature and `BindingResult` placement |
| Custom advice always returns 400 | Ignores return-value error status | Use `ex.getStatusCode()` / `status` parameter |
| Duplicate `@ExceptionHandler` mapping with base class | Registered duplicate handler when extending `ResponseEntityExceptionHandler` | Override `handleHandlerMethodValidationException` |
| Unparseable JSON body | Jackson/HTTP message converter error, not a constraint | Handle `HttpMessageNotReadableException` |
| Test calls method directly and sees no exception | Bypassed Spring MVC handler invocation | Use MockMvc/HTTP integration tests |
| Logging raw rejected values | Can leak secrets or user data | Log error codes, safe parameter/path, and correlation ID |
| Returned message changes when locale changes | Message interpolated via MessageSource/validator | Test message codes and i18n config; do not hardcode text |
| Mixing Spring MVC and WebFlux docs | The two web stacks have different infrastructure/error types | Consult Servlet MVC docs matching your exact version |

An effective debugging order:

1. Did the request match the controller handler?
2. Did argument resolution/type conversion succeed?
3. Is a Jakarta Validation provider installed and configured?
4. Does the handler have a **direct constraint** on a parameter/return value, or only `@Valid` on a DTO?
5. Does the controller have class-level `@Validated` routing validation through AOP?
6. Does the handler have `BindingResult`/`Errors` right after an object parameter while another parameter failed?
7. What is the exact exception class, status code, and `isForReturnValue()`?
8. Which advice/error handler caught the exception and did it alter the status/body?
9. Test end-to-end via MockMvc with malformed input, constraint failures, DTO-only, mixed parameters, and return values.

## 15. Self-check exercises

**Exercise 1 — Distinguishing the two exceptions.** With `@Valid @RequestBody CheckoutRequest request` and no other direct constraints, sending a body with `customerCode=""` yields what common exception? — `MethodArgumentNotValidException`, because validation applies to a single object argument.

**Exercise 2 — Adding a direct constraint.** The same handler adds `@RequestParam("channel") @Pattern(...) String channel`. What changes? — Method validation is required and can check both the direct constraint and the nested DTO; errors can go through `HandlerMethodValidationException`.

**Exercise 3 — Conversion.** With `@RequestParam @Min(1) int page`, sending `page=abc` causes which error? — Conversion to `int` fails before validation, not a `@Min` violation.

**Exercise 4 — Two parameter groups.** `@PathVariable @Min(1) long id` and `@RequestParam @Min(1) int count` both receive `0`. How many entries does `getParameterValidationResults()` typically have? — Two entries corresponding to the two method parameters, each with one violation.

**Exercise 5 — Nested DTO.** A `@Valid CheckoutRequest` has two invalid fields. Can you infer `getParameterValidationResults().size() == 2`? — No; one parameter holding multiple field errors can still be a single result.

**Exercise 6 — Return value.** A `@NotNull String code()` handler returns `null`. What are `isForReturnValue()` and the HTTP status? — `true` and **500**, because the server broke its return contract.

**Exercise 7 — `BindingResult`.** If a form DTO is invalid and `BindingResult` sits immediately after it, does the handler always run? — No; only if all validation errors belong to parameters with corresponding `Errors`; an error on another parameter still throws an exception.

**Exercise 8 — AOP.** Why might a controller with class-level `@Validated` not throw `HandlerMethodValidationException`? — Because Spring may use AOP method validation instead of built-in MVC.

**Exercise 9 — Error response.** Should you catch `HandlerMethodValidationException` and always return 400? — No; return-value violations are 500 server errors by contract.

**Exercise 10 — Testing.** Why is `new DemoController().findItem(0,0)` insufficient? — Because it bypasses MVC argument resolvers, validation infrastructure, and exception handlers. You must use MockMvc/HTTP tests.

## 16. Production implementation checklist

- [ ] Use Spring MVC 6.1+ and a compatible Jakarta Validation provider; on Spring Boot 3.4/3.5 add the Validation starter.
- [ ] Pick the right annotation: `@Valid` for cascading DTOs; `@Min`/`@NotBlank`/`@Pattern`... for direct constraints.
- [ ] If wanting built-in MVC method validation, **do not put class-level `@Validated` on the controller**.
- [ ] Understand that method validation can encompass `@Valid` DTOs too when the handler has direct constraints.
- [ ] Handle **both** `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [ ] Separate missing-parameter/type-conversion/JSON-syntax errors from constraint violations.
- [ ] Use `getParameterValidationResults()` properly: grouped by parameter, never assuming it equals individual violation count.
- [ ] For nested DTOs, process `ParameterErrors` and field/object errors if detailed error responses are needed.
- [ ] Respect `getStatusCode()` and `isForReturnValue()`: 400 for input, 500 for return value.
- [ ] Use `ResponseEntityExceptionHandler` overrides or deliberate `@ExceptionHandler` methods, avoiding overlapping mappings.
- [ ] Place `BindingResult` directly after the target object argument and account for errors on other parameters.
- [ ] Never expose rejected secrets, stack traces, class internals, or unvetted messages to clients.
- [ ] Test with MockMvc for valid requests, invalid direct constraints, invalid DTO-only, invalid mixed DTO+direct, and invalid return values.
- [ ] If Spring AOP is present on controllers/services, verify which mechanism actually runs and which exception is thrown.
- [ ] For multi-language support, use message codes and `MessageSource`; verify RFC 9457/`ProblemDetail` responses against the API contract.

**Remember:** `HandlerMethodValidationException` is the signal of **built-in Spring MVC handler method validation** when method-level validation fails. It groups results by parameter, provides a visitor API, and lets you distinguish **400 for input data** from **500 for return values**. Do not confuse it with `MethodArgumentNotValidException` from standalone DTO validation, `MethodArgumentTypeMismatchException` from type conversion, or `ConstraintViolationException` from AOP method validation in services.

## Official references

- [Spring Framework 6.2 — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring API 6.2 — HandlerMethodValidationException](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring API 6.2 — HandlerMethodValidationException.Visitor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.Visitor.html)
- [Spring API 6.2 — ParameterValidationResult](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring API 6.2 — ParameterErrors](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/method/ParameterErrors.html)
- [Spring API 6.2 — ResponseEntityExceptionHandler](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
