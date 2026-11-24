# Jackson Changes, JSON Testers, and Serialization Dependencies

## 1. Why Does This Matter When Upgrading Spring Boot?

A Spring Boot service can boot cleanly, pass every unit test, and still break clients after upgrading Jackson or changing serialization dependencies. Two JSON payloads can both be syntactically valid yet violate the same wire contract:

**Before upgrading:**

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "PAID"
}
~~~

**After serializer configuration accidentally changes:**

~~~json
{
  "invoiceId": "INV-7",
  "issuedAt": 1767323045,
  "amount": {"cents": 1999},
  "state": "PAID",
  "memo": null
}
~~~

Differences lie in field names, timestamp representation, money data shape, and null-inclusion policy. An older consumer may fail immediately—or worse, read the wrong value and keep processing.

This lesson belongs to **Versions and Migration** in the **Spring Boot - testing** module, covering **Jackson changes, JSON testers, and serialization dependencies**.

Learning objectives:

1. Understand the distinction between the Jackson library, Spring Boot auto-configuration, and MVC HTTP message converters.
2. Distinguish Jackson 2 (`com.fasterxml.jackson.databind.ObjectMapper`) from Jackson 3 (`tools.jackson.databind.json.JsonMapper`).
3. Know that Spring Boot 3.x uses Jackson 2, while Spring Boot 4.0 prefers Jackson 3 with a temporary Jackson 2 bridge.
4. Use `dependencyInsight` to inspect the actual resolved Jackson version and prevent core/databind/module mismatches.
5. Use `@JsonTest`, `JacksonTester`, `JsonContent`, JSONPath, AssertJ, and golden fixtures to protect JSON contracts.
6. Test custom `@JsonComponent` serializers/deserializers in Spring Boot 3.3.5, and understand migrating to `@JacksonComponent` on Boot 4.
7. Distinguish the Boot-injected mapper from a manually instantiated `new ObjectMapper()`.
8. Catch regressions in `snake_case`, nullability, enums, numeric coercion, Java Time, timezones, and extra fields.
9. Test tolerant and strict legacy consumers against candidate JSON instead of only round-tripping the new DTO.
10. Verify real Spring MVC JSON via `@WebMvcTest` and wiring via `@SpringBootTest`.
11. Build a **Java 17, Spring Boot 3.3.5, Gradle 8.8, JUnit Jupiter** project with complete fixtures and source code.
12. Establish a Jackson 3 upgrade plan, CI contract gate, dependency conflict resolution, and rollback strategy.

**Core mindset:** "Compiles" does not mean "JSON compatible". A correctly typed Java object can still carry contract-breaking values: cents turned into dollars, timestamps in the wrong timezone, or a new enum unsupported by older clients.

## 2. Three Serialization Layers Frequently Confused

~~~text
Spring MVC Controller / RestClient / messaging producer
                       |
                       v
Spring HTTP MessageConverter / codec / serializer adapter
                       |
                       v
Spring Boot auto-configured JSON mapper
                       |
           +-----------+-----------+
           |           |           |
       Jackson     custom modules  settings
       library     serializers     profiles
           |
           v
       JSON wire bytes
           |
           v
Legacy client / new client / schema validator
~~~

A test calling `new ObjectMapper().writeValueAsString(dto)` only tests **a self-created mapper**. It does not prove the Spring Boot app uses that mapper over HTTP, and it can miss the Java Time module, `@JsonComponent`, and config properties.

`@JsonTest` exercises the mapper in the **JSON test slice**, whereas `@WebMvcTest` tests JSON produced through **Spring MVC converters**. `@SpringBootTest` verifies full application wiring when custom configs/beans influence the mapper. If clients use a separate mapper, test the client side too.

## 3. Version and API Map

| Line | Typical Mapper | JSON Test Support | Key Notes |
| --- | --- | --- | --- |
| Boot 3.3.x | Jackson 2 `ObjectMapper` | `@JsonTest`, `JacksonTester` | `@JsonComponent`, `JavaTimeModule`, Boot BOM |
| Boot 3.4/3.5 | Jackson 2 `ObjectMapper` | `JacksonTester` | Jackson minor / Boot defaults may evolve |
| Boot 4.0 | Jackson 3 `JsonMapper` | `JacksonTester` for Jackson 3 | New group/packages, `@JacksonComponent`, module discovery |
| Boot 4.0 bridge | Secondary Jackson 2 `ObjectMapper` | `Jackson2Tester` for bridge | Deprecated; requires a migration plan |

Specific support lines change over time. The versions in this lab are **deliberate technical reference points**, not a guarantee that they still receive production security patches.

### 3.1. Spring Boot 3.x / Jackson 2

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.JsonDeserializer;
~~~

Spring Boot 3.3.5 manages Jackson via the dependency BOM. With `spring-boot-starter-web`, the JSON mapper is pre-configured and wired into Spring MVC.

### 3.2. Spring Boot 4.0 / Jackson 3

~~~java
import tools.jackson.databind.json.JsonMapper;
import tools.jackson.databind.JsonNode;
~~~

Jackson 3 moves most group IDs and Java packages from `com.fasterxml.jackson` to `tools.jackson`. **Important exception:** Jackson annotations remain in `com.fasterxml.jackson.annotation` and the annotations artifact remains under `com.fasterxml.jackson.core`, per the Spring Boot 4.0 Migration Guide. Therefore, never run an automated replace-all across all imports.

### 3.3. The New Mapper Is Not Equivalent to the Old Mapper

A custom `ObjectMapper` bean used by a Boot 3 app to alter JSON behavior **does not automatically replace** Jackson 3's `JsonMapper` configured by Boot 4. If both majors coexist, the app may hold two mappers picked differently by converters and clients. Always verify which mapper actually produces HTTP responses.

## 4. Serialization Dependencies Are Part of the Contract

Common modules in the JSON stack:

| Dependency | Role |
| --- | --- |
| Jackson core | Streaming parser/generator |
| Jackson databind | Mapping between Java objects and JSON trees |
| Jackson annotations | Property naming, include/ignore, format, subtype hints |
| JSR310/JavaTime module (Jackson 2) | `Instant`, `LocalDate`, `OffsetDateTime` |
| JDK8 module | `Optional` and Java 8 types |
| ParameterNames module | Constructor parameter names when needed |
| Kotlin module | Kotlin data classes, nullability behavior |
| Jackson XML module | XML mapper, if the app serves XML |
| Jackson YAML/CBOR/Smile | Other wire formats |
| Spring Boot starters/BOM | Resolved versions and auto-configuration |
| Spring Boot test dependencies | JSON testers, JUnit, AssertJ, JsonPath/JSONAssert |

An SDK bringing in another transitive Jackson dependency can skew `jackson-databind`, `jackson-core`, and datatype modules. This manifests as `NoSuchMethodError`, `NoClassDefFoundError`, `LinkageError`, or silent JSON output changes without exceptions.

### 4.1. Diagnosing With Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-datatype-jsr310 --configuration runtimeClasspath
~~~

