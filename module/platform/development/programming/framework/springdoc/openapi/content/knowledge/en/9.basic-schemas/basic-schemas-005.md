# Dates, Times, Durations, UUIDs, and Formats to Cross-Check

APIs frequently exchange birth dates, delivery dates, transaction timestamps, opening hours, processing durations, or unique identifiers. In Java, these values have dedicated types such as **LocalDate**, **OffsetDateTime**, **Duration**, and **UUID**. In JSON, they are typically transmitted as strings. OpenAPI uses **type: string** combined with **format** to describe how the string should be interpreted, helping readers, Swagger UI, validators, and client generation tools understand the meaning of the data.

When using springdoc-openapi, schemas can be inferred from Java types and annotations. However, the Java type, how Jackson serializes JSON, and **format** in OpenAPI are three distinct layers. A document having **format: date-time** does not by itself guarantee the actual JSON includes a time zone; the **@Schema** annotation also does not automatically change how Jackson reads or writes data. You must design the contract first, configure appropriate converters, and verify the specification alongside actual requests and responses.

## 1. What Does format Mean in OpenAPI?

An OpenAPI schema describes JSON data types using values such as **string**, **number**, **integer**, **boolean**, **object**, and **array**. The **format** attribute adds a specific convention for a data type, for example:

~~~yaml
type: string
format: date
~~~

The schema above indicates that the value is a string representing a date in **date** format. Similarly, **format: uuid** indicates that the string has the form of a UUID. **format** helps tools render input UIs, validate data, or generate corresponding types for programming languages.

Do not treat **format** as the sole validation mechanism. Under OpenAPI 3.1, **format** is by default treated as an annotation that validators are not required to enforce. Support depends on each tool; a tool that does not recognize a format may simply fall back to **type: string**. Therefore, the API still needs to parse and validate data at runtime, while testing schemas with an appropriate validator.

OpenAPI 3.1 uses a schema system based on JSON Schema 2020-12 and the OpenAPI Format Registry. The date, time, duration, and UUID formats listed in the registry include **date**, **date-time**, **time**, **duration**, and **uuid**. The registry also distinguishes **date-time-local** and **time-local** for values without a time zone or offset. Tools are not required to support every format in the registry, so verify compatibility with the toolchain you use.

## 2. Choosing Java Types Based on Temporal Semantics

Before choosing a **format**, choose the right Java type. Types in **java.time** distinguish calendar dates, wall-clock times, absolute instants, and durations:

| Java Type | Meaning | Example Representation |
| --- | --- | --- |
| **LocalDate** | Calendar date without time or time zone | **2026-11-20** |
| **LocalTime** | Wall-clock time without date or time zone | **09:30:00** |
| **OffsetTime** | Wall-clock time with UTC offset | **09:30:00+07:00** |
| **LocalDateTime** | Local date and time without offset or time zone | **2026-11-20T09:30:00** |
| **Instant** | A point on the timeline, typically expressed in UTC | **2026-11-20T02:30:00Z** |
| **OffsetDateTime** | Date and time with UTC offset | **2026-11-20T09:30:00+07:00** |
| **ZonedDateTime** | Date and time attached to a time zone with rules, e.g., Asia/Ho_Chi_Minh | **2026-11-20T09:30:00+07:00[Asia/Ho_Chi_Minh]** |
| **Duration** | Time span measured in seconds and nanoseconds | **PT1H30M** |
| **Period** | Time span in calendar units such as years, months, days | **P1Y2M3D** |
| **UUID** | 128-bit identifier | **550e8400-e29b-41d4-a716-446655440000** |

**LocalDate** fits birth dates, holidays, or delivery dates. **LocalDateTime** fits when business logic only cares about local time, such as an appointment time at a known venue. **Instant** or **OffsetDateTime** fits event timestamps that need consistent comparison across systems.

**LocalDateTime** does not contain enough information to identify a single global point in time. For example, **2026-11-20T09:30:00** could mean 09:30 in many different time zones. If an API uses that value to schedule transfers, book tickets, or process cross-region events, specify a time zone or send an explicit zone ID. Do not implicitly assume UTC for **LocalDateTime** unless the contract explicitly defines it.

**OffsetDateTime** stores an offset, such as **+07:00**, but does not store a time zone name like **Asia/Ho_Chi_Minh**. **ZonedDateTime** carries region information and calendar transition rules. If you need to preserve the time zone region name across an API, consider publishing two separate fields, such as **localDateTime** and **timeZone** (**Asia/Ho_Chi_Minh**), instead of assuming every client understands the **[Asia/Ho_Chi_Minh]** suffix in Java strings.

## 3. Commonly Used Formats

The following table provides a useful schema convention for OpenAPI 3.1. For extended formats or those with narrower tool support, check the OpenAPI version and toolchain before publishing:

