# Distinguishing Type Conversion Errors, Binding Errors, and Validation Errors in Spring MVC

## 1. Goal and Big Picture

When a request sends data to a controller, **type conversion errors**, **data binding errors**, and **validation errors** describe failures at **related yet distinct stages**. A `400 Bad Request` response alone does not tell you which stage failed. You must inspect controller parameter types, exceptions, `BindingResult`, and configuration to diagnose accurately.

After this lesson, you will be able to:

- Describe the request flow from raw input strings, type conversion, populating objects, to applying business constraints.
- Distinguish conversion errors on `@RequestParam`/`@PathVariable` from field binding errors on `@ModelAttribute`.
- Distinguish JSON parse/deserialization errors on `@RequestBody` from Jakarta Bean Validation errors that occur *after* object creation.
- Understand `BindingResult`, `FieldError`, `ObjectError`, `typeMismatch`, `@Valid`, `@Validated`, and default error reporting.
- Choose how to return HTTP errors, test stage-by-stage, and prevent invalid data from entering business logic.

**Scope:** Spring MVC on the Servlet stack, Java 17+, Spring Framework 6.1+/Spring Boot 3.x with Jakarta Validation. Some exception details vary across versions or depend on custom handlers; the lesson points out common cases and key exceptions. This is not a guide specific to Spring WebFlux.

## 2. Three Processing Layers: Conversion, Binding, Validation

### 2.1. Mental Flow

```text
HTTP request
  |
  +--> Locate matching handler and resolvers
  |       (@RequestParam / @PathVariable / @ModelAttribute / @RequestBody)
  |
  +--> Read input data
  |       query/form/header/path are typically strings;
  |       JSON body is bytes -> JSON tokens
  |
  +--> Convert data
  |       "42" -> Integer(42)
  |       "2026-10-21" -> LocalDate
  |       JSON -> Java object via HttpMessageConverter/Jackson
  |
  +--> Bind if target is a model attribute
  |       assign properties onto target object;
  |       record property errors in BindingResult
  |
  +--> Validate if enabled
  |       @NotBlank, @Min, @NotNull, custom validators,
  |       multi-field or method parameter constraints
  |
  +--> Controller handler and business logic when valid
```

This is a **conceptual** diagram; not every parameter type goes through every step. For example, `@RequestParam Integer` is converted directly by an argument resolver without a form object to bind; `@RequestBody` uses `HttpMessageConverter`/Jackson to deserialize JSON rather than `@ModelAttribute`'s property binding mechanism.

### 2.2. Exact Definitions

**Type conversion**: transforming a source value into a target Java type, usually via `ConversionService`, `Converter`, `Formatter`, or `PropertyEditor`. For example, `"abc"` cannot be converted into `Integer`, and a malformed date string cannot be converted into `LocalDate`. Conversion is a **step** that can happen during binding.

**Data binding**: connecting request values to constructor parameters or properties of an object, typically performed by `WebDataBinder` for `@ModelAttribute`. Binding encompasses resolving properties, applying conversion, and recording issues. Hence **a conversion error can be represented as a binding error** on a specific field, rather than the two being mutually exclusive.

**Validation**: checking already-typed data against validity constraints. For instance, `Integer age = 0` converts cleanly yet violates `@Min(1)`; `name = ""` is a valid Java `String` yet violates `@NotBlank`. Spring supports Jakarta Bean Validation via `@Valid`/`@Validated` and Spring's `Validator`.

### 2.3. Quick Comparison

| Scenario | Typical failing stage | Illustration | Typical HTTP outcome |
| --- | --- | --- | --- |
| Query `?age=abc` bound to `@RequestParam Integer age` | Method argument type conversion | String cannot become Integer | `400`, typically `MethodArgumentTypeMismatchException` |
| Form `age=abc` bound to `@ModelAttribute Form.age` | Field conversion **inside data binding** | `BindingResult` gets `FieldError` with code `typeMismatch` | Controller handles if `BindingResult` is present; otherwise typically `400` |
| Form has unwritable property or unbindable constructor | Object binding/instantiation | Setter, constructor, or field mismatch | Depends on error type/config; can become binding error or another exception |
| Form `age=0` with `@Min(1)` | Validation | Valid Integer value violates constraint | `FieldError` code `Min`, or default `400` |
| JSON `{"age":"oops"}` with `Integer age` | JSON deserialization | Jackson cannot construct object | Typically `400`, `HttpMessageNotReadableException` |
| JSON `{"age":0}` with `@Min(1)` | Validation after deserialization | Object created, violates constraint | `400`, typically `MethodArgumentNotValidException` |
| Query `?age=0` with `@Min(1)` directly on parameter | Handler **method validation** | Value converts, violates method constraint | Spring MVC 6.1+ typically `HandlerMethodValidationException`, `400` for input errors |

