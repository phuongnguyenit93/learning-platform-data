# Conversion Map Between Main Date and Time Types in Java

In `java.time`, temporal data types **do not just differ in name**: each type carries a different amount of information and meaning. A `LocalDate` is only a calendar date, `LocalTime` is only a wall-clock time, while `Instant` represents a global point on the timeline. To convert between them properly, you first need to know **what data you currently have**, **what data you need to keep**, and **what information must be supplied**.

For example, `2025-01-15T09:30` cannot yet be converted on its own into a unique `Instant` because it is unknown whether it is 09:30 in Hanoi, Paris, or New York. Conversely, `2025-01-15T02:30:00Z` is a determined `Instant`; when displayed in Vietnam on that date, it will be 09:30 with offset `+07:00`.

**Core rule:** Converting from an absolute point in time to local time requires choosing a **time zone/offset**; converting from a local date-time to an absolute point in time also requires choosing a **time zone/offset and resolving ambiguous DST times if any**. Extracting date/time components can **lose information** and cannot necessarily be reversed.

## 1. Identifying the Eight Common Components

| Type | Has date? | Has time? | Offset / zone? | Identifies an `Instant`? | Example |
| --- | --- | --- | --- | --- | --- |
| `LocalDate` | Yes | No | No | No | `2025-01-15` |
| `LocalTime` | No | Yes | No | No | `09:30` |
| `LocalDateTime` | Yes | Yes | No | **No** | `2025-01-15T09:30` |
| `Instant` | Absolute point in time | Absolute point in time | Does not store zone name; usually represented in UTC | **Yes** | `2025-01-15T02:30:00Z` |
| `OffsetTime` | No | Yes | Fixed UTC offset | No, because date is missing | `09:30+07:00` |
| `OffsetDateTime` | Yes | Yes | Fixed UTC offset | **Yes** | `2025-01-15T09:30+07:00` |
| `ZonedDateTime` | Yes | Yes | `ZoneId` and offset corresponding to the instant | **Yes** | `2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]` |
| `ZoneId` / `ZoneOffset` | Not a time | Not a time | Region rules / UTC offset | Not by itself | `Asia/Ho_Chi_Minh` / `+07:00` |

Two other important types that are **not points in time**:

- `Duration`: **elapsed time** measured in seconds/nanoseconds, such as `PT1H30M`. It does not have a start date or time zone on its own.
- `Period`: **calendar-based amount** (years, months, days), such as `P1M`. One month cannot be converted into a fixed number of seconds without choosing an applicable date/zone.

**Do not confuse `LocalDateTime` with `Instant`:** the word “Local” is the core information. It does not store an offset and is not a global timestamp. Any type name that already has a zone or offset should be clearly documented in variable names/API contracts when data flows across multiple systems.

## 2. Overview Map of Conversion Paths

```text
                       LocalDate + LocalTime
                         |           |
                         +---- of() --+
                               |
                               v
                         LocalDateTime
                         /           \
                atZone(ZoneId)    atOffset(ZoneOffset)
                     /                 \
                    v                   v
              ZonedDateTime       OffsetDateTime
                  |     \             /     |
      toLocal*()  |      toInstant()  /      | toLocal*()
                  |         \        /       |
                  v          v      v        v
           LocalDate/Time       Instant    LocalDateTime
                 ^               |   |
                 |   atZone(zone)|   |atOffset(offset)
                 +---------------+---+
                                 |
                     Date.from / Date.toInstant
                                 |
                          java.util.Date
```

This is a directional diagram; not all arrows are completely symmetric. Note:

1. `Instant → ZonedDateTime` with a `ZoneId` is an **unambiguous** mapping: `instant.atZone(zone)`.
2. `Instant → OffsetDateTime` with a `ZoneOffset` is also unambiguous: `instant.atOffset(offset)`.
3. `LocalDateTime → ZonedDateTime` requires a `ZoneId`; during a DST gap/overlap, a resolution policy is also needed.
4. `LocalDateTime → OffsetDateTime` only requires the provided `ZoneOffset`; this approach **does not automatically check whether the offset is valid in a geographic region**, because the zone is not an input.
5. `ZonedDateTime/OffsetDateTime → Instant` can be done with `toInstant()`. If you drop the zone/offset via `toLocalDateTime()`, you **lose the data needed to distinguish the actual instant**.
6. `LocalDate` and `LocalTime` can be combined into `LocalDateTime` via `date.atTime(time)`, but cannot reach `Instant` on their own without adding a zone/offset.
7. `java.util.Date` can bridge to `Instant`, but is limited to **millisecond** precision.

