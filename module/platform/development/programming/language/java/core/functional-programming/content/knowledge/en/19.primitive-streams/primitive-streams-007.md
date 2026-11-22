# Integer Overflow and Floating-Point Error in Java Stream Aggregations

## 1. Why can sum() and average() produce unexpected results?

The primitive streams `IntStream`, `LongStream`, and `DoubleStream` allow calculating sums, averages, extrema, and statistics without boxing each element. For example:

```java
int total = java.util.stream.IntStream.of(1, 2, 3).sum(); // 6
double mean = java.util.stream.DoubleStream.of(1.0, 2.0, 3.0)
        .average().orElseThrow(); // 2.0
```

These two statements are placed inside the body of a Java method. When data is large, has many elements, or has significantly different values, learners must control two **different groups of issues**:

1. **Integer overflow**: the mathematical result exceeds the representation range of `int` or `long`, causing the primitive sum to wrap around (*wraparound*) and **not throw an exception automatically**.
2. **Floating-point error**: `double` numbers have a finite binary representation and addition requires rounding. The sum or average may not match the expected decimal result; the **grouping/addition order** can change the approximated value.

Memorable examples:

```text
Integer.MAX_VALUE + 1 = 2147483648 (mathematical)
IntStream.sum() returns    -2147483648 (int overflow)

0.1 + 0.2 = 0.3            (decimal math)
double may represent       0.30000000000000004
```

Key point: **The Stream API does not turn primitive addition into arbitrary-precision arithmetic**. You must decide the data type, overflow detection method, and acceptable error margin **before** aggregating.

## 2. Review of primitive stream types

| API | Element type | Return type of `sum()` | Return type of `average()` | Notes |
| --- | --- | --- | --- | --- |
| `IntStream` | signed `int`, 32-bit | `int` | `OptionalDouble` | `sum()` can overflow `int` |
| `LongStream` | signed `long`, 64-bit | `long` | `OptionalDouble` | `sum()` can overflow `long` |
| `DoubleStream` | IEEE 754 `double`, 64-bit | `double` | `OptionalDouble` | Has representation/rounding error, `Infinity`/`NaN` |

Range of `int`: from `-2_147_483_648` to `2_147_483_647`; `long`: from `-9_223_372_036_854_775_808L` to `9_223_372_036_854_775_807L`.

The sum of a sequence can exceed the data type's range **even when every element is within range**. For example, two positive integers `2_000_000_000` are both valid in `int`, but their sum `4_000_000_000` is not.

`average()` returns `OptionalDouble` because the source may be empty; how the average is computed should not be inferred as "call `sum()` and divide by `int`" in every implementation. For instance, the average of two large `int` values can still be valid even though `IntStream.sum()` overflows. However, the returned `double` value may also need rounding.

## 3. IntStream.sum(): silent overflow without warning

Example:

```java
int max = Integer.MAX_VALUE;
int result = IntStream.of(max, 1).sum();
System.out.println(result); // -2147483648
```

These are statements inside a method that has imported `java.util.stream.IntStream`. `Integer.MAX_VALUE` is `2_147_483_647`. Adding `1` gives the mathematical result `2_147_483_648`, exceeding `int`.

`IntStream.sum()` uses `int` addition semantics: Java **does not automatically throw `ArithmeticException`** for standard integer addition. The result stored in `int` wraps around in 32-bit representation, here becoming the negative number `-2_147_483_648`.

A risk in applications:

```text
Order quantity/aggregated value expected to be large positive
              |
       IntStream.sum()
              |
     overflows to negative
              |
  business check concludes wrongly
```

The impact is not just "off by a few units", it can flip the sign of the value; a condition like `total > 0` can also return the opposite result.

**You cannot detect every overflow case by checking the sign of the sum.** Adding negative numbers, multiple addition steps, or elements with alternating signs can make the final result look plausible despite intermediate overflow.

## 4. Widen the type **before** addition

If the sum of `int` values may exceed `int` but still fits in `long`, the usual simple approach is to create a `LongStream` **before** `sum()`:

