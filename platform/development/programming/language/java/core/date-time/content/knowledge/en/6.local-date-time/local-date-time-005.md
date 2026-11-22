# LocalDateTime: Replacing Components and Truncating Precision

## 1. Objectives and Scope

This lesson focuses on two groups of operations on `java.time.LocalDateTime` in Java 17+:

1. **Replacing a component** of a date-time using `withYear()`, `withMonth()`, `withDayOfMonth()`, `withHour()`, `withMinute()`, `withSecond()`, `withNano()`, or the general forms `with(TemporalField, long)` and `with(TemporalAdjuster)`.
2. **Truncating time granularity** to days, hours, minutes, seconds, milliseconds, microseconds, etc. using `truncatedTo(TemporalUnit)`.

After this lesson, you will be able to explain the immutability of `LocalDateTime`, distinguish **setting a component** from **adding/subtracting a duration**, understand end-of-month and leap-year cases, choose valid truncation units, and avoid confusing truncation with rounding.

**Scope:** `LocalDateTime` represents a **local** date and time, without a time zone or UTC offset. The component-replacement and truncation operations in this lesson act directly on the date-time fields of the local value. A `LocalDateTime` by itself must not be treated as identifying an absolute instant in time.

## 2. LocalDateTime Is an Immutable Value

`LocalDateTime` holds date fields (year, month, day) and time fields (hour, minute, second, nanosecond). The object is **immutable**: every `with...()` and `truncatedTo()` operation returns a resulting value; the original value is never modified.

```java
LocalDateTime original = LocalDateTime.of(2024, 1, 31, 14, 27);
original.withHour(9); // Return value is discarded

System.out.println(original); // 2024-01-31T14:27

LocalDateTime updated = original.withHour(9);
System.out.println(updated);  // 2024-01-31T09:27
System.out.println(original); // 2024-01-31T14:27
```

This is an **illustrative snippet inside a method**, requiring `import java.time.LocalDateTime;`.

You can reassign the variable `original = original.withHour(9);` if you want the variable to point to the new value; this **does not mutate the old object**. The API may optimize by returning the same object when nothing changes, so do not use `==` to check whether two date-times have the same value; use `equals()`, `isBefore()`, or `isAfter()` depending on your needs.

### Creation and Nanosecond Granularity

```java
LocalDateTime moment = LocalDateTime.of(
        2024, 1, 31, 14, 27, 38, 987_654_321);
System.out.println(moment);
// 2024-01-31T14:27:38.987654321
```

This is an illustrative snippet inside a method, requiring `import java.time.LocalDateTime;`.

The value contains all fields:

| Field | Value | Common Range |
| --- | ---: | --- |
| Year | 2024 | `LocalDateTime` supports the extended ISO year range |
| Month | 1 | 1–12 |
| Day of month | 31 | 1–28/29/30/31, depending on month/year |
| Hour | 14 | 0–23 |
| Minute | 27 | 0–59 |
| Second | 38 | 0–59 |
| Nanosecond of second | 987,654,321 | 0–999,999,999 |

`LocalDateTime` **can represent** the nanosecond fraction; that does not guarantee that a clock, database, or measuring device **has actual precision** down to 1 ns. `LocalDateTime.now()` uses the system clock with platform-dependent resolution; examples with fixed values use `of(...)` so the output is reproducible.

## 3. Replacing Components with with...()

The methods have clear names indicating **which component to set**:

| Method | Meaning | Example |
| --- | --- | --- |
| `withYear(2025)` | Sets year to 2025 | Keeps other fields when possible |
| `withMonth(2)` | Sets month to 2 | May adjust end-of-month day |
| `withDayOfMonth(1)` | Sets day of month to 1 | Moves to the first day of the month |
| `withDayOfYear(60)` | Sets the 60th day of the year | Depends on whether it is a leap year |
| `withHour(9)` | Sets hour to 09 | Keeps minute/second/nano |
| `withMinute(0)` | Sets minute to 00 | Keeps hour/second/nano |
| `withSecond(0)` | Sets second to 00 | **Does not automatically set nano to 0** |
| `withNano(0)` | Sets nanosecond fraction to 0 | Does not modify second |

