# NaN, Infinity, and Signed Zero in DoubleStream

When using the Java Stream API to aggregate numeric data, not every `double` value is a finite real number. Beyond ordinary values, Java has **`NaN` (Not a Number)**, **positive/negative infinity** (`+Infinity`, `-Infinity`), and **two representations of zero** (`+0.0`, `-0.0`). These values can change the outcomes of `DoubleStream.sum()`, `average()`, `min()`, `max()`, `sorted()`, `distinct()`, and comparisons.

This lesson belongs to the **Numeric Aggregation Accuracy** chapter of the **JAVA_STREAM_API** module. After learning to build lazy pipelines with `filter`, `map`, `reduce`, and `collect`, you also need to examine the **numeric contract** of input data. This is especially important in statistics, sensor-data processing, grouping with collectors, running parallel Streams, and performance tuning: a result can follow `double` rules yet violate business expectations.

> **Title clarification:** The phrase “signed zero” can be misunderstood as “zero without a sign”. Java’s `double` type **does not discard the sign bit when the value is zero**: it distinguishes the representations `+0.0` and `-0.0`. The value written as `0.0` is positively signed zero. This lesson explains both representations and their consequences in `DoubleStream`.

## 1. Special Values in the double Type

Java `double` uses the IEEE 754 64-bit binary floating-point format. Certain operations can produce special values even without compile errors or exceptions.

| Value | Java syntax | Example producing it | Meaning |
| --- | --- | --- | --- |
| NaN | `Double.NaN` | `0.0 / 0.0`; `Math.sqrt(-1.0)` | Undefined arithmetic result in the real numbers |
| Positive infinity | `Double.POSITIVE_INFINITY` | `1.0 / 0.0`; operation exceeding finite range | Positive infinite value |
| Negative infinity | `Double.NEGATIVE_INFINITY` | `-1.0 / 0.0` | Negative infinite value |
| Positive zero | `+0.0` or `0.0` | `1.0 - 1.0` | Zero with a positive sign bit |
| Negative zero | `-0.0` | `-1.0 / Double.POSITIVE_INFINITY` | Zero with a negative sign bit |
| Finite number | `12.5`, `-2.0` | Ordinary arithmetic operations | Value with finite magnitude |

Example:

```java
System.out.println(0.0 / 0.0);  // NaN
System.out.println(1.0 / 0.0);  // Infinity
System.out.println(-1.0 / 0.0); // -Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

Unlike integer division by zero, these `double` divisions **do not throw `ArithmeticException`**. They follow floating-point semantics. Consequently, a computation pipeline can keep running with `NaN` or `Infinity` without the programmer noticing.

Standard check methods:

```java
Double.isNaN(value);       // Detects only NaN.
Double.isInfinite(value);  // Detects +Infinity or -Infinity.
Double.isFinite(value);    // True only for finite values, including +/-0.0.
```

`Double.isFinite` has existed since Java 8; it is well suited when defining a policy to “collect statistics only over finite values”.

## 2. NaN Does Not Follow Ordinary Numeric Comparisons

`NaN` has different comparison rules from real numbers:

```java
double missing = Double.NaN;

