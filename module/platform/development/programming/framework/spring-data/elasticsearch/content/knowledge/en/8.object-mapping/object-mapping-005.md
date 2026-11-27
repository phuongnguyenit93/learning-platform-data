# Temporal Type Mapping and Custom Date Formats

In Elasticsearch, date and time are a data type with dedicated mapping support. Spring Data Elasticsearch allows declaring date/time fields on Java entities using `@Field`, while converting temporal types such as `Instant`, `LocalDate`, `LocalDateTime`, `OffsetDateTime`, or `Date` into formats that Elasticsearch understands.

When integrating the two systems, the challenge is rarely just picking a Java type. The application must also align on timezone semantics, time precision, outbound string formats, how Elasticsearch parses the input, and how APIs return dates to clients. If these layers follow different conventions, a value can drift by hours, lose millisecond precision, or be rejected during indexing.

This lesson explains the `date` and `date_nanos` types, how Java temporal types are mapped, how to configure custom `format` and `pattern` settings, how to handle timezones, and how to distinguish Elasticsearch formats from Jackson JSON formatting.

## 1. How Does Elasticsearch Represent Dates and Times?

Elasticsearch provides the `date` field type to store dates or points in time. During indexing, date values are normalized into an integer representing elapsed time since the Unix epoch (1970-01-01T00:00:00Z). For the `date` type, the internal unit is milliseconds. This enables Elasticsearch to sort, filter by time ranges, perform date math, and run aggregations on temporal data.

A `date` field can accept input values as:

- A date-time string matching one of the formats allowed by the mapping.
- An integer representing epoch milliseconds.
- A date-time value containing a timezone/offset, if the format supports that component.

Document example:

```json
{
  "eventName": "OrderCreated",
  "occurredAt": "2026-11-13T09:30:00Z"
}
```

Mapping:

```json
{
  "properties": {
    "occurredAt": {
      "type": "date"
    }
  }
}
```

Elasticsearch parses the string according to the field's format and normalizes the value for indexing. `_source` typically preserves the original JSON string sent in, whereas values used for sorting, range queries, and date operations are processed as Elasticsearch date types.

### 1.1. `date` and `date_nanos`

Elasticsearch offers two common temporal types:

| Type | Precision | Use Case |
|---|---|---|
| `date` | Milliseconds | Creation/update timestamps, business dates, schedules, standard logs |
| `date_nanos` | Nanoseconds | High-precision events, telemetry, or trading data needing to distinguish closely spaced instants |

`date_nanos` stores time with nanosecond precision but has a narrower representable range than `date` (roughly from year 1970 to 2262). Do not choose `date_nanos` merely because a Java type supports nanoseconds; select it when the system genuinely needs that precision and all participating components support it.

Elasticsearch field precision alone does not guarantee the application preserves full precision. If converters, Java types, JSON serializers, or upstream sources only supply milliseconds, the nanosecond portion is already lost before Elasticsearch receives the request.

## 2. Choosing the Right Java Temporal Type

The Java Time API provides several types for representing time. Choose a type based on business semantics, not merely on string formatting.

| Java Type | Meaning | Use When |
|---|---|---|
| `Instant` | An absolute point on the UTC timeline | Events, logs, creation/update timestamps, system timestamps |
| `OffsetDateTime` | Date and time with a specific UTC offset | APIs needing to preserve the offset supplied by clients |
| `ZonedDateTime` | Date and time tied to a timezone ID, e.g. `Asia/Ho_Chi_Minh` | Schedules or rules dependent on geographical timezones |
| `LocalDateTime` | Local date and time without offset/timezone | Wall-clock time when the business explicitly defines the timezone externally |
| `LocalDate` | Calendar date without time of day | Birthdays, invoice dates, calendar effective dates |
| `LocalTime` | Time of day without a date | Opening hours or daily recurring times; not a standalone timestamp |
| `java.util.Date` | An instant measured in epoch milliseconds | Integrating with legacy Java code |
| `Calendar` | An instant along with calendar/timezone rules | Legacy code requiring compatibility with older APIs |