Example:

```java
LocalDateTime source = LocalDateTime.of(
        2024, 8, 23, 14, 27, 38, 987_654_321);

LocalDateTime meeting = source.withHour(9).withMinute(0);
LocalDateTime exactSecond = source.withNano(0);
LocalDateTime startOfMinute = source.withSecond(0).withNano(0);
```

This is an illustrative snippet inside a method, requiring `import java.time.LocalDateTime;`.

Results:

- `meeting` = `2024-08-23T09:00:38.987654321`: hour/minute changed, second fraction preserved.
- `exactSecond` = `2024-08-23T14:27:38`: only the nanosecond part is zeroed.
- `startOfMinute` = `2024-08-23T14:27`: both second and nanosecond are zeroed.

**Common pitfall:** `withSecond(0)` is **not** a "truncate to the start of the minute" method, because nanoseconds may still be non-zero. Use `truncatedTo(ChronoUnit.MINUTES)` or set both `withSecond(0).withNano(0)`.

### 3.1. Distinguishing with...(), plus...(), and minus...()

```java
LocalDateTime source = LocalDateTime.of(2024, 5, 10, 14, 27);

LocalDateTime setHour = source.withHour(9);  // 2024-05-10T09:27
LocalDateTime addHour = source.plusHours(9); // 2024-05-10T23:27
LocalDateTime minusHour = source.minusHours(9); // 2024-05-10T05:27
```

This is an illustrative snippet inside a method, requiring `import java.time.LocalDateTime;`.

- `withHour(9)` means "**set hour to 9**".
- `plusHours(9)` means "**add 9 hours**".
- `minusHours(9)` means "**subtract 9 hours**".

`with...()` operations are typically associated with **choosing a specific field value**, such as a start-of-work hour, minute 00, or the first day of the month. Use `plus/minus` when the problem involves **shifting** by an amount.

## 4. End-of-Month, Leap-Year, and Invalid-Value Rules

When setting the month or year, the current day may **not exist in the new month/year**. Certain `with...()` methods adjust the day to the last valid day:

```java
LocalDateTime jan31 = LocalDateTime.of(2024, 1, 31, 14, 27);
LocalDateTime feb2024 = jan31.withMonth(2);
LocalDateTime leapDay = LocalDateTime.of(2024, 2, 29, 14, 27);
LocalDateTime nextYear = leapDay.withYear(2025);

System.out.println(feb2024); // 2024-02-29T14:27
System.out.println(nextYear); // 2025-02-28T14:27
```

This is an illustrative snippet inside a method, requiring `import java.time.LocalDateTime;`. With `withMonth(2)`, Jan 31 adjusts to the last day of February; with `withYear(2025)`, Feb 29 of a leap year becomes Feb 28 of a non-leap year.

However, **directly setting a non-existent day** with `withDayOfMonth()` throws `DateTimeException`. For example:

```java
LocalDateTime feb29 = LocalDateTime.of(2024, 2, 29, 14, 27);
// feb29.withDayOfMonth(30); // DateTimeException: February 2024 has no day 30
```

This is an illustrative snippet inside a method. Rule to remember: **certain month/year changes have a day-adjustment mechanism**; do not generalize that every `with...()` automatically fixes any invalid day.

Other limits: `withHour(24)`, `withMinute(60)`, `withSecond(60)`, and `withNano(1_000_000_000)` are all invalid for the range of `LocalDateTime`. When data comes from a form or API, validate or handle `DateTimeException` appropriately.

### Execution Order in Chained Component Replacements

```java
LocalDateTime start = LocalDateTime.of(2024, 1, 31, 14, 27);

LocalDateTime a = start.withMonth(2).withDayOfMonth(28);
LocalDateTime b = start.withDayOfMonth(28).withMonth(2);
```

