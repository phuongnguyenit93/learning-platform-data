# NaN, Infinity, Signed Zero, and Subnormals in Java

## 1. Why Must You Understand Special Values?

Java's `float` and `double` represent binary floating-point numbers according to IEEE 754 rules. Beyond ordinary finite numbers, they include **NaN** (*Not a Number*), **positive/negative infinity**, **signed zero** (+0.0 and -0.0), and **subnormal numbers** (finite nonzero numbers smaller in magnitude than the smallest positive normal number).

These values directly affect division, comparison, sorting, statistics, testing, formatting, storage, and API data handling. You can encounter a result that looks “valid” as a `double` type yet violates business constraints.

Distinctions to make right away:

| Case | Example | Property |
| --- | --- | --- |
| NaN | `0.0 / 0.0` | Not a numeric value with ordinary ordering |
| Positive infinity | `1.0 / 0.0` | Greater than every finite number in floating-point comparisons |
| Negative infinity | `-1.0 / 0.0` | Less than every finite number in floating-point comparisons |
| Positive zero | `+0.0` | Zero with a positive sign bit |
| Negative zero | `-0.0` | Zero with a negative sign bit; can give different results in some operations |
| Smallest positive subnormal | `Double.MIN_VALUE` | Smallest nonzero positive finite value of `double` |

**Constant-name warning:** `Double.MIN_VALUE` is **not** the most negative finite number. It is `4.9E-324`, a positive subnormal number. The finite negative value largest in magnitude near the bottom of the representable range is `-Double.MAX_VALUE`. The threshold for the smallest positive *normal* number is `Double.MIN_NORMAL`.

## 2. Foundations of `double` and `float` Representation

A `double` value has 64 bits, commonly described as 1 sign bit, 11 exponent bits, and 52 fraction bits. A `float` has 32 bits with 1 sign bit, 8 exponent bits, and 23 fraction bits. Normal numbers use a significand with an implicit leading bit, giving precision of about 53 and 24 binary bits respectively.

Conceptual model:

```text
double = sign (1 bit) | exponent (11 bits) | fraction (52 bits)

Ordinary exponent + fraction → finite normal number
All-1s exponent, fraction = 0 → +Infinity or -Infinity
All-1s exponent, fraction ≠ 0 → NaN
All-0s exponent, fraction = 0 → +0.0 or -0.0
All-0s exponent, fraction ≠ 0 → subnormal number
```

`float` uses the same representation categories, with different bit counts. This is the mechanism of **binary floating-point types**, not `BigDecimal`. Do not extrapolate this bit layout to `BigInteger` or integral types.

Since Java 17, floating-point semantics are always strict per the Java specification; the `strictfp` modifier is no longer needed to obtain consistent semantics as before. Even so, math library functions have their own precision contracts; do not assume every calculation is as exact as real-number arithmetic.

## 3. NaN — Result of an Undefined Operation

NaN stands for *Not a Number*. Examples:

```java
double a = 0.0 / 0.0;
double b = Math.sqrt(-1.0);
double c = Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY;
double d = Double.POSITIVE_INFINITY * 0.0;
```

All four variables hold NaN in Java. These are illustrative statements that must be placed inside a method to run.

**Floating-point division 0.0 / 0.0 returns NaN**, rather than throwing `ArithmeticException` as integer division by 0 does. For example, `int x = 1 / 0;` compiles, yet throws `ArithmeticException` at runtime; with an integer variable holding 0 as denominator, division also throws this exception. With `double`, dividing a nonzero finite number by ±0.0 typically produces signed infinity.

### 3.1. Primitive Comparisons with NaN

NaN has no ordinary ordering relationship with other numbers — including itself:

```java
double x = Double.NaN;

System.out.println(x == x);  // false
System.out.println(x != x);  // true
System.out.println(x < 1.0); // false
System.out.println(x > 1.0); // false
System.out.println(x <= 1.0);// false
System.out.println(x >= 1.0);// false
```

Do not use `value == Double.NaN` to detect NaN: it is **always false**. Use:

```java
boolean isNan = Double.isNaN(value);
boolean isNanFloat = Float.isNaN(floatValue);
```

These two lines assume `value` has type `double`, `floatValue` has type `float`, and they are inside a method.

### 3.2. Why Does `Double.equals` Differ from the `==` Operator?

`Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` returns **true** per the wrapper class contract, even though `doubleNaN == doubleNaN` returns false. `Double.compare` establishes a total order so collection APIs can sort; in this order, NaN values are treated as equal in the comparator and **greater than `Double.POSITIVE_INFINITY`**.

