# Converting Between Date, Instant, and java.time Types in Java

## 1. Why convert between the two API generations?

In many Java systems, temporal data passes through both legacy and modern code:

- Legacy APIs, drivers, or certain libraries may use `java.util.Date` and `java.util.Calendar`.
- Modern code typically uses types in `java.time` such as `Instant`, `LocalDate`, `LocalTime`, `LocalDateTime`, `ZonedDateTime`, and `OffsetDateTime`.
- SQL data sometimes uses `java.sql.Date`, `java.sql.Time`, or `java.sql.Timestamp`, which must **not** be equated with `java.util.Date` despite inheritance relationships.

The goal of conversion is to **preserve temporal meaning**, avoiding confusing an absolute instant with the displayed wall time of a region. A line of code that compiles is not necessarily business-correct if it ignores time zone, precision, or daylight saving time (DST).

For example, a UTC instant:

```text
2024-02-29T23:30:00Z
```

is the **exact same instant** as local time in `Asia/Ho_Chi_Minh`:

```text
2024-03-01T06:30:00+07:00
```

The two strings have **different calendar dates** yet point to the same instant. Therefore, converting from `Date` to `LocalDate` **requires a time zone policy**; Java cannot deduce a unique local date from epoch time alone.

## 2. Map of temporal types to remember

| Type | What does it represent? | Has time zone / offset? | When to use? |
|---|---|---|---|
| `java.util.Date` | A point on the timeline, API resolution in milliseconds | The object itself holds no zone | Legacy library compatibility |
| `Instant` | A point on the UTC timeline, nanosecond precision | Absolute instant; holds no zone name | Timestamps, logs, system communication |
| `LocalDate` | Year-month-day on a calendar | No | Birthdates, booking dates, business dates |
| `LocalTime` | Hour-minute-second within a day | No | Opening hours or daily appointment times |
| `LocalDateTime` | Date and time "on a clock" | No | Local schedule not yet bound to a zone |
| `OffsetDateTime` | Date/time with a fixed offset like `+07:00` | Has offset | Times carrying an offset in APIs |
| `ZonedDateTime` | Date/time bound to a `ZoneId` like `Europe/Paris`, using zone rules | Has zone and offset at that instant | Schedules, events spanning DST |
| `ZoneId` | Rule set for a time zone region | Represents the zone itself | Interpreting local time |
| `ZoneOffset` | Fixed offset relative to UTC | Has offset | Communication like `+07:00`, `Z` |

**Semantic anchor:** `Date` and `Instant` answer "**when**"; `LocalDateTime` answers "**what time the clock shows**", yet cannot identify a unique instant until bound to a time zone.

`Instant` is not "local time using GMT"; it is an absolute point on the timeline. `Date.toString()` may display using the JVM default time zone, but that **does not make Date an object that stores a timezone**.

## 3. Standard conversion between java.util.Date and Instant

The two most direct APIs:

```java
Instant instant = legacyDate.toInstant(); // Date -> Instant
Date legacyDate = Date.from(instant);     // Instant -> Date
```

With `Date`, import `java.util.Date` and `java.time.Instant` properly. When both statements are used together, declare variables in logical order:

```java
Instant instant = Instant.parse("2024-02-29T23:30:00Z");
Date legacyDate = Date.from(instant);
Instant restored = legacyDate.toInstant();
```

These statements do not depend on the JVM default time zone to determine the **instant**. Epoch data is preserved, **within the precision and range limits of Date**.

### Why can Instant -> Date lose precision?

`Instant` has nanoseconds; `java.util.Date` represents an instant as milliseconds since epoch via `getTime()`. When constructing a `Date` from an `Instant` whose nanosecond part is not divisible by 1,000,000, **the sub-millisecond fraction is not preserved**.

Example:

```text
Original Instant:        2024-02-29T23:30:00.123456789Z
After Date.from(...):    2024-02-29T23:30:00.123Z
```

This is not a timezone bug, but **precision loss** caused by converting to a type with millisecond granularity. If an application requires nanoseconds, a `java.util.Date` cannot preserve them; keep `Instant` or use an appropriate storage type.

`Date.from(Instant)` can also throw `IllegalArgumentException` if `Instant` lies outside `Date`'s representable range; do not assume every `Instant.MIN/MAX` value can be converted.

### Why should Date.toString not be used for verification?

