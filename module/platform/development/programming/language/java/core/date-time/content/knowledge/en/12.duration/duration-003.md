# Measuring the Distance Between Two Values with between()

In Java, `Duration.between(start, end)` creates a `Duration` object representing the amount of time from a start value to an end value. This method is commonly used to calculate the elapsed time between two timestamps, request processing time, wait time, or the length of a shift with both date and time specified.

~~~java
Instant start = Instant.parse("2025-04-09T09:00:00Z");
Instant end = Instant.parse("2025-04-09T10:30:15.250Z");
Duration elapsed = Duration.between(start, end);
// PT1H30M15.25S
~~~

The core rule is **result = end − start**. Swapping the order of the two arguments can produce a negative Duration. Duration represents time in seconds and nanoseconds, and does not directly model a calendar month or the notion of “the same time tomorrow”.

## 1. Syntax and Input Types

~~~java
Duration duration = Duration.between(start, end);
~~~

The two arguments are typically types that support the time units Duration requires, such as `Instant`, `OffsetDateTime`, `ZonedDateTime`, `LocalDateTime`, `LocalTime`, or `OffsetTime`. Not every `Temporal` type is suitable; a date-only type without the required time fields can throw `UnsupportedTemporalTypeException`.

| Input Type | Meaning and Limitations |
| --- | --- |
| `Instant` | Duration between two absolute points in time |
| `OffsetDateTime` | Two points with date, time, and a fixed offset |
| `ZonedDateTime` | Elapsed duration according to zone rules, including time transitions |
| `LocalDateTime` | Distance between local date-times; does not by itself determine an absolute duration |
| `LocalTime` | Compares wall-clock time only; has no date, so it can be negative across midnight |
| `OffsetTime` | Has time and offset but no date, so care is needed at day boundaries |

Duration does not mutate the input objects. `java.time` types are immutable; the method returns a new object.

## 2. Reading Results and Converting Units

~~~java
Instant start = Instant.parse("2025-04-09T09:00:00Z");
Instant end = Instant.parse("2025-04-09T10:30:15.250Z");
Duration duration = Duration.between(start, end);

System.out.println(duration);                 // PT1H30M15.25S
System.out.println(duration.getSeconds());    // 5415
System.out.println(duration.getNano());       // 250000000
System.out.println(duration.toMillis());      // 5415250
System.out.println(duration.toSeconds());     // 5415
System.out.println(duration.toMinutesPart()); // 30
System.out.println(duration.toSecondsPart()); // 15
~~~

`Duration.toString()` uses ISO-8601 representation; `PT1H30M15.25S` means 1 hour, 30 minutes, and 15.25 seconds.

- `getSeconds()` returns the normalized whole-seconds component, not the seconds within a minute; it can be greater than 59 or negative.
- `getNano()` returns the remaining nanosecond fraction within the second in the normalized representation.
- `toSeconds()` and `toMillis()` return the total number of whole units, truncating any fraction smaller than the target unit.
- `toMinutesPart()` and `toSecondsPart()` return the remainder after dividing into larger units. For example, the total is 90 minutes, but `toMinutesPart()` is 30 because there is one whole hour.

The nanosecond resolution of the type does not guarantee that the source clock has equivalent accuracy.

## 3. Argument Order (start/end) and Negative Duration

~~~java
Instant earlier = Instant.parse("2025-04-09T09:00:00Z");
Instant later = Instant.parse("2025-04-09T10:30:15.250Z");

System.out.println(Duration.between(earlier, later));
// PT1H30M15.25S
System.out.println(Duration.between(later, earlier));
// PT-1H-30M-15.25S
~~~

A negative result is valid when `end` occurs before `start`. It may indicate that the two arguments were swapped or represent an offset from a later point back to an earlier point. Do not automatically call `abs()` to hide the negative sign: decide based on business requirements whether it is an error or a directional result. `abs()` only takes the magnitude, losing the before/after information.

## 4. Choosing the Right Type to Calculate Time Intervals

### Instant: Actual Elapsed Time Between Two Events

~~~java
Instant requestStart = Instant.parse("2025-04-09T09:00:00Z");
Instant requestEnd = Instant.parse("2025-04-09T09:00:02.345Z");
Duration latency = Duration.between(requestStart, requestEnd);
// PT2.345S
~~~

When both points are already absolute timestamps, `Instant` is the clear choice for the duration between events. To measure execution time within the same JVM, `System.nanoTime()` is usually more appropriate because it is a monotonic clock for measuring intervals, whereas `Instant.now()` uses a wall clock that may be adjusted.

### LocalDateTime: Distance on the Local Clock