## 3. Specific Method Map: From Where to Where?

| From type | To type | Standard conversion | Needs extra info or loses info? |
| --- | --- | --- | --- |
| `LocalDate` + `LocalTime` | `LocalDateTime` | `LocalDateTime.of(date, time)` or `date.atTime(time)` | Combines existing date and time, without attaching a zone. |
| `LocalDateTime` | `LocalDate` | `local.toLocalDate()` | **Drops the time part**. |
| `LocalDateTime` | `LocalTime` | `local.toLocalTime()` | **Drops the date part**. |
| `Instant` | `ZonedDateTime` | `instant.atZone(zone)` | **Needs `ZoneId`**, preserves the instant. |
| `Instant` | `OffsetDateTime` | `instant.atOffset(offset)` | **Needs `ZoneOffset`**, preserves the instant. |
| `Instant` | `LocalDateTime` | `LocalDateTime.ofInstant(instant, zone)` | **Needs zone/offset**, drops that info in the result. |
| `ZonedDateTime` | `Instant` | `zoned.toInstant()` | Preserves the instant, **loses the zone name** in the return type. |
| `OffsetDateTime` | `Instant` | `offsetDateTime.toInstant()` | Preserves the instant, **loses the display offset** in the return type. |
| `ZonedDateTime` | `LocalDateTime` | `zoned.toLocalDateTime()` | **Loses zone + offset**. |
| `OffsetDateTime` | `LocalDateTime` | `offsetDateTime.toLocalDateTime()` | **Loses offset**. |
| `ZonedDateTime` | `LocalDate` / `LocalTime` | `zoned.toLocalDate()` / `zoned.toLocalTime()` | Extracts only the date or time, drops everything else. |
| `OffsetDateTime` | `OffsetTime` | `offsetDateTime.toOffsetTime()` | **Drops the date**, keeps time + offset. |
| `LocalTime` + `ZoneOffset` | `OffsetTime` | `time.atOffset(offset)` | Adds offset, still missing date. |
| `OffsetTime` + `LocalDate` | `OffsetDateTime` | `offsetTime.atDate(date)` or `date.atTime(offsetTime)` | Adds date, can be converted to `Instant`. |
| `LocalDateTime` | `ZonedDateTime` | `local.atZone(zone)` | Needs zone; has default rules for handling DST. |
| `LocalDateTime` | `OffsetDateTime` | `local.atOffset(offset)` | Needs fixed offset; does not check `ZoneRules`. |
| `OffsetDateTime` | `ZonedDateTime` | `offsetDateTime.atZoneSameInstant(zone)` | Needs zone; **preserves the instant**, local time may change. |
| `ZonedDateTime` | `OffsetDateTime` | `zoned.toOffsetDateTime()` | Preserves the instant and current offset; loses zone name. |
| `ZonedDateTime` | `ZonedDateTime` in another zone | `zoned.withZoneSameInstant(otherZone)` | **Preserves `Instant`**, usually changes displayed time. |
| `LocalDate` | Start-of-day `ZonedDateTime` | `date.atStartOfDay(zone)` | Needs `ZoneId`, follows the valid start of day in the zone. |
| `Instant` | `java.util.Date` | `Date.from(instant)` | May **lose sub-millisecond precision**. |
| `java.util.Date` | `Instant` | `date.toInstant()` | `Date` values only have millisecond precision. |

**Two different directions:** When extracting components from a richer value like `ZonedDateTime.toLocalDateTime()`, the discarded information can make it **impossible to convert back accurately**. Conversely, converting from `Instant` to a type with a provided zone is a representation of the **same actual instant**. To restore the original point in time, the appropriate supplementary information must be kept.

## 4. Converting from `Instant` to User Time

Suppose an event occurs at:

```text
2025-01-15T02:30:00Z
```

A user in Vietnam needs to view the time in `Asia/Ho_Chi_Minh`. Create a `ZonedDateTime`:

```java
Instant event = Instant.parse("2025-01-15T02:30:00Z");
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime localView = event.atZone(vietnam);
// 2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]
```