Distinguish **requested version** from **resolved version**. Read Spring Boot BOM dependency constraints and see why Gradle picked a given version. Do not pin a newer `jackson-databind` while leaving core/datatype modules on older versions without verifying compatibility.

### 4.2. Test Runtime Can Differ From Production Runtime

A Jackson module placed only in `testImplementation` can make tests pass while the production app lacks that module. Inspect both `runtimeClasspath` and `testRuntimeClasspath`. With `spring-boot-starter-web`, JSON support must exist in main runtime; never drop a starter and add the JSON module only to test scope.

### 4.3. When Bumping Spring Boot Minors

Do not read only the `jackson-databind` version. Check Spring Framework message converters, Spring Data/JPA, WebFlux codecs, Jackson modules, test helper versions, and dependency overrides. If serialized JSON changes, isolate whether the cause is the DTO code, annotations, modules, or Boot auto-configuration.

## 5. What Must a Strong JSON Contract Protect?

Assume a baseline invoice response:

~~~json
{"invoice_id":"INV-7","issued_at":"2026-01-02T03:04:05Z","amount_cents":1999,"state":"PAID"}
~~~

Changes likely to break existing clients:

| Change | Consequence |
| --- | --- |
| `invoice_id` → `invoiceId` | Client reading the old field sees missing/null |
| `amount_cents` integer → string | Type mismatch / different coercion |
| `amount_cents` → `{"cents":1999}` | Custom serializer no longer active |
| `issued_at` ISO string → epoch | Date parser / contract mismatch |
| `state` `PAID` → `PAID_FULL` | Enum parser / generated client fails |
| `state` adds `ON_HOLD` | Legacy exhaustive switch can fail |
| `memo` absent → `memo:null` | Changes null vs. absent semantics |
| price `1999` → `20` keeping type | Semantic corruption; schemas do not catch it |
| Adding non-null `memo` | Compatible with tolerant readers; breaks strict readers |
| Response `application/json` → `text/plain` | HTTP consumers fail to deserialize |
| New required request field | Older clients cannot send it |
| Error status `404` → `200` with null | Older clients branch incorrectly |
| Money `Long` → `double` | Precision/rounding loss |
| Unknown JSON property policy changes | Clients reject or silently discard fields |

**Never assume "adding a field is always backward-compatible".** If a consumer sets `FAIL_ON_UNKNOWN_PROPERTIES=true`, even a new field breaks it. Test against **the consumer versions actually supported**.

### 5.1. Frozen Fixtures Instead of Expected Output Generated by the New Mapper

A golden fixture captured from the **released contract** must be kept independent. If a test serializes the candidate DTO and uses that same output as expected, actual and expected shift together—the test stays green while the contract breaks.

### 5.2. Structural vs. Semantic Assertions

JSONPath/`JsonNode` verify keys, types, and nullability, yet they cannot tell whether `20` cents violates a `1999` cents business rule. Include concrete expected values and dedicated domain invariants.

### 5.3. JSON Object Equality and Field Order

Field order inside a JSON object usually carries no business meaning. Comparing `JsonNode` trees verifies structure independent of whitespace or property order. Conversely, **JSON arrays** are typically order-sensitive. If an API signs or hashes raw bytes, add canonicalization or byte-level tests.

## 6. `@JsonTest` and JSON Testers

In Spring Boot 3.x, `@JsonTest` creates a **JSON slice** with the mapper, serializers/modules, and JSON test helpers. It does not load business services or repositories like a full context.

~~~java
@JsonTest
class InvoiceJsonSliceTest {
    @Autowired
    JacksonTester<InvoiceDto> json;
}
~~~

Helpers:

- `JacksonTester<T>`: write/parse helper for Jackson.
- `JsonContent<T>`: result of `json.write(value)`, exposing text via `getJson()`.
- `JsonContentAssert`: AssertJ-based assertions for JSON equality and JSONPath.
- `BasicJsonTester`: JSON string assertions without requiring a DTO type.
- `GsonTester<T>`/`JsonbTester<T>`: when an app chooses Gson or JSON-B.
- `@AutoConfigureJsonTesters`: enables JSON testers inside an appropriate test context.

### 6.1. Two Types of Tests You Should Have

**Mapper test:**

~~~java
JsonNode tree = mapper.readTree(
    json.write(dto).getJson());
assertTrue(tree.path("amount_cents").isIntegralNumber());
~~~

**HTTP test:**

