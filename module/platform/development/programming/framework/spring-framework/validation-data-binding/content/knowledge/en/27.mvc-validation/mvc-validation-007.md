# MethodArgumentNotValidException When Validating Argument Objects in Spring MVC

## 1. Meaning: data was bound/read yet failed validation

When an HTTP request sends data to create or update an object, Spring MVC has to perform two distinct tasks:

1. **Read/convert data** into a Java object: `@ModelAttribute` uses model/data binding; `@RequestBody` and `@RequestPart` can use `HttpMessageConverter` to read the message/part.
2. **Check constraints** if `@Valid` or `@Validated` and a suitable validator are present, such as Jakarta Bean Validation with `@NotBlank`, `@Email`, `@Min`.

When Spring MVC validates **a handler method's argument object** and finds errors, under the conditions explained below, it throws **`org.springframework.web.bind.MethodArgumentNotValidException`**. This is not an exception from the `@NotBlank` annotation itself; it is a **Spring MVC argument-resolution layer** exception carrying the errors for that argument object.

Example:

~~~java
@PostMapping("/users")
public String create(@Valid @RequestBody UserInput input) {
    return "created";
}
~~~

This is an **in-controller snippet** requiring a `UserInput` DTO declaration and imports. If JSON parsing succeeds yet `input.name` is an empty string and the DTO has `@NotBlank`, Spring can throw `MethodArgumentNotValidException` **before the body of `create` runs**. With a typical MVC setup and no custom error handler, Spring returns **HTTP 400 Bad Request**.

**Key point:** `MethodArgumentNotValidException` reflects the **`BindingResult` of a single method argument**; it does not mean "every request error is a Bean Validation error". For example, malformed JSON is a body-reading error, whereas direct constraints on method parameters may go through a different method validation mechanism.

## 2. Exactly when does Spring MVC throw this exception?

In Spring Framework 6.1+ (including corresponding Spring Boot 3.2+ versions), the MVC documentation distinguishes two mechanisms:

- **Individual argument validation:** `@Valid` or `@Validated` is placed on **a single command object** of `@ModelAttribute`, `@RequestBody`, or `@RequestPart`; there is no `Errors`/`BindingResult` immediately after the argument and no other constraint configuration requiring **method validation**. On errors, Spring MVC throws `MethodArgumentNotValidException`.
- **Method validation:** a Jakarta Validation constraint is placed **directly** on a handler parameter or return value (for instance `@Min(1)` on `@RequestParam int size`). This mechanism also covers nested objects via `@Valid` and normally raises **`HandlerMethodValidationException`** instead of `MethodArgumentNotValidException`.

| Handler signature (illustrative) | On invalid data, typical outcome |
| --- | --- |
| `save(@Valid @RequestBody UserInput input)` | `MethodArgumentNotValidException` if JSON deserializes successfully and Bean Validation then fails. |
| `save(@Valid @ModelAttribute UserInput input)` | `MethodArgumentNotValidException` if binding/validation fails without an immediately following `BindingResult`. |
| `save(@Valid @RequestPart("metadata") UserInput input)` | `MethodArgumentNotValidException` when the part is read into an object that violates constraints. |
| `save(@Valid @RequestBody UserInput input, BindingResult result)` | Controller is invoked and receives errors in `result` when only validation errors for that parameter exist. |
| `search(@RequestParam @Min(1) int size)` | `HandlerMethodValidationException` when method validation is triggered. |
| `save(@NotNull @Valid @RequestBody UserInput input)` | Has direct constraint `@NotNull`, so it may switch to method validation; do not assume `MethodArgumentNotValidException`. |
| `save(@RequestBody UserInput input)` without `@Valid` | Reads JSON into an object; Bean Validation does **not** run automatically just because the DTO has constraints. |
| `save(@Valid @RequestBody List<UserInput> input)` | Being a container, validation behavior cannot be assumed identical to a command object; test against your setup/constraints and version. |

**`@Valid` itself is not a constraint annotation**; it only indicates that the object's constraints should be traversed. Conversely, `@NotNull` is a constraint and can cause method validation to become the primary handling mechanism. For controllers with class-level `@Validated`, method validation may run through an AOP proxy; Spring Framework recommends removing the class-level annotation when wanting built-in MVC method validation since version 6.1.

### Three conditions to remember

