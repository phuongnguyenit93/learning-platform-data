# Creating a Duration from Seconds, Minutes, Hours, 24-Hour Days, and ISO-8601 Strings

`Duration` in `java.time` represents **an amount of time in seconds and nanoseconds**, such as 90 seconds, 2 hours, or a nominal 24-hour day. You can create one from numeric units using `Duration.ofSeconds`, `ofMinutes`, `ofHours`, and `ofDays`, or parse an ISO-8601 formatted string using `Duration.parse`.

Key point: **`Duration.ofDays(1)` always means 24 hours (86,400 seconds)**. It does not mean "move to the same time on the next calendar day in any time zone"; when DST applies, a day on the local calendar can be 23 or 25 actual hours long. Therefore, distinguish between a **fixed duration** and a **calendar day interval**.

## 1. What Does Duration Represent?

`Duration` is an immutable data type for representing a length of time on the timeline. The value is normalized into a **seconds** component and a **nanosecond-of-second** component; the total nanoseconds of the entire duration can far exceed one second or one day.

Some examples:

| Meaning | Creation | Represented value |
| --- | --- | --- |
| 90 seconds | `Duration.ofSeconds(90)` | 1 minute 30 seconds |
| 15 minutes | `Duration.ofMinutes(15)` | 900 seconds |
| 2 hours | `Duration.ofHours(2)` | 7,200 seconds |
| 1 24-hour day | `Duration.ofDays(1)` | 86,400 seconds |
| 3.25 seconds | `Duration.ofSeconds(3, 250_000_000)` | 3 seconds + 250 million nanoseconds |
| Zero duration | `Duration.ZERO` | 0 seconds |

`Duration` is suitable when you need to measure or add a definite amount of time: wait times, timeouts, the elapsed time between two `Instant`s, the length of a task execution, or "after exactly 30 minutes".

It does **not** carry a start/end point, calendar date, or time zone. `Duration.ofHours(2)` says "2 hours" without specifying when those 2 hours begin.

## 2. Creating from Seconds, Minutes, Hours, and Days

### 2.1. Basic Factory Methods

```java
import java.time.Duration;

Duration seconds = Duration.ofSeconds(90);
Duration minutes = Duration.ofMinutes(15);
Duration hours = Duration.ofHours(2);
Duration days = Duration.ofDays(1);

System.out.println(seconds); // PT1M30S
System.out.println(minutes.toSeconds()); // 900
System.out.println(hours.toSeconds());   // 7200
System.out.println(days.toHours());      // 24
```

This is an illustrative snippet to be placed inside a Java method. The `of…` methods are **static** factory methods, while `toSeconds()` and `toHours()` are methods for reading values from a `Duration` object.

API table:

| API | Input unit | Meaning |
| --- | --- | --- |
| `Duration.ofSeconds(long seconds)` | Seconds | Creates from total number of seconds |
| `Duration.ofSeconds(long seconds, long nanoAdjustment)` | Seconds + nanoseconds | Creates a nanosecond-precision duration, normalizing the fractional part |
| `Duration.ofNanos(long nanos)` | Nanoseconds | Creates from number of nanoseconds |
| `Duration.ofMinutes(long minutes)` | Minutes | Each minute equals 60 seconds |
| `Duration.ofHours(long hours)` | Hours | Each hour equals 3,600 seconds |
| `Duration.ofDays(long days)` | 24-hour days | Each day always equals 86,400 seconds |
| `Duration.ZERO` | Constant | Duration of 0 |

### 2.2. Why Is the Input Unit `long`?

Durations can exceed the range of `int`. The factory methods accept `long` to support long intervals. When calling them with large numeric literals, you can use underscores for readability:

```java
Duration tenMinutes = Duration.ofSeconds(600L);
Duration oneDay = Duration.ofSeconds(86_400L);
Duration twoDays = Duration.ofDays(2);
```

This is an illustrative snippet. Underscores in numeric literals are valid Java syntax and do not change the value. With `Duration.ofDays(2)`, the total duration is 172,800 seconds, which is equivalent to exactly 48 hours.

