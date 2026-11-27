# Instant, LocalDateTime, Date, and UTC Conventions

> **Chapter:** Data Types  
> **Module:** `SPRING_DATA_MONGODB`

Time is a subtle source of bugs in data systems: an event occurring at **09:00 in Vietnam** is actually **02:00 UTC**, whereas an appointment for “09:00 tomorrow local time” may need to be interpreted in the scheduler's time zone. Ignoring this distinction can cause an application to store, sort, or aggregate data incorrectly without ever throwing an exception.

In Spring Data MongoDB, three common Java types are `java.time.Instant`, `java.time.LocalDateTime`, and `java.util.Date`. They do not carry the same meaning even though all three can end up converted to **BSON Date** in MongoDB. This lesson establishes clear UTC conventions for working through `MongoTemplate` or repositories, while preparing the groundwork for queries, aggregations, indexes, transactions, reactive access, testing, and performance diagnostics in the `SPRING_DATA_MONGODB` module.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **absolute instants**, **local wall-clock times**, and **time zones/offsets**, and explain how BSON Date stores time.
2. Choose properly among `Instant`, `LocalDateTime`, and `Date` in Java models and APIs.
3. Convert local times to `Instant` using an explicit `ZoneId`; avoid relying on `ZoneId.systemDefault()`.
4. Design documents, local-date-range queries, and aggregations with consistent UTC conventions.
5. Handle millisecond precision, daylight saving time (DST), historical data, and conversion pitfalls in Spring Data MongoDB.

## 2. Three Concepts to Keep Separate

| Concept | Example | Information Carried | Question Answered |
| --- | --- | --- | --- |
| **Absolute point in time** (*instant*) | `2026-11-20T02:00:00Z` | A position on the UTC timeline | **When** did the event happen? |
| **Local wall-clock time** (*local date-time*) | `2026-11-20T09:00:00` | Date, hour, minute, second; **no** time zone | **What time** does a local clock show? |
| **Regional time zone** | `Asia/Ho_Chi_Minh` | Regional offset rules and historical transitions | **Where** is 09:00 being interpreted? |
| **UTC offset** (*offset*) | `+07:00` | Difference from UTC at a given moment | **How far** is local time from UTC? |

A single instant has many display representations, yet remains **the exact same event**:

```text
2026-11-20 02:00:00 UTC
    = 2026-11-20 09:00:00 Asia/Ho_Chi_Minh (+07:00)
    = 2026-11-19 21:00:00 America/New_York (EST, -05:00)
```

Conversely, the string `2026-11-20 09:00:00` alone does not identify an instant: 09:00 in Hanoi and 09:00 in New York are two different points in time.

**Core convention:** the moment an event occurs (order creation, payment capture, logging, sending a notification) should be stored and exchanged as an **instant**, while time zones are used to **interpret local input, format display output, or compute calendar-based reports**.

## 3. What Does MongoDB's BSON Date Actually Contain?

MongoDB has the **BSON Date** type: a **signed 64-bit integer** representing **milliseconds since the Unix epoch** (`1970-01-01T00:00:00Z`). Negative values represent points in time before the epoch. BSON Date does not store a time zone name, offset, display format, or nanoseconds.

Example in `mongosh`:

```javascript
use shop

const moment = ISODate("2026-11-20T02:00:00.000Z");
moment.toISOString(); // "2026-11-20T02:00:00.000Z"
moment.getTime();      // milliseconds since Unix epoch

db.events.insertOne({
  name: "ORDER_PAID",
  occurredAt: moment
})

db.events.findOne({ name: "ORDER_PAID" })
```

`ISODate(...)` is the shell representation/constructor in `mongosh`; the persisted value is **BSON Date**, not the literal string `"ISODate(...)"`. In MongoDB Extended JSON, the same value may appear as:

```json
{
  "occurredAt": {
    "$date": "2026-11-20T02:00:00Z"
  }
}
```

This is **Extended JSON** representing a Date type; the `occurredAt` field is not a business object with a `$date` field. If you store `"2026-11-20T02:00:00Z"` directly as a string, it becomes a **BSON String**, which has different query and index semantics.

### 3.1. UTC Identifies the Instant, Not the User's Time Zone