This snippet requires `import java.time.*;`. `atZone` **does not make the event happen 7 hours later**. It only changes the representation of the same `Instant` to the corresponding local time and offset. When converting back:

```java
Instant sameEvent = localView.toInstant();
// 2025-01-15T02:30:00Z
```

You can also convert directly to a local date-time:

```java
LocalDateTime displayOnly =
        LocalDateTime.ofInstant(event, vietnam);
// 2025-01-15T09:30
```

The result is only a `LocalDateTime`, meaning the zone information is **not stored in the new object**. If the system only wants to display it, that is usually appropriate; if you need to exchange global timestamps, store `Instant` and `ZoneId` separately if needed.

### `ZoneId` vs. `ZoneOffset`

- `ZoneId.of("Asia/Ho_Chi_Minh")` represents a **region with historical/future rules**. `ZonedDateTime` can have the corresponding zone rules applied.
- `ZoneOffset.ofHours(7)` only represents a **fixed +07:00** offset. It does not contain a city name or the full history of zone rules.
- `OffsetDateTime` can provide a complete global timestamp when it has date, time, and offset, but if business logic needs recurring schedules in a specific location, keeping `ZoneId` remains important.

For a known `Instant`, using `event.atOffset(ZoneOffset.ofHours(7))` gives the `OffsetDateTime` `2025-01-15T09:30+07:00`, still pointing to that same `Instant`.

## 5. From Local Date-Time to Global Instant

`LocalDateTime.of(2025, 1, 15, 9, 30)` by itself **does not determine** an `Instant`. A zone or offset must be supplied.

### With `ZoneId`: create `ZonedDateTime` then `Instant`

```java
LocalDateTime local = LocalDateTime.of(2025, 1, 15, 9, 30);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

ZonedDateTime zoned = local.atZone(zone);
Instant moment = zoned.toInstant();
// 2025-01-15T02:30:00Z
```

This approach **applies the `ZoneRules`** of the region. For normal hours, there is one valid offset. However, across DST transitions:

- **Gap:** the local time may not exist. `atZone(zone)` by default adjusts forward past the missing interval.
- **Overlap:** the local time may correspond to **two offsets**. `atZone(zone)` by default usually picks the earlier offset on the timeline; business logic may need to pick the later one or reject ambiguity.

### With `ZoneOffset`: compute the instant from a fixed offset

```java
LocalDateTime local = LocalDateTime.of(2025, 1, 15, 9, 30);
ZoneOffset offset = ZoneOffset.ofHours(7);

Instant moment = local.toInstant(offset);
OffsetDateTime offsetValue = local.atOffset(offset);
// Both moment and offsetValue.toInstant() are 2025-01-15T02:30:00Z
```

`toInstant(offset)` and `atOffset(offset).toInstant()` use the **provided offset**, without checking whether it matches any geographic `ZoneId`. If the data comes from an appointment in a city with DST, use the actual zone and resolve gaps/overlaps explicitly rather than forcing a guessed offset.

### Why can't you call `local.toInstant()` with no arguments?

Because `LocalDateTime` does not contain a zone or offset to identify an actual instant, Java requires you to pass a `ZoneOffset` if using `toInstant` directly. You cannot infer UTC from the string `2025-01-15T09:30` just because the DB column is named `createdAt`.

## 6. Combining and Splitting `LocalDate`, `LocalTime`, `LocalDateTime`

When UI data has two separate inputs:

```java
LocalDate date = LocalDate.of(2025, 1, 15);
LocalTime time = LocalTime.of(9, 30);

LocalDateTime local = LocalDateTime.of(date, time);
// Equivalent: date.atTime(time)
// Equivalent: time.atDate(date)
```

Extracting each part back:

```java
LocalDate extractedDate = local.toLocalDate();
LocalTime extractedTime = local.toLocalTime();
```

These snippets are illustrated inside a method with `import java.time.*;`. **Combining date + time does not mean attaching a time zone.** Conversely, extracting just the date or time discards the remaining information.

If you only have a `LocalDate` and want the start-of-day instant for a zone, use:

```java
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime startOfBusinessDay = date.atStartOfDay(zone);
Instant dayStart = startOfBusinessDay.toInstant();
```