1. A **configured validator** and a trigger annotation are required. In Spring Boot, `spring-boot-starter-validation` is typically used.
2. The failure must occur after Spring **already has the argument object or corresponding `BindingResult`**. If JSON cannot be read due to syntax errors, that is a converter error before validation.
3. Placing `BindingResult` or `Errors` **immediately after the validated parameter** allows Spring to pass errors to the controller for local handling instead of throwing an exception for that object alone.

## 3. What is inside `MethodArgumentNotValidException`?

In Spring Framework 6.x, `MethodArgumentNotValidException` extends `BindException` and implements `ErrorResponse`. It holds information about the failed handler parameter and a **`BindingResult`**.

Important APIs:

| API | Meaning |
| --- | --- |
| `getParameter()` | `MethodParameter` describing the handler parameter that failed. |
| `getBindingResult()` | Returns the `BindingResult` containing errors of the bound/validated object. |
| `getFieldErrors()` | List of `FieldError`s (inherited via `BindException`/`BindingResult`). |
| `getGlobalErrors()` | List of object-level errors (for example, class-level constraints). |
| `getAllErrors()` | Both field errors and object/global errors. |
| `getErrorCount()` | Total number of object/field errors in `BindingResult`. |
| `getStatusCode()` | HTTP status per `ErrorResponse`; for this exception it is **400 Bad Request**. |
| `getBody()` | `ProblemDetail` representing the error per Spring `ErrorResponse`; actual response still depends on config/handlers. |

`FieldError` typically provides:

- `getField()`: property name (e.g., `name`, `age`, `address.city`).
- `getCode()`: a specific error code resolved along the code hierarchy (`NotBlank`, `Min`, `typeMismatch`, etc.).
- `getDefaultMessage()`: interpolated message, which can be internationalized.
- `getRejectedValue()`: the offending value if available; **do not pass this value straight into API responses or logs**, as it may be a password, token, or personal data.
- `getObjectName()`: bound object name, helpful when the same controller receives multiple objects.

`ObjectError` (object-level error) may not be tied to a single property. For example, a class-level validator checking two date fields produces an object error unless it explicitly adds a property node.

### Example of reading errors structurally

~~~java
@ExceptionHandler(MethodArgumentNotValidException.class)
ResponseEntity<?> onInvalid(MethodArgumentNotValidException ex) {
    BindingResult result = ex.getBindingResult();

    for (FieldError field : result.getFieldErrors()) {
        System.out.println(field.getField() + ": "
                + field.getCode());
    }

    for (ObjectError error : result.getGlobalErrors()) {
        System.out.println("object: " + error.getCode());
    }

    return ResponseEntity.badRequest().build();
}
~~~

This is a **controller/advice snippet**, not a complete class. It needs imports for `BindingResult`, `FieldError`, `ObjectError`, `ResponseEntity`, and `ExceptionHandler`. The example only illustrates the API; in production, use a logger that redacts sensitive data instead of `System.out`.

**Do not assume** `getFieldErrors()` order is stable enough to serve as an API contract. If you need deterministic ordering in error JSON, sort by field or another defined criterion.

## 4. How do binding errors and validation errors appear together?

`MethodArgumentNotValidException` carries a `BindingResult`, so it can contain two kinds of errors:

1. **Binding/conversion error:** HTTP parameter `age=abc` cannot convert to `Integer` with `@ModelAttribute`, producing a `FieldError` with a `typeMismatch`-related code. If the controller has no adjacent `BindingResult`, the framework can throw `MethodArgumentNotValidException`.
2. **Constraint violation:** the input became a Java object yet fails `@NotBlank`, `@Email`, `@Min`, etc. Spring integrates Jakarta Bean Validation results into `BindingResult`.

Example DTO:

~~~java
public class UserInput {
    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    // getters/setters...
}
~~~

This is an **incomplete class illustration lacking getters/setters**; a full compilable version is in section 6.

With a form request `age=abc`, the binder can produce `typeMismatch`. With JSON `{"age":"abc"}`, Jackson can fail during deserialization and Spring throws `HttpMessageNotReadableException` instead of creating a similar `FieldError`. Both look like "wrong type" to a user, yet **the failure step differs**.

One input can have multiple errors on the same field (for instance, multiple constraints violated simultaneously). Do not arbitrarily assume "one field has at most one error" if the API intends to display all constraint messages. If returning each field name only once, document that explicitly as a summarized contract.

