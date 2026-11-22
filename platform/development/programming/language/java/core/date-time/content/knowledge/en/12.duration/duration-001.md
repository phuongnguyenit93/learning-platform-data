# `Duration` represents an amount of time in seconds and nanoseconds

When a program needs to know how long a task takes to run, how long a verification code remains valid, or how much time separates two events, we need **elapsed time**. In Java, `java.time.Duration` represents this kind of interval. It is suitable for seconds, minutes, hours, and fractions of a second, including negative durations when two instants are passed in reverse order.

`Duration` differs from `Period`: a minute or an hour can be represented as a fixed amount of time, whereas a calendar month or day depends on the calendar and context. Understanding `Duration` accurately helps avoid bugs when calculating deadlines, comparing instants, measuring performance, and working across regions with Daylight Saving Time transitions.

## 1. Duration is the length between two instants

`Duration` is commonly created from two `Instant` values:

~~~java
Instant start = Instant.parse("2026-05-01T10:00:00Z");
Instant end = Instant.parse("2026-05-01T10:00:12Z");

Duration elapsed = Duration.between(start, end);
// PT12S
~~~

The result `PT12S` is the ISO-8601 representation of a 12-second duration. `Duration` does not store a start date, local time, or time zone; it only represents an interval of time. Therefore, two instants can be on different dates or in different years, and the length is still computed in seconds and nanoseconds.

`Duration` objects are immutable. Addition, subtraction, multiplication, or unit conversion produces a new value without modifying the existing object.

## 2. Seconds and nanoseconds precision

Java represents a `Duration` using a signed seconds component and a normalized nanoseconds component. You can read them with:

- `getSeconds()` — the seconds component.
- `getNano()` — the nanoseconds part within the normalized second, from 0 to 999,999,999.
- `toNanos()` — the total length converted to nanoseconds as a `long`, if it does not overflow.
- `toMillis()` — the total length converted to milliseconds as a `long`.

Example of a 1.5-second duration:

~~~java
Duration d = Duration.ofMillis(1500);

System.out.println(d.getSeconds()); // 1
System.out.println(d.getNano());    // 500000000
System.out.println(d.toMillis());   // 1500
System.out.println(d.toNanos());    // 1500000000
~~~

The nano part allows representing fractions of a second with nanosecond resolution. That does not guarantee the physical clock or operating system can always measure accurately down to 1 ns; representation resolution and measurement accuracy are two different concepts.

### 2.1. Normalization of negative durations

Negative durations are still represented using normalized seconds and nanoseconds. For example, `Duration.ofMillis(-500)` represents negative half a second:

~~~java
Duration d = Duration.ofMillis(-500);

System.out.println(d);            // PT-0.5S
System.out.println(d.getSeconds()); // -1
System.out.println(d.getNano());    // 500000000
System.out.println(d.toMillis());   // -500
~~~

The component pair is `(-1 second, +500,000,000 nanoseconds)`, totaling `-1 + 0.5 = -0.5 seconds`. Do not assume the nano component will carry a negative sign. The seconds and nano parts must be interpreted together.

For two instants, `Duration.between(start, end)` returns a positive duration if `end` is after `start`, and a negative duration if `end` is before `start`:

~~~java
Instant later = Instant.parse("2026-01-01T00:00:01Z");
Instant earlier = Instant.parse("2026-01-01T00:00:00Z");

System.out.println(Duration.between(earlier, later)); // PT1S
System.out.println(Duration.between(later, earlier)); // PT-1S
~~~

Argument order matters. If an unexpected negative duration appears, check how the start/end instants were chosen.

## 3. Creating a Duration with factory methods

### 3.1. Seconds, minutes, hours, and smaller units

Common methods:

| Method | Example | Meaning |
| --- | --- | --- |
| `Duration.ofNanos(n)` | `ofNanos(500)` | 500 nanoseconds |
| `Duration.ofMillis(n)` | `ofMillis(1250)` | 1.25 seconds |
| `Duration.ofSeconds(n)` | `ofSeconds(30)` | 30 seconds |
| `Duration.ofMinutes(n)` | `ofMinutes(5)` | 300 seconds |
| `Duration.ofHours(n)` | `ofHours(2)` | 7,200 seconds |
| `Duration.ofDays(n)` | `ofDays(1)` | Exactly 24 hours in Duration |
| `Duration.between(a, b)` | `between(start, end)` | Length from a to b |

`Duration.ofDays(1)` equals exactly 24 hours, not "the next day in a locality." This calculation matters across DST, when a calendar day can last 23 or 25 hours on the timeline.

Factory methods accept signed amounts, within the allowed range of the data type. They do not infer calendar dates or time zones.