This is an illustrative snippet inside a method. For this input, both `a` and `b` evaluate to `2024-02-28T14:27`. However, the general rule is that **operations run from left to right**: `start.withMonth(2).withDayOfMonth(31)` fails on the second step, whereas `start.withDayOfMonth(31).withMonth(2)` adjusts to `2024-02-29T14:27`. Do not arbitrarily reorder calls in a pipeline that depends on intermediate values.

## 5. General Form with(TemporalField, long)

If the date/time field is selected dynamically (for example, from a configuration table), use this form:

```java
LocalDateTime updated = source.with(
        ChronoField.MINUTE_OF_HOUR, 5);
```

This is an illustrative snippet inside a method, requiring `source` to be a `LocalDateTime` and `import java.time.temporal.ChronoField;`.

Some `ChronoField` values supported by `LocalDateTime`:

- `YEAR`, `MONTH_OF_YEAR`, `DAY_OF_MONTH`, `DAY_OF_YEAR`;
- `HOUR_OF_DAY`, `MINUTE_OF_HOUR`, `SECOND_OF_MINUTE`;
- `MILLI_OF_SECOND`, `MICRO_OF_SECOND`, `NANO_OF_SECOND`.

Note that `NANO_OF_SECOND` is the nanosecond fraction within a second, not a nanosecond timestamp since the Unix epoch. `LocalDateTime` has no time zone or offset, so fields like `INSTANT_SECONDS` cannot be retrieved from it directly.

Check support when the field comes from an external source:

```java
boolean supported = source.isSupported(ChronoField.MINUTE_OF_HOUR);
// true

boolean instantSupported = source.isSupported(ChronoField.INSTANT_SECONDS);
// false
```

This is an illustrative snippet inside a method with `source` as a `LocalDateTime`. Calling `with(...)` with an unsupported field may throw `UnsupportedTemporalTypeException`, which is a subclass of `DateTimeException`.

In regular code, `withMinute(5)` is easier to read than `with(ChronoField.MINUTE_OF_HOUR, 5)`; the general form is suited for dynamic field selection.

## 6. Form with(TemporalAdjuster): Adjusting by Calendar Rules

`with(TemporalAdjuster)` lets you apply calendar-semantic adjustments such as "first day of the month", "last day of the month", or "next Monday". `TemporalAdjusters` provides many built-in adjusters.

```java
LocalDateTime source = LocalDateTime.of(2024, 8, 23, 14, 27);

LocalDateTime firstDay =
        source.with(TemporalAdjusters.firstDayOfMonth());
LocalDateTime lastDay =
        source.with(TemporalAdjusters.lastDayOfMonth());
LocalDateTime nextMonday =
        source.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
```

This is an illustrative snippet inside a method, requiring:

```java
import java.time.DayOfWeek;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;
```

Results:

- `firstDay` = `2024-08-01T14:27`;
- `lastDay` = `2024-08-31T14:27`;
- `nextMonday` = `2024-08-26T14:27`.

Calendar adjusters change the **date part** while preserving the time of day if the rule does not require changing it. If you want both the first day of the month **and 00:00**, add a truncation to days:

```java
LocalDateTime monthStart = source
        .with(TemporalAdjusters.firstDayOfMonth())
        .truncatedTo(ChronoUnit.DAYS);
// 2024-08-01T00:00
```

This is an illustrative snippet with `import java.time.temporal.ChronoUnit;` and the previous imports. The two operations perform two distinct tasks: adjusting the **date** and clearing the **time-of-day components**.

You can replace the date or time part with `with(LocalDate)` / `with(LocalTime)` because those types implement `TemporalAdjuster`, but `with(TemporalAdjusters....)` expresses calendar-rule intent more clearly.

## 7. truncatedTo(TemporalUnit): Truncating Fields Smaller Than a Unit

`LocalDateTime.truncatedTo(unit)` returns a date-time with **all time fields smaller than the chosen unit truncated**, leaving larger parts unchanged and without adding anything to round up.

Visualization:

