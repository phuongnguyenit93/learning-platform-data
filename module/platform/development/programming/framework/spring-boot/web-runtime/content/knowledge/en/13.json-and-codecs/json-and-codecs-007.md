# Handling Unknown Fields, Invalid Enums, and Nested Data in Spring Boot JSON

## 1. Lesson Objectives

An HTTP API frequently receives JSON from browsers, mobile apps, partner systems, or message gateways. Syntactically valid JSON can still be **invalid under the data contract**: a client sends an undefined field, passes a non-existent enum value, leaves a nested object blank, or sends an array containing invalid elements. In Spring Boot, Jackson and HTTP codecs convert JSON into Java objects; validation and error handling must continue checking data semantics before invoking business logic.

This lesson focuses on three scenarios:

1. **Unknown properties:** JSON contains a key that does not map to a DTO property—for example, sending `"isAdmin":true` in a registration request that only has `email` and `name`.
2. **Invalid enums:** JSON sends a string not belonging to the enum, or sends a number that Jackson maps by declaration ordinal unless configured strictly.
3. **Nested data:** nested objects, lists, nulls, missing fields, and invalid list elements; deserializing properly and validating across the structure.

By the end of this lesson, you should be able to:

- Distinguish JSON syntax errors, deserialization errors, Bean Validation errors, and business errors.
- Choose strict/lenient mode for unknown fields; understand the effects of `FAIL_ON_UNKNOWN_PROPERTIES`, `@JsonIgnoreProperties`, and `@JsonAlias`.
- Recognize enum strings, numeric ordinals, casing, null, `@JsonEnumDefaultValue`, and backward-compatibility options.
- Use Java 17 record DTOs with `@NotBlank`, `@NotNull`, `@Min`, `@NotEmpty`, and `@Valid` for nested objects and lists.
- Turn input errors into clear HTTP 400 responses without leaking stack traces or sensitive data.
- Write a Spring Boot 3.3.x example using WebFlux.fn and `WebTestClient`, while understanding differences from Spring MVC.
- Design regression tests for both valid and invalid cases across every JSON layer.

**Version scope:** Specific configurations and Jackson code in this lesson use **Spring Boot 3.3.x + Jackson 2 + Java 17+**. Spring Boot 4.0 makes Jackson 3 the default, changing packages and several property/configuration APIs. Do not copy Jackson 2 configurations directly into Boot 4 without checking the migration guide.

## 2. How Does JSON Enter the Application?

With an HTTP request:

~~~http
POST /api/orders HTTP/1.1
Host: localhost:8080
Content-Type: application/json
Accept: application/json