### 2.3. Creating Fractional Seconds

`Duration` supports precision down to the nanosecond:

```java
Duration fractional = Duration.ofSeconds(3, 250_000_000);
Duration nanos = Duration.ofNanos(3_250_000_000L);

System.out.println(fractional); // PT3.25S
System.out.println(nanos);      // PT3.25S
System.out.println(fractional.equals(nanos)); // true
```

The illustrative snippet requires importing `java.time.Duration`. The `nanoAdjustment` parameter of `ofSeconds(seconds, nanoAdjustment)` is not limited to 0–999,999,999; Java normalizes the adjustment to represent the equivalent total duration, provided the arithmetic does not exceed the supported numeric limits.

For example, `Duration.ofSeconds(3, 1_250_000_000)` is equivalent to 4 seconds and 250 million nanoseconds after normalization. A usually more readable way is to supply the seconds along with a reasonable nanosecond fraction.

**Do not confuse** `Duration.ofNanos(500_000_000)` (half a second) with `Duration.ofMillis(500_000_000)` (500 million milliseconds). The unit is a critical part of the data contract.

## 3. A 24-Hour Day Is Not the Same as a Calendar Day

`Duration.ofDays(n)` treats a day as **exactly 24 hours**. This is a fixed convention independent of time zones:

```java
Duration oneDay = Duration.ofDays(1);
System.out.println(oneDay.getSeconds()); // 86400
System.out.println(oneDay.toHours());    // 24
```

The illustrative snippet requires importing `java.time.Duration`. If you start from an `Instant` and add `Duration.ofDays(1)`, the result is always exactly 86,400 seconds further along the timeline.

In a region that observes DST, the actual elapsed time between two midnights of consecutive days can be 23 or 25 hours. If the requirement is "tomorrow at the same local time", use calendar dates and a zone, such as `ZonedDateTime.plusDays(1)`, instead of adding `Duration.ofDays(1)` to an absolute instant without considering zone rules.

`Period` is a different type used to represent calendar components such as years, months, and days. `Period.ofDays(1)` means "one calendar day" when applied to a date/time with an appropriate calendar context; `Duration.ofDays(1)` means "24 actual hours". In particular, the number of days in a `Period` cannot always be converted into a single fixed number of seconds without knowing the reference point in time and the applicable calendar.

| Goal | Type/API to use |
| --- | --- |
| After exactly 24 hours | `instant.plus(Duration.ofDays(1))` |
| Advance the calendar date by one day, keeping local time in the zone | `zonedDateTime.plusDays(1)` or equivalent calendar arithmetic |
| Elapsed time between two instants | `Duration.between(start, end)` |
| Calculate calendar months/years/days | `Period` with a date or time type that has an appropriate calendar context |

## 4. ISO-8601 Strings: Duration.parse

`Duration.parse(String)` reads an ISO-8601 duration representation. Key designators:

- `P` starts the duration (*period*) representation.
- `D` indicates days.
- `T` introduces the time-of-day portion: hours, minutes, seconds.
- `H` indicates hours, `M` indicates minutes, `S` indicates seconds.
- The seconds part may contain a decimal fraction, such as `PT3.5S`.

Examples:

| ISO-8601 string | Meaning |
| --- | --- |
| `PT0S` | 0 seconds |
| `PT30S` | 30 seconds |
| `PT15M` | 15 minutes |
| `PT2H` | 2 hours |
| `P1D` | 1 day = 24 hours |
| `P2DT3H` | 2 days + 3 hours = 51 hours |
| `PT1H30M` | 1 hour 30 minutes |
| `PT3.25S` | 3.25 seconds |
| `P2DT3H4M5.5S` | 2 days + 3 hours + 4 minutes + 5.5 seconds |

Note that the `M` designator depends on its position: before `T` it means **months** in ISO calendar notation, whereas after `T` it means **minutes** in the hours-minutes-seconds duration portion. `Duration` does not represent calendar months like `Period`; for instance, a duration of 2 months does not have a fixed number of seconds without specifying how to convert it on a calendar.

### Parse and Format Example