**Never write a rigid rule like "conversion = exception X, binding = exception Y, validation = exception Z" for every controller argument type.** Exceptions depend on *input source* and *processing stage*.

## 3. Conversion: Errors Turning Strings into Java Types

### 3.1. Simple Parameters: `@RequestParam` and `@PathVariable`

```java
@GetMapping("/products")
public String products(@RequestParam("page") int page) {
    return "page=" + page;
}
```

| Request | Interpretation | Common outcome |
| --- | --- | --- |
| `GET /products?page=3` | `"3"` converts to `int 3` | Controller runs |
| `GET /products?page=abc` | Cannot parse as number | `400`: conversion error |
| `GET /products` | Required parameter missing | `400`: missing parameter, **not conversion** |
| `GET /products?page=` | Empty string may convert to null; `int` cannot hold null | `400`, may be reported as missing after conversion |
| `GET /products?page=-1` | Converts `-1` successfully | Controller runs unless `@Min(1)` is enabled |

Common exceptions:

- `MethodArgumentTypeMismatchException`: conversion failed for a method argument like `@RequestParam` or `@PathVariable`.
- `MissingServletRequestParameterException`: required parameter is missing; Spring also distinguishes cases where **the parameter name is present but converts to null**.
- `MissingPathVariableException`: a required URI template variable could not be resolved; distinguish from a URL not matching any handler.
- Spring's `TypeMismatchException` is the base class for type conversion errors; do not assume the observed exception at every layer is always one fixed subclass.

A URL `/products/abc` for `@PathVariable Long id` normally fails while converting to `Long`; by contrast, `/products` might not match the `/products/{id}` mapping at all and return **404** before argument conversion runs.

### 3.2. Dates/Times, Enums, and Formatters

```java
@GetMapping("/reports")
public String report(
        @RequestParam
        @org.springframework.format.annotation.DateTimeFormat(iso =
                org.springframework.format.annotation.DateTimeFormat.ISO.DATE)
        java.time.LocalDate from) {
    return from.toString();
}
```

`?from=2026-10-21` is valid; `?from=tomorrow` or `?from=2026-99-99` does not match a valid date format/value and usually triggers 400 before invoking the controller. For enums, value names are usually case-sensitive under the default converter unless you register a custom converter.

Customize conversion via global `FormattingConversionService`/`Converter`/`Formatter` or per-controller `@InitBinder`/`WebDataBinder`. Do not write custom converters that swallow errors and return `null` if the application needs to detect invalid input; doing so turns conversion errors into missing values.

### 3.3. Type Errors vs. Business Rule Errors

`?amount=abc` failing to parse as `BigDecimal` is a **conversion error**. `?amount=-50` parses as a number; if the contract requires a positive amount, that is a **validation error**. `?currency=VND` parses into a valid enum, yet an account not supporting VND is a **business rule error**, outside both categories. Do not infer every `400` comes from Bean Validation.

## 4. Data Binding: Populating Objects from Form/Query Data

### 4.1. `@ModelAttribute` Goes Through `WebDataBinder`

```java
public class RegisterForm {
    private String email;
    private Integer age;

    public RegisterForm() {}

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public Integer getAge() { return age; }
    public void setAge(Integer age) { this.age = age; }
}
```

```java
@PostMapping("/register-form")
public String register(
        @ModelAttribute("form") RegisterForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "INVALID";
    }
    return "OK";
}
```

These are **two illustrative snippets**, assuming necessary Spring imports. A form request with `email=lan@example.com&age=abc` creates `RegisterForm` and binds `email` successfully, while conversion to `Integer age` fails. `BindingResult` contains a `FieldError` for `age`, typically with primary code `typeMismatch`; the handler is still invoked because `BindingResult` sits **immediately after** `@ModelAttribute`.

If the form sends `age=20`, the binder sets `Integer` successfully; **there is no automatic age validation** merely because the field is named `age`. Declare constraints and trigger validation if limits are required.

`BindingResult` exposes key fields and methods:

