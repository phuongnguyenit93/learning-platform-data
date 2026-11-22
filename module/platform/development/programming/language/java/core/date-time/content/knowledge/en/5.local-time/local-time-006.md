# LocalTime: Truncating Precision with truncatedTo()

In `java.time`, `LocalTime` describes a **time of day** with nanosecond precision, for example `14:37:59.987654321`. Sometimes we only want to keep information down to the minute, hour, or millisecond: for grouping data by time intervals, normalizing input, displaying a specific level of detail, or comparing two times at the same precision level.

The `LocalTime.truncatedTo(TemporalUnit unit)` method **removes time components smaller than the selected unit**, producing a `LocalTime` with the appropriate level of detail. This is a **truncation** operation, not rounding to the nearest unit.

Example:

~~~java
LocalTime time = LocalTime.of(14, 37, 59, 987_654_321);
LocalTime minute = time.truncatedTo(ChronoUnit.MINUTES);
// minute = 14:37, NOT 14:38
~~~

## 1. Exact Meaning of `truncatedTo()`

The word *truncate* in this context means discarding the part smaller than a chosen time unit, aligned to boundaries measured from the **start of the day**.

For `14:37:59.987654321`:

| Retained unit | `truncatedTo(...)` | Result | Discarded components |
|---|---|---|---|
| Nanosecond | `ChronoUnit.NANOS` | `14:37:59.987654321` | None |
| Microsecond | `ChronoUnit.MICROS` | `14:37:59.987654` | Last 321 nanoseconds |
| Millisecond | `ChronoUnit.MILLIS` | `14:37:59.987` | Last 654,321 nanoseconds |
| Second | `ChronoUnit.SECONDS` | `14:37:59` | Entire nanosecond fraction |
| Minute | `ChronoUnit.MINUTES` | `14:37` | Seconds and nanosecond fraction |
| Hour | `ChronoUnit.HOURS` | `14:00` | Minutes, seconds, and nanoseconds |
| Half-day | `ChronoUnit.HALF_DAYS` | `12:00` | Everything after the 12:00 mark |
| Day | `ChronoUnit.DAYS` | `00:00` | Entire time of day |

For example, `14:37:59` truncated to minutes gives `14:37`, **not bumping up** to `14:38` even though it has 59 seconds. Similarly, `23:59:59.999999999` truncated to days gives `00:00` **on the clock of the same day**, not 00:00 of the next day: `LocalTime` does not contain a date.

### Method and Parameter Type

Primary signature:

~~~java
public LocalTime truncatedTo(TemporalUnit unit)
~~~

In practice, we usually pass a constant from the `ChronoUnit` enum, such as `ChronoUnit.MINUTES` or `ChronoUnit.HOURS`. Required imports:

~~~java
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;
~~~

The return value is a **new `LocalTime` in terms of value**, with parts smaller than the chosen unit set to 0. Because `LocalTime` is *immutable*, the original object's value is not modified. Java may return the same reference when no change is needed; do not rely on `==` to check equality.

~~~java
LocalTime original = LocalTime.of(9, 12, 45);
LocalTime truncated = original.truncatedTo(ChronoUnit.MINUTES);

// original is still 09:12:45
// truncated is 09:12
~~~

If you want to update the variable, **reassign the result**:

~~~java
original = original.truncatedTo(ChronoUnit.MINUTES);
// original now holds 09:12
~~~

## 2. Common Truncation Levels

### Truncating to Seconds: `ChronoUnit.SECONDS`

~~~java
LocalTime time = LocalTime.of(8, 5, 42, 345_678_901);
LocalTime withoutFraction = time.truncatedTo(ChronoUnit.SECONDS);
// withoutFraction = 08:05:42
~~~

This operation discards the entire sub-second fraction (`getNano() == 0`), while keeping the hour, minute, and second intact.

### Truncating to Milliseconds or Microseconds

~~~java
LocalTime time = LocalTime.of(8, 5, 42, 345_678_901);
LocalTime millis = time.truncatedTo(ChronoUnit.MILLIS);
// millis = 08:05:42.345

LocalTime micros = time.truncatedTo(ChronoUnit.MICROS);
// micros = 08:05:42.345678
~~~

One second has 1,000 milliseconds, each millisecond has 1,000 microseconds, and each microsecond has 1,000 nanoseconds. Therefore:

- Truncating to milliseconds keeps the nanosecond-of-second part as a multiple of `1_000_000`.
- Truncating to microseconds keeps the nanosecond-of-second part as a multiple of `1_000`.
- Truncating to nanoseconds preserves the full maximum precision inherent to `LocalTime`.

`truncatedTo(ChronoUnit.NANOS)` does not create more precise data: it simply keeps the existing value unchanged.

### Truncating to Minutes or Hours

~~~java
LocalTime time = LocalTime.of(8, 5, 42, 345_678_901);

LocalTime toMinute = time.truncatedTo(ChronoUnit.MINUTES);
// 08:05

LocalTime toHour = time.truncatedTo(ChronoUnit.HOURS);
// 08:00
~~~

This is a common case when you want to group times into the same **minute mark** or **hour mark** within the day.

For example, the two times `08:05:01` and `08:05:59` both become `08:05` after truncating to minutes. They belong to the same minute on the clock, even though they are not the same exact instant.

### Truncating to Half-Days or Days

~~~java
LocalTime time = LocalTime.of(14, 37, 59, 987_654_321);

LocalTime halfDay = time.truncatedTo(ChronoUnit.HALF_DAYS);
// 12:00

LocalTime startOfDay = time.truncatedTo(ChronoUnit.DAYS);
// 00:00
~~~

`HALF_DAYS` divides the day into two 12-hour intervals: from `00:00` to before `12:00`, and from `12:00` to before `24:00`. Truncating to this unit produces either `00:00` or `12:00`.

`DAYS` always resets `LocalTime` to `00:00`; it does not create or return a `LocalDate`. This truncation is only useful if the business logic truly needs the start-of-day clock value.

## 3. Conditions for a Unit to Be Accepted

Not every `TemporalUnit` can be used with `LocalTime.truncatedTo()`. According to the Java contract, a valid truncation unit must have a **duration not exceeding a standard day and that duration must divide into a standard day (24 hours) without a remainder**, at nanosecond precision.

The following common `ChronoUnit` values are all valid:

~~~text
NANOS, MICROS, MILLIS, SECONDS, MINUTES, HOURS, HALF_DAYS, DAYS
~~~

Units such as `ChronoUnit.WEEKS` or `ChronoUnit.MONTHS` are **invalid** for this operation. A week is longer than 24 hours; a month also does not have a fixed length corresponding to an integer fraction of a standard day.

~~~java
LocalTime time = LocalTime.NOON;
time.truncatedTo(ChronoUnit.WEEKS);
// Throws java.time.temporal.UnsupportedTemporalTypeException
~~~

The snippet illustrates an error, not a complete program. `UnsupportedTemporalTypeException` is a subclass of `DateTimeException`. Passing `null` for `unit` throws a `NullPointerException`; you should pass a valid, explicit `ChronoUnit`.

**Note:** `Duration.ofMinutes(5)` is a `Duration` object, **not a `TemporalUnit`**. Therefore, you cannot call `time.truncatedTo(Duration.ofMinutes(5))`. When you want to create 5-minute or 15-minute boundaries, you can calculate by minutes since midnight or implement an appropriate `TemporalUnit`; see the 5-minute grouping example in the practical applications section.

## 4. Complete Example with Java 17

Create the file **`LocalTimeTruncationDemo.java`**:

~~~java
import java.time.DateTimeException;
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;

