# Floating-Point Precision Errors and Addition Order in Reduction

In the Java Stream API, `reduce`, `sum`, and collectors let you aggregate a sequence of numbers declaratively. However, the result of adding `double` values does not always match real-number addition in mathematics. Two pipelines summing the exact same values can produce slightly different results simply because **the addition order or grouping changes**.

This lesson belongs to the **Numeric Aggregation Accuracy** chapter of the **JAVA_STREAM_API** module. We will move from floating-point representation to understanding the associativity requirement of `reduce`, analyzing how results are combined in parallel execution, and choosing among `reduce`, `DoubleStream.sum()`, `BigDecimal`, and error-control techniques. This knowledge helps you build `filter`, `map`, `reduce`, and `collect` pipelines that honor their contracts while evaluating precision, shared state, and performance.

## 1. Why Can `double` Addition Have Rounding Errors?

Java uses IEEE 754 binary floating-point representation for `float` and `double`. A `double` has finite precision (a 53-bit significand, including the implicit leading bit for normal numbers). Many familiar decimal fractions **have no finite binary representation**, so they must be rounded when stored or during each operation.

```java
double a = 0.1;
double b = 0.2;
double actual = a + b;

System.out.println(actual);         // 0.30000000000000004
System.out.println(actual == 0.3);  // false
```

`0.1`, `0.2`, and `0.3` in source code are each rounded to the nearest representable `double`. The first two are added and rounded again; that result differs from the `double` produced directly from the literal `0.3`.

This does not mean Java calculates incorrectly: the runtime is following finite-precision floating-point arithmetic. To reason accurately about aggregation, distinguish:

| Concept | Meaning | Example |
|---|---|---|
| Ideal mathematical value | Real-number arithmetic with unlimited precision | `0.1 + 0.2 = 0.3` |
| Value stored in `double` | Binary approximation of a number | The literal `0.1` does not exactly represent one-tenth |
| Floating-point operation result | Result rounded according to `double` arithmetic rules | `0.1 + 0.2` prints `0.30000000000000004` |
| Aggregation error | Discrepancy accumulated from input values and rounding steps | Summing many tiny amounts alongside a huge amount |

The relative precision of `double` is roughly 15–17 significant decimal digits; this is **not** a guarantee that summing millions of numbers will always be accurate to the last 15 digits. Error also depends on magnitude, signs, and operation order.

### 1.1. When Large Numbers Swallow Small Numbers

```java
double large = 1e16;
double small = 1.0;

System.out.println(large + small == large); // true
```

The gap between consecutive `double` values around `1e16` is greater than `1`. Therefore, adding `1` does not change the `double` value after rounding. This phenomenon is especially important when aggregating data spanning vastly different orders of magnitude.

## 2. Floating-Point Addition Is Not Strictly Associative

In mathematics over real numbers, associativity states:

```text
(a + b) + c = a + (b + c)
```

With `double`, each addition step can round, so two groupings can return different results:

```java
double a = 1e16;
double b = -1e16;
double c = 1.0;

double leftGrouped  = (a + b) + c;
double rightGrouped = a + (b + c);

System.out.println(leftGrouped);  // 1.0
System.out.println(rightGrouped); // 0.0
```

Specifically:

1. `(1e16 + -1e16) + 1`: the two large numbers cancel to `0`, then `1` is added, yielding `1`.
2. `1e16 + (-1e16 + 1)`: in the inner addition, `1` is lost to rounding next to `-1e16`; the final step yields `0`.

Same three inputs, same `+` operator, yet a different **grouping** causes an exact discrepancy of `1.0`. The exact arithmetic sum of those values is `1.0`; the right-hand grouping lost the contribution of the small element.

Diagram showing where rounding occurs:

```text
Left grouping                         Right grouping

  1e16 + (-1e16)                       -1e16 + 1
         |                                  |
         0                           -1e16 (rounded)
         |                                  |
        + 1                            + 1e16
         |                                  |
         1                                  0
```