- `hasErrors()`, `getErrorCount()`: whether errors exist and how many.
- `getFieldErrors()`: property-level `FieldError`s, e.g., `age`.
- `getGlobalErrors()`: object-level `ObjectError`s, e.g., relationships across two fields.
- `FieldError.getField()`: property name such as `"age"`.
- `FieldError.getCode()`: general error code, e.g., `typeMismatch` or `Min`; `getCodes()` lists candidate codes ordered from specific to general.
- `FieldError.getRejectedValue()`: the rejected value; **never put this raw value into logs or responses**, as it may contain sensitive data.
- `FieldError.isBindingFailure()`: indicates a binding failure; constraint validation errors normally have `isBindingFailure() == false`. This is a helpful signal, though you should not rely on a single flag alone to classify all infrastructure errors.
- `getSuppressedFields()`: list of fields skipped because binding them was disallowed; **does not necessarily create a FieldError**. Inspect this when using allowlists to prevent mass assignment.

### 4.2. Binding Involves More Than Numeric Parsing

Data binding failures can also involve invalid property names, setters/constructors, nested fields, indexed properties, required fields configured on `WebDataBinder`, or conversion/formatting. Under `DataBinder`'s default `ignoreUnknownFields`, unknown fields may be ignored rather than becoming `FieldError`s. Depending on `allowedFields`/`disallowedFields` policies, disallowed fields can be suppressed without **being treated as validation errors**.

If an endpoint accepts form data, use a dedicated input DTO containing only editable fields. Do not bind directly into a JPA entity containing `id`, `role`, `isAdmin`, or sensitive fields the client must not change; combine allowlists and `getSuppressedFields()` checks where appropriate.

### 4.3. `BindingResult` Must Immediately Follow Its Argument

Correct:

```java
@PostMapping("/save")
public String save(@Valid @ModelAttribute("form") RegisterForm form,
                   BindingResult result) {
    return result.hasErrors() ? "INVALID" : "SAVED";
}
```

Wrong because it is not adjacent to the bound/validated object:

```java
// INVALID example: do not copy into a real controller.
@PostMapping("/save")
public String save(@Valid @ModelAttribute("form") RegisterForm form,
                   @RequestParam String source,
                   BindingResult result) {
    return "UNRELIABLE";
}
```

Spring requires `Errors` or `BindingResult` **immediately after** the corresponding bound/validated parameter. With multiple model attributes, each `BindingResult` must follow its own object directly. Misplacing it can trigger an `IllegalStateException` regarding `BindingResult`/`Errors` or cause the framework to throw an exception rather than populating the intended parameter.

### 4.4. What If There Is No `BindingResult`?

In modern Spring MVC, binding/validation errors on `@ModelAttribute` typically raise `MethodArgumentNotValidException` and default to status 400 when no matching `BindingResult`/`Errors` is present. In older docs or specific code paths, you may see `BindException`. **Do not hardcode assumptions to a single exception class across all Spring versions and argument types.** In template-based MVC apps, adding `BindingResult` lets you re-render errors next to the form instead of returning a default 400.

## 5. Validation: Type-Valid Data That Violates Constraints

### 5.1. Declaring and Triggering Constraints

Example using Jakarta Bean Validation:

```java
public record CreateUser(
        @jakarta.validation.constraints.NotBlank String name,
        @jakarta.validation.constraints.NotNull
        @jakarta.validation.constraints.Min(18) Integer age) {}
```

- `name=""` or `name="   "`: converts to `String`, yet `@NotBlank` fails.
- `age=17`: converts to `Integer`, yet `@Min(18)` fails.
- `age=null`: violates `@NotNull`. `@Min` alone normally treats `null` as valid; pair with `@NotNull` when age is required.
- `age="abc"` in JSON: can fail during Jackson deserialization, **before** `@Min` ever evaluates an integer.
- `@Valid` activates constraint evaluation on the appropriate argument; putting constraints on a DTO without triggering validation lets invalid requests pass into the controller.

Common dependency in Spring Boot 3: `spring-boot-starter-validation`. The Spring MVC Web starter does not guarantee a validation provider is present on its own. When using Jakarta Validation in Boot 3, import `jakarta.validation.*`, not `javax.validation.*` from older Boot 2 examples.

### 5.2. `@NotNull`, `@NotEmpty`, `@NotBlank`

| Constraint | null | String `""` | String `"   "` |
| --- | --- | --- | --- |
| `@NotNull` | Invalid | Valid | Valid |
| `@NotEmpty` | Invalid | Invalid | Valid |
| `@NotBlank` | Invalid | Invalid | Invalid |

`@NotEmpty` applies to supported container/`CharSequence` types, whereas `@NotBlank` is for strings. `@Size(min=1)` alone does not mean "not null"; `null` usually passes `@Size`.

