# Built-in Method Validation Since Spring Framework 6.1 in Spring MVC

## 1. What did Spring MVC 6.1 change?

Before Spring Framework 6.1, a common way to check constraints on **controller method parameters** was adding `@Validated` at the class level so Spring AOP would intercept method calls and trigger Jakarta Bean Validation. Starting in **Spring Framework 6.1**, Spring MVC provides **built-in method validation** for `@RequestMapping` handlers. This mechanism lives inside Spring MVC's request-processing pipeline, **requiring no AOP proxy to validate handler methods themselves**.

Example handler:

~~~java
@GetMapping("/codes")
public String code(
        @RequestParam @NotBlank String prefix,
        @RequestParam @Min(1) int number) {
    return prefix + "-" + number;
}
~~~

With Spring MVC 6.1+ configured with a suitable Bean Validation provider:

- `GET /codes?prefix=INV&number=3` is valid: the method can execute and return `INV-3`.
- `GET /codes?prefix=&number=3` violates `@NotBlank` on the `prefix` parameter.
- `GET /codes?prefix=INV&number=0` violates `@Min(1)` on the `number` parameter.
- Violations from **built-in MVC method validation** are typically represented by `HandlerMethodValidationException`. Input argument errors correspond to **HTTP 400**.

You can also declare constraints **on the method to validate the return value**:

~~~java
@GetMapping("/broken")
@NotBlank
public String broken() {
    return "";
}
~~~

Here the method body has already run and returned an empty string, after which Spring MVC checks the postcondition. Violations on a **return value** are represented by `HandlerMethodValidationException` with **HTTP 500**, because this is a server-side bug rather than a client input error.

**Key takeaway:** `@Valid` and `@Validated` on a DTO normally trigger validation of that individual object; **direct** constraints like `@NotBlank`, `@Min`, or `@NotNull` on method parameters (or constraints on the method return value) trigger **method validation**. When both exist, method validation encompasses nested constraints via `@Valid` as well.

In this lesson, "Spring Framework 6.1+" refers to the mechanism introduced in 6.1 and continuing in Spring Framework 6.2. The runnable example uses **Java 17 / Spring Boot 3.5.7 / Spring Framework 6.2**, with `jakarta.validation.*` annotations and packages. Do not mix legacy Javax Validation code from Spring Boot 2.x into the example.

## 2. Distinguishing two validation paths in Spring MVC

Since 6.1, the same controller can encounter **two different validation styles**. Choosing the right path determines the exception type, how error details are extracted, and how HTTP responses are handled.

| Case | Mechanism typically applied | Typical exception | Default HTTP |
| --- | --- | --- | --- |
| `@Valid @RequestBody OrderInput`, no other direct method constraints | Individual request object validation | `MethodArgumentNotValidException` | 400 |
| `@Valid @ModelAttribute OrderForm`, no immediately following `BindingResult` and no direct method constraints | Individual model attribute validation | `MethodArgumentNotValidException` | 400 |
| `@RequestParam @Min(1) int quantity` | Built-in **method validation** | `HandlerMethodValidationException` | 400 |
| `@RequestHeader @NotBlank String token` | Built-in method validation | `HandlerMethodValidationException` | 400 |
| `@RequestParam @Min(1) int priority` alongside `@Valid @RequestBody OrderInput body` | Built-in method validation, including nested validation of `body` | `HandlerMethodValidationException` | 400 |
| `@NotBlank` on a method returning `String` | Built-in return-value method validation | `HandlerMethodValidationException` | 500 |
| `@RequestParam int quantity` receiving `"abc"` | Type conversion/binding **before validation** | Possibly `MethodArgumentTypeMismatchException` | 400 |
| `@RequestParam(required=true) String name` missing | Request argument resolution, **before validation** | Possibly `MissingServletRequestParameterException` | 400 |

Do not treat the table as "every annotation always causes that exact exception". Trigger conditions vary by handler signature, `Errors`/`BindingResult` placement, presence of a provider, and integration setup. The table reflects common Spring MVC 6.1/6.2 scenarios.

### 2.1. Why doesn't `@Valid` alone trigger method validation?

Jakarta Validation's `@Valid` is a **cascade** annotation requesting validation of a nested object's constraints. It is **not a `@Constraint`**. In contrast, `@NotNull`, `@NotBlank`, and `@Min` are constraint annotations.

~~~java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderInput body) {
    // One request object is validated individually.
}
~~~

If there are no other direct method constraints, Spring MVC can validate `body` through the argument resolver mechanism; when the object has errors and no `Errors`/`BindingResult` immediately follows it, `MethodArgumentNotValidException` is normally thrown.

If you additionally declare:

~~~java
@PostMapping("/orders")
public void create(
        @RequestParam @Min(1) int priority,
        @Valid @RequestBody OrderInput body) {
    // Both direct constraints and the nested object must be validated.
}
~~~

`@Min(1)` makes method validation necessary. **Method validation replaces the object-only path** because it covers both the direct constraint on `priority` and nested constraints inside `body`. On violation, Spring MVC uses `HandlerMethodValidationException`, rather than automatically raising two separate exceptions for the two parameters.