## 5. Role of `BindingResult` immediately after a method argument

Compare the following two handlers.

**Without `BindingResult`:**

~~~java
@PostMapping("/users")
public String create(@Valid @RequestBody UserInput input) {
    // When validation fails, execution normally does not enter here.
    return "ok";
}
~~~

**With `BindingResult` immediately after:**

~~~java
@PostMapping("/users/local")
public ResponseEntity<?> createLocally(
        @Valid @RequestBody UserInput input,
        BindingResult result) {

    if (result.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Invalid data");
    }

    return ResponseEntity.ok("ok");
}
~~~

These two snippets belong to different handlers, not the same mapping. In the second variant, Bean Validation errors for `input` are placed into `result` and handled by the controller itself. Parameter order is critical:

~~~java
// Correct: BindingResult immediately follows the validated object.
void save(@Valid @ModelAttribute UserInput form,
          BindingResult result) {}

// Wrong in intent: an unrelated parameter is inserted in between.
void save(@Valid @ModelAttribute UserInput form,
          @RequestParam String source,
          BindingResult result) {}
~~~

The second snippet requires imports and can fail how Spring resolves `BindingResult`. **Always declare `BindingResult`/`Errors` directly adjacent to its corresponding object**.

When `@RequestBody` **cannot parse JSON** or a required body is missing, it cannot be "turned into" a `BindingResult` for the deserialized object because that object was never created. Furthermore, if method validation is active and there is an error on another parameter without an adjacent `Errors`, `HandlerMethodValidationException` can still occur.

### `@ModelAttribute` and form data

Example:

~~~java
@PostMapping(path = "/users/form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
ResponseEntity<?> submit(
        @Valid @ModelAttribute UserInput input) {
    return ResponseEntity.ok().build();
}
~~~

Servlet request parameters from the form are bound by Spring into `UserInput`. If `age=not-a-number`, `BindingResult` records a field error and MVC can throw `MethodArgumentNotValidException`. Adding `BindingResult result` right after `input` lets the controller return a view/form or return 400 JSON by design.

Do not apply this logic to JSON as if it were a `ServletRequestDataBinder` process: `@RequestBody` uses `HttpMessageConverter`.

## 6. Runnable example: Spring Boot 3.2+, Java 17, and clear REST API errors

The example uses Spring Boot **3.2+** with Spring Framework **6.1+**, Java 17+, Maven, and the `jakarta.validation.*` namespace. Other compatible versions can also be used, provided you keep dependencies aligned with a unified Spring Boot BOM.

### 6.1. Maven dependencies

In a Maven Spring Boot project using `spring-boot-starter-parent` or matching dependency management, include:

~~~xml
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
~~~

The web starter provides Spring MVC and JSON converters; the validation starter provides the Bean Validation provider; the test starter provides JUnit 5 and MockMvc test support.

Create four main files under `src/main/java/com/example/mvcvalidation/` and one test file in `src/test/java/com/example/mvcvalidation/`.

### 6.2. `ValidationMvcApplication.java`

~~~java
package com.example.mvcvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationMvcApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationMvcApplication.class, args);
    }
}
~~~

### 6.3. `UserInput.java`: DTO with three constraints

~~~java
package com.example.mvcvalidation;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class UserInput {

    @NotBlank
    private String name;

    @NotBlank
    @Email
    private String email;

    @NotNull
    @Min(18)
    private Integer age;

    public UserInput() {
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getAge() {
        return age;
    }

    public void setAge(Integer age) {
        this.age = age;
    }
}
~~~

- `@NotBlank` ensures name/email has content after trimming per the constraint's logic.
- `@Email` checks email format per the provider; it does not replace verifying address ownership.
- `@NotNull` checks that `age` is non-null, and `@Min(18)` checks the minimum age.
- The DTO accepts only the three required properties. Do not use an entity containing `role`, `isAdmin`, or `balance` directly, reducing mass assignment risks.

### 6.4. `UserController.java`: JSON, form, and local error handling

~~~java
package com.example.mvcvalidation;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/api/users")
public class UserController {

    @PostMapping(
            path = "/json",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createJson(
            @Valid @RequestBody UserInput input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "created"));
    }

    @PostMapping(
            path = "/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<Map<String, String>> createForm(
            @Valid @ModelAttribute UserInput input) {

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of("status", "created"));
    }

    @PostMapping(
            path = "/local",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<Map<String, String>> createLocally(
            @Valid @RequestBody UserInput input,
            BindingResult result) {

        if (result.hasErrors()) {
            return ResponseEntity.badRequest()
                    .body(Map.of("status", "handled-locally"));
        }

        return ResponseEntity.ok(
                Map.of("status", "accepted"));
    }
}
~~~

