# Dates, Times, Datetimes, Timezones, and Durations in Cypher

When modeling connected data with **Neo4j**, many nodes and relationships need to record time: account registration dates, event timestamps, store operating hours, expiration dates, or the duration of a study session. Cypher supports dedicated **temporal data types** to represent and query such information.

This lesson belongs to the **Data Types** chapter of the `DATABASE_ENGINE_GRAPH_NEO4J` module. The focus is on choosing the right type for each business requirement, constructing values using Cypher functions, understanding timezones and offsets, performing arithmetic with `DURATION`, querying by time ranges, and exchanging data with the Java Driver and Spring Data Neo4j.

**Goal after this lesson:** clearly distinguish *calendar date*, *time of day*, *zoned point in time*, and *duration*; understand why these concepts cannot substitute for one another.

## 1. Six Temporal Types to Know

Cypher has six common temporal type categories:

| Cypher Type | Constructor | What Does It Hold? | When to Use? |
| --- | --- | --- | --- |
| `DATE` | `date()` | Calendar date: year, month, day | Birthdays, course launch dates, expiration dates |
| `LOCAL TIME` | `localtime()` | Hour, minute, second; no timezone/offset | Store opening hours on a local schedule |
| `ZONED TIME` | `time()` | Time of day with UTC offset | Appointment time with UTC offset |
| `LOCAL DATETIME` | `localdatetime()` | Date and time; no timezone/offset | Scheduled appointments where timezone context is managed by the application |
| `ZONED DATETIME` | `datetime()` | Date and time with offset or named timezone | Payment timestamps, account creation, logging |
| `DURATION` | `duration()` | Time span consisting of calendar and clock components | Exam time limits, adding deadlines, measuring elapsed time between two points |

> The word "local" in `LOCAL TIME` and `LOCAL DATETIME` means **containing no timezone information**, not that Neo4j automatically attaches the server's timezone to the stored value.

Visual example:

```cypher
RETURN
  date('2026-11-25') AS ngay,
  localtime('09:30:00') AS gioDiaPhuong,
  time('09:30:00+07:00') AS gioCoOffset,
  localdatetime('2026-11-25T09:30:00') AS ngayGioDiaPhuong,
  datetime('2026-11-25T09:30:00+07:00') AS mocThoiGian,
  duration('PT1H30M') AS thoiLuong;
```

All of the expressions above construct values in queries. Like strings, numbers, and booleans, temporal types can also be stored as **properties** on nodes or relationships.

## 2. DATE: Recording Calendar Dates Only

`DATE` represents a calendar date, **without time of day or timezone**. Birthdays, publication dates, and certification dates are suitable use cases.

### 2.1. Creating Dates from Strings or Components

```cypher
RETURN
  date('2026-11-25') AS fromIsoString,
  date({year: 2026, month: 11, day: 25}) AS fromComponents;
```

ISO 8601 formatted strings help avoid day/month ambiguity. `'2026-11-25'` is clearer than `'25/11/2026'` because slash-separated formats depend on regional conventions.

You can extract date components:

```cypher
WITH date('2026-11-25') AS d
RETURN
  d.year AS nam,
  d.month AS thang,
  d.day AS ngay,
  d.dayOfWeek AS thuTrongTuan;
```

`dayOfWeek` generally follows ISO: Monday is `1`, Sunday is `7`.

### 2.2. DATE Differs from Date-Like Strings

```cypher
RETURN
  '2026-11-25' AS dateText,
  date('2026-11-25') AS actualDate;
```

`dateText` is a `STRING`, whereas `actualDate` is a `DATE`. If you need to compute days remaining or filter by date ranges, store it as `DATE` instead of a string.

Example of a node containing a publication date:

```cypher
CREATE (b:TemporalDemoBook {
  bookCode: 'B-001',
  title: 'Graph Data Architecture',
  publishedOn: date('2026-11-25')
})
RETURN b.bookCode, b.publishedOn;
```

The `CREATE` statement creates a new node each time it runs. When practicing repeatedly, be careful to avoid creating duplicate demo data.

## 3. LOCAL TIME and ZONED TIME: Time of Day

### 3.1. LOCAL TIME Describes Only Time of Day