For an event occurring at a specific moment, `Instant` is usually the clearest choice. It carries no user display timezone; it represents a single point in time. You can convert an `Instant` to a local timezone when displaying it.

`LocalDateTime` contains no timezone or offset. The value `2026-11-13T09:30:00` by itself does not indicate whether it is 09:30 in Vietnam, London, or UTC. If business logic uses `LocalDateTime`, you must establish the timezone at another layer and convert explicitly before comparing against absolute instants.

For calendar dates like birth dates, avoid arbitrarily turning them into UTC midnight if business logic does not require it. Using `LocalDate` preserves exact date meaning without introducing off-by-one-day shifts for users in other timezones.

## 3. Mapping Date Fields with `@Field`

In Spring Data Elasticsearch, `@Field` describes a property's data type in Elasticsearch mapping. Example entity with an order creation timestamp:

```java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "orders")
public class Order {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // Constructors, getters and setters
}
```

`FieldType.Date` creates an Elasticsearch `date` field mapping. Spring Data Elasticsearch uses mapping metadata and the conversion infrastructure to convert Java values into appropriate representations on read and write.

Conceptually, the corresponding mapping is:

```json
{
  "properties": {
    "status": {
      "type": "keyword"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
```

If no custom format is specified, Elasticsearch uses the default `date` format, typically `strict_date_optional_time||epoch_millis`. That accepts compliant ISO date-time strings or epoch milliseconds. When working with the default format, prefer ISO-8601 strings ending with `Z` or an explicit offset for absolute timestamps.

Supported Java Time types and exact conversion behavior depend on the Spring Data Elasticsearch version and configured conversions. Spring Data provides built-in conversions for common types; if you use custom types or special representation rules, a custom converter may be required.

## 4. Using `DateFormat` and `pattern` for Custom Formats

When an upstream system sends dates in a custom format, you can declare the format for the field. Spring Data Elasticsearch exposes `format` and `pattern` on `@Field`.

For example, a legacy system sends the string `2026-11-13 16:45:30`:

```java
import java.time.LocalDateTime;

import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.DateFormat;

@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "yyyy-MM-dd HH:mm:ss"
)
private LocalDateTime importedAt;
```

`DateFormat.custom` indicates the field uses a custom pattern. `pattern` describes the format Elasticsearch uses to parse the date-time. Spring Data uses this mapping metadata when creating the index and converting data.

The corresponding mapping in Elasticsearch looks like:

```json
{
  "properties": {
    "importedAt": {
      "type": "date",
      "format": "yyyy-MM-dd HH:mm:ss"
    }
  }
}
```

If you want to accept multiple input formats, Elasticsearch supports joining formats with `||`. Example:

```java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "yyyy-MM-dd HH:mm:ss||yyyy-MM-dd'T'HH:mm:ssXXX||epoch_millis"
)
private Instant occurredAt;
```

The mapping allows values matching any of the declared formats. Only accept source formats that genuinely need support. An overly broad format list makes incoming data unpredictable and can allow upstream systems to send the same field using conflicting conventions.

### 4.1. Distinguishing `format` and `pattern`

- `format` in the annotation lists Elasticsearch's built-in formats, represented by `DateFormat`.
- `pattern` provides a custom format pattern. When using a custom pattern, you normally declare `format = DateFormat.custom`.

Available enum values and format patterns depend on your Spring Data Elasticsearch and Elasticsearch versions. Check the API of the dependency in use if you need a specific format. Avoid inventing enum names or format names not present in your library version.

### 4.2. Using ISO-8601 format

For timestamps with offsets, you can declare a pattern accepting matching ISO-8601 strings:

```java
@Field(
    type = FieldType.Date,
    format = DateFormat.custom,
    pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"
)
private OffsetDateTime receivedAt;
```

Sample data:

```json
{
  "receivedAt": "2026-11-13T16:45:30.123+07:00"
}
```

