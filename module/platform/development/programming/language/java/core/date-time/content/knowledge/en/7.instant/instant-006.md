# Adding and Subtracting Durations and Supported Units in Java `Instant`

An order is created at `2025-01-15T10:00:00Z` and will expire **after 90 minutes**. The system needs to calculate **a new timestamp** on the real timeline without choosing a local time zone:

```java
Instant createdAt = Instant.parse("2025-01-15T10:00:00Z");
Instant expiresAt = createdAt.plus(Duration.ofMinutes(90));
// expiresAt = 2025-01-15T11:30:00Z
```

This snippet belongs inside a Java method and requires `import java.time.*;`. In Java 8+, `Instant` represents an absolute point in time as seconds from the epoch plus a nanosecond part. `Duration` represents an elapsed amount of real time. The `plus(...)` and `minus(...)` operations shift an `Instant` by an elapsed duration and return a **new object** because `Instant` is immutable.

There are three different questions to clarify before choosing a calculation:

- **After exactly 90 minutes or 24 hours?** Add a `Duration` or an amount in a unit supported by `Instant`.
- **At the same local time tomorrow or next month?** Apply calendar rules on `ZonedDateTime` with a specific `ZoneId`; do not assume you can add a fixed number of seconds.
- **How much time is between two points in time?** Use `Duration.between(start, end)` or `ChronoUnit.between(...)` to measure the difference.

## 1. The `Instant` Model and the Meaning of Addition/Subtraction

The value `Instant.parse("2025-01-15T10:00:00Z")` points to a single moment in time. The `Z` symbol indicates the string is represented in UTC. Anywhere in the world can interpret this same point in time, even though the local display time differs.

```text
Initial instant: 2025-01-15T10:00:00Z
                   │
              +90 minutes
                   ↓
New instant:     2025-01-15T11:30:00Z
```

`Instant` has representation precision down to **nanoseconds**. Addition/subtraction on `Instant` does not automatically account for DST, end of month, or business days. If you add "1 day" using `ChronoUnit.DAYS`, Java adds **86,400 seconds**, which is exactly 24 hours; this is a **duration-based day**, not necessarily a calendar day in a region with daylight saving time.

Every `plus`/`minus` method returns a new `Instant`:

```java
Instant start = Instant.parse("2025-01-15T10:00:00Z");
Instant later = start.plusSeconds(30);
// start is still 2025-01-15T10:00:00Z
// later is 2025-01-15T10:00:30Z
```

Calling `start.plusSeconds(30);` without assigning the result will not modify `start`.

## 2. Duration Addition Methods

### Adding Seconds, Milliseconds, or Nanoseconds Directly

`Instant` provides convenience methods:

| Method | Unit | Example |
| --- | --- | --- |
| `plusSeconds(long seconds)` | Seconds | `instant.plusSeconds(90)` adds 1 minute and 30 seconds. |
| `plusMillis(long millis)` | Milliseconds | `instant.plusMillis(1_500)` adds 1.5 seconds. |
| `plusNanos(long nanos)` | Nanoseconds | `instant.plusNanos(1_000_000)` adds 1 millisecond. |

Unit relationships: 1 second = 1,000 milliseconds = 1,000,000 microseconds = 1,000,000,000 nanoseconds. Do not pass a millisecond value to `plusNanos` without converting it.

Example:

```java
Instant base = Instant.parse("2025-01-15T10:00:00Z");

Instant a = base.plusSeconds(3_600); // 11:00:00Z
Instant b = base.plusMillis(1_500);  // 10:00:01.500Z
Instant c = base.plusNanos(1);       // 10:00:00.000000001Z
```

This is an illustrative snippet inside a method and requires `import java.time.Instant;`. Parameter values can be negative—for example, `plusSeconds(-30)` is equivalent to subtracting 30 seconds—but you should choose `minusSeconds(30)` when the intent is subtraction to keep the code easy to understand.

### Adding a `Duration`

`Duration` is the appropriate type when the elapsed time is computed, configured, or passed between classes:

```java
Duration retention = Duration.ofHours(2).plusMinutes(30);
Instant deadline = base.plus(retention);
// deadline = 2025-01-15T12:30:00Z
```