`System.out.println(date)` calls `Date.toString()`, whose string output depends on the environment's default timezone. For stable comparisons, log `date.toInstant()`, `date.getTime()`, or use a formatter with an explicit `ZoneId`.

## 4. Java 17+ program: Date ⇄ Instant with a fixed timestamp

Save as `DateInstantDemo.java`:

```java
import java.time.Instant;
import java.util.Date;

public class DateInstantDemo {
    public static void main(String[] args) {
        Instant original =
                Instant.parse("2024-02-29T23:30:00.123456789Z");

        Date legacy = Date.from(original);
        Instant restored = legacy.toInstant();

        System.out.println("instant=" + original);
        System.out.println("legacyMillis=" + legacy.getTime());
        System.out.println("restored=" + restored);
        System.out.println("same=" + original.equals(restored));
    }
}
```

Compile and run:

```bash
javac DateInstantDemo.java
java DateInstantDemo
```

Verified output on Java 17+:

```text
instant=2024-02-29T23:30:00.123456789Z
legacyMillis=1709249400123
restored=2024-02-29T23:30:00.123Z
same=false
```

Explanation:

1. `Instant.parse(...)` creates a point on the UTC timeline.
2. `Date.from(original)` converts it to the legacy object with milliseconds.
3. `Date.getTime()` returns milliseconds since the Unix epoch (`1970-01-01T00:00:00Z`).
4. `Date.toInstant()` reconstructs an instant from the retained milliseconds.
5. `original.equals(restored)` is `false` because the `456789` nanosecond remainder was lost.

If the initial `Instant` only has millisecond precision and falls within the supported range, a round-trip normally preserves the instant.

**Note on negative pre-epoch values:** When converting sub-millisecond epochs around `1970-01-01T00:00:00Z`, do not replace `Date.from(instant)` with truncate-toward-zero division of nanos/1,000,000, because epoch conversions have specific rules for negative numbers. Use standard APIs rather than hand-rolled arithmetic.

## 5. Date / Instant to ZonedDateTime and LocalDateTime

To display the local date and time of a specific region from an `Instant`, attach a `ZoneId`:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned =
        legacyDate.toInstant().atZone(zone);

LocalDateTime localDateTime =
        zoned.toLocalDateTime();
```

Formula:

```text
Date -> Instant -> ZonedDateTime(zone) -> LocalDateTime
```

For the instant `2024-02-29T23:30:00.123Z`, in `Asia/Ho_Chi_Minh` it becomes `2024-03-01T06:30:00.123`.

### Standalone Java 17+ example

Save `DateToLocalDemo.java`:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Date;

public class DateToLocalDemo {
    public static void main(String[] args) {
        Date legacy = Date.from(
                Instant.parse("2024-02-29T23:30:00.123Z"));

        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
        LocalDateTime local =
                legacy.toInstant().atZone(zone).toLocalDateTime();
        LocalDate date =
                legacy.toInstant().atZone(zone).toLocalDate();

        System.out.println("local=" + local);
        System.out.println("date=" + date);
        System.out.println("utcLocal=" +
                legacy.toInstant()
                        .atZone(ZoneOffset.UTC)
                        .toLocalDateTime());
    }
}
```

Run:

```bash
javac DateToLocalDemo.java
java DateToLocalDemo
```

Output:

```text
local=2024-03-01T06:30:00.123
date=2024-03-01
utcLocal=2024-02-29T23:30:00.123
```

For the same `Date`, the local date in UTC and Vietnam differs. If the business asks for "the date of the event" without a zone, the problem is **underspecified**.

**Do not** obtain a `LocalDateTime` by slicing `Date.toString()`; string formatting depends on the JVM and locale. Nor should you call `LocalDateTime.now()` to "convert" an existing `Date`: `now()` reads the current time, not the input timestamp.

## 6. LocalDateTime / ZonedDateTime / OffsetDateTime back to Date

To obtain a `Date` from a local date and time, you must supply a **zone or offset** to convert to an instant:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDateTime local =
        LocalDateTime.of(2024, 3, 1, 6, 30, 0, 123_000_000);

