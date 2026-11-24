# Distinguishing Malformed JSON Data from Constraint Violations in Spring MVC

## 1. Two kinds of "400 Bad Request" errors occurring at two different layers

When a REST controller receives JSON via `@RequestBody`, there are at least **two independent questions**:

1. **Can the request body be read and converted into a Java object?** This is the job of the HTTP message converter (usually Jackson). A misplaced comma, truncated JSON, or an unconvertible data type can cause this step to fail.
2. **Is the constructed object valid according to business/constraint rules?** This is the job of Jakarta Bean Validation via `@Valid`/`@Validated`, such as `@NotBlank`, `@NotNull`, `@Size`, `@Email`, or `@Min`.

Both error kinds often return HTTP **400**, yet they are **not the same exception** and **should not return the same vague error code**. With Spring MVC 6.x:

- Reading/converting JSON fails: typically `HttpMessageNotReadableException`. The underlying cause can be `JsonParseException` (syntax error), or `InvalidFormatException` / `MismatchedInputException` (cannot map to the Java type).
- Object was read, but violates constraints of a `@Valid @RequestBody` command object: usually `MethodArgumentNotValidException`.
- If Spring MVC applies **method validation** (for example, a controller method has a direct constraint on another parameter), starting in Spring Framework 6.1 this may be `HandlerMethodValidationException` instead of `MethodArgumentNotValidException`.

This lesson focuses on JSON REST endpoints on the **Spring MVC / Servlet stack**, and does not assume identical exception classes for Spring WebFlux. Examples use Java 17, Spring Boot 3.x, Spring Framework 6.x, and the `jakarta.validation.*` package.

## 2. The `@RequestBody` processing pipeline

Typical flow of a POST request:

```text
HTTP POST /users
Content-Type: application/json
        |
        v
DispatcherServlet + HandlerMapping
        |
        v
Select controller method / argument resolver
        |
        v
HttpMessageConverter (typically MappingJackson2HttpMessageConverter)
        |
        +---- JSON cannot be parsed?
        |         |
        |         +--> HttpMessageNotReadableException
        |                    |
        |                    +--> HTTP 400; controller has not run
        |
        +---- JSON parsed, but cannot map to DTO?
        |         |
        |         +--> HttpMessageNotReadableException
        |                    |
        |                    +--> HTTP 400; controller has not run
        |
        v
Java DTO has been created
        |
        +---- @Valid / @Validated and suitable Validator?
        |         |
        |         +--> Validate Jakarta Validation constraints
        |                    |
        |                    +--> Error? MethodArgumentNotValidException
        |                               or HandlerMethodValidationException
        |                               depending on method signature
        |
        v
Controller method is invoked
        |
        v
Business logic / persistence / response
```

**Core rule:** if Jackson cannot construct the method argument, Spring does not yet have an object on which to run Bean Validation for that argument. Therefore, a payload `{"age":"abc"}` with a Java field of type `Integer` **is not a `@Min` violation**; it is a JSON→Java conversion error before `@Min` ever gets a chance to check.

Conversely, `{"age":15}` is valid JSON and converts to `Integer(15)`. When the field has `@Min(18)`, that is a **constraint violation**.

## 3. Four concepts that must be kept separate

| Category | Example | When detected | Typical exception | Default HTTP |
| --- | --- | --- | --- | --- |
| **JSON syntax error** | `{"name":, "age":20}`, missing brace | JSON parser | `HttpMessageNotReadableException`, cause may be Jackson `JsonParseException` | 400 |
| **Mapping / deserialization error** | `{"age":"abc"}` for `Integer age`; array instead of object | Jackson mapping / converter | `HttpMessageNotReadableException`, cause may be `InvalidFormatException`, `MismatchedInputException` | 400 |
| **Constraint violation** | `{"name":"","age":15}` with `@NotBlank` and `@Min(18)` | Jakarta Bean Validation after DTO creation | `MethodArgumentNotValidException` for typical `@Valid @RequestBody` DTO | 400 |
| **Method validation** | `@Min(1) @RequestParam int page` on controller | Spring MVC built-in method validation (6.1+) | `HandlerMethodValidationException` | 400 |

