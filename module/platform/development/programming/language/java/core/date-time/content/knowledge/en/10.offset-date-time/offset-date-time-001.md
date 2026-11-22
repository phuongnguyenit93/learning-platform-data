# OffsetDateTime: Representing Date and Time with a UTC Offset in Java

## 1. What Problem Does OffsetDateTime Solve?

A timestamp label such as **2024-07-15 09:30** does not yet identify an absolute point in time: it could be 09:30 in Vietnam, Paris, New York, or somewhere else. `java.time.OffsetDateTime` adds a **UTC offset** so that the value can map to a specific instant.

For example:

- `2024-07-15T09:30+02:00` means the local clock is two hours ahead of UTC; the corresponding instant is `2024-07-15T07:30:00Z`.
- `2024-07-15T09:30Z` uses a zero UTC offset; the corresponding instant is `2024-07-15T09:30:00Z`.
- Two values with the **same displayed time but different offsets** are usually two different instants.
- Two values with **different displayed times but the same instant** may simply be two ways of representing the same point in time.

In Java 17+, `OffsetDateTime` is an immutable value class, thread-safe when used as a value, and has nanosecond-level representation precision. It does not contain a geographical region ID or the full history of DST rules.

Lesson goals: create/read `OffsetDateTime`, distinguish it from `LocalDateTime`, `Instant`, and `ZonedDateTime`, understand offset changes, calculations/conversions, comparisons, parsing/formatting, and common design mistakes.

## 2. Three Key Components

An `OffsetDateTime` contains:

1. **The local date-time part** (`LocalDateTime`): year, month, day, hour, minute, second, nanosecond.
2. **The UTC offset** (`ZoneOffset`): from UTC to the local clock, for example `+07:00`.
3. **The relationship to an instant**: once the date-time and offset are known, the absolute point on the timeline can be calculated.

You can visualize it as:

```text
OffsetDateTime = LocalDateTime + ZoneOffset

2024-07-15T09:30+02:00
      |           |
      |           +-- two hours ahead of UTC
      +-------------- date and time displayed at that offset

UTC instant = local date-time - offset
            = 2024-07-15T07:30:00Z
```

`ZoneOffset` defines the sign according to the ISO-8601 standard: `+02:00` means the time at that offset is **two hours ahead of UTC**, so converting to UTC requires subtracting two hours; `-05:00` means the local time is **five hours behind UTC**.

### Comparison with Related java.time Types

| Type | Has displayed date/time? | Has offset? | Has regional ZoneId? | Identifies an instant? |
| --- | --- | --- | --- | --- |
| `LocalDateTime` | Yes | No | No | No |
| `OffsetDateTime` | Yes | Yes | No | Yes |
| `ZonedDateTime` | Yes | Yes | Yes | Yes |
| `Instant` | Point on the UTC timeline | Displayed in UTC | No | Yes |
| `ZoneOffset` | No | Itself is the offset | No | No, if date-time is missing |

**Choose `OffsetDateTime`** when you need to exchange or store a specific date-time **along with the recorded offset**. Choose `ZonedDateTime` when you need to preserve **region rules** such as `Europe/Paris` for future appointments. Choose `Instant` when the focus is on an absolute timestamp without needing to carry a local representation.

## 3. Creating OffsetDateTime with Common APIs

### 3.1. Combining Components and ZoneOffset

```java
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 30);
ZoneOffset offset = ZoneOffset.ofHours(2);

OffsetDateTime value = OffsetDateTime.of(local, offset);
// 2024-07-15T09:30+02:00
```

This is an **illustrative snippet inside a method**, not a standalone Java program. `OffsetDateTime.of(...)` has an overload that accepts year, month, day, hour, minute, second, nanosecond, and offset fields:

```java
OffsetDateTime precise = OffsetDateTime.of(
        2024, 7, 15, 9, 30, 45, 123_456_789,
        ZoneOffset.of("+02:00"));
// 2024-07-15T09:30:45.123456789+02:00
```