`XXX` represents an offset such as `+07:00`. Because the offset is present, Elasticsearch can resolve an absolute point in time. In the Java application, `OffsetDateTime` makes it explicit that the value carries an offset.

If the system normalizes all timestamps to UTC, you can use strings ending with `Z` and the `Instant` type. Ensure the actual pattern and converter match the string shape sent by the application.

## 5. Timezones and UTC

Timezones are one of the most common causes of time drift when integrating applications with Elasticsearch.

A timestamp like `2026-11-13T16:45:30+07:00` and `2026-11-13T09:45:30Z` represent the exact same instant. The `+07:00` offset indicates local time is seven hours ahead of UTC. Once Elasticsearch parses the offset, it normalizes to the corresponding instant.

Conversely, the string `2026-11-13 16:45:30` has no offset. It is merely a date and time under an implicit convention. If the application, Elasticsearch, and the upstream source assume different timezones, the exact same string can be interpreted as different moments in time.

### 5.1. Convention for storing absolute timestamps

For event creation times, payment timestamps, or sync timestamps, standardize on storing absolute timestamps in UTC:

```java
Instant now = Instant.now();
```

When serialized as ISO-8601, the value looks like:

```text
2026-11-13T09:45:30Z
```

When displaying to users, convert to the appropriate timezone:

```java
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

String localText = DateTimeFormatter.ISO_OFFSET_DATE_TIME.format(
        now.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
             .toOffsetDateTime());
```

Storing UTC makes comparisons, sorting, and range queries consistent. Displaying local time is the responsibility of the presentation layer or API according to an agreed contract.

### 5.2. When should you use `LocalDateTime`?

`LocalDateTime` fits when a value means wall-clock time, such as “the store opens at 09:00” or “the appointment starts at 14:30” in a timezone already known from the location.

If you need to convert `LocalDateTime` to an absolute instant, you must supply a `ZoneId`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.Instant;

LocalDateTime localTime = LocalDateTime.of(2026, 11, 13, 16, 45);
Instant instant = localTime
        .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
        .toInstant();
```

Avoid implicitly relying on `ZoneId.systemDefault()` in business logic running across multiple servers. OS timezones can differ between developer laptops, containers, and production hosts. Use a business-defined timezone or store the timezone ID separately when reconstructing local schedules.

### 5.3. Offset and timezone ID are not the same

`OffsetDateTime` captures the offset at one point in time, such as `+07:00`. `ZonedDateTime` captures a timezone ID such as `Asia/Ho_Chi_Minh` or `Europe/Paris`, including historical rules and daylight saving time for that region.

An offset alone is insufficient to replay future timezone rules. If an application manages meeting schedules or opening hours, you may need to store both the local date-time and the timezone ID. If you only need to know when an event occurred, `Instant` is usually simpler and safer.

## 6. Calendar Date Types vs. Instant Types

Not all “date” data is a timestamp.

Example birth date:

```java
import java.time.LocalDate;

@Field(type = FieldType.Date, format = DateFormat.date)
private LocalDate birthDate;
```

A value like `1995-08-21` is a calendar date requiring neither time nor timezone. If you convert it into an `Instant` at UTC midnight, displaying it in another timezone can shift it to the previous day. Therefore, keep `LocalDate` when business logic only cares about the calendar date.

Example event timestamp:

```java
import java.time.Instant;

@Field(type = FieldType.Date)
private Instant eventTime;
```

This value pinpoints an absolute instant. When sent over an API, use ISO-8601 with `Z` or an offset.

`LocalTime` is also not a complete timestamp. If you need to store opening hours, you can store it as `keyword` or a suitable date/time representation matching your data contract, but do not treat it as a point on the timeline without a date and timezone.

## 7. Using `date_nanos` When Nanosecond Precision Is Required

If business requirements need to distinguish events occurring less than one millisecond apart, you can use Elasticsearch `date_nanos`.

Mapping example using Elasticsearch DSL:

```http
PUT telemetry
{
  "mappings": {
    "properties": {
      "capturedAt": {
        "type": "date_nanos"
      }
    }
  }
}
```

In Spring Data Elasticsearch, library versions supporting `FieldType.Date_Nanos` allow declaring:

```java
import java.time.Instant;

