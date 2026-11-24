# JSON and Serialization in Spring Boot: Naming Strategy, Nulls, Enums, and Date/Time Formatting

## 1. Why are these four issues a single API contract?

In many Java systems, internal objects use camelCase, enums by constant name, and `java.time` types. Yet JSON returned to frontends/partners may use snake_case field names, omit null fields, publish lowercase enum codes, and require timestamps with offsets. Consider a Java record:

```java
record BookingEvent(
        String bookingId,
        String customerName,
        DeliveryState state,
        LocalDate travelDate,
        OffsetDateTime createdAt,
        String optionalNote) {}
```

It may need to produce JSON per the **wire contract**:

```json
{
  "booking_id": "B-42",
  "customer_name": "Mai",
  "state": "queued",
  "travel_date": "08/11/2026",
  "created_at": "2026-11-08T09:30:00+07:00"
}
```

The `optional_note` field is omitted because its Java value is `null`. Enum `DeliveryState.QUEUED` outputs `"queued"` instead of the constant name `"QUEUED"`. `LocalDate` uses the contracted date format; `OffsetDateTime` keeps the `+07:00` offset so receivers do not guess the timezone.

If you only test services using `assertEquals` on Java objects, **you have not tested the JSON real clients receive**. This lesson identifies the Jackson choices and shows how to write tests that catch breaking JSON contract changes even while Java services still pass.

The lesson uses **Java 17, Spring Boot 3.3.x, and Jackson 2.x** for all runnable code. Spring Boot 4.x defaults to Jackson 3, where packages/configurations change; the final section details how to cross-check when upgrading instead of mixing imports from both lines.

## 2. Learning objectives

After this lesson you can:

1. Understand JSON serialization and deserialization, especially the difference between Java field names and external property names.
2. Configure naming strategies at the application level or per DTO, and know when `@JsonProperty`/`@JsonAlias` are used.
3. Distinguish **missing** fields, fields with JSON `null`, empty strings, empty collections, and primitive defaults.
4. Use `@JsonInclude` to control null output without confusing it with input validation.
5. Design stable enum wire codes with `@JsonValue`/`@JsonCreator`, avoiding ordinals and implicitly changed constant names.
6. Choose the right `LocalDate`, `Instant`, `OffsetDateTime`, `LocalDateTime`, format string, and timezone/offset.
7. Understand `JavaTimeModule` and why `new ObjectMapper()` can differ from the mapper provided by Spring Boot.
8. Write `@JsonTest` + `JacksonTester` tests to verify JSON contracts directly.
9. Write `@WebMvcTest` + `MockMvc` tests to confirm HTTP requests/responses use the right Jackson configuration.
10. Maintain a regression suite for round-trips, invalid input, missing/null fields, and date-time policies during framework upgrades.

## 3. Both conversion directions must be tested separately

**Serialization** converts a Java object to JSON:

```text
Java BookingEvent
    |
    +-- Property naming: bookingId -> booking_id
    +-- Inclusion rule: optionalNote=null -> omit field
    +-- Enum encoder: QUEUED -> "queued"
    +-- Date/time formatter: LocalDate -> "08/11/2026"
    +-- Offset datetime -> "2026-11-08T09:30:00+07:00"
    v
JSON response
```

**Deserialization** converts JSON back to a Java object:

```text
JSON request
    |
    +-- Find exact field name booking_id
    +-- Distinguish absent and explicit null
    +-- Enum decoder: "queued" -> QUEUED
    +-- Parse date as "dd/MM/yyyy"
    +-- Parse datetime with offset
    v
Java BookingEvent
```

Asymmetric nature:

- `@JsonInclude(NON_NULL)` decides **which fields are written out**. It does **not** prevent clients from sending JSON null, nor does it require the field on input.
- `@JsonAlias` supports **reading** legacy names while serialization still uses the primary name.
- `@JsonValue` defines the enum wire value; to control reading and error messages, add `@JsonCreator`.
- `@JsonFormat` can affect both reading and writing, but requires understanding the specific temporal type.
- A green round-trip is useful, yet **insufficient** if both serializer and deserializer drifted wrongly in the same direction. Keep an **expected JSON independent of production code**.

## 4. How Jackson works in Spring Boot 3.3

Spring Boot 3.3 typically provides a `com.fasterxml.jackson.databind.ObjectMapper` bean configured through:

- Discovered/registered Jackson 2 modules, including `java.time` support when the right dependency is present;
- `spring.jackson.*` properties;
- `Jackson2ObjectMapperBuilderCustomizer` and other Jackson customizations;
- Jackson annotations on models/DTOs such as `@JsonNaming`, `@JsonInclude`, `@JsonValue`, `@JsonFormat`;
- Custom `@JsonComponent`, `JsonSerializer`, `JsonDeserializer`, or Jackson `Module` beans if present.

With `spring-boot-starter-web`, Jackson is normally on the classpath via the JSON starter. Spring MVC uses HTTP message converters (such as the Jackson converter) to encode/decode `@RequestBody` and response bodies.

**Two points to remember:**

1. The Spring Boot auto-configured `ObjectMapper` **can differ** from a plain `new ObjectMapper()` in modules, naming, null inclusion, and date/time features.
2. `@JsonTest` uses a **JSON test slice** with Jackson auto-configured for that scope; `@WebMvcTest` adds MVC converters/request handling. Never treat `@JsonTest` as a full HTTP test.

### 4.1. Relevant Boot 3.3 properties

```properties
# Application config example - not all need to be enabled:
spring.jackson.property-naming-strategy=SNAKE_CASE
spring.jackson.default-property-inclusion=non_null
spring.jackson.serialization.write-dates-as-timestamps=false
spring.jackson.deserialization.adjust-dates-to-context-time-zone=false
spring.jackson.time-zone=UTC
```

These lines are **independent options**; you do not need to copy all of them into every app. In the sample project below, naming and null rules are placed on the DTO to show locality; only two date-time features are placed in `application.properties` for consistent behavior.

| Setting | Purpose in Boot 3.3 |
| --- | --- |
| `spring.jackson.property-naming-strategy` | Selects the naming strategy for Jackson properties, e.g. `SNAKE_CASE` |
| `spring.jackson.default-property-inclusion` | Default inclusion rule such as `non_null` |
| `spring.jackson.serialization.write-dates-as-timestamps` | Toggles serializing dates/times as timestamps/arrays by type |
| `spring.jackson.deserialization.adjust-dates-to-context-time-zone` | Enables/disables adjusting timezone-aware date-times to the mapper context timezone |
| `spring.jackson.time-zone` | Default mapper timezone, affecting related serializers/deserializers |
| `spring.jackson.date-format` | Default date format primarily for `java.util.Date`/`Calendar`; **not a universal format for all `java.time` types** |

**Distinguish from `spring.mvc.format.*`:** the `spring.mvc.format.date/time/date-time` group mainly configures Spring MVC formatting/conversion for query/path/form data. It does not mean Jackson JSON serialization of `@RequestBody` or response DTOs.

## 5. Naming strategy: camelCase, snake_case, kebab-case

### 5.1. One object, multiple naming styles

Java code:

```java
record CustomerInfo(
        String customerId,
        String firstName,
        String billingAddress) {}
```

Common Jackson 2 options:

| Strategy | Java name | Example JSON property |
| --- | --- | --- |
| Default lower camel | `customerId` | `customerId` |
| `SNAKE_CASE` | `customerId` | `customer_id` |
| `KEBAB_CASE` | `customerId` | `customer-id` |
| `UPPER_CAMEL_CASE` | `customerId` | `CustomerId` |
| `LOWER_CASE` | `customerId` | `customerid` |

These illustrate typical transformations. For acronyms, special characters, Unicode, existing underscores, or non-standard property getters, naming strategies have specific rules; **test actual JSON** instead of guessing solely by eye.

### 5.2. Application-wide configuration

In Spring Boot 3.3:

```properties
spring.jackson.property-naming-strategy=SNAKE_CASE
```