**Implication for Streams:** `reduce` can only split work freely and combine intermediate results without changing semantics if the accumulator is associative by contract. `double` addition does not guarantee strict bit-level associativity.

## 3. Summing With `reduce` in the Stream API

For `Stream<Double>`, one way to aggregate is:

```java
import java.util.List;

List<Double> values = List.of(2.5, 1.5, 3.0);

double total = values.stream()
        .reduce(0.0, Double::sum);

System.out.println(total); // 7.0
```

Here:

- `0.0` is the *identity* used to initialize the reduction.
- `Double::sum` is a `BinaryOperator<Double>` combining two values.
- `reduce` is a terminal operation that triggers pipeline consumption.

Similarly, with `DoubleStream`:

```java
import java.util.stream.DoubleStream;

double total = DoubleStream.of(2.5, 1.5, 3.0)
        .reduce(0.0, Double::sum);
System.out.println(total); // 7.0
```

The overload with an identity returns `double`; the `reduce(DoubleBinaryOperator)` overload without an identity returns `OptionalDouble`, because the stream may be empty:

```java
import java.util.OptionalDouble;

OptionalDouble totalMaybe = DoubleStream.empty()
        .reduce(Double::sum);
System.out.println(totalMaybe.isEmpty()); // true
```

### 3.1. The Associativity Requirement of `reduce`

The contract of `reduce(identity, accumulator)` requires the accumulator to be associative; `identity` must be an identity element for that combining operation. This requirement matters because the Java Stream API can perform parallel reduction by computing partial sums and combining them.

For mathematical real numbers, addition is associative. For `double`, associativity is only an approximation due to representation limits and rounding. Therefore, using `Double::sum` in `reduce` is useful, yet **you cannot require every partitioning strategy to produce bit-for-bit identical results**.

In addition, `+0.0` and `-0.0` differ in their sign bit. Using `0.0` as the identity is natural for ordinary arithmetic sums, but can alter the sign of `-0.0` in edge cases. If an application must preserve signed-zero distinctions, define an explicit policy instead of relying on default aggregation.

### 3.2. An Order-Sensitive Example

```java
import java.util.List;

List<Double> samples = List.of(1e16, -1e16, 1.0);

double reduced = samples.stream()
        .reduce(0.0, Double::sum);

System.out.println(reduced);
// With sequential addition in List order: 1.0
```

On a simple sequential pipeline, we typically observe addition following the `List` element order. However, the purpose of this example is not to claim every `reduce` implementation will always use one fixed addition tree: the `reduce` contract primarily requires the operator to be associative to allow parallel execution.

## 4. Why Can `parallelStream().reduce(...)` Produce a Different Result?

In a parallel stream, Java can split data into chunks, reduce each chunk, and then combine partial sums. That splitting and combining is not required to match a sequential left-to-right addition.

```java
List<Double> samples = List.of(1e16, -1e16, 1.0);

double sequential = samples.stream()
        .reduce(0.0, Double::sum);

double parallel = samples.parallelStream()
        .reduce(0.0, Double::sum);

System.out.println("Sequential: " + sequential);
System.out.println("Parallel:   " + parallel);
// Do not assert that the two lines must differ or must match bit-for-bit.
```

Each run can form a valid addition grouping according to its work-splitting strategy:

```text
Source: [1e16, -1e16, 1]

Grouping A: ((1e16 + -1e16) + 1) = 1

Grouping B: (1e16 + (-1e16 + 1)) = 0
```

Java does not promise whether `parallelStream()` will use Grouping A or Grouping B in this example. Actual output can depend on dataset size, `Spliterator` splitting, terminal operation implementation, and runtime environment. **Do not write tests requiring a parallel floating-point sum to equal a sum computed in one specific sequential order.**

### 4.1. Encounter Order and Addition Order Are Different Concerns

A `List` source has a defined encounter order; `toList()` can preserve element order even in a parallel pipeline. Yet **preserving element encounter order does not mean preserving addition grouping** inside `reduce`.