```java
import java.time.Duration;

Duration duration = Duration.parse("P2DT3H4M5.5S");

System.out.println(duration);
// PT51H4M5.5S
System.out.println(duration.getSeconds());
// 183845
System.out.println(duration.getNano());
// 500000000
```

This is an illustrative snippet. `Duration.parse` converts an ISO-8601 string into a value; when `toString()` formats it back, Java may produce an equivalent representation by normalizing the total number of hours instead of keeping the original days component. Thus `P2DT3H4M5.5S` is printed as `PT51H4M5.5S`, which is still the exact same duration.

`Duration.parse` throws `DateTimeParseException` (a subclass of `DateTimeException`) if the string is not accepted. For user input or external API data, handle parse errors rather than assuming every string is valid.

## 5. Complete Java 17+ Program

Create the file **`DurationCreationDemo.java`**:

```java
import java.time.Duration;
import java.time.temporal.ChronoUnit;

public class DurationCreationDemo {
    public static void main(String[] args) {
        Duration seconds = Duration.ofSeconds(90);
        Duration minutes = Duration.ofMinutes(15);
        Duration hours = Duration.ofHours(2);
        Duration days = Duration.ofDays(1);
        Duration fractional = Duration.ofSeconds(3, 250_000_000);
        Duration iso = Duration.parse("P2DT3H4M5.5S");
        Duration negative = Duration.ofSeconds(-1, 500_000_000);

        System.out.println("90 seconds: " + seconds);
        System.out.println("15 minutes in seconds: " + minutes.toSeconds());
        System.out.println("2 hours in seconds: " + hours.toSeconds());
        System.out.println("1 day in hours: " + days.toHours());
        System.out.println("Fractional seconds: " + fractional);
        System.out.println("ISO duration: " + iso);
        System.out.println("ISO total seconds: " + iso.getSeconds());
        System.out.println("Negative normalized: " + negative);
        System.out.println("One day seconds: " + Duration.ofDays(1).getSeconds());
        System.out.println("Rounded down to minutes: "
                + Duration.ofSeconds(125).truncatedTo(ChronoUnit.MINUTES));
        System.out.println("Zero duration: " + Duration.ZERO);
    }
}
```

Compile and run:

```bash
javac DurationCreationDemo.java
java DurationCreationDemo
```

**Exact stdout** (verified with `javac --release 17` and `java`):

```text
90 seconds: PT1M30S
15 minutes in seconds: 900
2 hours in seconds: 7200
1 day in hours: 24
Fractional seconds: PT3.25S
ISO duration: PT51H4M5.5S
ISO total seconds: 183845
Negative normalized: PT-0.5S
One day seconds: 86400
Rounded down to minutes: PT2M
Zero duration: PT0S
```

The program demonstrates creation from numeric units, string parsing, preserving nanoseconds, normalizing negative values, and truncating precision. The output is **actual output from the Java program**, not a guessed example.

## 6. Reading Duration Values and Converting Units

Commonly used methods:

| Method | Returns | Meaning |
| --- | --- | --- |
| `getSeconds()` | `long` | Normalized seconds component |
| `getNano()` | `int` | Nanosecond-of-second component, from 0 to 999,999,999 |
| `toSeconds()` | `long` | Total duration converted to whole seconds |
| `toMinutes()` | `long` | Total number of whole minutes |
| `toHours()` | `long` | Total number of whole hours |
| `toDays()` | `long` | Total number of whole 24-hour days |
| `toMillis()` | `long` | Total milliseconds; may fail if it does not fit in `long` |
| `toNanos()` | `long` | Total nanoseconds; much smaller range than `Duration`'s domain |

Example with a 125-second `Duration`:

```java
Duration d = Duration.ofSeconds(125);

System.out.println(d.toMinutes()); // 2
System.out.println(d.toSeconds()); // 125
System.out.println(d.toHours());   // 0
```

`toMinutes()` takes the whole-unit part and does not round 125 seconds up to 3 minutes. If you need to explicitly truncate to minutes, `truncatedTo(ChronoUnit.MINUTES)` creates a new `Duration` with units smaller than a minute dropped. This is not rounding to the nearest minute.