Therefore, distinguish:

- `==`, `<`, `>`: primitive comparison operators; NaN is not equal to any number.
- `Double.isNaN`: detects NaN in the intended sense.
- `Double.equals`, `Double.hashCode`: object/hash contract, in which all NaN representations are treated equivalently for equality checks.
- `Double.compare`: ordering usable for sorting, with special rules for NaN and signed zero.

NaN can carry various payload bits internally. `Double.doubleToLongBits` normalizes NaN to a canonical form; `Double.doubleToRawLongBits` preserves the raw bits of the input. Do not rely on the specific payload of an operation's result to infer the cause of NaN in business logic.

## 4. Positive and Negative Infinity

Java has `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY`, along with `Float.POSITIVE_INFINITY` and `Float.NEGATIVE_INFINITY`.

```java
double positive = 1.0 / 0.0;   // Infinity
double negative = -1.0 / 0.0;  // -Infinity
double overflow = Double.MAX_VALUE * 2.0; // Infinity
```

Several important results:

| Operation | Result |
| --- | --- |
| `1.0 / +0.0` | `Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `-1.0 / +0.0` | `-Infinity` |
| `1.0 / Double.POSITIVE_INFINITY` | `0.0` |
| `Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY` | `NaN` |
| `0.0 * Double.POSITIVE_INFINITY` | `NaN` |
| `Double.MAX_VALUE * 2.0` | `Infinity` |

Infinity is **different from NaN**: `Double.isInfinite(positive)` is true, `Double.isNaN(positive)` is false. Infinity is also **not finite**. Operations can propagate infinity, turn two opposite-sign infinities into NaN, or return zero.

Do not treat infinity as “a very large but normal number” when the domain requires finite sizes, durations, prices, or ratios. Operations can overflow from completely finite inputs into infinity; therefore input-only validation is insufficient.

## 5. Signed Zero: `+0.0` and `-0.0` Are Equal Under `==` Yet Have Different Bits

IEEE 754 has two representations for zero: `+0.0` and `-0.0`. Under primitive comparison:

```java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero); // Infinity
System.out.println(1.0 / negativeZero); // -Infinity
```

Thus, `==` considers the two numbers numerically equal, yet some operations still distinguish the sign bit. Negative zero can arise from an arithmetic result that is negative and too small and underflows, from the literal `-0.0`, or from conversions that preserve sign.

**Three different ways to distinguish them:**

- `negativeZero == 0.0` is true, insufficient to detect the sign.
- `Double.compare(-0.0, +0.0) < 0` is true under the wrapper's total order.
- `Double.doubleToRawLongBits(-0.0) == Long.MIN_VALUE` is true: the highest sign bit is set, and all remaining bits are 0.

Under `Double.equals`, `Double.valueOf(-0.0).equals(Double.valueOf(+0.0))` is **false**. That differs from primitive `==`. `Double.hashCode` must also uphold the `equals` contract, so corresponding hash codes can differ.

### 5.1. Impact on `HashSet` and Sorting

When using `HashSet<Double>`, `+0.0` and `-0.0` are **two distinct elements under `equals`**. For NaN, two NaN values with different raw payload bits are still treated as equal by the wrapper.

A set containing `+0.0`, `-0.0`, a first NaN, and a second NaN can have size **3**, not 2 or 4. Similarly, `TreeSet<Double>` uses `Double.compare`, so it separates signed zeros and merges NaNs. This behavior differs from how primitive `==` treats them; do not substitute those rules carelessly.

Library operations like `Math.min(+0.0, -0.0)` return `-0.0`, while `Math.max(+0.0, -0.0)` return `+0.0`; if an argument is NaN, `Math.min` and `Math.max` return NaN. These are useful edge cases when testing min/max logic.

## 6. Subnormals: The Region Very Close to 0 and Gradual Underflow

**Normal** numbers use a significand with an implicit leading bit; **subnormal** numbers have a zero exponent field and a nonzero fraction field. Subnormals allow representing numbers near 0 smaller than the smallest normal threshold with gradually decreasing precision (*gradual underflow*).

For `double`:

- `Double.MIN_NORMAL` = `2.2250738585072014E-308`, the smallest positive normal number.
- `Double.MIN_VALUE` = `4.9E-324`, the smallest nonzero positive subnormal number.
- A finite number `x` is subnormal when `0 < Math.abs(x) && Math.abs(x) < Double.MIN_NORMAL`.
- `Double.MIN_VALUE / 2.0` rounds to `+0.0`, because the mathematical result is too small to represent as a nonzero `double`.
- `Math.nextUp(0.0)` is `Double.MIN_VALUE`; `Math.nextDown(0.0)` is `-Double.MIN_VALUE`.

`Float.MIN_NORMAL` and `Float.MIN_VALUE` play the corresponding roles for `float`. Do not use `Double.MIN_VALUE` to describe the most negative range; this short name means the **smallest positive** value.

### 6.1. Do Not Confuse Subnormals with Zero, NaN, or Infinity

A subnormal is still a finite, nonzero number. It can participate in addition, subtraction, multiplication, and division, and `Double.isFinite` returns true. However, the spacing between representable values in the subnormal region causes **relative precision to degrade**.

A very small calculation can:

1. Produce a nonzero subnormal result.
2. Shrink further, then round to signed zero.
3. Once the result is completely lost to underflow, `value == 0.0` can be true even though the mathematical result was not 0.

This is why you should not use `x == 0.0` as proof that a numerical algorithm experienced no underflow. If an application handles tiny probabilities, log-likelihood normalization, matrices with very small coefficients, or scaling divisions, consider value ranges and numerically stable algorithms.

## 7. Runnable Java 17+ Program Demonstrating Special Cases

Save the entire program below as `FloatingDiagnosticsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;
import java.util.stream.DoubleStream;

