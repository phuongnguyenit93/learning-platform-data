# Distinguishing Malformed JSON Syntax, Type Mismatches, and Invalid Data in Spring MVC

## 1. Objectives

The following three HTTP requests can all receive a **400 Bad Request** response, yet **their causes, failure stages, and fixes are completely different**:

```json
{"sku":"A-100", "quantity": 2,
```

```json
{"sku":"A-100", "quantity": "many", "shipping":{"city":"Ha Noi"}}
```

```json
{"sku":"", "quantity": 0, "shipping":{"city":""}}
```

- **Malformed JSON syntax:** the text does not conform to JSON grammar. The first example is missing the closing `}` of the object. The JSON parser cannot build a complete data structure.
- **Wrong JSON type or inability to deserialize to Java types:** the text is valid JSON, but the mapper cannot construct the target Java type. For example, `"quantity": "many"` cannot be converted into an `Integer` under standard Jackson configuration.
- **Invalid data:** the JSON is syntactically valid and converts into a Java object, yet **violates the API's validation rules**, such as quantity ≥ 1, non-blank SKU, or required shipping city.

After this lesson, you will accurately distinguish these three error classes, understand Spring MVC's `@RequestBody` pipeline, know when `HttpMessageNotReadableException` or `MethodArgumentNotValidException` occurs, handle errors in a structured way without leaking internal details, and write tests reproducing each case.

**Scope:** Spring MVC (Servlet stack), Spring Framework 6.x, Spring Boot 3.x, Jackson as the JSON mapper, Java 17+. With WebFlux, Moshi/Gson, or altered Jackson configuration, exception names and type-conversion behavior may differ.

## 2. Three Verification Layers in the Request Path

A request arriving at a controller such as:

```java
@PostMapping("/api/orders")
OrderCreated create(@Valid @RequestBody CreateOrderRequest request) {
    // Called when the body is readable, the object is created, and validation passes.
}
```

*This snippet only illustrates the signature; the full Java application is in Section 8.*

Basic processing flow:

```text
Client
   │
   │ POST /api/orders
   │ Content-Type: application/json
   ▼
DispatcherServlet / RequestMappingHandlerAdapter
   │
   ├─ (A) Select HTTP message converter matching media type
   │      Wrong Content-Type → may return 415 Unsupported Media Type
   │
   ├─ (B) JSON parser (Jackson)
   │      Text violates JSON grammar → JsonParseException
   │      Spring wraps in HttpMessageNotReadableException → 400
   │
   ├─ (C) JSON deserialization / mapping
   │      Valid JSON, but cannot construct CreateOrderRequest:
   │      e.g., String "many" → Integer quantity
   │      → MismatchedInputException / InvalidFormatException
   │      Spring wraps in HttpMessageNotReadableException → 400
   │
   ├─ (D) Validation on constructed Java object (`@Valid`)
   │      @NotBlank, @Min, @NotNull, nested @Valid, ...
   │      → MethodArgumentNotValidException → typically 400
   │
   └─ (E) Controller method
          → processes business logic if input is valid
          → may return business errors like 409/422/400 per contract
```

**Biggest distinction:** JSON can be **syntactically valid** yet **wrong for the Java type**; a Java object can be **constructed successfully** yet **violate validation**. Never lump all three together as "invalid JSON" in API documentation or operational metrics.

**Note on ordering:** the steps above are a mental model and do not promise every request passes through every step. For example, `Content-Type: text/plain` may be rejected when selecting a converter, before the JSON parser runs. A custom converter can combine parsing and mapping in a single call. Routing, security filters, body size limits, or network reads can also stop a request earlier.

## 3. Malformed JSON Errors (Syntax Error)

JSON must obey its own syntax: objects enclosed in `{}`, keys as double-quoted strings, pairs separated by commas, strings properly escaped, and numbers not written in arbitrary JavaScript forms.

### 3.1. Invalid Examples