```text
Original value:       2024-01-31T14:27:38.987654321
Truncated to hours:   2024-01-31T14:00
Truncated to minutes: 2024-01-31T14:27
Truncated to seconds: 2024-01-31T14:27:38
Truncated to ms:      2024-01-31T14:27:38.987
Truncated to µs:      2024-01-31T14:27:38.987654
```

The method takes a `TemporalUnit` (commonly `ChronoUnit`):

```java
LocalDateTime source = LocalDateTime.of(
        2024, 1, 31, 14, 27, 38, 987_654_321);

LocalDateTime hour = source.truncatedTo(ChronoUnit.HOURS);
LocalDateTime minute = source.truncatedTo(ChronoUnit.MINUTES);
LocalDateTime second = source.truncatedTo(ChronoUnit.SECONDS);
LocalDateTime millis = source.truncatedTo(ChronoUnit.MILLIS);
LocalDateTime micros = source.truncatedTo(ChronoUnit.MICROS);
LocalDateTime dateStart = source.truncatedTo(ChronoUnit.DAYS);
```

This is an illustrative snippet inside a method, requiring `import java.time.LocalDateTime;` and `import java.time.temporal.ChronoUnit;`.

| Unit | Truncated Value |
| --- | --- |
| `DAYS` | `2024-01-31T00:00` |
| `HOURS` | `2024-01-31T14:00` |
| `MINUTES` | `2024-01-31T14:27` |
| `SECONDS` | `2024-01-31T14:27:38` |
| `MILLIS` | `2024-01-31T14:27:38.987` |
| `MICROS` | `2024-01-31T14:27:38.987654` |
| `NANOS` | Preserved in full: `2024-01-31T14:27:38.987654321` |

**Truncating to days** on `LocalDateTime` means keeping the date and setting the time to 00:00:00.000000000. It does **not** determine "the actual start of the day in UTC" because `LocalDateTime` has no attached `ZoneId`.

### Why Is DAYS Valid While WEEKS Is Not?

`LocalDateTime.truncatedTo(...)` performs truncation based on the **time within a single day**. The truncation unit must have a positive duration that **evenly divides a standard 24-hour day**, and must not be longer than a standard day. Therefore `NANOS`, `MICROS`, `MILLIS`, `SECONDS`, `MINUTES`, `HOURS`, `HALF_DAYS`, and `DAYS` are valid; `WEEKS`, `MONTHS`, and `YEARS` are not valid truncation units.

Example:

```java
LocalDateTime noon = source.truncatedTo(ChronoUnit.HALF_DAYS);
// For source 14:27, noon is 2024-01-31T12:00

// source.truncatedTo(ChronoUnit.WEEKS);
// UnsupportedTemporalTypeException
```

This is an illustrative snippet inside a method with `source` as a `LocalDateTime`. To get the start of the week, use a **calendar rule** with an adjuster/selecting the first day of the week, then truncate the time part:

```java
LocalDateTime startOfIsoWeek = source
        .with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        .truncatedTo(ChronoUnit.DAYS);
```

This is an illustrative snippet requiring `ChronoUnit`, `DayOfWeek`, and `TemporalAdjusters`. The Monday-start week convention in this example follows the ISO calendar; some business domains or locales use Sunday or another rule.

## 8. Runnable Code: Replacing Components and Truncating Precision

Save the file **`LocalDateTimeAdjustmentDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.temporal.ChronoField;
import java.time.temporal.ChronoUnit;

public class LocalDateTimeAdjustmentDemo {
    public static void main(String[] args) {
        LocalDateTime original = LocalDateTime.of(
                2024, 1, 31, 14, 27, 38, 987_654_321);

        LocalDateTime february = original.withMonth(2);
        LocalDateTime nineOClock = original.withHour(9)
                .withMinute(0).withSecond(0).withNano(0);
        LocalDateTime minuteFive =
                original.with(ChronoField.MINUTE_OF_HOUR, 5);

        System.out.println("original = " + original);
        System.out.println("february = " + february);
        System.out.println("nineOClock = " + nineOClock);
        System.out.println("minuteFive = " + minuteFive);
        System.out.println("truncatedHours = "
                + original.truncatedTo(ChronoUnit.HOURS));
        System.out.println("truncatedMinutes = "
                + original.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("truncatedMillis = "
                + original.truncatedTo(ChronoUnit.MILLIS));
        System.out.println("truncatedMicros = "
                + original.truncatedTo(ChronoUnit.MICROS));
        System.out.println("truncatedDays = "
                + original.truncatedTo(ChronoUnit.DAYS));
        System.out.println("originalAgain = " + original);
    }
}
```

