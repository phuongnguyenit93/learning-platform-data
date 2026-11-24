# Naming Conventions, Dates/Times, Timezones, and Null Values in JSON

An HTTP API needs more than valid JSON. **Field names**, **date/time semantics**, **timezones/offsets**, and **null representation** are all part of the data contract that frontends, mobile apps, third-party systems, and backend versions must agree upon. A seemingly small change—renaming `createdAt` to `created_at`, emitting timestamps without a timezone, or omitting `null` fields—can cause clients to misinterpret data without triggering any server compilation error.

This lesson belongs to the **JSON and codecs** group of the Spring Boot web runtime. It focuses on **naming conventions**, **Jackson serialization/deserialization**, **Java Time/ISO-8601**, **UTC and regional timezones**, **null vs. missing/empty**, validation, PATCH semantics, and contract tests. Examples use **Spring Boot 3.3.13, Spring Framework 6.1, Jackson 2, Spring MVC, Java 21, and Gradle**. WebFlux follows the same JSON contract principles but uses reactive HTTP codecs instead of the Servlet MVC path.

## 1. Java Models and Public JSON Contracts Are Two Separate Layers

Suppose Java defines:

~~~java
public record EventView(
    String eventId,
    String eventName,
    Instant occurredAt
) {}
~~~

A client may expect JSON:

~~~json
{
  "event_id": "evt-42",
  "event_name": "Java Conference",
  "occurred_at": "2026-11-07T03:04:05Z"
}
~~~

Java record components use `camelCase` per Java convention, whereas JSON uses `snake_case`. To maintain this mapping, the application must configure an explicit **naming strategy or annotations** rather than assuming Jackson knows the public convention.

Path of a JSON request/response in Spring MVC:

~~~text
HTTP request (Content-Type: application/json)
                 |
                 v
@RequestBody / HttpMessageConverter
                 |
                 v
Jackson ObjectMapper deserialize -> Java DTO
                 |
                 v
Controller / Service / Domain
                 |
                 v
Java response DTO
                 |
                 v
Jackson ObjectMapper serialize
                 |
                 v
HTTP response (Content-Type: application/json)
~~~

Spring WebFlux typically uses `HttpMessageReader` and `HttpMessageWriter` in a reactive codec chain. Both stacks can use Jackson; do not mistake MVC converter APIs as the sole API for WebFlux.

**Principle:** API DTOs form the public data boundary, while entities/databases/internal models can have their own structures and names. Serializing a JPA entity directly risks exposing internal fields, hitting lazy proxies/circular references, or unintentionally breaking JSON when changing database schemas.

## 2. Choosing and Maintaining a Field Naming Convention

| Convention | Example | Remarks |
| --- | --- | --- |
| `camelCase` | `eventId`, `occurredAt` | Familiar in JavaScript, Java |
| `snake_case` | `event_id`, `occurred_at` | Common in HTTP APIs, data pipelines |
| `kebab-case` | `event-id`, `occurred-at` | Less common in JSON objects |
| `PascalCase` | `EventId`, `OccurredAt` | Occasionally seen in legacy APIs |

There is no single mandatory standard. What matters is being **consistent, predictable, and never changing arbitrarily**. For example, an API mixing `created_at`, `updatedAt`, and `lastLogin_time` forces clients to remember three naming styles.

Helpful guidelines:

1. Use domain-descriptive names: `customer_id`, `payment_status`, `created_at`, `total_amount` instead of `data1`, `val`.
2. Boolean names should have clear semantics, such as `enabled` or `is_enabled`; pick one consistent style and test Jackson getter/record naming.
3. Have a convention for acronyms: `api_key`, `url`, `http_status`; in camelCase, `apiKey`, `httpStatus`. Avoid unusual JavaBean getters like `getURL()` unless naming output is tested.
4. If sending numbers with units, state them explicitly: `timeout_ms`, `duration_seconds`, `amount_minor_units`. Never make clients guess.
5. For business enums, keep value casing consistent (`PENDING` or `pending`) and document all possible values.
6. Never reuse an old field name with an entirely different meaning; use versioning/migration.
7. JSON keys are case-sensitive, so `eventId` differs from `eventID`.

### 2.1. When an API Has Already Been Released

Changing a field name can be a breaking change even when the Java backend compiles cleanly. Before changing conventions:

- Measure which clients still use the old field.
- Agree on a migration version and deprecation schedule.
- On input, you can accept a temporary alias.
- On output, you can retain the old field temporarily or publish a new API version.
- Maintain tests comparing JSON schemas/contracts, not just controller unit tests.