For large durations, `toNanos()` and `toMillis()` can throw `ArithmeticException` if the total cannot be represented in a `long`. `Duration` has a value range larger than the number of nanoseconds that fit in a `long`. When handling large durations, use `getSeconds()`/`getNano()` or `Duration`'s own arithmetic methods rather than converting the entire duration to nanoseconds.

Likewise, pay attention to the difference between **component** and **total**: `getSeconds()` returns the normalized seconds component of the object; `toSeconds()` returns the total whole seconds corresponding to the entire duration according to the API's conversion rules. To be precise, use the `to…` methods for unit conversion and the `get…` methods when inspecting the normalized components.

## 7. Negative Durations and Nanosecond Normalization

A `Duration` can be negative, for example the interval between two instants when the end is earlier than the start. Java's operations normalize the nanosecond part so that the nano component is always in the range 0–999,999,999; the negative sign is carried by the seconds component.

```java
Duration negative = Duration.ofSeconds(-1, 500_000_000);
System.out.println(negative);           // PT-0.5S
System.out.println(negative.getSeconds()); // -1
System.out.println(negative.getNano());    // 500000000
```

This is an illustrative snippet requiring `import java.time.Duration`. Even though `getSeconds()` returns -1 and `getNano()` returns 500 million, the total duration is **−0.5 seconds**. Do not miscalculate the total by treating nanoseconds as a positive value added to the absolute value of seconds; understand `Duration`'s normalization rules.

When adding/subtracting durations, many operations can overflow the numeric range and throw `ArithmeticException`. If data comes from external sources, validate value ranges and handle exceptions appropriately; do not use an arbitrary "large number of days" without defining contract limits.

## 8. Adding Duration to an Instant and Subtracting Two Instants

`Duration` is usually most meaningful when applied to `Instant` or another appropriate time type:

```java
import java.time.*;

Instant start = Instant.parse("2024-03-01T09:00:00Z");
Instant after90Minutes = start.plus(Duration.ofMinutes(90));
System.out.println(after90Minutes);
// 2024-03-01T10:30:00Z

Duration elapsed = Duration.between(start, after90Minutes);
System.out.println(elapsed); // PT1H30M
```

This is an illustrative snippet requiring `import java.time.*`. `Duration.between(start, end)` returns the length from start to end; if `end` is before `start`, the result is negative. Two instants are what need to be clearly defined for a duration to have concrete meaning.

When adding `Duration.ofDays(1)` to an `Instant`, you get a point in time exactly 86,400 seconds later. When adding it to a `ZonedDateTime`, the API still adds the actual elapsed time, so the displayed clock time may shift by one hour on the next calendar day across a DST transition. If the requirement is "same time tomorrow on the local calendar", use `zoned.plusDays(1)`.

## 9. Duration vs. Period: Do Not Use Interchangeably

| Characteristic | `Duration` | `Period` |
| --- | --- | --- |
| Primary representation | Seconds and nanoseconds | Calendar years, months, and days |
| `ofDays(1)` / `ofDays(1)` | Always 24 hours | One calendar day when applied to a date-bearing type |
| Fixed-length months? | No month unit | Has a months component; actual length depends on calendar/reference date |
| Measuring time between two Instants | Suitable | Not the primary purpose |
| "After one calendar month" | Should not be converted to a fixed number of seconds | Suitable when applied in a calendar context |

Example:

```java
LocalDate date = LocalDate.of(2024, 3, 1);

LocalDate nextCalendarDay = date.plus(Period.ofDays(1));
// 2024-03-02

Instant now = Instant.parse("2024-03-01T09:00:00Z");
Instant next24Hours = now.plus(Duration.ofDays(1));
// 2024-03-02T09:00:00Z
```

The illustrative snippet requires `import java.time.*`. On `LocalDate`, which has no time-of-day or zone, adding `Period.ofDays(1)` is a clear calendar-day operation. With `Instant`, `Duration.ofDays(1)` is an absolute 24 hours. This distinction becomes even more critical when calculating payroll, shifts, appointments, billing dates, or reports by local date.