**Why does the controller have two error paths?**

- `/json` and `/form` **have no `BindingResult`** in their signatures. Individual object validation errors are thrown as `MethodArgumentNotValidException` and handled by the advice below.
- `/local` has `BindingResult` immediately after `@Valid @RequestBody UserInput`. If JSON deserialization succeeds yet constraints fail, Spring passes errors into the controller; the advice does **not** handle this case.
- If a request sends malformed JSON to `/local`, the controller still may not be invoked because the converter fails before validation.

### 6.5. `ValidationErrorAdvice.java`: returning structured errors

~~~java
package com.example.mvcvalidation;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import java.util.List;
import java.util.Map;

@RestControllerAdvice
public class ValidationErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> onInvalidArgument(
            MethodArgumentNotValidException ex) {

        // Minimal API example: return only field names, do not echo data.
        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        Map<String, Object> body = Map.of(
                "error", "VALIDATION_FAILED",
                "fields", fields
        );

        return ResponseEntity.badRequest().body(body);
    }
}
~~~

Note that this is an **illustrative response schema explicitly chosen by the application**, not Spring's default JSON:

~~~json
{
  "error": "VALIDATION_FAILED",
  "fields": ["age", "email", "name"]
}
~~~

For an input violating all three constraints, this response returns the three field names **deduplicated and sorted** alphabetically. The code intentionally avoids `FieldError#getRejectedValue()` to prevent leaking sensitive data. In a real application, you can add meaningful error codes and i18n messages with an appropriate redaction policy. To handle class-level errors, add `getGlobalErrors()` to the response schema; the current example only has field-level constraints.

### 6.6. `ValidationMvcApplicationTest.java`: 7 MockMvc tests

Create `src/test/java/com/example/mvcvalidation/ValidationMvcApplicationTest.java`:

~~~java
package com.example.mvcvalidation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ValidationMvcApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validJsonReachesController() throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"Lan","email":"lan@example.com","age":22}
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"));
    }

    @Test
    void invalidJsonObjectIsHandledByAdvice() throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","email":"wrong","age":16}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0]").value("age"))
                .andExpect(jsonPath("$.fields[1]").value("email"))
                .andExpect(jsonPath("$.fields[2]").value("name"));
    }

    @Test
    void invalidFormObjectIsHandledByAdvice() throws Exception {
        mvc.perform(post("/api/users/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("email", "lan@example.com")
                    .param("age", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error")
                        .value("VALIDATION_FAILED"))
                .andExpect(jsonPath("$.fields[0]").value("age"));
    }

    @Test
    void validFormIsAccepted() throws Exception {
        mvc.perform(post("/api/users/form")
                    .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                    .param("name", "Lan")
                    .param("email", "lan@example.com")
                    .param("age", "22"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"));
    }

    @Test
    void localBindingResultSuppressesTheGlobalHandler()
            throws Exception {
        mvc.perform(post("/api/users/local")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"name":"","email":"wrong","age":16}
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status")
                        .value("handled-locally"));
    }

    @Test
    void malformedJsonFailsBeforeBeanValidation()
            throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"name\":"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void missingRequiredBodyFailsBeforeController()
            throws Exception {
        mvc.perform(post("/api/users/json")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest());
    }
}
~~~

Run from the root of the project configured with the Maven wrapper:

~~~bash
./mvnw test -Dtest=ValidationMvcApplicationTest
~~~

On Windows use `mvnw.cmd test -Dtest=ValidationMvcApplicationTest`; if Maven is installed globally, use `mvn test -Dtest=ValidationMvcApplicationTest`.

With the starters and default configuration above, **all 7 tests are expected to pass**. Statuses/responses controlled by the code:

| Case | HTTP status | Main response body |
| --- | --- | --- |
| Valid JSON | 201 | `{"status":"created"}` |
| Syntactically valid JSON with three invalid fields | 400 | `{"error":"VALIDATION_FAILED","fields":["age","email","name"]}` |
| Form `age=abc` | 400 | `error=VALIDATION_FAILED`, `fields=["age"]` |
| Valid form | 201 | `{"status":"created"}` |
| Invalid JSON fields with `BindingResult` | 400 | `{"status":"handled-locally"}` |
| Malformed JSON | 400 | Framework error before controller handles it; default schema depends on config. |
| Missing required body | 400 | Framework error before controller handles it; default schema depends on config. |

**Scope of this claim:** the test suite is designed for Spring Boot 3.2+ and Spring MVC 6.1+; a Maven test suite is not proof for every application version or configuration. If you add Spring Security, a custom `@ControllerAdvice`, or replace the MessageConverter/Validator, integration behavior may change and require adjusting the tests. The tests assert field names sorted by the application; they do not assert default provider messages since those can vary by locale.

### 6.7. Sending real requests with curl

While the app is running with `./mvnw spring-boot:run`:

~~~bash
curl -i -X POST "http://localhost:8080/api/users/json" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"wrong","age":16}'

curl -i -X POST "http://localhost:8080/api/users/form" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "name=Lan&email=lan@example.com&age=abc"

curl -i -X POST "http://localhost:8080/api/users/local" \
  -H "Content-Type: application/json" \
  -d '{"name":"","email":"wrong","age":16}'
~~~

This uses Unix shell syntax; PowerShell can use `curl.exe` with appropriate quoting/line continuation. The three requests pass through `@RequestBody`, `@ModelAttribute`, and a handler managing `BindingResult` itself respectively. In the example, all three return HTTP 400, yet **the way errors are raised and handled differs**.

## 7. Handling errors with `ResponseEntityExceptionHandler` or `@RestControllerAdvice`

There are two common ways to standardize errors:

### Approach A — `@RestControllerAdvice` with `@ExceptionHandler`

This is the approach used in section 6. It catches `MethodArgumentNotValidException` and returns an application-specific response. Pros: clear, concise, no need to override other default handlers.

### Approach B — Extending `ResponseEntityExceptionHandler`

If the application wants uniform handling across many Spring MVC exceptions/`ProblemDetail`, you can create a `@ControllerAdvice` extending `ResponseEntityExceptionHandler`. The following example is a **replacement class** for `ValidationErrorAdvice` in the demo; **do not register both handlers simultaneously for the same exception**:

~~~java
package com.example.mvcvalidation;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

import java.util.Map;

@ControllerAdvice
public class CommonMvcErrorHandler
        extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        Object body = Map.of(
                "error", "VALIDATION_FAILED",
                "errorCount", ex.getBindingResult().getErrorCount()
        );

        return handleExceptionInternal(
                ex, body, headers, status, request);
    }
}
~~~

In real code, the `ResponseEntityExceptionHandler` import should be written on a **single line** (wrapped here in the sample for display); the full form is:

~~~java
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
~~~

**Note:** in the example class above, if you add the standard import line yourself, **replace the two wrapped import lines** with the full import line before compiling. This sample only illustrates how to override the handler. The project in section 6 already has a working implementation, so you do not need to add this alternative handler to run the tests.

With Spring Framework 6.x, the protected override signature takes `MethodArgumentNotValidException`, `HttpHeaders`, `HttpStatusCode`, and `WebRequest`. Other versions may change the API; consult the Javadoc for the exact Spring version in your project. Do not simultaneously declare `@ExceptionHandler(MethodArgumentNotValidException.class)` in a subclass when the base class already handles the same exception internally, as that causes mapping ambiguity.

### `ProblemDetail` and `ErrorResponse`

Since Spring Framework 6, `MethodArgumentNotValidException` is an `ErrorResponse`, exposing `getStatusCode()` and `getBody()` of type `ProblemDetail`. The framework can render error responses in RFC 9457 / problem details format depending on configuration. Do not assert that the default HTTP payload is always a fixed JSON structure: Spring Boot, `@ControllerAdvice`, content negotiation, problem-details options, and versions can affect the body.

If the application exposes a public REST API, **choose an error contract with clear versioning/stability**. The `{error, fields}` example in section 6 is intentionally minimal and easy to test; production can add constraint codes, messages, trace IDs, URIs, and global errors without returning raw rejected input to clients.

## 8. Distinguishing closely related exceptions