A BSON Date has the exact same millisecond count whether read by a server in Vietnam, the US, or Europe. Display tools may format it in different time zones. Therefore, you cannot conclude a document was “stored off by 7 hours” merely because `mongosh` shows `02:00Z` while the UI renders `09:00`.

If a user picks 09:00 on 2026-11-20 in Vietnam, the canonical value stored in MongoDB is:

```javascript
ISODate("2026-11-20T02:00:00.000Z")
```

**Mistake to avoid:** adding seven hours when writing and adding seven hours again when reading. Conversions must follow a fixed rule at the **boundaries** where data is ingested or displayed.

### 3.2. Milliseconds and Precision Loss

`Instant` can represent nanosecond resolution, whereas BSON Date stores only **milliseconds**. Example:

```java
Instant precise = Instant.parse("2026-11-20T02:00:00.123456789Z");
Date legacy = Date.from(precise);

System.out.println(legacy.toInstant());
// 2026-11-20T02:00:00.123Z
```

The six sub-millisecond nanosecond digits are lost when converting to `Date`. When writing `Instant` into BSON Date, expect millisecond precision only; do not assert round-trip equality against original nanosecond components.

**Distinction note:** BSON `Timestamp` is a different type used by internal/replication mechanisms in MongoDB; do not use it in place of BSON Date for ordinary business timestamps.

## 4. Comparing Instant, LocalDateTime, and Date in Java

| Type | Identifies an Instant? | Contains Time Zone? | Mutable? | Recommended Use |
| --- | --- | --- | --- | --- |
| `Instant` | **Yes** | Carries no zone name; anchored on the UTC timeline | No (immutable) | `createdAt`, `updatedAt`, `paidAt`, `expiresAt` |
| `LocalDateTime` | **No** | **No** | No (immutable) | Local schedules like “Monday 09:00”, before applying `ZoneId` |
| `java.util.Date` | **Yes** (holds epoch milliseconds) | Does not store time zone | **Yes** (mutable) | Legacy library/DTO integration; convert to `Instant` at boundaries |

In Java:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Date;

Instant instant = Instant.parse("2026-11-20T02:00:00Z");
LocalDateTime local = LocalDateTime.of(2026, 11, 20, 9, 0);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

Instant fromLocal = local.atZone(vietnam).toInstant();
Date legacyDate = Date.from(instant);
Instant fromLegacy = legacyDate.toInstant();
ZonedDateTime display = instant.atZone(vietnam);

System.out.println(fromLocal.equals(instant)); // true
System.out.println(fromLegacy.equals(instant)); // true
System.out.println(display); // 2026-11-20T09:00+07:00[Asia/Ho_Chi_Minh]
```

### 4.1. Instant: Default Choice for Event Timestamps

`Instant` answers **when**, not **where**. It fits machine-generated timestamps: request receipt, authentication, record creation, payment, timeouts, TTLs, and audit trails. Comparing two instants requires no time-zone conversion.

To obtain the current instant:

```java
Instant now = Instant.now();
```

In logic requiring deterministic, repeatable tests, inject a `Clock` rather than calling `Instant.now()` directly everywhere.

### 4.2. LocalDateTime: Incomplete Calendar Value Without Zone

`LocalDateTime.of(2026, 11, 20, 9, 0)` only says **09:00 on November 20**, with no `+07:00` or `Asia/Ho_Chi_Minh`. It cannot resolve to an exact instant until the **zone/offset** is known.

`LocalDateTime` fits when business rules must preserve **wall-clock time**: store operating hours, counter opening times, or appointments whose region is stored separately. When scheduling a task to fire at a specific instant, pair it with a zone and handle DST transitions.

### 4.3. java.util.Date: Legacy Type That Still Represents an Instant

Despite having “Date” in its name, `java.util.Date` represents milliseconds since the epoch, not a calendar “year-month-day only” date. It **does not retain a time zone**.

```java
Date date = Date.from(Instant.parse("2026-11-20T02:00:00Z"));
Instant instant = date.toInstant();