`plus(Duration)` applies the length stored in `Duration`, which is held in seconds and nanoseconds. A `Duration` can be negative; adding a negative duration moves the `Instant` backward on the timeline. When business logic requires a fixed interval, passing a `Duration` is usually clearer than uncommented unit numbers.

### Adding an Amount and a `TemporalUnit`

General overload:

```java
Instant afterNinetyMinutes = base.plus(90, ChronoUnit.MINUTES);
Instant afterOneDay = base.plus(1, ChronoUnit.DAYS);
Instant afterMicrosecond = base.plus(1, ChronoUnit.MICROS);
```

Requires `import java.time.temporal.ChronoUnit;` along with `import java.time.Instant;`. `TemporalUnit` is the unit interface; `ChronoUnit` is Java's standard unit enum. **Not every `ChronoUnit` unit is supported by `Instant`**. You should check if the unit comes from user input or configuration.

## 3. Corresponding Subtraction Operations

`Instant` has symmetric methods:

| Addition | Subtraction | Example |
| --- | --- | --- |
| `plusSeconds(n)` | `minusSeconds(n)` | Exactly 30 seconds before 10:00: `minusSeconds(30)`. |
| `plusMillis(n)` | `minusMillis(n)` | Exactly 250 ms before 10:00: `minusMillis(250)`. |
| `plusNanos(n)` | `minusNanos(n)` | Subtract one nanosecond with `minusNanos(1)`. |
| `plus(duration)` | `minus(duration)` | Subtract `Duration.ofMinutes(10)`. |
| `plus(amount, unit)` | `minus(amount, unit)` | Subtract 2 hours with `minus(2, ChronoUnit.HOURS)`. |

Example with `base = 2025-01-15T10:00:00Z`:

```java
Instant oneHourBefore = base.minusSeconds(3_600);
Instant twoHoursBefore = base.minus(2, ChronoUnit.HOURS);
Instant aQuarterSecondBefore = base.minusMillis(250);
Instant oneNanosecondBefore = base.minusNanos(1);
```

The results are `2025-01-15T09:00:00Z`, `2025-01-15T08:00:00Z`, `2025-01-15T09:59:59.750Z`, and `2025-01-15T09:59:59.999999999Z`, respectively. Note that subtracting 1 nanosecond rolls back to the **previous second** with a nano part of `999999999`; Java handles that borrow automatically.

`minusSeconds(-30)` is equivalent to `plusSeconds(30)`. Negative inputs are mathematically valid, but you should avoid sign confusion in business logic.

## 4. `ChronoUnit` Units Supported by `Instant`

For the **standard `ChronoUnit` units**, `Instant` supports the group from `NANOS` to `DAYS` as follows:

| Unit | Fixed Length | `Instant.plus(amount, unit)` |
| --- | --- | --- |
| `NANOS` | 1 nanosecond | Supported |
| `MICROS` | 1 microsecond = 1,000 ns | Supported |
| `MILLIS` | 1 millisecond = 1,000,000 ns | Supported |
| `SECONDS` | 1 second | Supported |
| `MINUTES` | 60 seconds | Supported |
| `HOURS` | 3,600 seconds | Supported |
| `HALF_DAYS` | 12 hours | Supported |
| `DAYS` | 24 hours = 86,400 seconds | Supported |
| `WEEKS` | Calendar week | **Not supported directly** |
| `MONTHS` | Calendar month | **Not supported directly** |
| `YEARS` | Calendar year | **Not supported directly** |
| `DECADES`, `CENTURIES`, `MILLENNIA` | Multiple years | Not supported directly |
| `ERAS`, `FOREVER` | Era / forever | Not supported directly |

With this standard enum, you can check:

```java
boolean supportsDays = base.isSupported(ChronoUnit.DAYS);       // true
boolean supportsMonths = base.isSupported(ChronoUnit.MONTHS);   // false
```

Calling `base.plus(1, ChronoUnit.MONTHS)` or `base.minus(1, ChronoUnit.WEEKS)` throws `UnsupportedTemporalTypeException`. `Instant` has no local calendar date to interpret "next month", so it cannot derive a new point in time from `MONTHS` alone.