```java
long correct = IntStream.of(Integer.MAX_VALUE, 1)
        .asLongStream()
        .sum(); // 2147483648
```

You can also use:

```java
long alsoCorrect = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToLong(n -> n)
        .sum(); // 2147483648
```

These snippets are statements inside a method that has imported `IntStream`. `asLongStream()` converts each `int` element to `long` before aggregating; `mapToLong` has a similar effect in this case.

**This is the wrong way:**

```java
long wrong = (long) IntStream.of(Integer.MAX_VALUE, 1).sum();
```

`sum()` has already returned the overflowed `int` (`-2_147_483_648`). Casting that wrong result to `long` only produces `-2_147_483_648L`, **not recovering the correct sum**.

Comparison:

| Expression | When type widening occurs | Value |
| --- | --- | --- |
| `(long) IntStream.of(MAX, 1).sum()` | **After** aggregation | `-2147483648` (wrong) |
| `IntStream.of(MAX, 1).asLongStream().sum()` | **Before** aggregation | `2147483648` |
| `IntStream.of(MAX, 1).mapToLong(n -> n).sum()` | **Before** aggregation | `2147483648` |

**Limitation:** `long` also has a finite range. Widening `int → long` only solves the problem when **the expected sum fits in `long`**. Do not treat this as an unlimited-precision integer solution.

## 5. LongStream.sum(): 64-bit overflow can still happen

`LongStream.sum()` returns `long`; it does not automatically promote to `BigInteger`.

```java
long wrapped = LongStream.of(Long.MAX_VALUE, 1L).sum();
// -9223372036854775808
```

This is a snippet placed inside a method that has imported `java.util.stream.LongStream`.

With inputs `Long.MAX_VALUE` (`9_223_372_036_854_775_807`) and `1`, the mathematical sum is `9_223_372_036_854_775_808`. The `long` result wraps around to `Long.MIN_VALUE`.

You cannot "widen to `double`" and assume integer precision. `double` has a finite significand (53-bit precision) and cannot accurately represent every large `long` integer value. Switching to `double` only trades an **overflow error** for a different **rounding/precision** problem.

When values may exceed `long` and an exact sum is still required, consider `BigInteger` or designing the data according to the business domain.

## 6. Need to detect overflow? Use Math.addExact()

If exceeding the type range is an **error that must be reported**, you can use `Math.addExact` in the aggregation:

```java
int checked = IntStream.of(1, 2, 3)
        .reduce(0, Math::addExact); // 6
```

These are illustrative statements in a method with `IntStream`. The `Math.addExact(int, int)` method (and its `long` overload) **throws `ArithmeticException`** if the addition at that step overflows.

Error-catching example:

```java
try {
    int checked = IntStream.of(Integer.MAX_VALUE, 1)
            .reduce(0, Math::addExact);
    System.out.println(checked);
} catch (ArithmeticException e) {
    System.out.println("overflow");
}
```

The output is `overflow` on Java 17. `LongStream.of(Long.MAX_VALUE,1L).reduce(0L, Math::addExact)` also throws `ArithmeticException`.

**Warning about intermediate sums:** even when the **final mathematical sum** is within range, the addition order may still pass through an out-of-range value. For example, `[Integer.MAX_VALUE, 1, -1]` has a final sum of `Integer.MAX_VALUE`, but when sequentially adding `MAX + 1` first, `Math.addExact` will detect overflow. Therefore, `reduce(0, Math::addExact)` is a way to **check the actual addition steps**, not an algorithm that computes an unbounded sum and only checks the final result.

In parallel processing, the grouping of elements may differ; this further reinforces the need to use `BigInteger` when you require the **exact mathematical sum** before checking the output range.

## 7. BigInteger: exact for large integer sums

`BigInteger` represents integers whose practical magnitude is limited only by memory resources, not restricted to 32 or 64 bits like `int`/`long`.

```java
BigInteger exact = LongStream.of(Long.MAX_VALUE, 1L)
        .mapToObj(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(exact); // 9223372036854775808
```

