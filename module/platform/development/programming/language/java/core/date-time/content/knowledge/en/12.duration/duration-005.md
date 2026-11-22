# Duration in Java: Addition, Subtraction, Multiplication, Division, Negation, and Absolute Value

## 1. Objective

`java.time.Duration` represents an **elapsed amount of time**, based on seconds and nanoseconds. In Java 17+, `Duration` is immutable: arithmetic operations return a new value and do not modify the original object.

This lesson covers addition, subtraction, multiplication, division, negation, and absolute value; how to handle negative durations, division remainders, and arithmetic overflow. Do not confuse `Duration` with `Period`: `Duration` is suited for amounts of time in seconds/nanoseconds, whereas `Period` represents calendar years, months, and days.

## 2. Creating a Duration

```java
Duration a = Duration.ofSeconds(3);
Duration b = Duration.ofMillis(1500);
Duration c = Duration.ofMinutes(2);
Duration d = Duration.ofNanos(250);
Duration e = Duration.ofDays(1);
```

This is illustrative code inside a method and requires `import java.time.Duration;`.

| Creation method | Equivalent length |
| --- | ---: |
| `Duration.ofSeconds(1)` | 1 second |
| `Duration.ofMillis(1500)` | 1.5 seconds |
| `Duration.ofNanos(1_000)` | 1 microsecond |
| `Duration.ofMinutes(2)` | 120 seconds |
| `Duration.ofDays(1)` | 86,400 seconds |

`Duration.ofDays(1)` means a fixed 24 hours, not the "next calendar day" in every time zone. A local day across DST can be 23 or 25 hours long; calendar day operations require the appropriate zoned date-time APIs.

`Duration.toString()` typically displays in ISO-8601 format, for example `PT3.5S`, `PT2M`, or `PT-0.5S`.

## 3. Adding with plus

Use `plus(Duration)` to add a duration, or methods such as `plusSeconds`, `plusMillis`, and `plusNanos` when the unit is already known.

```java
Duration base = Duration.ofSeconds(2);
Duration extra = Duration.ofMillis(500);

Duration total = base.plus(extra);
Duration alsoTotal = base.plusMillis(500);

System.out.println(total);       // PT2.5S
System.out.println(alsoTotal);   // PT2.5S
System.out.println(base);        // PT2S
```

This is illustrative code inside a method and requires `import java.time.Duration;`. The output shows that `base` remains unchanged. Each call produces a new return value.

```java
Duration timeout = Duration.ofSeconds(1)
        .plusMillis(250)
        .plusNanos(40);
System.out.println(timeout); // PT1.25000004S
```

Addition calls can be chained. If the result exceeds the range of `Duration`, the operation may throw `ArithmeticException`.

## 4. Subtracting with minus

Use `minus(Duration)` or overloads such as `minusSeconds`, `minusMillis`, and `minusNanos`.

```java
Duration meeting = Duration.ofSeconds(3);
Duration breakTime = Duration.ofMillis(500);

System.out.println(meeting.minus(breakTime)); // PT2.5S
System.out.println(meeting.minusMillis(500)); // PT2.5S
System.out.println(meeting);                  // PT3S
```

The result does not update the original variable. Subtraction can produce a negative duration:

```java
Duration remaining = Duration.ofSeconds(2).minusSeconds(5);
System.out.println(remaining); // PT-3S
System.out.println(remaining.isNegative()); // true
```

Negative durations are valid. For example, `Duration.between(start, end)` is often negative when `end` comes before `start`. Do not clamp all negative values to 0 unless that is a business requirement.

## 5. Multiplying with multipliedBy

`multipliedBy(long)` multiplies a duration by an integer.

```java
Duration interval = Duration.ofMillis(1500);

System.out.println(interval.multipliedBy(3));  // PT4.5S
System.out.println(interval.multipliedBy(0));  // PT0S
System.out.println(interval.multipliedBy(-2)); // PT-3S
System.out.println(interval);                  // PT1.5S
```

This is illustrative code and requires `Duration`. Multiplying by 0 produces `Duration.ZERO`; multiplying by a negative number flips the sign. The original object remains `PT1.5S`.

Multiplication can exceed the representable range and cause `ArithmeticException`. Use the standard API instead of manually multiplying the seconds/nanos components without overflow checks.

## 6. Dividing with dividedBy(long)

`dividedBy(long)` divides a duration by an integer and still returns a `Duration`. The maximum resolution is nanoseconds, so fractional nanoseconds cannot be preserved.

```java
System.out.println(Duration.ofSeconds(5).dividedBy(2)); // PT2.5S

Duration fiveNanos = Duration.ofNanos(5);
System.out.println(fiveNanos.dividedBy(2)); // PT0.000000002S
System.out.println(fiveNanos.dividedBy(3)); // PT0.000000001S
```