@Field(type = FieldType.Date_Nanos)
private Instant capturedAt;
```

Verify that `FieldType.Date_Nanos` exists in the Spring Data Elasticsearch version your project uses. If the version does not support this annotation, you may need to manage the mapping via index settings/templates or upgrade to a compatible dependency train.

Example value with nanoseconds:

```json
{
  "capturedAt": "2026-11-13T09:45:30.123456789Z"
}
```

Only choose `date_nanos` when both the source data and the conversion types preserve the needed precision. `Instant` can represent nanoseconds, whereas some converters or legacy `Date` types only retain milliseconds.

## 8. Creating Date/Time Mappings with Spring Data Elasticsearch

Spring Data can generate mappings from entity metadata. Full example:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.DateFormat;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "events")
public class EventDocument {

    @Id
    private String id;

    @Field(type = FieldType.Date)
    private Instant occurredAt;

    @Field(type = FieldType.Date, format = DateFormat.date)
    private LocalDate eventDate;

    @Field(
        type = FieldType.Date,
        format = DateFormat.custom,
        pattern = "yyyy-MM-dd HH:mm:ss"
    )
    private LocalDateTime importedAt;

    @Field(
        type = FieldType.Date,
        format = DateFormat.custom,
        pattern = "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"
    )
    private OffsetDateTime sourceTimestamp;

    // Constructors, getters and setters
}
```

The entity illustrates four semantics:

- `occurredAt`: an absolute point in time.
- `eventDate`: a calendar date.
- `importedAt`: a legacy date-time string without a timezone; its timezone must be agreed upon at the business layer.
- `sourceTimestamp`: a date-time with an offset embedded directly in the string.

When using annotations to create indices, ensure formats and patterns are compatible with the values emitted by converters. If an index already exists, changing annotations does not automatically alter the existing mapping.

### 8.1. Declaring custom settings and mappings

If you need custom analyzers, complex mappings, or versioned index management, you can create the index with explicit settings/mappings and then use the entity to map documents. Date mapping example in DSL:

```http
PUT events-v1
{
  "mappings": {
    "properties": {
      "occurredAt": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      },
      "importedAt": {
        "type": "date",
        "format": "yyyy-MM-dd HH:mm:ss||epoch_millis"
      }
    }
  }
}
```

The Spring Data entity must describe types compatible with this mapping. If mappings are managed via files or index templates, prevent auto-create index from generating a mapping different from the prepared one.

## 9. Querying Dates and Times

Once a field is mapped as `date`, you can use range queries to filter time intervals.

Example finding events within a single UTC day:

```http
GET events/_search
{
  "query": {
    "range": {
      "occurredAt": {
        "gte": "2026-11-13T00:00:00Z",
        "lt": "2026-11-14T00:00:00Z"
      }
    }
  }
}
```

Using `gte` and `lt` creates a half-open interval `[start, end)`, avoiding having to guess the last millisecond of the day. If business logic defines a day according to a local timezone, convert the start of that day and the start of the next day in that timezone to UTC before sending the query.

Elasticsearch also supports date math:

```http
GET events/_search
{
  "query": {
    "range": {
      "occurredAt": {
        "gte": "now-24h",
        "lte": "now"
      }
    }
  }
}
```

`now` is evaluated by Elasticsearch at query execution time. You can specify a timezone in range queries when working with calendar date math expressions and timezone-based intervals, provided the meanings of `now`, `time_zone`, `gte`, `lt`, and input formats are clearly established.

### 9.1. Querying a calendar date in a local timezone

Suppose you need to fetch events on 13/11/2026 in Vietnam time. Do not assume that day starts at `00:00Z`. Compute the local interval and convert it to UTC:

```java
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.Instant;

LocalDate date = LocalDate.of(2026, 11, 13);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant from = date.atStartOfDay(zone).toInstant();
Instant until = date.plusDays(1).atStartOfDay(zone).toInstant();
```

