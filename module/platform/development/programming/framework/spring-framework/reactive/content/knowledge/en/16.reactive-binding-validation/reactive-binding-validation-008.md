# Distinguishing Decoding, Type Conversion, and Binding Errors in Spring WebFlux

## 1. Goal: identifying which layer an error happens in

When a request enters a Spring WebFlux controller, the data must pass through several steps before business logic can run. For a JSON body, Spring reads bytes and then decodes them into an object. For a query parameter, path variable, or header, Spring usually receives a string and converts that string to a Java type. Once the object is created and bound, Bean Validation can check rules such as `@NotBlank`, `@Email`, and `@Min`. Finally, the service can apply business rules.

The three kinds of errors in the title differ in **timing**, **mechanism**, and **how to fix them**:

1. **Decoding/deserialization errors**: the bytes or body content cannot be read by the codec/`HttpMessageReader` into the target type.
2. **Type conversion errors**: a string-form request value cannot be converted into the Java type of an argument/property.
3. **Binding/validation errors**: the data was read or converted, but cannot be bound properly into the object, or the object violates a constraint.

Do not lump everything into “bad JSON”. A request can send completely valid JSON while the query parameter `page=abc` still fails type conversion; conversely, the body can decode into a DTO successfully while `email` is still invalid.

This lesson focuses on annotation-based Spring WebFlux controllers, how to distinguish errors, common exceptions/statuses, unified handling with `@ControllerAdvice`/`ProblemDetail`, and testing with `WebTestClient`.

## 2. The full pipeline from HTTP bytes to business logic

```text
HTTP request
    |
    +--> Content-Type / body bytes
    |          |
    |          v
    |    HttpMessageReader / codec
    |          |
    |          v
    |    Decode / deserialize into DTO
    |          |
    |          v
    +--> Query / path / header / cookie strings
               |
               v
         ConversionService
               |
               v
         Java argument / property
               |
               v
       Data binding into command object
               |
               v
       Bean Validation (@Valid, @Min...)
               |
               v
       Controller method / service
               |
               v
       Business validation / persistence
```

This is a conceptual model. For a specific controller, argument resolvers can process individual parameters along different branches; for example, the body and query parameters can be resolved independently. The core point is that decoding errors are not the same as conversion errors, and both happen before or during the phase of supplying data to the method. Bean Validation checks the object/arguments after values already have suitable types.

### One single example, three different errors

Suppose an API receives:

```http
POST /accounts?page=abc
Content-Type: application/json

{"name":"","email":"not-an-email","age":16}
```

With the controller expecting:

- `page` is `int`.
- The body is `CreateAccount`.
- `name` must be non-blank, `email` must be properly formatted, and `age` must be 18 or older.

What can happen:

- `page=abc` cannot be converted to `int`: **type conversion failure**.
- If the body is `{"name":`, the JSON is incomplete: **decoding failure**.
- If the body is valid JSON as in the example but the values violate constraints: **validation failure**.

In a real request, the first error detected may prevent later steps from running; the server does not necessarily return all errors at once.

## 3. Decoding errors: bytes/body cannot become an object

### 3.1. Role of `HttpMessageReader` and codecs

With `@RequestBody`, Spring WebFlux uses an `HttpMessageReader` compatible with the media type and target type to read the body. Common codecs:

- Jackson JSON decoder: reads JSON into Java objects.
- String decoder: reads text content into `String`.
- Byte array decoder: reads content into `byte[]`.
- Form reader: parses `application/x-www-form-urlencoded`.
- Multipart reader: parses multipart parts.

Example:

```java
@PostMapping(
        path = "/accounts",
        consumes = MediaType.APPLICATION_JSON_VALUE
)
public Mono<Account> create(@RequestBody Mono<Account> body) {
    return body;
}
```

The request body must be JSON that can be decoded into `Account`, and the application must have a codec supporting that type.

### 3.2. Decoding error cases

**Syntactically invalid JSON**

```json
{"name":"Lan","age":
```

The parser cannot finish the JSON structure. The body cannot be turned into an object.

**JSON with a structure incompatible with the target type**

Suppose `age` is `int`:

```json
{"name":"Lan","age":"many"}
```

