# Testing Comparisons with Appropriate Tolerances in Java

When testing or diagnosing numeric calculations, comparing two results with `==` or `equals()` does not always reflect the true requirement. With binary floating-point numbers (`float`, `double`), the desired mathematical result may be represented by an approximation. Conversely, allowing too wide a tolerance can cause a **test to accept genuinely wrong results**.

The goal of this lesson is to choose an **equality criterion suited to the number type and measurement/business requirements**, using absolute tolerance, relative tolerance, or a combination of both when appropriate, and to test special cases such as numbers near 0, varying magnitudes, `NaN`, infinities, negative zero, and `BigDecimal`.

**Principle:** before writing an assertion, answer “In what sense must these two results be equal, and how much deviation is allowed?”. There is no single `epsilon` constant right for every calculation, every unit, and every value range.

## 1. Why Should `double` Usually Not Be Compared Exactly with `==`?

Java's `double` type uses IEEE 754 binary representation with finite precision. Many simple decimal fractions, such as 0.1 or 0.2, have no exact finite binary representation. When stored and computed, values must be rounded according to floating-point rules.

Example:

```java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual);             // 0.30000000000000004
System.out.println(actual == expected); // false
```

`actual` and `expected` are two close `double` values, yet they **differ in bits**, so `==` returns `false`. In an approximation test, a very small deviation may be acceptable if requirements permit.

However, `==` is **not wrong in every case**:

- When testing a value required to be exact, such as a small integer represented exactly in `double`, exact comparison can be appropriate.
- When testing special values or states, you may need an **exact** check or bit check, not a tolerance.
- When business requirements demand absolute precision, you cannot patch a wrong data-type design by arbitrarily adding an epsilon.

Differences in floating-point numbers can stem from input representation, operation ordering, rounding at each step, algebraic transformations, or approximation algorithms. An “acceptance interval” is only useful when there is a **basis for determining valid deviation**.

## 2. Absolute Error: Use When Units and Maximum Deviation Matter

Let the reference value be `expected` and the result under test be `actual`:

```text
absoluteError = |actual - expected|

Accept when:
|actual - expected| <= absoluteTolerance
```

For example, if a measurement may deviate by at most 0.01 units, you can check:

```java
boolean acceptable =
        Math.abs(actual - expected) <= 0.01;
```

This is an **illustrative snippet** assuming `actual` and `expected` are finite `double` values in the same unit, not so large that their difference overflows. Cases of `NaN` or infinity must be handled separately if the test can encounter them.

### Benefits and Limitations

Absolute error is easy to express in units—for instance “must not deviate by more than 0.001 seconds” or “must not deviate by more than 0.1 °C”—**if that limit is actually specified**. It is especially useful near **zero**.

However, a fixed threshold can be too loose for very small numbers or too strict for very large numbers:

| Expected | Actual | Absolute error | Result with tolerance = 0.001 |
|---:|---:|---:|---|
| 0 | 0.0005 | 0.0005 | Accept |
| 1000 | 1000.0005 | 0.0005 | Accept |
| 1,000,000,000 | 1,000,000,000.1 | Approx. 0.1 | Reject |

The last example has a relative deviation of about one part in ten billion, yet is rejected by the absolute threshold of 0.001. Whether this is right or wrong depends on the requirement: if the absolute error must be less than 0.001, it **must be rejected**, no matter how large the numbers are.

## 3. Relative Error: Evaluating Deviation by Magnitude

Another criterion compares the deviation to the magnitude of the reference value:

```text
relativeError = |actual - expected| / |expected|
```

This formula breaks down when `expected = 0`, because dividing by 0 does not yield a useful relative error. If `expected` is close to 0, the ratio can also amplify a tiny absolute difference.

When comparing two approximate values **symmetrically**, you can use the metric:

```text
scale = max(|expected|, |actual|)
relativeCondition: |actual - expected| <= relTol * scale
```

If both equal 0, exact equality is already satisfied. When two numbers are very close to 0 yet unequal, a relative criterion alone is often too strict; at that point an absolute threshold must be considered.

**Distinction needed:** “relative error with respect to `expected`” and “symmetric relative threshold based on max magnitude” are two different definitions. In test documentation, write out the formula explicitly instead of merely saying “use a relative epsilon”.

## 4. Combining Absolute Tolerance and Relative Tolerance

A general check for many finite `double` calculations is:

```text
diff = |actual - expected|
scale = max(|expected|, |actual|)

acceptable = diff <= max(absTol, relTol * scale)
```

