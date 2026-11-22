# OffsetTime Represents Time with an Offset but Without a Date

In Java, `OffsetTime` is a data type in the `java.time` package that represents a **wall-clock time combined with a fixed offset from UTC (UTC offset)**, without **containing a date, year, month, or geographic time zone name**. For example:

~~~text
09:15:30.123456789+07:00
└── time of day ─┘└UTC offset
~~~

This string states that the clock displays **09 hours, 15 minutes, 30 seconds, plus a fractional part of 123456789 nanoseconds, at offset UTC+07:00**. It does not state **which date** that time occurs on, nor does it state whether it is the time specifically for `Asia/Ho_Chi_Minh` or another locality.

The key takeaway: `OffsetTime` holds *time + offset* but **does not uniquely identify an `Instant`** (an absolute point in time) because it lacks a date. When you need to place the value on a timeline, attach a `LocalDate`; when you need DST rules or historical offset changes, use `ZoneId` with appropriate types such as `ZonedDateTime`.

## 1. Comparing OffsetTime with Related Time Types

| Java Type | Date | Time | UTC Offset | Geographic ZoneId | Use When |
| --- | :---: | :---: | :---: | :---: | --- |
| `LocalTime` | No | Yes | No | No | Only a wall-clock time |
| **`OffsetTime`** | **No** | **Yes** | **Yes** | **No** | Time of day with a specific offset |
| `LocalDateTime` | Yes | Yes | No | No | Local date and time |
| `OffsetDateTime` | Yes | Yes | Yes | No | Date and time with offset, sufficient to identify an instant |
| `ZonedDateTime` | Yes | Yes | Yes | Yes | Date and time in a region with DST/historical rules |
| `Instant` | Absolute point in time | — | On the UTC timeline | No | Timestamp of a determined event |

Important difference between the two values:

~~~text
09:15:30          ← LocalTime: time only, no offset
09:15:30+07:00    ← OffsetTime: time + UTC offset, no date
~~~

In the second case, the `+07:00` offset provides **the relationship between local time and UTC**, but it is not enough to determine the absolute date of the event. For instance, both 2025-04-09 and 2025-04-10 can have the time `09:15+07:00`, corresponding to **two different instants** 24 hours apart.

`OffsetTime` is also **not equivalent** to `ZonedDateTime`: the `+07:00` offset has no historical rules, daylight saving time (DST), or future policies of a country.

## 2. Data Structure: LocalTime + ZoneOffset

Conceptually, an `OffsetTime` consists of two parts:

- `LocalTime`: hour, minute, second, and nanosecond within the second (maximum resolution of 1 ns).
- `ZoneOffset`: offset from UTC, such as `Z` (equal to `+00:00`), `+07:00`, or `-05:00`.

Java provides direct getters:

~~~java
OffsetTime value =
        OffsetTime.parse("09:15:30.123456789+07:00");

LocalTime time = value.toLocalTime();
ZoneOffset offset = value.getOffset();

int hour = value.getHour();     // 9
int minute = value.getMinute(); // 15
int second = value.getSecond(); // 30
int nano = value.getNano();     // 123456789
int secondsEastOfUtc = offset.getTotalSeconds(); // 25200
~~~

`getNano()` is the **nanosecond-of-second fraction**, not the total nanoseconds of the day. With `+07:00`, `getTotalSeconds()` returns `7 × 3600 = 25200`; with negative offsets, the result is negative.

`OffsetTime` values are **immutable** and can be safely shared across threads. Methods like `plusHours`, `withHour`, `withOffsetSameInstant`, and `withOffsetSameLocal` all return a new object without modifying the original one.

`ZoneOffset` is a **fixed offset**, not a `ZoneId` of a region with historical rules. Java allows offsets in hours, minutes, and in some APIs even seconds, with a maximum valid range of ±18:00. Do not assume every offset in the world is a whole number of hours.

## 3. Creating OffsetTime from Components

There are several ways to create the same time with an offset:

~~~java
import java.time.LocalTime;
import java.time.OffsetTime;
import java.time.ZoneOffset;