~~~java
mvc.perform(get("/api/v1/invoices/INV-7"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.amount_cents").value(1999));
~~~

These two snippets belong inside a test class that injects the corresponding fields; they are not two standalone Java source files.

### 6.2. Avoid `new ObjectMapper()` in Tests

~~~java
ObjectMapper adHocMapper = new ObjectMapper();
~~~

In Boot 3, this mapper can lack `JavaTimeModule` and `@JsonComponent` custom serializers. It does not reflect the mapper Spring MVC actually uses. When verifying Spring Boot behavior, inject `ObjectMapper` from `@JsonTest` or a full context.

### 6.3. JSON Testers Alone Do Not Prove Consumer Compatibility

If `JacksonTester<NewInvoiceDto>` serializes and deserializes back into `NewInvoiceDto`, both sides can drift together and the round-trip still passes. Pair it with frozen v1 fixtures and a real legacy reader.

## 7. Common Sources of Drift

### 7.1. Property Naming

Use `@JsonProperty("invoice_id")` to lock the wire name even if Java field names are refactored. If you rely on a global `snake_case` naming strategy, add tests for it and avoid changing strategies casually during refactoring.

### 7.2. Null Inclusion

`@JsonInclude(JsonInclude.Include.NON_NULL)` omits `memo` when null. Another API might promise `memo: null` is always present. Tests must distinguish an absent key from an explicit `null`.

### 7.3. Custom Money Serializer

A `Money(long cents)` record serializes by default as a nested object. Our API contract requires `amount_cents` as a JSON integer. Boot 3's `@JsonComponent` registers the serializer for `Money`. Migrating to Boot 4 requires converting custom serializers to Jackson 3 APIs and `@JacksonComponent`.

### 7.4. Java Time

For `Instant`, a mapper needs Java Time support and appropriate timestamp settings to emit an ISO string. A mapper missing the module can throw; a mapper with numeric timestamps enabled emits an epoch number. Assert both string format and exact value.

### 7.5. Enum Evolution

A new enum constant can break older clients. Do not blindly enable unknown-enum-to-null and treat it as compatible if downstream code dereferences it expecting non-null. If using an `UNKNOWN` fallback, define its semantics explicitly and test it.

### 7.6. Coercion

JSON string `"1999"` and number `1999` are not the same type. Certain Jackson configurations coerce between them; money APIs need strict policies and negative tests. The lab below uses a strict deserializer.

### 7.7. `BigDecimal`, `double`, and Precision

Money should use integer minor units or `BigDecimal` with explicit scale and rounding. Switching to `double` introduces floating-point drift. For JavaScript consumers, integers exceeding `Number.MAX_SAFE_INTEGER` also require careful wire representation design.

### 7.8. Polymorphism

Settings such as `@JsonTypeInfo`, default typing, and subtype registration can change across Jackson upgrades. Never enable permissive polymorphic deserialization on untrusted client payloads. Audit subtype allowlists, discriminators, and security advisories.

## 8. Migration: Boot 3.x → Boot 4.0 / Jackson 2 → Jackson 3

This section follows the **Spring Boot 4.0 Migration Guide** and official JSON documentation. Boot 4 examples show **the migration direction**; the runnable project below stays pinned to Boot 3.3.5.

### 8.1. Jackson 3 by Default

Spring Boot 4.0 defaults to Jackson 3 `JsonMapper`. JSON/Jackson starters provide Jackson 3. A custom Jackson 2 `ObjectMapper` bean you defined **does not automatically replace Jackson 3's `JsonMapper`** in Boot 4.

### 8.2. Relocated Packages and Group IDs

Jackson 3 generally moves to `tools.jackson`, yet Jackson annotations remain in `com.fasterxml.jackson.annotation`. Never run blind search-and-replace.

### 8.3. Annotation and Module Migrations

Boot 3 uses `@JsonComponent`/`@JsonMixin`. Boot 4 prefers explicit names `@JacksonComponent`/`@JacksonMixin`. Custom serializers/deserializers must be updated to Jackson 3 types/signatures. You cannot keep a Jackson 2 Java serializer, swap only the annotation, and expect Boot 4 to apply it.

### 8.4. Module Discovery

Per the Boot 4 migration guide, Jackson 3 auto-detects classpath modules more broadly than Boot 3. You can configure:

~~~properties
spring.jackson.find-and-add-modules=false
~~~

Use this intentionally in Boot 4 when you want tight control over discovery alongside golden contracts. Do not add properties without understanding the source of behavioral differences.

### 8.5. Defaults Closer to Jackson 2

Boot 4 provides:

~~~properties
spring.jackson.use-jackson2-defaults=true
~~~

This property brings `JsonMapper` 3 defaults closer to Boot 3's Jackson 2 behavior, **without guaranteeing byte-for-byte compatibility**. You still must verify custom modules, DTOs, HTTP converters, and clients.

### 8.6. Temporary Jackson 2 Bridge

Boot 4 offers a Jackson 2 support module:

~~~groovy
implementation 'org.springframework.boot:spring-boot-jackson2'
~~~

This module is **deprecated** and intended purely for transitional use. Jackson 2-specific properties move under the `spring.jackson2.*` namespace. When both Jackson majors are present, select the preferred mapper per HTTP stack—for example, Spring MVC/imperative clients:

~~~properties
spring.http.converters.preferred-json-mapper=jackson2
~~~

And for WebFlux/reactive codecs:

~~~properties
spring.http.codecs.preferred-json-mapper=jackson2
~~~

Do not enable both across every app blindly. This is a transitional bridge with a sunset plan, not a permanent solution.

### 8.7. JSON Testers in Boot 4

~~~text
Spring Boot 3.x:
  JacksonTester<T>  -> Jackson 2 ObjectMapper

Spring Boot 4.x:
  JacksonTester<T>  -> Jackson 3 JsonMapper
  Jackson2Tester<T> -> Jackson 2 bridge (deprecated)
~~~

Use the matching Boot 4 JSON test starter/module. Boot 4 modularizes starters and test modules; consult `spring-boot-starter-jackson`, `spring-boot-starter-jackson-test`, and your target version's docs rather than copying Boot 3 imports/dependencies blindly.

### 8.8. Changed Jackson Configuration Property Paths

Boot 4 introduces paths like `spring.jackson.json.read.*`/`spring.jackson.json.write.*`. Jackson 2 bridge settings sit under `spring.jackson2.*`. Check the migration guide and generated metadata instead of assuming Boot 3 property keys still govern Jackson 3.

### 8.9. Practical Upgrade Sequence

1. Stabilize on a supported Spring Boot 3.x baseline.
2. Save frozen fixtures for all public API versions actively used by clients.
3. Run `@JsonTest`, `MockMvc`, and real consumer tests on the baseline.
4. Read the migration guide and dependency constraints for Boot 4.
5. Upgrade Boot, Gradle, JDK, and test starters per support policy.
6. Migrate `ObjectMapper` (2) → `JsonMapper` (3), custom serializer/module code, and `@JacksonComponent`.
7. Verify migrated JSON test classes and confirm legacy DTO fixtures remain valid.
8. Run HTTP converter tests, because the JSON slice mapper is not always the exact mapper serving responses.
9. If temporarily using the Jackson 2 bridge, document which transport uses which mapper and plan bridge removal.
10. Run schema diffs, semantic assertions, staging/canary validation, and verify rollback readiness.

## 9. Runnable Project: Java 17, Spring Boot 3.3.5, Gradle

This lab is designed to run **strictly on Boot 3.3.5/Jackson 2**. Boot 4 requires migrating the source before running. There are no Docker, database, or external HTTP dependencies.

### 9.1. Directory Structure

~~~text
jackson-contract-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/jsonlab/
    │   ├── JsonLabApplication.java
    │   ├── domain/Money.java
    │   ├── domain/InvoiceState.java
    │   ├── api/InvoiceDto.java
    │   ├── api/CreateInvoiceRequest.java
    │   ├── api/InvoiceService.java
    │   ├── api/InvoiceController.java
    │   ├── api/InvoiceNotFoundException.java
    │   ├── api/InvoiceErrorHandler.java
    │   ├── json/MoneyJsonComponent.java
    │   └── consumer/LegacyInvoiceV1.java
    └── test/
        ├── resources/contracts/
        │   ├── invoice-v1.json
        │   ├── invoice-v2-additive.json
        │   ├── invoice-breaking-rename.json
        │   ├── invoice-breaking-units.json
        │   ├── invoice-breaking-enum.json
        │   └── invoice-breaking-null.json
        └── java/com/example/jsonlab/
            ├── InvoiceJsonTest.java
            ├── InvoiceMvcTest.java
            ├── InvoiceFullContextTest.java
            └── MapperWiringTest.java
~~~

Wrapper scripts/JARs are generated by Gradle or taken from your repository; you cannot create the binary `gradle-wrapper.jar` by copying Markdown.

### 9.2. `settings.gradle`

~~~groovy
rootProject.name = 'jackson-contract-lab'
~~~

### 9.3. `build.gradle`

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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

The Boot BOM dependency management selects compatible Jackson 2 core/databind/module versions. `spring-boot-starter-web` provides Jackson and HTTP converters; `starter-validation` brings Jakarta Bean Validation for request body checks. `starter-test` includes JUnit Jupiter, MockMvc, and JSON tester support.

### 9.4. `JsonLabApplication.java`

~~~java
package com.example.jsonlab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(JsonLabApplication.class, args);
    }
}
~~~

### 9.5. `domain/Money.java`

~~~java
package com.example.jsonlab.domain;

public record Money(long cents) {

    public Money {
        if (cents < 0L) {
            throw new IllegalArgumentException(
                "amount_cents must be nonnegative");
        }
    }
}
~~~

### 9.6. `domain/InvoiceState.java`

~~~java
package com.example.jsonlab.domain;