## 3. Three Ways to Configure JSON Field Names with Jackson

### 3.1. Global property-naming-strategy

Spring Boot 3.3 supports the official `spring.jackson.property-naming-strategy` property:

~~~yaml
spring:
  jackson:
    property-naming-strategy: SNAKE_CASE
~~~

When using the Boot-configured ObjectMapper, the Java property `occurredAt` typically serializes as `occurred_at`. The global strategy also affects deserialization of compatible DTOs.

**Scope note:** custom mappers created manually via `new ObjectMapper()` do not automatically receive Boot configuration; some libraries maintain their own ObjectMapper. A global policy also affects multiple APIs simultaneously, so do not enable it abruptly on a system serving production clients.

### 3.2. @JsonNaming on a Single API DTO

~~~java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;
import java.time.Instant;

@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record EventView(
    String eventId,
    String eventName,
    Instant occurredAt
) {}
~~~

This is a class fragment inside a project with Jackson, not a JDK-only Java program. The annotation is scoped to the type, allowing `snake_case` to be applied per DTO without changing other API contracts.

If both input and output use `snake_case`, configure/declare it consistently on **both request DTOs and response DTOs**. Do not update only the output and forget request binding.

### 3.3. @JsonProperty and @JsonAlias

When a legacy field requires an exact preserved name:

~~~java
public record LegacyInput(
    @JsonProperty("event_id")
    @JsonAlias("eventId")
    String eventId
) {}
~~~

This snippet requires imports from `com.fasterxml.jackson.annotation`. `@JsonProperty("event_id")` selects the primary JSON name, while `@JsonAlias("eventId")` lets deserialization accept the old name into the same field. **Aliases are for input**; serialization still emits only the primary name, never both keys.

If a client sends both the primary name and an alias, clarify expected behavior; avoid sending conflicting values and relying on JSON property order. Once migration finishes, consider removing old aliases.

### 3.4. Do Not Confuse Bean Property Names with Map Keys

Naming strategies primarily apply to Java bean/record property names. With `Map<String,Object>`, keys are treated as JSON data and **are not automatically converted to snake_case** like Java member names. Do not casually replace DTOs with Maps expecting naming policies to apply.

## 4. Dates and Times in JSON: Choosing Java Types by Meaning

JSON has no native date/time type. Strings or numbers only have meaning when the API contract defines how to interpret them.

| Java Type | Has Time? | Has Offset/Zone? | Example JSON | Suitable For |
| --- | --- | --- | --- | --- |
| `LocalDate` | No | No | `"2026-11-07"` | Birthdays, calendar dates, date-based deadlines |
| `LocalTime` | Time of day | No | `"09:30:00"` | Recurring opening hours |
| `LocalDateTime` | Yes | **No** | `"2026-11-07T10:04:05"` | Local wall-clock time without a defined instant |
| `Instant` | Yes | UTC point | `"2026-11-07T03:04:05Z"` | Created/updated timestamps, events, audits |
| `OffsetDateTime` | Yes | Offset `+07:00` or `Z` | `"2026-11-07T10:04:05+07:00"` | Timestamp with explicit offset |
| `ZonedDateTime` | Yes | IANA ZoneId | Requires explicit format or separate zone field | Calendars, DST, regional timezones |
| `Duration` | Elapsed span | No | `"PT15M"` or numeric with unit | Timeouts, durations |
| `Period` | Days/months/years | No | `"P1M"` | Calendar-based intervals |

In particular, `LocalDateTime` **has no timezone**. The string `2026-11-07T10:04:05` does not state whether it is UTC or Vietnam time. If client and server assume different timezones, they can disagree by hours while both parse the JSON without errors.

### 4.1. Instant for Absolute Events

Fields like `created_at`, `updated_at`, `processed_at`, and `expires_at` should represent an unambiguous point on the timeline. `Instant` enables comparing, calculating elapsed time, and storing independently of the server's default timezone.

~~~java
Instant instant = Instant.parse("2026-11-07T03:04:05Z");
~~~

With Jackson Java Time configured to write ISO strings, the corresponding JSON is `"2026-11-07T03:04:05Z"`.

### 4.2. OffsetDateTime Represents the Same Instant from a Different View

~~~text
2026-11-07T03:04:05Z
2026-11-07T10:04:05+07:00
~~~

These two strings represent the exact same instant. Java can verify this with `OffsetDateTime.parse(...).toInstant()`. An offset like `+07:00` is not an IANA zone name; multiple regions share an offset, and some regions shift offsets for daylight saving time.

### 4.3. LocalDate Differs from a Timestamp