Explanation:

- **`absTol`** is the allowed absolute deviation, useful around 0.
- **`relTol`** allows deviation to scale with magnitude, useful for very large quantities.
- Using `max` means either bound suffices for acceptance. This is an **OR-combined** tolerance policy, not equivalent to “must satisfy both simultaneously”.
- If business logic requires **both** absolute and relative errors to be below thresholds, check **two separate AND conditions**. Do not arbitrarily use the `max` formula for a stricter contract.

Hypothetical example with `absTol = 1e-12` and `relTol = 1e-9`:

| Expected | Actual | Evaluation |
|---:|---:|---|
| `0.3` | `0.1 + 0.2` | Accept: tiny binary error |
| `0.0` | `1e-13` | Accept: within absolute threshold |
| `0.0` | `1e-8` | Reject: exceeds absolute threshold and relative criterion |
| `1e9` | `1e9 + 0.1` | Accept: small proportional error |
| `1.0` | `1.1` | Reject: deviation too large |

**The thresholds above are for illustration only**, not default values to copy into every project. When testing scientific algorithms, thresholds may come from numerical error analysis, approximation quality, or precision requirements. For physical measurements, instrument resolution may need to be considered. For financial, counting, or identifier data, different rules must apply.

### A Safe Approximate-Equality Helper for `double`

```java
static boolean nearlyEqual(
        double expected, double actual,
        double absTol, double relTol) {

    if (!Double.isFinite(absTol) || absTol < 0.0
            || !Double.isFinite(relTol)
            || relTol < 0.0 || relTol >= 1.0) {
        throw new IllegalArgumentException(
                "Invalid tolerance");
    }

    if (Double.isNaN(expected) || Double.isNaN(actual)) {
        return false;
    }

    if (expected == actual) {
        return true;
    }

    if (!Double.isFinite(expected) || !Double.isFinite(actual)) {
        return false;
    }

    double difference = Math.abs(actual - expected);
    double scale = Math.max(Math.abs(expected), Math.abs(actual));

    return difference <= Math.max(absTol, relTol * scale);
}
```

This is **a method** that can be placed inside a Java class. Its design decisions should be clearly understood:

1. Tolerances are required to be finite and non-negative; `relTol < 1` prevents a meaningless relative threshold that could accept huge differences. This is a constraint of the **illustrative function**, not a universal limit for every API.
2. `NaN` is always treated as not nearly equal, even when both sides are `NaN`. If a test **expects NaN**, check separately with `Double.isNaN(...)`.
3. Two infinities of the same sign are treated as equal in the `expected == actual` branch; one finite and one infinite side, or opposite infinities, are rejected.
4. `+0.0` and `-0.0` are considered equal in **numerical value**. If a test requires distinguishing the sign of 0, compare bits.
5. For two huge finite values of opposite signs, subtraction can overflow to infinity. The function rejects that, consistent with the finite tolerance policy and `relTol < 1` here.
6. The function does not infer `absTol`/`relTol` on its own; callers must supply them based on the problem.

Do not write a “nearly equal” helper that silently lets `NaN` or infinity pass an error condition simply because IEEE 754 arithmetic produces special values.

## 5. Special Boundary Cases

### 5.1. Near 0 and Negative Zero

The ratio `|actual - expected| / |expected|` is not usefully defined when `expected` is 0. Hence absolute error is crucial when comparing results expected near 0:

```java
nearlyEqual(0.0, 1e-13, 1e-12, 1e-9); // true
nearlyEqual(0.0, 1e-8, 1e-12, 1e-9);  // false
```

In Java, `+0.0 == -0.0` is `true`. Yet the sign bits of the two values differ, and some operations produce different results: `1.0 / +0.0` is `+Infinity`, whereas `1.0 / -0.0` is `-Infinity`.

If the sign of zero **is part of the contract**, check bits:

```java
boolean sameBits = Double.doubleToRawLongBits(0.0)
        == Double.doubleToRawLongBits(-0.0); // false
```

Bit comparison can also distinguish `NaN` bit patterns; use it only when the requirement is genuinely tied to IEEE 754 representation.

### 5.2. NaN

`Double.NaN` represents “Not a Number”. Under IEEE 754 primitive comparison:

```java
System.out.println(Double.NaN == Double.NaN); // false
System.out.println(Double.isNaN(Double.NaN));   // true
```

If the test's purpose is to catch an algorithm that **should have produced a finite number**, a `NaN` result must be rejected. If the algorithm is **specified to return NaN** for an invalid input, assert `Double.isNaN(actual)`. Do not treat a tolerance interval as a tool for checking `NaN`.