`date.atTime(LocalTime.MIDNIGHT)` only creates a `LocalDateTime` at `00:00`, without a zone attached. `date.atStartOfDay(zone)` finds the **valid start of day according to the zone**; in some zones where an offset transition occurs right at midnight, the two approaches cannot be treated as completely equivalent when determining the actual instant.

### Adding an offset to a time without a date

`OffsetTime` carries a wall-clock time and an offset, but **has no date**:

```java
OffsetTime officeTime = LocalTime.of(9, 30)
        .atOffset(ZoneOffset.ofHours(7));
// 09:30+07:00

OffsetDateTime dated = officeTime.atDate(LocalDate.of(2025, 1, 15));
// 2025-01-15T09:30+07:00

Instant instant = dated.toInstant();
// 2025-01-15T02:30:00Z
```

To get an `Instant`, you must add a date; `OffsetTime` alone is not enough. Nor does an offset replace `ZoneId` when recurring work-hour schedules depend on a region with time-change rules.

## 7. Complete Java 17+ Example: Walking Through the Main Types

Create the file **`DateTimeConversionMapDemo.java`**. The example fixes `Instant` so the output does not depend on the runtime or the JVM's default time zone:

```java
import java.time.*;
import java.util.Date;

public class DateTimeConversionMapDemo {
    public static void main(String[] args) {
        Instant instant = Instant.parse("2025-01-15T02:30:00Z");
        ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

        ZonedDateTime zoned = instant.atZone(zone);
        LocalDate localDate = zoned.toLocalDate();
        LocalTime localTime = zoned.toLocalTime();
        LocalDateTime localDateTime =
                LocalDateTime.of(localDate, localTime);
        ZoneOffset offset = zoned.getOffset();
        OffsetDateTime offsetDateTime = instant.atOffset(offset);
        OffsetTime offsetTime = offsetDateTime.toOffsetTime();

        System.out.println("Instant           : " + instant);
        System.out.println("ZonedDateTime     : " + zoned);
        System.out.println("LocalDate         : " + localDate);
        System.out.println("LocalTime         : " + localTime);
        System.out.println("LocalDateTime     : " + localDateTime);
        System.out.println("OffsetDateTime    : " + offsetDateTime);
        System.out.println("OffsetTime        : " + offsetTime);
        System.out.println("Round-trip via zone   : "
                + localDateTime.atZone(zone).toInstant());
        System.out.println("Round-trip via offset : "
                + localDateTime.toInstant(offset));
        System.out.println("Date + time       : "
                + localDate.atTime(localTime));
        System.out.println("Epoch millis      : "
                + instant.toEpochMilli());

        Date legacy = Date.from(instant);
        System.out.println("Legacy round-trip : "
                + legacy.toInstant());
        System.out.println("Time preserved    : "
                + instant.equals(legacy.toInstant()));
    }
}
```

Commands to run on JDK 17+:

```bash
javac DateTimeConversionMapDemo.java
java DateTimeConversionMapDemo
```

Compiled and verified output:

```text
Instant           : 2025-01-15T02:30:00Z
ZonedDateTime     : 2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]
LocalDate         : 2025-01-15
LocalTime         : 09:30
LocalDateTime     : 2025-01-15T09:30
OffsetDateTime    : 2025-01-15T09:30+07:00
OffsetTime        : 09:30+07:00
Round-trip via zone   : 2025-01-15T02:30:00Z
Round-trip via offset : 2025-01-15T02:30:00Z
Date + time       : 2025-01-15T09:30
Epoch millis      : 1736908200000
Legacy round-trip : 2025-01-15T02:30:00Z
Time preserved    : true
```

**Reading the output:**

1. `Instant` is fixed at `02:30Z`, while `ZonedDateTime` displays `09:30+07:00`. Both representations are the **same actual instant**.
2. `LocalDate` and `LocalTime` are extracted from `zoned`; `LocalDateTime.of(date, time)` recombines the date and time. Splitting and recombining here did not lose date/time digits, but **the new value itself no longer carries a zone or offset**.
3. `OffsetDateTime` represents the date/time with `+07:00`, so it can convert directly back to `Instant`. `OffsetTime` only keeps the time `09:30+07:00`, with no date.
4. Both round-trip paths return the original `Instant` because the known date, time, zone, and offset here are consistent, and the example is not in a DST gap/overlap.
5. `Date.from(instant)` and `legacy.toInstant()` preserve the instant in the example because it has second-level precision, fitting within `java.util.Date`'s millisecond limit.