These are statements inside a method that has imported `java.math.BigInteger` and `LongStream`. Each element is converted to `BigInteger` **before** addition. The value `BigInteger.ZERO` is the identity element of addition.

Similar example with `IntStream`:

```java
BigInteger exactInt = IntStream.of(Integer.MAX_VALUE, 1)
        .mapToObj(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);
```

The sum is `2147483648`, with no overflow.

Trade-off: `BigInteger` operations can incur more allocation/memory and CPU overhead than primitive addition. Choose based on the **actual value range** and precision requirements; do not use `BigInteger` unconditionally for every small sequence.

If you need to convert `BigInteger` back to `long` while detecting out-of-range values, use `longValueExact()` instead of `longValue()`: the `Exact` method throws `ArithmeticException` when it cannot be represented exactly.

## 8. summaryStatistics() and average() differ from sum() in sum type

Java provides `IntStream.summaryStatistics()` which returns `IntSummaryStatistics`. This object stores the sum as a `long`, unlike `IntStream.sum()` which returns `int`:

```java
IntSummaryStatistics stats =
        IntStream.of(Integer.MAX_VALUE, 1).summaryStatistics();

System.out.println(stats.getSum()); // 2147483648
System.out.println(stats.getAverage()); // 1.073741824E9
```

The illustrative snippet imports `java.util.IntSummaryStatistics` and `IntStream`. `getAverage()` returns `double`, which in this case accurately represents `1_073_741_824.0`.

`IntStream.of(Integer.MAX_VALUE,1).average().orElseThrow()` also returns an average represented as `1.073741824E9` in the Java 17 test program. **Do not infer** that `average()` always computes the average by calling `IntStream.sum()` and dividing by the count, because `sum()` could have overflowed `int`.

However, you still must check limits:

- `IntSummaryStatistics.getSum()` has type `long`, which is still finite.
- `LongStream.summaryStatistics()` and `LongSummaryStatistics.getSum()` use `long`; they cannot automatically save a sum that exceeds `long`.
- Averages represented as `double` can **round** for large integers or precision-sensitive data.
- For an empty stream, `average()` returns `OptionalDouble.empty()`; calling `orElseThrow()` when empty will throw an exception.

`summaryStatistics` is useful when you need `count`, `sum`, `min`, `max`, and `average` simultaneously, but **it is not an arbitrary-precision aggregation tool**.

## 9. Complete Java 17 program: integer overflow

Create the file `IntegerAggregateSafetyDemo.java`:

```java
import java.math.BigInteger;
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class IntegerAggregateSafetyDemo {
    public static void main(String[] args) {
        int max = Integer.MAX_VALUE;
        System.out.println("intMax=" + max);
        System.out.println("intSumOverflow=" + IntStream.of(max, 1).sum());
        System.out.println("widenAfterOverflow=" + (long) IntStream.of(max, 1).sum());
        System.out.println("intToLongBeforeSum=" + IntStream.of(max, 1).asLongStream().sum());
        System.out.println("mapToLongBeforeSum=" +
                IntStream.of(max, 1).mapToLong(n -> n).sum());

        IntSummaryStatistics stats = IntStream.of(max, 1).summaryStatistics();
        System.out.println("intStatsSum=" + stats.getSum());
        System.out.println("intStatsAverage=" + stats.getAverage());
        System.out.println("intAverage=" +
                IntStream.of(max, 1).average().orElseThrow());

        System.out.println("longMax=" + Long.MAX_VALUE);
        System.out.println("longSumOverflow=" +
                LongStream.of(Long.MAX_VALUE, 1L).sum());
        BigInteger exactLong = LongStream.of(Long.MAX_VALUE, 1L)
                .mapToObj(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add);
        System.out.println("bigIntegerSum=" + exactLong);

        try {
            System.out.println("checkedIntSum=" +
                    IntStream.of(max, 1).reduce(0, Math::addExact));
        } catch (ArithmeticException e) {
            System.out.println("checkedIntSum=overflow");
        }

        try {
            System.out.println("checkedLongSum=" +
                    LongStream.of(Long.MAX_VALUE, 1L)
                            .reduce(0L, Math::addExact));
        } catch (ArithmeticException e) {
            System.out.println("checkedLongSum=overflow");
        }

        System.out.println("exactIntBigInteger=" + IntStream.of(max, 1)
                .mapToObj(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add));

        try {
            IntStream.of(max, 1, -1).reduce(0, Math::addExact);
            System.out.println("intermediate=ok");
        } catch (ArithmeticException e) {
            System.out.println("intermediate=overflow");
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 IntegerAggregateSafetyDemo.java
java IntegerAggregateSafetyDemo
```