Run with Java 17+:

```bash
javac LocalDateTimeAdjustmentDemo.java
java LocalDateTimeAdjustmentDemo
```

Deterministic output:

```text
original = 2024-01-31T14:27:38.987654321
february = 2024-02-29T14:27:38.987654321
nineOClock = 2024-01-31T09:00
minuteFive = 2024-01-31T14:05:38.987654321
truncatedHours = 2024-01-31T14:00
truncatedMinutes = 2024-01-31T14:27
truncatedMillis = 2024-01-31T14:27:38.987
truncatedMicros = 2024-01-31T14:27:38.987654
truncatedDays = 2024-01-31T00:00
originalAgain = 2024-01-31T14:27:38.987654321
```

Explanation:

1. `withMonth(2)` moves Jan 31 to Feb 29, 2024 because it is a leap year, preserving the hour and nanoseconds.
2. Chaining `withHour(9).withMinute(0).withSecond(0).withNano(0)` sets the time to exactly 09:00, avoiding leftover seconds or nanoseconds.
3. `with(ChronoField.MINUTE_OF_HOUR, 5)` replaces minute 27 with 05; other fields remain unchanged.
4. `truncatedTo(...)` drops time parts smaller than the unit without rounding and without mutating `original`.

Note that `LocalDateTime.toString()` may **omit trailing zero groups**. For example, 09:00 prints as `2024-01-31T09:00` rather than forcing `:00.000000000`. The second and nanosecond fields still hold the value 0.

## 9. Truncation vs. Rounding vs. Display Formatting

These three operations serve different purposes:

| Purpose | API or Approach | Changes the Underlying Value? |
| --- | --- | --- |
| Truncate parts smaller than one minute | `truncatedTo(ChronoUnit.MINUTES)` | Yes: seconds/nanos become 0 in the result |
| Round to the nearest minute | Define a rule and compute intentionally | Yes: minute sometimes increments |
| Display only down to minutes | `DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm")` | No: only changes the formatted text |

Example with the same value:

```java
LocalDateTime input = LocalDateTime.of(2024, 2, 29, 23, 59, 45);
LocalDateTime truncated = input.truncatedTo(ChronoUnit.MINUTES);
LocalDateTime roundedHalfUp = input.plusSeconds(30)
        .truncatedTo(ChronoUnit.MINUTES);

System.out.println(truncated);     // 2024-02-29T23:59
System.out.println(roundedHalfUp); // 2024-03-01T00:00
```

This is an illustrative snippet inside a method, requiring imports for `LocalDateTime` and `ChronoUnit`. The "add 30 seconds first, then truncate to minutes" approach demonstrates a **round-to-nearest-minute, half-up** policy on a local calendar; in general problems, consider boundary overflow, rounding rules, and sign/direction requirements of the quantity being processed.

To **change only the display** while keeping nanoseconds intact:

```java
DateTimeFormatter formatter =
        DateTimeFormatter.ofPattern("uuuu-MM-dd HH:mm");
String display = input.format(formatter); // 2024-02-29 23:59
LocalDateTime stillOriginal = input;      // still has second = 45
```

This is an illustrative snippet inside a method, requiring `import java.time.format.DateTimeFormatter;` and the `input` variable from the example above.