| Meaning | Suggested OpenAPI Schema | Example |
| --- | --- | --- |
| Calendar date | **type: string**, **format: date** | **2026-11-20** |
| Date-time with offset or UTC | **type: string**, **format: date-time** | **2026-11-20T09:30:00+07:00** |
| Date-time without time zone | **type: string**, **format: date-time-local** | **2026-11-20T09:30:00** |
| Time with offset | **type: string**, **format: time** | **09:30:00+07:00** |
| Time without offset | **type: string**, **format: time-local** | **09:30:00** |
| Duration | **type: string**, **format: duration** | **PT1H30M** |
| UUID | **type: string**, **format: uuid** | **550e8400-e29b-41d4-a716-446655440000** |

**date** and **date-time** are familiar formats from OpenAPI 3.0. In OpenAPI 3.1, formats such as **time**, **duration**, **uuid**, **date-time-local**, and **time-local** are documented in the JSON Schema/OpenAPI Format Registry ecosystem. For OpenAPI 3.0 documents, some tools still understand **uuid** or extended formats by convention, but do not assume every validator or client generator handles them identically.

For **LocalDateTime** and **LocalTime**, do not attach **date-time** or **time** solely because the Java type name contains Date or Time. RFC 3339 **date-time** and **time** formats include an offset component. If the string has no offset, use the corresponding local format when supported by the toolchain, or describe the pattern and semantics clearly in **description** when compatibility with older tools is needed.

## 4. Describing Schemas in OpenAPI YAML

The example below describes an event with a calendar date, start timestamp, local opening time, expected duration, and organizer identifier:

~~~yaml
components:
  schemas:
    Event:
      type: object
      required:
        - id
        - eventDate
        - startsAt
      properties:
        id:
          type: string
          format: uuid
          description: Event identifier
          example: 550e8400-e29b-41d4-a716-446655440000
        eventDate:
          type: string
          format: date
          description: Event date in the local calendar
          example: 2026-11-20
        startsAt:
          type: string
          format: date-time
          description: Start timestamp with UTC offset
          example: 2026-11-20T09:30:00+07:00
        doorsOpenAt:
          type: string
          format: time-local
          description: Opening time on the venue's local clock
          example: 08:45:00
        expectedDuration:
          type: string
          format: duration
          description: Expected duration in duration format
          example: PT1H30M
~~~

Attributes **required**, **description**, and **example** make the schema easier to use. **required** indicates that the field must be present in the object; it does not mean the string must be non-empty or valid for the format. **example** illustrates a value, but also does not replace validation. With OpenAPI 3.1, you can add **minLength**, **maxLength**, or **pattern** if specific string structure constraints are needed.

## 5. Declaring Java Types and Springdoc Annotations

springdoc-openapi reads Java types and OpenAPI annotations to generate schemas. Example of a DTO using a Java record:

~~~java
import java.time.Duration;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.UUID;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;

public record CreateEventRequest(
    @NotNull
    @Schema(
        description = "Event date",
        type = "string",
        format = "date",
        example = "2026-11-20"
    )
    LocalDate eventDate,

    @NotNull
    @Schema(
        description = "Start timestamp with offset",
        type = "string",
        format = "date-time",
        example = "2026-11-20T09:30:00+07:00"
    )
    OffsetDateTime startsAt,

    @Schema(
        description = "Local timestamp, without offset",
        type = "string",
        format = "date-time-local",
        example = "2026-11-20T09:30:00"
    )
    LocalDateTime localReminderAt,

    @Schema(
        description = "Expected duration",
        type = "string",
        format = "duration",
        example = "PT1H30M"
    )
    Duration expectedDuration,

    @NotNull
    @Schema(
        description = "Organizer identifier",
        type = "string",
        format = "uuid",
        example = "550e8400-e29b-41d4-a716-446655440000"
    )
    UUID organizerId
) {
}
~~~

**@Schema** is used to adjust the OpenAPI description. Here **type** and **format** publish a clear contract when Java types or library versions infer something different from the intended semantics. They do not change how Jackson serializes/deserializes JSON, nor do they automatically convert request parameters.

For many **java.time** types, swagger-core has model converters to infer schemas. The result depends on the swagger-core version used by springdoc and the configured OpenAPI version. Recent swagger-core releases added Java time mappings aligned with the OpenAPI Format Registry; springdoc release notes also record changes for **Duration**, **LocalTime**, and **OffsetTime**. Therefore, do not assume two projects using different springdoc versions will always generate the same **format**. Inspect **/v3/api-docs** and use **@Schema(format = "...")** to override when needed.