// Defensive copy to avoid exposing a mutable object from a legacy API.
Date defensiveCopy = new Date(date.getTime());
```

`Date.toString()` uses the JVM process's default time zone for **formatting**, which can create the illusion that the underlying value changed. Use `Date.toInstant()`, `Date.getTime()`, or formatters with an explicit zone when comparing instants.

Do not confuse `java.util.Date` with `java.sql.Date` (calendar date semantics in JDBC) or `LocalDate` (a calendar date without time).

## 5. Converting Between Local Time and UTC

### 5.1. Converting Properly with ZoneId

A user enters `2026-11-20 09:30` and selects time zone `Asia/Ho_Chi_Minh`:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;

LocalDateTime requested =
    LocalDateTime.of(2026, 11, 20, 9, 30);

ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant scheduledAt = requested.atZone(zone).toInstant();

System.out.println(scheduledAt);
// 2026-11-20T02:30:00Z
```

When formatting for local display:

```java
LocalDateTime localAgain =
    LocalDateTime.ofInstant(scheduledAt, zone);

System.out.println(localAgain);
// 2026-11-20T09:30
```

To represent a **point in time**, store `scheduledAt` as a BSON Date. If business logic must preserve the booking region or reconstruct local schedule rules when time-zone rules change, store `zoneId` as a separate field.

### 5.2. Why You Must Not Assign UTC Arbitrarily

```java
LocalDateTime local = LocalDateTime.of(2026, 11, 20, 9, 30);

// Semantically WRONG if 09:30 is Vietnam time.
Instant wrong = local.toInstant(java.time.ZoneOffset.UTC);
// 2026-11-20T09:30:00Z (+7 hours off from the intended instant)

// CORRECT: we know this time belongs to Asia/Ho_Chi_Minh.
Instant correct = local
    .atZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .toInstant();
// 2026-11-20T02:30:00Z
```

`ZoneOffset.UTC` is only right when **the input time is genuinely UTC**, not as a shortcut to “coerce any LocalDateTime into UTC”.

### 5.3. Fixed Offsets vs. Regional Time Zones

`ZoneOffset.of("+07:00")` is a fixed offset. `ZoneId.of("Asia/Ho_Chi_Minh")` is a regional zone with historical rules. Some regions shift offsets during the year due to DST; using a fixed offset cannot express those rules across all dates.

For data that only needs an instant plus the offset at input time, `OffsetDateTime` can work at the API boundary. For appointments or long-term local schedules, storing `ZoneId` lets you interpret rules regionally.

## 6. Daylight Saving Time: Nonexistent or Ambiguous Hours

Some regions adjust their offset seasonally. For example, in `America/New_York`:

- When springing forward to daylight saving time, a local hour is **skipped** (*gap*).
- When falling back to standard time, a local hour occurs **twice** (*overlap*).

Consequently, the same string `2026-11-01T01:30` in New York can map to **two different instants**. Calling `atZone(...)` without an explicit policy silently picks one offset during an overlap or shifts the clock forward during a gap.

If a scheduling system requires an unambiguous instant, it can reject non-unique local times:

```java
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.List;

public static Instant resolveUnambiguous(
        LocalDateTime localTime, ZoneId zone) {
    List<ZoneOffset> validOffsets =
        zone.getRules().getValidOffsets(localTime);

    if (validOffsets.size() != 1) {
        throw new IllegalArgumentException(
            "Local time does not exist or is ambiguous: "
                + localTime + " in " + zone);
    }

    return localTime.toInstant(validOffsets.get(0));
}
```

Place this helper in a Java utility/service class; the method logic is complete. If business rules allow choosing one of the two `01:30` occurrences, the UI must let the user select an offset or define an explicit tie-breaking rule, then persist the resolved instant.

**Note:** Vietnam does not currently observe DST, yet multi-country data, historical time zones, and future appointments still require handling via proper `ZoneId`.

## 7. Mapping Temporal Types in Spring Data MongoDB

For an order management application, choose:

- `createdAt`: order creation instant, using `Instant`.
- `paidAt`: payment instant, using `Instant` or `null` when unpaid.
- `importedLegacyAt`: legacy system compatibility field using `Date`.
- `displayZoneId`: time zone used for display or interpreting local calendar data.

File `OrderTimeline.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Date;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;

@Document(collection = "order_timelines")
public record OrderTimeline(
    @Id String id,
    String orderId,
    @Field("created_at") Instant createdAt,
    @Field("paid_at") Instant paidAt,
    @Field("imported_legacy_at") Date importedLegacyAt,
    String displayZoneId
) {}
```