{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

Typical steps in Spring Boot:

~~~text
HTTP request body
    |
    v
Web runtime (Tomcat/Jetty/Reactor Netty)
    |
    v
Spring MVC HttpMessageConverter
  or Spring WebFlux HttpMessageReader / Jackson2JsonDecoder
    |
    v
Jackson parse + data binding
    |
    +-- JSON syntax error? -> body read error
    +-- unknown property in strict mode? -> mapping error
    +-- unrecognized enum? -> mapping error
    |
    v
CreateOrderRequest and nested records
    |
    v
Bean Validation or custom validation
    |
    +-- missing required? -> 400 validation
    +-- quantity <= 0? -> 400 validation
    |
    v
Application service / domain
    |
    v
HTTP status + response DTO + JSON encoder
~~~

Jackson is a tool that converts JSON into Java objects; it does not replace all business rules. For example, JSON with `quantity = 0` can still be converted by Jackson into `Integer` 0; validation must reject it. Conversely, an enum value `"TURBO"` absent from the enum can fail **before the DTO is constructed**, so Bean Validation is never called.

In WebFlux.fn, `ServerRequest.bodyToMono(CreateOrderRequest.class)` reads the body via codecs. In Spring MVC, `@RequestBody` uses `HttpMessageConverter`. Error mechanisms and exception types differ, but JSON contract, DTO, and Jackson principles remain closely aligned.

## 3. Four Error Layers That Must Not Be Equated

| Layer | Example | Detected By | Typical Suitable HTTP |
| --- | --- | --- | --- |
| JSON syntax | Missing brace or quote | JSON parser | 400 |
| JSON mapping | Unknown field in strict mode, enum `"TURBO"`, object instead of string | Jackson deserializer | 400 |
| DTO validation | Blank `shipping.city`, `lines[0].quantity = 0` | Jakarta Bean Validation | 400 |
| Business rules | Unknown SKU, duplicate order, or out of stock | Domain/service | 400/404/409/422 per API contract |

A Jackson stack trace can contain field paths and error locations; this information is useful for internal logs, not for returning verbatim to clients. Standardize responses with an error code, safe message, and valid field list when needed.

Other statuses are also important:

- 415 Unsupported Media Type: `Content-Type` has no matching decoder, e.g., sending `text/plain` to an endpoint accepting only JSON.
- 413 Payload Too Large: HTTP body exceeds configured limits.
- 401/403: authentication/authorization issues; must not be masked as JSON errors.
- 500: real programming or dependency errors; do not catch everything and turn it into 400.

## 4. What Is an Unknown Field?

Suppose the DTO only defines:

~~~java
public record UserRequest(String name, String email) {
}
~~~

Client sends:

~~~json
{
  "name": "Lan",
  "email": "lan@example.test",
  "isAdmin": true
}
~~~

The key `isAdmin` **has no matching property** in `UserRequest`. This is an unknown JSON field. It differs from a field that exists and carries `null` or a wrong type.

When mapping into a static DTO, Jackson can behave in three ways:

- **Strict:** reject unknown keys with `UnrecognizedPropertyException` or a mapping error wrapped in an HTTP exception.
- **Lenient:** ignore unknown keys and construct the DTO from recognized fields.
- **Custom handling:** a `@JsonAnySetter`, deserializer, or specialized handler records unknown keys by design.

You cannot assume all unknown fields are rejected solely by using records. Check mapper configuration, annotations, mixins, and deserializer mechanics.

### 4.1. Jackson 2 Default vs. Spring Boot 3

A plain Jackson 2 `ObjectMapper` normally enables `FAIL_ON_UNKNOWN_PROPERTIES`; Spring Boot 3.x uses a more lenient default and disables failing on unknown properties on the Boot auto-configured mapper. This frequently causes confusion when moving from unit tests using `new ObjectMapper()` to a real Spring Boot app.

Do not verify strict mode by creating an arbitrary `new ObjectMapper()` and assuming it matches the HTTP codec's `ObjectMapper`. Inspect the mapper/configuration actually used by the web application, and run HTTP integration tests.

### 4.2. When Should You Be Strict?

Strict mode fits when:

- The API performs critical write commands: payments, permissions, status updates, administration.
- Misnamed fields could cause the system to silently ignore client intent.
- Contracts are published with OpenAPI/JSON Schema and clients should catch mistakes early.
- You want to catch typos like `delivaryMethod` instead of ignoring them.
- Inbound data requires tight schema change control.

For example, a partner sends `shipping.adress` instead of `shipping.address`. In lenient mode, the misspelled field may be silently dropped to null, causing deeper errors if validation is incomplete. Strict mode surfaces the error early at the API boundary.

### 4.3. When Can You Be Lenient?

Lenient mode can be useful for:

- Client/server rolling upgrades where newer versions add fields harmless to older versions.
- Event schemas designed for consumers to ignore extra attributes.
- External data read/import endpoints with dedicated preservation/extraction policies.
- Legacy DTOs temporarily supported during a tested migration window.

**Not equivalent to security:** ignoring unknown fields prevents clients from binding directly to undeclared fields, yet it does not replace separate input DTOs, server-side authorization, and mass-assignment protection.

## 5. Configuring Strict Unknown Fields in Spring Boot 3.3

An explicit configuration for Boot 3.x's default mapper is:

~~~yaml
spring:
  jackson:
    deserialization:
      fail-on-unknown-properties: true
      fail-on-numbers-for-enums: true
~~~

These two flags are independent:

- `FAIL_ON_UNKNOWN_PROPERTIES`: errors when a field is not handled by the DTO/deserializer.
- `FAIL_ON_NUMBERS_FOR_ENUMS`: rejects JSON integer numbers as enum ordinals.

Example in `.properties`:

~~~properties
spring.jackson.deserialization.fail-on-unknown-properties=true
spring.jackson.deserialization.fail-on-numbers-for-enums=true
~~~

This is **Jackson 2 / Spring Boot 3.x** configuration. When enabled globally, existing DTOs are also affected. Run regression tests before deploying, since older clients sending extra fields may start receiving HTTP 400.

You can configure it via Java if centralized programmatic control is needed:

~~~java
@Bean
Jackson2ObjectMapperBuilderCustomizer strictJson() {
    return builder -> builder.featuresToEnable(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS
    );
}
~~~

This snippet requires importing `Jackson2ObjectMapperBuilderCustomizer` from `org.springframework.boot.autoconfigure.jackson` and `DeserializationFeature` from `com.fasterxml.jackson.databind`. Place it inside an appropriate Boot 3.x `@Configuration`. In the complete project below, only `application.yml` is used to avoid duplicate configuration.

**Important note:** If a project creates its own `ObjectMapper`, `Jackson2JsonDecoder`, or custom codecs, `spring.jackson.*` properties may not reach the mapper used by endpoints. Never claim strict mode is enabled just from reading YAML; test real HTTP requests. In Spring Boot 4/Jackson 3, mapper types and property names have changed.

## 6. Per-DTO Exception: @JsonIgnoreProperties

Sometimes a system wants strict defaults, yet one legacy integration DTO can receive new fields from a partner. In Jackson 2, you can annotate:

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record PartnerEvent(
        String externalId,
        String type
) {
}
~~~

This type-level annotation instructs Jackson to ignore unmapped JSON properties for `PartnerEvent`, even when the global policy is stricter. This is an **intentional exception** and should not be applied broadly to every write DTO.

Another option is controlled renaming/aliases:

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;

public record RenameRequest(
        @JsonAlias("customer_id") String customerId
) {
}
~~~

When reading JSON, `customer_id` is accepted as an alias for `customerId`. `@JsonAlias` primarily aids deserialization and does not force serialization to emit the alias name; JSON output follows the primary property name unless configured otherwise.

**Which should you choose?**

- Client sends unsupported typo: strict 400.
- Legacy client sends old field name during an active migration window: explicit `@JsonAlias`.
- Partner sends non-essential extension metadata ignored by consumer: scoped `@JsonIgnoreProperties(ignoreUnknown=true)`.
- Need to store extra fields: design a dedicated `Map`/`JsonNode` with explicit validation, storage, quotas, and permissions instead of passing arbitrary extras straight to entities.

## 7. Unknown Fields Across Nested Levels

Unknown properties do not only appear on the root object. For example:

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000",
    "gps": "21.0,105.8"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

If a strict mapper deserializes `shipping` into an `Address` record lacking `gps`, mapping fails at path `shipping.gps`. Placing `@JsonIgnoreProperties(ignoreUnknown=true)` on **Address** only ignores unknown fields on `Address`. Do not assume an annotation on the root DTO automatically cascades to ignore unknown fields on every nested class; check each level's class and type.

With `Map<String,Object>`, `JsonNode`, or raw JSON trees, arbitrary keys are part of the map/tree data, so the same concept of "unknown Java property" as static DTO binding does not apply. If you need schema validation for maps/trees, use JSON Schema, a custom validator, or explicit business checks.

Never pass an unrestricted object tree straight into an ORM entity and expect unknown-field strictness to provide safety. Size, depth, key count limits, and allowed operations must be explicitly designed.

## 8. Invalid Enums: Cases to Distinguish

Given an enum:

~~~java
public enum DeliveryMethod {
    STANDARD,
    EXPRESS
}
~~~

JSON values:

| JSON | Expected Behavior in Strict Mode | Explanation |
| --- | --- | --- |
| `"STANDARD"` | Valid | Exact enum name |
| `"EXPRESS"` | Valid | Exact enum name |
| `"SAME_DAY"` | Deserialization error | Not in enum |
| `"express"` | Usually errors | Jackson 2 is case-sensitive by default |
| `1` | Errors if `FAIL_ON_NUMBERS_FOR_ENUMS=true` | Otherwise Jackson 2 can map by ordinal |
| `null` | Can deserialize to null | Needs `@NotNull` to reject |
| Missing key | Can become null in DTO record | Needs `@NotNull` or required creator policy |
| `{}` | Invalid for standard enums | JSON object differs from enum string |

A critical pitfall is **numeric ordinal coercion**. If an enum has `STANDARD`(ordinal=0), `EXPRESS`(ordinal=1), a JSON number `1` can become `EXPRESS` in Jackson 2 when not forbidden. Adding, removing, or reordering enum constants changes numeric meanings, so never build public APIs around ordinals.

**Recommended contract:** accept and emit enums as stable named strings, validate exact names, and reject ordinals. If a public API needs names differing from enum constants, use `@JsonValue`/`@JsonCreator` or tested conversion DTOs.

## 9. Choosing a Policy for Unknown Enum Values

There are three common strategies with completely different semantics:

### 9.1. Reject: Appropriate for Critical Commands

Keep Jackson 2's default string enum behavior: unknown strings cause mapping errors; combine with `FAIL_ON_NUMBERS_FOR_ENUMS=true` and Bean Validation `@NotNull`. Use this for order creation, payments, permissions, and non-guessable states.

For example, `deliveryMethod="DRONE"` is rejected rather than defaulting to `STANDARD`, because choosing an invalid delivery method is a domain error.

### 9.2. Coerce to Null: Risk of Losing Information

Jackson 2 provides:

~~~java
DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_AS_NULL
~~~

When enabled, an unknown enum string becomes `null`. Do not use this flag as a general "fix": if the field is optional, callers may never know a value was silently discarded; in enum collections, null can break `EnumSet`/`EnumMap`. If used, define clear null semantics and validation.

### 9.3. Map to an UNKNOWN Constant with @JsonEnumDefaultValue

Jackson 2 supports:

~~~java
import com.fasterxml.jackson.annotation.JsonEnumDefaultValue;

public enum ExternalEventType {
    CREATED,
    UPDATED,
    @JsonEnumDefaultValue UNKNOWN
}
~~~

To enable the fallback:

~~~java
mapper.enable(
        DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE);
~~~

The mapper snippet is illustrative; it must target the `ObjectMapper` actually used to deserialize. Without `@JsonEnumDefaultValue`, enabling the feature alone does not create a default constant. This mechanism suits **event/read models needing forward compatibility**, not commands with real side effects by default.

Decide how `UNKNOWN` is handled: preserve the raw value in separate metadata, skip safely, alert monitoring, or route to a dead-letter flow; never trigger business actions with an `UNKNOWN` status. When both `UNKNOWN` fallback and `AS_NULL` are enabled, Jackson 2 prioritizes the default enum feature if present.

## 10. Renamed Enums, Aliases, and API Compatibility

Renaming an enum constant from `STANDARD` to `ECONOMY` can break older clients sending `STANDARD` even though Java compiles cleanly. Treat enums as **versioned API contracts**.

Options:

- Keep the old wire value and rename only internally via explicit mapping.
- Define API DTOs with stable strings/enums and map to domain enums in the service.
- Read multiple aliases using a custom `@JsonCreator` and serialize one primary name with `@JsonValue`.
- Maintain a deprecation window, backward-compatibility tests, and usage metrics.
- Use `UNKNOWN` fallback only for consumers with a defined policy for unrecognized values.

Example enum reading public values via creator (standalone snippet):

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum ApiDelivery {
    STANDARD("standard"),
    EXPRESS("express");

    private final String code;

    ApiDelivery(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static ApiDelivery fromJson(String raw) {
        for (ApiDelivery value : values()) {
            if (value.code.equals(raw)) {
                return value;
            }
        }
        throw new IllegalArgumentException("Unsupported delivery method");
    }
}
~~~

The code requires Java 17+ and compiles without Spring if Jackson annotations are on the classpath. The JSON contract is `"standard"`/`"express"`, decoupled from `enum.name()`. Test numbers, nulls, casing, and exception wrapping; if you strictly want to forbid numeric coercion, keep matching strict settings and verify actual creator behavior.

## 11. Nested Data: Three Layers to Handle

Suppose an order creation request contains:

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2},
    {"sku": "BOOK-02", "quantity": 1}
  ]
}
~~~