### 5.3. Infinity and Floating-Point Overflow

`Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` are special values. Two matching infinities compare equal with `==`, yet infinity minus itself yields `NaN`; thus a formula using only `Math.abs(expected - actual)` is insufficient.

If the algorithm must return a finite number, check `Double.isFinite(actual)` before comparing. If infinity is a specified valid result, test that case explicitly, separate from tolerance checks.

### 5.4. ULP: Spacing Between Adjacent Floating-Point Values

`Math.ulp(x)` returns the size of one *unit in the last place* at `x` according to its magnitude and floating-point representation. Example:

```java
System.out.println(Math.ulp(1.0)); // 2.220446049250313E-16
```

In testing numerical algorithms, error is sometimes specified in ULPs (for example, the result is only a few representable `double` values away from the reference). This can be useful when evaluating the rounding characteristics of a specific algorithm.

However, **a fixed ULP count is not a universal business threshold either**. ULP spacing changes with magnitude, requires care near 0, in the subnormal region, across 0, with opposite-sign numbers, and when one side is `NaN` or infinity. Do not arbitrarily use `Math.ulp(expected)` as a default epsilon for testing every calculation.

## 6. Complete Java 17+ Example with Deterministic Results

Save the file `NumericToleranceDemo.java`:

```java
import java.math.BigDecimal;

public class NumericToleranceDemo {
    static boolean nearlyEqual(
            double expected, double actual,
            double absTol, double relTol) {

        if (!Double.isFinite(absTol) || absTol < 0.0
                || !Double.isFinite(relTol)
                || relTol < 0.0 || relTol >= 1.0) {
            throw new IllegalArgumentException("Invalid tolerance");
        }
        if (Double.isNaN(expected) || Double.isNaN(actual)) {
            return false;
        }
        if (expected == actual) {
            return true;
        }
        if (!Double.isFinite(expected) || !Double.isFinite(actual)) {
            return false;
        }
        double difference = Math.abs(actual - expected);
        double scale = Math.max(Math.abs(expected), Math.abs(actual));
        return difference <= Math.max(absTol, relTol * scale);
    }

    static boolean withinDecimalTolerance(
            BigDecimal expected,
            BigDecimal actual,
            BigDecimal tolerance) {
        if (tolerance.signum() < 0) {
            throw new IllegalArgumentException("Negative tolerance");
        }
        return actual.subtract(expected).abs()
                .compareTo(tolerance) <= 0;
    }

    public static void main(String[] args) {
        double absTol = 1e-12;
        double relTol = 1e-9;

        System.out.println("exact double: " + ((0.1 + 0.2) == 0.3));
        System.out.println("near double: "
                + nearlyEqual(0.3, 0.1 + 0.2, absTol, relTol));
        System.out.println("near zero pass: "
                + nearlyEqual(0.0, 1e-13, absTol, relTol));
        System.out.println("near zero fail: "
                + nearlyEqual(0.0, 1e-8, absTol, relTol));
        System.out.println("large magnitude: "
                + nearlyEqual(1e9, 1e9 + 0.1, absTol, relTol));
        System.out.println("far values: "
                + nearlyEqual(1.0, 1.1, absTol, relTol));

        System.out.println("NaN near NaN: "
                + nearlyEqual(Double.NaN, Double.NaN, absTol, relTol));
        System.out.println("same +infinity: "
                + nearlyEqual(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, absTol, relTol));
        System.out.println("opposite infinities: "
                + nearlyEqual(Double.POSITIVE_INFINITY,
                        Double.NEGATIVE_INFINITY, absTol, relTol));
        System.out.println("signed zero near: "
                + nearlyEqual(0.0, -0.0, absTol, relTol));
        System.out.println("signed zero same bits: "
                + (Double.doubleToRawLongBits(0.0)
                   == Double.doubleToRawLongBits(-0.0)));

        BigDecimal exactA = new BigDecimal("1.00");
        BigDecimal exactB = new BigDecimal("1.000");
        System.out.println("BigDecimal equals: "
                + exactA.equals(exactB));
        System.out.println("BigDecimal numeric equal: "
                + (exactA.compareTo(exactB) == 0));
        System.out.println("BigDecimal within 0.01: "
                + withinDecimalTolerance(exactA,
                        new BigDecimal("1.009"),
                        new BigDecimal("0.01")));
        System.out.println("BigDecimal outside 0.01: "
                + withinDecimalTolerance(exactA,
                        new BigDecimal("1.011"),
                        new BigDecimal("0.01")));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac NumericToleranceDemo.java
java NumericToleranceDemo
```