public enum InvoiceState {
    OPEN,
    PAID
}
~~~

### 9.7. `api/InvoiceDto.java`

~~~java
package com.example.jsonlab.api;

import java.time.Instant;
import com.example.jsonlab.domain.Money;
import com.example.jsonlab.domain.InvoiceState;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record InvoiceDto(
    @JsonProperty("invoice_id")
    String invoiceId,
    @JsonProperty("issued_at")
    Instant issuedAt,
    @JsonProperty("amount_cents")
    Money amount,
    @JsonProperty("state")
    InvoiceState state,
    @JsonProperty("memo")
    String memo) {
}
~~~

`@JsonProperty` preserves `snake_case` even if Java record fields are refactored. `@JsonInclude(NON_NULL)` ensures `memo` is omitted when null.

### 9.8. `api/CreateInvoiceRequest.java`

~~~java
package com.example.jsonlab.api;

import com.example.jsonlab.domain.Money;
import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record CreateInvoiceRequest(
    @JsonProperty("invoice_id")
    @NotBlank String invoiceId,
    @JsonProperty("amount_cents")
    @NotNull Money amount,
    @JsonProperty("memo")
    String memo) {
}
~~~

`memo` is optional so older requests omitting it remain valid. The money field is deserialized by the custom deserializer enforcing a JSON integer.

### 9.9. `api/InvoiceService.java`

~~~java
package com.example.jsonlab.api;

import java.time.Instant;

import com.example.jsonlab.domain.InvoiceState;
import com.example.jsonlab.domain.Money;

import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    private static final Instant ISSUED_AT =
        Instant.parse("2026-01-02T03:04:05Z");

    public InvoiceDto find(String id) {
        if (!"INV-7".equals(id)) {
            throw new InvoiceNotFoundException(id);
        }
        return new InvoiceDto(
            "INV-7", ISSUED_AT,
            new Money(1999L), InvoiceState.PAID, null);
    }

    public InvoiceDto create(CreateInvoiceRequest request) {
        return new InvoiceDto(
            request.invoiceId(), ISSUED_AT,
            request.amount(), InvoiceState.OPEN,
            request.memo());
    }
}
~~~

Fixed data keeps tests deterministic. This is a demo service, not production persistence or monetary logic.

### 9.10. `api/InvoiceNotFoundException.java`

~~~java
package com.example.jsonlab.api;

public class InvoiceNotFoundException
        extends RuntimeException {

    public InvoiceNotFoundException(String id) {
        super("Invoice not found: " + id);
    }
}
~~~

### 9.11. `api/InvoiceController.java`

~~~java
package com.example.jsonlab.api;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/invoices")
public class InvoiceController {

    private final InvoiceService service;

    public InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping(
        value = "/{id}",
        produces = MediaType.APPLICATION_JSON_VALUE)
    public InvoiceDto find(
            @PathVariable("id") String id) {
        return service.find(id);
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    public InvoiceDto create(
            @Valid @RequestBody CreateInvoiceRequest request) {
        return service.create(request);
    }
}
~~~

### 9.12. `api/InvoiceErrorHandler.java`

~~~java
package com.example.jsonlab.api;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InvoiceErrorHandler {

    @ExceptionHandler(InvoiceNotFoundException.class)
    public ResponseEntity<ApiError> missing() {
        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body(new ApiError("INVOICE_NOT_FOUND"));
    }

    public record ApiError(String code) {
    }
}
~~~

### 9.13. `json/MoneyJsonComponent.java`

~~~java
package com.example.jsonlab.json;

import java.io.IOException;

import com.example.jsonlab.domain.Money;
import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonToken;
import com.fasterxml.jackson.databind.DeserializationContext;
import com.fasterxml.jackson.databind.JsonDeserializer;
import com.fasterxml.jackson.databind.JsonMappingException;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;

import org.springframework.boot.jackson.JsonComponent;

@JsonComponent
public class MoneyJsonComponent {

    public static class Serializer
            extends JsonSerializer<Money> {

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers)
                throws IOException {

            generator.writeNumber(value.cents());
        }
    }

    public static class Deserializer
            extends JsonDeserializer<Money> {

        @Override
        public Money deserialize(
                JsonParser parser,
                DeserializationContext context)
                throws IOException {

            if (parser.currentToken()
                    != JsonToken.VALUE_NUMBER_INT) {
                throw JsonMappingException.from(
                    parser,
                    "amount_cents must be JSON integer");
            }

            return new Money(parser.getLongValue());
        }
    }
}
~~~

**Explanation:** The serializer writes `Money` as a JSON number, and the deserializer accepts **only an integer number token** without coercing `"1999"` from a string. If this component/module is dropped, the value object serializes as `{"cents":1999}`, and both JSON and MVC tests catch it.

### 9.14. `consumer/LegacyInvoiceV1.java`

~~~java
package com.example.jsonlab.consumer;

import java.time.Instant;

import com.example.jsonlab.domain.InvoiceState;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

@JsonIgnoreProperties(ignoreUnknown = true)
public record LegacyInvoiceV1(
    @JsonProperty("invoice_id")
    String invoiceId,
    @JsonProperty("issued_at")
    Instant issuedAt,
    @JsonProperty("amount_cents")
    Long amountCents,
    @JsonProperty("state")
    InvoiceState state) {

    public LegacyInvoiceV1 {
        if (invoiceId == null || invoiceId.isBlank()
                || issuedAt == null
                || amountCents == null
                || amountCents < 0L
                || state == null) {
            throw new IllegalArgumentException(
                "Invalid legacy invoice contract");
        }
    }
}
~~~

This older client intentionally ignores unknown JSON fields yet fails fast if old fields are removed or null. `Long` avoids a missing amount silently turning into `0`. Adding a new enum constant still fails; `ignoreUnknown` does not apply to unknown enum constants.

## 10. Six Golden JSON Fixtures

All reside under `src/test/resources/contracts/`. Never generate expected JSON from the candidate mapper at runtime.

### `invoice-v1.json`

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "PAID"
}
~~~

### `invoice-v2-additive.json`

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "PAID",
  "memo": "Paid in full"
}
~~~

### `invoice-breaking-rename.json`

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_minor_units": 1999,
  "state": "PAID"
}
~~~

### `invoice-breaking-units.json`

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 20,
  "state": "PAID"
}
~~~

### `invoice-breaking-enum.json`

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": 1999,
  "state": "ON_HOLD"
}
~~~

### `invoice-breaking-null.json`

~~~json
{
  "invoice_id": "INV-7",
  "issued_at": "2026-01-02T03:04:05Z",
  "amount_cents": null,
  "state": "PAID"
}
~~~

The "breaking" fixtures only demonstrate how incompatibilities are caught. An `assertThrows` test passing when it rejects incompatible data **does not mean** a real provider returning that breaking response is compatible. Candidate providers must be tested with positive contract assertions separately.

## 11. `InvoiceJsonTest`: Testing the Spring Boot Mapper

**`src/test/java/com/example/jsonlab/InvoiceJsonTest.java`**

~~~java
package com.example.jsonlab;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;