### 5.3. Field-Level vs. Object-Level Errors

A property constraint typically creates a `FieldError` with a code like `NotBlank` or `Min`. A class-level constraint, such as "end date must follow start date," can create an `ObjectError`/global error. API schemas should be able to represent both **field errors** and **global errors**, rather than assuming every error has a field name.

### 5.4. Validation Groups

`@Validated(Create.class)`/`@Validated(Update.class)` apply constraint groups tailored to create/update actions. Avoid forcing "creation requires all fields" onto PATCH requests that allow omitting fields. Groups do not substitute for distinguishing **omitted** JSON properties from **explicit null**: once deserialized to the same Java `null`, the validator cannot reconstruct field presence.

## 6. `@RequestBody`: Deserialization Is a Different Pipeline

Example:

```java
@PostMapping(path = "/users", consumes = "application/json")
public String create(@Valid @RequestBody CreateUser input) {
    return "OK";
}
```

When Jackson is configured, `MappingJackson2HttpMessageConverter` reads JSON and constructs `CreateUser`. This process is **not identical** to `WebDataBinder` binding `age` from a form parameter.

| JSON body | Stage | Typical outcome |
| --- | --- | --- |
| `{"name":"Lan","age":25}` | Both deserialization and validation succeed | Handler runs |
| `{"name":"Lan","age":"oops"}` | Jackson cannot convert `"oops"` to Integer | `HttpMessageNotReadableException`, 400 |
| `{"name":"Lan","age":17}` | Deserialized, `@Min(18)` fails | `MethodArgumentNotValidException`, 400 |
| `{"name":"","age":25}` | Deserialized, `@NotBlank` fails | `MethodArgumentNotValidException`, 400 |
| `{"name":"Lan","age":25` | Malformed JSON syntax | `HttpMessageNotReadableException`, 400 |
| Missing body when `@RequestBody` is required | Missing request body content | Typically `HttpMessageNotReadableException`, 400 |
| Sending `text/plain` to endpoint with `consumes="application/json"` | Unsupported media type | `415 Unsupported Media Type`, **not validation** |

If the application configures custom Jackson coercion (e.g., coercing numeric strings to numbers or empty strings to null), outcomes can differ. Inspect your actual `ObjectMapper`. Do not catch `HttpMessageNotReadableException` and label every failure as a "`@Min` violation"; validation may not have run at all.

**`@Valid @RequestBody DTO, BindingResult`** is supported by Spring MVC when `BindingResult` immediately follows the DTO, letting the controller inspect validation errors on a successfully read object. However, when JSON cannot be deserialized, the controller usually **has no object** to pass with `BindingResult`; the request fails before reaching the method.

## 7. Method Validation: Key Differences Starting in Spring MVC 6.1+

Two key modes:

1. **Argument validation**: `@Valid` or `@Validated` on `@RequestBody`, `@ModelAttribute`, or `@RequestPart` objects, without direct parameter constraints triggering method validation. Default error is usually `MethodArgumentNotValidException` if no `BindingResult` immediately follows.
2. **Method validation**: constraints such as `@Min`, `@NotBlank`, or `@NotNull` placed **directly** on controller method parameters (or return values) cause Spring MVC 6.1+ to validate at the method level. Input failures typically throw `HandlerMethodValidationException`, usually HTTP 400. Method validation also encompasses nested constraints via `@Valid` when needed.

Example:

```java
@GetMapping("/min-page")
public String minPage(
        @RequestParam("page")
        @jakarta.validation.constraints.Min(1) int page) {
    return "page=" + page;
}
```

- `?page=abc`: conversion fails **before validation**.
- `?page=0`: conversion to `int` succeeds, then `@Min(1)` fails; Spring MVC 6.1+ normally throws `HandlerMethodValidationException`.
- `?page=2`: valid.

`@Valid` **is not** a direct constraint that triggers method validation by itself; it cascades constraints inside an object. By contrast, `@NotNull` is a constraint. Specifically, if a controller places `@Validated` at the **class level**, some versions/configs use AOP proxy method validation rather than Spring MVC 6.1+'s built-in mechanism, leading to a different exception (such as `ConstraintViolationException`) and different HTTP mapping. When adopting MVC 6.1+'s native behavior, check removing class-level `@Validated` per your version's docs. Do not funnel every validation error into a single `@ExceptionHandler(MethodArgumentNotValidException.class)` and assume everything is covered.

