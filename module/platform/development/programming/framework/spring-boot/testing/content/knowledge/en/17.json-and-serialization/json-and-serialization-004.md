# Spring Boot Testing — Deserializing Valid, Missing-Field, Wrong-Type, or Extra-Field JSON

## 1. The problem to solve

When a client sends an HTTP POST/PUT/PATCH with `Content-Type: application/json`, Spring MVC must convert the **JSON string** into a **Java object** before the controller invokes business logic. The four most important scenarios are:

1. **Valid:** JSON is syntactically valid, has the right types/shape, and satisfies business input constraints.
2. **Missing field:** JSON omits a property required by the API; Jackson may still create the DTO with `null` or a primitive default.
3. **Wrong type:** JSON cannot be converted into the target Java type, for instance `"quantity": "many"` for a DTO with `Integer quantity`.
4. **Extra field:** JSON sends a property absent from the DTO, for instance `"isAdmin": true`; the app must choose to **intentionally ignore** or **reject** it.

The key is separating two steps: **deserialization** and **validation**:

- **Jackson deserialization** answers: "Can the JSON construct a Java value of the declared type?"
- **Jakarta Bean Validation** answers: "Does the resulting Java object satisfy the input constraints?"
- **Controller/service domain validation** answers: "Is this structurally valid data permitted to perform this business operation?"

JSON can be readable **yet still invalid**. For example, `{"sku":"SKU-1"}` can be converted by Jackson into a record with `quantity == null`; only with `@Valid` and `@NotNull` does MVC reject it with HTTP 400. Conversely, malformed JSON is rejected **before** Jakarta Validator ever runs.

### Learning goals

- Explain the flow `@RequestBody` → `HttpMessageConverter`/Jackson → DTO → `@Valid` → controller.
- Write Java 17 `record`/POJO types suitable for request DTOs.
- Test valid JSON, missing properties, explicit `null`, blank strings, and out-of-range numbers.
- Test syntax errors, wrong shapes, and wrong types that Jackson cannot convert.
- Understand **numeric/string coercion**: a different JSON type does **not always** mean Jackson will fail.
- Understand `FAIL_ON_UNKNOWN_PROPERTIES` and the difference between **plain Jackson** and the **`ObjectMapper` configured by Spring Boot 3.5**.
- Use `@JsonIgnoreProperties(ignoreUnknown = true)` when an API genuinely allows extra fields.
- Standardize errors using `@RestControllerAdvice` without leaking exception text, raw payloads, or secrets.
- Write `@WebMvcTest` + `MockMvc` tests checking status, JSON responses, and verifying the service is not invoked on invalid input.
- Know when to add `@SpringBootTest(RANDOM_PORT)` to test real HTTP.

## 2. How is the request body processed?

Given a controller:

```java
@PostMapping("/api/orders")
public ResponseEntity<?> create(
        @Valid @RequestBody CreateOrderRequest request) {
    // Runs only when the HTTP message converter reads the JSON
    // and Bean Validation finds no errors.
}
```

Condensed flow:

```mermaid
flowchart TD
    A[HTTP request + Content-Type] --> B{Matching handler and converter?}
    B -->|No| C[415 Unsupported Media Type or routing error]
    B -->|Yes| D[Jackson reads JSON syntax and structure]
    D -->|Cannot read| E[HttpMessageNotReadableException]
    D -->|Readable| F[Create Java request DTO]
    F --> G{@Valid and Bean Validation pass?}
    G -->|Invalid| H[MethodArgumentNotValidException]
    G -->|Valid| I[Controller executes]
    E --> J[Advice: 400 INVALID_JSON]
    H --> K[Advice: 400 VALIDATION_ERROR]
    I --> L[HTTP 201/200 or domain response]
```

This diagram focuses on **MVC + one validated command object**. A controller with direct method-level constraints may trigger `HandlerMethodValidationException`; a controller with `BindingResult` right after the parameter can handle errors locally. Those are distinct cases—do not turn every input error into `MethodArgumentNotValidException`.

### Two error layers commonly conflated

| Scenario | Does Jackson create the DTO? | Does Bean Validation run? | Typical exception |
| --- | --- | --- | --- |
| Valid JSON with full values | Yes | Yes, if `@Valid` | None |
| Missing `Integer` `quantity` | Usually yes, field is `null` | Yes, if `@Valid` | `MethodArgumentNotValidException` from `@NotNull` |
| `"quantity":null` present | Usually yes, field is `null` | Yes, if `@Valid` | `MethodArgumentNotValidException` from `@NotNull` |
| `"quantity":0`, requires ≥1 | Yes | Yes | `MethodArgumentNotValidException` from `@Min` |
| `"quantity":"many"` | Cannot convert to number | Does not reach DTO validation | `HttpMessageNotReadableException` |
| JSON `{not-json` | Cannot parse | No | `HttpMessageNotReadableException` |
| JSON is an array instead of a DTO object | Usually cannot deserialize | No | `HttpMessageNotReadableException` |
| Unknown field in strict mode | No | No | `HttpMessageNotReadableException` (wraps Jackson unknown property error) |
| Unknown field in lenient mode | Yes, extra field ignored | Yes, if `@Valid` | No error solely for extra field |
| Empty body with `@RequestBody(required=true)` | No | No | Usually `HttpMessageNotReadableException` |
| `Content-Type: text/plain` for JSON-only endpoint | JSON converter not called | No | Usually HTTP 415 |

**Do not depend on exception classes at the API layer:** Jackson exceptions such as `MismatchedInputException`, `InvalidFormatException`, and `UnrecognizedPropertyException` are typically wrapped inside `HttpMessageNotReadableException` in MVC. The API should return a safe error contract, while tests assert stable status/codes rather than stack trace text.

## 3. Valid DTOs and the role of Java records

Example request for an order:

```json
{
  "sku": "SKU-123",
  "quantity": 2,
  "address": {
    "city": "Da Nang"
  }
}
```

Java 17 record:

```java
public record CreateOrderRequest(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @NotNull @Valid Address address
) {
    public record Address(@NotBlank String city) {}
}
```

This is an **excerpt** omitting imports; the complete version is in section 9.

- `record` defines components, the canonical constructor, and accessors like `sku()`, `quantity()`, and `address()`.
- Compatible Jackson 2.x in Spring Boot 3.5 can deserialize a JSON object into a Java record when JSON names match record components.
- `@NotBlank` forbids `null`, `""`, and whitespace-only strings.
- `@NotNull @Min(1) Integer quantity` requires both a non-null value and at least 1.
- `@NotNull @Valid Address address` both requires a non-null object and cascades validation into `address.city`.
- `@Valid` itself is a **cascade instruction**; it does not make a nullable object mandatory.
- Jackson does not automatically invoke Bean Validation just because annotations exist on the class; MVC integration must place `@Valid`/`@Validated` on the right controller argument, with a validation provider in dependencies.