Under standard mapping configuration, `Instant` and `Date` convert to BSON Date; `displayZoneId` is a zone name string such as `Asia/Ho_Chi_Minh`. To keep the entire domain model immutable, convert `importedLegacyAt` to `Instant` at the import boundary and drop `Date` from the entity.

Illustrative document:

```javascript
{
  _id: ObjectId("66a000000000000000000021"),
  orderId: "ORD-100",
  created_at: ISODate("2026-11-20T01:45:00.000Z"),
  paid_at: ISODate("2026-11-20T02:00:00.000Z"),
  imported_legacy_at: ISODate("2026-11-20T00:00:00.000Z"),
  displayZoneId: "Asia/Ho_Chi_Minh",
  _class: "com.example.shop.orders.OrderTimeline"
}
```

The `_class` field is shown because default mapping may write Java type metadata; it **does not** alter how BSON Date stores timestamps.

### 7.1. Recording Time Using an Injected Clock

File `OrderTimelineService.java`:

```java
package com.example.shop.orders;

import java.time.Clock;
import java.time.Instant;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderTimelineService {
    private final MongoTemplate mongoTemplate;
    private final Clock clock;

    public OrderTimelineService(
            MongoTemplate mongoTemplate, Clock clock) {
        this.mongoTemplate = mongoTemplate;
        this.clock = clock;
    }

    public OrderTimeline create(String orderId) {
        OrderTimeline timeline = new OrderTimeline(
            null,
            orderId,
            Instant.now(clock),
            null,
            null,
            "Asia/Ho_Chi_Minh"
        );
        return mongoTemplate.insert(timeline);
    }
}
```