### 2.2. `@NotNull` and `required` are not completely identical

~~~java
@RequestParam(required = true) String name
~~~

When the request parameter does not exist, Spring MVC can report an error right at **argument resolution**, before Bean Validation ever receives a value. Meanwhile:

~~~java
@RequestParam(required = false) @NotNull String name
~~~

allows the resolver to supply `null`, yet the `@NotNull` constraint detects it when method validation runs. Both options can end up returning HTTP 400, **but the processing path, exception, and error content are not necessarily identical**.

Likewise, `@Valid` does not forbid `null` on its own. If a handler actually accepts `null` during resolution, use an appropriate constraint such as `@NotNull` when needed. With `@RequestBody(required=true)`, a missing body can be rejected before validation takes place.

## 3. Internal MVC processing flow

~~~text
HTTP request
  |
  v
DispatcherServlet
  |
  v
HandlerMapping selects @RequestMapping method
  |
  v
HandlerAdapter resolves method arguments
  |  - @RequestParam / @PathVariable / @RequestHeader
  |  - @RequestBody via HttpMessageConverter (Jackson)
  |  - @ModelAttribute via WebDataBinder
  |  - Type conversion, missing argument checks, and binding errors
  |
  +--> If only @Valid is present for a command object:
  |       argument resolver can validate the object individually
  |       and throw MethodArgumentNotValidException
  |
  v
If the method requires built-in method validation:
  HandlerMethodValidator checks direct parameters
  and nested constraints declared via @Valid
  |
  +--> Violation on an argument NOT handled in place
  |       -> HandlerMethodValidationException (400)
  |
  v
Invoke controller method body
  |
  v
If return-value constraints exist: validate return value
  |
  +--> Violation on return
  |       -> HandlerMethodValidationException (500)
  |
  v
Response rendering: String/JSON/ModelAndView...
~~~

The diagram is a generalized model assuming no custom resolvers/interceptors. Spring processes each argument kind through its appropriate mechanism before invoking the method; method validation does not replace **JSON deserialization**, **data binding**, **type conversion**, or **authorization checks**.

In Spring Framework 6.1+, the MVC method validation component is `HandlerMethodValidator`, and the error object is `HandlerMethodValidationException`. `HandlerMethodValidationException` implements `MethodValidationResult`: it carries metadata about the method, target, each parameter, cross-parameter errors, and a flag indicating whether the violation is on the return value.

Comparison with Spring AOP method validation:

- Built-in Spring MVC validation processes **handler methods** as part of request dispatching.
- Spring AOP uses `MethodValidationPostProcessor`, typically for **service beans** with class-level `@Validated` and calls going through a proxy.
- AOP service validation normally throws `jakarta.validation.ConstraintViolationException` by default, or `MethodValidationException` if adaptation is configured. **Do not conflate** those two with MVC's `HandlerMethodValidationException`.
- Calling `this.serviceMethod(...)` inside a service can bypass the Spring proxy; MVC dispatch does not rely on self-invocation to trigger built-in handler validation.

## 4. Conditions and how to enable built-in method validation

To operate under the new MVC mechanism, you need:

1. An application using **Spring Framework 6.1 or newer** with Spring MVC `@RequestMapping` controllers.
2. A suitable Jakarta Bean Validation provider (such as Hibernate Validator). In Spring Boot 3.x, use `spring-boot-starter-validation`.
3. **Direct constraints on handler parameters** such as `@Min`, `@NotBlank`, or constraints on the method's **return value**. Plain `@Valid` alone is not this trigger.
4. **Remove `@Validated` at the controller class level** when you want built-in MVC method validation. Keeping the class-level annotation causes method validation to take the **AOP proxy** path, contrary to the migration goal.
5. Valid types/binding for the handler signature and request arguments so execution reaches method validation. If conversion fails earlier, a different exception occurs.

Correct example for the new mechanism:

~~~java
@RestController
@RequestMapping("/api")
class ApiController {
    @GetMapping("/greet")
    public String greet(@RequestParam @NotBlank String name) {
        return "Hello " + name;
    }
}
~~~

**Do not add `@Validated` on `ApiController`**. `@RestController` combines `@Controller` and `@ResponseBody`; it is not an annotation that triggers constraints on its own, though it is the standard way to declare REST handlers.

Example that causes confusion during upgrades:

~~~java
@RestController
@Validated // Class-level AOP mechanism, not MVC built-in.
class LegacyController {
    @GetMapping("/greet")
    String greet(@RequestParam @NotBlank String name) {
        return "Hello " + name;
    }
}
~~~

When upgrading from Spring 6.0 to 6.1+, review why `@Validated` was used: if it was only added to check direct method constraints, consider **removing it at the class level** and letting handlers use the built-in mechanism. After removing it, **re-check exception handlers and validation groups**; do not assume all legacy behavior stays unchanged.

## 5. Complete, runnable Spring Boot 3.5.7 project