### Why choose Integer instead of int for required fields?

`Integer` can represent `null`, allowing `@NotNull` to distinguish "client did not send quantity" from "client sent 0." With primitive `int`, under common Jackson 2 settings, a missing property or JSON null can become default `0` (unless strict failure flags are enabled). With `@Min(0)`, that `0` would even pass validation despite the input actually being missing.

**Recommendation:** for required inputs where presence must be verified, use wrapper types `Integer`/`Long`/`Boolean` with `@NotNull`; for required text, use `@NotBlank`; only convert to domain types after validation succeeds.

### Do not bind JPA entities directly

Do not accept `@RequestBody UserEntity` if the entity has `role`, `balance`, `isAdmin`, `creditLimit`, or internal fields with setters. Use a request DTO containing only the properties the endpoint permits; DTO validation and domain authorization are separate layers of responsibility.

If a client sends `"isAdmin":true` and the DTO has no `isAdmin`, a strict mapper rejects it or a lenient mapper ignores it—it will **never** auto-grant admin rights just because the JSON had that field.

## 4. Missing field, explicit null, and default: how do they differ?

Consider these three JSON inputs:

```json
{"sku":"SKU-123","address":{"city":"Da Nang"}}
```

```json
{"sku":"SKU-123","quantity":null,"address":{"city":"Da Nang"}}
```

```json
{"sku":"SKU-123","quantity":0,"address":{"city":"Da Nang"}}
```

In a record with `Integer quantity`, Jackson normally yields `null` for both **missing** and **explicit null**. Bean Validation then flags `@NotNull` for the first two cases, and `@Min(1)` for the third.

| Input form | Java `quantity` after Jackson | Failing constraint | Meaning |
| --- | --- | --- | --- |
| Missing property | `null` | `@NotNull` | Client omitted the field |
| `"quantity":null` | `null` | `@NotNull` | Client sent null |
| `"quantity":0` | `0` | `@Min(1)` | Numeric value out of range |
| `"quantity":1` | `1` | None | Valid lower boundary |
| `"quantity":10` | `10` | None if `@Max(10)` | Valid upper boundary |
| `"quantity":11` | `11` | `@Max(10)` | Exceeds upper bound |
| `"quantity":"many"` | DTO creation fails | None | Jackson cannot convert |

**Note:** a Java record target type does not automatically guarantee every property is present. In Jackson 2.x, `DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES` is typically **disabled by default**, unless a property/creator is declared required per a specific contract. Full missing-creator policies differ from Bean Validation; do not substitute them for `@NotNull` across all APIs.

### When a real app must distinguish "not sent" from "sent as null"

For example, PATCH: omitting `displayName` means "keep as-is," whereas `"displayName":null` means "clear name." A record with `String displayName` loses presence information because both become null. Options include:

- Read `JsonNode` and use `has("displayName")` (presence) and `isNull()` (explicit null).
- Use a wrapper type in the system with **three states**: undefined, explicit null, value.
- Define JSON Merge Patch (RFC 7396), JSON Patch (RFC 6902), or a dedicated PATCH DTO with explicit semantics.

Do not mistake `Optional<String>` in a request DTO for a complete PATCH-presence solution: depending on deserializer/config, `Optional.empty()` can represent both missing and explicit null. **Test with concrete evidence** for each state if the API must distinguish them.

### Is `@JsonProperty(required=true)` the same as `@NotNull`?

No. `@JsonProperty(required=true)` is Jackson metadata that can be used to require a creator property's presence in certain deserialization modes. It does not replace Jakarta Bean Validation and does not automatically ensure every field/setter property is non-null. Conversely, `@NotNull` is a validation provider constraint and only takes effect when validation is triggered.

Do not combine these annotations arbitrarily and assume a single error type: **a "missing creator property" error occurs inside Jackson**, whereas **a `@NotNull` error occurs after the DTO has been constructed**. The API may map both to 400, yet each mechanism should be tested.

## 5. Wrong type: Jackson may reject or coerce automatically

The following requests do not produce the same result:

```json
{"sku":"SKU-123","quantity":"many","address":{"city":"Hue"}}
```

```json
{"sku":"SKU-123","quantity":"2","address":{"city":"Hue"}}
```

```json
{"sku":"SKU-123","quantity":2.5,"address":{"city":"Hue"}}
```

```json
{"sku":"SKU-123","quantity":[],"address":{"city":"Hue"}}
```

- `"many"` → `Integer` usually **cannot be parsed** and causes a deserialization error.
- `"2"` → `Integer` **can be accepted by Jackson 2.x via coercion** if configuration allows it.
- `2.5` → integer types may truncate/convert or be rejected depending on `ACCEPT_FLOAT_AS_INT`/coercion settings.
- `[]` → `Integer` usually mismatches, though empty-array-as-null features and custom deserializers can alter behavior.

**Important:** do not write a test claiming "every string value for Integer must return 400" without disabling coercion. What should be tested is the **API's policy**. The sample tests `"many"` and a top-level JSON array—two cases clearly incompatible with the DTO record.

### Related Jackson 2.x flags

| Setting | Effect | Consequence |
| --- | --- | --- |
| `FAIL_ON_UNKNOWN_PROPERTIES` | Rejects properties not on the DTO | Extra field → Jackson error |
| `FAIL_ON_NULL_FOR_PRIMITIVES` | Rejects JSON null for primitives | Prevents null from becoming 0/false |
| `FAIL_ON_MISSING_CREATOR_PROPERTIES` | Requires creator properties to be present | Missing constructor input → Jackson error |
| `FAIL_ON_NULL_CREATOR_PROPERTIES` | Rejects null creator properties | JSON null creator input → Jackson error |
| `ACCEPT_FLOAT_AS_INT` | Allows converting floats to integers | Risks silent truncation if enabled |
| `ACCEPT_EMPTY_STRING_AS_NULL_OBJECT` | Treats empty strings as null for some object types | Requires careful scoping |
| `FAIL_ON_TRAILING_TOKENS` | Rejects extra characters/tokens after the root JSON value | E.g. `{} {}` is not read as a valid document |
| `JsonParser.Feature.STRICT_DUPLICATE_DETECTION` | Detects duplicate JSON object field names | Useful for APIs forbidding duplicate keys |

Depending on Jackson minor version and deserializer, `CoercionConfig` also manages coercion per input shape/target type. Not every flag applies identically to `int`, `Integer`, enums, dates, collections, or custom classes. When configuring stricter settings, use **small tests verifying desired behavior** rather than changing the entire `ObjectMapper` and regressing other APIs.

