# Converting Seconds or Nanoseconds Since Start of Day with LocalTime

In Java, `LocalTime` describes a **time of day**: hour, minute, second, and nanosecond-of-second. When working with a counter of **seconds since 00:00** (*second of day*) or **nanoseconds since 00:00** (*nano of day*), you can convert directly between integers and `LocalTime` without manually splitting or assembling individual hour–minute–second components.

This lesson focuses on the four corresponding methods of `java.time.LocalTime`:

- `LocalTime.ofSecondOfDay(long)`: seconds since start of day → `LocalTime`.
- `LocalTime.ofNanoOfDay(long)`: nanoseconds since start of day → `LocalTime`.
- `localTime.toSecondOfDay()`: `LocalTime` → whole seconds since start of day.
- `localTime.toNanoOfDay()`: `LocalTime` → total nanoseconds since start of day.

These conversions operate on **wall-clock time of day**, containing no calendar date, time zone, UTC instant, or multi-day duration.

## 1. Understanding “Since Start of Day”

The start-of-day reference point is **00:00:00.000000000**. From this point, each second or nanosecond corresponds to a position within the 24-hour range under the `LocalTime` model.

One minute has **60 seconds**, one hour has **3,600 seconds**, and one day in the `LocalTime` local-time model has **86,400 nominal seconds**. One second has **1,000,000,000 nanoseconds**.

| Time | Seconds Since Start of Day | Nanoseconds Since Start of Day |
| --- | ---: | ---: |
| `00:00:00` | 0 | 0 |
| `00:00:01` | 1 | 1,000,000,000 |
| `00:01:00` | 60 | 60,000,000,000 |
| `01:00:00` | 3,600 | 3,600,000,000,000 |
| `12:00:00` | 43,200 | 43,200,000,000,000 |
| `12:34:56` | 45,296 | 45,296,000,000,000 |
| `12:34:56.123456789` | 45,296 | 45,296,123,456,789 |
| `23:59:59` | 86,399 | 86,399,000,000,000 |
| `23:59:59.999999999` | 86,399 | 86,399,999,999,999 |

**Note:** `86_400` is the total **number of seconds in a full 24-hour day**, and is also an **out-of-range value** for the second-of-day index. `86_400` seconds after 00:00 is 00:00 **of the next day**, not a `LocalTime` value within the current day. For nanoseconds, `86_400_000_000_000L` is likewise an *exclusive* upper bound.

## 2. Conversion APIs and Value Ranges

| Direction | API | Numeric Type | Valid Range or Result |
| --- | --- | --- | --- |
| Seconds → time | `LocalTime.ofSecondOfDay(long secondOfDay)` | `long` | **0 to 86,399**, inclusive |
| Nanoseconds → time | `LocalTime.ofNanoOfDay(long nanoOfDay)` | `long` | **0 to 86,399,999,999,999**, inclusive |
| Time → seconds | `time.toSecondOfDay()` | Returns `int` | 0 to 86,399 |
| Time → nanoseconds | `time.toNanoOfDay()` | Returns `long` | 0 to 86,399,999,999,999 |

The two `of…` methods are **static** factory methods for creating `LocalTime`. The two `to…` methods are **instance** methods called on an existing `LocalTime` object.

### Creating a Time from Seconds Since 00:00

```java
import java.time.LocalTime;

LocalTime midnight = LocalTime.ofSecondOfDay(0);       // 00:00
LocalTime noon = LocalTime.ofSecondOfDay(43_200);      // 12:00
LocalTime example = LocalTime.ofSecondOfDay(45_296);   // 12:34:56
LocalTime lastSecond = LocalTime.ofSecondOfDay(86_399); // 23:59:59
```

This is an **illustrative snippet** and must be placed inside a Java method. Because the input only provides whole seconds, the resulting time has **nanosecond-of-second equal to 0**. If you need to preserve sub-second fractions, use `ofNanoOfDay`.

### Creating a Time from Nanoseconds Since 00:00

```java
import java.time.LocalTime;

LocalTime precise = LocalTime.ofNanoOfDay(45_296_123_456_789L);
// 12:34:56.123456789

LocalTime lastNano = LocalTime.ofNanoOfDay(86_399_999_999_999L);
// 23:59:59.999999999
```

The `L` suffix on long integer literals ensures the `long` type. Nanosecond-of-day values exceed the `int` range, so you must not store them in an `int` variable or perform nanosecond multiplications using 32-bit integers.

### Getting Seconds or Nanoseconds from `LocalTime`