Saying "valid JSON" **is not synonymous** with "a valid payload in every sense". The JSON parser only checks JSON grammar; Jackson also checks Java types and deserialization settings; Bean Validation checks constraints on the populated data.

### 3.1. JSON syntax errors

JSON must have matching braces, colons, commas, and valid escape sequences. Invalid example:

```json
{"name": "Lan", "age": }
```

There is no value after `age:`. Jackson cannot read a valid JSON token, typically throwing a parse exception that Spring wraps in `HttpMessageNotReadableException`. There is no complete `CreateUserRequest` to validate, and the controller method does not run.

Another example:

```text
{"name": "Lan", "age": 20
```

This is an **invalid request body string**, so it is presented as `text` rather than tagging the code fence as `json` in documentation. It is missing the closing `}` for the object.

### 3.2. Syntactically valid JSON that cannot be read as the DTO

```json
{"name": "Lan", "age": "not-a-number"}
```

This is valid JSON. However, if `age` is `Integer`, Jackson by default cannot convert that string into an integer. The error is usually `HttpMessageNotReadableException`, with a corresponding cause such as `InvalidFormatException`.

Other types can also trigger deserialization errors depending on Jackson configuration: unsupported enum values, invalid date/time formats, wrong object/array shape, uninstantiable constructors, invalid polymorphic types, and so on.

**Do not assert that every type mismatch throws an error.** Jackson has coercion features; for example, certain numeric strings can be accepted for integer conversion, or unknown properties may be ignored depending on configuration. When strict input typing is needed, configure Jackson explicitly and test real payloads.

### 3.3. Readable JSON that violates constraints

```json
{"name": "", "age": 15}
```

If the DTO requires `name` to be non-blank and `age >= 18`, Jackson constructs the object successfully, and then Bean Validation detects two violations. With a simple `@Valid @RequestBody`, Spring MVC normally throws `MethodArgumentNotValidException` and returns HTTP 400. **The controller method does not run** unless the exception is handled via another branch.

### 3.4. Valid data

```json
{"name": "Lan", "age": 22}
```

This is syntactically valid JSON, maps cleanly to types, and satisfies the sample DTO constraints; the controller method is invoked.

## 4. Runnable Java 17 example: Spring Boot MVC + Jackson + Jakarta Validation

We create a `POST /users` endpoint with a two-field DTO:

- `name`: must be a non-blank string.
- `age`: must be present and greater than or equal to 18.

The lesson uses a `@RestControllerAdvice` to return **two distinct error codes**:

- `REQUEST_BODY_UNREADABLE` when reading the request body fails.
- `CONSTRAINT_VIOLATION` when data was deserialized but violates constraints.

Both syntax and type conversion errors fall into the unreadable group, **though they can still be classified further by cause if the API genuinely needs it**, provided internal system details are not exposed.

### 4.1. Directory layout