`LOCAL TIME` stores time of day without a UTC offset:

```cypher
RETURN
  localtime('08:00:00') AS openingTime,
  localtime('17:30:00') AS closingTime,
  localtime({hour: 9, minute: 15, second: 0}) AS meetingTime;
```

A store opening at 08:00 every day in local time can store `openingTime: localtime('08:00:00')`. This is a recurring schedule time, **not a unique point on the global timeline**.

### 3.2. ZONED TIME Includes a UTC Offset

`time()` constructs a time value with an offset:

```cypher
RETURN
  time('09:30:00+07:00') AS morningAtUtcPlus7,
  time('02:30:00Z') AS morningAtUtc,
  time({hour: 18, minute: 0, timezone: '+07:00'}) AS eveningAtUtcPlus7;
```

The `Z` notation means a `+00:00` offset from UTC. `+07:00` is UTC plus seven hours; offsets stored in `ZONED TIME` apply to the time of day, without providing a specific calendar date to determine seasonal daylight saving rules.

**Do not confuse `ZONED TIME` with an event timestamp:** time and offset alone are still insufficient to tell which date an event occurred on. If you need a transaction occurrence timestamp, use `ZONED DATETIME`.

### 3.3. When to Choose LOCAL TIME?

Suppose a store opens at 09:00 in the city where it is located, year-round according to local time. You can store:

```cypher
CREATE (s:TemporalDemoStore {
  storeId: 'ST-001',
  city: 'Ho Chi Minh',
  timeZoneId: 'Asia/Ho_Chi_Minh',
  opensAt: localtime('09:00:00'),
  closesAt: localtime('21:00:00')
})
RETURN s.storeId, s.opensAt, s.closesAt, s.timeZoneId;
```

Here `opensAt` is the time of day; `timeZoneId` is **separately stored business metadata** so the application knows which region that time belongs to. For multi-day weekly schedules, overnight shifts, or countries with daylight saving time, model explicit schedule rules rather than just two time properties.

## 4. LOCAL DATETIME and ZONED DATETIME: Date Combined with Time

### 4.1. LOCAL DATETIME Carries No Timezone

`localdatetime()` creates a combined date and time value:

```cypher
RETURN
  localdatetime('2026-11-25T14:30:00') AS meetingLocal,
  localdatetime({
    year: 2026,
    month: 11,
    day: 25,
    hour: 14,
    minute: 30
  }) AS fromComponents;
```

This value states **2026-11-25 at 14:30**, without specifying whether 14:30 is in Ho Chi Minh City, Tokyo, or Paris. If two systems in different timezones read this value, they need an **external convention** to determine the actual instant.

`LOCAL DATETIME` is suitable when an application stores a "local schedule" appointment alongside timezone context in another field. It should not be assumed to be UTC by default.

### 4.2. ZONED DATETIME Represents an Instant with Timezone Context

`datetime()` creates a date-time value with an offset or named timezone identifier:

```cypher
RETURN
  datetime('2026-11-25T14:30:00+07:00') AS withOffset,
  datetime('2026-11-25T07:30:00Z') AS inUtc,
  datetime({
    year: 2026,
    month: 11,
    day: 25,
    hour: 14,
    minute: 30,
    timezone: 'Asia/Ho_Chi_Minh'
  }) AS withNamedZone;
```

In this example, 14:30 at UTC+07 and 07:30 at UTC+00 represent the exact same instant on the timeline. Upon display, the application may convert it to the user's timezone.

**Remember how to choose the type:**

- Schedule needing only a date → `DATE`.
- Daily recurring opening hours → `LOCAL TIME`, optionally paired with timezone metadata.
- Local schedule without an embedded zone → `LOCAL DATETIME`.
- Event occurrence timestamp, system logs, payments → `ZONED DATETIME`.

## 5. Timezones: UTC, Offsets, and Zone Identifiers

Three concepts to distinguish:

| Concept | Example | Meaning |
| --- | --- | --- |
| UTC | `2026-11-25T07:30:00Z` | Point in time in Coordinated Universal Time |
| UTC offset | `+07:00`, `-05:00` | Fixed offset at the represented instant |
| Timezone region | `Asia/Ho_Chi_Minh`, `Europe/Paris` | Timezone rules by geographic region and date |