**Why is `DAYS` supported?** `Instant` defines the `DAYS` unit as a **fixed 24 hours**, rather than performing a calendar-day addition in a time zone. For **a week of exactly 7 × 24 hours**, use `Duration.ofDays(7)` or `plus(7, ChronoUnit.DAYS)`; if you want "the same local time next week", perform calendar addition on a zoned `ZonedDateTime`.

Note that the table refers to standard `ChronoUnit` enum constants; a custom `TemporalUnit` implementation may have its own rules depending on its logic, so you should not assume every unit outside `ChronoUnit` is rejected.

## 5. `Duration` vs. `Period`: How Do They Differ When Added to `Instant`?

- `Duration` expresses **real elapsed time** in seconds and nanoseconds. `Duration.ofDays(1)` is always **86,400 seconds**.
- `Period` expresses **calendar years, months, and days**, suited for `LocalDate` or `ZonedDateTime` in calendar-based calculations. A month can be 28–31 days long.

An easily overlooked detail: `Instant.plus(Period.ofDays(1))` **works**, because this `Period` only applies the `DAYS` unit that `Instant` supports. However, `Instant.plus(Period.ofMonths(1))` **does not work**, because `MONTHS` is not supported. That does not mean you can use any `Period` just like a `Duration` on `Instant`.

To avoid ambiguity, if the intent is **after exactly N seconds, minutes, hours, or 24-hour days**, choose `Duration`. If the intent is **the same day next month or the same time tomorrow in a region**, choose calendar addition after obtaining a `ZoneId`. Do not assume one month = 30 days.

## 6. Complete Java 17+ Example: Arithmetic and Valid Units

Create the file **`InstantArithmeticDemo.java`**:

```java
import java.time.*;
import java.time.temporal.ChronoUnit;

public class InstantArithmeticDemo {
    public static void main(String[] args) {
        Instant start = Instant.parse("2025-01-15T10:00:00Z");
        Duration ninetyMinutes = Duration.ofMinutes(90);

        System.out.println("Start              : " + start);
        System.out.println("Plus 90 minutes    : " + start.plus(ninetyMinutes));
        System.out.println("Minus 2 hours      : "
                + start.minus(2, ChronoUnit.HOURS));
        System.out.println("Plus 1500 millis   : " + start.plusMillis(1500));
        System.out.println("Minus 1 nanosecond : " + start.minusNanos(1));
        System.out.println("Plus 1 day         : "
                + start.plus(1, ChronoUnit.DAYS));
        System.out.println("Plus 24 hours      : "
                + start.plus(Duration.ofHours(24)));
        System.out.println("Supported (days)   : "
                + start.isSupported(ChronoUnit.DAYS));
        System.out.println("Supported (months) : "
                + start.isSupported(ChronoUnit.MONTHS));
        System.out.println("Period of 1 day    : "
                + start.plus(Period.ofDays(1)));

        try {
            start.plus(1, ChronoUnit.MONTHS);
        } catch (java.time.temporal.UnsupportedTemporalTypeException e) {
            System.out.println(
                    "Plus month error   : UnsupportedTemporalTypeException"
            );
        }
        try {
            start.plus(Period.ofMonths(1));
        } catch (java.time.temporal.UnsupportedTemporalTypeException e) {
            System.out.println(
                    "Period month error : UnsupportedTemporalTypeException"
            );
        }
        System.out.println("Original           : " + start);
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac InstantArithmeticDemo.java
java InstantArithmeticDemo
```

Verified Java output:

```text
Start              : 2025-01-15T10:00:00Z
Plus 90 minutes    : 2025-01-15T11:30:00Z
Minus 2 hours      : 2025-01-15T08:00:00Z
Plus 1500 millis   : 2025-01-15T10:00:01.500Z
Minus 1 nanosecond : 2025-01-15T09:59:59.999999999Z
Plus 1 day         : 2025-01-16T10:00:00Z
Plus 24 hours      : 2025-01-16T10:00:00Z
Supported (days)   : true
Supported (months) : false
Period of 1 day    : 2025-01-16T10:00:00Z
Plus month error   : UnsupportedTemporalTypeException
Period month error : UnsupportedTemporalTypeException
Original           : 2025-01-15T10:00:00Z
```