## 8. Conversions That Cannot Be Reversed Without Adding Data

| Performed | Lost information | What is needed to restore? |
| --- | --- | --- |
| `ZonedDateTime → LocalDateTime` | Zone and offset | Needs original zone/offset; overlap may also require offset selection. |
| `OffsetDateTime → LocalDateTime` | Offset | Needs original offset to know the original `Instant`. |
| `ZonedDateTime → LocalDate` | Time, zone, offset | Needs time and zone policy; date alone cannot deduce a specific event. |
| `ZonedDateTime → LocalTime` | Date, zone, offset | Needs date and zone/offset. |
| `OffsetDateTime → OffsetTime` | Date | Needs original date. |
| `Instant → LocalDateTime` | Zone info used for representation | Needs original zone kept; applying a different zone produces a different instant from the same local time. |
| `ZonedDateTime → OffsetDateTime` | `ZoneId` name with region rules | Needs original zone if future schedules must follow location rules. |
| `Instant → java.util.Date` | Sub-millisecond fraction | Lost nanoseconds cannot be recovered. |

**Example of two `Instant`s with the same local time:** `2024-11-03T01:30` in New York can be either `2024-11-03T05:30:00Z` (offset `-04:00`) or `2024-11-03T06:30:00Z` (offset `-05:00`). If both are converted to `LocalDateTime` by dropping the offset, they become the exact same value and the original instant cannot be determined on its own.

Do not convert to a “less-informative” type and then treat it as a global timestamp storage format. For event logs, payments, and system records, **prefer `Instant`** and store `ZoneId` alongside it when local context must be preserved.

## 9. Map Requiring DST Awareness: *gap*, *overlap*, and Conversion Direction

An `Instant` always corresponds to **one** local date-time in a `ZoneId` at a given point in time. In the reverse direction, however, `LocalDateTime + ZoneId → Instant` can have:

- **One** valid offset (normal time).
- **Zero** valid offsets (gap, skipped hour).
- **Two** valid offsets (overlap, repeated hour).

Java lets you inspect this via `zone.getRules().getValidOffsets(local)`. With `local.atZone(zone)`, by default a time in a gap is pushed forward to a valid time and an overlap usually selects the earlier offset; business logic may require a different policy.

### Java 17+ Example: Converting Across a Gap/Overlap

Create the file **`ConversionDstDemo.java`**:

```java
import java.time.*;
import java.util.List;

public class ConversionDstDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");

        LocalDateTime overlap =
                LocalDateTime.of(2024, 11, 3, 1, 30);
        List<ZoneOffset> choices =
                zone.getRules().getValidOffsets(overlap);
        ZonedDateTime earlier =
                overlap.atZone(zone).withEarlierOffsetAtOverlap();
        ZonedDateTime later =
                overlap.atZone(zone).withLaterOffsetAtOverlap();

        System.out.println("Overlap offsets : " + choices);
        System.out.println("Earlier instant : " + earlier.toInstant());
        System.out.println("Later instant   : " + later.toInstant());
        System.out.println("Same local      : " +
                earlier.toLocalDateTime()
                        .equals(later.toLocalDateTime()));

        LocalDateTime gap =
                LocalDateTime.of(2024, 3, 10, 2, 30);
        System.out.println("Gap offsets     : " +
                zone.getRules().getValidOffsets(gap));
        System.out.println("Gap resolved    : " + gap.atZone(zone));

        Instant fixed = Instant.parse("2024-03-10T07:30:00Z");
        System.out.println("Instant to zone : " + fixed.atZone(zone));

        LocalDate date = LocalDate.of(2024, 3, 10);
        System.out.println("Start of day    : "
                + date.atStartOfDay(zone));
    }
}
```

```bash
javac ConversionDstDemo.java
java ConversionDstDemo
```

Verified output:

```text
Overlap offsets : [-04:00, -05:00]
Earlier instant : 2024-11-03T05:30:00Z
Later instant   : 2024-11-03T06:30:00Z
Same local      : true
Gap offsets     : []
Gap resolved    : 2024-03-10T03:30-04:00[America/New_York]
Instant to zone : 2024-03-10T03:30-04:00[America/New_York]
Start of day    : 2024-03-10T00:00-05:00[America/New_York]
```