A birthday `2026-11-07` is a calendar date; converting it to UTC midnight and displaying it in another timezone can shift it to the previous day. When business logic requires a **date-only** value, store `LocalDate` and serialize `yyyy-MM-dd` without adding meaningless time components.

## 5. UTC, IANA Timezones, and DST

A sound model:

~~~text
Client: local date/time + IANA zone (when business logic requires it)
                  |
                  v
Validate DST gap/overlap or offset policy
                  |
                  v
Resolve to Instant
                  |
             +----+----+
             |         |
             v         v
     Store/compare   Display via user's ZoneId
       as Instant
~~~

- **UTC** is a convenient reference scale for inter-service communication, especially for business timestamps.
- **ZoneId** such as `Asia/Ho_Chi_Minh` or `Europe/Paris` describes a region with historical/future timezone rules.
- **Offset** `+07:00` is merely the difference from UTC at one moment; it does not fully capture transition rules across all dates.
- **DST gap**: a local wall-clock interval can cease to exist when clocks spring forward.
- **DST overlap**: a local wall-clock time can map to two distinct instants when clocks fall back.

For example, a schedule of "09:00 every Monday in Paris" should not be saved as a permanent `+01:00` offset. You may need to store `LocalTime`, recurrence rules, and `Europe/Paris`, then resolve each occurrence into an instant using timezone rules.

**Never use `ZoneId.systemDefault()` to guess the client's timezone.** A developer machine might run `Asia/Ho_Chi_Minh`, production servers might run UTC, and a cluster might run elsewhere. Timezones must come from the contract, business config, or validated user preferences.

## 6. Date/Time String Standards to Publish

For machine-to-machine JSON:

- Calendar date: `yyyy-MM-dd`, e.g., `"2026-11-07"`.
- Timestamp: ISO-8601 / RFC 3339 with `Z` or offset, e.g., `"2026-11-07T03:04:05Z"`.
- Keep fractional seconds conventions consistent if clients expect fixed precision; `.123`, `.123456`, and `.123456789` carry different precisions.
- Avoid locale-dependent formats like `07/11/2026 10:04`: month/day order is ambiguous and timezone is missing.
- If using numeric epochs, explicitly state seconds vs. milliseconds, e.g., `timestamp_seconds` or `timestamp_ms`. Unit mismatches distort time by 1000x.
- Do not take the first 10 characters of a UTC timestamp to determine **the user's local calendar date**, as the same instant can fall on different dates across regions.
- If the API preserves nanosecond precision while the database stores milliseconds, publish rounding/truncation rules; never assume no precision is lost.

## 7. Jackson and Spring Boot 3.3: Configurable Serialization

`spring-boot-starter-web` typically pulls in Jackson via `spring-boot-starter-json`. Boot auto-configures `ObjectMapper` and supports `java.time` when the relevant Jackson modules are on the classpath.

To explicitly ensure Java Time objects are written as ISO strings rather than numeric timestamps/arrays:

~~~yaml
spring:
  jackson:
    serialization:
      write-dates-as-timestamps: false
~~~

Spring Boot 3.3 includes configuration keys such as:

- `spring.jackson.property-naming-strategy`: global Java bean naming.
- `spring.jackson.default-property-inclusion`: inclusion policy when **serializing responses**.
- `spring.jackson.time-zone`: formatting timezone in certain Jackson operations.
- `spring.jackson.serialization.*` and `spring.jackson.deserialization.*`: Jackson feature switches.

**Do not assume `spring.jackson.time-zone=UTC` turns every `LocalDateTime` into a zoned timestamp.** `LocalDateTime` itself carries no instant/zone. Certain Java Time serializers/deserializers have specific rules for preserving/adjusting offsets; if the contract requires absolute instants, normalize to `Instant` at the API boundary or define explicit policies and test them.

### 7.1. @JsonFormat and @DateTimeFormat Are Not Interchangeable

- `@JsonFormat` is a Jackson annotation for JSON serialization/deserialization on the corresponding field/type.
- `@DateTimeFormat` is typically used by Spring's `ConversionService` when binding query/path/form parameters; it does not automatically alter JSON `@RequestBody` parsing.

Example query fragment:

~~~java
@GetMapping("/calendar")
public String calendar(
        @RequestParam
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return date.toString();
}
~~~

Compare with a Jackson field fragment:

~~~java
public record CalendarView(
    @JsonFormat(shape = JsonFormat.Shape.STRING, pattern = "yyyy-MM-dd")
    LocalDate date
) {}
~~~