Register `Clock` as a Spring bean:

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClockConfig {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

`Clock.systemUTC()` clarifies the convention and lets tests substitute `Clock.fixed(...)`. Note: system clocks across multiple hosts can still drift; when database-assigned timestamps are needed during updates, consider the `$currentDate` operator and infrastructure clock synchronization conventions.

### 7.2. Repository Querying by Instant

File `OrderTimelineRepository.java`:

```java
package com.example.shop.orders;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderTimelineRepository
        extends MongoRepository<OrderTimeline, String> {

    List<OrderTimeline>
    findByCreatedAtGreaterThanEqualAndCreatedAtLessThan(
        Instant fromInclusive, Instant toExclusive);
}
```

Derived queries use the **Java property name** `createdAt`; Spring Data mapping translates it to BSON field `created_at` via `@Field`. The repository does not inherently know what UTC range represents a “Vietnam calendar day”; the caller must pass the converted boundary instants.

### 7.3. LocalDateTime Can Map to BSON Date, but Requires Caution

Spring Data MongoDB supports Java Time converters; **`LocalDateTime` has no timezone**, yet a BSON Date must represent an instant. The converter must **choose a zone** to assign meaning to that local time.

According to Spring Data documentation, Spring Data's default local-time converter (`LocalDateTime` → `java.util.Date`) uses **`ZoneId.systemDefault()`**. Some configurations use MongoDB Java Driver's Java Time codecs with **UTC**. Consequently, the same `LocalDateTime.of(2026, 11, 20, 9, 0)` can be persisted as **different instants** if conversion settings or process time zones differ.

| Source Converting `LocalDateTime 09:00` | Zone Used to Interpret 09:00 | Resulting BSON Date |
| --- | --- | --- |
| Spring Data local-time converter, host running in Vietnam | `Asia/Ho_Chi_Minh` | `2026-11-20T02:00:00Z` |
| Driver converter/codec using UTC | `UTC` | `2026-11-20T09:00:00Z` |
| Host with a different default zone | That host's zone | Can produce yet another instant |

Therefore, **do not rely on the host machine's time zone** to determine a critical business timestamp. The safe approach is accepting `LocalDateTime + ZoneId`, resolving to `Instant` in the service layer, and storing `Instant` on the entity.

If the domain genuinely needs to store **pure wall-clock time** such as “every Monday at 09:00”, consider a dedicated model holding local date/time and `zoneId` with an explicit storage representation (such as an ISO local-date-time string or numeric fields). Do not assume BSON Date can express “09:00 in every time zone”.

## 8. API Conventions: Input, Storage, Display

### 8.1. APIs Exchanging Absolute Instants

Example request/response using ISO 8601 with an explicit offset:

```json
{
  "orderId": "ORD-100",
  "paidAt": "2026-11-20T02:00:00Z"
}
```

Or a value with offset `+07:00`:

```json
{
  "orderId": "ORD-100",
  "paidAt": "2026-11-20T09:00:00+07:00"
}
```

Both strings describe the same instant. With Jackson configured for Java Time, you can bind to `OffsetDateTime` or a suitable type and convert to `Instant`. Avoid accepting a zone-less string like `"2026-11-20T09:00:00"` and guessing the server's time zone.

### 8.2. APIs Exchanging Local Appointments

If a user schedules a local appointment, the API can accept:

```json
{
  "appointmentLocal": "2026-11-20T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
```

The service validates `zoneId` and computes `scheduledAt: Instant`. For DST gaps/overlaps, define an explicit policy: prompt for re-entry or choose a valid offset. If the schedule is a recurring weekly rule, a single instant is insufficient; store both the recurrence rule and the time zone to compute each occurrence.

### 8.3. Formatting for Display

```java
import java.time.Instant;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

Instant paidAt = Instant.parse("2026-11-20T02:00:00Z");

String shown = DateTimeFormatter
    .ofPattern("dd/MM/yyyy HH:mm z")
    .withZone(ZoneId.of("Asia/Ho_Chi_Minh"))
    .format(paidAt);

System.out.println(shown);
// Example: 20/11/2026 09:00 ICT
```

Display in the user's locale/zone while keeping `Instant` as the source data. **String formatting is a presentation concern**; never store timestamps solely as `dd/MM/yyyy HH:mm` if you still need to filter, sort, compute durations, or index as dates.

## 9. Querying by Local Date Range Correctly

Suppose a user asks: “All orders created on **2026-11-20 Vietnam time**”. This local day starts and ends in UTC as follows:

```text
Local date: 2026-11-20, Asia/Ho_Chi_Minh

start = 2026-11-20 00:00:00 +07:00
      = 2026-11-19T17:00:00Z

end   = 2026-11-21 00:00:00 +07:00
      = 2026-11-20T17:00:00Z

Query range: [start, end)
```

Using a **half-open interval** `[start, end)` avoids rounding risks at `23:59:59.999` and prevents double-counting documents across consecutive days.

### 9.1. Computing Boundaries in Java

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate day = LocalDate.of(2026, 11, 20);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant start = day.atStartOfDay(zone).toInstant();
Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

System.out.println(start); // 2026-11-19T17:00:00Z
System.out.println(end);   // 2026-11-20T17:00:00Z
```

**Do not use** `start.plus(24, ChronoUnit.HOURS)` as the boundary for every local day: days in regions with DST can be 23 or 25 hours long. Compute the **start of the next day in the same ZoneId**, then convert to an instant.

### 9.2. MongoTemplate

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;
import java.util.List;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;

public List<OrderTimeline> findByLocalDay(
        MongoTemplate mongoTemplate,
        LocalDate day,
        ZoneId zone) {

    Instant start = day.atStartOfDay(zone).toInstant();
    Instant end = day.plusDays(1).atStartOfDay(zone).toInstant();

    Query query = Query.query(
            Criteria.where("createdAt").gte(start).lt(end))
        .with(Sort.by(Sort.Direction.ASC, "createdAt"));

    return mongoTemplate.find(query, OrderTimeline.class);
}
```

Place this method in a Java service/class and inject a real `MongoTemplate`. The `createdAt` criterion refers to the **Java property**; `MongoTemplate` uses `@Field("created_at")` metadata to query the corresponding MongoDB field.

### 9.3. mongosh

```javascript
db.order_timelines
  .find({
    created_at: {
      $gte: ISODate("2026-11-19T17:00:00Z"),
      $lt: ISODate("2026-11-20T17:00:00Z")
    }
  })
  .sort({ created_at: 1 })
```

Create an index for frequent time-range queries:

```javascript
db.order_timelines.createIndex({ created_at: 1 })
```

If queries also filter by `orderId` or `storeId`, consider a compound index matching the query pattern instead of creating single-field indexes for every field. BSON Date lets MongoDB filter/sort by the stored instant; MongoDB does not need to know the user's time zone once UTC boundaries are supplied.

## 10. Aggregation by Local Day

When building dashboards, a “day” usually follows the business time zone, **not the UTC day**. MongoDB aggregations include timezone-aware operators such as `$dateTrunc` and `$dateToString`.

Suppose the `order_timelines` collection has `paid_at` as BSON Date, and we want to count orders per Vietnam day:

```javascript
db.order_timelines.aggregate([
  { $match: { paid_at: { $type: "date" } } },
  {
    $group: {
      _id: {
        $dateTrunc: {
          date: "$paid_at",
          unit: "day",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: { $sum: 1 }
    }
  },
  { $sort: { _id: 1 } },
  {
    $project: {
      _id: 0,
      localDay: {
        $dateToString: {
          format: "%Y-%m-%d",
          date: "$_id",
          timezone: "Asia/Ho_Chi_Minh"
        }
      },
      orderCount: 1
    }
  }
])
```

`$dateTrunc` with `unit: "day"` and a regional zone produces start-of-day instants under that region's rules; `$dateToString` formats the day label for reporting. Using `$dateTrunc` requires a MongoDB version supporting the operator (MongoDB 5.0 or later).

**Two common mistakes:**

1. Grouping with `$dateToString` without specifying `timezone` and displaying labels in Vietnam: orders near local midnight get attributed to the wrong day.
2. Querying a local day using `00:00Z` UTC boundaries: misses orders early in the local day and pulls in orders from the next day.

If weekly/monthly summaries are needed, standardize week numbering, week start day, and business timezone. Pre-aggregated daily totals should also explicitly document “day in which zone”.

## 11. Configuring Time Conversions in Spring Data

In practice, there are two conversion layers:

1. **Java domain → Spring Data mapping**: applies metadata from `@Document`, `@Field`, and `MongoCustomConversions`.
2. **Resulting value → BSON via MongoDB driver**: writes BSON Date, String, Number, and other types.

For `Instant` and `Date` representing an instant, the mapping path to BSON Date is relatively direct. For `LocalDateTime`, zone decisions can vary depending on the chosen converter/codec.

According to the Spring Data MongoDB API, `MongoCustomConversions.MongoConverterConfigurationAdapter` offers Java Time options:

- `useSpringDataJavaTimeCodecs()`: uses Spring Data converters with `ZoneId.systemDefault()` for local temporal types.
- `useNativeDriverJavaTimeCodecs()`: uses driver Java Time codecs with `ZoneOffset.UTC` for local temporal types.

Check the exact API names and `MongoCustomConversions` initialization for your project's framework version; changing this setting on a database that already contains `LocalDateTime` data can cause **the exact same BSON Date to be interpreted differently than before**.

**Recommended convention for business timestamps:** store `Instant`, converting local inputs using an explicit `ZoneId` in the service layer; treat `LocalDateTime` as a **local calendar value** rather than automatically as a timestamp. This makes logic independent of OS time zones.

If a project requires custom converters, register them via `MongoCustomConversions` with `@WritingConverter`/`@ReadingConverter` as needed, explicitly define target BSON types, and test after changing configuration. Misconfigured global conversions can alter unrelated fields.

## 12. Migrating When Legacy Data Uses the Wrong Type

Long-lived systems often contain a mix:

```javascript
// A: proper BSON Date type
{ _id: "A", occurredAt: ISODate("2026-11-20T02:00:00Z") }

// B: string with explicit offset
{ _id: "B", occurredAt: "2026-11-20T09:00:00+07:00" }

// C: local-time string without zone information
{ _id: "C", occurredAt: "2026-11-20 09:00:00" }
```

You cannot fix all of them with a single blind string-to-Date cast while ignoring semantics:

- **A** is already BSON Date; no conversion needed.
- **B** carries an offset; it can parse to the same instant if the format is valid.
- **C** lacks a zone; you must know which time zone the producing source used, or acknowledge that an exact instant cannot be recovered without context.

### 12.1. Profiling Existing Types

```javascript
db.events.aggregate([
  {
    $group: {
      _id: { $type: "$occurredAt" },
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```

This check surfaces fields stored as `date`, `string`, `null`, or missing; strings require further format and origin analysis.

### 12.2. Previewing Local Time Interpretation

Suppose it is **verified** that `legacyLocalTime` in an older dataset was always recorded in Vietnam time formatted as `YYYY-MM-DD HH:mm:ss`. Test parsing with a **read-only** pipeline:

```javascript
db.legacyEvents.aggregate([
  { $match: { legacyLocalTime: { $type: "string" } } },
  {
    $project: {
      legacyLocalTime: 1,
      convertedAt: {
        $dateFromString: {
          dateString: "$legacyLocalTime",
          format: "%Y-%m-%d %H:%M:%S",
          timezone: "Asia/Ho_Chi_Minh",
          onError: null,
          onNull: null
        }
      }
    }
  },
  { $limit: 20 }
])
```

Only after verifying sample data, time zones, error handling, and recovery options should you build migration write commands. Avoid parsing a string that already includes an offset and then applying another timezone. Local timestamps falling inside DST gaps/overlaps may require manual decisions or supplementary metadata.

For live systems, consider a phase where readers support both old and new formats; migrate in batches while reconciling record counts, timestamps, and parse failures; and keep a rollback plan. Converting BSON String to BSON Date changes how sorting, comparisons, indexes, and aggregations behave.

## 13. Testing Time Correctly and Checking Performance

### 13.1. Java Unit Tests Without a Database

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import org.junit.jupiter.api.Test;

class TimeRulesTest {
    @Test
    void vietnamLocalTimeMapsToExpectedInstant() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant instant = LocalDateTime.of(2026, 11, 20, 9, 0)
            .atZone(zone)
            .toInstant();

        assertEquals(
            Instant.parse("2026-11-20T02:00:00Z"),
            instant
        );
    }

    @Test
    void localDayProducesHalfOpenUtcBounds() {
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDate date = LocalDate.of(2026, 11, 20);

        assertEquals(
            Instant.parse("2026-11-19T17:00:00Z"),
            date.atStartOfDay(zone).toInstant()
        );
        assertEquals(
            Instant.parse("2026-11-20T17:00:00Z"),
            date.plusDays(1).atStartOfDay(zone).toInstant()
        );
    }
}
```

### 13.2. Round-Trip Testing via MongoDB

With `MongoTemplate` or a repository, create an entity with an `Instant` containing milliseconds, save and reload it, then compare against the millisecond-truncated instant:

```java
import java.time.Instant;
import java.time.temporal.ChronoUnit;