| Exception/outcome | When does it occur? | How to handle |
| --- | --- | --- |
| **`MethodArgumentNotValidException`** | Spring MVC individual argument binding/validation fails without an adjacent `BindingResult`. | Read `BindingResult`, convert into structured HTTP 400 / field errors. |
| **`HandlerMethodValidationException`** | Built-in Spring MVC method validation checks direct constraints on method parameters/return value and finds errors. | Process the list of parameter validation results; input errors are typically 400, return-value errors typically 500. |
| **`HttpMessageNotReadableException`** | `@RequestBody`/`@RequestPart` cannot read/deserialize the HTTP message, e.g., malformed JSON or missing required body. | Return an appropriate 400; do not confuse with a `@NotBlank` error that already ran. |
| **`HttpMediaTypeNotSupportedException`** | `Content-Type`/`consumes` or converter does not support the request body. | Respond with 415 Unsupported Media Type, guiding clients to send the right format. |
| **`ConstraintViolationException`** | An integration/executable validation layer may throw it carrying `Set<ConstraintViolation>`; not the default return of `Validator#validate`. | Identify the layer, constraints, and HTTP policy; do not equate directly with `MethodArgumentNotValidException`. |
| **`BindException`** | General Spring binding/validation exception; `MethodArgumentNotValidException` extends it in Spring 6.x. | Check subclasses and `BindingResult`; avoid overly broad handlers that mask errors. |
| Jakarta **`ValidationException`** | Misconfigured provider/custom constraint/validation group or abnormal execution failure. | Investigate code/infrastructure; do not blame the client by default. |

**Specifically regarding `HandlerMethodValidationException`:** Spring MVC 6.1+ has a built-in mechanism. Example:

~~~java
@GetMapping("/page")
public String page(@RequestParam @Min(1) int size) {
    return "size=" + size;
}
~~~

This is a snippet with `@RequestParam`, `@Min`, and `@GetMapping` imports; if `size=0`, method validation can throw `HandlerMethodValidationException`. If the controller uses class-level `@Validated` via AOP, the exception pipeline can differ; configure and test explicitly.

When you want to handle both types in `@ControllerAdvice`, you need **two branches matching each exception's data structure**: `MethodArgumentNotValidException#getBindingResult()` describes a single object; `HandlerMethodValidationException#getParameterValidationResults()` describes errors across method parameters.

## 9. Internationalization (i18n), object-level errors, and response safety

### 9.1. Error codes and messages

Jakarta Validation produces `ConstraintViolation`s; Spring converts them into `FieldError`s or `ObjectError`s in `BindingResult`. `MessageCodesResolver` can provide multiple prioritized codes, for example:

~~~text
NotBlank.userInput.name
NotBlank.name
NotBlank.java.lang.String
NotBlank
~~~

This is an **illustrative example** of the object/field/type code idea; the exact object name and code list depend on the binding context. Do not hardcode them into a public API before agreeing on a contract.

With Bean Validation, you can declare:

~~~java
@NotBlank(message = "{user.name.required}")
private String name;
~~~

And `src/main/resources/ValidationMessages.properties`:

~~~properties
user.name.required=Name is required
~~~

`src/main/resources/ValidationMessages_vi.properties`:

~~~properties
user.name.required=Vui lòng nhập tên
~~~

These are **optional snippets**; when applying them, replace the field annotation in the sample DTO and configure locale/message interpolation accordingly. Do not assume errors always come out in Vietnamese just because the server runs in Vietnam. You can use Spring `MessageSource` and the request's `Locale` to interpolate/localize messages according to configuration.

### 9.2. Class-level errors

Constraints placed on a class (for example requiring `startDate <= endDate`) can produce an **object-level violation** and convert to an `ObjectError`. A handler reading only `getFieldErrors()` will **miss** this error; if your contract requires listing all errors, read `getGlobalErrors()` or `getAllErrors()` as well.

When a custom constraint uses `ConstraintValidatorContext#addPropertyNode("endDate")`, it can route a class-level error onto a specific field. Path layout is decided by the custom validator's author, not guessed by `MethodArgumentNotValidException`.

### 9.3. Never expose sensitive data

`FieldError#getRejectedValue()` is handy for preserving form input, yet it can contain PII/secrets. For REST APIs, **avoid returning raw `rejectedValue`, target objects, or full stack traces in error JSON**. Output only field names, error codes, and controlled messages. Every endpoint accepting client input still needs authorization, mass-assignment protection, size limits, and data protection.

