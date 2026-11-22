# Converting Duration to Milliseconds or Nanoseconds and Handling Overflow Risks

## Objectives

`java.time.Duration` represents an amount of time in seconds and nanoseconds. When converting to milliseconds or nanoseconds using `toMillis()` and `toNanos()`, two things to understand are that **smaller units may lose precision** and **the result may exceed the limits of the `long` type**.

After this lesson, you will know how to choose the right conversion method, identify the truncated portion when converting units, handle `ArithmeticException`, and avoid manual multiplication or division that causes overflow or incorrect time calculations.

## 1. How Does Duration Store Time Amounts?

`Duration` does not represent a calendar date-time or a time zone. It represents a length of time with nanosecond resolution. Conceptually, a value has a normalized seconds part and nanoseconds part; the nanoseconds part is in the range from 0 to 999,999,999, even when the duration is negative.

```java
Duration a = Duration.ofSeconds(2, 500_000_000);
Duration b = Duration.ofMillis(250);
Duration c = Duration.ofNanos(1_500);
```

These values correspond to 2.5 seconds, 0.25 seconds, and 1,500 nanoseconds. `Duration` can be very long; it is not limited to a 24-hour range like many types that only track hours, minutes, and seconds within a day. Its internal representation can cover a very wide range, but converting it into a single `long` number of milliseconds or nanoseconds may no longer fit.

Two limits to keep in mind:

- `long` has a maximum value of `Long.MAX_VALUE` (9,223,372,036,854,775,807) and a minimum value of `Long.MIN_VALUE` (-9,223,372,036,854,775,808).
- One second has 1,000 milliseconds and 1,000,000,000 nanoseconds. Therefore, the `long` limits for milliseconds and nanoseconds correspond to significantly different lengths of time.

## 2. Converting Duration to Milliseconds with toMillis()

Use `toMillis()` when the target API accepts a number of milliseconds, such as millisecond-based timeouts, measuring elapsed time for display, or integrating with legacy systems:

```java
Duration duration = Duration.ofSeconds(2, 345_678_900);

long millis = duration.toMillis();
System.out.println(millis);
```

Compile the complete example in Section 5 to run it. The result of the conversion is `2345`: the 678,900 sub-millisecond nanoseconds are not retained in the `long` millisecond value.

`toMillis()` only returns **an integer**. It cannot encode fractional milliseconds. If the business logic requires sub-millisecond precision, do not convert to `long` milliseconds prematurely.

## 3. Converting Duration to Nanoseconds with toNanos()

One nanosecond equals one billionth of a second. Use `toNanos()` when the target API requires a number of nanoseconds and the value range is guaranteed to fit in a `long`:

```java
Duration duration = Duration.ofMillis(1501);

long nanos = duration.toNanos();
System.out.println(nanos);
```

Output:

```text
1501000000
```

`toNanos()` allows representing finer detail than milliseconds, but it also causes the integer value to grow much faster. The `long` limit in nanoseconds corresponds to roughly 292 years in each direction from zero, whereas the seconds range of `Duration` is much larger. Therefore, a `Duration` can be completely valid while `toNanos()` still throws an exception.

## 4. Precision Loss When Converting Units

When converting a duration to a larger unit, parts smaller than the target unit cannot be preserved in a single integer.

| Original value | `toMillis()` | `toNanos()` | Meaning |
|---|---:|---:|---|
| `Duration.ofNanos(1)` | 0 | 1 | One nanosecond is less than one millisecond. |
| `Duration.ofNanos(999_999)` | 0 | 999999 | Less than one full millisecond. |
| `Duration.ofNanos(1_500_000)` | 1 | 1500000 | 0.5 milliseconds is dropped in the millisecond result. |
| `Duration.ofMillis(1501)` | 1501 | 1501000000 | Converting to nanoseconds preserves the exact amount of time. |

For example, if the duration is 1.999 milliseconds, `toMillis()` returns 1 whole millisecond; the 0.999 millisecond remainder does not appear in the result. Java does not automatically round up to the "nearest" value just because the fractional part is large. If rounding is needed for business logic (such as never setting a timeout shorter than the requested duration), define an explicit rounding policy instead of assuming `toMillis()` does it.

`toMillisPart()`, `toSecondsPart()`, and other `*Part()` methods can extract components for display; they do not replace total duration calculations and do not solve rounding on their own.

### Do Not Confuse with TimeUnit Conversions