If Jackson's configuration cannot coerce the string `"many"` into a number, the decoder throws an error. Some numeric string values can be coerced by Jackson depending on configuration, so you should not rely on a single example to claim that every string-number fails.

**Inappropriate JSON shape**

If the method expects an `Account` object but the body is an array or scalar, the decoder may fail to create the target type. Exact behavior depends on the codec and configuration.

**Empty body when the argument is required**

If the request sends no body while the method requires `@RequestBody`, WebFlux reports an input error instead of creating a default object on its own. If the body can be absent, declare `required=false` or an appropriate type/contract.

**No codec reads the media type or unsupported media type**

This is a case to distinguish: an unsupported `Content-Type` usually leads to **415 Unsupported Media Type** at the reader-selection step, not a JSON syntax error. Only if the media type is supported but the content is wrong is it a decoding error.

**Payload over the limit**

If the body exceeds the memory/read limit of the codec or multipart reader, the server can return **413 Payload Too Large** or a corresponding error depending on configuration. This is a size limit, not a field validation error.

### 3.3. Exceptions and HTTP status

In WebFlux, body reading/decoding errors are usually raised as a 400 input exception, such as `ServerWebInputException` with an underlying cause from the codec/decoder. The exact exception and cause depend on the `HttpMessageReader`, codec, and version.

You need to distinguish:

| Situation | Usual HTTP result |
|---|---|
| Malformed JSON | 400 Bad Request |
| JSON cannot be decoded into target type | 400 Bad Request |
| Missing required body | 400 Bad Request |
| Unsupported `Content-Type` | 415 Unsupported Media Type |
| Payload exceeds limit | 413 Payload Too Large |

Do not catch `DecodingException` everywhere and return 400 manually. Let WebFlux handle the standard exception or standardize the response at the `@ControllerAdvice` layer while keeping the cause for internal logging/tracing.

## 4. Type conversion errors: request string does not become a Java type

### 4.1. Which arguments need conversion?

Many request values are initially received as strings. If the argument is not declared as `String`, Spring automatically applies type conversion through `ConversionService` and registered converters/formatters.

Common examples:

- `@RequestParam("page") int page`
- `@PathVariable UUID id`
- `@RequestHeader("X-Region") Locale region`
- `@CookieValue("expires") LocalDate expires`
- `@MatrixVariable("count") long count`

In WebFlux, `@RequestParam` binds query parameters. Form data and multipart are accessed through separate mechanisms or data binding into a command object; do not confuse the Servlet request parameter model with WebFlux.

### 4.2. Example of an unconvertible query parameter

```java
@GetMapping("/search")
public Mono<String> search(@RequestParam int page) {
    return Mono.just("page=" + page);
}
```

Valid request:

```http
GET /search?page=3
```

Spring converts the string `"3"` into `int 3`.

Invalid request:

```http
GET /search?page=three
```

The number converter cannot convert `"three"` into `int`. The controller method does not run with an invalid `page` value. This is a **type conversion error**, not a JSON decoding error, because the request has no JSON body to parse.

An example with `LocalDate`:

```java
@GetMapping("/events")
public Flux<Event> events(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate from) {
    return eventService.from(from);
}
```

The value `from=2026-03-21` can be converted to `LocalDate`. The value `from=tomorrow` does not match the ISO date format, so conversion fails.

### 4.3. Missing value vs. conversion failure

These two requests are different:

```text
GET /search
GET /search?page=abc
```

If `page` is required and has no value, Spring can raise `MissingRequestValueException` (a kind of `ServerWebInputException`). If there is a value but it cannot be parsed, that is a conversion error, usually wrapped in the corresponding input/type mismatch exception.

Empty values also need attention. When an empty string is turned into `null` by a converter, Spring can treat the result as a missing value. This often happens with `Long`, `UUID`, or types that do not accept `null`. If the argument is genuinely optional, use `required=false`, `Optional<T>`, or `@Nullable` per the contract.

### 4.4. Configuring Converters and Formatters

When a request format is not the default format, you can register a global converter/formatter:

```java
@Configuration
public class WebConfig implements WebFluxConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                OrderCode.class,
                OrderCode::parse
        );
    }
}
```