### Which ObjectMapper does Spring MVC use?

A common mistake is testing:

```java
ObjectMapper mapper = new ObjectMapper();
```

and concluding Spring MVC behaves identically. That is **not always true**: the `ObjectMapper` auto-configured by Spring Boot has defaults/customizers, Java time modules, naming strategies, and feature flags from `application.properties`. The sample project tests both plain Jackson and the Spring Boot-provided `ObjectMapper` to illustrate the difference.

## 6. Extra fields: differences between plain Jackson and Spring Boot

Suppose a DTO has only three fields `sku`, `quantity`, and `address`, yet the client sends:

```json
{
  "sku":"SKU-123",
  "quantity":2,
  "address":{"city":"Hue"},
  "isAdmin":true
}
```

Jackson 2.x `new ObjectMapper()` defaults to `FAIL_ON_UNKNOWN_PROPERTIES=true`; extra properties can cause `UnrecognizedPropertyException`. However, **Spring Boot 3.x configures its Jackson mapper with `FAIL_ON_UNKNOWN_PROPERTIES=false` by default**, so extra fields are typically ignored unless stricter configuration is applied.

To make an API **actively reject undeclared fields**, enable:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
```

In the sample project, this property is in `src/test/resources/application-test.properties` and the test activates `@ActiveProfiles("test")`. Do not infer policy from "Jackson defaults" without checking the properties of the **Boot-configured ObjectMapper**. When applying this to production, configure the strict policy consistently in production config/contracts if external clients truly must obey that constraint.

### When should you be strict?

- Write APIs (create/update) requiring a tight contract and wanting to catch client typos like `quanity` instead of `quantity`.
- Extra fields could indicate client domain misunderstanding or payload/over-posting attacks.
- Avoiding the bug where "requests return 200 yet a property the user thought was saved was silently ignored."

**Trade-off:** adding a valid field in a newer client version can cause an older server to reject payloads. APIs prioritizing forward compatibility sometimes intentionally permit extra fields. The strict/lenient choice belongs in the **API versioning policy**, not random developer preference.

### Lenient on one DTO type, without loosening the whole API

For payloads that permit extensibility, you can write:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public record LenientPreviewRequest(String sku, Integer quantity) {
}
```

`@JsonIgnoreProperties(ignoreUnknown = true)` lets Jackson ignore unknown properties **on that type**, even when the global mapper is strict. The sample uses endpoint `/api/orders/preview` to demonstrate this distinction deliberately.

**Do not confuse with:**
- `@JsonIgnore`: ignores a known property in the JSON model, not arbitrary unknown fields.
- `@JsonProperty("snake_case_name")`: sets the mapping name of a property, without opening arbitrary properties.
- `@JsonAlias({"legacyName"})`: accepts alternative names during deserialization, without retaining arbitrary extra fields.
- `@JsonAnySetter`: captures unknown fields into an intentional map/handler, not the same as ignoring them.
- `@JsonIgnoreProperties(value={"internalField"})`: declares named properties to ignore, different from `ignoreUnknown=true`.

If you need to collect extensible metadata, use `Map<String,Object>` or `@JsonAnySetter` and enforce size/format/allowlist checks. Never let extra fields directly influence permissions, pricing, order status, or security-sensitive logic.

## 7. HTTP error policy: 400 is not enough to conclude

The sample chooses two error codes:

| API code | HTTP status | Situation | Stage |
| --- | --- | --- | --- |
| `INVALID_JSON` | 400 | Syntax error, type mismatch, forbidden unknown property, missing body | Jackson/message converter |
| `VALIDATION_ERROR` | 400 | DTO constructed, but `@NotBlank`, `@NotNull`, `@Min`, `@Max` fails | Jakarta Validation |

And several other errors are **not** lumped into those two codes:

| Case | Usually appropriate HTTP status | Why |
| --- | --- | --- |
| `Content-Type: text/plain` for a JSON-only endpoint | 415 | No converter matches `consumes` |
| Unsupported HTTP method | 405 | Route contract violation, not JSON |
| Non-existent endpoint URL | 404 | No handler |
| Unauthenticated client | 401 | Security, not validation |
| Unauthorized client | 403 | Authorization, not JSON |
| Resource conflict/already exists | 409 | Domain policy |
| Server bug, DB outage, or response serialization failure | Appropriate 5xx | Should not turn into an input error |
| `@Valid` DTO is valid, yet business rules forbid the action | Per domain contract, e.g. 409/422 | Bean Validation does not replace business rules |

Return a stable error body without leaking internal details, such as:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "quantity",
      "message": "quantity is required"
    }
  ]
}
```

For Jackson parse exceptions:

```json
{
  "code": "INVALID_JSON",
  "errors": [
    {
      "field": "body",
      "message": "JSON body is invalid or missing"
    }
  ]
}
```

Do not send `JsonMappingException.getPathReference()`, raw input, rejected passwords/tokens, or stack traces to clients. If the product uses RFC 9457 `ProblemDetail`, you can use that standard format with stable error codes; what matters is testing **one agreed API contract**.

## 8. Runnable project: Java 17, Spring Boot 3.5, Maven

This project intentionally uses **Spring MVC + Mockito tests** without a database. It isolates Jackson/validation/network errors without noise from SQL, transactions, or external services.

Endpoints:

| Endpoint | Meaning | Expectation |
| --- | --- | --- |
| `POST /api/orders` | Strict JSON DTO, validates sku/quantity/address | 201 + `{"id":...}` when valid |
| `POST /api/orders` | Missing field, null, or out-of-range value | 400 + `VALIDATION_ERROR` |
| `POST /api/orders` | Syntax error, type mismatch, unknown property | 400 + `INVALID_JSON` |
| `POST /api/orders/preview` | Lenient DTO ignoring unknown fields | 200 + echoed sku/quantity |
| JSON-only endpoint with `text/plain` | Invalid media type | 415 |

### 8.1. File structure

```text
json-deserialize-demo/
├── pom.xml
└── src/
    ├── main/java/example/jsondemo/
    │   ├── JsonDemoApplication.java
    │   ├── CreateOrderRequest.java
    │   ├── LenientPreviewRequest.java
    │   ├── OrderService.java
    │   ├── OrderController.java
    │   ├── ApiError.java
    │   └── ApiExceptionAdvice.java
    └── test/
        ├── resources/application-test.properties
        └── java/example/jsondemo/
            ├── OrderControllerTest.java
            ├── JacksonBasicsTest.java
            └── RealHttpJsonIntegrationTest.java