| Request body | Syntax error | Valid form |
| --- | --- | --- |
| `{"id": 1,` | Missing field or closing brace after comma | `{"id": 1}` |
| `{'id': 1}` | Standard JSON requires double quotes for keys | `{"id": 1}` |
| `{id: 1}` | Property names cannot omit quotes in standard JSON | `{"id": 1}` |
| `{"id": 1,}` | Trailing comma is invalid in standard JSON | `{"id": 1}` |
| `{"active": True}` | JSON booleans are lowercase `true` or `false` | `{"active": true}` |
| `{"name": "A" "age": 3}` | Missing comma between two pairs | `{"name":"A","age":3}` |
| `{"x":"raw↵newline"}` | Unescaped raw newline character inside a JSON string | `{"x":"valid\nnewline"}` |

In these cases, Jackson can report `com.fasterxml.jackson.core.JsonParseException` or a subtype (such as unexpected EOF). When reading `@RequestBody`, Spring MVC typically wraps the error in `org.springframework.http.converter.HttpMessageNotReadableException`. The controller method **is normally not invoked**, because there is no target object to pass in.

If an application enables relaxed parser features (such as allowing single quotes or trailing commas), non-standard JSON may be accepted. The examples in this lesson assume Spring Boot 3's default JSON configuration. Do not confuse "a parser with permissive mode" with "standard JSON allows that syntax".

### 3.2. Reading Parser Errors

Root cause details in server logs can include line/column positions, invalid tokens, and explanations from Jackson. This is helpful when debugging; when returning public API responses, avoid copying full exception messages or raw request bodies into responses, as they can leak data, library versions, and internal structure.

Recommended stable response:

```json
{
  "code": "JSON_SYNTAX",
  "fields": []
}
```

This is an **error contract intentionally designed for the lesson's example**, not Spring Boot's default error format. If an API needs to report line/column details, decide that in a dedicated contract and assess security impact. There is no need to return "fields" when the parser could not even parse a valid JSON document.

### 3.3. How Does a Missing Body Differ from Malformed JSON?

A `POST` request with no body when `@RequestBody(required = true)` (the default) is used can produce an `HttpMessageNotReadableException` such as "Required request body is missing". This is **not strictly a syntax error in a JSON document**, because there is no JSON document to parse. Use a general code like `BODY_NOT_READABLE` or `BODY_REQUIRED` if classifying separately.

A body containing the literal `null` is **valid JSON** (the null literal); what happens next depends on the target type and whether `@RequestBody` requires a non-null object. Do not call it malformed JSON syntax.

## 4. Syntactically Valid JSON with Wrong Types / Deserialization Failures

JSON only has basic value types: object, array, string, number, boolean, and null. Java has richer types (`Integer`, `LocalDate`, `UUID`, enums, records, collections, application-defined classes). Jackson must apply mapping rules between the two sides.

### 4.1. Examples of Valid JSON That Does Not Match Java

Suppose a DTO has `Integer quantity`, `LocalDate deliveryDate`, and `List<String> labels`.

| Input JSON | Target Java Type | Possible Failure Reason |
| --- | --- | --- |
| `{"quantity":"many"}` | `Integer` | Cannot parse string as a number |
| `{"quantity":999999999999}` | `Integer` | Number exceeds integer range |
| `{"deliveryDate":"tomorrow"}` | `LocalDate` | Does not match accepted date parser format |
| `{"labels":{"key":"x"}}` | `List<String>` | Object instead of array, without special coercion config |
| `{"shipping":[] }` | `ShippingAddress` object | Array instead of expected object shape |
| `{"status":"UNKNOWN"}` | `OrderStatus` enum | No enum constant matching the string |
| `{"id":"not-a-uuid"}` | `UUID` | String cannot form a UUID per mapper rules |

Jackson typically throws `com.fasterxml.jackson.databind.exc.MismatchedInputException` or its subtype `InvalidFormatException`. These exceptions are **request reading/mapping** errors, and Spring MVC typically wraps them in `HttpMessageNotReadableException`, so the default HTTP status is commonly **400**.

**Important note on coercion:** a JSON string targeting a numeric Java field does not always fail. Depending on Jackson and its configuration, `"quantity":"2"` **may** be accepted and converted to `Integer(2)`. `2.0`, empty strings, booleans, or a single item instead of an array also behave according to coercion settings. That is why tests use `"quantity":"many"` for a reliable type-mismatch case in the demo config. If the API contract **strictly requires a JSON number**, configure strict deserialization/coercion and add a test; simply declaring `Integer` does not guarantee rejecting numeric strings.