```java
List<Double> values = List.of(1e16, -1e16, 1.0);

System.out.println(values.parallelStream().toList());
// [1.0E16, -1.0E16, 1.0]: element order is preserved

System.out.println(values.parallelStream().reduce(0.0, Double::sum));
// The sum is affected by how partial sums are combined
```

`sequential()` requests sequential processing, yet **it does not turn floating-point arithmetic into exact arithmetic**. Even when always adding sequentially in a fixed order, rounding error can still exist.

### 4.2. Do Not Update a Shared Sum Variable Inside a Lambda

```java
double[] total = {0.0};

// Unsafe: multiple threads update total[0] concurrently.
// values.parallelStream().forEach(x -> total[0] += x);
```

Reading, adding, and writing back to `total[0]` can interleave concurrently, causing a *data race* and lost updates. Even if replaced with a thread-safe adder, addition order can still vary and arithmetic error still exists. Use `reduce` or an appropriate collector so Java manages partial sums; then choose a precision strategy matching your requirements.

## 5. How Do `reduce(Double::sum)` and `DoubleStream.sum()` Differ?

Java provides the specialized terminal operation `DoubleStream.sum()`:

```java
double total = DoubleStream.of(0.1, 0.2).sum();
System.out.println(total);
```

`DoubleStream.sum()` is documented in Java as allowed to use **compensated summation** or other techniques to reduce rounding error when summing floating-point values. Consequently, in many cases, `sum()` can yield better numerical accuracy than writing `reduce(0.0, Double::sum)` yourself.

Key distinctions:

| Criterion | `reduce(0.0, Double::sum)` | `DoubleStream.sum()` |
|---|---|---|
| Meaning | Reduction with a user-supplied operator | Summation via a specialized terminal operation |
| Summation technique | Applies `double` addition on every combine step | Implementation may use compensated summation/other techniques |
| Absolute mathematical exactness | Not guaranteed | **Not** guaranteed |
| Sensitive to order/grouping | Possibly | Possibly |
| Usability on primitive streams | Yes, though more general | Available directly on `DoubleStream` |
| When to choose | Demonstrating `reduce` or using a custom operator | Computing an ordinary `double` sum |

Example:

```java
import java.util.stream.DoubleStream;

double viaReduce = DoubleStream.of(1e16, -1e16, 1.0)
        .reduce(0.0, Double::sum);
double viaSum = DoubleStream.of(1e16, -1e16, 1.0)
        .sum();

System.out.println("reduce = " + viaReduce);
System.out.println("sum    = " + viaSum);
// Evaluate by error tolerance and business rules; do not assume they are always equal.
```

**Do not assume** that `DoubleStream.sum()` must use one specific compensated algorithm or that its output must be bit-stable across every JDK and parallel execution. The API reserves the right to choose an appropriate summation technique and order.

### 5.1. Other Aggregation Terminal Operations

`DoubleStream.average()`, `DoubleSummaryStatistics`, and collectors such as `Collectors.summingDouble`, `Collectors.averagingDouble`, and `Collectors.summarizingDouble` also operate on floating-point numbers. They express intent cleanly, yet **do not eliminate the inherent error of `double`**.

```java
import java.util.DoubleSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

List<Double> readings = List.of(0.1, 0.2, 0.3);

DoubleSummaryStatistics stats = readings.stream()
        .collect(Collectors.summarizingDouble(Double::doubleValue));

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // Approximate double sum
System.out.println(stats.getAverage()); // Approximate double average
```

Note: `average()` on an empty stream returns `OptionalDouble.empty()`; APIs with an identity or statistics may adopt different conventions for the empty case. Do not compute `sum / count` when `count == 0` without a defined handling policy.

## 6. Summing Very Large, Very Small, and Opposite-Sign Data

When values differ greatly in magnitude, small terms can be lost during individual additions. When positive and negative values nearly cancel out, that error can become large **relative to the true sum**.

