# Seconds, Milliseconds, Microseconds, and Nanoseconds in Java

## 1. Objectives

After this lesson, you will be able to:

- Explain the differences between seconds (s), milliseconds (ms), microseconds (µs), and nanoseconds (ns), and convert between units without confusing conversion factors.
- Distinguish between an **instant** (a point on the timeline), a **duration** (the length between two points), and **elapsed time for performance measurement**.
- Choose the right Java API: `Instant`, `Duration`, `ChronoUnit`, `TimeUnit`, `System.currentTimeMillis()`, and `System.nanoTime()`.
- Recognize limitations regarding clock resolution, accuracy, truncation of fractional parts, and integer overflow during conversions.

## 2. The Four Units and Conversion Factors

These are **base-10 SI units**, not base-2 storage units.

| Unit | Symbol | In seconds | Relationship to smaller unit |
| --- | --- | ---: | --- |
| Second | s | 1 s | 1 s = 1,000 ms |
| Millisecond | ms | 10⁻³ s | 1 ms = 1,000 µs |
| Microsecond | µs (sometimes written us) | 10⁻⁶ s | 1 µs = 1,000 ns |
| Nanosecond | ns | 10⁻⁹ s | 1 ns = 0.001 µs |

Therefore:

- **1 second = 1,000 milliseconds = 1,000,000 microseconds = 1,000,000,000 nanoseconds.**
- **1 millisecond = 1,000,000 nanoseconds.**
- Converting from a larger unit to a smaller unit: **multiply** by 1,000 at each step. Converting from a smaller unit to a larger unit: **divide** by 1,000 at each step.
- 1.234567890 seconds = 1,234.567890 ms = 1,234,567.890 µs = 1,234,567,890 ns.

For example: a latency of 2.5 ms equals 2,500 µs or 2,500,000 ns. A measurement recording 1,234,567 ns equals 1.234567 ms. Digits after the decimal point are only meaningful when accompanied by a **unit**.

## 3. Instant, Duration, and Counters

These three concepts are often confused:

| What to represent | Meaning | Appropriate API |
| --- | --- | --- |
| A point in time on the UTC timeline | For example, when a transaction starts | `java.time.Instant` |
| A time span of a defined length | For example, a 750 ms timeout | `java.time.Duration` |
| A unit used in calculations between points in time | For example, difference in µs | `java.time.temporal.ChronoUnit` |
| Integer unit conversion and concurrency wait operations | For example, ms → ns | `java.util.concurrent.TimeUnit` |
| Real-time wall clock based on the Unix epoch, in ms | Recording the current point in time | `System.currentTimeMillis()` |
| High-resolution counter for calculating elapsed time | Measuring operation duration | `System.nanoTime()` |

An **instant** answers "when did it happen?", whereas a **duration** answers "how long did it last?". A numeric value `1_000_000` does not by itself state whether it is 1 second in microseconds, 1 millisecond in nanoseconds, or a timestamp in milliseconds. Therefore, variable names, APIs, and data contracts must explicitly state the unit.

The **Unix epoch** is `1970-01-01T00:00:00Z`. A Unix timestamp counts time relative to this reference point; instants before the epoch have negative values. The unit of a timestamp must be clearly specified: Unix seconds and epoch milliseconds are two different encodings of the same instant.

## 4. `Instant`: Seconds and Nanosecond Fraction of a Point in Time

`Instant` represents a point in time on the UTC timeline without carrying a display time zone. In terms of representation, it has two main components:

- `getEpochSecond()`: the number of seconds since the Unix epoch, of type `long`.
- `getNano()`: the nanosecond fraction **within the current second**, always from `0` to `999_999_999`.

For example, `Instant.ofEpochSecond(1, 234_567_890)` means 1 second plus 234,567,890 ns after the epoch, formatted as `1970-01-01T00:00:01.234567890Z`. **`getNano()` is not the total number of nanoseconds since the epoch.**

Java normalizes nanosecond values outside the range [0, 999,999,999] when constructing an `Instant`. For example, `Instant.ofEpochSecond(0, -1)` is the instant 1 ns before the epoch; in that case, `getEpochSecond() == -1` and `getNano() == 999_999_999`. This is the canonical representation even for negative values.

Common creation and reading operations:

```java
Instant epoch = Instant.EPOCH;
Instant fromMillis = Instant.ofEpochMilli(1_234);
Instant precise = Instant.ofEpochSecond(1, 234_567_890);
Instant parsed = Instant.parse("2026-01-02T03:04:05.123456789Z");

long millisecondsSinceEpoch = fromMillis.toEpochMilli();
int nanoFraction = precise.getNano();
```