### 4.2. Shape Mismatches and Unreadable Errors

Other cases:

- Nested structures incompatible with the record/class constructor.
- Valid JSON, yet Jackson has no way to instantiate the object (missing creator, unusable constructor, or incompatible polymorphic type config).
- A DTO constructor/creator throws an exception itself; this can also surface as a mapping error.
- Under strict configuration, **undeclared** JSON properties can cause `UnrecognizedPropertyException`. However, Spring Boot typically configures Jackson to ignore unknown properties; do not automatically assume unknown properties are rejected.
- JSON with duplicate keys may be accepted by the parser/mapper unless duplicate-key checks are enabled; do not assume it is always a syntax error.

**Rule:** if the parser understands the JSON document but the mapper cannot construct the expected Java object, it is a **deserialization/mapping** error, not a Bean Validation error. `@NotNull` and `@Min` cannot meaningfully run on a DTO that **could not be constructed**.

A suitable API code:

```json
{
  "code": "JSON_TYPE",
  "fields": []
}
```

In real systems, you can classify further into `JSON_SHAPE`/`JSON_VALUE_FORMAT`/`JSON_TYPE`. Do not assume every `JsonMappingException` is a "client type error": custom deserializers, setter bugs, or server misconfiguration can also cause exceptions. The example in Section 8 only classifies `MismatchedInputException` as `JSON_TYPE`; other failures fall back to a general code.

### 4.3. Null Values and Missing Fields

`null` is a valid JSON value, and omitting a field is not a syntax error either. For example:

```json
{"sku":"A-100","quantity":null,"shipping":{"city":"Ha Noi"}}
```

When `quantity` uses **`Integer`** (wrapper), Jackson can construct the object with `quantity == null`. `@NotNull` on `quantity` then reports a **validation error**. By contrast, primitive `int` cannot hold null, so the mapper may default to `0` or fail depending on `FAIL_ON_NULL_FOR_PRIMITIVES`; this is why request DTOs should generally use wrappers plus explicit constraints for required fields.

`null` for a nested object can also deserialize as null; `@Valid` alone on that field **does not require the field to be present**. Add `@NotNull` if `shipping` is required, and `@Valid` to validate constraints inside when `shipping` is non-null.

## 5. Syntactically and Type-Valid JSON Violating Data Rules

Once the parser and mapper succeed, the Java object can still violate the API's contract:

```java
public record CreateOrderRequest(
    @NotBlank String sku,
    @NotNull @Min(1) Integer quantity,
    @NotNull @Valid ShippingAddress shipping
) {}

public record ShippingAddress(@NotBlank String city) {}
```

*These are illustrative definitions; import Jakarta Validation and place them in an appropriate project. The full version is in Section 8.*

Body:

```json
{"sku":"","quantity":0,"shipping":{"city":""}}
```

The JSON is completely valid syntactically and all Java types can be constructed (`String`, `Integer`, nested record), yet:

- `sku=""` violates `@NotBlank`.
- `quantity=0` violates `@Min(1)`; this is not a number-parsing error.
- `shipping.city=""` violates `@NotBlank` on the nested object; `@Valid` on `shipping` enables cascading into it.
- `@NotNull` makes missing fields or explicit `null` invalid.

If a controller declares `@Valid @RequestBody CreateOrderRequest request` and has **no** `Errors`/`BindingResult` immediately following it, Spring MVC typically throws `org.springframework.web.bind.MethodArgumentNotValidException`. The exception contains a `BindingResult` with `FieldError`s for fields such as `sku`, `quantity`, and `shipping.city`. The default HTTP status is **400 Bad Request** in Spring MVC.

Response built by the example:

```json
{
  "code": "VALIDATION_FAILED",
  "fields": ["quantity", "shipping.city", "sku"]
}
```

Errors can also apply to the whole object (cross-field constraints), not just individual fields. If needed, record `ObjectError`/global errors separately. When designing a JSON API, use stable error codes and localized messages; do not echo raw `getRejectedValue()` when values might contain secrets.