## 8. Runnable Spring Boot 3 + Java 17+ Example

This sample application distinguishes three handling paths in one controller:

- `GET /input-errors/query?age=abc`: method argument conversion error.
- `POST /input-errors/form` with `age=abc`: binding error captured in `BindingResult`.
- `POST /input-errors/form` with `age=0`: validation error (`@Min`), after the binder converted the type successfully.
- `POST /input-errors/json` with unconvertible JSON: deserialization error.
- `POST /input-errors/json` with age `0`: Bean Validation error.
- `GET /input-errors/method?age=0`: direct method constraint error in Spring MVC 6.1+.

Spring Boot 3.x Maven project, package `com.example.demo`; requires `spring-boot-starter-web` and `spring-boot-starter-validation`.

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Create `src/main/java/com/example/demo/InputErrorController.java`:

```java
package com.example.demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/input-errors")
public class InputErrorController {

    @GetMapping("/query")
    public Map<String, Integer> query(@RequestParam("age") Integer age) {
        return Map.of("age", age);
    }

    @GetMapping("/method")
    public Map<String, Integer> method(
            @RequestParam("age") @Min(1) int age) {
        return Map.of("age", age);
    }

    @PostMapping(path = "/form",
                 consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> form(
            @Valid @ModelAttribute("form") FormInput input,
            BindingResult binding) {

        if (binding.hasErrors()) {
            List<FieldIssue> issues = binding.getFieldErrors()
                    .stream()
                    .map(this::toIssue)
                    .toList();
            return ResponseEntity.badRequest()
                    .body(new ErrorPayload("INVALID_FORM", issues));
        }

        return ResponseEntity.ok(Map.of("status", "ACCEPTED"));
    }

    @PostMapping(path = "/json",
                 consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> json(
            @Valid @RequestBody JsonInput input) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "CREATED"));
    }

    private FieldIssue toIssue(FieldError error) {
        // Do not expose rejectedValue or sensitive info to the client.
        return new FieldIssue(error.getField(), error.getCode());
    }

    public record FieldIssue(String field, String code) {}
    public record ErrorPayload(String error, List<FieldIssue> fields) {}

    public static class FormInput {
        @NotBlank
        private String name;

        @NotNull
        @Min(1)
        private Integer age;

        public FormInput() {}

        public String getName() { return name; }
        public void setName(String name) { this.name = name; }

        public Integer getAge() { return age; }
        public void setAge(Integer age) { this.age = age; }
    }

    public record JsonInput(
            @NotBlank String name,
            @NotNull @Min(1) Integer age) {}
}
```

Code explanation:

- `@RequestParam Integer age`: Spring converts the String parameter to Integer **before** calling `query`.
- `@ModelAttribute FormInput`: the binder populates properties; for `age=abc`, `FieldError` normally has `getCode() == "typeMismatch"`. For `age=0`, the validation error normally has code `Min`.
- `@Valid` applies to the form object; `BindingResult` right after the object lets the controller return structured JSON errors. `ResponseEntity.badRequest()` is an **application** choice, not mandatory behavior when taking `BindingResult`.
- `@Valid @RequestBody JsonInput`: if Jackson reads the body yet Bean Validation fails, there is no adjacent `BindingResult`, so the framework produces a 400 response.
- `@Min(1)` directly on parameter `age` in `method` enables method validation in Spring MVC 6.1+ under default configuration.

Note that `ErrorPayload` above represents only **field errors** for the demo. Production apps should also handle `getGlobalErrors()`, API-contract codes, localized messages, and a request correlation id, without exposing raw exceptions or secrets.

Run from the Maven project directory with wrapper:

```bash
./mvnw spring-boot:run
```

Windows PowerShell: `.\mvnw.cmd spring-boot:run`. Default port is 8080 unless configured otherwise. The controller class cannot be compiled standalone with `javac InputErrorController.java` because it needs Spring/Jakarta dependencies. The sample code is meant to compile inside a Boot project with the dependencies listed above.

## 9. Using curl to Observe Error Boundaries

The `curl` commands below run once the app is started on `http://localhost:8080`.

### 9.1. Conversion on `@RequestParam`

```bash
curl -i "http://localhost:8080/input-errors/query?age=abc"
```

Typically returns **400 Bad Request**; `query` does not run, and Spring typically reports `MethodArgumentTypeMismatchException` server-side.

```bash
curl -i "http://localhost:8080/input-errors/query?age=20"
```

Returns **200 OK**, JSON body containing `"age":20`.