This is an illustrative snippet with `OffsetDateTime` and `ZoneOffset` already imported. The value holds the nanosecond-of-second part from 0 to 999,999,999.

### 3.2. Creating from LocalDateTime

`LocalDateTime.atOffset(ZoneOffset)` is convenient when you already have a local time **and a clearly determined offset**:

```java
LocalDateTime local = LocalDateTime.of(2024, 7, 15, 9, 30);
OffsetDateTime result = local.atOffset(ZoneOffset.ofHours(2));
```

This is an illustrative snippet requiring the `LocalDateTime` and `ZoneOffset` types to be imported. Attaching an offset to a local time is a **decision about the instant**: if the offset is wrong, the resulting instant is also wrong.

Do not infer an offset from a `LocalDateTime` on your own. If you only know `Europe/Paris`, you must obtain the `ZoneId` rules at the appropriate date-time and handle DST gaps/overlaps; use the zone API instead of hardcoding `+01:00` or `+02:00`.

### 3.3. Creating from an Instant and Offset/Zone

If you have an absolute instant, you can represent it with an offset or a zone:

```java
Instant instant = Instant.parse("2024-07-15T07:30:00Z");
OffsetDateTime inVietnam =
        OffsetDateTime.ofInstant(instant, ZoneOffset.ofHours(7));
OffsetDateTime inParis =
        OffsetDateTime.ofInstant(instant, ZoneId.of("Europe/Paris"));
```

This is an illustrative snippet requiring `import java.time.Instant;`, `OffsetDateTime`, `ZoneOffset`, and `ZoneId`. Results:

- `inVietnam` = `2024-07-15T14:30+07:00`.
- `inParis` = `2024-07-15T09:30+02:00` according to Paris rules in July 2024.

`ofInstant(instant, zone)` uses the **effective offset of the zone at that instant** and returns an `OffsetDateTime`. The result **does not retain the `Europe/Paris` ID**. If you need to carry the zone ID, use `instant.atZone(zone)` to get a `ZonedDateTime`.

### 3.4. Current Time

```java
OffsetDateTime nowAtUtc = OffsetDateTime.now(ZoneOffset.UTC);
OffsetDateTime nowInZone = OffsetDateTime.now(
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

This is an illustrative snippet. The result depends on the actual time and environment, so there is no fixed stdout. The no-argument `now()` relies on the system default time zone, which can differ across laptops, containers, and servers.

In testable code, use a configured or injected `Clock`, for example `OffsetDateTime.now(clock)`. If business logic requires the user's offset, determine their `ZoneId` and pass it explicitly when creating the time.

## 4. ZoneOffset: Sign, Limits, and Fixed Offsets

`ZoneOffset` is a type of `ZoneId` that represents a **fixed UTC offset**:

```java
ZoneOffset plusSeven = ZoneOffset.of("+07:00");
ZoneOffset same = ZoneOffset.ofHours(7);
ZoneOffset withMinutes = ZoneOffset.ofHoursMinutes(5, 30);
ZoneOffset utc = ZoneOffset.UTC;
```

This is an illustrative snippet with `import java.time.ZoneOffset;`. Both `plusSeven` and `same` represent an offset of +7 hours, while `withMinutes` is +05:30.

Java allows offsets in the range **-18:00 to +18:00**, with valid hour/minute/second fields and consistent signs. Offsets like `+19:00` or `+07:60` are rejected with a `DateTimeException`. The range of `ZoneOffset` objects is wider than most offsets used in practice; not every representable offset is used by a geographical region.

Distinguish carefully:

- `ZoneOffset.of("+07:00")` has a fixed offset and is unaware of DST.
- `ZoneId.of("Asia/Ho_Chi_Minh")` is a **region** ID containing historical time rule data and the ability to reflect future policy changes.
- Two values may share the same offset at one instant, but they are not interchangeable representatives for every date.

## 5. Reading Components and Converting to Instant

From an `OffsetDateTime`, extract its components:

```java
OffsetDateTime event = OffsetDateTime.parse(
        "2024-07-15T09:30:45.123456789+02:00");