Date date = Date.from(local.atZone(zone).toInstant());
```

Result:

```text
2024-02-29T23:30:00.123Z
```

When writing a complete program, use `date.toInstant()` for stable display of the result.

Common conversion paths:

| Source | Convert to Instant | Then |
|---|---|---|
| `ZonedDateTime` | `zoned.toInstant()` | `Date.from(...)` |
| `OffsetDateTime` | `offsetDateTime.toInstant()` | `Date.from(...)` |
| `LocalDateTime` | `localDateTime.atZone(zone).toInstant()` | `Date.from(...)` |
| `LocalDate` | `localDate.atStartOfDay(zone).toInstant()` | `Date.from(...)` |
| `LocalTime` | Must be combined with a `LocalDate` and zone/offset | Cannot form an Instant on its own |

**Avoid blindly calling `localDateTime.toEpochSecond(ZoneOffset.UTC)`** if that local time actually belongs to a region with a non-UTC offset. That call is only valid if you **deliberately define** the time in `LocalDateTime` as UTC.

### LocalDate to Date: no single universal conversion

A `LocalDate` such as `2024-03-01` corresponds to many instants across different zones. If you need "start of day per zone rules", use:

```java
LocalDate localDate = LocalDate.of(2024, 3, 1);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Date startOfDay =
        Date.from(localDate.atStartOfDay(zone).toInstant());
```

`atStartOfDay(zone)` handles the time zone rules for that day. It is not always as simple as combining `LocalTime.MIDNIGHT` and assuming every local day has a valid 00:00: in some regions with midnight DST transitions or historical adjustments, the start of day may be adjusted to the earliest valid instant.

If the data domain is **birthdates, expiration dates, or holidays** and has no need for an absolute instant, it is best to **keep `LocalDate`**. Convert to `Date` only when the target API strictly requires it and the business has defined the zone/day rule.

## 7. How does ZonedDateTime differ from OffsetDateTime?

An offset like `+07:00` is a fixed difference from UTC at a point in time, whereas a `ZoneId` like `Europe/Paris` contains **historical rules and seasonal changes**.

Example:

```java
Instant moment = Instant.parse("2024-02-29T23:30:00Z");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = moment.atZone(zone);
OffsetDateTime offset = moment.atOffset(ZoneOffset.ofHours(7));
```

Both may show the same wall-clock time, yet:

- `zoned` carries the region's `ZoneId`, enabling calculations across future offset transitions.
- `offset` carries only the fixed `+07:00` offset.
- Both return the same absolute instant from `toInstant()`.

When formatting API payloads, `OffsetDateTime` is often suitable for timestamps with an offset, whereas recurring schedules like "9 AM in Paris" need `ZoneId` because the offset can change seasonally. Do not replace an entire zone with its current offset and assume that offset holds for every past and future date.

`Instant` does not retain the original `ZoneId`. Converting `ZonedDateTime -> Instant -> ZonedDateTime` with a **different zone** still preserves the instant, but does not preserve the original local display or zone name.

## 8. Daylight Saving Time: gaps and overlaps change results

Some zones observe **DST**. When clocks spring forward, a span of local time **does not exist** (*gap*). When clocks fall back, a span of local time occurs **twice** with two different offsets (*overlap*).

`LocalDateTime` only holds wall-clock date/time, so calling `LocalDateTime.atZone(zone)` may apply the zone's default resolution rules:

- **Gap:** the nonexistent local time is shifted forward to a valid time, usually by the length of the gap.
- **Overlap:** the local time has two valid offsets; `atZone` normally picks the earlier offset per Java rules. You can call `withLaterOffsetAtOverlap()` to select the other offset.

### Java 17+ program demonstrating DST

Save `DstConversionDemo.java`:

```java
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZonedDateTime;