**Reading the output:** Adding 90 minutes to 10:00 produces 11:30. Subtracting 2 hours produces 08:00. `plusMillis(1500)` produces the `.500` millisecond part after advancing by 1 second. `minusNanos(1)` steps back one nanosecond into the immediately preceding second. `DAYS` produces the same result as `Duration.ofHours(24)`. `MONTHS` is rejected, while `Period.ofDays(1)` succeeds because it only contains a days component. Finally, `start` remains unchanged, demonstrating immutability.

## 7. Why Adding 1 `DAYS` on `Instant` Differs from Adding 1 Calendar Day

Suppose a user schedules an event for **12:00 on March 9, 2024 in New York**. The next day, this region transitions to DST: the UTC offset shifts from `-05:00` to `-04:00`. In that case:

- `Instant.plus(1, ChronoUnit.DAYS)` advances **24 real hours later**, displaying **13:00 on March 10** in New York.
- `ZonedDateTime.plusDays(1)` advances to **12:00 on March 10 in local time**, which is only **23 real hours** after the starting point.

To see the difference, create the file **`InstantAcrossDstDemo.java`**:

```java
import java.time.*;
import java.time.temporal.ChronoUnit;

public class InstantAcrossDstDemo {
    public static void main(String[] args) {
        ZoneId zone = ZoneId.of("America/New_York");
        ZonedDateTime localStart =
                ZonedDateTime.of(2024, 3, 9, 12, 0, 0, 0, zone);
        Instant start = localStart.toInstant();

        Instant afterInstantDay =
                start.plus(1, ChronoUnit.DAYS);
        ZonedDateTime afterCalendarDay =
                localStart.plusDays(1);

        System.out.println("Local start         : " + localStart);
        System.out.println("Instant start       : " + start);
        System.out.println("Instant + 1 DAY     : " + afterInstantDay);
        System.out.println("Viewed in New York  : "
                + afterInstantDay.atZone(zone));
        System.out.println("Local + 1 calendar day: " + afterCalendarDay);
        System.out.println("Calendar day instant: "
                + afterCalendarDay.toInstant());
        System.out.println("Hours to local +1d : "
                + Duration.between(start,
                        afterCalendarDay.toInstant()).toHours());
        System.out.println("Hours instant +1d  : "
                + Duration.between(start, afterInstantDay).toHours());
    }
}
```

```bash
javac InstantAcrossDstDemo.java
java InstantAcrossDstDemo
```

Verified output:

```text
Local start         : 2024-03-09T12:00-05:00[America/New_York]
Instant start       : 2024-03-09T17:00:00Z
Instant + 1 DAY     : 2024-03-10T17:00:00Z
Viewed in New York  : 2024-03-10T13:00-04:00[America/New_York]
Local + 1 calendar day: 2024-03-10T12:00-04:00[America/New_York]
Calendar day instant: 2024-03-10T16:00:00Z
Hours to local +1d : 23
Hours instant +1d  : 24
```

Both results are correct. One operation preserves **an exact elapsed duration of 24 hours**, while the other preserves **12:00 local time the next day**. DST causes the two requirements to produce different results.

For the business requirement "the same date and time next month in Paris", you need a `ZoneId`:

```java
Instant event = Instant.parse("2025-01-15T10:00:00Z");
ZoneId zone = ZoneId.of("Europe/Paris");

ZonedDateTime local = event.atZone(zone);
ZonedDateTime nextMonthLocal = local.plusMonths(1);
Instant nextMonthInstant = nextMonthLocal.toInstant();
```

This is an **illustrative snippet inside a method** and requires `import java.time.*;`. The `plusMonths(1)` addition happens on the calendar date-time in the Paris zone, and only afterward is it converted back to `Instant`. When DST or end-of-month dates are involved, decide clearly how to handle them based on business rules.

## 8. Comparing Operation Styles by Practical Need