```

### 8.2. pom.xml

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
    <artifactId>json-deserialize-demo</artifactId>
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

`spring-boot-starter-validation` is a separate dependency: do not assume `spring-boot-starter-web` already contains the provider. Validation annotations only take effect when a Jakarta Validation provider is active and the controller applies `@Valid`. The Boot parent manages Spring/Jackson/JUnit/Mockito versions.

### 8.3. application-test.properties

`src/test/resources/application-test.properties`:

```properties
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.main.banner-mode=off
logging.level.org.springframework.web=WARN
```

**Sample policy:** unknown JSON properties are rejected by default in the test profile. If production must also be strict, configure strict mode **in production** per contract; this test file does not alter production behavior.

### 8.4. Spring Boot application

`src/main/java/example/jsondemo/JsonDemoApplication.java`:

```java
package example.jsondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonDemoApplication.class, args);
    }
}
```

Placing the application and classes under package `example.jsondemo` lets default component scan discover the controller, advice, and service.

### 8.5. Strict request DTO

`src/main/java/example/jsondemo/CreateOrderRequest.java`:

```java
package example.jsondemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotBlank(message = "sku is required")
        @Size(min = 3, max = 20,
              message = "sku length must be between 3 and 20")
        String sku,

        @NotNull(message = "quantity is required")
        @Min(value = 1, message = "quantity must be at least 1")
        @Max(value = 10, message = "quantity must be at most 10")
        Integer quantity,

        @NotNull(message = "address is required")
        @Valid Address address
) {
    public record Address(
            @NotBlank(message = "city is required") String city) {
    }
}
```

This is an immutable DTO; the demo uses no custom constructors or business defaults. Hence Jackson cleanly distinguishes shape/type, Jakarta Validator checks constraints, and tests clearly pinpoint where failures happen.

### 8.6. Explicitly lenient DTO

`src/main/java/example/jsondemo/LenientPreviewRequest.java`:

```java
package example.jsondemo;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LenientPreviewRequest(
        String sku, Integer quantity) {
}
```

This type intentionally **has no constraints**: the preview endpoint only illustrates that Jackson can ignore extra fields with a local annotation. It is not a template for a real write API without adding validation/authorization rules.

### 8.7. Database-free service keeping tests focused on JSON

`src/main/java/example/jsondemo/OrderService.java`:

```java
package example.jsondemo;

import java.util.concurrent.atomic.AtomicLong;
import org.springframework.stereotype.Service;

@Service
public class OrderService {
    private final AtomicLong ids = new AtomicLong(100);

    public long create(String sku, int quantity, String city) {
        // Demo: return a new ID; no database.
        return ids.incrementAndGet();
    }
}
```

In `@WebMvcTest`, `OrderService` is replaced by `@MockitoBean`. In the real HTTP integration test, the real service runs without persistent business state requiring cleanup. The `sku/quantity/city` fields are passed to the service only after the request passes validation.

### 8.8. Controller: strict order creation and lenient preview

`src/main/java/example/jsondemo/OrderController.java`:

```java
package example.jsondemo;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    public record Created(long id) {
    }

    public record Preview(String sku, Integer quantity) {
    }

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

    @PostMapping(
        path = "/preview",
        consumes = MediaType.APPLICATION_JSON_VALUE)
    public Preview preview(
            @RequestBody LenientPreviewRequest request) {
        return new Preview(request.sku(), request.quantity());
    }
}
```

In `create`, `request.quantity()` unboxes safely to `int` **only when** `@NotNull` has been enforced. Removing `@Valid` lets a client omitting `quantity` cause a `NullPointerException` or wrong side effects; the missing-field test below catches that regression.

### 8.9. Error DTO

`src/main/java/example/jsondemo/ApiError.java`:

```java
package example.jsondemo;

import java.util.List;

public record ApiError(
        String code,
        List<Violation> errors
) {
    public record Violation(String field, String message) {
    }
}
```

Every error response has a stable code and clear field/message entries. Nothing includes raw JSON, rejected values, or exception stack traces.

### 8.10. `@RestControllerAdvice`

`src/main/java/example/jsondemo/ApiExceptionAdvice.java`:

```java
package example.jsondemo;