public class FloatingDiagnosticsDemo {
    public static void main(String[] args) {
        double nan = 0.0 / 0.0;
        double positiveInfinity = 1.0 / 0.0;
        double negativeInfinity = -1.0 / 0.0;
        double positiveZero = 0.0;
        double negativeZero = -0.0;
        double subnormal = Double.MIN_VALUE;

        System.out.println("NaN detected: " + Double.isNaN(nan));
        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("NaN != NaN: " + (nan != nan));
        System.out.println("Infinity positive: "
                + (positiveInfinity == Double.POSITIVE_INFINITY));
        System.out.println("Infinity negative: "
                + (negativeInfinity == Double.NEGATIVE_INFINITY));
        System.out.println("Infinity finite: "
                + Double.isFinite(positiveInfinity));
        System.out.println("Signed zeros primitive equal: "
                + (positiveZero == negativeZero));
        System.out.println("Signed zeros boxed equal: "
                + Double.valueOf(positiveZero).equals(Double.valueOf(negativeZero)));
        System.out.println("Negative zero reciprocal: " + (1.0 / negativeZero));
        System.out.println("Signed zero ordering: "
                + (Double.compare(negativeZero, positiveZero) < 0));
        System.out.println("Subnormal positive: " + (subnormal > 0.0));
        System.out.println("Subnormal below normal: "
                + (subnormal < Double.MIN_NORMAL));
        System.out.println("Subnormal half underflow: "
                + (subnormal / 2.0 == 0.0));
        System.out.println("Next after zero: "
                + (Math.nextUp(0.0) == subnormal));
        System.out.println("Negative zero raw sign: "
                + (Double.doubleToRawLongBits(negativeZero) == Long.MIN_VALUE));
        System.out.println("Nonempty average can be NaN: "
                + Double.isNaN(DoubleStream.of(1.0, Double.NaN)
                        .average().orElseThrow()));

        Set<Double> samples = new HashSet<>();
        samples.add(positiveZero);
        samples.add(negativeZero);
        samples.add(Double.NaN);
        samples.add(Double.longBitsToDouble(0x7ff8000000000001L));
        System.out.println("HashSet size: " + samples.size());
        System.out.println("HashSet contains NaN: "
                + samples.contains(Double.NaN));
        System.out.println("Boxed NaN equals NaN: "
                + Double.valueOf(Double.NaN).equals(Double.valueOf(nan)));
    }
}
```

Compile and run:

```bash
javac FloatingDiagnosticsDemo.java
java FloatingDiagnosticsDemo
```

Verified stdout:

```text
NaN detected: true
NaN == NaN: false
NaN != NaN: true
Infinity positive: true
Infinity negative: true
Infinity finite: false
Signed zeros primitive equal: true
Signed zeros boxed equal: false
Negative zero reciprocal: -Infinity
Signed zero ordering: true
Subnormal positive: true
Subnormal below normal: true
Subnormal half underflow: true
Next after zero: true
Negative zero raw sign: true
Nonempty average can be NaN: true
HashSet size: 3
HashSet contains NaN: true
Boxed NaN equals NaN: true
```

The output relies only on properties with deterministic contracts; it does not depend on random number generators or `HashSet` iteration order. The pair of NaNs added to the Set have different raw bit payloads, yet `Double.equals` still treats them as the same key.

## 8. `Double.isFinite`: Validating Both Inputs and Outputs

For many business domains, the minimum requirement is that **values must be finite**. Java provides:

```java
Double.isNaN(x);       // Only NaN
Double.isInfinite(x);  // Only +Infinity or -Infinity
Double.isFinite(x);    // Neither NaN nor infinity
```

These three lines illustrate the API with a `double` variable `x` inside a method. `Double.isFinite` returns true for +0.0, -0.0, and subnormal numbers. It does **not** check whether a value lies within business bounds or has exact precision.

When a division requires a finite result and a nonzero denominator, check both input and output. Example saved in `FiniteValueDemo.java`:

```java
public class FiniteValueDemo {
    static double divideFinite(double numerator, double denominator) {
        if (!Double.isFinite(numerator) || !Double.isFinite(denominator)) {
            throw new IllegalArgumentException("Inputs must be finite");
        }
        if (denominator == 0.0) {
            throw new IllegalArgumentException("Denominator must be nonzero");
        }
        double result = numerator / denominator;
        if (!Double.isFinite(result)) {
            throw new ArithmeticException("Result is not finite");
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("4 / 2 = " + divideFinite(4.0, 2.0));
        try {
            divideFinite(1.0, -0.0);
        } catch (IllegalArgumentException e) {
            System.out.println("Negative zero rejected");
        }
        try {
            divideFinite(Double.MAX_VALUE, 0.5);
        } catch (ArithmeticException e) {
            System.out.println("Overflow rejected");
        }
        try {
            divideFinite(Double.NaN, 1.0);
        } catch (IllegalArgumentException e) {
            System.out.println("NaN rejected");
        }
    }
}
```

Run:

```bash
javac FiniteValueDemo.java
java FiniteValueDemo
```

Verified stdout:

```text
4 / 2 = 2.0
Negative zero rejected
Overflow rejected
NaN rejected
```

The function intentionally rejects both forms of zero as the denominator with `denominator == 0.0`; this condition catches both +0.0 and -0.0. It also checks the result after division, because `Double.MAX_VALUE / 0.5` has finite inputs and a nonzero denominator yet **its result overflows to Infinity**.

This is an example contract when results *must be finite*. Some scientific applications intentionally use Infinity or NaN and need a different policy. Do not lump all cases into a generic error without considering business semantics.

## 9. Comparison, Sorting, Min/Max, and Collections

Primitive relational operators, `Double.compare`, `Double.equals`, and `HashSet`/`HashMap` follow different rules. Distinguish them before writing filter predicates or numeric keys.

| Value pair | `primitive ==` | `Double.equals` | `Double.compare` |
| --- | --- | --- | --- |
| `+0.0` and `-0.0` | true | false | `compare(-0.0, +0.0) < 0` |
| `NaN` and `NaN` | false | true | 0 |
| `+Infinity` and `+Infinity` | true | true | 0 |
| `1.0` and `1.0` | true | true | 0 |

`Double.compare` uses a total order useful for sorting: `-Infinity` is less than finite numbers, finite numbers are ordered by value with `-0.0 < +0.0`, followed by `+Infinity` and then NaN. Do not turn this sorting rule into a claim that NaN is mathematically the “largest number”.

`Math.min` and `Math.max` follow a different rule from `Double.compare` in that NaN **propagates**: if one argument is NaN, the result is NaN. For signed zero, `Math.min(+0.0, -0.0)` returns -0.0 and `Math.max(+0.0, -0.0)` returns +0.0.

If you need extrema while **ignoring NaN**, define a filtering policy beforehand; if you want to reject abnormal data, validate with `Double.isFinite`. Do not rely on `min`/`max` to “auto-heal” inputs.

## 10. NaN and Statistics: A Present `Optional` Can Still Hold NaN

With `DoubleStream.average()`, an empty stream returns `OptionalDouble.empty()`. However, a **non-empty** stream containing NaN can return a present `OptionalDouble` containing NaN:

```java
var result = java.util.stream.DoubleStream
        .of(1.0, Double.NaN)
        .average();

System.out.println(result.isPresent()); // true
System.out.println(Double.isNaN(result.orElseThrow())); // true
```

This is an illustrative snippet inside a method; the runnable code in the program in section 7 verifies this scenario.

**“No samples”** and **“has samples yet aggregation returns NaN”** are two distinct states. If business rules disallow NaN or infinity, validate input data before aggregation or check results per a defined rule. Avoid silently filtering NaN out of data if doing so alters the meaning of sample count, especially in data-quality reporting.

An aggregation full of NaNs cannot magically turn into a valid average. Besides NaN, accumulating very large finite values can also overflow to Infinity, so there is no guarantee that “all finite inputs” yield a finite output.

## 11. Underflow and Numerical Algorithms: Understanding Properly

**Overflow** occurs when a mathematically finite result exceeds the finite representable range and can become Infinity. **Underflow** occurs when a result has tiny magnitude, loses precision, becomes subnormal, or rounds to signed zero.

Example:

```java
double tiny = Double.MIN_VALUE;
double half = tiny / 2.0;    // +0.0, underflow
double huge = Double.MAX_VALUE;
double twice = huge * 2.0;  // Infinity, overflow
```

Subnormals provide a cushion instead of immediately flushing every value below `Double.MIN_NORMAL` to zero. Even so, this region has fewer significant relative digits; computing relative errors like `Math.abs(actual - expected) / Math.abs(expected)` with tiny `expected` can become unstable, overflow, or divide by zero.

Some practical guidelines:

- Avoid subtracting two nearly equal numbers when an algorithm has a more stable equivalent formula.
- For products of many tiny probabilities, consider working in log space when appropriate.
- When checking near zero, use a tolerance designed for the problem's scale; one fixed epsilon for all data can fail.
- Do not infer that `x == 0.0` means zero signal; it may be the result of underflow.
- Do not disable or substitute subnormals without knowing precision requirements and the runtime platform.

For financial calculations requiring exact decimals, `BigDecimal` can be more suitable than `double`, though you must still handle scale, rounding, resource limits, and non-terminating decimal divisions.

## 12. Parsing, Formatting, and API Boundaries

Java can represent `NaN` and `Infinity` as strings when calling `Double.toString`:

```java
System.out.println(Double.toString(Double.NaN)); // NaN
System.out.println(Double.toString(Double.POSITIVE_INFINITY)); // Infinity
System.out.println(Double.toString(-0.0)); // -0.0
```

`Double.parseDouble("NaN")` returns NaN, and `Double.parseDouble("Infinity")` returns positive infinity. That does not mean every data interchange protocol permits them.

**Standard JSON has no `NaN` or `Infinity` numeric tokens.** Some libraries refuse to serialize non-finite values while others have special modes; choose a clear contract: reject the request, represent an error state, use a nullable field, or define and validate a special string. Do not emit a `NaN` token as a JSON number assuming every client can parse it.

**`BigDecimal` has no NaN or Infinity.** Consequently, `BigDecimal.valueOf(Double.NaN)` and `new BigDecimal("Infinity")` do not create valid decimal values; they throw `NumberFormatException`. Converting from `double` to `BigDecimal` requires checking finiteness, while also recognizing that the original `double` value may already be an approximation.

**Databases and external systems:** some DBMSs have representations or rules for non-finite floating-point values, while others do not; sorting, grouping, indexing, and comparison behavior may differ from Java. Validate values and schemas at boundaries rather than relying on one system's default behavior.

**Signed zero on export:** a system may decide to preserve the negative sign to retain measurement information or normalize -0.0 to 0.0 for display. If normalizing, do so at a defined boundary rather than imposing it arbitrarily on every numerical algorithm.

## 13. Properly Testing Special Values

Floating-point tests should state precisely the expected result kind:

| Objective | Appropriate assertion |
| --- | --- |
| Detect NaN | `Double.isNaN(actual)` |
| Detect positive infinity | `actual == Double.POSITIVE_INFINITY` |
| Ensure finite value | `Double.isFinite(actual)` |
| Distinguish -0.0 and +0.0 | `Double.doubleToRawLongBits(actual)` or `Double.compare` |
| Confirm subnormal | `actual != 0.0 && Math.abs(actual) < Double.MIN_NORMAL` and finite |
| Confirm underflow to zero | Check zero output along with input conditions and operation contract |
| Approximate finite comparison | Domain- and magnitude-appropriate tolerance, after handling NaN/Infinity |

Do not merely use `Math.abs(expected - actual) < tolerance` without checking special cases. If `actual` is NaN, the comparison evaluates to false; if both are infinities of the same sign, subtraction produces NaN even if under some policy they are considered equivalent. Defining approximate equality must explicitly state the **policy for NaN, infinity, signed zero**, and tolerance selection.

An example checking finiteness and error for finite values:

```java
static boolean closeFinite(double left, double right,
                           double absoluteTolerance) {
    if (!Double.isFinite(left) || !Double.isFinite(right)
            || !Double.isFinite(absoluteTolerance)
            || absoluteTolerance < 0.0) {
        return false;
    }
    return Math.abs(left - right) <= absoluteTolerance;
}
```

This is a sample method to place inside a class. If subtracting `left - right` overflows to Infinity even when both inputs are finite, the result is false, matching “not close to each other” in this check. For data spanning many orders of magnitude, add a relative tolerance with careful overflow handling rather than relying on a single absolute threshold.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `x == Double.NaN` | Always false | `Double.isNaN(x)` |
| Assuming every division by 0 throws `ArithmeticException` | Wrong for `double`/`float`; produces Infinity/NaN | Distinguish integer and floating-point arithmetic |
| Treating Infinity as a normal number | Can propagate invalid values | `Double.isFinite` and domain validation |
| Validating only finite inputs | Operations can still overflow to Infinity | Validate outputs |
| Assuming `+0.0` and `-0.0` share raw bits | Bugs in reciprocals, serialization, or hashing | Check `Double.compare`/raw bits when needed |
| Thinking `Double.MIN_VALUE` is the most negative number | Confuses subnormal range | Distinguish `MIN_VALUE`, `MIN_NORMAL`, `-MAX_VALUE` |
| Treating subnormals as zero | Loses tiny finite numbers | Check `0 < abs(x) < MIN_NORMAL` |
| Assuming a present `OptionalDouble` is finite | NaN/Infinity can still be held inside | Distinguish presence and `Double.isFinite` |
| Sending NaN/Infinity as a JSON number without policy | Non-standard data or inconsistent library behavior | Normalize/serialize per agreed schema |
| Using `double` for exact money | Binary representation error | Choose `BigDecimal` with appropriate rounding |
| Assuming NaN in hash collections behaves like `primitive ==` | Wrong: `Double.equals` treats NaNs as equal | Use the API suited to the intent |

## 15. Self-Check Questions

1. **What does `0.0 / 0.0` return?** NaN; not an integer division exception.
2. **What does `1.0 / -0.0` return?** Negative infinity.
3. **Is `Double.NaN == Double.NaN` true or false?** False; use `Double.isNaN` to detect NaN.
4. **What is `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))`?** True, because the wrapper class defines NaN equality for objects and collections.
5. **What is `0.0 == -0.0`?** True for primitives, yet `Double.equals` distinguishes the two representations.
6. **Is `Double.MIN_VALUE` infinitely negative?** No; it is the **smallest nonzero positive subnormal** number.
7. **Is a subnormal finite?** Yes; it is nonzero, not NaN, and not infinite, though its relative precision is lower than normal numbers.
8. **What does `Double.MIN_VALUE / 2.0` give?** `+0.0` due to underflow and rounding.
9. **Can a non-empty dataset and `DoubleStream.average()` return NaN?** Yes; a present `Optional` does not guarantee a finite number.
10. **Is validating inputs with `Double.isFinite` enough for outputs?** No; multiplying or dividing finite inputs can still overflow to infinity.
11. **Why check for NaN/Infinity before JSON?** Standard JSON numbers have no NaN/Infinity tokens; data exchange interfaces must specify how to handle them.
12. **Why not always normalize `-0.0` to `+0.0`?** The sign can carry important information in numerical algorithms or result rules; normalize only if the domain requires it.

## 16. Key Takeaways

`float`/`double` represent far more than ordinary finite numbers. **NaN** makes primitive comparisons differ from expectations; **±Infinity** arises from division by zero and overflow; **±0.0** are equal under `==` yet differ in bits and certain operations; **subnormals** represent tiny numbers before underflowing to zero.

When implementing, clearly determine whether an API uses **primitive comparison**, **wrapper ordering**, or **`equals`/`hashCode`**. Use `Double.isNaN`, `Double.isInfinite`, and `Double.isFinite` for diagnostics; validate both inputs and outputs when finiteness is required; keep policies for missing data, rounding, min/max, and serialization consistent. The Java 17+ examples demonstrate that understanding these boundary cases matters more than testing only ordinary numbers.