public class DstConversionDemo {
    public static void main(String[] args) {
        ZoneId paris = ZoneId.of("Europe/Paris");

        ZonedDateTime gap =
                LocalDateTime.parse("2024-03-31T02:30:00")
                        .atZone(paris);

        ZonedDateTime overlap =
                LocalDateTime.parse("2024-10-27T02:30:00")
                        .atZone(paris);

        System.out.println("gap=" + gap);
        System.out.println("overlap=" + overlap);
        System.out.println("later=" +
                overlap.withLaterOffsetAtOverlap());
    }
}
```

Run:

```bash
javac DstConversionDemo.java
java DstConversionDemo
```

Output on Java 17 with corresponding time zone rules:

```text
gap=2024-03-31T03:30+02:00[Europe/Paris]
overlap=2024-10-27T02:30+02:00[Europe/Paris]
later=2024-10-27T02:30+01:00[Europe/Paris]
```

On March 31, 2024 in Paris, `02:30` does not exist because clocks jump from 2 AM to 3 AM, so Java adjusts it to `03:30+02:00`. On October 27, 2024, `02:30` occurs twice: first at `+02:00`, then again at `+01:00`.

To let users choose an **exact** instant during an overlap, additional offset information or policy is required. For critical schedule data, check `zone.getRules().getValidOffsets(localDateTime)` before attaching a zone if you want to reject gaps/overlaps instead of using defaults.

**Common misconception:** stating "`LocalDateTime` and `Instant` convert one-to-one." That is false: some `LocalDateTime` values map to zero instants in a given zone (gap), and some map to two instants (overlap).

## 9. java.util.Date vs. java.sql.Date and java.sql.Timestamp

Sharing the name `Date` easily causes confusion.

### `java.util.Date`

This is the legacy class representing an instant in milliseconds. Usage:

```java
Instant instant = utilDate.toInstant();
java.util.Date converted = java.util.Date.from(instant);
```

This is an illustrative snippet with `utilDate` already declared.

### `java.sql.Date`

`java.sql.Date` is designed for SQL `DATE` — a **calendar date**, not a timestamp with precise time of day. Although it subclasses `java.util.Date`, it **overrides `toInstant()` to throw `UnsupportedOperationException`**.

Therefore, the following code is **unsafe**:

```java
java.sql.Date sqlDate =
        java.sql.Date.valueOf("2024-03-01");
Instant instant = sqlDate.toInstant(); // UnsupportedOperationException
```

If the SQL data is a date without time, use:

```java
LocalDate day = sqlDate.toLocalDate();
java.sql.Date converted = java.sql.Date.valueOf(day);
```

When working with modern JDBC, if the driver supports JDBC 4.2, you can read SQL DATE directly via `ResultSet.getObject(column, LocalDate.class)` instead of detouring through the legacy class. Verify actual driver support.

**Do not cast `java.sql.Date` to `java.util.Date` and call `toInstant()` hoping to avoid the error.** Virtual method dispatch still executes `java.sql.Date`'s override.

### `java.sql.Timestamp`

`java.sql.Timestamp` serves SQL TIMESTAMP and adds a nanosecond component beyond `java.util.Date`. Methods include:

```java
java.sql.Timestamp timestamp =
        java.sql.Timestamp.from(instant);

Instant restored = timestamp.toInstant();
```

For the `Instant` example `2024-02-29T23:30:00.123456789Z`, `Timestamp.from(instant).toInstant()` can preserve nanosecond precision in memory. However, **SQL column types and databases** may only support limited precision or have different timezone semantics, so round-tripping through a DB is not guaranteed to retain every nanosecond.

Distinguish SQL `TIMESTAMP WITHOUT TIME ZONE` from `TIMESTAMP WITH TIME ZONE` according to **specific driver/DB semantics**; never assume every `Timestamp` is a true UTC instant. If the SQL column is a zoneless local date-time, `LocalDateTime` may be more appropriate when supported by JDBC.

## 10. Calendar to java.time and back

`java.util.Calendar` holds additional timezone, calendar-system, and mutable state; to extract the instant:

```java
Calendar calendar = Calendar.getInstance();
Instant instant = calendar.toInstant();
```

If you want to preserve zone information from a `GregorianCalendar`:

```java
java.util.GregorianCalendar calendar =
        new java.util.GregorianCalendar(
                java.util.TimeZone.getTimeZone("Europe/Paris"));

java.time.ZonedDateTime zoned =
        calendar.toZonedDateTime();
```

When bridging from `ZonedDateTime` back to legacy GregorianCalendar:

```java
java.util.GregorianCalendar restored =
        java.util.GregorianCalendar.from(zoned);
```

The two snippets above are **illustrative fragments**, not complete programs, and do not claim that every `Calendar` configuration property is preserved. For example, first week of year, chronology, and legacy Calendar leniency options may need separate handling.

Beware of `Calendar.MONTH` in the legacy API: it uses 0–11 indices, whereas `LocalDate.getMonthValue()` is 1–12. Never transfer month numbers by copying them directly without accounting for the difference.

## 11. Default ZoneId or explicit zone?

Code like this can look convenient:

```java
LocalDateTime local =
        date.toInstant()
                .atZone(ZoneId.systemDefault())
                .toLocalDateTime();