Then pass `from` as `gte` and `until` as `lt`. This approach also handles daylight saving time transition days in timezones with DST rules, where a local day is not always 24 hours long.

## 10. Distinguishing Elasticsearch Date Formats from Jackson JSON Formats

A Spring Boot application typically has at least two temporal conversion layers:

1. **Spring Data Elasticsearch mapping converter** converts Java entities into documents sent to Elasticsearch and back.
2. **Jackson HTTP message converter** converts Java objects into REST API JSON and back.

`@Field(format = ..., pattern = ...)` controls Elasticsearch's date-time mapping. It does not dictate the JSON string that Spring MVC returns to clients.

Conversely, `@JsonFormat` controls how Jackson serializes and deserializes JSON. It does not automatically change the field mapping in Elasticsearch.

Example:

```java
import java.time.Instant;

import com.fasterxml.jackson.annotation.JsonFormat;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Field(type = FieldType.Date)
@JsonFormat(shape = JsonFormat.Shape.STRING)
private Instant createdAt;
```

Here `@Field` describes the field type in Elasticsearch; `@JsonFormat` describes JSON representation via Jackson. If the API needs a specific pattern, declare pattern and timezone on `@JsonFormat` per the API contract. Do not use `@JsonFormat` as a substitute for `@Field(pattern = ...)` when configuring Elasticsearch mapping.

Keeping these two layers distinct prevents errors like “REST returns ISO-8601 but Elasticsearch rejects the string” or “Elasticsearch stores correctly but the API displays the wrong timezone”. When debugging, separately inspect the HTTP JSON request, the Java object after Jackson, the document produced by Spring Data, and the actual `_source` in Elasticsearch.

## 11. Custom Converters for Special Java Types or Business Rules

Common Java types usually already have converters in Spring Data Elasticsearch. If the application uses a custom type or requires conversion logic that standard date mappings cannot express, you can register custom converters.

For example, a legacy system represents time with a custom class:

```java
public record LegacyTimestamp(long epochMillis) {
}
```

You can define reading and writing converters between that type and a temporal type supported by Spring Data. Example illustrating conversion direction:

```java
import java.time.Instant;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class LegacyTimestampWriteConverter
        implements Converter<LegacyTimestamp, Instant> {

    @Override
    public Instant convert(LegacyTimestamp source) {
        return Instant.ofEpochMilli(source.epochMillis());
    }
}
```

A reading converter can convert `Instant` back into `LegacyTimestamp`:

```java
import java.time.Instant;

import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class LegacyTimestampReadConverter
        implements Converter<Instant, LegacyTimestamp> {

    @Override
    public LegacyTimestamp convert(Instant source) {
        return new LegacyTimestamp(source.toEpochMilli());
    }
}
```

This illustrates the conversion concept. The intermediate type and how Spring Data selects converters depend on the mapping context, document data types, and registered converters. For date fields, ensure the converter produces a value accepted by Elasticsearch's date mapping. If converting to a string, that string must match the field's format; if converting to an epoch number, standardize whether the unit is milliseconds or seconds.

Converters must be registered in `ElasticsearchCustomConversions` and included in the Spring Data Elasticsearch configuration appropriate for your version. Conceptual configuration example:

```java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.core.convert.ElasticsearchCustomConversions;

@Configuration
public class ElasticsearchConversionConfig {

    @Bean
    ElasticsearchCustomConversions elasticsearchCustomConversions() {
        return new ElasticsearchCustomConversions(List.of(
                new LegacyTimestampWriteConverter(),
                new LegacyTimestampReadConverter()
        ));
    }
}
```

Package names, constructors, and registration mechanisms for custom conversions can vary across release trains. Verify against the API of your Spring Data Elasticsearch version. Do not register broad converters for `String` or `Long` if they could alter how other fields across the application are converted.

## 12. Common Pitfalls When Mapping Dates and Times

### Date-time string does not match the mapping format

