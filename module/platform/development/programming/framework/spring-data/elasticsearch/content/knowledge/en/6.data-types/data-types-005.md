# `date`, `date_nanos`, Formats, and Time Zones

Elasticsearch provides two primary temporal data types: `date` and `date_nanos`. Both represent a point in time on the timeline and support range filtering, sorting, and time-based aggregations. The most important difference is precision: `date` stores time at millisecond precision, whereas `date_nanos` supports nanosecond precision.

When working with Spring Data Elasticsearch, choosing the right field type is only the first step. The application must also align on date-time string formats, Java type conversions, and time zones when writing and querying. If these conventions are unclear, data can suffer time shifts, lose sub-millisecond parts, or be filtered inaccurately at day boundaries.

## 1. Two Temporal Data Types in Elasticsearch

### 1.1. The `date` Type

The `date` type suits most business data with millisecond precision, such as:

- Record creation or update timestamps.
- Article publication dates.
- Order creation or payment timestamps.
- Session start and end times.
- Contract expiration dates or appointment schedules.

Elasticsearch converts `date` values into an integer representing milliseconds since the Unix epoch, namely `1970-01-01T00:00:00Z`. As a result, data can be sorted and compared efficiently as numeric values.

A `date` field can accept date-time strings in a declared format or epoch millisecond numbers. When returning results, the display format depends on the API and how the application converts data; Elasticsearch does not preserve the original input text as a raw string.

### 1.2. The `date_nanos` Type

The `date_nanos` type stores time with nanosecond precision. It is useful when events can occur very close together and millisecond-level ordering is insufficient, for example:

- High-frequency telemetry data.
- Transaction events or logs requiring distinction between very close timestamps.
- System observability data with high-resolution timestamps.
- Scientific or device data with clocks outputting nanoseconds.

`date_nanos` uses a 64-bit integer representation of epoch nanoseconds. Because this integer's range is finite, the supported date span is narrower than `date`; in Elasticsearch documentation, the practical range of `date_nanos` is commonly stated as roughly 1970 to 2262. If the system must store historical dates far before the epoch or dates far into the future, verify the bounds of your deployed Elasticsearch version before selecting this type.

### 1.3. Comparing `date` and `date_nanos`

| Criterion | date | date_nanos |
|---|---|---|
| Precision | Milliseconds | Nanoseconds |
| Internal representation | Epoch milliseconds | Epoch nanoseconds |
| Date range | Wide, suitable for ordinary calendar dates | Narrower due to 64-bit integer limits |
| Size and overhead | Usually more suitable for general timestamps | Can consume more resources depending on workload |
| Use cases | Business timestamps, created/updated dates, schedules | Telemetry or events requiring nanosecond resolution |

Do not choose `date_nanos` merely because it has higher precision. If the data source only provides milliseconds, storing nanoseconds adds no extra temporal information. Choose precision based on business requirements, input timestamp quality, date span, and storage/query overhead.

## 2. Date-Time Formats (`format`)

Elasticsearch mapping specifies which formats are accepted when parsing input values. A field can declare one format or multiple formats joined by the `||` delimiter. Elasticsearch tries the formats in order to parse values.

### 2.1. Default Formats

If no format is declared, the `date` type defaults to:

~~~text
strict_date_optional_time||epoch_millis
~~~

This means the field can accept strict ISO-formatted date-time strings or epoch millisecond numbers.

The `date_nanos` type has a corresponding default for strings with nanosecond precision:

~~~text
strict_date_optional_time_nanos||epoch_millis
~~~

Examples of date-time strings readable by ISO formats:

~~~text
2025-04-18
2025-04-18T09:30:00Z
2025-04-18T09:30:00.123Z
2025-04-18T09:30:00.123456789Z
2025-04-18T16:30:00+07:00
~~~

Values with nanosecond fractional parts require `date_nanos` if full precision must be preserved. With `date`, time values are stored at millisecond precision.

### 2.2. Declaring Formats in Mapping

Mappings can be declared explicitly via the REST API:

~~~http
PUT /application-events
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "createdAt": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      },
      "measuredAt": {
        "type": "date_nanos",
        "format": "strict_date_optional_time_nanos||epoch_millis"
      }
    }
  }
}
~~~

Document example:

~~~http
POST /application-events/_doc
Content-Type: application/json

{
  "createdAt": "2025-04-18T09:30:00.123Z",
  "measuredAt": "2025-04-18T09:30:00.123456789Z"
}
~~~

The `createdAt` field suits standard timestamps. The `measuredAt` field can preserve the nanosecond part thanks to `date_nanos`.

### 2.3. Combining Multiple Formats

An application may receive data from multiple sources—for instance, one source sends ISO-8601 while another sends epoch milliseconds. You can declare multiple formats:

~~~json
{
  "mappings": {
    "properties": {
      "eventTime": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis"
      }
    }
  }
}
~~~

Do not expand the format list arbitrarily. Every added format increases the number of representations the application must understand and test. Ideally, normalize data at the system boundary so producers send a unified format.

### 2.4. Custom Formats

If input data has a custom format, you can declare the corresponding pattern. For example, a legacy system sends date-time as year-month-day, space, hour-minute-second:

~~~http
PUT /legacy-events
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "eventTime": {
        "type": "date",
        "format": "yyyy-MM-dd HH:mm:ss"
      }
    }
  }
}
~~~

Document:

~~~json
{
  "eventTime": "2025-04-18 09:30:00"
}
~~~

The pattern must match the actual data and how Elasticsearch interprets date-time symbols. Different symbols have different meanings, for example:

| Symbol | Common meaning |
|---|---|
| yyyy | Calendar year |
| MM | Month |
| dd | Day of month |
| HH | Hour in 24-hour clock |
| mm | Minute |
| ss | Second |
| S | Fractional second |
| XXX | Time zone offset such as +07:00 |

Do not confuse `MM` (month) with `mm` (minute). If the pattern does not include an offset or zone, the input string carries no time zone information on its own; Elasticsearch will apply its default rule when parsing.

For new systems, prefer ISO-8601 with an explicit offset, such as `2025-04-18T16:30:00+07:00`, or UTC with the `Z` suffix. Custom patterns should only be used when integrating legacy data.

## 3. Epoch Time: Seconds and Milliseconds

The Unix epoch is `1970-01-01T00:00:00Z`. An epoch timestamp represents the elapsed duration since this reference point.

Two common units:

- Epoch second: seconds since the epoch.
- Epoch millisecond: milliseconds since the epoch.

Example:

~~~text
2025-01-01T00:00:00Z

epoch seconds      = 1735689600
epoch milliseconds = 1735689600000
~~~

The unit difference is a factor of 1,000. Sending a seconds value to a field expecting milliseconds causes Elasticsearch to interpret it as milliseconds and produce a timestamp near early 1970. This is a common bug when integrating JavaScript, Java, devices, and external APIs.

If you want to accept epoch seconds, the mapping must declare the appropriate format, for example:

~~~json
{
  "eventTime": {
    "type": "date",
    "format": "epoch_second"
  }
}
~~~

If the system needs both ISO strings and epoch seconds, you can declare:

~~~json
{
  "eventTime": {
    "type": "date",
    "format": "strict_date_optional_time||epoch_second"
  }
}
~~~

Standardize units in the API contract. A property name like `createdAt` does not tell you whether the accompanying integer is in seconds or milliseconds; API documentation and data types should make the unit explicit.

## 4. Time Zones and How Elasticsearch Normalizes Time

### 4.1. Absolute Instants and Local Time

An absolute instant identifies a unique point on the timeline. For example:

~~~text
2025-04-18T09:30:00Z
2025-04-18T16:30:00+07:00
~~~

These two representations refer to the exact same instant: 09:30 UTC corresponds to 16:30 in the UTC+07:00 time zone.

Conversely, the string `2025-04-18 16:30:00` has no offset or zone. It only tells you that a local clock reads 16:30; the exact absolute instant cannot be determined without knowing the assumed time zone.