An **offset** like `+07:00` only tells you it is seven hours ahead of UTC at that instant. A **region** like `Europe/Paris` has historical rules and may change offsets seasonally. Therefore, an offset and a zone identifier are not interchangeable.

### 5.1. Daylight Saving Time (DST) and Ambiguous Local Times

In regions observing daylight saving time (DST), a local time can:

- **Not exist** when clocks spring forward.
- **Occur twice** when clocks fall back, yielding two distinct UTC instants.

For example, `'2026-10-25T02:30:00'` in a European region with seasonal clock changes can be ambiguous. A unique UTC instant cannot be inferred from `LOCAL DATETIME` alone.

Practical rules:

1. Store event timestamps using `ZONED DATETIME`, ideally with complete offset/zone information.
2. If you need to preserve region-based scheduling rules, store the **timezone region identifier** rather than only an offset.
3. When converting user-entered local times into UTC instants, validate non-existent or repeated DST times.
4. Never manually add or subtract `7` hours for every location and date; use timezone-aware temporal libraries.

### 5.2. Sub-Second Precision

Cypher supports high-precision temporal components, including sub-second fractions:

```cypher
RETURN
  datetime('2026-11-25T14:30:00.123456789+07:00') AS eventMoment,
  localtime('09:15:30.500') AS localTimeWithMillis;
```

The `.123456789` part represents nanoseconds in the corresponding temporal representation. However, **actual input data precision** depends on the source: a sensor measuring milliseconds does not become nanosecond-accurate simply because it is stored in a type capable of holding nanoseconds.

## 6. DURATION: Calendar-Aware Time Spans

`DURATION` describes a span of time, distinct from a date or datetime instant. It can contain month, day, second, and sub-second components; these components do not always convert to a fixed number of seconds.

### 6.1. ISO 8601 Duration Syntax

`duration()` accepts strings in ISO 8601 format prefixed with `P`. The part after `T` represents time-of-day units:

| Value | Meaning |
| --- | --- |
| `duration('P7D')` | 7 days |
| `duration('P2W')` | 2 weeks |
| `duration('P1M')` | 1 calendar month |
| `duration('P1Y')` | 1 calendar year |
| `duration('PT1H30M')` | 1 hour 30 minutes |
| `duration('PT45S')` | 45 seconds |
| `duration('P2DT3H')` | 2 days and 3 hours |
| `duration('PT1M')` | 1 minute |

**Watch the letter `M`:** in `P1M`, `M` stands for **months**; in `PT1M`, `M` comes after `T` and therefore stands for **minutes**. Confusing the two can cause serious business bugs.

Example:

```cypher
RETURN
  duration('P1M') AS oneCalendarMonth,
  duration('PT1M') AS oneMinute,
  duration('P3DT2H15M') AS courseDuration;
```

### 6.2. Creating Durations from Components

You can construct a `DURATION` using a map:

```cypher
RETURN
  duration({days: 7, hours: 2}) AS weekAndTwoHours,
  duration({hours: 1, minutes: 45, seconds: 30}) AS lessonLength;
```

The value `duration({days: 7})` carries a **calendar day** component. On an instant in a DST-observing region, "adding one calendar day" and "adding 24 actual hours" can produce different displayed wall-clock times. Clarify whether the goal is *calendar shifting* or *adding elapsed physical time*.

### 6.3. One Month Is Not Always 30 Days

A calendar month can be 28, 29, 30, or 31 days long. Consequently:

- `duration('P1M')` is **one calendar month**.
- `duration('P30D')` is **thirty days**.
- `duration('PT720H')` is **720 hours**.

These three concepts must not be treated as equivalent by default, especially across DST transitions or when adding from dates near the end of a month.

For example, a subscription plan expiring after one calendar month should follow calendar-month business rules, whereas a 90-minute timeout should use minute/second durations.

## 7. Computing with DATE, DATETIME, and DURATION

### 7.1. Adding/Subtracting a Duration with a Date