```

`ZoneId.systemDefault()` reads the JVM environment's default zone. It may be acceptable for an application **serving only one fixed configured zone**, yet easily causes bugs on cloud, container, CI, or multi-user services:

- A developer laptop uses `Asia/Ho_Chi_Minh`, while a container uses `UTC`.
- A Paris customer's schedule data gets interpreted in a server's zone in Vietnam.
- An environment configuration change shifts local dates across midnight.

**Recommendation:** pass a business-meaningful `ZoneId` explicitly via parameters or configuration. For timestamps used in storage/exchange, keep `Instant` as long as possible; apply a zone only at the display boundary or when evaluating local-date logic.

Do not call `TimeZone.setDefault(...)` per request: it is global state that can affect other threads. In tests, construct explicit `ZoneId`s for stable results.

## 12. Precision discrepancies: nano, milli, and range bounds

Types have different precision capabilities:

| Type | Temporal representation capability |
|---|---|
| `Instant` | Nanoseconds per the java.time model |
| `LocalDateTime` | Nanoseconds, **no instant yet** |
| `ZonedDateTime` | Nanoseconds plus zone rules |
| `java.util.Date` | Milliseconds |
| `java.sql.Timestamp` | Has extra nanosecond field, though DB storage precision may be lower |

Document precision-loss boundaries clearly in code and tests:

```java
Instant original =
        Instant.parse("2024-02-29T23:30:00.123456789Z");

Instant afterLegacy =
        java.util.Date.from(original).toInstant();

// afterLegacy = 2024-02-29T23:30:00.123Z
```

Milliseconds are not just "displaying 3 decimal digits"; they are the **resolution of a Date value**. If a system uses timestamps to order events occurring closely together, passing through legacy `Date` can collapse two distinct events onto the same millisecond.

Beyond resolution, supported date ranges across types do not completely overlap either. Conversions between very wide-range types and `Date`/epoch milliseconds can fail. Never convert large timestamps via manual millisecond multiplication without checking for overflow.

## 13. Preserving semantics across application conversions

### An event occurring at an instant

For example, "Payment confirmed at 2024-02-29T23:30Z". That is an instant. Use `Instant` in the domain/API; when legacy compatibility is mandatory, use `Date.from(instant)` and accept millisecond limits. Display via `instant.atZone(userZone)`.

### Appointments in local time

For example, "appointment at 09:00 on Oct 27, 2024 in Paris". To pinpoint the exact instant, you need `LocalDateTime` **plus** `ZoneId`, and on a DST overlap day you may need an offset or resolution policy. Store epoch milliseconds only after resolving the instant, if the domain truly requires a unique point in time.

### Birthdates / expiration dates

For example, "2024-03-01" with no time of day. Use `LocalDate`. Converting through `Date` as midnight UTC and then displaying in a negative-offset zone can shift it to the previous day, causing calendar errors. Convert to an instant only if business rules define "start of day in which zone."

### APIs returning timestamps with offsets

For example, `2024-03-01T06:30:00+07:00` can be parsed with `OffsetDateTime.parse(...)`, then `.toInstant()` to compare points in time:

```java
OffsetDateTime fromApi =
        OffsetDateTime.parse("2024-03-01T06:30:00+07:00");
Instant timestamp = fromApi.toInstant();