This is a snippet: `OrderCode` must be an application domain type and have a static `parse(String)` method. Once registered, Spring can convert query/path/header strings to `OrderCode` whenever an argument resolver requests that type.

For per-controller or per-attribute customization, you can use `@InitBinder` to configure `WebDataBinder`. Avoid putting complex business logic inside a converter; a converter should focus on syntax/representation. For example, converting `"PENDING"` to an enum is conversion; checking whether an order is allowed to transition to PENDING is a business rule.

### 4.5. Exceptions and HTTP status

A conversion failure from a request value is usually mapped to **400 Bad Request**. The exception/cause name can differ between named-value argument resolvers and data binding into an object. When debugging, inspect `MethodParameter`, the argument name, the target type, and the cause instead of reading only the message.

Do not change every conversion failure to 422 just because the data is “invalid”. If a value cannot be represented as the declared argument type, 400 is the appropriate default for request syntax/type.

## 5. Binding errors: a value cannot be assigned to an object

**Data binding** is the step of assigning request values to properties or constructor parameters of a command object. This is commonly how forms/search criteria are handled:

```java
public class SearchForm {
    private int page;
    private LocalDate from;

    public int getPage() { return page; }
    public void setPage(int page) { this.page = page; }

    public LocalDate getFrom() { return from; }
    public void setFrom(LocalDate from) { this.from = from; }
}
```

```java
@GetMapping("/search-form")
public Mono<String> search(@ModelAttribute SearchForm form) {
    return Mono.just("page=" + form.getPage());
}
```

Spring creates/binds the object from the request values. If `page=abc`, property conversion fails. `BindingResult` can hold a `FieldError` with the rejected value and field information. Depending on the controller signature, the binding error can be handled right in the method or thrown as `WebExchangeBindException`.

### Using `BindingResult` right after `@ModelAttribute`

```java
@GetMapping("/search-form")
public Mono<ResponseEntity<?>> search(
        @Valid @ModelAttribute SearchForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return Mono.just(
                ResponseEntity.badRequest().body("Invalid search fields"));
    }

    return Mono.just(ResponseEntity.ok(form));
}
```

This is an illustrative snippet. `BindingResult` must sit immediately after the bound/validated argument. If errors are collected into `BindingResult`, the controller method is still called to decide the response itself. Without `Errors`/`BindingResult` in the proper position, Spring can raise `WebExchangeBindException`.

A binding error is not necessarily a Bean Validation error. For example, `page=abc` can produce a field conversion error in `BindingResult`; whereas `page=-1` can convert to a number successfully yet violate `@Min(0)` at the validation step.

## 6. Constraint errors: the object is typed, but violates a constraint

Bean Validation checks values/objects after they have been decoded or bound. Common annotations:

| Constraint | Checks |
|---|---|
| `@NotNull` | Value must not be null |
| `@NotBlank` | String is not null, not empty, and has non-whitespace characters |
| `@NotEmpty` | String/collection/map/array is not empty |
| `@Size(min, max)` | Length or size within range |
| `@Email` | String matches the validator's email rule |
| `@Min` / `@Max` | Numeric bounds |
| `@Positive` | Positive number |
| `@Past` / `@Future` | Point in time in the past/future |

DTO example:

```java
public record CreateAccount(
        @NotBlank String name,
        @Email String email,
        @Min(18) int age
) {}
```

The following body is valid JSON and decodes into the record:

```json
{
  "name": "",
  "email": "not-an-email",
  "age": 16
}
```

However, the object violates three constraints. This is a **validation error**, not a decoding error. The JSON parser is not responsible for deciding whether an email is valid for business rules or whether age is at least 18.

### `@Valid` and `@Validated`

In WebFlux, you can use:

```java
@PostMapping("/accounts")
public Mono<AccountResponse> create(
        @Valid @RequestBody Mono<CreateAccount> body) {
    return body.map(accountService::create);
}
```

`@Valid` asks Bean Validation to apply to the object being read. With per-method-parameter validation such as `@RequestBody`, WebFlux can raise `WebExchangeBindException` if the object violates constraints. This is a 400 error by default.