Three data layers:

1. **Root object:** `customerId` and `deliveryMethod`.
2. **Nested object:** `shipping` with `recipient`/`city`/`postalCode`.
3. **Nested collection:** `lines` as `List<OrderLine>`; each element has `sku`/`quantity`.

The JSON decoder can build all records when names and types match. However, consider these failure cases separately:

- `shipping` completely missing -> typically binds to `null` without a strict creator policy.
- `shipping` is a string instead of an object -> mapping error.
- `shipping.city` is `""` -> mapping succeeds; `@NotBlank` validation rejects it.
- `lines` is `[]` -> mapping produces an empty list; `@NotEmpty` rejects it.
- `lines` has a null element -> requires `@NotNull` on the element type.
- `lines[0].quantity` is `0` -> `@Min(1)` rejects it.
- `lines[0].quantity` is missing -> use `Integer` + `@NotNull` to detect it, rather than primitive `int` defaulting to `0` and obscuring the error source.
- JSON has an unknown field in `lines[0]` -> strict unknown property checks apply at `OrderLine`.

**Do not conflate Java null with JSON missing:** a missing field and a field explicitly set to null can both yield Java `null` when Jackson instantiates the object. If the contract must distinguish those two states, use creator presence mechanisms, `JsonNode`, or DTOs with presence tracking; Bean Validation `@NotNull` only guarantees a non-null value post-binding without distinguishing the source.

## 12. Bean Validation Across Nested Objects and Lists

Jakarta Bean Validation in Spring Boot 3.x uses the `jakarta.validation.*` package. For nested DTOs, nested constraints only execute when **cascaded validation** is enabled at the right places:

~~~java
public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull DeliveryMethod deliveryMethod,
        @NotNull @Valid Address shipping,
        @NotEmpty List<@NotNull @Valid OrderLine> lines
) {
}
~~~

For `Address`:

~~~java
public record Address(
        @NotBlank String recipient,
        @NotBlank String city,
        @NotBlank String postalCode
) {
}
~~~

For `OrderLine`:

~~~java
public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity
) {
}
~~~

These snippets require importing `jakarta.validation.Valid` and `jakarta.validation.constraints.*`; the complete project in section 17 contains full files and imports.

Meaning:

- `@NotBlank` rejects `null`, `""`, and whitespace-only strings for `CharSequence`.
- `@NotNull` ensures the reference is not null.
- `@NotEmpty` rejects `null` and empty collections.
- `@Min(1)` ensures the number is at least 1; `@Min` alone does **not** reject null.
- `@Valid` on `shipping` triggers constraint validation inside `Address`.
- `List<@NotNull @Valid OrderLine>` ensures no element is null and cascades validation into each `OrderLine`.
- Violations can carry paths like `shipping.city` or `lines[0].quantity` depending on the validator and data list.