### 3.2. Parsing ISO-8601 strings

`Duration.parse` reads durations in ISO-8601 format:

~~~java
Duration a = Duration.parse("PT15M"); // 15 minutes
Duration b = Duration.parse("PT1H30M"); // 1 hour 30 minutes
Duration c = Duration.parse("P2DT3H"); // 2 days (48 hours) + 3 hours
Duration negative = Duration.parse("PT-0.5S"); // negative half a second
~~~

The `P` designator starts the duration, and `T` separates the time part from the day/month/year part. In `Duration`, day `D` equals 24 hours; calendar years and months are not fixed duration units in `Duration`.

When receiving data from an API, standardize the format and unit. The string `"90"` by itself does not specify whether it means 90 seconds, milliseconds, or minutes; ISO `PT90S` clearly expresses that it is 90 seconds.

### 3.3. Constructing from seconds and nano adjustment

`Duration.ofSeconds(seconds, nanoAdjustment)` lets you add a nanosecond adjustment. The input is normalized according to the same seconds/nanoseconds rules of a duration:

~~~java
Duration a = Duration.ofSeconds(1, 500_000_000);
Duration b = Duration.ofSeconds(2, -500_000_000);

System.out.println(a); // PT1.5S
System.out.println(b); // PT1.5S
System.out.println(a.equals(b)); // true
~~~

The nano adjustment does not have to be within the 0–999,999,999 range before calling; Java adjusts it into the appropriate seconds component. Even so, in business code it is usually better to pass clearly meaningful amounts and let the API manage normalization.

## 4. Comparing and extracting components

`Duration` can be compared with `compareTo`, `equals`, and the `isZero`, `isNegative` methods:

~~~java
Duration shortWait = Duration.ofSeconds(5);
Duration longWait = Duration.ofSeconds(10);

System.out.println(shortWait.compareTo(longWait) < 0); // true
System.out.println(shortWait.isZero()); // false
System.out.println(shortWait.isNegative()); // false
~~~

The `toDays()`, `toHours()`, `toMinutes()`, and `toSeconds()` methods return the number of **whole** units, without keeping the fractional part of the larger unit:

~~~java
Duration d = Duration.ofSeconds(90);

System.out.println(d.toMinutes()); // 1
System.out.println(d.toSeconds()); // 90
~~~

Here `toMinutes()` is not 1.5 because the result is an integer `long`. If you need a decimal fraction of minutes for display, you must define your own conversion to floating-point or a smaller unit with the desired precision. Avoid using floating-point numbers when exact deadline boundary comparisons are required.

`toNanos()` and `toMillis()` can throw `ArithmeticException` if the value exceeds the `long` range. Never assume every valid `Duration` can be converted to an integer total of nanoseconds. For very large durations, comparing directly or using the appropriate operations on `Duration` can be safer than multiplying unit counts yourself.

## 5. Adding, subtracting, and multiplying durations

New values can be created using `plus`, `minus`, `multipliedBy`, and `dividedBy`:

~~~java
Duration base = Duration.ofMinutes(10);
Duration plus = base.plus(Duration.ofSeconds(30));
Duration minus = base.minus(Duration.ofMinutes(2));
Duration doubled = base.multipliedBy(2);
Duration half = base.dividedBy(2);

System.out.println(plus);    // PT10M30S
System.out.println(minus);   // PT8M
System.out.println(doubled); // PT20M
System.out.println(half);    // PT5M
~~~

`Duration` is immutable, so `base` remains `PT10M`. Use `plusSeconds`, `minusMillis`, `plusNanos` when you want to express the unit directly.

A duration can overflow if an operation exceeds the supported range; validate external input and handle exceptions appropriately. Integer division should also be understood in terms of `Duration` precision, without assuming every duration divides evenly into an integer number of nanoseconds.

## 6. Duration is not the same as Period or a calendar day

This is the most important distinction:

- `Duration.ofHours(24)`: an amount of time of exactly 24 hours.
- `Period.ofDays(1)`: one calendar day.
- `ZonedDateTime.plusDays(1)`: shifts to the next day on the regional calendar, following local time rules.
- `ZonedDateTime.plusHours(24)`: advances exactly 24 hours on the timeline.

Suppose we start at 12:00 on 2026-10-31 in New York, before the clocks fall back to end DST:

~~~java
ZoneId zone = ZoneId.of("America/New_York");
ZonedDateTime start = LocalDateTime.of(2026, 10, 31, 12, 0)
        .atZone(zone);

ZonedDateTime nextCalendarDay = start.plusDays(1);
ZonedDateTime after24Hours = start.plusHours(24);