```text
json-vs-validation/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── JsonVsValidationApplication.java
    │   ├── CreateUserRequest.java
    │   ├── UsersController.java
    │   └── ApiErrorHandler.java
    └── test/java/demo/
        └── UsersControllerTest.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>json-vs-validation</artifactId>
    <version>1.0.0</version>

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

`spring-boot-starter-web` brings in Spring MVC and Jackson, while `spring-boot-starter-validation` supplies the Jakarta Validation API and a provider like Hibernate Validator. Without a suitable provider, `@Valid` may not trigger validation as the example expects; verify actual dependencies.

### 4.3. `src/main/java/demo/JsonVsValidationApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonVsValidationApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonVsValidationApplication.class, args);
    }
}
```

### 4.4. `src/main/java/demo/CreateUserRequest.java`

```java
package demo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateUserRequest(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

Why use `Integer` instead of `int`? If `age` is omitted, an `Integer` field can be `null`, letting `@NotNull` accurately detect the missing-value error. With primitive `int`, some deserialization paths may default to 0; tests could then easily confuse "missing" with "age under 18".

For `name`, `@NotBlank` checks `null`, empty strings, and whitespace-only strings. `@Min(18)` checks the numeric value that was read; **it does not check JSON syntax or type coercion**.

### 4.5. `src/main/java/demo/UsersController.java`

```java
package demo;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/users")
public class UsersController {
    @PostMapping
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody CreateUserRequest request) {

        // Executes only when JSON has been deserialized
        // and the DTO violates no constraints.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "status", "created",
                        "name", request.name()
                ));
    }
}
```

`@RequestBody` instructs Spring to read the body using an HTTP message converter; `@Valid` triggers Bean Validation on the DTO after deserialization. Without `@Valid`/`@Validated` or an equivalent activation mechanism, annotations on the DTO **do not automatically throw `MethodArgumentNotValidException`** when the controller is called.

### 4.6. `src/main/java/demo/ApiErrorHandler.java`

```java
package demo;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

@RestControllerAdvice
public class ApiErrorHandler extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        // Do not return ex.getMessage() or stack traces directly to the client.
        Map<String, Object> body = Map.of(
                "code", "REQUEST_BODY_UNREADABLE",
                "message", "JSON body is missing, malformed, or incompatible"
        );

        return new ResponseEntity<>(body, headers, status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<Map<String, String>> errors = ex.getBindingResult()
                .getFieldErrors().stream()
                .sorted(Comparator.comparing(FieldError::getField))
                .map(field -> Map.of(
                        "field", field.getField(),
                        "message", Objects.toString(
                                field.getDefaultMessage(), "Invalid value")
                ))
                .toList();

        Map<String, Object> body = Map.of(
                "code", "CONSTRAINT_VIOLATION",
                "message", "Request fields violate validation rules",
                "errors", errors
        );

        return new ResponseEntity<>(body, headers, status);
    }
}
```

**Why use `ResponseEntityExceptionHandler`?** In Spring MVC, the framework already defines handlers for many standard exceptions. Extending this class and **overriding its protected hooks** is a way to centralize error formatting without creating conflicting `@ExceptionHandler` methods for `HttpMessageNotReadableException` and `MethodArgumentNotValidException`. Do not add `@ExceptionHandler` onto those two overridden methods in the example.

`HttpStatusCode status` and `HttpHeaders headers` are supplied by Spring; the example preserves the status code (typically 400). Returning `REQUEST_BODY_UNREADABLE` helps clients identify body-reading failures, while `CONSTRAINT_VIOLATION` includes the list of violating fields when the data was parseable.

**Intentional limitation of the example:** only these two exceptions are handled. A controller with direct constraints on method parameters may also need to override `handleHandlerMethodValidationException(...)`; section 7 covers when that happens.

### 4.7. `src/test/java/demo/UsersControllerTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.web.bind.MethodArgumentNotValidException;

import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class UsersControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void malformedJsonIsNotReadable() throws Exception {
        MvcResult result = mvc.perform(
                        post("/users")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"name\":,\"age\":20}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("REQUEST_BODY_UNREADABLE"))
                .andReturn();

        assertInstanceOf(HttpMessageNotReadableException.class,
                result.getResolvedException());
    }

    @Test
    void wrongTypeIsNotReadable() throws Exception {
        MvcResult result = mvc.perform(
                        post("/users")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"name\":\"Lan\",\"age\":\"abc\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("REQUEST_BODY_UNREADABLE"))
                .andReturn();

        assertInstanceOf(HttpMessageNotReadableException.class,
                result.getResolvedException());
    }

    @Test
    void validJsonButBadFieldsIsConstraintViolation() throws Exception {
        MvcResult result = mvc.perform(
                        post("/users")
                                .contentType(MediaType.APPLICATION_JSON)
                                .content("{\"name\":\"\",\"age\":15}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.errors.length()").value(2))
                .andExpect(jsonPath("$.errors[0].field").value("age"))
                .andExpect(jsonPath("$.errors[1].field").value("name"))
                .andReturn();

        assertInstanceOf(MethodArgumentNotValidException.class,
                result.getResolvedException());
    }

    @Test
    void missingAgeIsNotNullViolation() throws Exception {
        mvc.perform(post("/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("CONSTRAINT_VIOLATION"))
                .andExpect(jsonPath("$.errors[0].field").value("age"));
    }

    @Test
    void validRequestReachesController() throws Exception {
        mvc.perform(post("/users")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"Lan\",\"age\":22}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status").value("created"))
                .andExpect(jsonPath("$.name").value("Lan"));
    }
}
```

Run tests:

```bash
mvn -q test
```

With the configuration above, **all five tests are expected to pass**, exiting with code 0. We do not assert a fixed Maven stdout format because log formatting, Surefire plugin version, and Spring log levels can vary. The tests verify **HTTP status**, **API error code**, and **resolved Spring exception class** rather than relying on stack traces or Jackson messages that can change across versions.

Start the server:

```bash
mvn spring-boot:run
```

Test with `curl` (on a POSIX shell or using quoting syntax appropriate for your shell):

```bash
curl -i -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  --data '{"name":"Lan","age":22}'

curl -i -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  --data '{"name":"","age":15}'

curl -i -X POST http://localhost:8080/users \
  -H 'Content-Type: application/json' \
  --data '{"name":,"age":20}'
```

Expected HTTP statuses are **201**, **400** due to constraints, and **400** due to unreadable body respectively. Example illustrating the response meaning (key ordering in JSON objects is not guaranteed):

```json
{
  "code": "CONSTRAINT_VIOLATION",
  "message": "Request fields violate validation rules",
  "errors": [
    {"field": "age", "message": "must be greater than or equal to 18"},
    {"field": "name", "message": "must not be blank"}
  ]
}
```

The field messages above are **common English-locale examples**, not a byte-for-byte contract: resource bundles, provider settings, and language can change the wording. For an unreadable body, the response looks like:

```json
{
  "code": "REQUEST_BODY_UNREADABLE",
  "message": "JSON body is missing, malformed, or incompatible"
}
```

There is no `errors` array for fields when Jackson could not construct the DTO. If the application needs to indicate where JSON failed, it can build controlled API error details from the cause, **without exposing raw stack traces or internal class descriptions** to clients.

## 5. Deep dive into exceptions and root causes

### 5.1. `HttpMessageNotReadableException` does not mean "syntax error only"

Spring throws `HttpMessageNotReadableException` when it cannot read the request body with a suitable converter. Common root-cause groups include:

| JSON / request | Common cause | Possible nested cause |
| --- | --- | --- |
| `{"name":,}` | Invalid syntax token | `JsonParseException` |
| `{"age":"abc"}` for `Integer age` | Value cannot convert to a number | `InvalidFormatException` |
| `[]` when DTO object is expected | Incompatible JSON shape | `MismatchedInputException` |
| Broken JSON string escaping | Parser error | `JsonParseException` |
| Empty body when `@RequestBody(required=true)` | Missing required body | `HttpMessageNotReadableException`, not necessarily with a Jackson parse cause |
| Custom deserializer rejects data | Implementation-dependent conversion error | May be `JsonMappingException` or another exception |

Therefore, the name **`REQUEST_BODY_UNREADABLE`** is safer than `JSON_SYNTAX_ERROR` for a general handler. If you want two separate codes, check whether the cause is an instance of `com.fasterxml.jackson.core.JsonParseException`, while still accounting for errors with no cause or causes that change across converters/versions. **Do not force every `HttpMessageNotReadableException` to be treated as `JsonParseException`.**

Also remember: not every request body is read by Jackson. Spring MVC selects a converter based on Java type, `Content-Type`, and available converters. For a normally configured JSON endpoint, Jackson is the typical converter.

### 5.2. What is useful inside `MethodArgumentNotValidException`?

This exception contains a `BindingResult`. For DTO field errors:

- `getFieldErrors()`: list of `FieldError`s with property path, message, rejected value, and constraint/binding metadata.
- `getGlobalErrors()`: object/class-level errors, such as class-level constraints or validators producing object errors.
- `getAllErrors()`: both field errors and object errors.
- `getFieldError("name")` can be used if you need to check a specific field.

Do not assume **every validation error is attached to a field**. For example, password confirmation or cross-field constraints can produce a **global error**. The sample handler only outputs `getFieldErrors()` to keep the example short; real applications should also inspect `getGlobalErrors()`. For complex error data, output a stable schema containing field errors, object errors, error codes, and an appropriate correlation ID.

**Rejected values** can contain emails, passwords, document numbers, or sensitive data. Do not pass raw `FieldError#getRejectedValue()` into responses or general logs.

### 5.3. Constraints do not guarantee field presence

Some constraints treat `null` as valid by default, such as `@Min` and `@Email`. Thus, when you want to require a value, use `@NotNull`; when you want a string with non-whitespace characters, use `@NotBlank`. In the demo:

```java
public record CreateUserRequest(
        @NotBlank String name,
        @NotNull @Min(18) Integer age
) {}
```

`{"name":"Lan"}` parses into a DTO with `age=null`, and then `@NotNull` fails. That is completely different from `{"name":"Lan","age":"abc"}`: the deserialization error happens before Bean Validation executes.

### 5.4. Wrong data type is not always invalid JSON syntax

All of these payloads are syntactically valid JSON:

```json
{"age": "abc"}
```

```json
{"age": null}
```

```json
{"age": 17}
```

Yet with the demo DTO:

- `"abc"`: cannot convert to `Integer` → unreadable.
- `null`: DTO can be constructed successfully → `@NotNull` violated.
- `17`: DTO constructed successfully → `@Min(18)` violated.

Classify by **failure phase**, not merely by "the payload looks wrong".

## 6. HTTP status and API error formatting

### 6.1. Why are both typically 400?

HTTP `400 Bad Request` is appropriate when the client sends an unreadable body **or** input data fails the endpoint's rules. Same status does not mean the same fix:

- For `REQUEST_BODY_UNREADABLE`, the client must fix JSON syntax, shape, types, or ensure a body is sent.
- For `CONSTRAINT_VIOLATION`, the client must fix field values according to the validation rules.

An API may also choose `422 Unprocessable Content` for certain cases where data was parsed but is invalid per business rules, if **that is an agreed contract**. However, in Spring MVC with `@Valid @RequestBody` by default, validation errors map to **400**. Do not switch to 422 without reviewing client contracts and exception handling.

### 6.2. A consistent contract example

Example of a standardized response structure:

```json
{
  "code": "CONSTRAINT_VIOLATION",
  "message": "Request fields violate validation rules",
  "errors": [
    {"field": "age", "message": "must be greater than or equal to 18"}
  ],
  "traceId": "example-correlation-id"
}
```

This is an **extended schema design suggestion**, different from the runnable handler in section 4 because the demo handler **does not yet include `traceId`**. You can attach a correlation ID from request tracing to aid support and log correlation, without putting file paths, implementation class names, or stack traces into client payloads.

Spring supports **`ProblemDetail` / RFC 9457** via `ErrorResponse`, and `ResponseEntityExceptionHandler` supports building error responses out of the box. If an API already uses Problem Details, stick to standard `type`, `title`, `status`, `detail`, `instance` and controlled extension properties instead of inventing inconsistent JSON shapes. The runnable example in section 4 chose a minimal `Map` to highlight the difference between the two error types.

### 6.3. Other errors that should not be lumped together

| Symptom | Typical exception/status | Is it JSON syntax or Bean Validation? |
| --- | --- | --- |
| `Content-Type: text/plain` on a JSON-only endpoint | `HttpMediaTypeNotSupportedException` (415) | No |
| Unsupported HTTP method, e.g., GET on a POST-only endpoint | `HttpRequestMethodNotSupportedException` (405) | No |
| Missing `@Valid` while DTO violates annotations | Controller may still be invoked if no other validation mechanism exists | Does not automatically throw constraint exception |
| Database connection error while processing a valid body | Infrastructure exception, typically 5xx | No |
| DB unique constraint violation after processing a valid DTO | Persistence-layer exception; mapped per API status policy | Not the same as Jakarta Bean Validation |
| `@RequestParam int page` receives `"abc"` | Possibly `MethodArgumentTypeMismatchException` / 400 | Not a `@RequestBody` JSON deserialization error |

The exact Spring MVC media type error class is `HttpMediaTypeNotSupportedException`, not `HttpMessageNotReadableException`; both can occur during request handling, but they carry different meanings.

## 7. Spring MVC 6.1+ case: method validation can change the exception

In Spring MVC 6.1+, if constraints are placed **directly** on method parameters or return values, built-in method validation can validate both those constraints and nested `@Valid` on DTOs.

Example controller method with both kinds of constraints:

```java
@PostMapping("/users")
public String create(
        @RequestParam @Min(1) int tenant,
        @Valid @RequestBody CreateUserRequest body) {
    return "ok";
}
```

This is an **illustrative fragment**, not a method used in the runnable project. If the JSON body is still unreadable, Jackson/converters can still raise `HttpMessageNotReadableException` before all arguments exist to validate the method. If the JSON is readable but method/DTO values are invalid, Spring MVC built-in method validation can raise **`HandlerMethodValidationException`** instead of `MethodArgumentNotValidException`.

Conditions to remember:

- `@Valid` **is not a direct constraint**; on its own, it typically triggers DTO validation at the argument level.
- Direct constraints like `@Min` or `@NotNull` on a method parameter can cause built-in **method validation** to apply.
- A controller with class-level `@Validated` may use **AOP-based method validation** instead of built-in MVC method validation. Per Spring 6.1+ guidance, when the built-in mechanism is desired, remove class-level `@Validated` from the controller.
- `BindingResult`/`Errors` placed immediately after an eligible argument can allow handling errors inside the controller under its own contract, preventing the default exception from surfacing as usual.

Therefore, a complete error handler for MVC 6.1+ typically needs to support both **`MethodArgumentNotValidException` and `HandlerMethodValidationException`**. The API for parameter validation results differs from the field error list of a `BindingResult`; do not cast or treat the two exceptions interchangeably.

In the demo project, the controller **does not put constraints directly on method parameters other than `@Valid`**, because the goal is to demonstrate the exact two branches—"unreadable body" and "DTO constraint violation"—in an easily verifiable way.

## 8. Security and operational notes

1. **Never expose raw Jackson exception messages** to external users. Messages can contain class names, internal property paths, offending input strings, or format details.
2. **Never expose sensitive rejected values** from `FieldError` to clients: passwords, tokens, personal data, and financial information should not appear.
3. **Log at the right level**: client input errors are typically debug/monitoring-level events as appropriate; not every bad input needs an ERROR stack trace. Include a request ID instead of logging entire payloads.
4. **Limit request body size** and configure appropriate deserialization limits to prevent oversized payloads, deeply nested arrays, or resource-exhausting inputs.
5. **Do not turn every exception into 400** via a catch-all `@ExceptionHandler(Exception.class)`. Server errors, configuration errors, database failures, and code bugs must remain distinguishable.
6. **Do not use error wording as the sole API contract.** Keep stable error codes, sensible field paths, and separate localization.
7. **Do not trust annotations merely because they exist.** There must be a Jakarta Validation provider and an activation point such as `@Valid`, `@Validated`, or method-validation integration.
8. **Do not handle parse errors with Bean Validation.** `ConstraintValidator` only receives objects/values after deserialization, not the raw token stream.
9. **Do not persist partial state** to the database if deserialization or validation fails. Normally the controller is not even invoked in those two branches; if a custom deserializer or interceptor causes side effects, evaluate it separately.
10. **Track error rates separately**: rising `REQUEST_BODY_UNREADABLE` may indicate a client version/schema mismatch, whereas rising `CONSTRAINT_VIOLATION` may point to unclear UI rules or out-of-sync data contracts.

## 9. Question-by-question debugging guide

When receiving HTTP 400 from a JSON endpoint:

1. **Check Content-Type.** Is it genuinely `application/json` and supported by a converter? If it is 415, it is a media type issue.
2. **Inspect the raw body** (in a safe environment, avoiding sensitive data). Does the JSON have valid braces, string escapes, and tokens?
3. **Check DTO mapping.** Are field names, enums, numeric types, date/times, collections, custom deserializers, and constructors compatible?
4. **Read the exception class in server logs/tests.** `HttpMessageNotReadableException` means the body could not be read into the argument; inspect the cause for parse error vs. type mismatch.
5. **If deserialization succeeded**, check `@Valid`/`@Validated` and the Jakarta Validation provider, DTO constraints, validation groups, and `@Valid` cascading logic.
6. **If `MethodArgumentNotValidException` occurred**, inspect `BindingResult#getFieldErrors()` and `getGlobalErrors()`. Do not just print `ex.getMessage()`.
7. **If `HandlerMethodValidationException` occurred**, check whether method parameters have direct constraints or return constraints; apply built-in MVC validation according to your version's docs.
8. **If the controller already ran**, the error likely belongs to business logic/DB rather than the two default preprocessing categories.
9. **Verify with tests** simulating malformed JSON, wrong type, valid JSON/invalid constraints, missing required fields, and valid requests.
10. **Check the API response** received by clients: status, code, field details, and consistency across endpoints.

### A short test checklist

| Test case | Input | Expected branch |
| --- | --- | --- |
| Missing value after key | `{"name":,"age":20}` | Unreadable / parse error |
| Wrong numeric type | `{"name":"Lan","age":"abc"}` | Unreadable / mapping error |
| Blank field + underage | `{"name":"","age":15}` | Constraint violation |
| Missing `age` | `{"name":"Lan"}` | Constraint violation via `@NotNull` |
| Success | `{"name":"Lan","age":22}` | Controller returns 201 |
| Missing body when required | Empty body | Unreadable request body |
| Wrong HTTP media type | `text/plain` | 415, neither of the two groups above |
| Added direct method constraint | `@Min(1) @RequestParam int tenant` | May use `HandlerMethodValidationException` |

The most important tests should verify the **actual exception type and response code**. Never rely solely on both categories happening to return status 400.

## 10. Conclusion and principles of application

**Malformed JSON**: the JSON parser cannot read tokens → `HttpMessageNotReadableException`.

**Syntactically valid JSON with wrong DTO type**: the converter cannot construct the object → also typically `HttpMessageNotReadableException`, though the cause is not parser syntax.

**JSON parsed/mapped successfully but violating constraints**: Bean Validation evaluates the object after deserialization → normally `MethodArgumentNotValidException` for `@Valid @RequestBody` command objects; Spring MVC 6.1+ method validation can produce `HandlerMethodValidationException` for applicable controller signatures.

Because all three outcomes may appear to clients as HTTP 400, you need **distinct error codes, consistent response schemas, MockMvc tests, and no leakage of sensitive information**. Classifying accurately by failure stage tells clients whether to fix **JSON syntax/types** or **values against validation rules**.

## References

- [Spring Framework — `@RequestBody` and validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MVC validation and HandlerMethodValidationException](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Framework 6.2 — DefaultHandlerExceptionResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/servlet/mvc/support/DefaultHandlerExceptionResolver.html)
- [Jakarta Validation — Bean Validation 3.0 specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jackson — JsonParseException Javadoc](https://fasterxml.github.io/jackson-core/javadoc/2.17/com/fasterxml/jackson/core/JsonParseException.html)