Do not assume `@Valid` on the root DTO automatically recurses into every level unless `@Valid` is placed on nested fields and list elements. Unit or integration tests must prove deep violations are reported properly.

### 12.1. Does @JsonProperty(required=true) Replace @NotNull?

No. `required` in JSON creator/binding relates to property presence under Jackson's rules; it does not replace validation semantics, guarantee non-blank strings, positive numbers, or valid child objects. Depending on version/creator configuration, certain annotations only affect specific object instantiation paths.

For public APIs, keep DTOs clean and use Bean Validation for post-binding values. If you need to distinguish absent/null or complex creator rules, write targeted Jackson tests.

## 13. How Validation Differs Between MVC and WebFlux.fn

**Spring MVC annotated controller:** typically uses `@Valid @RequestBody CreateOrderRequest request` with a matching validation provider. Binding errors can throw `HttpMessageNotReadableException`; Bean Validation failures typically throw `MethodArgumentNotValidException`. Using `@RestControllerAdvice` standardizes them into HTTP 400.

**Spring WebFlux annotated controller:** can use `@Valid` with `@RequestBody` on reactive APIs, though exception/validation flows differ from MVC, especially when the argument is `Mono<T>`. Check `WebExchangeBindException`, `ServerWebInputException`, and test annotation/method validation per version.

**Spring WebFlux.fn:** `request.bodyToMono(CreateOrderRequest.class)` only decodes the body; it **does not automatically run all Bean Validation constraints** the way `@Valid` does on annotated controllers. Inject `jakarta.validation.Validator` into the `HandlerFunction` and call `validator.validate(dto)`, or build an equivalent controlled validation step.

Example:

~~~java
Set<ConstraintViolation<CreateOrderRequest>> violations =
        validator.validate(requestDto);

if (!violations.isEmpty()) {
    List<String> fields = violations.stream()
            .map(v -> v.getPropertyPath().toString())
            .distinct()
            .sorted()
            .toList();
    // Create ServerResponse 400 per the API contract.
}
~~~

This snippet assumes `validator` and `requestDto` already exist; the complete project below contains the full method. **Never blindly return rejected values or raw exception messages**: they can contain PII, tokens, or internal class names.

## 14. WebFlux Codecs and MVC HttpMessageConverter

In Spring WebFlux, HTTP message readers/writers use codecs matching media types; with Jackson 2, `Jackson2JsonDecoder`/`Encoder` are used in standard configurations. `bodyToMono` reads the request body `Publisher` and decodes it into an object. In Spring MVC, `HttpMessageConverter` reads the Servlet request body.

Differences learners must understand:

| Aspect | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Common input API | `@RequestBody CreateOrderRequest` | `bodyToMono(CreateOrderRequest.class)` or `@RequestBody Mono<T>` |
| Boot 3.x JSON infrastructure | `MappingJackson2HttpMessageConverter` | `Jackson2JsonDecoder`/`Encoder` |
| Decode error handling | `HttpMessageNotReadableException` | May see `DecodingException`, `ServerWebInputException` |
| Validation | `@Valid`/Bean Validation in annotated binding | Annotated or explicit `Validator` in functional handlers |
| HTTP body | Servlet read/write | `Publisher`/Reactive Streams |
| Media type selection | `Content-Type` and `Accept` | `Content-Type` and `Accept` |
| Threading | Servlet stack | Reactive stack; avoid blocking the event loop |

The same Boot-configured `ObjectMapper` can be shared across components, but if the application builds custom codecs or mappers, global settings may not affect them. Hence, HTTP tests are more authoritative than standalone `new ObjectMapper()` unit tests.

**Watch out for 415 errors:** a `text/plain` request body rejected by the JSON reader can result in `UnsupportedMediaTypeStatusException`/415. Do not catch `Exception` broadly and force everything into `INVALID_JSON` 400, which obscures media type mismatches.

## 15. Categorizing Error Responses Safely

Recommended concise structure:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request validation failed",
  "fields": [
    "shipping.city",
    "lines[0].quantity"
  ]
}
~~~

Client-friendly error codes:

- `INVALID_JSON`: syntax/mapping error, including unknown enums or unknown fields under strict policy.
- `MISSING_BODY`: missing JSON body.
- `VALIDATION_FAILED`: DTO decoded, but failed constraints.
- `UNSUPPORTED_MEDIA_TYPE`: wrong `Content-Type`, returning 415 from the framework layer.
- `BUSINESS_RULE_VIOLATION`: valid JSON, but rejected by domain rules.

Never return raw `com.fasterxml.jackson.databind.exc.UnrecognizedPropertyException` or raw stack traces. Under strict unknown fields, internal messages can reveal type names, field paths, and even raw JSON inputs. Clients should receive stable error codes; internal logs can record sanitized paths and trace IDs for investigation.

If the API must return exact mapping failure fields, extract `JsonMappingException.getPath()` carefully and sanitize; never expose `exception.getMessage()` verbatim since it contains server internals, input values, or class names.

## 16. Strict/Lenient Policies and API Version Contracts

There is no single flag "right for every case":

| Scenario | Unknown Fields | Unknown Enums | Nested Validation |
| --- | --- | --- | --- |
| Order creation / payments | Usually strict | Reject | Mandatory |
| Admin / permissions API | Strict | Reject | Mandatory |
| Multi-version event consumer | Controlled lenient | Can map to `UNKNOWN` | Mandatory for consumed fields |
| Unstandardized data import | Custom parse/`JsonNode` | Log and classify | Validate against import schema |
| Partner read model | Can use local `@JsonIgnoreProperties` | Alias/fallback per contract | Validate before use |

Choose the policy during API design, not by toggling globals in production to work around one failing request. When tightening strictness, prepare contract tests, client notices, new error metrics, canary rollouts, and rollback plans.

**An input DTO must never be a JPA entity:** separate request DTOs from entities so clients cannot inadvertently manipulate fields like `isAdmin`, `internalStatus`, `cost`, or `ownerId`. Unknown-field strictness protects the contract, while access control must be enforced at service/security layers.

## 17. Hands-On Project: Java 17 + Spring Boot 3.3 + WebFlux.fn

The project below runs a `POST /api/orders` API using strict Jackson 2 for unknown fields and numeric enum values, accepts nested JSON, invokes Jakarta Bean Validation **explicitly in WebFlux.fn**, and returns 201/400 with structured responses.