~~~java
LocalDateTime start = LocalDateTime.of(2025, 4, 9, 9, 0);
LocalDateTime end = LocalDateTime.of(2025, 4, 9, 10, 0);
System.out.println(Duration.between(start, end)); // PT1H
~~~

This is the distance between two local date-time values. Because `LocalDateTime` has no offset or `ZoneId`, it cannot be guaranteed to always represent the actual elapsed time between two global events, especially near DST transitions.

### ZonedDateTime: Calendar Days May Not Be 24 Hours Long

~~~java
ZoneId newYork = ZoneId.of("America/New_York");
ZonedDateTime start =
        ZonedDateTime.of(2025, 3, 9, 0, 0, 0, 0, newYork);
ZonedDateTime end =
        ZonedDateTime.of(2025, 3, 10, 0, 0, 0, 0, newYork);
System.out.println(Duration.between(start, end)); // PT23H
~~~

Under current DST rules, March 9, 2025 in New York skips one hour when the clocks spring forward. The two midnights are 23 actual hours apart. In contrast, `Duration.ofDays(1)` is always 24 hours. If the goal is “the same time on the next calendar day”, add days with `LocalDate` and apply the `ZoneId` rather than adding a 24-hour Duration.

## 5. Duration, Period, and ChronoUnit

`Duration` measures seconds and nanoseconds. `Period` expresses calendar components in years, months, and days; `ChronoUnit` counts the number of units between values supported by the input type.

| API | Appropriate Question |
| --- | --- |
| `Duration.between(a,b)` | How much time has elapsed? |
| `Period.between(dateA,dateB)` | What is the distance in calendar years, months, and days? |
| `ChronoUnit.DAYS.between(a,b)` | How many days are between two dates? |
| `Duration.ofDays(1)` | Fixed 24-hour time span |

~~~java
LocalDate jan31 = LocalDate.of(2025, 1, 31);
LocalDate feb28 = LocalDate.of(2025, 2, 28);
System.out.println(Period.between(jan31, feb28)); // P28D
System.out.println(ChronoUnit.DAYS.between(jan31, feb28)); // 28
System.out.println(Duration.ofDays(1).toHours()); // 24
~~~

Do not use Duration for “one month” or “one year” because the number of days in a calendar interval varies. To measure the distance between two `LocalDate` values, use `Period` or `ChronoUnit.DAYS`; `LocalDate` does not provide the time fields required by Duration.

## 6. LocalTime Across Midnight

~~~java
LocalTime start = LocalTime.of(23, 30);
LocalTime end = LocalTime.of(1, 0);
System.out.println(Duration.between(start, end));
// PT-22H-30M
~~~

Java does not automatically know that `end` belongs to the next day. If this is a shift from 23:30 to 01:00 the next day, include the dates:

~~~java
LocalDateTime shiftStart = LocalDateTime.of(2025, 4, 9, 23, 30);
LocalDateTime shiftEnd = LocalDateTime.of(2025, 4, 10, 1, 0);
System.out.println(Duration.between(shiftStart, shiftEnd)); // PT1H30M
~~~

If the shift follows local time in a zone with DST, include `ZoneId` to calculate the actual elapsed duration; two standalone wall-clock times do not provide the date or zone rules.

## 7. Truncation, Arithmetic, and Precision

~~~java
Duration duration = Duration.ofSeconds(125, 123_000_000);
System.out.println(duration.toMinutes()); // 2
System.out.println(duration.toSeconds()); // 125
System.out.println(duration.toMillis()); // 125123
System.out.println(duration.truncatedTo(ChronoUnit.MINUTES)); // PT2M
~~~

`truncatedTo(ChronoUnit.MINUTES)` discards anything smaller than a minute without rounding up. If rounding is needed, you must explicitly define whether to round to nearest, always up, or always down, and handle negative values consistently. `toMillis()` loses sub-millisecond precision; converting very large durations can throw `ArithmeticException` if the result overflows the target numeric type.

Duration is immutable; arithmetic operations return a new object:

~~~java
Duration wait = Duration.ofSeconds(10);
System.out.println(wait.multipliedBy(2)); // PT20S
System.out.println(wait.dividedBy(2));    // PT5S
System.out.println(Duration.ofHours(2).plusMinutes(15)); // PT2H15M
~~~

## 8. Complete Java 17+ Example

Save the code as `DurationBetweenDemo.java`:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Period;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.time.temporal.ChronoUnit;