Both require appropriate imports and are not standalone Java programs. Only use custom patterns when required by the contract; `LocalDate` and `Instant` already have standard ISO representations.

## 8. Distinguishing Null, Missing, and Empty Values

JSON shapes:

~~~json
{}
~~~

~~~json
{"note":null}
~~~

~~~json
{"note":""}
~~~

~~~json
{"note":"Noted"}
~~~

~~~json
{"tags":[]}
~~~

| Representation | How Client/Server May Interpret It | Should Not Be Equated With |
| --- | --- | --- |
| Missing `note` | Not provided, unknown, or do not update | `null` |
| `"note":null` | No value or clear/remove command depending on PATCH contract | Empty string |
| `"note":""` | Explicit empty string provided | Missing key |
| `"note":"A"` | Has content | — |
| `"tags":[]` | List exists and is empty | Missing or null |
| `"enabled":false` | Explicit false value | Not provided |
| `"count":0` | Explicit number 0 | Not provided |

Exact semantics belong to the API contract. If a null field means "unknown," that differs from an empty collection meaning "known to have zero items."

### 8.1. Response Nulls and Input Nulls Are Two Directions

- **Serialization**: Is a Java null written as a JSON key with value `null`, or omitted?
- **Deserialization**: Are a missing key, explicit `null`, and empty string bound the same way or differently?
- **Business semantics**: For POST/PUT/PATCH, should these cases clear, preserve, apply a default, or reject?

Changing a JSON inclusion policy only adjusts **how responses are emitted**, not how update logic behaves.

## 9. @JsonInclude and Global default-property-inclusion

Common Jackson modes:

| Mode | Meaning |
| --- | --- |
| `ALWAYS` | Writes the property even when null if supported by the serializer |
| `NON_NULL` | Omits the key when the Java value is null |
| `NON_EMPTY` | Can omit null, empty strings, and empty collections/maps per Jackson's "empty" definition |
| `NON_ABSENT` | Omits null and absent states of certain supported reference types |
| `NON_DEFAULT` | Omits default values per Jackson rules; test carefully |

Example:

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record EventView(String eventId, String note) {}
~~~

`new EventView("evt-42", null)` typically produces JSON:

~~~json
{"eventId":"evt-42"}
~~~

With `ALWAYS`, it would be:

~~~json
{"eventId":"evt-42","note":null}
~~~

To apply globally, Spring Boot 3.3 supports `spring.jackson.default-property-inclusion`:

~~~yaml
spring:
  jackson:
    default-property-inclusion: non_null
~~~

This is an **ObjectMapper-wide policy** that can affect many endpoints; on released APIs, review for breaking changes.

**Avoid overusing NON_EMPTY**: a field `items: []` can be a valid, clearer state than a missing field. `false` and `0` are also often critical data; never silently drop them via unclear business heuristics.

## 10. Deserialization: Missing Keys Do Not Always Error

Example record:

~~~java
public record EventInput(
    String eventName,
    OffsetDateTime scheduledAt,
    String note
) {}
~~~

In common Jackson setups, both **missing `note`** and **explicit JSON `"note":null`** result in Java `note == null`. A Java record does not automatically treat fields as business-required; `@JsonProperty(required=true)` also has semantics tied to creators/deserializers and should not replace validation.

Use the validation starter when needed:

~~~groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
~~~

~~~java
public record EventInput(
    @NotBlank String eventName,
    @NotNull OffsetDateTime scheduledAt,
    String note
) {}
~~~

In the controller, use `@Valid @RequestBody EventInput input`. When a request has a blank name or missing/null `scheduledAt`, Bean Validation rejects it under the corresponding constraints, typically returning HTTP 400.

Remember:

- `@NotBlank` rejects null, empty strings, and whitespace-only strings for `CharSequence`.
- `@NotNull` requires a non-null reference.
- A malformed timestamp string causes a **JSON reading error** before validation runs.
- If using primitive `int`/`boolean` for optional fields, many bindings default missing keys to `0`/`false`, hiding "client did not send it"; use wrappers and presence tracking when needed.
- \`@JsonSetter(nulls=Nulls.FAIL)\` and SKIP/AS_EMPTY modes can customize explicit null handling, but do not replace a semantically clear data model.

## 11. PATCH: Absent Differs from Explicit Null

For partial updates:

~~~json
{"display_name":"An"}
~~~

can mean update one field and keep others unchanged; whereas:

~~~json
{"display_name":null}
~~~

can mean clear, set to null, or invalid. **Define the contract explicitly** rather than letting the framework guess.

In **JSON Merge Patch (RFC 7396)**, a null member means removing that member; its media type is `application/merge-patch+json`. In **JSON Patch (RFC 6902)**, the request is a distinct array of operations, typically with media type `application/json-patch+json`. A regular JSON endpoint **does not automatically implement RFC 7396** merely because it uses HTTP PATCH.

When you need to distinguish missing from explicit null before business logic, read via Jackson `JsonNode`:

~~~java
JsonNode note = json.path("note");

if (note.isMissingNode()) {
    // key is absent
} else if (note.isNull()) {
    // key present with JSON null
} else if (note.isTextual() && note.asText().isEmpty()) {
    // empty string
}
~~~

`json.path("note")` returns `MissingNode` for an absent key, whereas `json.get("note")` returns Java `null` when the key is absent and `NullNode` for JSON `null`. The snippet above is a fragment inside a method with a valid `JsonNode json`.

Do not implement PATCH by binding every field into a DTO without knowing which fields the client sent, then overwriting existing data with all null fields.

## 12. OpenAPI: required and nullable Are Separate Attributes

A field can be:

1. **Required, non-null**: key is always present, value must be a valid non-null type.
2. **Required, nullable**: key is always present, value may be null.
3. **Optional, non-null when present**: key may be omitted, but if present must not be null.
4. **Optional, nullable**: key may be omitted, and if present may be null.

Example OpenAPI 3.1/JSON Schema snippet:

~~~yaml
type: object
required:
  - event_id
  - occurred_at
properties:
  event_id:
    type: string
  occurred_at:
    type: string
    format: date-time
  note:
    type:
      - string
      - "null"
~~~

This is only a schema snippet, not a standalone OpenAPI document. `note` is not listed in `required`, so it may be omitted; if present, this example schema allows string or null. Never use the vague word "optional" while skipping whether null is valid.

## 13. Standalone Java: Two Representations of One Instant

Example requiring only **JDK 17+**, with no Spring/Jackson dependencies.

**TimeContractDemo.java**

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class TimeContractDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2026-11-07T03:04:05Z");
        OffsetDateTime local =
            OffsetDateTime.parse("2026-11-07T10:04:05+07:00");
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        ZonedDateTime displayed = instant.atZone(zone);
        LocalDate date = LocalDate.of(2026, 11, 7);

        System.out.println("Same instant: " +
            instant.equals(local.toInstant()));
        System.out.println("UTC: " + instant);
        System.out.println("Vietnam: " + displayed.toLocalDateTime());
        System.out.println("Calendar date: " + date);
    }
}
~~~

Run:

~~~bash
javac TimeContractDemo.java
java TimeContractDemo
~~~

Exact expected stdout:

~~~text
Same instant: true
UTC: 2026-11-07T03:04:05Z
Vietnam: 2026-11-07T10:04:05
Calendar date: 2026-11-07
~~~

`toLocalDateTime()` in this example only demonstrates displaying wall-clock time for a region; it is **not** a suggestion to convert API timestamps into zoneless `LocalDateTime`.

## 14. Runnable Spring Boot Project: Naming, Date-Time, and Null

A small project demonstrating:

- `camelCase` Java record components serialized/deserialized as `snake_case` JSON.
- `Instant` written as a UTC ISO string; offset `OffsetDateTime` input normalized via `toInstant()`.
- `LocalDate` expressing a calendar date; `zone_id` as an explicit field when required by business logic.
- `@JsonInclude(NON_NULL)` causing keys to be omitted; `ALWAYS` keeping explicit nulls.
- `JsonNode` distinguishing absent/null/empty.
- Validation rejecting blank names and null timestamps.

Structure:

~~~text
json-contract-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/jsoncontract/
    │   │   ├── JsonContractApplication.java
    │   │   └── JsonContractController.java
    │   └── resources/application.yml
    └── test/java/com/example/jsoncontract/
        └── JsonContractControllerTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'json-contract-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**src/main/java/com/example/jsoncontract/JsonContractApplication.java**

~~~java
package com.example.jsoncontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonContractApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonContractApplication.class, args);
    }
}
~~~

**src/main/resources/application.yml**

~~~yaml
spring:
  jackson:
    serialization:
      write-dates-as-timestamps: false
~~~

This configures temporal serialization; the example does not enable system-wide naming/inclusion because it uses annotations on specific DTOs.

### 14.1. Complete Controller and DTOs

**src/main/java/com/example/jsoncontract/JsonContractController.java**

~~~java
package com.example.jsoncontract;

import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.annotation.JsonNaming;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/json")
public class JsonContractController {

    private static final Instant FIXED_INSTANT =
        Instant.parse("2026-11-07T03:04:05Z");

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public record EventView(
        String eventId,
        String eventName,
        Instant occurredAt,
        Instant scheduledAt,
        LocalDate eventDate,
        String zoneId,
        String note
    ) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public record CreateEventRequest(
        @NotBlank String eventName,
        @NotNull OffsetDateTime scheduledAt,
        String note
    ) {}

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record NullDemo(
        String note,
        String emptyText,
        List<String> emptyTags
    ) {}

    @GetMapping(path = "/example",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public EventView example() {
        return new EventView(
            "evt-42", "Java Conference",
            FIXED_INSTANT, FIXED_INSTANT,
            LocalDate.of(2026, 11, 7),
            "Asia/Ho_Chi_Minh", null
        );
    }

    @PostMapping(path = "/echo",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public EventView echo(@Valid @RequestBody CreateEventRequest request) {
        // Echo/normalize input only; does not write to database.
        return new EventView(
            "evt-echo", request.eventName(),
            FIXED_INSTANT, request.scheduledAt().toInstant(),
            LocalDate.of(2026, 11, 7),
            "Asia/Ho_Chi_Minh", request.note()
        );
    }

    @GetMapping(path = "/null-policy",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public NullDemo nullPolicy() {
        return new NullDemo(null, "", List.of());
    }

    @PostMapping(path = "/inspect-note",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> inspectNote(@RequestBody JsonNode json) {
        JsonNode note = json.path("note");

        if (note.isMissingNode()) {
            return Map.of("state", "absent");
        }
        if (note.isNull()) {
            return Map.of("state", "null");
        }
        if (note.isTextual() && note.asText().isEmpty()) {
            return Map.of("state", "empty-string");
        }
        if (note.isTextual()) {
            return Map.of("state", "value", "value", note.asText());
        }
        return Map.of("state", "unsupported-type");
    }
}
~~~

Details to read carefully:

- `@JsonNaming` is declared on both `EventView` and `CreateEventRequest`, keeping input/output conventions synchronized.
- `EventView` uses `NON_NULL`, so `note == null` **does not appear** in JSON. `NullDemo` uses `ALWAYS`, so JSON includes key `note` with value null.
- `scheduledAt` input carries an offset: the controller normalizes via `toInstant()` before emitting `Instant`, avoiding assumptions that Jackson preserves offset strings across all configs.
- `zoneId` is an explicit field; it does not come automatically from the server timezone.
- `FIXED_INSTANT` aids deterministic testing. Production should inject a `Clock` and use real time rather than hard-coding timestamps.
- `inspectNote` only classifies states; it does not implement JSON Merge Patch or persist state.

### 14.2. Starting and Manually Verifying

With JDK 21 and a compatible Gradle 8.5+, in the project directory:

~~~bash
./gradlew bootRun
~~~

If the project lacks a wrapper yet has Gradle installed, generate the wrapper:

~~~bash
gradle wrapper --gradle-version 8.5
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

By default the application serves on port 8080 unless overridden.

Example GET:

~~~bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/api/json/example
~~~

Expected body; key ordering is not guaranteed:

~~~json
{
  "event_id": "evt-42",
  "event_name": "Java Conference",
  "occurred_at": "2026-11-07T03:04:05Z",
  "scheduled_at": "2026-11-07T03:04:05Z",
  "event_date": "2026-11-07",
  "zone_id": "Asia/Ho_Chi_Minh"
}
~~~

There is no `note` key in the JSON due to `NON_NULL`.

POST with an offset timestamp:

~~~bash
curl -i -X POST http://localhost:8080/api/json/echo \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "event_name":"Meeting",
    "scheduled_at":"2026-11-07T10:04:05+07:00",
    "note":null
  }'
~~~

Expected HTTP 200 and payload containing:

~~~json
{
  "event_id": "evt-echo",
  "event_name": "Meeting",
  "occurred_at": "2026-11-07T03:04:05Z",
  "scheduled_at": "2026-11-07T03:04:05Z",
  "event_date": "2026-11-07",
  "zone_id": "Asia/Ho_Chi_Minh"
}
~~~

Input `10:04:05+07:00` is normalized to `03:04:05Z` without changing the instant. Because the POST endpoint is an echo rather than resource creation, the demo returns 200 instead of claiming 201 Created.

### 14.3. Verifying Null, Empty, and Missing

~~~bash
curl -s http://localhost:8080/api/json/null-policy
~~~

JSON output:

~~~json
{"note":null,"empty_text":"","empty_tags":[]}
~~~

Try the input cases:

~~~bash
curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{}'

curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{"note":null}'

curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{"note":""}'

curl -s -X POST http://localhost:8080/api/json/inspect-note \
  -H "Content-Type: application/json" -d '{"note":"hello"}'
~~~

The four bodies in order:

~~~json
{"state":"absent"}
~~~

~~~json
{"state":"null"}
~~~

~~~json
{"state":"empty-string"}
~~~

~~~json
{"state":"value","value":"hello"}
~~~

Do not compare JSON responses as raw strings when unnecessary; JSON object keys can change order.

## 15. Testing API Contracts with MockMvc and JsonNode

**src/test/java/com/example/jsoncontract/JsonContractControllerTest.java**

~~~java
package com.example.jsoncontract;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(JsonContractController.class)
class JsonContractControllerTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper mapper;

    @Test
    void snakeCaseDateAndOmittedNullAreStable() throws Exception {
        MvcResult result = mvc.perform(get("/api/json/example")
                .accept(MediaType.APPLICATION_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.event_id").value("evt-42"))
            .andExpect(jsonPath("$.occurred_at")
                .value("2026-11-07T03:04:05Z"))
            .andExpect(jsonPath("$.event_date")
                .value("2026-11-07"))
            .andExpect(jsonPath("$.zone_id")
                .value("Asia/Ho_Chi_Minh"))
            .andReturn();

        JsonNode body = mapper.readTree(
            result.getResponse().getContentAsString());
        assertFalse(body.has("note"));
        assertFalse(body.has("eventId"));
        assertTrue(body.has("event_id"));
    }

    @Test
    void offsetInputIsNormalizedToUtcInstant() throws Exception {
        mvc.perform(post("/api/json/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "event_name": "Meeting",
                      "scheduled_at": "2026-11-07T10:04:05+07:00",
                      "note": null
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.event_name").value("Meeting"))
            .andExpect(jsonPath("$.scheduled_at")
                .value("2026-11-07T03:04:05Z"));
    }

    @Test
    void blankNameAndNullInstantAreInvalid() throws Exception {
        mvc.perform(post("/api/json/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"event_name":"","scheduled_at":null}
                    """))
            .andExpect(status().isBadRequest());
    }

    @Test
    void nullAndEmptyValuesRemainDifferent() throws Exception {
        MvcResult result = mvc.perform(get("/api/json/null-policy"))
            .andExpect(status().isOk())
            .andReturn();

        JsonNode body = mapper.readTree(
            result.getResponse().getContentAsString());

        assertTrue(body.has("note"));
        assertTrue(body.get("note").isNull());
        assertEquals("", body.get("empty_text").asText());
        assertTrue(body.get("empty_tags").isArray());
        assertEquals(0, body.get("empty_tags").size());
    }

    @Test
    void missingNullAndEmptyAreDifferentRequestStates() throws Exception {
        mvc.perform(post("/api/json/inspect-note")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("absent"));

        mvc.perform(post("/api/json/inspect-note")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"note\":null}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("null"));

        mvc.perform(post("/api/json/inspect-note")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"note\":\"\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.state").value("empty-string"));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

The assertions verify JSON field names, UTC timestamps, validation, and key **presence**, rather than just checking response status. `@WebMvcTest` uses the MVC test slice without opening a real Tomcat socket. The sample code/tests have been technically reviewed by source inspection; only claim "executed and passed" when Gradle actually runs and reports the outcome.

## 16. Common JSON Date/Null Mistakes

### 16.1. Emitting LocalDateTime While Calling It UTC

`"2026-11-07T10:04:05"` has no offset. If machine A treats it as UTC and machine B treats it as `+07:00`, times diverge by hours. API timestamps should emit `Instant` or offset-bearing strings per contract.

### 16.2. Relying on Server Default Timezone

`ZoneId.systemDefault()` depends on the JVM/container; dev and production can differ. Select timezones from domain/config or verified user preferences.

### 16.3. Taking the UTC Date as the User's Local Date

An instant near UTC midnight can belong to the next day in Vietnam or the previous day in other regions. To display local dates, convert the instant to the user's `ZoneId` before extracting `LocalDate`.

### 16.4. Thinking Offset +07:00 Is a Regional Timezone

An offset does not carry historical/future DST transitions. Future schedules need a `ZoneId` and a policy for DST gaps/overlaps.

### 16.5. Using @DateTimeFormat on JSON @RequestBody

JSON conversion is handled by Jackson, while `@DateTimeFormat` normally applies to `ConversionService` for query/path/form binding. Check `ObjectMapper`, JavaTime module, and DTO types.

### 16.6. Enabling NON_NULL API-Wide Without Review

Some clients distinguish null from missing. Changing `default-property-inclusion` can break behavior even though payloads look shorter.

### 16.7. Equating [] with null

An empty collection typically means "known to contain zero items"; null may mean "unknown/unloaded." Define semantics upfront and test them.

### 16.8. Using Primitives for Optional Fields

`false` or `0` can be silently defaulted when input is missing. If you need to distinguish absence, use wrapper types/presence tracking and proper validation.

### 16.9. Relying Only on @JsonProperty(required=true)

It does not replace `@Valid`/`@NotNull` and HTTP-boundary testing; creator/binding forms have distinct semantics.

### 16.10. Using JsonInclude Instead of PATCH Semantics

Inclusion affects serialization; PATCH needs to know missing keys, null keys, and explicit update policies, using `JsonNode` or `JsonNullable`/custom DTOs.

### 16.11. Changing Naming Strategy Abruptly

Switching camelCase to snake_case changes every wire key. That is a contract change requiring versioning, migration, and client tests.

### 16.12. Serializing JPA Entities Directly

Risks exposing sensitive data, reference cycles, or lazy proxies; use controlled API DTOs.

### 16.13. JSON Numbers for Currency

`double` has binary rounding errors; money/decimals need `BigDecimal` or minor units with explicit currency, unit, and precision. Do not treat `null` as `0` if business rules distinguish the two states.

### 16.14. Locale-Dependent Date Strings

A string like `07/11/2026` is month/day ambiguous across regions; use ISO formats and localize only in the UI.

## 17. Pre-Release JSON API Checklist

1. Does public JSON use camelCase or snake_case, and are there any exceptions?
2. Is naming configured via global `spring.jackson.property-naming-strategy`, `@JsonNaming`, or `@JsonProperty`?
3. Are input and output DTOs tested with the same convention?
4. Is anyone serializing entities or sensitive data straight into responses?
5. Are `created_at`/`updated_at` represented with `Instant`/offset-bearing timestamps?
6. Is `LocalDate` purely a calendar date without being turned into UTC midnight?
7. Do all timestamps clearly specify `Z`/offset, precision, and epoch units?
8. When business rules need regional timezones, are IANA `ZoneId` and DST policies defined?
9. Is anything relying on JVM default timezone or locale?
10. Are Jackson JavaTime config and `write-dates-as-timestamps=false` covered by contract tests?
11. Is `spring.jackson.time-zone` being mistakenly expected to add a zone to `LocalDateTime`?
12. Are required/nullable/optional states distinguished in OpenAPI?
13. Are null, missing, `""`, `[]`, `false`, and `0` given clear semantics?
14. Could global or per-type `NON_NULL`/`NON_EMPTY` drop data clients expect?
15. For PATCH, are absent and explicit null distinguished per contract/media type?
16. Are `@Valid` with `@NotBlank`/`@NotNull` enabled and tested?
17. If renaming fields, are migration/versioning and consumer contract tests in place?
18. Do tests cover non-UTC timezone offsets, invalid timestamps, near-midnight edges, and DST?
19. Do JSON tests assert parsed fields instead of object key order?
20. Is there official documentation for field names, date/time formats, null policies, and compatibility?

**Conclusion:** JSON in Spring Boot is a **data contract**. Field naming conventions should stay stable and consistent; `Instant` with ISO-8601/UTC suits absolute instants, `LocalDate` suits calendar dates, and `ZoneId` must be preserved when business logic involves regional wall-clock times. Above all, **absent fields, explicit nulls, and empty values** are not automatically identical; `@JsonInclude` only controls serialization, while request validation and PATCH semantics require dedicated design. Document them and protect them with contract tests.

## References

- [Spring Boot 3.3 — JSON](https://docs.spring.io/spring-boot/3.3/reference/features/json.html): Jackson auto-configuration, ObjectMapper, and custom serializers.
- [Spring Boot 3.3 — JSON application properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.jackson.property-naming-strategy`, `spring.jackson.default-property-inclusion`, serialization, and timezone.
- [Spring Framework — MVC HTTP Message Conversion](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html): converting JSON HTTP bodies.
- [RFC 3339 — Date and Time on the Internet](https://www.rfc-editor.org/rfc/rfc3339): offset timestamp format.
- [RFC 7396 — JSON Merge Patch](https://www.rfc-editor.org/rfc/rfc7396): null handling in merge patch.
- [RFC 6902 — JSON Patch](https://www.rfc-editor.org/rfc/rfc6902): JSON patch operations.