LocalDateTime local = event.toLocalDateTime();
LocalDate date = event.toLocalDate();
LocalTime time = event.toLocalTime();
ZoneOffset offset = event.getOffset();
Instant instant = event.toInstant();
long epochSecond = event.toEpochSecond();
```

This is an illustrative snippet requiring `OffsetDateTime`, `LocalDateTime`, `LocalDate`, `LocalTime`, `ZoneOffset`, and `Instant` to be imported. Values:

- `local` = `2024-07-15T09:30:45.123456789`.
- `offset` = `+02:00`.
- `instant` = `2024-07-15T07:30:45.123456789Z`.
- `epochSecond` counts **whole seconds** from the Unix epoch, not milliseconds.

**Important:** `toLocalDateTime()` discards the offset; if you store only that, you cannot reliably restore the original instant on your own. `toInstant()` preserves the absolute point in time but drops the chosen local/offset representation; to reconstruct the exact same representation, you must also store the offset.

## 6. Changing the Offset: Keep Instant or Keep Local Time?

Two methods that most commonly cause major discrepancies when working with `OffsetDateTime`:

- `withOffsetSameInstant(newOffset)`: **keeps the same instant** (absolute point in time), changing the displayed time to match the new offset.
- `withOffsetSameLocal(newOffset)`: **keeps the same local date-time fields**, changing the offset and therefore **changing the instant**.

These represent very different business choices.

Suppose the original time is `2024-07-15T09:30+02:00`:

| Usage | Result | Instant |
| --- | --- | --- |
| Original | `09:30+02:00` | `07:30Z` |
| `withOffsetSameInstant(UTC)` | `07:30Z` | Still `07:30Z` |
| `withOffsetSameLocal(UTC)` | `09:30Z` | Changed to `09:30Z` |
| `withOffsetSameInstant(+07:00)` | `14:30+07:00` | Still `07:30Z` |

Save the program **`OffsetConversionDemo.java`**:

```java
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

public class OffsetConversionDemo {
    public static void main(String[] args) {
        OffsetDateTime original = OffsetDateTime.of(
                2024, 7, 15, 9, 30, 0, 0,
                ZoneOffset.ofHours(2));

        OffsetDateTime sameInstant =
                original.withOffsetSameInstant(ZoneOffset.UTC);
        OffsetDateTime sameLocal =
                original.withOffsetSameLocal(ZoneOffset.UTC);
        OffsetDateTime vietnam =
                original.withOffsetSameInstant(ZoneOffset.ofHours(7));

        System.out.println("original = " + original);
        System.out.println("sameInstant = " + sameInstant);
        System.out.println("sameLocal = " + sameLocal);
        System.out.println("vietnam = " + vietnam);
        System.out.println("originalInstant = " + original.toInstant());
        System.out.println("sameInstantUtc = " + sameInstant.toInstant());
        System.out.println("sameLocalUtc = " + sameLocal.toInstant());
    }
}
```

Compile and run with Java 17+:

```bash
javac OffsetConversionDemo.java
java OffsetConversionDemo
```

Deterministic output:

```text
original = 2024-07-15T09:30+02:00
sameInstant = 2024-07-15T07:30Z
sameLocal = 2024-07-15T09:30Z
vietnam = 2024-07-15T14:30+07:00
originalInstant = 2024-07-15T07:30:00Z
sameInstantUtc = 2024-07-15T07:30:00Z
sameLocalUtc = 2024-07-15T09:30:00Z
```

Explanation: if the user wants to view **the same event** in another place, keep the instant. If the business logic intentionally wants to reassign a fixed local time to a different offset, then `withOffsetSameLocal()` is appropriate.

Both methods return a **new** value and do not modify `original`.

## 7. Converting from OffsetDateTime to a Zone with DST Rules

`OffsetDateTime` has no regional `ZoneId`. When you need to display the same instant in someone else's time zone:

```java
OffsetDateTime event = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");