### 5.1. How Do @Valid and @Validated Differ Here?

- `@Valid` is the standard way to request Jakarta Bean Validation on the constructed object. Add `@Valid` on nested properties to cascade validation.
- `@Validated` supports validation groups and Spring integration mechanisms when needed.
- For constraints like `@NotBlank` and `@Min` to run, the project must include a Jakarta Validation implementation, such as `spring-boot-starter-validation`.
- Adding annotations without a validation provider or without triggering validation in the right spot can let invalid requests reach the service.
- **Semantic validation is not the same as database business checks:** for example, duplicate SKU, out of stock, locked order status, or lack of permission to edit an order. Those errors can arise **after** Bean Validation when the controller calls the service; choose HTTP 400/409/422 per contract and semantics rather than forcing everything into `MethodArgumentNotValidException`.

### 5.2. When Is It No Longer MethodArgumentNotValidException?

Starting in Spring MVC 6.1, method validation can apply when constraints are placed directly on handler parameters/return values, such as `@Min(1) @RequestParam int page`. In that case, `HandlerMethodValidationException` may appear instead of `MethodArgumentNotValidException`. That does not change the fact that the error occurs at the validation stage, but you must handle the right exception for your method signatures.

If a controller declares `@Valid @RequestBody Dto dto, Errors errors` **adjacent to each other**, Bean Validation errors on the deserialized object can be handed to the controller instead of throwing `MethodArgumentNotValidException`. Still, `Errors` cannot catch syntax or deserialization failures, because the method never receives a valid DTO.

## 6. Quick Comparison Table: Cause, Exception, HTTP

| Scenario | Stage | Typical Exception | Default/Common HTTP |
| --- | --- | --- | --- |
| `{"quantity":1,}` | JSON syntax | `JsonParseException` inside `HttpMessageNotReadableException` | 400 |
| `{"quantity":"many"}` when expecting `Integer` | Deserialization | `InvalidFormatException`/`MismatchedInputException` inside `HttpMessageNotReadableException` | 400 |
| `{"quantity":0}` with `@Min(1)` | Bean Validation after deserialization | `MethodArgumentNotValidException` | 400 |
| `{"quantity":null}` with `@NotNull` and `Integer` | Bean Validation | `MethodArgumentNotValidException` | 400 |
| Missing body when `@RequestBody` requires a body | HTTP body missing | `HttpMessageNotReadableException` | 400 |
| `Content-Type: text/plain` sent to JSON-only endpoint | Converter/media type selection | `HttpMediaTypeNotSupportedException` | 415 |
| `Accept: text/plain` when endpoint only produces `application/json` | Content negotiation | `HttpMediaTypeNotAcceptableException` | 406 |
| `@RequestParam int page` receiving `page=abc` | Request parameter conversion outside JSON body | `MethodArgumentTypeMismatchException` | 400 |
| Constraint directly on handler parameter | Method validation | `HandlerMethodValidationException` (MVC 6.1+) | 400 for invalid input |
| Valid object violating a business rule | Service/domain | Application-defined exception/response | 400, 409, or 422 per contract |

**Do not guess the cause from HTTP 400 alone.** On the wire, all three main errors can share status 400; distinguishing them requires response error codes, server logs/metrics, or the exception chain.

**Do not rely 100% on a single exception name:** behavior varies across Spring Framework/Jackson versions, converters, exception handler configs, and controller styles. When logging for debugging, inspect `exception.getCause()` and classify carefully; do not expose raw third-party exception class names as a long-term public API contract.

## 7. Designing Helpful JSON Error Contracts for Clients

Frontend/mobile clients need to know whether to **fix request serialization** or **display form errors**. A transparent API can standardize:

| `code` | Meaning for Client | Suggested Action |
| --- | --- | --- |
| `JSON_SYNTAX` | Body is not syntactically valid JSON | Fix serialization, report client/integration bug |
| `JSON_TYPE` | JSON structure/value cannot map to DTO | Fix data type or shape per API contract |
| `BODY_NOT_READABLE` | Body is missing or unreadable for another reason | Check request body and content negotiation |
| `VALIDATION_FAILED` | DTO parsed/deserialized but violated constraints | Display field errors for the user to correct |
| `BUSINESS_RULE_VIOLATION` | Input passed technical validation but violated business rules | Show state message and corresponding guidance |