Prerequisites: JDK 17+, a Gradle Wrapper compatible with Spring Boot 3.3, Maven Central access, and an open port. The example uses `AtomicLong` for in-memory ID generation without a database; IDs reset upon restart. This project teaches JSON/codecs, not production order system architecture.

### 17.1. Project Structure

~~~text
json-contract-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/json/
        JsonContractApplication.java
        DeliveryMethod.java
        Address.java
        OrderLine.java
        CreateOrderRequest.java
        OrderCreated.java
        ApiError.java
        OrderHandler.java
        OrderRoutes.java
      resources/
        application.yml
    test/
      java/example/json/
        JsonContractApplicationTests.java
~~~

### 17.2. settings.gradle

~~~groovy
rootProject.name = 'json-contract-demo'
~~~

### 17.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

To keep WebFlux as the web stack, the example omits `spring-boot-starter-web`. When both MVC and WebFlux starters are present, Spring Boot typically picks Servlet MVC. In real projects, use build-managed dependency versions.

### 17.4. application.yml

~~~yaml
spring:
  application:
    name: json-contract-demo
  jackson:
    deserialization:
      fail-on-unknown-properties: true
      fail-on-numbers-for-enums: true

server:
  port: 8080
~~~

These two flags underpin two regression tests: unknown fields and numeric enums must fail at the JSON decode layer. If the flags do not reach the actual HTTP mapper, the tests will catch it.

### 17.5. JsonContractApplication.java

~~~java
package example.json;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonContractApplication.class, args);
    }
}
~~~

### 17.6. DeliveryMethod.java

~~~java
package example.json;

public enum DeliveryMethod {
    STANDARD,
    EXPRESS
}
~~~

### 17.7. Address.java

~~~java
package example.json;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String recipient,
        @NotBlank String city,
        @NotBlank String postalCode
) {
}
~~~

### 17.8. OrderLine.java

~~~java
package example.json;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderLine(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity
) {
}
~~~

`Integer` is used instead of `int` to distinguish missing/null from an explicitly sent zero. `@Min(1)` catches `0` or negative values; `@NotNull` catches null.

### 17.9. CreateOrderRequest.java

~~~java
package example.json;

import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record CreateOrderRequest(
        @NotBlank String customerId,
        @NotNull DeliveryMethod deliveryMethod,
        @NotNull @Valid Address shipping,
        @NotEmpty List<@NotNull @Valid OrderLine> lines
) {
}
~~~

Validation cascades into `shipping` and each `OrderLine`. If `shipping=null`, `@NotNull` rejects it; if `lines=[]` or null, `@NotEmpty` rejects it. If `lines` contains a null element, the type-use `@NotNull` catches it.

### 17.10. OrderCreated.java

~~~java
package example.json;

public record OrderCreated(
        long id,
        DeliveryMethod deliveryMethod,
        int lineTypes
) {
}
~~~

`lineTypes` is the number of distinct line items, not the sum of quantities.

### 17.11. ApiError.java

~~~java
package example.json;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<String> fields
) {
}
~~~

Returns only offending field names, never raw input values (especially important when payloads contain sensitive data).

### 17.12. OrderHandler.java

~~~java
package example.json;

import java.net.URI;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

import org.springframework.core.codec.DecodingException;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.server.ServerWebInputException;

import reactor.core.publisher.Mono;

@Component
public class OrderHandler {

    private final Validator validator;
    private final AtomicLong ids = new AtomicLong();

    public OrderHandler(Validator validator) {
        this.validator = validator;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(input -> {
                    Set<ConstraintViolation<CreateOrderRequest>> violations =
                            validator.validate(input);

                    if (!violations.isEmpty()) {
                        List<String> fields = violations.stream()
                                .map(v -> v.getPropertyPath().toString())
                                .distinct()
                                .sorted()
                                .toList();

                        return ServerResponse.badRequest()
                                .contentType(MediaType.APPLICATION_JSON)
                                .bodyValue(new ApiError(
                                        "VALIDATION_FAILED",
                                        "Request validation failed",
                                        fields));
                    }

                    long id = ids.incrementAndGet();
                    OrderCreated output = new OrderCreated(
                            id,
                            input.deliveryMethod(),
                            input.lines().size());

                    return ServerResponse
                            .created(URI.create("/api/orders/" + id))
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(output);
                })
                .switchIfEmpty(Mono.defer(
                        () -> badJson("MISSING_BODY",
                                "JSON body is required")))
                .onErrorResume(DecodingException.class,
                        ex -> badJson("INVALID_JSON",
                                "Malformed or incompatible JSON"))
                .onErrorResume(ServerWebInputException.class,
                        ex -> badJson("INVALID_JSON",
                                "Malformed or incompatible JSON"));
    }

    private Mono<ServerResponse> badJson(
            String code, String message) {
        return ServerResponse.badRequest()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiError(code, message, List.of()));
    }
}
~~~

Exact flow analysis:

1. `bodyToMono` decodes JSON into `CreateOrderRequest` and its nested records.
2. Unknown properties or invalid enums cause the codec to emit an error; the two `onErrorResume` handlers here handle matching `DecodingException` or `ServerWebInputException`. Other exceptions are not automatically converted into 400.
3. Once decoded, `Validator` checks root fields and nested objects/lists. On failure, it returns 400 `VALIDATION_FAILED` with sorted paths without incrementing the ID.
4. If the body is empty, `Mono.empty` converts to 400 `MISSING_BODY`.
5. If valid, it increments `AtomicLong` and returns HTTP 201 Created, `Location=/api/orders/{id}`, and body `OrderCreated`.

**Important boundary:** Some body errors may be wrapped differently by the framework depending on version/codec. If in a real project an exception does not fall into these two types, use an appropriate web-level error handler and test it rather than blindly widening to `onErrorResume(Exception.class,...)`, which masks server bugs. When request `Content-Type` is wrong, let the framework's media type error produce 415 instead of coercing it into `INVALID_JSON`.

In a production project, separate endpoint DTOs from persistence/domain models, and add services, database transactions, authorization, idempotency, metrics, and business validation.

### 17.13. OrderRoutes.java

~~~java
package example.json;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration(proxyBeanMethods = false)
public class OrderRoutes {

    @Bean
    RouterFunction<ServerResponse> orderRouter(
            OrderHandler handler) {
        return RouterFunctions.route()
                .POST("/api/orders", handler::create)
                .build();
    }
}
~~~

Do not add `RequestPredicates.contentType(application/json)` to this route: if the predicate fails to match, the request may return 404 before the codec can report 415. The router only matches method/path; the body decoder enforces media type.