ZonedDateTime inVietnam = event.atZoneSameInstant(
        ZoneId.of("Asia/Ho_Chi_Minh"));
// 2024-07-15T14:30+07:00[Asia/Ho_Chi_Minh]
```

This is an illustrative snippet importing `OffsetDateTime`, `ZonedDateTime`, and `ZoneId`. The word **SameInstant** explicitly indicates keeping the UTC instant unchanged.

`event.toZonedDateTime()` creates a `ZonedDateTime` based on the existing offset (using the offset as a zone), but **does not automatically restore the original region ID**. For example, `09:30+02:00` can correspond to many different regions; from the offset alone, you cannot conclude that it necessarily belongs to Paris or any specific city.

When a requirement says “a recurring meeting at 9 AM every day in Paris time”, storing only `+02:00` is not enough: in winter, Paris's offset can be `+01:00`. Store `ZoneId.of("Europe/Paris")` along with the scheduling rule and handle DST. `OffsetDateTime` is better suited for **stamping a one-time offset at creation/exchange time**, or when the data contract is genuinely local time + fixed offset.

## 8. Parsing Strings with parse()

`OffsetDateTime.parse(text)` by default reads the ISO-8601 format with an offset:

```java
OffsetDateTime a = OffsetDateTime.parse(
        "2024-07-15T09:30:00+02:00");

OffsetDateTime b = OffsetDateTime.parse(
        "2024-07-15T07:30:00Z");
```

This is an illustrative snippet requiring `import java.time.OffsetDateTime;`. Both represent the same instant but with two different local representations.

A string containing only date and time like `2024-07-15T09:30` is **not sufficient** to parse directly into an `OffsetDateTime` using the default ISO formatter because the offset is missing. If you need to accept such data, the API must have a separate offset or `ZoneId` field, and construct the value after determining the rules.

Invalid syntax or missing required parts will throw a `DateTimeParseException` (a subclass of `DateTimeException`).

### Parsing with a Custom Format

When the input contract does not use the letter `T`, you can define a `DateTimeFormatter`:

```java
DateTimeFormatter formatter = DateTimeFormatter.ofPattern(
        "uuuu-MM-dd HH:mm XXX");

OffsetDateTime value = OffsetDateTime.parse(
        "2024-07-15 09:30 +02:00", formatter);
```

This is an illustrative snippet inside a method, requiring `java.time.format.DateTimeFormatter` and `OffsetDateTime` to be imported. With the `XXX` pattern symbol, the formatter represents the offset in ISO form such as `+02:00` or `Z` for UTC.

Do not let the formatter “guess” a time zone when the input has no offset. If the API needs to accept a region identifier like `Europe/Paris`, use a formatter/schema with a zone field and convert to `ZonedDateTime` or `Instant` as intended.

## 9. Formatting for Display and Serialization

`OffsetDateTime.toString()` produces ISO text matching the precision of the value:

```java
OffsetDateTime time = OffsetDateTime.of(
        2024, 7, 15, 9, 30, 0, 0,
        ZoneOffset.ofHours(2));

System.out.println(time);
// 2024-07-15T09:30+02:00
```

This is an illustrative snippet inside a method. Because seconds and nanoseconds are both 0, `toString()` may omit the `:00` seconds part, but **the offset value is always preserved**.

When using `DateTimeFormatter.ISO_OFFSET_DATE_TIME`, you get the ISO form with offset. If you want a custom format for user display:

```java
DateTimeFormatter display = DateTimeFormatter.ofPattern(
        "dd/MM/uuuu HH:mm XXX");