If logging:

~~~java
logger.warn("Invalid request: fields={}",
        ex.getBindingResult().getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .toList());
~~~

This is an **in-handler snippet assuming a suitable logger**, not a standalone program. This avoids logging field values; to correlate errors with requests, attach a safely managed request ID.

## 10. Common mistakes and fixes

1. **Adding constraints only on the DTO while forgetting `@Valid`.** Spring reads JSON, yet Bean Validation never runs. Fix by placing `@Valid` or `@Validated` on the proper parameter and configuring a validator.
2. **Missing `spring-boot-starter-validation`.** Without an active provider, constraint expectations may go unmet. Ensure Jakarta Validation and Hibernate Validator dependencies match the Spring Boot BOM.
3. **Thinking malformed JSON throws `MethodArgumentNotValidException`.** The converter could not construct an object yet; typically `HttpMessageNotReadableException` is thrown.
4. **Placing `BindingResult` not immediately after the target object.** Spring may fail to bind errors properly or throw a signature error. Fix the argument order.
5. **Catching all MVC errors with a generic `Exception.class` handler returning 400.** This can hide server bugs and erase distinctions between parser, Bean Validation, method validation, and configuration errors.
6. **Relying on `FieldError` ordering.** Never arbitrarily pick "the first error" as an API contract unless deliberate. Sort/aggregate errors deterministically.
7. **Reading only `getFieldErrors()` when cross-field errors must be reported.** Add `getGlobalErrors()`/`getAllErrors()`.
8. **Using `@Valid` on a container and assuming it behaves identically to a DTO command object.** Understand method validation / element constraint mechanics and test on the actual version.
9. **Mixing class-level `@Validated` on a controller with built-in MVC method validation without understanding proxies.** On Spring Framework 6.1+, consider removing class-level `@Validated` when wanting the new mechanism, and test with direct `@Min`/`@NotBlank`.
10. **Echoing rejected values in responses.** Can leak passwords, tokens, or personal data; never return raw rejectedValue/exception traces.
11. **Confusing `@ModelAttribute` with `@RequestBody`.** Form/query binding and JSON message conversion produce different type-conversion errors; choose the annotation matching your input contract.
12. **Confusing validation with authorization.** Data valid under `@NotNull` may still attempt to update a property the user is not authorized to modify.

## 11. Pre-release checklist

- [ ] DTO includes only inputs actually allowed to be received, with clear constraints.
- [ ] `@Valid`/`@Validated` annotations are placed on arguments to validate; validator dependency is active.
- [ ] `@ModelAttribute`, `@RequestBody`, and `@RequestPart` along with their data-reading/conversion steps are clearly distinguished.
- [ ] If errors should be thrown to advice, **do not place an adjacent `BindingResult`**; if handling in the controller, place it correctly and check `hasErrors()`.
- [ ] Dedicated policies exist for `MethodArgumentNotValidException`, `HandlerMethodValidationException`, JSON reading errors, and media types.
- [ ] Handler processes both field-level and object-level errors if the API schema requires them.
- [ ] Responses are stable and never leak rejected values, stack traces, or server-only details.
- [ ] MockMvc tests cover valid JSON, constraint failures, form `typeMismatch`, local `BindingResult`, and malformed/missing JSON bodies.
- [ ] Locale, error codes, HTTP statuses, and the project's Spring version are verified.
- [ ] Default Hibernate Validator/Spring wording is not hardcoded into test contracts unless message sources are controlled.

**Remember:** `MethodArgumentNotValidException` is how Spring MVC signals that **a bound/deserialized argument object was validated and failed without local handling**. From this exception, extract `BindingResult` to build a structured HTTP 400 response. If the failure happened while reading the HTTP body or during method-level validation, handle the **corresponding different exception mechanism** rather than lumping everything into one class.

## References

- Spring Framework Reference — **Spring MVC Validation** and distinguishing `MethodArgumentNotValidException`/`HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework Reference — **`@RequestBody` and validation**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework Reference — **`@ModelAttribute` argument**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework Javadoc 6.2 — **`MethodArgumentNotValidException`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html
- Spring Framework Javadoc 6.2 — **`ResponseEntityExceptionHandler`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html
- Spring Framework Reference — **Error Responses and ProblemDetail**: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