Instant input = Instant.parse("2026-11-20T02:00:00.123456Z");
Instant expected = input.truncatedTo(ChronoUnit.MILLIS);

// Save input in the entity via repository/MongoTemplate, then read back.
// assertEquals(expected, reloaded.getCreatedAt());
```

This illustrates the **test expectation**; replace `reloaded.getCreatedAt()` with your entity's actual accessor. For the `OrderTimeline` record above, the accessor is `reloaded.createdAt()`. When testing mapping, verify that BSON actually stores type `date`, not string.

Integration test cases to include:

| Scenario | Expectation |
| --- | --- |
| Save and read `Instant` | Returns the same instant at millisecond resolution |
| Save and read `java.util.Date` | Milliseconds unchanged, independent of display time zone |
| Run `LocalDateTime` converter under different JVM time zones | Detect divergence and lock down the conversion contract |
| Query a Vietnam calendar day | Matches data inside `[17:00Z previous day, 17:00Z today)` |
| Day crossing DST in New York | Correct local-day boundaries, spanning 23 or 25 hours |
| Timestamp with nanoseconds | Do not expect sub-millisecond fractions to survive BSON Date |
| Missing/null fields or legacy strings | Handled per defined mapping/migration strategy |
| Data written from multiple services | Timestamps compared under the same UTC contract; clock skew accounted for |

### 13.3. Performance Diagnostics

Inspect indexes and execution plans via `explain("executionStats")`:

```javascript
db.order_timelines
  .find({
    created_at: {
      $gte: ISODate("2026-11-19T17:00:00Z"),
      $lt: ISODate("2026-11-20T17:00:00Z")
    }
  })
  .sort({ created_at: 1 })
  .explain("executionStats")