This example implements both validation paths, return validation, and a case where `BindingResult` works alongside direct constraints. It uses **Java 17**, Maven, and Spring Boot 3.5.7.

### 5.1. File layout

~~~text
pom.xml
src/main/java/com/example/mvcvalidation/
  MvcValidationApplication.java
  OrderInput.java
  OrderController.java
src/test/java/com/example/mvcvalidation/
  OrderControllerTest.java
~~~

No database is needed, no manual `MethodValidationPostProcessor` bean is needed, and `spring-boot-starter-aop` is not needed solely to validate handlers via built-in MVC validation.

### 5.2. Maven

~~~xml
<!-- pom.xml -->
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
    <artifactId>mvc-method-validation</artifactId>
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
</project>
~~~

`spring-boot-starter-web` provides Spring MVC, JSON deserialization, and the embedded server; `spring-boot-starter-validation` puts the Jakarta Validation implementation on the classpath; `spring-boot-starter-test` provides JUnit 5 and `MockMvc`. Do not declare `@EnableWebMvc` so Spring Boot's default MVC configuration is preserved.

### 5.3. Application

~~~java
// src/main/java/com/example/mvcvalidation/MvcValidationApplication.java
package com.example.mvcvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MvcValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(MvcValidationApplication.class, args);
    }
}
~~~

### 5.4. Shared DTO for JSON and form

~~~java
// src/main/java/com/example/mvcvalidation/OrderInput.java
package com.example.mvcvalidation;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class OrderInput {

    @NotBlank(message = "Product code must not be blank")
    private String productCode;

    @NotNull(message = "Quantity is required")
    @Min(value = 1, message = "Minimum quantity is 1")
    private Integer quantity;

    public OrderInput() {
    }

    public String getProductCode() {
        return productCode;
    }

    public void setProductCode(String productCode) {
        this.productCode = productCode;
    }

    public Integer getQuantity() {
        return quantity;
    }

    public void setQuantity(Integer quantity) {
        this.quantity = quantity;
    }
}
~~~

The DTO has a public no-args constructor and getters/setters so Jackson can read JSON and `WebDataBinder` can process HTML forms. In a real project, an input DTO should only contain fields allowed from the client, never binding directly to an entity with sensitive properties.

### 5.5. Controller: five scenarios in one class