Output:

```text
exact double: false
near double: true
near zero pass: true
near zero fail: false
large magnitude: true
far values: false
NaN near NaN: false
same +infinity: true
opposite infinities: false
signed zero near: true
signed zero same bits: false
BigDecimal equals: false
BigDecimal numeric equal: true
BigDecimal within 0.01: true
BigDecimal outside 0.01: false
```

Key takeaways in the program:

- `0.1 + 0.2 == 0.3` fails **exact equality**, yet passes with the declared test tolerance.
- The same combined threshold must still reject `0` vs `1e-8` or `1.0` vs `1.1`. A tolerance that is too wide has no bug-catching value.
- `NaN` is not accepted as “near a number”; infinities need separate rules.
- In `BigDecimal`, numerical equality and representation equality can differ due to scale. Comparing against an **exact decimal tolerance interval** does not require converting to `double`.

## 7. `BigDecimal`: Do Not Use Epsilon as a Default Reflex

`BigDecimal` represents decimal values as `unscaledValue × 10^(-scale)`, suitable when exact decimal arithmetic control is needed. With two `BigDecimal` values, first clarify the requirement:

| Need | How to check |
|---|---|
| Same numerical value, ignoring scale | `a.compareTo(b) == 0` |
| Same numerical value **and** same scale | `a.equals(b)` |
| Allow a specified decimal deviation | `a.subtract(b).abs().compareTo(tolerance) <= 0` |
| Result must meet a specific business scale/mode | Normalize/round per approved policy then check value and scale accordingly |

Example:

```java
BigDecimal expected = new BigDecimal("10.00");
BigDecimal actual = new BigDecimal("10.005");

BigDecimal tolerance = new BigDecimal("0.01");

boolean within = actual.subtract(expected).abs()
        .compareTo(tolerance) <= 0; // true
```

This approach **does not use `doubleValue()`**, so it introduces no binary conversion error. Still, allowing a 0.01 deviation remains a **testing/business decision**, not a default property of `BigDecimal`.

As another example, if the requirement is “must compute exactly 10.00 at scale 2”, accepting `10.005` because it is “off by no more than 0.01” hides an incorrect result. When testing totals, transactions, or taxes, use the official policy on precision, scale, rounding order, and rounding boundaries as the standard.

### Do Not Infer Epsilon from Scale

`new BigDecimal("1.00")` has scale 2, yet that does not mean the maximum allowed error is `0.01` or `0.005`. A scale-2 value may already be rounded, may have been entered verbatim, or may simply be a storage format.

Similarly, a database `DECIMAL(p, s)` column or an API accepting `BigDecimal` **does not by itself tell you** what deviation is acceptable. Tolerance must come from the specification, measurement method, error analysis, or business requirements.

## 8. Testing with Assertions: Do Not Let Thresholds Mask Bugs

In JUnit Jupiter, for example:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

// Example inside a @Test
assertEquals(0.3, 0.1 + 0.2, 1e-12);
```

This example **depends on JUnit Jupiter** and is not a standalone JDK-only Java program. The `delta` parameter in the floating-point comparison overload is an **absolute** tolerance threshold for numeric deviation, handling special values per the API's contract. It does not implement the **combined absolute and relative** formula from section 4.

If a combined tolerance is required, use a tested custom helper:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

// Example inside a @Test
assertTrue(nearlyEqual(expected, actual, absTol, relTol));
```

When an assertion fails, diagnostics should show **expected, actual, absolute error, applied threshold, and unit** if available. This helps distinguish logic bugs, acceptable calculation error, and misconfigured tolerances.

A few notes:

- Do not use `assertEquals(expected, actual, 0.0)` as if it automatically handles all floating-point error; when exactness is required, state that explicitly.
- Do not set `delta` overly large just to “make the test turn green”. Tolerance is part of the **specification**, not a tool for dodging bugs.
- Do not mix approximate checks with integer or identifier comparisons: IDs, iteration counts, and array indices usually require **exact equality**.
- Do not assume the same tolerance fits seconds, lengths, percentages, currency, or probabilities. **Units and scales** determine what a threshold means.

## 9. On What Requirements Should Error Thresholds Be Based?

A tolerance should stem from one or more of the following grounds:

1. **Allowed error in the business contract or measurement standard:** for example, measured values with published instrument resolution and error.
2. **Algorithm error analysis:** number of operations, numerical stability, cancellation loss on subtraction, conditioning of the problem, and accumulated rounding error.
3. **Data range and units:** `expected` near 0, very large, positive/negative, or spanning many orders of magnitude.
4. **Reference standard and accuracy of `expected`:** is the “true” result an exact mathematical value, a high-precision approximation, or an experimental measurement that also has error?
5. **Special-value behavior:** are `NaN`, `Infinity`, `-0.0`, or overflow/underflow accepted?
6. **Purpose of the test:** verifying an exact invariant, cross-checking an approximate algorithm, regression testing across platforms, or verifying compliance with regulated tolerances.

**Distinguish machine precision from business error:** `Math.ulp(1.0)` is a property of binary floating-point numbers near 1, not the allowed error of a physical measurement or an accounting system. An unstable calculation can accumulate deviations of many ULPs; conversely, a business rule may forbid any numeric discrepancy no matter how small.

If there is no explicit error contract, tests should document the assumed tolerance interval and **confirm it with the calculation owner**, rather than assigning an ungrounded default constant.

## 10. Common Mistakes

1. **Picking `epsilon = 1e-6` for all numbers.** That threshold can be meaningless when units, value ranges, or requirements change.
2. **Using only relative error near 0.** A zero or tiny denominator makes the ratio useless. Add absolute error when appropriate.
3. **Using only absolute error across multiple orders of magnitude.** It can reject a value with tiny relative error or accept large relative error on small numbers; decide strictly from requirements.
4. **Treating all `NaN` values as equal inside an approximate-comparison helper.** A buggy function returning `NaN` can slip through. Test `NaN` explicitly when it is the specified result.
5. **Ignoring infinity and negative zero.** These values have special IEEE 754 semantics; an explicit policy is needed.
6. **Converting `BigDecimal` to `double` to compare with an epsilon.** Doing so forfeits the advantage of exact decimal arithmetic.
7. **Using `BigDecimal.equals()` when only numerical equality is needed.** `1.0` and `1.00` are not `equals()`, yet `compareTo() == 0`.
8. **Using tolerance to mask business rounding bugs.** An invoice required to be exact to 2 decimal places under an approved rule should not pass merely because a wrong number is close to the result.
9. **Failing to test boundary values right around the tolerance.** Test at the threshold, slightly below, slightly above, negative numbers, and near 0; understand that the tolerance itself might not have an exact decimal representation in `double`.
10. **Relying on a single run matching to conclude an algorithm is accurate.** Numerical calculations can vary with inputs and operation order; test across representative domains and key invariants.

## 11. Self-Check

**Question 1.** Why can `0.1 + 0.2 == 0.3` be `false` in Java?  
**Answer:** `double` uses finite binary representation; 0.1 and 0.2 cannot be stored exactly, leading to a discrepancy between the addition result and the approximate representation of 0.3.

**Question 2.** When `expected` is 0, should you divide absolute error by `|expected|` to compute relative error?  
**Answer:** No; the denominator is 0. Use an absolute error criterion determined by the problem, or another appropriate policy.

**Question 3.** With `absTol = 1e-12` and `relTol = 1e-9`, does checking `expected = 0`, `actual = 1e-8` pass?  
**Answer:** No; the difference `1e-8` exceeds both the absolute threshold `1e-12` and the relative limit based on the pair's magnitude.

**Question 4.** In the helper above, are two `NaN` values considered nearly equal?  
**Answer:** No. If NaN is the expected result, use `Double.isNaN(actual)`.

**Question 5.** How should `BigDecimal("1.0")` and `BigDecimal("1.00")` be compared if only equal numerical value is required?  
**Answer:** `a.compareTo(b) == 0`. `equals()` also checks scale.

**Question 6.** When testing monetary values that must be exact to two decimal places under an approved rule, should you use an arbitrary epsilon?  
**Answer:** No. Compute and round under the official policy, then assert the value (and scale if required by the contract) using `BigDecimal`.

**Question 7.** Is `Math.ulp(1.0)` the “standard epsilon for every algorithm”?  
**Answer:** No; ULP varies with value range and does not by default reflect measurement error, algorithmic error, or business-acceptable deviation.

**Takeaway:** Compare **exactly** when the contract requires exactness; use **absolute error** in units when fixed deviation matters; use **relative error** when magnitude-scaled deviation matters; use a **controlled combination** for wide ranges and near 0. Every threshold must have a testing rationale, never derived arbitrarily from the numeric type alone.