**Design warning:** Do not use string formatting as a way to truncate internal data unless the system contract actually requires serializing to a string and parsing back. `DateTimeFormatter` only governs representation; `truncatedTo()` directly affects the resulting date-time value.

## 10. Truncating to ms, µs, and ns When Working with Databases

`LocalDateTime` stores the fractional second in **nanoseconds** as an integer from 0 to 999,999,999. Common units:

| Granularity | Nanoseconds per Unit | Fractional Example |
| --- | ---: | --- |
| Millisecond (ms) | 1,000,000 ns | `.987` |
| Microsecond (µs) | 1,000 ns | `.987654` |
| Nanosecond (ns) | 1 ns | `.987654321` |

A system that stores down to microseconds may require:

```java
LocalDateTime persisted =
        original.truncatedTo(ChronoUnit.MICROS);
```

This is an illustrative snippet inside a method with `original` as a `LocalDateTime` containing nanoseconds, requiring `ChronoUnit`.

In an application that persists date-times, you should verify:

- Which fractional-second precision the **database column and JDBC driver** support; do not assume every DB preserves all 9 digits.
- **Database behavior** when receiving more fractional digits than the column allows: it may round or truncate depending on the DBMS and column type.
- If you need exact equality between a written value and a read-back value, consider **normalizing to the same granularity** per the contract before saving.
- **`LocalDateTime` contains no time zone**: truncating to milliseconds/microseconds/nanoseconds does not turn this value into a UTC timestamp. To represent an absolute instant, use a type/strategy with appropriate offset/zone information.

A `LocalDateTime` with nanosecond part `987_654_321` becomes `987_654_000` after `truncatedTo(MICROS)` and `987_000_000` after `truncatedTo(MILLIS)`. This is **intentional information loss**; the truncated digits cannot be recovered simply by changing units.

## 11. Practical Problem: Grouping Records by Minute or Hour

Suppose an application records events with local times:

```text
2024-08-23T14:27:03
2024-08-23T14:27:51
2024-08-23T14:28:04
```

You can create a per-minute grouping key using `truncatedTo(ChronoUnit.MINUTES)`; the first two events map to the same key `2024-08-23T14:27`.

Save the file **`LocalMinuteGroupingDemo.java`**:

```java
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class LocalMinuteGroupingDemo {
    public static void main(String[] args) {
        List<LocalDateTime> events = List.of(
                LocalDateTime.of(2024, 8, 23, 14, 27, 3),
                LocalDateTime.of(2024, 8, 23, 14, 27, 51),
                LocalDateTime.of(2024, 8, 23, 14, 28, 4));

        Map<LocalDateTime, Long> counts = events.stream()
                .collect(Collectors.groupingBy(
                        time -> time.truncatedTo(ChronoUnit.MINUTES),
                        TreeMap::new,
                        Collectors.counting()));

        counts.forEach((minute, count) ->
                System.out.println(minute + " -> " + count));
    }
}
```

Run:

```bash
javac LocalMinuteGroupingDemo.java
java LocalMinuteGroupingDemo
```

Output:

```text
2024-08-23T14:27 -> 2
2024-08-23T14:28 -> 1
```

Explanation: `TreeMap` sorts `LocalDateTime` keys in natural order so the printed output is ordered. The original event values are not modified.

**When grouping events across multiple time zones or along a real timeline**, do not group solely on `LocalDateTime`; the same label "14:27" may correspond to different instants. In that case, normalize timestamps that carry instant information (such as `Instant`) and define how buckets are created in UTC or a specific `ZoneId`.

## 12. Replacing Date While Keeping Time; Setting Time While Keeping Date

Many scheduling applications need to combine a "date picked from a calendar" with a "fixed time from configuration".

### Replacing the Entire Date Part

```java
LocalDateTime appointment =
        LocalDateTime.of(2024, 8, 23, 14, 27, 38);

LocalDateTime anotherDay =
        appointment.with(LocalDate.of(2024, 9, 2));
// 2024-09-02T14:27:38
```