Some springdoc release notes also note that converters may generate the **partial-time** format for Java time types. This name is not in the currently common standard formats of the OpenAPI Format Registry. If **partial-time** appears in your project's documentation, check support in your validators and client generators; you can override it with **time-local** or **time** when the data semantics fit, or keep **type: string** with a clear pattern description to prioritize compatibility.

## 6. Distinguishing Request Conversion from OpenAPI Description

Three mechanisms are frequently confused:

| Mechanism | Role | Scope |
| --- | --- | --- |
| **@DateTimeFormat** | Specifies how Spring converts string values to Java types during web data binding | Query parameters, path variables, form fields, and Spring data binding |
| **@JsonFormat** | Specifies the shape Jackson uses when reading or writing JSON | JSON request bodies and response bodies |
| **@Schema** | Describes type, format, example, and meaning in the OpenAPI specification | API documentation and OpenAPI tools |

Example with a query parameter:

~~~java
import java.time.LocalDate;

import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/api/events")
public List<EventResponse> findByDate(
        @RequestParam("date")
        @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
        LocalDate date) {
    return eventService.findByDate(date);
}
~~~

Request:

~~~text
GET /api/events?date=2026-11-20
~~~

**@DateTimeFormat** instructs Spring how to parse the query string into **LocalDate**. For JSON bodies, Jackson handles conversion. If the application uses a custom pattern, configure Jackson accordingly, for example via **@JsonFormat** or **ObjectMapper**:

~~~java
import com.fasterxml.jackson.annotation.JsonFormat;
import java.time.OffsetDateTime;

public record EventPayload(
    @JsonFormat(shape = JsonFormat.Shape.STRING)
    OffsetDateTime startsAt
) {
}
~~~

In most APIs, prefer standardized ISO-8601/RFC 3339 formats over custom patterns. Custom patterns should only be used when required by the contract and must be clearly documented in OpenAPI. If **@Schema** publishes **date-time** while Jackson serializes as a numeric array or an offset-less string, documentation and actual data will mismatch.

## 7. Distinguishing Duration and Period

**Duration** and **Period** both represent time spans, but are used for different calculations:

- **Duration** represents a continuous amount of time in seconds and nanoseconds. For example, **Duration.ofHours(2)** can be represented as **PT2H**; **Duration.ofDays(1)** equals exactly 24 hours.
- **Period** represents calendar units such as years, months, and days. For example, **Period.ofMonths(1)** is one calendar month, not a fixed number of seconds; a month can have 28, 29, 30, or 31 days.

The **duration** format fits RFC 3339/ISO-8601 duration strings supported by tools. Examples:

| Value | Meaning |
| --- | --- |
| **PT15M** | 15 minutes |
| **PT1H30M** | 1 hour 30 minutes |
| **P2DT3H** | 2 days and 3 hours in duration representation |
| **P1Y2M3D** | 1 year, 2 months, and 3 days in calendar representation |

Do not use **Duration** to model a calendar month or a calendar year. If business logic requires renewal schedules, billing cycles, or monthly terms, choose **Period** or a separate number-of-months/days model and describe the calculation rules. If the API wants to pass a number of seconds instead of an ISO-8601 string, publish a numeric schema, unit, and clear range, e.g., **type: integer**, **format: int64**, **description: Duration in seconds**.

## 8. UUIDs and How to Publish Identifiers

Java provides **java.util.UUID** to represent 128-bit identifiers. In JSON, a UUID is typically serialized as a canonical string consisting of 5 hyphen-separated hexadecimal groups:

~~~text
550e8400-e29b-41d4-a716-446655440000
~~~

OpenAPI schema:

~~~yaml
type: string
format: uuid
example: 550e8400-e29b-41d4-a716-446655440000
~~~

With DTOs using **UUID**, Jackson can read/write UUID strings and springdoc typically infers a string schema. If you use **String** instead of **UUID**, declare **@Schema(type = "string", format = "uuid")** to publish the intent clearly. When using **String**, the application must also validate the string itself using a parser or appropriate constraint; **format: uuid** in documentation does not turn an arbitrary string into a UUID.

For path variables, Spring can bind directly:

~~~java
@GetMapping("/api/events/{id}")
public EventResponse getEvent(@PathVariable UUID id) {
    return eventService.getById(id);
}
~~~

If a client sends a value that cannot be parsed as a UUID, the request fails during conversion before reaching business logic. Define a standard error response for that case and document the appropriate status code in OpenAPI.

## 9. Inspecting Formats in Generated Documentation

After the application starts, open the default endpoint **/v3/api-docs** or your configured custom endpoint. Find the corresponding schema under **components.schemas** and verify:

1. Is **type** correctly **string** when data is transmitted as a string?
2. Does **format** match the semantics: **date**, **date-time**, **date-time-local**, **time**, **time-local**, **duration**, or **uuid**?
3. Is **example** syntactically valid and of the same data type as the schema?
4. Does the description clearly state time zone, offset, duration units, and UUID usage?
5. Do required fields, nullability, and validation match the DTO?
6. Does the actual JSON produced by Jackson have the same shape published by the schema?