~~~java
// src/main/java/com/example/mvcvalidation/OrderController.java
package com.example.mvcvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.MediaType;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class OrderController {

    // 1. Direct method parameter constraints.
    @GetMapping("/codes")
    public String code(
            @RequestParam @NotBlank String prefix,
            @RequestParam @Min(1) int serial) {
        return prefix + "-" + serial;
    }

    // 2. Return-value method constraint.
    @GetMapping("/broken")
    @NotBlank(message = "Result must not be blank")
    public String broken() {
        return ""; // Intentionally invalid to observe HTTP 500 error.
    }

    // 3. Validate only a request DTO: object-only validation.
    @PostMapping(
            path = "/orders/object",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public String objectOnly(@Valid @RequestBody OrderInput input) {
        return input.getProductCode();
    }

    // 4. Direct constraint present; MVC method validation includes @Valid DTO.
    @PostMapping(
            path = "/orders/method",
            consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public String withMethodValidation(
            @RequestParam @Min(1) int priority,
            @Valid @RequestBody OrderInput input) {
        return input.getProductCode() + ":" + priority;
    }

    // 5. BindingResult immediately after @ModelAttribute.
    @PostMapping(
            path = "/orders/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public String formWithLocalErrors(
            @RequestParam @Min(1) int priority,
            @Valid @ModelAttribute("orderInput") OrderInput input,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return "errors:" + errors.getErrorCount();
        }
        return "ok:" + input.getProductCode();
    }
}
~~~

**There is no class-level `@Validated`** on `OrderController`. This is intentional for the example.

Walking through each one:

- `GET /api/codes`: `@NotBlank` and `@Min` are direct constraints on method parameters. When invalid and no matching `BindingResult` exists, Spring MVC creates `HandlerMethodValidationException` (400).
- `GET /api/broken`: the method returns `""`, and the `@NotBlank` constraint on the method fails on the **return value**; the exception is `HandlerMethodValidationException` with status 500.
- `POST /api/orders/object`: only `@Valid @RequestBody`, with no direct method constraints. When `OrderInput` is invalid, Spring MVC normally throws `MethodArgumentNotValidException`.
- `POST /api/orders/method`: has `@Min(1)` directly on `priority`; therefore method validation checks both `priority` and nested constraints of `OrderInput`, reporting `HandlerMethodValidationException`.
- `POST /api/orders/form`: has direct constraint `@Min(1)`, while `BindingResult` is placed **immediately after `@ModelAttribute`**. If only errors inside `OrderInput` occur, the method can still be invoked to handle `errors`. If `priority` is also invalid, method validation throws an exception because **there is no `Errors` immediately after the `priority` parameter**.

`BindingResult` in a form handler **does not globally handle errors for the whole method**. It only binds to the model attribute parameter right before it. This rule is especially important when a handler has multiple objects and direct parameter constraints.

### 5.6. MockMvc integration test

~~~java
// src/test/java/com/example/mvcvalidation/OrderControllerTest.java
package com.example.mvcvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validDirectParameters() throws Exception {
        mvc.perform(get("/api/codes")
                .param("prefix", "INV")
                .param("serial", "3"))
            .andExpect(status().isOk())
            .andExpect(content().string("INV-3"));
    }

    @Test
    void directParameterViolationsUseMvcMethodValidation()
            throws Exception {
        mvc.perform(get("/api/codes")
                .param("prefix", " ")
                .param("serial", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());
                assertFalse(ex.isForReturnValue());
                assertFalse(ex.getParameterValidationResults().isEmpty());
            });
    }

    @Test
    void invalidReturnIsServerError() throws Exception {
        mvc.perform(get("/api/broken"))
            .andExpect(status().isInternalServerError())
            .andExpect(result -> {
                var ex = assertInstanceOf(
                        HandlerMethodValidationException.class,
                        result.getResolvedException());
                assertTrue(ex.isForReturnValue());
            });
    }

    @Test
    void objectOnlyValidationHasArgumentException()
            throws Exception {
        mvc.perform(post("/api/orders/object")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productCode":"","quantity":2}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                    MethodArgumentNotValidException.class,
                    result.getResolvedException()));
    }

    @Test
    void methodConstraintAlsoValidatesNestedDto()
            throws Exception {
        mvc.perform(post("/api/orders/method")
                .param("priority", "1")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"productCode":"","quantity":2}
                    """))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                    HandlerMethodValidationException.class,
                    result.getResolvedException()));
    }

    @Test
    void bindingResultHandlesOnlyItsOwnArgument()
            throws Exception {
        mvc.perform(post("/api/orders/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("priority", "1")
                .param("productCode", "")
                .param("quantity", "2"))
            .andExpect(status().isOk())
            .andExpect(content().string("errors:1"));
    }

    @Test
    void otherInvalidMethodParameterStillThrows()
            throws Exception {
        mvc.perform(post("/api/orders/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("priority", "0")
                .param("productCode", "")
                .param("quantity", "2"))
            .andExpect(status().isBadRequest())
            .andExpect(result -> assertInstanceOf(
                    HandlerMethodValidationException.class,
                    result.getResolvedException()));
    }
}
~~~

The tests use Java 17 **text blocks** for JSON. Key assertions check not only the HTTP status, but also verify the **exact exception class** and, for the return case, that `ex.isForReturnValue()` is `true`.

Run from the directory containing `pom.xml`:

~~~bash
mvn test
~~~

**Expected** outcome: all 7 tests PASS with the stated default configuration. Specifically: valid direct arguments return 200; invalid direct arguments return 400/`HandlerMethodValidationException`; invalid return returns 500; object-only invalid returns 400/`MethodArgumentNotValidException`; mixed validation returns 400/`HandlerMethodValidationException`; `BindingResult` lets the handler process form errors; invalid other method parameter still returns 400. Maven/Surefire logs are not hardcoded because they depend on the execution environment. The cases were reviewed for API usage and expected behavior, though this write-up does not claim an actual Maven run was executed.

To start the HTTP server and test manually:

~~~bash
mvn spring-boot:run
~~~

Then:

~~~bash
curl -i "http://localhost:8080/api/codes?prefix=INV&serial=3"
curl -i "http://localhost:8080/api/codes?prefix=&serial=0"
curl -i "http://localhost:8080/api/broken"
~~~

The valid request returns body `INV-3`; the second request receives 400; the third request receives 500. Error body content is decided by the error response mechanism and application configuration, which may be customized by Spring Boot/`ErrorAttributes`/`@ControllerAdvice`, so we do not hardcode error JSON when only verifying semantics.

## 6. Understanding `HandlerMethodValidationException`

The `org.springframework.web.method.annotation.HandlerMethodValidationException` class was added in **Spring Framework 6.1**. It carries error data already transformed by Spring into a convenient controller-layer abstraction instead of only providing raw `Set<ConstraintViolation<?>>`.

Key APIs to know:

| API | Meaning |
| --- | --- |
| `getStatusCode()` | 400 for input validation errors; 500 for return-value violations under this mechanism |
| `isForReturnValue()` | `true` if a return value was violated; `false` if a parameter was violated |
| `getMethod()` | The Java `Method` that was validated |
| `getTarget()` | Target of the method invocation |
| `getParameterValidationResults()` | List of errors per parameter/result |
| `getCrossParameterValidationResults()` | Cross-parameter constraint errors, if any |
| `visitResults(Visitor)` | Dispatches errors by parameter annotation type: request parameter, model attribute, request body, etc. |

**Do not rely on `getMessage()` and parse text to identify fields.** Messages are human-readable descriptions that can be localized and change across versions/providers. Use the metadata of `ParameterValidationResult` and `ParameterErrors` to map errors back to the right input field.

### 6.1. `ParameterValidationResult` for direct constraints

For `@RequestParam @Min(1) int priority`, a `ParameterValidationResult` holds the parameter and error set, which can be read as:

~~~java
// Illustrative snippet, assuming HandlerMethodValidationException ex was caught:
for (var result : ex.getParameterValidationResults()) {
    int parameterIndex = result.getMethodParameter().getParameterIndex();
    var resolvableErrors = result.getResolvableErrors();

    // parameterIndex and error codes are used to build a safe response.
}
~~~

Here `getResolvableErrors()` is a list of `MessageSourceResolvable`; it contains error codes and arguments to resolve translations using `MessageSource`. When the object is a nested collection/map, `ParameterValidationResult` also provides `getContainer()`, `getContainerIndex()`, or `getContainerKey()` depending on the failing element kind. Do not try to infer the index/key by splitting message strings.

### 6.2. `ParameterErrors` for nested objects

When an error comes from a `@Valid` DTO, the result type can be `ParameterErrors` (a subclass of `ParameterValidationResult` that implements the `Errors` interface):

~~~java
// Illustrative snippet inside a result processor:
if (result instanceof org.springframework.validation.method.ParameterErrors nested) {
    for (var fieldError : nested.getFieldErrors()) {
        String field = fieldError.getField();
        String code = fieldError.getCode();

        // Example: field="productCode", code="NotBlank".
    }
}
~~~

Do not apply the same handling to all results: direct parameter violations do not necessarily have `FieldError`s, whereas nested object validation can. The rule of thumb is keeping error data grouped by **parameter**, then distinguishing direct errors from nested field errors.

### 6.3. Visitor for handling by parameter type

Spring provides `HandlerMethodValidationException.Visitor` to dispatch each `ParameterValidationResult` group according to the annotation used by the controller. This is an appropriate API when a system has multiple input styles:

~~~java
// Illustrative snippet inside an exception handler, with ex already in scope.
// Imports:
// org.springframework.web.bind.annotation.RequestParam
// org.springframework.web.bind.annotation.ModelAttribute
// org.springframework.validation.method.ParameterValidationResult
// org.springframework.validation.method.ParameterErrors

ex.visitResults(new HandlerMethodValidationException.Visitor() {

    @Override
    public void requestParam(
            RequestParam annotation, ParameterValidationResult result) {
        // result.getMethodParameter(), result.getResolvableErrors()
    }

    @Override
    public void modelAttribute(
            ModelAttribute annotation, ParameterErrors errors) {
        // errors.getFieldErrors()
    }

    @Override
    public void other(ParameterValidationResult result) {
        // Types without a dedicated callback, or fallback.
    }
});
~~~

The Visitor also has callbacks for annotations such as `@RequestHeader`, `@PathVariable`, `@RequestBody`, and `@RequestPart`. Methods receiving an annotation may receive `null` depending on how Spring classifies the parameter. The snippet above does not build a response itself; its purpose is to introduce the API for separating errors by input source.

**Cross-parameter constraints** can produce errors not tied to a single parameter; also inspect `getCrossParameterValidationResults()` rather than reading only `getParameterValidationResults()`.

## 7. Handling HTTP errors with `@ControllerAdvice`

Real applications should have **a stable error contract**. However, do not turn every validation failure into HTTP 400:

- If the **client sends invalid parameters**, 400 is usually appropriate.
- If the **controller returns data violating the return contract**, that is usually a server-side bug or failure; keep 500, log safely, and avoid leaking internal details in the response.
- If an error occurs before method validation due to JSON syntax, conversion, or a required parameter, the corresponding exception needs to be handled through the appropriate exception resolution path.

### 7.1. An optional `@RestControllerAdvice`

The following example is an **optional component**, not a required file to run the minimal test suite in section 5. If added to the application, it changes the error body while preserving the corresponding HTTP statuses.

~~~java
// src/main/java/com/example/mvcvalidation/ApiValidationAdvice.java
package com.example.mvcvalidation;

import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<ProblemDetail> onMethod(
            HandlerMethodValidationException ex) {

        HttpStatusCode status = ex.getStatusCode();
        String detail = ex.isForReturnValue()
                ? "Server-side result violated contract."
                : "Invalid request parameters.";

        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(status, detail);

        if (!ex.isForReturnValue()) {
            var indexes = ex.getParameterValidationResults().stream()
                    .map(r -> r.getMethodParameter().getParameterIndex())
                    .distinct()
                    .toList();
            problem.setProperty("parameterIndexes", indexes);
        }

        return ResponseEntity.status(status).body(problem);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> onArgument(
            MethodArgumentNotValidException ex) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                ex.getStatusCode(), "Invalid object data.");

        var fields = ex.getBindingResult().getFieldErrors().stream()
                .map(error -> error.getField())
                .distinct()
                .toList();
        problem.setProperty("fields", fields);

        return ResponseEntity.status(ex.getStatusCode()).body(problem);
    }
}
~~~

Good qualities of this example:
- Uses `ex.getStatusCode()` to **preserve the 400/500 distinction**.
- Does not return raw input, exception stack traces, or sensitive provider metadata.
- Return errors get a generic message; input errors can list parameter indexes and fields so clients can fix them.

In larger projects, you can **extend `ResponseEntityExceptionHandler`** and override the appropriate handler methods instead of defining multiple overlapping handlers. Once extending that class, do not also define duplicate `@ExceptionHandler` methods for the same exception types in the same advice, as that causes ambiguity. `ProblemDetail` and `MessageSource` support structured error representation, localization, and consistent details.

### 7.2. Localizing messages

`MethodArgumentNotValidException` has `BindingResult` with `FieldError`; `HandlerMethodValidationException` has `ParameterValidationResult#getResolvableErrors()` and `ParameterErrors`. These objects involve `MessageSourceResolvable`, enabling error codes to be resolved via `MessageSource` and locale.

Do not concatenate `constraint.getMessage()` or `exception.getMessage()` into an ad-hoc JSON object and hope for consistency. Design the response with:
- A stable error code (for example `INVALID_ARGUMENT`).
- Appropriate parameter name or index.
- Field name if it is a nested object.
- Localized message, avoiding leaking rejected values.
- No internal details of return-value violations exposed externally.

For applications with public clients, consider using the RFC 9457 `ProblemDetail` structure alongside Spring's error handling mechanism. `title`, `detail`, and extension properties should have a clear contract so clients never have to parse natural language.

## 8. `BindingResult` and `Errors` alongside method validation

This is a very practical change when moving from per-argument validation to whole-method validation. A handler can still be invoked **even when validation errors exist**, provided **all** errors belong to method arguments that have `Errors` or `BindingResult` **immediately after** them in the signature.

Example:

~~~java
@PostMapping("/preview")
public String preview(
        @RequestParam @Min(1) int priority,
        @Valid @ModelAttribute("orderInput") OrderInput form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return "form-invalid";
    }
    return "ok";
}
~~~

Explanation:

- `priority` has direct constraint `@Min(1)`, so MVC triggers method validation.
- `form` has `@Valid`, so its nested constraints are checked.
- `BindingResult` sits **immediately after `form`**, so the controller can handle errors belonging to that form itself.
- If `priority=1` is valid while `form.productCode` is blank, the handler can be invoked and `errors.hasErrors()` is `true`.
- If `priority=0` violates its direct constraint, there is no `Errors` immediately after `priority` to handle that error locally; Spring MVC throws `HandlerMethodValidationException`.

Do not put `BindingResult` at the end of the method far away from the validated object; Spring requires an explicit adjacency relationship. Multiple form objects require multiple corresponding `BindingResult` parameters. Do not use a single `BindingResult` for scalar arguments.

**Do not blindly apply the rule above to return-value constraints.** Return validation runs after the handler executes and cannot be "handled in place" by an earlier input argument's `BindingResult`.

## 9. Migrating from Spring Framework 6.0 to 6.1+

### 9.1. Before upgrading: controller using an AOP proxy

In many older codebases:

~~~java
@RestController
@Validated
class LegacyOrderController {

    @GetMapping("/orders")
    String list(@RequestParam @Min(1) int limit) {
        return "count=" + limit;
    }
}
~~~

Here class-level `@Validated` can cause method validation to run via Spring AOP (when `MethodValidationPostProcessor` and an appropriate proxy are present). Errors from AOP typically belong to `ConstraintViolationException` rather than `HandlerMethodValidationException`. HTTP status mapping then depends on exception handlers and should not automatically be assumed to be 400.

### 9.2. After upgrading: remove class-level `@Validated` if choosing built-in MVC

~~~java
@RestController
class ModernOrderController {

    @GetMapping("/orders")
    String list(@RequestParam @Min(1) int limit) {
        return "count=" + limit;
    }
}
~~~

With a Bean Validation provider integrated in MVC 6.1+, the direct constraint `@Min(1)` is handled by MVC; parameter errors are described via `HandlerMethodValidationException` and default to HTTP 400.

**Do not just delete the annotation and skip testing.** Things to check:

| Before 6.1 / AOP | After 6.1 / MVC built-in | Action required |
| --- | --- | --- |
| Controller-level `@Validated` | Remove controller-level annotation when choosing MVC built-in | Verify whether `@Validated` is still needed elsewhere |
| Catching `ConstraintViolationException` in advice | May receive `HandlerMethodValidationException` | Add handling for the new exception type |
| Custom logic returning 400 for every violation | MVC distinguishes input 400 and return 500 | Preserve the proper statuses |
| Only testing object-only `@Valid` | Test both direct parameters and return values | Write MockMvc tests |
| Manually reading raw `ConstraintViolation#getPropertyPath()` | Use `ParameterValidationResult`, `ParameterErrors` | Update error mapping |
| Method validation via proxy with AOP limits | Built-in runs in the MVC handler pipeline | No handler proxy needed to enforce constraints |
| `@Validated(SomeGroup.class)` on the class | Can affect group/validation semantics | Review group behavior and validator config |

If the application intentionally uses AOP method validation on controllers or has complex group handling, you do not necessarily have to switch immediately; however, **choose one clear strategy** and test errors against the expected exceptions.

### 9.3. Checking frequently missed cases

- `@Valid @RequestBody` **without** direct method constraints: still normally follows object-only validation.
- Same handler **adds `@Min`** on a `@RequestParam`: can change the exception type for request body validation failures.
- Method with a constraint on the **return value**: can return 500 after the method body runs.
- Missing `@RequestParam(required=true)`: exception may be thrown **before** Bean Validation.
- Malformed JSON: `HttpMessageNotReadableException`, not a method constraint.
- String-to-number conversion fails: type-mismatch exception, not a `@Min` violation.
- `BindingResult` immediately after an object: handler can run if all errors belong to arguments with immediately following `Errors`.
- Controller class-level `@Validated` accidentally left behind: can still run via AOP.

## 10. Advanced scenarios

### 10.1. Nested validation and container element constraints

~~~java
public class BatchInput {
    @NotEmpty
    private List<@NotBlank String> codes;

    public List<String> getCodes() {
        return codes;
    }

    public void setCodes(List<String> codes) {
        this.codes = codes;
    }
}
~~~

When `@Valid @RequestBody BatchInput body` is validated, Bean Validation can apply `@NotEmpty` to the list and `@NotBlank` to each element. Container element constraints require value extractors; for `List`, providers usually support them out of the box.

If the same method also has `@RequestParam @Min(1) int priority`, nested violations in `BatchInput` go through the method validation flow. Errors on multiple elements can appear in `ParameterErrors` or `ParameterValidationResult` along with container index/key metadata. Do not assume that merely having a `List` causes `@Valid` to trigger if that input type is not validated by the handler signature.

`BatchInput` here only illustrates DTO structure; it is not a required file in the section 5 project.

### 10.2. Cross-parameter constraints

A custom constraint applied to a method's **parameter array** — for example, "`start` must be less than or equal to `end`" — is implemented via `ConstraintValidator<MyConstraint, Object[]>` with:

~~~java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
~~~

This is an annotation snippet inside a validator, not a standalone class. Spring MVC method validation can receive cross-parameter errors, and `HandlerMethodValidationException#getCrossParameterValidationResults()` lets you read them. Such errors do not necessarily belong to a single `@RequestParam`, so do not force-map them to one field without designing `ConstraintValidatorContext` properly.

When using inheritance/interfaces on method parameters, pay attention to Jakarta Validation rules: preconditions cannot be added on an overridden method; return constraints can be added subject to spec limits. Spring MVC 6.1 does not relax those Bean Validation rules.

### 10.3. Groups

Spring's `@Validated` can select validation groups. However, **class-level `@Validated` on a controller** specifically affects whether MVC uses built-in method validation or an AOP proxy. If a project previously used controller-level `@Validated(Group.class)` and now wants to remove it for MVC 6.1+, redesign group selection using supported APIs and test interaction with any custom `Validator`; do not assume migration preserves group selection unchanged.

Jakarta's `@Valid` only requests cascading, not group selection. For nested objects, `@ConvertGroup` group conversion can take effect during cascading. Every group selection needs its own integration test rather than testing beans solely with `validator.validate(bean, Group.class)`.

### 10.4. Async returns and reactive publishers

When a handler returns `CompletableFuture<T>`, `DeferredResult<T>`, `Callable<T>`, or a publisher, do not assume constraints on the type parameter are validated at the moment the async value arrives in the same way as a direct synchronous return. Spring MVC has its own async request processing lifecycle, and Bean Validation does not automatically "await" every wrapper. For async returns, verify what object is actually validated, what the integration supports, and write tests for response completion time.

In Spring WebFlux applications, built-in method validation also exists since Spring Framework 6.1, yet the WebFlux pipeline is not the Servlet MVC `HandlerMethodValidator` covered in this lesson; do not copy conclusions about exceptions and argument resolution verbatim without checking WebFlux documentation.

### 10.5. Custom validators and global configuration

When a Jakarta Validation provider is on the classpath, Spring MVC typically registers an appropriate global `Validator` (such as `LocalValidatorFactoryBean`). You can customize it via `WebMvcConfigurer#getValidator()` or use local `@InitBinder` validators as needed.

Keep these distinct:
- `@InitBinder` customizes data binders, formatters, and local validators for arguments.
- `LocalValidatorFactoryBean` is the adapter/bridge connecting Bean Validation to Spring.
- `MethodValidationPostProcessor` serves AOP method validation for beans and is **not required** for built-in MVC validation.
- `HandlerMethodValidator` handles method constraints on MVC handlers when integration conditions are met.

If you replace the global validator with an implementation that does not fully support Bean Validation, method validation behavior may change. Test both conversion/binding and executable validation after customization.

### 10.6. Constructor and service method validation

MVC's `@RequestMapping` handler validation is not a mechanism that validates "every method in the application". Service beans usually use class-level `@Validated` with an AOP proxy; constructor validation requires separate integration or `ExecutableValidator`. Do not remove `@Validated` from services merely because MVC 6.1 has built-in method validation: **the two scopes are different**.

## 11. Diagnosing errors and anti-patterns

| Symptom | Common cause | How to check |
| --- | --- | --- |
| `@Min` on controller parameter does not run | Missing provider, framework version too old, dispatch bypasses MVC, constraint placed incorrectly | Check dependencies, Spring version, handler signature, and MockMvc tests |
| `@Valid @RequestBody` errors are still `MethodArgumentNotValidException` | Signature has no direct method constraints | This may be expected behavior; check the table in section 2 |
| Added `@Min` and DTO exception type changed | Method validation replaced object-only validation | Handle `HandlerMethodValidationException` alongside the old type |
| Handler rejected despite having `BindingResult` | Error on **another parameter** lacking an immediately following `Errors` | Inspect every method argument |
| `BindingResult` does not receive the right errors | Not placed immediately after `@ModelAttribute` / `@RequestBody` | Fix method argument order |
| Missing parameter or invalid JSON does not hit method exception handler | Failure in resolution/deserialization before validation | Catch `MissingServletRequestParameterException` / `HttpMessageNotReadableException` properly |
| Invalid return response returns HTTP 400 | Custom advice maps all validation errors to 400 | Use `ex.isForReturnValue()` or `ex.getStatusCode()` |
| MockMvc test does not trigger method validation | Missing global validator or custom standalone MVC setup differing from Spring Boot | Use `@SpringBootTest @AutoConfigureMockMvc` or configure `standaloneSetup` with a validator |
| Controller still throws `ConstraintViolationException` from proxy | Class-level `@Validated` still present; AOP method validation activated | If choosing MVC built-in, remove class-level `@Validated` and retest |
| Client sees sensitive values in response | Directly mapping `getArgument()`, raw violations/rejected values | Return only safe fields and error codes |
| Internal service call is not validated | Spring AOP self-invocation bypasses proxy | Test through injected bean; do not confuse with MVC built-in |
| Cannot determine which list index failed | Ignored container metadata | Use `ParameterValidationResult#getContainerIndex()` / `getContainerKey()`, or `ParameterErrors` |

### An effective debugging workflow

1. Confirm **Spring MVC version** and that `spring-boot-starter-validation`/provider is on the classpath.
2. Read the **handler signature**: is `@Valid` only on an object, or is there a direct `@Constraint` on a method argument/return?
3. Check if the controller has class-level `@Validated`. If the target is the MVC 6.1+ mechanism, remove that annotation.
4. Separate **resolution/binding** errors from **Bean Validation** errors: missing parameters, malformed JSON, and type mismatches happen earlier.
5. Send a minimal request through `MockMvc`, verifying **HTTP status**, `resolvedException`, and `isForReturnValue()`.
6. Read `ParameterValidationResult`/`ParameterErrors` to locate params/fields instead of parsing messages.
7. Check `BindingResult` adjacency after an object if handling errors locally.
8. If `@ControllerAdvice` is present, check ordering/resolvers and status mapping; do not replace 500 with 400.
9. When upgrading from AOP, test both before/after error types and ensure service validation is unaffected.

## 12. Project adoption checklist

- [ ] Project uses Spring Framework **6.1+** with compatible Java/Jakarta Validation versions.
- [ ] Controllers using built-in MVC validation **do not have class-level `@Validated`**.
- [ ] Direct method constraints (on parameters or return values) are declared on valid types and positions.
- [ ] Team understands plain `@Valid` **is not a direct constraint**, so object-only validation may continue throwing `MethodArgumentNotValidException`.
- [ ] `@ControllerAdvice` handles both `MethodArgumentNotValidException` and `HandlerMethodValidationException`, preserving 400/500 statuses.
- [ ] `BindingResult`/`Errors`, when used, are always placed **immediately after** their corresponding argument; errors on other arguments still go through method validation.
- [ ] Binding/JSON/required parameter errors have separate handling branches; not every HTTP 400 is treated as a constraint violation.
- [ ] MockMvc integration tests cover valid requests, invalid direct parameters, invalid nested DTOs, invalid returns, and local `BindingResult`.
- [ ] Service method validation via `@Validated`/AOP is kept where needed; MVC scope is not confused with application-wide scope.
- [ ] Error responses never leak tokens, user data, raw rejected values, or stack traces.

## 13. References

- Spring Framework 6.2, **Spring MVC Validation** (explains the two validation levels, `@Validated`, and `BindingResult`): https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2, **MVC validation configuration**: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-config/validation.html
- Spring Framework 6.2 Javadoc, **HandlerMethodValidationException**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html
- Spring Framework 6.2 Javadoc, **ParameterValidationResult**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 Javadoc, **ParameterErrors**: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/validation/method/ParameterErrors.html
- Spring Framework 6.2, **Spring-driven Method Validation (AOP)**: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Boot 3.5, **Validation**: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- Jakarta Validation, **Bean Validation specification**: https://jakarta.ee/specifications/bean-validation/