public class DurationBetweenDemo {
    public static void main(String[] args) {
        Instant start = Instant.parse("2025-04-09T09:00:00Z");
        Instant end = Instant.parse("2025-04-09T10:30:15.250Z");
        Duration duration = Duration.between(start, end);

        System.out.println("duration=" + duration);
        System.out.println("seconds=" + duration.getSeconds());
        System.out.println("nanos=" + duration.getNano());
        System.out.println("totalMillis=" + duration.toMillis());
        System.out.println("totalSeconds=" + duration.toSeconds());
        System.out.println("minutesPart=" + duration.toMinutesPart());
        System.out.println("secondsPart=" + duration.toSecondsPart());
        System.out.println("negative=" + Duration.between(end, start));
        System.out.println("plusDayHours=" + Duration.ofDays(1).toHours());

        LocalDate jan31 = LocalDate.of(2025, 1, 31);
        LocalDate feb28 = LocalDate.of(2025, 2, 28);
        System.out.println("period=" + Period.between(jan31, feb28));
        System.out.println("days=" + ChronoUnit.DAYS.between(jan31, feb28));

        ZoneId ny = ZoneId.of("America/New_York");
        ZonedDateTime springStart =
                ZonedDateTime.of(2025, 3, 9, 0, 0, 0, 0, ny);
        ZonedDateTime springEnd =
                ZonedDateTime.of(2025, 3, 10, 0, 0, 0, 0, ny);
        System.out.println("dstElapsed="
                + Duration.between(springStart, springEnd));

        System.out.println("div=" + Duration.ofSeconds(125).dividedBy(2));
        System.out.println("trunc="
                + Duration.ofSeconds(125, 123_000_000)
                        .truncatedTo(ChronoUnit.MINUTES));

        LocalDateTime localStart = LocalDateTime.of(2025, 4, 9, 9, 0);
        LocalDateTime localEnd = LocalDateTime.of(2025, 4, 9, 10, 0);
        System.out.println("betweenLocalDateTime="
                + Duration.between(localStart, localEnd));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac DurationBetweenDemo.java
java DurationBetweenDemo
~~~

Output with fixed data:

~~~text
duration=PT1H30M15.25S
seconds=5415
nanos=250000000
totalMillis=5415250
totalSeconds=5415
minutesPart=30
secondsPart=15
negative=PT-1H-30M-15.25S
plusDayHours=24
period=P28D
days=28
dstElapsed=PT23H
div=PT1M2.5S
trunc=PT2M
betweenLocalDateTime=PT1H
~~~

## 9. Common Mistakes

| Mistake | How to Handle |
| --- | --- |
| Swapping `start` and `end`, causing a negative Duration | Check the argument order; only take the absolute value if business logic requires it |
| Using `getSeconds()` as seconds within a minute | Use `toSecondsPart()` to get the seconds component |
| Using `toMillis()` when nanosecond precision is needed | Keep the Duration or use a unit with sufficient precision |
| Treating `Duration.ofDays(1)` as the next calendar day in a DST zone | Calculate the date with `LocalDate` and the zone with `ZoneId` |
| Using `LocalTime` to calculate a shift across midnight | Use `LocalDateTime` with start and end dates |
| Using Duration for calendar months or years | Choose `Period` or `ChronoUnit` |
| Calculating actual elapsed time from a `LocalDateTime` without a zone | Determine the offset/zone from the data source first |
| Treating nanosecond representation as clock accuracy | Distinguish between type resolution and time-source quality |

## 10. Self-Check

**Question 1.** What does `Duration.between(09:00Z, 10:30:15.250Z)` equal?

**Answer:** `PT1H30M15.25S`, which is 5,415.25 seconds.

**Question 2.** Why can swapping the order of arguments make a Duration negative?

**Answer:** The calculation is `end − start`, so swapping the order flips the sign.

**Question 3.** What does `Duration.ofDays(1).toHours()` return?

**Answer:** A fixed 24 hours, not the length of any calendar day in a DST zone.

**Question 4.** What should be used for the calendar interval from 2025-01-31 to 2025-02-28?

**Answer:** `Period` or `ChronoUnit.DAYS.between`, because both endpoints are dates without a time of day.

**Question 5.** How much actual time separates the two New York midnights around the March 2025 DST start date?

**Answer:** `PT23H` according to the time zone rules in the example.

**Question 6.** Do two `LocalTime` values `23:30` and `01:00` by themselves indicate a 90-minute shift?

**Answer:** No; the date is missing. Add the dates and calculate with `LocalDateTime`.

**Key Takeaway:** `Duration.between(start, end)` measures the duration **end minus start** in seconds and nanoseconds. Choose the right input type, check the sign and precision, and distinguish fixed durations from calendar-based intervals.