### 9.2. Conversion Inside Form Binding

```bash
curl -i "http://localhost:8080/input-errors/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "name=Lan&age=abc"
```

Controller `form` executes because `BindingResult` immediately follows `FormInput`; e.g., returns **400** with JSON equivalent to:

```json
{
  "error": "INVALID_FORM",
  "fields": [
    {"field": "age", "code": "typeMismatch"}
  ]
}
```

**Sample body may contain additional field errors** depending on validation execution and config; tests should look for code `typeMismatch` rather than hardcoding exact error counts or order. `age=abc` cannot become an Integer; this is a conversion failure recorded in `BindingResult`.

### 9.3. Validation of a Successfully Bound Form

```bash
curl -i "http://localhost:8080/input-errors/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data "name=Lan&age=0"
```

`age=0` converts **successfully**; `@Min(1)` fails. Example returns **400** with field code `Min`. Similarly `name=` produces code `NotBlank`. Neither of these is a `typeMismatch`.

### 9.4. Undeserializable JSON

```bash
curl -i "http://localhost:8080/input-errors/json" \
  -H "Content-Type: application/json" \
  --data '{"name":"Lan","age":"abc"}'
```

Typically **400 Bad Request**, `HttpMessageNotReadableException`, with no form `FieldError` inside `form`. If the JSON body has **syntax errors**, the same reading branch reports the failure before validation.

### 9.5. Valid JSON Violating Constraints

```bash
curl -i "http://localhost:8080/input-errors/json" \
  -H "Content-Type: application/json" \
  --data '{"name":"Lan","age":0}'
```

Typically **400 Bad Request**, `MethodArgumentNotValidException`. JSON is readable, yet `@Min(1)` fails.

```bash
curl -i "http://localhost:8080/input-errors/json" \
  -H "Content-Type: application/json" \
  --data '{"name":"Lan","age":20}'
```

Returns **201 Created** and JSON:

```json
{"status":"CREATED"}
```

### 9.6. Method Validation

```bash
curl -i "http://localhost:8080/input-errors/method?age=0"
```

On Spring MVC 6.1+ with the built-in mechanism, the `@Min(1)` constraint on the method parameter fails: typically 400 with `HandlerMethodValidationException`. Sending `age=abc`, by contrast, is a **type conversion error** before the constraint is reached.

Windows tip: use `curl.exe` on one line when older PowerShell maps `curl` to an alias; trailing `\` characters in examples are bash/zsh line-continuation syntax.

## 10. MockMvc Tests to Identify Exact Error Categories

Place `src/test/java/com/example/demo/InputErrorControllerTest.java` with dependencies `spring-boot-starter-test` and `spring-boot-starter-validation`. Tests do not assume Spring Boot's default error body is identical across versions. When a form has multiple errors, use matchers checking by code rather than relying on order.

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(InputErrorController.class)
class InputErrorControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void queryConversionFailsBeforeController() throws Exception {
        mvc.perform(get("/input-errors/query").param("age", "abc"))
                .andExpect(status().isBadRequest());

        mvc.perform(get("/input-errors/query").param("age", "20"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.age").value(20));
    }

    @Test
    void formConversionFailureAppearsAsBindingError() throws Exception {
        mvc.perform(post("/input-errors/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Lan")
                .param("age", "abc"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.error").value("INVALID_FORM"))
            .andExpect(jsonPath("$.fields[*].code",
                    hasItem("typeMismatch")));
    }

    @Test
    void formValidationHasDifferentCode() throws Exception {
        mvc.perform(post("/input-errors/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("name", "Lan")
                .param("age", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fields[*].code", hasItem("Min")));
    }

    @Test
    void jsonDeserializationErrorIs400() throws Exception {
        mvc.perform(post("/input-errors/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\",\"age\":\"abc\"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void jsonValidationErrorIs400() throws Exception {
        mvc.perform(post("/input-errors/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\",\"age\":0}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void directParameterConstraintRejectsZero() throws Exception {
        mvc.perform(get("/input-errors/method").param("age", "0"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void validJsonRequestCanCreate() throws Exception {
        mvc.perform(post("/input-errors/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\":\"Lan\",\"age\":20}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.status").value("CREATED"));
    }
}
```

Run:

```bash
./mvnw test
```

Windows: `.\mvnw.cmd test`. These are **recommended tests to run in the sample project with appropriate dependencies**; statuses can be altered by Spring Security, filters, or custom controller advices. If the app has security requiring authentication/CSRF, configure test security or mock a valid user before interpreting input errors.