`@Valid` is not a constraint annotation. It requests cascade validation for the object/nested objects. `@NotNull`, `@Min`, and `@NotBlank` are the constraints.

### Method validation vs. single-object validation

When a constraint is placed directly on a method parameter, for example:

```java
@GetMapping("/pages")
public Mono<String> pages(@RequestParam @Min(1) @Max(100) int page) {
    return Mono.just("page=" + page);
}
```

Spring Framework 6.1+ has built-in method validation. Constraint errors on method parameters can produce `HandlerMethodValidationException`, whereas individual validation of a `@RequestBody` or `@ModelAttribute` usually produces `WebExchangeBindException`.

Applications should be prepared to handle both exception types. If a controller has class-level `@Validated`, method validation may be applied via an AOP proxy; to use Spring Framework 6.1+'s built-in controller method validation, review the placement of `@Validated` at the class level.

### Nested validation

```java
public record Address(
        @NotBlank String city,
        @NotBlank String country
) {}

public record CreateAccount(
        @NotBlank String name,
        @Valid Address address
) {}
```

`@Valid` on `address` tells the validator to descend into the nested object. If `@Valid` is omitted, constraints inside `Address` may not be cascaded from `CreateAccount`.

## 7. Quick comparison table of the three error groups

| Characteristic | Decode | Type conversion | Binding / validation |
|---|---|---|---|
| Input data | Body bytes/stream | Request value string | Object properties/arguments |
| Mechanism | `HttpMessageReader`, codec, Jackson | `ConversionService`, `Converter`, `Formatter` | `WebDataBinder`, `BindingResult`, Bean Validation |
| Example | JSON missing `}` | `page=abc` while argument is `int` | `age=16` violating `@Min(18)` |
| Does controller method run? | Usually not if body argument cannot be resolved | Usually not if argument cannot be converted | Can run if `BindingResult` is present; otherwise usually throws |
| Common exceptions | `ServerWebInputException` with codec cause | `ServerWebInputException`/input type mismatch or binding field error | `WebExchangeBindException`, `HandlerMethodValidationException` |
| Default HTTP status | Usually 400 | Usually 400 | Usually 400 |
| How to fix | Fix JSON/codec/target type | Fix value/format or register converter | Fix field/constraint or handle errors per contract |

Some errors do not fall into these three groups:

- Unsupported request media type: 415.
- Payload over limit: 413.
- Missing required request value: usually 400 with `MissingRequestValueException`.
- Business rule violations such as account already exists: decided by the application, often 409 Conflict or 422 Unprocessable Content depending on the API contract.
- Server/dependency errors: must not be disguised as 400 input errors.

## 8. How to read exceptions and find the root cause

When receiving an HTTP 400, do not log only `exception.getMessage()`. Check:

1. What kind of top-level exception is it?
2. Is there an associated `MethodParameter`?
3. What is the argument/property name and what is the target type?
4. Which field errors does `BindingResult` have?
5. Does the cause chain have any codec, Jackson, conversion, or validator error?
6. Did the error happen before the controller ran, during binding, during validation, or in the service?

Safe logging example:

```java
log.warn(
        "Request input failed: exceptionType={}, message={}",
        error.getClass().getSimpleName(),
        error.getMessage()
);
```

In internal logs, you can record the cause chain according to policy. Do not return stack traces, SQL, file paths, internal class names, or sensitive rejected values to the client.

### `WebExchangeBindException`

`WebExchangeBindException` is a kind of `ServerWebInputException` and contains a `BindingResult`. You can read:

- `getFieldErrors()` to get errors by property.
- `getGlobalErrors()` to get object-level errors.
- `getBindingResult()` to access all binding/validation errors.
- `getField()` and `getCode()` of each `FieldError` to build a structured response.

### `HandlerMethodValidationException`

This exception represents validation applied to a method and groups results by method parameter. Spring provides `visitResults(...)` to classify parameters such as request param, header, model attribute, and others. Use this API when you need to produce consistent errors per argument.

### Decode and conversion errors