If the mapping accepts `yyyy-MM-dd HH:mm:ss` while the application sends `2026-11-13T16:45:30Z`, Elasticsearch may reject the document because the string does not match the format. Check the mapping and the actual string being sent; adjust the pattern or normalize inputs under a unified convention.

### Using `LocalDateTime` without specifying a timezone

`LocalDateTime` has no offset. If one system treats it as UTC while the application interprets it as Vietnam time, timestamps can be off by seven hours. Use `Instant`/`OffsetDateTime` for absolute instants or specify `ZoneId` explicitly when converting.

### Using epoch seconds instead of epoch milliseconds

Elasticsearch `date` treats integers as epoch milliseconds by default. If an upstream source sends epoch seconds without the mapping declaring a corresponding format or a converter scaling by 1000, dates can land in 1970 or an unexpected day. Establish the unit clearly at both the API and converter levels.

### Losing nanosecond precision

The `date` field only supports millisecond precision. If nanoseconds are required, use `date_nanos` and verify the entire conversion pipeline preserves precision.

### Changing annotations without updating old mappings

An existing index's mapping does not automatically reflect all changes in an entity. Inspect `_mapping`; if you need an incompatible date type or format change, create a new index and reindex data following a migration procedure.

### Confusing `@JsonFormat` with `@Field(pattern = ...)`

`@JsonFormat` affects Jackson JSON; `@Field` affects Elasticsearch mapping/conversion. When the API and Elasticsearch use different formats, configure both layers consistently.

### Storing calendar dates as UTC timestamps

Birth dates or invoice dates are not necessarily instants. Converting a `LocalDate` to UTC midnight and displaying it in another timezone can shift the date backward or forward. Keep `LocalDate` when business logic only cares about the calendar date.

## 13. Inspecting Actual Mappings and Documents

Once the application has created the index, inspect the mapping:

```http
GET events/_mapping
```

Inspect the document in `_source`:

```http
GET events/_doc/event-100
```

Test a date range query:

```http
GET events/_search
{
  "query": {
    "range": {
      "occurredAt": {
        "gte": "2026-11-13T00:00:00Z",
        "lt": "2026-11-14T00:00:00Z"
      }
    }
  }
}
```

If the mapping allows multiple formats, test each input format in a test environment to confirm Elasticsearch parses it properly. Also inspect the actual document written by Spring Data, not just the Java object values prior to calling `save`.

When you need to inspect date values formatted by Elasticsearch, you can use `fields` or `docvalue_fields` in the Search API with the desired format, depending on field type and query requirements. Formatted `fields` output does not mean `_source` was modified; those two mechanisms serve different purposes.

## 14. Design and Implementation Workflow

When adding temporal fields to a Spring Data Elasticsearch entity, follow this process:

1. Determine whether the data represents a calendar date, local wall-clock time, or an absolute instant.
2. Pick the Java type that reflects that meaning: `LocalDate`, `LocalDateTime`, `Instant`, `OffsetDateTime`, or another suitable type.
3. Choose the Elasticsearch field type: `date` for typical millisecond precision or `date_nanos` when nanoseconds are genuinely required.
4. Standardize timezones and epoch units across data sources, the application, and Elasticsearch.
5. Prefer the default ISO-8601 format if possible; only declare `DateFormat.custom` and `pattern` when compatibility with a custom format is required.
6. Verify the generated mapping with `GET index/_mapping`.
7. Inspect actual JSON and documents, then test range queries with representative timestamps.
8. Configure `@JsonFormat` separately if the REST API has a different format contract from Elasticsearch.
9. Use custom converters when data types or conversion rules go beyond default mapping capabilities.
10. When making incompatible mapping changes, create a new index and reindex instead of expecting annotations to alter an old index.

Accurate temporal mapping requires aligning on time semantics before choosing formats. `@Field` and Elasticsearch mappings govern how fields are stored, parsed, and queried; the Java Time API expresses date-time meaning in the application; Jackson formats API JSON. Keeping clear boundaries among these three layers avoids timezone shifts, precision loss, and format errors when Spring Data Elasticsearch converts objects.