```java
List<Double> values = List.of(1e16, 1.0, -1e16);

double leftToRight = 0.0;
for (double value : values) {
    leftToRight += value;
}

System.out.println(leftToRight); // 0.0
// The mathematical sum of the three values is 1.0.
```

In the step `1e16 + 1`, the value `1` is rounded away. Subtracting `1e16` afterward leaves `0`. Changing the order to `1e16, -1e16, 1` brings the sequential sum back to `1`.

Additional edge cases to watch for:

- **NaN:** if the input contains `Double.NaN`, additions and the aggregated result can become `NaN`. Do not check `NaN` with `value == Double.NaN`; use `Double.isNaN(value)`.
- **Infinity:** summing huge finite values can overflow to `Infinity`; a sum containing both `+Infinity` and `-Infinity` can produce `NaN`.
- **Sign of zero:** `+0.0` and `-0.0` have different bit patterns; an addition or `+0.0` identity can change the sign.
- **Input overflow/loss of precision:** a value already rounded when parsed into `double` cannot be recovered simply by changing the summation method at the end.

Therefore, “the sum is still a valid `double`” **does not** by itself prove the result is accurate enough for the application.

## 7. Strategies to Improve Accuracy and Reproducibility

No single strategy is optimal for every problem. Clarify whether the application prioritizes **numerical accuracy**, **bit-for-bit reproducibility**, or **speed**.

### 7.1. Prefer `DoubleStream.sum()` for Ordinary Floating-Point Sums

```java
double total = readings.stream()
        .mapToDouble(Double::doubleValue)
        .sum();
```

`mapToDouble` converts `Stream<Double>` to `DoubleStream` and avoids unnecessary boxing during summation. `sum()` expresses intent clearly and lets Java pick an error-reducing technique. However, the result remains approximate.

### 7.2. Control Addition Order When Reproducibility Matters

When you need a repeatable summation procedure for an input with a fixed order, enforce sequential execution, preserve input order, and specify the algorithm explicitly:

```java
static double leftFold(List<Double> values) {
    double total = 0.0;
    for (double value : values) {
        total += value;
    }
    return total;
}
```

This code makes addition in `List` element order explicit; it **does not** eliminate error. If you use a stream, avoid `unordered` sources and do not assume switching to `parallel()` preserves the grouping of a fixed loop.

Sorting values by magnitude before summing can sometimes improve accuracy, yet it is not a universal rule for every data distribution, and reordering can affect business logic. Do not treat `sorted()` as a cure-all for rounding error.

### 7.3. Compensated Summation

Algorithms such as Kahan summation and Neumaier summation use a compensation variable to retain part of the rounding error from prior additions. They often reduce error compared to naive sequential addition, especially when aggregating values of widely varying magnitudes.

However:

- Compensation does not make a `double` result absolutely exact.
- Stateful algorithms must be designed properly if you want to split data and merge results in parallel.
- You cannot casually mutate a shared stateful accumulator inside `parallelStream().forEach(...)` and call it a safe reduction.

For many applications, `DoubleStream.sum()` is a good starting point before writing a custom compensated algorithm and measuring error.

### 7.4. Use `BigDecimal` When Exact Decimal Addition Is Required

For money or data requiring exact decimal addition, `BigDecimal` is generally more suitable than `double`. **Construct from decimal strings**, rather than defaulting to `new BigDecimal(0.1)`.

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> amounts = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal total = amounts.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.60
```

With `BigDecimal` inputs constructed properly from strings, `add` performs **exact** decimal addition without binary rounding like `double`. `BigDecimal` addition does not mutate the source objects; the result is a new object.

```java
System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625