```

Measure `totalDocsExamined`, `totalKeysExamined`, latency, and returned document count on representative data. BSON Date indexes support efficient range queries and chronological sorting; storing timestamps as strings with mixed formats/offsets makes queries error-prone and harder to optimize.

## 14. Common Mistakes

| Mistake | Consequence | Prevention |
| --- | --- | --- |
| Storing `LocalDateTime` as BSON Date without deciding time zone | Stored instants differ across hosts/containers | Convert `LocalDateTime + ZoneId` to `Instant` in the service layer |
| Assuming `java.util.Date` stores a time zone | Logs/display mislead developers, offsets get added twice | Treat `Date` as epoch milliseconds; format using an explicit zone |
| Using `LocalDateTime.now()` as a system timestamp | Result depends on process default time zone | Use `Instant.now(clock)` |
| Using `23:59:59.999` as end of day | Fragile when precision changes; inconsistent bounds | Use half-open `[start, nextStart)` intervals |
| Assuming every day is exactly 24 hours long | Fails on DST transition days | Compute next day start via `LocalDate.plusDays(1).atStartOfDay(zone)` |
| Using `ZoneOffset.UTC` to convert 09:00 Vietnam time | Off by seven hours | Use the exact `ZoneId` of the data source |
| Asserting nanosecond `Instant` equality after a BSON Date round-trip | Tests fail due to millisecond truncation | Truncate to milliseconds when comparing |
| Storing dates as `dd/MM/yyyy HH:mm` strings | Hard to filter, sort, and index chronologically | Use BSON Date for instants; format only for display |
| Parsing zone-less legacy strings using the server's time zone | Data gets silently misinterpreted | Audit sources, verify zones, and migrate with reconciliation |
| Grouping reports by UTC day instead of business zone | Orders near midnight get counted on the wrong day | Pass explicit time zones in bounds or aggregation operators |

## 15. Case Study Exercise

A store in Ho Chi Minh City records `paidAt` for orders. A customer places and pays for an order at **23:50 on 2026-11-20 Vietnam time**, while the analytics dashboard runs on a server configured in UTC. The manager wants to compute **revenue for November 20 in Vietnam time**.

Answer the following:

1. Should `paidAt` be `Instant`, `LocalDateTime`, or `Date` in a new domain model? Why?
2. What UTC instant corresponds to `23:50` in Vietnam?
3. Over what UTC range should the dashboard query `paidAt`?
4. If the server moves from UTC to another time zone, should the statistics change?
5. If using MongoDB aggregation, in which operators must the time zone be specified?

**Solution guide:**

- Choose `Instant` because payment is an event that occurred at a specific point in time.
- `2026-11-20T23:50:00+07:00` corresponds to `2026-11-20T16:50:00Z`.
- The Vietnam calendar day range is `[2026-11-19T17:00:00Z, 2026-11-20T17:00:00Z)`.
- Results must never depend on the server's default time zone: only the business zone `Asia/Ho_Chi_Minh` determines day boundaries.
- For daily aggregation, use `$dateTrunc`/`$dateToString` with the appropriate `timezone` parameter.

## 16. References

- MongoDB — [BSON Types: Date](https://www.mongodb.com/docs/manual/reference/bson-types/): Date definition, millisecond resolution, and epoch.
- MongoDB — [Date() and Datetime in mongosh](https://www.mongodb.com/docs/manual/reference/method/date/): `Date`, `new Date`, `ISODate`, and UTC formatting.
- Spring Data MongoDB — [Object Mapping](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/mapping.html): mapping `Instant` and Java Time types.
- Spring Data MongoDB — [Custom Conversions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/mapping/custom-conversions.html): `LocalDateTime` converters and system time zone dependency.

## Key Takeaways

**BSON Date** stores milliseconds for an instant on the UTC timeline and carries no time zone metadata. **`Instant`** is the default choice for business timestamps; **`java.util.Date`** carries the same meaning but is a legacy, mutable API limited to millisecond precision; **`LocalDateTime`** is only a local wall-clock time and must be paired with a `ZoneId` to identify an instant. Convert at API/service boundaries, persist instants consistently, compute report boundaries in the business time zone, and test across time-zone shifts, DST, and BSON precision.