You can inspect quickly by fetching the specification:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Then inspect the endpoint's actual JSON response, especially for **LocalDateTime**, **ZonedDateTime**, and **Duration**. Some Jackson configurations may serialize temporal values as strings, numbers, or other structures. If using a custom serializer/deserializer, the schema must describe the actual wire representation rather than relying solely on the Java type.

## 10. Validation and Common Pitfalls

**format** helps document conventions, while runtime validation must be handled in the application. You can combine:

- **@NotNull** to require the field to have a value;
- **@Past**, **@PastOrPresent**, **@Future**, or **@FutureOrPresent** for appropriate temporal rules;
- **@Pattern** if the API accepts strings with a custom pattern;
- dedicated Java types such as **LocalDate**, **OffsetDateTime**, **Duration**, or **UUID** so parsers reject invalid data;
- additional business checks when constraints on time zone, intervals, or multi-field relationships are needed.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| **LocalDateTime** is described as **date-time** despite having no offset | Java type lacks time zone but schema uses an offset format | Use **date-time-local** when supported by the toolchain, or clearly document pattern and local conventions |
| Timestamps shift when clients are in other time zones | API accepts **LocalDateTime** and parties interpret zones differently | Use **Instant**/**OffsetDateTime** or pass a separate zone ID per the contract |
| **ZonedDateTime** outputs string with **[Region/City]** while validator expects RFC 3339 | Java representation includes zone region outside standard date-time format | Use **OffsetDateTime**/**Instant** for timestamps or separate **zoneId** into its own field |
| **Duration** outputs a number instead of **PT...** string | Jackson configured to write durations as numbers or custom serializer | Align JSON serializer and schema; document unit if using numbers |
| Validator ignores **format: uuid** or **format: duration** | Tool does not support format or treats format as an annotation only | Verify validator capabilities and enforce validation on the server |
| Swagger UI displays temporal field as a plain string | UI does not support format or docs do not generate expected format | Inspect **/v3/api-docs**, swagger-core version, and **@Schema** annotations |
| Temporal query parameter fails to parse while JSON body works | **@DateTimeFormat** and Jackson have different configurations | Configure Spring data binding and JSON serialization separately |
| Invalid UUID is only caught inside the service | DTO uses **String**, skipping early parsing | Use **UUID** or validate the string before business processing |

One point to note is that **@DateTimeFormat** belongs to Spring data binding, whereas **@JsonFormat** belongs to Jackson. Adjusting one annotation does not guarantee both query parameters and JSON bodies change the same way. Test each request source separately.

## 11. Design Principles

Choose Java types based on business semantics, then choose schemas and formats that accurately reflect how data is transmitted over HTTP. Use **LocalDate** for calendar dates, **LocalTime** for local wall-clock times, **Instant** or **OffsetDateTime** for instants comparable across systems, **Duration** for continuous spans, and **UUID** for identifiers. Only use **LocalDateTime** when the time zone is understood from business context or transmitted separately.

Keep formats consistent across requests, responses, Jackson, and OpenAPI. When upgrading springdoc or swagger-core, review generated schemas for temporal types because converters may change how **format** is assigned. Do not rely on a single Swagger UI example to conclude data is validated; verify the specification, actual JSON, and application parsing behavior.

## 12. Official References

- [OpenAPI Specification 3.1.2 — Data Type Formats](https://spec.openapis.org/oas/v3.1.2.html#data-type-format) — role of **format** and optionality of validation.
- [OpenAPI Formats Registry](https://spec.openapis.org/registry/format/) — **date**, **date-time**, **date-time-local**, **time**, **time-local**, **duration**, and **uuid** formats.
- [Java SE — java.time](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/package-summary.html) — semantics of Java date and time types.
- [Spring Framework — Spring Field Formatting](https://docs.spring.io/spring/reference/core/validation/format.html) — **@DateTimeFormat**, **@DurationFormat**, and Spring data conversion.
- [Spring Boot — JSON](https://docs.spring.io/spring-boot/reference/features/json.html) — JSON mapper configuration and serializers/deserializers.
- [Swagger Core Releases](https://github.com/swagger-api/swagger-core/releases) — Java time converter changes and OpenAPI Format Registry support.
- [Springdoc OpenAPI Releases](https://github.com/springdoc/springdoc-openapi/releases) — schema mapping changes across springdoc versions.

When schemas accurately describe dates, times, durations, and UUIDs, clients can construct data following shared conventions and tools can provide better verification. What matters most is consistency across Java types, serialized JSON, OpenAPI formats, and runtime validation rules in the Spring Boot application.