System.out.println(new BigDecimal("0.1")); // 0.1
System.out.println(BigDecimal.valueOf(0.1)); // 0.1
```

`new BigDecimal(0.1)` converts the **exact binary value stored** in the `double` into its exact decimal form. `BigDecimal.valueOf(0.1)` uses `double`'s canonical string representation, which is often cleaner, yet cannot restore original decimal precision if data was already rounded or miscomputed earlier. For financial data, prefer receiving and storing values as decimals right at the source.

Note that `BigDecimal.divide` may require specifying precision or a `RoundingMode` when a quotient is non-terminating; exactness of **addition** does not imply every `BigDecimal` operation automatically yields a finite decimal.

### 7.5. Use Integer Units When the Domain Allows

If business rules allow converting to the smallest unit, such as amounts in cents or measurements in fixed integer units, you can sum using `long` and convert for display at the end:

```java
import java.util.stream.LongStream;

long totalCents = LongStream.of(125, 250, 375).sum();
System.out.println(totalCents); // 750 (cents)
```

Integer summation eliminates binary rounding of fractions, yet **can still overflow**. `LongStream.sum()` does not automatically detect overflow. When overflow detection is needed, use `Math.addExact` in an appropriate algorithm, or use `BigInteger`/`BigDecimal` depending on the domain. Also define rounding rules when converting decimal values into integer units.

## 8. Testing Numerical Results Properly

Direct comparison with `==` is appropriate when testing **exact floating-point value equality**, yet is usually unsuitable for testing approximate computed results:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual == expected); // false
```

For finite values with a business-defined tolerance, you can use a check combining absolute and relative error:

```java
static boolean approximatelyEqual(double a, double b,
                                  double absoluteTolerance,
                                  double relativeTolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return a == b; // NaN is not considered equal.
    }
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return Math.abs(a - b)
            <= absoluteTolerance + relativeTolerance * scale;
}
```

```java
System.out.println(
        approximatelyEqual(0.1 + 0.2, 0.3, 1e-12, 1e-12)
); // true
```

This example illustrates a basic strategy for finite values in ordinary ranges. For extremely large values, `a - b` or threshold calculations can overflow; specialized numerical tasks require comparisons tailored to the domain and expected error. **Do not pick an arbitrary fixed epsilon** and apply it blindly to every scale or calculation.

With `BigDecimal`:

```java
BigDecimal x = new BigDecimal("1.0");
BigDecimal y = new BigDecimal("1.00");

System.out.println(x.compareTo(y) == 0); // true: numerically equal
System.out.println(x.equals(y));         // false: different scale
```

Choose `compareTo` when comparing numeric value; choose `equals` when scale representation itself is part of the requirement.

## 9. Common Mistakes

| Reasoning / code pattern | Problem | How to handle it |
|---|---|---|
| “Mathematical addition is associative, so `Double::sum` is too” | Each `double` addition can round | Accept a tolerance or choose a more accurate numeric type/algorithm |
| “Streams have encounter order, so `reduce` must add strictly left-to-right” | `reduce` may combine partial sums differently | Do not infer an addition tree from element order |
| “Running in parallel only changes speed; `double` results must match bit-for-bit” | Changing addition grouping can alter the result | Use a reproducible strategy or compare with tolerance |
| “Replacing `reduce` with `sum()` guarantees an exact result” | `sum()` can reduce error, not eliminate it | Define precision requirements and choose `BigDecimal` if needed |
| “`new BigDecimal(0.1)` stores exact decimal 0.1” | It stores the exact value of the approximated `double` | Use `new BigDecimal("0.1")` from a decimal source |
| “Just add `sorted()` and addition becomes exact” | Reordering only helps in certain cases | Measure error; use an appropriate algorithm |
| “Using `peek` or `forEach` to add into a shared variable is fine” | Side effects can be skipped, cause data races, or run out of order | Use safe terminal operations and collectors |
| “Testing every `double` sum with `actual == expected`” | Rounding error can fail valid tests | Compare using a justified tolerance |
| “`long` addition is always safe” | It can overflow | Bound the data domain or detect overflow |
| “`Double.NaN == Double.NaN` is true” | `NaN` equals no number, not even itself | Use `Double.isNaN` |

## 10. Complete Runnable Example (Java 17+)

The following program ties together addition order with `reduce`, `DoubleStream.sum()`, and `BigDecimal`:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.DoubleStream;