The sample app returns a simple `{"code":"...","fields":[...]}` shape to highlight the differences clearly. In larger projects you can use `ProblemDetail` (RFC 9457), e.g., `type`, `title`, `status`, `detail`, and extension properties `code`/`errors`. That is a **formatting choice** and does not change where exceptions arise.

Recommendations for servers:

1. Standardize the error response schema across the entire API, including a stable error code and field paths when safe.
2. Never return raw stack traces, raw JSON bodies, server file paths, or Jackson messages containing sensitive data.
3. For validation, return appropriate codes per field; for i18n, render messages from `MessageSource`. Consider bounding the number of errors/elements to avoid oversized responses.
4. Track logs/metrics separately for `JSON_SYNTAX`, `JSON_TYPE`, and `VALIDATION_FAILED`; they represent different signals about client bugs vs. UX.
5. Ensure custom `@RestControllerAdvice` does not swallow every exception into HTTP 400. Server errors unrelated to input should surface properly (typically HTTP 500), not disguised as user errors.
6. Test missing bodies, JSON nulls, unknown fields, string-to-number coercion, nested validation, enum fields, and payload size limits under real deployment settings.

## 8. Runnable Spring Boot 3 + Java 17 Application

The example uses **Spring Boot 3.3.13**, Spring MVC, Jackson, and Jakarta Validation. The demo defines three distinct error codes, plus a fallback for `HttpMessageNotReadableException` when it is not clearly syntax or type mismatch.

### 8.1. Structure

```text
json-errors-demo/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── JsonErrorsDemoApplication.java
    │   ├── OrderController.java
    │   └── JsonErrorAdvice.java
    └── test/java/example/
        └── OrderControllerTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>json-errors-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

`spring-boot-starter-web` provides Spring MVC and standard JSON conversion via Jackson. `spring-boot-starter-validation` enables Jakarta constraints in the demo; `spring-boot-starter-test` includes JUnit Jupiter, MockMvc, and test assertions.

### 8.3. JsonErrorsDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonErrorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonErrorsDemoApplication.class, args);
    }
}
```

### 8.4. OrderController.java

```java
package example;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Package-private records are placed in the same file per Java 17 syntax.
record ShippingAddress(@NotBlank String city) {}

record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @NotNull @Valid ShippingAddress shipping
) {}

record OrderCreated(
        String status, String sku, Integer quantity, String city
) {}

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public OrderCreated create(@Valid @RequestBody CreateOrderRequest request) {
        return new OrderCreated(
                "accepted",
                request.sku(),
                request.quantity(),
                request.shipping().city());
    }
}
```

The records act as both Java DTOs and explicit declarations of validation rules. `@NotNull @Valid ShippingAddress shipping` ensures the nested object is non-null and validates `city`. `@NotBlank String sku` checks the string; `@Min(1) Integer quantity` checks for a positive number after deserialization. The method does not declare `Errors` immediately after the request DTO, so validation errors are routed by Spring to the global exception handler.

### 8.5. JsonErrorAdvice.java

This is the core piece for **classifying** failures instead of returning a generic "invalid JSON" for everything.

```java
package example;

import java.util.List;

import com.fasterxml.jackson.core.JsonParseException;
import com.fasterxml.jackson.databind.exc.MismatchedInputException;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;

// Demo response structure shared across error categories.
record ApiError(String code, List<String> fields) {}

@RestControllerAdvice
public class JsonErrorAdvice extends ResponseEntityExceptionHandler {

    @Override
    protected ResponseEntity<Object> handleHttpMessageNotReadable(
            HttpMessageNotReadableException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        String code = classifyUnreadable(ex);
        return new ResponseEntity<>(
                new ApiError(code, List.of()),
                headers,
                status);
    }

    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(
            MethodArgumentNotValidException ex,
            HttpHeaders headers,
            HttpStatusCode status,
            WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors().stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new ResponseEntity<>(
                new ApiError("VALIDATION_FAILED", fields),
                headers,
                status);
    }

    private static String classifyUnreadable(Throwable error) {
        // Spring may wrap Jackson errors in one or more causes.
        boolean typeMismatch = false;
        Throwable cursor = error;

        while (cursor != null) {
            if (cursor instanceof JsonParseException) {
                return "JSON_SYNTAX";
            }
            if (cursor instanceof MismatchedInputException) {
                typeMismatch = true;
            }
            cursor = cursor.getCause();
        }

        // Do not assume all unreadable errors are syntax or type errors.
        return typeMismatch ? "JSON_TYPE" : "BODY_NOT_READABLE";
    }
}
```