public class LocalTimeTruncationDemo {
    public static void main(String[] args) {
        LocalTime original = LocalTime.of(14, 37, 59, 987_654_321);
        System.out.println("original       = " + original);
        System.out.println("nanos          = "
                + original.truncatedTo(ChronoUnit.NANOS));
        System.out.println("micros         = "
                + original.truncatedTo(ChronoUnit.MICROS));
        System.out.println("millis         = "
                + original.truncatedTo(ChronoUnit.MILLIS));
        System.out.println("seconds        = "
                + original.truncatedTo(ChronoUnit.SECONDS));
        System.out.println("minutes        = "
                + original.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("hours          = "
                + original.truncatedTo(ChronoUnit.HOURS));
        System.out.println("half days      = "
                + original.truncatedTo(ChronoUnit.HALF_DAYS));
        System.out.println("days           = "
                + original.truncatedTo(ChronoUnit.DAYS));
        System.out.println("original again = " + original);

        LocalTime nearMidnight = LocalTime.of(23, 59, 59, 999_999_999);
        System.out.println("late minute    = "
                + nearMidnight.truncatedTo(ChronoUnit.MINUTES));
        System.out.println("late day       = "
                + nearMidnight.truncatedTo(ChronoUnit.DAYS));
        System.out.println("already exact  = "
                + LocalTime.of(14, 37).truncatedTo(ChronoUnit.MINUTES));

        try {
            original.truncatedTo(ChronoUnit.WEEKS);
        } catch (DateTimeException exception) {
            System.out.println("weeks rejected = "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run from the directory containing the file, using JDK 17 or later:

~~~bash
javac LocalTimeTruncationDemo.java
java LocalTimeTruncationDemo
~~~

Actual output verified with `javac --release 17`:

~~~text
original       = 14:37:59.987654321
nanos          = 14:37:59.987654321
micros         = 14:37:59.987654
millis         = 14:37:59.987
seconds        = 14:37:59
minutes        = 14:37
hours          = 14:00
half days      = 12:00
days           = 00:00
original again = 14:37:59.987654321
late minute    = 23:59
late day       = 00:00
already exact  = 14:37
weeks rejected = UnsupportedTemporalTypeException
~~~

**Explanation:**

1. `original` still holds `14:37:59.987654321` after all truncations; the object is immutable.
2. Reducing precision from nanoseconds to microseconds/milliseconds only discards the lower part without rounding.
3. Truncating to minutes, hours, or half-days produces `14:37`, `14:00`, and `12:00`.
4. Truncating to `DAYS` returns `00:00`, even from a time near the end of the day; `LocalTime` never rolls over to the next day.
5. A value already exact to the minute (`14:37`) remains unchanged in content.
6. Truncating to weeks is rejected with a clear temporal exception.

## 5. Practical Applications

### Grouping Values by Minute

Suppose you have times recorded by a measuring device on the **same calendar day**:

~~~java
LocalTime first = LocalTime.of(10, 25, 3);
LocalTime second = LocalTime.of(10, 25, 58);

LocalTime firstBucket = first.truncatedTo(ChronoUnit.MINUTES);
LocalTime secondBucket = second.truncatedTo(ChronoUnit.MINUTES);

boolean sameMinute = firstBucket.equals(secondBucket); // true
~~~

This creates a **grouping key** by minute of the day. If you need to group events spanning multiple days, a key consisting only of `LocalTime` will mix up `10:25` today with `10:25` tomorrow. In that case, also keep `LocalDate` or work with a type that has full date/instant information.

### Normalizing Appointment Times Accepted Only to the Minute

For example, the input is `09:15:42.500` but the convention is to store appointment times to the minute:

~~~java
LocalTime submitted = LocalTime.of(9, 15, 42, 500_000_000);
LocalTime minutePrecision = submitted.truncatedTo(ChronoUnit.MINUTES);
// minutePrecision = 09:15
~~~

This **intentionally alters the value**: the seconds/nanoseconds part is discarded and cannot be recovered from `minutePrecision` alone. If the business requirement calls for "rounding to the nearest minute", this is not the right API; you must clearly define the rounding rule (especially at `23:59:59`) and handle the date as well when crossing midnight.

### Grouping by 5-Minute Intervals

`truncatedTo(ChronoUnit.MINUTES)` only works with single-minute units and cannot directly specify "5 minutes". Because `LocalTime` falls within a single day, you can compute the number of seconds since 00:00 to divide into intervals:

~~~java
LocalTime time = LocalTime.of(10, 27, 49);
int secondsPerBucket = 5 * 60;
int startSecond = (time.toSecondOfDay() / secondsPerBucket)
        * secondsPerBucket;
LocalTime bucket = LocalTime.ofSecondOfDay(startSecond);
// bucket = 10:25
~~~

This is an **illustrative snippet inside a method**, not a standalone runnable Java file. For a time of day, `toSecondOfDay()` is in the range 0–86,399, so integer division finds the nearest 5-minute boundary **not exceeding the input time**. The nanosecond part is naturally discarded. When you need to group real events spanning multiple days, include date/time-zone information before designing the grouping key.

### Truncating Values and Formatting for Display Are Two Different Operations

If you only want to **display** `14:37` while still **keeping the original seconds/nanoseconds data**, use formatting:

~~~java
import java.time.format.DateTimeFormatter;

// Illustration inside a method, where the time variable already exists:
String displayed = time.format(DateTimeFormatter.ofPattern("HH:mm"));
~~~

The resulting string may be `14:37`, yet the `time` object retains its original precision. Conversely, `truncatedTo(ChronoUnit.MINUTES)` returns a time value whose sub-minute data has been discarded. Choose the approach based on the requirement: **display only** or **modifying the value to be processed/stored**.

## 6. Important Limitations and Common Pitfalls

| Misconception | Why it is wrong | Correct approach |
|---|---|---|
| Thinking truncating to minutes rounds to the nearest minute | `14:37:59` becomes `14:37`, not `14:38` | If rounding is desired, design a separate rounding operation |
| Calling `time.truncatedTo(...)` and ignoring the result | `LocalTime` is immutable; the original object does not change | Assign `LocalTime result = ...` or reassign the variable |
| Using `ChronoUnit.MINUTE` or `ChronoUnit.HOUR` | Enum constants are plural | Use `ChronoUnit.MINUTES`, `ChronoUnit.HOURS` |
| Calling `truncatedTo(Duration.ofMinutes(5))` | `Duration` does not implement `TemporalUnit` | Use a supported `ChronoUnit` or compute bucket boundaries |
| Using `WEEKS`/`MONTHS` | Does not satisfy the constraint of dividing a standard day evenly | Only pass valid units |
| Thinking `truncatedTo(DAYS)` advances to the next day | `LocalTime` only holds time of day, so the result is `00:00` | If the date matters, use a date-bearing type and apply date-rollover logic |
| Using `==` to compare results | Should not rely on reference identity | Use `equals(...)` when comparing `LocalTime` values |
| Treating `LocalTime` as an actual timestamp | Has no date and no time zone | Use `LocalDateTime`/`ZonedDateTime`/`Instant` as appropriate for the context |
| Truncating data when you only want `HH:mm` formatting | Truncation changes the internal represented value | Use `DateTimeFormatter` if you only need presentation |
| Assuming truncation preserves the original data in the result | Parts smaller than the selected unit are lost | Keep the `original` variable if you still need the full time |

**Limitation of the time-of-day context:** `LocalTime` has no awareness of Daylight Saving Time (DST), time zones, or dates. `LocalTime.truncatedTo()` divides according to a **standard 24-hour day**. In reality, days in some time zones can be 23 or 25 hours long due to clock changes; if a system groups events by actual elapsed hours or across multiple local calendar days, choose `Instant`/`ZonedDateTime` and appropriate grouping rules instead of simply truncating `LocalTime`.

## 7. Self-Check Questions

1. What is `LocalTime.of(16, 28, 59).truncatedTo(ChronoUnit.MINUTES)`? **`16:28`**, not `16:29`.
2. What is `LocalTime.of(16, 28, 59, 123_456_789).truncatedTo(ChronoUnit.MILLIS)`? **`16:28:59.123`**.
3. Does truncating `LocalTime.of(23, 59, 59)` to `DAYS` automatically roll over to tomorrow? **No**; the result is `00:00` with no date attached.
4. What does truncating `06:45:00` to `HOURS` return? **`06:00`**.
5. What does `LocalTime.of(13, 0).truncatedTo(ChronoUnit.HALF_DAYS)` return? **`12:00`**.
6. Can `ChronoUnit.WEEKS` be passed to `LocalTime.truncatedTo()`? **No**, it will be rejected with `UnsupportedTemporalTypeException`.
7. What should you use if you want to keep the original time `10:25:48` but only display `10:25`? **`DateTimeFormatter`**; there is no need to truncate and lose data.
8. Do two records at `10:25` on two different days have the same key after truncating `LocalTime` to minutes? **Yes**, so you must include the **date** if the business logic needs to distinguish the two records.

**Key takeaway:** `LocalTime.truncatedTo(ChronoUnit.MINUTES)` discards seconds and nanoseconds, and `truncatedTo(ChronoUnit.HOURS)` discards minutes, seconds, and nanoseconds; every truncation **does not round** and **does not mutate the original object**. Choose the appropriate unit and distinguish between time of day and an instant/timestamp with a date and time zone.

### References

- [Java SE 17 — LocalTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/LocalTime.html)
- [Java SE 17 — ChronoUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/ChronoUnit.html)
- [Java SE 17 — TemporalUnit](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/temporal/TemporalUnit.html)
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html)