import com.example.jsonlab.api.InvoiceDto;
import com.example.jsonlab.api.InvoiceService;
import com.example.jsonlab.consumer.LegacyInvoiceV1;
import com.example.jsonlab.domain.InvoiceState;
import com.example.jsonlab.domain.Money;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;
import org.springframework.context.ApplicationContext;
import org.springframework.core.io.ClassPathResource;

import static org.junit.jupiter.api.Assertions.*;

@JsonTest
class InvoiceJsonTest {

    @Autowired
    JacksonTester<InvoiceDto> json;

    @Autowired
    ObjectMapper mapper;

    @Autowired
    ApplicationContext context;

    private static InvoiceDto sample(String memo) {
        return new InvoiceDto(
            "INV-7",
            Instant.parse("2026-01-02T03:04:05Z"),
            new Money(1999L),
            InvoiceState.PAID,
            memo);
    }

    private static String fixture(String name)
            throws IOException {

        try (InputStream input =
            new ClassPathResource(
                "contracts/" + name).getInputStream()) {

            return new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8);
        }
    }

    public record StrictInvoice(
        @JsonProperty("invoice_id")
        String invoiceId,
        @JsonProperty("issued_at")
        Instant issuedAt,
        @JsonProperty("amount_cents")
        Long amountCents,
        @JsonProperty("state")
        InvoiceState state) {
    }

    @Test
    void baselineMatchesFrozenWireContract()
            throws Exception {
        JsonNode expected = mapper.readTree(
            fixture("invoice-v1.json"));
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());

        assertEquals(expected, actual);
    }

    @Test
    void absentMemoIsNotRenderedAsNull()
            throws Exception {
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());
        assertFalse(actual.has("memo"));
    }

    @Test
    void additiveMemoRetainsOriginalFields()
            throws Exception {
        JsonNode expected = mapper.readTree(
            fixture("invoice-v2-additive.json"));
        JsonNode actual = mapper.readTree(
            json.write(sample("Paid in full")).getJson());
        assertEquals(expected, actual);
    }

    @Test
    void customMoneySerializerWritesInteger()
            throws Exception {
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());
        assertTrue(
            actual.path("amount_cents").isIntegralNumber());
        assertEquals(1999L,
            actual.path("amount_cents").longValue());
    }

    @Test
    void instantIsIsoText()
            throws Exception {
        JsonNode actual = mapper.readTree(
            json.write(sample(null)).getJson());
        assertTrue(actual.path("issued_at").isTextual());
        assertEquals(
            "2026-01-02T03:04:05Z",
            actual.path("issued_at").textValue());
    }

    @Test
    void jacksonTesterParsesOriginalFixture()
            throws Exception {
        InvoiceDto result = json.parseObject(
            fixture("invoice-v1.json"));
        assertEquals(sample(null), result);
    }

    @Test
    void tolerantOldReaderAcceptsAddedField()
            throws Exception {
        LegacyInvoiceV1 result = mapper.readValue(
            fixture("invoice-v2-additive.json"),
            LegacyInvoiceV1.class);

        assertEquals("INV-7", result.invoiceId());
        assertEquals(1999L,
            result.amountCents().longValue());
        assertEquals(InvoiceState.PAID, result.state());
    }

    @Test
    void strictOldReaderRejectsAddedField()
            throws Exception {
        ObjectMapper strict = mapper.copy().configure(
            DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
            true);

        assertThrows(
            JsonProcessingException.class,
            () -> strict.readValue(
                fixture("invoice-v2-additive.json"),
                StrictInvoice.class));
    }

    @Test
    void renamedMoneyFieldBreaksLegacy()
            throws Exception {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                fixture("invoice-breaking-rename.json"),
                LegacyInvoiceV1.class));
    }

    @Test
    void unknownEnumBreaksLegacy()
            throws Exception {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                fixture("invoice-breaking-enum.json"),
                LegacyInvoiceV1.class));
    }

    @Test
    void missingRequiredMoneyFailsFast()
            throws Exception {
        assertThrows(
            JsonProcessingException.class,
            () -> mapper.readValue(
                fixture("invoice-breaking-null.json"),
                LegacyInvoiceV1.class));
    }

    @Test
    void semanticUnitChangeStillParses()
            throws Exception {
        LegacyInvoiceV1 result = mapper.readValue(
            fixture("invoice-breaking-units.json"),
            LegacyInvoiceV1.class);

        assertEquals(20L,
            result.amountCents().longValue());
        assertNotEquals(1999L,
            result.amountCents().longValue());
    }

    @Test
    void jsonSliceDoesNotLoadBusinessService() {
        assertEquals(0,
            context.getBeanNamesForType(
                InvoiceService.class).length);
    }
}
~~~

### Meaning of the 13 Test Methods

- Baseline JSON tree equality catches field/type/date/enum/null policy drift.
- Money serialization verifies the custom `@JsonComponent` is active.
- `JacksonTester` parsing the fixture verifies reverse deserialization, not just serialization.
- Legacy tolerant/strict tests distinguish unknown-field policies.
- Renames, unknown enums, and null amounts are tested as intentional failures.
- Semantic `amount=20` demonstrates that **parsers do not catch business-value corruption**.
- The JSON slice asserts the business service is not loaded, keeping the test fast and properly scoped.

### Using JsonContent/AssertJ

`json.write(value)` returns `JsonContent<T>` with `getJson()`. In Boot 3.x, inside a test method that already has `json` and `sample`, you can write:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

assertThat(json.write(sample(null)))
    .hasJsonPathNumberValue("@.amount_cents");
~~~

This is a **snippet inside a test class**, not a complete Java file. `JacksonTester` also supports assertions via `JsonContentAssert`. For fixtures in a custom resource path, the lab uses `ClassPathResource`/`JsonNode` to avoid relative resource naming ambiguity and JSON object key-order sensitivity.

## 12. `InvoiceMvcTest`: Testing HTTP Conversion

**`src/test/java/com/example/jsonlab/InvoiceMvcTest.java`**

~~~java
package com.example.jsonlab;

import java.time.Instant;