This is an illustrative snippet requiring `import java.time.LocalDate;` and `import java.time.LocalDateTime;` inside a method. `LocalDate` implements `TemporalAdjuster`, so `with(LocalDate)` replaces the entire date part and preserves the time part.

### Replacing the Entire Time Part

```java
LocalDateTime newTime = appointment.with(LocalTime.of(9, 0));
// 2024-08-23T09:00
```

This is an illustrative snippet requiring `import java.time.LocalTime;` with `appointment` from the example above. `LocalTime.of(9, 0)` has seconds and nanoseconds equal to 0, so the result is exact 09:00 instead of calling only `withHour(9)` and keeping the smaller fractions of the old time.

Equivalent approaches by intent:

```java
LocalDateTime startOfDay = appointment
        .toLocalDate()
        .atStartOfDay();

LocalDateTime sameDayAtNine = appointment
        .toLocalDate()
        .atTime(9, 0);
```

This is an illustrative snippet inside a method, requiring `LocalDateTime`. The two results are `2024-08-23T00:00` and `2024-08-23T09:00`. Methods like `atStartOfDay()` and `atTime()` express **creating a date-time from a date**, rather than adjusting the original object.

## 13. DST, Time Zones, and the Boundaries of LocalDateTime

`LocalDateTime.of(2024, 3, 10, 2, 30)` is valid as a **local date-time label**, but in `America/New_York`, 02:30 on March 10, 2024 falls into a clock-jump gap (DST gap), so it does not map directly to an actual instant in that time zone.

Performing:

```java
LocalDateTime t = LocalDateTime.of(2024, 3, 10, 2, 30);
LocalDateTime cut = t.truncatedTo(ChronoUnit.HOURS);
// 2024-03-10T02:00
```

does not resolve non-existent time intervals when attaching a `ZoneId`. This is an illustrative snippet with `LocalDateTime` and `ChronoUnit` inside a method.

Key distinctions:

- `LocalDateTime` describes **date/time fields** and can truncate those fields without knowing a time zone.
- `ZonedDateTime` combines the local calendar with **time-zone rules** to handle overlaps and gaps.
- `Instant` describes **an absolute point** on the UTC timeline.

If you are processing a meeting schedule in local time, specify the `ZoneId` and DST handling rules at the input/output boundaries. If you need to bucket events by elapsed seconds, compute from actual instants (such as `Instant`), because a "local start of hour" can repeat or be skipped in DST regions.

## 14. Error Checking and Boundary Conditions

Common mistakes:

1. **Discarding the return value:** `value.withMinute(0);` does not change the `value` variable.
2. **Setting only seconds and forgetting nanoseconds:** `withSecond(0)` does not produce the exact start of the minute if `getNano() != 0`.
3. **Confusing "set" with "add":** `withHour(9)` is different from `plusHours(9)`.
4. **Treating truncation as rounding:** `truncatedTo(MINUTES)` turns `14:27:59.999` into `14:27`, not `14:28`.
5. **Using too large a unit:** `truncatedTo(WEEKS/MONTHS/YEARS)` is invalid on `LocalDateTime`.
6. **Ignoring end-of-month dates:** `withMonth(2)` from Jan 31 adjusts to Feb 28/29; however, `withDayOfMonth(31)` on a February date is invalid.
7. **Assuming LocalDateTime is UTC:** the value contains no offset or zone.
8. **Confusing display formatting with data:** `format()` does not strip nanoseconds from the object.
9. **Assuming fixed storage precision:** databases, formatters, and clocks may only support ms or µs.
10. **Using system clock values in fixed tests:** prefer `LocalDateTime.of(...)` so expected output stays constant.

Save the file **`InvalidLocalDateTimeDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;

public class InvalidLocalDateTimeDemo {
    public static void main(String[] args) {
        LocalDateTime value = LocalDateTime.of(2024, 2, 29, 14, 27);

        try {
            value.withDayOfMonth(30);
        } catch (DateTimeException ex) {
            System.out.println("Invalid day");
        }

        try {
            value.truncatedTo(ChronoUnit.WEEKS);
        } catch (DateTimeException ex) {
            System.out.println("Unsupported truncate unit");
        }

        System.out.println("unchanged = " + value);
    }
}
```