String rendered = time.format(display);
// "15/07/2024 09:30 +02:00"
```

This is an illustrative snippet requiring `DateTimeFormatter` to be imported. Formatting only turns the value into a string for display; it **does not change the instant or offset** in the original object.

When outputting JSON or sending over an API, state the contract clearly—for example, that the `occurredAt` field contains an ISO offset date-time string. Avoid a string like `2024-07-15 09:30` without an offset if the receiver needs a unique point in time. If a framework serializes `OffsetDateTime` automatically, verify its actual configuration and test round-trip behavior (serialize → deserialize).

## 10. Comparison: equals(), isEqual(), isBefore(), compareTo()

A crucial distinction is **full value equality** versus **same point on the timeline**.

Given:

```java
OffsetDateTime a = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");
OffsetDateTime b = OffsetDateTime.parse(
        "2024-07-15T07:30Z");
```

The two values have the same instant. However:

- `a.equals(b)` returns `false`: `equals()` checks both **local date-time and offset**.
- `a.isEqual(b)` returns `true`: `isEqual()` compares the **instant**.
- `a.isBefore(b)` and `a.isAfter(b)` both return `false`: same instant.
- `a.compareTo(b)` can be **non-zero** when the offset/local time differs even for the same instant, because natural ordering compares by instant first, then breaks ties using local date-time to remain consistent with `equals()`.

Save **`OffsetComparisonDemo.java`**:

```java
import java.time.OffsetDateTime;

public class OffsetComparisonDemo {
    public static void main(String[] args) {
        OffsetDateTime a = OffsetDateTime.parse(
                "2024-07-15T09:30+02:00");
        OffsetDateTime b = OffsetDateTime.parse(
                "2024-07-15T07:30Z");

        System.out.println("equals = " + a.equals(b));
        System.out.println("isEqual = " + a.isEqual(b));
        System.out.println("isBefore = " + a.isBefore(b));
        System.out.println("compareTo = " + a.compareTo(b));
        System.out.println("sameInstant = "
                + a.toInstant().equals(b.toInstant()));
    }
}
```

Run:

```bash
javac OffsetComparisonDemo.java
java OffsetComparisonDemo
```

Deterministic output:

```text
equals = false
isEqual = true
isBefore = false
compareTo = 1
sameInstant = true
```

**Implications for collections:** Two `OffsetDateTime` instances with the same instant but different offsets can be **two distinct keys** in a `HashMap` or two distinct elements in a `TreeSet` using natural ordering. If business identity is the **instant**, normalize to `Instant` as the key or use an instant-based comparator, and clearly define how to handle two different representations of the same instant.

## 11. Adding, Subtracting, and Replacing Fields

`OffsetDateTime` has methods similar to `LocalDateTime`:

```java
OffsetDateTime start = OffsetDateTime.parse(
        "2024-01-31T10:15+07:00");

OffsetDateTime afterOneDay = start.plusDays(1);
// 2024-02-01T10:15+07:00

OffsetDateTime afterOneMonth = start.plusMonths(1);
// 2024-02-29T10:15+07:00

OffsetDateTime newHour = start.withHour(9);
// 2024-01-31T09:15+07:00

OffsetDateTime priorMinutes = start.minusMinutes(30);
// 2024-01-31T09:45+07:00
```

This is an illustrative snippet inside a method with `OffsetDateTime` already imported. These methods do not mutate the original value and preserve the offset if the operation does not require changing it.

**Semantic distinction:** Because an `OffsetDateTime`'s offset is **fixed within the value**, adding a day like `plusDays(1)` does not automatically update for a region's DST rules. If you need event scheduling according to `ZoneId` rules, use `ZonedDateTime`.

Calendar-month addition/subtraction handles 28/29/30/31-day months according to `java.time` rules. `plusMonths(1)` from 2024-01-31 leads to 2024-02-29; it is not equivalent to adding 30 days.

## 12. Normalizing to UTC While Preserving the Instant

When you need to represent the same instant in UTC:

```java
OffsetDateTime value = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");
OffsetDateTime utcView =
        value.withOffsetSameInstant(ZoneOffset.UTC);