`TimeUnit.NANOSECONDS.toMillis(value)` operates on a `long` value already in nanoseconds and truncates the remainder. `TimeUnit` conversions have different overflow handling rules: excessively large conversions saturate at the `long` bounds instead of throwing `ArithmeticException`. `Duration.toMillis()` and `Duration.toNanos()` throw `ArithmeticException` when the result cannot be represented. Do not swap one API for the other if the system relies on specific overflow behavior.

## 5. Complete Example: Both Units and Precision Loss

Create the file `DurationUnitConversionDemo.java`:

```java
import java.time.Duration;

public class DurationUnitConversionDemo {
    public static void main(String[] args) {
        Duration duration = Duration.ofSeconds(2, 345_678_900);

        System.out.println("Duration: " + duration);
        System.out.println("Millis:   " + duration.toMillis());
        System.out.println("Nanos:    "
                + Duration.ofMillis(1501).toNanos());
        System.out.println("Sub-ms:   " + Duration.ofNanos(999_999).toMillis());
    }
}
```

Compile and run with Java 17+:

```bash
javac DurationUnitConversionDemo.java
java DurationUnitConversionDemo
```

Output:

```text
Duration: PT2.3456789S
Millis:   2345
Nanos:    1501000000
Sub-ms:   0
```

The results show that `toMillis()` drops the sub-millisecond remainder, while converting a 1501-millisecond duration to nanoseconds produces the corresponding total nanoseconds. Each resulting number is safe only when the conversion does not exceed the `long` range.

## 6. Why Can Overflow Occur?

A common mistake is taking total seconds and multiplying by 1,000 or 1,000,000,000:

```java
long millis = duration.getSeconds() * 1000;
long nanos = duration.getSeconds() * 1_000_000_000;
```

Integer multiplication in Java can overflow without throwing an exception; the resulting value is then wrong and may even have the opposite sign of what was intended. The snippet above also ignores the nanosecond part of the duration, so it is not a complete conversion even when the multiplication fits in range.

Prefer `duration.toMillis()` and `duration.toNanos()`: they account for the nanosecond part and use overflow-checked arithmetic. If the result does not fit in a `long`, they throw `ArithmeticException` instead of returning a wrapped-around number.

A very long `Duration` can still be created successfully:

```java
Duration huge = Duration.ofSeconds(Long.MAX_VALUE);
```

However, `huge.toMillis()` cannot succeed because it needs to multiply that huge number of seconds by 1,000 to compute total milliseconds. Similarly, even much shorter durations can exceed the nanosecond limit because the conversion factor is one billion.

## 7. Catching ArithmeticException at the Conversion Boundary

If external data can request unboundedly large durations, handle the error right where you convert to `long`:

```java
import java.time.Duration;

public class DurationOverflowDemo {
    public static void main(String[] args) {
        Duration huge = Duration.ofSeconds(Long.MAX_VALUE);

        try {
            long millis = huge.toMillis();
            System.out.println("Millis: " + millis);
        } catch (ArithmeticException ex) {
            System.out.println("Milliseconds out of long range");
        }

        try {
            long nanos = huge.toNanos();
            System.out.println("Nanos: " + nanos);
        } catch (ArithmeticException ex) {
            System.out.println("Nanoseconds out of long range");
        }
    }
}
```

```bash
javac DurationOverflowDemo.java
java DurationOverflowDemo
```

Output:

```text
Milliseconds out of long range
Nanoseconds out of long range
```

This code does not print the JVM exception message because message details may depend on where the exception originated. It handles the exception type and prints a stable business message.

Avoid catching a generic `Exception` if the goal is to handle unit-conversion overflow. Catching `ArithmeticException` specifically helps distinguish numeric range overflow from other program errors.

## 8. Choosing an Overflow Strategy Based on the Business Contract

Catching overflow is only the first step. The application must decide what to do when a duration cannot be represented in the target unit or API.

- **Reject the input:** Appropriate when an out-of-range duration is invalid data. Report an error at the input or API boundary, and do not proceed as if the conversion succeeded.
- **Enforce an explicit cap:** Suitable for timeouts, retries, or wait intervals. Validate against a system-defined limit before passing the value to a library.
- **Saturate to the limit:** Use only when the contract explicitly states that any excessive value is treated as the maximum or minimum limit. Return `Long.MAX_VALUE` or `Long.MIN_VALUE` explicitly; do not mistake this for the behavior of `Duration.toMillis()`.
- **Keep `Duration`:** If the downstream component also accepts `Duration`, do not convert to `long` prematurely. Preserving the richer type avoids precision loss and defers limit decisions until the boundary that requires an integer.