When the Boot-provided Jackson mapper receives this setting, properties without explicit overrides convert to snake_case. Advantage: consistency if the entire API follows one convention. Risk: changing a global property alters the JSON of **every DTO** handled by that mapper and can break backward compatibility.

**Do not** alter global naming just so one new endpoint returns snake_case if older APIs still use camelCase. When endpoints have differing contracts, placing annotations directly on the appropriate DTO is safer.

### 5.3. Per-DTO configuration

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record CustomerInfo(
        String customerId,
        String firstName,
        String billingAddress) {}
```

This illustrative code is a record to place in `CustomerInfo.java`/an appropriate package; the resulting JSON uses `customer_id`, `first_name`, and `billing_address` unless overridden by other annotations.

**Advantage of `@JsonNaming`:** documents the external contract right on the model, makes review easy, and leaves other DTOs untouched.

### 5.4. `@JsonProperty` and `@JsonAlias`

When a field has a fixed contract-mandated name, use `@JsonProperty`:

```java
public record ClientInfo(
        @JsonProperty("customer_id") String customerId,
        @JsonProperty("displayName") String displayName) {}
```

This snippet requires `import com.fasterxml.jackson.annotation.JsonProperty`. Explicit names typically take precedence over general naming rules.

If you want to **read an old name** while **writing a new name**:

```java
public record ClientInfo(
        @JsonProperty("customer_id")
        @JsonAlias({"customerId", "legacy_customer_code"})
        String customerId) {}
```

`@JsonAlias` is **deserialization-only**: it does not make JSON responses emit all three keys at once. This helps while migrating API clients to `customer_id`; include tests for both the new name and the aliases.

**Note:** if a client sends both `customer_id` and `customerId` with conflicting values, do not rely on an arbitrary processing order as a business rule. Define a policy requiring one canonical name and rejecting ambiguous input when needed.

### 5.5. Map keys are not POJO property names

`SNAKE_CASE` applies naming to **bean/record property names**. It **does not guarantee automatically converting dynamic keys** inside a `Map<String,Object>`. For instance, a Map with key `"customerId"` may still serialize with that exact key. To normalize Map keys, use a dedicated strategy (transform keys beforehand, custom key serializer, or an explicit DTO).

Therefore, do not test naming strategies solely with a `Map` object if your goal is protecting DTO property naming.

## 6. Null: absent, explicit null, empty, and default

JSON has several distinct states:

```json
{"optional_note": null}
```

```json
{}
```

```json
{"optional_note": ""}
```

```json
{"optional_note": []}
```

They do **not** share the same contract meaning:

| JSON | Possible API meaning |
| --- | --- |
| Field **absent** | Client did not provide / does not want to modify the value |
| `"field": null` | Client provided an explicit null value, possibly requesting deletion |
| `"field": ""` | Empty string, valid or invalid depending on validation |
| `"field": []` | Empty list, distinct from null |
| `"field": 0` | Zero value, distinct from null when using wrapper types |

**In a Java record with ordinary nullable fields**, Jackson may bind both a missing field and an explicit null to `null`. This **loses presence information** if a PATCH API needs to distinguish "leave unchanged" from "clear." Do not rely on a plain Java record `String` to infer either meaning without an additional mechanism.

### 6.1. `@JsonInclude` controls output

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ApiResult(
        String code,
        String optionalNote) {}
```

This snippet requires `import com.fasterxml.jackson.annotation.JsonInclude`. With `new ApiResult("OK", null)`, the serializer can emit `{"code":"OK"}`; the rule only controls **writing JSON**, without forbidding deserialization of null.

Common options:

| Include | Primary behavior | Note |
| --- | --- | --- |
| `ALWAYS` | Writes properties by default, including nulls | Null fields usually appear |
| `NON_NULL` | Omits properties with Java null value | Does not automatically drop empty strings/lists |
| `NON_EMPTY` | Omits null and values Jackson considers empty such as `""`, empty collections/maps | Depends on serializer/type; not every zero is empty |
| `NON_ABSENT` | Omits null/absent values of reference types like `Optional.empty()` when supported | Requires JDK8 module when using `Optional` |
| `NON_DEFAULT` | Omits values determined to be defaults in context | Semantics depend on class-level/global/value defaults; test separately |

**Common misconception:** `NON_NULL` does **not** mean "optional field" in the request contract. A required input field still needs separate validation even if the response serializer omits nulls.

### 6.2. Do not confuse `null` with missing fields on deserialization

Suppose:

```java
public record PatchRequest(String displayName) {}
```

When deserializing `{}` or `{"displayName":null}`, both can yield `new PatchRequest(null)` under standard Jackson settings. Yet HTTP PATCH often requires:

- Field **absent**: do not update.
- Field **with null**: clear data.
- Field **with value**: update.

You can use `JsonNode.has(...)` and `JsonNode.isNull()` to observe presence, or a wrapper type representing undefined/null/value (such as a `JsonNullable` library suited to your API) instead of a plain record.

```java
JsonNode root = mapper.readTree(jsonText);
boolean provided = root.has("display_name");
boolean explicitlyNull =
        provided && root.get("display_name").isNull();
```

This snippet requires `JsonNode`, `ObjectMapper`, and a `jsonText` variable. `root.has("display_name")` is true even when the value is JSON null; `root.hasNonNull("display_name")` is true only if the value is non-null. Check missing keys accurately rather than inferring from `root.path(...).asText()`.

### 6.3. Validation is not JSON inclusion

`@NotNull`, `@NotBlank`, and `@Valid` from Jakarta Bean Validation handle request validity when the validator is active. `@JsonInclude(NON_NULL)` does not replace them.

- `@NotNull`: rejects Java null during validation.
- `@NotBlank`: requires a non-null string containing at least one non-whitespace character.
- `@Valid`: triggers nested/`@RequestBody` validation when MVC and the validation starter are properly set up.
- `@JsonSetter(nulls = Nulls.FAIL)`: can fail when JSON supplies null to a specific property—a deserialization mechanism distinct from validation.

**Never assume** a required field will return HTTP 400 merely because you added `@JsonInclude`. Establish the validation/deserialization contract and write negative tests.

### 6.4. Primitive fields can hide missing input

`int quantity` and `boolean active` are primitives with defaults `0`/`false`. If a client omits the field, some deserialization modes assign the default; afterward it is hard to tell real input from missing input. When missing input must be rejected, consider wrappers `Integer`/`Boolean` with validation, or stricter creator property rules.

## 7. Enum: Java names should not blindly be the wire contract

By default, Jackson usually serializes enums by constant name:

```java
enum DeliveryState {
    QUEUED, SENT
}
```

`DeliveryState.QUEUED` usually outputs `"QUEUED"`. If the API publishes `"queued"`, renaming constants, changing case, or enabling `toString()` can break clients.

### 7.1. Why not use ordinal?

`ordinal()` is the enum's declaration position, e.g. QUEUED=0, SENT=1. Prepending a constant shifts the positions of all subsequent constants. A JSON number like `0` is also opaque and easily couples consumers to code ordering.

**Recommendation:** use **stable wire codes**, independent of enum constant names and ordinals.