ZoneOffset offset = ZoneOffset.ofHours(7);
LocalTime localTime = LocalTime.of(9, 15, 30, 123_456_789);

OffsetTime a = OffsetTime.of(localTime, offset);
OffsetTime b = OffsetTime.of(
        9, 15, 30, 123_456_789, offset);
OffsetTime c =
        OffsetTime.parse("09:15:30.123456789+07:00");

// a.equals(b) && b.equals(c) is true.
~~~

The `of` overloads validate the time and offset. For example, hour `24` or minute `60` will be rejected with a `DateTimeException`. If you only pass `LocalTime.of(9,15)`, the second and nanosecond default to `0`.

When using `OffsetTime.now()`, Java gets the current instant via the system clock and the JVM's default time zone, then derives the time and offset **at that moment**. When clarity is needed, use `OffsetTime.now(zone)` or `OffsetTime.now(clock)`. Once created, the object only retains `LocalTime` and `ZoneOffset`, **not the `ZoneId` used for the calculation**.

Deterministic testing example:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2025-04-09T02:15:30Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));

OffsetTime fixedValue = OffsetTime.now(fixedClock);
// 09:15:30+07:00
~~~

This snippet requires importing `java.time.*`. Using `Clock.fixed(...)` helps avoid flaky unit tests caused by the real clock or the runner machine's timezone configuration.

## 4. Parsing OffsetTime from ISO-8601 Strings

`OffsetTime.parse(text)` uses the ISO representation with **time and offset**. For example:

~~~java
OffsetTime a = OffsetTime.parse("09:15+07:00");
OffsetTime b = OffsetTime.parse("09:15:30+07:00");
OffsetTime c = OffsetTime.parse("09:15:30.123456789+07:00");
OffsetTime d = OffsetTime.parse("09:15:30Z");
~~~

Where:

- `09:15` is the hour and minute.
- `:30` is the second (if omitted, it is interpreted as 0).
- `.123456789` is the fractional second with nanosecond resolution.
- `+07:00` means the clock is seven hours ahead of UTC.
- `Z` means a UTC offset of 0, equivalent to `+00:00`.

For example:

~~~java
OffsetTime z = OffsetTime.parse("09:15:30Z");
OffsetTime zero = OffsetTime.parse("09:15:30+00:00");
// z.equals(zero) == true
~~~

The value `2025-04-09T09:15:30+07:00` **has a date**, so it is suitable for `OffsetDateTime.parse(...)`, not the default `OffsetTime.parse(...)`. Conversely, `09:15:30` lacks an offset, so parse it with `LocalTime.parse(...)` or require an offset to be provided; do not silently default to UTC unless the data contract specifies it.

Malformed input, invalid hours, or out-of-range offsets can throw `DateTimeParseException`; applications should return a message indicating which field is invalid rather than catching all exceptions and silently substituting another offset.

## 5. Complete Java 17+ Program

Save the following content to `OffsetTimeLessonDemo.java`:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.time.OffsetTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Locale;