**Implications for the conversion map:**

- `LocalDateTime → ZonedDateTime` at an **overlap** has two offset choices: earlier and later; `toInstant()` yields two instants one hour apart.
- `LocalDateTime → ZonedDateTime` in a **gap** is adjusted by `atZone` by default to the valid 03:30. If the exact time entered by the user must be preserved, validate and reject instead of using the default.
- `Instant → ZonedDateTime` is always unambiguous within a zone; `07:30Z` maps straight to `03:30-04:00`, with no ambiguous offset choice.
- `date.atStartOfDay(zone)` is used when you need the **valid start of day in a zone**. Even when that date has DST at 02:00, the start of day at 00:00 still uses `-05:00`. In other zones, an offset transition may occur near midnight, so do not assume every day starts at exactly 00:00 across all zone rules.

## 10. Changing Time Zones: Keep the Same Instant or Keep the Same Wall-Clock Time?

Two methods on `ZonedDateTime` serve different purposes:

```java
ZonedDateTime hcm =
        Instant.parse("2025-01-15T02:30:00Z")
                .atZone(ZoneId.of("Asia/Ho_Chi_Minh"));

ZonedDateTime parisSameInstant =
        hcm.withZoneSameInstant(ZoneId.of("Europe/Paris"));

ZonedDateTime parisSameLocal =
        hcm.withZoneSameLocal(ZoneId.of("Europe/Paris"));
```

- `withZoneSameInstant` **keeps the exact original `Instant`**. The displayed time in Paris changes to reflect the same point in time.
- `withZoneSameLocal` tries to keep **09:30 on the clock** and then interprets it in Paris; the `Instant` usually changes. It may encounter gaps/overlaps and zone resolution rules.
- With a known `Instant`, the direct, readable way to convert zones is `instant.atZone(otherZone)`.

When changing the time zone for an event timestamp that already occurred, you normally choose **same instant**, not **same local**. When moving a fixed-hour schedule between two locations and wanting to keep the same wall-clock time, same local may be needed, but the business intent must be stated clearly.

## 11. Bridging with Legacy Libraries: `Date`, `Calendar`, Epoch Millis

In older Java applications, you may encounter `java.util.Date`, `java.util.Calendar`, `TimeZone`, and Unix epoch numbers. Treat them as **bridges** at integration boundaries, and prefer `java.time` in new business code.

### `java.util.Date` ↔ `Instant`

```java
Instant instant = Instant.parse("2025-01-15T02:30:00Z");
java.util.Date oldDate = java.util.Date.from(instant);
Instant back = oldDate.toInstant();
```

`java.util.Date` stores an instant with **millisecond precision** and does not store a zone name. If `instant` has sub-millisecond nanoseconds, converting to `Date` loses that precision. `Date.toString()` formats using the system time zone setting, but `Date` itself does not carry a local zone in its value.

### Unix epoch milliseconds ↔ `Instant`

```java
Instant fromMillis = Instant.ofEpochMilli(1_736_908_200_000L);
long epochMillis = fromMillis.toEpochMilli();
// epochMillis = 1736908200000
```

`ofEpochMilli` takes the number of milliseconds since `1970-01-01T00:00:00Z`. Do not confuse epoch seconds with epoch milliseconds: they differ by a factor of **1,000**. `Instant.toEpochMilli()` converts to millisecond precision, discarding fractional nanoseconds; for very large values, limits/overflow may occur.

If external data uses **epoch seconds**, choose `Instant.ofEpochSecond(seconds)` and store seconds with explicit units. Do not take `System.nanoTime()` to convert into an epoch timestamp: that source is only for measuring elapsed duration within the JVM from an arbitrary origin.

### `Calendar` and `TimeZone`

`java.util.Calendar` can convert to `Instant` via `calendar.toInstant()`. `TimeZone` can yield a `ZoneId` via `timeZone.toZoneId()`. Conversely, when interfacing with legacy APIs, `GregorianCalendar.from(zonedDateTime)` creates a `GregorianCalendar` from a `ZonedDateTime`. Distinguish between absolute timestamps and converting local time fields, and be careful with lenient/historical settings of legacy APIs.