This is an **illustrative snippet**, requiring `import java.time.Instant;` and placement inside a method body. `toEpochMilli()` returns whole milliseconds, so any fraction smaller than 1 ms is not preserved. For values outside the range representable by a `long` in milliseconds, `toEpochMilli()` can throw `ArithmeticException`.

`Instant.now()` can display up to 9 fractional second digits, but **the actual resolution and accuracy of the clock depend on the operating system, hardware, and clock source**. Having a nanosecond field does not mean the system measures accurately to 1 ns.

## 5. `Duration`: Time Length with Nanosecond Resolution

`Duration` represents an amount of time based on seconds and nanoseconds, suitable for timeouts, elapsed time, media durations, and time addition/subtraction.

```java
Duration oneAndHalfSeconds = Duration.ofMillis(1_500);
Duration oneMicrosecond = Duration.ofNanos(1_000);
Duration twoSeconds = Duration.ofSeconds(2);
Duration combined = twoSeconds.plusMillis(250).plusNanos(75);

long wholeMillis = combined.toMillis();
long totalNanos = combined.toNanos();
```

This is an **illustrative snippet**, requiring `import java.time.Duration;` and a method body. In the example, `combined` is 2 seconds + 250 ms + 75 ns: `wholeMillis` = 2,250, `totalNanos` = 2,250,000,075.

Note how `Duration` normalizes **negative values**. `Duration.ofNanos(-1)` has `getSeconds() == -1` and `getNano() == 999_999_999`, yet the total length is still **negative 1 ns**. Do not treat these two components as two independent quantities with the same sign.

APIs such as `toMillis()`, `toNanos()`, and integer unit counts do not retain fractions smaller than the target unit. For example, 1,234,567 ns → `toMillis() == 1`. When the total number of nanoseconds does not fit within `long` bounds, `Duration.toNanos()` throws `ArithmeticException`. Do not convert an extremely large duration to ns just to compare it: use `compareTo()`, `isNegative()`, `isZero()`, or addition/subtraction methods at the `Duration` level.

## 6. Complete Java 17+ Program: Unit Conversion and Inspecting Instants

Save as **`TimeUnitDemo.java`**:

```java
import java.time.Duration;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.concurrent.TimeUnit;

public class TimeUnitDemo {
    public static void main(String[] args) {
        long milliseconds = 1_234L;
        long microseconds = TimeUnit.MILLISECONDS.toMicros(milliseconds);
        long nanoseconds = TimeUnit.MILLISECONDS.toNanos(milliseconds);

        System.out.println("ms = " + milliseconds);
        System.out.println("us = " + microseconds);
        System.out.println("ns = " + nanoseconds);

        Instant instant = Instant.ofEpochSecond(1, 234_567_890);
        System.out.println("instant = " + instant);
        System.out.println("nanoPart = " + instant.getNano());

        Duration duration = Duration.ofSeconds(1)
                .plusMillis(234)
                .plusNanos(567_890);
        System.out.println("durationNanos = " + duration.toNanos());
        System.out.println("durationMicros = " + duration.toNanos() / 1_000);
        System.out.println("betweenMicros = "
                + ChronoUnit.MICROS.between(Instant.EPOCH, instant));
    }
}
```

Compile and run:

```bash
javac TimeUnitDemo.java
java TimeUnitDemo
```

Deterministic output:

```text
ms = 1234
us = 1234000
ns = 1234000000
instant = 1970-01-01T00:00:01.234567890Z
nanoPart = 234567890
durationNanos = 1234567890
durationMicros = 1234567
betweenMicros = 1234567
```

Explanation:

1. `TimeUnit.MILLISECONDS.toMicros(1_234)` multiplies by 1,000; to ns, it multiplies by 1,000,000.
2. `getNano()` returns only the nanosecond fraction of the second on `Instant`.
3. The constructed `Duration` has 1,234,567,890 ns; integer division by 1,000 yields 1,234,567 µs, dropping the trailing 890 ns.
4. `ChronoUnit.MICROS.between(a, b)` returns the **whole** number of microseconds between two `Instant`s, also discarding the remaining nanoseconds during conversion.

Choose `Duration.between(start, end)` when you need to preserve the full precision supported by the API; choose `ChronoUnit.MILLIS/MICROS/NANOS.between` when the caller needs an integer in a specific unit. Calling `between` with a very small unit over a very long time span can overflow `long`.

## 7. `TimeUnit`, `ChronoUnit`, and Integer Conversions

`TimeUnit` provides the constants `NANOSECONDS`, `MICROSECONDS`, `MILLISECONDS`, `SECONDS`, `MINUTES`, `HOURS`, and `DAYS`. For example:

```java
long nanos = TimeUnit.MICROSECONDS.toNanos(750);        // 750_000
long millis = TimeUnit.MICROSECONDS.toMillis(1_999);    // 1
long seconds = TimeUnit.MILLISECONDS.toSeconds(2_999); // 2
```