5 ns divided by 2 has a mathematical value of 2.5 ns, but `Duration` cannot represent half a nanosecond; the result is 2 ns. Dividing by 0 throws `ArithmeticException`.

Do not confuse `dividedBy(long)` with dividing a duration by another duration; they return two different result types.

## 7. Dividing a Duration by a Duration

The `dividedBy(Duration)` overload returns the whole number of times one duration fits into another.

```java
System.out.println(Duration.ofSeconds(10)
        .dividedBy(Duration.ofSeconds(3))); // 3

System.out.println(Duration.ofSeconds(1)
        .dividedBy(Duration.ofMillis(250))); // 4

System.out.println(Duration.ofSeconds(1)
        .dividedBy(Duration.ofMillis(300))); // 3
```

This is illustrative code and requires `Duration`. One second contains three whole 300 ms blocks, and the remaining 100 ms is discarded. The result is an integer, not a decimal ratio. A divisor duration of 0 causes `ArithmeticException`.

If you need a decimal ratio, explicitly define the precision and rounding policy when converting to an appropriate numeric type; do not assume `Duration` division returns a floating-point number.

## 8. Negating with negated()

`negated()` returns a duration of equal magnitude with the opposite sign.

```java
Duration positive = Duration.ofMillis(1500);
Duration negative = positive.negated();

System.out.println(positive); // PT1.5S
System.out.println(negative); // PT-1.5S
System.out.println(negative.negated()); // PT1.5S
```

Negation does not modify the original object; a zero duration remains zero. Extreme values may not have a corresponding negated value within the representable range, in which case the operation throws `ArithmeticException`.

## 9. Absolute Value with abs()

`abs()` returns a duration with a non-negative magnitude.

```java
Duration late = Duration.ofMillis(-1500);

System.out.println(late);       // PT-1.5S
System.out.println(late.abs()); // PT1.5S
System.out.println(late);       // PT-1.5S
```

Use `abs()` when only the magnitude of the difference is needed. If the sign indicates whether an event is early or overdue, keep the sign until making the business decision. Extreme cases that cannot be negated may throw `ArithmeticException`.

## 10. Negative Durations: seconds and nanos

`Duration` is normalized into seconds and nanoseconds components. The nanosecond component is always from 0 to 999,999,999, even when the overall duration is negative.

```java
Duration d = Duration.ofNanos(-1);

System.out.println(d);               // PT-0.000000001S
System.out.println(d.getSeconds());  // -1
System.out.println(d.getNano());     // 999999999
System.out.println(d.toMillis());    // 0
```

For -1 ns, the normalized representation is -1 second + 999,999,999 ns, totaling -1 ns. `getNano()` is not the total nanoseconds and does not necessarily have the same sign as the overall `Duration`.

`toMillis()` returns whole milliseconds; when the duration is -1 ns, the part smaller than 1 ms is truncated toward 0. That does not turn the original duration into `Duration.ZERO`. If computing total nanoseconds as a `long`, `toNanos()` can throw `ArithmeticException` when the value exceeds the range.

## 11. Integer Division, Truncation, and Rounding

Two different operations:

- `Duration.dividedBy(long)` returns a `Duration` with nanosecond resolution.
- `toMillis()` or `toNanos()` returns an integer in the target unit; any fraction smaller than that unit is discarded.

```java
Duration d = Duration.ofNanos(1_999_999);

System.out.println(d.toMillis());   // 1
System.out.println(d.toNanos());    // 1999999
System.out.println(d.dividedBy(2)); // PT0.000999999S
```

`toMillis()` returns 1 because 1,999,999 ns equals 1.999999 ms and converting to ms takes the integer part. `dividedBy(2)` has the value 999,999.5 ns; fractional nanoseconds cannot be represented, so the result is 999,999 ns.

If business logic requires rounding to nearest, always rounding up, or ties-to-even, implement the policy explicitly. `Duration` does not automatically apply a general business rounding rule across operations.

## 12. Overflow and Exception Handling

Multiplication, negation, and unit conversion operations can exceed the valid range. For example:

```java
Duration huge = Duration.ofSeconds(Long.MAX_VALUE);

try {
    System.out.println(huge.multipliedBy(2));
} catch (ArithmeticException ex) {
    System.out.println("overflow");
}

try {
    System.out.println(Duration.ofSeconds(Long.MIN_VALUE).negated());
} catch (ArithmeticException ex) {
    System.out.println("negation overflow");
}
```

Output:

```text
overflow
negation overflow
```

Large values can come from external data. Validate inputs and handle `ArithmeticException` according to the contract; do not catch all exceptions and ignore them, as that can easily hide real bugs.

## 13. Complete Java Program

Save the file **`DurationArithmeticDemo.java`**:

```java
import java.time.Duration;

public class DurationArithmeticDemo {
    public static void main(String[] args) {
        Duration base = Duration.ofSeconds(3);
        Duration halfSecond = Duration.ofMillis(500);

        System.out.println("plus = " + base.plus(halfSecond));
        System.out.println("minus = " + base.minus(halfSecond));
        System.out.println("times3 = " + halfSecond.multipliedBy(3));
        System.out.println("divide2 = " + Duration.ofSeconds(5).dividedBy(2));
        System.out.println("ratio = "
                + Duration.ofSeconds(1).dividedBy(Duration.ofMillis(300)));
        System.out.println("negated = " + halfSecond.negated());
        System.out.println("abs = " + Duration.ofMillis(-1500).abs());
        System.out.println("negativeNano = " + Duration.ofNanos(-1));
        System.out.println("negativeMillis = " + Duration.ofNanos(-1).toMillis());
        System.out.println("original = " + base);
    }
}
```

Compile and run on Java 17+:

```bash
javac DurationArithmeticDemo.java
java DurationArithmeticDemo
```

Deterministic output:

```text
plus = PT3.5S
minus = PT2.5S
times3 = PT1.5S
divide2 = PT2.5S
ratio = 3
negated = PT-0.5S
abs = PT1.5S
negativeNano = PT-0.000000001S
negativeMillis = 0
original = PT3S
```

Operations return a new `Duration`; dividing a `Duration` by a `Duration` returns the whole number of blocks; negation and absolute value do not modify the original variable; a -1 ns duration can convert to 0 ms when taking the integer part.

## 14. Applying in Real-World Programs

| Need | API | Notes |
| --- | --- | --- |
| Total time of two work steps | `a.plus(b)` | Result is a new value |
| Remaining time = deadline - now | `Duration.between(now, deadline)` | Can be negative when overdue |
| Multiply per-task time by iteration count | `perTask.multipliedBy(count)` | Check for overflow |
| Divide total load into equal parts | `total.dividedBy(parts)` | Remainder may not divide evenly to ns |
| Count whole blocks in total time | `total.dividedBy(block)` | Returns `long`, discards remainder |
| Get magnitude of a difference | `difference.abs()` | Use only when sign is not needed |
| Flip the sign of a difference | `difference.negated()` | Can overflow at extreme values |
| Represent a 24-hour wait interval | `Duration.ofDays(1)` | Differs from calendar day in DST zones |
| Convert to milliseconds for legacy APIs | `duration.toMillis()` | May lose micro/nanoseconds; check range |

For timeouts or performance durations, keep `Duration` as long as possible and convert to an integer only at the API boundary. Always document the unit clearly when using integers: milliseconds and nanoseconds share the same Java type.

## 15. Common Pitfalls

1. **Assuming `Duration` is mutable.** `duration.plusSeconds(5);` does not update the variable if the result is discarded.
2. **Forgetting the subtraction order.** `Duration.between(start, end)` is `end - start`; it can be negative.
3. **Confusing duration division with a decimal ratio.** `dividedBy(Duration)` returns the whole number of blocks.
4. **Mistaking `getNano()` for total nanoseconds.** It is the normalized nanosecond component.
5. **Assuming `toMillis()` always rounds to nearest.** Sub-millisecond fractions are truncated toward 0.
6. **Ignoring overflow.** Multiplication, negation, and unit conversions can fail.
7. **Calling `abs()` and losing business meaning.** Preserve the sign if you need to know whether something is early or overdue.
8. **Using `Duration` for calendar months.** Months do not have a fixed length; use `Period` and the appropriate date-time types.

## 16. Self-Check Exercises

**Question 1.** What does `Duration.ofSeconds(3).plusMillis(500)` print?

**Answer:** `PT3.5S`.

**Question 2.** What is the value of `Duration.ofSeconds(5).dividedBy(2)`?

**Answer:** `PT2.5S`.

**Question 3.** What does `Duration.ofSeconds(1).dividedBy(Duration.ofMillis(300))` return?

**Answer:** `3`, because only three complete 300 ms blocks fit.

**Question 4.** Why does `Duration.ofNanos(-1).toMillis()` equal 0?

**Answer:** Converting to whole milliseconds truncates the fractional part toward 0; the original duration is still -1 ns.

**Question 5.** What does `Duration.ofSeconds(Long.MAX_VALUE).multipliedBy(2)` cause?

**Answer:** It throws `ArithmeticException` due to overflow.

**Question 6.** Can `Duration.ofDays(1)` be used in place of a calendar day in Paris across DST?

**Answer:** It should not be. `Duration` is a fixed 24 hours; a local day can be 23 or 25 hours long.

**Key takeaway:** `Duration` supports addition, subtraction, multiplication, division, negation, and absolute value through immutable methods. Understanding signs, nanosecond resolution, integer division rules, and arithmetic limits helps prevent bugs in timeouts, duration measurements, task scheduling, and unit conversions.