public class OffsetTimeLessonDemo {
    public static void main(String[] args) {
        OffsetTime original = OffsetTime.parse(
                "09:15:30.123456789+07:00");

        OffsetTime utc = original.withOffsetSameInstant(
                ZoneOffset.UTC);
        OffsetTime unchangedLocal = original.withOffsetSameLocal(
                ZoneOffset.UTC);
        OffsetDateTime atDate = original.atDate(
                LocalDate.of(2025, 4, 9));

        System.out.println("original=" + original);
        System.out.println("time=" + original.toLocalTime());
        System.out.println("offset=" + original.getOffset());
        System.out.println("offsetSeconds="
                + original.getOffset().getTotalSeconds());
        System.out.println("hour=" + original.getHour()
                + ",minute=" + original.getMinute()
                + ",second=" + original.getSecond()
                + ",nano=" + original.getNano());

        System.out.println("utcSameInstant=" + utc);
        System.out.println("utcSameLocal=" + unchangedLocal);
        System.out.println("dateAttached=" + atDate);
        System.out.println("instant=" + atDate.toInstant());

        System.out.println("iso="
                + DateTimeFormatter.ISO_OFFSET_TIME
                        .format(original));
        System.out.println("shortFormat=" + original.format(
                DateTimeFormatter.ofPattern(
                        "HH:mm:ss.SSSXXX", Locale.ROOT)));

        System.out.println("sameInstantOfDay="
                + original.isEqual(utc));
        System.out.println("equalObjects="
                + original.equals(utc));
        System.out.println("compareTo="
                + original.compareTo(utc));

        System.out.println("crossMidnight="
                + OffsetTime.parse("00:30+02:00")
                        .withOffsetSameInstant(ZoneOffset.UTC));
        System.out.println("plusHours="
                + OffsetTime.parse("23:30+07:00").plusHours(2));

        System.out.println("parsedZ="
                + OffsetTime.parse("09:15:30Z"));
        System.out.println("parsedZeroOffset="
                + OffsetTime.parse("09:15:30+00:00"));

        Clock fixedClock = Clock.fixed(
                Instant.parse("2025-04-09T02:15:30Z"),
                ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("fixedNow="
                + OffsetTime.now(fixedClock));
    }
}
~~~

Compile and run:

~~~bash
javac OffsetTimeLessonDemo.java
java OffsetTimeLessonDemo
~~~

Verified output with Java:

~~~text
original=09:15:30.123456789+07:00
time=09:15:30.123456789
offset=+07:00
offsetSeconds=25200
hour=9,minute=15,second=30,nano=123456789
utcSameInstant=02:15:30.123456789Z
utcSameLocal=09:15:30.123456789Z
dateAttached=2025-04-09T09:15:30.123456789+07:00
instant=2025-04-09T02:15:30.123456789Z
iso=09:15:30.123456789+07:00
shortFormat=09:15:30.123+07:00
sameInstantOfDay=true
equalObjects=false
compareTo=1
crossMidnight=22:30Z
plusHours=01:30+07:00
parsedZ=09:15:30Z
parsedZeroOffset=09:15:30Z
fixedNow=09:15:30+07:00
~~~

**Explanation of key lines:**

- `utcSameInstant` changes the offset to UTC and **shifts the time accordingly**: 09:15 at UTC+7 becomes 02:15 UTC.
- `utcSameLocal` only replaces the offset, **keeping the time 09:15**. These two values will represent different instants when attached to the same date.
- `dateAttached` now has **date + time + offset**, so `toInstant()` can be called.
- `sameInstantOfDay=true` together with `equalObjects=false` illustrates the difference between comparing offset-normalized times and comparing both components in full.
- `compareTo=1` is a valid result: when comparing by natural ordering, `OffsetTime` compares the normalized reference time and uses the local time as a tie-breaker if the normalized parts are equal. Do not replace `isEqual` with `compareTo(...) == 0` when you only want to check whether two times are equivalent with respect to offset.

## 6. Two Ways to Change Offset: SameInstant and SameLocal

This is the most important distinction when using `OffsetTime`.

### withOffsetSameInstant(newOffset)

~~~java
OffsetTime original = OffsetTime.parse("09:15+07:00");
OffsetTime converted =
        original.withOffsetSameInstant(ZoneOffset.UTC);
// 02:15Z
~~~

The idea is to keep the **same position in UTC time within an implicit reference day**, so the local time must be adjusted by the offset difference. Intuitive formula:

~~~text
reference UTC time = local time − offset
09:15 − 07:00 = 02:15
~~~

The API name uses `SameInstant`, but because `OffsetTime` **has no date**, you still cannot obtain a unique `Instant` from the resulting object. Strictly speaking, the conversion preserves the offset-adjusted correspondence of the time part, which may **wrap around midnight**.

For example:

~~~java
OffsetTime time = OffsetTime.parse("00:30+02:00");
OffsetTime utc = time.withOffsetSameInstant(ZoneOffset.UTC);
// 22:30Z
~~~

`00:30+02:00` corresponds to `22:30Z` of the **previous UTC day**, if there were an actual local date. However, `OffsetTime` only stores `22:30Z` and **has nowhere to record the previous day**. Therefore, if you attach the same `LocalDate` to both values after conversion, the resulting `Instant` values will **differ by exactly one day**; this operation is not the way to move a dated event between two time zones.

When you already have a date and need to change the offset while preserving the actual instant, use `OffsetDateTime.withOffsetSameInstant(...)` or `ZonedDateTime.withZoneSameInstant(...)` after combining the full date and time.

### withOffsetSameLocal(newOffset)

~~~java
OffsetTime original = OffsetTime.parse("09:15+07:00");
OffsetTime changed =
        original.withOffsetSameLocal(ZoneOffset.UTC);
// 09:15Z
~~~

This method keeps **the local time digits** unchanged and only replaces the offset. When attached to the same date, `09:15+07:00` and `09:15Z` are **7 hours apart in absolute time**.

Comparison:

| Method | From `09:15+07:00` to UTC | What Is Preserved |
| --- | --- | --- |
| `withOffsetSameInstant(UTC)` | `02:15Z` | Time relationship normalized to UTC |
| `withOffsetSameLocal(UTC)` | `09:15Z` | Local clock reads `09:15` |

Do not use `withOffsetSameLocal` for the task of "converting time between UTC and Vietnam" if you want to preserve the point in time; this method **changes the offset meaning** of the same clock reading.

## 7. To Get an Instant, Attach a Date

An `OffsetTime` **does not have a direct `toInstant()`** because it lacks a date. To convert to an absolute point in time, you must supply a `LocalDate`:

~~~java
OffsetTime clockWithOffset =
        OffsetTime.parse("09:15:30+07:00");
LocalDate calendarDate = LocalDate.of(2025, 4, 9);

OffsetDateTime dated = clockWithOffset.atDate(calendarDate);
Instant instant = dated.toInstant();
// 2025-04-09T02:15:30Z
~~~

`OffsetTime.atDate(LocalDate)` returns an `OffsetDateTime`: the same time and offset, now with a date. At this point, the conversion to UTC has complete data and is unambiguous.

If the value is `09:15+07:00` and you attach:

~~~text
2025-04-09 → 2025-04-09T02:15:00Z
2025-04-10 → 2025-04-10T02:15:00Z
~~~

the two instants are one day apart. This is concrete proof that **a time with an offset but without a date is not an event timestamp**.

Given an existing `Instant`, you can convert it to an `OffsetTime` to keep only the time and offset:

~~~java
OffsetTime timeInVietnam =
        Instant.parse("2025-04-09T02:15:30Z")
                .atOffset(ZoneOffset.ofHours(7))
                .toOffsetTime();
// 09:15:30+07:00
~~~

**Converting in this direction discards the date**. You cannot recover the original `Instant` from `timeInVietnam` unless you store the accompanying date.

If a meeting starts on a specific date in a geographic region, it is better to take `LocalDate`, `LocalTime`, and `ZoneId` and create a `ZonedDateTime` according to the appropriate DST rules. `OffsetTime` does not provide an adequate model for meetings scheduled in civil time that changes seasonally.

## 8. Comparing Two OffsetTime Values: equals, isEqual, isBefore, and compareTo

When comparing two `OffsetTime` instances, decide whether you want to compare **the time digits and offset** or **the time normalized to UTC on a reference day**.

~~~java
OffsetTime vietnam = OffsetTime.parse("09:15+07:00");
OffsetTime utc = OffsetTime.parse("02:15Z");

boolean sameValue = vietnam.equals(utc); // false
boolean sameReferenceTime = vietnam.isEqual(utc); // true
~~~

- `equals` checks both `LocalTime` and `ZoneOffset` in full. Two values are equal only when both components are equal.
- `isEqual` checks equivalence by offset when normalizing the time (often described as **the same instant on an implicit reference date**).
- `isBefore` and `isAfter` compare ordering by the similarly normalized time; they **have no actual date** to decide which event occurred earlier across multiple days.
- `compareTo` / natural ordering uses its own rule: it compares the normalized time part, and if equal, uses the local time as a tie-breaker to ensure natural ordering is consistent with `equals`. Therefore, `isEqual` can be `true` while `compareTo` is non-zero.

In the complete program example, the two objects `09:15:30.123456789+07:00` and `02:15:30.123456789Z` have `isEqual=true`, `equals=false`, and `compareTo=1`.

**Note about midnight:** Comparisons on `OffsetTime` cannot know that "22:30 UTC belongs to the previous day" if a time at a positive offset has crossed a day boundary. To compare **the actual order of two events**, attach the proper date to each event first and compare `Instant` or `OffsetDateTime`. Do not use `OffsetTime.isBefore` to order multi-day records.

## 9. Formatting OffsetTime with DateTimeFormatter

`OffsetTime.toString()` returns an ISO string with an offset; `DateTimeFormatter.ISO_OFFSET_TIME` is the standard formatter for this type:

~~~java
OffsetTime time =
        OffsetTime.parse("09:15:30.123456789+07:00");

String iso = time.toString();
String formatted = DateTimeFormatter.ISO_OFFSET_TIME.format(time);
// Both: "09:15:30.123456789+07:00"
~~~

If an API contract requires milliseconds (three fractional digits), use an explicit formatter:

~~~java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("HH:mm:ss.SSSXXX");
String text = time.format(formatter);
// 09:15:30.123+07:00
~~~

| Pattern Symbol | Meaning | Example |
| --- | --- | --- |
| `HH` | Hour 00–23 | `09` |
| `mm` | Minute | `15` |
| `ss` | Second | `30` |
| `SSS` | Three fractional digits (milliseconds) | `123` |
| `SSSSSSSSS` | Nine fractional digits (nanoseconds) | `123456789` |
| `X` | Short ISO offset | `+07` |
| `XXX` | ISO offset with colon | `+07:00` |
| `Z` in pattern | RFC 822 offset depending on length | `+0700` |
| `'Z'` (single-quoted) | Literal character `Z`, **does not compute offset** | Can cause data misinterpretation |

Confusing `mm` (minute) with `MM` (month) or `XXX` (ISO offset) with a fixed `'Z'` character easily leads to incorrect data. If you need true UTC formatting, convert to the UTC offset first before formatting; **do not append a literal `Z` suffix when the data is not at offset 0**.

The `SSS` pattern takes three fractional digits and **does not round** the nanosecond value. When parsing back a string truncated to milliseconds, you cannot recover sub-millisecond nanoseconds. If full precision is required, use the ISO formatter or a fractional pattern up to 9 digits.

An `OffsetTime` can also be parsed with a custom formatter, provided the format includes both time and offset fields:

~~~java
DateTimeFormatter fixed = DateTimeFormatter.ofPattern(
        "HH:mm:ss.SSSXXX");
OffsetTime parsed =
        OffsetTime.parse("09:15:30.123+07:00", fixed);
~~~

## 10. OffsetTime Does Not Store a Time Zone and Does Not Handle DST

The same `+02:00` offset may be used by multiple regions during different periods. These regions may have **different histories or DST rules**. An `OffsetTime` like `09:00+02:00` only stores the offset number; it does not let you ask "at 09:00 next July in London, what will the offset be?".

For example, if the schedule for a New York branch states:

~~~text
09:00 America/New_York time every business day
~~~

then the start time may correspond to `09:00-05:00` in winter and `09:00-04:00` in summer, based on the rules for that period. Storing only `OffsetTime.parse("09:00-05:00")` accidentally hardcodes the `-05:00` offset, causing the UTC instant of the recurring appointment to **shift by one hour** during DST.

If you need a recurring schedule based on a local wall clock, store **LocalTime + ZoneId** and the recurrence rule. When resolving each occurrence, pick the corresponding date, resolve any gap/overlap, and convert to `ZonedDateTime` and `Instant`.

Conceptual example:

~~~java
LocalDate meetingDate = LocalDate.of(2025, 7, 15);
LocalTime meetingTime = LocalTime.of(9, 0);
ZoneId meetingZone = ZoneId.of("America/New_York");

ZonedDateTime meeting = ZonedDateTime.of(
        meetingDate, meetingTime, meetingZone);
// Time zone rules determine the appropriate offset on this date.
~~~

This is illustrative code inside a method with `java.time.*` imports. On DST transition days, a local time may **not exist** (gap) or **occur twice** (overlap). If business policy requires special handling, check `ZoneRules.getValidOffsets(LocalDateTime)` before deciding.

Even when an `OffsetTime` is created with `OffsetTime.now(ZoneId)`, the `ZoneId` only participates **to select the offset at the current moment**; that `ZoneId` is no longer retained in the returned value.

## 11. Time Arithmetic, Day Overflow, and Date-Free Limitations

Addition and subtraction on `OffsetTime` preserve the offset and produce a new time:

~~~java
OffsetTime original = OffsetTime.parse("23:30+07:00");
OffsetTime later = original.plusHours(2);
// 01:30+07:00
~~~

The result does not indicate that it is 01:30 of **the next day**. This behaves like `LocalTime` because `OffsetTime` has no date component. If you want to compute "two hours after an event at 23:30 on April 9", attach the date first:

~~~java
OffsetDateTime original = OffsetTime
        .parse("23:30+07:00")
        .atDate(LocalDate.of(2025, 4, 9));

OffsetDateTime later = original.plusHours(2);
// 2025-04-10T01:30+07:00
~~~

In problems where absolute points in time must be preserved, use `Instant` for duration calculations or `ZonedDateTime` following the zone's rules. Clearly distinguish **adding 24 real hours** from **advancing to the next calendar day**, especially in regions with DST.

`OffsetTime` has no information about leap years, day of month, day of week, the number of hours in a local calendar day in a DST zone, or future offset transitions. Do not try to infer any of this information from the existing offset.

## 12. Appropriate and Inappropriate Use Cases

### Potentially Appropriate

- **API fields carrying only a declared time and offset**: for example `"businessClock": "09:15:00+07:00"`, when the contract confirms the data is intentionally **dateless**.
- **Clock-time data at a fixed offset**: a configuration operating at `+07:00` independent of any geographic region's seasonal rules.
- **Time exchange between systems** that need to preserve the clock reading and UTC offset without storing a date.
- **Tests or educational examples** distinguishing `LocalTime`, `ZoneOffset`, and `OffsetTime`.

### Usually Inappropriate

- **Timestamps of past events**: store `Instant` or `OffsetDateTime` because a date is required to identify the point in time.
- **Meeting schedules in a city's local time**: requires `LocalDateTime + ZoneId` or `ZonedDateTime`.
- **Transaction occurrence date-time in a database**: `OffsetTime` alone loses the date and is insufficient for auditing.
- **Weekly schedules in a DST region**: requires date and zone ID information, not just the current offset.

In a JSON API, for example, two fields have very different semantics:

~~~json
{
  "openingTimeAtFixedOffset": "09:00:00+07:00",
  "createdAt": "2025-04-09T02:00:00Z"
}
~~~

The first field is **a time with an offset, without a date**; the second is **an absolute point in time**. Do not deserialize both fields into the same type or write a dateless time string into an event timestamp column.

When using SQL, some databases have a `TIME WITH TIME ZONE` data type close to the concept of time + offset, but **driver and DBMS behavior can vary**. Before mapping `OffsetTime` via JDBC, check JDBC 4.2 support, offset handling policies, and the specific column type; do not assume the type name guarantees identical handling across all systems.

## 13. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Assuming `OffsetTime` already identifies a unique instant | Missing a date, so there is no specific timestamp | Attach a `LocalDate` using `atDate(...)` |
| Treating `+07:00` as the `Asia/Ho_Chi_Minh` time zone | Lacks the region's history or future rules | Store `ZoneId` separately if needed |
| Using `withOffsetSameLocal` to "convert to UTC" | Changes the instant once a date is attached | Clearly distinguish SameLocal and SameInstant |
| Assuming `withOffsetSameInstant` preserves the date across midnight | `OffsetTime` does not store a date; time wraps around | Attach the date first and use `OffsetDateTime` |
| Treating `equals` the same as `isEqual` | Values with different time + offset can normalize to the same time | Choose the comparison matching your intent |
| Using `compareTo==0` instead of `isEqual` | Natural ordering breaks ties using local time | Use `isEqual` if only checking normalized time |
| Subtracting `OffsetTime` to compute duration across days | No start/end date information | Use `OffsetDateTime` or `Instant` |
| Assuming `OffsetTime.now(zone)` remembers `ZoneId` | Zone information is lost after creation | Store `ZoneId` separately when needed |
| Storing a daily DST-aware schedule with a fixed offset | Can shift by an hour during DST transitions | Use `LocalTime + ZoneId` per day |
| Appending literal `'Z'` to a non-zero offset time | Misstates the relationship to UTC | Use an actual offset formatter |
| Assuming `09:15` has no seconds | In `LocalTime`, seconds default to 0 | Read `getSecond()` and choose explicit formats |
| Formatting with `SSS` and expecting full nanoseconds on re-parse | Loses sub-millisecond precision | Store/serialize full fractional digits if needed |

## 14. Self-Check Exercises

**Question 1.** Does `OffsetTime.parse("09:00+07:00")` determine the instant at which an event occurred?

**Answer:** No. It is missing a date. Attaching `2025-04-09` corresponds to `2025-04-09T02:00:00Z`; attaching `2025-04-10` yields a different instant.

**Question 2.** For `09:15+07:00`, how do `withOffsetSameInstant(UTC)` and `withOffsetSameLocal(UTC)` differ?

**Answer:** The first produces `02:15Z` (shifts the time according to the offset), while the second produces `09:15Z` (keeps the local time unchanged, changes the offset).

**Question 3.** What does `OffsetTime.parse("00:30+02:00").withOffsetSameInstant(UTC)` return, and why should you be careful?

**Answer:** `22:30Z`. If there were a real date, that UTC time would belong to **the previous day**; the `OffsetTime` object does not store that information, so you cannot accurately shift dates if you only keep the result.

**Question 4.** Is `OffsetTime.parse("09:15+07:00").isEqual(OffsetTime.parse("02:15Z"))` true?

**Answer:** True, because the two values correspond to the same normalized UTC time on the reference day. However, `equals` is `false` because the `LocalTime` and `ZoneOffset` components differ.

**Question 5.** Which API should you call to convert an `OffsetTime` on 2025-04-09 into an `Instant`?

**Answer:** `offsetTime.atDate(LocalDate.of(2025,4,9)).toInstant()`. Attaching the date creates an `OffsetDateTime`, which can then be converted to an instant.

**Question 6.** When scheduling a daily `09:00` meeting in New York, is storing only `OffsetTime.parse("09:00-05:00")` sufficient?

**Answer:** No. New York has DST rules and may use `-04:00` in the summer. You need to keep `LocalTime` together with `ZoneId.of("America/New_York")` and determine the offset for each date.

**Question 7.** Why does `OffsetTime.parse("09:15:30.123456789+07:00").format(DateTimeFormatter.ofPattern("HH:mm:ss.SSSXXX"))` not preserve all nanoseconds in the string?

**Answer:** The `SSS` pattern only prints three fractional digits of a second, corresponding to milliseconds. The original object still retains all nanoseconds, but parsing the truncated string back will not be able to reconstruct the discarded precision.

**Remember:** `OffsetTime = LocalTime + ZoneOffset`, meaning **time with an offset, without a date and without a ZoneId**. Use it when your data needs those exact two components. If you need an event with an absolute point in time, add a `LocalDate` to get an `OffsetDateTime`; if you need a schedule in a city's local time with DST rules, use an appropriate `ZoneId`.