import java.util.Comparator;
import java.util.List;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiExceptionAdvice {

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> invalidJson(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest()
                .body(new ApiError(
                        "INVALID_JSON",
                        List.of(new ApiError.Violation(
                                "body",
                                "JSON body is invalid or missing"))));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> validationFailure(
            MethodArgumentNotValidException exception) {

        List<ApiError.Violation> errors =
                exception.getBindingResult().getFieldErrors()
                        .stream()
                        .map(e -> new ApiError.Violation(
                                e.getField(), e.getDefaultMessage()))
                        .sorted(Comparator
                                .comparing(ApiError.Violation::field)
                                .thenComparing(ApiError.Violation::message))
                        .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_ERROR", errors));
    }
}
```

**Why not return `exception.getMessage()`?** Jackson errors can reveal class names, property paths, or portions of payload values. Production APIs should return helpful yet safe messages; server-side logs should also mask secrets when content is sensitive.

**Intentional limitation:** the handler only collects `getFieldErrors()`. When adding class-level/cross-field constraints, also include `getGlobalErrors()` so clients can see errors not bound to a single property. The sample code only uses field constraints.

Do **not** add an `@ExceptionHandler(Exception.class)` returning HTTP 400, since 415/404/5xx and domain errors have different semantics. For Spring MVC built-in method validation directly on parameters, add a dedicated handler for `HandlerMethodValidationException` if the API uses that model.

## 9. MockMvc tests: proving all four input scenarios

The primary test uses `@WebMvcTest(OrderController.class)`: it boots the MVC slice with Jackson message converters and the validator, **without** starting a database or the real service. `@MockitoBean` registers a mock service in the Spring test context; `verifyNoInteractions(service)` proves invalid input is blocked **before business calls**.

File `src/test/java/example/jsondemo/OrderControllerTest.java`:

```java
package example.jsondemo;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(OrderController.class)
@ActiveProfiles("test")
class OrderControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockitoBean
    OrderService service;

    @Test
    void springBootMapperIsStrictBecauseTestProfileConfiguresIt() {
        assertTrue(mapper.isEnabled(
                DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES));
    }

    @Test
    void validInputIsDeserializedAndPassedToService()
            throws Exception {
        when(service.create("SKU-123", 2, "Da Nang"))
                .thenReturn(101L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "address":{"city":"Da Nang"}}
                        """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(101));

        verify(service).create("SKU-123", 2, "Da Nang");
    }

    @ParameterizedTest
    @ValueSource(ints = {1, 10})
    void validBoundaryQuantitiesAreAccepted(int quantity)
            throws Exception {
        when(service.create("SKU-123", quantity, "Hue"))
                .thenReturn(102L);

        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":%d,
                         "address":{"city":"Hue"}}
                        """.formatted(quantity)))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value(102));

        verify(service).create("SKU-123", quantity, "Hue");
    }

    @Test
    void missingQuantityBecomesValidationError()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123",
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"))
                .andExpect(jsonPath("$.errors[0].message")
                        .value("quantity is required"));

        verifyNoInteractions(service);
    }

    @Test
    void explicitNullQuantityAlsoFailsNotNull()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":null,
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @ParameterizedTest
    @ValueSource(ints = {0, 11})
    void outOfRangeQuantityFailsValidation(int quantity)
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":%d,
                         "address":{"city":"Hue"}}
                        """.formatted(quantity)))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("quantity"));

        verifyNoInteractions(service);
    }

    @Test
    void missingSkuFailsNotBlank() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"quantity":2,"address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"));

        verifyNoInteractions(service);
    }

    @Test
    void blankSkuFailsNotBlank() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"   ","quantity":2,
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("sku"));

        verifyNoInteractions(service);
    }

    @Test
    void missingAddressFailsNotNull() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address"));

        verifyNoInteractions(service);
    }

    @Test
    void missingCityIsFoundByNestedValidation()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,"address":{}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("VALIDATION_ERROR"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("address.city"));

        verifyNoInteractions(service);
    }

    @Test
    void nonNumericQuantityFailsDuringDeserialization()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":"many",
                         "address":{"city":"Hue"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"))
                .andExpect(jsonPath("$.errors[0].field")
                        .value("body"));

        verifyNoInteractions(service);
    }

    @Test
    void topLevelArrayIsNotAnOrderRecord()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        [{"sku":"SKU-123","quantity":2,
                          "address":{"city":"Hue"}}]
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void malformedJsonFailsBeforeValidation()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{not-json"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void emptyRequiredBodyReturns400() throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void extraTopLevelFieldIsRejectedByStrictMapper()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "address":{"city":"Hue"},
                         "isAdmin":true}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void extraNestedFieldIsAlsoRejected()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "address":{"city":"Hue","unknown":"x"}}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_JSON"));

        verifyNoInteractions(service);
    }

    @Test
    void lenientPreviewExplicitlyIgnoresExtraFields()
            throws Exception {
        mvc.perform(post("/api/orders/preview")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                        {"sku":"SKU-123","quantity":2,
                         "extra":"ignored"}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku")
                        .value("SKU-123"))
                .andExpect(jsonPath("$.quantity").value(2));

        verifyNoInteractions(service);
    }

    @Test
    void wrongContentTypeIs415NotValidation400()
            throws Exception {
        mvc.perform(post("/api/orders")
                    .contentType(MediaType.TEXT_PLAIN)
                    .content("""
                        {"sku":"SKU-123","quantity":2}
                        """))
                .andExpect(status().isUnsupportedMediaType());

        verifyNoInteractions(service);
    }
}
```

Test characteristics:

- `@WebMvcTest` uses real Spring MVC argument resolution/message converters, rather than instantiating the controller directly with `new`.
- `@ActiveProfiles("test")` activates the strict Jackson property; the first test asserts the mapper actually received this flag.
- Each invalid case asserts **HTTP 400 + matching error code + no service interactions**.
- Spring Framework 6.2's `@MockitoBean` for Boot 3.4+ replaces the older `@MockBean`; Spring test infrastructure resets mocks per standard lifecycle.
- Single-field errors can be asserted with `$.errors[0]`; if multiple fields fail simultaneously, do not assume ordering unless the error contract explicitly sorts them.
- `@JsonIgnoreProperties(ignoreUnknown=true)` on the preview DTO demonstrates local lenient policy while the strict endpoint still rejects unknown fields.
- `text/plain` hits media type handling and returns 415, not JSON parsing/validation 400.

## 10. Trying plain Jackson: ObjectMapper is not identical to Spring Boot's

Add a unit test to avoid the misconception "creating `new ObjectMapper()` gives the same mapper the application uses."

File `src/test/java/example/jsondemo/JacksonBasicsTest.java`:

```java
package example.jsondemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException;
import org.junit.jupiter.api.Test;

class JacksonBasicsTest {

    record SimpleInput(String sku, Integer quantity) {
    }

    @Test
    void missingNullableRecordMemberDeserializesAsNull()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        SimpleInput input = mapper.readValue(
                "{\"sku\":\"SKU-123\"}", SimpleInput.class);

        assertEquals("SKU-123", input.sku());
        assertNull(input.quantity());
    }

    @Test
    void directJacksonMapperRejectsUnknownByDefault() {
        ObjectMapper mapper = new ObjectMapper();

        assertThrows(UnrecognizedPropertyException.class, () ->
                mapper.readValue(
                        "{\"sku\":\"SKU-123\",\"quantity\":2,"
                                + "\"extra\":true}",
                        SimpleInput.class));
    }

    @Test
    void explicitLenientJacksonMapperCanIgnoreUnknown()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper()
                .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);

        SimpleInput input = mapper.readValue(
                "{\"sku\":\"SKU-123\",\"quantity\":2,"
                        + "\"extra\":true}",
                SimpleInput.class);

        assertEquals("SKU-123", input.sku());
        assertEquals(2, input.quantity());
    }

    @Test
    void explicitNullIsAlsoNullWithoutBeanValidation()
            throws Exception {
        ObjectMapper mapper = new ObjectMapper();

        SimpleInput input = mapper.readValue(
                "{\"sku\":\"SKU-123\",\"quantity\":null}",
                SimpleInput.class);

        assertNull(input.quantity());
    }
}
```

**These are 4 pure Jackson tests** without creating a Spring context. They directly test JSON syntax, record deserialization, and unknown-property handling under that mapper's configuration. Note that Jackson reading a DTO with null does not mean an HTTP controller using `@Valid` will accept it.

### Three different configuration places

| Context | How ObjectMapper is obtained | Default / sample unknown policy |
| --- | --- | --- |
| Pure unit | `new ObjectMapper()` | Jackson 2.x defaults `FAIL_ON_UNKNOWN_PROPERTIES=true` |
| Normal Spring Boot 3.5 | Boot-configured `ObjectMapper` | Boot disables `FAIL_ON_UNKNOWN_PROPERTIES` by default |
| Sample's Spring Boot test profile | Boot-configured `ObjectMapper` + strict property | `FAIL_ON_UNKNOWN_PROPERTIES=true` |
| Lenient type in sample | `@JsonIgnoreProperties(ignoreUnknown=true)` on DTO | Ignores unknown fields on that type even when mapper is strict |

Do not claim that **all** `ObjectMapper` instances in an application share the same flags: a project may create separate mappers, use custom `HttpMessageConverter`s, configure JSON differently for `RestClient`/`WebClient`, or instantiate an object mapper elsewhere. To verify real endpoints, prefer **MockMvc/HTTP integration tests** over Jackson unit tests alone.

## 11. Real HTTP tests: RANDOM_PORT and JSON requests over a socket

`@WebMvcTest` verifies MVC deserialization and error mapping in a mock Servlet request. If the requirement is "a client calling a real server with proper Content-Type/HTTP headers," add a small `@SpringBootTest(RANDOM_PORT)` group.

File `src/test/java/example/jsondemo/RealHttpJsonIntegrationTest.java`:

```java
package example.jsondemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@ActiveProfiles("test")
class RealHttpJsonIntegrationTest {

    @LocalServerPort
    int port;

    @Autowired
    ObjectMapper mapper;

    private HttpResponse<String> post(String body) throws Exception {
        URI uri = URI.create(
                "http://127.0.0.1:" + port + "/api/orders");

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body))
                .build();

        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(3))
                .build();

        return client.send(
                request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void validPayloadReturns201OverRealHttp()
            throws Exception {
        assertTrue(port > 0);

        HttpResponse<String> response = post("""
            {"sku":"SKU-123","quantity":2,
             "address":{"city":"Hue"}}
            """);

        assertEquals(201, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertTrue(body.path("id").asLong() > 0);
    }

    @Test
    void strictUnknownPayloadReturns400OverRealHttp()
            throws Exception {
        HttpResponse<String> response = post("""
            {"sku":"SKU-123","quantity":2,
             "address":{"city":"Hue"},
             "isAdmin":true}
            """);

        assertEquals(400, response.statusCode());
        JsonNode body = mapper.readTree(response.body());
        assertEquals("INVALID_JSON",
                body.path("code").asText());
    }
}
```

JDK 17 `HttpClient` requires no extra HTTP test client library. `@LocalServerPort` retrieves the actual port of the embedded server; do not hard-code `localhost:8080`. The test profile enables the strict Jackson policy. The real service uses in-memory IDs, so no database teardown is needed in the demo. In applications with persistence, the HTTP client and server typically run in different transactions; `@Transactional` on the client test **does not roll back** changes committed by the server.

These two checks confirm full HTTP transport to the booted server, though they do not prove HTTPS, gateways, schema migrations, or production DBs. Those layers need dedicated infrastructure/integration tests when contracted.

## 12. Running the code and expected outcomes

Requires JDK 17+, Maven, and connectivity to download Maven dependencies on the first run. From the directory with `pom.xml`:

```bash
mvn test
```

Or run each group:

```bash
mvn test -Dtest=OrderControllerTest
mvn test -Dtest=JacksonBasicsTest
mvn test -Dtest=RealHttpJsonIntegrationTest
```

**Expected results:**

| Group | Method declarations | Test invocations | Evidence |
| --- | ---: | ---: | --- |
| `OrderControllerTest` | 18 (including 2 parameterized) | 20 | MVC binding + validation + unknown policy + service interactions |
| `JacksonBasicsTest` | 4 | 4 | Plain Jackson missing/null/strict/lenient |
| `RealHttpJsonIntegrationTest` | 2 | 2 | Real server returning 201/400 for JSON |
| **Total** | **24** | **26** | No DB/Docker required |

These numbers account for `@ParameterizedTest` on min/max and out-of-range, each method having two inputs. With matching dependencies/versions, **26 test invocations are expected to PASS, with 0 failures/errors/skips**. This is the expected behavior from the example code; to confirm in practice, run Maven and inspect `target/surefire-reports`. There is no `System.out.println` in the code, so there is no fixed application stdout beyond Maven/Spring logs.

Representative scenarios:

| Input | Expected HTTP | API code/response | Is the service called? |
| --- | --- | --- | --- |
| Valid JSON | 201 | `{"id":101}` in MVC mock, ID > 0 over real HTTP | Yes |
| Missing `quantity` | 400 | `VALIDATION_ERROR`, field `quantity` | No |
| `quantity:null` | 400 | `VALIDATION_ERROR`, field `quantity` | No |
| `quantity:0` / `11` | 400 | `VALIDATION_ERROR` | No |
| Missing/blank `sku` | 400 | `VALIDATION_ERROR`, field `sku` | No |
| Missing `address` | 400 | `VALIDATION_ERROR`, field `address` | No |
| Missing `address.city` | 400 | `VALIDATION_ERROR`, field `address.city` | No |
| `quantity:"many"` | 400 | `INVALID_JSON` | No |
| Malformed JSON syntax | 400 | `INVALID_JSON` | No |
| Root is a JSON array | 400 | `INVALID_JSON` | No |
| Empty body | 400 | `INVALID_JSON` | No |
| Top-level unknown `isAdmin` | 400 | `INVALID_JSON` under strict test policy | No |
| Nested unknown in address | 400 | `INVALID_JSON` under strict policy | No |
| Lenient preview with `extra` | 200 | Preview with known fields only | No |
| `Content-Type: text/plain` | 415 | Spring media type error | No |

If the strict policy is removed from the test profile, the unknown-property cases **must fail** because 400 is no longer returned. If `@Valid` is removed, missing/null/invalid constraint cases **must fail** because requests can slip into the controller; those are the regressions this suite can detect.

## 13. Deeper dive: when does a missing field fail immediately in Jackson?

In the sample, a missing `Integer quantity` produces `null` and `@NotNull` returns a validation error. However, some schemas use required Jackson creator properties:

- `@JsonCreator` selects the constructor/static factory Jackson invokes.
- `@JsonProperty(value="id", required=true)` on a creator parameter requires the property to be present per Jackson creator semantics.
- `FAIL_ON_MISSING_CREATOR_PROPERTIES` can force Jackson to fail when creator inputs are absent.
- `FAIL_ON_NULL_CREATOR_PROPERTIES` can force failure for null creator properties.
- `@JsonSetter(nulls=Nulls.FAIL)` can set null policy per property/deserializer as appropriate.

When these are enabled, the **exact same missing-field JSON** shifts from `MethodArgumentNotValidException` to `HttpMessageNotReadableException`. That is not necessarily a bug; it is a difference in configuration layer. The API contract should keep HTTP 400 stable and test the appropriate cause/response code.

Do not apply these creator flags system-wide without evaluating backward compatibility for DTOs and legacy clients. A DTO with default property handling in business logic does not necessarily need to fail when JSON omits a field.

### Missing optional fields

For genuinely optional fields, you can use:

```java
public record SearchFilter(
        String keyword,
        Integer pageSize,
        Boolean includeInactive) {
}
```

When a property is absent, Java wrappers receive null; the service/controller **must** intentionally apply defaults/normalization before use. Avoid unboxing a null `Boolean includeInactive`, and avoid silently "defaulting to 0" when the request contract demands ≥1. Every business-meaningful default must be documented and tested separately for missing, null, and explicit values.

## 14. Unknown but syntactically valid JSON fields: where should strictness live?

Three common policy layers:

1. **Global ObjectMapper strictness:** configure `spring.jackson.deserialization.fail-on-unknown-properties=true`. All DTOs using that mapper are affected.
2. **Per-type leniency:** `@JsonIgnoreProperties(ignoreUnknown=true)` for extensible contract types. Only annotated DTOs get the exception.
3. **Endpoint-specific mapper/deserializer:** custom `HttpMessageConverter`, `ObjectReader`, or custom deserializer when special formats are required—more complex, so use only with clear justification.

An important caveat: placing `@JsonIgnoreProperties(ignoreUnknown = false)` on a type **does not by itself guarantee** strictness if the global `ObjectMapper` allows unknowns, because `false` merely means "this annotation does not ask to ignore unknowns"; the deserializer still follows the global feature flag and other handlers. To enforce strictness, configure the actual mapper in use or add explicit known-key validation.

If you need JSON extensibility **without losing data**, use `@JsonAnySetter` to capture unknown keys into a controlled map, then decide whether to store or reject them. Only ignore unknown fields when ignoring them is part of the API contract.

### Property names, naming strategies, and aliases

`@JsonProperty("order_id")` maps JSON `order_id` to Java `orderId`. `spring.jackson.property-naming-strategy=SNAKE_CASE` changes the mapper's naming strategy. `@JsonAlias("oldName")` permits legacy names during **deserialization**, without causing responses to serialize the alias.

If an API enforces strict unknown properties and a client sends `orderID` instead of `orderId`, the mistyped key can trigger both an unknown-property error **and** a missing target field. Test exact JSON property names and migration aliases when evolving contracts.

## 15. Common exceptions and vulnerabilities when deserializing JSON

### Primitive defaults and business rules

If you write:

```java
public record UnsafeInput(int quantity) {}
```

under Jackson 2's default `FAIL_ON_NULL_FOR_PRIMITIVES=false`, missing or null can be interpreted as 0. If `quantity` is a required field, use a wrapper with `@NotNull` or enable appropriate strict null handling. **Never** let 0 be mistaken for a user intentionally choosing 0 when the request actually omitted the property.

### Converting strings into numbers

`"quantity":"2"` can pass via implicit coercion. If the API demands JSON numbers as **native numeric tokens**, configure Jackson coercion for the target type and test directly; `@Min` only validates the resulting Java value after conversion, not whether the original JSON token was a String or Number.

### Duplicate keys

JSON such as:

```json
{"quantity":1,"quantity":100}
```

is not trustworthy business input; many parsers/mappers accept it and pick the last value or behave differently depending on configuration. If the contract requires rejecting duplicate keys, enable duplicate detection on the parser—such as `JsonParser.Feature.STRICT_DUPLICATE_DETECTION` in Jackson 2.x—and test with the real converter. `FAIL_ON_READING_DUP_TREE_KEY` only applies to certain tree-reading paths and **does not** replace general duplicate detection during direct POJO binding.

### Trailing tokens

A valid JSON object followed by trailing data:

```text
{"sku":"SKU-123"} {"other":"payload"}
```

requires a "single document only" policy. Jackson's `FAIL_ON_TRAILING_TOKENS` can reject tokens beyond the root JSON value; default behavior may vary depending on how the reader/converter is invoked. If this belongs in your threat model, test via real HTTP requests rather than just `ObjectMapper.readTree` on a single object.

### Polymorphic typing and unsafe deserialization

Do not enable Jackson **default typing** for untrusted data without thoroughly understanding type validation/allowlists. For external JSON, avoid letting clients specify arbitrary Java class names in type metadata. Only use polymorphic JSON with an explicit schema, subtype allowlist, and versioning; never deserialize untrusted input into an arbitrary internal object graph.

### Over-posting risk

In write APIs, never deserialize directly into a JPA entity containing role/admin fields or store arbitrary unknown properties unchecked. An allowlisted DTO with only publicly editable fields, domain authorization, and service-level invariants remain mandatory even when Jackson is strict.

### Size and depth limits

Bean Validation does not stop a huge JSON payload or thousands of nested objects from exhausting memory before validation runs. Configure request body size limits at the server/gateway, Jackson stream read constraints appropriate to your version, maximum item counts, and schema constraints like `@Size(max=...)`. Separate input validation tests from body-size/depth load and security tests.

## 16. Comparing MockMvc, ObjectMapper unit tests, and HTTP integration

| Criterion | Pure ObjectMapper | `@WebMvcTest` + MockMvc | `@SpringBootTest(RANDOM_PORT)` |
| --- | --- | --- | --- |
| Spring context? | No | MVC slice | Full Boot context |
| Tests Boot's Jackson config? | No, if `new ObjectMapper()` | Yes, per test slice context | Yes, per full app context |
| Reads `@RequestBody` via MVC converter? | No | Yes | Yes |
| Runs `@Valid` and exception advice? | No, unless manually wired | Yes | Yes |
| Real HTTP socket? | No | No | Yes |
| Needs a test port? | No | No | `@LocalServerPort` |
| Speed | Fastest | Usually fast | Slower due to full startup/server |
| Use when | Verifying standalone mapper behavior | API input mapping + status/error contract | End-to-end HTTP smoke with real wiring |

Do not place `@SpringBootTest` and `@WebMvcTest` on the same class because they select different bootstrappers. If you want full-context + mock HTTP requests, use `@SpringBootTest` + `@AutoConfigureMockMvc`. Pick the smallest layer that still proves the goal.

## 17. Diagnosing failed deserialization tests

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Wrong JSON type yet server returns 500 | Advice does not handle `HttpMessageNotReadableException`, or exception is swallowed/status overridden | Check resolved exception; map parse errors to 400 |
| JSON missing `quantity` yet returns 201 | Missing `@Valid` or `@NotNull`, or primitive default used | Check controller annotations and DTO constraints |
| `@NotNull` does not run | Missing validation provider or test calls controller directly | Add starter validation; use MockMvc |
| Unexpected field still returns 201 | Boot-configured mapper ignores unknowns | Enable strict property if API contract requires it |
| Unexpected field fails in unit test yet HTTP accepts it | `new ObjectMapper()` and Boot mapper have different defaults | Test directly with the Spring-injected mapper |
| `"2"` accepted despite wanting numeric token | Jackson coercion is enabled | Configure strict coercion; test the policy |
| Record DTO fails to deserialize | Jackson version/constructor annotations/creator config/naming mismatch | Align Boot BOM; inspect record mapping |
| JSON field missing after rename | `@JsonProperty`/naming strategy/`@JsonAlias` incompatible | Test actual wire key names |
| Nested `city` is not validated | Missing `@Valid` on nested field | Add `@Valid` + `@NotNull` if field is mandatory |
| Client sends null yet test only covers missing | Cases may differ under strict creator/null policies | Separate assertions for missing and null |
| `@WebMvcTest` fails missing `OrderService` | Slice intentionally omits regular services | `@MockitoBean` or import suitable test bean |
| JSON request body fails with 415 | `Content-Type` does not match `consumes` | Send `application/json`; distinguish from 400 |
| Multiple violations change order | Validator does not guarantee natural ordering | Assert field set or sort in the API contract |
| Unknown nested fields not rejected | Field type has `@JsonIgnoreProperties` or custom deserializer | Inspect DTO tree and mapper policy |
| Test passes alone, fails in suite | Different contexts/profiles, shared mutable config/mocks | Use explicit test profile and avoid global mapper mutation |
| API leaks payload data on error | Returning raw exceptions or rejected values | Safe generic response; redacted details in server logs |
| Boot 4 fails with old Jackson imports | Jackson 3/test modules differ from Boot 3 | Check BOM and API docs for your version |

### Sequence for debugging

1. Confirm the request has `Content-Type: application/json`, the right method/path, and an actual body.
2. Check the root-cause exception if MVC returns 400: parse/token mismatch or validation?
3. Inspect DTO types and naming: are `@JsonProperty`/aliases/global naming strategies active?
4. Verify the **actual** mapper via `@Autowired ObjectMapper` and its feature flags in the test.
5. Check `@Valid`, starter validation, constraints, and nested cascades.
6. Verify `@RestControllerAdvice` is discovered by component scan/test slice.
7. Assert status + code + field + `verifyNoInteractions` to confirm invalid input was blocked.
8. When differences only happen over real HTTP, add a `RANDOM_PORT` test with client-like body/headers.
9. Never fix failures by disabling validation or using a broad `catch(Exception)` returning 200/a default object.
10. Run the entire suite and inspect `target/surefire-reports` to spot filtered or skipped tests.

## 18. Architecture and versions: Spring Boot 3.5 to 4

**The complete codebase targets Spring Boot 3.5.0, Spring Framework 6.2, and Jackson 2.x.** When upgrading to Spring Boot 4:

- Spring Boot 4 uses Spring Framework 7 and targets Jackson 3; Jackson API packages, defaults, and converter configuration must be cross-checked against official docs.
- Boot 4's test infrastructure is modularized by technology, with focused test starters like `spring-boot-starter-webmvc-test` and `@WebMvcTest` moved to updated packages.
- Spring Framework's `@MockitoBean` continues as the replacement for legacy `@MockBean`.
- Do not copy `com.fasterxml.jackson.databind.ObjectMapper` from Jackson 2 directly to Jackson 3 without checking migration rules.
- The principles **missing ≠ null ≠ invalid shape**, strict unknown policies, and Bean Validation remain core API contract concerns; verify behavior via HTTP tests on the target stack.

Unless a major upgrade is required in the lab, use the exact dependencies/imports from sections 8–11. Align versions via the Spring Boot BOM/parent instead of mixing arbitrary Jackson, Hibernate Validator, and JUnit versions.

## 19. Acceptance checklist

- [ ] Distinguished Jackson deserialization from Jakarta Bean Validation?
- [ ] Request DTO contains only API-permitted fields, without binding sensitive entities directly?
- [ ] `@RequestBody` and `@Valid` placed on the right controller argument?
- [ ] `spring-boot-starter-validation` or a compatible provider present?
- [ ] Valid-input test confirms HTTP 201, exact JSON response, and service called with exact arguments?
- [ ] Missing-property and explicit-null tests are two separate cases?
- [ ] Required numeric fields use wrapper `Integer`/`Long` + `@NotNull` when needed?
- [ ] Numbers tested at lower/upper boundaries and just outside boundaries?
- [ ] Non-convertible input such as `"quantity":"many"` tested?
- [ ] Malformed JSON, wrong root shape, and empty body tested?
- [ ] Aware that `"2"`/`2.5` coercion can depend on config, avoiding false assumptions?
- [ ] Strict/lenient unknown-property policy explicitly chosen?
- [ ] If strict, `ObjectMapper` config verified inside the Spring test context?
- [ ] If lenient, only DTOs that truly allow unknown fields are annotated?
- [ ] Both top-level and nested unknown properties tested?
- [ ] Error responses have stable status/code/fields without raw payloads or stack traces?
- [ ] Tested `text/plain` receiving 415, not confused with validation 400?
- [ ] MockMvc invalid cases verify the service was not called?
- [ ] Tests do not depend on ordering of multiple `FieldError`s unless contracted?
- [ ] At least one real HTTP test included if the contract requires testing real sockets/servers?
- [ ] Tests do not confuse a direct `new ObjectMapper()` with Spring Boot's configured mapper?
- [ ] CI reports actual executed/failed/skipped test counts, not just build status?
- [ ] When upgrading Boot/Jackson major versions, checked test starters, imports, defaults, and contracts?

## 20. Official documentation and reference sources

1. [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): `HttpMessageConverter`, `@Valid`, `MethodArgumentNotValidException`, and `BindingResult`.
2. [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): argument resolver and method-level validation.
3. [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/): `spring.jackson.deserialization.*` and Jackson settings.
4. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@MockitoBean`, `@SpringBootTest`.
5. [Jackson 2.19 DeserializationFeature API](https://javadoc.io/static/com.fasterxml.jackson.core/jackson-databind/2.19.0/com/fasterxml/jackson/databind/DeserializationFeature.html): default flags, coercion, and failure handling.
6. [Jackson — Deserialization Features](https://github.com/FasterXML/jackson-databind/wiki/Deserialization-Features): `FAIL_ON_UNKNOWN_PROPERTIES`, null primitives, creator features.
7. [Jackson — @JsonIgnoreProperties](https://github.com/FasterXML/jackson-annotations/wiki/Jackson-Annotations): ignored/unknown JSON fields.
8. [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/): `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Valid`.
9. [OWASP — Mass Assignment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html): DTO allowlisting, avoiding binding internal/security fields.
10. [Spring Boot Reference — JSON](https://docs.spring.io/spring-boot/reference/features/json.html): cross-checking ObjectMapper/Jackson integration across Boot versions.

**Conclusion:** successful deserialization **does not prove a request is valid**. Missing fields can become `null`; wrong types can fail in Jackson or get coerced; extra fields are accepted or rejected depending on `ObjectMapper`/DTO policy. A reliable API must explicitly define these four scenarios, test the responses, and ensure invalid input **never reaches business services**.