public class FloatingPointReductionDemo {
    static double leftFold(List<Double> values) {
        double sum = 0.0;
        for (double value : values) {
            sum += value;
        }
        return sum;
    }

    static boolean approximatelyEqual(double a, double b, double epsilon) {
        return Double.isFinite(a)
                && Double.isFinite(b)
                && Math.abs(a - b) <= epsilon;
    }

    public static void main(String[] args) {
        // 1. Binary representation error.
        System.out.println(0.1 + 0.2); // 0.30000000000000004
        System.out.println(0.1 + 0.2 == 0.3); // false

        // 2. Non-associativity.
        double a = 1e16, b = -1e16, c = 1.0;
        System.out.println((a + b) + c); // 1.0
        System.out.println(a + (b + c)); // 0.0

        // 3. Sequential and parallel reduction pipelines.
        List<Double> numbers = List.of(a, b, c);
        double folded = leftFold(numbers);
        double reduced = numbers.stream().reduce(0.0, Double::sum);
        double parallel = numbers.parallelStream().reduce(0.0, Double::sum);
        double summed = numbers.stream().mapToDouble(Double::doubleValue).sum();

        System.out.println("Left fold: " + folded); // 1.0
        System.out.println("Reduce:    " + reduced);
        System.out.println("Parallel:  " + parallel);
        System.out.println("Sum:       " + summed);
        // Do not require reduced/parallel/summed to always be bit-identical.

        // 4. Approximate check in a small value range.
        System.out.println(approximatelyEqual(0.1 + 0.2, 0.3, 1e-12));
        // true

        // 5. Exact decimal sum from String source data.
        BigDecimal money = List.of("0.10", "0.20", "0.30").stream()
                .map(BigDecimal::new)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println(money); // 0.60

        // 6. For ordinary double sums, a specialized API exists.
        System.out.println(DoubleStream.of(2.5, 1.5, 3.0).sum()); // 7.0
    }
}
```

The example does not assert that `parallel` necessarily differs from or equals `reduced`, because understanding the Stream API's freedom to choose how to combine partial results is the key point. The lines with exact output comments correspond to cases whose values are unambiguous for the chosen data.

## 11. Self-Check

1. **Why is `0.1 + 0.2 == 0.3` `false`?** Because these decimal fractions are not represented exactly as `double`; addition introduces another rounding step.
2. **Why can `(a+b)+c` differ from `a+(b+c)` when `a=1e16`, `b=-1e16`, `c=1`?** Because `1` can be lost when added to a large number before the two large numbers cancel out.
3. **Does `reduce(0.0, Double::sum)` guarantee bit-identical results between sequential and parallel runs?** No. Additions can be grouped differently.
4. **Is `DoubleStream.sum()` an exact decimal addition?** No. It can use error-reducing techniques, yet still returns a `double`.
5. **For monetary inputs like `"0.10"` and `"0.20"`, how should `BigDecimal` be constructed?** From decimal strings (`new BigDecimal("0.10")`), avoiding passing values through `double` first.
6. **Do `BigDecimal("1.0")` and `BigDecimal("1.00")` have the same numeric value?** Yes under `compareTo`; `equals` differs because of scale.
7. **Is `parallelStream().forEach(x -> sum += x)` valid?** Unsafe: `sum` is shared state, creating a potential race condition.
8. **How should `double` sums be tested?** Define an acceptable error bound for the data domain, handle `NaN`/infinity explicitly, and compare with an appropriate tolerance.
9. **If you only need the sum of an ordinary finite `DoubleStream`, which API should you try first?** `DoubleStream.sum()`, because it expresses summation directly and can reduce error compared to a simple addition reduction.

**Key takeaway:** Errors in `double` stem from finite binary representation and rounding steps. Because `double` addition is not strictly associative, changing order or grouping in `reduce`—especially under parallel execution—can alter the sum. Choose your data type, summation algorithm, execution mode, and testing policy based on the problem's **accuracy and reproducibility** requirements.