**JDBC:** `java.sql.Date`, `java.sql.Time`, and `java.sql.Timestamp` are separate JDBC types and should not be assumed to all behave as `java.util.Date` with identical semantics. Drivers and SQL column types can differ in how they handle zones/offsets; check the driver's mapping contract and schema. `LocalDate` usually fits a `DATE` column; `LocalDateTime` fits a date-time type without a zone; and global timestamps must have a clear storage/retrieval convention (e.g., UTC + matching column/driver type).

## 12. `Duration` and `Period`: Time Amounts Are Not “Instants”

A common misconception when reading the conversion map is thinking you can convert a `Duration` directly into an `Instant`. `Duration` has no starting point, whereas `Instant` is a specific point in time. You must supply a base `Instant`:

```java
Instant issuedAt = Instant.parse("2025-01-15T10:00:00Z");
Duration ttl = Duration.ofMinutes(90);
Instant expiresAt = issuedAt.plus(ttl);
// 2025-01-15T11:30:00Z
```

To calculate the length between two points in time:

```java
Duration elapsed = Duration.between(issuedAt, expiresAt);
// PT1H30M
```

`Period.ofMonths(1)`, on the other hand, carries calendar-month semantics. To get “one month later at the same time in Paris”, you must have the zone, convert to `ZonedDateTime`, add `plusMonths(1)`, and convert back to `Instant` if needed:

```java
ZoneId zone = ZoneId.of("Europe/Paris");
Instant nextMonth =
        issuedAt.atZone(zone).plusMonths(1).toInstant();
```

These snippets are illustrated inside a method needing `import java.time.*;`. A month does not have a fixed number of seconds, so do not turn `Period.ofMonths(1)` into an arbitrary 30-day `Duration`.

## 13. Choosing Types and Conversion Paths in Projects

| Business scenario | Preferred data type | Conversion path / advice |
| --- | --- | --- |
| Recording payment, login, or log timestamps | `Instant` | Store absolute instant; for display use `atZone(userZone)`. |
| Birthdays, holidays | `LocalDate` | Do not add time/zone when data is only a calendar date. |
| Daily opening hours | `LocalTime` + location `ZoneId` | Only create `ZonedDateTime` when a specific date is known. |
| One-off meeting scheduled at a location | `LocalDateTime` + `ZoneId` and DST policy | `local.atZone(zone).toInstant()` after resolving gap/overlap. |
| Recurring schedule in a city | Recurring `LocalTime`/date + `ZoneId` + DST rules | Do not replace the zone with a fixed offset. |
| API sending a timestamp with offset | `OffsetDateTime` or `Instant` | `offsetDateTime.toInstant()` to compare/store instant; keep offset if exact input display is needed. |
| API receiving a date-time string without offset | `LocalDateTime` | Require/define zone in the contract; do not silently assume UTC. |
| API processing duration | `Duration` | No calendar time needed; measure elapsed time with an appropriate source. |
| Monthly/yearly accounting date-times | `LocalDate` or `ZonedDateTime` + `Period` | Compute by calendar, do not force into fixed seconds. |
| Legacy system using `Date` | `Instant` at integration boundaries | `Date.toInstant()` / `Date.from(instant)`; note ms precision. |

### Three Questions Before Converting

1. **Is the current value already an absolute point in time?** If you have `Instant`, `OffsetDateTime`, or `ZonedDateTime`, you can preserve the instant when changing how it is displayed.
2. **Does the output need to keep date, time, offset, zone, or only a part?** Calls like `toLocalDate()`, `toLocalTime()`, and `toLocalDateTime()` are lossy extractions.
3. **If going from local time to an actual instant, where does the zone/offset come from?** It must come from business logic, input, or the data contract; do not default to the machine's zone when the semantics require the user's or location's time zone.

## 14. Common Conversion Mistakes