```cypher
WITH date('2026-11-25') AS startDate
RETURN
  startDate + duration('P7D') AS afterSevenDays,
  startDate - duration('P1D') AS previousDay;
```

The results are `2026-12-02` and `2026-11-24`, respectively.

Example calculating a document due date in calendar days:

```cypher
WITH date('2026-11-25') AS borrowedOn
RETURN
  borrowedOn,
  borrowedOn + duration('P14D') AS dueOn;
```

If the due date is counted in **business days**, adding 14 calendar days is insufficient: the application must also account for Saturdays, Sundays, and public holidays according to policy.

### 7.2. Adding/Subtracting a Duration with a Datetime

```cypher
WITH datetime('2026-11-25T09:00:00+07:00') AS startedAt
RETURN
  startedAt,
  startedAt + duration('PT90M') AS endedAt;
```

`PT90M` is 90 minutes. Because the base value includes the UTC+07 offset, the computed result preserves the temporal context needed to interpret the end instant.

### 7.3. Measuring the Interval Between Two Instants

`duration.between(start, end)` calculates the span from start to end:

```cypher
WITH
  datetime('2026-11-25T09:00:00+07:00') AS startedAt,
  datetime('2026-11-25T10:30:00+07:00') AS finishedAt
RETURN duration.between(startedAt, finishedAt) AS elapsed;
```

The result corresponds to 1 hour and 30 minutes.

Cypher also provides unit-specific functions to express differences:

```cypher
WITH
  date('2026-11-25') AS fromDate,
  date('2026-12-02') AS toDate
RETURN
  duration.inDays(fromDate, toDate) AS daysBetween,
  duration.inMonths(fromDate, toDate) AS monthsComponent;
```

`duration.inDays()` and `duration.inMonths()` do more than format output: they serve calculations with distinct calendar-unit semantics. When you need *total seconds* or *total minutes*, explicitly control the unit and rounding rules. Never multiply months by a constant to derive seconds.

### 7.4. Comparing Matching Temporal Types

```cypher
WITH
  date('2026-11-25') AS today,
  date('2026-12-01') AS deadline
RETURN
  today < deadline AS beforeDeadline,
  today = deadline AS onDeadline;
```

Do not mix `DATE`, `LOCAL DATETIME`, and `ZONED DATETIME` in conditions assuming they automatically coerce to the same representation. Choose consistent storage types and convert intentionally at application/query boundaries.

## 8. Extracting Components and Getting Current Time

### 8.1. Accessing Components of a Temporal Value

Cypher lets you access components via dot notation:

```cypher
WITH datetime('2026-11-25T14:30:45+07:00') AS eventAt
RETURN
  eventAt.year AS eventYear,
  eventAt.month AS eventMonth,
  eventAt.day AS eventDay,
  eventAt.hour AS eventHour,
  eventAt.minute AS eventMinute,
  eventAt.second AS eventSecond;
```

Extracting year/month/day is useful for generating report labels, but for queries filtering many records, it is usually better to filter using a **range of timestamps** on the raw property rather than extracting `eventAt.year` on every row.

### 8.2. Functions for Current Date and Time

`date()`, `time()`, `localtime()`, `datetime()`, and `localdatetime()` can be called with no arguments to read from the runtime system clock.

```cypher
RETURN
  date() AS currentDate,
  localtime() AS currentLocalTime,
  datetime() AS currentDateTime;
```

These results **change depending on execution time** and are affected by the clock/timezone rules of the execution environment. When consistent transaction timestamps are required, use the same time source within a unit of work and define timezone rules explicitly. Neo4j supports transaction, statement, and realtime clock modes for temporal functions; applications should pick the mode matching consistency requirements rather than assuming all calls behave identically.

If you want the current time in a specified zone, pass `timezone` in a map:

```cypher
RETURN datetime({timezone: 'Asia/Ho_Chi_Minh'}) AS nowInHoChiMinh;
```

The result is a timestamp with the requested zone context. Because this example is dynamic, there is no fixed literal value to compare against.

## 9. Storing Temporal Values on Nodes and Relationships

Both nodes and relationships can own properties of temporal types.

Suppose a learning platform needs to store course publication dates and learner enrollment timestamps:

```cypher
CREATE
  (learner:TemporalDemoLearner {
    learnerId: 'L-100',
    name: 'Ha',
    registeredOn: date('2026-11-01')
  }),
  (course:TemporalDemoCourse {
    courseId: 'C-NEO-01',
    title: 'Neo4j with Cypher',
    publishedOn: date('2026-10-25'),
    typicalLessonLength: duration('PT45M')
  })
CREATE (learner)-[:ENROLLED_IN {
  enrolledAt: datetime('2026-11-25T09:15:00+07:00')
}]->(course);
```

In this model:

- `registeredOn` and `publishedOn` are `DATE` because the domain only needs dates.
- `typicalLessonLength` is `DURATION` because it represents a **duration**, not a start instant.
- `enrolledAt` is `ZONED DATETIME` because the exact enrollment instant must be identified.
- The `ENROLLED_IN` relationship is the real link between learner and course; its `enrolledAt` property records the timestamp of that relationship itself.

Read query:

```cypher
MATCH (l:TemporalDemoLearner)-[r:ENROLLED_IN]->(c:TemporalDemoCourse)
RETURN
  l.name,
  c.title,
  l.registeredOn,
  r.enrolledAt,
  c.typicalLessonLength;
```

Do not store temporal data as a map like `{year: 2026, month: 11, day: 25}` as a **property value**, because Neo4j cannot store a map directly in a property. Use `DATE`/`DATETIME` types or intentional scalar fields.

## 10. Filtering by Time Range and Performance Impact

Real-world queries often need to retrieve records within a specific day or date range.

### 10.1. Half-Open Interval [start, end)

Use an **inclusive** lower bound and an **exclusive** upper bound:

```cypher
MATCH (e:TemporalDemoEvent)
WHERE e.occurredAt >= datetime('2026-11-25T00:00:00+07:00')
  AND e.occurredAt < datetime('2026-11-26T00:00:00+07:00')
RETURN e.eventId, e.occurredAt
ORDER BY e.occurredAt;
```

This represents the date 2026-11-25 at UTC+07 for `occurredAt` data stored consistently as `ZONED DATETIME`.

Using the **start of the next day** as the upper bound avoids guessing the "last second of the day" or maximum sub-second precision. Intervals of the form `[start, end)` also chain cleanly into consecutive ranges without double-counting boundary instants.

### 10.2. Finding Due Dates

```cypher
MATCH (task:TemporalDemoTask)
WHERE task.dueOn IS NOT NULL
  AND task.dueOn < date('2026-12-01')
RETURN task.taskId, task.dueOn
ORDER BY task.dueOn;
```

Here `dueOn` is a `DATE`. If compared against a plain string `'2026-12-01'` without the proper type, the temporal condition will not carry the intended semantics.

### 10.3. Temporal Properties and Indexes

Neo4j can use a **range index** to accelerate comparison or range filters on temporal properties when the index structure and query plan match.

Example index creation syntax:

```cypher
CREATE RANGE INDEX temporal_event_at_idx IF NOT EXISTS
FOR (e:TemporalDemoEvent)
ON (e.occurredAt);
```

Not every query with an index will necessarily use it. Inspect the plan using `EXPLAIN` or `PROFILE` with representative data:

```cypher
EXPLAIN
MATCH (e:TemporalDemoEvent)
WHERE e.occurredAt >= datetime('2026-11-25T00:00:00+07:00')
  AND e.occurredAt < datetime('2026-11-26T00:00:00+07:00')
RETURN e.eventId;
```

A generally effective strategy is **comparing the property directly against time bounds** rather than writing `WHERE e.occurredAt.year = 2026` and expecting the same efficiency. Index usage depends on the Neo4j version, index type, record count, and exact predicate structure.

## 11. Ingesting from Strings and Error Handling

CSV files, HTTP payloads, and many integration sources initially carry dates and times as strings. Determine the format and convert to the appropriate temporal type before writing.

### 11.1. Converting Valid Input