Decode errors usually have a cause from the codec/decoder (for example `DecodingException` or a Jackson exception). Conversion errors can have a cause from `ConversionService`, `ConversionFailedException`, `IllegalArgumentException`, or an input exception type. Do not rely solely on nested exception names as a stable public API; wrapping can change across resolvers/codecs/versions.

## 9. Standardizing errors with `ProblemDetail` and `@ControllerAdvice`

A good API returns errors with a stable structure without exposing internals. Spring Framework supports RFC 9457 via `ProblemDetail` and `ErrorResponse`. In WebFlux, you can use `@RestControllerAdvice` or extend `ResponseEntityExceptionHandler`.

Example of building a validation response:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(WebExchangeBindException.class)
    ResponseEntity<ProblemDetail> handleBinding(
            WebExchangeBindException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "One or more request fields are invalid."
        );
        problem.setTitle("Validation failed");

        List<Map<String, String>> errors =
                exception.getFieldErrors().stream()
                        .map(error -> Map.of(
                                "field", error.getField(),
                                "code", error.getCode() == null
                                        ? "invalid"
                                        : error.getCode()
                        ))
                        .toList();

        problem.setProperty("errors", errors);
        return ResponseEntity.badRequest().body(problem);
    }
}
```

This is a snippet requiring imports for `ProblemDetail`, `HttpStatus`, `ResponseEntity`, `WebExchangeBindException`, `RestControllerAdvice`, `ExceptionHandler`, `List`, and `Map`.

In a complete application, you also need to handle `HandlerMethodValidationException`, input/conversion errors, and domain errors according to policy. Do not return rejected values directly if they might contain passwords, tokens, document numbers, or personal data.

Example response:

```json
{
  "type": "about:blank",
  "title": "Validation failed",
  "status": 400,
  "detail": "One or more request fields are invalid.",
  "errors": [
    {"field": "name", "code": "NotBlank"},
    {"field": "email", "code": "Email"}
  ]
}
```

`ProblemDetail` helps clients receive status, title, detail, and field errors consistently. Displayed messages should be controlled and can be internationalized via `MessageSource`; raw exception messages are not always suitable to send directly.

### Do not collapse every error into 400

A generic exception handler like `@ExceptionHandler(Exception.class)` returning 400 can mask a `NullPointerException`, a programming bug, or a database error as a “bad request”. Classify input, validation, domain, and server exceptions; unexpected errors should stay 5xx for investigation.

## 10. Testing each error group with `WebTestClient`

A test suite should include at minimum these cases:

| Test input | Group to verify | Expected result |
|---|---|---|
| Malformed JSON | Decode | 400 |
| JSON field with non-coercible type | Decode | 400 |
| `?page=abc` for `int` argument | Type conversion | 400 |
| `?from=not-a-date` for `LocalDate` | Type conversion | 400 |
| Valid JSON but `name` is blank | Bean Validation | 400 |
| `page=0` with `@Min(1)` | Method validation | 400 |
| Valid JSON satisfying constraints | Success | 200 |

Do not assert only the status if the goal is to identify the exact error group. In unit/integration tests, you can check `ProblemDetail.title`, field error codes, or internal traces. However, do not rely on a default Jackson message because its text can change across versions.

## 11. Runnable Java 17+ project: Spring Boot WebFlux

The example creates a small API with three independent input paths:

- `POST /accounts`: decodes JSON and then validates the DTO.
- `GET /lookup?page=...&from=...`: converts query strings to `int` and `LocalDate`.
- `GET /pages?page=...`: method validation for page bounds.

Uses Java 17+, Maven, and Spring Boot 3.3.5.

### 11.1. Directory structure

```text
webflux-input-errors/
├── pom.xml
└── src/
    ├── main/java/edu/demo/
    │   ├── InputErrorsApplication.java
    │   ├── AccountController.java
    │   └── CreateAccount.java
    └── test/java/edu/demo/
        └── InputErrorsTest.java
```

### 11.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>edu.demo</groupId>
    <artifactId>webflux-input-errors</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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

### 11.3. `InputErrorsApplication.java`

```java
package edu.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(InputErrorsApplication.class, args);
    }
}
```

### 11.4. `CreateAccount.java`

```java
package edu.demo;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateAccount(
        @NotBlank String name,
        @Email String email,
        @Min(18) int age
) {
}
```

### 11.5. `AccountController.java`

```java
package edu.demo;