System.out.println(missing == missing); // false
System.out.println(missing < 10.0);     // false
System.out.println(missing > 10.0);     // false
System.out.println(missing <= 10.0);    // false
System.out.println(missing >= 10.0);    // false
System.out.println(Double.isNaN(missing)); // true
```

Do not use `value == Double.NaN` to detect NaN: that comparison always returns `false`. Use `Double.isNaN(value)`.

For finite values and infinities, primitive comparisons such as `-5.0 < Double.POSITIVE_INFINITY` follow ordinary numerical ordering. `NaN` alone is neither less than, greater than, nor equal to itself under the `==` operator.

However, `Double.compare(a, b)` is defined to provide a **total ordering** for sorting:

- `-Infinity` comes before every finite value.
- `-0.0` comes before `+0.0`.
- `+Infinity` comes after every finite value.
- `NaN` is treated as greater than `+Infinity`; NaNs are considered equal under this comparison.

That is also the ordering used by `DoubleStream.sorted()`, unlike writing a custom comparator using `<` or `>` without handling NaN.

## 3. Impact of NaN and Infinity on Aggregation Operations

Consider common `DoubleStream` terminal operations:

| Operation | With NaN present | With infinity present | Additional notes |
| --- | --- | --- | --- |
| `sum()` | Result is NaN | One-sided infinity can yield infinity of that sign; summing both `+Infinity` and `-Infinity` yields NaN | Addition order and numerical error can affect results |
| `average()` | Present result can be NaN | Average can be infinite or NaN depending on data | Returns `OptionalDouble`; empty Stream yields `OptionalDouble.empty()` |
| `min()` | NaN is propagated to the result | `-Infinity` is smaller than other numeric values | `-0.0` is smaller than `+0.0` |
| `max()` | NaN is propagated to the result | `+Infinity` is larger than other numeric values | `+0.0` is larger than `-0.0` |
| `count()` | Still counts NaN elements | Still counts infinite elements | Counts elements only; does not measure validity |
| `summaryStatistics()` | Sum, average, min/max can become NaN | Matches the corresponding terminal operations | `getCount()` still reflects the number of collected elements |

In the table, “NaN is propagated” means **even a single NaN in the input** causes `DoubleStream.min()` and `max()` to return an `OptionalDouble` **holding NaN**, rather than ignoring NaN and picking a finite value.

### Example: Same Source, Different Results

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;
import java.util.stream.DoubleStream;

public class SpecialValuesDemo {
    public static void main(String[] args) {
        double[] values = {2.0, Double.NaN, 5.0};

        System.out.println(Arrays.stream(values).count()); // 3
        System.out.println(Arrays.stream(values).sum());   // NaN
        System.out.println(Arrays.stream(values).average().getAsDouble()); // NaN
        System.out.println(Arrays.stream(values).min().getAsDouble()); // NaN
        System.out.println(Arrays.stream(values).max().getAsDouble()); // NaN

        DoubleSummaryStatistics stats = Arrays.stream(values).summaryStatistics();
        System.out.println(stats.getCount()); // 3
        System.out.println(stats.getSum());   // NaN

        System.out.println(DoubleStream.of(
            3.0, Double.POSITIVE_INFINITY).sum()); // Infinity
        System.out.println(DoubleStream.of(
            Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY).sum()); // NaN
    }
}
```

Here, `count() == 3` **does not mean** there were three valid observations for computation. A value is NaN yet still counts as an element in the Stream. When analyzing real data, you must choose explicitly how to handle invalid values.

### OptionalDouble.empty Differs from OptionalDouble Containing NaN

```java
OptionalDouble noData = DoubleStream.empty().average();
OptionalDouble invalidAverage = DoubleStream.of(Double.NaN).average();

System.out.println(noData.isPresent());         // false
System.out.println(invalidAverage.isPresent());  // true
System.out.println(Double.isNaN(invalidAverage.getAsDouble())); // true
```

The two cases mean different things: **no data** versus **data present whose computation produced NaN**. `orElse(...)` replaces the value **only when OptionalDouble is empty**; it does not replace NaN. Calling `getAsDouble()` on `OptionalDouble.empty()` throws `NoSuchElementException`.

## 4. Two Representations of Zero: +0.0 and -0.0

Under ordinary numeric comparisons, `+0.0` and `-0.0` are equal:

```java
System.out.println(+0.0 == -0.0); // true
System.out.println(+0.0 < -0.0);  // false
System.out.println(-0.0 < +0.0);  // false
```

Yet their sign bits differ and can produce different results:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity

System.out.println(
    Double.doubleToRawLongBits(+0.0) ==
    Double.doubleToRawLongBits(-0.0)
); // false

System.out.println(Double.compare(-0.0, +0.0) < 0); // true
System.out.println(
    Double.valueOf(-0.0).equals(Double.valueOf(+0.0))
); // false
```

`Double.compare` and `Double.equals` follow rules that distinguish the two signed zeros, even though the primitive `==` operator considers them equal.

### DoubleStream min and max Distinguish the Sign of Zero

```java
double minZero = DoubleStream.of(+0.0, -0.0)
    .min().orElseThrow(IllegalStateException::new);
double maxZero = DoubleStream.of(+0.0, -0.0)
    .max().orElseThrow(IllegalStateException::new);