This is an illustrative snippet with `import java.util.concurrent.TimeUnit;`. `TimeUnit` converts **integer values**; when dividing, any fraction of the target unit is truncated toward zero. When multiplication exceeds `long`, `TimeUnit` conversion methods typically **saturate to `Long.MAX_VALUE` or `Long.MIN_VALUE`**, unlike `Duration.toNanos()` which can throw an exception.

`ChronoUnit` is the set of units for the date-time API (e.g., `SECONDS`, `MILLIS`, `MICROS`, `NANOS`) and the `between` operation on two temporals. Not all date-time objects support every unit; for example, `LocalDate` does not represent nanoseconds within a day. A unit only describes magnitude; it **does not by itself determine a time zone**.

To convert decimal numbers without losing fractional parts due to binary representation, you can use `BigDecimal` with an explicit rounding rule:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalUnitDemo {
    public static void main(String[] args) {
        BigDecimal milliseconds = new BigDecimal("0.123456");
        BigDecimal nanoseconds = milliseconds.movePointRight(6);
        System.out.println(nanoseconds.toPlainString()); // 123456
        System.out.println(nanoseconds.setScale(0, RoundingMode.UNNECESSARY));
    }
}
```

Save as `DecimalUnitDemo.java`, run with `javac DecimalUnitDemo.java` and `java DecimalUnitDemo`. Both output lines are `123456`. The factor from **milliseconds to nanoseconds is 10⁶**. `RoundingMode.UNNECESSARY` only accepts an exact integer result; if there is a fractional nanosecond part, you must explicitly choose a rounding policy appropriate for your business logic.

## 8. Measuring Execution Time: `nanoTime()` vs. `currentTimeMillis()`

`System.currentTimeMillis()` represents wall-clock time based on the Unix epoch in ms. The system clock can be adjusted (NTP, administrative changes); the difference between two consecutive calls does not necessarily reflect accurate elapsed time.

`System.nanoTime()` returns a `long` value from an arbitrary JVM/system origin. The value can be negative; **do not convert it to a Unix timestamp, do not store it as a calendar point in time**, and do not compare readings across different JVMs. Take the difference between two measurements in the same environment:

```java
public class StopwatchDemo {
    public static void main(String[] args) {
        long start = System.nanoTime();

        long sum = 0;
        for (int i = 0; i < 100_000; i++) {
            sum += i;
        }

        long elapsedNanos = System.nanoTime() - start;
        double elapsedMillis = elapsedNanos / 1_000_000.0;

        System.out.println("sum = " + sum);
        System.out.printf("elapsed = %.3f ms%n", elapsedMillis);
    }
}
```

Save `StopwatchDemo.java`; run `javac StopwatchDemo.java`, then `java StopwatchDemo`. The first line is `sum = 4999950000`; the measured milliseconds on the second line **vary on each run**. For reliable benchmarks, you need to warm up the JVM, avoid drawing conclusions from a single run, control JIT/GC/scheduling, and consider **JMH**. A simple loop only demonstrates how to read the clock, not accurate microbenchmarking.

When measuring timeouts, compare `System.nanoTime() - start` against a duration threshold, such as `TimeUnit.SECONDS.toNanos(2)`. Subtracting `long` values works via two's complement arithmetic even if the counter wraps around, provided the measured interval does not exceed the signed difference range (approximately 292 years in ns). For business timestamps that need to be stored and exchanged, use `Instant` and an injectable clock via `Clock` for testing.

## 9. Resolution, Accuracy, and Rounding Rules

Three distinct concepts:

- **Resolution (granularity):** the smallest step a clock or API can actually distinguish in practice. A value returned in ns does not guarantee the clock updates every ns.
- **Accuracy:** how close the measured point in time is to real time; affected by clock synchronization, the operating system, and hardware.
- **Numeric precision:** the number of digits or fractional parts that can be **represented** and preserved across conversions.

When converting ns → µs/ms using integer division, the remainder smaller than the target unit is lost. Rounding rules must be explicitly specified: truncation toward zero (as in many Java integer divisions), round to nearest, floor, ceiling, or throw an error if not exact.

For example: 1,999,999 ns is **1 ms** if taking the integer part in ms, but **nearly 2 ms** if rounding to the nearest ms. Do not append three `000` digits to a timestamp and claim the data is accurate to microseconds or nanoseconds if the original source only had millisecond precision.

When transmitting data via JSON, databases, Kafka, or APIs, always clearly document whether a field is `epochMillis`, `epochMicros`, an ISO-8601 `Instant`, or `durationNanos`. A database timestamp column might only store up to µs or ms even though Java can represent ns; verify the actual precision of the driver, column, and interchange format.

## 10. Integer Limits, Negative Values, and Exceptions

- `long` is a 64-bit signed integer. An amount of ns greater than `Long.MAX_VALUE` cannot fit in a single `long`. `Long.MAX_VALUE` ns is only about **292 years**; using ms with the same `long` type covers a much larger time range.
- Avoid unchecked multiplication like `milliseconds * 1_000_000` without checking for overflow; you can use `Math.multiplyExact(milliseconds, 1_000_000L)` to get an `ArithmeticException`, or use `TimeUnit` when the contract accepts saturation.
- `Duration.toNanos()` can overflow; `Duration` itself has a larger range than fitting everything into a single `long` of ns.
- Java integer division **truncates toward zero**, so be especially careful with negative durations, pre-epoch timestamps, and how `Math.floorDiv` is used.
- A pre-epoch `Instant` can have `getEpochSecond() < 0` while `getNano() >= 0` due to normalization. Do not naively add the two components and convert units without checks.

Program demonstrating negative values and overflow, saved as **`NegativeDurationDemo.java`**:

```java
import java.time.Duration;