## 18. Running the Project and Testing with curl

After placing sources in the right packages/paths and creating a compatible Gradle Wrapper, on Linux/macOS:

~~~bash
./gradlew bootRun
~~~

On PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Once the server is running on port 8080, send valid JSON:

~~~bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  --data-binary '{
    "customerId": "C-101",
    "deliveryMethod": "EXPRESS",
    "shipping": {
      "recipient": "Mai",
      "city": "Ha Noi",
      "postalCode": "10000"
    },
    "lines": [
      {"sku": "BOOK-01", "quantity": 2}
    ]
  }'
~~~

If this is the first valid request after startup, expect HTTP 201 Created, `Location=/api/orders/1`, and an equivalent body:

~~~json
{"id":1,"deliveryMethod":"EXPRESS","lineTypes":1}
~~~

Do not rely on JSON key ordering or fixed IDs after multiple requests. The demo API only assigns IDs in memory without persisting orders.

### 18.1. Unknown Property at Root

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "isAdmin": true,
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

With strict configuration, the JSON is rejected during deserialization. Expect HTTP 400 and a payload like:

~~~json
{"code":"INVALID_JSON","message":"Malformed or incompatible JSON","fields":[]}
~~~

### 18.2. Unknown Property in a Nested Object

Send `shipping.gps`:

~~~json
{
  "customerId": "C-101",
  "deliveryMethod": "EXPRESS",
  "shipping": {
    "recipient": "Mai",
    "city": "Ha Noi",
    "postalCode": "10000",
    "gps": "unknown"
  },
  "lines": [
    {"sku": "BOOK-01", "quantity": 2}
  ]
}
~~~

Expect 400 `INVALID_JSON` when the strict mapper applies to `Address`. This is a crucial test proving strictness applies beyond the root level.

### 18.3. Invalid Enum String

Replace `deliveryMethod="EXPRESS"` with `"SAME_DAY"`. The enum has no `SAME_DAY` constant, so expect 400 `INVALID_JSON`, not a fallback to `STANDARD`.

### 18.4. Numeric Enum Violating Contract

Replace `deliveryMethod="EXPRESS"` with `deliveryMethod=1` (JSON number). Thanks to `fail-on-numbers-for-enums=true`, expect 400 `INVALID_JSON`. If that flag were off in Jackson 2, `1` would map to `EXPRESS` by ordinal, making the API fragile whenever enum declaration order changes.

### 18.5. Invalid Nested Validation

Change `shipping.city` to `""` or `lines[0].quantity` to `0`. JSON deserializes fine, but `@NotBlank` or `@Min` causes `Validator` to return 400 `VALIDATION_FAILED`. The error body lists fields like `shipping.city` or `lines[0].quantity` without echoing raw inputs.

## 19. WebTestClient Integration Tests

The tests below use a **real HTTP server on `RANDOM_PORT`** to verify routing, the Boot-configured JSON decoder, validation, and HTTP responses. They do not merely invoke a standalone `ObjectMapper`.

File `src/test/java/example/json/JsonContractApplicationTests.java`:

~~~java
package example.json;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class JsonContractApplicationTests {

    @Autowired
    WebTestClient client;

    private static final String VALID_JSON = """
            {
              "customerId":"C-101",
              "deliveryMethod":"EXPRESS",
              "shipping":{
                "recipient":"Mai",
                "city":"Ha Noi",
                "postalCode":"10000"
              },
              "lines":[
                {"sku":"BOOK-01","quantity":2}
              ]
            }
            """;

    @Test
    void validNestedPayloadReturns201() {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID_JSON)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().exists("Location")
                .expectBody()
                .jsonPath("$.deliveryMethod").isEqualTo("EXPRESS")
                .jsonPath("$.lineTypes").isEqualTo(1);
    }

    @Test
    void unknownRootFieldIsRejected() {
        String json = VALID_JSON.replace(
                "\"customerId\":\"C-101\"",
                "\"customerId\":\"C-101\",\"isAdmin\":true");

        expectInvalidJson(json);
    }

    @Test
    void unknownNestedFieldIsRejected() {
        String json = VALID_JSON.replace(
                "\"city\":\"Ha Noi\"",
                "\"city\":\"Ha Noi\",\"gps\":\"secret\"");

        expectInvalidJson(json);
    }

    @Test
    void invalidEnumStringIsRejected() {
        String json = VALID_JSON.replace(
                "\"EXPRESS\"", "\"SAME_DAY\"");

        expectInvalidJson(json);
    }

    @Test
    void numericEnumIsRejected() {
        String json = VALID_JSON.replace(
                "\"deliveryMethod\":\"EXPRESS\"",
                "\"deliveryMethod\":1");

        expectInvalidJson(json);
    }

    @Test
    void nestedBlankCityFailsValidation() {
        String json = VALID_JSON.replace(
                "\"city\":\"Ha Noi\"", "\"city\":\"\"");

        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(json)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("VALIDATION_FAILED");
    }

    @Test
    void nestedQuantityZeroFailsValidation() {
        String json = VALID_JSON.replace(
                "\"quantity\":2", "\"quantity\":0");

        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(json)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("VALIDATION_FAILED");
    }

    @Test
    void missingBodyReturnsBadRequest() {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("MISSING_BODY");
    }

    private void expectInvalidJson(String json) {
        client.post()
                .uri("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(json)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code")
                .isEqualTo("INVALID_JSON");
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

**QA Note:** The Java test helpers use `String.replace` with exact substrings present in `VALID_JSON` (no whitespace around the colons on those lines), ensuring inputs truly mutate rather than accidentally re-sending valid JSON. `VALID_JSON` is a Java 17 text block. In test environments with custom exception handlers, adjust assertions to match the implemented API contract and verify real code.

Add extra regression tests as needed: malformed JSON syntax, duplicate fields, empty arrays, null list elements, null `shipping`, missing `deliveryMethod`, wrong types, oversized bodies, `Content-Type: text/plain`, trailing tokens, and deeply nested structures.

## 20. Nulls, Missing Fields, and Primitives in JSON

The Java type strongly determines deserialization behavior:

~~~java
record BadLine(String sku, int quantity) {}
record BetterLine(String sku, Integer quantity) {}
~~~

With `BadLine`, if `quantity` is missing or null and strict primitive checks are off, Jackson 2 may supply the default `0`, leaving the application unable to tell whether the client actually sent `0` or omitted it. With `BetterLine`, missing/null becomes Java `null`, easily caught by `@NotNull`.

Clear strategies:

- Use boxed `Integer`/`Long` instead of primitives for required input fields when missingness must be detected.
- Combine `@NotNull` with `@Min`/`@Max`.
- Use `@NotBlank` for required strings and `@NotEmpty` for collections.
- Use `@Valid` on nested objects and list elements.
- If missing and explicit null require distinct behavior, use a schema/creator or representation with presence tracking.
- Do not rely on `@JsonInclude(NON_NULL)` to infer input validation; it primarily governs response serialization.

Jackson 2 also provides `FAIL_ON_NULL_FOR_PRIMITIVES`, `FAIL_ON_MISSING_CREATOR_PROPERTIES`, and `FAIL_ON_NULL_CREATOR_PROPERTIES`. They have specific semantics useful in strict contracts, yet affect many DTOs broadly. Do not toggle them globally just to fix one field; verify with targeted tests.

## 21. Numeric Coercion and Numeric Enum Cases

Jackson 2 can coerce values across types—for example, JSON string `"2"` to a numeric property under some setups, or numbers to enum ordinals if allowed. Coercion is not equivalent to validation.

For public APIs requiring strict JSON types, in addition to `fail-on-numbers-for-enums`, you can configure Jackson `CoercionConfig` in Jackson 2 and test inputs such as:

- `"quantity":"2"` (string) instead of `quantity:2` (number).
- `"deliveryMethod":1` (number) instead of `"EXPRESS"`.
- `"lines":{}` instead of an array.
- `"shipping":[]` instead of an object.
- Empty string for a nested object.
- Float `1.2` for `Integer`.
- `null` for primitives and boxed types.

Do not rely on default coercion behavior of a specific Jackson version without contract tests; flags and naming APIs evolve across versions. Use DTOs and validation to enforce errors right at the boundary.

## 22. JSON Trees and Controlled Extensible Data

When a JSON source genuinely carries variable fields, a strict static DTO may not fit. You can choose `JsonNode` or `Map<String, JsonNode>` for the extensible payload section:

~~~java
public record PartnerPayload(
        String id,
        Map<String, JsonNode> metadata
) {
}
~~~

This snippet requires importing `Map` and `com.fasterxml.jackson.databind.JsonNode` for Jackson 2. This does not mean arbitrary metadata is allowed to do anything. Enforce:

- Allowed key names or namespace validation.
- Limits on total key count, depth, string length, and payload size.
- Never letting metadata drive authorization or unconstrained SQL queries.
- Never logging raw tokens/passwords.
- Schema versioning and compatibility for open payloads.

When mapping into `JsonNode`, Jackson stores a JSON tree instead of binding domain DTO fields. Therefore `FAIL_ON_UNKNOWN_PROPERTIES` cannot replace JSON Schema validation for raw trees.

## 23. Duplicate Keys and Resource Exhaustion Attacks

A JSON document can repeat keys:

~~~json
{
  "deliveryMethod": "STANDARD",
  "deliveryMethod": "EXPRESS"
}
~~~

Many parsers/binders keep the last value or handle duplicates differently. Repeated fields can create **parser differentials** across gateways, WAFs, payload signatures, and backends. For sensitive APIs, align duplicate-key policies across gateways and Jackson, enable strict duplicate detection when appropriate, and test it.

Do not confuse `FAIL_ON_READING_DUP_TREE_KEY` (focused on the tree model) with parser-level strict duplicate detection when binding DTOs. Their scopes are not identical.

Also control:

- HTTP body size at proxy/server and codec layers.
- Nesting depth and list element counts.
- Overly long strings and numbers.
- Multipart/file payloads on dedicated endpoints.
- Rate limits, request timeouts, and cancellation.
- Verbosity of JSON error logging.

Resource protection cannot rely solely on `@Valid` after the whole body has been decoded, since an oversized payload can exhaust resources before validation runs.

## 24. Using Logs and Tracing to Diagnose JSON Failures

When encountering 400s in production:

1. Check `Content-Type` and the endpoint's media types.
2. Distinguish parser syntax errors, mapping errors, and Bean Validation via exception types.
3. Identify the JSON path if available while sanitizing data.
4. Confirm strictness settings on the actual HTTP mapper/codec in use.
5. Check schema version and client version; did a newer client add a field?
6. Check enum wire values; were constants renamed or did a client send numbers?
7. Verify cascaded `@Valid` and nullable fields in nested DTOs.
8. Inspect body/nesting limits if failures occur only on large payloads.
9. Reproduce with `WebTestClient` using sanitized payloads.
10. After fixing, add tests to prevent regressions.

Useful metrics: counts of `INVALID_JSON`, `VALIDATION_FAILED`, `UNSUPPORTED_MEDIA_TYPE`; rates per route and client version; unknown-field error counts during strict mode rollouts; rejected enum value rates. Avoid putting raw field values into metric labels to prevent high cardinality and PII leaks.

## 25. Forward Compatibility and Rolling Upgrade Strategies

When clients and servers deploy at different paces, strictness is a contract decision:

- **Request commands:** usually require strict fields, enums, and nested validation. Returning 400 surfaces mismatches immediately when clients send unknown fields.
- **Responses read by older clients:** can tolerate new response fields so older clients keep working when the server adds data.
- **Event-driven consumers:** often ignore extra fields or route unknown enums to dead-letter/quarantine rather than misprocessing.
- **Migrations:** accept old/new aliases for a bounded window with deprecation metrics and per-client-version tests.

Use OpenAPI/JSON Schema to publish required/optional fields, allowed enum values, and nested models. However, schema docs do not replace runtime validation; maintain code and tests in sync.

**A dangerous example:** a client sends `"isAdmin":true` in a profile update request, the server ignores the field and returns 200, and the client assumes permissions were updated. Strict mode returning 400 is much clearer, though actual permissions must still be enforced by service/server authorization.

## 26. Troubleshooting Table

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| Unknown field is not rejected | Boot mapper is lenient, `@JsonIgnoreProperties`, or custom codec | Check `FAIL_ON_UNKNOWN_PROPERTIES`, annotations, and HTTP integration tests |
| Unknown field in nested object is accepted | Nested type has `ignoreUnknown`, uses `Map`/`JsonNode`, or custom converter | Inspect nested types and decoding path |
| Enum `"EXPRESS"` works but `"express"` errors | Enums are case-sensitive | Define wire format; do not toggle case-insensitivity carelessly |
| Numeric enum `1` is accepted | Ordinal coercion not disabled | Enable `FAIL_ON_NUMBERS_FOR_ENUMS` and test |
| Unknown enum becomes null | `READ_UNKNOWN_ENUM_VALUES_AS_NULL` enabled | Check null policy and `@NotNull` |
| Unknown enum becomes `UNKNOWN` | Default enum feature + annotation enabled | Check use case; avoid treating `UNKNOWN` as a valid command |
| Blank `shipping.city` is accepted | Missing cascaded `@Valid` or missing `Validator` | Check field annotations and validation path |
| Missing `lines[0].quantity` becomes `0` | Primitive `int` and default value | Use `Integer` + `@NotNull`, test missing/null |
| POST JSON returns 415 | Wrong `Content-Type` or missing codec | Check headers, starters, and codecs |
| POST JSON returns 400, client sees stack trace | Error handler returns raw exception message | Standardize `ApiError` and sanitize |
| WebFlux.fn does not validate DTO | `bodyToMono` only decodes | Inject `Validator.validate` after decoding |
| Strict in unit tests, lenient over HTTP | Tested `ObjectMapper` differs from HTTP mapper | Test with `RANDOM_PORT` and real endpoints |
| JSON import errors after Boot upgrade | Jackson 2 vs. Jackson 3 package/API changes | Follow migration guide for target Boot version |
| JSON response has wrong field names | Different naming strategy or `@JsonProperty` | Test serialized contract and inspect mapper |
| Parsing large payloads exhausts memory | Missing request/codec size limits | Enforce limits at server/proxy/codec layers |

## 27. Advanced Practice Exercises

1. **Unknown root:** Send `isAdmin` in order creation JSON; verify 400 `INVALID_JSON` in strict mode. Then test lenient mode on a separate DTO and record the difference.
2. **Unknown nested:** Send `shipping.gps` and `lines[0].notes`; confirm nested paths are rejected by the strict mapper.
3. **Enum strings:** Send `SAME_DAY` and `express`; record status, exception type, and sanitized response.
4. **Enum ordinals:** Send `1`/`0`; check behavior before and after `FAIL_ON_NUMBERS_FOR_ENUMS`; demonstrate why ordinals are unsuitable for wire formats.
5. **Enum default:** Create a separate event DTO with `@JsonEnumDefaultValue UNKNOWN`; test a newer client sending an unknown value and verify the handling policy. Do not apply to live delivery commands.
6. **Nested validation:** Test `shipping=null`, `city=""`, `lines=[]`, `lines=[null]`, `quantity=0`, and omitted `quantity`; compare field lists.
7. **Strict creator:** Design a requirement distinguishing missing from explicit null; implement validation/presence tracking and test each case.
8. **Error format:** Return stable error codes, request IDs, and offending field paths; verify clients never see raw stack traces or secrets.
9. **Compatibility:** Add alias `customer_id` via `@JsonAlias`, then remove it after a scheduled migration window.
10. **Security:** Test duplicate keys, deeply nested payloads, oversized bodies, and JSON type coercion; enforce limits and observe responses.
11. **Web stacks:** Implement the equivalent endpoint in Spring MVC `@RestController`; verify exception types differ from WebFlux while the API error contract stays identical.
12. **Deployment:** Use identical artifacts/mappers across staging and production, compare config flags, and monitor 400 rates post-rollout.

A practice exercise is complete when it includes source code, HTTP requests, passing tests, actual JSON status/responses, and an analysis of whether each failure occurred at the parser, mapping, validation, or business layer. Never fabricate test outputs or benchmarks without executing them in a real environment.

## 28. Self-Check

1. How does an unknown JSON property differ from a `null` value?
2. How does Jackson 2's `FAIL_ON_UNKNOWN_PROPERTIES` differ from Boot 3.x's default configuration?
3. Why must you test the HTTP codec's `ObjectMapper` rather than just `new ObjectMapper()` in a unit test?
4. When is `@JsonIgnoreProperties(ignoreUnknown=true)` appropriate?
5. Does `@JsonAlias` make Jackson serialize using the alias name?
6. Why is a numeric enum a fragile contract when declaration order changes?
7. How do `READ_UNKNOWN_ENUM_VALUES_AS_NULL` and `READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` differ?
8. Does `@JsonEnumDefaultValue` take effect if its corresponding feature is not enabled?
9. Why is `@NotNull` necessary for enum inputs?
10. Why does a nested `Address` object need `@Valid`?
11. Why does `lines` need both `@NotEmpty` and `@Valid` on elements?
12. How do `Integer` and `int` behave differently when JSON omits `quantity`?
13. When does the decoder fail before Bean Validation runs?
14. Does WebFlux.fn `bodyToMono` automatically run all Jakarta Bean Validation checks?
15. How do MVC `HttpMessageConverter` and WebFlux codecs differ at the processing stack level?
16. Why should `Content-Type` errors return 415 instead of being forced into `INVALID_JSON` 400?
17. Why should raw Jackson exception messages never be returned to clients?
18. Are unknown fields in a `JsonNode` handled by `FAIL_ON_UNKNOWN_PROPERTIES` like DTO properties?
19. What risk do duplicate JSON keys create when gateways and backends process them differently?
20. What notable changes does Spring Boot 4.x introduce regarding Jackson packages and mappers?
21. Which tests prove strict mode applies to unknown nested properties and enum ordinals?
22. When should you use strict request DTOs alongside lenient response/event consumers?

## 29. References

- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.jackson.deserialization.*` and related settings.
- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): how Boot 3 integrates Jackson.
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html): `ServerRequest.bodyToMono`, `ServerResponse`, error handling, and codecs.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): handling bodies via reactive readers/writers.
- [Jackson 2 — DeserializationFeature](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/2.17.2/com/fasterxml/jackson/databind/DeserializationFeature.html): `FAIL_ON_UNKNOWN_PROPERTIES`, enum-number policy, and unknown enum features.
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/3.0/): `@Valid` cascading, constraints, and collection element validation.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): Jackson 3 changes, packages, configuration properties, and mappers.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): verifying JSON decoders, status, and responses in WebFlux.

**Conclusion:** The JSON parser/mapper determines whether structure is readable; Bean Validation determines whether the DTO satisfies constraints; services determine whether business rules allow execution. For unknown fields and invalid enums, choose an explicit policy and cover it with tests. For nested data, validate across objects and lists. Only when these boundaries are crisp will JSON error responses be accurate, safe, and maintainable.