```cypher
WITH {
  birthDateText: '2001-07-18',
  eventTimeText: '2026-11-25T09:15:00+07:00',
  openingTimeText: '08:30:00',
  lessonLengthText: 'PT1H20M'
} AS raw
RETURN
  date(raw.birthDateText) AS birthDate,
  datetime(raw.eventTimeText) AS eventAt,
  localtime(raw.openingTimeText) AS opensAt,
  duration(raw.lessonLengthText) AS lessonLength;
```

When parsing user-supplied dates and times, decide:

1. Are strings without a timezone accepted for event timestamps?
2. Do strings follow ISO 8601?
3. Can the input contain `null` or empty strings?
4. At which layer are timezones and DST rules handled?
5. How will an invalid date like `2026-02-29` be rejected?

### 11.2. Preventing Invalid Data from Breaking the Pipeline

Temporal constructors require valid values. Invalid date strings can raise errors during conversion; do not assume malformed inputs will silently return `null`.

Example calling `date()` only when the string is non-null and matches a structural pattern:

```cypher
WITH '2026-11-25' AS rawDate
RETURN
  CASE
    WHEN rawDate IS NOT NULL
      AND rawDate =~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
    THEN date(rawDate)
    ELSE null
  END AS parsedDate;
```

**Limitation of this example:** the regex only checks the `YYYY-MM-DD` format, **not whether the calendar date actually exists**. `2026-02-29` matches the regex yet is not a valid date. For bulk ingestion, add real calendar validation in the application or dedicated error handling before creating Neo4j write transactions.

### 11.3. Do Not Assign null Directly When Intent Is Unclear

When executing `SET n.publishedOn = null`, Neo4j **deletes** that property. If an API treats "omitted date field" as "keep existing value" yet passes `null`, the update can unintentionally erase data.

With parameterization:

```cypher
MATCH (e:TemporalDemoEvent {eventId: $eventId})
SET e.occurredAt = $occurredAt
RETURN e.eventId, e.occurredAt;
```

Ensure `$occurredAt` is a temporal value validated by the application, and define the handling of `null` clearly. If the system simply needs to store dates/times, prefer passing temporal objects from the driver rather than converting back and forth through strings.

## 12. Java Driver and Spring Data Neo4j: Temporal Mapping

### 12.1. Passing java.time Types via the Java Driver

Java's `java.time` package provides types that align closely with Neo4j's temporal semantics:

| Meaning | Common Java Type | Cypher Type |
| --- | --- | --- |
| Calendar date | `LocalDate` | `DATE` |
| Time without offset | `LocalTime` | `LOCAL TIME` |
| Time with offset | `OffsetTime` | `ZONED TIME` |
| Date-time without timezone | `LocalDateTime` | `LOCAL DATETIME` |
| Date-time with timezone | `ZonedDateTime` / `OffsetDateTime` | `ZONED DATETIME` |
| Duration | `Duration` or `Period` depending on kind | `DURATION` |

Java's `Duration` represents second/nanosecond-based lengths; `Period` represents year/month/day components. Do not arbitrarily convert `Period.ofMonths(1)` into a fixed number of seconds.

Example passing a `ZonedDateTime` via a parameter map:

```java
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.Map;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;

public class TemporalEventWriter {
    public static void saveEvent(Driver driver) {
        ZonedDateTime occurredAt = ZonedDateTime.of(
            2026, 11, 25, 9, 30, 0, 0,
            ZoneId.of("Asia/Ho_Chi_Minh")
        );

        String cypher = """
            MERGE (e:TemporalDemoEvent {eventId: $eventId})
            SET e.occurredAt = $occurredAt
            RETURN e.eventId
            """;

        try (Session session = driver.session()) {
            session.executeWrite(tx -> {
                tx.run(cypher, Map.of(
                    "eventId", "EV-001",
                    "occurredAt", occurredAt
                )).consume();
                return null;
            });
        }
    }
}
```

In production, a unique constraint on `eventId` is needed to guarantee unique event identifiers under concurrent requests. The Java snippet demonstrates parameter binding; driver configuration, authentication, and error handling are the application's responsibility.

Reading a typed temporal value:

```java
// With query RETURN e.occurredAt AS occurredAt:
ZonedDateTime eventTime =
    record.get("occurredAt").asZonedDateTime();
```