import com.example.jsonlab.api.CreateInvoiceRequest;
import com.example.jsonlab.api.InvoiceController;
import com.example.jsonlab.api.InvoiceDto;
import com.example.jsonlab.api.InvoiceNotFoundException;
import com.example.jsonlab.api.InvoiceService;
import com.example.jsonlab.domain.InvoiceState;
import com.example.jsonlab.domain.Money;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(InvoiceController.class)
class InvoiceMvcTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    InvoiceService service;

    private static InvoiceDto sample(String memo) {
        return new InvoiceDto(
            "INV-7",
            Instant.parse("2026-01-02T03:04:05Z"),
            new Money(1999L),
            InvoiceState.PAID,
            memo);
    }

    @Test
    void httpGetPreservesOriginalContract()
            throws Exception {

        when(service.find("INV-7"))
            .thenReturn(sample(null));

        mvc.perform(get("/api/v1/invoices/INV-7")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(content()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.invoice_id")
                .value("INV-7"))
            .andExpect(jsonPath("$.issued_at")
                .value("2026-01-02T03:04:05Z"))
            .andExpect(jsonPath("$.amount_cents")
                .isNumber())
            .andExpect(jsonPath("$.amount_cents")
                .value(1999))
            .andExpect(jsonPath("$.state")
                .value("PAID"))
            .andExpect(jsonPath("$.memo")
                .doesNotExist());

        verify(service).find("INV-7");
    }

    @Test
    void httpGetAllowsAdditiveMemo()
            throws Exception {
        when(service.find("INV-7"))
            .thenReturn(sample("Paid in full"));

        mvc.perform(get("/api/v1/invoices/INV-7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.amount_cents")
                .value(1999))
            .andExpect(jsonPath("$.memo")
                .value("Paid in full"));
    }

    @Test
    void http404KeepsErrorCode()
            throws Exception {
        when(service.find("UNKNOWN"))
            .thenThrow(
                new InvoiceNotFoundException("UNKNOWN"));

        mvc.perform(get("/api/v1/invoices/UNKNOWN"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("INVOICE_NOT_FOUND"));
    }

    @Test
    void oldPostWithoutMemoIsStillAccepted()
            throws Exception {
        when(service.create(any(CreateInvoiceRequest.class)))
            .thenReturn(sample(null));

        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":1999}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.amount_cents")
                .value(1999));

        ArgumentCaptor<CreateInvoiceRequest> captor =
            ArgumentCaptor.forClass(
                CreateInvoiceRequest.class);

        verify(service).create(captor.capture());
        assertEquals("INV-9",
            captor.getValue().invoiceId());
        assertEquals(new Money(1999L),
            captor.getValue().amount());
        assertNull(captor.getValue().memo());
    }

    @Test
    void newPostMayHaveOptionalMemo()
            throws Exception {
        when(service.create(any(CreateInvoiceRequest.class)))
            .thenReturn(sample("Gift"));

        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":1999,"
                    + "\"memo\":\"Gift\"}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.memo")
                .value("Gift"));

        ArgumentCaptor<CreateInvoiceRequest> captor =
            ArgumentCaptor.forClass(
                CreateInvoiceRequest.class);

        verify(service).create(captor.capture());
        assertEquals("Gift",
            captor.getValue().memo());
    }

    @Test
    void quotedAmountIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":\"1999\"}"))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void missingAmountIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"invoice_id\":\"INV-9\"}"))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }

    @Test
    void negativeAmountIsRejectedBeforeService()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":-1}"))
            .andExpect(status().isBadRequest());
        verifyNoInteractions(service);
    }
}
~~~

### Why Use MockMvc If You Already Have `@JsonTest`?

`@JsonTest` can pass while the MVC message converter in the app uses a different custom mapper or content negotiation setup. `@WebMvcTest` protects Spring MVC routing, status codes, media types, and serialization. `verifyNoInteractions(service)` ensures malformed requests never reach business execution.

## 13. `InvoiceFullContextTest`: Real Application Wiring

**`src/test/java/com/example/jsonlab/InvoiceFullContextTest.java`**

~~~java
package com.example.jsonlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(classes = JsonLabApplication.class)
@AutoConfigureMockMvc
class InvoiceFullContextTest {

    @Autowired
    MockMvc mvc;

    @Test
    void fullAppUsesCorrectMapperAndSerializer()
            throws Exception {
        mvc.perform(get("/api/v1/invoices/INV-7"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.invoice_id")
                .value("INV-7"))
            .andExpect(jsonPath("$.issued_at")
                .value("2026-01-02T03:04:05Z"))
            .andExpect(jsonPath("$.amount_cents")
                .value(1999))
            .andExpect(jsonPath("$.memo")
                .doesNotExist());
    }

    @Test
    void fullAppStillReturns404ForUnknownInvoice()
            throws Exception {
        mvc.perform(get("/api/v1/invoices/UNKNOWN"))
            .andExpect(status().isNotFound())
            .andExpect(jsonPath("$.code")
                .value("INVOICE_NOT_FOUND"));
    }

    @Test
    void fullAppAcceptsOldPostRequest()
            throws Exception {
        mvc.perform(post("/api/v1/invoices")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"invoice_id\":\"INV-9\","
                    + "\"amount_cents\":2500}"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.invoice_id")
                .value("INV-9"))
            .andExpect(jsonPath("$.amount_cents")
                .value(2500))
            .andExpect(jsonPath("$.state")
                .value("OPEN"));
    }
}
~~~

The full-context test uses the real `InvoiceService` and real `MoneyJsonComponent`. No DB or network is needed because the demo service is deterministic. `MockMvc` opens no sockets; if proxies, TLS, or streaming need testing, add a separate random-port HTTP smoke test.

## 14. `MapperWiringTest`: Inspecting the Real Jackson Runtime

**`src/test/java/com/example/jsonlab/MapperWiringTest.java`**

~~~java
package com.example.jsonlab;

import java.time.Instant;
import com.example.jsonlab.api.InvoiceDto;
import com.example.jsonlab.domain.Money;
import com.example.jsonlab.domain.InvoiceState;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(classes = JsonLabApplication.class)
class MapperWiringTest {

    @Autowired
    ObjectMapper mapper;

    @Test
    void boot3RuntimeStillUsesJackson2() {
        assertEquals(
            2, mapper.version().getMajorVersion());
    }