System.out.println(start);
System.out.println(nextCalendarDay);
System.out.println(after24Hours);
System.out.println(Duration.between(
        start.toInstant(), nextCalendarDay.toInstant()).toHours());
~~~

With New York's time zone rules for this example, the output is:

~~~text
2026-10-31T12:00-04:00[America/New_York]
2026-11-01T12:00-05:00[America/New_York]
2026-11-01T11:00-05:00[America/New_York]
25
~~~

The next day at the same 12:00 is 25 actual hours later because the clock fell back one hour. A `Duration` does not carry a `ZoneId`, so it does not automatically reflect regional calendar rules. Choose the operation that matches the exact business question: "after 24 hours" or "the same time tomorrow."

## 7. Calculating elapsed time

### 7.1. Using Instant when measuring the distance between two real points in time

~~~java
Instant start = Instant.parse("2026-05-01T10:00:00Z");
Instant finish = Instant.parse("2026-05-01T10:03:40Z");

Duration elapsed = Duration.between(start, finish);
System.out.println(elapsed); // PT3M40S
System.out.println(elapsed.toSeconds()); // 220
~~~

This approach fits two well-defined absolute instants. For events in different time zones, converting them to `Instant` and taking the `Duration` ensures the elapsed time is computed correctly.

Do not take two timezone-less `LocalDateTime` values from different locations and assume their difference is the actual elapsed duration. If local timestamps may be subject to DST or belong to different zones, resolve the zone/offset first.

### 7.2. Measuring a block of code in the JVM

When measuring task execution time, use the difference between two `System.nanoTime()` values:

~~~java
long startNanos = System.nanoTime();
// Perform the work to measure.
long elapsedNanos = System.nanoTime() - startNanos;
Duration elapsed = Duration.ofNanos(elapsedNanos);
~~~

`nanoTime()` is meant for measuring intervals within the same process, not calendar timestamps or nanoseconds since the epoch. Do not print its absolute value as a date/time, and do not compare it directly across two machines. When benchmarking performance, account for JIT warm-up, system load, garbage collection, and enough iterations for reliable measurements.

### 7.3. Using Clock to test deadlines

`Clock` helps control "now" in code that relies on deadlines:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-05-01T10:00:00Z"),
        ZoneOffset.UTC);

Instant now = Instant.now(clock);
Instant deadline = now.plus(Duration.ofMinutes(5));
boolean expired = !now.isBefore(deadline);
~~~

The example uses a fixed instant so you can test right at the boundary without waiting for a real clock. In applications, the time source used to decide deadlines should be chosen deliberately, usually a trusted server time source.

## 8. Deadlines and boundaries

A common way to express a deadline: starting at instant `start` and expiring after `ttl`:

~~~java
Instant expiresAt = start.plus(Duration.ofMinutes(15));
boolean expired = !Instant.now().isBefore(expiresAt);
~~~

The condition above treats **the exact expiration instant** as already expired. If business logic uses a different convention at the boundary, express it explicitly with `isBefore` or `isAfter`.

You should compute `expiresAt` once when creating the deadline, then compare against the current instant. Avoid adding 15 minutes to `now` on every check, because that keeps pushing the deadline into the future.

For TTLs in distributed systems, you also need to determine the time source, clock skew, network latency, and retry handling. `Duration` expresses an amount of time; it does not synchronize machine clocks or guarantee that a task executes at the exact deadline.

## 9. Negative seconds, normalization, and loss of precision

A `Duration` can also be negative:

~~~java
Duration negative = Duration.ofMillis(-1);
System.out.println(negative); // PT-0.001S
System.out.println(negative.getSeconds()); // -1
System.out.println(negative.getNano()); // 999000000
~~~

The pair `(-1 second, +999000000 nanoseconds)` sums to negative one millisecond. Similar to `Instant`, you should not write your own seconds/nanos structure assuming nanos always have the same sign as the duration.

When converting down to millisecond or second resolution, any sub-unit fraction is lost. `Duration.ofNanos(1).toMillis()` returns 0, because one nanosecond is less than one millisecond. `Duration.ofNanos(-1).toMillis()` also returns 0 under `Duration`'s unit conversion; do not confuse this with `Instant.toEpochMilli()`, which computes a timestamp relative to the epoch with its own boundary rules on the negative side.

Use the API directly instead of manually computing total nanoseconds or milliseconds with multiplications that may overflow. When you need a representation to send over an API, document the unit and precision.

## 10. Common pitfalls