## 10. ISO-8601 and Common Pitfalls

1. **Confusing `P1D` with a calendar month.** `Duration.parse("P1D")` is a 24-hour day, not a month or a calendar day of variable actual length.
2. **Placing `M` in the wrong position.** The date/month portion before `T` uses calendar semantics; the portion after `T` is minutes. With `Duration`, use appropriate ISO hours–minutes–seconds strings such as `PT1H30M`.
3. **Assuming ISO strings preserve each component when formatted.** `Duration.parse("P2DT3H")` may be printed as `PT51H`; the value is still equivalent.
4. **Using `ofDays(1)` to reach the same local time tomorrow.** This is exactly 24 hours, which can shift the clock time across DST; use calendar arithmetic on `ZonedDateTime` when that is the goal.
5. **Treating `toMinutes()` as rounding.** It returns the total whole minutes, dropping any remainder smaller than a minute.
6. **Calling `toNanos()` on very large durations.** Total nanoseconds may overflow `long`; use seconds + nanos or appropriate methods.
7. **Confusing `getNano()` with the total nanoseconds of the duration.** It is the normalized nanosecond-of-second component, not the total nanoseconds of the entire duration.
8. **Ignoring negative durations.** `Duration.between(later, earlier)` can be negative; check the order of instants when your logic does not allow negative values.
9. **Parsing user strings without catching errors.** Malformed strings can cause `DateTimeParseException`.
10. **Confusing Duration with clock time.** `Duration` does not hold a start instant or time zone; use `Instant`/`ZonedDateTime` to attach point-in-time context.

## 11. Test Cases to Include

| Case | Expected result |
| --- | --- |
| `Duration.ofSeconds(90)` | `PT1M30S` |
| `Duration.ofMinutes(15).toSeconds()` | 900 |
| `Duration.ofHours(2).toSeconds()` | 7200 |
| `Duration.ofDays(1).getSeconds()` | 86400 |
| `Duration.parse("P2DT3H4M5.5S")` | `PT51H4M5.5S` |
| `Duration.parse("PT3.25S").getNano()` | 250,000,000 |
| `Duration.ZERO` | `PT0S` |
| `Duration.ofSeconds(125).toMinutes()` | 2 |
| `Duration.ofSeconds(125).truncatedTo(MINUTES)` | `PT2M` |
| Parsing an invalid ISO string | `DateTimeParseException` |
| Adding `Duration.ofDays(1)` to `Instant` | Exactly 86,400 seconds later |
| `ZonedDateTime.plusDays(1)` across DST | Preserves calendar-day/local-time semantics per zone rules; actual elapsed time may not be 24 hours |

In JUnit 5, you can use `assertEquals` to compare the expected `Duration`, or `assertThrows(DateTimeParseException.class, () -> Duration.parse("not-a-duration"))` to verify invalid input is rejected. You should also separately test total seconds, the nano part, and negative/large cases if your logic relies on them.

## 12. Choosing an API by Data Semantics

| Need | API |
| --- | --- |
| Create from seconds | `Duration.ofSeconds(seconds)` |
| Create from minutes | `Duration.ofMinutes(minutes)` |
| Create from hours | `Duration.ofHours(hours)` |
| Create from 24-hour days | `Duration.ofDays(days)` |
| Create from nanoseconds | `Duration.ofNanos(nanos)` |
| Parse an ISO-8601 string | `Duration.parse(text)` |
| Get duration between two instants | `Duration.between(start, end)` |
| Add a fixed amount of time | `instant.plus(duration)` |
| Truncate units smaller than a given unit | `duration.truncatedTo(ChronoUnit.MINUTES)` |
| Calculate by calendar years/months/days | `Period` and a date/time type with appropriate context |

**Remember:** Use `Duration` when your domain refers to a **fixed-length amount of time**, created from seconds, minutes, hours, 24-hour days, or ISO-8601 strings. Use `Period` and calendar rules when you need years, months, or days on a local calendar. Do not let the word "day" trick you into confusing an absolute 24 hours with a calendar day across DST.