```java
import java.time.LocalTime;

LocalTime time = LocalTime.of(12, 34, 56, 123_456_789);

int secondOfDay = time.toSecondOfDay(); // 45296
long nanoOfDay = time.toNanoOfDay();    // 45296123456789
```

`toSecondOfDay()` returns **the number of completed seconds since the start of the day**. For `12:34:56.123456789`, the value is **45,296**, **without rounding up** to 45,297. The `123_456_789` nanoseconds remain in the original `LocalTime`, but are discarded in the **returned `int` value**. `toNanoOfDay()` preserves full nanosecond precision.

## 3. Formulas for Understanding the Result

With `hour` in 0–23, `minute` in 0–59, and `second` in 0–59:

```text
secondOfDay = hour × 3600 + minute × 60 + second
nanoOfDay   = secondOfDay × 1_000_000_000 + nanoOfSecond
```

Where `nanoOfSecond` is an integer from 0 to 999,999,999, representing the sub-second fraction. For example, at `12:34:56.123456789`:

```text
secondOfDay = 12 × 3600 + 34 × 60 + 56
            = 43_200 + 2_040 + 56
            = 45_296

nanoOfDay   = 45_296 × 1_000_000_000 + 123_456_789
            = 45_296_123_456_789
```

If you need to manually decode a **validated** second value, you can use integer division and remainder:

```java
long totalSeconds = 45_296L;
long hour = totalSeconds / 3_600;         // 12
long minute = (totalSeconds % 3_600) / 60; // 34
long second = totalSeconds % 60;         // 56
```

This is an illustrative snippet for learning the formula. In production code, prefer `LocalTime.ofSecondOfDay(totalSeconds)` so Java handles boundary checks and conversion. For nanoseconds, first extract whole seconds by dividing by `1_000_000_000L`, then get the nanosecond-of-second using remainder modulo `1_000_000_000L`.

Avoid computing `hour * 3_600_000_000_000` with `int` arithmetic because it can overflow **before being assigned to `long`**. If you must compute it manually, use `long` literals/variables and prefer `Math.addExact` / `Math.multiplyExact` when inputs might exceed numeric bounds. For a valid `LocalTime`, `toNanoOfDay()` already computes accurately and fits within `long`.

## 4. Complete Runnable Java 17+ Example

Save the file as **`LocalTimeDayUnitsDemo.java`**:

```java
import java.time.DateTimeException;
import java.time.LocalTime;
import java.time.temporal.ChronoUnit;

public class LocalTimeDayUnitsDemo {
    public static void main(String[] args) {
        long secondOfDay = 45_296L;
        long nanoOfDay = 45_296_123_456_789L;

        LocalTime wholeSecond = LocalTime.ofSecondOfDay(secondOfDay);
        LocalTime fractional = LocalTime.ofNanoOfDay(nanoOfDay);

        System.out.println("From seconds: " + wholeSecond);
        System.out.println("From nanos: " + fractional);
        System.out.println("Second of day: " + fractional.toSecondOfDay());
        System.out.println("Nano of day: " + fractional.toNanoOfDay());
        System.out.println("Round trip seconds: "
                + LocalTime.ofSecondOfDay(fractional.toSecondOfDay()));
        System.out.println("Truncate to seconds: "
                + fractional.truncatedTo(ChronoUnit.SECONDS));
        System.out.println("Start of day: " + LocalTime.ofSecondOfDay(0));
        System.out.println("Last second: " + LocalTime.ofSecondOfDay(86_399));
        System.out.println("Last nanosecond: "
                + LocalTime.ofNanoOfDay(86_399_999_999_999L));
        printValidation("seconds=86400", () -> LocalTime.ofSecondOfDay(86_400));
        printValidation("nanos=-1", () -> LocalTime.ofNanoOfDay(-1));
    }

    private static void printValidation(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": VALID");
        } catch (DateTimeException ex) {
            System.out.println(label + ": INVALID");
        }
    }
}
```

Compile and run:

```bash
javac LocalTimeDayUnitsDemo.java
java LocalTimeDayUnitsDemo
```

**Exact stdout** (verified with `javac --release 17` and `java`):

```text
From seconds: 12:34:56
From nanos: 12:34:56.123456789
Second of day: 45296
Nano of day: 45296123456789
Round trip seconds: 12:34:56
Truncate to seconds: 12:34:56
Start of day: 00:00
Last second: 23:59:59
Last nanosecond: 23:59:59.999999999
seconds=86400: INVALID
nanos=-1: INVALID
```

Key observations:

1. `ofSecondOfDay(45_296)` constructs `12:34:56` with no nanosecond part.
2. `ofNanoOfDay(45_296_123_456_789L)` constructs `12:34:56.123456789`.
3. `fractional.toSecondOfDay()` returns `45296`, without the nanosecond part; `toNanoOfDay()` preserves the full `45296123456789`.
4. `LocalTime.ofSecondOfDay(fractional.toSecondOfDay())` returns to the **whole-second** mark, dropping `.123456789`.
5. Inputs of `86400` seconds or `-1` nanoseconds are rejected with `DateTimeException`. The example catches the exception only to print a simple label; production code should handle it according to the input contract.

## 5. Precision and Round-Trip Conversion

A **round trip** conversion converts an object to a number and back to an object.

### Round Trip via Nanoseconds: Preserves the Full Time

```java
LocalTime original = LocalTime.of(12, 34, 56, 123_456_789);
long nanos = original.toNanoOfDay();
LocalTime restored = LocalTime.ofNanoOfDay(nanos);

System.out.println(original.equals(restored)); // true
```

This snippet requires importing `java.time.LocalTime`. For every valid `LocalTime`, the `toNanoOfDay` → `ofNanoOfDay` pair restores the value **exact to the nanosecond**.

### Round Trip via Seconds: May Lose Sub-Second Fractions

```java
LocalTime original = LocalTime.of(12, 34, 56, 123_456_789);
int seconds = original.toSecondOfDay();
LocalTime restored = LocalTime.ofSecondOfDay(seconds);

System.out.println(original.equals(restored)); // false
System.out.println(restored);                  // 12:34:56
```

This snippet requires importing `java.time.LocalTime`. This case **does not round**; it discards the entire nanosecond part. `toSecondOfDay` is suitable for rules that only require hours–minutes–seconds; it is unsuitable if you must store and restore times with millisecond/microsecond/nanosecond precision.

To make the intent to drop sub-second fractions explicit, you can call `time.truncatedTo(ChronoUnit.SECONDS)` before comparing or persisting data. Do not confuse **truncation** with time-zone conversion or rounding up to the next second.

### Milliseconds, Microseconds, and Nanoseconds

Some external systems use milliseconds or microseconds since start of day. These are **not** the units `ofNanoOfDay` accepts directly:

| Source Unit | Multiplier to Nanoseconds | Example |
| --- | ---: | --- |
| Second | `1_000_000_000L` | 1 second → 1,000,000,000 nanos |
| Millisecond | `1_000_000L` | 1 millisecond → 1,000,000 nanos |
| Microsecond | `1_000L` | 1 microsecond → 1,000 nanos |
| Nanosecond | `1L` | Unchanged |

**Correct** example when the input is 12:34:56.123, corresponding to 45,296,123 milliseconds since start of day:

```java
long millisOfDay = 45_296_123L;
long nanosOfDay = Math.multiplyExact(millisOfDay, 1_000_000L);
LocalTime fromMillis = LocalTime.ofNanoOfDay(nanosOfDay);
// 12:34:56.123
```

This snippet requires importing `java.time.LocalTime`. `Math.multiplyExact` throws `ArithmeticException` if the multiplication overflows `long`; `ofNanoOfDay` still validates that the value falls within the nanosecond-of-day range. If the source data contains fractions smaller than the stored unit, converting to whole seconds/milliseconds loses information that cannot be recovered by multiplying back.

## 6. Bounds from 0 to Before 24:00 and Handling Invalid Values

`LocalTime` supports values from **00:00:00.000000000** to **23:59:59.999999999**. There is no `24:00` as a distinct `LocalTime`, and there are no negative indices.

```java
LocalTime.ofSecondOfDay(0);                   // valid
LocalTime.ofSecondOfDay(86_399);              // valid
LocalTime.ofNanoOfDay(0L);                    // valid
LocalTime.ofNanoOfDay(86_399_999_999_999L);   // valid

LocalTime.ofSecondOfDay(-1);                  // DateTimeException
LocalTime.ofSecondOfDay(86_400);              // DateTimeException
LocalTime.ofNanoOfDay(-1L);                   // DateTimeException
LocalTime.ofNanoOfDay(86_400_000_000_000L);  // DateTimeException
```

These are **illustrative calls**; the last four lines intentionally trigger errors and must not be executed sequentially without exception handling in a program that needs to continue running. If you need to reject inputs before calling the API, the rule is:

```java
boolean validSeconds = seconds >= 0 && seconds < 86_400L;
boolean validNanos = nanos >= 0 && nanos < 86_400_000_000_000L;
```

The variables `seconds` and `nanos` are assumed to be declared as `long`. In most cases, simply call the API and handle `DateTimeException` according to your contract rather than writing a parallel validation mechanism.