System.out.println(minZero); // -0.0
System.out.println(maxZero); // 0.0
```

The semantics of `min`/`max` on `double` match `Math.min`/`Math.max`: negative zero is treated as smaller than positive zero, and NaN makes the result NaN.

Therefore, arbitrarily replacing `DoubleStream.min()` with a hand-written `reduce` using `a < b ? a : b` can cause NaN and signed-zero handling to **differ** from the standard operation.

## 5. sorted and distinct: Ordered and Unique by double Rules

These two intermediate operations do not look only at the `==` operator.

```java
import java.util.Arrays;
import java.util.stream.DoubleStream;

double[] sorted = DoubleStream.of(
    Double.NaN,
    +0.0,
    Double.POSITIVE_INFINITY,
    -0.0,
    Double.NEGATIVE_INFINITY
).sorted().toArray();

System.out.println(Arrays.toString(sorted));
// [-Infinity, -0.0, 0.0, Infinity, NaN]

double[] unique = DoubleStream.of(
    -0.0, +0.0, Double.NaN, Double.NaN
).distinct().toArray();

System.out.println(Arrays.toString(unique));
// [-0.0, 0.0, NaN]
```

Key points to remember:

1. `sorted()` uses ordering compatible with `Double.compare`. Thus, NaN has a well-defined position in the sort order instead of making sorting uninterpretable.
2. `distinct()` treats `-0.0` and `+0.0` as **two distinct values**, so it keeps both.
3. `distinct()` treats NaN values as equivalent for deduplication, even though the primitive expression `Double.NaN == Double.NaN` is `false`.
4. When a Stream has an encounter order, `distinct()` keeps the first element encountered in each equivalence class.

If business rules treat all zeros as one identical value, **normalize before calling `distinct()`**:

```java
double[] normalizedZeros = DoubleStream.of(-0.0, +0.0, 2.0)
    .map(x -> x == 0.0 ? 0.0 : x)
    .distinct()
    .toArray();

System.out.println(Arrays.toString(normalizedZeros)); // [0.0, 2.0]
```

Whether to normalize should be decided by business requirements. In certain measurements and numerical problems, the sign of zero carries information and should be preserved.

## 6. Sum and Average Still Suffer Floating-Point Error

Even without NaN or Infinity, `double` addition can round. For instance, `0.1` and `0.2` are not represented exactly by finite binary fractions:

```java
double ordinary = 0.1 + 0.2;
System.out.println(ordinary == 0.3); // false
```

`DoubleStream.sum()` uses a summation strategy aimed at improving accuracy over naive addition, yet **does not turn `double` into an exact decimal type**. Do not assume that summing on a Stream or dividing for an average preserves every decimal digit exactly.

Addition order also matters because floating-point addition is **not strictly associative**:

\[
(a+b)+c \quad \text{may differ from} \quad a+(b+c)
\]

When numbers span very different magnitudes, small contributions can be lost to rounding. Very large values can also produce Infinity mid-calculation and later turn the result into NaN when opposite-signed infinities meet.

### When Currency or Exact Decimal Sums Are Needed

Monetary data with fixed decimal-digit rules is generally better suited to `BigDecimal` or integers representing the smallest currency unit than to `double`:

```java
import java.math.BigDecimal;
import java.util.stream.Stream;

BigDecimal total = Stream.of("0.10", "0.20", "1.35")
    .map(BigDecimal::new)
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 1.65
```

`new BigDecimal(String)` preserves the exact decimal number provided. Avoid `new BigDecimal(0.1)` if you intend the exact decimal `0.1`: the `double` constructor reflects the actual binary value stored.

If using `mapToLong` to convert into smallest-unit integers, control rounding rules, value ranges, and the risk of `long` overflow. Primitive Streams are helpful for performance, yet do not automatically satisfy every accuracy requirement.

## 7. Choosing a Policy for NaN and Infinity Before Aggregating

No single choice fits every data source. Determine whether NaN or infinity represents a data error, information to keep, or a value with special meaning.

| Policy | Approach | When appropriate |
| --- | --- | --- |
| Keep as is | Let NaN/Infinity reach the terminal operation | Need exact IEEE 754 results or want to surface anomalous results |
| Keep only finite numbers | `filter(Double::isFinite)` | Compute statistics only over valid measurements per business contract |
| Exclude only NaN | `filter(x -> !Double.isNaN(x))` | Still want to allow `+Infinity`/`-Infinity` |
| Fail on error | Validate each element, reject invalid data | Business contract forbids special values |
| Normalize zero | `map(x -> x == 0.0 ? 0.0 : x)` | No need to distinguish `-0.0` and `+0.0` |

**Do not silently drop NaN and infinity** if they indicate sensor failures, missing data, or a special event that must be reported. A reliable program typically records the count of invalid values before excluding them from aggregation.

### Practical Example: Sensor Measurement Statistics

```java
import java.util.Arrays;
import java.util.DoubleSummaryStatistics;