1. **Wrongly attaching UTC to `LocalDateTime`:** `2025-01-15T09:30` does not mean `09:30Z`. A zone/offset is needed before creating an `Instant`.
2. **Arbitrarily using `ZoneId.systemDefault()`:** A server container may run in UTC while users are in Vietnam. The chosen zone must match business requirements.
3. **Losing the offset during a DST overlap:** Two `ZonedDateTime`s at different instants can have the same `LocalDateTime`. Do not store only local date-time if you need to reconstruct the instant.
4. **Using a fixed offset for a recurring schedule in a city:** An offset cannot represent the DST rules of a `ZoneId`.
5. **Treating `Instant.atZone(zone)` as adding/subtracting hours to the instant:** It only changes the representation of the same point in time.
6. **Confusing `withZoneSameInstant` with `withZoneSameLocal`:** One preserves the instant, while the other tries to preserve the local time; do not substitute them casually.
7. **Calling `LocalDate.atTime(0,0)` and assuming it is the start-of-day instant for every zone:** You must apply `ZoneId` and account for offset transitions near midnight; use `atStartOfDay(zone)` when that is the problem.
8. **Using `OffsetTime` as a timestamp:** It has no date, so it cannot represent a one-time event.
9. **Assuming `Date` keeps nanosecond precision:** `java.util.Date` only has millisecond precision.
10. **Confusing epoch milliseconds with epoch seconds:** Using the wrong unit produces dates off by thousands of years.
11. **Turning `Period` into 30 days:** A calendar month does not have a fixed length in seconds.
12. **Forgetting immutability:** `java.time` types return new values; they do not mutate the existing variable.
13. **Parsing a string as if type conversion were complete:** `LocalDateTime.parse(...)` does not produce an `Instant` on its own; the data is still missing a zone.
14. **Ignoring parse errors or invalid data:** Malformed date strings, invalid zones, or gap times must be validated and reported appropriately.

## 15. Self-Check Exercises

**Exercise 1.** Convert `Instant.parse("2025-01-15T02:30:00Z")` to Vietnam time.

**Answer:** `instant.atZone(ZoneId.of("Asia/Ho_Chi_Minh"))` gives `2025-01-15T09:30+07:00[Asia/Ho_Chi_Minh]`. The UTC instant does not change.

**Exercise 2.** Given `LocalDate.of(2025, 1, 15)` and `LocalTime.of(9, 30)`, how do you create a `LocalDateTime`?

**Answer:** `LocalDateTime.of(date, time)` or `date.atTime(time)`. After this step, you still do not have an `Instant` until you choose a zone/offset.

**Exercise 3.** Convert `LocalDateTime.of(2025, 1, 15, 9, 30)` to `Instant` with offset `+07:00`.

**Answer:** `local.toInstant(ZoneOffset.ofHours(7))`, resulting in `2025-01-15T02:30:00Z`.

**Exercise 4.** Does converting a `ZonedDateTime` to `LocalDateTime` retain enough information to convert back?

**Answer:** No. The zone/offset is dropped; during an overlap, even the choice between earlier and later is lost.

**Exercise 5.** Why can't `OffsetTime.of(9,30,0,0,ZoneOffset.ofHours(7))` be converted directly into an `Instant` event?

**Answer:** It is missing a date. Add a date with `offsetTime.atDate(date)` to get an `OffsetDateTime`, then call `toInstant()`.

**Exercise 6.** From `java.util.Date` to `Instant`, which API is appropriate and what should you watch out for?

**Answer:** `date.toInstant()`; `Date` has millisecond precision and does not preserve sub-millisecond nanoseconds.

**Exercise 7.** How many `Instant`s can 2024-11-03 at 01:30 in New York correspond to?

**Answer:** Two, due to DST overlap: `05:30Z` or `06:30Z`, depending on whether the offset is `-04:00` or `-05:00`.

**Exercise 8.** You want to change the display from Vietnam to Paris while keeping the same event. Use `withZoneSameLocal` or `withZoneSameInstant`?

**Answer:** `withZoneSameInstant(ZoneId.of("Europe/Paris"))`, because you need to keep the original `Instant`.

## Key Takeaways

**The conversion map must start with the meaning of the data, not just API names.** `LocalDate`, `LocalTime`, and `LocalDateTime` do not determine a global instant on their own; `OffsetDateTime`, `ZonedDateTime`, and `Instant` can represent an instant, but hold different contexts. Use `atZone(zone)`, `atOffset(offset)`, and `toInstant()` to move between local time and an actual instant; use `toLocalDate()/toLocalTime()/toLocalDateTime()` when you want to extract a subset of information and **accept losing context**. Always supply a zone/offset explicitly, check DST when going from local time to an actual instant, and choose `Duration`/`Period` for time amounts according to their proper meaning.