public class NegativeDurationDemo {
    public static void main(String[] args) {
        Duration minusOneNano = Duration.ofNanos(-1);
        System.out.println("seconds = " + minusOneNano.getSeconds());
        System.out.println("nanoPart = " + minusOneNano.getNano());
        System.out.println("wholeMillis = " + minusOneNano.toMillis());

        try {
            Duration.ofSeconds(Long.MAX_VALUE).toNanos();
        } catch (ArithmeticException ex) {
            System.out.println("nanos overflow");
        }
    }
}
```

Run `javac NegativeDurationDemo.java` and `java NegativeDurationDemo`:

```text
seconds = -1
nanoPart = 999999999
wholeMillis = 0
nanos overflow
```

The result `wholeMillis = 0` reflects integer truncation when converting a **duration** of -1 ns to ms; it does not mean the original duration is zero.

## 11. Selection Rules in Applications

| Scenario | Choose | Reason |
| --- | --- | --- |
| Storing order creation time, logs, or event timestamps | `Instant` / UTC ISO-8601 string | Unambiguous point in time, avoids unit and time zone ambiguity |
| Passing a Unix timestamp to an API that only accepts integers | `Instant.toEpochMilli()` if the contract is ms | Must document field name, check range, and note lost nanoseconds |
| 500 ms HTTP timeout | `Duration.ofMillis(500)` | Self-describing unit, easy to pass to APIs accepting `Duration` |
| Converting µs ↔ ns in concurrency libraries | `TimeUnit` | Integer unit conversion with saturation semantics |
| Counting microseconds between two instants | `ChronoUnit.MICROS.between(...)` | Returns an integer in the chosen unit |
| Measuring elapsed time of a code block | `System.nanoTime()` difference | Decoupled from calendar clock adjustments |
| Displaying a user's local time | `Instant` combined with `ZoneId` / `ZonedDateTime` | Seconds/ns units do not handle time zones or DST |

## 12. Common Mistakes and Self-Check

1. **Confusing 1,024 with 1,000.** The units s, ms, µs, and ns are base-10; 1 ms = 1,000,000 ns.
2. **Treating `getNano()` as epoch nanoseconds.** It is only the nanosecond fraction of a single second on `Instant`.
3. **Using `currentTimeMillis()` for benchmarking or `nanoTime()` as a timestamp.** Choose the clock according to its purpose.
4. **Assuming nanosecond representation means 1 ns measurement accuracy.** You must consider the clock source and empirical behavior.
5. **Multiplying without checking for `long` overflow.** Use conversion APIs and appropriate overflow policies.
6. **Seeing -1 ns become 0 ms and concluding the duration is zero.** Keep finer-grained units or use `Duration` until the final step.
7. **Storing integer time values without documenting the unit.** Use clear names like `elapsedNanos`, `timeoutMillis`, `createdAtEpochMillis`; document the contract for each system.

Self-check:

- How many ns is 0.75 ms? **750,000 ns**.
- What is the whole millisecond part of 2,500,001 ns? **2 ms**, with 500,001 ns remaining.
- What is `getNano()` of `Instant.ofEpochSecond(0, -1)`? **999,999,999**, while `getEpochSecond() == -1`.
- To measure the elapsed time of a method call that might be affected by system clock adjustments, what should you choose? **The difference between two calls to `System.nanoTime()`**.
- When you need to store a semantically accurate point in time, choose `Instant`; when you need to store "wait 300 ms", choose **`Duration.ofMillis(300)`**.

**Remember:** s, ms, µs, and ns are just units. First determine whether the quantity being measured is an **instant** or a **duration**, then choose the API and clearly specify the unit, rounding rule, overflow limits, and actual precision.