public class SensorSummaryDemo {
    public static void main(String[] args) {
        double[] readings = {
            21.5, Double.NaN, Double.POSITIVE_INFINITY,
            -0.0, 23.0, Double.NEGATIVE_INFINITY
        };

        long total = Arrays.stream(readings).count();
        long invalid = Arrays.stream(readings)
            .filter(x -> !Double.isFinite(x))
            .count();
        long nan = Arrays.stream(readings)
            .filter(Double::isNaN)
            .count();

        DoubleSummaryStatistics valid = Arrays.stream(readings)
            .filter(Double::isFinite)
            .summaryStatistics();

        System.out.println("Total records: " + total);  // 6
        System.out.println("Non-finite: " + invalid); // 3
        System.out.println("NaN: " + nan);              // 1
        System.out.println("Valid samples: " + valid.getCount()); // 3
        System.out.println("Valid sum: " + valid.getSum());  // 44.5
        System.out.println("Min: " + valid.getMin());   // -0.0
        System.out.println("Max: " + valid.getMax());   // 23.0
    }
}
```

The example **explicitly defines “valid” as finite**. The negative sign on `-0.0` is still preserved because negative zero is neither NaN nor Infinity. If business semantics do not distinguish the sign of zero, you can normalize it in the pipeline before collecting statistics.

Each call to `Arrays.stream(readings)` creates a new Stream. You cannot reuse the same Stream object after a terminal operation has consumed it.

### When Invalid Data Must Be Rejected Immediately

```java
double[] measurements = {1.5, 2.5, Double.NaN};

for (double value : measurements) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Non-finite value");
    }
}

double total = Arrays.stream(measurements).sum();
```

This is appropriate when invalid data must be treated as an **input error**. Validating upfront avoids returning a NaN value that callers may not know how to handle.

## 8. Running Parallel Streams and Result Reproducibility

`double` addition is not strictly associative, while `parallel()` can split elements into chunks, sum each chunk, and merge results. Consequently, **the bit pattern of a sum or average is not guaranteed to be identical** across every grouping and processing order, even when all data is finite.

```java
double[] values = {1.0e16, 1.0, -1.0e16, 3.0};

double sequential = Arrays.stream(values).sum();
double parallel = Arrays.stream(values).parallel().sum();