Verified output:

```text
intMax=2147483647
intSumOverflow=-2147483648
widenAfterOverflow=-2147483648
intToLongBeforeSum=2147483648
mapToLongBeforeSum=2147483648
intStatsSum=2147483648
intStatsAverage=1.073741824E9
intAverage=1.073741824E9
longMax=9223372036854775807
longSumOverflow=-9223372036854775808
bigIntegerSum=9223372036854775808
checkedIntSum=overflow
checkedLongSum=overflow
exactIntBigInteger=2147483648
intermediate=overflow
```

The result groups are intentionally placed side by side: **casting after overflow** is still wrong; **widening to long before sum** is correct when the sum fits in long; **Math.addExact** detects overflow; **BigInteger** preserves the exact mathematical sum.

For inputs containing elements that can change signs, note that `intermediate=overflow` illustrates the sequential addition path passing through an out-of-range value, even though the final mathematical sum of the three elements still fits in `int`.

## 10. DoubleStream: why can 0.1 + 0.2 not equal 0.3?

The `double` type uses **binary** floating-point representation (per IEEE 754). Decimal numbers such as `0.1`, `0.2`, and `0.3` generally **do not have an exact finite binary representation**. When stored as `double`, the value is rounded to a representable binary number.

Therefore:

```java
double total = DoubleStream.of(0.1, 0.2).sum();
System.out.println(total); // 0.30000000000000004 on tested Java 17
```

This snippet is in a method that has imported `DoubleStream`. The result is not because "Stream adds incorrectly", but comes from **floating-point representation and rounding limits**. Even `0.1 + 0.2` without Stream produces that value in the test program.

The error is usually small relative to the scale of the numbers, but **you cannot conclude that every error is negligible**: when summing a large number of elements, subtracting close numbers, or having financial/high-precision requirements, errors can affect business decisions.

`DoubleStream.sum()` may use compensated summation (*compensated summation*) to reduce error, depending on the implementation, but **it does not guarantee an exact decimal result**; the Javadoc explicitly states that floating-point summation can depend on aggregation order.

## 11. Addition order can change the double result

In mathematical real numbers, addition is associative: `(a + b) + c = a + (b + c)`. In rounded floating-point addition, that equality **is not guaranteed**.

Consider the three numbers `1e16`, `1.0`, and `-1e16`. Mathematically, the sum is `1.0`. However, when adding `1e16 + 1.0`, the `1.0` part is very small compared to `1e16` and can be lost due to rounding. A different addition order can preserve `1.0`.

The tested Java 17 program gives:

```java
double first = DoubleStream.of(1e16, 1.0, -1e16).sum();
double second = DoubleStream.of(1e16, -1e16, 1.0).sum();
```

The observed results from the program in section 14 are `first = 0.0`, `second = 1.0`. **You should not treat these two specific numbers as a mandatory guarantee across all JDKs/aggregation algorithms**: the `DoubleStream.sum()` specification does not fix the addition order, and an implementation may use a different error-reduction technique. The point illustrated is that **floating-point aggregation can be sensitive to order and grouping of additions**.

With **parallel** streams, partial sums may be computed in groups and then combined, not necessarily matching left-to-right addition. Therefore, using `parallel()` can change rounding results in the low-order digits, even when the data source does not change.

If a process requires **reproducible results** at high precision, define the order, algorithm, and appropriate numeric type upfront; do not rely solely on the fact that the value is returned as `double`.