| Need | Appropriate Expression | Explanation |
| --- | --- | --- |
| Expires after 15 minutes | `issuedAt.plus(Duration.ofMinutes(15))` | Adds exactly 900 seconds. |
| Add 500 milliseconds | `start.plusMillis(500)` | Fixed milliseconds. |
| Go back 2 hours | `end.minus(2, ChronoUnit.HOURS)` | Fixed hour unit. |
| After exactly 24 hours | `start.plus(1, ChronoUnit.DAYS)` | `DAYS` on `Instant` = 86,400 seconds. |
| After exactly 7 × 24 hours | `start.plus(Duration.ofDays(7))` | Fixed duration of 604,800 seconds. |
| Same local time tomorrow | `start.atZone(zone).plusDays(1).toInstant()` | Follows calendar days in the zone. |
| Same local time next month | `start.atZone(zone).plusMonths(1).toInstant()` | Follows calendar months in the zone. |
| Length between two `Instant` values | `Duration.between(start, end)` | Real elapsed difference between the points. |

For application data, store `Instant` as the creation or expiration timestamp (e.g., `createdAt`, `expiresAt`), while using `Duration` for configured intervals (e.g., `tokenTtl`). Separating calendar data from elapsed durations keeps API structure clear and easy to test.

**Measuring timeouts while an operation is running** requires extra care: `Instant.now()` reads the wall-clock time, which can be affected by system clock adjustments. When measuring real elapsed execution time within a single JVM, a source like `System.nanoTime()` is usually more suitable. Expiration timestamps that must remain meaningful after restarts or when exchanged between systems are well-suited for `Instant`.

## 9. Limits and Exceptions to Handle

### Unsupported Units

If you call `instant.plus(1, ChronoUnit.MONTHS)` or `instant.minus(1, ChronoUnit.YEARS)`, Java throws `UnsupportedTemporalTypeException`. Check with `instant.isSupported(unit)` before adding/subtracting when the input contains a dynamic unit. For calendar-based requirements, convert to `ZonedDateTime` or `LocalDate` and use the corresponding unit.

### Finite Time Range and Overflow

`Instant` has value bounds `Instant.MIN` and `Instant.MAX`. Addition that exceeds this range does not wrap around; instead, it may throw `DateTimeException` or `ArithmeticException` depending on the cause. Conversions or multiplications using `long`, such as `Duration.toNanos()` on a very large duration, can also overflow. Validate unusually large quantities from APIs and handle errors deliberately.

### Nanosecond Part

`Instant` represents points in time down to nanoseconds; `plusNanos(1)` increments by one nanosecond **in the value model**. This does not mean the machine clock or database can always measure or store exact nanoseconds. When persisting to a database or JSON, check the precision and format contract of the receiving system.

### Negative Signs and Business-Invalid Quantities

Negative arguments are valid for addition/subtraction, but an application may need to reject negative TTLs, timeouts, or retention periods. Do not let negative addition inadvertently create an expiration time earlier than the creation time. Inputs outside business rules should be validated at the ingestion layer.

### Addition Returns a New Value

`Instant` is immutable, so:

```java
Instant deadline = Instant.parse("2025-01-15T10:00:00Z");
deadline.plusSeconds(60); // result ignored: deadline is still 10:00
deadline = deadline.plusSeconds(60); // deadline becomes 10:01
```

This snippet is only for illustration in a scope with `import java.time.Instant;`. To keep the original timestamp, use a separate variable `Instant extendedDeadline = deadline.plusSeconds(60);`.

## 10. Calculating the Duration Between Two Timestamps

This is a related operation, distinct from addition/subtraction: **measuring the difference between two `Instant` values**. Use `Duration.between(...)`:

```java
Instant first = Instant.parse("2025-01-15T10:00:00Z");
Instant second = Instant.parse("2025-01-15T11:30:00Z");

Duration elapsed = Duration.between(first, second); // PT1H30M
long minutes = ChronoUnit.MINUTES.between(first, second); // 90
```

This is an illustrative snippet inside a method with `import java.time.*;` and `import java.time.temporal.ChronoUnit;`. `Duration` preserves the seconds/nanoseconds part, whereas `ChronoUnit.MINUTES.between` returns whole minutes. When you need to represent differences under one minute, do not take only whole minutes, as the remainder will be lost.