import java.time.LocalDate;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class AccountController {

    @PostMapping(
            path = "/accounts",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<CreateAccount> create(
            @Valid @RequestBody Mono<CreateAccount> body) {
        return body;
    }

    @GetMapping("/lookup")
    public Mono<String> lookup(
            @RequestParam int page,
            @RequestParam
            @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
            LocalDate from) {

        return Mono.just("page=" + page + ",from=" + from);
    }

    @GetMapping("/pages")
    public Mono<String> pages(
            @RequestParam @Min(1) @Max(100) int page) {
        return Mono.just("page=" + page);
    }
}
```

The controller does not declare class-level `@Validated`; the example uses Spring Framework 6.1+'s built-in method validation for `@Min` and `@Max` on the `page` argument.

### 11.6. `InputErrorsTest.java`

```java
package edu.demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class InputErrorsTest {

    @Autowired
    WebTestClient client;

    @Test
    void validJsonAndValidFieldsReturn200() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "email": "lan@example.com",
                          "age": 22
                        }
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Lan");
    }

    @Test
    void malformedJsonReturns400() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"name\":")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void nonCoercibleJsonFieldReturns400() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "Lan",
                          "email": "lan@example.com",
                          "age": "many"
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidPageStringReturns400() {
        client.get()
                .uri("/api/lookup?page=abc&from=2026-03-21")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void invalidDateStringReturns400() {
        client.get()
                .uri("/api/lookup?page=2&from=not-a-date")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void beanValidationFailureReturns400() {
        client.post()
                .uri("/api/accounts")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {
                          "name": "",
                          "email": "not-an-email",
                          "age": 16
                        }
                        """)
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void methodConstraintFailureReturns400() {
        client.get()
                .uri("/api/pages?page=0")
                .exchange()
                .expectStatus().isBadRequest();
    }

    @Test
    void validQueryArgumentsReturn200() {
        client.get()
                .uri("/api/lookup?page=3&from=2026-03-21")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("page=3,from=2026-03-21");
    }
}
```

Run in the project directory:

```bash
mvn test
```

When dependencies can be downloaded and the test environment works, there are eight tests. The expected result is `Tests run: 8, Failures: 0, Errors: 0, Skipped: 0`. This is an example project for learners to run themselves; passing status is confirmed only after running Maven in a real environment.

### 11.7. Reading what each test means

| Test | What is proven |
|---|---|
| `validJsonAndValidFieldsReturn200` | JSON decodes, constraints are valid |
| `malformedJsonReturns400` | Decoder cannot parse the body |
| `nonCoercibleJsonFieldReturns400` | Decoder cannot assign the `age` token to `int` |
| `invalidPageStringReturns400` | Conversion from query string to `int` fails |
| `invalidDateStringReturns400` | Formatter cannot parse ISO date |
| `beanValidationFailureReturns400` | DTO is created but violates Bean Validation |
| `methodConstraintFailureReturns400` | Argument has the right type but violates `@Min` |
| `validQueryArgumentsReturn200` | Query string conversion succeeds |

Note: the tests above confirm HTTP status and endpoint behavior, not a single internal exception/cause name. If you need to test a specific exception type, write a unit test for the resolver/converter or check the `ProblemDetail` standardized by the application itself.

## 12. How to handle each error type in practice

### 12.1. Decode error

- Confirm the request `Content-Type` is correct.
- Check JSON syntax, shape, and target type.
- Check codec/Jackson modules and custom decoders.
- Do not relax coercion for every case if doing so makes the API accept ambiguous payloads.
- Limit payload size and avoid buffering the entire stream unnecessarily.

### 12.2. Conversion error

- Identify the argument name and target type.
- Check contract formats: numbers, UUID, dates, enums, locale.
- Use `@DateTimeFormat`/`@NumberFormat` when appropriate.
- Register `Converter`/`Formatter` in `WebFluxConfigurer` or `@InitBinder` for domain types.
- Define empty/missing/nullable rules explicitly rather than relying accidentally on null coercion.

### 12.3. Binding and validation errors

- Use `@Valid` for command objects/DTOs.
- Place constraints on the right fields and nested objects.
- Use `@Valid` on nested properties to cascade.
- With `@ModelAttribute`, use `BindingResult` right after the argument if you want to handle it in the controller.
- Handle both `WebExchangeBindException` and `HandlerMethodValidationException`.
- Return structured field errors; do not send stack traces or sensitive rejected values.

### 12.4. Business validation

Bean Validation is suitable for constraints independent of system state, such as a validly formatted email, an age within range, or a required field. Rules depending on current data belong in the service/domain:

- Username is already in use.
- Insufficient balance.
- Order has already moved to a state that cannot be modified.
- Delivery date has no remaining capacity.

Do not query the database inside custom validators for every field if that creates hidden I/O. State-dependent rules should have a clear service flow and domain error mapping per the API contract.

## 13. Standardizing statuses and responses

A guiding table:

| Error | Usually appropriate status | Example |
|---|---:|---|
| Malformed body decode | 400 | JSON missing a brace |
| Unconvertible request value | 400 | `page=abc` for `int` |
| Binding/Bean Validation | 400 | `name` blank |
| Missing required input | 400 | missing required query param/header/body |
| Unsupported media type | 415 | sending `text/plain` to a JSON-only endpoint |
| Payload too large | 413 | exceeding body limit |
| Domain rule conflict | 409 | username already exists |
| Content has valid type/format but cannot be processed by business logic | 422 may fit | requested state cannot be executed per contract |
| Unexpected server error | 500 | unclassified bug or dependency failure |

400 is the common default for input parsing/conversion/validation in WebFlux. 409 and 422 are API/domain decisions; Spring does not automatically infer every business error.

### `ResponseEntityExceptionHandler` and `ErrorResponse`

Spring WebFlux has framework exceptions implementing `ErrorResponse`, providing status, headers, and body per Problem Details. `ResponseEntityExceptionHandler` is a convenient base class for handling WebFlux exceptions and `ErrorResponseException` centrally.

In an application, you should:

1. Use a stable response schema.
2. Map field errors to error codes/field paths.
3. Keep the cause and trace ID in internal logs.
4. Do not send raw exception messages to the client if they might expose details.
5. Distinguish input errors from server errors and domain errors.

## 14. Common design mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling every 400 error a “validation error” | Cannot distinguish parse, conversion, and constraints | Record exception type/cause and layer where it occurred |
| Using Bean Validation to parse strings into numbers | Validation runs after conversion | Use target type/`Converter`/`Formatter` |
| Using `@Email` to handle malformed JSON | Codec cannot create DTO so validator has not run | Fix payload or decoder |
| Assuming right Content-Type means valid JSON | Body can still have wrong syntax/shape | Check decode and validation separately |
| Mixing decode failures and unsupported media types | Returns wrong status or message | 400 for parse; 415 for unsupported media type |
| Using `@Valid` but omitting `@Valid` on nested objects | Nested constraints are not cascaded | Place `@Valid` on nested property |
| Forgetting `HandlerMethodValidationException` | Some method constraint errors are not handled consistently | Handle both method validation and bind validation exceptions |
| Handling only `WebExchangeBindException` | Misses conversion or method validation | Have a general input handler and a specific validation handler |
| Returning unmasked rejected values | Can leak passwords/tokens/PII | Return field + error code, omit raw value |
| Catching `Exception` and always returning 400 | Masks bugs and server errors as client errors | Handle specific exceptions, leave unexpected errors as 5xx |
| Putting business rules in a Converter | Conversion becomes DB/state-dependent logic | Keep converters purely syntactic, check business rules in service |
| Testing only the happy path | Does not catch input failure layers | Test decode, conversion, binding, validation separately |

## 15. Checklist for diagnosing failing requests

When an endpoint returns 400, check in order:

1. **Did the request reach the right endpoint?** Confirm path, method, and mapping.
2. **Is the media type supported?** If not, the error is usually 415.
3. **Can the body bytes be parsed?** Check JSON syntax and shape.
4. **Is the DTO type compatible with the tokens?** Check number/string/array/object, custom codecs, and Jackson configuration.
5. **Can query/path/header be converted?** Confirm target Java type and format.
6. **Is a required value missing or empty?** Distinguish missing from invalid.
7. **Does `BindingResult` have field errors?** Check property path, rejected type, and error code.
8. **Did Bean Validation run?** Confirm `@Valid`, nested `@Valid`, and validator dependency.
9. **Is there method validation?** Handle `HandlerMethodValidationException` if constraints are directly on parameters/return.
10. **Is there business validation after the controller?** Do not confuse domain conflicts with malformed input.
11. **Is the error response standardized?** Check ProblemDetail, status, and correlation ID.
12. **Do logs protect sensitive data?** Do not log raw bodies/rejected values arbitrarily.

## 16. Self-check exercises

**Exercise 1.** An endpoint receives `@RequestBody CreateAccount`. The request sends JSON missing a `}` brace. Which group does the error belong to?

**Answer:** Decode/deserialization failure. The JSON cannot yet be parsed into the DTO; Bean Validation has no object to check yet.

**Exercise 2.** An endpoint receives `@RequestParam int page`. The client sends `page=abc`. Which group does the error belong to?

**Answer:** Type conversion failure. The query string cannot be converted to `int`.

**Exercise 3.** JSON `{"name":"","email":"bad","age":17}` parses into a record successfully, but the DTO has `@NotBlank`, `@Email`, `@Min(18)`. Which group does the error belong to?

**Answer:** Bean Validation failure. The data is already typed, but violates constraints.

**Exercise 4.** `Content-Type: text/plain` is sent to a JSON-only endpoint. Is this a JSON decode error?

**Answer:** No. This is an unsupported media type, usually returning 415 before the JSON decoder processes the body.

**Exercise 5.** What exception does `@Valid @RequestBody Mono<Dto>` violating constraints usually raise in WebFlux?

**Answer:** `WebExchangeBindException` for individual method parameter validation; if method validation applies due to direct constraints on parameters, it can be `HandlerMethodValidationException`.

**Exercise 6.** Is `@Valid` a constraint annotation?

**Answer:** No. It requests cascade validation. `@NotNull`, `@Min`, `@NotBlank` are constraints.

**Exercise 7.** Query `from=` becomes an empty string, while the target is `UUID` or `Long`. Why might it be treated as missing?

**Answer:** A converter may turn an empty string into `null`; Spring may treat a null result as a missing request value if the argument is required.

**Exercise 8.** A username already existing in the database is a conversion error or a Bean Validation error?

**Answer:** Usually it is business/domain validation because it depends on current system state; the service/domain checks and maps it according to the API contract.

## 17. Key takeaways

- **Decode**: body bytes/stream → Java object via `HttpMessageReader`/codec. Malformed JSON or incompatible shape is usually 400.
- **Conversion**: request string → Java type via `ConversionService`/`Converter`/`Formatter`. For example `page=abc` for `int`, usually 400.
- **Binding**: assigns request values to object/properties; errors can reside in `BindingResult`.
- **Bean Validation**: the object is already typed but violates constraints; WebFlux uses `WebExchangeBindException` or `HandlerMethodValidationException` depending on the mechanism.
- **Business validation**: rules depending on system state should live in the service/domain.
- **415** is unsupported media type; **413** is payload over limit; these are not Bean Validation errors.
- Standardize the error response while preserving the internal cause for debugging.

When classifying errors, ask three questions: **can the body be read into an object; can the request value be converted to a Java type; does the object satisfy constraints?** Answering in order pinpoints the layer to fix.

## Official documentation

- Spring Framework 6.2, **WebFlux Validation**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html
- Spring Framework 6.2, **WebFlux `@RequestBody`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html
- Spring Framework 6.2, **WebFlux `@RequestParam`**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestparam.html
- Spring Framework 6.2, **WebFlux Type Conversion**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/typeconversion.html
- Spring Framework 6.2, **WebFlux Data Binding**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/data-binding.html
- Spring Framework 6.2, **WebFlux Error Responses and Problem Details**: https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html
- Spring Framework 6.2, **WebFlux `ServerWebInputException` API**: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/web/server/ServerWebInputException.html
- Spring Framework, **WebTestClient**: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html