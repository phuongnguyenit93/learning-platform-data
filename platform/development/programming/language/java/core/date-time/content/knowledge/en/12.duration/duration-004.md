# Duration: Negative, Zero, and Positive Durations

In the Java Date-Time API (`java.time`), `Duration` represents **a length of time**, such as how long a request runs, the time between two events, or the difference between two `Instant` values. A `Duration` can be **positive**, **zero**, or **negative**. Its sign indicates the signed length being represented; it does not by itself assert the ordering of a pair of events unless you know the calculation convention.

Common examples:

~~~java
Duration positive = Duration.ofSeconds(2);   // PT2S
Duration zero = Duration.ZERO;               // PT0S
Duration negative = Duration.ofSeconds(-2);  // PT-2S
~~~

- **Positive**: total duration is greater than 0.
- **Zero**: signed length is exact 0; `isZero()` returns `true`.
- **Negative**: total duration is less than 0; `isNegative()` returns `true`.

A negative sign is not an error by default. For example, `Duration.between(later, earlier)` is negative if the second argument occurs before the first argument. Whether to accept a negative duration depends on business rules: runtime statistics typically expect non-negative values, whereas directional comparisons and historical differences may be valid when negative.

## 1. What is Duration?

`Duration` represents an amount of time in units based on seconds and nanoseconds. It is useful for time spans such as `PT1.5S` (one and a half seconds) or `PT15M` (15 minutes). Its model is not a calendar date or a wall-clock time in a time zone.

| Type | Meaning | Example |
|---|---|---|
| `Instant` | A point on the timeline | `2024-01-01T00:00:05Z` |
| `Duration` | Directed time span between points | `PT5S`, `PT-2S` |
| `Period` | Calendar-based span in years/months/days | `P1M` (one calendar month) |
| `LocalTime` | Time on a clock, without date/time zone | `10:30` |

**`Duration.ofDays(1)` differs from "one calendar day" in every context.** `Duration` treats one day as 24 hours (86,400 seconds); `Period.ofDays(1)` is one calendar day. In a region using DST, a calendar day from midnight to the next midnight may not be exactly 24 hours long. Choose the type based on the meaning of the requirement.

## 2. Sign of a Duration: Negative, Zero, Positive

### Checking the Sign via the API

Key methods:

| API | Meaning |
|---|---|
| `duration.isNegative()` | Returns `true` if the total duration is less than 0 |
| `duration.isZero()` | Returns `true` if the duration is exactly 0 |
| `duration.isPositive()` | This method does not exist in Java 17; check for positive with `!isNegative() && !isZero()` |
| `duration.abs()` | Returns the corresponding non-negative magnitude; may fail if the magnitude exceeds the representable range |
| `duration.negated()` | Returns a duration with the opposite sign; does not modify the original object |

Java 17 has `isNegative()` and `isZero()`, but **does not have `isPositive()`**. If you need to check for positive:

~~~java
boolean positive = !duration.isNegative() && !duration.isZero();
~~~

Do not write `duration.getSeconds() > 0` as the sole sign check, because `Duration` can have an additional nanosecond component that affects the overall sign.

### The Zero State

`Duration.ZERO` is a constant representing a zero-length duration. A zero duration can come from two identical instants:

~~~java
Instant event = Instant.parse("2024-01-01T00:00:00Z");
Duration elapsed = Duration.between(event, event);
System.out.println(elapsed);          // PT0S
System.out.println(elapsed.isZero()); // true
System.out.println(elapsed.isNegative()); // false
~~~

Zero is a distinct case—neither negative nor positive. If a condition requires "duration greater than 0", checking only `!isNegative()` is not enough because a value of 0 also passes that condition.

## 3. How to Read Negative Durations and Seconds/Nanos Components

A common point of confusion is that `Duration` normalizes the nanosecond part to the range **0 to 999,999,999**, even when the entire duration is negative. For example:

~~~java
Duration negative = Duration.ofSeconds(-2, 500_000_000);
System.out.println(negative);          // PT-1.5S
System.out.println(negative.getSeconds()); // -2
System.out.println(negative.getNano());    // 500000000
System.out.println(negative.isNegative()); // true
~~~

Read the meaning correctly: the total duration is `-2 + 0.5 = -1.5` seconds. `getSeconds()` returns `-2` and `getNano()` returns `500_000_000` — the nanoseconds are non-negative. If you only look at `getSeconds()` or only look at `getNano()`, it is very easy to misread the sign of the entire duration.