Two `Instant` values carry no time zone, so there is no need to convert to local time to calculate the real elapsed length. Only convert to `ZonedDateTime` when you want to apply calendar rules or display to a user.

## 11. Common Mistakes

1. **Adding months/years directly to `Instant`:** `MONTHS` and `YEARS` are not supported; choose a calendar-aware type and `ZoneId` when needed.
2. **Treating `DAYS` as a local calendar day:** `Instant.plus(1, DAYS)` is always 24 hours, whereas a DST day can be 23 or 25 hours.
3. **Assuming `ChronoUnit.WEEKS` is supported because a week is 7 days:** for 7 × 24 hours, use `Duration.ofDays(7)`; for the same day/time next week, add on a zoned calendar type.
4. **Confusing units:** `plusMillis(1000)` adds 1 second, while `plusNanos(1000)` adds one microsecond.
5. **Confusing `Period` and `Duration`:** `Period.ofDays(1)` can be applied to `Instant`, but `Period.ofMonths(1)` cannot; use `Duration` to pass elapsed time.
6. **Rounding a month to 30 days:** inaccurate for months with 28, 29, or 31 days.
7. **Ignoring the return value:** `Instant` is immutable and does not mutate the original variable.
8. **Not validating large input values:** addition can exceed `Instant.MAX`, or duration conversion can cause `long` overflow.
9. **Attaching the system time zone when adding a time span:** `Instant` does not need a time zone for 90 minutes or 24 hours; use a time zone when business logic truly follows a local calendar.
10. **Measuring latency with two wall-clock reads and blindly trusting the result:** clock adjustments can cause timestamp subtraction to not reflect actual execution time; consider an elapsed-time source.

## 12. Self-Check Exercises

**1.** What does `Instant.parse("2025-01-15T10:00:00Z").plusSeconds(45)` return?

**Answer:** `2025-01-15T10:00:45Z`.

**2.** Starting from `2025-01-15T10:00:00Z`, what do you get by subtracting 250 milliseconds?

**Answer:** `2025-01-15T09:59:59.750Z`.

**3.** Is `plus(1, ChronoUnit.DAYS)` equivalent to `plus(Duration.ofHours(24))`?

**Answer:** Yes, on `Instant` both add 86,400 seconds.

**4.** Does `Instant` support `ChronoUnit.MICROS`, `HALF_DAYS`, and `WEEKS`?

**Answer:** `MICROS` and `HALF_DAYS` are supported; `WEEKS` is not supported directly.

**5.** How do you calculate "the same time tomorrow" in New York across the start of DST?

**Answer:** Convert the `Instant` to `ZonedDateTime` using `atZone(ZoneId.of("America/New_York"))`, call `plusDays(1)`, and then `toInstant()`. The result may be 23 hours after the initial instant rather than 24 hours.

**6.** Does `Instant.plus(Period.ofMonths(1))` work?

**Answer:** No, because it must apply the `MONTHS` unit, which is not supported by `Instant`. A calendar-aware date-time type is needed to add months.

**7.** Why does calling `instant.plusSeconds(30);` leave the `instant` variable unchanged?

**Answer:** Because `Instant` is immutable. You must store the returned value.

**8.** Two UTC instants are 90 minutes apart, and you need to store the full elapsed interval. Which type should you choose?

**Answer:** `Duration.between(start, end)`, which produces the representation `PT1H30M`.

## Key Takeaways

`Instant` is well-suited for shifting a timestamp by an **elapsed duration**: `plus/minus(Duration)`, `plusSeconds/plusMillis/plusNanos`, `minusSeconds/minusMillis/minusNanos`, or the overload with a supported `ChronoUnit`. Standard units supported directly range from `NANOS` to `DAYS`; `DAYS` on `Instant` is strictly **24 hours**. Calendar units such as `WEEKS`, `MONTHS`, and `YEARS` cannot be added directly. When business logic requires **the same local time on a future day or month**, convert to a calendar-aware type with a `ZoneId`, apply the regional rules, and convert back to `Instant` if needed.