Run:

```bash
javac InvalidLocalDateTimeDemo.java
java InvalidLocalDateTimeDemo
```

Output:

```text
Invalid day
Unsupported truncate unit
unchanged = 2024-02-29T14:27
```

The `value` object remains intact after both failed operations thanks to immutability.

## 15. Guidelines for Choosing APIs in Applications

| Requirement | Recommendation | Explanation |
| --- | --- | --- |
| Change appointment hour while keeping date/minute/second | `withHour(9)` | Sets only the hour field |
| Set exact 09:00:00.000… | `with(LocalTime.of(9, 0))` | Replaces the entire time part |
| Set first day of month, keeping time | `with(TemporalAdjusters.firstDayOfMonth())` | Adjusts the date part |
| Set **start of day** 00:00 | `truncatedTo(ChronoUnit.DAYS)` | Sets all time fields to 0 |
| Create an hourly grouping key | `truncatedTo(ChronoUnit.HOURS)` | Truncates minute/second/nano |
| Truncate nanoseconds to microseconds for DB sync | `truncatedTo(ChronoUnit.MICROS)` | Drops the last 0–999 ns |
| Display only year-month-day and hour-minute | `DateTimeFormatter` | Does not alter the date-time value |
| Add exactly 30 minutes | `plusMinutes(30)` | Shifts by an amount on the local timeline |
| Truncate an absolute UTC date-time | Choose `Instant` and an instant contract | `LocalDateTime` lacks time zone/offset |

Operations can be combined, but the order must be expressed clearly. For example, `dateTime.withHour(9).truncatedTo(MINUTES)` both sets the hour to 09 and clears seconds/nanoseconds; it **still keeps the original minute**. To get exact 09:00, you must set the minute to 0 or use `with(LocalTime.of(9, 0))`.

## 16. Self-Check Exercises

**Question 1.** For `LocalDateTime.of(2024, 1, 31, 14, 27).withMonth(2)`, what is the result?

**Answer:** `2024-02-29T14:27`. 2024 is a leap year, so day 31 is adjusted to the end of February.

**Question 2.** Is `withSecond(0)` always equivalent to `truncatedTo(ChronoUnit.MINUTES)`?

**Answer:** No. `withSecond(0)` keeps `nanoOfSecond`; `truncatedTo(MINUTES)` sets both seconds and nanoseconds to 0.

**Question 3.** What do you get when truncating `2024-01-31T14:27:38.987654321` to `MILLIS` and `MICROS`?

**Answer:** `2024-01-31T14:27:38.987` and `2024-01-31T14:27:38.987654`, respectively.

**Question 4.** Why shouldn't you call `truncatedTo(ChronoUnit.MONTHS)` on `LocalDateTime`?

**Answer:** `truncatedTo` truncates by a duration unit that evenly divides a standard day and is no longer than a day; a month is a calendar unit with variable length. To get the start of the month, use `TemporalAdjusters.firstDayOfMonth()` combined with truncating to days.

**Question 5.** Starting from `LocalDateTime.of(2024, 8, 23, 14, 27, 38)`, how do you create exact 09:00 on the same day?

**Answer:** `value.with(LocalTime.of(9, 0))`, or the chain `value.withHour(9).withMinute(0).withSecond(0).withNano(0)`.

**Question 6.** When calling `truncatedTo(MINUTES)` on `LocalDateTime`, do we obtain a UTC timestamp?

**Answer:** No. The result is still a **local date-time without a time zone or offset**.

**Takeaway:** The `with...()` family **sets/replaces a component or applies a rule**, while `truncatedTo(...)` **drops time parts smaller than the desired granularity**. Both return an immutable `LocalDateTime`. Choose the operation based on business rules, account for end-of-month dates and unit limits, and do not confuse arithmetic precision with time zones or rounding.