To assert the exact exception class in a specific version, you can add `andExpect(result -> ...)` inspecting `MvcResult.getResolvedException()` in a dedicated test, though only when the exception is handled by MockMvc's resolver. For production apps, prefer testing **public API error codes** rather than coupling clients to internal Java classes.

## 11. Exceptions, Statuses, and Centralized Handling

Exceptions worth recognizing in Spring MVC:

| Type | Typical cause | Useful classification |
| --- | --- | --- |
| `MissingServletRequestParameterException` | Missing required query/form parameter | Missing input |
| `MethodArgumentTypeMismatchException` | `@RequestParam`/`@PathVariable` cannot convert | Conversion |
| `MethodArgumentNotValidException` | Validation of `@RequestBody`, `@ModelAttribute`, or argument binding/validation without `BindingResult` | Binding/argument validation |
| `HandlerMethodValidationException` | Constraint directly on handler method parameter, Spring MVC 6.1+ | Method validation |
| `HttpMessageNotReadableException` | JSON body parse/deserialize failure or unreadable required body | Message conversion |
| `HttpMediaTypeNotSupportedException` | Request `Content-Type` not supported by endpoint/converter | HTTP content type, typically `415` |
| `BindException` / `TypeMismatchException` | Binding/conversion along specific paths, especially with custom binders or different versions | Inspect location and version |

**Not everything is 400**: `415` is a media type issue; authorization failures can be `401`/`403`; unmatched handlers can be `404`. A `ConstraintViolationException` from a service or database also does not automatically mean HTTP 400: it could be a business/system bug and must be classified by origin.

Spring MVC provides `DefaultHandlerExceptionResolver` and `ResponseEntityExceptionHandler` to handle many default exceptions. In REST APIs, you can extend `ResponseEntityExceptionHandler` in `@RestControllerAdvice` and override appropriate handlers to emit consistent error structures (e.g., RFC 9457 `ProblemDetail`). However, override signatures vary by Spring version; read your exact release's Javadoc before copying. When writing custom `@ExceptionHandler` methods, ensure you never return 200 for invalid input or accidentally swallow infrastructure exceptions into 400.

A sensible error response may include a stable error code, error category, field path, controlled message, and request id; **never** expose stack traces, internal class names, passwords, access tokens, or raw SQL to clients. Use `MessageSource`/validation message bundles when supporting multiple languages. Distinguish machine-readable codes (like `INVALID_FIELD`) from human-facing messages.

### 11.1. Reading `BindingResult` Cleanly Instead of Only Checking Status

```java
if (binding.hasErrors()) {
    for (org.springframework.validation.FieldError field :
            binding.getFieldErrors()) {
        String name = field.getField();
        String code = field.getCode();
        boolean conversionOrBinding = field.isBindingFailure();

        // Log/route using name + code safely.
        // Do not log user-supplied values if sensitive data may be present.
    }

    for (org.springframework.validation.ObjectError global :
            binding.getGlobalErrors()) {
        String code = global.getCode();
        // Whole-object errors (e.g., two dates invalid together).
    }
}
```

This snippet illustrates **code inside a method declaring `BindingResult binding`**, not a standalone Java program. `FieldError.getCode()` is usually a short code (e.g., `Min`), whereas `getCodes()` supplies specific codes incorporating object/field/type for `MessageSource` lookup.

## 12. Real-World Traps

1. **Conversion errors are not necessarily separate from binding.** In `@ModelAttribute`, failed conversion to Integer is recorded as a field binding error, typically with `typeMismatch`.
2. **Without `@Valid` enabled, do not expect constraints to run.** An object annotated with `@Min` is not automatically rejected in every context unless validation is triggered.
3. **Validation cannot fix unreadable JSON.** If Jackson fails before creating an object, `@NotBlank`/`@Min` have nothing to evaluate.
4. **Misplaced `BindingResult` breaks behavior.** Place it immediately after the corresponding bound/validated argument.
5. **One field can have multiple failure reasons.** Never assume there is only one `FieldError` per field or a fixed error order.
6. **`@NotNull` differs from `@NotBlank`.** To block whitespace-only names, use `@NotBlank`; `@NotNull` only rejects `null`.
7. **Empty strings can convert to null.** With `Integer`/`Long`, `?age=` may be treated as missing after conversion; do not assume `typeMismatch` for all empty inputs.
8. **Never swallow conversion errors into silent defaults.** If a client sends `age=abc`, defaulting `age=0` can cause subtle business bugs.
9. **Never bind JPA entities directly from arbitrary requests.** Use input DTOs, field allowlists, and service-layer authorization; binders can traverse nested properties if allowed.
10. **`required=false` does not mean data is valid.** It only controls whether input presence is required; present values must still pass type conversion and validation.
11. **Annotations belong to specific layers.** `@RequestBody` uses Jackson/message converters, `@ModelAttribute` uses Spring binding, and Bean Validation constraints run per context; fixing a converter in one layer does not necessarily affect all three.
12. **Do not make exception class names your API contract.** The framework may change wrapper exceptions; contracts should rely on status, error codes, and your application's error schema.
13. **Watch out for the new method validation mechanism.** Adding a constraint directly on a parameter can shift the exception from `MethodArgumentNotValidException` to `HandlerMethodValidationException` in Spring MVC 6.1+.
14. **Syntactically valid data can still violate business rules.** Age 20 may pass type conversion and `@Min` yet still be ineligible for a specific product; separate business validation remains necessary.