## 12. average(), Infinity, and NaN

`DoubleStream.average()` returns `OptionalDouble`; it is affected by floating-point representation and summation. For example:

```java
double average = DoubleStream.of(0.1, 0.2)
        .average().orElseThrow();
```

In the test program, the printed value is `0.15000000000000002`, not the exact decimal string `0.15`.

There are two additional special values to watch out for:

- **`Infinity`**: summing very large finite `double` values can overflow the finite floating-point range and yield `Double.POSITIVE_INFINITY` (or negative infinity correspondingly).
- **`NaN`** (*not a number*): if the input contains `Double.NaN`, `DoubleStream.sum()` returns `NaN`; results can become meaningless if input validation is skipped.

Test example:

```java
System.out.println(DoubleStream.of(
        Double.MAX_VALUE, Double.MAX_VALUE).sum()); // Infinity
System.out.println(DoubleStream.of(
        1.0, Double.NaN).sum()); // NaN
```

These are illustrative statements in a method that has imported `DoubleStream`.

When building aggregations for reports, define a policy **for non-finite values** (`Double.isFinite(value)`, `Double.isNaN(value)`) instead of automatically rounding or displaying them as valid values.

## 13. When should you use BigDecimal?

For decimal calculations that require exact results according to decimal rules (especially currency), `BigDecimal` is usually more suitable than `double`.

```java
BigDecimal exact = Stream.of("0.1", "0.2")
        .map(BigDecimal::new)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(exact); // 0.3
```

This is an illustrative snippet inside a method, requiring imports `java.math.BigDecimal` and `java.util.stream.Stream`. Creating `BigDecimal` from the **original decimal string** allows exact representation of `0.1` and `0.2`.

In the complete program, we also use:

```java
BigDecimal value = DoubleStream.of(0.1, 0.2)
        .mapToObj(BigDecimal::valueOf)
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

`BigDecimal.valueOf(double)` converts through the canonical decimal representation of `Double.toString`, so in this **specific example** it gives `0.3`. However, if a `double` value was already rounded in an earlier operation, converting to `BigDecimal` **cannot recover the lost original decimal data**. When you have a choice, read monetary amounts directly from strings, integer minor units, or `BigDecimal` data from the start.

Avoid:

```text
new BigDecimal(0.1) // Does not accurately represent "0.1" in the decimal sense
```

This is a warning expression, not a standalone program. This constructor takes the **actual binary value** of `double`, which can produce a long string of decimal digits. Prefer `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` when you clearly understand the conversion semantics.

`BigDecimal` does not automatically make all business logic "error-free": **division** can produce repeating decimals and requires an appropriate `MathContext`, `scale`, or `RoundingMode`. Rounding rules must be part of the business design.

## 14. Complete Java 17 program: floating-point error

Create the file `FloatingAggregatePrecisionDemo.java`:

```java
import java.math.BigDecimal;
import java.util.stream.DoubleStream;