// Both follow double arithmetic, but do not use == to assert that
// every floating-point summation produces identical bit patterns.
```

If results are tested for approximate equality, define an **absolute/relative tolerance** suited to the value domain; note that NaN and Infinity must be checked separately:

```java
static boolean nearlyEqual(double a, double b, double epsilon) {
    if (!Double.isFinite(a) || !Double.isFinite(b) || epsilon < 0.0) {
        return false;
    }
    return Math.abs(a - b) <= epsilon;
}
```

This check is a simple example using **absolute error** for a known value domain. With data spanning vastly different magnitudes, consider relative error, difference overflow, and signed-zero semantics. Do not apply one `epsilon` mechanically to every application.

When using `reduce` or a custom Collector with `double`, understand the associativity of the accumulator, partial-combine rules, and shared state. For primitive summation, `DoubleStream.sum()` generally expresses intent and handles rounding error better than `reduce(0.0, Double::sum)`. Still, neither choice automatically turns floating-point math into exact decimal arithmetic.

## 9. Common Misconceptions

| Misconception | What to remember |
| --- | --- |
| “NaN is a very large number.” | NaN is a special value outside primitive numeric ordering; use `Double.isNaN` to detect it |
| “`x == Double.NaN` detects NaN.” | That comparison is always false; use `Double.isNaN(x)` |
| “`sum()` automatically skips NaN.” | With NaN in the input, the sum becomes NaN |
| “`count()` reports the number of valid measurements.” | `count()` counts all elements, including NaN and Infinity |
| “`average().orElse(0)` replaces NaN.” | `orElse` handles only `OptionalDouble.empty()`, not a present NaN value |
| “`+0.0` and `-0.0` behave identically in every operation.” | They are equal under `==` yet differ in sign bit, reciprocal division, and `Double.compare` |
| “`distinct()` removes one of the two signed zeros.” | `DoubleStream.distinct()` retains both `-0.0` and `+0.0` if both appear |
| “`sorted()` cannot handle NaN.” | `sorted()` uses a defined total order, placing NaN after `+Infinity` |
| “`DoubleStream.sum()` is always exact.” | Floating-point sums still undergo rounding and are not necessarily bit-reproducible across every addition order |
| “`parallelStream()` always produces the exact same bits as sequential.” | Merge order can differ; use an appropriate comparison policy and precision specification |
| “Filtering with `Double.isFinite` is always right.” | It is a business choice that can hide faulty data if not logged |

## 10. Exercises With Answers

**Exercise 1 — How does NaN affect things?** Predict:

```java
double[] data = {10.0, Double.NaN, 20.0};
double sum = Arrays.stream(data).sum();
long count = Arrays.stream(data).count();
```

**Answer:** `sum` is `NaN`, `count` is `3`. If you want the sum of finite values only, you can use `Arrays.stream(data).filter(Double::isFinite).sum()` to get `30.0`, while also recording that one element was invalid.

**Exercise 2 — Opposite-signed infinities.** What is the result of the following expression?

```java
double result = DoubleStream
    .of(Double.POSITIVE_INFINITY, Double.NEGATIVE_INFINITY)
    .sum();
```

**Answer:** `NaN`, because the sum of two opposite-signed infinities is undefined under floating-point semantics.

**Exercise 3 — Signed zeros.** How many elements remain after `distinct()`, and what is their sorted order?

```java
double[] result = DoubleStream.of(+0.0, -0.0, +0.0)
    .distinct()
    .sorted()
    .toArray();
```

**Answer:** Two elements, in the order `[-0.0, 0.0]`. `distinct` distinguishes negative and positive zero, while `sorted` places negative zero before positive zero.

**Exercise 4 — OptionalDouble.** Distinguish these two snippets:

```java
OptionalDouble a = DoubleStream.empty().min();
OptionalDouble b = DoubleStream.of(Double.NaN).min();
```

**Answer:** `a.isPresent()` is `false` because there are no elements; `b.isPresent()` is `true` and `Double.isNaN(b.getAsDouble())` is `true`.

**Exercise 5 — Data policy.** Temperature readings are `[20.0, NaN, 22.0, +Infinity]`. Compute the average of finite values only:

```java
double[] temperatures = {
    20.0, Double.NaN, 22.0, Double.POSITIVE_INFINITY
};

OptionalDouble average = Arrays.stream(temperatures)
    .filter(Double::isFinite)
    .average();

System.out.println(average.orElseThrow(
    IllegalStateException::new)); // 21.0
```

**Explanation:** This policy excludes NaN and infinity, keeping `20.0` and `22.0`; the average is `21.0`. In a real application, you should also report the count of excluded values to avoid masking data issues.

## Key Takeaways

In **JAVA_STREAM_API**, `DoubleStream` provides convenient aggregations while still adhering to `double` semantics: **NaN generally propagates**, **infinity can appear in sums/averages**, and **`+0.0`/`-0.0` are not completely equivalent**. `min`, `max`, `sorted`, and `distinct` have well-defined rules for NaN and signed zero. To report meaningful statistics, decide how to treat non-finite values, distinguish empty data from data producing NaN, evaluate rounding error, and account for differences under parallel execution. When exact decimal precision is required, consider a data model such as `BigDecimal` instead of assuming `double` always represents values exactly.