## 13. Workflow for Debugging a 400 Request

Ask questions in order instead of guessing:

1. **Did a handler match?** If not, check URL/method/content negotiation first.
2. **Where does the data come from?** Query/path/header/form → Spring argument conversion/data binder; JSON/XML body → HTTP message converter.
3. **Is the input syntactically/type-valid?** `abc` → Integer, malformed JSON brackets, or invalid date formats point to conversion/deserialization.
4. **Was the object created and were properties bound?** For forms, check `BindingResult.getFieldErrors()` and `getSuppressedFields()`.
5. **Did validation run?** Check `@Valid`/`@Validated`, dependencies and constraints, or direct constraints on method parameters.
6. **Did the error come from method validation or argument validation?** Inspect the exception and annotation placement.
7. **Who produced the final HTTP response?** `@ControllerAdvice`, custom exception resolvers, security filters, or gateways can override defaults.
8. **What should be fixed?** Fix the HTTP client if types are wrong; update DTO/converters if the format contract differs; adjust constraints if business rules changed; never disable all validation just to "stop getting 400s."

## 14. Self-Check Exercises

**Exercise 1.** What failure occurs on `GET /input-errors/query?age=xyz`?

**Answer:** Type conversion failure String → Integer in the argument resolver; typically `MethodArgumentTypeMismatchException` and HTTP 400. The controller does not run.

**Exercise 2.** `POST /input-errors/form` with `age=xyz` and `BindingResult` right after `@ModelAttribute`?

**Answer:** Type conversion error **inside binding**, represented in `BindingResult` as a `FieldError` typically coded `typeMismatch`. The controller gets a chance to inspect the errors and return a response.

**Exercise 3.** `age=0` binds to `Integer`, with `@Min(1)` and validation enabled?

**Answer:** Type conversion succeeds; validation fails. The field error code is typically `Min`, not `typeMismatch`.

**Exercise 4.** Will JSON `{"age":"xyz"}` targeting an `Integer age` DTO reliably produce a `FieldError` in `BindingResult`?

**Answer:** No. Jackson may fail to deserialize the object and throw `HttpMessageNotReadableException` before Bean Validation.

**Exercise 5.** JSON `{"age":0}` sent to `@Valid @RequestBody` with `@Min(1)`?

**Answer:** Object deserializes; Bean Validation fails; default is typically `MethodArgumentNotValidException` and 400 (when no `BindingResult` immediately follows).

**Exercise 6.** Why might a handler with `@RequestParam @Min(1) int age` called with `?age=0` not throw `MethodArgumentNotValidException`?

**Answer:** That is a direct constraint on a **method parameter**; Spring MVC 6.1+ normally handles it through method validation and `HandlerMethodValidationException`.

**Exercise 7.** `@ModelAttribute` applies allowed fields, yet the client sends an out-of-list property; does `hasErrors()` always become true?

**Answer:** No. Blocked fields can appear in `BindingResult.getSuppressedFields()` without creating field errors; write an explicit check if needed.

## References

- Spring Framework — Spring MVC Type Conversion: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/typeconversion.html
- Spring Framework — Data Binding: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html
- Spring Framework — `@ModelAttribute` and `BindingResult`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework — Method Arguments: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/arguments.html
- Spring Framework — `@RequestBody`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — Validation, `MethodArgumentNotValidException`, `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — `@InitBinder` and `WebDataBinder`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html
- Spring Framework — MVC Error Responses: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- Jakarta Bean Validation: https://jakarta.ee/specifications/bean-validation/