Elasticsearch normalizes `date`/`date_nanos` values into a UTC-based epoch representation. The offset provided in the string is used to compute the corresponding instant. The original time zone name, such as `Asia/Ho_Chi_Minh`, is not retained as part of the `date` value after normalization.

If business logic needs to know the original time zone chosen by the user, store the zone ID separately, for example:

~~~json
{
  "scheduledAt": "2025-04-18T09:30:00Z",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

Here `scheduledAt` represents the absolute instant; `timeZone` stores the local calendar context so it can be displayed or recalculated according to business rules.

### 4.2. Strings Without a Time Zone

If a date-time string has no offset or zone, Elasticsearch defaults to interpreting it as UTC. For example:

~~~text
2025-04-18T16:30:00
~~~

This value is interpreted as 16:30 UTC, not automatically as 16:30 in the time zone of the application host or user.

Therefore, avoid sending local date-times without offsets unless producer and consumer agree on the convention. Convert to an instant with an offset/UTC before sending, or explicitly specify the zone in the application's conversion pipeline.

### 4.3. Converting Between Vietnam Time and UTC

Vietnam uses the UTC+07:00 time zone. For example, `2025-04-18T16:30:00+07:00` corresponds to `2025-04-18T09:30:00Z`.

When storing instants from a Vietnam-based application, send ISO-8601 strings with an offset or convert to `Instant`/UTC before writing. When displaying, convert the UTC instant to the `ZoneId` appropriate for the user.

Do not hardcode adding or subtracting seven hours across multiple layers. Let the date-time library handle converting `Instant` to `ZoneId`; this is clearer and prevents bugs when the application serves users across multiple countries.

## 5. Using Time Zones in Range Queries

When filtering data by a local time interval, day boundaries must be converted according to the right time zone. Elasticsearch range queries support the `time_zone` parameter.

Example finding events on April 18, 2025 in Vietnam time:

~~~http
POST /application-events/_search
Content-Type: application/json

{
  "query": {
    "range": {
      "createdAt": {
        "gte": "2025-04-18T00:00:00",
        "lt": "2025-04-19T00:00:00",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

Elasticsearch interprets the two local bounds using the `+07:00` offset and converts them to UTC instants for comparison. Using `gte` for the start and `lt` for the end avoids double-counting an event occurring at midnight of the following day.

If sending bounds with explicit offsets, such as:

~~~json
{
  "gte": "2025-04-17T17:00:00Z",
  "lt": "2025-04-18T17:00:00Z"
}
~~~

then those values already express unambiguous absolute instants. There is no need to add `time_zone` only to re-convert the same bounds.

The `format` parameter on a range query can be used to parse input bounds using a specific format. If omitted, Elasticsearch uses the field mapping's format. Distinguish the mapping's format (which governs what data the field accepts) from the query's format (which governs how bounds in the search request are parsed).

## 6. Date Math and the Current Time

Elasticsearch supports date math in temporal queries. The `now` symbol represents the current time. Time units can be added/subtracted and rounded by unit:

| Expression | Meaning |
|---|---|
| now | Current instant |
| now-1d | One day before the current instant |
| now-15m | 15 minutes ago |
| now/d | Rounded down to the start of the day |
| now-7d/d | Seven days ago, rounded down to the start of the day |
| now+2h | Two hours from now |

Example finding events from the last seven days:

~~~http
POST /application-events/_search
Content-Type: application/json

{
  "query": {
    "range": {
      "createdAt": {
        "gte": "now-7d",
        "lte": "now"
      }
    }
  }
}
~~~

`now` is evaluated at Elasticsearch's current instant on the UTC timeline. In queries with `time_zone`, that parameter does not alter the absolute instant `now` itself; however, the time zone can affect day/hour rounding in date math and how offsetless bounds are interpreted. When business logic requires "today in the user's time zone", specify the time zone and test day boundaries.

## 7. Time Zones in Date Histograms

A date histogram groups documents into time buckets. For daily data, time zone affects when each bucket begins. If you want daily reports in local time, pass `time_zone` into the aggregation.

Example:

~~~http
POST /application-events/_search
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "events_per_day": {
      "date_histogram": {
        "field": "createdAt",
        "calendar_interval": "day",
        "time_zone": "+07:00"
      }
    }
  }
}
~~~

`calendar_interval` `day` creates buckets aligned to calendar days. This is the right choice for calendar-based daily, monthly, or yearly reports. `fixed_interval` represents a fixed duration, such as `24h`, `60m`, or `15m`.

Do not always substitute `fixed_interval` `24h` for `calendar_interval` `day`. In time zones observing daylight saving time, a calendar day can be 23 or 25 hours long. Using calendar intervals with `time_zone` keeps buckets aligned to local days. With fixed intervals, intervals are computed strictly by fixed duration.

## 8. Mapping Temporal Types in Spring Data Elasticsearch

Spring Data Elasticsearch uses mapping metadata and `MappingElasticsearchConverter` to convert Java entities to documents and back. Common Java temporal types include:

| Java type | Meaning | Notes |
|---|---|---|
| Instant | An absolute point on the UTC timeline | Usually the clearest choice for event timestamps |
| OffsetDateTime | Date-time with a UTC offset | Elasticsearch normalizes to an instant; the original offset is not kept as a separate zone |
| ZonedDateTime | Date-time tied to a ZoneId | If ZoneId must be retained, store a separate zone field |
| LocalDateTime | Date-time without offset/zone | Only use when business logic truly represents local time and a zone is defined at conversion |
| LocalDate | Calendar date without time of day | Suitable for birth dates or calendar effective dates when time is unneeded |
| java.util.Date | Instant at millisecond precision | Legacy type; modern APIs generally prefer java.time |

For event timestamps, `Instant` usually conveys the clearest meaning. `LocalDateTime` carries no time zone information; do not treat it like an `Instant` unless the application specifies a zone for conversion.

### 8.1. Declaring a `date` Field

Entity example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "application-events")
public class ApplicationEvent {

    @Id
    private String id;

    @Field(type = FieldType.Date)
    private Instant createdAt;

    // constructors, getters and setters
}
~~~

`FieldType.Date` declares a `date` type in Elasticsearch mapping. `Instant` represents an absolute point in time, convenient for normalization and temporal comparisons.

### 8.2. Declaring a `date_nanos` Field

If nanosecond precision must be preserved, you can use `FieldType.Date_Nanos` in Spring Data Elasticsearch versions that support this type:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "sensor-readings")
public class SensorReading {

    @Id
    private String id;

    @Field(type = FieldType.Date_Nanos)
    private Instant measuredAt;

    // constructors, getters and setters
}
~~~

Confirm that `FieldType.Date_Nanos` exists in your project's Spring Data Elasticsearch version. If an older version lacks support for the enum or corresponding mapping, upgrade in lockstep according to the compatibility matrix or configure mappings differently.

`Instant` can hold nanoseconds, but if the target field is `date`, sub-millisecond parts will not be stored at nanosecond precision. To preserve nanoseconds, both the Elasticsearch mapping type and the data conversion path must support that precision.

### 8.3. Declaring Custom Formats in Annotations

Spring Data Elasticsearch allows declaring format and pattern on `@Field`. Example:

~~~java
@Field(
    type = FieldType.Date,
    pattern = "yyyy-MM-dd HH:mm:ss"
)
private LocalDateTime importedAt;
~~~

The pattern must match actual data. The example above has no offset, so it represents local time under the application's convention rather than determining an absolute instant on its own. If data contains an offset, the pattern must include the offset portion and the Java type should reflect that information.

For new data, prefer ISO-8601 and temporal types with clear semantics. Custom patterns are generally reserved for legacy systems or fixed integration contracts.

## 9. Normalizing Time at the Application Boundary

A reliable architecture standardizes time handling where data enters the system:

~~~text
Client / external system
        |
        | ISO-8601 with offset or epoch with explicit unit
        v
API boundary
        |
        | parse and validate
        | convert to Instant
        v
Spring Data Elasticsearch
        |
        | date or date_nanos mapping
        v
Elasticsearch (UTC timeline)
        |
        | range query / sort / aggregation
        v
API response
        |
        | convert Instant to display ZoneId
        v
User
~~~

Practical rules:

1. Clearly distinguish whether data is an absolute instant or a local calendar date/time.
2. For absolute instants, require clients to send ISO-8601 with offset or epoch with an explicit unit.
3. Parse data at the API boundary and convert to `Instant` if business logic works with absolute instants.
4. Choose `date` or `date_nanos` based on the precision actually required.
5. When searching by local date, convert day boundaries to UTC or pass the appropriate `time_zone` in the query.
6. When displaying, convert `Instant` to the user's `ZoneId`.
7. If the original time zone or local schedule must be preserved, store an additional zone ID or necessary business metadata.

## 10. Common Mistakes

### 10.1. Sending Epoch Seconds to a Field Expecting Epoch Milliseconds

The value `1735689600` can be interpreted as milliseconds if the mapping uses `epoch_millis`. The resulting date will be near 1970 instead of 2025. Verify units in the API contract and convert explicitly.

### 10.2. Using `date` While Expecting Nanoseconds

The `date` type has millisecond precision. If the application sends timestamps with nine fractional digits, do not expect `date` to preserve full precision. Use `date_nanos` when genuinely needed.

### 10.3. Treating `LocalDateTime` as a UTC Instant

`LocalDateTime` has no offset or `ZoneId`. The same value `09:00` can refer to different instants depending on time zone. Convert to `Instant` using an explicit `ZoneId` before writing when business logic requires an absolute instant.

### 10.4. Storing UTC Yet Filtering by Local Day as If It Were UTC

A day in UTC+07:00 starts at 17:00 UTC on the previous day. Using `00:00` UTC as the start of a Vietnam day will miss or include extra data around the boundary. Convert boundaries or use `time_zone`.

### 10.5. Assuming Elasticsearch Retains the Original Time Zone Name

Offsets determine the instant and are normalized to UTC. If you need to know whether the original schedule belonged to `Asia/Ho_Chi_Minh`, `Europe/Paris`, or another zone, store `ZoneId` separately.

### 10.6. Using Overly Broad or Inconsistent Formats

Accepting unnecessary patterns makes data hard to normalize and increases input errors. Pick one standard format for producers and retain legacy formats only when real compatibility demands it.

### 10.7. Using Inclusive End Bounds at Time Interval Boundaries

When querying a single day, `gte` start of day and `lt` start of the next day is usually safer than `gte`/`lte` with an assumed end-of-day timestamp like `23:59:59.999`. Using a half-open interval does not depend on whether precision is `date` or `date_nanos`.

## 11. Example: Storing and Searching Events by Day in Vietnam

Suppose the system receives events from a device in Vietnam. The device sends:

~~~json
{
  "measuredAt": "2025-04-18T16:30:00.123456789+07:00"
}
~~~

The application parses the value into an `Instant`. The corresponding instant is:

~~~text
2025-04-18T09:30:00.123456789Z
~~~

If the event requires nanosecond precision, the entity uses `FieldType.Date_Nanos` and the index mapping has type `date_nanos`. If millisecond precision suffices, use `FieldType.Date`.

To find all events on April 18, 2025 in Vietnam time, the API can send a range query with `time_zone` `+07:00` and a half-open interval from the start of the day to the start of the next day. Elasticsearch compares the normalized instants along the same UTC timeline.

When returning data to the UI, the application converts `Instant` to `ZoneId.of("Asia/Ho_Chi_Minh")` for display. If a user changes time zones, the same `Instant` can be rendered in a different local time without altering stored data.

## 12. Conclusion

`date` is the right choice for most business timestamps with millisecond precision. `date_nanos` is for data genuinely requiring nanosecond precision and comes with a narrower date range. Formats specify how Elasticsearch parses strings or epochs; time zones determine how local values and query boundaries are interpreted.

In Spring Data Elasticsearch, choose Java types aligned with data meaning—commonly `Instant` for absolute instants—and map them to `FieldType.Date` or `FieldType.Date_Nanos`. Normalize inputs to ISO-8601 with offsets or epochs with explicit units, store instants in UTC, and convert to user time zones only when querying or displaying.