This normalization rule allows every value to be represented by a valid seconds + nanoseconds pair. Do not assume a `Duration` is positive just because `getNano()` is greater than 0.

### ISO-8601 String of a Duration

`Duration.toString()` uses the ISO-8601 text format:

| Duration | Common String |
|---|---|
| Positive two seconds | `PT2S` |
| Positive 1.5 seconds | `PT1.5S` |
| Negative two seconds | `PT-2S` |
| Negative 1.5 seconds | `PT-1.5S` |
| Zero | `PT0S` |
| 15 minutes | `PT15M` |
| One 24-hour day | `PT24H` |

`P` begins the period part; `T` marks the hours/minutes/seconds part; `S` represents seconds. This is a duration format, not a date-time format like `2024-01-01T00:00:00Z`.

When reading a duration from an API or configuration, use `Duration.parse("PT-1.5S")` and validate it against business bounds. Do not parse the string by simply stripping `PT` or guessing the sign from a single component.

## 4. Duration.between: Argument Order Determines the Sign

`Duration.between(start, end)` computes the span from the first argument to the second argument. Algebraically, it is equivalent to **end − start**:

- If end occurs after start: positive duration.
- If end equals start: zero duration.
- If end occurs before start: negative duration.

~~~java
Instant start = Instant.parse("2024-01-01T00:00:10Z");
Instant end = Instant.parse("2024-01-01T00:00:12Z");

Duration forward = Duration.between(start, end); // PT2S
Duration backward = Duration.between(end, start); // PT-2S
~~~

Illustration table:

| Start | End | Result | Sign |
|---|---|---|---|
| 10 seconds | 12 seconds | `PT2S` | Positive |
| 10 seconds | 10 seconds | `PT0S` | Zero |
| 12 seconds | 10 seconds | `PT-2S` | Negative |

**Arguments are not automatically sorted chronologically.** If you swap the two arguments, the sign is inverted. When an unexpected negative duration appears, first check the argument order and the meaning of both variables. Business logic may require rejecting data where the end precedes the start, or a directed subtraction may be intentionally correct.

With `Instant`, `Duration.between(a,b)` is the appropriate way to measure a time span on the timeline. With other types, the result follows how that type models time; in particular, do not treat `Duration.between(LocalTime...)` as a global duration between two events without knowing the dates and how midnight crossings are handled.

## 5. Operations on Signed Durations

### Adding and Subtracting Durations

~~~java
Duration negative = Duration.ofMillis(-1500); // PT-1.5S
Duration adjusted = negative.plusSeconds(3); // PT1.5S
Duration shorter = Duration.ofSeconds(2).minusSeconds(5); // PT-3S
~~~

Adding a positive duration can turn a negative duration positive; subtracting a span larger than the initial magnitude can make the result negative. Operations do not mutate the original object because `Duration` is immutable; you must keep the returned value.

### Negating and Taking the Absolute Value

~~~java
Duration d = Duration.ofSeconds(-2);
Duration flipped = d.negated(); // PT2S
Duration magnitude = d.abs();    // PT2S
~~~

`negated()` and `abs()` differ in purpose: `negated()` flips the algebraic sign; `abs()` returns the non-negative magnitude. Avoid using `abs()` to mask anomalous data when a negative sign carries important information.

**Watch out for overflow:** `Duration` has a finite representable range. `abs()` or `negated()` can throw `ArithmeticException` for special values whose magnitude cannot be represented after flipping the sign; do not assume absolute value is always safe for every duration.

### Dividing a Duration

~~~java
Duration duration = Duration.ofMillis(-1500);
Duration half = duration.dividedBy(2); // PT-0.75S
~~~

Dividing a duration divides the **signed length**, preserving the sign and normalizing the nanosecond part. It is not manual integer-second rounding. If the system converts the result to milliseconds, nanoseconds, or whole seconds, carefully inspect the unit conversion step and any precision loss.

## 6. Unit Conversions and Arithmetic Limits

Several convenient APIs:

- `toDays()`, `toHours()`, `toMinutes()`, `toSeconds()` return the whole number of corresponding units; any remainder smaller than the unit is truncated according to the API's rules.
- `toMillis()` converts to milliseconds; may throw `ArithmeticException` if the result exceeds the `long` range.
- `toNanos()` converts to nanoseconds as a `long`; can also overflow for large spans.
- `getSeconds()` and `getNano()` read the normalized seconds/nanoseconds pair; they are not equivalent to a simple floating-point number if you look at only one component in isolation.

For example, with `Duration.ofMillis(-1500)`:

~~~java
Duration d = Duration.ofMillis(-1500);
System.out.println(d.toSeconds()); // -1
System.out.println(d.toMillis());  // -1500
~~~

`toSeconds()` returns whole seconds and truncates the fractional part; it does not round to the nearest second. The sign of the integer result can also be counterintuitive if you only inspect the seconds and nanoseconds parts individually — check `isNegative()` to verify the overall sign.

If a duration comes from a large difference, do not assume converting to millis/nanos is always safe. Validate the input range and handle exceptions when unit conversion might overflow.

## 7. Standalone Runnable Java 17 Example

Create the file **`DurationSignDemo.java`**:

~~~java
import java.time.Duration;
import java.time.Instant;

public class DurationSignDemo {
    public static void main(String[] args) {
        Duration negative = Duration.ofSeconds(-2, 500_000_000);
        Duration zero = Duration.ZERO;
        Duration positive = Duration.ofMillis(1500);

        System.out.println("negative = " + negative);
        System.out.println("negative seconds = " + negative.getSeconds());
        System.out.println("negative nanos = " + negative.getNano());
        System.out.println("negative isNegative = " + negative.isNegative());
        System.out.println("negative isZero = " + negative.isZero());
        System.out.println("zero = " + zero);
        System.out.println("zero isNegative = " + zero.isNegative());
        System.out.println("zero isZero = " + zero.isZero());
        System.out.println("positive = " + positive);
        System.out.println("positive isNegative = " + positive.isNegative());
        System.out.println("positive millis = " + positive.toMillis());
        System.out.println("negative divided by 2 = " + negative.dividedBy(2));
        System.out.println("negative plus 3 sec = " + negative.plusSeconds(3));

        Instant later = Instant.parse("2024-01-01T00:00:10Z");
        Instant earlier = Instant.parse("2024-01-01T00:00:12Z");
        Duration reverse = Duration.between(earlier, later);
        System.out.println("reverse between = " + reverse);
        System.out.println("reverse sign negative = " + reverse.isNegative());
        System.out.println("absolute = " + reverse.abs());
        System.out.println("abs equals positive? = " +
                reverse.abs().equals(Duration.ofSeconds(2)));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac DurationSignDemo.java
java DurationSignDemo
~~~

Verified output when compiled with `javac --release 17`:

~~~text
negative = PT-1.5S
negative seconds = -2
negative nanos = 500000000
negative isNegative = true
negative isZero = false
zero = PT0S
zero isNegative = false
zero isZero = true
positive = PT1.5S
positive isNegative = false
positive millis = 1500
negative divided by 2 = PT-0.75S
negative plus 3 sec = PT1.5S
reverse between = PT-2S
reverse sign negative = true
absolute = PT2S
abs equals positive? = true
~~~

**Reading the output:**

1. `negative` is negative overall even though `getNano()` is positive; the pair `-2 seconds + 500,000,000 ns` represents `-1.5 seconds`.
2. `Duration.ZERO` is not negative, nor is it positive: `isZero()` is `true`.
3. `PT1.5S` is a positive duration, which can be converted to 1500 milliseconds.
4. Dividing `-1.5` seconds by two yields `-0.75` seconds; adding 3 seconds to the original duration yields `+1.5` seconds.
5. `Duration.between(earlier, later)` in the example is intentionally ordered backward in time, so it returns `PT-2S`; calling `abs()` gives a magnitude of 2 seconds.

## 8. Applications and Business Policies

### Measuring Task Execution Time

If measuring the interval between start and completion using two `Instant` values:

~~~java
Instant started = Instant.now();
// perform work
Instant finished = Instant.now();
Duration elapsed = Duration.between(started, finished);
~~~

Normally we expect `elapsed` to be non-negative, but the system clock can be adjusted. For performance measurement within a single process, `System.nanoTime()` is more appropriate because it uses a monotonic clock; `Instant` is suited for recording wall-clock timestamps. Do not rely on wall-clock durations as an absolute guarantee of execution time.

### Validating That a Duration Must Be Positive

If the duration must be greater than 0:

~~~java
if (duration.isNegative() || duration.isZero()) {
    throw new IllegalArgumentException("Duration must be greater than 0");
}
~~~

If business logic allows zero but not negative:

~~~java
if (duration.isNegative()) {
    throw new IllegalArgumentException("Duration must not be negative");
}
~~~

Use a condition that accurately reflects the requirement; do not just write `!duration.isNegative()` when zero is invalid. A negative duration is sometimes completely valid when representing "ended before the start time" in a directed calculation, so decide based on context.

### When Receiving a Duration from an API or Configuration

- Establish the unit/format contract, such as ISO strings `PT30S` or `PT-1.5S`.
- Validate the sign according to business rules: timeouts, deadlines, or delays typically have specific requirements.
- When converting to milliseconds/nanoseconds, check for potential overflow.
- Do not confuse `Duration` with an `Instant` timestamp: one is a **length**, while the other is a **point**.
- If negative data violates the contract, return a meaningful validation error rather than taking the absolute value to hide the input.

## 9. Common Mistakes

| Misconception | Why It Is Wrong | Correct Approach |
|---|---|---|
| Assuming a negative duration is always a bug | `between(a,b)` is negative when `b` is earlier than `a` | Check input order and business rules |
| Thinking `getNano()` is negative when the duration is negative | The nanosecond component is normalized to be non-negative | Check `isNegative()` and understand the seconds/nanos pair |
| Using `getSeconds() > 0` to verify positive | Does not properly handle the total duration and nanosecond part | Use `!isNegative() && !isZero()` |
| Using `!isNegative()` to verify positive | Zero is also non-negative | Add the `!isZero()` check |
| Treating zero and negative as the same | Zero is exact 0; negative is less than 0 | Distinguish `isZero()` and `isNegative()` |
| Treating `Duration.ofDays(1)` as one calendar day in every zone | It is a fixed 24 hours | Use `Period.ofDays(1)` when a calendar day is meant |
| Swapping the order of `Duration.between(start,end)` | The sign flips because the calculation is directed | Verify that `end` minus `start` matches intent |
| Calling `abs()` and ignoring negative data | Can hide data or business-flow bugs | Only use absolute value when business logic needs magnitude |
| Believing `toMillis()` always succeeds | Large values can overflow `long` | Check bounds and catch `ArithmeticException` |
| Thinking `Duration` mutates the object on add/subtract | The type is immutable | Store the newly returned value |
| Using `Duration` for calendar months | Months have varying numbers of days | Use `Period` for calendar years/months/days |

## 10. Self-Check Questions

1. What is `Duration.ofSeconds(2).isNegative()`? **false**, the duration is positive.
2. What are `Duration.ZERO.isZero()` and `isNegative()`? **true** and **false**.
3. Is `Duration.between(later, earlier)` negative or positive if `earlier` occurs before `later`? **Negative**, because the second argument is earlier than the first.
4. Why does `Duration.ofSeconds(-2, 500_000_000)` print as `PT-1.5S`? Because the algebraic total is **-1.5 seconds**, even though the nanosecond component is positive.
5. Does Java 17 have `Duration.isPositive()`? **No**; check using `!isNegative() && !isZero()`.
6. What does `Duration.ofMillis(-1500).toSeconds()` return? **-1**, the fractional part is truncated; `toMillis()` returns **-1500**.
7. Which API gets the non-negative magnitude? **`abs()`**, though you still need to watch for overflow at extreme values.
8. Should you take `abs()` on every negative duration? **No**; only when the requirement calls for magnitude, because the sign may carry data meaning.
9. How long is one day in `Duration`? **24 hours**; a calendar day in a DST zone may have a different length.
10. If "duration must be positive" but the duration is zero, which condition rejects it? **`isNegative() || isZero()`**.

**Key takeaway:** The sign of a `Duration` reflects the **total directed time span**: negative when less than zero, zero when exact 0, and positive when greater than zero. Use `isNegative()` together with `isZero()` to classify it; when computing `Duration.between(a,b)`, remember that the sign depends on the order of the two arguments and the business meaning.

### References

- [Java SE 17 — Duration](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html)
- [Java SE 17 — Instant](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html)
- [Java SE 17 — Period](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Period.html)