**Why classify this way?**

- `JsonParseException` indicates a parser-level error, hence `JSON_SYNTAX`.
- `MismatchedInputException` (including many `InvalidFormatException` cases) represents input value/shape mapping failures, hence `JSON_TYPE`.
- Missing bodies or other read errors can be `HttpMessageNotReadableException` with neither cause above, so `BODY_NOT_READABLE` serves as fallback.

This is only a **pragmatic demo classification**. There is no guarantee every Jackson deserialization error is a `MismatchedInputException`; `JsonMappingException` also has subtypes related to creator bugs, setters, custom deserializers, or configuration. In production, handle specific cases intentionally, log full details server-side, and keep client responses concise and safe.

`ResponseEntityExceptionHandler` already provides centralized handling for many Spring MVC exceptions. Here we **override** `handleHttpMessageNotReadable`/`handleMethodArgumentNotValid` to unify the body, avoiding writing duplicate `@ExceptionHandler` methods that conflict with inherited handlers.

### 8.6. Running and Sending Four Request Types

Install JDK 17+ and Maven. From the directory containing `pom.xml`:

```bash
mvn test
mvn spring-boot:run
```

Valid request:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-100","quantity":2,"shipping":{"city":"Ha Noi"}}'
```

Expected HTTP **200**, JSON body:

```json
{"status":"accepted","sku":"A-100","quantity":2,"city":"Ha Noi"}
```

**Malformed syntax** request (intentionally missing `}`):

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-100","quantity":2,'
```

Expected HTTP **400**, body:

```json
{"code":"JSON_SYNTAX","fields":[]}
```

**Type mismatch** request (string cannot convert to integer):

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"A-100","quantity":"many","shipping":{"city":"Ha Noi"}}'
```

Expected HTTP **400**, body:

```json
{"code":"JSON_TYPE","fields":[]}
```

**Bean Validation violation** request:

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"sku":"","quantity":0,"shipping":{"city":""}}'
```

Expected HTTP **400**, body:

```json
{"code":"VALIDATION_FAILED","fields":["quantity","shipping.city","sku"]}
```

In this example, all three error statuses are 400, yet **`code` differs** because the cause happened at a different layer. The validation error field list is sorted so it does not depend on provider iteration order. Note that 415 or 406 error responses are not customized to the schema above: inherited handlers may emit `ProblemDetail`, so do not expect `ApiError` for HTTP errors you have not overridden.