The `record` variable in the second snippet assumes it comes from a Java Driver query result and that column `occurredAt` is non-null with a matching type. If the property may be absent, check `record.get("occurredAt").isNull()` before reading.

### 12.2. When Using Spring Data Neo4j

With Spring Data Neo4j, temporal properties on entities can be declared with the appropriate `java.time` types. Depending on the framework version, converter setup, and mapping rules, verify that the Java types map to the desired Neo4j types.

Example fields on a Java entity:

```java
import java.time.LocalDate;
import java.time.ZonedDateTime;

public class CourseTimeFields {
    private LocalDate publishedOn;
    private ZonedDateTime updatedAt;

    // Getter/setter or entity configuration suited to the project.
}
```

This is an **illustration of field type selection**, not a complete Spring Data Neo4j entity. Annotations and persistence methods depend on the application's entity model. Avoid turning all temporal fields into `String` if the system needs comparisons, duration arithmetic, or range queries.

When designing JSON APIs, output datetimes in ISO 8601 format, including the appropriate offset or zone. If the client only needs a calendar date, return `YYYY-MM-DD` to avoid implying a specific instant.

## 13. Real-World Scenario: Event Logs and Deadlines

A learning system needs to record session-start events, calculate a deadline 90 minutes later, and find overdue sessions.

### 13.1. Creating a Sample Event

```cypher
CREATE (e:TemporalDemoEvent {
  eventId: 'EV-001',
  startedAt: datetime('2026-11-25T09:00:00+07:00'),
  allowedDuration: duration('PT90M')
})
SET e.dueAt = e.startedAt + e.allowedDuration
RETURN e.eventId, e.startedAt, e.allowedDuration, e.dueAt;
```

`startedAt` and `dueAt` are **timestamps with offsets**; `allowedDuration` is a **duration**. Storing `dueAt` makes overdue queries convenient, but consistency must be maintained whenever `startedAt` or `allowedDuration` is modified.

### 13.2. Finding Sessions That Have Reached Their Deadline

```cypher
WITH datetime('2026-11-25T11:00:00+07:00') AS checkAt
MATCH (e:TemporalDemoEvent)
WHERE e.dueAt IS NOT NULL
  AND e.dueAt <= checkAt
RETURN e.eventId, e.dueAt
ORDER BY e.dueAt;
```

This example uses a fixed `checkAt` so you can verify results directly. In production, replace it with an application-supplied parameter or a current-time function per system policy.

### 13.3. Distinguishing Due Dates from Due Timestamps

If the rule is "submit before the end of 2026-11-25 in the learner's timezone", a `DATE` property such as `dueOn` **does not specify the exact expiration instant on its own**. The application must know the learner's timezone and define "end of day" in that calendar before computing the submission cutoff instant.

If the rule is "90 minutes from session start", using `ZONED DATETIME` paired with a `DURATION` expressed in minutes/seconds is much clearer.

## 14. Common Pitfalls

| Mistake | Risk | Solution |
| --- | --- | --- |
| Storing `'2026-11-25'` as `STRING` for all date fields | Hard to enforce validity and perform date math | Use `DATE` when the data represents a calendar date |
| Using `LOCAL DATETIME` for global event timestamps | Lacks timezone to identify a unique instant | Use `ZONED DATETIME` with an offset or zone |
| Storing only `09:00` to record when an event occurred | Missing date and timezone | Use `ZONED DATETIME` for points in time |
| Treating `+07:00` and `Asia/Ho_Chi_Minh` as identical concepts | Loses regional rules, especially in DST zones | Distinguish fixed offsets from timezone IDs |
| Assuming `P1M` means one minute | `M` before `T` means months | Use `PT1M` for one minute |
| Assuming one month is always 30 days | Inaccurate across months and leap years | Use calendar semantics and business rules |
| Using `LOCAL DATETIME` for ambiguous DST hours without a zone | Cannot determine a unique UTC instant | Track the zone and handle repeated/non-existent times |
| Using `23:59:59` as upper bound when filtering a day | Misses sub-second instants at the end of the day | Use a half-open interval up to `00:00` of the next day |
| Converting `date('2026-02-29')` | Non-existent calendar date | Validate real dates and handle input errors |
| Assuming `SET e.at = null` means "do not update" | Neo4j deletes the property | Distinguish keeping unchanged from clearing fields |
| Computing `DATEDIFF` by dividing months by a fixed number of days | Loses calendar semantics | Use `duration.between` / `duration.inDays` as required |
| Comparing `STRING` with temporal values expecting auto-conversion | Unexpected results or errors | Normalize to matching types before comparing |