If boundary checks are required, use overflow-checked APIs to convert and handle exceptions, or write checks against verified limits. Avoid multiplying first and checking afterward, as the value may have already overflowed.

## 9. Common Error-Prone Strategies

### 9.1. Manually Multiplying Seconds

```java
long nanos = duration.getSeconds() * 1_000_000_000;
```

There are two issues: the multiplication can silently overflow, and the remaining nanosecond part in `Duration` is dropped. Use `toNanos()` and handle `ArithmeticException`.

### 9.2. Assuming Duration Cannot Overflow

The fact that `Duration` can hold a large seconds value does not mean its total nanoseconds fit in a `long`. Always distinguish the range of the source type from the range of the target unit.

### 9.3. Assuming Implicit Rounding Up or Down

`toMillis()` returns whole milliseconds without a business rounding parameter. For positive timeouts, if the requirement is to guarantee a wait time no shorter than requested, truncation may not meet the requirement. Explicitly define "truncate", "round up", or another rule, and check for overflow in the rounding calculation as well.

### 9.4. Using TimeUnit Without Considering Differences

`TimeUnit` and `Duration` have different APIs, inputs, and overflow policies. If the code needs to detect unconvertible durations, use `Duration`'s checked methods and handle exceptions. Use saturating conversion only when that is truly the intended contract.

### 9.5. Ignoring the Nanosecond Part When Reading Manually

`getSeconds()` is the normalized seconds component, not a rounded total seconds value. If you need to convert the entire duration, you must include the nanosecond part and handle overflow accurately; generally, you should use the built-in conversion APIs.

## 10. Related Methods

| API | Returns | Use when |
|---|---|---|
| `toMillis()` | Total milliseconds as `long` | The API accepts total milliseconds and the value is in range. |
| `toNanos()` | Total nanoseconds as `long` | Nanosecond granularity is needed and the value is in range. |
| `toDays()`, `toHours()`, `toMinutes()`, `toSeconds()` | Total whole units as `long` | Total in the corresponding unit is needed, and dropping smaller sub-units is acceptable. |
| `toMillisPart()` | Millisecond component within the second | Displaying a component; not total milliseconds. |
| `toNanosPart()` | Normalized nanosecond component | Displaying or computing a component; not total nanoseconds. |
| `getSeconds()`, `getNano()` | Normalized seconds and nanoseconds components | You genuinely need access to the internal structure; you must manage arithmetic and overflow yourself if converting manually. |

When a human-readable string is needed, `Duration.toString()` produces a format like `PT2.3456789S`, which is the ISO-8601 duration format. When computing a total in a unit, use `toMillis()` or `toNanos()`; do not parse the `toString()` string to perform arithmetic.

## 11. Self-Check

**Question 1.** What does `Duration.ofNanos(999_999).toMillis()` return?

**Answer:** `0`, because the duration is less than one millisecond. The fractional part is lost when returning whole milliseconds.

**Question 2.** Why can `Duration.ofSeconds(Long.MAX_VALUE)` be constructed, while `toMillis()` can throw an exception?

**Answer:** `Duration` represents seconds over a range larger than the total-millisecond range of `long`; the multiplication during conversion does not fit in `long` and throws `ArithmeticException`.

**Question 3.** Should you use `duration.getSeconds() * 1000` instead of `toMillis()`?

**Answer:** No. That multiplication can overflow silently and ignores the nanosecond part. `toMillis()` both accounts for the fractional part per the API contract and checks for overflow.

**Question 4.** When a system wants to reject durations that cannot be converted to nanoseconds, where should that be handled?

**Answer:** Wrap `toNanos()` with `ArithmeticException` handling at the conversion boundary, then return an error or reject the input according to the API contract.

**Question 5.** Is `toMillisPart()` the total number of milliseconds of a duration?

**Answer:** No. It is the millisecond component, so for durations longer than one second it cannot replace `toMillis()`.

---

**Rule of thumb:** Keep `Duration` until the boundary where an integer is actually needed. Use `toMillis()` or `toNanos()` for checked conversions; when `ArithmeticException` occurs, apply a clear business policy instead of letting multiplication overflow and produce wrong results.