The `curl` commands use `\` for line continuation in POSIX shells. On PowerShell, use `curl.exe` on a single line or PowerShell's multiline syntax; avoid the `curl` alias pointing to `Invoke-WebRequest`.

### 8.7. MockMvc Verifying All Three Error Layers

File `src/test/java/example/OrderControllerTest.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validJsonReachesController() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"A-100","quantity":2,
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("accepted"))
            .andExpect(jsonPath("$.quantity").value(2));
    }

    @Test
    void malformedJsonIsSyntaxFailure() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"sku\":\"A-100\",\"quantity\":2,"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("JSON_SYNTAX"));
    }

    @Test
    void invalidIntegerIsDeserializationFailure() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"A-100","quantity":"many",
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("JSON_TYPE"));
    }

    @Test
    void validJsonObjectCanFailBeanValidation() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"","quantity":0,
                             "shipping":{"city":""}}
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(content().json("""
                    {"code":"VALIDATION_FAILED",
                     "fields":["quantity","shipping.city","sku"]}
                    """));
    }

    @Test
    void missingBodyIsNeitherSyntaxNorDtoValidation() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("BODY_NOT_READABLE"));
    }

    @Test
    void nullQuantityDeserializesThenFailsNotNull() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {"sku":"A-100","quantity":null,
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.fields[0]").value("quantity"));
    }

    @Test
    void wrongMediaTypeIs415NotJsonSyntaxError() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("hello"))
            .andExpect(status().isUnsupportedMediaType());
    }

    @Test
    void unacceptableResponseTypeIs406NotJsonError() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .accept(MediaType.TEXT_PLAIN)
                    .content("""
                            {"sku":"A-100","quantity":2,
                             "shipping":{"city":"Ha Noi"}}
                            """))
            .andExpect(status().isNotAcceptable());
    }
}
```

Run:

```bash
mvn test
```

The tests lock in expected behavior: parser errors, mapper errors, constraint errors, missing bodies, syntactically valid null failing constraints, and 415/406 for media types. All tests run through the Spring MVC test context with `MockMvc`; no standalone HTTP server is needed.

**Testing limitation:** the assertions above reflect expectations under the demo config. When changing Jackson features, DTOs, constraint groups, error handlers, or Spring Framework versions, re-run tests and update contracts intentionally.

## 9. Edge Cases That Commonly Cause Misunderstanding

### 9.1. JSON Numbers Quoted as Strings

```json
{"quantity":"2"}
```

Many Jackson setups convert `"2"` into `Integer(2)`, so the request may **succeed** if other fields are valid. If you strictly require a JSON number, enforce a strict coercion policy and write a test proving `"quantity":"2"` is rejected. There is no fixed "inherent JSON type error" independent of the configured **deserialization contract**.

### 9.2. Absent Fields, Nulls, and Empty Strings

| JSON | Target | Common Result |
| --- | --- | --- |
| Missing `quantity` | `Integer quantity` | `null`, then `@NotNull` reports validation error |
| `"quantity":null` | `Integer quantity` | `null`, `@NotNull` reports validation error |
| `"quantity":""` | `Integer quantity` | May become `null` or mapping error depending on coercion; test it |
| `"quantity":"abc"` | `Integer quantity` | Mapping error, cannot construct number |
| `"sku":""` | `String sku` + `@NotBlank` | Type-valid String, validation error |
| `"sku":null` | `String sku` + `@NotBlank` | Null deserializes fine, validation error |
| `"shipping":null` | `@NotNull @Valid ShippingAddress` | Null is syntactically valid; `@NotNull` reports validation error |
| Missing `shipping.city` | `@Valid ShippingAddress` + `@NotBlank city` | If shipping object is created, nested validation reports city |

### 9.3. Date/Time, Enums, and Custom Formats

Suppose a DTO has:

```java
record Appointment(java.time.LocalDate date, Priority priority) {}
enum Priority { LOW, HIGH }
```

JSON `{"date":"tomorrow","priority":"URGENT"}` is syntactically valid JSON, yet Jackson cannot parse the date or enum under standard settings. If you need a different date format, use Jackson configuration such as `@JsonFormat` or a custom deserializer; `@DateTimeFormat` is primarily for Spring type conversion (e.g., forms/queries) and is not a general solution for JSON `@RequestBody`. For unknown enum values, define an explicit policy rather than silently mapping arbitrary values.

### 9.4. Unknown Fields and Duplicate Keys

JSON `{"sku":"A-100","quantity":1,"shipping":{"city":"HN"},"admin":true}` is syntactically valid. `admin` is a field **outside the DTO contract**, yet it will not necessarily fail under Spring Boot's Jackson config: unknown properties may be ignored. To make the API reject them, configure strict deserialization settings and test it. Sensitive entity fields must never be exposed carelessly via request DTOs with matching setters.

With duplicate keys like `{"quantity":1,"quantity":2}`, JSON parsers often accept them unless duplicate-key checking is enabled. Do not claim it is always a syntax error. Decide the policy in your API contract, parser settings, and tests.

### 9.5. Validation After the Controller Is Invoked

If you place `Errors` or `BindingResult` right after `@Valid @RequestBody`, Bean Validation errors can be passed into the method for manual handling. However, if the mapper could not construct the object, the controller still cannot run. Similarly, business checks after parsing/validation (such as stock availability) belong to a separate stage: input can be valid JSON, valid Java types, and pass Bean Validation yet still be rejected by the service.

## 10. Troubleshooting Workflow When an API Returns HTTP 400

1. **Record the HTTP method, URL, Content-Type, and Accept** first. If status is 415/406, fix headers/media types rather than the parser or DTO.
2. **Verify standard JSON syntax** with a parser; check quotes, commas, brackets, escapes, and encoding. If the parser fails, fix the JSON producer.
3. **Compare the Java schema and payload**: object/array, number/string/boolean/null, dates, enums, property keys, generic collections, nested structures; check coercion config.
4. **Check validation constraints**: `@NotNull`, `@NotBlank`, `@Min`, nested `@Valid`, custom validators, and validation groups.
5. **Inspect the server exception chain** to distinguish parser from mapper, then handle via advice. Do not expose sensitive chain details publicly.
6. **Check API error codes**: `JSON_SYNTAX`, `JSON_TYPE`, `VALIDATION_FAILED`; all share HTTP 400, yet the client's corrective action differs.
7. **Write regression tests** with a minimal case for each layer, plus boundaries such as null, missing body, invalid dates/enums, and mismatched Content-Type.

For beginners, set breakpoints in `JsonErrorAdvice.handleHttpMessageNotReadable` and `handleMethodArgumentNotValid`. Those two paths are enough to see the difference between **"object could not be created"** and **"object was created but violated constraints"**.

## 11. Self-Check Questions

1. What kind of error is JSON `{"age": 21,}`? **Syntax error** if the parser enforces standard JSON, due to the trailing comma.
2. What kind of error is JSON `{"age":"twenty"}` into `Integer age`? **Deserialization/type mismatch** under standard Jackson; the JSON itself is syntactically valid.
3. What kind of error is JSON `{"age":17}` into `Integer age` with `@Min(18)`? **Validation**; not a type-conversion error.
4. Is JSON `{"age":null}` into `Integer age` with `@NotNull` a syntax error? **No.** Null is a valid JSON literal; `@NotNull` reports a constraint violation.
5. Is JSON `{"age":"21"}` guaranteed to be a type error? **Not necessarily.** Jackson can coerce numeric strings into integers depending on coercion policy.
6. Why doesn't `BindingResult` after `@RequestBody` catch malformed JSON syntax errors? **No DTO was successfully deserialized**, so the controller has no argument to receive validation results.
7. What Spring exception wraps JSON parser errors? **`HttpMessageNotReadableException`**; the cause may be `JsonParseException`.
8. How is a `@NotBlank` failure on a `@Valid @RequestBody` DTO without an adjacent `Errors` parameter typically reported? **`MethodArgumentNotValidException`**.
9. Does HTTP 415 say anything about JSON syntax? **Not necessarily.** It usually indicates the request media type does not match the endpoint.
10. When an enum receives a non-existent value, why shouldn't you assume it is a validation error? **Jackson can fail before the DTO is created**, which is a deserialization error.
11. Why should an API include a `code` alongside the HTTP status? **Because multiple error stages share HTTP 400 yet require different remedies**.
12. If the DTO parses and validates fine, but the inventory service reports out of stock, is it a JSON error? **No.** That is a business rule, requiring its own error contract and HTTP status.

## 12. References and Key Takeaways

- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): decoding bodies via `HttpMessageConverter` and handling `@Valid`/`Errors`.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): `MethodArgumentNotValidException` and `HandlerMethodValidationException`.
- [Spring MVC — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): converter selection from media types.
- [Spring Framework 6.2 — ResponseEntityExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html): overriding `HttpMessageNotReadableException` and `MethodArgumentNotValidException` branches.
- [Jackson Databind — MismatchedInputException](https://www.javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/exc/MismatchedInputException.html): input mapping/deserialization errors.
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/3.0/): constraint validation on Java objects.

**Rule to remember:** *Syntax* asks "Can the JSON be read as a document?"; *type/deserialization* asks "Can the document be turned into the target Java object?"; *validation* asks "Does the constructed object satisfy the data contract?". Three distinct questions can all yield HTTP 400, so classify by processing layer and return clear feedback.