System.out.println(utcView);   // 2024-07-15T07:30Z
System.out.println(value.toInstant()); // 2024-07-15T07:30:00Z
```

This is an illustrative snippet requiring `OffsetDateTime` and `ZoneOffset`. The two values have the **same instant**, but `OffsetDateTime` still represents a date-time with a UTC offset, whereas `Instant` is an absolute point in time.

In databases or distributed systems:

- If you only need chronological ordering, comparisons, or event timestamps, **`Instant`** is usually simpler.
- If the API contract requires both the date-time and the specific offset as recorded, **`OffsetDateTime`** carries that semantics.
- If a recurring schedule follows local time in a specific place, an additional **`ZoneId`** is needed—typically using `ZonedDateTime` or storing local date/time + region ID.

Do not treat normalizing the offset to UTC as a “no-op” transformation at the `equals()` level. It preserves the **instant**, but the local part and offset usually change.

## 13. A Complete Example: Creating, Parsing, Converting, and Reading an Instant

Save the file **`OffsetDateTimeOverviewDemo.java`**:

```java
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.ZonedDateTime;

public class OffsetDateTimeOverviewDemo {
    public static void main(String[] args) {
        OffsetDateTime meeting = OffsetDateTime.of(
                2024, 7, 15, 9, 30, 0, 0,
                ZoneOffset.ofHours(2));

        Instant instant = meeting.toInstant();
        OffsetDateTime inVietnam = meeting.withOffsetSameInstant(
                ZoneOffset.ofHours(7));
        ZonedDateTime inVietnamZone = meeting.atZoneSameInstant(
                ZoneId.of("Asia/Ho_Chi_Minh"));

        System.out.println("meeting = " + meeting);
        System.out.println("instant = " + instant);
        System.out.println("vietnamOffset = " + inVietnam);
        System.out.println("vietnamZone = " + inVietnamZone);
        System.out.println("local = " + meeting.toLocalDateTime());
        System.out.println("offset = " + meeting.getOffset());
        System.out.println("epochSecond = " + meeting.toEpochSecond());
    }
}
```

Run:

```bash
javac OffsetDateTimeOverviewDemo.java
java OffsetDateTimeOverviewDemo
```

Deterministic output under standard time zone rules:

```text
meeting = 2024-07-15T09:30+02:00
instant = 2024-07-15T07:30:00Z
vietnamOffset = 2024-07-15T14:30+07:00
vietnamZone = 2024-07-15T14:30+07:00[Asia/Ho_Chi_Minh]
local = 2024-07-15T09:30
offset = +02:00
epochSecond = 1721028600
```

The `epochSecond` result is the number of seconds since `1970-01-01T00:00:00Z`, not nanoseconds or milliseconds. If you need sub-second precision, keep `Instant` or use APIs that support nanoseconds.

## 14. Data Sent Across Systems: Losing the Offset vs. Preserving the Instant

Suppose service A sends the string `2024-07-15T09:30+02:00` to service B:

- If B parses it into `OffsetDateTime`, B has **both the local time and the offset**.
- If B calls `toInstant()`, B preserves the **absolute point in time**, but loses which +02:00 offset the sender chose.
- If B calls `toLocalDateTime()` and stores only that, B loses the **offset information** and no longer has a unique way to recover the instant.

A common mistake is receiving an `OffsetDateTime` and then doing:

```java
OffsetDateTime received = OffsetDateTime.parse(
        "2024-07-15T09:30+02:00");

LocalDateTime lostOffset = received.toLocalDateTime();