### When Should Out-of-Day Values Be Normalized?

Some device-control or wrap-around clock problems treat second `86_400` as equivalent to `00:00`, or `-1` as equivalent to `23:59:59`. **This is an intentional normalization policy**, distinct from data validation:

```java
long rawSeconds = -1L;
long normalized = Math.floorMod(rawSeconds, 86_400L); // 86399
LocalTime wrapped = LocalTime.ofSecondOfDay(normalized);
// 23:59:59
```

`Math.floorMod` produces a non-negative result when the divisor is positive, unlike the `%` remainder operator which can be negative for negative dividends. Normalization discards information about **how many days have elapsed**. If `rawSeconds` represents an actual elapsed duration from a reference point, use `Duration` or combine `LocalDate`/`LocalDateTime` with time addition; **do not silently wrap out-of-range inputs into valid times** if the business logic does not call for it.

Similarly, you can use `Math.floorMod(rawNanos, 86_400_000_000_000L)` when a nanosecond-precision wrap-around clock is explicitly required. For data validation problems, reject out-of-range numbers.

## 7. Distinguishing Second of Day, Unix Seconds, and Durations

The following three representations are **different** even though all use “seconds” as their unit:

| Concept | Example | Meaning |
| --- | --- | --- |
| `second of day` | `45_296` | Position 12:34:56 within a day according to `LocalTime` |
| `epoch second` | `Instant.getEpochSecond()` | Seconds on the Unix/Java scale since 1970-01-01T00:00:00Z |
| `Duration` | `Duration.ofSeconds(45_296)` | Length of a time span, which may span multiple days or be negative |

`LocalTime.ofSecondOfDay` **must not be used** with arbitrary Unix seconds or `Duration` values. Unix seconds typically exceed 86,399 and will throw `DateTimeException`, and even if a value happens to fall within range, it does not mean the intended “seconds since start of day”.

If you have an **epoch second** and need the local time, create an `Instant` and convert it using a time zone:

```java
long epochSecond = 1_709_251_200L;
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalTime localTime = Instant.ofEpochSecond(epochSecond)
        .atZone(zone)
        .toLocalTime();
```

This snippet requires importing `java.time.*`. When converting from an absolute instant to a time of day, **`ZoneId` is required to determine the local time**. Meanwhile, `LocalTime` itself has no knowledge of the date, UTC time, offset, or time zone of the value it holds.

## 8. Calendar, DST, and Leap Second Notes

`LocalTime` is **wall-clock time in a nominal 24-hour day**, not a measure of the actual seconds elapsed since midnight everywhere in the world.

- In regions with Daylight Saving Time (DST), a local day may be only **23 hours** or **25 hours** long in real elapsed time. Therefore, `toSecondOfDay()` cannot be used to always compute the exact real seconds elapsed since that day's midnight.
- During a DST transition, a local time may **not exist** or may **occur twice**; `LocalTime.ofSecondOfDay` can still construct that time because `LocalTime` itself has no date or zone to check DST rules.
- `LocalTime` has seconds from 0 to 59; it does not directly represent a leap second `23:59:60` as a `second=60` component.

When you need the actual elapsed duration from midnight in a specific zone and date, combine `LocalDate` and `ZoneId` and work with `ZonedDateTime` / `Instant`:

```java
LocalDate date = LocalDate.of(2024, 3, 10);
ZoneId zone = ZoneId.of("America/New_York");

Instant start = date.atStartOfDay(zone).toInstant();
Instant nextStart = date.plusDays(1).atStartOfDay(zone).toInstant();

long actualSeconds = Duration.between(start, nextStart).getSeconds();
// 82800 (23 hours) on the DST start day in New York in 2024
```

This snippet requires importing `java.time.*`. The `86_400` nominal seconds of `LocalTime` remain valid as **time-of-day coordinates**; the `82_800` seconds in the example is the **actual duration between two midnights**. Distinguishing these two measurements is critical when calculating shifts, hourly billing, or uptime.

## 9. Choosing a Representation for Input, Storage, and Transmission

When data represents a **time of day** (for example, a service counter opens at 09:30), `LocalTime` is the right type. If an external protocol uses “seconds since start of day”, convert at the system boundary:

```java
int openingSeconds = LocalTime.of(9, 30).toSecondOfDay(); // 34200
LocalTime opening = LocalTime.ofSecondOfDay(openingSeconds); // 09:30
```

If the protocol requires nanosecond precision, use `long` with `toNanoOfDay` / `ofNanoOfDay`. If only milliseconds are needed, agree explicitly on field names and units (such as `millisOfDay`), because mistaking milliseconds for nanoseconds shifts the time of day by orders of magnitude.