    @Test
    void mapperHasJavaTimeAndMoneySupport()
            throws Exception {

        InvoiceDto dto = new InvoiceDto(
            "INV-7",
            Instant.parse("2026-01-02T03:04:05Z"),
            new Money(1999L),
            InvoiceState.PAID,
            null);

        JsonNode json = mapper.readTree(
            mapper.writeValueAsString(dto));

        assertTrue(json.path("amount_cents")
            .isIntegralNumber());
        assertEquals(1999L,
            json.path("amount_cents").longValue());
        assertEquals("2026-01-02T03:04:05Z",
            json.path("issued_at").asText());
    }
}
~~~

The first method is **only valid for the Boot 3/Jackson 2 baseline**. After migrating to Boot 4, update the test to Jackson 3 `JsonMapper` and the matching major-version assertion; never keep Jackson 2 `ObjectMapper` injection and treat it as verifying default Jackson 3.

## 15. Summary of Test Coverage and Run Commands

| Class | `@Test` Methods | Role |
| --- | ---: | --- |
| `InvoiceJsonTest` | 13 | JSON fixtures, `JacksonTester`, legacy clients, dates/money/enums |
| `InvoiceMvcTest` | 8 | MVC converter, request validation, status, JSON |
| `InvoiceFullContextTest` | 3 | Real service + application mapper wiring |
| `MapperWiringTest` | 2 | Jackson version and modules in full context |
| **Total** | **26** | Multi-layer contract regression tests |

Run command:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If the project does not yet have a Gradle Wrapper and a compatible Gradle is installed:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Run a single JSON group when triaging:

~~~bash
./gradlew test --tests 'com.example.jsonlab.InvoiceJsonTest'
./gradlew test --tests 'com.example.jsonlab.InvoiceMvcTest'
./gradlew test --tests 'com.example.jsonlab.InvoiceFullContextTest'
./gradlew test --tests 'com.example.jsonlab.MapperWiringTest'
~~~

Force the test task to re-run:

~~~bash
./gradlew test --rerun-tasks --stacktrace
~~~

Reports after execution are typically written to:

~~~text
build/reports/tests/test/index.html
build/test-results/test/TEST-com.example.jsonlab.InvoiceJsonTest.xml
build/test-results/test/TEST-com.example.jsonlab.InvoiceMvcTest.xml
build/test-results/test/TEST-com.example.jsonlab.InvoiceFullContextTest.xml
build/test-results/test/TEST-com.example.jsonlab.MapperWiringTest.xml
~~~

**Expected:** 26 JUnit methods discovered and passing if all sources, fixtures, dependencies, and JDK align. This is **projected from the source code**; **Gradle/JUnit was not executed while authoring this lesson**. Never fabricate "BUILD SUCCESSFUL" or execution timings. Negative fixtures pass when assertions catch breaking JSON as designed.

## 16. Common Errors After Upgrading Jackson

### 16.1. `NoClassDefFoundError`

If a dependency still expects Jackson 2 while runtime only has Jackson 3, you may see:

~~~text
NoClassDefFoundError: com/fasterxml/jackson/databind/ObjectMapper
~~~

Inspect the resolved classpath and un-upgraded libraries. Boot 4 provides a temporary Jackson 2 bridge, yet you must plan the migration rather than assuming permanent Jackson 2 support.

### 16.2. `NoSuchMethodError`

If Jackson core, databind, and datatype modules are incompatible, runtime fails with linkage errors:

~~~text
java.lang.NoSuchMethodError: ... Jackson API ...
~~~

Diagnose with `dependencyInsight` and the BOM. Never "fix" linkage errors with `@JsonIgnoreProperties` or loosened JSON assertions.

### 16.3. Missing `JavaTimeModule`

An ad-hoc `new ObjectMapper()` can lack `JavaTimeModule` and fail to serialize `Instant`. The Boot auto-configured mapper includes the proper modules and defaults. Tests should inject the real mapper, or if the app deliberately constructs its own mapper, configure its modules explicitly.

### 16.4. `JacksonTester` Fails to Inject

Check `@JsonTest`, the test starter, the JSON mapper on the classpath, the generic type, and which Jackson 2/Jackson 3 tester API is in use. In Boot 4, `JacksonTester` targets Jackson 3 by default, while `Jackson2Tester` is the deprecated bridge. Do not pull all production configs into the slice just to inject a tester.

### 16.5. `@JsonComponent` Is No Longer Registered

If `Money` serializes as `{"cents":1999}`, check component scanning, self-created mappers, overridden modules, or an incomplete Jackson 3 migration. Run both `@JsonTest` and `MockMvc` to pinpoint which boundary is affected.

### 16.6. JSON Slice Passes While HTTP Fails

Spring MVC converters may be using a different mapper due to a custom bean/config or Boot 4's `preferred-json-mapper`. Inspect the converter registry, `MappingJackson2HttpMessageConverter`/Jackson 3 equivalents, and wiring. Never infer HTTP converter behavior from the JSON slice alone.

### 16.7. Enum Parsing Fails

If a provider adds `ON_HOLD`, a legacy Java enum does not recognize that constant. Design an explicit `UNKNOWN` fallback or contract version; a fallback is valid only if downstream handles its semantics properly. Never silently turn errors into null.

### 16.8. Null Turns Into `0`

If a client uses primitive `long` and the field is missing, Jackson can default to `0` depending on settings. `LegacyInvoiceV1` uses boxed `Long` and constructor validation to fail fast. For payments, silent corruption must be caught by domain assertions.

### 16.9. JSON Equality Too Strict or Too Loose

Whole-object snapshots reject additive fields even for tolerant consumers; a key-only assertion misses type changes. Choose **provider contracts** and **consumer contracts** deliberately while protecting required fields and values.

### 16.10. Testing Only DTO Round-Trips

`NewDto` serialize→deserialize can pass when both serializer and deserializer shift together. Only frozen fixtures and legacy consumer tests reveal real backward compatibility.

## 17. CI Strategy When Upgrading Boot/Jackson

A sound pipeline separates two stages:

~~~text
Baseline Boot 3 source + frozen released JSON fixtures
    |
    +-- @JsonTest
    +-- @WebMvcTest
    +-- @SpringBootTest
    +-- legacy consumer fixture tests
    |
    v
Record baseline contract + test evidence
    |
    v
Candidate Boot 4 source with migrated APIs/imports/dependencies
    |
    +-- equivalent JSON tests using Jackson 3
    +-- same frozen fixtures and legacy client interactions
    +-- HTTP converter tests
    +-- schema/semantic validations
    |
    v
PASS -> staging/canary
FAIL -> fix candidate or versioned migration
~~~

**Do not build a fake matrix** by bumping the Spring Boot plugin version from 3.3.5 to 4.0 on the exact same Jackson 2 code and calling all compiler errors "Jackson breaking changes". Boot 4 migration requires intentional API and test-module updates. However, **released wire contracts** must not change silently.

### 17.1. What Should CI Artifacts Retain?

- Git commits and baseline/candidate IDs.
- JDK, Gradle Wrapper, Spring Boot, and Jackson resolved versions.
- Test counts (`passed`/`failed`/`skipped`) from JUnit XML.
- Golden fixture versions and consumer owners.
- JSON diffs across fields/types/values on failure.
- HTTP method, path, status, and media type of failing interactions.
- `dependencyInsight` outputs or SBOMs for releases.
- Zero tokens, PII, or credentials inside fixtures or logs.

### 17.2. Running the Baseline on GitHub Actions

Illustrative workflow snippet for a Boot 3 source with a committed Wrapper:

~~~yaml
name: json-contract-tests

on:
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  json-contract:
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v4
      - name: Execute JSON contract tests
        run: ./gradlew test --rerun-tasks
      - name: Upload JUnit reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: boot3-json-contracts
          path: |
            build/reports/tests/test/
            build/test-results/test/
          if-no-files-found: ignore
~~~

GitHub Actions versions in this snippet are illustrative, not a recommendation to blindly use `latest`; pin audited commit SHAs per your supply-chain policy. A Boot 4 candidate requires source/test migration and its own workflow or candidate branch job.

### 17.3. Never Mask Failures by Regenerating Fixtures

If Jackson 3 serializes JSON differently, analyze **real compatibility**. If it is breaking, preserve the v1 endpoint or introduce a new alias/version; never regenerate expected v1 fixtures in the same commit just to turn the suite green. Any waiver must record an owner, consumer impact, migration path, and sunset date.

## 18. Mutation Tests: Proving Tests Turn Red When Contracts Break

| Sandbox Branch Mutation | Detecting Test |
| --- | --- |
| Delete `MoneyJsonComponent` | JSON money number/baseline tests, `MockMvc` |
| Change `@JsonProperty` `invoice_id` → `invoiceId` | Frozen JSON + MVC |
| Remove `@JsonInclude(NON_NULL)` | Absent `memo` + frozen baseline |
| Switch JavaTime serializer to epoch numbers | `Instant` string + MVC |
| Allow string `"1999"` instead of integer | Invalid POST test |
| Remove `@NotNull` on request amount | Missing amount POST test |
| Add enum state unknown to legacy client | Legacy enum negative test |
| Rename `amount_cents` to `amount_minor_units` | Legacy missing amount test |
| Change `amount_cents = 1999` to `20` | Business value assertions |
| Change `Content-Type` to `text/plain` | MVC content-type assertion |
| Change missing resource from `404` to `200` | Error contract tests |
| Register an ad-hoc mapper in `@Configuration` | Full mapper/MVC tests |
| Alter Boot BOM causing mismatched Jackson modules | `dependencyInsight` + runtime tests |
| Update fixtures to match new output | Never treat as a fix; review consumer contract |

No single mutation is caught by all four test classes: that is why complementary boundaries are necessary. If a mutation breaks clients while all tests remain green, add coverage.

## 19. Hands-On Exercises

**A.** Run the lab on Java 17/Boot 3.3.5, inspect the 26-test report and `InvoiceDto` JSON output.

**B.** Remove `@JsonComponent` so `Money` becomes a nested object; observe the tests fail.

**C.** Remove `@JsonProperty("invoice_id")` and see how the JSON field name changes.

**D.** Remove `@JsonInclude(NON_NULL)` and observe `memo: null` appear.

**E.** Instantiate a standalone `new ObjectMapper()` and compare Java Time and serializer behavior against the injected mapper.

**F.** Switch `Instant` to numeric timestamps in a sandbox while protecting the ISO-string public contract.

**G.** Allow the deserializer to accept a string amount; watch the negative HTTP request test fail.

**H.** Test the additive `memo` field with the strict legacy reader vs. the tolerant reader.

**I.** Send the fixture containing unknown enum `ON_HOLD` to the legacy DTO; design a fallback policy.

**J.** Send a null amount and observe boxed `Long` + constructor validation failing fast.

**K.** Keep the number type while changing the amount value `1999` → `20`; distinguish parse correctness from business semantics.

**L.** Run `dependencyInsight` for Jackson `databind`/`core`/`jsr310` and record the resolved versions.

**M.** Introduce an intentional version mismatch override in a sandbox to study linkage errors; do not merge the override.

**N.** Read the Boot 4 Migration Guide and list the custom serializer imports requiring Jackson 3 updates.

**O.** On a separate branch, migrate `@JsonComponent` to `@JacksonComponent` + Jackson 3 types and write matching tests.

**P.** If using the bridge, configure `spring-boot-jackson2` and the preferred MVC converter; verify HTTP JSON matches baseline.

**Q.** Experiment with `spring.jackson.use-jackson2-defaults` on a Boot 4 candidate and compare JSON snapshots without assuming full parity.

**R.** Generate an OpenAPI schema diff and check fixture types and nullability.

**S.** Add a `RANDOM_PORT` live HTTP smoke test and run a legacy `RestClient` if your project has clients outside Spring context.

**T.** Prepare a canary/rollback plan for when a JSON contract must be versioned.

## 20. Serialization Upgrade Testing Checklist

- [ ] Know the exact Spring Boot version, Jackson major, JDK, and Gradle Wrapper in use?
- [ ] Consulted vendor release/migration notes for the exact branch?
- [ ] Are Jackson core, databind, and datatype modules managed in lockstep?
- [ ] Avoided accidentally pinning a single Jackson module outside the BOM?
- [ ] Audited third-party libraries that do not yet support Jackson 3?
- [ ] Have golden JSON fixtures of the released contract?
- [ ] Does `@JsonTest` use the right mapper/tester for the Boot version?
- [ ] Avoided using `new ObjectMapper()` in place of the Spring-managed mapper without justification?
- [ ] Is your custom `@JsonComponent` or `@JacksonComponent` actually registered?
- [ ] Are null/absent fields, enums, dates, numbers, and field names asserted?
- [ ] Are money fields asserted to be JSON integers, not strings or nested objects?
- [ ] Are semantic assertions in place for cents, currency, and timezone?
- [ ] Are both tolerant and strict legacy consumer tests present where needed?
- [ ] Are both `JacksonTester` write and parse tested, not just DTO round-trips?
- [ ] Are `MockMvc`/HTTP converter tests covering public APIs?
- [ ] Are full-context tests verifying custom mappers, profiles, and wiring?
- [ ] Does a v1 request omitting new optional fields still succeed?
- [ ] Does malformed JSON get rejected before reaching the business service?
- [ ] Are error status codes, bodies, and content types protected?
- [ ] Does the Boot 4 candidate use `JsonMapper`/Jackson 3 with the right imports and modules?
- [ ] Are annotation package exceptions handled properly?
- [ ] If using the Jackson 2 bridge, is the deprecation and sunset plan documented?
- [ ] Is the preferred JSON mapper configured per MVC/WebFlux transport?
- [ ] Are module discovery, coercion, and changed property paths tested?
- [ ] Does CI actually run the tests and archive JUnit reports (not just `UP-TO-DATE`)?
- [ ] Are golden fixtures never auto-regenerated from candidate outputs?
- [ ] Are public JSON snapshots free of PII and secrets?
- [ ] Are contract diffs and a release/rollback plan ready if breaking?
- [ ] Are negative fixtures never mistaken for proof of provider compatibility?

## 21. Official Documentation

- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): `ObjectMapper`, Jackson 2, `@JsonComponent`, module auto-config.
- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@JsonTest`/`JacksonTester` and test slices.
- [Spring Boot 3.3 — JacksonTester API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/json/JacksonTester.html).
- [Spring Boot 4.0 — JSON](https://docs.spring.io/spring-boot/4.0/reference/features/json.html): Jackson 3 default, Jackson 2 bridge, preferred mapper properties.
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): group/package migrations, modules, `@JacksonComponent`, starters.
- [Spring Boot 4.0 — Testing](https://docs.spring.io/spring-boot/4.0/reference/testing/spring-boot-applications.html): JSON test slice, Jackson 3, and deprecated Jackson 2 support.
- [Spring Framework — HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html).
- [Jackson 3 Migration Guide](https://github.com/FasterXML/jackson/wiki/Jackson-Release-3.0).
- [Gradle — Dependency Reports](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.10.2/user-guide/).
- [RFC 8259 — JSON](https://www.rfc-editor.org/rfc/rfc8259).
- [RFC 3339 — Timestamps](https://www.rfc-editor.org/rfc/rfc3339).

**Remember:** whenever you change Jackson, JSON testers, or serialization dependencies, verify the **wire JSON actually received by clients**, not just whether new DTOs compile and deserialize. Spring Boot 3.x uses Jackson 2 `ObjectMapper`/`JacksonTester`; Spring Boot 4.0 prefers Jackson 3 `JsonMapper`, with a deprecated bridge for Jackson 2. Combine frozen fixtures, `@JsonTest`, `MockMvc`, full-context wiring, and legacy consumer assertions to protect backward compatibility. Any contract-breaking change must be versioned and explicitly migrated.