public class FloatingAggregatePrecisionDemo {
    public static void main(String[] args) {
        System.out.println("binarySum=" + DoubleStream.of(0.1, 0.2).sum());
        System.out.println("naiveAddition=" + (0.1 + 0.2));

        double a = DoubleStream.of(1e16, 1.0, -1e16).sum();
        double b = DoubleStream.of(1e16, -1e16, 1.0).sum();
        System.out.println("orderedA=" + a);
        System.out.println("orderedB=" + b);

        System.out.println("average=" +
                DoubleStream.of(0.1, 0.2).average().orElseThrow());

        BigDecimal exact = DoubleStream.of(0.1, 0.2)
                .mapToObj(BigDecimal::valueOf)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        System.out.println("bigDecimalSum=" + exact);
        System.out.println("stringDecimal=" +
                new BigDecimal("0.1").add(new BigDecimal("0.2")));

        System.out.println("positiveInfinity=" +
                DoubleStream.of(Double.MAX_VALUE, Double.MAX_VALUE).sum());
        System.out.println("containsNaN=" +
                DoubleStream.of(1.0, Double.NaN).sum());
        System.out.println("equality=" +
                (DoubleStream.of(0.1, 0.2).sum() == 0.3));
        System.out.println("closeEnough=" +
                (Math.abs(DoubleStream.of(0.1, 0.2).sum() - 0.3) <= 1e-12));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 FloatingAggregatePrecisionDemo.java
java FloatingAggregatePrecisionDemo
```

Actual output on the Java 17 environment used to verify this lesson:

```text
binarySum=0.30000000000000004
naiveAddition=0.30000000000000004
orderedA=0.0
orderedB=1.0
average=0.15000000000000002
bigDecimalSum=0.3
stringDecimal=0.3
positiveInfinity=Infinity
containsNaN=NaN
equality=false
closeEnough=true
```

**Important:** the lines demonstrating `DoubleStream.sum()` addition order were recorded from the tested JDK; the specification does not require every implementation to print `orderedA=0.0` and `orderedB=1.0`. When teaching or testing on another JDK, focus on the floating-point contract and error risks, not locking business logic to those two ordered outputs.

The `equality=false` example illustrates how directly comparing `double` with `==` can be surprising. `closeEnough=true` illustrates approximate comparison with an appropriate tolerance for the example; how to choose a practical tolerance will be explained in the next section.

## 15. Comparing doubles with tolerance

For scientific calculations or floating-point data with expected error, comparisons often need an **absolute tolerance** or **relative tolerance**, instead of defaulting to `a == b`:

```java
static boolean approximatelyEqual(
        double a, double b,
        double absoluteTolerance,
        double relativeTolerance) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(
            absoluteTolerance, relativeTolerance * scale);
}
```

This is an **illustrative method** to be placed inside a Java class, not a standalone call. Choose `absoluteTolerance` appropriately near zero, and `relativeTolerance` appropriately when the scale is large. In real applications, verify that both tolerances are finite and non-negative, and carefully consider overflow in intermediate calculations; the simple example above is not a comparison library for all IEEE 754 cases.

Do not pick `1e-12` as a universal constant. The same absolute error can be huge for data around `1e-15` yet negligible for data around `1e9`. Base it on measurement requirements, value ranges, and acceptable error.

For **currency, discrete item counts, balances, or legal conditions requiring exact equality**, a better choice is usually an exact data model (`long` minor units within a safe range, `BigInteger`, or `BigDecimal`) rather than "approximately comparing monetary amounts".

## 16. Caution with reduce(), parallel(), and addition algorithms

Some custom aggregation approaches:

```java
int total = IntStream.of(1, 2, 3).reduce(0, Integer::sum);
double amount = DoubleStream.of(0.1, 0.2)
        .reduce(0.0, Double::sum);
```

These two statements are placed in a method that has imported `IntStream` and `DoubleStream`.

Using `reduce` **does not automatically solve** overflow or error: `Integer::sum` still adds `int` and can overflow; `Double::sum` still rounds `double`. Furthermore, `DoubleStream.sum()` may use a compensated summation algorithm, so you should not assume `reduce(0.0, Double::sum)` always gives the same precision or exact result as `sum()`.

In parallel reduction, the stream may combine partial sums in a different tree structure. Floating-point addition is **not representationally associative**; therefore, the low-order digits of the result can change. With `Math.addExact`, different grouping can cause overflow at different steps, even if the final mathematical sum is representable.

When you need integer aggregation that is **exact regardless of grouping order**, `BigInteger::add` is an operation aligned with mathematical semantics. When an exact decimal result is needed, `BigDecimal::add` is usually appropriate if the operands were created accurately and not previously rounded.

## 17. Choosing a technique by requirement

| Requirement | Usually appropriate approach | What to check |
| --- | --- | --- |
| `int` sum guaranteed to fit in `int` | `IntStream.sum()` | Know the element count and value limits |
| `int` sum may exceed `int`, guaranteed to fit in `long` | `asLongStream().sum()` | Widen **before** summing |
| `long` sum guaranteed to fit in `long` | `LongStream.sum()` | Sum limit, not just element limit |
| Want explicit error when addition overflows | `reduce(0, Math::addExact)` | May throw on intermediate sums |
| Integer sum exceeding `long`, exactness required | `BigInteger` + `reduce(BigInteger.ZERO, BigInteger::add)` | Allocation cost, data size |
| `double` sum for calculations with acceptable error | `DoubleStream.sum()` | Control NaN/Infinity, tolerance, order |
| Exact decimal monetary sum | `BigDecimal` from canonical decimal data | Scale, rounding, input parsing |
| Need average when stream may be empty | `average()` + handle `OptionalDouble` | Do not call `getAsDouble` when no value is present |
| Need `IntStream` statistics | `summaryStatistics()` | `getSum()` is long, still finite |
| Need strictly reproducible results | Define algorithm, order, and numeric type | Do not rely on arbitrary reduction order |

How to choose before coding: determine the **value range of each element**, the **limit on element count**, the **mathematical sum limit**, **error/precision requirements**, and whether the pipeline runs in **parallel**.

## 18. Common mistakes and fixes

| Mistake / misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| Assigning `IntStream.sum()` to `long` to avoid overflow | Overflow happens **before** assignment | `asLongStream()` or `mapToLong()` before `sum()` |
| Assuming `LongStream.sum()` never overflows | `long` is only 64 bits | Use `BigInteger` if range can be exceeded |
| Using `Integer::sum` in `reduce` to "check" overflow | `Integer::sum` does not report overflow | `Math.addExact` when fail-fast is desired |
| Thinking `Math.addExact` only checks the final sum | It checks **each addition performed** | Use `BigInteger` if exact final sum is needed regardless of grouping |
| Converting large `long` to `double` to hold the sum | `double` cannot represent all large integers | `BigInteger` when exact integers are required |
| Assuming `0.1 + 0.2 == 0.3` is always true | Binary representation of decimals has error | Use appropriate tolerance or `BigDecimal` |
| Assuming `DoubleStream.sum()` always yields the same result in any order | Floating-point addition rounds and is not strictly associative | Design algorithm/numeric type per requirements |
| `new BigDecimal(0.1)` always equals decimal `0.1` | Constructor takes the actual binary `double` | `new BigDecimal("0.1")` or `BigDecimal.valueOf(0.1)` |
| Converting computed `double` data to `BigDecimal` to restore precision | Prior rounding error cannot be recovered | Read/store exact data from the start |
| Using `average().orElseThrow()` on an empty stream | `OptionalDouble` is empty | Use `isPresent()`, `orElse(...)`, or an appropriate policy |
| Ignoring `NaN`/`Infinity` in reports | Can produce meaningless/non-finite results | Define validation and handling policy |
| Using arbitrary tolerance for monetary amounts | May accept impermissible business discrepancies | Model exact decimal values |

## 19. Self-check exercises (with answers)

**Exercise 1 — int overflow.** What is the result of `IntStream.of(Integer.MAX_VALUE, 1).sum()`? Does `long n = ...sum()` fix it?

Answer: the `int` result is `-2147483648`. Assigning to `long` **does not fix it**, because overflow happens beforehand. Each element must be converted to `long` before addition.

**Exercise 2 — LongStream.** What does `IntStream.of(Integer.MAX_VALUE, 1).asLongStream().sum()` return?

Answer: `2147483648`, because both elements are widened to `long` before addition.

**Exercise 3 — Long overflow.** What is the mathematical sum of `Long.MAX_VALUE + 1` and what type should be used to represent it accurately?

Answer: `9223372036854775808`, which exceeds `long`. Use `BigInteger`, for example mapping with `BigInteger::valueOf` and then `reduce(BigInteger.ZERO, BigInteger::add)`.

**Exercise 4 — Overflow check.** Can `IntStream.of(Integer.MAX_VALUE,1,-1).reduce(0,Math::addExact)` throw `ArithmeticException` even though the final mathematical sum is `Integer.MAX_VALUE`?

Answer: **Yes**. Sequential addition encounters `MAX+1` first, exceeding the `int` range; `Math.addExact` reports overflow at the intermediate addition.

**Exercise 5 — Decimal error.** Why can `DoubleStream.of(0.1,0.2).sum() == 0.3` be `false`?

Answer: `double` uses rounded binary representation, so the sum can be `0.30000000000000004`. Use `BigDecimal` for exact decimal values or compare with tolerance if the problem accepts error.

**Exercise 6 — Order.** Why can `DoubleStream.of(1e16,1,-1e16).sum()` differ from `DoubleStream.of(1e16,-1e16,1).sum()`?

Answer: `double` addition rounds at each step; when adding a very large number with a very small number, the small part can be lost. Grouping/order and the summation algorithm affect error; the JDK does not guarantee a single fixed addition order across all implementations.

**Exercise 7 — BigDecimal.** State how to create two decimal numbers `0.1` and `0.2` so their sum is an exact `0.3`.

Answer: `new BigDecimal("0.1").add(new BigDecimal("0.2"))`, or read two strings and then `Stream.of(...).map(BigDecimal::new).reduce(...)`. Avoid relying on `double` values that have already lost information.

**Exercise 8 — Average.** Why should you not replace `IntStream.average()` with `(double) intStream.sum()/count` when values are large?

Answer: `IntStream.sum()` can overflow `int` **before** converting to `double`. An appropriate algorithm/intermediate type must be chosen; `average()` is the dedicated API and still requires attention to `OptionalDouble` and precision.

**Exercise 9 — Finiteness.** What can `DoubleStream.of(Double.MAX_VALUE, Double.MAX_VALUE).sum()` return?

Answer: `Infinity`, even though each input element is finite, because the sum exceeds the finite representable range. You should check with `Double.isFinite(result)` if the business logic does not accept infinity.

## 20. Checklist before putting aggregations into production

1. **Identify the source:** `IntStream`, `LongStream`, `DoubleStream`, or exact decimal data?
2. **Determine the sum range:** not just individual elements, but also whether `count × max magnitude` and intermediate addition steps can exceed the range?
3. **Choose overflow handling:** widen type before `sum()`, `Math.addExact` to fail on error, or `BigInteger` for precision not limited by primitive types?
4. **Determine floating-point requirements:** how much error is acceptable, are deterministic results needed, and does the data originate from exact decimals?
5. **Check special values:** empty streams, `NaN`, `Infinity`, negative numbers, and very large and very small numbers mixed together.
6. **Run boundary tests:** `Integer.MAX_VALUE + 1`, `Long.MAX_VALUE + 1`, `0.1 + 0.2`, `1e16 + 1 - 1e16`.
7. **Test parallel mode if used:** avoid depending on low-order digits of `double` or side effects of reduction.
8. **Document business policy clearly:** fail-fast, value bounds, rule-based rounding, or exact calculation with another data type.

## 21. Key takeaways

- `IntStream.sum()` returns `int` and **can overflow silently**; `LongStream.sum()` behaves similarly with `long`.
- **Widen the type before adding**: `asLongStream().sum()`, not `(long) intStream.sum()`.
- Use `Math.addExact` when you want to check overflow **at each addition performed**, and use `BigInteger` when you need exact integer sums not limited by primitives.
- `IntSummaryStatistics.getSum()` uses `long`; `average()` returns `OptionalDouble`. Do not treat every statistics API as a clone of `IntStream.sum()`.
- `DoubleStream.sum()` is subject to **rounding error**, can vary by order/grouping, and does not guarantee exact decimal results; special values `NaN` and `Infinity` must also be considered.
- **Currency and decimal data requiring absolute accuracy**: prefer `BigDecimal` created from exact data; do not expect converting an already inaccurate `double` to `BigDecimal` to recover the original data.
- Choose the numeric type and error policy based on **business requirements**, not just Stream syntax convenience.

Official references: [Java 17 IntStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/IntStream.html), [LongStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/LongStream.html), [DoubleStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/DoubleStream.html), [Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(int,int)), [BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html), [BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html).