## 15. Practice Exercises and Solutions

### Exercise 1 — Choosing Data Types

Choose the appropriate type for four fields:

1. A learner's date of birth.
2. Start time of a store work shift.
3. Timestamp when the system confirmed a transaction.
4. Duration of a 75-minute tutorial video.

**Answer:** `DATE`, `LOCAL TIME`, `ZONED DATETIME`, and `DURATION`, respectively. For work shifts, timezone or store context must also be managed at the application/model level.

### Exercise 2 — Creating a Datetime with Offset

Create a value for 2026-11-25 at 09:30 with offset UTC+07:

```cypher
RETURN datetime('2026-11-25T09:30:00+07:00') AS eventAt;
```

### Exercise 3 — Calculating a Deadline Three Days Later

Given `startedOn = date('2026-11-25')`, calculate the due date three calendar days later.

**Answer:**

```cypher
WITH date('2026-11-25') AS startedOn
RETURN startedOn + duration('P3D') AS dueOn;
```

Result: `2026-11-28`.

### Exercise 4 — Calculating Meeting Duration

A meeting starts at 14:00 and ends at 15:45 on the same day with the same UTC+07 offset. Compute its duration:

```cypher
WITH
  datetime('2026-11-25T14:00:00+07:00') AS startedAt,
  datetime('2026-11-25T15:45:00+07:00') AS finishedAt
RETURN duration.between(startedAt, finishedAt) AS meetingLength;
```

The result corresponds to **1 hour 45 minutes**.

### Exercise 5 — Finding Events Within a Day

Write a filter condition for `TemporalDemoEvent` nodes whose `occurredAt` falls on 2026-11-25 in UTC+07.

**Answer:**

```cypher
MATCH (e:TemporalDemoEvent)
WHERE e.occurredAt >= datetime('2026-11-25T00:00:00+07:00')
  AND e.occurredAt < datetime('2026-11-26T00:00:00+07:00')
RETURN e.eventId, e.occurredAt;
```

### Exercise 6 — Explaining DST

Why is storing only `localdatetime('2026-10-25T02:30:00')` insufficient to pinpoint a meeting's instant in a region observing daylight saving time?

**Answer:** because `LOCAL DATETIME` carries no timezone information, and on certain DST transition dates/regions, 02:30 can occur twice with two different offsets. You need the zone identifier plus rules for handling ambiguous times, or store the resolved instant as `ZONED DATETIME`.

## 16. Temporal Implementation Checklist in Neo4j

1. Does this field represent a **date**, **scheduled recurring time**, **event instant**, or **duration**?
2. Have you chosen `DATE`, `LOCAL TIME`, `ZONED DATETIME`, or `DURATION` according to its semantics?
3. For user-entered dates and times, where does the timezone/offset come from and how is it validated?
4. Does the application handle DST transition edge cases?
5. Is the business duration defined in calendar months/days or actual elapsed hours/seconds?
6. Is data from CSV/APIs converted to temporal types before writing?
7. Do date-range queries use `[start, end)` intervals instead of guessing end-of-day timestamps?
8. Are temporal fields mapped to the proper `java.time` types when using the Java Driver/Spring Data Neo4j?
9. Do updates distinguish "value omitted" from "null sent to delete the property"?
10. For temporal queries over large datasets, have you inspected `EXPLAIN`/`PROFILE` and considered a range index?

---

**Remember:** `DATE` expresses a calendar date; `LOCAL TIME` and `LOCAL DATETIME` carry no timezone; `ZONED TIME` and `ZONED DATETIME` include appropriate offset/zone info; `DURATION` expresses a span of time. When storing and querying connected data in Neo4j, separate **timestamps**, **schedule times**, and **durations**, handle timezone/DST semantics explicitly, and use temporal types with parameterized Cypher queries for consistency.