### 7.2. `@JsonValue` and `@JsonCreator`

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum DeliveryState {
    QUEUED("queued"),
    SENT("sent");

    private final String wireCode;

    DeliveryState(String wireCode) {
        this.wireCode = wireCode;
    }

    @JsonValue
    public String wireCode() {
        return wireCode;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static DeliveryState fromWireCode(String code) {
        for (DeliveryState state : values()) {
            if (state.wireCode.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException(
                "Unknown delivery state: " + code);
    }
}
```

This is a complete Java 17 enum when saved in `DeliveryState.java`.

- `@JsonValue`: serializes `QUEUED` → `"queued"`.
- `@JsonCreator`: deserializes `"queued"` → `QUEUED`.
- Independent of `name()`, `ordinal()`, `toString()`.
- An unknown value like `"delayed"` throws an exception in the creator, wrapped by Jackson as a mapping exception when reading JSON. In HTTP MVC, request decoding failures normally map to 400 unless overridden by an error handler.

When adding a new state, consider older clients' compatibility; even if the server can emit the new code, clients may not recognize it yet.

### 7.3. Should unknown enums be allowed?

There are several strategies:

1. **Strict**: unknown enum codes fail—appropriate when data must be tightly controlled and clients need clear feedback.
2. **Fallback `UNKNOWN`**: define a `@JsonEnumDefaultValue` constant and enable `DeserializationFeature.READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE` in Jackson 2 if appropriate.
3. **Map to null**: `READ_UNKNOWN_ENUM_VALUES_AS_NULL` when explicitly decided.

Do not enable global fallbacks just to turn tests green, as they can **mask typos or incompatible API changes**. `UNKNOWN` must be handled intentionally in business logic; never treat it as an ordinary valid state by default.

**Do not confuse:** `@JsonEnumDefaultValue` alone does not mean the "using default value" feature is enabled in every mapper/version. Test unknown enum input to verify.

### 7.4. `@JsonFormat(shape=OBJECT)` for enums?

Jackson can also serialize an enum as an object with multiple properties. However, an API using `{"code":"queued","label":"Queued"}` has a different schema from the string `"queued"`. When the contract only requires a stable code, `@JsonValue` is usually simpler. Do not switch to object enum output and expect string-expecting clients to stay compatible.

## 8. Date/time: choose the right Java type before formatting

| Java type | Representation | Has timezone/offset? | Use when |
| --- | --- | --- | --- |
| `LocalDate` | Calendar date, e.g. 2026-11-08 | **No** | Birthdates, booking dates, due dates |
| `LocalTime` | Time of day | No | Scheduled opening hours, needs separate zone to resolve an instant |
| `LocalDateTime` | Local date + time | **No** | Internal schedules when zone is managed separately |
| `Instant` | Absolute point on the UTC timeline | No zone ID; represents an instant | Audit `createdAt`, event timestamps |
| `OffsetDateTime` | Date-time + offset like `+07:00` | **Has offset**, not necessarily a zone ID | API needs explicit date-time and offset |
| `ZonedDateTime` | Date-time + zone ID like `Asia/Ho_Chi_Minh` | Has zone ID and rule-based offset | Regional/DST-aware schedules |
| `java.util.Date` | Legacy type representing an instant | Format depends on mapper/timezone | Legacy system compatibility |

**Principle:** choose the type by data meaning first, then format JSON. Do not use `LocalDateTime` for "global transaction creation time" if clients must determine an unambiguous timezone-independent instant.

### 8.1. Offset differs from zone ID

`+07:00` is a **fixed offset** from UTC. `Asia/Ho_Chi_Minh` is a **ZoneId** containing historical timezone rules and can differ semantically from a fixed offset in regions with DST. Under daylight-saving transitions, a local wall-clock time can be ambiguous or nonexistent in a zone.

If the API only needs an absolute instant, UTC-normalized `Instant` is usually simplest. If you must preserve the `+07:00` offset submitted by a user, use `OffsetDateTime`. For future regional schedules, you may need a `ZoneId` alongside local date/time.

### 8.2. ISO-8601 and custom patterns

With `JavaTimeModule` and proper Boot setup, `java.time` types typically serialize as ISO-8601-like strings. Yet **do not rely on defaults as an immutable contract**: `WRITE_DATES_AS_TIMESTAMPS`, modules, annotations, and Jackson major versions can all change output.

To specify a single field:

```java
@JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "dd/MM/yyyy")
LocalDate travelDate
```

To specify an offset datetime:

```java
@JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
OffsetDateTime createdAt
```

`@JsonFormat` comes from `com.fasterxml.jackson.annotation`. The `XXX` pattern formats offsets as `+07:00` or `Z` for UTC; `'T'` is a literal character. The demo uses whole-second timestamps so fractional-second precision does not need to be specified.

### 8.3. Pattern tokens commonly misused

| Token | Meaning | Common mistake |
| --- | --- | --- |
| `yyyy` | Year-of-era | Confused with week-based year `YYYY` |
| `uuuu` | Proleptic year in `DateTimeFormatter` | Needs care with strict/era parsing |
| `MM` | Month | Confused with `mm` (minutes) |
| `dd` | Day of month | Confused with `DD` (day of year) |
| `HH` | Hour 0–23 | Confused with `hh` (1–12 without AM/PM) |
| `mm` | Minute | Confused with `MM` (month) |
| `ss` | Second | Does not represent milliseconds |
| `SSS` | 3-digit millisecond/fraction | Longer nanosecond data needs its own policy |
| `XXX` | Offset like `+07:00`/`Z` | Not synonymous with `ZoneId` |
| `'T'` | Literal `T` character | Forgetting quotes makes the pattern invalid |

Especially avoid `YYYY-MM-dd` for calendar dates: `YYYY` is the week-based year and can differ from the calendar year around year boundaries. Test dates near Dec 31 and Jan 01 to catch this bug.

### 8.4. Timezone normalization during deserialization

An input like:

```json
{"created_at":"2026-11-08T09:30:00+07:00"}
```

represents the same instant as `2026-11-08T02:30:00Z`. In Jackson 2, `ADJUST_DATES_TO_CONTEXT_TIME_ZONE` can adjust certain offset/zone date-times to the mapper context timezone while reading.

When the contract requires **preserving the sender's offset**, disable that feature for your app/test mapper as supported by your version:

```properties
spring.jackson.deserialization.adjust-dates-to-context-time-zone=false
```

If the contract only cares about the instant, compare `toInstant()` rather than offset strings. Two strings with different offsets can represent the **exact same instant**; tests should decide whether to preserve *instant*, *offset*, or *local wall time*.

**Never mutate the JVM timezone inside individual tests** to force expected values to match. That alters global state and creates flaky parallel tests. Use data with explicit offsets/zones and mapper/test configuration.

### 8.5. `spring.jackson.date-format` does not cover all `java.time` types

In Boot 3.3:

```properties
spring.jackson.date-format=yyyy-MM-dd HH:mm:ss
```

primarily applies to `java.util.Date`/`Calendar` and formats handled by Jackson's legacy `DateFormat`. It is **not a uniform switch** for every `LocalDate`, `Instant`, or `OffsetDateTime` handled by `JavaTimeModule`. To format specific JSON fields differently, use `@JsonFormat` or appropriate `java.time` serializers/deserializers.

Likewise, `spring.mvc.format.date` applies to Spring conversion for request params/path/form values, and does not automatically alter `@RequestBody` JSON.

## 9. Do not build a standalone ObjectMapper and assume it matches Spring Boot

A common mistake:

```java
ObjectMapper mapper = new ObjectMapper();
String json = mapper.writeValueAsString(
        OffsetDateTime.now());
```

This is an **example of a fragile approach**, not suitable as a contract test. A plain mapper may **lack** `JavaTimeModule` for `OffsetDateTime` depending on dependencies/version, and lacks the app's `spring.jackson.*`/customizers. The result can be an exception like "Java 8 date/time type not supported" or JSON differing from real HTTP responses.

In Spring Boot tests, prefer:

```java
@JsonTest
class JsonContractTest {
    @Autowired
    ObjectMapper mapper;
}
```

or `@Autowired JacksonTester<T>`. They use the JSON configuration assembled by Boot for the test slice. If you must unit test a manually constructed mapper, configure its modules/features explicitly; **never** compare a plain mapper against HTTP and assume differences are controller bugs.

### 9.1. What is JavaTimeModule?

In Jackson 2, `jackson-datatype-jsr310` provides `JavaTimeModule` to serialize/deserialize `java.time`. `spring-boot-starter-json` in Boot 3.3 includes this support when dependencies are properly managed. When building a mapper manually, you may need:

```java
ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
        .disable(
                DeserializationFeature.ADJUST_DATES_TO_CONTEXT_TIME_ZONE);
```

This is a **standalone mapper pattern** requiring `com.fasterxml.jackson.*` imports; do not create a separate mapper inside each controller without good reason, as it can bypass global application settings.

### 9.2. Mutating a singleton ObjectMapper can affect the entire app

The `ObjectMapper` bean is typically shared. Never call `mapper.setPropertyNamingStrategy(...)` arbitrarily inside a test and let it leak into other tests via context caching. To customize a mapper for one specific test, use isolated test properties/configuration or `mapper.copy()` for a local instance.

Jackson customizations should be applied **before the mapper is used**; mutating a mapper after its first read/write can cause unpredictable behavior or thread-safety issues under parallel execution.

## 10. Runnable project: Java 17, Spring Boot 3.3.0, Jackson 2

The following project protects **naming, nulls, enums, and date/time** together through:

- Pure JSON tests using `@JsonTest`/`JacksonTester`.
- Global naming strategy testing using `@TestPropertySource` in a separate JSON slice.
- HTTP JSON testing at the MVC layer using `@WebMvcTest`/`MockMvc`.
- Negative tests with unknown enum codes and invalid dates.
- Null/missing distinction tests using `JsonNode`, without pretending plain nullable DTOs preserve presence.

### 10.1. Directory tree

```text
booking-json-contract/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── resources/
    │   │   └── application.properties
    │   └── java/example/json/
    │       ├── JsonDemoApplication.java
    │       ├── DeliveryState.java
    │       ├── BookingEvent.java
    │       ├── BookingQueryService.java
    │       └── BookingController.java
    └── test/java/example/json/
        ├── BookingEventJsonTest.java
        ├── GlobalNamingJsonTest.java
        └── BookingControllerWebTest.java
```

### 10.2. Gradle settings

**`settings.gradle`:**

```groovy
rootProject.name = 'booking-json-contract'
```

### 10.3. Gradle build

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot 3.3.0 uses BOM-managed Jackson 2.x. `spring-boot-starter-web` pulls in Jackson and matching Jackson Java Time support; `spring-boot-starter-test` supplies JUnit Jupiter, AssertJ, JSON test helpers, Mockito, MockMvc, and Spring Test. The example uses no database, Docker, or external services.

Use a Gradle Wrapper compatible with JDK 17/Boot 3.3 (for instance, Gradle 8.5), and do not override a single Jackson version individually while expecting the test BOM to stay consistent.

### 10.4. App-level date-time features

**`src/main/resources/application.properties`:**

```properties
# JSON java.time must be written as strings instead of timestamps/arrays.
spring.jackson.serialization.write-dates-as-timestamps=false

# When reading OffsetDateTime, preserve the offset from JSON instead of converting to the mapper context zone.
spring.jackson.deserialization.adjust-dates-to-context-time-zone=false
```

These two lines are kept **fixed** in the demo, shared by both the JSON slice and the MVC web slice. Naming and null rules are not set globally because `BookingEvent` uses DTO annotations. This lets the tests demonstrate which layer controls each behavior.

If a real API wants to normalize all timestamps to UTC, it may choose a different contract. In that case, do **not** blindly copy disabling timezone adjustment; use `Instant`/appropriate mapper configuration and assert the right instant.

### 10.5. Spring Boot application

**`src/main/java/example/json/JsonDemoApplication.java`:**

```java
package example.json;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonDemoApplication.class, args);
    }
}
```

Placing `@SpringBootApplication` at the root package lets Boot scan the service/controller. With `@JsonTest`, the test slice mainly loads JSON infrastructure without starting a web server.

### 10.6. Enum wire contract

**`src/main/java/example/json/DeliveryState.java`:**

```java
package example.json;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum DeliveryState {
    QUEUED("queued"),
    SENT("sent");

    private final String wireCode;

    DeliveryState(String wireCode) {
        this.wireCode = wireCode;
    }

    @JsonValue
    public String wireCode() {
        return wireCode;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static DeliveryState fromWireCode(String code) {
        for (DeliveryState state : values()) {
            if (state.wireCode.equals(code)) {
                return state;
            }
        }
        throw new IllegalArgumentException(
                "Unknown delivery state: " + code);
    }
}
```

With this type: Java `DeliveryState.QUEUED` → JSON `"queued"`; JSON `"sent"` → Java `DeliveryState.SENT`; JSON `"delayed"` fails decoding. Because the wire code is explicitly assigned, renaming a Java enum constant (without changing `wireCode`) does not change the external wire contract.

**Do not** emit enum ordinals such as 0/1. Adding enum values can shift ordinals.

### 10.7. DTO: naming + null + date/time format

**`src/main/java/example/json/BookingEvent.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
@JsonInclude(JsonInclude.Include.NON_NULL)
public record BookingEvent(
        String bookingId,
        String customerName,
        DeliveryState state,
        @JsonFormat(
                shape = JsonFormat.Shape.STRING,
                pattern = "dd/MM/yyyy")
        LocalDate travelDate,
        @JsonFormat(
                shape = JsonFormat.Shape.STRING,
                pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
        OffsetDateTime createdAt,
        String optionalNote) {}
```

Each annotation has a distinct role:

- `@JsonNaming(...SnakeCaseStrategy.class)`: Java `bookingId` → JSON `booking_id`.
- `@JsonInclude(NON_NULL)`: `optionalNote = null` → omits `optional_note` when **writing** JSON.
- `DeliveryState` has its own serializer/deserializer via `@JsonValue`/`@JsonCreator`.
- `travelDate` uses `dd/MM/yyyy`, e.g. `08/11/2026`.
- `createdAt` uses the pattern with `XXX`, e.g. `2026-11-08T09:30:00+07:00`.

**Java record note:** Jackson 2 in Boot 3.3 supports records. Annotations on record components are picked up by Jackson when processing properties. For traditional JavaBeans POJOs, annotations can be placed on fields/getters/constructor parameters depending on mapper introspection; test directly on production classes rather than guessing.

### 10.8. Simple service for MVC tests

**`src/main/java/example/json/BookingQueryService.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import org.springframework.stereotype.Service;

@Service
public class BookingQueryService {
    public BookingEvent find(String bookingId) {
        return new BookingEvent(
                bookingId,
                "Mai",
                DeliveryState.QUEUED,
                LocalDate.of(2026, 11, 8),
                OffsetDateTime.parse(
                        "2026-11-08T09:30:00+07:00"),
                null);
    }
}
```

This is a demo service with no database/HTTP calls. `@WebMvcTest` will mock the service to focus on the JSON/MVC boundary without needing the full application context.

### 10.9. Controller with GET and POST echo

**`src/main/java/example/json/BookingController.java`:**

```java
package example.json;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {
    private final BookingQueryService service;

    public BookingController(BookingQueryService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public BookingEvent get(@PathVariable String id) {
        return service.find(id);
    }

    @PostMapping("/echo")
    public BookingEvent echo(@RequestBody BookingEvent body) {
        return body;
    }
}
```

The `echo` endpoint only illustrates **deserialization + serialization through Spring MVC**. It is not a mandatory production API pattern; real applications should have proper business contracts, validation, and security.

## 11. Test 1 — `@JsonTest` protecting the entire JSON wire contract

**`src/test/java/example/json/BookingEventJsonTest.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.boot.test.json.JacksonTester;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@JsonTest
class BookingEventJsonTest {
    @Autowired
    JacksonTester<BookingEvent> json;

    @Autowired
    ObjectMapper mapper;

    private BookingEvent sample() {
        return new BookingEvent(
                "B-42",
                "Mai",
                DeliveryState.QUEUED,
                LocalDate.of(2026, 11, 8),
                OffsetDateTime.parse(
                        "2026-11-08T09:30:00+07:00"),
                null);
    }

    private String validJson() {
        return """
                {
                  "booking_id": "B-42",
                  "customer_name": "Mai",
                  "state": "queued",
                  "travel_date": "08/11/2026",
                  "created_at": "2026-11-08T09:30:00+07:00"
                }
                """;
    }

    @Test
    void serializeUsesSnakeCaseEnumCodeAndDateFormats()
            throws Exception {
        String output = json.write(sample()).getJson();
        JsonNode root = mapper.readTree(output);

        assertEquals("B-42",
                root.path("booking_id").asText());
        assertEquals("Mai",
                root.path("customer_name").asText());
        assertEquals("queued",
                root.path("state").asText());
        assertEquals("08/11/2026",
                root.path("travel_date").asText());
        assertEquals("2026-11-08T09:30:00+07:00",
                root.path("created_at").asText());

        assertFalse(root.has("bookingId"));
        assertFalse(root.has("createdAt"));
        assertFalse(root.has("optional_note"));
    }

    @Test
    void deserializationPreservesValuesAndOffset()
            throws Exception {
        BookingEvent event = json.parseObject(validJson());

        assertEquals(sample(), event);
        assertEquals("+07:00",
                event.createdAt().getOffset().toString());
        assertEquals(
                OffsetDateTime.parse(
                        "2026-11-08T02:30:00Z").toInstant(),
                event.createdAt().toInstant());
    }

    @Test
    void missingAndExplicitNullBothBecomeNullInPlainRecord()
            throws Exception {
        JsonNode root = mapper.readTree(validJson());
        assertFalse(root.has("optional_note"));

        BookingEvent missing =
                mapper.treeToValue(root, BookingEvent.class);
        assertNull(missing.optionalNote());

        ObjectNode withNull = (ObjectNode) root.deepCopy();
        withNull.putNull("optional_note");

        assertTrue(withNull.has("optional_note"));
        assertTrue(withNull.get("optional_note").isNull());

        BookingEvent explicit =
                mapper.treeToValue(withNull, BookingEvent.class);
        assertNull(explicit.optionalNote());
    }

    @Test
    void unknownEnumCodeFailsInsteadOfSilentlyMapping()
            throws Exception {
        String invalid = validJson().replace(
                "\"queued\"", "\"delayed\"");

        assertThrows(JsonProcessingException.class,
                () -> mapper.readValue(
                        invalid, BookingEvent.class));
    }

    @Test
    void invalidCalendarDateFailsOnDecode() {
        String invalid = validJson().replace(
                "08/11/2026", "not-a-date");

        assertThrows(JsonProcessingException.class,
                () -> mapper.readValue(
                        invalid, BookingEvent.class));
    }
}
```

### 11.1. What does this test actually verify?

- JSON field names `booking_id` and `created_at`, while excluding camelCase in output.
- `optional_note` is absent when the Java value is null (not merely checking `path(...).asText()` is empty).
- Enum `QUEUED` is written as `"queued"`; unknown codes are rejected.
- `LocalDate` and `OffsetDateTime` adhere to explicit patterns.
- On read, `OffsetDateTime` preserves the `+07:00` offset thanks to the Boot test mapper config, while representing the exact UTC instant `02:30:00Z`.
- Missing `optional_note` and explicit null both become Java null in a plain record, demonstrating why PATCH may require a dedicated presence representation.
- Invalid date text raises a decoding error rather than silently converting to an assumed date.

### 11.2. Why assert JSON using JsonNode?

`JsonNode` lets you check an **absent** field via `has` rather than `asText()`—since `MissingNode` returns an empty string, which can confuse missing with empty. It is also independent of JSON key order and whitespace.

Besides `ObjectMapper.readTree`, Spring Boot's `JacksonTester` provides AssertJ JSON assertions, for example:

```java
assertThat(json.write(sample()))
        .extractingJsonPathStringValue("@.booking_id")
        .isEqualTo("B-42");
```

This snippet requires the AssertJ `assertThat` static import; the main sample primarily uses `JsonNode` + JUnit to assert every concrete presence state.

### 11.3. Protecting fixed expected values rather than only round-trips

If the serializer accidentally changes `booking_id` to `bookingId` and the deserializer changes identically, a test that only serializes and deserializes back could **still pass**. Therefore, `serializeUses...` asserts exact independent JSON keys/values while `deserializationPreserves...` tests the read path. Together they catch far more regressions.

## 12. Test 2 — Application-level naming strategy

To prove that `spring.jackson.property-naming-strategy=SNAKE_CASE` affects a DTO **without `@JsonNaming`**, create a separate JSON slice with the test property.

**`src/test/java/example/json/GlobalNamingJsonTest.java`:**

```java
package example.json;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.json.JsonTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

@JsonTest
@TestPropertySource(properties =
        "spring.jackson.property-naming-strategy=SNAKE_CASE")
class GlobalNamingJsonTest {
    @Autowired
    ObjectMapper mapper;

    record PlainEnvelope(
            String trackingId,
            String customerEmail) {}

    @Test
    void globalStrategyAppliesToUnannotatedRecord()
            throws Exception {
        String result = mapper.writeValueAsString(
                new PlainEnvelope(
                        "TRK-7", "mai@example.test"));

        JsonNode root = mapper.readTree(result);

        assertEquals("TRK-7",
                root.path("tracking_id").asText());
        assertEquals("mai@example.test",
                root.path("customer_email").asText());
        assertFalse(root.has("trackingId"));
        assertFalse(root.has("customerEmail"));
    }
}
```

Key takeaways:

- `PlainEnvelope` has no `@JsonNaming`: naming comes from Spring Boot's property.
- The property is set only in **this test class's context**, without modifying production config.
- Switching a global property in a large app can simultaneously alter all DTOs lacking overrides. Regression tests for the public API schema are essential.
- Test contexts with different properties receive **different cache keys**; that is normal Spring TestContext behavior.

## 13. Test 3 — JSON across the Spring MVC HTTP boundary with MockMvc

`@JsonTest` is the best place for focused serializer/deserializer tests. Yet you must also verify that Spring MVC actually uses that Jackson configuration for `@RequestBody` and responses.

**`src/test/java/example/json/BookingControllerWebTest.java`:**

```java
package example.json;

import java.time.LocalDate;
import java.time.OffsetDateTime;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(BookingController.class)
class BookingControllerWebTest {
    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @MockBean
    BookingQueryService service;

    private BookingEvent sample() {
        return new BookingEvent(
                "B-42",
                "Mai",
                DeliveryState.QUEUED,
                LocalDate.of(2026, 11, 8),
                OffsetDateTime.parse(
                        "2026-11-08T09:30:00+07:00"),
                null);
    }

    @Test
    void getRendersPublicWireContract() throws Exception {
        when(service.find("B-42"))
                .thenReturn(sample());

        mvc.perform(get("/api/bookings/B-42"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.booking_id")
                        .value("B-42"))
                .andExpect(jsonPath("$.customer_name")
                        .value("Mai"))
                .andExpect(jsonPath("$.state")
                        .value("queued"))
                .andExpect(jsonPath("$.travel_date")
                        .value("08/11/2026"))
                .andExpect(jsonPath("$.created_at")
                        .value(
                                "2026-11-08T09:30:00+07:00"))
                .andExpect(jsonPath("$.optional_note")
                        .doesNotExist());

        verify(service).find("B-42");
    }

    @Test
    void postEchoDecodesAndReencodesJson()
            throws Exception {
        String payload = mapper.writeValueAsString(
                sample());

        mvc.perform(post("/api/bookings/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.booking_id")
                        .value("B-42"))
                .andExpect(jsonPath("$.state")
                        .value("queued"))
                .andExpect(jsonPath("$.travel_date")
                        .value("08/11/2026"))
                .andExpect(jsonPath("$.created_at")
                        .value(
                                "2026-11-08T09:30:00+07:00"));
    }

    @Test
    void postRejectsUnknownEnumWireCode()
            throws Exception {
        String payload = mapper.writeValueAsString(
                sample()).replace(
                        "\"queued\"", "\"delayed\"");

        mvc.perform(post("/api/bookings/echo")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(payload))
                .andExpect(status().isBadRequest());
    }
}
```

### 13.1. What is proven

- `@WebMvcTest` configures the MVC controller and the slice's HTTP message converters.
- `@MockBean BookingQueryService` provides the external dependency outside the slice, though the real service is **not tested**.
- GET returns snake_case, omits null, uses the right enum wire code, and uses the right date/time formats in the **mocked HTTP response**.
- POST decodes the same format into `BookingEvent` and echoes JSON per the contract.
- Unparseable enum code `delayed` fails request body decoding; under the example's default MVC error handling, status is 400.
- Does not open an embedded TCP server, nor prove databases/remote clients.

### 13.2. Why are pure JSON tests still needed?

HTTP GET can pass while the deserialization direction goes untested; POST echo adds the read path yet still cannot inspect field presence as precisely as `JsonNode`. `@JsonTest` runs lightly and binds directly to the DTO contract; `@WebMvcTest` guarantees the MVC layer uses that JSON configuration.

**Error response note:** the test only asserts status 400 for an invalid enum code. Spring Boot/Spring MVC default error body schemas can vary across versions/configs; do not assert raw stack traces or an error JSON code not implemented via `@ControllerAdvice`.

## 14. Running the project and expected outcomes

With JDK 17, a compatible Gradle Wrapper, and downloaded dependencies:

```bash
./gradlew test
./gradlew test --tests example.json.BookingEventJsonTest
./gradlew test --tests example.json.GlobalNamingJsonTest
./gradlew test --tests example.json.BookingControllerWebTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.json.BookingEventJsonTest
```

Expected: **9 test methods pass**: `BookingEventJsonTest` has 5, `GlobalNamingJsonTest` has 1, and `BookingControllerWebTest` has 3. Once all Gradle tasks finish, `BUILD SUCCESSFUL` normally appears. There is no fixed business stdout; Boot may print startup/test logs, which are **not** assertions.

**Practice goal:** no Docker, database, network, or third parties needed. A JSON contract regression will fail at least one specific assertion; inspect the failed test name and actual JSON to see which naming/null/enum/date rule changed.

### 14.1. Expected outcomes table

| Scenario | Result |
| --- | --- |
| Serialize `BookingEvent` | `booking_id`/`created_at` in snake_case |
| `optionalNote = null` | `optional_note` omitted |
| `DeliveryState.QUEUED` | JSON `"queued"` |
| `travelDate = 2026-11-08` | JSON `"08/11/2026"` |
| `createdAt = ...+07:00` | JSON retains `+07:00` in pattern |
| Deserialize valid JSON | Record constructed with right values |
| JSON missing `optional_note` | Java `optionalNote == null` |
| JSON `optional_note:null` | Java `optionalNote == null` |
| Enum `"delayed"` | Parse error; HTTP POST echo 400 |
| `travel_date:"not-a-date"` | Parse error |
| Global `SNAKE_CASE` on unannotated record | `tracking_id`, `customer_email` |

### 14.2. Two error types often misdiagnosed

- **JSON test fails:** likely due to changed naming/date/enum formats, missing `JavaTimeModule`, or a misapplied Jackson customizer.
- **MVC test fails loading context:** likely due to a missing `BookingQueryService` mock, package scan issue, or web/security auto-config. This is a test scope/bean graph issue, not necessarily Jackson.

Do not "fix" JSON errors by immediately switching to a full `@SpringBootTest` context. Identify whether the context is missing a bean or the JSON serializer is emitting the wrong output.

## 15. @JsonTest or @SpringBootTest?

| Goal | Suitable approach | What remains unproven |
| --- | --- | --- |
| DTO serialization/deserialization | `@JsonTest` + `JacksonTester` | HTTP routing, services, DB |
| Global Jackson naming/property overrides | `@JsonTest` + test properties | Runtime endpoints/network |
| Controller returns right JSON/schema | `@WebMvcTest` + `MockMvc` | Real service, DB, embedded server |
| Controller-service-repository wiring | `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | TCP/embedded server |
| Client sends HTTP to real server | `@SpringBootTest(RANDOM_PORT)` + HTTP client | External ingress/TLS/load balancers |
| Reactive WebFlux contract | `@WebFluxTest` + `WebTestClient` | Default full reactive app |
| Outbound `WebClient` JSON | Client/mock HTTP server integration | Does not prove inbound endpoints |

**Rule:** if changes only affect DTO naming/null/dates, `@JsonTest` usually gives the fastest feedback. Yet a few HTTP tests help catch cases where the web boundary uses a different converter or config from standalone mapper tests.

## 16. Why can JSON output differ at runtime?

Common causes:

1. **Not the same mapper bean:** tests create `new ObjectMapper()`, while MVC uses Boot's mapper.
2. **Different global strategy:** `spring.jackson.property-naming-strategy` differs between test/profile and production.
3. **Mix-ins or `@JsonView`:** change property visibility on specific endpoints only.
4. **Custom Jackson `Module`/`@JsonComponent`:** slice tests do not auto-import every module if its configuration is excluded.
5. **Controller returns `String` instead of an object:** Spring MVC may send the string verbatim without passing through Jackson the same way.
6. **`ResponseEntity` and content negotiation:** `Accept`/`Content-Type` headers affect converter selection.
7. **Date-time modules and features:** `WRITE_DATES_AS_TIMESTAMPS`, timezone adjustments, or custom formatters differ.
8. **Global inclusion vs DTO override:** a specific `@JsonInclude` can omit a field even if the application default is `ALWAYS`.
9. **Different versions/libraries:** Jackson 2 vs Jackson 3; annotations, serializers, or defaults are not necessarily identical.
10. **Getter/`is`-getter vs field visibility:** in POJOs with inconsistently placed getters and annotations, Jackson property introspection can produce unexpected names/properties.

**Debugging mindset:** compare **the same object**, **the same `ObjectMapper` configuration**, and **the same JSON serializer path** before concluding the bug is in the DTO.

## 17. Naming strategy and schema evolution

Switching from camelCase to snake_case in a public API can be a **breaking change** even if Java logic is unchanged. Clients reading `response.customerId` will receive `undefined` once the server starts sending `customer_id`.

Transition strategies:

- Publish a versioned API or a migration plan.
- Use `@JsonAlias` during **deserialization** to accept both old and new names where appropriate.
- Serialize only one canonical name per contract, avoiding emitting two redundant keys unless intentionally designed.
- Test both legacy client request inputs and new response outputs.
- When different APIs follow different conventions, use per-endpoint/version DTOs instead of flipping global naming on the shared `ObjectMapper`.

Example allowing clients to send legacy input:

```java
public record UserRequest(
        @JsonProperty("customer_id")
        @JsonAlias("customerId")
        String customerId) {}
```

Code requires Jackson imports. Serialization of `UserRequest` still emits `customer_id`, while `customerId` is accepted on read when the mapper supports alias annotations.

**Do not assume** enabling an alias completes the migration. If both fields are sent, validation/business logic needs an ambiguity-resolution rule; schema docs and client tests must also be updated.

## 18. Changing an enum is changing a protocol

Suppose the system adds a new state `RETRYING("retrying")`. The server can serialize that code, yet old clients only know `queued`/`sent`. Clients using exhaustive switches may fail.

When extending an enum:

1. Check whether the client contract permits unknown values.
2. If not, version the API or roll out clients before the server.
3. If allowed, design a client `UNKNOWN` fallback with observability/metrics.
4. Keep existing wire codes stable—never rename `"queued"` to `"waiting"` just because a Java enum constant was renamed.
5. Test both serializer **and** deserializer, plus negative cases.
6. Never globally enable `READ_UNKNOWN_ENUM_VALUES_AS_NULL` if null carries a distinct meaning.

**Best practice:** enum values are protocol data, not mere Java source implementation details.

## 19. Null omission and PATCH semantics

Consider a PATCH API:

```json
{"display_name":"Mai"}
```

and:

```json
{"display_name":null}
```

You may want:

- PATCH omitting `display_name`: leave existing name untouched.
- PATCH with `display_name:null`: clear the name.

If both deserialize into `record Patch(String displayName)` and you check `if (displayName == null)`, you cannot distinguish a delete request from a no-op.

A payload-tree-level solution:

```java
JsonNode body = mapper.readTree(jsonText);
if (body.has("display_name")) {
    if (body.get("display_name").isNull()) {
        // Delete-name requested (if permitted by business contract).
    } else {
        String newName = body.get("display_name").asText();
        // Update after validation.
    }
}
```

This snippet illustrates the concept; handle data types and validation carefully. For large APIs, use a typed wrapper representing `UNDEFINED`/`NULL`/`VALUE` to preserve strong typing.

**Do not put `@JsonInclude(NON_NULL)` on a request DTO and expect the parser to know PATCH intent.** That annotation is an output rule, not a mechanism for tracking field presence on read.

## 20. Date/time format is a business contract

### 20.1. Calendar date differs from instant

A travel date `2026-11-08` is not an instant. Converting it to UTC timestamp `00:00:00Z` can make users in negative timezones see **the previous day**. Use `LocalDate` for calendar dates when the contract truly means a date.

### 20.2. Timestamps with explicit timezones

For a global event's `createdAt`, two common contracts exist:

- **Canonical UTC `Instant`:** `2026-11-08T02:30:00Z`.
- **`OffsetDateTime` preserving submitted offset:** `2026-11-08T09:30:00+07:00`.

They can represent the same instant. Tests should decide whether to assert the **offset text** or just `toInstant()`. If clients must display regional timezones (DST/regional rules), an offset alone may not suffice.

### 20.3. Fractional seconds/nanoseconds

Java `Instant`/`OffsetDateTime` can hold nanosecond precision. An API wanting only milliseconds needs explicit rounding/truncation rules. `@JsonFormat(pattern = "...SSSXXX")` formats 3 fractional digits; if data carries higher precision, define truncation/rounding and assert boundary values.

Avoid comparing `OffsetDateTime.now()` in tests: current time constantly changes. Use a fixed timestamp via `parse(...)` or inject a `Clock` to control test data.

### 20.4. Locale and date/time strings

If a format uses month/day names (e.g. `MMM`), locale can affect output. Configure `@JsonFormat(locale=...)` or a dedicated formatter when contracted. With numeric-only patterns like `dd/MM/yyyy` in the demo, locale dependency is avoided so tests remain stable.

### 20.5. Special calendar boundaries

Also test:

- Feb 29 in leap years and invalid dates.
- Dec 31 and Jan 01 to catch `YYYY` vs `yyyy` bugs.
- Before/after DST transitions if using `ZoneId` in daylight-saving regions.
- Offsets `Z`, `+00:00`, `+07:00`, `-05:00` if accepted by the contract.
- 0, 3, 6, or 9 fractional-second digits if the API specifies precision.
- Very old (pre-1970) or far-future timestamps if required by the business.

A passing "today test" does not prove a formatter works at calendar boundaries.

## 21. JsonTesters, golden files, and JSONPath

Spring Boot's `JacksonTester<T>` can compare JSON against a resource file using AssertJ helpers:

```java
assertThat(json.write(sample()))
        .isEqualToJson("expected-booking.json");
```

This example requires the JSON fixture file where `JacksonTester` looks relative to the test class/resources; it is not in the runnable project because the lesson used explicit `JsonNode` assertions instead.

Advantages of golden JSON:

- Forms a clear **external contract**, easy to review in pull requests.
- Catches changed property names or enum wire codes.
- Fits large DTOs and nested structures.

Disadvantages:

- Oversized snapshots get mechanically updated without reviewing API compatibility.
- Dynamic UUIDs, timestamps, and generated IDs make golden JSON unstable if uncontrolled.
- Some JSON comparison options ignore extra fields or array order; choose strictness per contract.

**Never automatically "update snapshots" when tests turn red.** First determine whether the change is intentional or a regression.

## 22. Verifying correct output without depending on implementation

In this lesson's tests:

- Expected `"queued"` is an external enum code, not derived from `DeliveryState.QUEUED.name().toLowerCase()`. If production code changes wrongly, the expected value still catches it.
- Expected `"08/11/2026"` is the contract string, not formatted by calling the production formatter.
- Expected property `booking_id` is a fixed JSON key, not computed via the same naming strategy.
- Constructing `new BookingEvent(...)` in tests is fine; using the production service to build both expected and actual can hide bugs.
- For timezones, verify both the wire string preserving offset and the equivalent instant when the contract requires both.

This is an **independent test oracle**: expected values must originate from API requirements, not by repeating the implementation.

## 23. Common bugs and diagnostic directions

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| JSON has `bookingId` instead of `booking_id` | Naming not configured or different mapper used | Check `@JsonNaming`/global strategy and real mapper |
| One DTO renames fields, another does not | Class-level annotation or `@JsonProperty` override | Review type-level vs global scope |
| `@JsonAlias` "does not emit alias" | Alias applies only to deserialization | Use canonical name when serializing |
| Map keys do not become snake_case | Naming strategy normally applies to POJO properties | Transform Map keys intentionally/custom serializer |
| Null field still serialized | `ALWAYS` default or inclusion config not applied to mapper/type | Assert `has("field")`, check `@JsonInclude` |
| Empty string field omitted | `NON_EMPTY` is active | Change contract/inclusion if empty carries meaning |
| Both null and missing become null | Plain DTO does not track presence | Use `JsonNode`/typed tri-state wrapper for PATCH |
| Enum outputs `"QUEUED"` instead of `"queued"` | Missing `@JsonValue`/enum config | Explicit wire code + test |
| JSON enum is number `0` | Ordinal serialization enabled/misconfigured | Never use ordinal as a wire contract |
| Unknown enum code silently becomes null | Unknown-as-null feature enabled | Check mapper features, add negative test |
| `LocalDate` outputs array `[2026,11,8]` | Timestamp feature/module config | Disable `WRITE_DATES_AS_TIMESTAMPS` or use `@JsonFormat` |
| `OffsetDateTime` converts `+07:00` to `Z` | Context timezone adjustment on deserialization | Check feature, assert exact offset/instant |
| `java.time` type fails to serialize | Mapper lacks `JavaTimeModule` | Use Boot mapper or register the right module |
| `spring.jackson.date-format` does not change `LocalDate` | Not a universal format for all `java.time` types | Use `@JsonFormat`/JavaTime customizer |
| `spring.mvc.format.date` does not change JSON | MVC conversion differs from Jackson JSON | Configure the proper Jackson layer |
| HTTP JSON API differs from unit tests | MVC converter uses a different mapper/config | Test with `@WebMvcTest`, inspect `ObjectMapper` beans |
| HTTP POST 400 instead of 200 | Invalid JSON parser/enum/date | Check body and `HttpMessageNotReadableException` root cause |
| HTTP 401/403 in web test | Security filters/CSRF present | Configure Spring Security Test or proper test profile |
| Date test fails only on CI | Relied on default locale/timezone/`now()` | Fixed values, explicit offsets, consistent config |
| Jackson imports fail after Boot 4 upgrade | Jackson 3 packages and modules differ | Upgrade dependencies consistently, check migration guide |
| Test passes yet production clients fail | Only round-trip tested, expected self-computed | Fixed wire JSON + HTTP contract tests |

### 23.1. Reading Jackson errors properly

When encountering `InvalidFormatException`, `MismatchedInputException`, `ValueInstantiationException`, or `JsonMappingException`, inspect:

1. Path of the failing property (e.g. `created_at`/`state`).
2. JSON token type: string, number, object, array, null.
3. Whether the Java target type is right.
4. Whether the date/time pattern and offset match.
5. Jackson features/defaults on the active mapper.
6. Whether annotations sit on the right property/accessor/record component.
7. Whether invalid data maps to HTTP 400/422 per contract.

Do not just edit the test's expected value to match actual JSON and ignore backward compatibility.

### 23.2. MVC 400 errors often happen before the controller

When `@RequestBody` JSON fails to parse (bad enum code or invalid date), the Spring MVC converter can throw `HttpMessageNotReadableException` before the controller method runs. Thus `@MockBean BookingQueryService` has no effect on decode errors in `POST /echo`.

If input validation must run **after** deserialization, use `@Valid` and a validator; do not confuse a 400 parse error with a 400 Bean Validation error.

## 24. Versioning: Boot 3.3/Jackson 2 and Boot 4/Jackson 3

This runnable project intentionally uses:

```java
import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
```

This is the **Jackson 2 import set** managed by the Spring Boot 3.3 BOM.

Starting with Spring Boot **4.0** and Spring Framework 7, Jackson 3 becomes the default in Spring Boot starters/auto-configuration; Jackson 2 retains a transitional compatibility path, yet you should not mix Jackson 2 and 3 artifacts arbitrarily. New packages include `tools.jackson.*` for mappers/core and several test/Jackson configurations change, while some annotations stay in library/version-specific packages.

**Do not upgrade to Boot 4, copy the Gradle/Java sample verbatim, and assume APIs remain unchanged.** Instead:

1. Use the Boot BOM and test starters matching the supported major version.
2. Check whether Jackson 2 or 3 is actually on the runtime classpath.
3. Update imports/mapper builders/customizers per the official migration guide.
4. Verify naming, null inclusion, enum codes, and date/time feature behavior with regression tests.
5. Check `@JsonTest`/`JacksonTester` against the mapper auto-configured in the new Boot version.
6. Check HTTP message converters in MVC/WebFlux, since standalone JSON mapper tests may not reflect every endpoint.
7. Keep the Jackson 2 compatibility layer only as a controlled transition step, never mixing incompatible modules.

In Spring Boot **3.4/3.5**, Jackson 2 remains primary for the 3.x line; however, annotations like `@MockBean` in MVC slices become deprecated in favor of Spring Framework's new `@MockitoBean`. When migrating, update both test doubles and the JSON mapper version consistently via the BOM.

## 25. Checklist when reviewing DTO JSON contracts

- [ ] Independent JSON contract example exists, separate from Java class implementation.
- [ ] Aware whether naming comes from global `spring.jackson.*` or `@JsonNaming` on the DTO.
- [ ] Fields with `@JsonProperty` have verified output names.
- [ ] `@JsonAlias` is used intentionally only for input backward compatibility.
- [ ] DTO POJO property names are not confused with dynamic `Map` keys.
- [ ] Null rules are explicitly specified: missing, explicit null, empty string/list.
- [ ] `@JsonInclude` is not used as a substitute for validation or PATCH presence tracking.
- [ ] Enums emit explicit wire codes, independent of `name()`/`ordinal()`.
- [ ] Unknown enum inputs have an explicit fail/fallback policy.
- [ ] `LocalDate` and instant/offset/timezone types are chosen for their true semantics.
- [ ] Date/time patterns are tested at year boundaries, leap days, and offsets/DST where relevant.
- [ ] `LocalDateTime.now()` is not used in expected API snapshots.
- [ ] Mapper in tests is Boot-configured or a standalone mapper explicitly configured with matching modules/features.
- [ ] Both JSON serialization **and** deserialization are tested; round-trips are not the sole proof.
- [ ] Negative tests cover invalid enums/dates and missing/null fields per contract.
- [ ] A web-layer test verifies HTTP converters and controller JSON output when important.
- [ ] If moving to Boot 4, Jackson 3 migration and test modules have been reviewed.
- [ ] Sensitive raw requests/responses are not logged solely to debug JSON failures.

## 26. Practice exercises

### Exercise 1 — Change strategy and observe tests

In `BookingEvent`, temporarily remove `@JsonNaming(SnakeCaseStrategy.class)`. Run `BookingEventJsonTest`. Which test turns red? Why? Restore the annotation.

**Hint:** keys `booking_id`/`created_at` will no longer match in JSON output. Do not change expected values to match if the public API contract has not changed.

### Exercise 2 — Change null policy

Replace `@JsonInclude(NON_NULL)` with `ALWAYS` and run serialization tests. Why does `optional_note` appear as JSON null? Next try `NON_EMPTY` with `optionalNote=""` and distinguish empty from missing.

**Hint:** the output policy changes; it does not mean the deserializer now distinguishes PATCH field presence.

### Exercise 3 — Add an enum state

Add `RETRYING("retrying")` to `DeliveryState`. Write two tests:

- Serialize Java `RETRYING` to `"retrying"`.
- Deserialize `"retrying"` to `RETRYING`.

Then describe how to release the new value without breaking older clients; API versioning or client fallback may be needed.

### Exercise 4 — Distinguish missing and explicit null

Use `ObjectNode` to construct two JSON nodes, one missing `optional_note` and one with the field set to null. Prove that `has`/`isNull` distinguishes them while `BookingEvent.optionalNote` after deserialization is null in both cases. Design a dedicated PATCH DTO with tri-state representation.

### Exercise 5 — `yyyy` vs `YYYY`

Create a dedicated formatter/experiment for Dec 30, Dec 31, and Jan 01 in years where the week-based year differs from the calendar year. Write expected values by calendar date and find a case where `YYYY` returns a different year. Never alter production formats just because mid-year tests pass.

### Exercise 6 — Offset vs instant

Take `2026-11-08T09:30:00+07:00` and `2026-11-08T02:30:00Z`. Compare `toInstant()` and `getOffset()`. When the business contract requires preserving the user's offset, what should you assert? When it only requires an absolute audit timestamp, what should you assert?

### Exercise 7 — Intentionally build a misconfigured mapper

In a sandbox unit test, construct `new ObjectMapper()` and serialize `OffsetDateTime` without registering `JavaTimeModule`. Compare the exception/output against Boot's `@JsonTest` mapper. Explain why a unit mapper does not represent the MVC mapper.

### Exercise 8 — Global strategy affecting multiple DTOs

Enable global `spring.jackson.property-naming-strategy=SNAKE_CASE` in test configuration and serialize two DTOs without `@JsonNaming`. How does the output change? If the app has one legacy camelCase endpoint, what is a safe versioning strategy?

### Exercise 9 — Invalid requests through MVC

Using `BookingControllerWebTest`, send `"state":"delayed"` and `"travel_date":"not-a-date"`. Write status 400 assertions for both. If you want standardized error JSON codes, add `@RestControllerAdvice` and test meaningful JSON codes instead of default exception messages.

### Exercise 10 — Golden JSON contract

Create `expected-booking.json` in test resources with exact field names/enum/dates and no `optional_note`. Compare using `JacksonTester`/JSONAssert. Distinguish acceptable changes (whitespace/key ordering) from breaking changes (field renames, enum codes, date patterns).

## 27. Summary: a lean and effective test strategy

`Naming strategy`, `null inclusion`, `enum wire value`, and `date/time format` are all **protocol decisions**. They may not affect Java business logic, yet they break JSON clients immediately upon release.

A solid strategy:

1. **`@JsonTest`** as a fast guard for each important public DTO: fixed expected JSON + read path + negative inputs.
2. **`@WebMvcTest`** to guard key HTTP routes, confirming converters, content types, and error mapping use the same schema.
3. **Service/domain tests** verifying business logic without starting a web context.
4. **Full integration tests** added when needed to prove DB, cross-bean interactions, or live HTTP transport.
5. **Schema regression tests before major upgrades** to catch Jackson 2 to Jackson 3 changes before production clients discover them first.

Most importantly: **test JSON as data that external systems actually observe**, not merely as Java objects living inside the JVM.

## 28. Official Documentation

- Spring Boot 3.3 — Testing Spring Boot Applications, JSON tests: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Common Application Properties, `spring.jackson.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Boot 3.3 — JSON features and Jackson customization: https://docs.spring.io/spring-boot/3.3/reference/features/json.html
- Spring Boot 3.3 — `@JsonTest` API: https://docs.spring.io/spring-boot/3.3.6/api/java/org/springframework/boot/test/autoconfigure/json/JsonTest.html
- Jackson 2 — JsonInclude: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonInclude.html
- Jackson 2 — JsonFormat: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonFormat.html
- Jackson 2 — JsonCreator and JsonValue: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonCreator.html
- Jackson 2 — PropertyNamingStrategies: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/PropertyNamingStrategies.html
- Jackson 2 — JavaTimeModule: https://javadoc.io/doc/com.fasterxml.jackson.datatype/jackson-datatype-jsr310/latest/com/fasterxml/jackson/datatype/jsr310/JavaTimeModule.html
- Java SE 17 — DateTimeFormatter patterns: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html
- Spring Framework — Spring MVC testing MockMvc: https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html
- Spring — Introducing Jackson 3 support, migration context: https://spring.io/blog/2025/10/07/introducing-jackson-3-support-in-spring/
- JUnit User Guide: https://docs.junit.org/current/user-guide/