| Pitfall | Why it is wrong | How to fix |
| --- | --- | --- |
| Treating `Duration.ofDays(1)` as tomorrow in local time | It is strictly 24 hours | Use calendar operations on `ZonedDateTime` when you need the next day |
| Treating `Duration` as `Period` | Fixed duration differs from calendar interval | Choose based on the required semantics |
| Subtracting two `LocalDateTime` values in different zones | No zone/offset to identify the two instants | Resolve the zone first, then use `Instant` |
| Using `System.currentTimeMillis()` for very short benchmarks | Wall clock can be adjusted and resolution is unsuitable | Use the difference of `System.nanoTime()` |
| Assuming `toMinutes()` returns a floating-point number | Returns whole minutes as a `long` | Keep seconds/nanos or define explicit rounding |
| Calling `toNanos()` on a very large duration without checking | Total may overflow `long` | Handle `ArithmeticException` or keep the `Duration` |
| Recomputing deadline from `now` on every check | The deadline keeps drifting | Compute `expiresAt` once |
| Assuming `Duration` mutates in place | `Duration` is immutable | Assign the result of `plus`/`minus` to a variable |
| Storing negative nanos without normalization | Invalid representation | Use the API's factory methods and getters |
| Confusing timestamps and durations | Timestamp is a point in time, duration is a span | Use `Instant` for instants, `Duration` for intervals |

## 11. Standalone Java 17+ program

This program uses fixed values to demonstrate positive/negative `Duration`, precision, arithmetic, the interval between two instants, and a deadline. The output does not depend on the current time.

~~~java
import java.time.Duration;
import java.time.Instant;

public class DurationBasicsDemo {
    public static void main(String[] args) {
        Duration d = Duration.ofMillis(1500);
        Duration negative = Duration.ofMillis(-500);

        System.out.println("d=" + d);
        System.out.println("d.seconds=" + d.getSeconds());
        System.out.println("d.nanos=" + d.getNano());
        System.out.println("d.millis=" + d.toMillis());
        System.out.println("negative=" + negative);
        System.out.println("negative.seconds=" + negative.getSeconds());
        System.out.println("negative.nanos=" + negative.getNano());

        Instant start = Instant.parse("2026-05-01T10:00:00Z");
        Instant end = Instant.parse("2026-05-01T10:03:40Z");
        Duration elapsed = Duration.between(start, end);
        System.out.println("elapsed=" + elapsed);
        System.out.println("elapsed.seconds=" + elapsed.toSeconds());

        Instant deadline = start.plus(Duration.ofMinutes(5));
        System.out.println("deadline=" + deadline);
        System.out.println("shorterThanDeadline="
                + start.isBefore(deadline));
        System.out.println("exactNanos=" + Duration.ofNanos(1).toNanos());
        System.out.println("subMillisecond=" + Duration.ofNanos(1).toMillis());
    }
}
~~~

Save with the exact name `DurationBasicsDemo.java`, then run:

~~~bash
javac DurationBasicsDemo.java
java DurationBasicsDemo
~~~

Standard output:

~~~text
d=PT1.5S
d.seconds=1
d.nanos=500000000
d.millis=1500
negative=PT-0.5S
negative.seconds=-1
negative.nanos=500000000
elapsed=PT3M40S
elapsed.seconds=220
deadline=2026-05-01T10:05:00Z
shorterThanDeadline=true
exactNanos=1
subMillisecond=0
~~~

Verification: `negative` has seconds `-1` and nanos `500000000`, totaling negative half a second. `elapsed` is 220 seconds. `deadline` is created from `start` plus five minutes, and a one-nanosecond duration is not enough to form a single millisecond.

## 12. Self-check exercises

1. What are `getSeconds()` and `getNano()` for `Duration.ofMillis(1500)`? Why is the total still 1.5 seconds?
2. When is `Duration.between(a, b)` negative? Swap the two instants and observe.
3. Compare `Duration.ofDays(1)` with `Period.ofDays(1)`. Which is appropriate for a 24-hour timeout, and which is appropriate for "the next day"?
4. For `Duration.ofMillis(-1)`, why is `getSeconds()` equal to -1 while `getNano()` is non-negative?
5. Why can `toNanos()` fail for very large `Duration` values? Handle the conversion error in a program.
6. Write tests checking instants before the deadline, at the exact deadline, and after the deadline. Explicitly specify whether the deadline is considered expired when equal.
7. Measure a block of code using `System.nanoTime()` and convert the difference to a `Duration`. Why should you not store an absolute `nanoTime` value as a date/time?
8. One requirement says "send a notification after 24 hours" and another says "send at 09:00 tomorrow in New York." Choose the appropriate time model and operation for each requirement.

**Remember:** `Duration` answers the question **"how long is the interval?"** in seconds and nanoseconds. It does not store a start time or local calendar rules. Use `Instant` to identify points in time, `Duration` to represent actual elapsed length, and calendar operations when the requirement is the same time on the next day.