If you need **the instant when a specific event occurred** (for example, delivered at 09:30 on which date, in which time zone), `LocalTime` alone is **insufficient**. Include date and zone information or store an `Instant`. If you need to accumulate multi-day durations, choose `Duration` instead of `LocalTime`: a wall-clock time wraps past midnight without tracking the number of days.

## 10. Common Pitfalls and How to Avoid Them

1. **Allowing exactly 86,400 seconds or 86,400,000,000,000 nanoseconds as input.** This is an exclusive upper bound; the last valid value is 86,399 seconds or 86,399,999,999,999 nanoseconds.
2. **Assuming `toSecondOfDay()` rounds.** It drops the nanosecond part of the second, so `12:34:56.999999999` still returns 45,296.
3. **Storing nanoseconds in `int`.** Values can exceed 86 trillion; use `long` and the `L` literal suffix when needed.
4. **Confusing “nanosecond of second” with “nanosecond of day”.** `time.getNano()` only returns the nanosecond part from 0–999,999,999; `time.toNanoOfDay()` returns the total since 00:00.
5. **Confusing Unix seconds with seconds of day.** For timestamps, go through `Instant` and `ZoneId` first.
6. **Using a fixed number of seconds to infer the actual duration of every local day.** DST can make the actual day different from 24 hours; use `ZonedDateTime` or `Instant` for actual duration calculations.
7. **Performing manual integer multiplication/division without checking for overflow.** Perform arithmetic in `long` or call the built-in API directly.
8. **Automatically applying `floorMod` to all invalid inputs.** Only do so when the problem is defined as a wrap-around clock; for data requiring validation, reject invalid values.
9. **Expecting `LocalTime` to hold a date or time zone.** `LocalTime` carries no such context; use a more appropriate type when the data requires it.

## 11. Testing Checklist

| Case | Input | Expected Result |
| --- | --- | --- |
| First second of day | `ofSecondOfDay(0)` | `00:00` |
| Last second of day | `ofSecondOfDay(86_399)` | `23:59:59` |
| Second above upper bound | `ofSecondOfDay(86_400)` | `DateTimeException` |
| Negative second | `ofSecondOfDay(-1)` | `DateTimeException` |
| First nanosecond of day | `ofNanoOfDay(0)` | `00:00` |
| Last nanosecond of day | `ofNanoOfDay(86_399_999_999_999L)` | `23:59:59.999999999` |
| Nanosecond above upper bound | `ofNanoOfDay(86_400_000_000_000L)` | `DateTimeException` |
| Negative nanosecond | `ofNanoOfDay(-1L)` | `DateTimeException` |
| Get seconds from fractional time | `12:34:56.123456789` | `toSecondOfDay() == 45296` |
| Get nanos from fractional time | `12:34:56.123456789` | `toNanoOfDay() == 45296123456789L` |
| Nano round trip | `ofNanoOfDay(time.toNanoOfDay())` | Equal to original `time` |
| Second round trip | `ofSecondOfDay(time.toSecondOfDay())` | Equal to `time` when `getNano()==0`; loses fraction if nanos present |

In JUnit 5, you can use `assertEquals` to check converted values and `assertThrows(DateTimeException.class, () -> LocalTime.ofSecondOfDay(86_400))` to validate input bounds. For round-trip tests, cover multiple times including 00:00, 12:00, near end of day, and times with non-zero nanoseconds.

## 12. API Quick Reference

| Need | Appropriate API |
| --- | --- |
| Seconds in a day → time | `LocalTime.ofSecondOfDay(long)` |
| Nanoseconds in a day → time | `LocalTime.ofNanoOfDay(long)` |
| Time → whole seconds since start of day | `LocalTime.toSecondOfDay()` |
| Time → total nanoseconds since start of day | `LocalTime.toNanoOfDay()` |
| Intentionally drop sub-second fraction | `LocalTime.truncatedTo(ChronoUnit.SECONDS)` |
| Intentionally normalize wrap-around clock | `Math.floorMod(raw, 86_400L)` before creating time |
| Convert absolute timestamp to time in zone | `Instant.atZone(zone).toLocalTime()` |
| Measure actual duration between two instants | `Duration.between(instant1, instant2)` |

**Core principle:** `ofSecondOfDay`/`toSecondOfDay` use **whole seconds**; `ofNanoOfDay`/`toNanoOfDay` use **nanoseconds** and preserve higher precision. Validate the range **0 to before 24:00**, choose `long` for nanoseconds, and always distinguish **time of day** from **absolute instants** or **actual durations**.