// Wrong if you assume the server's time zone is the original time zone:
OffsetDateTime reinterpreted = lostOffset.atOffset(ZoneOffset.UTC);
```

This is an illustrative snippet requiring `OffsetDateTime`, `LocalDateTime`, and `ZoneOffset` to be imported. `reinterpreted` is `2024-07-15T09:30Z`, which is **instant 09:30Z**, shifted by two hours from the original instant `07:30Z`.

Therefore, when designing DTOs, databases, and mappings, decide whether you need to preserve **instant**, **offset**, **local time**, and/or **ZoneId** before choosing column/data types. Do not infer information that was not stored.

## 15. Common Pitfalls and Testing

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Thinking `+07:00` is the Vietnam region ID | Loses history and region rules | Use a regional `ZoneId` when location-based policies are needed |
| Calling `withOffsetSameLocal()` to display the same event elsewhere | Changes the instant | Use `withOffsetSameInstant()` |
| Using `equals()` to check if two representations share the same instant | Result can be false | Use `isEqual()` or compare `toInstant()` |
| Dropping the offset via `toLocalDateTime()` and assuming UTC | Wrong point in time | Keep the offset or convert directly to `Instant` |
| Parsing a string without an offset into `OffsetDateTime` | `DateTimeParseException` | Include the offset/zone in the contract |
| Assuming the current offset is always valid for meetings in other months | Wrong in DST regions | Store `ZoneId` and apply rules by date |
| Using `now()` in tests with fixed expected output | Not reproducible | Use `Clock.fixed(...)` or explicit `of(...)` timestamps |
| Treating `toEpochSecond()` as milliseconds | Off by a factor of 1,000 | Specify units clearly or convert from `Instant` per contract |
| Assuming storing OffsetDateTime in any DB always preserves the offset | May be normalized or lose the offset | Test round-trip behavior for the specific driver, column type, and config |

Cases to test:

1. Two different offset representations for the same instant.
2. Same local date-time with different offsets.
3. Midnight, date rollover when changing offsets, and timestamps before the Unix epoch.
4. ISO parsing/formatting with `Z`, `+07:00`, and nanoseconds.
5. Out-of-range offsets (e.g., `+19:00`).
6. Conversions involving `Europe/Paris` in winter/summer and around DST gaps/overlaps.
7. Database/JSON mapping preserving or dropping the offset according to the contract.

## 16. Self-Check Exercises

**Question 1.** What instant is `2024-07-15T09:30+02:00` equivalent to?

**Answer:** `2024-07-15T07:30:00Z`, because the +02:00 offset is two hours ahead of UTC.

**Question 2.** What does calling `withOffsetSameInstant(ZoneOffset.ofHours(7))` on the value in Question 1 return?

**Answer:** `2024-07-15T14:30+07:00`, keeping the instant `07:30Z` unchanged.

**Question 3.** If you call `withOffsetSameLocal(ZoneOffset.UTC)` on the value in Question 1, does the instant change?

**Answer:** Yes. It keeps `09:30` and changes the offset to `Z`, so the instant shifts from `07:30Z` to `09:30Z`.

**Question 4.** Do two `OffsetDateTime` values with the same `toInstant()` but different offsets have `equals() == true`?

**Answer:** Not necessarily; `equals()` also compares local date-time and offset. `isEqual()` checks for the same instant.

**Question 5.** Is `OffsetDateTime` sufficient to schedule a recurring event at “09:00 every day in Paris”?

**Answer:** Not sufficient. You need the regional `ZoneId` `Europe/Paris` to apply DST rules as dates change.

**Question 6.** Can `2024-07-15T09:30` be parsed directly using the default `OffsetDateTime.parse(...)`?

**Answer:** No; the string is missing a UTC offset. You need an offset or a clearly defined policy to obtain the zone/offset from another source.

**Key takeaway:** `OffsetDateTime` holds **local date-time + UTC offset**, which determines an instant. When you want to change the display of the **same event**, use `withOffsetSameInstant()`. When you intentionally want to reattach a local time to a different offset, use `withOffsetSameLocal()`. An offset is a fixed number; region-based scheduling and DST require a time zone ID via `ZoneId`.