// timestamp = 2024-02-29T23:30:00Z
```

Do not call `LocalDateTime.parse(...)` on a string containing an offset and discard the offset. If you need to preserve source offset/zone details for re-display, store them separately per business requirements.

## 14. Testing error-prone cases

A conversion test suite should cover:

| Test case | What to verify |
|---|---|
| `Date.from(instant).toInstant()` with whole milliseconds | Preserves the instant |
| Instant with sub-millisecond nanoseconds | Confirms precision truncation |
| Instant near UTC midnight | Different LocalDates between UTC and other regions |
| `LocalDateTime.atZone(...)` in a DST gap | Explicit adjustment or rejection policy verified |
| LocalDateTime in a DST overlap | Which offset is chosen and whether user confirmation is needed |
| `ZoneId.of("Europe/Paris")` vs. `+01:00` offset | Never equate a zone with a fixed offset |
| `java.sql.Date.toInstant()` | Knows this method throws `UnsupportedOperationException` |
| `java.sql.Date.toLocalDate()` | Extracts calendar date with the right type |
| `Timestamp.from(instant).toInstant()` | In-memory nanoseconds vs. actual DB precision |
| System running in `UTC` and `Asia/Ho_Chi_Minh` | Output unchanged when zone is explicit |
| Legacy `Calendar` month numbers | Never confuse 0–11 with 1–12 |

In new code, unit tests should use **fixed temporal inputs** like `Instant.parse("...Z")` and `ZoneId.of("...")`. Avoid `Instant.now()` or `ZoneId.systemDefault()` in tests expecting deterministic output, as results will depend on the host machine and execution time.

## 15. Common mistakes

1. **Thinking Date has a timezone.** `java.util.Date` holds an instant; `toString()` formats it in the environment's timezone.
2. **Converting Date directly to LocalDate without choosing a zone.** Local date depends on the zone.
3. **Using `LocalDateTime.now()` to convert an old Date.** It reads current time, ignoring the input.
4. **Treating LocalDateTime as a UTC instant.** LocalDateTime carries no zone/offset.
5. **Using a fixed offset instead of ZoneId.** Loses DST history and transition rules.
6. **Ignoring DST gaps and overlaps.** Nonexistent times get shifted or one of two offsets gets picked silently.
7. **Expecting `Date.from(instant)` to keep nanoseconds.** Date holds only milliseconds.
8. **Using Date.toString() as a serializer.** Output depends on default timezone and is not a stable contract.
9. **Equating `java.sql.Date` with `java.util.Date`.** `java.sql.Date.toInstant()` throws `UnsupportedOperationException`; use `toLocalDate()` for SQL DATE.
10. **Assuming SQL TIMESTAMP always has a zone.** Semantics depend on column type and driver.
11. **Storing birthdates as UTC midnight and displaying in another zone.** Dates can shift backward by one day.
12. **Using the server's default timezone for all users.** Output changes with the environment rather than user location or data meaning.
13. **Not testing milli vs. nano precision.** Round-tripping through legacy Date can drop data.
14. **Using `Calendar.MONTH` as 1–12.** Legacy Calendar numbers months starting from 0.
15. **Computing epoch manually with unchecked int/long math.** Prone to overflow or bugs with negative pre-1970 values.

## 16. Self-check questions

**Question 1.** Which method converts from `java.util.Date` to `Instant`?

**Answer:** `date.toInstant()`.

**Question 2.** What converts from `Instant` to `java.util.Date`, and what is the limitation?

**Answer:** `Date.from(instant)`; sub-millisecond nanoseconds can be lost.

**Question 3.** Can you convert a `Date` to a `LocalDate` without knowing a zone?

**Answer:** You cannot uniquely determine the **intended local date**; you need `date.toInstant().atZone(zone).toLocalDate()` with the business-appropriate zone.

**Question 4.** In `Asia/Ho_Chi_Minh`, what date is `2024-02-29T23:30:00Z`?

**Answer:** `2024-03-01`, at 06:30 local time.

**Question 5.** If a `LocalDateTime` falls inside a DST overlap, does it always identify a single instant?

**Answer:** No. Two valid offsets/instants exist; a selection rule is required.

**Question 6.** Is `java.sql.Date.toInstant()` the same as `java.util.Date.toInstant()`?

**Answer:** No. SQL Date overrides it to throw `UnsupportedOperationException`; use `toLocalDate()` to get the date.

**Question 7.** Should `LocalDate.atStartOfDay(zone).toInstant()` be used to store a birthdate without retaining the zone?

**Answer:** No. A birthdate is a `LocalDate`; if forced to convert to an instant, the zone must be explicitly defined and care taken not to lose date semantics.

**Question 8.** `Timestamp.from(instant).toInstant()` keeps nanoseconds in Java; can you be sure the DB also keeps nanoseconds?

**Answer:** No. Column and DB driver precision and semantics may be lower.

## 17. Key takeaways

Choose the temporal type based on **data semantics** before converting: `Instant`/`Date` for absolute instants, `LocalDate` for calendar dates, `LocalDateTime` for unzoned local time, and `ZonedDateTime` for zoned times with DST rules. The direct bridges **`Date.toInstant()`** and **`Date.from(Instant)`** are straightforward, subject to millisecond precision limits. Converting from an instant to a local representation requires an **explicit `ZoneId`**. For SQL DATE, use `LocalDate` instead of trying to turn it into an instant.

**Official documentation:** [Java SE 17 — java.util.Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Date.html) · [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html) · [Java SE 17 — LocalDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalDateTime.html) · [Java SE 17 — ZonedDateTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/ZonedDateTime.html) · [Java SE 17 — java.sql.Date](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Date.html) · [Java SE 17 — Timestamp](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Timestamp.html).
